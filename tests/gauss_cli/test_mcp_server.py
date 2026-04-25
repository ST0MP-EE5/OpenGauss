from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace

import yaml

from gauss_cli import mcp_server
from gauss_cli.project import discover_gauss_project
from gauss_state import SessionDB
from swarm_manager import SwarmManager


def _seed_lean_project(root):
    (root / "lakefile.toml").write_text('name = "demo"\n', encoding="utf-8")


def test_gauss_project_status_reports_missing_project(tmp_path):
    _seed_lean_project(tmp_path)

    result = mcp_server.gauss_project_status(str(tmp_path))

    assert result["project_found"] is False
    assert result["cwd"] == str(tmp_path.resolve())
    assert "No active Gauss project found" in result["message"]


def test_gauss_project_init_creates_manifest_and_is_idempotent(tmp_path):
    _seed_lean_project(tmp_path)

    first = mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")
    second = mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")

    project = discover_gauss_project(tmp_path)
    assert first["created"] is True
    assert second["created"] is False
    assert first["project"]["name"] == "Demo Project"
    assert second["project"]["manifest_path"] == str(project.manifest_path)


def test_gauss_project_convert_detects_blueprint_and_is_idempotent(tmp_path):
    _seed_lean_project(tmp_path)
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "blueprint.yml").write_text("steps: []\n", encoding="utf-8")

    first = mcp_server.gauss_project_convert(str(tmp_path), name="Blueprint Project")
    second = mcp_server.gauss_project_convert(str(tmp_path), name="Blueprint Project")

    assert first["created"] is True
    assert second["created"] is False
    assert "templates/blueprint.yml" in first["blueprint_markers"]
    assert first["project"]["name"] == "Blueprint Project"


def test_gauss_project_create_populates_template_and_initializes_project(tmp_path):
    template_root = tmp_path / "template"
    template_root.mkdir()
    _seed_lean_project(template_root)
    (template_root / ".github" / "workflows").mkdir(parents=True)
    (template_root / ".github" / "workflows" / "gauss.yml").write_text("name: gauss\n", encoding="utf-8")

    result = mcp_server.gauss_project_create(
        "new-project",
        cwd=str(tmp_path),
        name="Created Project",
        template_source=str(template_root),
    )

    target = tmp_path / "new-project"
    project = discover_gauss_project(target)
    assert result["created"] is True
    assert result["target"] == str(target.resolve())
    assert result["project"]["name"] == "Created Project"
    assert result["template_source"] == str(template_root)
    assert project.source_mode == "template"


def test_axle_check_uses_project_environment_from_cwd(monkeypatch, tmp_path):
    _seed_lean_project(tmp_path)
    mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")

    manifest_path = tmp_path / ".gauss" / "project.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["lean_service"] = {
        "provider": "axle",
        "environment": "lean-4.28.0",
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    captured = {}

    class FakeService:
        async def check(self, **kwargs):
            captured.update(kwargs)
            return {"okay": True}

    monkeypatch.setattr(mcp_server, "_build_axle_service", lambda: FakeService())

    result = asyncio.run(
        mcp_server.axle_check(
            content="def answer := 42",
            cwd=str(tmp_path),
        )
    )

    assert result["success"] is True
    assert result["environment"] == "lean-4.28.0"
    assert captured["environment"] == "lean-4.28.0"
    assert captured["content"] == "def answer := 42"


def test_build_server_registers_axle_tools(monkeypatch):
    registered = []

    class DummyServer:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self, *, name, description):
            del description
            registered.append(name)

            def _decorator(fn):
                return fn

            return _decorator

    monkeypatch.setattr(mcp_server, "_ensure_fastmcp", lambda: DummyServer)

    mcp_server.build_server()

    assert "axle_environments" in registered
    assert "axle_check" in registered
    assert "axle_verify_proof" in registered
    assert "axle_extract_decls" in registered
    assert "axle_repair_proofs" in registered
    assert "axle_simplify_theorems" in registered
    assert "axle_normalize" in registered
    assert "axle_rename" in registered
    assert "gauss_lean_lsp_diagnostics" in registered
    assert "gauss_lean_lsp_goals" in registered
    assert "gauss_lean_lsp_references" in registered
    assert "gauss_lean_proof_context" in registered
    assert "gauss_lean_comparator_check" in registered


def test_mcp_lsp_and_comparator_tools_are_native_adapters(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "local_lean_lsp_diagnostics",
        lambda **kwargs: {"provider": "local", "diagnostics": [], "received": kwargs},
    )
    monkeypatch.setattr(
        mcp_server,
        "local_lean_comparator_check",
        lambda **kwargs: {"provider": "local", "comparator_valid": True, "mcp_call_count": 0, "received": kwargs},
    )

    diagnostics = mcp_server.gauss_lean_lsp_diagnostics("Demo.lean", cwd="/tmp/project")
    comparator = mcp_server.gauss_lean_comparator_check(
        "Challenge.lean",
        "Solution.lean",
        cwd="/tmp/project",
    )

    assert diagnostics["success"] is True
    assert diagnostics["mcp_adapter"] is True
    assert diagnostics["received"]["path"] == "Demo.lean"
    assert comparator["mcp_adapter"] is True
    assert comparator["comparator_valid"] is True
    assert comparator["mcp_call_count"] == 0


