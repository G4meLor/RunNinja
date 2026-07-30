"""Buildings screen: list of 18 buildings with Buy 1/10/Max."""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill, ScrollList
from ui.tooltip import TooltipManager
from utils import format_number
from data import buildings as bd
from core import game_economy


class BuildingsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_back]
        self.list = None
        self._build_list()
        self.buy_buttons: list[Button] = []
        # Task 36 (pl-hints-nav-tooltips): a TooltipManager with
        # callable-text (live values from state) for every building.
        self.tooltips = TooltipManager()

    def _build_list(self) -> None:
        state = self.game.state
        items = []
        for b in bd.BUILDINGS:
            lvl = state.building_level(b.id)
            # Use the state-aware (tier-scaled) gps so the per-building
            # display matches the tier-scaled total_gps pill at the top.
            gps = game_economy.building_gps(state, b.id)
            unlocked = state.zone_index >= b.unlock_zone
            items.append({
                "label": f"{b.name}  Lv {lvl}",
                "sub": f"+{format_number(gps)} g/s" + ("" if unlocked else "  (locked)"),
                "color": (120, 220, 200) if unlocked else C.text_muted,
                "data": b,
            })
        self.list = ScrollList(pygame.Rect(16, 100, 460, cfg.WINDOW_H - 180), items, item_h=48)
        self.list.on_select = self._on_select
        self.selected = None

    def _on_select(self, i, item) -> None:
        self.selected = item["data"].id
        self._build_buy_buttons()

    def _build_buy_buttons(self) -> None:
        self.buy_buttons = []
        if not self.selected:
            return
        state = self.game.state
        b = bd.BY_ID[self.selected]
        x = 500
        y = 120
        for n, label in [(1, "Buy x1"), (10, "Buy x10"), (-1, "Buy Max")]:
            if n == -1:
                n = game_economy.buy_max(state, b.id)
            cost = game_economy.total_cost(state, b.id, max(1, n))
            enabled = state.gold >= cost and state.zone_index >= b.unlock_zone
            btn = Button((x, y, 220, 40), f"{label}  ({format_number(cost)} g)",
                         on_click=lambda nn=n: self._buy(nn), enabled=enabled)
            self.buy_buttons.append(btn)
            y += 48

    def _buy(self, n: int) -> None:
        state = self.game.state
        bought = game_economy.buy(state, self.selected, n)
        if bought > 0:
            self.game.state.save()
            self._build_list()
            self._build_buy_buttons()

    def handle(self, event):
        # Wire UI click sounds: gate each button's click SFX on the
        # player's sound setting. The buy buttons are built dynamically
        # (rebuilt on selection / purchase), so set sound_on each handle
        # call so they are gated on state.sound_on.
        state = self.game.state
        for b in self.buttons + self.buy_buttons:
            b.sound_on = state.sound_on
        if self.list:
            self.list.handle(event)
        for b in self.buttons + self.buy_buttons:
            b.handle(event)

    def update(self, dt):
        for b in self.buttons + self.buy_buttons:
            b.update(dt)
        if self.list:
            self.list.update(dt)
        # Refresh buy button affordability.
        if self.selected:
            state = self.game.state
            b = bd.BY_ID[self.selected]
            for btn, (n, _) in zip(self.buy_buttons, [(1, ""), (10, ""), (-1, "")]):
                if n == -1:
                    n = game_economy.buy_max(state, b.id)
                cost = game_economy.total_cost(state, b.id, max(1, n))
                btn.enabled = state.gold >= cost and state.zone_index >= b.unlock_zone
                btn.label = f"{'Buy x1' if n==1 else 'Buy x10' if n==10 else 'Buy Max'}  ({format_number(cost)} g)"

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Buildings", (cfg.WINDOW_W // 2, 40), font_xl(bold=True), C.text)
        draw_text_center(surf, "Passive gold per second. Buy in bulk to grow your idle income.",
                         (cfg.WINDOW_W // 2, 76), font_sm(), C.text_dim)
        x = 16; y = 100
        x += currency_pill(surf, x, y, "Gold", format_number(state.gold), C.gold) + 10
        currency_pill(surf, x, y, "G/s", format_number(game_economy.total_gps(state)), (120, 220, 200))
        if self.list:
            self.list.draw(surf)
        # Detail.
        if self.selected:
            b = bd.BY_ID[self.selected]
            r = pygame.Rect(500, 100, 300, 200)
            draw_panel(surf, r, fill=(20, 22, 40), border=C.panel_border)
            from assets import building_surface
            surf.blit(building_surface(b.id, 64), (r.x + 16, r.y + 16))
            draw_text(surf, b.name, (r.x + 90, r.y + 20), font_lg(bold=True), C.text)
            draw_text(surf, b.desc, (r.x + 90, r.y + 48), font_sm(), C.text_dim)
            draw_text(surf, f"Level: {state.building_level(b.id)}", (r.x + 16, r.y + 96), font_sm(), C.text)
            # State-aware (tier-scaled) gps — matches the total_gps pill.
            draw_text(surf, f"Gold/sec: {format_number(game_economy.building_gps(state, b.id))}",
                      (r.x + 16, r.y + 116), font_sm(), (120, 220, 200))
            draw_text(surf, f"Unlock: zone {b.unlock_zone + 1}", (r.x + 16, r.y + 136), font_xs(), C.text_dim)
        for b in self.buttons + self.buy_buttons:
            b.draw(surf)
        # Task 36: register a tooltip per building row with live values
        # (the current level, gps, cost, unlock status — a callable-text
        # form so the tooltip reflects the current state when hovered).
        # The ScrollList's items are at fixed positions; we register a
        # tooltip for each building's row rect (including off-screen rows
        # so the count matches the building roster).
        self.tooltips.clear()
        if self.list is not None:
            y0 = self.list.rect.y - int(self.list.scroll)
            for i, b in enumerate(bd.BUILDINGS):
                row_rect = pygame.Rect(self.list.rect.x,
                                       y0 + i * self.list.item_h,
                                       self.list.rect.w, self.list.item_h)
                tip = self._building_tooltip(b.id)
                self.tooltips.register(f"building:{b.id}", row_rect, tip)
        self.tooltips.update(pygame.mouse.get_pos())
        self.tooltips.draw(surf)

    def _building_tooltip(self, bid: str):
        """A callable tooltip for a building (live values from state)."""
        def _text():
            state = self.game.state
            b = bd.BY_ID[bid]
            lvl = state.building_level(bid)
            gps = game_economy.building_gps(state, bid)
            cost = game_economy.building_cost(state, bid)
            unlocked = state.zone_index >= b.unlock_zone
            status = ("Unlocked" if unlocked
                      else f"Unlocks at zone {b.unlock_zone + 1}")
            return (f"{b.name}\nLevel: {lvl}\n"
                    f"Gold/sec: {format_number(gps)}\n"
                    f"Next cost: {format_number(cost)} g\n{status}")
        return _text
