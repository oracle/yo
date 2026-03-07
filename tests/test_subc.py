#!/usr/bin/env python3
import argparse

import yo.subc as subc


def test_wrap_subparser_aliases_adds_hidden_aliases():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    subparsers.add_parser("launch")

    subc._wrap_subparser_aliases(subparsers, {"launch": ["la"]})

    assert "launch" in subparsers.choices
    assert "la" in subparsers.choices
    assert len(subparsers.choices) == 1
    assert list(subparsers.choices) == ["launch"]


def test_unique_prefixes_are_only_unambiguous_prefixes():
    out = subc._unique_prefixes(["launch", "list", "shape"])
    assert out["launch"] == ["la", "lau", "laun", "launc"]
    assert out["list"] == ["li", "lis"]
    assert out["shape"] == ["s", "sh", "sha", "shap"]


def test_command_alias_dispatch():
    class Root(subc.Command):
        rootname = "demo"
        name = "root"
        description = "root"

        def run(self):
            return "root"

    class Delete(Root):
        name = "delete"
        alias = "rm"
        description = "delete"

        def run(self):
            return "deleted"

    assert Root.main("", args=["rm"]) == "deleted"


def test_shortest_prefix_dispatch_top_level():
    class Root(subc.Command):
        rootname = "demo"
        name = "root"
        description = "root"

        def run(self):
            return "root"

    class Launch(Root):
        name = "launch"
        description = "launch"

        def run(self):
            return "launched"

    class List(Root):
        name = "list"
        description = "list"

        def run(self):
            return "listed"

    assert Root.main("", args=["la"], shortest_prefix=True) == "launched"
    assert Root.main("", args=["lis"], shortest_prefix=True) == "listed"


def test_shortest_prefix_dispatch_nested_subcommand():
    class Root(subc.Command):
        rootname = "demo"
        name = "root"
        description = "root"

        def run(self):
            return "root"

    class TaskInfo(Root):
        name = "task info"
        description = "task info"

        def run(self):
            return "info"

    class TaskList(Root):
        name = "task list"
        description = "task list"

        def run(self):
            return "list"

    assert Root.main("", args=["task", "i"], shortest_prefix=True) == "info"
    assert Root.main("", args=["task", "l"], shortest_prefix=True) == "list"


def test_add_commands_supports_user_alias_mapping():
    class Root(subc.Command):
        rootname = "demo"
        name = "root"
        description = "root"

        def run(self):
            return "root"

    class List(Root):
        name = "list"
        description = "list"

        def run(self):
            return "listed"

    parser = argparse.ArgumentParser()
    Root.add_commands(parser, cmd_aliases={"ls": "list"})
    ns = parser.parse_args(["ls"])
    assert ns.func(ns) == "listed"
