"""Shared pytest fixtures and headless-environment setup for Tap Ninja tests.

These env vars MUST be set before `pygame` is imported anywhere, because
pygame reads them once at `pygame.init()` / `pygame.display.set_mode()`.
`setdefault` keeps the value from the shell (e.g. an explicit
`SDL_VIDEODRIVER=dummy pytest ...`) while still working when the shell
omits it.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="session")
def pygame_headless():
    """Initialise pygame once for the whole session on a dummy 1280x720 surface.

    Tests that need a live screen can use this fixture; the smoke test in
    `test_smoke.py` constructs `Game()` directly (which calls
    `pygame.display.set_mode` itself), so it does not need this fixture —
    but later tasks may.
    """
    import pygame
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass
    screen = pygame.display.set_mode((1280, 720))
    yield pygame
    pygame.quit()
