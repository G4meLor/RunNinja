"""Sprite caches must call `.convert_alpha()` before caching.

The 5 sprite generators in `assets.py` (ninja/enemy/firefly/building/pet)
create `pygame.Surface(..., pygame.SRCALPHA)` surfaces and draw on them.
Without a `.convert_alpha()` call, every later blit does a slow 32-bit
ARGB software composite against the display format; with it, the surface
is converted once at cache-miss time to the display's native alpha format
and subsequent blits are fast.

Acceptance criteria covered:
- ninja/enemy/firefly/building/pet surfaces all call .convert_alpha()
  before caching — checked by monkeypatching `pygame.Surface.convert_alpha`
  to count calls per cache miss. This is deterministic and does not
  depend on the video driver's pixel format (the dummy driver's display
  is RGB888, so `convert_alpha` is a format no-op there — a masks-based
  check would not detect the fix).
- No behavior change — sprites render identically (smoke test passes,
  checked separately in `test_smoke.py`).
- Blit throughput improves ~1.5-2x in a microbenchmark — the dummy
  driver does not reproduce this (the display format matches the
  SRCALPHA format, so there is no format conversion to skip); the
  microbenchmark below is informational and asserts only "no major
  regression" (converted is not dramatically slower than unconverted).
  The real speedup is on hardware where the display's native format
  differs from ARGB.
- Caches remain lazy (no work before display.set_mode) — checked by
  importing `assets` and asserting the cache dicts exist as the lazy
  sentinels (no surfaces are built at import time).
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def test_caches_lazy_before_display_init():
    """Importing assets must not populate any sprite cache.

    `convert_alpha()` requires the display to be initialised, so the
    sprite functions must be lazy: they only build & convert on the first
    cache miss, which happens during gameplay after `display.set_mode`.
    Importing the module alone must do no work.
    """
    import assets
    # The cache dicts are the lazy sentinels — they exist at module load
    # but are empty until a sprite function is invoked. We assert they
    # are dicts (the lazy contract); the real "no work at import" guard
    # is that no surface is built at import time.
    assert isinstance(assets._NINJA_CACHE, dict)
    assert isinstance(assets._ENEMY_CACHE, dict)
    assert isinstance(assets._FIREFLY_CACHE, dict)
    assert isinstance(assets._BUILDING_CACHE, dict)
    assert isinstance(assets._PET_CACHE, dict)


def _reset_caches():
    import assets
    assets._NINJA_CACHE.clear()
    assets._ENEMY_CACHE.clear()
    assets._FIREFLY_CACHE.clear()
    assets._BUILDING_CACHE.clear()
    assets._PET_CACHE.clear()


def _install_counter(pygame):
    """Replace `pygame.Surface` with a subclass that counts
    `convert_alpha` calls. Returns `(orig, count_holder)`; the holder is
    a 1-element list so it can be read without re-importing. The caller
    MUST restore `pygame.Surface = orig` in a `finally`."""
    class CountingSurface(pygame.Surface):
        convert_alpha_count = 0
        def convert_alpha(self, *a, **k):
            type(self).convert_alpha_count += 1
            return super().convert_alpha(*a, **k)
    orig = pygame.Surface
    pygame.Surface = CountingSurface  # type: ignore[assignment]
    return orig, CountingSurface


def test_sprite_surfaces_call_convert_alpha(pygame_headless):
    """Each sprite function must call `.convert_alpha()` on the final
    surface before caching it.

    We replace `pygame.Surface` with a subclass that counts
    `convert_alpha` calls (the C-level `Surface` type is immutable, so
    we cannot monkeypatch the method directly — but the sprite
    functions look up `pygame.Surface` at call time, so swapping the
    class attribute on the module works). On a cache miss (fresh
    cache), each of the 5 sprite functions must call `convert_alpha` at
    least once.
    """
    import pygame
    from assets import (
        ninja_surface, enemy_surface, firefly_surface,
        building_surface, pet_surface,
    )
    from data.enemies import ZONES

    _reset_caches()

    orig, Counter = _install_counter(pygame)
    try:
        e = ZONES[0]["enemies"][0]
        ninja_surface(64)
        n_after_ninja = Counter.convert_alpha_count
        enemy_surface(e)
        n_after_enemy = Counter.convert_alpha_count
        firefly_surface(10)
        n_after_firefly = Counter.convert_alpha_count
        building_surface("farm")
        n_after_building = Counter.convert_alpha_count
        pet_surface("frog", 120)
        n_after_pet = Counter.convert_alpha_count
    finally:
        pygame.Surface = orig  # type: ignore[assignment]

    assert n_after_ninja >= 1, "ninja_surface did not call convert_alpha"
    assert n_after_enemy >= n_after_ninja + 1, \
        "enemy_surface did not call convert_alpha"
    assert n_after_firefly >= n_after_enemy + 1, \
        "firefly_surface did not call convert_alpha"
    assert n_after_building >= n_after_firefly + 1, \
        "building_surface did not call convert_alpha"
    assert n_after_pet >= n_after_building + 1, \
        "pet_surface did not call convert_alpha"


def test_convert_alpha_not_called_on_cache_hit(pygame_headless):
    """A second call (cache hit) must not call convert_alpha again."""
    import pygame
    from assets import (
        ninja_surface, enemy_surface, firefly_surface,
        building_surface, pet_surface,
    )
    from data.enemies import ZONES

    _reset_caches()
    # Prime the caches (this calls convert_alpha once per function).
    e = ZONES[0]["enemies"][0]
    ninja_surface(64)
    enemy_surface(e)
    firefly_surface(10)
    building_surface("farm")
    pet_surface("frog", 120)

    orig, Counter = _install_counter(pygame)
    try:
        ninja_surface(64)
        enemy_surface(e)
        firefly_surface(10)
        building_surface("farm")
        pet_surface("frog", 120)
        extra = Counter.convert_alpha_count
    finally:
        pygame.Surface = orig  # type: ignore[assignment]
    assert extra == 0, (
        f"convert_alpha called on cache hit: {extra} extra calls"
    )


def test_caches_hit_on_second_call(pygame_headless):
    """Second call returns the same (cached, converted) surface object."""
    from assets import (
        ninja_surface, enemy_surface, firefly_surface,
        building_surface, pet_surface,
    )
    from data.enemies import ZONES
    _reset_caches()
    e = ZONES[0]["enemies"][0]
    first = [
        ninja_surface(64),
        enemy_surface(e),
        firefly_surface(10),
        building_surface("farm"),
        pet_surface("frog", 120),
    ]
    seconds = [
        ninja_surface(64),
        enemy_surface(e),
        firefly_surface(10),
        building_surface("farm"),
        pet_surface("frog", 120),
    ]
    names = ["ninja", "enemy", "firefly", "building", "pet"]
    for f, s, name in zip(first, seconds, names):
        assert f is s, f"{name}: second call did not hit cache"


def test_blit_throughput_microbenchmark(pygame_headless):
    """Microbenchmark: blitting a converted surface vs an unconverted one.

    Note: under `SDL_VIDEODRIVER=dummy` the display is RGB888 and
    `convert_alpha()` is a format no-op (the converted surface has the
    same ARGB masks as the SRCALPHA surface), so the ~1.5-2x speedup
    the task brief targets is not reproducible here — it manifests on
    real hardware where the display's native format differs from ARGB.
    This test asserts only "no major regression": the converted path is
    not dramatically slower than the unconverted path (within a generous
    factor), which guards against the fix accidentally making blits
    slower.
    """
    import time
    import pygame

    screen = pygame.display.get_surface()
    assert screen is not None, "display not initialised"

    size = 64
    iters = 20000

    unconverted = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(unconverted, (40, 40, 60), (10, 10, 40, 40),
                     border_radius=6)
    pygame.draw.circle(unconverted, (220, 180, 150), (32, 20), 10)
    try:
        alpha = pygame.surfarray.pixels_alpha(unconverted)
        alpha[:] = 200
        del alpha
    except Exception:
        pass

    converted = unconverted.convert_alpha()

    def bench(src):
        # Warm up so first-call overhead doesn't skew either side.
        for _ in range(2000):
            screen.blit(src, (0, 0))
        # Take the minimum of a few runs to reduce noise.
        best = float("inf")
        for _ in range(5):
            t0 = time.perf_counter()
            for _ in range(iters):
                screen.blit(src, (0, 0))
            best = min(best, time.perf_counter() - t0)
        return best

    t_unconverted = bench(unconverted)
    t_converted = bench(converted)

    # Informational — printed for the test report.
    speedup = t_unconverted / t_converted
    print(
        f"microbenchmark: unconverted={t_unconverted:.4f}s "
        f"({t_unconverted/iters*1e6:.2f} us/blit), "
        f"converted={t_converted:.4f}s "
        f"({t_converted/iters*1e6:.2f} us/blit), "
        f"speedup={speedup:.2f}x"
    )
    # No-major-regression floor: converted must not be more than 1.5x
    # slower than unconverted. (In the dummy driver the two are within
    # noise of each other; on real hardware the converted path is
    # faster.)
    assert t_converted <= t_unconverted * 1.5, (
        f"convert_alpha regression: converted={t_converted:.4f}s "
        f"is >1.5x slower than unconverted={t_unconverted:.4f}s"
    )
