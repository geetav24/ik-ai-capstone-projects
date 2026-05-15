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
from app.core.tools.registry import get_registry
from app.models.v2_models import FraudFinding
from app.workflows.state import LoanReviewState


async def fraud_detection_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads application + risk_assessment; writes fraud_finding.

    TODO — implement:

    1. Get the registry and call the fraud_signal_check tool:
           result = await registry.call("fraud_signal_check", {
               "loan_id":           app["loan_id"],
               "loan_amount":       float(app["loan_amount"]),
               "annual_income":     float(app["annual_income"]),
               "employment_status": app["employment_status"],
               "credit_score":      app["credit_score"],
           })

    2. Map result to FraudFinding:
           FraudFinding(
               signals=result["signals"],
               confidence=result["confidence"],
           )

    3. Return:
        {
            "fraud_finding": FraudFinding(...).model_dump(),
            "agent_trace": [TraceEntry(agent="fraud_detection", ...).model_dump()],
        }

    If fraud_finding is None in the final response (fraud agent didn't run),
    the UI should show "Fraud check: not required". That's intentional.
    """
    raise NotImplementedError("TODO: implement FraudDetectionAgent")
