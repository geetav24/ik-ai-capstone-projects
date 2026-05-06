from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class LoanReviewRequest(BaseModel):
    """Request from the React UI.

    Keep it simple for the MVP. Later, you can add uploaded documents,
    debt-to-income ratio, employment history, collateral, or loan purpose.
    """

    loan_id: str = Field(..., examples=["LN-1001"])
    borrower_name: str = Field(..., examples=["Jane Smith"])
    loan_amount: float = Field(..., examples=[250000])
    annual_income: float = Field(..., examples=[95000])
    credit_score: int = Field(..., examples=[680])
    question: str = Field(..., examples=["Borrower is missing bank statements. What should reviewer check?"])


class AgentTrace(BaseModel):
    """Simple trace so you can explain what each agent did in the demo."""

    agent: str
    summary: str


class EvaluationResult(BaseModel):
    """Rule-based evaluation now. Later add LLM-as-judge fields."""

    score: int
    passed: bool
    checks: Dict[str, bool]
    feedback: List[str]


class LoanReviewResponse(BaseModel):
    loan_id: str
    borrower_name: str
    answer: str
    missing_documents: List[str]
    risk_flags: List[str]
    requires_human_review: bool
    guardrails_applied: List[str]
    agent_trace: List[AgentTrace]
    evaluation: Optional[EvaluationResult] = None
    raw_llm_notes: Optional[str] = None
