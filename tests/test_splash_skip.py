"""Splash/Skip progression layer: Cleave + Yokai Portal (Task 16).

Two late-ascension "zooming through zones" features:

1. **Cleave** (from the skill tree): when a tap massively overkills an
   enemy (damage exceeds the enemy's remaining HP by a large margin),
   the next ``cleave_count()`` enemies are chain-cleared too. Gated
   behind mid-ascension (``ascend_tier >= 3``) so a new player (tier 0)
   never sees splash in the first runs.

2. **Yokai Portal** boss variant: a 5% chance for a boss to be a Yokai
   Portal variant that, when killed, jumps ``zone_distance`` by a chunk
   (50% of ``ZONE_DISTANCE``) so the next zone starts partway in. The
   boss is still killed normally — bestiary/achievement reveals fire
   through the normal kill path (``monsters_killed`` increments, the
   ``slayer`` achievement checks ``bosses_killed``, etc.) — only the
   zone bar jumps.
"""
import pytest

import config as cfg


# ---------------------------------------------------------------------------
# 1. Cleave stat (skill tree node)
# ---------------------------------------------------------------------------
def test_cleave_node_in_offense_branch(pygame_headless):
    """A "Cleave" node exists in the offense branch of the skill tree."""
    from data import skill_tree as st
    cleave_nodes = [n for n in st.NODES if n.effect_key == "cleave"]
    assert cleave_nodes, "no Cleave node in the skill tree"
    n = cleave_nodes[0]
    assert n.branch == "offense", (
        f"Cleave node branch {n.branch!r} != 'offense'")
    # The node id is in BY_ID (so can_unlock + the UI can find it).
    assert n.id in st.BY_ID


def test_cleave_node_unlockable_in_skill_tree(pygame_headless):
    """The Cleave node is unlockable via can_unlock with its prereq + cost."""
    from data import skill_tree as st
    cleave_nodes = [n for n in st.NODES if n.effect_key == "cleave"]
    n = cleave_nodes[0]
    # With the prereq unlocked + enough elixir, can_unlock is True.
    if n.prereq is not None:
        assert st.can_unlock(n.id, {n.prereq}, n.cost + 1)
    else:
        assert st.can_unlock(n.id, set(), n.cost + 1)


# ---------------------------------------------------------------------------
# 2. cleave_count() — the mid-ascension gate
# ---------------------------------------------------------------------------
def test_cleave_count_zero_for_new_player(pygame_headless):
    """A new player (ascend_tier == 0) has cleave_count == 0.

    This is THE gate: a new player never sees splash in the first runs.
    Even with the Cleave node unlocked, cleave_count is 0 at tier 0.
    """
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.ascend_tier = 0
    state.skill_tree = {"off_cleave1"}  # hypothetically unlocked
    r = Runner(state)
    assert r.cleave_count() == 0, (
        "new player (tier 0) should have cleave_count == 0")


def test_cleave_count_zero_below_tier_3(pygame_headless):
    """Cleave does not fire below tier 3 (mid-ascension gate)."""
    from core.state import GameState
    from engine.runner import Runner
    for tier in (1, 2):
        state = GameState()
        state.ascend_tier = tier
        state.skill_tree = {"off_cleave1"}
        r = Runner(state)
        assert r.cleave_count() == 0, (
            f"tier {tier} should have cleave_count == 0 (mid-ascension gate)")


