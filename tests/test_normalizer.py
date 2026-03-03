"""Tests for Phase 2 Normalizer."""

import pytest

from app.core.config import get_settings
from app.services.normalizer import normalize


@pytest.fixture(autouse=True)
def _reset_normalizer_settings(monkeypatch):
    monkeypatch.setenv("NORMALIZER_USE_LLM", "false")
    monkeypatch.delenv("NORMALIZER_DOMAIN_TERMS", raising=False)
    monkeypatch.setenv("NORMALIZER_QUERY_EXPANSION", "false")
    monkeypatch.setenv("NORMALIZER_SLOTS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_normalize_transactional():
    spec = await normalize("what is the price of VPS?")
    assert spec.intent == "transactional"
    assert spec.required_evidence == []
    assert spec.hard_requirements == ["numbers_units"]
    assert spec.soft_requirements == ["has_any_url"]
    assert not spec.is_ambiguous
    assert spec.keyword_queries
    assert spec.semantic_queries
    assert spec.keyword_queries == spec.semantic_queries
    assert spec.extraction_mode == "rule_primary"


@pytest.mark.asyncio
async def test_normalize_policy():
    spec = await normalize("refund policy")
    assert spec.intent == "policy"
    assert "policy_language" in spec.required_evidence
    assert "policy_language" in (spec.hard_requirements or [])
    assert spec.risk_level in ("low", "medium", "high")


@pytest.mark.asyncio
async def test_normalize_ambiguous_with_pasted_content():
    """User pastes our response and asks 'what diff from this?'."""
    spec = await normalize(
        "what diff from this? 1) Dedicated Server (bare-metal)... [bc387f35 | https://greencloudvps.com/dedicated-servers.php]",
        conversation_history=[
            {"role": "user", "content": "what diff from ur dedicated server and vds?"},
            {"role": "assistant", "content": "Dedicated Server (bare-metal)... VDS (Virtual)..."},
        ],
    )
    assert spec.is_ambiguous
    assert spec.intent == "ambiguous"
    assert spec.clarifying_questions


@pytest.mark.asyncio
async def test_normalize_ambiguous_short_query_with_long_assistant():
    """Short 'what diff from this?' with prior long assistant reply."""
    spec = await normalize(
        "what diff from this?",
        conversation_history=[
            {"role": "user", "content": "dedicated vs vds?"},
            {"role": "assistant", "content": "A" * 200},  # long prior answer
        ],
    )
    assert spec.is_ambiguous


@pytest.mark.asyncio
async def test_normalize_not_ambiguous_without_context():
    """Short query without pasted content or long history - not ambiguous."""
    spec = await normalize("what diff from this?")
    assert not spec.is_ambiguous


@pytest.mark.asyncio
async def test_normalize_entities_default_generic_mode():
    spec = await normalize("VPS pricing for Windows and Linux")
    assert spec.entities == []
    assert spec.resolved_slots == {}
    assert spec.config_overrides_applied == []


@pytest.mark.asyncio
async def test_normalize_compatibility_mode_uses_domain_overrides(monkeypatch):
    monkeypatch.setenv("NORMALIZER_DOMAIN_TERMS", "vps,windows,linux")
    monkeypatch.setenv("NORMALIZER_SLOTS_ENABLED", "true")
    monkeypatch.setenv("NORMALIZER_QUERY_EXPANSION", "true")
    get_settings.cache_clear()

    spec = await normalize("VPS pricing for Windows and Linux")

    assert "vps" in spec.entities
    assert "windows" in spec.entities
    assert "linux" in spec.entities
    assert spec.resolved_slots is not None
    assert spec.resolved_slots.get("product_type") == "vps"
    assert spec.resolved_slots.get("os") == "windows"
    assert "normalizer_domain_terms" in (spec.config_overrides_applied or [])
    assert "normalizer_query_expansion" in (spec.config_overrides_applied or [])
    assert "normalizer_slots_enabled" in (spec.config_overrides_applied or [])
    assert spec.keyword_queries[0] != spec.semantic_queries[0]
    assert "pricing" in spec.keyword_queries[0].lower()


@pytest.mark.asyncio
async def test_normalize_skip_retrieval_greetings():
    """Greetings/social need NO retrieval."""
    for q in ["hello", "hello]", "hi", "hey!", "thanks", "ok", "bye"]:
        spec = await normalize(q)
        assert spec.skip_retrieval, f"Expected skip_retrieval for {q!r}"
        assert spec.canned_response
        assert spec.intent == "social"


@pytest.mark.asyncio
async def test_normalize_no_skip_for_questions():
    """Actual questions need retrieval."""
    spec = await normalize("what is the price of VPS?")
    assert not spec.skip_retrieval
