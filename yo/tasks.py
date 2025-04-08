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
"""
yo.tasks: module for managing "tasks" (bash scripts) on an instance
"""
import collections
import dataclasses
import inspect
import os
import random
import re
import shlex
import stat
import string
import subprocess
import tempfile
import time
import typing as t
from functools import lru_cache
from pathlib import Path

import rich
from rich.live import Live

from yo.api import YoCtx
from yo.api import YoInstance
from yo.ssh import ssh_args
from yo.ssh import ssh_into
from yo.util import YoExc

TASK_DIRECTORIES = [
    os.path.expanduser("~/.oci/yo-tasks"),
    # This should be installed with the package
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "data/yo-tasks"),
    # Uncomment for testing, if running from a git checkout:
    # os.path.join(os.path.abspath(os.path.dirname(__file__)), "../test-tasks"),
]


GlobList = t.List[t.Tuple[str, str, bool]]


def standardize_globs(include_files: GlobList) -> t.Tuple[GlobList, GlobList]:
    user = []
    system = []
    for pattern, dest, optional in include_files:
        pattern = os.path.expanduser(pattern)
        if not pattern.startswith("/"):
            raise YoExc(
                f"Only absolute or user-relative paths are allowed: {pattern}"
            )
        if dest.startswith("~/"):
            user.append((pattern, dest[2:].lstrip("/"), optional))
        elif dest.startswith("/"):
            system.append((pattern, dest.lstrip("/"), optional))
        else:
            raise YoExc(
                f"Only absolute or user-relative paths are allowed: {dest}"
            )
    return user, system


def build_tarball(
    ctx: "YoCtx",
    include_files: GlobList,
    root: Path,
    tarball: Path,
    task_name: str,
) -> None:
    # First, build our list of files & directories to include. Raise any errors
    # regarding destination directories or missing files.
    pairs = []
    for pattern, dest, optional in include_files:
        destpath = Path(dest)
        maybe_file = Path(pattern)
        if maybe_file.is_file():
            if not dest or dest[-1] == "/":
                destpath = destpath / maybe_file.name
            pairs.append((maybe_file, destpath))
        elif maybe_file.is_dir():
            pairs.append((maybe_file, destpath))
        else:
            # Patterns must be either home or rooted, but globs must be
            # relative.  Determine the correct root directory for the glob, and
            # then glob against it after we've transformed the path to a
            # relative one.
            globroot = Path.home() if pattern.startswith("~/") else Path("/")
            matches = list(globroot.glob(pattern[1:].lstrip("/")))
            if not matches and not optional:
                raise YoExc(f"file or pattern not found: {pattern}")
            if pattern == dest:
                raise YoExc(
                    f"glob results need to have a destination directory: {pattern}"
                )
            for match in matches:
                pairs.append((match, destpath / match.name))

    verb = "building"
    if tarball.exists():
        verb = "rebuilding"
        mtime = tarball.stat().st_mtime
        for file_or_dir, _ in pairs:
            statbuf = file_or_dir.lstat()
            if statbuf.st_mtime > mtime:
                break  # need rebuild
            if stat.S_ISDIR(statbuf.st_mode):
                if any(
                    any(
                        (file_or_dir / d / p).stat().st_mtime > mtime
                        for p in ps + ds
                    )
                    for d, ps, ds in os.walk(file_or_dir)
                ):
                    break
        else:
            return  # no need to build tarball

    ctx.con.log(f"Task {task_name}: {verb} {tarball.name}")
    cmd: t.List[str | Path] = ["tar", "-czhf", tarball]
    with tempfile.TemporaryDirectory() as td:
        tdpath = Path(td)
        for src, dst in pairs:
            tmp_path = tdpath / dst
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.symlink_to(src)
            cmd.append(str(dst))
        subprocess.run(cmd, cwd=tdpath)


