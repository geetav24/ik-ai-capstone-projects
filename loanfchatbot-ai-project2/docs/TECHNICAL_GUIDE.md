# LoanInquiry AI — Technical Guide (Project 2)

> **Who this is for:** IK SDE Pathway students learning how to build conversational multi-agent AI systems.
> This guide walks through every file and design decision in the codebase, with real code snippets and "Why this works" explanations.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Two Pipelines: LangGraph vs Google ADK](#2-two-pipelines-langgraph-vs-google-adk)
3. [InquiryState — The Pipeline Memory](#3-inquirystate--the-pipeline-memory)
4. [Data Contracts (Pydantic Models)](#4-data-contracts-pydantic-models)
5. [Agent Pipeline Walkthrough — LangGraph v2](#5-agent-pipeline-walkthrough--langgraph-v2)
6. [Intent Routing](#6-intent-routing)
7. [Google ADK Pipeline](#7-google-adk-pipeline)
8. [Memory System](#8-memory-system)
9. [Tool Layer](#9-tool-layer)
10. [FastAPI Endpoints](#10-fastapi-endpoints)
11. [Request Lifecycle](#11-request-lifecycle)
12. [Shared Infrastructure with Project 1](#12-shared-infrastructure-with-project-1)

---

## 1. System Overview

LoanInquiry AI is a **conversational loan assistant** — the chat-based companion to Project 1 (LoanFlow AI). Where Project 1 is a structured one-shot review pipeline for bank staff, Project 2 is an interactive chatbot for loan applicants and general users.

### Key differences from Project 1

| Dimension | Project 1 (LoanFlow AI) | Project 2 (LoanInquiry AI) |
|---|---|---|
| Interface | Form (one question per submit) | Chat (multi-turn conversation) |
| Memory | None — stateless per call | BufferMemory + SummaryMemory |
| Audience | Bank loan reviewer | Loan applicant / general user |
| Framework | LangGraph only | LangGraph **and** Google ADK |
| Agents | 8 agents (fixed pipeline) | 7 nodes (intent-routed) |
| Tools | MCP server over HTTP SSE | Direct Python function calls |
| Guardrails | Input + Output | Input only (hard-stop) |
| Endpoint | POST /review | POST /v2/chat |

### Design principle: guidance-only

Like Project 1, this system **never approves or rejects a loan**. Every response is clearly framed as guidance or an estimate. The `instruction` on every LlmAgent and every SynthesisAgent system prompt contains the rule: *"Never approve or reject a loan."*

### What users can ask

- **Policy questions** — "What credit score do I need for a personal loan?"
- **Loan status** — "What is the status of LN-004?"
- **Eligibility estimates** — "I earn $80k with a 710 credit score — how much can I borrow?"
- **External guidance** — "Where can I get a certified copy of my tax return?"
- **Follow-up questions** — "What if I'm self-employed?" (references prior turn via memory)

---

## 2. Two Pipelines: LangGraph vs Google ADK

Project 2 ships **two implementations** of the same multi-agent pipeline so you can compare them directly.

### LangGraph v2 (`workflows/langgraph_workflow.py`)

```
input_guardrail → intent_router →[conditional]→ policy_agent →[conditional]→ eligibility_agent
                                              → status_agent
                                              → web_search_agent
                                              → synthesis (direct, for "general" intent)
                         ↓ all paths converge ↓
                              synthesis_agent → END
```

You write Python code that defines **explicit graph edges**. The routing logic is in `_route_from_intent()` and `_route_from_policy()` — two normal Python functions. Every routing decision is visible in the code.

### Google ADK (`workflows/adk_workflow.py`)

```
triage_agent (LlmAgent)
  └── reads description fields of sub_agents
  └── picks one:  policy_agent | status_agent | web_search_agent | eligibility_agent
  └── synthesizes final answer
```

You write `description` strings on each `LlmAgent`. The triage LLM **reads those descriptions** and decides which specialist to call. No routing code — the LLM is the router.

### Side-by-side comparison

| Concern | LangGraph | Google ADK |
|---|---|---|
| Routing mechanism | Python code (`add_conditional_edges`) | LLM reads `description` strings |
| Visibility | Every edge is explicit in code | Routing is implicit (LLM decision) |
| Code volume | More code (node + edge per agent) | Less code (declarative sub_agents list) |
| Flexibility | Full control — exactly what you specify | LLM's language understanding decides |
| Best for | Deterministic pipelines, audit trails | Conversational routing, quick prototyping |
| Project 1 used | Yes | No |
| Project 2 uses | Yes (v2 LangGraph path) | Yes (active `/v2/chat` endpoint) |

> **Why ship both?** The contrast is the lesson. LangGraph makes every decision explicit — ideal when you need to audit routing. ADK reduces boilerplate — ideal when the LLM's language understanding is itself the routing logic. Project 2 lets you run both and observe the tradeoffs.

---

## 3. InquiryState — The Pipeline Memory

`InquiryState` is the LangGraph state TypedDict — the shared memory that flows through all 7 nodes.

```python
# app/models/models.py
class InquiryState(TypedDict, total=False):
    # set by API handler BEFORE the graph runs
    session_id: str
    raw_message: str
    memory_type: str              # "buffer" | "summary"

    # set by InputGuardrailAgent
    sanitized_message: str
    injection_signals: list[str]
    redactions: list[str]

    # set by IntentRouterAgent
    intent: str                   # "policy" | "status" | "web" | "eligibility" | "general"
    loan_id_hint: str | None      # extracted loan ID if intent == "status"
    specialists_to_run: list[str] # subset of: ["policy", "status", "web", "eligibility"]

    # set by specialist agents
    policy_chunks: list[dict]     # PolicyChunk dicts
    loan_status: dict | None      # LoanStatus dict or None
    web_results: list[dict]       # WebResult dicts
    eligibility_result: dict | None  # EligibilityResult dict or None

    # set by SynthesisAgent
    final_answer: str

    # accumulated by all agents
    agent_trace: list[dict]       # AgentTraceEntry dicts
    specialists_called: list[str] # which agents actually ran

    # set by API handler AFTER graph completes
    memory_snapshot: list[dict]   # last N ChatMessage dicts for response
```

### `total=False` — all fields optional

The `total=False` parameter means every field is `Optional` by default. Nodes only touch the keys they own. If `StatusAgent` runs, it doesn't need to care about `policy_chunks`. If `PolicyAgent` didn't run, `policy_chunks` simply isn't in state.

> **Compare to Project 1:** Project 1's `LoanReviewState` uses `Optional[dict]` explicitly per field and `Annotated[list, operator.add]` for append-only lists. Project 2 uses `total=False` TypedDict — cleaner, but trace accumulation is **manual**.

### Manual trace accumulation — different from Project 1

In Project 1, `agent_trace` is `Annotated[list, operator.add]` — LangGraph automatically appends entries when nodes return `{"agent_trace": [new_entry]}`.

In Project 2, each agent must read the existing trace and extend it manually:

```python
# Every agent in Project 2 does this:
existing_trace = state.get("agent_trace") or []
return {
    "agent_trace": existing_trace + [trace.model_dump()],
    # ... other keys
}
```

This is slightly more verbose but makes the accumulation explicit and easier to understand.

### How state flows

```
API sets: session_id, raw_message, memory_type
    ↓ InputGuardrail adds: sanitized_message, injection_signals, redactions
    ↓ IntentRouter adds: intent, loan_id_hint, specialists_to_run
    ↓ PolicyAgent adds: policy_chunks, specialists_called=["policy"]
    ↓ EligibilityAgent adds: eligibility_result, specialists_called=["policy","eligibility"]
    ↓ SynthesisAgent adds: final_answer
API reads: final_answer, agent_trace, specialists_called → V2ChatResponse
API then sets: memory_snapshot (added after graph, not by graph nodes)
```

---

## 4. Data Contracts (Pydantic Models)

All types live in `app/models/models.py`. Define your contracts before writing agents — if two agents disagree on what a `PolicyChunk` looks like, you've already lost.

### Shared primitives

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = None

class PolicyChunk(BaseModel):
    filename: str
    chunk_index: int
    score: float
    text: str

class WebResult(BaseModel):
    title: str
    url: str
    content: str

class LoanStatus(BaseModel):
    loan_id: str
    borrower_name: str
    loan_type: str
    loan_amount: float
    status: str = "under_review"
    credit_score: int
    annual_income: float
    employment_status: str
```

### Per-agent output types

```python
class AgentTraceEntry(BaseModel):
    agent: str
    started_at: datetime
    finished_at: datetime
    input_summary: str
    output_summary: str

class EligibilityResult(BaseModel):
    eligible: bool
    max_loan_amount: float | None = None
    reason: str
    policy_citations: list[str] = []
```

### API contracts

```python
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
```

---

## 5. Agent Pipeline Walkthrough — LangGraph v2

### Agent 1: InputGuardrailAgent (`agents/input_guardrail.py`)

**Reads:** `state["raw_message"]`
**Writes:** `sanitized_message`, `injection_signals`, `redactions`, appends to `agent_trace`

Four steps, same structure as Project 1, with one key improvement:

```python
# Project 2 scopes Presidio to specific entities only
_PRESIDIO_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
    "DATE_TIME", "US_PASSPORT", "US_ITIN", "NRP",
]
# US_BANK_NUMBER is EXCLUDED from Presidio — its numeric patterns
# collide with large dollar amounts like $12,000,000.
# The regex step above handles bank account numbers instead with a
# negative lookbehind: (?<!\$)\b\d{8,17}\b
```

**Hard-stop in main.py:** If `injection_signals` is non-empty, `main.py` returns a safe refusal immediately — the ADK pipeline is **never called**. This is the most important security property: injection detection happens before any LLM call.

```python
# main.py
if injection_signals:
    return V2ChatResponse(
        answer="I'm sorry, I can't process that request.",
        intent="blocked",
        # ... no LLM involved
    )
```

---

### Agent 2: IntentRouterAgent (`agents/intent_router.py`)

**Reads:** `state["sanitized_message"]`
**Writes:** `intent`, `loan_id_hint`, `specialists_to_run`, appends to `agent_trace`

Two-path classification strategy:

```python
# Fast path — regex before LLM (saves a round trip on the most common status pattern)
_LOAN_ID_RE = re.compile(r"\bLN-\d{3,}\b", re.IGNORECASE)

loan_id_match = _LOAN_ID_RE.search(sanitized)
if loan_id_match:
    intent = "status"
    loan_id_hint = loan_id_match.group(0).upper()
else:
    # LLM classification
    parsed = await ask_llm_json(system_prompt, user_prompt)
    intent = parsed.get("intent", "general")
```

Intent → specialists mapping:

```python
_INTENT_TO_SPECIALISTS = {
    "policy":      ["policy"],
    "status":      ["status"],
    "web":         ["web"],
    "eligibility": ["policy", "eligibility"],  # policy must run first
    "general":     [],                          # skip all specialists
}
```

> **Why `["policy", "eligibility"]` for eligibility?** EligibilityAgent needs policy chunks to ground its loan limit calculation. If it ran without PolicyAgent, it would have no policy context and would hallucinate rules. The two-step sequence is enforced by the `_route_from_policy` conditional edge.

---

### Agent 3: PolicyAgent (`agents/policy_agent.py`)

**Reads:** `state["sanitized_message"]`
**Writes:** `policy_chunks`, appends to `specialists_called` and `agent_trace`

```python
# Strip delimiters before embedding — they are noise for the vector search
query = sanitized.replace("<<<USER_MESSAGE>>>", "").replace("<<<END_USER_MESSAGE>>>", "").strip()
chunks = await search_policy(query=query, top_k=5)
```

> **Why only retrieve here?** PolicyAgent's single responsibility is fetching relevant policy chunks. It does **not** generate an answer. SynthesisAgent sees all specialist outputs and produces the final combined answer. This separation means you can swap out the retrieval strategy (different top_k, reranking, hybrid search) without touching the answer generation logic.

---

### Agent 4: StatusAgent (`agents/status_agent.py`)

**Reads:** `state["loan_id_hint"]`
**Writes:** `loan_status`, appends to `specialists_called` and `agent_trace`

Calls `get_loan_status(loan_id)` which queries the shared SQLite `loanflow.db`. Returns `None` if not found — the agent trace notes "loan not found" and SynthesisAgent presents a polite "loan ID not found" message.

---

### Agent 5: WebSearchAgent (`agents/web_search_agent.py`)

**Reads:** `state["sanitized_message"]`
**Writes:** `web_results`, appends to `specialists_called` and `agent_trace`

Calls `web_search(query)` → Tavily REST API. Returns top-3 `WebResult` dicts with title, URL, and content snippet (first 300 chars used by SynthesisAgent).

---

### Agent 6: EligibilityAgent (`agents/eligibility_agent.py`)

**Reads:** `state["policy_chunks"]`, `state["sanitized_message"]`
**Writes:** `eligibility_result`, appends to `specialists_called` and `agent_trace`

This is the most LLM-heavy specialist. It:
1. Formats `policy_chunks` as a context block
2. Asks the LLM to extract the user's stated income/credit score/loan type from the message
3. Applies DTI, credit tier, and LTV rules from the policy context to those numbers
4. Returns a structured `EligibilityResult`

```python
system_prompt = (
    "You are a loan eligibility analyst. "
    "Use ONLY the policy excerpts below to answer eligibility questions. "
    "Never invent loan limits or rules not present in the policy.\n\n"
    "---- Policy context ----\n"
    f"{policy_context}\n\n"
    "Return ONLY JSON matching this schema:\n"
    '{"eligible": true|false, "max_loan_amount": <number or null>, '
    '"reason": "<explanation>", "policy_citations": ["<source1>", ...]}'
)
```

Falls back to a safe default `{"eligible": False, "max_loan_amount": None, "reason": "Could not determine..."}` if the LLM returns non-JSON.

---

### Agent 7: SynthesisAgent (`agents/synthesis_agent.py`)

**Reads:** all specialist outputs + `injection_signals` + `intent`
**Writes:** `final_answer`, appends to `agent_trace`

This is the only agent whose output the user reads. It:
1. Builds context sections from whatever specialists ran
2. Calls `ask_llm_fast` (gpt-4o-mini) with the combined context
3. If `injection_signals` non-empty: adds a security note to the context telling the LLM not to follow embedded instructions

```python
context_parts = [s for s in [
    policy_section,
    status_section,
    web_section,
    eligibility_section,
    injection_section,
] if s]
full_context = "\n\n".join(context_parts) or "(no specialist context available)"
```

If intent is `"general"` and no specialists ran, `full_context` is `"(no specialist context available)"` — the LLM answers conversationally from memory/context alone.

---

## 6. Intent Routing

Two conditional routing functions sit between nodes in the LangGraph graph:

```python
def _route_from_intent(state: InquiryState) -> str:
    specialists = state.get("specialists_to_run") or []
    if not specialists:
        return "synthesis"          # general intent → skip all specialists
    first = specialists[0]
    return {
        "policy":      "policy_agent",
        "status":      "status_agent",
        "web":         "web_search_agent",
        "eligibility": "policy_agent",   # eligibility starts with policy
    }.get(first, "synthesis")


def _route_from_policy(state: InquiryState) -> str:
    specialists = state.get("specialists_to_run") or []
    if "eligibility" in specialists:
        return "eligibility_agent"  # continue to second specialist
    return "synthesis"              # policy-only → done
```

The graph wires these as `add_conditional_edges`:

```python
g.add_conditional_edges("intent_router", _route_from_intent, {
    "policy_agent":     "policy_agent",
    "status_agent":     "status_agent",
    "web_search_agent": "web_search_agent",
    "synthesis":        "synthesis",
})
g.add_conditional_edges("policy_agent", _route_from_policy, {
    "eligibility_agent": "eligibility_agent",
    "synthesis":         "synthesis",
})
```

All specialist paths (status → synthesis, web → synthesis, eligibility → synthesis) converge at SynthesisAgent.

---

## 7. Google ADK Pipeline

The ADK pipeline in `workflows/adk_workflow.py` achieves the same outcome with much less routing code.

### LiteLlm bridge — no Gemini key needed

```python
_MODEL = LiteLlm(model="openai/gpt-4o-mini")
```

`LiteLlm` is an ADK adapter that routes LLM calls to OpenAI. The `openai/` prefix tells it which provider. You reuse the same `OPENAI_API_KEY` from Project 1's `.env`.

### Specialist sub_agents — description-driven routing

```python
_policy_agent = LlmAgent(
    name="policy_agent",
    model=_MODEL,
    description=(                      # ← triage LLM reads this to decide routing
        "Answers questions about loan policy rules, required documents, "
        "credit score tiers, DTI limits, and eligibility criteria."
    ),
    instruction=(                      # ← system prompt for this specialist
        "You are a loan policy specialist. "
        "Always call the search_policy tool before answering. "
        "Cite every policy claim using [Source: filename, chunk N]. "
        "Never invent rules. Never approve or reject a loan."
    ),
    tools=[FunctionTool(func=search_policy)],
)
```

The `description` is what the triage LLM reads to pick a specialist. Keep it short and unambiguous — it's not a system prompt, it's a label.

### Triage agent — router + synthesizer

```python
_triage_agent = LlmAgent(
    name="loan_inquiry_triage",
    model=_MODEL,
    instruction="Route to exactly one specialist based on intent...",
    sub_agents=[_policy_agent, _status_agent, _web_agent, _eligibility_agent],
)
```

The triage agent both **routes** (picks a sub_agent) and **synthesizes** (produces the final answer after the specialist responds). This is a key ADK pattern — the triage agent is the entry point and exit point.

### Session management

```python
_session_service = InMemorySessionService()
_runner = Runner(agent=_triage_agent, app_name="LoanInquiry", session_service=_session_service)
```

ADK's `InMemorySessionService` automatically accumulates turn history per `session_id`. You don't need to manually build a conversation history string — ADK injects prior turns into the LLM context automatically.

```python
async def run_adk_inquiry(session_id: str, sanitized_message: str) -> str:
    # Create session on first turn
    existing = await _session_service.get_session(...)
    if existing is None:
        await _session_service.create_session(...)

    async for event in _runner.run_async(..., new_message=user_content):
        if event.is_final_response():
            final_answer = event.content.parts[0].text
    return final_answer
```

> **Two memory systems coexist:** ADK's `InMemorySessionService` handles the LLM-facing conversation history. Our `session_store` (BufferMemory / SummaryMemory) provides the `memory_snapshot` field in the API response so the frontend can show the conversation history. They are separate and serve different purposes.

---

## 8. Memory System

Memory in Project 2 is **conversational** — it persists across HTTP requests for the same `session_id`. This is what makes Project 2 a chatbot rather than a one-shot API.

### BufferMemory (`memory/buffer_memory.py`)

Stores the last N messages verbatim in a list. When the list exceeds `max_messages`, the oldest are dropped (sliding window).

```python
class BufferMemory:
    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self._history: list[ChatMessage] = []

    def add(self, role: str, content: str) -> None:
        self._history.append(ChatMessage(role=role, content=content, ...))
        if len(self._history) > self.max_messages:
            self._history = self._history[-self.max_messages:]  # drop oldest

    def format_for_prompt(self) -> str:
        lines = [f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
                 for m in self._history]
        return "\n".join(lines)
```

**Use when:** conversations are short (< 10 turns), latency is critical, no LLM cost budget for memory.

### SummaryMemory (`memory/summary_memory.py`)

Keeps a compressed summary of older turns plus the last N verbatim messages. When the buffer exceeds `recent_messages * 2`, it compresses the oldest half into a 2-3 sentence summary using `ask_llm_fast`.

```python
async def _compress(self) -> None:
    to_compress = self._recent[:-self.recent_messages]   # oldest half
    self._recent = self._recent[-self.recent_messages:]  # keep recent half

    history_text = "\n".join(...)
    existing = f"Previous summary: {self._summary}\n\n" if self._summary else ""

    self._summary = await ask_llm_fast(
        "Produce a concise 2-3 sentence summary...",
        f"{existing}New messages:\n{history_text}",
    )

def format_for_prompt(self) -> str:
    parts = []
    if self._summary:
        parts.append(f"[Earlier conversation summary]: {self._summary}")
    for msg in self._recent:
        parts.append(f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content}")
    return "\n".join(parts)
```

**Use when:** conversations may run 20+ turns, exact wording of old turns is less important than topic continuity.

### session_store (`core/session_store.py`)

A simple module-level dict that maps `session_id → memory object`:

```python
_sessions: dict[str, Union[BufferMemory, SummaryMemory]] = {}

def get_or_create(session_id: str, memory_type: str = "buffer"):
    if session_id not in _sessions:
        _sessions[session_id] = BufferMemory() if memory_type == "buffer" else SummaryMemory()
    return _sessions[session_id]
```

> **Production note:** this is in-process memory — a server restart clears all sessions. Replace `_sessions` with a Redis client (`redis_client.setex(session_id, 3600, pickle.dumps(memory))`) for persistence. The interface (`get_or_create`, `delete`, `list_sessions`) doesn't need to change.

---

## 9. Tool Layer

Project 2 calls tools as **plain Python async functions** — no MCP server, no SSE transport. This is simpler than Project 1's MCP architecture because the tool layer doesn't need to be decoupled into a separate process.

### `tools/policy_tool.py` — Pinecone semantic search

```python
async def search_policy(query: str, top_k: int = 5) -> list[PolicyChunk]:
    # embed query using text-embedding-3-small
    # query Pinecone index "loanflow-ai"
    # return top_k PolicyChunk objects
```

Called by: PolicyAgent (LangGraph), policy_agent LlmAgent (ADK), EligibilityAgent (LangGraph).

Shares the **same Pinecone index** as Project 1 (`loanflow-ai`, `text-embedding-3-small`). Project 1's `generate_policy.py` populates it; Project 2 reads it.

### `tools/loan_status_tool.py` — SQLite lookup

```python
async def get_loan_status(loan_id: str) -> dict | None:
    # query loanflow.db / loan_applications where loan_id = ?
    # return LoanStatus dict or None if not found
```

Reads the **same SQLite database** as Project 1 (`loanflow.db`). Loan records seeded by Project 1's `seed.py` are queryable here. No write access — read-only status lookup.

### `tools/web_search_tool.py` — Tavily REST API

```python
async def web_search(query: str, max_results: int = 3) -> list[WebResult]:
    # POST to Tavily API with TAVILY_API_KEY
    # returns list of WebResult(title, url, content)
```

Requires `TAVILY_API_KEY` in `.env` — the only env var Project 2 needs beyond what Project 1 already uses.

---

## 10. FastAPI Endpoints

```python
# main.py
@app.post("/v2/chat", response_model=V2ChatResponse)
async def chat_v2(request: V2ChatRequest):
    # Phase 1 — InputGuardrailAgent
    guardrail_result = await input_guardrail_agent({"raw_message": request.message})
    if injection_signals:
        return V2ChatResponse(answer="I'm sorry, I can't process that request.", ...)

    # Phase 2 — ADK pipeline
    answer = await run_adk_inquiry(session_id=request.session_id, sanitized_message=...)

    # Phase 3 — Update session memory
    memory = get_or_create(request.session_id, request.memory_type)
    memory.add("user", request.message)
    memory.add("assistant", answer)

    return V2ChatResponse(answer=answer, memory_snapshot=memory.get_messages()[-6:], ...)
```

### All endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v2/chat` | Primary — guardrail → ADK → memory update |
| `POST` | `/chat` | v1 preserved — single-agent loop for teaching comparison |
| `DELETE` | `/chat/{session_id}` | Clear session from `session_store` |
| `GET` | `/sessions` | List active session IDs in `session_store` |
| `GET` | `/health` | Health check |

> **Note:** `DELETE /chat/{session_id}` only clears `session_store`. ADK's `InMemorySessionService` is a separate object and is **not** cleared. If you want to fully reset a conversation, you'd need to also call `_session_service.delete_session(...)` in the ADK workflow. This is a known gap — track it as future work.

---

## 11. Request Lifecycle

Step-by-step trace for: *"I earn $80,000/year with a credit score of 710 — how much can I borrow for a mortgage?"*

**Intent:** `eligibility` → specialists: `["policy", "eligibility"]`

```
1. HTTP POST /v2/chat
   {session_id: "sess-abc", message: "I earn $80k...", memory_type: "buffer"}

2. FastAPI deserialises V2ChatRequest

3. InputGuardrailAgent (plain Python — before ADK)
   ├── len("I earn $80k...") = 68 chars ✔
   ├── Financial PII regex → no SSN/card/bank found
   ├── Presidio → no PERSON/EMAIL/PHONE detected
   ├── Injection denylist → no phrases matched
   └── Wraps: "<<<USER_MESSAGE>>>\nI earn $80k...\n<<<END_USER_MESSAGE>>>"
   Returns: {sanitized_message, injection_signals=[], redactions=[]}

4. injection_signals is empty → continue to ADK

5. run_adk_inquiry("sess-abc", sanitized_message)
   ├── InMemorySessionService.get_session("sess-abc") → None (first turn)
   ├── InMemorySessionService.create_session("sess-abc")
   └── Runner.run_async(new_message=Content(user, sanitized))

6. triage_agent reads sub_agent descriptions
   └── eligibility_agent description matches → hand off

7. eligibility_agent runs
   ├── Calls FunctionTool(search_policy) with query derived from message
   ├── Pinecone returns 5 policy chunks (DTI limits, LTV ratios, credit tiers)
   ├── LLM applies rules: $80k income → DTI 43% → max ~$34k/yr payment
   │   credit 710 → qualifies for standard tier
   │   mortgage → 80% LTV → needs 20% down
   └── Returns: eligible=True, max_loan_amount=350000, reason="...", policy_citations=[...]

8. triage_agent synthesizes final answer with citations
   └── "Based on the policy [Source: loan_policy.pdf, chunk 3], with an annual income
       of $80,000 and a credit score of 710, you would likely qualify for a mortgage
       up to approximately $350,000. This is an estimate — a loan officer will
       make the final determination."

9. runner yields is_final_response event → extract text answer

10. main.py updates session_store
    ├── memory.add("user", original_message)
    └── memory.add("assistant", answer)

11. Return V2ChatResponse
    {session_id: "sess-abc",
     answer: "Based on the policy...",
     intent: "unknown",           ← ADK routing is internal; not exposed
     specialists_called: [],      ← ADK routing is internal; not exposed
     injection_signals: [],
     redactions: [],
     agent_trace: [guardrail_trace_entry],
     memory_snapshot: [{role:"user", content:"I earn..."}, {role:"assistant", content:"Based on..."}]}
```

> **Why does `intent` come back as `"unknown"`?** ADK manages routing internally — the triage LLM's decision is not exposed via a public API. The `intent` and `specialists_called` fields in `V2ChatResponse` are only populated for the LangGraph path. If you need these values from the ADK path, add a custom ADK callback or wrap the specialist calls to emit events. This is a noted future improvement.

---

## 12. Shared Infrastructure with Project 1

Project 2 is designed to run **independently** — Project 1's backend does not need to be running.

| Resource | Created by | Read by |
|---|---|---|
| Pinecone index `loanflow-ai` | `loanflow-ai-project1/generate_policy.py` | `policy_tool.py`, `web_search_tool.py` |
| SQLite `loanflow.db` | `loanflow-ai-project1/backend/app/db/seed.py` | `loan_status_tool.py` |
| `.env` (OPENAI_API_KEY, PINECONE_API_KEY) | Set up once for Project 1 | Copied to Project 2 `.env` |
| `TAVILY_API_KEY` | New for Project 2 | `web_search_tool.py` |

### Setup checklist for Project 2

```bash
# 1. Run Project 1's generate_policy.py once to populate Pinecone
cd loanflow-ai-project1
python generate_policy.py

# 2. Run Project 1's seed.py once to populate SQLite
cd backend
python -m app.db.seed

# 3. Copy .env and add Tavily key
cp loanflow-ai-project1/backend/.env loanfchatbot-ai-project2/backend/.env
echo "TAVILY_API_KEY=your_key_here" >> loanfchatbot-ai-project2/backend/.env

# 4. Start Project 2's backend only
cd loanfchatbot-ai-project2
docker compose up
# OR
cd backend && uvicorn app.main:app --reload --port 8002
```

> **Why share the Pinecone index?** The policy document is the same for both projects. Sharing the index avoids double-indexing, prevents drift between two copies, and means any policy update only needs to be run once through `generate_policy.py`.
