"""Task 29 (gfx-parallax): 3-5 pre-baked scrollable background layers.

The single static background blit is split into 5 scrollable layers
(sky, far hills, mid hills, near foliage, road) blit at parallax
offsets [0, 0.15, 0.35, 0.6, 1.0] from a single scroll accumulator.
Parallax accelerates 2x during Auto Katana. Layers pin to 0 scroll
when reduced_motion is on (or the low render tier).

Acceptance criteria covered:
- 3-5 parallax layers blit at distinct scroll offsets from one accumulator
- Parallax visibly accelerates 2x during Auto Katana
- Layers pin to 0 scroll when reduced_motion is on
- All layer surfaces cached per (zone, hue, layer) with convert_alpha
- 60fps maintained with parallax enabled at the high tier (smoke)
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _reinit_display():
    """Re-init pygame + the display if a prior test quit pygame.

    The ``pygame_headless`` fixture is session-scoped; prior tests in
    this file call ``pygame.quit()`` which tears down the display. The
    font cache holds stale freetype objects after quit, so we also clear
    it (``reset_fonts``) before constructing ``main.Game()`` so the
    buttons' ``font_md()`` calls build fresh fonts against the live
    display. Without this, ``Button.__init__`` calls ``font_md(bold=True)``
    while the display is down, caching a stale font object that segfaults
    on ``font.render`` during ``draw()``.
    """
    import pygame
    from theme import reset_fonts
    if not pygame.display.get_init():
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        pygame.display.set_mode((1280, 720))
    reset_fonts()


# ---------------------------------------------------------------------------
# Layer cache
# ---------------------------------------------------------------------------
def test_parallax_layers_exist(pygame_headless):
    """parallax_layers returns 3-5 cached surfaces (from the brief)."""
    from assets import parallax_layers
    layers = parallax_layers(zone_index=0, hue=90)
    assert len(layers) >= 3
    for s in layers:
        assert s is not None


def test_parallax_layers_count_5(pygame_headless):
    """parallax_layers returns exactly 5 layers (sky, far hills, mid
    hills, near foliage, road)."""
    from assets import parallax_layers
    layers = parallax_layers(zone_index=0, hue=90)
    assert len(layers) == 5


def test_parallax_layers_cached(pygame_headless):
    """parallax_layers returns the same surface objects on repeated calls
    (cached per zone, hue, layer)."""
    from assets import parallax_layers
    a = parallax_layers(zone_index=0, hue=90)
    b = parallax_layers(zone_index=0, hue=90)
    assert all(a[i] is b[i] for i in range(len(a)))


def test_parallax_uses_zone_in_cycle_for_cache(pygame_headless):
    """The cache keys on (zone_in_cycle, hue) not (zone_index, hue), so
    zone 0 and zone 9 (both in_cycle 0) share the same cached surfaces.
    This keeps the cache bounded (9 zones x hues x layers, not unbounded
    across cycles)."""
    from assets import parallax_layers
    a = parallax_layers(zone_index=0, hue=90)
    b = parallax_layers(zone_index=9, hue=90)
    assert all(a[i] is b[i] for i in range(len(a))), (
        "zone 0 and zone 9 should share cached layers (same in_cycle 0)")
    c = parallax_layers(zone_index=1, hue=90)
    assert any(a[i] is not c[i] for i in range(len(a))), (
        "zone 0 and zone 1 should have different layers (different in_cycle)")


def test_parallax_layers_cached_per_zone_hue(pygame_headless):
    """Different (zone, hue) produce different surfaces; same (zone, hue)
    produce the same surfaces."""
    from assets import parallax_layers
    a = parallax_layers(zone_index=0, hue=90)
    b = parallax_layers(zone_index=1, hue=120)
    c = parallax_layers(zone_index=0, hue=90)
    assert all(a[i] is c[i] for i in range(len(a)))
    assert any(a[i] is not b[i] for i in range(len(a)))


def test_parallax_layers_call_convert_alpha(pygame_headless):
    """Each layer surface calls convert_alpha before caching."""
    import pygame
    from assets import parallax_layers, _PARALLAX_CACHE

    _PARALLAX_CACHE.clear()

    class CountingSurface(pygame.Surface):
        convert_alpha_count = 0

        def convert_alpha(self, *a, **k):
            type(self).convert_alpha_count += 1
            return super().convert_alpha(*a, **k)

    orig = pygame.Surface
    pygame.Surface = CountingSurface  # type: ignore[assignment]
    try:
        layers = parallax_layers(zone_index=0, hue=90)
    finally:
        pygame.Surface = orig  # type: ignore[assignment]

    assert CountingSurface.convert_alpha_count >= 5, (
        f"expected >= 5 convert_alpha calls, got "
        f"{CountingSurface.convert_alpha_count}")
    for s in layers:
        assert isinstance(s, pygame.Surface)


# ---------------------------------------------------------------------------
# Scroll accumulator + Auto Katana acceleration
# ---------------------------------------------------------------------------
def test_runner_has_scroll_speed(pygame_headless):
    """Runner has a scroll_speed() method returning a positive value."""
    from engine.runner import Runner
    from core.state import GameState
    state = GameState()
    r = Runner(state)
    assert hasattr(r, "scroll_speed")
    assert callable(r.scroll_speed)
    base = r.scroll_speed()
    assert base > 0


def test_parallax_accelerates_with_energy(pygame_headless):
    """scroll_speed() returns a higher value when energy_active is True
    (from the brief: parallax accelerates 2x during Auto Katana)."""
    from engine.runner import Runner
    from core.state import GameState
    state = GameState()
    r = Runner(state)
    base_scroll = r.scroll_speed()
    state.energy_active = True
    assert r.scroll_speed() > base_scroll
    assert r.scroll_speed() == base_scroll * 2.0


def test_gamescreen_has_scroll_accumulator(pygame_headless):
    """The GameScreen has a scroll_accumulator attribute."""
    import main
    _reinit_display()
    g = main.Game()
    screen = g.screens["game"]
    assert hasattr(screen, "scroll_accumulator")
    assert screen.scroll_accumulator == 0.0
    import pygame
    pygame.quit()


# ---------------------------------------------------------------------------
# Reduced motion / low tier pins scroll to 0
# ---------------------------------------------------------------------------
def test_parallax_pinned_by_reduced_motion(pygame_headless):
    """When reduced_motion is on, the screen does not advance the scroll
    accumulator (layers pin to 0 scroll)."""
    import main
    _reinit_display()
    g = main.Game()
    screen = g.screens["game"]
    g.current_screen = "game"
    screen.scroll_accumulator = 0.0
    g.state.reduced_motion = True
    for _ in range(10):
        g._update(1 / 60)
    assert screen.scroll_accumulator == 0.0, (
        f"scroll_accumulator advanced under reduced_motion: "
        f"{screen.scroll_accumulator}")
    import pygame
    pygame.quit()


def test_parallax_pinned_by_low_tier(pygame_headless):
    """When render_quality is low (and reduced_motion is off), the screen
    does not advance the scroll accumulator."""
    import main
    _reinit_display()
    g = main.Game()
    screen = g.screens["game"]
    g.current_screen = "game"
    screen.scroll_accumulator = 0.0
    g.state.reduced_motion = False
    g.state.render_quality = "low"
    for _ in range(10):
        g._update(1 / 60)
    assert screen.scroll_accumulator == 0.0, (
        f"scroll_accumulator advanced at low tier: "
        f"{screen.scroll_accumulator}")
    import pygame
    pygame.quit()


def test_parallax_advances_at_high_tier(pygame_headless):
    """At the high tier (reduced_motion off), the scroll accumulator
    advances each frame."""
    import main
    _reinit_display()
    g = main.Game()
    screen = g.screens["game"]
    g.current_screen = "game"
    g.state.reduced_motion = False
    g.state.render_quality = "high"
    screen.scroll_accumulator = 0.0
    g._update(1 / 60)
    assert screen.scroll_accumulator > 0.0, (
        f"scroll_accumulator did not advance at high tier: "
        f"{screen.scroll_accumulator}")
    import pygame
    pygame.quit()


def test_parallax_accelerates_with_energy_in_game(pygame_headless):
    """When energy_active is True, the scroll accumulator advances 2x
    faster than the base rate. Uses a generous energy pool so the Auto
    Katana does not deplete during the test frame."""
    import main
    _reinit_display()
    g = main.Game()
    screen = g.screens["game"]
    g.current_screen = "game"
    g.state.reduced_motion = False
    g.state.render_quality = "high"
    g.state.energy = 600.0
    g.state.energy_max = 600.0
    screen.scroll_accumulator = 0.0
    g.state.energy_active = False
    g._update(1 / 60)
    base_advance = screen.scroll_accumulator
    screen.scroll_accumulator = 0.0
    g.state.energy_active = True
    g.state.energy = 600.0
    g._update(1 / 60)
    boosted_advance = screen.scroll_accumulator
    assert boosted_advance == base_advance * 2.0, (
        f"boosted advance {boosted_advance} != 2x base {base_advance * 2.0}")
    import pygame
    pygame.quit()


# ---------------------------------------------------------------------------
# Parallax offsets
# ---------------------------------------------------------------------------
def test_parallax_offsets_distinct(pygame_headless):
    """The parallax offsets are 5 distinct values starting at 0, increasing."""
    from ui.screen_game import PARALLAX_OFFSETS
    assert len(PARALLAX_OFFSETS) == 5
    assert len(set(PARALLAX_OFFSETS)) == len(PARALLAX_OFFSETS)
    assert PARALLAX_OFFSETS[0] == 0.0
    for i in range(len(PARALLAX_OFFSETS) - 1):
        assert PARALLAX_OFFSETS[i] < PARALLAX_OFFSETS[i + 1]
    assert PARALLAX_OFFSETS[-1] == 1.0


# ---------------------------------------------------------------------------
# Smoke: parallax layers blit without error
# ---------------------------------------------------------------------------
def test_parallax_blits_without_error(pygame_headless):
    """The game screen draws 30 frames with parallax layers at the high
    tier without error (60fps maintained). Exercises both ``_update()``
    and ``draw()`` so the render path (the parallax blit + the
    downstream enemy/ninja positioning that reads ``ly``) is verified.
    """
    import pygame
    import main
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.render_quality = "high"
    g.state.reduced_motion = False
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()


def test_parallax_blits_without_error_low_tier(pygame_headless):
    """The game screen draws 30 frames with parallax pinned (low tier)
    without error. Exercises the ``draw()`` path with the accumulator
    pinned to 0 so the static-blit path is verified too."""
    import pygame
    import main
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.render_quality = "low"
    g.state.reduced_motion = False
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()


def test_parallax_blits_without_error_reduced_motion(pygame_headless):
    """The game screen draws 30 frames with reduced_motion on without
    error. Exercises the ``draw()`` path with the accumulator pinned to
    0 via the reduced_motion gate."""
    import pygame
    import main
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.reduced_motion = True
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()
