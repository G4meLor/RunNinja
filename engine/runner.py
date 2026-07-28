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
from core.quests import maybe_refresh_dailies, update_daily_progress, check_achievements
from engine.ninja import Ninja, make_ninja, compute_ninja_stats
from engine.enemy import Enemy, tick_combat, tap as tap_enemy, PARTY_X
from engine.firefly import Firefly, update_fireflies, catch_firefly
from engine.skills import ActiveSkill, make_skill, tick_skill, can_fire, fire as fire_skill
from engine.world import World
from engine.eventbus import EventBus
from engine.fx import FXLayer
from engine.death_fx import DeathFxSystem
from engine.combo_fx import ComboFxSystem
from engine.ninja_fx import NinjaFxSystem
from engine.skill_fx import SkillFxSystem
from engine.zone_fx import ZoneFxSystem
from engine.boss_fx import BossFxSystem
from engine.firefly_fx import FireflyFxSystem


COMBO_WINDOW = 3.0       # seconds before combo decays
COMBO_MULT_CAP = 3.0     # asymptotic ceiling for the combo multiplier


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
        self.bus.on("enemy_dmg", self._on_enemy_dmg)
        self.bus.on("ninja_dmg", self._on_ninja_dmg)
        self.bus.on("boss_spawn", self._on_boss_spawn)
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
        self.world.on_firefly_spawn = lambda *a, **k: self.bus.emit("firefly_spawn", *a, **k)
        # Notifications for the UI.
        self.notifications: list[tuple[str, float, tuple]] = []
        self.last_loot: dict = {}

    def _refresh_skills(self) -> None:
        """Rebuild the active-skill set from unlocked skill-tree nodes."""
        self.skills.clear()
        for sid in ("kunai", "shuriken", "rope", "speed"):
            unlock_node = {
                "kunai": "ab_root", "shuriken": "ab_shuriken",
                "rope": "ab_rope", "speed": "ab_speed",
            }[sid]
            if unlock_node in self.state.skill_tree:
                self.skills[sid] = make_skill(sid)

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

    # -----------------------------------------------------------------
    # Combo
    # -----------------------------------------------------------------
    def combo_mult(self) -> float:
        c = self.state.combo
        tau = cfg.COMBO_TAU - _upgrade_val(self.state, "combo_step")
        tau = max(5.0, tau)  # floor so the ramp never becomes instant
        # Asymptotic approach to the multiplier ceiling: at c=0 the
        # multiplier is 1.0; as c -> inf it approaches COMBO_MULT_CAP.
        # The bonus above the 1.0x base is (COMBO_MULT_CAP - 1.0), so the
        # total multiplier is structurally capped at COMBO_MULT_CAP.
        return 1.0 + (COMBO_MULT_CAP - 1.0) * (1.0 - math.exp(-c / tau))

    def gold_mult(self) -> float:
        evo = aggregate_bonuses(self.state)
        return (1.0 + evo.get("gold_pct", 0.0) + evo.get("godai_fire", 0.0)
                + _upgrade_pct(self.state, "gold_drop"))

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

        def on_kill(enemy: Enemy) -> None:
            self._on_enemy_killed(enemy, combo_m, gold_m, evo)

        tick_combat(self.ninja, self.world.enemies, dt,
                    combo_mult=combo_m, gold_mult=gold_m,
                    auto_active=auto_active, on_kill=on_kill)

        # Cull dead enemies after their death-fade window so corpses don't
        # clog the spawn cap (the old C1 bug).  last_damage_timer is
        # decremented for ALL enemies in tick_combat, so a dead enemy
        # reaches -0.3 within ~0.9s of death and is dropped here.
        self.world.enemies = [e for e in self.world.enemies
                              if e.alive or e.last_damage_timer > -0.3]

        # Combo decay.
        if self.state.combo > 0:
            self.state.combo_timer -= dt
            if self.state.combo_timer <= 0:
                self.state.combo = 0

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
            self.state.combo = 0
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
        self.state.combo += 1
        self.state.combo_timer = COMBO_WINDOW + evo.get("combo_window", 0.0) + _upgrade_val(self.state, "combo_window")
        if self.state.combo > self.state.best_combo_ever:
            self.state.best_combo_ever = self.state.combo
        if self.state.combo > self.state.best_combo_today:
            self.state.best_combo_today = self.state.combo
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
            self.notify(f"Boss slain: {enemy.name}!", (255, 220, 120))
            self.boss_fx.stop()
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
    # Player actions
    # -----------------------------------------------------------------
    def tap(self) -> None:
        """The player taps the screen — deal tap damage to the nearest enemy."""
        if not self.ninja.alive:
            return
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        target = tap_enemy(self.ninja, self.world.enemies,
                           combo_mult=combo_m, gold_mult=gold_m,
                           on_kill=lambda e: self._on_enemy_killed(e, combo_m, gold_m, aggregate_bonuses(self.state)))
        # Also try to catch a firefly near the tap.
        # (The UI passes the tap position; here we approximate with nearest.)

    def tap_at(self, x: float, y: float) -> None:
        """Tap at a specific position — catch fireflies there, else hit nearest enemy."""
        # Firefly catch first.
        evo = aggregate_bonuses(self.state)
        for f in self.world.fireflies[:]:
            if abs(f.x - x) < 20 + f.size and abs(f.y - y) < 20 + f.size:
                gold = catch_firefly(f, base_gold=50 * (1 + self.state.zone_index * 0.5),
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
        """Fire an active skill if unlocked and off cooldown."""
        sk = self.skills.get(sid)
        if sk is None or not can_fire(sk):
            return
        fire_skill(sk)
        self.state.skills_used_today += 1
        combo_m = self.combo_mult()
        gold_m = self.gold_mult()
        # Skill VFX.
        self.skill_fx.trigger(sid, self.ninja.x, self.ninja.y, self.world.enemies)
        if sid == "kunai":
            # Burst damage to the nearest 5 enemies.
            targets = sorted([e for e in self.world.enemies if e.alive], key=lambda e: e.x)[:5]
            for t in targets:
                from engine.enemy import _apply_damage
                dmg = self.ninja.tap_damage * 3 * combo_m
                _apply_damage(t, dmg, is_crit=True)
                if not t.alive:
                    self._on_enemy_killed(t, combo_m, gold_m, aggregate_bonuses(self.state))
            self.notify("Kunai Barrage!", (255, 120, 110))
        elif sid == "shuriken":
            # AOE all enemies.
            from engine.enemy import _apply_damage
            for t in self.world.enemies:
                if t.alive:
                    dmg = self.ninja.auto_damage * 2 * combo_m
                    _apply_damage(t, dmg)
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
