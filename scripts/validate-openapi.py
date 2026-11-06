"""Minimal deterministic contract validation without calling external services."""

import json
from pathlib import Path

document = json.loads(Path("packages/contracts/openapi.json").read_text())
assert document.get("openapi", "").startswith("3.")
assert document.get("paths")
assert document.get("components", {}).get("schemas")
required_paths = {
    "/health/live",
    "/health/ready",
    "/api/v1/meta",
    "/api/v1/auth/patients/identify",
    "/api/v1/auth/staff/login",
    "/api/v1/appointments",
    "/api/v1/chat/sessions/{session_id}/messages/stream",
    "/api/v1/backoffice/knowledge/documents/{document_id}/publish",
}
missing_paths = required_paths - document["paths"].keys()
assert not missing_paths, f"Rotas obrigatórias ausentes: {sorted(missing_paths)}"

for path, path_item in document["paths"].items():
    for method, operation in path_item.items():
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue
        for status, response in operation.get("responses", {}).items():
            if not status.startswith("2"):
                continue
            for media_type, media in response.get("content", {}).items():
                assert media.get("schema"), (
                    f"Schema de sucesso vazio em {method.upper()} {path} ({status} {media_type})"
                )

security_schemes = document["components"].get("securitySchemes", {})
assert security_schemes.get("BearerAuth", {}).get("scheme") == "bearer"
serialized = json.dumps(document).casefold()
for forbidden in ("x-tenant-id", "tenant_id", "real-token", "production-secret"):
    assert forbidden not in serialized, f"OpenAPI contém valor proibido: {forbidden}"
