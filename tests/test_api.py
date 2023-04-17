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
import datetime
import typing as t
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from tests.testing.factories import instance_factory
from tests.testing.factories import NOT_MY_EMAIL
from tests.testing.factories import oci_instance_factory
from tests.testing.factories import oci_instance_fromyo
from tests.testing.factories import short_name
from tests.testing.fake_oci import FakeOCI
from tests.testing.rich import FakeTable
from yo.api import now
from yo.api import YoCtx
from yo.util import YoExc


@pytest.fixture
def fake_ctx(tmpdir):
    es = contextlib.ExitStack()
    with es:
        es.enter_context(mock.patch("rich.table.Table", new=FakeTable))
        cache = tmpdir.join("cache.json")
        ctx = YoCtx(config_factory(), {}, cache_file=cache)
        fake = FakeOCI(ctx)
        yield fake, ctx


@pytest.fixture
def ctx(fake_ctx):
    return fake_ctx[1]


@pytest.fixture
def fake(fake_ctx):
    return fake_ctx[0]


def set_cache(
    ctx: YoCtx, kind: str, values: t.List[t.Any], update_age=0, refresh_age=0
):
    under = "_" + kind
    assert under in ctx._caches
    cache = getattr(ctx, under)
    cache.set(values)
    if update_age:
        cache.last_update = now() - datetime.timedelta(seconds=update_age)
    if refresh_age:
        cache.last_refresh = now() - datetime.timedelta(seconds=refresh_age)


def test_list(ctx: YoCtx, fake: FakeOCI):
    fake.compute._instances = [
        oci_instance_factory(created_by=NOT_MY_EMAIL),
        oci_instance_factory(display_name="myinstance1", id="myinstance1"),
        oci_instance_factory(display_name="myinstance2", id="myinstance2"),
    ]
    result = ctx.list_instances()
    fake.compute.list_instances.assert_called_once()
    assert len(result) == 2
    assert result[0].name == "myinstance1"
    assert result[0].id == "myinstance1"
    assert result[1].name == "myinstance2"
    assert result[1].id == "myinstance2"


@pytest.mark.parametrize("short", [True, False])
def test_get_instance_by_name_uncached(ctx, fake, short):
    inst = instance_factory()
    oci_inst = oci_instance_fromyo(inst)
    set_cache(ctx, "instances", [])
    fake.compute._instances = [oci_inst]
    name = short_name(inst.name) if short else inst.name
    assert inst == ctx.get_instance_by_name(name, (), ())
    fake.compute.list_instances.assert_called()
    assert ctx._instances.get_all() == [inst]


@pytest.mark.parametrize("short", [True, False])
def test_get_instance_by_name_cached(ctx, fake, short):
    inst = instance_factory()
    set_cache(ctx, "instances", [inst])
    name = short_name(inst.name) if short else inst.name
    assert inst == ctx.get_instance_by_name(name, (), ())
    fake.compute.list_instances.assert_not_called()


def test_get_instance_by_name_exact_nomatch(ctx, fake):
    # We use a name that's the short name for an existing instance, but use
    # --exact-name. We expect that we'll get an exception and that it will check
    # --the API once the cache lookup fails.
    inst = instance_factory()
    oci_inst = oci_instance_fromyo(inst)
    set_cache(ctx, "instances", [inst])
    sn = short_name(inst.name)
    fake.compute._instances = [oci_inst]
    with pytest.raises(YoExc, match=f"No instance named {sn}"):
        ctx.get_instance_by_name(sn, (), (), exact_name=True)
    fake.compute.list_instances.assert_called_once()


def test_get_instance_by_name_wrong_state_api_correct(ctx, fake):
    # Lookup an instance by shortname, but filter to only RUNNING instances. The
    # cached instance is in state STOPPED, but the true API state is RUNNING. We
    # expect that yo refreshes the instance list, discovers it is running, and
    # returns the updated instance.
    inst = instance_factory(state="STOPPED")
    inst_run = dataclasses.replace(inst, state="RUNNING")
    inst_run_oci = oci_instance_fromyo(inst_run)
    set_cache(ctx, "instances", [inst])
    fake.compute._instances = [inst_run_oci]
    assert inst_run == ctx.get_instance_by_name(
        short_name(inst.name), ("RUNNING"), ()
    )
    fake.compute.list_instances.assert_called_once()


def test_get_instance_by_name_wrong_state(ctx, fake):
    # Lookup an instance by shortname, but filter to only RUNNING instances. The
    # cached instance is in state STOPPED, but the true API state is RUNNING. We
    # expect that yo refreshes the instance list, discovers it is running, and
    # returns the updated instance.
    inst = instance_factory(state="STOPPED")
    inst_run_oci = oci_instance_fromyo(inst)
    set_cache(ctx, "instances", [inst])
    fake.compute._instances = [inst_run_oci]
    # roughly match the error message
    with pytest.raises(
        YoExc,
        match=rf'Instance named "{inst.name}" found, but its state \(STOPPED\)',
    ):
        ctx.get_instance_by_name(short_name(inst.name), ("RUNNING"), ())
    fake.compute.list_instances.assert_called_once()
    fake.compute.get_instance.assert_not_called()


def test_get_instance_by_name_two(ctx, fake):
    # Lookup an instance by shortname, but filter to only RUNNING instances. The
    # cached instance is in state PROVISIONING (but the true API state is
    # RUNNING). Another instance with the same name exists and is in state
    # TERMINATED.  We expect that yo refreshes the instance list, discovers it
    # is running, ignores the old terminated instance, and returns the updated
    # correct instance.
    inst = instance_factory(state="PROVISIONING")
    inst2 = instance_factory(name=inst.name, state="TERMINATED")
    inst_run = dataclasses.replace(inst, state="RUNNING")
    inst_run_oci = oci_instance_fromyo(inst_run)
    inst2_oci = oci_instance_fromyo(inst2)
    set_cache(ctx, "instances", [inst, inst2])
    fake.compute._instances = [inst_run_oci, inst2_oci]
    assert inst_run == ctx.get_instance_by_name(
        short_name(inst.name), ("RUNNING"), ()
    )
    fake.compute.list_instances.assert_called_once()
    fake.compute.get_instance.assert_not_called()
