import asyncio
from datetime import datetime
import json
import time
import uuid
from typing import AsyncGenerator, Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.responses import StreamingResponse
from backend.app.core.auth import get_current_user
from backend.app.core.logging import logger
from backend.app.core.state import AnalystState
from backend.app.db.firestore import firestore_db
from backend.app.graph.analyst_graph import analyst_graph
from backend.app.infrastructure.memory_compactor import dual_memory_mgr
from backend.app.infrastructure.telemetry_engine import telemetry_engine

router = APIRouter(prefix="/analyze", tags=["Analyze"])


class AnalyzeRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    search_scope: Optional[str] = "session"
    model_preference: Optional[str] = "auto"  # 'auto' | 'flash' | 'pro' | 'groq'


async def stream_analysis_events(
    query: str, session_id: str, user_id: str, search_scope: str = "session",
    model_preference: str = "auto",
) -> AsyncGenerator[str, None]:
    """Async generator streaming LangGraph state machine node updates via SSE."""
    trace_id = f"trace-{str(uuid.uuid4())[:8]}"
    start_stream_time = time.time()
    node_latencies: Dict[str, float] = {}

    # Fetch Dual Memory Context (Executive Long-Term Summary + Short-Term Turns)
    mem_context = dual_memory_mgr.get_compacted_context(session_id, trace_id=trace_id, user_id=user_id)

    initial_state: AnalystState = {
        "user_query": query,
        "trace_id": trace_id,
        "session_id": session_id,
        "search_scope": search_scope,
        "long_term_summary": mem_context.get("long_term_summary", ""),
        "short_term_turns": mem_context.get("short_term_turns", []),
        "memory_compacted": mem_context.get("memory_compacted", False),
        "reflection_count": 0,
        "user_model_preference": model_preference or "auto",
        "user_id": user_id,
    }

    logger.info(
        f"Starting SSE Stream Analysis | session_id={session_id} | trace_id={trace_id} | search_scope={search_scope}"
    )

    yield f"data: {json.dumps({'event': 'start', 'trace_id': trace_id, 'query': query, 'search_scope': search_scope})}\n\n"

    accumulated_state: Dict[str, Any] = dict(initial_state)

    try:
        # Iterate over graph steps cleanly in single pass
        for event in analyst_graph.stream(initial_state):
            node_start_time = time.time()
            for node_name, node_state in event.items():
                accumulated_state.update(node_state)
                node_latencies[node_name] = round((time.time() - node_start_time) * 1000, 2)

                node_log = {
                    "event": "node_complete",
                    "node": node_name,
                    "trace_id": trace_id,
                    "latency_ms": node_latencies[node_name],
                }

                if node_name == "cache":
                    node_log["cache_hit"] = node_state.get("semantic_cache_hit", False)
                elif node_name == "guardrail":
                    node_log["safe"] = node_state.get("guardrail_status", {}).get(
                        "safe"
                    )
                elif node_name == "planner":
                    plan = node_state.get("plan", {})
                    node_log["sub_tasks"] = plan.get("sub_tasks", [])
                    node_log["requires_mcp"] = plan.get("requires_mcp", False)
                    node_log["mcp_tools"] = plan.get("mcp_tools", [])

                elif node_name == "router":
                    node_log["selected_model"] = node_state.get("selected_model")
                elif node_name == "retrieval":
                    node_log["chunk_count"] = len(
                        node_state.get("reranked_chunks", [])
                    )
                    node_log["mcp_results"] = node_state.get("mcp_results", {})
                elif node_name == "analysis":
                    node_log["report_snippet"] = node_state.get(
                        "analysis_report", ""
                    )[:100]
                elif node_name == "reflection":
                    node_log["confidence"] = node_state.get("reflection_confidence")
                    node_log["critique"] = node_state.get("reflection_critique")
                elif node_name == "judge":
                    node_log["eval_scores"] = node_state.get("judge_eval_scores")

                yield f"data: {json.dumps(node_log)}\n\n"
                await asyncio.sleep(0.3)

        final_report = accumulated_state.get("analysis_report", "")
        selected_model = accumulated_state.get("selected_model", "gemini-1.5-flash")
        context_text = accumulated_state.get("context_text", "")
        
        # Add new interaction turn to Dual Memory Store & Firestore
        if final_report:
            dual_memory_mgr.add_turn(
                session_id=session_id, user_message=query, assistant_reply=final_report, user_id=user_id
            )

        # Compute Telemetry (Token Count, USD Cost, Latencies)
        telemetry = telemetry_engine.calculate_telemetry(
            model_name=selected_model,
            prompt_text=query + context_text,
            completion_text=final_report,
            node_latencies=node_latencies,
            is_cache_hit=accumulated_state.get("semantic_cache_hit", False),
        )

        # Persist assistant response directly into Firestore database
        assistant_msg_data = {
            "id": f"msg_{int(datetime.utcnow().timestamp()*1000)}",
            "role": "assistant",
            "content": final_report,
            "timestamp": datetime.utcnow().isoformat(),
            "citations": accumulated_state.get("citations", []),
            "evalScores": accumulated_state.get("judge_eval_scores", {}),
            "telemetry": telemetry,
            "nodeEvents": accumulated_state.get("node_execution_logs", []),
            "cacheHit": accumulated_state.get("semantic_cache_hit", False),
            "cacheType": accumulated_state.get("cache_type", "semantic_vector"),
            "memoryCompacted": mem_context.get("memory_compacted", False),
            "searchScope": search_scope,
        }
        firestore_db.save_chat_message(user_id, session_id, assistant_msg_data)

        # Final result event
        final_payload = {
            "event": "complete",
            "trace_id": trace_id,
            "report": final_report,
            "citations": accumulated_state.get("citations", []),
            "eval_scores": accumulated_state.get("judge_eval_scores", {}),
            "semantic_cache_hit": accumulated_state.get("semantic_cache_hit", False),
            "cache_type": accumulated_state.get("cache_type", "semantic_vector"),
            "memory_compacted": mem_context.get("memory_compacted", False),
            "long_term_summary": mem_context.get("long_term_summary", ""),
            "telemetry": telemetry,
            "guardrail_safe": accumulated_state.get("guardrail_status", {}).get(
                "safe", True
            ),
        }
        yield f"data: {json.dumps(final_payload)}\n\n"

    except Exception as e:
        logger.error(f"Error streaming graph execution: {e}")
        yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"





@router.post("/stream")
async def analyze_stream(req: AnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """Stream real-time agent execution events and analysis report using Server-Sent Events (SSE)."""
    session_id = req.session_id or f"session-{str(uuid.uuid4())[:8]}"
    search_scope = req.search_scope or "session"
    model_preference = req.model_preference or "auto"
    user_id = current_user["uid"]
    return StreamingResponse(
        stream_analysis_events(req.query, session_id, user_id, search_scope, model_preference),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
