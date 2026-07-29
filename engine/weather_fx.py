"""Weather FX: per-zone weather particles (Task 31 / gfx-weather).

A ``WeatherFXSystem`` spawns zone-appropriate particles from the top
edge using ``ParticleSystem2`` presets. Pooled (no per-frame allocations
after warm-up — the particle system reuses dead particles via its pool).

Weather types (the brief's hero zones):
  * ``"rain"``  — Bamboo Forest: blue-white streaks falling fast.
  * ``"ash"``   — Oni Volcano: orange embers drifting up + down.
  * ``"snow"``   — Sky Citadel: white flakes drifting slowly.
  * ``"drift"``  — Cosmic Void: purple motes drifting sideways.
  * ``"none"``  — the default: no particles (the tutorial + non-hero
                  zones reuse this).

Count caps per type (the brief): rain <= 120, snow <= 60, ash <= 80,
drift <= 80. The cap is enforced by the particle system's
``max_particles`` (set per weather type) so the count never exceeds the
cap regardless of spawn rate.

Under ``reduced_motion`` OR the low render tier, the system falls back
to a static tint overlay (no particles) — the same gate as parallax
(Task 29) + sprite-sheet animation (Task 30). The tint is a thin
full-screen SRCALPHA overlay tinted by the weather type's color (a
subtle "this zone is wet/cold/hot/void" cue without motion).

Integration:
  * ``Runner.__init__``:  ``self.weather_fx = WeatherFXSystem()``
  * ``Runner.update``:  sync ``weather_fx.set_weather(zone_weather,
    zone_index)`` + ``weather_fx.reduced_motion`` + ``weather_fx.quality``
    each tick, then ``weather_fx.update(dt)``.
  * ``GameScreen.draw``:  ``runner.weather_fx.draw(surf)`` after the
    parallax layers + the road, before the enemies (so the weather
    overlays the road but is under the enemies + HUD).
"""
from __future__ import annotations

import math

import pygame

import config as cfg
from engine.particles import ParticleSystem2
from utils import rng


# ---------------------------------------------------------------------------
# Weather presets
# ---------------------------------------------------------------------------
# Each preset is (color, vx_range, vy_range, life, size, gravity, shape,
# glow, cap, spawn_per_sec, fade_color). The cap is the max active
# particles for this weather type (enforced via the particle system's
# max_particles). spawn_per_sec is the spawn rate (particles per second);
# the system spawns ``spawn_per_sec * dt`` particles per tick (rounded
# stochastically so the rate is accurate at any fps).
#
# The presets are tuned for a 60fps loop:
#   * rain:  fast vertical streaks, short life (off-screen quickly), high
#            spawn rate (the cap is the limiter, not the rate).
#   * snow:  slow drift, long life (flakes hang in the air), low spawn
#            rate (the cap is rarely hit; the flakes accumulate).
#   * ash:   medium drift, medium life, medium spawn rate.
#   * drift: sideways drift, long life, low spawn rate (the void motes
#            linger).
#
# The colors are picked to read as the weather type at a glance:
#   * rain:  pale blue-white (200, 220, 255).
#   * ash:   warm orange (255, 160, 80) fading to dark (180, 60, 20).
#   * snow:  white (240, 245, 255).
#   * drift: purple (180, 120, 255) fading to dark (90, 60, 160).

