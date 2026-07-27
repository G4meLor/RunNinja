"""Building purchase juice: pulse, floating '+N', coin burst, affordable glow.

Pure-state FX layer for the Buildings screen.  On a successful buy the
building icon in the detail panel pulses (scale + gold halo), a gold
'+N' floats up off the icon, a coin-colored particle burst fountains
out, and the G/s currency pill flashes.  Buildings the player can
afford get a subtle breathing gold glow on their list row.

All transient state lives in **fixed-size pools** that are pre-allocated
in ``__init__`` and reused via active flags, so neither ``update`` nor
``draw`` allocate after warmup — no new surfaces, no new particle or
float-text objects, no new lists.  The screen reads ``pulse_scale(bid)``
to scale-blit the icon and ``can_afford_glow(...)`` to glow affordable
rows; this module never imports the screen or the building data.
"""
from __future__ import annotations

import math

import pygame

from utils import rng, clamp, ease_out_cubic, format_number
from theme import C, font_md
from assets import Particle


# --- tunables ---------------------------------------------------------------
_PULSE_DUR = 0.45          # icon pulse + halo duration (seconds)
_PULSE_AMP = 0.18          # max icon scale overshoot
_GS_PULSE_DUR = 0.40       # G/s pill pulse duration
_FLOAT_LIFE = 0.90         # floating '+N' life
_COIN_LIFE = 0.60          # coin particle base life
_COIN_COUNT = 14           # coins per buy
_MAX_PARTICLES = 80        # particle pool cap (>= max concurrent coins)
_MAX_FLOATS = 8            # float-text pool cap

_COIN_COLOR = (255, 230, 140)      # bright gold (C.coin-ish)
_HALO_COLOR = (255, 205, 90)       # gold halo
_TRANSPARENT = (0, 0, 0, 0)

