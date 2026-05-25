# LoanFlow AI — Flow Diagrams

> All diagrams below use [Mermaid](https://mermaid.js.org/) syntax.
> Render them in GitHub, VS Code (Markdown Preview with Mermaid plugin), or paste into [mermaid.live](https://mermaid.live).

---

## Table of Contents

1. [Main LangGraph Pipeline](#1-main-langgraph-pipeline)
2. [LangGraph State — Memory Flow Through Nodes](#2-langgraph-state--memory-flow-through-nodes)
3. [MCP Architecture — How Tools Are Called](#3-mcp-architecture--how-tools-are-called)
4. [InputGuardrail — Detailed Flow](#4-inputguardrail--detailed-flow)
5. [OutputGuardrail — Detailed Flow](#5-outputguardrail--detailed-flow)
6. [Routing Decision Tree](#6-routing-decision-tree)
7. [Database — Two Access Paths](#7-database--two-access-paths)
8. [Agent State Read/Write Map](#8-agent-state-readwrite-map)

---

## 1. Main LangGraph Pipeline

This is the full agent pipeline as it runs for every `POST /review` request. Solid arrows are unconditional edges; diamond shapes are conditional routing functions. The `parallel_specialists` box runs three agents concurrently inside a single node using `asyncio.gather()`.

```mermaid
flowchart TD
    A["HTTP POST /review\nLoanReviewRequest"] --> B["run_loan_review\nInitialise LoanReviewState\nall fields = None / empty"]
    B --> IG

    IG["InputGuardrail\n① Length cap — reject if > 2000 chars\n② Financial PII regex: SSN · bank acct · credit card\n③ Presidio: PERSON · EMAIL · PHONE\n④ Injection denylist — 30 phrases · 5 categories\n⑤ Delimiter wrap <<<USER_QUESTION>>>"]

    IG -->|"sanitized_input\ninjection_signals\nagent_trace +"| PL

    PL["PlannerAgent\nRule-based — no LLM\nloan_amount > 500 k?\nincome / annual_income > 5.0?\nzero income?\nself_employed + loan > 200 k?"]

    PL -->|"plan\nagent_trace +"| PS

    subgraph PS["Parallel Specialists — asyncio.gather()"]
        RA["RetrievalAgent\nLLM picks search_policy_tool\nvia MCP → Pinecone\nReturns Citation list"]
        DC["DocumentCheckAgent\nMCP: search_policy\n+ extract_requirements\nsubmitted vs required"]
        RR["RiskReviewAgent\nRule-based · 5 flags\nincome_ratio_anomaly\nlow_credit_score\nmissing_income_evidence\nzero_income\nno_documents_submitted"]
    end

    PS -->|"retrieved_context\ndoc_check_result\nrisk_assessment\nagent_trace +"| CE1

    CE1{"should_run_fraud?\nhigh loan OR ratio anomaly\nOR zero income\nOR self_employed high loan\nOR risk flag matches"}

    CE1 -->|"YES"| FD
    CE1 -->|"NO"| RV

    FD["FraudDetectionAgent\nMCP: check_fraud_signals_tool\nDeterministic math thresholds\nReturns signals + confidence"]
    FD -->|"fraud_finding\nagent_trace +"| RV

    RV["ReviewerAgent\nBuilds system prompt:\n  retrieved policy chunks\n  risk flags + fraud signals\n  missing docs\nCalls gpt-4o — ask_llm_quality\nDetermines requires_human_review"]

    RV -->|"reviewer_guidance\nagent_trace +"| OG

    OG["OutputGuardrail\n① Forbidden phrases: approved · denied · rejected\n② Citation honesty: cited chunk must be in retrieved_context\n③ PII scrub: financial regexes\nOn violation → swap safe fallback"]

    OG -->|"guardrail_result\nguardrails_applied +\nagent_trace +"| CE2

    CE2{"should_use_safe_fallback?\nguardrail_result.passed?"}

    CE2 -->|"PASS"| EV
    CE2 -->|"FAIL"| SF

    SF["SafeFallback Node\nInjects canned answer\nrequires_human_review = True\nguardrails_applied += output_guardrail_fallback"]

    SF -->|"reviewer_guidance updated\nagent_trace +"| EV

    EV["EvaluationAgent\nLLM-as-Judge — gpt-4o · temperature=0\nScores: decision_quality\ngrounding_score 0.0–1.0\nhallucination_risk\npolicy_compliance\nreasoning"]

    EV -->|"evaluation\nagent_trace +"| END(["LoanReviewResponse\nJSON → HTTP client"])
```

---

## 2. LangGraph State — Memory Flow Through Nodes

The `LoanReviewState` TypedDict is the pipeline's shared memory. No agent imports another agent's module — they communicate exclusively through state keys. The key design insight: each node **returns a partial dict** and LangGraph **merges** it into the running state.

Two fields are annotated with `Annotated[list, operator.add]` which makes them **append-only** — each node can only add entries, never overwrite earlier ones. This is how `agent_trace` accumulates a full audit log across all 9 nodes without any explicit coordination.

```mermaid
flowchart LR
    INIT(["Initial State\napplication ✔\nraw_question ✔\nall others = None / []"])

    IG_OUT["After InputGuardrail\nsanitized_input ✔\ninjection_signals ✔\nagent_trace = [ig_entry]"]

    PL_OUT["After PlannerAgent\nplan ✔\nagent_trace = [ig_entry, pl_entry]"]

    PS_OUT["After parallel_specialists\nretrieved_context ✔\ndoc_check_result ✔\nrisk_assessment ✔\nagent_trace = [..., ra_entry, dc_entry, rr_entry]"]

    FD_OUT["After FraudDetectionAgent\nfraud_finding ✔\nagent_trace = [..., fd_entry]"]

    RV_OUT["After ReviewerAgent\nreviewer_guidance ✔\nagent_trace = [..., rv_entry]"]

    OG_OUT["After OutputGuardrail\nguardrail_result ✔\n± reviewer_guidance updated\nguardrails_applied = [tag]\nagent_trace = [..., og_entry]"]

    EV_OUT["After EvaluationAgent\nevaluation ✔\nagent_trace = [..., ev_entry]  ← full trace"]

    INIT --> IG_OUT --> PL_OUT --> PS_OUT --> FD_OUT --> RV_OUT --> OG_OUT --> EV_OUT
```

### Append-only accumulation detail

```mermaid
flowchart LR
    subgraph TRACE["agent_trace — Annotated[list, operator.add]"]
        T1["[ig_entry]"] --> T2["[ig, pl]"] --> T3["[ig, pl, ra, dc, rr]"] --> T4["[ig, pl, ra, dc, rr, fd]"] --> T5["[..., rv, og, ev]"]
    end

    subgraph GA["guardrails_applied — Annotated[list, operator.add]"]
        G1["[]"] --> G2["['input_guardrail'] if PII/injection"] --> G3["['input_guardrail', 'output_guardrail'] if violation"]
    end
```

---

## 3. MCP Architecture — How Tools Are Called

The MCP server is a **completely separate process** (port 8001). The FastAPI backend connects to it once at startup and reuses the SSE session for every request. Agents call `call_tool(name, args)` — they never import `registry.py` or any tool implementation.

```mermaid
sequenceDiagram
    participant API as FastAPI /review
    participant WF as LangGraph Workflow
    participant AG as Agent (e.g. RetrievalAgent)
    participant TR as tool_runner.py
    participant MC as MCP Client (client.py)
    participant MS as MCP Server (port 8001)
    participant EXT as Pinecone / SQLite

    note over API,MC: Startup (once)
    API->>MC: init_mcp_client()
    MC->>MS: open SSE stream at MCP_SERVER_URL
    MS-->>MC: session initialised

    note over API,EXT: Per request
    API->>WF: run_loan_review(application, question)
    WF->>AG: await retrieval_agent(state)
    AG->>TR: run_with_tools(system_prompt, user_prompt)
    TR->>TR: call LLM with tool schemas
    note right of TR: LLM decides to call search_policy_tool
    TR->>MC: call_tool("search_policy_tool", {query, top_k})
    MC->>MS: HTTP SSE — call_tool request
    MS->>EXT: Pinecone.query(vector, top_k)
    EXT-->>MS: [{filename, chunk_index, score, text}, ...]
    MS-->>MC: JSON over SSE
    MC-->>TR: parsed list[dict]
    TR-->>AG: {content, tool_calls_made: [{tool, args, result}]}
    AG->>AG: extract chunks from tool_calls_made[].result
    AG-->>WF: {retrieved_context, agent_trace}
    WF-->>API: final LoanReviewState

    note over API,MC: Shutdown (once)
    API->>MC: shutdown_mcp_client()
    MC->>MS: close SSE session
```

---

## 4. InputGuardrail — Detailed Flow

This is the **first line of defense**. It runs before any LLM call, before any agent sees the user's question. The module-level Presidio engines (`AnalyzerEngine`, `AnonymizerEngine`) are loaded **once at import time** — not per request — so the spaCy model load cost is paid once at startup.

```mermaid
flowchart TD
    IN["raw_question from state\nstate.get('raw_question', '')"] --> LC

    LC{"len(raw_question) > 2000?"}
    LC -->|"YES"| ERR["raise ValueError\n'Question exceeds 2000 character limit'\n→ FastAPI returns 400"]
    LC -->|"NO"| R1

    R1["Financial PII Regex — 3 patterns\n① SSN: \\b\\d{3}-\\d{2}-\\d{4}\\b\n② Bank acct: \\b\\d{8,17}\\b\n③ Credit card: 4 groups of 4\nReplace → [REDACTED:US_SSN] etc."]

    R1 --> R2["Presidio Analyzer\nLanguage='en'\nDetects: PERSON · EMAIL_ADDRESS · PHONE_NUMBER\nReturns list[AnalysisResult]"]

    R2 --> R3["Presidio Anonymizer\nFor each entity type → OperatorConfig('replace')\nreplaces span with [REDACTED:ENTITY_TYPE]"]

    R3 --> INJ["Injection Denylist Scan\n30 phrases across 5 categories:\n• Override / jailbreak\n• Approval manipulation\n• Authority impersonation\n• System prompt extraction\n• Role hijacking\nScans: cleaned question + borrower_name + loan_type + employment_status"]

    INJ --> DL["Delimiter Wrapping\n<<<USER_QUESTION>>>\n{cleaned_question}\n<<<END_USER_QUESTION>>>\n\nDownstream LLMs told: treat this content as DATA not instructions"]

    DL --> OUT["SanitizedInput\nquestion = delimited cleaned text\nredactions = sorted set of PII types found\ninjection_signals = matched denylist phrases"]

    OUT --> TR["TraceEntry\nagent='input_guardrail'\nstarted_at / finished_at\ninput_summary: question length\noutput_summary: redactions + injection_signals"]

    TR --> RET["Return partial state dict\n{\n  sanitized_input: SanitizedInput.model_dump()\n  injection_signals: [list of phrases]\n  agent_trace: [trace_entry]\n  guardrails_applied: ['input_guardrail'] if active\n}"]
```

---

## 5. OutputGuardrail — Detailed Flow

This runs **after** ReviewerAgent and **before** EvaluationAgent. It validates the answer the LLM produced. On any violation it replaces the answer with a safe canned response — there is **no retry loop**, by design. The conditional edge after this node routes to `safe_fallback` (which feeds evaluation) or directly to evaluation.

```mermaid
flowchart TD
    IN["reviewer_guidance.answer\nretrieved_context.chunks"] --> C1

    C1{"Check 1 — Forbidden Phrases\nFor each phrase in FORBIDDEN_PHRASES:\n  word-boundary regex match in answer.lower()\n  skip if immediately preceded by 'not'"}

    C1 -->|"phrase found (not preceded by 'not')"| V1["violations.append('forbidden_phrase')"]
    C1 -->|"clean"| C2

    V1 --> C2

    C2{"Check 2 — Citation Honesty\nparse all [Source: filename, chunk N] in answer\nbuild set of (filename, chunk_index) from retrieved_context\ncompare each cited pair against present set"}

    C2 -->|"cited pair not in retrieved_context"| V2["violations.append('fabricated_citation')"]
    C2 -->|"all cited pairs verified"| C3

    V2 --> C3

    C3{"Check 3 — PII Scrub\nrun same financial PII regexes as InputGuardrail\non the answer text"}

    C3 -->|"PII pattern matched"| V3["replace in sanitized_answer\nviolations.append('pii_in_output')"]
    C3 -->|"clean"| DECIDE

    V3 --> DECIDE

    DECIDE{"len(violations) > 0?"}

    DECIDE -->|"YES"| FAIL["GuardrailResult(passed=False, violations=violations)\nreviewer['answer'] = SAFE_FALLBACK_ANSWER\nreviewer['requires_human_review'] = True\nguardrails_applied += ['output_guardrail']"]

    DECIDE -->|"NO"| PASS["GuardrailResult(passed=True, violations=[])\nif PII was scrubbed: reviewer['answer'] = sanitized_answer\nguardrails_applied stays empty"]

    FAIL --> CE["Conditional Edge: should_use_safe_fallback\nguardrail_result.passed = False → route to safe_fallback node"]
    PASS --> CE2["Conditional Edge: should_use_safe_fallback\nguardrail_result.passed = True → route directly to evaluation"]
```

---

## 6. Routing Decision Tree

Two routing decisions happen in the pipeline. The **first** (PlannerAgent) fires before the parallel specialists — it uses application fields only. The **second** (should_run_fraud conditional edge) fires after parallel specialists — it also has access to the RiskReviewAgent's output flags, so it can catch anomalies the planner couldn't see.

```mermaid
flowchart TD
    APP["LoanApplication\nloan_amount\nannual_income\nemployment_status"] --> PA

    subgraph PA["PlannerAgent — runs BEFORE specialists"]
        RA1{"loan_amount > 500,000?"}
        RA1 -->|"YES"| FRAUD_P["plan includes\nfraud_detection"]
        RA1 -->|"NO"| RA2{"annual_income == 0?"}
        RA2 -->|"YES"| FRAUD_P
        RA2 -->|"NO"| RA3{"loan_amount / annual_income > 5.0?"}
        RA3 -->|"YES"| FRAUD_P
        RA3 -->|"NO"| RA4{"employment_status == 'self_employed'\nAND loan_amount > 200,000?"}
        RA4 -->|"YES"| FRAUD_P
        RA4 -->|"NO"| STD["Standard path\nplan does NOT include fraud_detection"]
    end

    FRAUD_P --> SPEC["Parallel Specialists run\nRiskReviewAgent produces flags"]
    STD --> SPEC

    SPEC --> CE

    subgraph CE["should_run_fraud() — conditional edge AFTER specialists"]
        CE1{"Same loan_amount checks\n(repeated for safety)"}
        CE1 -->|"YES"| FRAUD_CE["route to fraud_detection"]
        CE1 -->|"NO"| CE2{"'income_ratio_anomaly'\nin risk_assessment.flags?"}
        CE2 -->|"YES"| FRAUD_CE
        CE2 -->|"NO"| CE3{"'velocity_anomaly'\nin risk_assessment.flags?"}
        CE3 -->|"YES"| FRAUD_CE
        CE3 -->|"NO"| SKIP["route directly to reviewer\nskip FraudDetectionAgent"]
    end
```

---

## 7. Database — Two Access Paths

A key architectural rule: **agents never import `db/`**. FastAPI routes query SQLite directly for list/detail endpoints. Agents reach SQLite only through MCP tools. This separation means the MCP server could be replaced with a different data source and agents wouldn't change at all.

```mermaid
flowchart LR
    subgraph FAST["FastAPI Routes — direct SQLite"]
        R1["GET /loans\nlist all loan_applications"]
        R2["GET /loans/{loan_id}\nfetch application + submitted_documents"]
        R3["POST /review\n→ save review_record after pipeline"]
        R1 --> DB
        R2 --> DB
        R3 --> DB
    end

    subgraph AGENTS["Agents — through MCP only"]
        A1["FraudDetectionAgent\ncall_tool('check_fraud_signals_tool')"]
        A2["DocumentCheckAgent\ncall_tool('get_submitted_documents_tool')\ncall_tool('extract_requirements_tool')"]
        A3["RetrievalAgent\ncall_tool('search_policy_tool')"]
        A1 --> MC
        A2 --> MC
        A3 --> MC
        MC["MCP Client\nclient.py\nSSE session"] --> MS["MCP Server\nregistry.py\nport 8001"]
        MS --> DB
    end

    DB[("SQLite\nloanflow.db\n─────────────────\nloan_applications\n  loan_id PK\n  borrower_name\n  loan_type · loan_amount\n  annual_income · credit_score\n  employment_status\n─────────────────\nsubmitted_documents\n  id PK · loan_id FK\n  doc_type · uploaded_at\n  parsed_fields JSON\n─────────────────\nreview_records\n  id PK · loan_id FK\n  question · response JSON\n  agent_trace JSON\n  evaluation JSON\n  guardrails_applied JSON")]
```

---

## 8. Agent State Read/Write Map

This diagram summarises exactly which state keys each agent reads and which it writes back. Every agent returns a **partial dict** — LangGraph merges it. The `+` notation means the field uses `Annotated[list, operator.add]` (append-only).

```mermaid
flowchart TD
    subgraph READS_WRITES["Agent → State Key Access"]
        IG_RW["InputGuardrail\n──────────────────────────\nREADS:\n  raw_question\n  application (borrower_name etc.)\nWRITES:\n  sanitized_input\n  injection_signals\nAPPENDS (+):\n  agent_trace\n  guardrails_applied"]

        PL_RW["PlannerAgent\n──────────────────────────\nREADS:\n  application\nWRITES:\n  plan\nAPPENDS (+):\n  agent_trace"]

        RA_RW["RetrievalAgent\n──────────────────────────\nREADS:\n  application\n  sanitized_input.question\nWRITES:\n  retrieved_context\nAPPENDS (+):\n  agent_trace"]

        DC_RW["DocumentCheckAgent\n──────────────────────────\nREADS:\n  application (loan_type, submitted_documents)\nWRITES:\n  doc_check_result\nAPPENDS (+):\n  agent_trace"]

        RR_RW["RiskReviewAgent\n──────────────────────────\nREADS:\n  application\n  doc_check_result.missing\nWRITES:\n  risk_assessment\nAPPENDS (+):\n  agent_trace"]

        FD_RW["FraudDetectionAgent\n──────────────────────────\nREADS:\n  application\n  risk_assessment\nWRITES:\n  fraud_finding\nAPPENDS (+):\n  agent_trace"]

        RV_RW["ReviewerAgent\n──────────────────────────\nREADS:\n  retrieved_context\n  risk_assessment\n  fraud_finding\n  doc_check_result\n  sanitized_input.question\n  injection_signals\nWRITES:\n  reviewer_guidance\nAPPENDS (+):\n  agent_trace"]

        OG_RW["OutputGuardrail\n──────────────────────────\nREADS:\n  reviewer_guidance.answer\n  retrieved_context.chunks\nWRITES:\n  guardrail_result\n  reviewer_guidance (if PII scrubbed or violation)\nAPPENDS (+):\n  agent_trace\n  guardrails_applied"]

        EV_RW["EvaluationAgent\n──────────────────────────\nREADS:\n  reviewer_guidance.answer\n  retrieved_context.chunks\n  risk_assessment.flags\n  fraud_finding.signals\nWRITES:\n  evaluation\nAPPENDS (+):\n  agent_trace"]
    end

    IG_RW --> PL_RW --> RA_RW
    PL_RW --> DC_RW
    PL_RW --> RR_RW
    RA_RW --> FD_RW
    DC_RW --> FD_RW
    RR_RW --> FD_RW
    FD_RW --> RV_RW --> OG_RW --> EV_RW
```

---

## Quick Reference: State Fields at a Glance

| State Field | Type | Set by | Read by | Append-only? |
|---|---|---|---|---|
| `application` | `dict` | Init | All agents | No |
| `raw_question` | `str` | Init | InputGuardrail | No |
| `sanitized_input` | `Optional[dict]` | InputGuardrail | RetrievalAgent, ReviewerAgent | No |
| `injection_signals` | `list[str]` | InputGuardrail | ReviewerAgent, should_run_fraud | No |
| `plan` | `Optional[dict]` | PlannerAgent | (routing reference) | No |
| `retrieved_context` | `Optional[dict]` | RetrievalAgent | ReviewerAgent, OutputGuardrail, EvaluationAgent | No |
| `doc_check_result` | `Optional[dict]` | DocumentCheckAgent | RiskReviewAgent, ReviewerAgent | No |
| `risk_assessment` | `Optional[dict]` | RiskReviewAgent | FraudDetectionAgent, ReviewerAgent, should_run_fraud, EvaluationAgent | No |
| `fraud_finding` | `Optional[dict]` | FraudDetectionAgent | ReviewerAgent, EvaluationAgent | No |
| `reviewer_guidance` | `Optional[dict]` | ReviewerAgent | OutputGuardrail (reads + updates), FastAPI route | No |
| `guardrail_result` | `Optional[dict]` | OutputGuardrail | should_use_safe_fallback | No |
| `evaluation` | `Optional[dict]` | EvaluationAgent | FastAPI route | No |
| `agent_trace` | `list[dict]` | Every node | FastAPI route | **YES** |
| `guardrails_applied` | `list[str]` | InputGuardrail, OutputGuardrail, SafeFallback | FastAPI route | **YES** |
