# -*- coding: utf-8 -*-
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
"""
yo is a CLI client for managing OCI instances.

Use yo -h to get a listing of all available subcommands. Use yo help (what you
are currently viewing) to see an overview of the tool. For information on a
particular subcommand, use yo COMMAND -h.

You can create instances with "launch", as well as "stop", "start", and
"reboot" them. If you'd like to reboot without contacting the operating system,
consider "reboot --force". You can "ssh" to your instance, or use "console" to
view the serial console, or just use "ip" to get the IP address. When done with
an instance, "terminate" it.

yo manages instance names in an opinionated way. Suppose your global username
is "stepbren". yo believes that:

  1. All instance names should be prefixed by "stepbren-".
  2. Name collisions should be avoided by appending a "-N" suffix, where N
     increments.

To enforce this, yo will automatically apply these rules on instance creation,
and when looking up an instance name, if your name doesn't already fit the
criteria. Some examples:

  * yo launch -n bug           # new instance stepbren-bug
  * yo launch -n stepbren-bug  # same as above
  * yo launch -n bug           # if stepbren-bug already exists, creates
                               #  stepbren-bug-1
  * yo launch -n bug-1         # if stepbren-bug-1 already exists, creates
                               #  stepbren-bug-2
  * yo ssh bug                 # connect to stepbren-bug

To avoid this behavior, you can pass --exact-name to various subcommands, or
set "exact_name = true" in the [yo] section of your config.
"""
import argparse
import base64
import collections
import contextlib
import dataclasses
import importlib
import inspect
import os
import random
import re
import shlex
import string
import subprocess
import sys
import textwrap
import time
import typing as t
from configparser import ConfigParser
from fnmatch import fnmatch
from functools import lru_cache

import argcomplete  # type: ignore
import rich.console
import rich.progress
import rich.syntax
import rich.table
import subc
from rich.live import Live
from rich.progress import Progress
from rich.prompt import Confirm

import yo.util
from yo.api import AttachmentType
from yo.api import ImageLoad
from yo.api import InstanceProfile
from yo.api import OS_TO_USER
from yo.api import VolumeKind
from yo.api import YoCtx
from yo.api import YoImage
from yo.api import YoInstance
from yo.api import YoShape
from yo.api import YoVolume
from yo.api import YoVolumeAttachment
from yo.util import current_yo_version
from yo.util import fmt_allow_deny
from yo.util import latest_yo_version
from yo.util import shlex_join
from yo.util import standardize_name
from yo.util import strftime
from yo.util import YoConfig
from yo.util import YoExc

CONFIG_FILE = os.path.expanduser("~/.oci/yo.ini")
OCI_CONFIG_FILE = os.path.expanduser("~/.oci/config")
TASK_DIRECTORIES = [
    os.path.expanduser("~/.oci/yo-tasks"),
    # This should be installed with the package
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "data/yo-tasks"),
]

T = t.TypeVar("T")
V = t.TypeVar("V")

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

REPOSITORY_URL = "https://github.com/oracle/yo"
DOCUMENTATION_URL = "https://oracle.github.io/yo/"
INITIAL_CONFIG_LINK = REPOSITORY_URL

warned_about_SSH_timeout = False

PYVER = sys.version_info[:2]

COMMAND_GROUP_ORDER = [
    "Basic Commands",
    "Instance Management",
    "Instance Communication & Interaction",
    "Task Management Commands",
    "Volume Management Commands",
    "Informative Commands",
    "Diagnostic Commands",
]


class ParagraphFormatter(argparse.HelpFormatter):
    def _fill_text(self, text: str, width: int, indent: str) -> str:
        # Remove existing indentation and get paragraphs
        text = textwrap.dedent(text).strip()
        paragraphs = [p.replace("\n", " ").strip() for p in text.split("\n\n")]

        # Now indent and wrap each paragraph
        wrapped_pars = [
            textwrap.fill(textwrap.indent(p, indent), width) for p in paragraphs
        ]

        # And return the block of text
        return "\n\n".join(wrapped_pars)


def arg_choices(c: t.List[str]) -> t.Optional[t.List[str]]:
    if os.environ.get("SPHINX_BUILD") == "1":
        return None
    else:
        return c


@dataclasses.dataclass
class FullYoConfig:
    config: YoConfig
    """The main [yo] configuration section."""

    profiles: t.Dict[str, "InstanceProfile"]
    """Instance profiles from [instances.*] sections."""

    aliases: t.Dict[str, str]
    """Aliases configured in [aliases]"""


def check_configs() -> None:
    has_oci_config = os.path.isfile(OCI_CONFIG_FILE)
    has_yo_config = os.path.isfile(CONFIG_FILE)
    if has_oci_config and has_yo_config:
        return
    con = rich.console.Console()
    con.print("Welcome to yo! It looks like yo or OCI is not yet configured.\n")
    if not has_oci_config:
        con.print("OCI SDK Config is Missing\n", style="red")
        con.print('  Run "oci setup bootstrap" and follow the instructions!')
        con.print("  You probably want us-ashburn-1 for your region.")
        if "SSH_CONNECTION" in os.environ:
            con.print(
                "\n  [red]It looks like you're connected via SSH.[/] To make",
            )
            con.print(
                "  the bootstrap work properly, please reconnect using the SSH"
            )
            con.print(
                '  arguments "-L 8181:localhost:8181". This is necessary to'
            )
            con.print(
                "  complete the OCI authentication flow on your host computer."
            )
        con.print()
    if not has_yo_config:
        import shutil

        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        sample = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "data/sample.yo.ini"
        )
        shutil.copy(sample, CONFIG_FILE)
        con.print("[red]yo configuration file is missing\n")
        con.print("  I've gone ahead and copied the sample configuration to:")
        con.print(f"  {CONFIG_FILE}")
        con.print(
            "  [orange]Please edit it (see the configuration guide below for help)\n"
        )
    con.print(
        "For more details on initial configuration, please see the guide:"
    )
    con.print(f"[u]{INITIAL_CONFIG_LINK}[/u]\n")
    raise YoExc("Configuration incomplete")


def load_config(config_file: str = CONFIG_FILE) -> FullYoConfig:
    config = ConfigParser(
        # To allow profiles to properly clear the value set by a parent, allow
        # no value config sections, which will set the value to None.
        allow_no_value=True,
    )
    assert os.path.isfile(config_file)
    config.read(config_file)
    yo_config = YoConfig.from_config_section(config["yo"])

    aliases: t.Dict[str, str] = {}
    if "aliases" in config.sections():
        for key in config["aliases"]:
            aliases[key] = str(config["aliases"][key])

    instance_profiles: t.Dict[str, InstanceProfile] = {}
    expr = re.compile(r"^instances.")
    ip_secs = [
        expr.sub("", sec)
        for sec in config.sections()
        if sec.startswith("instances.")
    ]
    inheritance = {
        sec: config[f"instances.{sec}"].get("inherit") for sec in ip_secs
    }
    seen: t.Set[str] = set()
    topo_sort: t.List[str] = []

    for sec in ip_secs:
        visiting: t.List[str] = []
        curr: t.Optional[str] = sec
        while curr is not None and curr not in seen:
            # print(f"  TS: visit {sec}")
            if curr in visiting:
                raise YoExc("Circular dependency in instance profiles")
            visiting.append(curr)
            curr = inheritance.get(curr)
        topo_sort.extend(reversed(visiting))
        seen.update(visiting)

    # Load sections in topological sort order, so dependencies are satisfied.
    for sec in topo_sort:
        keys = {}
        parent = inheritance[sec]
        if parent:
            keys.update(dataclasses.asdict(instance_profiles[parent]))
            del config[f"instances.{sec}"]["inherit"]
        keys.update(config[f"instances.{sec}"])
        instance_profiles[sec] = InstanceProfile.from_dict(
            keys, f"instances.{sec}"
        )
        instance_profiles[sec].validate(sec)
    return FullYoConfig(yo_config, instance_profiles, aliases)


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


@dataclasses.dataclass
class YoTask:
    name: str
    path: str
    script: str
    dependencies: t.List[str]
    conflicts: t.List[str]

    @classmethod
    @lru_cache(maxsize=None)
    def load(cls, name: str) -> "YoTask":
        """
        Load a task by name and return it.

        This function is cached - it will only really search and load any given
        task name once: then it will return the same object thereafter.
        """
        for directory in TASK_DIRECTORIES:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                path = os.path.abspath(path)
                break
        else:
            raise YoExc(f"error: Script for task {name} not found")

        with open(path) as f:
            script = f.read()

        dependencies = []
        conflicts = []
        all_tasks = list_tasks()
        lines = script.split("\n")
        for i in range(len(lines)):
            line = lines[i].strip()
            if line.startswith("DEPENDS_ON"):
                dependencies.append(line.split(None, maxsplit=1)[1])
            elif line.startswith("CONFLICTS_WITH"):
                conflicts.append(line.split(None, maxsplit=1)[1])
            elif line.startswith("MAYBE_DEPENDS_ON"):
                task = line.split(None, maxsplit=1)[1]
                if task in all_tasks:
                    dependencies.append(task)
                    line = line.replace("MAYBE_DEPENDS_ON", "DEPENDS_ON")
                else:
                    line = line.replace(
                        "MAYBE_DEPENDS_ON", "# MAYBE_DEPENDS_ON"
                    )
                lines[i] = line
        return YoTask(name, path, "\n".join(lines), dependencies, conflicts)


@lru_cache(maxsize=1)
def list_tasks() -> t.List[str]:
    tasks = []
    for directory in TASK_DIRECTORIES:
        if os.path.isdir(directory):
            tasks.extend(os.listdir(directory))
    return sorted({s for s in tasks if s[-1] != "~"})


def get_safe_heredoc(text: str) -> str:
    while True:
        here = "".join(random.sample(string.ascii_letters, 32))
        if here not in text:
            return here


@lru_cache(maxsize=1)
def get_tasklib(task_dir_safe: str) -> str:
    tasklib = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "data/yo_tasklib.sh"
    )
    contents = open(tasklib).read()
    return contents.replace("$$TASK_DIR$$", task_dir_safe)


def _task_run(ctx: YoCtx, inst: YoInstance, task: YoTask) -> None:
    """
    Run a task on an instance. This doesn't check or load dependencies.
    """
    task_dir_safe = ctx.config.task_dir_safe
    ctx.con.log(
        f"Start task [blue]{task.name}[/blue] on instance [green]{inst.name}..."
    )
    ip = ctx.get_instance_ip(inst, True)
    user = ctx.get_ssh_user(inst)
    script_text = get_tasklib(task_dir_safe) + task.script
    commands = inspect.cleandoc(
        """
    task_dir={task_dir}
    name={name}
    dir="$task_dir/$name"
    if [ -f "$dir/status" ]; then
        mv "$dir/status" "$dir/../$name.status"
        rm -rf "$dir"
        mkdir -p "$dir"
        mv "$dir/../$name.status" "$dir/status.old"
    fi
    mkdir -p "$dir"
    cd "$dir"
    cat <<'{heredoc}' > ./script
    {script_text}
    {heredoc}
    if [ -f ./pid ]; then
        echo Task is already running!
        exit
    fi
    nohup sh -c 'bash -x ./script; echo $? >./status; rm ./pid' \
        >./output 2>&1 </dev/null &
    echo $! >./pid
    """
    )
    heredoc = get_safe_heredoc(script_text)
    commands = commands.format(
        heredoc=heredoc,
        script_text=script_text,
        task_dir=task_dir_safe,
        name=shlex.quote(task.name),
    )
    ssh_into(ip, user, ctx, extra_args=["-q"], cmds=[commands], quiet=True)


def run_all_tasks(ctx: YoCtx, inst: YoInstance, tasks: t.Iterable[str]) -> None:
    # Tasks can have dependencies. We need to be sure to load the full set of
    # dependencies in the list of tasks we're given. We also need to verify
    # there are no circular dependencies. And it's nice to launch them in order
    # that will satisfy their dependencies, but the "DEPENDS_ON" function should
    # successfully handle waiting until all depnedencies are completed anyway.

    # 0: not visited, 1: visiting, 2: finished visit
    name_to_visit: t.Dict[str, int] = collections.defaultdict(int)
    # output ordering
    ordered_tasks: t.List[YoTask] = []

    def visit(task_name: str) -> None:
        if name_to_visit[task_name] == 2:
            # already completed, skip
            return
        if name_to_visit[task_name] == 1:
            # currently visiting, not a DAG
            raise YoExc("Tasks express a circular dependency")

        name_to_visit[task_name] = 1
        task = YoTask.load(task_name)
        for dep_name in task.dependencies:
            visit(dep_name)
        name_to_visit[task_name] = 2
        ordered_tasks.append(task)

    for name in tasks:
        visit(name)

    # Now ordered_tasks contains the order in which we should launch them.
    # Verify that there are no conflicts
    all_task_names = {t.name for t in ordered_tasks}
    for task in ordered_tasks:
        for conflict in task.conflicts:
            if conflict in all_task_names:
                raise YoExc(f"Task {task} conflicts with {conflict}")

    # Do the thing!
    for task in ordered_tasks:
        _task_run(ctx, inst, task)


