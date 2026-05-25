"""
LoanInquiry v2 — 6-node LangGraph pipeline.

Graph topology:
                           ┌──────────────┐
                           │ input_guard  │  Node 1
                           └──────┬───────┘
                                  │
                           ┌──────▼───────┐
                           │ intent_router│  Node 2
                           └──────┬───────┘
                  ________________│________________
                 /        |               |        \
         ┌──────▼──┐ ┌────▼────┐ ┌───────▼──┐ ┌───▼────────┐
         │ policy  │ │ status  │ │   web    │ │ eligibility│  Nodes 3-6
         └──────┬──┘ └────┬────┘ └───────┬──┘ └───┬────────┘
                 \        |               |        /
                  ‾‾‾‾‾‾‾‾│‾‾‾‾‾‾‾‾‾‾‾‾‾│‾‾‾‾‾‾‾‾
                           │
                    ┌──────▼───────┐
                    │  synthesis   │  Node 7
                    └──────────────┘

Conditional routing (after intent_router):
  intent == "policy"      → policy_agent      → synthesis
  intent == "status"      → status_agent      → synthesis
  intent == "web"         → web_search_agent  → synthesis
  intent == "eligibility" → policy_agent (first), then eligibility_agent → synthesis
  intent == "general"     → synthesis directly (no specialists)

The graph is compiled once at module level and reused across requests.
"""
from langgraph.graph import END, StateGraph

from app.agents.eligibility_agent import eligibility_agent
from app.agents.input_guardrail import input_guardrail_agent
from app.agents.intent_router import intent_router_agent
from app.agents.policy_agent import policy_agent
from app.agents.status_agent import status_agent
from app.agents.synthesis_agent import synthesis_agent
from app.agents.web_search_agent import web_search_agent
from app.models.models import InquiryState


# ---------------------------------------------------------------------------
# Routing functions — called by add_conditional_edges after intent_router
# ---------------------------------------------------------------------------

def _route_from_intent(state: InquiryState) -> str:
    """
    Maps the intent set by IntentRouterAgent to the next node name.

    eligibility requires policy context first, so it routes to policy_agent;
    policy_agent → eligibility_agent routing is handled by _route_from_policy.
    """
    specialists = state.get("specialists_to_run") or []
    if not specialists:
        return "synthesis"
    # Route to first specialist; eligibility starts with policy
    first = specialists[0]
    return {
        "policy":      "policy_agent",
        "status":      "status_agent",
        "web":         "web_search_agent",
        "eligibility": "policy_agent",   # policy runs first for eligibility intent
    }.get(first, "synthesis")


def _route_from_policy(state: InquiryState) -> str:
    """
    After policy_agent runs: if eligibility is also in specialists_to_run,
    continue to eligibility_agent.  Otherwise go to synthesis.
    """
    specialists = state.get("specialists_to_run") or []
    if "eligibility" in specialists:
        return "eligibility_agent"
    return "synthesis"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    g = StateGraph(InquiryState)

    # --- Register nodes
    g.add_node("input_guardrail",  input_guardrail_agent)
    g.add_node("intent_router",    intent_router_agent)
    g.add_node("policy_agent",     policy_agent)
    g.add_node("status_agent",     status_agent)
    g.add_node("web_search_agent", web_search_agent)
    g.add_node("eligibility_agent", eligibility_agent)
    g.add_node("synthesis",        synthesis_agent)

    # --- Entry point
    g.set_entry_point("input_guardrail")

    # --- Fixed edges
    g.add_edge("input_guardrail", "intent_router")

    # --- Conditional routing after intent classification
    g.add_conditional_edges(
        "intent_router",
        _route_from_intent,
        {
            "policy_agent":     "policy_agent",
            "status_agent":     "status_agent",
            "web_search_agent": "web_search_agent",
            "synthesis":        "synthesis",
        },
    )

    # --- After policy: either continue to eligibility or go to synthesis
    g.add_conditional_edges(
        "policy_agent",
        _route_from_policy,
        {
            "eligibility_agent": "eligibility_agent",
            "synthesis":         "synthesis",
        },
    )

    # --- All specialists converge on synthesis
    g.add_edge("status_agent",     "synthesis")
    g.add_edge("web_search_agent", "synthesis")
    g.add_edge("eligibility_agent", "synthesis")

    # --- Terminal edge
    g.add_edge("synthesis", END)

    return g


# Compile once at import time — reused for all requests
_graph = _build_graph().compile()


# ---------------------------------------------------------------------------
# Public entry point used by main.py
# ---------------------------------------------------------------------------

async def run_v2_inquiry(initial_state: InquiryState) -> InquiryState:
    """
    Execute the full LangGraph pipeline and return the completed state.

    Callers (main.py) are responsible for:
      - Setting state['session_id'], ['raw_message'], ['memory_type'] before calling.
      - Reading state['final_answer'] and state['agent_trace'] from the result.
      - Updating session memory after the call returns.
    """
    result: InquiryState = await _graph.ainvoke(initial_state)
    return result
