"""Dashboard: token/cost summary, retrieval hit-rate, escalation rate."""

from fastapi import APIRouter
from prometheus_client import REGISTRY

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_stats():
    """Return aggregated stats for dashboard (from Prometheus metrics)."""
    metrics = {}
    for collector in REGISTRY.collect():
        for sample in collector.samples:
            if sample.name.startswith("support_ai_"):
                labels = "_".join(f"{k}={v}" for k, v in sorted(sample.labels.items())) if sample.labels else ""
                key = f"{sample.name}" + (f"{{{labels}}}" if labels else "")
                metrics[key] = sample.value
    return {"metrics": metrics}
