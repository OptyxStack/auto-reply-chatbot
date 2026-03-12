#!/usr/bin/env python3
"""
Re-ingest all documents from the database with enriched metadata (page_kind, product_family).

Use after updating the ingestion pipeline to add page_kind/product_family to existing chunks.
Run from project root: python scripts/reingest_all.py

Requires: PostgreSQL, OpenSearch, Qdrant running.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main() -> int:
    from sqlalchemy import select
    from app.db.models import Document
    from app.db.session import async_session_factory
    from app.services.ingestion import IngestionService

    async with async_session_factory() as session:
        result = await session.execute(select(Document))
        docs = result.scalars().all()

    if not docs:
        print("No documents in database.")
        return 0

    print(f"Re-ingesting {len(docs)} documents with force_reindex=True (page_kind/product_family)...")

    svc = IngestionService()
    ok = 0
    err = 0
    skipped = 0

    for i, doc in enumerate(docs):
        raw = doc.raw_content or doc.cleaned_content or ""
        if not raw or len(raw) < 50:
            skipped += 1
            continue
        doc_dict = {
            "url": doc.source_url,
            "title": doc.title,
            "raw_text": raw,
            "doc_type": doc.doc_type,
            "metadata": doc.doc_metadata or {},
            "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
        }
        try:
            async with async_session_factory() as session:
                result = await svc.ingest_document(doc_dict, session, force_reindex=True)
                if result:
                    ok += 1
        except Exception as e:
            err += 1
            print(f"  Error doc {i} ({doc.source_url[:50]}...): {e}")

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i + 1}/{len(docs)}")

    print(f"Done: {ok} re-indexed, {skipped} skipped (no content), {err} errors")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
