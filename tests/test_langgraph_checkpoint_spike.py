"""Issue #46: SQLite-backed resume against the actual Poeticus ReAct builder."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("langgraph.checkpoint.sqlite")

REPO = Path(__file__).resolve().parents[1]


def _run(stage: str, db: Path, thread: str = "checkpoint-spike:test") -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.experiments.langgraph_checkpoint_spike",
            "--db", str(db),
            "--stage", stage,
            "--thread", thread,
        ],
        cwd=REPO,
        env={
            **os.environ,
            "LANGSMITH_TRACING": "false",
            "LANGGRAPH_STRICT_MSGPACK": "true",
        },
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    return json.loads(result.stdout)


def test_existing_react_graph_resumes_from_sqlite_after_process_restart(tmp_path):
    """Separate Python processes must share only durable checkpoints, not objects."""
    db = tmp_path / "synthetic-checkpoints.sqlite3"
    paused = _run("pause", db)
    assert paused == {
        "stage": "pause",
        "next": ["tools"],
        "model_calls": 1,
        "tool_calls": 0,
        "history_depth": 3,
    }
    assert db.exists()

    finished = _run("resume", db)
    assert finished["stage"] == "resume"
    assert finished["next"] == []
    assert finished["model_calls"] == 2  # resumed thread + independent thread B
    assert finished["tool_calls"] == 1
    assert finished["other_thread_isolated"] is True
    assert finished["history_depth"] >= 4
    assert "SQLite 恢复" in finished["reply"]


def test_resume_must_not_silently_start_without_checkpoint(tmp_path):
    db = tmp_path / "missing.sqlite3"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.experiments.langgraph_checkpoint_spike",
            "--db", str(db),
            "--stage", "resume",
            "--thread", "missing",
        ],
        cwd=REPO,
        env={**os.environ, "LANGSMITH_TRACING": "false"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode != 0
    assert "Expected paused tool node" in result.stderr
