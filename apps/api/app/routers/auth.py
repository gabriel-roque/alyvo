from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.providers import notification_provider
from app.config import get_settings
from app.db import get_db
from app.models import OtpCode, RefreshToken, Role, User
from app.observability import record
from app.security import (
    cpf_lookup,
    decode_token,
    hash_value,
    issue_token,
    protect_cpf,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class PatientStart(BaseModel):
    tenant_id: str = "clinic-alyvo"
    cpf: str
    email: str | None = None


class PatientVerify(BaseModel):
    tenant_id: str = "clinic-alyvo"
    cpf: str
    code: str


class PatientRegister(BaseModel):
    tenant_id: str = "clinic-alyvo"
    cpf: str
    name: str
    email: str
    registration_token: str


class StaffLogin(BaseModel):
    tenant_id: str = "clinic-alyvo"
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class PatientStartResponse(BaseModel):
    status: str
    expires_in: int
    delivery: str
    demo_code: str | None = None


class AuthResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    status: str | None = None
    registration_token: str | None = None
    patient: dict | None = None
    user: dict | None = None


def token_pair(user: User, db: Session) -> dict:
    refresh = issue_token(user.id, user.tenant_id, user.role.value, minutes=60 * 24 * 7, kind="refresh")
    db.add(
        RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=hash_value(refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    db.commit()
    return {
        "access_token": issue_token(user.id, user.tenant_id, user.role.value),
        "refresh_token": refresh,
        "token_type": "bearer",
    }


@router.post("/patient/start", response_model=PatientStartResponse)
def start_patient_auth(payload: PatientStart, db: Session = Depends(get_db)):
    key = cpf_lookup(payload.cpf)
    now = datetime.now(timezone.utc)
    recent = db.scalar(
        select(OtpCode).where(OtpCode.tenant_id == payload.tenant_id, OtpCode.cpf_hmac == key).order_by(desc(OtpCode.expires_at))
    )
    if recent and not recent.used_at and recent.expires_at.replace(tzinfo=timezone.utc) > now + timedelta(minutes=4):
        raise HTTPException(429, "Aguarde antes de solicitar outro código")
    code = get_settings().demo_otp
    db.add(OtpCode(tenant_id=payload.tenant_id, cpf_hmac=key, code_hash=hash_value(code), expires_at=now + timedelta(minutes=10)))
    db.commit()
    patient = db.scalar(select(User).where(User.tenant_id == payload.tenant_id, User.cpf_hmac == key))
    destination = patient.email if patient else payload.email
    if not destination:
        raise HTTPException(422, "Informe um e-mail para receber o código")
    notification_provider().send_otp(destination, code)
    record("auth.otp_requested", tenant_id=payload.tenant_id, patient_exists=bool(patient))
    response = {"status": "sent", "expires_in": 600, "delivery": "mailpit"}
    if get_settings().app_env != "production":
        response["demo_code"] = code
    return response


@router.post("/patient/verify", response_model=AuthResponse)
def verify_patient(payload: PatientVerify, db: Session = Depends(get_db)):
    key = cpf_lookup(payload.cpf)
    code = db.scalar(
        select(OtpCode).where(OtpCode.tenant_id == payload.tenant_id, OtpCode.cpf_hmac == key).order_by(desc(OtpCode.expires_at))
    )
    now = datetime.now(timezone.utc)
    if not code or code.used_at or code.expires_at.replace(tzinfo=timezone.utc) < now or code.attempts >= 5:
        raise HTTPException(401, "Código inválido ou expirado")
    code.attempts += 1
    if code.code_hash != hash_value(payload.code):
        db.commit()
        raise HTTPException(401, "Código inválido ou expirado")
    code.used_at = now
    patient = db.scalar(select(User).where(User.tenant_id == payload.tenant_id, User.cpf_hmac == key, User.role == Role.patient))
    db.commit()
    if not patient:
        return {"status": "registration_required", "registration_token": issue_token("pending", payload.tenant_id, "patient", 15, kind="registration")}
    result = token_pair(patient, db)
    record("auth.patient_verified", tenant_id=payload.tenant_id, user_id=patient.id)
    result["patient"] = {"id": patient.id, "name": patient.name}
    return result


@router.post("/patient/register", status_code=201, response_model=AuthResponse)
def register_patient(payload: PatientRegister, db: Session = Depends(get_db)):
    registration = decode_token(payload.registration_token)
    if registration.get("kind") != "registration" or registration.get("tenant") != payload.tenant_id:
        raise HTTPException(401, "Token de cadastro inválido")
    key = cpf_lookup(payload.cpf)
    if db.scalar(select(User).where(User.tenant_id == payload.tenant_id, User.cpf_hmac == key)):
        raise HTTPException(409, "Paciente já cadastrado")
    patient = User(tenant_id=payload.tenant_id, role=Role.patient, name=payload.name, email=payload.email, cpf_hmac=key, cpf_encrypted=protect_cpf(payload.cpf))
    db.add(patient)
    db.commit()
    db.refresh(patient)
    record("auth.patient_registered", tenant_id=payload.tenant_id, user_id=patient.id)
    return token_pair(patient, db)


@router.post("/staff/login", response_model=AuthResponse)
def login_staff(payload: StaffLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.tenant_id == payload.tenant_id, User.email == payload.email, User.role.in_([Role.admin, Role.receptionist])))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Credenciais inválidas")
    result = token_pair(user, db)
    record("auth.staff_login", tenant_id=payload.tenant_id, user_id=user.id, role=user.role.value)
    result["user"] = {"id": user.id, "name": user.name, "role": user.role.value}
    return result


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    identity = decode_token(payload.refresh_token)
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_value(payload.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
    )
    if identity.get("kind") != "refresh" or not stored:
        raise HTTPException(401, "Refresh token inválido")
    user = db.scalar(select(User).where(User.id == identity["sub"], User.tenant_id == identity["tenant"]))
    if not user:
        raise HTTPException(401, "Usuário inválido")
    stored.revoked_at = datetime.now(timezone.utc)
    return token_pair(user, db)


@router.post("/logout", status_code=204)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    if payload.refresh_token:
        stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_value(payload.refresh_token)))
        if stored:
            stored.revoked_at = datetime.now(timezone.utc)
            db.commit()
    return None

