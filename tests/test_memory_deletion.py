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

    def get(self, memory_id):
        return dict(self.records[memory_id]) if memory_id in self.records else None

    def update(self, memory_id, *, text, metadata):
        self.records[memory_id]["memory"] = text
        self.records[memory_id]["metadata"].update(metadata)

    def delete(self, memory_id):
        del self.records[memory_id]

    def search(self, question, *, filters, top_k, threshold):
        return {"results": self.get_all(filters=filters, top_k=100)["results"][:top_k]}


def test_delete_one_conversation_preserves_other_messages_and_users(monkeypatch):
    fake = FakeMemory()
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    monkeypatch.setattr(config, "USER_MEMORY_ENABLED", True)
    user_memory.remove_conversation_memories("A", "conv-A")
    assert set(fake.records) == {"a2", "b1"}


def test_clear_private_memories_never_removes_other_users(monkeypatch):
    fake = FakeMemory()
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    monkeypatch.setattr(user_memory, "_has_memory_storage", lambda: True)
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

def test_manual_correction_keeps_ownership_and_breaks_old_auto_link(monkeypatch):
    fake = FakeMemory()
    fake.records["a1"]["metadata"]["source_message_id"] = "msg-A"
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    assert user_memory.correct_memory("B", "a1", "窃改") is None
    assert fake.records["a1"]["memory"] == "苏轼偏好"
    corrected = user_memory.correct_memory("A", "a1", "  更喜欢李清照  ")
    assert corrected["memory"] == "更喜欢李清照"
    meta = fake.records["a1"]["metadata"]
    assert meta["source"] == "user_correction"
    assert meta["original_conversation_id"] == "conv-A"
    assert meta["original_source_message_id"] == "msg-A"
    assert corrected["original_source_message_id"] == "msg-A"
    assert meta["conversation_id"] is None
    monkeypatch.setattr(user_memory, "_has_memory_storage", lambda: True)
    listed = user_memory.list_private_memories("A")
    assert listed[0]["original_source_message_id"] == "msg-A"
    # A second manual correction must not destroy original source provenance.
    user_memory.correct_memory("A", "a1", "现在喜欢周邦彦")
    assert fake.records["a1"]["metadata"]["original_source_message_id"] == "msg-A"
    monkeypatch.setattr(config, "USER_MEMORY_ENABLED", True)
    user_memory.remove_conversation_memories("A", "conv-A")
    assert set(fake.records) == {"a1", "a2", "b1"}




def test_recall_marks_manual_correction_as_authoritative(monkeypatch):
    fake = FakeMemory()
    fake.records["a2"]["memory"] = "自动提取：最喜欢姜夔"
    fake.records["a1"]["memory"] = "本人更正：最喜欢李清照"
    fake.records["a1"]["metadata"]["corrected_by_user"] = True
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)

    notes = user_memory.recall("A", "我最喜欢哪位词人？")
    assert notes[0] == "【本人已更正的现行记忆】本人更正：最喜欢李清照"
    assert notes[1] == "【从旧对话提取、可能过时】自动提取：最喜欢姜夔"
    assert "别人的" not in str(notes)


def test_deleting_one_record_does_not_claim_to_forget_other_records(monkeypatch):
    fake = FakeMemory()
    fake.records["a1"]["memory"] = "我最喜欢姜夔"
    fake.records["a2"]["memory"] = "我喜欢姜夔胜过其他词人"
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)

    user_memory.correct_memory("A", "a1", "我最喜欢李清照")
    assert user_memory.delete_memory("A", "a1")
    assert user_memory.recall("A", "我最喜欢谁？") == [
        "【从旧对话提取、可能过时】我喜欢姜夔胜过其他词人"
    ]

def test_single_memory_delete_checks_current_owner(monkeypatch):
    fake = FakeMemory()
    monkeypatch.setattr(user_memory, "_memory", lambda: fake)
    assert user_memory.delete_memory("B", "a1") is False
    assert user_memory.delete_memory("A", "a1") is True
    assert user_memory.delete_memory("A", "a1") is False
    assert set(fake.records) == {"a2", "b1"}


def test_queued_write_rechecks_consent_inside_mutation_lock(monkeypatch):
    from threading import Event, Thread
    from uuid import uuid4

    from backend.users import private_data

    monkeypatch.setattr(config, "USER_MEMORY_ENABLED", True)
    state = {"allowed": True}
    started = Event()
    writes = []
    monkeypatch.setattr(
        private_data, "source_allows_memory",
        lambda *args: state["allowed"],
    )
    monkeypatch.setattr(
        user_memory, "remember",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )
    keys = [str(uuid4()) for _ in range(3)]

    def pending():
        started.set()
        user_memory.safe_remember(
            keys[0], "我喜欢苏轼",
            conversation_id=keys[1], source_message_id=keys[2],
        )

    # The clear action holds the mutation lock. The delayed task must observe
    # the *new* consent state after it is released, not a stale decision.
    with user_memory.memory_mutation_lock():
        thread = Thread(target=pending)
        thread.start()
        assert started.wait(2)
        state["allowed"] = False
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert writes == []

def test_recall_rechecks_current_database_consent(monkeypatch):
    from uuid import uuid4

    from backend.users import private_data

    monkeypatch.setattr(config, "USER_MEMORY_ENABLED", True)
    user_id = str(uuid4())
    monkeypatch.setattr(private_data, "get_memory_opt_in", lambda *_: False)
    monkeypatch.setattr(
        user_memory, "recall",
        lambda *args: pytest.fail("Memory read after consent was revoked"),
    )
    assert user_memory.safe_recall(user_id, "喜欢谁") == []
    monkeypatch.setattr(private_data, "get_memory_opt_in", lambda *_: True)
    monkeypatch.setattr(user_memory, "recall", lambda *args: ["喜欢李清照"])
    assert user_memory.safe_recall(user_id, "喜欢谁") == ["喜欢李清照"]
