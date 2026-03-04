#!/usr/bin/env python3
import configparser
import dataclasses
import inspect

import pytest

from tests.testing.factories import config_factory
from yo.util import check_args_dataclass
from yo.util import removesuffix
from yo.util import standardize_name
from yo.util import YoConfig
from yo.util import YoExc
from yo.util import YoRegion


def _yo_section(extra: str = ""):
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read_string(
        inspect.cleandoc(
            f"""
            [yo]
            instance_compartment_id =   ocid1.compartment.oc1..test
            region = us-ashburn-1
            my_email = USER@EXAMPLE.COM
            my_username = testuser
            {extra}
            """
        )
    )
    return parser["yo"]


def _regions(vcn_id: str = "ocid1.vcn.oc1..test"):
    return {
        "us-ashburn-1": YoRegion(
            name="us-ashburn-1",
            vcn_id=vcn_id,
            subnet_id="ocid1.subnet.oc1..test",
        )
    }


def test_yoconfig_from_config_section_parses_fields():
    conf = _yo_section(
        inspect.cleandoc(
            """
            extension_modules = one.mod, two.mod
            image_compartment_ids = ocid1.compartment.oc1..a
                ocid1.compartment.oc1..b
            creator_tags = team-alpha team-beta,team-gamma
            exact_name = true
            resource_filtering = false
            check_for_update_every = 12
            allow_legacy_imds_endpoints = true
            """
        )
    )

    cfg = YoConfig.from_config_section(conf, _regions(), mtime=123.0)
    assert cfg.my_email == "user@example.com"
    assert cfg.instance_compartment_id == "ocid1.compartment.oc1..test"
    assert cfg.extension_modules == ["one.mod", "two.mod"]
    assert cfg.image_compartment_ids == [
        "ocid1.compartment.oc1..a",
        "ocid1.compartment.oc1..b",
    ]
    assert cfg.creator_tags == ["team-alpha", "team-beta", "team-gamma"]
    assert cfg.exact_name is True
    assert cfg.resource_filtering is False
    assert cfg.check_for_update_every == 12
    assert cfg.allow_legacy_imds_endpoints is True


def test_yoconfig_from_config_section_rejects_hash_by_default():
    conf = _yo_section("notify_prog = echo {message} # trailing hash")
    with pytest.raises(YoExc, match="section"):
        YoConfig.from_config_section(conf, _regions(), mtime=1.0)


def test_yoconfig_from_config_section_allows_hash_when_enabled():
    conf = _yo_section(
        inspect.cleandoc(
            """
            allow_hash_in_config_value = true
            notify_prog = echo {message} # allowed
            """
        )
    )
    cfg = YoConfig.from_config_section(conf, _regions(), mtime=1.0)
    assert cfg.notify_prog == "echo {message} # allowed"


def test_yoconfig_from_config_section_rejects_hash_in_regions():
    conf = _yo_section()
    with pytest.raises(YoExc, match="regions.us-ashburn-1"):
        YoConfig.from_config_section(conf, _regions("bad#vcn"), mtime=1.0)


@pytest.mark.parametrize(
    "name,exact_arg,config_exact,expected",
    [
        ("vm1", True, False, "vm1"),
        ("vm1", None, True, "vm1"),
        ("vm1", False, True, "alice-vm1"),
        ("vm1", None, False, "alice-vm1"),
        ("alice-vm1", None, False, "alice-vm1"),
    ],
)
def test_standardize_name_respects_exact_name(
    name, exact_arg, config_exact, expected
):
    cfg = config_factory(my_username="alice", exact_name=config_exact)
    assert standardize_name(name, exact_arg, cfg) == expected


@pytest.mark.parametrize(
    "task_dir,expected",
    [
        ("/tmp/tasks/", "/tmp/tasks"),
        ("~/.cache/yo tasks/", "\"$HOME\"'/.cache/yo tasks'"),
        ("$HOME/tasks/", '"$HOME"/tasks'),
    ],
)
def test_task_dir_safe(task_dir, expected):
    cfg = config_factory(task_dir=task_dir)
    assert cfg.task_dir_safe == expected


def test_removesuffix():
    assert removesuffix("id_rsa.pub", ".pub") == "id_rsa"
    assert removesuffix("id_rsa", ".pub") == "id_rsa"


def test_check_args_dataclass_errors_are_informative():
    @dataclasses.dataclass
    class Demo:
        req: str
        opt: int = 1

    with pytest.raises(YoExc, match='unknown configuration "bad"'):
        check_args_dataclass(Demo, ["req", "bad"], "demo")
    with pytest.raises(YoExc, match="missing required configurations: req"):
        check_args_dataclass(Demo, ["opt"], "demo")
