"""Compatibility tests for the managed autoformalize launcher module."""

from __future__ import annotations

import pytest

import gauss_cli.autoformalize as autoformalize


def _config(*, backend: str = "codex") -> dict:
    return {
        "gauss": {
            "autoformalize": {
                "backend": backend,
                "auth_mode": "auto",
            }
        }
    }


def test_managed_backend_surface_matches_upstream_with_native_compatibility():
    assert autoformalize.supported_autoformalize_backends() == ("codex",)
    assert autoformalize._resolve_backend_name(_config(backend="native"), {}) == "codex"
    assert autoformalize._resolve_backend_name(_config(backend="direct"), {}) == "codex"
    assert autoformalize._resolve_backend_name(_config(backend="openai_codex"), {}) == "codex"
    assert autoformalize._resolve_backend_name(
        _config(),
        {"GAUSS_AUTOFORMALIZE_BACKEND": "openai-codex"},
    ) == "codex"


def test_external_backend_is_no_longer_supported():
    with pytest.raises(autoformalize.AutoformalizeConfigError, match="gauss.autoformalize.backend"):
        autoformalize._resolve_backend_name(_config(backend="external"), {})


def test_claude_backend_is_no_longer_supported():
    with pytest.raises(autoformalize.AutoformalizeConfigError, match="gauss.autoformalize.backend"):
        autoformalize._resolve_backend_name(_config(backend="claude"), {})


def test_workflow_aliases_still_parse_for_legacy_callers():
    workflow = autoformalize._parse_managed_workflow_command("/autoformalize JordanCycleTheorem")

    assert workflow.workflow_kind == "autoformalize"
    assert workflow.canonical_command == "/autoformalize"
    assert workflow.backend_command == "/lean4:autoformalize JordanCycleTheorem"
    assert workflow.workflow_args == "JordanCycleTheorem"
