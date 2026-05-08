```mermaid
flowchart TD
    UI[React UI] --> API[FastAPI Backend]

    API --> Upload[Document Upload API]
    Upload --> Parser[PDF Parser]
    Parser --> Chunker[Text Chunker]
    Chunker --> Embed[OpenAI Embeddings]
    Embed --> Pinecone[(Pinecone Vector DB)]

    API --> Review[Loan Review API]
    Review --> Graph[LangGraph Workflow]

    Graph --> RetrievalAgent[Retrieval Agent]
    RetrievalAgent --> LoanPolicyTool[Loan Policy Tool]
    LoanPolicyTool --> Pinecone

    Graph --> DocumentCheckAgent[Document Check Agent]
    Graph --> RiskReviewAgent[Risk Review Agent]
    Graph --> GuardrailAgent[Guardrail Agent]
    Graph --> ReviewerAgent[Reviewer Agent]
    Graph --> EvaluationAgent[Evaluation Agent / LLM-as-Judge]

    ReviewerAgent --> LLM[OpenAI LLM]
    EvaluationAgent --> JudgeLLM[OpenAI LLM Judge]

    Graph --> Response[Structured Response]
    Response --> UI

    Response --> Citations[Citations]
    Response --> Trace[Agent Trace]
    Response --> Evaluation[Evaluation Result]

```mermaid

### Architecture Overview

LoanFlow AI is a RAG-powered agentic loan review assistant.

The system allows users to upload loan policy documents, extracts and chunks the document text, generates OpenAI embeddings, and stores the vectors in Pinecone. When a reviewer submits a loan review question, the LangGraph workflow retrieves relevant policy chunks through a LoanPolicyTool and passes that grounded context to specialized agents.

The workflow includes document checking, risk review, guardrail enforcement, reviewer guidance generation, and an LLM-as-Judge evaluation step. The response includes the AI recommendation, missing documents, risk flags, retrieved policy context, citations, guardrails, agent trace, and evaluation results.