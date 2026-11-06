from datetime import date

from app.api.schemas.common import StrictModel


class PatientIdentify(StrictModel):
    cpf: str
    birth_date: date


class PatientRegister(StrictModel):
    name: str
    email: str
    registration_token: str


class StaffLogin(StrictModel):
    email: str
    password: str


class TokenBody(StrictModel):
    refresh_token: str


class PatientView(StrictModel):
    id: str
    name: str


class PatientAuthResponse(StrictModel):
    status: str
    access_token: str | None = None
    registration_token: str | None = None
    patient: PatientView | None = None


class TokenResponse(StrictModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
