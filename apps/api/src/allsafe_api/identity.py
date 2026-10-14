"""Local lab identities, opaque browser sessions and optional OIDC login."""

from datetime import timedelta
from typing import Annotated, cast

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client.apps import StarletteOAuth2App
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from httpx import HTTPError
from joserfc.errors import JoseError
from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from allsafe_api.database import get_session
from allsafe_api.models import AuditEvent, IdentityState, LoginAttempt, User, UserSession, utc_now
from allsafe_api.schemas import (
    CreateUserRequest,
    LinkOIDCRequest,
    LoginRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserResponse,
)
from allsafe_api.security import (
    CSRF_COOKIE,
    PASSWORD_HASHER,
    SESSION_COOKIE,
    Actor,
    CurrentActor,
    generate_token,
    hash_password,
    hash_token,
    require_permission,
    unauthorized,
    user_response,
    validate_origin,
    verify_password,
)

router = APIRouter(prefix="/api/v1", tags=["Identity"])
DatabaseSession = Annotated[Session, Depends(get_session)]
UserAdministrator = Annotated[Actor, Depends(require_permission("users:manage"))]


def initialize_identity(application: FastAPI) -> None:
    """Seed only an empty local laboratory; never overwrite an existing identity."""
    engine = application.state.engine
    if not inspect(engine).has_table("identity_state"):
        return
    configured = application.state.settings
    with application.state.session_factory() as database, database.begin():
        if database.get(IdentityState, 1) is None:
            database.add(IdentityState(id=1, revision=0))
        if configured.authentication_mode == "local" and configured.initial_admin_password:
            exists = database.scalar(select(User.id).limit(1))
            if exists is None:
                database.add(
                    User(
                        email=configured.initial_admin_email,
                        display_name="ALLSAFE Administrator",
                        role="admin",
                        active=True,
                        training_permission=True,
                        password_hash=hash_password(
                            configured.initial_admin_password.get_secret_value()
                        ),
                    )
                )


def serialize_identity_changes(database: Session) -> None:
    # UPDATE locks the common row before reads: SQLite and PostgreSQL serialize
    # simultaneous last-admin changes and password/login decisions across workers.
    database.execute(
        update(IdentityState)
        .where(IdentityState.id == 1)
        .values(revision=IdentityState.revision + 1)
    )


def revoke_user_sessions(database: Session, user_id: str) -> None:
    database.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


def add_session(database: Session, request: Request, user: User) -> tuple[str, str]:
    token, csrf = generate_token(), generate_token()
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        database.execute(
            update(UserSession)
            .where(UserSession.token_hash == hash_token(previous), UserSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
    database.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_hash=hash_token(csrf),
            expires_at=utc_now()
            + timedelta(seconds=request.app.state.settings.user_session_ttl_seconds),
        )
    )
    database.add(AuditEvent(event_type="auth.login", actor=user.id, target_id=user.id, details={}))
    return token, csrf


def session_cookies(response: Response, request: Request, token: str, csrf: str) -> None:
    settings = request.app.state.settings
    for name, value, http_only in ((SESSION_COOKIE, token, True), (CSRF_COOKIE, csrf, False)):
        response.set_cookie(
            name,
            value,
            httponly=http_only,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
            max_age=settings.user_session_ttl_seconds,
        )
    response.headers["Cache-Control"] = "no-store"


@router.get("/auth/config")
def auth_configuration(request: Request) -> dict[str, str | bool]:
    mode = request.app.state.settings.authentication_mode
    return {"mode": mode, "oidc_enabled": mode == "oidc"}


