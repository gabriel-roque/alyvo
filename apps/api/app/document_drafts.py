from __future__ import annotations

import json

from app.config import get_settings

_local: dict[str, dict] = {}


def _key(tenant_id: str, patient_id: str, document_id: str) -> str:
    return f"patient-document-draft:{tenant_id}:{patient_id}:{document_id}"


def put_draft(
    tenant_id: str,
    patient_id: str,
    document_id: str,
    fields: dict[str, str],
    confidence: dict[str, float],
    raw_ocr: str = "",
) -> None:
    key = _key(tenant_id, patient_id, document_id)
    value = {"fields": fields, "confidence": confidence, "raw_ocr": raw_ocr}
    if get_settings().app_env == "test":
        _local[key] = value
        return
    from redis import Redis

    Redis.from_url(get_settings().redis_url).setex(
        key,
        24 * 60 * 60,
        json.dumps(value, ensure_ascii=False),
    )


def get_draft(tenant_id: str, patient_id: str, document_id: str) -> dict:
    key = _key(tenant_id, patient_id, document_id)
    if get_settings().app_env == "test":
        return _local.get(key, {})
    from redis import Redis

    value = Redis.from_url(get_settings().redis_url).get(key)
    return json.loads(value) if value else {}


def delete_draft(tenant_id: str, patient_id: str, document_id: str) -> None:
    key = _key(tenant_id, patient_id, document_id)
    if get_settings().app_env == "test":
        _local.pop(key, None)
        return
    from redis import Redis

    Redis.from_url(get_settings().redis_url).delete(key)
