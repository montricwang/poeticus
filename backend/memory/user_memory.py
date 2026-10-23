"""Optional Mem0 OSS adapter for verified Poeticus users.

The HTTP boundary owns authentication and source-message persistence. This module
accepts trusted IDs only; it cannot authenticate a caller or recover raw messages.
"""

import atexit
import logging
import os
import threading
from contextlib import contextmanager
from uuid import UUID
from functools import lru_cache
from pathlib import Path

from backend import config

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parents[3] / "poeticus-data"
_DEFAULT_MODEL = _DATA_ROOT / "models/Qwen3-Embedding-0.6B-7c0e29cfcdf2"
_DEFAULT_STORAGE = _DATA_ROOT / "user-memory-local"
_INIT_LOCK = threading.Lock()
_MUTATION_LOCK = threading.RLock()

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


@contextmanager
def memory_mutation_lock():
    """Serialize in-process writes, corrections and erasure of private memory."""
    with _MUTATION_LOCK:
        yield


def _owned_memory(user_id: str, memory_id: str) -> dict | None:
    record = _memory().get(memory_id)
    if not isinstance(record, dict) or record.get("user_id") != user_id:
        return None
    return record


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


def owns_private_memory(user_id: str, memory_id: str) -> bool:
    """Check ownership before changing other persisted state."""
    with _MUTATION_LOCK:
        return _owned_memory(user_id, memory_id) is not None


def delete_memory(user_id: str, memory_id: str) -> bool:
    """Only the verified owner may delete a memory by its untrusted UUID."""
    with _MUTATION_LOCK:
        if _owned_memory(user_id, memory_id) is None:
            return False
        _memory().delete(memory_id)
        return True


def correct_memory(user_id: str, memory_id: str, text: str) -> dict | None:
    """A user correction is an explicit assertion, no longer a chat-derived guess."""
    content = text.strip()
    if not content or len(content) > 300:
        raise ValueError("Invalid corrected memory length")
    with _MUTATION_LOCK:
        previous = _owned_memory(user_id, memory_id)
        if previous is None:
            return None

        # Keep the original locator as audit metadata, but sever automatic
        # deletion linkage: the user has now explicitly asserted this memory.
        metadata = previous.get("metadata") or {}
        original = metadata.get("conversation_id") or metadata.get("original_conversation_id")
        _memory().update(
            memory_id,
            text=content,
            metadata={
                "source": "user_correction",
                "corrected_by_user": True,
                "original_conversation_id": original,
                "conversation_id": None,
                "source_message_id": None,
            },
        )
        return {"id": memory_id, "memory": content, "source": "user_correction"}


def safe_recall(user_id: str | None, question: str) -> list[str]:
    if not (config.USER_MEMORY_ENABLED and user_id):
        return []
    try:
        from backend.users.private_data import get_memory_opt_in

        # An active SSE request can outlive a consent toggle. Recheck at
        # actual retrieval time, not only when the HTTP request begins.
        with _MUTATION_LOCK:
            if not get_memory_opt_in(UUID(user_id)):
                return []
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
        from backend.users.private_data import source_allows_memory

        # Work may be queued after the reply. Recheck both source existence
        # and the persisted consent/cutoff immediately before writing.
        with _MUTATION_LOCK:
            if not source_allows_memory(
                UUID(user_id), UUID(conversation_id), UUID(source_message_id), user_text
            ):
                return
            remember(
                user_id,
                user_text,
                conversation_id=conversation_id,
                source_message_id=source_message_id,
            )
    except Exception as exc:
        logger.warning("User memory save failed: %s", type(exc).__name__)


def remove_conversation_memories(user_id: str, conversation_id: str) -> None:
    """Purge this conversation's derived memories, preserving user corrections.

    The deletion caller holds memory_mutation_lock through SQL source removal.
    """
    storage = Path(
        os.getenv("POETICUS_USER_MEMORY_STORAGE_DIR", str(_DEFAULT_STORAGE))
    ).expanduser() / "qdrant"
    if not config.USER_MEMORY_ENABLED and not storage.exists():
        return

    with _MUTATION_LOCK:
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


def _has_memory_storage() -> bool:
    storage = Path(
        os.getenv("POETICUS_USER_MEMORY_STORAGE_DIR", str(_DEFAULT_STORAGE))
    ).expanduser() / "qdrant"
    return storage.is_dir()


def list_private_memories(user_id: str) -> list[dict]:
    """List only this user's memory content and coarse provenance."""
    with _MUTATION_LOCK:
        if not _has_memory_storage():
            return []
        response = _memory().get_all(filters={"user_id": user_id}, top_k=100)
    entries = response.get("results", [])
    return [
        {
            "id": item["id"],
            "memory": item["memory"],
            "source": (item.get("metadata") or {}).get("source", "unknown"),
            "conversation_id": (item.get("metadata") or {}).get("conversation_id"),
            "source_message_id": (item.get("metadata") or {}).get("source_message_id"),
        }
        for item in entries
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("memory"), str)
    ]


def delete_all_private_memories(user_id: str) -> int:
    """Delete only the user's Mem0 records, in bounded batches."""
    with _MUTATION_LOCK:
        if not _has_memory_storage():
            return 0
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
