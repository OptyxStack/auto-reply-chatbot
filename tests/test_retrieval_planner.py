"""Tests for retrieval planner (Workstream 3)."""

import pytest

from app.services.retrieval_planner import build_retrieval_plan
from app.services.retry_planner import RetryStrategy, plan_targeted_retry_queries
from app.services.schemas import HypothesisSpec, QuerySpec


def test_build_retrieval_plan_attempt_1():
    """Attempt 1 produces broad_hybrid plan."""
    plan = build_retrieval_plan("vps pricing", 1)
    assert plan.profile == "generic_profile"
    assert plan.attempt_index == 1
    assert plan.reason == "broad_hybrid"
    assert plan.query_keyword
    assert plan.query_semantic
    assert plan.fetch_n > 0
    assert plan.rerank_k > 0
    assert plan.preferred_sources == ["conversation"]


def test_build_retrieval_plan_adds_diversity_budget_hint():
    plan = build_retrieval_plan("how do i configure service", 1)
    assert plan.budget_hint is not None
    diversity = plan.budget_hint.get("diversity_doc_types") or []
    assert isinstance(diversity, list)
    assert any(dt in diversity for dt in ("howto", "docs", "faq"))


def test_build_retrieval_plan_prefers_query_spec_profile():
    """QuerySpec retrieval_profile overrides keyword heuristics."""
    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=["refund policy"],
        semantic_queries=["refund policy"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="policy_profile",
    )
    plan = build_retrieval_plan("vps plans", 1, query_spec=spec)
    assert plan.profile == "policy_profile"


def test_build_retrieval_plan_attempt_2_with_retry_strategy():
    """Attempt 2 with retry strategy produces retry_precision plan."""
    from app.services.retry_planner import RetryStrategy

    plan = build_retrieval_plan(
        "pricing",
        2,
        retry_strategy=RetryStrategy(boost_patterns=["USD", "order"]),
    )
    assert plan.attempt_index == 2
    assert plan.reason == "retry_boost_patterns"
    assert plan.boost_patterns
    assert "USD" in plan.boost_patterns


def test_build_retrieval_plan_pricing_profile_increases_fetch():
    """Pricing profile increases fetch_n and rerank_k."""
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["transaction_link"],
        risk_level="low",
        keyword_queries=["vps plans link"],
        semantic_queries=["vps plans link"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="pricing_profile",
    )
    plan = build_retrieval_plan("vps plans", 1, query_spec=spec)
    assert plan.profile == "pricing_profile"
    assert plan.fetch_n >= 50
    assert plan.rerank_k >= 8


def test_build_retrieval_plan_uses_doc_type_prior_and_budget_hint():
    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["policy_language"],
        risk_level="high",
        keyword_queries=["refund policy"],
        semantic_queries=["refund policy"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="policy_profile",
        hard_requirements=["policy_language"],
        doc_type_prior=["policy", "tos"],
    )
    plan = build_retrieval_plan("refund policy", 1, query_spec=spec)
    assert plan.preferred_doc_types is not None
    assert plan.preferred_doc_types[:2] == ["policy", "tos"]
    assert plan.budget_hint is not None
    assert plan.budget_hint.get("boost_pricing") is False
    assert plan.preferred_sources == ["conversation"]
    assert plan.budget_hint.get("preferred_sources") == ["conversation"]
    assert "policy_language" in (plan.budget_hint.get("hard_requirements") or [])
    assert "policy" in (plan.budget_hint.get("ensure_doc_types") or [])


def test_build_retrieval_plan_derives_doc_types_even_when_queryspec_doc_type_prior_empty():
    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["policy_language"],
        risk_level="high",
        keyword_queries=["refund policy"],
        semantic_queries=["refund policy"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="policy_profile",
        hard_requirements=["policy_language"],
        doc_type_prior=[],
    )

    plan = build_retrieval_plan("refund policy", 1, query_spec=spec)

    assert plan.preferred_doc_types is not None
    assert "policy" in plan.preferred_doc_types
    assert "tos" in plan.preferred_doc_types
    assert plan.profile == "policy_profile"
    assert plan.preferred_sources == ["conversation"]


def test_build_retrieval_plan_accepts_conversation_in_doc_type_prior():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["buy more ip"],
        semantic_queries=["buy more ip for vps"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="pricing_profile",
        doc_type_prior=["pricing", "conversation"],
    )

    plan = build_retrieval_plan("buy more ip", 1, query_spec=spec)

    assert plan.preferred_doc_types is not None
    assert plan.preferred_doc_types[:2] == ["pricing", "conversation"]
    assert "tos" in plan.preferred_doc_types
    assert plan.preferred_sources == ["conversation"]


