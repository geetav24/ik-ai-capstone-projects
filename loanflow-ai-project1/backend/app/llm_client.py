"""
LLM client — two entry points, one OpenAI client.

ask_llm_fast()    → gpt-4o-mini  — planner, guardrails, doc-check, fraud
ask_llm_quality() → gpt-4o       — reviewer guidance, LLM-as-Judge

Why two functions instead of a parameter?
  Callers shouldn't decide which model to use — that's an infra decision.
  Hardcoding the split here means you can tune the model names in one place.

Cost note: gpt-4o-mini is ~15x cheaper per token than gpt-4o.
Only use ask_llm_quality where answer quality directly affects the output
the human reviewer reads. Everything else uses fast.
"""
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
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content


async def ask_llm_quality(system_prompt: str, user_prompt: str) -> str:
    response = await _get_client().chat.completions.create(
        model=QUALITY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content


async def ask_llm_json(system_prompt: str, user_prompt: str, *, fast: bool = True) -> dict:
    """
    Wrapper that returns parsed JSON. Raises ValueError if the model returns
    non-JSON (tells you to fix your prompt, not retry blindly).

    fast=True  → gpt-4o-mini (default, for structured extraction tasks)
    fast=False → gpt-4o (for judge calls where quality matters)
    """
    fn = ask_llm_fast if fast else ask_llm_quality
    content = await fn(system_prompt, user_prompt)
    # Strip markdown code fences if the LLM wrapped the JSON
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1]
        stripped = stripped.rsplit("```", 1)[0].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned non-JSON. Fix your prompt or add 'Return ONLY valid JSON.' "
            f"Raw response: {content[:200]}"
        ) from e
