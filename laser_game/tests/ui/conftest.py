"""Shared pytest fixtures for UI tests.

The tests force pygame into a deterministic headless configuration by using
the SDL ``dummy`` video and audio drivers.  Fonts are initialised via pygame's
default font to avoid platform dependent rasterisation differences.
"""

from __future__ import annotations

import os
from typing import Generator

import pytest


@pytest.fixture(scope="session", autouse=True)
def configure_headless_environment() -> Generator[None, None, None]:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    yield


@pytest.fixture(scope="session")
def pygame_module():
    pygame = pytest.importorskip("pygame")
    pygame.display.init()
    pygame.font.init()
    yield pygame
    pygame.quit()
