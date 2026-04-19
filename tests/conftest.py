"""Shared fixtures for the gauss-agent test suite."""

import asyncio
import os
import signal
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OPTIONAL_TEST_PREFIXES = (
    "tests/acp",
    "tests/gateway",
)
OPTIONAL_TEST_FILES = {
    "tests/tools/test_transcription.py",
    "tests/tools/test_transcription_tools.py",
}
LEGACY_TEST_FILES = {
    "tests/gauss_cli/test_doctor.py",
    "tests/gauss_cli/test_setup_openclaw_migration.py",
    "tests/gauss_cli/test_update_check.py",
    "tests/test_cli_status_bar.py",
    "tests/test_model_tools.py",
    "tests/tools/test_delegate.py",
    "tests/tools/test_mcp_tool.py",
}


def _flag_enabled(name: str) -> bool:
    value = str(os.getenv(name, "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _relative_repo_path(path: object) -> str:
    try:
        resolved = Path(str(path)).resolve()
    except Exception:
        return ""
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _test_surface(path: object) -> str | None:
    relative = _relative_repo_path(path)
    if not relative.startswith("tests/"):
        return None
    if any(relative == prefix or relative.startswith(f"{prefix}/") for prefix in OPTIONAL_TEST_PREFIXES):
        return "optional"
    if relative in OPTIONAL_TEST_FILES:
        return "optional"
    if relative in LEGACY_TEST_FILES:
        return "legacy"
    return "core"


def pytest_addoption(parser):
    parser.addoption(
        "--run-optional",
        action="store_true",
        default=_flag_enabled("GAUSS_RUN_OPTIONAL_TESTS"),
        help="Collect and run optional non-core test surfaces (ACP, gateway, voice/transcription).",
    )
    parser.addoption(
        "--run-legacy",
        action="store_true",
        default=_flag_enabled("GAUSS_RUN_LEGACY_TESTS"),
        help="Collect and run legacy or experimental non-core test surfaces.",
    )


def pytest_ignore_collect(collection_path, config):
    surface = _test_surface(collection_path)
    if surface == "optional" and not config.getoption("run_optional"):
        return True
    if surface == "legacy" and not config.getoption("run_legacy"):
        return True
    return False


def pytest_collection_modifyitems(config, items):
    for item in items:
        surface = _test_surface(getattr(item, "path", item.fspath))
        if surface is None:
            continue
        item.add_marker(getattr(pytest.mark, surface))


@pytest.fixture(autouse=True)
def _isolate_gauss_home(tmp_path, monkeypatch):
    """Redirect GAUSS_HOME to a temp dir so tests never write to ~/.gauss/."""
    fake_home = tmp_path / "gauss_test"
    fake_home.mkdir()
    (fake_home / "sessions").mkdir()
    (fake_home / "cron").mkdir()
    (fake_home / "memories").mkdir()
    (fake_home / "skills").mkdir()
    monkeypatch.setenv("GAUSS_HOME", str(fake_home))
    # Reset plugin singleton so tests don't leak plugins from ~/.gauss/plugins/
    try:
        import gauss_cli.plugins as _plugins_mod
        monkeypatch.setattr(_plugins_mod, "_plugin_manager", None)
    except Exception:
        pass
    # Tests should not inherit the agent's current gateway/messaging surface.
    # Individual tests that need gateway behavior set these explicitly.
    monkeypatch.delenv("GAUSS_SESSION_PLATFORM", raising=False)
    monkeypatch.delenv("GAUSS_SESSION_CHAT_ID", raising=False)
    monkeypatch.delenv("GAUSS_SESSION_CHAT_NAME", raising=False)
    monkeypatch.delenv("GAUSS_GATEWAY_SESSION", raising=False)


@pytest.fixture(autouse=True)
def _clear_host_api_env(monkeypatch):
    """Prevent host API keys and local auth state from leaking into tests."""
    for key in (
        "EXA_API_KEY",
        "PARALLEL_API_KEY",
        "FIRECRAWL_API_KEY",
        "FIRECRAWL_API_URL",
        "TAVILY_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "VOICE_TOOLS_OPENAI_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "GROQ_API_KEY",
        "HF_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "COPILOT_GITHUB_TOKEN",
        "MINIMAX_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def tmp_dir(tmp_path):
    """Provide a temporary directory that is cleaned up automatically."""
    return tmp_path


@pytest.fixture()
def mock_config():
    """Return a minimal gauss config dict suitable for unit tests."""
    return {
        "model": "test/mock-model",
        "toolsets": ["terminal", "file"],
        "max_turns": 10,
        "terminal": {
            "backend": "local",
            "cwd": "/tmp",
            "timeout": 30,
        },
        "compression": {"enabled": False},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "command_allowlist": [],
    }


# ── Global test timeout ─────────────────────────────────────────────────────
# Kill any individual test that takes longer than 30 seconds.
# Prevents hanging tests (subprocess spawns, blocking I/O) from stalling the
# entire test suite.

def _timeout_handler(signum, frame):
    raise TimeoutError("Test exceeded 30 second timeout")


@pytest.fixture(autouse=True)
def _ensure_current_event_loop(request):
    """Provide a default event loop for sync tests that call get_event_loop().

    Python 3.11+ no longer guarantees a current loop for plain synchronous tests.
    A number of gateway tests still use asyncio.get_event_loop().run_until_complete(...).
    Ensure they always have a usable loop without interfering with pytest-asyncio's
    own loop management for @pytest.mark.asyncio tests.
    """
    if request.node.get_closest_marker("asyncio") is not None:
        yield
        return

    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = None

    created = loop is None or loop.is_closed()
    if created:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        yield
    finally:
        if created and loop is not None:
            try:
                loop.close()
            finally:
                asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def _enforce_test_timeout(request):
    """Kill any individual test that takes longer than 30 seconds."""
    if sys.platform == "win32":
        yield
        return
    timeout_seconds = 30
    timeout_marker = request.node.get_closest_marker("timeout")
    if timeout_marker is not None:
        if timeout_marker.args:
            timeout_seconds = int(timeout_marker.args[0])
        elif "seconds" in timeout_marker.kwargs:
            timeout_seconds = int(timeout_marker.kwargs["seconds"])
    old = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)
