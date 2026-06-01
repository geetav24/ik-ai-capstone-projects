"""
LoanInquiry v2 — Google ADK multi-agent pipeline.

Replaces LangGraph with ADK's triage + sub_agents pattern.

Architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │  triage_agent  (LlmAgent — reads descriptions, routes)      │
  │   ├── policy_agent      Pinecone RAG                        │
  │   ├── status_agent      SQLite loan-status lookup           │
  │   ├── web_search_agent  Tavily web search                   │
  │   └── eligibility_agent policy-grounded loan limit calc     │
  └─────────────────────────────────────────────────────────────┘

The InputGuardrailAgent (PII + injection) runs in main.py BEFORE
this pipeline — ADK receives the sanitized message, not the raw one.

Model: LiteLlm bridges ADK to OpenAI, so no Gemini key is needed.
       OPENAI_API_KEY is read from the environment automatically.

LangGraph vs ADK in one line:
  LangGraph — you draw the edges; ADK — the LLM reads descriptions and decides.
"""
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai.types import Content, Part

from app.tools.loan_status_tool import get_loan_status
from app.tools.policy_tool import search_policy
from app.tools.web_search_tool import web_search

# ---------------------------------------------------------------------------
# Model — LiteLlm wraps any OpenAI-compatible model
# ---------------------------------------------------------------------------
# LiteLlm reads OPENAI_API_KEY from env.  Prefix "openai/" tells it which
# provider to use.  Swap to "openai/gpt-4o" here for the quality model.
_MODEL = LiteLlm(model="openai/gpt-4o-mini")

# ---------------------------------------------------------------------------
# Specialist agents
# ---------------------------------------------------------------------------

_policy_agent = LlmAgent(
    name="policy_agent",
    model=_MODEL,
    # ADK uses `description` to decide which sub_agent to call.
    # Keep it short and unambiguous — the triage LLM reads this.
    description=(
        "Answers questions about loan policy rules, required documents, "
        "credit score tiers, DTI limits, and eligibility criteria."
    ),
    # TODO: tune instruction — this is the system prompt for this specialist.
    #       Rules to enforce:
    #         1. Always call search_policy before answering.
    #         2. Cite [Source: filename, chunk N] for every claim.
    #         3. Never approve or reject a loan.
    #         4. If no relevant chunks, say so clearly.
    instruction=(
        "You are a loan policy specialist. "
        "Always call the search_policy tool before answering. "
        "Cite every policy claim using [Source: filename, chunk N]. "
        "Never invent rules. Never approve or reject a loan."
    ),
    tools=[FunctionTool(func=search_policy)],
)

_status_agent = LlmAgent(
    name="status_agent",
    model=_MODEL,
    description=(
        "Looks up the status of a specific loan application when the user "
        "mentions a loan ID such as LN-001, LN-006, etc."
    ),
    # TODO: tune instruction — handle not-found case gracefully.
    #       Tell the agent to format the result as a readable summary,
    #       not raw JSON.
    instruction=(
        "You are a loan status specialist. "
        "Extract the loan ID from the user's message and call get_loan_status. "
        "Present the result clearly. If the loan ID is not found, say so politely."
    ),
    tools=[FunctionTool(func=get_loan_status)],
)

_web_agent = LlmAgent(
    name="web_search_agent",
    model=_MODEL,
    description=(
        "Searches the web for information not in the internal policy database: "
        "government agency contacts, where to obtain documents, current interest "
        "rates, and general financial guidance."
    ),
    # TODO: tune instruction — constrain to loan-relevant queries only.
    #       Include URLs in the answer.  Limit to 3 results max.
    instruction=(
        "You are a web research specialist for loan-related questions. "
        "Call web_search with a concise query derived from the user's question. "
        "Include source URLs in your answer."
    ),
    tools=[FunctionTool(func=web_search)],
)

_eligibility_agent = LlmAgent(
    name="eligibility_agent",
    model=_MODEL,
    description=(
        "Estimates whether a user qualifies for a loan and what their maximum "
        "loan amount would be, based on their stated income, credit score, and "
        "loan type, grounded in the bank's policy rules."
    ),
    # TODO: tune instruction — must search policy FIRST to get the rules,
    #       then apply them to the user's numbers.  Be explicit that this is
    #       an estimate, not a decision.  Cite the policy sources used.
    instruction=(
        "You are a loan eligibility analyst. "
        "First call search_policy to retrieve DTI limits, credit score tiers, "
        "and LTV rules relevant to the loan type. "
        "Then apply those rules to the user's stated financials. "
        "Clearly state this is an estimate. Never approve or reject. Cite sources."
    ),
    tools=[FunctionTool(func=search_policy)],
)

# ---------------------------------------------------------------------------
# Triage (router) agent
# ---------------------------------------------------------------------------
# This is the entry point for the Runner.  It reads sub_agent descriptions
# and decides which one to hand off to, then synthesizes the final answer.

_triage_agent = LlmAgent(
    name="loan_inquiry_triage",
    model=_MODEL,
    # TODO: tune instruction — reinforce routing rules here.
    #       The LLM both routes AND synthesizes the final answer, so the
    #       instruction needs to cover both responsibilities.
    #       Key addition: tell it to pass conversation context when routing.
    instruction=(
        "You are LoanInquiry, a helpful and honest loan assistant. "
        "Route the user's question to exactly one specialist based on intent:\n"
        "  • Policy questions → policy_agent\n"
        "  • Loan ID / application status → status_agent\n"
        "  • External resources / government links → web_search_agent\n"
        "  • Loan eligibility / maximum loan amount → eligibility_agent\n"
        "After the specialist responds, produce a clear, concise final answer. "
        "Cite sources when available. Never approve or reject a loan."
    ),
    sub_agents=[_policy_agent, _status_agent, _web_agent, _eligibility_agent],
)

# ---------------------------------------------------------------------------
# Runner — created once at module level, reused across all requests
# ---------------------------------------------------------------------------
# InMemorySessionService keeps conversation turns in memory.
# Each session_id gets its own history; turns accumulate automatically.

_session_service = InMemorySessionService()

_runner = Runner(
    agent=_triage_agent,
    app_name="LoanInquiry",
    session_service=_session_service,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_adk_inquiry(session_id: str, sanitized_message: str) -> str:
    """
    Run the ADK pipeline for one chat turn.

    Accepts the SANITIZED message from InputGuardrailAgent (main.py strips
    PII and checks for injection before calling this function).

    Returns the final text answer from the triage agent.

    ADK manages its own per-session turn history internally via
    InMemorySessionService.  main.py still updates the app-level
    session_store so the /v2/chat response includes memory_snapshot.
    """
    user_content = Content(role="user", parts=[Part(text=sanitized_message)])

    # ADK 2.0 requires the session to exist before run_async; create on first turn.
    existing = await _session_service.get_session(
        app_name="LoanInquiry", user_id="default", session_id=session_id
    )
    if existing is None:
        await _session_service.create_session(
            app_name="LoanInquiry", user_id="default", session_id=session_id
        )

    final_answer = ""
    async for event in _runner.run_async(
        user_id="default",          # single-user app; use request user ID if multi-tenant
        session_id=session_id,
        new_message=user_content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_answer = event.content.parts[0].text or ""

    return final_answer
