"""Provider composition boundary.

The implementation remains isolated in the legacy adapter module while callers
depend on this infrastructure-facing path.
"""

from app.ai.providers import (
    ChatModelProvider,
    EmbeddingProvider,
    ModelTurn,
    ObjectStorageProvider,
    OcrProvider,
    ToolCall,
    chat_provider,
    embedding_provider,
    object_storage_provider,
    ocr_provider,
)

__all__ = [
    "ChatModelProvider",
    "EmbeddingProvider",
    "ModelTurn",
    "ObjectStorageProvider",
    "OcrProvider",
    "ToolCall",
    "chat_provider",
    "embedding_provider",
    "object_storage_provider",
    "ocr_provider",
]
