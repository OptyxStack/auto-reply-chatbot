"""Tests for flow debug explainability."""

from app.services.flow_debug import REASON_HUMAN_READABLE, build_flow_debug


def test_build_flow_debug_includes_stage_reasons():
    """stage_reasons and termination_reason should appear in debug output."""
    debug = build_flow_debug(
        trace_id="t1",
        evidence_pack=None,
        evidence=[],
        messages=[],
        model_used="gpt-5.2",
        stage_reasons=["understand: query_spec_ready", "retrieve: chunks=8", "assess_evidence: gate=pass"],
        termination_reason="done",
    )
    assert debug["stage_reasons"] == ["understand: query_spec_ready", "retrieve: chunks=8", "assess_evidence: gate=pass"]
    assert debug["termination_reason"] == "done"


def test_build_flow_debug_decision_router_reason_human():
    """decision_router should include reason_human for known reasons."""
    from app.services.schemas import DecisionResult

    dr = DecisionResult(
        decision="ASK_USER",
        reason="ambiguous_query",
        clarifying_questions=["What would you like to compare?"],
        partial_links=[],
    )
    debug = build_flow_debug(
        trace_id="t2",
        evidence_pack=None,
        evidence=[],
        messages=[],
        model_used="gpt-4o-mini",
        decision_router=dr,
    )
    assert debug["decision_router"]["reason"] == "ambiguous_query"
    assert debug["decision_router"]["reason_human"] == "Query ambiguous; referent unclear"


def test_reason_human_readable_mapping():
    """REASON_HUMAN_READABLE should cover main decision reasons."""
    assert REASON_HUMAN_READABLE["sufficient"] == "Evidence sufficient for answer"
    assert REASON_HUMAN_READABLE["missing_evidence_quality"] == "Evidence quality below threshold"
    assert REASON_HUMAN_READABLE.get("unknown_reason", "x") == "x"
