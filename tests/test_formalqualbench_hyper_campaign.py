from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


def _load_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "run_formalqualbench_hyper_campaign.py"
    spec = importlib.util.spec_from_file_location("run_formalqualbench_hyper_campaign", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load FormalQualBench Hyper campaign module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_experiment_manifest_absolutizes_profile_and_benchmark_paths(tmp_path: Path):
    module = _load_module()

    resolved_path = module._resolve_experiment_manifest(
        module.DEFAULT_EXPERIMENT,
        entrypoint=module.DEFAULT_ENTRYPOINT,
        output_root=tmp_path,
    )

    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    assert payload["task_seed_profile"] == str((module.CAMPAIGN_DIR / "task_seed_profile").resolve())
    benchmark = payload["evaluation"]["benchmarks"][0]
    assert benchmark["entrypoint"] == str(module.DEFAULT_ENTRYPOINT.resolve())
    assert Path(benchmark["config_file"]).is_absolute()


def test_resolve_study_manifest_points_conditions_at_resolved_experiment(tmp_path: Path):
    module = _load_module()
    experiment_path = tmp_path / "resolved_experiment.yaml"
    experiment_path.write_text("name: demo\n", encoding="utf-8")

    resolved_path = module._resolve_study_manifest(
        module.DEFAULT_STUDY,
        experiment_manifest=experiment_path,
        output_root=tmp_path,
    )

    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    assert payload["conditions"][0]["experiment_config"] == str(experiment_path.resolve())
