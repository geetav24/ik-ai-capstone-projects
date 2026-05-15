from fastapi import APIRouter
from app.models.loan_models import LoanReviewRequest
from app.models.loan_models import LoanReviewResponse
from app.services.loan_review_service import review_loan


router = APIRouter()

@router.post("/agent/review")
def review_loas(request: LoanReviewRequest):
    return review_loan(request)
