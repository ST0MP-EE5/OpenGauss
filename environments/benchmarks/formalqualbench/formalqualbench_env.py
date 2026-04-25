from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

_repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from gauss_cli.lean_workflow import (  # noqa: E402
    NATIVE_LEAN_TOOLSET,
    run_native_lean_workflow,
)
from gauss_cli.lean_comparator import (  # noqa: E402
    comparator_config_payload as _native_comparator_config_payload,
    extract_theorem_names as _native_extract_theorem_names,
)
from gauss_cli.project import initialize_gauss_project  # noqa: E402
from gauss_cli.config import get_gauss_home  # noqa: E402


DEFAULT_TASKS = (
    "PontryaginDuality",
    "BurnsidePrimeDegreeTheorem",
    "JordanCycleTheorem",
)
FAILED2_TASKS = (
    "ParisHarringtonPrinciple",
    "ColorfulCaratheodoryTheorem",
)
DEFAULT_FORMALQUALBENCH_REPO = "https://github.com/math-inc/FormalQualBench.git"
DEFAULT_FORMALQUALBENCH_REF = "main"
DEFAULT_COMPARATOR_REPO = "https://github.com/leanprover/comparator.git"
DEFAULT_COMPARATOR_REF = "master"
DEFAULT_LEAN4EXPORT_REF = ""
DEFAULT_LANDRUN_REPO = "https://github.com/Zouuup/landrun.git"
DEFAULT_LANDRUN_REF = "main"
DEFAULT_PERMITTED_AXIOMS = ("propext", "Quot.sound", "Classical.choice")
SUMMARY_ENV = "HERMES_HYPER_SUMMARY_PATH"
SAMPLES_ENV = "HERMES_HYPER_SAMPLES_PATH"
DEFAULT_MODEL = "gpt-5.5"
NATIVE_BACKEND_NAME = "native"
OVERRIDE_BUNDLE_SUBDIR = Path("workspace") / "opengauss_formalqualbench"
OVERRIDE_BUNDLE_ROOT_ENV = "GAUSS_AUTOFORMALIZE_OVERRIDE_BUNDLE_ROOT"
RUNS_ROOT_SUBDIR = Path("benchmarks") / "formalqualbench" / "runs"
NATIVE_COUNTER_KEYS = (
    "model_call_count",
    "lean_lsp_call_count",
    "axle_call_count",
    "local_build_call_count",
    "comparator_call_count",
    "bash_call_count",
    "mcp_call_count",
)


@dataclass(slots=True)
class OverrideBundle:
    root: Path | None = None
    instructions_template: Path | None = None
    startup_context: Path | None = None
    theorem_hints_dir: Path | None = None


@dataclass(slots=True)
class ComparatorToolchain:
    comparator_binary: Path
    landrun_binary: Path
    lean4export_binary: Path

    def to_env(self) -> dict[str, str]:
        path_entries = [
            str(self.landrun_binary.parent),
            str(self.lean4export_binary.parent),
            os.environ.get("PATH", ""),
        ]
        return {
            "GAUSS_COMPARATOR_BINARY": str(self.comparator_binary),
            "GAUSS_LANDRUN_BINARY": str(self.landrun_binary),
            "GAUSS_LEAN4EXPORT_BINARY": str(self.lean4export_binary),
            "PATH": os.pathsep.join(item for item in path_entries if item),
        }


@dataclass(slots=True)
class EvalConfig:
    backend: str = NATIVE_BACKEND_NAME
    workflow_lane: str = NATIVE_BACKEND_NAME
    system_name: str = ""
    task_filter: tuple[str, ...] = DEFAULT_TASKS
    task_timeout_seconds: int = 4 * 60 * 60
    check_timeout_seconds: int = 30 * 60
    stagnation_timeout_seconds: int = 30 * 60
    stagnation_grace_seconds: int = 5 * 60
    stagnation_poll_seconds: int = 15
    formalqualbench_repo: str = DEFAULT_FORMALQUALBENCH_REPO
    formalqualbench_ref: str = DEFAULT_FORMALQUALBENCH_REF
    comparator_repo: str = DEFAULT_COMPARATOR_REPO
    comparator_ref: str = DEFAULT_COMPARATOR_REF
    lean4export_ref: str = DEFAULT_LEAN4EXPORT_REF
    landrun_path: str = "landrun"
    cache_root: Path | None = None
    output_root: Path | None = None
    model_name: str = DEFAULT_MODEL
    reasoning_effort: str = "high"
    max_agent_turns: int | None = None
    max_attempts: int = 1
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
    counters: dict[str, int] = field(default_factory=dict)


def _decode_process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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


def _native_counter_defaults() -> dict[str, int]:
    return {key: 0 for key in NATIVE_COUNTER_KEYS}


def _merge_native_counters(*payloads: dict[str, Any] | None) -> dict[str, int]:
    merged = _native_counter_defaults()
    for payload in payloads:
        if not payload:
            continue
        for key in NATIVE_COUNTER_KEYS:
            try:
                merged[key] += int(payload.get(key, 0) or 0)
            except (TypeError, ValueError):
                continue
    return merged


def _workflow_message_counters(messages: list[dict[str, Any]]) -> dict[str, int]:
    counters = _native_counter_defaults()
    counters["model_call_count"] = sum(1 for item in messages if item.get("role") == "assistant")
    for item in messages:
        text = json.dumps(item, ensure_ascii=False)
        if "lean_lsp_" in text or "lean_proof_context" in text:
            counters["lean_lsp_call_count"] += 1
        if "axle_" in text:
            counters["axle_call_count"] += 1
        if "lean_lake_build" in text or "lean_check_file" in text:
            counters["local_build_call_count"] += 1
        if "lean_comparator_check" in text:
            counters["comparator_call_count"] += 1
        if "lean_project_inspect" in text:
            counters["bash_call_count"] += 1
        if "mcp_" in text:
            counters["mcp_call_count"] += 1
    return counters


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return value


