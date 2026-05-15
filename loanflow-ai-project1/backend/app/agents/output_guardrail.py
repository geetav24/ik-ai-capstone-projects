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
import re
from datetime import datetime, timezone

from app.agents.input_guardrail import _FINANCIAL_PII
from app.models.v2_models import GuardrailResult, TraceEntry
from app.workflows.state import LoanReviewState

SAFE_FALLBACK_ANSWER = (
    "Unable to produce guidance for this application. "
    "Please escalate for manual review."
)

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
    Guidance-only implementation of the OutputGuardrail.
    """
    started = datetime.now(timezone.utc)
    reviewer = state.get("reviewer_guidance") or {}
    answer = reviewer.get("answer", "") or ""
    retrieved = state.get("retrieved_context") or {}
    retrieved_chunks = retrieved.get("chunks", []) if retrieved is not None else []

    violations = []

    # CHECK 1 — Forbidden phrases (avoid "not approved" false positive)
    answer_lower = answer.lower()
    for phrase in FORBIDDEN_PHRASES:
        # word-boundary match for the phrase
        pattern = r"\b" + re.escape(phrase) + r"\b"
        for m in re.finditer(pattern, answer_lower, flags=re.IGNORECASE):
            start = m.start()
            # check if 'not' immediately precedes the match (e.g., "not approved")
            pre_window = answer_lower[max(0, start - 6):start].strip()
            if pre_window.startswith("not"):
                # skip this occurrence (not approved)
                continue
            violations.append("forbidden_phrase")
            # one violation entry is enough
            break
        if "forbidden_phrase" in violations:
            break

    # CHECK 2 — Citation honesty
    fabricated = False
    citation_pattern = re.compile(r"\[Source:\s*(.+?),\s*chunk\s*(\d+)\]", flags=re.IGNORECASE)
    cited_pairs = citation_pattern.findall(answer)
    if cited_pairs:
        # Build a set of (filename, index) present in retrieved_context
        present_pairs = {
            (c.get("filename"), int(c.get("chunk_index")))
            for c in retrieved_chunks
            if c.get("filename") is not None and c.get("chunk_index") is not None
        }
        for filename, chunk_idx_str in cited_pairs:
            try:
                idx = int(chunk_idx_str)
            except ValueError:
                fabricated = True
                break
            if (filename.strip(), idx) not in present_pairs:
                fabricated = True
                break
        if fabricated:
            violations.append("fabricated_citation")

    # CHECK 3 — PII scrub (use the same financial regexes as InputGuardrail)
    pii_labels_found = set()
    sanitized_answer = answer
    for pattern, label in _FINANCIAL_PII:
        if re.search(pattern, sanitized_answer):
            sanitized_answer = re.sub(pattern, f"[REDACTED:{label}]", sanitized_answer)
            pii_labels_found.add(label)
    if pii_labels_found:
        violations.append("pii_in_output")

    # Build guardrail result and possibly swap answer
    if violations:
        guardrail_result = GuardrailResult(passed=False, violations=violations)
        # set fallback and force human review
        reviewer["answer"] = SAFE_FALLBACK_ANSWER
        reviewer["requires_human_review"] = True
        guardrails_applied = ["output_guardrail"]
        output_summary = f"violations={violations}"
    else:
        guardrail_result = GuardrailResult(passed=True, violations=[])
        # If we sanitized PII but no other violations, keep sanitized text
        if pii_labels_found:
            reviewer["answer"] = sanitized_answer
        guardrails_applied = []
        output_summary = "passed"

    finished = datetime.now(timezone.utc)
    trace = TraceEntry(
        agent="output_guardrail",
        started_at=started,
        finished_at=finished,
        input_summary=f"answer_len={len(answer)};cited={len(cited_pairs)}",
        output_summary=output_summary,
    )

    result: dict = {
        "guardrail_result": guardrail_result.model_dump(),
        "agent_trace": [trace.model_dump()],
        "guardrails_applied": guardrails_applied,
    }

    # Include updated reviewer_guidance if changed (LangGraph merges outputs)
    if reviewer:
        result["reviewer_guidance"] = reviewer

    return result