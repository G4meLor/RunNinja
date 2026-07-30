"""Bestiary screen — a research menu of every enemy the player has
encountered, grouped by zone.

Each of the 9 zones renders as a section: a header (zone index, name,
boss-status pill) followed by a row of 3 enemy cards and one boss card
beneath them.  Zones the player has not yet reached (``index >
state.best_zone``) show silhouettes and no names; a zone's boss card
stays locked (silhouette) until that zone's boss has been defeated
(``index < state.bosses_killed``).

Category tabs (Task 26 / cnt-quest-codex): a row of tabs at the top of
the viewport filters the roster. ``All`` shows every zone; ``Bosses``
shows only the zone bosses; the four Godai element tabs (``Wind``,
``Fire``, ``Water``, ``Void``) show only the zones whose enemies share
that element. The tab state is a single ``self.tab`` string; the
filtered view reuses the same section layout (no new widget, no new
state machine -- just a filter on the zone list).

Lore / Bestiary Codex (Task 26): each enemy + boss has a ``lore`` field
on ``EnemyDef`` (pure data, no new mechanic). The lore is a one-line
in-fiction description shown beneath the stat row on the card when the
enemy is revealed; locked enemies show no lore (the lore is a reward for
reaching the zone).

State read:
  state.best_zone      — highest zone index reached; zones with
                         ``i <= best_zone`` are revealed.
  state.bosses_killed  — total bosses slain; zone ``i``'s boss is
                         revealed as defeated when ``i < bosses_killed``.

All sprites come from the cached ``assets.enemy_surface`` (keyed by
``(edef.id, size)``); silhouettes are built once and cached in
``_SIL_CACHE``.  No surfaces, lists, or sprite caches are allocated
per frame — only the small ``font.render`` text images the rest of the
UI already produces every frame.
"""
from __future__ import annotations

import pygame

import config as cfg
from data import enemies as ed
from assets import enemy_surface, hsl
from theme import (C, font_xs, font_sm, font_md, font_lg, font_xl,
                   draw_text, draw_text_center, draw_panel, gradient_v)
from ui.widgets import Button
from utils import clamp


# --- Layout ---------------------------------------------------------------
_VIEW_X = 40
_VIEW_W = cfg.WINDOW_W - 80            # 1200
_VIEW_Y = 110
_VIEW_H = cfg.WINDOW_H - 110 - 70      # 540 (leave room for the back button)

_HEADER_H = 30
_CARD_H = 92
_BOSS_H = 96
_GAP = 12
_SECTION_GAP = 22

_SPRITE = 64
_BOSS_SPRITE = 80

# Category tabs (Task 26 / cnt-quest-codex). ``All`` shows every zone;
# ``Bosses`` shows only the zone bosses; the four element tabs filter by
# the zone's dominant element. The tab row is drawn at the top of the
# viewport; clicking a tab sets ``self.tab`` and resets the scroll.
_TABS: tuple[str, ...] = ("All", "Bosses", "Wind", "Fire", "Water", "Void")
_TAB_H = 32
_TAB_Y = 78
_TAB_PAD = 16


# Element -> tab-name mapping (the zone's enemies share an element; the
# tab filters by that element). ``none`` (the village) is shown under
# ``All`` but not under any element tab.
_ELEMENT_TAB = {"wind": "Wind", "fire": "Fire", "water": "Water", "void": "Void"}


# --- Silhouette cache (built once per (id, size)) -------------------------
_SIL_CACHE: dict[tuple, pygame.Surface] = {}


