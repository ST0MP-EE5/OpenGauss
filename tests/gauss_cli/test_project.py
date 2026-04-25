"""Tests for the Gauss project manifest and discovery helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from gauss_cli import project as project_mod


def _write_lean_root(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "lakefile.lean").write_text("-- lean project\n", encoding="utf-8")


def test_initialize_and_load_gauss_project_creates_manifest_and_runtime_dirs(tmp_path: Path):
    root = tmp_path / "Demo"
    _write_lean_root(root)

    project = project_mod.initialize_gauss_project(root, name="Demo Project")
    loaded = project_mod.load_gauss_project(root)

    assert loaded.label == "Demo Project"
    assert loaded.manifest_path == root / ".gauss" / "project.yaml"
    assert loaded.lean_root == root
    assert loaded.runtime_dir == root / ".gauss" / "runtime"
    assert loaded.cache_dir == root / ".gauss" / "cache"
    assert loaded.workflows_dir == root / ".gauss" / "workflows"
    assert loaded.manifest["schema_version"] == project_mod.GAUSS_PROJECT_SCHEMA_VERSION
    assert project == loaded


def test_discover_gauss_project_uses_nearest_parent(tmp_path: Path):
    outer = tmp_path / "Outer"
    inner = outer / "Nested"
    nested_project = inner / "Project"
    _write_lean_root(outer)
    _write_lean_root(nested_project)

    outer_project = project_mod.initialize_gauss_project(outer, name="Outer Project")
    nested = project_mod.initialize_gauss_project(nested_project, name="Nested Project")
    active = nested_project / "Math" / "Subdir"
    active.mkdir(parents=True)

    discovered = project_mod.discover_gauss_project(active)

    assert discovered == nested
    assert discovered != outer_project


def test_discover_gauss_project_skips_non_project_gauss_config_dirs(tmp_path: Path):
    home = tmp_path / "Home"
    repo = home / "Documents" / "Repo"
    (home / ".gauss").mkdir(parents=True)
    repo.mkdir(parents=True)

    with pytest.raises(project_mod.ProjectNotFoundError, match="No active Gauss project"):
        project_mod.discover_gauss_project(repo)


def test_load_gauss_project_rejects_manifest_paths_outside_root(tmp_path: Path):
    root = tmp_path / "Demo"
    outside = tmp_path / "Outside"
    _write_lean_root(root)
    _write_lean_root(outside)
    manifest = root / ".gauss" / "project.yaml"
    project_mod.initialize_gauss_project(root, name="Demo Project")

    manifest.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "name: Demo Project",
                "kind: lean4",
                "lean_root: ../Outside",
                "created_at: 2026-03-18T00:00:00+00:00",
                "source:",
                "  mode: init",
                "  template_source: ''",
                "blueprint:",
                "  markers: []",
                "paths:",
                "  runtime: .gauss/runtime",
                "  cache: .gauss/cache",
                "  workflows: .gauss/workflows",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(project_mod.ProjectManifestError, match="outside the project root"):
        project_mod.load_gauss_project(root)


def test_format_project_summary_includes_relative_cwd_and_blueprint(tmp_path: Path):
    root = tmp_path / "BlueprintDemo"
    _write_lean_root(root)
    (root / "templates").mkdir()
    (root / "templates" / "blueprint.yml").write_text("name: demo\n", encoding="utf-8")
    project = project_mod.initialize_gauss_project(
        root,
        name="Blueprint Demo",
        blueprint_markers=("templates/blueprint.yml",),
    )
    active_cwd = root / "Math"
    active_cwd.mkdir()

    summary = project_mod.format_project_summary(project, active_cwd=active_cwd)

    assert summary == "Blueprint Demo · cwd:Math · blueprint"


def test_populate_project_from_template_local_directory_copies_contents(tmp_path: Path):
    template = tmp_path / "template"
    target = tmp_path / "generated"
    _write_lean_root(template)
    (template / "README.md").write_text("# Template\n", encoding="utf-8")

    project_mod.populate_project_from_template(target, str(template))

    assert (target / "lakefile.lean").read_text(encoding="utf-8") == "-- lean project\n"
    assert (target / "README.md").read_text(encoding="utf-8") == "# Template\n"


def test_populate_project_from_template_requires_configured_source(tmp_path: Path):
    with pytest.raises(project_mod.ProjectTemplateUnavailableError, match="template source"):
        project_mod.populate_project_from_template(tmp_path / "generated", "")


def test_resolve_template_source_prefers_env_over_config():
    config = {"gauss": {"project": {"template_source": "config-template"}}}

    result = project_mod.resolve_template_source(
        config,
        {project_mod.GAUSS_PROJECT_TEMPLATE_ENV: "env-template"},
    )

    assert result == "env-template"