def _eval_config_payload(config: EvalConfig, *, config_path: Path | None = None) -> dict[str, Any]:
    payload = {item.name: _json_safe_value(getattr(config, item.name)) for item in fields(EvalConfig)}
    if config_path is not None:
        payload["source_config_path"] = str(config_path)
    payload["native_counter_keys"] = list(NATIVE_COUNTER_KEYS)
    payload["mcp_call_count"] = 0
    return payload


def load_eval_config(config_path: Path, cli_overrides: dict[str, str] | None = None) -> EvalConfig:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    env_cfg = payload.get("env", {}) or {}
    openai_cfg = payload.get("openai", {}) or {}
    cli_overrides = cli_overrides or {}

    backend = str(cli_overrides.get("env.backend", env_cfg.get("backend", NATIVE_BACKEND_NAME)) or NATIVE_BACKEND_NAME)
    backend = backend.strip().lower()
    backend = "native" if backend in {"native", "direct", "codex"} else backend
    workflow_lane = NATIVE_BACKEND_NAME
    model_name = str(cli_overrides.get("openai.model_name", openai_cfg.get("model_name", DEFAULT_MODEL)) or DEFAULT_MODEL)
    reasoning_effort = str(
        cli_overrides.get("openai.reasoning_effort", openai_cfg.get("reasoning_effort", "high")) or "high"
    ).strip().lower()
    output_root = cli_overrides.get("env.output_root") or env_cfg.get("output_root")
    cache_root = cli_overrides.get("env.cache_root") or env_cfg.get("cache_root")

    config = EvalConfig(
        backend=backend,
        workflow_lane=workflow_lane,
        system_name=str(env_cfg.get("system_name") or "opengauss-gpt55-direct"),
        task_filter=_parse_task_filter(cli_overrides.get("env.task_filter", env_cfg.get("task_filter"))),
        task_timeout_seconds=int(
            cli_overrides.get("env.task_timeout_seconds", env_cfg.get("task_timeout_seconds", 4 * 60 * 60))
        ),
        check_timeout_seconds=int(
            cli_overrides.get("env.check_timeout_seconds", env_cfg.get("check_timeout_seconds", 30 * 60))
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
        lean4export_ref=str(env_cfg.get("lean4export_ref", DEFAULT_LEAN4EXPORT_REF) or "").strip(),
        landrun_path=str(env_cfg.get("landrun_path", "landrun")),
        cache_root=Path(cache_root).expanduser().resolve() if cache_root else None,
        output_root=Path(output_root).expanduser().resolve() if output_root else None,
        model_name=model_name,
        reasoning_effort=reasoning_effort or "high",
        max_agent_turns=(
            int(cli_overrides["env.max_agent_turns"])
            if "env.max_agent_turns" in cli_overrides and cli_overrides["env.max_agent_turns"]
            else env_cfg.get("max_agent_turns")
        ),
        max_attempts=int(cli_overrides.get("env.max_attempts", env_cfg.get("max_attempts", 1))),
        auth_provider=str(env_cfg.get("auth_provider") or "").strip() or None,
        permitted_axioms=tuple(env_cfg.get("permitted_axioms") or DEFAULT_PERMITTED_AXIOMS),
        enable_nanoda=bool(env_cfg.get("enable_nanoda", False)),
        system_prompt=str(env_cfg.get("system_prompt") or "").strip(),
    )
    return config


def _workflow_toolset(config: EvalConfig) -> str:
    del config
    return NATIVE_LEAN_TOOLSET


def _read_lean_toolchain(project_root: Path) -> str:
    toolchain_path = project_root / "lean-toolchain"
    if not toolchain_path.is_file():
        raise RuntimeError(f"Lean toolchain file not found: {toolchain_path}")
    return toolchain_path.read_text(encoding="utf-8").strip()


def _assert_matching_lean_toolchain(component: str, project_root: Path, expected_toolchain: str) -> str:
    actual_toolchain = _read_lean_toolchain(project_root)
    if actual_toolchain != expected_toolchain:
        raise RuntimeError(
            f"{component} Lean toolchain mismatch: expected {expected_toolchain!r} "
            f"to match FormalQualBench, got {actual_toolchain!r} at {project_root / 'lean-toolchain'}."
        )
    return actual_toolchain


def _discover_override_bundle() -> OverrideBundle:
    override_root = str(os.getenv(OVERRIDE_BUNDLE_ROOT_ENV, "") or "").strip()
    if override_root:
        root = Path(override_root).expanduser()
    else:
        hermes_home = str(os.getenv("HERMES_HOME", "") or "").strip()
        if not hermes_home:
            return OverrideBundle()
        root = Path(hermes_home).expanduser() / OVERRIDE_BUNDLE_SUBDIR
    if not root.is_dir():
        return OverrideBundle()
    resolved_root = root.resolve()
    theorem_hints_dir = root / "theorem_hints"
    instructions_template = None
    for candidate_name in ("instructions.md", "codex_instructions.md"):
        candidate = resolved_root / candidate_name
        if candidate.is_file():
            instructions_template = candidate
            break
    return OverrideBundle(
        root=resolved_root,
        instructions_template=instructions_template,
        startup_context=(resolved_root / "startup_context.md") if (resolved_root / "startup_context.md").is_file() else None,
        theorem_hints_dir=theorem_hints_dir.resolve() if theorem_hints_dir.is_dir() else None,
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
            stdout=_decode_process_text(exc.stdout),
            stderr=_decode_process_text(exc.stderr),
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
                        stdout=_decode_process_text(stdout),
                        stderr=_decode_process_text(stderr),
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
                    stdout=_decode_process_text(stdout),
                    stderr=_decode_process_text(stderr),
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
                        stdout=_decode_process_text(stdout),
                        stderr=_decode_process_text(stderr),
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
    clone = _run_checked(["git", "clone", "--no-checkout", repo_url, str(destination)], cwd=destination.parent)
    if clone.returncode != 0:
        raise RuntimeError(f"Failed to clone {repo_url}: {clone.stderr or clone.stdout}")
    fetch = _run_checked(["git", "-C", str(destination), "fetch", "--depth", "1", "origin", revision], cwd=destination.parent)
    if fetch.returncode != 0:
        raise RuntimeError(f"Failed to fetch {revision} from {repo_url}: {fetch.stderr or fetch.stdout}")
    checkout = _run_checked(["git", "-C", str(destination), "checkout", "--force", "FETCH_HEAD"], cwd=destination.parent)
    if checkout.returncode != 0:
        raise RuntimeError(f"Failed to checkout {revision} from {repo_url}: {checkout.stderr or checkout.stdout}")
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


def _pin_lake_manifest_package(project_root: Path, package_name: str, revision: str) -> bool:
    revision = str(revision or "").strip()
    if not revision:
        return False
    manifest_path = project_root / "lake-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Lake manifest not found under {project_root}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise RuntimeError(f"Lake manifest has no package list: {manifest_path}")

    changed = False
    found = False
    for package in packages:
        if not isinstance(package, dict) or package.get("name") != package_name:
            continue
        found = True
        if package.get("rev") != revision:
            package["rev"] = revision
            changed = True
        if package.get("inputRev") != revision:
            package["inputRev"] = revision
            changed = True
    if not found:
        raise RuntimeError(f"Package {package_name!r} not found in {manifest_path}")
    if changed:
        manifest_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def _remove_lake_package_checkout(project_root: Path, package_name: str) -> None:
    manifest_path = project_root / "lake-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    packages_dir = Path(payload.get("packagesDir") or ".lake/packages")
    package_root = project_root / packages_dir / package_name
    if package_root.exists():
        shutil.rmtree(package_root)


def _apply_comparator_dependency_pins(config: EvalConfig, comparator_root: Path) -> None:
    if not config.lean4export_ref:
        return
    if _pin_lake_manifest_package(comparator_root, "lean4export", config.lean4export_ref):
        _remove_lake_package_checkout(comparator_root, "lean4export")


def _remove_lake_build_outputs(project_root: Path) -> None:
    build_root = project_root / ".lake" / "build"
    if build_root.exists():
        shutil.rmtree(build_root)


def _ensure_landrun_binary(config: EvalConfig, cache_root: Path) -> Path:
    requested = str(config.landrun_path or "").strip()
    if requested:
        expanded = Path(requested).expanduser()
        if expanded.is_file() and os.access(expanded, os.X_OK):
            return expanded.resolve()
        resolved = shutil.which(requested)
        if resolved:
            return Path(resolved).resolve()

    go = shutil.which("go")
    if go is None:
        raise RuntimeError(
            "landrun is not available in PATH and Go is not installed, so the FormalQualBench "
            "comparator sandbox cannot be bootstrapped."
        )

    landrun_root = _ensure_git_checkout(
        DEFAULT_LANDRUN_REPO,
        DEFAULT_LANDRUN_REF,
        cache_root / "landrun",
    )
    binary = landrun_root / "landrun"
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary.resolve()

    build = _run_checked([go, "build", "-o", str(binary), "cmd/landrun/main.go"], cwd=landrun_root)
    if build.returncode != 0:
        raise RuntimeError(f"Failed to build landrun: {build.stderr or build.stdout}")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"landrun binary not found after build: {binary}")
    return binary.resolve()


def _ensure_lean4export_binary(comparator_root: Path, *, expected_lean_toolchain: str) -> Path:
    package_root = comparator_root / ".lake" / "packages" / "lean4export"
    if not package_root.is_dir():
        raise RuntimeError(f"lean4export package not found under comparator checkout: {package_root}")
    _assert_matching_lean_toolchain("lean4export", package_root, expected_lean_toolchain)

    binary = package_root / ".lake" / "build" / "bin" / "lean4export"
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary.resolve()

    build = _run_checked(["lake", "build", "lean4export"], cwd=package_root)
    if build.returncode != 0:
        raise RuntimeError(f"Failed to build lean4export: {build.stderr or build.stdout}")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"lean4export binary not found after build: {binary}")
    return binary.resolve()


