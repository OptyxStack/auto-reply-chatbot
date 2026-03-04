"""ASSESS_EVIDENCE phase: quality gate."""

from app.services.archi_config import get_evidence_quality_llm_v2, get_evidence_quality_use_llm
from app.services.evidence_quality import (
    evaluate_quality,
    evaluate_quality_llm,
    evaluate_quality_llm_v2,
    passes_quality_gate,
)
from app.services.flow_debug import _pipeline_log
from app.services.orchestrator import OrchestratorContext, PhaseResult


async def execute_assess_evidence(ctx: OrchestratorContext) -> PhaseResult:
    """Run quality gate on retrieved evidence."""
    required_evidence = ctx.extra.get("required_evidence", [])
    hard_requirements = ctx.extra.get("hard_requirements", [])

    if get_evidence_quality_llm_v2():
        quality_report = await evaluate_quality_llm_v2(
            ctx.query,
            ctx.evidence,
            required_evidence,
            hard_requirements=hard_requirements,
        )
    elif get_evidence_quality_use_llm():
        quality_report = await evaluate_quality_llm(
            ctx.query,
            ctx.evidence,
            required_evidence,
            hard_requirements=hard_requirements,
        )
    else:
        quality_report = evaluate_quality(
            ctx.evidence,
            required_evidence,
            hard_requirements=hard_requirements,
        )
    try:
        from app.core.metrics import evidence_quality_score
        evidence_quality_score.observe(quality_report.quality_score)
    except Exception:
        pass
    gate_passed = passes_quality_gate(
        quality_report,
        required_evidence,
        hard_requirements=hard_requirements,
    )
    _pipeline_log(
        "assess", "done",
        passes_quality_gate=gate_passed,
        quality_score=quality_report.quality_score,
        missing_signals=quality_report.missing_signals,
        hard_requirement_coverage=quality_report.hard_requirement_coverage,
        trace_id=ctx.trace_id,
    )
    return PhaseResult(
        quality_report=quality_report,
        passes_quality_gate=gate_passed,
    )
