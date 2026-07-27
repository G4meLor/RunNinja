"""Unified hover-tooltip manager for the Tap Ninja UI.

Any screen that wants a hover tooltip constructs a ``TooltipManager`` once,
then each frame:

1. calls ``clear()`` (hover regions are recomputed per-frame because the
   layout may change — buttons move, list items scroll, currencies update),
2. calls ``register(region_id, rect, text)`` for every interactive region
   it wants a tooltip on (currencies, stat bars, buttons, list items,
   skill-tree nodes, ...),
3. calls ``update(mouse_pos)`` so the manager can find which region the
   cursor is over (and apply a small hover-in delay so quick flicks do not
   flash the tooltip),
4. calls ``draw(surf)`` last, after its own content, so the tooltip renders
   on top of everything else.

Rendering uses pygame primitives only, reuses cached fonts from
``theme``, wraps long lines, and clamps the card to the screen so it never
runs off the edge.  No per-frame allocations on the hot path once warm:
the card surface is grown lazily to the largest size seen and then reused.
"""
from __future__ import annotations

import pygame

from theme import (
    C, font_xs, font_sm, font_md,
    draw_panel, draw_text,
)
import config as cfg


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_HOVER_DELAY = 0.18      # seconds the cursor must rest before the tooltip appears
_FADE_SPEED = 12.0       # alpha easing speed
_PAD_X = 10              # inner horizontal padding
_PAD_Y = 8               # inner vertical padding
_LINE_GAP = 2            # pixels between wrapped lines
_MAX_WIDTH = 280         # max card width before wrapping kicks in
_OFFSET = (16, 16)      # cursor offset so the card does not cover the pointer
_MARGIN = 8              # keep this many pixels from the screen edge


# ---------------------------------------------------------------------------
# Region record
# ---------------------------------------------------------------------------
class _Region:
    """A registered hover region.

    ``text`` may be a plain string or a callable that returns the current
    text — the callable form lets screens show live values (e.g. "Gold:
    1.2k — dropped by monsters") without re-registering every frame.
    """
    __slots__ = ("id", "rect", "text")

    def __init__(self, region_id: str, rect: pygame.Rect, text) -> None:
        self.id = region_id
        self.rect = pygame.Rect(rect)
        self.text = text


