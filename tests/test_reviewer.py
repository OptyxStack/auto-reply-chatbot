"""Tests for reviewer gate."""

import pytest

from app.services.reviewer import ReviewerGate, ReviewerStatus


def test_reviewer_pass_with_citations(mock_evidence_chunks):
    """PASS with valid citations should pass reviewer."""
    gate = ReviewerGate()
    result = gate.review(
        decision="PASS",
        answer="You can get a refund within 30 days.",
        citations=[
            {"chunk_id": "chunk-1", "source_url": "https://example.com/refund", "doc_type": "policy"},
        ],
        evidence=mock_evidence_chunks,
        query="refund policy",
        confidence=0.9,
    )
    assert result.status == ReviewerStatus.PASS
    assert not result.reasons


def test_reviewer_fail_pass_without_citations(mock_evidence_chunks):
    """PASS without citations should fail to ASK_USER."""
    gate = ReviewerGate()
    result = gate.review(
        decision="PASS",
        answer="You can get a refund within 30 days.",
        citations=[],
        evidence=mock_evidence_chunks,
        query="refund policy",
        confidence=0.9,
    )
    assert result.status == ReviewerStatus.ASK_USER
    assert "citation" in result.reasons[0].lower()


def test_reviewer_fail_citation_not_in_evidence(mock_evidence_chunks):
    """Citation with chunk_id not in evidence should fail."""
    gate = ReviewerGate()
    result = gate.review(
        decision="PASS",
        answer="Refunds available.",
        citations=[{"chunk_id": "chunk-999", "source_url": "...", "doc_type": "policy"}],
        evidence=mock_evidence_chunks,
        query="refund",
        confidence=0.8,
    )
    assert result.status == ReviewerStatus.ASK_USER
    assert "not in evidence" in result.reasons[0].lower()


def test_reviewer_high_risk_requires_policy(mock_evidence_chunks):
    """High-risk query (refund) without policy citation should ESCALATE."""
    gate = ReviewerGate(require_policy_for_high_risk=True)
    result = gate.review(
        decision="PASS",
        answer="You may get a refund.",
        citations=[
            {"chunk_id": "chunk-2", "source_url": "https://example.com/billing", "doc_type": "faq"},
        ],
        evidence=mock_evidence_chunks,
        query="I want a refund",
        confidence=0.9,
    )
    assert result.status == ReviewerStatus.ESCALATE
    assert "policy" in result.reasons[0].lower()


def test_reviewer_retrieve_more_max_attempts(mock_evidence_chunks):
    """RETRIEVE_MORE at max attempts should become ASK_USER."""
    gate = ReviewerGate()
    result = gate.review(
        decision="RETRIEVE_MORE",
        answer="Some answer.",
        citations=[],
        evidence=mock_evidence_chunks,
        query="test",
        confidence=0.5,
        retrieval_attempt=2,
        max_attempts=2,
    )
    assert result.status == ReviewerStatus.ASK_USER
    assert "Max retrieval attempts" in result.reasons[0]
