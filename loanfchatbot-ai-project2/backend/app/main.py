"""
LoanInquiry AI — FastAPI backend.

Endpoints:
  POST /chat          — v1 single-agent (preserved for backwards compat)
  POST /v2/chat       — v2 multi-agent Google ADK pipeline
  DELETE /chat/{sid}  — clear session memory
  GET  /sessions      — list active sessions
  GET  /health        — health check
"""
import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.models.models import (
    AgentTraceEntry,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    V2ChatRequest,
    V2ChatResponse,
)
from app.agent.loan_inquiry_agent import run_inquiry
from app.agents.input_guardrail import input_guardrail_agent
from app.core.session_store import delete, get_or_create, list_sessions
from app.workflows.adk_workflow import run_adk_inquiry


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="LoanInquiry AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "LoanInquiry AI", "version": "2.0"}


# ---------------------------------------------------------------------------
# v1 — single-agent endpoint (preserved)
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    return await run_inquiry(request)


# ---------------------------------------------------------------------------
# v2 — multi-agent Google ADK endpoint
# ---------------------------------------------------------------------------

@app.post("/v2/chat", response_model=V2ChatResponse)
async def chat_v2(request: V2ChatRequest):
    """
    Two-phase pipeline:

    Phase 1 — InputGuardrailAgent (our code, runs before ADK):
      Redacts PII, detects injection, wraps message in delimiters.
      On length violation: returns HTTP 400 immediately.

    Phase 2 — Google ADK triage pipeline:
      triage_agent reads sub_agent descriptions and routes to:
        policy_agent | status_agent | web_search_agent | eligibility_agent
      The chosen specialist calls its tool, then triage synthesizes the answer.

    ADK manages its own session turns internally (InMemorySessionService).
    We also update our session_store so memory_snapshot is available.
    """
    # --- Phase 1: guardrail (explicit code — easy to demo and audit)
    guardrail_start = datetime.now(timezone.utc)
    try:
        guardrail_result = await input_guardrail_agent({"raw_message": request.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    injection_signals = guardrail_result.get("injection_signals") or []
    redactions        = guardrail_result.get("redactions") or []
    sanitized_message = guardrail_result.get("sanitized_message", request.message)
    guardrail_trace   = guardrail_result.get("agent_trace") or []

    # Hard-stop on injection: return a safe refusal without hitting the LLM
    if injection_signals:
        return V2ChatResponse(
            session_id=request.session_id,
            answer="I'm sorry, I can't process that request.",
            intent="blocked",
            specialists_called=[],
            injection_signals=injection_signals,
            redactions=redactions,
            agent_trace=[AgentTraceEntry(**t) for t in guardrail_trace if isinstance(t, dict)],
            memory_snapshot=[],
        )

    # --- Phase 2: ADK pipeline (routing + specialist + synthesis)
    try:
        answer = await run_adk_inquiry(
            session_id=request.session_id,
            sanitized_message=sanitized_message,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ADK pipeline error: {e}")

    # --- Update our session memory (for memory_snapshot in response)
    memory = get_or_create(request.session_id, request.memory_type)
    if inspect.iscoroutinefunction(memory.add):
        await memory.add("user", request.message)
        await memory.add("assistant", answer)
    else:
        memory.add("user", request.message)
        memory.add("assistant", answer)

    raw_messages = memory.get_messages()[-6:]
    memory_snapshot = [
        ChatMessage(role=m.role, content=m.content)
        for m in raw_messages
        if hasattr(m, "role") and hasattr(m, "content")
    ]

    # ADK handles routing internally — intent and specialists_called are not
    # surfaced by ADK's public API.  We report what we know from the guardrail.
    # TODO: use ADK event metadata or add a custom callback to extract these
    #       values if you need them in the response for the trace UI.
    return V2ChatResponse(
        session_id=request.session_id,
        answer=answer,
        intent="unknown",           # ADK routing is internal; see TODO above
        specialists_called=[],      # ADK routing is internal; see TODO above
        injection_signals=injection_signals,
        redactions=redactions,
        agent_trace=[AgentTraceEntry(**t) for t in guardrail_trace if isinstance(t, dict)],
        memory_snapshot=memory_snapshot,
    )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@app.delete("/chat/{session_id}")
def clear_session(session_id: str):
    delete(session_id)
    return {"cleared": session_id}


@app.get("/sessions")
def sessions():
    return {"active_sessions": list_sessions()}
