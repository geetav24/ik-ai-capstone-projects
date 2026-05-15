"""
RetrievalAgent — fetches relevant policy chunks from Pinecone via the tool layer.

This agent is a thin wrapper: it calls the loan_policy_search tool and
reformats the result as a RetrievedContext. No LLM call here.

Key constraint: the agent calls the TOOL, never Pinecone directly.
"""
from datetime import datetime, timezone
from app.core.tools.registry import get_registry
from app.models.v2_models import RetrievedContext, Citation, TraceEntry
from app.workflows.state import LoanReviewState


async def retrieval_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads state["sanitized_input"]["question"]; writes retrieved_context.
    """
    started = datetime.now(timezone.utc)
    registry = get_registry()
    app = state["application"]
    sanitized_input = state.get("sanitized_input", {})
    question = sanitized_input.get("question", "")
    
    # Build a rich query that includes both the question and key loan attributes
    query = (
        f"{question} "
        f"loan_type={app.get('loan_type', '')} "
        f"loan_amount={app.get('loan_amount', 0)}"
    )
    
    # Call the tool
    result = await registry.call("loan_policy_search", {"query": query, "top_k": 5})
    
    # Map result["chunks"] into Citation objects
    citations = []
    for chunk in result["chunks"]:
        citation = Citation(
            filename=chunk.get("filename", ""),
            chunk_index=chunk.get("chunk_index", 0),
            score=chunk.get("score", 0.0),
            text=chunk.get("text", ""),
        )
        citations.append(citation)
    
    retrieved_context = RetrievedContext(chunks=citations)
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="retrieval",
        started_at=started,
        finished_at=finished,
        input_summary=f"Question length: {len(question)}",
        output_summary=f"Retrieved {len(citations)} policy chunks",
    )
    
    return {
        "retrieved_context": retrieved_context.model_dump(),
        "agent_trace": [trace_entry.model_dump()],
    }
