"""
Loan Status Tool — fetch loan application data from SQLite.

Points at the same loanflow.db used by Project 1.
DB_PATH env var overrides the default.
"""
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.models.models import LoanStatus

_DEFAULT_DB = (
    Path(__file__).resolve().parents[4]
    / "loanflow-ai-project1"
    / "backend"
    / "loanflow.db"
)


def _db_path() -> str:
    return os.getenv("DB_PATH", str(_DEFAULT_DB))


async def get_loan_status(loan_id: str) -> LoanStatus | None:
    """
    Fetch a loan application by ID.

    Args:
        loan_id: e.g. "LN-001"

    Returns:
        LoanStatus if found, None if not found
    """
    path = _db_path()
    if not Path(path).exists():
        raise FileNotFoundError(f"Database not found at {path}. Set DB_PATH env var.")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT * FROM loan_applications WHERE loan_id = ?",
            (loan_id.upper(),),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    r = dict(row)
    return LoanStatus(
        loan_id=r["loan_id"],
        borrower_name=r["borrower_name"],
        loan_type=r["loan_type"],
        loan_amount=float(r["loan_amount"]),
        status=r.get("status") or "under_review",
        credit_score=int(r["credit_score"]),
        annual_income=float(r["annual_income"]),
        employment_status=r["employment_status"],
    )
