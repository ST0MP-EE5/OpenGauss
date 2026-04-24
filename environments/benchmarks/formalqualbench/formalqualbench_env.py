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

from gauss_cli.lean_workflow import run_native_lean_workflow  # noqa: E402
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


@dataclass(slots=True)
class EvalConfig:
    backend: str = NATIVE_BACKEND_NAME
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
    lean4export_ref: str = DEFAULT_LEAN4EXPORT_REF
    landrun_path: str = "landrun"
    cache_root: Path | None = None
    output_root: Path | None = None
    model_name: str = DEFAULT_MODEL
    reasoning_effort: str = "medium"
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

    backend = str(cli_overrides.get("env.backend", env_cfg.get("backend", NATIVE_BACKEND_NAME)) or NATIVE_BACKEND_NAME)
    backend = "native" if backend.strip().lower() in {"native", "direct", "codex"} else backend.strip().lower()
    model_name = str(cli_overrides.get("openai.model_name", openai_cfg.get("model_name", DEFAULT_MODEL)) or DEFAULT_MODEL)
    reasoning_effort = str(
        cli_overrides.get("openai.reasoning_effort", openai_cfg.get("reasoning_effort", "medium")) or "medium"
    ).strip().lower()
    output_root = cli_overrides.get("env.output_root") or env_cfg.get("output_root")
    cache_root = cli_overrides.get("env.cache_root") or env_cfg.get("cache_root")

    config = EvalConfig(
        backend=backend,
        system_name=str(env_cfg.get("system_name") or "opengauss-gpt55-direct"),
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
        lean4export_ref=str(env_cfg.get("lean4export_ref", DEFAULT_LEAN4EXPORT_REF) or "").strip(),
        landrun_path=str(env_cfg.get("landrun_path", "landrun")),
        cache_root=Path(cache_root).expanduser().resolve() if cache_root else None,
        output_root=Path(output_root).expanduser().resolve() if output_root else None,
        model_name=model_name,
        reasoning_effort=reasoning_effort or "medium",
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
        raise RuntimeError(f"Failed to prime FormalQualBench mathlib checkout: {update.stderr or update.stdout}")

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
    namespace_stack: list[str] = []
    for line in challenge_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        namespace_match = re.match(r"namespace\s+([A-Za-z0-9_'.]+)\b", stripped)
        if namespace_match:
            namespace_stack.extend(part for part in namespace_match.group(1).split(".") if part)
            continue

        theorem_match = re.match(r"(?:theorem|lemma)\s+([A-Za-z0-9_'.]+)\b", stripped)
        if theorem_match:
            theorem_name = theorem_match.group(1)
            if "." in theorem_name:
                return [theorem_name.removeprefix("_root_.")]
            return [".".join([*namespace_stack, theorem_name]) if namespace_stack else theorem_name]

        end_match = re.match(r"end(?:\s+([A-Za-z0-9_'.]+))?\b", stripped)
        if end_match and namespace_stack:
            end_name = end_match.group(1)
            if end_name:
                for _ in [part for part in end_name.split(".") if part]:
                    if namespace_stack:
                        namespace_stack.pop()
            else:
                namespace_stack.pop()

    raise RuntimeError(f"Could not find theorem name in {challenge_path}")


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
    return {
        "challenge_module": "Challenge",
        "solution_module": "Solution",
        "theorem_names": theorem_names,
        "permitted_axioms": list(config.permitted_axioms),
        "enable_nanoda": bool(config.enable_nanoda),
    }


def _run_native_backend(config: EvalConfig, *, command: str, workspace_root: Path) -> ProcessResult:
    start = time.time()
    previous_terminal_cwd = os.environ.get("TERMINAL_CWD")
    os.environ["TERMINAL_CWD"] = str(workspace_root)
    try:
        result = run_native_lean_workflow(
            command,
            cwd=workspace_root,
            model=config.model_name,
            reasoning_effort=config.reasoning_effort,
            max_iterations=config.max_agent_turns or 90,
            quiet_mode=True,
        )
        return ProcessResult(
            returncode=0 if result.success else 1,
            stdout=result.final_response or "",
            stderr=result.error or "",
            duration_seconds=round(time.time() - start, 3),
            error=result.error or None,
        )
    except Exception as exc:
        return ProcessResult(
            returncode=None,
            stdout="",
            stderr=str(exc),
            duration_seconds=round(time.time() - start, 3),
            error=str(exc),
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
    command = f"/autoformalize {_build_backend_instruction(config, task_name, theorem_hint)}"
    backend_result = _run_native_backend(
        config,
        command=command,
        workspace_root=workspace_root,
    )
    (artifact_dir / "backend.stdout.log").write_text(backend_result.stdout, encoding="utf-8")
    (artifact_dir / "backend.stderr.log").write_text(backend_result.stderr, encoding="utf-8")

    theorem_names = _extract_theorem_names(challenge_path)
    comparator_config_path = artifact_dir / "comparator_config.json"
    _write_json(comparator_config_path, _comparator_config_payload(config, theorem_names))

    lake_result = _run_checked(
        ["lake", "build", "Challenge", "Solution"],
        cwd=workspace_root,
        timeout_seconds=min(config.task_timeout_seconds, 30 * 60),
    )
    comparator_env = dict(os.environ)
    comparator_env["PATH"] = os.pathsep.join(
        [
            str(toolchain.landrun_binary.parent),
            str(toolchain.lean4export_binary.parent),
            comparator_env.get("PATH", ""),
        ]
    ).strip(os.pathsep)
    comparator_result = _run_checked(
        ["lake", "env", str(toolchain.comparator_binary), str(comparator_config_path)],
        cwd=workspace_root,
        env=comparator_env,
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
    bash_call_count = 0
    mcp_call_count = 0
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
    bundle = _discover_override_bundle()
    cache_root = config.cache_root or (get_gauss_home() / "benchmarks" / "formalqualbench" / "cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    formalqualbench_root = _ensure_git_checkout(
        config.formalqualbench_repo,
        config.formalqualbench_ref,
        cache_root / "formalqualbench",
    )
    expected_lean_toolchain = _read_lean_toolchain(formalqualbench_root)
    _prime_formalqualbench_cache(formalqualbench_root)
    toolchain = _ensure_comparator_toolchain(
        config,
        cache_root,
        expected_lean_toolchain=expected_lean_toolchain,
    )

    results = [
        _run_one_task(
            config,
            cached_repo=formalqualbench_root,
            toolchain=toolchain,
            output_root=output_root,
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
        "model": config.model_name,
        "reasoning_effort": config.reasoning_effort,
        "lean_toolchain": expected_lean_toolchain,
        "formalqualbench_ref": config.formalqualbench_ref,
        "comparator_ref": config.comparator_ref,
        "lean4export_ref": config.lean4export_ref,
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
    parser = argparse.ArgumentParser(description="FormalQualBench benchmark runner for native OpenGauss Lean workflows.")
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
