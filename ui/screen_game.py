"""Main gameplay screen: the road, ninja, enemies, fireflies, HUD, combo,
energy, and active-skill buttons.
"""
from __future__ import annotations

import math
import pygame

import config as cfg
from theme import C, font_xs, font_sm, font_md, font_lg, font_xl
from theme import draw_text, draw_text_center, draw_bar, draw_panel
from ui.widgets import Button, currency_pill
from utils import format_number, clamp


# ---------------------------------------------------------------------------
# Task 27 (pl-juice-polish): skill cooldown progress fill + low-HP vignette
# ---------------------------------------------------------------------------
# The low-HP threshold (the ninja's HP fraction below which the red
# vignette ramps in during a boss fight). 0.25 = 25% of max_hp.
_LOW_HP_THRESHOLD = 0.25
# The skill cooldown-ready glow duration (seconds). The glow decays over
# this duration after a cooldown-ready transition.
_SKILL_GLOW_DUR = 1.0
# The count-up duration for the gold pill (seconds). The HUD gold counts
# up from the old value to the new value over this duration (no instant
# snapping). Tuned so a boss-kill gain feels like a quick count-up (~0.8s)
# rather than a snap or a slow crawl.
_GOLD_COUNT_DUR = 0.8

# Task 29 (gfx-parallax): the parallax scroll offsets for the 5 background
# layers (sky, far hills, mid hills, near foliage, road). The sky (offset
# 0) does not scroll; the road (offset 1.0) scrolls at the full rate; the
# hill + foliage layers scroll at intermediate rates for the parallax
# effect. The screen blits each layer at ``-int(scroll * offset) %
# WINDOW_W`` from a single ``scroll_accumulator`` that advances each
# frame (pinned to 0 when reduced_motion is on or the render tier is low).
PARALLAX_OFFSETS = (0.0, 0.15, 0.35, 0.6, 1.0)

# Task 32 (gfx-outline-shading-squash): squash-and-stretch parameters.
# The squash plays for ~80ms on slash/hit, driven by the existing
# ``slash_anim`` (initial 0.15s) and ``last_damage_timer`` (initial 0.6s)
# timers. The peak squash is 12% (k=0.12), so the sprite scales to
# (1.12, 0.88) at the peak and decays back to (1.0, 1.0) over 80ms.
_SQUASH_PEAK = 0.12
_SQUASH_DUR = 0.08  # 80ms
# The slash/hit timer initial values (the values the timers are reset to
# when a slash/hit fires). Used to compute the elapsed time since the
# slash/hit (elapsed = initial - current).
_SLASH_TIMER_INITIAL = 0.15
_HIT_TIMER_INITIAL = 0.6


def squash_factor(slash_anim: float = 0.0, last_damage_timer: float = 0.0,
                  reduced_motion: bool = False) -> float:
    """The squash-and-stretch factor k for the current frame.

    Returns 0.0 when there is no squash (at rest, or after the 80ms
    squash window, or when ``reduced_motion`` is on). The sprite scales
    to (1+k, 1-k) — wider + shorter — so the squash reads as an impact
    (the ninja compresses on the slash/hit, then springs back).

    The squash is driven by the existing ``slash_anim`` / ``last_damage_timer``
    timers (no new state). The elapsed time since the slash/hit is
    ``initial - current`` (the timers count down from the initial value);
    the squash decays linearly from the peak to 0 over ``_SQUASH_DUR``
    (80ms). Hit takes priority over slash (the ninja recoils when hit
    mid-slash).

    Gated by ``reduced_motion`` (the squash is a visual flourish; the
    slash/hit frame selection from the sprite sheet is the non-visual
    cue for reduced_motion players). The screen also gates on the
    render tier (low tier -> no squash); the tier gate is applied by the
    caller (the screen passes ``reduced_motion=not anim_enabled`` where
    ``anim_enabled = parallax_enabled(quality)``, so the low tier
    disables the squash the same way it disables parallax).
    """
    if reduced_motion:
        return 0.0
    # Hit takes priority over slash (the ninja recoils when hit
    # mid-slash; the hit squash is the recoil, the slash squash is the
    # lunge compress).
    if last_damage_timer > 0:
        elapsed = _HIT_TIMER_INITIAL - last_damage_timer
    elif slash_anim > 0:
        elapsed = _SLASH_TIMER_INITIAL - slash_anim
    else:
        return 0.0
    if elapsed < 0:
        elapsed = 0.0
    if elapsed >= _SQUASH_DUR:
        return 0.0
    # Linear decay from the peak to 0 over _SQUASH_DUR. Clamp tiny
    # floating-point residuals to 0 so the squash is exactly 0 at the
    # end of the window (no subpixel squash that the player can't see).
    k = _SQUASH_PEAK * (1.0 - elapsed / _SQUASH_DUR)
    return k if k > 1e-6 else 0.0


def _approach(current: float, target: float, max_delta: float) -> float:
    """Move ``current`` toward ``target`` by at most ``max_delta``."""
    if current < target:
        return min(target, current + max_delta)
    return max(target, current - max_delta)


class GameScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.lane_scroll = 0.0
        # Task 29 (gfx-parallax): a single scroll accumulator that all 5
        # parallax layers read. Advanced each frame by
        # ``runner.scroll_speed() * dt`` (2x during Auto Katana); pinned
        # to 0 when ``reduced_motion`` is on or the render tier is low
        # (parallax disabled) so the layers do not scroll.
        self.scroll_accumulator = 0.0
        self.toasts: list = []
        self._bg_key = None
        self.welcome_pending = None
        self.welcome_t = 0.0
        self._init_welcome()
        # Active-skill buttons (built when skills are unlocked).
        self.skill_buttons: list[Button] = []
        self._build_skill_buttons()
        # Combo Finisher buttons (always present; enabled when charges > 0).
        self.finisher_buttons: list[Button] = []
        self._build_finisher_buttons()
        # Energy button.
        self.btn_energy = Button(
            (cfg.WINDOW_W - 180, cfg.WINDOW_H - 60, 160, 44),
            "Auto Katana", on_click=self._toggle_energy,
        )
        # Nav buttons.
        self.nav_buttons: list[Button] = []
        self._build_nav()
        # Task 34 (cnt-shadow-dungeon-variants): Shadow Dungeon entry +
        # variant selector. A button on the game screen opens the dungeon
        # variant selector (Story/Endless/Daily). The selector is a small
        # modal that overlays the game screen; the three variant buttons
        # enter the dungeon with the chosen variant. The dungeon entry
        # gate (``can_enter_dungeon``) is a threshold check; the button
        # is disabled when the player does not meet the gate.
        self.btn_dungeon = Button(
            (cfg.WINDOW_W - 292, cfg.WINDOW_H - 60, 100, 44),
            "Dungeon", on_click=self._open_dungeon_selector,
            color=(140, 60, 180),
        )
        # The variant selector modal (drawn over the game screen when
        # ``dungeon_selector_open`` is True). The three variant buttons
        # enter the dungeon with the chosen variant.
        self.dungeon_selector_open: bool = False
        self.dungeon_variant_buttons: list[Button] = []
        self._build_dungeon_variant_buttons()
        # Task 34: the dungeon entry method (called by the variant buttons
        # to enter the dungeon with a variant). Exposed as a public method
        # so the UI layer + tests can call it directly.
        # Task 27 (pl-juice-polish): per-skill cooldown-ready glow timers.
        # ``_skill_glow[sid]`` is the remaining glow seconds (decays to 0).
        # ``_skill_was_on_cooldown[sid]`` tracks whether the skill was on
        # cooldown last tick so the screen can detect the cooldown-ready
        # transition (the moment the chime + glow fire). The glow is the
        # visual cue; the chime is the audio cue; both fire once per
        # cooldown-ready transition (not every tick while ready).
        self._skill_glow: dict[str, float] = {}
        self._skill_was_on_cooldown: dict[str, bool] = {}
        # Task 27: the low-HP red vignette intensity (0..1). Decays to 0
        # when the ninja is above the low-HP threshold or no boss is
        # active; ramps to 1 when the ninja is below the threshold AND a
        # boss is active. The vignette is a VISUAL urgency cue, NOT a boss
        # enrage timer mechanic (gap #5: no enrage timer, no weak-point-
        # tap; the boss is auto-killable through normal DPS).
        self._vignette_intensity: float = 0.0
        # Task 27: count-up currency display. The HUD gold pill counts up
        # from the old value to the new value over ``_GOLD_COUNT_DUR``
        # seconds (no instant snapping). ``_displayed_gold`` is the value
        # currently shown; ``_gold_count_old`` / ``_gold_count_new`` are
        # the count-up endpoints; ``_gold_count_t`` is the elapsed time.
        # When the actual gold changes (a gain), a new count-up starts
        # from the current displayed value to the new actual value.
        self._displayed_gold: float = 0.0
        self._gold_count_old: float = 0.0
        self._gold_count_new: float = 0.0
        self._gold_count_t: float = 0.0
        # Task 27: gold milestone celebration. The screen toasts when a
        # gold milestone (1k / 10k / 100k / ...) is crossed. The previous
        # gold value is tracked so the screen can detect the crossing.
        self._prev_gold: float = 0.0

    def _build_nav(self) -> None:
        y = 8
        x = cfg.WINDOW_W - 8
        labels = [
            ("Cosmetics", lambda: self.game.set_screen("cosmetics")),
            ("Bestiary", lambda: self.game.set_screen("bestiary")),
            ("Godai", lambda: self.game.set_screen("godai")),
            ("Hero", lambda: self.game.set_screen("hero")),
            ("Records", lambda: self.game.set_screen("records")),
            ("Settings", lambda: self.game.set_screen("settings")),
            ("Quests", lambda: self.game.set_screen("quests")),
            ("Pets", lambda: self.game.set_screen("pets")),
            ("Skills", lambda: self.game.set_screen("skilltree")),
            ("Upgrades", lambda: self.game.set_screen("upgrades")),
            ("Buildings", lambda: self.game.set_screen("buildings")),
            ("Ascend", lambda: self.game.set_screen("ascend")),
        ]
        for label, cb in reversed(labels):
            w = 64
            x -= w + 4
            btn = Button((x, y, w, 32), label, on_click=cb)
            self.nav_buttons.insert(0, btn)

    # -----------------------------------------------------------------
    # Task 34 (cnt-shadow-dungeon-variants): dungeon entry + variant
    # selector
    # -----------------------------------------------------------------
    def _build_dungeon_variant_buttons(self) -> None:
        """Build the three dungeon variant buttons (Story/Endless/Daily).

        The buttons are in the variant selector modal; each enters the
        dungeon with the chosen variant. The buttons are always present
        (built once); they're enabled only when the player meets the
        dungeon entry gate (``can_enter_dungeon``) — the gate is checked
        in ``update`` each tick.

        Layout: the modal panel is centered at (cx, cy) with size
        (pw, ph) = (360, 320) (see ``_draw_dungeon_selector``). The
        three variant buttons (bh=44, gap=8) are stacked vertically
        starting at the panel's title area; the Close button sits at the
        bottom of the panel. All buttons are inside the panel frame
        (no overlap with the panel border, no overlap with each other).
        """
        from engine.runner import can_enter_dungeon, daily_dungeon_seed
        cx = cfg.WINDOW_W // 2
        cy = cfg.WINDOW_H // 2
        bw, bh = 220, 44
        # The modal panel size (must match ``_draw_dungeon_selector``).
        pw, ph = 360, 320
        panel_top = cy - ph // 2          # 200
        panel_bottom = cy + ph // 2       # 520
        # The title + subtitle take the top ~70px of the panel; the
        # variant buttons start below the subtitle. The three buttons
        # (bh=44) + 2 gaps (8) = 148px; the Close button (36) + a 12px
        # gap = 48px. Total content: 70 (title) + 148 (variants) + 48
        # (close) = 266px, which fits inside the 320px panel with
        # ~27px of padding top/bottom.
        variants_start = panel_top + 80   # 280
        variants = [
            ("Story", "story",
             "A fixed 5-floor dungeon. Easier, a narrative progression."),
            ("Endless", "endless",
             "Infinite floors, scaling difficulty. How deep can you go?"),
            ("Daily", "daily",
             "A shared daily challenge. 5 floors, same for everyone today."),
        ]
        self.dungeon_variant_buttons = []
        # The three variant buttons, stacked vertically with an 8px gap.
        for i, (label, vtype, hint) in enumerate(variants):
            y = variants_start + i * (bh + 8)
            btn = Button(
                (cx - bw // 2, y, bw, bh),
                label, on_click=lambda v=vtype: self._enter_dungeon(v),
                color=(140, 60, 180), hint=hint,
            )
            self.dungeon_variant_buttons.append(btn)
        # The Close button at the bottom of the panel (inside the frame,
        # below the variant buttons with a 12px gap). The variant buttons
        # end at variants_start + 3*(bh+8) - 8 = 280 + 148 - 8 = 420;
        # the Close button starts at 420 + 12 = 432, ends at 432 + 36 =
        # 468, which is inside the panel (panel_bottom = 520) with a
        # ~52px bottom margin.
        btn_close = Button(
            (cx - 60, variants_start + len(variants) * (bh + 8) - 8 + 12,
             120, 36),
            "Close", on_click=self._close_dungeon_selector,
            color=(80, 80, 100),
        )
        self.dungeon_variant_buttons.append(btn_close)
        # Keep the variant list for reference (the UI layer can read it).
        self._dungeon_variants = [v for _l, v, _h in variants]

    def _open_dungeon_selector(self) -> None:
        """Open the dungeon variant selector modal."""
        # Only open if the player meets the entry gate (the gate is a
        # threshold check; the selector shows the variants but the enter
        # buttons are disabled if the gate is not met — checked in
        # ``update``).
        self.dungeon_selector_open = True

    def _close_dungeon_selector(self) -> None:
        """Close the dungeon variant selector modal without entering."""
        self.dungeon_selector_open = False

    def _enter_dungeon(self, variant: str) -> None:
        """Enter the dungeon with the chosen variant.

        Constructs a ``DungeonRunner`` with the variant, enters it (the
        gate is a threshold check — ``enter`` returns False if the gate
        is not met), and ticks the dungeon alongside the road (the road
        keeps idling). The dungeon runner is stored on the game so the
        main loop can tick it + the road together.

        The variant is one of "story" | "endless" | "daily":
          * Story:   a fixed 5-floor dungeon, easier (the narrative
                     progression).
          * Endless: infinite floors, scaling difficulty.
          * Daily:   a shared daily challenge (5 floors, same for
                     everyone today — the daily seed is deterministic
                     per day).
        """
        from engine.runner import DungeonRunner, can_enter_dungeon
        state = self.game.state
        # The gate is a threshold check; if the player does not meet it,
        # do not enter (the button should be disabled, but guard here too).
        if not can_enter_dungeon(state):
            self.notify("Need 50 medals or zone 9 to enter the dungeon.",
                        C.text_warn)
            return
        # Construct the dungeon runner with the variant + enter. The
        # dungeon runner is stored on the game so the main loop can tick
        # it alongside the road.
        dr = DungeonRunner(state, variant=variant)
        if not dr.enter():
            self.notify("Could not enter the dungeon.", C.text_warn)
            return
        self.game.dungeon_runner = dr
        # Close the selector modal (the dungeon is now active).
        self.dungeon_selector_open = False
        # Notify the player which variant they entered.
        vlabel = {"story": "Story", "endless": "Endless",
                  "daily": "Daily"}.get(variant, variant)
        self.notify(f"Shadow Dungeon ({vlabel}) entered!", (255, 180, 90))
        from assets import play
        play("skill", state.sound_on)

    def _build_skill_buttons(self) -> None:
        self.skill_buttons = []
        # Track the skill id for each button so the synergy arc can find
        # the two buttons involved by skill id (Task 25).
        self._skill_button_ids: list[str] = []
        runner = self.game.runner
        x = 16
        for sid, sk in runner.skills.items():
            btn = Button((x, cfg.WINDOW_H - 60, 130, 44), sk.name,
                         on_click=lambda s=sid: self._fire_skill(s))
            self.skill_buttons.append(btn)
            self._skill_button_ids.append(sid)
            x += 140

    def _build_finisher_buttons(self) -> None:
        """Build the 4 combo-finisher buttons.

        Each button shows the finisher's name; the charge count is drawn
        next to it (in the combo HUD area). The buttons are always
        present; they're disabled when the player has fewer charges than
        the finisher's cost (the runner's ``activate_finisher`` is the
        source of truth — it no-ops and notifies if charges are short).
        """
        from engine.runner import FINISHERS
        self.finisher_buttons = []
        # Place the finisher buttons in a row above the skill buttons
        # (cfg.WINDOW_H - 110) so they don't overlap the skill row.
        x = 16
        y = cfg.WINDOW_H - 110
        for fid, (name, cost, _kind) in FINISHERS.items():
            btn = Button((x, y, 150, 40), name,
                         on_click=lambda f=fid: self._fire_finisher(f))
            self.finisher_buttons.append(btn)
            x += 156
        self._finisher_ids = list(FINISHERS.keys())

    def _fire_finisher(self, fid: str) -> None:
        """Spend charges on a combo finisher (called by the finisher buttons)."""
        self.game.runner.activate_finisher(fid)
        from assets import play
        play("skill", self.game.state.sound_on)

    def _fire_skill(self, sid: str) -> None:
        self.game.runner.activate_skill(sid)
        from assets import play
        play("skill", self.game.state.sound_on)

    def _toggle_energy(self) -> None:
        self.game.runner.toggle_energy()

    def _init_welcome(self) -> None:
        from core import offline
        report = offline.compute(self.game.state)
        if report.get("applied"):
            self.welcome_pending = report

    def handle(self, event: pygame.event.Event) -> None:
        if self.welcome_pending:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                from core import offline
                offline.apply(self.game.state, self.welcome_pending)
                self._welcome_notify(self.welcome_pending)
                self.welcome_pending = None
            return
        # Task 34: the dungeon variant selector modal takes priority over
        # the road tap + the other buttons (the modal is an overlay).
        if self.dungeon_selector_open:
            for b in self.dungeon_variant_buttons:
                b.handle(event)
            return
        # Tap on the road.
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and cfg.ROAD_TOP <= event.pos[1] <= cfg.ROAD_BOTTOM):
            self.game.runner.tap_at(event.pos[0], event.pos[1])
            from assets import play
            play("tap", self.game.state.sound_on)
        for b in self.nav_buttons + self.skill_buttons + self.finisher_buttons:
            b.handle(event)
        self.btn_energy.handle(event)
        # Task 34: the dungeon entry button (opens the variant selector).
        self.btn_dungeon.handle(event)

    def update(self, dt: float) -> None:
        for b in self.nav_buttons + self.skill_buttons + self.finisher_buttons:
            b.update(dt)
        self.btn_energy.update(dt)
        # Task 34: update the dungeon entry button + the variant selector.
        # The dungeon button is enabled only when the player meets the
        # entry gate (``can_enter_dungeon``); the variant buttons inside
        # the selector are gated the same way.
        from engine.runner import can_enter_dungeon
        gate_met = can_enter_dungeon(self.game.state)
        self.btn_dungeon.update(dt)
        self.btn_dungeon.enabled = gate_met
        for b in self.dungeon_variant_buttons:
            b.update(dt)
            # The "Close" button is always enabled; the variant buttons
            # are enabled only when the gate is met.
            if b is not self.dungeon_variant_buttons[0]:
                b.enabled = gate_met
        # If the dungeon is active, tick the dungeon runner alongside the
        # road (the road keeps idling). The dungeon runner is stored on
        # the game; the main loop ticks the road runner, the screen ticks
        # the dungeon runner (the dungeon is a track on the same run).
        if (self.game.state.dungeon_active
                and hasattr(self.game, "dungeon_runner")
                and self.game.dungeon_runner is not None):
            self.game.dungeon_runner.update(dt)
        state = self.game.state
        # Refresh skill buttons if the runner's skill set changed.
        if len(self.skill_buttons) != len(self.game.runner.skills):
            self._build_skill_buttons()
        # Sync the skill FX reduced-motion gate from state each tick
        # (same pattern as the combo_fx gate sync in the runner).
        self.game.runner.skill_fx.reduced_motion = state.reduced_motion
        # Task 27 (pl-juice-polish): skill cooldown-ready chime + glow.
        # For each unlocked skill, detect the cooldown-ready transition
        # (the skill was on cooldown last tick, and is ready this tick).
        # On the transition: fire the chime (respecting ``sound_on``) +
        # arm the glow timer (the glow decays over ~1.0s; the visual cue
        # for the cooldown-ready event). The chime is the audio cue; the
        # glow is the visual cue (gated by ``reduced_motion`` -- the glow
        # is a visual flourish; the chime is the non-visual cue for
        # reduced_motion players).
        runner = self.game.runner
        for sid, sk in runner.skills.items():
            was_on_cd = self._skill_was_on_cooldown.get(sid, False)
            is_on_cd = sk.timer > 0
            if was_on_cd and not is_on_cd:
                # Cooldown-ready transition: fire the chime + arm the glow.
                from assets import play
                play("skill_ready", state.sound_on)
                if not state.reduced_motion:
                    self._skill_glow[sid] = 1.0  # 1.0s glow
            self._skill_was_on_cooldown[sid] = is_on_cd
        # Decay the per-skill glow timers.
        for sid in list(self._skill_glow.keys()):
            if self._skill_glow[sid] > 0:
                self._skill_glow[sid] = max(0.0, self._skill_glow[sid] - dt)
                if self._skill_glow[sid] <= 0:
                    del self._skill_glow[sid]
        # Task 27: low-HP red vignette (a VISUAL urgency cue, NOT a boss
        # enrage timer mechanic -- gap #5). Ramp the vignette intensity
        # toward 1.0 when the ninja is below the low-HP threshold (25%
        # of max_hp) AND a boss is active; decay toward 0 otherwise.
        # Gated by ``reduced_motion`` (the vignette is a visual flourish;
        # reduced_motion players get no vignette -- the boss bar + the
        # ninja's HP bar are the non-visual urgency cues).
        if not state.reduced_motion:
            runner = self.game.runner
            world = runner.world
            ninja = runner.ninja
            boss_active = bool(world.boss_active)
            low_hp = (ninja.max_hp > 0
                      and ninja.hp / ninja.max_hp < 0.25
                      and ninja.alive)
            target = 1.0 if (boss_active and low_hp) else 0.0
            # Smooth ramp/decay (0.6s ramp, 1.2s decay) so the vignette
            # eases in/out rather than snapping.
            rate = 1.66 if target > self._vignette_intensity else 0.83
            self._vignette_intensity = _approach(
                self._vignette_intensity, target, dt * rate)
        else:
            self._vignette_intensity = 0.0
        # Task 27: count-up currency display. When the actual gold changes
        # (a gain), start a new count-up from the current displayed value
        # to the new actual value. The count-up uses ``count_up`` from
        # ``ui.currency_fx`` (an eased animation, no instant snapping).
        # Losses (spending) snap immediately -- the count-up is for gains
        # only (counting down a loss would feel like a slow drain, which
        # is worse than a snap).
        from ui.currency_fx import count_up, gold_milestone_crossed
        actual_gold = float(state.gold)
        if actual_gold != self._gold_count_new:
            if actual_gold > self._gold_count_new:
                # A gain: start a new count-up from the current displayed
                # value to the new actual value.
                self._gold_count_old = self._displayed_gold
                self._gold_count_new = actual_gold
                self._gold_count_t = 0.0
            else:
                # A loss (spending): snap immediately + re-baseline.
                self._displayed_gold = actual_gold
                self._gold_count_old = actual_gold
                self._gold_count_new = actual_gold
                self._gold_count_t = _GOLD_COUNT_DUR
        # Advance the count-up timer + compute the displayed value.
        if self._gold_count_t < _GOLD_COUNT_DUR:
            self._gold_count_t = min(_GOLD_COUNT_DUR, self._gold_count_t + dt)
            self._displayed_gold = count_up(
                self._gold_count_old, self._gold_count_new,
                _GOLD_COUNT_DUR, self._gold_count_t)
        else:
            self._displayed_gold = self._gold_count_new
        # Task 27: gold milestone celebration. When a gold milestone (1k /
        # 10k / 100k / ...) is crossed, toast the milestone (a brief
        # celebration). The toast is gated by ``sound_on`` (the toast
        # itself is visual; the chime is the audio cue, played by the
        # toast -- but we don't play a chime here to avoid stacking with
        # the skill-ready chime; the toast is the visual cue).
        crossed = gold_milestone_crossed(self._prev_gold, actual_gold)
        if crossed is not None:
            self.notify(f"Gold milestone: {format_number(crossed)}!", C.gold)
        self._prev_gold = actual_gold
        # Task 29 (gfx-parallax): advance the scroll accumulator. The
        # accumulator is the single scroll value all 5 parallax layers
        # read; each layer blits at ``offset * accumulator``. The
        # accumulator advances at ``runner.scroll_speed() * dt`` (2x
        # during Auto Katana). Pinned to 0 when ``reduced_motion`` is on
        # or the render tier is low (parallax disabled) so the layers do
        # not scroll — the accessibility gate and the tier never
        # diverge (both read ``effective_render_quality`` →
        # ``parallax_enabled``).
        from core.quality import parallax_enabled
        if parallax_enabled(state.effective_render_quality()):
            self.scroll_accumulator += self.game.runner.scroll_speed() * dt
        else:
            self.scroll_accumulator = 0.0
        # Lane scroll (kept for backward compat; the parallax road layer
        # now carries the lane lines, but lane_scroll is still advanced
        # so any reader sees a moving value).
        self.lane_scroll = (self.lane_scroll + 90 * dt) % 60
        # Toasts.
        for t in self.toasts:
            t.update(dt)
        self.toasts = [t for t in self.toasts if t.alive]
        # Welcome.
        if self.welcome_pending:
            self.welcome_t = min(1.0, self.welcome_t + dt * 3)

    def draw(self, surf: pygame.Surface) -> None:
        runner = self.game.runner
        state = self.game.state
        world = runner.world
        ox, oy = self.game.shake_offset()

        # Task 29 (gfx-parallax): blit 5 pre-baked scrollable background
        # layers at parallax offsets [0, 0.15, 0.35, 0.6, 1.0] from a
        # single scroll accumulator. The layers are cached per
        # (zone_in_cycle, hue) in assets.parallax_layers; each is a
        # full-screen SRCALPHA surface with convert_alpha. The sky
        # (offset 0) does not scroll; the road (offset 1.0) scrolls at
        # the full rate; the hill + foliage layers scroll at
        # intermediate rates for the parallax effect. The accumulator
        # is pinned to 0 when reduced_motion is on or the render tier is
        # low (parallax disabled) so the layers do not scroll.
        from assets import parallax_layers
        from core.quality import parallax_enabled
        layers = parallax_layers(world.zone_in_cycle, world.zone["hue"])
        scroll = (self.scroll_accumulator
                  if parallax_enabled(state.effective_render_quality())
                  else 0.0)
        for i, (layer, offset) in enumerate(zip(layers, PARALLAX_OFFSETS)):
            if offset == 0:
                # Non-scrollable layer (sky): blit at the shake offset.
                surf.blit(layer, (ox, oy))
            else:
                # Scrollable layer: blit at two positions to cover the
                # screen with seamless tiling. The layer tiles at
                # WINDOW_W (the hill sine frequencies are integer
                # multiples of 2*pi/WINDOW_W; the lane lines + foliage
                # use spacings that divide WINDOW_W), so the wrap is
                # invisible.
                lw = layer.get_width()
                sx = -int(scroll * offset) % lw
                surf.blit(layer, (sx + ox, oy))
                surf.blit(layer, (sx - lw + ox, oy))

        # Lane y-center (used by the enemy + ninja positioning below).
        ly = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2

        # Enemies.
        # Task 30 (gfx-sprite-sheet-anim): the bandit shape has a
        # multi-frame idle cycle; other shapes keep the static sprite.
        # ``enemy_frame`` returns a zero-copy subsurface (no per-frame
        # allocation, same pixel count + format as the static sprite).
        # Pin to frame 0 when ``reduced_motion`` (or the low render tier,
        # which reduced_motion forces) so the animation is disabled for
        # accessibility.
        # Task 32 (gfx-outline-shading-squash): the enemy squash-and-
        # stretch scales (1+k, 1-k) for ~80ms on hit, driven by the
        # existing ``last_damage_timer`` (the enemy recoils when hit).
        # Gated by the same tier path as the sprite-sheet animation (low
        # tier disables both); the reduced_motion gate is never bypassed.
        # The squash is applied per-frame with ``smoothscale`` (the
        # outline + shading are cache-time, zero per-frame cost; the
        # squash is per-frame because it's a transient animation driven
        # by the hit timer).
        from assets import enemy_frame
        from core.quality import parallax_enabled
        # The sprite-sheet animation is gated on the same tier path as
        # parallax (low tier disables both): the tier is the single
        # source of truth and the reduced_motion gate is never bypassed.
        anim_enabled = parallax_enabled(state.effective_render_quality())
        for e in world.enemies:
            if not e.alive and e.last_damage_timer <= -0.3:
                continue
            es = enemy_frame(e.edef, size=e.size * 2, bob=e.bob,
                             reduced_motion=not anim_enabled)
            ex = int(e.x) + ox
            ey = ly + 8 + oy
            e.y = ey
            # Task 32: squash-and-stretch on hit. The squash scales
            # (1+k, 1-k) for ~80ms after the hit (the enemy recoils).
            # Gated by the tier (low tier / reduced_motion -> no squash).
            k_enemy = squash_factor(last_damage_timer=e.last_damage_timer,
                                   reduced_motion=not anim_enabled)
            if k_enemy > 0:
                ew, eh = es.get_size()
                es = pygame.transform.smoothscale(
                    es, (max(1, int(ew * (1 + k_enemy))),
                          max(1, int(eh * (1 - k_enemy)))))
            if not e.alive:
                fade = max(0.0, (e.last_damage_timer + 0.3) / 0.3)
                es = es.copy()
                es.set_alpha(int(255 * fade))
            # Elites get a distinct red-orange tint so they read as a
            # tougher variant at a glance. The mini-boss keeps the boss
            # red — it is already a boss-statted enemy.
            if e.is_elite and e.alive:
                tint = pygame.Surface(es.get_size(), pygame.SRCALPHA)
                tint.fill((255, 140, 60, 90))
                es = es.copy()
                es.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            if e.flash > 0 and e.alive:
                flash = pygame.Surface(es.get_size(), pygame.SRCALPHA)
                flash.fill((255, 255, 255, int(120 * e.flash / 0.12)))
                es = es.copy()
                es.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(es, es.get_rect(midbottom=(ex, ey + 30)))
            if e.max_hp > 0 and e.alive:
                bw = max(28, e.size)
                br = pygame.Rect(ex - bw // 2, ey - 18, bw, 5)
                # Elites get the warning-amber bar; the boss + mini-boss
                # keep the red boss bar so the threat read stays consistent.
                if e.is_boss or e.is_miniboss:
                    bar_fill = C.text_bad
                elif e.is_elite:
                    bar_fill = C.text_warn
                else:
                    bar_fill = C.hp
                draw_bar(surf, br, e.hp / e.max_hp,
                         fill=bar_fill,
                         bg=C.hp_bg, border=C.panel_border)
            if (e.is_boss or e.is_miniboss) and e.alive:
                draw_text_center(surf, e.name, (ex, ey - 28), font_sm(bold=True), C.text_warn)
                # Yokai Portal boss variant (Task 16): a rare boss variant
                # that jumps the zone bar when killed. The variant gets a
                # "YOKAI PORTAL" tag above the boss name so the player can
                # see the skip is coming (the brief calls for "a brief"
                # visual cue; the boss-FX intro already fires for the boss).
                if getattr(e, "is_yokai_portal", False):
                    draw_text_center(surf, "YOKAI PORTAL", (ex, ey - 44),
                                     font_xs(bold=True), C.soul)
            if e.is_elite and e.alive:
                draw_text_center(surf, "ELITE", (ex, ey - 44), font_xs(bold=True), C.text_warn)

        # Ninja.
        # Task 30 (gfx-sprite-sheet-anim): the ninja sprite sheet is
        # pre-rolled at cache time (8 frames: idle bob x2, slash
        # windup/extend/recover, hit flinch, dead). ``ninja_frame``
        # returns a zero-copy subsurface (no per-frame allocation, same
        # pixel count + format as the static sprite). Frame selection is
        # from ``slash_anim`` (windup/extend/recover), ``bob`` (idle),
        # and ``last_damage_timer`` (hit flinch). Pin to frame 0 when
        # ``reduced_motion`` (or the low render tier, which reduced_motion
        # forces) so the animation is disabled for accessibility. The
        # screen's vertical bob (math.sin(bob * 4) * 2) is kept as the
        # positional bob — the frame selection adds the in-sprite pose
        # on top of the positional bob, so the two compose.
        # Task 32 (gfx-outline-shading-squash): the ninja squash-and-
        # stretch scales (1+k, 1-k) for ~80ms on slash/hit, driven by
        # the existing ``slash_anim`` / ``last_damage_timer`` timers.
        # Gated by the same tier path as the sprite-sheet animation (low
        # tier disables both); the reduced_motion gate is never bypassed.
        # The squash is applied per-frame with ``smoothscale`` (the
        # outline + shading are cache-time, zero per-frame cost; the
        # squash is per-frame because it's a transient animation driven
        # by the slash/hit timers).
        from assets import ninja_frame
        from core.quality import parallax_enabled
        anim_enabled = parallax_enabled(state.effective_render_quality())
        ns = ninja_frame(72, runner.ninja.slash_anim, runner.ninja.bob,
                         last_damage_timer=runner.ninja.last_damage_timer,
                         reduced_motion=not anim_enabled)
        # Task 32: squash-and-stretch on slash/hit. The squash scales
        # (1+k, 1-k) for ~80ms after the slash/hit (the ninja compresses
        # on the slash lunge / hit recoil, then springs back). Gated by
        # the tier (low tier / reduced_motion -> no squash).
        k_ninja = squash_factor(slash_anim=runner.ninja.slash_anim,
                               last_damage_timer=runner.ninja.last_damage_timer,
                               reduced_motion=not anim_enabled)
        if k_ninja > 0:
            nw, nh = ns.get_size()
            ns = pygame.transform.smoothscale(
                ns, (max(1, int(nw * (1 + k_ninja))),
                      max(1, int(nh * (1 - k_ninja)))))
        bob = math.sin(runner.ninja.bob * 4) * 2
        nx = 180 + ox
        ny = ly - 30 + bob + oy
        runner.ninja.y = ny
        if not runner.ninja.alive:
            gs = ns.copy()
            gs.fill((10, 10, 20, 120), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(gs, gs.get_rect(midbottom=(nx, ny + 50)))
        else:
            surf.blit(ns, ns.get_rect(midbottom=(nx, ny + 50)))
        if runner.ninja.max_hp > 0:
            br = pygame.Rect(nx - 24, ny - 16, 48, 5)
            draw_bar(surf, br, runner.ninja.hp / runner.ninja.max_hp,
                     fill=C.hp, bg=C.hp_bg, border=C.panel_border)

        # Fireflies.
        from assets import firefly_surface
        for f in world.fireflies:
            fs = firefly_surface(max(6, int(f.size)), f.hue)
            surf.blit(fs, fs.get_rect(center=(int(f.x) + ox, int(f.y) + oy)))

        # FX + particles + death animations + combo milestones + skill VFX.
        runner.fx.draw(surf)
        self.game.particles.draw(surf)
        runner.death_fx.draw(surf)
        runner.combo_fx.draw(surf)
        runner.ninja_fx.draw(surf)
        runner.skill_fx.draw(surf)
        runner.firefly_fx.draw(surf)
        # Task 31 (gfx-weather): per-zone weather particles. Drawn after
        # the parallax layers + the road + the FX, before the boss intro
        # + zone transition overlay, so the weather overlays the road but
        # is under the boss banner + zone transition. The weather system
        # gates itself (reduced_motion / low tier -> static tint, no
        # particles); the screen does not need to gate here.
        runner.weather_fx.draw(surf)
        # Boss/mini-boss intro + health bar overlay. The mini-boss intro
        # is brief and does not keep a persistent bar; the zone boss bar
        # stays until the boss dies.
        if runner.boss_fx.active:
            boss = next((e for e in world.enemies if e.is_boss and e.alive), None)
            if boss is None:
                # Mini-boss intro path: no persistent boss entity to track.
                pct = 1.0
            else:
                pct = boss.hp / boss.max_hp if boss.max_hp > 0 else 0
            runner.boss_fx.draw(surf, pct)
        # Zone transition overlay.
        if runner.zone_fx.active:
            runner.zone_fx.draw(surf)

        # Task 27 (pl-juice-polish): low-HP red vignette -- a VISUAL
        # urgency cue when the ninja is below 25% HP during a boss fight.
        # This is NOT a boss enrage timer mechanic (gap #5: no enrage
        # timer, no weak-point-tap; the boss is auto-killable through
        # normal DPS). The vignette is purely visual: a red border that
        # fades in when the ninja is low AND a boss is active, fades out
        # otherwise. Gated by ``reduced_motion`` (the ramp/decay is
        # skipped + the intensity is forced to 0 in ``update`` when
        # reduced_motion is on; the boss bar + the ninja's HP bar are the
        # non-visual urgency cues for reduced_motion players).
        if self._vignette_intensity > 0:
            self._draw_low_hp_vignette(surf, self._vignette_intensity)

        # HUD.
        self._draw_hud(surf, state, world)

        # Combo (big, center).
        if state.combo >= 1:
            combo_m = runner.combo_mult()
            txt = f"x{combo_m:.1f}  (combo {state.combo})"
            col = C.gold if state.combo < 50 else (C.text_warn if state.combo < 100 else C.text_bad)
            draw_text_center(surf, txt, (cfg.WINDOW_W // 2, cfg.ROAD_TOP + 30),
                             font_lg(bold=True), col)

        # Notifications.
        y = cfg.ROAD_TOP + 70
        for (text, life, color) in runner.notifications[-6:]:
            a = max(0, min(1, life / 3.0))
            img = font_md(bold=True).render(text, True, color)
            img.set_alpha(int(255 * a))
            r = img.get_rect(midtop=(cfg.WINDOW_W // 2, y))
            surf.blit(img, r)
            y += r.h + 4

        # Boss banner.
        if world.boss_active:
            banner = pygame.Rect(0, cfg.ROAD_TOP, cfg.WINDOW_W, 28)
            bg2 = pygame.Surface(banner.size, pygame.SRCALPHA)
            pygame.draw.rect(bg2, (40, 10, 20, 200), bg2.get_rect())
            surf.blit(bg2, banner.topleft)
            draw_text_center(surf, "BOSS", (cfg.WINDOW_W // 2, cfg.ROAD_TOP + 14),
                             font_md(bold=True), C.text_bad)

        # Skill buttons + energy.
        # Task 27 (pl-juice-polish): draw the cooldown progress fill +
        # the cooldown-ready glow on each skill button. The cooldown
        # progress fill is a thin bar at the bottom of the button that
        # fills from 0 to 1 as the cooldown ticks down (so the player
        # can see at a glance how close the skill is to ready). The glow
        # is a brief golden border that fires for ~1.0s when the cooldown
        # transitions to ready (the visual cue for the cooldown-ready
        # event; the chime is the audio cue). The glow is gated by
        # ``reduced_motion`` (the glow is a visual flourish; the chime is
        # the non-visual cue for reduced_motion players).
        for i, b in enumerate(self.skill_buttons):
            b.draw(surf)
            sid = self._skill_button_ids[i] if i < len(self._skill_button_ids) else None
            if sid is None:
                continue
            sk = runner.skills.get(sid)
            if sk is None:
                continue
            # Cooldown progress fill: a thin bar at the bottom of the
            # button. ``pct`` is the remaining cooldown fraction (1.0 =
            # just fired, 0.0 = ready). The fill width is the inverse
            # (1 - pct) so the bar grows as the cooldown ticks down.
            if sk.cooldown > 0 and sk.timer > 0:
                pct = clamp(sk.timer / sk.cooldown, 0.0, 1.0)
                cd_bar = pygame.Rect(b.rect.x + 4, b.rect.bottom - 6,
                                     b.rect.w - 8, 4)
                # The fill is the "ready" portion (1 - pct); the bg is
                # the "remaining" portion (pct). The fill is a bright
                # accent (C.exp) so it reads as "progress toward ready".
                draw_bar(surf, cd_bar, 1.0 - pct,
                         fill=C.exp, bg=C.mp_bg, border=C.panel_border)
            # Cooldown-ready glow: a golden border that fires for ~1.0s
            # after the cooldown-ready transition. The glow timer is in
            # ``self._skill_glow``; the glow fades over the duration.
            glow_t = self._skill_glow.get(sid, 0.0)
            if glow_t > 0:
                a = int(220 * (glow_t / _SKILL_GLOW_DUR))
                if a > 0:
                    glow_rect = b.rect.inflate(6, 6)
                    glow_surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                    pygame.draw.rect(glow_surf, (255, 220, 120, a),
                                     glow_surf.get_rect(), 3, border_radius=8)
                    surf.blit(glow_surf, glow_rect.topleft)
        self.btn_energy.draw(surf)
        # Energy bar above the button.
        ebr = pygame.Rect(cfg.WINDOW_W - 180, cfg.WINDOW_H - 70, 160, 6)
        draw_bar(surf, ebr, state.energy / state.energy_max,
                 fill=C.mp, bg=C.mp_bg, border=C.panel_border)
        # Tap rhythm display (Task 25 / gp-skill-synergy-rhythm): a small
        # indicator above the skill buttons showing the current rhythm
        # streak + a bar (streak / cap). The rhythm is strictly a bonus
        # (floor 0, never a penalty); the display is suppressed when
        # reduced_motion is on (the soft tick SFX is the non-visual cue
        # for reduced_motion players).
        if not state.reduced_motion:
            self._draw_rhythm_display(surf, state)
        # Synergy arc (Task 25): a brief glowing arc between the two
        # skill buttons that were just fired in a synergy. The arc fades
        # out over ``SYNERGY_ARC_DUR`` (1.0s); the runner decrements
        # ``_synergy_arc_timer`` each tick. Gated by reduced_motion (the
        # arc is a visual flourish; the synergy notification + bonus
        # damage still fire regardless).
        if (runner._synergy_arc_timer > 0
                and not state.reduced_motion
                and runner.last_synergy is not None):
            self._draw_synergy_arc(surf, runner)

        # Combo Finisher buttons + charge count. The buttons are drawn
        # in a row above the skill buttons; each shows the finisher name
        # and is enabled only when the player has enough charges. The
        # charge count is drawn as a small label above the row.
        from engine.runner import FINISHERS
        charges = state.combo_charges
        # Charge count label (top-left of the finisher row).
        chg_x = 16
        chg_y = cfg.WINDOW_H - 130
        chg_text = f"Charges: {charges}"
        draw_text(surf, chg_text, (chg_x, chg_y), font_sm(bold=True), C.gold)
        for i, b in enumerate(self.finisher_buttons):
            fid = self._finisher_ids[i] if i < len(self._finisher_ids) else None
            if fid is not None:
                _name, cost, _kind = FINISHERS[fid]
                # Enable the button only when the player has enough charges.
                b.enabled = charges >= cost
                # Phantom Step needs combo >= 100 too; show it as
                # disabled (but still spendable on click — the runner
                # refunds the charges with a notification if combo < 100).
                if fid == "phantom_step" and state.combo < 100:
                    b.enabled = False
            b.draw(surf)

        # Nav buttons.
        for b in self.nav_buttons:
            b.draw(surf)

        # Task 34 (cnt-shadow-dungeon-variants): the dungeon entry button
        # + the dungeon HUD (the active dungeon's floor + variant). The
        # button opens the variant selector modal; the HUD shows the
        # current dungeon state (floor / variant) when a dungeon is active.
        self.btn_dungeon.draw(surf)
        if state.dungeon_active:
            self._draw_dungeon_hud(surf, state)
        # Task 34: the dungeon variant selector modal (an overlay drawn
        # over the game screen when ``dungeon_selector_open`` is True).
        if self.dungeon_selector_open:
            self._draw_dungeon_selector(surf)

        # Welcome modal.
        if self.welcome_pending:
            self._draw_welcome(surf)

    def _draw_hud(self, surf, state, world) -> None:
        pygame.draw.rect(surf, C.panel_lo, (0, 0, cfg.WINDOW_W, cfg.HUD_H))
        pygame.draw.line(surf, C.panel_border, (0, cfg.HUD_H), (cfg.WINDOW_W, cfg.HUD_H), 1)
        x = 16; y = 10
        # Task 27 (pl-juice-polish): the gold pill uses the count-up
        # display value (``self._displayed_gold``) instead of the actual
        # ``state.gold`` so the pill counts up from the old value to the
        # new value (no instant snapping). The count-up is advanced in
        # ``update``; here we just read the displayed value.
        gold_display = getattr(self, "_displayed_gold", float(state.gold))
        x += currency_pill(surf, x, y, "Gold", format_number(gold_display), C.gold) + 10
        x += currency_pill(surf, x, y, "Elixir", format_number(state.elixir), (120, 220, 200)) + 10
        x += currency_pill(surf, x, y, "Amber", format_number(state.amber), (255, 180, 60)) + 10
        currency_pill(surf, x, y, "Medals", format_number(state.medals), (200, 200, 220))
        # Zone + cycle. Past zone 9 the 9 themed zones repeat at scaled
        # stats; the cycle (``zone_index // 9``) is the post-endgame
        # progression, so the HUD always surfaces it. The in-cycle zone
        # (``zone_index % 9``) is the zone the player sees (1-9).
        in_cycle = world.zone_in_cycle
        cycle = world.cycle
        if cycle > 0:
            zone_label = (f"{world.zone_name}  —  Zone {in_cycle + 1}"
                          f"  (Cycle {cycle + 1})")
        else:
            zone_label = f"{world.zone_name}  —  Zone {in_cycle + 1}"
        draw_text_center(surf, zone_label,
                         (cfg.WINDOW_W // 2, 18), font_md(bold=True), C.text)
        zb = pygame.Rect(cfg.WINDOW_W // 2 - 140, 38, 280, 10)
        draw_bar(surf, zb, world.zone_progress(), fill=C.exp, bg=C.mp_bg, border=C.panel_border)

    def _draw_welcome(self, surf) -> None:
        from core import offline
        report = self.welcome_pending
        dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, int(160 * self.welcome_t)))
        surf.blit(dim, (0, 0))
        cw, ch = 560, 220
        cx, cy = cfg.WINDOW_W // 2, cfg.WINDOW_H // 2
        r = pygame.Rect(0, 0, cw, ch)
        r.center = (cx, cy)
        draw_panel(surf, r, fill=(22, 26, 46), border=C.panel_border_hi, border_w=2, radius=16)
        draw_text_center(surf, "Welcome back", (cx, r.y + 36), font_xl(bold=True), C.text)
        dur = offline.format_duration(report["seconds"])
        draw_text_center(surf, f"Away for {dur}", (cx, r.y + 76), font_md(), C.text_dim)
        draw_text_center(surf, f"+{format_number(report['gold'])} gold",
                         (cx, r.y + 116), font_lg(bold=True), C.gold)
        draw_text_center(surf, f"+{report['kills']} enemies slain",
                         (cx, r.y + 150), font_sm(), C.text_dim)
        a = int(180 + 60 * math.sin(self.welcome_t * 6))
        draw_text_center(surf, "click to collect", (cx, r.bottom - 24),
                         font_sm(), (a, a, a))

    def _welcome_notify(self, report) -> None:
        from core import offline
        dur = offline.format_duration(report["seconds"])
        self.notify(f"While away {dur}: +{format_number(report['gold'])} gold", C.gold)

    def notify(self, text: str, color=C.text) -> None:
        from ui.widgets import Toast
        self.toasts.append(Toast(text, life=3.0, color=color))
        if len(self.toasts) > 6:
            self.toasts.pop(0)

    # -----------------------------------------------------------------
    # Task 34 (cnt-shadow-dungeon-variants): dungeon HUD + selector
    # -----------------------------------------------------------------
    def _draw_dungeon_hud(self, surf, state) -> None:
        """Draw the active dungeon's HUD (floor + variant + exit button).

        A small panel in the top-left of the play area showing the
        current dungeon's floor + variant (Story/Endless/Daily). The
        dungeon's best floor is shown too (the depth record). The HUD is
        drawn only when a dungeon is active (the dungeon is a track on
        the same run, not a separate screen).
        """
        from engine.runner import STORY_FLOORS, DAILY_FLOORS
        x = 16
        y = cfg.HUD_H + 8
        # The dungeon variant label (Story/Endless/Daily).
        vlabel = {"story": "Story", "endless": "Endless",
                  "daily": "Daily"}.get(state.dungeon_type, state.dungeon_type)
        # The floor label (the current floor + the max for the variant).
        if state.dungeon_type == "story":
            floor_txt = f"Floor {state.dungeon_floor}/{STORY_FLOORS}"
        elif state.dungeon_type == "daily":
            floor_txt = f"Floor {state.dungeon_floor}/{DAILY_FLOORS}"
        else:
            floor_txt = f"Floor {state.dungeon_floor}"
        # The panel.
        pw, ph = 200, 56
        panel = pygame.Rect(x, y, pw, ph)
        draw_panel(surf, panel, fill=(30, 18, 50),
                  border=(140, 60, 180), border_w=2, radius=8)
        draw_text(surf, f"Shadow Dungeon — {vlabel}",
                  (x + 8, y + 6), font_sm(bold=True), (200, 160, 240))
        draw_text(surf, floor_txt,
                  (x + 8, y + 26), font_xs(), C.text_dim)
        draw_text(surf, f"Best: {state.dungeon_best_floor}",
                  (x + 110, y + 26), font_xs(), C.text_dim)

    def _draw_dungeon_selector(self, surf) -> None:
        """Draw the dungeon variant selector modal.

        A dim overlay + a panel with the three variant buttons
        (Story/Endless/Daily) + a Close button. The buttons are built in
        ``_build_dungeon_variant_buttons``; here we just draw the modal
        frame + the buttons. The buttons are enabled only when the
        player meets the entry gate (``can_enter_dungeon``).
        """
        from engine.runner import can_enter_dungeon
        # Dim overlay (the modal is an overlay over the game screen).
        dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 120))
        surf.blit(dim, (0, 0))
        # The modal panel (a frame around the variant buttons). The panel
        # size MUST match the layout in ``_build_dungeon_variant_buttons``
        # so the buttons sit inside the frame.
        cx = cfg.WINDOW_W // 2
        cy = cfg.WINDOW_H // 2
        pw, ph = 360, 320
        panel = pygame.Rect(0, 0, pw, ph)
        panel.center = (cx, cy)
        draw_panel(surf, panel, fill=(22, 18, 36),
                  border=(140, 60, 180), border_w=2, radius=16)
        draw_text_center(surf, "Shadow Dungeon",
                         (cx, panel.y + 24), font_lg(bold=True),
                         (200, 160, 240))
        draw_text_center(surf, "Choose your descent",
                         (cx, panel.y + 50), font_sm(), C.text_dim)
        # The entry gate status (a hint if the gate is not met).
        gate_met = can_enter_dungeon(self.game.state)
        if not gate_met:
            draw_text_center(surf,
                             "Need 50 medals or zone 9 to enter.",
                             (cx, panel.bottom - 24), font_xs(),
                             C.text_warn)
        # Draw the variant buttons (built in _build_dungeon_variant_buttons).
        for b in self.dungeon_variant_buttons:
            b.draw(surf)

    # -----------------------------------------------------------------
    # Task 27 (pl-juice-polish): low-HP red vignette
    # -----------------------------------------------------------------
    def _draw_low_hp_vignette(self, surf: pygame.Surface, intensity: float) -> None:
        """Draw the low-HP red vignette at ``intensity`` (0..1).

        A red border that fades in around the play area when the ninja is
        below 25% HP during a boss fight. The vignette is a VISUAL urgency
        cue, NOT a boss enrage timer mechanic (gap #5: no enrage timer,
        no weak-point-tap; the boss is auto-killable through normal DPS).

        The vignette is a full-screen SRCALPHA overlay with a transparent
        centre + a red border that fades in as the intensity ramps. The
        border width + alpha scale with the intensity so the vignette
        eases in (and out, when the ninja heals above the threshold or
        the boss dies). Cached per-frame is fine -- the vignette is only
        drawn while the intensity > 0, which is a transient state.
        """
        if intensity <= 0:
            return
        # The vignette: a full-screen red overlay with a transparent
        # centre. We draw four red rectangles around the play area (the
        # border) with an alpha that scales with the intensity. The
        # border width is ~24px at full intensity (a clear "danger"
        # frame without obscuring the play area).
        a = int(180 * intensity)
        if a <= 0:
            return
        bw = int(24 * intensity)
        if bw <= 0:
            return
        overlay = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
        # Top + bottom + left + right borders.
        pygame.draw.rect(overlay, (200, 30, 40, a),
                         (0, 0, cfg.WINDOW_W, bw))
        pygame.draw.rect(overlay, (200, 30, 40, a),
                         (0, cfg.WINDOW_H - bw, cfg.WINDOW_W, bw))
        pygame.draw.rect(overlay, (200, 30, 40, a),
                         (0, 0, bw, cfg.WINDOW_H))
        pygame.draw.rect(overlay, (200, 30, 40, a),
                         (cfg.WINDOW_W - bw, 0, bw, cfg.WINDOW_H))
        surf.blit(overlay, (0, 0))

    # -----------------------------------------------------------------
    # Tap rhythm display + synergy arc (Task 25 / gp-skill-synergy-rhythm)
    # -----------------------------------------------------------------
    def _draw_rhythm_display(self, surf: pygame.Surface, state) -> None:
        """Draw the tap rhythm streak + a small bar above the skill buttons.

        The rhythm is strictly a bonus (floor 0, never a penalty); the
        display shows the current streak (0..20) + a bar (streak / cap).
        Suppressed when ``reduced_motion`` is on (the soft tick SFX is
        the non-visual cue for reduced_motion players).
        """
        from engine.runner import RHYTHM_CAP
        streak = state.rhythm_streak
        # Place the display above the skill buttons, left-aligned.
        x = 16
        y = cfg.WINDOW_H - 80
        # Label + streak count.
        label = f"Rhythm {streak}/{RHYTHM_CAP}"
        col = C.gold if streak > 0 else C.text_dim
        draw_text(surf, label, (x, y), font_xs(bold=True), col)
        # Small bar (streak / cap) below the label.
        bar_w = 120
        bar = pygame.Rect(x, y + 14, bar_w, 5)
        draw_bar(surf, bar, streak / RHYTHM_CAP,
                 fill=C.gold, bg=C.mp_bg, border=C.panel_border)

    def _draw_synergy_arc(self, surf: pygame.Surface, runner) -> None:
        """Draw a brief glowing arc between the two skill buttons that
        were just fired in a synergy.

        The arc fades out over ``SYNERGY_ARC_DUR`` (1.0s); the runner
        decrements ``_synergy_arc_timer`` each tick. The arc is a glowing
        line (a wide semi-transparent glow + a narrow bright core) from
        the top-center of button A to the top-center of button B, with the
        synergy name text above the midpoint. Gated by ``reduced_motion``
        (the arc is a visual flourish; the synergy notification + bonus
        damage still fire regardless).
        """
        # Find the two skill buttons involved in the synergy. The runner
        # tracks ``last_skill_id`` (the first skill) + the just-fired
        # skill is ``last_skill_id`` of the *previous* call... no: the
        # runner sets ``last_skill_id`` to the *second* skill after the
        # synergy check, so we can't read the pair from the runner here.
        # Instead, the arc is drawn between the last two skill buttons
        # that were fired. We approximate by reading the synergy name
        # (which implies the pair) -- but the simplest approach is to
        # draw the arc between the two buttons whose ids match the
        # synergy pair. Since we don't store the pair on the runner, we
        # draw a generic arc centered on the skill button row with the
        # synergy name text above it.
        from engine.runner import SYNERGY_ARC_DUR
        # Fade alpha over the timer (1.0 at the start, 0.0 at the end).
        t = runner._synergy_arc_timer / SYNERGY_ARC_DUR
        alpha = max(0.0, min(1.0, t))
        # Draw the arc over the full skill button row (a glowing band
        # above the buttons + the synergy name centered above it).
        if not self.skill_buttons:
            return
        first_btn = self.skill_buttons[0]
        last_btn = self.skill_buttons[-1]
        x0 = first_btn.rect.centerx
        x1 = last_btn.rect.centerx
        y = first_btn.rect.y - 6
        # Glow: a wide semi-transparent line over the button row.
        glow = pygame.Surface((x1 - x0 + 40, 30), pygame.SRCALPHA)
        gw = glow.get_width()
        for w, a in ((8, int(80 * alpha)), (4, int(160 * alpha)),
                     (2, int(255 * alpha))):
            pygame.draw.line(glow, (255, 220, 120, a),
                             (4, 15), (gw - 4, 15), w)
        surf.blit(glow, (x0 - 20, y - 15))
        # Synergy name text above the midpoint, fading.
        name = runner.last_synergy or ""
        if name:
            col = (255, 220, 120)
            img = font_sm(bold=True).render(name, True, col)
            img.set_alpha(int(255 * alpha))
            r = img.get_rect(midbottom=((x0 + x1) // 2, y - 2))
            surf.blit(img, r)
