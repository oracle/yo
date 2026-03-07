#!/usr/bin/env python3
import sys
from unittest import mock

from yo.main import YoCmd


def test_cache_clean_removes_region_and_legacy_cache_files(
    tmp_path, monkeypatch, mock_cmd_ctx, capsys
):
    monkeypatch.setenv("HOME", str(tmp_path))
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    r1 = cache_dir / "yo.us-ashburn-1.json"
    r2 = cache_dir / "yo.us-phoenix-1.json"
    legacy = cache_dir / "yo.json"
    r1.write_text("{}")
    r2.write_text("{}")
    legacy.write_text("{}")
    mock_cmd_ctx.config.region = "us-ashburn-1"
    mock_cmd_ctx.config.regions = {
        "us-ashburn-1": object(),
        "us-phoenix-1": object(),
    }

    YoCmd.main("", args=["cache-clean"])

    assert not r1.exists()
    assert not r2.exists()
    assert not legacy.exists()
    out = capsys.readouterr().out
    assert "cleaned" in out


def test_version_pip_reports_up_to_date(mock_cmd_ctx, capsys):
    with mock.patch("yo.main.PKGMAN", "pip"), mock.patch(
        "yo.main.current_yo_version", return_value=(1, 2, 3)
    ), mock.patch("yo.main.latest_yo_version", return_value=(1, 2, 3)):
        YoCmd.main("", args=["version"])

    out = capsys.readouterr().out
    assert "yo 1.2.3" in out
    assert "You are up-to-date!" in out


def test_version_non_pip_shows_manager_instructions(mock_cmd_ctx, capsys):
    with mock.patch("yo.main.PKGMAN", "brew"), mock.patch(
        "yo.main.current_yo_version", return_value=(1, 2, 3)
    ):
        YoCmd.main("", args=["version"])

    out = capsys.readouterr().out
    assert "Yo's installation is managed by brew" in out


def test_script_dispatches_with_ctx_and_updates_argv(
    tmp_path, monkeypatch, mock_cmd_ctx
):
    script = tmp_path / "script.py"
    script.write_text("print('hello')")
    monkeypatch.setattr(sys, "argv", ["yo"])

    with mock.patch("yo.main.runpy.run_path") as run_path:
        YoCmd.main("", args=["script", str(script), "arg1", "arg2"])

    run_path.assert_called_once_with(
        str(script),
        init_globals={"ctx": mock_cmd_ctx},
        run_name="__main__",
    )
    assert sys.argv == [str(script), "arg1", "arg2"]
