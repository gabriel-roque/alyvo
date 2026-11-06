from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorResponse(StrictModel):
    code: str
    message: str
    field_errors: list[dict[str, str]] = Field(default_factory=list)
    correlation_id: str


class Page[T](StrictModel):
    items: list[T]
    total: int
    page: int = 1
    page_size: int


class IdResponse(StrictModel):
    id: str


class LivenessResponse(StrictModel):
    status: str


class ReadinessResponse(StrictModel):
    status: str
    database: str


class MetaResponse(StrictModel):
    name: str
    mode: str
    clinic: str
    timezone: str
    data_policy: str
