"""Intent-based shortcut cache for common queries (who am i, what can you do, etc.).

Returns predefined answers without calling LLM/retrieval. Configurable via env.
"""

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IntentMatch:
    """Result of intent matching."""

    intent: str
    answer: str


# GreenCloud VPS - intent cache for common queries
# https://green.cloud | https://green.cloud/docs
DEFAULT_INTENTS: dict[str, dict[str, str]] = {
    "what_can_you_do": {
        "patterns": r"\b(what (can you|do you|does (this )?ai) do|bạn làm gì|ai làm gì|chức năng)\b",
        "answer": "I'm GreenCloud's AI support assistant. I can help with questions about our VPS (Windows, Linux KVM, macOS), dedicated servers, pricing, setup guides, and policies. Our docs are at https://green.cloud/docs. What would you like to know?",
    },
    "who_are_you": {
        "patterns": r"\b(who are you|bạn là ai|ai là gì)\b",
        "answer": "I'm GreenCloud's AI support assistant. GreenCloud is a leading VPS and dedicated server provider (founded 2013), offering Windows VPS, KVM Linux VPS, macOS VPS, and bare-metal servers. I answer questions using our documentation at https://green.cloud/docs.",
    },
    "who_am_i": {
        "patterns": r"\b(who am i|tôi là ai|mình là ai)\b",
        "answer": "I don't have access to your GreenCloud account details. For billing, account info, or service management, please log in at https://greencloudvps.com/billing or contact our 24/7 support (average response: 9 minutes).",
    },
    "about_greencloud": {
        "patterns": r"\b(what is greencloud|about greencloud|greencloud là gì|giới thiệu greencloud)\b",
        "answer": "GreenCloud is an Infrastructure as a Service provider founded in 2013. We offer: Windows VPS (from $8/mo), KVM Linux VPS (from $6/mo), macOS VPS (from $22/mo), and dedicated servers (from $110/mo). 99.99% uptime, 24/7 in-house support (9-min avg response), 30 locations across 4 continents. Docs: https://green.cloud/docs",
    },
    "hello": {
        "patterns": r"^(hi|hello|hey|chào|xin chào)\s*!?$",
        "answer": "Hello! Welcome to GreenCloud support. I can help with VPS, dedicated servers, pricing, or how-to guides. What do you need?",
    },
}


def _load_intent_responses() -> dict[str, dict[str, str]]:
    """Load intent config from settings or use defaults."""
    return DEFAULT_INTENTS


def match_intent(query: str) -> IntentMatch | None:
    """Check if query matches a cached intent. Returns (intent, answer) or None."""
    settings = get_settings()
    if not getattr(settings, "intent_cache_enabled", True):
        return None

    q = query.strip().lower()
    if len(q) > 200:  # Long queries unlikely to be simple intents
        return None

    intents = _load_intent_responses()
    for intent_key, config in intents.items():
        patterns = config.get("patterns", "")
        answer = config.get("answer", "")
        if not patterns or not answer:
            continue
        try:
            if re.search(patterns, q, re.IGNORECASE):
                return IntentMatch(intent=intent_key, answer=answer)
        except re.error:
            logger.warning("intent_pattern_invalid", intent=intent_key, pattern=patterns)
            continue
    return None
