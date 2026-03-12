"""Tests for Phase 3 Decision Router."""

import pytest

from app.search.base import EvidenceChunk
from app.services.decision_router import route
from app.services.evidence_quality import QualityReport
from app.services.schemas import DecisionResult, QuerySpec


def _ambiguous_spec() -> QuerySpec:
    return QuerySpec(
        intent="ambiguous",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=["What would you like to compare?"],
        is_ambiguous=True,
        answerable_without_clarification=False,
        blocking_clarifying_questions=["What would you like to compare?"],
    )


def test_route_ambiguous():
    dr = route(_ambiguous_spec(), None, [], [], True)
    assert dr.decision == "ASK_USER"
    assert dr.reason == "ambiguous_query"
    assert dr.lane == "ASK_USER"
    assert dr.answer
    assert dr.clarifying_questions


def test_route_pass():
    spec = QuerySpec(
        intent="informational",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    report = QualityReport(0.8, {"numbers_units": 0.9}, [], None, None)
    dr = route(spec, report, [], [], True)
    assert dr.decision == "PASS"
    assert dr.reason == "sufficient"
    assert dr.lane == "CANDIDATE_VERIFY"
    assert dr.answer_policy == "direct"


def test_route_partial_for_answerable_refinement_case():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=["What budget range do you have in mind?"],
        is_ambiguous=True,
        answerable_without_clarification=True,
        assistant_should_lead=True,
        missing_info_for_refinement=["budget"],
        refinement_questions=["What budget range do you have in mind?"],
        answer_mode_hint="weak",
    )
    report = QualityReport(0.8, {"numbers_units": 0.9}, [], None, None)
    evidence = [
        EvidenceChunk("c1", "Starter plan: $10/month", "https://example.com/pricing", "pricing", 0.8, "Starter plan: $10/month"),
    ]

    dr = route(spec, report, evidence, ["numbers_units"], True)

    assert dr.decision == "PASS"
    assert dr.reason == "answerable_with_refinement"
    assert dr.lane == "CANDIDATE_VERIFY"
    assert dr.answer_policy == "bounded"
    assert dr.clarifying_questions == ["What budget range do you have in mind?"]


def test_route_missing_evidence_quality_no_evidence():
    """When gate fails and no evidence, return ASK_USER."""
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    report = QualityReport(0.3, {"numbers_units": 0.1}, ["missing_numbers"], None, None)
    evidence = []
    dr = route(spec, report, evidence, ["numbers_units"], False)
    assert dr.decision == "ASK_USER"
    assert dr.reason == "missing_evidence_quality"


def test_route_partial_candidate_when_quality_gate_fails_with_usable_evidence():
    """Mode-calibration prefers bounded PASS_PARTIAL when evidence is usable."""
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    report = QualityReport(0.3, {"numbers_units": 0.1}, ["missing_numbers"], None, None)
    evidence = [
        EvidenceChunk("c1", "snippet", "https://example.com/page", "pricing", 0.8, "full"),
    ]
    dr = route(spec, report, evidence, ["numbers_units"], False)
    assert dr.decision == "PASS"
    assert dr.reason == "partial_sufficient"
    assert dr.lane == "CANDIDATE_VERIFY"
    assert dr.answer_policy == "bounded"


def test_route_no_legacy_llm_decides_lane_when_gate_fails_with_evidence():
    """Legacy PASS_LLM_DECIDES lane is replaced by CANDIDATE_VERIFY/PASS_PARTIAL."""
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    report = QualityReport(0.3, {"numbers_units": 0.1}, ["missing_numbers"], None, None)
    evidence = [
        EvidenceChunk("c1", "snippet", "https://example.com/page", "pricing", 0.8, "full"),
    ]
    dr = route(spec, report, evidence, ["numbers_units"], False)
    assert dr.decision == "PASS"
    assert dr.reason == "partial_sufficient"
    assert dr.lane == "CANDIDATE_VERIFY"


