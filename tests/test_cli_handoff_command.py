"""Tests for native Lean workflow dispatch and the legacy `/handoff` alias."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cli as cli_mod
from cli import GaussCLI


def _make_cli():
    cli_obj = GaussCLI.__new__(GaussCLI)
    cli_obj._app = None
    cli_obj.console = MagicMock()
    cli_obj.config = {"gauss": {"autoformalize": {"backend": "native"}}}
    cli_obj._project_override_root = None
    cli_obj._chat_mode_enabled = False
    cli_obj._pending_input = MagicMock()
    cli_obj._active_handoff_cwd = lambda: "/tmp"
    cli_obj._invalidate = MagicMock()
    cli_obj._command_running = False
    cli_obj._command_status = ""
    cli_obj._last_invalidate = 0.0
    cli_obj.max_turns = 90
    cli_obj.session_id = "sess-test"
    cli_obj._session_db = None
    cli_obj._on_tool_progress = MagicMock()
    return cli_obj


def test_autoformalize_dispatches_to_native_runner():
    cli_obj = _make_cli()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(final_response="done", error="", success=True)

    with patch.object(cli_mod, "run_native_lean_workflow", side_effect=fake_run), \
         patch.object(cli_mod, "ChatConsole", return_value=cli_obj.console):
        assert cli_obj.process_command("/autoformalize prove the main theorem") is True

    assert captured["command"] == "/autoformalize prove the main theorem"
    assert captured["kwargs"]["max_iterations"] == 90
    assert captured["kwargs"]["session_id"] == "sess-test"
    cli_obj.console.print.assert_called_with("done")


def test_prove_dispatches_to_native_runner():
    cli_obj = _make_cli()

    with patch.object(cli_obj, "_handle_native_workflow_command") as mock_handle:
        assert cli_obj.process_command("/prove Main.lean") is True

    mock_handle.assert_called_once_with("/prove Main.lean")


def test_handoff_alias_rewrites_to_autoformalize():
    cli_obj = _make_cli()

    with patch.object(cli_obj, "_handle_autoformalize_command") as mock_handle:
        assert cli_obj.process_command("/handoff prove the base case") is True

    cli_obj.console.print.assert_called_once()
    assert "/handoff" in cli_obj.console.print.call_args[0][0]
    assert "/autoformalize" in cli_obj.console.print.call_args[0][0]
    mock_handle.assert_called_once_with("/autoformalize prove the base case")


def test_managed_chat_status_points_to_native_lean_path():
    cli_obj = _make_cli()
    cli_obj._app = object()

    with patch.object(cli_obj, "_active_managed_backend_name", return_value="codex"):
        assert cli_obj.process_command("/managed-chat status") is True

    rendered = "\n".join(call.args[0] for call in cli_obj.console.print.call_args_list)
    assert "legacy escape hatch" in rendered
    assert "Native Lean workflows run through OpenGauss directly" in rendered
    assert "/chat" in rendered
