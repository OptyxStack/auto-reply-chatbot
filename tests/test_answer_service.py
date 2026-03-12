"""Tests for answer service helpers."""

from app.services.answer_utils import (
    apply_answer_plan,
    build_answer_plan,
    collect_rewrite_candidates,
    parse_llm_response,
    render_calibrated_candidate,
    resolve_retrieval_query,
)
from app.services.evidence_quality import QualityReport
from app.services.retry_planner import RetryStrategy
from app.services.schemas import DecisionResult, QuerySpec


def test_collect_rewrite_candidates_dedupes_case_insensitive():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
        rewrite_candidates=["Pricing Query", "pricing query", "Dedicated pricing"],
    )

    candidates = collect_rewrite_candidates("pricing query", spec)

    assert candidates == ["pricing query", "Dedicated pricing"]


def test_resolve_retrieval_query_uses_rewrite_candidate_on_retry():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
        rewrite_candidates=["pricing query", "dedicated monthly pricing"],
    )

    query, source, candidates = resolve_retrieval_query(
        base_query="pricing query",
        attempt=2,
        query_spec=spec,
        retry_strategy=None,
    )

    assert query == "dedicated monthly pricing"
    assert source == "rewrite_candidate_1"
    assert candidates == ["pricing query", "dedicated monthly pricing"]


def test_resolve_retrieval_query_prefers_retry_strategy_suggestion():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
        rewrite_candidates=["pricing query", "dedicated monthly pricing"],
    )
    strategy = RetryStrategy(suggested_query="policy refund terms")

    query, source, _ = resolve_retrieval_query(
        base_query="pricing query",
        attempt=2,
        query_spec=spec,
        retry_strategy=strategy,
        explicit_override="reviewer suggested query",
    )

    assert query == "policy refund terms"
    assert source == "retry_strategy_suggested_query"


def test_build_answer_plan_for_pass_partial_lane():
    spec = QuerySpec(
        intent="transactional",
        entities=[],
        constraints={},
        required_evidence=["has_any_url"],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
        hard_requirements=["numbers_units"],
    )
    dr = DecisionResult(
        decision="PASS",
        reason="partial_sufficient",
        clarifying_questions=[],
        partial_links=[],
        answer_policy="bounded",
        lane="PASS_PARTIAL",
    )
    report = QualityReport(
        quality_score=0.35,
        feature_scores={"numbers_units": 0.1},
        missing_signals=["missing_links"],
        staleness_risk=None,
        boilerplate_risk=0.0,
    )

    plan = build_answer_plan(dr, spec, report)

    assert plan.lane == "CANDIDATE_VERIFY"
    assert plan.allowed_claim_scope == "partial"
    assert plan.tone_policy == "cautious"
    assert "numbers_units" in plan.required_citations


def test_apply_answer_plan_bounds_pass_partial_output():
    plan = build_answer_plan(
        DecisionResult(
            decision="PASS",
            reason="partial_sufficient",
            clarifying_questions=["Which region do you prefer?"],
            partial_links=[],
            answer_policy="bounded",
            lane="PASS_PARTIAL",
        ),
        None,
        None,
    )

    decision, answer, followup, confidence = apply_answer_plan(
        plan,
        {
            "decision": "ASK_USER",
            "answer": "The available evidence shows the service starts at $10/month.",
            "followup_questions": ["Which plan do you want?"],
            "confidence": 0.92,
        },
    )

    assert decision == "PASS"
    assert followup == ["Which plan do you want?"]
    assert confidence == 0.6
    assert "unverified" in answer.lower() or "best available" in answer.lower() or "best we have" in answer.lower()


def test_apply_answer_plan_uses_router_followup_for_pass_partial_when_llm_omits_it():
    plan = build_answer_plan(
        DecisionResult(
            decision="PASS",
            reason="answerable_with_refinement",
            clarifying_questions=["What budget range works for you?"],
            partial_links=[],
            answer_policy="bounded",
            lane="PASS_PARTIAL",
        ),
        None,
        None,
    )

    decision, answer, followup, confidence = apply_answer_plan(
        plan,
        {
            "decision": "PASS",
            "answer": "A good starting point is 4 GB RAM and 2 vCPU.",
            "followup_questions": [],
            "confidence": 0.8,
        },
    )

    assert decision == "PASS"
    assert "starting point" in answer
    assert followup == ["What budget range works for you?"]
    assert confidence == 0.6


