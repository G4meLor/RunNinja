"""Boss intro FX: a dramatic ~1.5s reveal when a boss enters.

The screen darkens, the boss name slams in huge text with a red glow,
and a top-of-screen health bar slides in.  Once the intro completes the
health bar stays visible for as long as the boss is alive; the screen
passes the boss's current HP percentage to ``draw`` each frame.

Mini-bosses reuse the same system with a shorter, lighter intro (see
``start_miniboss``): the darken is lighter, the name slam is quicker,
and there is no persistent health bar — the mini-boss is a roadblock,
not a zone climax, so the intro should not overstay.

Pure-state + pygame primitives; fonts are cached, surfaces are cached,
no per-frame allocations on the hot path.

Integration (see docs/specs/boss_fx.md):
  * ``world._enter_boss`` calls ``boss_fx.start(...)`` via a callback set
    on the World instance (``world.on_boss_enter``).  The runner wires
    the callback to the shared ``BossFxSystem`` it owns.
  * ``world._spawn_miniboss`` emits ``miniboss_spawn`` on the bus; the
    runner's ``_on_miniboss_spawn`` calls ``boss_fx.start_miniboss(...)``.
  * ``screen_game.draw`` draws the overlay and passes the boss's HP pct
    so the health bar tracks damage.
  * ``main.py`` triggers a ``Game.shake(...)`` on boss spawn (the
    callback in the runner does this; the spec documents the shake
    hook).
"""
from __future__ import annotations

import pygame

import config as cfg
from theme import font_huge, draw_bar
from utils import clamp, ease_out_cubic, ease_in_out_cubic, lerp


# ---------------------------------------------------------------------------
# Timing / layout
# ---------------------------------------------------------------------------
INTRO_DURATION = 1.5          # total intro length (seconds)
DARKEN_TIME = 0.35            # ramp the screen darken over this long
NAME_SLAM_START = 0.30        # when the name begins to slam in
NAME_SLAM_TIME = 0.45         # slam travel duration
HEALTH_REVEAL_START = 0.75    # when the health bar begins to slide in
HEALTH_REVEAL_TIME = 0.45     # slide-in duration

# Mini-boss intro: a brief, less-dramatic version of the boss reveal.
# The mini-boss is a roadblock, not a zone climax — so the intro is
# shorter, the darken is lighter, and there is no lingering dim.
MINIBOSS_INTRO_DURATION = 0.6
MINIBOSS_DARKEN_TIME = 0.20
MINIBOSS_NAME_SLAM_START = 0.10
MINIBOSS_NAME_SLAM_TIME = 0.25
MINIBOSS_DARKEN_ALPHA_MAX = 90
MINIBOSS_DARKEN_ALPHA_HOLD = 0

DARKEN_ALPHA_MAX = 150        # max overlay alpha during intro
DARKEN_ALPHA_HOLD = 90        # lingering dim while the boss is alive

HEALTH_BAR_H = 18
HEALTH_BAR_Y = cfg.HUD_H + 8
HEALTH_BAR_MARGIN = 240        # inset from left/right edges

# Phase transition (Task 13): a ~0.8s nameplate flash + banner + hue shift
# that fires when the boss crosses an HP milestone (75/50/25%). No pause --
# the boss keeps attacking while the transition plays. The banner shows the
# new phase label; the hue shifts toward red as the phase deepens.
PHASE_TRANSITION_DURATION = 0.8
PHASE_BANNER_TIME = 0.45      # banner slide-in + hold + slide-out
PHASE_FLASH_TIME = 0.25       # nameplate flash (white -> normal)
PHASE_HUE_SHIFT_TIME = 0.8   # hue eases toward red over the whole transition

# Phase labels shown on the banner (short, punchy).
_PHASE_LABELS = {
    1: "PHASE 2 — PROJECTILE",
    2: "PHASE 3 — HAZARD",
    3: "PHASE 4 — SHIELD",
}

# Red glow palette (hue-independent; bosses are always "red threat").
_GLOW = (255, 60, 70)
_GLOW_DIM = (120, 20, 30)
_TEXT = (255, 220, 220)


