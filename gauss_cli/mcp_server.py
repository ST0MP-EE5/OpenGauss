"""OpenGauss MCP bridge for Codex and other external runtimes."""

from __future__ import annotations

import copy
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised via CLI guard
    FastMCP = None  # type: ignore[assignment]

from gauss_cli.config import load_config
from gauss_cli.lean_service import (
    AxleProofService,
    LeanProofServiceError,
    local_lake_build,
    local_lean_check_file,
    local_lean_lsp_definition,
    local_lean_lsp_diagnostics,
    local_lean_lsp_goals,
    local_lean_lsp_hover,
    local_lean_lsp_references,
    local_lean_lsp_symbols,
    local_lean_proof_context,
    local_lean_project_status,
    local_lean_sorry_report,
    resolve_axle_environment,
)
from gauss_cli.lean_comparator import local_lean_comparator_check
from gauss_cli.lean_workflow import (
    LeanWorkflowError,
    NATIVE_LEAN_TOOLSET,
    prepare_native_lean_workflow,
    run_native_lean_workflow,
)
from gauss_cli.project import (
    GaussProject,
    ProjectCommandError,
    ProjectManifestError,
    ProjectNotFoundError,
    ProjectTemplateUnavailableError,
    detect_blueprint_markers,
    discover_gauss_project,
    find_lean_project_root,
    format_project_summary,
    initialize_gauss_project,
    populate_project_from_template,
    resolve_template_source,
)
from gauss_state import SessionDB
from swarm_manager import SwarmManager, SwarmTask
from tools.file_tools import patch_tool, read_file_tool, search_tool, write_file_tool
from tools.lean_project_shell_tool import _lean_project_inspect_tool
from toolsets import resolve_toolset

SERVER_NAME = "opengauss"
_SENSITIVE_ENV_FRAGMENTS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "AUTH",
    "COOKIE",
)
_DEFAULT_RUN_TIMEOUT_SECONDS = 30 * 60
_DEFAULT_MAX_OUTPUT_CHARS = 20_000
_DEFAULT_SESSION_LIST_LIMIT = 20
_WORKFLOW_TOOL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("prove", "/prove", "Run the OpenGauss prove workflow."),
    ("draft", "/draft", "Run the OpenGauss draft workflow."),
    ("review", "/review", "Run the OpenGauss review workflow."),
    ("checkpoint", "/checkpoint", "Run the OpenGauss checkpoint workflow."),
    ("refactor", "/refactor", "Run the OpenGauss refactor workflow."),
    ("golf", "/golf", "Run the OpenGauss golf workflow."),
    ("autoprove", "/autoprove", "Run the OpenGauss autoprove workflow."),
    ("formalize", "/formalize", "Run the OpenGauss formalize workflow."),
)

CODEX_MCP_TOOL_ALIASES: dict[str, str] = {
    "read_file": "gauss_read_file",
    "write_file": "gauss_write_file",
    "patch": "gauss_patch",
    "search_files": "gauss_search_files",
    "lean_project_status": "gauss_lean_project_status",
    "lean_sorry_report": "gauss_lean_sorry_report",
    "lean_lake_build": "gauss_lean_lake_build",
    "lean_check_file": "gauss_lean_check_file",
    "lean_lsp_diagnostics": "gauss_lean_lsp_diagnostics",
    "lean_lsp_goals": "gauss_lean_lsp_goals",
    "lean_lsp_hover": "gauss_lean_lsp_hover",
    "lean_lsp_definition": "gauss_lean_lsp_definition",
    "lean_lsp_references": "gauss_lean_lsp_references",
    "lean_lsp_symbols": "gauss_lean_lsp_symbols",
    "lean_proof_context": "gauss_lean_proof_context",
    "lean_comparator_check": "gauss_lean_comparator_check",
    "lean_project_inspect": "gauss_lean_project_inspect",
}

for _tool_name in resolve_toolset(NATIVE_LEAN_TOOLSET):
    CODEX_MCP_TOOL_ALIASES.setdefault(_tool_name, _tool_name)


def _ensure_fastmcp() -> type[FastMCP]:
    if FastMCP is None:  # pragma: no cover - exercised via CLI guard
        raise RuntimeError(
            "Gauss MCP support requires the optional `mcp` dependency. "
            "Install it with `pip install -e .[mcp]`."
        )
    return FastMCP


def _resolve_cwd(cwd: str | None) -> Path:
    active_cwd = Path(cwd or os.getcwd()).expanduser().resolve()
    if not active_cwd.exists():
        raise ValueError(f"Working directory does not exist: {active_cwd}")
    if not active_cwd.is_dir():
        raise ValueError(f"Working directory is not a directory: {active_cwd}")
    return active_cwd


def _load_runtime_config() -> dict[str, Any]:
    return copy.deepcopy(load_config())


def _project_payload(project: GaussProject, *, active_cwd: Path | None = None) -> dict[str, Any]:
    return {
        "name": project.name,
        "label": project.label,
        "root": str(project.root),
        "gauss_dir": str(project.gauss_dir),
        "manifest_path": str(project.manifest_path),
        "lean_root": str(project.lean_root),
        "runtime_dir": str(project.runtime_dir),
        "cache_dir": str(project.cache_dir),
        "workflows_dir": str(project.workflows_dir),
        "kind": project.kind,
        "source_mode": project.source_mode,
        "template_source": project.template_source,
        "blueprint_markers": list(project.blueprint_markers),
        "summary": format_project_summary(project, active_cwd=active_cwd),
    }


def _resolve_target_path(path_value: str, *, cwd: str | None) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise ValueError("path must be a non-empty filesystem path.")
    base_dir = _resolve_cwd(cwd)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _redact_env_value(key: str, value: str) -> str:
    uppercase = key.upper()
    if any(fragment in uppercase for fragment in _SENSITIVE_ENV_FRAGMENTS):
        return "<redacted>"
    if len(value) > 400:
        return f"{value[:200]}...<{len(value) - 400} chars omitted>...{value[-200:]}"
    return value


