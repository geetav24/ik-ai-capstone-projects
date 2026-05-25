"""Tests for buffer and summary memory."""
import pytest
from app.memory.buffer_memory import BufferMemory


def test_buffer_memory_adds_messages():
    mem = BufferMemory(max_messages=4)
    mem.add("user", "Hello")
    mem.add("assistant", "Hi there!")
    assert len(mem.get_messages()) == 2


def test_buffer_memory_sliding_window():
    mem = BufferMemory(max_messages=2)
    mem.add("user", "msg1")
    mem.add("user", "msg2")
    mem.add("user", "msg3")
    msgs = mem.get_messages()
    assert len(msgs) == 2
    assert msgs[0].content == "msg2"


def test_buffer_memory_format_for_prompt():
    mem = BufferMemory()
    mem.add("user", "What is a pay stub?")
    mem.add("assistant", "A pay stub is...")
    prompt = mem.format_for_prompt()
    assert "User:" in prompt
    assert "Assistant:" in prompt


def test_buffer_memory_clear():
    mem = BufferMemory()
    mem.add("user", "test")
    mem.clear()
    assert mem.get_messages() == []
