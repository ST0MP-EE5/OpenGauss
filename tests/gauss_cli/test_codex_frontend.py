from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import gauss_cli.main as main_mod
from gauss_cli import codex_frontend


def test_prepare_codex_frontend_auto_selects_checked_in_lean4(monkeypatch, tmp_path):
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.chdir(main_mod.PROJECT_ROOT)

    plan = codex_frontend.prepare_codex_frontend(env={"PATH": str(tmp_path)}, cwd=main_mod.PROJECT_ROOT)

    assert plan.project.root == main_mod.PROJECT_ROOT / "Lean4"
    assert plan.model == "gpt-5.5"
    assert plan.reasoning_effort == "high"
    assert plan.codex_home == plan.project.runtime_dir / "codex-frontend" / "codex-home"
    assert plan.config_path.is_file()
    assert plan.instructions_path.is_file()
    config_text = plan.config_path.read_text(encoding="utf-8")
    assert 'model = "gpt-5.5"' in config_text
    assert 'model_reasoning_effort = "high"' in config_text
    assert "[mcp_servers.opengauss]" in config_text
    assert "gauss_cli.main" in config_text
    instructions = plan.instructions_path.read_text(encoding="utf-8")
    assert "OpenGauss owns the Lean project" in instructions
    assert "MCP is only the local transport adapter" in instructions
    assert "gauss_lean_lake_build" in instructions
    assert "gauss_lean_check_file" in instructions


def test_prepare_codex_frontend_allows_explicit_project(monkeypatch, tmp_path):
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    project_root = tmp_path / "FoM"
    project_root.mkdir()
    (project_root / "lakefile.toml").write_text("[[lean_lib]]\nname = \"FoM\"\n", encoding="utf-8")
    (project_root / "lean-toolchain").write_text("leanprover/lean4:v4.28.0\n", encoding="utf-8")
    from gauss_cli.project import initialize_gauss_project

    initialize_gauss_project(project_root, name="FoM")

    plan = codex_frontend.prepare_codex_frontend(
        env={"PATH": str(tmp_path)},
        cwd=tmp_path,
        project_path="FoM",
    )

    assert plan.project.root == project_root
    assert plan.active_cwd == project_root


def test_prepare_codex_frontend_stages_lean4_skill_and_lsp_mcp(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex_bin = bin_dir / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    uvx_bin = bin_dir / "uvx"
    uvx_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    uvx_bin.chmod(0o755)
    skill_source = tmp_path / "lean4-skill"
    (skill_source / "references").mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("# Lean4 Skill\n", encoding="utf-8")
    (skill_source / "references" / "proof.md").write_text("proof workflow\n", encoding="utf-8")

    plan = codex_frontend.prepare_codex_frontend(
        env={
            "PATH": str(bin_dir),
            "GAUSS_LEAN4_SKILLS_PATH": str(skill_source),
            "GAUSS_LEAN_LSP_MCP_SPEC": "lean-lsp-mcp-test",
        },
        cwd=main_mod.PROJECT_ROOT,
    )

    assert plan.lean4_skill_path == plan.codex_home / "skills" / "lean4"
    assert (plan.lean4_skill_path / "SKILL.md").read_text(encoding="utf-8") == "# Lean4 Skill\n"
    assert (plan.lean4_skill_path / "references" / "proof.md").is_file()
    config_text = plan.config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.lean-lsp]" in config_text
    assert str(uvx_bin) in config_text
    assert "lean-lsp-mcp-test" in config_text
    assert "LEAN_PROJECT_PATH" in config_text
    instructions = plan.instructions_path.read_text(encoding="utf-8")
    assert "Lean4 skill path" in instructions
    assert "upstream Lean LSP goal-state behavior" in instructions


def test_prepare_codex_frontend_allows_explicit_mcp_python(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex_bin = bin_dir / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    mcp_python = tmp_path / "python"
    mcp_python.write_text("#!/bin/sh\n", encoding="utf-8")
    mcp_python.chmod(0o755)

    plan = codex_frontend.prepare_codex_frontend(
        env={"PATH": str(bin_dir), "GAUSS_MCP_PYTHON": str(mcp_python)},
        cwd=main_mod.PROJECT_ROOT,
    )

    config_text = plan.config_path.read_text(encoding="utf-8")
    assert f'command = "{mcp_python}"' in config_text


def test_bare_gauss_launches_codex_frontend(monkeypatch):
    captured = {}

    def fake_launch(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.chdir(main_mod.PROJECT_ROOT)
    monkeypatch.setattr(sys, "argv", ["gauss"])
    monkeypatch.setattr(main_mod, "launch_codex_frontend", fake_launch, raising=False)
    monkeypatch.setattr("gauss_cli.codex_frontend.launch_codex_frontend", fake_launch)

    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 0
    assert captured["cwd"] == Path.cwd()
    assert captured["project_path"] is None
    assert captured["model"] is None
    assert captured["reasoning_effort"] is None
    assert captured["query"] is None


def test_gauss_query_uses_codex_exec(monkeypatch, tmp_path):
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    plan = codex_frontend.prepare_codex_frontend(
        env={"PATH": str(tmp_path)},
        cwd=main_mod.PROJECT_ROOT,
        query="check the project",
    )

    assert plan.argv[:4] == (str(codex_bin), "exec", "--skip-git-repo-check", "--color")
    assert "--dangerously-bypass-approvals-and-sandbox" in plan.argv
    assert "check the project" in plan.argv[-1]
    assert "Use the OpenGauss MCP tools as the primary interface" in plan.argv[-1]
    assert "gauss_lean_project_status" in plan.argv[-1]
    assert "gauss_lean_check_file" in plan.argv[-1]
    assert "Do not call `gauss`, `lake`, `lean`, or ad hoc Python subprocesses" in plan.argv[-1]


def test_launch_codex_frontend_invokes_codex(monkeypatch, tmp_path):
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    codex_bin.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    captured = {}

    def fake_run(argv, *, cwd, env, check):
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["env"] = env
        captured["check"] = check
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(codex_frontend.subprocess, "run", fake_run)

    assert codex_frontend.launch_codex_frontend(cwd=main_mod.PROJECT_ROOT) == 0
    assert captured["argv"][0] == str(codex_bin)
    assert captured["argv"][1] == "--dangerously-bypass-approvals-and-sandbox"
    assert captured["cwd"] == main_mod.PROJECT_ROOT / "Lean4"
    assert captured["env"]["GAUSS_ACTIVE_PROJECT"].endswith("/Lean4")


def test_legacy_lean4_launcher_subcommand_is_removed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gauss", "lean4"])

    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 2
