"""Run-upgrades screen: temporary stat boosts bought with gold."""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel
from ui.widgets import Button, currency_pill
from ui.tooltip import TooltipManager
from utils import format_number
from core import game_economy


class UpgradesScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_back]
        self.upgrade_buttons: list[Button] = []
        self._build_buttons()
        # Task 36 (pl-hints-nav-tooltips): a TooltipManager with
        # callable-text (live values from state) for every upgrade.
        self.tooltips = TooltipManager()

    def _build_buttons(self) -> None:
        self.upgrade_buttons = []
        state = self.game.state
        x = 60; y = 120
        for key, label, *_ in cfg.TAP_UPGRADE_DEFS:
            lvl = state.upgrade_level(key)
            cost = game_economy.upgrade_cost(state, key)
            btn = Button((x, y, 560, 40),
                         f"{label}  Lv {lvl}  →  {format_number(cost)} g",
                         on_click=lambda k=key: self._buy(k),
                         enabled=game_economy.can_upgrade(state, key))
            self.upgrade_buttons.append(btn)
            y += 44

    def _buy(self, key: str) -> None:
        state = self.game.state
        if game_economy.apply_upgrade(state, key):
            self.game.state.save()
            self._build_buttons()

    def handle(self, event):
        for b in self.buttons + self.upgrade_buttons:
            b.handle(event)

    def update(self, dt):
        state = self.game.state
        for btn, (key, label, *_) in zip(self.upgrade_buttons, cfg.TAP_UPGRADE_DEFS):
            lvl = state.upgrade_level(key)
            cost = game_economy.upgrade_cost(state, key)
            btn.label = f"{label}  Lv {lvl}  →  {format_number(cost)} g"
            btn.enabled = game_economy.can_upgrade(state, key)
        for b in self.buttons + self.upgrade_buttons:
            b.update(dt)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Upgrades", (cfg.WINDOW_W // 2, 40), font_xl(bold=True), C.text)
        draw_text_center(surf, "Temporary boosts. Reset on ascension.",
                         (cfg.WINDOW_W // 2, 76), font_sm(), C.text_dim)
        x = 16; y = 100
        currency_pill(surf, x, y, "Gold", format_number(state.gold), C.gold)
        for b in self.buttons + self.upgrade_buttons:
            b.draw(surf)
        # Task 36: register a tooltip per upgrade button with live values
        # (the current level, cost, and effect — a callable-text form so
        # the tooltip reflects the current state when hovered).
        self.tooltips.clear()
        for btn, (key, label, *_) in zip(self.upgrade_buttons,
                                         cfg.TAP_UPGRADE_DEFS):
            tip = self._upgrade_tooltip(key, label)
            self.tooltips.register(f"upgrade:{key}", btn.rect, tip)
        self.tooltips.update(pygame.mouse.get_pos())
        self.tooltips.draw(surf)

    def _upgrade_tooltip(self, key: str, label: str):
        """A callable tooltip for an upgrade (live values from state).

        Returns a zero-arg callable that reads the current level, cost,
        and effect from state so the tooltip reflects the current state
        when hovered (the callable is evaluated lazily by the
        TooltipManager only when the region is hovered).
        """
        def _text():
            state = self.game.state
            lvl = state.upgrade_level(key)
            cost = game_economy.upgrade_cost(state, key)
            base = cfg.UPGRADE_BASE_EFFECT.get(key, 0.0)
            growth = cfg.UPGRADE_EFFECT_GROWTH.get(key, 1.0)
            effect = base * (growth ** max(0, lvl - 1)) * max(1, lvl)
            can = game_economy.can_upgrade(state, key)
            status = "Affordable" if can else "Need more gold"
            return (f"{label}\nLevel: {lvl}/{cfg.UPGRADE_MAX_LEVEL}\n"
                    f"Cost: {format_number(cost)} g\n"
                    f"Next effect: +{format_number(effect)}\n{status}")
        return _text
