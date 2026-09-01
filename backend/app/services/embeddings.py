"""OpenAI-compatible 임베딩 API 경계와 검색용 유사도 함수."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import settings


class EmbeddingError(Exception):
    """임베딩 공급자 호출 실패."""


async def embed(texts: list[str]) -> list[list[float]]:
    if not settings.embedding_configured:
        raise EmbeddingError("embedding_not_configured")
    if settings.embedding_provider == "local":
        try:
            return await _local_embed(texts)
        except EmbeddingError:
            raise
        except Exception as error:
            raise EmbeddingError(f"local_embedding_failed:{type(error).__name__}") from error
    try:
        async with httpx.AsyncClient(timeout=settings.embedding_timeout_seconds) as client:
            response = await client.post(
                settings.embedding_api_url,
                headers={
                    "Authorization": f"Bearer {settings.embedding_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.embedding_model, "input": texts},
            )
    except httpx.HTTPError as error:
        raise EmbeddingError(f"embedding_request_failed:{type(error).__name__}") from error
    if response.status_code >= 400:
        raise EmbeddingError(f"embedding_provider_error:{response.status_code}")
    try:
        data: Any = response.json().get("data")
        vectors = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise EmbeddingError("embedding_response_invalid") from error
    if len(vectors) != len(texts) or not all(isinstance(vector, list) for vector in vectors):
        raise EmbeddingError("embedding_count_mismatch")
    return vectors


@lru_cache(maxsize=1)
def _local_model():
    """SentenceTransformers 모델은 첫 호출 때만 로드한다."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise EmbeddingError("local_embedding_dependency_missing:sentence-transformers") from error
    return SentenceTransformer(settings.embedding_local_model)


async def _local_embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _local_model()
    vectors = await __import__("asyncio").to_thread(
        model.encode,
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    result = vectors.tolist()
    if not isinstance(result, list) or len(result) != len(texts):
        raise EmbeddingError("local_embedding_count_mismatch")
    return result


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator
