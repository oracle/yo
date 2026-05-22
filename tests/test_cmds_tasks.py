#!/usr/bin/env python3
import types
from unittest import mock

from tests.testing.factories import instance_factory
from yo.main import YoCmd


def test_task_run_dry_run_prepares_and_prints_only(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    plan = mock.Mock()
    mock_cmd_ctx.get_only_instance.return_value = inst

    with mock.patch("yo.main.TaskPlan", return_value=plan) as task_plan_cls:
        YoCmd.main("", args=["task", "run", "prep", "--dry-run"])

    task_plan_cls.assert_called_once_with(["prep"])
    plan.prepare.assert_called_once_with(mock_cmd_ctx)
    plan.dry_run_print.assert_called_once_with()
    plan.run.assert_not_called()
    plan.join.assert_not_called()


def test_task_run_wait_runs_and_joins(mock_cmd_ctx, mock_cmd_boundaries):
    inst = instance_factory(id="inst1", name="test-vm")
    plan = mock.Mock()
    mock_cmd_ctx.get_only_instance.return_value = inst

    with mock.patch("yo.main.TaskPlan", return_value=plan):
        YoCmd.main("", args=["task", "run", "prep", "--wait"])

    plan.prepare.assert_called_once_with(mock_cmd_ctx)
    plan.run.assert_called_once_with(mock_cmd_ctx, inst)
    plan.join.assert_called_once_with(mock_cmd_ctx, inst)
    mock_cmd_boundaries.send_notification.assert_called_once_with(
        mock_cmd_ctx.c, "Task ['prep'] complete on instance test-vm"
    )


def test_task_status_prints_table(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    statuses = {"prep": ("RUNNING", 1234)}
    mock_cmd_ctx.get_only_instance.return_value = inst

    with mock.patch(
        "yo.main.task_get_status", return_value=statuses
    ), mock.patch(
        "yo.main.task_status_to_table", return_value="TABLE"
    ) as to_table:
        YoCmd.main("", args=["task", "status"])

    to_table.assert_called_once_with(statuses)
    mock_cmd_ctx.con.print.assert_called_with("TABLE")


def test_task_wait_waits_on_named_task(mock_cmd_ctx, mock_cmd_boundaries):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_only_instance.return_value = inst

    with mock.patch("yo.main.task_join") as task_join:
        YoCmd.main("", args=["task", "wait", "prep"])

    task_join.assert_called_once_with(mock_cmd_ctx, inst, wait_tasks=["prep"])
    mock_cmd_boundaries.send_notification.assert_called_once_with(
        mock_cmd_ctx.c, "Task prep complete on instance test-vm"
    )


def test_task_join_waits_for_all_tasks(mock_cmd_ctx, mock_cmd_boundaries):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_only_instance.return_value = inst

    with mock.patch("yo.main.task_join") as task_join:
        YoCmd.main("", args=["task", "join"])

    task_join.assert_called_once_with(mock_cmd_ctx, inst)
    mock_cmd_boundaries.send_notification.assert_called_once_with(
        mock_cmd_ctx.c, "All tasks complete on instance test-vm"
    )


def test_task_info_prints_metadata_and_script(mock_cmd_ctx):
    task = mock.Mock(
        path="/tmp/prep",
        dependencies=["net"],
        conflicts=["db"],
        script="echo prep",
    )
    with mock.patch("yo.main.YoTask.load", return_value=task), mock.patch(
        "rich.syntax.Syntax", return_value="SYNTAX"
    ):
        YoCmd.main("", args=["task", "info", "prep"])

    calls = [c.args[0] for c in mock_cmd_ctx.con.print.call_args_list]
    assert "File: /tmp/prep" in calls
    assert "Dependencies: net" in calls
    assert "Conflicts: db" in calls
    assert "SYNTAX" in calls


def test_task_list_renders_dependency_and_conflict_metadata(mock_cmd_ctx):
    prep = types.SimpleNamespace(
        dependencies=["net"],
        conflicts=[],
        path="/tmp/prep",
    )
    test = types.SimpleNamespace(
        dependencies=[],
        conflicts=["prep"],
        path="/tmp/test",
    )
    with mock.patch(
        "yo.main.list_tasks", return_value=["prep", "test"]
    ), mock.patch("yo.main.YoTask.load", side_effect=[prep, test]):
        YoCmd.main("", args=["task", "list"])

    table = mock_cmd_ctx.con.print.call_args.args[0]
    assert table._columns == ["Name", "D/C", "Path"]
    assert table._rows == [
        ("prep", "Depends: net", "/tmp/prep"),
        ("test", "Conflicts: prep", "/tmp/test"),
    ]