def _silhouette(edef, size: int) -> pygame.Surface:
    """A dark, shape-preserving silhouette of an enemy sprite.

    Built by multiplying the cached coloured sprite by a near-black fill
    (``BLEND_RGBA_MULT`` keeps the alpha outline while crushing RGB), then
    cached by ``(id, size)`` so subsequent frames reuse the same surface.
    """
    key = (getattr(edef, "id", str(edef)), size)
    cached = _SIL_CACHE.get(key)
    if cached is not None:
        return cached
    src = enemy_surface(edef, size)
    out = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    out.fill((8, 10, 18, 255))
    out.blit(src, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _SIL_CACHE[key] = out
    return out


def _zone_element(zone: dict) -> str:
    """The dominant element of a zone's enemies (the first enemy's
    element; the zone's enemies share an element by design)."""
    for e in zone["enemies"]:
        el = getattr(e, "element", "none")
        if el and el != "none":
            return el
    return "none"


class BestiaryScreen:
    """A scrollable research menu of the enemy roster."""

    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button(
            (16, cfg.WINDOW_H - 60, 120, 44), "Back",
            on_click=lambda: self.game.set_screen("game"),
        )
        self.buttons = [self.btn_back]

        # Smooth-scroll state (same pattern as ui.widgets.ScrollList).
        self.scroll = 0.0
        self.target_scroll = 0.0

        # Drag-scroll state (same pattern as ui.widgets.ScrollList). A
        # press inside the scroll viewport starts a potential drag; if
        # the mouse moves before the release the scroll follows the drag
        # delta (clamped to 0..max_scroll). The release ends the drag.
        self._dragging = False
        self._drag_anchor_y = 0
        self._drag_anchor_scroll = 0.0

        # Category tab (Task 26): the active filter. ``All`` shows every
        # zone; ``Bosses`` shows only the bosses; an element tab shows
        # only the zones whose enemies share that element.
        self.tab: str = "All"

        # Static layout constants — never rebuilt per frame.
        self._card_w = (_VIEW_W - 2 * _GAP) // 3
        per = _HEADER_H + 14 + _CARD_H + 8 + _BOSS_H + _SECTION_GAP
        self._content_h = len(ed.ZONES) * per

    @property
    def max_scroll(self) -> float:
        return max(0.0, float(self._content_h - _VIEW_H))

    # ------------------------------------------------------------------
    # Category tab: the filtered zone list (Task 26 / cnt-quest-codex)
    # ------------------------------------------------------------------
    def _filtered_zones(self) -> list[tuple[int, dict]]:
        """The (index, zone) pairs to render under the current tab.

        ``All`` -> every zone. ``Bosses`` -> every zone (the boss card is
        always shown; the trash-enemies row is hidden in this tab). An
        element tab -> only the zones whose dominant element matches.
        """
        if self.tab == "All" or self.tab == "Bosses":
            return list(enumerate(ed.ZONES))
        # Element tab: filter by the zone's dominant element.
        out = []
        for i, z in enumerate(ed.ZONES):
            if _ELEMENT_TAB.get(_zone_element(z)) == self.tab:
                out.append((i, z))
        return out

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        # Task 37 (pl-music-sfx): pass ``state.sound_on`` to each button so
        # the UI click sound is gated on the SFX toggle. Read once here so
        # the rest of handle does not re-read it per button.
        state = self.game.state
        for b in self.buttons:
            b.sound_on = state.sound_on
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEWHEEL:
            self.target_scroll -= event.y * 60
            self.target_scroll = max(0.0, min(self.target_scroll, self.max_scroll))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Category tab click (Task 26): the tab row is at _TAB_Y. A tab
            # click is not a drag-start (the tab row is outside the scroll
            # viewport), so handle it first and return.
            for i, name in enumerate(_TABS):
                r = self._tab_rect(i)
                if r.collidepoint(event.pos):
                    if self.tab != name:
                        self.tab = name
                        # Reset scroll on tab change (the content height
                        # changes, so the old scroll may be out of range).
                        self.scroll = 0.0
                        self.target_scroll = 0.0
                    return
            # Drag-scroll (same pattern as ui.widgets.ScrollList): a press
            # inside the scroll viewport records a drag anchor; MOUSEMOTION
            # while dragging sets target_scroll from the drag delta (clamped
            # to 0..max_scroll); MOUSEBUTTONUP ends the drag. The viewport
            # is the same rect the scroll content is clipped to in draw().
            view = pygame.Rect(_VIEW_X, _VIEW_Y, _VIEW_W, _VIEW_H)
            if view.collidepoint(event.pos):
                self._dragging = True
                self._drag_anchor_y = event.pos[1]
                self._drag_anchor_scroll = self.target_scroll
        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                dy = event.pos[1] - self._drag_anchor_y
                self.target_scroll = clamp(
                    self._drag_anchor_scroll - dy, 0.0, self.max_scroll)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging:
                self._dragging = False

    def update(self, dt: float) -> None:
        for b in self.buttons:
            b.update(dt)
        self.scroll += (self.target_scroll - self.scroll) * min(1.0, dt * 14)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        state = self.game.state

        surf.fill(C.bg_top)
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Bestiary", (cfg.WINDOW_W // 2, 40),
                         font_xl(bold=True), C.text)
        draw_text_center(surf, "Every foe on the endless road.",
                         (cfg.WINDOW_W // 2, 58), font_sm(), C.text_dim)

        # Category tab row (Task 26 / cnt-quest-codex).
        self._draw_tabs(surf)

        # Clip the scrollable content to the viewport.
        view = pygame.Rect(_VIEW_X, _VIEW_Y, _VIEW_W, _VIEW_H)
        clip = surf.get_clip()
        surf.set_clip(view)

        cur_y = _VIEW_Y - int(self.scroll)
        for i, zone in self._filtered_zones():
            section_top = cur_y
            section_bottom = cur_y + _HEADER_H + 14 + _CARD_H + 8 + _BOSS_H
            # Skip sections entirely above / below the viewport.
            if section_bottom < _VIEW_Y:
                cur_y = section_bottom + _SECTION_GAP
                continue
            if section_top > _VIEW_Y + _VIEW_H:
                break

            revealed = i <= state.best_zone
            boss_defeated = i < state.bosses_killed
            hue = zone["hue"]
            accent = hsl(hue, 0.5, 0.55) if revealed else C.text_muted

            self._draw_header(surf, i, zone, revealed, boss_defeated, accent, cur_y)
            ey = cur_y + _HEADER_H + 14
            if self.tab != "Bosses":
                for c, edef in enumerate(zone["enemies"]):
                    rx = _VIEW_X + c * (self._card_w + _GAP)
                    rect = pygame.Rect(rx, ey, self._card_w, _CARD_H)
                    self._draw_enemy_card(surf, rect, edef, revealed)
            by = ey + _CARD_H + 8
            boss_rect = pygame.Rect(_VIEW_X, by, _VIEW_W, _BOSS_H)
            self._draw_boss_card(surf, boss_rect, ed.BOSSES[zone["id"]],
                                 revealed, boss_defeated)
            cur_y = by + _BOSS_H + _SECTION_GAP

        self._draw_scrollbar(surf)
        surf.set_clip(clip)

        for b in self.buttons:
            b.draw(surf)

    # ------------------------------------------------------------------
    # Category tab row (Task 26 / cnt-quest-codex)
    # ------------------------------------------------------------------
    def _tab_rect(self, i: int) -> pygame.Rect:
        """The hit-rect for the i-th tab. Tabs are evenly spaced across
        the viewport width."""
        n = len(_TABS)
        w = (_VIEW_W - (n - 1) * _TAB_PAD) // n
        x = _VIEW_X + i * (w + _TAB_PAD)
        return pygame.Rect(x, _TAB_Y, w, _TAB_H)

    def _draw_tabs(self, surf: pygame.Surface) -> None:
        for i, name in enumerate(_TABS):
            r = self._tab_rect(i)
            active = (name == self.tab)
            fill = C.panel_hi if active else C.panel
            border = C.panel_border_hi if active else C.panel_border
            pygame.draw.rect(surf, fill, r, border_radius=6)
            pygame.draw.rect(surf, border, r, 1, border_radius=6)
            col = C.text if active else C.text_dim
            draw_text_center(surf, name, r.center, font_sm(bold=active), col)

    # ------------------------------------------------------------------
    # Section pieces
    # ------------------------------------------------------------------
    def _draw_header(self, surf, i: int, zone: dict, revealed: bool,
                     boss_defeated: bool, accent: tuple, y: int) -> None:
        r = pygame.Rect(_VIEW_X, y, _VIEW_W, _HEADER_H)
        # Hue dot.
        pygame.draw.circle(surf, accent, (r.x + 8, r.centery), 6)
        draw_text(surf, f"Zone {i + 1}", (r.x + 22, r.y + 7),
                  font_md(bold=True), accent)
        name = zone["name"] if revealed else "Undiscovered"
        draw_text(surf, name, (r.x + 96, r.y + 7), font_md(bold=True),
                  C.text if revealed else C.text_muted)
        # Boss-status pill on the right.
        if revealed:
            if boss_defeated:
                label, col = "Boss defeated", C.text_good
            else:
                label, col = "Boss locked", C.text_warn
        else:
            label, col = "Locked", C.text_muted
        self._pill(surf, label, col, midright=(r.right, r.centery))
        # Divider.
        pygame.draw.line(surf, C.panel_border,
                         (r.x, r.bottom - 1), (r.right, r.bottom - 1), 1)

    def _draw_enemy_card(self, surf, rect: pygame.Rect, edef,
                         revealed: bool) -> None:
        draw_panel(surf, rect, fill=C.panel, border=C.panel_border)
        if revealed:
            spr = enemy_surface(edef, _SPRITE)
            surf.blit(spr, spr.get_rect(midleft=(rect.x + 12, rect.centery)))
            tx = rect.x + _SPRITE + 24
            draw_text(surf, edef.name, (tx, rect.y + 10),
                      font_md(bold=True), C.text)
            sy = rect.y + 36
            draw_text(surf, f"HP x{edef.hp_mult:.1f}", (tx, sy), font_xs(), C.hp)
            draw_text(surf, f"DMG x{edef.dmg_mult:.1f}",
                      (tx + 96, sy), font_xs(), C.text_bad)
            draw_text(surf, f"Gold x{edef.gold_mult:.1f}",
                      (tx + 192, sy), font_xs(), C.gold)
            foot = f"spd {edef.speed}   sz {edef.size}"
            if edef.rare_drop > 0:
                foot += f"   rare {edef.rare_drop:.0%}"
            draw_text(surf, foot, (tx, sy + 16), font_xs(), C.text_muted)
            # Lore / Bestiary Codex (Task 26): a one-line in-fiction
            # description shown beneath the stat row when the enemy is
            # revealed. Pure data -- no new mechanic. Locked enemies show
            # no lore (the lore is a reward for reaching the zone).
            lore = getattr(edef, "lore", "") or ""
            if lore:
                draw_text(surf, lore, (tx, rect.bottom - 14),
                          font_xs(), C.text_dim)
        else:
            spr = _silhouette(edef, _SPRITE)
            surf.blit(spr, spr.get_rect(midleft=(rect.x + 12, rect.centery)))
            draw_text(surf, "???", (rect.x + _SPRITE + 24, rect.y + 10),
                      font_md(bold=True), C.text_muted)
            draw_text(surf, "Locked zone", (rect.x + _SPRITE + 24, rect.y + 38),
                      font_xs(), C.text_muted)

    def _draw_boss_card(self, surf, rect: pygame.Rect, bdef,
                        revealed: bool, defeated: bool) -> None:
        border = C.gold if defeated else (C.text_bad if revealed else C.panel_border)
        draw_panel(surf, rect, fill=C.panel, border=border, border_w=2)
        if revealed and defeated:
            spr = enemy_surface(bdef, _BOSS_SPRITE)
            surf.blit(spr, spr.get_rect(midleft=(rect.x + 14, rect.centery)))
            tx = rect.x + _BOSS_SPRITE + 28
            draw_text(surf, bdef.name, (tx, rect.y + 10),
                      font_lg(bold=True), C.gold)
            sy = rect.y + 44
            draw_text(surf, f"HP x{bdef.hp_mult:.1f}", (tx, sy), font_sm(), C.hp)
            draw_text(surf, f"DMG x{bdef.dmg_mult:.1f}",
                      (tx + 120, sy), font_sm(), C.text_bad)
            draw_text(surf, f"Gold x{bdef.gold_mult:.1f}",
                      (tx + 240, sy), font_sm(), C.gold)
            if bdef.desc:
                draw_text(surf, bdef.desc, (tx, sy + 22), font_xs(), C.text_dim)
            # Lore / Bestiary Codex (Task 26): the boss's lore entry,
            # shown beneath the desc when the boss is defeated. Pure data.
            lore = getattr(bdef, "lore", "") or ""
            if lore:
                draw_text(surf, lore, (tx, sy + 40), font_xs(), C.text_muted)
            self._pill(surf, "DEFEATED", C.text_good,
                       midright=(rect.right - 14, rect.y + 16))
        else:
            spr = _silhouette(bdef, _BOSS_SPRITE)
            surf.blit(spr, spr.get_rect(midleft=(rect.x + 14, rect.centery)))
            tx = rect.x + _BOSS_SPRITE + 28
            draw_text(surf, "???", (tx, rect.y + 10),
                      font_lg(bold=True), C.text_muted)
            if revealed:
                sub = "Defeat this zone's boss to reveal."
                col = C.text_warn
            else:
                sub = "Locked zone"
                col = C.text_muted
            draw_text(surf, sub, (tx, rect.y + 44), font_sm(), col)
            self._pill(surf, "LOCKED", col,
                       midright=(rect.right - 14, rect.y + 16))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pill(self, surf, text: str, color: tuple, *, midright: tuple) -> None:
        img = font_xs(bold=True).render(text, True, color)
        r = img.get_rect(midright=midright)
        bg = r.inflate(14, 6)
        pygame.draw.rect(surf, C.panel_lo, bg, border_radius=8)
        pygame.draw.rect(surf, color, bg, 1, border_radius=8)
        surf.blit(img, r)

    def _draw_scrollbar(self, surf) -> None:
        if self.max_scroll <= 0:
            return
        track = pygame.Rect(_VIEW_X + _VIEW_W - 6, _VIEW_Y, 4, _VIEW_H)
        pygame.draw.rect(surf, C.panel_lo, track, border_radius=2)
        thumb_h = max(30, int(_VIEW_H * _VIEW_H / self._content_h))
        ratio = self.scroll / self.max_scroll
        thumb_y = _VIEW_Y + int((_VIEW_H - thumb_h) * ratio)
        thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
        pygame.draw.rect(surf, C.panel_border, thumb, border_radius=2)
