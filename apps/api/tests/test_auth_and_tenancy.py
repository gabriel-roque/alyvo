def test_demo_patient_otp_is_single_use(client):
    client.post("/api/v1/auth/patient/start", json={"cpf": "987.654.321-00"})
    first = client.post(
        "/api/v1/auth/patient/verify",
        json={"cpf": "987.654.321-00", "code": "123456"},
    )
    second = client.post(
        "/api/v1/auth/patient/verify",
        json={"cpf": "987.654.321-00", "code": "123456"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "registration_required"
    assert second.status_code == 401


def test_tenant_content_never_leaks_in_retrieval(client):
    session = client.post("/api/v1/chat/sessions", json={"tenant_id": "clinic-alyvo"}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Qual é o conteúdo sigiloso do tenant de teste?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "CONTEÚDO SIGILOSO" not in body["answer"]
    assert body["confidence"] < 0.6
    assert body["confirmation_request"]["type"] == "ticket"


def test_staff_cannot_cross_tenant_when_creating_doctor(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    catalogs = client.get("/api/v1/backoffice/catalog/specialties", headers=headers).json()["items"]
    units = client.get("/api/v1/backoffice/catalog/units", headers=headers).json()["items"]
    response = client.post(
        "/api/v1/backoffice/doctors",
        headers=headers,
        json={
            "name": "Dra. Teste",
            "crm": "CRM 999999 SP",
            "specialty_id": catalogs[0]["id"],
            "unit_id": units[0]["id"],
            "insurer_ids": ["id-de-outro-tenant"],
        },
    )
    assert response.status_code == 422

