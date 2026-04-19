"""Tests for AXLE-backed Gauss tools."""

from __future__ import annotations

import asyncio
import json

from gauss_cli.lean_service import LeanProofServiceUnavailableError
import tools.axle_tool as axle_tool


class _FakeAxleService:
    def __init__(self):
        self.calls = []

    async def list_environments(self, *, timeout_seconds=None):
        self.calls.append(("environments", timeout_seconds))
        return [{"name": "lean-4.28.0", "description": "Lean + Mathlib"}]

    async def check(self, **kwargs):
        self.calls.append(("check", kwargs))
        return {"okay": True, "content": kwargs["content"]}


def test_axle_environments_tool_returns_count(monkeypatch):
    service = _FakeAxleService()
    monkeypatch.setattr(axle_tool, "_build_axle_service", lambda: service)

    result = json.loads(asyncio.run(axle_tool.axle_environments_tool(timeout_seconds=12)))

    assert result["success"] is True
    assert result["count"] == 1
    assert result["environments"][0]["name"] == "lean-4.28.0"


def test_axle_check_tool_uses_configured_environment_before_tool_argument(monkeypatch):
    service = _FakeAxleService()
    monkeypatch.setattr(axle_tool, "_build_axle_service", lambda: service)
    monkeypatch.setattr(axle_tool, "load_config", lambda: {})
    monkeypatch.setattr(
        axle_tool,
        "resolve_axle_environment",
        lambda config, *, explicit_environment=None: "config-env",
    )

    result = json.loads(
        asyncio.run(
            axle_tool.axle_check_tool(
                content="def x := 1",
                environment="explicit-env",
            )
        )
    )

    assert result["success"] is True
    assert result["environment"] == "config-env"
    assert service.calls[0][1]["environment"] == "config-env"


def test_axle_check_tool_returns_structured_errors(monkeypatch):
    class _FailingService:
        async def check(self, **kwargs):
            raise LeanProofServiceUnavailableError("AXLE unavailable")

    monkeypatch.setattr(axle_tool, "_build_axle_service", lambda: _FailingService())
    monkeypatch.setattr(axle_tool, "load_config", lambda: {})
    monkeypatch.setattr(
        axle_tool,
        "resolve_axle_environment",
        lambda config, *, explicit_environment=None: "lean-4.28.0",
    )

    result = json.loads(asyncio.run(axle_tool.axle_check_tool(content="def x := 1")))

    assert result["success"] is False
    assert result["error_type"] == "service_unavailable"
    assert "AXLE unavailable" in result["error"]
