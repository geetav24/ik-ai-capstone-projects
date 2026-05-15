"""
MCP-aligned Tool Protocol (USE_CASES.md §5).

Tools are the ONLY way agents talk to external data (Pinecone, SQLite, fraud stubs).
This interface matches what a real MCP server would expose over stdio/SSE.
In v2 we keep the interface but skip the transport (in-process for speed).

Writing to this Protocol from Day 1 means:
  - agents never import Session or Pinecone directly
  - if you ever add a real MCP transport, you change the registry, not the agents
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict   # JSON Schema describing the args dict

    async def call(self, args: dict) -> dict:
        """
        Execute the tool with validated args.
        Returns a plain dict (JSON-serializable).
        Raise ValueError for bad inputs; let other exceptions propagate.
        """
        ...
