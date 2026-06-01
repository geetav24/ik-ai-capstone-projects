"""LLM client — fast (gpt-4o-mini) and quality (gpt-4o) entry points."""
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

FAST_MODEL    = "gpt-4o-mini"
QUALITY_MODEL = "gpt-4o"

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Check backend/.env")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


async def ask_llm_fast(system_prompt: str, user_prompt: str) -> str:
    response = await _get_client().chat.completions.create(
        model=FAST_MODEL,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content


async def ask_llm_json(system_prompt: str, user_prompt: str, *, fast: bool = True) -> dict:
    fn = ask_llm_fast
    content = await fn(system_prompt, user_prompt)
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1]
        stripped = stripped.rsplit("```", 1)[0].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON. Raw: {content[:200]}") from e
