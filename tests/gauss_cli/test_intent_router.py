"""Tests for deterministic plain-language Lean command routing."""

from gauss_cli.intent_router import route_intent


def _command(text: str) -> str | None:
    candidate = route_intent(text, active_cwd="/tmp/project", chat_mode=False)
    return candidate.command if candidate else None


def test_routes_lean_learning_commands():
    assert _command("check Main.lean") == "/check Main.lean"
    assert _command("build") == "/build"
    assert _command("goals Main.lean:12") == "/goals Main.lean:12"
    assert _command("@lean symbols compact") == "/symbols compact"


def test_routes_project_and_workflow_commands():
    assert _command("project status") == "/project status"
    assert _command("@project status") == "/project status"
    assert _command("prove theorem X") == "/prove theorem X"


def test_unrelated_chat_is_not_routed():
    assert route_intent("what is the intuition behind this proof?") is None
