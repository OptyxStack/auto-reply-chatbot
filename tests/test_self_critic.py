"""Tests for self-critic service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.search.base import EvidenceChunk
from app.services.self_critic import critique


@pytest.mark.asyncio
async def test_self_critic_flags_completeness_issue(monkeypatch):
    monkeypatch.setattr(
        "app.services.self_critic.get_settings",
        lambda: type(
            "S",
            (),
            {"self_critic_enabled": True, "self_critic_require_completeness": True},
        )(),
    )
    mock_resp = type(
        "R",
        (),
        {
            "content": (
                '{"pass": false, "issues": ["Missing a major option from evidence"], '
                '"suggested_fix": "Compare the available options and cite both."}'
            )
        },
    )()
    with patch("app.services.self_critic.get_llm_gateway") as mock_gw:
        mock_gw.return_value.chat = AsyncMock(return_value=mock_resp)
        with patch("app.services.self_critic.get_model_for_task", return_value="gpt-4o-mini"):
            result = await critique(
                query="Which option should I choose?",
                answer="Option A is good.",
                citations=[{"chunk_id": "c1"}],
                evidence=[
                    EvidenceChunk("c1", "Option A details", "https://docs/a", "docs", 0.8, "Option A details"),
                    EvidenceChunk("c2", "Option B details", "https://docs/b", "docs", 0.75, "Option B details"),
                ],
                context={"answer_shape": "comparison"},
            )
    assert result is not None
    assert result.pass_ is False
    assert any("option" in issue.lower() for issue in result.issues)
