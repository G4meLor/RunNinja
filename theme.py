"""Visual theme: palette, fonts, and small drawing helpers.

The game is rendered entirely with pygame primitives — no external image
assets — so the *look* is defined here.  We keep a tight, harmonious
palette and expose a few cached font objects.

Task 38 (pl-accessibility) adds three accessibility layers on top of the
existing palette + font system:
  * **High-contrast mode**: a parallel ``HIGH_CONTRAST`` palette with
    WCAG AAA contrast ratios (text on background >= 7:1).
    ``apply_high_contrast(state)`` swaps the ``C`` class attributes to
    the high-contrast values when ``state.high_contrast`` is True, and
    restores the default palette when False. All code reading ``C.text``,
    ``C.panel``, etc. gets the high-contrast values without code changes.
  * **Text scale**: a multiplier (0.8x-1.6x) that scales the
    ``font_xs/sm/md/lg/xl/huge`` base sizes. The scale is a module-level
    ``_text_scale`` set by ``set_text_scale`` / ``apply_text_scale``;
    the font cache key includes the scaled size so different scales get
    different cached fonts.
  * **Dyslexia-friendly font**: a toggle that switches the font family
    to a monospace fallback + adds wider letter spacing. The letter-
    spacing render is cached (keyed by size, bold, dyslexia) and only
    applied when the toggle is on (no spacing when off). The
    ``render_text(font, text, color)`` helper wraps ``font.render`` +
    applies the spacing; ``draw_text`` / ``draw_text_center`` use it.
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

    # Boss "red threat" glow (Task 38: moved here from boss_fx.py so the
    # high-contrast palette can swap them). Used by engine/boss_fx.py for
    # the boss health bar fill + the name glow halo.
    boss_glow = (255, 60, 70)
    boss_glow_dim = (120, 20, 30)
    boss_text = (255, 220, 220)
    # Boss health-bar backing panel + bg fill (the dark red-tinted rect
    # behind the bar). Centralised here so the high-contrast palette can
    # swap them too.
    boss_bar_panel = (20, 8, 12)
    boss_bar_bg = (40, 12, 18)


# ---------------------------------------------------------------------------
# High-contrast palette (WCAG AAA: text on background >= 7:1)
# ---------------------------------------------------------------------------
# A parallel palette that ``apply_high_contrast`` swaps the ``C`` class
# attributes to when ``state.high_contrast`` is True. The values are
# chosen for maximum legibility: pure white text on near-black background,
# bright panel borders, and rarity/branch colors pushed to high-contrast-
# distinguishable hues (the color-blind-safe symbols in cb_symbols.py
# provide the redundant cue, but the colors themselves are also more
# distinct here).
HIGH_CONTRAST = {
    "bg_top": (0, 0, 0),
    "bg_bottom": (0, 0, 0),
    "road": (20, 20, 20),
    "road_edge": (60, 60, 60),
    "lane_line": (180, 180, 180),
    "sky_star": (255, 255, 255),
    "panel": (0, 0, 0),
    "panel_hi": (30, 30, 30),
    "panel_lo": (0, 0, 0),
    "panel_border": (220, 220, 220),
    "panel_border_hi": (255, 255, 255),
    "text": (255, 255, 255),
    "text_dim": (230, 230, 230),
    "text_muted": (200, 200, 200),
    "text_warn": (255, 230, 0),
    "text_bad": (255, 120, 120),
    "text_good": (120, 255, 120),
    "gold": (255, 230, 0),
    "coin": (255, 240, 80),
    "soul": (220, 180, 255),
    "exp": (150, 220, 255),
    "rarity": {
        "common": (200, 200, 200),
        "rare": (80, 180, 255),
        "epic": (220, 120, 255),
        "legendary": (255, 180, 40),
        "mythic": (255, 80, 180),
    },
    "hp": (90, 255, 120),
    "hp_bg": (0, 40, 0),
    "mp": (120, 200, 255),
    "mp_bg": (0, 30, 60),
    "shield": (255, 230, 120),
    "btn": (40, 40, 40),
    "btn_hover": (80, 80, 80),
    "btn_press": (20, 20, 20),
    "btn_text": (255, 255, 255),
    "btn_disabled": (90, 90, 90),
    "btn_disabled_text": (160, 160, 160),
    "branch": {
        "offense": (255, 120, 110),
        "defense": (110, 180, 255),
        "fortune": (255, 230, 0),
        "speed": (130, 230, 160),
    },
    "boss_glow": (255, 90, 100),
    "boss_glow_dim": (200, 40, 50),
    "boss_text": (255, 240, 240),
    "boss_bar_panel": (40, 0, 0),
    "boss_bar_bg": (80, 0, 0),
}

# Snapshot of the default palette (taken once at import) so
# ``apply_high_contrast`` can restore it without re-defining the values.
_DEFAULT_PALETTE: dict[str, object] = {}
_PALETTE_KEYS: tuple[str, ...] = (
    "bg_top", "bg_bottom", "road", "road_edge", "lane_line", "sky_star",
    "panel", "panel_hi", "panel_lo", "panel_border", "panel_border_hi",
    "text", "text_dim", "text_muted", "text_warn", "text_bad", "text_good",
    "gold", "coin", "soul", "exp", "rarity", "hp", "hp_bg", "mp", "mp_bg",
    "shield", "btn", "btn_hover", "btn_press", "btn_text",
    "btn_disabled", "btn_disabled_text", "branch",
    "boss_glow", "boss_glow_dim", "boss_text",
    "boss_bar_panel", "boss_bar_bg",
)


def _snapshot_palette() -> dict[str, object]:
    """Capture the current ``C`` palette (a deep copy of the dict fields)."""
    snap = {}
    for k in _PALETTE_KEYS:
        v = getattr(C, k)
        # Copy dicts (rarity, branch) so swapping doesn't mutate the
        # default's dicts.
        if isinstance(v, dict):
            snap[k] = dict(v)
        else:
            snap[k] = v
    return snap


def _restore_palette(snap: dict[str, object]) -> None:
    """Restore ``C`` attributes from a snapshot."""
    for k, v in snap.items():
        setattr(C, k, v)


def _apply_palette(palette: dict[str, object]) -> None:
    """Swap the ``C`` class attributes to the given palette."""
    for k, v in palette.items():
        setattr(C, k, v)


def apply_high_contrast(state) -> None:
    """Apply the high-contrast palette when ``state.high_contrast`` is True.

    Swaps the ``C`` class attributes in place so all code reading ``C.text``,
    ``C.panel``, etc. gets the high-contrast values without code changes.
    Restores the default palette when the toggle is off. Idempotent: the
    default palette is snapshotted once (lazily) and restored verbatim.

    Call this when the toggle changes (from the settings screen) and at
    startup (apply the saved state). The function is safe to call
    repeatedly — it snapshots the default palette on the first call and
    restores from the snapshot thereafter.
    """
    global _DEFAULT_PALETTE
    if not _DEFAULT_PALETTE:
        _DEFAULT_PALETTE = _snapshot_palette()
    if getattr(state, "high_contrast", False):
        _apply_palette(HIGH_CONTRAST)
    else:
        _restore_palette(_DEFAULT_PALETTE)


# ---------------------------------------------------------------------------
# Fonts  (cached lazily so we don't create surfaces before pygame.init)
# ---------------------------------------------------------------------------
# Task 38 (pl-accessibility): the font cache + the font_* helpers scale by
# the module-level ``_text_scale`` (set by ``set_text_scale`` /
# ``apply_text_scale``), and the font family switches to a monospace
# fallback when ``_dyslexia_font`` is True. The cache key includes the
# scaled size + the dyslexia flag so different scales + dyslexia on/off
# get different cached fonts.
_FONTS: dict[str, pygame.font.Font] = {}

# Module-level accessibility settings (set by the settings screen + at
# startup; read by the font_* helpers + render_text). Clamped to 0.8-1.6.
_text_scale: float = 1.0
_dyslexia_font: bool = False

# Per-letter-spacing render cache: (size, bold, dyslexia) -> the cached
# spaced-glyph metadata so the render is not re-built per frame. The cache
# is keyed by (size, bold, dyslexia) so the on/off states get different
# entries (the brief's specimen: "keyed by size, bold, dyslexia").
_RENDER_CACHE: dict[tuple[int, bool, bool], object] = {}

# The monospace fallback family for dyslexia mode (wider letter spacing
# is applied on top of the monospace rendering).
_DYSLEXIA_FONT_FAMILY = "dejavusansmono,monospace,couriernew,courier"
_DEFAULT_FONT_FAMILY = "dejavusans,arial,sans"


def _clamp_scale(s: float) -> float:
    """Clamp the text scale to the 0.8-1.6 range."""
    return 0.8 if s < 0.8 else 1.6 if s > 1.6 else float(s)


def set_text_scale(scale: float) -> None:
    """Set the module-level text scale (clamped to 0.8-1.6).

    The font_* helpers read this and scale their base size by it. Clears
    the font cache so the new scale gets fresh cached fonts.
    """
    global _text_scale
    _text_scale = _clamp_scale(scale)
    _FONTS.clear()
    _RENDER_CACHE.clear()


def get_text_scale() -> float:
    """The current module-level text scale (1.0 = no scaling)."""
    return _text_scale


def apply_text_scale(state) -> None:
    """Read ``state.text_scale`` and set the module-level scale (clamped).

    Convenience for the settings screen + startup: pass the state, the
    scale is read + clamped + applied. Clears the font cache.
    """
    set_text_scale(getattr(state, "text_scale", 1.0))


def set_dyslexia_font(on: bool) -> None:
    """Set the module-level dyslexia-font toggle.

    When True, the font_* helpers use a monospace fallback family and
    ``render_text`` adds wider letter spacing. Clears the font + render
    caches so the new setting gets fresh cached fonts.
    """
    global _dyslexia_font
    _dyslexia_font = bool(on)
    _FONTS.clear()
    _RENDER_CACHE.clear()


def get_dyslexia_font() -> bool:
    """The current module-level dyslexia-font toggle."""
    return _dyslexia_font


def apply_dyslexia_font(state) -> None:
    """Read ``state.dyslexia_font`` and set the module-level toggle."""
    set_dyslexia_font(getattr(state, "dyslexia_font", False))


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    # Scale the base size by the module-level text scale (clamped). The
    # scaled size is what the cache key uses, so different scales get
    # different cached fonts.
    scaled = max(6, int(round(size * _text_scale)))
    key = f"{scaled}:{int(bold)}:{int(_dyslexia_font)}"
    f = _FONTS.get(key)
    if f is None:
        family = _DYSLEXIA_FONT_FAMILY if _dyslexia_font else _DEFAULT_FONT_FAMILY
        f = pygame.font.SysFont(family, scaled, bold=bold)
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
    _RENDER_CACHE.clear()


# ---------------------------------------------------------------------------
# Dyslexia letter-spacing render
# ---------------------------------------------------------------------------
# The per-character spacing (in pixels) added between glyphs when the
# dyslexia toggle is on. Wide enough to clearly separate letters without
# blowing up the layout.
_DYSLEXIA_LETTER_SPACING = 2


def render_text(font: pygame.font.Font, text: str,
                color: tuple[int, int, int]) -> pygame.Surface:
    """Render ``text`` with ``font``, applying dyslexia letter spacing.

    When the dyslexia toggle is OFF, this is a plain ``font.render`` (no
    spacing) — the same as calling ``font.render`` directly, so existing
    call sites that use ``font.render`` are unaffected.

    When the dyslexia toggle is ON, each character is rendered separately
    and blitted with a ``_DYSLEXIA_LETTER_SPACING``-px gap between them.
    The result is a wider surface (the same height). The per-(size, bold,
    dyslexia) glyph widths are cached so the render is not re-built per
    frame; the cache is keyed by (size, bold, dyslexia) so the on/off
    states get different cached entries.
    """
    if not _dyslexia_font or len(text) <= 1:
        return font.render(text, True, color)
    # Render each character + blit with a gap. The cache key is
    # (size, bold, dyslexia) — the brief's specimen. We cache the per-
    # character widths so the layout is not re-computed per frame, but
    # the surfaces are rendered fresh per call (the color varies).
    key = (font.get_height(), bool(font.get_bold()), True)
    cached = _RENDER_CACHE.get(key)
    if cached is None:
        # Measure each printable ASCII char once for this (size, bold,
        # dyslexia) combo so the layout is stable.
        widths = {}
        for ch in set(text):
            try:
                widths[ch] = font.render(ch, True, color).get_width()
            except Exception:
                widths[ch] = 0
        cached = widths
        _RENDER_CACHE[key] = cached
    widths = cached
    gap = _DYSLEXIA_LETTER_SPACING
    total_w = sum(widths.get(ch, 0) for ch in text) + gap * (len(text) - 1)
    # Render the first char to get the height (the rest are the same font).
    first = font.render(text[0], True, color)
    h = first.get_height()
    surf = pygame.Surface((max(1, total_w), h), pygame.SRCALPHA)
    x = 0
    for ch in text:
        img = font.render(ch, True, color)
        surf.blit(img, (x, 0))
        x += widths.get(ch, img.get_width()) + gap
    return surf


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
    img = render_text(font, text, color)
    surf.blit(img, pos)
    return img.get_rect(topleft=pos)


def draw_text_center(surf: pygame.Surface, text: str, center, font: pygame.font.Font,
                     color: tuple[int, int, int] = C.text) -> pygame.Rect:
    img = render_text(font, text, color)
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
