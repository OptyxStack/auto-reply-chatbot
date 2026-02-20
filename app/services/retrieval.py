"""Hybrid retrieval: BM25 + vector + rerank."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.search.base import EvidenceChunk, SearchChunk
from app.search.embeddings import get_embedding_provider
from app.search.opensearch_client import OpenSearchClient
from app.search.qdrant_client import QdrantSearchClient
from app.search.reranker import RerankerProvider, get_reranker_provider

logger = get_logger(__name__)


@dataclass
class EvidencePack:
    """Retrieved evidence for answer generation."""

    chunks: list[EvidenceChunk] = field(default_factory=list)
    retrieval_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryRewrite:
    """Query rewrite for dual retrieval."""

    keyword_query: str
    semantic_query: str


class RetrievalService:
    """Hybrid retrieval with query rewrite, merge, and rerank."""

    def __init__(
        self,
        opensearch: OpenSearchClient | None = None,
        qdrant: QdrantSearchClient | None = None,
        embedding_provider=None,
        reranker: RerankerProvider | None = None,
    ) -> None:
        self._settings = get_settings()
        self._opensearch = opensearch or OpenSearchClient()
        self._qdrant = qdrant or QdrantSearchClient()
        self._embedder = embedding_provider or get_embedding_provider()
        self._reranker = reranker or get_reranker_provider()

    def _query_rewrite(self, query: str) -> QueryRewrite:
        """Rewrite query: expand plans/pricing queries for better retrieval."""
        q = query.lower()
        keyword_query = query
        # Expand "VPS plans" type queries for better BM25 hits on pricing docs
        if any(kw in q for kw in ["plan", "plans", "price", "pricing", "vps", "offer"]):
            extras = []
            if "plan" in q or "plans" in q:
                extras.extend(["pricing", "budget", "windows vps", "kvm vps", "storage"])
            if "price" in q or "cost" in q:
                extras.extend(["USD", "monthly", "annually"])
            if extras:
                keyword_query = f"{query} {' '.join(extras[:4])}"
        return QueryRewrite(keyword_query=keyword_query, semantic_query=query)

    def _merge_and_dedupe(
        self,
        bm25_chunks: list[SearchChunk],
        vector_chunks: list[SearchChunk],
    ) -> list[SearchChunk]:
        """Merge and dedupe by chunk_id. Prefer higher score when duplicate."""
        seen: dict[str, SearchChunk] = {}
        for c in bm25_chunks + vector_chunks:
            if c.chunk_id not in seen or c.score > seen[c.chunk_id].score:
                seen[c.chunk_id] = c
        return list(seen.values())

    async def retrieve(
        self,
        query: str,
        top_n: int | None = None,
        top_k: int | None = None,
        doc_types: list[str] | None = None,
    ) -> EvidencePack:
        """Execute hybrid retrieval pipeline."""
        top_n = top_n or self._settings.retrieval_top_n
        top_k = top_k or self._settings.retrieval_top_k

        qr = self._query_rewrite(query)

        # For plans/pricing queries: fetch more and don't filter by doc_type
        q_lower = query.lower()
        is_plans_query = any(kw in q_lower for kw in ["plan", "plans", "price", "pricing", "vps", "offer"])
        fetch_n = min(top_n * 2, 100) if is_plans_query else top_n

        # 1. BM25 from OpenSearch
        bm25_chunks = await self._opensearch.search(
            query=qr.keyword_query,
            top_n=fetch_n,
            doc_types=doc_types,
        )

        # 2. Vector from Qdrant (sync client - run in thread)
        vectors = await self._embedder.embed([qr.semantic_query])
        vector_chunks = await asyncio.to_thread(
            self._qdrant.search,
            vector=vectors[0],
            top_n=fetch_n,
            doc_types=doc_types,
        )

        # 3. Merge and dedupe
        merged = self._merge_and_dedupe(bm25_chunks, vector_chunks)

        stats = {
            "bm25_count": len(bm25_chunks),
            "vector_count": len(vector_chunks),
            "merged_count": len(merged),
        }

        if not merged:
            try:
                from app.core.metrics import retrieval_requests_total, retrieval_miss_rate
                retrieval_requests_total.inc()
                retrieval_miss_rate.inc()
            except Exception:
                pass
            return EvidencePack(chunks=[], retrieval_stats=stats)

        # 4. Rerank - use more chunks for plans/pricing queries
        extra = self._settings.retrieval_plans_extra_chunks
        rerank_k = min(top_k + extra, len(merged)) if is_plans_query else top_k
        reranked = await self._reranker.rerank(query, merged, rerank_k)

        evidence = [
            EvidenceChunk(
                chunk_id=c.chunk_id,
                snippet=c.chunk_text[:500] + ("..." if len(c.chunk_text) > 500 else ""),
                source_url=c.source_url,
                doc_type=c.doc_type,
                score=score,
                full_text=c.chunk_text,
            )
            for c, score in reranked
        ]

        stats["reranked_count"] = len(evidence)
        try:
            from app.core.metrics import (
                retrieval_requests_total,
                retrieval_chunks_returned,
                retrieval_hit_rate,
            )
            retrieval_requests_total.inc()
            retrieval_chunks_returned.observe(len(evidence))
            retrieval_hit_rate.inc()
        except Exception:
            pass
        return EvidencePack(chunks=evidence, retrieval_stats=stats)
