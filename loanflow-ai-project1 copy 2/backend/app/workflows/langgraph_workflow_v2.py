"""
LoanFlow v2 — LangGraph workflow with conditional routing (USE_CASES.md §4).

Architecture (copy this into README):

    InputGuardrail → PlannerAgent → RetrievalAgent → DocumentCheckAgent
        → RiskReviewAgent → [conditional] → FraudDetectionAgent (optional)
            → ReviewerAgent → OutputGuardrail → [conditional]
                → EvaluationAgent → END
                (violation path: SafeFallback → EvaluationAgent → END)

Key LangGraph concepts used here:
  - StateGraph:           the graph builder; nodes + edges defined on it
  - add_node:             registers a coroutine as a named graph node
  - add_edge:             unconditional A → B transition
  - add_conditional_edges: calls a routing function to pick next node
  - set_entry_point:      first node to run
  - compile():            returns an executable Runnable (call .ainvoke())
"""
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import END, StateGraph

from app.agents.document_check_agent import document_check_agent
from app.agents.evaluation_agent import evaluation_agent
from app.agents.fraud_detection_agent import fraud_detection_agent
from app.agents.input_guardrail import input_guardrail_agent
from app.agents.output_guardrail import output_guardrail_agent
from app.agents.planner_agent import planner_agent
from app.agents.retrieval_agent import retrieval_agent
from app.agents.reviewer_agent import reviewer_agent
from app.agents.risk_review_agent import risk_review_agent
from app.models.v2_models import LoanReviewResponse, ReviewerGuidance
from app.workflows.state import LoanReviewState


# ---------------------------------------------------------------------------
# Routing thresholds (must match planner_agent.py constants)
# ---------------------------------------------------------------------------
HIGH_LOAN_THRESHOLD = 500_000
INCOME_RATIO_THRESHOLD = 5.0

SAFE_FALLBACK_ANSWER = (
    "Unable to produce guidance for this application. "
    "Please escalate for manual review."
)


# ---------------------------------------------------------------------------
# Conditional edge: should FraudDetection run?
# ---------------------------------------------------------------------------

def should_run_fraud(state: LoanReviewState) -> Literal["fraud_detection", "reviewer"]:
    """
    Called by LangGraph after risk_review_node completes.
    Returns the name of the next node to execute.

    TODO — implement routing logic:

    Read from state:
        app = state["application"]
        flags = state.get("risk_assessment", {}).get("flags", [])
        flag_types = {f["flag_type"] for f in flags}

    Run fraud if ANY condition is true:
        1. float(app["loan_amount"]) > HIGH_LOAN_THRESHOLD
        2. annual_income > 0 and loan_amount / annual_income > INCOME_RATIO_THRESHOLD
        3. annual_income == 0  (zero income is a fraud signal)
        4. app["employment_status"] == "self_employed" and loan_amount > 200_000
        5. "income_ratio_anomaly" in flag_types  (RiskReview already caught it)
        6. "velocity_anomaly" in flag_types

    Return "fraud_detection" or "reviewer".
    """
    raise NotImplementedError("TODO: implement should_run_fraud routing function")


# ---------------------------------------------------------------------------
# Conditional edge: did OutputGuardrail pass?
# ---------------------------------------------------------------------------

def should_use_safe_fallback(state: LoanReviewState) -> Literal["evaluation", "safe_fallback"]:
    """
    Called by LangGraph after output_guardrail_node completes.

    TODO — implement:
        result = state.get("guardrail_result", {})
        if result.get("passed", True):
            return "evaluation"
        return "safe_fallback"
    """
    raise NotImplementedError("TODO: implement should_use_safe_fallback routing function")


# ---------------------------------------------------------------------------
# Safe fallback node — replaces answer when output guardrail fires
# ---------------------------------------------------------------------------

async def safe_fallback_node(state: LoanReviewState) -> dict:
    """
    Injects a safe fallback answer. Runs only on guardrail violation.
    Does NOT call the LLM — just replaces the answer.

    This node is already complete — no TODO needed here.
    """
    return {
        "reviewer_guidance": {
            "answer": SAFE_FALLBACK_ANSWER,
            "requires_human_review": True,
        },
        "agent_trace": [{
            "agent": "safe_fallback",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "input_summary": "guardrail violation detected",
            "output_summary": "safe fallback answer injected",
        }],
        "guardrails_applied": ["output_guardrail_fallback"],
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    """
    Registers all nodes and edges. Returns the compiled graph.

    Node registration order doesn't matter — LangGraph uses the edge
    definitions to determine execution order.
    """
    workflow = StateGraph(LoanReviewState)

    # -- Register nodes (node name → coroutine) ----------------------------
    workflow.add_node("input_guardrail",  input_guardrail_agent)
    workflow.add_node("planner",          planner_agent)
    workflow.add_node("retrieval",        retrieval_agent)
    workflow.add_node("document_check",   document_check_agent)
    workflow.add_node("risk_review",      risk_review_agent)
    workflow.add_node("fraud_detection",  fraud_detection_agent)
    workflow.add_node("reviewer",         reviewer_agent)
    workflow.add_node("output_guardrail", output_guardrail_agent)
    workflow.add_node("safe_fallback",    safe_fallback_node)
    workflow.add_node("evaluation",       evaluation_agent)

    # -- Entry point --------------------------------------------------------
    workflow.set_entry_point("input_guardrail")

    # -- Unconditional edges (linear backbone) ------------------------------
    workflow.add_edge("input_guardrail", "planner")
    workflow.add_edge("planner",         "retrieval")
    workflow.add_edge("retrieval",       "document_check")
    workflow.add_edge("document_check",  "risk_review")

    # -- Conditional edge: fraud or skip directly to reviewer ---------------
    workflow.add_conditional_edges(
        "risk_review",
        should_run_fraud,
        {
            "fraud_detection": "fraud_detection",
            "reviewer":        "reviewer",
        },
    )

    workflow.add_edge("fraud_detection", "reviewer")

    # -- Conditional edge: output guardrail pass/fail -----------------------
    workflow.add_edge("reviewer", "output_guardrail")

    workflow.add_conditional_edges(
        "output_guardrail",
        should_use_safe_fallback,
        {
            "evaluation":    "evaluation",
            "safe_fallback": "safe_fallback",
        },
    )

    workflow.add_edge("safe_fallback", "evaluation")
    workflow.add_edge("evaluation",    END)

    return workflow


# Compiled graph — import this in the FastAPI route
graph = build_workflow().compile()


# ---------------------------------------------------------------------------
# Entry point — called by the FastAPI /review route
# ---------------------------------------------------------------------------

async def run_loan_review(application: dict, question: str) -> LoanReviewState:
    """
    Execute the full pipeline. Returns final state.

    The FastAPI route calls this and maps state → LoanReviewResponse.

    Initial state sets all Optional fields to None and list fields to [].
    LangGraph requires every key in the TypedDict to be present at start.
    """
    initial_state: LoanReviewState = {
        "application":       application,
        "raw_question":      question,
        "sanitized_input":   None,
        "injection_signals": [],
        "plan":              None,
        "retrieved_context": None,
        "doc_check_result":  None,
        "risk_assessment":   None,
        "fraud_finding":     None,
        "reviewer_guidance": None,
        "guardrail_result":  None,
        "agent_trace":       [],
        "guardrails_applied": [],
        "evaluation":        None,
    }

    final_state: LoanReviewState = await graph.ainvoke(initial_state)
    return final_state
