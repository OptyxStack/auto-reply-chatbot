"""Tests for Phase 4 offline evaluation harness."""

from pathlib import Path

import pytest

from app.services.offline_eval import (
    OfflineEvalCase,
    evaluate_case,
    load_eval_cases_jsonl,
    run_offline_eval,
)
from app.services.schemas import AnswerOutput


def _debug_payload(
    *,
    evidence_ids: list[str],
    evidence_rows: list[dict] | None = None,
    covered_requirements: list[str] | None = None,
    hard_coverage: dict[str, bool] | None = None,
    unsupported_claims: list[str] | None = None,
    decision_router: dict | None = None,
):
    rows = evidence_rows or [{"chunk_id": cid} for cid in evidence_ids]
    return {
        "evidence_summary": rows,
        "evidence_set": {"covered_requirements": covered_requirements or []},
        "quality_report": {"hard_requirement_coverage": hard_coverage or {}},
        "review_unsupported_claims": unsupported_claims or [],
        "decision_router": decision_router or {},
    }


class _FakeAnswerService:
    def __init__(self, outputs_by_query: dict[str, AnswerOutput]):
        self._outputs_by_query = outputs_by_query

    async def generate(self, query: str, conversation_history=None, trace_id=None):
        _ = (conversation_history, trace_id)
        return self._outputs_by_query[query]


def test_load_eval_cases_contains_required_replay_classes():
    fixture = Path(__file__).parent / "fixtures" / "offline_eval_replay_cases.jsonl"
    cases = load_eval_cases_jsonl(fixture)
    tags = {tag for case in cases for tag in case.tags}

    assert "ambiguous_referent" in tags
    assert "recommendation_refinement" in tags
    assert "conversation_capability" in tags
    assert "policy_question" in tags
    assert "pricing_question" in tags
    assert "troubleshooting_steps" in tags
    assert "multilingual_query" in tags


@pytest.mark.asyncio
async def test_evaluate_case_computes_split_metrics_and_passes():
    case = OfflineEvalCase(
        name="policy_case",
        input="what is refund policy?",
        expected_decision="PASS",
        expected_chunk_ids=["chunk-policy-1"],
        required_evidence=["policy_language"],
        expected_answer_contains=["refund within 30 days"],
    )
    output = AnswerOutput(
        decision="PASS",
        answer="Our refund policy allows refund within 30 days.",
        followup_questions=[],
        citations=[{"chunk_id": "chunk-policy-1"}],
        confidence=0.9,
        debug=_debug_payload(
            evidence_ids=["chunk-policy-1", "chunk-faq-1"],
            covered_requirements=["policy_language"],
            hard_coverage={"policy_language": True},
            unsupported_claims=[],
        ),
    )
    svc = _FakeAnswerService({case.input: output})

    result = await evaluate_case(svc, case, run_id="testrun")

    assert result.passed is True
    assert result.metrics["retrieval_recall"] == 1.0
    assert result.metrics["evidence_coverage"] == 1.0
    assert result.metrics["answer_correctness"] == 1.0
    assert result.metrics["hallucination_rate"] == 0.0
    assert result.metrics["citation_validity"] == 1.0
    assert result.metrics["wrong_but_cited"] is False
    assert result.metrics["answer_type_mismatch"] is False
    assert result.metrics["partial_without_disclaimer"] is False
    assert result.metrics["faq_returned_for_link_lookup"] is False


@pytest.mark.asyncio
async def test_run_offline_eval_marks_hallucination_failures():
    case = OfflineEvalCase(
        name="pricing_case",
        input="price?",
        expected_decision="PASS",
        expected_chunk_ids=["chunk-price-1"],
        required_evidence=["numbers_units"],
        expected_answer_contains=["$10"],
        forbidden_answer_contains=["free forever"],
        hallucination_threshold=0.0,
    )
    output = AnswerOutput(
        decision="PASS",
        answer="Price is $10 monthly and free forever for premium users.",
        followup_questions=[],
        citations=[{"chunk_id": "chunk-price-1"}],
        confidence=0.8,
        debug=_debug_payload(
            evidence_ids=["chunk-price-1"],
            covered_requirements=["numbers_units"],
            hard_coverage={"numbers_units": True},
            unsupported_claims=["free forever for premium users"],
        ),
    )
    svc = _FakeAnswerService({case.input: output})

    summary, results = await run_offline_eval(svc, [case], run_id="testrun2")

    assert summary.case_count == 1
    assert summary.fail_count == 1
    assert results[0].passed is False
    assert results[0].metrics["hallucination_rate"] > 0.0
    assert results[0].metrics["forbidden_violations"]
    assert summary.wrong_but_cited_rate == 1.0


