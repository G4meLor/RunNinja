"""Headless smoke test: the game constructs and ticks 30 frames without error.

This is the canary for the whole test harness — if this fails, every later
task's tests will fail too. It must run under `SDL_VIDEODRIVER=dummy` (set
either on the command line or by `conftest.py`).
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def test_game_constructs_and_runs_30_frames():
    """Construct `Game()` headless and run 30 frames of `_update(1/60)`."""
    import main
    g = main.Game()
    for _ in range(30):
        g._update(1 / 60)
    # No exception = pass; assert the core attributes are wired.
    assert g.state is not None
    assert g.runner is not None
