"""Pytest fixtures."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_evidence_chunks():
    """Sample evidence chunks for reviewer tests."""
    from app.search.base import EvidenceChunk
    return [
        EvidenceChunk(
            chunk_id="chunk-1",
            snippet="Refunds are available within 30 days.",
            source_url="https://example.com/refund",
            doc_type="policy",
            score=0.9,
        ),
        EvidenceChunk(
            chunk_id="chunk-2",
            snippet="Contact support for billing issues.",
            source_url="https://example.com/billing",
            doc_type="faq",
            score=0.8,
        ),
    ]