# ---------------------------------------------------------------------------
# TooltipManager
# ---------------------------------------------------------------------------
class TooltipManager:
    """Reusable, screen-agnostic hover-tooltip manager.

    A screen owns one instance and drives it per-frame (see module docstring).
    The manager is self-contained: it caches fonts (via ``theme``), wraps
    long text, eases the card in/out, and clamps the card to the window.
    """

    def __init__(self) -> None:
        self._regions: dict[str, _Region] = {}
        # Order of insertion — used so the latest registration wins ties and
        # so iteration is deterministic.
        self._order: list[str] = []
        self._hover_id: str | None = None
        self._hover_t: float = 0.0          # 0..1 eased visibility
        self._rest_t: float = 0.0           # seconds the cursor has rested on the current region
        # Reusable scratch surface for the card (grown lazily).
        self._card_surf: pygame.Surface | None = None
        self._card_size: tuple[int, int] = (0, 0)
        # Cached wrapped text for the current hover id — avoids re-wrapping
        # every frame while the cursor stays on the same region.
        self._cached_id: str | None = None
        self._cached_text: str | None = None
        self._cached_lines: list[str] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, region_id: str, rect, text) -> None:
        """Register (or re-register) a hover region.

        ``rect`` is anything ``pygame.Rect(...)`` accepts (a Rect, a 4-tuple,
        or a 4-list).  ``text`` is either a string or a zero-arg callable
        returning the current tooltip text; the callable is evaluated lazily
        in ``update`` only when the region is actually hovered, so it is
        cheap to register many live regions.
        """
        r = pygame.Rect(rect)
        existing = self._regions.get(region_id)
        if existing is None:
            self._order.append(region_id)
        self._regions[region_id] = _Region(region_id, r, text)

    def clear(self) -> None:
        """Drop all registered regions.

        Call this at the top of each frame before re-registering the current
        layout.  Hover regions are recomputed per-frame because the layout
        may change (buttons move, list items scroll, currencies update).
        """
        self._regions.clear()
        self._order.clear()
        # If the previously-hovered region is gone next frame, the rest
        # timer resets naturally via _hover_id mismatch in update().

    # ------------------------------------------------------------------
    # Per-frame logic
    # ------------------------------------------------------------------
    def update(self, mouse_pos, dt: float = 0.0) -> None:
        """Find the hovered region and ease the tooltip visibility.

        Pass the current mouse position and the frame dt.  A small hover-in
        delay (``_HOVER_DELAY``) keeps the tooltip from flashing on quick
        flicks across regions.
        """
        mx, my = mouse_pos
        new_id: str | None = None
        # Iterate in reverse insertion order so the latest registration wins
        # ties (later draws are conceptually "on top").
        for region_id in reversed(self._order):
            r = self._regions[region_id]
            if r.rect.collidepoint(mx, my):
                new_id = region_id
                break

        if new_id != self._hover_id:
            self._hover_id = new_id
            self._rest_t = 0.0
            # Invalidate the wrapped-text cache on a region change.
            self._cached_id = None

        if new_id is not None:
            self._rest_t += dt
            if self._rest_t >= _HOVER_DELAY:
                target = 1.0
            else:
                target = 0.0
        else:
            target = 0.0

        # Ease the visibility toward the target.
        self._hover_t += (target - self._hover_t) * min(1.0, max(0.0, dt) * _FADE_SPEED)
        if self._hover_t < 0.01 and target == 0.0:
            self._hover_t = 0.0

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        """Render the tooltip card near the cursor, clamped to the screen.

        Call this *after* the screen has drawn its own content so the
        tooltip sits on top.  No-op if nothing is hovered or the eased
        visibility is ~0.
        """
        if self._hover_id is None or self._hover_t < 0.01:
            return
        region = self._regions.get(self._hover_id)
        if region is None:
            return
        text = region.text
        if callable(text):
            try:
                text = text()
            except Exception:
                return
        if not text:
            return

        # Resolve the (possibly cached) wrapped lines for this region+text.
        if self._cached_id != self._hover_id or self._cached_text != text:
            lines = self._wrap(text, _MAX_WIDTH - _PAD_X * 2)
            self._cached_id = self._hover_id
            self._cached_text = text
            self._cached_lines = lines
        else:
            lines = self._cached_lines
        if not lines:
            return

        # Measure the card.
        font = font_sm()
        title_font = font_sm(bold=True)
        # First line is the title (bold), the rest are body (regular).
        title_h = title_font.get_linesize()
        body_h = font.get_linesize()
        inner_w = max(
            title_font.size(lines[0])[0],
            max((font.size(ln)[0] for ln in lines[1:]), default=0),
        )
        card_w = inner_w + _PAD_X * 2
        card_h = _PAD_Y * 2 + title_h + (len(lines) - 1) * (body_h + _LINE_GAP)

        # Position: offset from the cursor, clamped to the window.
        mx, my = pygame.mouse.get_pos()
        tx = mx + _OFFSET[0]
        ty = my + _OFFSET[1]
        if tx + card_w > cfg.WINDOW_W - _MARGIN:
            tx = cfg.WINDOW_W - _MARGIN - card_w
        if ty + card_h > cfg.WINDOW_H - _MARGIN:
            # Flip above the cursor if there is room; otherwise clamp to the top.
            above = my - _OFFSET[1] - card_h
            if above >= _MARGIN:
                ty = above
            else:
                ty = cfg.WINDOW_H - _MARGIN - card_h
        if tx < _MARGIN:
            tx = _MARGIN
        if ty < _MARGIN:
            ty = _MARGIN

        card_rect = pygame.Rect(int(tx), int(ty), int(card_w), int(card_h))

        # Ease alpha (rounded) for a soft fade-in/out.
        alpha = int(255 * max(0.0, min(1.0, self._hover_t)))

        # Reuse a scratch surface sized for the card (grow lazily, never shrink
        # so we don't reallocate on every jitter in card height).
        if (self._card_surf is None
                or self._card_size[0] < card_w
                or self._card_size[1] < card_h):
            new_w = max(card_w, self._card_size[0])
            new_h = max(card_h, self._card_size[1])
            self._card_surf = pygame.Surface((new_w, new_h), pygame.SRCALPHA)
            self._card_size = (new_w, new_h)
        cs = self._card_surf
        # Clear only the slice we will use.
        cs.fill((0, 0, 0, 0), pygame.Rect(0, 0, int(card_w), int(card_h)))

        local_rect = pygame.Rect(0, 0, int(card_w), int(card_h))
        draw_panel(cs, local_rect,
                  fill=C.panel, border=C.panel_border_hi, border_w=1, radius=6)

        # Title (first line, bold).
        draw_text(cs, lines[0], (local_rect.x + _PAD_X, local_rect.y + _PAD_Y),
                  title_font, C.text)
        # Body lines.
        y = local_rect.y + _PAD_Y + title_h + _LINE_GAP
        for ln in lines[1:]:
            draw_text(cs, ln, (local_rect.x + _PAD_X, y), font, C.text_dim)
            y += body_h + _LINE_GAP

        # Apply alpha to the slice and blit.
        if alpha < 255:
            # set_alpha on a per-surface basis works for SRCALPHA surfaces.
            cs.set_alpha(alpha)
        surf.blit(cs, card_rect.topleft, pygame.Rect(0, 0, int(card_w), int(card_h)))
        if alpha < 255:
            cs.set_alpha(255)

    # ------------------------------------------------------------------
    # Text wrapping
    # ------------------------------------------------------------------
    @staticmethod
    def _wrap(text: str, max_width: int) -> list[str]:
        """Split ``text`` into wrapped lines that fit ``max_width`` px.

        Newlines in the input are honored (each starts a new line, then is
        wrapped if still too long).  Wrapping is word-based with a
        greedy fill; very long words are hard-broken by character so a
        single long token (e.g. a giant number) cannot overflow the card.
        """
        if not text:
            return []
        font = font_sm()
        out: list[str] = []
        for para in text.split("\n"):
            if not para:
                out.append("")
                continue
            words = para.split(" ")
            cur = ""
            for w in words:
                if not cur:
                    trial = w
                else:
                    trial = cur + " " + w
                if font.size(trial)[0] <= max_width:
                    cur = trial
                    continue
                # `trial` too wide.
                if cur:
                    out.append(cur)
                    cur = ""
                # Try the word alone; if it still overflows, hard-break it.
                if font.size(w)[0] <= max_width:
                    cur = w
                else:
                    # Character-level break.
                    chunk = ""
                    for ch in w:
                        if font.size(chunk + ch)[0] <= max_width:
                            chunk += ch
                        else:
                            if chunk:
                                out.append(chunk)
                            chunk = ch
                    cur = chunk
            if cur:
                out.append(cur)
        return out

    # ------------------------------------------------------------------
    # Introspection (handy for tests / debugging)
    # ------------------------------------------------------------------
    @property
    def hover_id(self) -> str | None:
        return self._hover_id

    @property
    def visible(self) -> bool:
        return self._hover_id is not None and self._hover_t > 0.01

    def __len__(self) -> int:
        return len(self._regions)
