"""
MCP tool implementations — 5 tools, no hardcoded business rules.

All imports are from mcp_server/ only. Zero coupling to app/.

Tools:
  1. search_policy           — semantic search over Pinecone knowledge base
  2. extract_requirements    — AI: what docs does policy require for this loan type?
  3. check_fraud_signals     — deterministic risk rules (no LLM)
  4. get_loan_application    — fetch application row from SQLite
  5. get_submitted_documents — fetch submitted docs from SQLite
"""
from sqlmodel import select

from mcp_server.db import get_session
from mcp_server.embeddings import create_embedding
from mcp_server.llm import ask_llm_json
from mcp_server.models import LoanApplicationTable, SubmittedDocumentTable
from mcp_server.vector_store import get_index


async def search_policy(query: str, top_k: int = 5) -> list[dict]:
    """
    Semantic search over the company's uploaded policy knowledge base.

    Returns chunks: [{ filename, chunk_index, score, text }, ...]
    """
    embedding = create_embedding(query)
    results = get_index().query(vector=embedding, top_k=top_k, include_metadata=True)

    chunks = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        chunks.append({
            "filename":    meta.get("filename", "unknown"),
            "chunk_index": meta.get("chunk_index", 0),
            "score":       match.get("score", 0.0),
            "text":        meta.get("text", ""),
        })
    return chunks


async def extract_requirements(loan_type: str, policy_chunks: list[dict]) -> list[str]:
    """
    Use the LLM to extract required document types from policy chunks.

    No hardcoded rules — the policy document is the source of truth.
    """
    if not policy_chunks:
        return ["id"]

    context = "\n\n".join(
        f"[Source: {c['filename']}, chunk {c['chunk_index']}]\n{c['text']}"
        for c in policy_chunks
    )

    system_prompt = (
        "You are a document requirements extractor. "
        "Read the policy excerpt and extract the list of required documents "
        f"for a {loan_type} loan application. "
        "Return ONLY a JSON object in this exact format:\n"
        '{"required_documents": ["doc_type_1", "doc_type_2"]}\n'
        "Valid doc_type values: "
        "pay_stub, bank_statement, tax_return, id, employment_letter, property_appraisal. "
        "If the policy does not specify, return {\"required_documents\": [\"id\"]}."
    )

    user_prompt = (
        f"Policy excerpt:\n{context}\n\n"
        f"What documents are required for a {loan_type} loan?"
    )

    result = await ask_llm_json(system_prompt, user_prompt)
    return result.get("required_documents", ["id"])


async def check_fraud_signals(
    loan_amount: float,
    annual_income: float,
    employment_status: str = "",
    credit_score: int = 700,
) -> dict:
    """
    Deterministic fraud signal detection based on bank risk thresholds.

    Returns: { signals: [...], confidence: 0.0–0.9 }
    """
    signals = []
    confidence = 0.0

    if annual_income == 0:
        signals.append("zero_income")
        confidence += 0.3
    elif loan_amount / annual_income > 5:
        signals.append("income_ratio_anomaly")
        confidence += 0.3

    if credit_score < 600 and loan_amount > 100_000:
        signals.append("low_credit_high_amount")
        confidence += 0.3

    if employment_status == "self_employed" and loan_amount > 200_000:
        signals.append("self_employed_high_loan")
        confidence += 0.3

    return {"signals": signals, "confidence": min(confidence, 0.9)}


async def get_loan_application(loan_id: str) -> dict:
    """Fetch one loan application from SQLite by loan_id."""
    with get_session() as session:
        row = session.get(LoanApplicationTable, loan_id)
        if row is None:
            raise ValueError(f"Loan application '{loan_id}' not found.")
        return {
            "loan_id":           row.loan_id,
            "borrower_name":     row.borrower_name,
            "loan_type":         row.loan_type,
            "loan_amount":       row.loan_amount,
            "annual_income":     row.annual_income,
            "credit_score":      row.credit_score,
            "employment_status": row.employment_status,
            "created_at":        row.created_at.isoformat() if row.created_at else None,
        }


async def get_submitted_documents(loan_id: str) -> list[dict]:
    """Fetch all submitted documents for a loan application."""
    with get_session() as session:
        rows = session.exec(
            select(SubmittedDocumentTable).where(
                SubmittedDocumentTable.loan_id == loan_id
            )
        ).all()
        return [
            {
                "doc_type":    row.doc_type,
                "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
            }
            for row in rows
        ]
