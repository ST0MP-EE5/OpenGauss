"""Tests for non-interactive setup and first-run headless behavior."""

from unittest.mock import patch

from argparse import Namespace


def _make_setup_args(**overrides):
    return Namespace(
        non_interactive=overrides.get("non_interactive", False),
        section=overrides.get("section", None),
        reset=overrides.get("reset", False),
    )


class TestNonInteractiveSetup:
    """Verify setup paths exit cleanly in headless/non-interactive environments."""

    def test_non_interactive_flag_skips_wizard(self, capsys):
        """--non-interactive should print guidance and not enter the wizard."""
        from gauss_cli.setup import run_setup_wizard

        args = _make_setup_args(non_interactive=True)

        with (
            patch("gauss_cli.setup.ensure_gauss_home"),
            patch("gauss_cli.setup.load_config", return_value={}),
            patch("gauss_cli.setup.get_gauss_home", return_value="/tmp/.gauss"),
            patch("gauss_cli.auth.get_active_provider", side_effect=AssertionError("wizard continued")),
            patch("builtins.input", side_effect=AssertionError("input should not be called")),
        ):
            run_setup_wizard(args)

        out = capsys.readouterr().out
        assert "gauss config set model.provider custom" in out

    def test_no_tty_skips_wizard(self, capsys):
        """When stdin has no TTY, the setup wizard should print guidance and return."""
        from gauss_cli.setup import run_setup_wizard

        args = _make_setup_args(non_interactive=False)

        with (
            patch("gauss_cli.setup.ensure_gauss_home"),
            patch("gauss_cli.setup.load_config", return_value={}),
            patch("gauss_cli.setup.get_gauss_home", return_value="/tmp/.gauss"),
            patch("gauss_cli.auth.get_active_provider", side_effect=AssertionError("wizard continued")),
            patch("sys.stdin") as mock_stdin,
            patch("builtins.input", side_effect=AssertionError("input should not be called")),
        ):
            mock_stdin.isatty.return_value = False
            run_setup_wizard(args)

        out = capsys.readouterr().out
        assert "gauss config set model.provider custom" in out
