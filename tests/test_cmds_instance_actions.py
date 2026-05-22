#!/usr/bin/env python3
from unittest import mock

import pytest

from tests.testing.factories import instance_factory
from yo.main import YoCmd
from yo.util import YoExc


def test_start_waits_and_notifies(mock_cmd_ctx, mock_cmd_boundaries):
    inst = instance_factory(id="inst1", name="test-vm")
    running = instance_factory(id="inst1", name="test-vm", state="RUNNING")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]
    mock_cmd_ctx.wait_instance_state.return_value = running

    YoCmd.main("", args=["start", "--wait", "test-vm"])

    mock_cmd_ctx.instance_action.assert_called_once_with("inst1", "START")
    mock_cmd_ctx.wait_instance_state.assert_called_once_with(
        "inst1",
        "RUNNING",
        max_interval_seconds=1,
        max_wait_seconds=600,
    )
    mock_cmd_boundaries.send_notification.assert_called_once_with(
        mock_cmd_ctx.c, "Instance test-vm is now in state RUNNING"
    )


def test_reboot_force_dry_run_does_not_call_api(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]

    YoCmd.main("", args=["reboot", "--force", "--dry-run", "-y", "test-vm"])

    mock_cmd_ctx.instance_action.assert_not_called()
    messages = [c.args[0] for c in mock_cmd_ctx.con.log.call_args_list]
    assert any("DRY RUN: Would RESET inst1" in msg for msg in messages)


def test_reboot_ssh_requires_single_instance(mock_cmd_ctx):
    mock_cmd_ctx.get_matching_instances.return_value = [
        instance_factory(id="a", name="test-a"),
        instance_factory(id="b", name="test-b"),
    ]

    with pytest.raises(YoExc, match="--ssh"):
        YoCmd.main("", args=["reboot", "--ssh", "-y", "test-a", "test-b"])


def test_reboot_ssh_connects_after_wait(mock_cmd_ctx, mock_cmd_boundaries):
    inst = instance_factory(id="inst1", name="test-vm")
    running = instance_factory(id="inst1", name="test-vm", state="RUNNING")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]
    mock_cmd_ctx.wait_instance_state.return_value = running
    mock_cmd_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_cmd_ctx.get_ssh_user.return_value = "opc"

    YoCmd.main("", args=["reboot", "--ssh", "-y", "test-vm"])

    mock_cmd_ctx.instance_action.assert_called_once_with("inst1", "SOFTRESET")
    mock_cmd_ctx.wait_instance_state.assert_called_once_with(
        "inst1",
        "RUNNING",
        max_interval_seconds=1,
        max_wait_seconds=600,
    )
    mock_cmd_boundaries.wait_for_ssh_access.assert_called_once_with(
        "1.2.3.4", "opc", mock_cmd_ctx.c, host_key_alias="inst1"
    )
    mock_cmd_boundaries.send_notification.assert_has_calls(
        [
            mock.call(
                mock_cmd_ctx.c, "Instance test-vm is now in state RUNNING"
            ),
            mock.call(mock_cmd_ctx.c, "Instance test-vm is connected via SSH"),
        ]
    )
    mock_cmd_boundaries.ssh_into.assert_called_once_with(
        "1.2.3.4", "opc", ctx=mock_cmd_ctx.c, host_key_alias="inst1"
    )


def test_resize_requires_any_change_argument(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm")
    mock_cmd_ctx.get_matching_instances.return_value = [inst]

    with pytest.raises(YoExc, match="no change requested"):
        YoCmd.main("", args=["resize", "test-vm"])

    mock_cmd_ctx.resize_instance.assert_not_called()


def test_resize_with_cpu_and_mem_calls_resize_instance(mock_cmd_ctx):
    inst = instance_factory(
        id="inst1", name="test-vm", shape="VM.Standard.E2.1"
    )
    mock_cmd_ctx.get_matching_instances.return_value = [inst]

    YoCmd.main("", args=["resize", "--cpu", "4", "--mem", "32", "test-vm"])

    mock_cmd_ctx.resize_instance.assert_called_once_with(
        inst, "VM.Standard.E2.1", 4.0, 32.0
    )


def test_ip_with_explicit_names_prints_table(mock_cmd_ctx):
    inst1 = instance_factory(id="inst1", name="test-vm")
    inst2 = instance_factory(id="inst2", name="test-db")
    mock_cmd_ctx.get_matching_instances.return_value = [inst1, inst2]
    mock_cmd_ctx.get_instance_ip.side_effect = ["1.1.1.1", "2.2.2.2"]

    YoCmd.main("", args=["ip", "test-vm", "test-db"])

    mock_cmd_ctx.get_matching_instances.assert_called_once_with(
        {"test-vm", "test-db"},
        (),
        ("TERMINATED",),
    )
    mock_cmd_ctx.get_all_instance_ips.assert_called_once_with([inst1, inst2])
    table = mock_cmd_ctx.con.print.call_args.args[0]
    assert table._columns == ["Name", "IP"]
    assert table._rows == [
        ("test-vm", "1.1.1.1"),
        ("test-db", "2.2.2.2"),
    ]
