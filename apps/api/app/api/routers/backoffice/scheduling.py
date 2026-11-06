from datetime import date

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import admin_actor, staff_actor
from app.api.schemas.common import Page
from app.api.schemas.scheduling import (
    AppointmentUpdate,
    AppointmentView,
    AvailabilityBlockPayload,
    AvailabilityBlockView,
    AvailabilityRulePayload,
    AvailabilityRuleView,
    DashboardView,
    PatientListView,
    StaffAppointmentCreate,
)
from app.modules.identity.domain import Actor
from app.modules.scheduling.application import SchedulingAdminService, SchedulingService

router = APIRouter()


@router.get("/dashboard", response_model=DashboardView)
def dashboard(_: Actor = Depends(staff_actor)):
    return SchedulingAdminService().dashboard()


@router.get("/patients", response_model=Page[PatientListView])
def patients(q: str = "", _: Actor = Depends(staff_actor)):
    return SchedulingAdminService().patients(q)


@router.get("/appointments", response_model=Page[AppointmentView])
def appointments(
    start: date,
    end: date,
    doctor_id: str | None = None,
    unit_id: str | None = None,
    _: Actor = Depends(staff_actor),
):
    return SchedulingService().agenda(start, end, doctor_id, unit_id)


@router.post("/appointments", response_model=AppointmentView, status_code=201)
def create_appointment(payload: StaffAppointmentCreate, actor: Actor = Depends(staff_actor)):
    return SchedulingAdminService().create_appointment(
        actor, payload.patient_id, payload.doctor_id, payload.starts_at, payload.reason
    )


@router.patch("/appointments/{appointment_id}", response_model=AppointmentView)
def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    actor: Actor = Depends(staff_actor),
):
    return SchedulingAdminService().reschedule_appointment(
        actor,
        appointment_id,
        payload.starts_at,
        payload.reason,
    )


@router.delete("/appointments/{appointment_id}", status_code=204)
def cancel_appointment(appointment_id: str, actor: Actor = Depends(staff_actor)):
    SchedulingAdminService().cancel_appointment(actor, appointment_id)
    return Response(status_code=204)


@router.get("/availability/rules", response_model=Page[AvailabilityRuleView])
def rules(_: Actor = Depends(staff_actor)):
    return SchedulingAdminService().list_rules()


@router.post("/availability/rules", response_model=AvailabilityRuleView, status_code=201)
def create_rule(payload: AvailabilityRulePayload, actor: Actor = Depends(admin_actor)):
    return SchedulingAdminService().create_rule(actor, payload.model_dump())


@router.patch("/availability/rules/{rule_id}", response_model=AvailabilityRuleView)
def update_rule(
    rule_id: str, payload: AvailabilityRulePayload, actor: Actor = Depends(admin_actor)
):
    return SchedulingAdminService().update_rule(actor, rule_id, payload.model_dump())


@router.delete("/availability/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, actor: Actor = Depends(admin_actor)):
    SchedulingAdminService().delete_rule(actor, rule_id)
    return Response(status_code=204)


@router.get("/availability/blocks", response_model=Page[AvailabilityBlockView])
def blocks(_: Actor = Depends(staff_actor)):
    return SchedulingAdminService().list_blocks()


@router.post("/availability/blocks", response_model=AvailabilityBlockView, status_code=201)
def create_block(payload: AvailabilityBlockPayload, actor: Actor = Depends(admin_actor)):
    return SchedulingAdminService().create_block(actor, payload.model_dump())


@router.delete("/availability/blocks/{block_id}", status_code=204)
def delete_block(block_id: str, actor: Actor = Depends(admin_actor)):
    SchedulingAdminService().delete_block(actor, block_id)
    return Response(status_code=204)