def test_build_retrieval_plan_uses_primary_hypothesis_contract():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["extra IP VPS"],
        semantic_queries=["extra IP VPS"],
        clarifying_questions=[],
        is_ambiguous=False,
        evidence_families=["capability_availability", "pricing_limits"],
        answer_shape="yes_no",
        primary_hypothesis=HypothesisSpec(
            name="primary",
            evidence_families=["capability_availability", "pricing_limits"],
            answer_shape="yes_no",
            retrieval_profile="pricing_profile",
            required_evidence=["numbers_units"],
            hard_requirements=[],
            soft_requirements=["policy_language"],
            doc_type_prior=["tos", "pricing", "conversation"],
            preferred_sources=["conversation"],
        ),
    )

    plan = build_retrieval_plan("extra IP VPS", 1, query_spec=spec)

    assert plan.active_hypothesis_name == "primary"
    assert plan.answer_shape == "yes_no"
    assert plan.evidence_families == ["capability_availability", "pricing_limits"]
    assert plan.authoritative_doc_types == ["tos", "pricing"]
    assert plan.supporting_doc_types == ["conversation"]
    assert plan.active_required_evidence == ["numbers_units"]


def test_build_retrieval_plan_retry_switches_to_fallback_hypothesis():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["numbers_units"],
        risk_level="low",
        keyword_queries=["extra IP VPS"],
        semantic_queries=["extra IP VPS"],
        clarifying_questions=[],
        is_ambiguous=False,
        primary_hypothesis=HypothesisSpec(
            name="primary",
            evidence_families=["pricing_limits"],
            answer_shape="yes_no",
            retrieval_profile="pricing_profile",
            required_evidence=["numbers_units"],
            doc_type_prior=["pricing"],
        ),
        fallback_hypotheses=[
            HypothesisSpec(
                name="fallback_policy",
                evidence_families=["policy_terms"],
                answer_shape="bounded_summary",
                retrieval_profile="policy_profile",
                required_evidence=["policy_language"],
                hard_requirements=[],
                doc_type_prior=["tos", "policy", "faq"],
                preferred_sources=["conversation"],
            )
        ],
    )

    plan = build_retrieval_plan(
        "extra IP VPS",
        2,
        query_spec=spec,
        retry_strategy=RetryStrategy(hypothesis_index=1, hypothesis_name="fallback_policy"),
    )

    assert plan.active_hypothesis_name == "fallback_policy"
    assert plan.profile == "policy_profile"
    assert plan.active_required_evidence == ["policy_language"]
    assert "tos" in (plan.authoritative_doc_types or [])


def test_build_retrieval_plan_adds_page_kind_hints_for_direct_link():
    spec = QuerySpec(
        intent="transactional",
        entities=["windows", "vps"],
        constraints={},
        required_evidence=["transaction_link"],
        risk_level="low",
        keyword_queries=["windows vps order page"],
        semantic_queries=["windows vps order page"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="pricing_profile",
        answer_type="direct_link",
        target_entity="windows_vps",
    )

    plan = build_retrieval_plan("windows vps order link", 1, query_spec=spec)
    hint = plan.budget_hint or {}

    assert hint.get("answer_type") == "direct_link"
    assert "order_page" in (hint.get("preferred_page_kinds") or [])
    assert "product_page" in (hint.get("preferred_page_kinds") or [])
    assert "windows_vps" in (hint.get("product_family_hints") or [])
    assert "faq" in (hint.get("demote_doc_types") or [])


def test_build_retrieval_plan_derives_windows_product_family_from_slots_and_entities():
    spec = QuerySpec(
        intent="informational",
        entities=["Windows VPS", "Singapore"],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=["windows vps singapore"],
        semantic_queries=["windows vps singapore"],
        clarifying_questions=[],
        is_ambiguous=False,
        retrieval_profile="generic_profile",
        answer_type="general",
        answer_shape="yes_no",
        target_entity="Windows VPS availability by location",
        resolved_slots={"product_type": "vps", "os": "windows"},
    )

    plan = build_retrieval_plan("do u have window vps in sg", 1, query_spec=spec)
    hint = plan.budget_hint or {}

    assert "windows_vps" in (hint.get("product_family_hints") or [])
    assert "product_page" in (hint.get("preferred_page_kinds") or [])


def test_plan_targeted_retry_queries_for_direct_link():
    queries = plan_targeted_retry_queries(
        expected_answer_type="direct_link",
        target_entity="windows_vps",
        query="need windows vps link",
    )
    assert queries
    assert queries[0] == "windows vps order page"
    assert "windows vps product page" in queries


def test_plan_targeted_retry_queries_for_policy():
    queries = plan_targeted_retry_queries(
        expected_answer_type="policy",
        target_entity="refund_policy",
        query="what is the refund policy",
    )
    assert queries
    assert "refund policy terms of service" in queries[0].lower()
