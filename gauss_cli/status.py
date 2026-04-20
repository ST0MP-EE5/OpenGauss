"""Status command for the contracted OpenGauss CLI."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gauss_cli.auth import (
    AuthError,
    get_codex_auth_status,
    get_nous_auth_status,
    resolve_provider,
)
from gauss_cli.branding import get_cli_command_name, get_product_name, rewrite_cli_references
from gauss_cli.colors import Colors, color
from gauss_cli.config import get_env_path, get_env_value, get_gauss_home, load_config
from gauss_cli.models import provider_label
from gauss_cli.runtime_provider import resolve_requested_provider

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def check_mark(ok: bool) -> str:
    return color("✓", Colors.GREEN) if ok else color("✗", Colors.RED)


def redact_key(key: str) -> str:
    if not key:
        return "(not set)"
    if len(key) < 12:
        return "***"
    return key[:4] + "..." + key[-4:]


def _format_iso_timestamp(value) -> str:
    if not value or not isinstance(value, str):
        return "(unknown)"
    text = value.strip()
    if not text:
        return "(unknown)"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _configured_model_label(config: dict) -> str:
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        model = (model_cfg.get("default") or model_cfg.get("name") or "").strip()
    elif isinstance(model_cfg, str):
        model = model_cfg.strip()
    else:
        model = ""
    return model or "(not set)"


def _effective_provider_label() -> str:
    requested = resolve_requested_provider()
    try:
        effective = resolve_provider(requested)
    except AuthError:
        effective = requested or "auto"
    if effective == "openrouter" and get_env_value("OPENAI_BASE_URL"):
        effective = "custom"
    return provider_label(effective)


def _configured_backend_label(config: dict) -> str:
    gauss_cfg = config.get("gauss", {})
    auto_cfg = gauss_cfg.get("autoformalize", {})
    return str(auto_cfg.get("backend") or "forge")


def show_status(args) -> None:
    show_all = getattr(args, "all", False)
    cli_name = get_cli_command_name()

    try:
        config = load_config()
    except Exception:
        config = {}

    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.CYAN))
    print(color(f"│ {f'{get_product_name()} Status':^55} │", Colors.CYAN))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.CYAN))

    print()
    print(color("◆ Environment", Colors.CYAN, Colors.BOLD))
    print(f"  Project:      {PROJECT_ROOT}")
    print(f"  Python:       {sys.version.split()[0]}")
    print(f"  Home:         {get_gauss_home()}")
    print(f"  .env file:    {check_mark(get_env_path().exists())} {'exists' if get_env_path().exists() else 'not found'}")
    print(f"  Model:        {_configured_model_label(config)}")
    print(f"  Provider:     {_effective_provider_label()}")
    print(f"  Backend:      {_configured_backend_label(config)}")

    print()
    print(color("◆ API Keys", Colors.CYAN, Colors.BOLD))
    keys = {
        "OpenRouter": "OPENROUTER_API_KEY",
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": "ANTHROPIC_API_KEY",
        "Firecrawl": "FIRECRAWL_API_KEY",
        "Browserbase": "BROWSERBASE_API_KEY",
        "AXLE": "AXLE_API_KEY",
    }
    for name, env_var in keys.items():
        value = get_env_value(env_var) or ""
        display = value if show_all else redact_key(value)
        print(f"  {name:<12}  {check_mark(bool(value))} {display}")

    print()
    print(color("◆ Auth Providers", Colors.CYAN, Colors.BOLD))
    nous_status = get_nous_auth_status() or {}
    codex_status = get_codex_auth_status() or {}
    nous_logged_in = bool(nous_status.get("logged_in"))
    codex_logged_in = bool(codex_status.get("logged_in"))
    print(
        f"  {'Nous Portal':<12}  {check_mark(nous_logged_in)} "
        f"{'logged in' if nous_logged_in else f'not logged in (run: {cli_name} model)'}"
    )
    print(
        f"  {'OpenAI Codex':<12}  {check_mark(codex_logged_in)} "
        f"{'logged in' if codex_logged_in else f'not logged in (run: {cli_name} model)'}"
    )
    if codex_status.get("auth_store"):
        print(f"    Auth file:  {codex_status['auth_store']}")
    if codex_status.get("last_refresh"):
        print(f"    Refreshed:  {_format_iso_timestamp(codex_status.get('last_refresh'))}")
    if codex_status.get("error") and not codex_logged_in:
        print(f"    Error:      {rewrite_cli_references(str(codex_status.get('error')))}")

    print()
    print(color("◆ Terminal", Colors.CYAN, Colors.BOLD))
    terminal_cfg = config.get("terminal", {})
    print(f"  Backend:      {terminal_cfg.get('backend', 'local')}")
    print(f"  CWD:          {terminal_cfg.get('cwd', '.')}")
    print(f"  Timeout:      {terminal_cfg.get('timeout', 180)}s")

    print()
    print(color("◆ Lean Workflows", Colors.CYAN, Colors.BOLD))
    print("  Managed lanes: forge, codex")
    print("  Benchmark env: formalqualbench")
    print()
