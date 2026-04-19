import os

import pytest

from environments.auth_bridge import (
    GAUSS_ENV_AUTH_PROVIDER_ENV,
    apply_environment_auth,
    requested_environment_provider,
)


class _FakeServerConfig:
    def __init__(self, *, server_type: str = "openai", base_url: str = "https://old", api_key: str = "old-key"):
        self.server_type = server_type
        self.base_url = base_url
        self.api_key = api_key


def test_requested_environment_provider_prefers_subprocess_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(GAUSS_ENV_AUTH_PROVIDER_ENV, "openai-codex")
    assert requested_environment_provider("openrouter") == "openai-codex"


def test_apply_environment_auth_updates_only_environment_server_configs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "environments.auth_bridge.resolve_codex_runtime_credentials",
        lambda: {
            "provider": "openai-codex",
            "api_key": "codex-token",
            "base_url": "https://chatgpt.com/backend-api/codex",
        },
    )
    original = _FakeServerConfig()
    untouched = _FakeServerConfig(server_type="vllm", base_url="http://localhost:8000/v1", api_key="")

    updated, resolved = apply_environment_auth([original, untouched], "openai-codex")

    assert resolved == {
        "provider": "openai-codex",
        "api_key": "codex-token",
        "base_url": "https://chatgpt.com/backend-api/codex",
    }
    assert updated[0].base_url == "https://chatgpt.com/backend-api/codex"
    assert updated[0].api_key == "codex-token"
    assert updated[1].base_url == "http://localhost:8000/v1"
    assert updated[1].api_key == ""
    assert original.base_url == "https://old"
    assert original.api_key == "old-key"
