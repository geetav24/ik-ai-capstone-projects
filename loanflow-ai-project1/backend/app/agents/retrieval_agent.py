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
    # Defensive parsing: accept several shapes and provide clear diagnostics on failure.
    raw_content = None
    try:
        if not result:
            raw_content = None
        else:
            # run_with_tools returns a dict with a 'content' key (string)
            raw_content = result.get("content")
    except Exception:
        raw_content = None
    # The LLM's final answer is the retrieved chunks — no tool name reference needed.
    chunks_raw = []
    tool_errors = []
    # Inspect tool call diagnostics for common failure modes (missing creds, db errors)
    if isinstance(result, dict):
        for call in result.get("tool_calls_made", []) or []:
            res = str(call.get("result") if isinstance(call, dict) else call)
            if res and ("Missing credentials" in res or "Error executing tool" in res or "no such table" in res):
                tool_errors.append(res[:1000])

    if raw_content:
        try:
            chunks_raw = json.loads(raw_content)
            if not isinstance(chunks_raw, list):
                raise ValueError("expected a JSON array")
        except Exception as e:
            # Log full diagnostic to help prompt tuning / tool debugging
            logger.warning(
                "RetrievalAgent: failed to parse LLM/tool response as JSON chunks. Returning empty chunks. Raw response (truncated 500 chars): %s. Error: %s",
                (raw_content[:500] if isinstance(raw_content, str) else repr(raw_content)),
                str(e),
            )
            chunks_raw = []
    else:
        if tool_errors:
            logger.warning("RetrievalAgent: tool errors detected: %s", tool_errors)
        else:
            logger.warning(
                "RetrievalAgent: empty response from run_with_tools. Result object: %s",
                repr(result),
            )
        chunks_raw = []

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