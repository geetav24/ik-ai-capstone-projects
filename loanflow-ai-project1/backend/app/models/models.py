"""
LoanFlow data contracts. These are the authoritative types for the entire system.
Agents read and write these. The API exposes them. The UI consumes them.
If two files disagree on what a RiskFlag looks like, fix one of them.
"""
from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Domain primitives
# ---------------------------------------------------------------------------

class SubmittedDocument(BaseModel):
    doc_type: Literal[
        "pay_stub", "bank_statement", "tax_return",
        "id", "employment_letter", "property_appraisal"
    ]
    uploaded_at: datetime
    parsed_fields: Optional[dict] = None


class LoanApplication(BaseModel):
    loan_id: str
    borrower_name: str
    loan_type: Literal["personal", "mortgage", "auto", "business"]
    loan_amount: Decimal
    annual_income: Decimal
    credit_score: int = Field(ge=300, le=850)
    employment_status: Literal["employed", "self_employed", "unemployed", "retired"]
    submitted_documents: list[SubmittedDocument] = []


class LoanReviewRequest(BaseModel):
    application: LoanApplication
    question: str = Field(
        max_length=2000,
        description="Raw reviewer question. Max 2000 chars — enforced by InputGuardrail.",
    )


# ---------------------------------------------------------------------------
# Shared result types used by multiple agents
# ---------------------------------------------------------------------------

class RiskFlag(BaseModel):
    flag_type: str
    severity: Literal["low", "medium", "high", "critical"]
    detail: str


class Citation(BaseModel):
    filename: str
    chunk_index: int
    score: float
    text: str


class TraceEntry(BaseModel):
    agent: str
    started_at: datetime
    finished_at: datetime
    input_summary: str
    output_summary: str


class FraudFinding(BaseModel):
    signals: list[str] = []
    confidence: float = 0.0


class Evaluation(BaseModel):
    decision_quality: str
    grounding_score: float
    hallucination_risk: str
    policy_compliance: str
    reasoning: str


# ---------------------------------------------------------------------------
# Per-agent output types (one per agent in §4)
# ---------------------------------------------------------------------------

class SanitizedInput(BaseModel):
    """Output of InputGuardrail."""
    question: str
    redactions: list[str] = []
    injection_signals: list[str] = []


class Plan(BaseModel):
    """Output of PlannerAgent. Decides which specialists run."""
    specialists_to_run: list[str]
    rationale: str


class RetrievedContext(BaseModel):
    """Output of RetrievalAgent."""
    chunks: list[Citation] = []


class DocCheckResult(BaseModel):
    """Output of DocumentCheckAgent."""
    missing: list[str] = []
    present: list[str] = []
    required_by_policy: list[str] = []


class RiskAssessment(BaseModel):
    """Output of RiskReviewAgent."""
    flags: list[RiskFlag] = []
    severity: Literal["low", "medium", "high", "critical"] = "low"


class ReviewerGuidance(BaseModel):
    """Output of ReviewerAgent."""
    answer: str
    requires_human_review: bool


class GuardrailResult(BaseModel):
    """Output of OutputGuardrail."""
    passed: bool
    violations: list[str] = []


# ---------------------------------------------------------------------------
# Final API response
# ---------------------------------------------------------------------------

class LoanReviewResponse(BaseModel):
    answer: str
    requires_human_review: bool
    missing_documents: list[str] = []
    risk_flags: list[RiskFlag] = []
    fraud_findings: Optional[FraudFinding] = None
    citations: list[Citation] = []
    guardrails_applied: list[str] = []
    injection_signals: list[str] = []
    agent_trace: list[TraceEntry] = []
    evaluation: Evaluation
