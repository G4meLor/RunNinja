"""Godai Elements screen — the five-element research sub-menu.

A dedicated screen for the Godai branch of the elixir skill tree: the
gate node sits at the centre of a circle and the four elements (Void,
Wind, Fire, Water) sit around it.  Each element node shows its current
accumulated bonus value (read from ``aggregate_bonuses``), a short
effect label, and its unlock state.  Clicking the gate or an element
routes to the skill-tree screen focused on the Godai branch so the
player can spend elixir to deepen that path.

The screen is purely visual + routing — it does **not** unlock nodes
itself; unlocking happens on the skill-tree screen.  It reads live state
each frame through ``aggregate_bonuses`` so the values update the moment
a node is unlocked elsewhere.

Rendering uses pygame primitives only and the cached theme fonts; no
per-frame allocations in the hot path.
"""
from __future__ import annotations

import math

import pygame

import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar, gradient_v
from ui.widgets import Button, currency_pill
from utils import format_number
from data import skill_tree as st
from core.bonuses import aggregate_bonuses


# ---------------------------------------------------------------------------
# Layout  (module-level so it is computed once, not per frame)
# ---------------------------------------------------------------------------
# Diagram centre and radius for the four-element ring.
_DIAG_CX = 480
_DIAG_CY = 410
_DIAG_R = 170

# Element-node radius (the circle drawn for each element).
_ELEM_R = 50
_GATE_R = 62

# The four element ids in clockwise order starting at the top.  Each has:
# (id, label, effect_key, effect_label, engine_use, angle, color).
# angle is measured from straight-up, clockwise; the node position is
# (cx + R*sin(a), cy - R*cos(a)).
_ELEMENTS = (
    ("godai_void",  "VOID",  "godai_void",  "Elixir gain",  "Ascension elixir multiplier", 0.0,           (170, 110, 220)),
    ("godai_wind",  "WIND",  "godai_wind",  "Gold / sec",   "Passive building income",      (math.pi / 2), (180, 220, 255)),
    ("godai_fire",  "FIRE",  "godai_fire",  "Coin gold",    "Enemy gold multiplier",        (math.pi),     (255, 130, 90)),
    ("godai_water", "WATER", "godai_water", "Hero power",   "Max HP / defence",             (3 * math.pi / 2), (110, 200, 230)),
)

# Detail panel on the right.
_DETAIL_RECT = pygame.Rect(780, 130, 480, 560)

# Gate node id.
_GATE_ID = "godai_gate"


def _node_pos(angle: float) -> tuple[int, int]:
    """Screen position of an element node at the given ring angle."""
    x = _DIAG_CX + int(_DIAG_R * math.sin(angle))
    y = _DIAG_CY - int(_DIAG_R * math.cos(angle))
    return (x, y)


