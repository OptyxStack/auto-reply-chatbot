"""Tests for Evidence Quality Gate and Evidence Hygiene."""

import pytest

from app.search.base import EvidenceChunk
from app.services.evidence_hygiene import compute_hygiene
from app.services.evidence_quality import (
    evaluate_quality,
    infer_required_evidence,
    passes_quality_gate,
    QualityReport,
)
from app.services.retry_planner import plan_retry, RetryStrategy


def test_compute_hygiene_empty():
    sigs = compute_hygiene([])
    assert sigs.chunk_count == 0
    assert sigs.pct_chunks_with_url == 0.0
    assert sigs.median_content_density == 0.0


def test_compute_hygiene_with_chunks():
    chunks = [
        EvidenceChunk("c1", "Plan: $10/mo at https://example.com/order", "https://example.com", "pricing", 0.9, "Plan: $10/mo at https://example.com/order"),
        EvidenceChunk("c2", "Contact us. Copyright 2024.", "https://example.com/menu", "nav", 0.5, "Contact us. Copyright 2024."),
    ]
    sigs = compute_hygiene(chunks)
    assert sigs.chunk_count == 2
    assert sigs.pct_chunks_with_url >= 50
    assert sigs.pct_chunks_with_number_unit >= 50
    assert sigs.pct_chunks_boilerplate_gt_06 >= 0


def test_evaluate_quality_empty():
    report = evaluate_quality([], ["numbers_units"])
    assert report.quality_score == 0.0
    assert "missing_evidence" in report.missing_signals or report.missing_signals


def test_evaluate_quality_with_numbers():
    chunks = [
        EvidenceChunk("c1", "Price: $10/month USD", "https://x.com", "pricing", 0.9, "Price: $10/month USD"),
    ]
    report = evaluate_quality(chunks, ["numbers_units"])
    assert report.feature_scores["numbers_units"] >= 0.3
    assert report.quality_score > 0


def test_infer_required_evidence():
    assert "numbers_units" in infer_required_evidence("what is the price?")
    assert "transaction_link" in infer_required_evidence("link to order")
    assert "policy_language" in infer_required_evidence("refund policy")
    assert "steps_structure" in infer_required_evidence("how to setup")
    # Comparison queries (diff, compare)
    comp = infer_required_evidence("what diff from dedicated and vds?")
    assert "numbers_units" in comp
    assert "has_any_url" in comp


def test_passes_quality_gate_no_required():
    report = QualityReport(0.7, {"numbers_units": 0.5}, [], None, 0.1)
    assert passes_quality_gate(report, None)


def test_passes_quality_gate_uses_gate_pass_when_set():
    """When report.gate_pass is set (LLM v2), passes_quality_gate uses it directly."""
    report_pass = QualityReport(0.3, {}, ["missing_numbers"], None, 0.5, gate_pass=True)
    assert passes_quality_gate(report_pass, ["numbers_units"], hard_requirements=["numbers_units"])

    report_fail = QualityReport(0.8, {"numbers_units": 0.9}, [], None, 0.1, gate_pass=False)
    assert not passes_quality_gate(report_fail, None)


def test_hard_requirement_uses_sufficiency_not_average_threshold():
    """A single strong chunk can satisfy a hard requirement even when average ratio is low."""
    chunks = [
        EvidenceChunk(
            "c1",
            "Plan: $10/month USD",
            "https://example.com/pricing",
            "pricing",
            0.9,
            "Plan: $10/month USD",
        ),
    ]
    chunks.extend(
        EvidenceChunk(
            f"noise-{idx}",
            "General info without numbers",
            "https://example.com/info",
            "faq",
            0.2,
            "General info without numbers",
        )
        for idx in range(9)
    )

    report = evaluate_quality(
        chunks,
        ["numbers_units"],
        hard_requirements=["numbers_units"],
    )

    assert report.feature_scores["numbers_units"] < 0.3
    assert report.sufficiency_scores is not None
    assert report.sufficiency_scores["numbers_units"] == 1.0
    assert report.hard_requirement_coverage is not None
    assert report.hard_requirement_coverage["numbers_units"] is True
    assert passes_quality_gate(
        report,
        ["numbers_units"],
        hard_requirements=["numbers_units"],
    )


def test_plan_retry_attempt_1():
    assert plan_retry(["missing_numbers"], 1) is None


def test_plan_retry_attempt_2():
    strat = plan_retry(["missing_numbers"], 2)
    assert strat is not None
    assert isinstance(strat, RetryStrategy)
    assert "USD" in strat.boost_patterns or "$" in strat.boost_patterns


def test_plan_retry_boilerplate():
    strat = plan_retry(["boilerplate_risk"], 2)
    assert strat.context_expansion is True
    assert "menu" in strat.exclude_patterns or "copyright" in strat.exclude_patterns
