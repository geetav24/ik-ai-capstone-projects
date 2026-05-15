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
from datetime import datetime, timezone
from app.llm_client import ask_llm_json
from app.models.v2_models import Evaluation, TraceEntry
from app.workflows.state import LoanReviewState


async def evaluation_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads all state; writes evaluation.
    """
    started = datetime.now(timezone.utc)
    
    # STEP 1 — Build the judge prompt
    reviewer_guidance = state.get("reviewer_guidance", {})
    answer = reviewer_guidance.get("answer", "")
    
    # Build retrieved context summary (first 200 chars each)
    retrieved_context = state.get("retrieved_context", {})
    chunks = retrieved_context.get("chunks", [])
    
    context_summary = ""
    for chunk in chunks:
        text = chunk.get("text", "")[:200]
        context_summary += f"- {chunk.get('filename')}: {text}...\n"
    
    # Build risk flags summary
    risk_assessment = state.get("risk_assessment", {})
    flags = risk_assessment.get("flags", [])
    risk_summary = ", ".join([f.get("flag_type", "unknown") for f in flags]) if flags else "None"
    
    system_prompt = """You are an expert loan review evaluator. Your job is to assess the quality 
of guidance provided to a loan reviewer. Return ONLY valid JSON in the exact format specified."""
    
    user_prompt = f"""Evaluate this loan review guidance:

GUIDANCE PROVIDED:
{answer}

POLICY CONTEXT AVAILABLE:
{context_summary}

RISK FLAGS IDENTIFIED:
{risk_summary}

Please score on these dimensions:
1. decision_quality: Is the guidance useful and actionable for the reviewer?
2. grounding_score: What percentage of claims are backed by policy context? (0.0-1.0)
3. hallucination_risk: Does the answer make unsupported claims? (low/medium/high)
4. policy_compliance: Does the guidance stay within policy scope? (pass/fail/partial)

IMPORTANT: Return ONLY this JSON structure, no other text:
{{
  "decision_quality": "pass" | "fail" | "partial",
  "grounding_score": 0.0-1.0,
  "hallucination_risk": "low" | "medium" | "high",
  "policy_compliance": "pass" | "fail" | "partial",
  "reasoning": "brief one-sentence explanation"
}}"""
    
    # STEP 2 — Call LLM with JSON parsing
    parsed = await ask_llm_json(system_prompt, user_prompt, fast=False)
    
    # STEP 3 — Validate and fill missing keys
    evaluation_data = {
        "decision_quality": parsed.get("decision_quality", "unknown"),
        "grounding_score": float(parsed.get("grounding_score", 0.0)),
        "hallucination_risk": parsed.get("hallucination_risk", "unknown"),
        "policy_compliance": parsed.get("policy_compliance", "unknown"),
        "reasoning": parsed.get("reasoning", "No reasoning provided"),
    }
    
    evaluation = Evaluation(**evaluation_data)
    
    # STEP 4 — Return
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="evaluation",
        started_at=started,
        finished_at=finished,
        input_summary=f"Answer length: {len(answer)}, Risk flags: {risk_summary}",
        output_summary=f"Quality: {evaluation.decision_quality}, Grounding: {evaluation.grounding_score:.2f}",
    )
    
    return {
        "evaluation": evaluation.model_dump(),
        "agent_trace": [trace_entry.model_dump()],
    }
