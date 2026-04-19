from __future__ import annotations

import copy
import os
from typing import Any

from gauss_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_api_key_provider_credentials,
    resolve_codex_runtime_credentials,
    resolve_provider,
)
from gauss_constants import OPENROUTER_BASE_URL

GAUSS_ENV_AUTH_PROVIDER_ENV = "GAUSS_ENV_AUTH_PROVIDER"


class EnvironmentAuthError(RuntimeError):
    """Raised when environment auth resolution fails."""


def requested_environment_provider(config_provider: str | None = None) -> str | None:
    env_provider = os.getenv(GAUSS_ENV_AUTH_PROVIDER_ENV, "").strip()
    configured_provider = (config_provider or "").strip()
    provider = env_provider or configured_provider
    return provider or None


def resolve_environment_credentials(provider_id: str | None) -> dict[str, str] | None:
    if not provider_id:
        return None

    normalized = provider_id.strip().lower()
    if normalized == "active":
        normalized = resolve_provider("auto")

    if normalized == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentAuthError(
                "Environment auth provider 'openrouter' requires OPENROUTER_API_KEY or OPENAI_API_KEY."
            )
        base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/") or OPENROUTER_BASE_URL
        return {
            "provider": "openrouter",
            "api_key": api_key,
            "base_url": base_url.rstrip("/"),
        }

    if normalized == "custom":
        base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not base_url:
            raise EnvironmentAuthError(
                "Environment auth provider 'custom' requires OPENAI_BASE_URL."
            )
        return {
            "provider": "custom",
            "api_key": api_key,
            "base_url": base_url,
        }

    if normalized == "openai-codex":
        creds = resolve_codex_runtime_credentials()
        return {
            "provider": str(creds["provider"]),
            "api_key": str(creds["api_key"]),
            "base_url": str(creds["base_url"]).rstrip("/"),
        }

    provider_config = PROVIDER_REGISTRY.get(normalized)
    if provider_config and provider_config.auth_type == "api_key":
        creds = resolve_api_key_provider_credentials(normalized)
        return {
            "provider": str(creds["provider"]),
            "api_key": str(creds["api_key"]),
            "base_url": str(creds["base_url"]).rstrip("/"),
        }

    raise EnvironmentAuthError(
        f"Unsupported environment auth provider '{provider_id}'."
    )


def _clone_server_config(server_config: Any) -> Any:
    if hasattr(server_config, "model_copy"):
        return server_config.model_copy()
    return copy.deepcopy(server_config)


def apply_environment_auth(
    server_configs: Any,
    provider_id: str | None,
) -> tuple[Any, dict[str, str] | None]:
    if not provider_id:
        return server_configs, None

    credentials = resolve_environment_credentials(provider_id)
    if credentials is None:
        return server_configs, None

    if not isinstance(server_configs, list):
        return server_configs, credentials

    updated_configs = []
    openai_like_count = 0
    for server_config in server_configs:
        clone = _clone_server_config(server_config)
        if getattr(clone, "server_type", None) == "openai":
            setattr(clone, "base_url", credentials["base_url"])
            setattr(clone, "api_key", credentials["api_key"])
            openai_like_count += 1
        updated_configs.append(clone)

    if openai_like_count == 0:
        raise EnvironmentAuthError(
            f"Environment auth provider '{provider_id}' requires at least one openai-style server config."
        )

    return updated_configs, credentials
