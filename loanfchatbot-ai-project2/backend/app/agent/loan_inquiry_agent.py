"""
LoanInquiry Agent — single LLM with 3 tools + conversation memory.

Separation of duties:
    This agent  → defines the chatbot persona and tool descriptions
    LLM         → decides which tool to call based on the question
    Tools       → policy search, loan status, web search
    Memory      → conversation history injected into every prompt

Design:
    No LangGraph needed — single agent, simple tool loop.
    Uses the same run_with_tools pattern from Project 1.
"""
import json
import os
from openai import AsyncOpenAI
from app.models.models import ChatRequest, ChatResponse, ToolCall, ChatMessage
from app.core.session_store import get_or_create
from app.tools.policy_tool import search_policy
from app.tools.loan_status_tool import get_loan_status
from app.tools.web_search_tool import web_search

FAST_MODEL = "gpt-4o-mini"

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": (
                "Search the bank's loan policy knowledge base for policy rules, "
                "document requirements, eligibility criteria, and compliance information. "
                "Use this for questions about what documents are needed, loan requirements, "
                "or policy guidelines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "top_k": {"type": "integer", "description": "Number of results", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_loan_status",
            "description": (
                "Look up the status of a specific loan application by loan ID. "
                "Use this when the user asks about their loan, mentions a loan ID "
                "like LN-001, or wants to know application details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_id": {"type": "string", "description": "Loan ID e.g. LN-001"},
                },
                "required": ["loan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for general information not in the policy knowledge base. "
                "Use this for questions like where to obtain documents, government agency "
                "contacts, general financial guidance, or external resources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
]

_TOOL_FN_MAP = {
    "search_policy": search_policy,
    "get_loan_status": get_loan_status,
    "web_search": web_search,
}


async def run_inquiry(request: ChatRequest) -> ChatResponse:
    """
    Run a single chat turn.

    1. Load session memory
    2. Build messages (system + history + user)
    3. LLM tool-calling loop (max 3 iterations)
    4. Save to memory, return response
    """
    memory = get_or_create(request.session_id, request.memory_type)
    history = memory.format_for_prompt()

    system_prompt = (
        "You are LoanInquiry, a helpful loan assistant for bank customers and reviewers.\n"
        "You have three tools: policy search, loan status lookup, and web search.\n"
        "Always use a tool when the question involves policy rules, loan status, or finding documents.\n"
        "Be concise and cite your sources.\n\n"
        "---- Conversation history ----\n"
        f"{history}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.message},
    ]

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    tool_calls_made: list[ToolCall] = []

    # Tool-calling loop (max 3 iterations)
    for _ in range(3):
        response = await client.chat.completions.create(
            model=FAST_MODEL,
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            answer = msg.content or ""
            import inspect
            if inspect.iscoroutinefunction(memory.add):
                await memory.add("user", request.message)
                await memory.add("assistant", answer)
            else:
                memory.add("user", request.message)
                memory.add("assistant", answer)
            return ChatResponse(
                session_id=request.session_id,
                answer=answer,
                tool_calls=tool_calls_made,
                memory_snapshot=memory.get_messages()[-6:],
            )

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            fn = _TOOL_FN_MAP.get(tc.function.name)
            if fn is None:
                result = f"Unknown tool: {tc.function.name}"
            else:
                try:
                    raw = await fn(**args)
                    result = raw if isinstance(raw, str) else json.dumps(
                        [r.model_dump() if hasattr(r, "model_dump") else r for r in raw] if isinstance(raw, list) else raw
                    )
                except NotImplementedError as e:
                    result = f"Tool not yet implemented: {e}"

            tool_calls_made.append(ToolCall(tool_name=tc.function.name, args=args, result=result if isinstance(result, str) else json.dumps(result)))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result if isinstance(result, str) else json.dumps(result)})

    return ChatResponse(session_id=request.session_id, answer="", tool_calls=tool_calls_made, memory_snapshot=[])
