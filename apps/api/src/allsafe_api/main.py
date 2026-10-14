"""Application factory and development ASGI entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from allsafe_api import __version__
from allsafe_api.config import Settings
from allsafe_api.database import (
    build_engine,
    make_session_factory,
    prepare_database_directory,
)
from allsafe_api.identity import initialize_identity
from allsafe_api.identity import router as identity_router
from allsafe_api.models import Base
from allsafe_api.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings if settings is not None else Settings()
    engine = build_engine(configured.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            if configured.environment == "production":
                raise RuntimeError(
                    "Production deployment is not supported by this graduation-project prototype. "
                    "Local lab identity and optional OIDC require a deployment security review."
                )
            prepare_database_directory(configured.database_url)
            if configured.initialize_schema:
                Base.metadata.create_all(engine)
            initialize_identity(application)
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="ALLSAFE Core API",
        version=__version__,
        description=(
            "Single-organization lab foundation: enrollment, heartbeat, inventory and audit. "
            "Local user identity and optional OIDC are for an audited laboratory configuration."
        ),
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.engine = engine
    application.state.session_factory = make_session_factory(engine)
    if configured.authentication_mode == "oidc":
        application.add_middleware(
            SessionMiddleware,
            secret_key=configured.session_signing_secret.get_secret_value(),
            session_cookie="allsafe_oidc_state",
            max_age=600,
            https_only=configured.cookie_secure,
            same_site="lax",
        )
        oauth = OAuth()
        oauth.register(
            name="organization",
            client_id=configured.oidc_client_id,
            client_secret=configured.oidc_client_secret.get_secret_value(),
            server_metadata_url=configured.oidc_server_metadata_url,
            client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
        )
        application.state.oauth = oauth

    @application.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's default error input can echo bearer-like enrollment credentials.
        # Return useful field errors without copying submitted payloads into responses.
        errors = [
            {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    application.include_router(router)
    application.include_router(identity_router)
    return application


app = create_app()
