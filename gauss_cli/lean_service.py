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
_LEAN_DECL_RE = re.compile(
    r"^\s*(?:(?:private|protected|noncomputable|unsafe|partial)\s+)*"
    r"(theorem|lemma|def|abbrev|axiom|constant|class|structure|inductive|instance)\s+"
    r"([A-Za-z_][A-Za-z0-9_'.!?]*)\b"
)
_LEAN_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>.*?\.lean):(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?P<severity>error|warning|information|info):\s*(?P<message>.*)$"
)
_LEAN_IMPORT_RE = re.compile(r"^\s*import\s+(.+?)\s*$")
_LEAN_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z0-9_'.]+)\b")
_LEAN_END_RE = re.compile(r"^\s*end(?:\s+([A-Za-z0-9_'.]+))?\b")
_LEAN_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_'.!?]*")


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


def _decode_process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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


def _resolve_project_and_lean_file(
    *,
    path: str | Path,
    cwd: str | Path | None = None,
) -> tuple[Any, Path]:
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
    return project, target


def _module_name_for_path(path: Path, *, lean_root: Path) -> str:
    relative = path.relative_to(lean_root).with_suffix("")
    return ".".join(relative.parts)


def _line_text(lines: list[str], line: int) -> str:
    if line < 1 or line > len(lines):
        return ""
    return lines[line - 1]


def _extract_identifier_at(lines: list[str], line: int, column: int) -> str:
    text = _line_text(lines, line)
    if not text:
        return ""
    index = max(0, min(len(text), int(column or 1) - 1))
    for match in _LEAN_IDENTIFIER_RE.finditer(text):
        if match.start() <= index <= match.end():
            return match.group(0)
    return ""


def _imports_for_content(content: str) -> list[str]:
    imports: list[str] = []
    for line in content.splitlines():
        match = _LEAN_IMPORT_RE.match(line)
        if match:
            imports.extend(part.strip() for part in match.group(1).split() if part.strip())
    return imports


def _scan_lean_declarations(path: Path, *, lean_root: Path) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    namespace_stack: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        namespace_match = _LEAN_NAMESPACE_RE.match(stripped)
        if namespace_match:
            namespace_stack.extend(part for part in namespace_match.group(1).split(".") if part)
            continue

        end_match = _LEAN_END_RE.match(stripped)
        if end_match and namespace_stack:
            end_name = end_match.group(1)
            pop_count = len([part for part in end_name.split(".") if part]) if end_name else 1
            for _ in range(pop_count):
                if namespace_stack:
                    namespace_stack.pop()
            continue

        decl_match = _LEAN_DECL_RE.match(stripped)
        if not decl_match:
            continue
        kind, name = decl_match.groups()
        full_name = name.removeprefix("_root_.")
        if "." not in full_name and namespace_stack:
            full_name = ".".join([*namespace_stack, full_name])
        declarations.append(
            {
                "kind": kind,
                "name": name,
                "full_name": full_name,
                "path": str(path),
                "relative_path": str(path.relative_to(lean_root)),
                "module": _module_name_for_path(path, lean_root=lean_root),
                "line": line_number,
                "column": max(1, line.find(name) + 1),
                "signature": stripped,
            }
        )
    return declarations


def _find_enclosing_declaration(path: Path, *, lean_root: Path, line: int) -> dict[str, Any] | None:
    candidates = [
        decl for decl in _scan_lean_declarations(path, lean_root=lean_root)
        if int(decl["line"]) <= int(line or 1)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: int(item["line"]))


