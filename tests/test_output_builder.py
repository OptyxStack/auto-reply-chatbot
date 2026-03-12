"""Tests for final output rendering in Phase 6."""

import pytest

from app.services.orchestrator import OrchestratorAction, OrchestratorContext
from app.services.output_builder import build_output
from app.services.schemas import QuerySpec, ReviewResult


@pytest.mark.asyncio
async def test_build_output_done_renders_from_calibrated_candidate():
    ctx = OrchestratorContext(query="windows vps order link")
    ctx.answer = "fallback answer"
    ctx.followup = ["fallback followup"]
    ctx.confidence = 0.55
    ctx.citations = [{"chunk_id": "c1", "source_url": "https://example.com/pricing", "doc_type": "pricing"}]
    ctx.review_result = ReviewResult(
        status="downgrade_lane",
        unsupported_claims=[],
        weakly_supported_claims=[],
        claim_to_citation_map={},
        reviewer_notes=[],
        final_lane="PASS_PARTIAL",
        suggested_retry_plan=None,
    )
    ctx.extra["answer_candidate"] = {
        "answer_text": "Closest related official page: https://example.com/pricing/windows-vps",
        "followup_questions": ["Which billing cycle do you prefer?"],
        "disclaimers": ["Closest related official page, exact order page not verified."],
    }

    out = await build_output(
        ctx,
        OrchestratorAction.DONE,
        get_model_for_query=lambda _: "test-model",
    )

    assert out.decision == "PASS"
    assert "closest related official page" in out.answer.lower()
    assert out.followup_questions == ["Which billing cycle do you prefer?"]
    assert (out.debug or {}).get("rollout_flags") is not None


@pytest.mark.asyncio
async def test_build_output_reports_shadow_rollout_when_enabled(monkeypatch):
    class _Settings:
        soft_contract_enabled = False
        answer_candidate_enabled = True
        page_kind_filter_enabled = True
        targeted_retry_enabled = True
        soft_contract_shadow_percent = 100

    from app.services import output_builder as module
    monkeypatch.setattr(module, "get_settings", lambda: _Settings())

    ctx = OrchestratorContext(query="pricing", trace_id="trace-shadow")
    ctx.answer = "fallback"
    ctx.followup = []
    ctx.review_result = ReviewResult(
        status="accept",
        unsupported_claims=[],
        weakly_supported_claims=[],
        claim_to_citation_map={},
        reviewer_notes=[],
        final_lane="PASS_EXACT",
        suggested_retry_plan=None,
    )

    out = await build_output(
        ctx,
        OrchestratorAction.DONE,
        get_model_for_query=lambda _: "test-model",
    )

    flags = (out.debug or {}).get("rollout_flags") or {}
    assert flags.get("soft_contract_enabled") is False
    assert flags.get("soft_contract_shadow_active") is True


@pytest.mark.asyncio
async def test_build_output_uses_bounded_availability_fallback_after_retry_exhaustion():
    evidence_chunk = type(
        "E",
        (),
        {
            "chunk_id": "c1",
            "source_url": "https://example.com/windows-vps",
            "doc_type": "docs",
            "score": 0.42,
            "snippet": "Windows VPS docs",
            "full_text": "Windows VPS docs without Singapore confirmation",
        },
    )()

    ctx = OrchestratorContext(
        query="do u have window vps in sg",
        max_attempts=2,
        retrieval_attempt=2,
    )
    ctx.evidence = [evidence_chunk]
    ctx.query_spec = QuerySpec(
        intent="informational",
        entities=["Windows VPS", "Singapore"],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=["windows vps singapore"],
        semantic_queries=["windows vps singapore"],
        clarifying_questions=[],
        is_ambiguous=False,
        answer_type="general",
        answer_shape="yes_no",
        evidence_families=["capability_availability"],
        resolved_slots={"product_type": "vps", "os": "windows"},
    )

    out = await build_output(
        ctx,
        OrchestratorAction.ASK_USER,
        get_model_for_query=lambda _: "test-model",
    )

    assert out.decision == "ASK_USER"
    assert "couldn't confirm from our docs" in out.answer.lower()
    assert "windows vps" in out.answer.lower()


@pytest.mark.asyncio
async def test_build_output_uses_bounded_availability_fallback_when_no_evidence():
    ctx = OrchestratorContext(
        query="do u have window vps in singpg",
        max_attempts=3,
        retrieval_attempt=3,
    )
    ctx.query_spec = QuerySpec(
        intent="informational",
        entities=["Windows VPS", "Singapore"],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=["windows vps singapore"],
        semantic_queries=["windows vps singapore"],
        clarifying_questions=[],
        is_ambiguous=False,
        answer_type="general",
        answer_shape="yes_no",
        evidence_families=["capability_availability"],
        resolved_slots={"product_type": "vps", "os": "windows"},
    )

    out = await build_output(
        ctx,
        OrchestratorAction.ASK_USER,
        get_model_for_query=lambda _: "test-model",
    )

    assert out.decision == "ASK_USER"
    assert "couldn't find documentation confirming" in out.answer.lower()
    assert "windows vps" in out.answer.lower()
