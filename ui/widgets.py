"""Reusable UI widgets: buttons, panels, bars, scroll lists.

All drawn with pygame primitives.  Widgets are *immediate-ish*: they
expose a ``draw(surf)`` and an ``handle(event)``; clicks call back.
"""
from __future__ import annotations

import pygame

from theme import C, font_sm, font_md, font_lg, font_xs, draw_panel, draw_text, draw_text_center, draw_bar
from utils import clamp


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------
# Task 37 (pl-music-sfx): buttons play a UI click sound on click. The
# sound is gated on the ``sound_on`` flag the owning screen passes (the
# screen reads ``state.sound_on`` and passes it here). The click sound is
# a layered SFX (``ui_click`` -- a short tone + a small noise burst), not
# a pure sine beep. The ``sound`` parameter selects which SFX to play
# (default ``"ui_click"``; a confirm button can pass ``"ui_confirm"``).
# ``sound_on`` defaults to False so a Button constructed without a
# ``sound_on`` argument is silent (no crash if the screen forgot to pass
# it -- the sound is opt-in per screen).
class Button:
    def __init__(self, rect: pygame.Rect, label: str, *,
                 on_click=None, font=None, enabled: bool = True,
                 color=None, text_color=None, hint: str = "",
                 sound: str = "ui_click", sound_on: bool = False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.font = font or font_md(bold=True)
        self.enabled = enabled
        self.color = color or C.btn
        self.text_color = text_color or C.btn_text
        self.hint = hint
        # Task 37: the UI click sound + the sound_on gate. ``sound`` is the
        # SFX name to play on click (default ``"ui_click"``); ``sound_on``
        # is the gate (the screen passes ``state.sound_on``). A Button
        # constructed without ``sound_on`` is silent (the default is False
        # so a screen that forgets to pass it doesn't crash -- the sound is
        # opt-in).
        self.sound = sound
        self.sound_on = sound_on
        self.hover = False
        self.pressed = False
        self.hover_t = 0.0

    def handle(self, event: pygame.event.Event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.pressed and self.rect.collidepoint(event.pos):
                self.pressed = False
                # Task 37: play the UI click sound (gated on ``sound_on``).
                if self.sound and self.sound_on:
                    from assets import play
                    play(self.sound, self.sound_on)
                if self.on_click:
                    self.on_click()
                return True
            self.pressed = False
        return False

    def update(self, dt: float) -> None:
        target = 1.0 if self.hover else 0.0
        self.hover_t += (target - self.hover_t) * min(1.0, dt * 12)

    def draw(self, surf: pygame.Surface) -> None:
        rect = self.rect.copy()
        if self.pressed:
            col = C.btn_press
            rect.y += 1
        elif not self.enabled:
            col = C.btn_disabled
        else:
            col = self._lerp(self.color, C.btn_hover, self.hover_t)
        pygame.draw.rect(surf, col, rect, border_radius=6)
        border = C.panel_border_hi if self.hover and self.enabled else C.panel_border
        pygame.draw.rect(surf, border, rect, 1, border_radius=6)
        tc = self.text_color if self.enabled else C.btn_disabled_text
        draw_text_center(surf, self.label, rect.center, self.font, tc)
        if self.hint and self.hover:
            # Tiny tooltip below.
            hint_surf = self.font.render(self.hint, True, C.text_dim)
            hr = hint_surf.get_rect(midtop=(rect.centerx, rect.bottom + 4))
            bg = hr.inflate(8, 4)
            pygame.draw.rect(surf, C.panel_lo, bg, border_radius=4)
            pygame.draw.rect(surf, C.panel_border, bg, 1, border_radius=4)
            surf.blit(hint_surf, hr)

    @staticmethod
    def _lerp(a, b, t):
        t = clamp(t, 0, 1)
        return (int(a[0] + (b[0] - a[0]) * t),
                int(a[1] + (b[1] - a[1]) * t),
                int(a[2] + (b[2] - a[2]) * t))


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
class Panel:
    def __init__(self, rect: pygame.Rect, title: str = "", *, fill=C.panel, border=C.panel_border):
        self.rect = pygame.Rect(rect)
        self.title = title
        self.fill = fill
        self.border = border

    def draw(self, surf: pygame.Surface) -> None:
        draw_panel(surf, self.rect, fill=self.fill, border=self.border)
        if self.title:
            draw_text(surf, self.title, (self.rect.x + 10, self.rect.y + 6), font_md(bold=True), C.text)


# ---------------------------------------------------------------------------
# Stat bar (label + bar + value)
# ---------------------------------------------------------------------------
class StatBar:
    def __init__(self, rect: pygame.Rect, label: str, value, maximum,
                 fill=C.hp, bg=C.hp_bg, fmt=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.value = value
        self.maximum = maximum
        self.fill = fill
        self.bg = bg
        self.fmt = fmt

    def draw(self, surf: pygame.Surface) -> None:
        draw_text(surf, self.label, (self.rect.x, self.rect.y), font_sm(), C.text_dim)
        bar_rect = pygame.Rect(self.rect.x, self.rect.y + 16, self.rect.w, 12)
        pct = self.value / self.maximum if self.maximum else 0
        draw_bar(surf, bar_rect, pct, fill=self.fill, bg=self.bg, border=C.panel_border)
        val = self.fmt(self.value) if self.fmt else str(self.value)
        draw_text(surf, val, (self.rect.right - 60, self.rect.y), font_sm(), C.text)


# ---------------------------------------------------------------------------
# Scrollable list (vertical)
# ---------------------------------------------------------------------------
class ScrollList:
    # Drag-scroll: a press inside the list starts a potential drag; if the
    # mouse moves more than a few px before release it is treated as a drag
    # (scrolling the list) instead of a click-select. The click-select still
    # fires on a press that does not move. A scrollbar indicator is drawn on
    # the right edge when the list is scrollable (max_scroll > 0).
    def __init__(self, rect: pygame.Rect, items, item_h: int = 56):
        self.rect = pygame.Rect(rect)
        self.items = items            # list of dicts: {label, sub, color, icon, data}
        self.item_h = item_h
        self.scroll = 0
        self.target_scroll = 0
        self.hover_index = -1
        self.selected_index = -1
        self.on_select = None
        # Drag-scroll state. ``_dragging`` is True between a press inside the
        # rect and the matching release; ``_drag_anchor_*`` records the press
        # so MOUSEMOTION can compute the scroll delta; ``_drag_moved`` flags
        # whether the motion exceeded the click threshold so the release
        # suppresses the click-select.
        self._dragging = False
        self._drag_anchor_y = 0
        self._drag_anchor_scroll = 0
        self._drag_moved = False

    @property
    def max_scroll(self) -> int:
        return max(0, len(self.items) * self.item_h - self.rect.h)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.target_scroll -= event.y * 40
                self.target_scroll = clamp(self.target_scroll, 0, self.max_scroll)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Start a potential drag BEFORE the click-select so motion is
            # tracked. The click-select still fires here on a press; if the
            # mouse later moves beyond the threshold, MOUSEBUTTONUP treats it
            # as the end of a drag and the selection is left as-is.
            if self.rect.collidepoint(event.pos):
                self._dragging = True
                self._drag_anchor_y = event.pos[1]
                self._drag_anchor_scroll = self.target_scroll
                self._drag_moved = False
            i = self._index_at(event.pos)
            if i is not None and 0 <= i < len(self.items):
                self.selected_index = i
                if self.on_select:
                    self.on_select(i, self.items[i])
                return True
        elif event.type == pygame.MOUSEMOTION:
            self.hover_index = self._index_at(event.pos)
            if self._dragging:
                dy = event.pos[1] - self._drag_anchor_y
                if abs(dy) > 4:
                    self._drag_moved = True
                self.target_scroll = clamp(
                    self._drag_anchor_scroll - dy, 0, self.max_scroll)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging:
                # If the mouse moved beyond the threshold this was a drag,
                # not a click -- the click-select already fired on DOWN for a
                # non-drag, so on a drag suppress the selection by returning
                # False (the selection set on DOWN stands only if it wasn't a
                # drag; for a drag we leave the selection as it was).
                was_drag = self._drag_moved
                self._dragging = False
                if was_drag:
                    return False
        return False

    def _index_at(self, pos) -> int | None:
        if not self.rect.collidepoint(pos):
            return None
        y = pos[1] - self.rect.y + self.scroll
        i = y // self.item_h
        if 0 <= i < len(self.items):
            return int(i)
        return None

    def update(self, dt: float) -> None:
        self.scroll += (self.target_scroll - self.scroll) * min(1.0, dt * 14)

    def _draw_scrollbar(self, surf: pygame.Surface) -> None:
        """Draw a track + thumb on the right edge when the list scrolls."""
        if self.max_scroll <= 0:
            return
        track_x = self.rect.right - 8
        track_w = 6
        thumb_h = max(30, int(self.rect.h * self.rect.h / max(1, len(self.items) * self.item_h)))
        thumb_y = self.rect.y + int((self.rect.h - thumb_h) * (self.scroll / max(1, self.max_scroll)))
        # Track.
        track_rect = pygame.Rect(track_x, self.rect.y, track_w, self.rect.h)
        pygame.draw.rect(surf, C.panel_lo, track_rect)
        pygame.draw.rect(surf, C.panel_border, track_rect, 1)
        # Thumb.
        thumb_rect = pygame.Rect(track_x, thumb_y, track_w, thumb_h)
        pygame.draw.rect(surf, C.panel_border_hi, thumb_rect)

    def draw(self, surf: pygame.Surface) -> None:
        clip = surf.get_clip()
        surf.set_clip(self.rect)
        draw_panel(surf, self.rect, fill=C.panel_lo, border=C.panel_border)
        y0 = self.rect.y - int(self.scroll)
        for i, item in enumerate(self.items):
            r = pygame.Rect(self.rect.x, y0 + i * self.item_h, self.rect.w, self.item_h)
            if r.bottom < self.rect.y or r.top > self.rect.bottom:
                continue
            if i == self.selected_index:
                pygame.draw.rect(surf, C.panel_hi, r)
            elif i == self.hover_index:
                pygame.draw.rect(surf, (38, 44, 70), r)
            # Icon (color square)
            color = item.get("color", C.text)
            pygame.draw.rect(surf, color, (r.x + 8, r.y + 12, 8, r.h - 24), border_radius=2)
            # Label + sub
            draw_text(surf, item.get("label", ""), (r.x + 24, r.y + 8), font_sm(bold=True), C.text)
            sub = item.get("sub", "")
            if sub:
                draw_text(surf, sub, (r.x + 24, r.y + 28), font_xs(), C.text_dim)
        surf.set_clip(clip)
        # Scrollbar drawn AFTER restoring the clip so it stays visible.
        self._draw_scrollbar(surf)


# ---------------------------------------------------------------------------
# Currency pill (icon + value)
# ---------------------------------------------------------------------------
def currency_pill(surf: pygame.Surface, x: int, y: int, label: str, value,
                  color: tuple, font=None) -> int:
    """Draw a small currency indicator; returns the width used."""
    font = font or font_md(bold=True)
    text = f"{label} {value}"
    img = font.render(text, True, C.text)
    w = img.get_width() + 28
    r = pygame.Rect(x, y, w, 28)
    pygame.draw.rect(surf, C.panel_lo, r, border_radius=14)
    pygame.draw.circle(surf, color, (x + 14, y + 14), 8)
    pygame.draw.rect(surf, C.panel_border, r, 1, border_radius=14)
    surf.blit(img, (x + 26, y + 5))
    return w


# ---------------------------------------------------------------------------
# Toast / notification (transient text)
# ---------------------------------------------------------------------------
class Toast:
    def __init__(self, text: str, life: float = 3.0, color=C.text):
        self.text = text
        self.life = life
        self.max_life = life
        self.color = color

    def update(self, dt: float) -> None:
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0

    def draw(self, surf: pygame.Surface, x: int, y: int) -> int:
        a = clamp(self.life / self.max_life, 0, 1)
        alpha = int(255 * a) if a > 0.7 else int(255 * (a / 0.7))
        font = font_md(bold=True)
        img = font.render(self.text, True, self.color)
        img.set_alpha(alpha)
        r = img.get_rect(midtop=(x, y))
        bg = r.inflate(16, 8)
        bg_surf = pygame.Surface(bg.size, pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, (*C.panel_lo, alpha), bg_surf.get_rect(), border_radius=6)
        pygame.draw.rect(bg_surf, (*C.panel_border, alpha), bg_surf.get_rect(), 1, border_radius=6)
        surf.blit(bg_surf, bg.topleft)
        surf.blit(img, r)
        return r.h