def task_get_status(
    ctx: YoCtx,
    inst: YoInstance,
) -> t.Mapping[str, t.Tuple[str, t.Union[int, str]]]:
    task_dir_safe = ctx.config.task_dir_safe
    # Take care to use the escaped task dir, and use the -print0 and xargs -0
    # arguments for maximum safety: filenames can be weird.
    command = (
        f"find {task_dir_safe} "
        "\\( -name pid -or -name status -or -name wait \\) -and -print0 "
        '| xargs -0 grep -H ".*" | sort'
    )
    ip = ctx.get_instance_ip(inst, True)
    user = ctx.get_ssh_user(inst)
    res = ssh_into(
        ip,
        user,
        ctx,
        extra_args=["-q"],
        cmds=[command],
        capture_output=True,
        quiet=True,
    )
    expr = re.compile(r"^.*/([^/]*)/(pid|status|wait):(.*)$")
    task_to_files: t.Dict[
        str, t.List[t.Tuple[str, str]]
    ] = collections.defaultdict(list)
    output = res.stdout.decode("utf-8").strip()
    if not output:
        return {}
    for line in output.split("\n"):
        match = expr.match(line)
        if not match:
            print(line)
            print(res.stdout)
            raise YoExc(
                f"bad task status data, examine {ctx.config.task_dir} on the host"
            )
        task, kind, stat = match.groups()
        task_to_files[task].append((kind, stat))

    task_to_status: t.Dict[str, t.Tuple[str, t.Union[str, int]]] = {}
    for task, stat_list in task_to_files.items():
        stat_list.sort()  # alphabetical ensures that "wait" is at the end
        if len(stat_list) == 1:
            kind, statstr = stat_list[0]
            stat = int(statstr)
            if kind == "pid":
                task_to_status[task] = ("RUNNING", stat)
            elif stat == 0:
                task_to_status[task] = ("SUCCESS", 0)
            else:
                task_to_status[task] = ("FAIL", 0)
        elif (
            len(stat_list) == 2
            and stat_list[0][0] == "pid"
            and stat_list[1][0] == "wait"
        ):
            task_to_status[task] = ("WAITING", stat_list[1][1])
        else:
            task_to_status[task] = ("UNKNOWN", 0)
    return task_to_status


def task_status_to_table(
    statuses: t.Mapping[str, t.Tuple[str, t.Union[int, str]]]
) -> rich.table.Table:
    t = rich.table.Table(title="Task Status")
    t.add_column("Task")
    t.add_column("Status")
    for task, (status, code) in statuses.items():
        if status == "RUNNING":
            status = f"[yellow]RUNNING[/yellow] (pid={code})"
        elif status == "FAIL":
            status = f"[red]FAILED[/red] (code={code})"
        elif status == "WAITING":
            status = f"[green]WAITING[/green] (on={code})"
        elif status == "UNKNOWN":
            status = "[red]UNKNOWN[/red]"
        else:
            status = f"[green]SUCCESS[/green] (code={code})"
        t.add_row(task, status)
    return t


def task_join(
    ctx: YoCtx,
    inst: YoInstance,
    wait_task: t.Optional[str] = None,
) -> t.Mapping[str, t.Tuple[str, t.Union[str, int]]]:
    with Live(console=ctx.con) as live:
        task_previous_status: t.Dict[str, str] = {}
        while True:
            status_dict = task_get_status(ctx, inst)
            live.update(task_status_to_table(status_dict))
            any_running = False
            for task, (status, _) in status_dict.items():
                prev_status = task_previous_status.get(task)
                task_previous_status[task] = status
                if not prev_status:
                    live.console.log(f"{task}: starting in status {status}")
                elif prev_status != status:
                    live.console.log(
                        f"{task}: changing status {prev_status} -> {status}"
                    )
                if status in ("RUNNING", "WAITING"):
                    any_running = True

            # If we're waiting for no particular task, then we have to wait
            # until all are completed. Otherwise, we wait until just the
            # specific wait_task is completed.
            can_terminate = (wait_task is None and not any_running) or (
                wait_task is not None
                and status_dict[wait_task][0]
                not in (
                    "RUNNING",
                    "WAITING",
                )
            )
            if can_terminate:
                break
            time.sleep(1)
    return status_dict


class YoCmd(subc.Command):
    c: YoCtx
    es: contextlib.ExitStack
    rootname = "yo"
    help_formatter_class = ParagraphFormatter  # type: ignore

    @classmethod
    def setup_config(cls) -> t.Tuple[YoCtx, t.Dict[str, str]]:
        check_configs()
        fc = load_config()
        cls.c = YoCtx(fc.config, fc.profiles)
        return cls.c, fc.aliases

    def base_run(self, args: argparse.Namespace) -> None:
        self.args = args
        self.es = contextlib.ExitStack()
        with self.es:
            self.run()

    def add_with_completer(
        self,
        parser: t.Union[
            argparse.ArgumentParser, argparse._MutuallyExclusiveGroup
        ],
        completer: t.Callable[[], t.List[str]],
        *args: t.Any,
        **kwargs: t.Any,
    ) -> argparse.Action:
        act = parser.add_argument(*args, **kwargs)
        act.completer = completer  # type: ignore
        return act

    def complete_instance(self, **kwargs: t.Any) -> t.List[str]:
        instances = self.c.list_instances_cached()
        names = []
        states_allowlist: t.List[str] = getattr(self, "states_allowlist", [])
        states_denylist: t.List[str] = getattr(self, "states_denylits", [])
        for inst in instances:
            if states_allowlist and inst.state not in states_allowlist:
                continue
            if inst.state in states_denylist:
                continue
            names.append(inst.name)
            if inst.name.startswith(self.c.config.my_username + "-"):
                names.append(inst.name[len(self.c.config.my_username) + 1 :])
        return names

    def complete_shape(self, **kwargs: t.Any) -> t.List[str]:
        return [s.name for s in self.c.list_shapes()]

    def complete_os(self, **kwargs: t.Any) -> t.List[str]:
        images = self.c.list_official_images()
        return sorted(set(f"{i.os}:{i.os_version}" for i in images))

    def complete_image(self, **kwargs: t.Any) -> t.List[str]:
        images = self.c.list_all_images()
        return sorted(set(i.name for i in images))

    def complete_saved(self, **kwargs: t.Any) -> t.List[str]:
        names = []
        for vol in self.c.list_volumes():
            if vol.saved_instance_metadata:
                names.append(vol.saved_instance_metadata.name)
        return names

    def complete_volume(self, **kwargs: t.Any) -> t.List[str]:
        volumes = self.c.list_volumes(False)
        names = []
        for vol in volumes:
            names.append(vol.name)
            if vol.name.startswith(self.c.config.my_username + "-"):
                names.append(vol.name[len(self.c.config.my_username) + 1 :])
            if vol.name != vol.alt_name:
                names.append(vol.alt_name)
                if vol.alt_name.startswith(self.c.config.my_username + "-"):
                    names.append(
                        vol.alt_name[len(self.c.config.my_username) + 1 :]
                    )
        return names


def send_notification(ctx: YoCtx, msg: str) -> None:
    if ctx.config.notify_prog:
        args = [
            a.format(message=msg) for a in shlex.split(ctx.config.notify_prog)
        ]
        subprocess.run(args)


class ListCmd(YoCmd):
    name = "list"
    group = "Basic Commands"
    help = "List your OCI instances."
    description = """
    List your OCI instances.

    Yo caches some data to speed up operations, but when you run "yo list", it
    will always ensure you get the freshest data. You can disable this behavior
    if you want, which will show you stale data, but it will be fast.

    By default, Yo also tries to only show instances that belong to you (though,
    please see the documentation for the config "yo.resource_filtering"). You
    can use the "--all" argument to see all of the instances in your
    compartment, regardless of whether Yo believes you created them. Please keep
    in mind that you won't be able to manage those instances (e.g. yo ssh, yo
    terminate, etc) unless you change your "yo.resource_filtering" configuration.
    """

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--cached",
            "-c",
            action="store_true",
            help="avoid loading and calling OCI if possible (list may be"
            "out of date)",
        )
        parser.add_argument(
            "--ip",
            "-i",
            action="store_true",
            help="include IP addresses (this may require calling the API)",
        )
        parser.add_argument(
            "--ad",
            action="store_true",
            help="display the availability domain column",
        )
        parser.add_argument(
            "--all",
            "-a",
            action="store_true",
            help="display all instances in the compartment (not just yours)",
        )

    def run(self) -> None:
        verbose = not self.c.config.silence_automatic_tag_warning
        # We do not cache other people's instances. If --all is provided, we
        # must not call list_instances_cached()
        if self.args.all:
            self.args.cached = False
        if self.args.cached:
            instances = self.c.list_instances_cached()
        else:
            self.es.enter_context(self.c.maybe_check_for_updates())
            instances = self.c.list_instances(
                verbose=verbose, show_all=self.args.all
            )

        instances = [
            x for x in instances if x.state not in ("TERMINATED", "TERMINATING")
        ]
        instances.sort(key=lambda i: i.time_created)

        # It's more efficient to bulk lookup the IPs. This will cache them so
        # that below, we don't do individual calls.
        if self.args.ip:
            self.c.get_all_instance_ips(instances)

        table = rich.table.Table()
        table.add_column("Name")
        table.add_column("Shape")
        table.add_column("Mem")
        table.add_column("CPU")
        table.add_column("State")
        if self.args.ad:
            table.add_column("AD")
        table.add_column("Created")
        if self.args.ip:
            table.add_column("IP")
        for instance in instances:
            name = instance.name
            if instance.termination_protected:
                name = ":lock:" + name
            values = [
                name,
                instance.shape,
                str(int(instance.memory_gb)),
                str(int(instance.ocpu)),
                instance.state,
            ]
            if self.args.ad:
                values.append(instance.ad)
            values += [
                strftime(instance.time_created),
            ]
            if self.args.ip:
                values.append(self.c.get_instance_ip(instance, quiet=True))
            table.add_row(*values)

        for volume in self.c.list_volumes():
            md = volume.saved_instance_metadata
            if not md:
                continue
            values = [
                f":warning: {md.name}",
                md.shape,
                str(md.memory_gb),
                str(md.ocpu),
                "[red]SAVED[/red]",
            ]
            if self.args.ad:
                values.append(volume.ad)
            values.append("---")
            if self.args.ip:
                values.append("---")
            table.add_row(*values)
        self.c.con.print(table)


class SingleInstanceCommand(YoCmd):
    positional_name: bool = True
    states_allowlist: t.Collection[str] = ("RUNNING",)
    states_denylist: t.Collection[str] = ()
    username: t.Optional[str]

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_instance,
            "--name",
            "-n",
            type=str,
            help="Name of the instance to filter by",
        )
        parser.add_argument(
            "--exact-name",
            "-E",
            action="store_true",
            default=None,
            help="Do not standardize the name by prefixing it with your "
            "system username if necessary.",
        )
        parser.add_argument(
            "--no-exact-name",
            action="store_false",
            dest="exact_name",
            default=None,
            help="Standardize the name by prefixing it with your system "
            "username (this is the default, but can be used to override "
            "your Yo configuration file)",
        )
        if self.positional_name:
            self.add_with_completer(
                parser,
                self.complete_instance,
                "name_pos",
                type=str,
                nargs="?",
                help="Name of the instance to filter by",
            )

    def run_for_instance(self, instance: YoInstance) -> None:
        raise NotImplementedError("Implement me!")

    def get_instance_name_arg(self) -> t.Optional[str]:
        """
        This is for subclasses to return a string name.

        Maybe your subclass has another way to specify a name, e.g. for SCP, use
        name:destination like the real scp command would. This function allows
        you to implement it and get it used.
        """
        return None

    def arg_name(self) -> t.Optional[str]:
        """
        Return the string name of the instance to act on.

        There may be several ways to get the name of an instance (e.g. the -n
        argument, the positional_name, or some other way defined by the
        command). This tries all of them in order and gives the first one.
        """
        self.username = None
        if self.args.name is not None:
            name: t.Optional[str] = self.args.name
        elif self.positional_name and self.args.name_pos is not None:
            name = self.args.name_pos
        else:
            name = self.get_instance_name_arg()
        if name and "@" in name:
            self.username, name = name.split("@")
        return name

    def run(self) -> None:
        name = self.arg_name()
        if name:
            inst = self.c.get_instance_by_name(
                name,
                self.states_allowlist,
                self.states_denylist,
                exact_name=self.args.exact_name,
            )
        else:
            inst = self.c.get_only_instance(
                self.states_allowlist, self.states_denylist
            )
        self.run_for_instance(inst)


class MultiInstanceCommand(YoCmd):
    action_message = "execute on"
    needs_confirmation = True
    states_allowlist = ()
    states_denylist = ("TERMINATED",)

    instance_count = 0

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        am = self.action_message
        cap_am = am.capitalize()
        parser.add_argument(
            "--all",
            action="store_true",
            help=f"{cap_am} all of my instances",
        )
        parser.add_argument(
            "--exact-name",
            "-E",
            action="store_true",
            default=None,
            help="Do not standardize the name by prefixing it with your "
            "system username if necessary.",
        )
        parser.add_argument(
            "--no-exact-name",
            action="store_false",
            dest="exact_name",
            default=None,
            help="Standardize the name by prefixing it with your system "
            "username (this is the default, but can be used to override "
            "your Yo configuration file)",
        )
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Do not prompt for confirmation, assume yes",
        )
        self.add_with_completer(
            parser,
            self.complete_instance,
            "instances",
            type=str,
            nargs="*",
            default=[],
            help=f"Instance names to {am}",
        )

    def validate_args(self, args: argparse.Namespace) -> None:
        # This function can be overridden as necessary to add validation
        # logic for command line args. It is left blank so that overriding
        # is not required.
        pass

    def run_for_instance(
        self,
        instance: YoInstance,
        progress: Progress,
    ) -> None:
        raise NotImplementedError(
            "Implement me if you don't implement run_for_all()"
        )

    def post_for_instance(self, instance: YoInstance) -> None:
        """
        Called by run_for_all() once each instance has been processed. This can
        be used to implement post-processing, like waiting.
        """

    def confirm(self, msg: str) -> bool:
        confirm = (
            not self.needs_confirmation or self.args.yes or Confirm.ask(msg)
        )
        if confirm:
            if self.needs_confirmation:
                if self.args.yes:
                    self.c.con.print(
                        "[red]Skipping confirmation because of --yes"
                    )
                else:
                    self.c.con.print("[bold red]Confirmed.")
        else:
            self.c.con.print("[green]Ok, canceling![/green]")
        return confirm

    def run_for_all(self, instances: t.List[YoInstance]) -> None:
        if not instances:
            self.c.con.print("[red]No instances matching conditions:")
            self.c.con.print(
                " state: {}".format(
                    fmt_allow_deny(self.states_allowlist, self.states_denylist)
                )
            )
            names = [
                standardize_name(n, self.args.exact_name, self.c.config)
                for n in self.args.instances
            ]
            if names:
                self.c.con.print(" name: {}".format(", ".join(names)))
            else:
                self.c.con.print(" name: any")
            return
        instance_list_str = "\n".join(f"- {x.name}" for x in instances)
        self.c.con.print(
            f"[bold red]About to {self.action_message} [underline]"
            f"{len(instances)}"
            f"[/underline] instances:\n"
            f"{instance_list_str}.[/bold red]"
        )
        if not self.confirm("Is this ok?"):
            return

        progress = Progress(
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TaskProgressColumn(),
            rich.progress.SpinnerColumn(),
            rich.progress.TimeElapsedColumn(),
            console=self.c.con,
        )
        with progress:
            for instance in progress.track(instances):
                self.run_for_instance(instance, progress)
        for instance in instances:
            self.post_for_instance(instance)

    def run(self) -> None:
        if self.args.instances and self.args.all:
            raise YoExc("You cannot specify both --all and instance names")
        elif not self.args.instances and not self.args.all:
            raise YoExc(
                "You need to specify either --all, or a list of instances"
            )
        self.validate_args(self.args)

        names = set(
            standardize_name(name, self.args.exact_name, self.c.config)
            for name in self.args.instances
        )

        to_run = self.c.get_matching_instances(
            names,
            self.states_allowlist,
            self.states_denylist,
            refresh=True,
        )
        self.instance_count = len(to_run)
        self.run_for_all(to_run)


class SshCmd(SingleInstanceCommand):
    name = "ssh"
    group = "Basic Commands"
    description = "SSH into an instance."

    states_allowlist: t.Collection[str] = (
        "RUNNING",
        "PROVISIONING",
        "STARTING",
    )
    states_denylist: t.Collection[str] = ()

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--wait",
            "-w",
            action="store_true",
            help="Wait for SSH access",
        )
        parser.add_argument(
            "--agent",
            "-A",
            action="store_true",
            help="Forward SSH agent",
        )
        parser.add_argument(
            "--ssh-args",
            default="",
            help="Arguments to pass to ssh",
        )
        parser.add_argument(
            "--start",
            "-s",
            action="store_true",
            help=(
                "Start the instance if not already started and then ssh "
                "(implies --wait)"
            ),
        )
        parser.add_argument(
            "--quiet",
            "-q",
            action="store_true",
            help=("Reduce the informative output"),
        )
        parser.add_argument(
            "cmds",
            nargs="*",
            default=None,
            help="Execute the listed commands rather than a login shell",
        )

    def get_cmds(self) -> t.List[str]:
        # Corner case: say that you run "yo ssh -n instance -- command"
        # Unfortunately, the "name_pos" argument will absorb the "command"
        # string (and ignore it), and we won't execute that command on the
        # instance. Worse, any further arguments would be interpreted as a
        # command to execute on the instance.
        # To rectify this, detect a situation where both "--name" and "name_pos"
        # are provided, and insert name_pos as the first argument to the
        # command.
        orig_cmds = self.args.cmds or []
        if self.args.name and self.args.name_pos:
            orig_cmds.insert(0, self.args.name_pos)
        return orig_cmds

    def run_for_instance(self, inst: YoInstance) -> None:
        if not self.args.quiet:
            self.c.con.log(f"Connecting to instance [blue]{inst.name}[/blue]")
        if self.args.start and inst.state == "STOPPED":
            self.args.wait = True
            self.c.instance_action(inst.id, "START")
        elif inst.state == "STOPPED":
            # This should now be impossible, kept around for paranoia
            raise YoExc("Instance is STOPPED, did you mean to use --start?")
        if self.args.wait and inst.state != "RUNNING":
            self.c.wait_instance_state(
                inst.id,
                "RUNNING",
                max_interval_seconds=1,
                max_wait_seconds=600,
            )
        ip = self.c.get_instance_ip(inst, quiet=self.args.quiet)
        user = self.username
        if not user:
            user = self.c.get_ssh_user(inst)
        extra_args = []
        if self.args.agent:
            extra_args.append("-A")
        if self.args.wait:
            wait_for_ssh_access(ip, user, self.c)
            send_notification(
                self.c, f"Instance {inst.name} is connected via SSH!"
            )
        extra_args += shlex.split(self.args.ssh_args)
        ssh_into(
            ip,
            user,
            ctx=self.c,
            extra_args=extra_args,
            cmds=self.get_cmds(),
            quiet=self.args.quiet,
        )

    def run(self) -> None:
        if self.args.start:
            self.states_allowlist = tuple(self.states_allowlist) + ("STOPPING",)
        super().run()


class ScpCmd(SingleInstanceCommand):
    name = "scp"
    group = "Instance Communication & Interaction"
    description = "Copy files to/from an instance using the scp command"
    positional_name = False

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        self.add_with_completer(
            parser,
            argcomplete.FilesCompleter,
            "scp_args",
            nargs="*",
            help=(
                "Arguments to pass to scp (use -- to protect, :"
                "gets replaced with destination host)"
            ),
        )

    def get_instance_name_arg(self) -> t.Optional[str]:
        for arg in self.args.scp_args:
            if ":" in arg:
                # It's unclear why mypy doesn't understand this...
                return t.cast(str, arg.split(":", 1)[0])
        return None

    def run_for_instance(self, inst: YoInstance) -> None:
        name = self.arg_name()  # need to load this again
        ip = self.c.get_instance_ip(inst)
        user = self.username
        if not user:
            user = self.c.get_ssh_user(inst)
        self.c.con.log(
            f"Copying to instance [blue]{inst.name}[/blue] "
            f"([green]{user}[/green]@[blue]{ip}[/blue])"
        )
        repl = re.compile("^((.*@)?{})?:".format(name))
        replaced = [
            repl.sub(f"{user}@{ip}:", arg) for arg in self.args.scp_args
        ]
        scp_args = ["scp"] + ssh_args(self.c, False)
        subprocess.run(scp_args + replaced)


class RemoteDesktopCommand(SingleInstanceCommand):
    @property
    def PORT(self) -> int:
        raise NotImplementedError("Define the PORT")

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--no-tunnel",
            "-T",
            action="store_false",
            dest="tunnel",
            help="Don't tunnel the connection over SSH",
        )

    @contextlib.contextmanager
    def maybe_tunnel(self, inst: YoInstance) -> t.Iterator[str]:
        """
        Handle SSH tunneling if configured. Return the host to connect.
        """
        ip = self.c.get_instance_ip(inst)
        if self.args.tunnel:
            user = self.username
            if not user:
                user = self.c.get_ssh_user(inst)
            self.c.con.log(
                f"SSH Tunnel to [blue]{inst.name}[/blue] "
                f"([green]{user}[/green]@[blue]{ip}[/blue])"
            )
            cmd = ssh_cmd(
                self.c,
                f"{user}@{ip}",
                [f"-NL{self.PORT}:localhost:{self.PORT}"],
            )
            ssh_tunnel = subprocess.Popen(cmd)
            try:
                yield "localhost"
            finally:
                ssh_tunnel.kill()
        else:
            yield ip


class VncCmd(RemoteDesktopCommand):
    name = "vnc"
    group = "Instance Communication & Interaction"
    description = "Connect to instance remote desktop using VNC."
    PORT = 5901

    def run_for_instance(self, inst: YoInstance) -> None:
        with self.maybe_tunnel(inst) as host:
            vnc = subprocess.Popen(
                self.c.config.vnc_prog.format(host=host, port=self.PORT),
                shell=True,
            )
            self.c.con.log("Launched your configured VNC program!")
            self.c.con.log("Exit it to terminate the SSH tunnel.")
            vnc.wait()


class RdpCmd(RemoteDesktopCommand):
    name = "rdp"
    group = "Instance Communication & Interaction"
    description = "Connect to instance remote desktop using RDP."
    PORT = 3389

    def run_for_instance(self, inst: YoInstance) -> None:
        rdp_prog = self.c.config.rdp_prog
        if rdp_prog is None:
            raise YoExc("You must configure rdp_prog first")
        init_user, pw = self.c.get_windows_initial_creds(inst)
        if init_user is not None:
            self.c.con.print(
                "This is a Windows instance! Here are the initial credentials:"
            )
            self.c.con.print(f"[bold]Username:[bold] {init_user}")
            self.c.con.print(f"[bold]Password:[bold] {pw}")
            if self.args.tunnel:
                self.c.con.print(
                    "warning: SSH tunnel enabled, this probably won't work on "
                    "Windows"
                )
        else:
            self.c.con.print("This is not a Windows instance...")
            self.c.con.print(
                "If you have not configured a password, you'll need to do that."
            )
            self.c.con.print("Try 'sudo passwd opc' on the instance first.")
            self.c.con.print(
                "Disregard this message if you already have a password."
            )
        with self.maybe_tunnel(inst) as host:
            rdp_string = rdp_prog.format(host=host, port=self.PORT)
            rdp = subprocess.Popen(rdp_string, shell=True)
            rdp.wait()


class RsyncCmd(SingleInstanceCommand):
    name = "rsync"
    group = "Instance Communication & Interaction"
    description = "Synchronize files using the rsync command."
    positional_name = False

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--raw",
            action="store_true",
            help=(
                "Do not use the rsync_args stored in the config, only "
                "use the ones provided on the command line."
            ),
        )
        self.add_with_completer(
            parser,
            argcomplete.FilesCompleter,
            "rsync_args",
            nargs="*",
            help=(
                "Arguments to pass to rsync (use -- to protect, :"
                "gets replaced with destination host)"
            ),
        )

    def run_for_instance(self, inst: YoInstance) -> None:
        ip = self.c.get_instance_ip(inst)
        user = self.username
        if not user:
            user = self.c.get_ssh_user(inst)
        rsync_args = ["rsync"]
        if self.c.config.rsync_args and not self.args.raw:
            rsync_args.extend(shlex.split(self.c.config.rsync_args))
        self.c.con.log(
            f"Rsync with instance [blue]{inst.name}[/blue] "
            f"([green]{user}[/green]@[blue]{ip}[/blue])"
        )
        repl = re.compile(r"^:")
        replaced = [
            repl.sub(f"{user}@{ip}:", arg) for arg in self.args.rsync_args
        ]
        subprocess.run(rsync_args + replaced)


class ConsoleCmd(SingleInstanceCommand):
    name = "console"
    group = "Instance Communication & Interaction"
    description = "View an instance's serial console using an SSH connection"

    states_allowlist = ()
    states_denylist = ("STOPPED", "TERMINATED")

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="refresh the local cache of serial consoles for this instance",
        )

    def run_for_instance(self, inst: YoInstance) -> None:
        dn = inst.name
        self.c.con.log(f"Connecting to instance [blue]{dn}[/blue] console")
        conn = self.c.get_or_create_console(inst.id, refresh=self.args.refresh)
        args = shlex.split(conn.connection_string)
        identity = self.c.config.ssh_private_key

        processed_args = []
        target = None

        for val in args:
            if val == "ssh":
                continue  # strip the ssh command from the args
            elif identity is not None and "ProxyCommand" in val:
                insert_args = f" -i {identity}"
                for arg in SSH_CONSOLE_OPTIONS:
                    insert_args += " " + shlex.quote(arg)
                ssh_ix = val.index("ssh") + 3
                val = val[:ssh_ix] + insert_args + val[ssh_ix:]
                processed_args.append(val)
            elif inst.id in val:
                target = val  # identify the target of the SSH
            else:
                processed_args.append(val)  # pass all other args

        if target is None:
            self.c.con.log(args)
            raise YoExc(
                "Could not understand OCI's console SSH string. This is a "
                "yo bug, please report it on Github."
            )

        cmd = ssh_cmd(self.c, target, SSH_CONSOLE_OPTIONS, processed_args)

        self.c.con.log("About to execute:")
        self.c.con.log(cmd)
        self.c.con.log(
            "[bold red]This connection will stay open for a long time.\n"
            "To exit a running SSH connection, use the escape sequence: "
            "<Return>~.\n"
        )
        total_time = time.time()
        proc = subprocess.run(cmd)
        total_time = time.time() - total_time
        if proc.returncode != 0 and total_time < SSH_MINIMUM_TIME:
            self.c.con.log(
                "\n[bold red]Note:[/bold red] It looks like your SSH session "
                "failed quite quickly.\n"
                "If the connection failed, yo's cache may be out of date. "
                "Use [blue]yo console --refresh[/blue] to address this.\n"
                "If that doesn't help, then this console may have been "
                "created on a different computer and have the wrong SSH key "
                "associated with it.\n"
                "In that case, you'll need to delete it in the console, and "
                "then rerun [blue]yo console --refresh[/blue]"
            )


