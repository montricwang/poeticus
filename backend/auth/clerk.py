"""Clerk session-token verification; no login credentials are stored locally."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend import config

logger = logging.getLogger(__name__)


def require_clerk_user(request: Request) -> str:
    """Return Clerk's trusted subject after verifying the session JWT.

    A user ID in JSON, a header, or an unsigned token is never authoritative.
    The optional SDK is loaded only for this protected endpoint.
    """
    if not config.CLERK_SECRET_KEY or not config.CLERK_AUTHORIZED_PARTIES:
        raise HTTPException(status_code=503, detail="身份验证尚未配置")

    try:
        from clerk_backend_api import AuthenticateRequestOptions, authenticate_request

        auth = authenticate_request(
            request,
            AuthenticateRequestOptions(
                secret_key=config.CLERK_SECRET_KEY,
                jwt_key=config.CLERK_JWT_KEY,
                authorized_parties=list(config.CLERK_AUTHORIZED_PARTIES),
                accepts_token=["session_token"],
            ),
        )
    except ImportError as exc:
        logger.warning("Clerk SDK is unavailable")
        raise HTTPException(status_code=503, detail="身份验证暂不可用") from exc
    except Exception as exc:
        logger.warning("Clerk verification failed: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="登录凭证无效") from exc

    if not auth.is_signed_in:
        raise HTTPException(status_code=401, detail="请先登录")

    payload = auth.payload
    subject = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(subject, str) or not subject.startswith("user_"):
        raise HTTPException(status_code=401, detail="登录凭证缺少用户身份")

    # This is Clerk's external subject, not the future local users.id.
    request.state.clerk_user_id = subject
    return subject


AuthenticatedClerkUser = Annotated[str, Depends(require_clerk_user)]