# ---------------------------------------------------------------------------
# Cached resources (built lazily once; never re-created per frame)
# ---------------------------------------------------------------------------
_darken_cache: dict[tuple, pygame.Surface] = {}
_name_cache: dict[tuple, pygame.Surface] = {}
_glow_cache: dict[tuple, pygame.Surface] = {}
_label_cache: dict[str, pygame.Surface] = {}


def _boss_label(name: str) -> pygame.Surface:
    """The small uppercase boss-name label for the health bar.  Cached."""
    cached = _label_cache.get(name)
    if cached is not None:
        return cached
    from theme import font_sm
    lbl = font_sm(bold=True).render(name.upper(), True, _TEXT)
    _label_cache[name] = lbl
    return lbl


def _darken_surface(w: int, h: int, alpha: int) -> pygame.Surface:
    """A full-screen black overlay with the given alpha.  Cached by (w,h,alpha)."""
    # Quantize alpha to steps of 8 so the cache stays small.
    q = (alpha >> 3) << 3
    key = (w, h, q)
    surf = _darken_cache.get(key)
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, q))
        _darken_cache[key] = surf
    return surf


def _glow_surface(w: int, h: int, color: tuple) -> pygame.Surface:
    """A soft radial-ish glow rectangle of the given size + color.  Cached.

    Built from a few concentric rounded rects with decreasing alpha.  Cheap
    enough to build once per (w,h,color) and reuse for every boss.
    """
    key = (w, h, color)
    surf = _glow_cache.get(key)
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w // 2, h // 2
        steps = 6
        max_r = min(w, h) // 2
        for i in range(steps, 0, -1):
            r = int(max_r * (i / steps))
            a = int(120 * (1 - i / steps) ** 1.4) + 20
            pygame.draw.circle(surf, (*color, min(180, a)), (cx, cy), r)
        _glow_cache[key] = surf
    return surf


def _name_surface(text: str, hue: int) -> pygame.Surface:
    """The boss name rendered huge + bold with a red glow halo.  Cached.

    The cache key includes the hue so each boss gets its own tinted halo
    without re-rendering every frame.
    """
    key = (text, hue)
    cached = _name_cache.get(key)
    if cached is not None:
        return cached
    font = font_huge(bold=True)
    # Render the name once, then composite a glow behind it.
    name_img = font.render(text, True, _TEXT)
    nw, nh = name_img.get_size()
    # Pad around the name for the glow halo.
    pad = 60
    gw, gh = nw + pad * 2, nh + pad * 2
    out = pygame.Surface((gw, gh), pygame.SRCALPHA)
    # Tint the glow by the boss hue so each boss feels distinct, but
    # keep it red-dominant for the "threat" read.
    from assets import hsl
    halo = hsl(hue if hue else 0, 0.85, 0.55)
    glow = _glow_surface(gw, gh, halo)
    out.blit(glow, (0, 0))
    # A second, brighter core glow.
    core = _glow_surface(nw + 20, nh + 20, _GLOW)
    out.blit(core, (pad - 10, pad - 10))
    out.blit(name_img, (pad, pad))
    _name_cache[key] = out
    return out


