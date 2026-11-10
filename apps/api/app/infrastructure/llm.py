from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.agent.presentation import (
    DeterministicResponseComposer,
    LlmResponseComposer,
    ResponseComposer,
)
from app.agent.routing import RouteDecision
from app.bootstrap.config import Settings, get_settings


class LlmRoutingClassifier:
    """Probabilistic last resort behind deterministic routing rules."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def __call__(self, message: str) -> RouteDecision | None:
        model = self._model()
        if model is None:
            return None
        prompt = (
            "Classifique a intenção principal usando apenas o schema solicitado. Use "
            "scheduling/availability para agenda, directory para médicos e catálogos, "
            "knowledge para políticas documentais e fallback/clarify quando houver ambiguidade. "
            "Nunca autorize execução. Use clinical_safety para sintomas ou emergência.\n"
            f"Mensagem: {message}"
        )
        try:
            result = model.with_structured_output(RouteDecision).invoke(prompt)
            return result if isinstance(result, RouteDecision) else None
        except Exception:
            return None

    def _model(self) -> Any | None:
        settings = self.settings
        if _openrouter_available(settings):
            return _openrouter_model(settings, temperature=0)
        if "ollama" in {settings.llm_primary_provider, settings.llm_fallback_provider}:
            return _ollama_model(settings, temperature=0)
        return None


class LangChainAnswerGenerator:
    """Low-temperature response generation with provider fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, system: str, prompt: str) -> str | None:
        for model in self._models():
            try:
                message = model.invoke([("system", system), ("human", prompt)])
                text = _message_text(message.content)
                if text:
                    return text
            except Exception:
                continue
        return None

    def _models(self) -> list[Any]:
        settings = self.settings
        models: list[Any] = []
        if _openrouter_available(settings):
            models.append(_openrouter_model(settings, temperature=0.3))
        if "ollama" in {settings.llm_primary_provider, settings.llm_fallback_provider}:
            models.append(_ollama_model(settings, temperature=0.3))
        return models


def _openrouter_available(settings: Settings) -> bool:
    return bool(
        settings.llm_primary_provider == "openrouter"
        and settings.allow_external_providers
        and settings.openrouter_api_key
    )


def _openrouter_model(settings: Settings, temperature: float) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.openrouter_model,
        timeout=settings.openrouter_timeout_seconds,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.llm_response_max_tokens,
        temperature=temperature,
    )


def _ollama_model(settings: Settings, temperature: float) -> Any:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=temperature,
        keep_alive=settings.ollama_keep_alive,
        num_ctx=settings.ollama_context_length,
        num_predict=settings.llm_response_max_tokens,
    )


@lru_cache
def routing_classifier() -> LlmRoutingClassifier | None:
    settings = get_settings()
    if settings.app_env in {"test", "studio"} or not settings.llm_routing_enabled:
        return None
    return LlmRoutingClassifier(settings)


@lru_cache
def response_composer() -> ResponseComposer:
    settings = get_settings()
    fallback = DeterministicResponseComposer()
    if settings.app_env in {"test", "studio"} or not settings.llm_response_enabled:
        return fallback
    return LlmResponseComposer(
        LangChainAnswerGenerator(settings),
        clinic_name=settings.clinic_name,
        fallback=fallback,
    )


def _message_text(content: object) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None
    parts = [
        item if isinstance(item, str) else item.get("text", "")
        for item in content
        if isinstance(item, (str, dict))
    ]
    text = "".join(part for part in parts if isinstance(part, str)).strip()
    return text or None
