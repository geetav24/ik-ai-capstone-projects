"""
Tool registry + 5 tool implementations (USE_CASES.md §5).

Each tool is a class that conforms to the Tool Protocol.
Agents call tools like:
    result = await registry.call("loan_policy_search", {"query": "...", "top_k": 5})

Tools implemented here:
  1. loan_policy_search        — Pinecone semantic search over policy docs
  2. fraud_signal_check        — mock fraud DB lookup
  3. document_required_lookup  — what docs are required for a given loan type
  4. loan_application_lookup   — fetch a stored application by loan_id (SQLite)
  5. submitted_documents_lookup — fetch submitted docs for an application (SQLite)
"""
from typing import Any
from app.core.tools.protocol import Tool


# ---------------------------------------------------------------------------
# Tool 1: loan_policy_search
# ---------------------------------------------------------------------------

class LoanPolicySearchTool:
    name = "loan_policy_search"
    description = "Semantic search over indexed loan policy documents. Returns top-k relevant chunks."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def call(self, args: dict) -> dict:
        """
        TODO: implement semantic search via Pinecone.

        Steps:
        1. Generate an embedding for args["query"] using the OpenAI embeddings client
           (reuse app/services/embedding_service.py — it's already wired to Pinecone).
        2. Call Pinecone index.query(...) with the embedding and top_k=args.get("top_k", 5).
        3. Map matches to a list of dicts:
             { "filename": ..., "chunk_index": ..., "score": ..., "text": ... }
        4. Return { "chunks": [...] }

        The caller (RetrievalAgent) will wrap this into a RetrievedContext object.
        """
        raise NotImplementedError("TODO: implement loan_policy_search")


# ---------------------------------------------------------------------------
# Tool 2: fraud_signal_check
# ---------------------------------------------------------------------------

class FraudSignalCheckTool:
    name = "fraud_signal_check"
    description = "Check a loan application against fraud signals. Returns synthetic signals for demo."
    input_schema = {
        "type": "object",
        "properties": {
            "loan_id":           {"type": "string"},
            "loan_amount":       {"type": "number"},
            "annual_income":     {"type": "number"},
            "employment_status": {"type": "string"},
            "credit_score":      {"type": "integer"},
        },
        "required": ["loan_id", "loan_amount", "annual_income"],
    }

    async def call(self, args: dict) -> dict:
        """
        TODO: implement rule-based fraud signal generation (mock — no real fraud DB).

        Signals to detect and return:
        - "income_ratio_anomaly"   if loan_amount / annual_income > 5
        - "low_credit_high_amount" if credit_score < 600 and loan_amount > 100_000
        - "self_employed_high_loan" if employment_status == "self_employed" and loan_amount > 200_000
        - "zero_income"            if annual_income == 0

        Return format:
          { "signals": ["income_ratio_anomaly", ...], "confidence": 0.0–1.0 }

        Confidence rule of thumb: 0.3 per signal, capped at 0.9.
        Keep this deterministic (no randomness) so tests are stable.
        """
        raise NotImplementedError("TODO: implement fraud_signal_check")


# ---------------------------------------------------------------------------
# Tool 3: document_required_lookup
# ---------------------------------------------------------------------------

class DocumentRequiredLookupTool:
    name = "document_required_lookup"
    description = "Returns the list of required documents for a given loan type, sourced from policy."
    input_schema = {
        "type": "object",
        "properties": {
            "loan_type": {
                "type": "string",
                "enum": ["personal", "mortgage", "auto", "business"],
            }
        },
        "required": ["loan_type"],
    }

    async def call(self, args: dict) -> dict:
        """
        TODO: implement required-doc lookup.

        Option A (simpler): hardcode a dict mapping loan_type → required docs.
        This is fine for v2 — the list is small and stable.

        Option B (stretch): semantic search the Pinecone policy index for
        "required documents for {loan_type} loan" and parse the results.
        Only do B if you have extra time — A is sufficient for the rubric.

        Suggested Option A table:
          "personal":  ["pay_stub", "bank_statement", "id"]
          "mortgage":  ["pay_stub", "bank_statement", "tax_return", "id", "property_appraisal"]
          "auto":      ["pay_stub", "id"]
          "business":  ["tax_return", "bank_statement", "id", "employment_letter"]

        Return format: { "required_documents": ["pay_stub", "bank_statement", ...] }
        """
        raise NotImplementedError("TODO: implement document_required_lookup")


# ---------------------------------------------------------------------------
# Tool 4: loan_application_lookup
# ---------------------------------------------------------------------------

class LoanApplicationLookupTool:
    name = "loan_application_lookup"
    description = "Fetch a stored loan application by loan_id from the SQLite database."
    input_schema = {
        "type": "object",
        "properties": {
            "loan_id": {"type": "string"}
        },
        "required": ["loan_id"],
    }

    async def call(self, args: dict) -> dict:
        """
        TODO: fetch one LoanApplicationTable row by primary key.

        Steps:
        1. Open a Session (import engine from app.db.database).
        2. session.get(LoanApplicationTable, args["loan_id"])
        3. If not found, raise ValueError(f"Loan {loan_id} not found")
        4. Return the row as a plain dict (use model.model_dump() or __dict__).

        Return format: { "application": { ...fields... } }

        Note: agents call this tool, not the FastAPI routes.
        FastAPI routes can query SQLite directly — two paths, two purposes.
        """
        raise NotImplementedError("TODO: implement loan_application_lookup")


# ---------------------------------------------------------------------------
# Tool 5: submitted_documents_lookup
# ---------------------------------------------------------------------------

class SubmittedDocumentsLookupTool:
    name = "submitted_documents_lookup"
    description = "Fetch all submitted documents for a given loan_id from SQLite."
    input_schema = {
        "type": "object",
        "properties": {
            "loan_id": {"type": "string"}
        },
        "required": ["loan_id"],
    }

    async def call(self, args: dict) -> dict:
        """
        TODO: query SubmittedDocumentTable for all rows matching loan_id.

        Steps:
        1. Open a Session.
        2. SELECT * FROM submitted_documents WHERE loan_id = args["loan_id"]
           Using SQLModel: session.exec(select(SubmittedDocumentTable).where(...))
        3. Return { "documents": [{ "doc_type": ..., "uploaded_at": ... }, ...] }

        Empty list is valid (no docs submitted).
        """
        raise NotImplementedError("TODO: implement submitted_documents_lookup")


# ---------------------------------------------------------------------------
# Registry — single access point for all tools
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Central tool registry. Agents call tools through this, never directly.

    Usage:
        registry = get_registry()
        result = await registry.call("fraud_signal_check", {"loan_id": "LN-003", ...})
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for tool in [
            LoanPolicySearchTool(),
            FraudSignalCheckTool(),
            DocumentRequiredLookupTool(),
            LoanApplicationLookupTool(),
            SubmittedDocumentsLookupTool(),
        ]:
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered. Available: {list(self._tools)}")
        return self._tools[name]

    async def call(self, name: str, args: dict) -> dict:
        return await self.get(name).call(args)

    def list_tools(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]


# Module-level singleton — import this in agent files
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
