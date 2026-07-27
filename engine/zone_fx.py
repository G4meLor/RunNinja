"""Zone transition cinematic: banner, cross-fade, light sweep, hit-stop.

A self-contained overlay system that makes advancing zones feel like
traveling.  The runner triggers it on a boss kill (before the world
advances the zone), the game screen draws the overlay, and main.py
applies the hit-stop via a callback.

Phases over ~2.0s:
  0.00 - 0.45  banner-in   : dark band slides down from the top, zone
                             name fades in centered on the band.
  0.45 - 1.20  cross-fade  : the new zone's background is blended in as
                             an alpha overlay so the palette shifts.
  0.80 - 1.40  sweep       : a soft diagonal light sweep wipes across.
  1.40 - 2.00  banner-out  : the band slides back up and fades out.

All rendering uses pygame primitives + cached theme fonts + the hsl()
helper from assets, so nothing here depends on external art.
"""
from __future__ import annotations

import math

import pygame

import config as cfg
from assets import hsl, background
from theme import C, font_lg, font_xl, font_huge, draw_text_center
from utils import clamp, ease_out_cubic, ease_in_out_cubic, lerp_color


# Phase timings (seconds).  Total ~2.0s.
T_BANNER_IN   = 0.45
T_CROSSFADE   = 0.75   # duration of the cross-fade (starts at T_BANNER_IN)
T_SWEEP_START = 0.80
T_SWEEP_DUR   = 0.60
T_BANNER_OUT  = 0.60   # starts at TOTAL - T_BANNER_OUT
TOTAL         = 2.00

# Hit-stop requested at trigger time so the boss kill gets a brief
# slow-motion beat before the world advances.
HITSTOP_DUR = 0.12


