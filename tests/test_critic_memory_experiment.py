"""Critic Notebook 研究原型的确定性回归：不调用模型、网络或生产数据库。"""

import sqlite3

import pytest

from scripts.experiments.critic_memory import CriticNotebook


def test_history_is_append_only_even_for_direct_sql(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    first = store.propose("姜夔-清空", "初步赞同某个词学判断")
    store.challenge("姜夔-清空", "这首词可能是反例")
    store.revise(
        "姜夔-清空",
        "同意该评论有局限，但应分辨不同批评标准",
        sources=["library:词源/清空"],
    )
    history = store.history("姜夔-清空")
    assert [event["id"] for event in history][0] == first
    assert [event["action"] for event in history] == ["propose", "challenge", "revise"]
    assert history[0]["content"] == "初步赞同某个词学判断"
    with sqlite3.connect(tmp_path / "critic.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE critic_events SET content = '覆盖' WHERE id = ?", (first,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM critic_events WHERE id = ?", (first,))


def test_review_requires_source_and_clear_objections(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    store.propose("诗人评价", "初步判断")
    with pytest.raises(ValueError, match="sourced"):
        store.approve("诗人评价", reviewer="human:editor")
    store.revise("诗人评价", "有依据的判断", sources=["library:人间词话/42"])
    store.challenge("诗人评价", "现有证据不能推出这个结论")
    with pytest.raises(ValueError, match="unchallenged"):
        store.approve("诗人评价", reviewer="human:editor")
    store.revise("诗人评价", "缩小结论的适用范围", sources=["library:人间词话/42"])
    with pytest.raises(ValueError, match="reviewer"):
        store.approve("诗人评价", reviewer="model")
    store.approve("诗人评价", reviewer="human:editor")
    assert store.current("诗人评价").state == "canonical"


def test_new_evidence_invalidates_previous_approval(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    store.propose("清空", "旧结论", sources=["external:source1"])
    store.approve("清空", reviewer="independent-eval:sample1")
    assert [x.claim_id for x in store.recall("旧结论")] == ["清空"]
    store.revise("清空", "新结论", sources=["external:source2"])
    assert store.current("清空").state == "candidate"
    assert store.recall("新结论") == []
    assert [x.claim_id for x in store.recall("新结论", include_candidates=True)] == ["清空"]
    store.approve("清空", reviewer="human:reviewer2")
    assert store.recall("新结论")[0].content == "新结论"
    assert store.recall("旧结论") == []


def test_retraction_keeps_history_but_disappears_from_current_recall(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    store.propose("可撤回", "试探性的观点", sources=["library:卷一/1"])
    store.approve("可撤回", reviewer="human:r")
    store.retract("可撤回", "发现出处有误")
    assert store.current("可撤回").state == "retracted"
    assert store.recall("观点", include_candidates=True) == []
    assert [event["action"] for event in store.history("可撤回")] == [
        "propose", "approve", "retract"
    ]


def test_links_and_appraisal_are_metadata_not_external_evidence(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    store.propose(
        "姜夔",
        "初步产生审美兴趣",
        related_claims=["王国维"],
        appraisal={"surprise": 3, "interest": 2},
    )
    event = store.history("姜夔")[0]
    assert event["related_claims"] == ("王国维",)
    assert event["appraisal"] == {"surprise": 3, "interest": 2}
    with pytest.raises(ValueError, match="sourced"):
        store.approve("姜夔", reviewer="human:editor")
    with pytest.raises(ValueError, match="external Library"):
        store.revise("姜夔", "错误引证", sources=["model:my-own-reply"])
    with pytest.raises(ValueError, match="appraisal"):
        store.revise("姜夔", "不合法的情绪值", appraisal={"interest": 4})


def test_consolidation_is_rebuildable_and_never_promotes(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    store.propose("A", "候选阅读札记", sources=["library:A/1"])
    store.propose("B", "已核验阅读札记", sources=["library:B/2"])
    store.approve("B", reviewer="human:editor")
    digest = store.consolidate()
    assert "已核验阅读札记" in digest.text
    assert "候选阅读札记" not in digest.text
    assert len(digest.contributing_events) == 1
    complete = store.consolidate(include_candidates=True)
    assert "[candidate] A" in complete.text
    assert store.current("A").state == "candidate"
    reopened = CriticNotebook(tmp_path / "critic.sqlite3")
    assert reopened.consolidate() == digest


def test_different_claims_are_isolated(tmp_path):
    store = CriticNotebook(tmp_path / "critic.sqlite3")
    store.propose("A", "姜夔的风格", sources=["library:A/1"])
    store.propose("B", "苏轼的风格", sources=["library:B/1"])
    store.challenge("A", "有反例")
    assert store.current("B").state == "candidate"
    assert len(store.history("B")) == 1
    with pytest.raises(ValueError, match="already exists"):
        store.propose("B", "覆盖旧记录")
    with pytest.raises(ValueError, match="must be proposed"):
        store.revise("C", "从未出现")
