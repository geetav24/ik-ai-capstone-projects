"""
PlannerAgent — decides which specialists to run (USE_CASES.md §4).

This is a rule-based router, NOT an LLM call.
The routing logic is deterministic: inspect the loan application fields
and return a Plan that names which agents should run.

Why rule-based?
  LLM-based planning is in the "out of scope for v2" list.
  Rules are faster, cheaper, and easier to test.
  If rules become unwieldy in v3, switch to LLM planner then.
"""
from app.models.v2_models import LoanApplication, Plan
from app.workflows.state import LoanReviewState

# Routing thresholds — defined here so tests can import them directly
HIGH_LOAN_THRESHOLD = 500_000
INCOME_RATIO_THRESHOLD = 5.0


async def planner_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads state["application"]; writes state["plan"].

    TODO — implement routing rules (from USE_CASES.md §4):

    Always run (every request):
        Retrieval, DocumentCheck, RiskReview, Reviewer, OutputGuardrail, Evaluation

    Run FraudDetection if ANY of these conditions:
        1. loan_amount > HIGH_LOAN_THRESHOLD
        2. loan_amount / annual_income > INCOME_RATIO_THRESHOLD
           (guard against division by zero if annual_income == 0)
        3. employment_status == "self_employed" AND loan_amount > 200_000
        4. risk_flags includes "velocity_anomaly"
           (NOTE: RiskReview hasn't run yet at planning time — this flag
            is re-evaluated in the conditional edge after RiskReview.
            The planner just sets initial intent; the edge function has final say.)

    Build specialists_to_run as a list of agent names that will run:
        ["fraud_detection"] if fraud path, [] otherwise.
    Rationale should be a short human-readable string explaining the decision.

    Return:
        {
            "plan": Plan(
                specialists_to_run=["fraud_detection"],  # or []
                rationale="loan_amount / annual_income = 7.5 exceeds threshold 5.0",
            ).model_dump(),
            "agent_trace": [TraceEntry(agent="planner", ...).model_dump()],
        }

    Edge case: annual_income == 0 → treat ratio as infinity → run fraud.
    """
    raise NotImplementedError("TODO: implement PlannerAgent")
