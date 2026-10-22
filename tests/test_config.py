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


def _run_config_import(raw_value: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHON_DOTENV_DISABLED"] = "true"
    if raw_value is None:
        env.pop("POETICUS_AGENT_MAX_TOOL_CALLS", None)
    else:
        env["POETICUS_AGENT_MAX_TOOL_CALLS"] = raw_value
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from backend.config import AGENT_MAX_TOOL_CALLS; print(AGENT_MAX_TOOL_CALLS)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_agent_tool_budget_config_reads_environment_and_keeps_default():
    default = _run_config_import(None)
    assert default.returncode == 0
    assert default.stdout.strip() == "2"

    configured = _run_config_import("7")
    assert configured.returncode == 0
    assert configured.stdout.strip() == "7"


def test_agent_tool_budget_invalid_environment_fails_fast():
    result = _run_config_import("11")
    assert result.returncode != 0
    assert "POETICUS_AGENT_MAX_TOOL_CALLS" in result.stderr
