from io import BytesIO


def test_public_graphrag_answer_has_sources(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quais cardiologistas aceitam o convênio Vida+ na Unidade Centro?"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "knowledge"
    assert body["citations"]
    assert body["confidence"] >= 0.9
    assert "Marina Lopes" in body["answer"]


def test_clinical_request_is_refused(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Faça meu diagnóstico e prescreva um remédio"},
    )
    assert response.json()["intent"] == "clinical_safety"
    assert "Não faço diagnóstico" in response.json()["answer"]


def test_ocr_fields_are_not_confirmed_before_patient_review(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    upload = client.post(
        "/api/v1/patient/documents",
        headers=headers,
        files={"file": ("carteirinha-demo.png", BytesIO(b"synthetic-image"), "image/png")},
        data={"kind": "insurance_card"},
    )
    assert upload.status_code == 202
    document = upload.json()
    assert document["confirmed"] is False
    assert document["status"] == "review_required"
    confirmed = client.post(
        f"/api/v1/patient/documents/{document['id']}/confirm",
        headers=headers,
        json={"fields": {**document["fields"], "numero": "CORRIGIDO-123"}, "confirmed": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed"] is True
    assert confirmed.json()["fields"]["numero"] == "CORRIGIDO-123"

