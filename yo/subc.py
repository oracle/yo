#!/usr/bin/env python3
"""
A simple sub-command library for writing rich CLIs
"""
import argparse
import collections
import typing as t
from abc import ABC
from abc import abstractproperty
from abc import abstractmethod


def _first_different(s1: str, s2: str) -> int:
    """
    Return index of the first different character in s1 or s2. If the strings
    are the same, raises a ValueError.
    """
    for i, (c1, c2) in enumerate(zip(s1, s2)):
        if c1 != c2:
            return i
    if len(s1) == len(s2):
        raise ValueError(f"Duplicate string {s1!r} is not allowed")
    return i + 1


def _unique_prefixes(strings: t.Iterable[str]) -> t.Dict[str, t.List[str]]:
    """
    Helper to find a list of unique prefixes for each string in strings.

    Return a dict mapping each string to a list of prefixes which are unique
    among all other strings within the list. Here is an example:

        >>> _unique_prefixes(["commit", "count", "apply", "app", "shape"])
        {'app': [],
         'apply': ['appl'],
         'commit': ['com', 'comm', 'commi'],
         'count': ['cou', 'coun'],
         'launch': ['la', 'lau', 'laun', 'launc'],
         'list': ['li', 'lis'],
         'shape': ['s', 'sh', 'sha', 'shap']}
    """
    strings = sorted(strings)
    diffs = [0] * len(strings)
    for i, (s1, s2) in enumerate(zip(strings, strings[1:])):
        common = _first_different(s1, s2)
        diffs[i] = max(diffs[i], common)
        diffs[i + 1] = max(diffs[i + 1], common)
    return {
        s: [s[:i] for i in range(x + 1, len(s))]
        for (s, x) in zip(strings, diffs)
    }


