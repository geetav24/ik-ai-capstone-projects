"""
DocumentCheckAgent — compares submitted docs against policy requirements.

v1 used a keyword hack: `if "bank" in question`. Don't do that.
v2 uses the document_required_lookup tool to get the actual required list
from policy, then does a set comparison against submitted docs.

No LLM call needed — this is pure set logic.
"""
from datetime import datetime, timezone
from app.core.tools.registry import get_registry
from app.models.v2_models import DocCheckResult, TraceEntry
from app.workflows.state import LoanReviewState


async def document_check_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads application + retrieved_context; writes doc_check_result.
    """
    started = datetime.now(timezone.utc)
    registry = get_registry()
    app = state["application"]
    
    # Step 1: Get required docs from tool
    result = await registry.call(
        "document_required_lookup",
        {"loan_type": app["loan_type"]}
    )
    required = set(result["required_documents"])
    
    # Step 2: Extract submitted doc types
    submitted = {doc["doc_type"] for doc in app.get("submitted_documents", [])}
    
    # Step 3: Compute missing and present
    missing = list(required - submitted)
    present = list(required & submitted)
    
    doc_check_result = DocCheckResult(
        missing=missing,
        present=present,
        required_by_policy=list(required),
    )
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="document_check",
        started_at=started,
        finished_at=finished,
        input_summary=f"loan_type={app.get('loan_type')}",
        output_summary=f"Missing: {missing}, Present: {present}",
    )
    
    return {
        "doc_check_result": doc_check_result.model_dump(),
        "agent_trace": [trace_entry.model_dump()],
    }
