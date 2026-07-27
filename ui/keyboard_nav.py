"""Keyboard navigation system for Tap Ninja.

Lets the player drive every screen without a mouse:

  * **Tab / Shift-Tab** cycles focus forward / backward through the
    buttons (and any scroll lists) registered for the current screen.
  * **Enter / Space** activates the focused button (calls its
    ``on_click``) or, if a scroll list is focused, confirms the current
    list selection.
  * **Arrow keys** move the focused scroll list's selection up / down
    and scroll to keep it visible.
  * A **pulsing focus ring** is drawn around the focused widget so the
    player always sees where keyboard input will land.

The system is a process-singleton (``keyboard_nav``).  ``main.py`` calls
``set_active(current_screen)`` whenever the screen changes, re-binds the
active screen's button list each frame (cheap -- one reference store),
and calls ``handle`` / ``update`` / ``draw_focus_ring`` in the event /
update / draw loops.  See ``docs/specs/keyboard_nav.md`` for the full
integration sketch.

Design notes
------------
* **pygame primitives only** -- the focus ring is ``pygame.draw.rect``
  on the screen surface; no per-frame ``Surface`` allocation.
* **no per-frame allocations** -- the pulse is a ``sin`` of an
  accumulating time; the ring color is an int lerp between two palette
  colors; the ring rect is a ``pygame.Rect.inflate`` (a small, cheap,
  stack-local object, same as every other draw in the codebase).
* **per-screen focus index** -- each screen remembers its focus
  position so switching away and back preserves the player's place.
* **duck-typed widgets** -- any object with a ``rect`` plus
  ``on_click`` / ``enabled`` is treated as a button; any object with
  ``rect`` / ``items`` / ``selected_index`` / ``on_select`` /
  ``item_h`` / ``target_scroll`` (i.e. ``ui.widgets.ScrollList``) is
  treated as a focusable list.
"""
from __future__ import annotations

import math
import pygame

from theme import C


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_PULSE_SPEED = 3.0          # rad/s -- focus ring pulse frequency (~2s period)
_RING_INFLATE = 4           # px the inner ring sits outside the widget
_RING_RADIUS = 8            # corner radius (close to the button's 6 / panel's 8)
_PRESS_FLASH = 0.12         # s -- brief pressed-state flash on activation

# Focus ring colors: lerp between a calm border and a bright accent so the
# ring breathes instead of blinking.
_RING_LO = C.panel_border_hi
_RING_HI = C.gold


