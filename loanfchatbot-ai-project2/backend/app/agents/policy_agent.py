"""
PolicyAgent — Specialist node that answers policy questions using RAG.

Responsibility:
  Retrieve the top-K relevant policy chunks from Pinecone for the user's
  message, then ask the LLM to produce a grounded answer that cites each
  source chunk.  Never invent policy rules that are not in the retrieved text.

Writes to state:
  policy_chunks      — list of PolicyChunk dicts retrieved from Pinecone
  specialists_called — appends "policy"
  agent_trace        — appends one AgentTraceEntry
"""
from datetime import datetime, timezone

from app.llm_client import ask_llm_fast
from app.models.models import AgentTraceEntry, InquiryState
from app.tools.policy_tool import search_policy


async def policy_agent(state: InquiryState) -> dict:
    """
    LangGraph node. Reads state['sanitized_message']; writes policy_chunks
    and appends to specialists_called and agent_trace.

    Steps:
      1. Call search_policy(query, top_k=5) to retrieve relevant chunks.
      2. (Optional) Ask LLM to refine or re-rank chunks for the specific question.
      3. Store raw chunks in state — SynthesisAgent will use them.

    Note: This agent only retrieves. It does NOT generate the final answer.
    Answer generation is the responsibility of SynthesisAgent.
    """
    started = datetime.now(timezone.utc)
    sanitized = state.get("sanitized_message", "")

    # TODO: extract the clean question from the <<<USER_MESSAGE>>> delimiters
    #       before passing to the embedding model. The delimiters are noise.
    query = sanitized.replace("<<<USER_MESSAGE>>>", "").replace("<<<END_USER_MESSAGE>>>", "").strip()

    # TODO: tune top_k — 5 chunks is a reasonable default; increase for complex
    #       policy questions, decrease for faster latency on simple lookups.
    chunks = await search_policy(query=query, top_k=5)

    chunk_dicts = [c.model_dump() for c in chunks]

    finished = datetime.now(timezone.utc)
    trace = AgentTraceEntry(
        agent="policy",
        started_at=started,
        finished_at=finished,
        input_summary=f"query_length={len(query)}",
        output_summary=f"retrieved={len(chunk_dicts)} chunks",
    )

    existing_trace = state.get("agent_trace") or []
    existing_called = state.get("specialists_called") or []
    return {
        "policy_chunks": chunk_dicts,
        "specialists_called": existing_called + ["policy"],
        "agent_trace": existing_trace + [trace.model_dump()],
    }
