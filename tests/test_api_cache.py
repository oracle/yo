#!/usr/bin/env python3
import json
import os
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from tests.testing.factories import instance_factory
from yo.api import YoCtx
from yo.api import YoRegionalCtx
from yo.util import YoExc
from yo.util import YoRegion


def _make_ctx(tmp_path, clear: bool = True, **cfg_kwargs):
    cache_file = tmp_path / "yo-cache.json"
    cfg = config_factory(**cfg_kwargs)
    cc = YoCtx(cfg, {})
    cc.con = mock.Mock()
    ctx = YoRegionalCtx(cc, cfg.region, str(cache_file))
    ctx.con = cc.con
    if clear:
        ctx.clear_cache()
    return ctx, cache_file


def test_load_cache_invalidates_when_config_newer(tmp_path):
    cache_file = tmp_path / "yo-cache.json"
    cache_file.write_text("{}")
    os.utime(cache_file, (1, 1))

    cfg = config_factory(mtime=2.0)
    cc = YoCtx(cfg, {})
    cc.con = mock.Mock()
    ctx = YoRegionalCtx(cc, cfg.region, str(cache_file))
    ctx.con = cc.con

    assert not cache_file.exists()
    assert ctx._instances.get_all() == []


def test_load_cache_invalidates_cache_version_mismatch(tmp_path):
    cache_file = tmp_path / "yo-cache.json"
    cache_file.write_text(
        json.dumps(
            {
                "cache_version": 0,
                "resource_filtering": True,
            }
        )
    )
    cfg = config_factory(mtime=0.0, resource_filtering=True)
    cc = YoCtx(cfg, {})
    cc.con = mock.Mock()
    ctx = YoRegionalCtx(cc, cfg.region, str(cache_file))
    ctx.con = cc.con
    ctx.clear_cache()

    assert not cache_file.exists()


def test_load_cache_invalidates_resource_filtering_mismatch(tmp_path):
    ctx1, cache_file = _make_ctx(
        tmp_path,
        mtime=0.0,
        resource_filtering=True,
    )
    ctx1.save_cache()
    ctx1.clear_cache()

    ctx2, _ = _make_ctx(
        tmp_path,
        clear=False,
        mtime=0.0,
        resource_filtering=False,
    )
    ctx2.clear_cache()
    assert not cache_file.exists()


def test_cached_items_get_runtime_region_without_serializing(tmp_path):
    ctx, cache_file = _make_ctx(tmp_path)
    inst = instance_factory()

    ctx._instances.set([inst])

    assert inst.region == ctx.region
    inserted = instance_factory()
    ctx._instances.insert(inserted)
    assert inserted.region == ctx.region
    assert all(
        "region" not in item for item in ctx._instances.export()["cache"]
    )

    ctx.save_cache()
    cache = json.loads(cache_file.read_text())
    assert all("region" not in item for item in cache["instances"]["cache"])

    loaded, _ = _make_ctx(tmp_path, clear=False)
    assert {item.region for item in loaded._instances.get_all()} == {ctx.region}


def test_rc_caches_regional_contexts(tmp_path):
    regions = {
        "r1": YoRegion("r1", "vcn1", "sub1"),
        "r2": YoRegion("r2", "vcn2", "sub2"),
    }
    cfg = config_factory(region="r1", regions=regions)
    ctx = YoCtx(cfg, {}, cache_dir=str(tmp_path))

    r1 = ctx.rc("r1")
    r2 = ctx.rc("r2")

    assert r1 is ctx.rc("r1")
    assert r2 is ctx.rc("r2")
    assert r1.region == "r1"
    assert r2.region == "r2"
    assert r1 is not r2
    assert r1._cache_file == str(tmp_path / "yo.r1.json")
    assert r2._cache_file == str(tmp_path / "yo.r2.json")


def test_rc_requires_known_region(tmp_path):
    regions = {"r1": YoRegion("r1", "vcn1", "sub1")}
    cfg = config_factory(region="r1", regions=regions)
    ctx = YoCtx(cfg, {}, cache_dir=str(tmp_path))
    with pytest.raises(YoExc, match="not configured"):
        ctx.rc("r2")