def _ensure_comparator_toolchain(
    config: EvalConfig,
    cache_root: Path,
    *,
    expected_lean_toolchain: str,
) -> ComparatorToolchain:
    comparator_root = _ensure_git_checkout(
        config.comparator_repo,
        config.comparator_ref,
        cache_root / "comparator",
    )
    _assert_matching_lean_toolchain("comparator", comparator_root, expected_lean_toolchain)
    _apply_comparator_dependency_pins(config, comparator_root)
    _remove_lake_build_outputs(comparator_root)
    build = _run_checked(["lake", "build", "comparator"], cwd=comparator_root)
    if build.returncode != 0:
        raise RuntimeError(f"Failed to build comparator: {build.stderr or build.stdout}")
    return ComparatorToolchain(
        comparator_binary=_find_comparator_binary(comparator_root),
        landrun_binary=_ensure_landrun_binary(config, cache_root),
        lean4export_binary=_ensure_lean4export_binary(
            comparator_root,
            expected_lean_toolchain=expected_lean_toolchain,
        ),
    )


def _prime_formalqualbench_cache(cached_repo: Path) -> None:
    mathlib_root = cached_repo / ".lake" / "packages" / "mathlib"
    if (mathlib_root / "Mathlib.lean").is_file():
        return

    update = _run_checked(["lake", "update"], cwd=cached_repo, timeout_seconds=30 * 60)
    if update.returncode != 0:
        detail = update.stderr or update.stdout or update.error or f"returncode={update.returncode}"
        raise RuntimeError(f"Failed to prime FormalQualBench mathlib checkout: {detail}")

    cache_get = _run_checked(["lake", "exe", "cache", "get"], cwd=cached_repo, timeout_seconds=30 * 60)
    if cache_get.returncode != 0:
        # The benchmark remains correct without the Mathlib build cache; this only affects latency.
        return


