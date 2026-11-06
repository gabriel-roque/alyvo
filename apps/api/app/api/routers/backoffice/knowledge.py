from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import admin_actor, staff_actor
from app.api.schemas.common import Page
from app.api.schemas.knowledge import DocumentView, PublishDocument, TextDocumentCreate
from app.bootstrap.config import get_settings
from app.infrastructure.providers import object_storage_provider
from app.modules.identity.domain import Actor
from app.modules.knowledge.application import KnowledgeService

router = APIRouter(prefix="/knowledge")


@router.get("/documents", response_model=Page[DocumentView])
def documents(_: Actor = Depends(staff_actor)):
    return KnowledgeService().list_documents()


@router.post("/documents", response_model=DocumentView, status_code=201)
def create_document(payload: TextDocumentCreate, actor: Actor = Depends(admin_actor)):
    return KnowledgeService().create_text(payload.title, payload.content, actor.id)


@router.post("/uploads", response_model=DocumentView, status_code=202)
async def upload(
    title: str = Form(...), file: UploadFile = File(...), actor: Actor = Depends(admin_actor)
):
    content = await file.read(get_settings().upload_max_bytes + 1)
    if not content or len(content) > get_settings().upload_max_bytes:
        from app.shared.application import ValidationError

        raise ValidationError("Arquivo vazio ou acima do limite")
    document_id = __import__("uuid").uuid4().hex
    storage_key = f"knowledge/{document_id}/{file.filename or 'upload'}"
    object_storage_provider().put_private(
        storage_key, content, file.content_type or "application/octet-stream"
    )
    return KnowledgeService().create_upload(
        title,
        file.filename or "upload",
        file.content_type or "application/octet-stream",
        storage_key,
        actor.id,
    )


@router.post("/documents/{document_id}/publish", response_model=DocumentView)
def publish(document_id: str, payload: PublishDocument, actor: Actor = Depends(admin_actor)):
    return KnowledgeService().publish(
        document_id,
        [entity.model_dump() for entity in payload.entities],
        actor.id,
    )


@router.post("/documents/{document_id}/reject", response_model=DocumentView)
def reject(document_id: str, actor: Actor = Depends(admin_actor)):
    return KnowledgeService().reject(document_id, actor.id)