def parse_lean_diagnostics(output: str, *, target_path: Path | None = None) -> list[dict[str, Any]]:
    """Parse Lean diagnostic lines from `lake env lean` output."""
    diagnostics: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in str(output or "").splitlines():
        match = _LEAN_DIAGNOSTIC_RE.match(raw_line)
        if match:
            if current:
                diagnostics.append(current)
            path_text = match.group("path")
            current = {
                "path": path_text,
                "relative_path": (
                    Path(path_text).name
                    if target_path is None
                    else str(target_path.name if Path(path_text).name == target_path.name else Path(path_text).name)
                ),
                "line": int(match.group("line")),
                "column": int(match.group("column")),
                "severity": match.group("severity"),
                "message": match.group("message").strip(),
            }
            continue
        if current and raw_line.strip():
            current["message"] = f"{current['message']}\n{raw_line}".strip()
    if current:
        diagnostics.append(current)
    return diagnostics


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
            stdout=_decode_process_text(exc.stdout),
            stderr=_decode_process_text(exc.stderr),
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


def local_lean_lsp_diagnostics(
    *,
    path: str | Path,
    cwd: str | Path | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Return Lean diagnostics for a project file through controlled local checks."""
    project, target = _resolve_project_and_lean_file(path=path, cwd=cwd)
    check_payload = local_lean_check_file(
        path=target,
        cwd=project.root,
        timeout_seconds=timeout_seconds,
    )
    output = "\n".join(
        part for part in (check_payload.get("stdout", ""), check_payload.get("stderr", "")) if part
    )
    diagnostics = parse_lean_diagnostics(output, target_path=target)
    for item in diagnostics:
        try:
            diagnostic_path = Path(str(item.get("path", ""))).resolve()
            item["relative_path"] = str(diagnostic_path.relative_to(project.lean_root))
        except (OSError, ValueError):
            item["relative_path"] = str(target.relative_to(project.lean_root))
    return {
        "provider": "local",
        "source": "lake env lean",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "path": str(target),
        "relative_path": str(target.relative_to(project.lean_root)),
        "success": bool(check_payload.get("success")),
        "returncode": check_payload.get("returncode"),
        "timed_out": bool(check_payload.get("timed_out")),
        "diagnostic_count": len(diagnostics),
        "diagnostics": diagnostics,
        "stdout": check_payload.get("stdout", ""),
        "stderr": check_payload.get("stderr", ""),
    }


def local_lean_lsp_symbols(
    *,
    query: str,
    cwd: str | Path | None = None,
    path: str | Path | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search Lean declarations in the active project or a single file."""
    active_dir = Path(cwd or (Path(path).expanduser().parent if path else os.getcwd())).expanduser().resolve()
    project = discover_gauss_project(active_dir)
    if path is not None and str(path).strip():
        _, target = _resolve_project_and_lean_file(path=path, cwd=project.root)
        files = [target]
    else:
        files = _lean_file_paths(project.lean_root)
    needle = str(query or "").strip().lower()
    matches: list[dict[str, Any]] = []
    for lean_file in files:
        for decl in _scan_lean_declarations(lean_file, lean_root=project.lean_root):
            haystack = " ".join(
                [
                    str(decl.get("name", "")),
                    str(decl.get("full_name", "")),
                    str(decl.get("signature", "")),
                ]
            ).lower()
            if needle and needle not in haystack:
                continue
            matches.append(decl)
            if len(matches) >= max(1, int(limit or 50)):
                break
        if len(matches) >= max(1, int(limit or 50)):
            break
    return {
        "provider": "local",
        "source": "declaration_index",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "query": query,
        "symbol_count": len(matches),
        "symbols": matches,
    }


def local_lean_lsp_definition(
    *,
    path: str | Path,
    line: int,
    column: int,
    cwd: str | Path | None = None,
    symbol: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find likely definition sites for a symbol at a Lean cursor position."""
    project, target = _resolve_project_and_lean_file(path=path, cwd=cwd)
    lines = target.read_text(encoding="utf-8").splitlines()
    resolved_symbol = str(symbol or "").strip() or _extract_identifier_at(lines, int(line or 1), int(column or 1))
    if not resolved_symbol:
        return {
            "provider": "local",
            "source": "declaration_index",
            "project_root": str(project.root),
            "lean_root": str(project.lean_root),
            "path": str(target),
            "relative_path": str(target.relative_to(project.lean_root)),
            "line": int(line or 1),
            "column": int(column or 1),
            "symbol": "",
            "definition_count": 0,
            "definitions": [],
        }
    candidates = local_lean_lsp_symbols(
        query=resolved_symbol,
        cwd=project.root,
        limit=max(50, int(limit or 20) * 4),
    )["symbols"]
    exact: list[dict[str, Any]] = []
    suffix = f".{resolved_symbol}"
    for candidate in candidates:
        name = str(candidate.get("name", ""))
        full_name = str(candidate.get("full_name", ""))
        if name == resolved_symbol or full_name == resolved_symbol or full_name.endswith(suffix):
            exact.append(candidate)
    matches = exact or candidates
    return {
        "provider": "local",
        "source": "declaration_index",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "path": str(target),
        "relative_path": str(target.relative_to(project.lean_root)),
        "line": int(line or 1),
        "column": int(column or 1),
        "symbol": resolved_symbol,
        "definition_count": len(matches[: max(1, int(limit or 20))]),
        "definitions": matches[: max(1, int(limit or 20))],
    }


def local_lean_lsp_references(
    *,
    path: str | Path,
    line: int,
    column: int,
    cwd: str | Path | None = None,
    symbol: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Find project references for the symbol at a Lean cursor position."""
    project, target = _resolve_project_and_lean_file(path=path, cwd=cwd)
    lines = target.read_text(encoding="utf-8").splitlines()
    resolved_symbol = str(symbol or "").strip() or _extract_identifier_at(lines, int(line or 1), int(column or 1))
    references: list[dict[str, Any]] = []
    if resolved_symbol:
        suffix = f".{resolved_symbol}"
        max_refs = max(1, int(limit or 100))
        for lean_file in _lean_file_paths(project.lean_root):
            for line_number, line_text in enumerate(lean_file.read_text(encoding="utf-8").splitlines(), start=1):
                for match in _LEAN_IDENTIFIER_RE.finditer(line_text):
                    token = match.group(0)
                    if token != resolved_symbol and not token.endswith(suffix):
                        continue
                    references.append(
                        {
                            "path": str(lean_file),
                            "relative_path": str(lean_file.relative_to(project.lean_root)),
                            "module": _module_name_for_path(lean_file, lean_root=project.lean_root),
                            "line": line_number,
                            "column": match.start() + 1,
                            "text": line_text.strip(),
                        }
                    )
                    if len(references) >= max_refs:
                        break
                if len(references) >= max_refs:
                    break
            if len(references) >= max_refs:
                break
    return {
        "provider": "local",
        "source": "lexical_reference_index",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "path": str(target),
        "relative_path": str(target.relative_to(project.lean_root)),
        "line": int(line or 1),
        "column": int(column or 1),
        "symbol": resolved_symbol,
        "reference_count": len(references),
        "references": references,
    }


def local_lean_lsp_hover(
    *,
    path: str | Path,
    line: int,
    column: int,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Return compact hover/type-like information for a Lean cursor position."""
    project, target = _resolve_project_and_lean_file(path=path, cwd=cwd)
    lines = target.read_text(encoding="utf-8").splitlines()
    symbol = _extract_identifier_at(lines, int(line or 1), int(column or 1))
    definition_payload = local_lean_lsp_definition(
        path=target,
        line=int(line or 1),
        column=int(column or 1),
        cwd=project.root,
        symbol=symbol,
        limit=5,
    )
    definitions = definition_payload.get("definitions", [])
    return {
        "provider": "local",
        "source": "declaration_index",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "path": str(target),
        "relative_path": str(target.relative_to(project.lean_root)),
        "line": int(line or 1),
        "column": int(column or 1),
        "symbol": symbol,
        "hover": definitions[0].get("signature", "") if definitions else "",
        "definitions": definitions,
    }


def local_lean_lsp_goals(
    *,
    path: str | Path,
    line: int,
    column: int,
    cwd: str | Path | None = None,
    context_radius: int = 12,
) -> dict[str, Any]:
    """Return local proof-state context near a Lean cursor position.

    This is an OpenGauss-native fallback for useful goal-state affordances. It
    avoids MCP and shell access; diagnostics come from `lake env lean`, and the
    local goal context is derived from the enclosing declaration and source.
    """
    project, target = _resolve_project_and_lean_file(path=path, cwd=cwd)
    lines = target.read_text(encoding="utf-8").splitlines()
    line_number = max(1, int(line or 1))
    radius = max(1, int(context_radius or 12))
    start_line = max(1, line_number - radius)
    end_line = min(len(lines), line_number + radius)
    source_window = [
        {
            "line": index,
            "text": lines[index - 1],
            "cursor_line": index == line_number,
        }
        for index in range(start_line, end_line + 1)
    ]
    enclosing = _find_enclosing_declaration(target, lean_root=project.lean_root, line=line_number)
    diagnostics_payload = local_lean_lsp_diagnostics(path=target, cwd=project.root, timeout_seconds=30 * 60)
    relevant_diagnostics = [
        item for item in diagnostics_payload["diagnostics"]
        if abs(int(item.get("line", 0)) - line_number) <= radius
    ]
    sorries = [
        {**finding, "relative_path": str(target.relative_to(project.lean_root))}
        for finding in detect_sorries(target.read_text(encoding="utf-8"))
        if abs(int(finding["line"]) - line_number) <= radius
    ]
    return {
        "provider": "local",
        "source": "lean_check_and_source_context",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "path": str(target),
        "relative_path": str(target.relative_to(project.lean_root)),
        "module": _module_name_for_path(target, lean_root=project.lean_root),
        "line": line_number,
        "column": int(column or 1),
        "enclosing_declaration": enclosing,
        "source_window": source_window,
        "diagnostics": relevant_diagnostics,
        "sorries": sorries,
        "goal_state_available": False,
        "goal_state_note": (
            "Native OpenGauss goal context is derived from Lean diagnostics and local source. "
            "It does not call lean-lsp-mcp."
        ),
    }


def local_lean_proof_context(
    *,
    path: str | Path,
    cwd: str | Path | None = None,
    line: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Return a compact combined Lean proof context for workflow prompts."""
    project, target = _resolve_project_and_lean_file(path=path, cwd=cwd)
    content = target.read_text(encoding="utf-8")
    diagnostics = local_lean_lsp_diagnostics(path=target, cwd=project.root)
    sorry_findings = detect_sorries(content)
    payload: dict[str, Any] = {
        "provider": "local",
        "source": "combined_native_context",
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "path": str(target),
        "relative_path": str(target.relative_to(project.lean_root)),
        "module": _module_name_for_path(target, lean_root=project.lean_root),
        "imports": _imports_for_content(content),
        "diagnostics": diagnostics["diagnostics"],
        "diagnostic_count": diagnostics["diagnostic_count"],
        "sorries": sorry_findings,
        "sorry_count": len(sorry_findings),
        "symbols": _scan_lean_declarations(target, lean_root=project.lean_root),
    }
    if line is not None and column is not None:
        payload["goals"] = local_lean_lsp_goals(
            path=target,
            line=int(line),
            column=int(column),
            cwd=project.root,
        )
        payload["hover"] = local_lean_lsp_hover(
            path=target,
            line=int(line),
            column=int(column),
            cwd=project.root,
        )
        payload["definition"] = local_lean_lsp_definition(
            path=target,
            line=int(line),
            column=int(column),
            cwd=project.root,
        )
        payload["references"] = local_lean_lsp_references(
            path=target,
            line=int(line),
            column=int(column),
            cwd=project.root,
            limit=20,
        )
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
