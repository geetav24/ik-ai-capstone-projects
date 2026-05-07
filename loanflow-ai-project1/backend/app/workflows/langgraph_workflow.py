# app/workflows/langgraph_workflow.py

from langgraph.graph import StateGraph, END
from app.llm_client import ask_llm
from app.tools.loan_policy_tool import get_loan_policy
from app.services.retrieval_service import search_similar_chunks

async def retrieval_agent(state: dict) -> dict:
    question = state.get("question", "")

    retrieved_context = search_similar_chunks(question, top_k=3)

    state["retrieved_context"] = retrieved_context
    state["agent_trace"].append("RetrievalAgent completed")

    return state

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
    risk_flags = []

    if state["credit_score"] < 700:
        risk_flags.append("low_credit_score")

    if state["loan_amount"] > 500000:
        risk_flags.append("high_loan_amount")

    state["risk_flags"] = risk_flags

    state["agent_trace"].append("RiskReviewAgent completed")

    return state


async def reviewer_agent(state: dict) -> dict:
    retrieved_context_text = "\n\n".join(
        [
            f"Source: {item.get('filename')} | Chunk: {item.get('chunk_index')}\n{item.get('text')}"
            for item in state.get("retrieved_context", [])
        ]
    )

    prompt = f"""
            You are a loan review assistant.

            Retrieved policy context:
            {retrieved_context_text}

            Loan details:
            - Loan ID: {state.get("loan_id")}
            - Borrower: {state.get("borrower_name")}
            - Loan Amount: {state.get("loan_amount")}
            - Annual Income: {state.get("annual_income")}
            - Credit Score: {state.get("credit_score")}

            Detected missing documents:
            {state.get("missing_documents", [])}

            Detected risk flags:
            {state.get("risk_flags", [])}

            Reviewer question:
            {state.get("question")}

            Write safe reviewer guidance.
            Do not approve or reject the loan.
            """
    answer = await ask_llm(prompt)

    citations = [
        {
            "filename": item.get("filename"),
            "chunk_index": item.get("chunk_index"),
            "score": item.get("score"),
        }
        for item in state.get("retrieved_context", [])
    ]
    state["citations"] = citations
    state["answer"] = answer

    state["agent_trace"].append("LoanPolicyTool called")
    state["agent_trace"].append("ReviewerAgent completed")

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
    graph.add_node("retrieval_agent", retrieval_agent)
    graph.add_node("document_check", document_check_agent)
    graph.add_node("risk_review", risk_review_agent)
    graph.add_node("guardrail", guardrail_agent)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("evaluation", evaluation_agent)

    graph.set_entry_point("retrieval_agent")
    graph.add_edge("retrieval_agent", "document_check")
    graph.add_edge("document_check", "risk_review")
    graph.add_edge("risk_review", "guardrail")
    graph.add_edge("guardrail", "reviewer")
    graph.add_edge("reviewer", "evaluation")
    graph.add_edge("evaluation", END)

    return graph.compile()


loan_review_graph = build_graph()