from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from gauss_cli.autoformalize import (  # noqa: E402
    AUTOFORMALIZE_CODEX_MODEL_ENV,
    AUTOFORMALIZE_MCP_COUNT_PATH_ENV,
    AUTOFORMALIZE_MCP_PROXY_ENV,
    AUTOFORMALIZE_NONINTERACTIVE_ENV,
    FORGE_AUTOFORMALIZE_BACKEND,
    FORGE_INSTRUCTIONS_TEMPLATE_ENV,
    FORGE_STARTUP_TEMPLATE_ENV,
    normalize_autoformalize_backend_name,
    resolve_autoformalize_request,
)
from gauss_cli.project import initialize_gauss_project  # noqa: E402
from gauss_cli.config import get_gauss_home  # noqa: E402


DEFAULT_TASKS = (
    "PontryaginDuality",
    "BurnsidePrimeDegreeTheorem",
    "JordanCycleTheorem",
)
DEFAULT_FORMALQUALBENCH_REPO = "https://github.com/math-inc/FormalQualBench.git"
DEFAULT_FORMALQUALBENCH_REF = "main"
DEFAULT_COMPARATOR_REPO = "https://github.com/leanprover/comparator.git"
DEFAULT_COMPARATOR_REF = "master"
DEFAULT_PERMITTED_AXIOMS = ("propext", "Quot.sound", "Classical.choice")
SUMMARY_ENV = "HERMES_HYPER_SUMMARY_PATH"
SAMPLES_ENV = "HERMES_HYPER_SAMPLES_PATH"
DEFAULT_MODEL = "gpt-5.4"
OVERRIDE_BUNDLE_SUBDIR = Path("workspace") / "opengauss_formalqualbench"


@dataclass(slots=True)
class OverrideBundle:
    root: Path | None = None
    forge_instructions: Path | None = None
    startup_context: Path | None = None
    theorem_hints_dir: Path | None = None


@dataclass(slots=True)
class EvalConfig:
    backend: str = FORGE_AUTOFORMALIZE_BACKEND
    system_name: str = ""
    task_filter: tuple[str, ...] = DEFAULT_TASKS
    task_timeout_seconds: int = 4 * 60 * 60
    stagnation_timeout_seconds: int = 30 * 60
    stagnation_grace_seconds: int = 5 * 60
    stagnation_poll_seconds: int = 15
    formalqualbench_repo: str = DEFAULT_FORMALQUALBENCH_REPO
    formalqualbench_ref: str = DEFAULT_FORMALQUALBENCH_REF
    comparator_repo: str = DEFAULT_COMPARATOR_REPO
    comparator_ref: str = DEFAULT_COMPARATOR_REF
    landrun_path: str = "landrun"
    cache_root: Path | None = None
    output_root: Path | None = None
    model_name: str = DEFAULT_MODEL
    max_agent_turns: int | None = None
    auth_provider: str | None = None
    permitted_axioms: tuple[str, ...] = DEFAULT_PERMITTED_AXIOMS
    enable_nanoda: bool = False
    system_prompt: str = ""


@dataclass(slots=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    idle_timed_out: bool = False
    error: str | None = None


def _parse_task_filter(value: Any) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_TASKS
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",") if item.strip()]
        return tuple(parts) if parts else DEFAULT_TASKS
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return tuple(parts) if parts else DEFAULT_TASKS
    return DEFAULT_TASKS


