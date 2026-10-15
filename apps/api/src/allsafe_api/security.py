"""Separate human sessions and device credentials for the single-organization lab."""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from allsafe_api.config import Settings
from allsafe_api.models import User, UserSession, utc_now
from allsafe_api.schemas import UserResponse, UserRole

bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
SESSION_COOKIE = "allsafe_session"
CSRF_COOKIE = "allsafe_csrf"
PASSWORD_HASHER = PasswordHasher()
# Unknown accounts still perform an Argon2 verification to reduce account disclosure.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(
        {
            "devices:read",
            "devices:manage",
            "desktop:manage",
            "audit:read",
            "modules:read",
            "users:manage",
            "scans:submit",
            "scans:own:read",
            "scans:read",
            "scans:review",
            "wazuh:read",
            "wazuh:manage",
        }
    ),
    "analyst": frozenset(
        {
            "devices:read",
            "audit:read",
            "modules:read",
            "scans:submit",
            "scans:own:read",
            "scans:read",
            "scans:review",
            "wazuh:read",
        }
    ),
    "employee": frozenset({"scans:submit", "scans:own:read"}),
}


@dataclass(frozen=True)
class Actor:
    id: str
    permissions: frozenset[str]
    user: UserResponse | None = None
    session_id: str | None = None
    session_channel: Literal["web", "mobile"] | None = None


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Random tokens contain >=256 bits of entropy; only verifiers reach the database.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str | None, supplied: str) -> bool:
    try:
        verified = PASSWORD_HASHER.verify(password_hash or DUMMY_PASSWORD_HASH, supplied)
    except (VerificationError, InvalidHashError):
        return False
    return bool(password_hash and verified)


def user_response(user: User) -> UserResponse:
    permissions = set(ROLE_PERMISSIONS.get(user.role, frozenset()))
    if user.training_permission:
        permissions.add("training:approve")
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=cast(UserRole, user.role),
        permissions=sorted(permissions),
        active=user.active,
    )


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def normalized_origin(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def validate_origin(request: Request) -> None:
    configured: Settings = request.app.state.settings
    supplied = request.headers.get("origin")
    trusted = {
        normalized_origin(configured.frontend_url),
        normalized_origin(configured.api_url),
    }
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        supplied is not None and supplied.lower().rstrip("/") not in trusted
    ):
        raise HTTPException(status_code=403, detail="Untrusted request origin")


def current_actor(request: Request, credentials: BearerCredentials) -> Actor:
    configured: Settings = request.app.state.settings
    if credentials is not None:
        bootstrap = configured.bootstrap_admin_token
        if bootstrap is not None and hmac.compare_digest(
            hash_token(credentials.credentials), hash_token(bootstrap.get_secret_value())
        ):
            return Actor(id="bootstrap-admin", permissions=ROLE_PERMISSIONS["admin"])
        token, channel = credentials.credentials, "mobile"
    else:
        token, channel = request.cookies.get(SESSION_COOKIE), "web"
    if not token:
        raise unauthorized()
    # This read uses its own session. Route transactions never inherit an auth autobegin.
    with request.app.state.session_factory() as database:
        login_session = database.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_token(token),
                UserSession.channel == channel,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utc_now(),
            )
        )
        if login_session is None:
            raise unauthorized()
        user = database.get(User, login_session.user_id)
        if user is None or not user.active:
            raise unauthorized()
        if channel == "web" and request.method not in {"GET", "HEAD", "OPTIONS"}:
            validate_origin(request)
            supplied_csrf = request.headers.get("x-csrf-token", "")
            cookie_csrf = request.cookies.get(CSRF_COOKIE, "")
            if (
                not supplied_csrf
                or not hmac.compare_digest(hash_token(supplied_csrf), hash_token(cookie_csrf))
                or (not hmac.compare_digest(hash_token(supplied_csrf), login_session.csrf_hash))
            ):
                raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")
        dto = user_response(user)
        return Actor(
            id=user.id,
            permissions=frozenset(dto.permissions),
            user=dto,
            session_id=login_session.id,
            session_channel=cast(Literal["web", "mobile"], channel),
        )


CurrentActor = Annotated[Actor, Depends(current_actor)]


def require_permission(permission: str) -> Callable[..., Actor]:
    def check(actor: CurrentActor) -> Actor:
        if permission not in actor.permissions:
            raise HTTPException(status_code=403, detail="Permission denied")
        return actor

    return check


def require_admin(actor: CurrentActor) -> str:
    if "devices:manage" not in actor.permissions:
        raise HTTPException(status_code=403, detail="Permission denied")
    return actor.id
