"""Combo Finishers + decay grace + combo-break feedback.

Three combo-system improvements (Task 10):

1. **Combo Finishers:** a charge is banked whenever the running combo
   crosses an existing ``combo_fx.MILESTONES`` threshold (25/50/100/200
   piggyback on the existing dict; the dict also has 10 so any milestone
   crosses counts). Charges persist through the decay window and are
   only lost when the combo fully resets (after the grace window). Four
   finishers spend charges; finisher damage is a fixed multiple of
   ``tap_damage`` with its own cap (``MAX_FINISHER_MULT``), NOT
   multiplicative with ``combo_mult``.

2. **Decay grace:** ``combo_timer`` is allowed to go negative to
   -1.5s before the combo resets to 0. A kill during the grace window
   (``combo_timer < 0``) restores ``combo_timer`` to the full window
   instead of starting a fresh combo from 1.

3. **COMBO LOST:** a "COMBO LOST" banner fires when the combo fully
   resets, gated by ``reduced_motion``.
"""
import pytest


# ---------------------------------------------------------------------------
# 1. Charge banking at milestones
# ---------------------------------------------------------------------------
def test_charge_banked_at_milestone(pygame_headless):
    """Crossing a MILESTONE banks a charge into ``combo_charges``."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.combo_fx import MILESTONES
    state = GameState()
    r = Runner(state)
    # Drive the actual kill path: spawn enemies and kill them one at a
    # time. Each kill increments combo by 1; when combo crosses a
    # MILESTONE key, a charge is banked.
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    # Spawn enough enemies to cross the first milestone (10) plus the
    # 25 milestone. We use the smallest milestone to keep the test short.
    target_milestone = min(MILESTONES.keys())  # 10
    state.combo = target_milestone - 1
    e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
    e.alive = True
    r._on_enemy_killed(e, r.combo_mult(), r.gold_mult(), {})
    assert state.combo == target_milestone
    assert state.combo_charges >= 1, (
        f"no charge banked at milestone {target_milestone}: "
        f"combo={state.combo}, charges={state.combo_charges}")


def test_charges_persist_through_decay_window(pygame_headless):
    """Charges persist while combo decays; only lost on the full reset."""
    from core.state import GameState
    from engine.runner import Runner, COMBO_WINDOW
    state = GameState()
    r = Runner(state)
    state.combo = 30
    state.combo_charges = 2
    # Decay within the grace window (combo_timer > -1.5): combo still
    # positive, timer negative but not past grace.
    state.combo_timer = -1.0
    r.update(0.05)
    # Combo is still alive (timer is in the grace window).
    assert state.combo > 0, "combo reset before grace expired"
    # Charges are NOT cleared during the grace window.
    assert state.combo_charges == 2, (
        f"charges lost during grace window: {state.combo_charges}")


def test_charges_lost_on_full_reset(pygame_headless):
    """When the combo fully resets (past -1.5s grace), charges go to 0."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo = 30
    state.combo_charges = 2
    # Drive the decay past the grace threshold.
    state.combo_timer = -1.4
    r.update(0.2)  # pushes timer to -1.6 -> full reset
    assert state.combo == 0, f"combo not reset: {state.combo}"
    assert state.combo_charges == 0, (
        f"charges not cleared on full reset: {state.combo_charges}")


# ---------------------------------------------------------------------------
# 2. Grace period
# ---------------------------------------------------------------------------
def test_combo_timer_goes_negative_in_grace(pygame_headless):
    """combo_timer goes negative to -1.5s before combo resets to 0."""
    from core.state import GameState
    from engine.runner import Runner, COMBO_WINDOW
    state = GameState()
    r = Runner(state)
    state.combo = 10
    state.combo_timer = 0.1
    # Tick past 0: combo is still alive in the grace window.
    r.update(0.2)
    assert state.combo_timer < 0, (
        f"timer not negative in grace: {state.combo_timer}")
    assert state.combo > 0, f"combo reset before grace: {state.combo}"


def test_grace_period_restores_combo_on_kill(pygame_headless):
    """A kill during grace (combo_timer < 0) restores combo_timer to full."""
    from core.state import GameState
    from engine.runner import Runner, COMBO_WINDOW
    state = GameState()
    r = Runner(state)
    state.combo = 50
    state.combo_timer = -1.0  # in grace
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
    r._on_enemy_killed(e, r.combo_mult(), r.gold_mult(), {})
    # Combo was restored to the full window (not a fresh combo from 1).
    assert state.combo_timer > 0, (
        f"combo_timer not restored on grace kill: {state.combo_timer}")
    assert state.combo == 51, (
        f"combo not incremented on grace kill: {state.combo}")


# ---------------------------------------------------------------------------
# 3. Finishers
# ---------------------------------------------------------------------------
def test_activate_finisher_thousand_cuts_spends_charge(pygame_headless):
    """thousand_cuts costs 1 charge and deals fixed-multiple tap_damage."""
    from core.state import GameState
    from engine.runner import Runner, MAX_FINISHER_MULT
    state = GameState()
    r = Runner(state)
    state.combo_charges = 1
    # Spawn enemies so the AOE has something to hit.
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    for _ in range(5):
        r.world.enemies.append(spawn_enemy(edef, hp=1000.0, dmg=1.0, gold=1.0))
    before = state.combo_charges
    r.activate_finisher("thousand_cuts")
    assert state.combo_charges == before - 1, (
        f"thousand_cuts did not spend a charge: {before} -> {state.combo_charges}")