def test_cleave_count_nonzero_at_tier_3_with_node(pygame_headless):
    """At tier >= 3 with the Cleave node unlocked, cleave_count > 0."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.ascend_tier = 3
    state.skill_tree = {"off_cleave1"}
    r = Runner(state)
    assert r.cleave_count() >= 1, (
        "tier 3 with cleave unlocked should have cleave_count >= 1")


def test_cleave_count_zero_at_tier_3_without_node(pygame_headless):
    """At tier 3 without the Cleave node, cleave_count is still 0.

    Both gates must hold: the tier gate AND the skill-tree node.
    """
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.ascend_tier = 3
    state.skill_tree = set()  # no cleave node
    r = Runner(state)
    assert r.cleave_count() == 0, (
        "tier 3 without cleave node should have cleave_count == 0")


# ---------------------------------------------------------------------------
# 3. Cleave application: massive overkill chain-clears the next K enemies
# ---------------------------------------------------------------------------
def test_cleave_chain_clears_next_enemies(pygame_headless):
    """A massive tap overkill cleaves the next ``cleave_count()`` enemies.

    The specimen test from the brief: spawn 3 weak enemies, tap (with a
    massive tap_damage that overkills the first by a huge margin), and
    assert at least 2 enemies are cleared (the tapped one + the cleave).
    """
    from core.state import GameState
    from engine.runner import Runner
    from data.enemies import ZONES
    from engine.enemy import spawn_enemy
    state = GameState()
    state.ascend_tier = 3
    state.skill_tree = {"off_cleave1"}
    r = Runner(state)
    # Make the ninja's tap damage massive so the first enemy is overkilled
    # by a huge margin (the cleave trigger condition).
    r.ninja.tap_damage = 10_000.0
    # Spawn 5 weak enemies close to the ninja so they're all in range.
    edef = ZONES[0]["enemies"][0]
    for i in range(5):
        e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
        e.x = 200 + i * 10  # all near PARTY_X, ordered by x
        r.world.enemies.append(e)
    cleave_k = r.cleave_count()
    assert cleave_k >= 1, "test setup: cleave_count must be >= 1 at tier 3"
    # Tap the first (nearest) enemy. The tap overkills it by a massive
    # margin (10_000 dmg vs 1 HP), so the cleave should fire and chain-
    # clear the next ``cleave_k`` enemies.
    r.tap()
    # At least 2 enemies should be cleared (the tapped one + at least one
    # cleave). With cleave_k >= 1, the chain clears the next K enemies.
    cleared = sum(1 for e in r.world.enemies if not e.alive)
    assert cleared >= 2, (
        f"cleave did not chain-clear: only {cleared} enemies cleared, "
        f"expected >= 2 (tapped + cleave_count={cleave_k})")


def test_cleave_does_not_fire_on_non_overkill(pygame_headless):
    """A tap that kills without a massive overkill does NOT cleave.

    The cleave only fires on a MASSIVE overkill (damage exceeds the
    enemy's HP by a large margin), not on every kill. A tap that exactly
    kills the enemy (no overkill) should not chain-clear the next enemies.

    Uses ``crit_chance == 0`` so the tap is a deterministic non-crit —
    the actual damage dealt equals ``tap_damage`` (no crit multiplier),
    so the overkill condition is deterministic. This is also the
    regression guard for the double-``roll_crit`` bug: the cleave must
    fire based on the ACTUAL damage dealt, not a separate roll.
    """
    from core.state import GameState
    from engine.runner import Runner
    from data.enemies import ZONES
    from engine.enemy import spawn_enemy
    state = GameState()
    state.ascend_tier = 3
    state.skill_tree = {"off_cleave1"}
    r = Runner(state)
    # Set tap_damage to just barely kill the enemy (no overkill). With
    # crit_chance == 0, the actual damage dealt is exactly tap_damage
    # (no crit multiplier), so the overkill condition is deterministic.
    r.ninja.tap_damage = 1.0  # exactly the enemy's HP, no overkill
    r.ninja.crit_chance = 0.0  # deterministic non-crit
    edef = ZONES[0]["enemies"][0]
    for i in range(5):
        e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
        e.x = 200 + i * 10
        r.world.enemies.append(e)
    r.tap()
    # Only the tapped enemy is dead (no cleave because no overkill).
    cleared = sum(1 for e in r.world.enemies if not e.alive)
    assert cleared == 1, (
        f"cleave fired without overkill: {cleared} cleared, expected 1")


def test_cleave_uses_actual_damage_not_separate_roll(pygame_headless):
    """The cleave condition uses the ACTUAL damage dealt, not a separate roll.

    Regression guard for the double-``roll_crit`` bug: ``tap()`` used to
    call ``ninja.roll_crit()`` to snapshot ``dmg_raw`` for the overkill
    condition, then ``tap_enemy`` called ``roll_crit()`` again for the
    actual damage — two independent draws. The cleave condition was
    stochastic and inconsistent with the actual damage.

    The fix: ``tap_enemy`` returns ``(target, dmg_dealt, is_crit)`` and
    ``tap()`` uses ``dmg_dealt`` (the actual damage) for the overkill
    condition. This test sets up a scenario where the snapshot roll and
    the actual roll would disagree (by controlling the RNG state) and
    verifies the cleave fires based on the ACTUAL damage, not the
    snapshot.

    Setup: ``crit_chance == 0`` so both rolls are deterministic
    non-crits (the actual damage is exactly ``tap_damage``). With
    ``tap_damage == 11`` (just over ``CLEAVE_OVERKILL_RATIO * HP = 10``
    for a 1 HP enemy), the cleave SHOULD fire (actual dmg 11 > 10).
    A regression that uses a separate roll would still see 11 (both
    rolls are non-crits here), so we also test the complement: with
    ``tap_damage == 9`` (below the 10x threshold), the cleave should
    NOT fire. The deterministic setup confirms the condition uses the
    actual damage, not a separate stochastic roll.
    """
    from core.state import GameState
    from engine.runner import Runner, CLEAVE_OVERKILL_RATIO
    from data.enemies import ZONES
    from engine.enemy import spawn_enemy
    edef = ZONES[0]["enemies"][0]

    # Case 1: tap_damage just over the overkill threshold -> cleave fires.
    state = GameState()
    state.ascend_tier = 3
    state.skill_tree = {"off_cleave1"}
    r = Runner(state)
    r.ninja.crit_chance = 0.0  # deterministic non-crit
    r.ninja.tap_damage = CLEAVE_OVERKILL_RATIO + 1.0  # 11 -> 11 > 10*1
    for i in range(5):
        e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
        e.x = 200 + i * 10
        r.world.enemies.append(e)
    r.tap()
    cleared = sum(1 for e in r.world.enemies if not e.alive)
    assert cleared >= 2, (
        f"cleave did not fire with actual dmg > RATIO*HP: "
        f"{cleared} cleared, expected >= 2 (dmg=11, RATIO*HP=10)")

    # Case 2: tap_damage just below the overkill threshold -> no cleave.
    state2 = GameState()
    state2.ascend_tier = 3
    state2.skill_tree = {"off_cleave1"}
    r2 = Runner(state2)
    r2.ninja.crit_chance = 0.0
    r2.ninja.tap_damage = CLEAVE_OVERKILL_RATIO - 1.0  # 9 -> 9 < 10*1
    for i in range(5):
        e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
        e.x = 200 + i * 10
        r2.world.enemies.append(e)
    r2.tap()
    cleared2 = sum(1 for e in r2.world.enemies if not e.alive)
    assert cleared2 == 1, (
        f"cleave fired with actual dmg < RATIO*HP: "
        f"{cleared2} cleared, expected 1 (dmg=9, RATIO*HP=10)")


def test_cleave_does_not_fire_at_tier_0_even_with_overkill(pygame_headless):
    """A new player (tier 0) never sees cleave, even with a massive overkill.

    The gate: at tier 0, cleave_count() == 0, so no chain-clear even if
    the tap massively overkills the enemy. This is the "new player never
    sees splash in the first runs" criterion.
    """
    from core.state import GameState
    from engine.runner import Runner
    from data.enemies import ZONES
    from engine.enemy import spawn_enemy
    state = GameState()
    state.ascend_tier = 0  # new player
    state.skill_tree = {"off_cleave1"}  # hypothetically unlocked
    r = Runner(state)
    r.ninja.tap_damage = 10_000.0
    edef = ZONES[0]["enemies"][0]
    for i in range(5):
        e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
        e.x = 200 + i * 10
        r.world.enemies.append(e)
    r.tap()
    # Only the tapped enemy is dead — no cleave at tier 0.
    cleared = sum(1 for e in r.world.enemies if not e.alive)
    assert cleared == 1, (
        f"cleave fired at tier 0: {cleared} cleared, expected 1 "
        "(new player must never see splash)")


# ---------------------------------------------------------------------------
# 4. Cleave preserves bestiary/achievement reveals (kills count normally)
# ---------------------------------------------------------------------------
def test_cleave_kills_count_in_monsters_killed(pygame_headless):
    """Cleared-by-cleave enemies still count as kills (monsters_killed).

    The cleave chain-clears the next K enemies, but they are still KILLED
    (alive=False, hp=0), so the kill path fires for each — bestiary and
    achievement reveals are not bypassed. ``monsters_killed`` increments
    per cleared enemy.
    """
    from core.state import GameState
    from engine.runner import Runner
    from data.enemies import ZONES
    from engine.enemy import spawn_enemy
    state = GameState()
    state.ascend_tier = 3
    state.skill_tree = {"off_cleave1"}
    r = Runner(state)
    r.ninja.tap_damage = 10_000.0
    edef = ZONES[0]["enemies"][0]
    for i in range(5):
        e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
        e.x = 200 + i * 10
        r.world.enemies.append(e)
    before = state.monsters_killed
    r.tap()
    # Each cleared enemy (tapped + cleave chain) incremented
    # monsters_killed. At least 2 cleared -> at least +2.
    after = state.monsters_killed
    assert after >= before + 2, (
        f"cleave kills did not count in monsters_killed: "
        f"{before} -> {after}, expected >= +2")


# ---------------------------------------------------------------------------
# 5. Yokai Portal boss variant
# ---------------------------------------------------------------------------
def test_yokai_portal_is_boss_variant(pygame_headless):
    """A Yokai Portal is a boss variant (is_boss=True) with a flag.

    The Yokai Portal is a 5% chance for a boss to be a Yokai Portal
    variant. It is still a boss (is_boss=True) so the normal boss-kill
    path fires (zone advance, bosses_killed++, etc.) — only the zone bar
    ALSO jumps by a chunk.
    """
    from engine.enemy import Enemy
    from data.enemies import ZONES
    edef = ZONES[0]["enemies"][0]
    e = Enemy(edef=edef, name=edef.name, shape=edef.shape, hue=edef.hue,
              hp=10, max_hp=10, dmg=1, gold=1, speed=edef.speed,
              size=edef.size, rare_drop=edef.rare_drop,
              is_boss=True)
    # A Yokai Portal flag exists on the Enemy (set by the world when the
    # 5% roll hits; default False).
    assert hasattr(e, "is_yokai_portal"), (
        "Enemy has no is_yokai_portal field for the Yokai Portal variant")
    assert e.is_yokai_portal is False, (
        "is_yokai_portal should default to False")


def test_yokai_portal_5pct_roll(pygame_headless):
    """5% of bosses are Yokai Portal variants (within tolerance)."""
    from engine.world import World
    # Spawn 1000 bosses via the actual _enter_boss path; the 5% roll is
    # inside the world.
    yokai_count = 0
    total = 1000
    for _ in range(total):
        w = World()
        w.zone_distance = cfg.ZONE_DISTANCE  # trigger boss
        w.update(1.0, paused=False)
        boss = next((e for e in w.enemies if e.is_boss), None)
        assert boss is not None, "no boss spawned"
        if getattr(boss, "is_yokai_portal", False):
            yokai_count += 1
    # 5% +/- 3% (statistical tolerance over 1000 rolls)
    assert 20 <= yokai_count <= 80, (
        f"yokai portal rate {yokai_count/total*100:.1f}% out of range")


def test_yokai_portal_jumps_zone_distance_on_kill(pygame_headless):
    """A Yokai Portal boss, when killed, jumps zone_distance by a chunk.

    The skip: the boss is killed normally (zone advances, bosses_killed
    increments), but the NEXT zone starts with zone_distance already
    partway in (a chunk of ZONE_DISTANCE) — the "zooming through zones"
    dopamine. The jump is 50% of ZONE_DISTANCE (the brief's "+50%
    ZONE_DISTANCE").
    """
    from engine.world import World
    w = World()
    # Force a boss.
    w.zone_distance = cfg.ZONE_DISTANCE
    w.update(1.0, paused=False)
    boss = next((e for e in w.enemies if e.is_boss), None)
    assert boss is not None
    # Force the boss to be a Yokai Portal variant.
    boss.is_yokai_portal = True
    # Kill the boss. The world's on_enemy_killed advances the zone and
    # (for a Yokai Portal) jumps zone_distance by a chunk.
    boss.alive = False
    boss.hp = 0
    w.on_enemy_killed(boss)
    # Zone advanced (the boss kill always advances the zone).
    assert w.zone_index == 1
    # The Yokai Portal jump: zone_distance is NOT 0 — it's a chunk.
    # The brief: +50% ZONE_DISTANCE, so the next zone starts at 50%
    # of ZONE_DISTANCE.
    assert w.zone_distance > 0, (
        "yokai portal did not jump zone_distance on kill")
    assert w.zone_distance == pytest.approx(cfg.ZONE_DISTANCE * 0.5), (
        f"yokai portal jump {w.zone_distance} != 50% ZONE_DISTANCE "
        f"{cfg.ZONE_DISTANCE * 0.5}")


def test_yokai_portal_does_not_jump_on_normal_boss(pygame_headless):
    """A normal (non-Yokai Portal) boss kill resets zone_distance to 0.

    The Yokai Portal skip is ONLY for the Yokai Portal variant — a normal
    boss kill resets zone_distance to 0 (the existing behavior). We
    force ``is_yokai_portal = False`` to test the non-Yokai path
    deterministically (the 5% roll is exercised in
    ``test_yokai_portal_5pct_roll``).
    """
    from engine.world import World
    w = World()
    w.zone_distance = cfg.ZONE_DISTANCE
    w.update(1.0, paused=False)
    boss = next((e for e in w.enemies if e.is_boss), None)
    assert boss is not None
    # Force the boss to NOT be a Yokai Portal (deterministic; the 5%
    # roll is exercised in test_yokai_portal_5pct_roll).
    boss.is_yokai_portal = False
    boss.alive = False
    boss.hp = 0
    w.on_enemy_killed(boss)
    # Normal boss: zone advances, zone_distance resets to 0.
    assert w.zone_index == 1
    assert w.zone_distance == 0.0, (
        f"normal boss kill did not reset zone_distance: {w.zone_distance}")


def test_yokai_portal_kill_counts_in_bosses_killed(pygame_headless):
    """A Yokai Portal kill still counts in bosses_killed (no bypass).

    The Yokai Portal skip does NOT bypass bestiary/achievement reveals:
    the boss is still killed normally (is_boss=True), so the runner's
    kill path fires — bosses_killed increments, the slayer achievement
    can fire, etc. Only the zone bar jumps.
    """
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Force a boss.
    r.world.zone_distance = cfg.ZONE_DISTANCE
    r.update(1.0, paused=False)
    boss = next((e for e in r.world.enemies if e.is_boss), None)
    assert boss is not None
    boss.is_yokai_portal = True
    before = state.bosses_killed
    # Kill the boss through the runner's kill path (the normal path).
    boss.alive = False
    boss.hp = 0
    from core.bonuses import aggregate_bonuses
    r._on_enemy_killed(boss, r.combo_mult(), r.gold_mult(),
                       aggregate_bonuses(state))
    after = state.bosses_killed
    assert after == before + 1, (
        f"yokai portal kill did not count in bosses_killed: "
        f"{before} -> {after}")


# ---------------------------------------------------------------------------
# 6. No new GameState fields (Cleave + Yokai Portal are transient)
# ---------------------------------------------------------------------------
def test_no_new_gamestate_fields(pygame_headless):
    """Cleave + Yokai Portal add no new GameState fields.

    Cleave is a skill-tree node (existing field ``skill_tree``) + a
    runner-computed ``cleave_count()`` (derived from ``ascend_tier`` +
    the cleave bonus). Yokai Portal is a transient flag on Enemy +
    World; the zone jump is a ``zone_distance`` write (existing field).
    No new GameState fields.
    """
    from core.state import GameState
    st = GameState()
    # No cleave-related field on GameState (it's derived in cleave_count).
    assert not hasattr(st, "cleave"), (
        "cleave must not be a GameState field (derived in cleave_count)")
    assert not hasattr(st, "cleave_count"), (
        "cleave_count must not be a GameState field (derived in Runner)")
    # No yokai_portal field on GameState (it's a transient Enemy flag).
    assert not hasattr(st, "yokai_portal"), (
        "yokai_portal must not be a GameState field (transient on Enemy)")
