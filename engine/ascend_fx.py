"""Ascension ceremony FX: a full-screen ritual when the player ascends.

Replaces the plain two-click confirm with a ~3 s cinematic:

    dim (~0.4 s)
        The screen darkens under a deep indigo veil while elixir-coloured
        particles begin to drift inward from the four screen corners.

    converge (~1.0 s)
        Elixir-coloured particles accelerate toward the screen centre,
        shrinking as they near it, and a soft core glow swells.

    reveal (~0.9 s)
        The new tier name slams in (scaled up from 1.6x to 1.0x with an
        ease-out) in elixir colour using ``font_huge``; the stat multiplier
        "x{mult}" appears just below in ``font_xl``.  A short radial flash
        marks the peak -- this is the frame the caller performs the actual
        ascension (``asc.ascend`` + ``runner.reset_for_ascension``).

    rewind (~0.7 s)
        A quick horizontal sweep "rewinds" the road: an elixir-coloured
        band wipes from the right edge to the left, then fades out.

Total ~3.0 s.  Pure state -- the renderer reads it.  No per-frame Surface
allocations in the hot loop: the dim veil, the converge scratch, the
flash scratch, and the rewind band are all created once (lazily) and
reused; only ``set_alpha`` / ``fill`` / ``draw`` / ``blit`` run per frame.
Fonts come from the cached ``theme`` helpers; the reveal text images are
rendered once at ``start`` (spawn time) and merely ``set_alpha``'d +
``smoothscale``'d per frame.
"""
from __future__ import annotations

import math

import pygame
import pygame.gfxdraw as gfx

import config as cfg
from assets import hsl
from theme import font_huge, font_xl
from utils import rng, clamp, ease_out_cubic


# --- Phase constants (small ints for cheap comparisons) -------------------
_IDLE = 0
_DIM = 1
_CONVERGE = 2
_REVEAL = 3
_REWIND = 4
_DONE = 5

# --- Durations (seconds); total ~3.0 s ------------------------------------
T_DIM = 0.40
T_CONVERGE = 1.00
T_REVEAL = 0.90
T_REWIND = 0.70
T_TOTAL = T_DIM + T_CONVERGE + T_REVEAL + T_REWIND   # 3.00

# --- Palette --------------------------------------------------------------
# Elixir teal (matches the elixir currency pill / ascension accent).
ELIXIR = hsl(170, 0.85, 0.70)          # (117, 239, 219) -- the converge/reveal colour
ELIXIR_BRIGHT = hsl(170, 0.95, 0.82)   # brighter core for the reveal flash
DIM_COLOR = (4, 8, 20)                 # deep indigo veil (matches the night theme)

# --- Particle counts (bounded; built once at start) ----------------------
N_PARTICLES = 56

# --- Scratch sizes --------------------------------------------------------
# The converge scratch must fit the largest particle glow (~6 px radius).
_SCRATCH_PARTICLE = 16
# The flash scratch holds the reveal shockwave ring (radius <= 120).
_SCRATCH_FLASH = 256
# Max flash radius (kept inside the flash scratch).
_FLASH_MAX_R = (_SCRATCH_FLASH - 6) // 2


class _Particle:
    """One elixir mote converging from a screen corner to the centre.

    Built once at ``start``; mutated each tick.  Position is in screen
    space; the particle eases toward ``CX``/``CY`` (the screen centre) and
    shrinks as it nears it.
    """
    __slots__ = ("sx", "sy", "x", "y", "life", "max_life", "size", "delay")

    def __init__(self, sx: float, sy: float, delay: float) -> None:
        self.sx = sx                 # start corner position
        self.sy = sy
        self.x = sx
        self.y = sy
        # Life spans the converge phase (plus a little tail); staggered so
        # the swarm arrives over ~0.8 s rather than all at once.
        self.max_life = rng().uniform(0.75, 1.05)
        self.life = self.max_life
        self.size = rng().uniform(2.5, 5.0)
        # Delay before this mote starts moving (so the swarm trails in).
        self.delay = delay


