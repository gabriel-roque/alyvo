import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path("/tmp/alyvo-test.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["APP_ENV"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["OCR_PROVIDER"] = "mock"

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def patient_token(client):
    started = client.post("/api/v1/auth/patient/start", json={"cpf": "123.456.789-09"})
    assert started.status_code == 200
    verified = client.post(
        "/api/v1/auth/patient/verify",
        json={"cpf": "123.456.789-09", "code": "123456"},
    )
    assert verified.status_code == 200
    return verified.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client):
    response = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@alyvo.local", "password": "alyvo-demo"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]

