"""
Session Store — in-memory store mapping session_id → memory object.

For production, replace with Redis:
  redis_client.setex(session_id, 3600, pickle.dumps(memory))
"""
from typing import Union
from app.memory.buffer_memory import BufferMemory
from app.memory.summary_memory import SummaryMemory

_sessions: dict[str, Union[BufferMemory, SummaryMemory]] = {}


def get_or_create(session_id: str, memory_type: str = "buffer") -> Union[BufferMemory, SummaryMemory]:
    if session_id not in _sessions:
        _sessions[session_id] = BufferMemory() if memory_type == "buffer" else SummaryMemory()
    return _sessions[session_id]


def delete(session_id: str) -> None:
    _sessions.pop(session_id, None)


def list_sessions() -> list[str]:
    return list(_sessions.keys())
