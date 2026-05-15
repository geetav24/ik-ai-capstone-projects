"""
Tests for the tool registry and fraud_signal_check tool.
fraud_signal_check is deterministic (rule-based), so tests don't need mocking.

For loan_policy_search, document_required_lookup, loan_application_lookup,
submitted_documents_lookup — stub the async `call` method using pytest monkeypatch
or unittest.mock.AsyncMock so no real Pinecone / SQLite call is made.

Run with: pytest tests/test_tools.py -v
"""
import pytest
from app.core.tools.registry import get_registry, FraudSignalCheckTool


@pytest.mark.asyncio
async def test_fraud_tool_income_ratio_anomaly():
    """Ratio 7.5 should produce income_ratio_anomaly signal."""
    tool = FraudSignalCheckTool()
    result = await tool.call({
        "loan_id": "LN-003",
        "loan_amount": 300_000,
        "annual_income": 40_000,
        "employment_status": "self_employed",
        "credit_score": 640,
    })
    assert "income_ratio_anomaly" in result["signals"]
    assert result["confidence"] > 0


@pytest.mark.asyncio
async def test_fraud_tool_zero_income():
    tool = FraudSignalCheckTool()
    result = await tool.call({
        "loan_id": "LN-005",
        "loan_amount": 10_000,
        "annual_income": 0,
        "employment_status": "unemployed",
        "credit_score": 600,
    })
    assert "zero_income" in result["signals"]


@pytest.mark.asyncio
async def test_fraud_tool_clean_application_no_signals():
    """Low-risk application should return empty signals."""
    tool = FraudSignalCheckTool()
    result = await tool.call({
        "loan_id": "LN-001",
        "loan_amount": 15_000,
        "annual_income": 60_000,
        "employment_status": "employed",
        "credit_score": 720,
    })
    assert result["signals"] == []
    assert result["confidence"] == 0.0


def test_registry_has_all_five_tools():
    registry = get_registry()
    tools = {t["name"] for t in registry.list_tools()}
    expected = {
        "loan_policy_search",
        "fraud_signal_check",
        "document_required_lookup",
        "loan_application_lookup",
        "submitted_documents_lookup",
    }
    assert tools == expected
