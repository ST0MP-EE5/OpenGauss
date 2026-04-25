"""Deterministic natural-language routing for the interactive Gauss CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class IntentCandidate:
    """A suggested canonical Gauss command for a plain-language input."""

    command: str
    title: str
    reason: str
    risk: str = "read"
    source: str = "natural"


_CURSOR_RE = re.compile(r"(?P<spec>\S+\.lean:\d+(?::\d+)?)")
_LEAN_PATH_RE = re.compile(r"(?P<path>\S+\.lean)")


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _strip_mention(text: str, mentions: Iterable[str]) -> tuple[str, str | None]:
    stripped = _normalize(text)
    if not stripped.startswith("@"):
        return stripped, None
    token, _, rest = stripped.partition(" ")
    mention = token[1:].strip().lower()
    if mention in set(mentions):
        return rest.strip(), mention
    return stripped, None


def _cursor_spec(text: str) -> str | None:
    match = _CURSOR_RE.search(text)
    return match.group("spec") if match else None


def _lean_path(text: str) -> str | None:
    match = _LEAN_PATH_RE.search(text)
    return match.group("path") if match else None


def _without_prefix(text: str, *prefixes: str) -> str:
    lowered = text.lower()
    for prefix in prefixes:
        if lowered == prefix:
            return ""
        if lowered.startswith(prefix + " "):
            return text[len(prefix):].strip()
    return text


def route_intent(
    text: str,
    *,
    active_cwd: str | Path | None = None,
    chat_mode: bool = False,
    enabled_mentions: Iterable[str] = ("lean", "project"),
) -> IntentCandidate | None:
    """Return a command suggestion for plain text, or ``None``.

    The router is deliberately deterministic.  ``active_cwd`` and
    ``chat_mode`` are accepted so callers can keep the routing API stable as
    future rules become project-aware.
    """

    del active_cwd, chat_mode
    raw = _normalize(text)
    if not raw or raw.startswith("/"):
        return None

    body, mention = _strip_mention(raw, enabled_mentions)
    lowered = body.lower()
    source = f"mention:{mention}" if mention else "natural"

    if mention == "project" or lowered.startswith("project "):
        args = _without_prefix(body, "project").strip()
        if not args:
            args = "status"
        return IntentCandidate(
            command=f"/project {args}",
            title="Project command",
            reason="Project-oriented request",
            source=source,
        )

    if mention == "lean":
        lowered = body.lower()

    if lowered in {"build", "lake build"} or lowered.startswith(("build ", "lake build ")):
        args = _without_prefix(body, "lake build", "build").strip()
        command = "/build" if not args else f"/build {args}"
        return IntentCandidate(command, "Build Lean project", "Lean build request", source=source)

    if lowered in {"check", "diagnostics", "diagnose"} or lowered.startswith(
        ("check ", "diagnostics ", "diagnose ")
    ):
        args = _without_prefix(body, "diagnostics", "diagnose", "check").strip()
        command = "/check" if not args else f"/check {args}"
        return IntentCandidate(command, "Check Lean file", "Lean check request", source=source)

    if "goal" in lowered:
        spec = _cursor_spec(body)
        if spec:
            return IntentCandidate(
                f"/goals {spec}",
                "Show Lean goals",
                "Lean goal-state request",
                source=source,
            )

    if lowered.startswith("goals "):
        args = _without_prefix(body, "goals").strip()
        if args:
            return IntentCandidate(f"/goals {args}", "Show Lean goals", "Lean goal-state request", source=source)

    if lowered.startswith("explain ") or lowered.startswith("what does "):
        spec = _cursor_spec(body)
        args = spec or _without_prefix(body, "explain", "what does").strip()
        if args:
            return IntentCandidate(f"/explain {args}", "Explain Lean context", "Lean explanation request", source=source)

    if "sorr" in lowered or "admit" in lowered:
        path = _lean_path(body)
        command = "/sorry" if not path else f"/sorry {path}"
        return IntentCandidate(command, "Show sorries", "Lean sorry/admit request", source=source)

    if lowered.startswith(("symbols ", "symbol ", "find symbol ", "find symbols ")):
        args = _without_prefix(body, "find symbols", "find symbol", "symbols", "symbol").strip()
        command = "/symbols" if not args else f"/symbols {args}"
        return IntentCandidate(command, "Search Lean symbols", "Lean symbol search request", source=source)

    if lowered in {"symbols", "symbol"}:
        return IntentCandidate("/symbols", "Search Lean symbols", "Lean symbol search request", source=source)

    workflow_prefixes = {
        "prove": "/prove",
        "autoprove": "/autoprove",
        "auto prove": "/autoprove",
        "formalize": "/formalize",
        "autoformalize": "/autoformalize",
        "auto formalize": "/autoformalize",
    }
    for prefix, command_name in workflow_prefixes.items():
        if lowered == prefix or lowered.startswith(prefix + " "):
            args = body[len(prefix):].strip()
            command = command_name if not args else f"{command_name} {args}"
            return IntentCandidate(
                command,
                "Run OpenGauss workflow",
                "Managed Lean workflow request",
                risk="workflow",
                source=source,
            )

    return None
