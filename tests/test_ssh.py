#!/usr/bin/env python3
from types import SimpleNamespace
from unittest import mock

import pytest

import yo.ssh as ssh
from yo.util import YoExc


@pytest.fixture(autouse=True)
def fake_known_hosts_file():
    with mock.patch(
        "yo.ssh.known_hosts_file", return_value="/tmp/yo-known-hosts"
    ):
        yield


def _ctx(
    *,
    ssh_args: str = "",
    ssh_interactive_args: str = "",
    ssh_private_key: str = "/tmp/test-key",
):
    return SimpleNamespace(
        config=SimpleNamespace(
            ssh_args=ssh_args,
            ssh_interactive_args=ssh_interactive_args,
            ssh_private_key=ssh_private_key,
        ),
        con=mock.Mock(),
    )


def test_ssh_args_adds_config_key_and_interactive_args():
    ctx = _ctx(
        ssh_args="-oProxyCommand=none",
        ssh_interactive_args="-t",
        ssh_private_key="/tmp/mykey",
    )

    non_interactive = ssh.ssh_args(ctx, interactive=False)
    interactive = ssh.ssh_args(ctx, interactive=True)

    assert "-oProxyCommand=none" in non_interactive
    assert "-oStrictHostKeyChecking=accept-new" in non_interactive
    assert "-oUserKnownHostsFile=/tmp/yo-known-hosts" in non_interactive
    assert "-i" in non_interactive
    assert "/tmp/mykey" in non_interactive
    assert "-t" not in non_interactive
    assert "-t" in interactive


def test_ssh_args_configured_options_win_by_appearing_first():
    ctx = _ctx(
        ssh_args=(
            "-oStrictHostKeyChecking=no "
            "-oUserKnownHostsFile=/dev/null "
            "-oHostKeyAlias=custom"
        ),
        ssh_private_key=None,
    )

    args = ssh.ssh_args(ctx, interactive=False, host_key_alias="ocid1.test")

    assert args.index("-oStrictHostKeyChecking=no") < args.index(
        "-oStrictHostKeyChecking=accept-new"
    )
    assert args.index("-oUserKnownHostsFile=/dev/null") < args.index(
        "-oUserKnownHostsFile=/tmp/yo-known-hosts"
    )
    assert args.index("-oHostKeyAlias=custom") < args.index(
        "-oHostKeyAlias=ocid1.test"
    )


def test_ssh_args_rejects_identity_in_config():
    ctx = _ctx(ssh_args="-i /tmp/another")
    with pytest.raises(YoExc, match="automatically selects the -i value"):
        ssh.ssh_args(ctx, interactive=False)


def test_ssh_cmd_puts_target_before_remote_command():
    ctx = _ctx(ssh_private_key=None)
    cmd = ssh.ssh_cmd(
        ctx,
        "opc@1.2.3.4",
        extra_args=["-A"],
        cmds=["echo", "hello"],
    )
    assert cmd[0] == "ssh"
    assert cmd[-4:] == ["--", "opc@1.2.3.4", "echo", "hello"]
    assert "-A" in cmd


def test_ssh_cmd_adds_host_key_alias():
    ctx = _ctx(ssh_private_key=None)
    cmd = ssh.ssh_cmd(ctx, "opc@1.2.3.4", host_key_alias="ocid1.instance")

    assert "-oHostKeyAlias=ocid1.instance" in cmd
    assert cmd[-2:] == ["--", "opc@1.2.3.4"]


def test_ssh_into_rejects_invalid_username():
    ctx = _ctx(ssh_private_key=None)

    with pytest.raises(YoExc, match="SSH username"):
        ssh.ssh_into("1.2.3.4", "-oProxyCommand=bad", ctx, quiet=True)


def test_ssh_into_prints_and_runs_command():
    ctx = _ctx(ssh_private_key=None)
    with mock.patch(
        "yo.ssh.ssh_cmd", return_value=["ssh", "target"]
    ), mock.patch("yo.ssh.subprocess.run") as run:
        ssh.ssh_into("1.2.3.4", "opc", ctx, extra_args=["-A"])

    ctx.con.print.assert_called_once()
    run.assert_called_once_with(["ssh", "target"])


def test_ssh_into_py36_capture_output_fallback():
    ctx = _ctx(ssh_private_key=None)
    with mock.patch("yo.ssh.PYVER", (3, 6)), mock.patch(
        "yo.ssh.ssh_cmd", return_value=["ssh", "target"]
    ), mock.patch("yo.ssh.subprocess.run") as run:
        ssh.ssh_into(
            "1.2.3.4",
            "opc",
            ctx,
            quiet=True,
            capture_output=True,
            check=True,
        )

    run.assert_called_once_with(
        ["ssh", "target"],
        check=True,
        stdout=ssh.subprocess.PIPE,
        stderr=ssh.subprocess.STDOUT,
    )


def test_wait_for_ssh_access_returns_true_when_probe_succeeds():
    ctx = _ctx(ssh_private_key=None)
    ssh.warned_about_SSH_timeout = False

    class FakeProgress:
        def __init__(self, *args, **kwargs):
            self.elapsed = 0.0
            self.total = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def add_task(self, *args, total=0, **kwargs):
            self.total = float(total)
            return 1

        @property
        def finished(self):
            return self.elapsed >= self.total

        def advance(self, _task, amount):
            self.elapsed += amount

    p1 = mock.Mock()
    p1.wait.return_value = 1
    p2 = mock.Mock()
    p2.wait.return_value = 0
    tick = {"t": 0.0}

    def fake_time():
        tick["t"] += 1.0
        return tick["t"]

    with mock.patch("yo.ssh.Progress", FakeProgress), mock.patch(
        "yo.ssh.ssh_cmd", return_value=["ssh", "probe"]
    ), mock.patch(
        "yo.ssh.subprocess.Popen", side_effect=[p1, p2]
    ) as popen, mock.patch(
        "yo.ssh.time.time", side_effect=fake_time
    ):
        assert ssh.wait_for_ssh_access("1.2.3.4", "opc", ctx, timeout_sec=10)

    assert popen.call_count == 2
    ctx.con.log.assert_called_with("SSH is up!")


def test_wait_for_ssh_access_timeout_logs_warning_and_returns_false():
    ctx = _ctx(ssh_private_key=None)
    ssh.warned_about_SSH_timeout = False

    class FakeProgress:
        def __init__(self, *args, **kwargs):
            self.elapsed = 0.0
            self.total = 0.0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def add_task(self, *args, total=0, **kwargs):
            self.total = float(total)
            return 1

        @property
        def finished(self):
            return self.elapsed >= self.total

        def advance(self, _task, amount):
            self.elapsed += amount

    proc = mock.Mock()
    proc.wait.side_effect = [ssh.subprocess.TimeoutExpired("ssh", 5), 1]
    tick = {"t": 0.0}

    def fake_time():
        tick["t"] += 10.0
        return tick["t"]

    with mock.patch("yo.ssh.Progress", FakeProgress), mock.patch(
        "yo.ssh.ssh_cmd", return_value=["ssh", "probe"]
    ), mock.patch("yo.ssh.subprocess.Popen", return_value=proc), mock.patch(
        "yo.ssh.time.time", side_effect=fake_time
    ):
        assert not ssh.wait_for_ssh_access(
            "1.2.3.4", "opc", ctx, timeout_sec=5, ssh_warn_grace=1
        )

    proc.terminate.assert_called_once_with()
    assert ssh.warned_about_SSH_timeout
    assert any(
        "SSH command timed out" in c.args[0] for c in ctx.con.log.call_args_list
    )
