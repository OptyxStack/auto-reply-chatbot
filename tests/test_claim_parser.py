"""Tests for claim parser (Workstream 5)."""

import pytest

from app.services.claim_parser import segment_claims, is_risky_claim, trim_unsupported_claims


def test_segment_claims_sentences():
    """Segment by sentence boundaries."""
    claims = segment_claims("First sentence. Second sentence. Third!")
    assert len(claims) == 3
    assert claims[0].text == "First sentence."
    assert claims[1].text == "Second sentence."
    assert claims[2].text == "Third!"


def test_segment_claims_bullets():
    """Segment bullet points."""
    claims = segment_claims("- Item one.\n- Item two.")
    assert len(claims) >= 2


def test_is_risky_claim_numbers():
    """Numbers and prices are risky."""
    assert is_risky_claim("The price is $100 per month.")
    assert is_risky_claim("Discount of 20%.")
    assert not is_risky_claim("You can contact support.")


def test_is_risky_claim_policy():
    """Policy phrases are risky."""
    assert is_risky_claim("According to our policy, refunds are available.")
    assert is_risky_claim("You are eligible for a refund.")
    assert not is_risky_claim("We offer great support.")


def test_trim_unsupported_claims():
    """Trim removes claims at given indices."""
    answer = "Safe sentence. Risky $100 claim. Another safe one."
    claims = segment_claims(answer)
    risky_idx = next(i for i, c in enumerate(claims) if "$100" in c.text)
    trimmed = trim_unsupported_claims(answer, [risky_idx])
    assert "$100" not in trimmed
    assert "Safe sentence" in trimmed
