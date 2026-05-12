"""
OutputGuardrail — validates the ReviewerAgent's answer before it reaches the user.

Runs AFTER ReviewerAgent, BEFORE EvaluationAgent.
(In v1 the guardrail ran before the reviewer — that was wrong. Fixed in v2.)

On violation: swap the answer with a safe fallback. No retry.
The conditional edge after this node routes to either EvaluationAgent (pass)
or SafeFallback (fail), which then feeds into EvaluationAgent.

Three checks (from USE_CASES.md §7):
  1. Forbidden phrases — "approved", "I approve", "denied", "rejected"
  2. Citation honesty — every cited source must be in retrieved_context
  3. PII scrub — strip any PII the LLM regurgitated
"""
from app.models.v2_models import GuardrailResult
from app.workflows.state import LoanReviewState

SAFE_FALLBACK_ANSWER = (
    "Unable to produce guidance for this application. "
    "Please escalate for manual review."
)

# Phrases that indicate the model crossed into approval/rejection territory
FORBIDDEN_PHRASES = [
    "i approve",
    "this loan is approved",
    "loan approved",
    "approved",
    "i reject",
    "this loan is rejected",
    "loan rejected",
    "denied",
    "rejected",
]


async def output_guardrail_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads reviewer_guidance + retrieved_context; writes guardrail_result.

    TODO — implement three checks:

    CHECK 1 — Forbidden phrases
        Lowercase the answer and check for any phrase in FORBIDDEN_PHRASES.
        Be careful: "not approved" should NOT trigger (check for standalone phrases
        or use word-boundary regex to avoid false positives).
        On violation: add "forbidden_phrase" to violations list.

    CHECK 2 — Citation honesty
        Parse the answer for inline citations (e.g., "[Source: filename, chunk X]").
        Check that each cited (filename, chunk_index) pair exists in
        state["retrieved_context"]["chunks"].
        On violation: add "fabricated_citation" to violations list.
        Hint: you can use a regex like r"\[Source: (.+?), chunk (\d+)\]"

    CHECK 3 — PII scrub (same regex as InputGuardrail)
        If the answer contains SSN / account / CC patterns, redact them.
        If any were found: add "pii_in_output" to violations list.

    If violations is empty:
        guardrail_result = GuardrailResult(passed=True)
        answer stays unchanged

    If violations is non-empty:
        guardrail_result = GuardrailResult(passed=False, violations=violations)
        state["reviewer_guidance"]["answer"] = SAFE_FALLBACK_ANSWER
        state["reviewer_guidance"]["requires_human_review"] = True

    Return:
        {
            "guardrail_result": guardrail_result.model_dump(),
            "reviewer_guidance": updated_guidance,   # may be swapped with fallback
            "agent_trace": [TraceEntry(agent="output_guardrail", ...).model_dump()],
            "guardrails_applied": ["output_guardrail"] if violations else [],
        }
    """
    raise NotImplementedError("TODO: implement OutputGuardrail")