@dataclasses.dataclass
class YoTask:
    name: str
    path: str
    script: str
    dependencies: t.List[str]
    conflicts: t.List[str]
    prereq_for: t.List[str]

    include_files: GlobList
    """
    A list of (glob pattern, optional) tuples specifying files
    """

    sendfiles: t.List[Path]
    """
    A list of absolute filenames to copy into $TASK_DATA_DIR
    """

    @classmethod
    def create_from_string(
        cls, name: str, script: str, path: str = "(memory)"
    ) -> "YoTask":
        dependencies = []
        conflicts = []
        prereq_for = []
        all_tasks = list_tasks()
        lines = script.split("\n")
        include_files = []
        sendfiles = []
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
            elif line.startswith("PREREQ_FOR"):
                prereq_for.append(line.split(None, maxsplit=1)[1])
            elif line.startswith("INCLUDE_FILE"):
                args = shlex.split(line)
                if len(args) == 3:
                    include_files.append((args[1], args[2], False))
                elif len(args) == 2:
                    include_files.append((args[1], args[1], False))
                else:
                    raise YoExc(
                        f"INCLUDE_FILE expects 1-2 args, got {len(args) - 1}\n{line}"
                    )
                lines[i] = "# " + line
            elif line.startswith("MAYBE_INCLUDE_FILE"):
                args = shlex.split(line)
                if len(args) == 3:
                    include_files.append((args[1], args[2], True))
                elif len(args) == 2:
                    include_files.append((args[1], args[1], True))
                else:
                    raise YoExc(
                        f"MAYBE_INCLUDE_FILE expects 1-2 args, got {len(args) - 1}\n{line}"
                    )
                lines[i] = "# " + line
            elif line.startswith("SENDFILE"):
                args = shlex.split(line)
                if len(args) != 2:
                    raise YoExc(
                        f"SENDFILE expects 1 arg, got {len(args) - 1}\n{line}"
                    )
                sendfiles.append(Path(os.path.expanduser(args[1])))
                lines[i] = "# " + line
        return YoTask(
            name,
            path,
            "\n".join(lines),
            dependencies,
            conflicts,
            prereq_for,
            include_files,
            sendfiles,
        )

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
        return cls.create_from_string(name, script, path=path)

    def insert_prereq(self, other: str) -> None:
        self.dependencies.append(other)
        self.script = f"DEPENDS_ON {other}\n{self.script}"

    def prepare_files(self, ctx: "YoCtx") -> None:
        if not self.include_files:
            return
        staging_dir = Path.home() / ".cache/yo/task-files" / self.name
        staging_dir.mkdir(parents=True, exist_ok=True)

        user, system = standardize_globs(self.include_files)
        if user:
            build_tarball(
                ctx, user, Path.home(), staging_dir / "user.tar.gz", self.name
            )
            self.sendfiles.append(staging_dir / "user.tar.gz")
        if system:
            build_tarball(
                ctx, system, Path("/"), staging_dir / "system.tar.gz", self.name
            )
            self.sendfiles.append(staging_dir / "system.tar.gz")
        self.include_files.clear()


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


def _task_run(ctx: "YoCtx", inst: YoInstance, task: YoTask) -> None:
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
    export TASK_BASE_DIR={task_dir}
    export TASK_NAME={name}
    export TASK_DIR="$TASK_BASE_DIR/$TASK_NAME"
    mkdir -p "$TASK_DIR"
    cd "$TASK_DIR"
    if [ -f "status" ]; then
        rm -f "output" "pid"
        mv "status" "status.old"
    fi
    cat <<'{heredoc}' > ./script
    {script_text}
    {heredoc}
    export TASK_DATA_DIR="$TASK_DIR/files"
    [ -f "$TASK_DATA_DIR/system.tar.gz" ] && sudo tar -C / -xf "$TASK_DATA_DIR/system.tar.gz"
    [ -f "$TASK_DATA_DIR/user.tar.gz" ] && tar -C ~ -xf "$TASK_DATA_DIR/user.tar.gz"
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
    if task.sendfiles:
        mkdir_p_cmd = inspect.cleandoc(
            """
            task_dir={task_dir}
            name={name}
            mkdir -p "$task_dir/$name/files"
            echo -n "$task_dir/$name/files"
            """
        ).format(
            task_dir=task_dir_safe,
            name=shlex.quote(task.name),
        )
        proc = ssh_into(
            ip,
            user,
            ctx,
            extra_args=["-q"],
            cmds=[mkdir_p_cmd],
            quiet=True,
            capture_output=True,
        )
        scp_cmd = ["scp"] + ssh_args(ctx, False)
        scp_cmd.extend(map(str, task.sendfiles))
        scp_cmd.append(f"{user}@{ip}:{proc.stdout.decode()}/")
        subprocess.run(scp_cmd)
    ssh_into(ip, user, ctx, extra_args=["-q"], cmds=[commands], quiet=True)


