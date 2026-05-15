"""
MCP Client — connects to the LoanFlow MCP server over HTTP/SSE.

The MCP server runs as a separate process (mcp-server/ package).
This client connects to it via URL — no subprocess spawning, no path tricks.

Env vars:
    MCP_SERVER_URL = http://localhost:8001/sse   (default: local dev)
    MCP_API_KEY    = secret                      (optional Bearer token)

Architecture:
    Agent → call_tool("search_policy_tool", {...})
                ↓
          MCP Client (this file)
                ↓   [HTTP/SSE]
          MCP Server  (mcp-server/mcp_server/server.py — separate process)
                ↓
          Tool implementation (registry.py)
                ↓
          Pinecone / SQLite / LLM

Lifecycle:
    init_mcp_client()     — called once at FastAPI startup (main.py lifespan)
    shutdown_mcp_client() — called once at FastAPI shutdown
    call_tool(...)        — called by agents during request handling
    list_tools(...)       — tool discovery / health check
"""
from __future__ import annotations

import json
import os
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

# ---------------------------------------------------------------------------
# Connection state — one session shared across all requests
# ---------------------------------------------------------------------------

_session: ClientSession | None = None
_transport_cm = None
_session_cm = None


def _make_transport_cm():
    """Build SSE transport context manager from current env vars.

    Read at call time (not import time) so the test fixture can override
    MCP_SERVER_URL before init_mcp_client() is called.
    """
    url = os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")
    headers: dict[str, str] = {}
    if api_key := os.getenv("MCP_API_KEY"):
        headers["Authorization"] = f"Bearer {api_key}"
    return sse_client(url=url, headers=headers or None)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init_mcp_client() -> None:
    """
    Open a persistent SSE session to the MCP server.
    The server must already be running at MCP_SERVER_URL.
    Call once at FastAPI startup via lifespan.
    """
    global _session, _transport_cm, _session_cm

    _transport_cm = _make_transport_cm()
    read_stream, write_stream = await _transport_cm.__aenter__()

    _session_cm = ClientSession(read_stream, write_stream)
    _session = await _session_cm.__aenter__()

    await _session.initialize()


async def shutdown_mcp_client() -> None:
    """
    Close the SSE session. The remote MCP server keeps running.
    Call at FastAPI shutdown via lifespan.
    """
    global _session, _transport_cm, _session_cm
    if _session_cm:
        await _session_cm.__aexit__(None, None, None)
    if _transport_cm:
        await _transport_cm.__aexit__(None, None, None)
    _session = None


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------

async def call_tool(tool_name: str, args: dict) -> Any:
    """
    Call a tool on the MCP server by name.

    Args:
        tool_name: Registered tool name (e.g. "search_policy_tool")
        args:      Arguments matching the tool's input schema

    Returns:
        Deserialized tool result (dict or list depending on the tool).
    """
    if _session is None:
        raise RuntimeError(
            "MCP client not initialized. "
            "Ensure init_mcp_client() is called at startup."
        )

    result = await _session.call_tool(tool_name, args)

    if not result.content:
        return {}

    raw = result.content[0].text
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, AttributeError):
        return raw


async def list_tools() -> list[str]:
    """Return names of all tools registered on the MCP server."""
    if _session is None:
        raise RuntimeError("MCP client not initialized.")
    result = await _session.list_tools()
    return [t.name for t in result.tools]


async def list_tools_with_schema() -> list[dict]:
    """
    Return full schema for every tool — name, description, JSON Schema params.
    Useful for the GET /tools discovery endpoint and debugging.
    """
    if _session is None:
        raise RuntimeError("MCP client not initialized.")
    result = await _session.list_tools()
    return [
        {
            "name":        t.name,
            "description": t.description or "",
            "parameters":  t.inputSchema,
        }
        for t in result.tools
    ]
