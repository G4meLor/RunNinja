"""Skill-tree screen (elixir): the permanent tree across 7 branches.

Task 27 / pl-juice-polish: a "Respec" button that calls
``core.ascend.respec_skill_tree(state)`` -- a FREE refund of all elixir
spent on the tree + a clear, so the player can re-spend on a different
build. The button is visible when the player has at least 1 unlocked
node (no respec if the tree is empty); on click, it refunds the total
cost of unlocked nodes, saves, and refreshes the screen.

Task 36 (pl-hints-nav-tooltips): a TooltipManager with callable-text
(live values from state) for every skill-tree node. The tooltip shows
the node's name, description, cost, branch, effect, and unlock status.
"""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel
from ui.widgets import Button, currency_pill
from ui.tooltip import TooltipManager
from ui.cb_symbols import branch_symbol  # Task 38: color-blind-safe symbols
from utils import format_number
from data import skill_tree as st
from core import skill_unlock
from core import ascend as asc


class SkillTreeScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        # Task 27: the "Respec" button. Calls ``asc.respec_skill_tree(state)``
        # on click, which refunds all elixir spent on the tree + clears it
        # (a free, manual respec). The button is enabled only when the
        # player has at least 1 unlocked node (no respec if the tree is
        # empty). The label shows the refund amount so the player can see
        # how much elixir they'd get back before clicking.
        self.btn_respec = Button(
            (cfg.WINDOW_W - 200, cfg.WINDOW_H - 60, 180, 44),
            "Respec", on_click=self._do_respec, color=(150, 80, 220),
            hint="Refund all elixir spent on the tree.")
        self.buttons = [self.btn_back, self.btn_respec]
        self.hover_node = None
        self.node_rects: dict[str, pygame.Rect] = {}
        # Task 36: a TooltipManager with callable-text (live values from
        # state) for every skill-tree node.
        self.tooltips = TooltipManager()

    def _do_respec(self) -> None:
        """Refund all elixir spent on the skill tree + clear it.

        Calls ``asc.respec_skill_tree(state)`` (a free refund), saves the
        state, and notifies the player. The button is only enabled when
        the player has at least 1 unlocked node, so this always refunds
        > 0 elixir.
        """
        state = self.game.state
        if not state.skill_tree:
            return
        refunded = asc.respec_skill_tree(state)
        if refunded > 0:
            state.save()
            # A toast on the game screen so the player sees the refund.
            self.game.screens["game"].notify(
                f"Respec: +{format_number(refunded)} elixir refunded.",
                (120, 220, 200))

    def _respec_refund_amount(self) -> int:
        """The elixir that would be refunded by a respec right now.

        The sum of the ``cost`` of every unlocked node (the same value the
        player paid to unlock it). Returns 0 if the tree is empty.
        """
        state = self.game.state
        return sum(st.BY_ID[nid].cost for nid in state.skill_tree
                  if nid in st.BY_ID)

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
        # Task 27: enable the respec button only when the player has at
        # least 1 unlocked node (no respec if the tree is empty). The
        # label shows the refund amount so the player can see how much
        # elixir they'd get back before clicking.
        refund = self._respec_refund_amount()
        self.btn_respec.enabled = refund > 0
        if refund > 0:
            self.btn_respec.label = f"Respec (+{format_number(refund)})"
        else:
            self.btn_respec.label = "Respec"

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
            # Task 38 (pl-accessibility): a color-blind-safe branch symbol
            # is blitted alongside the branch color (the shape is the
            # redundant cue; the color stays).
            sym = branch_symbol(branch, 22)
            surf.blit(sym, (header.x + 6, header.centery - sym.get_height() // 2))
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
        # Task 36: register a tooltip per skill-tree node with live values
        # (the node's effect, cost, unlock status — a callable-text form so
        # the tooltip reflects the current state when hovered).
        self.tooltips.clear()
        for nid, r in self.node_rects.items():
            tip = self._node_tooltip(nid)
            self.tooltips.register(f"node:{nid}", r, tip)
        self.tooltips.update(pygame.mouse.get_pos())
        self.tooltips.draw(surf)

    def _node_tooltip(self, nid: str):
        """A callable tooltip for a skill-tree node (live values)."""
        def _text():
            state = self.game.state
            node = st.BY_ID.get(nid)
            if node is None:
                return ""
            unlocked = nid in state.skill_tree
            can = skill_unlock.can_unlock(state, nid)
            if unlocked:
                status = "Unlocked"
            elif can:
                status = "Can unlock"
            else:
                prereq = node.prereq
                if prereq and prereq not in state.skill_tree:
                    status = f"Requires {st.BY_ID[prereq].name}"
                else:
                    status = f"Need {node.cost} elixir"
            return (f"{node.name}\n{node.desc}\n"
                    f"Cost: {node.cost} elixir\n"
                    f"Branch: {node.branch}\n{status}")
        return _text
