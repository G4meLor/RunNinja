"""Quests screen: daily quests + achievements."""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill
from utils import format_number
from data import quests as q
from core import quests as qcore


class QuestsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_back]

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Quests", (cfg.WINDOW_W // 2, 36), font_xl(bold=True), C.text)
        draw_text_center(surf, "Daily quests refresh every 24h.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
        x = 16; y = 100
        x += currency_pill(surf, x, y, "Medals", format_number(state.medals), (200, 200, 220)) + 10
        currency_pill(surf, x, y, "Amber", format_number(state.amber), (255, 180, 60))

        # Daily quests.
        draw_text(surf, "Daily Quests", (60, 130), font_lg(bold=True), C.text)
        y = 170
        for dq_state in state.daily_quests:
            dq = next((d for d in q.DAILY_POOL if d.id == dq_state["id"]), None)
            if dq is None:
                continue
            r = pygame.Rect(60, y, 560, 56)
            draw_panel(surf, r, fill=C.panel, border=C.panel_border)
            draw_text(surf, dq.name, (r.x + 14, r.y + 8), font_md(bold=True), C.text)
            draw_text(surf, dq.desc, (r.x + 14, r.y + 30), font_xs(), C.text_dim)
            progress = dq_state.get("progress", 0)
            claimed = dq_state.get("claimed", False)
            bar = pygame.Rect(r.right - 180, r.y + 20, 160, 12)
            pct = min(1.0, progress / dq.target)
            draw_bar(surf, bar, pct, fill=C.gold if claimed else C.exp,
                     bg=C.mp_bg, border=C.panel_border)
            draw_text(surf, f"{int(min(progress, dq.target))}/{int(dq.target)}",
                      (r.right - 180, r.y + 36), font_xs(), C.text_dim)
            if claimed:
                draw_text(surf, "✓", (r.right - 30, r.y + 18), font_md(bold=True), C.text_good)
            y += 64

        # Achievements.
        # Visible (non-hidden) achievements are shown in the main list;
        # hidden/secret achievements are shown in a separate "???"
        # section below so their cryptic hints are ALWAYS rendered
        # (gp-permanent-scaling: the player has an in-game path to the
        # unlock that is NOT wiki-dependent). The previous ``[:7]``
        # slice cut the list before the hidden achievements (positions
        # 19+) so the hints were never displayed.
        y = 390
        draw_text(surf, "Achievements", (60, y), font_lg(bold=True), C.text)
        y += 34
        visible = [a for a in q.ACHIEVEMENTS if not getattr(a, "hidden", False)]
        hidden = [a for a in q.ACHIEVEMENTS if getattr(a, "hidden", False)]
        for a in visible[:6]:
            unlocked = a.id in state.achievements
            col = C.text_good if unlocked else C.text_muted
            draw_text(surf, ("✓ " if unlocked else "○ ") + a.name + "  —  " + a.desc,
                      (60, y), font_xs(), col)
            y += 22
        # Hidden / secret achievements -- a separate "???" section. The
        # cryptic hint is shown until unlocked (NOT the full desc) so
        # the player has an in-game path to the unlock that is NOT
        # wiki-dependent. After unlock, show the full name + desc.
        y += 10
        draw_text(surf, "???  Hidden", (60, y), font_md(bold=True), C.gold)
        y += 24
        for a in hidden:
            unlocked = a.id in state.achievements
            col = C.text_good if unlocked else C.text_muted
            if unlocked:
                label = "✓ " + a.name + "  —  " + a.desc
            else:
                label = "?  " + a.hint
            draw_text(surf, label, (60, y), font_xs(), col)
            y += 22

        for b in self.buttons:
            b.draw(surf)
