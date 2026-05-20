#!/usr/bin/env python3
from unittest import mock

import pytest

from tests.testing.factories import instance_factory
from yo.main import YoCmd
from yo.util import YoExc


def test_launch_rejects_mutually_exclusive_os_and_image(mock_cmd_ctx):
    with pytest.raises(SystemExit):
        YoCmd.main(
            "",
            args=[
                "launch",
                "--os",
                "Oracle Linux:9",
                "--image",
                "CustomImage",
            ],
        )


def test_launch_dry_run_avoids_create_and_prints_plan(mock_cmd_ctx):
    mock_cmd_ctx.get_launch_config.return_value = {
        "display_name": "test-vm",
        "username": "opc",
    }
    plan = mock.Mock()
    with mock.patch("yo.main.LaunchCmd.build_task_plan", return_value=plan):
        YoCmd.main("", args=["launch", "--dry-run"])

    mock_cmd_ctx.launch_instance.assert_not_called()
    plan.dry_run_print.assert_called_once_with()


def test_launch_ssh_implies_wait_and_connects(
    mock_cmd_ctx, mock_cmd_boundaries
):
    inst = instance_factory(id="inst1", name="test-vm", state="PROVISIONING")
    running = instance_factory(id="inst1", name="test-vm", state="RUNNING")
    plan = mock.Mock()
    plan.have_tasks.return_value = False
    mock_cmd_ctx.get_launch_config.return_value = {
        "display_name": "test-vm",
        "username": "opc",
    }
    mock_cmd_ctx.launch_instance.return_value = inst
    mock_cmd_ctx.wait_instance_state.return_value = running
    mock_cmd_ctx.get_instance_ip.return_value = "1.2.3.4"

    with mock.patch("yo.main.LaunchCmd.build_task_plan", return_value=plan):
        YoCmd.main("", args=["launch", "--ssh"])

    mock_cmd_ctx.wait_instance_state.assert_called_once_with("inst1", "RUNNING")
    mock_cmd_boundaries.wait_for_ssh_access.assert_called_once_with(
        "1.2.3.4", "opc", mock_cmd_ctx, host_key_alias="inst1"
    )
    plan.run.assert_called_once_with(mock_cmd_ctx, running)
    mock_cmd_boundaries.send_notification.assert_called_once_with(
        mock_cmd_ctx, "Instance test-vm is ready!"
    )
    mock_cmd_boundaries.ssh_into.assert_called_once_with(
        "1.2.3.4", "opc", ctx=mock_cmd_ctx, host_key_alias="inst1"
    )


def test_terminate_rejects_all_and_explicit_names(mock_cmd_ctx):
    with pytest.raises(YoExc, match="both --all and instance names"):
        YoCmd.main("", args=["terminate", "--all", "test-vm"])


def test_terminate_requires_all_or_names(mock_cmd_ctx):
    with pytest.raises(YoExc, match="either --all"):
        YoCmd.main("", args=["terminate"])


def test_terminate_dry_run_skips_api_call(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]

    YoCmd.main(
        "",
        args=["terminate", "-y", "--dry-run", "--preserve-volume", "test-vm"],
    )

    mock_cmd_ctx.terminate_instance.assert_not_called()
    messages = [c.args[0] for c in mock_cmd_ctx.con.log.call_args_list]
    assert any("DRY RUN: Would terminate inst1" in msg for msg in messages)
    assert any("would preserve root volume" in msg for msg in messages)


def test_terminate_cancelled_confirmation_does_not_terminate(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]
    with mock.patch("yo.main.Confirm.ask", return_value=False):
        YoCmd.main("", args=["terminate", "test-vm"])

    mock_cmd_ctx.terminate_instance.assert_not_called()


def test_terminate_waits_for_instance_to_terminate(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]

    YoCmd.main("", args=["terminate", "-y", "--wait", "test-vm"])

    mock_cmd_ctx.terminate_instance.assert_called_once_with(
        "inst1", preserve_volume=False
    )
    mock_cmd_ctx.wait_instance_state.assert_called_once_with(
        "inst1",
        "TERMINATED",
        max_interval_seconds=1,
        max_wait_seconds=600,
    )


def test_terminate_refuses_termination_protected_instance(mock_cmd_ctx):
    inst = instance_factory(
        id="inst1", name="test-vm", termination_protected=True
    )
    mock_cmd_ctx.get_matching_instances.return_value = [inst]

    with pytest.raises(YoExc, match="termination protected"):
        YoCmd.main("", args=["terminate", "-y", "test-vm"])
