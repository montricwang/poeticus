"""Minimal signed-in identity endpoint; public reading stays unauthenticated."""

from fastapi import APIRouter, Response

from backend.auth.clerk import AuthenticatedClerkUser

router = APIRouter()


@router.get("/api/auth/me")
def current_user(clerk_user_id: AuthenticatedClerkUser, response: Response) -> dict[str, str]:
    """Expose only the verified external ID, never tokens or private profile data."""
    response.headers["Cache-Control"] = "no-store"
    return {"clerk_user_id": clerk_user_id}
