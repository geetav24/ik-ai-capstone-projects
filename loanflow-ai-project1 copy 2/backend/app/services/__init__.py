from pydantic import BaseModel
from typing import List

class LoanReviewRequest(BaseModel):
    loan_id: str
    question: str

class LoanReviewResponse(BaseModel):
    loanId: str
    answer: str
    missingDocuments: List[str]
    riskFlags: List[str]
    requiresHumanReview: bool
    guardrailsApplied: List[str]