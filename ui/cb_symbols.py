"""Color-blind-safe symbol overlays for rarities and skill branches.

Rarities and skill-tree branches are currently distinguished by color
alone (``C.rarity`` in ``theme.py``, ``branch_color`` in
``data/skill_tree.py``).  This module adds a **shape per rarity and per
branch** so color-blind players can tell them apart without relying on
hue.  Each public function returns a small ``pygame.Surface`` (alpha
channel, transparent background) sized to ``size`` x ``size``; the
caller blits it next to (or on top of) the colored element.

Shapes are drawn with pygame primitives only (``pygame.draw.circle``,
``.polygon``, ``.rect``, ``.line``) on a per-pixel-alpha surface, and
every surface is cached by ``(kind, key, size)`` — no per-frame
allocations after the first call.

## Rarity symbols

| rarity     | shape     |
|------------|-----------|
| common     | circle    |
| rare       | triangle  |
| epic       | square    |
| legendary  | diamond   |
| mythic     | star      |

## Branch symbols

| branch     | shape     |
|------------|-----------|
| offense    | sword     |
| economy    | coin      |
| elixir     | flask     |
| energy     | bolt      |
| firefly    | light     |
| abilities  | star      |
| godai      | pentagon  |

Integration: see ``docs/specs/cb_symbols.md``.
"""
from __future__ import annotations

import math

import pygame


# ---------------------------------------------------------------------------
# Caches: (kind, key, size) -> pygame.Surface
# ---------------------------------------------------------------------------
_RARITY_CACHE: dict[tuple[str, int], pygame.Surface] = {}
_BRANCH_CACHE: dict[tuple[str, int], pygame.Surface] = {}


# Symbol color: a high-contrast neutral so the shape reads on any
# background and against the rarity/branch tint.  Callers that want the
# symbol tinted to match the color can recolor it — but the default is
# plain white-ish so the *shape* is the signal, not the hue.
_SYM_COLOR = (245, 248, 255)


