from pydantic import BaseModel, Field
from typing import List

class LoanReviewRequest(BaseModel):
    loan_id: str = Field(..., examples=["LN-1001"])
    borrower_name: str = Field(..., examples=["Jane Smith"])
    loan_amount: float = Field(..., examples=[250000])
    annual_income: float = Field(..., examples=[95000])
    credit_score: int = Field(..., examples=[680])
    question: str = Field(..., examples=["Borrower is missing bank statements. What should reviewer check?"])


class Evaluation(BaseModel):
    decision_quality: str
    reasoning: str
    hallucination_risk: str
    policy_compliance: str
    grounding_score: float
    
class Citation(BaseModel):
    filename: str
    chunk_index: int
    score: float


class RetrievedContext(BaseModel):
    filename: str
    chunk_index: int
    score: float
    text: str

class LoanReviewResponse(BaseModel):
    loan_id: str
    borrower_name: str 
    loan_amount: float 
    annual_income: float
    credit_score: float
    answer: str
    missingDocuments: List[str]
    riskFlags: List[str]
    requiresHumanReview: bool
    guardrailsApplied: List[str]
    agentTrace: List[str]
    evaluation: Evaluation
    citations: List[Citation]
    retrievedContext: List[RetrievedContext]