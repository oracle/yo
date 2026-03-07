#!/usr/bin/env python3
from pathlib import Path
from unittest import mock

import pytest

from yo.tasks import TaskPlan
from yo.tasks import YoTask
from yo.util import YoExc


def _task(
    name: str,
    *,
    deps=None,
    conflicts=None,
    prereq_for=None,
    include_files=None,
    sendfiles=None,
) -> YoTask:
    return YoTask(
        name=name,
        path=f"/tmp/{name}",
        script=f"echo {name}",
        dependencies=list(deps or []),
        conflicts=list(conflicts or []),
        prereq_for=list(prereq_for or []),
        include_files=list(include_files or []),
        sendfiles=list(sendfiles or []),
    )


def test_prepare_detects_conflicts():
    a = _task("a", conflicts=["b"])
    b = _task("b")
    plan = TaskPlan([a, b])

    with pytest.raises(YoExc, match="conflicts"):
        plan.prepare(mock.Mock())


def test_prepare_detects_circular_dependency():
    a = _task("a", deps=["b"])
    b = _task("b", deps=["a"])
    plan = TaskPlan([a, b])

    with pytest.raises(YoExc, match="circular dependency"):
        plan.prepare(mock.Mock())


def test_prepare_inserts_prereqs_and_orders_dependencies():
    helper = _task("helper", prereq_for=["main"])
    main = _task("main")
    plan = TaskPlan([main, helper])

    plan.prepare(mock.Mock())

    assert "helper" in main.dependencies
    assert main.script.startswith("DEPENDS_ON helper\n")
    assert [t.name for t in plan.ordered_tasks] == ["helper", "main"]


def test_prepare_calls_prepare_files_and_checks_missing_sendfiles():
    existing = Path(__file__)
    include = [("~/.bashrc", "~/.bashrc", False)]
    task = _task(
        "files",
        include_files=include,
        sendfiles=[existing, existing.parent / "does-not-exist"],
    )
    task.prepare_files = mock.Mock()
    plan = TaskPlan([task])

    with pytest.raises(YoExc, match="missing files for task files"):
        plan.prepare(mock.Mock())

    task.prepare_files.assert_called_once()


def test_run_and_join_use_ordered_tasks():
    one = _task("one")
    two = _task("two")
    plan = TaskPlan([one, two])
    plan.ordered_tasks = [one, two]
    ctx = mock.Mock()
    inst = mock.Mock()

    with mock.patch("yo.tasks._task_run") as task_run, mock.patch(
        "yo.tasks.task_join"
    ) as task_join:
        plan.run(ctx, inst)
        plan.join(ctx, inst)

    assert [c.args[2].name for c in task_run.mock_calls] == ["one", "two"]
    task_join.assert_called_once_with(ctx, inst, ["one", "two"])
