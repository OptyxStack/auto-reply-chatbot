"""Admin API routes (ingest, etc.)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pathlib import Path

from app.api.schemas import IngestDocument, IngestRequest, IngestResponse
from app.core.auth import verify_admin_api_key
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingest(
    body: IngestRequest,
    _auth: str = Depends(verify_admin_api_key),
):
    """Trigger ingestion job. Queues documents for processing via Celery."""
    try:
        from worker.tasks import ingest_documents_task

        docs = [
            {
                "url": d.url,
                "title": d.title,
                "raw_text": d.raw_text,
                "raw_html": d.raw_html,
                "content": d.content,
                "doc_type": d.doc_type,
                "effective_date": d.effective_date,
                "last_updated": d.last_updated,
                "product": d.product,
                "region": d.region,
                "metadata": d.metadata,
                "source_file": d.source_file,
            }
            for d in body.documents
        ]
        job = ingest_documents_task.delay(docs)
        return IngestResponse(
            job_id=job.id,
            documents_count=len(docs),
            status="queued",
        )
    except Exception as e:
        logger.error("ingest_trigger_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest-from-source")
async def ingest_from_source(
    _auth: str = Depends(verify_admin_api_key),
    source_dir: str = Query(default="source", description="Path to source directory"),
):
    """Ingest documents from source/ JSON files. Runs synchronously."""
    try:
        from app.services.source_loaders import load_all_docs
        from app.db.session import async_session_factory
        from app.services.ingestion import IngestionService
        import asyncio

        path = Path(source_dir)
        if not path.is_absolute():
            for base in (Path("/app"), Path.cwd()):
                candidate = base / source_dir
                if candidate.exists():
                    path = candidate
                    break
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Source directory not found: {source_dir}")

        docs = load_all_docs(path)
        if not docs:
            return {"status": "ok", "message": "No documents to ingest", "results": {"ok": 0, "skipped": 0, "error": 0}}

        svc = IngestionService()
        results = {"ok": 0, "skipped": 0, "error": 0}
        for i, doc in enumerate(docs):
            try:
                async with async_session_factory() as session:
                    result = await svc.ingest_document(doc, session)
                    if result:
                        results["ok"] += 1
                    else:
                        results["skipped"] += 1
            except Exception as e:
                results["error"] += 1
                logger.warning("ingest_doc_failed", url=doc.get("url", "")[:80], error=str(e))

        return {"status": "ok", "results": results, "total": len(docs)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ingest_from_source_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
