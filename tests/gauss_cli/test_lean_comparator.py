from __future__ import annotations

from pathlib import Path

from gauss_cli import lean_comparator
from gauss_cli.lean_service import LocalLeanCommandResult
from gauss_cli.project import initialize_gauss_project


def _seed_comparator_project(root: Path) -> tuple[Path, Path]:
    root.mkdir()
    (root / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")
    initialize_gauss_project(root, name="Demo")
    challenge = root / "Challenge.lean"
    solution = root / "Solution.lean"
    challenge.write_text("namespace Demo\n theorem MainTheorem : True := by trivial\nend Demo\n", encoding="utf-8")
    solution.write_text("namespace Demo\n theorem MainTheorem : True := by trivial\nend Demo\n", encoding="utf-8")
    return challenge, solution


def test_local_lean_comparator_check_passes_with_configured_comparator(monkeypatch, tmp_path):
    challenge, solution = _seed_comparator_project(tmp_path / "project")
    comparator = tmp_path / "comparator"
    comparator.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    comparator.chmod(0o755)
    commands: list[list[str]] = []

    def fake_run(command, *, cwd, timeout_seconds):
        del cwd, timeout_seconds
        commands.append(command)
        return LocalLeanCommandResult(command=command, cwd=str(tmp_path), returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(lean_comparator, "_run_local_lean_command", fake_run)

    result = lean_comparator.local_lean_comparator_check(
        challenge_path=challenge,
        solution_path=solution,
        cwd=challenge.parent,
        comparator_binary=comparator,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result["success"] is True
    assert result["verdict"] == "pass"
    assert result["theorem_names"] == ["Demo.MainTheorem"]
    assert commands[0] == ["lake", "build", "Challenge", "Solution"]
    assert commands[1][:2] == ["lake", "env"]
    assert Path(result["comparator_config_path"]).is_file()


def test_local_lean_comparator_check_classifies_illegal_axiom(monkeypatch, tmp_path):
    challenge, solution = _seed_comparator_project(tmp_path / "project")
    comparator = tmp_path / "comparator"
    comparator.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    comparator.chmod(0o755)

    def fake_run(command, *, cwd, timeout_seconds):
        del cwd, timeout_seconds
        if command[:2] == ["lake", "build"]:
            return LocalLeanCommandResult(command=command, cwd=str(tmp_path), returncode=0, stdout="", stderr="")
        return LocalLeanCommandResult(
            command=command,
            cwd=str(tmp_path),
            returncode=1,
            stdout="",
            stderr="illegal axiom Classical.choice2",
        )

    monkeypatch.setattr(lean_comparator, "_run_local_lean_command", fake_run)

    result = lean_comparator.local_lean_comparator_check(
        challenge_path=challenge,
        solution_path=solution,
        cwd=challenge.parent,
        comparator_binary=comparator,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result["success"] is False
    assert result["comparator_valid"] is False
    assert result["verdict"] == "illegal_axiom"


def test_local_lean_comparator_check_reports_missing_comparator(monkeypatch, tmp_path):
    challenge, solution = _seed_comparator_project(tmp_path / "project")

    monkeypatch.setattr(
        lean_comparator,
        "_run_local_lean_command",
        lambda command, *, cwd, timeout_seconds: LocalLeanCommandResult(
            command=command,
            cwd=str(cwd),
            returncode=0,
            stdout="lake ok",
            stderr="",
        ),
    )
    monkeypatch.setattr(lean_comparator, "_find_comparator_binary", lambda *_args, **_kwargs: None)

    result = lean_comparator.local_lean_comparator_check(
        challenge_path=challenge,
        solution_path=solution,
        cwd=challenge.parent,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result["success"] is False
    assert result["verdict"] == "comparator_unavailable"
    assert result["comparator_available"] is False
    assert result["mcp_call_count"] == 0