class AscendFxSystem:
    """Drives the ascension ceremony.

    Lifecycle
    ---------
    1. ``start(tier_name, stat_mult, elixir_gained)`` -- arm the ceremony.
       Renders the reveal text images once (spawn time, not per frame).
    2. each frame: ``update(dt)`` -- advance the phase machine.  After this
       returns, read ``peak`` (one-frame flag: the moment the caller should
       perform the actual ascension + reset).
    3. each frame: ``draw(surf, base_draw)`` -- draw the underlying screen
       via ``base_draw`` (a zero-arg callable), then overlay the ceremony.
    4. when ``done`` is True, the ceremony is finished; call ``reset()``.

    The caller is responsible for performing the ascension at the peak and
    for blocking screen input while ``active`` is True.
    """

    def __init__(self) -> None:
        self._phase = _IDLE
        self._t = 0.0                  # elapsed time in the current phase
        # Reusable surfaces -- created lazily so we don't allocate before
        # ``pygame.display.set_mode``.  All are kept for the life of the
        # system and only mutated (set_alpha / fill / draw / blit) per frame.
        self._dim: pygame.Surface | None = None
        self._particle_scratch: pygame.Surface | None = None
        self._flash_scratch: pygame.Surface | None = None
        self._rewind: pygame.Surface | None = None
        # Ceremony content (set at start).
        self._tier_name: str = ""
        self._stat_mult: float = 1.0
        self._elixir_gained: int = 0
        self._particles: list[_Particle] = []
        # Pre-rendered reveal images (built once at start; only set_alpha /
        # smoothscale per frame -- no re-rendering in the hot loop).
        self._tier_img: pygame.Surface | None = None
        self._mult_img: pygame.Surface | None = None
        self._tier_w: int = 0
        self._tier_h: int = 0
        self._mult_w: int = 0
        self._mult_h: int = 0
        # One-shot peak flag: True for the single frame the caller should
        # perform the actual ascension + reset on.
        self._peak_flag = False
        # Reduced-motion gate (set from state.reduced_motion by the caller).
        # When True the ceremony short-circuits to the peak + done so the
        # ascension still happens, just without the animation.
        self.reduced_motion = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        """True while the ceremony is in progress (dim through rewind)."""
        return self._phase in (_DIM, _CONVERGE, _REVEAL, _REWIND)

    @property
    def done(self) -> bool:
        """True once the ceremony has fully completed."""
        return self._phase == _DONE

    @property
    def peak(self) -> bool:
        """True for exactly one frame: the moment the caller should perform
        the actual ascension (``asc.ascend`` + ``runner.reset_for_ascension``)
        and save.  Read this *after* ``update(dt)`` and before ``draw``.

        The peak fires at the start of the reveal phase -- the visual
        climax (tier name slamming in) coincides with the state change.
        """
        return self._peak_flag

    @property
    def phase(self) -> str:
        """Human-readable phase name (for debugging/specs)."""
        return {0: "idle", 1: "dim", 2: "converge",
                3: "reveal", 4: "rewind", 5: "done"}[self._phase]

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def start(self, tier_name: str, stat_mult: float,
              elixir_gained: int) -> None:
        """Begin the ascension ceremony.

        ``tier_name``  -- the new tier's display name (e.g. "Eternal").
        ``stat_mult``  -- the new tier's stat multiplier (e.g. 3.00).
        ``elixir_gained`` -- elixir awarded by this ascension (shown in the
                          reveal; pure cosmetic).

        Renders the reveal text images once here (at spawn time, on a
        button click -- not in the hot loop) and builds the particle
        swarm.  If ``reduced_motion`` is set, the ceremony is skipped:
        the peak fires immediately and the phase jumps to ``DONE`` so the
        caller's ascension still happens, just without the animation.
        """
        self._tier_name = tier_name
        self._stat_mult = float(stat_mult)
        self._elixir_gained = int(elixir_gained)
        self._t = 0.0
        self._peak_flag = False

        # Pre-render the reveal text once (spawn time).  These surfaces are
        # only set_alpha'd / smoothscale'd per frame -- never re-rendered.
        self._tier_img = font_huge(bold=True).render(
            tier_name, True, ELIXIR)
        self._tier_w, self._tier_h = self._tier_img.get_size()
        self._mult_img = font_xl(bold=True).render(
            f"x{self._stat_mult:.2f} stats", True, ELIXIR)
        self._mult_w, self._mult_h = self._mult_img.get_size()

        # Build the converging particle swarm (one allocation, at start).
        # Particles spawn at the four screen corners and converge to the
        # centre; staggered delays so the swarm trails in over ~0.8 s.
        self._particles = []
        corners = (
            (0.0, 0.0),
            (float(cfg.WINDOW_W), 0.0),
            (0.0, float(cfg.WINDOW_H)),
            (float(cfg.WINDOW_W), float(cfg.WINDOW_H)),
        )
        for i in range(N_PARTICLES):
            cx, cy = corners[i % 4]
            # Jitter the start position a little inside the corner so the
            # motes don't all overlap at the exact pixel.
            sx = cx + rng().uniform(-30.0, 30.0) * (1.0 if cx == 0.0 else -1.0)
            sy = cy + rng().uniform(-30.0, 30.0) * (1.0 if cy == 0.0 else -1.0)
            delay = (i / N_PARTICLES) * 0.22      # 0 -> ~0.22 s stagger
            self._particles.append(_Particle(sx, sy, delay))

        if self.reduced_motion:
            # Instant: fire the peak immediately and finish so the caller's
            # ascension happens without the animation.
            self._phase = _DONE
            self._peak_flag = True
        else:
            self._phase = _DIM

    def reset(self) -> None:
        """Return to idle (used after the caller consumes the ceremony)."""
        self._phase = _IDLE
        self._t = 0.0
        self._peak_flag = False
        self._tier_name = ""
        self._stat_mult = 1.0
        self._elixir_gained = 0
        self._particles = []
        self._tier_img = None
        self._mult_img = None

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance the ceremony by ``dt`` seconds.

        Call once per frame.  After this returns, check ``peak`` (to perform
        the actual ascension + reset) and then call ``draw``.
        """
        self._peak_flag = False
        if self._phase == _IDLE or self._phase == _DONE:
            return

        self._t += dt

        if self._phase == _DIM:
            if self._t >= T_DIM:
                self._phase = _CONVERGE
                self._t = 0.0
        elif self._phase == _CONVERGE:
            self._update_particles(dt)
            if self._t >= T_CONVERGE:
                self._phase = _REVEAL
                self._t = 0.0
                # The reveal is the visual climax: fire the one-frame peak
                # flag so the caller performs the actual ascension now.
                self._peak_flag = True
        elif self._phase == _REVEAL:
            if self._t >= T_REVEAL:
                self._phase = _REWIND
                self._t = 0.0
        elif self._phase == _REWIND:
            if self._t >= T_REWIND:
                self._phase = _DONE
                self._t = 0.0

    def _update_particles(self, dt: float) -> None:
        """Advance the converging motes for one tick.

        Each mote eases from its corner toward the screen centre; its life
        ticks down so the renderer can fade it.  The swarm is rebuilt once
        (at ``start``); here we only mutate positions/lives.
        """
        cx = cfg.WINDOW_W * 0.5
        cy = cfg.WINDOW_H * 0.5
        for p in self._particles:
            if p.delay > 0.0:
                p.delay -= dt
                continue
            # Fraction of converge progress for this mote (0 -> 1).
            prog = 1.0 - clamp(p.life / p.max_life, 0.0, 1.0)
            # Ease toward the centre: the mote accelerates as it nears it.
            ease = ease_out_cubic(prog)
            p.x = p.sx + (cx - p.sx) * ease
            p.y = p.sy + (cy - p.sy) * ease
            p.life -= dt

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface, base_draw: callable) -> None:
        """Draw the underlying screen, then overlay the ceremony.

        ``base_draw`` is a zero-arg callable that renders the current
        screen (the caller decides *which* screen is "current").  This
        module then overlays the dim veil, converging particles, reveal
        text, and rewind sweep on top.

        Outside an active ceremony this just calls the drawable and
        returns -- zero overhead.
        """
        base_draw()

        if self._phase == _IDLE or self._phase == _DONE:
            return

        if self._phase == _DIM:
            self._draw_dim(surf)
        elif self._phase == _CONVERGE:
            self._draw_dim(surf)
            self._draw_particles(surf)
        elif self._phase == _REVEAL:
            self._draw_dim(surf)
            self._draw_particles(surf)
            self._draw_reveal(surf)
        elif self._phase == _REWIND:
            self._draw_dim(surf)
            self._draw_rewind(surf)

    # ------------------------------------------------------------------
    # Phase renderers
    # ------------------------------------------------------------------
    def _draw_dim(self, surf: pygame.Surface) -> None:
        """Overlay the deep-indigo dim veil.

        The veil ramps from 0 -> ~210 alpha over the dim phase, then holds
        for the rest of the ceremony (converge/reveal/rewind) so the
        underlying screen stays darkened under the FX.  The dim surface is
        a plain (non-SRCALPHA) full-screen Surface created once and reused;
        only ``set_alpha`` is called per frame.
        """
        # Ramp during the dim phase, then hold.
        if self._phase == _DIM:
            p = self._t / T_DIM
        else:
            p = 1.0
        p = clamp(p, 0.0, 1.0)
        # Ease the ramp so the dim settles smoothly.
        p = p * p * (3 - 2 * p)
        alpha = int(210 * p)
        if alpha <= 0:
            return
        veil = self._get_dim()
        veil.set_alpha(alpha)
        surf.blit(veil, (0, 0))

    def _draw_particles(self, surf: pygame.Surface) -> None:
        """Draw the converging elixir motes.

        Each mote is a translucent elixir-coloured circle drawn via the
        reusable particle scratch (cleared per mote).  The scratch is
        SRCALPHA so the circle's alpha blends correctly when blitted onto
        the opaque screen; the screen itself is non-SRCALPHA so direct
        ``pygame.draw.circle`` with a 4-tuple would *replace* rather than
        blend -- the scratch + blit path is what gives real translucency.
        The motes shrink + fade as they near the centre.
        """
        s = self._get_particle_scratch()
        mid = _SCRATCH_PARTICLE // 2
        for p in self._particles:
            if p.life <= 0.0:
                continue
            # Fade by remaining life; shrink as the mote nears the centre.
            life_frac = clamp(p.life / p.max_life, 0.0, 1.0)
            a = int(220 * life_frac)
            if a <= 0:
                continue
            r = max(1, int(p.size * (0.4 + 0.6 * life_frac)))
            # Cap the radius to the scratch.
            if r > mid - 1:
                r = mid - 1
            s.fill((0, 0, 0, 0))
            pygame.draw.circle(s, (*ELIXIR, a), (mid, mid), r)
            surf.blit(s, (int(p.x) - mid, int(p.y) - mid))

    def _draw_reveal(self, surf: pygame.Surface) -> None:
        """Draw the reveal: tier name slam-in + stat multiplier + flash.

        The tier name scales from 1.6x down to 1.0x with an ease-out over
        the first ~0.35 s of the reveal (the "slam in"), then holds at full
        size with full alpha for the rest of the reveal.  The stat
        multiplier appears just below, fading in after the slam.  A short
        radial flash (expanding elixir shockwave ring) marks the peak.

        The text images are pre-rendered once at ``start``; here we only
        ``smoothscale`` + ``set_alpha`` + ``blit`` them.  ``smoothscale``
        at 1.0x is a near-noop (~3 ms / 1000 calls), and the slam ramp is
        short, so the per-frame cost is small.
        """
        p = clamp(self._t / T_REVEAL, 0.0, 1.0)

        # --- Tier name: slam in (1.6x -> 1.0x) over the first 0.35 s,
        # then hold.  The scale eases out so the name decelerates as it
        # lands.  Alpha ramps in over the same window.
        slam_frac = clamp(self._t / 0.35, 0.0, 1.0)
        slam_ease = ease_out_cubic(slam_frac)
        scale = 1.6 - 0.6 * slam_ease           # 1.6 -> 1.0
        tier_alpha = int(255 * slam_ease)

        if self._tier_img is not None and tier_alpha > 0:
            tw = max(1, int(self._tier_w * scale))
            th = max(1, int(self._tier_h * scale))
            img = pygame.transform.smoothscale(self._tier_img, (tw, th))
            img.set_alpha(tier_alpha)
            surf.blit(img, img.get_rect(
                center=(cfg.WINDOW_W // 2, cfg.WINDOW_H // 2 - 30)))

        # --- Stat multiplier: fade in after the slam (0.25 s -> end).
        mult_frac = clamp((self._t - 0.25) / 0.45, 0.0, 1.0)
        mult_alpha = int(255 * ease_out_cubic(mult_frac))
        if self._mult_img is not None and mult_alpha > 0:
            # Use the pre-rendered image; only set_alpha + blit per frame.
            self._mult_img.set_alpha(mult_alpha)
            surf.blit(self._mult_img, self._mult_img.get_rect(
                center=(cfg.WINDOW_W // 2, cfg.WINDOW_H // 2 + 18)))

        # --- Radial flash: expanding elixir shockwave ring at the peak.
        # Fires over the first ~0.40 s of the reveal; expands outward and
        # fades.  Drawn via the reusable flash scratch (cleared per frame).
        flash_life = 0.40 - self._t
        if flash_life > 0.0:
            fp = 1.0 - (flash_life / 0.40)         # 0 -> 1
            radius = int(20 + 100 * ease_out_cubic(fp))
            if radius > _FLASH_MAX_R:
                radius = _FLASH_MAX_R
            alpha = int(220 * (1.0 - fp))
            if alpha > 0 and radius > 0:
                s = self._get_flash_scratch()
                s.fill((0, 0, 0, 0))
                mid = _SCRATCH_FLASH // 2
                # Filled disc (faint) + ring (brighter) for the shockwave.
                pygame.draw.circle(s, (*ELIXIR, alpha // 4),
                                   (mid, mid), radius)
                pygame.draw.circle(s, (*ELIXIR_BRIGHT, alpha),
                                   (mid, mid), radius, max(2, radius // 8))
                surf.blit(s, (cfg.WINDOW_W // 2 - mid,
                              cfg.WINDOW_H // 2 - mid))

    def _draw_rewind(self, surf: pygame.Surface) -> None:
        """Draw the rewind: a quick horizontal sweep that wipes the road.

        An elixir-coloured band enters from the right edge and sweeps to
        the left over the rewind phase, then fades out.  The band is a
        plain (non-SRCALPHA) Surface created once and reused; only
        ``set_alpha`` + ``blit`` run per frame.  The band is narrow
        (~90 px) so the sweep reads as a fast wipe rather than a fill.

        The "rewind" metaphor: the band moves right-to-left (the reverse
        of the normal left-to-right road direction), suggesting the run
        is being rewound back to the start.
        """
        p = clamp(self._t / T_REWIND, 0.0, 1.0)
        # Position: right edge -> left edge over the phase.
        band_w = 90
        # Ease so the sweep decelerates as it exits.
        sweep = ease_out_cubic(p)
        x = int(cfg.WINDOW_W - band_w - sweep * (cfg.WINDOW_W - band_w))
        # Alpha: ramp in over the first 30%, hold 30%-70%, ramp out 70%-100%.
        if p < 0.30:
            a = int(220 * (p / 0.30))
        elif p > 0.70:
            a = int(220 * ((1.0 - p) / 0.30))
        else:
            a = 220
        a = int(clamp(a, 0, 220))
        if a <= 0:
            return
        band = self._get_rewind()
        band.set_alpha(a)
        surf.blit(band, (x, 0))

    # ------------------------------------------------------------------
    # Internals -- lazy reusable surfaces
    # ------------------------------------------------------------------
    def _get_dim(self) -> pygame.Surface:
        """Reusable full-screen dim veil (plain Surface, set_alpha'd per frame).

        Plain (non-SRCALPHA) so ``set_alpha`` gives a uniform global fade
        when blitted over the opaque screen -- the classic dim technique.
        Created once; reused every frame.
        """
        if self._dim is None:
            self._dim = pygame.Surface(
                (cfg.WINDOW_W, cfg.WINDOW_H)).convert()
            self._dim.fill(DIM_COLOR)
        return self._dim

    def _get_particle_scratch(self) -> pygame.Surface:
        """Reusable SRCALPHA scratch for one particle glow.

        Cleared per mote; never reallocated in the loop.
        """
        if self._particle_scratch is None:
            self._particle_scratch = pygame.Surface(
                (_SCRATCH_PARTICLE, _SCRATCH_PARTICLE),
                pygame.SRCALPHA).convert_alpha()
        return self._particle_scratch

    def _get_flash_scratch(self) -> pygame.Surface:
        """Reusable SRCALPHA scratch for the reveal shockwave ring.

        Cleared per frame; never reallocated in the loop.
        """
        if self._flash_scratch is None:
            self._flash_scratch = pygame.Surface(
                (_SCRATCH_FLASH, _SCRATCH_FLASH),
                pygame.SRCALPHA).convert_alpha()
        return self._flash_scratch

    def _get_rewind(self) -> pygame.Surface:
        """Reusable rewind band (plain Surface, set_alpha'd per frame).

        Plain (non-SRCALPHA) so ``set_alpha`` gives a uniform fade when
        blitted over the screen.  The band is a tall narrow elixir strip
        (the sweep).  Created once; reused every frame.
        """
        if self._rewind is None:
            band_w = 90
            self._rewind = pygame.Surface(
                (band_w, cfg.WINDOW_H)).convert()
            self._rewind.fill(ELIXIR)
        return self._rewind
