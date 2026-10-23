"""Provenance cleanup must not remove another reader's memories."""

from types import SimpleNamespace

import pytest

from backend import config
from backend.memory import user_memory


class FakeMemory:
    def __init__(self):
        self.records = {
            "a1": {"id": "a1", "memory": "苏轼偏好", "metadata": {"conversation_id": "conv-A"}, "user_id": "A"},
            "a2": {"id": "a2", "memory": "另一段", "metadata": {"conversation_id": "conv-B"}, "user_id": "A"},
            "b1": {"id": "b1", "memory": "别人的", "metadata": {"conversation_id": "conv-A"}, "user_id": "B"},
        }

    def get_all(self, *, filters, top_k):
        assert top_k in (100, 1000)
        user = filters["user_id"]
        return {"results": [dict(e) for e in self.records.values() if e["user_id"] == user][:top_k]}

    def delete(self, memory_id):
        del self.records[memory_id]


def test_delete_one_conversation_preserves_other_messages_and_users(monkeypatch):
    fake = FakeMemory()
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    monkeypatch.setattr(config, "USER_MEMORY_ENABLED", True)
    user_memory.remove_conversation_memories("A", "conv-A")
    assert set(fake.records) == {"a2", "b1"}


def test_clear_private_memories_never_removes_other_users(monkeypatch):
    fake = FakeMemory()
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    assert user_memory.delete_all_private_memories("A") == 2
    assert set(fake.records) == {"b1"}


def test_delete_refuses_unbounded_partial_scan(monkeypatch):
    class LimitMemory:
        def get_all(self, **kwargs):
            return {"results": [{"id": f"m{i}", "metadata": {}, "user_id": "A"} for i in range(1000)]}

    monkeypatch.setattr(user_memory, "_memory", lambda: LimitMemory())
    monkeypatch.setattr(config, "USER_MEMORY_ENABLED", True)
    with pytest.raises(RuntimeError, match="limit"):
        user_memory.remove_conversation_memories("A", "conv-A")
