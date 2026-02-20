"""Reranker providers: local HTTP service, Cohere, or custom."""

import httpx
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.search.base import RerankerProvider, SearchChunk

logger = get_logger(__name__)


class LocalRerankerProvider(RerankerProvider):
    """Local HTTP reranker service (e.g. sentence-transformers cross-encoder)."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def rerank(
        self, query: str, chunks: list[SearchChunk], top_k: int
    ) -> list[tuple[SearchChunk, float]]:
        """Call local reranker endpoint."""
        if not chunks:
            return []

        url = f"{self._settings.reranker_url.rstrip('/')}/rerank"
        payload = {
            "query": query,
            "documents": [c.chunk_text for c in chunks],
            "top_k": min(top_k, len(chunks)),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("reranker_failed", error=str(e))
            # Fallback: return chunks by original score
            return [(c, c.score) for c in chunks[:top_k]]

        results = data.get("results", [])
        if not results:
            return [(c, c.score) for c in chunks[:top_k]]

        # Map back to original chunks by index
        chunk_map = {i: c for i, c in enumerate(chunks)}
        out: list[tuple[SearchChunk, float]] = []
        for r in results:
            idx = r.get("index", -1)
            score = r.get("relevance_score", 0.0)
            if idx in chunk_map:
                out.append((chunk_map[idx], score))
        return out[:top_k]


class CohereRerankerProvider(RerankerProvider):
    """Cohere Rerank API."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def rerank(
        self, query: str, chunks: list[SearchChunk], top_k: int
    ) -> list[tuple[SearchChunk, float]]:
        """Call Cohere Rerank API."""
        if not chunks or not self._settings.cohere_api_key:
            return [(c, c.score) for c in chunks[:top_k]]

        url = "https://api.cohere.ai/v1/rerank"
        payload = {
            "model": "rerank-multilingual-v3.0",
            "query": query,
            "documents": [c.chunk_text for c in chunks],
            "top_n": min(top_k, len(chunks)),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._settings.cohere_api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("cohere_reranker_failed", error=str(e))
            return [(c, c.score) for c in chunks[:top_k]]

        results = data.get("results", [])
        chunk_map = {i: c for i, c in enumerate(chunks)}
        out: list[tuple[SearchChunk, float]] = []
        for r in results:
            idx = r.get("index", -1)
            score = r.get("relevance_score", 0.0)
            if idx in chunk_map:
                out.append((chunk_map[idx], score))
        return out[:top_k]


class IdentityRerankerProvider(RerankerProvider):
    """No-op reranker: returns chunks sorted by original score."""

    async def rerank(
        self, query: str, chunks: list[SearchChunk], top_k: int
    ) -> list[tuple[SearchChunk, float]]:
        """Sort by score and return top_k."""
        sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)
        return [(c, c.score) for c in sorted_chunks[:top_k]]


def get_reranker_provider() -> RerankerProvider:
    """Factory for reranker based on config."""
    settings = get_settings()
    if settings.reranker_provider == "cohere":
        return CohereRerankerProvider()
    if settings.reranker_provider == "local":
        return LocalRerankerProvider()
    return IdentityRerankerProvider()
