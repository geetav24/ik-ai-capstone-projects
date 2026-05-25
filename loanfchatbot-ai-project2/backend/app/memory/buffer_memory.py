"""
Buffer Memory — keeps the last N messages in a list.

Simplest memory type. Fast, no storage needed.
Loses context after N messages (sliding window).
"""
from app.models.models import ChatMessage


class BufferMemory:
    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self._history: list[ChatMessage] = []

    def add(self, role: str, content: str) -> None:
        from datetime import datetime, timezone
        self._history.append(ChatMessage(role=role, content=content, timestamp=datetime.now(timezone.utc)))
        if len(self._history) > self.max_messages:
            self._history = self._history[-self.max_messages:]

    def get_messages(self) -> list[ChatMessage]:
        return list(self._history)

    def format_for_prompt(self) -> str:
        """Format history as a string to inject into the system prompt."""
        if not self._history:
            return "(no previous conversation)"
        lines = []
        for msg in self._history:
            prefix = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{prefix}: {msg.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._history = []
