from __future__ import annotations

from gauss_cli import lean_workflow


def test_prepare_native_lean_workflow_uses_checked_in_lean4_project():
    plan = lean_workflow.prepare_native_lean_workflow(
        "/prove JordanCycleTheorem",
        cwd=lean_workflow.Path(__file__).resolve().parents[2] / "Lean4",
    )

    assert plan.provider == "openai-codex"
    assert plan.model == "gpt-5.5"
    assert plan.toolsets == ("opengauss-lean",)
    assert plan.spec.workflow_kind == "prove"
    assert plan.project.root.name == "Lean4"


def test_run_native_lean_workflow_constructs_codex_agent_with_native_toolset(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            self.session_id = kwargs["session_id"]

        def run_conversation(self, user_message, *, system_message=None, task_id=None, persist_user_message=None):
            captured["user_message"] = user_message
            captured["system_message"] = system_message
            captured["task_id"] = task_id
            captured["persist_user_message"] = persist_user_message
            return {"final_response": "done", "messages": [{"role": "assistant", "content": "done"}]}

    monkeypatch.setattr(
        lean_workflow,
        "resolve_runtime_provider",
        lambda requested: {"api_key": "codex-token", "base_url": "https://chatgpt.com/backend-api/codex"},
    )
    import run_agent

    monkeypatch.setattr(run_agent, "AIAgent", FakeAgent)

    result = lean_workflow.run_native_lean_workflow(
        "/autoformalize prove the main theorem",
        cwd=lean_workflow.Path(__file__).resolve().parents[2] / "Lean4",
        session_id="sess-native",
    )

    kwargs = captured["kwargs"]
    assert kwargs["provider"] == "openai-codex"
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["api_mode"] == "codex_responses"
    assert kwargs["reasoning_config"] == {"enabled": True, "effort": "medium"}
    assert kwargs["enabled_toolsets"] == ["opengauss-lean"]
    assert kwargs["skip_context_files"] is False
    assert kwargs["skip_memory"] is False
    assert captured["persist_user_message"] == "/autoformalize prove the main theorem"
    assert "do not delegate to external CLIs" in captured["system_message"]
    assert result.final_response == "done"


def test_run_native_lean_workflow_accepts_reasoning_effort(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            self.session_id = kwargs["session_id"]

        def run_conversation(self, *_args, **_kwargs):
            return {"final_response": "done", "messages": []}

    monkeypatch.setattr(lean_workflow, "resolve_runtime_provider", lambda requested: {"api_key": "tok", "base_url": "url"})
    import run_agent

    monkeypatch.setattr(run_agent, "AIAgent", FakeAgent)

    lean_workflow.run_native_lean_workflow(
        "/autoformalize prove the main theorem",
        cwd=lean_workflow.Path(__file__).resolve().parents[2] / "Lean4",
        session_id="sess-native",
        reasoning_effort="high",
        skip_context_files=True,
        skip_memory=True,
    )

    assert captured["kwargs"]["reasoning_config"] == {"enabled": True, "effort": "high"}
    assert captured["kwargs"]["skip_context_files"] is True
    assert captured["kwargs"]["skip_memory"] is True