def _resolve_output_root(config: EvalConfig, config_path: Path) -> Path:
    summary_path = str(os.getenv(SUMMARY_ENV, "") or "").strip()
    if summary_path:
        return Path(summary_path).expanduser().resolve().parent
    if config.output_root is not None:
        return config.output_root
    return (config_path.parent / "formalqualbench-run").resolve()


def _build_backend_instruction(
    config: EvalConfig,
    task_name: str,
    theorem_hint: str,
    *,
    attempt_index: int = 1,
    previous_failure: dict[str, Any] | None = None,
) -> str:
    lines = [
        f"FormalQualBench theorem: {task_name}.",
        "Use Challenge.lean as the immutable source of truth.",
        "Write the proof in Solution.lean and keep the theorem name exactly the same.",
        "Do not modify Challenge.lean or comparator policy files.",
        "The output should be comparator-compatible and should remove `sorry` from Solution.lean.",
        "Do not introduce new axioms, constants, unsafe declarations, or elaborator workarounds.",
        "Success requires Comparator validity, not just lake build success.",
    ]
    lines.extend(
        [
            f"OpenGauss harness attempt {attempt_index} of {max(1, config.max_attempts)}.",
            "Use lean_comparator_check during the attempt; if it fails, use its exact output to repair.",
            "Use lean_project_inspect only for controlled read-only project/source inspection.",
        ]
    )
    if previous_failure:
        feedback = str(previous_failure.get("feedback") or "").strip()
        failure_kind = str(previous_failure.get("failure_kind") or "previous_failure")
        lines.extend(
            [
                "",
                f"Previous attempt failed with kind `{failure_kind}`.",
                "Repair the existing Solution.lean; do not preserve failed bypasses.",
            ]
        )
        if feedback:
            lines.extend(["Previous verifier feedback:", feedback])
    if config.system_prompt:
        lines.extend(["", "Additional benchmark policy:", config.system_prompt])
    if theorem_hint:
        lines.extend(["", "Theorem-local hint:", theorem_hint])
    return " ".join(line.strip() for line in lines if line.strip())


def _extract_theorem_names(challenge_path: Path) -> list[str]:
    return _native_extract_theorem_names(challenge_path)


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


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
    lakefile_toml = workspace_root / "lakefile.toml"
    if lakefile_toml.is_file():
        contents = lakefile_toml.read_text(encoding="utf-8")
        additions: list[str] = []
        for module_name in ("Challenge", "Solution"):
            if f'name = "{module_name}"' not in contents:
                additions.append(f'[[lean_lib]]\nname = "{module_name}"\n')
        if additions:
            lakefile_toml.write_text(
                contents.rstrip() + "\n\n" + "\n".join(additions),
                encoding="utf-8",
            )
    artifact_dir = output_root / "artifacts" / task_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return workspace_root, artifact_dir, challenge_path, solution_path


def _comparator_config_payload(config: EvalConfig, theorem_names: list[str]) -> dict[str, Any]:
    return _native_comparator_config_payload(
        challenge_module="Challenge",
        solution_module="Solution",
        theorem_names=theorem_names,
        permitted_axioms=config.permitted_axioms,
        enable_nanoda=config.enable_nanoda,
    )


def _check_timeout_for_attempt(config: EvalConfig, attempt_index: int, previous_failure: dict[str, Any] | None) -> int:
    base_timeout = max(1, int(config.check_timeout_seconds or 30 * 60))
    if previous_failure and previous_failure.get("failure_kind") == "timeout":
        return min(config.task_timeout_seconds, max(base_timeout * 2, 60 * 60))
    if attempt_index > 1:
        return min(config.task_timeout_seconds, max(base_timeout, 60 * 60))
    return min(config.task_timeout_seconds, base_timeout)


def _comparator_env(toolchain: ComparatorToolchain) -> dict[str, str]:
    env = dict(os.environ)
    env.update(toolchain.to_env())
    return env


def _classify_attempt_failure(
    *,
    backend_result: ProcessResult,
    lake_result: ProcessResult,
    comparator_result: ProcessResult,
) -> str:
    if backend_result.timed_out or lake_result.timed_out or comparator_result.timed_out:
        return "timeout"
    if backend_result.returncode not in (0, None) or backend_result.error:
        return "backend_failure"
    if lake_result.returncode != 0:
        return "build_failure"
    output = "\n".join([comparator_result.stdout, comparator_result.stderr]).lower()
    if "axiom" in output or "unsafe" in output:
        return "illegal_axiom"
    if "theorem" in output and ("mismatch" in output or "not found" in output):
        return "theorem_mismatch"
    return "comparator_failure"


def _attempt_feedback(
    *,
    backend_result: ProcessResult,
    lake_result: ProcessResult,
    comparator_result: ProcessResult,
    limit: int = 6000,
) -> str:
    parts = [
        "backend stdout:\n" + backend_result.stdout,
        "backend stderr:\n" + backend_result.stderr,
        "lake stdout:\n" + lake_result.stdout,
        "lake stderr:\n" + lake_result.stderr,
        "comparator stdout:\n" + comparator_result.stdout,
        "comparator stderr:\n" + comparator_result.stderr,
    ]
    text = "\n\n".join(part for part in parts if part.strip())
    return text[-limit:] if len(text) > limit else text


