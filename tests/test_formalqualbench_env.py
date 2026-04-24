from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from environments.benchmarks.formalqualbench import formalqualbench_env as fq


def test_load_eval_config_defaults_to_top3(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("env: {}\n", encoding="utf-8")

    config = fq.load_eval_config(config_path)

    assert config.backend == "native"
    assert config.task_filter == fq.DEFAULT_TASKS
    assert config.model_name == "gpt-5.5"
    assert config.task_timeout_seconds == 14400
    assert config.stagnation_timeout_seconds == 1800
    assert config.stagnation_grace_seconds == 300
    assert config.reasoning_effort == "medium"


def test_verified8_config_uses_native_codex_lane():
    config = fq.load_eval_config(
        Path(__file__).resolve().parent.parent
        / "environments"
        / "benchmarks"
        / "formalqualbench"
        / "opengauss_verified8.yaml"
    )

    assert config.system_name == "opengauss-gpt55-direct-verified8"
    assert config.backend == "native"
    assert config.model_name == "gpt-5.5"
    assert config.reasoning_effort == "high"
    assert config.auth_provider == "openai-codex"
    assert config.formalqualbench_ref == "efaa113c6a00a79e92842ce541b407d7695d7699"
    assert config.comparator_ref == "11443b99aa874875225c16b55eaa417442a2bb30"
    assert config.lean4export_ref == "ca36c44858e2d7ba40996203d2f08a69113d1211"
    assert config.task_filter == (
        "DeBruijnErdos",
        "JordanDerangementTheorem",
        "ParisHarringtonPrinciple",
        "ColorfulCaratheodoryTheorem",
        "DLOQuantifierElimination",
        "BanachStoneTheorem",
        "GleasonKahaneZelazkoTheorem",
        "VonNeumannDoubleCommutantTheorem",
    )


def test_discover_override_bundle_prefers_explicit_root(monkeypatch, tmp_path: Path):
    bundle_root = tmp_path / "override-bundle"
    hints_dir = bundle_root / "theorem_hints"
    hints_dir.mkdir(parents=True)
    (bundle_root / "instructions.md").write_text("benchmark instructions\n", encoding="utf-8")
    (bundle_root / "startup_context.md").write_text("benchmark context\n", encoding="utf-8")
    (hints_dir / "PontryaginDuality.md").write_text("hint\n", encoding="utf-8")

    monkeypatch.setenv(fq.OVERRIDE_BUNDLE_ROOT_ENV, str(bundle_root))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    bundle = fq._discover_override_bundle()

    assert bundle.root == bundle_root.resolve()
    assert bundle.instructions_template == (bundle_root / "instructions.md").resolve()
    assert bundle.startup_context == (bundle_root / "startup_context.md").resolve()
    assert bundle.theorem_hints_dir == hints_dir.resolve()


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
    lakefile = (workspace_root / "lakefile.toml").read_text(encoding="utf-8")
    assert 'name = "Challenge"' in lakefile
    assert 'name = "Solution"' in lakefile


def test_extract_theorem_names_uses_namespace_prefix(tmp_path: Path):
    challenge_path = tmp_path / "Challenge.lean"
    challenge_path.write_text(
        "\n".join(
            [
                "namespace JordanCycleTheorem",
                "namespace Inner",
                "theorem MainTheorem : True := by trivial",
                "end Inner",
                "end JordanCycleTheorem",
            ]
        ),
        encoding="utf-8",
    )

    assert fq._extract_theorem_names(challenge_path) == ["JordanCycleTheorem.Inner.MainTheorem"]


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
    def fake_run_checked(command, *, cwd, env=None, timeout_seconds=None):
        del cwd, env, timeout_seconds
        if command[:2] == ["lake", "build"]:
            return fq.ProcessResult(returncode=0, stdout="lake ok", stderr="", duration_seconds=2.0)
        if command[:2] == ["lake", "env"]:
            return fq.ProcessResult(returncode=1, stdout="", stderr="comparator failed", duration_seconds=3.0)
        raise AssertionError(f"Unexpected command: {command}")

    def fake_run_native_backend(config, *, command, workspace_root):
        assert config.backend == "native"
        assert config.reasoning_effort == "medium"
        assert command.startswith("/autoformalize FormalQualBench theorem: JordanCycleTheorem.")
        assert workspace_root.name == "JordanCycleTheorem"
        return fq.ProcessResult(returncode=0, stdout="backend ok", stderr="", duration_seconds=1.0)

    monkeypatch.setattr(fq, "_run_checked", fake_run_checked)
    monkeypatch.setattr(fq, "_run_native_backend", fake_run_native_backend)

    config = fq.EvalConfig(backend="native", system_name="opengauss-gpt55-direct")
    result = fq._run_one_task(
        config,
        cached_repo=cached_repo,
        toolchain=fq.ComparatorToolchain(
            comparator_binary=tmp_path / "comparator",
            landrun_binary=tmp_path / "landrun",
            lean4export_binary=tmp_path / "lean4export",
        ),
        output_root=tmp_path / "run",
        task_name="JordanCycleTheorem",
        bundle=fq.OverrideBundle(),
    )

    assert result["task_name"] == "JordanCycleTheorem"
    assert result["theorem_names"] == ["JordanCycleTheorem.MainTheorem"]
    assert result["lake_build_returncode"] == 0
    assert result["comparator_returncode"] == 1
    assert result["comparator_valid"] is False
    assert result["score"] == 0.0
    assert Path(result["challenge_path"]).is_file()
    assert Path(result["solution_path"]).is_file()
    assert Path(result["comparator_config_path"]).is_file()
    comparator_payload = json.loads(Path(result["comparator_config_path"]).read_text(encoding="utf-8"))
    assert comparator_payload["theorem_names"] == ["JordanCycleTheorem.MainTheorem"]


def test_native_backend_disables_ambient_context_for_benchmarks(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_run_native_lean_workflow(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

        class Result:
            success = True
            final_response = "ok"
            error = ""

        return Result()

    monkeypatch.setattr(fq, "run_native_lean_workflow", fake_run_native_lean_workflow)
    config = fq.EvalConfig(model_name="gpt-5.5", reasoning_effort="high")

    result = fq._run_native_backend(config, command="/autoformalize test", workspace_root=tmp_path)

    assert result.returncode == 0
    assert captured["command"] == "/autoformalize test"
    assert captured["kwargs"]["cwd"] == tmp_path
    assert captured["kwargs"]["model"] == "gpt-5.5"
    assert captured["kwargs"]["reasoning_effort"] == "high"
    assert captured["kwargs"]["skip_context_files"] is True
    assert captured["kwargs"]["skip_memory"] is True


def test_evaluate_config_writes_summary_with_call_counts_and_artifacts(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "env": {
                    "system_name": "opengauss-gpt55-direct",
                    "backend": "native",
                    "task_filter": ["JordanCycleTheorem", "BurnsidePrimeDegreeTheorem"],
                },
                "openai": {"model_name": "gpt-5.5"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"
    samples_path = tmp_path / "samples.jsonl"
    monkeypatch.setenv(fq.SUMMARY_ENV, str(summary_path))
    monkeypatch.setenv(fq.SAMPLES_ENV, str(samples_path))
    monkeypatch.setattr(fq, "_discover_override_bundle", lambda: fq.OverrideBundle())

    def fake_git_checkout(repo_url, revision, destination):
        del repo_url, revision
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "lean-toolchain").write_text("leanprover/lean4:v4.28.0\n", encoding="utf-8")
        return destination

    monkeypatch.setattr(fq, "_ensure_git_checkout", fake_git_checkout)
    monkeypatch.setattr(fq, "_prime_formalqualbench_cache", lambda cached_repo: None)
    monkeypatch.setattr(
        fq,
        "_ensure_comparator_toolchain",
        lambda config, cache_root, expected_lean_toolchain: fq.ComparatorToolchain(
            comparator_binary=cache_root / "comparator",
            landrun_binary=cache_root / "landrun",
            lean4export_binary=cache_root / "lean4export",
        ),
    )

    def fake_run_one_task(config, *, cached_repo, toolchain, output_root, task_name, bundle):
        del cached_repo, toolchain, bundle
        score = 1.0 if task_name == "JordanCycleTheorem" else 0.0
        artifact_dir = output_root / "artifacts" / task_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return {
            "task_name": task_name,
            "backend": config.backend,
            "system": config.system_name,
            "artifact_dir": str(artifact_dir),
            "challenge_path": str(output_root / f"{task_name}-Challenge.lean"),
            "solution_path": str(output_root / f"{task_name}-Solution.lean"),
            "comparator_config_path": str(output_root / f"{task_name}-comparator.json"),
            "comparator_valid": bool(score),
            "score": score,
            "wall_clock_seconds": 5.0 if score else 7.0,
            "bash_call_count": 0,
            "mcp_call_count": 0,
        }

    monkeypatch.setattr(fq, "_run_one_task", fake_run_one_task)

    summary = fq.evaluate_config(config_path)

    assert summary["system"] == "opengauss-gpt55-direct"
    assert summary["backend"] == "native"
    assert summary["lean_toolchain"] == "leanprover/lean4:v4.28.0"
    assert summary["task_count"] == 2
    assert summary["solve_count"] == 1
    assert summary["total_bash_call_count"] == 0
    assert summary["total_mcp_call_count"] == 0
    assert summary["total_tool_call_count"] == 0
    assert summary["selection_score"] == 999988000.0
    assert summary["artifact_root"] == str(summary_path.parent)
    assert summary_path.exists()
    assert samples_path.exists()
    lines = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2


def test_assert_matching_lean_toolchain_rejects_mismatch(tmp_path: Path):
    root = tmp_path / "component"
    root.mkdir()
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.30.0-rc2\n", encoding="utf-8")

    try:
        fq._assert_matching_lean_toolchain("lean4export", root, "leanprover/lean4:v4.28.0")
    except RuntimeError as exc:
        assert "Lean toolchain mismatch" in str(exc)
        assert "lean4export" in str(exc)
    else:
        raise AssertionError("Expected mismatched Lean toolchain to raise")


def test_pin_lake_manifest_package_rewrites_revision(tmp_path: Path):
    root = tmp_path / "comparator"
    package_root = root / ".lake" / "packages" / "lean4export"
    package_root.mkdir(parents=True)
    manifest = {
        "version": "1.1.0",
        "packagesDir": ".lake/packages",
        "packages": [
            {
                "url": "https://github.com/leanprover/lean4export",
                "type": "git",
                "rev": "old",
                "name": "lean4export",
                "inputRev": "master",
            }
        ],
        "name": "Comparator",
    }
    (root / "lake-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    changed = fq._pin_lake_manifest_package(root, "lean4export", "new")

    payload = json.loads((root / "lake-manifest.json").read_text(encoding="utf-8"))
    assert changed is True
    assert payload["packages"][0]["rev"] == "new"
    assert payload["packages"][0]["inputRev"] == "new"


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
        idle_timeout_seconds=2,
        idle_grace_seconds=0,
        poll_seconds=1,
    )

    assert result.returncode == 0
    assert result.timed_out is False
    assert result.idle_timed_out is False
