from pydantic import Field

from app.api.schemas.common import StrictModel


class TextDocumentCreate(StrictModel):
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=2)


class KnowledgeEntity(StrictModel):
    type: str
    name: str
    id: str | None = None


class PublishDocument(StrictModel):
    entities: list[KnowledgeEntity] = Field(default_factory=list)
    confirmed: bool = True


class DocumentView(StrictModel):
    id: str
    title: str
    status: str
    source: str
    entities: list[KnowledgeEntity]
    preview: str
    filename: str
    error: str
    sync_status: str


class KnowledgeUploadBatch(StrictModel):
    items: list[DocumentView]
    total: int
