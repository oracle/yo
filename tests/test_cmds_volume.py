#!/usr/bin/env python3
from unittest import mock

import pytest

from tests.testing.factories import instance_factory
from tests.testing.factories import volume_attachment_factory
from tests.testing.factories import volume_factory
from yo.main import YoCmd
from yo.util import YoExc


def test_volume_create_attach_requires_for(mock_cmd_ctx):
    with pytest.raises(YoExc, match="--attach requires a value for --for"):
        YoCmd.main("", args=["volume", "create", "data", "50", "--attach"])


def test_volume_create_attach_flow_uses_instance_ad(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm", ad="AD-1")
    vol = volume_factory(id="vol1", name="test-data", ad="AD-1")
    mock_cmd_ctx.get_instance_by_name.return_value = inst
    mock_cmd_ctx.create_volume.return_value = vol

    with mock.patch("yo.main.do_volume_attach") as do_volume_attach:
        YoCmd.main(
            "",
            args=[
                "volume",
                "create",
                "data",
                "50",
                "--for",
                "test-vm",
                "--attach",
            ],
        )

    mock_cmd_ctx.create_volume.assert_called_once_with("test-data", "AD-1", 50)
    mock_cmd_ctx.wait_volume.assert_called_once_with(vol, "AVAILABLE")
    do_volume_attach.assert_called_once_with(mock_cmd_ctx, mock.ANY, vol, inst)


def test_volume_attach_rejects_block_volume_to_stopped_instance(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm", state="STOPPED")
    mock_cmd_ctx.get_instance_by_name.return_value = inst

    with pytest.raises(
        YoExc, match="may only be attached while the instance is RUNNING"
    ):
        YoCmd.main("", args=["volume", "attach", "test-vol", "test-vm"])


def test_volume_attach_rejects_boot_volume_to_running_instance(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm", state="RUNNING")
    mock_cmd_ctx.get_instance_by_name.return_value = inst

    with pytest.raises(
        YoExc,
        match="Boot volumes may only be attached while the instance is STOPPED",
    ):
        YoCmd.main(
            "",
            args=["volume", "attach", "test-vol", "test-vm", "--as-boot"],
        )


def test_volume_attach_calls_attach_helper(mock_cmd_ctx):
    inst = instance_factory(id="inst1", name="test-vm", state="RUNNING")
    vol = volume_factory(id="vol1", name="test-vol")
    mock_cmd_ctx.get_instance_by_name.return_value = inst
    mock_cmd_ctx.get_volume.return_value = vol

    with mock.patch("yo.main.do_volume_attach") as do_volume_attach:
        YoCmd.main(
            "",
            args=["volume", "attach", "test-vol", "test-vm", "--iscsi"],
        )

    do_volume_attach.assert_called_once_with(mock_cmd_ctx, mock.ANY, vol, inst)


def test_volume_detach_rejects_mutually_exclusive_from_and_all(mock_cmd_ctx):
    with pytest.raises(YoExc, match="mutually exclusive"):
        YoCmd.main(
            "",
            args=[
                "volume",
                "detach",
                "test-vol",
                "--from",
                "test-vm",
                "--all",
            ],
        )


def test_volume_detach_requires_disambiguation_for_multiple_attachments(
    mock_cmd_ctx,
):
    vol = volume_factory(id="vol1", name="test-vol")
    va1 = volume_attachment_factory(volume_id="vol1", state="ATTACHED")
    va2 = volume_attachment_factory(volume_id="vol1", state="ATTACHED")
    mock_cmd_ctx.get_volume.return_value = vol
    mock_cmd_ctx.attachments_by_volume.return_value = {"vol1": [va1, va2]}

    with pytest.raises(YoExc, match="Attached to multiple instances"):
        YoCmd.main("", args=["volume", "detach", "test-vol"])


def test_volume_detach_from_single_instance(mock_cmd_ctx):
    vol = volume_factory(id="vol1", name="test-vol")
    inst = instance_factory(id="inst1", name="test-vm")
    va1 = volume_attachment_factory(
        volume_id="vol1",
        instance_id="inst1",
        state="ATTACHED",
    )
    va2 = volume_attachment_factory(
        volume_id="vol1",
        instance_id="inst2",
        state="ATTACHED",
    )
    mock_cmd_ctx.get_volume.return_value = vol
    mock_cmd_ctx.attachments_by_volume.return_value = {"vol1": [va1, va2]}
    mock_cmd_ctx.get_instance_by_name.return_value = inst

    with mock.patch("yo.main.do_detach_volume") as do_detach_volume:
        YoCmd.main(
            "",
            args=["volume", "detach", "test-vol", "--from", "test-vm"],
        )

    do_detach_volume.assert_called_once_with(mock_cmd_ctx, mock.ANY, [va1])


def test_volume_delete_detaches_before_delete_by_default(mock_cmd_ctx):
    vol = volume_factory(id="vol1", name="test-vol")
    va = volume_attachment_factory(volume_id="vol1", state="ATTACHED")
    mock_cmd_ctx.get_volume.return_value = vol
    mock_cmd_ctx.attachments_by_volume.return_value = {"vol1": [va]}

    with mock.patch("yo.main.do_detach_volume") as do_detach_volume:
        YoCmd.main("", args=["volume", "delete", "test-vol"])

    do_detach_volume.assert_called_once_with(mock_cmd_ctx, mock.ANY, [va])
    mock_cmd_ctx.delete_volume.assert_called_once_with(vol)


def test_volume_delete_no_detach_skips_detach_helper(mock_cmd_ctx):
    vol = volume_factory(id="vol1", name="test-vol")
    va = volume_attachment_factory(volume_id="vol1", state="ATTACHED")
    mock_cmd_ctx.get_volume.return_value = vol
    mock_cmd_ctx.attachments_by_volume.return_value = {"vol1": [va]}

    with mock.patch("yo.main.do_detach_volume") as do_detach_volume:
        YoCmd.main("", args=["volume", "delete", "test-vol", "--no-detach"])

    do_detach_volume.assert_not_called()
    mock_cmd_ctx.delete_volume.assert_called_once_with(vol)


def test_volume_resize_waits_for_available(mock_cmd_ctx):
    vol = volume_factory(id="vol1", name="test-vol", size_in_gbs=100)
    resized = volume_factory(id="vol1", name="test-vol", size_in_gbs=200)
    mock_cmd_ctx.get_volume.return_value = vol
    mock_cmd_ctx.resize_volume.return_value = resized

    YoCmd.main("", args=["volume", "resize", "test-vol", "200"])

    mock_cmd_ctx.resize_volume.assert_called_once_with(vol, 200)
    mock_cmd_ctx.wait_volume.assert_called_once_with(resized, "AVAILABLE")
    mock_cmd_ctx.con.log.assert_called_with("Resized!")