_WEATHER_PRESETS: dict[str, dict] = {
    "none": {
        "color": (0, 0, 0),
        "vx_range": (0.0, 0.0),
        "vy_range": (0.0, 0.0),
        "life": 0.0,
        "size": 0,
        "gravity": 0.0,
        "shape": "circle",
        "glow": False,
        "cap": 0,
        "spawn_per_sec": 0.0,
        "fade_color": None,
        "tint": (0, 0, 0, 0),  # no tint
    },
    "rain": {
        "color": (200, 220, 255),
        "vx_range": (-30.0, 30.0),
        "vy_range": (520.0, 680.0),
        "life": 1.4,
        "size": 2,
        "gravity": 0.0,        # already fast; no extra gravity
        "shape": "spark",      # streaks aligned with velocity
        "glow": False,
        "cap": 120,
        "spawn_per_sec": 240.0,
        "fade_color": None,
        "tint": (90, 110, 160, 28),  # subtle blue tint
    },
    "snow": {
        "color": (240, 245, 255),
        "vx_range": (-25.0, 25.0),
        "vy_range": (50.0, 90.0),
        "life": 6.0,
        "size": 3,
        "gravity": 0.0,
        "shape": "circle",
        "glow": False,
        "cap": 60,
        "spawn_per_sec": 18.0,
        "fade_color": None,
        "tint": (200, 210, 240, 24),  # subtle cool tint
    },
    "ash": {
        "color": (255, 160, 80),
        "vx_range": (-20.0, 20.0),
        "vy_range": (-40.0, 60.0),    # some rise, some fall
        "life": 3.0,
        "size": 2,
        "gravity": -10.0,             # gentle buoyancy (embers rise)
        "shape": "circle",
        "glow": True,                 # additive glow (embers are bright)
        "cap": 80,
        "spawn_per_sec": 40.0,
        "fade_color": (180, 60, 20),
        "tint": (120, 50, 30, 24),    # warm tint
    },
    "drift": {
        "color": (180, 120, 255),
        "vx_range": (-40.0, 40.0),
        "vy_range": (-20.0, 30.0),    # nearly weightless
        "life": 5.0,
        "size": 3,
        "gravity": 0.0,
        "shape": "star",
        "glow": True,
        "cap": 80,
        "spawn_per_sec": 16.0,
        "fade_color": (90, 60, 160),
        "tint": (90, 60, 160, 22),    # purple tint
    },
}


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class WeatherFXSystem:
    """Owns the per-zone weather particles + the static tint overlay.

    The system is pure state; it allocates nothing per frame in the hot
    loop (the particle system is pooled — dead particles return to the
    pool and are reused). The tint overlay is a single full-screen
    SRCALPHA surface, built once per weather change (not per frame).
    """

    def __init__(self) -> None:
        self.particles = ParticleSystem2()
        # The current weather preset name (e.g. "rain"). ``set_weather``
        # rebinds the particle system's ``max_particles`` to the preset's
        # cap so the count never exceeds the cap.
        self._weather: str = "none"
        self._preset: dict = _WEATHER_PRESETS["none"]
        # The current zone index (for the tint overlay's per-zone tint
        # variation — not used yet, but kept so the screen can read it).
        self._zone_index: int = 0
        # The spawn accumulator (particles per second * dt, rounded
        # stochastically so the rate is accurate at any fps).
        self._spawn_acc: float = 0.0
        # Accessibility + tier gates. When ``reduced_motion`` is True OR
        # ``quality`` is "low", the system falls back to the static tint
        # overlay (no particles). The screen reads these from state.
        self.reduced_motion: bool = False
        self.quality: str = "med"
        # The cached tint overlay surface (built once per weather change,
        # not per frame). None when the current weather has no tint.
        self._tint_surf: pygame.Surface | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_weather(self, weather: str, zone_index: int = 0) -> None:
        """Set the current weather preset. Rebinds the particle system's
        ``max_particles`` to the preset's cap so the count never exceeds
        the cap. Clears the active particles (the new weather starts
        fresh; the old weather's particles would otherwise linger with
        the wrong color/velocity)."""
        w = weather if weather in _WEATHER_PRESETS else "none"
        # If the weather is unchanged, do nothing (avoid clearing on
        # every tick — the runner calls this each tick).
        if w == self._weather and zone_index == self._zone_index:
            return
        self._weather = w
        self._preset = _WEATHER_PRESETS[w]
        self._zone_index = zone_index
        # Rebind the cap so the count never exceeds the preset's cap.
        self.particles.max_particles = self._preset["cap"]
        # Clear the active particles (the new weather starts fresh).
        self.particles.clear()
        # Reset the spawn accumulator.
        self._spawn_acc = 0.0
        # Rebuild the tint overlay (cached per weather change).
        self._tint_surf = None

    def update(self, dt: float) -> None:
        """Advance the weather FX by one tick.

        Spawns particles from the top edge at the preset's spawn rate
        (capped by the preset's cap via the particle system's
        ``max_particles``). Under ``reduced_motion`` OR the low tier,
        no particles are spawned (the static tint overlay is the only
        output).
        """
        # Gate: reduced_motion OR low tier -> no particles (static tint).
        if self.reduced_motion or self.quality == "low":
            # Clear any active particles (the gate may have turned on
            # mid-weather; the particles are not needed under the gate).
            if len(self.particles) > 0:
                self.particles.clear()
            return
        # "none" weather: no particles.
        if self._weather == "none":
            return
        # Spawn particles from the top edge. The spawn rate is
        # ``spawn_per_sec``; we accumulate the fractional count and
        # spawn stochastically so the rate is accurate at any fps.
        rate = self._preset["spawn_per_sec"]
        self._spawn_acc += rate * dt
        n = int(self._spawn_acc)
        if n > 0:
            self._spawn_acc -= n
            self._spawn_top_edge(n)
        # Update the particles (move + cull dead).
        self.particles.update(dt)

    def draw(self, surf: pygame.Surface) -> None:
        """Draw the weather (particles OR static tint overlay).

        Under ``reduced_motion`` OR the low tier, draws the static tint
        overlay (no particles). Otherwise draws the particles. The tint
        is also drawn under the particles at high/med tier (a subtle
        base tint + the particles on top) so the zone reads as the
        weather type even before the particles fill in.
        """
        # Static tint overlay (the reduced-motion / low-tier fallback,
        # AND the base tint at high/med tier). The tint is a full-screen
        # SRCALPHA surface built once per weather change.
        tint = self._preset["tint"]
        if tint[3] > 0:
            if self._tint_surf is None:
                self._tint_surf = pygame.Surface(
                    (cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
                self._tint_surf.fill(tint)
            surf.blit(self._tint_surf, (0, 0))
        # Particles (only when not gated; the gate was checked in
        # ``update`` but we re-check here so a mid-frame gate toggle
        # does not draw stale particles).
        if self.reduced_motion or self.quality == "low":
            return
        if self._weather == "none":
            return
        self.particles.draw(surf)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _spawn_top_edge(self, n: int) -> None:
        """Spawn ``n`` particles from the top edge (y = HUD_H, the
        road's top) with the preset's velocity ranges."""
        if n <= 0 or self._weather == "none":
            return
        p = self._preset
        # Spawn from the top edge (y = cfg.ROAD_TOP, just above the road).
        # x is random across the screen width.
        y = float(cfg.ROAD_TOP)
        r = rng()
        # Use the emit method (directional, not radial) so the particles
        # get the right velocity ranges. We emit one at a time with a
        # random x so the particles spread across the top edge (not all
        # at the same x).
        for _ in range(n):
            x = r.uniform(0.0, float(cfg.WINDOW_W))
            self.particles.emit(
                x, y, p["color"], count=1,
                vx_range=p["vx_range"], vy_range=p["vy_range"],
                life=p["life"], size=p["size"],
                gravity=p["gravity"], shape=p["shape"],
                glow=p["glow"], fade_color=p["fade_color"],
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def weather(self) -> str:
        return self._weather
