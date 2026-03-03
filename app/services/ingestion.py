"""Ingestion pipeline: clean, chunk, embed, index."""

import asyncio
import hashlib
import re
from datetime import datetime
from html import unescape
from typing import Any

from bs4 import BeautifulSoup
import tiktoken

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Document, Chunk
from app.search.embeddings import get_embedding_provider
from app.search.opensearch_client import OpenSearchClient
from app.search.qdrant_client import QdrantSearchClient

logger = get_logger(__name__)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _clean_html(html: str, base_url: str | None = None) -> str:
    """Strip boilerplate and extract text from HTML. Preserves links as text when base_url given."""
    from urllib.parse import urljoin, urlparse

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    if base_url:
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            try:
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                if parsed.scheme in ("http", "https"):
                    link_text = a.get_text(strip=True) or full_url
                    a.replace_with(f"{link_text} ({full_url})")
            except Exception:
                pass

    text = soup.get_text(separator="\n")
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def _extract_headings(soup: BeautifulSoup) -> str:
    """Extract heading hierarchy as string."""
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        headings.append(tag.get_text(strip=True))
    return " | ".join(headings)


def _chunk_by_semantic_boundaries(
    text: str,
    min_tokens: int = 300,
    max_tokens: int = 700,
) -> list[tuple[str, str]]:
    """Chunk text by headings/paragraphs. Returns list of (chunk_text, headings)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        enc = tiktoken.get_encoding("gpt2")

    def count_tokens(s: str) -> int:
        return len(enc.encode(s))

    # Split by double newlines and headings
    blocks = re.split(r"\n(?=#{1,6}\s|\n\n)", text)
    blocks = [b.strip() for b in blocks if b.strip()]

    chunks: list[tuple[str, str]] = []
    current = []
    current_headings = ""
    current_tokens = 0

    for block in blocks:
        block_tokens = count_tokens(block)
        # Check if block is a heading
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", block)
        if heading_match:
            level, title = heading_match.groups()
            current_headings = title
            if current and current_tokens >= min_tokens:
                chunk_text = "\n\n".join(current)
                chunks.append((chunk_text, prev_headings))
                current = [block]
                prev_headings = current_headings
                current_tokens = block_tokens
            else:
                current.append(block)
                prev_headings = current_headings
                current_tokens += block_tokens
        else:
            if current_tokens + block_tokens > max_tokens and current and current_tokens >= min_tokens:
                chunk_text = "\n\n".join(current)
                chunks.append((chunk_text, current_headings))
                current = [block]
                current_tokens = block_tokens
            else:
                current.append(block)
                current_tokens += block_tokens

    if current:
        chunk_text = "\n\n".join(current)
        chunks.append((chunk_text, current_headings))

    return chunks


def prepare_document(doc: dict[str, Any]) -> tuple[str, str, list[tuple[str, str]]]:
    """Clean and chunk a document. Returns (cleaned_content, raw_content, chunks)."""
    raw = doc.get("raw_text") or doc.get("raw_html") or doc.get("content", "")
    base_url = doc.get("url") or doc.get("source_url")
    if doc.get("raw_html") or "<" in raw[:100]:
        cleaned = _clean_html(raw, base_url=base_url)
    else:
        cleaned = raw

    settings = get_settings()
    chunks = _chunk_by_semantic_boundaries(
        cleaned,
        min_tokens=settings.chunk_min_tokens,
        max_tokens=settings.chunk_max_tokens,
    )
    return cleaned, raw, chunks


class IngestionService:
    """Orchestrates document ingestion: clean, chunk, store, embed, index."""

    def __init__(
        self,
        opensearch: OpenSearchClient | None = None,
        qdrant: QdrantSearchClient | None = None,
        embedder=None,
    ) -> None:
        self._settings = get_settings()
        self._opensearch = opensearch or OpenSearchClient()
        self._qdrant = qdrant or QdrantSearchClient()
        self._embedder = embedder or get_embedding_provider()

    async def ingest_document(self, doc: dict[str, Any], db_session) -> str | None:
        """Ingest a single document. Returns document_id or None if skipped (idempotent)."""
        url = doc.get("url") or doc.get("source_url")
        if not url:
            logger.warning("ingest_skipped_no_url")
            return None

        title = doc.get("title", "Untitled")
        doc_type = doc.get("doc_type", "other")
        effective_date = doc.get("effective_date") or doc.get("last_updated")
        metadata = doc.get("metadata")
        source_file = doc.get("source_file")
        if isinstance(effective_date, str):
            try:
                effective_date = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
            except ValueError:
                effective_date = None

        cleaned, raw, chunk_tuples = prepare_document(doc)
        checksum = _checksum(cleaned)

        # Optional: store raw doc in object storage
        if raw:
            try:
                from app.core.storage import get_storage
                storage = get_storage()
                if storage._get_client():
                    key = f"raw/{_checksum(url)}.txt"
                    body = raw.encode("utf-8") if isinstance(raw, str) else raw
                    storage.put(key, body, "text/plain")
            except Exception:
                pass

        # Idempotency: check existing by source_url
        from sqlalchemy import select
        from app.db.models import Document as DocModel

        result = await db_session.execute(select(DocModel).where(DocModel.source_url == url))
        existing = result.scalars().first()
        if existing and existing.checksum == checksum:
            logger.info("ingest_skipped_unchanged", source_url=url)
            # Content unchanged: skip re-chunk/re-embed but still update doc_type, title (e.g. from classifier)
            existing.title = title
            existing.doc_type = doc_type
            existing.effective_date = effective_date
            existing.doc_metadata = metadata
            existing.source_file = source_file
            existing.updated_at = datetime.utcnow()
            await db_session.flush()
            return existing.id

        # Create or update document
        if existing:
            document_id = existing.id
            # Fetch old chunk IDs before delete (for search index cleanup)
            from sqlalchemy import delete, select
            from app.db.models import Chunk as ChunkModel
            old_chunks_result = await db_session.execute(select(ChunkModel.id).where(ChunkModel.document_id == document_id))
            old_chunk_ids = list(old_chunks_result.scalars().all())
            for cid in old_chunk_ids:
                await self._opensearch.delete_chunk(cid)
                self._qdrant.delete_chunk(cid)
            existing.title = title
            existing.doc_type = doc_type
            existing.effective_date = effective_date
            existing.checksum = checksum
            existing.raw_content = raw
            existing.cleaned_content = cleaned
            existing.doc_metadata = metadata
            existing.source_file = source_file
            existing.updated_at = datetime.utcnow()
            await db_session.execute(delete(ChunkModel).where(ChunkModel.document_id == document_id))
        else:
            new_doc = Document(
                title=title,
                source_url=url,
                doc_type=doc_type,
                effective_date=effective_date,
                checksum=checksum,
                raw_content=raw,
                cleaned_content=cleaned,
                doc_metadata=metadata,
                source_file=source_file,
            )
            db_session.add(new_doc)
            await db_session.flush()
            document_id = new_doc.id

        # Ensure search indices exist
        await self._opensearch.ensure_index()
        self._qdrant.ensure_collection(self._embedder.dimensions())

        # Create chunks and index
        for idx, (chunk_text, headings) in enumerate(chunk_tuples):
            token_count = len(tiktoken.get_encoding("cl100k_base").encode(chunk_text))
            chunk_checksum = _checksum(chunk_text)

            chunk_meta = {"headings": headings, "doc_type": doc_type}
            if metadata:
                chunk_meta.update({k: v for k, v in metadata.items() if k in ("product", "category", "key_points") and v is not None})
            chunk = Chunk(
                document_id=document_id,
                chunk_index=idx,
                chunk_text=chunk_text,
                token_count=token_count,
                chunk_metadata=chunk_meta,
                checksum=chunk_checksum,
            )
            db_session.add(chunk)
            await db_session.flush()

            # Embed and index
            vectors = await self._embedder.embed([chunk_text])
            qdrant_meta = {"headings": headings}
            if metadata:
                qdrant_meta.update({k: v for k, v in metadata.items() if k in ("product", "category") and v is not None})
            self._qdrant.upsert_chunk(
                chunk_id=chunk.id,
                vector=vectors[0],
                chunk_text=chunk_text,
                document_id=document_id,
                source_url=url,
                doc_type=doc_type,
                metadata=qdrant_meta,
            )
            await self._opensearch.index_chunk(
                chunk_id=chunk.id,
                document_id=document_id,
                title=title,
                headings=headings,
                body=chunk_text,
                doc_type=doc_type,
                source_url=url,
                effective_date=effective_date.isoformat() if effective_date else None,
                chunk_text=chunk_text,
            )

        await db_session.commit()
        logger.info("ingest_complete", document_id=document_id, chunks=len(chunk_tuples))
        return document_id
