from app.main import app


def test_scalar_and_openapi_are_available(client):
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "/openapi.json" in docs.text
    schema = client.get("/openapi.json").json()
    assert "/api/v1/meta" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    serialized = str(schema).casefold()
    assert "tenant_id" not in serialized
    assert "x-tenant-id" not in serialized


def test_every_business_route_is_versioned():
    paths = app.openapi()["paths"]
    assert all(path.startswith("/api/v1") or path.startswith("/health/") for path in paths)


def test_catalog_delete_returns_no_content(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/api/v1/backoffice/insurers",
        headers=headers,
        json={
            "name": "Convênio Sintético Temporário",
            "description": "",
            "address": "",
            "preparation": "",
            "unit_ids": [],
            "active": True,
        },
    )
    assert created.status_code == 201
    deleted = client.delete(
        f"/api/v1/backoffice/insurers/{created.json()['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204
    assert deleted.content == b""


def test_application_error_has_stable_envelope(client, patient_token):
    response = client.delete(
        "/api/v1/appointments/missing",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "field_errors", "correlation_id"}


def test_sse_contract_emits_status_delta_and_final(client):
    session_id = client.post("/api/v1/chat/sessions").json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages/stream",
        json={"content": "Olá"},
    )
    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: delta" in response.text
    assert "event: final" in response.text