class WaitCmd(SingleInstanceCommand):
    name = "wait"
    group = "Instance Management"
    description = "Wait for an instance to enter a state."

    states_allowlist = ()
    states_denylist = ("TERMINATED",)

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--state",
            "-s",
            type=str,
            default="RUNNING",
            help="State to wait for the instance to enter",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=600,
            help="How long to wait (in seconds)",
        )

    def run_for_instance(self, instance: YoInstance) -> None:
        inst = self.c.wait_instance_state(
            instance.id,
            self.args.state,
            max_interval_seconds=1,
            max_wait_seconds=self.args.timeout,
        )
        send_notification(
            self.c, f"Instance {inst.name} is in state {inst.state}"
        )


class TaskRunCmd(SingleInstanceCommand):
    name = "task run"
    group = "Task Management Commands"
    description = "Run a long-running task script on an instance."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "task",
            choices=arg_choices(list_tasks()),
            help="name of the task to execute",
        )
        parser.add_argument(
            "-w",
            "--wait",
            action="store_true",
            help="should we wait until the task is finished?",
        )

    def run_for_instance(self, inst: YoInstance) -> None:
        run_all_tasks(self.c, inst, [self.args.task])
        if self.args.wait:
            task_join(self.c, inst, wait_task=self.args.task)
            send_notification(
                self.c,
                f"Task {self.args.task} complete on instance {inst.name}",
            )


class CopyIdCmd(SingleInstanceCommand):
    name = "copy-id"
    group = "Instance Communication & Interaction"
    description = "Copy an SSH public key onto an instance using ssh-copy-id."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "-i",
            "--identity-file",
            type=str,
            required=False,
            help="Specify path to the public key file",
        )

    def run_for_instance(self, instance: YoInstance) -> None:
        # Firstly, we need to extract instance name and public key file path from command-line arguments
        instance_name = instance.name
        public_key_file_path = self.args.identity_file
        ip = self.c.get_instance_ip(instance)
        user = self.c.get_ssh_user(instance)

        options = SSH_OPTIONS[:]
        if public_key_file_path:
            options += ["-i", public_key_file_path]

        ssh_copy_id_cmd = ["ssh-copy-id"] + options + [f"{user}@{ip}"]

        # Execution starts here
        try:
            subprocess.run(ssh_copy_id_cmd, check=True)
            self.c.con.print(
                f"SSH public key copied to '{instance_name}' successfully."
            )
        except subprocess.CalledProcessError:
            self.c.con.print(
                f"Error copying SSH public key to '{instance_name}'!!"
            )
            sys.exit(
                1
            )  # Exit the program with a non-zero status code to indicate an error


class TaskStatusCmd(SingleInstanceCommand):
    name = "task status"
    group = "Task Management Commands"
    description = "Report the status of all tasks on an instance."

    def run_for_instance(self, inst: YoInstance) -> None:
        statuses = task_get_status(self.c, inst)
        self.c.con.print(task_status_to_table(statuses))


class TaskWaitCmd(SingleInstanceCommand):
    name = "task wait"
    group = "Task Management Commands"
    description = "Wait for a task to complete on an instance."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "task",
            choices=arg_choices(list_tasks()),
            help="name of the task to execute",
        )

    def run_for_instance(self, inst: YoInstance) -> None:
        task_join(self.c, inst, wait_task=self.args.task)
        send_notification(
            self.c, f"Task {self.args.task} complete on instance {inst.name}"
        )


class TaskJoinCmd(SingleInstanceCommand):
    name = "task join"
    group = "Task Management Commands"
    description = "Wait for all tasks on a given instance to complete."

    def run_for_instance(self, inst: YoInstance) -> None:
        task_join(self.c, inst)
        send_notification(self.c, f"All tasks complete on instance {inst.name}")


class TaskInfo(YoCmd):
    name = "task info"
    group = "Task Management Commands"
    description = "Show the basic information and script contents for a task."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "task",
            choices=arg_choices(list_tasks()),
            help="name of task to give info on",
        )

    def run(self) -> None:
        task = YoTask.load(self.args.task)
        self.c.con.print(f"File: {task.path}")
        self.c.con.print(f"Dependencies: {', '.join(task.dependencies)}")
        self.c.con.print(f"Conflicts: {', '.join(task.conflicts)}")
        self.c.con.print("\nScript:")
        s = rich.syntax.Syntax(task.script, "bash", theme="ansi_light")
        self.c.con.print(s)


class TaskList(YoCmd):
    name = "task list"
    group = "Task Management Commands"
    description = "List every task and its basic metadata"

    def run(self) -> None:
        t = rich.table.Table()
        t.add_column("Name")
        t.add_column("D/C")
        t.add_column("Path")
        for task_name in list_tasks():
            task = YoTask.load(task_name)
            dc = ""
            if task.dependencies:
                dc += "Depends: " + ", ".join(task.dependencies) + "\n"
            if task.conflicts:
                dc += "Conflicts: " + ", ".join(task.conflicts) + "\n"
            t.add_row(task_name, dc.strip(), task.path)
        self.c.con.print(t)


class IpCmd(YoCmd):
    name = "ip"
    group = "Instance Communication & Interaction"
    help = "Print the IP address for one or more instances."
    description = """
    Print the IP address for one or more instances.

    Yo tries to avoid making you remember an instance IP. For example, you can
    connect via SSH using "yo ssh". However, in some cases you may need to get
    the IP address still.
    """

    states_allowlist = ()
    states_denylist = ("TERMINATED",)

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--exact-name",
            "-E",
            action="store_true",
            default=None,
            help="Do not standardize the name by prefixing it with your "
            "system useranme if necessary.",
        )
        parser.add_argument(
            "--no-exact-name",
            action="store_false",
            dest="exact_name",
            default=None,
            help="Standardize the name by prefixing it with your system "
            "username (this is the default, but can be used to override "
            "your Yo configuration file)",
        )
        self.add_with_completer(
            parser,
            self.complete_instance,
            "instances",
            type=str,
            default=[],
            nargs="*",
            help="Instance names to fetch IP for (if empty, fetch all)",
        )

    def run(self) -> None:
        names = set(
            standardize_name(name, self.args.exact_name, self.c.config)
            for name in self.args.instances
        )
        instances = self.c.get_matching_instances(
            names, self.states_allowlist, self.states_denylist
        )
        # Use this to fetch all the IP addresses we don't already know.
        # Doing it in bulk is more efficient than querying for each instance
        # individually.
        self.c.get_all_instance_ips(instances)
        table = rich.table.Table()
        table.add_column("Name")
        table.add_column("IP")
        for instance in instances:
            table.add_row(
                instance.name,
                self.c.get_instance_ip(instance, True),
            )
        self.c.con.print(table)


class ImagesCmd(YoCmd):
    name = "images"
    group = "Informative Commands"
    help = "List images available to use for launching an instance."
    description = """
    List images available to use for launching an instance.

    This lists all official images as well as custom images (created by a user
    in your tenancy). Yo searches for custom images in the compartments
    indicated by configuration "yo.instance_compartment_id" (that is, the
    compartment you create instances within) as well as any value from
    "yo.image_compartment_ids".

    Custom images will have a "Creator" field, while official images will have
    this field blank. For official images, there are typically more than one
    image for a particular "OS" and "version" combination: images get updated
    with the latest packages regularly. It's easiest for you to simply specify
    your desired OS and version in yo launch (or your instance profile) rather
    than searching for an image name here.
    """

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_os,
            "os",
            type=str,
            nargs="?",
            default=None,
            help="Operating system and version, separated by colon (:)",
        )
        parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Print detailed image information",
        )

    def run(self) -> None:
        images = self.c.list_all_images()
        if self.args.os:
            os, ver = self.args.os.split(":", 1)
            images = list(
                filter(lambda x: x.os == os and x.os_version == ver, images)
            )
        images.sort(key=lambda i: i.name, reverse=True)
        if self.args.verbose:
            self.c.con.print(images)
        else:
            if not images:
                raise YoExc("No matching images...")
            table = rich.table.Table()
            table.add_column("Name")
            table.add_column("OS")
            table.add_column("OS Ver.")
            table.add_column("Creator")
            for img in images:
                table.add_row(
                    img.display_name, img.os, img.os_version, img.created_by
                )
            self.c.con.print(table)
            if self.args.os:
                image = images[0]
                dn = image.display_name
                self.c.con.print(f"Would use image [blue]{dn}[/blue]")


class CompatCmd(YoCmd):
    name = "compat"
    group = "Informative Commands"
    help = "Show a compatibility matrix of images and shapes."
    description = """
    Show a compatibility matrix of images and shapes.

    Not all images are compatible with all shapes. In fact, the relationship can
    be quite complex. This command exists mostly to satisfy curiosity. It
    formats a quite large matrix of official images and shapes, where an "X" is
    marked if the shape for that row is compatible with the image of that
    column.

    When you select OS and version, Yo will automatically select the image
    version compatible with your shape, so you should never need to know these
    details.
    """

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--shape",
            "-S",
            default="*",
            help="shape name or fnmatch(3) pattern: filters shapes in table",
        )
        parser.add_argument(
            "--os",
            default="*",
            help="OS name or fnmatch(3) pattern: filters OS in table",
        )
        parser.add_argument(
            "--image",
            default="*",
            help="image name or fnmatch(3) pattern to filter by image name"
            " (only used when --image-names is specified)",
        )
        parser.add_argument(
            "--image-names",
            action="store_true",
            help="OS name or fnmatch(3) pattern: filters OS in table",
        )
        parser.add_argument(
            "--width",
            type=int,
            default=24,
            help="Width of column for shape names",
        )

    def run(self) -> None:
        images = self.c.list_official_images()
        if self.args.image_names:
            images = [i for i in images if fnmatch(i.name, self.args.image)]
        else:
            images = [
                i
                for i in images
                if fnmatch(f"{i.os}:{i.os_version}", self.args.os)
            ]
        images.sort(key=lambda i: i.name)

        shapes = self.c.list_shapes()
        shapes = [s for s in shapes if fnmatch(s.shape, self.args.shape)]
        shapes.sort(key=lambda s: s.shape)

        def style_by_image(index: int, text: str) -> str:
            if index % 2 == 1:
                text = f"[bold]{text}[/bold]"
            if "aarch64" in images[index].name:
                text = f"[blue]{text}[/blue]"
            elif "DenseIO" in images[index].name:
                text = f"[green]{text}[/green]"
            return text

        namelen = self.args.width
        spc = 2
        for shape in shapes:
            shape_name = shape.shape[:namelen].rjust(namelen)
            compat = []
            for i, image in enumerate(images):
                char = "X" if shape.shape in image.compatibility else " "
                char = style_by_image(i, char)
                compat.append(char)
            self.c.con.print(shape_name + " " * spc + "".join(compat))

        if self.args.image_names:
            os_ver_count = [(i.name, 1) for i in images]
        else:
            os_ver_count = list(
                collections.Counter(
                    [f"{i.os}:{i.os_version}" for i in images]
                ).items()
            )
        total = 0

        def residual_bar(index: int) -> str:
            return "".join(
                style_by_image(i, "|") for i in range(index, len(images))
            )

        for text, count in os_ver_count:
            spc_before = namelen + spc + total
            if len(text) > spc_before + count:
                text = text[-spc_before + count :]
            text = text.rjust(spc_before + count)
            hl = " " * spc_before
            for i in range(total, total + count):
                hl += style_by_image(i, "^")
            bar = residual_bar(total + count)
            hl += bar
            text += bar
            if not self.args.image_names:
                self.c.con.print(hl)
            self.c.con.print(text)
            total += count

        self.c.con.print(
            "Color Legend: [blue]aarch64[/blue], [green]DenseIO[/green]"
        )


