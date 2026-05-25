"""
Minimal LLM client for the MCP server.

Only exposes ask_llm_json — the one LLM call registry.py needs
(extract_requirements). No fast/quality split needed here;
registry tools that call the LLM always use gpt-4o-mini.
"""
import json
import os

from openai import AsyncOpenAI

_client = None
_MODEL = "gpt-4o-mini"


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


async def ask_llm_json(system_prompt: str, user_prompt: str) -> dict:
    """Call the LLM and parse the response as JSON. Raises ValueError on bad JSON."""
    response = await _get_client().chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON. Raw: {content[:200]}") from e
