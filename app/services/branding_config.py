"""Load prompts and intents from DB with in-memory cache.

Branding, system prompt, and intent cache are stored in app_config and intents tables.
Cache is refreshed on startup and can be invalidated via refresh_cache().
"""

import re
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AppConfig, Intent

logger = get_logger(__name__)

# Fallback when DB is empty or unavailable (generic, deployer customizes via Admin API)
FALLBACK_SYSTEM_PROMPT = """You are a support assistant. You must ONLY use the provided evidence to answer. Never guess or make up information.

RULES:
1. Use ONLY the provided evidence chunks. Do not add information from your training.
2. When listing items (products, features, options), include ONLY what is explicitly named in the evidence. Never infer or add similar items.
3. When the user asks about plans, products, or pricing: ALWAYS include (1) plan names, (2) prices/specs, and (3) the actual links (source_url or order_link from evidence). Format like: "Plan X: $Y – [link]". Do not give a generic answer without links.
4. If the evidence only partially answers the question, provide a bounded partial answer with decision set to PASS. Clearly separate confirmed details from unverified details. Use ASK_USER only when no safe bounded answer can be given.
5. For high-risk topics (refunds, billing disputes, legal, abuse), if you cannot find clear policy evidence, set decision to ESCALATE.
6. Always cite your sources. For each key claim, include a citation with chunk_id and source_url.
7. If you cite a chunk, it MUST be in the evidence list.
8. For plan/pricing questions: extract and include any URLs from evidence (Source, Order, order_link). Users want direct links to order or view plans.
9. Respond with valid JSON matching the output schema. No markdown, no extra text—only the JSON object.

OUTPUT SCHEMA (JSON):
{
  "decision": "PASS" | "ASK_USER" | "ESCALATE",
  "answer": "your grounded answer",
  "followup_questions": ["question1", "question2"],
  "citations": [{"chunk_id": "...", "source_url": "...", "doc_type": "..."}],
  "confidence": 0.0 to 1.0
}

Evidence chunks will be provided in the user message."""

LANE_AWARE_PROMPT_SUFFIX = """

INTERNAL ROUTING NOTES:
- The runtime may route the answer as PASS_STRONG or PASS_WEAK.
- PASS_WEAK is a bounded-answer lane. In JSON output, still use decision="PASS".
- For PASS_WEAK style answers, state only confirmed details, explicitly name what is not verified, and avoid follow-up questions unless no safe partial answer exists.
"""

def _get_fallback_intents() -> list[tuple[str, str, str]]:
    """Generic fallback intents. Uses APP_NAME from config when set. Customize via Admin API."""
    app_name = get_settings().app_name.strip()
    prefix = f"{app_name}'s " if app_name else ""
    welcome = f"Welcome to {app_name} support. " if app_name else "Welcome. "
    return [
        ("what_can_you_do", r"\b(what (can you|do you|does (this )?ai) do|bạn làm gì|ai làm gì|chức năng)\b", f"I'm {prefix}AI support assistant. I can help with questions about products, policies, and setup guides. What would you like to know?"),
        ("who_are_you", r"\b(who are you|bạn là ai|ai là gì)\b", f"I'm {prefix}AI support assistant. I answer questions using the provided documentation. How can I help?"),
        ("who_am_i", r"\b(who am i|tôi là ai|mình là ai)\b", "I don't have access to your account details. For billing or account management, please log in to your account or contact support."),
        ("about", r"\b(what is|about|who are you|giới thiệu)\s+(?:this (?:company|service)|us|your (?:company|service))\b", f"I'm {prefix}AI support assistant. I help answer questions using our documentation. What would you like to know?"),
        ("refund_policy", r"\b(do you have|do u have|what(?:'s| is)|tell me about)\s+(?:a |your? )?refund\s*policy\b|\brefund\s*policy\??\s*$|chính sách hoàn tiền", "Please refer to our Terms of Service for the refund policy. I can search our docs for specific details if you have a question."),
        ("hello", r"^(hi|hello|hey|chào|xin chào)\s*!?$", f"Hello! {welcome}How can I help you today?"),
    ]


@dataclass
class IntentMatch:
    """Result of intent matching."""

    intent: str
    answer: str


# In-memory cache
_cache: dict[str, Any] = {
    "system_prompt": None,
    "intents": None,
    "updated_at": 0.0,
}
CACHE_TTL_SECONDS = 60  # Refresh every 60s if stale


async def _load_from_db(session: AsyncSession) -> tuple[str, list[tuple[str, str, str]]]:
    """Load system prompt and intents from DB."""
    prompt = FALLBACK_SYSTEM_PROMPT
    intents: list[tuple[str, str, str]] = []

    try:
        # System prompt
        result = await session.execute(
            select(AppConfig.value).where(AppConfig.key == "system_prompt").limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            prompt = row

        # Intents (enabled only, ordered by sort_order)
        result = await session.execute(
            select(Intent.key, Intent.patterns, Intent.answer)
            .where(Intent.enabled == True)
            .order_by(Intent.sort_order)
        )
        intents = [(r.key, r.patterns, r.answer) for r in result.all()]
        if not intents:
            intents = _get_fallback_intents()
    except Exception as e:
        logger.warning("branding_config_load_failed", error=str(e))
        intents = _get_fallback_intents()

    return prompt, intents


async def refresh_cache(session: AsyncSession) -> None:
    """Load config from DB and update in-memory cache."""
    prompt, intents = await _load_from_db(session)
    _cache["system_prompt"] = prompt
    _cache["intents"] = intents
    _cache["updated_at"] = time.monotonic()
    logger.info("branding_config_cache_refreshed", intents_count=len(intents))


def get_system_prompt() -> str:
    """Return cached system prompt. Falls back to FALLBACK if cache empty."""
    prompt = _cache.get("system_prompt")
    if prompt is None:
        prompt = FALLBACK_SYSTEM_PROMPT
    if "PASS_WEAK is a bounded-answer lane" not in prompt:
        prompt = f"{prompt.rstrip()}\n{LANE_AWARE_PROMPT_SUFFIX}".strip()
    return prompt


def get_intents() -> list[tuple[str, str, str]]:
    """Return cached intents as (key, patterns, answer). Falls back if cache empty."""
    intents = _cache.get("intents")
    if intents is None:
        return _get_fallback_intents()
    return intents


def match_intent(query: str) -> IntentMatch | None:
    """Check if query matches a cached intent. Returns IntentMatch or None."""
    settings = get_settings()
    if not getattr(settings, "intent_cache_enabled", True):
        return None

    q = query.strip().lower()
    if len(q) > 200:
        return None

    intents = get_intents()
    for intent_key, patterns, answer in intents:
        if not patterns or not answer:
            continue
        try:
            if re.search(patterns, q, re.IGNORECASE):
                return IntentMatch(intent=intent_key, answer=answer)
        except re.error:
            logger.warning("intent_pattern_invalid", intent=intent_key, pattern=patterns)
            continue
    return None


def is_cache_stale() -> bool:
    """True if cache is empty or TTL exceeded."""
    if _cache.get("system_prompt") is None:
        return True
    elapsed = time.monotonic() - _cache.get("updated_at", 0)
    return elapsed > CACHE_TTL_SECONDS