# ---------------------------------------------------------------------------
# KeyboardNav
# ---------------------------------------------------------------------------
class KeyboardNav:
    """Process-wide keyboard focus manager.

    ``bind(screen_name, buttons, *, lists=None)`` registers the
    focusable widgets for a screen.  ``set_active(screen_name)`` tells the
    manager which screen's bindings are current.  ``handle(event)`` /
    ``update(dt)`` / ``draw_focus_ring(surf)`` are called from
    ``main.py``'s event / update / draw loops.
    """

    def __init__(self) -> None:
        # screen_name -> list of focusable widgets (buttons then lists,
        # in registration order).
        self._bindings: dict[str, list] = {}
        # screen_name -> focus index into that screen's widget list.
        self._focus: dict[str, int] = {}
        self._active: str = ""
        # Pulse accumulator (seconds).
        self._t: float = 0.0
        # Brief pressed-flash state for the last-activated button.
        self._pressed_btn = None
        self._press_t: float = 0.0
        # Accessibility: when True the ring is steady (no pulse) and the
        # pressed flash is skipped.  main.py sets this from
        # ``state.reduced_motion``.
        self.reduced_motion: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def bind(self, screen_name: str, buttons, *, lists=None) -> None:
        """Register the focusable widgets for a screen.

        ``buttons`` is a list of ``Button`` (or any objects with a
        ``rect`` attribute plus an ``on_click`` / ``enabled`` pair).
        ``lists`` is an optional list of scroll-list-like widgets
        (``ui.widgets.ScrollList``); they are appended after the buttons
        in Tab order.  Re-binding the same screen **preserves** the
        focus index (clamped to the new length) so dynamic button lists
        -- e.g. the buildings screen's ``buy_buttons`` rebuilt on a
        purchase -- do not reset focus.
        """
        widgets = list(buttons) if buttons else []
        if lists:
            widgets.extend(list(lists))
        self._bindings[screen_name] = widgets
        # Preserve / clamp the per-screen focus index.
        if screen_name not in self._focus:
            self._focus[screen_name] = 0
        n = len(widgets)
        if n == 0:
            self._focus[screen_name] = 0
        else:
            idx = self._focus[screen_name]
            if idx < 0 or idx >= n:
                self._focus[screen_name] = 0

    def set_active(self, screen_name: str) -> None:
        """Set the current screen.  Called from ``main.py.set_screen``."""
        self._active = screen_name
        # If the screen has no binding yet, focus is a no-op until
        # ``bind`` is called -- everything degrades gracefully.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @property
    def _widgets(self) -> list:
        return self._bindings.get(self._active, [])

    @property
    def _index(self) -> int:
        return self._focus.get(self._active, 0)

    def _set_index(self, i: int) -> None:
        n = len(self._widgets)
        if n == 0:
            self._focus[self._active] = 0
            return
        self._focus[self._active] = i % n

    def _focused(self):
        ws = self._widgets
        i = self._index
        if 0 <= i < len(ws):
            return ws[i]
        return None

    @staticmethod
    def _is_list(widget) -> bool:
        """A list-like widget has ``items`` and ``selected_index``."""
        return (widget is not None
                and hasattr(widget, "items")
                and hasattr(widget, "selected_index"))

    @staticmethod
    def _is_button(widget) -> bool:
        return (widget is not None
                and hasattr(widget, "on_click")
                and hasattr(widget, "enabled")
                and hasattr(widget, "rect"))

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle(self, event: pygame.event.Event) -> bool:
        """Process a keyboard event.  Returns True if consumed.

        Call from ``main.py``'s event loop (inside the ``KEYDOWN``
        branch, before the screen's own ``handle``).  Non-keyboard events
        are ignored; the manager only acts on Tab / Enter / Space /
        arrows, so it never fights the 1-9 / ESC / P / F1 shortcuts.
        """
        if event.type != pygame.KEYDOWN:
            return False
        if not self._widgets:
            return False
        key = event.key
        shift = bool(event.mod & pygame.KMOD_SHIFT)

        # --- Tab / Shift-Tab: cycle focus ---
        if key == pygame.K_TAB:
            self._cycle(1 if not shift else -1)
            return True
        # --- Enter / Space: activate the focused widget ---
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            return self._activate()
        # --- Arrow keys: navigate the focused list ---
        if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            return self._arrow(key)
        return False

    def _cycle(self, direction: int) -> None:
        """Move focus by ``direction`` (+1 / -1), skipping disabled buttons.

        The first Tab press on a fresh screen lands on the first enabled
        widget (so focus is never stuck on an off-screen starting index);
        subsequent presses advance by one step each, wrapping around.
        """
        n = len(self._widgets)
        if n == 0:
            return
        i = self._index
        for _ in range(n):
            i = (i + direction) % n
            w = self._widgets[i]
            # Stop on the first non-button or enabled button we hit.
            if not self._is_button(w) or getattr(w, "enabled", True):
                break
        self._set_index(i)

    def _activate(self) -> bool:
        """Enter / Space: fire the focused button or confirm the list selection."""
        w = self._focused()
        if w is None:
            return False
        if self._is_button(w):
            # Swallow the key even when disabled so it doesn't fall
            # through to other handlers -- just don't fire the callback.
            if not getattr(w, "enabled", True):
                return True
            if w.on_click is not None:
                w.on_click()
            # Brief pressed flash for tactile feedback (skipped under
            # reduced motion).
            if not self.reduced_motion:
                self._pressed_btn = w
                self._press_t = _PRESS_FLASH
            return True
        if self._is_list(w):
            i = w.selected_index
            if 0 <= i < len(w.items) and w.on_select is not None:
                w.on_select(i, w.items[i])
            return True
        return False

    def _arrow(self, key) -> bool:
        """Arrow keys move the focused list's selection; no-op on a button."""
        w = self._focused()
        if not self._is_list(w):
            return False
        items = getattr(w, "items", [])
        if not items:
            return False
        n = len(items)
        i = w.selected_index
        if i < 0:
            # Nothing selected yet -- first arrow lands on item 0 without
            # advancing past it.
            i = 0
        elif key in (pygame.K_UP, pygame.K_LEFT):
            i = i - 1 if i > 0 else 0
        else:  # DOWN / RIGHT
            i = i + 1 if i < n - 1 else n - 1
        w.selected_index = i
        if w.on_select is not None:
            w.on_select(i, w.items[i])
        self._scroll_to(w, i)
        return True

    @staticmethod
    def _scroll_to(w, i: int) -> None:
        """Adjust the list's ``target_scroll`` so item ``i`` stays visible."""
        rect = w.rect
        item_h = getattr(w, "item_h", 48)
        max_scroll = getattr(w, "max_scroll", 0)
        item_top = i * item_h
        item_bot = item_top + item_h
        cur = w.target_scroll
        if item_top < cur:
            w.target_scroll = item_top
        elif item_bot > cur + rect.h:
            w.target_scroll = max(0, item_bot - rect.h)
        w.target_scroll = max(0, min(w.target_scroll, max_scroll))

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        # Advance the pulse accumulator.
        self._t += dt
        # Drive the brief pressed flash: hold the button's ``pressed``
        # flag True for _PRESS_FLASH seconds, then release it.
        if self._press_t > 0:
            self._press_t -= dt
            if self._press_t <= 0:
                self._press_t = 0.0
                if self._pressed_btn is not None:
                    self._pressed_btn.pressed = False
                self._pressed_btn = None
        if self._pressed_btn is not None:
            self._pressed_btn.pressed = True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw_focus_ring(self, surf: pygame.Surface) -> None:
        """Draw a pulsing ring around the focused widget.

        Call from ``main.py`` *after* the screen's ``draw`` so the ring
        sits on top of everything.  No-op if no widget is focused.
        """
        w = self._focused()
        if w is None:
            return
        rect = getattr(w, "rect", None)
        if rect is None:
            return
        # Pulse factor in [0, 1]; frozen at full brightness under
        # reduced motion.
        if self.reduced_motion:
            pulse = 1.0
        else:
            pulse = 0.5 + 0.5 * math.sin(self._t * _PULSE_SPEED)
        # Lerp the ring color between the calm and bright accents.
        col = (
            int(_RING_LO[0] + (_RING_HI[0] - _RING_LO[0]) * pulse),
            int(_RING_LO[1] + (_RING_HI[1] - _RING_LO[1]) * pulse),
            int(_RING_LO[2] + (_RING_HI[2] - _RING_LO[2]) * pulse),
        )
        # Outer faint glow ring -- lerped toward the bg so it reads as a
        # halo without needing alpha.
        glow = rect.inflate(_RING_INFLATE * 2 + 2, _RING_INFLATE * 2 + 2)
        glow_col = (
            int(col[0] * 0.4 + C.bg_top[0] * 0.6),
            int(col[1] * 0.4 + C.bg_top[1] * 0.6),
            int(col[2] * 0.4 + C.bg_top[2] * 0.6),
        )
        pygame.draw.rect(surf, glow_col, glow, 1, border_radius=_RING_RADIUS + 2)
        # Inner bright ring -- pulsing thickness (2..4 px).
        ring = rect.inflate(_RING_INFLATE, _RING_INFLATE)
        thickness = 2 + int(pulse * 2)
        pygame.draw.rect(surf, col, ring, thickness, border_radius=_RING_RADIUS)


# ---------------------------------------------------------------------------
# Process singleton + global hook
# ---------------------------------------------------------------------------
keyboard_nav = KeyboardNav()


def set_active(screen_name: str) -> None:
    """Global hook: set the active screen on the singleton manager.

    ``main.py.set_screen`` calls this so the nav tracks the current
    screen without holding a reference to the ``Game``.
    """
    keyboard_nav.set_active(screen_name)
