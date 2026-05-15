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
from app.models.v2_models import GuardrailResult, TraceEntry
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
    """
    started = datetime.now(timezone.utc)
    
    reviewer_guidance = state.get("reviewer_guidance", {})
    answer = reviewer_guidance.get("answer", "")
    retrieved_context = state.get("retrieved_context", {})
    
    violations = []
    
    # CHECK 1 — Forbidden phrases
    answer_lower = answer.lower()
    for phrase in FORBIDDEN_PHRASES:
        if re.search(r"\b" + re.escape(phrase) + r"\b", answer_lower):
            violations.append("forbidden_phrase")
            break
    
    # CHECK 2 — Citation honesty
    # Parse for inline citations like [Source: filename, chunk X]
    citation_pattern = r"\[Source: (.+?), chunk (\d+)\]"
    citations_in_answer = re.findall(citation_pattern, answer)
    
    # Build a set of valid (filename, chunk_index) pairs from retrieved_context
    valid_citations = set()
    for chunk in retrieved_context.get("chunks", []):
        filename = chunk.get("filename", "")
        chunk_index = chunk.get("chunk_index", 0)
        valid_citations.add((filename, str(chunk_index)))
    
    # Check each cited pair
    for filename, chunk_idx in citations_in_answer:
        if (filename, chunk_idx) not in valid_citations:
            violations.append("fabricated_citation")
            break
    
    # CHECK 3 — PII scrub
    pii_redacted = answer
    
    # SSN pattern: ###-##-####
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    if re.search(ssn_pattern, pii_redacted):
        pii_redacted = re.sub(ssn_pattern, "[REDACTED:SSN]", pii_redacted)
        violations.append("pii_in_output")
    
    # Account number: 8-17 digits
    account_pattern = r"\b\d{8,17}\b"
    if re.search(account_pattern, pii_redacted):
        pii_redacted = re.sub(account_pattern, "[REDACTED:ACCOUNT]", pii_redacted)
        violations.append("pii_in_output")
    
    # Credit card: ####-####-####-####
    cc_pattern = r"\b(?:\d{4}[- ]?){3}\d{4}\b"
    if re.search(cc_pattern, pii_redacted):
        pii_redacted = re.sub(cc_pattern, "[REDACTED:CC]", pii_redacted)
        violations.append("pii_in_output")
    
    # Determine pass/fail and final answer
    guardrail_result = GuardrailResult(passed=len(violations) == 0, violations=list(set(violations)))
    
    # Update guidance if violations found
    if violations:
        reviewer_guidance["answer"] = SAFE_FALLBACK_ANSWER
        reviewer_guidance["requires_human_review"] = True
    else:
        # Use the PII-redacted version (even though no violations, be safe)
        reviewer_guidance["answer"] = pii_redacted
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="output_guardrail",
        started_at=started,
        finished_at=finished,
        input_summary=f"Answer length: {len(answer)}",
        output_summary=f"Violations: {violations}, Passed: {guardrail_result.passed}",
    )
    
    guardrails_applied = []
    if violations:
        guardrails_applied.append("output_guardrail")
    
    return {
        "guardrail_result": guardrail_result.model_dump(),
        "reviewer_guidance": reviewer_guidance,
        "agent_trace": [trace_entry.model_dump()],
        "guardrails_applied": guardrails_applied,
    }
