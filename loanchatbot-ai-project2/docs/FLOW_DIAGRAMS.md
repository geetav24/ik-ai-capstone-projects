# LoanInquiry AI — Flow Diagrams (Project 2)

> All diagrams use [Mermaid](https://mermaid.js.org/) syntax.
> Render in GitHub, VS Code (Mermaid Preview plugin), or [mermaid.live](https://mermaid.live).

---

## Table of Contents

1. [LangGraph v2 Pipeline — Full Flow](#1-langgraph-v2-pipeline--full-flow)
2. [Google ADK Pipeline — How Declarative Routing Works](#2-google-adk-pipeline--how-declarative-routing-works)
3. [InquiryState — Memory Flow Through Nodes](#3-inquirystate--memory-flow-through-nodes)
4. [Intent Routing Decision Tree](#4-intent-routing-decision-tree)
5. [InputGuardrail — Detailed Flow](#5-inputguardrail--detailed-flow)
6. [Memory System — BufferMemory vs SummaryMemory](#6-memory-system--buffermemory-vs-summarymemory)
7. [POST /v2/chat — Full Request Lifecycle](#7-post-v2chat--full-request-lifecycle)
8. [Agent State Read/Write Map](#8-agent-state-readwrite-map)
9. [Project 1 vs Project 2 — Architecture Comparison](#9-project-1-vs-project-2--architecture-comparison)

---

## 1. LangGraph v2 Pipeline — Full Flow

The v2 pipeline has 7 nodes wired by two conditional routing functions. The key insight: the eligibility path is **sequential** (policy must retrieve context *before* eligibility can apply it), while all other paths are single-specialist then synthesis.

```mermaid
flowchart TD
    IN["HTTP POST /v2/chat\nV2ChatRequest\nsession_id · message · memory_type"] --> PH1

    subgraph PH1["Phase 1 — Guardrail (plain Python, before graph)"]
        IG["InputGuardrailAgent\n① Length cap — reject > 2000 chars\n② Financial PII regex (SSN · bank · card)\n③ Presidio (PERSON · EMAIL · PHONE etc.)\n   scoped — excludes patterns that collide with dollar amounts\n④ Injection denylist — 34 phrases\n⑤ Wrap in <<<USER_MESSAGE>>> delimiters"]
        CHK{"injection_signals\nnon-empty?"}
        IG --> CHK
        CHK -->|"YES — hard stop"| BLOCK["Return safe refusal\n'I'm sorry, I can't process that request.'\nNO LLM called at all"]
    end

    CHK -->|"NO — continue"| INIT["Initialise InquiryState\nsanitized_message · injection_signals · redactions\nspecialists_to_run = None · agent_trace = []"]

    INIT --> IR["IntentRouterAgent\n① Regex fast path: LN-\\d{3,} → status (no LLM)\n② LLM: ask_llm_json → {intent, loan_id}\n③ Map intent → specialists_to_run list"]

    IR -->|"intent + specialists_to_run\nagent_trace +"| CE1

    CE1{"_route_from_intent\nspecialists_to_run[0]"}

    CE1 -->|"policy"| PA["PolicyAgent\nStrip delimiters from query\nsearch_policy(query, top_k=5) → Pinecone\nRETRIEVES ONLY — no synthesis\npolicy_chunks + specialists_called"]

    CE1 -->|"status"| SA["StatusAgent\nget_loan_status(loan_id_hint) → SQLite\nNone-safe — polite message if not found\nloan_status + specialists_called"]

    CE1 -->|"web"| WA["WebSearchAgent\nweb_search(query) → Tavily API\nReturns top-3 WebResult dicts\nweb_results + specialists_called"]

    CE1 -->|"eligibility → policy_agent first"| PA

    CE1 -->|"general → no specialists"| SY

    PA -->|"policy_chunks\nspecialists_called +['policy']\nagent_trace +"| CE2

    CE2{"_route_from_policy\n'eligibility' in specialists_to_run?"}

    CE2 -->|"YES — eligibility path"| EA["EligibilityAgent\nRuns AFTER PolicyAgent\nReads: policy_chunks + sanitized_message\nLLM applies policy rules to user's financials\nask_llm_json → EligibilityResult\neligible · max_loan_amount · reason · policy_citations"]

    CE2 -->|"NO — policy only"| SY

    EA -->|"eligibility_result\nspecialists_called +['eligibility']\nagent_trace +"| SY

    SA -->|"loan_status\nagent_trace +"| SY
    WA -->|"web_results\nagent_trace +"| SY

    SY["SynthesisAgent\nReads ALL specialist outputs from state\nBuilds context sections:\n  • policy_chunks → formatted citations\n  • loan_status → readable summary\n  • web_results → titles + URLs\n  • eligibility_result → estimate + citations\n  • injection_signals → security note\nCalls ask_llm_fast\nProduces final_answer"]

    SY -->|"final_answer\nagent_trace +"| RESP["V2ChatResponse\nanswer · intent · specialists_called\ninjection_signals · redactions\nagent_trace · memory_snapshot"]
```

---

## 2. Google ADK Pipeline — How Declarative Routing Works

The ADK pipeline is a completely different approach. Instead of drawing edges in code, you write `description` strings on each sub_agent — the **triage LLM reads those descriptions** and decides which specialist to call. This diagram shows the conceptual flow inside ADK.

```mermaid
flowchart TD
    CALL["run_adk_inquiry\nsession_id · sanitized_message"] --> SS

    SS["InMemorySessionService\nCreate session on first turn\nADK manages turn history automatically\n(separate from our session_store)"]

    SS --> RA["Runner.run_async\nuser_id='default'\nsession_id · new_message=Content(user, text)"]

    RA --> TA["triage_agent  (LlmAgent)\nInstruction: 'Route to exactly one specialist'\nModel: LiteLlm('openai/gpt-4o-mini')\n→ OpenAI via LiteLlm bridge (no Gemini key needed)\n\nReads sub_agent DESCRIPTIONS to decide routing"]

    TA -->|"reads description:\n'Answers questions about loan policy rules...'"| PAS["policy_agent  (LlmAgent)\nTool: FunctionTool(search_policy)\nInstruction: always call search_policy first\nCite [Source: filename, chunk N]"]

    TA -->|"reads description:\n'Looks up status when user mentions LN-NNN'"| SAS["status_agent  (LlmAgent)\nTool: FunctionTool(get_loan_status)\nInstruction: extract loan ID, call tool, format result"]

    TA -->|"reads description:\n'Searches web for external resources...'"| WAS["web_search_agent  (LlmAgent)\nTool: FunctionTool(web_search)\nInstruction: concise query, include URLs"]

    TA -->|"reads description:\n'Estimates max loan amount based on income...'"| EAS["eligibility_agent  (LlmAgent)\nTool: FunctionTool(search_policy)\nInstruction: search policy first, apply to user's financials\nMark as estimate, cite sources"]

    PAS --> TA2
    SAS --> TA2
    WAS --> TA2
    EAS --> TA2

    TA2["triage_agent synthesizes\nFinal answer from specialist response\nStreams events back to runner"]

    TA2 --> FIN["event.is_final_response()\nextract final text\nreturn answer string"]
```

---

## 3. InquiryState — Memory Flow Through Nodes

`InquiryState` is a `TypedDict` with `total=False` — every field is optional. Each node reads what it needs and writes only what it owns. Unlike Project 1, trace accumulation is **manual**: each agent does `existing_trace + [new_entry]` (no `Annotated[list, operator.add]`).

```mermaid
flowchart LR
    INIT(["API handler sets:\nsession_id ✔\nraw_message ✔\nmemory_type ✔\nall others absent"])

    IG_OUT["After InputGuardrail\nsanitized_message ✔\ninjection_signals ✔\nredactions ✔\nagent_trace = [ig_entry]"]

    IR_OUT["After IntentRouter\nintent ✔\nloan_id_hint ✔ (or None)\nspecialists_to_run ✔\nagent_trace = [ig, ir]"]

    PA_OUT["After PolicyAgent (if ran)\npolicy_chunks ✔\nspecialists_called = ['policy']\nagent_trace = [ig, ir, pa]"]

    EA_OUT["After EligibilityAgent (if ran)\neligibility_result ✔\nspecialists_called = ['policy','eligibility']\nagent_trace = [ig, ir, pa, ea]"]

    SA_OUT["After StatusAgent (if ran)\nloan_status ✔ (or None)\nspecialists_called = ['status']\nagent_trace = [ig, ir, sa]"]

    WA_OUT["After WebSearchAgent (if ran)\nweb_results ✔\nspecialists_called = ['web']\nagent_trace = [ig, ir, wa]"]

    SY_OUT["After SynthesisAgent\nfinal_answer ✔\nagent_trace = [..., sy_entry]  ← complete"]

    END_OUT["API handler adds:\nmemory_snapshot ✔ (last 6 messages)\nReturns V2ChatResponse"]

    INIT --> IG_OUT --> IR_OUT --> PA_OUT --> EA_OUT --> SY_OUT --> END_OUT
    IR_OUT --> SA_OUT --> SY_OUT
    IR_OUT --> WA_OUT --> SY_OUT
    IR_OUT --> SY_OUT
```

### Manual trace accumulation (difference from Project 1)

```mermaid
flowchart LR
    subgraph P1["Project 1 — Annotated append-only"]
        A1["Annotated[list, operator.add]\nLangGraph merges automatically\nNode returns: {'agent_trace': [new_entry]}"]
    end

    subgraph P2["Project 2 — Manual accumulation"]
        A2["Each agent reads existing_trace\nexisting_trace = state.get('agent_trace') or []\nReturns: {'agent_trace': existing_trace + [new_entry]}"]
    end
```

---

## 4. Intent Routing Decision Tree

Two routing decisions happen in the LangGraph v2 pipeline. The **IntentRouter** fires first (with a regex fast path), then a second conditional edge fires after PolicyAgent to handle the eligibility two-step.

```mermaid
flowchart TD
    MSG["sanitized_message"] --> REGEX

    subgraph IR["IntentRouterAgent"]
        REGEX{"LN-\\d{3,} pattern\nin message?"}
        REGEX -->|"YES — fast path\nno LLM call"| STATUS_I["intent = 'status'\nloan_id_hint = matched ID"]
        REGEX -->|"NO"| LLM_I["ask_llm_json\nclassify into:\npolicy · status · web · eligibility · general"]
        LLM_I --> MAP["Map intent → specialists_to_run\npolicy      → ['policy']\nstatus      → ['status']\nweb         → ['web']\neligibility → ['policy','eligibility']\ngeneral     → []"]
    end

    STATUS_I --> CE1
    MAP --> CE1

    CE1{"_route_from_intent\nspecialists_to_run[0]"}

    CE1 -->|"'policy'"| PA_N["PolicyAgent\nretrieves chunks"]
    CE1 -->|"'status'"| SA_N["StatusAgent → Synthesis"]
    CE1 -->|"'web'"| WA_N["WebSearchAgent → Synthesis"]
    CE1 -->|"'eligibility' → 'policy_agent'"| PA_N
    CE1 -->|"[] — general"| SY_N["Synthesis (direct)"]

    PA_N --> CE2

    CE2{"_route_from_policy\n'eligibility' in\nspecialists_to_run?"}

    CE2 -->|"YES"| EA_N["EligibilityAgent\napplies policy rules\nto user's financials"]
    CE2 -->|"NO"| SY_N

    EA_N --> SY_N
    SA_N --> SY_N
    WA_N --> SY_N
```

---

## 5. InputGuardrail — Detailed Flow

The guardrail is called **twice**: once as a LangGraph node (inside the graph, for the v2 LangGraph pipeline) and once as a plain function call in `main.py` (before the ADK pipeline). In both cases the logic is identical.

**Key improvement over Project 1**: Presidio entity scope is restricted — `US_BANK_NUMBER` is excluded from Presidio because its numeric pattern collides with large dollar amounts (e.g., `$12000000`). A negative-lookbehind regex handles bank numbers instead.

```mermaid
flowchart TD
    IN["raw_message from state\nor from HTTP request body"] --> LC

    LC{"len(raw_message) > 2000?"}
    LC -->|"YES"| ERR["raise ValueError\n'Message exceeds 2000 character limit'\n→ HTTP 400 in main.py"]
    LC -->|"NO"| R1

    R1["Financial PII Regex — 3 patterns\n① SSN: \\b\\d{3}-\\d{2}-\\d{4}\\b\n② Bank acct: (?<!\\$)\\b\\d{8,17}\\b\n   negative lookbehind prevents redacting dollar amounts\n③ Credit card: 4 groups of 4 digits\nReplace → [REDACTED:US_SSN] etc."]

    R1 --> R2["Presidio Analyzer\nscoped entities ONLY:\n  PERSON · EMAIL_ADDRESS · PHONE_NUMBER\n  LOCATION · DATE_TIME · US_PASSPORT\n  US_ITIN · NRP\n(US_BANK_NUMBER excluded — handled by regex above)"]

    R2 --> R3["Presidio Anonymizer\nreplace each entity with [REDACTED:TYPE]"]

    R3 --> INJ["Injection Denylist Scan — 34 phrases\nCategories:\n  • Override / jailbreak\n  • Approval manipulation\n  • Authority impersonation\n  • System prompt extraction\n  • Role hijacking\nScan: cleaned message only\n(not app fields — no structured data here unlike P1)"]

    INJ --> DL["Delimiter Wrapping\n<<<USER_MESSAGE>>>\n{cleaned_message}\n<<<END_USER_MESSAGE>>>"]

    DL --> CHK{"injection_signals\nnon-empty?"}

    CHK -->|"YES (in main.py)"| STOP["Hard-stop: return safe refusal\nNO ADK pipeline called\nNO LLM call made"]
    CHK -->|"NO (or inside graph)"| RET["Return partial state dict\n{\n  sanitized_message\n  injection_signals\n  redactions\n  agent_trace: existing + [entry]\n}"]
```

---

## 6. Memory System — BufferMemory vs SummaryMemory

The memory system lives **outside** the LangGraph graph — it's managed by `main.py` after each turn. The graph itself is stateless; memory is injected by reading `memory.format_for_prompt()` in the agent prompts.

```mermaid
flowchart TD
    subgraph BM["BufferMemory — Sliding Window"]
        BM1["Turn 1: [U1, A1]"]
        BM2["Turn 5: [U1,A1,U2,A2,U3,A3,U4,A4,U5,A5]"]
        BM3["Turn 6: [A1,U2,A2,U3,A3,U4,A4,U5,A5,U6]\nU1 dropped — window full"]
        BM1 --> BM2 --> BM3
        BM_N["max_messages=10\nformat_for_prompt():\n'User: ...\nAssistant: ...'"]
    end

    subgraph SM["SummaryMemory — Rolling Compression"]
        SM1["Turn 1-4: _recent=[U1,A1,U2,A2]\n_summary=''"]
        SM2["Turn 9: _recent has >recent_messages*2\n→ _compress() triggered"]
        SM3["_compress():\n  to_compress = oldest messages\n  ask_llm_fast to summarize\n  _summary = '2-3 sentence summary'\n  _recent = last N verbatim"]
        SM4["format_for_prompt():\n'[Earlier conversation summary]: ...\nUser: ...\nAssistant: ...'"]
        SM1 --> SM2 --> SM3 --> SM4
    end

    subgraph SS["session_store.py"]
        SS1["_sessions: dict[str, BufferMemory | SummaryMemory]"]
        SS2["get_or_create(session_id, memory_type)\n→ creates on first call"]
        SS3["delete(session_id) → clears memory\nNOTE: does NOT clear ADK's InMemorySessionService"]
        SS1 --> SS2 --> SS3
    end

    BM --> SS
    SM --> SS
```

### When to use which

```mermaid
flowchart LR
    Q{"Conversation\nlength?"}
    Q -->|"Short (< 10 turns)"| USE_BM["BufferMemory\nFaster · No LLM cost\nmemory_type='buffer'"]
    Q -->|"Long (10+ turns)"| USE_SM["SummaryMemory\nScalable · LLM compression cost\nmemory_type='summary'"]
```

---

## 7. POST /v2/chat — Full Request Lifecycle

Step-by-step for the query: *"I earn $80k/year with a credit score of 710 — how much can I borrow for a mortgage?"* (eligibility intent).

```mermaid
sequenceDiagram
    participant U as User (Chat UI)
    participant API as FastAPI /v2/chat
    participant GRD as InputGuardrailAgent
    participant ADK as ADK Runner (run_adk_inquiry)
    participant TA as triage_agent
    participant PA as policy_agent (sub_agent)
    participant EA as eligibility_agent (sub_agent)
    participant PC as Pinecone
    participant SS as session_store

    U->>API: POST /v2/chat\n{session_id, message, memory_type}

    note over API,GRD: Phase 1 — Guardrail
    API->>GRD: input_guardrail_agent({raw_message})
    GRD->>GRD: length check ✔
    GRD->>GRD: PII regex — no SSN/card found
    GRD->>GRD: Presidio — no PII entities
    GRD->>GRD: injection denylist — clean
    GRD->>GRD: wrap in <<<USER_MESSAGE>>>
    GRD-->>API: {sanitized_message, injection_signals=[], redactions=[]}

    note over API,EA: Phase 2 — ADK Pipeline
    API->>ADK: run_adk_inquiry(session_id, sanitized_message)
    ADK->>TA: new_message = Content(role=user, text=sanitized)
    TA->>TA: read sub_agent descriptions\neligibility_agent description matches → route there
    TA->>EA: hand off eligibility question
    EA->>PA: (eligibility_agent calls search_policy internally)
    PA->>PC: Pinecone query: "mortgage DTI limit credit score requirements"
    PC-->>PA: 5 policy chunks
    EA->>EA: ask LLM: apply DTI/LTV rules to $80k income + 710 credit
    EA-->>TA: EligibilityResult: eligible=True, max_loan=~$350k, reason, citations
    TA->>TA: synthesize final answer with citations
    TA-->>ADK: final text response
    ADK-->>API: answer string

    note over API,SS: Phase 3 — Memory Update
    API->>SS: get_or_create(session_id, "buffer")
    SS-->>API: BufferMemory instance
    API->>SS: memory.add("user", original_message)
    API->>SS: memory.add("assistant", answer)
    API->>SS: memory.get_messages()[-6:]

    API-->>U: V2ChatResponse\n{answer, intent="unknown", specialists_called=[]\ninjection_signals=[], redactions=[]\nagent_trace=[guardrail_entry]\nmemory_snapshot=[last 6 msgs]}
```

---

## 8. Agent State Read/Write Map

Every agent in the LangGraph v2 pipeline reads specific state keys and writes specific state keys. This table makes dependencies explicit — useful for understanding why agent ordering matters.

```mermaid
flowchart TD
    subgraph RW["Agent State Access — LangGraph v2"]
        IG_RW["InputGuardrailAgent\n──────────────────────────\nREADS:\n  raw_message\nWRITES:\n  sanitized_message\n  injection_signals\n  redactions\nMANUAL APPEND:\n  agent_trace (existing + [entry])"]

        IR_RW["IntentRouterAgent\n──────────────────────────\nREADS:\n  sanitized_message\nWRITES:\n  intent\n  loan_id_hint\n  specialists_to_run\nMANUAL APPEND:\n  agent_trace"]

        PA_RW["PolicyAgent\n──────────────────────────\nREADS:\n  sanitized_message\nWRITES:\n  policy_chunks\nMANUAL APPEND:\n  specialists_called\n  agent_trace"]

        SA_RW["StatusAgent\n──────────────────────────\nREADS:\n  loan_id_hint\nWRITES:\n  loan_status\nMANUAL APPEND:\n  specialists_called\n  agent_trace"]

        WA_RW["WebSearchAgent\n──────────────────────────\nREADS:\n  sanitized_message\nWRITES:\n  web_results\nMANUAL APPEND:\n  specialists_called\n  agent_trace"]

        EA_RW["EligibilityAgent\n──────────────────────────\nREADS:\n  policy_chunks\n  sanitized_message\nWRITES:\n  eligibility_result\nMANUAL APPEND:\n  specialists_called\n  agent_trace"]

        SY_RW["SynthesisAgent\n──────────────────────────\nREADS:\n  sanitized_message · intent\n  injection_signals\n  policy_chunks\n  loan_status\n  web_results\n  eligibility_result\n  specialists_called\nWRITES:\n  final_answer\nMANUAL APPEND:\n  agent_trace"]
    end

    IG_RW --> IR_RW
    IR_RW --> PA_RW
    IR_RW --> SA_RW
    IR_RW --> WA_RW
    PA_RW --> EA_RW
    PA_RW --> SY_RW
    SA_RW --> SY_RW
    WA_RW --> SY_RW
    EA_RW --> SY_RW
```

---

## 9. Project 1 vs Project 2 — Architecture Comparison

```mermaid
flowchart LR
    subgraph P1["Project 1 — LoanFlow AI"]
        P1_I["Interface: Form (one-shot)"]
        P1_M["Memory: None (stateless)"]
        P1_F["Framework: LangGraph only"]
        P1_A["Audience: Bank reviewer"]
        P1_P["Pipeline: 8 agents\nInputGuardrail→Planner→\nParallel Specialists→\nFraudDetection→Reviewer→\nOutputGuardrail→Evaluation"]
        P1_T["Tools: MCP server (5 tools)\nHTTP SSE transport\nAgents never import tools directly"]
        P1_G["Guardrails: Input + Output\nCitation honesty check\nForbidden phrase check"]
    end

    subgraph P2["Project 2 — LoanInquiry AI"]
        P2_I["Interface: Chat (multi-turn)"]
        P2_M["Memory: BufferMemory + SummaryMemory\n+ ADK InMemorySessionService"]
        P2_F["Framework: LangGraph + Google ADK\n(two implementations)"]
        P2_A["Audience: Loan applicant"]
        P2_P["Pipeline: 7 nodes\nInputGuardrail→IntentRouter→\nSpecialist(s)→Synthesis"]
        P2_T["Tools: Direct function calls\nsearch_policy · get_loan_status · web_search\n(no MCP server)"]
        P2_G["Guardrails: Input only\nInjection hard-stop\nbefore any LLM call"]
    end

    subgraph SHARED["Shared Infrastructure"]
        SH1["Pinecone index: loanflow-ai\ntext-embedding-3-small"]
        SH2["SQLite: loanflow.db\nloan_applications · submitted_documents"]
        SH3[".env: OPENAI_API_KEY · PINECONE_API_KEY\nP2 adds: TAVILY_API_KEY"]
    end

    P1 --> SHARED
    P2 --> SHARED
```

---

## Quick Reference — InquiryState Fields

| Field | Type | Set by | Read by |
|---|---|---|---|
| `session_id` | `str` | API handler | StatusAgent, session_store |
| `raw_message` | `str` | API handler | InputGuardrail |
| `memory_type` | `str` | API handler | session_store |
| `sanitized_message` | `str` | InputGuardrail | IntentRouter, PolicyAgent, WebSearchAgent, EligibilityAgent, Synthesis |
| `injection_signals` | `list[str]` | InputGuardrail | Synthesis (security note) |
| `redactions` | `list[str]` | InputGuardrail | API response |
| `intent` | `str` | IntentRouter | Synthesis (context), routing functions |
| `loan_id_hint` | `str\|None` | IntentRouter | StatusAgent |
| `specialists_to_run` | `list[str]` | IntentRouter | `_route_from_intent`, `_route_from_policy` |
| `policy_chunks` | `list[dict]` | PolicyAgent | EligibilityAgent, Synthesis |
| `loan_status` | `dict\|None` | StatusAgent | Synthesis |
| `web_results` | `list[dict]` | WebSearchAgent | Synthesis |
| `eligibility_result` | `dict\|None` | EligibilityAgent | Synthesis |
| `final_answer` | `str` | SynthesisAgent | API handler → response |
| `agent_trace` | `list[dict]` | Every node (manual append) | API handler → response |
| `specialists_called` | `list[str]` | PolicyAgent, StatusAgent, WebSearchAgent, EligibilityAgent | Synthesis, API response |
| `memory_snapshot` | `list[dict]` | API handler (after graph) | Response only |
