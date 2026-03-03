"""Tests for evidence set builder (Workstream 3)."""

import pytest

from app.search.base import SearchChunk
from app.services.evidence_set_builder import build_evidence_set
from app.services.schemas import CandidatePool, QuerySpec, RetrievalPlan


def test_build_evidence_set_empty():
    """Empty reranked produces empty evidence set."""
    spec = QuerySpec(
        intent="informational",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    plan = RetrievalPlan(
        profile="generic_profile",
        attempt_index=1,
        reason="broad_hybrid",
        query_keyword="test",
        query_semantic="test",
    )
    es = build_evidence_set([], spec, plan)
    assert es.chunks == []
    assert es.primary_chunks == []
    assert es.supporting_chunks == []
    assert es.build_reason


def test_build_evidence_set_with_chunks():
    """Reranked chunks produce evidence set with primary/supporting split."""
    chunks = [
        (SearchChunk("c1", "d1", "text with http://link.com", "http://link.com", "faq", 0.9), 0.95),
        (SearchChunk("c2", "d2", "policy terms refund", "url2", "policy", 0.8), 0.85),
        (SearchChunk("c3", "d3", "step 1. first", "url3", "howto", 0.7), 0.75),
    ]
    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["has_any_url", "policy_language"],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
    )
    plan = RetrievalPlan(
        profile="policy_profile",
        attempt_index=1,
        reason="broad_hybrid",
        query_keyword="refund",
        query_semantic="refund",
    )
    es = build_evidence_set(chunks, spec, plan)
    assert len(es.chunks) == 3
    assert len(es.primary_chunks) <= 3
    assert es.covered_requirements or es.uncovered_requirements
    assert es.build_reason
    assert "policy_profile" in es.build_reason
