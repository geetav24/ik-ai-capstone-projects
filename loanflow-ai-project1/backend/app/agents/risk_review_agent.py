"""
RiskReviewAgent — raises typed risk flags from application data + doc check result.

This agent replaces the v1 IncomeVerificationAgent concept:
income/loan ratio anomaly is detected HERE as a RiskFlag, not in a separate agent.

No LLM call needed. Pure rule-based flag generation.
The flags this agent produces feed directly into the PlannerAgent routing decision
(via the conditional edge function `should_run_fraud` in the workflow).
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.models.v2_models import RiskAssessment, RiskFlag, TraceEntry
from app.workflows.state import LoanReviewState


async def risk_review_agent(state: LoanReviewState) -> dict:
    """
    Rule-based risk reviewer (guidance-only implementation).

    Produces RiskFlag entries and an overall severity roll-up.
    """
    started_at = datetime.utcnow()

    application = state.get("application", {}) or {}
    doc_check = state.get("doc_check_result") or {}

    # Safely parse numeric fields (handles Decimal, str, int)
    def _to_decimal(v):
        try:
            if v is None:
                return Decimal(0)
            if isinstance(v, Decimal):
                return v
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return Decimal(0)

    loan_amount = _to_decimal(application.get("loan_amount"))
    annual_income = _to_decimal(application.get("annual_income"))
    credit_score = int(application.get("credit_score") or 0)
    submitted_documents = application.get("submitted_documents") or []

    missing_docs = doc_check.get("missing", []) if doc_check is not None else []

    flags: list[RiskFlag] = []

    # FLAG 1 — income_ratio_anomaly
    if annual_income > 0:
        ratio = loan_amount / annual_income
        if ratio > Decimal(5):
            flags.append(
                RiskFlag(
                    flag_type="income_ratio_anomaly",
                    severity="high",
                    detail=f"Ratio {float(ratio):.1f} exceeds threshold 5.0",
                )
            )

    # FLAG 2 — missing_income_evidence
    income_related = {"pay_stub", "bank_statement", "tax_return"}
    missing_income_docs = [d for d in missing_docs if d in income_related]
    if missing_income_docs:
        flags.append(
            RiskFlag(
                flag_type="missing_income_evidence",
                severity="medium",
                detail=f"Missing: {', '.join(missing_income_docs)}",
            )
        )

    # FLAG 3 — low_credit_score
    if credit_score < 600:
        flags.append(
            RiskFlag(
                flag_type="low_credit_score",
                severity="medium",
                detail=f"Score {credit_score} is below 600",
            )
        )

    # FLAG 4 — zero_income
    if annual_income == 0:
        flags.append(
            RiskFlag(
                flag_type="zero_income",
                severity="critical",
                detail="Annual income is zero",
            )
        )

    # FLAG 5 — no_documents_submitted
    if len(submitted_documents) == 0:
        flags.append(
            RiskFlag(
                flag_type="no_documents_submitted",
                severity="high",
                detail="No documents submitted with application",
            )
        )

    # Severity roll-up
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if flags:
        max_rank = max(severity_rank.get(f.severity, 0) for f in flags)
        overall = next(k for k, v in severity_rank.items() if v == max_rank)
    else:
        overall = "low"

    risk_assessment = RiskAssessment(flags=flags, severity=overall).model_dump()

    finished_at = datetime.utcnow()
    input_summary = (
        f"loan_amount={float(loan_amount):.2f};annual_income={float(annual_income):.2f};"
        f"credit_score={credit_score};missing_docs={len(missing_docs)};submitted_docs={len(submitted_documents)}"
    )
    output_summary = f"flags={len(flags)};severity={overall}"

    trace_entry = TraceEntry(
        agent="risk_review",
        started_at=started_at,
        finished_at=finished_at,
        input_summary=input_summary,
        output_summary=output_summary,
    ).model_dump()

    return {
        "risk_assessment": risk_assessment,
        "agent_trace": [trace_entry],
    }