def test_render_calibrated_candidate_for_pass_exact():
    answer, followup = render_calibrated_candidate(
        {
            "answer_text": "Order at https://example.com/order/windows-vps",
            "followup_questions": ["Do you need monthly or yearly billing?"],
            "disclaimers": [],
        },
        calibrated_lane="PASS_EXACT",
        fallback_answer="fallback",
        fallback_followup=[],
    )

    assert "https://example.com/order/windows-vps" in answer
    assert followup == ["Do you need monthly or yearly billing?"]


def test_render_calibrated_candidate_adds_partial_disclaimer_when_missing():
    answer, followup = render_calibrated_candidate(
        {
            "answer_text": "Closest page we found is https://example.com/pricing/windows-vps.",
            "followup_questions": [],
            "disclaimers": [],
        },
        calibrated_lane="PASS_PARTIAL",
        fallback_answer="fallback",
        fallback_followup=["Which region do you need?"],
    )

    assert "best we have" in answer.lower() or "best available" in answer.lower() or "closest" in answer.lower()
    assert followup == ["Which region do you need?"]


def test_render_calibrated_candidate_adds_partial_disclaimer_without_candidate():
    answer, followup = render_calibrated_candidate(
        None,
        calibrated_lane="PASS_PARTIAL",
        fallback_answer="Closest page we found is https://example.com/pricing/windows-vps.",
        fallback_followup=["Which region do you need?"],
    )

    assert "best we have" in answer.lower() or "best available" in answer.lower() or "closest" in answer.lower()
    assert followup == ["Which region do you need?"]


def test_parse_llm_response_supports_optional_advice_block():
    parsed = parse_llm_response(
        """
        {
          "decision": "PASS",
          "candidate": {
            "answer_type": "general",
            "answer_mode": "PASS_PARTIAL",
            "answer_text": "Based on our docs, NEWSEO1 starts at $16/month and NEWSEO2 starts at $26/month.",
            "citations": [{"chunk_id": "chunk-price-1", "source_url": "https://example.com/seo", "doc_type": "pricing"}],
            "advice": {
              "enabled": true,
              "text": "If you are just starting out, I would begin with NEWSEO2 for a safer default.",
              "basis": ["balanced default", "budget not provided"],
              "confidence": 0.58
            }
          }
        }
        """
    )

    candidate = parsed["candidate"]
    assert candidate["answer_text"].startswith("Based on our docs")
    assert candidate["advice_enabled"] is True
    assert "NEWSEO2" in candidate["advice_text"]
    assert candidate["advice_basis"] == ["balanced default", "budget not provided"]


def test_render_calibrated_candidate_appends_safe_advice_block():
    answer, followup = render_calibrated_candidate(
        {
            "answer_text": "Based on our docs, NEWSEO1 starts at $16/month and NEWSEO2 starts at $26/month.",
            "followup_questions": ["What budget range works for you?"],
            "disclaimers": [],
            "advice_enabled": True,
            "advice_text": "If you are just starting out, I would begin with NEWSEO2 for a safer default.",
            "metadata": {},
        },
        calibrated_lane="PASS_PARTIAL",
        fallback_answer="fallback",
        fallback_followup=[],
    )

    assert "my recommendation:" in answer.lower()
    assert "NEWSEO2" in answer
    assert followup == ["What budget range works for you?"]


def test_render_calibrated_candidate_drops_fact_like_advice_block():
    answer, _ = render_calibrated_candidate(
        {
            "answer_text": "Based on our docs, NEWSEO1 starts at $16/month and NEWSEO2 starts at $26/month.",
            "followup_questions": [],
            "disclaimers": [],
            "advice_enabled": True,
            "advice_text": "Choose NEWSEO3 at $46/month here: https://example.com/newseo3",
            "metadata": {},
        },
        calibrated_lane="PASS_EXACT",
        fallback_answer="fallback",
        fallback_followup=[],
    )

    assert "my recommendation:" not in answer.lower()
    assert "https://example.com/newseo3" not in answer
