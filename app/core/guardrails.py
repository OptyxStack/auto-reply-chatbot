"""Guardrails: input sanitization, jailbreak/injection defense."""

import re
from typing import Any

from app.core.logging import get_logger, redact_pii

logger = get_logger(__name__)

# Patterns that suggest prompt injection / jailbreak
INJECTION_PATTERNS = [
    (r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?", "instruction_override"),
    (r"disregard\s+(?:all\s+)?(?:previous|above)", "instruction_override"),
    (r"you\s+are\s+now\s+(?:a|an)\s+\w+", "role_override"),
    (r"pretend\s+you\s+are", "role_override"),
    (r"act\s+as\s+if\s+you", "role_override"),
    (r"system\s*:\s*", "system_prompt_leak"),
    (r"\[INST\]|\[/INST\]", "instruction_marker"),
    (r"<\|im_start\|>|<\|im_end\|>", "chatml_marker"),
]


def sanitize_user_input(text: str) -> str:
    """Sanitize user input: strip dangerous patterns, return cleaned string."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = text.strip()
    for pattern, _ in INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[REDACTED]", cleaned, flags=re.I)
    return cleaned[:10000]  # Max length


def check_injection(text: str) -> tuple[bool, str | None]:
    """Check for injection. Returns (is_safe, attack_type if found)."""
    if not text:
        return True, None
    for pattern, attack_type in INJECTION_PATTERNS:
        if re.search(pattern, text, re.I):
            return False, attack_type
    return True, None


def safe_for_logging(value: Any, redact_emails: bool = True, redact_phones: bool = True) -> Any:
    """Recursively redact PII from value for logging."""
    if isinstance(value, str):
        return redact_pii(value, redact_emails, redact_phones)
    if isinstance(value, dict):
        return {k: safe_for_logging(v, redact_emails, redact_phones) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_for_logging(v, redact_emails, redact_phones) for v in value]
    return value