@pytest.mark.asyncio
async def test_evaluate_case_flags_answer_type_mismatch_and_faq_link_error():
    case = OfflineEvalCase(
        name="link_lookup_case",
        input="give me windows vps order link",
        expected_decision="PASS",
        expected_answer_type="direct_link",
        required_evidence=["transaction_link"],
        expected_answer_contains=["order"],
    )
    output = AnswerOutput(
        decision="PASS",
        answer="See this FAQ for details.",
        followup_questions=[],
        citations=[{"chunk_id": "chunk-faq-1", "doc_type": "faq", "source_url": "https://example.com/faq"}],
        confidence=0.8,
        debug=_debug_payload(
            evidence_ids=["chunk-faq-1"],
            evidence_rows=[
                {
                    "chunk_id": "chunk-faq-1",
                    "doc_type": "faq",
                    "source_url": "https://example.com/faq",
                }
            ],
        ),
    )
    svc = _FakeAnswerService({case.input: output})

    result = await evaluate_case(svc, case, run_id="testrun3")

    assert result.metrics["answer_type_mismatch"] is True
    assert result.metrics["faq_returned_for_link_lookup"] is True
    assert result.metrics["wrong_but_cited"] is True


@pytest.mark.asyncio
async def test_evaluate_case_flags_partial_without_disclaimer():
    case = OfflineEvalCase(
        name="partial_case",
        input="can you confirm setup and exact limits?",
        expected_decision="PASS",
        expected_answer_mode="partial",
        expected_answer_type="troubleshooting",
        required_evidence=["steps_structure"],
        expected_answer_contains=["step"],
    )
    output = AnswerOutput(
        decision="PASS",
        answer="Step 1: run this command. Step 2: restart service.",
        followup_questions=[],
        citations=[{"chunk_id": "chunk-howto-1"}],
        confidence=0.55,
        debug=_debug_payload(
            evidence_ids=["chunk-howto-1"],
            decision_router={"lane": "PASS_PARTIAL", "reason": "answerable_with_refinement"},
        ),
    )
    svc = _FakeAnswerService({case.input: output})

    result = await evaluate_case(svc, case, run_id="testrun4")

    assert result.metrics["partial_answer"] is True
    assert result.metrics["has_partial_disclaimer"] is False
    assert result.metrics["partial_without_disclaimer"] is True


@pytest.mark.asyncio
async def test_run_offline_eval_can_use_recorded_output_without_service():
    case = OfflineEvalCase(
        name="recorded_case",
        input="where is order link",
        expected_decision="PASS",
        expected_answer_type="direct_link",
        required_evidence=["transaction_link"],
        expected_answer_contains=["order"],
        recorded_output={
            "decision": "PASS",
            "answer": "Order here: https://example.com/order/windows-vps",
            "followup_questions": [],
            "citations": [
                {
                    "chunk_id": "trace-1",
                    "source_url": "https://example.com/order/windows-vps",
                    "doc_type": "pricing",
                }
            ],
            "confidence": 0.8,
            "debug": {
                "evidence_summary": [
                    {
                        "chunk_id": "trace-1",
                        "source_url": "https://example.com/order/windows-vps",
                        "doc_type": "pricing",
                    }
                ],
                "evidence_set": {"covered_requirements": ["transaction_link"]},
                "quality_report": {"hard_requirement_coverage": {"transaction_link": True}},
            },
        },
    )
    summary, results = await run_offline_eval(
        None,
        [case],
        run_id="testrun5",
        use_recorded_output=True,
    )

    assert summary.case_count == 1
    assert results[0].passed is True
    assert results[0].metrics["answer_type_mismatch"] is False
