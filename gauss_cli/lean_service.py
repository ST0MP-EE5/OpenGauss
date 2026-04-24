"""Lean proof-service abstractions and AXLE adapter helpers."""

from __future__ import annotations

import importlib
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from gauss_cli.config import load_config
from gauss_cli.project import (
    ProjectManifestError,
    ProjectNotFoundError,
    discover_gauss_project,
    find_lean_project_root,
)

SUPPORTED_LEAN_SERVICE_PROVIDERS = {"local", "axle"}
DEFAULT_LEAN_SERVICE_PROVIDER = "local"
DEFAULT_AXLE_URL = "https://axle.axiommath.ai"
_LEAN_TOOLCHAIN_VERSION_RE = re.compile(r"^(?:leanprover/lean4:)?v?(\d+\.\d+\.\d+)$")
_SORRY_RE = re.compile(r"\b(?:sorry|admit)\b")
_LEAN_FILE_EXCLUDED_PARTS = {".git", ".lake", ".gauss", "__pycache__"}


class LeanProofServiceError(RuntimeError):
    """Base class for proof-service failures."""

    code = "lean_service_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code or self.code


class LeanProofServiceConfigurationError(LeanProofServiceError):
    """Raised when proof-service configuration is invalid or incomplete."""

    code = "configuration_error"


class LeanProofServiceUnavailableError(LeanProofServiceError):
    """Raised when the proof service cannot be reached."""

    code = "service_unavailable"


class LeanProofServicePermissionError(LeanProofServiceError):
    """Raised when the proof service denies access."""

    code = "permission_denied"


class LeanProofServiceNotFoundError(LeanProofServiceError):
    """Raised when the proof service reports a missing resource."""

    code = "not_found"


class LeanProofServiceConflictError(LeanProofServiceError):
    """Raised when the proof service reports a state conflict."""

    code = "conflict"


class LeanProofServiceRateLimitError(LeanProofServiceError):
    """Raised when the proof service rate-limits the request."""

    code = "rate_limited"


class LeanProofServiceRuntimeError(LeanProofServiceError):
    """Raised when the proof service cannot complete a valid request."""

    code = "runtime_error"


class LeanProofServiceInternalError(LeanProofServiceError):
    """Raised when the proof service reports an internal bug."""

    code = "internal_error"


@dataclass(frozen=True)
class LocalLeanCommandResult:
    """Structured result for local Lean project commands."""

    command: list[str]
    cwd: str
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error

    def to_payload(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "command": list(self.command),
            "cwd": self.cwd,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "error": self.error,
        }


