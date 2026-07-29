"""Procedural asset generation for Tap Ninja.

ninja, enemies, fireflies, buildings, backgrounds — all pygame
primitives, no external image files.
"""
from __future__ import annotations

import math
import colorsys
from typing import Tuple

import pygame

import config as cfg
from utils import rng


def hsl(h: int, s: float, l: float) -> Tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


# === Ninja ===
_NINJA_CACHE: dict[int, pygame.Surface] = {}


def ninja_surface(size: int = 64) -> pygame.Surface:
    cached = _NINJA_CACHE.get(size)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    body = (40, 40, 60)
    headband = (220, 60, 60)
    skin = (220, 180, 150)
    pygame.draw.rect(surf, body, (cx - 14, cy - 6, 28, 26), border_radius=6)
    pygame.draw.circle(surf, skin, (cx, cy - 14), 10)
    pygame.draw.rect(surf, headband, (cx - 12, cy - 20, 24, 5))
    pygame.draw.rect(surf, headband, (cx + 8, cy - 22, 14, 3))
    pygame.draw.line(surf, (20, 20, 30), (cx - 5, cy - 14), (cx - 2, cy - 14), 2)
    pygame.draw.line(surf, (20, 20, 30), (cx + 2, cy - 14), (cx + 5, cy - 14), 2)
    pygame.draw.line(surf, (220, 220, 230), (cx - 18, cy - 2), (cx - 6, cy + 18), 3)
    pygame.draw.rect(surf, headband, (cx - 22, cy + 16, 8, 3))
    surf = surf.convert_alpha()
    _NINJA_CACHE[size] = surf
    return surf


# === Enemy ===
_ENEMY_CACHE: dict[tuple, pygame.Surface] = {}


