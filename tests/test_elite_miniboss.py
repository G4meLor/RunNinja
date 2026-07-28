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
    """An elite from ``_spawn_regular`` has 3x HP and 5x gold vs the base.

    Exercises the actual ``_spawn_regular`` code path: spawns a batch,
    filters the elites, and asserts each elite's hp/gold equal 3x/5x the
    base stats for its edef (and ``rare_drop == 1.0``). A regression in
    ``_spawn_regular`` that drops the ``* 3.0`` / ``* 5.0`` multipliers
    would be caught here, not masked by a trivial ``spawn_enemy`` pass-
    through.
    """
    from engine.world import World
    w = World()
    # Spawn enough that at least one elite is virtually guaranteed
    # (5% over 200 rolls -> ~10 elites on average).
    for _ in range(200):
        w._spawn_regular()
    elites = [e for e in w.enemies if e.is_elite]
    regulars = [e for e in w.enemies if not e.is_elite]
    assert regulars, "no regular enemies spawned"
    assert elites, "no elites spawned in 200 rolls (statistical fluke?)"
    # Each elite: 3x base HP, 5x base gold, guaranteed rare_drop.
    for e in elites:
        base_hp = w.zone_hp(e.edef)
        base_gold = w.zone_gold(e.edef)
        assert e.hp == base_hp * 3.0, (
            f"elite hp {e.hp} != 3x base {base_hp * 3.0}")
        assert e.gold == base_gold * 5.0, (
            f"elite gold {e.gold} != 5x base {base_gold * 5.0}")
        assert e.rare_drop == 1.0, f"elite rare_drop {e.rare_drop} != 1.0"
        assert e.is_elite is True
    # A regular enemy: 1x base HP, 1x base gold, edef's rare_drop.
    for e in regulars:
        base_hp = w.zone_hp(e.edef)
        base_gold = w.zone_gold(e.edef)
        assert e.hp == base_hp, f"regular hp {e.hp} != base {base_hp}"
        assert e.gold == base_gold, f"regular gold {e.gold} != base {base_gold}"
        assert e.is_elite is False
        assert e.rare_drop == e.edef.rare_drop


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
    """The mini-boss from ``_spawn_miniboss`` has 0.4x the zone boss stats.

    Exercises the actual ``_spawn_miniboss`` code path (not a trivial
    ``spawn_boss`` pass-through). A regression in ``_spawn_miniboss``
    that drops the ``* 0.4`` multipliers or fails to set the
    ``is_miniboss`` flag would be caught here.
    """
    from engine.world import World
    from data import enemies as ed
    w = World()
    bdef = ed.boss_for_zone(w.zone_id)
    boss_hp = w.zone_hp(bdef)
    boss_dmg = w.zone_dmg(bdef)
    boss_gold = w.zone_gold(bdef)
    # Drive the actual code path: _spawn_miniboss appends a mini-boss to
    # w.enemies and sets miniboss_active.
    n_before = len(w.enemies)
    w._spawn_miniboss()
    assert w.miniboss_active is True
    minibosses = [e for e in w.enemies if e.is_miniboss]
    assert len(minibosses) == 1, (
        f"expected 1 mini-boss, got {len(minibosses)}")
    mb = minibosses[0]
    assert mb.hp == boss_hp * 0.4, (
        f"miniboss hp {mb.hp} != 0.4x boss {boss_hp * 0.4}")
    assert mb.dmg == boss_dmg * 0.4, (
        f"miniboss dmg {mb.dmg} != 0.4x boss {boss_dmg * 0.4}")
    assert mb.gold == boss_gold * 0.4, (
        f"miniboss gold {mb.gold} != 0.4x boss {boss_gold * 0.4}")
    assert mb.is_miniboss is True
    assert mb.is_boss is False, (
        "mini-boss must NOT be the zone boss (is_boss stays False)")


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
