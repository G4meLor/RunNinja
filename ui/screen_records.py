"""Records / stats dashboard for Tap Ninja."""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button
from utils import format_number
from data import quests as q
from core import game_economy


class RecordsScreen:
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
        draw_text_center(surf, "Records", (cfg.WINDOW_W // 2, 40), font_xl(bold=True), C.text)
        draw_text_center(surf, "The road you have walked.",
                         (cfg.WINDOW_W // 2, 76), font_sm(), C.text_dim)

        stats = [
            ("Total distance", f"{format_number(state.total_distance)} m", C.exp),
            ("Enemies slain", format_number(state.monsters_killed), C.hp),
            ("Bosses slain", format_number(state.bosses_killed), C.text_bad),
            ("Lifetime gold", format_number(state.lifetime_gold), C.gold),
            ("Total pulls", format_number(state.pet_pulls), (255, 180, 60)),
            ("Ascensions", format_number(state.total_ascensions), (150, 80, 220)),
            ("Best combo", format_number(state.best_combo_ever), C.gold),
            ("Playtime", _fmt_time(state.playtime), C.text),
            ("Buildings", str(len(state.buildings)), (120, 220, 200)),
            ("Skills", f"{len(state.skill_tree)}/54", (180, 130, 255)),
        ]
        card_w, card_h = 280, 80
        gap = 14
        cols = 4
        grid_w = cols * card_w + (cols - 1) * gap
        x0 = (cfg.WINDOW_W - grid_w) // 2
        y0 = 120
        for i, (label, val, col) in enumerate(stats):
            r_idx, c_idx = divmod(i, cols)
            x = x0 + c_idx * (card_w + gap)
            y = y0 + r_idx * (card_h + gap)
            r = pygame.Rect(x, y, card_w, card_h)
            draw_panel(surf, r, fill=C.panel, border=C.panel_border)
            draw_text(surf, label, (r.x + 12, r.y + 10), font_xs(), C.text_dim)
            draw_text(surf, val, (r.x + 12, r.y + 30), font_lg(bold=True), col)

        # Collection.
        cr = pygame.Rect(x0, y0 + 3 * (card_h + gap) + 8, grid_w, 50)
        draw_panel(surf, cr, fill=C.panel, border=C.panel_border)
        draw_text(surf, f"Pets  {len(state.pets)}/12   ·   Achievements  {len(state.achievements)}/{len(q.ACHIEVEMENTS)}",
                  (cr.x + 14, cr.y + 16), font_md(bold=True), C.text)

        for b in self.buttons:
            b.draw(surf)


def _fmt_time(s):
    s = int(s)
    if s < 60: return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60: return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"
