"""Minimal signed-in identity endpoint; public reading stays unauthenticated."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from backend import config
from backend.auth.clerk import AuthenticatedClerkUser
from backend.users.repository import get_or_create_user
from backend.users.private_data import get_memory_opt_in, set_memory_opt_in

router = APIRouter()


@router.get("/api/auth/me")
def current_user(clerk_user_id: AuthenticatedClerkUser, response: Response) -> dict[str, str]:
    """Verify the signed-in identity without mutating account data."""
    response.headers["Cache-Control"] = "no-store"
    return {"clerk_user_id": clerk_user_id}


@router.post("/api/auth/session")
def register_session(
    clerk_user_id: AuthenticatedClerkUser,
    response: Response,
    request: Request,
) -> dict[str, str | bool]:
    """Idempotently provision a stable private user ID after Clerk verification."""
    response.headers["Cache-Control"] = "no-store"
    user_id = get_or_create_user(clerk_user_id)
    request.state.authenticated_user_id = str(user_id)
    return {
        "user_id": str(user_id),
        "clerk_user_id": clerk_user_id,
        "memory_opt_in": get_memory_opt_in(user_id),
        "memory_available": config.USER_MEMORY_ENABLED,
    }

class MemoryPreference(BaseModel):
    enabled: bool


@router.put("/api/auth/memory-preference")
def update_memory_preference(
    preference: MemoryPreference, clerk_id: AuthenticatedClerkUser,
    response: Response,
) -> dict[str, bool]:
    """Never let a client set memory consent for another user."""
    response.headers["Cache-Control"] = "no-store"
    user_id = get_or_create_user(clerk_id)
    return {"memory_opt_in": set_memory_opt_in(user_id, preference.enabled)}
