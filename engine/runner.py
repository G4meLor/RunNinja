"""Runner: the top-level simulation driver for Tap Ninja.

Ties the world, ninja, combat, fireflies, active skills, and energy
together.  Owns the FX layer and routes kills to loot + combo + zone
progression.  Exposes a single ``update(dt)`` the main loop calls.
"""
from __future__ import annotations

import math
import time

import config as cfg
from core.state import GameState
from utils import rng
from core.bonuses import aggregate_bonuses
from core.quests import (maybe_refresh_dailies, update_daily_progress,
                         check_achievements, award_boss_token,
                         maybe_refresh_weeklies, update_weekly_progress,
                         update_chapter_progress)
from engine.ninja import Ninja, make_ninja, compute_ninja_stats
from engine.enemy import (Enemy, tick_combat, tap as tap_enemy, nearest_enemy,
                          PARTY_X, spawn_enemy, spawn_boss)
from engine.firefly import Firefly, update_fireflies, catch_firefly
from engine.skills import ActiveSkill, make_skill, tick_skill, can_fire, fire as fire_skill
from engine.skills import SYNERGIES, SYNERGY_WINDOW, SYNERGY_DMG_MULT
from engine.world import World
from engine.eventbus import EventBus
from engine.fx import FXLayer
from engine.death_fx import DeathFxSystem
from engine.combo_fx import ComboFxSystem, MILESTONES as _COMBO_MILESTONES
from engine.ninja_fx import NinjaFxSystem
from engine.skill_fx import SkillFxSystem
from engine.zone_fx import ZoneFxSystem
from engine.boss_fx import BossFxSystem
from engine.firefly_fx import FireflyFxSystem
from engine.weather_fx import WeatherFXSystem


COMBO_WINDOW = 3.0       # seconds before combo decays
COMBO_MULT_CAP = 3.0     # asymptotic ceiling for the combo multiplier
COMBO_GRACE = 1.5        # seconds combo_timer can go negative before reset

# Cleave (Task 16): the overkill ratio that triggers a cleave. A tap
# that deals more than ``CLEAVE_OVERKILL_RATIO`` times the target's
# pre-tap HP (a massive overkill, not just a kill) chain-clears the
# next ``cleave_count()`` enemies. With RATIO = 10, a tap that one-
# shots a 1 HP enemy with 10k damage triggers the cleave; a tap that
# exactly kills (dmg == HP) does NOT. Tuned so the cleave fires on a
# real "massive overkill" (the late-ascension tap_damage >> enemy HP
# scenario the feature is for), not on every kill.
CLEAVE_OVERKILL_RATIO = 10.0

# Combo Finishers: a charge is banked when the running combo crosses a
# ``combo_fx.MILESTONES`` threshold (25/50/100/200 — piggyback on the
# existing dict, which also has 10). Charges persist through the decay
# window and are only lost when the combo fully resets (after the grace
# window). Each finisher spends charges; finisher damage is a FIXED
# multiple of ``tap_damage`` with its own cap (``MAX_FINISHER_MULT``),
# NOT multiplicative with ``combo_mult`` — so a finisher never scales
# with the combo multiplier (the cap is the whole point: a fixed burst
# the player banks charges for, not another combo-scaled nuke).
MAX_FINISHER_MULT = 5.0  # cap on tap_damage multiplier for finisher damage

# Finisher definitions: id -> (name, cost in charges, kind).
# ``kind`` selects the effect branch in ``activate_finisher``.
#   thousand_cuts    — line AOE, 1 charge, dmg = tap_damage * 5 (capped)
#   phantom_step     — boss-kill if combo >= 100, 2 charges
#   mirage           — shadow clones, 1 charge
#   executioner_edge — guaranteed-crit taps, 1 charge
# Bosses are auto-killable WITHOUT phantom_step (the ninja's auto-attack
# kills them normally); phantom_step is a convenience, never a gate on
# progression.
FINISHERS: dict[str, tuple[str, int, str]] = {
    "thousand_cuts":    ("Thousand Cuts",    1, "aoe"),
    "phantom_step":     ("Phantom Step",     2, "boss_kill"),
    "mirage":           ("Mirage",           1, "clones"),
    "executioner_edge": ("Executioner's Edge", 1, "crit_buff"),
}

# ---------------------------------------------------------------------------
# Godai fusion (Task 21 / gp-godai-fusion)
# ---------------------------------------------------------------------------
# 4 dual-element fusion effects on a 30s cooldown. A fusion fires when both
# elements of a pair are unlocked (in ``state.skill_tree``) AND the
# attuned element matches one of the pair. The fusion deals a burst of
# AOE damage to all alive enemies (a flat multiple of ``tap_damage``,
# NOT multiplicative with ``combo_mult`` — same cap philosophy as the
# finishers). The fusion is the single elemental combat system (the
# zone-environmental-hazards proposal is NOT implemented).
#
# The 4 fusions from the brief (each is a distinct pair):
#   void + fire  -> "inferno"  (the burning void)
#   wind + water -> "tempest"  (the storm)
#   fire + water -> "steam"    (the scalding burst)
#   void + wind  -> "vacuum"   (the suffocating pull)
FUSIONS: dict[tuple[str, str], str] = {
    ("void", "fire"):  "inferno",
    ("wind", "water"): "tempest",
    ("fire", "water"): "steam",
    ("void", "wind"):  "vacuum",
}
# The fusion fires on a 30s cooldown. ``_fusion_timer`` counts down; when
# it hits 0 the fusion fires (if a pair is unlocked + the attuned element
# matches) and the timer resets to the cooldown.
FUSION_COOLDOWN: float = 30.0
# Fusion damage = tap_damage * FUSION_DMG_MULT (capped, NOT multiplicative
# with combo_mult). Tuned so a fusion is a meaningful burst but not a
# replacement for the auto-attack loop.
FUSION_DMG_MULT: float = 8.0
# ---------------------------------------------------------------------------
# Tap rhythm (Task 25 / gp-skill-synergy-rhythm)
# ---------------------------------------------------------------------------
# The median of the last 5 tap intervals in the 0.35-0.55s window builds
# ``state.rhythm_streak`` (cap 20), +2.5% tap damage per level. Rhythm is
# strictly a BONUS (floor 0, never a penalty) -- motor-impaired players
# aren't punished. The rolling tap timestamps are kept here (separate from
# the fatigue window in ``_tap_timestamps``, which only spans 1.0s; the
# rhythm window spans up to ~2.5s at 0.5s intervals so the lists diverge).
RHYTHM_WINDOW_SIZE: int = 5          # taps to keep for rhythm evaluation
RHYTHM_MIN_INTERVAL: float = 0.35    # seconds; below this = too fast (reset)
RHYTHM_MAX_INTERVAL: float = 0.55    # seconds; above this = too slow (reset)
RHYTHM_CAP: int = 20                 # max streak levels
RHYTHM_BONUS_PER_LEVEL: float = 0.025  # +2.5% tap damage per level
# The synergy arc display lifetime (seconds). The screen draws a glowing
# arc between the two skill buttons while this timer is > 0.
SYNERGY_ARC_DUR: float = 1.0
# Farm-when-stuck (Task 28 / pl-automation): when stuck on a boss for this
# many seconds (with ``auto_progress`` unlocked), the runner enters farm
# mode -- the road keeps earning gold (from buildings + kills) instead of
# dead-ending. Tuned so a boss that takes > 30s to kill triggers farm mode
# (the player is "stuck"). The farm mode is a flag the UI can read (to show
# "Farming..." instead of "Stuck!"). The gold earning already happens
# through the normal tick (buildings + kills); farm mode is the explicit
# signal that the road is farming while stuck, not a separate earning path.
FARM_STUCK_THRESHOLD: float = 30.0
# The element node id -> element name (the unlock gate for a fusion pair).
_GODAI_ELEMENT_NODES: dict[str, str] = {
    "godai_void":  "void",
    "godai_wind":  "wind",
    "godai_fire":  "fire",
    "godai_water": "water",
}
# The 4-cycle: each element is 2x strong against the next in the cycle.
# Used by ``auto_attune_element`` to pick the best element for a zone.
_ELEMENT_ADVANTAGE: dict[str, str] = {
    "void":  "wind",   # void 2x vs wind
    "wind":  "fire",   # wind 2x vs fire
    "fire":  "water",  # fire 2x vs water
    "water": "void",   # water 2x vs void
}


