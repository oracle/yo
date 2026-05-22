#!/usr/bin/env python3
# Copyright (c) 2023, Oracle and/or its affiliates.
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or data
# (collectively the "Software"), free of charge and under any and all copyright
# rights in the Software, and any and all patent rights owned or freely
# licensable by each licensor hereunder covering either (i) the unmodified
# Software as contributed to or provided by such licensor, or (ii) the Larger
# Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the
#     lrgrwrks.txt file if one is included with the Software (each a "Larger
#     Work" to which the Software is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright notice
# and either this complete permission notice or at a minimum a reference to the
# UPL must be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import contextlib
import dataclasses
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from tests.testing.factories import image_factory
from tests.testing.factories import instance_factory
from tests.testing.rich import FakeTable
from yo.main import YoCmd
from yo.util import strftime
from yo.util import YoExc
from yo.util import YoRegion


class ImmediateFuture:
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value


class ImmediateExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        return ImmediateFuture(fn(*args, **kwargs))


@pytest.fixture
def mock_ctx():
    es = contextlib.ExitStack()
    with es:
        cc = es.enter_context(
            mock.patch("yo.main.YoCtx"),
        ).return_value
        mock_ctx = mock.MagicMock()
        cc.config = config_factory()
        cc.region = cc.config.region
        cc._tpe = ImmediateExecutor()
        mock_ctx.list_volumes.return_value = []
        mock_con = es.enter_context(
            mock.patch(
                "rich.console.Console",
                autospec=True,
            )
        ).return_value
        cc.con = mock_con
        cc.rc.return_value = mock_ctx
        mock_ctx.c = cc
        mock_ctx.config = cc.config
        mock_ctx.con = cc.con
        mock_ctx._tpe = cc._tpe
        es.enter_context(
            mock.patch(
                "rich.table.Table",
                new=FakeTable,
            )
        )
        YoCmd.cc = cc
        YoCmd.c = mock_ctx
        yield mock_ctx


@dataclasses.dataclass
class SshMocks:
    ssh_into: mock.Mock
    wait: mock.Mock


@pytest.fixture(autouse=True)  # always prevent SSH
def mock_ssh():
    with contextlib.ExitStack() as es:
        ssh_into = es.enter_context(
            mock.patch("yo.main.ssh_into", autospec=True)
        )
        wait = es.enter_context(
            mock.patch("yo.main.wait_for_ssh_access", autospec=True)
        )
        yield SshMocks(ssh_into, wait)


@pytest.fixture(autouse=True)  # always prevent system notifications
def mock_notify():
    with mock.patch("yo.main.send_notification", autospec=True) as notify:
        yield notify


def test_list_empty(mock_ctx):
    mock_ctx.list_instances.return_value = []
    YoCmd.main("blah", args=["list"])
    mock_ctx.list_instances.assert_called_once_with(
        verbose=False, show_all=False
    )
    mock_ctx.con.print.assert_called_once()
    table = mock_ctx.con.print.call_args[0][0]
    assert table._columns == ["Name", "Shape", "Mem", "CPU", "State", "Created"]


def test_list_results(mock_ctx):
    insts = [
        instance_factory(),
        instance_factory(),
    ]
    mock_ctx.list_instances.return_value = insts
    YoCmd.main("", args=["list"])
    mock_ctx.list_instances.assert_called_once_with(
        verbose=False, show_all=False
    )
    mock_ctx.con.print.assert_called_once()
    table = mock_ctx.con.print.call_args[0][0]
    assert table._columns == ["Name", "Shape", "Mem", "CPU", "State", "Created"]
    assert table._rows == [
        (
            insts[0].name,
            insts[0].shape,
            str(insts[0].memory_gb),
            str(insts[0].ocpu),
            insts[0].state,
            strftime(insts[0].time_created),
        ),
        (
            insts[1].name,
            insts[1].shape,
            str(insts[1].memory_gb),
            str(insts[1].ocpu),
            insts[1].state,
            strftime(insts[1].time_created),
        ),
    ]


