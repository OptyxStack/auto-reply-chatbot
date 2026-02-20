"""Abstract interfaces for search components."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SearchChunk:
    """Unified chunk representation from search backends."""

    chunk_id: str
    document_id: str
    chunk_text: str
    source_url: str
    doc_type: str
    score: float
    metadata: dict[str, Any] | None = None


@dataclass
class EvidenceChunk:
    """Evidence chunk with citation info for answer generation."""

    chunk_id: str
    snippet: str
    source_url: str
    doc_type: str
    score: float
    full_text: str | None = None


class EmbeddingProvider(ABC):
    """Abstract embedding provider interface."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts and return vectors."""
        pass

    @abstractmethod
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        pass


class RerankerProvider(ABC):
    """Abstract reranker interface."""

    @abstractmethod
    async def rerank(
        self, query: str, chunks: list[SearchChunk], top_k: int
    ) -> list[tuple[SearchChunk, float]]:
        """Rerank chunks by relevance to query. Returns top_k (chunk, score) pairs."""
        pass
