"""Bootstrap lab admin access and random bearer credential helpers."""

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Tokens have >=256 bits of randomness: SHA-256 stores a non-recoverable verifier.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(request: Request, credentials: BearerCredentials) -> str:
    token = request.app.state.settings.bootstrap_admin_token
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator access is not configured",
        )
    if credentials is None or not hmac.compare_digest(
        hash_token(credentials.credentials), hash_token(token.get_secret_value())
    ):
        raise unauthorized()
    return "bootstrap-admin"
