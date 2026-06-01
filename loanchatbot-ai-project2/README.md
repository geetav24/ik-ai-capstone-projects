![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![Google ADK](https://img.shields.io/badge/Google_ADK-Multi--Agent-4285F4?logo=google&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini-412991?logo=openai&logoColor=white)
![Pinecone](https://img.shields.io/badge/Pinecone-VectorDB-6B46C1)
![Tavily](https://img.shields.io/badge/Tavily-WebSearch-orange)

# LoanInquiry AI — Conversational Loan Assistant

LoanInquiry AI is a multi-agent conversational chatbot that helps bank customers and loan reviewers get instant answers about loan policy, application status, and eligibility.

Built as IK SDE Pathway Capstone Project 2 — extends Project 1 (LoanFlow AI) with a Google ADK multi-agent pipeline, conversational memory, and PII guardrails.

---

## Does Project 1 need to be running?

**No.** Project 2 does not call Project 1's API. But it does share two artifacts:

| Artifact | Where it lives | What to do |
|---|---|---|
| Pinecone index (`loanflow-ai`) | Pinecone cloud | Run `generate_policy.py` in Project 1 once |
| Loan applications DB (`loanflow.db`) | `../loanflow-ai-project1/backend/loanflow.db` | Exists after Project 1 is set up |

Project 2 queries Pinecone and SQLite **directly** using the same API keys. Project 1's backend server can be stopped.

---

## Architecture

### v2 endpoint — Google ADK multi-agent pipeline (`POST /v2/chat`)

```
User message
    ↓
FastAPI /v2/chat
    ↓
InputGuardrailAgent  ← PII redaction (Presidio) + injection denylist
    ↓ (sanitized message)
Google ADK Runner
    └── triage_agent  (LlmAgent — reads descriptions, routes)
          ├── policy_agent       → search_policy (Pinecone RAG)
          ├── status_agent       → get_loan_status (SQLite)
          ├── web_search_agent   → web_search (Tavily)
          └── eligibility_agent  → search_policy + LLM calc
    ↓
V2ChatResponse (answer + injection_signals + redactions + agent_trace)
```

**How ADK routing works:** The triage `LlmAgent` reads each specialist's `description` field and decides which sub-agent to hand off to. No explicit routing code — the LLM decides.

### v1 endpoint — single-agent (`POST /chat`, preserved for backwards compat)

```
User message → LoanInquiry Agent → [search_policy | get_loan_status | web_search] → answer
```

### Memory types

| Type | How it works | When to use |
|---|---|---|
| Buffer | Keeps last N messages verbatim | Short conversations (≤ 10 turns) |
| Summary | LLM compresses old turns into a rolling paragraph | Long conversations |

---

## Agents

| Agent | Framework | Responsibility |
|---|---|---|
| `InputGuardrailAgent` | Plain Python | PII redaction, injection detection, length cap |
| `triage_agent` | ADK `LlmAgent` | Classify intent, route to specialist, synthesize answer |
| `policy_agent` | ADK `LlmAgent` | RAG over loan policy KB (Pinecone) |
| `status_agent` | ADK `LlmAgent` | Loan application status lookup (SQLite) |
| `web_search_agent` | ADK `LlmAgent` | External web search (Tavily) |
| `eligibility_agent` | ADK `LlmAgent` | Loan eligibility + max loan estimate (policy-grounded) |

---

## Setup

### Prerequisites

- Python 3.11+
- Node 18+ (for frontend)
- Project 1 set up (Pinecone index populated, `loanflow.db` exists)

### Step 1 — Verify Project 1 artifacts exist

```bash
# From the ik-ai-capstone-projects/ directory:

# Check the DB is there
ls loanflow-ai-project1/backend/loanflow.db

# If it doesn't exist, set up Project 1 first:
#   cd loanflow-ai-project1
#   Follow Project 1's README to populate the DB and Pinecone index
```

### Step 2 — Create Project 2's `.env`

```bash
cd loanfchatbot-ai-project2/backend
cp .env.example .env
```

Then edit `.env` and fill in your keys. All values are the **same as Project 1's** except `TAVILY_API_KEY`.

```
OPENAI_API_KEY=sk-...          # same as Project 1
PINECONE_API_KEY=pcsk_...      # same as Project 1
PINECONE_INDEX_NAME=loanflow-ai  # same as Project 1
TAVILY_API_KEY=tvly-...        # get free key at tavily.com
```

### Step 3 — Install dependencies

```bash
cd loanfchatbot-ai-project2/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# spaCy model needed by Presidio (PII detection)
python -m spacy download en_core_web_sm
```

### Step 4 — Run the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8002
```

> Use port **8002** to avoid clashing with Project 1 (port 8000) and its MCP server (port 8001).

### Step 5 — Run the frontend (optional)

```bash
cd frontend
npm install && npm run dev
```

---

## API Reference

### `POST /v2/chat` — multi-agent ADK pipeline

```json
{
  "session_id": "user-abc",
  "message": "What documents do I need for a mortgage?",
  "memory_type": "buffer"
}
```

Response:
```json
{
  "session_id": "user-abc",
  "answer": "For a mortgage you need ... [Source: loan_policy.pdf, chunk 3]",
  "intent": "unknown",
  "specialists_called": [],
  "injection_signals": [],
  "redactions": [],
  "agent_trace": [
    {
      "agent": "input_guardrail",
      "started_at": "...",
      "finished_at": "...",
      "input_summary": "message_length=48",
      "output_summary": "redactions=[], injection_signals=[]"
    }
  ],
  "memory_snapshot": [...]
}
```

### `POST /chat` — v1 single-agent (preserved)

```json
{ "session_id": "user-abc", "message": "What is the status of LN-004?", "memory_type": "buffer" }
```

### `DELETE /chat/{session_id}` — clear session memory

### `GET /health` — health check

---

## Running Tests

```bash
cd backend
pytest -v
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key (same as Project 1) |
| `PINECONE_API_KEY` | Yes | Pinecone API key (same as Project 1) |
| `PINECONE_INDEX_NAME` | Yes | Pinecone index name — must be `loanflow-ai` |
| `EMBEDDING_MODEL` | No | Defaults to `text-embedding-3-small` |
| `TAVILY_API_KEY` | Yes | Tavily web search — get free key at tavily.com |
| `DB_PATH` | No | Path to `loanflow.db`. Defaults to `../loanflow-ai-project1/backend/loanflow.db` |

---

## Project Structure

```
loanfchatbot-ai-project2/
├── backend/
│   ├── app/
│   │   ├── agents/               # 6 agent implementations
│   │   │   ├── input_guardrail.py
│   │   │   ├── intent_router.py
│   │   │   ├── policy_agent.py
│   │   │   ├── status_agent.py
│   │   │   ├── web_search_agent.py
│   │   │   ├── eligibility_agent.py
│   │   │   └── synthesis_agent.py
│   │   ├── workflows/
│   │   │   └── adk_workflow.py   # ADK triage + sub_agents wiring
│   │   ├── tools/                # tool implementations
│   │   ├── memory/               # BufferMemory + SummaryMemory
│   │   ├── models/models.py      # Pydantic contracts
│   │   └── main.py               # FastAPI app
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── docs/
│   └── USE_CASES.md
└── README.md
```

---

## Relationship to Project 1

```
loanflow-ai-project1/                 loanfchatbot-ai-project2/
├── generate_policy.py  ──────────►  Pinecone index (shared, read-only)
├── backend/loanflow.db ──────────►  SQLite DB (read-only via DB_PATH)
├── backend/.env        ──(copy)──►  backend/.env (same keys + TAVILY)
└── backend/ (server)               (NOT needed — no HTTP dependency)
```
