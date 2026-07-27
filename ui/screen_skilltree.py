"""Skill-tree screen (elixir): the permanent tree across 7 branches."""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel
from ui.widgets import Button, currency_pill
from utils import format_number
from data import skill_tree as st
from core import skill_unlock


class SkillTreeScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_back]
        self.hover_node = None
        self.node_rects: dict[str, pygame.Rect] = {}

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEMOTION:
            self.hover_node = None
            for nid, r in self.node_rects.items():
                if r.collidepoint(event.pos):
                    self.hover_node = nid
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.hover_node:
                state = self.game.state
                if skill_unlock.can_unlock(state, self.hover_node):
                    skill_unlock.unlock(state, self.hover_node)
                    self.game.state.save()

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Skill Tree", (cfg.WINDOW_W // 2, 36), font_xl(bold=True), C.text)
        draw_text_center(surf, "Spend Elixir on permanent upgrades.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
        x = 16; y = 100
        currency_pill(surf, x, y, "Elixir", format_number(state.elixir), (120, 220, 200))
        unlocked, total = len(state.skill_tree), len(st.NODES)
        draw_text(surf, f"Unlocked: {unlocked}/{total}", (cfg.WINDOW_W - 200, 100), font_sm(), C.text_dim)

        self.node_rects = {}
        branches = st.BRANCHES
        n = len(branches)
        col_w = (cfg.WINDOW_W - 80) // n
        top_y = 140
        col_h = cfg.WINDOW_H - 220
        for i, branch in enumerate(branches):
            bx = 40 + i * col_w
            col = st.branch_color(branch)
            header = pygame.Rect(bx + 10, top_y, col_w - 20, 30)
            draw_panel(surf, header, fill=(col[0] // 5, col[1] // 5, col[2] // 5), border=col)
            draw_text_center(surf, branch.capitalize(), header.center, font_sm(bold=True), col)
            nodes = st.nodes_by_branch(branch)
            for j, node in enumerate(nodes):
                ny = top_y + 40 + j * (col_h - 40) // max(1, len(nodes))
                r = pygame.Rect(bx + col_w // 2 - 65, ny, 130, 50)
                self.node_rects[node.id] = r
                if node.prereq and node.prereq in self.node_rects:
                    pr = self.node_rects[node.prereq]
                    pygame.draw.line(surf, col if node.id in state.skill_tree else C.panel_border,
                                     (pr.centerx, pr.bottom), (r.centerx, r.top), 2)
                unlocked_n = node.id in state.skill_tree
                can = skill_unlock.can_unlock(state, node.id)
                if unlocked_n:
                    draw_panel(surf, r, fill=(col[0] // 4, col[1] // 4, col[2] // 4), border=col, border_w=2)
                    draw_text_center(surf, node.name, r.center, font_xs(bold=True), C.text)
                elif can:
                    fill = (40, 48, 78) if self.hover_node == node.id else (30, 34, 56)
                    draw_panel(surf, r, fill=fill, border=col)
                    draw_text_center(surf, node.name, r.center, font_xs(bold=True), C.text)
                    draw_text_center(surf, f"{node.cost} e", (r.centerx, r.bottom + 10),
                                     font_xs(), (120, 220, 200))
                else:
                    draw_panel(surf, r, fill=C.panel_lo, border=C.panel_border)
                    draw_text_center(surf, node.name, r.center, font_xs(), C.text_muted)
        if self.hover_node:
            node = st.BY_ID[self.hover_node]
            tx, ty = pygame.mouse.get_pos()
            tx += 16; ty += 16
            if tx + 260 > cfg.WINDOW_W:
                tx = cfg.WINDOW_W - 268
            if ty + 90 > cfg.WINDOW_H:
                ty = cfg.WINDOW_H - 98
            tr = pygame.Rect(tx, ty, 260, 90)
            draw_panel(surf, tr, fill=C.panel, border=C.panel_border_hi)
            draw_text(surf, node.name, (tr.x + 10, tr.y + 8), font_sm(bold=True), C.text)
            draw_text(surf, node.desc, (tr.x + 10, tr.y + 30), font_xs(), C.text_dim)
            draw_text(surf, f"Cost: {node.cost} elixir", (tr.x + 10, tr.y + 52), font_xs(), (120, 220, 200))
            draw_text(surf, f"Branch: {node.branch}", (tr.x + 10, tr.y + 70), font_xs(), C.text_muted)
        for b in self.buttons:
            b.draw(surf)
