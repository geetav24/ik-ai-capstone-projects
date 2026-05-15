"""
Tests for tool functions and MCP wiring.

Unit tests   — call registry functions directly; no subprocess, no network.
               Run: pytest tests/test_tools.py -v -m "not integration"

Integration  — marked @pytest.mark.integration; spin up the real MCP server
               over SSE on a test port, connect via URL.
               Run: pytest tests/test_tools.py -v -m integration

Default `pytest` run includes both.
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.mcp.client import (
    call_tool,
    init_mcp_client,
    list_tools,
    shutdown_mcp_client,
)
from mcp_server.registry import check_fraud_signals

_MCP_ROOT = Path(__file__).resolve().parents[2] / "mcp-server"
_TEST_PORT = 8765


# ---------------------------------------------------------------------------
# Session fixture — starts the MCP server over SSE, connects via URL
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def mcp_session():
    # Start the server from its own directory — no PYTHONPATH needed
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.server"],
        cwd=str(_MCP_ROOT),
        env={**os.environ, "MCP_TRANSPORT": "sse", "MCP_PORT": str(_TEST_PORT)},
    )
    await asyncio.sleep(2.5)  # wait for uvicorn SSE server to bind

    os.environ["MCP_SERVER_URL"] = f"http://localhost:{_TEST_PORT}/sse"
    await init_mcp_client()
    yield
    try:
        await shutdown_mcp_client()
    except RuntimeError:
        pass
    proc.terminate()
    proc.wait()


# ---------------------------------------------------------------------------
# Unit tests — deterministic, no subprocess, never touch OpenAI or Pinecone
# ---------------------------------------------------------------------------

async def test_fraud_income_ratio_anomaly():
    result = await check_fraud_signals(
        loan_amount=300_000,
        annual_income=40_000,
        employment_status="self_employed",
        credit_score=640,
    )
    assert "income_ratio_anomaly" in result["signals"]
    assert result["confidence"] > 0


async def test_fraud_zero_income():
    result = await check_fraud_signals(loan_amount=10_000, annual_income=0)
    assert "zero_income" in result["signals"]


async def test_fraud_clean_application_no_signals():
    result = await check_fraud_signals(
        loan_amount=15_000,
        annual_income=60_000,
        employment_status="employed",
        credit_score=720,
    )
    assert result["signals"] == []
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Integration tests — require a live MCP server subprocess
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_mcp_client_lists_all_five_tools(mcp_session):
    tools = await list_tools()
    assert set(tools) == {
        "search_policy_tool",
        "extract_requirements_tool",
        "check_fraud_signals_tool",
        "get_loan_application_tool",
        "get_submitted_documents_tool",
    }


@pytest.mark.integration
async def test_mcp_call_tool_routes_correctly(mcp_session):
    """call_tool() sends over stdio MCP protocol and deserializes the response."""
    result = await call_tool(
        "check_fraud_signals_tool",
        {
            "loan_amount": 300_000,
            "annual_income": 40_000,
            "employment_status": "self_employed",
            "credit_score": 640,
        },
    )
    assert "signals" in result
    assert "confidence" in result


@pytest.mark.integration
async def test_mcp_result_matches_direct_registry_call(mcp_session):
    """For the deterministic fraud tool, MCP transport must produce the same result as a direct call."""
    kwargs = {
        "loan_amount": 300_000,
        "annual_income": 40_000,
        "employment_status": "self_employed",
        "credit_score": 640,
    }
    direct = await check_fraud_signals(**kwargs)
    via_mcp = await call_tool("check_fraud_signals_tool", kwargs)

    assert via_mcp["signals"] == direct["signals"]
    assert via_mcp["confidence"] == direct["confidence"]
