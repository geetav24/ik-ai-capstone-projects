"""
PlannerAgent — decides which specialists to run (USE_CASES.md §4).

This is a rule-based router, NOT an LLM call.
The routing logic is deterministic: inspect the loan application fields
and return a Plan that names which agents should run.

Why rule-based?
  LLM-based planning is in the "out of scope" list.
  Rules are faster, cheaper, and easier to test.
  If rules become unwieldy in v3, switch to LLM planner then.
"""
from datetime import datetime, timezone
from app.models.models import LoanApplication, Plan, TraceEntry
from app.workflows.state import LoanReviewState

# Routing thresholds — defined here so tests can import them directly
HIGH_LOAN_THRESHOLD = 500_000
INCOME_RATIO_THRESHOLD = 5.0


async def planner_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads state["application"]; writes state["plan"].
    """
    started = datetime.now(timezone.utc)
    app = state["application"]
    
    # Determine if fraud detection should run
    specialists_to_run = []
    rationale = ""

    # Decimal fields arrive as strings after model_dump() — normalise upfront
    loan_amount = float(app.get("loan_amount") or 0)
    annual_income = float(app.get("annual_income") or 0)

    # Rule 1: loan_amount > HIGH_LOAN_THRESHOLD
    if loan_amount > HIGH_LOAN_THRESHOLD:
        specialists_to_run.append("fraud_detection")
        rationale = f"loan_amount {loan_amount} exceeds threshold {HIGH_LOAN_THRESHOLD}"
    
    if annual_income == 0:
        # Edge case: zero income → treat ratio as infinity
        specialists_to_run.append("fraud_detection")
        rationale = "annual_income is zero (edge case)"
    elif annual_income > 0:
        ratio = loan_amount / annual_income
        if ratio > INCOME_RATIO_THRESHOLD:
            if "fraud_detection" not in specialists_to_run:
                specialists_to_run.append("fraud_detection")
                rationale = f"loan_amount / annual_income = {ratio:.2f} exceeds threshold {INCOME_RATIO_THRESHOLD}"
    
    # Rule 3: self_employed_high_loan
    employment_status = app.get("employment_status", "")
    if employment_status == "self_employed" and loan_amount > 200_000:
        if "fraud_detection" not in specialists_to_run:
            specialists_to_run.append("fraud_detection")
            rationale = "self_employed with high loan amount (> 200,000)"
    
    # Remove duplicates while preserving order
    specialists_to_run = list(dict.fromkeys(specialists_to_run))
    
    plan = Plan(
        specialists_to_run=specialists_to_run,
        rationale=rationale or "Standard review path",
    )
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="planner",
        started_at=started,
        finished_at=finished,
        input_summary=f"loan_id={app.get('loan_id')}",
        output_summary=f"Plan: {specialists_to_run}",
    )
    
    return {
        "plan": plan.model_dump(),
        "agent_trace": [trace_entry.model_dump()],
    }
