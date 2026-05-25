"""
Tests for refactored agents: retrieval_agent and document_check_agent.

All tests mock run_with_tools — no real OpenAI or MCP server.
Both agents read from result["content"] as JSON — no tool names in agent code.
The agents' jobs are:
  - retrieval_agent:       parse Citation objects from LLM's JSON answer
  - document_check_agent:  do deterministic set comparison (missing vs present)

Patch target must be the name in the agent's own module, not the source module.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.models import LoanApplication, SubmittedDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _retrieval_fake(chunks: list[dict]) -> dict:
    """Fake run_with_tools result where LLM returns chunks as JSON in content."""
    return {"content": json.dumps(chunks), "tool_calls_made": []}


def _app_with_docs(*doc_types) -> dict:
    app = LoanApplication(
        loan_id="LN-T",
        borrower_name="Test User",
        loan_type="personal",
        loan_amount=Decimal("10000"),
        annual_income=Decimal("50000"),
        credit_score=700,
        employment_status="employed",
        submitted_documents=[
            SubmittedDocument(doc_type=dt, uploaded_at=datetime.now(timezone.utc))
            for dt in doc_types
        ],
    )
    return app.model_dump()


# ---------------------------------------------------------------------------
# retrieval_agent
# ---------------------------------------------------------------------------

async def test_retrieval_agent_builds_citations_from_llm_answer(low_risk_application):
    """LLM returns chunks as JSON in content → Citation objects built correctly."""
    state = {
        "application": low_risk_application,
        "sanitized_input": {"question": "What documents are required?"},
    }
    chunks = [
        {"filename": "policy.pdf", "chunk_index": 0, "score": 0.92, "text": "Personal loans need pay_stub."},
        {"filename": "policy.pdf", "chunk_index": 1, "score": 0.85, "text": "All loans require ID."},
    ]
    fake = _retrieval_fake(chunks)

    with patch("app.agents.retrieval_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.retrieval_agent import retrieval_agent
        output = await retrieval_agent(state)

    assert "retrieved_context" in output
    result_chunks = output["retrieved_context"]["chunks"]
    assert len(result_chunks) == 2
    assert result_chunks[0]["filename"] == "policy.pdf"
    assert result_chunks[0]["score"] == 0.92
    assert result_chunks[1]["chunk_index"] == 1


async def test_retrieval_agent_empty_chunks_gives_empty_citations():
    """LLM returns empty array → empty citations list, output shape intact."""
    state = {
        "application": {"loan_id": "LN-001", "loan_type": "personal"},
        "sanitized_input": {"question": "anything"},
    }
    fake = _retrieval_fake([])

    with patch("app.agents.retrieval_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.retrieval_agent import retrieval_agent
        output = await retrieval_agent(state)

    assert output["retrieved_context"]["chunks"] == []


async def test_retrieval_agent_missing_question_key_does_not_crash():
    """sanitized_input without 'question' → empty string, agent runs fine."""
    state = {
        "application": {"loan_id": "LN-001"},
        "sanitized_input": {},
    }
    fake = _retrieval_fake([])

    with patch("app.agents.retrieval_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.retrieval_agent import retrieval_agent
        output = await retrieval_agent(state)

    assert "retrieved_context" in output


async def test_retrieval_agent_raises_on_non_json_llm_response():
    """LLM returning plain text instead of JSON is a prompt bug — raise RuntimeError."""
    state = {
        "application": {"loan_id": "LN-001"},
        "sanitized_input": {"question": "q"},
    }
    fake = {"content": "Here are the relevant sections...", "tool_calls_made": []}

    with patch("app.agents.retrieval_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.retrieval_agent import retrieval_agent
        with pytest.raises(RuntimeError, match="valid JSON chunks"):
            await retrieval_agent(state)


async def test_retrieval_agent_trace_entry_present():
    """Exactly one trace entry with agent='retrieval' and timing fields."""
    state = {
        "application": {"loan_id": "LN-001"},
        "sanitized_input": {"question": "q"},
    }
    fake = _retrieval_fake([])

    with patch("app.agents.retrieval_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.retrieval_agent import retrieval_agent
        output = await retrieval_agent(state)

    assert len(output["agent_trace"]) == 1
    trace = output["agent_trace"][0]
    assert trace["agent"] == "retrieval"
    assert "started_at" in trace
    assert "finished_at" in trace


# ---------------------------------------------------------------------------
# document_check_agent — set comparison logic
# ---------------------------------------------------------------------------

def _doc_fake(required: list[str]) -> dict:
    """Build a fake run_with_tools result where the LLM returns required docs as JSON."""
    import json
    return {"content": json.dumps(required), "tool_calls_made": []}


async def test_doc_check_all_required_docs_present(low_risk_application):
    """All required docs submitted → missing is empty."""
    state = {"application": low_risk_application}  # has pay_stub, bank_statement, id
    fake = _doc_fake(["pay_stub", "bank_statement", "id"])

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        output = await document_check_agent(state)

    result = output["doc_check_result"]
    assert result["missing"] == []
    assert sorted(result["present"]) == ["bank_statement", "id", "pay_stub"]
    assert sorted(result["required_by_policy"]) == ["bank_statement", "id", "pay_stub"]


async def test_doc_check_no_docs_submitted_all_missing(high_risk_application):
    """No docs submitted → all required docs appear in missing."""
    state = {"application": high_risk_application}  # submitted_documents=[]
    fake = _doc_fake(["pay_stub", "bank_statement", "id", "tax_return"])

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        output = await document_check_agent(state)

    result = output["doc_check_result"]
    assert sorted(result["missing"]) == ["bank_statement", "id", "pay_stub", "tax_return"]
    assert result["present"] == []


async def test_doc_check_partial_submission_splits_correctly():
    """Partial submission: submitted docs split into present and missing."""
    state = {"application": _app_with_docs("pay_stub")}
    fake = _doc_fake(["pay_stub", "id", "bank_statement"])

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        output = await document_check_agent(state)

    result = output["doc_check_result"]
    assert result["missing"] == ["bank_statement", "id"]
    assert result["present"] == ["pay_stub"]


async def test_doc_check_extra_submitted_docs_not_counted_as_required():
    """Docs submitted that aren't required don't inflate present or required_by_policy."""
    state = {"application": _app_with_docs("pay_stub", "id", "employment_letter")}
    fake = _doc_fake(["pay_stub", "id"])

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        output = await document_check_agent(state)

    result = output["doc_check_result"]
    assert result["missing"] == []
    assert sorted(result["present"]) == ["id", "pay_stub"]  # employment_letter excluded
    assert sorted(result["required_by_policy"]) == ["id", "pay_stub"]


async def test_doc_check_raises_on_non_json_llm_response():
    """LLM returning plain text instead of JSON is a prompt bug — raise RuntimeError."""
    state = {"application": _app_with_docs("id")}
    fake = {"content": "You need pay_stub and id.", "tool_calls_made": []}

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        with pytest.raises(RuntimeError, match="valid JSON array"):
            await document_check_agent(state)


async def test_doc_check_raises_when_llm_returns_json_object_not_array():
    """LLM returning a JSON object instead of an array is a prompt bug — raise RuntimeError."""
    import json
    state = {"application": _app_with_docs("id")}
    fake = {"content": json.dumps({"required": ["id"]}), "tool_calls_made": []}

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        with pytest.raises(RuntimeError, match="valid JSON array"):
            await document_check_agent(state)


async def test_doc_check_results_are_sorted():
    """missing and present lists are always sorted alphabetically."""
    state = {"application": _app_with_docs("tax_return", "id")}
    fake = _doc_fake(["pay_stub", "id", "bank_statement", "tax_return"])

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        output = await document_check_agent(state)

    result = output["doc_check_result"]
    assert result["missing"] == sorted(result["missing"])
    assert result["present"] == sorted(result["present"])


async def test_doc_check_trace_entry_metadata():
    """Trace entry carries agent name and timing."""
    state = {"application": _app_with_docs("id")}
    fake = _doc_fake(["id"])

    with patch("app.agents.document_check_agent.run_with_tools", AsyncMock(return_value=fake)):
        from app.agents.document_check_agent import document_check_agent
        output = await document_check_agent(state)

    assert len(output["agent_trace"]) == 1
    trace = output["agent_trace"][0]
    assert trace["agent"] == "document_check"
    assert "started_at" in trace
    assert "finished_at" in trace