def _parse_cli_overrides(argv: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if not token.startswith("--"):
            index += 1
            continue
        if "=" in token:
            key, value = token[2:].split("=", 1)
            overrides[key] = value
            index += 1
            continue
        if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            overrides[token[2:]] = argv[index + 1]
            index += 2
            continue
        overrides[token[2:]] = "true"
        index += 1
    return overrides


def load_eval_config(config_path: Path, cli_overrides: dict[str, str] | None = None) -> EvalConfig:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    env_cfg = payload.get("env", {}) or {}
    openai_cfg = payload.get("openai", {}) or {}
    cli_overrides = cli_overrides or {}

    backend = normalize_autoformalize_backend_name(
        cli_overrides.get("env.backend", env_cfg.get("backend", FORGE_AUTOFORMALIZE_BACKEND))
    )
    model_name = str(cli_overrides.get("openai.model_name", openai_cfg.get("model_name", DEFAULT_MODEL)) or DEFAULT_MODEL)
    output_root = cli_overrides.get("env.output_root") or env_cfg.get("output_root")
    cache_root = cli_overrides.get("env.cache_root") or env_cfg.get("cache_root")

    config = EvalConfig(
        backend=backend,
        system_name=str(env_cfg.get("system_name") or f"opengauss-{backend}-direct"),
        task_filter=_parse_task_filter(cli_overrides.get("env.task_filter", env_cfg.get("task_filter"))),
        task_timeout_seconds=int(
            cli_overrides.get("env.task_timeout_seconds", env_cfg.get("task_timeout_seconds", 4 * 60 * 60))
        ),
        stagnation_timeout_seconds=int(
            cli_overrides.get(
                "env.stagnation_timeout_seconds",
                env_cfg.get("stagnation_timeout_seconds", 30 * 60),
            )
        ),
        stagnation_grace_seconds=int(
            cli_overrides.get(
                "env.stagnation_grace_seconds",
                env_cfg.get("stagnation_grace_seconds", 5 * 60),
            )
        ),
        stagnation_poll_seconds=int(
            cli_overrides.get(
                "env.stagnation_poll_seconds",
                env_cfg.get("stagnation_poll_seconds", 15),
            )
        ),
        formalqualbench_repo=str(env_cfg.get("formalqualbench_repo", DEFAULT_FORMALQUALBENCH_REPO)),
        formalqualbench_ref=str(env_cfg.get("formalqualbench_ref", DEFAULT_FORMALQUALBENCH_REF)),
        comparator_repo=str(env_cfg.get("comparator_repo", DEFAULT_COMPARATOR_REPO)),
        comparator_ref=str(env_cfg.get("comparator_ref", DEFAULT_COMPARATOR_REF)),
        landrun_path=str(env_cfg.get("landrun_path", "landrun")),
        cache_root=Path(cache_root).expanduser().resolve() if cache_root else None,
        output_root=Path(output_root).expanduser().resolve() if output_root else None,
        model_name=model_name,
        max_agent_turns=(
            int(cli_overrides["env.max_agent_turns"])
            if "env.max_agent_turns" in cli_overrides and cli_overrides["env.max_agent_turns"]
            else env_cfg.get("max_agent_turns")
        ),
        auth_provider=str(env_cfg.get("auth_provider") or "").strip() or None,
        permitted_axioms=tuple(env_cfg.get("permitted_axioms") or DEFAULT_PERMITTED_AXIOMS),
        enable_nanoda=bool(env_cfg.get("enable_nanoda", False)),
        system_prompt=str(env_cfg.get("system_prompt") or "").strip(),
    )
    return config


def _discover_override_bundle() -> OverrideBundle:
    hermes_home = str(os.getenv("HERMES_HOME", "") or "").strip()
    if not hermes_home:
        return OverrideBundle()
    root = Path(hermes_home).expanduser() / OVERRIDE_BUNDLE_SUBDIR
    if not root.is_dir():
        return OverrideBundle()
    theorem_hints_dir = root / "theorem_hints"
    return OverrideBundle(
        root=root,
        forge_instructions=(root / "forge_instructions.md") if (root / "forge_instructions.md").is_file() else None,
        startup_context=(root / "startup_context.md") if (root / "startup_context.md").is_file() else None,
        theorem_hints_dir=theorem_hints_dir if theorem_hints_dir.is_dir() else None,
    )


def _read_theorem_hint(bundle: OverrideBundle, task_name: str) -> str:
    if bundle.theorem_hints_dir is None:
        return ""
    hint_path = bundle.theorem_hints_dir / f"{task_name}.md"
    if not hint_path.is_file():
        return ""
    return hint_path.read_text(encoding="utf-8").strip()


def _run_checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> ProcessResult:
    start = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ProcessResult(
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            duration_seconds=round(time.time() - start, 3),
            timed_out=True,
            error=f"Timed out after {timeout_seconds}s",
        )
    except OSError as exc:
        return ProcessResult(
            returncode=None,
            stdout="",
            stderr="",
            duration_seconds=round(time.time() - start, 3),
            error=str(exc),
        )
    return ProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        duration_seconds=round(time.time() - start, 3),
    )


def _latest_progress_timestamp(paths: list[Path]) -> float | None:
    latest: float | None = None
    for path in paths:
        if not path.exists():
            continue
        try:
            candidate = path.stat().st_mtime
        except OSError:
            continue
        latest = candidate if latest is None else max(latest, candidate)
        if path.is_dir():
            for child in path.rglob("*"):
                try:
                    child_mtime = child.stat().st_mtime
                except OSError:
                    continue
                latest = max(latest, child_mtime)
    return latest


