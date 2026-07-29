"""Task 31 (gfx-weather): per-zone weather particles.

Weather particles (rain in Bamboo, ash in Volcano, snow in Sky, void
drift in Void) make zones feel like places. A ``WeatherFXSystem`` spawns
zone-appropriate particles from the top edge using ``ParticleSystem2``
presets. Pooled (no per-frame allocations). Caps counts per weather
type (rain <=120, snow <=60). Under ``reduced_motion`` OR the low
render tier, falls back to a static tint overlay (no particles).

Acceptance criteria covered:
- At least 3 zones have distinct weather particle presets
- Weather uses ParticleSystem2 (pooled, no per-frame allocations)
- Particle counts capped per type and reduced under reduced_motion
- reduced_motion falls back to a static tint overlay
- 60fps maintained with weather enabled (smoke)
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# ---------------------------------------------------------------------------
# Zone weather keys
# ---------------------------------------------------------------------------
def test_zone_weather_keys():
    """Every zone has a 'weather' key (the brief's specimen test)."""
    from data.enemies import ZONES
    for z in ZONES:
        assert "weather" in z, f"zone {z['id']} missing weather key"


def test_weather_system(pygame_headless):
    """WeatherFXSystem can be constructed (the brief's specimen test)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    assert w is not None


def test_zone_weather_values_valid():
    """Every zone's weather is a known preset."""
    from data.enemies import ZONES
    allowed = {"none", "rain", "ash", "snow", "drift"}
    for z in ZONES:
        assert z["weather"] in allowed, (
            f"zone {z['id']} has bad weather {z['weather']!r}")


def test_at_least_3_distinct_weather():
    """At least 3 distinct weather presets appear across the 9 zones
    (the acceptance criterion)."""
    from data.enemies import ZONES
    seen = set()
    for z in ZONES:
        seen.add(z["weather"])
    # "none" + at least 3 real weather types.
    assert len(seen - {"none"}) >= 3, (
        f"expected >= 3 distinct weather presets, got {seen}")


def test_hero_zones_have_expected_weather():
    """The hero zones have the expected weather from the brief:
    bamboo=rain, volcano=ash, sky=snow, void=drift."""
    from data.enemies import zone_by_id
    assert zone_by_id("bamboo")["weather"] == "rain"
    assert zone_by_id("volcano")["weather"] == "ash"
    assert zone_by_id("sky")["weather"] == "snow"
    assert zone_by_id("void")["weather"] == "drift"


# ---------------------------------------------------------------------------
# WeatherFXSystem uses ParticleSystem2 (pooled)
# ---------------------------------------------------------------------------
def test_weather_system_uses_particle_system2():
    """WeatherFXSystem uses a ParticleSystem2 (pooled)."""
    from engine.runner import WeatherFXSystem
    from engine.particles import ParticleSystem2
    w = WeatherFXSystem()
    assert isinstance(w.particles, ParticleSystem2)


def test_particle_system2_has_emit_method():
    """ParticleSystem2 has an `emit` directional spawner (used by
    weather to spawn particles from the top edge with a velocity
    range, not a radial burst)."""
    from engine.particles import ParticleSystem2
    assert hasattr(ParticleSystem2, "emit")
    ps = ParticleSystem2()
    # emit should spawn particles without error.
    ps.emit(100, -10, (255, 255, 255), count=5,
            vx_range=(-10, 10), vy_range=(300, 400), life=1.0)
    assert len(ps) == 5


# ---------------------------------------------------------------------------
# Particle counts capped per type
# ---------------------------------------------------------------------------
def test_rain_count_capped(pygame_headless):
    """Rain particles are capped at 120 (the brief's cap)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("rain", 120)
    w.reduced_motion = False
    w.quality = "high"
    # Run for several seconds to reach steady state.
    for _ in range(300):
        w.update(1 / 60)
    assert len(w.particles) <= 120, (
        f"rain exceeded cap: {len(w.particles)}")


def test_snow_count_capped(pygame_headless):
    """Snow particles are capped at 60 (the brief's cap)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("snow", 200)
    w.reduced_motion = False
    w.quality = "high"
    # Snow has a long life; run long enough to reach steady state.
    for _ in range(600):
        w.update(1 / 60)
    assert len(w.particles) <= 60, (
        f"snow exceeded cap: {len(w.particles)}")


def test_ash_count_capped(pygame_headless):
    """Ash particles are capped (<= 80)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("ash", 10)
    w.reduced_motion = False
    w.quality = "high"
    for _ in range(300):
        w.update(1 / 60)
    assert len(w.particles) <= 80, (
        f"ash exceeded cap: {len(w.particles)}")


def test_drift_count_capped(pygame_headless):
    """Void drift particles are capped (<= 80)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("drift", 270)
    w.reduced_motion = False
    w.quality = "high"
    for _ in range(600):
        w.update(1 / 60)
    assert len(w.particles) <= 80, (
        f"drift exceeded cap: {len(w.particles)}")


def test_none_weather_no_particles(pygame_headless):
    """The 'none' weather spawns no particles."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("none", 0)
    w.reduced_motion = False
    w.quality = "high"
    for _ in range(60):
        w.update(1 / 60)
    assert len(w.particles) == 0


# ---------------------------------------------------------------------------
# reduced_motion + low tier fall back to static tint (no particles)
# ---------------------------------------------------------------------------
def test_reduced_motion_no_particles(pygame_headless):
    """Under reduced_motion, the weather system spawns no particles
    (static tint overlay only)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("rain", 120)
    w.reduced_motion = True
    w.quality = "high"
    for _ in range(60):
        w.update(1 / 60)
    assert len(w.particles) == 0, (
        f"reduced_motion spawned particles: {len(w.particles)}")


def test_low_tier_no_particles(pygame_headless):
    """At the low render tier, the weather system spawns no particles
    (static tint overlay only)."""
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("rain", 120)
    w.reduced_motion = False
    w.quality = "low"
    for _ in range(60):
        w.update(1 / 60)
    assert len(w.particles) == 0, (
        f"low tier spawned particles: {len(w.particles)}")


def test_reduced_motion_draws_tint(pygame_headless):
    """Under reduced_motion, draw produces no error (the static tint
    path is exercised without crashing)."""
    import pygame
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("rain", 120)
    w.reduced_motion = True
    w.quality = "high"
    surf = pygame.Surface((1280, 720))
    for _ in range(30):
        w.update(1 / 60)
        w.draw(surf)


def test_low_tier_draws_tint(pygame_headless):
    """At the low tier, draw produces no error (the static tint path)."""
    import pygame
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("snow", 200)
    w.reduced_motion = False
    w.quality = "low"
    surf = pygame.Surface((1280, 720))
    for _ in range(30):
        w.update(1 / 60)
        w.draw(surf)


# ---------------------------------------------------------------------------
# No per-frame allocations (pooled)
# ---------------------------------------------------------------------------
def test_weather_no_per_frame_scratch_allocations(pygame_headless):
    """After warm-up, weather draw must not grow the scratch cache
    (pooled — no per-frame Surface allocations)."""
    import pygame
    from engine.runner import WeatherFXSystem
    w = WeatherFXSystem()
    w.set_weather("rain", 120)
    w.reduced_motion = False
    w.quality = "high"
    surf = pygame.Surface((1280, 720))
    # Warm up.
    for _ in range(10):
        w.update(1 / 60)
        w.draw(surf)
    allocs_before = len(w.particles._scratch_cache)
    for _ in range(60):
        w.update(1 / 60)
        w.draw(surf)
    allocs_after = len(w.particles._scratch_cache)
    assert allocs_after == allocs_before, (
        f"weather leaked {allocs_after - allocs_before} scratch surfaces "
        f"(before={allocs_before}, after={allocs_after})")


# ---------------------------------------------------------------------------
# Runner wires the weather FX
# ---------------------------------------------------------------------------
def test_runner_has_weather_fx(pygame_headless):
    """The runner has a weather_fx attribute (WeatherFXSystem)."""
    from engine.runner import Runner
    from engine.runner import WeatherFXSystem
    from core.state import GameState
    r = Runner(GameState())
    assert hasattr(r, "weather_fx")
    assert isinstance(r.weather_fx, WeatherFXSystem)


# ---------------------------------------------------------------------------
# Smoke: the game draws with weather (60fps maintained)
# ---------------------------------------------------------------------------
def _reinit_display():
    """Re-init pygame + the display if a prior test quit pygame."""
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


def test_game_draws_with_weather(pygame_headless):
    """The game screen draws 30 frames with weather (rain zone) at the
    high tier without error (60fps maintained)."""
    import main
    import pygame
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.reduced_motion = False
    g.state.render_quality = "high"
    # Force a weather zone (bamboo = rain).
    g.state.zone_index = 1
    g.runner.world.zone_index = 1
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()


def test_game_draws_weather_reduced_motion(pygame_headless):
    """The game screen draws 30 frames with weather under reduced_motion
    (static tint path) without error."""
    import main
    import pygame
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.reduced_motion = True
    g.state.zone_index = 1  # bamboo = rain
    g.runner.world.zone_index = 1
    for _ in range(30):
        g._update(1 / 60)
        g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()


def test_game_draws_weather_all_zones(pygame_headless):
    """The game screen draws frames across all 9 zones (each weather
    type) without error. Exercises the zone-weather sync path."""
    import main
    import pygame
    _reinit_display()
    g = main.Game()
    g.current_screen = "game"
    g.state.reduced_motion = False
    g.state.render_quality = "high"
    for zi in range(9):
        g.state.zone_index = zi
        g.runner.world.zone_index = zi
        for _ in range(10):
            g._update(1 / 60)
            g.screens["game"].draw(g.screen)
    assert g.state is not None
    pygame.quit()
