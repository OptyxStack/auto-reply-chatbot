"""OpenSearch client for BM25 keyword search."""

import asyncio
from typing import Any

from opensearchpy import OpenSearch

from app.core.config import get_settings

try:
    from opensearchpy import AsyncOpenSearch
except ImportError:
    AsyncOpenSearch = None  # Fallback to sync client with asyncio.to_thread
from app.core.logging import get_logger
from app.search.base import SearchChunk

logger = get_logger(__name__)


INDEX_SETTINGS = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "analysis": {
            "analyzer": {
                "default": {
                    "type": "standard",
                },
                "synonym_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "synonym_filter"],
                },
            },
            "filter": {
                "synonym_filter": {
                    "type": "synonym",
                    "synonyms": [
                        "refund, return, money back",
                        "billing, invoice, payment",
                        "cancel, cancellation",
                    ],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "synonym_analyzer"},
            "headings": {"type": "text", "analyzer": "synonym_analyzer"},
            "body": {"type": "text", "analyzer": "synonym_analyzer"},
            "doc_type": {"type": "keyword"},
            "source_url": {"type": "keyword"},
            "effective_date": {"type": "date"},
            "chunk_text": {"type": "text", "analyzer": "synonym_analyzer"},
        },
    },
}


class OpenSearchClient:
    """OpenSearch client for BM25 retrieval."""

    def __init__(self) -> None:
        self._client: Any = None
        self._sync_client: OpenSearch | None = None
        self._settings = get_settings()

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if AsyncOpenSearch is not None:
            self._client = AsyncOpenSearch(
                hosts=[self._settings.opensearch_host],
                http_auth=(
                    (self._settings.opensearch_user, self._settings.opensearch_password)
                    if self._settings.opensearch_user
                    else None
                ),
                use_ssl=self._settings.opensearch_host.startswith("https"),
                verify_certs=True,
            )
            return self._client
        # Fallback: sync client (run in thread)
        if self._sync_client is None:
            self._sync_client = OpenSearch(
                hosts=[self._settings.opensearch_host],
                http_auth=(
                    (self._settings.opensearch_user, self._settings.opensearch_password)
                    if self._settings.opensearch_user
                    else None
                ),
                use_ssl=self._settings.opensearch_host.startswith("https"),
                verify_certs=True,
            )
        return self._sync_client

    def _is_async(self) -> bool:
        return self._client is not None

    async def ensure_index(self) -> None:
        """Create index if not exists."""
        client = await self._get_client()
        if self._is_async():
            exists = await client.indices.exists(index=self._settings.opensearch_index)
            if not exists:
                await client.indices.create(
                    index=self._settings.opensearch_index,
                    body=INDEX_SETTINGS,
                )
                logger.info("opensearch_index_created", index=self._settings.opensearch_index)
        else:
            exists = await asyncio.to_thread(
                client.indices.exists, index=self._settings.opensearch_index
            )
            if not exists:
                await asyncio.to_thread(
                    client.indices.create,
                    index=self._settings.opensearch_index,
                    body=INDEX_SETTINGS,
                )
                logger.info("opensearch_index_created", index=self._settings.opensearch_index)

    async def index_chunk(
        self,
        chunk_id: str,
        document_id: str,
        title: str,
        headings: str,
        body: str,
        doc_type: str,
        source_url: str,
        effective_date: str | None,
        chunk_text: str,
    ) -> None:
        """Index a single chunk."""
        client = await self._get_client()
        doc = {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "title": title,
            "headings": headings,
            "body": body,
            "doc_type": doc_type,
            "source_url": source_url,
            "effective_date": effective_date,
            "chunk_text": chunk_text,
        }
        if self._is_async():
            await client.index(
                index=self._settings.opensearch_index,
                id=chunk_id,
                body=doc,
                refresh=True,
            )
        else:
            await asyncio.to_thread(
                client.index,
                index=self._settings.opensearch_index,
                id=chunk_id,
                body=doc,
                refresh=True,
            )

    async def delete_chunk(self, chunk_id: str) -> None:
        """Delete a chunk by ID."""
        client = await self._get_client()
        try:
            if self._is_async():
                await client.delete(
                    index=self._settings.opensearch_index,
                    id=chunk_id,
                    refresh=True,
                )
            else:
                await asyncio.to_thread(
                    client.delete,
                    index=self._settings.opensearch_index,
                    id=chunk_id,
                    refresh=True,
                )
        except Exception as e:
            logger.warning("opensearch_delete_failed", chunk_id=chunk_id, error=str(e))

    async def search(
        self,
        query: str,
        top_n: int = 50,
        doc_types: list[str] | None = None,
        boost_pricing: bool = False,
    ) -> list[SearchChunk]:
        """BM25 search. Returns top_n chunks. When boost_pricing=True, pricing chunks rank higher."""
        client = await self._get_client()

        must = [
            {"multi_match": {"query": query, "fields": ["title^2", "headings^1.5", "body", "chunk_text"]}}
        ]
        if doc_types:
            must.append({"terms": {"doc_type": doc_types}})

        bool_query: dict[str, Any] = {"must": must}
        if boost_pricing:
            bool_query["should"] = [
                {"term": {"doc_type": {"value": "pricing", "boost": 2.0}}},
            ]
            bool_query["minimum_should_match"] = 0

        body = {
            "size": top_n,
            "query": {"bool": bool_query},
            "_source": ["chunk_id", "document_id", "chunk_text", "source_url", "doc_type"],
        }

        try:
            if self._is_async():
                response = await client.search(
                    index=self._settings.opensearch_index, body=body
                )
            else:
                response = await asyncio.to_thread(
                    client.search,
                    index=self._settings.opensearch_index,
                    body=body,
                )
        except Exception as e:
            logger.error("opensearch_search_failed", query=query, error=str(e))
            return []

        chunks: list[SearchChunk] = []
        for hit in response.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            score = hit.get("_score", 0.0)
            chunks.append(
                SearchChunk(
                    chunk_id=src.get("chunk_id", hit["_id"]),
                    document_id=src.get("document_id", ""),
                    chunk_text=src.get("chunk_text", ""),
                    source_url=src.get("source_url", ""),
                    doc_type=src.get("doc_type", "other"),
                    score=float(score),
                    metadata=src,
                )
            )
        return chunks

    async def close(self) -> None:
        """Close client."""
        if self._client and self._is_async():
            await self._client.close()
        self._client = None
        self._sync_client = None


def get_opensearch_client() -> OpenSearchClient:
    """Factory for dependency injection."""
    return OpenSearchClient()