def test_gauss_autoformalize_prepare_returns_direct_native_payload(tmp_path):
    _seed_lean_project(tmp_path)
    project = mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")["project"]

    result = mcp_server.gauss_autoformalize_prepare(
        "/prove Demo",
        cwd=str(tmp_path),
        backend="codex",
    )

    assert result["mode"] == "direct"
    assert result["backend_name"] == "native"
    assert result["ignored_backend"] == "codex"
    assert result["workflow_kind"] == "prove"
    assert result["project"]["name"] == project["name"]
    assert result["provider"] == "openai-codex"
    assert result["model"] == "gpt-5.5"
    assert result["toolsets"] == ["opengauss-lean"]
    assert result["handoff"] is None
    assert result["managed_context"] is None
    assert result["native_runner"]["mcp_call_count"] == 0


def test_workflow_prepare_wrapper_builds_slash_command(monkeypatch):
    captured = {}

    def fake_prepare(command, *, cwd=None, backend=None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["backend"] = backend
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "gauss_autoformalize_prepare", fake_prepare)

    result = mcp_server.gauss_prove_prepare(
        "JordanCycleTheorem",
        cwd="/tmp/demo",
        backend="native",
    )

    assert result == {"ok": True}
    assert captured == {
        "command": "/prove JordanCycleTheorem",
        "cwd": "/tmp/demo",
        "backend": "native",
    }


def test_workflow_run_wrapper_builds_slash_command(monkeypatch):
    captured = {}

    def fake_run(command, *, cwd=None, backend=None, timeout_seconds=None, max_output_chars=None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["backend"] = backend
        captured["timeout_seconds"] = timeout_seconds
        captured["max_output_chars"] = max_output_chars
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "gauss_autoformalize_run", fake_run)

    result = mcp_server.gauss_formalize_run(
        "PontryaginDuality",
        cwd="/tmp/demo",
        backend="native",
        timeout_seconds=120,
        max_output_chars=2048,
    )

    assert result == {"ok": True}
    assert captured == {
        "command": "/formalize PontryaginDuality",
        "cwd": "/tmp/demo",
        "backend": "native",
        "timeout_seconds": 120,
        "max_output_chars": 2048,
    }


def test_workflow_spawn_wrapper_builds_slash_command(monkeypatch):
    captured = {}

    def fake_spawn(command, *, cwd=None, backend=None, timeout_seconds=None, max_output_chars=None):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["backend"] = backend
        captured["timeout_seconds"] = timeout_seconds
        captured["max_output_chars"] = max_output_chars
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "gauss_autoformalize_spawn", fake_spawn)

    result = mcp_server.gauss_autoprove_spawn(
        "BurnsidePrimeDegreeTheorem",
        cwd="/tmp/demo",
        backend="native",
        timeout_seconds=300,
        max_output_chars=4096,
    )

    assert result == {"ok": True}
    assert captured == {
        "command": "/autoprove BurnsidePrimeDegreeTheorem",
        "cwd": "/tmp/demo",
        "backend": "native",
        "timeout_seconds": 300,
        "max_output_chars": 4096,
    }


def test_gauss_autoformalize_run_executes_noninteractive_workflow(monkeypatch, tmp_path):
    _seed_lean_project(tmp_path)
    mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")
    captured = {}

    def fake_run_native(command, *, cwd, **kwargs):
        captured["command"] = command
        captured["cwd"] = str(cwd)
        captured["kwargs"] = kwargs
        return SimpleNamespace(final_response="ok\n", error="", success=True)

    monkeypatch.setattr(mcp_server, "run_native_lean_workflow", fake_run_native)

    result = mcp_server.gauss_autoformalize_run(
        "/autoformalize PontryaginDuality",
        cwd=str(tmp_path),
        backend="native",
        timeout_seconds=90,
    )

    assert captured["command"] == "/autoformalize PontryaginDuality"
    assert captured["cwd"] == str(tmp_path.resolve())
    assert result["mode"] == "direct"
    assert result["backend_name"] == "native"
    assert result["execution"]["returncode"] == 0
    assert result["execution"]["timed_out"] is False
    assert result["execution"]["stdout"] == "ok\n"
    assert result["handoff"] is None
    assert result["native_runner"]["mcp_call_count"] == 0


