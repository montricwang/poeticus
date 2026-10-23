"""Private conversations are readable and removable only by their owner."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

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
    # Keep the SQL source and memory cleanup in one in-process mutation
    # interval, so a delayed background write cannot resurrect erased facts.
    from backend.memory.user_memory import memory_mutation_lock, remove_conversation_memories

    with memory_mutation_lock():
        ensure_owns_conversation(user_id, conversation_id)
        remove_conversation_memories(str(user_id), str(conversation_id))
        delete_conversation(user_id, conversation_id)



@router.get("/api/memories")
def memories(clerk_id: AuthenticatedClerkUser, response: Response) -> dict:
    """The memory list is private, even when extraction is disabled."""
    from backend.memory.user_memory import list_private_memories

    user_id = get_or_create_user(clerk_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        return {"memories": list_private_memories(str(user_id))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆服务暂时不可用") from exc


@router.delete("/api/memories")
def clear_memories(clerk_id: AuthenticatedClerkUser, response: Response) -> dict:
    from backend.memory.user_memory import delete_all_private_memories, memory_mutation_lock
    from backend.users.private_data import set_memory_opt_in

    user_id = get_or_create_user(clerk_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        with memory_mutation_lock():
            # Clear also revokes consent. Even queued extraction cannot
            # recreate deleted memories, and re-enabling requires user action.
            set_memory_opt_in(user_id, False, reset=True)
            deleted = delete_all_private_memories(str(user_id))
        return {"deleted": deleted, "memory_opt_in": False}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆删除未全部完成，请重试") from exc


class MemoryCorrection(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.patch("/api/memories/{memory_id}")
def revise_memory(
    memory_id: str, correction: MemoryCorrection, clerk_id: AuthenticatedClerkUser,
    response: Response,
) -> dict:
    from backend.memory.user_memory import (
        correct_memory, memory_mutation_lock, owns_private_memory,
    )
    from backend.users.private_data import invalidate_pending_memory

    if not correction.text.strip():
        raise HTTPException(status_code=422, detail="记忆内容不能为空")
    user_id = get_or_create_user(clerk_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        with memory_mutation_lock():
            if not owns_private_memory(str(user_id), memory_id):
                raise HTTPException(status_code=404, detail="记忆不存在")
            # Newer explicit corrections take precedence over queued LLM text.
            invalidate_pending_memory(user_id)
            result = correct_memory(str(user_id), memory_id, correction.text)
        if result is None:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆更正失败，请重试") from exc


@router.delete("/api/memories/{memory_id}", status_code=204)
def remove_memory(
    memory_id: str, clerk_id: AuthenticatedClerkUser,
) -> None:
    from backend.memory.user_memory import (
        delete_memory, memory_mutation_lock, owns_private_memory,
    )
    from backend.users.private_data import invalidate_pending_memory

    user_id = get_or_create_user(clerk_id)
    try:
        with memory_mutation_lock():
            if not owns_private_memory(str(user_id), memory_id):
                raise HTTPException(status_code=404, detail="记忆不存在")
            invalidate_pending_memory(user_id)
            owned = delete_memory(str(user_id), memory_id)
        if not owned:
            raise HTTPException(status_code=404, detail="记忆不存在")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="记忆删除失败，请重试") from exc