class LaunchCmd(YoCmd):
    name = "launch"
    group = "Basic Commands"
    help = "Launch an OCI instance."
    description = """
    Launch an OCI instance.

    The instance settings (image/OS, shape, name, etc) are typically taken from
    the instance profile in your configuration file.  However, you can override
    these settings with command line options too.

    You can run startup tasks on the instance via the "-t" option. Again, these
    can be specified via an instance profile, so that you don't need to write
    long commands. If you ask Yo to run a task, it will wait until the instance
    is ready, and then connect over SSH so that it can start the tasks.

    You can use "-s" to wait until the instance is ready and then use SSH to
    connect. If you've configured "yo.notify_prog", then you can also receive a
    desktop notification when your instance is ready. Alternatively, use "-w" to
    wait until the instance is ready, but not connect via SSH.
    """

    def _profile_choices(self) -> t.Optional[t.List[str]]:
        if hasattr(self, "c"):
            return list(self.c.instance_profiles)
        else:
            return None  # for docs

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--name",
            "-n",
            type=str,
            default=None,
            help="Name to give the instance",
        )
        grp = parser.add_mutually_exclusive_group()
        self.add_with_completer(
            grp,
            self.complete_os,
            "--os",
            type=str,
            default=None,
            help="Operating system and version, separated by colon (:)",
        )
        self.add_with_completer(
            grp,
            self.complete_image,
            "--image",
            type=str,
            default=None,
            help="Display name of a custom image in the instance_compartment_id",
        )
        self.add_with_completer(
            grp,
            self.complete_volume,
            "--volume",
            "-V",
            type=str,
            default=None,
            help="Select a boot volume to use to launch your instance",
        )
        self.add_with_completer(
            parser,
            self.complete_shape,
            "--shape",
            "-S",
            type=str,
            default=None,
            help="Specify the shape to use",
        )
        parser.add_argument(
            "--boot-volume-size-gbs",
            type=int,
            default=None,
            help="Specify the size of the boot volume (unit is GiB)",
        )
        parser.add_argument(
            "--mem",
            type=float,
            default=None,
            help="Specify the amount of memory (unit is GiB)",
        )
        parser.add_argument(
            "--cpu",
            type=float,
            default=None,
            help="Specify the amount of CPUs",
        )
        parser.add_argument(
            "--wait",
            "-w",
            action="store_true",
            help="Wait for the instance to start running",
        )
        parser.add_argument(
            "--wait-ssh",
            action="store_true",
            help="Wait for the instance to be reachable via SSH (implies --wait)",
        )
        parser.add_argument(
            "--ssh",
            "-s",
            action="store_true",
            help="SSH to the instance once it is running (implies --wait-ssh)",
        )
        parser.add_argument(
            "--exact-name",
            "-E",
            action="store_true",
            default=None,
            help="When set, allows you to bypass the name rules implemented "
            "by this program. In particular: (1) allows non-unique "
            "instance names, and (2) allows you to use a name which is "
            "not prefixed by your username.",
        )
        parser.add_argument(
            "--no-exact-name",
            action="store_false",
            dest="exact_name",
            default=None,
            help="the opposite of --exact-name (this is the default, but can "
            "be used to override your Yo configuration file)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="When set, don't actually create the instance, just print "
            "what we would have done.",
        )
        parser.add_argument(
            "--profile",
            "-p",
            type=str,
            default="DEFAULT",
            choices=self._profile_choices(),
            help="Which profile (from your ~/.oci/yo.ini) should be used",
        )
        parser.add_argument(
            "--task",
            "-t",
            type=str,
            action="append",
            dest="tasks",
            default=[],
            choices=arg_choices(list_tasks()),
            help="Tasks to run once the instance is up and accessible",
        )
        parser.add_argument(
            "--load-image",
            choices=list(ImageLoad),
            type=ImageLoad,
            default=None,
            help="Strategy for loading images (relevant only for --image)",
        )
        parser.add_argument(
            "--username",
            "-u",
            type=str,
            default=None,
            help="Custom username for logging into the instance",
        )

    def _maybe_warn_name(self, profile: InstanceProfile, name: str) -> str:
        if self.args.name is not None and name != self.args.name:
            self.c.con.log(
                f"[magenta]Warning[/magenta]: display name set to {name} "
                f"instead of {self.args.name}. If you want to have your name "
                f"used exactly, use --exact-name."
            )
        elif self.args.name is None and name != profile.name:
            self.c.con.log(
                f"[magenta]Warning[/magenta]: display name set to {name} "
                f"instead of {profile.name}. If you want to have your name "
                f"used exactly, use --exact-name and pass --name explicitly."
            )
        return name

    def pick_name(self, profile: InstanceProfile, max_tries: int = 100) -> str:
        if self.args.exact_name:
            if not self.args.name:
                raise YoExc(
                    "You specified --exact-name but did not provide a name"
                )
            return t.cast(str, self.args.name)
        name = profile.name
        if self.args.name is not None:
            name = self.args.name
        name = standardize_name(name, self.args.exact_name, self.c.config)
        all_instances = self.c.list_instances()
        names = set(
            inst.name for inst in all_instances if inst.state != "TERMINATED"
        )
        for vol in self.c.list_volumes():
            if vol.saved_instance_metadata:
                names.add(vol.saved_instance_metadata.name)
        if name not in names:
            return self._maybe_warn_name(profile, name)
        stem = name
        ver = 0
        m = re.search(r"-(\d+)$", stem)
        if m:
            stem = stem[: m.span()[0]]
            ver = int(m.group(1))
        for i in range(ver + 1, ver + max_tries + 1):
            name = f"{stem}-{i}"
            if name not in names:
                return self._maybe_warn_name(profile, name)
        raise YoExc(
            f"We could not come up with a unique instance name, after trying "
            f"{max_tries} times. Consider changing your supplied name or "
            f"using the --exact-name option to allow non-unique names."
        )

    def pick_image(self, profile: InstanceProfile, shape: str) -> YoImage:
        """
        Return an image ID based on the profile settings (and command line
        args if they override it).
        """
        load_image = profile.load_image
        if self.args.load_image:
            load_image = self.args.load_image

        if self.args.image:
            return self.c.get_image_by_name(self.args.image, load_image)
        elif self.args.os:
            os_config = self.args.os
        elif profile.image:
            return self.c.get_image_by_name(profile.image, load_image)
        elif profile.os:
            os_config = profile.os
        else:
            # should be impossible
            assert False, "no image or os specified"
        os, ver = os_config.split(":", 1)

        def compatible(image: YoImage) -> bool:
            return (
                image.os == os
                and image.os_version == ver
                and image.compatibility.get(shape) is not None
            )

        images = self.c.list_official_images()
        images = list(filter(compatible, images))
        images.sort(key=lambda i: i.name, reverse=True)
        if not images:
            raise YoExc(
                f"No matching images for {os_config} and shape {shape}..."
            )

        image = images[0]
        dn = image.name
        self.c.con.log(f"Using image [blue]{dn}[/blue]")
        return image

    def set_mem_cpu(
        self,
        profile: InstanceProfile,
        image: YoImage,
        shape: YoShape,
        create_args: t.Dict[str, t.Any],
    ) -> None:
        """
        Set the memory and cpu of an instance, if necessary.

        This is actually complex. We let users configure mem/cpu in many places,
        and you can configure just one of them if you'd like. One could be set,
        but not the other. Further, a shape may or may not support memory or CPU
        flex. And finally, we need to check the image compatibility.
        """
        mem = self.args.mem or profile.mem
        cpu = self.args.cpu or profile.cpu
        if (
            not self.args.mem
            and not self.args.cpu
            and not shape.memory_options
            and not shape.ocpu_options
        ):
            # This is very specific but very common. When the instance is not
            # flex, and the user didn't provide mem/cpu CLI flags, we don't need
            # to do any more. Note that in the case where the instance profile
            # does have memory/cpu values configured, but the instance is
            # non-flex, we don't continue: this would raise an error which is
            # somewhat hard for a user to avoid.
            return

        # ENSURE CPU CONFIGURED, VERIFY SHAPE COMPAT
        if not cpu:
            # cpu is not configured (but memory was), use the shape default
            cpu = shape.ocpus
        elif shape.ocpu_options:
            if cpu < shape.ocpu_options.min or cpu > shape.ocpu_options.max:
                raise YoExc(
                    f"CPU selection {cpu} is out of allowed range "
                    f"{shape.ocpu_options.min} - {shape.ocpu_options.max}"
                )
            # cpu is set, and in correct range, yay!
        else:
            raise YoExc("You configured CPU, but this is not a flex shape")

        # ENSURE MEM CONFIGURED, VERIFY SHAPE COMPAT
        if not mem:
            # mem is not configured (but cpu was), use the shape default
            if (
                shape.memory_options
                and shape.memory_options.default_per_ocpu_gbs
            ):
                mem = shape.memory_options.default_per_ocpu_gbs * cpu
            else:
                mem = (shape.memory_in_gbs / shape.ocpus) * cpu
        elif shape.memory_options:
            # mem is configured, check its range
            mem_per_ocpu = mem / cpu
            if (
                mem < shape.memory_options.min_gbs
                or mem > shape.memory_options.max_gbs
            ):
                raise YoExc(
                    f"Memory selection {mem} is out of allowed range "
                    f"{shape.memory_options.min_gbs} - "
                    f"{shape.memory_options.max_gbs}"
                )
            elif (
                mem_per_ocpu < shape.memory_options.min_per_ocpu_gbs
                or mem_per_ocpu > shape.memory_options.max_per_ocpu_gbs
            ):
                raise YoExc(
                    f"The mem/CPU ratio you have, {mem_per_ocpu} GiB/CPU "
                    f"(mem={mem}, cpu={cpu}) is out of allowed range: "
                    f"{shape.memory_options.min_per_ocpu_gbs} GiB/CPU - "
                    f"{shape.memory_options.max_per_ocpu_gbs} GiB/CPU"
                )
        else:
            raise YoExc("You configured Mem, but this is not a flex shape")

        # CHECK IMAGE COMPATIBILITY
        compat = image.compatibility[shape.shape]
        if (
            compat.min_ocpu
            and compat.max_ocpu
            and (cpu < compat.min_ocpu or cpu > compat.max_ocpu)
        ):
            raise YoExc(
                f"Configured CPU {cpu} is not compatible with image "
                f"{image.name}: allowed CPU range {compat.min_ocpu} "
                f" - {compat.max_ocpu}"
            )
        if (
            compat.min_mem_gbs
            and compat.max_mem_gbs
            and (mem < compat.min_mem_gbs or mem > compat.max_mem_gbs)
        ):
            raise YoExc(
                f"Configured Mem {mem} is not compatible with image "
                f"{image.name}: allowed Mem range (GiB) {compat.min_mem_gbs}"
                f" - {compat.max_mem_gbs}"
            )
        self.c.con.log(
            f"Configured flex shape with [blue]{cpu} CPUs[/blue]"
            f" and [blue]{mem} GiB[/blue] memory"
        )
        create_args["shape_config"] = {
            "memory_in_gbs": mem,
            "ocpus": cpu,
        }

    def standardize_wait(self, tasks: bool) -> None:
        # There are several conditions where we may need to wait. Of course,
        # --ssh requires waiting for the instance to be ready, but also running
        # tasks on the instance. Finally, we have the --wait and --wait-ssh
        # arguments. This simply makes all of the arguments consistent  with
        # each other.
        if self.args.ssh or tasks:
            self.args.wait_ssh = True
        if self.args.wait_ssh:
            self.args.wait = True

    def user_data(
        self, image_user: str, profile: InstanceProfile
    ) -> t.Tuple[str, t.Optional[str]]:
        user_spec = self.args.username or profile.username
        if not user_spec or user_spec == "$DEFAULT":
            return image_user, None
        elif user_spec == "$MY_USERNAME":
            user_spec = self.c.config.my_username
        self.c.con.log(f"Setting custom username: {user_spec}")
        user_data_lines = [
            "#cloud-config",
            "system_info:",
            "  default_user:",
            f"    name: {user_spec}",
        ]
        user_data = base64.b64encode(
            "\n".join(user_data_lines).encode()
        ).decode()
        return user_spec, user_data

    def run(self) -> None:
        profile = self.c.instance_profiles[self.args.profile]
        create_args = profile.create_arg_dict()

        if self.args.shape is not None:
            # override configured shape from "create_arg_dict()"
            create_args["shape"] = self.args.shape
        shape = self.c.get_shape_by_name(create_args["shape"])
        create_args["compartment_id"] = self.c.config.instance_compartment_id
        subnet = self.c.pick_subnet(profile.availability_domain)
        create_args["subnet_id"] = subnet.id

        volume = None
        if self.args.volume:
            volname = standardize_name(
                self.args.volume, self.args.exact_name, self.c.config
            )
            volume = self.c.get_volume(volname, kind=VolumeKind.BOOT)
            if volume.image_id is not None:
                image = self.c.get_image(volume.image_id)
                user = OS_TO_USER[image.os]
            else:
                user = "opc"  # better than nothing
            create_args["volume_id"] = volume.id
            self.c.con.log(f"Using boot volume: {self.args.volume}")
        else:
            image = self.pick_image(profile, shape.shape)
            create_args["image_id"] = image.id
            user = OS_TO_USER[image.os]

        # Grab ssh key from the config file, NOT instance profile
        create_args["metadata"] = {
            "ssh_authorized_keys": self.c.config.ssh_public_key_full,
        }

        user, user_data = self.user_data(user, profile)
        if user_data:
            create_args["metadata"]["user_data"] = user_data
        create_args["username"] = user

        self.set_mem_cpu(profile, image, shape, create_args)

        name = self.pick_name(profile)
        create_args["display_name"] = name
        if self.args.boot_volume_size_gbs is not None:
            gbs = self.args.boot_volume_size_gbs
            create_args["boot_volume_size_gbs"] = gbs

        self.c.con.log(f"Launching instance [blue]{name}[/blue]")
        if self.args.dry_run:
            self.c.con.log("DRY RUN. Args below:")
            self.c.con.log(create_args)
            return
        inst = self.c.launch_instance(create_args)
        if volume:
            # If we're launching from a boot volume, there may be a saved
            # instance metadata. Clearly we didn't use that to launch the
            # instance, but regardless, we don't want that metadata on the
            # volume now that it has in use again. Remove it.
            self.c.remove_saved_metadata(volume)

        tasks = set(profile.tasks + self.args.tasks)
        self.standardize_wait(bool(tasks))

        if not self.args.wait:
            return

        # Wait for the instance to reach RUNNING
        inst = self.c.wait_instance_state(inst.id, "RUNNING")

        # Wait for SSH to come up
        if self.args.wait_ssh:
            ip = self.c.get_instance_ip(inst)
            if not wait_for_ssh_access(ip, user, self.c):
                self.c.con.log("[red]Could not connect via SSH")
                self.c.con.log("Maybe you're not connected to VPN?")
                return

        run_all_tasks(self.c, inst, tasks)
        if tasks:
            task_join(self.c, inst)

        send_notification(self.c, f"Instance {inst.name} is ready!")

        if self.args.ssh:
            ssh_into(ip, user, ctx=self.c)