class TaskPlan:
    """
    A group of tasks to be run altogether on an instance

    This plan encompasses the necessary files to copy over, as well as the order
    of the tasks to run.
    """

    name_to_task: t.Dict[str, YoTask]
    ordered_tasks: t.List[YoTask]

    def _prepare_prereqs_check_conflicts(self) -> None:
        # Now we have loaded the complete set of tasks that should run. Some tasks
        # may appoint themselves as "prerequisites" for another. We need to insert
        # this dependency relationship so that the script is updated, and so that
        # the circular dependency detection knows about it. We can also use this
        # opportunity to detect conflicts.
        for task in self.name_to_task.values():
            for name in task.prereq_for:
                if name in self.name_to_task:
                    self.name_to_task[name].insert_prereq(task.name)
            for name in task.conflicts:
                if name in self.name_to_task:
                    raise YoExc(f"Task {task.name} conflicts with {name}")

    def _create_execution_order(self) -> None:
        # Now all tasks are loaded, and prerequisites have been marked. Use a
        # topological sort to verify that no circular dependencies are present. Here
        # we use a recursive traversal because honestly, if you specify enough tasks
        # to trigger a recursion error, then I would like to receive that bug
        # report!
        name_to_visit: t.Dict[str, int] = collections.defaultdict(int)
        self.ordered_tasks.clear()  # guard against running twice

        def visit(task: YoTask) -> None:
            if name_to_visit[task.name] == 2:
                # already completed, skip
                return
            if name_to_visit[task.name] == 1:
                # currently visiting, not a DAG
                raise YoExc("Tasks express a circular dependency")

            name_to_visit[task.name] = 1
            for dep_name in task.dependencies:
                visit(self.name_to_task[dep_name])
            name_to_visit[task.name] = 2
            self.ordered_tasks.append(task)

        for task in self.name_to_task.values():
            visit(task)

    def _prepare_files(self, ctx: "YoCtx") -> None:
        for task in self.ordered_tasks:
            if task.include_files:
                task.prepare_files(ctx)
            missing = [f for f in task.sendfiles if not f.is_file()]
            if missing:
                missing_str = ", ".join(map(str, missing))
                raise YoExc(
                    f"missing files for task {task.name}: {missing_str}"
                )

    def __init__(self, tasks: t.Iterable[t.Union[YoTask, str]]) -> None:
        # The caller may specify tasks as either strings or YoTask instances, for
        # convenience. Let's get everything into a "name_to_task" dict.
        self.name_to_task = {}
        for task in tasks:
            if isinstance(task, str):
                self.name_to_task[task] = YoTask.load(task)
            else:
                self.name_to_task[task.name] = task

        # Tasks may have dependencies. Let's go through every task, and their
        # dependencies, and load them all. At this point, we're not yet checking
        # whether there are any circular dependencies: just loading them.
        tasks_to_load = list(self.name_to_task.values())
        for task in tasks_to_load:
            for name in task.dependencies:
                if name not in self.name_to_task:
                    self.name_to_task[name] = YoTask.load(name)
                    tasks_to_load.append(self.name_to_task[name])

        self.ordered_tasks = []

    def prepare(self, ctx: "YoCtx") -> None:
        self._prepare_prereqs_check_conflicts()
        self._create_execution_order()
        self._prepare_files(ctx)

    def have_tasks(self) -> bool:
        return bool(self.ordered_tasks)

    def dry_run_print(self) -> None:
        if not self.have_tasks():
            print("No tasks to run.")
            return
        print("Would start tasks in the following order:")
        for task in self.ordered_tasks:
            deps = ""
            if task.dependencies:
                deps = f" (depends on: {', '.join(task.dependencies)})"
            print(f" - {task.name}{deps}")
            if task.name == "yo-install-packages":
                print("   " + "\n   ".join(task.script.split("\n")))

    def run(self, ctx: "YoCtx", inst: YoInstance) -> None:
        # Now ordered_tasks contains the order in which we should launch them.  This
        # is just a nice-to-have: even if we launched them out of order, the
        # DEPENDS_ON function would enforce the order of execution. Regardless,
        # let's start the tasks.
        for task in self.ordered_tasks:
            _task_run(ctx, inst, task)

    def join(self, ctx: "YoCtx", inst: YoInstance) -> None:
        wait_tasks = [t.name for t in self.ordered_tasks]
        task_join(ctx, inst, wait_tasks)


