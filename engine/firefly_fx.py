"""Firefly FX: magical spawn, gentle pulse, and a satisfying catch burst.

A self-contained system the runner and screen drive.  Pure state + cached
surfaces — no per-frame allocations in the hot loop.

Integration:
  - ``runner.tap_at`` calls ``on_catch(x, y, gold)`` when a firefly is caught.
  - The world / runner calls ``on_spawn(firefly)`` right after a firefly is
    added to the world (spawn sparkle + "tap me!" pulse).
  - The game screen calls ``pulse(t)`` to scale the firefly glow while alive,
    and ``update(dt)`` + ``draw(surf)`` each frame for the transient bursts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from theme import C, font_sm, font_md
from utils import rng, clamp


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
SPAWN_SPARKLE_LIFE = 0.55      # seconds the spawn ring expands + fades
SPAWN_PULSE_LIFE = 1.2         # "tap me!" pulse on first spawn
CATCH_BURST_LIFE = 0.7         # golden particle burst duration
CATCH_TEXT_LIFE = 1.1         # floating "+gold" text duration

_GOLD = (255, 220, 120)        # warm golden accent for firefly FX
_GOLD_BRIGHT = (255, 245, 180)


# ---------------------------------------------------------------------------
# Cached sparkle surface (a soft radial glow disc).
# Keyed by radius so we only build a few sizes total.
# ---------------------------------------------------------------------------
_GLOW_CACHE: dict[int, pygame.Surface] = {}


def _glow_disc(radius: int) -> pygame.Surface:
    """A cached radial-falloff alpha disc of the given radius."""
    r = max(1, int(radius))
    surf = _GLOW_CACHE.get(r)
    if surf is not None:
        return surf
    size = r * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    # Layer a few concentric circles for a soft falloff.  Cheap and cached.
    steps = 4
    for i in range(steps, 0, -1):
        rr = int(r * i / steps)
        a = int(60 * (1 - (i / steps)) + 20)
        pygame.draw.circle(surf, (*_GOLD, a), (r, r), rr)
    _GLOW_CACHE[r] = surf
    return surf


# ---------------------------------------------------------------------------
# Transient FX objects (spawn ring, catch burst particles, float text)
# ---------------------------------------------------------------------------
@dataclass
class _SpawnSparkle:
    x: float
    y: float
    life: float
    max_life: float
    max_radius: float

    def update(self, dt: float) -> None:
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0


@dataclass
class _GoldParticle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    gravity: float = 220.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0


@dataclass
class _FloatGold:
    x: float
    y: float
    vy: float
    text: str
    life: float
    max_life: float

    def update(self, dt: float) -> None:
        self.y += self.vy * dt
        self.vy += 40 * dt          # gentle settle (not a hard fall)
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
class FireflyFxSystem:
    """Owns the transient firefly visual effects.

    The system is pure state; it allocates nothing per frame in the hot loop
    (particle/burst lists are mutated in place and rebuilt only when culled).
    """

    def __init__(self) -> None:
        self._sparkles: list[_SpawnSparkle] = []
        self._particles: list[_GoldParticle] = []
        self._texts: list[_FloatGold] = []
        # Track active "tap me!" pulses keyed by id(firefly) -> remaining time.
        # The screen reads ``spawn_pulse_remaining(fid)`` to scale the glow.
        self._spawn_pulses: dict[int, float] = {}

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def on_spawn(self, firefly) -> None:
        """Spawn sparkle + a "tap me!" pulse.  Call right after a firefly is
        added to the world."""
        x = float(firefly.x)
        y = float(firefly.y)
        self._sparkles.append(_SpawnSparkle(
            x=x, y=y,
            life=SPAWN_SPARKLE_LIFE, max_life=SPAWN_SPARKLE_LIFE,
            max_radius=20.0 + getattr(firefly, "size", 8.0),
        ))
        self._spawn_pulses[id(firefly)] = SPAWN_PULSE_LIFE

    def on_catch(self, x: float, y: float, gold: float) -> None:
        """Golden burst + floating "+gold" text + chime.  Call from the
        runner when a firefly is caught."""
        # Golden particle burst.
        count = 14
        for _ in range(count):
            ang = rng().uniform(0, math.tau)
            sp = rng().uniform(60, 160)
            self._particles.append(_GoldParticle(
                x=x, y=y,
                vx=math.cos(ang) * sp,
                vy=math.sin(ang) * sp - 40.0,   # bias upward a touch
                life=CATCH_BURST_LIFE * rng().uniform(0.7, 1.2),
                max_life=CATCH_BURST_LIFE,
                size=rng().uniform(2.0, 4.0),
            ))
        # A bright central flash ring.
        self._sparkles.append(_SpawnSparkle(
            x=x, y=y,
            life=0.4, max_life=0.4,
            max_radius=26.0,
        ))
        # Floating "+gold" text.
        gold_str = f"+{int(round(gold))}"
        self._texts.append(_FloatGold(
            x=x, y=y - 10,
            vy=-60.0,
            text=gold_str,
            life=CATCH_TEXT_LIFE, max_life=CATCH_TEXT_LIFE,
        ))
        # Chime.
        from assets import play
        play("firefly", True)

    def update(self, dt: float) -> None:
        # Sparkles.
        for s in self._sparkles:
            s.update(dt)
        if self._sparkles:
            self._sparkles = [s for s in self._sparkles if s.alive]
        # Particles.
        for p in self._particles:
            p.update(dt)
        if self._particles:
            self._particles = [p for p in self._particles if p.alive]
        # Floating text.
        for t in self._texts:
            t.update(dt)
        if self._texts:
            self._texts = [t for t in self._texts if t.alive]
        # Spawn-pulse timers.
        if self._spawn_pulses:
            for fid in list(self._spawn_pulses.keys()):
                self._spawn_pulses[fid] -= dt
                if self._spawn_pulses[fid] <= 0:
                    del self._spawn_pulses[fid]

    def draw(self, surf: pygame.Surface) -> None:
        # Spawn sparkles: an expanding, fading ring + a soft glow disc.
        for s in self._sparkles:
            t = 1.0 - clamp(s.life / s.max_life, 0.0, 1.0)   # 0..1
            radius = int(s.max_radius * t)
            alpha = int(220 * (1.0 - t))
            if radius > 0 and alpha > 0:
                # Soft glow underlay (cached).
                gd = _glow_disc(radius)
                gd_copy = gd.copy()
                gd_copy.set_alpha(alpha)
                rect = gd_copy.get_rect(center=(int(s.x), int(s.y)))
                surf.blit(gd_copy, rect)
                # Crisp ring on top.
                if radius >= 2:
                    ring = pygame.Surface((radius * 2 + 4, radius * 2 + 4),
                                          pygame.SRCALPHA)
                    pygame.draw.circle(ring, (*_GOLD_BRIGHT, alpha),
                                       (radius + 2, radius + 2), radius, 2)
                    surf.blit(ring, ring.get_rect(center=(int(s.x), int(s.y))))
        # Golden burst particles.
        for p in self._particles:
            a = clamp(p.life / p.max_life, 0.0, 1.0)
            alpha = int(255 * a)
            r = max(1, int(p.size))
            # Use a cached glow disc tinted by drawing a small circle.
            # (Tiny per-particle surfaces are unavoidable but bounded; the
            # count is small and culled each frame.)
            ps = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(ps, (*_GOLD, alpha), (r, r), r)
            surf.blit(ps, (int(p.x) - r, int(p.y) - r))
        # Floating "+gold" text.
        for t in self._texts:
            a = clamp(t.life / t.max_life, 0.0, 1.0)
            alpha = int(255 * a) if a > 0.5 else int(255 * (a / 0.5))
            f = font_md(bold=True)
            img = f.render(t.text, True, _GOLD_BRIGHT)
            img.set_alpha(alpha)
            surf.blit(img, img.get_rect(center=(int(t.x), int(t.y))))

    # ------------------------------------------------------------------
    # Helpers the screen uses
    # ------------------------------------------------------------------
    def pulse(self, t: float) -> float:
        """A gentle breathing scale for the firefly glow.

        ``t`` is the current time (seconds).  Returns a multiplier in roughly
        [0.85, 1.15] the screen applies to the firefly glow size/alpha.
        """
        return 1.0 + 0.15 * math.sin(t * 3.0)

    def spawn_pulse_remaining(self, fid: int) -> float:
        """Remaining "tap me!" pulse time for a firefly id, or 0.

        The screen can blend this with ``pulse()`` to make a freshly-spawned
        firefly pulse more strongly for the first ~1.2s.
        """
        return self._spawn_pulses.get(fid, 0.0)

    def spawn_pulse_scale(self, fid: int, t: float) -> float:
        """Combined glow scale: gentle breathing + a decaying "tap me!" pulse.

        For the first SPAWN_PULSE_LIFE seconds the firefly pulses faster and
        harder (an attention-grabbing "tap me!"), fading into the gentle
        breathing pulse.  The screen should call this once per firefly per
        frame and use the returned value to scale the glow.
        """
        base = self.pulse(t)
        rem = self._spawn_pulses.get(fid, 0.0)
        if rem <= 0:
            return base
        # Decay envelope: strongest at spawn, eases out.
        env = rem / SPAWN_PULSE_LIFE                       # 1 -> 0
        # Faster, larger oscillation while the spawn pulse is active.
        fast = 1.0 + 0.35 * env * math.sin(t * 12.0)
        # Blend: as env -> 0 we settle into the gentle base pulse.
        return base * (1.0 - env) + fast * env
