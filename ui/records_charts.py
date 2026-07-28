"""Visual charts for the Records dashboard.

A self-contained stats panel rendered with pygame primitives:
a gold/sec sparkline (rolling 60 s), a zone-progress bar, a pet
collection donut, an achievement progress bar with per-achievement
icons, and a nicely formatted playtime readout.

The class is *passive*: it reads from ``game.state`` and the economy
module, draws into a rect the caller supplies, and keeps a bounded
rolling buffer of gold/sec samples.  Fonts come from the cached
``theme`` helpers, so no surface is created per frame.
"""
from __future__ import annotations

import math
from collections import deque

import pygame

import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_panel, draw_bar
from utils import format_number
from data import pets as pet_def
from data import quests as q
from data import enemies as ed
from core import game_economy


# One sample per second, 60 samples == the last 60 s of gold/sec.
_SAMPLE_INTERVAL = 1.0
_BUFFER_SIZE = 60


class RecordsCharts:
    """Renders the visual section of the Records dashboard."""

    def __init__(self, game) -> None:
        self.game = game
        self._gps: deque[float] = deque(maxlen=_BUFFER_SIZE)
        self._sample_t = 0.0
        # Seed the buffer so the sparkline isn't blank on the first frame.
        try:
            self._gps.append(float(game_economy.total_gps(game.state)))
        except Exception:
            self._gps.append(0.0)

    # ------------------------------------------------------------------
    # Rolling gold/sec buffer
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Sample current gold/sec into the rolling buffer once per second.

        ``dt`` is the real frame delta passed in by the screen; we accrue
        it and push one sample per ``_SAMPLE_INTERVAL`` so the buffer spans
        exactly the last 60 s regardless of frame rate.
        """
        self._sample_t += dt
        while self._sample_t >= _SAMPLE_INTERVAL:
            self._sample_t -= _SAMPLE_INTERVAL
            try:
                gps = float(game_economy.total_gps(self.game.state))
            except Exception:
                gps = 0.0
            self._gps.append(gps)

    # ------------------------------------------------------------------
    # Layout + draw
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw the whole visual section into ``rect``.

        Layout (two rows):
          top    ── sparkline (wide)  +  playtime (narrow)
          bottom ── zone progress  +  pet donut  +  achievement bar
        """
        x, y, w, h = rect
        gap = 12
        top_h = max(86, h // 2 - gap // 2)
        bot_h = h - top_h - gap
        top_y = y
        bot_y = y + top_h + gap

        # Top row.
        play_w = min(300, max(180, w // 4))
        spark_w = w - play_w - gap
        self._draw_sparkline(surf, pygame.Rect(x, top_y, spark_w, top_h))
        self._draw_playtime(surf, pygame.Rect(x + spark_w + gap, top_y,
                                              play_w, top_h))

        # Bottom row: three equal-ish columns.
        zone_w = (w - 2 * gap) // 3
        donut_w = zone_w
        ach_w = w - zone_w - donut_w - 2 * gap
        self._draw_zone_progress(surf, pygame.Rect(x, bot_y, zone_w, bot_h))
        self._draw_pet_donut(surf, pygame.Rect(x + zone_w + gap, bot_y,
                                               donut_w, bot_h))
        self._draw_achievements(surf, pygame.Rect(x + 2 * (zone_w + gap),
                                                  bot_y, ach_w, bot_h))

    # ------------------------------------------------------------------
    # Sparkline of recent gold/sec
    # ------------------------------------------------------------------
    def _draw_sparkline(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        draw_panel(surf, rect, fill=C.panel, border=C.panel_border)
        pad = 10
        draw_text(surf, "Gold / sec  ·  last 60 s",
                  (rect.x + pad, rect.y + 8), font_xs(), C.text_dim)
        samples = list(self._gps)
        cur = samples[-1] if samples else 0.0
        draw_text(surf, f"{format_number(cur)}/s",
                  (rect.right - pad, rect.y + 7), font_sm(bold=True), C.gold)

        plot = pygame.Rect(rect.x + pad, rect.y + 28,
                           rect.w - 2 * pad, rect.h - 36)
        if plot.w <= 6 or plot.h <= 6:
            return
        pygame.draw.rect(surf, C.panel_lo, plot, border_radius=4)

        n = len(samples)
        if n < 2:
            draw_text_center(surf, "collecting…", plot.center,
                             font_xs(), C.text_muted)
            return
        lo = min(samples)
        hi = max(samples)
        if hi <= lo:
            hi = lo + 1.0
        span = hi - lo

        pts: list[tuple[float, float]] = []
        for i, v in enumerate(samples):
            px = plot.x + 2 + (i / (n - 1)) * (plot.w - 4)
            py = plot.bottom - 4 - ((v - lo) / span) * (plot.h - 8)
            pts.append((px, py))

        # Soft fill under the line (alpha so the panel shows through).
        fill_surf = pygame.Surface((plot.w, plot.h), pygame.SRCALPHA)
        rel = [(p[0] - plot.x, p[1] - plot.y) for p in pts]
        rel.append((pts[-1][0] - plot.x, plot.h - 1))
        rel.append((pts[0][0] - plot.x, plot.h - 1))
        pygame.draw.polygon(fill_surf, (*C.gold, 55), rel)
        surf.blit(fill_surf, plot.topleft)

        # The line + a bright dot at the most recent sample.
        pygame.draw.lines(surf, C.gold, False, pts, 2)
        pygame.draw.circle(surf, C.coin,
                           (int(pts[-1][0]), int(pts[-1][1])), 3)

    # ------------------------------------------------------------------
    # Playtime
    # ------------------------------------------------------------------
    def _draw_playtime(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        draw_panel(surf, rect, fill=C.panel, border=C.panel_border)
        draw_text(surf, "Playtime", (rect.x + 12, rect.y + 8),
                  font_xs(), C.text_dim)
        secs = int(self.game.state.playtime)
        big, sub = _fmt_playtime(secs)
        draw_text_center(surf, big, (rect.centerx, rect.y + 40),
                         font_xl(bold=True), C.exp)
        if sub:
            draw_text_center(surf, sub, (rect.centerx, rect.y + 72),
                             font_sm(), C.text_dim)

    # ------------------------------------------------------------------
    # Zone progress bar
    # ------------------------------------------------------------------
    def _draw_zone_progress(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        draw_panel(surf, rect, fill=C.panel, border=C.panel_border)
        state = self.game.state
        total_zones = len(ed.ZONES)
        # Infinite zone cycling: the in-cycle zone (0..8) is the visible
        # zone; the cycle (zone_index // 9) is the post-endgame tier.
        in_cycle = state.zone_index % total_zones
        cycle = state.zone_index // total_zones
        within = state.zone_distance / cfg.ZONE_DISTANCE
        within = 0.0 if within < 0 else 1.0 if within > 1 else within
        pct = (in_cycle + within) / total_zones
        zone = ed.zone_by_index(in_cycle)

        draw_text(surf, "Zone progress", (rect.x + 12, rect.y + 8),
                  font_xs(), C.text_dim)
        draw_text(surf, f"{int(pct * 100)}%",
                  (rect.right - 12, rect.y + 7), font_sm(bold=True), C.exp)
        if cycle > 0:
            label = f"{in_cycle + 1}/{total_zones}  ·  {zone['name']}  (Cycle {cycle + 1})"
        else:
            label = f"{in_cycle + 1}/{total_zones}  ·  {zone['name']}"
        draw_text(surf, label,
                  (rect.x + 12, rect.y + 26), font_sm(bold=True), C.text)
        bar = pygame.Rect(rect.x + 12, rect.bottom - 20, rect.w - 24, 12)
        draw_bar(surf, bar, pct, fill=C.exp, bg=C.mp_bg, border=C.panel_border)

    # ------------------------------------------------------------------
    # Pet collection donut
    # ------------------------------------------------------------------
    def _draw_pet_donut(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        draw_panel(surf, rect, fill=C.panel, border=C.panel_border)
        state = self.game.state
        owned = len(state.pets)
        total = len(pet_def.PETS)
        pct = owned / total if total else 0.0

        donut_r = max(16, min(rect.h - 20, rect.w - 150) // 2)
        ring = max(6, donut_r // 3)
        cx = rect.x + 16 + donut_r
        cy = rect.centery

        # Track ring: outer disc + inner punch.
        pygame.draw.circle(surf, C.mp_bg, (cx, cy), donut_r)
        pygame.draw.circle(surf, C.panel, (cx, cy), donut_r - ring)
        # Filled wedge for the owned share, then re-punch the hole so the
        # fill becomes a ring segment matching the track.
        if pct > 0:
            segs = max(2, int(360 * pct))
            pts = [(cx, cy)]
            for i in range(segs + 1):
                ang = -math.pi / 2 + (i / segs) * 2 * math.pi * pct
                pts.append((cx + donut_r * math.cos(ang),
                           cy + donut_r * math.sin(ang)))
            pygame.draw.polygon(surf, C.soul, pts)
            pygame.draw.circle(surf, C.panel, (cx, cy), donut_r - ring)
        pygame.draw.circle(surf, C.panel_border, (cx, cy), donut_r, 1)
        pygame.draw.circle(surf, C.panel_border, (cx, cy), donut_r - ring, 1)

        draw_text_center(surf, f"{owned}/{total}", (cx, cy - 3),
                         font_md(bold=True), C.text)
        draw_text_center(surf, "pets", (cx, cy + 14), font_xs(), C.text_dim)

        tx = cx + donut_r + 14
        draw_text(surf, "Collection", (tx, rect.y + 8), font_xs(), C.text_dim)
        draw_text(surf, f"{int(pct * 100)}%", (tx, rect.y + 24),
                  font_lg(bold=True), C.soul)
        draw_text(surf, f"{total - owned} left", (tx, rect.y + 54),
                  font_xs(), C.text_muted)

    # ------------------------------------------------------------------
    # Achievement progress bar with icons
    # ------------------------------------------------------------------
    def _draw_achievements(self, surf: pygame.Surface, rect: pygame.Rect) -> None:
        draw_panel(surf, rect, fill=C.panel, border=C.panel_border)
        state = self.game.state
        unlocked = sum(1 for a in q.ACHIEVEMENTS if a.id in state.achievements)
        total = len(q.ACHIEVEMENTS)
        pct = unlocked / total if total else 0.0

        draw_text(surf, "Achievements", (rect.x + 12, rect.y + 8),
                  font_xs(), C.text_dim)
        draw_text(surf, f"{unlocked}/{total}",
                  (rect.right - 12, rect.y + 7), font_sm(bold=True), C.gold)

        # Icon row: a check for each unlocked achievement, a hollow dot
        # for each locked one.  Cheap and reads at a glance.
        ix = rect.x + 12
        iy = rect.y + 26
        for a in q.ACHIEVEMENTS:
            got = a.id in state.achievements
            ch = "✓" if got else "○"
            col = C.text_good if got else C.text_muted
            img = font_xs(bold=True).render(ch, True, col)
            if ix + img.get_width() > rect.right - 12:
                break
            surf.blit(img, (ix, iy))
            ix += img.get_width() + 4

        bar = pygame.Rect(rect.x + 12, rect.bottom - 20, rect.w - 24, 12)
        draw_bar(surf, bar, pct, fill=C.gold, bg=C.mp_bg, border=C.panel_border)


# ----------------------------------------------------------------------
# Playtime formatter
# ----------------------------------------------------------------------
def _fmt_playtime(secs: int) -> tuple[str, str]:
    """Split a playtime in seconds into (big unit, small remainder).

    Picks the largest unit that makes sense and pushes the rest into a
    dim sub-line, so "12h 34m 16s" reads as a bold ``12h`` with a small
    ``34m 16s`` under it instead of one long string.
    """
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"{secs}s", ""
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m", f"{s}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h", f"{m}m {s}s"
    d, h = divmod(h, 24)
    return f"{d}d", f"{h}h {m}m"
