"""Skill-tree unlock juice — pulse, expanding ring, glowing prereq lines,
and a floating "+effect" text on unlock; plus a path-highlight when the
player hovers a locked-but-unlockable node.

All rendering uses pygame primitives.  No per-frame allocations happen in
the hot path: the fx system keeps a fixed pool of ``_Pulse`` slots, a
fixed pool of ``_FloatText`` slots, and a fixed pool of ``_LineGlow``
slots.  The path-highlight returns a caller-owned (system-owned, reused)
list of (rect, alpha) tuples.

Integration points (see docs/specs/skilltree_fx.md):
  * ``SkillTreeScreen.handle`` calls ``fx.on_unlock(...)`` right after a
    successful ``skill_unlock.unlock(...)``.
  * ``SkillTreeScreen.draw`` calls ``fx.highlight_path(...)`` to fetch the
    glowing-path list, draws those rects, then calls ``fx.draw(surf)``.
  * ``SkillTreeScreen.update`` calls ``fx.update(dt)``.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from data import skill_tree as st
from theme import font_sm
from utils import ease_out_cubic

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_PULSE_DUR = 0.45          # seconds the node pulses after unlock
_RING_DUR = 0.55           # seconds the ring expands/fades
_RING_MAX_R = 70           # peak ring radius (px)
_LINE_GLOW_DUR = 0.40     # seconds prereq edges glow after unlock
_FLOAT_DUR = 0.90         # seconds the "+effect" text floats up
_FLOAT_RISE = 38           # pixels the text rises over its lifetime

# Pool sizes — generous enough for rapid re-unlocks without growth.
_MAX_PULSES = 8
_MAX_FLOATS = 8
_MAX_LINE_GLOWS = 24       # one per prereq edge that lights up


# ---------------------------------------------------------------------------
# Internal effect records (stored once, mutated in place)
# ---------------------------------------------------------------------------
class _Pulse:
    __slots__ = ("node_id", "rect", "color", "t", "active")

    def __init__(self) -> None:
        self.node_id: str = ""
        self.rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.t: float = 0.0
        self.active: bool = False


class _FloatText:
    __slots__ = ("text", "x", "y0", "y", "color", "t", "active")

    def __init__(self) -> None:
        self.text: str = ""
        self.x: int = 0
        self.y0: int = 0
        self.y: int = 0
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.t: float = 0.0
        self.active: bool = False


class _LineGlow:
    __slots__ = ("node_id", "t", "active")

    def __init__(self) -> None:
        self.node_id: str = ""
        self.t: float = 0.0
        self.active: bool = False


# ---------------------------------------------------------------------------
# The system
# ---------------------------------------------------------------------------
class SkillTreeFxSystem:
    """Owns the active unlock effects and the path-highlight state.

    Construct one per ``SkillTreeScreen`` (or share one on the game
    object).  All state lives on the instance, so the hot path performs
    zero allocations once the pools are warm.
    """

    def __init__(self) -> None:
        # Fixed pools — recycled, never grown.
        self._pulses: List[_Pulse] = [_Pulse() for _ in range(_MAX_PULSES)]
        self._floats: List[_FloatText] = [_FloatText() for _ in range(_MAX_FLOATS)]
        self._line_glows: List[_LineGlow] = [_LineGlow() for _ in range(_MAX_LINE_GLOWS)]
        # Per-node pulse progress, so callers can ask "is this node pulsing?".
        self._pulse_t: Dict[str, float] = {}
        # Reusable scratch list returned to callers — never re-allocated.
        self._path_buf: List[Tuple[pygame.Rect, int]] = []
        # Reusable scratch surface for the expanding ring (sized up lazily,
        # then reused — never re-allocated per frame after warm-up).
        self._ring_surf: pygame.Surface | None = None
        self._ring_surf_size: int = 0
        # Reusable scratch surface for the node-frame pulse outline.
        self._frame_surf: pygame.Surface | None = None
        self._frame_surf_size: Tuple[int, int] = (0, 0)
        # Reusable scratch surface for the floating text fade.
        self._text_surf: pygame.Surface | None = None

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------
    def on_unlock(self, node_id: str, rect: pygame.Rect,
                  branch_color: Tuple[int, int, int],
                  effect_text: str | None = None) -> None:
        """Fire the unlock juice for ``node_id``.

        ``rect`` is the node's screen rect (used for the pulse + ring
        origin).  ``branch_color`` is the node's branch color (see
        ``skill_tree.branch_color``).  ``effect_text`` is the short label
        shown rising from the node — pass the node's ``desc`` or a
        pre-formatted "+X% effect" string; if omitted we synthesize one
        from the node definition.
        """
        # Pick a free pulse slot (oldest active one if none free).
        slot = self._next_free(self._pulses)
        slot.node_id = node_id
        slot.rect = rect
        slot.color = branch_color
        slot.t = 0.0
        slot.active = True
        self._pulse_t[node_id] = 0.0

        # Light up the prereq chain edges: the node's own incoming edge +
        # every ancestor edge up to the root.  Each edge is identified by
        # its *child* node id (the node whose `prereq` the edge comes
        # from), because that is how the screen draws edges — it iterates
        # nodes and draws the line from `node.prereq` to `node`.
        # Light up the prereq chain edges: the node's own incoming edge +
        # every ancestor edge up to the root.  Each edge is identified by
        # its *child* node id (the node whose `prereq` the edge comes
        # from), because that is how the screen draws edges — it iterates
        # nodes and draws the line from `node.prereq` to `node`.
        chain = self._prereq_chain(node_id)
        glow_nodes = [nid for nid in chain + [node_id]
                      if st.BY_ID.get(nid) is not None
                      and st.BY_ID[nid].prereq is not None]
        for nid in glow_nodes:
            gslot = self._next_free(self._line_glows)
            gslot.node_id = nid
            gslot.t = 0.0
            gslot.active = True

        # Floating "+effect" text.
        text = effect_text
        if text is None:
            text = self._format_effect_text(node_id)
        fslot = self._next_free(self._floats)
        fslot.text = text
        fslot.x = rect.centerx
        fslot.y0 = rect.top + 4
        fslot.y = fslot.y0
        fslot.color = branch_color
        fslot.t = 0.0
        fslot.active = True

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for p in self._pulses:
            if not p.active:
                continue
            p.t += dt
            if p.t >= _PULSE_DUR:
                p.active = False
                self._pulse_t.pop(p.node_id, None)
            else:
                self._pulse_t[p.node_id] = p.t

        for g in self._line_glows:
            if g.active:
                g.t += dt
                if g.t >= _LINE_GLOW_DUR:
                    g.active = False

        for f in self._floats:
            if not f.active:
                continue
            f.t += dt
            if f.t >= _FLOAT_DUR:
                f.active = False
            else:
                # Ease the rise so it floats up and slows.
                eased = ease_out_cubic(f.t / _FLOAT_DUR)
                f.y = int(f.y0 - _FLOAT_RISE * eased)

    # ------------------------------------------------------------------
    # Draw all active effects onto ``surf``.
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        # Prerequisite line glows are drawn by the screen itself (it owns
        # the rects and the edge geometry); here we only draw the pulse
        # rings, node-frame pulses, and floating text.
        for p in self._pulses:
            if p.active:
                self._draw_pulse(surf, p)
        for f in self._floats:
            if f.active:
                self._draw_float(surf, f)

    # ------------------------------------------------------------------
    # Path highlight: a glowing path from root to ``node_id``.
    # ------------------------------------------------------------------
    def highlight_path(self, node_id: str,
                       node_rects: Dict[str, pygame.Rect],
                       unlocked: set[str]
                       ) -> List[Tuple[pygame.Rect, int]]:
        """Return a list of ``(rect, alpha)`` for the glowing path from the
        root of ``node_id``'s branch down to (and including) ``node_id``.

        The screen draws each returned rect with the given alpha (the
        alpha encodes a sin-based pulse so the path appears to flow).
        Only nodes that are *locked but unlockable* should trigger this —
        the caller decides that; we just trace the chain.

        The returned list is owned by this system and reused across calls,
        so the caller must not retain it (read it immediately).
        """
        buf = self._path_buf
        buf.clear()
        chain = self._prereq_chain(node_id)
        chain.append(node_id)
        # Pulse the alpha with a slow sin so the path shimmers.
        t = pygame.time.get_ticks() * 0.001
        for nid in chain:
            r = node_rects.get(nid)
            if r is None:
                continue
            # Flow: a single sin wave; nodes earlier in the chain pulse
            # earlier because their rect order matches the chain order.
            phase = (t * 2.0) % 6.2831853
            a = int(120 + 90 * math.sin(phase))
            buf.append((r, a))
        return buf

    # ------------------------------------------------------------------
    # Helpers used by the screen to draw the glowing edges + node frames.
    # ------------------------------------------------------------------
    def line_glow_alpha(self, node_id: str) -> int:
        """Alpha (0..255) for the incoming edge of ``node_id`` while it is
        glowing after an unlock.  Returns 0 when no glow is active.

        The screen calls this when drawing the prereq line for ``node_id``
        and blends the result onto the branch color.
        """
        for g in self._line_glows:
            if g.active and g.node_id == node_id:
                p = g.t / _LINE_GLOW_DUR
                # Fade out.
                return int(220 * (1.0 - p))
        return 0

    def node_pulse_scale(self, node_id: str) -> float:
        """Scale factor (1.0 = no pulse) for the node frame while it is
        pulsing.  The screen can inflate the node rect by this factor."""
        t = self._pulse_t.get(node_id)
        if t is None:
            return 1.0
        # A quick bump: peak at ~1.18 mid-way, back to 1.0 at the end.
        p = t / _PULSE_DUR
        return 1.0 + 0.18 * math.sin(p * math.pi)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _prereq_chain(self, node_id: str) -> List[str]:
        """Return the list of ancestor node ids (root-first, excluding
        ``node_id`` itself) following ``SkillNode.prereq`` links."""
        chain: List[str] = []
        seen: set[str] = set()
        n = st.BY_ID.get(node_id)
        while n is not None and n.prereq and n.prereq not in seen:
            chain.append(n.prereq)
            seen.add(n.prereq)
            n = st.BY_ID.get(n.prereq)
        chain.reverse()
        return chain

    @staticmethod
    def _next_free(pool: List) -> object:
        for slot in pool:
            if not slot.active:
                return slot
        # Pool exhausted — recycle the oldest (first) slot.
        return pool[0]

    @staticmethod
    def _format_effect_text(node_id: str) -> str:
        n = st.BY_ID.get(node_id)
        if n is None:
            return "+1"
        key = n.effect_key
        val = n.effect_value
        if key.startswith("unlock_"):
            return "Unlocked!"
        if "pct" in key:
            sign = "+" if val >= 0 else ""
            return f"{sign}{int(round(val * 100))}%"
        if key == "energy_timer":
            return f"+{int(val)}s"
        if key.startswith("start_"):
            return f"+{int(val)}"
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:g}"

    # ------------------------------------------------------------------
    # Primitive drawing.  We keep three reusable scratch surfaces on the
    # instance (ring, frame outline, text fade) so the per-frame path does
    # not allocate new surfaces — it only fills/blits the cached ones.
    # ------------------------------------------------------------------
    def _draw_pulse(self, surf: pygame.Surface, p: _Pulse) -> None:
        # --- Expanding ring ---
        pt = p.t / _RING_DUR
        if pt < 1.0:
            r = int(_RING_MAX_R * ease_out_cubic(pt))
            if r > 0:
                alpha = int(220 * (1.0 - pt))
                size = r * 2 + 4
                if self._ring_surf is None or self._ring_surf_size < size:
                    self._ring_surf = pygame.Surface(
                        (size, size), pygame.SRCALPHA).convert_alpha()
                    self._ring_surf_size = size
                rs = self._ring_surf
                rs.fill((0, 0, 0, 0))
                pygame.draw.circle(rs, (*p.color, alpha),
                                   (size // 2, size // 2), r, 3)
                surf.blit(rs, (p.rect.centerx - size // 2,
                               p.rect.centery - size // 2))

        # --- Node-frame pulse (a bright inflated outline) ---
        pulse_p = p.t / _PULSE_DUR
        if pulse_p < 1.0:
            alpha = int(180 * (1.0 - pulse_p))
            inflate = int(6 * math.sin(pulse_p * math.pi))
            r = p.rect.inflate(inflate * 2, inflate * 2)
            w, h = r.w + 4, r.h + 4
            if (self._frame_surf is None
                    or self._frame_surf_size[0] < w
                    or self._frame_surf_size[1] < h):
                # Grow the scratch surface (only happens when a larger node
                # pulses; subsequent frames reuse it).
                nw = max(w, self._frame_surf_size[0])
                nh = max(h, self._frame_surf_size[1])
                self._frame_surf = pygame.Surface(
                    (nw, nh), pygame.SRCALPHA).convert_alpha()
                self._frame_surf_size = (nw, nh)
            fs = self._frame_surf
            fs.fill((0, 0, 0, 0))
            tmp_rect = pygame.Rect(2, 2, r.w, r.h)
            pygame.draw.rect(fs, (*p.color, alpha), tmp_rect, 3,
                             border_radius=10)
            surf.blit(fs, (r.x - 2, r.y - 2))

    def _draw_float(self, surf: pygame.Surface, f: _FloatText) -> None:
        p = f.t / _FLOAT_DUR
        alpha = int(255 * (1.0 - ease_out_cubic(p)))
        if alpha <= 0:
            return
        # Render the text with the branch color; use a cached font.
        img = font_sm(bold=True).render(f.text, True, f.color)
        # Soft shadow for readability.
        shadow = font_sm(bold=True).render(f.text, True, (0, 0, 0))
        if alpha < 255:
            img = img.copy()
            img.set_alpha(alpha)
            shadow = shadow.copy()
            shadow.set_alpha(min(180, alpha))
        rect = img.get_rect(midtop=(f.x, f.y))
        surf.blit(shadow, (rect.x + 1, rect.y + 1))
        surf.blit(img, rect)
