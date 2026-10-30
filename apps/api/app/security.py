import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from .config import get_settings


def normalize_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        raise HTTPException(422, "CPF deve conter 11 dígitos")
    return digits


def cpf_lookup(value: str) -> str:
    return hmac.new(get_settings().app_secret.encode(), normalize_cpf(value).encode(), hashlib.sha256).hexdigest()


def protect_cpf(value: str) -> str:
    from cryptography.fernet import Fernet

    digits = normalize_cpf(value)
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().app_secret.encode()).digest())
    return Fernet(key).encrypt(digits.encode()).decode()


def hash_value(value: str) -> str:
    return hmac.new(get_settings().app_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: str, tenant_id: str, role: str, minutes: int = 120, kind: str = "access") -> str:
    payload = {
        "sub": user_id,
        "tenant": tenant_id,
        "role": role,
        "kind": kind,
        "jti": secrets.token_urlsafe(12),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=minutes)).timestamp()),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(get_settings().app_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(get_settings().app_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if payload["exp"] < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Token inválido ou expirado") from exc


def current_identity(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Autenticação necessária")
    return decode_token(authorization.removeprefix("Bearer "))


def optional_identity(authorization: str | None = Header(default=None)) -> dict | None:
    if not authorization:
        return None
    return current_identity(authorization)


def require_staff(identity: dict) -> None:
    if identity["role"] not in {"admin", "receptionist"}:
        raise HTTPException(403, "Acesso restrito à equipe")


def require_admin(identity: dict) -> None:
    if identity["role"] != "admin":
        raise HTTPException(403, "Acesso restrito à administração")


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000)
    return f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        _, salt, _ = encoded.split("$", 2)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), encoded)

