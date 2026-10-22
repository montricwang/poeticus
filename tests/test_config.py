"""Configuration parsing tests for runtime limits."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.config import DEFAULT_AGENT_MAX_TOOL_CALLS, _parse_agent_max_tool_calls

ROOT = Path(__file__).resolve().parents[1]


def test_agent_tool_budget_default_and_valid_bounds():
    assert DEFAULT_AGENT_MAX_TOOL_CALLS == 2
    assert _parse_agent_max_tool_calls(None) == DEFAULT_AGENT_MAX_TOOL_CALLS
    assert _parse_agent_max_tool_calls("1") == 1
    assert _parse_agent_max_tool_calls("10") == 10
    assert _parse_agent_max_tool_calls("5") == 5


@pytest.mark.parametrize("value", ["", "abc", "1.5", "0", "11", "-1"])
def test_agent_tool_budget_rejects_invalid_values(value: str):
    with pytest.raises(ValueError, match="POETICUS_AGENT_MAX_TOOL_CALLS"):
        _parse_agent_max_tool_calls(value)


def test_agent_tool_budget_is_loaded_from_environment():
    env = os.environ.copy()
    env["POETICUS_AGENT_MAX_TOOL_CALLS"] = "7"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from backend.config import AGENT_MAX_TOOL_CALLS; print(AGENT_MAX_TOOL_CALLS)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "7"


def test_invalid_environment_budget_fails_configuration_import():
    env = os.environ.copy()
    env["POETICUS_AGENT_MAX_TOOL_CALLS"] = "not-an-integer"
    result = subprocess.run(
        [sys.executable, "-c", "from backend.config import AGENT_MAX_TOOL_CALLS"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "POETICUS_AGENT_MAX_TOOL_CALLS must be an integer from 1 to 10" in result.stderr