class Runner:
    def __init__(self, state: GameState) -> None:
        self.state = state
        self.world = World()
        self.world.zone_index = state.zone_index
        self.world.zone_distance = state.zone_distance
        self.world.total_distance = state.total_distance
        self.ninja = make_ninja(state)
        self.fx = FXLayer()
        self.death_fx = DeathFxSystem()
        self.combo_fx = ComboFxSystem()
        # Wire the combo FX reduced-motion gate from state (the same way
        # death_fx is wired by main.py; set here so tests that construct
        # a Runner directly without main.py still get the gate).
        self.combo_fx.reduced_motion = state.reduced_motion
        self.ninja_fx = NinjaFxSystem()
        self.skill_fx = SkillFxSystem()
        self.zone_fx = ZoneFxSystem()
        self.boss_fx = BossFxSystem()
        self.firefly_fx = FireflyFxSystem()
        # Task 31 (gfx-weather): per-zone weather particles. The system
        # spawns zone-appropriate particles from the top edge (rain in
        # Bamboo, ash in Volcano, snow in Sky, void drift in Void) using
        # ParticleSystem2 presets. Pooled (no per-frame allocations).
        # Capped per weather type (rain <=120, snow <=60, ash/drift <=80).
        # Under reduced_motion OR the low render tier, falls back to a
        # static tint overlay (no particles). The screen reads the current
        # zone's ``weather`` key (added by Task 31) via the world's zone
        # dict and calls ``set_weather`` on zone change.
        self.weather_fx = WeatherFXSystem()
        # Active skills (only those unlocked).
        self.skills: dict[str, ActiveSkill] = {}
        self._refresh_skills()
        # Runner-owned EventBus: engine modules emit events; the runner
        # subscribes the FX systems. Replaces the module-global FX
        # callbacks (kept as deprecated aliases that forward to the bus).
        self.bus = EventBus()
        # Executioner's Edge finisher: a transient timer that, while > 0,
        # makes every tap/auto-attack a guaranteed crit. Decremented in
        # ``update``. See ``activate_finisher("executioner_edge")``.
        self._executioner_timer: float = 0.0
        # Godai fusion timer (Task 21): counts down from FUSION_COOLDOWN;
        # when it hits 0 the fusion fires (if a pair is unlocked + the
        # attuned element matches) and the timer resets. Starts at 0 so
        # the first fusion fires as soon as the conditions are met (no
        # 30s wait on a fresh run).
        self._fusion_timer: float = 0.0
        # Tap fatigue (Task 24 / gp-tap-auto-rebalance): anti-macro for
        # active tapping. A rolling list of recent tap timestamps (epoch
        # seconds); ``tap_fatigue_mult`` counts the taps in the last
        # TAP_FATIGUE_WINDOW seconds and applies a per-tap penalty above
        # the threshold, floored at TAP_FATIGUE_FLOOR. The window is 1.0s
        # so a macro that fires 100 taps/s does not trivialize the game;
        # the floor (0.3x) keeps tap meaningful even under heavy fatigue.
        self._tap_timestamps: list[float] = []
        # Tap rhythm (Task 25 / gp-skill-synergy-rhythm): a rolling list of
        # the last 5 tap timestamps (epoch seconds) used to compute the
        # median interval. Separate from ``_tap_timestamps`` (the fatigue
        # window) because the rhythm window spans up to ~2.5s at 0.5s
        # intervals while the fatigue window is 1.0s.
        self._rhythm_taps: list[float] = []
        # Skill synergies (Task 25 / gp-skill-synergy-rhythm): track the
        # last skill fired + when, so the next activate_skill can check
        # whether the pair matches a synergy within the 2s window.
        # ``last_synergy`` is the name of the last synergy that fired (or
        # None) -- the UI reads it + ``_synergy_arc_timer`` to draw the arc.
        self.last_skill_id: str | None = None
        self.last_skill_time: float = 0.0
        self.last_synergy: str | None = None
        self._synergy_arc_timer: float = 0.0
        # Task 28 / pl-automation: farm-when-stuck tracking.
        # ``_boss_stuck_timer`` counts how long the current boss has been
        # alive (reset when no boss is active). When the timer exceeds
        # ``FARM_STUCK_THRESHOLD`` (with ``auto_progress`` unlocked), the
        # runner enters ``farm_mode`` -- the road keeps earning gold
        # (from buildings + kills) instead of dead-ending. ``farm_mode``
        # is a flag the UI can read (to show "Farming..." instead of
        # "Stuck!").
        self._boss_stuck_timer: float = 0.0
        self.farm_mode: bool = False
        self.bus.on("enemy_dmg", self._on_enemy_dmg)
        self.bus.on("ninja_dmg", self._on_ninja_dmg)
        self.bus.on("boss_spawn", self._on_boss_spawn)
        self.bus.on("miniboss_spawn", self._on_miniboss_spawn)
        self.bus.on("boss_phase", self._on_boss_phase)
        self.bus.on("firefly_spawn", self.firefly_fx.on_spawn)
        # Wire the bus into the engine modules.
        from engine import enemy as _e
        _e.set_event_bus(self.bus)
        self.world.set_event_bus(self.bus)
        # Deprecated aliases: keep the module globals for one release so
        # any caller that still sets them directly keeps working. The
        # bus is the primary path; these forward to it.
        _e.on_enemy_dmg = lambda *a, **k: self.bus.emit("enemy_dmg", *a, **k)
        _e.on_ninja_dmg = lambda *a, **k: self.bus.emit("ninja_dmg", *a, **k)
        self.world.on_boss_spawn = lambda *a, **k: self.bus.emit("boss_spawn", *a, **k)
        self.world.on_miniboss_spawn = lambda *a, **k: self.bus.emit("miniboss_spawn", *a, **k)
        self.world.on_firefly_spawn = lambda *a, **k: self.bus.emit("firefly_spawn", *a, **k)
        # Notifications for the UI.
        self.notifications: list[tuple[str, float, tuple]] = []
        self.last_loot: dict = {}

    def _refresh_skills(self) -> None:
        """Rebuild the active-skill set from unlocked skill-tree nodes.

        Task 22: the ``skill_cd`` run upgrade reduces the effective
        cooldown for all unlocked skills. The cooldown is recomputed
        here (the base ``SKILL_DEFS`` cooldown * the multiplier) so the
        reduction applies as long as the skill is unlocked. The upgrade
        resets on ascension.
        """
        self.skills.clear()
        cd_mult = self.skill_cooldown_mult()
        for sid in ("kunai", "shuriken", "rope", "speed"):
            unlock_node = {
                "kunai": "ab_root", "shuriken": "ab_shuriken",
                "rope": "ab_rope", "speed": "ab_speed",
            }[sid]
            if unlock_node in self.state.skill_tree:
                sk = make_skill(sid)
                sk.cooldown = sk.cooldown * cd_mult
                self.skills[sid] = sk

    # -----------------------------------------------------------------
    # Task 29 (gfx-parallax): scroll accumulator speed
    # -----------------------------------------------------------------
    def scroll_speed(self) -> float:
        """The base scroll speed for the parallax layers (pixels/second).

        Returns 90.0 normally, 180.0 (2x) when Auto Katana
        (``energy_active``) is engaged — the brief calls for the parallax
        to visibly accelerate 2x during Auto Katana. The screen reads
        this to advance its ``scroll_accumulator`` each frame; the
        accumulator is pinned to 0 when ``reduced_motion`` is on or the
        render tier is low (see ``ui.screen_game``).
        """
        base = 90.0
        if self.state.energy_active:
            base *= 2.0
        return base

    # -----------------------------------------------------------------
    # FX callbacks
    # -----------------------------------------------------------------
    def _on_enemy_dmg(self, x, y, amount, *, is_crit=False, is_boss=False) -> None:
        self.fx.damage(x, y, amount, crit=is_crit)
        # Ninja slash arc on every hit (visual feedback for tap + auto).
        self.ninja_fx.on_slash(self.ninja, x, y, is_crit=is_crit)

    def _on_ninja_dmg(self, x, y, amount) -> None:
        self.fx.damage(x, y - 24, amount, crit=False)

    def _on_boss_spawn(self, name: str, hue: int) -> None:
        """Trigger boss intro FX when the world spawns a boss."""
        self.boss_fx.start(name, hue)

    def _on_miniboss_spawn(self, name: str, hue: int) -> None:
        """Trigger a smaller boss-FX intro for a mini-boss.

        The mini-boss reuses the boss intro system but with a shorter,
        less-dramatic reveal (the brief calls for "a brief" intro).
        """
        self.boss_fx.start_miniboss(name, hue)

    def _on_boss_phase(self, name: str, hue: int,
                       old_phase: int, new_phase: int) -> None:
        """Trigger phase-transition visuals when the boss phase changes.

        The boss's phase is DERIVED from HP each tick (no state machine);
        when it crosses a milestone (75/50/25%, i.e. phase 1/2/3), the
        enemy module emits ``boss_phase`` on the bus and this handler
        fires the ~0.8s nameplate flash + banner + hue shift (no pause).
        """
        self.boss_fx.start_phase(name, hue, new_phase)

    # -----------------------------------------------------------------
    # Combo
    # -----------------------------------------------------------------
    def combo_mult(self) -> float:
        c = self.state.combo
        tau = cfg.COMBO_TAU - _upgrade_val(self.state, "combo_step")
        # Task 22: the combo_step_pct skill-tree bonus reduces tau further
        # (a faster combo ramp), capped at the same 5.0 floor so the ramp
        # never becomes instant. The bonus is permanent (skill-tree); the
        # run upgrade resets on ascension.
        evo = aggregate_bonuses(self.state)
        tau -= evo.get("combo_step_pct", 0.0) * cfg.COMBO_TAU
        tau = max(5.0, tau)  # floor so the ramp never becomes instant
        # Asymptotic approach to the multiplier ceiling: at c=0 the
        # multiplier is 1.0; as c -> inf it approaches COMBO_MULT_CAP.
        # The bonus above the 1.0x base is (COMBO_MULT_CAP - 1.0), so the
        # total multiplier is structurally capped at COMBO_MULT_CAP.
        return 1.0 + (COMBO_MULT_CAP - 1.0) * (1.0 - math.exp(-c / tau))

    # -----------------------------------------------------------------
    # Godai attunement + fusion (Task 21 / gp-godai-fusion)
    # -----------------------------------------------------------------
    def auto_attune_element(self) -> str:
        """The best Godai element to attune for the current zone.

        Returns the element that is 2x strong against the current zone's
        dominant enemy element (the 4-cycle). Returns "none" when:
          * the ``godai_auto_attune`` node is NOT unlocked (the idle floor
            — no automatic attunement; the player can still set
            ``state.attuned_element`` manually if they want), or
          * the zone's enemies are all "none" (no element to beat), or
          * no element is 2x against the zone's dominant element.

        The pick is the COMPLEMENT to the 4 element nodes (the unlock
        gate for the fusion layer), NOT a competing system: the element
        nodes still grant their flat +15% stat boosts; the auto-attune
        layer on top.
        """
        if "godai_auto_attune" not in self.state.skill_tree:
            return "none"
        # Find the dominant enemy element in the current zone (the most
        # common non-"none" element among the zone's enemies). If all
        # enemies are "none", there's nothing to beat -> "none".
        from data.enemies import zone_by_index
        zone = zone_by_index(self.state.zone_index)
        counts: dict[str, int] = {}
        for e in zone["enemies"]:
            if e.element != "none":
                counts[e.element] = counts.get(e.element, 0) + 1
        if not counts:
            return "none"
        dominant = max(counts, key=counts.get)
        # Pick the element that is 2x against the dominant element (the
        # reverse of the 4-cycle: if dominant is "fire", the element 2x
        # against fire is "water" — water > fire in the cycle).
        for attacker, defender in _ELEMENT_ADVANTAGE.items():
            if defender == dominant:
                return attacker
        return "none"

    def _unlocked_elements(self) -> set[str]:
        """The set of Godai elements unlocked in the skill tree."""
        return {name for nid, name in _GODAI_ELEMENT_NODES.items()
                if nid in self.state.skill_tree}

    def _active_fusion(self) -> str | None:
        """The fusion to fire this tick, or None.

        A fusion fires when both elements of a pair are unlocked (in
        ``state.skill_tree``). The attuned element does NOT need to match
        the pair — the fusion is a reward for unlocking both elements; the
        attuned element affects the damage via ``element_mult`` (the
        fusion respects the type chart). Returns the fusion name (e.g.
        "inferno") or None if no pair is fully unlocked.
        """
        unlocked = self._unlocked_elements()
        for (a, b), name in FUSIONS.items():
            if a in unlocked and b in unlocked:
                return name
        return None

    def _tick_fusion(self, dt: float) -> None:
        """Advance the fusion timer and fire the fusion when it's ready.

        Called from ``update`` once per tick. Decrements ``_fusion_timer``
        by ``dt``; when it hits 0, fires the active fusion (if any) and
        resets the timer to ``FUSION_COOLDOWN``. The fusion deals a burst
        of AOE damage to all alive enemies (a flat multiple of
        ``tap_damage``, NOT multiplicative with ``combo_mult``).
        """
        self._fusion_timer -= dt
        if self._fusion_timer > 0:
            return
        # Timer expired: reset and try to fire.
        self._fusion_timer = FUSION_COOLDOWN
        fusion = self._active_fusion()
        if fusion is None:
            return
        # Fire the fusion: AOE damage to all alive enemies. The damage is
        # a flat multiple of ``tap_damage`` (capped, NOT multiplicative
        # with combo_mult — same philosophy as the finishers). The
        # elemental multiplier still applies (the fusion respects the
        # type chart), so a fusion vs a 2x-advantaged enemy deals 2x.
        from engine.enemy import _apply_damage
        dmg = self.ninja.tap_damage * FUSION_DMG_MULT
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        evo = aggregate_bonuses(self.state)
        for t in list(self.world.enemies):
            if t.alive:
                _apply_damage(t, dmg, is_crit=True,
                              attuned=self.state.attuned_element)
                if not t.alive:
                    self._on_enemy_killed(t, combo_m, gold_m, evo)
        # Skill VFX for the fusion (reuse the skill-FX burst).
        self.skill_fx.trigger("shuriken", self.ninja.x, self.ninja.y,
                              self.world.enemies)
        self.notify(f"Godai Fusion: {fusion}!", (255, 180, 90))

    def gold_mult(self) -> float:
        evo = aggregate_bonuses(self.state)
        return (1.0 + evo.get("gold_pct", 0.0) + evo.get("godai_fire", 0.0)
                + _upgrade_pct(self.state, "gold_drop")
                # Stacking tokens (gp-permanent-scaling): coin tokens are
                # +1% each to gold. Permanent, sourced from daily quests +
                # zone-boss milestones (NOT achievements -- no
                # double-counting with the Heritage passives).
                + evo.get("coin_token_pct", 0.0))

    # -----------------------------------------------------------------
    # Cleave (Task 16): overkill-clears the next K enemies on a massive
    # overkill. Gated behind mid-ascension (``ascend_tier >= 3``) so a
    # new player never sees splash in the first runs — the gate is the
    # whole point (early zones feel earned). The Cleave node lives in
    # the offense branch of the skill tree (``off_cleave1``); the runner
    # multiplies the node's count by the tier gate.
    # -----------------------------------------------------------------
    def cleave_count(self) -> int:
        """The number of enemies to chain-clear on a massive overkill.

        Returns 0 below tier 3 (the mid-ascension gate) — a new player
        never sees splash. At tier >= 3 with the Cleave node unlocked,
        returns the node's ``cleave`` count (the number of enemies to
        chain-clear). Both gates must hold: the tier gate AND the
        skill-tree node.
        """
        if self.state.ascend_tier < 3:
            return 0
        evo = aggregate_bonuses(self.state)
        return int(evo.get("cleave", 0))

    # -----------------------------------------------------------------
    # Combo decay helpers (Task 22: combo-decay-resistance run upgrades)
    # -----------------------------------------------------------------
    def combo_grace(self) -> float:
        """The current combo grace window (seconds the combo can go
        negative before fully resetting).

        Base ``COMBO_GRACE`` + the ``combo_grace`` run upgrade (flat
        additive seconds) + the ``combo_grace_pct`` skill-tree bonus
        (a multiplier on the base+upgrade grace). The run upgrade
        resets on ascension so there is no save-migration risk; the
        skill-tree bonus is permanent.
        """
        evo = aggregate_bonuses(self.state)
        grace_pct = evo.get("combo_grace_pct", 0.0)
        return (COMBO_GRACE + _upgrade_val(self.state, "combo_grace")) * (1.0 + grace_pct)

    def combo_decay_rate(self) -> float:
        """The combo timer drain rate multiplier (1.0 = normal, < 1.0 =
        slower drain from the ``combo_sustain`` run upgrade).

        ``combo_sustain`` is a flat reduction on the drain rate (capped
        at 0.5 so the combo never freezes). The upgrade resets on
        ascension so there is no save-migration risk.
        """
        sustain = _upgrade_val(self.state, "combo_sustain")
        return max(0.5, 1.0 - sustain)

    # -----------------------------------------------------------------
    # Active-skill helpers (Task 22: skill-adjacent run upgrades)
    # -----------------------------------------------------------------
    def skill_damage_mult(self) -> float:
        """The skill damage multiplier from the ``skill_dmg`` run upgrade.

        Base 1.0 + the upgrade's flat additive (same stack as
        ``tap_mult``). The upgrade resets on ascension.
        """
        return 1.0 + _upgrade_val(self.state, "skill_dmg")

    def skill_cooldown_mult(self) -> float:
        """The skill cooldown multiplier from the ``skill_cd`` run upgrade.

        Base 1.0 - the upgrade's flat reduction (capped at 0.5 so
        cooldowns never drop below half). The upgrade resets on
        ascension.
        """
        cd = _upgrade_val(self.state, "skill_cd")
        return max(0.5, 1.0 - cd)

    # -----------------------------------------------------------------
    # Tap fatigue (Task 24 / gp-tap-auto-rebalance)
    # -----------------------------------------------------------------
    def tap_fatigue_mult(self) -> float:
        """The current tap fatigue multiplier (1.0 = no fatigue, 0.3 = floor).

        Counts the taps in the last ``TAP_FATIGUE_WINDOW`` seconds. If the
        count exceeds ``TAP_FATIGUE_THRESHOLD`` (5), each tap above the
        threshold reduces the multiplier by ``TAP_FATIGUE_PER_TAP`` (5%),
        floored at ``TAP_FATIGUE_FLOOR`` (0.3x) so tapping never becomes
        useless. The window is 1.0 second so a macro that fires 100 taps/s
        is capped at the floor; a player tapping at 5 taps/s or less pays
        no fatigue. This bounds the active-burst upside so auto-attack
        remains the backbone DPS.
        """
        now = time.monotonic()
        # Drop timestamps older than the window.
        window = cfg.TAP_FATIGUE_WINDOW
        self._tap_timestamps = [t for t in self._tap_timestamps
                                if now - t < window]
        taps = len(self._tap_timestamps)
        if taps <= cfg.TAP_FATIGUE_THRESHOLD:
            return 1.0
        excess = taps - cfg.TAP_FATIGUE_THRESHOLD
        return max(cfg.TAP_FATIGUE_FLOOR, 1.0 - excess * cfg.TAP_FATIGUE_PER_TAP)

    def _record_tap(self) -> None:
        """Record a tap timestamp for the fatigue window."""
        self._tap_timestamps.append(time.monotonic())

    # -----------------------------------------------------------------
    # Tap rhythm (Task 25 / gp-skill-synergy-rhythm)
    # -----------------------------------------------------------------
    def rhythm_mult(self) -> float:
        """The current tap rhythm multiplier (1.0 = no bonus, 1.5 = max).

        ``1.0 + RHYTHM_BONUS_PER_LEVEL * state.rhythm_streak``. The streak
        is capped at ``RHYTHM_CAP`` (20) so the max multiplier is 1.5x.
        Rhythm is strictly a BONUS: the multiplier is always >= 1.0 (floor
        0, never a penalty) -- motor-impaired players aren't punished.
        """
        return 1.0 + RHYTHM_BONUS_PER_LEVEL * self.state.rhythm_streak

    def _record_rhythm_tap(self) -> None:
        """Record a tap timestamp for the rhythm window + update the streak.

        Keeps the last ``RHYTHM_WINDOW_SIZE`` (5) tap timestamps; computes
        the median of the intervals between them; if the median is in the
        0.35-0.55s window, increments ``state.rhythm_streak`` (capped at
        ``RHYTHM_CAP``); else resets the streak to 0. A soft tick SFX
        plays when the streak increments (a non-visual cue for
        ``reduced_motion`` players).
        """
        self._rhythm_taps.append(time.monotonic())
        if len(self._rhythm_taps) > RHYTHM_WINDOW_SIZE:
            self._rhythm_taps = self._rhythm_taps[-RHYTHM_WINDOW_SIZE:]
        self._update_rhythm_streak()

    def _update_rhythm_streak(self) -> None:
        """Evaluate the rhythm window + update ``state.rhythm_streak``.

        Requires ``RHYTHM_WINDOW_SIZE`` (5) taps before judging the rhythm;
        with fewer taps the streak is unchanged (no bonus, no penalty --
        the player hasn't established a rhythm yet).
        """
        if len(self._rhythm_taps) < RHYTHM_WINDOW_SIZE:
            return
        intervals = [self._rhythm_taps[i + 1] - self._rhythm_taps[i]
                     for i in range(len(self._rhythm_taps) - 1)]
        median = sorted(intervals)[len(intervals) // 2]
        if RHYTHM_MIN_INTERVAL <= median <= RHYTHM_MAX_INTERVAL:
            self.state.rhythm_streak = min(RHYTHM_CAP,
                                          self.state.rhythm_streak + 1)
            # Soft tick SFX (a non-visual cue for reduced_motion players).
            from assets import play
            play("tick", self.state.sound_on)
        else:
            self.state.rhythm_streak = 0

    # -----------------------------------------------------------------
    # Update
    # -----------------------------------------------------------------
    def update(self, dt: float, *, paused: bool = False) -> None:
        if paused:
            return
        evo = aggregate_bonuses(self.state)
        density = evo.get("density_pct", 0.0) + _upgrade_pct(self.state, "enemy_density")
        firefly_spawn = evo.get("firefly_spawn", 0.0)

        # World.
        self.world.firefly_size_bonus = evo.get("firefly_size", 0.0)
        self.world.update(dt, paused=paused, density_pct=density,
                          firefly_spawn_pct=firefly_spawn)

        # Building income (passive gold/sec).
        from core.game_economy import total_gps
        gps = total_gps(self.state)
        gps_gold = gps * dt
        self._award_gold(gps_gold)

        # Combat.
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        auto_active = self.state.energy_active
        # Godai auto-attune (Task 21): if the auto-attune node is unlocked,
        # set ``state.attuned_element`` to the best element for the current
        # zone each tick (the 2x-advantage pick). Without the node, the
        # attuned element stays whatever the player set (default "none" =
        # 1x — idle is never worse than 1x).
        if "godai_auto_attune" in self.state.skill_tree:
            self.state.attuned_element = self.auto_attune_element()
        # Executioner's Edge finisher: while the timer is > 0, every tap
        # and auto-attack is a guaranteed crit. We model this by briefly
        # maxing the ninja's crit_chance for the duration of the combat
        # tick (the value is restored below after tick_combat), so the
        # existing roll_crit path picks it up without a new code path.
        _saved_crit_chance = self.ninja.crit_chance
        if self._executioner_timer > 0:
            self.ninja.crit_chance = 1.0  # guaranteed crit

        def on_kill(enemy: Enemy) -> None:
            self._on_enemy_killed(enemy, combo_m, gold_m, evo)

        tick_combat(self.ninja, self.world.enemies, dt,
                    combo_mult=combo_m, gold_mult=gold_m,
                    auto_active=auto_active, on_kill=on_kill,
                    attuned=self.state.attuned_element)

        # Restore the ninja's real crit_chance (the Executioner's Edge
        # override was only for this tick).
        self.ninja.crit_chance = _saved_crit_chance

        # Cull dead enemies after their death-fade window so corpses don't
        # clog the spawn cap (the old C1 bug).  last_damage_timer is
        # decremented for ALL enemies in tick_combat, so a dead enemy
        # reaches -0.3 within ~0.9s of death and is dropped here.
        self.world.enemies = [e for e in self.world.enemies
                              if e.alive or e.last_damage_timer > -0.3]

        # Executioner's Edge finisher timer (transient guaranteed-crit
        # buff). Decrement after the combat tick (the override above
        # applied for this whole tick).
        if self._executioner_timer > 0:
            self._executioner_timer = max(0.0, self._executioner_timer - dt)

        # Godai fusion (Task 21): advance the fusion timer and fire the
        # active fusion when it's ready (30s cooldown). The fusion deals
        # AOE damage to all alive enemies; see ``_tick_fusion``.
        self._tick_fusion(dt)
        # Synergy arc timer (Task 25): decrement the display timer so the
        # glowing arc between the skill buttons fades out after
        # ``SYNERGY_ARC_DUR`` (1.0s).
        if self._synergy_arc_timer > 0:
            self._synergy_arc_timer = max(0.0, self._synergy_arc_timer - dt)

        # Combo decay (with grace period). ``combo_timer`` is allowed to
        # go negative to -COMBO_GRACE (-1.5s) before the combo fully
        # resets; a kill during the grace window (combo_timer < 0)
        # restores combo_timer to the full window (see _on_enemy_killed).
        # Charges persist through the decay window and are only cleared
        # on the full reset (the grace window is a "last chance" to
        # refresh the combo, not a fresh start).
        # Task 22: combo_grace extends the grace window; combo_sustain
        # slows the decay rate (the timer drains slower, so the combo
        # lasts longer before hitting the grace floor). Both are run
        # upgrades that reset on ascension -- no save-migration risk.
        # Sync the combo FX reduced-motion gate from state each tick
        # (the same way main.py wires death_fx; syncing here keeps the
        # gate current if the player toggles reduced_motion mid-run).
        self.combo_fx.reduced_motion = self.state.reduced_motion
        if self.state.combo > 0:
            self.state.combo_timer -= dt * self.combo_decay_rate()
            if self.state.combo_timer <= -self.combo_grace():
                # Combo fully reset: fire the COMBO LOST banner (gated
                # by reduced_motion inside combo_fx.lost), then clear
                # the combo + banked charges.
                self.combo_fx.lost(self.state.combo)
                self.state.combo = 0
                self.state.combo_charges = 0

        # Fireflies.
        update_fireflies(self.world.fireflies, dt)

        # Active skills tick.
        for sk in self.skills.values():
            tick_skill(sk, dt)

        # Energy / Auto Katana.  ``energy_timer`` (skill tree) extends the max
        # duration; ``energy_regen`` speeds recharge; ``energy_from_kill`` adds
        # energy per kill.
        if self.state.energy_active:
            self.state.energy -= dt
            if self.state.energy <= 0:
                self.state.energy = 0
                self.state.energy_active = False
                self.state.energy_lockout = 5.0
                self.notify("Auto Katana depleted!", (255, 180, 90))
        elif self.state.energy_lockout > 0:
            self.state.energy_lockout -= dt
        else:
            regen = (1.0 + evo.get("energy_regen", 0.0)) * 0.5  # base 0.5/s
            self.state.energy = min(self.state.energy_max, self.state.energy + regen * dt)
        # The auto-katana's max duration is the base + the skill-tree bonus.
        # (Recompute lazily; cheap.)
        self.state.energy_max = 600.0 + evo.get("energy_timer", 0.0)

        # -----------------------------------------------------------------
        # Task 28 / pl-automation: automation nodes (auto-cast, auto-firefly,
        # auto-energy, auto-ascend, farm-when-stuck). These are gated behind
        # deep elixir investment (high-cost skill-tree nodes) -- an earned
        # endgame convenience, not available to new players. The automation
        # block runs after the energy section so the energy state is current;
        # the skills tick (above) is before so the cooldowns are current; the
        # fireflies update (above) is before so the fireflies are current.
        # -----------------------------------------------------------------
        # Auto-cast: if auto_cast unlocked + energy active, auto-fire Rope
        # Hook + Shuriken when off cooldown. The auto-cast uses the same
        # ``activate_skill`` path so synergies + skill_dmg apply (the auto-
        # cast is a reward for deep investment, not a separate code path).
        if "auto_cast" in self.state.skill_tree and self.state.energy_active:
            if "rope" in self.skills and can_fire(self.skills["rope"]):
                self.activate_skill("rope")
            if "shuriken" in self.skills and can_fire(self.skills["shuriken"]):
                self.activate_skill("shuriken")
        # Auto-firefly: if auto_firefly unlocked, auto-catch all fireflies.
        # The auto-catch awards the same gold a manual ``tap_at`` would
        # (the firefly multipliers + combo apply), so auto_firefly is a
        # convenience, not a bonus.
        if "auto_firefly" in self.state.skill_tree:
            self._auto_catch_fireflies()
        # Auto-energy: if auto_energy unlocked + energy available + not
        # active + not locked out, auto-activate Energy. The ``toggle_energy``
        # call activates Energy (the conditions for activation are met).
        if ("auto_energy" in self.state.skill_tree
                and not self.state.energy_active
                and self.state.energy_lockout <= 0
                and self.state.energy > 0):
            self.toggle_energy()
        # Auto-ascend: if auto_ascend unlocked + at the player's threshold,
        # auto-ascend (respecting the player's threshold). The ascend
        # resets the state; ``reset_for_ascension`` resets the runner's
        # world + transient state. The threshold is respected -- the
        # player sets it and the auto-ascend only fires when the threshold
        # is met (see ``core.ascend.should_auto_ascend``).
        from core.ascend import should_auto_ascend
        if should_auto_ascend(self.state):
            from core.ascend import ascend
            gained = ascend(self.state)
            if gained > 0:
                self.reset_for_ascension()
                self.notify(f"Auto-ascended! +{gained} elixir", (150, 80, 220))
        # Farm-when-stuck: track how long the current boss has been alive.
        # When the timer exceeds ``FARM_STUCK_THRESHOLD`` (with
        # ``auto_progress`` unlocked), the runner enters farm mode -- the
        # road keeps earning gold (from buildings + kills, which already
        # happen through the normal tick) instead of dead-ending. The farm
        # mode is a flag the UI can read. When the boss is killed (no boss
        # alive), the timer resets + farm mode is cleared.
        boss_alive = any(e.is_boss and e.alive for e in self.world.enemies)
        if boss_alive:
            self._boss_stuck_timer += dt
        else:
            self._boss_stuck_timer = 0.0
            self.farm_mode = False
        if ("auto_progress" in self.state.skill_tree
                and self._boss_stuck_timer >= FARM_STUCK_THRESHOLD):
            self.farm_mode = True

        # Ninja respawn.
        if not self.ninja.alive:
            self.ninja.alive = True
            # Task 22: the ``revive_pct`` skill-tree bonus (from the
            # defense branch's Phoenix Shell node + the legacy EVOLUTION
            # ``phoenix`` node) raises the respawn HP. Base 0.3 (30%);
            # each revive_pct point adds to the fraction (capped at 1.0 so
            # the ninja never respawns above full HP).
            revive_pct = evo.get("revive_pct", 0.0)
            self.ninja.hp = self.ninja.max_hp * min(1.0, 0.3 + revive_pct)
            # A death breaks the combo (the ninja dropped). Clear combo
            # + charges; the COMBO LOST banner is NOT fired here (the
            # death is its own feedback).
            self.state.combo = 0
            self.state.combo_charges = 0
            self.state.combo_timer = 0.0
            self.notify("The ninja rises again!", (130, 230, 160))

        # Sync world totals to state.
        self.state.total_distance = self.world.total_distance
        self.state.zone_index = self.world.zone_index
        self.state.zone_distance = self.world.zone_distance
        # Track best zone ever reached (for achievements + ascension gating).
        if self.state.zone_index > self.state.best_zone:
            self.state.best_zone = self.state.zone_index

        # Quests + achievements.
        maybe_refresh_dailies(self.state)
        completed = update_daily_progress(self.state)
        for c in completed:
            self.notify(f"Quest complete: {c['name']}  +{c['medals']} medals",
                        (200, 200, 220))
        # Weekly + chapter quests (Task 26 / cnt-quest-codex). Weekly
        # quests refresh every 7d and read cumulative counters; chapter
        # quests are one-time milestones tied to zone progression. Both
        # award Medals + Amber (no tokens -- tokens come from daily quests
        # + zone-boss milestones only, distinct sources, no double-counting
        # with the Heritage passives).
        maybe_refresh_weeklies(self.state)
        weekly_completed = update_weekly_progress(self.state)
        for c in weekly_completed:
            self.notify(f"Weekly: {c['name']}  +{c['medals']} medals",
                        (255, 205, 90))
        chapter_completed = update_chapter_progress(self.state)
        for c in chapter_completed:
            self.notify(f"Chapter: {c['name']}  +{c['medals']} medals",
                        (255, 180, 60))
        newly = check_achievements(self.state)
        for a in newly:
            self.notify(f"Achievement: {a.name}  +{a.reward_amber} amber",
                        (255, 205, 90))

        # FX.
        self.fx.update(dt)
        self.death_fx.update(dt)
        self.combo_fx.update(dt)
        self.ninja_fx.update(dt)
        self.skill_fx.update(dt)
        self.zone_fx.update(dt)
        self.boss_fx.update(dt)
        self.firefly_fx.update(dt)
        # Task 31 (gfx-weather): sync the weather FX to the current zone
        # each tick. The world's zone dict has a ``weather`` key (added by
        # Task 31); the screen reads it via the world. Sync here so the
        # weather follows zone changes (the world advances zone_index on
        # a boss kill; the next tick the weather FX reads the new zone).
        # The reduced_motion + render-tier gates are read from state here
        # so the weather respects the same gates as the other FX.
        from data.enemies import zone_by_index
        zone = zone_by_index(self.state.zone_index)
        self.weather_fx.set_weather(
            zone.get("weather", "none"),
            self.state.zone_index,
        )
        self.weather_fx.reduced_motion = self.state.reduced_motion
        self.weather_fx.quality = self.state.effective_render_quality()
        self.weather_fx.update(dt)

        # Notifications decay.
        self.notifications = [(t, life - dt, col) for (t, life, col) in self.notifications
                             if life - dt > 0]

    # -----------------------------------------------------------------
    # Kill handling
    # -----------------------------------------------------------------
    def _on_enemy_killed(self, enemy: Enemy, combo_m: float, gold_m: float, evo: dict) -> None:
        gold = enemy.gold * combo_m * gold_m
        self._award_gold(gold)
        self.state.monsters_killed += 1
        self.state.kills_today += 1
        # Combo increment + grace-window restore. A kill during the grace
        # window (combo_timer < 0) restores the full window — the combo
        # was "saved" at the last second. A kill with combo_timer >= 0
        # just refreshes the window as usual.
        prev_combo = self.state.combo
        self.state.combo += 1
        self.state.combo_timer = COMBO_WINDOW + evo.get("combo_window", 0.0) + _upgrade_val(self.state, "combo_window")
        if self.state.combo > self.state.best_combo_ever:
            self.state.best_combo_ever = self.state.combo
        if self.state.combo > self.state.best_combo_today:
            self.state.best_combo_today = self.state.combo
        # Combo Finisher charge banking: when the running combo crosses a
        # ``combo_fx.MILESTONES`` threshold (25/50/100/200 — and 10, the
        # other key in the dict), bank a charge into ``combo_charges``.
        # ``prev_combo < m <= self.state.combo`` catches the exact cross
        # (so a single kill that jumps from 24 to 25 banks a charge,
        # and a kill from 99 to 100 banks another). Charges persist
        # through the decay window and are only lost on the full reset
        # (see the decay block in ``update``).
        for m in _COMBO_MILESTONES:
            if prev_combo < m <= self.state.combo:
                self.state.combo_charges += 1
                break  # one charge per kill (a single kill can't cross 2)
        # Combo milestone celebration.
        info = self.combo_fx.check(self.state.combo)
        if info is not None:
            award = info["gold"] * gold_m
            self._award_gold(award)
            self.combo_fx.trigger(self.state.combo, enemy.x, enemy.y, gold=award)
            self.notify(f"{info['label']}  +{int(round(award))} gold", (255, 205, 90))
        # Energy-from-kill: recharge the auto-katana a little per kill.
        if evo.get("energy_from_kill", 0.0) > 0 and not self.state.energy_active:
            self.state.energy = min(self.state.energy_max,
                                   self.state.energy + evo["energy_from_kill"])
        # Rare drops.
        if enemy.is_boss:
            self.state.bosses_killed += 1
            # Stacking token (gp-permanent-scaling): award a token at a
            # capped milestone rate (every BOSS_TOKEN_EVERY kills). The
            # cap ensures the +1%-per-token complements rather than
            # replaces the exponential zone scaling.
            award_boss_token(self.state, self.state.bosses_killed - 1)
            # Gear drop (cnt-gear-loot): a boss kill drops a gear piece
            # (random slot, rarity from GACHA_RATES, random affix from
            # the slot's pool). The new piece replaces any existing piece
            # in the slot (one piece per slot). The drop is automatic --
            # no active requirement -- so gear progression is a passive
            # consequence of boss kills (the player just kills bosses and
            # the gear set fills in over time). The Forge UI (enhance /
            # reroll / salvage) is Task 33.
            self._drop_gear()
            self.notify(f"Boss slain: {enemy.name}!", (255, 220, 120))
            self.boss_fx.stop()
        if enemy.is_miniboss:
            # Mini-boss kill: a brief notification. The boss-FX intro
            # self-clears once its shorter intro completes (see
            # BossFxSystem.update), so no ``boss_fx.stop()`` here.
            self.notify(f"Mini-boss slain: {enemy.name}!", (255, 200, 130))
        if enemy.is_elite:
            # Elite kill: the guaranteed rare_drop is handled by the
            # chest/drop mechanic (a later task). For now, a brief
            # notification so the player sees the elite died.
            self.notify(f"Elite slain: {enemy.name}!", (255, 180, 120))
        # Firefly spawn chance on kill.
        if rng().random() < 0.05:
            self.world.fireflies.append(_make_firefly_near(enemy.x, enemy.y))
            self.bus.emit("firefly_spawn", self.world.fireflies[-1])
        self.world.on_enemy_killed(enemy)
        self.death_fx.spawn(enemy)

    def _award_gold(self, amount: float) -> None:
        self.state.gold += amount
        self.state.lifetime_gold += amount
        self.state.gold_earned_today += amount

    # -----------------------------------------------------------------
    # Gear drops (cnt-gear-loot)
    # -----------------------------------------------------------------
    def _drop_gear(self) -> None:
        """Drop a gear piece on a boss kill (automatic, no active requirement).

        Picks a random slot from ``cfg.GEAR_SLOTS``, a rarity from
        ``cfg.GACHA_RATES`` (the same table the pet gacha uses), and a
        random affix from the slot's pool (``cfg.GEAR_AFFIXES[slot]``).
        The affix value is the base value scaled by the rarity multiplier
        (``cfg.GEAR_RARITY_MULT[rarity]``). The new piece replaces any
        existing piece in the slot (one piece per slot, 4 slots max).

        The drop is the MODEL half of the gear split (Task 20): the
        state.gear dict is the source of truth; the Forge UI (enhance /
        reroll / salvage) is Task 33. The gear provider in
        ``core.bonuses`` reads ``state.gear`` and emits the affix effects
        into the flat bonus dict via ``aggregate_bonuses``, so the gear
        contributions stack additively with the skill tree + pets +
        tokens + heritage contributions to the same effect keys.
        """
        slot = rng().choice(cfg.GEAR_SLOTS)
        # Roll a rarity from GACHA_RATES (reuse the gacha distribution).
        rarities = tuple(cfg.GACHA_RATES.keys())
        weights = [cfg.GACHA_RATES[r] for r in rarities]
        rarity = rng().choices(rarities, weights=weights, k=1)[0]
        # Pick a random affix from the slot's pool.
        pool = cfg.GEAR_AFFIXES.get(slot)
        if not pool:
            return
        affix_key, base_val = rng().choice(pool)
        value = base_val * cfg.GEAR_RARITY_MULT.get(rarity, 1.0)
        # Replace any existing piece in the slot (one piece per slot).
        self.state.gear[slot] = {
            "affix": affix_key,
            "value": value,
            "rarity": rarity,
        }

    # -----------------------------------------------------------------
    # Player actions
    # -----------------------------------------------------------------
    def tap(self) -> None:
        """The player taps the screen — deal tap damage to the nearest enemy."""
        if not self.ninja.alive:
            return
        # Task 24 (gp-tap-auto-rebalance): record this tap for the fatigue
        # window BEFORE computing the multiplier so the count is current.
        self._record_tap()
        # Task 25 (gp-skill-synergy-rhythm): record this tap for the rhythm
        # window + update the streak. The rhythm is strictly a bonus (the
        # multiplier is >= 1.0, floor 0, never a penalty).
        self._record_rhythm_tap()
        fatigue_m = self.tap_fatigue_mult()
        rhythm_m = self.rhythm_mult()
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        evo = aggregate_bonuses(self.state)
        # Executioner's Edge finisher: while the timer is > 0, every tap
        # is a guaranteed crit. We model this by briefly maxing the
        # ninja's crit_chance for the duration of the tap (the value is
        # restored after), so the existing roll_crit path inside
        # ``tap_enemy`` picks it up. (Same pattern as the override in
        # ``update`` around ``tick_combat`` for auto-attacks.)
        _saved_crit_chance = self.ninja.crit_chance
        if self._executioner_timer > 0:
            self.ninja.crit_chance = 1.0  # guaranteed crit
        # Tap fatigue (Task 24) + rhythm (Task 25): scale the ninja's
        # tap_damage by the fatigue multiplier (a penalty above 5 taps/s,
        # floored at 0.3x) AND the rhythm multiplier (a bonus, >= 1.0)
        # for this tap (restored after, same pattern as the crit_chance
        # override above). The rhythm multiplier is always >= 1.0 so it
        # never makes the tap worse -- it only adds on top of the fatigue.
        _saved_tap_damage = self.ninja.tap_damage
        self.ninja.tap_damage = self.ninja.tap_damage * fatigue_m * rhythm_m
        # Snapshot the target's HP before the tap so we can detect the
        # massive overkill (the cleave trigger condition). The cleave
        # fires when the tap damage exceeds the enemy's remaining HP by
        # a large margin (CLEAVE_OVERKILL_RATIO * HP), i.e. the enemy
        # was one-shot by a huge margin.
        target_pre = nearest_enemy(self.world.enemies)
        target_hp_before = target_pre.hp if target_pre is not None else 0.0
        # ``tap_enemy`` returns ``(target, dmg_dealt, is_crit)`` so we
        # can use the ACTUAL damage dealt for the cleave overkill
        # condition (not a separate roll — see the review note on the
        # double ``roll_crit`` bug). The actual damage is the tap's
        # tap_damage * crit_mult * combo_m (the same value
        # ``_apply_damage`` reduced the target's HP by, modulo the boss
        # shield); for a non-boss target, the shield is 0 so
        # ``dmg_dealt`` is the full damage applied.
        target, dmg_dealt, _is_crit = tap_enemy(
            self.ninja, self.world.enemies,
            combo_mult=combo_m, gold_mult=gold_m,
            on_kill=lambda e: self._on_enemy_killed(e, combo_m, gold_m, evo),
            attuned=self.state.attuned_element)
        # Restore the ninja's real crit_chance + tap_damage (the
        # overrides were only for this tap).
        self.ninja.crit_chance = _saved_crit_chance
        self.ninja.tap_damage = _saved_tap_damage
        # Cleave (Task 16): if the tap massively overkilled the target
        # (the actual damage dealt exceeded the target's pre-tap HP by
        # a large margin), chain-clear the next ``cleave_count()``
        # enemies. The cleave is gated behind mid-ascension
        # (``cleave_count() == 0`` below tier 3), so a new player never
        # sees splash. Each chain-cleared enemy goes through the normal
        # kill path (``_on_enemy_killed``) so monsters_killed, gold,
        # combo, bestiary/achievement reveals all fire — the cleave does
        # NOT bypass the kill path, it just clears the enemies in one
        # burst.
        if target is not None and not target.alive:
            cleave_k = self.cleave_count()
            if cleave_k > 0:
                # The overkill condition: the tap's ACTUAL damage
                # exceeded ``CLEAVE_OVERKILL_RATIO`` times the target's
                # pre-tap HP (a massive overkill, not just a kill). This
                # is the "damage massively overkills" trigger from the
                # brief. We use the ACTUAL damage dealt (``dmg_dealt``,
                # returned by ``tap_enemy``) vs the target's pre-tap HP
                # — a tap that exactly kills (dmg_dealt == HP) does NOT
                # trigger the cleave; a tap that one-shots a 1 HP enemy
                # with 10k damage (dmg_dealt = 10k) does. The boss
                # shield is not a factor here because the cleave is for
                # trash enemies (bosses are excluded from the chain in
                # ``_apply_cleave``); for a non-boss target, the shield
                # is 0 so dmg_dealt is the full damage applied.
                if target_hp_before > 0 and dmg_dealt > target_hp_before * CLEAVE_OVERKILL_RATIO:
                    self._apply_cleave(target, cleave_k, combo_m, gold_m, evo)
        # Also try to catch a firefly near the tap.
        # (The UI passes the tap position; here we approximate with nearest.)

    def _apply_cleave(self, killed: Enemy, k: int,
                      combo_m: float, gold_m: float, evo: dict) -> None:
        """Chain-clear the next ``k`` alive enemies after a massive overkill.

        The clearees are the next ``k`` alive enemies AFTER the killed
        target in the world's enemy list (ordered by x, the same order
        ``nearest_enemy`` walks). Each clearee is killed through the
        normal path (``_on_enemy_killed``) so monsters_killed, gold,
        combo, and bestiary/achievement reveals all fire — the cleave
        does NOT bypass the kill path, it just clears the enemies in
        one burst. Bosses are NOT cleaved (the cleave is for trash
        enemies; a boss would be a progression gate, not a skip).
        """
        # Order the alive enemies by x (nearest-first, the same order
        # ``nearest_enemy`` walks). The killed target is already dead
        # (alive == False), so it's skipped; the clearees are the next
        # ``k`` alive enemies after it.
        alive_sorted = sorted(
            (e for e in self.world.enemies if e.alive and not e.is_boss),
            key=lambda e: e.x)
        cleaved = 0
        for e in alive_sorted:
            if cleaved >= k:
                break
            # Kill the enemy through the normal path (the cleave does
            # NOT bypass bestiary/achievement reveals — the enemy is
            # still killed, just with "cleave" damage instead of a tap).
            e.alive = False
            e.hp = 0
            self._on_enemy_killed(e, combo_m, gold_m, evo)
            cleaved += 1

    def tap_at(self, x: float, y: float) -> None:
        """Tap at a specific position — catch fireflies there, else hit nearest enemy."""
        # Firefly catch first.
        evo = aggregate_bonuses(self.state)
        for f in self.world.fireflies[:]:
            if abs(f.x - x) < 20 + f.size and abs(f.y - y) < 20 + f.size:
                # Firefly gold scales with the in-cycle zone (0..8) so
                # it stays bounded across cycles (the cycle multiplier
                # scales enemy stats, not firefly rewards).
                in_cycle = self.state.zone_index % 9
                gold = catch_firefly(f, base_gold=50 * (1 + in_cycle * 0.5),
                                      combo_mult=self.combo_mult(),
                                      firefly_gold_mult=1.0 + evo.get("firefly_gold", 0.0),
                                      firefly_value_mult=1.0 + evo.get("firefly_value", 0.0))
                self._award_gold(gold)
                self.state.fireflies_today += 1
                self.world.fireflies.remove(f)
                self.firefly_fx.on_catch(f.x, f.y, gold)
                self.notify(f"Firefly! +{int(gold)} gold", (255, 240, 120))
                return
        # Otherwise, attack the nearest enemy.
        self.tap()

    def activate_skill(self, sid: str) -> None:
        """Fire an active skill if unlocked and off cooldown.

        Task 22: the ``skill_dmg`` run upgrade multiplies the damage
        dealt by all damage skills (kunai/shuriken). The multiplier is
        applied on top of the existing tap/auto * combo stack so it
        composes cleanly. The upgrade resets on ascension.

        Task 25 (gp-skill-synergy-rhythm): firing two active skills
        within ``SYNERGY_WINDOW`` (2s) in a specific order triggers a
        named synergy bonus (a sequencing puzzle on the 4 active skills).
        The synergy is a flat burst (NOT multiplicative with combo_mult),
        same philosophy as the finishers and fusion. The synergy is a
        BONUS -- it only adds damage, never a penalty.
        """
        sk = self.skills.get(sid)
        if sk is None or not can_fire(sk):
            return
        fire_skill(sk)
        self.state.skills_used_today += 1
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        skill_m = self.skill_damage_mult()  # Task 22: skill_dmg upgrade
        # Skill VFX.
        self.skill_fx.trigger(sid, self.ninja.x, self.ninja.y, self.world.enemies)
        if sid == "kunai":
            # Burst damage to the nearest 5 enemies.
            targets = sorted([e for e in self.world.enemies if e.alive], key=lambda e: e.x)[:5]
            for t in targets:
                from engine.enemy import _apply_damage
                dmg = self.ninja.tap_damage * 3 * combo_m * skill_m
                _apply_damage(t, dmg, is_crit=True,
                              attuned=self.state.attuned_element)
                if not t.alive:
                    self._on_enemy_killed(t, combo_m, gold_m, aggregate_bonuses(self.state))
            self.notify("Kunai Barrage!", (255, 120, 110))
        elif sid == "shuriken":
            # AOE all enemies.
            from engine.enemy import _apply_damage
            for t in self.world.enemies:
                if t.alive:
                    dmg = self.ninja.auto_damage * 2 * combo_m * skill_m
                    _apply_damage(t, dmg,
                                  attuned=self.state.attuned_element)
                    if not t.alive:
                        self._on_enemy_killed(t, combo_m, gold_m, aggregate_bonuses(self.state))
            self.notify("Shuriken Vortex!", (180, 130, 255))
        elif sid == "rope":
            # Instant-kill the weakest alive enemy.
            targets = [e for e in self.world.enemies if e.alive and not e.is_boss]
            if targets:
                t = min(targets, key=lambda e: e.hp)
                t.alive = False
                t.hp = 0
                self._on_enemy_killed(t, combo_m, gold_m, aggregate_bonuses(self.state))
            self.notify("Rope Hook!", (130, 230, 160))
        elif sid == "speed":
            # Speed Step: a short burst of auto-katana-like attack speed.
            # We model it by briefly engaging the auto-attack boost.
            # NOTE: the Speed Step kill-ramp-with-decay rework is NOT
            # implemented (it punishes idle). The speed skill is a simple
            # energy burst, not a ramp that decays on no-kills.
            self.state.energy_active = True
            self.state.energy = max(self.state.energy, 8.0)
            self.notify("Speed Step!", (255, 240, 120))
        # Skill Synergies (Task 25): check whether the previous skill
        # fired within the 2s window matches a synergy pair. The synergy
        # is a sequencing puzzle -- the player fires two skills in a
        # specific order within the window. The bonus is a flat burst
        # (NOT multiplicative with combo_mult), applied on top of the
        # second skill's effect. The synergy is a BONUS -- it only adds
        # damage, never a penalty.
        now = time.monotonic()
        if (self.last_skill_id is not None
                and now - self.last_skill_time <= SYNERGY_WINDOW
                and (self.last_skill_id, sid) in SYNERGIES):
            self.last_synergy = SYNERGIES[(self.last_skill_id, sid)]
            self._synergy_arc_timer = SYNERGY_ARC_DUR
            # Apply the synergy bonus: a flat burst of AOE damage to all
            # alive enemies (a flat multiple of tap_damage, NOT
            # multiplicative with combo_mult -- same philosophy as the
            # finishers and fusion). The elemental multiplier still
            # applies (the synergy respects the type chart).
            from engine.enemy import _apply_damage
            evo = aggregate_bonuses(self.state)
            dmg = self.ninja.tap_damage * SYNERGY_DMG_MULT
            for t in list(self.world.enemies):
                if t.alive:
                    _apply_damage(t, dmg, is_crit=True,
                                  attuned=self.state.attuned_element)
                    if not t.alive:
                        self._on_enemy_killed(t, combo_m, gold_m, evo)
            # Skill VFX for the synergy (reuse the skill-FX burst).
            self.skill_fx.trigger("shuriken", self.ninja.x, self.ninja.y,
                                  self.world.enemies)
            self.notify(f"Synergy: {self.last_synergy}!", (255, 220, 120))
        # Track this skill for the next synergy check (regardless of
        # whether a synergy fired -- the next skill pairs with this one).
        self.last_skill_id = sid
        self.last_skill_time = now

    def toggle_energy(self) -> None:
        if self.state.energy_active:
            self.state.energy_active = False
            self.state.energy_lockout = 5.0
        elif self.state.energy > 0 and self.state.energy_lockout <= 0:
            self.state.energy_active = True
            self.notify("Auto Katana engaged!", (130, 230, 160))

    # -----------------------------------------------------------------
    # Task 28 / pl-automation: auto-firefly (auto-catch all fireflies)
    # -----------------------------------------------------------------
    def _auto_catch_fireflies(self) -> None:
        """Auto-catch all fireflies (the ``auto_firefly`` node).

        Catches every firefly in the world (no position check -- auto-catch
        catches all). The gold awarded is the same a manual ``tap_at``
        would award (the firefly multipliers + combo apply), so
        ``auto_firefly`` is a convenience, not a bonus. The fireflies are
        removed from the world + the firefly-catch FX fire.
        """
        if not self.world.fireflies:
            return
        evo = aggregate_bonuses(self.state)
        in_cycle = self.state.zone_index % 9
        for f in self.world.fireflies[:]:
            gold = catch_firefly(f, base_gold=50 * (1 + in_cycle * 0.5),
                                  combo_mult=self.combo_mult(),
                                  firefly_gold_mult=1.0 + evo.get("firefly_gold", 0.0),
                                  firefly_value_mult=1.0 + evo.get("firefly_value", 0.0))
            self._award_gold(gold)
            self.state.fireflies_today += 1
            self.firefly_fx.on_catch(f.x, f.y, gold)
        self.world.fireflies.clear()

    # -----------------------------------------------------------------
    # Combo Finishers
    # -----------------------------------------------------------------
    def activate_finisher(self, fid: str) -> None:
        """Spend banked combo charges on a finisher.

        Each finisher spends a fixed number of charges (see
        ``FINISHERS``). Finisher damage is a FIXED multiple of
        ``tap_damage`` with its own cap (``MAX_FINISHER_MULT``), NOT
        multiplicative with ``combo_mult`` — so a finisher never scales
        with the combo multiplier (the cap is the whole point: a fixed
        burst the player banks charges for, not another combo-scaled
        nuke). Bosses are auto-killable WITHOUT ``phantom_step`` (the
        ninja's auto-attack kills them normally); ``phantom_step`` is a
        convenience, never a gate on progression.
        """
        fdef = FINISHERS.get(fid)
        if fdef is None:
            return  # unknown finisher id: no-op (don't spend charges)
        name, cost, kind = fdef
        if self.state.combo_charges < cost:
            self.notify(f"{name}: need {cost} charges!", (220, 120, 120))
            return
        # Spend the charges.
        self.state.combo_charges -= cost
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        evo = aggregate_bonuses(self.state)
        if kind == "aoe":
            # Thousand Cuts: line AOE. Damage = tap_damage * 5, capped
            # at MAX_FINISHER_MULT (so the multiplier is min(5, MAX)).
            # NOT multiplicative with combo_mult.
            mult = min(5.0, MAX_FINISHER_MULT)
            dmg = self.ninja.tap_damage * mult
            from engine.enemy import _apply_damage
            for t in list(self.world.enemies):
                if t.alive:
                    _apply_damage(t, dmg, is_crit=True,
                                  attuned=self.state.attuned_element)
                    if not t.alive:
                        self._on_enemy_killed(t, combo_m, gold_m, evo)
            # Skill VFX for the finisher (reuse the skill-FX burst).
            self.skill_fx.trigger("shuriken", self.ninja.x, self.ninja.y,
                                  self.world.enemies)
            self.notify(f"{name}!", (255, 90, 90))
        elif kind == "boss_kill":
            # Phantom Step: instant-kill a boss IF combo >= 100. Bosses
            # are auto-killable WITHOUT this (the ninja's auto-attack
            # kills them normally); this is a convenience skip, never a
            # gate on progression. With combo < 100, the finisher spends
            # no charges and refunds them (it's a no-op, not a waste).
            if self.state.combo < 100:
                # Refund: this finisher is only meaningful at combo >= 100.
                self.state.combo_charges += cost
                self.notify(f"{name}: needs combo >= 100!", (220, 120, 120))
                return
            boss = next((e for e in self.world.enemies if e.is_boss and e.alive), None)
            if boss is not None:
                boss.alive = False
                boss.hp = 0
                self._on_enemy_killed(boss, combo_m, gold_m, evo)
                self.notify(f"{name}! Boss slain!", (255, 220, 120))
            else:
                # No boss to kill: refund the charges (don't waste them).
                self.state.combo_charges += cost
                self.notify(f"{name}: no boss to kill!", (220, 120, 120))
        elif kind == "clones":
            # Mirage: shadow clones — a brief burst of auto-katana-like
            # attack speed (modeled like the "speed" skill: a short
            # energy burst). The clones deal no extra damage themselves;
            # the effect is the auto-attack burst over the next few
            # seconds. Costs 1 charge.
            self.state.energy_active = True
            self.state.energy = max(self.state.energy, 6.0)
            self.notify(f"{name}! Shadow clones engaged!", (180, 130, 255))
        elif kind == "crit_buff":
            # Executioner's Edge: guaranteed-crit taps for a short
            # window. We model this by briefly maxing the ninja's
            # crit_chance for the duration of each combat tick while the
            # timer is > 0 (see the override in ``update``). Costs 1
            # charge. The effect is purely visual + a brief DPS bump; the
            # cap on the damage itself is the ninja's existing crit_dmg (no
            # new multiplier, NOT multiplicative with combo_mult).
            self._executioner_timer = 5.0  # seconds of guaranteed crits
            self.notify(f"{name}! Guaranteed crits!", (255, 180, 90))

    # -----------------------------------------------------------------
    # Misc
    # -----------------------------------------------------------------
    def notify(self, text: str, color=(255, 255, 255)) -> None:
        self.notifications.append((text, 3.0, color))

    def update_fx(self, dt: float) -> None:
        self.fx.update(dt)

    def reset_for_ascension(self) -> None:
        self.world.reset_for_ascension()
        self.ninja = make_ninja(self.state)
        self._refresh_skills()
        self.state.energy = self.state.energy_max
        self.state.energy_active = False
        # Reset combo + charges + the Executioner's Edge timer on ascension.
        self.state.combo = 0
        self.state.combo_charges = 0
        self.state.combo_timer = 0.0
        self._executioner_timer = 0.0
        # Reset the Godai fusion timer on ascension (transient — starts at
        # 0 so the first fusion fires as soon as the conditions are met on
        # the new run). ``attuned_element`` is NOT reset here — the
        # auto-attune node (if unlocked) re-picks it on the next
        # ``update`` tick, and a manual attunement persists across the
        # ascension (the player's choice is sticky).
        self._fusion_timer = 0.0
        # Reset the tap fatigue window on ascension (transient — the
        # rolling tap timestamps clear so the new run starts fresh).
        self._tap_timestamps = []
        # Reset the synergy tracking + rhythm streak on ascension
        # (transient — the new run starts fresh; rhythm_streak is on
        # state so it persists across saves but resets on the prestige).
        self.last_skill_id = None
        self.last_skill_time = 0.0
        self.last_synergy = None
        self._synergy_arc_timer = 0.0
        self._rhythm_taps = []
        self.state.rhythm_streak = 0
        # Task 28: reset the farm-when-stuck tracking on ascension
        # (transient -- the new run starts fresh; the boss is gone).
        self._boss_stuck_timer = 0.0
        self.farm_mode = False
        # Clear all FX.
        self.fx.texts.clear()
        self.death_fx.fx.clear()
        self.combo_fx.reset()
        self.ninja_fx._arcs.clear() if hasattr(self.ninja_fx, '_arcs') else None
        self.skill_fx.effects.clear() if hasattr(self.skill_fx, 'effects') else None
        # Task 31: clear the weather FX on ascension (the new run starts
        # in the village, weather "none" — the next tick re-syncs).
        self.weather_fx.particles.clear()


def _upgrade_pct(state: GameState, key: str) -> float:
    """Total % effect of a multiplicative run upgrade."""
    if state.upgrade_level(key) <= 0:
        return 0.0
    base = cfg.UPGRADE_BASE_EFFECT.get(key, 0.0)
    growth = cfg.UPGRADE_EFFECT_GROWTH.get(key, 1.0)
    lvl = state.upgrade_level(key)
    return base * (growth ** (lvl - 1)) * lvl


def _upgrade_val(state: GameState, key: str) -> float:
    return _upgrade_pct(state, key)


def _make_firefly_near(x: float, y: float):
    from engine.firefly import spawn_firefly
    return spawn_firefly(x, y if 120 < y < 380 else 250)


# ---------------------------------------------------------------------------
# Shadow Dungeon (Task 23 / cnt-shadow-dungeon-runner)
# ---------------------------------------------------------------------------
# A ``DungeonRunner`` that COMPOSES existing engine components (World,
# enemy.py spawn/combat, skills.py) rather than duplicating the main
# ``Runner`` logic. The road loop stays intact while the dungeon is active
# — the main ``Runner.update`` checks ``state.dungeon_active`` and, if so,
# ticks the dungeon ALONGSIDE the road (the road keeps idling). No new
# currency is added; the dungeon is gated on medals OR zone progression
# (existing fields), not a new currency. The Godai Fire element ties to
# the dungeon: the dungeon's enemies + boss use the Fire element from
# Task 21's ``element`` field on EnemyDef/Enemy.
#
# This is the "frontier" task — the architecture prerequisite for the
# dungeon variants (Task 34). The DungeonRunner does NOT reimplement
# combat, spawning, or skill ticking; it reuses the existing modules
# (``tick_combat``, ``spawn_enemy``, ``spawn_boss``, ``tick_skill``). It
# owns its own ``World`` instance (the dungeon world) distinct from the
# road's ``World`` so the dungeon drives its own spawn/combat scenario
# without touching the road.
#
# The dungeon's enemies + boss are fire-themed (the Godai Fire element).
# The type chart from ``engine.enemy.element_mult`` applies to dungeon
# enemies the same way it applies to road enemies — the dungeon reuses
# the Godai type chart, NOT a separate system. A wind-attuned player
# deals 2x to a fire dungeon enemy (wind > fire in the 4-cycle); a
# water-attuned player deals 0.5x (water < fire).

# The dungeon entry gate: medals OR zone progression. The gate is a
# threshold check, NOT a cost — entering the dungeon does NOT spend
# medals. The two gates are alternatives so a player who has progressed
# far along the road can enter even without medals (and vice versa).
DUNGEON_MEDAL_GATE = 50       # medals needed to enter the dungeon
DUNGEON_ZONE_GATE = 9         # zone_index needed (one full cycle) to enter

# The dungeon's fire-themed enemy pool. The dungeon uses a fixed set of
# fire-element EnemyDefs (the dungeon is fire-themed, NOT a zone). The
# pool is defined here (not in data/enemies.py) so the dungeon's theme is
# owned by the dungeon runner, not the zone data — the dungeon is a
# distinct content track, not a zone reskin.
from data.enemies import EnemyDef as _EnemyDef
DUNGEON_ENEMIES: list = [
    _EnemyDef("d_imp", "Dungeon Imp", "demon", 0, 1.4, 1.8, 1.8, 30, 16,
              rare_drop=0.07, element="fire"),
    _EnemyDef("d_hound", "Dungeon Hound", "beast", 10, 1.6, 2.0, 1.9, 32, 20,
              rare_drop=0.07, element="fire"),
    _EnemyDef("d_oni", "Dungeon Oni", "oni", 350, 2.0, 2.2, 2.2, 26, 22,
              rare_drop=0.08, element="fire"),
]
# The dungeon boss: a fire-themed capstone. The dungeon boss is a fixed
# EnemyDef (not a zone boss) so the dungeon's theme is self-contained.
DUNGEON_BOSS = _EnemyDef(
    "d_boss", "Shadow Inferno", "demon", 10, 14.0, 6.0, 16.0, 14, 46,
    rare_drop=0.7, desc="The dungeon's heart of fire.", element="fire")

# Dungeon floor scaling: HP/DMG/GOLD grow per floor so the dungeon
# deepens as the player descends. The growth is exponential (per floor)
# so a long dungeon run gets harder the deeper the player goes.
DUNGEON_HP_BASE = 60.0
DUNGEON_HP_GROWTH = 1.20      # per floor
DUNGEON_DMG_BASE = 8.0
DUNGEON_DMG_GROWTH = 1.15
DUNGEON_GOLD_BASE = 20.0
DUNGEON_GOLD_GROWTH = 1.18


def can_enter_dungeon(state: GameState) -> bool:
    """Whether the player can enter the Shadow Dungeon.

    The gate is medals OR zone progression (existing fields), NOT a new
    currency. A player with ``medals >= DUNGEON_MEDAL_GATE`` OR
    ``zone_index >= DUNGEON_ZONE_GATE`` can enter. The gate is a threshold
    check, NOT a cost — entering does NOT spend medals (see
    ``DungeonRunner.enter``). The two gates are alternatives so a player
    who has progressed far along the road can enter even without medals.
    """
    return (state.medals >= DUNGEON_MEDAL_GATE
            or state.zone_index >= DUNGEON_ZONE_GATE)


class DungeonRunner:
    """A dungeon runner that COMPOSES existing engine components.

    The ``DungeonRunner`` owns its own ``World`` instance (the dungeon
    world) distinct from the road's ``World``. It reuses the existing
    engine modules — ``tick_combat``, ``spawn_enemy``, ``spawn_boss``,
    ``tick_skill`` — rather than duplicating the main ``Runner`` logic.
    The road loop stays intact while the dungeon is active: the main
    ``Runner.update`` checks ``state.dungeon_active`` and, if so, ticks
    the dungeon ALONGSIDE the road (the road keeps idling).

    The dungeon's enemies + boss use the Fire Godai element (from Task
    21's ``element`` field). The type chart from
    ``engine.enemy.element_mult`` applies to dungeon enemies the same
    way it applies to road enemies — the dungeon reuses the Godai type
    chart, NOT a separate system.

    No new currency: the dungeon is gated on medals OR zone progression
    (existing fields) via ``can_enter_dungeon``. Entering does NOT spend
    medals (the gate is a threshold check, not a cost).
    """

    def __init__(self, state: GameState) -> None:
        self.state = state
        # Compose a World instance for the dungeon. The dungeon world is a
        # distinct instance from the road's World so the dungeon drives its
        # own spawn/combat scenario without touching the road. We reuse
        # the existing World class (the dungeon world composition lives in
        # engine/world.py; the dungeon-specific spawn methods are on the
        # DungeonRunner, not the World, so the World stays generic).
        self.world = World()
        # The ninja is shared with the road (the player's single hero);
        # the dungeon reuses the same ninja stats so the player's build
        # carries into the dungeon. The ninja is recomputed from state so
        # the dungeon sees the current stats (not a stale copy).
        self.ninja = make_ninja(state)
        # Active skills (only those unlocked) — reuse the same skill set
        # the road uses. The dungeon does NOT duplicate the skill logic;
        # it ticks the same ActiveSkill instances via ``tick_skill``.
        self.skills: dict[str, ActiveSkill] = {}
        self._refresh_skills()
        # The dungeon does NOT wire its own EventBus into
        # ``engine.enemy``: ``enemy.set_event_bus`` is a MODULE-global, so
        # calling it here would clobber the road's bus (the road's
        # ``Runner.__init__`` wired it). Instead, the dungeon's
        # ``tick_combat`` emits to whatever bus the road wired (the road's
        # bus), which is fine — the road's FX will show dungeon combat
        # events too (or the UI layer can suppress them per-screen). The
        # combat MODEL (HP, damage, kills) is per-World, not per-bus, so
        # the dungeon's combat is isolated from the road's combat even
        # though the enemy-event bus is shared. The dungeon keeps a bus
        # attribute for the UI layer to wire dungeon-specific FX handlers
        # onto, but the engine modules emit to the road's shared bus.
        self.bus = EventBus()
        # The dungeon floor (1-indexed after ``enter``). 0 = not entered.
        self._floor: int = 0
        # The dungeon spawn timer (the dungeon spawns enemies on its own
        # interval, separate from the road's spawn timer).
        self._spawn_timer: float = 0.0
        # Whether a boss is active on the current floor (gates the next
        # floor's spawn until the boss is killed).
        self._boss_active: bool = False

    def _refresh_skills(self) -> None:
        """Rebuild the active-skill set from unlocked skill-tree nodes.

        Mirrors the main Runner's ``_refresh_skills`` so the dungeon uses
        the SAME skills the road uses (the player's build carries over).
        The dungeon does NOT duplicate the skill logic; it ticks the same
        ActiveSkill instances via ``tick_skill``. The ``skill_cd`` run
        upgrade reduces the effective cooldown (recomputed here, same as
        the road); the upgrade resets on ascension.
        """
        self.skills.clear()
        cd_mult = self._skill_cooldown_mult()
        for sid in ("kunai", "shuriken", "rope", "speed"):
            unlock_node = {
                "kunai": "ab_root", "shuriken": "ab_shuriken",
                "rope": "ab_rope", "speed": "ab_speed",
            }[sid]
            if unlock_node in self.state.skill_tree:
                sk = make_skill(sid)
                sk.cooldown = sk.cooldown * cd_mult
                self.skills[sid] = sk

    # -----------------------------------------------------------------
    # Floor stat scaling (the dungeon deepens as the player descends)
    # -----------------------------------------------------------------
    def _floor_hp(self, edef) -> float:
        """The HP for a dungeon enemy on the current floor."""
        base = DUNGEON_HP_BASE * (DUNGEON_HP_GROWTH ** max(0, self._floor - 1))
        return base * edef.hp_mult

    def _floor_dmg(self, edef) -> float:
        """The damage for a dungeon enemy on the current floor."""
        base = DUNGEON_DMG_BASE * (DUNGEON_DMG_GROWTH ** max(0, self._floor - 1))
        return base * edef.dmg_mult

    def _floor_gold(self, edef) -> float:
        """The gold for a dungeon enemy on the current floor."""
        base = DUNGEON_GOLD_BASE * (DUNGEON_GOLD_GROWTH ** max(0, self._floor - 1))
        return base * edef.gold_mult

    # -----------------------------------------------------------------
    # Spawning (reuses engine.enemy.spawn_enemy / spawn_boss)
    # -----------------------------------------------------------------
    def spawn_enemy(self) -> None:
        """Spawn a fire-themed dungeon enemy into the dungeon world.

        Reuses ``engine.enemy.spawn_enemy`` (the existing spawn function)
        with a fire-themed EnemyDef from ``DUNGEON_ENEMIES``. The enemy's
        ``element`` is "fire" (copied from the EnemyDef at spawn time).
        """
        edef = rng().choice(DUNGEON_ENEMIES)
        e = spawn_enemy(edef, hp=self._floor_hp(edef),
                        dmg=self._floor_dmg(edef),
                        gold=self._floor_gold(edef))
        self.world.enemies.append(e)

    def spawn_boss(self) -> None:
        """Spawn the fire-themed dungeon boss into the dungeon world.

        Reuses ``engine.enemy.spawn_boss`` (the existing spawn function)
        with the fire-themed ``DUNGEON_BOSS`` EnemyDef. The boss's
        ``element`` is "fire" (copied from the EnemyDef at spawn time).
        """
        bdef = DUNGEON_BOSS
        boss = spawn_boss(bdef, hp=self._floor_hp(bdef),
                          dmg=self._floor_dmg(bdef),
                          gold=self._floor_gold(bdef))
        self.world.enemies.append(boss)
        self._boss_active = True
        # Boss intro FX: emit via the dungeon's bus.
        self.bus.emit("boss_spawn", boss.name, boss.hue)

    # -----------------------------------------------------------------
    # Lifecycle (enter / exit)
    # -----------------------------------------------------------------
    def enter(self) -> bool:
        """Enter the dungeon. Returns True if entry succeeded.

        Sets ``state.dungeon_active = True``, ``state.dungeon_type =
        "story"``, and ``state.dungeon_floor = 1``. The gate
        (``can_enter_dungeon``) is a threshold check, NOT a cost —
        entering does NOT spend medals or any currency. If the player
        does not meet the gate, entry fails (returns False) and the
        state is unchanged.
        """
        if not can_enter_dungeon(self.state):
            return False
        self.state.dungeon_active = True
        self.state.dungeon_type = "story"
        self.state.dungeon_floor = 1
        self._floor = 1
        # Clear the dungeon world for a fresh dungeon run.
        self.world.enemies.clear()
        self.world.fireflies.clear()
        self._spawn_timer = 0.0
        self._boss_active = False
        return True

    def exit(self) -> None:
        """Exit the dungeon. Clears ``state.dungeon_active`` and resets
        the dungeon_floor. The road loop resumes normally after exit
        (the road was never disturbed — it kept idling while the dungeon
        was active)."""
        self.state.dungeon_active = False
        self.state.dungeon_floor = 0
        self._floor = 0
        self.world.enemies.clear()
        self._boss_active = False

    # -----------------------------------------------------------------
    # Update (composes the existing engine modules)
    # -----------------------------------------------------------------
    def update(self, dt: float, *, paused: bool = False) -> None:
        """Advance one dungeon tick.

        Composes the existing engine modules: ``tick_combat`` (combat),
        ``spawn_enemy`` / ``spawn_boss`` (spawning), ``tick_skill``
        (active skills). Does NOT duplicate the main Runner's update
        logic; the dungeon drives its own World instance. The road loop
        is undisturbed (the road's World is a separate instance; the
        DungeonRunner does not touch the road's World).
        """
        if paused or not self.state.dungeon_active:
            return
        evo = aggregate_bonuses(self.state)

        # Spawn enemies on the dungeon's own interval (separate from the
        # road's spawn timer). The dungeon spawns up to 6 enemies at a
        # time, then the boss once the floor is "cleared" (no more
        # regular enemies). The boss gates the next floor.
        if not self._boss_active:
            self._spawn_timer += dt
            # The dungeon spawn interval is a fixed 1.0s (the dungeon is
            # a tighter, more intense loop than the road).
            interval = 1.0
            while self._spawn_timer >= interval:
                self._spawn_timer -= interval
                if len(self.world.enemies) < 6:
                    self.spawn_enemy()
            # If the spawn cap is reached and all enemies are dead, spawn
            # the boss (the floor's capstone). This advances the floor
            # when the boss is killed (see ``_on_enemy_killed``).
            if (len(self.world.enemies) >= 6
                    and all(not e.alive for e in self.world.enemies)
                    and not any(e.is_boss for e in self.world.enemies)):
                self.spawn_boss()

        # Combat: reuse ``tick_combat`` from engine.enemy. The dungeon
        # passes ``attuned=self.state.attuned_element`` so the Godai type
        # chart applies to dungeon enemies the same way it applies to
        # road enemies (the dungeon reuses the Godai type chart, NOT a
        # separate system).
        combo_m = self._combo_mult()
        gold_m = self._gold_mult()
        auto_active = self.state.energy_active

        def on_kill(enemy: Enemy) -> None:
            self._on_enemy_killed(enemy, combo_m, gold_m, evo)

        tick_combat(self.ninja, self.world.enemies, dt,
                    combo_mult=combo_m, gold_mult=gold_m,
                    auto_active=auto_active, on_kill=on_kill,
                    attuned=self.state.attuned_element)

        # Cull dead enemies after their death-fade window (mirrors the
        # road's cull so corpses don't clog the dungeon's spawn cap).
        self.world.enemies = [e for e in self.world.enemies
                             if e.alive or e.last_damage_timer > -0.3]

        # Active skills tick (reuse ``tick_skill`` from engine.skills).
        for sk in self.skills.values():
            tick_skill(sk, dt)

        # Energy / Auto Katana (the dungeon shares the player's energy
        # pool — the dungeon is a track on the same run, not a separate
        # mode). Mirrors the road's energy drain so the auto-katana
        # depletes while the dungeon is active.
        if self.state.energy_active:
            self.state.energy -= dt
            if self.state.energy <= 0:
                self.state.energy = 0
                self.state.energy_active = False
                self.state.energy_lockout = 5.0
        elif self.state.energy_lockout > 0:
            self.state.energy_lockout -= dt
        else:
            regen = (1.0 + evo.get("energy_regen", 0.0)) * 0.5
            self.state.energy = min(self.state.energy_max,
                                    self.state.energy + regen * dt)

        # Ninja respawn (the dungeon shares the ninja — a death in the
        # dungeon respawns the ninja the same way the road does).
        if not self.ninja.alive:
            self.ninja.alive = True
            revive_pct = evo.get("revive_pct", 0.0)
            self.ninja.hp = self.ninja.max_hp * min(1.0, 0.3 + revive_pct)
            self.state.combo = 0
            self.state.combo_charges = 0
            self.state.combo_timer = 0.0

        # Combo decay (the dungeon shares the combo — a kill in the
        # dungeon refreshes the combo the same way a road kill does).
        if self.state.combo > 0:
            self.state.combo_timer -= dt * self._combo_decay_rate()
            if self.state.combo_timer <= -self._combo_grace():
                self.state.combo = 0
                self.state.combo_charges = 0

    # -----------------------------------------------------------------
    # Kill handling (routes through the normal kill path)
    # -----------------------------------------------------------------
    def _on_enemy_killed(self, enemy: Enemy, combo_m: float,
                        gold_m: float, evo: dict) -> None:
        """Route a dungeon kill through the normal kill path.

        Reuses the same gold/combo/monster-count logic as the road's
        ``Runner._on_enemy_killed`` so monsters_killed, gold, and combo
        all fire — the dungeon does NOT bypass the kill path. The
        dungeon boss advances ``state.dungeon_floor`` by 1 (the next
        floor); the dungeon is floor-based progression, not zone-based.
        """
        gold = enemy.gold * combo_m * gold_m
        self._award_gold(gold)
        self.state.monsters_killed += 1
        self.state.kills_today += 1
        # Combo increment + grace-window restore. The combo_window run
        # upgrade extends the refresh window (same term as the road's
        # ``_on_enemy_killed``): the skill-tree bonus (evo) AND the run
        # upgrade (``_upgrade_val``) both apply.
        prev_combo = self.state.combo
        self.state.combo += 1
        self.state.combo_timer = (COMBO_WINDOW
                                  + evo.get("combo_window", 0.0)
                                  + _upgrade_val(self.state, "combo_window"))
        if self.state.combo > self.state.best_combo_ever:
            self.state.best_combo_ever = self.state.combo
        if self.state.combo > self.state.best_combo_today:
            self.state.best_combo_today = self.state.combo
        # Combo charge banking (reuse the same milestones as the road).
        for m in _COMBO_MILESTONES:
            if prev_combo < m <= self.state.combo:
                self.state.combo_charges += 1
                break
        # Boss kill: advance the dungeon floor (the dungeon is floor-
        # based progression). The boss is NOT a zone boss (the dungeon
        # does not advance the road's zone_index); it advances the
        # dungeon's own floor counter.
        if enemy.is_boss:
            self.state.bosses_killed += 1
            self.state.dungeon_floor += 1
            self._floor = self.state.dungeon_floor
            self._boss_active = False
        # Energy-from-kill (mirror the road's path).
        if evo.get("energy_from_kill", 0.0) > 0 and not self.state.energy_active:
            self.state.energy = min(self.state.energy_max,
                                   self.state.energy + evo["energy_from_kill"])

    def _award_gold(self, amount: float) -> None:
        self.state.gold += amount
        self.state.lifetime_gold += amount
        self.state.gold_earned_today += amount

    # -----------------------------------------------------------------
    # Combo + gold helpers (reuse the same formulas as the road)
    # -----------------------------------------------------------------
    def _combo_mult(self) -> float:
        """The combo multiplier (reuses the road's formula so the
        dungeon's combo scales the same way the road's does)."""
        c = self.state.combo
        tau = cfg.COMBO_TAU - _upgrade_val(self.state, "combo_step")
        evo = aggregate_bonuses(self.state)
        tau -= evo.get("combo_step_pct", 0.0) * cfg.COMBO_TAU
        tau = max(5.0, tau)
        return 1.0 + (COMBO_MULT_CAP - 1.0) * (1.0 - math.exp(-c / tau))

    def _gold_mult(self) -> float:
        evo = aggregate_bonuses(self.state)
        return (1.0 + evo.get("gold_pct", 0.0) + evo.get("godai_fire", 0.0)
                + _upgrade_pct(self.state, "gold_drop")
                + evo.get("coin_token_pct", 0.0))

    def _combo_grace(self) -> float:
        evo = aggregate_bonuses(self.state)
        grace_pct = evo.get("combo_grace_pct", 0.0)
        return (COMBO_GRACE + _upgrade_val(self.state, "combo_grace")) * (1.0 + grace_pct)

    def _combo_decay_rate(self) -> float:
        sustain = _upgrade_val(self.state, "combo_sustain")
        return max(0.5, 1.0 - sustain)

    def _skill_damage_mult(self) -> float:
        """The skill damage multiplier from the ``skill_dmg`` run upgrade.

        Mirrors the road's ``skill_damage_mult`` so the dungeon's skills
        scale the same way the road's do. The upgrade resets on ascension.
        """
        return 1.0 + _upgrade_val(self.state, "skill_dmg")

    def _skill_cooldown_mult(self) -> float:
        """The skill cooldown multiplier from the ``skill_cd`` run upgrade.

        Mirrors the road's ``skill_cooldown_mult`` so the dungeon's skill
        cooldowns scale the same way the road's do (capped at 0.5 so
        cooldowns never drop below half). The upgrade resets on ascension.
        """
        cd = _upgrade_val(self.state, "skill_cd")
        return max(0.5, 1.0 - cd)

    # -----------------------------------------------------------------
    # Player actions (reuse the same tap / skill logic as the road)
    # -----------------------------------------------------------------
    def tap(self) -> None:
        """The player taps in the dungeon — deal tap damage to the
        nearest dungeon enemy. Reuses ``engine.enemy.tap`` (the existing
        tap function) so the tap respects the Godai type chart (the
        dungeon reuses the Godai type chart, NOT a separate system)."""
        if not self.ninja.alive:
            return
        combo_m = self._combo_mult()
        gold_m = self._gold_mult()
        evo = aggregate_bonuses(self.state)
        tap_enemy(self.ninja, self.world.enemies,
                  combo_mult=combo_m, gold_mult=gold_m,
                  on_kill=lambda e: self._on_enemy_killed(e, combo_m, gold_m, evo),
                  attuned=self.state.attuned_element)

    def activate_skill(self, sid: str) -> None:
        """Fire an active skill in the dungeon. Reuses the same skill
        logic as the road (the dungeon does NOT duplicate the skill
        logic; it fires the same ActiveSkill instances). The
        ``skill_dmg`` run upgrade multiplies the damage dealt by all
        damage skills (kunai/shuriken), same as the road."""
        sk = self.skills.get(sid)
        if sk is None or not can_fire(sk):
            return
        fire_skill(sk)
        self.state.skills_used_today += 1
        combo_m = self._combo_mult()
        gold_m = self._gold_mult()
        skill_m = self._skill_damage_mult()  # Task 22: skill_dmg upgrade
        # The dungeon's skill effects mirror the road's (the same skills
        # the road uses). The dungeon's world is the target list; the
        # skill_dmg multiplier applies on top of the tap/auto * combo
        # stack so it composes cleanly (same as the road).
        from engine.enemy import _apply_damage
        if sid == "kunai":
            targets = sorted([e for e in self.world.enemies if e.alive],
                              key=lambda e: e.x)[:5]
            for t in targets:
                dmg = self.ninja.tap_damage * 3 * combo_m * skill_m
                _apply_damage(t, dmg, is_crit=True,
                              attuned=self.state.attuned_element)
                if not t.alive:
                    self._on_enemy_killed(t, combo_m, gold_m,
                                          aggregate_bonuses(self.state))
        elif sid == "shuriken":
            for t in self.world.enemies:
                if t.alive:
                    dmg = self.ninja.auto_damage * 2 * combo_m * skill_m
                    _apply_damage(t, dmg,
                                  attuned=self.state.attuned_element)
                    if not t.alive:
                        self._on_enemy_killed(t, combo_m, gold_m,
                                              aggregate_bonuses(self.state))
        elif sid == "rope":
            targets = [e for e in self.world.enemies if e.alive and not e.is_boss]
            if targets:
                t = min(targets, key=lambda e: e.hp)
                t.alive = False
                t.hp = 0
                self._on_enemy_killed(t, combo_m, gold_m,
                                      aggregate_bonuses(self.state))
        elif sid == "speed":
            self.state.energy_active = True
            self.state.energy = max(self.state.energy, 8.0)
