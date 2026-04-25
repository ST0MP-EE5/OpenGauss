from __future__ import annotations

import threading
import time

import pytest

from swarm_manager import SwarmManager, SwarmTask


@pytest.fixture(autouse=True)
def _reset_singleton():
    SwarmManager.reset()
    yield
    SwarmManager.reset()


def test_swarm_task_defaults():
    task = SwarmTask(task_id="af-001", description="test", theorem="T")

    assert task.status == "queued"
    assert task.progress == "Waiting"
    assert task.thread is None
    assert task.process is None


def test_spawn_generic_workflow_task_runs_callback():
    manager = SwarmManager()
    done = threading.Event()

    def run_fn(task, *args, **kwargs):
        del args, kwargs
        task.progress = "done"
        done.set()
        return "ok"

    task = manager.spawn(
        theorem="MainTheorem",
        description="prove theorem",
        workflow_kind="autoformalize",
        workflow_command="/autoformalize MainTheorem",
        project_name="Lean4",
        run_fn=run_fn,
    )

    assert task.task_id == "af-001"
    assert done.wait(2)
    task.thread.join(timeout=2)
    assert task.status == "complete"
    assert task.progress == "done"


def test_render_table_and_summary_for_open_tasks():
    manager = SwarmManager()
    task = manager.spawn(theorem="T", description="demo", project_name="Lean4")
    task.status = "running"
    task.start_time = time.time() - 1

    table = manager.render_table()
    summary = manager.summary_line()

    assert table.row_count == 1
    assert summary is not None
    assert "1 agent running" in summary
