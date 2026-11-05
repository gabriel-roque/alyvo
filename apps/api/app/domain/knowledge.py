from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeIndexDescriptor:
    version: str
    parser_version: str
    embedding_model: str