_COIN_SURF_SIZE = 24
_COIN_CENTER = (_COIN_SURF_SIZE // 2, _COIN_SURF_SIZE // 2)
_HALO_SURF_SIZE = 120
_HALO_CENTER = (_HALO_SURF_SIZE // 2, _HALO_SURF_SIZE // 2)


class _FloatText:
    """A single rising, fading '+N'.  Pool-allocated; reused via ``active``."""

    __slots__ = ("x", "y", "vy", "surf", "life", "max_life", "active")

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.surf: pygame.Surface | None = None
        self.life = 0.0
        self.max_life = 1.0
        self.active = False

    def update(self, dt: float) -> None:
        if not self.active:
            return
        self.y += self.vy * dt
        self.vy += 40.0 * dt            # gentle deceleration, stays rising
        self.life -= dt
        if self.life <= 0.0:
            self.active = False


class BuildingFxSystem:
    """Per-frame FX for the Buildings screen.

    Owns per-building pulse timers, a floating-text pool, a coin-burst
    particle pool, and a G/s-counter pulse.  All pools are pre-allocated
    in ``__init__`` and reused via active flags, so neither ``update``
    nor ``draw`` allocate after warmup.  The screen sets
    ``self.reduced_motion`` from ``state.reduced_motion`` each frame.
    """

    def __init__(self) -> None:
        # bid -> remaining pulse time (0 == idle; entries linger, bounded
        # by the building count, so no per-frame dict resizing).
        self._pulse_t: dict[str, float] = {}
        # bid -> icon center (x, y) in screen coords, captured at on_buy.
        self._pulse_pos: dict[str, tuple[float, float]] = {}
        # G/s pill pulse timer.
        self._gs_t: float = 0.0
        # Pre-allocated, reusable pools.
        self._floats: list[_FloatText] = [_FloatText() for _ in range(_MAX_FLOATS)]
        self._particles: list[Particle] = [
            Particle(0.0, 0.0, 0.0, 0.0, 0.0, _COIN_COLOR, 3, 220.0)
            for _ in range(_MAX_PARTICLES)
        ]
        # Reusable scratch surfaces (created once, refilled each frame).
        self._coin_surf = pygame.Surface((_COIN_SURF_SIZE, _COIN_SURF_SIZE),
                                         pygame.SRCALPHA)
        self._halo_surf = pygame.Surface((_HALO_SURF_SIZE, _HALO_SURF_SIZE),
                                         pygame.SRCALPHA)
        # One scratch rect for all blits (avoids per-blit tuple allocs).
        self._scratch = pygame.Rect(0, 0, 0, 0)
        # Set by the screen each frame from state.reduced_motion.
        self.reduced_motion: bool = False

    # ------------------------------------------------------------------
    # Buy event
    # ------------------------------------------------------------------
    def on_buy(self, bid: str, x: float, y: float, levels_bought: int) -> None:
        """Fire the purchase FX at the building icon center (x, y).

        Always arms the icon pulse, the halo, and the G/s pill pulse.
        The floating '+N' and coin burst are skipped under reduced motion.
        """
        if levels_bought <= 0:
            return
        self._pulse_t[bid] = _PULSE_DUR
        self._pulse_pos[bid] = (float(x), float(y))
        self._gs_t = _GS_PULSE_DUR
        if self.reduced_motion:
            return
        # --- Floating '+N' (reuse an inactive pool slot) ---
        text = f"+{format_number(levels_bought)}"
        rendered = font_md(bold=True).render(text, True, C.gold)
        for ft in self._floats:
            if not ft.active:
                ft.x = float(x)
                ft.y = float(y) - 8.0
                ft.vy = -80.0
                ft.surf = rendered
                ft.life = _FLOAT_LIFE
                ft.max_life = _FLOAT_LIFE
                ft.active = True
                break
        # --- Coin burst (reuse inactive particle slots) ---
        count = 0
        for p in self._particles:
            if p.life > 0.0:
                continue
            ang = rng().uniform(0.0, math.tau)
            sp = rng().uniform(80.0, 180.0)
            p.x = float(x)
            p.y = float(y)
            p.vx = math.cos(ang) * sp
            p.vy = math.sin(ang) * sp - 40.0      # slight upward bias
            p.life = _COIN_LIFE * rng().uniform(0.7, 1.2)
            p.max_life = p.life
            p.color = _COIN_COLOR
            p.size = rng().uniform(2.0, 4.0)
            p.gravity = 220.0
            count += 1
            if count >= _COIN_COUNT:
                break

    # ------------------------------------------------------------------
    # Reads for the screen
    # ------------------------------------------------------------------
    def pulse_scale(self, bid: str) -> float:
        """Current icon scale factor for ``bid`` (1.0 when idle)."""
        if self.reduced_motion:
            return 1.0
        timer = self._pulse_t.get(bid, 0.0)
        if timer <= 0.0:
            return 1.0
        elapsed = _PULSE_DUR - timer
        t = clamp(elapsed / _PULSE_DUR, 0.0, 1.0)
        # Snap to max on buy, ease back to 1.0 (snappy pop + settle).
        return 1.0 + _PULSE_AMP * (1.0 - ease_out_cubic(t))

    def gs_pulse_alpha(self) -> int:
        """Glow alpha (0..180) for the G/s pill; 0 when idle."""
        if self._gs_t <= 0.0:
            return 0
        return int(180.0 * (self._gs_t / _GS_PULSE_DUR))

    def can_afford_glow(self, bid: str, rect: pygame.Rect,
                        can_afford: bool, t: float) -> int:
        """Breathing gold glow alpha (0..~60) for an affordable list row.

        Returns 0 when ``can_afford`` is False.  ``t`` is the current
        clock seconds (for the breathing modulation); ``rect`` is accepted
        for API completeness but the breathing is global so all affordable
        rows glow in unison, reading as 'available' rather than noisy.
        """
        if not can_afford:
            return 0
        return int(35.0 + 25.0 * math.sin(t * 1.2))

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        # Decay pulse timers in place (no dict resize; dead keys stay 0).
        if self._pulse_t:
            for bid in self._pulse_t:
                v = self._pulse_t[bid] - dt
                self._pulse_t[bid] = v if v > 0.0 else 0.0
        # G/s pill pulse.
        if self._gs_t > 0.0:
            self._gs_t -= dt
            if self._gs_t < 0.0:
                self._gs_t = 0.0
        # Floats + coin particles (pools are fixed-size; no compaction).
        for ft in self._floats:
            ft.update(dt)
        for p in self._particles:
            if p.life > 0.0:
                p.update(dt)

    def draw(self, surf: pygame.Surface) -> None:
        # 1. Pulse halos — expanding, fading gold ring behind/around the
        #    icon.  Drawn first so the icon (scale-blitted by the screen)
        #    and the floating text sit on top.
        hs = self._halo_surf
        scratch = self._scratch
        for bid, timer in self._pulse_t.items():
            if timer <= 0.0:
                continue
            pos = self._pulse_pos.get(bid)
            if pos is None:
                continue
            elapsed = _PULSE_DUR - timer
            t = clamp(elapsed / _PULSE_DUR, 0.0, 1.0)
            radius = int(32 + 22 * t)
            alpha = int(150 * (1.0 - t))
            if alpha <= 0 or radius <= 0:
                continue
            cx, cy = pos
            hs.fill(_TRANSPARENT)
            pygame.draw.circle(hs, _HALO_COLOR, _HALO_CENTER, radius, width=3)
            hs.set_alpha(alpha)
            scratch.x = int(cx) - _HALO_CENTER[0]
            scratch.y = int(cy) - _HALO_CENTER[1]
            surf.blit(hs, scratch)
        # 2. Coin particles — filled gold circles with life-decay alpha.
        cs = self._coin_surf
        for p in self._particles:
            if p.life <= 0.0:
                continue
            a = int(255 * clamp(p.life / p.max_life, 0.0, 1.0))
            if a <= 0:
                continue
            r = max(2, int(p.size))
            cs.fill(_TRANSPARENT)
            pygame.draw.circle(cs, _COIN_COLOR, _COIN_CENTER, r)
            cs.set_alpha(a)
            scratch.x = int(p.x) - _COIN_CENTER[0]
            scratch.y = int(p.y) - _COIN_CENTER[1]
            surf.blit(cs, scratch)
        # 3. Floating '+N' texts — pre-rendered, just set_alpha + blit.
        for ft in self._floats:
            if not ft.active or ft.surf is None:
                continue
            a = clamp(ft.life / ft.max_life, 0.0, 1.0)
            alpha = int(255 * a) if a > 0.6 else int(255 * (a / 0.6))
            ft.surf.set_alpha(alpha)
            scratch.x = int(ft.x) - ft.surf.get_width() // 2
            scratch.y = int(ft.y) - ft.surf.get_height() // 2
            surf.blit(ft.surf, scratch)
