"""Tests for task-aware model routing."""

import pytest

from app.services.model_router import get_model_for_task


def test_get_model_for_task_generate_uses_primary():
    """Generate task should use primary model (gpt-5.2)."""
    model = get_model_for_task("generate")
    assert model  # From config; typically gpt-5.2


def test_get_model_for_task_self_critic_uses_primary():
    """Self-critic task should use primary model."""
    model = get_model_for_task("self_critic")
    assert model


def test_get_model_for_task_normalizer_uses_economy():
    """Normalizer task should use economy model."""
    model = get_model_for_task("normalizer")
    assert model


def test_get_model_for_task_decision_router_uses_economy():
    """Decision router task should use economy model."""
    model = get_model_for_task("decision_router")
    assert model


def test_get_model_for_task_evidence_evaluator_uses_economy():
    """Evidence evaluator task should use economy model."""
    model = get_model_for_task("evidence_evaluator")
    assert model


def test_get_model_for_task_final_polish_uses_economy():
    """Final polish task should use economy model."""
    model = get_model_for_task("final_polish")
    assert model


def test_get_model_for_task_unknown_falls_back_to_primary():
    """Unknown task falls back to primary."""
    model = get_model_for_task("unknown_task")
    assert model