class TerminateCmd(MultiInstanceCommand):
    name = "terminate"
    group = "Instance Management"
    help = "Terminate one or more instances."
    description = """
    Terminate one or more instances.

    This command offers a "--dry-run" mode for safety. It also requires that you
    confirm the instances you terminate, or else run with "--yes" if you're
    confident.

    You can save preserve the instance's boot volume with "-p", and if you'd
    like, you can even preserve it and specify a more useful name using "-s". In
    the future, you can launch an instance from that boot volume using "yo
    launch -V".
    """

    action_message = "terminate"

    states_allowlist = ()
    states_denylist = ("TERMINATED",)

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--preserve-volume",
            "-p",
            dest="preserve_volume",
            action="store_true",
            default=None,
            help="Do not remove the root volume for this instance",
        )
        parser.add_argument(
            "--no-preserve-volume",
            "-P",
            dest="preserve_volume",
            action="store_false",
            default=None,
            help="Remove the root volume for this instance",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not actually terminate the instances",
        )
        parser.add_argument(
            "--wait",
            "-w",
            action="store_true",
            help="Wait for instance state TERMINATED",
        )

    def should_preserve_volume(self) -> bool:
        if self.args.preserve_volume is not None:
            return t.cast(bool, self.args.preserve_volume)
        if self.c.config.preserve_volume_on_terminate is not None:
            return self.c.config.preserve_volume_on_terminate
        return False

    def run_for_instance(self, inst: YoInstance, progress: Progress) -> None:
        # This just makes me feel good, but it's duplication. The real
        # protection is in self.run_for_all()
        if inst.termination_protected:
            raise YoExc(f"instance {inst.name} is termination protected")
        if self.args.dry_run:
            progress.log(f"DRY RUN: Would terminate {inst.id}")
            if self.should_preserve_volume():
                progress.log("DRY RUN: would preserve root volume!")
            else:
                progress.log("DRY RUN: would delete root volume!")
            return
        self.c.terminate_instance(
            inst.id,
            preserve_volume=self.should_preserve_volume(),
        )

    def confirm(self, msg: str) -> bool:
        if self.should_preserve_volume():
            self.c.con.print("Your boot volume will be preserved!")
        return super().confirm(msg)

    def run_for_all(self, instances: t.List[YoInstance]) -> None:
        """
        Process termination protection before we even get to the confirmation
        prompt, that way people are less scared :)
        """
        protected = []
        for inst in instances:
            if inst.termination_protected:
                protected.append(inst.name)
        if len(protected) == 1:
            raise YoExc(f"instance {protected[0]} is termination protected")
        elif len(protected) > 1:
            namelist = ", ".join(protected)
            raise YoExc(f"instances {namelist} are termination protected")
        return super().run_for_all(instances)

    def post_for_instance(self, inst: YoInstance) -> None:
        if self.args.wait and not self.args.dry_run:
            self.c.wait_instance_state(
                inst.id,
                "TERMINATED",
                max_interval_seconds=1,
                max_wait_seconds=600,
            )


class InstanceActionCommand(MultiInstanceCommand):
    action = "OVERRIDE ME"
    force_action: t.Optional[str] = None

    states_allowlist = ()
    states_denylist = ("TERMINATED",)
    target_state: t.Optional[str] = None

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        if self.force_action:
            parser.add_argument(
                "--force",
                action="store_true",
                help="Forcibly perform the action without notifying the OS. "
                "This risks losing data, but it is best for handling a "
                "machine whose OS is hung.",
            )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=f"Do not actually {self.action_message} the instances",
        )
        if self.target_state is not None:
            parser.add_argument(
                "--wait",
                "-w",
                action="store_true",
                help=f"Wait for instance state {self.target_state}",
            )

    def do_action(self, inst: YoInstance, action: str) -> None:
        self.c.instance_action(inst.id, action)

    def run_for_instance(self, inst: YoInstance, progress: Progress) -> None:
        action = self.action
        if self.force_action and self.args.force:
            action = self.force_action
        if self.args.dry_run:
            progress.log(f"DRY RUN: Would {action} {inst.id}")
            return
        self.do_action(inst, action)

    def post_for_instance(self, inst: YoInstance) -> None:
        if self.args.wait and self.target_state and not self.args.dry_run:
            inst = self.c.wait_instance_state(
                inst.id,
                self.target_state,
                max_interval_seconds=1,
                max_wait_seconds=600,
            )
            send_notification(
                self.c, f"Instance {inst.name} is now in state {inst.state}"
            )


class StopCommand(InstanceActionCommand):
    name = "stop"
    group = "Instance Management"
    description = "Stop (shut down) one or more OCI instances"

    action_message = "stop"
    action = "SOFTSTOP"
    force_action = "STOP"
    target_state = "STOPPED"


class DiagnosticInterruptCommand(InstanceActionCommand):
    name = "nmi"
    alias = "diagnostic-interrupt"
    group = "Instance Management"
    description = """
    Send diagnostic interrupt (NMI) to one or more instance (dangerous)
    """

    action_message = "interrupt"
    action = "SENDDIAGNOSTICINTERRUPT"


class InstanceActionMaybeSsh(InstanceActionCommand):
    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--ssh",
            "-s",
            action="store_true",
            help="SSH to the instance once it is running (implies --wait)",
        )

    def validate_args(self, args: argparse.Namespace) -> None:
        args.wait = args.wait or args.ssh

    def run_for_all(self, instances: t.List[YoInstance]) -> None:
        if self.args.ssh and self.instance_count != 1:
            raise YoExc(
                f"You passed --ssh, but there are {self.instance_count} "
                f"instances"
            )
        return super().run_for_all(instances)

    def post_for_instance(self, inst: YoInstance) -> None:
        super().post_for_instance(inst)
        if not self.args.ssh:
            return
        ip = self.c.get_instance_ip(inst, True)
        user = self.c.get_ssh_user(inst)
        if not wait_for_ssh_access(ip, user, self.c):
            self.c.con.log("[red]Could not connect via SSH")
            self.c.con.log("Maybe you're not connected to VPN?")
            return
        send_notification(self.c, f"Instance {inst.name} is connected via SSH")
        ssh_into(ip, user, ctx=self.c)


class RebootCommand(InstanceActionMaybeSsh):
    name = "reboot"
    group = "Instance Management"
    description = "Reboot one or more OCI instances."

    action_message = "reboot"
    action = "SOFTRESET"
    force_action = "RESET"
    target_state = "RUNNING"


class StartCommand(InstanceActionMaybeSsh):
    name = "start"
    group = "Instance Management"
    description = "Start (boot up) one or more OCI instances."

    action_message = "start"
    action = "START"
    target_state = "RUNNING"
    needs_confirmation = False


class ResizeCmd(InstanceActionMaybeSsh):
    name = "resize"
    group = "Instance Management"
    description = "Resize (change shape) and reboot an OCI instance."

    action_message = "resize"
    action = "RESIZE"  # this is a fake action
    target_state = "RUNNING"
    needs_confirmation = True

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        self.add_with_completer(
            parser,
            self.complete_shape,
            "--shape",
            "-S",
            type=str,
            help="Instance shape to select (REQUIRED)",
        )

    def validate_args(self, args: argparse.Namespace) -> None:
        super().validate_args(args)
        if not args.shape:
            raise YoExc("You must provide --shape")

    def do_action(self, inst: YoInstance, _: str) -> None:
        self.c.resize_instance(inst.id, self.args.shape)


class TeardownCmd(SingleInstanceCommand):
    name = "teardown"
    group = "Instance Management"
    description = "Save block volume and instance metadata, then terminate."
    states_allowlist: t.Collection[str] = ()
    states_denylist: t.Collection[str] = ("TERMINATED", "TERMINATING")

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Do not prompt for confirmation, assume yes",
        )

    def run_for_instance(self, instance: YoInstance) -> None:
        if instance.termination_protected:
            raise YoExc(f"Instance {instance.name} is termination protected")
        inst_to_atch = self.c.attachments_by_instance()
        self.c.con.print(
            f"About to [red]TERMINATE[/red] instance [blue]{instance.name}[/blue],"
            " preserving the boot volume so it can be later rebuilt."
        )
        if len(inst_to_atch[instance.id]) > 1:
            self.c.con.print(
                "[orange]warning:[/orange] This instance has volumes other than "
                "the boot volume attached. Yo cannot remember these volume "
                "attachments: if you rebuild the instance, you will need to "
                "manually reattach the volumes."
            )
        if self.args.yes:
            self.c.con.print("[red]Skipping confirmation because of --yes")
        elif Confirm.ask("Is this ok?"):
            self.c.con.print("[bold red]Confirmed.")
        else:
            self.c.con.print("Aborted!")
            return
        self.c.save_instance(instance)


class RebuildCmd(YoCmd):
    name = "rebuild"
    group = "Instance Management"
    description = "Rebuild a saved & torn down instance."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_saved,
            "name",
            type=str,
            help="Name of instance in SAVED state",
        )
        parser.add_argument(
            "--exact-name",
            "-E",
            action="store_true",
            default=None,
            help="Do not standardize the name by prefixing it with your "
            "system username if necessary.",
        )
        parser.add_argument(
            "--wait",
            "-w",
            action="store_true",
            help="Wait for the instance to start running",
        )
        parser.add_argument(
            "--ssh",
            "-s",
            action="store_true",
            help="SSH to the instance once it is running (implies --wait)",
        )

    def run(self) -> None:
        name = standardize_name(
            self.args.name, self.args.exact_name, self.c.config
        )
        for v in self.c.list_volumes():
            md = v.saved_instance_metadata
            if md and md.name == name:
                break
        else:
            raise YoExc(f"could not find saved instance: {name}")
        inst = self.c.resume_instance(v)
        if self.args.wait or self.args.ssh:
            self.c.wait_instance_state(inst.id, "RUNNING")
        if self.args.ssh:
            ip = self.c.get_instance_ip(inst)
            user = self.c.get_ssh_user(inst)
            if not wait_for_ssh_access(ip, user, self.c):
                self.c.con.log("[red]Could not connect via SSH")
                self.c.con.log("Maybe you're not connected to VPN?")
                return


class OsCmd(YoCmd):
    name = "os"
    group = "Informative Commands"
    description = "List official OS and version combinations."

    def run(self) -> None:
        images = self.c.list_official_images()
        names = sorted(set(f"{i.os}:{i.os_version}" for i in images))
        self.c.con.print("\n".join(names))


