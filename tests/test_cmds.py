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

from tests.testing.factories import image_factory
from tests.testing.factories import instance_factory
from tests.testing.rich import FakeTable
from yo.main import YoCmd
from yo.util import strftime


@pytest.fixture
def mock_ctx():
    es = contextlib.ExitStack()
    with es:
        mock_ctx = es.enter_context(
            mock.patch("yo.main.YoCtx"),
        ).return_value
        mock_con = es.enter_context(
            mock.patch(
                "rich.console.Console",
                autospec=True,
            )
        ).return_value
        mock_ctx.con = mock_con
        es.enter_context(
            mock.patch(
                "rich.table.Table",
                new=FakeTable,
            )
        )
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


def test_ssh_one_instance(mock_ctx, mock_ssh):
    mock_ctx.get_only_instance.return_value = instance_factory()
    mock_ctx.get_image.return_value = image_factory()
    mock_ctx.get_instance_ip.return_value = "1.2.3.4"
    mock_ctx.get_ssh_user.return_value = "opc"
    YoCmd.main("", args=["ssh"])
    mock_ssh.ssh_into.assert_called_once_with(
        "1.2.3.4",
        "opc",
        ctx=mock_ctx,
        extra_args=[],
        cmds=[],
        quiet=False,
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
    mock_ctx.get_instance_by_name.return_value = instance_factory()
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
        ctx=mock_ctx,
        extra_args=[],
        cmds=[],
        quiet=False,
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
    mock_ssh.wait.assert_called_once_with("1.2.3.4", "opc", mock_ctx)
    mock_notify.assert_called_once_with(
        mock_ctx, "Instance myinstance is connected via SSH!"
    )
    mock_ssh.ssh_into.assert_called_once_with(
        "1.2.3.4",
        "opc",
        ctx=mock_ctx,
        extra_args=["-A"],
        cmds=[],
        quiet=False,
    )
