from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RefreshToken, Role, User
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


class PatientIdentify(BaseModel):
    tenant_id: str = "clinic-alyvo"
    cpf: str
    birth_date: date


class PatientRegister(BaseModel):
    tenant_id: str = "clinic-alyvo"
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


def patient_access(user: User) -> dict:
    return {
        "status": "authenticated",
        "access_token": issue_token(user.id, user.tenant_id, Role.patient.value),
        "token_type": "bearer",
        "patient": {"id": user.id, "name": user.name},
    }


def staff_tokens(user: User, db: Session) -> dict:
    refresh = issue_token(
        user.id, user.tenant_id, user.role.value, minutes=60 * 24 * 7, kind="refresh"
    )
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
        "user": {"id": user.id, "name": user.name, "role": user.role.value},
    }


@router.post("/patient/identify")
def identify_patient(payload: PatientIdentify, db: Session = Depends(get_db)):
    key = cpf_lookup(payload.cpf)
    patient = db.scalar(
        select(User).where(
            User.tenant_id == payload.tenant_id,
            User.cpf_hmac == key,
            User.role == Role.patient,
            User.deleted_at.is_(None),
        )
    )
    if patient:
        if patient.birth_date != payload.birth_date:
            record("auth.patient_rejected", tenant_id=payload.tenant_id)
            raise HTTPException(401, "CPF ou data de nascimento inválidos")
        record("auth.patient_identified", tenant_id=payload.tenant_id, user_id=patient.id)
        return patient_access(patient)
    registration_token = issue_token(
        "pending",
        payload.tenant_id,
        Role.patient.value,
        minutes=15,
        kind="registration",
        claims={"cpf_hmac": key, "cpf": payload.cpf, "birth_date": payload.birth_date.isoformat()},
    )
    return {"status": "registration_required", "registration_token": registration_token}


@router.post("/patient/register", status_code=201)
def register_patient(payload: PatientRegister, db: Session = Depends(get_db)):
    claims = decode_token(payload.registration_token)
    if claims.get("kind") != "registration" or claims.get("tenant") != payload.tenant_id:
        raise HTTPException(401, "Cadastro expirado ou inválido")
    if db.scalar(
        select(User).where(
            User.tenant_id == payload.tenant_id,
            User.cpf_hmac == claims["cpf_hmac"],
        )
    ):
        raise HTTPException(409, "Paciente já cadastrado")
    patient = User(
        tenant_id=payload.tenant_id,
        role=Role.patient,
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        cpf_hmac=claims["cpf_hmac"],
        cpf_encrypted=protect_cpf(claims["cpf"]),
        birth_date=date.fromisoformat(claims["birth_date"]),
    )
    db.add(patient)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "E-mail já cadastrado") from exc
    db.refresh(patient)
    record("auth.patient_registered", tenant_id=payload.tenant_id, user_id=patient.id)
    return patient_access(patient)


@router.post("/staff/login")
def login_staff(payload: StaffLogin, db: Session = Depends(get_db)):
    user = db.scalar(
        select(User).where(
            User.tenant_id == payload.tenant_id,
            User.email == payload.email.strip().lower(),
            User.role.in_([Role.admin, Role.receptionist]),
            User.deleted_at.is_(None),
        )
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Credenciais inválidas")
    return staff_tokens(user, db)


@router.post("/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    claims = decode_token(payload.refresh_token)
    if claims.get("kind") != "refresh" or claims.get("role") == Role.patient.value:
        raise HTTPException(401, "Refresh token inválido")
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_value(payload.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
    )
    if not stored:
        raise HTTPException(401, "Refresh token revogado")
    user = db.get(User, claims["sub"])
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    stored.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return staff_tokens(user, db)


@router.post("/logout", status_code=204)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    if payload.refresh_token:
        stored = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_value(payload.refresh_token))
        )
        if stored:
            stored.revoked_at = datetime.now(timezone.utc)
            db.commit()
