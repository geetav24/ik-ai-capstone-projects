# app/workflows/langgraph_workflow.py

from langgraph.graph import StateGraph,START, END


async def document_check_agent(state: dict) -> dict:
    """
    TODO: Later you will implement real document logic here.
    For now, this proves LangGraph node is running.
    """
    state["missing_documents"] = []

    question = state.get("question", "").lower()

    if "bank" in question or "statement" in question:
        state["missing_documents"].append("bank_statements")

    state["agent_trace"].append("DocumentCheckAgent completed")
    return state


async def risk_review_agent(state: dict) -> dict:
    """
    TODO: Later add credit score / income / loan amount risk rules.
    """
    state["risk_flags"] = []
    
    if state["credit_score"] < 650:
     state["risk_flags"].append("low_credit_score")

    if state["loan_amount"] > state["annual_income"] * 5:
        state["risk_flags"].append("high_dti_risk")
    
    state["agent_trace"].append("RiskReviewAgent completed")
    return state


async def reviewer_agent(state: dict) -> dict:
    """
    TODO: Later replace this with LLM-generated reviewer guidance.
    """
    state["answer"] = (
        f"Loan {state['loan_id']} requires human review. "
        f"Missing documents: {state['missing_documents']}. "
        f"Risk flags: {state['risk_flags']}. "
        "This system does not approve or reject loans."
    )

    state["agent_trace"].append("reviewer_agent")
    return state

async def guardrail_agent(state: dict) -> dict:
    state["requires_human_review"] = True
    state["guardrails_applied"] = [
        "no_final_approval",
        "human_review_required"
    ]
    state["agent_trace"].append("GuardrailAgent completed")
    return state

async def evaluation_agent(state: dict) -> dict:
    score = 100
    feedback = []

    answer = state.get("answer", "").lower()

    if not state.get("requires_human_review"):
        score -= 40
        feedback.append("Human review was not required.")

    if "approve" in answer or "reject" in answer:
        score -= 50
        feedback.append("Unsafe final decision language detected.")

    if not state.get("missing_documents"):
        score -= 10
        feedback.append("No missing documents identified.")

    if state.get("risk_flags"):
        feedback.append("Risk indicators were successfully identified.")
    else:
        feedback.append("No major risk indicators detected based on current review rules.")

    if not feedback:
        feedback.append("Good response. Safety and review guidance look correct.")

    state["evaluation"] = {
        "score": score,
        "passed": score >= 70,
        "feedback": feedback
    }
    state["agent_trace"].append("EvaluationAgent completed")
    return state

def build_graph():
    graph = StateGraph(dict)
    graph.add_node("document_check", document_check_agent)
    graph.add_node("risk_review", risk_review_agent)
    graph.add_node("guardrail", guardrail_agent)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("evaluation", evaluation_agent)

    graph.add_edge(START, "document_check")
    graph.add_edge("document_check", "risk_review")
    graph.add_edge("risk_review", "guardrail")
    graph.add_edge("guardrail", "reviewer")
    graph.add_edge("reviewer", "evaluation")
    graph.add_edge("evaluation", END)

    return graph.compile()


loan_review_graph = build_graph()