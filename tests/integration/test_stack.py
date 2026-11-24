from __future__ import annotations

import os

import httpx
import pytest
from neo4j import GraphDatabase
from redis import Redis
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    "STACK_DATABASE_URL" not in os.environ,
    reason="full-stack integration environment is not running",
)


def test_api_and_web_are_ready() -> None:
    api_url = os.environ["API_URL"].rstrip("/")
    api_root = api_url.removesuffix("/api/v1")

    readiness = httpx.get(f"{api_root}/health/ready", timeout=10)
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ok"

    metadata = httpx.get(f"{api_url}/meta", timeout=10)
    assert metadata.status_code == 200

    web = httpx.get(os.environ["WEB_URL"], timeout=10)
    assert web.status_code == 200
    assert "Alyvo" in web.text


def test_postgres_schema_is_at_migration_head() -> None:
    engine = create_engine(os.environ["STACK_DATABASE_URL"])
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'chat_sessions'"
                )
            )
        }
    engine.dispose()

    assert revision == "0002_conversation_context"
    assert "context_json" in columns


def test_redis_is_reachable() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"])
    try:
        assert client.ping() is True
    finally:
        client.close()


def test_neo4j_is_reachable() -> None:
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


def test_minio_and_ollama_are_ready() -> None:
    minio = httpx.get(f"{os.environ['MINIO_URL']}/minio/health/live", timeout=10)
    assert minio.status_code == 200

    tags = httpx.get(f"{os.environ['OLLAMA_URL']}/api/tags", timeout=10)
    assert tags.status_code == 200
    assert tags.json()["models"]
