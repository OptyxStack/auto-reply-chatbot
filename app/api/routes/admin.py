"""Admin API routes (ingest, config, intents)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pathlib import Path
from sqlalchemy import select

from app.api.schemas import (
    AppConfigResponse,
    AppConfigUpdateRequest,
    IngestDocument,
    IngestRequest,
    IngestResponse,
    IntentCreateRequest,
    IntentResponse,
    IntentUpdateRequest,
)
from app.core.auth import verify_admin_api_key
from app.core.logging import get_logger
from app.db.models import AppConfig, Intent
from app.db.session import get_db
from app.services.branding_config import refresh_cache
from sqlalchemy.ext.asyncio import AsyncSession

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


# --- Branding config (prompts, intents) ---


@router.post("/config/refresh-cache")
async def refresh_config_cache(
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Refresh in-memory cache for system prompt and intents from DB."""
    await refresh_cache(db)
    return {"status": "ok", "message": "Cache refreshed"}


@router.get("/config/{key}", response_model=AppConfigResponse)
async def get_config(
    key: str,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Get config value by key (e.g. system_prompt)."""
    result = await db.execute(select(AppConfig).where(AppConfig.key == key).limit(1))
    row = result.scalars().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Config key not found: {key}")
    return AppConfigResponse(key=row.key, value=row.value)


@router.put("/config/{key}", response_model=AppConfigResponse)
async def update_config(
    key: str,
    body: AppConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Update config value. Creates if key does not exist."""
    result = await db.execute(select(AppConfig).where(AppConfig.key == key).limit(1))
    row = result.scalars().one_or_none()
    if row:
        row.value = body.value
    else:
        from app.db.models import generate_uuid
        row = AppConfig(id=generate_uuid(), key=key, value=body.value)
        db.add(row)
    await db.flush()
    await refresh_cache(db)
    return AppConfigResponse(key=row.key, value=row.value)


@router.get("/intents", response_model=list[IntentResponse])
async def list_intents(
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """List all intents ordered by sort_order."""
    result = await db.execute(select(Intent).order_by(Intent.sort_order))
    rows = result.scalars().all()
    return [
        IntentResponse(id=r.id, key=r.key, patterns=r.patterns, answer=r.answer, enabled=r.enabled, sort_order=r.sort_order)
        for r in rows
    ]


@router.post("/intents", response_model=IntentResponse)
async def create_intent(
    body: IntentCreateRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Create a new intent."""
    result = await db.execute(select(Intent).where(Intent.key == body.key).limit(1))
    if result.scalars().one_or_none():
        raise HTTPException(status_code=409, detail=f"Intent key already exists: {body.key}")
    from app.db.models import generate_uuid
    intent = Intent(
        id=generate_uuid(),
        key=body.key,
        patterns=body.patterns,
        answer=body.answer,
        enabled=body.enabled,
        sort_order=body.sort_order,
    )
    db.add(intent)
    await db.flush()
    await refresh_cache(db)
    return IntentResponse(id=intent.id, key=intent.key, patterns=intent.patterns, answer=intent.answer, enabled=intent.enabled, sort_order=intent.sort_order)


@router.put("/intents/{intent_id}", response_model=IntentResponse)
async def update_intent(
    intent_id: str,
    body: IntentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Update intent by id."""
    result = await db.execute(select(Intent).where(Intent.id == intent_id).limit(1))
    intent = result.scalars().one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    if body.patterns is not None:
        intent.patterns = body.patterns
    if body.answer is not None:
        intent.answer = body.answer
    if body.enabled is not None:
        intent.enabled = body.enabled
    if body.sort_order is not None:
        intent.sort_order = body.sort_order
    await db.flush()
    await refresh_cache(db)
    return IntentResponse(id=intent.id, key=intent.key, patterns=intent.patterns, answer=intent.answer, enabled=intent.enabled, sort_order=intent.sort_order)


@router.delete("/intents/{intent_id}")
async def delete_intent(
    intent_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Delete intent by id."""
    result = await db.execute(select(Intent).where(Intent.id == intent_id).limit(1))
    intent = result.scalars().one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    await db.delete(intent)
    await db.flush()
    await refresh_cache(db)
    return {"status": "ok", "message": "Intent deleted"}
