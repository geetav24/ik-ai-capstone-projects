"""
EvaluationAgent (LLM-as-Judge) — scores the final response.

Runs last, after OutputGuardrail. Scores whatever answer reaches it —
the real guidance OR the safe fallback. Both are meaningful to score.

Uses ask_llm_quality (gpt-4o) because evaluation quality matters for the rubric.
Uses temperature=0 (set in ask_llm_quality) for reproducibility.

Four dimensions to score (each as a string: "pass" | "fail" | "partial"):
  - decision_quality   : Is the guidance useful and actionable?
  - grounding_score    : Is every claim backed by a retrieved policy chunk? (0.0–1.0)
  - hallucination_risk : Does the answer contain claims not in the retrieved context?
  - policy_compliance  : Does the answer stay within policy scope?
"""
from app.llm_client import ask_llm_json
from app.models.v2_models import Evaluation
from app.workflows.state import LoanReviewState


async def evaluation_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads all state; writes evaluation.

    TODO — implement:

    STEP 1 — Build the judge prompt. Include:
        - The final answer (from state["reviewer_guidance"]["answer"])
        - The retrieved policy chunks (abbreviated — first 200 chars each)
        - The risk flags (names only)
        - Instructions to return ONLY valid JSON in this exact schema:
            {
              "decision_quality": "pass" | "fail" | "partial",
              "grounding_score": 0.0–1.0,
              "hallucination_risk": "low" | "medium" | "high",
              "policy_compliance": "pass" | "fail" | "partial",
              "reasoning": "one-sentence explanation"
            }

    STEP 2 — Call ask_llm_json(system_prompt, user_prompt, fast=False)
        (fast=False → uses gpt-4o for judge quality)

    STEP 3 — Validate the JSON has all required keys. If any are missing,
        fill them with "unknown" / 0.0 rather than crashing.

    STEP 4 — Return:
        {
            "evaluation": Evaluation(**parsed_json).model_dump(),
            "agent_trace": [TraceEntry(agent="evaluation", ...).model_dump()],
        }
    """
    raise NotImplementedError("TODO: implement EvaluationAgent")
