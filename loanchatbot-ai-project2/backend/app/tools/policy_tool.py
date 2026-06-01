"""
Policy Tool — semantic search over the loan policy knowledge base.

Reuses the Pinecone index from LoanFlow (Project 1).
Same index, same embedding model — plug and play.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.models.models import PolicyChunk

_openai_client = None
_pinecone_index = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing — check backend/.env")
        _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


def _get_index():
    global _pinecone_index
    if _pinecone_index is None:
        from pinecone import Pinecone
        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME", "loanflow-policy")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY missing — check backend/.env")
        pc = Pinecone(api_key=api_key)
        _pinecone_index = pc.Index(index_name)
    return _pinecone_index


async def search_policy(query: str, top_k: int = 3) -> list[PolicyChunk]:
    """
    Search Pinecone for policy chunks relevant to the query.

    Args:
        query:  Natural language question
        top_k:  Number of chunks to return

    Returns:
        List of PolicyChunk sorted by relevance score
    """
    # Embed the query with the same model used during indexing
    response = await _get_openai().embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    vector = response.data[0].embedding

    # Query Pinecone
    index = _get_index()
    results = index.query(vector=vector, top_k=top_k, include_metadata=True)

    chunks = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        chunks.append(PolicyChunk(
            filename=meta.get("filename", "loan_policy.pdf"),
            chunk_index=int(meta.get("chunk_index", 0)),
            score=float(match.get("score", 0.0)),
            text=meta.get("text", ""),
        ))
    return chunks
