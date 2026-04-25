"""OpenGauss-native Comparator proof-audit tool."""

from __future__ import annotations

import json
from typing import Any

from gauss_cli.lean_comparator import local_lean_comparator_check
from gauss_cli.lean_service import LeanProofServiceError
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


def _comparator_check_tool(
    *,
    challenge_path: str,
    solution_path: str,
    cwd: str | None = None,
    theorem_names: list[str] | None = None,
    permitted_axioms: list[str] | None = None,
    comparator_binary: str | None = None,
    artifact_dir: str | None = None,
    timeout_seconds: int = 30 * 60,
) -> str:
    try:
        payload = local_lean_comparator_check(
            challenge_path=challenge_path,
            solution_path=solution_path,
            cwd=cwd,
            theorem_names=theorem_names,
            permitted_axioms=permitted_axioms,
            comparator_binary=comparator_binary,
            artifact_dir=artifact_dir,
            timeout_seconds=int(timeout_seconds or 30 * 60),
        )
    except Exception as exc:
        return _error_payload("lean_comparator_check", exc)
    return _json_payload(payload)


LEAN_COMPARATOR_CHECK_SCHEMA = {
    "name": "lean_comparator_check",
    "description": (
        "Audit a Lean solution against a challenge with native Lake build and Comparator. "
        "Use this before claiming benchmark or theorem equivalence success."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "challenge_path": {
                "type": "string",
                "description": "Challenge Lean file path relative to the project Lean root, or absolute.",
            },
            "solution_path": {
                "type": "string",
                "description": "Solution Lean file path relative to the project Lean root, or absolute.",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory used to discover the nearest OpenGauss project.",
            },
            "theorem_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional theorem names to audit. Omit to extract from the challenge file.",
            },
            "permitted_axioms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional permitted axiom policy. Defaults to FormalQualBench policy.",
            },
            "comparator_binary": {
                "type": "string",
                "description": "Optional Comparator binary path. Otherwise use env or PATH discovery.",
            },
            "artifact_dir": {
                "type": "string",
                "description": "Optional directory for comparator_config.json and result.json artifacts.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Timeout for each local build/comparator command. Defaults to 1800.",
            },
        },
        "required": ["challenge_path", "solution_path"],
        "additionalProperties": False,
    },
}


registry.register(
    name="lean_comparator_check",
    toolset="lean-comparator",
    schema=LEAN_COMPARATOR_CHECK_SCHEMA,
    handler=lambda args, **kw: _comparator_check_tool(
        challenge_path=args.get("challenge_path", ""),
        solution_path=args.get("solution_path", ""),
        cwd=args.get("cwd"),
        theorem_names=args.get("theorem_names"),
        permitted_axioms=args.get("permitted_axioms"),
        comparator_binary=args.get("comparator_binary"),
        artifact_dir=args.get("artifact_dir"),
        timeout_seconds=args.get("timeout_seconds") or 30 * 60,
    ),
)
