"""Menu hub screen — a full grouped navigation hub.

The game screen's cramped 12-button nav rail (the "menu crams too many
things, poor categorization" complaint) is replaced by a clean 3-button
primary rail (Ascend / Hero / Menu) on the game screen. The full set of
14 screens lives HERE, on the Menu hub, grouped into 4 labeled sections
(Play / Manage / Collect / Meta) with full labels + keyboard-shortcut
badges.

Layout: a 2-column grid of buttons (each 280x48) with a colored section
header above each group. A Back button at the bottom-left returns to the
game screen. Each button calls ``self.game.set_screen(screen_id)`` so the
hub is a pure routing screen (no state mutation of its own).
"""
from __future__ import annotations

import pygame

import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, gradient_v
from ui.widgets import Button


# The 4 sections (in display order). Each entry is
# (section_label, header_color, [(screen_id, label, shortcut), ...]).
# The shortcut is the keyboard key that opens the screen (shown as a
# small badge on the button, e.g. "Buildings  [2]").
_SECTIONS = [
    ("Play", (120, 220, 200), [
        ("game", "Game", "1"),
        ("ascend", "Ascend", "6"),
    ]),
    ("Manage", (255, 180, 90), [
        ("buildings", "Buildings", "2"),
        ("upgrades", "Upgrades", "3"),
        ("skilltree", "Skill Tree", "4"),
        ("pets", "Pets", "5"),
        ("hero", "Hero", "h"),
    ]),
    ("Collect", (255, 240, 120), [
        ("quests", "Quests", "7"),
        ("records", "Records", "8"),
        ("bestiary", "Bestiary", "b"),
        ("godai", "Godai Elements", "g"),
        ("cosmetics", "Cosmetics", "c"),
    ]),
    ("Meta", (160, 170, 200), [
        ("settings", "Settings", "9"),
        ("menu", "Title", "0"),
    ]),
]


class MenuHubScreen:
    """The full Menu hub — all 14 screens grouped into 4 labeled sections."""

    def __init__(self, game) -> None:
        self.game = game
        # The Back button returns to the game screen.
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons: list[Button] = [self.btn_back]
        # Build the section buttons. Each button calls
        # ``self.game.set_screen(screen_id)``; the button label is the full
        # screen name + the keyboard shortcut badge (drawn separately in
        # ``draw`` so the badge reads as a small pill on the right edge).
        self._section_layout: list[tuple[str, tuple, list[Button]]] = []
        self._build_buttons()

    def _build_buttons(self) -> None:
        """Build the 2-column grid of section buttons.

        The grid is laid out top-down per section: a colored section
        header, then the section's buttons in 2 columns (280x48 each,
        8px gap). The sections stack vertically with a 16px gap between
        sections. The total content starts at y=96 (below the title) and
        ends above the Back button (y=WINDOW_H-60).
        """
        bw, bh = 280, 48
        gap_x = 8          # horizontal gap between the 2 columns
        gap_y = 8          # vertical gap between buttons in a column
        section_gap = 16   # gap between sections
        # The 2-column grid: left column x, right column x.
        col_x0 = 60
        col_x1 = col_x0 + bw + gap_x
        y = 96
        self.buttons = [self.btn_back]
        self._section_layout = []
        for section_label, header_color, items in _SECTIONS:
            section_y = y
            # The section header (drawn in ``draw``); reserve its height.
            y += 28
            section_buttons: list[Button] = []
            for i, (screen_id, label, _shortcut) in enumerate(items):
                col = i % 2
                row = i // 2
                bx = col_x0 if col == 0 else col_x1
                by = y + row * (bh + gap_y)
                btn = Button(
                    (bx, by, bw, bh), label,
                    on_click=lambda sid=screen_id: self._goto(sid),
                )
                section_buttons.append(btn)
            self.buttons.extend(section_buttons)
            # Advance y past this section's buttons.
            n_rows = (len(items) + 1) // 2
            y += n_rows * (bh + gap_y) + section_gap
            self._section_layout.append(
                (section_label, header_color, section_buttons))

    def _goto(self, screen_id: str) -> None:
        """Route to a screen (the hub is a pure routing screen)."""
        self.game.set_screen(screen_id)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def handle(self, event):
        # Wire UI click sounds: pass the sound_on gate to each button so
        # the buttons play the ui_click SFX when sound is enabled.
        state = self.game.state
        for b in self.buttons:
            b.sound_on = state.sound_on
            b.handle(event)

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        # Title.
        draw_text_center(surf, "Menu", (cfg.WINDOW_W // 2, 36),
                         font_xl(bold=True), C.text)
        draw_text_center(surf, "All screens — grouped by category.",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
        # Section headers + buttons.
        # The shortcut badge for each button: look up the section's items
        # to find the (screen_id, label, shortcut) for each button (the
        # buttons are built in the same order as the items, so the index
        # aligns).
        for (section_label, header_color, section_buttons), \
                (_sl, _hc, items) in zip(self._section_layout, _SECTIONS):
            # The section header (colored, above the buttons).
            header_y = section_buttons[0].rect.y - 28
            draw_text(surf, section_label, (60, header_y),
                      font_lg(bold=True), header_color)
            for i, b in enumerate(section_buttons):
                b.draw(surf)
                # The keyboard-shortcut badge (a small pill on the right
                # edge of the button).
                shortcut = items[i][2]
                self._draw_shortcut_badge(surf, b.rect, shortcut)

        # Back button.
        self.btn_back.draw(surf)

    def _draw_shortcut_badge(self, surf, rect, shortcut: str) -> None:
        """Draw a small keyboard-shortcut badge on the right edge of a button.

        The badge is a small rounded rect with the shortcut key label
        (font_xs) so the player can see the keyboard shortcut at a glance.
        """
        bw, bh = 22, 18
        bx = rect.right - bw - 6
        by = rect.centery - bh // 2
        badge = pygame.Rect(bx, by, bw, bh)
        pygame.draw.rect(surf, C.panel_lo, badge, border_radius=4)
        pygame.draw.rect(surf, C.panel_border, badge, 1, border_radius=4)
        img = font_xs(bold=True).render(shortcut, True, C.text_dim)
        r = img.get_rect(center=badge.center)
        surf.blit(img, r)
