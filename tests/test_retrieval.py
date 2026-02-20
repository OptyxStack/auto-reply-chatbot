"""Tests for retrieval merge logic."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.search.base import SearchChunk
from app.services.retrieval import RetrievalService


def test_merge_and_dedupe_by_chunk_id():
    """Merged results should dedupe by chunk_id, prefer higher score."""
    svc = RetrievalService()
    bm25 = [
        SearchChunk("c1", "d1", "text1", "url1", "policy", 0.8),
        SearchChunk("c2", "d1", "text2", "url1", "policy", 0.6),
    ]
    vector = [
        SearchChunk("c1", "d1", "text1", "url1", "policy", 0.95),  # duplicate, higher score
        SearchChunk("c3", "d2", "text3", "url2", "faq", 0.7),
    ]
    merged = svc._merge_and_dedupe(bm25, vector)
    assert len(merged) == 3  # c1, c2, c3
    c1 = next(m for m in merged if m.chunk_id == "c1")
    assert c1.score == 0.95  # prefer higher score


def test_query_rewrite():
    """Query rewrite returns same query for both (simple implementation)."""
    svc = RetrievalService()
    qr = svc._query_rewrite("refund policy")
    assert qr.keyword_query == "refund policy"
    assert qr.semantic_query == "refund policy"
