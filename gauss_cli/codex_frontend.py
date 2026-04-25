"""Codex frontend launcher for the OpenGauss Lean harness."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from gauss_cli.config import get_gauss_home, get_project_root
from gauss_cli.project import GaussProject, discover_gauss_project

DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_REASONING_EFFORT = "high"
DEFAULT_LEAN_LSP_MCP_SPEC = "lean-lsp-mcp"
QUERY_HARNESS_GUIDANCE = """\
Use the OpenGauss MCP tools as the primary interface for Lean/project work in this request.

Required behavior:
- Prefer `gauss_lean_project_status`, `gauss_lean_check_file`, `gauss_lean_lake_build`,
  `gauss_lean_sorry_report`, Lean LSP tools, AXLE tools, Comparator tools, and
  `gauss_lean_project_inspect` over shell commands.
- Do not call `gauss`, `lake`, `lean`, or ad hoc Python subprocesses from shell unless the user
  explicitly asks for raw shell behavior or an OpenGauss tool is unavailable.
- Keep proof/workflow ownership inside OpenGauss services; Codex is the frontend/model runtime.

User request:
"""


class CodexFrontendError(RuntimeError):
    """Raised when the Codex frontend cannot be prepared or launched."""


@dataclass(frozen=True)
class CodexFrontendPlan:
    """Resolved launch metadata for a project-scoped Codex frontend."""

    project: GaussProject
    active_cwd: Path
    codex_executable: str
    codex_home: Path
    config_path: Path
    instructions_path: Path
    lean4_skill_path: Path | None
    argv: tuple[str, ...]
    child_env: Mapping[str, str]
    model: str
    reasoning_effort: str

    def to_payload(self) -> dict[str, str]:
        return {
            "project": self.project.label,
            "project_root": str(self.project.root),
            "lean_root": str(self.project.lean_root),
            "active_cwd": str(self.active_cwd),
            "codex_home": str(self.codex_home),
            "config_path": str(self.config_path),
            "instructions_path": str(self.instructions_path),
            "lean4_skill_path": str(self.lean4_skill_path or ""),
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "argv": " ".join(self.argv),
        }


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def _project_manifest_exists(path: Path) -> bool:
    return (path / ".gauss" / "project.yaml").is_file()


def _repo_root_lean_project(cwd: Path) -> Path | None:
    repo_root = get_project_root()
    lean_root = repo_root / "Lean4"
    try:
        if cwd.resolve() != repo_root.resolve():
            return None
        if _project_manifest_exists(lean_root):
            return lean_root
    except OSError:
        return None

    child_projects = [
        child
        for child in repo_root.iterdir()
        if child.is_dir() and _project_manifest_exists(child)
    ]
    if len(child_projects) == 1:
        return child_projects[0]
    return None


def _resolve_requested_project(project_path: str | Path, *, cwd: Path) -> Path:
    raw = Path(project_path).expanduser()
    candidates = [raw if raw.is_absolute() else cwd / raw]
    repo_candidate = get_project_root() / raw
    if not raw.is_absolute() and repo_candidate not in candidates:
        candidates.append(repo_candidate)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return candidates[0].resolve()


def _active_project_cwd(cwd: Path, *, project_path: str | Path | None = None) -> Path:
    if project_path:
        return _resolve_requested_project(project_path, cwd=cwd)
    return _repo_root_lean_project(cwd) or cwd


def _copy_codex_auth(codex_home: Path, env: Mapping[str, str]) -> None:
    """Copy an existing stock Codex auth file into the isolated project profile."""
    configured = str(env.get("CODEX_HOME", "") or "").strip()
    source_home = Path(configured).expanduser() if configured else Path.home() / ".codex"
    source_auth = source_home / "auth.json"
    if not source_auth.is_file():
        return
    destination = codex_home / "auth.json"
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_auth, destination)
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass


def _lean4_skill_source(env: Mapping[str, str]) -> Path | None:
    override = str(env.get("GAUSS_LEAN4_SKILLS_PATH", "") or "").strip()
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(
        get_gauss_home()
        / "autoformalize"
        / "assets"
        / "lean4-skills"
        / "plugins"
        / "lean4"
        / "skills"
        / "lean4"
    )
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    return None


def _stage_lean4_skill(codex_home: Path, env: Mapping[str, str]) -> Path | None:
    source = _lean4_skill_source(env)
    if source is None:
        return None
    destination = codex_home / "skills" / "lean4"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def _lean_lsp_mcp_runner(env: Mapping[str, str]) -> tuple[str, ...] | None:
    explicit = str(env.get("GAUSS_LEAN_LSP_MCP_COMMAND", "") or "").strip()
    if explicit:
        return (explicit,)
    spec = str(env.get("GAUSS_LEAN_LSP_MCP_SPEC", "") or "").strip() or DEFAULT_LEAN_LSP_MCP_SPEC
    uvx = shutil.which("uvx", path=env.get("PATH"))
    if uvx:
        return (uvx, "--from", spec, "lean-lsp-mcp")
    uv = shutil.which("uv", path=env.get("PATH"))
    if uv:
        return (uv, "x", "--from", spec, "lean-lsp-mcp")
    return None


def _mcp_python_executable(env: Mapping[str, str]) -> str:
    explicit = str(env.get("GAUSS_MCP_PYTHON", "") or "").strip()
    if explicit:
        return str(Path(explicit).expanduser())
    venv_python = get_project_root() / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def _guided_query(query: str) -> str:
    return f"{QUERY_HARNESS_GUIDANCE}{query}"


def _write_codex_instructions(
    path: Path,
    *,
    project: GaussProject,
    active_cwd: Path,
    lean4_skill_path: Path | None,
    lean_lsp_mcp_enabled: bool,
) -> None:
    lines = [
        "# OpenGauss Codex Frontend",
        "",
        "You are Codex running inside the OpenGauss Lean harness.",
        "",
        "Ownership boundary:",
        "- Codex is the chat interface and model runtime.",
        "- OpenGauss owns the Lean project, AXLE, Comparator, workflow loop, benchmark retries, and artifacts.",
        "- MCP is only the local transport adapter between stock Codex CLI and OpenGauss services.",
        "",
        "Active project:",
        f"- Project: `{project.label}`",
        f"- Project root: `{project.root}`",
        f"- Lean root: `{project.lean_root}`",
        f"- Active working directory: `{active_cwd}`",
        "",
        "Use OpenGauss tools for Lean work:",
        "- The `opengauss` MCP server mirrors the canonical `opengauss-lean` harness surface for interactive use.",
        "- The Lean4 workflow skill is staged into this Codex profile when available; use it as the standing proof-engineering playbook.",
        "- Use `gauss_lean_project_status` before changing proofs when project state is unclear.",
        "- Use `gauss_read_file`, `gauss_search_files`, `gauss_write_file`, and `gauss_patch` for project file work.",
        "- Use `gauss_lean_lsp_diagnostics`, `gauss_lean_lsp_goals`, `gauss_lean_lsp_hover`, `gauss_lean_lsp_definition`, `gauss_lean_lsp_references`, and `gauss_lean_lsp_symbols` for Lean context.",
        "- Use `gauss_lean_lake_build`, `gauss_lean_check_file`, and `gauss_lean_sorry_report` for local verification.",
        "- Use AXLE tools when proof checking, repair, declaration extraction, normalization, or renaming helps.",
        "- Use `gauss_lean_project_inspect` for controlled read-only project/source inspection.",
        "- Treat `Challenge.lean` as immutable in benchmark-style tasks and write final proofs in `Solution.lean`.",
        "- Use `gauss_lean_comparator_check`; Comparator validity is the final proof-audit authority when a Challenge/Solution pair is present.",
        "- Do not introduce `axiom`, new `constant`, `unsafe`, theorem bypasses, or elaborator-level workarounds.",
        "- For complete proof workflows, prefer `gauss_autoformalize_prepare`, `gauss_autoformalize_run`, or `gauss_autoformalize_spawn` instead of reconstructing the harness loop manually.",
        "",
        "For normal project learning, prefer read-only Lean context tools before editing. For proof automation, keep the loop inside OpenGauss tools and artifacts.",
        "",
    ]
    if lean4_skill_path is not None:
        lines.extend([f"Lean4 skill path: `{lean4_skill_path}`", ""])
    if lean_lsp_mcp_enabled:
        lines.extend(
            [
                "The `lean-lsp` MCP server is also available for upstream Lean LSP goal-state behavior.",
                "Use it only for context; OpenGauss remains the owner of builds, Comparator audit, retries, and artifacts.",
                "",
            ]
        )
    _write_text_atomic(path, "\n".join(lines))


def _write_codex_config(
    path: Path,
    *,
    instructions_path: Path,
    project: GaussProject,
    model: str,
    reasoning_effort: str,
    mcp_python_executable: str,
    lean_lsp_mcp_runner: Sequence[str] | None,
) -> None:
    python_module = [mcp_python_executable, "-m", "gauss_cli.main", "mcp-server", "--transport", "stdio"]
    lines = [
        f"model = {_toml_string(model)}",
        f"model_reasoning_effort = {_toml_string(reasoning_effort)}",
        f"model_instructions_file = {_toml_string(str(instructions_path))}",
        "",
        "[mcp_servers.opengauss]",
        f"command = {_toml_string(python_module[0])}",
        f"args = [{', '.join(_toml_string(arg) for arg in python_module[1:])}]",
        "",
        "[mcp_servers.opengauss.env]",
        f"GAUSS_ACTIVE_PROJECT = {_toml_string(str(project.root))}",
        f"GAUSS_LEAN_ROOT = {_toml_string(str(project.lean_root))}",
        f"TERMINAL_CWD = {_toml_string(str(project.root))}",
        "",
    ]
    if lean_lsp_mcp_runner:
        runner = list(lean_lsp_mcp_runner)
        lines.extend(
            [
                "[mcp_servers.lean-lsp]",
                f"command = {_toml_string(runner[0])}",
                f"args = [{', '.join(_toml_string(arg) for arg in runner[1:])}]",
                "",
                "[mcp_servers.lean-lsp.env]",
                f"LEAN_PROJECT_PATH = {_toml_string(str(project.lean_root))}",
                "",
            ]
        )
    _write_text_atomic(path, "\n".join(lines))


def prepare_codex_frontend(
    *,
    cwd: str | Path | None = None,
    project_path: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    query: str | None = None,
    extra_args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> CodexFrontendPlan:
    base_env = dict(env or os.environ)
    active_cwd = _active_project_cwd(
        Path(cwd or os.getcwd()).expanduser().resolve(),
        project_path=project_path,
    )
    project = discover_gauss_project(active_cwd)
    codex_exe = shutil.which("codex", path=base_env.get("PATH"))
    if not codex_exe:
        raise CodexFrontendError("Codex CLI not found. Install the OpenAI Codex CLI, then run `gauss` again.")

    resolved_model = str(model or DEFAULT_CODEX_MODEL).strip() or DEFAULT_CODEX_MODEL
    resolved_reasoning = str(reasoning_effort or DEFAULT_CODEX_REASONING_EFFORT).strip().lower() or DEFAULT_CODEX_REASONING_EFFORT
    profile_root = project.runtime_dir / "codex-frontend"
    codex_home = profile_root / "codex-home"
    config_path = codex_home / "config.toml"
    instructions_path = codex_home / "opengauss-instructions.md"
    codex_home.mkdir(parents=True, exist_ok=True)

    _copy_codex_auth(codex_home, base_env)
    lean4_skill_path = _stage_lean4_skill(codex_home, base_env)
    lean_lsp_runner = _lean_lsp_mcp_runner(base_env)
    mcp_python = _mcp_python_executable(base_env)
    _write_codex_instructions(
        instructions_path,
        project=project,
        active_cwd=active_cwd,
        lean4_skill_path=lean4_skill_path,
        lean_lsp_mcp_enabled=lean_lsp_runner is not None,
    )
    _write_codex_config(
        config_path,
        instructions_path=instructions_path,
        project=project,
        model=resolved_model,
        reasoning_effort=resolved_reasoning,
        mcp_python_executable=mcp_python,
        lean_lsp_mcp_runner=lean_lsp_runner,
    )

    argv: list[str] = [codex_exe]
    if query:
        argv.extend(
            [
                "exec",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--dangerously-bypass-approvals-and-sandbox",
                _guided_query(query),
            ]
        )
    else:
        argv.append("--dangerously-bypass-approvals-and-sandbox")
    argv.extend(str(arg) for arg in (extra_args or ()))

    child_env = dict(base_env)
    child_env.update(
        {
            "CODEX_HOME": str(codex_home),
            "GAUSS_ACTIVE_PROJECT": str(project.root),
            "GAUSS_LEAN_ROOT": str(project.lean_root),
            "TERMINAL_CWD": str(project.root),
            "GAUSS_CODEX_FRONTEND": "1",
        }
    )
    return CodexFrontendPlan(
        project=project,
        active_cwd=active_cwd,
        codex_executable=codex_exe,
        codex_home=codex_home,
        config_path=config_path,
        instructions_path=instructions_path,
        lean4_skill_path=lean4_skill_path,
        argv=tuple(argv),
        child_env=child_env,
        model=resolved_model,
        reasoning_effort=resolved_reasoning,
    )


def launch_codex_frontend(
    *,
    cwd: str | Path | None = None,
    project_path: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    query: str | None = None,
    extra_args: Sequence[str] | None = None,
) -> int:
    plan = prepare_codex_frontend(
        cwd=cwd,
        project_path=project_path,
        model=model,
        reasoning_effort=reasoning_effort,
        query=query,
        extra_args=extra_args,
    )
    return subprocess.run(
        list(plan.argv),
        cwd=plan.project.root,
        env=dict(plan.child_env),
        check=False,
    ).returncode
