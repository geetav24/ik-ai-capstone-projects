"""
Tests for tool_runner.py — the LLM tool-calling loop.

Unit tests only — no real OpenAI, no real MCP server.
Mocks at the boundary: _client.chat.completions.create and call_tool.

Schema cache is pre-populated via an autouse fixture so _get_openai_tools
never tries to reach the MCP server.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.tool_runner import find_tool_result, run_with_tools


# ---------------------------------------------------------------------------
# Helpers — build mock OpenAI response objects
# ---------------------------------------------------------------------------

def _tool_call(call_id: str, name: str, args: dict):
    """Build a mock ToolCall as returned by the OpenAI SDK."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _response(content: str | None = None, tool_calls=None):
    """Build a mock ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls  # None → LLM done; list → tool call turn

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Autouse fixture — inject fake schema cache, no MCP call needed
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fake_schema_cache(monkeypatch):
    """Pre-populate the module-level schema cache so tests never hit MCP."""
    fake = [
        {
            "name": "search_policy_tool",
            "description": "Semantic search over loan policy KB.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
                "required": ["query"],
            },
        },
        {
            "name": "extract_requirements_tool",
            "description": "Extract required doc types from policy chunks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_type": {"type": "string"},
                    "policy_chunks": {"type": "array"},
                },
                "required": ["loan_type", "policy_chunks"],
            },
        },
        {
            "name": "check_fraud_signals_tool",
            "description": "Deterministic fraud signal detection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_amount": {"type": "number"},
                    "annual_income": {"type": "number"},
                },
                "required": ["loan_amount", "annual_income"],
            },
        },
    ]
    import app.core.tool_runner as tr
    monkeypatch.setattr(tr, "_schema_cache", fake)


# ---------------------------------------------------------------------------
# run_with_tools — core loop behaviour
# ---------------------------------------------------------------------------

async def test_no_tool_calls_returns_content_immediately():
    """LLM answers on the first turn — loop runs exactly once."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_response(content="Final answer", tool_calls=None)
    )
    with patch("app.core.tool_runner._get_client", return_value=mock_client):
        result = await run_with_tools(
            system_prompt="You are a test agent.",
            user_prompt="What is 2+2?",
        )

    assert result["content"] == "Final answer"
    assert result["tool_calls_made"] == []
    mock_client.chat.completions.create.assert_called_once()


async def test_single_tool_call_then_final_answer():
    """LLM calls one tool, receives result, then returns final text."""
    chunks = [{"filename": "policy.pdf", "chunk_index": 0, "score": 0.9, "text": "..."}]
    tc = _tool_call("tc-1", "search_policy_tool", {"query": "personal loan docs"})

    responses = [
        _response(content=None, tool_calls=[tc]),
        _response(content="Done searching.", tool_calls=None),
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=responses)
    with patch("app.core.tool_runner._get_client", return_value=mock_client), \
         patch("app.core.tool_runner.call_tool", AsyncMock(return_value=chunks)):
        result = await run_with_tools(
            system_prompt="Find policy sections.",
            user_prompt="What docs are needed?",
            allowed_tools=["search_policy_tool"],
        )

    assert result["content"] == "Done searching."
    assert len(result["tool_calls_made"]) == 1
    call = result["tool_calls_made"][0]
    assert call["name"] == "search_policy_tool"
    assert call["result"] == chunks


async def test_two_sequential_tool_calls():
    """LLM calls search then extract — the two-turn doc-check chain."""
    chunks = [{"filename": "policy.pdf", "chunk_index": 0, "score": 0.9, "text": "Need pay_stub and id"}]
    required = ["pay_stub", "id"]

    tc1 = _tool_call("tc-1", "search_policy_tool", {"query": "personal docs"})
    tc2 = _tool_call("tc-2", "extract_requirements_tool", {"loan_type": "personal", "policy_chunks": chunks})

    responses = [
        _response(content=None, tool_calls=[tc1]),
        _response(content=None, tool_calls=[tc2]),
        _response(content="Requirements extracted.", tool_calls=None),
    ]

    async def fake_call_tool(name, args):
        return chunks if name == "search_policy_tool" else required

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=responses)
    with patch("app.core.tool_runner._get_client", return_value=mock_client), \
         patch("app.core.tool_runner.call_tool", side_effect=fake_call_tool):
        result = await run_with_tools(
            system_prompt="Check documents.",
            user_prompt="personal loan",
        )

    assert len(result["tool_calls_made"]) == 2
    assert result["tool_calls_made"][0]["name"] == "search_policy_tool"
    assert result["tool_calls_made"][1]["name"] == "extract_requirements_tool"
    assert result["tool_calls_made"][1]["result"] == required


