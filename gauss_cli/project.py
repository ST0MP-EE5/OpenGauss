"""Gauss project discovery and local manifest management."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

GAUSS_PROJECT_DIRNAME = ".gauss"
GAUSS_PROJECT_MANIFEST_FILENAME = "project.yaml"
GAUSS_PROJECT_SCHEMA_VERSION = 1
GAUSS_PROJECT_TEMPLATE_ENV = "GAUSS_BLUEPRINT_TEMPLATE_SOURCE"
GAUSS_PROJECT_TEMPLATE_CONFIG_KEY = "gauss.project.template_source"

_BLUEPRINT_MARKERS = (
    "lean-toolchain",
    "lakefile.lean",
    "lakefile.toml",
    "templates/blueprint.yml",
    ".github/workflows/gauss.yml",
)


class GaussProjectError(RuntimeError):
    """Base class for Gauss project failures."""


class ProjectNotFoundError(GaussProjectError):
    """Raised when no active Gauss project can be found."""


class ProjectManifestError(GaussProjectError):
    """Raised when a `.gauss` manifest is missing or malformed."""


class ProjectCommandError(GaussProjectError):
    """Raised when a project-management command cannot be completed."""


class ProjectTemplateUnavailableError(ProjectCommandError):
    """Raised when `/project create` has no configured template source."""


@dataclass(frozen=True)
class GaussProject:
    """Validated local Gauss project metadata."""

    root: Path
    gauss_dir: Path
    manifest_path: Path
    name: str
    kind: str
    schema_version: int
    lean_root: Path
    runtime_dir: Path
    cache_dir: Path
    workflows_dir: Path
    created_at: str
    source_mode: str
    template_source: str
    blueprint_markers: tuple[str, ...]
    manifest: dict[str, Any]

    @property
    def label(self) -> str:
        """Return the user-facing project label."""
        return self.name or self.root.name

    @property
    def is_blueprint(self) -> bool:
        """Return whether blueprint markers were recorded for this project."""
        return bool(self.blueprint_markers)


def is_lean_project_root(path: Path) -> bool:
    """Return whether *path* looks like a Lean 4 project root."""
    return (path / "lakefile.lean").exists() or (path / "lakefile.toml").exists()


def find_lean_project_root(start: Path) -> Path | None:
    """Walk upward from *start* and return the nearest Lean 4 project root."""
    resolved = start.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if is_lean_project_root(candidate):
            return candidate
    return None


def detect_blueprint_markers(root: Path) -> tuple[str, ...]:
    """Return the known Lean blueprint markers present under *root*."""
    markers = [marker for marker in _BLUEPRINT_MARKERS if (root / marker).exists()]
    return tuple(markers)


def resolve_template_source(
    config: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the configured blueprint template source, if any."""
    env_map = env or {}
    configured = str(env_map.get(GAUSS_PROJECT_TEMPLATE_ENV, "") or "").strip()
    if configured:
        return configured

    if not isinstance(config, Mapping):
        return ""

    gauss_cfg = config.get("gauss")
    if not isinstance(gauss_cfg, Mapping):
        return ""

    project_cfg = gauss_cfg.get("project")
    if not isinstance(project_cfg, Mapping):
        return ""

    return str(project_cfg.get("template_source", "") or "").strip()


