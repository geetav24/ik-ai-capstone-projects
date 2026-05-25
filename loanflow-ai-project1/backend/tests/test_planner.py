"""
Tests for PlannerAgent routing logic.
No LLM calls — planner is pure rule-based logic.

Pattern: build a minimal state dict, call the agent, assert on the plan.
Once you implement planner_agent, these tests should pass as-is.

Run with: pytest tests/test_planner.py -v
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.agents.planner_agent import planner_agent, HIGH_LOAN_THRESHOLD, INCOME_RATIO_THRESHOLD


def _make_state(loan_amount, annual_income, employment_status="employed", loan_type="personal"):
    """Helper: builds a minimal LoanReviewState dict for planner tests."""
    return {
        "application": {
            "loan_id": "TEST",
            "borrower_name": "Test User",
            "loan_type": loan_type,
            "loan_amount": str(loan_amount),
            "annual_income": str(annual_income),
            "credit_score": 650,
            "employment_status": employment_status,
            "submitted_documents": [],
        },
        "raw_question": "What should the reviewer check?",
        "sanitized_input": {
            "question": "What should the reviewer check?",
            "redactions": [],
            "injection_signals": [],
        },
        "injection_signals": [],
        "plan": None,
        "retrieved_context": None,
        "doc_check_result": None,
        "risk_assessment": None,
        "fraud_finding": None,
        "reviewer_guidance": None,
        "guardrail_result": None,
        "agent_trace": [],
        "guardrails_applied": [],
        "evaluation": None,
    }


@pytest.mark.asyncio
async def test_low_risk_skips_fraud():
    """Small personal loan, good income — fraud should NOT run."""
    state = _make_state(loan_amount=15_000, annual_income=60_000)
    result = await planner_agent(state)
    plan = result["plan"]
    assert "fraud_detection" not in plan["specialists_to_run"]


@pytest.mark.asyncio
async def test_high_loan_amount_triggers_fraud():
    """Loan above threshold should trigger fraud detection."""
    state = _make_state(loan_amount=HIGH_LOAN_THRESHOLD + 1, annual_income=200_000)
    result = await planner_agent(state)
    assert "fraud_detection" in result["plan"]["specialists_to_run"]


@pytest.mark.asyncio
async def test_income_ratio_anomaly_triggers_fraud():
    """loan / income > 5 should trigger fraud detection."""
    state = _make_state(loan_amount=300_000, annual_income=40_000)  # ratio = 7.5
    result = await planner_agent(state)
    assert "fraud_detection" in result["plan"]["specialists_to_run"]


@pytest.mark.asyncio
async def test_zero_income_triggers_fraud():
    """Zero income is an automatic fraud signal."""
    state = _make_state(loan_amount=10_000, annual_income=0)
    result = await planner_agent(state)
    assert "fraud_detection" in result["plan"]["specialists_to_run"]


@pytest.mark.asyncio
async def test_self_employed_high_loan_triggers_fraud():
    state = _make_state(loan_amount=250_000, annual_income=100_000, employment_status="self_employed")
    result = await planner_agent(state)
    assert "fraud_detection" in result["plan"]["specialists_to_run"]