def enemy_surface(edef, size: int = 48) -> pygame.Surface:
    key = (getattr(edef, "id", str(edef)), size)
    cached = _ENEMY_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    base = hsl(edef.hue, 0.6, 0.5)
    dark = hsl(edef.hue, 0.5, 0.30)
    light = hsl(edef.hue, 0.5, 0.7)
    cx, cy = size // 2, size // 2
    r = size // 3
    shape = edef.shape
    if shape == "bandit":
        pygame.draw.rect(surf, base, (cx - r, cy - 4, r * 2, r + 4), border_radius=4)
        pygame.draw.circle(surf, dark, (cx, cy - 8), r - 2)
        pygame.draw.rect(surf, (180, 40, 40), (cx - r + 2, cy - 12, r * 2 - 4, 3))
        pygame.draw.circle(surf, (255, 80, 80), (cx - 4, cy - 6), 2)
        pygame.draw.circle(surf, (255, 80, 80), (cx + 4, cy - 6), 2)
    elif shape in ("oni", "demon"):
        pygame.draw.rect(surf, base, (cx - r, cy - 4, r * 2, r + 4), border_radius=4)
        pygame.draw.polygon(surf, dark, [(cx - 8, cy - 4), (cx - 12, cy - 16), (cx - 4, cy - 8)])
        pygame.draw.polygon(surf, dark, [(cx + 8, cy - 4), (cx + 12, cy - 16), (cx + 4, cy - 8)])
        pygame.draw.circle(surf, (255, 240, 60), (cx - 4, cy - 2), 2)
        pygame.draw.circle(surf, (255, 240, 60), (cx + 4, cy - 2), 2)
    elif shape in ("yokai", "wraith"):
        ghost = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.ellipse(ghost, (*base, 180), (cx - r, cy - r, r * 2, r * 2))
        surf.blit(ghost, (0, 0))
        pygame.draw.circle(surf, (255, 255, 255), (cx - 4, cy - 4), 2)
        pygame.draw.circle(surf, (255, 255, 255), (cx + 4, cy - 4), 2)
    elif shape == "skeleton":
        pygame.draw.circle(surf, hsl(0, 0, 0.85), (cx, cy - 6), r - 2)
        pygame.draw.rect(surf, hsl(0, 0, 0.8), (cx - r + 4, cy + 2, r * 2 - 8, r))
        pygame.draw.circle(surf, (20, 0, 0), (cx - 4, cy - 6), 3)
        pygame.draw.circle(surf, (20, 0, 0), (cx + 4, cy - 6), 3)
    elif shape == "beast":
        pygame.draw.ellipse(surf, base, (cx - r, cy - r // 2, r * 2, r))
        pygame.draw.circle(surf, dark, (cx - r + 4, cy - 2), 6)
        pygame.draw.circle(surf, (255, 80, 80), (cx - r + 4, cy - 2), 2)
    elif shape == "golem":
        pygame.draw.rect(surf, base, (cx - r, cy - r + 2, r * 2, r * 2 - 2), border_radius=3)
        pygame.draw.rect(surf, dark, (cx - r, cy - r + 2, r * 2, 6))
        pygame.draw.rect(surf, light, (cx - 4, cy - 4, 8, 8))
    elif shape == "dragon":
        pygame.draw.ellipse(surf, base, (cx - r, cy - r // 2, r * 2, r + 4))
        pygame.draw.polygon(surf, dark, [(cx - r, cy), (cx - r - 8, cy - 8), (cx - r + 6, cy + 6)])
        pygame.draw.polygon(surf, light, [(cx, cy - 6), (cx + r, cy - 14), (cx + r, cy)])
        pygame.draw.circle(surf, (255, 200, 60), (cx - r + 4, cy), 2)
    else:
        pygame.draw.circle(surf, base, (cx, cy), r)
    surf = surf.convert_alpha()
    _ENEMY_CACHE[key] = surf
    return surf


# === Firefly ===
_FIREFLY_CACHE: dict[tuple, pygame.Surface] = {}


def firefly_surface(size: int = 10, hue: int = 60) -> pygame.Surface:
    key = (size, hue)
    cached = _FIREFLY_CACHE.get(key)
    if cached is not None:
        return cached
    s = pygame.Surface((size * 4, size * 4), pygame.SRCALPHA)
    cx = size * 2
    col = hsl(hue, 0.9, 0.7)
    for i in range(4):
        r = size * 2 - i * 3
        a = 60 - i * 12
        glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, a), (r, r), r)
        s.blit(glow, (cx - r, cx - r))
    pygame.draw.circle(s, col, (cx, cx), size // 2 + 1)
    pygame.draw.circle(s, (255, 255, 255), (cx, cx), max(1, size // 3))
    s = s.convert_alpha()
    _FIREFLY_CACHE[key] = s
    return s


# === Building icons ===
_BUILDING_CACHE: dict[tuple, pygame.Surface] = {}


def building_surface(bid: str, size: int = 48) -> pygame.Surface:
    key = (bid, size)
    cached = _BUILDING_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    roof = (180, 60, 60)
    wall = (60, 50, 50)
    if bid in ("farm", "sawmill", "mine"):
        pygame.draw.rect(surf, wall, (cx - 14, cy - 4, 28, 18))
        pygame.draw.polygon(surf, roof, [(cx - 16, cy - 4), (cx + 16, cy - 4), (cx, cy - 18)])
    elif bid in ("tavern", "blacksmith", "barracks"):
        pygame.draw.rect(surf, wall, (cx - 16, cy - 6, 32, 22))
        pygame.draw.rect(surf, roof, (cx - 18, cy - 8, 36, 5))
    elif bid == "dojo":
        pygame.draw.rect(surf, (200, 80, 80), (cx - 16, cy - 2, 4, 22))
        pygame.draw.rect(surf, (200, 80, 80), (cx + 12, cy - 2, 4, 22))
        pygame.draw.rect(surf, (200, 80, 80), (cx - 20, cy - 6, 40, 5))
        pygame.draw.rect(surf, (200, 80, 80), (cx - 18, cy - 14, 36, 4))
    else:
        for i in range(3):
            w = 30 - i * 6
            y = cy - 6 + i * 8
            pygame.draw.rect(surf, wall, (cx - w // 2, y, w, 6))
            pygame.draw.polygon(surf, roof, [(cx - w // 2 - 2, y), (cx + w // 2 + 2, y), (cx, y - 6)])
    surf = surf.convert_alpha()
    _BUILDING_CACHE[key] = surf
    return surf


# === Pet icons ===
_PET_CACHE: dict[tuple, pygame.Surface] = {}


def pet_surface(pid: str, hue: int, size: int = 40) -> pygame.Surface:
    key = (pid, size)
    cached = _PET_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    col = hsl(hue, 0.6, 0.55)
    pygame.draw.ellipse(surf, col, (cx - 12, cy - 6, 24, 18))
    pygame.draw.circle(surf, col, (cx - 10, cy - 8), 5)
    pygame.draw.circle(surf, col, (cx + 10, cy - 8), 5)
    pygame.draw.circle(surf, (20, 20, 30), (cx - 5, cy - 2), 2)
    pygame.draw.circle(surf, (20, 20, 30), (cx + 5, cy - 2), 2)
    surf = surf.convert_alpha()
    _PET_CACHE[key] = surf
    return surf


# === Background ===
_BG_CACHE: dict[tuple, pygame.Surface] = {}


def background(zone_index: int, zone_hue: int) -> pygame.Surface:
    key = ("bg", zone_index, zone_hue)
    cached = _BG_CACHE.get(key)
    if cached is not None:
        return cached
    from theme import C, gradient_v
    surf = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H)).convert()
    sky_top = hsl(zone_hue, 0.5, 0.15)
    sky_bottom = hsl(zone_hue, 0.4, 0.25)
    gradient_v(surf, pygame.Rect(0, 0, cfg.WINDOW_W, cfg.ROAD_TOP), sky_top, sky_bottom)
    pygame.draw.circle(surf, (240, 235, 220), (cfg.WINDOW_W - 120, 50), 28)
    moon = pygame.Surface((70, 70), pygame.SRCALPHA)
    pygame.draw.circle(moon, (240, 235, 220, 60), (35, 35), 34)
    surf.blit(moon, (cfg.WINDOW_W - 155, 15))
    for _ in range(60):
        x = rng().randint(0, cfg.WINDOW_W)
        y = rng().randint(0, cfg.ROAD_TOP - 10)
        b = rng().randint(120, 200)
        surf.set_at((x, y), (b, b, min(255, b + 30)))
    hill_col = hsl(zone_hue, 0.4, 0.18)
    pts = [(0, cfg.ROAD_TOP)]
    x = 0
    while x < cfg.WINDOW_W + 40:
        pts.append((x, cfg.ROAD_TOP - 30 - (math.sin(x * 0.02) * 20 + 20)))
        x += 40
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(surf, hill_col, pts)
    mid_col = hsl(zone_hue, 0.45, 0.13)
    pts = [(0, cfg.ROAD_TOP)]
    x = 0
    while x < cfg.WINDOW_W + 60:
        pts.append((x, cfg.ROAD_TOP - 14 - (math.sin(x * 0.035 + 1.2) * 12 + 12)))
        x += 60
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(surf, mid_col, pts)
    pygame.draw.rect(surf, C.road, (0, cfg.ROAD_TOP, cfg.WINDOW_W, cfg.ROAD_H))
    pygame.draw.rect(surf, C.road_edge, (0, cfg.ROAD_TOP, cfg.WINDOW_W, 4))
    pygame.draw.rect(surf, C.road_edge, (0, cfg.ROAD_BOTTOM - 4, cfg.WINDOW_W, 4))
    for x in range(0, cfg.WINDOW_W, 60):
        pygame.draw.rect(surf, C.lane_line, (x + 20, cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2, 30, 4))
    for x in range(80, cfg.WINDOW_W, 200):
        pygame.draw.rect(surf, (40, 30, 30), (x, cfg.ROAD_TOP - 8, 3, 10))
        pygame.draw.circle(surf, (255, 140, 60), (x + 1, cfg.ROAD_TOP - 12), 5)
        glow = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 140, 60, 40), (12, 12), 12)
        surf.blit(glow, (x - 11, cfg.ROAD_TOP - 24))
    _BG_CACHE[key] = surf
    return surf


# === Parallax layers (Task 29 / gfx-parallax) ===
# 5 pre-baked scrollable background layers (sky, far hills, mid hills,
# near foliage, road) blit at parallax offsets [0, 0.15, 0.35, 0.6, 1.0]
# from a single scroll accumulator. Cached per (zone_in_cycle, hue) so
# the cache is bounded (9 zones x hues x 5 layers, not unbounded across
# cycles). Each layer is a full-screen SRCALPHA surface; scrollable
# layers tile horizontally at WINDOW_W so they wrap seamlessly.
_PARALLAX_CACHE: dict[tuple, list] = {}


def parallax_layers(zone_index: int, hue: int) -> list:
    """Return 5 cached parallax background layers.

    Layers (in draw order, with their parallax offsets):
      0. Sky         (offset 0.0  — no scroll; gradient + moon + stars)
      1. Far hills   (offset 0.15 — scrolls slowly; tileable silhouette)
      2. Mid hills   (offset 0.35 — scrolls medium; tileable silhouette)
      3. Near foliage(offset 0.6  — scrolls faster; bushes + torches)
      4. Road        (offset 1.0  — scrolls full; road rect + lane lines)

    Each layer is a full-screen (WINDOW_W x WINDOW_H) SRCALPHA surface
    cached per (zone_in_cycle, hue) with ``convert_alpha`` so the cache
    is bounded (9 zones x hues, not unbounded across cycles). The
    scrollable layers (1-4) use sine frequencies that are integer
    multiples of 2*pi/WINDOW_W so the hill silhouettes tile seamlessly
    at WINDOW_W (the y at x=0 and x=WINDOW_W match, so wrapping is
    invisible). The caller blits each layer at ``-int(scroll * offset)
    % WINDOW_W`` and ``- int(scroll * offset) % WINDOW_W - WINDOW_W`` to
    cover the screen.
    """
    in_cycle = zone_index % 9
    key = ("parallax", in_cycle, hue)
    cached = _PARALLAX_CACHE.get(key)
    if cached is not None:
        return cached
    from theme import C, gradient_v
    layers = []
    # Layer 0: Sky (offset 0, no scroll). Gradient + moon + stars in the
    # top portion (0..ROAD_TOP); transparent below so the hill + road
    # layers composite underneath.
    sky = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    sky_top = hsl(hue, 0.5, 0.15)
    sky_bottom = hsl(hue, 0.4, 0.25)
    gradient_v(sky, pygame.Rect(0, 0, cfg.WINDOW_W, cfg.ROAD_TOP),
               sky_top, sky_bottom)
    pygame.draw.circle(sky, (240, 235, 220), (cfg.WINDOW_W - 120, 50), 28)
    moon = pygame.Surface((70, 70), pygame.SRCALPHA)
    pygame.draw.circle(moon, (240, 235, 220, 60), (35, 35), 34)
    sky.blit(moon, (cfg.WINDOW_W - 155, 15))
    for _ in range(60):
        x = rng().randint(0, cfg.WINDOW_W)
        y = rng().randint(0, cfg.ROAD_TOP - 10)
        b = rng().randint(120, 200)
        sky.set_at((x, y), (b, b, min(255, b + 30)))
    layers.append(sky.convert_alpha())
    # Layer 1: Far hills (offset 0.15, tileable at WINDOW_W). The hill
    # line uses sin(x * 2*pi*4/WINDOW_W) so 4 peaks tile seamlessly.
    fh = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    hill_col = hsl(hue, 0.4, 0.18)
    pts = [(0, cfg.ROAD_TOP)]
    for x in range(0, cfg.WINDOW_W + 1, 20):
        y = cfg.ROAD_TOP - 30 - (math.sin(x * 2 * math.pi * 4 / cfg.WINDOW_W) * 20 + 20)
        pts.append((x, y))
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(fh, hill_col, pts)
    layers.append(fh.convert_alpha())
    # Layer 2: Mid hills (offset 0.35, tileable at WINDOW_W). 5 peaks.
    mh = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    mid_col = hsl(hue, 0.45, 0.13)
    pts = [(0, cfg.ROAD_TOP)]
    for x in range(0, cfg.WINDOW_W + 1, 30):
        y = cfg.ROAD_TOP - 14 - (math.sin(x * 2 * math.pi * 5 / cfg.WINDOW_W + 1.2) * 12 + 12)
        pts.append((x, y))
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(mh, mid_col, pts)
    layers.append(mh.convert_alpha())
    # Layer 3: Near foliage (offset 0.6, tileable at WINDOW_W). Bushes
    # at 80px intervals + roadside torches at 160px intervals along the
    # road edge. 80 and 160 both divide WINDOW_W (1280/80=16, 1280/160=8)
    # so the foliage tiles seamlessly at WINDOW_W.
    nf = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    foliage_col = hsl(hue, 0.5, 0.10)
    for x in range(0, cfg.WINDOW_W, 80):
        pygame.draw.circle(nf, foliage_col, (x + 20, cfg.ROAD_TOP - 4), 8)
        pygame.draw.circle(nf, foliage_col, (x + 40, cfg.ROAD_TOP - 2), 6)
    for x in range(80, cfg.WINDOW_W, 160):
        pygame.draw.rect(nf, (40, 30, 30), (x, cfg.ROAD_TOP - 8, 3, 10))
        pygame.draw.circle(nf, (255, 140, 60), (x + 1, cfg.ROAD_TOP - 12), 5)
    layers.append(nf.convert_alpha())
    # Layer 4: Road (offset 1.0, tileable at WINDOW_W). The road rect +
    # lane lines. Lane lines at 64px intervals (64 divides WINDOW_W =
    # 1280) so the lines tile seamlessly.
    rd = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    pygame.draw.rect(rd, C.road, (0, cfg.ROAD_TOP, cfg.WINDOW_W, cfg.ROAD_H))
    pygame.draw.rect(rd, C.road_edge, (0, cfg.ROAD_TOP, cfg.WINDOW_W, 4))
    pygame.draw.rect(rd, C.road_edge, (0, cfg.ROAD_BOTTOM - 4, cfg.WINDOW_W, 4))
    for x in range(0, cfg.WINDOW_W, 64):
        pygame.draw.rect(rd, C.lane_line,
                         (x + 32, cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2, 30, 4))
    layers.append(rd.convert_alpha())
    _PARALLAX_CACHE[key] = layers
    return layers


# === Particles ===
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity")
    def __init__(self, x, y, vx, vy, life, color, size=3, gravity=0.0):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.color = color; self.size = size; self.gravity = gravity
    def update(self, dt):
        self.x += self.vx * dt; self.y += self.vy * dt
        self.vy += self.gravity * dt; self.life -= dt
    @property
    def alive(self): return self.life > 0


class ParticleSystem:
    def __init__(self):
        self.particles: list[Particle] = []
    def burst(self, x, y, color, count=12, speed=120, life=0.4, size=3):
        for _ in range(count):
            ang = rng().uniform(0, math.tau)
            sp = rng().uniform(speed * 0.4, speed)
            self.particles.append(Particle(x, y, math.cos(ang) * sp, math.sin(ang) * sp,
                                            life * rng().uniform(0.6, 1.2), color, size, 200))
    def trail(self, x, y, color, count=1, size=2):
        for _ in range(count):
            self.particles.append(Particle(x + rng().uniform(-2, 2), y + rng().uniform(-2, 2),
                                           rng().uniform(-10, 10), rng().uniform(-10, 10), 0.3, color, size))
    def update(self, dt):
        for p in self.particles: p.update(dt)
        self.particles = [p for p in self.particles if p.alive]
    def draw(self, surf):
        for p in self.particles:
            a = max(0, min(255, int(255 * (p.life / p.max_life))))
            r = max(1, int(p.size))
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*p.color, a), (r, r), r)
            surf.blit(s, (p.x - r, p.y - r))


# === Procedural SFX ===
_SFX: dict[str, object] = {}
_SFX_OK = False


def _make_tone(freq, dur, vol=0.3, decay=8.0, harmonics=1):
    import numpy as np
    try:
        sr = 22050; n = int(sr * dur); t = np.arange(n) / sr
        wave = np.zeros(n, dtype=np.float32)
        for h in range(1, harmonics + 1):
            wave += (1.0 / h) * np.sin(2 * np.pi * freq * h * t)
        wave *= vol * np.exp(-t * decay)
        stereo = np.column_stack([wave, wave])
        return pygame.sndarray.make_sound((stereo * 32767).astype(np.int16))
    except Exception:
        return None


def _make_sweep(f0, f1, dur, vol=0.3):
    import numpy as np
    try:
        sr = 22050; n = int(sr * dur); t = np.arange(n) / sr
        freq = f0 + (f1 - f0) * (t / dur)
        phase = 2 * np.pi * np.cumsum(freq) / sr
        wave = vol * np.sin(phase) * np.exp(-t * 4)
        stereo = np.column_stack([wave, wave])
        return pygame.sndarray.make_sound((stereo * 32767).astype(np.int16))
    except Exception:
        return None


def init_sfx():
    global _SFX_OK
    if _SFX_OK:
        return
    try:
        if not pygame.mixer.get_init():
            return
        _SFX["tap"] = _make_tone(330, 0.05, 0.15, 20)
        _SFX["crit"] = _make_tone(660, 0.10, 0.22, 10, 2)
        _SFX["kill"] = _make_tone(220, 0.08, 0.18, 12)
        _SFX["boss"] = _make_tone(110, 0.5, 0.35, 4, 3)
        _SFX["firefly"] = _make_sweep(600, 1200, 0.3, 0.25)
        _SFX["skill"] = _make_sweep(300, 900, 0.4, 0.25)
        _SFX["ascend"] = _make_sweep(200, 1200, 1.0, 0.35)
        _SFX["gacha"] = _make_sweep(400, 800, 0.3, 0.25)
        # Task 25 (gp-skill-synergy-rhythm): a soft, short, high-pitched
        # tick for the rhythm streak increment -- a non-visual cue for
        # reduced_motion players (the visual rhythm display is suppressed
        # when reduced_motion is on; the tick is the alternative cue).
        _SFX["tick"] = _make_tone(880, 0.03, 0.08, 30)
        # Task 27 (pl-juice-polish): a soft, high-pitched chime for the
        # skill cooldown-ready cue. The chime respects ``sound_on`` (the
        # screen passes ``state.sound_on`` to ``play``); the visual glow
        # + cooldown progress fill are the non-visual cues for
        # ``reduced_motion`` players (the chime is the audio cue).
        _SFX["skill_ready"] = _make_sweep(600, 1200, 0.25, 0.20)
        _SFX_OK = True
    except Exception:
        _SFX_OK = False


def play(name, sound_on=True):
    if not sound_on or not _SFX_OK:
        return
    snd = _SFX.get(name)
    if snd is None:
        return
    try:
        # Guard against the mixer being quit between init_sfx() and play()
        # (e.g. a test fixture quits pygame; _SFX_OK stays True but the
        # mixer is gone, and snd.play() segfaults). The get_init() check
        # is cheap and prevents the segfault.
        if not pygame.mixer.get_init():
            return
        snd.play()
    except Exception:
        pass
