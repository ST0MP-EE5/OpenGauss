#!/usr/bin/env python3
"""Run the OpenGauss + Hyper FormalQualBench sanity campaign."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gauss_cli.config import get_gauss_home


DEFAULT_HERMES_ROOT = Path("/Users/agambirchhina/Downloads/Hermes")
CAMPAIGN_DIR = REPO_ROOT / "integrations" / "hyperagents" / "formalqualbench"
DEFAULT_ENTRYPOINT = REPO_ROOT / "environments" / "benchmarks" / "formalqualbench" / "formalqualbench_env.py"
DEFAULT_BUNDLE_ROOT = CAMPAIGN_DIR / "task_seed_profile" / "workspace" / "opengauss_formalqualbench"
DEFAULT_DIRECT_ENV = CAMPAIGN_DIR / "native_direct_all_env.yaml"
DEFAULT_EXPERIMENT = CAMPAIGN_DIR / "experiment.yaml"
DEFAULT_STUDY = CAMPAIGN_DIR / "study.yaml"
DIRECT_SYSTEM = "opengauss-gpt55-direct"
HYPER_SYSTEM = "opengauss-gpt55-hyper-promoted"
OVERRIDE_BUNDLE_ROOT_ENV = "GAUSS_AUTOFORMALIZE_OVERRIDE_BUNDLE_ROOT"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_path(path_value: str, *, base_dir: Path) -> str:
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())
    return str((base_dir / candidate).resolve())


def _load_run_study(hermes_root: Path):
    if not hermes_root.is_dir():
        raise FileNotFoundError(f"Hermes repo not found: {hermes_root}")
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    from hyperagents.study import run_study

    return run_study


def _resolve_experiment_manifest(source: Path, *, entrypoint: Path, output_root: Path) -> Path:
    payload = _load_yaml(source)
    payload["task_seed_profile"] = str((CAMPAIGN_DIR / "task_seed_profile").resolve())
    for benchmark in payload.get("evaluation", {}).get("benchmarks", []) or []:
        benchmark["entrypoint"] = str(entrypoint.resolve())
        config_file = str(benchmark.get("config_file") or "").strip()
        if config_file:
            benchmark["config_file"] = _resolve_path(config_file, base_dir=CAMPAIGN_DIR)
    resolved_path = output_root / "resolved_experiment.yaml"
    resolved_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return resolved_path


def _resolve_study_manifest(source: Path, *, experiment_manifest: Path, output_root: Path) -> Path:
    payload = _load_yaml(source)
    for condition in payload.get("conditions", []) or []:
        condition["experiment_config"] = str(experiment_manifest.resolve())
    resolved_path = output_root / "resolved_study.yaml"
    resolved_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return resolved_path


def _run_direct_system(
    *,
    entrypoint: Path,
    config_path: Path,
    bundle_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    system_root = output_root / "direct" / DIRECT_SYSTEM
    system_root.mkdir(parents=True, exist_ok=True)
    summary_path = system_root / "summary.json"
    samples_path = system_root / "samples.jsonl"
    stdout_path = system_root / "runner.stdout.log"
    stderr_path = system_root / "runner.stderr.log"

    env = dict(os.environ)
    env["HERMES_HYPER_SUMMARY_PATH"] = str(summary_path)
    env["HERMES_HYPER_SAMPLES_PATH"] = str(samples_path)
    env[OVERRIDE_BUNDLE_ROOT_ENV] = str(bundle_root.resolve())

    command = [sys.executable, str(entrypoint), "evaluate", "--config", str(config_path)]
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Direct OpenGauss run failed with exit code {result.returncode}: {stderr_path}")
    payload = _load_json(summary_path)
    payload["summary_path"] = str(summary_path)
    payload["samples_path"] = str(samples_path)
    payload["stdout_path"] = str(stdout_path)
    payload["stderr_path"] = str(stderr_path)
    return payload


def _collect_hyper_result(study_root: Path, study_result: dict[str, Any]) -> dict[str, Any]:
    run_summaries = sorted((study_root / "runs").glob("*/*/summary.json"))
    completed = []
    for path in run_summaries:
        payload = _load_json(path)
        if payload.get("status") == "completed":
            completed.append(payload)
    hyper_run = next(
        (
            payload
            for payload in completed
            if payload.get("condition_name") == "native-hyper" and payload.get("final_test_summary_path")
        ),
        None,
    )
    if hyper_run is None:
        raise RuntimeError("Hyper study completed without a native-hyper final test summary.")
    final_summary_path = Path(str(hyper_run["final_test_summary_path"])).expanduser().resolve()
    final_payload = _load_json(final_summary_path)
    final_payload["summary_path"] = str(final_summary_path)
    final_payload["study_summary_path"] = str(study_result["summary_path"])
    final_payload["study_report_path"] = str(study_result["report_path"])
    final_payload["best_candidate_id"] = hyper_run.get("best_candidate_id")
    return final_payload


def _normalize_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": str(payload.get("system") or ""),
        "backend": str(payload.get("backend") or ""),
        "task_count": int(payload.get("task_count") or 0),
        "solve_count": int(payload.get("solve_count") or 0),
        "mean_score": float(payload.get("mean_score") or 0.0),
        "total_wall_clock_seconds": float(payload.get("total_wall_clock_seconds") or 0.0),
        "total_bash_call_count": int(payload.get("total_bash_call_count") or 0),
        "total_mcp_call_count": int(payload.get("total_mcp_call_count") or 0),
        "total_tool_call_count": int(payload.get("total_tool_call_count") or 0),
        "selection_score": float(payload.get("selection_score") or 0.0),
        "artifact_root": str(payload.get("artifact_root") or ""),
        "summary_path": str(payload.get("summary_path") or ""),
        "samples_path": str(payload.get("samples_path") or ""),
        "stdout_path": str(payload.get("stdout_path") or ""),
        "stderr_path": str(payload.get("stderr_path") or ""),
        "study_summary_path": str(payload.get("study_summary_path") or ""),
        "study_report_path": str(payload.get("study_report_path") or ""),
        "best_candidate_id": payload.get("best_candidate_id"),
        "task_filter": list(payload.get("task_filter") or []),
    }


def _comparison_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# OpenGauss FormalQualBench Native + Hyper Campaign",
        "",
        "| system | backend | solves | mean_score | wall_clock_s | bash | mcp | tool_calls | selection_score |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            "| {system} | {backend} | {solve_count}/{task_count} | {mean_score:.3f} | {total_wall_clock_seconds:.1f} | {total_bash_call_count} | {total_mcp_call_count} | {total_tool_call_count} | {selection_score:.3f} |".format(
                **result
            )
        )
    return "\n".join(lines) + "\n"


def _decision_note(results: list[dict[str, Any]]) -> str:
    by_system = {entry["system"]: entry for entry in results}
    direct = by_system.get(DIRECT_SYSTEM)
    hyper = by_system.get(HYPER_SYSTEM)
    lines = [
        "# OpenGauss Native + Hyper decision note",
        "",
        "- Comparator is the pass/fail authority.",
        "- Hyper mutates only the OpenGauss-owned benchmark bundle.",
    ]
    if direct is not None:
        lines.append(
            f"- `{DIRECT_SYSTEM}`: {direct['solve_count']}/{direct['task_count']} "
            f"with `{direct['total_wall_clock_seconds']:.1f}s` and `{direct['total_tool_call_count']}` tool calls."
        )
    if hyper is not None:
        lines.append(
            f"- `{HYPER_SYSTEM}`: {hyper['solve_count']}/{hyper['task_count']} "
            f"with `{hyper['total_wall_clock_seconds']:.1f}s` and `{hyper['total_tool_call_count']}` tool calls."
        )
    if direct is not None and hyper is not None:
        lines.append(
            f"- Delta (hyper - direct): solves `{hyper['solve_count'] - direct['solve_count']}`, "
            f"wall-clock `{hyper['total_wall_clock_seconds'] - direct['total_wall_clock_seconds']:.1f}s`, "
            f"tool calls `{hyper['total_tool_call_count'] - direct['total_tool_call_count']}`."
        )
    return "\n".join(lines) + "\n"


def run_campaign(
    *,
    hermes_root: Path,
    output_root: Path,
    entrypoint: Path,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    direct_payload = _run_direct_system(
        entrypoint=entrypoint,
        config_path=DEFAULT_DIRECT_ENV,
        bundle_root=DEFAULT_BUNDLE_ROOT,
        output_root=output_root,
    )

    run_study = _load_run_study(hermes_root)
    resolved_experiment = _resolve_experiment_manifest(DEFAULT_EXPERIMENT, entrypoint=entrypoint, output_root=output_root)
    resolved_study = _resolve_study_manifest(DEFAULT_STUDY, experiment_manifest=resolved_experiment, output_root=output_root)
    study_root = output_root / "hyper-study"
    if study_root.exists():
        shutil.rmtree(study_root)
    study_result = run_study(resolved_study, root=study_root)
    hyper_payload = _collect_hyper_result(study_root, study_result)

    results = [_normalize_result(direct_payload), _normalize_result(hyper_payload)]
    comparison = {
        "generated_at": _utc_now(),
        "results": results,
    }
    _write_json(output_root / "comparison_summary.json", comparison)
    (output_root / "comparison_summary.md").write_text(_comparison_markdown(results), encoding="utf-8")
    (output_root / "decision_note.md").write_text(_decision_note(results), encoding="utf-8")
    return comparison


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OpenGauss + Hyper FormalQualBench sanity campaign.")
    parser.add_argument(
        "--hermes-root",
        default=str(DEFAULT_HERMES_ROOT),
        help="Path to the Hermes repo that provides HyperAgents.",
    )
    parser.add_argument(
        "--output-root",
        default="",
        help="Directory for campaign artifacts. Defaults to the Gauss home benchmarks area.",
    )
    parser.add_argument(
        "--entrypoint",
        default=str(DEFAULT_ENTRYPOINT),
        help="Path to the OpenGauss FormalQualBench evaluator entrypoint.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if str(args.output_root).strip()
        else (get_gauss_home() / "benchmarks" / "formalqualbench" / "hyper-campaigns" / datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
    )
    run_campaign(
        hermes_root=Path(args.hermes_root).expanduser().resolve(),
        output_root=output_root,
        entrypoint=Path(args.entrypoint).expanduser().resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