def _env_override_payload(resolved_env: dict[str, str], base_env: dict[str, str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for key, value in resolved_env.items():
        if base_env.get(key) == value:
            continue
        overrides[key] = _redact_env_value(key, value)
    return dict(sorted(overrides.items()))


def _truncate_output(text: str, *, max_chars: int) -> tuple[str, bool, int]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False, 0
    if max_chars < 64:
        return text[:max_chars], True, len(text) - max_chars
    head = max_chars // 2
    tail = max_chars - head
    omitted = len(text) - max_chars
    truncated = f"{text[:head]}\n...[{omitted} chars omitted]...\n{text[-tail:]}"
    return truncated, True, omitted


def _compose_managed_workflow_command(frontend_command: str, user_instruction: str | None) -> str:
    payload = str(user_instruction or "").strip()
    if payload:
        return f"{frontend_command} {payload}"
    return frontend_command


def _session_db_path() -> Path:
    return Path(os.getenv("GAUSS_HOME", Path.home() / ".gauss")).expanduser() / "state.db"


def _open_session_db() -> SessionDB:
    return SessionDB(db_path=_session_db_path())


def _resolve_session_id_or_raise(db: SessionDB, session_id_or_prefix: str) -> str:
    raw = str(session_id_or_prefix or "").strip()
    if not raw:
        raise ValueError("session_id must be a non-empty session ID or unique prefix.")
    resolved = db.resolve_session_id(raw)
    if resolved is None:
        raise ValueError(f"Session not found or ambiguous: {raw}")
    return resolved


def _session_summary_payload(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": session.get("id"),
        "title": session.get("title"),
        "source": session.get("source"),
        "model": session.get("model"),
        "message_count": session.get("message_count"),
        "tool_call_count": session.get("tool_call_count"),
        "started_at": session.get("started_at"),
        "ended_at": session.get("ended_at"),
        "last_active": session.get("last_active"),
        "preview": session.get("preview", ""),
        "end_reason": session.get("end_reason"),
        "parent_session_id": session.get("parent_session_id"),
    }


def _swarm_task_payload(task: SwarmTask) -> dict[str, Any]:
    now = time.time()
    started = task.start_time
    ended = task.end_time
    duration_seconds: float | None = None
    if started is not None:
        duration_seconds = round((ended or now) - started, 3)
    return {
        "task_id": task.task_id,
        "description": task.description,
        "theorem": task.theorem,
        "workflow_kind": task.workflow_kind,
        "workflow_command": task.workflow_command,
        "project_name": task.project_name,
        "project_root": task.project_root,
        "working_dir": task.working_dir,
        "backend_name": task.backend_name,
        "status": task.status,
        "session_id": task.session_id,
        "progress": task.progress,
        "result": task.result,
        "error": task.error,
        "lean_status": task.lean_status,
        "start_time": started,
        "end_time": ended,
        "duration_seconds": duration_seconds,
        "interactive": task.pty_master_fd is not None,
    }


def gauss_project_status(cwd: str | None = None) -> dict[str, Any]:
    """Discover the nearest OpenGauss project for a working directory."""
    active_cwd = _resolve_cwd(cwd)
    try:
        project = discover_gauss_project(active_cwd)
    except (ProjectNotFoundError, ProjectManifestError) as exc:
        return {
            "cwd": str(active_cwd),
            "project_found": False,
            "message": str(exc),
        }

    return {
        "cwd": str(active_cwd),
        "project_found": True,
        "project": _project_payload(project, active_cwd=active_cwd),
    }


def gauss_project_init(
    cwd: str | None = None,
    *,
    name: str | None = None,
    lean_root: str | None = None,
) -> dict[str, Any]:
    """Initialize an OpenGauss project in a Lean repository."""
    active_cwd = _resolve_cwd(cwd)
    manifest_path = active_cwd / ".gauss" / "project.yaml"
    manifest_existed = manifest_path.exists()
    try:
        project = initialize_gauss_project(active_cwd, name=name, lean_root=lean_root)
    except ProjectCommandError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "cwd": str(active_cwd),
        "created": not manifest_existed,
        "project": _project_payload(project, active_cwd=active_cwd),
    }


def gauss_project_convert(
    cwd: str | None = None,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    """Register an existing Lean repository as an OpenGauss project."""
    active_cwd = _resolve_cwd(cwd)
    lean_root = find_lean_project_root(active_cwd)
    if lean_root is None:
        raise ValueError(
            "Lean project root not found. `/project convert` expects a Lean 4 repository."
        )

    manifest_path = lean_root / ".gauss" / "project.yaml"
    manifest_existed = manifest_path.exists()
    markers = detect_blueprint_markers(lean_root)
    try:
        project = initialize_gauss_project(
            lean_root,
            name=name,
            source_mode="convert-blueprint" if markers else "convert",
            blueprint_markers=markers,
        )
    except ProjectCommandError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "cwd": str(active_cwd),
        "created": not manifest_existed,
        "project": _project_payload(project, active_cwd=active_cwd),
        "blueprint_markers": list(markers),
    }


def gauss_project_create(
    path: str,
    *,
    cwd: str | None = None,
    name: str | None = None,
    template_source: str | None = None,
) -> dict[str, Any]:
    """Create a new OpenGauss project from the configured blueprint template."""
    target = _resolve_target_path(path, cwd=cwd)
    chosen_template = str(template_source or "").strip() or resolve_template_source(
        _load_runtime_config(),
        os.environ,
    )
    if not chosen_template:
        raise ValueError(
            "Blueprint project creation is blocked until a template source is configured."
        )

    try:
        populate_project_from_template(target, chosen_template)
        project = initialize_gauss_project(
            target,
            name=name or target.name,
            source_mode="template",
            template_source=chosen_template,
            blueprint_markers=detect_blueprint_markers(target),
        )
    except (ProjectCommandError, ProjectTemplateUnavailableError) as exc:
        raise ValueError(str(exc)) from exc

    return {
        "cwd": str(_resolve_cwd(cwd)),
        "target": str(target),
        "template_source": chosen_template,
        "created": True,
        "project": _project_payload(project, active_cwd=target),
    }


def _build_axle_service() -> AxleProofService:
    return AxleProofService()


def _axle_success_payload(operation: str, **payload: Any) -> dict[str, Any]:
    return {
        "success": True,
        "provider": "axle",
        "operation": operation,
        **payload,
    }


def _axle_error_payload(
    operation: str,
    exc: LeanProofServiceError,
    *,
    environment: str = "",
) -> dict[str, Any]:
    return {
        "success": False,
        "provider": "axle",
        "operation": operation,
        "environment": environment,
        "error": str(exc),
        "error_type": exc.code,
    }


def _resolve_axle_environment_for_cwd(
    *,
    cwd: str | None,
    environment: str | None,
) -> tuple[Path, str]:
    active_cwd = _resolve_cwd(cwd)
    resolved_environment = resolve_axle_environment(
        _load_runtime_config(),
        explicit_environment=environment,
        cwd=active_cwd,
    )
    return active_cwd, resolved_environment


async def axle_environments(timeout_seconds: float | None = None) -> dict[str, Any]:
    """List AXLE Lean environments exposed through the OpenGauss MCP bridge."""
    service = _build_axle_service()
    try:
        environments = await service.list_environments(timeout_seconds=timeout_seconds)
    except LeanProofServiceError as exc:
        return _axle_error_payload("environments", exc)
    return _axle_success_payload(
        "environments",
        environments=environments,
        count=len(environments),
    )


async def axle_check(
    content: str,
    *,
    environment: str | None = None,
    cwd: str | None = None,
    mathlib_options: bool | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Check Lean code with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.check(
            content=content,
            environment=resolved_environment,
            mathlib_options=mathlib_options,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("check", exc, environment=environment or "")
    return _axle_success_payload(
        "check",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


async def axle_verify_proof(
    formal_statement: str,
    content: str,
    *,
    environment: str | None = None,
    cwd: str | None = None,
    permitted_sorries: list[str] | None = None,
    mathlib_options: bool | None = None,
    use_def_eq: bool | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Verify a Lean proof with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.verify_proof(
            formal_statement=formal_statement,
            content=content,
            environment=resolved_environment,
            permitted_sorries=permitted_sorries,
            mathlib_options=mathlib_options,
            use_def_eq=use_def_eq,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("verify_proof", exc, environment=environment or "")
    return _axle_success_payload(
        "verify_proof",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


async def axle_extract_decls(
    content: str,
    *,
    environment: str | None = None,
    cwd: str | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Extract Lean declarations with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.extract_decls(
            content=content,
            environment=resolved_environment,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("extract_decls", exc, environment=environment or "")
    return _axle_success_payload(
        "extract_decls",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


async def axle_repair_proofs(
    content: str,
    *,
    environment: str | None = None,
    cwd: str | None = None,
    names: list[str] | None = None,
    indices: list[int] | None = None,
    repairs: list[str] | None = None,
    terminal_tactics: list[str] | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Repair Lean proofs with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.repair_proofs(
            content=content,
            environment=resolved_environment,
            names=names,
            indices=indices,
            repairs=repairs,
            terminal_tactics=terminal_tactics,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("repair_proofs", exc, environment=environment or "")
    return _axle_success_payload(
        "repair_proofs",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


async def axle_simplify_theorems(
    content: str,
    *,
    environment: str | None = None,
    cwd: str | None = None,
    names: list[str] | None = None,
    indices: list[int] | None = None,
    simplifications: list[str] | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Simplify Lean theorem proofs with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.simplify_theorems(
            content=content,
            environment=resolved_environment,
            names=names,
            indices=indices,
            simplifications=simplifications,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("simplify_theorems", exc, environment=environment or "")
    return _axle_success_payload(
        "simplify_theorems",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


async def axle_normalize(
    content: str,
    *,
    environment: str | None = None,
    cwd: str | None = None,
    normalizations: list[str] | None = None,
    failsafe: bool | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Normalize Lean code with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.normalize(
            content=content,
            environment=resolved_environment,
            normalizations=normalizations,
            failsafe=failsafe,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("normalize", exc, environment=environment or "")
    return _axle_success_payload(
        "normalize",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


async def axle_rename(
    content: str,
    declarations: dict[str, str],
    *,
    environment: str | None = None,
    cwd: str | None = None,
    ignore_imports: bool | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Rename Lean declarations with AXLE using project-aware environment resolution."""
    service = _build_axle_service()
    try:
        active_cwd, resolved_environment = _resolve_axle_environment_for_cwd(
            cwd=cwd,
            environment=environment,
        )
        result = await service.rename(
            content=content,
            declarations=declarations,
            environment=resolved_environment,
            ignore_imports=ignore_imports,
            timeout_seconds=timeout_seconds,
        )
    except LeanProofServiceError as exc:
        return _axle_error_payload("rename", exc, environment=environment or "")
    return _axle_success_payload(
        "rename",
        cwd=str(active_cwd),
        environment=resolved_environment,
        result=result,
    )


def _native_lean_error_payload(operation: str, exc: Exception) -> dict[str, Any]:
    error_type = exc.code if isinstance(exc, LeanProofServiceError) else type(exc).__name__
    return {
        "success": False,
        "provider": "local",
        "operation": operation,
        "error": str(exc),
        "error_type": error_type,
        "mcp_adapter": True,
    }


def _payload_from_json_tool(raw: str, *, operation: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _native_lean_error_payload(operation, exc)
    if not isinstance(payload, dict):
        return {
            "success": False,
            "provider": "local",
            "operation": operation,
            "error": f"Unexpected tool payload type: {type(payload).__name__}",
            "error_type": "invalid_payload",
            "mcp_adapter": True,
        }
    payload.setdefault("success", "error" not in payload)
    payload.setdefault("provider", "local")
    payload.setdefault("operation", operation)
    payload["mcp_adapter"] = True
    return payload


def _active_project_root_for_tool(cwd: str | None = None) -> Path:
    active_cwd = _resolve_cwd(cwd)
    try:
        return discover_gauss_project(active_cwd).root
    except Exception:
        return active_cwd


@contextmanager
def _mcp_file_tool_environment(cwd: str | None = None):
    project_root = _active_project_root_for_tool(cwd)
    previous_cwd = Path.cwd()
    previous_terminal_cwd = os.environ.get("TERMINAL_CWD")
    os.environ["TERMINAL_CWD"] = str(project_root)
    os.chdir(project_root)
    try:
        yield project_root, f"mcp-opengauss-{abs(hash(str(project_root)))}"
    finally:
        os.chdir(previous_cwd)
        if previous_terminal_cwd is None:
            os.environ.pop("TERMINAL_CWD", None)
        else:
            os.environ["TERMINAL_CWD"] = previous_terminal_cwd


def gauss_read_file(
    path: str,
    *,
    cwd: str | None = None,
    offset: int = 1,
    limit: int = 500,
) -> dict[str, Any]:
    """Adapter over the same file read tool available to the native Lean harness."""
    with _mcp_file_tool_environment(cwd) as (_project_root, task_id):
        raw = read_file_tool(path=path, offset=offset, limit=limit, task_id=task_id)
    return _payload_from_json_tool(raw, operation="read_file")


def gauss_write_file(
    path: str,
    content: str,
    *,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Adapter over the same file write tool available to the native Lean harness."""
    with _mcp_file_tool_environment(cwd) as (_project_root, task_id):
        raw = write_file_tool(path=path, content=content, task_id=task_id)
    return _payload_from_json_tool(raw, operation="write_file")


def gauss_patch(
    *,
    cwd: str | None = None,
    mode: str = "replace",
    path: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    replace_all: bool = False,
    patch: str | None = None,
) -> dict[str, Any]:
    """Adapter over the same targeted patch tool available to the native Lean harness."""
    with _mcp_file_tool_environment(cwd) as (_project_root, task_id):
        raw = patch_tool(
            mode=mode,
            path=path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            patch=patch,
            task_id=task_id,
        )
    return _payload_from_json_tool(raw, operation="patch")


def gauss_search_files(
    pattern: str,
    *,
    cwd: str | None = None,
    target: str = "content",
    path: str = ".",
    file_glob: str | None = None,
    limit: int = 50,
    offset: int = 0,
    output_mode: str = "content",
    context: int = 0,
) -> dict[str, Any]:
    """Adapter over the same file search tool available to the native Lean harness."""
    with _mcp_file_tool_environment(cwd) as (_project_root, task_id):
        raw = search_tool(
            pattern=pattern,
            target=target,
            path=path,
            file_glob=file_glob,
            limit=limit,
            offset=offset,
            output_mode=output_mode,
            context=context,
            task_id=task_id,
        )
    return _payload_from_json_tool(raw, operation="search_files")


def gauss_lean_project_status(*, cwd: str | None = None) -> dict[str, Any]:
    """Adapter over native Lean project status."""
    try:
        payload = local_lean_project_status(cwd=cwd)
    except Exception as exc:
        return _native_lean_error_payload("lean_project_status", exc)
    return {"success": True, "provider": "local", "operation": "lean_project_status", "mcp_adapter": True, **payload}


def gauss_lean_sorry_report(
    *,
    cwd: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Adapter over native Lean sorry/admit reporting."""
    try:
        payload = local_lean_sorry_report(cwd=cwd, path=path)
    except Exception as exc:
        return _native_lean_error_payload("lean_sorry_report", exc)
    return {"success": True, "provider": "local", "operation": "lean_sorry_report", "mcp_adapter": True, **payload}


def gauss_lean_lake_build(
    *,
    cwd: str | None = None,
    targets: list[str] | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Adapter over native controlled Lake build."""
    try:
        payload = local_lake_build(cwd=cwd, targets=targets, timeout_seconds=timeout_seconds)
    except Exception as exc:
        return _native_lean_error_payload("lean_lake_build", exc)
    return {"provider": "local", "operation": "lean_lake_build", "mcp_adapter": True, **payload}


def gauss_lean_check_file(
    path: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Adapter over native controlled Lean file check."""
    try:
        payload = local_lean_check_file(path=path, cwd=cwd, timeout_seconds=timeout_seconds)
    except Exception as exc:
        return _native_lean_error_payload("lean_check_file", exc)
    return {"provider": "local", "operation": "lean_check_file", "mcp_adapter": True, **payload}


def gauss_lean_project_inspect(
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 60,
    max_output_chars: int = 20000,
) -> dict[str, Any]:
    """Adapter over native controlled read-only project inspection."""
    raw = _lean_project_inspect_tool(
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
    )
    return _payload_from_json_tool(raw, operation="lean_project_inspect")


def gauss_lean_lsp_diagnostics(
    path: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Adapter over native Lean diagnostics service."""
    try:
        payload = local_lean_lsp_diagnostics(path=path, cwd=cwd, timeout_seconds=timeout_seconds)
    except Exception as exc:
        return _native_lean_error_payload("lean_lsp_diagnostics", exc)
    return {"success": True, "operation": "lean_lsp_diagnostics", "mcp_adapter": True, **payload}


def gauss_lean_lsp_goals(
    path: str,
    line: int,
    column: int,
    *,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Adapter over native Lean goal-context service."""
    try:
        payload = local_lean_lsp_goals(path=path, line=line, column=column, cwd=cwd)
    except Exception as exc:
        return _native_lean_error_payload("lean_lsp_goals", exc)
    return {"success": True, "operation": "lean_lsp_goals", "mcp_adapter": True, **payload}


def gauss_lean_lsp_hover(
    path: str,
    line: int,
    column: int,
    *,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Adapter over native Lean hover service."""
    try:
        payload = local_lean_lsp_hover(path=path, line=line, column=column, cwd=cwd)
    except Exception as exc:
        return _native_lean_error_payload("lean_lsp_hover", exc)
    return {"success": True, "operation": "lean_lsp_hover", "mcp_adapter": True, **payload}


def gauss_lean_lsp_definition(
    path: str,
    line: int,
    column: int,
    *,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Adapter over native Lean definition lookup."""
    try:
        payload = local_lean_lsp_definition(path=path, line=line, column=column, cwd=cwd)
    except Exception as exc:
        return _native_lean_error_payload("lean_lsp_definition", exc)
    return {"success": True, "operation": "lean_lsp_definition", "mcp_adapter": True, **payload}


def gauss_lean_lsp_references(
    path: str,
    line: int,
    column: int,
    *,
    cwd: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Adapter over native Lean reference search."""
    try:
        payload = local_lean_lsp_references(path=path, line=line, column=column, cwd=cwd, limit=limit)
    except Exception as exc:
        return _native_lean_error_payload("lean_lsp_references", exc)
    return {"success": True, "operation": "lean_lsp_references", "mcp_adapter": True, **payload}


def gauss_lean_lsp_symbols(
    query: str,
    *,
    cwd: str | None = None,
    path: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Adapter over native Lean symbol search."""
    try:
        payload = local_lean_lsp_symbols(query=query, cwd=cwd, path=path, limit=limit)
    except Exception as exc:
        return _native_lean_error_payload("lean_lsp_symbols", exc)
    return {"success": True, "operation": "lean_lsp_symbols", "mcp_adapter": True, **payload}


def gauss_lean_proof_context(
    path: str,
    *,
    cwd: str | None = None,
    line: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Adapter over native combined Lean proof context."""
    try:
        payload = local_lean_proof_context(path=path, cwd=cwd, line=line, column=column)
    except Exception as exc:
        return _native_lean_error_payload("lean_proof_context", exc)
    return {"success": True, "operation": "lean_proof_context", "mcp_adapter": True, **payload}


def gauss_lean_comparator_check(
    challenge_path: str,
    solution_path: str,
    *,
    cwd: str | None = None,
    theorem_names: list[str] | None = None,
    permitted_axioms: list[str] | None = None,
    comparator_binary: str | None = None,
    artifact_dir: str | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Adapter over native Comparator proof audit."""
    try:
        payload = local_lean_comparator_check(
            challenge_path=challenge_path,
            solution_path=solution_path,
            cwd=cwd,
            theorem_names=theorem_names,
            permitted_axioms=permitted_axioms,
            comparator_binary=comparator_binary,
            artifact_dir=artifact_dir,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return _native_lean_error_payload("lean_comparator_check", exc)
    return {"mcp_adapter": True, **payload}


def gauss_sessions_list(
    *,
    source: str | None = None,
    limit: int = _DEFAULT_SESSION_LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """List stored OpenGauss sessions with previews and activity metadata."""
    if limit <= 0:
        raise ValueError("limit must be positive.")
    if offset < 0:
        raise ValueError("offset must be non-negative.")

    db = _open_session_db()
    try:
        sessions = db.list_sessions_rich(source=source, limit=limit, offset=offset)
        total = db.session_count(source=source)
    finally:
        db.close()

    return {
        "db_path": str(_session_db_path()),
        "source": source,
        "limit": limit,
        "offset": offset,
        "total_sessions": total,
        "sessions": [_session_summary_payload(session) for session in sessions],
    }


def gauss_session_export(session_id: str) -> dict[str, Any]:
    """Export a stored OpenGauss session and its messages."""
    db = _open_session_db()
    try:
        resolved_id = _resolve_session_id_or_raise(db, session_id)
        exported = db.export_session(resolved_id)
    finally:
        db.close()

    assert exported is not None
    return {
        "db_path": str(_session_db_path()),
        "session": exported,
    }


def gauss_session_rename(session_id: str, title: str) -> dict[str, Any]:
    """Rename a stored OpenGauss session."""
    db = _open_session_db()
    try:
        resolved_id = _resolve_session_id_or_raise(db, session_id)
        try:
            renamed = db.set_session_title(resolved_id, title)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        session = db.get_session(resolved_id)
    finally:
        db.close()

    return {
        "db_path": str(_session_db_path()),
        "session_id": resolved_id,
        "updated": bool(renamed),
        "title": session.get("title") if session else None,
    }


def gauss_sessions_prune(
    *,
    older_than_days: int = 90,
    source: str | None = None,
) -> dict[str, Any]:
    """Prune ended sessions older than the requested age."""
    if older_than_days <= 0:
        raise ValueError("older_than_days must be positive.")

    db = _open_session_db()
    try:
        deleted = db.prune_sessions(older_than_days=older_than_days, source=source)
    finally:
        db.close()

    return {
        "db_path": str(_session_db_path()),
        "source": source,
        "older_than_days": older_than_days,
        "deleted_sessions": deleted,
    }


def gauss_swarm_list(*, status: str | None = None) -> dict[str, Any]:
    """List tracked OpenGauss swarm tasks."""
    manager = SwarmManager()
    tasks = manager.list_tasks(status=status)
    return {
        "status_filter": status,
        "task_count": len(tasks),
        "counts": manager.counts(),
        "tasks": [_swarm_task_payload(task) for task in tasks],
    }


def gauss_swarm_status(task_id: str) -> dict[str, Any]:
    """Inspect a single OpenGauss swarm task."""
    raw = str(task_id or "").strip()
    if not raw:
        raise ValueError("task_id must be a non-empty swarm task ID.")
    task = SwarmManager().get_task(raw)
    if task is None:
        raise ValueError(f"Swarm task not found: {raw}")
    return {
        "task": _swarm_task_payload(task),
    }


def gauss_swarm_cancel(task_id: str) -> dict[str, Any]:
    """Cancel a running OpenGauss swarm task."""
    raw = str(task_id or "").strip()
    if not raw:
        raise ValueError("task_id must be a non-empty swarm task ID.")
    manager = SwarmManager()
    task = manager.get_task(raw)
    if task is None:
        raise ValueError(f"Swarm task not found: {raw}")
    cancelled = manager.cancel(raw)
    refreshed = manager.get_task(raw)
    return {
        "task_id": raw,
        "cancelled": cancelled,
        "task": _swarm_task_payload(refreshed or task),
    }


def gauss_autoformalize_prepare(
    command: str,
    *,
    cwd: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    """Resolve a native OpenGauss Lean workflow command into project state."""
    if not str(command or "").strip():
        raise ValueError("command must be a non-empty Lean workflow command.")

    try:
        active_cwd = _resolve_cwd(cwd)
        plan = prepare_native_lean_workflow(command, cwd=active_cwd, toolset=NATIVE_LEAN_TOOLSET)
    except (LeanWorkflowError, ProjectCommandError, ProjectManifestError) as exc:
        raise ValueError(str(exc)) from exc

    return {
        **plan.to_payload(),
        "mode": "direct",
        "backend_name": "native",
        "ignored_backend": backend or "",
        "native_runner": {
            "provider": plan.provider,
            "model": plan.model,
            "api_mode": "codex_responses",
            "mcp_call_count": 0,
        },
        "project": _project_payload(plan.project, active_cwd=active_cwd),
        "managed_context": None,
        "handoff": None,
    }


def gauss_autoformalize_run(
    command: str,
    *,
    cwd: str | None = None,
    backend: str | None = None,
    timeout_seconds: int = _DEFAULT_RUN_TIMEOUT_SECONDS,
    max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
) -> dict[str, Any]:
    """Run a native OpenGauss Lean workflow command noninteractively."""
    if not str(command or "").strip():
        raise ValueError("command must be a non-empty Lean workflow command.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")

    try:
        active_cwd = _resolve_cwd(cwd)
        plan = prepare_native_lean_workflow(command, cwd=active_cwd, toolset=NATIVE_LEAN_TOOLSET)
    except (LeanWorkflowError, ProjectCommandError, ProjectManifestError) as exc:
        raise ValueError(str(exc)) from exc

    start = time.time()
    try:
        result = run_native_lean_workflow(command, cwd=active_cwd, toolset=NATIVE_LEAN_TOOLSET)
        stdout_text = result.final_response or ""
        stderr_text = result.error or ""
        timed_out = False
        returncode = 0 if result.success else 1
        error = result.error
    except LeanWorkflowError as exc:
        stdout_text = ""
        stderr_text = str(exc)
        timed_out = False
        returncode = None
        error = str(exc)
    except Exception as exc:
        stdout_text = ""
        stderr_text = str(exc)
        timed_out = False
        returncode = None
        error = str(exc)

    stdout_preview, stdout_truncated, stdout_omitted = _truncate_output(
        stdout_text,
        max_chars=max_output_chars,
    )
    stderr_preview, stderr_truncated, stderr_omitted = _truncate_output(
        stderr_text,
        max_chars=max_output_chars,
    )

    return {
        **plan.to_payload(),
        "mode": "direct",
        "backend_name": "native",
        "ignored_backend": backend or "",
        "project": _project_payload(plan.project, active_cwd=active_cwd),
        "managed_context": None,
        "handoff": None,
        "native_runner": {
            "provider": plan.provider,
            "model": plan.model,
            "api_mode": "codex_responses",
            "mcp_call_count": 0,
        },
        "execution": {
            "returncode": returncode,
            "timed_out": timed_out,
            "error": error,
            "duration_seconds": round(time.time() - start, 3),
            "stdout": stdout_preview,
            "stderr": stderr_preview,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "stdout_omitted_chars": stdout_omitted,
            "stderr_omitted_chars": stderr_omitted,
        },
    }


def _run_spawned_native_workflow(
    task: SwarmTask,
    *,
    cwd: str,
    command: str,
    max_output_chars: int,
) -> None:
    """Run a native Lean workflow in the background and summarize the result."""
    start = time.time()
    task.progress = "Running native OpenGauss Lean workflow"
    try:
        result = run_native_lean_workflow(command, cwd=cwd, toolset=NATIVE_LEAN_TOOLSET)
        stdout_preview, _, _ = _truncate_output(result.final_response or "", max_chars=max_output_chars)
        stderr_preview, _, _ = _truncate_output(result.error or "", max_chars=max_output_chars)
        if result.success:
            task.result = stdout_preview or "Native Lean workflow completed."
            task.progress = "Completed"
        else:
            task.status = "failed"
            task.error = result.error or "Native Lean workflow failed"
            task.result = stderr_preview or stdout_preview or None
            task.progress = "Exited with error"
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc)
        task.progress = "Unexpected error"
    finally:
        task.process = None
        task.end_time = time.time()


def gauss_autoformalize_spawn(
    command: str,
    *,
    cwd: str | None = None,
    backend: str | None = None,
    timeout_seconds: int = _DEFAULT_RUN_TIMEOUT_SECONDS,
    max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
) -> dict[str, Any]:
    """Spawn a native OpenGauss Lean workflow command as a swarm task."""
    if not str(command or "").strip():
        raise ValueError("command must be a non-empty Lean workflow command.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")

    try:
        active_cwd = _resolve_cwd(cwd)
        plan = prepare_native_lean_workflow(command, cwd=active_cwd, toolset=NATIVE_LEAN_TOOLSET)
    except (LeanWorkflowError, ProjectCommandError, ProjectManifestError) as exc:
        raise ValueError(str(exc)) from exc

    swarm = SwarmManager()
    task = swarm.spawn(
        theorem=plan.spec.workflow_args or plan.spec.command_text,
        description=plan.spec.workflow_args or plan.spec.command_text,
        workflow_kind=plan.spec.workflow_kind,
        workflow_command=plan.spec.command_text,
        project_name=plan.project.label,
        project_root=str(plan.project.root),
        working_dir=str(plan.project.root),
        backend_name="native",
        run_fn=_run_spawned_native_workflow,
        run_kwargs={
            "cwd": str(active_cwd),
            "command": plan.spec.command_text,
            "max_output_chars": max_output_chars,
        },
    )

    return {
        **plan.to_payload(),
        "mode": "direct",
        "backend_name": "native",
        "ignored_backend": backend or "",
        "project": _project_payload(plan.project, active_cwd=active_cwd),
        "managed_context": None,
        "handoff": None,
        "task": _swarm_task_payload(task),
    }


def _make_workflow_prepare(frontend_command: str):
    def _tool(
        user_instruction: str = "",
        *,
        cwd: str | None = None,
        backend: str | None = None,
    ) -> dict[str, Any]:
        return gauss_autoformalize_prepare(
            _compose_managed_workflow_command(frontend_command, user_instruction),
            cwd=cwd,
            backend=backend,
        )

    return _tool


def _make_workflow_run(frontend_command: str):
    def _tool(
        user_instruction: str = "",
        *,
        cwd: str | None = None,
        backend: str | None = None,
        timeout_seconds: int = _DEFAULT_RUN_TIMEOUT_SECONDS,
        max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
    ) -> dict[str, Any]:
        return gauss_autoformalize_run(
            _compose_managed_workflow_command(frontend_command, user_instruction),
            cwd=cwd,
            backend=backend,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )

    return _tool


def _make_workflow_spawn(frontend_command: str):
    def _tool(
        user_instruction: str = "",
        *,
        cwd: str | None = None,
        backend: str | None = None,
        timeout_seconds: int = _DEFAULT_RUN_TIMEOUT_SECONDS,
        max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
    ) -> dict[str, Any]:
        return gauss_autoformalize_spawn(
            _compose_managed_workflow_command(frontend_command, user_instruction),
            cwd=cwd,
            backend=backend,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )

    return _tool


for _workflow_name, _frontend_command, _description in _WORKFLOW_TOOL_SPECS:
    _prepare_name = f"gauss_{_workflow_name}_prepare"
    _run_name = f"gauss_{_workflow_name}_run"
    _spawn_name = f"gauss_{_workflow_name}_spawn"
    _prepare_tool = _make_workflow_prepare(_frontend_command)
    _prepare_tool.__name__ = _prepare_name
    _prepare_tool.__doc__ = f"Prepare the native `{_frontend_command}` workflow through OpenGauss."
    globals()[_prepare_name] = _prepare_tool
    _run_tool = _make_workflow_run(_frontend_command)
    _run_tool.__name__ = _run_name
    _run_tool.__doc__ = f"Run the native `{_frontend_command}` workflow through OpenGauss."
    globals()[_run_name] = _run_tool
    _spawn_tool = _make_workflow_spawn(_frontend_command)
    _spawn_tool.__name__ = _spawn_name
    _spawn_tool.__doc__ = f"Spawn the native `{_frontend_command}` workflow through OpenGauss."
    globals()[_spawn_name] = _spawn_tool


def build_server() -> FastMCP:
    """Build the OpenGauss MCP server instance."""
    server_cls = _ensure_fastmcp()
    server = server_cls(
        SERVER_NAME,
        instructions=(
            "OpenGauss project/workflow adapter. Use these tools to inspect or initialize "
            "a Gauss Lean project and to call native OpenGauss Lean workflows from "
            "an external MCP client."
        ),
    )

    server.tool(
        name="gauss_project_status",
        description="Discover the nearest OpenGauss project from a working directory.",
    )(gauss_project_status)
    server.tool(
        name="gauss_project_init",
        description="Initialize an OpenGauss project in the given Lean repository.",
    )(gauss_project_init)
    server.tool(
        name="gauss_project_convert",
        description="Register the current Lean repository as an OpenGauss project.",
    )(gauss_project_convert)
    server.tool(
        name="gauss_project_create",
        description="Create a new OpenGauss project from a configured blueprint template.",
    )(gauss_project_create)
    server.tool(
        name="gauss_read_file",
        description="Read a file through the OpenGauss harness file tool.",
    )(gauss_read_file)
    server.tool(
        name="gauss_write_file",
        description="Write a file through the OpenGauss harness file tool.",
    )(gauss_write_file)
    server.tool(
        name="gauss_patch",
        description="Patch files through the OpenGauss harness patch tool.",
    )(gauss_patch)
    server.tool(
        name="gauss_search_files",
        description="Search files through the OpenGauss harness search tool.",
    )(gauss_search_files)
    server.tool(
        name="axle_environments",
        description="List AXLE Lean environments available to the active OpenGauss runtime.",
    )(axle_environments)
    server.tool(
        name="axle_check",
        description="Check Lean code with AXLE using project-aware environment resolution.",
    )(axle_check)
    server.tool(
        name="axle_verify_proof",
        description="Verify a Lean proof with AXLE using project-aware environment resolution.",
    )(axle_verify_proof)
    server.tool(
        name="axle_extract_decls",
        description="Extract Lean declarations with AXLE using project-aware environment resolution.",
    )(axle_extract_decls)
    server.tool(
        name="axle_repair_proofs",
        description="Repair Lean proofs with AXLE using project-aware environment resolution.",
    )(axle_repair_proofs)
    server.tool(
        name="axle_simplify_theorems",
        description="Simplify Lean theorem proofs with AXLE using project-aware environment resolution.",
    )(axle_simplify_theorems)
    server.tool(
        name="axle_normalize",
        description="Normalize Lean code with AXLE using project-aware environment resolution.",
    )(axle_normalize)
    server.tool(
        name="axle_rename",
        description="Rename Lean declarations with AXLE using project-aware environment resolution.",
    )(axle_rename)
    server.tool(
        name="gauss_lean_project_status",
        description="Return native OpenGauss Lean project status.",
    )(gauss_lean_project_status)
    server.tool(
        name="gauss_lean_sorry_report",
        description="Report Lean sorry/admit findings through native OpenGauss services.",
    )(gauss_lean_sorry_report)
    server.tool(
        name="gauss_lean_lake_build",
        description="Run controlled native `lake build` for the active OpenGauss Lean project.",
    )(gauss_lean_lake_build)
    server.tool(
        name="gauss_lean_check_file",
        description="Run controlled native `lake env lean <file>` for the active OpenGauss Lean project.",
    )(gauss_lean_check_file)
    server.tool(
        name="gauss_lean_lsp_diagnostics",
        description="Return native Lean diagnostics for a file; MCP is only an adapter.",
    )(gauss_lean_lsp_diagnostics)
    server.tool(
        name="gauss_lean_lsp_goals",
        description="Return native Lean goal/context information at a cursor; MCP is only an adapter.",
    )(gauss_lean_lsp_goals)
    server.tool(
        name="gauss_lean_lsp_hover",
        description="Return native Lean hover information at a cursor; MCP is only an adapter.",
    )(gauss_lean_lsp_hover)
    server.tool(
        name="gauss_lean_lsp_definition",
        description="Find likely Lean definition sites through the native declaration index.",
    )(gauss_lean_lsp_definition)
    server.tool(
        name="gauss_lean_lsp_references",
        description="Find Lean symbol references through the native reference index.",
    )(gauss_lean_lsp_references)
    server.tool(
        name="gauss_lean_lsp_symbols",
        description="Search Lean declarations through the native declaration index.",
    )(gauss_lean_lsp_symbols)
    server.tool(
        name="gauss_lean_proof_context",
        description="Return combined native Lean proof context for a file.",
    )(gauss_lean_proof_context)
    server.tool(
        name="gauss_lean_comparator_check",
        description="Run native Comparator proof audit; MCP is only an adapter.",
    )(gauss_lean_comparator_check)
    server.tool(
        name="gauss_lean_project_inspect",
        description="Run controlled read-only project inspection through the OpenGauss Lean harness.",
    )(gauss_lean_project_inspect)
    server.tool(
        name="gauss_sessions_list",
        description="List stored OpenGauss sessions with previews and activity metadata.",
    )(gauss_sessions_list)
    server.tool(
        name="gauss_session_export",
        description="Export a stored OpenGauss session and its messages.",
    )(gauss_session_export)
    server.tool(
        name="gauss_session_rename",
        description="Rename a stored OpenGauss session.",
    )(gauss_session_rename)
    server.tool(
        name="gauss_sessions_prune",
        description="Prune old ended OpenGauss sessions.",
    )(gauss_sessions_prune)
    server.tool(
        name="gauss_swarm_list",
        description="List tracked OpenGauss swarm tasks.",
    )(gauss_swarm_list)
    server.tool(
        name="gauss_swarm_status",
        description="Inspect a single OpenGauss swarm task.",
    )(gauss_swarm_status)
    server.tool(
        name="gauss_swarm_cancel",
        description="Cancel a running OpenGauss swarm task.",
    )(gauss_swarm_cancel)
    server.tool(
        name="gauss_autoformalize_prepare",
        description=(
            "Resolve an OpenGauss Lean workflow command such as /prove or "
            "/autoformalize into native project/runtime state."
        ),
    )(gauss_autoformalize_prepare)
    server.tool(
        name="gauss_autoformalize_run",
        description=(
            "Run an OpenGauss native Lean workflow command and return structured results."
        ),
    )(gauss_autoformalize_run)
    server.tool(
        name="gauss_autoformalize_spawn",
        description=(
            "Spawn an OpenGauss native Lean workflow command as a background swarm task "
            "and return structured task metadata."
        ),
    )(gauss_autoformalize_spawn)
    for workflow_name, frontend_command, description in _WORKFLOW_TOOL_SPECS:
        server.tool(
            name=f"gauss_{workflow_name}_prepare",
            description=f"{description} Return native project/runtime state.",
        )(globals()[f"gauss_{workflow_name}_prepare"])
        server.tool(
            name=f"gauss_{workflow_name}_run",
            description=f"{description} Execute it noninteractively and return structured results.",
        )(globals()[f"gauss_{workflow_name}_run"])
        server.tool(
            name=f"gauss_{workflow_name}_spawn",
            description=f"{description} Spawn it as a background swarm task.",
        )(globals()[f"gauss_{workflow_name}_spawn"])
    return server


MCP_SERVER = build_server() if FastMCP is not None else None


def run_mcp_server(*, transport: str = "stdio") -> None:
    """Run the OpenGauss MCP server."""
    if MCP_SERVER is None:  # pragma: no cover - exercised via CLI guard
        _ensure_fastmcp()
    assert MCP_SERVER is not None
    MCP_SERVER.run(transport=transport)
