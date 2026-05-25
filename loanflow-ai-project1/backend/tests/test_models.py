"""
Smoke tests for Pydantic contracts.
No LLM calls, no DB — pure model validation.
Run with: pytest tests/test_models.py -v
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.models.models import (
    LoanApplication,
    LoanReviewRequest,
    SubmittedDocument,
    RiskFlag,
)


def test_loan_application_valid():
    app = LoanApplication(
        loan_id="LN-001",
        borrower_name="Alice",
        loan_type="personal",
        loan_amount=Decimal("15000"),
        annual_income=Decimal("60000"),
        credit_score=720,
        employment_status="employed",
        submitted_documents=[],
    )
    assert app.loan_id == "LN-001"
    assert app.credit_score == 720


def test_credit_score_out_of_range_raises():
    with pytest.raises(Exception):
        LoanApplication(
            loan_id="X",
            borrower_name="X",
            loan_type="personal",
            loan_amount=Decimal("1000"),
            annual_income=Decimal("50000"),
            credit_score=200,  # below 300 — should fail validation
            employment_status="employed",
        )


def test_question_max_length_enforced():
    with pytest.raises(Exception):
        LoanReviewRequest(
            application=LoanApplication(
                loan_id="X", borrower_name="X", loan_type="personal",
                loan_amount=Decimal("1000"), annual_income=Decimal("50000"),
                credit_score=700, employment_status="employed",
            ),
            question="x" * 2001,  # over 2000 char limit
        )


def test_risk_flag_severity_values():
    flag = RiskFlag(flag_type="low_credit_score", severity="medium", detail="score 550")
    assert flag.severity == "medium"
