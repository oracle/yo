#!/usr/bin/env python3
import json
import os
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from yo.api import YoCtx
from yo.util import YoExc
from yo.util import YoRegion


def _make_ctx(tmp_path, clear: bool = True, **cfg_kwargs):
    cache_file = tmp_path / "yo-cache.json"
    cfg = config_factory(**cfg_kwargs)
    ctx = YoCtx(cfg, {}, cache_file=str(cache_file))
    ctx.con = mock.Mock()
    if clear:
        ctx.clear_cache()
    return ctx, cache_file


def test_load_cache_invalidates_when_config_newer(tmp_path):
    cache_file = tmp_path / "yo-cache.json"
    cache_file.write_text("{}")
    os.utime(cache_file, (1, 1))

    cfg = config_factory(mtime=2.0)
    ctx = YoCtx(cfg, {}, cache_file=str(cache_file))
    ctx.con = mock.Mock()

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
    ctx = YoCtx(cfg, {}, cache_file=str(cache_file))
    ctx.con = mock.Mock()
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


def test_switch_region_reloads_clients_and_cache(tmp_path):
    regions = {
        "r1": YoRegion("r1", "vcn1", "sub1"),
        "r2": YoRegion("r2", "vcn2", "sub2"),
    }
    ctx, _ = _make_ctx(tmp_path, region="r1", regions=regions)
    ctx._oci = object()

    with mock.patch.object(ctx, "_setup_oci") as setup_oci, mock.patch.object(
        ctx, "clear_cache"
    ) as clear_cache, mock.patch.object(ctx, "load_cache") as load_cache:
        ctx.switch_region("r2")

    assert ctx.config.region == "r2"
    assert "yo.r2.json" in ctx._cache_file
    setup_oci.assert_called_once()
    clear_cache.assert_called_once()
    load_cache.assert_called_once()


def test_switch_region_requires_known_region(tmp_path):
    regions = {"r1": YoRegion("r1", "vcn1", "sub1")}
    ctx, _ = _make_ctx(tmp_path, region="r1", regions=regions)
    with pytest.raises(YoExc, match="not configured"):
        ctx.switch_region("r2")
