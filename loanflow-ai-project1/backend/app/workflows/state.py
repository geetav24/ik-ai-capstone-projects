from typing import TypedDict, List, Dict, Any


class LoanReviewState(TypedDict, total=False):
    """State object passed between LangGraph nodes.

    Each agent reads from and writes to this shared state. Keeping the state
    explicit makes the workflow easy to debug and present.
    """

    loan_id: str
    borrower_name: str
    loan_amount: float
    annual_income: float
    credit_score: int
    question: str

    missing_documents: List[str]
    risk_flags: List[str]
    guardrails_applied: List[str]
    requires_human_review: bool
    answer: str
    raw_llm_notes: str
    agent_trace: List[Dict[str, str]]
    evaluation: Dict[str, Any]
