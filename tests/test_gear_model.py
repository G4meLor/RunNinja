"""Task 20: Gear data model + affix definitions + boss-drop logic.

The MODEL half of the gear split (the Forge UI is Task 33). Covers:

  * **Gear affix defs** in ``config.py``: 4 slots (blade, mask, talisman,
    cloak) with affix pools per rarity, reusing ``GACHA_RATES`` for the
    drop distribution.

  * **Gear provider** in ``core/bonuses.py``: reads ``state.gear`` and
    emits the affix effects into the flat bonus dict via
    ``aggregate_bonuses`` (BonusProvider registry). The effect keys are
    the same keys the engine already reads, so gear stacks additively
    with the skill tree + pets + tokens + heritage contributions.

  * **Boss-drop logic** in ``engine/runner.py``: on boss kill, drop a
    gear piece (random slot, rarity from ``GACHA_RATES``, random affix
    from the slot's pool). The new piece replaces any existing piece in
    the slot (one piece per slot).

  * **Stacking order**: gear is one of the additive sources in the
    ``evo`` layer; the total damage multiplier is clamped to
    ``MAX_TOTAL_DAMAGE_MULT`` (the sanity cap in ``config.py``).
"""
import pytest


# ---------------------------------------------------------------------------
# Specimen tests from the task brief
# ---------------------------------------------------------------------------
def test_gear_provider(pygame_headless):
    """A gear piece in state.gear flows through aggregate_bonuses."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0) >= 0.1


def test_boss_drops_gear(pygame_headless):
    """Killing a boss drops a gear piece into state.gear."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_boss
    from data import enemies as ed
    from core.bonuses import aggregate_bonuses
    state = GameState()
    r = Runner(state)
    # Spawn and kill a boss through the runner's kill path.
    bdef = ed.boss_for_zone("village")
    boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
    boss.alive = False
    boss.hp = 0
    before = len(state.gear)
    r._on_enemy_killed(boss, r.combo_mult(), r.gold_mult(),
                       aggregate_bonuses(state))
    after = len(state.gear)
    assert after >= 1, f"no gear dropped on boss kill: {state.gear}"
    assert after > before, f"gear count did not increase: {before} -> {after}"


# ---------------------------------------------------------------------------
# Gear provider registration + contract
# ---------------------------------------------------------------------------
def test_gear_provider_registered(pygame_headless):
    """The gear provider is in the BonusProvider registry."""
    from core.bonuses import _PROVIDERS, _gear_provider
    assert _gear_provider in _PROVIDERS


def test_gear_provider_empty(pygame_headless):
    """Empty state.gear -> no gear contributions."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    out = aggregate_bonuses(state)
    # No gear -> no gear-sourced keys. The aggregate may have other keys
    # from other providers (all zero for an empty state), but the gear
    # provider itself contributes nothing.
    # (We can't assert specific keys are absent because other providers
    # may emit the same keys; instead assert the gear provider alone
    # returns an empty dict.)
    from core.bonuses import _gear_provider
    assert _gear_provider(state) == {}


def test_gear_provider_multiple_slots_stack(pygame_headless):
    """Two slots with the same affix stack additively."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.gear = {
        "blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"},
        "cloak": {"affix": "tap_pct", "value": 0.05, "rarity": "common"},
    }
    out = aggregate_bonuses(state)
    # Both slots contribute tap_pct; they sum.
    assert out.get("tap_pct", 0) == pytest.approx(0.15)


def test_gear_provider_different_affixes(pygame_headless):
    """Different affixes in different slots emit different keys."""
    from core.state import GameState
    from core.bonuses import aggregate_bonuses
    state = GameState()
    state.gear = {
        "blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"},
        "talisman": {"affix": "gold_pct", "value": 0.1, "rarity": "rare"},
    }
    out = aggregate_bonuses(state)
    assert out.get("tap_pct", 0) == pytest.approx(0.1)
    assert out.get("gold_pct", 0) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Gear slot + affix definitions in config.py
# ---------------------------------------------------------------------------
def test_gear_4_slots(pygame_headless):
    """GEAR_SLOTS has exactly 4 slots: blade, mask, talisman, cloak."""
    import config as cfg
    assert hasattr(cfg, "GEAR_SLOTS")
    slots = cfg.GEAR_SLOTS
    assert len(slots) == 4, f"expected 4 gear slots, got {len(slots)}: {slots}"
    for s in ("blade", "mask", "talisman", "cloak"):
        assert s in slots, f"missing gear slot: {s}"