def load_gauss_project(target: str | Path) -> GaussProject:
    """Load and validate a Gauss project from a root, `.gauss/`, or manifest path."""
    candidate = Path(target).expanduser().resolve()

    if candidate.is_file():
        manifest_path = candidate
        gauss_dir = manifest_path.parent
        root = gauss_dir.parent
    elif candidate.name == GAUSS_PROJECT_DIRNAME:
        gauss_dir = candidate
        manifest_path = gauss_dir / GAUSS_PROJECT_MANIFEST_FILENAME
        root = gauss_dir.parent
    else:
        root = candidate
        gauss_dir = root / GAUSS_PROJECT_DIRNAME
        manifest_path = gauss_dir / GAUSS_PROJECT_MANIFEST_FILENAME

    if not gauss_dir.is_dir():
        raise ProjectNotFoundError(f"Gauss project directory not found at {gauss_dir}.")
    if not manifest_path.is_file():
        raise ProjectManifestError(
            f"Found `{gauss_dir}` but `{GAUSS_PROJECT_MANIFEST_FILENAME}` is missing."
        )

    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ProjectManifestError(f"Failed to read {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectManifestError(f"{manifest_path} must contain a mapping.")

    schema_version = payload.get("schema_version")
    if schema_version != GAUSS_PROJECT_SCHEMA_VERSION:
        raise ProjectManifestError(
            f"{manifest_path} has schema_version={schema_version!r}; "
            f"expected {GAUSS_PROJECT_SCHEMA_VERSION}."
        )

    name = str(payload.get("name", "") or "").strip()
    if not name:
        raise ProjectManifestError(f"{manifest_path} is missing a non-empty `name`.")

    kind = str(payload.get("kind", "") or "").strip() or "lean4"
    if kind != "lean4":
        raise ProjectManifestError(f"{manifest_path} has unsupported `kind`: {kind!r}.")

    lean_root = _resolve_relative_path(
        root,
        payload.get("lean_root", "."),
        field_name="lean_root",
    )
    if not is_lean_project_root(lean_root):
        raise ProjectManifestError(
            f"{manifest_path} declares lean_root={payload.get('lean_root')!r}, "
            "but that directory is not a Lean 4 project root."
        )

    paths_payload = payload.get("paths", {})
    if not isinstance(paths_payload, Mapping):
        raise ProjectManifestError(f"{manifest_path} has invalid `paths` metadata.")

    runtime_dir = _resolve_relative_path(
        root,
        paths_payload.get("runtime", f"{GAUSS_PROJECT_DIRNAME}/runtime"),
        field_name="paths.runtime",
    )
    cache_dir = _resolve_relative_path(
        root,
        paths_payload.get("cache", f"{GAUSS_PROJECT_DIRNAME}/cache"),
        field_name="paths.cache",
    )
    workflows_dir = _resolve_relative_path(
        root,
        paths_payload.get("workflows", f"{GAUSS_PROJECT_DIRNAME}/workflows"),
        field_name="paths.workflows",
    )

    source_payload = payload.get("source", {})
    if source_payload is None:
        source_payload = {}
    if not isinstance(source_payload, Mapping):
        raise ProjectManifestError(f"{manifest_path} has invalid `source` metadata.")

    blueprint_payload = payload.get("blueprint", {})
    if blueprint_payload is None:
        blueprint_payload = {}
    if not isinstance(blueprint_payload, Mapping):
        raise ProjectManifestError(f"{manifest_path} has invalid `blueprint` metadata.")

    markers = tuple(
        str(marker).strip()
        for marker in (blueprint_payload.get("markers") or [])
        if str(marker).strip()
    )

    for path in (gauss_dir, runtime_dir, cache_dir, workflows_dir):
        path.mkdir(parents=True, exist_ok=True)

    created_at = str(payload.get("created_at", "") or "").strip()
    source_mode = str(source_payload.get("mode", "") or "").strip() or "init"
    template_source = str(source_payload.get("template_source", "") or "").strip()

    return GaussProject(
        root=root,
        gauss_dir=gauss_dir,
        manifest_path=manifest_path,
        name=name,
        kind=kind,
        schema_version=GAUSS_PROJECT_SCHEMA_VERSION,
        lean_root=lean_root,
        runtime_dir=runtime_dir,
        cache_dir=cache_dir,
        workflows_dir=workflows_dir,
        created_at=created_at,
        source_mode=source_mode,
        template_source=template_source,
        blueprint_markers=markers,
        manifest=dict(payload),
    )


def discover_gauss_project(start: str | Path) -> GaussProject:
    """Search upward from *start* for the nearest valid `.gauss` project root."""
    resolved = Path(start).expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        gauss_dir = candidate / GAUSS_PROJECT_DIRNAME
        if not gauss_dir.exists():
            continue
        manifest_path = gauss_dir / GAUSS_PROJECT_MANIFEST_FILENAME
        if not manifest_path.is_file():
            continue
        return load_gauss_project(candidate)

    raise ProjectNotFoundError(
        "No active Gauss project found. Use `/project init`, `/project convert`, "
        "or `/project use <path>` first."
    )


def initialize_gauss_project(
    root: str | Path,
    *,
    name: str | None = None,
    lean_root: str | Path | None = None,
    source_mode: str = "init",
    template_source: str = "",
    blueprint_markers: tuple[str, ...] | None = None,
) -> GaussProject:
    """Create a `.gauss` manifest under *root* and return the validated project."""
    project_root = Path(root).expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    manifest_path = project_root / GAUSS_PROJECT_DIRNAME / GAUSS_PROJECT_MANIFEST_FILENAME
    if manifest_path.is_file():
        return load_gauss_project(project_root)

    if lean_root is None:
        resolved_lean_root = find_lean_project_root(project_root)
    else:
        resolved_lean_root = Path(lean_root).expanduser().resolve()

    if resolved_lean_root is None:
        raise ProjectCommandError(
            "Lean project root not found. `/project init` and `/project convert` "
            "work inside Lean 4 repositories (expected `lakefile.lean` or `lakefile.toml`)."
        )

    try:
        resolved_lean_root.relative_to(project_root)
    except ValueError as exc:
        raise ProjectCommandError(
            f"Lean root {resolved_lean_root} is outside the requested project root {project_root}."
        ) from exc

    if not is_lean_project_root(resolved_lean_root):
        raise ProjectCommandError(
            f"Lean root {resolved_lean_root} is missing `lakefile.lean` or `lakefile.toml`."
        )

    gauss_dir = project_root / GAUSS_PROJECT_DIRNAME
    runtime_dir = gauss_dir / "runtime"
    cache_dir = gauss_dir / "cache"
    workflows_dir = gauss_dir / "workflows"
    for path in (gauss_dir, runtime_dir, cache_dir, workflows_dir):
        path.mkdir(parents=True, exist_ok=True)

    markers = blueprint_markers if blueprint_markers is not None else detect_blueprint_markers(project_root)
    payload = {
        "schema_version": GAUSS_PROJECT_SCHEMA_VERSION,
        "name": (name or project_root.name or "gauss-project").strip(),
        "kind": "lean4",
        "lean_root": str(resolved_lean_root.relative_to(project_root)) or ".",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "mode": str(source_mode or "init").strip() or "init",
            "template_source": str(template_source or "").strip(),
        },
        "blueprint": {
            "markers": list(markers),
        },
        "paths": {
            "runtime": f"{GAUSS_PROJECT_DIRNAME}/runtime",
            "cache": f"{GAUSS_PROJECT_DIRNAME}/cache",
            "workflows": f"{GAUSS_PROJECT_DIRNAME}/workflows",
        },
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return load_gauss_project(project_root)


def populate_project_from_template(target_dir: str | Path, template_source: str) -> None:
    """Populate *target_dir* from a configured template source."""
    target = Path(target_dir).expanduser().resolve()
    if target.exists():
        raise ProjectCommandError(f"Target path already exists: {target}")

    template_value = str(template_source or "").strip()
    if not template_value:
        raise ProjectTemplateUnavailableError(
            "Blueprint project creation is blocked until a template source is configured."
        )

    source_path = Path(template_value).expanduser()
    if source_path.exists():
        if source_path.is_dir() and (source_path / ".git").is_dir():
            _run_git_clone(str(source_path.resolve()), target)
            return
        if source_path.is_dir():
            shutil.copytree(source_path, target)
            return
        raise ProjectCommandError(f"Template source is not a directory: {source_path}")

    _run_git_clone(template_value, target)


def format_project_summary(project: GaussProject, *, active_cwd: Path | None = None) -> str:
    """Return a compact text summary for CLI surfaces."""
    bits = [project.label]
    if active_cwd is not None:
        try:
            rel = active_cwd.resolve().relative_to(project.root)
        except ValueError:
            rel = None
        if rel is not None and str(rel) not in {"", "."}:
            bits.append(f"cwd:{rel}")
    if project.is_blueprint:
        bits.append("blueprint")
    return " · ".join(bits)


def _resolve_relative_path(root: Path, value: Any, *, field_name: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ProjectManifestError(f"Project manifest field `{field_name}` must not be empty.")

    path = Path(raw)
    if path.is_absolute():
        raise ProjectManifestError(f"Project manifest field `{field_name}` must be relative.")

    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectManifestError(
            f"Project manifest field `{field_name}` points outside the project root."
        ) from exc
    return resolved


def _run_git_clone(source: str, target: Path) -> None:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", source, str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise ProjectCommandError(f"Failed to clone template source {source!r}: {stderr}") from exc
