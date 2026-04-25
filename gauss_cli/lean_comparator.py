"""Native Comparator proof-audit service for OpenGauss Lean projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from gauss_cli.lean_service import (
    LeanProofServiceConfigurationError,
    _module_name_for_path,
    _resolve_project_and_lean_file,
    _run_local_lean_command,
)

DEFAULT_PERMITTED_AXIOMS = ("propext", "Quot.sound", "Classical.choice")


def extract_theorem_names(challenge_path: Path) -> list[str]:
    """Extract theorem/lemma names from a challenge file, preserving namespaces."""
    namespace_stack: list[str] = []
    for line in challenge_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        namespace_match = re.match(r"namespace\s+([A-Za-z0-9_'.]+)\b", stripped)
        if namespace_match:
            namespace_stack.extend(part for part in namespace_match.group(1).split(".") if part)
            continue

        theorem_match = re.match(r"(?:theorem|lemma)\s+([A-Za-z0-9_'.]+)\b", stripped)
        if theorem_match:
            theorem_name = theorem_match.group(1).removeprefix("_root_.")
            if "." in theorem_name:
                return [theorem_name]
            return [".".join([*namespace_stack, theorem_name]) if namespace_stack else theorem_name]

        end_match = re.match(r"end(?:\s+([A-Za-z0-9_'.]+))?\b", stripped)
        if end_match and namespace_stack:
            end_name = end_match.group(1)
            pop_count = len([part for part in end_name.split(".") if part]) if end_name else 1
            for _ in range(pop_count):
                if namespace_stack:
                    namespace_stack.pop()

    raise LeanProofServiceConfigurationError(
        f"Could not find theorem or lemma name in {challenge_path}",
        code="theorem_name_not_found",
    )


def comparator_config_payload(
    *,
    challenge_module: str,
    solution_module: str,
    theorem_names: list[str],
    permitted_axioms: list[str] | tuple[str, ...] | None = None,
    enable_nanoda: bool = False,
) -> dict[str, Any]:
    return {
        "challenge_module": challenge_module,
        "solution_module": solution_module,
        "theorem_names": list(theorem_names),
        "permitted_axioms": list(permitted_axioms or DEFAULT_PERMITTED_AXIOMS),
        "enable_nanoda": bool(enable_nanoda),
    }


def _find_comparator_binary(project_root: Path, explicit_binary: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_binary:
        candidates.append(Path(explicit_binary).expanduser())
    for env_name in ("GAUSS_COMPARATOR_BINARY", "COMPARATOR_BINARY"):
        env_value = str(os.getenv(env_name, "") or "").strip()
        if env_value:
            candidates.append(Path(env_value).expanduser())
    resolved_path = shutil.which("comparator")
    if resolved_path:
        candidates.append(Path(resolved_path))
    candidates.extend(
        [
            project_root / ".lake" / "build" / "bin" / "comparator",
            project_root.parent / "comparator" / ".lake" / "build" / "bin" / "comparator",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _classify_comparator_failure(result_payload: dict[str, Any]) -> str:
    if result_payload["lake_build"]["timed_out"] or result_payload["comparator"]["timed_out"]:
        return "timeout"
    if result_payload["lake_build"]["returncode"] != 0:
        return "build_failure"
    output = "\n".join(
        [
            str(result_payload["comparator"].get("stdout", "")),
            str(result_payload["comparator"].get("stderr", "")),
        ]
    ).lower()
    if "axiom" in output or "unsafe" in output:
        return "illegal_axiom"
    if "theorem" in output and ("mismatch" in output or "not found" in output):
        return "theorem_mismatch"
    return "comparator_failure"


def local_lean_comparator_check(
    *,
    challenge_path: str | Path,
    solution_path: str | Path,
    cwd: str | Path | None = None,
    theorem_names: list[str] | tuple[str, ...] | None = None,
    permitted_axioms: list[str] | tuple[str, ...] | None = None,
    comparator_binary: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    timeout_seconds: int = 30 * 60,
) -> dict[str, Any]:
    """Audit a Lean solution with Lake and Comparator through native services."""
    project, challenge = _resolve_project_and_lean_file(path=challenge_path, cwd=cwd)
    _, solution = _resolve_project_and_lean_file(path=solution_path, cwd=project.root)
    names = list(theorem_names or extract_theorem_names(challenge))
    challenge_module = _module_name_for_path(challenge, lean_root=project.lean_root)
    solution_module = _module_name_for_path(solution, lean_root=project.lean_root)

    if artifact_dir is None:
        project.runtime_dir.mkdir(parents=True, exist_ok=True)
        artifact_root = Path(tempfile.mkdtemp(prefix="opengauss-comparator-", dir=str(project.runtime_dir)))
    else:
        artifact_root = Path(artifact_dir).expanduser().resolve()
        artifact_root.mkdir(parents=True, exist_ok=True)

    config_path = _write_json(
        artifact_root / "comparator_config.json",
        comparator_config_payload(
            challenge_module=challenge_module,
            solution_module=solution_module,
            theorem_names=names,
            permitted_axioms=permitted_axioms,
        ),
    )
    start = time.time()
    lake_result = _run_local_lean_command(
        ["lake", "build", challenge_module, solution_module],
        cwd=project.lean_root,
        timeout_seconds=int(timeout_seconds or 30 * 60),
    )
    comparator_path = _find_comparator_binary(project.lean_root, comparator_binary)
    if comparator_path is None:
        payload = {
            "success": False,
            "provider": "local",
            "operation": "lean_comparator_check",
            "verdict": "comparator_unavailable",
            "comparator_available": False,
            "comparator_valid": False,
            "project_root": str(project.root),
            "lean_root": str(project.lean_root),
            "challenge_path": str(challenge),
            "solution_path": str(solution),
            "challenge_module": challenge_module,
            "solution_module": solution_module,
            "theorem_names": names,
            "permitted_axioms": list(permitted_axioms or DEFAULT_PERMITTED_AXIOMS),
            "artifact_dir": str(artifact_root),
            "comparator_config_path": str(config_path),
            "lake_build": lake_result.to_payload(),
            "comparator": {
                "command": [],
                "cwd": str(project.lean_root),
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
                "error": "Comparator binary not found. Set GAUSS_COMPARATOR_BINARY or COMPARATOR_BINARY.",
            },
            "duration_seconds": round(time.time() - start, 3),
            "mcp_call_count": 0,
        }
        _write_json(artifact_root / "result.json", payload)
        return payload

    comparator_result = _run_local_lean_command(
        ["lake", "env", str(comparator_path), str(config_path)],
        cwd=project.lean_root,
        timeout_seconds=int(timeout_seconds or 30 * 60),
    )
    comparator_valid = (
        lake_result.success
        and comparator_result.returncode == 0
        and not comparator_result.timed_out
        and not comparator_result.error
    )
    payload = {
        "success": comparator_valid,
        "provider": "local",
        "operation": "lean_comparator_check",
        "verdict": "pass" if comparator_valid else "",
        "comparator_available": True,
        "comparator_binary": str(comparator_path),
        "comparator_valid": comparator_valid,
        "project_root": str(project.root),
        "lean_root": str(project.lean_root),
        "challenge_path": str(challenge),
        "solution_path": str(solution),
        "challenge_module": challenge_module,
        "solution_module": solution_module,
        "theorem_names": names,
        "permitted_axioms": list(permitted_axioms or DEFAULT_PERMITTED_AXIOMS),
        "artifact_dir": str(artifact_root),
        "comparator_config_path": str(config_path),
        "lake_build": lake_result.to_payload(),
        "comparator": comparator_result.to_payload(),
        "duration_seconds": round(time.time() - start, 3),
        "mcp_call_count": 0,
    }
    if not payload["verdict"]:
        payload["verdict"] = _classify_comparator_failure(payload)
    _write_json(artifact_root / "result.json", payload)
    return payload
