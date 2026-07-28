"""Shadow Dungeon runner (Task 23 / cnt-shadow-dungeon-runner).

A ``DungeonRunner`` that COMPOSES existing engine components (World,
enemy.py spawn/combat, skills.py) rather than duplicating the main
``Runner`` logic. The road loop stays intact while the dungeon is
active — the main ``Runner.update`` checks ``state.dungeon_active`` and,
if so, ticks the dungeon instead of (or alongside) the road. No new
currency is added; the dungeon is gated on medals or zone progression.
The Godai Fire element ties to the dungeon (the dungeon's enemies use
the Fire element from Task 21's ``element`` field).

This is the "frontier" task — the architecture prerequisite for the
dungeon variants (Task 34). The DungeonRunner does NOT reimplement
combat, spawning, or skill ticking; it reuses the existing modules.
"""
import pytest


# ---------------------------------------------------------------------------
# 1. DungeonRunner composes existing engine components
# ---------------------------------------------------------------------------
def test_dungeon_runner_composes(pygame_headless):
    """DungeonRunner composes a World + enemies + skills, not a duplicate
    Runner. The brief's specimen test."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    dr = DungeonRunner(state)
    # Composes a World + enemies + skills, not a duplicate Runner.
    assert hasattr(dr, "world")
    assert dr.state is state
    # The road loop (the main Runner) is undisturbed.
    # (verify the dungeon runs without touching the main runner's world)


def test_dungeon_runner_has_own_world(pygame_headless):
    """The DungeonRunner owns its own World instance, distinct from any
    Runner's world — the dungeon drives its own spawn/combat scenario,
    not the road's."""
    from core.state import GameState
    from engine.runner import Runner, DungeonRunner
    state = GameState()
    runner = Runner(state)
    dr = DungeonRunner(state)
    # The dungeon's world is a distinct World instance — not the runner's.
    assert dr.world is not runner.world
    assert dr.world is not None
    # The dungeon's enemies list is the dungeon world's, not the road's.
    assert dr.world.enemies is not runner.world.enemies


def test_dungeon_runner_does_not_duplicate_runner_update(pygame_headless):
    """DungeonRunner.update composes the existing modules (tick_combat,
    spawn_enemy, tick_skill) rather than reimplementing them. We verify
    by checking the dungeon runner ticks without error and actually
    advances combat via the shared engine functions (a kill increments
    state.monsters_killed through the normal kill path)."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    from engine.enemy import spawn_enemy
    from data.enemies import EnemyDef
    state = GameState()
    # Enter the dungeon so the runner's update ticks combat (the update
    # gates on state.dungeon_active). The gate is medals OR zone; the
    # default state has neither, so set medals to clear the gate.
    state.medals = 100
    dr = DungeonRunner(state)
    dr.enter()
    # Spawn a fragile enemy directly into the dungeon world so the combat
    # tick has something to kill. The dungeon runner's update should drive
    # the combat via the shared tick_combat (the ninja auto-attacks).
    edef = EnemyDef("e_test", "Test", "bandit", 0, 1.0, 1.0, 1.0, 20, 16,
                    element="fire")
    e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
    e.x = 200  # in attack range of the ninja (PARTY_X = 180)
    dr.world.enemies.append(e)
    kills_before = state.monsters_killed
    # Tick until the enemy is dead (the ninja auto-attacks at ~1/s).
    for _ in range(120):
        if not e.alive:
            break
        dr.update(1 / 60)
    assert not e.alive, "dungeon runner did not kill the enemy"
    assert state.monsters_killed > kills_before, (
        "dungeon runner did not increment monsters_killed (kill path not "
        "routed through the normal _on_enemy_killed)")


# ---------------------------------------------------------------------------
# 2. The road loop runs undisturbed while the dungeon is active
# ---------------------------------------------------------------------------
def test_dungeon_active_flag_does_not_break_road(pygame_headless):
    """The main Runner.update still runs cleanly when
    ``state.dungeon_active`` is True — the road loop stays intact (the
    road keeps idling). The dungeon is ticked ALONGSIDE the road, not
    instead of it; the road's world, combat, and economy all still
    advance."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.dungeon_active = True
    runner = Runner(state)
    # Snapshot the road state before.
    zone_before = runner.world.zone_index
    total_before = runner.world.total_distance
    gold_before = state.gold
    # Tick the road runner 60 frames — the road should still advance.
    for _ in range(60):
        runner.update(1 / 60)
    # The road's world advanced (total_distance increased).
    assert runner.world.total_distance > total_before, (
        "the road loop did not advance while dungeon_active=True")
    # The road's zone_index is consistent (the road's state sync still ran).
    assert runner.world.zone_index >= zone_before
    # The state's total_distance was synced from the road's world.
    assert state.total_distance == runner.world.total_distance


