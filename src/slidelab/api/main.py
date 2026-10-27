"""API для Mini App и раздача её статики.

uv run uvicorn --factory slidelab.api.main:create_app --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response
from starlette.types import Scope

from slidelab.api.routes import catalog, me, orders, packages, support
from slidelab.config import Settings, get_settings
from slidelab.core.db import make_engine, make_sessionmaker
from slidelab.core.errors import DomainError, ForbiddenError, NotFoundError
from slidelab.core.services.pricing import PricingError

log = logging.getLogger("slidelab.webapp")


class ClientError(BaseModel):
    message: str = Field(max_length=2000)
    ua: str | None = Field(default=None, max_length=500)
    tg_version: str | None = Field(default=None, max_length=20)
    platform: str | None = Field(default=None, max_length=40)
    url: str | None = Field(default=None, max_length=300)


WEBAPP_DIST = Path(__file__).resolve().parents[3] / "webapp" / "dist"

class WebappFiles(StaticFiles):
    """Файлы сборки с хэшем в имени кэшируются навсегда, index.html — всегда свежий."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


ERROR_STATUS: dict[type[DomainError], int] = {NotFoundError: 404, ForbiddenError: 403}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "sessionmaker", None) is not None:  # тесты подставили свои
            yield
            return
        engine = make_engine(settings.database_url)
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.bot = Bot(
            settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        app.state.storage = RedisStorage.from_url(settings.redis_url) if settings.redis_url else MemoryStorage()
        yield
        await app.state.bot.session.close()
        await app.state.storage.close()
        await engine.dispose()

    app = FastAPI(title="SlideLab API", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.api_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = next((code for cls, code in ERROR_STATUS.items() if isinstance(exc, cls)), 409)
        return JSONResponse({"code": exc.code, "detail": str(exc)}, status_code=status)

    @app.exception_handler(PricingError)
    async def pricing_error(request: Request, exc: PricingError) -> JSONResponse:
        return JSONResponse({"code": "pricing", "detail": str(exc)}, status_code=422)

    for module in (me, catalog, orders, packages, support):
        app.include_router(module.router, prefix="/api")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/client-errors", status_code=204)
    async def client_error(report: ClientError) -> None:
        """Ошибки Mini App на устройстве клиента — иначе мы видели бы только «чёрный экран»."""
        log.warning(
            "Mini App упала: %s | tg=%s %s | %s",
            report.message,
            report.tg_version,
            report.platform,
            report.ua,
        )

    # Собранная Mini App (webapp/dist) — с того же домена, без CORS
    if WEBAPP_DIST.is_dir():
        app.mount("/", WebappFiles(directory=WEBAPP_DIST, html=True), name="webapp")
    return app
