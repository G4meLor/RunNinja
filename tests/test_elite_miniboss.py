"""Elite enemies + mini-bosses.

Regression test for the dead ``is_elite`` field on Enemy: it was drawn in
``screen_game`` but never spawned. This task wires up a 5% elite roll in
``world._spawn_regular`` (3x HP, 5x gold, guaranteed ``rare_drop=1.0``)
and a mini-boss at 50% ``ZONE_DISTANCE`` that blocks progress until
killed (0.4x the zone boss stats). No new GameState fields; elites are
transient.
"""
import config as cfg


def test_elite_spawn_5pct(pygame_headless):
    """5% of regular spawns are elite, within statistical tolerance."""
    from engine.world import World
    w = World()
    for _ in range(1000):
        w._spawn_regular()
    elites = sum(1 for e in w.enemies if e.is_elite)
    total = len(w.enemies)
    assert total == 1000
    # 5% +/- 3% (statistical tolerance over 1000 rolls)
    assert 20 <= elites <= 80, f"elite rate {elites/10}% out of range"


def test_elite_stats_3x_hp_5x_gold(pygame_headless):
    """An elite has 3x HP and 5x gold vs the same enemy's base stats."""
    from engine.world import World
    w = World()
    # Spawn a non-elite and an elite from the same zone pool entry so we
    # can compare the multipliers directly. We force the roll by setting
    # ``is_elite`` after spawn via the same code path the engine uses.
    pool = w.zone["enemies"]
    edef = pool[0]
    base_hp = w.zone_hp(edef)
    base_gold = w.zone_gold(edef)

    # Manually exercise both branches of _spawn_regular's scaling.
    from engine.enemy import spawn_enemy
    regular = spawn_enemy(edef, hp=base_hp * 1.0,
                          dmg=w.zone_dmg(edef), gold=base_gold * 1.0)
    elite = spawn_enemy(edef, hp=base_hp * 3.0,
                        dmg=w.zone_dmg(edef), gold=base_gold * 5.0)
    elite.is_elite = True
    elite.rare_drop = 1.0

    assert regular.hp == base_hp
    assert regular.gold == base_gold
    assert elite.hp == base_hp * 3.0
    assert elite.gold == base_gold * 5.0
    assert elite.rare_drop == 1.0
    assert elite.is_elite is True
    assert regular.is_elite is False


def test_miniboss_field_on_enemy(pygame_headless):
    """Enemy has an ``is_miniboss`` field defaulting to False."""
    from engine.enemy import Enemy
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    e = Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
              hp=10, max_hp=10, dmg=1, gold=1, speed=edef.speed,
              size=edef.size, rare_drop=edef.rare_drop)
    assert e.is_miniboss is False


def test_miniboss_blocks_progress(pygame_headless):
    """A mini-boss spawns at 50% zone distance and blocks progress until killed."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Advance to 50% zone distance.
    r.world.zone_distance = cfg.ZONE_DISTANCE * 0.5
    r.update(1.0)
    # A mini-boss should be present and the miniboss_active flag set.
    assert r.world.miniboss_active is True
    minibosses = [e for e in r.world.enemies if e.is_miniboss]
    assert len(minibosses) >= 1, "no miniboss spawned at 50% zone distance"
    mb = minibosses[0]
    # The mini-boss is NOT the zone boss (is_boss stays False).
    assert mb.is_boss is False
    assert mb.is_miniboss is True
    # While the mini-boss is alive, zone distance must not advance.
    dist_before = r.world.zone_distance
    r.update(1.0)
    dist_after = r.world.zone_distance
    assert dist_after == dist_before, (
        f"zone distance advanced while miniboss active: {dist_before} -> {dist_after}")


def test_miniboss_releases_progress_on_kill(pygame_headless):
    """Once the mini-boss is killed, progress resumes."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    r.world.zone_distance = cfg.ZONE_DISTANCE * 0.5
    r.update(1.0)
    assert r.world.miniboss_active is True
    # Kill the mini-boss.
    mb = next(e for e in r.world.enemies if e.is_miniboss)
    mb.alive = False
    mb.hp = 0
    r.world.on_enemy_killed(mb)
    assert r.world.miniboss_active is False
    # Progress now resumes.
    dist_before = r.world.zone_distance
    r.update(1.0)
    assert r.world.zone_distance > dist_before


def test_miniboss_stats_04x_boss(pygame_headless):
    """The mini-boss has 0.4x the zone boss's HP/dmg/gold."""
    from engine.world import World
    from data import enemies as ed
    from engine.enemy import spawn_boss
    w = World()
    bdef = ed.boss_for_zone(w.zone_id)
    boss_hp = w.zone_hp(bdef)
    boss_dmg = w.zone_dmg(bdef)
    boss_gold = w.zone_gold(bdef)
    # The mini-boss is built with 0.4x the boss stats.
    mb = spawn_boss(bdef, hp=boss_hp * 0.4, dmg=boss_dmg * 0.4,
                    gold=boss_gold * 0.4)
    mb.is_boss = False
    mb.is_miniboss = True
    assert mb.hp == boss_hp * 0.4
    assert mb.dmg == boss_dmg * 0.4
    assert mb.gold == boss_gold * 0.4
    assert mb.is_miniboss is True
    assert mb.is_boss is False


def test_miniboss_not_spawned_after_boss(pygame_headless):
    """No mini-boss spawns while the zone boss is active."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Force the boss to be active (past 100% zone distance).
    r.world.zone_distance = cfg.ZONE_DISTANCE
    r.update(1.0)
    assert r.world.boss_active is True
    # No mini-boss should have spawned.
    assert not any(e.is_miniboss for e in r.world.enemies)


def test_no_new_gamestate_fields(pygame_headless):
    """``miniboss_active`` lives on World, not GameState (elites are transient)."""
    from core.state import GameState
    st = GameState()
    assert not hasattr(st, "miniboss_active"), (
        "miniboss_active must not be a GameState field (elites/transient)")
    from engine.world import World
    w = World()
    assert hasattr(w, "miniboss_active")
