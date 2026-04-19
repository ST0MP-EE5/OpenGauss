"""Lean proof-service abstractions and AXLE adapter helpers."""

from __future__ import annotations

import importlib
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from gauss_cli.config import load_config
from gauss_cli.project import ProjectManifestError, ProjectNotFoundError, discover_gauss_project

SUPPORTED_LEAN_SERVICE_PROVIDERS = {"local", "axle"}
DEFAULT_LEAN_SERVICE_PROVIDER = "local"
DEFAULT_AXLE_URL = "https://axle.axiommath.ai"


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
