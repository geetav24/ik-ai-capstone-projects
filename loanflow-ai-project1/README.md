# LoanFlow AI — Project 1 Capstone

AI-powered loan review assistant using **React + FastAPI + LangGraph + Ollama/OpenAI-ready LLM service**.

## Goal
A loan reviewer enters borrower/loan details and a question. The backend runs a LangGraph workflow with 3 agents:

1. **Document Check Agent** — identifies missing documents.
2. **Risk Review Agent** — flags basic loan risks.
3. **Guardrail Agent** — prevents the AI from making final approve/reject decisions and requires human review.

The UI displays the agent result and evaluation score.

## Recommended Friday MVP
- React UI with one loan review form.
- FastAPI backend with `/agent/review`.
- LangGraph workflow wired with 3 agent nodes.
- Local LLM via Ollama, with fallback mock response.
- Rule-based evaluation.

## Local setup

### 1. Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Test:
```bash
curl http://localhost:8000/health
```

### 2. Ollama optional
Install Ollama, then:
```bash
ollama pull gemma2:2b
ollama serve
```

The app can run without Ollama using `LLM_PROVIDER=mock`.

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

## Environment
Backend `.env`:
```env
LLM_PROVIDER=mock
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma2:2b
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

## Later increments
- Add PDF upload and RAG with Qdrant.
- Add LLM-as-judge evaluation.
- Deploy frontend to Vercel or S3/CloudFront.
- Deploy backend to AWS ECS/Fargate or EC2.
