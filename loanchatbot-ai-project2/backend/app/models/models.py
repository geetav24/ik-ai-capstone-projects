"""
LoanInquiry data contracts — used by /v2/chat (Google ADK pipeline).
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = None


class LoanStatus(BaseModel):
    loan_id: str
    borrower_name: str
    loan_type: str
    loan_amount: float
    status: str = "under_review"
    credit_score: int
    annual_income: float
    employment_status: str


class PolicyChunk(BaseModel):
    filename: str
    chunk_index: int
    score: float
    text: str


class WebResult(BaseModel):
    title: str
    url: str
    content: str


# ---------------------------------------------------------------------------
# v2 — multi-agent ADK contracts
# ---------------------------------------------------------------------------

IntentType = Literal["policy", "status", "web", "eligibility", "general"]


class AgentTraceEntry(BaseModel):
    """Audit record for one agent node execution."""
    agent: str
    started_at: datetime
    finished_at: datetime
    input_summary: str
    output_summary: str


class InquiryState(TypedDict, total=False):
    """
    LangGraph state shared across all nodes in the v2 pipeline.

    Fields are written by individual agents and read by downstream agents.
    All fields are optional (total=False) so nodes only touch what they own.
    """
    # --- input (set by API handler before graph runs)
    session_id: str
    raw_message: str
    memory_type: str                    # "buffer" | "summary"

    # --- set by InputGuardrailAgent
    sanitized_message: str
    injection_signals: list[str]
    redactions: list[str]

    # --- set by IntentRouterAgent
    intent: str                         # IntentType value
    loan_id_hint: str | None            # extracted loan ID if intent=="status"
    specialists_to_run: list[str]       # subset of: policy, status, web, eligibility

    # --- set by specialist agents
    policy_chunks: list[dict]           # PolicyChunk dicts
    loan_status: dict | None            # LoanStatus dict or None
    web_results: list[dict]             # WebResult dicts
    eligibility_result: dict | None     # EligibilityResult dict or None

    # --- set by SynthesisAgent
    final_answer: str

    # --- accumulated by all agents (append-only)
    agent_trace: list[dict]             # AgentTraceEntry dicts
    specialists_called: list[str]       # names of agents that actually ran

    # --- set by API handler after graph completes
    memory_snapshot: list[dict]         # last N ChatMessage dicts


class V2ChatRequest(BaseModel):
    session_id: str
    message: str
    memory_type: Literal["buffer", "summary"] = "buffer"


class V2ChatResponse(BaseModel):
    session_id: str
    answer: str
    intent: str = "general"
    specialists_called: list[str] = []
    injection_signals: list[str] = []
    redactions: list[str] = []
    agent_trace: list[AgentTraceEntry] = []
    memory_snapshot: list[ChatMessage] = []
