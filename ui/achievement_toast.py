"""Achievement toast system: slide-in reward cards for unlocked achievements.

Replaces the plain one-line ``Runner.notify`` for achievement unlocks with
a polished slide-in card from the top-right: the achievement name, a
medal/amber reward line, a brief glow on arrival, and a small particle
burst.  Up to 3 toasts stack vertically; each has its own life timer and
slides back out to the right when it expires.

Integration (see docs/specs/achievement_toast.md):
  * ``main.py`` owns one ``AchievementToastSystem``, ticks it once per
    frame, and draws it *after* the active screen so it overlays every
    screen (achievements can unlock while the player browses
    buildings/upgrades/etc, not just on the game screen).
  * ``Runner.update`` calls ``show(achievement)`` for each newly-unlocked
    achievement returned by ``core.quests.check_achievements``.

All rendering uses pygame primitives + the cached theme fonts.  Transient
state lives in a fixed-size particle pool; text surfaces are rendered once
at ``show`` time and reused; the glow halo is cached by card size -- so
neither ``update`` nor ``draw`` allocates after warmup.
"""
from __future__ import annotations

import math

import pygame

import config as cfg
from theme import C, font_sm, font_md
from utils import clamp, ease_out_cubic, rng


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_SLIDE_IN = 0.30        # seconds to slide in from the right edge
_HOLD = 3.00            # seconds the card sits at rest
_SLIDE_OUT = 0.40       # seconds to slide back out to the right
_GLOW_DUR = 0.80        # arrival glow duration (fades from slide-in start)
_CARD_W = 300
_CARD_H = 68
_GAP = 8
_TOP_Y = 104            # first card's top Y (just below the HUD strip)
_RIGHT_MARGIN = 12
_MAX_TOASTS = 3
_ICON_R = 12
_PARTICLE_COUNT = 14    # particles per arrival burst
_MAX_PARTICLES = 48     # pool cap (>= max concurrent bursts)
_PARTICLE_SURF = 16     # reusable particle scratch size (square)

_AMBER_COLOR = (255, 180, 60)
_MEDAL_COLOR = (220, 220, 240)
_GOLD_COLOR = (255, 220, 120)
_TRANSPARENT = (0, 0, 0, 0)


