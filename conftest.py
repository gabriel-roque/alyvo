import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path("/tmp/alyvo-test.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
# An explicit empty value wins over a developer's local .env; popping the
# variable would let pydantic-settings load DATABASE_ADMIN_URL from that file.
os.environ["DATABASE_ADMIN_URL"] = f"sqlite:///{TEST_DB}"
os.environ["APP_ENV"] = "test"
os.environ["LLM_PRIMARY_PROVIDER"] = "mock"
os.environ["LLM_FALLBACK_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["OCR_PROVIDER"] = "mock"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""

from app.bootstrap.seed import seed  # noqa: E402
from app.main import app  # noqa: E402
from app.shared.infrastructure.database import engine  # noqa: E402
from app.shared.infrastructure.models import Base  # noqa: E402

for table in Base.metadata.sorted_tables:
    table.create(engine)
seed()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def patient_token(client):
    identified = client.post(
        "/api/v1/auth/patients/identify",
        json={"cpf": "123.456.789-09", "birth_date": "1990-01-15"},
    )
    assert identified.status_code == 200
    return identified.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client):
    response = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@alyvo.local", "password": "alyvo-demo"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]