def _write_attempt_artifacts(
    *,
    artifact_dir: Path,
    attempt_index: int,
    backend_result: ProcessResult,
    lake_result: ProcessResult,
    comparator_result: ProcessResult,
    solution_path: Path,
    attempt_result: dict[str, Any],
) -> None:
    attempt_dir = artifact_dir / f"attempt_{attempt_index}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    for filename, contents in {
        "backend.stdout.log": backend_result.stdout,
        "backend.stderr.log": backend_result.stderr,
        "lake_build.stdout.log": lake_result.stdout,
        "lake_build.stderr.log": lake_result.stderr,
        "comparator.stdout.log": comparator_result.stdout,
        "comparator.stderr.log": comparator_result.stderr,
    }.items():
        (attempt_dir / filename).write_text(contents, encoding="utf-8")
    if solution_path.is_file():
        shutil.copy2(solution_path, attempt_dir / "Solution.lean")
    _write_json(attempt_dir / "result.json", attempt_result)


def _run_native_backend_subprocess(
    config: EvalConfig,
    *,
    command: str,
    workspace_root: Path,
    toolchain: ComparatorToolchain | None = None,
    extra_guidance: list[str] | None = None,
) -> ProcessResult:
    result_path = workspace_root / ".gauss" / "runtime" / f"backend-result-{os.getpid()}-{int(time.time() * 1000)}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    extra_env = toolchain.to_env() if toolchain is not None else {}
    child_command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_native-backend",
        "--command",
        command,
        "--cwd",
        str(workspace_root),
        "--model",
        config.model_name,
        "--reasoning-effort",
        config.reasoning_effort,
        "--max-iterations",
        str(config.max_agent_turns or 90),
        "--toolset",
        _workflow_toolset(config),
        "--result-path",
        str(result_path),
        "--extra-env-json",
        json.dumps(extra_env),
        "--extra-guidance-json",
        json.dumps(extra_guidance or []),
    ]
    env = dict(os.environ)
    env.update(extra_env)
    result = _run_checked_with_stagnation(
        child_command,
        cwd=workspace_root,
        env=env,
        timeout_seconds=max(1, int(config.task_timeout_seconds or 4 * 60 * 60)),
        idle_timeout_seconds=max(1, int(config.stagnation_timeout_seconds or 30 * 60)),
        idle_grace_seconds=max(0, int(config.stagnation_grace_seconds or 0)),
        poll_seconds=max(1, int(config.stagnation_poll_seconds or 15)),
        progress_paths=[workspace_root / "Solution.lean", result_path],
    )
    if not result_path.is_file():
        return ProcessResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timed_out=result.timed_out,
            idle_timed_out=result.idle_timed_out,
            error=result.error,
            counters=_native_counter_defaults(),
        )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    counters = _native_counter_defaults()
    counters.update({key: int(payload.get("counters", {}).get(key, 0) or 0) for key in NATIVE_COUNTER_KEYS})
    return ProcessResult(
        returncode=payload.get("returncode"),
        stdout=str(payload.get("stdout") or ""),
        stderr=str(payload.get("stderr") or ""),
        duration_seconds=float(payload.get("duration_seconds") or result.duration_seconds),
        timed_out=result.timed_out,
        idle_timed_out=result.idle_timed_out,
        error=result.error or payload.get("error"),
        counters=counters,
    )


def _run_native_backend(
    config: EvalConfig,
    *,
    command: str,
    workspace_root: Path,
    toolchain: ComparatorToolchain | None = None,
    extra_guidance: list[str] | None = None,
) -> ProcessResult:
    start = time.time()
    previous_terminal_cwd = os.environ.get("TERMINAL_CWD")
    os.environ["TERMINAL_CWD"] = str(workspace_root)
    try:
        extra_env = toolchain.to_env() if toolchain is not None else None
        result = run_native_lean_workflow(
            command,
            cwd=workspace_root,
            model=config.model_name,
            reasoning_effort=config.reasoning_effort,
            max_iterations=config.max_agent_turns or 90,
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            toolset=_workflow_toolset(config),
            extra_env=extra_env,
            extra_system_guidance=extra_guidance,
        )
        messages = list(getattr(result, "messages", []) or [])
        return ProcessResult(
            returncode=0 if result.success else 1,
            stdout=result.final_response or "",
            stderr=result.error or "",
            duration_seconds=round(time.time() - start, 3),
            error=result.error or None,
            counters=_workflow_message_counters(messages),
        )
    except Exception as exc:
        return ProcessResult(
            returncode=None,
            stdout="",
            stderr=str(exc),
            duration_seconds=round(time.time() - start, 3),
            error=str(exc),
            counters=_native_counter_defaults(),
        )
    finally:
        if previous_terminal_cwd is None:
            os.environ.pop("TERMINAL_CWD", None)
        else:
            os.environ["TERMINAL_CWD"] = previous_terminal_cwd


