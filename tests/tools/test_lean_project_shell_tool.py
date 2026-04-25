from __future__ import annotations

import json
from pathlib import Path

from gauss_cli.project import initialize_gauss_project
from tools.lean_project_shell_tool import _lean_project_inspect_tool


def _init_project(root: Path) -> None:
    (root / "lakefile.toml").write_text("name = \"Demo\"\n", encoding="utf-8")
    initialize_gauss_project(root, name="Demo", source_mode="benchmark")


def test_lean_project_inspect_allows_read_only_command(tmp_path: Path):
    _init_project(tmp_path)
    (tmp_path / "Solution.lean").write_text("theorem MainTheorem : True := by trivial\n", encoding="utf-8")

    payload = json.loads(_lean_project_inspect_tool(command="rg MainTheorem Solution.lean", cwd=str(tmp_path)))

    assert payload["success"] is True
    assert payload["operation"] == "lean_project_inspect"
    assert "MainTheorem" in payload["stdout"]
    assert payload["mcp_call_count"] == 0


def test_lean_project_inspect_blocks_mutating_command(tmp_path: Path):
    _init_project(tmp_path)

    payload = json.loads(_lean_project_inspect_tool(command="rm Solution.lean", cwd=str(tmp_path)))

    assert payload["success"] is False
    assert payload["error_type"] == "ValueError"
    assert "not allowed" in payload["error"]


def test_lean_project_inspect_blocks_path_escape(tmp_path: Path):
    _init_project(tmp_path)

    payload = json.loads(_lean_project_inspect_tool(command="cat ../outside.lean", cwd=str(tmp_path)))

    assert payload["success"] is False
    assert payload["error_type"] == "ValueError"
    assert "escapes project root" in payload["error"]
