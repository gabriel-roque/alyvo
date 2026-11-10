from datetime import date, datetime, timedelta, timezone


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_identity_registration_refresh_and_logout_lifecycle(client):
    identify = client.post(
        "/api/v1/auth/patients/identify",
        json={"cpf": "987.654.321-00", "birth_date": "1985-05-20"},
    )
    assert identify.status_code == 200
    assert identify.json()["status"] == "registration_required"

    registration = client.post(
        "/api/v1/auth/patients/register",
        json={
            "name": "Paciente Cobertura",
            "email": "paciente.cobertura@alyvo.local",
            "registration_token": identify.json()["registration_token"],
        },
    )
    assert registration.status_code == 201
    assert registration.json()["status"] == "identified"

    identified = client.post(
        "/api/v1/auth/patients/identify",
        json={"cpf": "987.654.321-00", "birth_date": "1985-05-20"},
    )
    assert identified.status_code == 200
    assert identified.json()["patient"]["name"] == "Paciente Cobertura"

    login = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@alyvo.local", "password": "alyvo-demo"},
    )
    refresh_token = login.json()["refresh_token"]
    refreshed = client.post("/api/v1/auth/tokens/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refreshed.json()["refresh_token"]},
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/tokens/refresh", json={"refresh_token": refresh_token}
        ).status_code
        == 401
    )


def test_backoffice_catalog_lifecycle(client, admin_token):
    headers = _auth(admin_token)
    specialty = client.post(
        "/api/v1/backoffice/specialties",
        headers=headers,
        json={"name": "Neurologia Cobertura", "description": "Testes neurológicos"},
    ).json()
    unit = client.post(
        "/api/v1/backoffice/units",
        headers=headers,
        json={"name": "Unidade Cobertura", "address": "Rua dos Testes, 10"},
    ).json()
    insurer = client.post(
        "/api/v1/backoffice/insurers",
        headers=headers,
        json={"name": "Plano Cobertura"},
    ).json()
    exam = client.post(
        "/api/v1/backoffice/exams",
        headers=headers,
        json={
            "name": "Exame Cobertura",
            "preparation": "Sem preparo",
            "unit_ids": [unit["id"]],
        },
    ).json()

    doctor_payload = {
        "name": "Dra. Teste Cobertura",
        "crm": "CRM COVERAGE",
        "specialty_id": specialty["id"],
        "unit_id": unit["id"],
        "insurer_ids": [insurer["id"]],
    }
    doctor = client.post("/api/v1/backoffice/doctors", headers=headers, json=doctor_payload).json()
    doctor_payload["name"] = "Dra. Teste Atualizada"
    updated_doctor = client.put(
        f"/api/v1/backoffice/doctors/{doctor['id']}",
        headers=headers,
        json=doctor_payload,
    )
    assert updated_doctor.status_code == 200
    assert updated_doctor.json()["name"] == "Dra. Teste Atualizada"

    updated_specialty = client.patch(
        f"/api/v1/backoffice/specialties/{specialty['id']}",
        headers=headers,
        json={"name": "Neurologia Atualizada", "description": "Atualizada"},
    )
    assert updated_specialty.status_code == 200
    listed = client.get(
        "/api/v1/backoffice/specialties",
        headers=headers,
        params={"q": "Atualizada", "page_size": 10},
    )
    assert listed.json()["total"] == 1

    for resource, identifier in (
        ("doctors", doctor["id"]),
        ("exams", exam["id"]),
        ("insurers", insurer["id"]),
        ("units", unit["id"]),
        ("specialties", specialty["id"]),
    ):
        assert (
            client.delete(
                f"/api/v1/backoffice/{resource}/{identifier}", headers=headers
            ).status_code
            == 204
        )


def test_backoffice_scheduling_lifecycle(client, admin_token, patient_token):
    headers = _auth(admin_token)
    patient_headers = _auth(patient_token)
    doctors = client.get("/api/v1/backoffice/doctors", headers=headers).json()["items"]
    doctor = doctors[0]

    rule_payload = {
        "doctor_id": doctor["id"],
        "unit_id": doctor["unit_id"],
        "weekday": 6,
        "starts_at": "09:00:00",
        "ends_at": "11:00:00",
        "slot_minutes": 30,
    }
    rule = client.post(
        "/api/v1/backoffice/availability/rules", headers=headers, json=rule_payload
    ).json()
    rule_payload["active"] = False
    assert (
        client.patch(
            f"/api/v1/backoffice/availability/rules/{rule['id']}",
            headers=headers,
            json=rule_payload,
        ).status_code
        == 200
    )
    assert client.get("/api/v1/backoffice/availability/rules", headers=headers).status_code == 200

    block_start = datetime.now(timezone.utc) + timedelta(days=40)
    block = client.post(
        "/api/v1/backoffice/availability/blocks",
        headers=headers,
        json={
            "doctor_id": doctor["id"],
            "starts_at": block_start.isoformat(),
            "ends_at": (block_start + timedelta(hours=1)).isoformat(),
            "reason": "Teste de cobertura",
        },
    ).json()
    assert client.get("/api/v1/backoffice/availability/blocks", headers=headers).status_code == 200
    assert (
        client.delete(
            f"/api/v1/backoffice/availability/blocks/{block['id']}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/backoffice/availability/rules/{rule['id']}", headers=headers
        ).status_code
        == 204
    )

    patients = client.get("/api/v1/backoffice/patients", headers=headers).json()["items"]
    patient = next(item for item in patients if item["name"] == "Juliana Demo")
    assert client.get("/api/v1/backoffice/dashboard", headers=headers).status_code == 200
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=14)
    slots = client.get(
        "/api/v1/appointments/availability",
        params={"from_date": start.isoformat(), "to_date": end.isoformat()},
    ).json()["items"]
    first = slots[0]
    second = next(slot for slot in slots[1:] if slot["doctor"]["id"] == first["doctor"]["id"])
    created = client.post(
        "/api/v1/backoffice/appointments",
        headers=headers,
        json={
            "patient_id": patient["id"],
            "doctor_id": first["doctor"]["id"],
            "starts_at": first["starts_at"],
            "reason": "Consulta de cobertura",
        },
    )
    assert created.status_code == 201, created.text
    appointment = created.json()

    assert client.get("/api/v1/appointments/me", headers=patient_headers).status_code == 200
    assert (
        client.get(
            "/api/v1/backoffice/appointments",
            headers=headers,
            params={"start": start.isoformat(), "end": end.isoformat()},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/backoffice/appointments/{appointment['id']}",
            headers=headers,
            json={"starts_at": second["starts_at"], "reason": "Reagendada"},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/backoffice/appointments/{appointment['id']}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/appointments/{appointment['id']}", headers=patient_headers
        ).status_code
        == 204
    )
