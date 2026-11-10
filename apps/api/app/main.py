from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.errors import install_error_handlers
from app.api.routers import auth, backoffice_router, chat, public
from app.api.schemas.common import ErrorResponse, LivenessResponse, MetaResponse, ReadinessResponse
from app.bootstrap.config import get_settings
from app.infrastructure.providers import embedding_provider
from app.shared.infrastructure.database import engine
from app.shared.infrastructure.observability import correlation_id_context, record


@asynccontextmanager
async def lifespan(_: FastAPI):
    active_settings = get_settings()
    if active_settings.app_env not in {"test", "studio"}:
        started = time.perf_counter()
        await asyncio.to_thread(lambda: embedding_provider().embed(["Alyvo"]))
        record(
            "embedding.warmed",
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    record("application.started", environment=active_settings.app_env)
    yield
    record("application.stopped")


settings = get_settings()
app = FastAPI(
    title="Alyvo API",
    version="1.0.0",
    description="Assistente administrativo single-clinic. Não oferece diagnóstico, prescrição ou triagem.",
    servers=[
        {"url": "/", "description": "Ambiente atual"},
        {"url": "http://localhost:8000", "description": "Desenvolvimento local"},
    ],
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    responses={
        401: {"model": ErrorResponse, "description": "Autenticação necessária"},
        403: {"model": ErrorResponse, "description": "Operação não autorizada"},
        404: {"model": ErrorResponse, "description": "Recurso não encontrado"},
        409: {"model": ErrorResponse, "description": "Conflito de negócio"},
        422: {"model": ErrorResponse, "description": "Entrada ou regra inválida"},
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_web_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    token = correlation_id_context.set(request_id)
    response = None
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "same-origin"
        return response
    finally:
        record(
            "http.request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code if response else 500,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        correlation_id_context.reset(token)


@app.get("/health/live", tags=["system"], response_model=LivenessResponse)
def liveness():
    return {"status": "ok"}


@app.get(
    "/health/ready",
    tags=["system"],
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "Dependência indisponível"}},
)
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "unavailable"}, status_code=503)


@app.get("/api/v1/meta", tags=["system"], response_model=MetaResponse)
def meta():
    return {
        "name": "Alyvo",
        "mode": "administrative-only",
        "clinic": settings.clinic_name,
        "timezone": settings.clinic_timezone,
        "data_policy": "synthetic-only",
    }


if settings.api_docs_enabled:
    from scalar_fastapi import get_scalar_api_reference

    @app.get("/docs", include_in_schema=False)
    def scalar_docs():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url or "/openapi.json",
            title="Alyvo API Reference",
            theme="purple",
            custom_css="""
                :root { --scalar-color-accent: #6d4aff; }
                .dark-mode { --scalar-color-accent: #9f8cff; }
            """,
            hide_models=False,
        )


for router in (auth.router, public.router, chat.router, backoffice_router):
    app.include_router(router, prefix="/api/v1")
