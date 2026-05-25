"""
Summary Memory — LLM compresses old messages into a rolling summary.

Keeps a summary paragraph of everything before the last N messages.
Trades exact wording for scalability — handles long conversations.
"""
from app.models.models import ChatMessage


class SummaryMemory:
    def __init__(self, recent_messages: int = 4):
        self.recent_messages = recent_messages
        self._summary: str = ""
        self._recent: list[ChatMessage] = []

    async def add(self, role: str, content: str) -> None:
        from datetime import datetime, timezone
        self._recent.append(ChatMessage(role=role, content=content, timestamp=datetime.now(timezone.utc)))
        if len(self._recent) > self.recent_messages * 2:
            await self._compress()

    async def _compress(self) -> None:
        """Summarize oldest messages, keep recent ones intact."""
        from app.llm_client import ask_llm_fast
        to_compress = self._recent[: -self.recent_messages]
        self._recent = self._recent[-self.recent_messages :]

        history_text = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
            for m in to_compress
        )
        existing = f"Previous summary: {self._summary}\n\n" if self._summary else ""
        new_summary = await ask_llm_fast(
            "You are a conversation summarizer. Produce a concise 2-3 sentence summary that captures the key topics and decisions from the conversation.",
            f"{existing}New messages to summarize:\n{history_text}",
        )
        self._summary = new_summary.strip()

    def format_for_prompt(self) -> str:
        parts = []
        if self._summary:
            parts.append(f"[Earlier conversation summary]: {self._summary}")
        for msg in self._recent:
            prefix = "User" if msg.role == "user" else "Assistant"
            parts.append(f"{prefix}: {msg.content}")
        return "\n".join(parts) if parts else "(no previous conversation)"

    def get_messages(self) -> list[ChatMessage]:
        return list(self._recent)

    def clear(self) -> None:
        self._summary = ""
        self._recent = []
