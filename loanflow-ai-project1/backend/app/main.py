from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.schemas.loan_schemas import LoanReviewRequest, LoanReviewResponse
from app.services.loan_review_service import review_loan

app = FastAPI(
    title="LoanFlow AI Capstone",
    description="LangGraph-powered loan review assistant with guardrails and evaluation.",
    version="0.1.0",
)

# CORS allows React/Vite frontend on localhost:5173 to call FastAPI on localhost:8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"service": "loanflow-ai", "status": "ok"}


@app.post("/agent/review", response_model=LoanReviewResponse)
async def agent_review(request: LoanReviewRequest):
    """Main demo endpoint called by the React UI."""

    return await review_loan(request)