def test_route_partial_candidate_when_quality_fails_with_partial_coverage():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units", "has_any_url"],
        risk_level="low",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=[],
        is_ambiguous=False,
        hard_requirements=["numbers_units"],
    )
    report = QualityReport(
        0.35,
        {"numbers_units": 0.1, "has_any_url": 0.0},
        ["missing_links"],
        None,
        None,
        sufficiency_scores={"numbers_units": 1.0, "has_any_url": 0.0},
        hard_requirement_coverage={"numbers_units": True},
    )
    evidence = [
        EvidenceChunk("c1", "Price: $10/month", "https://example.com/pricing", "pricing", 0.8, "Price: $10/month"),
    ]

    dr = route(spec, report, evidence, ["numbers_units", "has_any_url"], False)

    assert dr.decision == "PASS"
    assert dr.reason == "partial_sufficient"
    assert dr.lane == "CANDIDATE_VERIFY"
    assert dr.answer_policy == "bounded"


def test_route_exact_task_goes_targeted_retry_when_quality_fails(monkeypatch):
    class _Settings:
        targeted_retry_enabled = True
        exact_answer_types = ["direct_link", "pricing", "policy"]

    from app.services import decision_router as module
    monkeypatch.setattr(module, "get_settings", lambda: _Settings())

    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["policy_language"],
        risk_level="low",
        keyword_queries=["refund terms"],
        semantic_queries=["refund policy"],
        clarifying_questions=[],
        is_ambiguous=False,
        answer_type="policy",
    )
    report = QualityReport(0.2, {"policy_language": 0.1}, ["missing_policy"], None, None)

    dr = route(spec, report, [], ["policy_language"], False)

    assert dr.decision == "PASS"
    assert dr.reason == "exact_targeted_retry"
    assert dr.lane == "TARGETED_RETRY"
    assert dr.answer_policy == "targeted_retry"


def test_route_exact_task_falls_back_to_ask_user_when_targeted_retry_disabled(monkeypatch):
    class _Settings:
        targeted_retry_enabled = False

    from app.services import decision_router as module
    monkeypatch.setattr(module, "get_settings", lambda: _Settings())

    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["policy_language"],
        risk_level="low",
        keyword_queries=["refund terms"],
        semantic_queries=["refund policy"],
        clarifying_questions=[],
        is_ambiguous=False,
        answer_type="policy",
    )
    report = QualityReport(0.2, {"policy_language": 0.1}, ["missing_policy"], None, None)

    dr = route(spec, report, [], ["policy_language"], False)

    assert dr.decision == "ASK_USER"
    assert dr.lane == "ASK_USER"


def test_route_exact_task_goes_candidate_verify_when_quality_passes(monkeypatch):
    class _Settings:
        targeted_retry_enabled = True
        exact_answer_types = ["direct_link", "pricing", "policy"]

    from app.services import decision_router as module
    monkeypatch.setattr(module, "get_settings", lambda: _Settings())

    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["transaction_link"],
        risk_level="low",
        keyword_queries=["windows vps order link"],
        semantic_queries=["windows vps order page"],
        clarifying_questions=[],
        is_ambiguous=False,
        answer_type="direct_link",
    )
    report = QualityReport(0.9, {"transaction_link": 0.9}, [], None, None)
    evidence = [
        EvidenceChunk("c1", "Order now", "https://example.com/order/windows-vps", "pricing", 0.9, "Order now"),
    ]

    dr = route(spec, report, evidence, ["transaction_link"], True)

    assert dr.decision == "PASS"
    assert dr.reason == "exact_candidate_verify"
    assert dr.lane == "CANDIDATE_VERIFY"
    assert dr.answer_policy == "direct"


def test_route_high_risk_insufficient():
    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["policy_language"],
        risk_level="high",
        keyword_queries=["x"],
        semantic_queries=["x"],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    report = QualityReport(0.2, {"policy_language": 0.1}, ["missing_policy"], None, None)
    dr = route(spec, report, [], ["policy_language"], False)
    assert dr.decision == "ESCALATE"
    assert dr.reason == "high_risk_insufficient"
    assert dr.lane == "ESCALATE"
