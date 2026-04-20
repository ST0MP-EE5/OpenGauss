from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

from environments.benchmarks.formalqualbench import formalqualbench_env as fq


def test_load_eval_config_defaults_to_top3(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("env: {}\n", encoding="utf-8")

    config = fq.load_eval_config(config_path)

    assert config.backend == "forge"
    assert config.task_filter == fq.DEFAULT_TASKS
    assert config.model_name == "gpt-5.4"
    assert config.task_timeout_seconds == 14400
    assert config.stagnation_timeout_seconds == 1800
    assert config.stagnation_grace_seconds == 300


def test_prepare_task_workspace_emits_challenge_and_solution(tmp_path: Path):
    cached_repo = tmp_path / "formalqualbench-cache"
    cached_repo.mkdir(parents=True)
    (cached_repo / "lakefile.toml").write_text("name = \"FormalQualBench\"\n", encoding="utf-8")
    task_dir = cached_repo / "FormalQualBench" / "JordanCycleTheorem"
    task_dir.mkdir(parents=True)
    challenge_text = "theorem MainTheorem : True := by sorry\n"
    (task_dir / "Main.lean").write_text(challenge_text, encoding="utf-8")

    workspace_root, artifact_dir, challenge_path, solution_path = fq._prepare_task_workspace(
        cached_repo,
        tmp_path / "run",
        "JordanCycleTheorem",
    )

    assert workspace_root.exists()
    assert artifact_dir.exists()
    assert (workspace_root / ".gauss" / "project.yaml").is_file()
    assert challenge_path.read_text(encoding="utf-8") == challenge_text
    assert solution_path.read_text(encoding="utf-8") == challenge_text


def test_run_one_task_requires_comparator_success(monkeypatch, tmp_path: Path):
    cached_repo = tmp_path / "formalqualbench-cache"
    cached_repo.mkdir(parents=True)
    (cached_repo / "lakefile.toml").write_text("name = \"FormalQualBench\"\n", encoding="utf-8")
    task_dir = cached_repo / "FormalQualBench" / "JordanCycleTheorem"
    task_dir.mkdir(parents=True)
    (task_dir / "Main.lean").write_text(
        "namespace JordanCycleTheorem\n theorem MainTheorem : True := by sorry\nend JordanCycleTheorem\n",
        encoding="utf-8",
    )
    helper_dir = tmp_path / "helpers"
    helper_dir.mkdir()
    (helper_dir / "bash").write_text("#!/bin/sh\nexec /bin/bash \"$@\"\n", encoding="utf-8")
    (helper_dir / "bash").chmod(0o755)
    mcp_proxy_path = tmp_path / "mcp_proxy.py"
    mcp_proxy_path.write_text("print('proxy')\n", encoding="utf-8")

    monkeypatch.setattr(
        fq,
        "resolve_autoformalize_request",
        lambda *args, **kwargs: SimpleNamespace(
            handoff_request=SimpleNamespace(
                argv=("/usr/bin/forge", "-p", "prompt"),
                cwd=str(tmp_path),
                env={"PATH": "/usr/bin"},
            )
        ),
    )

    def fake_run_checked(command, *, cwd, env=None, timeout_seconds=None):
        del cwd, env, timeout_seconds
        if command[:2] == ["lake", "build"]:
            return fq.ProcessResult(returncode=0, stdout="lake ok", stderr="", duration_seconds=2.0)
        if command[:2] == ["lake", "env"]:
            return fq.ProcessResult(returncode=1, stdout="", stderr="comparator failed", duration_seconds=3.0)
        raise AssertionError(f"Unexpected command: {command}")

    def fake_run_checked_with_stagnation(
        command,
        *,
        cwd,
        env=None,
        timeout_seconds=None,
        progress_paths=None,
        idle_timeout_seconds=0,
        idle_grace_seconds=0,
        poll_seconds=0,
    ):
        del cwd, env, timeout_seconds, progress_paths, idle_timeout_seconds, idle_grace_seconds, poll_seconds
        if command[0] == "/usr/bin/forge":
            return fq.ProcessResult(returncode=0, stdout="backend ok", stderr="", duration_seconds=1.0)
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(fq, "_run_checked", fake_run_checked)
    monkeypatch.setattr(fq, "_run_checked_with_stagnation", fake_run_checked_with_stagnation)

    config = fq.EvalConfig(backend="forge", system_name="opengauss-forge-gpt54-direct")
    result = fq._run_one_task(
        config,
        cached_repo=cached_repo,
        comparator_binary=tmp_path / "comparator",
        output_root=tmp_path / "run",
        helper_dir=helper_dir,
        mcp_proxy_path=mcp_proxy_path,
        task_name="JordanCycleTheorem",
        bundle=fq.OverrideBundle(),
    )

    assert result["task_name"] == "JordanCycleTheorem"
    assert result["theorem_names"] == ["MainTheorem"]
    assert result["lake_build_returncode"] == 0
    assert result["comparator_returncode"] == 1
    assert result["comparator_valid"] is False
    assert result["score"] == 0.0
    assert Path(result["challenge_path"]).is_file()
    assert Path(result["solution_path"]).is_file()
    assert Path(result["comparator_config_path"]).is_file()
    comparator_payload = json.loads(Path(result["comparator_config_path"]).read_text(encoding="utf-8"))
    assert comparator_payload["theorem_names"] == ["MainTheorem"]


def test_evaluate_config_writes_summary_with_call_counts_and_artifacts(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "env": {
                    "system_name": "opengauss-forge-hyper-promoted",
                    "backend": "forge",
                    "task_filter": ["JordanCycleTheorem", "BurnsidePrimeDegreeTheorem"],
                },
                "openai": {"model_name": "gpt-5.4"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"
    samples_path = tmp_path / "samples.jsonl"
    monkeypatch.setenv(fq.SUMMARY_ENV, str(summary_path))
    monkeypatch.setenv(fq.SAMPLES_ENV, str(samples_path))
    monkeypatch.setattr(fq, "_ensure_helpers", lambda output_root: (output_root / ".helpers", output_root / ".helpers" / "bash", output_root / ".helpers" / "mcp_proxy.py"))
    monkeypatch.setattr(fq, "_discover_override_bundle", lambda: fq.OverrideBundle())
    monkeypatch.setattr(fq, "_ensure_git_checkout", lambda repo_url, revision, destination: destination)
    monkeypatch.setattr(fq, "_ensure_comparator_binary", lambda config, cache_root: cache_root / "comparator")

    def fake_run_one_task(config, *, cached_repo, comparator_binary, output_root, helper_dir, mcp_proxy_path, task_name, bundle):
        del config, cached_repo, comparator_binary, helper_dir, mcp_proxy_path, bundle
        score = 1.0 if task_name == "JordanCycleTheorem" else 0.0
        artifact_dir = output_root / "artifacts" / task_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return {
            "task_name": task_name,
            "backend": "forge",
            "system": "opengauss-forge-hyper-promoted",
            "artifact_dir": str(artifact_dir),
            "challenge_path": str(output_root / f"{task_name}-Challenge.lean"),
            "solution_path": str(output_root / f"{task_name}-Solution.lean"),
            "comparator_config_path": str(output_root / f"{task_name}-comparator.json"),
            "comparator_valid": bool(score),
            "score": score,
            "wall_clock_seconds": 5.0 if score else 7.0,
            "bash_call_count": 3 if score else 4,
            "mcp_call_count": 2 if score else 5,
        }

    monkeypatch.setattr(fq, "_run_one_task", fake_run_one_task)

    summary = fq.evaluate_config(config_path)

    assert summary["system"] == "opengauss-forge-hyper-promoted"
    assert summary["backend"] == "forge"
    assert summary["task_count"] == 2
    assert summary["solve_count"] == 1
    assert summary["total_bash_call_count"] == 7
    assert summary["total_mcp_call_count"] == 7
    assert summary["total_tool_call_count"] == 14
    assert summary["selection_score"] == 999987986.0
    assert summary["artifact_root"] == str(summary_path.parent)
    assert summary_path.exists()
    assert samples_path.exists()
    lines = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2


def test_run_checked_with_stagnation_times_out_when_no_progress(tmp_path: Path):
    stagnant_file = tmp_path / "stagnant.txt"
    stagnant_file.write_text("still\n", encoding="utf-8")

    result = fq._run_checked_with_stagnation(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        progress_paths=[stagnant_file],
        idle_timeout_seconds=1,
        idle_grace_seconds=0,
        poll_seconds=1,
    )

    assert result.timed_out is True
    assert result.idle_timed_out is True
    assert result.returncode is None
    assert result.error == "No progress detected for 1s"


def test_run_checked_with_stagnation_allows_progress_updates(tmp_path: Path):
    progress_file = tmp_path / "progress.txt"
    progress_file.write_text("start\n", encoding="utf-8")
    script = (
        "from pathlib import Path; import time; "
        "p = Path('progress.txt'); "
        "time.sleep(0.2); p.write_text('updated\\n', encoding='utf-8'); "
        "time.sleep(0.2)"
    )

    result = fq._run_checked_with_stagnation(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        progress_paths=[progress_file],
        idle_timeout_seconds=1,
        idle_grace_seconds=0,
        poll_seconds=1,
    )

    assert result.returncode == 0
    assert result.timed_out is False
    assert result.idle_timed_out is False
