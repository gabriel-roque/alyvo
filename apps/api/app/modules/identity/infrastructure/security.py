from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken

from app.bootstrap.config import get_settings
from app.modules.identity.domain import Actor, UserRole
from app.shared.application import AuthenticationRequiredError, ValidationError


def normalize_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        raise ValidationError("CPF deve conter 11 dígitos")
    return digits


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().app_secret.encode()).digest())
    return Fernet(key)


def cpf_lookup(value: str) -> str:
    return hmac.new(
        get_settings().app_secret.encode(), normalize_cpf(value).encode(), hashlib.sha256
    ).hexdigest()


def protect_cpf(value: str) -> str:
    return _fernet().encrypt(normalize_cpf(value).encode()).decode()


def unprotect_cpf(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return ""


def mask_cpf(value: str | None) -> str:
    digits = unprotect_cpf(value)
    return f"***.{digits[3:6]}.{digits[6:9]}-**" if len(digits) == 11 else "***"


def hash_value(value: str) -> str:
    return hmac.new(get_settings().app_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def issue_token(
    user_id: str,
    role: str,
    minutes: int = 120,
    kind: str = "access",
    claims: dict | None = None,
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "kind": kind,
        "jti": secrets.token_urlsafe(12),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=minutes)).timestamp()),
        **(claims or {}),
    }
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(
        get_settings().app_secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return f"{body}.{signature}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().app_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise AuthenticationRequiredError("Token inválido ou expirado") from exc


def actor_from_token(token: str) -> Actor:
    payload = decode_token(token)
    return Actor(id=payload["sub"], role=UserRole(payload["role"]))


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
