from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

GLUED_HEADING_REPLACEMENTS = {
    "PolíticadeproteçãodedadospessoaiseLGPD": "Política de proteção de dados pessoais e LGPD",
    "Objetivoealcance": "Objetivo e alcance",
    "Dadostratados": "Dados tratados",
    "Finalidadesebaseslegais": "Finalidades e bases legais",
    "Princípiosdetratamento": "Princípios de tratamento",
    "Compartilhamentodedados": "Compartilhamento de dados",
    "Segurançaeconfidencialidade": "Segurança e confidencialidade",
    "Armazenamentoeeliminação": "Armazenamento e eliminação",
    "Direitosdotitular": "Direitos do titular",
    "Atualizaçãodapolítica": "Atualização da política",
    "Etapasdoprocessamento": "Etapas do processamento",
    "Prazosdereferência": "Prazos de referência",
    "Fatoresquepodemalteraroprazo": "Fatores que podem alterar o prazo",
    "Liberaçãoeacessoaosresultados": "Liberação e acesso aos resultados",
    "Quandoentraremcontato": "Quando entrar em contato",
}


@dataclass(frozen=True)
class StructuralChunk:
    content: str
    content_hash: str
    section: str
    page: int | None
    parent_id: str


def normalize_extracted_text(text: str) -> str:
    """Normalize parser/OCR artifacts without inventing document content."""

    value = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    for glued, readable in GLUED_HEADING_REPLACEMENTS.items():
        value = re.sub(re.escape(glued), f"{readable}\n", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<=[a-zà-ÿ])(?=[A-Z]{2,}\b)", " ", value)
    value = value.replace("•", "\n• ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _windows(words: list[str], size: int, overlap: int) -> list[list[str]]:
    if not words:
        return []
    step = max(size - overlap, 1)
    return [words[start : start + size] for start in range(0, len(words), step)]


def _sections(page: str) -> list[tuple[str, str]]:
    current_title = "Documento"
    current: list[str] = []
    result: list[tuple[str, str]] = []
    for raw_line in page.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            if current and current[-1] != "":
                current.append("")
            continue
        markdown_heading = line.startswith("#")
        short_heading = len(line) <= 100 and line.rstrip(":").isupper()
        if markdown_heading or short_heading:
            if any(current):
                result.append((current_title, "\n".join(current).strip()))
            current_title = line.lstrip("# ").rstrip(":") or "Documento"
            current = []
        else:
            current.append(line)
    if any(current):
        result.append((current_title, "\n".join(current).strip()))
    return result or [("Documento", " ".join(page.split()))]


def structural_chunks(
    text: str,
    *,
    child_tokens: int = 300,
    parent_tokens: int = 1000,
    overlap_tokens: int = 50,
) -> list[StructuralChunk]:
    """Create parent-aware chunks while retaining headings, pages and table rows."""

    text = normalize_extracted_text(text)
    chunks: list[StructuralChunk] = []
    pages = text.split("\f")
    for page_number, page in enumerate(pages, start=1):
        for section, body in _sections(page):
            words = re.findall(r"\S+", body)
            for parent_words in _windows(words, parent_tokens, overlap_tokens):
                parent_text = " ".join(parent_words)
                parent_id = hashlib.sha256(
                    f"{page_number}:{section}:{parent_text}".encode()
                ).hexdigest()[:32]
                for child_words in _windows(
                    parent_words,
                    child_tokens,
                    overlap_tokens,
                ):
                    content = " ".join(child_words).strip()
                    if not content:
                        continue
                    chunks.append(
                        StructuralChunk(
                            content=content,
                            content_hash=hashlib.sha256(content.encode()).hexdigest(),
                            section=section,
                            page=page_number,
                            parent_id=parent_id,
                        )
                    )
    return chunks
