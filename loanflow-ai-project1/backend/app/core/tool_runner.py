"""
Tool Runner — lets the LLM decide which MCP tools to call.

Separation of duties:
    tool_runner  — HOW: fetches schemas, converts to OpenAI format, runs the loop
    Agent        — WHAT: defines the task via system + user prompts, allowed tools
    LLM          — WHICH: picks tools and arguments based on the task
    MCP server   — EXECUTES: runs the tool, returns the result

Usage in an agent:
    result = await run_with_tools(
        system_prompt="You are a document compliance agent...",
        user_prompt=f"Check documents for: {loan_type}",
        allowed_tools=["search_policy_tool", "extract_requirements_tool"],
    )
    content      = result["content"]        # LLM's final text response
    tool_calls   = result["tool_calls_made"]  # list of {name, args, result}

The LLM loops until it has enough information to answer — no hardcoded call sequence.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.mcp.client import call_tool, list_tools_with_schema
from app.llm_client import FAST_MODEL, QUALITY_MODEL, _get_client

# ---------------------------------------------------------------------------
# Schema cache — tool schemas don't change at runtime; fetch once per process
# ---------------------------------------------------------------------------

_schema_cache: list[dict] | None = None


async def _get_openai_tools(allowed: list[str] | None = None) -> list[dict]:
    """
    Return MCP tool schemas in OpenAI function-calling format.
    Caches after the first fetch. Filtered to `allowed` if provided.
    """
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = await list_tools_with_schema()

    schemas = _schema_cache
    if allowed is not None:
        schemas = [s for s in schemas if s["name"] in allowed]

    return [
        {
            "type": "function",
            "function": {
                "name":        s["name"],
                "description": s["description"],
                "parameters":  s["parameters"],
            },
        }
        for s in schemas
    ]


# ---------------------------------------------------------------------------
# Tool-calling loop
# ---------------------------------------------------------------------------

async def run_with_tools(
    system_prompt: str,
    user_prompt: str,
    allowed_tools: list[str] | None = None,
    quality: bool = False,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """
    Run an LLM with access to MCP tools.

    The LLM decides which tools to call, in what order, with what arguments.
    Loops until the LLM produces a final text response (no more tool calls)
    or max_iterations is reached.

    Args:
        system_prompt:  Agent role and task instructions for the LLM
        user_prompt:    Specific input for this request
        allowed_tools:  Restrict which tools the LLM can see. None = all tools.
        quality:        True → gpt-4o (reviewer/judge). False → gpt-4o-mini.
        max_iterations: Safety cap on the tool-call loop.

    Returns:
        {
            "content":        str   — LLM's final text response
            "tool_calls_made": list — [{name, args, result}, ...]
        }
    """
    model = QUALITY_MODEL if quality else FAST_MODEL
    tools = await _get_openai_tools(allowed_tools)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    tool_calls_made: list[dict] = []

    for _ in range(max_iterations):
        response = await _get_client().chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        # Append assistant message — must be the raw object for tool_call_id continuity
        messages.append(msg)

        if not msg.tool_calls:
            # LLM is done — return final answer
            return {
                "content":         msg.content or "",
                "tool_calls_made": tool_calls_made,
            }

        # Execute every tool the LLM requested
        for tc in msg.tool_calls:
            args   = json.loads(tc.function.arguments)
            result = await call_tool(tc.function.name, args)

            tool_calls_made.append({
                "name":   tc.function.name,
                "args":   args,
                "result": result,
            })

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(result),
            })

    # Reached max iterations — return what we have
    return {
        "content":         "",
        "tool_calls_made": tool_calls_made,
    }


def find_tool_result(tool_calls_made: list[dict], tool_name: str) -> Any:
    """
    Helper — extract the result of a specific tool from tool_calls_made.

    Returns None if the tool was not called.
    """
    for tc in tool_calls_made:
        if tc["name"] == tool_name:
            return tc["result"]
    return None
