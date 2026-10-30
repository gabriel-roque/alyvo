from __future__ import annotations

import concurrent.futures
import os
import time
import uuid

import httpx
import psycopg
from neo4j import GraphDatabase

API = os.getenv("API_URL", "http://localhost:8000/api/v1")
ROOT = API.removesuffix("/api/v1")
TENANT = "clinic-alyvo"


def assert_ok(response: httpx.Response) -> dict:
    response.raise_for_status()
    return response.json() if response.content else {}


def main() -> None:
    with httpx.Client(timeout=120, headers={"X-Tenant-ID": TENANT}) as client:
        health = assert_ok(client.get(f"{ROOT}/health/deep"))
        assert health["status"] == "ok", health

        staff = assert_ok(client.post(f"{API}/auth/staff/login", json={"tenant_id": TENANT, "email": "admin@alyvo.local", "password": "alyvo-demo"}))
        admin = {"Authorization": f"Bearer {staff['access_token']}", "X-Tenant-ID": TENANT}
        specialties = assert_ok(client.get(f"{API}/backoffice/catalog/specialties", headers=admin))["items"]
        units = assert_ok(client.get(f"{API}/backoffice/catalog/units", headers=admin))["items"]
        insurers = assert_ok(client.get(f"{API}/backoffice/catalog/insurers", headers=admin))["items"]
        marker = uuid.uuid4().hex[:8]
        doctor_name = f"Dra. E2E {marker}"
        assert_ok(client.post(f"{API}/backoffice/doctors", headers=admin, json={"name": doctor_name, "crm": f"CRM {marker}", "specialty_id": specialties[0]["id"], "unit_id": units[0]["id"], "insurer_ids": [insurers[0]["id"]]}))

        graph_evidence = ""
        for _ in range(30):
            session = assert_ok(client.post(f"{API}/chat/sessions", json={"tenant_id": TENANT}))["id"]
            answer = assert_ok(client.post(f"{API}/chat/sessions/{session}/messages", json={"content": f"Onde {doctor_name} atende?"}))
            graph_evidence = answer["answer"] + " " + " ".join(item["excerpt"] for item in answer["citations"])
            if doctor_name in graph_evidence:
                break
            time.sleep(1)
        assert doctor_name in graph_evidence, "Outbox não projetou o novo médico no GraphRAG"

        rejected_marker = f"SEGREDO-REJEITADO-{marker}"
        ingestion = assert_ok(client.post(f"{API}/backoffice/ingestions", headers=admin, json={"title": "Documento rejeitado E2E", "content": rejected_marker}))
        assert_ok(client.post(f"{API}/backoffice/ingestions/{ingestion['id']}/reject", headers=admin))
        session = assert_ok(client.post(f"{API}/chat/sessions", json={"tenant_id": TENANT}))["id"]
        rejected_answer = assert_ok(client.post(f"{API}/chat/sessions/{session}/messages", json={"content": rejected_marker}))
        rejected_evidence = " ".join(item["excerpt"] for item in rejected_answer["citations"])
        assert rejected_marker not in rejected_evidence, "Ingestão rejeitada vazou para recuperação"

        with GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        ) as driver:
            with driver.session() as graph:
                matches = graph.run(
                    """
                    MATCH (d:Document {tenant_id: $tenant})-[:HAS_CHUNK]->(c:Chunk)
                    WHERE c.content CONTAINS $marker
                    RETURN count(c) AS matches
                    """,
                    tenant=TENANT,
                    marker=rejected_marker,
                ).single()["matches"]
        assert matches == 0, "Ingestão rejeitada alterou o GraphRAG"

        assert_ok(client.post(f"{API}/auth/patient/start", json={"tenant_id": TENANT, "cpf": "123.456.789-09"}))
        patient = assert_ok(client.post(f"{API}/auth/patient/verify", json={"tenant_id": TENANT, "cpf": "123.456.789-09", "code": "123456"}))
        patient_headers = {"Authorization": f"Bearer {patient['access_token']}", "X-Tenant-ID": TENANT}
        slot = assert_ok(client.get(f"{API}/availability?tenant_id={TENANT}"))["items"][0]
        reason = f"Concorrência E2E {marker}"
        payload = {"doctor_id": slot["doctor"]["id"], "starts_at": slot["starts_at"], "reason": reason, "confirmed": True}

        def book() -> int:
            with httpx.Client(timeout=30) as concurrent_client:
                return concurrent_client.post(f"{API}/appointments", headers=patient_headers, json=payload).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(lambda _: book(), range(2)))
        assert statuses == [201, 409], statuses
        appointments = assert_ok(client.get(f"{API}/appointments/me", headers=patient_headers))["items"]
        created = next(item for item in appointments if item["reason"] == reason and item["status"] == "confirmed")
        assert_ok(client.post(f"{API}/appointments/{created['id']}/cancel?confirmed=true", headers=patient_headers))

    database = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(database) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT,))
            cursor.execute("SELECT count(*) FROM knowledge_documents WHERE tenant_id = 'clinic-isolation'")
            assert cursor.fetchone()[0] == 0, "RLS permitiu leitura de outro tenant"

    print("Cenários de sistema aprovados: saúde, outbox, rejeição, concorrência e RLS.")


if __name__ == "__main__":
    main()