def test_gear_affixes_per_slot(pygame_headless):
    """Each slot has a non-empty affix pool in GEAR_AFFIXES."""
    import config as cfg
    assert hasattr(cfg, "GEAR_AFFIXES")
    for slot in cfg.GEAR_SLOTS:
        assert slot in cfg.GEAR_AFFIXES, f"no affix pool for slot: {slot}"
        pool = cfg.GEAR_AFFIXES[slot]
        assert len(pool) > 0, f"empty affix pool for slot: {slot}"
        # Each affix is (effect_key, base_value).
        for affix in pool:
            assert len(affix) == 2, f"bad affix format in {slot}: {affix}"
            key, val = affix
            assert isinstance(key, str) and key, f"bad affix key in {slot}: {key}"
            assert val > 0, f"non-positive affix value in {slot}: {val}"


def test_gear_rarity_mult_uses_gacha_rarities(pygame_headless):
    """GEAR_RARITY_MULT covers all GACHA_RATES rarities."""
    import config as cfg
    assert hasattr(cfg, "GEAR_RARITY_MULT")
    for rarity in cfg.GACHA_RATES:
        assert rarity in cfg.GEAR_RARITY_MULT, (
            f"GEAR_RARITY_MULT missing rarity: {rarity}")
        assert cfg.GEAR_RARITY_MULT[rarity] > 0, (
            f"GEAR_RARITY_MULT[{rarity}] <= 0")


# ---------------------------------------------------------------------------
# Boss-drop logic
# ---------------------------------------------------------------------------
def test_boss_drop_uses_gacha_rates(pygame_headless):
    """Boss-drop rarity distribution reuses GACHA_RATES.

    Over many boss kills, the rarity distribution should approximate
    GACHA_RATES (common ~60%, rare ~27%, etc.). This verifies the boss-drop
    logic uses GACHA_RATES, not a separate distribution.
    """
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_boss
    from data import enemies as ed
    from core.bonuses import aggregate_bonuses
    import config as cfg

    # Seed for determinism.
    from utils import seed
    seed(42)

    state = GameState()
    r = Runner(state)
    bdef = ed.boss_for_zone("village")
    counts = {rarity: 0 for rarity in cfg.GACHA_RATES}
    n = 2000
    for _ in range(n):
        # Clear gear so each drop is fresh (the slot is random, so the
        # rarity distribution is what we're measuring, not the slot).
        state.gear = {}
        boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
        boss.alive = False
        boss.hp = 0
        r._on_enemy_killed(boss, r.combo_mult(), r.gold_mult(),
                           aggregate_bonuses(state))
        # The dropped piece's rarity.
        for g in state.gear.values():
            counts[g["rarity"]] = counts.get(g["rarity"], 0) + 1

    # The distribution should approximate GACHA_RATES within tolerance.
    # Common is the most common (~60%); mythic is the rarest (~0.5%).
    # With 2000 drops, common should be ~1200, mythic ~10.
    total = sum(counts.values())
    assert total == n, f"not all drops counted: {total} != {n}"
    # Common should be the majority (>50%).
    assert counts["common"] / n > 0.5, (
        f"common rate too low: {counts['common']/n:.2%} "
        f"(expected ~{cfg.GACHA_RATES['common']:.0%})")
    # Mythic should be very rare (<2%).
    assert counts["mythic"] / n < 0.02, (
        f"mythic rate too high: {counts['mythic']/n:.2%} "
        f"(expected ~{cfg.GACHA_RATES['mythic']:.2%})")


