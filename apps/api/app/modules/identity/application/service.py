from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.identity.infrastructure.security import (
    cpf_lookup,
    hash_value,
    issue_token,
    protect_cpf,
    verify_password,
)
from app.shared.application import AuthenticationRequiredError, ConflictError, NotFoundError
from app.shared.infrastructure.models import RefreshToken, Role, User
from app.shared.infrastructure.uow import SqlAlchemyUnitOfWork, uow_factory


class IdentityService:
    def __init__(self, factory=uow_factory):
        self._factory = factory

    def identify_patient(self, cpf: str, birth_date: date) -> dict:
        with self._factory() as uow:
            patient = uow.session.scalar(
                select(User).where(
                    User.cpf_hmac == cpf_lookup(cpf),
                    User.role == Role.patient,
                    User.archived_at.is_(None),
                )
            )
            if not patient:
                token = issue_token(
                    "pending",
                    Role.patient.value,
                    minutes=15,
                    kind="registration",
                    claims={"cpf": protect_cpf(cpf), "birth_date": birth_date.isoformat()},
                )
                return {"status": "registration_required", "registration_token": token}
            if patient.birth_date != birth_date:
                raise AuthenticationRequiredError("CPF ou data de nascimento inválidos")
            return self._patient_tokens(patient, uow)

    def register_patient(self, name: str, email: str, registration: dict) -> dict:
        if registration.get("kind") != "registration":
            raise AuthenticationRequiredError("Cadastro expirado ou inválido")
        with self._factory() as uow:
            if uow.session.scalar(select(User.id).where(User.email == email)):
                raise ConflictError("E-mail já cadastrado")
            patient = User(
                role=Role.patient,
                name=name,
                email=email,
                password_hash=None,
                cpf_hmac=cpf_lookup_from_encrypted(registration["cpf"]),
                cpf_encrypted=registration["cpf"],
                birth_date=date.fromisoformat(registration["birth_date"]),
            )
            uow.session.add(patient)
            try:
                uow.flush()
            except IntegrityError as exc:
                raise ConflictError("Paciente já cadastrado") from exc
            return self._patient_tokens(patient, uow)

    def login_staff(self, email: str, password: str) -> dict:
        with self._factory() as uow:
            user = uow.session.scalar(
                select(User).where(User.email == email, User.archived_at.is_(None))
            )
            if not user or user.role not in {Role.admin, Role.receptionist}:
                raise AuthenticationRequiredError("Credenciais inválidas")
            if not verify_password(password, user.password_hash):
                raise AuthenticationRequiredError("Credenciais inválidas")
            return self._staff_tokens(user, uow)

    def refresh(self, raw_token: str, payload: dict) -> dict:
        if payload.get("kind") != "refresh":
            raise AuthenticationRequiredError("Refresh token inválido")
        with self._factory() as uow:
            stored = uow.session.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == hash_value(raw_token))
            )
            now = datetime.now(timezone.utc)
            if not stored or stored.revoked_at or stored.expires_at <= now:
                raise AuthenticationRequiredError("Refresh token revogado")
            user = uow.session.get(User, stored.user_id)
            if not user:
                raise NotFoundError("Usuário não encontrado")
            stored.revoked_at = now
            return self._staff_tokens(user, uow)

    def logout(self, raw_token: str) -> None:
        with self._factory() as uow:
            stored = uow.session.scalar(
                select(RefreshToken).where(RefreshToken.token_hash == hash_value(raw_token))
            )
            if stored and not stored.revoked_at:
                stored.revoked_at = datetime.now(timezone.utc)

    def _patient_tokens(self, patient: User, uow: SqlAlchemyUnitOfWork) -> dict:
        return {
            "status": "identified",
            "access_token": issue_token(patient.id, Role.patient.value),
            "patient": {"id": patient.id, "name": patient.name},
        }

    def _staff_tokens(self, user: User, uow: SqlAlchemyUnitOfWork) -> dict:
        access = issue_token(user.id, user.role.value)
        refresh = issue_token(user.id, user.role.value, minutes=60 * 24 * 7, kind="refresh")
        uow.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_value(refresh),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        )
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def cpf_lookup_from_encrypted(value: str) -> str:
    from app.modules.identity.infrastructure.security import unprotect_cpf

    return cpf_lookup(unprotect_cpf(value))