# ---------------------------------------------------------------------------
# BossFxSystem
# ---------------------------------------------------------------------------
class BossFxSystem:
    """Owns the boss intro + persistent health bar overlay.

    Lifecycle:
      * ``start(boss_name, boss_hue)``  — call when a boss spawns.
      * ``update(dt)``                  — call every frame while ``active``.
      * ``draw(surf, boss_hp_pct)``     — call every frame while ``active``;
        pass the boss's current ``hp / max_hp`` so the bar tracks damage.
      * ``active``                      — True from ``start`` until the boss
        dies (the runner calls ``stop`` once ``world.boss_active`` flips
        back to False, or the intro simply completes and the bar stays
        until ``stop``).
    """

    __slots__ = (
        "_name", "_hue", "_t", "_intro_done", "_running",
        "_bar_pct", "_shake_pending", "_name_y0", "_name_y1",
        "_name_surf", "_bar_w", "_miniboss",
        # Phase transition (Task 13): nameplate flash + banner + hue shift.
        "_phase_active", "_phase_t", "_phase", "_phase_name", "_phase_hue",
    )

    def __init__(self) -> None:
        self._name: str = ""
        self._hue: int = 0
        self._t: float = 0.0
        self._intro_done: bool = False
        self._running: bool = False
        self._bar_pct: float = 1.0
        self._shake_pending: bool = False
        # Name slam travel: from off-screen-top to center.
        self._name_y0: float = -120.0
        self._name_y1: float = float(cfg.WINDOW_H // 2)
        self._name_surf: pygame.Surface | None = None
        self._bar_w: int = cfg.WINDOW_W - HEALTH_BAR_MARGIN * 2
        # Mini-boss mode: a shorter, lighter intro variant. When True,
        # ``update``/``draw`` use the MINIBOSS_* timing constants and skip
        # the lingering darken + persistent health bar (the mini-boss is a
        # roadblock, not a zone climax — no health bar stays after the
        # brief intro).
        self._miniboss: bool = False
        # Phase transition (Task 13): a ~0.8s nameplate flash + banner +
        # hue shift that fires when the boss crosses an HP milestone. No
        # pause — the boss keeps attacking while the transition plays.
        self._phase_active: bool = False
        self._phase_t: float = 0.0
        self._phase: int = 0
        self._phase_name: str = ""
        self._phase_hue: int = 0

    # --- public API -------------------------------------------------------
    def start(self, boss_name: str, boss_hue: int) -> None:
        """Begin the intro for a freshly-spawned boss."""
        self._name = boss_name
        self._hue = int(boss_hue)
        self._t = 0.0
        self._intro_done = False
        self._running = True
        self._miniboss = False
        self._bar_pct = 1.0
        self._shake_pending = True
        # Build the cached name surface now (one allocation, not per-frame).
        self._name_surf = _name_surface(boss_name, self._hue)

    def start_miniboss(self, name: str, hue: int) -> None:
        """Begin a brief, less-dramatic intro for a mini-boss.

        Reuses the boss intro pipeline with the MINIBOSS_* timing constants:
        a shorter total duration, a lighter darken, and no lingering dim or
        persistent health bar — the mini-boss is a roadblock, not a zone
        climax, so the intro should not overstay.
        """
        self._name = name
        self._hue = int(hue)
        self._t = 0.0
        self._intro_done = False
        self._running = True
        self._miniboss = True
        self._bar_pct = 1.0
        self._shake_pending = True
        self._name_surf = _name_surface(name, self._hue)

    def start_phase(self, name: str, hue: int, phase: int) -> None:
        """Trigger a phase-transition visual: nameplate flash + banner + hue shift.

        Fires when the boss crosses an HP milestone (75/50/25%, i.e. phase
        1/2/3). Plays over ~0.8s WITHOUT pausing — the boss keeps attacking
        while the transition plays. The banner shows the new phase label;
        the hue shifts toward red as the phase deepens (the boss gets more
        desperate). Reuses the existing banner + nameplate machinery so the
        transition feels like part of the boss intro, not a separate system.
        """
        self._phase_active = True
        self._phase_t = 0.0
        self._phase = int(phase)
        self._phase_name = name
        self._phase_hue = int(hue)

    def stop(self) -> None:
        """Clear the overlay (call when the boss dies)."""
        self._intro_done = False
        self._running = False
        self._miniboss = False
        self._t = 0.0
        self._name = ""
        self._name_surf = None
        self._bar_pct = 1.0
        self._shake_pending = False
        # Clear any in-flight phase transition.
        self._phase_active = False
        self._phase_t = 0.0
        self._phase = 0
        self._phase_name = ""
        self._phase_hue = 0

    @property
    def active(self) -> bool:
        """True while the intro is playing OR the boss health bar should show."""
        return self._running

    @property
    def wants_shake(self) -> bool:
        """True for one read after ``start`` — the runner triggers a shake."""
        s = self._shake_pending
        self._shake_pending = False
        return s

    def update(self, dt: float) -> None:
        duration = MINIBOSS_INTRO_DURATION if self._miniboss else INTRO_DURATION
        if self._t < duration:
            self._t = min(duration, self._t + dt)
            if self._t >= duration:
                self._intro_done = True
                # Mini-boss intro ends after the brief reveal — no
                # persistent health bar stays. The full zone boss keeps
                # the bar until ``stop``.
                if self._miniboss:
                    self._running = False
                    self._name_surf = None
        # Phase transition (Task 13): advance the ~0.8s nameplate flash +
        # banner + hue shift. No pause — the boss keeps attacking while
        # the transition plays (this only advances the visual timeline).
        if self._phase_active:
            self._phase_t = min(PHASE_TRANSITION_DURATION,
                                self._phase_t + dt)
            if self._phase_t >= PHASE_TRANSITION_DURATION:
                self._phase_active = False

    def draw(self, surf: pygame.Surface, boss_hp_pct: float) -> None:
        """Draw the overlay.  ``boss_hp_pct`` is the boss's hp/max_hp, 0..1."""
        if not self.active:
            return
        self._bar_pct = clamp(boss_hp_pct, 0.0, 1.0)
        w, h = surf.get_size()

        # Mini-boss variant: a brief name slam + lighter darken, no
        # persistent health bar. The mini-boss is a roadblock, not a
        # zone climax, so the intro is shorter and does not linger.
        if self._miniboss:
            self._draw_miniboss(surf, w, h)
            # Phase transition overlays play on top of the miniboss intro
            # too (a miniboss can phase if it somehow reaches the
            # thresholds; the visuals are shared).
            if self._phase_active:
                self._draw_phase_transition(surf, w, h)
            return

        # --- Darken ---
        if self._t < DARKEN_TIME:
            a = int(DARKEN_ALPHA_MAX * ease_in_out_cubic(self._t / DARKEN_TIME))
        else:
            a = DARKEN_ALPHA_MAX if not self._intro_done else DARKEN_ALPHA_HOLD
        if a > 0:
            surf.blit(_darken_surface(w, h, a), (0, 0))

        # --- Name slam ---
        if self._t >= NAME_SLAM_START and self._name_surf is not None:
            ns = self._name_surf
            if self._t < NAME_SLAM_START + NAME_SLAM_TIME:
                # Slam in with ease-out-cubic for a heavy landing feel.
                p = ease_out_cubic(
                    (self._t - NAME_SLAM_START) / NAME_SLAM_TIME
                )
                y = self._name_y0 + (self._name_y1 - self._name_y0) * p
            else:
                y = self._name_y1
            # After the slam, the name holds then fades as the bar reveals.
            hold_end = NAME_SLAM_START + NAME_SLAM_TIME + 0.25
            fade_end = hold_end + 0.35
            if self._t > hold_end:
                fp = clamp((self._t - hold_end) / (fade_end - hold_end), 0.0, 1.0)
                alpha = int(255 * (1.0 - ease_in_out_cubic(fp)))
            else:
                alpha = 255
            if alpha > 0:
                # set_alpha on the cached surface is cheap and does not
                # allocate; we restore it after blit so the cache stays
                # pristine for the next frame / next boss.
                ns.set_alpha(alpha)
                rect = ns.get_rect(center=(w // 2, int(y)))
                surf.blit(ns, rect)
                ns.set_alpha(255)

        # --- Health bar reveal (stays after intro) ---
        if self._t >= HEALTH_REVEAL_START:
            if self._t < HEALTH_REVEAL_START + HEALTH_REVEAL_TIME:
                p = ease_out_cubic(
                    (self._t - HEALTH_REVEAL_START) / HEALTH_REVEAL_TIME
                )
                # Slide in from the top edge.
                y = HEALTH_BAR_Y - 40 + 40 * p
                # Width wipes in left-to-right.
                bw = int(self._bar_w * p)
            else:
                y = HEALTH_BAR_Y
                bw = self._bar_w
            x = (w - bw) // 2
            br = pygame.Rect(x, int(y), bw, HEALTH_BAR_H)
            # Backing panel for contrast.
            panel = pygame.Rect(br.x - 4, br.y - 4, br.w + 8, br.h + 8)
            pygame.draw.rect(surf, (20, 8, 12), panel, border_radius=4)
            pygame.draw.rect(surf, _GLOW_DIM, panel, 1, border_radius=4)
            draw_bar(surf, br, self._bar_pct,
                     fill=_GLOW, bg=(40, 12, 18), border=_GLOW_DIM, radius=3)
            # Label the bar once it's fully revealed.
            if self._intro_done and self._name:
                lbl = _boss_label(self._name)
                lr = lbl.get_rect(midleft=(br.x, br.centery))
                surf.blit(lbl, lr)

        # Phase transition overlay (Task 13): nameplate flash + banner +
        # hue shift on top of the persistent health bar. No pause — the
        # boss keeps attacking while the transition plays.
        if self._phase_active:
            self._draw_phase_transition(surf, w, h)

    def _draw_phase_transition(self, surf: pygame.Surface, w: int, h: int) -> None:
        """The ~0.8s phase-transition overlay: nameplate flash + banner + hue shift.

        Fires when the boss crosses an HP milestone (75/50/25%, i.e. phase
        1/2/3). Plays WITHOUT pausing — the boss keeps attacking while the
        transition plays. Three layers, all driven by ``_phase_t``:
          1. Nameplate flash: a white flash on the boss-name label that
             fades out over PHASE_FLASH_TIME (0.25s).
          2. Banner: a thin band slides in from the top, shows the phase
             label, then slides back out over PHASE_BANNER_TIME (0.45s).
          3. Hue shift: the health bar fill eases toward red over the
             whole transition (PHASE_HUE_SHIFT_TIME, 0.8s) so the boss
             reads as more desperate at deeper phases.
        All pygame primitives + cached fonts; no per-frame allocations.
        """
        t = self._phase_t
        cx = w // 2

        # --- 1. Nameplate flash (white -> normal over PHASE_FLASH_TIME) ---
        if t < PHASE_FLASH_TIME:
            # Ease the flash out (bright at t=0, normal by t=PHASE_FLASH_TIME).
            fp = 1.0 - ease_in_out_cubic(t / PHASE_FLASH_TIME)
            flash_alpha = int(180 * fp)
            if flash_alpha > 0 and self._name:
                # Flash a bright band over the health-bar label area.
                lbl = _boss_label(self._name)
                lr = lbl.get_rect(midleft=(HEALTH_BAR_MARGIN, HEALTH_BAR_Y + 4))
                flash = pygame.Surface(lbl.get_size(), pygame.SRCALPHA)
                flash.fill((255, 255, 255, flash_alpha))
                surf.blit(flash, lr, special_flags=pygame.BLEND_RGBA_ADD)

        # --- 2. Banner (slide in, hold, slide out over PHASE_BANNER_TIME) ---
        if t < PHASE_BANNER_TIME:
            label = _PHASE_LABELS.get(self._phase, "PHASE")
            # Slide in for the first 40%, hold 20%, slide out the last 40%.
            p = t / PHASE_BANNER_TIME
            if p < 0.4:
                bp = ease_out_cubic(p / 0.4)
                band_y = int(lerp(-40, cfg.ROAD_TOP + 30, bp))
                band_alpha = int(235 * bp)
            elif p < 0.6:
                band_y = cfg.ROAD_TOP + 30
                band_alpha = 235
            else:
                bp = ease_out_cubic((p - 0.6) / 0.4)
                band_y = int(lerp(cfg.ROAD_TOP + 30, -40, bp))
                band_alpha = int(235 * (1.0 - bp))
            if band_alpha > 0:
                band_h = 34
                band = pygame.Surface((w, band_h), pygame.SRCALPHA)
                # Deep red-tinted band for the "threat" read.
                pygame.draw.rect(band, (50, 10, 20, band_alpha),
                                 band.get_rect(), border_radius=6)
                # Thin accent line top + bottom.
                pygame.draw.line(band, (*_GLOW, band_alpha),
                                 (40, 4), (w - 40, 4), 2)
                pygame.draw.line(band, (*_GLOW, band_alpha),
                                 (40, band_h - 6), (w - 40, band_h - 6), 2)
                surf.blit(band, (0, band_y))
                # Phase label centered on the band.
                from theme import font_md
                txt = font_md(bold=True).render(label, True, _TEXT)
                txt.set_alpha(band_alpha)
                tr = txt.get_rect(center=(cx, band_y + band_h // 2))
                surf.blit(txt, tr)

        # --- 3. Hue shift (health bar fill eases toward red) ---
        # The shift is visual-only; it does not change the bar's pct, just
        # the fill color. We re-draw the bar with a red-shifted fill that
        # eases back to the normal glow over PHASE_HUE_SHIFT_TIME.
        if t < PHASE_HUE_SHIFT_TIME and self._intro_done:
            hp = 1.0 - ease_in_out_cubic(t / PHASE_HUE_SHIFT_TIME)
            # Lerp the fill from a bright-red flash back to the normal glow.
            flash_fill = (255, 90, 100)
            fill = (int(flash_fill[0] + (_GLOW[0] - flash_fill[0]) * (1.0 - hp)),
                    int(flash_fill[1] + (_GLOW[1] - flash_fill[1]) * (1.0 - hp)),
                    int(flash_fill[2] + (_GLOW[2] - flash_fill[2]) * (1.0 - hp)))
            br = pygame.Rect((w - self._bar_w) // 2, HEALTH_BAR_Y,
                             self._bar_w, HEALTH_BAR_H)
            panel = pygame.Rect(br.x - 4, br.y - 4, br.w + 8, br.h + 8)
            pygame.draw.rect(surf, (20, 8, 12), panel, border_radius=4)
            pygame.draw.rect(surf, _GLOW_DIM, panel, 1, border_radius=4)
            draw_bar(surf, br, self._bar_pct,
                     fill=fill, bg=(40, 12, 18), border=_GLOW_DIM, radius=3)
            if self._name:
                lbl = _boss_label(self._name)
                lr = lbl.get_rect(midleft=(br.x, br.centery))
                surf.blit(lbl, lr)

    def _draw_miniboss(self, surf: pygame.Surface, w: int, h: int) -> None:
        """The brief mini-boss intro: a lighter darken + a quick name slam.

        No persistent health bar — the mini-boss is a roadblock, not a zone
        climax, so the intro reveals the name and gets out of the way. The
        runner clears ``_running`` once the intro completes (see ``update``).
        """
        # --- Lighter darken (no lingering dim) ---
        if self._t < MINIBOSS_DARKEN_TIME:
            a = int(MINIBOSS_DARKEN_ALPHA_MAX
                    * ease_in_out_cubic(self._t / MINIBOSS_DARKEN_TIME))
        else:
            # Ramp the darken back down once the intro is past its peak.
            remaining = MINIBOSS_INTRO_DURATION - MINIBOSS_DARKEN_TIME
            if remaining > 0 and self._t > MINIBOSS_DARKEN_TIME:
                fp = clamp((self._t - MINIBOSS_DARKEN_TIME) / remaining,
                            0.0, 1.0)
                a = int(MINIBOSS_DARKEN_ALPHA_MAX
                        * (1.0 - ease_in_out_cubic(fp)))
            else:
                a = MINIBOSS_DARKEN_ALPHA_MAX
        if a > 0:
            surf.blit(_darken_surface(w, h, a), (0, 0))

        # --- Quick name slam ---
        if (self._t >= MINIBOSS_NAME_SLAM_START
                and self._name_surf is not None):
            ns = self._name_surf
            if self._t < MINIBOSS_NAME_SLAM_START + MINIBOSS_NAME_SLAM_TIME:
                p = ease_out_cubic(
                    (self._t - MINIBOSS_NAME_SLAM_START) / MINIBOSS_NAME_SLAM_TIME
                )
                y = self._name_y0 + (self._name_y1 - self._name_y0) * p
            else:
                y = self._name_y1
            # Hold briefly then fade out by the end of the intro.
            hold_end = (MINIBOSS_NAME_SLAM_START
                        + MINIBOSS_NAME_SLAM_TIME + 0.05)
            fade_end = MINIBOSS_INTRO_DURATION
            if self._t > hold_end and fade_end > hold_end:
                fp = clamp((self._t - hold_end) / (fade_end - hold_end),
                            0.0, 1.0)
                alpha = int(255 * (1.0 - ease_in_out_cubic(fp)))
            else:
                alpha = 255
            if alpha > 0:
                ns.set_alpha(alpha)
                rect = ns.get_rect(center=(w // 2, int(y)))
                surf.blit(ns, rect)
                ns.set_alpha(255)
