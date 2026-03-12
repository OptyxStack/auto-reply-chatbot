"""Tests for verify phase decision propagation."""

import pytest

from app.services.orchestrator import OrchestratorContext
from app.services.phases.verify import execute_verify
from app.services.reviewer import ReviewerResult, ReviewerStatus
from app.services.schemas import DecisionResult, QuerySpec


class _ReviewerStub:
    def __init__(self):
        self.last_kwargs = None

    def review(self, **kwargs):
        self.last_kwargs = kwargs
        decision = kwargs.get("decision")
        status = ReviewerStatus.PASS
        if decision == "ASK_USER":
            status = ReviewerStatus.ASK_USER
        elif decision == "ESCALATE":
            status = ReviewerStatus.ESCALATE
        return ReviewerResult(
            status=status,
            reasons=[],
            suggested_queries=[],
            missing_fields=[],
        )


def _ctx() -> OrchestratorContext:
    ctx = OrchestratorContext(query="test query")
    ctx.answer = "answer"
    ctx.citations = []
    ctx.evidence = []
    ctx.confidence = 0.7
    ctx.decision_result = DecisionResult(
        decision="PASS",
        reason="sufficient",
        clarifying_questions=[],
        partial_links=[],
        answer_policy="direct",
        lane="PASS_EXACT",
    )
    ctx.query_spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        answer_type="direct_link",
        target_entity="windows_vps",
        acceptable_related_types=["pricing"],
        answer_expectation="exact",
    )
    return ctx


@pytest.mark.asyncio
async def test_verify_uses_generated_decision_from_context():
    from app.services import phases
    phases.verify._pipeline_log = lambda *args, **kwargs: None

    ctx = _ctx()
    ctx.generated_decision = "ESCALATE"
    reviewer = _ReviewerStub()

    result = await execute_verify(ctx, reviewer=reviewer)

    assert reviewer.last_kwargs is not None
    assert reviewer.last_kwargs["decision"] == "ESCALATE"
    assert result.reviewer_result.status == ReviewerStatus.ESCALATE


@pytest.mark.asyncio
async def test_verify_falls_back_to_pass_for_invalid_generated_decision():
    from app.services import phases
    phases.verify._pipeline_log = lambda *args, **kwargs: None

    ctx = _ctx()
    ctx.generated_decision = "UNEXPECTED"
    reviewer = _ReviewerStub()

    result = await execute_verify(ctx, reviewer=reviewer)

    assert reviewer.last_kwargs is not None
    assert reviewer.last_kwargs["decision"] == "PASS"
    assert result.reviewer_result.status == ReviewerStatus.PASS


@pytest.mark.asyncio
async def test_verify_runs_multi_hypothesis_judge_when_history_present():
    from app.services import phases
    phases.verify._pipeline_log = lambda *args, **kwargs: None

    ctx = _ctx()
    ctx.extra["hypothesis_history"] = [
        {"name": "primary", "retrieval_profile": "policy_profile", "evidence_families": ["policy_terms"], "quality_score": 0.2, "gate_pass": False, "evidence_count": 4},
        {"name": "fallback_capability", "retrieval_profile": "pricing_profile", "evidence_families": ["capability_availability"], "quality_score": 0.8, "gate_pass": True, "evidence_count": 5},
    ]
    reviewer = _ReviewerStub()

    result = await execute_verify(ctx, reviewer=reviewer)

    assert result.hypothesis_judge is not None
    assert result.hypothesis_judge["selected_hypothesis"] == "fallback_capability"


@pytest.mark.asyncio
async def test_verify_forwards_answer_calibration_context():
    from app.services import phases
    phases.verify._pipeline_log = lambda *args, **kwargs: None

    ctx = _ctx()
    ctx.extra["answer_candidate"] = {
        "answer_type": "pricing",
        "answer_mode": "PASS_PARTIAL",
    }
    reviewer = _ReviewerStub()

    await execute_verify(ctx, reviewer=reviewer)

    assert reviewer.last_kwargs is not None
    assert reviewer.last_kwargs["expected_answer_type"] == "direct_link"
    assert reviewer.last_kwargs["acceptable_related_types"] == ["pricing"]
    assert reviewer.last_kwargs["answer_expectation"] == "exact"
    assert reviewer.last_kwargs["target_entity"] == "windows_vps"
    assert reviewer.last_kwargs["answer_candidate"] == ctx.extra["answer_candidate"]
