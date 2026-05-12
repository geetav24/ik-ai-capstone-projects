"""
ReviewerAgent — synthesizes guidance grounded in policy + specialist findings.

This is the only agent the human reviewer directly reads. It must:
  1. Stay grounded in retrieved policy chunks (cite them).
  2. Never approve or reject the loan — guidance only.
  3. Use the quality LLM (gpt-4o), not the fast one.
  4. Surface all upstream signals (risk flags, fraud findings, missing docs).

This agent receives the most context of any node in the graph.
Its prompt design is where most of the "AI" quality lives.
"""
from datetime import datetime, timezone
from app.llm_client import ask_llm_quality
from app.models.v2_models import ReviewerGuidance, TraceEntry
from app.workflows.state import LoanReviewState


async def reviewer_agent(state: LoanReviewState) -> dict:
    """
    LangGraph node. Reads all upstream state; writes reviewer_guidance.
    """
    started = datetime.now(timezone.utc)
    
    # STEP 1 — Build context string from retrieved_context chunks
    retrieved_context = state.get("retrieved_context", {})
    chunks = retrieved_context.get("chunks", [])
    
    context_str = ""
    for chunk in chunks:
        context_str += f"[Source: {chunk.get('filename', 'unknown')}, chunk {chunk.get('chunk_index', 0)}]\n"
        context_str += f"{chunk.get('text', '')}\n\n"
    
    # STEP 2 — Build system prompt
    system_prompt = """You are a careful loan review assistant helping a human reviewer.

CRITICAL RULES:
1. Never approve or reject a loan. Only provide guidance.
2. Ground every claim in the policy context provided below.
3. If something is not in the retrieved policy, say so explicitly.

You will provide careful, grounded guidance to help the reviewer make an informed decision."""
    
    # STEP 3 — Build user prompt with all context
    app = state.get("application", {})
    risk_assessment = state.get("risk_assessment", {})
    fraud_finding = state.get("fraud_finding")
    doc_check_result = state.get("doc_check_result", {})
    sanitized_input = state.get("sanitized_input", {})
    question = sanitized_input.get("question", "")
    
    upstream_signals = []
    
    # Risk flags
    risk_flags = risk_assessment.get("flags", [])
    for flag in risk_flags:
        upstream_signals.append(f"Risk: {flag.get('flag_type')} ({flag.get('severity')})")
    
    # Fraud findings
    if fraud_finding:
        signals = fraud_finding.get("signals", [])
        confidence = fraud_finding.get("confidence", 0.0)
        upstream_signals.append(f"Fraud signals: {signals} (confidence: {confidence:.2f})")
    
    # Missing documents
    missing_docs = doc_check_result.get("missing", [])
    if missing_docs:
        upstream_signals.append(f"Missing documents: {missing_docs}")
    
    signals_section = "\n".join(upstream_signals) if upstream_signals else "No risk signals."
    
    user_prompt = f"""Application Summary:
- Loan ID: {app.get('loan_id')}
- Borrower: {app.get('borrower_name')}
- Loan Type: {app.get('loan_type')}
- Amount: ${app.get('loan_amount')}
- Annual Income: ${app.get('annual_income')}
- Credit Score: {app.get('credit_score')}

Upstream Signals:
{signals_section}

Retrieved Policy Guidance:
{context_str}

Reviewer's Question:
{question}

Please provide careful, policy-grounded guidance to help the reviewer evaluate this application."""
    
    # STEP 4 — Call LLM
    answer = await ask_llm_quality(system_prompt, user_prompt)
    
    # STEP 5 — Set requires_human_review
    requires_human_review = False
    
    if risk_assessment:
        severity = risk_assessment.get("severity", "low")
        if severity in ["critical", "high"]:
            requires_human_review = True
    
    if fraud_finding and fraud_finding.get("signals"):
        requires_human_review = True
    
    if missing_docs:
        requires_human_review = True
    
    reviewer_guidance = ReviewerGuidance(
        answer=answer,
        requires_human_review=requires_human_review,
    )
    
    finished = datetime.now(timezone.utc)
    trace_entry = TraceEntry(
        agent="reviewer",
        started_at=started,
        finished_at=finished,
        input_summary=f"Loan {app.get('loan_id')}, {len(chunks)} policy chunks",
        output_summary=f"Answer length: {len(answer)}, requires_human_review: {requires_human_review}",
    )
    
    return {
        "reviewer_guidance": reviewer_guidance.model_dump(),
        "agent_trace": [trace_entry.model_dump()],
    }
