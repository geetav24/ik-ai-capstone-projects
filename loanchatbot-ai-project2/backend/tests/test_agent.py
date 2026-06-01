"""Tests for loan inquiry agent — mock all tools."""
import pytest
from unittest.mock import AsyncMock, patch
from app.models.models import ChatRequest


async def test_chat_returns_response():
    """Agent returns a ChatResponse with session_id."""
    from app.agent.loan_inquiry_agent import run_inquiry

    mock_response = AsyncMock()
    mock_response.choices[0].message.content = "For a personal loan you need a pay stub."
    mock_response.choices[0].message.tool_calls = None

    with patch("app.agent.loan_inquiry_agent.AsyncOpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await run_inquiry(ChatRequest(session_id="test-123", message="What docs do I need?"))

    assert result.session_id == "test-123"
    assert result.answer != "" or result.tool_calls is not None