def _run_one_task(
    config: EvalConfig,
    *,
    cached_repo: Path,
    toolchain: ComparatorToolchain,
    output_root: Path,
    task_name: str,
    bundle: OverrideBundle,
) -> dict[str, Any]:
    workspace_root, artifact_dir, challenge_path, solution_path = _prepare_task_workspace(
        cached_repo,
        output_root,
        task_name,
    )
    theorem_hint = _read_theorem_hint(bundle, task_name)
    theorem_names = _extract_theorem_names(challenge_path)
    comparator_config_path = artifact_dir / "comparator_config.json"
    _write_json(comparator_config_path, _comparator_config_payload(config, theorem_names))

    attempts: list[dict[str, Any]] = []
    previous_failure: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    max_attempts = max(1, int(config.max_attempts or 1))

    for attempt_index in range(1, max_attempts + 1):
        command = f"/autoformalize {_build_backend_instruction(config, task_name, theorem_hint, attempt_index=attempt_index, previous_failure=previous_failure)}"
        extra_guidance = [
            f"FormalQualBench task: {task_name}.",
            f"Attempt {attempt_index} of {max_attempts}.",
            f"Comparator binary: {toolchain.comparator_binary}.",
        ]
        if previous_failure and previous_failure.get("feedback"):
            extra_guidance.append(str(previous_failure["feedback"]))
        backend_result = _run_native_backend(
            config,
            command=command,
            workspace_root=workspace_root,
            toolchain=toolchain,
            extra_guidance=extra_guidance,
        )
        check_timeout = _check_timeout_for_attempt(config, attempt_index, previous_failure)
        lake_result = _run_checked(
            ["lake", "build", "Challenge", "Solution"],
            cwd=workspace_root,
            timeout_seconds=check_timeout,
        )
        comparator_result = _run_checked(
            ["lake", "env", str(toolchain.comparator_binary), str(comparator_config_path)],
            cwd=workspace_root,
            env=_comparator_env(toolchain),
            timeout_seconds=check_timeout,
        )
        comparator_valid = comparator_result.returncode == 0 and not comparator_result.timed_out
        total_duration = round(
            backend_result.duration_seconds + lake_result.duration_seconds + comparator_result.duration_seconds,
            3,
        )
        failure_kind = "" if comparator_valid else _classify_attempt_failure(
            backend_result=backend_result,
            lake_result=lake_result,
            comparator_result=comparator_result,
        )
        native_counters = _merge_native_counters(
            backend_result.counters,
            {
                "local_build_call_count": 1,
                "comparator_call_count": 1,
                "bash_call_count": 0,
                "mcp_call_count": 0,
            },
        )
        attempt_result = {
            "task_name": task_name,
            "backend": config.backend,
            "workflow_lane": config.workflow_lane,
            "system": config.system_name,
            "attempt_index": attempt_index,
            "workspace_root": str(workspace_root),
            "artifact_dir": str(artifact_dir / f"attempt_{attempt_index}"),
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
            "failure_kind": failure_kind,
            "wall_clock_seconds": total_duration,
            "native_counters": native_counters,
            **native_counters,
            "comparator_config_path": str(comparator_config_path),
            "final_solution_path": str(artifact_dir / f"attempt_{attempt_index}" / "Solution.lean"),
        }
        _write_attempt_artifacts(
            artifact_dir=artifact_dir,
            attempt_index=attempt_index,
            backend_result=backend_result,
            lake_result=lake_result,
            comparator_result=comparator_result,
            solution_path=solution_path,
            attempt_result=attempt_result,
        )
        attempts.append(attempt_result)
        previous_failure = {
            "failure_kind": failure_kind,
            "feedback": _attempt_feedback(
                backend_result=backend_result,
                lake_result=lake_result,
                comparator_result=comparator_result,
            ),
        }
        final_result = attempt_result
        if comparator_valid:
            break

    assert final_result is not None
    last_attempt_index = int(final_result["attempt_index"])
    last_attempt_dir = artifact_dir / f"attempt_{last_attempt_index}"
    for filename in (
        "backend.stdout.log",
        "backend.stderr.log",
        "lake_build.stdout.log",
        "lake_build.stderr.log",
        "comparator.stdout.log",
        "comparator.stderr.log",
    ):
        source = last_attempt_dir / filename
        if source.is_file():
            shutil.copy2(source, artifact_dir / filename)
    if solution_path.is_file():
        shutil.copy2(solution_path, artifact_dir / "Solution.lean")

    total_counters = _native_counter_defaults()
    for attempt in attempts:
        total_counters = _merge_native_counters(total_counters, attempt.get("native_counters") or attempt)
    result = {
        **final_result,
        "artifact_dir": str(artifact_dir),
        "attempt_count": len(attempts),
        "max_attempts": max_attempts,
        "attempts": attempts,
        "wall_clock_seconds": round(sum(float(item.get("wall_clock_seconds", 0.0) or 0.0) for item in attempts), 3),
        "native_counters": total_counters,
        **total_counters,
        "backend_stdout_path": str(artifact_dir / "backend.stdout.log"),
        "backend_stderr_path": str(artifact_dir / "backend.stderr.log"),
        "lake_build_stdout_path": str(artifact_dir / "lake_build.stdout.log"),
        "lake_build_stderr_path": str(artifact_dir / "lake_build.stderr.log"),
        "comparator_stdout_path": str(artifact_dir / "comparator.stdout.log"),
        "comparator_stderr_path": str(artifact_dir / "comparator.stderr.log"),
        "final_solution_path": str(artifact_dir / "Solution.lean"),
    }
    _write_json(artifact_dir / "result.json", result)
    return result


def _load_existing_task_result(output_root: Path, task_name: str) -> dict[str, Any] | None:
    result_path = output_root / "artifacts" / task_name / "result.json"
    if not result_path.is_file():
        return None
    return json.loads(result_path.read_text(encoding="utf-8"))