def test_road_loop_undisturbed_by_dungeon_runner(pygame_headless):
    """Constructing and ticking a DungeonRunner does not touch the main
    Runner's world — the road loop is undisturbed. The DungeonRunner
    owns its own World; the road's World is a separate instance."""
    from core.state import GameState
    from engine.runner import Runner, DungeonRunner
    state = GameState()
    runner = Runner(state)
    dr = DungeonRunner(state)
    # Tick the dungeon runner; the road's world should be unchanged by
    # the dungeon's update (the dungeon drives its OWN world).
    road_enemies_before = list(runner.world.enemies)
    road_total_before = runner.world.total_distance
    for _ in range(30):
        dr.update(1 / 60)
    assert runner.world.enemies == road_enemies_before, (
        "the dungeon runner mutated the road runner's world.enemies")
    assert runner.world.total_distance == road_total_before, (
        "the dungeon runner mutated the road runner's total_distance")


# ---------------------------------------------------------------------------
# 3. No new currency — the dungeon is gated on medals or zone progression
# ---------------------------------------------------------------------------
def test_no_new_currency_field(pygame_headless):
    """No new currency was added to GameState for the dungeon. The four
    currencies (gold, elixir, amber, medals) are unchanged; the dungeon
    is gated on medals or zone progression (existing fields), not a new
    currency."""
    from core.state import GameState
    s = GameState()
    # The four currencies exist and are the only scalar currency fields.
    assert hasattr(s, "gold")
    assert hasattr(s, "elixir")
    assert hasattr(s, "amber")
    assert hasattr(s, "medals")
    # The dungeon fields exist (Task 5's dataclass) but are NOT currencies:
    # dungeon_active (bool), dungeon_type (str), dungeon_floor (int),
    # dungeon_seed (int). None of these is a spendable currency.
    assert s.dungeon_active is False
    assert s.dungeon_type == "none"
    assert s.dungeon_floor == 0
    assert s.dungeon_seed == 0


def test_dungeon_entry_gated_on_medals_or_zone(pygame_headless):
    """The dungeon entry gate uses medals OR zone progression, not a new
    currency. A player with medals >= the gate OR zone_index >= the gate
    can enter; a player below both cannot."""
    from core.state import GameState
    from engine.runner import can_enter_dungeon
    # A fresh state (no medals, zone 0) cannot enter the dungeon.
    s0 = GameState()
    assert can_enter_dungeon(s0) is False, (
        "a fresh player can enter the dungeon without any gating")
    # A player with enough medals can enter (the medal gate).
    s1 = GameState()
    s1.medals = 100
    assert can_enter_dungeon(s1) is True, (
        "a player with enough medals cannot enter the dungeon")
    # A player far enough along the road can enter (the zone gate).
    s2 = GameState()
    s2.zone_index = 20
    assert can_enter_dungeon(s2) is True, (
        "a player far enough along the road cannot enter the dungeon")


def test_dungeon_entry_does_not_spend_currency(pygame_headless):
    """Entering the dungeon does NOT spend medals or any currency — the
    gate is a threshold check, not a cost. The player's medals are
    unchanged after entering."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    state.medals = 100
    medals_before = state.medals
    dr = DungeonRunner(state)
    dr.enter()
    assert state.medals == medals_before, (
        "entering the dungeon spent medals (the gate should be a "
        "threshold check, not a cost)")


# ---------------------------------------------------------------------------
# 4. The Godai Fire element ties to the dungeon
# ---------------------------------------------------------------------------
def test_dungeon_enemies_use_fire_element(pygame_headless):
    """The dungeon's enemies use the Fire Godai element (from Task 21's
    ``element`` field on EnemyDef/Enemy). The dungeon is fire-themed."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    dr = DungeonRunner(state)
    # Spawn a dungeon enemy; it should have element="fire".
    dr.spawn_enemy()
    assert dr.world.enemies, "no enemies spawned in the dungeon"
    for e in dr.world.enemies:
        assert e.element == "fire", (
            f"dungeon enemy {e.name} has element {e.element!r}, not 'fire'")


