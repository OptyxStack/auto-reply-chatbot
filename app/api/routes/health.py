"""Health and metrics endpoints."""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import REGISTRY, generate_latest

from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    checks = {}
    try:
        from sqlalchemy import text
        from app.db.session import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    try:
        import redis.asyncio as redis
        from app.core.config import get_settings
        r = redis.from_url(get_settings().redis_url)
        await r.ping()
        await r.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:50]}"

    status = "healthy" if all("ok" in v for v in checks.values()) else "degraded"
    return HealthResponse(
        status=status,
        version="1.0.0",
        checks=checks,
    )


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
