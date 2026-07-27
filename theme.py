"""Visual theme: palette, fonts, and small drawing helpers.

The game is rendered entirely with pygame primitives — no external image
assets — so the *look* is defined here.  We keep a tight, harmonious
palette and expose a few cached font objects.
"""
from __future__ import annotations

import pygame

# ---------------------------------------------------------------------------
# Palette  (a deep-night, neon-arcade scheme)
# ---------------------------------------------------------------------------
class C:
    # Backgrounds
    bg_top = (12, 14, 28)
    bg_bottom = (24, 18, 44)
    road = (30, 34, 54)
    road_edge = (18, 22, 38)
    lane_line = (60, 70, 100)

    sky_star = (200, 210, 255)

    # Panels
    panel = (22, 26, 46)
    panel_hi = (32, 38, 64)
    panel_lo = (16, 20, 36)
    panel_border = (60, 72, 110)
    panel_border_hi = (110, 130, 200)

    # Text
    text = (235, 238, 250)
    text_dim = (160, 170, 200)
    text_muted = (110, 120, 150)
    text_warn = (255, 180, 90)
    text_bad = (255, 110, 120)
    text_good = (130, 230, 160)

    # Accents
    gold = (255, 205, 90)
    coin = (255, 230, 140)
    soul = (180, 120, 255)
    exp = (120, 200, 255)

    # Rarity colors
    rarity = {
        "common": (170, 178, 200),
        "rare": (110, 190, 255),
        "epic": (190, 130, 255),
        "legendary": (255, 170, 70),
        "mythic": (255, 90, 160),
    }

    # HP / state colors
    hp = (90, 220, 120)
    hp_bg = (40, 60, 48)
    mp = (110, 180, 255)
    mp_bg = (38, 50, 70)
    shield = (255, 220, 120)

    # Buttons
    btn = (44, 52, 84)
    btn_hover = (60, 72, 116)
    btn_press = (28, 34, 56)
    btn_text = (235, 238, 250)
    btn_disabled = (90, 96, 120)
    btn_disabled_text = (130, 136, 160)

    # Evolution branch colors
    branch = {
        "offense": (255, 120, 110),
        "defense": (110, 180, 255),
        "fortune": (255, 205, 90),
        "speed": (130, 230, 160),
    }


# ---------------------------------------------------------------------------
# Fonts  (cached lazily so we don't create surfaces before pygame.init)
# ---------------------------------------------------------------------------
_FONTS: dict[str, pygame.font.Font] = {}


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    key = f"{size}:{int(bold)}"
    f = _FONTS.get(key)
    if f is None:
        f = pygame.font.SysFont("dejavusans,arial,sans", size, bold=bold)
        _FONTS[key] = f
    return f


def font_xs(bold: bool = False) -> pygame.font.Font: return _font(12, bold)
def font_sm(bold: bool = False) -> pygame.font.Font: return _font(14, bold)
def font_md(bold: bool = False) -> pygame.font.Font: return _font(18, bold)
def font_lg(bold: bool = False) -> pygame.font.Font: return _font(24, bold)
def font_xl(bold: bool = False) -> pygame.font.Font: return _font(34, bold)
def font_huge(bold: bool = False) -> pygame.font.Font: return _font(54, bold)


def reset_fonts() -> None:
    _FONTS.clear()


# ---------------------------------------------------------------------------
# Tiny drawing helpers reused across the UI
# ---------------------------------------------------------------------------
def draw_panel(surf: pygame.Surface, rect: pygame.Rect, *,
               fill: tuple[int, int, int] = C.panel,
               border: tuple[int, int, int] = C.panel_border,
               border_w: int = 1, radius: int = 8,
               title: str | None = None) -> None:
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    if border_w:
        pygame.draw.rect(surf, border, rect, border_w, border_radius=radius)
    if title:
        draw_text(surf, title, (rect.x + 10, rect.y + 6), font_md(bold=True), C.text)


def draw_text(surf: pygame.Surface, text: str, pos, font: pygame.font.Font,
              color: tuple[int, int, int] = C.text) -> pygame.Rect:
    img = font.render(text, True, color)
    surf.blit(img, pos)
    return img.get_rect(topleft=pos)


def draw_text_center(surf: pygame.Surface, text: str, center, font: pygame.font.Font,
                     color: tuple[int, int, int] = C.text) -> pygame.Rect:
    img = font.render(text, True, color)
    r = img.get_rect(center=center)
    surf.blit(img, r)
    return r


def draw_bar(surf: pygame.Surface, rect: pygame.Rect, pct: float,
             fill: tuple[int, int, int] = C.hp, bg: tuple[int, int, int] = C.hp_bg,
             border: tuple[int, int, int] | None = None, radius: int = 3) -> None:
    pct = 0.0 if pct < 0 else 1.0 if pct > 1 else pct
    pygame.draw.rect(surf, bg, rect, border_radius=radius)
    if pct > 0:
        inner = rect.copy()
        inner.w = max(2, int(rect.w * pct))
        pygame.draw.rect(surf, fill, inner, border_radius=radius)
    if border is not None:
        pygame.draw.rect(surf, border, rect, 1, border_radius=radius)


_GRADIENT_CACHE: dict[tuple, pygame.Surface] = {}


def gradient_v(surf: pygame.Surface, rect: pygame.Rect,
               top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    """Vertical gradient.  Full-screen gradients are cached by (w,h,top,bottom)."""
    h = rect.h
    if h <= 0:
        return
    # Cache only the common full-screen case; small rects are cheap enough.
    if rect.topleft == (0, 0) and rect.size == surf.get_size():
        key = (rect.w, rect.h, top, bottom)
        cached = _GRADIENT_CACHE.get(key)
        if cached is None:
            cached = pygame.Surface((rect.w, rect.h)).convert()
            for y in range(h):
                t = y / max(1, h - 1)
                col = (int(top[0] + (bottom[0] - top[0]) * t),
                       int(top[1] + (bottom[1] - top[1]) * t),
                       int(top[2] + (bottom[2] - top[2]) * t))
                pygame.draw.line(cached, col, (0, y), (rect.w - 1, y))
            _GRADIENT_CACHE[key] = cached
        surf.blit(cached, (0, 0))
        return
    # Fallback: line-by-line for small/odd rects.
    for y in range(h):
        t = y / max(1, h - 1)
        col = (int(top[0] + (bottom[0] - top[0]) * t),
               int(top[1] + (bottom[1] - top[1]) * t),
               int(top[2] + (bottom[2] - top[2]) * t))
        pygame.draw.line(surf, col, (rect.x, rect.y + y), (rect.right - 1, rect.y + y))


def gradient_h(surf: pygame.Surface, rect: pygame.Rect,
               left: tuple[int, int, int], right: tuple[int, int, int]) -> None:
    w = rect.w
    if w <= 0:
        return
    for x in range(w):
        t = x / max(1, w - 1)
        col = (int(left[0] + (right[0] - left[0]) * t),
               int(left[1] + (right[1] - left[1]) * t),
               int(left[2] + (right[2] - left[2]) * t))
        pygame.draw.line(surf, col, (rect.x + x, rect.y), (rect.x + x, rect.bottom - 1))