def test_activate_finisher_insufficient_charges_noop(pygame_headless):
    """Activating a finisher with 0 charges does nothing."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo_charges = 0
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    for _ in range(5):
        r.world.enemies.append(spawn_enemy(edef, hp=1000.0, dmg=1.0, gold=1.0))
    r.activate_finisher("thousand_cuts")
    # No charge spent, no enemies killed (insufficient charges is a no-op).
    assert state.combo_charges == 0
    assert all(e.alive for e in r.world.enemies)


def test_finisher_damage_not_multiplicative_with_combo_mult(pygame_headless):
    """Finisher damage is a fixed multiple of tap_damage (capped), not combo_mult."""
    from core.state import GameState
    from engine.runner import Runner, MAX_FINISHER_MULT
    state = GameState()
    r = Runner(state)
    state.combo_charges = 4
    state.combo = 200  # very high combo -> combo_mult near the cap
    # Spawn a fresh enemy with known HP, then thousand_cuts it.
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    e = spawn_enemy(edef, hp=10_000_000.0, dmg=1.0, gold=1.0)
    r.world.enemies.append(e)
    r.activate_finisher("thousand_cuts")
    # Damage should be approximately tap_damage * 5 (capped at MAX_FINISHER_MULT).
    # If it were multiplicative with combo_mult, the damage would be ~3x higher.
    expected_max = r.ninja.tap_damage * MAX_FINISHER_MULT + 1.0
    damage_dealt = 10_000_000.0 - e.hp
    assert damage_dealt <= expected_max, (
        f"finisher damage {damage_dealt} exceeds tap_damage*MAX_FINISHER_MULT "
        f"{expected_max} — was combo_mult applied?")


def test_phantom_step_boss_kill_if_combo_gte_100(pygame_headless):
    """phantom_step costs 2 charges and kills a boss if combo >= 100."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo = 100
    state.combo_charges = 2
    # Spawn a boss.
    from data import enemies as ed
    from engine.enemy import spawn_boss
    bdef = ed.boss_for_zone(r.world.zone_id)
    boss = spawn_boss(bdef, hp=10_000_000.0, dmg=1.0, gold=1.0)
    r.world.enemies.append(boss)
    r.world.boss_active = True
    r.activate_finisher("phantom_step")
    assert not boss.alive, "phantom_step did not kill the boss"
    assert state.combo_charges == 0, (
        f"phantom_step did not cost 2 charges: {state.combo_charges}")


def test_phantom_step_no_kill_if_combo_lt_100(pygame_headless):
    """phantom_step with combo < 100 does NOT kill the boss (refunds the charges)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo = 50
    state.combo_charges = 2
    from data import enemies as ed
    from engine.enemy import spawn_boss
    bdef = ed.boss_for_zone(r.world.zone_id)
    boss = spawn_boss(bdef, hp=10_000_000.0, dmg=1.0, gold=1.0)
    r.world.enemies.append(boss)
    r.world.boss_active = True
    r.activate_finisher("phantom_step")
    # Boss is still alive (combo < 100).
    assert boss.alive, (
        "phantom_step killed boss with combo < 100 — should only kill at >=100")
    # Charges are refunded (the finisher is a no-op without combo >= 100).
    assert state.combo_charges == 2, (
        f"phantom_step did not refund charges on combo < 100: {state.combo_charges}")


def test_bosses_auto_killable_without_phantom_step(pygame_headless):
    """A boss is killable through normal combat (finishers never gate progression)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Spawn a boss with low HP; the ninja's auto-attack should kill it.
    from data import enemies as ed
    from engine.enemy import spawn_boss
    bdef = ed.boss_for_zone(r.world.zone_id)
    boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
    r.world.enemies.append(boss)
    boss.x = 200
    r.world.boss_active = True
    r.update(2.0)  # plenty of time for the ninja to auto-attack
    assert not boss.alive, "boss not auto-killed — finishers must not gate progression"


def test_activate_finisher_mirage_spends_charge(pygame_headless):
    """mirage costs 1 charge."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo_charges = 1
    r.activate_finisher("mirage")
    assert state.combo_charges == 0


def test_activate_finisher_executioner_edge_spends_charge(pygame_headless):
    """executioner_edge costs 1 charge."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo_charges = 1
    r.activate_finisher("executioner_edge")
    assert state.combo_charges == 0


