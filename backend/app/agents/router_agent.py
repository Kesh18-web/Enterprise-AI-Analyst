"""
Model Router Agent — Smart, clean model selection.

Priority order:
  1. User explicitly picked a model from the frontend selector  → use it directly (0ms)
  2. Auto mode                                                  → lightweight Groq call to decide
                                                                   between gemini-2.0-flash and groq
  3. Groq unavailable for auto call                            → deterministic fallback (0ms)
"""
import json
from typing import Any, Dict

from backend.app.core.config import settings
from backend.app.core.logging import logger, logger_timer
from backend.app.core.state import AnalystState

# Model identifiers used throughout the system
MODEL_DEEPSEEK = "deepseek"
MODEL_FLASH = "gemini-2.5-flash"
MODEL_PRO = "gemini-2.5-pro"
MODEL_GROQ = "groq/llama-70b"


class ModelRouterAgent:
    """
    Model Router Agent.
    For 'auto' mode: uses Groq Llama 3.3 70B to classify query complexity.
    For explicit user selections: returns immediately (0ms).
    """

    def select_model(self, task_type: str, state: AnalystState) -> str:
        trace_id = state.get("trace_id", "N/A")
        query = state.get("user_query", "")
        user_pref = state.get("user_model_preference", "auto")
        source = state.get("primary_knowledge_source", "PARAMETRIC_LLM")

        with logger_timer("ModelRouterAgent: Route Allocation", trace_id=trace_id) as log:

            # ── 1. Explicit user selection from frontend dropdown ────────────
            if user_pref == "deepseek":
                log.info(f"[Router] User-selected DeepSeek → {MODEL_DEEPSEEK}")
                return MODEL_DEEPSEEK

            if user_pref == "flash":
                log.info(f"[Router] User-selected Flash → {MODEL_FLASH}")
                return MODEL_FLASH

            if user_pref == "pro":
                log.info(f"[Router] User-selected Pro → {MODEL_PRO}")
                return MODEL_PRO

            if user_pref == "groq":
                log.info(f"[Router] User-selected Groq → {MODEL_GROQ}")
                return MODEL_GROQ

            # ── 2. Auto mode: Groq Llama 3.3 70B complexity classification ───
            if source == "ENTERPRISE_RAG":
                log.info(f"[Router] Auto (Document RAG query) → {MODEL_DEEPSEEK}")
                return MODEL_DEEPSEEK

            if settings.GROQ_API_KEY:
                try:
                    from backend.app.core.llm import get_llm

                    groq_router_llm = get_llm(model_name="groq/llama-70b", temperature=0.0)

                    prompt = (
                        "You are a query complexity classifier. Analyze this user query and decide the optimal LLM tier.\n\n"
                        "Rules:\n"
                        "- If the query is a simple factual question or quick lookup → use 'groq'\n"
                        "- If the query requires deep reasoning, document analysis, synthesis, or SOTA logic → use 'deepseek'\n\n"
                        f"Query: \"{query}\"\n"
                        f"Knowledge source needed: {source}\n\n"
                        "Reply with ONLY one word: 'deepseek' or 'groq'"
                    )

                    response = groq_router_llm.invoke(prompt)
                    decision = str(response.content).strip().lower().replace("'", "").replace("\"", "")

                    if "groq" in decision:
                        selected = MODEL_GROQ
                    else:
                        selected = MODEL_DEEPSEEK

                    log.info(f"[Router] Auto (Groq LLM) → '{decision}' → {selected}")
                    return selected

                except Exception as e:
                    log.warning(f"[Router] Groq auto-routing call failed ({e}). Using deterministic fallback.")

            log.info(f"[Router] Deterministic fallback → {MODEL_DEEPSEEK} (default)")
            return MODEL_DEEPSEEK


# Global singleton
model_router_agent = ModelRouterAgent()
