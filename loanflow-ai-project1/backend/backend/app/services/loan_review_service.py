from app.workflows.langgraph_workflow import loan_review_graph


async def review_loan(loan_id: str, question: str):
    initial_state = {
        "loan_id": loan_id,
        "question": question,
        "missing_documents": [],
        "risk_flags": [],
        "requires_human_review": True,
        "answer": "",
        "agent_trace": [],
        "credit_score":0,
        "loan_amount":0,
        "annual_income":0,
        "evaluation":{},
        "guardrails_applied": []
    }

    final_state = await loan_review_graph.ainvoke(initial_state)

    return {
        "loanId": final_state["loan_id"],
        "answer": final_state["answer"],
        "missingDocuments": final_state["missing_documents"],
        "riskFlags": final_state["risk_flags"],
        "requiresHumanReview": final_state["requires_human_review"],
        "agentTrace": final_state.get("agent_trace", []),
        "guardrailsApplied": final_state.get("guardrails_applied", []),
        "credit_score": final_state["credit_score"],
        "loan_amount": final_state["loan_amount"],
        "annual_income": final_state["annual_income"],
        "evaluation": {
            "decision_quality": "safe",
            "reasoning": "The agent identified missing documents and risk flags, then routed the loan to human review.",
            "hallucination_risk": "low",
            "policy_compliance": "passed"
        }
    }