def _write_failed_task_result(
    config: EvalConfig,
    *,
    output_root: Path,
    task_name: str,
    exc: Exception,
) -> dict[str, Any]:
    artifact_dir = output_root / "artifacts" / task_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    error_text = f"{type(exc).__name__}: {exc}"
    for filename, contents in {
        "backend.stdout.log": "",
        "backend.stderr.log": error_text,
        "lake_build.stdout.log": "",
        "lake_build.stderr.log": "",
        "comparator.stdout.log": "",
        "comparator.stderr.log": "",
    }.items():
        (artifact_dir / filename).write_text(contents, encoding="utf-8")
    comparator_config_path = artifact_dir / "comparator_config.json"
    if not comparator_config_path.exists():
        _write_json(
            comparator_config_path,
            _native_comparator_config_payload(
                challenge_module="Challenge",
                solution_module="Solution",
                theorem_names=[],
                permitted_axioms=config.permitted_axioms,
                enable_nanoda=config.enable_nanoda,
            ),
        )
    native_counters = _native_counter_defaults()
    result = {
        "task_name": task_name,
        "backend": config.backend,
        "workflow_lane": config.workflow_lane,
        "system": config.system_name,
        "workspace_root": str(output_root / "workspaces" / task_name),
        "artifact_dir": str(artifact_dir),
        "challenge_path": str(output_root / "workspaces" / task_name / "Challenge.lean"),
        "solution_path": str(output_root / "workspaces" / task_name / "Solution.lean"),
        "theorem_names": [],
        "backend_returncode": None,
        "backend_timed_out": False,
        "backend_idle_timed_out": False,
        "backend_error": error_text,
        "lake_build_returncode": None,
        "lake_build_timed_out": False,
        "comparator_returncode": None,
        "comparator_timed_out": False,
        "comparator_valid": False,
        "score": 0.0,
        "wall_clock_seconds": 0.0,
        "native_counters": native_counters,
        **native_counters,
        "backend_stdout_path": str(artifact_dir / "backend.stdout.log"),
        "backend_stderr_path": str(artifact_dir / "backend.stderr.log"),
        "lake_build_stdout_path": str(artifact_dir / "lake_build.stdout.log"),
        "lake_build_stderr_path": str(artifact_dir / "lake_build.stderr.log"),
        "comparator_stdout_path": str(artifact_dir / "comparator.stdout.log"),
        "comparator_stderr_path": str(artifact_dir / "comparator.stderr.log"),
        "comparator_config_path": str(comparator_config_path),
        "final_solution_path": str(artifact_dir / "Solution.lean"),
        "failure_kind": "task_exception",
        "attempt_count": 0,
        "max_attempts": max(1, int(config.max_attempts or 1)),
    }
    _write_json(artifact_dir / "result.json", result)
    return result


def _write_run_config(output_root: Path, config: EvalConfig, *, config_path: Path) -> Path:
    return _write_json(output_root / "run_config.resolved.json", _eval_config_payload(config, config_path=config_path))


def _build_summary(
    *,
    config: EvalConfig,
    results: list[dict[str, Any]],
    output_root: Path,
    lean_toolchain: str = "",
) -> dict[str, Any]:
    solve_count = sum(1 for item in results if item.get("comparator_valid"))
    total_wall_clock_seconds = round(sum(float(item.get("wall_clock_seconds", 0.0) or 0.0) for item in results), 3)
    total_counters = _native_counter_defaults()
    for item in results:
        total_counters = _merge_native_counters(total_counters, item.get("native_counters") or item)
    total_tool_call_count = (
        total_counters["lean_lsp_call_count"]
        + total_counters["axle_call_count"]
        + total_counters["local_build_call_count"]
        + total_counters["comparator_call_count"]
        + total_counters["bash_call_count"]
        + total_counters["mcp_call_count"]
    )
    selection_score = round((solve_count * 1_000_000_000.0) - (total_wall_clock_seconds * 1_000.0) - total_tool_call_count, 3)
    return {
        "system": config.system_name,
        "backend": config.backend,
        "workflow_lane": config.workflow_lane,
        "model": config.model_name,
        "reasoning_effort": config.reasoning_effort,
        "lean_toolchain": lean_toolchain,
        "formalqualbench_ref": config.formalqualbench_ref,
        "comparator_ref": config.comparator_ref,
        "lean4export_ref": config.lean4export_ref,
        "task_count": len(results),
        "solve_count": solve_count,
        "mean_score": (solve_count / len(results)) if results else 0.0,
        "total_wall_clock_seconds": total_wall_clock_seconds,
        "native_counters": total_counters,
        **{f"total_{key}": value for key, value in total_counters.items()},
        "total_tool_call_count": total_tool_call_count,
        "selection_score": selection_score,
        "artifact_root": str(output_root),
        "task_filter": list(config.task_filter),
        "results": results,
    }


