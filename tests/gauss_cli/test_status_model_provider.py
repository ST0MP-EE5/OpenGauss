"""Tests for gauss_cli.status model/provider display."""

from types import SimpleNamespace


def _patch_common_status_deps(monkeypatch, status_mod, tmp_path, *, openai_base_url=""):
    import gauss_cli.auth as auth_mod

    monkeypatch.setattr(status_mod, "get_env_path", lambda: tmp_path / ".env", raising=False)
    monkeypatch.setattr(status_mod, "get_gauss_home", lambda: tmp_path, raising=False)

    def _get_env_value(name: str):
        if name == "OPENAI_BASE_URL":
            return openai_base_url
        return ""

    monkeypatch.setattr(status_mod, "get_env_value", _get_env_value, raising=False)
    monkeypatch.setattr(auth_mod, "get_nous_auth_status", lambda: {}, raising=False)
    monkeypatch.setattr(auth_mod, "get_codex_auth_status", lambda: {}, raising=False)
    monkeypatch.setattr(
        status_mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="inactive\n", returncode=3),
    )


def test_show_status_displays_configured_dict_model_and_provider_label(monkeypatch, capsys, tmp_path):
    from gauss_cli import status as status_mod

    _patch_common_status_deps(monkeypatch, status_mod, tmp_path)
    monkeypatch.setattr(
        status_mod,
        "load_config",
        lambda: {"model": {"default": "gpt-5.5", "provider": "openai-codex"}},
        raising=False,
    )
    monkeypatch.setattr(status_mod, "resolve_requested_provider", lambda requested=None: "openai-codex", raising=False)
    monkeypatch.setattr(status_mod, "resolve_provider", lambda requested=None, **kwargs: "openai-codex", raising=False)
    monkeypatch.setattr(status_mod, "provider_label", lambda provider: "OpenAI Codex", raising=False)

    status_mod.show_status(SimpleNamespace(all=False, deep=False))

    out = capsys.readouterr().out
    assert "Model:        gpt-5.5" in out
    assert "Provider:     OpenAI Codex" in out


def test_show_status_displays_legacy_string_model_and_custom_endpoint(monkeypatch, capsys, tmp_path):
    from gauss_cli import status as status_mod

    _patch_common_status_deps(monkeypatch, status_mod, tmp_path, openai_base_url="http://localhost:8080/v1")
    monkeypatch.setattr(status_mod, "load_config", lambda: {"model": "qwen3:latest"}, raising=False)
    monkeypatch.setattr(status_mod, "resolve_requested_provider", lambda requested=None: "auto", raising=False)
    monkeypatch.setattr(status_mod, "resolve_provider", lambda requested=None, **kwargs: "openrouter", raising=False)
    monkeypatch.setattr(status_mod, "provider_label", lambda provider: "Custom endpoint" if provider == "custom" else provider, raising=False)

    status_mod.show_status(SimpleNamespace(all=False, deep=False))

    out = capsys.readouterr().out
    assert "Model:        qwen3:latest" in out
    assert "Provider:     Custom endpoint" in out
