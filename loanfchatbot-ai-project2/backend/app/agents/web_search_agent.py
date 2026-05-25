"""
WebSearchAgent — Specialist node that searches the web for external information.

Responsibility:
  Handle questions that require real-world context beyond the internal policy
  KB: where to obtain documents, government agency contacts, general financial
  literacy, rate comparisons, etc.

Writes to state:
  web_results        — list of WebResult dicts (title, url, content)
  specialists_called — appends "web"
  agent_trace        — appends one AgentTraceEntry
"""
from datetime import datetime, timezone

from app.models.models import AgentTraceEntry, InquiryState
from app.tools.web_search_tool import web_search


async def web_search_agent(state: InquiryState) -> dict:
    """
    LangGraph node. Reads state['sanitized_message']; writes web_results
    and appends to specialists_called and agent_trace.

    Note: Tavily's sync client is wrapped in run_in_executor inside
    web_search_tool.py — this node can safely await it.
    """
    started = datetime.now(timezone.utc)
    sanitized = state.get("sanitized_message", "")

    # TODO: derive a cleaner search query from the sanitized message.
    #       Stripping the delimiters is the minimum; a better approach is to
    #       ask the LLM to rephrase the question as a web search query.
    query = sanitized.replace("<<<USER_MESSAGE>>>", "").replace("<<<END_USER_MESSAGE>>>", "").strip()

    # TODO: tune max_results — 3 is enough for most questions; increase for
    #       research-style queries where the user needs multiple sources.
    results = await web_search(query=query, max_results=3)
    result_dicts = [r.model_dump() for r in results]

    finished = datetime.now(timezone.utc)
    trace = AgentTraceEntry(
        agent="web_search",
        started_at=started,
        finished_at=finished,
        input_summary=f"query_length={len(query)}",
        output_summary=f"results={len(result_dicts)}",
    )

    existing_trace = state.get("agent_trace") or []
    existing_called = state.get("specialists_called") or []
    return {
        "web_results": result_dicts,
        "specialists_called": existing_called + ["web"],
        "agent_trace": existing_trace + [trace.model_dump()],
    }