@router.post("/auth/login", response_model=UserResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, session: DatabaseSession
) -> UserResponse:
    validate_origin(request)
    if request.app.state.settings.authentication_mode != "local":
        raise HTTPException(status_code=409, detail="Local password login is disabled")
    subject_hash = hash_token(payload.email)
    source_hash = hash_token(request.client.host if request.client else "unknown")
    now = utc_now()
    user = None
    tokens = None
    with session.begin():
        serialize_identity_changes(session)
        cutoff = now - timedelta(minutes=5)
        subject_failures = (
            session.scalar(
                select(func.count())
                .select_from(LoginAttempt)
                .where(
                    LoginAttempt.subject_hash == subject_hash, LoginAttempt.attempted_at > cutoff
                )
            )
            or 0
        )
        source_failures = (
            session.scalar(
                select(func.count())
                .select_from(LoginAttempt)
                .where(LoginAttempt.source_hash == source_hash, LoginAttempt.attempted_at > cutoff)
            )
            or 0
        )
        if subject_failures >= 5 or source_failures >= 20:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts; try later",
                headers={"Retry-After": "300"},
            )
        # Expired failure records carry no operational value in this lab.
        session.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at <= cutoff))
        user = session.scalar(select(User).where(User.email == payload.email))
        valid = verify_password(
            user.password_hash if user else None, payload.password.get_secret_value()
        )
        if not valid or user is None or not user.active:
            session.add(
                LoginAttempt(subject_hash=subject_hash, source_hash=source_hash, attempted_at=now)
            )
            user = None
        else:
            if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
                user.password_hash = hash_password(payload.password.get_secret_value())
            session.execute(delete(LoginAttempt).where(LoginAttempt.subject_hash == subject_hash))
            tokens = add_session(session, request, user)
    # Failed attempts must commit before the generic error is raised.
    if user is None or tokens is None:
        raise unauthorized()
    session_cookies(response, request, *tokens)
    return user_response(user)


@router.get("/auth/me", response_model=UserResponse)
def me(actor: CurrentActor, response: Response) -> UserResponse:
    if actor.user is None:
        raise unauthorized()
    response.headers["Cache-Control"] = "no-store"
    return actor.user


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request, response: Response, actor: CurrentActor, session: DatabaseSession
) -> None:
    if actor.session_id is None:
        raise unauthorized()
    with session.begin():
        session.execute(
            update(UserSession)
            .where(UserSession.id == actor.session_id)
            .values(revoked_at=utc_now())
        )
        session.add(
            AuditEvent(event_type="auth.logout", actor=actor.id, target_id=actor.id, details={})
        )
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            secure=request.app.state.settings.cookie_secure,
            httponly=name == SESSION_COOKIE,
            samesite="lax",
        )
    response.headers["Cache-Control"] = "no-store"


@router.get("/users", response_model=list[UserResponse])
def list_users(
    session: DatabaseSession, _: UserAdministrator, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[UserResponse]:
    return [
        user_response(user)
        for user in session.scalars(select(User).order_by(User.created_at, User.id).limit(limit))
    ]


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    payload: CreateUserRequest, request: Request, session: DatabaseSession, actor: UserAdministrator
) -> UserResponse:
    if request.app.state.settings.authentication_mode == "local" and payload.password is None:
        raise HTTPException(status_code=422, detail="Local users require a password")
    if request.app.state.settings.authentication_mode == "oidc" and payload.password is not None:
        raise HTTPException(status_code=422, detail="OIDC users must not have a local password")
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        role=payload.role,
        active=True,
        training_permission=payload.training_permission,
        password_hash=(
            hash_password(payload.password.get_secret_value()) if payload.password else None
        ),
    )
    try:
        with session.begin():
            serialize_identity_changes(session)
            session.add(user)
            session.flush()
            session.add(
                AuditEvent(
                    event_type="user.created",
                    actor=actor.id,
                    target_id=user.id,
                    details={"role": user.role},
                )
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists") from None
    return user_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str, payload: UpdateUserRequest, session: DatabaseSession, actor: UserAdministrator
) -> UserResponse:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one field is required")
    with session.begin():
        serialize_identity_changes(session)
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if (
            user.role == "admin"
            and user.active
            and (changes.get("active") is False or changes.get("role", user.role) != "admin")
        ):
            others = (
                session.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == "admin", User.active.is_(True), User.id != user.id)
                )
                or 0
            )
            if others == 0:
                raise HTTPException(
                    status_code=409, detail="The last active admin must be retained"
                )
        sensitive_changed = any(
            key in {"role", "active", "training_permission"} and getattr(user, key) != value
            for key, value in changes.items()
        )
        for key, value in changes.items():
            setattr(user, key, value)
        if sensitive_changed:
            revoke_user_sessions(session, user.id)
        session.add(
            AuditEvent(
                event_type="user.updated",
                actor=actor.id,
                target_id=user.id,
                details={"changed_fields": sorted(changes)},
            )
        )
    return user_response(user)


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    session: DatabaseSession,
    actor: UserAdministrator,
) -> None:
    if request.app.state.settings.authentication_mode != "local":
        raise HTTPException(
            status_code=409, detail="Passwords are managed by the identity provider"
        )
    with session.begin():
        serialize_identity_changes(session)
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = hash_password(payload.password.get_secret_value())
        revoke_user_sessions(session, user.id)
        session.execute(
            delete(LoginAttempt).where(LoginAttempt.subject_hash == hash_token(user.email))
        )
        session.add(
            AuditEvent(
                event_type="user.password_reset", actor=actor.id, target_id=user.id, details={}
            )
        )


