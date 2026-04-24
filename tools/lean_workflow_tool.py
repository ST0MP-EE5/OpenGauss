"""OpenGauss-native Lean project tools."""

from __future__ import annotations

import json
from typing import Any

from gauss_cli.lean_service import (
    LeanProofServiceError,
    local_lake_build,
    local_lean_check_file,
    local_lean_project_status,
    local_lean_sorry_report,
)
from tools.registry import registry


def _json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error_payload(operation: str, exc: Exception) -> str:
    error_type = exc.code if isinstance(exc, LeanProofServiceError) else type(exc).__name__
    return _json_payload(
        {
            "success": False,
            "provider": "local",
            "operation": operation,
            "error": str(exc),
            "error_type": error_type,
        }
    )


def _status_tool(*, cwd: str | None = None) -> str:
    try:
        payload = local_lean_project_status(cwd=cwd)
    except Exception as exc:
        return _error_payload("lean_project_status", exc)
    return _json_payload(
        {
            "success": True,
            "provider": "local",
            "operation": "lean_project_status",
            **payload,
        }
    )


def _sorry_report_tool(*, cwd: str | None = None, path: str | None = None) -> str:
    try:
        payload = local_lean_sorry_report(cwd=cwd, path=path)
    except Exception as exc:
        return _error_payload("lean_sorry_report", exc)
    return _json_payload(
        {
            "success": True,
            "provider": "local",
            "operation": "lean_sorry_report",
            **payload,
        }
    )


def _lake_build_tool(
    *,
    cwd: str | None = None,
    targets: list[str] | None = None,
    timeout_seconds: int = 30 * 60,
) -> str:
    try:
        payload = local_lake_build(
            cwd=cwd,
            targets=targets,
            timeout_seconds=int(timeout_seconds or 30 * 60),
        )
    except Exception as exc:
        return _error_payload("lean_lake_build", exc)
    return _json_payload(
        {
            "provider": "local",
            "operation": "lean_lake_build",
            **payload,
        }
    )


def _check_file_tool(
    *,
    path: str,
    cwd: str | None = None,
    timeout_seconds: int = 30 * 60,
) -> str:
    try:
        payload = local_lean_check_file(
            path=path,
            cwd=cwd,
            timeout_seconds=int(timeout_seconds or 30 * 60),
        )
    except Exception as exc:
        return _error_payload("lean_check_file", exc)
    return _json_payload(
        {
            "provider": "local",
            "operation": "lean_check_file",
            **payload,
        }
    )


LEAN_PROJECT_STATUS_SCHEMA = {
    "name": "lean_project_status",
    "description": "Inspect the active OpenGauss Lean project without using MCP or shell access.",
    "parameters": {
        "type": "object",
        "properties": {
            "cwd": {
                "type": "string",
                "description": "Optional working directory used to discover the nearest OpenGauss project.",
            },
        },
        "additionalProperties": False,
    },
}

LEAN_SORRY_REPORT_SCHEMA = {
    "name": "lean_sorry_report",
    "description": "Report `sorry` or `admit` occurrences in one Lean file or the active project.",
    "parameters": {
        "type": "object",
        "properties": {
            "cwd": {
                "type": "string",
                "description": "Optional working directory used to discover the nearest OpenGauss project.",
            },
            "path": {
                "type": "string",
                "description": "Optional Lean file path relative to the project Lean root.",
            },
        },
        "additionalProperties": False,
    },
}

LEAN_LAKE_BUILD_SCHEMA = {
    "name": "lean_lake_build",
    "description": "Run `lake build` for the active Lean project through controlled argv execution.",
    "parameters": {
        "type": "object",
        "properties": {
            "cwd": {
                "type": "string",
                "description": "Optional working directory used to discover the nearest OpenGauss project.",
            },
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional Lake targets to build. Omit for a full project build.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Build timeout in seconds. Defaults to 1800.",
            },
        },
        "additionalProperties": False,
    },
}

LEAN_CHECK_FILE_SCHEMA = {
    "name": "lean_check_file",
    "description": "Run `lake env lean <file>` for a Lean file inside the active project.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Lean file path relative to the project Lean root.",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory used to discover the nearest OpenGauss project.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Check timeout in seconds. Defaults to 1800.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


registry.register(
    name="lean_project_status",
    toolset="lean-local",
    schema=LEAN_PROJECT_STATUS_SCHEMA,
    handler=lambda args, **kw: _status_tool(cwd=args.get("cwd")),
)
registry.register(
    name="lean_sorry_report",
    toolset="lean-local",
    schema=LEAN_SORRY_REPORT_SCHEMA,
    handler=lambda args, **kw: _sorry_report_tool(cwd=args.get("cwd"), path=args.get("path")),
)
registry.register(
    name="lean_lake_build",
    toolset="lean-local",
    schema=LEAN_LAKE_BUILD_SCHEMA,
    handler=lambda args, **kw: _lake_build_tool(
        cwd=args.get("cwd"),
        targets=args.get("targets"),
        timeout_seconds=args.get("timeout_seconds") or 30 * 60,
    ),
)
registry.register(
    name="lean_check_file",
    toolset="lean-local",
    schema=LEAN_CHECK_FILE_SCHEMA,
    handler=lambda args, **kw: _check_file_tool(
        path=args.get("path", ""),
        cwd=args.get("cwd"),
        timeout_seconds=args.get("timeout_seconds") or 30 * 60,
    ),
)
