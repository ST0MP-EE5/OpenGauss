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
    local_lean_lsp_definition,
    local_lean_lsp_diagnostics,
    local_lean_lsp_symbols,
    local_lean_proof_context,
    local_lean_lsp_references,
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


def test_resolve_axle_environment_infers_from_lean_toolchain_before_global_config(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")
    (project_root / "lean-toolchain").write_text("leanprover/lean4:v4.28.0\n", encoding="utf-8")
    initialize_gauss_project(project_root, name="Project Override")

    resolved = resolve_axle_environment(
        {"gauss": {"lean_service": {"environment": "config-env"}}},
        cwd=project_root,
    )

    assert resolved == "lean-4.28.0"


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


def test_native_lsp_symbols_and_definition_use_project_index(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")
    initialize_gauss_project(project_root, name="Demo")
    lean_file = project_root / "Demo.lean"
    lean_file.write_text(
        "\n".join(
            [
                "namespace Demo",
                "theorem helper : True := by trivial",
                "theorem target : True := by",
                "  exact helper",
                "end Demo",
            ]
        ),
        encoding="utf-8",
    )

    symbols = local_lean_lsp_symbols(query="helper", cwd=project_root)
    definition = local_lean_lsp_definition(path="Demo.lean", line=4, column=9, cwd=project_root)
    references = local_lean_lsp_references(path="Demo.lean", line=4, column=9, cwd=project_root)

    assert symbols["symbol_count"] == 1
    assert symbols["symbols"][0]["full_name"] == "Demo.helper"
    assert definition["symbol"] == "helper"
    assert definition["definitions"][0]["full_name"] == "Demo.helper"
    assert references["symbol"] == "helper"
    assert references["reference_count"] == 2


def test_native_lsp_diagnostics_parse_controlled_lean_check(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")
    initialize_gauss_project(project_root, name="Demo")
    lean_file = project_root / "Demo.lean"
    lean_file.write_text("theorem broken : True := by\n  exact False.elim ?h\n", encoding="utf-8")

    def fake_check_file(*, path, cwd=None, timeout_seconds=1800):
        del cwd, timeout_seconds
        return {
            "success": False,
            "returncode": 1,
            "timed_out": False,
            "stdout": "",
            "stderr": f"{Path(path)}:2:9: error: unsolved goals\ncase h\n⊢ False\n",
        }

    monkeypatch.setattr("gauss_cli.lean_service.local_lean_check_file", fake_check_file)

    diagnostics = local_lean_lsp_diagnostics(path="Demo.lean", cwd=project_root)

    assert diagnostics["success"] is False
    assert diagnostics["diagnostic_count"] == 1
    assert diagnostics["diagnostics"][0]["line"] == 2
    assert diagnostics["diagnostics"][0]["severity"] == "error"
    assert "unsolved goals" in diagnostics["diagnostics"][0]["message"]


def test_native_proof_context_combines_imports_sorries_and_cursor_context(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")
    initialize_gauss_project(project_root, name="Demo")
    lean_file = project_root / "Demo.lean"
    lean_file.write_text(
        "\n".join(
            [
                "import Mathlib",
                "namespace Demo",
                "theorem target : True := by",
                "  sorry",
                "end Demo",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "gauss_cli.lean_service.local_lean_check_file",
        lambda **kwargs: {"success": True, "returncode": 0, "timed_out": False, "stdout": "", "stderr": ""},
    )

    context = local_lean_proof_context(path="Demo.lean", cwd=project_root, line=4, column=4)

    assert context["imports"] == ["Mathlib"]
    assert context["sorry_count"] == 1
    assert context["symbols"][0]["full_name"] == "Demo.target"
    assert context["goals"]["goal_state_available"] is False
    assert context["hover"]["symbol"] == "sorry"


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