def _ease_in_cubic(t: float) -> float:
    """Accelerating ease-in (matches the slide-out 'whoosh' off-screen)."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * t


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# Cached glow halo (soft rounded-rect bloom), keyed by (w, h).
# Built once per card size; reused forever.
# ---------------------------------------------------------------------------
_GLOW_CACHE: dict[tuple[int, int], pygame.Surface] = {}


def _glow_surface(w: int, h: int) -> pygame.Surface:
    key = (w, h)
    surf = _GLOW_CACHE.get(key)
    if surf is not None:
        return surf
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    # A few concentric rounded rects with falling alpha for a soft bloom.
    steps = 5
    for i in range(steps):
        inflate = -i * 6
        r = pygame.Rect(0, 0, w, h).inflate(inflate, inflate)
        if r.w > 0 and r.h > 0:
            a = int(46 * (1 - i / steps) + 8)
            pygame.draw.rect(surf, (*C.gold, a), r, border_radius=18)
    _GLOW_CACHE[key] = surf
    return surf


# ---------------------------------------------------------------------------
# Pooled particle (reused via an active flag; never re-allocated)
# ---------------------------------------------------------------------------
class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size",
                 "color", "gravity", "active")

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.life = 0.0
        self.max_life = 1.0
        self.size = 2.0
        self.color = _GOLD_COLOR
        self.gravity = 220.0
        self.active = False


# ---------------------------------------------------------------------------
# One toast card
# ---------------------------------------------------------------------------
class _Toast:
    __slots__ = ("name_surf", "reward_surf", "amber", "medals",
                 "life", "max_life", "y", "target_y", "index")

    def __init__(self, name_surf: pygame.Surface, reward_surf: pygame.Surface,
                 amber: int, medals: int, life: float, max_life: float,
                 y: float, target_y: float, index: int) -> None:
        self.name_surf = name_surf
        self.reward_surf = reward_surf
        self.amber = amber
        self.medals = medals
        self.life = life
        self.max_life = max_life
        self.y = y
        self.target_y = target_y
        self.index = index


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class AchievementToastSystem:
    """Owns the achievement toast cards + arrival particle bursts.

    The system is pure state; it allocates nothing per frame after warmup
    (particles live in a fixed pool, text surfaces are rendered once at
    ``show`` time, the glow halo is cached by card size, and a single
    reusable particle scratch surface is cleared + refilled per particle).

    Lifecycle::

        toasts = AchievementToastSystem()
        toasts.show(achievement)       # enqueue a card
        toasts.update(dt)              # advance slide-in / hold / slide-out
        toasts.draw(surf)              # overlay on top of everything
    """

    def __init__(self) -> None:
        self._toasts: list[_Toast] = []
        self._particles: list[_Particle] = [
            _Particle() for _ in range(_MAX_PARTICLES)
        ]
        # Reusable scratch surface for particles (cleared + refilled).
        self._particle_surf = pygame.Surface(
            (_PARTICLE_SURF, _PARTICLE_SURF), pygame.SRCALPHA
        )
        # One scratch rect for all blits (avoids per-blit tuple allocs).
        self._scratch = pygame.Rect(0, 0, 0, 0)
        # Set by the caller each frame from state.reduced_motion.
        self.reduced_motion: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show(self, achievement) -> None:
        """Enqueue a toast card for a newly-unlocked achievement.

        ``achievement`` is a ``data.quests.Achievement`` (or any object
        with ``name`` / ``reward_amber`` / ``reward_medals`` attributes).
        The newest card slides in at the top; older cards shift down.
        The stack is capped at ``_MAX_TOASTS`` (oldest dropped).
        """
        name = getattr(achievement, "name", "Achievement")
        amber = int(getattr(achievement, "reward_amber", 0) or 0)
        medals = int(getattr(achievement, "reward_medals", 0) or 0)

        # Render the text once and reuse the surfaces every frame.
        name_surf = font_md(bold=True).render(name, True, C.text)
        parts = []
        if amber > 0:
            parts.append(f"+{amber} amber")
        if medals > 0:
            parts.append(f"+{medals} medals")
        reward_str = "  ".join(parts) if parts else "Unlocked!"
        reward_surf = font_sm(bold=True).render(reward_str, True, C.gold)

        max_life = _SLIDE_IN + _HOLD + _SLIDE_OUT
        # New toast goes to the top (index 0); existing toasts shift down.
        toast = _Toast(
            name_surf, reward_surf, amber, medals,
            max_life, max_life, float(_TOP_Y), float(_TOP_Y), 0,
        )
        self._toasts.insert(0, toast)
        # Cap the stack: drop the oldest (now last) if over the limit.
        if len(self._toasts) > _MAX_TOASTS:
            self._toasts.pop()
        # Re-index + retarget after the insert/drop.
        self._reindex()

        # Arrival particle burst at the new (top) card's icon center.
        if not self.reduced_motion:
            bx = cfg.WINDOW_W - _CARD_W - _RIGHT_MARGIN + 28
            by = _TOP_Y + _CARD_H // 2
            self._burst(bx, by, amber, medals)

    def update(self, dt: float) -> None:
        """Advance every toast's life timer and ease Y toward its target.

        Each toast eases toward its slot Y so the stack reflows smoothly
        when a card is removed (no instant jumps).  Expired toasts are
        culled and the remaining cards are re-indexed.
        """
        # Toasts: life timers + smooth re-stack.
        for t in self._toasts:
            t.life -= dt
            t.y += (t.target_y - t.y) * min(1.0, dt * 10.0)
        # Cull expired; re-index if the stack changed.
        if self._toasts:
            before = len(self._toasts)
            self._toasts = [t for t in self._toasts if t.life > 0]
            if len(self._toasts) != before:
                self._reindex()
        # Particles (fixed pool; no compaction, just deactivate).
        for p in self._particles:
            if not p.active:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += p.gravity * dt
            p.life -= dt
            if p.life <= 0:
                p.active = False

    def draw(self, surf: pygame.Surface) -> None:
        """Draw all active toast cards on top of the current frame.

        Call this *after* the active screen has drawn so the toasts overlay
        every screen (game, buildings, upgrades, ...).
        """
        if self._toasts:
            rest_x = cfg.WINDOW_W - _CARD_W - _RIGHT_MARGIN
            off_x = float(cfg.WINDOW_W + 8)
            scratch = self._scratch
            for t in self._toasts:
                self._draw_card(surf, t, rest_x, off_x, scratch)
        # Particles draw on top of the cards (the burst reads as sparks
        # flying off the icon).
        self._draw_particles(surf)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _reindex(self) -> None:
        for i, t in enumerate(self._toasts):
            t.index = i
            t.target_y = _TOP_Y + i * (_CARD_H + _GAP)

    def _draw_card(self, surf: pygame.Surface, t: _Toast,
                   rest_x: int, off_x: float, scratch: pygame.Rect) -> None:
        elapsed = t.max_life - t.life
        # Phase + x position (slide-in -> hold -> slide-out).
        if elapsed < _SLIDE_IN:
            p = ease_out_cubic(clamp(elapsed / _SLIDE_IN, 0.0, 1.0))
            x = _lerp(off_x, float(rest_x), p)
            text_alpha = int(255 * p)
        elif elapsed < _SLIDE_IN + _HOLD:
            x = float(rest_x)
            text_alpha = 255
        else:
            p = _ease_in_cubic(
                clamp((elapsed - _SLIDE_IN - _HOLD) / _SLIDE_OUT, 0.0, 1.0)
            )
            x = _lerp(float(rest_x), off_x, p)
            text_alpha = int(255 * (1.0 - p))
        if x >= cfg.WINDOW_W:
            # Fully off the right edge -- nothing to draw.
            return
        y = int(t.y)
        rect = pygame.Rect(int(x), y, _CARD_W, _CARD_H)

        # Arrival glow (fades over _GLOW_DUR from the slide-in start).
        if not self.reduced_motion and elapsed < _GLOW_DUR:
            glow_alpha = int(190 * (1.0 - elapsed / _GLOW_DUR))
            if glow_alpha > 0:
                g = _glow_surface(_CARD_W + 24, _CARD_H + 24)
                g.set_alpha(glow_alpha)
                scratch.x = rect.x - 12
                scratch.y = rect.y - 12
                surf.blit(g, scratch)

        # Card body + hi border.
        pygame.draw.rect(surf, C.panel, rect, border_radius=10)
        pygame.draw.rect(surf, C.panel_border_hi, rect, 2, border_radius=10)

        # Left gold accent stripe -- the "achievement" feel.
        stripe = pygame.Rect(rect.x, rect.y + 6, 4, rect.h - 12)
        pygame.draw.rect(surf, C.gold, stripe, border_radius=2)

        # Medal / amber icon.
        ix = rect.x + 28
        iy = rect.centery
        if t.amber > 0:
            pygame.draw.circle(surf, _AMBER_COLOR, (ix, iy), _ICON_R)
            pygame.draw.circle(surf, (255, 220, 140), (ix, iy), _ICON_R - 4)
            pygame.draw.circle(surf, C.panel_border, (ix, iy), _ICON_R, 1)
        else:
            pts = [(ix, iy - _ICON_R), (ix + _ICON_R, iy),
                   (ix, iy + _ICON_R), (ix - _ICON_R, iy)]
            pygame.draw.polygon(surf, _MEDAL_COLOR, pts)
            inner = _ICON_R - 4
            pygame.draw.polygon(
                surf, (255, 255, 255),
                [(ix, iy - inner), (ix + inner, iy),
                 (ix, iy + inner), (ix - inner, iy)],
            )

        # Name + reward (pre-rendered; just set_alpha + blit).
        if text_alpha < 255:
            t.name_surf.set_alpha(text_alpha)
            t.reward_surf.set_alpha(text_alpha)
        else:
            t.name_surf.set_alpha(255)
            t.reward_surf.set_alpha(255)
        surf.blit(t.name_surf, (rect.x + 52, rect.y + 10))
        surf.blit(t.reward_surf, (rect.x + 52, rect.y + 32))

    def _burst(self, x: float, y: float, amber: int, medals: int) -> None:
        """Fire a small gold/amber particle burst at the card icon.

        Reuses inactive pool slots; no new particle objects are created.
        """
        count = 0
        for p in self._particles:
            if p.active:
                continue
            ang = rng().uniform(0.0, math.tau)
            sp = rng().uniform(60.0, 170.0)
            p.x = float(x)
            p.y = float(y)
            p.vx = math.cos(ang) * sp
            p.vy = math.sin(ang) * sp - 30.0       # slight upward bias
            p.life = rng().uniform(0.45, 0.70)
            p.max_life = p.life
            p.size = rng().uniform(2.0, 4.0)
            p.color = _AMBER_COLOR if (amber > 0 and count % 2 == 0) else _GOLD_COLOR
            p.gravity = 220.0
            p.active = True
            count += 1
            if count >= _PARTICLE_COUNT:
                break

    def _draw_particles(self, surf: pygame.Surface) -> None:
        """Draw active particles with a single reusable scratch surface."""
        ps = self._particle_surf
        scratch = self._scratch
        center = _PARTICLE_SURF // 2
        for p in self._particles:
            if not p.active:
                continue
            a = int(255 * clamp(p.life / p.max_life, 0.0, 1.0))
            if a <= 0:
                continue
            r = max(2, int(p.size))
            ps.fill(_TRANSPARENT)
            pygame.draw.circle(ps, (*p.color, a), (center, center), r)
            scratch.x = int(p.x) - center
            scratch.y = int(p.y) - center
            surf.blit(ps, scratch)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        """True while any toast or particle is still animating."""
        return bool(self._toasts) or any(p.active for p in self._particles)

    def clear(self) -> None:
        self._toasts.clear()
        for p in self._particles:
            p.active = False
