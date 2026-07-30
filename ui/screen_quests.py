"""Quests screen: daily + weekly + chapter quests + achievements.

Quest variety (Task 26 / cnt-quest-codex): the daily pool is now one of
THREE quest tiers -- daily (refresh 24h), weekly (refresh 7d, bigger
reward), chapter (one-time, tied to zone progression). The screen shows
all three in stacked sections so the player has a clear view of their
short-term, week-long, and one-time goals. Quest variety is bounded --
daily + weekly + chapter + achievements, NOT 6+ quest types.

Scrolling: the stacked sections (daily + weekly + chapter + achievements
+ hidden) can grow past the 720px window, so the quest list scrolls
inside a viewport rect. The title, subtitle, and currency pills stay
fixed; only the quest content scrolls.
"""
from __future__ import annotations

import pygame
import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from ui.widgets import Button, currency_pill
from utils import format_number, clamp
from data import quests as q
from core import quests as qcore


class QuestsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button((16, cfg.WINDOW_H - 60, 120, 44), "Back",
                               on_click=lambda: self.game.set_screen("game"))
        self.buttons = [self.btn_back]
        # Scroll state: the quest list content scrolls inside the viewport.
        # Viewport top = 110 (just below the currency pills); bottom = 640
        # (above the Back button at y=660). The content height is dynamic
        # (computed in draw()), so max_scroll is derived from it.
        self.scroll = 0.0
        self.target_scroll = 0.0
        self.viewport = pygame.Rect(60, 110, 1160, 530)
        self._content_h = 530  # updated in draw()

    def _max_scroll(self) -> float:
        # The content height from the viewport top; max_scroll is the
        # amount the content overflows the viewport (530px tall).
        return max(0.0, getattr(self, "_content_h", 530) - 530)

    def handle(self, event):
        # Wire UI click sounds: pass the sound_on gate to each button so
        # the Back button plays the ui_click SFX when sound is enabled.
        state = self.game.state
        for b in self.buttons:
            b.sound_on = state.sound_on
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEWHEEL:
            self.target_scroll = clamp(
                self.target_scroll - event.y * 40, 0, self._max_scroll())

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)
        # Smooth the scroll toward the target (same easing as ScrollList).
        self.scroll += (self.target_scroll - self.scroll) * min(1.0, dt * 14)

    def draw(self, surf):
        state = self.game.state
        surf.fill(C.bg_top)
        from theme import gradient_v
        gradient_v(surf, surf.get_rect(), C.bg_top, C.bg_bottom)
        draw_text_center(surf, "Quests", (cfg.WINDOW_W // 2, 36), font_xl(bold=True), C.text)
        draw_text_center(surf, "Daily 24h · Weekly 7d · Chapter one-time",
                         (cfg.WINDOW_W // 2, 72), font_sm(), C.text_dim)
        x = 16; y = 100
        x += currency_pill(surf, x, y, "Medals", format_number(state.medals), (200, 200, 220)) + 10
        currency_pill(surf, x, y, "Amber", format_number(state.amber), (255, 180, 60))

        # Clip the quest/achievement content to the viewport and scroll it.
        # The header ("Daily Quests" at y=130) is the first content line;
        # it scrolls WITH the list (the title/subtitle/pills above do not).
        clip = surf.get_clip()
        surf.set_clip(self.viewport)
        y = 130 - int(self.scroll)

        # Daily quests.
        draw_text(surf, "Daily Quests", (60, y), font_lg(bold=True), C.text)
        y = 170 - int(self.scroll)
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

        # Weekly quests (Task 26 / cnt-quest-codex). Same shape as the
        # daily quests (``DailyQuest``), but a longer refresh (7d) and a
        # bigger reward. Displayed in a separate section so the player can
        # see their week-long goals alongside the daily ones.
        y += 8
        draw_text(surf, "Weekly Quests", (60, y), font_lg(bold=True), C.gold)
        y += 34
        for wq_state in state.weekly_quests:
            wq = next((w for w in q.WEEKLY_POOL if w.id == wq_state["id"]), None)
            if wq is None:
                continue
            r = pygame.Rect(60, y, 560, 56)
            draw_panel(surf, r, fill=C.panel, border=C.panel_border)
            draw_text(surf, wq.name, (r.x + 14, r.y + 8), font_md(bold=True), C.text)
            draw_text(surf, wq.desc, (r.x + 14, r.y + 30), font_xs(), C.text_dim)
            progress = wq_state.get("progress", 0)
            claimed = wq_state.get("claimed", False)
            bar = pygame.Rect(r.right - 180, r.y + 20, 160, 12)
            pct = min(1.0, progress / wq.target)
            draw_bar(surf, bar, pct, fill=C.gold if claimed else C.exp,
                     bg=C.mp_bg, border=C.panel_border)
            draw_text(surf, f"{int(min(progress, wq.target))}/{int(wq.target)}",
                      (r.right - 180, r.y + 36), font_xs(), C.text_dim)
            if claimed:
                draw_text(surf, "✓", (r.right - 30, r.y + 18), font_md(bold=True), C.text_good)
            y += 64

        # Chapter quests (Task 26 / cnt-quest-codex). One-time milestones
        # tied to zone progression. The state is initialized lazily on
        # the first ``update_chapter_progress`` call; here we read the
        # state (which may be empty on a brand-new save) and display
        # whatever chapter quests exist.
        y += 8
        draw_text(surf, "Chapter Quests", (60, y), font_lg(bold=True),
                  (255, 180, 60))
        y += 34
        chapter_states = state.chapter_quests
        for cq_state in chapter_states:
            cq = next((c for c in q.CHAPTER_QUESTS if c.id == cq_state["id"]), None)
            if cq is None:
                continue
            r = pygame.Rect(60, y, 560, 56)
            draw_panel(surf, r, fill=C.panel, border=C.panel_border)
            draw_text(surf, cq.name, (r.x + 14, r.y + 8), font_md(bold=True), C.text)
            draw_text(surf, cq.desc, (r.x + 14, r.y + 30), font_xs(), C.text_dim)
            progress = cq_state.get("progress", 0)
            claimed = cq_state.get("claimed", False)
            bar = pygame.Rect(r.right - 180, r.y + 20, 160, 12)
            pct = min(1.0, progress / cq.target)
            draw_bar(surf, bar, pct, fill=C.gold if claimed else C.exp,
                     bg=C.mp_bg, border=C.panel_border)
            draw_text(surf, f"{int(min(progress, cq.target))}/{int(cq.target)}",
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
        y += 10
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

        # Content height from the viewport top (110). y is the cursor after
        # the last hidden achievement, already offset by -scroll, so add
        # scroll back to get the unscrolled height. max_scroll then lets the
        # content bottom reach exactly the viewport bottom (640).
        self._content_h = y - 110 + int(self.scroll)
        # Clamp the target scroll now that we know the real content height.
        self.target_scroll = clamp(self.target_scroll, 0, self._max_scroll())
        surf.set_clip(clip)

        for b in self.buttons:
            b.draw(surf)