class ShapesCmd(YoCmd):
    name = "shapes"
    group = "Informative Commands"
    description = "List instance shape options."

    NAME_TO_FILTER: t.Dict[str, t.Callable[[YoShape], bool]] = {
        "bm": lambda s: s.shape.startswith("BM."),
        "vm": lambda s: s.shape.startswith("VM."),
        "amd": lambda s: "AMD" in s.processor_description,
        "intel": lambda s: "Intel" in s.processor_description,
        "arm": lambda s: "Ampere" in s.processor_description,
        "flex": lambda s: s.ocpu_options is not None,
        "gpu": lambda s: s.gpus > 0,
        "disk": lambda s: s.local_disks > 0,
    }

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--verbose",
            "-v",
            help="print detailed shape information",
            action="store_true",
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--cpu",
            action="store_true",
            help="display detailed CPU information (default)",
        )
        group.add_argument(
            "--disk",
            action="store_true",
            help="display detailed disk information",
        )
        group.add_argument(
            "--gpu",
            action="store_true",
            help="display detailed gpu information",
        )
        group.add_argument(
            "--availability",
            "-a",
            action="store_true",
            help="display availability across domains (long load time)",
        )

        parser.add_argument(
            "--filter",
            "-f",
            choices=self.NAME_TO_FILTER.keys(),
            action="append",
            help="filter to shapes with particular features (multiple allowed)",
        )

    def apply_filters(self, shape: YoShape) -> bool:
        f = self.args.filter or []
        return all([self.NAME_TO_FILTER[n](shape) for n in f])

    def filtered_shapes(self) -> t.Iterable[YoShape]:
        return filter(self.apply_filters, self.c.list_shapes())

    def headers(self, table: rich.table.Table) -> None:
        table.add_column("Shape")
        table.add_column("Mem")
        table.add_column("CPUs")
        table.add_column("GPUs")
        table.add_column("Net(gbps)")
        table.add_column("Disk(GiB)")
        if self.args.disk:
            table.add_column("# Disks")
            table.add_column("Disk Info")
        elif self.args.gpu:
            table.add_column("GPU Info")
        else:
            table.add_column("CPU Info")

    def add_row(self, shape: YoShape, table: rich.table.Table) -> None:
        fields = [
            shape.shape,
            str(shape.memory_in_gbs),
            str(shape.ocpus),
            str(shape.gpus),
            str(shape.networking_bandwidth_in_gbps),
            str(shape.local_disks_total_size_in_gbs or 0),
        ]
        if self.args.disk:
            fields.append(str(shape.local_disks))
            fields.append(shape.local_disk_description)
        elif self.args.gpu:
            fields.append(shape.gpu_description)
        else:
            fields.append(shape.processor_description)
        table.add_row(*fields)

    def show_avail(self) -> None:
        shapes = list(self.filtered_shapes())
        limit_names: t.Set[str] = set()
        for shape in shapes:
            limit_names.update(shape.quota_names)
        limits = self.c.list_limit_availability(limit_names)

        table = rich.table.Table()
        table.add_column("Shape")
        for ad in limits.all_ads:
            table.add_column(ad)

        missing_quotas: t.Set[str] = set()
        for shape in shapes:
            vals: t.List[str] = [shape.name]
            shav = self.c.compute_shape_availability(limits, shape)
            if shav.missing_quotas:
                vals[0] = f"*{shape.name}"
                missing_quotas.update(shav.missing_quotas)
            for ad in limits.all_ads:
                fit = shav.ad_to_max_count[ad]
                if fit is not None:
                    fit = int(fit)
                    if fit >= 1:
                        vals.append(f"[green]{fit}")
                    else:
                        vals.append(f"[red]{fit}")
                else:
                    vals.append("[green](unlimited)")
            table.add_row(*vals)
        self.c.con.print(table)
        if missing_quotas:
            self.c.con.print(
                "[italic]*Some quotas were not found, yo assumed they are unlimited"
            )

        self.c.con.line()
        self.c.con.print(
            "Looking for more details on a particular shape? Try `yo limits -S SHAPE`"
        )

    def run(self) -> None:
        if self.args.verbose:
            for shape in self.filtered_shapes():
                self.c.con.print(shape)
        elif self.args.availability:
            self.show_avail()
        else:
            table = rich.table.Table()
            self.headers(table)
            for shape in sorted(self.filtered_shapes(), key=lambda x: x.shape):
                self.add_row(shape, table)
            self.c.con.print(table)


class ShapeCmd(YoCmd):
    name = "shape"
    group = "Informative Commands"
    description = "Get info about a single shape."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_shape,
            "shape",
            type=str,
            default=None,
            help="shape to get info about",
        )

    def run(self) -> None:
        s = self.c.get_shape_by_name(self.args.shape)
        table = rich.table.Table()
        table.add_column("Topic", justify="right")
        table.add_column("Info")
        table.add_row("Name", s.shape)
        table.add_row("Processor", s.processor_description)
        table.add_row("# CPUs", str(s.ocpus))
        table.add_row("Memory (GiB)", str(s.memory_in_gbs))
        table.add_row("Bandwidth (gpbs)", str(s.networking_bandwidth_in_gbps))
        table.add_row("Max # VNIC", str(s.max_vnic_attachments))
        table.add_row("GPU Description", s.gpu_description)
        table.add_row("# GPUs", str(s.gpus))
        table.add_row("Local Disks", s.local_disk_description)
        table.add_row("# Local Disks", str(s.local_disks))
        table.add_row("Total Disk (GiB)", str(s.local_disks_total_size_in_gbs))
        if s.ocpu_options:
            table.add_row(
                "Flex CPU Options",
                f"{s.ocpu_options.min} - {s.ocpu_options.max} CPU",
            )
        if s.memory_options:
            mo = s.memory_options
            table.add_row(
                "Flex Mem Options",
                f"{mo.min_gbs} - {mo.max_gbs} GiB\n"
                f"{mo.min_per_ocpu_gbs} - {mo.max_per_ocpu_gbs} GiB/CPU\n"
                f"Default: {mo.default_per_ocpu_gbs} GiB / CPU",
            )
        if s.networking_bandwidth_options:
            nb = s.networking_bandwidth_options
            table.add_row(
                "Bandwidth Options",
                f"{nb.min_gbps} - {nb.max_gbps} gbps "
                f"(default: {nb.default_per_ocpu_gbps} gbps/CPU)",
            )
        if s.max_vnic_attachment_options:
            vo = s.max_vnic_attachment_options
            table.add_row(
                "Max VNIC Options",
                f"{vo.min} - {vo.max} (default: {vo.default_per_ocpu} /CPU)",
            )
        self.c.con.print(table)


class LimitsCmd(YoCmd):
    name = "limits"
    group = "Informative Commands"
    description = "Display your tenancy & region's service limits."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--service",
            "-s",
            type=str,
            choices=["compute", "block-storage"],
            default="compute",
            help="which service to view limits of",
        )
        self.add_with_completer(
            parser,
            self.complete_shape,
            "--shape",
            "-S",
            type=str,
            default=None,
            help="shape to get info about",
        )

    def run(self) -> None:
        limit_names = []
        if self.args.shape:
            shape = self.c.get_shape_by_name(self.args.shape)
            limit_names = shape.quota_names

        limits = self.c.list_limit_availability(
            limit_names, service=self.args.service
        )

        if limits.ad_limits:
            table = rich.table.Table(title="Resource Limits per-AD")
            table.add_column("Limit")
            for ad in limits.all_ads:
                table.add_column(ad)
            for lim in limits.ad_limits:
                vals: t.List[str] = [lim]
                ad_to_value = limits.name_to_ad_to_avail[lim]
                for ad in limits.all_ads:
                    if ad in ad_to_value:
                        av = ad_to_value[ad]
                        vals.append(
                            f"{av.fractional_availability} / {av.limit}"
                        )
                    else:
                        vals.append("--")
                table.add_row(*vals)
            self.c.con.print(table)

        if limits.name_to_avail:
            table = rich.table.Table(title="Global or Regional Limits")
            table.add_column("Limit")
            table.add_column("Availability")
            for name, av in limits.name_to_avail.items():
                table.add_row(
                    name, f"{av.fractional_availability} / {av.limit}"
                )
            self.c.con.print(table)

        if self.args.shape:
            self.c.con.rule("But... will it fit?")
            shav = self.c.compute_shape_availability(limits, shape)

            table = rich.table.Table(
                "Resource", "Requirement", title="Resources Required"
            )
            for quota, requirement in shav.quota_to_requirement.items():
                table.add_row(quota, str(requirement))
            self.c.con.print(table)

            table = rich.table.Table(title="Will it fit?")
            table.add_column("AD")
            table.add_column("Space")
            table.add_column("Limiting Factor?")
            for ad in limits.all_ads:
                space = shav.ad_to_max_count[ad]
                if space is None:
                    table.add_row("[green](unlimited)")
                elif space >= 1:
                    table.add_row(
                        ad,
                        f"[green]{int(space)}",
                        "--",
                    )
                else:
                    factors = "\n".join(
                        f"{q}: require {shav.quota_to_requirement[q]} but only {v} avail"
                        for q, v in shav.ad_to_limiting_quotas[ad]
                    )
                    table.add_row(
                        ad,
                        f"[red]{int(space)}",
                        factors,
                    )
            self.c.con.print(table)

            if shav.missing_quotas:
                self.c.con.print(
                    "[orange]Warning:[/orange] the following quotas were not listed by OCI, so "
                    "yo could not determine whether they are satisfied:"
                )
                self.c.con.print(
                    "\n".join(f"- {q}" for q in shav.missing_quotas)
                )


class DebugCmd(YoCmd):
    name = "debug"
    group = "Diagnostic Commands"
    description = "Open up a python prompt in the context of a command."

    def run(self) -> None:
        try:
            import IPython  # type: ignore

            IPython.embed()
            return
        except ImportError:
            pass

        # Do this outside the except block so that any errors inside the
        # code.interact don't get treated as a nested exception.
        import code

        code.interact(local=locals())


class VersionCmd(YoCmd):
    name = "version"
    group = "Diagnostic Commands"
    description = "Show the version of yo and check for updates."

    def run(self) -> None:
        ver = current_yo_version()
        print(f"yo {ver[0]}.{ver[1]}.{ver[2]}")
        print(f"Documentation: {DOCUMENTATION_URL}")
        print(f"Development & issues: {REPOSITORY_URL}")
        print()

        latest_ver = latest_yo_version()
        if not latest_ver:
            print("Error loading the latest version!")
            return
        elif latest_ver == ver:
            print("You are up-to-date!")
            return
        print("Latest version: {}.{}.{}".format(*latest_ver))
        print("To update:")
        print(f"  {yo.util.UPGRADE_COMMAND}")
        print("Then verify by re-running yo version")


class VolumeListCmd(YoCmd):
    name = "volume list"
    group = "Volume Management Commands"
    description = "List block & boot volumes."

    def run(self) -> None:
        volumes = self.c.list_volumes(refresh=True)

        table = rich.table.Table()
        table.add_column("Name")
        table.add_column("Kind")
        table.add_column("GiB")
        table.add_column("State")
        table.add_column("AD")
        table.add_column("Created")
        for volume in volumes:
            table.add_row(
                volume.name,
                volume.kind,
                str(int(volume.size_in_gbs)),
                volume.state,
                volume.ad,
                strftime(volume.time_created),
            )
        self.c.con.print(table)


class AttachedCmd(YoCmd):
    name = "volume attached"
    alias = "attached"
    group = "Volume Management Commands"
    description = "List volumes by their current instance attachment."

    def run(self) -> None:
        vol_by_id = {vol.id: vol for vol in self.c.list_volumes(refresh=True)}
        va_by_inst = self.c.attachments_by_instance()

        table = rich.table.Table()
        table.add_column("Instance/Volume")
        table.add_column("Kind")
        table.add_column("GiB")
        table.add_column("Volume State")
        table.add_column("Att. State")
        table.add_column("Att. Kind")
        for inst_id, vas in va_by_inst.items():
            # filter detached, they will look weird
            vas = [va for va in vas if va.state != "DETACHED"]
            if not vas:
                continue
            inst = self.c.get_instance_by_id(inst_id)
            table.add_row(f"{inst.name}:")
            for i, va in enumerate(vas):
                vol = vol_by_id[va.volume_id]
                table.add_row(
                    f"- {vol.name}",
                    vol.kind,
                    str(vol.size_in_gbs),
                    vol.state,
                    va.state,
                    va.attachment_type,
                    end_section=(i + 1 == len(vas)),
                )
        self.c.con.print(table)


def volume_attach_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-exact-name",
        action="store_false",
        dest="exact_name",
        default=None,
        help="follow Yo's normal rules on standardizing instance & volume names"
        " (this is the default, but can be used to override the config file)",
    )
    parser.add_argument(
        "--exact-name",
        "-E",
        action="store_true",
        dest="exact_name",
        default=None,
        help="use the instance & volume names exactly as given",
    )
    va = parser.add_argument_group(
        "Volume Attachment Arguments",
    )
    va.add_argument(
        "--ro",
        action="store_true",
        help="Attach volume read-only",
    )
    va.add_argument(
        "--shared",
        action="store_true",
        help="Attach volume in shared mode",
    )
    va.add_argument(
        "--no-setup",
        action="store_false",
        dest="setup",
        help="Do not automatically run iSCSI setup commands over SSH",
    )
    parser.set_defaults(kind="pv")
    grp = va.add_mutually_exclusive_group()
    grp.add_argument(
        "--iscsi",
        dest="kind",
        action="store_const",
        const="iscsi",
        help="use iSCSI to attach",
    )
    grp.add_argument(
        "--pv",
        dest="kind",
        action="store_const",
        const="pv",
        help="use paravirtualized to attach (default)",
    )
    grp.add_argument(
        "--emulated",
        dest="kind",
        action="store_const",
        const="emulated",
        help="use emulated to attach",
    )
    grp.add_argument(
        "--service-determined",
        dest="kind",
        action="store_const",
        const="service_determined",
        help="Let OCI decide the right attachment type",
    )


