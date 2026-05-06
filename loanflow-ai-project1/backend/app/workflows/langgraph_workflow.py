from langgraph.graph import StateGraph, START, END

from app.schemas.loan_schemas import LoanReviewRequest
from app.services.llm_service import generate_reviewer_answer
from app.services.evaluation_service import evaluate_review
from app.workflows.state import LoanReviewState


async def document_check_agent(state: LoanReviewState) -> LoanReviewState:
    """Agent 1: identifies missing or requested documents.

    This starts rule-based for demo reliability. Later replace or enhance with:
    - document upload parsing
    - RAG retrieval from Qdrant
    - LLM extraction from uploaded PDFs
    """

    question = state.get("question", "").lower()
    missing_documents = []

    if "bank statement" in question or "bank statements" in question:
        missing_documents.append("bank_statements")
    if "pay stub" in question or "paystubs" in question:
        missing_documents.append("pay_stubs")
    if "tax" in question:
        missing_documents.append("tax_returns")
    if "id" in question or "identity" in question:
        missing_documents.append("government_id")

    state["missing_documents"] = missing_documents
    state.setdefault("agent_trace", []).append({
        "agent": "DocumentCheckAgent",
        "summary": f"Detected missing documents: {missing_documents or 'none'}",
    })
    return state


async def risk_review_agent(state: LoanReviewState) -> LoanReviewState:
    """Agent 2: applies simple risk rules.

    These are intentionally simple MVP rules. In production, risk models and policy
    engines would be more sophisticated and reviewed by compliance/legal teams.
    """

    risk_flags = []
    credit_score = int(state.get("credit_score", 0))
    annual_income = float(state.get("annual_income", 0))
    loan_amount = float(state.get("loan_amount", 0))

    if credit_score < 650:
        risk_flags.append("low_credit_score")
    if annual_income <= 0:
        risk_flags.append("invalid_income")
    if annual_income > 0 and loan_amount / annual_income > 4:
        risk_flags.append("high_loan_to_income_ratio")

    state["risk_flags"] = risk_flags
    state.setdefault("agent_trace", []).append({
        "agent": "RiskReviewAgent",
        "summary": f"Detected risk flags: {risk_flags or 'none'}",
    })
    return state


async def guardrail_agent(state: LoanReviewState) -> LoanReviewState:
    """Agent 3: final safety guardrail and response formatter.

    Guardrail principle: AI may assist, but must not make final lending decisions.
    """

    request = LoanReviewRequest(
        loan_id=state["loan_id"],
        borrower_name=state["borrower_name"],
        loan_amount=state["loan_amount"],
        annual_income=state["annual_income"],
        credit_score=state["credit_score"],
        question=state["question"],
    )

    answer = await generate_reviewer_answer(
        request,
        state.get("missing_documents", []),
        state.get("risk_flags", []),
    )

    state["answer"] = answer
    state["requires_human_review"] = True
    state["guardrails_applied"] = [
        "no_final_approval",
        "no_final_rejection",
        "human_review_required",
        "financial_decision_guardrail",
    ]
    state.setdefault("agent_trace", []).append({
        "agent": "GuardrailAgent",
        "summary": "Applied final-decision safety guardrails and formatted reviewer response.",
    })
    return state


async def evaluation_agent(state: LoanReviewState) -> LoanReviewState:
    """Evaluation node: grades output safety and completeness.

    This is part of the workflow so the demo can show that the system measures
    output quality, not just generates an answer.
    """

    state["evaluation"] = evaluate_review(
        answer=state.get("answer", ""),
        missing_documents=state.get("missing_documents", []),
        risk_flags=state.get("risk_flags", []),
        requires_human_review=state.get("requires_human_review", False),
    )
    state.setdefault("agent_trace", []).append({
        "agent": "EvaluationAgent",
        "summary": f"Evaluation score: {state['evaluation']['score']}/100",
    })
    return state


def build_loan_review_graph():
    """Build and compile the LangGraph workflow.

    Flow:
    START -> DocumentCheckAgent -> RiskReviewAgent -> GuardrailAgent -> EvaluationAgent -> END
    """

    graph = StateGraph(LoanReviewState)
    graph.add_node("document_check", document_check_agent)
    graph.add_node("risk_review", risk_review_agent)
    graph.add_node("guardrail", guardrail_agent)
    graph.add_node("evaluation", evaluation_agent)

    graph.add_edge(START, "document_check")
    graph.add_edge("document_check", "risk_review")
    graph.add_edge("risk_review", "guardrail")
    graph.add_edge("guardrail", "evaluation")
    graph.add_edge("evaluation", END)

    return graph.compile()


loan_review_graph = build_loan_review_graph()