class ZoneFxSystem:
    """Drives a single zone-transition sequence.

    The system is idle until ``trigger()`` is called; while ``active``
    is True, ``update(dt)`` advances the timeline and ``draw(surf)``
    renders the overlay (banner + sweep) over the road.  The cross-fade
    is exposed via ``crossfade_alpha()`` / ``crossfade_surface()`` so
    the screen can blend the new background under the overlay.
    """

    def __init__(self) -> None:
        self.t: float = 0.0
        self._active: bool = False
        self.zone_index: int = 0
        self.zone_name: str = ""
        self.old_hue: int = 0
        self.new_hue: int = 0
        # Cached new-zone background surface for the cross-fade overlay.
        self._new_bg: pygame.Surface | None = None
        # Cached sweep surface (regenerated per trigger so the angle is
        # stable for the whole sequence).
        self._sweep: pygame.Surface | None = None
        # Callback fired once at trigger time so main.py can apply the
        # hit-stop (slow-motion) without this module depending on Game.
        self.on_hitstop = None  # callable(dur: float) -> None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self._active

    def trigger(self, zone_index: int, zone_name: str,
                old_hue: int, new_hue: int) -> None:
        """Start a ~2s transition into ``zone_index``.

        Caches the new zone's background (via assets.background) so the
        cross-fade can blit it as an alpha overlay, and requests the
        hit-stop through ``on_hitstop`` if set.
        """
        self.zone_index = zone_index
        self.zone_name = zone_name
        self.old_hue = old_hue
        self.new_hue = new_hue
        self.t = 0.0
        self._active = True
        # Pre-render the destination background once; background() caches
        # by (zone_index, hue) so this is cheap on repeat transitions.
        self._new_bg = background(zone_index, new_hue).copy()
        self._sweep = None  # built lazily on first draw
        if self.on_hitstop is not None:
            try:
                self.on_hitstop(HITSTOP_DUR)
            except Exception:
                pass

    def update(self, dt: float) -> None:
        if not self._active:
            return
        self.t += dt
        if self.t >= TOTAL:
            self._active = False
            self._new_bg = None
            self._sweep = None

    # Cross-fade exposure for the screen: while the cross-fade phase is
    # running, return the alpha (0..255) to apply to the new background
    # overlay.  Outside the phase returns 0 so the screen can short-circuit.
    def crossfade_alpha(self) -> int:
        if not self._active or self._new_bg is None:
            return 0
        start = T_BANNER_IN
        end = T_BANNER_IN + T_CROSSFADE
        if self.t < start:
            return 0
        if self.t >= end:
            return 255
        p = ease_in_out_cubic((self.t - start) / T_CROSSFADE)
        return int(255 * clamp(p, 0.0, 1.0))

    def crossfade_surface(self) -> pygame.Surface | None:
        """The new-zone background to blend over the current one."""
        return self._new_bg

    def old_zone_index(self) -> int:
        """Index of the zone we're leaving (new index - 1, clamped >= 0).

        The world advances ``zone_index`` at trigger time, so the screen
        would otherwise draw the *new* background immediately; drawing the
        old background (via this index) while the overlay cross-fades the
        new one in is what makes the palette shift visible.
        """
        return max(0, self.zone_index - 1)

    def draw(self, surf: pygame.Surface) -> None:
        if not self._active:
            return
        t = self.t
        w, h = surf.get_size()
        cx = w // 2

        # --- Banner band (slides in from the top, out to the top) ---
        band_h = 150
        if t < T_BANNER_IN:
            # Sliding in: ease the band down from -band_h to its rest.
            p = ease_out_cubic(t / T_BANNER_IN)
            rest_y = cfg.ROAD_TOP + 40
            band_y = int(lerp_val(-band_h, rest_y, p))
            band_alpha = int(255 * p)
        elif t < TOTAL - T_BANNER_OUT:
            # Holding: band sits at rest, full opacity.
            band_y = cfg.ROAD_TOP + 40
            band_alpha = 255
        else:
            # Sliding out: ease back up past the top.
            p = ease_out_cubic((t - (TOTAL - T_BANNER_OUT)) / T_BANNER_OUT)
            rest_y = cfg.ROAD_TOP + 40
            band_y = int(lerp_val(rest_y, -band_h, p))
            band_alpha = int(255 * (1.0 - p))

        if band_alpha > 0:
            band = pygame.Surface((w, band_h), pygame.SRCALPHA)
            # Deep, slightly-tinted panel so the band reads as part of the
            # new zone's palette without being garish.
            tint = hsl(self.new_hue, 0.35, 0.10)
            pygame.draw.rect(band, (*tint, int(235 * (band_alpha / 255))),
                             band.get_rect(), border_radius=10)
            # Thin accent line top + bottom in the new zone's hue.
            accent = hsl(self.new_hue, 0.6, 0.55)
            pygame.draw.line(band, (*accent, band_alpha),
                             (40, 6), (w - 40, 6), 2)
            pygame.draw.line(band, (*accent, band_alpha),
                             (40, band_h - 8), (w - 40, band_h - 8), 2)
            surf.blit(band, (0, band_y))

            # Zone name — fade/scale in during banner-in, steady, then
            # fade out during banner-out.
            if t < T_BANNER_IN:
                text_p = ease_out_cubic(t / T_BANNER_IN)
            elif t < TOTAL - T_BANNER_OUT:
                text_p = 1.0
            else:
                text_p = 1.0 - ease_out_cubic(
                    (t - (TOTAL - T_BANNER_OUT)) / T_BANNER_OUT)
            text_alpha = int(255 * clamp(text_p, 0.0, 1.0))
            if text_alpha > 0:
                label = f"Zone {self.zone_index + 1}  —  {self.zone_name}"
                # Render the title and a small subtitle, then set alpha.
                title = font_xl(bold=True).render(label, True, C.text)
                title.set_alpha(text_alpha)
                tr = title.get_rect(center=(cx, band_y + band_h // 2 - 12))
                surf.blit(title, tr)
                sub = font_lg().render("the road goes on", True, C.text_dim)
                sub.set_alpha(int(text_alpha * 0.8))
                sr = sub.get_rect(center=(cx, band_y + band_h // 2 + 22))
                surf.blit(sub, sr)

        # --- Light sweep (diagonal wipe across the full screen) ---
        if T_SWEEP_START <= t < T_SWEEP_START + T_SWEEP_DUR:
            p = (t - T_SWEEP_START) / T_SWEEP_DUR
            # Build the sweep once per trigger so the gradient is stable.
            if self._sweep is None:
                self._sweep = _make_sweep(w, h, self.new_hue)
            # The sweep band travels left -> right; its leading edge is
            # at x = p * (w + sweep_w) - sweep_w/2.
            sweep_w = 220
            x = int(p * (w + sweep_w) - sweep_w // 2)
            # Fade the whole sweep in then out so it doesn't pop.
            env = math.sin(min(1.0, p) * math.pi)
            sweep_alpha = int(180 * env)
            if sweep_alpha > 0 and self._sweep is not None:
                # Blit the slice of the sweep that's currently on-screen.
                # self._sweep is full-screen; just blit it with set_alpha
                # and let the x-position come from a clipped rect.
                sw = self._sweep
                sw.set_alpha(sweep_alpha)
                surf.blit(sw, (x, 0))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def lerp_val(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _make_sweep(w: int, h: int, hue: int) -> pygame.Surface:
    """A soft diagonal light band on a transparent full-screen surface.

    The band is a vertical gradient (transparent -> bright -> transparent)
    so when it's blitted at a moving x offset it reads as a sweep.
    """
    sweep_w = 220
    surf = pygame.Surface((sweep_w, h), pygame.SRCALPHA)
    base = hsl(hue, 0.7, 0.7)
    for i in range(sweep_w):
        # Triangular-ish falloff: bright in the middle, transparent at the
        # edges, so the sweep has a soft leading + trailing edge.
        d = abs(i - sweep_w / 2) / (sweep_w / 2)
        a = int(180 * (1.0 - d) ** 2)
        if a <= 0:
            continue
        pygame.draw.line(surf, (*base, a), (i, 0), (i, h - 1))
    return surf
