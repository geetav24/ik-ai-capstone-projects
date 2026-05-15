"""Pinecone vector store access for the MCP server — lazy init."""
import os

from pinecone import Pinecone

_pc = None
_index = None


def get_index():
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        _index = _pc.Index(os.getenv("PINECONE_INDEX_NAME"))
    return _index
