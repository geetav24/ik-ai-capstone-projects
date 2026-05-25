"""
IntentRouterAgent — Node 2 in the v2 LangGraph pipeline.

Classifies the user's sanitized message into one of five intents and
decides which specialist agents to run downstream.

Intent taxonomy:
  policy      → user asks about rules, requirements, documents, eligibility criteria
  status      → user mentions a loan ID (LN-NNN) or asks about their application
  web         → user asks about external resources, government sites, general finance
  eligibility → user wants to know their loan limit / whether they qualify
  general     → everything else (greet, clarify, out-of-scope)

Writes to state:
  intent            — one of the five values above
  loan_id_hint      — extracted loan ID string if intent == "status", else None
  specialists_to_run — list of agent keys for the conditional router
  agent_trace       — appends one AgentTraceEntry
"""
import re
from datetime import datetime, timezone

from app.llm_client import ask_llm_json
from app.models.models import AgentTraceEntry, InquiryState


# Quick regex to detect loan IDs before calling the LLM (saves a round trip
# for the most common status-check pattern).
_LOAN_ID_RE = re.compile(r"\bLN-\d{3,}\b", re.IGNORECASE)


async def intent_router_agent(state: InquiryState) -> dict:
    """
    LangGraph node.  Reads state['sanitized_message']; writes intent,
    loan_id_hint, specialists_to_run, and appends to agent_trace.

    Strategy:
      1. Regex pre-check: if a loan ID is present → intent = "status" (fast path).
      2. Otherwise: ask the LLM to classify the message and return JSON.
      3. Map intent to specialists_to_run list.
    """
    started = datetime.now(timezone.utc)
    sanitized = state.get("sanitized_message", "")

    # --- Fast path: loan ID regex
    loan_id_match = _LOAN_ID_RE.search(sanitized)
    if loan_id_match:
        intent = "status"
        loan_id_hint = loan_id_match.group(0).upper()
    else:
        # --- LLM classification
        # TODO: tune the system prompt — explain the five intent categories clearly.
        #       The JSON schema must exactly match {"intent": "<value>", "loan_id": "<LN-NNN or null>"}.
        system_prompt = (
            "You are an intent classifier for a loan chatbot. "
            "Classify the user message into exactly one of these intents: "
            "policy, status, web, eligibility, general.\n\n"
            "policy    — questions about loan rules, document requirements, eligibility criteria\n"
            "status    — questions about a specific loan application; often contains a loan ID\n"
            "web       — requests for external links, government contacts, or general finance info\n"
            "eligibility — user wants to know how much they can borrow or whether they qualify\n"
            "general   — greetings, clarifications, or questions outside the above\n\n"
            'Respond ONLY with JSON: {"intent": "<value>", "loan_id": "<LN-NNN or null>"}'
        )

        # TODO: tune user prompt — decide how much context from conversation history
        #       to include here for better multi-turn intent resolution.
        user_prompt = f"User message:\n{sanitized}"

        try:
            parsed = await ask_llm_json(system_prompt, user_prompt)
            intent = parsed.get("intent", "general")
            if intent not in ("policy", "status", "web", "eligibility", "general"):
                intent = "general"
            loan_id_raw = parsed.get("loan_id")
            loan_id_hint = loan_id_raw.upper() if loan_id_raw and loan_id_raw != "null" else None
        except Exception:
            intent = "general"
            loan_id_hint = None

    # --- Map intent → specialists_to_run
    # TODO: consider allowing multiple specialists for compound questions
    #       (e.g., "What documents do I need and what is my loan limit?")
    _INTENT_TO_SPECIALISTS: dict[str, list[str]] = {
        "policy":      ["policy"],
        "status":      ["status"],
        "web":         ["web"],
        "eligibility": ["policy", "eligibility"],   # eligibility needs policy context
        "general":     [],
    }
    specialists_to_run = _INTENT_TO_SPECIALISTS.get(intent, [])

    finished = datetime.now(timezone.utc)
    trace = AgentTraceEntry(
        agent="intent_router",
        started_at=started,
        finished_at=finished,
        input_summary=f"message_length={len(sanitized)}",
        output_summary=f"intent={intent}, loan_id_hint={loan_id_hint}, specialists={specialists_to_run}",
    )

    existing_trace = state.get("agent_trace") or []
    return {
        "intent": intent,
        "loan_id_hint": loan_id_hint,
        "specialists_to_run": specialists_to_run,
        "agent_trace": existing_trace + [trace.model_dump()],
    }
