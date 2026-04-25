from __future__ import annotations

import sys
from argparse import Namespace

import pytest

import gauss_cli.main as main_mod


def test_repo_root_applies_native_lean_defaults(monkeypatch):
    monkeypatch.chdir(main_mod.PROJECT_ROOT)
    monkeypatch.delenv("TERMINAL_CWD", raising=False)
    args = Namespace(model=None, provider=None, toolsets=None)

    assert main_mod._apply_native_lean_defaults(args) is True

    assert args.model == "gpt-5.5"
    assert args.provider == "openai-codex"
    assert args.toolsets == "opengauss-lean"
    assert main_mod.os.environ["TERMINAL_CWD"] == str(main_mod.LEAN4_WORKSPACE_ROOT)


def test_bare_gauss_from_repo_root_dispatches_native_lean_chat(monkeypatch):
    captured = {}

    def fake_cmd_chat(args):
        captured["model"] = args.model
        captured["provider"] = args.provider
        captured["toolsets"] = args.toolsets

    monkeypatch.chdir(main_mod.PROJECT_ROOT)
    monkeypatch.setattr(sys, "argv", ["gauss"])
    monkeypatch.setattr(main_mod, "_has_any_provider_configured", lambda: True)
    monkeypatch.setattr(main_mod, "cmd_chat", fake_cmd_chat)

    main_mod.main()

    assert captured == {
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "toolsets": "opengauss-lean",
    }


def test_legacy_lean4_launcher_subcommand_is_removed(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gauss", "lean4"])

    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 2


def test_bench_formalqual_run_cli_dispatches_native_service(monkeypatch, tmp_path):
    captured = {}
    config_path = tmp_path / "formalqual.yaml"
    config_path.write_text("env: {}\n", encoding="utf-8")

    def fake_cmd_bench(args):
        captured["bench_suite"] = args.bench_suite
        captured["formalqual_action"] = args.formalqual_action
        captured["config"] = args.config

    monkeypatch.setattr(sys, "argv", ["gauss", "bench", "formalqual", "run", "--config", str(config_path)])
    monkeypatch.setattr(main_mod, "cmd_bench", fake_cmd_bench)

    main_mod.main()

    assert captured == {
        "bench_suite": "formalqual",
        "formalqual_action": "run",
        "config": str(config_path),
    }
