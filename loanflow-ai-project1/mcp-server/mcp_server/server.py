"""
LoanFlow MCP Server — standalone tool layer.

Run locally (stdio, for dev):
    cd backend
    python -m mcp_server.server

Run as HTTP service (SSE, for prod):
    MCP_TRANSPORT=sse MCP_PORT=8001 python -m mcp_server.server

All tool implementations live in registry.py.
This file only wires them to the MCP protocol.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")

from mcp.server.fastmcp import FastMCP

from mcp_server.registry import (
    check_fraud_signals,
    extract_requirements,
    get_loan_application,
    get_submitted_documents,
    search_policy,
)

mcp = FastMCP(
    name="loanflow-tools",
    instructions=(
        "You are the LoanFlow tool server. "
        "Provide accurate data from the policy knowledge base and loan database. "
        "Never fabricate information — return only what the underlying data sources contain."
    ),
)


@mcp.tool()
async def search_policy_tool(query: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search over the company's loan policy knowledge base.

    The policy document is the single source of truth — always search
    before making compliance or document-requirement decisions.

    Args:
        query:  Natural language search query
        top_k:  Number of chunks to return (default 5)

    Returns:
        List of chunks: [{filename, chunk_index, score, text}, ...]
    """
    return await search_policy(query, top_k)


@mcp.tool()
async def extract_requirements_tool(loan_type: str, policy_chunks: list[dict]) -> list[str]:
    """
    Use AI to extract required document types from policy chunks.

    Call search_policy_tool first, then pass results here.
    No hardcoded rules — the policy text drives the answer.

    Args:
        loan_type:     One of: personal, mortgage, auto, business
        policy_chunks: Chunks returned by search_policy_tool

    Returns:
        List of required doc types: ["pay_stub", "bank_statement", ...]
    """
    return await extract_requirements(loan_type, policy_chunks)


@mcp.tool()
async def check_fraud_signals_tool(
    loan_amount: float,
    annual_income: float,
    employment_status: str = "",
    credit_score: int = 700,
) -> dict:
    """
    Deterministic fraud signal detection using bank risk thresholds.

    Signals: income_ratio_anomaly, zero_income, low_credit_high_amount,
             self_employed_high_loan.

    Returns:
        {signals: [...], confidence: 0.0–0.9}
    """
    return await check_fraud_signals(
        loan_amount=loan_amount,
        annual_income=annual_income,
        employment_status=employment_status,
        credit_score=credit_score,
    )


@mcp.tool()
async def get_loan_application_tool(loan_id: str) -> dict:
    """
    Fetch a stored loan application from the database.

    Args:
        loan_id: Primary key, e.g. "LN-001"
    """
    return await get_loan_application(loan_id)


@mcp.tool()
async def get_submitted_documents_tool(loan_id: str) -> list[dict]:
    """
    Fetch all documents submitted for a loan application.

    Args:
        loan_id: The loan application ID

    Returns:
        List of {doc_type, uploaded_at}. Empty list if none submitted.
    """
    return await get_submitted_documents(loan_id)


if __name__ == "__main__":
    import os
    from mcp.server.fastmcp import FastMCP as _FastMCP

    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "sse":
        # host/port must be passed to the FastMCP constructor, not run()
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8001"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")
    else:
        mcp.run()