class _SneakyDict(collections.UserDict):
    """
    A dictionary which can have "hidden" keys that only show up if you know
    about them. The keys are just aliases to other keys. They show up with
    "getitem" and "contains" operations, but not in list / len operations.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases = {}

    def __getitem__(self, key):
        key = self._aliases.get(key, key)
        return super().__getitem__(key)

    def __contains__(self, key):
        key = self._aliases.get(key, key)
        return super().__contains__(key)

    def add_aliases(self, alias_map: t.Dict[str, t.List[str]]):
        alias_to_name = {a: n for n, l in alias_map.items() for a in l}
        self._aliases.update(alias_to_name)


def _wrap_subparser_aliases(
        option: argparse._SubParsersAction,
        alias_map: t.Dict[str, t.List[str]]
) -> None:
    """
    Unfortunately, this mucks around with an internal implementation of
    argparse. However, the API seems pretty stable, and I hope to catch any
    compatibility issues with testing on each new version.

    The "choices" and "_name_parser_map" fields are used to determine which
    subcommands are allowed, and also to list out all of the subcommands for the
    help output (or even to generate completions with something like
    argcomplete).

    For the purposes of lookup (or membership testing), we want the aliases to
    be reflected in these variables. But for the purposes of listing, the
    aliases should be hidden. Thus, use a the _SneakyDict from above to hide the
    aliases.
    """
    new_choices = _SneakyDict(option.choices)
    new_choices.add_aliases(alias_map)
    option.choices = new_choices  # type: ignore
    option._name_parser_map = option.choices


T = t.TypeVar("T", bound="Command")
F = t.TypeVar("F", bound=argparse.HelpFormatter)


class Command(ABC):
    """
    A simple class for implementing sub-commands in your command line
    application. Create a subclass for your app as follows:

        class MyCmd(subc.Command):
            rootname = "mycmd"

    Then, each command in your app can subclass this, implementing the three
    required fields:

        class HelloWorld(MyCmd):
            name = 'hello-world'
            description = 'say hello'
            def run(self):
                print('hello world')

    Finally, use your app-level subclass for creating an argument parser:

        def main():
            parser = argparse.ArgumentParser(description='a cool tool')
            MyCmd.add_commands(parser)
            args = parser.parse_args()
            args.func(args)

    Optional properties of the command:

    - help_formatter_class: used to specify how argparse formats help
    - group: used to categorize commands into groups
    - help: used as a short description (fallback to description)
    - alias: used as an optional alias for this command (in case you rename it)
    """

    @property
    def help_formatter_class(self) -> t.Type[F]:
        return argparse.HelpFormatter

    @abstractproperty
    def name(self) -> str:
        """A field or property which is used for the command name argument"""

    @abstractproperty
    def description(self) -> str:
        """A field or property which is used as the help/description"""

    def add_args(self, parser: argparse.ArgumentParser):
        pass  # default is no arguments

    @abstractmethod
    def run(self) -> t.Any:
        """Function which is called for this command."""

    def base_run(self, args: argparse.Namespace):
        self.args = args
        return self.run()

    @classmethod
    def iter_commands(cls: t.Type[T]) -> t.Iterator[T]:
        """
        Iterate over all sub-commands of the root parser

        This function yields an instance subclass which subc will consider a
        "command" that is, only leaf classes in the hierarchy. You can use this
        if you want to do some sort of operation on each command, e.g.
        generating documentation.
        """
        subclasses = collections.deque(cls.__subclasses__())
        while subclasses:
            subcls = subclasses.popleft()
            this_node_subclasses = subcls.__subclasses__()
            if this_node_subclasses:
                # Assume that any class with children is not executable. Add
                # its children to the queue (BFS) but do not instantiate it.
                subclasses.extend(this_node_subclasses)
            else:
                yield subcls()

    def simple_sub_parser(self) -> argparse.ArgumentParser:
        """
        Return a simple argument parser for this sub-command

        This function returns an argument parser which could be used to parse
        arguments for this sub-command. It's not the same as the parser you get
        if you were to use the root command with add_commands() - but it's good
        if you'd like to only execute this one command, or if you'd like to
        create a parser for use by documentation generators like
        sphinx-argparse.
        """
        if hasattr(self, "rootname"):
            prog = f"{self.rootname}"
        else:
            prog = self.name
        parser = argparse.ArgumentParser(
            prog=prog,
            description=self.description,
            formatter_class=self.help_formatter_class,
        )
        self.add_args(parser)
        return parser

    @classmethod
    def add_commands(
        cls,
        parser: argparse.ArgumentParser,
        default: t.Optional[str] = None,
        shortest_prefix: bool = False,
        cmd_aliases: t.Optional[t.Mapping[str, str]] = None,
        group_order: t.Optional[t.List[str]] = None,
    ) -> argparse.ArgumentParser:
        """
        Add all subcommands which are descendents of this class to parser.

        This call is required in order to setup an argument parser before
        parsing args and executing sub-command. Each sub-command must be a
        sub-class (or a further descendent) of this class. Only leaf subclasses
        are considered commands -- internal "nodes" in the hierarchy are skipped
        as they are assumed to be helpers.

        A default command to run may be set with 'default'. When the argument
        parser is called without a sub-command, this command will automatically
        execute (rather than simply raising an Exception).

        Shortest prefix sub-command matching allows the user to select a
        sub-command by using any string which is a prefix of exactly one
        command, e.g. "git cl" rather than "git clone". This is useful whenever
        there is a small, unchanging set of sub-commands, as a user can develop
        muscle memory for prefixes. However, if the set of sub-commands changes
        over time, then users may develop muscle-memory for a prefix which
        becomes ambiguous with a new command. Thus, it may be preferable to
        allow users to specify their own alias list. You can setup shortest
        prefix aliases and also user-specified aliases with this function, even
        simultaneously if you'd like.

        :param parser: Argument parser which is already created for this app
        :param default: Name of the command which should be executed if none is
          selected
        :param shortest_prefix: Enable shortest prefix command matching
        :param cmd_aliases: User-provided alias list in the form
          {"alias": "true name"}.
        :param group_order: Ordering of the groups in display
        :returns: the modified parser (this can be ignored)
        """
        default_set = False
        subparsers = parser.add_subparsers(
            help=argparse.SUPPRESS, metavar="SUB-COMMAND",
        )
        parser.formatter_class = argparse.RawTextHelpFormatter
        to_add = list(cls.iter_commands())

        # Groups are for the help display, we will group the subcommands with
        # this and then output each one in a section.
        groups = collections.defaultdict(list)

        # Subcmds are for an added level of sub-command. For example, if subc is
        # used for "prog subcommand", then this would allow "prog level1 level2"
        # commands. We don't (yet) go further than this.
        subcmds = collections.defaultdict(list)

        # These are the names which actually would get considered for the unique
        # prefix operation. It will exclude the sub-sub-command names.
        names = []

        # These are the aliases defined by each command, e.g. in case they have
        # some other name for compatibility with previous versions of a tool.
        # This will be extended with the users cmd_aliases if provided.
        # ALIAS -> TRUE NAME
        aliases = {}

        max_len = 0

        for cmd in to_add:
            base_name = cmd.name
            max_len = max(max_len, len(cmd.name))
            if " " in cmd.name:
                base_name = cmd.name.replace(" ", "-")
                sub, rem = cmd.name.split(" ", 1)
                subcmds[sub].append((rem, cmd))
            else:
                # Only include in shortest prefix mappings if it's not
                # a sub-sub-command.
                names.append(cmd.name)

            cmd_parser = subparsers.add_parser(
                base_name,
                description=cmd.description,
                formatter_class=cmd.help_formatter_class,
            )
            cmd.add_args(cmd_parser)
            cmd_parser.set_defaults(func=cmd.base_run)
            if hasattr(cmd, "alias"):
                names.append(cmd.alias)
                aliases[cmd.alias] = base_name

            groups[getattr(cmd, "group", "")].append(cmd)

            if cmd.name == default:
                parser.set_defaults(func=cmd.base_run)
                default_set = True

        for subcmd, cmdlist in subcmds.items():
            subcmd_parser = subparsers.add_parser(subcmd)
            subcmd_subp = subcmd_parser.add_subparsers(
                title="sub-command", metavar="SUB-COMMAND",
            )
            sub_names = []
            names.append(subcmd)
            subcmd_parser.set_defaults(_sub=subcmd_parser)
            subcmd_parser.set_defaults(func=lambda ns: ns._sub.print_help())
            for name, cmd in cmdlist:
                sub_names.append(name)
                cmd_parser = subcmd_subp.add_parser(
                    name,
                    help=getattr(cmd, "help", cmd.description),
                    description=cmd.description,
                    formatter_class=cmd.help_formatter_class,
                )
                cmd.add_args(cmd_parser)
                cmd_parser.set_defaults(func=cmd.base_run)
            if shortest_prefix:
                sub_inv_aliases = _unique_prefixes(sub_names)
                _wrap_subparser_aliases(subcmd_subp, sub_inv_aliases)

        if cmd_aliases:
            names.extend(cmd_aliases)
            aliases.update(cmd_aliases)

        inv_aliases = collections.defaultdict(list)
        if shortest_prefix:
            inv_aliases.update(_unique_prefixes(names))
        for name, target in aliases.items():
            if " " in target:
                # allow alias to a subcommand
                target = target.replace(" ", "-")
            inv_aliases[target].append(name)
            inv_aliases[target].extend(inv_aliases.pop(name, []))
        _wrap_subparser_aliases(subparsers, inv_aliases)

        if not group_order:
            group_order = sorted(groups)
        lines = []
        for group in group_order:
            cmds = groups[group]
            if group:
                lines.append(group)
            for cmd in cmds:
                help = getattr(cmd, "help", cmd.description.strip())
                lines.append(f"{cmd.name.ljust(max_len)} {help}")
            lines.append("")

        parser.epilog = "\n".join(lines[:-1])

        if not default_set:
            def default_func(*args, **kwargs):
                raise Exception('you must select a sub-command')
            parser.set_defaults(func=default_func)
        return parser

    @classmethod
    def main(
            cls,
            description: str,
            default: t.Optional[str] = None,
            args: t.Optional[t.List[str]] = None,
            shortest_prefix: bool = False,
    ) -> t.Any:
        """
        Parse arguments and run the selected sub-command.

        This helper function is expected to be the main, most useful API for
        subc, although you could directly call the add_commands() method.
        Creates an argument parser, adds every discovered sub-command, parses
        the arguments, and executes the selected sub-command, returning its
        return value.

        Custom arguments (rather than sys.argv) can be specified using "args".
        Details on the arguments "default" and "shortest_prefix" can be found
        in the docstring for add_commands().

        :param description: Description of the application (for help output)
        :param default: Default command name
        :param args: If specified, a list of args to use in place of sys.argv
        :param shortest_prefix: whether to enable prefix matching
        :returns: Return value of the selected command's run() method
        """
        parser = argparse.ArgumentParser(description=description)
        cls.add_commands(
            parser, default=default, shortest_prefix=shortest_prefix,
        )
        ns = parser.parse_args(args=args)
        return ns.func(ns)
