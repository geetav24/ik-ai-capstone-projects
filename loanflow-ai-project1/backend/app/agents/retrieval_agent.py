"""
RetrievalAgent — LLM decides what to search and how to query the policy KB.

Separation of duties:
    This agent  → defines the task and output format
    LLM         → selects tools from descriptions, calls them, returns JSON answer
    tool_runner → executes whatever tools the LLM requests via MCP
    MCP server  → runs the actual Pinecone query

No tool names in this agent — zero coupling to the tool layer.
The LLM reads tool descriptions and decides what to call.
"""
import json
import logging
from datetime import datetime, timezone

from app.core.tool_runner import run_with_tools

logger = logging.getLogger(__name__)
from app.models.models import Citation, RetrievedContext, TraceEntry
from app.workflows.state import LoanReviewState


async def retrieval_agent(state: LoanReviewState) -> dict:
    started  = datetime.now(timezone.utc)
    app      = state["application"]
    question = state.get("sanitized_input", {}).get("question", "")

    # TODO: tune system prompt — describe the goal and quality bar for retrieval.
    #       Do NOT name tools — the LLM picks them from descriptions.
    system_prompt = (
        "You are a policy retrieval specialist for a loan review system. "
        "Find the most relevant policy sections for the given loan application and question. "
        "Return ONLY a JSON array of retrieved chunks: "
        '[{"filename": "...", "chunk_index": 0, "score": 0.9, "text": "..."}]'
    )

    # TODO: tune user prompt — experiment with how much application context
    #       to include. More context → better queries, higher token cost.
    user_prompt = (
        f"Loan application:\n{json.dumps(app, default=str)}\n\n"
        f"Reviewer question: {question}"
    )

    result = await run_with_tools(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    chunks_raw = []
    tool_errors = []

    if isinstance(result, dict):
        # --- Strategy 1: extract chunks directly from tool call results (most reliable)
        # gpt-4o-mini often writes natural language in `content` instead of JSON,
        # so we pull the raw Pinecone results from tool_calls_made directly.
        for call in result.get("tool_calls_made", []) or []:
            call_result = call.get("result") if isinstance(call, dict) else None
            # Check for tool errors first
            res_str = str(call_result)
            if res_str and ("Missing credentials" in res_str or "Error executing tool" in res_str or "no such table" in res_str):
                tool_errors.append(res_str[:1000])
                continue
            # search_policy_tool returns a list of chunk dicts directly
            if isinstance(call_result, list) and call_result:
                chunks_raw.extend(call_result)

        # --- Strategy 2: fall back to parsing LLM content as JSON (if tool result was empty)
        if not chunks_raw:
            raw_content = result.get("content", "")
            if raw_content:
                try:
                    stripped = raw_content.strip()
                    if stripped.startswith("```"):
                        stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        chunks_raw = parsed
                    else:
                        raise ValueError("expected JSON array")
                except Exception as e:
                    logger.warning(
                        "RetrievalAgent: JSON parse fallback failed. Raw (500 chars): %s. Error: %s",
                        raw_content[:500],
                        str(e),
                    )

    if tool_errors:
        logger.warning("RetrievalAgent: tool errors detected: %s", tool_errors)
    if not chunks_raw and not tool_errors:
        logger.warning(
            "RetrievalAgent: no chunks from tool calls or content. Result: %s",
            repr(result),
        )

    # Build Citation objects (be defensive about missing fields)
    citations = []
    for c in chunks_raw:
        if not isinstance(c, dict):
            continue
        try:
            citations.append(
                Citation(
                    filename=c.get("filename", "unknown"),
                    chunk_index=int(c.get("chunk_index", 0)),
                    score=float(c.get("score", 0.0)),
                    text=c.get("text", "") or "",
                )
            )
        except Exception:
            # Skip malformed chunk but continue processing others
            logger.debug("Skipping malformed retrieved chunk: %s", c)
            continue

    finished = datetime.now(timezone.utc)
    output_summary = f"retrieved {len(citations)} chunks"
    if tool_errors:
        output_summary += "; tool_errors=" + ";".join(tool_errors)

    trace = TraceEntry(
        agent="retrieval",
        started_at=started,
        finished_at=finished,
        input_summary=f"question length={len(question)}",
        output_summary=output_summary,
    )

    return {
        "retrieved_context": RetrievedContext(chunks=citations).model_dump(),
        "agent_trace": [trace.model_dump()],
    }