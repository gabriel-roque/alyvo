import smtplib
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import AdminSessionLocal, create_schema, engine, tenant_context
from .migrations import apply_migrations
from .observability import correlation_id_context, record
from .rate_limit import limiter
from .routers import auth, backoffice, chat, operations
from .security import decode_token
from .seed import ensure_seeded


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    apply_migrations()
    with AdminSessionLocal() as db:
        ensure_seeded(db)
    yield


app = FastAPI(
    title="Alyvo API",
    version="0.1.0",
    description=(
        "API multi-tenant do assistente administrativo Alyvo. Usa somente dados sintéticos; "
        "não oferece diagnóstico, prescrição ou triagem."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    tenant_id = request.headers.get("x-tenant-id", get_settings().demo_tenant)
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        try:
            tenant_id = decode_token(authorization.removeprefix("Bearer "))["tenant"]
        except Exception:
            pass
    if request.url.path.endswith(("/patient/start", "/patient/verify", "/patient/register", "/staff/login", "/refresh")):
        operation_name = request.url.path.rsplit("/", 2)[-2:]
        limiter.check(f"auth:{':'.join(operation_name)}:{request.client.host if request.client else 'unknown'}", 10)
    elif "/chat/" in request.url.path and request.method == "POST":
        limiter.check(f"chat:{request.client.host if request.client else 'unknown'}")
    tenant_token = tenant_context.set(tenant_id)
    correlation_token = correlation_id_context.set(request_id)
    try:
        response = await call_next(request)
    finally:
        tenant_context.reset(tenant_token)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "same-origin"
    record(
        "http.request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    correlation_id_context.reset(correlation_token)
    return response


@app.get("/health", tags=["system"])
def health():
    database = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - response is the diagnostic
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "environment": get_settings().app_env,
        "providers": {
            "llm": get_settings().llm_provider,
            "embedding": get_settings().embedding_provider,
            "ocr": get_settings().ocr_provider,
        },
    }


@app.get("/health/deep", tags=["system"])
def deep_health():
    services = {
        "postgres": "ok",
        "redis": "ok",
        "neo4j": "ok",
        "minio": "ok",
        "mailpit": "ok",
        "ollama": "ok",
    }
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        services["postgres"] = "unavailable"
    try:
        from redis import Redis

        Redis.from_url(get_settings().redis_url).ping()
    except Exception:
        services["redis"] = "unavailable"
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(get_settings().neo4j_uri, auth=(get_settings().neo4j_user, get_settings().neo4j_password))
        driver.verify_connectivity()
        driver.close()
    except Exception:
        services["neo4j"] = "unavailable"
    try:
        from app.ai.providers import object_storage_provider

        object_storage_provider()
    except Exception:
        services["minio"] = "unavailable"
    try:
        with smtplib.SMTP(get_settings().smtp_host, get_settings().smtp_port, timeout=3):
            pass
    except Exception:
        services["mailpit"] = "unavailable"
    if get_settings().llm_provider == "ollama":
        try:
            response = httpx.get(f"{get_settings().ollama_base_url}/api/tags", timeout=3)
            response.raise_for_status()
        except Exception:
            services["ollama"] = "unavailable"
    status = "ok" if all(value == "ok" for value in services.values()) else "degraded"
    return JSONResponse({"status": status, "services": services}, status_code=200 if status == "ok" else 503)


@app.get("/api/v1/meta", tags=["system"])
def meta():
    return {
        "name": "Alyvo",
        "mode": "administrative-only",
        "data_policy": "synthetic-only",
        "demo_tenant": get_settings().demo_tenant,
    }


for api_router in (auth.router, operations.router, chat.router, backoffice.router):
    app.include_router(api_router, prefix="/api/v1")

