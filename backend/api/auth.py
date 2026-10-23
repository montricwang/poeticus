"""Minimal signed-in identity endpoint; public reading stays unauthenticated."""

from fastapi import APIRouter, Request, Response

from backend.auth.clerk import AuthenticatedClerkUser
from backend.users.repository import get_or_create_user

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
) -> dict[str, str]:
    """Idempotently provision a stable private user ID after Clerk verification."""
    response.headers["Cache-Control"] = "no-store"
    user_id = get_or_create_user(clerk_user_id)
    request.state.authenticated_user_id = str(user_id)
    return {"user_id": str(user_id), "clerk_user_id": clerk_user_id}
