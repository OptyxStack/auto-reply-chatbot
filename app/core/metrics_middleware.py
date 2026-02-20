"""Middleware to record API request metrics."""

import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import api_latency_seconds, api_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record API request count and latency."""

    async def dispatch(self, request: Request, call_next: Callable):
        start = time.perf_counter()
        path = (request.url.path or "unknown").rstrip("/") or "/"
        method = request.method or "unknown"
        # Normalize path for cardinality (avoid high cardinality from UUIDs)
        if "/conversations/" in path:
            path = "/v1/conversations/{id}" + ("/messages" if "messages" in path else "")

        response = await call_next(request)
        duration = time.perf_counter() - start
        status = response.status_code

        try:
            api_requests_total.labels(method=method, path=path[:80], status=str(status)).inc()
            api_latency_seconds.labels(method=method, path=path[:80]).observe(duration)
        except Exception:
            pass

        return response