def test_gauss_autoformalize_run_reports_native_error(monkeypatch, tmp_path):
    _seed_lean_project(tmp_path)
    mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")

    def fake_run_native(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(mcp_server, "run_native_lean_workflow", fake_run_native)

    result = mcp_server.gauss_autoformalize_run(
        "/autoformalize BurnsidePrimeDegreeTheorem",
        cwd=str(tmp_path),
        backend="native",
        timeout_seconds=45,
    )

    assert result["execution"]["returncode"] is None
    assert result["execution"]["timed_out"] is False
    assert result["execution"]["error"] == "model unavailable"
    assert result["execution"]["stdout"] == ""
    assert result["execution"]["stderr"] == "model unavailable"


def test_gauss_autoformalize_spawn_runs_background_task(monkeypatch, tmp_path):
    _seed_lean_project(tmp_path)
    mcp_server.gauss_project_init(str(tmp_path), name="Demo Project")
    SwarmManager.reset()

    try:
        def fake_run_native(*_args, **_kwargs):
            return SimpleNamespace(final_response="background ok", error="", success=True)

        monkeypatch.setattr(mcp_server, "run_native_lean_workflow", fake_run_native)

        result = mcp_server.gauss_autoformalize_spawn(
            "/prove PontryaginDuality",
            cwd=str(tmp_path),
            backend="native",
            timeout_seconds=30,
        )

        assert result["backend_name"] == "native"
        assert result["handoff"] is None
        task_id = result["task"]["task_id"]
        assert result["task"]["status"] in {"queued", "running", "complete"}

        deadline = time.time() + 5
        task_status = None
        while time.time() < deadline:
            task_status = mcp_server.gauss_swarm_status(task_id)["task"]
            if task_status["status"] in {"complete", "failed"}:
                break
            time.sleep(0.05)

        assert task_status is not None
        assert task_status["status"] == "complete"
        assert "background ok" in (task_status["result"] or "")
    finally:
        SwarmManager.reset()


def test_session_tools_list_export_rename_and_prune(monkeypatch, tmp_path):
    gauss_home = tmp_path / ".gauss"
    monkeypatch.setenv("GAUSS_HOME", str(gauss_home))
    db = SessionDB(db_path=gauss_home / "state.db")
    try:
        db.create_session("sess-1234", source="cli", model="gpt-test")
        db.append_message("sess-1234", role="user", content="first theorem")
        db.append_message("sess-1234", role="assistant", content="working on it")
        db.end_session("sess-1234", "done")
        old_started = time.time() - (120 * 86400)
        db._conn.execute(
            "UPDATE sessions SET started_at = ?, ended_at = ? WHERE id = ?",
            (old_started, old_started + 60, "sess-1234"),
        )
        db._conn.commit()
    finally:
        db.close()

    listed = mcp_server.gauss_sessions_list(limit=10)
    assert listed["total_sessions"] == 1
    assert listed["sessions"][0]["id"] == "sess-1234"
    assert listed["sessions"][0]["preview"] == "first theorem"

    exported = mcp_server.gauss_session_export("sess-12")
    assert exported["session"]["id"] == "sess-1234"
    assert len(exported["session"]["messages"]) == 2

    renamed = mcp_server.gauss_session_rename("sess-1234", "Lean Work")
    assert renamed["updated"] is True
    assert renamed["title"] == "Lean Work"

    pruned = mcp_server.gauss_sessions_prune(older_than_days=90)
    assert pruned["deleted_sessions"] == 1
    assert mcp_server.gauss_sessions_list(limit=10)["total_sessions"] == 0


def test_swarm_tools_list_status_and_cancel():
    SwarmManager.reset()
    manager = SwarmManager()
    try:
        task = manager.spawn(
            theorem="JordanCycleTheorem",
            description="Direct run",
            workflow_kind="prove",
            workflow_command="/prove JordanCycleTheorem",
            project_name="Demo",
            project_root="/tmp/demo",
            working_dir="/tmp/demo",
            backend_name="native",
        )

        listed = mcp_server.gauss_swarm_list()
        assert listed["task_count"] == 1
        assert listed["tasks"][0]["task_id"] == task.task_id
        assert listed["tasks"][0]["status"] == "queued"

        status = mcp_server.gauss_swarm_status(task.task_id)
        assert status["task"]["workflow_command"] == "/prove JordanCycleTheorem"

        cancelled = mcp_server.gauss_swarm_cancel(task.task_id)
        assert cancelled["cancelled"] is True
        assert cancelled["task"]["status"] == "cancelled"
    finally:
        SwarmManager.reset()


def test_run_mcp_server_delegates_to_fastmcp(monkeypatch):
    captured = {}

    class DummyServer:
        def run(self, *, transport):
            captured["transport"] = transport

    monkeypatch.setattr(mcp_server, "MCP_SERVER", DummyServer())

    mcp_server.run_mcp_server(transport="stdio")

    assert captured == {"transport": "stdio"}


def test_main_dispatches_mcp_server(monkeypatch):
    import gauss_cli.main as main_mod

    captured = {}

    def fake_cmd_mcp_server(args):
        captured["transport"] = args.transport

    monkeypatch.setattr(main_mod, "cmd_mcp_server", fake_cmd_mcp_server)
    monkeypatch.setattr(sys, "argv", ["gauss", "mcp-server", "--transport", "stdio"])

    main_mod.main()

    assert captured == {"transport": "stdio"}
