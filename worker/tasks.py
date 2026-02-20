"""Celery tasks for ingestion."""

import asyncio
from typing import Any

from app.core.logging import get_logger
from worker.celery_app import celery_app

logger = get_logger(__name__)


async def _ingest_one(doc: dict[str, Any]):
    """Ingest one document with async session."""
    from app.db.session import async_session_factory
    from app.services.ingestion import IngestionService

    async with async_session_factory() as session:
        svc = IngestionService()
        return await svc.ingest_document(doc, session)


@celery_app.task(bind=True, name="worker.tasks.ingest_documents")
def ingest_documents_task(self, documents: list[dict[str, Any]]):
    """Ingest multiple documents. Runs async ingestion in sync context."""
    results = []
    for i, doc in enumerate(documents):
        try:
            result = asyncio.run(_ingest_one(doc))
            results.append({"index": i, "document_id": result, "status": "ok"})
        except Exception as e:
            logger.error("ingest_document_failed", index=i, error=str(e))
            results.append({"index": i, "error": str(e), "status": "error"})

    return {"processed": len(documents), "results": results}
