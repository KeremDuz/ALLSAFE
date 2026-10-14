"""Application factory and development ASGI entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from allsafe_api import __version__
from allsafe_api.config import Settings
from allsafe_api.database import (
    build_engine,
    make_session_factory,
    prepare_database_directory,
)
from allsafe_api.models import Base
from allsafe_api.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings if settings is not None else Settings()
    engine = build_engine(configured.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            if configured.environment == "production":
                raise RuntimeError(
                    "Production is not supported by the bootstrap administrator authentication. "
                    "Configure user identity and authorization before a production deployment."
                )
            prepare_database_directory(configured.database_url)
            if configured.initialize_schema:
                Base.metadata.create_all(engine)
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="ALLSAFE Core API",
        version=__version__,
        description=(
            "Single-organization lab foundation: enrollment, heartbeat, inventory and audit. "
            "Bootstrap administrator authentication is for development only."
        ),
        lifespan=lifespan,
    )
    application.state.settings = configured
    application.state.engine = engine
    application.state.session_factory = make_session_factory(engine)

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
    return application


app = create_app()
