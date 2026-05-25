"""
StatusAgent — Specialist node that looks up a loan application by ID.

Responsibility:
  Use the loan_id_hint extracted by IntentRouterAgent to query the SQLite
  database and return structured loan application details.

  If no loan_id_hint is set, attempt to extract a loan ID from the
  sanitized message as a fallback.

Writes to state:
  loan_status        — LoanStatus dict if found, None if not found
  specialists_called — appends "status"
  agent_trace        — appends one AgentTraceEntry
"""
import re
from datetime import datetime, timezone

from app.models.models import AgentTraceEntry, InquiryState
from app.tools.loan_status_tool import get_loan_status

_LOAN_ID_RE = re.compile(r"\bLN-\d{3,}\b", re.IGNORECASE)


async def status_agent(state: InquiryState) -> dict:
    """
    LangGraph node. Reads state['loan_id_hint'] (or falls back to parsing
    state['sanitized_message']); writes loan_status and appends to
    specialists_called and agent_trace.
    """
    started = datetime.now(timezone.utc)

    loan_id = state.get("loan_id_hint")

    # Fallback: extract from message if router missed it
    if not loan_id:
        sanitized = state.get("sanitized_message", "")
        match = _LOAN_ID_RE.search(sanitized)
        loan_id = match.group(0).upper() if match else None

    loan_status_dict = None
    lookup_summary = "loan_id=None (not found in message)"

    if loan_id:
        result = await get_loan_status(loan_id)
        if result is not None:
            loan_status_dict = result.model_dump()
            lookup_summary = f"loan_id={loan_id}, status={result.status}"
        else:
            lookup_summary = f"loan_id={loan_id}, not_found=True"

    finished = datetime.now(timezone.utc)
    trace = AgentTraceEntry(
        agent="status",
        started_at=started,
        finished_at=finished,
        input_summary=f"loan_id_hint={state.get('loan_id_hint')}",
        output_summary=lookup_summary,
    )

    existing_trace = state.get("agent_trace") or []
    existing_called = state.get("specialists_called") or []
    return {
        "loan_status": loan_status_dict,
        "specialists_called": existing_called + ["status"],
        "agent_trace": existing_trace + [trace.model_dump()],
    }
