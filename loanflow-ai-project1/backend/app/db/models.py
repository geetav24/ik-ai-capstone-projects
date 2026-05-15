"""
SQLModel table definitions (§6a of USE_CASES.md).

The same class is both a Pydantic model and a DB row when table=True.
JSON columns store evolving payloads so we avoid migration churn during the build.

Three tables:
  loan_applications   — one row per loan application
  submitted_documents — one row per document attached to an application
  review_records      — one row per /review call (full pipeline output)
"""
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class LoanApplicationTable(SQLModel, table=True):
    __tablename__ = "loan_applications"

    loan_id: str = Field(primary_key=True)
    borrower_name: str
    loan_type: str                # "personal" | "mortgage" | "auto" | "business"
    loan_amount: float
    annual_income: float
    credit_score: int
    employment_status: str        # "employed" | "self_employed" | "unemployed" | "retired"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SubmittedDocumentTable(SQLModel, table=True):
    __tablename__ = "submitted_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: str = Field(foreign_key="loan_applications.loan_id")
    doc_type: str                 # "pay_stub" | "bank_statement" | "tax_return" | "id" | ...
    uploaded_at: datetime
    parsed_fields: Optional[str] = None   # JSON string; None until doc extraction is built


class ReviewRecordTable(SQLModel, table=True):
    __tablename__ = "review_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: str = Field(foreign_key="loan_applications.loan_id")
    question: str
    response: Optional[str] = None          # JSON: LoanReviewResponse
    agent_trace: Optional[str] = None       # JSON: list[TraceEntry]
    evaluation: Optional[str] = None        # JSON: Evaluation
    guardrails_applied: Optional[str] = None  # JSON: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
