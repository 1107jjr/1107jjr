from __future__ import annotations

from pathlib import Path

import pytest

from laser_game.ui.main import (
    ASSET_ENV_VAR,
    LEVEL_ENV_VAR,
    UIDirectories,
    main,
    resolve_directories,
)


def test_resolve_directories_returns_package_defaults():
    directories = resolve_directories()

    assert isinstance(directories, UIDirectories)
    assert directories.asset_root.exists()
    assert directories.level_root.exists()


def test_resolve_directories_honours_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    asset_dir = tmp_path / "assets"
    level_dir = tmp_path / "levels"
    asset_dir.mkdir()
    level_dir.mkdir()

    monkeypatch.setenv(ASSET_ENV_VAR, str(asset_dir))
    monkeypatch.setenv(LEVEL_ENV_VAR, str(level_dir))

    directories = resolve_directories()

    assert directories.asset_root == asset_dir
    assert directories.level_root == level_dir


def test_resolve_directories_errors_on_missing_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    asset_dir = tmp_path / "does_not_exist"
    level_dir = tmp_path / "missing_levels"

    monkeypatch.setenv(ASSET_ENV_VAR, str(asset_dir))
    monkeypatch.setenv(LEVEL_ENV_VAR, str(level_dir))

    with pytest.raises(FileNotFoundError):
        resolve_directories()


def test_main_prints_message(capsys: pytest.CaptureFixture[str]):
    directories = main()
    output = capsys.readouterr().out

    assert "Laser Game UI bootstrap" in output
    assert str(directories.asset_root) in output
    assert str(directories.level_root) in output