def test_list_all_regions_results(mock_ctx):
    r1 = mock_ctx.config.region
    r2 = "us-phoenix-1"
    mock_ctx.config.regions[r2] = YoRegion(r2, "vcn2", "sub2")
    mock_ctx.c._tpe = ImmediateExecutor()
    mock_ctx._tpe = mock_ctx.c._tpe

    region2_ctx = mock.MagicMock()
    region2_ctx.c = mock_ctx.c
    region2_ctx.config = dataclasses.replace(mock_ctx.config, region=r2)
    region2_ctx.con = mock_ctx.con
    mock_ctx.c.rc.side_effect = lambda region: {
        r1: mock_ctx,
        r2: region2_ctx,
    }[region]

    insts = [
        instance_factory(name="test-r1"),
        instance_factory(name="test-r2"),
    ]
    mock_ctx.list_instances.return_value = [insts[0]]
    region2_ctx.list_instances.return_value = [insts[1]]
    mock_ctx.list_volumes.return_value = []
    region2_ctx.list_volumes.return_value = []
    mock_ctx.get_all_instance_ips.return_value = {insts[0].id: "10.0.0.1"}
    region2_ctx.get_all_instance_ips.return_value = {insts[1].id: "10.0.0.2"}

    YoCmd.main("", args=["list", "--all-regions", "--ip"])

    assert [args[0] for _, args, _ in mock_ctx._tpe.submitted] == [r1, r2]
    mock_ctx.list_instances.assert_called_once_with(
        verbose=False, show_all=False
    )
    region2_ctx.list_instances.assert_called_once_with(
        verbose=False, show_all=False
    )
    mock_ctx.get_all_instance_ips.assert_called_once_with([insts[0]])
    region2_ctx.get_all_instance_ips.assert_called_once_with([insts[1]])

    mock_ctx.con.print.assert_called_once()
    table = mock_ctx.con.print.call_args[0][0]
    assert table._columns == [
        "Region",
        "Name",
        "Shape",
        "Mem",
        "CPU",
        "State",
        "Created",
        "IP",
    ]
    assert table._rows == [
        (
            r1,
            insts[0].name,
            insts[0].shape,
            str(insts[0].memory_gb),
            str(insts[0].ocpu),
            insts[0].state,
            strftime(insts[0].time_created),
            "10.0.0.1",
        ),
        (
            r2,
            insts[1].name,
            insts[1].shape,
            str(insts[1].memory_gb),
            str(insts[1].ocpu),
            insts[1].state,
            strftime(insts[1].time_created),
            "10.0.0.2",
        ),
    ]


def test_list_top_level_help_mentions_all_regions():
    list_cmd = next(cmd for cmd in YoCmd.iter_commands() if cmd.name == "list")
    assert "--all-regions" in list_cmd.description


def test_ssh_one_instance(mock_ctx, mock_ssh):
    inst = instance_factory()
    mock_ctx.get_only_instance.return_value = inst
    mock_ctx.get_image.return_value = image_factory()
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.get_ssh_user.return_value = "opc"
    YoCmd.main("", args=["ssh"])
    mock_ssh.ssh_into.assert_called_once_with(
        "1.2.3.4",
        "opc",
        ctx=mock_ctx.c,
        extra_args=[],
        cmds=[],
        quiet=False,
        host_key_alias=inst.id,
    )
    # need to ensure that we used get_only_instance()
    mock_ctx.get_only_instance.assert_called_once_with(
        ("RUNNING", "PROVISIONING", "STARTING"),
        (),
    )
    mock_ctx.wait_instance_state.assert_not_called()
    mock_ssh.wait.assert_not_called()


