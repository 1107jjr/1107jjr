"""Shared pytest fixtures for UI tests.

The tests force pygame into a deterministic headless configuration by using
the SDL ``dummy`` video and audio drivers.  Fonts are initialised via pygame's
default font to avoid platform dependent rasterisation differences.
"""

from __future__ import annotations

import os
from importlib import util
from pathlib import Path
from typing import Generator

import pytest
import sys


os.environ.setdefault("LASER_GAME_FORCE_PYGAME_STUB", "1")
_STUB_PATH = Path(__file__).resolve().parents[3] / "pygame" / "__init__.py"


def _import_pygame_stub():
    spec = util.spec_from_file_location("pygame", _STUB_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - safety net
        raise RuntimeError("Unable to load pygame stub for UI tests.")
    module = util.module_from_spec(spec)
    sys.modules["pygame"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Remove the partially initialised module so later imports can recover.
        sys.modules.pop("pygame", None)
        raise
    return module


@pytest.fixture(scope="session", autouse=True)
def configure_headless_environment() -> Generator[None, None, None]:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    yield


@pytest.fixture(scope="session")
def pygame_module():
    pygame = _import_pygame_stub()
    pygame.display.init()
    pygame.font.init()
    try:
        yield pygame
    finally:
        pygame.quit()
