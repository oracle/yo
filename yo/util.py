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
import configparser
import dataclasses
import datetime
import os.path
import re
import shlex
import typing as t
import urllib.request
from pathlib import Path

T = t.TypeVar("T")


class YoExc(Exception):
    pass


def opt_strlist(opts: t.Dict[str, t.Any], field: str) -> None:
    """
    Helper for parsing string lists in the yo.ini config file.

    Allows strings to be delimited by commas and/or whitespace, including
    newlines. If the field exists, split it into a list and set that on the
    dictionary. Otherwise, do nothing at all.

    :param opts: option dict
    :param field: name of field
    """
    val = t.cast(t.Optional[str], opts.get(field))
    if val:
        opts[field] = re.split(r"[,\s]+", val.strip(), flags=re.M)


@dataclasses.dataclass
class YoConfig:
    instance_compartment_id: str
    vcn_id: str
    region: str
    my_email: str
    my_username: str
    subnet_id: t.Optional[str] = None
    subnet_compartment_id: t.Optional[str] = None
    ssh_public_key: str = "~/.ssh/id_rsa.pub"
    rsync_args: t.Optional[str] = None
    vnc_prog: str = "krdc vnc://{host}:{port}"
    notify_prog: t.Optional[str] = None
    oci_profile: str = "DEFAULT"
    preserve_volume_on_terminate: t.Optional[bool] = None
    ssh_args: t.Optional[str] = None
    ssh_interactive_args: t.Optional[str] = None
    rdp_prog: t.Optional[str] = None
    extension_modules: t.List[str] = dataclasses.field(default_factory=list)
    task_dir: str = "/tmp/tasks"
    image_compartment_ids: t.List[str] = dataclasses.field(default_factory=list)
    silence_automatic_tag_warning: t.Optional[bool] = None
    exact_name: t.Optional[bool] = None
    resource_filtering: bool = True
    check_for_update_every: t.Optional[int] = 6
    creator_tags: t.List[str] = dataclasses.field(default_factory=list)

    @property
    def ssh_public_key_full(self) -> str:
        path = os.path.expanduser(self.ssh_public_key)
        return open(path).read()

    @property
    def task_dir_safe(self) -> str:
        """
        Return the task_dir processed for insertion into a shell script.

        The task_dir may start with the string "$HOME" or "~", in which case the
        path will be prefixed by the home directory. However, this is a special case
        handled by yo, and there is no further shell processing allowed on the
        task_dir: its value will be escaped for inclusion in the shell script. For
        insertion into the script, this value should be used as-is, without any
        quotes around it. The best way to do so is to insert a bash variable, and
        then use the best practices of quoting bash variables for the remainder of
        the script.

            dir={value_returned_from_this_function}
            echo "$dir"

        :param task_dir: the configured task_dir
        :returns: a final escaped shell token that represents the task_dir
        """
        task_dir = self.task_dir.rstrip("/")
        use_home = False
        if task_dir.startswith("~"):
            use_home = True
            task_dir = task_dir[1:]
        elif task_dir.startswith("$HOME"):
            use_home = True
            task_dir = task_dir[5:]
        task_dir = shlex.quote(task_dir)
        if use_home:
            task_dir = '"$HOME"' + task_dir
        return task_dir

    @property
    def ssh_private_key(self) -> t.Union[Path, None]:
        private_key = Path(removesuffix(self.ssh_public_key, ".pub"))
        private_key = private_key.expanduser()
        if private_key.exists():
            return private_key
        else:
            return None

    @classmethod
    def from_config_section(cls, conf: configparser.SectionProxy) -> "YoConfig":
        d = dict(**conf)
        check_args_dataclass(cls, d.keys(), "~/.oci/yo.ini \\[yo] section")
        bools = [
            "preserve_volume_on_terminate",
            "silence_automatic_tag_warning",
            "exact_name",
            "resource_filtering",
        ]
        for b in bools:
            if b in d:
                d[b] = conf.getboolean(b)
        if "check_for_update_every" in d:
            d["check_for_update_every"] = int(d["check_for_update_every"])
        # OCI stores email addresses as lower case. While most people write
        # their email address in lower case, it's not a guarantee. Since we use
        # email address to filter OCI resources, it's imperative that the casing
        # match. To be safe, lower-case the email.
        d["my_email"] = d["my_email"].lower()
        opt_strlist(d, "extension_modules")
        opt_strlist(d, "image_compartment_ids")
        opt_strlist(d, "creator_tags")
        return YoConfig(**d)

    @property
    def all_creator_tags(self) -> t.Set[str]:
        if not hasattr(self, "_all_creator_tags"):
            self._all_creator_tags = set(
                [self.my_email, f"oracle/{self.my_email}", self.my_username]
                + self.creator_tags
            )
        return self._all_creator_tags


