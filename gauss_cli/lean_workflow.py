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

DEFAULT_NATIVE_LEAN_MODEL = "gpt-5.5"
NATIVE_LEAN_PROVIDER = "openai-codex"
NATIVE_LEAN_TOOLSET = "opengauss-lean"

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
    )


def _build_system_message(plan: NativeLeanWorkflowPlan) -> str:
    project = plan.project
    return "\n".join(
        [
            "You are the native OpenGauss Lean workflow agent.",
            "OpenGauss owns this workflow loop; do not delegate to external CLIs, MCP, or shell launchers.",
            f"Workflow: {plan.spec.canonical_command}",
            f"Project root: {project.root}",
            f"Lean root: {project.lean_root}",
            "Use only the available OpenGauss Lean tools: file tools, AXLE proof-service tools, and native Lean project tools.",
            "Use lean_project_status first when project state is unclear.",
            "Use lean_lake_build or lean_check_file for verification instead of invoking shell commands.",
            "Use lean_sorry_report before claiming a theorem or module is complete.",
            "When editing, preserve nearby project style and keep changes scoped to the requested Lean workflow.",
            "Finish with a concise status that names changed files and the strongest verification result obtained.",
        ]
    )


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
def _workflow_environment(project_root: Path):
    previous_cwd = Path.cwd()
    previous_terminal_cwd = os.environ.get("TERMINAL_CWD")
    os.environ["TERMINAL_CWD"] = str(project_root)
    os.chdir(project_root)
    try:
        yield
    finally:
        os.chdir(previous_cwd)
        if previous_terminal_cwd is None:
            os.environ.pop("TERMINAL_CWD", None)
        else:
            os.environ["TERMINAL_CWD"] = previous_terminal_cwd


def run_native_lean_workflow(
    command: str,
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    max_iterations: int = 90,
    session_id: str | None = None,
    session_db: Any = None,
    quiet_mode: bool = True,
    tool_progress_callback: Any = None,
) -> NativeLeanWorkflowResult:
    plan = prepare_native_lean_workflow(command, cwd=cwd, model=model)
    runtime = resolve_runtime_provider(requested=NATIVE_LEAN_PROVIDER)
    resolved_model = model or DEFAULT_NATIVE_LEAN_MODEL

    from run_agent import AIAgent

    with _workflow_environment(plan.project.root):
        agent = AIAgent(
            model=resolved_model,
            api_key=runtime.get("api_key", ""),
            base_url=runtime.get("base_url", ""),
            provider=NATIVE_LEAN_PROVIDER,
            api_mode="codex_responses",
            max_iterations=max_iterations,
            enabled_toolsets=[NATIVE_LEAN_TOOLSET],
            quiet_mode=quiet_mode,
            verbose_logging=False,
            platform="cli",
            session_id=session_id or f"lean-{uuid.uuid4().hex[:10]}",
            session_db=session_db,
            tool_progress_callback=tool_progress_callback,
        )
        result = agent.run_conversation(
            _build_user_message(plan),
            system_message=_build_system_message(plan),
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
