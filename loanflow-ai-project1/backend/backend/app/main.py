from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.loan_models import LoanReviewRequest, LoanReviewResponse
from app.services.loan_review_service import review_loan

app = FastAPI(title="LoanFlow AI - Project 1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agent/review", response_model=LoanReviewResponse)
async def agent_review(request: LoanReviewRequest):   
    return await review_loan(request.loan_id,request.question)