# ---------------------------------------------------------------------------
# Rarity symbols
# ---------------------------------------------------------------------------
def _draw_circle(surf: pygame.Surface, size: int) -> None:
    cx = cy = size // 2
    r = max(2, size // 2 - 2)
    pygame.draw.circle(surf, _SYM_COLOR, (cx, cy), r)
    pygame.draw.circle(surf, (20, 22, 36), (cx, cy), r, 1)


def _draw_triangle(surf: pygame.Surface, size: int) -> None:
    cx = size // 2
    pad = max(2, size // 6)
    top = (cx, pad)
    bl = (pad, size - pad - 1)
    br = (size - pad - 1, size - pad - 1)
    pygame.draw.polygon(surf, _SYM_COLOR, [top, bl, br])
    pygame.draw.polygon(surf, (20, 22, 36), [top, bl, br], 1)


def _draw_square(surf: pygame.Surface, size: int) -> None:
    pad = max(2, size // 5)
    r = pygame.Rect(pad, pad, size - 2 * pad - 1, size - 2 * pad - 1)
    pygame.draw.rect(surf, _SYM_COLOR, r, border_radius=2)
    pygame.draw.rect(surf, (20, 22, 36), r, 1, border_radius=2)


def _draw_diamond(surf: pygame.Surface, size: int) -> None:
    cx = cy = size // 2
    r = max(3, size // 2 - 2)
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    pygame.draw.polygon(surf, _SYM_COLOR, pts)
    pygame.draw.polygon(surf, (20, 22, 36), pts, 1)


def _draw_star(surf: pygame.Surface, size: int) -> None:
    cx = cy = size // 2
    r_outer = max(3, size // 2 - 2)
    r_inner = max(2, r_outer // 2)
    pts: list[tuple[int, int]] = []
    for i in range(10):
        ang = -math.pi / 2 + i * (math.pi / 5)
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    pygame.draw.polygon(surf, _SYM_COLOR, pts)
    pygame.draw.polygon(surf, (20, 22, 36), pts, 1)


_RARITY_DRAWERS = {
    "common": _draw_circle,
    "rare": _draw_triangle,
    "epic": _draw_square,
    "legendary": _draw_diamond,
    "mythic": _draw_star,
}


def rarity_symbol(rarity: str, size: int = 20) -> pygame.Surface:
    """Return a cached surface with the shape for ``rarity``.

    Unknown rarities fall back to the ``common`` circle so the UI never
    breaks if a new rarity is added before this map is updated.
    """
    key = (rarity, int(size))
    cached = _RARITY_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    drawer = _RARITY_DRAWERS.get(rarity, _draw_circle)
    drawer(surf, size)
    _RARITY_CACHE[key] = surf
    return surf


# ---------------------------------------------------------------------------
# Branch symbols
# ---------------------------------------------------------------------------
def _draw_sword(surf: pygame.Surface, size: int) -> None:
    cx = size // 2
    pad = max(2, size // 6)
    # Blade: vertical line tapering to a point at the top.
    blade_w = max(2, size // 8)
    top = (cx, pad)
    bot = (cx, size - pad - 3)
    pygame.draw.line(surf, _SYM_COLOR, top, bot, blade_w)
    pygame.draw.polygon(surf, _SYM_COLOR,
                        [top, (cx - 1, pad + 2), (cx + 1, pad + 2)])
    # Crossguard.
    gw = max(4, size // 3)
    gy = size - pad - 4
    pygame.draw.line(surf, _SYM_COLOR,
                     (cx - gw // 2, gy), (cx + gw // 2, gy), 2)
    # Pommel.
    pygame.draw.circle(surf, _SYM_COLOR, (cx, size - pad - 1),
                      max(2, size // 8))
    # Outline for contrast.
    pygame.draw.line(surf, (20, 22, 36), top, bot, 1)


def _draw_coin(surf: pygame.Surface, size: int) -> None:
    cx = cy = size // 2
    r = max(3, size // 2 - 2)
    pygame.draw.circle(surf, _SYM_COLOR, (cx, cy), r)
    pygame.draw.circle(surf, (20, 22, 36), (cx, cy), r, 1)
    # Inner mark so it reads as a coin, not just a circle.
    inner = max(2, r // 3)
    pygame.draw.circle(surf, (20, 22, 36), (cx, cy), inner, 1)


def _draw_flask(surf: pygame.Surface, size: int) -> None:
    cx = size // 2
    pad = max(2, size // 6)
    # Neck.
    neck_w = max(2, size // 6)
    neck_top = pad
    neck_bot = pad + max(3, size // 4)
    neck = pygame.Rect(cx - neck_w // 2, neck_top, neck_w, neck_bot - neck_top)
    pygame.draw.rect(surf, _SYM_COLOR, neck)
    # Body: a triangle (erlenmeyer-ish) flaring out under the neck.
    body_top = neck_bot
    body_bot = size - pad - 1
    half_w = max(4, size // 3)
    pts = [(cx - half_w, body_bot),
           (cx + half_w, body_bot),
           (cx + 2, body_top),
           (cx - 2, body_top)]
    pygame.draw.polygon(surf, _SYM_COLOR, pts)
    pygame.draw.polygon(surf, (20, 22, 36), pts, 1)
    # Liquid line.
    pygame.draw.line(surf, (20, 22, 36),
                     (cx - half_w + 2, body_bot - 3),
                     (cx + half_w - 2, body_bot - 3), 1)


def _draw_bolt(surf: pygame.Surface, size: int) -> None:
    cx = size // 2
    pad = max(2, size // 5)
    # Lightning bolt as a zig-zag polygon (top-right -> bottom-left zig).
    pts = [
        (cx + 1, pad),
        (cx - size // 4, size // 2),
        (cx, size // 2),
        (cx - size // 4, size - pad - 1),
        (cx + size // 4, size // 2),
        (cx, size // 2),
        (cx + size // 4, pad),
    ]
    pygame.draw.polygon(surf, _SYM_COLOR, pts)
    pygame.draw.polygon(surf, (20, 22, 36), pts, 1)


def _draw_light(surf: pygame.Surface, size: int) -> None:
    cx = cy = size // 2
    r = max(3, size // 2 - 2)
    # Lantern body: a rounded rectangle / circle with rays.
    pygame.draw.circle(surf, _SYM_COLOR, (cx, cy), r)
    pygame.draw.circle(surf, (20, 22, 36), (cx, cy), r, 1)
    # Four rays (N, E, S, W) so it reads as light, not just a circle.
    ray_len = max(2, size // 6)
    for ang in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        x0 = cx + (r + 1) * math.cos(ang)
        y0 = cy + (r + 1) * math.sin(ang)
        x1 = cx + (r + 1 + ray_len) * math.cos(ang)
        y1 = cy + (r + 1 + ray_len) * math.sin(ang)
        pygame.draw.line(surf, _SYM_COLOR,
                         (int(x0), int(y0)), (int(x1), int(y1)), 2)


def _draw_pentagon(surf: pygame.Surface, size: int) -> None:
    cx = cy = size // 2
    r = max(3, size // 2 - 2)
    pts: list[tuple[float, float]] = []
    for i in range(5):
        ang = -math.pi / 2 + i * (2 * math.pi / 5)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    pygame.draw.polygon(surf, _SYM_COLOR, pts)
    pygame.draw.polygon(surf, (20, 22, 36), pts, 1)


_BRANCH_DRAWERS = {
    "offense": _draw_sword,
    "economy": _draw_coin,
    "elixir": _draw_flask,
    "energy": _draw_bolt,
    "firefly": _draw_light,
    "abilities": _draw_star,      # reuse the rarity star drawer
    "godai": _draw_pentagon,
}


def branch_symbol(branch: str, size: int = 20) -> pygame.Surface:
    """Return a cached surface with the shape for ``branch``.

    Unknown branches fall back to the ``offense`` sword so the UI never
    breaks if a new branch is added before this map is updated.
    """
    key = (branch, int(size))
    cached = _BRANCH_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    drawer = _BRANCH_DRAWERS.get(branch, _draw_sword)
    drawer(surf, size)
    _BRANCH_CACHE[key] = surf
    return surf


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
def clear_caches() -> None:
    """Drop all cached symbol surfaces (call after ``pygame.display.set_mode``)."""
    _RARITY_CACHE.clear()
    _BRANCH_CACHE.clear()
