"""
SQLModel table definitions for the MCP server's DB access.

These mirror app/db/models.py — both point to the same SQLite file.
Defined separately so mcp_server/ has zero imports from app/.

In a production system with PostgreSQL, both packages would share a
db-models library. For this project, duplication is intentional.
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class LoanApplicationTable(SQLModel, table=True):
    __tablename__ = "loan_applications"

    loan_id: str = Field(primary_key=True)
    borrower_name: str
    loan_type: str
    loan_amount: float
    annual_income: float
    credit_score: int
    employment_status: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SubmittedDocumentTable(SQLModel, table=True):
    __tablename__ = "submitted_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    loan_id: str = Field(foreign_key="loan_applications.loan_id")
    doc_type: str
    uploaded_at: datetime
    parsed_fields: Optional[str] = None