def test_boss_drop_piece_shape(pygame_headless):
    """A dropped gear piece has affix, value, and rarity keys."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_boss
    from data import enemies as ed
    from core.bonuses import aggregate_bonuses
    import config as cfg

    state = GameState()
    r = Runner(state)
    bdef = ed.boss_for_zone("village")
    boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
    boss.alive = False
    boss.hp = 0
    r._on_enemy_killed(boss, r.combo_mult(), r.gold_mult(),
                       aggregate_bonuses(state))
    assert len(state.gear) >= 1
    for slot, g in state.gear.items():
        assert slot in cfg.GEAR_SLOTS, f"unknown slot: {slot}"
        assert "affix" in g, f"missing affix in {slot}: {g}"
        assert "value" in g, f"missing value in {slot}: {g}"
        assert "rarity" in g, f"missing rarity in {slot}: {g}"
        assert g["rarity"] in cfg.GACHA_RATES, (
            f"unknown rarity in {slot}: {g['rarity']}")
        assert g["value"] > 0, f"non-positive value in {slot}: {g}"
        # The affix should be a valid key from the slot's pool.
        affix_keys = [a[0] for a in cfg.GEAR_AFFIXES[slot]]
        assert g["affix"] in affix_keys, (
            f"affix {g['affix']} not in {slot}'s pool: {affix_keys}")


def test_boss_drop_replaces_slot(pygame_headless):
    """A new gear piece replaces the existing piece in the same slot.

    One piece per slot (4 slots, 4 pieces max). A new drop in an occupied
    slot replaces the old piece (not stack on top).
    """
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_boss
    from data import enemies as ed
    from core.bonuses import aggregate_bonuses

    state = GameState()
    r = Runner(state)
    bdef = ed.boss_for_zone("village")
    # Pre-fill a slot.
    state.gear = {"blade": {"affix": "tap_pct", "value": 0.1, "rarity": "rare"}}
    # Kill a boss; the drop may or may not land in "blade", but the total
    # number of occupied slots should never exceed 4 (one per slot).
    for _ in range(20):
        boss = spawn_boss(bdef, hp=1.0, dmg=1.0, gold=1.0)
        boss.alive = False
        boss.hp = 0
        r._on_enemy_killed(boss, r.combo_mult(), r.gold_mult(),
                           aggregate_bonuses(state))
    assert len(state.gear) <= 4, (
        f"more than 4 gear slots occupied: {len(state.gear)}: {state.gear}")


def test_non_boss_does_not_drop_gear(pygame_headless):
    """A normal (non-boss) enemy kill does NOT drop gear."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_enemy
    from data.enemies import ZONES
    from core.bonuses import aggregate_bonuses

    state = GameState()
    r = Runner(state)
    edef = ZONES[0]["enemies"][0]
    e = spawn_enemy(edef, hp=1.0, dmg=1.0, gold=1.0)
    e.alive = False
    e.hp = 0
    before = len(state.gear)
    r._on_enemy_killed(e, r.combo_mult(), r.gold_mult(),
                       aggregate_bonuses(state))
    assert state.gear == {}, (
        f"non-boss kill dropped gear: {state.gear}")


# ---------------------------------------------------------------------------
# MAX_TOTAL_DAMAGE_MULT cap (the sanity cap documented in config.py)
# ---------------------------------------------------------------------------
def test_max_total_damage_mult_unchanged(pygame_headless):
    """MAX_TOTAL_DAMAGE_MULT is still 1e9 (the sanity cap).

    Gear values are tuned to fit within the stacking order under this cap.
    The cap itself is unchanged by the gear model (it's the last line of
    defense against a runaway multiplier stack).
    """
    import config as cfg
    assert cfg.MAX_TOTAL_DAMAGE_MULT == 1e9


def test_gear_values_reasonable(pygame_headless):
    """Gear values are reasonable: even a mythic piece doesn't trivially
    exceed the stacking order.

    A mythic piece's value is base * GEAR_RARITY_MULT[mythic]. Even at
    the highest rarity, a single piece's contribution should be a sane
    additive pct (not a 1000x multiplier that would blow past
    MAX_TOTAL_DAMAGE_MULT).
    """
    import config as cfg
    mythic_mult = cfg.GEAR_RARITY_MULT.get("mythic", 1.0)
    for slot, pool in cfg.GEAR_AFFIXES.items():
        for affix_key, base_val in pool:
            mythic_val = base_val * mythic_mult
            # A single mythic piece should not exceed +200% (0.2) for pct
            # keys, or +10 for flat keys (energy_timer, combo_window).
            # These are additive contributions, not multipliers, so even
            # at 200% the total damage multiplier stays well under 1e9.
            if affix_key.endswith("_pct") or affix_key in (
                    "firefly_gold", "firefly_spawn", "firefly_size",
                    "density_pct", "energy_regen"):
                assert mythic_val <= 2.0, (
                    f"{slot}/{affix_key} mythic value {mythic_val} too high")
            else:
                # Flat keys (energy_timer seconds, combo_window seconds).
                assert mythic_val <= 50.0, (
                    f"{slot}/{affix_key} mythic value {mythic_val} too high")
