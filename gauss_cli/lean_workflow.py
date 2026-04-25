"""Native OpenGauss Lean workflow runner."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gauss_cli.project import GaussProject, discover_gauss_project, format_project_summary
from gauss_cli.runtime_provider import resolve_runtime_provider
from gauss_cli.lean_workflow_profiles import get_workflow_profile

DEFAULT_NATIVE_LEAN_MODEL = "gpt-5.5"
NATIVE_LEAN_PROVIDER = "openai-codex"
NATIVE_LEAN_TOOLSET = "opengauss-lean"
DEFAULT_LOCAL_LEAN_TOOLSET = NATIVE_LEAN_TOOLSET
DEFAULT_LEAN_REASONING_EFFORT = "high"

_WORKFLOW_ALIAS_MAP = {
    "/prove": ("prove", "/prove"),
    "/draft": ("draft", "/draft"),
    "/review": ("review", "/review"),
    "/checkpoint": ("checkpoint", "/checkpoint"),
    "/refactor": ("refactor", "/refactor"),
    "/golf": ("golf", "/golf"),
    "/autoprove": ("autoprove", "/autoprove"),
    "/auto-proof": ("autoprove", "/autoprove"),
    "/auto_proof": ("autoprove", "/autoprove"),
    "/formalize": ("formalize", "/formalize"),
    "/autoformalize": ("autoformalize", "/autoformalize"),
    "/auto-formalize": ("autoformalize", "/autoformalize"),
    "/auto_formalize": ("autoformalize", "/autoformalize"),
}


class LeanWorkflowError(RuntimeError):
    """Base class for native Lean workflow failures."""


class LeanWorkflowUsageError(LeanWorkflowError):
    """Raised when a Lean workflow command is malformed."""


@dataclass(frozen=True)
class LeanWorkflowSpec:
    workflow_kind: str
    frontend_command: str
    canonical_command: str
    workflow_args: str

    @property
    def command_text(self) -> str:
        return (
            self.canonical_command
            if not self.workflow_args
            else f"{self.canonical_command} {self.workflow_args}"
        )


@dataclass(frozen=True)
class NativeLeanWorkflowPlan:
    spec: LeanWorkflowSpec
    project: GaussProject
    active_cwd: Path
    provider: str
    model: str
    toolsets: tuple[str, ...] = (NATIVE_LEAN_TOOLSET,)

    def to_payload(self) -> dict[str, Any]:
        return {
            "cwd": str(self.active_cwd),
            "provider": self.provider,
            "model": self.model,
            "toolsets": list(self.toolsets),
            "workflow_kind": self.spec.workflow_kind,
            "frontend_command": self.spec.frontend_command,
            "canonical_command": self.spec.canonical_command,
            "command": self.spec.command_text,
            "user_instruction": self.spec.workflow_args,
            "project": {
                "name": self.project.name,
                "label": self.project.label,
                "root": str(self.project.root),
                "lean_root": str(self.project.lean_root),
                "manifest_path": str(self.project.manifest_path),
                "summary": format_project_summary(self.project, active_cwd=self.active_cwd),
            },
        }


@dataclass(frozen=True)
class NativeLeanWorkflowResult:
    plan: NativeLeanWorkflowPlan
    final_response: str
    messages: list[dict[str, Any]]
    error: str = ""

    @property
    def success(self) -> bool:
        return not self.error

    def to_payload(self) -> dict[str, Any]:
        return {
            **self.plan.to_payload(),
            "success": self.success,
            "final_response": self.final_response,
            "error": self.error,
            "message_count": len(self.messages),
        }


def parse_lean_workflow_command(command: str) -> LeanWorkflowSpec:
    text = str(command or "").strip()
    if not text.startswith("/"):
        raise LeanWorkflowUsageError(
            "Expected a Lean workflow command such as /prove, /autoprove, /formalize, or /autoformalize."
        )
    parts = text.split(maxsplit=1)
    command_name = parts[0].strip().lower()
    workflow_args = parts[1].strip() if len(parts) > 1 else ""
    if command_name == "/handoff":
        command_name = "/autoformalize"
    try:
        workflow_kind, canonical_command = _WORKFLOW_ALIAS_MAP[command_name]
    except KeyError as exc:
        raise LeanWorkflowUsageError(
            "Expected one of: /prove, /draft, /review, /checkpoint, /refactor, "
            "/golf, /autoprove, /formalize, /autoformalize."
        ) from exc
    return LeanWorkflowSpec(
        workflow_kind=workflow_kind,
        frontend_command=command_name,
        canonical_command=canonical_command,
        workflow_args=workflow_args,
    )


def compose_lean_workflow_command(frontend_command: str, user_instruction: str | None) -> str:
    payload = str(user_instruction or "").strip()
    return frontend_command if not payload else f"{frontend_command} {payload}"


def prepare_native_lean_workflow(
    command: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    toolset: str | None = None,
) -> NativeLeanWorkflowPlan:
    active_cwd = Path(cwd or os.getcwd()).expanduser().resolve()
    spec = parse_lean_workflow_command(command)
    project = discover_gauss_project(active_cwd)
    return NativeLeanWorkflowPlan(
        spec=spec,
        project=project,
        active_cwd=active_cwd,
        provider=NATIVE_LEAN_PROVIDER,
        model=model or DEFAULT_NATIVE_LEAN_MODEL,
        toolsets=(toolset or DEFAULT_LOCAL_LEAN_TOOLSET,),
    )


def _build_system_message(plan: NativeLeanWorkflowPlan, extra_guidance: list[str] | tuple[str, ...] | None = None) -> str:
    project = plan.project
    profile = get_workflow_profile(plan.spec.workflow_kind)
    lines = [
        "You are the OpenGauss Lean workflow agent.",
        "OpenGauss owns this workflow loop; do not delegate to external CLIs, MCP, or shell launchers.",
        f"Workflow: {plan.spec.canonical_command}",
        f"Native workflow profile: {profile.name} - {profile.summary}",
        f"Project root: {project.root}",
        f"Lean root: {project.lean_root}",
        f"Enabled toolset: {', '.join(plan.toolsets)}.",
        "Use only the available OpenGauss Lean tools: file tools, AXLE tools, Lean project tools, LSP-style context tools, controlled project inspection, and Comparator audit tools.",
        "Use lean_project_status first when project state is unclear.",
        "Use lean_proof_context, lean_lsp_diagnostics, lean_lsp_goals, lean_lsp_symbols, lean_lsp_definition, and lean_lsp_references for Lean context.",
        "Use lean_lake_build or lean_check_file for verification instead of invoking shell commands.",
        "Use lean_comparator_check as the final proof-audit tool for Challenge.lean/Solution.lean tasks.",
        "Use lean_sorry_report before claiming a theorem or module is complete.",
        "Use lean_project_inspect for controlled read-only project/source inspection when needed.",
        "When editing, preserve nearby project style and keep changes scoped to the requested Lean workflow.",
        "Do not introduce `axiom`, `constant`, `unsafe`, theorem bypasses, private synthetic axioms, or elaborator-level axiom injection.",
        "Comparator is the pass/fail authority for benchmark-style tasks; lake build plus zero sorries is not enough.",
        "Native profile guidance:",
        *[f"- {item}" for item in profile.guidance],
        "Finish with a concise status that names changed files and the strongest verification result obtained.",
    ]
    lines.append("If Comparator is unavailable or failing, keep working or report the exact blocking Comparator failure; do not claim success.")
    if extra_guidance:
        lines.extend(["Additional run guidance:", *[str(item) for item in extra_guidance if str(item).strip()]])
    return "\n".join(lines)


def _build_user_message(plan: NativeLeanWorkflowPlan) -> str:
    instruction = plan.spec.workflow_args or "Inspect the active Lean project and report the next useful proof step."
    return "\n".join(
        [
            f"Run native OpenGauss workflow `{plan.spec.canonical_command}`.",
            f"User instruction: {instruction}",
            "",
            "Do not use external managed backends. Work directly in the Lean project.",
        ]
    )


@contextmanager
def _workflow_environment(project_root: Path, extra_env: Mapping[str, str] | None = None):
    previous_cwd = Path.cwd()
    previous_terminal_cwd = os.environ.get("TERMINAL_CWD")
    previous_extra: dict[str, str | None] = {}
    os.environ["TERMINAL_CWD"] = str(project_root)
    for key, value in (extra_env or {}).items():
        previous_extra[key] = os.environ.get(key)
        os.environ[key] = str(value)
    os.chdir(project_root)
    try:
        yield
    finally:
        os.chdir(previous_cwd)
        if previous_terminal_cwd is None:
            os.environ.pop("TERMINAL_CWD", None)
        else:
            os.environ["TERMINAL_CWD"] = previous_terminal_cwd
        for key, previous_value in previous_extra.items():
            if previous_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value


def run_native_lean_workflow(
    command: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_iterations: int = 90,
    session_id: str | None = None,
    session_db: Any = None,
    quiet_mode: bool = True,
    skip_context_files: bool = False,
    skip_memory: bool = False,
    tool_progress_callback: Any = None,
    toolset: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    extra_system_guidance: list[str] | tuple[str, ...] | None = None,
) -> NativeLeanWorkflowResult:
    plan = prepare_native_lean_workflow(command, cwd=cwd, model=model, toolset=toolset)
    runtime = resolve_runtime_provider(requested=NATIVE_LEAN_PROVIDER)
    resolved_model = model or DEFAULT_NATIVE_LEAN_MODEL
    effective_extra_env = dict(extra_env or {})
    from run_agent import AIAgent

    with _workflow_environment(plan.project.root, extra_env=effective_extra_env):
        agent = AIAgent(
            model=resolved_model,
            api_key=runtime.get("api_key", ""),
            base_url=runtime.get("base_url", ""),
            provider=NATIVE_LEAN_PROVIDER,
            api_mode="codex_responses",
            max_iterations=max_iterations,
            enabled_toolsets=list(plan.toolsets),
            quiet_mode=quiet_mode,
            verbose_logging=False,
            platform="cli",
            session_id=session_id or f"lean-{uuid.uuid4().hex[:10]}",
            session_db=session_db,
            skip_context_files=skip_context_files,
            skip_memory=skip_memory,
            reasoning_config={
                "enabled": True,
                "effort": str(reasoning_effort or DEFAULT_LEAN_REASONING_EFFORT).strip().lower()
                or DEFAULT_LEAN_REASONING_EFFORT,
            },
            tool_progress_callback=tool_progress_callback,
        )
        result = agent.run_conversation(
            _build_user_message(plan),
            system_message=_build_system_message(plan, extra_guidance=extra_system_guidance),
            task_id=agent.session_id,
            persist_user_message=plan.spec.command_text,
        )

    if not isinstance(result, Mapping):
        return NativeLeanWorkflowResult(plan=plan, final_response=str(result), messages=[])
    final_response = str(result.get("final_response", "") or "")
    return NativeLeanWorkflowResult(
        plan=NativeLeanWorkflowPlan(
            spec=plan.spec,
            project=plan.project,
            active_cwd=plan.active_cwd,
            provider=NATIVE_LEAN_PROVIDER,
            model=resolved_model,
            toolsets=plan.toolsets,
        ),
        final_response=final_response,
        messages=list(result.get("messages") or []),
        error=str(result.get("error", "") or ""),
    )
