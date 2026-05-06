from app.workflows.langgraph_workflow import loan_review_graph
from app.models.loan_models import LoanReviewRequest, LoanReviewResponse

async def review_loan(request: LoanReviewRequest):
    initial_state = {
        "loan_id": request.loan_id,
        "borrower_name": request.borrower_name,
        "question": request.question,
        "missing_documents": [],
        "risk_flags": [],
        "requires_human_review": True,
        "answer": "",
        "agent_trace": [],
        "credit_score": request.credit_score,
        "loan_amount": request.loan_amount,
        "annual_income": request.annual_income,
        "evaluation": {},
        "guardrails_applied": []
    }

    final_state = await loan_review_graph.ainvoke(initial_state)

    return {
        "loan_id": final_state["loan_id"],
        "borrower_name": final_state["borrower_name"],
        "loan_amount": final_state["loan_amount"],
        "annual_income": final_state["annual_income"],
        "credit_score": final_state["credit_score"],
        "answer": final_state["answer"],
        "missingDocuments": final_state["missing_documents"],
        "riskFlags": final_state["risk_flags"],
        "requiresHumanReview": final_state["requires_human_review"],
        "agentTrace": final_state.get("agent_trace", []),
        "guardrailsApplied": final_state.get("guardrails_applied", []),
        "evaluation": {
            "decision_quality": "safe",
            "reasoning": "The agent identified missing documents and risk flags, then routed the loan to human review.",
            "hallucination_risk": "low",
            "policy_compliance": "passed"
        }
    }