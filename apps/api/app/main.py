import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import get_settings
from .db import SessionLocal, create_schema, engine
from .routers import auth, backoffice, chat, operations
from .seed import ensure_seeded


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    with SessionLocal() as db:
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
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "same-origin"
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

