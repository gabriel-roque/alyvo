from __future__ import annotations

import hashlib
import json
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import Settings, get_settings
from app.observability import record


@dataclass(frozen=True)
class OcrResult:
    raw_text: str
    fields: dict[str, str]
    confidence: dict[str, float]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelTurn:
    content: str
    tool_calls: list[ToolCall]


class ChatModelProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, context: list[str]) -> str: ...

    def respond(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        return ModelTurn(self.complete(messages[-1]["content"], []), [])


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OcrProvider(ABC):
    @abstractmethod
    def extract(self, content: bytes, filename: str) -> OcrResult: ...


class ObjectStorageProvider(ABC):
    @abstractmethod
    def put_private(self, key: str, content: bytes, content_type: str) -> str: ...

    @abstractmethod
    def get_private(self, key: str) -> bytes: ...

    @abstractmethod
    def presigned_get(self, key: str, expires: int = 900) -> str: ...

    @abstractmethod
    def delete_private(self, key: str) -> None: ...


class DeterministicChatProvider(ChatModelProvider):
    def complete(self, prompt: str, context: list[str]) -> str:
        started = time.perf_counter()
        if not context:
            answer = "Não encontrei evidência suficiente na base aprovada. Entre em contato com a clínica para confirmar."
        else:
            answer = f"Com base nas informações aprovadas da clínica: {context[0]}"
        record("llm.complete", provider="mock", model="deterministic", input_tokens=len(prompt.split()) + sum(len(item.split()) for item in context), output_tokens=len(answer.split()), duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return answer

    def respond(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        user_messages = [item["content"] for item in messages if item.get("role") == "user"]
        message = user_messages[-1].casefold()
        conversation = " ".join(user_messages).casefold()
        if any(term in message for term in ("minhas consultas", "meus agendamentos", "consultas marcadas")):
            return ModelTurn("", [ToolCall("list_my_appointments", {})])
        if any(term in conversation for term in ("agendar", "marcar uma consulta", "horário", "horario", "disponibilidade")):
            return ModelTurn("", [ToolCall("search_availability", {})])
        if any(term in message for term in ("cancelar", "desmarcar")):
            return ModelTurn("", [ToolCall("list_my_appointments", {"status": "confirmed"})])
        return ModelTurn("", [ToolCall("search_knowledge", {"query": messages[-1]["content"]})])


class LangChainChatProvider(ChatModelProvider):
    """LangChain-backed OpenRouter primary with local Ollama failover."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.primary_name = settings.llm_primary_provider
        self.fallback_name = settings.llm_fallback_provider
        self.primary = self._model(self.primary_name)
        self.fallback = self._model(self.fallback_name)

    def _model(self, provider: str):
        if provider == "openrouter":
            if not self.settings.allow_external_providers or not self.settings.openrouter_api_key:
                return None
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.settings.openrouter_model,
                api_key=self.settings.openrouter_api_key,
                base_url=self.settings.openrouter_base_url,
                timeout=self.settings.openrouter_timeout_seconds,
                max_retries=self.settings.openrouter_max_retries,
                temperature=0,
                default_headers={
                    "HTTP-Referer": self.settings.public_web_url,
                    "X-Title": "Alyvo",
                },
            )
        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=self.settings.ollama_model,
                base_url=self.settings.ollama_base_url,
                temperature=0,
                keep_alive=self.settings.ollama_keep_alive,
                num_ctx=self.settings.ollama_context_length,
                client_kwargs={
                    "timeout": httpx.Timeout(
                        connect=self.settings.ollama_connect_timeout_seconds,
                        read=self.settings.ollama_timeout_seconds,
                        write=10,
                        pool=5,
                    )
                },
            )
        return None

    @staticmethod
    def _content(message) -> str:
        value = getattr(message, "content", "")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in value
            )
        return str(value or "")

    def _invoke(self, messages: list[dict], tools: list[dict] | None = None):
        started = time.perf_counter()
        last_error: Exception | None = None
        for provider, model in (
            (self.primary_name, self.primary),
            (self.fallback_name, self.fallback),
        ):
            if model is None:
                continue
            try:
                runnable = model.bind_tools(tools) if tools else model
                response = runnable.invoke(messages)
                record(
                    "llm.complete",
                    provider=provider,
                    model=(
                        self.settings.openrouter_model
                        if provider == "openrouter"
                        else self.settings.ollama_model
                    ),
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
                return response
            except Exception as exc:  # providers expose different transport errors
                last_error = exc
                record(
                    "llm.fallback",
                    failed_provider=provider,
                    fallback_provider=self.fallback_name,
                    reason=type(exc).__name__,
                )
        if last_error:
            raise last_error
        raise RuntimeError("Nenhum provedor de chat está configurado")

    def complete(self, prompt: str, context: list[str]) -> str:
        if not context:
            return DeterministicChatProvider().complete(prompt, context)
        evidence = "\n".join(f"DADO APROVADO: {item}" for item in context)
        messages = [
            {
                "role": "system",
                "content": (
                    "Você é a assistente administrativa Alyvo. Responda em português brasileiro, "
                    "de forma acolhedora e em até três frases. Use somente os dados aprovados. "
                    "Não diagnostique, não prescreva e não invente informações."
                ),
            },
            {"role": "user", "content": f"{evidence}\n\nPERGUNTA: {prompt}"},
        ]
        try:
            return self._content(self._invoke(messages))
        except Exception:
            return DeterministicChatProvider().complete(prompt, context)

    def respond(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        try:
            response = self._invoke(messages, tools)
        except Exception:
            return DeterministicChatProvider().respond(messages, tools)
        calls = []
        for call in getattr(response, "tool_calls", []) or []:
            arguments = call.get("args", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments or "{}")
            calls.append(ToolCall(call.get("name", ""), arguments))
        return ModelTurn(self._content(response), calls)


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Small stable embedding for tests; production adapter remains interchangeable."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.casefold().encode()).digest()
            raw = [(value - 127.5) / 127.5 for value in digest]
            norm = math.sqrt(sum(value * value for value in raw)) or 1
            vectors.append([value / norm for value in raw])
        record("embedding.complete", provider="mock", model="sha256", count=len(texts), dimensions=len(vectors[0]) if vectors else 0, duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return vectors


class BgeM3EmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        import os

        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer("BAAI/bge-m3", device="cpu")
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        missing = [text for text in texts if text not in self._cache]
        if missing:
            encoded = self.model.encode(missing, normalize_embeddings=True).tolist()
            for text, vector in zip(missing, encoded, strict=True):
                if len(self._cache) >= 256:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[text] = vector
        vectors = [self._cache[text] for text in texts]
        record("embedding.complete", provider="local", model="BAAI/bge-m3", count=len(texts), dimensions=len(vectors[0]) if vectors else 0, duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return vectors


class DeterministicOcrProvider(OcrProvider):
    def extract(self, content: bytes, filename: str) -> OcrResult:
        stem = filename.lower()
        if "pedido" in stem:
            fields = {"paciente": "Juliana Silva", "exame": "Hemograma completo", "solicitante": "Dra. Ana Costa"}
        elif "ident" in stem or "rg" in stem:
            fields = {"nome": "Juliana Silva", "cpf": "***.456.789-**", "documento": "RG 12.345.678-9"}
        else:
            fields = {"nome": "Juliana Silva", "convenio": "Vida+", "numero": "VIDA-102938", "validade": "12/2027"}
        return OcrResult(
            raw_text=" | ".join(f"{key}: {value}" for key, value in fields.items()),
            fields=fields,
            confidence={key: 0.96 if index != 2 else 0.84 for index, key in enumerate(fields)},
        )


class PaddleOcrProvider(OcrProvider):
    def __init__(self) -> None:
        # Paddle 2.6 bundles zlib symbols that conflict with pyclipper's import
        # on Debian. Loading pyclipper first avoids the native loader collision.
        import pyclipper  # noqa: F401
        from paddleocr import PaddleOCR

        self.ocr = PaddleOCR(use_angle_cls=True, lang="pt")

    def extract(self, content: bytes, filename: str) -> OcrResult:
        import tempfile
        from io import BytesIO

        suffix = ".pdf" if filename.lower().endswith(".pdf") else ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix) as file:
            file.write(content)
            file.flush()
            result = self.ocr.ocr(file.name, cls=True)

        # A second, grayscale/autocontrast pass makes noisy scans materially
        # more stable. Keep whichever complete pass has the best mean score.
        if suffix != ".pdf":
            import numpy as np
            from PIL import Image, ImageOps

            image = Image.open(BytesIO(content)).convert("RGB")
            enhanced = ImageOps.autocontrast(ImageOps.grayscale(image))
            enhanced_result = self.ocr.ocr(np.asarray(enhanced), cls=True)

            def mean_score(pages) -> float:
                scores = [line[1][1] for page in pages or [] for line in page or []]
                return sum(scores) / len(scores) if scores else 0.0

            if mean_score(enhanced_result) > mean_score(result):
                result = enhanced_result
        lines = [line[1][0] for page in result for line in page]
        confidence = [line[1][1] for page in result for line in page]
        return OcrResult("\n".join(lines), {"texto": "\n".join(lines)}, {"texto": min(confidence or [0.0])})


class LocalObjectStorage(ObjectStorageProvider):
    _objects: dict[str, bytes] = {}

    def put_private(self, key: str, content: bytes, content_type: str) -> str:
        self._objects[key] = content
        return key

    def get_private(self, key: str) -> bytes:
        return self._objects[key]

    def presigned_get(self, key: str, expires: int = 900) -> str:
        return f"private://{key}?expires={expires}"

    def delete_private(self, key: str) -> None:
        self._objects.pop(key, None)


class MinioObjectStorage(ObjectStorageProvider):
    def __init__(self) -> None:
        import boto3

        settings = get_settings()
        scheme = "https" if settings.minio_secure else "http"
        self.bucket = settings.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
        )
        public_scheme = "https" if settings.minio_secure else "http"
        self.public_client = boto3.client(
            "s3",
            endpoint_url=f"{public_scheme}://{settings.minio_public_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
        )
        existing = {item["Name"] for item in self.client.list_buckets().get("Buckets", [])}
        if self.bucket not in existing:
            self.client.create_bucket(Bucket=self.bucket)

    def put_private(self, key: str, content: bytes, content_type: str) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)
        return key

    def get_private(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def presigned_get(self, key: str, expires: int = 900) -> str:
        return self.public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def delete_private(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def chat_provider() -> ChatModelProvider:
    settings = get_settings()
    selected = settings.llm_primary_provider
    if selected == "mock":
        return DeterministicChatProvider()
    return LangChainChatProvider(settings)


@lru_cache
def embedding_provider() -> EmbeddingProvider:
    return BgeM3EmbeddingProvider() if get_settings().embedding_provider == "bge-m3" else DeterministicEmbeddingProvider()


@lru_cache
def ocr_provider() -> OcrProvider:
    return PaddleOcrProvider() if get_settings().ocr_provider == "paddle" else DeterministicOcrProvider()


@lru_cache
def object_storage_provider() -> ObjectStorageProvider:
    settings = get_settings()
    if settings.app_env == "test":
        return LocalObjectStorage()
    return MinioObjectStorage()



