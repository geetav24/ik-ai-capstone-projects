"""Tests for tool implementations — mock external services."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_search_policy_returns_chunks():
    mock_openai = AsyncMock()
    mock_openai.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 1536)]
    )
    mock_index = MagicMock()
    mock_index.query.return_value = {
        "matches": [
            {"score": 0.92, "metadata": {"filename": "loan_policy.pdf", "chunk_index": 2, "text": "DTI must not exceed 43%."}}
        ]
    }
    with patch("app.tools.policy_tool._get_openai", return_value=mock_openai), \
         patch("app.tools.policy_tool._get_index", return_value=mock_index):
        from app.tools.policy_tool import search_policy
        results = await search_policy("personal loan documents", top_k=1)
    assert len(results) == 1
    assert results[0].score == 0.92
    assert "DTI" in results[0].text


@pytest.mark.asyncio
async def test_get_loan_status_returns_loan(tmp_path):
    import sqlite3
    db = tmp_path / "loanflow.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE loan_applications "
        "(loan_id TEXT, borrower_name TEXT, loan_type TEXT, loan_amount REAL, "
        "status TEXT, credit_score INTEGER, annual_income REAL, employment_status TEXT)"
    )
    conn.execute(
        "INSERT INTO loan_applications VALUES (?,?,?,?,?,?,?,?)",
        ("LN-001", "Alice Smith", "personal", 10000.0, "under_review", 720, 80000.0, "employed"),
    )
    conn.commit()
    conn.close()

    with patch("app.tools.loan_status_tool._db_path", return_value=str(db)):
        from app.tools.loan_status_tool import get_loan_status
        loan = await get_loan_status("LN-001")
    assert loan is not None
    assert loan.borrower_name == "Alice Smith"
    assert loan.credit_score == 720


@pytest.mark.asyncio
async def test_get_loan_status_not_found(tmp_path):
    import sqlite3
    db = tmp_path / "loanflow.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE loan_applications "
        "(loan_id TEXT, borrower_name TEXT, loan_type TEXT, loan_amount REAL, "
        "status TEXT, credit_score INTEGER, annual_income REAL, employment_status TEXT)"
    )
    conn.commit()
    conn.close()

    with patch("app.tools.loan_status_tool._db_path", return_value=str(db)):
        from app.tools.loan_status_tool import get_loan_status
        result = await get_loan_status("LN-999")
    assert result is None


@pytest.mark.asyncio
async def test_web_search_returns_results():
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "IRS Tax Return", "url": "https://irs.gov", "content": "Get your tax transcript here."}
        ]
    }
    with patch("app.tools.web_search_tool._get_client", return_value=mock_client):
        from app.tools.web_search_tool import web_search
        results = await web_search("how to get tax return", max_results=1)
    assert len(results) == 1
    assert results[0].url == "https://irs.gov"
