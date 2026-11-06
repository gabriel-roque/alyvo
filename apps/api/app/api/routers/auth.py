from fastapi import APIRouter, Response

from app.api.schemas.identity import (
    PatientAuthResponse,
    PatientIdentify,
    PatientRegister,
    StaffLogin,
    TokenBody,
    TokenResponse,
)
from app.modules.identity.application import IdentityService
from app.modules.identity.infrastructure.security import decode_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/patients/identify", response_model=PatientAuthResponse)
def identify(payload: PatientIdentify):
    return IdentityService().identify_patient(payload.cpf, payload.birth_date)


@router.post("/patients/register", response_model=PatientAuthResponse, status_code=201)
def register(payload: PatientRegister):
    registration = decode_token(payload.registration_token)
    return IdentityService().register_patient(payload.name, payload.email, registration)


@router.post("/staff/login", response_model=TokenResponse)
def login(payload: StaffLogin):
    return IdentityService().login_staff(payload.email, payload.password)


@router.post("/tokens/refresh", response_model=TokenResponse)
def refresh(payload: TokenBody):
    return IdentityService().refresh(payload.refresh_token, decode_token(payload.refresh_token))


@router.post("/logout", status_code=204)
def logout(payload: TokenBody):
    IdentityService().logout(payload.refresh_token)
    return Response(status_code=204)
