"""Tests for AXLE proof-service adapter and environment resolution."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from gauss_cli.lean_service import (
    AxleProofService,
    LeanProofServiceConfigurationError,
    LeanProofServiceUnavailableError,
    get_lean_service_provider,
    resolve_axle_environment,
)
from gauss_cli.project import initialize_gauss_project


def _write_project_lean_service(project_root: Path, *, provider: str = "", environment: str = "") -> None:
    manifest_path = project_root / ".gauss" / "project.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["lean_service"] = {
        "provider": provider,
        "environment": environment,
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_get_lean_service_provider_defaults_to_local(tmp_path):
    provider = get_lean_service_provider(
        {"gauss": {"lean_service": {"provider": "local"}}},
        cwd=tmp_path,
    )
    assert provider == "local"


def test_get_lean_service_provider_prefers_project_override(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "lakefile.lean").write_text("-- lean project\n", encoding="utf-8")
    initialize_gauss_project(project_root, name="Project Override")
    _write_project_lean_service(project_root, provider="axle", environment="project-env")

    provider = get_lean_service_provider(
        {"gauss": {"lean_service": {"provider": "local"}}},
        cwd=project_root,
    )

    assert provider == "axle"


def test_resolve_axle_environment_prefers_project_override_then_config_then_tool_arg(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "lakefile.lean").write_text("-- lean project\n", encoding="utf-8")
    initialize_gauss_project(project_root, name="Project Override")
    _write_project_lean_service(project_root, environment="project-env")

    resolved = resolve_axle_environment(
        {"gauss": {"lean_service": {"environment": "config-env"}}},
        explicit_environment="explicit-env",
        cwd=project_root,
    )

    assert resolved == "project-env"


def test_resolve_axle_environment_falls_back_to_config_before_tool_arg(tmp_path):
    resolved = resolve_axle_environment(
        {"gauss": {"lean_service": {"environment": "config-env"}}},
        explicit_environment="explicit-env",
        cwd=tmp_path,
    )

    assert resolved == "config-env"


def test_resolve_axle_environment_uses_tool_arg_when_no_default_exists(tmp_path):
    resolved = resolve_axle_environment(
        {"gauss": {"lean_service": {"environment": ""}}},
        explicit_environment="explicit-env",
        cwd=tmp_path,
    )

    assert resolved == "explicit-env"


def test_resolve_axle_environment_raises_when_unconfigured(tmp_path):
    with pytest.raises(LeanProofServiceConfigurationError):
        resolve_axle_environment(
            {"gauss": {"lean_service": {"environment": ""}}},
            cwd=tmp_path,
        )


def _install_fake_axle(
    monkeypatch,
    *,
    check_result=None,
    check_error=None,
    status_result=None,
    template_module=None,
):
    @dataclass
    class FakeCheckResponse:
        okay: bool
        content: str

    if template_module is None:
        class FakeAxleApiError(Exception):
            pass

        class FakeAxleInvalidArgument(FakeAxleApiError):
            pass

        class FakeAxleIsUnavailable(Exception):
            pass

        class FakeAxleRateLimitedError(FakeAxleApiError):
            pass

        class FakeAxleForbiddenError(FakeAxleApiError):
            pass

        class FakeAxleNotFoundError(FakeAxleApiError):
            pass

        class FakeAxleConflictError(FakeAxleApiError):
            pass

        class FakeAxleInternalError(FakeAxleApiError):
            pass

        class FakeAxleRuntimeError(FakeAxleApiError):
            pass
    else:
        FakeAxleApiError = template_module.AxleApiError
        FakeAxleInvalidArgument = template_module.AxleInvalidArgument
        FakeAxleIsUnavailable = template_module.AxleIsUnavailable
        FakeAxleRateLimitedError = template_module.AxleRateLimitedError
        FakeAxleForbiddenError = template_module.AxleForbiddenError
        FakeAxleNotFoundError = template_module.AxleNotFoundError
        FakeAxleConflictError = template_module.AxleConflictError
        FakeAxleInternalError = template_module.AxleInternalError
        FakeAxleRuntimeError = template_module.AxleRuntimeError

    class FakeAxleClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def check_status(self, timeout_seconds=60):
            if isinstance(status_result, Exception):
                raise status_result
            return status_result or {"status": "healthy", "timeout_seconds": timeout_seconds}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def check(self, **kwargs):
            if check_error is not None:
                raise check_error
            return check_result or FakeCheckResponse(okay=True, content=kwargs["content"])

    fake_axle = types.ModuleType("axle")
    fake_axle.AxleClient = FakeAxleClient
    fake_axle.AxleApiError = FakeAxleApiError
    fake_axle.AxleInvalidArgument = FakeAxleInvalidArgument
    fake_axle.AxleIsUnavailable = FakeAxleIsUnavailable
    fake_axle.AxleRateLimitedError = FakeAxleRateLimitedError
    fake_axle.AxleForbiddenError = FakeAxleForbiddenError
    fake_axle.AxleNotFoundError = FakeAxleNotFoundError
    fake_axle.AxleConflictError = FakeAxleConflictError
    fake_axle.AxleInternalError = FakeAxleInternalError
    fake_axle.AxleRuntimeError = FakeAxleRuntimeError

    monkeypatch.setitem(sys.modules, "axle", fake_axle)
    return fake_axle


@pytest.mark.asyncio
async def test_axle_proof_service_serializes_check_responses(monkeypatch):
    _install_fake_axle(monkeypatch)

    result = await AxleProofService().check(
        content="def x := 1",
        environment="lean-4.28.0",
    )

    assert result["okay"] is True
    assert result["content"] == "def x := 1"


def test_axle_proof_service_status_uses_sdk(monkeypatch):
    _install_fake_axle(monkeypatch, status_result={"status": "healthy", "version": "test"})

    result = AxleProofService().status(timeout_seconds=15)

    assert result == {"status": "healthy", "version": "test"}


@pytest.mark.asyncio
async def test_axle_proof_service_translates_availability_errors(monkeypatch):
    fake_axle = _install_fake_axle(monkeypatch)

    _install_fake_axle(
        monkeypatch,
        template_module=fake_axle,
        check_error=fake_axle.AxleIsUnavailable("https://axle.example", "offline"),
    )

    with pytest.raises(LeanProofServiceUnavailableError) as excinfo:
        await AxleProofService().check(
            content="def x := 1",
            environment="lean-4.28.0",
            timeout_seconds=30,
        )

    assert excinfo.value.code == "service_unavailable"


@pytest.mark.asyncio
async def test_axle_proof_service_translates_invalid_argument_errors(monkeypatch):
    fake_axle = _install_fake_axle(monkeypatch)
    _install_fake_axle(
        monkeypatch,
        template_module=fake_axle,
        check_error=fake_axle.AxleInvalidArgument("bad request"),
    )

    with pytest.raises(LeanProofServiceConfigurationError) as excinfo:
        await AxleProofService().check(
            content="def x := 1",
            environment="lean-4.28.0",
        )

    assert excinfo.value.code == "invalid_request"