class LeanProofService(ABC):
    """Abstract interface for Lean proof-service providers."""

    @abstractmethod
    def status(self, *, timeout_seconds: float = 60) -> dict[str, Any]:
        """Return provider health/status information."""

    @abstractmethod
    async def list_environments(self, *, timeout_seconds: float | None = None) -> list[dict[str, Any]]:
        """Return environments supported by the proof service."""

    @abstractmethod
    async def check(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        """Check Lean code."""

    @abstractmethod
    async def verify_proof(
        self,
        *,
        formal_statement: str,
        content: str,
        environment: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verify a proof."""

    @abstractmethod
    async def extract_decls(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        """Extract declarations from Lean code."""

    @abstractmethod
    async def repair_proofs(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        """Repair proofs in Lean code."""

    @abstractmethod
    async def simplify_theorems(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        """Simplify theorem proofs."""

    @abstractmethod
    async def normalize(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        """Normalize Lean code."""

    @abstractmethod
    async def rename(
        self,
        *,
        content: str,
        declarations: dict[str, str],
        environment: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Rename Lean declarations."""


def axle_sdk_available() -> bool:
    """Return whether the AXLE SDK can be imported."""
    try:
        importlib.import_module("axle")
    except ImportError:
        return False
    return True


def get_lean_service_provider(
    config: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> str:
    """Return the configured Lean proof-service provider."""
    project_settings = _get_project_lean_service_settings(cwd)
    project_provider = project_settings.get("provider")
    if project_provider:
        return project_provider

    cfg = _lean_service_config(config)
    provider = str(cfg.get("provider", DEFAULT_LEAN_SERVICE_PROVIDER) or DEFAULT_LEAN_SERVICE_PROVIDER).strip()
    if provider not in SUPPORTED_LEAN_SERVICE_PROVIDERS:
        allowed = ", ".join(sorted(SUPPORTED_LEAN_SERVICE_PROVIDERS))
        raise LeanProofServiceConfigurationError(
            f"Unsupported gauss.lean_service.provider {provider!r}. Expected one of: {allowed}."
        )
    return provider


def get_configured_axle_environment(
    config: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> str | None:
    """Return the configured default AXLE environment without using tool arguments."""
    project_settings = _get_project_lean_service_settings(cwd)
    if project_settings.get("environment"):
        return project_settings["environment"]

    inferred = _infer_axle_environment_from_toolchain(cwd)
    if inferred:
        return inferred

    cfg = _lean_service_config(config)
    configured = str(cfg.get("environment", "") or "").strip()
    return configured or None


def resolve_axle_environment(
    config: Mapping[str, Any] | None = None,
    *,
    explicit_environment: str | None = None,
    cwd: str | Path | None = None,
    require: bool = True,
) -> str | None:
    """Resolve an AXLE environment.

    Resolution order intentionally follows the v1 integration plan:
    project override -> user config default -> explicit tool argument.
    """
    configured = get_configured_axle_environment(config, cwd=cwd)
    if configured:
        return configured

    explicit = str(explicit_environment or "").strip()
    if explicit:
        return explicit

    if require:
        raise LeanProofServiceConfigurationError(
            "No AXLE environment is configured. Set gauss.lean_service.environment, "
            "add lean_service.environment to .gauss/project.yaml, or call axle_environments first."
        )
    return None


def serialize_service_result(value: Any) -> Any:
    """Convert proof-service responses into JSON-safe Python values."""
    if is_dataclass(value):
        return serialize_service_result(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): serialize_service_result(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_service_result(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_service_result(item) for item in value]
    return value


def _lean_file_paths(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.lean"):
        if any(part in _LEAN_FILE_EXCLUDED_PARTS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def detect_sorries(content: str) -> list[dict[str, Any]]:
    """Return line-level `sorry`/`admit` occurrences in Lean content."""
    findings: list[dict[str, Any]] = []
    for index, line in enumerate(str(content or "").splitlines(), start=1):
        if _SORRY_RE.search(line):
            findings.append({"line": index, "text": line.strip()})
    return findings


def local_lean_project_status(*, cwd: str | Path | None = None) -> dict[str, Any]:
    """Return local OpenGauss/Lean project status without using MCP or shell."""
    active_dir = Path(cwd or os.getcwd()).expanduser().resolve()
    project = discover_gauss_project(active_dir)
    lean_files = _lean_file_paths(project.lean_root)
    sorry_count = 0
    files_with_sorries: list[str] = []
    for path in lean_files:
        try:
            findings = detect_sorries(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if findings:
            sorry_count += len(findings)
            files_with_sorries.append(str(path.relative_to(project.lean_root)))

    return {
        "project": {
            "name": project.name,
            "root": str(project.root),
            "lean_root": str(project.lean_root),
            "manifest_path": str(project.manifest_path),
        },
        "lean_files": len(lean_files),
        "sorry_count": sorry_count,
        "files_with_sorries": files_with_sorries,
        "toolchain_environment": _infer_axle_environment_from_toolchain(active_dir),
    }


def local_lean_sorry_report(
    *,
    cwd: str | Path | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Return `sorry`/`admit` findings for a file or the active Lean project."""
    active_dir = Path(cwd or os.getcwd()).expanduser().resolve()
    project = discover_gauss_project(active_dir)
    if path is not None and str(path).strip():
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = project.lean_root / candidate
        targets = [candidate.resolve()]
    else:
        targets = _lean_file_paths(project.lean_root)

    files: list[dict[str, Any]] = []
    total = 0
    for target in targets:
        try:
            target.relative_to(project.lean_root)
        except ValueError as exc:
            raise LeanProofServiceConfigurationError(
                f"Lean file is outside project root: {target}",
                code="invalid_path",
            ) from exc
        if not target.is_file():
            raise LeanProofServiceNotFoundError(f"Lean file not found: {target}")
        findings = detect_sorries(target.read_text(encoding="utf-8"))
        total += len(findings)
        if findings:
            files.append(
                {
                    "path": str(target),
                    "relative_path": str(target.relative_to(project.lean_root)),
                    "sorries": findings,
                }
            )

    return {
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "sorry_count": total,
        "files": files,
    }


def _run_local_lean_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> LocalLeanCommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return LocalLeanCommandResult(
            command=command,
            cwd=str(cwd),
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
            error=f"Timed out after {timeout_seconds}s",
        )
    except OSError as exc:
        return LocalLeanCommandResult(
            command=command,
            cwd=str(cwd),
            returncode=None,
            stdout="",
            stderr="",
            error=str(exc),
        )
    return LocalLeanCommandResult(
        command=command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def local_lake_build(
    *,
    cwd: str | Path | None = None,
    targets: list[str] | tuple[str, ...] | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Run `lake build` for the active project using controlled argv execution."""
    active_dir = Path(cwd or os.getcwd()).expanduser().resolve()
    project = discover_gauss_project(active_dir)
    cleaned_targets = [str(target).strip() for target in (targets or []) if str(target).strip()]
    result = _run_local_lean_command(
        ["lake", "build", *cleaned_targets],
        cwd=project.lean_root,
        timeout_seconds=timeout_seconds,
    )
    payload = result.to_payload()
    payload["project_root"] = str(project.root)
    payload["lean_root"] = str(project.lean_root)
    payload["targets"] = cleaned_targets
    return payload


def local_lean_check_file(
    *,
    path: str | Path,
    cwd: str | Path | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Run `lake env lean <file>` on a project file using controlled argv execution."""
    active_dir = Path(cwd or os.getcwd()).expanduser().resolve()
    project = discover_gauss_project(active_dir)
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = project.lean_root / target
    target = target.resolve()
    try:
        target.relative_to(project.lean_root)
    except ValueError as exc:
        raise LeanProofServiceConfigurationError(
            f"Lean file is outside project root: {target}",
            code="invalid_path",
        ) from exc
    if not target.is_file():
        raise LeanProofServiceNotFoundError(f"Lean file not found: {target}")

    result = _run_local_lean_command(
        ["lake", "env", "lean", str(target)],
        cwd=project.lean_root,
        timeout_seconds=timeout_seconds,
    )
    payload = result.to_payload()
    payload["project_root"] = str(project.root)
    payload["lean_root"] = str(project.lean_root)
    payload["path"] = str(target)
    payload["relative_path"] = str(target.relative_to(project.lean_root))
    payload["sorries"] = detect_sorries(target.read_text(encoding="utf-8"))
    return payload


class AxleProofService(LeanProofService):
    """Lean proof-service adapter backed by AXLE."""

    def __init__(
        self,
        *,
        url: str | None = None,
        max_concurrency: int | None = None,
        base_timeout_seconds: float | None = None,
        api_key: str | None = None,
    ) -> None:
        self.url = url
        self.max_concurrency = max_concurrency
        self.base_timeout_seconds = base_timeout_seconds
        self.api_key = api_key

    def status(self, *, timeout_seconds: float = 60) -> dict[str, Any]:
        axle = _import_axle()
        client = self._create_client(axle)
        try:
            return serialize_service_result(client.check_status(timeout_seconds=timeout_seconds))
        except Exception as exc:
            raise self._translate_error(axle, exc) from exc

    async def list_environments(self, *, timeout_seconds: float | None = None) -> list[dict[str, Any]]:
        return await self._call("environments", timeout_seconds=timeout_seconds)

    async def check(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("check", content=content, environment=environment, **kwargs)

    async def verify_proof(
        self,
        *,
        formal_statement: str,
        content: str,
        environment: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._call(
            "verify_proof",
            formal_statement=formal_statement,
            content=content,
            environment=environment,
            **kwargs,
        )

    async def extract_decls(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("extract_decls", content=content, environment=environment, **kwargs)

    async def repair_proofs(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("repair_proofs", content=content, environment=environment, **kwargs)

    async def simplify_theorems(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("simplify_theorems", content=content, environment=environment, **kwargs)

    async def normalize(self, *, content: str, environment: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("normalize", content=content, environment=environment, **kwargs)

    async def rename(
        self,
        *,
        content: str,
        declarations: dict[str, str],
        environment: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._call(
            "rename",
            content=content,
            declarations=declarations,
            environment=environment,
            **kwargs,
        )

    async def _call(self, method_name: str, **kwargs: Any) -> Any:
        axle = _import_axle()
        client = self._create_client(axle)
        try:
            async with client as session:
                method = getattr(session, method_name)
                response = await method(**kwargs)
        except Exception as exc:
            raise self._translate_error(axle, exc) from exc
        return serialize_service_result(response)

    def _create_client(self, axle_module: Any) -> Any:
        return axle_module.AxleClient(
            url=self.url,
            max_concurrency=self.max_concurrency,
            base_timeout_seconds=self.base_timeout_seconds,
            api_key=self.api_key,
        )

    def _translate_error(self, axle_module: Any, exc: Exception) -> LeanProofServiceError:
        if isinstance(exc, LeanProofServiceError):
            return exc
        if isinstance(exc, axle_module.AxleIsUnavailable):
            return LeanProofServiceUnavailableError(str(exc))
        if isinstance(exc, axle_module.AxleRateLimitedError):
            return LeanProofServiceRateLimitError(str(exc))
        if isinstance(exc, axle_module.AxleForbiddenError):
            return LeanProofServicePermissionError(str(exc))
        if isinstance(exc, axle_module.AxleNotFoundError):
            return LeanProofServiceNotFoundError(str(exc))
        if isinstance(exc, axle_module.AxleConflictError):
            return LeanProofServiceConflictError(str(exc))
        if isinstance(exc, axle_module.AxleInvalidArgument):
            return LeanProofServiceConfigurationError(str(exc), code="invalid_request")
        if isinstance(exc, axle_module.AxleInternalError):
            return LeanProofServiceInternalError(str(exc))
        if isinstance(exc, axle_module.AxleRuntimeError):
            return LeanProofServiceRuntimeError(str(exc))
        if isinstance(exc, axle_module.AxleApiError):
            return LeanProofServiceRuntimeError(str(exc))
        return LeanProofServiceError(f"Unexpected AXLE error: {type(exc).__name__}: {exc}")


def _import_axle() -> Any:
    try:
        return importlib.import_module("axle")
    except ImportError as exc:
        raise LeanProofServiceConfigurationError(
            "AXLE SDK is not installed. Install axiom-axle>=1.2.0 to use AXLE-backed tools.",
            code="dependency_missing",
        ) from exc


def _lean_service_config(config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    resolved = dict(config or load_config())
    gauss_cfg = resolved.get("gauss")
    if not isinstance(gauss_cfg, Mapping):
        return {}
    lean_service_cfg = gauss_cfg.get("lean_service")
    if not isinstance(lean_service_cfg, Mapping):
        return {}
    return lean_service_cfg


def _get_project_lean_service_settings(cwd: str | Path | None) -> dict[str, str]:
    active_dir = Path(cwd or os.getcwd()).expanduser()
    try:
        project = discover_gauss_project(active_dir)
    except ProjectNotFoundError:
        return {}
    except ProjectManifestError as exc:
        raise LeanProofServiceConfigurationError(str(exc)) from exc

    payload = project.manifest.get("lean_service") or {}
    if not payload:
        return {}
    if not isinstance(payload, Mapping):
        raise LeanProofServiceConfigurationError(
            f"{project.manifest_path} has invalid lean_service metadata."
        )

    provider = str(payload.get("provider", "") or "").strip()
    environment = str(payload.get("environment", "") or "").strip()

    if provider and provider not in SUPPORTED_LEAN_SERVICE_PROVIDERS:
        allowed = ", ".join(sorted(SUPPORTED_LEAN_SERVICE_PROVIDERS))
        raise LeanProofServiceConfigurationError(
            f"{project.manifest_path} sets lean_service.provider={provider!r}; expected one of: {allowed}."
        )

    return {
        "provider": provider,
        "environment": environment,
    }


def _infer_axle_environment_from_toolchain(cwd: str | Path | None) -> str | None:
    """Infer an AXLE environment name from the nearest Lean toolchain file."""
    active_dir = Path(cwd or os.getcwd()).expanduser()
    lean_root: Path | None = None

    try:
        project = discover_gauss_project(active_dir)
    except ProjectNotFoundError:
        lean_root = find_lean_project_root(active_dir.resolve())
    except ProjectManifestError as exc:
        raise LeanProofServiceConfigurationError(str(exc)) from exc
    else:
        lean_root = project.lean_root

    if lean_root is None:
        return None

    toolchain_path = lean_root / "lean-toolchain"
    if not toolchain_path.is_file():
        return None

    try:
        toolchain_value = toolchain_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    match = _LEAN_TOOLCHAIN_VERSION_RE.match(toolchain_value)
    if not match:
        return None

    return f"lean-{match.group(1)}"
