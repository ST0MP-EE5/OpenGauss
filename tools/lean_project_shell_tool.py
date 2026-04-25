"""Controlled project-inspection command tool for OpenGauss parity runs."""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from gauss_cli.project import discover_gauss_project
from tools.registry import registry


_ALLOWED_COMMANDS = {
    "cat",
    "du",
    "find",
    "grep",
    "head",
    "lake",
    "ls",
    "pwd",
    "rg",
    "sed",
    "stat",
    "tail",
    "wc",
}
_FORBIDDEN_TOKENS = {
    "&&",
    "||",
    ";",
    "|",
    ">",
    ">>",
    "<",
    "<<",
    "`",
    "$(",
}
_MUTATING_COMMANDS = {
    "chmod",
    "chown",
    "cp",
    "git",
    "mkdir",
    "mv",
    "python",
    "python3",
    "rm",
    "rmdir",
    "sh",
    "touch",
}


def _json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validate_argv(command: str, project_root: Path) -> list[str]:
    if any(token in command for token in _FORBIDDEN_TOKENS):
        raise ValueError("Only a single read-only command is allowed; shell operators are blocked.")
    argv = shlex.split(command)
    if not argv:
        raise ValueError("Command cannot be empty.")
    executable = Path(argv[0]).name
    if executable in _MUTATING_COMMANDS or executable not in _ALLOWED_COMMANDS:
        raise ValueError(f"Command {executable!r} is not allowed for parity inspection.")
    if executable == "lake" and argv[1:4] not in (["env", "lean", "--version"], ["env", "lean", "--help"]):
        raise ValueError("The parity inspection tool only permits `lake env lean --version|--help`.")
    for arg in argv[1:]:
        if arg.startswith("-") or "/" not in arg:
            continue
        candidate = (project_root / arg).resolve() if not Path(arg).is_absolute() else Path(arg).resolve()
        if not _inside(project_root, candidate):
            raise ValueError(f"Path escapes project root: {arg}")
    return argv


def _lean_project_inspect_tool(
    *,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = 60,
    max_output_chars: int = 20000,
) -> str:
    start = time.time()
    try:
        active_dir = Path(cwd or ".").expanduser().resolve()
        project = discover_gauss_project(active_dir)
        workdir = active_dir if _inside(project.root, active_dir) else project.root
        argv = _validate_argv(command, project.root)
        completed = subprocess.run(
            argv,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds or 60)),
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        truncated = False
        limit = max(1000, int(max_output_chars or 20000))
        if len(stdout) > limit:
            stdout = stdout[:limit] + "\n...[truncated]..."
            truncated = True
        if len(stderr) > limit:
            stderr = stderr[:limit] + "\n...[truncated]..."
            truncated = True
        return _json_payload(
            {
                "success": completed.returncode == 0,
                "provider": "local",
                "operation": "lean_project_inspect",
                "command": argv,
                "cwd": str(workdir),
                "project_root": str(project.root),
                "returncode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
                "truncated": truncated,
                "duration_seconds": round(time.time() - start, 3),
                "mcp_call_count": 0,
            }
        )
    except subprocess.TimeoutExpired as exc:
        return _json_payload(
            {
                "success": False,
                "provider": "local",
                "operation": "lean_project_inspect",
                "command": command,
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "timed_out": True,
                "error": f"Timed out after {timeout_seconds}s",
                "duration_seconds": round(time.time() - start, 3),
                "mcp_call_count": 0,
            }
        )
    except Exception as exc:
        return _json_payload(
            {
                "success": False,
                "provider": "local",
                "operation": "lean_project_inspect",
                "command": command,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "mcp_call_count": 0,
            }
        )


LEAN_PROJECT_INSPECT_SCHEMA = {
    "name": "lean_project_inspect",
    "description": (
        "Run a controlled read-only project-inspection command for FormalQualBench parity work. "
        "Allowed commands include rg, grep, sed, cat, ls, find, head, tail, wc, stat, du, pwd, "
        "and `lake env lean --version|--help`; shell operators and mutating commands are blocked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Single read-only inspection command.",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory inside the active OpenGauss project.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Timeout in seconds. Defaults to 60.",
            },
            "max_output_chars": {
                "type": "integer",
                "description": "Maximum stdout/stderr characters returned per stream.",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    },
}


registry.register(
    name="lean_project_inspect",
    toolset="lean-project-inspect",
    schema=LEAN_PROJECT_INSPECT_SCHEMA,
    handler=lambda args, **kw: _lean_project_inspect_tool(
        command=args.get("command", ""),
        cwd=args.get("cwd"),
        timeout_seconds=args.get("timeout_seconds") or 60,
        max_output_chars=args.get("max_output_chars") or 20000,
    ),
)
