"""Private conversations are readable and removable only by their owner."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from backend.auth.clerk import AuthenticatedClerkUser
from backend.users.repository import get_or_create_user
from backend.users.private_data import (
    delete_conversation,
    ensure_owns_conversation,
    list_conversations,
    read_conversation,
)

router = APIRouter()


@router.get("/api/conversations")
def conversations(clerk_id: AuthenticatedClerkUser, limit: int = 30) -> dict:
    if not 1 <= limit <= 50:
        raise HTTPException(status_code=422, detail="查询数量超出范围")
    user_id = get_or_create_user(clerk_id)
    return {"conversations": list_conversations(user_id, limit)}


@router.get("/api/conversations/{conversation_id}")
def conversation(clerk_id: AuthenticatedClerkUser, conversation_id: UUID) -> dict:
    return read_conversation(get_or_create_user(clerk_id), conversation_id)


@router.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_private_conversation(
    clerk_id: AuthenticatedClerkUser, conversation_id: UUID
) -> None:
    user_id = get_or_create_user(clerk_id)
    ensure_owns_conversation(user_id, conversation_id)
    # Fail closed if private-memory cleanup fails; do not leave orphaned memories.
    from backend.memory.user_memory import remove_conversation_memories

    remove_conversation_memories(str(user_id), str(conversation_id))
    delete_conversation(user_id, conversation_id)



@router.get("/api/memories")
def memories(clerk_id: AuthenticatedClerkUser) -> dict:
    """The memory list is private, even when extraction is disabled."""
    from backend.memory.user_memory import list_private_memories

    user_id = get_or_create_user(clerk_id)
    try:
        return {"memories": list_private_memories(str(user_id))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆服务暂时不可用") from exc


@router.delete("/api/memories")
def clear_memories(clerk_id: AuthenticatedClerkUser) -> dict:
    from backend.memory.user_memory import delete_all_private_memories

    user_id = get_or_create_user(clerk_id)
    try:
        return {"deleted": delete_all_private_memories(str(user_id))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆删除未全部完成，请重试") from exc
