"""Tests for generate phase helpers (prior citations injection)."""

import pytest

from app.services.phases.generate import (
    _build_prior_citation_chunks,
    _extract_urls_from_text,
    _is_link_request_query,
)


def test_extract_urls_from_text():
    text = "See https://greencloudvps.com/windows-vps.php and https://example.com/order"
    urls = _extract_urls_from_text(text)
    assert len(urls) == 2
    assert "https://greencloudvps.com/windows-vps.php" in urls
    assert "https://example.com/order" in urls


def test_extract_urls_deduplicates():
    text = "https://a.com https://a.com https://b.com"
    urls = _extract_urls_from_text(text)
    assert urls == ["https://a.com", "https://b.com"]


def test_is_link_request_query():
    assert _is_link_request_query("page link please") is True
    assert _is_link_request_query("link please") is True
    assert _is_link_request_query("that link") is True
    assert _is_link_request_query("the link") is True
    assert _is_link_request_query("give me the url") is True
    assert _is_link_request_query("what is your refund policy") is False
    assert _is_link_request_query("") is False


def test_build_prior_citation_chunks_empty_history():
    assert _build_prior_citation_chunks([]) == []


def test_build_prior_citation_chunks_extracts_from_assistant():
    history = [
        {"role": "user", "content": "do you have windows vps in singapore"},
        {
            "role": "assistant",
            "content": "We offer Windows VPS. See https://greencloudvps.com/windows-vps.php and https://greencloudvps.com/managed-windows-vps.php",
        },
    ]
    chunks = _build_prior_citation_chunks(history)
    assert len(chunks) == 2
    assert chunks[0].source_url == "https://greencloudvps.com/windows-vps.php"
    assert chunks[1].source_url == "https://greencloudvps.com/managed-windows-vps.php"
    assert chunks[0].doc_type == "prior_citation"
    assert chunks[0].chunk_id.startswith("prior-")
