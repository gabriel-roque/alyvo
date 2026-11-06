from datetime import date

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import current_actor
from app.api.schemas.catalog import DoctorView
from app.api.schemas.common import Page
from app.api.schemas.scheduling import AppointmentCreate, AppointmentView, AvailabilityPage
from app.modules.catalog.application import CatalogService
from app.modules.identity.domain import Actor
from app.modules.scheduling.application import SchedulingService

router = APIRouter(tags=["public"])


@router.get("/directory/doctors", response_model=Page[DoctorView])
def doctors(q: str = ""):
    return CatalogService().list_doctors(q)


@router.get("/appointments/availability", response_model=AvailabilityPage)
def availability(
    from_date: date,
    to_date: date | None = None,
    doctor_id: str | None = None,
    specialty_id: str | None = None,
    unit_id: str | None = None,
    insurer_id: str | None = None,
    period: str | None = None,
):
    return SchedulingService().availability(
        from_date, to_date or from_date, doctor_id, specialty_id, unit_id, insurer_id, period
    )


@router.post("/appointments", response_model=AppointmentView, status_code=201)
def create_appointment(payload: AppointmentCreate, actor: Actor = Depends(current_actor)):
    return SchedulingService().create(actor, payload.doctor_id, payload.starts_at, payload.reason)


@router.get("/appointments/me", response_model=Page[AppointmentView])
def my_appointments(actor: Actor = Depends(current_actor)):
    return SchedulingService().list_mine(actor)


@router.delete("/appointments/{appointment_id}", status_code=204)
def cancel_appointment(appointment_id: str, actor: Actor = Depends(current_actor)):
    SchedulingService().cancel(actor, appointment_id)
    return Response(status_code=204)
