"""Tests for conversation history relevance check."""

import pytest

from app.services.phases.relevance_check import (
    _format_history_for_check,
    _parse_relevance_response,
)
from app.services.schemas import RelevanceCheckResult


def test_format_history_for_check_empty():
    assert _format_history_for_check([], 5) == "(empty)"


def test_format_history_for_check_truncates():
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "What about refund?"},
        {"role": "assistant", "content": "Refund policy is..."},
    ]
    out = _format_history_for_check(history, 2)
    assert "[user]" in out
    assert "[assistant]" in out
    assert "Hello" in out
    assert "refund" in out


def test_parse_relevance_response_valid():
    content = '{"relevant": false, "reason": "new topic", "relevant_turn_count": 0}'
    r = _parse_relevance_response(content)
    assert r is not None
    assert isinstance(r, RelevanceCheckResult)
    assert r.relevant is False
    assert r.reason == "new topic"
    assert r.relevant_turn_count == 0


def test_parse_relevance_response_relevant_all():
    content = '{"relevant": true, "reason": "same topic", "relevant_turn_count": "all"}'
    r = _parse_relevance_response(content)
    assert r is not None
    assert r.relevant is True
    assert r.relevant_turn_count == "all"


def test_parse_relevance_response_json_fence():
    content = '```json\n{"relevant": false, "reason": "x", "relevant_turn_count": 0}\n```'
    r = _parse_relevance_response(content)
    assert r is not None
    assert r.relevant is False


def test_parse_relevance_response_invalid_returns_none():
    assert _parse_relevance_response("") is None
    assert _parse_relevance_response("not json") is None
    assert _parse_relevance_response("{}") is not None  # minimal valid
