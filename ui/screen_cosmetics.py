"""Cosmetics shop screen — spend Amber on skins, themes & conveniences.

Cosmetics are non-power items bought with Amber.  They come in four
categories:

  * **skin**       — ninja skins (mutually exclusive: one at a time)
  * **particle**   — combat particle themes (mutually exclusive)
  * **theme**      — UI color themes (mutually exclusive)
  * **convenience**— gameplay conveniences (each toggled independently):
                     auto-firefly catch, doubled offline cap, etc.

State (see docs/specs/cosmetics.md for the full integration sketch):

  * ``state.cosmetics: set[str]``           — owned cosmetic ids
  * ``state.equipped_cosmetics: dict[str,bool]`` — equipped cosmetic ids

The screen reads/writes those attributes through ``getattr``/``setattr``
so it stays compatible with saves that pre-date the cosmetics patch —
missing fields are lazily created on first access.  Cosmetic defs live
inline here for now; the spec doc sketches a ``data/cosmetics.py``
``CosmeticDef`` dataclass they can be lifted into later.
"""
from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_xl
from theme import draw_text, draw_text_center, draw_panel, gradient_v
from ui.widgets import Button, currency_pill
from utils import format_number


# ---------------------------------------------------------------------------
# Cosmetic definitions
# ---------------------------------------------------------------------------
@dataclass
class CosmeticDef:
    id: str
    name: str
    category: str        # skin | particle | theme | convenience
    cost: int            # amber
    hue: int             # icon accent hue
    desc: str


# (id, name, category, cost, hue, desc)
_ROWS = [
    # --- Ninja skins (mutually exclusive) ---
    ("skin_shadow",  "Shadow Ninja",  "skin",   0,   240, "Classic dark silhouette."),
    ("skin_crimson", "Crimson Blade", "skin",   15,  0,   "A blood-red headband."),
    ("skin_jade",    "Jade Wind",     "skin",   40,  120, "Green as bamboo."),
    ("skin_gold",    "Golden Spirit", "skin",   120, 50,  "Gilded for the worthy."),
    ("skin_void",    "Void Walker",    "skin",   300, 280, "Touched by the abyss."),

    # --- Particle themes (mutually exclusive) ---
    ("part_sparks",  "Sparks",        "particle", 0,   60,  "Default combat sparks."),
    ("part_sakura",  "Sakura Petals", "particle", 25,  330, "Pink petals on the wind."),
    ("part_ember",   "Embers",        "particle", 60,  20,  "Glowing cinders."),
    ("part_frost",   "Frost",         "particle", 100, 190, "Cold blue shards."),
    ("part_soul",    "Soul Flame",    "particle", 200, 280, "Violet soul-fire."),

    # --- UI color themes (mutually exclusive) ---
    ("ui_midnight",  "Midnight",     "theme",   0,   240, "Default night palette."),
    ("ui_dawn",      "Dawn",         "theme",   50,  20,  "A warmer dawn sky."),
    ("ui_forest",    "Forest",       "theme",   90,  120, "Verdant greens."),
    ("ui_bloodmoon", "Blood Moon",   "theme",   180, 0,   "Crimson night."),

    # --- Convenience items (each toggled independently) ---
    ("conv_auto_firefly", "Auto Firefly Catch", "convenience", 80,  255,
     "Auto-catch fireflies."),
    ("conv_double_offline", "Double Offline Cap", "convenience", 150, 200,
     "Offline cap 8h -> 16h."),
    ("conv_energy_reserve", "Energy Reserve", "convenience", 120, 130,
     "+25% auto-katana regen."),
    ("conv_quick_tap", "Wide Tap", "convenience", 60, 90,
     "+50% tap catch radius."),
]

COSMETICS: list[CosmeticDef] = [CosmeticDef(*r) for r in _ROWS]
BY_ID: dict[str, CosmeticDef] = {c.id: c for c in COSMETICS}
BY_CAT: dict[str, list[CosmeticDef]] = {}
for _c in COSMETICS:
    BY_CAT.setdefault(_c.category, []).append(_c)

CAT_LABELS = {
    "skin": "Ninja Skins",
    "particle": "Particle Themes",
    "theme": "UI Themes",
    "convenience": "Convenience",
}
CAT_ORDER = ("skin", "particle", "theme", "convenience")
# One equipped per category for these; "convenience" items toggle freely.
MUTEX_CATEGORIES = {"skin", "particle", "theme"}


