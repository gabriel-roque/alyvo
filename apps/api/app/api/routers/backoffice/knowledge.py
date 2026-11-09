from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import admin_actor, staff_actor
from app.api.schemas.common import Page
from app.api.schemas.knowledge import (
    DocumentView,
    KnowledgeUploadBatch,
    PublishDocument,
    TextDocumentCreate,
)
from app.bootstrap.config import get_settings
from app.infrastructure.providers import object_storage_provider
from app.modules.identity.domain import Actor
from app.modules.knowledge.application import KnowledgeService, KnowledgeUpload
from app.shared.application import ValidationError

router = APIRouter(prefix="/knowledge")


@router.get("/documents", response_model=Page[DocumentView])
def documents(_: Actor = Depends(staff_actor)):
    return KnowledgeService().list_documents()


@router.post("/documents", response_model=DocumentView, status_code=201)
def create_document(payload: TextDocumentCreate, actor: Actor = Depends(admin_actor)):
    return KnowledgeService().create_text(payload.title, payload.content, actor.id)


@router.post("/uploads", response_model=KnowledgeUploadBatch, status_code=202)
async def upload(files: list[UploadFile] = File(...), actor: Actor = Depends(admin_actor)):
    if not files:
        raise ValidationError("Envie ao menos um arquivo")

    settings = get_settings()
    prepared: list[tuple[KnowledgeUpload, bytes]] = []
    for file in files:
        filename = file.filename or "upload"
        content = await file.read(settings.upload_max_bytes + 1)
        if not content:
            raise ValidationError(f"O arquivo {filename} está vazio")
        if len(content) > settings.upload_max_bytes:
            raise ValidationError(f"O arquivo {filename} está acima do limite")
        document_id = uuid4().hex
        prepared.append(
            (
                KnowledgeUpload(
                    id=document_id,
                    title=Path(filename).stem.strip() or filename,
                    filename=filename,
                    content_type=file.content_type or "application/octet-stream",
                    storage_key=f"knowledge/{document_id}/{filename}",
                ),
                content,
            )
        )

    storage = object_storage_provider()
    written_keys: list[str] = []
    try:
        for candidate, content in prepared:
            storage.put_private(candidate.storage_key, content, candidate.content_type)
            written_keys.append(candidate.storage_key)
        items = KnowledgeService().create_uploads(
            [candidate for candidate, _ in prepared], actor.id
        )
    except Exception:
        for key in written_keys:
            storage.delete_private(key)
        raise
    return {"items": items, "total": len(items)}


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
