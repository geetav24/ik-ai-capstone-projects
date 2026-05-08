from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.loan_models import LoanReviewRequest, LoanReviewResponse
from app.services.loan_review_service import review_loan
from dotenv import load_dotenv
from app.routes.document_routes import router as document_router

load_dotenv()
app = FastAPI(title="LoanFlow AI - Project 1")
# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://loanflow-app.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agent/review", response_model=LoanReviewResponse)
async def agent_review(request: LoanReviewRequest):   
    return await review_loan(request)