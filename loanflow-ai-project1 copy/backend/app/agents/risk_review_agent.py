"""
RiskReviewAgent — raises typed risk flags from application data + doc check result.

This agent replaces the v1 IncomeVerificationAgent concept:
income/loan ratio anomaly is detected HERE as a RiskFlag, not in a separate agent.

No LLM call needed. Pure rule-based flag generation.
The flags this agent produces feed directly into the PlannerAgent routing decision
(via the conditional edge function `should_run_fraud` in the workflow).
"""
from app.models.v2_models import RiskAssessment, RiskFlag
from app.workflows.state import LoanReviewState


async def risk_review_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads application + doc_check_result; writes risk_assessment.

    TODO — implement the following checks. Each check that fires adds a RiskFlag.

    FLAG 1 — income_ratio_anomaly
        if annual_income > 0 and loan_amount / annual_income > 5:
            RiskFlag(flag_type="income_ratio_anomaly", severity="high",
                     detail=f"Ratio {ratio:.1f} exceeds threshold 5.0")

    FLAG 2 — missing_income_evidence
        if doc_check_result has missing docs AND any of them are income-related
        (pay_stub, bank_statement, tax_return):
            RiskFlag(flag_type="missing_income_evidence", severity="medium",
                     detail=f"Missing: {missing_income_docs}")

    FLAG 3 — low_credit_score
        if credit_score < 600:
            RiskFlag(flag_type="low_credit_score", severity="medium",
                     detail=f"Score {credit_score} is below 600")

    FLAG 4 — zero_income
        if annual_income == 0:
            RiskFlag(flag_type="zero_income", severity="critical",
                     detail="Annual income is zero")

    FLAG 5 — no_documents_submitted
        if len(submitted_documents) == 0:
            RiskFlag(flag_type="no_documents_submitted", severity="high",
                     detail="No documents submitted with application")

    Severity roll-up rule:
        overall severity = max severity across all flags
        (critical > high > medium > low)
        If no flags: severity = "low"

    Return:
        {
            "risk_assessment": RiskAssessment(flags=flags, severity=overall).model_dump(),
            "agent_trace": [TraceEntry(agent="risk_review", ...).model_dump()],
        }
    """
    raise NotImplementedError("TODO: implement RiskReviewAgent")
