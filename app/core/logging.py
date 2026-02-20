"""Structured JSON logging with trace_id support."""

import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import Processor

# Context var for trace_id (set by middleware)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def add_trace_id(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add trace_id to log event if available."""
    trace_id = trace_id_var.get()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def redact_pii_processor(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact PII from log event values."""
    try:
        from app.core.config import get_settings
        settings = get_settings()
        if not settings.pii_redact_emails and not settings.pii_redact_phones:
            return event_dict
        for key in ("content", "query", "message", "answer", "error"):
            if key in event_dict and isinstance(event_dict[key], str):
                event_dict[key] = redact_pii(
                    event_dict[key],
                    settings.pii_redact_emails,
                    settings.pii_redact_phones,
                )
    except Exception:
        pass
    return event_dict


def redact_pii(value: str, redact_emails: bool = True, redact_phones: bool = True) -> str:
    """Redact PII from string for logging."""
    if not isinstance(value, str):
        return value
    if redact_emails:
        value = re.sub(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "[EMAIL_REDACTED]",
            value,
        )
    if redact_phones:
        value = re.sub(
            r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
            "[PHONE_REDACTED]",
            value,
        )
    return value


def setup_logging(
    json_logs: bool = True,
    log_level: str = "INFO",
    redact_emails: bool = True,
    redact_phones: bool = True,
) -> None:
    """Configure structured logging."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_trace_id,
        redact_pii_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer: Processor = structlog.processors.JSONRenderer()
        processors = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))
        processors = shared_processors + [structlog.dev.ConsoleRenderer(colors=True)]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger."""
    return structlog.get_logger(name)
