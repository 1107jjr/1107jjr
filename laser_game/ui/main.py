"""Entry point helpers for the optional Laser Game UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ASSET_ENV_VAR = "LASER_GAME_ASSET_ROOT"
LEVEL_ENV_VAR = "LASER_GAME_LEVEL_ROOT"


@dataclass(frozen=True)
class UIDirectories:
    """Bundle with resolved directories required by the UI."""

    asset_root: Path
    level_root: Path


def _default_asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def _default_level_root() -> Path:
    return Path(__file__).resolve().parents[1] / "levels"


def _read_directory(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value).expanduser()
    return fallback


def resolve_directories(check_exists: bool = True) -> UIDirectories:
    """Resolve UI directories using environment variables.

    Parameters
    ----------
    check_exists:
        When *True*, raise :class:`FileNotFoundError` if a resolved directory does
        not exist on disk. Disable this in contexts where you want to inspect the
        chosen paths without touching the filesystem.
    """

    asset_root = _read_directory(ASSET_ENV_VAR, _default_asset_root())
    level_root = _read_directory(LEVEL_ENV_VAR, _default_level_root())

    if check_exists:
        missing = [path for path in (asset_root, level_root) if not path.exists()]
        if missing:
            missing_str = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(
                f"Required UI resource directories do not exist: {missing_str}"
            )

    return UIDirectories(asset_root=asset_root, level_root=level_root)


def main() -> UIDirectories:
    """Return resolved directories and print a short bootstrap message."""

    directories = resolve_directories()
    message = (
        "Laser Game UI bootstrap\n"
        f"  assets: {directories.asset_root}\n"
        f"  levels: {directories.level_root}\n"
        "Set the environment variables to point to custom directories if needed."
    )
    print(message)
    return directories


if __name__ == "__main__":  # pragma: no cover - manual invocation entry point
    main()
