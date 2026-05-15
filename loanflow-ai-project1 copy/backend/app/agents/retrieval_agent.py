"""
RetrievalAgent — fetches relevant policy chunks from Pinecone via the tool layer.

This agent is a thin wrapper: it calls the loan_policy_search tool and
reformats the result as a RetrievedContext. No LLM call here.

Key constraint: the agent calls the TOOL, never Pinecone directly.
"""
from app.core.tools.registry import get_registry
from app.models.v2_models import RetrievedContext, Citation
from app.workflows.state import LoanReviewState


async def retrieval_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads state["sanitized_input"]["question"]; writes retrieved_context.

    TODO — implement:

    1. Get the registry: registry = get_registry()
    2. Build a rich query that includes both the question and key loan attributes:
           query = (
               f"{state['sanitized_input']['question']} "
               f"loan_type={app['loan_type']} "
               f"loan_amount={app['loan_amount']}"
           )
       A richer query retrieves more relevant policy chunks than the raw question alone.
    3. Call: result = await registry.call("loan_policy_search", {"query": query, "top_k": 5})
    4. Map result["chunks"] into Citation objects.
    5. Return:
        {
            "retrieved_context": RetrievedContext(chunks=[...]).model_dump(),
            "agent_trace": [TraceEntry(agent="retrieval", ...).model_dump()],
        }
    """
    raise NotImplementedError("TODO: implement RetrievalAgent")