def _darken(color: tuple[int, int, int], factor: float = 0.35) -> tuple[int, int, int]:
    """A darker shade of an element color, used for node fills."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linear blend between two colors, clamped to [0,1]."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


class GodaiScreen:
    """Godai Elements research sub-menu.

    handle / update / draw — the standard screen triple.  ``handle``
    routes node clicks to the skill-tree screen; ``draw`` renders the
    pentagon diagram + detail panel.
    """

    def __init__(self, game) -> None:
        self.game = game
        # Back button (bottom-left, same convention as the other screens).
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                              on_click=lambda: self.game.set_screen("game"))
        # "Open skill tree" button in the detail panel — routes to the
        # skill-tree screen so the player can actually unlock the node.
        self.btn_skilltree = Button(
            (_DETAIL_RECT.x + 20, _DETAIL_RECT.bottom - 70,
             _DETAIL_RECT.w - 40, 48),
            "Open Skill Tree",
            on_click=lambda: self.game.set_screen("skilltree"),
            color=(150, 80, 220),
        )
        self.buttons = [self.btn_back, self.btn_skilltree]
        # Currently selected node id (gate or an element) for the detail panel.
        self.selected: str = _GATE_ID
        # Hovered node id, set in handle() each mouse motion.
        self.hover: str | None = None
        # Node hit-rects, recomputed each draw (positions are fixed but we
        # rebuild the dict so the rects are fresh pygame.Rect objects).
        self.node_rects: dict[str, pygame.Rect] = {}
        # Precompute element positions once — they never move.
        self._positions: dict[str, tuple[int, int]] = {
            _GATE_ID: (_DIAG_CX, _DIAG_CY),
        }
        for eid, _label, _key, _eff, _use, angle, _col in _ELEMENTS:
            self._positions[eid] = _node_pos(angle)

    # -----------------------------------------------------------------
    # Input
    # -----------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> None:
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEMOTION:
            self.hover = self._node_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._node_at(event.pos)
            if hit is not None:
                # Select the node for the detail panel, and route to the
                # skill-tree screen so the player can unlock/upgrade it.
                self.selected = hit
                self.game.set_screen("skilltree")

    def _node_at(self, pos: tuple[int, int]) -> str | None:
        """Return the node id under the mouse, or None.

        Uses the precomputed ``_positions`` (set in ``__init__``) so hit
        testing works even before the first ``draw`` populates
        ``node_rects``.
        """
        for nid, (nx, ny) in self._positions.items():
            r = _GATE_R if nid == _GATE_ID else _ELEM_R
            if (pos[0] - nx) ** 2 + (pos[1] - ny) ** 2 <= r * r:
                return nid
        return None

    # -----------------------------------------------------------------
    # Update
    # -----------------------------------------------------------------
    def update(self, dt: float) -> None:
        for b in self.buttons:
            b.update(dt)

    # -----------------------------------------------------------------
    # Draw
    # -----------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        state = self.game.state
        evo = aggregate_bonuses(state)
        godai_unlocked = _GATE_ID in state.skill_tree

        # Background.
        surf.fill(C.bg_top)
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)

        # Title.
        draw_text_center(surf, "Godai Elements", (cfg.WINDOW_W // 2, 36),
                         font_xl(bold=True), st.branch_color("godai"))
        draw_text_center(surf, "The five-element path of deep progression.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)

        # Elixir pill (top-left) — the currency the gate + elements cost.
        currency_pill(surf, 16, 100, "Elixir", format_number(state.elixir),
                      (120, 220, 200))
        # Gate unlock status (top-right of the diagram column).
        gate_status = "Unlocked" if godai_unlocked else "Locked"
        gate_col = C.text_good if godai_unlocked else C.text_muted
        draw_text(surf, f"Gate: {gate_status}",
                  (cfg.WINDOW_W - 200, 100), font_sm(bold=True), gate_col)

        # ----- The diagram -----
        self._draw_diagram(surf, state, evo, godai_unlocked)

        # ----- Detail panel -----
        self._draw_detail(surf, state, evo, godai_unlocked)

        # Buttons.
        for b in self.buttons:
            b.draw(surf)

    # -----------------------------------------------------------------
    # Diagram (gate + 4 elements + connecting lines)
    # -----------------------------------------------------------------
    def _draw_diagram(self, surf: pygame.Surface, state, evo: dict, godai_unlocked: bool) -> None:
        # Build the node hit-rects for this frame.
        self.node_rects = {}

        # --- Connecting lines: gate <-> each element ---
        # Draw the lines *under* the nodes so the circles cap them.
        for eid, _label, _key, _eff, _use, angle, col in _ELEMENTS:
            ex, ey = self._positions[eid]
            unlocked = eid in state.skill_tree
            line_col = col if unlocked else C.panel_border
            # Slightly thicker + brighter when unlocked.
            pygame.draw.line(surf, line_col, (_DIAG_CX, _DIAG_CY), (ex, ey),
                             3 if unlocked else 2)

        # --- Outer ring (faint guide circle through the 4 elements) ---
        ring_rect = pygame.Rect(_DIAG_CX - _DIAG_R, _DIAG_CY - _DIAG_R,
                                _DIAG_R * 2, _DIAG_R * 2)
        pygame.draw.circle(surf, C.panel_lo, (_DIAG_CX, _DIAG_CY), _DIAG_R, 1)

        # --- Element nodes ---
        for eid, label, key, eff_label, _use, angle, col in _ELEMENTS:
            ex, ey = self._positions[eid]
            self.node_rects[eid] = pygame.Rect(ex - _ELEM_R, ey - _ELEM_R,
                                               _ELEM_R * 2, _ELEM_R * 2)
            unlocked = eid in state.skill_tree
            value = evo.get(key, 0.0)
            self._draw_element_node(surf, ex, ey, label, eff_label, value,
                                    col, unlocked,
                                    hover=(self.hover == eid),
                                    selected=(self.selected == eid))

        # --- Gate node (centre) ---
        self.node_rects[_GATE_ID] = pygame.Rect(
            _DIAG_CX - _GATE_R, _DIAG_CY - _GATE_R,
            _GATE_R * 2, _GATE_R * 2)
        self._draw_gate_node(surf, godai_unlocked,
                             hover=(self.hover == _GATE_ID),
                             selected=(self.selected == _GATE_ID))

    def _draw_element_node(self, surf: pygame.Surface, ex: int, ey: int,
                           label: str, eff_label: str, value: float,
                           col: tuple[int, int, int], unlocked: bool,
                           *, hover: bool, selected: bool) -> None:
        # Fill: dark tint of the element color when unlocked, else panel_lo.
        if unlocked:
            fill = _darken(col, 0.30)
        else:
            fill = C.panel_lo
        pygame.draw.circle(surf, fill, (ex, ey), _ELEM_R)
        # Border: element color when unlocked, brighter on hover/selected.
        border = col if unlocked else C.panel_border
        border_w = 3 if (hover or selected) else 2
        pygame.draw.circle(surf, border, (ex, ey), _ELEM_R, border_w)
        # Selection / hover ring.
        if hover or selected:
            ring_col = _blend(col, (255, 255, 255), 0.5) if unlocked else C.panel_border_hi
            pygame.draw.circle(surf, ring_col, (ex, ey), _ELEM_R + 5, 2)

        # Element label (top of node).
        draw_text_center(surf, label, (ex, ey - 22), font_md(bold=True),
                         col if unlocked else C.text_muted)
        # Effect label (middle).
        draw_text_center(surf, eff_label, (ex, ey - 4), font_xs(), C.text_dim)
        # Accumulated bonus value (bottom).
        if value > 0:
            val_txt = f"+{int(round(value * 100))}%"
            val_col = C.text_good
        else:
            val_txt = "—"
            val_col = C.text_muted
        draw_text_center(surf, val_txt, (ex, ey + 18), font_sm(bold=True), val_col)

    def _draw_gate_node(self, surf: pygame.Surface, unlocked: bool,
                        *, hover: bool, selected: bool) -> None:
        col = st.branch_color("godai")
        fill = _darken(col, 0.30) if unlocked else C.panel_lo
        pygame.draw.circle(surf, fill, (_DIAG_CX, _DIAG_CY), _GATE_R)
        border = col if unlocked else C.panel_border
        border_w = 3 if (hover or selected) else 2
        pygame.draw.circle(surf, border, (_DIAG_CX, _DIAG_CY), _GATE_R, border_w)
        if hover or selected:
            ring_col = _blend(col, (255, 255, 255), 0.5) if unlocked else C.panel_border_hi
            pygame.draw.circle(surf, ring_col, (_DIAG_CX, _DIAG_CY), _GATE_R + 5, 2)
        # Label.
        draw_text_center(surf, "GATE", (_DIAG_CX, _DIAG_CY - 18),
                         font_md(bold=True), col if unlocked else C.text_muted)
        draw_text_center(surf, "Godai", (_DIAG_CX, _DIAG_CY + 4), font_xs(), C.text_dim)
        # Cost or unlocked marker.
        if unlocked:
            draw_text_center(surf, "OPEN", (_DIAG_CX, _DIAG_CY + 22),
                             font_sm(bold=True), C.text_good)
        else:
            node = st.BY_ID[_GATE_ID]
            draw_text_center(surf, f"{node.cost} e", (_DIAG_CX, _DIAG_CY + 22),
                             font_sm(bold=True), (120, 220, 200))

    # -----------------------------------------------------------------
    # Detail panel (right side)
    # -----------------------------------------------------------------
    def _draw_detail(self, surf: pygame.Surface, state, evo: dict, godai_unlocked: bool) -> None:
        r = _DETAIL_RECT
        draw_panel(surf, r, fill=C.panel, border=C.panel_border, border_w=1)

        nid = self.selected
        if nid == _GATE_ID:
            node = st.BY_ID[_GATE_ID]
            title = node.name
            color = st.branch_color("godai")
            unlocked = nid in state.skill_tree
            value = evo.get(node.effect_key, 0.0)
            effect_txt = "Unlocks the Godai Elements sub-tree."
            use_txt = "Enables Void, Wind, Fire, Water."
            cost = node.cost
            prereq_name = st.BY_ID[node.prereq].name if node.prereq else "—"
            prereq_ok = (node.prereq in state.skill_tree) if node.prereq else True
        else:
            node = st.BY_ID[nid]
            # Find this element's metadata.
            meta = next((m for m in _ELEMENTS if m[0] == nid), None)
            label = meta[1] if meta else node.name
            color = meta[6] if meta else st.branch_color("godai")
            title = node.name
            unlocked = nid in state.skill_tree
            value = evo.get(node.effect_key, 0.0)
            effect_txt = node.desc
            use_txt = meta[4] if meta else ""
            cost = node.cost
            prereq_name = st.BY_ID[node.prereq].name if node.prereq else "—"
            prereq_ok = (node.prereq in state.skill_tree) if node.prereq else True

        # Header.
        draw_text(surf, title, (r.x + 20, r.y + 16), font_lg(bold=True), color)
        # Branch tag.
        draw_text(surf, "Branch: Godai", (r.x + 20, r.y + 48), font_xs(), C.text_muted)

        # Status row.
        status_y = r.y + 80
        if unlocked:
            draw_text(surf, "UNLOCKED", (r.x + 20, status_y),
                     font_md(bold=True), C.text_good)
        else:
            draw_text(surf, "LOCKED", (r.x + 20, status_y),
                     font_md(bold=True), C.text_muted)

        # Accumulated bonus (the headline number for this element).
        bonus_y = r.y + 120
        draw_text(surf, "Accumulated bonus", (r.x + 20, bonus_y),
                 font_xs(), C.text_dim)
        if value > 0:
            val_txt = f"+{int(round(value * 100))}%"
            val_col = C.text_good
        elif nid == _GATE_ID and unlocked:
            val_txt = "Active"
            val_col = C.text_good
        else:
            val_txt = "0%"
            val_col = C.text_muted
        draw_text(surf, val_txt, (r.x + 20, bonus_y + 18),
                 font_xl(bold=True), val_col)

        # Effect + engine-use description.
        desc_y = r.y + 180
        draw_text(surf, "Effect", (r.x + 20, desc_y), font_xs(), C.text_dim)
        # Wrap the effect text by crude char count.
        self._draw_wrapped(surf, effect_txt, (r.x + 20, desc_y + 18),
                           r.w - 40, font_sm(), C.text)
        use_y = desc_y + 18 + self._wrapped_height(effect_txt, r.w - 40, font_sm()) + 12
        draw_text(surf, "Applied to", (r.x + 20, use_y), font_xs(), C.text_dim)
        self._draw_wrapped(surf, use_txt, (r.x + 20, use_y + 18),
                          r.w - 40, font_sm(), C.text_dim)

        # Upgrade path: prereq + cost.
        path_y = r.y + 340
        draw_text(surf, "Upgrade path", (r.x + 20, path_y),
                 font_md(bold=True), C.text)
        draw_text(surf, f"Prerequisite: {prereq_name}",
                 (r.x + 20, path_y + 24), font_sm(),
                 C.text_good if prereq_ok else C.text_bad)
        # Cost row.
        cost_col = (120, 220, 200) if state.elixir >= cost else C.text_muted
        draw_text(surf, f"Cost: {cost} Elixir",
                 (r.x + 20, path_y + 48), font_sm(bold=True), cost_col)
        # Elixir affordability bar.
        bar = pygame.Rect(r.x + 20, path_y + 72, r.w - 40, 12)
        pct = min(1.0, state.elixir / cost) if cost > 0 else 1.0
        draw_bar(surf, bar, pct, fill=(120, 220, 200), bg=C.mp_bg,
                 border=C.panel_border)

        # Hint.
        if not unlocked:
            draw_text(surf, "Click the node or “Open Skill Tree” to unlock.",
                     (r.x + 20, path_y + 100), font_xs(), C.text_muted)
        else:
            draw_text(surf, "Unlocked. Open the skill tree to deepen this path.",
                     (r.x + 20, path_y + 100), font_xs(), C.text_dim)

    # -----------------------------------------------------------------
    # Tiny text wrapper (pygame fonts don't wrap).  Allocates a list per
    # call but only for the detail panel, not the hot loop.
    # -----------------------------------------------------------------
    def _draw_wrapped(self, surf: pygame.Surface, text: str, pos: tuple[int, int],
                      max_w: int, font: pygame.font.Font,
                      color: tuple[int, int, int]) -> None:
        x, y = pos
        for line in self._wrap(text, max_w, font):
            draw_text(surf, line, (x, y), font, color)
            y += font.get_height() + 2

    def _wrapped_height(self, text: str, max_w: int, font: pygame.font.Font) -> int:
        lines = self._wrap(text, max_w, font)
        return max(1, len(lines)) * (font.get_height() + 2)

    @staticmethod
    def _wrap(text: str, max_w: int, font: pygame.font.Font) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        cur = words[0]
        for w in words[1:]:
            tentative = cur + " " + w
            if font.size(tentative)[0] <= max_w:
                cur = tentative
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines
