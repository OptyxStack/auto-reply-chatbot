"""Admin API routes (ingest, config, intents, crawl)."""

import asyncio
import json
import queue
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AppConfigResponse,
    AppConfigUpdateRequest,
    CheckWhmcsCookiesRequest,
    CheckWhmcsCookiesResponse,
    CrawlTicketsRequest,
    CrawlTicketsResponse,
    IngestDocument,
    IngestRequest,
    IngestResponse,
    IntentCreateRequest,
    IntentResponse,
    IntentUpdateRequest,
    SaveWhmcsCookiesRequest,
    SaveWhmcsCookiesResponse,
    WHMCS_COOKIES_KEY,
)
from app.core.auth import verify_admin_api_key
from app.core.logging import get_logger
from app.db.models import AppConfig, Intent
from app.db.session import get_db
from app.services.branding_config import refresh_cache

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


@router.post("/save-whmcs-cookies", response_model=SaveWhmcsCookiesResponse)
async def save_whmcs_cookies(
    body: SaveWhmcsCookiesRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Save WHMCS session cookies for later crawl. Paste JSON from browser after manual login."""
    import json

    from app.db.models import generate_uuid

    value = json.dumps(body.session_cookies, ensure_ascii=False)
    result = await db.execute(select(AppConfig).where(AppConfig.key == WHMCS_COOKIES_KEY).limit(1))
    row = result.scalars().one_or_none()
    if row:
        row.value = value
    else:
        row = AppConfig(id=generate_uuid(), key=WHMCS_COOKIES_KEY, value=value)
        db.add(row)
    await db.commit()
    return SaveWhmcsCookiesResponse(status="ok", count=len(body.session_cookies))


@router.post("/check-whmcs-cookies", response_model=CheckWhmcsCookiesResponse)
async def api_check_whmcs_cookies(
    body: CheckWhmcsCookiesRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Check if saved or provided cookies authenticate successfully."""
    session_cookies = body.session_cookies
    if not session_cookies or len(session_cookies) == 0:
        result = await db.execute(select(AppConfig).where(AppConfig.key == WHMCS_COOKIES_KEY).limit(1))
        row = result.scalars().one_or_none()
        if row:
            import json

            try:
                session_cookies = json.loads(row.value)
            except Exception:
                session_cookies = None

    if not session_cookies or len(session_cookies) == 0:
        raise HTTPException(
            status_code=400,
            detail="Lưu cookies trước hoặc gửi session_cookies trong body.",
        )

    from app.crawlers.whmcs import check_whmcs_cookies as do_check

    def _run():
        return do_check(
            base_url=body.base_url.rstrip("/"),
            list_path=body.list_path,
            session_cookies=session_cookies,
            headless=True,
            timeout_ms=15000,
            debug=body.debug,
        )

    try:
        ok, message, debug_info = await asyncio.to_thread(_run)
        return CheckWhmcsCookiesResponse(ok=ok, message=message, debug=debug_info)
    except Exception as e:
        logger.error("check_whmcs_cookies_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whmcs-cookies")
async def get_whmcs_cookies(
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Get saved WHMCS cookies (count only, not values)."""
    result = await db.execute(select(AppConfig).where(AppConfig.key == WHMCS_COOKIES_KEY).limit(1))
    row = result.scalars().one_or_none()
    if not row:
        return {"saved": False, "count": 0}
    try:
        import json

        data = json.loads(row.value)
        return {"saved": True, "count": len(data) if isinstance(data, list) else 0}
    except Exception:
        return {"saved": True, "count": 0}


@router.post("/crawl-tickets", response_model=CrawlTicketsResponse)
async def crawl_tickets(
    body: CrawlTicketsRequest,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_admin_api_key),
):
    """Crawl WHMCS tickets. Uses saved cookies (from save-whmcs-cookies) or inline session_cookies/credentials."""
    session_cookies = body.session_cookies
    if not session_cookies or len(session_cookies) == 0:
        # Load from saved config
        result = await db.execute(select(AppConfig).where(AppConfig.key == WHMCS_COOKIES_KEY).limit(1))
        row = result.scalars().one_or_none()
        if row:
            import json

            try:
                session_cookies = json.loads(row.value)
            except Exception:
                session_cookies = None

    has_cookies = session_cookies and len(session_cookies) > 0
    has_creds = body.username and body.password
    if not has_cookies and not has_creds:
        raise HTTPException(
            status_code=400,
            detail="Lưu cookies trước (Save cookies) hoặc cung cấp username+password.",
        )

    from app.crawlers.whmcs import WHMCSConfig, crawl_whmcs_tickets
    from app.services.ticket_db import upsert_ticket_from_crawl

    ticket_queue: queue.Queue = queue.Queue()

    async def _save_worker():
        """Lưu từng ticket vào DB ngay khi crawl xong."""
        saved = 0
        while True:
            try:
                t = await asyncio.to_thread(ticket_queue.get)
                if t is None:
                    break
                ok = await upsert_ticket_from_crawl(t)
                if ok:
                    saved += 1
            except Exception as e:
                logger.warning("crawl_ticket_save_failed", error=str(e))
        return saved

    def _run_crawl():
        config = WHMCSConfig(
            base_url=body.base_url.rstrip("/"),
            list_path=body.list_path,
            login_path=body.login_path,
            username=body.username,
            password=body.password,
            totp_code=body.totp_code,
            session_cookies=session_cookies,
            headless=True,
        )
        return crawl_whmcs_tickets(config, ticket_queue=ticket_queue)

    try:
        save_task = asyncio.create_task(_save_worker())
        tickets, skipped = await asyncio.to_thread(_run_crawl)
        await save_task
    except Exception as e:
        logger.error("crawl_tickets_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    # Save to source/tickets.json
    source_dir = Path.cwd() / "source"
    if not source_dir.exists():
        for base in (Path("/app"), Path.cwd()):
            candidate = base / "source"
            if candidate.exists():
                source_dir = candidate
                break
    source_dir.mkdir(parents=True, exist_ok=True)
    out_path = source_dir / "tickets.json"

    data = {
        "source": "whmcs",
        "crawled_from": body.base_url,
        "tickets": [
            {
                "external_id": t["external_id"],
                "subject": t["subject"],
                "description": t.get("description", ""),
                "status": t.get("status", "Open"),
                "priority": t.get("priority"),
                "client_id": t.get("client_id"),
                "email": t.get("email"),
                "name": t.get("name"),
                "detail_url": t.get("detail_url"),
                "metadata": t.get("metadata"),
            }
            for t in tickets
        ],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return CrawlTicketsResponse(
        status="ok",
        count=len(tickets),
        skipped=skipped,
        saved_to=str(out_path),
        tickets=tickets,
    )


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