def check_args_dataclass(
    klass: t.Any, args: t.Iterable[str], name: str
) -> None:
    """
    Check whether required args are present, and raise error for unknown.

    Dataclasses are pretty nice, but just passing user configuration dicts
    directly into their constructors will result in bad error messages for
    users. This function can check for missing required arguments or unknown
    arguments, and raise a pretty error.
    """
    optional = set()
    required = set()
    for field in dataclasses.fields(klass):
        if (
            field.default == dataclasses.MISSING
            and field.default_factory == dataclasses.MISSING
        ):
            required.add(field.name)
        else:
            optional.add(field.name)

    for arg in args:
        if arg in required:
            required.remove(arg)
        elif arg in optional:
            continue
        else:
            raise YoExc(f'In {name}: unknown configuration "{arg}"')
    if required:
        missing = ", ".join(required)
        raise YoExc(f"In {name}: missing required configurations: {missing}")


def one(items: t.List[T], nonemsg: str, multiplemsg: str) -> T:
    if len(items) == 0:
        raise YoExc(nonemsg)
    elif len(items) > 1:
        raise YoExc(multiplemsg)
    return items[0]


def standardize_name(
    name: str, exact_name: t.Optional[bool], config: YoConfig
) -> str:
    # When --exact-name is given on the CLI, return name unchanged.
    if exact_name:
        return name
    # When neither --exact-name nor --no-exact-name are given, but the config contains
    # an exact_name configuration that's true, return the name unchanged.
    # This means that an explicit --no-exact-name (exact_name == False) will fail this
    # test and continue with the logic.
    if exact_name is None and config.exact_name:
        return name
    pfx = f"{config.my_username}-"
    if not name.startswith(pfx):
        name = pfx + name
    return name


def fmt_allow_deny(allow: t.Collection[str], deny: t.Collection[str]) -> str:
    if not allow:
        fmt = "any"
    else:
        fmt = "[{}]".format(", ".join(allow))
    if deny:
        fmt += " except [{}]".format(", ".join(deny))
    return fmt


def strftime(dt: datetime.datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def removesuffix(string: str, suffix: str) -> str:
    """
    If string ends with suffix, return it without the suffix.
    Replaces str.removesuffix() which is added in Python 3.9.
    """
    if string.endswith(suffix):
        return string[: len(string) - len(suffix)]
    return string


def shlex_join(args: t.Iterable[str]) -> str:
    return " ".join(shlex.quote(s) for s in args)


PYPI_URL = "https://pypi.org/simple/yo/"
UPGRADE_COMMAND = "pip install --upgrade yo"


def latest_yo_version() -> t.Optional[t.Tuple[int, int, int]]:
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=5) as response:
            html = response.read().decode("utf-8")
        expr = re.compile(r"yo-(\d+)\.(\d+)\.(\d+)")
        return max(
            [
                (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                for m in expr.finditer(html)
            ]
        )
    except Exception:
        return None


def current_yo_version() -> t.Tuple[int, int, int]:
    import pkg_resources

    ver_str = pkg_resources.get_distribution("yo").version
    g1, g2, g3 = ver_str.split(".")
    return (int(g1), int(g2), int(g3))
