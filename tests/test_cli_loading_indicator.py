"""Regression tests for loading feedback on slow slash commands."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cli as cli_mod
from cli import GaussCLI


class TestCLILoadingIndicator:
    def _make_cli(self):
        cli_obj = GaussCLI.__new__(GaussCLI)
        cli_obj._app = None
        cli_obj._last_invalidate = 0.0
        cli_obj._command_running = False
        cli_obj._command_status = ""
        cli_obj._active_handoff_cwd = lambda: "/tmp"
        cli_obj._invalidate = MagicMock()
        cli_obj.console = MagicMock()
        cli_obj.config = {}
        cli_obj._project_override_root = None
        cli_obj.max_turns = 90
        cli_obj.session_id = "sess-test"
        cli_obj._session_db = None
        cli_obj._on_tool_progress = MagicMock()
        return cli_obj

    def test_autoformalize_command_sets_busy_state_and_prints_status(self, capsys):
        cli_obj = self._make_cli()
        seen = {}

        def fake_run_native(*_args, **_kwargs):
            seen["running"] = cli_obj._command_running
            seen["status"] = cli_obj._command_status
            return SimpleNamespace(final_response="autoformalize done", error="", success=True)

        class PrintConsole:
            def print(self, value):
                print(value)

        with patch.object(cli_mod, "run_native_lean_workflow", side_effect=fake_run_native), \
             patch.object(cli_mod, "ChatConsole", return_value=PrintConsole()):
            assert cli_obj.process_command("/autoformalize prove the main lemma")

        output = capsys.readouterr().out
        assert "⏳ Running native OpenGauss Lean workflow..." in output
        assert "autoformalize done" in output
        assert seen == {
            "running": True,
            "status": "Running native OpenGauss Lean workflow...",
        }
        assert cli_obj._command_running is False
        assert cli_obj._command_status == ""
        assert cli_obj._invalidate.call_count == 2

    def test_handoff_alias_uses_the_same_busy_state(self, capsys):
        cli_obj = self._make_cli()
        seen = {}

        def fake_run_native(command, **_kwargs):
            seen["command"] = command
            seen["running"] = cli_obj._command_running
            seen["status"] = cli_obj._command_status
            return SimpleNamespace(final_response="handoff alias done", error="", success=True)

        class PrintConsole:
            def print(self, value):
                print(value)

        with patch.object(cli_mod, "run_native_lean_workflow", side_effect=fake_run_native), \
             patch.object(cli_mod, "ChatConsole", return_value=PrintConsole()):
            assert cli_obj.process_command("/handoff prove the base case")

        output = capsys.readouterr().out
        assert "⏳ Running native OpenGauss Lean workflow..." in output
        assert "handoff alias done" in output
        assert seen["command"] == "/autoformalize prove the base case"
        assert seen == {
            "command": "/autoformalize prove the base case",
            "running": True,
            "status": "Running native OpenGauss Lean workflow...",
        }
        assert cli_obj._command_running is False
        assert cli_obj._command_status == ""
        assert cli_obj._invalidate.call_count == 2

    def test_busy_state_falls_back_to_ascii_prefix_when_unicode_is_disabled(self, capsys, monkeypatch):
        cli_obj = self._make_cli()
        monkeypatch.setattr(cli_mod, "supports_unicode", lambda *_args, **_kwargs: False)
        monkeypatch.setattr(cli_mod, "supports_ansi", lambda *_args, **_kwargs: False)

        with cli_obj._busy_command("Running native OpenGauss Lean workflow..."):
            print("done")

        output = capsys.readouterr().out
        assert "... Running native OpenGauss Lean workflow..." in output
        assert "⏳" not in output
        assert "done" in output
