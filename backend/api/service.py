"""Public health and service metadata routes."""
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/health", tags=["service"])
def health():
    """Liveness only: no database, model API or external tools."""
    return {"status": "ok"}


@router.get("/api/info", tags=["service"])
def public_info(request: Request):
    """Public product metadata; never expose runtime configuration."""
    return {
        "name": "Poeticus",
        "version": request.app.version,
        "repository": "https://github.com/montricwang/poeticus",
    }
