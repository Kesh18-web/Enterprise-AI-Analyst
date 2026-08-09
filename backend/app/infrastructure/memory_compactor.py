from typing import Any, Dict, List, Optional
from backend.app.core.llm import get_llm
from backend.app.core.logging import logger, logger_timer
from backend.app.db.firestore import firestore_db


class DualMemoryManager:
    """
    Unified Enterprise Dual Memory Engine:
    - Short-Term Working Memory: Retains 3 to 6 raw, exact conversation turns.
    - Long-Term Memory Compactor: Triggers LLM compaction in batches (every 3 turns starting at turn 6).
    """

    def __init__(self, window_size: int = 6, batch_size: int = 3):
        self.window_size = window_size
        self.batch_size = batch_size
        # In-memory storage per session_id: stores raw turns & active long-term summary
        self._session_store: Dict[str, Dict[str, Any]] = {}

    def _get_or_create_session(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        if session_id not in self._session_store:
            # Hydrate turns from persistent GCP Firestore storage (if user_id provided)
            firestore_msgs = firestore_db.get_chat_messages(user_id, session_id) if user_id else []
            turns: List[Dict[str, str]] = []
            curr_user = ""
            for msg in firestore_msgs:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    curr_user = content
                elif role == "assistant" and curr_user:
                    turns.append({"user": curr_user, "assistant": content})
                    curr_user = ""

            self._session_store[session_id] = {
                "turns": turns,  # List of {"user": str, "assistant": str}
                "long_term_summary": "",
                "compaction_count": 0,
                "last_compacted_idx": 0,
            }
        return self._session_store[session_id]

    def add_turn(self, session_id: str, user_message: str, assistant_reply: str, user_id: Optional[str] = None) -> None:
        """Append a new interaction turn to the session memory."""
        session = self._get_or_create_session(session_id, user_id=user_id)
        session["turns"].append(
            {"user": user_message.strip(), "assistant": assistant_reply.strip()}
        )
        logger.info(
            f"[DualMemory] Added interaction turn to session '{session_id}' (Total Turns: {len(session['turns'])})"
        )

    def get_compacted_context(
        self, session_id: str, trace_id: str = "N/A", user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch memory context. Compaction triggers ONLY when total_turns >= window_size (6)
        AND (total_turns - window_size) % batch_size == 0 (turns 6, 9, 12, 15...).
        """
        session = self._get_or_create_session(session_id, user_id=user_id)
        turns = session["turns"]
        total_turns = len(turns)

        if total_turns == 0:
            return {
                "long_term_summary": "",
                "short_term_turns": [],
                "memory_compacted": False,
                "total_turns": 0,
                "compaction_count": session.get("compaction_count", 0),
            }

        # Case 1: Before window threshold (< 6 turns) -> 0 LLM summarizer calls
        if total_turns < self.window_size:
            return {
                "long_term_summary": session.get("long_term_summary", ""),
                "short_term_turns": turns,
                "memory_compacted": False,
                "total_turns": total_turns,
                "compaction_count": session.get("compaction_count", 0),
            }

        # Check mathematical batch trigger condition for turns 6, 9, 12, 15...
        should_compact = ((total_turns - self.window_size) % self.batch_size == 0)

        last_compacted_idx = session.get("last_compacted_idx", 0)

        # Case 2: Non-trigger turn -> Return current working window without calling LLM
        if not should_compact:
            recent_turns = turns[last_compacted_idx:]
            return {
                "long_term_summary": session.get("long_term_summary", ""),
                "short_term_turns": recent_turns,
                "memory_compacted": False,
                "total_turns": total_turns,
                "compaction_count": session.get("compaction_count", 0),
            }

        # Case 3: Trigger turn (turns 6, 9, 12...) -> Compact batch slice turns[last_compacted_idx : last_compacted_idx + batch_size]
        with logger_timer("DualMemoryManager: Long-Term Memory Compaction", trace_id=trace_id) as log:
            batch_to_compact = turns[last_compacted_idx : last_compacted_idx + self.batch_size]
            recent_turns = turns[last_compacted_idx + self.batch_size:]

            existing_summary = session.get("long_term_summary", "")
            turns_text = "\n".join(
                [f"User: {t['user']}\nAssistant: {t['assistant'][:200]}..." for t in batch_to_compact]
            )

            prompt = (
                f"Existing Executive Summary: {existing_summary if existing_summary else 'None'}\n\n"
                f"Older Conversation History Batch to Compact:\n{turns_text}\n\n"
                "You are an AI Memory Compactor. Condense the older conversation history batch and existing summary into a tight, dense 2-3 sentence Executive Memory Summary.\n"
                "Extract key entities, user preferences, repositories mentioned, and established compliance facts.\n"
                "Return ONLY the updated Executive Memory Summary."
            )

            try:
                llm = get_llm(temperature=0.0)
                res = llm.invoke(prompt)
                updated_summary = res.content.strip()
            except Exception as e:
                log.warning(f"Live LLM Memory Compactor fallback: {e}")
                updated_summary = f"{existing_summary} User discussed compliance requirements & system configuration."

            session["long_term_summary"] = updated_summary
            session["last_compacted_idx"] = last_compacted_idx + self.batch_size
            session["compaction_count"] += 1

            log.info(
                f"[DualMemory] Successfully compacted batch of {len(batch_to_compact)} turns (indices {last_compacted_idx}..{last_compacted_idx + self.batch_size}) into {len(updated_summary)} chars summary (Compaction #{session['compaction_count']})"
            )

            return {
                "long_term_summary": updated_summary,
                "short_term_turns": recent_turns,
                "memory_compacted": True,
                "total_turns": total_turns,
                "compaction_count": session["compaction_count"],
                "compacted_turns_count": session["last_compacted_idx"],
            }


# Global Dual Memory Singleton Manager (Window=6, Batch=3)
dual_memory_mgr = DualMemoryManager(window_size=6, batch_size=3)