def task_get_status(
    ctx: "YoCtx",
    inst: YoInstance,
) -> t.Mapping[str, t.Tuple[str, t.Union[int, str]]]:
    task_dir_safe = ctx.config.task_dir_safe
    # Take care to use the escaped task dir, and use the -print0 and xargs -0
    # arguments for maximum safety: filenames can be weird.
    command = (
        f"find {task_dir_safe} "
        "\\( -name pid -or -name status -or -name wait \\) -and -print0 "
        '2>/dev/null | xargs -0 grep -H ".*" | sort'
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


def _status_code(status: str, code: t.Union[int, str, None]) -> str:
    if status == "RUNNING":
        return f"[yellow]RUNNING[/yellow] (pid={code})"
    elif status == "FAIL":
        return f"[red]FAILED[/red] (code={code})"
    elif status == "WAITING":
        return f"[green]WAITING[/green] (on={code})"
    elif status == "UNKNOWN":
        return "[red]UNKNOWN[/red]"
    else:
        return "[green]SUCCESS[/green]"


def task_status_to_table(
    statuses: t.Mapping[str, t.Tuple[str, t.Union[int, str]]]
) -> rich.table.Table:
    t = rich.table.Table(title="Task Status")
    t.add_column("Task")
    t.add_column("Status")
    for task, (status, code) in statuses.items():
        t.add_row(task, _status_code(status, code))
    return t


def task_join(
    ctx: "YoCtx",
    inst: YoInstance,
    wait_tasks: t.Iterable[str] = (),
) -> t.Mapping[str, t.Tuple[str, t.Union[str, int]]]:
    with Live(console=ctx.con) as live:
        task_previous_status: t.Dict[str, t.Tuple[str, t.Union[int, str]]] = {}
        while True:
            status_dict = task_get_status(ctx, inst)
            live.update(task_status_to_table(status_dict))
            any_running = False
            for task, (status, code) in status_dict.items():
                prev_status, prev_code = task_previous_status.get(
                    task, (None, None)
                )
                task_previous_status[task] = status, code
                if not prev_status:
                    live.console.log(
                        f"{task}: starting in status {_status_code(status, code)}",
                        highlight=False,
                    )
                elif prev_status != status or prev_code != code:
                    live.console.log(
                        f"{task}: changing status {_status_code(prev_status, prev_code)} -> {_status_code(status, code)}",
                        highlight=False,
                    )
                if status in ("RUNNING", "WAITING"):
                    any_running = True

            # If we're waiting for no particular task, then we have to wait
            # until all are completed. Otherwise, we wait until just the
            # specific wait_tasks are all completed.
            can_terminate = (not wait_tasks and not any_running) or (
                wait_tasks
                and all(
                    (status_dict[wt][0] not in ("RUNNING", "WAITING"))
                    for wt in wait_tasks
                )
            )
            if can_terminate:
                break
            time.sleep(1)
    return status_dict
