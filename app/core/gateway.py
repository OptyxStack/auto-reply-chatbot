"""API Gateway middleware: request size, IP rules, WAF."""

import re
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# WAF: common injection / jailbreak patterns
WAF_PATTERNS = [
    (r"ignore\s+(?:all\s+)?(?:previous|above)\s+instructions?", "instruction_override"),
    (r"you\s+are\s+now\s+(?:a|an)\s+\w+\s+that", "role_override"),
    (r"<\s*script\s*>", "script_injection"),
    (r"javascript\s*:", "script_injection"),
    (r"(?:\bOR\b|\bAND\b)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+", "sql_injection"),
    (r"union\s+select\s+", "sql_injection"),
    (r"drop\s+table\s+", "sql_injection"),
    (r"\{\{.*?\}\}", "template_injection"),
    (r"\$\{.*?\}", "template_injection"),
]


def _check_waf(content: str) -> str | None:
    """Return attack type if WAF triggered, else None."""
    if not content:
        return None
    content_lower = content.lower()
    for pattern, attack_type in WAF_PATTERNS:
        if re.search(pattern, content_lower, re.I):
            return attack_type
    return None


class GatewayMiddleware(BaseHTTPMiddleware):
    """Request size limit, IP rules, WAF."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"

        # IP blocklist (comma-separated in env)
        blocklist = getattr(settings, "ip_blocklist", "") or ""
        if blocklist and client_ip in [x.strip() for x in blocklist.split(",") if x.strip()]:
            logger.warning("gateway_ip_blocked", ip=client_ip)
            return Response(status_code=403, content="Forbidden")

        # IP allowlist (if set, only these IPs allowed)
        allowlist = getattr(settings, "ip_allowlist", "") or ""
        if allowlist:
            allowed = [x.strip() for x in allowlist.split(",") if x.strip()]
            if client_ip not in allowed:
                logger.warning("gateway_ip_not_allowed", ip=client_ip)
                return Response(status_code=403, content="Forbidden")

        # Request body size limit (skip for SSE streaming response path)
        max_body = getattr(settings, "max_request_body_bytes", 1_000_000) or 1_000_000
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > max_body:
                return Response(
                    status_code=413,
                    content="Request entity too large",
                )
            # WAF check on body
            try:
                body_str = body.decode("utf-8", errors="replace")
                attack = _check_waf(body_str)
                if attack:
                    logger.warning("gateway_waf_triggered", attack=attack, ip=client_ip)
                    return Response(status_code=400, content="Invalid request")
            except Exception:
                pass
            # Re-inject body for downstream (Request stores body once)
            async def receive():
                return {"type": "http.request", "body": body}

            request = Request(request.scope, receive=receive)

        return await call_next(request)
