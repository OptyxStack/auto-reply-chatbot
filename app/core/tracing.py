"""OpenTelemetry tracing and Prometheus metrics."""

from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from opentelemetry import trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import REGISTRY, make_asgi_app

from app.core.config import get_settings
from app.core.logging import trace_id_var

# Trace ID for request correlation
request_trace_id_var: ContextVar[str | None] = ContextVar("request_trace_id", default=None)

# LLM usage accumulator for per-message cost (list of {model, input_tokens, output_tokens})
llm_usage_var: ContextVar[list | None] = ContextVar("llm_usage", default=None)


def get_trace_id() -> str:
    """Get or create trace_id for current request."""
    tid = trace_id_var.get() or request_trace_id_var.get()
    if tid:
        return tid
    return str(uuid4())


def setup_tracing(app) -> None:
    """Configure OpenTelemetry and Prometheus."""
    settings = get_settings()
    resource = Resource.create({"service.name": "support-ai-assistant"})

    # Tracing
    provider = TracerProvider(resource=resource)
    if settings.debug:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("support-ai-assistant", "1.0.0")

    # Metrics
    reader = PrometheusMetricReader()
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    # Note: OpenTelemetry Prometheus uses its own registry; we'll expose via /metrics

    FastAPIInstrumentor.instrument_app(app)

    @app.middleware("http")
    async def add_trace_id_middleware(request: Request, call_next):
        tid = request.headers.get("X-Trace-Id") or str(uuid4())
        trace_id_var.set(tid)
        request_trace_id_var.set(tid)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = tid
        return response