async def test_max_iterations_cap_stops_infinite_loop():
    """Safety cap: stops at max_iterations even if LLM keeps requesting tools."""
    tc = _tool_call("tc-inf", "search_policy_tool", {"query": "loop"})
    always_tool = _response(content=None, tool_calls=[tc])

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=always_tool)
    with patch("app.core.tool_runner._get_client", return_value=mock_client), \
         patch("app.core.tool_runner.call_tool", AsyncMock(return_value=[])):
        result = await run_with_tools(
            system_prompt="Loop.",
            user_prompt="go",
            max_iterations=3,
        )

    assert result["content"] == ""
    assert len(result["tool_calls_made"]) == 3


async def test_quality_flag_routes_to_quality_model():
    """quality=True must pass QUALITY_MODEL to the completions API."""
    from app.llm_client import QUALITY_MODEL

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_response(content="quality response")
    )
    with patch("app.core.tool_runner._get_client", return_value=mock_client):
        await run_with_tools(
            system_prompt="Evaluate carefully.",
            user_prompt="Score this.",
            quality=True,
        )

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == QUALITY_MODEL


async def test_fast_flag_routes_to_fast_model():
    """quality=False (default) must pass FAST_MODEL to the completions API."""
    from app.llm_client import FAST_MODEL

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_response(content="fast response")
    )
    with patch("app.core.tool_runner._get_client", return_value=mock_client):
        await run_with_tools(
            system_prompt="Quick check.",
            user_prompt="Go.",
        )

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == FAST_MODEL


async def test_allowed_tools_filter_limits_schema_sent():
    """Only the tools in allowed_tools are included in the API call."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_response(content="ok")
    )
    with patch("app.core.tool_runner._get_client", return_value=mock_client):
        await run_with_tools(
            system_prompt="Search only.",
            user_prompt="query",
            allowed_tools=["search_policy_tool"],
        )

    tools_sent = mock_client.chat.completions.create.call_args.kwargs["tools"]
    names = [t["function"]["name"] for t in tools_sent]
    assert names == ["search_policy_tool"]


async def test_tool_result_appended_to_messages():
    """Tool result is sent back in a tool-role message with matching tool_call_id."""
    tc = _tool_call("tc-abc", "search_policy_tool", {"query": "test"})
    responses = [
        _response(content=None, tool_calls=[tc]),
        _response(content="Got it.", tool_calls=None),
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=responses)
    with patch("app.core.tool_runner._get_client", return_value=mock_client), \
         patch("app.core.tool_runner.call_tool", AsyncMock(return_value=["chunk"])):
        await run_with_tools(system_prompt="s", user_prompt="u")

    # Second call's messages must include the tool result
    second_call_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_messages = [m for m in second_call_messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "tc-abc"


# ---------------------------------------------------------------------------
# find_tool_result
# ---------------------------------------------------------------------------

def test_find_tool_result_returns_matching_entry():
    calls = [
        {"name": "search_policy_tool", "args": {}, "result": ["chunk"]},
        {"name": "extract_requirements_tool", "args": {}, "result": ["pay_stub", "id"]},
    ]
    assert find_tool_result(calls, "extract_requirements_tool") == ["pay_stub", "id"]


def test_find_tool_result_first_match_wins():
    """When a tool is called twice, returns the first result."""
    calls = [
        {"name": "search_policy_tool", "args": {}, "result": ["first"]},
        {"name": "search_policy_tool", "args": {}, "result": ["second"]},
    ]
    assert find_tool_result(calls, "search_policy_tool") == ["first"]


def test_find_tool_result_returns_none_when_not_found():
    calls = [{"name": "search_policy_tool", "args": {}, "result": []}]
    assert find_tool_result(calls, "check_fraud_signals_tool") is None


def test_find_tool_result_empty_list_returns_none():
    assert find_tool_result([], "any_tool") is None
