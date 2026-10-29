from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import OtpCode, Role, User
from app.security import cpf_lookup, hash_value, issue_token, protect_cpf

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


class StaffLogin(BaseModel):
    tenant_id: str = "clinic-alyvo"
    email: str
    password: str


@router.post("/patient/start")
def start_patient_auth(payload: PatientStart, db: Session = Depends(get_db)):
    key = cpf_lookup(payload.cpf)
    now = datetime.now(timezone.utc)
    recent = db.scalar(
        select(OtpCode).where(OtpCode.tenant_id == payload.tenant_id, OtpCode.cpf_hmac == key).order_by(desc(OtpCode.expires_at))
    )
    if recent and recent.expires_at.replace(tzinfo=timezone.utc) > now + timedelta(minutes=4):
        raise HTTPException(429, "Aguarde antes de solicitar outro código")
    code = get_settings().demo_otp
    db.add(OtpCode(tenant_id=payload.tenant_id, cpf_hmac=key, code_hash=hash_value(code), expires_at=now + timedelta(minutes=10)))
    db.commit()
    response = {"status": "sent", "expires_in": 600, "delivery": "mailpit"}
    if get_settings().app_env != "production":
        response["demo_code"] = code
    return response


@router.post("/patient/verify")
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
        return {"status": "registration_required", "registration_token": issue_token("pending", payload.tenant_id, "patient", 15)}
    return {"access_token": issue_token(patient.id, patient.tenant_id, patient.role.value), "token_type": "bearer", "patient": {"id": patient.id, "name": patient.name}}


@router.post("/patient/register", status_code=201)
def register_patient(payload: PatientRegister, db: Session = Depends(get_db)):
    key = cpf_lookup(payload.cpf)
    if db.scalar(select(User).where(User.tenant_id == payload.tenant_id, User.cpf_hmac == key)):
        raise HTTPException(409, "Paciente já cadastrado")
    patient = User(tenant_id=payload.tenant_id, role=Role.patient, name=payload.name, email=payload.email, cpf_hmac=key, cpf_encrypted=protect_cpf(payload.cpf))
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return {"access_token": issue_token(patient.id, patient.tenant_id, patient.role.value), "token_type": "bearer"}


@router.post("/staff/login")
def login_staff(payload: StaffLogin, db: Session = Depends(get_db)):
    if payload.password != "alyvo-demo":
        raise HTTPException(401, "Credenciais inválidas")
    user = db.scalar(select(User).where(User.tenant_id == payload.tenant_id, User.email == payload.email, User.role.in_([Role.admin, Role.receptionist])))
    if not user:
        raise HTTPException(401, "Credenciais inválidas")
    return {"access_token": issue_token(user.id, user.tenant_id, user.role.value), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "role": user.role.value}}


@router.post("/refresh")
def refresh():
    return {"detail": "Use login/OTP na demonstração local"}


@router.post("/logout", status_code=204)
def logout():
    return None