def do_volume_attach(
    ctx: YoCtx, args: argparse.Namespace, volume: YoVolume, inst: YoInstance
) -> None:
    va = ctx.attach_volume(
        volume,
        inst.id,
        kind=args.kind,
        ro=args.ro,
        shared=args.shared,
    )
    va = ctx.wait_attachment(va, "ATTACHED")
    setup = False
    if args.setup and args.kind == "iscsi":
        ctx.con.log("Running commands to mount iSCSI volume...")
        ip = ctx.get_instance_ip(inst)
        user = ctx.get_ssh_user(inst)
        attach, _ = ctx.get_attachment_commands(va)
        res = ssh_into(
            ip,
            user,
            ctx,
            extra_args=["-q"],
            cmds=[" && ".join(attach)],
            capture_output=True,
            quiet=True,
        )
        if res.returncode == 0:
            setup = True
        else:
            ctx.con.log("[orange]warn:[/orange] failed to setup iSCSI device")
    ctx.report_attached(va, setup)


class VolumeCreateCmd(YoCmd):
    name = "volume create"
    group = "Volume Management Commands"
    description = "Create a block volume."

    def _default_ad(self) -> t.Optional[str]:
        if hasattr(self, "c"):
            self.c.instance_profiles["DEFAULT"].availability_domain
        return None

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "name",
            type=str,
            help="name of block volume (unique names strongly preferred)",
        )
        parser.add_argument(
            "size_gbs",
            type=int,
            help="Size of block volume",
        )
        parser.add_argument(
            "--ad",
            type=str,
            default=self._default_ad(),
            help="availability domain (not needed if you use --for)",
        )
        self.add_with_completer(
            parser,
            self.complete_instance,
            "--for",
            "-f",
            dest="inst_name",
            type=str,
            help="which instance you intend to attach to (yo will choose the"
            "right availability domain automatically)",
        )
        parser.add_argument(
            "--attach",
            "-a",
            action="store_true",
            help="attach to the instance after completion (requires --for)",
        )
        volume_attach_args(parser)

    def run(self) -> None:
        if self.args.setup:
            self.args.attach = True
        if self.args.attach and not self.args.inst_name:
            raise YoExc("--attach requires a value for --for")

        inst = None
        ad = self.args.ad
        if self.args.inst_name:
            inst = self.c.get_instance_by_name(
                self.args.inst_name,
                ("RUNNING",),
                (),
                exact_name=self.args.exact_name,
            )
            ad = inst.ad

        name = standardize_name(
            self.args.name, self.args.exact_name, self.c.config
        )
        # TODO: deduplicate...
        volume = self.c.create_volume(name, ad, self.args.size_gbs)
        self.c.wait_volume(volume, "AVAILABLE")
        if self.args.attach:
            assert inst is not None, "should be impossible"
            do_volume_attach(self.c, self.args, volume, inst)


class AttachCmd(YoCmd):
    name = "volume attach"
    alias = "attach"
    group = "Volume Management Commands"
    description = "Attach a block or boot volume to an instance."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_volume,
            "volume_name",
            type=str,
            help="name of volume",
        )
        self.add_with_completer(
            parser,
            self.complete_instance,
            "instance_name",
            type=str,
            help="name of instance",
        )
        volume_attach_args(parser)

    def run(self) -> None:
        if self.args.setup:
            self.args.wait = True
        name = standardize_name(
            self.args.volume_name, self.args.exact_name, self.c.config
        )
        inst = self.c.get_instance_by_name(
            self.args.instance_name,
            ("RUNNING",),
            (),
            exact_name=self.args.exact_name,
        )
        vol = self.c.get_volume(name)
        do_volume_attach(self.c, self.args, vol, inst)


class VolumeRename(YoCmd):
    name = "volume rename"
    group = "Volume Management Commands"
    description = "Rename a block or boot volume."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_volume,
            "volume_name",
            type=str,
            help="name of volume",
        )
        parser.add_argument(
            "new_name",
            type=str,
            help="new name for volume",
        )
        parser.add_argument(
            "--exact-name",
            "-n",
            action="store_true",
            help="do not try to standardize the volume names",
        )

    def run(self) -> None:
        old_name = standardize_name(
            self.args.volume_name, self.args.exact_name, self.c.config
        )
        new_name = standardize_name(
            self.args.new_name, self.args.exact_name, self.c.config
        )
        volume = self.c.get_volume(old_name)
        self.c.rename_volume(volume, new_name)


def detach_volume_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-exact-name",
        action="store_false",
        dest="exact_name",
        default=None,
        help="follow Yo's normal rules on standardizing instance & volume names"
        " (this is the default, but can be used to override the config file)",
    )
    parser.add_argument(
        "--exact-name",
        "-E",
        action="store_true",
        dest="exact_name",
        default=None,
        help="use the instance & volume names exactly as given",
    )
    parser.add_argument(
        "--no-teardown",
        action="store_false",
        dest="teardown",
        help="do not run iSCSI tear down commands",
    )


def do_detach_volume(
    ctx: YoCtx,
    args: argparse.Namespace,
    detach_vas: t.List[YoVolumeAttachment],
) -> None:
    for detach_va in detach_vas:
        if args.teardown and detach_va.attachment_type == AttachmentType.ISCSI:
            inst = ctx.get_instance_by_id(detach_va.instance_id)
            ctx.con.log(
                f"Running commands to unmount iSCSI volume on {inst.name}..."
            )
            ip = ctx.get_instance_ip(inst)
            user = ctx.get_ssh_user(inst)
            _, detach = ctx.get_attachment_commands(detach_va)
            res = ssh_into(
                ip,
                user,
                ctx,
                extra_args=["-q"],
                cmds=[" && ".join(detach)],
                capture_output=True,
                quiet=True,
            )
            if res.returncode != 0:
                print(res.stderr)
                raise YoExc(
                    "failed to unmount on host, your volume has not been detached"
                )
            ctx.con.log("Unmounted!")
        ctx.detach_volume(detach_va)
    for detach_va in detach_vas:
        ctx.wait_attachment(detach_va, "DETACHED")


class DetachCmd(YoCmd):
    name = "volume detach"
    alias = "detach"
    group = "Volume Management Commands"
    description = "Detach a block or boot volume from an instance."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_volume,
            "volume",
            type=str,
            help="name of volume to detach",
        )
        self.add_with_completer(
            parser,
            self.complete_instance,
            "--from",
            dest="from_instance",
            type=str,
            help="instance to detach from, if there are multiple",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="instance to detach from, if there are multiple",
        )
        detach_volume_args(parser)

    def run(self) -> None:
        if self.args.all and self.args.from_instance:
            raise YoExc("--from and --all are mutually exclusive")
        name = standardize_name(
            self.args.volume, self.args.exact_name, self.c.config
        )
        vol = self.c.get_volume(name)
        vas = self.c.attachments_by_volume()[vol.id]
        vas = [va for va in vas if va.state == "ATTACHED"]
        detach_vas = []
        if self.args.from_instance:
            inst = self.c.get_instance_by_name(
                self.args.from_instance,
                ("RUNNING",),
                (),
                exact_name=self.args.exact_name,
            )
            for va in vas:
                if va.instance_id == inst.id:
                    detach_vas.append(va)
                    break
            else:
                raise YoExc(
                    f"volume {vol.name} is not attached to instance {inst.name}"
                )
        elif len(vas) > 1 and not self.args.all:
            raise YoExc("Attached to multiple instances, use --from or --all")
        elif vas:
            detach_vas = vas
        else:
            raise YoExc(f"volume {vol.name} has no current attachments")

        do_detach_volume(self.c, self.args, detach_vas)


class VolumeDeleteCmd(YoCmd):
    name = "volume delete"
    group = "Volume Management Commands"
    description = "Delete a block or boot volume."

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        self.add_with_completer(
            parser,
            self.complete_volume,
            "name",
            type=str,
            help="name of volume to delete",
        )
        parser.add_argument(
            "--no-detach",
            "-D",
            action="store_false",
            dest="detach",
            help="do not detach from all instances first",
        )
        detach_volume_args(parser)

    def run(self) -> None:
        name = standardize_name(
            self.args.name, self.args.exact_name, self.c.config
        )
        volume = self.c.get_volume(name)
        vas = self.c.attachments_by_volume()[volume.id]
        vas = [va for va in vas if va.state == "ATTACHED"]
        if self.args.detach:
            do_detach_volume(self.c, self.args, vas)
        self.c.delete_volume(volume)
        self.c.con.log("Deleted!")


class RenameCmd(SingleInstanceCommand):
    name = "rename"
    group = "Instance Management"
    description = "Give an instance a new name."
    positional_name = True

    # This runs on any instance state
    states_allowlist = ()
    states_denylist = ()

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument("new_name", type=str, help="new name for instance")

    def run_for_instance(self, instance: YoInstance) -> None:
        new_name = standardize_name(
            self.args.new_name, self.args.exact_name, self.c.config
        )
        instances = self.c.list_instances()
        non_terminated_names = {
            inst.name for inst in instances if inst.state != "TERMINATED"
        }
        if new_name in non_terminated_names:
            raise YoExc(f"The name {new_name} is already in use")
        self.c.rename_instance(instance, new_name)


class ProtectCmd(SingleInstanceCommand):
    name = "protect"
    group = "Instance Management"
    description = "Enable or disable Yo's termination protection."
    positional_name = True

    # This runs on any instance state
    states_allowlist = ()
    states_denylist = ()

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        super().add_args(parser)
        parser.add_argument(
            "setting",
            choices=["on", "off"],
            help="whether termination protection is on or off",
        )

    def run_for_instance(self, instance: YoInstance) -> None:
        self.c.protect_instance(instance, self.args.setting == "on")


class ConsoleHistoryCmd(SingleInstanceCommand):
    name = "console-history"
    group = "Instance Communication & Interaction"
    description = "Fetch and print serial console history for an instance."

    def run_for_instance(self, instance: YoInstance) -> None:
        print(self.c.get_console_history(instance).decode())


class MoshCmd(SingleInstanceCommand):
    name = "mosh"
    group = "Instance Communication & Interaction"
    description = "Connect to the instance via mosh."

    def run_for_instance(self, inst: YoInstance) -> None:
        ip = self.c.get_instance_ip(inst)
        user = self.username
        if not user:
            user = self.c.get_ssh_user(inst)
        # Mosh uses SSH to establish an initial connection.
        # We must be sure to specify the correct SSH key, and to do this we need
        # to use all the ssh arguments we have configured.
        args = ssh_args(self.c, False)
        ssh_opt = "--ssh=ssh " + shlex_join(args)
        subprocess.run(
            [
                "mosh",
                ssh_opt,
                f"{user}@{ip}",
            ],
        )


class CacheCleanCmd(YoCmd):
    name = "cache-clean"
    group = "Diagnostic Commands"
    description = "Clear Yo's cache -- a good first troubleshooting step."

    def run(self) -> None:
        if os.path.isfile(self.c._cache_file):
            os.unlink(self.c._cache_file)


class HelpCmd(YoCmd):
    name = "help"
    group = "Diagnostic Commands"
    description = "Show help for yo."

    def run(self) -> None:
        print(__doc__.strip())


def _extend(ctx: YoCtx) -> None:
    """
    This is for advanced users to add custom extension scripts.  It is not
    mentioned in the documentation, and for good reason: there is no stable API
    defined (yet). However, it can still be useful to stick a stub in here for
    something.
    """
    # The configuration "extension_modules" is still supported, but no longer
    # recommended. Entry points (below) are a better way that don't require the
    # user to manually configure things.
    for module in ctx.config.extension_modules:
        importlib.import_module(module)

    # The importlib.metadata API is included in Python 3.8+. Normally, one might
    # simply try to import it, catching the ImportError and falling back to the
    # older API. However, the API was _transitional_ in 3.8 and 3.9, and it is
    # different enough to break callers compared to the non-transitional API. So
    # here we are, using sys.version_info like heathens.
    if sys.version_info >= (3, 10):
        from importlib.metadata import entry_points  # novermin
    else:
        import pkg_resources

        def entry_points(group: str) -> t.Iterable["pkg_resources.EntryPoint"]:
            return pkg_resources.iter_entry_points(group)

    for entry_point in entry_points(group="yo.extensions.v1"):
        entry_point.load()


def main() -> None:
    os.environ["OCI_PYTHON_SDK_NO_SERVICE_IMPORTS"] = "True"
    try:
        desc = (
            "A simple OCI client. Use 'yo help' for an overview, or yo -h "
            "for a listing of each command. For a help on a particular "
            "command, use 'yo COMMAND -h'."
        )
        parser = argparse.ArgumentParser(description=desc)
        ctx, aliases = YoCmd.setup_config()
        _extend(ctx)
        YoCmd.add_commands(
            parser,
            default="help",
            shortest_prefix=True,
            cmd_aliases=aliases,
            group_order=COMMAND_GROUP_ORDER,
        )
        argcomplete.autocomplete(parser)
        ns = parser.parse_args()
        with ctx:
            ns.func(ns)
    except YoExc as e:
        con = rich.console.Console()
        con.print(f"[bold red]error: {e.args[0]}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(1)


def build_parser_functions() -> None:
    # Don't mind this function: it exists solely to enable
    # automatic documentation generation for commands
    g = globals()
    trans = str.maketrans(" -", "__")
    for cmd in YoCmd.iter_commands():
        name = cmd.name.translate(trans)
        g[f"cmd_{name}_args"] = cmd.simple_sub_parser


if __name__ == "__main__":
    main()
elif os.environ.get("SPHINX_BUILD") == "1":
    build_parser_functions()