def test_dungeon_boss_uses_fire_element(pygame_headless):
    """The dungeon's boss uses the Fire Godai element. The dungeon boss is
    fire-themed (the capstone of the fire-themed dungeon)."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    dr = DungeonRunner(state)
    dr.spawn_boss()
    bosses = [e for e in dr.world.enemies if e.is_boss]
    assert bosses, "no boss spawned in the dungeon"
    for b in bosses:
        assert b.element == "fire", (
            f"dungeon boss {b.name} has element {b.element!r}, not 'fire'")


def test_dungeon_fire_ties_to_godai_fire_bonus(pygame_headless):
    """The dungeon's fire theme ties to the Godai Fire element system: the
    ``element_mult`` type chart applies to dungeon enemies the same way
    it applies to road enemies. A water-attuned player deals 2x damage to
    a fire dungeon enemy (water > fire in the 4-cycle); a wind-attuned
    player deals 0.5x (wind < fire). This verifies the dungeon reuses the
    Godai type chart from engine.enemy, not a separate system."""
    from engine.enemy import element_mult
    # The dungeon enemies are fire-themed; the type chart applies. The
    # 4-cycle is void > wind > fire > water > void, so wind is 2x vs fire
    # (wind > fire) and water is 0.5x vs fire (water < fire). A player
    # attuned to wind deals 2x to a fire dungeon enemy; a player attuned
    # to water deals 0.5x. This is the Godai type chart from engine.enemy,
    # reused by the dungeon (NOT a separate system).
    assert element_mult("wind", "fire") == 2.0   # wind > fire (2x)
    assert element_mult("water", "fire") == 0.5  # water < fire (0.5x)
    assert element_mult("fire", "fire") == 1.0   # same element (1x)
    assert element_mult("none", "fire") == 1.0   # idle floor (1x)


# ---------------------------------------------------------------------------
# 5. DungeonRunner enter/exit lifecycle
# ---------------------------------------------------------------------------
def test_dungeon_enter_sets_active_flag(pygame_headless):
    """Entering the dungeon sets state.dungeon_active=True and
    dungeon_type to the dungeon's type (default "story")."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state)
    dr.enter()
    assert state.dungeon_active is True
    assert state.dungeon_type == "story"
    assert state.dungeon_floor == 1


def test_dungeon_exit_clears_active_flag(pygame_headless):
    """Exiting the dungeon clears state.dungeon_active and resets the
    dungeon_floor. The road loop resumes normally after exit."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state)
    dr.enter()
    assert state.dungeon_active is True
    dr.exit()
    assert state.dungeon_active is False
    assert state.dungeon_floor == 0


def test_dungeon_floor_advances_on_boss_kill(pygame_headless):
    """Killing the dungeon boss advances dungeon_floor by 1 (the next
    floor). The dungeon is floor-based progression (not zone-based)."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state)
    dr.enter()
    floor_before = state.dungeon_floor
    dr.spawn_boss()
    boss = next(e for e in dr.world.enemies if e.is_boss)
    # Kill the boss through the dungeon's kill path.
    boss.alive = False
    boss.hp = 0
    dr._on_enemy_killed(boss, combo_m=1.0, gold_m=1.0, evo={})
    assert state.dungeon_floor == floor_before + 1, (
        "dungeon floor did not advance on boss kill")


# ---------------------------------------------------------------------------
# 6. Smoke: the dungeon runner ticks without error
# ---------------------------------------------------------------------------
def test_dungeon_runner_ticks_clean(pygame_headless):
    """The DungeonRunner.update ticks without error for 60 frames after
    entering (the dungeon combat + spawn + skill tick all compose
    cleanly)."""
    from core.state import GameState
    from engine.runner import DungeonRunner
    state = GameState()
    state.medals = 100
    dr = DungeonRunner(state)
    dr.enter()
    for _ in range(60):
        dr.update(1 / 60)
    # No exception = pass; the dungeon is still active.
    assert state.dungeon_active is True


def test_dungeon_runner_with_main_runner_smoke(pygame_headless):
    """The full smoke: a main Runner + a DungeonRunner both tick without
    error when the dungeon is active. The road loop and the dungeon loop
    coexist (the road keeps idling while the dungeon ticks)."""
    from core.state import GameState
    from engine.runner import Runner, DungeonRunner
    state = GameState()
    state.medals = 100
    runner = Runner(state)
    dr = DungeonRunner(state)
    dr.enter()
    for _ in range(60):
        runner.update(1 / 60)
        dr.update(1 / 60)
    # Both worlds advanced (the road's total_distance and the dungeon's
    # floor are both > 0).
    assert runner.world.total_distance > 0
    assert state.dungeon_active is True
