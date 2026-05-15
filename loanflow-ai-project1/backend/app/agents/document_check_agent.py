"""
DocumentCheckAgent — LLM searches policy and extracts required docs.

Separation of duties:
    This agent  → defines the compliance task and output format
    LLM         → selects tools from descriptions, calls them, returns JSON answer
    tool_runner → executes whatever tools the LLM requests via MCP
    MCP server  → runs Pinecone search + AI requirement extraction

No tool names in this agent — zero coupling to the tool layer.
The LLM reads tool descriptions and decides what to call.
"""
import json
import logging
from datetime import datetime, timezone

from app.core.tool_runner import run_with_tools
from app.models.models import DocCheckResult, TraceEntry
from app.workflows.state import LoanReviewState

logger = logging.getLogger(__name__)

ALLOWED_DOC_TYPES = {
    "pay_stub",
    "bank_statement",
    "tax_return",
    "id",
    "employment_letter",
    "property_appraisal",
}


async def document_check_agent(state: LoanReviewState) -> dict:
    started = datetime.now(timezone.utc)
    app = state["application"]
    loan_type = app.get("loan_type", "personal")
    submitted_set = {doc["doc_type"] for doc in app.get("submitted_documents", [])}

    system_prompt = (
        "You are a document compliance assistant. Determine which document types "
        "are required for the given loan type. RETURN ONLY a JSON array of document "
        "type strings (from the allowed set). Example: [\"pay_stub\", \"id\"]"
    )
    user_prompt = (
        f"Loan type: {loan_type}\n"
        f"Submitted documents: {sorted(submitted_set)}\n\n"
        "Return a JSON array of required document types for this loan type."
    )

    result = await run_with_tools(system_prompt=system_prompt, user_prompt=user_prompt)

    raw_content = result.get("content") if isinstance(result, dict) else None
    required_raw = []
    if raw_content:
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, list):
                required_raw = parsed
            else:
                logger.warning(
                    "DocumentCheckAgent: LLM returned JSON but not a list. Raw: %s",
                    str(raw_content)[:500],
                )
                required_raw = []
        except Exception as e:
            logger.warning(
                "DocumentCheckAgent: failed to parse LLM response as JSON array. Error: %s Raw: %s",
                e,
                str(raw_content)[:500],
            )
            required_raw = []
    else:
        # If the tool layer failed (missing creds, DB error), try a conservative rule-based fallback
        logger.warning("DocumentCheckAgent: empty response from run_with_tools. Result: %s", repr(result))
        # Inspect tool call errors for diagnostics
        tool_errors = []
        if isinstance(result, dict):
            for call in result.get("tool_calls_made", []) or []:
                res = str(call.get("result") if isinstance(call, dict) else call)
                if res and ("Missing credentials" in res or "no such table" in res or "Error executing tool" in res):
                    tool_errors.append(res[:1000])
        if tool_errors:
            logger.warning("DocumentCheckAgent: detected tool errors: %s", tool_errors)

        # Conservative defaults by loan type
        lt = (loan_type or "").lower()
        if lt == "mortgage":
            required_raw = ["pay_stub", "bank_statement", "tax_return", "id", "property_appraisal"]
        elif lt == "auto":
            required_raw = ["pay_stub", "id", "bank_statement"]
        else:
            # personal/other
            required_raw = ["pay_stub", "id"]

    # Sanitize and filter allowed doc types
    required = []
    for item in required_raw:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate in ALLOWED_DOC_TYPES and candidate not in required:
            required.append(candidate)

    required_set = set(required)

    # Deterministic set comparison
    missing = sorted(required_set - submitted_set)
    present = sorted(required_set & submitted_set)

    doc_result = DocCheckResult(
        missing=missing,
        present=present,
        required_by_policy=sorted(required_set),
    )

    finished = datetime.now(timezone.utc)
    trace = TraceEntry(
        agent="document_check",
        started_at=started,
        finished_at=finished,
        input_summary=f"loan_type={loan_type}, submitted={sorted(submitted_set)}",
        output_summary=f"required={sorted(required_set)}, missing={missing}, present={present}",
    )

    return {
        "doc_check_result": doc_result.model_dump(),
        "agent_trace": [trace.model_dump()],
    }