import json
from typing import Any, Dict
from backend.app.core.llm import get_llm, extract_text_content
from backend.app.core.logging import logger, logger_timer
from backend.app.core.state import AnalystState
from backend.app.db.firestore import firestore_db


class JudgeAgent:
    """Judge Agent evaluating faithfulness, groundedness, completeness, and recording telemetry."""

    def evaluate_output(self, state: AnalystState) -> Dict[str, float]:
        """Compute LLM-as-a-Judge evaluation scores using reasoning model and persist to Firestore."""
        trace_id = state.get("trace_id", "N/A")
        user_id = state.get("user_id", "system")
        query = state.get("user_query", "")
        report = state.get("analysis_report", "")
        context_text = state.get("context_text", "")
        citations = state.get("citations", [])
        reranked_chunks = state.get("reranked_chunks", [])
        selected_model = state.get("selected_model", "gemini-2.5-flash")
        plan = state.get("plan", {})
        requires_rag = plan.get("requires_rag", True)

        with logger_timer("JudgeAgent: LLM-as-a-Judge Evaluation", trace_id=trace_id) as log:
            log.info(f"Computing LLM-as-a-Judge metrics for query: '{query}' (requires_rag={requires_rag})...")

            # 1. Live LLM-as-a-Judge Evaluation with Retry Loop
            import time
            for attempt in range(3):
                try:
                    judge_llm = get_llm(model_name="gemini-2.5-flash", temperature=0.0)
                    
                    if not requires_rag:
                        prompt = f"""
User Query: '{query}'

Synthesized Answer to Evaluate:
{report}

You are an Independent Lead AI Evaluation Auditor. Rate this answer across 2 quantitative metrics on a scale from 0.00 to 1.00:
1. "answer_relevance": Did the response directly answer what the user asked with accuracy and clarity?
2. "overall_quality": Comprehensive assessment of clarity, conciseness, and depth.

Return ONLY a valid JSON object with these exact keys:
{{
  "answer_relevance": <float 0.00-1.00>,
  "overall_quality": <float 0.00-1.00>
}}
"""
                    else:
                        prompt = f"""
User Query: '{query}'

Retrieved Evidence Context:
{context_text}

Synthesized Report to Evaluate:
{report}

Number of Footnote Citations Verified: {len(citations)}

You are an Independent Lead AI Evaluation Auditor. Rate the synthesized report across 3 quantitative metrics on a scale from 0.00 to 1.00:
1. "groundedness": Are all claims strictly supported by the context evidence? If claims are ungrounded or invented, rate between 0.00-0.40. If facts match context, rate 0.85-1.00.
2. "answer_relevance": Did the report directly answer what the user asked?
3. "citation_coverage": Are footnote citations present and valid for all retrieved facts?

Return ONLY a valid JSON object with these exact keys:
{{
  "groundedness": <float 0.00-1.00>,
  "answer_relevance": <float 0.00-1.00>,
  "citation_coverage": <float 0.00-1.00>,
  "overall_quality": <float 0.00-1.00>
}}
"""

                    response = judge_llm.invoke(prompt)
                    raw_text = extract_text_content(response.content)

                    if "```json" in raw_text:
                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_text:
                        raw_text = raw_text.split("```")[1].split("```")[0].strip()

                    judge_data = json.loads(raw_text)

                    if not requires_rag:
                        answer_relevance = round(float(judge_data.get("answer_relevance", 0.90)), 2)
                        overall_quality = round(float(judge_data.get("overall_quality", answer_relevance)), 2)
                        scores = {
                            "groundedness": 1.0,
                            "answer_relevance": answer_relevance,
                            "citation_coverage": 1.0,
                            "overall_quality": overall_quality,
                        }
                    else:
                        groundedness = round(float(judge_data.get("groundedness", 0.85)), 2)
                        answer_relevance = round(float(judge_data.get("answer_relevance", 0.85)), 2)
                        citation_coverage = round(float(judge_data.get("citation_coverage", 1.0 if citations else 0.0)), 2)
                        overall_quality = round(
                            float(judge_data.get("overall_quality", (groundedness * 0.4 + answer_relevance * 0.4 + citation_coverage * 0.2))),
                            2,
                        )
                        scores = {
                            "groundedness": groundedness,
                            "answer_relevance": answer_relevance,
                            "citation_coverage": citation_coverage,
                            "overall_quality": overall_quality,
                        }

                    log.info(
                        f"Live Judge Evaluation Scores | Overall={scores['overall_quality']} | Groundedness={scores['groundedness']} | Relevance={scores['answer_relevance']}"
                    )

                    eval_record = {
                        "trace_id": trace_id,
                        "query": query,
                        "scores": scores,
                        "model": selected_model,
                        "requires_rag": requires_rag,
                    }
                    firestore_db.save_document(
                        user_id=user_id or "system",
                        collection_name="evaluation_metrics",
                        doc_id=trace_id,
                        data=eval_record,
                    )
                    return scores

                except Exception as e:
                    if attempt < 2:
                        time.sleep(1.5)
                        continue
                    log.warning(
                        f"[FALLBACK_TRIGGERED] Live LLM-as-a-Judge call failed after 3 attempts ({e}). Executing dynamic text-overlap heuristic."
                    )

            # 2. Dynamic Text-Overlap Heuristic Judge (Zero hardcoded constant scores)
            if not context_text or not report:
                groundedness = 0.50 if not requires_rag else 0.10
                answer_relevance = 0.70
            else:
                context_words = set(context_text.lower().split())
                report_words = set(report.lower().split())
                overlap = len(context_words & report_words)
                union = len(context_words | report_words)
                jaccard = (overlap / union) if union > 0 else 0.0
                # Scale Jaccard overlap dynamically to 0.0-1.0 groundedness metric
                groundedness = round(min(1.0, jaccard * 3.5), 2)
                answer_relevance = round(min(1.0, 0.60 + jaccard * 2.0), 2)

            citation_coverage = 1.0 if citations else (1.0 if not requires_rag else 0.0)
            overall_quality = round(
                (groundedness * 0.4) + (answer_relevance * 0.4) + (citation_coverage * 0.2), 2
            )

            scores = {
                "groundedness": groundedness,
                "answer_relevance": answer_relevance,
                "citation_coverage": citation_coverage,
                "overall_quality": overall_quality,
            }

            log.info(f"Dynamic Heuristic Judge Scores | Overall={overall_quality} | Groundedness={groundedness}")

            eval_record = {
                "trace_id": trace_id,
                "query": query,
                "scores": scores,
                "model": selected_model,
                "requires_rag": requires_rag,
            }
            firestore_db.save_document(
                user_id=user_id or "system",
                collection_name="evaluation_metrics",
                doc_id=trace_id,
                data=eval_record,
            )
            return scores


# Global singleton instance
judge_agent = JudgeAgent()