def _hsl(h: int, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------
class CosmeticsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_back]
        self.card_rects: dict[str, pygame.Rect] = {}
        self.hover_id: str | None = None
        self.flash_msg: str = ""
        self.flash_t: float = 0.0

    # -----------------------------------------------------------------
    # State access  (graceful: the cosmetics fields may not exist on
    # older saves — we lazily create them; see docs/specs/cosmetics.md)
    # -----------------------------------------------------------------
    def _ensure(self) -> None:
        state = self.game.state
        if not isinstance(getattr(state, "cosmetics", None), set):
            state.cosmetics = set()
        if not isinstance(getattr(state, "equipped_cosmetics", None), dict):
            state.equipped_cosmetics = {}
        # Equip the cost-0 default for each mutex category if nothing is
        # equipped there yet, so the game keeps its default look on first
        # visit.
        eq = state.equipped_cosmetics
        for cat in MUTEX_CATEGORIES:
            if not any(eq.get(c.id) for c in BY_CAT[cat]):
                for c in BY_CAT[cat]:
                    if c.cost == 0:
                        eq[c.id] = True
                        break

    def _owned(self, c: CosmeticDef) -> bool:
        return c.cost == 0 or c.id in self.game.state.cosmetics

    def _equipped(self, c: CosmeticDef) -> bool:
        return bool(self.game.state.equipped_cosmetics.get(c.id, False))

    def _equip(self, c: CosmeticDef) -> None:
        state = self.game.state
        if c.category in MUTEX_CATEGORIES:
            for other in BY_CAT[c.category]:
                if other.id != c.id and state.equipped_cosmetics.get(other.id):
                    state.equipped_cosmetics.pop(other.id, None)
        state.equipped_cosmetics[c.id] = True

    def _unequip(self, c: CosmeticDef) -> None:
        self.game.state.equipped_cosmetics.pop(c.id, None)

    def _buy(self, c: CosmeticDef) -> bool:
        state = self.game.state
        if state.amber < c.cost:
            return False
        state.amber -= c.cost
        state.cosmetics.add(c.id)
        return True

    def _flash(self, msg: str) -> None:
        self.flash_msg = msg
        self.flash_t = 1.4

    # -----------------------------------------------------------------
    # Event handling
    # -----------------------------------------------------------------
    def handle(self, event):
        self._ensure()
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEMOTION:
            self.hover_id = None
            for cid, r in self.card_rects.items():
                if r.collidepoint(event.pos):
                    self.hover_id = cid
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for cid, r in self.card_rects.items():
                if r.collidepoint(event.pos):
                    self._click_card(BY_ID[cid])
                    break

    def _click_card(self, c: CosmeticDef) -> None:
        state = self.game.state
        if self._owned(c):
            if self._equipped(c):
                # Don't allow unequipping the last skin/particle/theme —
                # there must always be one active look.
                if c.category in MUTEX_CATEGORIES:
                    self._flash("Pick another skin to swap.")
                    return
                self._unequip(c)
            else:
                self._equip(c)
            self.game.state.save()
        else:
            if self._buy(c):
                self._equip(c)
                self.game.state.save()
                from assets import play
                play("gacha", state.sound_on)
            else:
                self._flash("Not enough Amber!")

    # -----------------------------------------------------------------
    # Update
    # -----------------------------------------------------------------
    def update(self, dt):
        self._ensure()
        for b in self.buttons:
            b.update(dt)
        if self.flash_t > 0:
            self.flash_t -= dt

    # -----------------------------------------------------------------
    # Draw
    # -----------------------------------------------------------------
    def draw(self, surf):
        state = self.game.state
        self._ensure()
        surf.fill(C.bg_top)
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Cosmetics", (cfg.WINDOW_W // 2, 36),
                         font_xl(bold=True), C.text)
        draw_text_center(surf, "Spend Amber on skins, themes & conveniences.",
                         (cfg.WINDOW_W // 2, 70), font_sm(), C.text_dim)
        # Currency row.
        x = 16; y = 96
        x += currency_pill(surf, x, y, "Amber",
                           format_number(state.amber), (255, 180, 60)) + 10
        owned = len(state.cosmetics)
        currency_pill(surf, x, y, "Owned",
                      f"{owned}/{len(COSMETICS)}", C.text)

        # Grid by category.
        self.card_rects = {}
        card_w, card_h = 200, 96
        gap_x = 12
        y = 128
        for cat in CAT_ORDER:
            items = BY_CAT[cat]
            # Section header.
            draw_text(surf, CAT_LABELS[cat], (60, y), font_md(bold=True), C.text_dim)
            y += 24
            cols = len(items)
            total_w = cols * card_w + (cols - 1) * gap_x
            x0 = (cfg.WINDOW_W - total_w) // 2
            for i, c in enumerate(items):
                r = pygame.Rect(x0 + i * (card_w + gap_x), y, card_w, card_h)
                self.card_rects[c.id] = r
                self._draw_card(surf, c, r)
            y += card_h + 10

        # Flash message (e.g. insufficient amber).
        if self.flash_t > 0:
            alpha = min(1.0, self.flash_t / 0.5)
            col = (int(C.text_bad[0] * alpha + C.bg_top[0] * (1 - alpha)),
                   int(C.text_bad[1] * alpha + C.bg_top[1] * (1 - alpha)),
                   int(C.text_bad[2] * alpha + C.bg_top[2] * (1 - alpha)))
            draw_text_center(surf, self.flash_msg,
                             (cfg.WINDOW_W // 2, cfg.WINDOW_H - 90),
                             font_sm(bold=True), col)

        for b in self.buttons:
            b.draw(surf)

    # -----------------------------------------------------------------
    # Card rendering
    # -----------------------------------------------------------------
    def _draw_card(self, surf, c: CosmeticDef, r: pygame.Rect) -> None:
        state = self.game.state
        owned = self._owned(c)
        equipped = self._equipped(c)
        hover = self.hover_id == c.id
        if equipped:
            border, border_w = C.gold, 2
        elif hover and (owned or state.amber >= c.cost):
            border, border_w = C.panel_border_hi, 1
        else:
            border, border_w = C.panel_border, 1
        fill = C.panel if owned else (20, 22, 36)
        draw_panel(surf, r, fill=fill, border=border, border_w=border_w)

        # Icon.
        self._draw_icon(surf, c, r.x + 10, r.y + 10)

        # Name.
        draw_text(surf, c.name, (r.x + 58, r.y + 10), font_sm(bold=True), C.text)

        # Cost / owned.
        if owned:
            draw_text(surf, "Owned", (r.x + 58, r.y + 30), font_xs(), C.text_good)
        else:
            col = C.gold if state.amber >= c.cost else C.text_bad
            draw_text(surf, f"{c.cost} Amber", (r.x + 58, r.y + 30), font_xs(), col)

        # Description.
        draw_text(surf, c.desc, (r.x + 10, r.y + 54), font_xs(), C.text_dim)

        # Equipped / hint tag.
        if equipped:
            draw_text(surf, "EQUIPPED", (r.x + 10, r.y + 76),
                      font_xs(bold=True), C.gold)
        elif owned and c.category in MUTEX_CATEGORIES:
            draw_text(surf, "click to swap", (r.x + 10, r.y + 76),
                      font_xs(), C.text_muted)
        elif owned:
            draw_text(surf, "click to toggle", (r.x + 10, r.y + 76),
                      font_xs(), C.text_muted)
        elif state.amber >= c.cost:
            draw_text(surf, "click to buy", (r.x + 10, r.y + 76),
                      font_xs(), C.text_dim)
        else:
            draw_text(surf, "need more amber", (r.x + 10, r.y + 76),
                      font_xs(), C.text_muted)

    def _draw_icon(self, surf, c: CosmeticDef, x: int, y: int) -> None:
        """A small procedural icon per category (pygame primitives)."""
        col = _hsl(c.hue, 0.7, 0.6)
        dark = _hsl(c.hue, 0.5, 0.28)
        if c.category == "skin":
            # Mini ninja silhouette: head + body + headband accent.
            pygame.draw.rect(surf, dark, (x + 10, y + 20, 16, 22), border_radius=3)
            pygame.draw.circle(surf, dark, (x + 18, y + 14), 9)
            pygame.draw.rect(surf, col, (x + 8, y + 12, 20, 4))
            pygame.draw.rect(surf, col, (x + 22, y + 10, 8, 2))
        elif c.category == "particle":
            # Cluster of glowing dots.
            for dx, dy in ((6, 24), (20, 10), (26, 26), (12, 32)):
                glow = pygame.Surface((10, 10), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*col, 70), (5, 5), 5)
                surf.blit(glow, (x + dx - 5, y + dy - 5))
                pygame.draw.circle(surf, col, (x + dx, y + dy), 3)
                pygame.draw.circle(surf, _hsl(c.hue, 0.9, 0.9),
                                  (x + dx, y + dy), 1)
        elif c.category == "theme":
            # Color swatch with two hue bands.
            pygame.draw.rect(surf, _hsl(c.hue, 0.5, 0.18),
                             (x + 4, y + 6, 40, 34), border_radius=4)
            pygame.draw.rect(surf, col, (x + 4, y + 6, 40, 10), border_radius=4)
            pygame.draw.rect(surf, _hsl(c.hue, 0.4, 0.5),
                             (x + 4, y + 30, 40, 10), border_radius=4)
            pygame.draw.rect(surf, C.panel_border,
                             (x + 4, y + 6, 40, 34), 1, border_radius=4)
        else:  # convenience — a small gear.
            cx, cy = x + 20, y + 20
            pygame.draw.circle(surf, _hsl(c.hue, 0.5, 0.35), (cx, cy), 11)
            pygame.draw.circle(surf, col, (cx, cy), 11, 2)
            pygame.draw.circle(surf, (20, 22, 36), (cx, cy), 5)
            for k in range(8):
                a = k * math.pi / 4
                pygame.draw.line(surf, col,
                                 (cx + math.cos(a) * 11, cy + math.sin(a) * 11),
                                 (cx + math.cos(a) * 15, cy + math.sin(a) * 15), 2)
