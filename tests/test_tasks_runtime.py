#!/usr/bin/env python3
import types
from unittest import mock

import pytest

from yo.tasks import _task_run
from yo.tasks import task_get_status
from yo.tasks import task_join
from yo.tasks import YoTask
from yo.util import YoExc


def _ctx() -> mock.Mock:
    ctx = mock.Mock()
    ctx.c = ctx
    ctx.c.config.task_dir_safe = "/tmp/yo tasks"
    ctx.c.config.task_dir = "/tmp/yo tasks"
    ctx.get_instance_ip.return_value = "1.2.3.4"
    ctx.get_ssh_user.return_value = "opc"
    return ctx


def _inst() -> types.SimpleNamespace:
    return types.SimpleNamespace(name="vm1", id="ocid1.instance.test")


def _task(name: str, *, sendfiles=None) -> YoTask:
    return YoTask(
        name=name,
        path=f"/tmp/{name}",
        script="echo hi",
        dependencies=[],
        conflicts=[],
        prereq_for=[],
        include_files=[],
        sendfiles=list(sendfiles or []),
    )


def test_task_run_without_sendfiles_uses_single_ssh():
    ctx = _ctx()
    task = _task("basic")

    with mock.patch("yo.tasks.get_tasklib", return_value=""), mock.patch(
        "yo.tasks.get_safe_heredoc",
        return_value="HEREDOC",
    ), mock.patch("yo.tasks.ssh_into") as ssh_into:
        _task_run(ctx, _inst(), task)

    ssh_into.assert_called_once()
    call = ssh_into.call_args
    assert call.kwargs["cmds"] and "HEREDOC" in call.kwargs["cmds"][0]
    assert "umask 077" in call.kwargs["cmds"][0]
    assert "chmod 700" in call.kwargs["cmds"][0]
    assert call.kwargs["host_key_alias"] == "ocid1.instance.test"


def test_task_run_with_sendfiles_copies_before_launch(tmp_path):
    ctx = _ctx()
    send_a = tmp_path / "a.txt"
    send_b = tmp_path / "b.txt"
    send_a.write_text("a")
    send_b.write_text("b")
    task = _task("with-files", sendfiles=[send_a, send_b])

    mkdir_res = types.SimpleNamespace(stdout=b"/remote/files")
    with mock.patch("yo.tasks.get_tasklib", return_value=""), mock.patch(
        "yo.tasks.ssh_args", return_value=["-oStrictHostKeyChecking=no"]
    ), mock.patch(
        "yo.tasks.ssh_into", side_effect=[mkdir_res, mock.Mock()]
    ) as ssh_into, mock.patch(
        "yo.tasks.subprocess.run"
    ) as subproc_run:
        _task_run(ctx, _inst(), task)

    assert ssh_into.call_count == 2
    scp_cmd = subproc_run.call_args.args[0]
    assert scp_cmd[:2] == ["scp", "-oStrictHostKeyChecking=no"]
    assert "--" in scp_cmd
    assert str(send_a) in scp_cmd and str(send_b) in scp_cmd
    assert scp_cmd[-1] == "opc@1.2.3.4:/remote/files/"
    assert ssh_into.call_args_list[0].kwargs["host_key_alias"] == (
        "ocid1.instance.test"
    )
    assert ssh_into.call_args_list[1].kwargs["host_key_alias"] == (
        "ocid1.instance.test"
    )


def test_task_get_status_parses_running_waiting_and_success():
    ctx = _ctx()
    output = "\n".join(
        [
            "/tmp/yo tasks/build/pid:1234",
            "/tmp/yo tasks/waiter/pid:2345",
            "/tmp/yo tasks/waiter/wait:compile",
            "/tmp/yo tasks/done/status:0",
        ]
    ).encode()
    ssh_res = types.SimpleNamespace(stdout=output)

    with mock.patch("yo.tasks.ssh_into", return_value=ssh_res):
        status = task_get_status(ctx, _inst())

    assert status["build"] == ("RUNNING", 1234)
    assert status["waiter"] == ("WAITING", "compile")
    assert status["done"] == ("SUCCESS", 0)


def test_task_get_status_rejects_malformed_output():
    ctx = _ctx()
    bad = types.SimpleNamespace(stdout=b"not-a-task-line")

    with mock.patch("yo.tasks.ssh_into", return_value=bad), pytest.raises(
        YoExc, match="bad task status data"
    ):
        task_get_status(ctx, _inst())


def test_task_join_waits_for_all_tasks_when_wait_list_empty():
    ctx = _ctx()
    inst = _inst()
    states = [
        {"a": ("RUNNING", 10), "b": ("SUCCESS", 0)},
        {"a": ("SUCCESS", 0), "b": ("SUCCESS", 0)},
    ]

    class FakeLive:
        def __init__(self, console):
            self.console = console

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, _):
            return None

    with mock.patch("yo.tasks.Live", FakeLive), mock.patch(
        "yo.tasks.task_get_status", side_effect=states
    ) as get_status, mock.patch("yo.tasks.task_status_to_table"), mock.patch(
        "yo.tasks.time.sleep"
    ) as sleep:
        out = task_join(ctx, inst)

    assert out == states[-1]
    assert get_status.call_count == 2
    sleep.assert_called_once_with(1)


def test_task_join_wait_tasks_terminates_when_target_finishes():
    ctx = _ctx()
    inst = _inst()
    states = [
        {"target": ("RUNNING", 11), "other": ("RUNNING", 12)},
        {"target": ("SUCCESS", 0), "other": ("RUNNING", 12)},
    ]

    class FakeLive:
        def __init__(self, console):
            self.console = console

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, _):
            return None

    with mock.patch("yo.tasks.Live", FakeLive), mock.patch(
        "yo.tasks.task_get_status", side_effect=states
    ) as get_status, mock.patch("yo.tasks.task_status_to_table"), mock.patch(
        "yo.tasks.time.sleep"
    ) as sleep:
        out = task_join(ctx, inst, wait_tasks=["target"])

    assert out == states[-1]
    assert get_status.call_count == 2
    sleep.assert_called_once_with(1)
