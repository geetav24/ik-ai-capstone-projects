"""
Web Search Tool — real-time web search via Tavily.

Used for questions outside the policy KB:
  "Where can I get a certified tax return?"
  "What is the FICO score scale?"
  "How do I get an employment letter?"
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.models.models import WebResult

_tavily_client = None


def _get_client():
    global _tavily_client
    if _tavily_client is None:
        from tavily import TavilyClient
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY missing — check backend/.env")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


async def web_search(query: str, max_results: int = 3) -> list[WebResult]:
    """
    Search the web via Tavily API.

    Args:
        query:       Natural language search query
        max_results: Number of results to return

    Returns:
        List of WebResult with title, url, and content snippet
    """
    client = _get_client()
    # TavilyClient.search is synchronous — run in executor to stay async-safe
    import asyncio
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.search(query, max_results=max_results),
    )
    return [
        WebResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
        )
        for r in response.get("results", [])
    ]
