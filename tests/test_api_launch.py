#!/usr/bin/env python3
import dataclasses
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from tests.testing.factories import image_factory
from tests.testing.factories import instance_factory
from tests.testing.factories import saved_boot_volume_factory
from tests.testing.factories import shape_factory
from yo.api import ImageCompatibility
from yo.api import InstanceProfile
from yo.api import ShapeMemoryOptions
from yo.api import ShapeOcpuOptions
from yo.api import YoCtx
from yo.util import YoExc


def _make_ctx(tmp_path, **cfg_kwargs):
    cache_file = tmp_path / "yo-cache.json"
    cfg = config_factory(**cfg_kwargs)
    ctx = YoCtx(cfg, {}, cache_file=str(cache_file))
    ctx.con = mock.Mock()
    ctx.clear_cache()
    return ctx


def test_launch_config_mem_cpu_non_flex_no_override(tmp_path):
    ctx = _make_ctx(tmp_path)
    non_flex = shape_factory(
        name="VM.Standard.E2.1.Micro",
        shape="VM.Standard.E2.1.Micro",
        ocpus=1,
        memory_in_gbs=1,
    )
    create_args = {}

    ctx._launch_config_mem_cpu(None, None, non_flex, None, None, create_args)
    assert create_args == {}


def test_launch_config_mem_cpu_rejects_non_flex_cpu_or_mem(tmp_path):
    ctx = _make_ctx(tmp_path)
    non_flex = shape_factory(
        name="VM.Standard.E2.1.Micro",
        shape="VM.Standard.E2.1.Micro",
        ocpus=1,
        memory_in_gbs=1,
    )

    with pytest.raises(YoExc, match="not a flex shape"):
        ctx._launch_config_mem_cpu(None, None, non_flex, 2, None, {})
    with pytest.raises(YoExc, match="not a flex shape"):
        ctx._launch_config_mem_cpu(None, None, non_flex, None, 8, {})


def test_launch_config_mem_cpu_uses_profile_defaults(tmp_path):
    ctx = _make_ctx(tmp_path)
    flex = shape_factory(
        name="VM.Standard.A1.Flex",
        shape="VM.Standard.A1.Flex",
        ocpus=1,
        memory_in_gbs=6,
        is_flexible=True,
        ocpu_options=ShapeOcpuOptions(min=1, max=4),
        memory_options=ShapeMemoryOptions(
            default_per_ocpu_gbs=6,
            min_gbs=6,
            max_gbs=48,
            min_per_ocpu_gbs=1,
            max_per_ocpu_gbs=24,
        ),
    )
    profile = InstanceProfile(
        availability_domain="1",
        shape=flex.name,
        os="Oracle Linux:9",
        cpu=2,
        mem=12,
    )
    create_args = {}

    ctx._launch_config_mem_cpu(profile, None, flex, None, None, create_args)
    assert create_args["shape_config"] == {"ocpus": 2, "memory_in_gbs": 12}


def test_launch_config_mem_cpu_validates_bounds_and_compat(tmp_path):
    ctx = _make_ctx(tmp_path)
    flex = shape_factory(
        name="VM.Standard.A1.Flex",
        shape="VM.Standard.A1.Flex",
        ocpus=1,
        memory_in_gbs=6,
        ocpu_options=ShapeOcpuOptions(min=1, max=4),
        memory_options=ShapeMemoryOptions(
            default_per_ocpu_gbs=6,
            min_gbs=6,
            max_gbs=48,
            min_per_ocpu_gbs=2,
            max_per_ocpu_gbs=16,
        ),
        is_flexible=True,
    )
    img = dataclasses.replace(
        image_factory(name="img-a"),
        compatibility={
            flex.shape: ImageCompatibility(
                shape=flex.shape,
                image_id="imgid",
                min_ocpu=1,
                max_ocpu=2,
                min_mem_gbs=6,
                max_mem_gbs=16,
            )
        },
    )

    with pytest.raises(YoExc, match="CPU selection"):
        ctx._launch_config_mem_cpu(None, None, flex, 8, 16, {})
    with pytest.raises(YoExc, match="mem/CPU ratio"):
        ctx._launch_config_mem_cpu(None, None, flex, 4, 6, {})
    with pytest.raises(YoExc, match="compatible with image"):
        ctx._launch_config_mem_cpu(None, img, flex, 3, 12, {})


def test_launch_config_name_handles_exact_collisions_and_exhaustion(tmp_path):
    ctx = _make_ctx(tmp_path, my_username="alice")
    profile = InstanceProfile(
        availability_domain="1",
        shape="VM.Standard.E2.1.Micro",
        os="Oracle Linux:9",
        name="db",
    )

    with pytest.raises(YoExc, match="did not provide a name"):
        ctx._launch_config_name(profile, None, exact_name=True)
    assert (
        ctx._launch_config_name(profile, "literal", exact_name=True)
        == "literal"
    )

    running = [
        instance_factory(name="alice-db", state="RUNNING"),
        instance_factory(name="alice-db-1", state="RUNNING"),
        instance_factory(name="alice-db-2", state="TERMINATED"),
    ]
    ctx.list_instances = mock.Mock(return_value=running)
    ctx.list_volumes = mock.Mock(
        return_value=[saved_boot_volume_factory("alice-db-2")]
    )

    assert (
        ctx._launch_config_name(profile, "db", exact_name=False, max_tries=10)
        == "alice-db-3"
    )

    ctx.list_instances = mock.Mock(return_value=running[:2])
    ctx.list_volumes = mock.Mock(
        return_value=[
            saved_boot_volume_factory("alice-db-2"),
            saved_boot_volume_factory("alice-db-3"),
        ]
    )
    with pytest.raises(
        YoExc, match="could not come up with a unique instance name"
    ):
        ctx._launch_config_name(profile, "db", exact_name=False, max_tries=2)


def test_launch_config_user_rejects_invalid_username(tmp_path):
    ctx = _make_ctx(tmp_path)
    profile = InstanceProfile(
        availability_domain="1",
        shape="VM.Standard.E2.1.Micro",
        os="Oracle Linux:9",
    )

    with pytest.raises(YoExc, match="custom username"):
        ctx._launch_config_user("opc", "-oProxyCommand=bad", profile)


def test_get_ssh_user_rejects_invalid_username_tag(tmp_path):
    ctx = _make_ctx(tmp_path)
    inst = instance_factory(username="-oProxyCommand=bad")

    with pytest.raises(YoExc, match="yo-username tag"):
        ctx.get_ssh_user(inst)
