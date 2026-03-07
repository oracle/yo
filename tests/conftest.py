#!/usr/bin/env python3
import contextlib
import types
import typing as t
from pathlib import Path
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from tests.testing.rich import FakeTable
from yo.api import YoCtx
from yo.main import YoCmd
from yo.tasks import get_tasklib
from yo.tasks import list_tasks
from yo.tasks import YoTask


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    for rel in (".oci", ".ssh", ".cache"):
        (home / rel).mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture
def write_yo_ini(fake_home: Path) -> t.Callable[[str], Path]:
    def _write(contents: str) -> Path:
        path = fake_home / ".oci" / "yo.ini"
        path.write_text(contents)
        return path

    return _write


@pytest.fixture
def write_oci_config(fake_home: Path) -> t.Callable[[str], Path]:
    def _write(contents: str = "[DEFAULT]\nregion=us-ashburn-1\n") -> Path:
        path = fake_home / ".oci" / "config"
        path.write_text(contents)
        return path

    return _write


@pytest.fixture
def write_ssh_keys(
    fake_home: Path,
) -> t.Callable[[str, str], t.Tuple[Path, Path]]:
    def _write(
        public: str = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDc test@localhost\n",
        private: str = "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n",
    ) -> t.Tuple[Path, Path]:
        priv = fake_home / ".ssh" / "id_rsa"
        pub = fake_home / ".ssh" / "id_rsa.pub"
        priv.write_text(private)
        pub.write_text(public)
        return pub, priv

    return _write


@pytest.fixture(autouse=True)
def clear_task_caches() -> t.Iterator[None]:
    YoTask.load.cache_clear()
    list_tasks.cache_clear()
    get_tasklib.cache_clear()
    yield
    YoTask.load.cache_clear()
    list_tasks.cache_clear()
    get_tasklib.cache_clear()


@pytest.fixture(autouse=True)
def clear_yoctx_class_caches() -> t.Iterator[None]:
    for cache_attr in YoCtx._caches:
        getattr(YoCtx, cache_attr).clear()
    yield
    for cache_attr in YoCtx._caches:
        getattr(YoCtx, cache_attr).clear()


@pytest.fixture
def mock_cmd_ctx() -> t.Iterator[mock.Mock]:
    with contextlib.ExitStack() as es:
        ctx = es.enter_context(mock.patch("yo.main.YoCtx")).return_value
        ctx.config = config_factory()
        ctx.instance_profiles = {
            "DEFAULT": mock.Mock(
                tasks=[],
                install=[],
                availability_domain="1",
            ),
        }
        ctx.con = es.enter_context(
            mock.patch("rich.console.Console", autospec=True)
        ).return_value
        es.enter_context(mock.patch("rich.table.Table", new=FakeTable))
        es.enter_context(
            mock.patch("yo.main.list_tasks", return_value=["prep", "test"])
        )
        YoCmd.c = ctx
        yield ctx


@pytest.fixture
def mock_cmd_boundaries() -> t.Iterator[types.SimpleNamespace]:
    with contextlib.ExitStack() as es:
        ssh_into = es.enter_context(
            mock.patch("yo.main.ssh_into", autospec=True)
        )
        wait_for_ssh_access = es.enter_context(
            mock.patch(
                "yo.main.wait_for_ssh_access",
                autospec=True,
                return_value=True,
            )
        )
        send_notification = es.enter_context(
            mock.patch("yo.main.send_notification", autospec=True)
        )
        yield types.SimpleNamespace(
            ssh_into=ssh_into,
            wait_for_ssh_access=wait_for_ssh_access,
            send_notification=send_notification,
        )
