from app.schemas.loan_schemas import LoanReviewRequest, LoanReviewResponse
from app.workflows.langgraph_workflow import loan_review_graph


async def review_loan(request: LoanReviewRequest) -> LoanReviewResponse:
    """Entry point used by FastAPI endpoint.

    Converts API request to LangGraph state, invokes workflow, converts state to
    response model for React UI.
    """

    initial_state = {
        "loan_id": request.loan_id,
        "borrower_name": request.borrower_name,
        "loan_amount": request.loan_amount,
        "annual_income": request.annual_income,
        "credit_score": request.credit_score,
        "question": request.question,
        "missing_documents": [],
        "risk_flags": [],
        "guardrails_applied": [],
        "requires_human_review": True,
        "agent_trace": [],
    }

    final_state = await loan_review_graph.ainvoke(initial_state)
    return LoanReviewResponse(**final_state)
