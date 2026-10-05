"""Single source of truth for cross-module runtime and API limits."""

import os

from dotenv import load_dotenv

load_dotenv()


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


# Public chat contract. Backend validation is authoritative; the frontend reads
# the browser-relevant subset from /api/capabilities instead of duplicating it.
CHAT_MAX_POEM_CHARS = 12000
CHAT_MAX_QUESTION_CHARS = 1200
CHAT_MAX_SELECTION_CHARS = 3000
CHAT_MAX_HISTORY_TURNS = 6
CHAT_MAX_HISTORY_MESSAGES = CHAT_MAX_HISTORY_TURNS * 2
CHAT_MAX_HISTORY_MESSAGE_CHARS = 4000
CHAT_MAX_HISTORY_TOTAL_CHARS = 12000

# LLM runtime configuration. Railway may override operational values without
# requiring a code change; all model call sites import these resolved values.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("POETICUS_LLM_MODEL", "deepseek-flash")
LLM_MAX_OUTPUT_TOKENS = _bounded_int(
    "POETICUS_LLM_MAX_OUTPUT_TOKENS",
    1200,
    128,
    2048,
)
LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_RETRIES = 0

# One user request may perform at most this many actual tool calls.
AGENT_MAX_TOOL_CALLS = 2
