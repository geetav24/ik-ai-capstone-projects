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
import asyncio
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

# Routing thresholds (must match planner_agent.py constants)
HIGH_LOAN_THRESHOLD = 500_000
INCOME_RATIO_THRESHOLD = 5.0

SAFE_FALLBACK_ANSWER = (
    "Unable to produce guidance for this application. "
    "Please escalate for manual review."
)


def should_run_fraud(state: LoanReviewState) -> Literal["fraud_detection", "reviewer"]:
    """
    Decide whether to run the fraud specialist after risk review.

    Conditions (if any true → run fraud_detection):
      1. loan_amount > HIGH_LOAN_THRESHOLD
      2. annual_income > 0 and loan_amount / annual_income > INCOME_RATIO_THRESHOLD
      3. annual_income == 0
      4. employment_status == "self_employed" and loan_amount > 200_000
      5. "income_ratio_anomaly" in risk flags
      6. "velocity_anomaly" in risk flags
    """
    app = state.get("application", {}) or {}
    loan_amount = float(app.get("loan_amount") or 0)
    annual_income = float(app.get("annual_income") or 0)
    employment_status = app.get("employment_status", "")

    ra = state.get("risk_assessment") or {}
    flags = ra.get("flags", []) if ra else []
    flag_types = {f.get("flag_type") for f in flags if isinstance(f, dict)}

    conds = [
        loan_amount > HIGH_LOAN_THRESHOLD,
        (annual_income > 0 and (loan_amount / annual_income) > INCOME_RATIO_THRESHOLD),
        annual_income == 0,
        (employment_status == "self_employed" and loan_amount > 200_000),
        ("income_ratio_anomaly" in flag_types),
        ("velocity_anomaly" in flag_types),
    ]

    return "fraud_detection" if any(conds) else "reviewer"


def should_use_safe_fallback(state: LoanReviewState) -> Literal["evaluation", "safe_fallback"]:
    """
    If the output guardrail failed, route to `safe_fallback`, otherwise to `evaluation`.
    """
    result = state.get("guardrail_result") or {}
    if result.get("passed", True):
        return "evaluation"
    return "safe_fallback"


async def safe_fallback_node(state: LoanReviewState) -> dict:
    """
    Simple node that injects a safe fallback answer. Used when guardrails fail.
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


async def parallel_specialists_node(state: LoanReviewState) -> dict:
    """
    Run retrieval, document_check, and risk_review concurrently.

    These three agents are fully independent — none reads the other's output.
    asyncio.gather cuts wall-clock time from ~25s sequential to ~10s.
    """
    results = await asyncio.gather(
        retrieval_agent(state),
        document_check_agent(state),
        risk_review_agent(state),
    )
    merged: dict = {}
    for r in results:
        for key, val in r.items():
            if key == "agent_trace" and isinstance(val, list):
                merged.setdefault("agent_trace", []).extend(val)
            else:
                merged[key] = val
    return merged


def build_workflow() -> StateGraph:
    """
    Register nodes and edges and return a compiled StateGraph.
    """
    workflow = StateGraph(LoanReviewState)

    # Register nodes
    workflow.add_node("input_guardrail",      input_guardrail_agent)
    workflow.add_node("planner",              planner_agent)
    workflow.add_node("parallel_specialists", parallel_specialists_node)
    workflow.add_node("fraud_detection",      fraud_detection_agent)
    workflow.add_node("reviewer",             reviewer_agent)
    workflow.add_node("output_guardrail",     output_guardrail_agent)
    workflow.add_node("safe_fallback",        safe_fallback_node)
    workflow.add_node("evaluation",           evaluation_agent)

    # Entry point
    workflow.set_entry_point("input_guardrail")

    # Linear backbone → parallel fan-out
    workflow.add_edge("input_guardrail",      "planner")
    workflow.add_edge("planner",              "parallel_specialists")

    # Conditional: fraud or skip to reviewer
    workflow.add_conditional_edges(
        "parallel_specialists",
        should_run_fraud,
        {
            "fraud_detection": "fraud_detection",
            "reviewer":        "reviewer",
        },
    )
    workflow.add_edge("fraud_detection", "reviewer")

    # Reviewer → OutputGuardrail
    workflow.add_edge("reviewer", "output_guardrail")

    # Conditional: output guardrail pass/fail
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


# Compile graph once at import time (used by FastAPI route)
graph = build_workflow().compile()


async def run_loan_review(application: dict, question: str) -> LoanReviewState:
    """
    Execute the full pipeline and return the final state.
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