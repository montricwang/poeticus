"""Offline SQLite Checkpointer experiment against Poeticus' actual ReAct graph.

The CLI runs with a fake model and evidence provider. No real user data or LLM
requests are required. It deliberately does not change the public chat graph.

Example:
    python -m scripts.experiments.langgraph_checkpoint_spike --db /tmp/poeticus-agent-checkpoints.sqlite --stage pause
    python -m scripts.experiments.langgraph_checkpoint_spike --db /tmp/poeticus-agent-checkpoints.sqlite --stage resume
"""

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Set before importing checkpoint serializers to restrict deserialization types.
os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ.setdefault("LLM_API_KEY", "checkpoint-spike-no-network")

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402

from backend.ai import graph as agent  # noqa: E402
from backend.evidence.schema import EvidenceItem  # noqa: E402


DEFAULT_THREAD = "checkpoint-spike:synthetic-A"
INPUT_STATE = {
    "poem": "自作测试文本：柳外春风。",
    "question": "这里的刘郎是谁？",
    "selection": "刘郎",
    "max_tool_calls": 2,
}


class FakeModel:
    """Decide from persisted tool messages, not in-memory call counters."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        messages = kwargs["messages"]
        current = str(messages[-1].get("content", "")) if messages else ""
        if "直接回答测试题" in current:
            content = "第二个 Thread 的独立回答。"
            tool_calls = None
        elif any(msg.get("role") == "tool" for msg in messages):
            content = "刘郎：用于验证工具节点之后可以从 SQLite 恢复。"
            tool_calls = None
        else:
            content = None
            tool_calls = [
                SimpleNamespace(
                    id="synthetic-call-1",
                    type="function",
                    function=SimpleNamespace(
                        name="lookup_allusion",
                        arguments=json.dumps({"term": "刘郎"}, ensure_ascii=False),
                    ),
                )
            ]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content=content, tool_calls=tool_calls,
            ))]
        )


class FakeEvidence:
    def __init__(self):
        self.calls = 0

    async def search(self, *, query, provider_name, evidence_type=None):
        self.calls += 1
        assert query == "刘郎"
        assert evidence_type == "allusion"
        return [EvidenceItem(
            anchor=query,
            type="allusion",
            text="刘郎：合成的典故说明，非文学事实。",
            provider="cnkgraph",
            status="candidate",
        )]


def run(db: Path, stage: str, thread_id: str = DEFAULT_THREAD) -> dict:
    """Run an interrupted graph in SQLite, or resume it in another process."""
    db.parent.mkdir(parents=True, exist_ok=True)
    fake_model, fake_evidence = FakeModel(), FakeEvidence()
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_model.create))
    )
    config = {"configurable": {"thread_id": thread_id}}

    with patch.object(agent, "client", fake_client), patch.object(
        agent.evidence_service, "search", fake_evidence.search
    ), SqliteSaver.from_conn_string(str(db)) as saver:
        graph = agent.builder.compile(
            checkpointer=saver, interrupt_before=["tools"]
        )
        if stage == "pause":
            if graph.get_state(config).values:
                raise RuntimeError("Thread already contains a checkpoint; choose a fresh --thread")
            paused = graph.invoke(INPUT_STATE, config=config)
            snapshot = graph.get_state(config)
            assert snapshot.next == ("tools",), snapshot.next
            assert len(paused["tool_calls"]) == 1
            assert fake_model.calls == 1 and fake_evidence.calls == 0
            return {
                "stage": stage, "next": list(snapshot.next),
                "model_calls": fake_model.calls, "tool_calls": fake_evidence.calls,
                "history_depth": len(list(graph.get_state_history(config))),
            }

        if stage == "resume":
            snapshot = graph.get_state(config)
            assert snapshot.next == ("tools",), (
                f"Expected paused tool node; got next={snapshot.next!r}"
            )
            # Supplying None resumes the existing graph state. Supplying
            # INPUT_STATE again would *start a new write*, not an exact resume.
            resumed = graph.invoke(None, config=config)
            done = graph.get_state(config)
            assert done.next == (), done.next
            assert resumed["tool_count"] == 1
            assert "SQLite 恢复" in resumed["reply"]
            assert fake_model.calls == 1, "The completed pre-pause agent was re-run"
            assert fake_evidence.calls == 1, "The tools node did not execute exactly once"
            assert sum(m["role"] == "tool" for m in resumed["messages"]) == 1
            assert len(list(graph.get_state_history(config))) >= 4
            # The same database must isolate a second thread's initial state.
            other_config = {"configurable": {"thread_id": thread_id + ":other"}}
            other_graph = agent.builder.compile(checkpointer=saver)
            other = other_graph.invoke(
                {
                    "poem": "合成的第二首诗",
                    "question": "直接回答测试题",
                    "max_tool_calls": 2,
                },
                config=other_config,
            )
            assert other["reply"] == "第二个 Thread 的独立回答。"
            assert "刘郎" not in json.dumps(other, ensure_ascii=False)
            assert other_graph.get_state(other_config).values["poem"] == "合成的第二首诗"
            return {
                "stage": stage, "next": list(done.next),
                "model_calls": fake_model.calls, "tool_calls": fake_evidence.calls,
                "reply": resumed["reply"],
                "other_thread_isolated": True,
                "history_depth": len(list(graph.get_state_history(config))),
            }
        raise ValueError(f"Unknown stage {stage}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--stage", choices=("pause", "resume"), required=True)
    parser.add_argument("--thread", default=DEFAULT_THREAD)
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.stage, args.thread), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
