"""Doc type catalog from DB. Used by doc_type_classifier and document forms."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocTypeModel

# In-memory cache: list of (key, label, description) for enabled doc types. Populated from DB on startup/refresh.
_cache: list[tuple[str, str, str | None]] | None = None


def get_valid_doc_type_keys() -> frozenset[str]:
    """Return valid doc type keys for classifier. From DB cache only."""
    global _cache
    if _cache is not None:
        return frozenset(k for k, _, _ in _cache)
    return frozenset()


def get_doc_types_for_prompt() -> list[tuple[str, str]]:
    """Return (key, description) for classifier prompt. From DB cache only."""
    global _cache
    if _cache is not None:
        return [(k, desc or lbl) for k, lbl, desc in _cache]
    return []


async def refresh_doc_type_cache(session: AsyncSession) -> None:
    """Load enabled doc types from DB into cache."""
    global _cache
    result = await session.execute(
        select(DocTypeModel.key, DocTypeModel.label, DocTypeModel.description)
        .where(DocTypeModel.enabled == True)
        .order_by(DocTypeModel.sort_order)
    )
    rows = result.all()
    _cache = [(r.key, r.label, r.description) for r in rows] if rows else []