@pytest.mark.parametrize("exact_name", [True, None])
@pytest.mark.parametrize("dash_n", [True, False])
def test_ssh_specify(mock_ctx, mock_ssh, exact_name, dash_n):
    inst = instance_factory()
    mock_ctx.get_instance_by_name.return_value = inst
    mock_ctx.get_image.return_value = image_factory()
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.get_ssh_user.return_value = "opc"
    args = ["ssh"]
    if dash_n:
        args.extend(["-n", "myinst"])
    else:
        args.append("myinst")
    if exact_name:
        args.append("--exact-name")
    YoCmd.main("", args=args)
    mock_ssh.ssh_into.assert_called_once_with(
        "1.2.3.4",
        "opc",
        ctx=mock_ctx.c,
        extra_args=[],
        cmds=[],
        quiet=False,
        host_key_alias=inst.id,
    )
    mock_ctx.get_instance_by_name.assert_called_once_with(
        "myinst",
        ("RUNNING", "PROVISIONING", "STARTING"),
        (),
        exact_name=exact_name,
    )
    mock_ctx.wait_instance_state.assert_not_called()
    mock_ssh.wait.assert_not_called()


@pytest.mark.parametrize("state", ["RUNNING", "STARTING", "PROVISIONING"])
def test_ssh_wait(mock_ctx, mock_ssh, mock_notify, state):
    inst = instance_factory(state=state, name="myinstance")
    mock_ctx.get_only_instance.return_value = inst
    mock_ctx.get_image.return_value = image_factory()
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.get_ssh_user.return_value = "opc"
    YoCmd.main("", args=["ssh", "-Aw"])
    if state != "RUNNING":
        mock_ctx.wait_instance_state.assert_called_once_with(
            inst.id,
            "RUNNING",
            max_interval_seconds=1,
            max_wait_seconds=600,
        )
    else:
        mock_ctx.wait_instance_state.assert_not_called()
    mock_ssh.wait.assert_called_once_with(
        "1.2.3.4", "opc", mock_ctx.c, host_key_alias=inst.id
    )
    mock_notify.assert_called_once_with(
        mock_ctx.c, "Instance myinstance is connected via SSH!"
    )
    mock_ssh.ssh_into.assert_called_once_with(
        "1.2.3.4",
        "opc",
        ctx=mock_ctx.c,
        extra_args=["-A"],
        cmds=[],
        quiet=False,
        host_key_alias=inst.id,
    )


def test_ssh_rejects_invalid_username_prefix(mock_ctx):
    with pytest.raises(YoExc, match="SSH username"):
        YoCmd.main("", args=["ssh", "Bad@myinst"])


def test_vnc_launch_splits_configured_command(mock_ctx):
    inst = instance_factory()
    mock_ctx.get_only_instance.return_value = inst
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.config.vnc_prog = "viewer --host {host} --port {port}"
    proc = mock.Mock()

    with mock.patch("yo.main.subprocess.Popen", return_value=proc) as popen:
        YoCmd.main("", args=["vnc", "--no-tunnel"])

    popen.assert_called_once_with(
        ["viewer", "--host", "1.2.3.4", "--port", "5901"]
    )
    proc.wait.assert_called_once_with()


def test_rdp_launch_splits_configured_command(mock_ctx):
    inst = instance_factory()
    mock_ctx.get_only_instance.return_value = inst
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.get_windows_initial_creds.return_value = (None, None)
    mock_ctx.config.rdp_prog = "rdp-viewer {host}:{port}"
    proc = mock.Mock()

    with mock.patch("yo.main.subprocess.Popen", return_value=proc) as popen:
        YoCmd.main("", args=["rdp", "--no-tunnel"])

    popen.assert_called_once_with(["rdp-viewer", "1.2.3.4:3389"])
    proc.wait.assert_called_once_with()


def test_rsync_uses_ssh_args_with_host_alias(mock_ctx):
    inst = instance_factory(id="inst1")
    mock_ctx.get_only_instance.return_value = inst
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.get_ssh_user.return_value = "opc"

    with mock.patch(
        "yo.main.ssh_args", return_value=["-oHostKeyAlias=inst1"]
    ) as ssh_args, mock.patch("yo.main.subprocess.run") as run:
        YoCmd.main("", args=["rsync", "src", ":dst"])

    ssh_args.assert_called_once_with(mock_ctx.c, False, "inst1")
    run.assert_called_once_with(
        [
            "rsync",
            "-e",
            "ssh -oHostKeyAlias=inst1",
            "src",
            "opc@1.2.3.4:dst",
        ]
    )
