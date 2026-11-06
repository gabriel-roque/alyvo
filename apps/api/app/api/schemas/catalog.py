from pydantic import Field

from app.api.schemas.common import StrictModel


class CatalogPayload(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    address: str = ""
    preparation: str = ""
    unit_ids: list[str] = Field(default_factory=list)
    active: bool = True


class CatalogView(CatalogPayload):
    id: str


class DoctorPayload(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    crm: str = Field(min_length=2, max_length=40)
    specialty_id: str
    unit_id: str
    insurer_ids: list[str] = Field(default_factory=list)
    active: bool = True


class DoctorView(DoctorPayload):
    id: str
    specialty: str
    unit: str
    insurers: list[str]