def _run_checked_with_stagnation(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    progress_paths: list[Path] | None = None,
    idle_timeout_seconds: int,
    idle_grace_seconds: int,
    poll_seconds: int,
) -> ProcessResult:
    start = time.time()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    progress_paths = progress_paths or []
    last_progress = _latest_progress_timestamp(progress_paths) or start
    deadline = (start + timeout_seconds) if timeout_seconds is not None else None
    poll_interval = max(1, poll_seconds)
    try:
        while True:
            remaining: float | None
            if deadline is None:
                remaining = None
            else:
                remaining = deadline - time.time()
                if remaining <= 0:
                    process.kill()
                    stdout, stderr = process.communicate()
                    return ProcessResult(
                        returncode=None,
                        stdout=stdout or "",
                        stderr=stderr or "",
                        duration_seconds=round(time.time() - start, 3),
                        timed_out=True,
                        error=f"Timed out after {timeout_seconds}s",
                    )
            try:
                stdout, stderr = process.communicate(
                    timeout=poll_interval if remaining is None else min(poll_interval, max(0.1, remaining))
                )
                return ProcessResult(
                    returncode=process.returncode,
                    stdout=stdout or "",
                    stderr=stderr or "",
                    duration_seconds=round(time.time() - start, 3),
                )
            except subprocess.TimeoutExpired:
                current_progress = _latest_progress_timestamp(progress_paths)
                if current_progress is not None and current_progress > last_progress:
                    last_progress = current_progress
                    continue
                now = time.time()
                if (
                    idle_timeout_seconds > 0
                    and now - start >= idle_grace_seconds
                    and now - last_progress >= idle_timeout_seconds
                ):
                    process.kill()
                    stdout, stderr = process.communicate()
                    return ProcessResult(
                        returncode=None,
                        stdout=stdout or "",
                        stderr=stderr or "",
                        duration_seconds=round(now - start, 3),
                        timed_out=True,
                        idle_timed_out=True,
                        error=f"No progress detected for {idle_timeout_seconds}s",
                    )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def _ensure_git_checkout(repo_url: str, revision: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if (destination / ".git").is_dir():
        _run_checked(["git", "-C", str(destination), "fetch", "--depth", "1", "origin", revision], cwd=destination.parent)
        _run_checked(["git", "-C", str(destination), "checkout", "--force", "FETCH_HEAD"], cwd=destination.parent)
        return destination
    if destination.exists():
        shutil.rmtree(destination)
    result = _run_checked(
        ["git", "clone", "--depth", "1", "--branch", revision, repo_url, str(destination)],
        cwd=destination.parent,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to clone {repo_url}: {result.stderr or result.stdout}")
    return destination


def _find_comparator_binary(repo_root: Path) -> Path:
    candidates = [
        repo_root / ".lake" / "build" / "bin" / "comparator",
        repo_root / "build" / "bin" / "comparator",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    matches = sorted(repo_root.glob("**/comparator"))
    for candidate in matches:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise RuntimeError(f"Comparator binary not found under {repo_root}")


def _ensure_comparator_binary(config: EvalConfig, cache_root: Path) -> Path:
    comparator_root = _ensure_git_checkout(
        config.comparator_repo,
        config.comparator_ref,
        cache_root / "comparator",
    )
    build = _run_checked(["lake", "build", "comparator"], cwd=comparator_root)
    if build.returncode != 0:
        raise RuntimeError(f"Failed to build comparator: {build.stderr or build.stdout}")
    return _find_comparator_binary(comparator_root)


def _resolve_output_root(config: EvalConfig, config_path: Path) -> Path:
    summary_path = str(os.getenv(SUMMARY_ENV, "") or "").strip()
    if summary_path:
        return Path(summary_path).expanduser().resolve().parent
    if config.output_root is not None:
        return config.output_root
    return (config_path.parent / "formalqualbench-run").resolve()


def _ensure_helpers(output_root: Path) -> tuple[Path, Path, Path]:
    helper_dir = output_root / ".helpers"
    helper_dir.mkdir(parents=True, exist_ok=True)
    bash_counter_path = helper_dir / "bash_count.txt"
    bash_wrapper_path = helper_dir / "bash"
    real_bash = shutil.which("bash") or "/bin/bash"
    bash_wrapper_path.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                'COUNT_FILE="${GAUSS_AUTOFORMALIZE_BASH_COUNT_PATH:-}"',
                'if [ -n "$COUNT_FILE" ]; then',
                '  mkdir -p "$(dirname "$COUNT_FILE")"',
                '  count=0',
                '  if [ -f "$COUNT_FILE" ]; then count=$(cat "$COUNT_FILE" 2>/dev/null || printf 0); fi',
                '  printf "%s\\n" "$((count + 1))" > "$COUNT_FILE"',
                "fi",
                f'exec "{real_bash}" "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    bash_wrapper_path.chmod(0o755)
    return helper_dir, bash_wrapper_path, Path(__file__).with_name("mcp_proxy.py")


def _build_backend_instruction(config: EvalConfig, task_name: str, theorem_hint: str) -> str:
    lines = [
        f"FormalQualBench theorem: {task_name}.",
        "Use Challenge.lean as the immutable source of truth.",
        "Write the proof in Solution.lean and keep the theorem name exactly the same.",
        "Do not modify Challenge.lean or comparator policy files.",
        "The output should be comparator-compatible and should remove `sorry` from Solution.lean.",
    ]
    if config.system_prompt:
        lines.extend(["", "Additional benchmark policy:", config.system_prompt])
    if theorem_hint:
        lines.extend(["", "Theorem-local hint:", theorem_hint])
    return " ".join(line.strip() for line in lines if line.strip())


def _extract_theorem_names(challenge_path: Path) -> list[str]:
    content = challenge_path.read_text(encoding="utf-8")
    matches = re.findall(r"\b(?:theorem|lemma)\s+([A-Za-z0-9_']+)", content)
    if not matches:
        raise RuntimeError(f"Could not find theorem name in {challenge_path}")
    return [matches[0]]


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _read_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def _prepare_task_workspace(cached_repo: Path, output_root: Path, task_name: str) -> tuple[Path, Path, Path, Path]:
    workspace_root = output_root / "workspaces" / task_name
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    shutil.copytree(cached_repo, workspace_root, ignore=shutil.ignore_patterns(".git"))
    initialize_gauss_project(workspace_root, name=f"FormalQualBench {task_name}", source_mode="benchmark")
    challenge_source = workspace_root / "FormalQualBench" / task_name / "Main.lean"
    if not challenge_source.is_file():
        raise RuntimeError(f"FormalQualBench task not found: {challenge_source}")
    challenge_path = workspace_root / "Challenge.lean"
    solution_path = workspace_root / "Solution.lean"
    shutil.copy2(challenge_source, challenge_path)
    shutil.copy2(challenge_source, solution_path)
    artifact_dir = output_root / "artifacts" / task_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return workspace_root, artifact_dir, challenge_path, solution_path


def _comparator_config_payload(config: EvalConfig, theorem_names: list[str]) -> dict[str, Any]:
    return {
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": theorem_names,
        "permitted_axioms": list(config.permitted_axioms),
        "enable_nanoda": bool(config.enable_nanoda),
    }


def _autoformalize_config(config: EvalConfig, artifact_dir: Path) -> dict[str, Any]:
    return {
        "gauss": {
            "autoformalize": {
                "backend": config.backend,
                "handoff_mode": "helper",
                "auth_mode": "auto",
                "managed_state_dir": str(artifact_dir / "managed"),
            }
        }
    }


def _task_environment(
    config: EvalConfig,
    *,
    workspace_root: Path,
    bash_wrapper_dir: Path,
    bundle: OverrideBundle,
    bash_count_path: Path,
    mcp_count_path: Path,
    mcp_proxy_path: Path,
) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        [
            str(bash_wrapper_dir),
            str(Path(config.landrun_path).expanduser().resolve().parent)
            if Path(config.landrun_path).expanduser().is_absolute()
            else "",
            env.get("PATH", ""),
        ]
    ).strip(os.pathsep)
    env["GAUSS_AUTOFORMALIZE_BASH_COUNT_PATH"] = str(bash_count_path)
    env[AUTOFORMALIZE_MCP_PROXY_ENV] = str(mcp_proxy_path)
    env[AUTOFORMALIZE_MCP_COUNT_PATH_ENV] = str(mcp_count_path)
    env[AUTOFORMALIZE_NONINTERACTIVE_ENV] = "1"
    env["TERMINAL_CWD"] = str(workspace_root)
    if config.backend == "codex" and config.model_name:
        env[AUTOFORMALIZE_CODEX_MODEL_ENV] = config.model_name
    if config.backend == FORGE_AUTOFORMALIZE_BACKEND:
        if bundle.forge_instructions is not None:
            env[FORGE_INSTRUCTIONS_TEMPLATE_ENV] = str(bundle.forge_instructions)
        if bundle.startup_context is not None:
            env[FORGE_STARTUP_TEMPLATE_ENV] = str(bundle.startup_context)
    return env


def _run_one_task(
    config: EvalConfig,
    *,
    cached_repo: Path,
    comparator_binary: Path,
    output_root: Path,
    helper_dir: Path,
    mcp_proxy_path: Path,
    task_name: str,
    bundle: OverrideBundle,
) -> dict[str, Any]:
    workspace_root, artifact_dir, challenge_path, solution_path = _prepare_task_workspace(
        cached_repo,
        output_root,
        task_name,
    )
    bash_count_path = artifact_dir / "bash_count.txt"
    mcp_count_path = artifact_dir / "mcp_count.txt"
    theorem_hint = _read_theorem_hint(bundle, task_name)
    command = f"/autoformalize {_build_backend_instruction(config, task_name, theorem_hint)}"
    launch_plan = resolve_autoformalize_request(
        command,
        _autoformalize_config(config, artifact_dir),
        active_cwd=str(workspace_root),
        base_env=_task_environment(
            config,
            workspace_root=workspace_root,
            bash_wrapper_dir=helper_dir,
            bundle=bundle,
            bash_count_path=bash_count_path,
            mcp_count_path=mcp_count_path,
            mcp_proxy_path=mcp_proxy_path,
        ),
    )

    managed_root = artifact_dir / "managed"
    backend_result = _run_checked_with_stagnation(
        list(launch_plan.handoff_request.argv),
        cwd=Path(launch_plan.handoff_request.cwd),
        env=launch_plan.handoff_request.env,
        timeout_seconds=config.task_timeout_seconds,
        progress_paths=[solution_path, managed_root],
        idle_timeout_seconds=config.stagnation_timeout_seconds,
        idle_grace_seconds=config.stagnation_grace_seconds,
        poll_seconds=config.stagnation_poll_seconds,
    )
    (artifact_dir / "backend.stdout.log").write_text(backend_result.stdout, encoding="utf-8")
    (artifact_dir / "backend.stderr.log").write_text(backend_result.stderr, encoding="utf-8")

    theorem_names = _extract_theorem_names(challenge_path)
    comparator_config_path = artifact_dir / "comparator_config.json"
    _write_json(comparator_config_path, _comparator_config_payload(config, theorem_names))

    if backend_result.idle_timed_out:
        lake_result = ProcessResult(
            returncode=None,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            error="Skipped because backend stagnated before producing a proof candidate",
        )
        comparator_result = ProcessResult(
            returncode=None,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            error="Skipped because backend stagnated before comparator validation",
        )
    else:
        lake_result = _run_checked(
            ["lake", "build", "Challenge", "Solution"],
            cwd=workspace_root,
            timeout_seconds=min(config.task_timeout_seconds, 30 * 60),
        )
        comparator_result = _run_checked(
            ["lake", "env", str(comparator_binary), str(comparator_config_path)],
            cwd=workspace_root,
            timeout_seconds=min(config.task_timeout_seconds, 30 * 60),
        )
    (artifact_dir / "lake_build.stdout.log").write_text(lake_result.stdout, encoding="utf-8")
    (artifact_dir / "lake_build.stderr.log").write_text(lake_result.stderr, encoding="utf-8")
    (artifact_dir / "comparator.stdout.log").write_text(comparator_result.stdout, encoding="utf-8")
    (artifact_dir / "comparator.stderr.log").write_text(comparator_result.stderr, encoding="utf-8")

    comparator_valid = comparator_result.returncode == 0 and not comparator_result.timed_out
    total_duration = round(
        backend_result.duration_seconds + lake_result.duration_seconds + comparator_result.duration_seconds,
        3,
    )
    bash_call_count = _read_count(bash_count_path)
    mcp_call_count = _read_count(mcp_count_path)
    result = {
        "task_name": task_name,
        "backend": config.backend,
        "system": config.system_name,
        "workspace_root": str(workspace_root),
        "artifact_dir": str(artifact_dir),
        "challenge_path": str(challenge_path),
        "solution_path": str(solution_path),
        "theorem_names": theorem_names,
        "backend_returncode": backend_result.returncode,
        "backend_timed_out": backend_result.timed_out,
        "backend_idle_timed_out": backend_result.idle_timed_out,
        "backend_error": backend_result.error,
        "lake_build_returncode": lake_result.returncode,
        "lake_build_timed_out": lake_result.timed_out,
        "comparator_returncode": comparator_result.returncode,
        "comparator_timed_out": comparator_result.timed_out,
        "comparator_valid": comparator_valid,
        "score": 1.0 if comparator_valid else 0.0,
        "wall_clock_seconds": total_duration,
        "bash_call_count": bash_call_count,
        "mcp_call_count": mcp_call_count,
        "backend_stdout_path": str(artifact_dir / "backend.stdout.log"),
        "backend_stderr_path": str(artifact_dir / "backend.stderr.log"),
        "lake_build_stdout_path": str(artifact_dir / "lake_build.stdout.log"),
        "lake_build_stderr_path": str(artifact_dir / "lake_build.stderr.log"),
        "comparator_stdout_path": str(artifact_dir / "comparator.stdout.log"),
        "comparator_stderr_path": str(artifact_dir / "comparator.stderr.log"),
        "comparator_config_path": str(comparator_config_path),
    }
    _write_json(artifact_dir / "result.json", result)
    return result


def evaluate_config(config_path: Path, cli_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    config = load_eval_config(config_path, cli_overrides)
    output_root = _resolve_output_root(config, config_path)
    output_root.mkdir(parents=True, exist_ok=True)
    helper_dir, _bash_wrapper, mcp_proxy_path = _ensure_helpers(output_root)
    bundle = _discover_override_bundle()
    cache_root = config.cache_root or (get_gauss_home() / "benchmarks" / "formalqualbench" / "cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    formalqualbench_root = _ensure_git_checkout(
        config.formalqualbench_repo,
        config.formalqualbench_ref,
        cache_root / "formalqualbench",
    )
    comparator_binary = _ensure_comparator_binary(config, cache_root)

    results = [
        _run_one_task(
            config,
            cached_repo=formalqualbench_root,
            comparator_binary=comparator_binary,
            output_root=output_root,
            helper_dir=helper_dir,
            mcp_proxy_path=mcp_proxy_path,
            task_name=task_name,
            bundle=bundle,
        )
        for task_name in config.task_filter
    ]
    solve_count = sum(1 for item in results if item["comparator_valid"])
    total_wall_clock_seconds = round(sum(float(item["wall_clock_seconds"]) for item in results), 3)
    total_bash_call_count = sum(int(item["bash_call_count"]) for item in results)
    total_mcp_call_count = sum(int(item["mcp_call_count"]) for item in results)
    total_tool_call_count = total_bash_call_count + total_mcp_call_count
    # Keep solve count lexicographically dominant, then prefer lower runtime, then fewer tool calls.
    selection_score = round((solve_count * 1_000_000_000.0) - (total_wall_clock_seconds * 1_000.0) - total_tool_call_count, 3)
    summary = {
        "system": config.system_name,
        "backend": config.backend,
        "task_count": len(results),
        "solve_count": solve_count,
        "mean_score": (solve_count / len(results)) if results else 0.0,
        "total_wall_clock_seconds": total_wall_clock_seconds,
        "total_bash_call_count": total_bash_call_count,
        "total_mcp_call_count": total_mcp_call_count,
        "total_tool_call_count": total_tool_call_count,
        "selection_score": selection_score,
        "artifact_root": str(output_root),
        "task_filter": list(config.task_filter),
        "results": results,
    }

    summary_path = Path(os.getenv(SUMMARY_ENV, "")).expanduser() if os.getenv(SUMMARY_ENV) else output_root / "summary.json"
    _write_json(summary_path, summary)
    samples_path = Path(os.getenv(SAMPLES_ENV, "")).expanduser() if os.getenv(SAMPLES_ENV) else output_root / "samples.jsonl"
    samples_path.parent.mkdir(parents=True, exist_ok=True)
    with samples_path.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FormalQualBench benchmark runner for OpenGauss-managed backends.")
    subparsers = parser.add_subparsers(dest="command")
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--config", required=True)
    args, extras = parser.parse_known_args(argv)
    if args.command != "evaluate":
        parser.print_help()
        return 2
    evaluate_config(Path(args.config).expanduser().resolve(), _parse_cli_overrides(extras))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
