"""
FraudDetectionAgent — runs conditionally based on PlannerAgent + RiskReview output.

This agent calls the fraud_signal_check tool and returns a FraudFinding.
It only runs when the conditional edge in the workflow routes to it.

A note on conditional routing:
  The PlannerAgent makes an initial call (before RiskReview data exists).
  The `should_run_fraud` edge function makes the FINAL routing decision
  after RiskReview flags are available. This agent only runs if that
  edge function returns "fraud_detection".
"""
from datetime import datetime, timezone
from app.core.tools.registry import get_registry
from app.models.v2_models import FraudFinding, TraceEntry
from app.workflows.state import LoanReviewState


async def fraud_detection_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads application + risk_assessment; writes fraud_finding.
    """
    started = datetime.now(timezone.utc)
    registry = get_registry()
    app = state["application"]
    
    # Call the fraud_signal_check tool
    result = await registry.call("fraud_signal_check", {
        "loan_id":           app.get("loan_id", ""),
        "loan_amount":       float(app.get("loan_amount", 0)),
        "annual_income":     float(app.get("annual_income", 0)),
        "employment_status": app.get("employment_status", ""),
        "credit_score":      app.get("credit_score", 700),
    })
    
    # Map result to FraudFinding
    fraud_finding = FraudFinding(
        signals=result.get("signals", []),
        confidence=result.get("confidence", 0.0),
    )
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="fraud_detection",
        started_at=started,
        finished_at=finished,
        input_summary=f"loan_id={app.get('loan_id')}",
        output_summary=f"Signals: {fraud_finding.signals}, Confidence: {fraud_finding.confidence:.2f}",
    )
    
    return {
        "fraud_finding": fraud_finding.model_dump(),
        "agent_trace": [trace_entry.model_dump()],
    }
