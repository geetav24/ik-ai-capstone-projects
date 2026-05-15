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
from datetime import datetime
from typing import Any

from app.llm_client import ask_llm_json
from app.models.v2_models import Evaluation, TraceEntry
from app.workflows.state import LoanReviewState


async def evaluation_agent(state: LoanReviewState) -> dict:
    """
    LLM-as-Judge evaluator (guidance-only).

    - Builds a concise judge prompt containing the final answer, first-200-char
      snippets of retrieved policy chunks, and risk flag names.
    - Calls `ask_llm_json(..., fast=False)` to get structured JSON.
    - Fills missing keys with safe defaults.
    - Returns `evaluation` and an `agent_trace`.
    """
    started_at = datetime.utcnow()

    # Extract the final answer (fall back to empty string)
    reviewer_guidance = state.get("reviewer_guidance") or {}
    final_answer = reviewer_guidance.get("answer", "")

    # Retrieved context: include abbreviated chunks (first 200 chars)
    retrieved = state.get("retrieved_context") or {}
    chunks = retrieved.get("chunks", []) if retrieved is not None else []
    abbreviated = []
    for c in chunks:
        filename = c.get("filename", "unknown")
        idx = c.get("chunk_index", 0)
        text = c.get("text", "") or ""
        snippet = text[:200].replace("\n", " ")
        abbreviated.append(f"[Source: {filename}, chunk {idx}] {snippet}")

    retrieved_str = "\n".join(abbreviated) or "(no retrieved context provided)"

    # Risk flags: names only
    risk_assessment = state.get("risk_assessment") or {}
    flags = risk_assessment.get("flags", []) if risk_assessment is not None else []
    flag_names = [f.get("flag_type") for f in flags]

    # Build fraud signals string for the judge
    fraud = state.get("fraud_finding") or {}
    fraud_signals = fraud.get("signals", []) if fraud else []

    # Build system and user prompts
    system_prompt = (
        "You are an automated evaluator scoring a loan review assistant's guidance.\n"
        "Return ONLY valid JSON matching the schema in the user prompt.\n"
        "Be concise in the `reasoning` field (one sentence).\n\n"
        "IMPORTANT grounding rules:\n"
        "1. Risk flags and fraud signals listed below come from a DETERMINISTIC rule engine — "
        "they are factual, not hallucinated. If the answer correctly references them, count that as grounded.\n"
        "2. grounding_score should reflect how well the answer is backed by EITHER policy citations "
        "OR deterministic rule findings. An answer that correctly surfaces risk flags without policy "
        "chunks is partially grounded, not zero-grounded.\n"
        "3. Only penalise hallucination_risk when the answer makes claims NOT supported by the "
        "policy snippets, risk flags, or fraud signals provided.\n"
    )

    user_prompt = (
        "Evaluate the assistant's final answer below.\n\n"
        "Final answer:\n"
        "----BEGIN ANSWER----\n"
        f"{final_answer}\n"
        "----END ANSWER----\n\n"
        "Retrieved policy snippets (first 200 chars each):\n"
        f"{retrieved_str}\n\n"
        "Deterministic risk flags (rule-engine output — factual):\n"
        f"{', '.join(flag_names) if flag_names else 'none'}\n\n"
        "Deterministic fraud signals (rule-engine output — factual):\n"
        f"{', '.join(fraud_signals) if fraud_signals else 'none'}\n\n"
        "Return ONLY valid JSON in this exact schema:\n"
        "{\n"
        '  "decision_quality": "pass" | "fail" | "partial",\n'
        '  "grounding_score": 0.0,  // 0.0-1.0: reflects grounding in policy OR deterministic rules\n'
        '  "hallucination_risk": "low" | "medium" | "high",\n'
        '  "policy_compliance": "pass" | "fail" | "partial",\n'
        '  "reasoning": "one-sentence explanation"\n'
        "}\n"
    )

    # Ask high-quality LLM and parse JSON
    try:
        parsed = await ask_llm_json(system_prompt, user_prompt, fast=False)
    except Exception as e:
        # If LLM returned non-JSON or parsing failed, fall back to safe defaults.
        parsed = {
            "decision_quality": "unknown",
            "grounding_score": 0.0,
            "hallucination_risk": "unknown",
            "policy_compliance": "unknown",
            "reasoning": f"LLM call failed or returned non-JSON: {str(e)[:200]}",
        }

    # Ensure required keys exist and have safe types/values
    def _safe_str(key: str, default: str = "unknown") -> str:
        v = parsed.get(key)
        return v if isinstance(v, str) else default

    def _safe_float(key: str, default: float = 0.0) -> float:
        v = parsed.get(key)
        try:
            return float(v)
        except Exception:
            return default

    decision_quality = _safe_str("decision_quality", "unknown")
    grounding_score = _safe_float("grounding_score", 0.0)
    hallucination_risk = _safe_str("hallucination_risk", "unknown")
    policy_compliance = _safe_str("policy_compliance", "unknown")
    reasoning = _safe_str("reasoning", "")

    evaluation = Evaluation(
        decision_quality=decision_quality,
        grounding_score=grounding_score,
        hallucination_risk=hallucination_risk,
        policy_compliance=policy_compliance,
        reasoning=reasoning,
    ).model_dump()

    finished_at = datetime.utcnow()
    input_summary = (
        f"answer_len={len(final_answer)};retrieved_chunks={len(chunks)};risk_flags={len(flag_names)}"
    )
    output_summary = f"decision_quality={decision_quality};grounding={grounding_score}"

    trace_entry = TraceEntry(
        agent="evaluation",
        started_at=started_at,
        finished_at=finished_at,
        input_summary=input_summary,
        output_summary=output_summary,
    ).model_dump()

    return {
        "evaluation": evaluation,
        "agent_trace": [trace_entry],
    }
