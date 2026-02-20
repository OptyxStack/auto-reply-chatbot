"""API key authentication middleware."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
admin_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> str:
    """Verify standard API key. Returns 'authenticated' on success."""
    settings = get_settings()
    if not settings.api_key:
        # No key configured - allow in dev
        return "dev"
    if api_key and api_key == settings.api_key:
        return "authenticated"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
    )


async def verify_admin_api_key(
    request: Request,
    admin_key: Annotated[str | None, Depends(admin_api_key_header)],
) -> str:
    """Verify admin API key for ingest/admin endpoints."""
    settings = get_settings()
    if not settings.admin_api_key:
        return "admin_dev"
    if admin_key and admin_key == settings.admin_api_key:
        return "admin"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing admin API key",
    )
