from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.core.mcp.client import init_mcp_client, list_tools_with_schema, shutdown_mcp_client
from app.db.database import create_db_and_tables, engine
from app.db.models import LoanApplicationTable, SubmittedDocumentTable
from app.models.v2_models import LoanApplication, LoanReviewRequest, LoanReviewResponse, SubmittedDocument
from app.routes.document_routes import router as document_router
from app.workflows.langgraph_workflow import run_loan_review


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    await init_mcp_client()    # start MCP server subprocess + open session
    yield
    await shutdown_mcp_client()  # close session + terminate subprocess


app = FastAPI(title="LoanFlow AI v2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "https://huggingface.co/spaces/geetav-26",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_router)


@app.get("/")
def root():
    return {"message": "LoanFlow AI v2 is running", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tools")
async def tools():
    """List all tools registered on the MCP server with their full schemas."""
    return {"tools": await list_tools_with_schema()}


@app.get("/loans")
def list_loans():
    """Return all seeded loan applications — used by the UI scenario selector."""
    with Session(engine) as session:
        loans = session.exec(select(LoanApplicationTable)).all()
        return [
            {
                "loan_id":           l.loan_id,
                "borrower_name":     l.borrower_name,
                "loan_type":         l.loan_type,
                "loan_amount":       l.loan_amount,
                "annual_income":     l.annual_income,
                "credit_score":      l.credit_score,
                "employment_status": l.employment_status,
            }
            for l in loans
        ]


@app.get("/loans/{loan_id}")
def get_loan(loan_id: str):
    """
    Return a single loan application with its submitted documents.
    The UI uses this to auto-fill the review form when a scenario is selected.
    """
    with Session(engine) as session:
        loan = session.get(LoanApplicationTable, loan_id)
        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        docs = session.exec(
            select(SubmittedDocumentTable).where(SubmittedDocumentTable.loan_id == loan_id)
        ).all()

        return {
            "loan_id":             loan.loan_id,
            "borrower_name":       loan.borrower_name,
            "loan_type":           loan.loan_type,
            "loan_amount":         loan.loan_amount,
            "annual_income":       loan.annual_income,
            "credit_score":        loan.credit_score,
            "employment_status":   loan.employment_status,
            "submitted_documents": [
                {"doc_type": d.doc_type, "uploaded_at": d.uploaded_at.isoformat()}
                for d in docs
            ],
        }


@app.post("/review", response_model=LoanReviewResponse)
async def review(request: LoanReviewRequest):
    state = await run_loan_review(
        application=request.application.model_dump(),
        question=request.question,
    )
    guidance = state.get("reviewer_guidance") or {}
    risk = state.get("risk_assessment") or {}
    doc_check = state.get("doc_check_result") or {}

    return LoanReviewResponse(
        answer=guidance.get("answer", ""),
        requires_human_review=guidance.get("requires_human_review", True),
        missing_documents=doc_check.get("missing", []),
        risk_flags=risk.get("flags", []),
        fraud_findings=state.get("fraud_finding"),
        citations=state.get("retrieved_context", {}).get("chunks", []),
        guardrails_applied=state.get("guardrails_applied", []),
        injection_signals=state.get("injection_signals", []),
        agent_trace=state.get("agent_trace", []),
        evaluation=state.get("evaluation") or {},
    )
