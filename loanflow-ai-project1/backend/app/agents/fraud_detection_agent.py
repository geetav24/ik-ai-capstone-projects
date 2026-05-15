"""
FraudDetectionAgent — runs conditionally via MCP tool call.
"""
from datetime import datetime, timezone

from app.core.mcp.client import call_tool
from app.models.models import FraudFinding, TraceEntry
from app.workflows.state import LoanReviewState


async def fraud_detection_agent(state: LoanReviewState) -> dict:
    started = datetime.now(timezone.utc)
    app = state["application"]

    result = await call_tool("check_fraud_signals_tool", {
        "loan_amount":       float(app.get("loan_amount", 0)),
        "annual_income":     float(app.get("annual_income", 0)),
        "employment_status": app.get("employment_status", ""),
        "credit_score":      int(app.get("credit_score", 700)),
    })

    finding = FraudFinding(signals=result["signals"], confidence=result["confidence"])

    finished = datetime.now(timezone.utc)
    trace = TraceEntry(
        agent="fraud_detection",
        started_at=started,
        finished_at=finished,
        input_summary=f"loan_id={app.get('loan_id')}",
        output_summary=f"signals={result['signals']}, confidence={result['confidence']}",
    )

    return {
        "fraud_finding": finding.model_dump(),
        "agent_trace": [trace.model_dump()],
    }