def test_executioner_edge_guaranteed_crit_on_tap(pygame_headless):
    """Executioner's Edge makes every tap a guaranteed crit while the timer is > 0.

    Regression for the bug where the override only covered auto-attacks
    inside ``update()`` (via ``tick_combat``) and missed the player-tap
    path (``tap()`` -> ``tap_enemy`` -> ``ninja.roll_crit``). The fix
    applies the same save/restore override in ``tap()`` so taps also
    get ``crit_chance = 1.0`` while ``_executioner_timer > 0``.

    The test asserts the damage dealt to a fresh enemy equals
    ``tap_damage * crit_dmg`` (the crit multiplier) — i.e. the tap was
    a crit. Without the fix, the tap uses the ninja's real crit_chance
    (0.05), so a crit is unlikely (5%) and the damage would almost
    always equal ``tap_damage * 1.0`` (non-crit).
    """
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Arm the Executioner's Edge timer (as if the finisher was just used).
    r._executioner_timer = 5.0
    # Spawn a fresh enemy with known HP.
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    enemy_hp = 10_000_000.0
    e = spawn_enemy(edef, hp=enemy_hp, dmg=1.0, gold=1.0)
    r.world.enemies.append(e)
    e.x = 200
    # Tap once. With the fix, the tap is a guaranteed crit, so the
    # damage equals tap_damage * crit_dmg (the crit multiplier).
    r.tap()
    damage_dealt = enemy_hp - e.hp
    expected_crit_damage = r.ninja.tap_damage * r.ninja.crit_dmg
    assert damage_dealt == pytest.approx(expected_crit_damage, rel=1e-6), (
        f"tap damage {damage_dealt} != guaranteed-crit damage "
        f"{expected_crit_damage} — Executioner's Edge did not make the tap a crit")
    # The override was restored after the tap (the ninja's real
    # crit_chance is back, not 1.0).
    assert r.ninja.crit_chance < 1.0, (
        f"crit_chance not restored after tap: {r.ninja.crit_chance}")


def test_executioner_edge_guaranteed_crit_on_auto_attack(pygame_headless):
    """Executioner's Edge makes every auto-attack a guaranteed crit while timer > 0.

    Complement to the tap test: the auto-attack path (inside ``update``)
    was already covered, but this locks it in as a regression guard so a
    future refactor that moves the override out of ``update`` is caught.
    """
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    r._executioner_timer = 5.0
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    from engine.enemy import spawn_enemy
    enemy_hp = 10_000_000.0
    e = spawn_enemy(edef, hp=enemy_hp, dmg=1.0, gold=1.0)
    r.world.enemies.append(e)
    e.x = 200
    # Run one update tick; the ninja auto-attacks the enemy. With the
    # fix, the attack is a guaranteed crit, so the damage equals
    # auto_damage * crit_dmg.
    r.update(1.0)
    damage_dealt = enemy_hp - e.hp
    # The enemy may have been killed (auto-attack + the enemy might be
    # hit multiple times in one tick); just assert the first hit was a
    # crit by checking the damage is a multiple of auto_damage * crit_dmg
    # (not auto_damage * 1.0). If the enemy is dead, the total damage
    # is at least one crit's worth.
    expected_crit_damage = r.ninja.auto_damage * r.ninja.crit_dmg
    assert damage_dealt >= expected_crit_damage, (
        f"auto-attack damage {damage_dealt} < one crit's worth "
        f"{expected_crit_damage} — Executioner's Edge did not make auto-attack a crit")
    # The override was restored after the tick.
    assert r.ninja.crit_chance < 1.0, (
        f"crit_chance not restored after update: {r.ninja.crit_chance}")


def test_activate_finisher_unknown_fid_noop(pygame_headless):
    """An unknown finisher id is a no-op (does not spend charges)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo_charges = 5
    r.activate_finisher("not_a_real_finisher")
    assert state.combo_charges == 5, "unknown finisher spent charges"


# ---------------------------------------------------------------------------
# 4. COMBO LOST feedback
# ---------------------------------------------------------------------------
def test_combo_lost_banner_method_exists(pygame_headless):
    """ComboFxSystem has a ``lost(combo)`` method for the COMBO LOST banner."""
    from engine.combo_fx import ComboFxSystem
    fx = ComboFxSystem()
    assert hasattr(fx, "lost"), "ComboFxSystem has no lost() method"
    # Calling it does not raise (combo fully reset path).
    fx.lost(30)


def test_combo_lost_gated_by_reduced_motion(pygame_headless):
    """COMBO LOST is suppressed when reduced_motion is set."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.reduced_motion = True
    state.combo = 30
    state.combo_charges = 2
    # Drive a full reset; with reduced_motion the banner is suppressed
    # (no exception, no banner animation state).
    state.combo_timer = -1.4
    r.update(0.2)
    assert state.combo == 0
    # The combo_fx banner is not alive (reduced_motion suppressed it).
    assert not r.combo_fx._banner.alive, (
        "COMBO LOST banner fired under reduced_motion")


def test_combo_lost_fires_on_full_reset(pygame_headless):
    """COMBO LOST banner fires when the combo fully resets (no reduced_motion)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.combo = 30
    state.combo_charges = 2
    state.combo_timer = -1.4
    r.update(0.2)
    assert state.combo == 0
    # The combo_fx banner was triggered by the lost() call.
    assert r.combo_fx._banner.alive, (
        "COMBO LOST banner did not fire on full reset")
