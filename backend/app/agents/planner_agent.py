import json
from typing import Any, Dict
from backend.app.core.llm import get_llm
from backend.app.core.logging import logger, logger_timer
from backend.app.core.state import AnalystState


class PlannerAgent:
    """Planner Agent responsible for intent classification and sub-task decomposition."""

    def plan_analysis(self, state: AnalystState) -> Dict[str, Any]:
        """Deconstruct inquiry into sub-tasks, select primary_knowledge_source, and configure retrieval weights."""
        query = state.get("user_query", "")
        trace_id = state.get("trace_id", "N/A")
        replan_count = state.get("reflection_count", 0)
        critique = state.get("reflection_critique", "")

        with logger_timer("PlannerAgent: Task Decomposition", trace_id=trace_id) as log:
            log.info(f"Invoking Live LLM Planner for query: '{query}' (replan_count={replan_count})")

            # Build short-term memory string — used ONLY for pronoun/coreference resolution
            short_term_turns = state.get("short_term_turns", []) or []
            if short_term_turns:
                history_lines = []
                for turn in short_term_turns:
                    history_lines.append(f"User: {turn.get('user', '')}")
                    history_lines.append(f"Assistant: {turn.get('assistant', '')[:150]}")
                conversation_history_block = (
                    "[Prior Turn Context — use ONLY to resolve pronouns/references in the current query, NOT for classification reasoning]:\n"
                    + "\n".join(history_lines)
                    + "\n\n"
                )
            else:
                conversation_history_block = ""

            long_term_summary = state.get("long_term_summary", "")

            search_scope = state.get("search_scope", "session")

            # Construct system & user prompt for live LLM planning with 5-Source Taxonomy
            prompt = (
                f"{conversation_history_block}"
                f"User Inquiry: {query}\n"
                f"Search Scope Mode: {search_scope} (Global Workspace Knowledge active if 'global')\n"
                f"Long-Term Conversation Memory Summary: {long_term_summary if long_term_summary else 'None (New Conversation)'}\n"
                f"Re-plan Iteration: {replan_count}\n"
                f"Reflection Critique / Gap Notes: {critique if critique else 'None (Initial Pass)'}\n\n"
                "You are an Enterprise AI Lead Analyst. Deconstruct this inquiry into a structured JSON execution plan following these explicit rules:\n\n"
                "1. primary_knowledge_source Taxonomy:\n"
                "   Select exactly ONE primary_knowledge_source based on these first principles:\n"
                "   - 'ENTERPRISE_RAG': Select for internal company policies, uploaded documents, cover letters, candidate resumes (e.g. Keshav), work experience, Aurigo company info, contracts, internal project repos, or when Search Scope Mode is 'global'.\n"
                "   - 'PARAMETRIC_LLM': Select ONLY for pure general knowledge, definitions, static concepts, explanations, educational guides, biology, pure math, algorithms, programming syntax (e.g. 'what is EBITDA', 'how to bake bread').\n"
                "   - 'REALTIME_WEB_MCP': Select ONLY when correctness strictly depends on live, time-sensitive external data (e.g. current weather forecast, breaking news, today's stock price, current date, live events, or explicit web search requests).\n"
                "   - 'GITHUB_MCP': Select ONLY when the query specifically asks to inspect a remote GitHub repository, search issues, or audit GitHub code.\n\n"
                "2. search_mode & weight tuning:\n"
                "   - 'exact_keyword': Choose when the query contains exact section numbers, rule codes, or error IDs. Favor BM25 keyword search (bm25_weight=0.80, dense_weight=0.20).\n"
                "   - 'semantic_conceptual': Choose when the query asks for broad policy summaries, resume overviews, or high-level concepts (dense_weight=0.80, bm25_weight=0.20).\n"
                "   - 'hybrid_balanced': Choose for standard compliance inquiries (bm25_weight=0.50, dense_weight=0.50).\n\n"
                "3. sub_tasks:\n"
                "   - Break down the inquiry into 2-4 logical sub-tasks. Resolve any pronouns/references using the Prior Turn Context above.\n\n"
                "4. github_repo extraction:\n"
                "   - If the query contains a GitHub repository URL (e.g. 'https://github.com/owner/repo') or slug (e.g. 'owner/repo'), extract and populate 'github_repo' as 'owner/repo' (no protocol, no trailing slash).\n"
                "   - If no repository is mentioned, set 'github_repo' to null.\n\n"
                "Return ONLY a valid JSON object matching this schema:\n"
                "{\n"
                '  "primary_knowledge_source": "ENTERPRISE_RAG",\n'
                '  "requires_rag": true,\n'
                '  "requires_mcp": false,\n'
                '  "mcp_tools": [],\n'
                '  "github_repo": null,\n'
                '  "sub_tasks": ["Extract candidate name", "Retrieve resume chunks", "Synthesize findings"],\n'
                '  "search_mode": "hybrid_balanced",\n'
                '  "bm25_weight": 0.50,\n'
                '  "dense_weight": 0.50,\n'
                '  "top_k": 8\n'
                "}"
            )

            from backend.app.core.llm import extract_text_content
            import re

            for attempt in range(3):
                try:
                    # Use Groq Llama 70B for flagship intent classification & task decomposition
                    llm = get_llm(model_name="groq/llama-70b", temperature=0.0)
                    response = llm.invoke(prompt)
                    response_text = extract_text_content(response.content)

                    match = re.search(r"\{.*\}", response_text, re.DOTALL)
                    if match:
                        response_text = match.group(0)

                    plan = json.loads(response_text)

                    # Ensure deterministic mapping from primary_knowledge_source
                    source = plan.get("primary_knowledge_source", "ENTERPRISE_RAG" if search_scope == "global" else "PARAMETRIC_LLM")
                    if source == "PARAMETRIC_LLM":
                        plan["requires_rag"] = False
                        plan["requires_mcp"] = False
                        plan["mcp_tools"] = []
                    elif source == "ENTERPRISE_RAG":
                        plan["requires_rag"] = True
                        plan["requires_mcp"] = False
                        plan["mcp_tools"] = []
                    elif source == "REALTIME_WEB_MCP":
                        plan["requires_rag"] = False
                        plan["requires_mcp"] = True
                        plan["mcp_tools"] = ["browser_search"]
                    elif source == "GITHUB_MCP":
                        plan["requires_rag"] = False
                        plan["requires_mcp"] = True
                        plan["mcp_tools"] = ["github_commits", "github_code_search", "github_issues_search"]

                    log.info(
                        f"Live LLM Plan Generated successfully (source={source}, {len(plan.get('sub_tasks', []))} sub-tasks, mode={plan.get('search_mode')})"
                    )
                    return plan

                except Exception as e:
                    if attempt < 2:
                        log.warning(f"Live LLM Planner attempt {attempt+1} failed ({e}). Retrying...")
                        continue

                    # If search_scope is global OR query looks like document inquiry, default fallback to ENTERPRISE_RAG!
                    fallback_source = "ENTERPRISE_RAG" if search_scope == "global" or any(w in query.lower() for w in ["keshav", "aurigo", "experience", "resume", "cover", "letter", "apply", "job", "policy", "document"]) else "PARAMETRIC_LLM"
                    log.warning(f"Live LLM Planner failed after 3 attempts ({e}). Defaulting to {fallback_source} fallback.")
                    return {
                        "primary_knowledge_source": fallback_source,
                        "requires_rag": (fallback_source == "ENTERPRISE_RAG"),
                        "requires_mcp": False,
                        "mcp_tools": [],
                        "sub_tasks": [f"Search evidence for: {query}", "Synthesize response"],
                        "search_mode": "hybrid_balanced",
                        "bm25_weight": 0.5,
                        "dense_weight": 0.5,
                        "top_k": 8,
                    }


# Global singleton instance
planner_agent = PlannerAgent()
