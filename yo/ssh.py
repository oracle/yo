# -*- coding: utf-8 -*-
# Copyright (c) 2025, Oracle and/or its affiliates.
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
import shlex
import subprocess
import sys
import time
import typing as t

import rich.progress
from rich.progress import Progress

from yo.api import YoCtx
from yo.util import YoExc


PYVER = sys.version_info[:2]

SSH_OPTIONS = [
    # OCI instances reuse the same pool of IPs. If you use OCI a lot, you'll
    # start getting IP collisions and key verification failures. While I'm never
    # one to disable security features, this is a case where it just doesn't
    # make sense to have it enabled. First, it annoys users who expect yo to
    # "just connect", but instead it prompts yes/no, or fails due to
    # verification errors. Second, it clutters up the ~/.ssh/known_hosts and
    # encourages users to chuck out their existing host keys, because of the OCI
    # verification failures. SO, we completely neuter the feature in our config.
    "-oCheckHostIP=no",
    "-oStrictHostKeyChecking=no",
    "-oUpdateHostKeys=no",
    "-oUserKnownHostsFile=/dev/null",
    # This will suppress warnings regarding "permanently added host key", which
    # are pretty pointless given that our known hosts file is /dev/null, and so
    # it's not very permanent, is it?
    "-oLogLevel=ERROR",
    # The following two options are mostly useful for long-running serial
    # console connections. But they certainly don't harm things when you're
    # keeping SSH open for a while.
    "-oServerAliveInterval=60",
    "-oTCPKeepAlive=yes",
]
SSH_CONSOLE_OPTIONS = [
    "-oHostKeyAlgorithms=+ssh-rsa",
    # From the OpenSSH 8.5 Changelog:
    #
    #   ssh(1), sshd(8): rename the PubkeyAcceptedKeyTypes keyword to
    #   PubkeyAcceptedAlgorithms. The previous name incorrectly suggested
    #   that it control allowed key algorithms, when this option actually
    #   specifies the signature algorithms that are accepted. The previous
    #   name remains available as an alias. bz#3253
    #
    # Thankfully, the alias seems to be available for a while. Unfortunately,
    # it means we're using an "undocumented" option in order to retain maximal
    # compatibility with OpenSSH versions.
    "-oPubkeyAcceptedKeyTypes=+ssh-rsa",
]
SSH_MINIMUM_TIME = 4

warned_about_SSH_timeout = False


def ssh_args(
    ctx: YoCtx,
    interactive: bool,
) -> t.List[str]:
    cmd = SSH_OPTIONS.copy()
    cmd += shlex.split(ctx.config.ssh_args or "")
    if "-i" in cmd:
        raise YoExc(
            "you have -i configured in ssh_args, but yo now "
            "automatically selects the -i value corresponding to"
            "your configured SSH key. Please remove it from your"
            "configuration."
        )
    if ctx.config.ssh_private_key is not None:
        cmd.extend(["-i", str(ctx.config.ssh_private_key)])
    if interactive:
        cmd += shlex.split(ctx.config.ssh_interactive_args or "")
    return cmd


def ssh_cmd(
    ctx: YoCtx,
    target: str,
    extra_args: t.Iterable[str] = (),
    cmds: t.Iterable[str] = (),
) -> t.List[str]:
    cmds = list(cmds)
    cmd = ["ssh"] + ssh_args(ctx, bool(cmds))
    cmd.extend(extra_args)
    cmd.append(target)
    cmd.extend(cmds)
    return cmd


def ssh_into(
    ip: str,
    user: str,
    ctx: YoCtx,
    extra_args: t.Iterable[str] = (),
    cmds: t.Iterable[str] = (),
    quiet: bool = False,
    **kwargs: t.Any,
) -> "subprocess.CompletedProcess[bytes]":
    """
    Run an SSH command with a user@ip target. Use extra_args before the
    hostname, and then add the strings in "cmds" to the command. If cmds is
    empty, this will result in SSH to the machine. Otherwise, SSH will interpret
    them as a command to execute on the remote system, and then exit.
    """
    if not quiet:
        ctx.con.print(f"ssh [green]{user}[/green]@[blue]{ip}[/blue]...")

    extra_args = list(extra_args)
    cmd = ssh_cmd(ctx, f"{user}@{ip}", extra_args, cmds)

    if extra_args and not quiet:
        print("Exact SSH command: {}".format(repr(cmd)))

    # Python 3.6 has no capture_output= kwarg. But we can just implement it
    # here. The run() method *will* properly handle reading from the pipe,
    # so we don't risk a deadlock.
    capture_output = kwargs.get("capture_output")
    if capture_output is not None and PYVER == (3, 6):
        del kwargs["capture_output"]
        if capture_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.STDOUT

    return subprocess.run(cmd, **kwargs)


def wait_for_ssh_access(
    ip: str,
    user: str,
    ctx: YoCtx,
    timeout_sec: int = 600,
    ssh_warn_grace: int = 60,
) -> bool:
    global warned_about_SSH_timeout
    start_time = last_time = time.time()
    progress = Progress(
        rich.progress.TextColumn("{task.description}"),
        rich.progress.SpinnerColumn(),
        rich.progress.TimeElapsedColumn(),
        rich.progress.TextColumn("Timeout in:"),
        rich.progress.TimeRemainingColumn(),
        console=ctx.con,
    )
    with progress:
        t = progress.add_task(
            "Wait for SSH", total=timeout_sec, finished_time=1, start=True
        )
        while not progress.finished:
            cmd = ssh_cmd(ctx, f"{user}@{ip}", ["-q"], ["true"])
            proc = subprocess.Popen(cmd)
            rv = 1
            try:
                rv = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait()
                if (
                    not warned_about_SSH_timeout
                    and time.time() - start_time >= ssh_warn_grace
                ):
                    ctx.con.log(
                        "[magenta]Warning:[/magenta] SSH command timed out. "
                        "This is normal: it may happen early in the boot. "
                        "But, it can also happen if you're disconnected from "
                        "a VPN between you and your instance. Double check your "
                        "connection if this hangs for more than a few minutes."
                    )
                    warned_about_SSH_timeout = True
            new_time = time.time()
            progress.advance(t, new_time - last_time)
            last_time = new_time
            if rv == 0:
                ctx.con.log("SSH is up!")
                return True
    return False
