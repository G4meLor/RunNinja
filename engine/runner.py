"""Runner: the top-level simulation driver for Tap Ninja.

Ties the world, ninja, combat, fireflies, active skills, and energy
together.  Owns the FX layer and routes kills to loot + combo + zone
progression.  Exposes a single ``update(dt)`` the main loop calls.
"""
from __future__ import annotations

import math

import config as cfg
from core.state import GameState
from utils import rng
from core.bonuses import aggregate_bonuses
from core.quests import maybe_refresh_dailies, update_daily_progress, check_achievements, award_boss_token
from engine.ninja import Ninja, make_ninja, compute_ninja_stats
from engine.enemy import Enemy, tick_combat, tap as tap_enemy, nearest_enemy, PARTY_X
from engine.firefly import Firefly, update_fireflies, catch_firefly
from engine.skills import ActiveSkill, make_skill, tick_skill, can_fire, fire as fire_skill
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

        # Ninja respawn.
        if not self.ninja.alive:
            self.ninja.alive = True
            self.ninja.hp = self.ninja.max_hp * 0.3
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
        # Restore the ninja's real crit_chance (the override was only
        # for this tap).
        self.ninja.crit_chance = _saved_crit_chance
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
            self.state.energy_active = True
            self.state.energy = max(self.state.energy, 8.0)
            self.notify("Speed Step!", (255, 240, 120))

    def toggle_energy(self) -> None:
        if self.state.energy_active:
            self.state.energy_active = False
            self.state.energy_lockout = 5.0
        elif self.state.energy > 0 and self.state.energy_lockout <= 0:
            self.state.energy_active = True
            self.notify("Auto Katana engaged!", (130, 230, 160))

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
        # Clear all FX.
        self.fx.texts.clear()
        self.death_fx.fx.clear()
        self.combo_fx.reset()
        self.ninja_fx._arcs.clear() if hasattr(self.ninja_fx, '_arcs') else None
        self.skill_fx.effects.clear() if hasattr(self.skill_fx, 'effects') else None


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
