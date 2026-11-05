from __future__ import annotations

from functools import lru_cache

from app.config import get_settings


class LocalReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, device="cpu")

    def rank(self, question: str, contents: list[str]) -> list[tuple[int, float]]:
        if not contents:
            return []
        scores = self.model.predict([(question, content) for content in contents])
        return sorted(
            ((index, float(score)) for index, score in enumerate(scores)),
            key=lambda item: item[1],
            reverse=True,
        )


@lru_cache
def local_reranker() -> LocalReranker:
    return LocalReranker(get_settings().reranker_model)
