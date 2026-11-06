from fastapi import APIRouter, Depends, Response

from app.api.dependencies import admin_actor, staff_actor
from app.api.schemas.catalog import CatalogPayload, CatalogView, DoctorPayload, DoctorView
from app.api.schemas.common import Page
from app.modules.catalog.application import CatalogService
from app.modules.catalog.domain import CatalogKind
from app.modules.identity.domain import Actor

router = APIRouter()


@router.get("/doctors", response_model=Page[DoctorView])
def doctors(q: str = "", include_inactive: bool = False, _: Actor = Depends(staff_actor)):
    return CatalogService().list_doctors(q, include_inactive)


@router.post("/doctors", response_model=DoctorView, status_code=201)
def create_doctor(payload: DoctorPayload, actor: Actor = Depends(admin_actor)):
    return CatalogService().create_doctor(payload.model_dump(), actor.id)


@router.put("/doctors/{doctor_id}", response_model=DoctorView)
def update_doctor(doctor_id: str, payload: DoctorPayload, actor: Actor = Depends(admin_actor)):
    return CatalogService().update_doctor(doctor_id, payload.model_dump(), actor.id)


@router.delete("/doctors/{doctor_id}", status_code=204)
def delete_doctor(doctor_id: str, actor: Actor = Depends(admin_actor)):
    CatalogService().archive_doctor(doctor_id, actor.id)
    return Response(status_code=204)


def register_catalog_routes(kind: CatalogKind) -> APIRouter:
    child = APIRouter(prefix=f"/{kind.value}")

    @child.get("", response_model=Page[CatalogView], name=f"list_{kind.value}")
    def list_items(
        q: str = "",
        include_inactive: bool = False,
        page: int = 1,
        page_size: int = 50,
        _: Actor = Depends(staff_actor),
    ):
        return CatalogService().list_catalog(kind, q, include_inactive, page, page_size)

    @child.post("", response_model=CatalogView, status_code=201, name=f"create_{kind.value}")
    def create_item(payload: CatalogPayload, actor: Actor = Depends(admin_actor)):
        return CatalogService().create_catalog(kind, payload.model_dump(), actor.id)

    @child.patch("/{item_id}", response_model=CatalogView, name=f"update_{kind.value}")
    def update_item(item_id: str, payload: CatalogPayload, actor: Actor = Depends(admin_actor)):
        return CatalogService().update_catalog(kind, item_id, payload.model_dump(), actor.id)

    @child.delete("/{item_id}", status_code=204, name=f"delete_{kind.value}")
    def delete_item(item_id: str, actor: Actor = Depends(admin_actor)):
        CatalogService().archive_catalog(kind, item_id, actor.id)
        return Response(status_code=204)

    return child


for catalog_kind in CatalogKind:
    router.include_router(register_catalog_routes(catalog_kind))