def _write_summary_artifacts(output_root: Path, summary: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    summary_path = Path(os.getenv(SUMMARY_ENV, "")).expanduser() if os.getenv(SUMMARY_ENV) else output_root / "summary.json"
    _write_json(summary_path, summary)
    samples_path = Path(os.getenv(SAMPLES_ENV, "")).expanduser() if os.getenv(SAMPLES_ENV) else output_root / "samples.jsonl"
    samples_path.parent.mkdir(parents=True, exist_ok=True)
    with samples_path.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {**summary, "summary_path": str(summary_path), "samples_path": str(samples_path)}


def evaluate_config(
    config_path: Path,
    cli_overrides: dict[str, str] | None = None,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    config = load_eval_config(config_path, cli_overrides)
    output_root = _resolve_output_root(config, config_path)
    output_root.mkdir(parents=True, exist_ok=True)
    _write_run_config(output_root, config, config_path=config_path)
    bundle = _discover_override_bundle()
    cache_root = config.cache_root or (get_gauss_home() / "benchmarks" / "formalqualbench" / "cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    formalqualbench_root = _ensure_git_checkout(
        config.formalqualbench_repo,
        config.formalqualbench_ref,
        cache_root / "formalqualbench",
    )
    expected_lean_toolchain = _read_lean_toolchain(formalqualbench_root)
    run_config_payload = _eval_config_payload(config, config_path=config_path)
    run_config_payload["lean_toolchain"] = expected_lean_toolchain
    _write_json(output_root / "run_config.resolved.json", run_config_payload)
    _prime_formalqualbench_cache(formalqualbench_root)
    toolchain = _ensure_comparator_toolchain(
        config,
        cache_root,
        expected_lean_toolchain=expected_lean_toolchain,
    )

    results: list[dict[str, Any]] = []
    for task_name in config.task_filter:
        if resume:
            existing = _load_existing_task_result(output_root, task_name)
            if existing is not None:
                results.append(existing)
                continue
        try:
            result = _run_one_task(
                config,
                cached_repo=formalqualbench_root,
                toolchain=toolchain,
                output_root=output_root,
                task_name=task_name,
                bundle=bundle,
            )
        except Exception as exc:
            result = _write_failed_task_result(
                config,
                output_root=output_root,
                task_name=task_name,
                exc=exc,
            )
        results.append(result)

    summary = _build_summary(
        config=config,
        results=results,
        output_root=output_root,
        lean_toolchain=expected_lean_toolchain,
    )
    return _write_summary_artifacts(output_root, summary, results)


def _resolve_run_root(run_id: str | Path) -> Path:
    raw = Path(str(run_id)).expanduser()
    if raw.exists() or raw.is_absolute() or len(raw.parts) > 1:
        return raw.resolve()
    return (get_gauss_home() / RUNS_ROOT_SUBDIR / str(run_id)).resolve()


def summarize_run(run_id: str | Path) -> dict[str, Any]:
    output_root = _resolve_run_root(run_id)
    run_config_path = output_root / "run_config.resolved.json"
    if not run_config_path.is_file():
        raise RuntimeError(f"run_config.resolved.json not found under {output_root}")
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    config = EvalConfig(
        **{
            item.name: run_config.get(item.name, item.default)
            for item in fields(EvalConfig)
            if item.name not in {"cache_root", "output_root"}
        },
        cache_root=Path(run_config["cache_root"]).expanduser().resolve() if run_config.get("cache_root") else None,
        output_root=output_root,
    )
    results: list[dict[str, Any]] = []
    task_filter = list(run_config.get("task_filter") or [])
    if task_filter:
        for task_name in task_filter:
            existing = _load_existing_task_result(output_root, str(task_name))
            if existing is not None:
                results.append(existing)
    else:
        for result_path in sorted((output_root / "artifacts").glob("*/result.json")):
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
    summary = _build_summary(
        config=config,
        results=results,
        output_root=output_root,
        lean_toolchain=str(run_config.get("lean_toolchain", "") or ""),
    )
    return _write_summary_artifacts(output_root, summary, results)


def resume_run(run_id: str | Path) -> dict[str, Any]:
    output_root = _resolve_run_root(run_id)
    run_config_path = output_root / "run_config.resolved.json"
    if not run_config_path.is_file():
        raise RuntimeError(f"run_config.resolved.json not found under {output_root}")
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    source_config = Path(str(run_config.get("source_config_path") or "")).expanduser()
    if not source_config.is_file():
        raise RuntimeError(
            f"Original FormalQualBench config not found for resume: {source_config}. "
            "Use summarize for partial results, or rerun with --config."
        )
    return evaluate_config(
        source_config.resolve(),
        {"env.output_root": str(output_root)},
        resume=True,
    )


def _run_native_backend_child(args: argparse.Namespace) -> int:
    extra_env = json.loads(args.extra_env_json or "{}")
    extra_guidance = json.loads(args.extra_guidance_json or "[]")
    previous: dict[str, str | None] = {}
    for key, value in extra_env.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = str(value)
    start = time.time()
    try:
        result = run_native_lean_workflow(
            args.backend_command,
            cwd=Path(args.cwd).expanduser().resolve(),
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            max_iterations=int(args.max_iterations),
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            toolset=args.toolset,
            extra_env={str(key): str(value) for key, value in extra_env.items()},
            extra_system_guidance=[str(item) for item in extra_guidance],
        )
        messages = list(getattr(result, "messages", []) or [])
        payload = {
            "returncode": 0 if result.success else 1,
            "stdout": result.final_response or "",
            "stderr": result.error or "",
            "duration_seconds": round(time.time() - start, 3),
            "error": result.error or None,
            "counters": _workflow_message_counters(messages),
        }
    except Exception as exc:
        payload = {
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.time() - start, 3),
            "error": str(exc),
            "counters": _native_counter_defaults(),
        }
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    _write_json(Path(args.result_path).expanduser().resolve(), payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FormalQualBench benchmark runner for native OpenGauss Lean workflows.")
    subparsers = parser.add_subparsers(dest="command")
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--config", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--output-root")
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run-id", required=True)
    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--run-id", required=True)
    backend_parser = subparsers.add_parser("_native-backend")
    backend_parser.add_argument("--command", dest="backend_command", required=True)
    backend_parser.add_argument("--cwd", required=True)
    backend_parser.add_argument("--model", required=True)
    backend_parser.add_argument("--reasoning-effort", default="high")
    backend_parser.add_argument("--max-iterations", default="90")
    backend_parser.add_argument("--toolset", required=True)
    backend_parser.add_argument("--result-path", required=True)
    backend_parser.add_argument("--extra-env-json", default="{}")
    backend_parser.add_argument("--extra-guidance-json", default="[]")
    args, extras = parser.parse_known_args(argv)
    if args.command == "_native-backend":
        return _run_native_backend_child(args)
    if args.command in {"evaluate", "run"}:
        overrides = _parse_cli_overrides(extras)
        if getattr(args, "output_root", None):
            overrides["env.output_root"] = str(Path(args.output_root).expanduser().resolve())
        evaluate_config(Path(args.config).expanduser().resolve(), overrides)
        return 0
    if args.command == "resume":
        resume_run(args.run_id)
        return 0
    if args.command == "summarize":
        summarize_run(args.run_id)
        return 0
    if args.command is None:
        parser.print_help()
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
