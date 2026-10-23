"""Optional Mem0 OSS adapter for verified Poeticus users.

The HTTP boundary owns authentication and source-message persistence. This module
accepts trusted IDs only; it cannot authenticate a caller or recover raw messages.
"""

import atexit
import logging
import os
import threading
from functools import lru_cache
from pathlib import Path

from backend import config

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parents[3] / "poeticus-data"
_DEFAULT_MODEL = _DATA_ROOT / "models/Qwen3-Embedding-0.6B-7c0e29cfcdf2"
_DEFAULT_STORAGE = _DATA_ROOT / "user-memory-local"
_INIT_LOCK = threading.Lock()

# Qwen3-Embedding yields 1024-dimensional document and query vectors.
_QWEN_DIMS = 1024


@lru_cache(maxsize=1)
def _create_memory():
    # Set this before importing the SDK, which initializes telemetry at import.
    os.environ.setdefault("MEM0_TELEMETRY", "false")
    from mem0 import Memory
    from mem0.utils.factory import EmbedderFactory
    from backend.memory.mem0_adapter import Qwen3RoleEmbedding

    model_path = Path(
        os.getenv("POETICUS_USER_MEMORY_MODEL_PATH", str(_DEFAULT_MODEL))
    ).expanduser()
    storage_path = Path(
        os.getenv("POETICUS_USER_MEMORY_STORAGE_DIR", str(_DEFAULT_STORAGE))
    ).expanduser()

    if not model_path.is_dir():
        raise RuntimeError("Local user-memory embedding model is unavailable")
    if not os.getenv("LLM_API_KEY"):
        raise RuntimeError("No LLM API key configured for user memory")

    storage_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Private chat-derived memory should not be traversable by local users.
    if os.name == "posix":
        storage_path.chmod(0o700)
    (storage_path / "qdrant").mkdir(exist_ok=True)

    # Mem0 2.2.1 selects the adapter using a factory mapping. Registering one
    # implementation is local to this Python process, not a system-wide change.
    EmbedderFactory.provider_to_class["huggingface"] = (
        "backend.memory.mem0_adapter.Qwen3RoleEmbedding"
    )

    memory = Memory.from_config(
        {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "poeticus_private_user_memory",
                    "embedding_model_dims": _QWEN_DIMS,
                    "path": str(storage_path / "qdrant"),
                    "on_disk": True,
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": str(model_path),
                    "embedding_dims": _QWEN_DIMS,
                    "model_kwargs": {
                        "device": "cpu",
                        "local_files_only": True,
                    },
                },
            },
            "llm": {
                "provider": "deepseek",
                "config": {
                    "model": os.getenv(
                        "POETICUS_USER_MEMORY_LLM_MODEL", "deepseek-chat"
                    ),
                    "api_key": os.environ["LLM_API_KEY"],
                    "deepseek_base_url": config.LLM_BASE_URL,
                    "temperature": 0,
                    "max_tokens": 300,
                },
            },
            "history_db_path": str(storage_path / "history.sqlite3"),
            "custom_instructions": (
                "只提取用户自己明确表达、有后续价值的个人阅读偏好、"
                "当前研究兴趣及明确更正；保留时间、条件和不确定性。"
                "一次性要求或引述他人观点不应写成用户永久偏好。"
                "候选记忆的 text 字段必须使用简体中文，"
                "保留原文中的人名、作品名和限定，不要自动译成英文。"
            ),
            "version": "v1.1",
        }
    )
    # Local Qdrant holds a file lock; close it before Python module teardown.
    atexit.register(memory.vector_store.client.close)
    return memory


def _memory():
    # Embedded Qdrant permits one client per local directory in a process.
    with _INIT_LOCK:
        return _create_memory()


def recall(user_id: str, question: str) -> list[str]:
    """Retrieve only this authenticated user's relevant memories."""
    response = _memory().search(
        question, filters={"user_id": user_id}, top_k=4, threshold=0.1
    )
    results = response.get("results", [])
    return [
        entry["memory"][:250]
        for entry in results
        if isinstance(entry, dict) and isinstance(entry.get("memory"), str)
    ][:4]


def remember(
    user_id: str,
    user_text: str,
    *,
    conversation_id: str,
    source_message_id: str,
) -> None:
    """Write a candidate only after a server-owned message ID is persisted."""
    if not (user_id and conversation_id and source_message_id):
        raise ValueError("A verified user and persisted message source are required")
    _memory().add(
        [{"role": "user", "content": user_text}],
        user_id=user_id,
        metadata={
            "source": "conversation",
            "conversation_id": conversation_id,
            "source_message_id": source_message_id,
        },
        infer=True,
    )


def delete_memory(user_id: str, memory_id: str) -> bool:
    """Delete only a memory already shown to belong to the given user."""
    response = _memory().get_all(filters={"user_id": user_id}, top_k=1000)
    owned = {item["id"] for item in response.get("results", [])}
    if memory_id not in owned:
        return False
    _memory().delete(memory_id)
    return True


def safe_recall(user_id: str | None, question: str) -> list[str]:
    if not (config.USER_MEMORY_ENABLED and user_id):
        return []
    try:
        return recall(user_id, question)
    except Exception as exc:
        logger.warning("User memory lookup failed: %s", type(exc).__name__)
        return []


def safe_remember(
    user_id: str | None,
    user_text: str,
    *,
    conversation_id: str | None,
    source_message_id: str | None,
) -> None:
    if not (
        config.USER_MEMORY_ENABLED
        and user_id
        and conversation_id
        and source_message_id
    ):
        return
    try:
        remember(
            user_id,
            user_text,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
        )
    except Exception as exc:
        logger.warning("User memory save failed: %s", type(exc).__name__)

def remove_conversation_memories(user_id: str, conversation_id: str) -> None:
    """Purge conversation-derived memories before deleting its message source.

    If the memory store was used previously, disabling new extraction must not
    silently skip cleanup. A retrieval limit refuses ambiguous partial deletion.
    """
    storage = Path(
        os.getenv("POETICUS_USER_MEMORY_STORAGE_DIR", str(_DEFAULT_STORAGE))
    ).expanduser() / "qdrant"
    if not config.USER_MEMORY_ENABLED and not storage.exists():
        return  # No local memory collection has ever been configured.

    memory = _memory()
    entries = memory.get_all(filters={"user_id": user_id}, top_k=1000).get("results", [])
    if len(entries) >= 1000:
        raise RuntimeError("Memory scan limit reached; refusing partial deletion")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") or {}
        if metadata.get("conversation_id") == conversation_id:
            memory.delete(entry["id"])


def list_private_memories(user_id: str) -> list[dict]:
    """Return bounded records for this user to inspect or delete."""
    response = _memory().get_all(filters={"user_id": user_id}, top_k=100)
    entries = response.get("results", [])
    return [
        {"id": item["id"], "memory": item["memory"]}
        for item in entries
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("memory"), str)
    ]


def delete_all_private_memories(user_id: str) -> int:
    """Delete the entire user's Mem0 history in bounded batches."""
    memory = _memory()
    deleted = 0
    for _ in range(100):
        entries = memory.get_all(filters={"user_id": user_id}, top_k=1000).get("results", [])
        if not entries:
            return deleted
        ids = [
            entry["id"] for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        ]
        if not ids:
            raise RuntimeError("Memory records have no valid identifiers")
        for memory_id in ids:
            memory.delete(memory_id)
        deleted += len(ids)
    raise RuntimeError("Memory cleanup exceeded its safety limit")
