"""
InputGuardrail — first node in the LangGraph workflow (USE_CASES.md §7).

Runs BEFORE any LLM call. Its job is to make the user's question safe
to pass downstream. Three defenses, in this order:
  1. Length cap   — reject if question > 2000 chars
  2. PII redaction — regex-replace SSN / account numbers / credit card numbers
  3. Injection detection — flag (don't block) known attack patterns

Returns SanitizedInput. Downstream agents receive the sanitized question,
never the raw one.
"""
import re
from datetime import datetime, timezone
from app.models.v2_models import SanitizedInput, TraceEntry
from app.workflows.state import LoanReviewState


async def input_guardrail_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node function. Reads state["raw_question"]; writes sanitized_input.
    """
    started = datetime.now(timezone.utc)
    raw_question = state.get("raw_question", "")
    
    # STEP 1 — Length cap
    if len(raw_question) > 2000:
        raise ValueError("Question exceeds 2000 character limit.")
    
    # STEP 2 — PII redaction
    redactions = []
    cleaned_question = raw_question
    
    # SSN pattern: ###-##-####
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    if re.search(ssn_pattern, cleaned_question):
        cleaned_question = re.sub(ssn_pattern, "[REDACTED:SSN]", cleaned_question)
        redactions.append("SSN")
    
    # Account number: 8-17 digits
    account_pattern = r"\b\d{8,17}\b"
    if re.search(account_pattern, cleaned_question):
        cleaned_question = re.sub(account_pattern, "[REDACTED:ACCOUNT]", cleaned_question)
        redactions.append("ACCOUNT")
    
    # Credit card: ####-####-####-#### or similar
    cc_pattern = r"\b(?:\d{4}[- ]?){3}\d{4}\b"
    if re.search(cc_pattern, cleaned_question):
        cleaned_question = re.sub(cc_pattern, "[REDACTED:CC]", cleaned_question)
        redactions.append("CC")
    
    # STEP 3 — Injection detection
    injection_signals = []
    question_lower = cleaned_question.lower()
    
    denylist = [
        "ignore previous instructions",
        "ignore all instructions",
        "you are now",
        "system:",
        "new role:",
        "act as",
        "disregard",
    ]
    
    for phrase in denylist:
        if phrase in question_lower:
            injection_signals.append(phrase)
    
    # STEP 4 — Delimiter wrap
    sanitized_question = (
        "<<<USER_QUESTION>>>\n"
        + cleaned_question +
        "\n<<<END_USER_QUESTION>>>"
    )
    
    sanitized_input = SanitizedInput(
        question=sanitized_question,
        redactions=redactions,
        injection_signals=injection_signals,
    )
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="input_guardrail",
        started_at=started,
        finished_at=finished,
        input_summary=f"Question length: {len(raw_question)}",
        output_summary=f"Redactions: {redactions}, Injection signals: {injection_signals}",
    )
    
    guardrails_applied = []
    if redactions or injection_signals:
        guardrails_applied.append("input_guardrail")
    
    return {
        "sanitized_input": sanitized_input.model_dump(),
        "injection_signals": injection_signals,
        "agent_trace": [trace_entry.model_dump()],
        "guardrails_applied": guardrails_applied,
    }