@router.post("/users/{user_id}/oidc", response_model=UserResponse)
def link_oidc(
    user_id: str, payload: LinkOIDCRequest, session: DatabaseSession, actor: UserAdministrator
) -> UserResponse:
    # Explicit administrator mapping; an email claim alone can never become admin.
    try:
        with session.begin():
            serialize_identity_changes(session)
            user = session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            user.oidc_issuer, user.oidc_subject = payload.issuer, payload.subject
            revoke_user_sessions(session, user.id)
            session.add(
                AuditEvent(
                    event_type="user.oidc_linked", actor=actor.id, target_id=user.id, details={}
                )
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="OIDC identity is already assigned") from None
    return user_response(user)


def oidc_client(request: Request) -> StarletteOAuth2App:
    if request.app.state.settings.authentication_mode != "oidc":
        raise HTTPException(status_code=503, detail="OIDC login is not configured")
    return cast(StarletteOAuth2App, request.app.state.oauth.create_client("organization"))


@router.get("/auth/oidc/login")
async def oidc_login(request: Request) -> Response:
    validate_origin(request)
    client = oidc_client(request)
    return await client.authorize_redirect(request, request.app.state.settings.oidc_redirect_uri)


@router.get("/auth/oidc/callback")
async def oidc_callback(request: Request, session: DatabaseSession) -> Response:
    client = oidc_client(request)
    try:
        # Authlib verifies the authorization state and the signed ID token
        # (issuer, audience, expiry and nonce) before producing userinfo.
        token = await client.authorize_access_token(request)
    except (OAuthError, JoseError, ValueError):
        request.session.clear()
        raise unauthorized() from None
    except HTTPError:
        request.session.clear()
        raise HTTPException(status_code=503, detail="Identity provider is unavailable") from None
    claims = token.get("userinfo")
    if not token.get("id_token") or not claims or claims.get("email_verified") is not True:
        request.session.clear()
        raise unauthorized()
    issuer, subject, email = claims.get("iss"), claims.get("sub"), claims.get("email")
    if not all(isinstance(value, str) and value for value in (issuer, subject, email)):
        request.session.clear()
        raise unauthorized()
    with session.begin():
        serialize_identity_changes(session)
        user = session.scalar(
            select(User).where(
                User.oidc_issuer == issuer, User.oidc_subject == subject, User.active.is_(True)
            )
        )
        if user is None or user.email != email.strip().lower():
            request.session.clear()
            raise unauthorized()
        tokens = add_session(session, request, user)
    request.session.clear()
    response = RedirectResponse(request.app.state.settings.frontend_url, status_code=303)
    session_cookies(response, request, *tokens)
    return response
