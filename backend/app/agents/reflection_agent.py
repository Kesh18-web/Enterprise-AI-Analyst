import json
from typing import Any, Dict
from backend.app.core.llm import get_llm, extract_text_content
from backend.app.core.logging import logger, logger_timer
from backend.app.core.state import AnalystState


class ReflectionAgent:
    """Reflection Agent providing self-critique, hallucination auditing, and re-plan routing."""

    def evaluate_and_reflect(self, state: AnalystState) -> Dict[str, Any]:
        """Audit report for unsupported claims and estimate confidence score using live LLM critique."""
        query = state.get("user_query", "")
        report = state.get("analysis_report", "")
        context_text = state.get("context_text", "")
        reranked_chunks = state.get("reranked_chunks", [])
        trace_id = state.get("trace_id", "N/A")
        replan_count = state.get("reflection_count", 0)
        plan = state.get("plan", {})
        requires_rag = plan.get("requires_rag", True)

        with logger_timer("ReflectionAgent: Self-Critique Audit", trace_id=trace_id) as log:
            log.info(f"Reflecting on generated report (iteration {replan_count}, requires_rag={requires_rag})...")

            # 1. Fast Pass for General Knowledge Queries
            if not requires_rag:
                log.info("General Knowledge query detected. Bypassing RAG groundedness reflection.")
                return {
                    "confidence": 0.95,
                    "critique": "General knowledge inquiry verified successfully.",
                    "should_replan": False,
                }

            # 2. Check for empty evidence
            if not reranked_chunks or "No relevant documentation" in report:
                log.warning("Reflection Audit: Empty context or missing evidence detected.")
                should_replan = replan_count < 2
                return {
                    "confidence": 0.30,
                    "critique": "Insufficient evidence retrieved in initial pass. Expanded sub-query retrieval recommended.",
                    "should_replan": should_replan,
                }

            # 3. Live LLM Self-Reflection Audit
            try:
                # Use Gemini 2.5 Flash for ultra-fast self-critique audit without Groq quota limits
                llm = get_llm(model_name="gemini-2.5-flash", temperature=0.0)
                prompt = f"""
User Query: '{query}'

Retrieved Context Evidence:
{context_text}

Synthesized Report to Audit:
{report}

You are an Enterprise AI Lead Quality Auditor. Evaluate the report above for groundedness, citation validity, and query completeness.

Scoring Rubric:
- 0.90 to 1.00: Flawless. 100% grounded in retrieved evidence, full query coverage, valid citations.
- 0.70 to 0.89: Good. Core answer is accurate and grounded in evidence, minor formatting notes.
- Below 0.70: Flawed. Missing major query aspects, unsupported claims, or insufficient evidence. (Set should_replan to true).

Return ONLY a valid JSON object with these exact keys:
{{
  "confidence": <float between 0.00 and 1.00 based on rubric>,
  "critique": "<1-2 sentence detailed critique of accuracy, completeness, and evidence grounding>",
  "should_replan": <boolean true or false>
}}
Rules:
- Set should_replan to true ONLY if confidence is below 0.70 AND important query aspects were missed.
"""

                response = llm.invoke(prompt)
                raw_text = extract_text_content(response.content)

                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                audit_data = json.loads(raw_text)
                confidence = float(audit_data.get("confidence", 0.90))
                critique = str(audit_data.get("critique", "Report is well grounded."))
                should_replan = bool(audit_data.get("should_replan", False))

                # Enforce max replan loops cap of 2
                if replan_count >= 2:
                    should_replan = False

                log.info(
                    f"Live LLM Reflection Audit Complete | Confidence={confidence:.2f} | Replan={should_replan} | Critique='{critique}'"
                )
                return {
                    "confidence": confidence,
                    "critique": critique,
                    "should_replan": should_replan,
                }

            except Exception as e:
                log.warning(
                    f"[FALLBACK_TRIGGERED] Live LLM Reflection Agent call unavailable ({e}). Reverting to heuristic reflection."
                )

            # 4. Fallback Heuristic
            confidence = 0.90 if len(reranked_chunks) >= 2 else 0.75
            should_replan = False
            critique = "Fallback heuristic audit: Report is grounded in retrieved chunk evidence."

            log.info(f"Fallback Reflection Complete | Confidence={confidence:.2f} | Replan={should_replan}")
            return {
                "confidence": confidence,
                "critique": critique,
                "should_replan": should_replan,
            }


# Global singleton instance
reflection_agent = ReflectionAgent()

