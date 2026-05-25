"""
LangGraph state for the loan review pipeline.

LoanReviewState is a TypedDict that flows through every node.
Each node receives the full state and returns a dict of keys to update.
LangGraph merges the returned dict into state — it doesn't replace the whole thing.

Fields annotated with `Annotated[list, operator.add]` are append-only:
  each node can only add entries, never overwrite the whole list.
  This is how agent_trace and guardrails_applied accumulate across nodes.
"""
import operator
from typing import Annotated, Optional, TypedDict


class LoanReviewState(TypedDict):
    # -----------------------------------------------------------------------
    # Input — set once at the entry point, never mutated
    # -----------------------------------------------------------------------
    application: dict           # LoanApplication.model_dump()
    raw_question: str           # the reviewer's original, unsanitized question

    # -----------------------------------------------------------------------
    # InputGuardrail output
    # -----------------------------------------------------------------------
    sanitized_input: Optional[dict]     # SanitizedInput.model_dump()
    injection_signals: list[str]        # top-level copy for easy routing checks

    # -----------------------------------------------------------------------
    # PlannerAgent output
    # -----------------------------------------------------------------------
    plan: Optional[dict]                # Plan.model_dump()

    # -----------------------------------------------------------------------
    # RetrievalAgent output
    # -----------------------------------------------------------------------
    retrieved_context: Optional[dict]   # RetrievedContext.model_dump()

    # -----------------------------------------------------------------------
    # Specialist outputs
    # -----------------------------------------------------------------------
    doc_check_result: Optional[dict]    # DocCheckResult.model_dump()
    risk_assessment: Optional[dict]     # RiskAssessment.model_dump()
    fraud_finding: Optional[dict]       # FraudFinding.model_dump() | None

    # -----------------------------------------------------------------------
    # ReviewerAgent + guardrails
    # -----------------------------------------------------------------------
    reviewer_guidance: Optional[dict]   # ReviewerGuidance.model_dump()
    guardrail_result: Optional[dict]    # GuardrailResult.model_dump()

    # -----------------------------------------------------------------------
    # Audit lists — append-only across nodes
    # -----------------------------------------------------------------------
    agent_trace: Annotated[list[dict], operator.add]        # TraceEntry list
    guardrails_applied: Annotated[list[str], operator.add]  # e.g. ["input_guardrail"]

    # -----------------------------------------------------------------------
    # EvaluationAgent output
    # -----------------------------------------------------------------------
    evaluation: Optional[dict]          # Evaluation.model_dump()
