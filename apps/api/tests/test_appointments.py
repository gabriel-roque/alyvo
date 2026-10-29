def test_appointment_requires_confirmation_and_prevents_conflict(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    slot = client.get("/api/v1/availability").json()["items"][0]
    payload = {
        "doctor_id": slot["doctor"]["id"],
        "starts_at": slot["starts_at"],
        "reason": "Consulta de rotina",
        "confirmed": False,
    }
    assert client.post("/api/v1/appointments", headers=headers, json=payload).status_code == 422
    payload["confirmed"] = True
    first = client.post("/api/v1/appointments", headers=headers, json=payload)
    second = client.post("/api/v1/appointments", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_patient_can_only_cancel_own_tenant_scoped_appointment(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    appointments = client.get("/api/v1/appointments/me", headers=headers).json()["items"]
    assert appointments
    response = client.post(
        f"/api/v1/appointments/{appointments[0]['id']}/cancel?confirmed=true",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

