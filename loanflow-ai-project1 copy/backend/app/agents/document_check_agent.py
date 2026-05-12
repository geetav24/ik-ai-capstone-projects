"""
DocumentCheckAgent — compares submitted docs against policy requirements.

v1 used a keyword hack: `if "bank" in question`. Don't do that.
v2 uses the document_required_lookup tool to get the actual required list
from policy, then does a set comparison against submitted docs.

No LLM call needed — this is pure set logic.
"""
from app.core.tools.registry import get_registry
from app.models.v2_models import DocCheckResult
from app.workflows.state import LoanReviewState


async def document_check_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads application + retrieved_context; writes doc_check_result.

    TODO — implement:

    1. Call the tool to get required docs:
           result = await registry.call(
               "document_required_lookup",
               {"loan_type": app["loan_type"]}
           )
           required = set(result["required_documents"])

    2. Extract submitted doc types from the application:
           submitted = {doc["doc_type"] for doc in app["submitted_documents"]}

    3. Compute:
           missing  = list(required - submitted)
           present  = list(required & submitted)

    4. Return:
        {
            "doc_check_result": DocCheckResult(
                missing=missing,
                present=present,
                required_by_policy=list(required),
            ).model_dump(),
            "agent_trace": [TraceEntry(agent="document_check", ...).model_dump()],
        }
    """
    raise NotImplementedError("TODO: implement DocumentCheckAgent")
