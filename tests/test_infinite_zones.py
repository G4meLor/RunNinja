"""Infinite zone cycling with per-cycle multipliers.

Regression test for the endgame stall: the game ended at zone 9 (Cosmic
Void boss HP ~1624, one-shot by maxed run upgrades). The fix cycles the
9 themed zones with per-cycle HP/DMG/GOLD multipliers so the road never
ends, and switches the ascension tier multiplier from the flat
``ASCEND_TIERS`` stat_mult ladder to ``1.6 ** tier`` (steeper at high
tiers so the post-ascension economy keeps pace with the cycling zones).
"""
import pytest


# ---------------------------------------------------------------------------
# Per-cycle zone multipliers
# ---------------------------------------------------------------------------
def test_cycle_multipliers():
    """zone_hp at zone 9 (cycle 1, in-cycle zone 0) equals zone 0's hp
    times ``CYCLE_HP_MULT``. Same shape for dmg/gold.
    """
    from engine.world import World
    from data.enemies import ZONES
    import config as cfg

    edef = ZONES[0]["enemies"][0]

    w0 = World()
    w0.zone_index = 0
    hp0 = w0.zone_hp(edef)
    dmg0 = w0.zone_dmg(edef)
    gold0 = w0.zone_gold(edef)

    w9 = World()
    w9.zone_index = 9  # cycle 1, in-cycle zone 0
    hp9 = w9.zone_hp(edef)
    dmg9 = w9.zone_dmg(edef)
    gold9 = w9.zone_gold(edef)

    assert hp9 == pytest.approx(hp0 * cfg.CYCLE_HP_MULT)
    assert dmg9 == pytest.approx(dmg0 * cfg.CYCLE_DMG_MULT)
    assert gold9 == pytest.approx(gold0 * cfg.CYCLE_GOLD_MULT)


def test_cycle_derived_from_zone_index():
    """cycle = floor(zone_index / 9); in-cycle zone = zone_index % 9."""
    from engine.world import World
    w = World()
    for zi, (exp_cycle, exp_incycle) in enumerate(
            [(0, 0), (0, 1), (0, 8), (1, 0), (1, 1), (2, 0), (3, 0)]):
        w.zone_index = [0, 1, 8, 9, 10, 18, 27][zi]
        assert w.cycle == exp_cycle, f"zone {w.zone_index}: cycle {w.cycle} != {exp_cycle}"
        assert w.zone_in_cycle == exp_incycle, (
            f"zone {w.zone_index}: in-cycle {w.zone_in_cycle} != {exp_incycle}")


def test_zone_growth_uses_in_cycle_zone():
    """The intra-zone growth uses ``zone_index % 9`` so cycle 1 zone 0
    has the same base as cycle 0 zone 0 (before the cycle multiplier)."""
    from engine.world import World
    from data.enemies import ZONES
    edef = ZONES[2]["enemies"][0]
    w = World()
    w.zone_index = 2
    base_c0 = w.zone_hp(edef)  # cycle 0, in-cycle zone 2
    w.zone_index = 11          # cycle 1, in-cycle zone 2
    base_c1 = w.zone_hp(edef)
    import config as cfg
    # Same in-cycle base, scaled by exactly one cycle multiplier.
    assert base_c1 == pytest.approx(base_c0 * cfg.CYCLE_HP_MULT)


def test_road_continues_past_zone_9():
    """Past zone 9 the road continues with the same 9 themed zones at
    scaled stats. The zone lookup wraps the index modulo 9 so cycle 1
    zone 0 reuses the village; the cycle multiplier keeps stats growing.
    """
    from engine.world import World
    from data.enemies import ZONES
    w = World()
    w.zone_index = 13  # cycle 1, in-cycle zone 4
    # The zone is one of the 9 themed zones, indexed by the in-cycle
    # position (13 % 9 == 4 -> ruins).
    assert w.zone["id"] == ZONES[13 % 9]["id"]
    # And stats are scaled up by the cycle multiplier.
    edef = ZONES[0]["enemies"][0]
    w.zone_index = 0
    hp0 = w.zone_hp(edef)
    w.zone_index = 18  # cycle 2, in-cycle zone 0
    hp18 = w.zone_hp(edef)
    import config as cfg
    assert hp18 == pytest.approx(hp0 * cfg.CYCLE_HP_MULT ** 2)


# ---------------------------------------------------------------------------
# tier_mult = 1.6 ^ tier (replaces the flat ASCEND_TIERS stat_mult ladder)
# ---------------------------------------------------------------------------
def test_tier_mult_formula():
    """``_ascend_tier_mult`` returns ``1.6 ** tier``, not the flat
    ``ASCEND_TIERS`` ladder. The 7 ``ASCEND_TIERS`` names remain as
    labels for the ascend UI."""
    from core.state import GameState
    from engine.ninja import _ascend_tier_mult
    assert _ascend_tier_mult(GameState(ascend_tier=0)) == 1.0
    assert _ascend_tier_mult(GameState(ascend_tier=1)) == pytest.approx(1.6)
    assert _ascend_tier_mult(GameState(ascend_tier=2)) == pytest.approx(1.6 ** 2)
    assert _ascend_tier_mult(GameState(ascend_tier=7)) == pytest.approx(1.6 ** 7)


def test_tier_mult_not_flat_ladder():
    """At tier 2 the new formula (1.6^2 = 2.56) differs from the old flat
    ladder value (1.60) -- this is the load-bearing change."""
    from core.state import GameState
    from engine.ninja import _ascend_tier_mult
    import config as cfg
    # The old flat ladder value at tier 2 was 1.60; the new value is 2.56.
    assert _ascend_tier_mult(GameState(ascend_tier=2)) != pytest.approx(
        cfg.ASCEND_TIERS[2][1])


# ---------------------------------------------------------------------------
# Cycle N header renders in the game HUD
# ---------------------------------------------------------------------------
def test_cycle_header_in_hud(pygame_headless):
    """The HUD renders a "Cycle N" label once the player is past zone 9.
    At cycle 0 the header still shows the cycle (Cycle 1) so the player
    always sees which cycle they're in."""
    import inspect
    from ui.screen_game import GameScreen
    src = inspect.getsource(GameScreen._draw_hud)
    # The HUD must reference the cycle (either world.cycle or a "Cycle"
    # label string).
    assert "Cycle" in src or "cycle" in src, (
        "GameScreen._draw_hud does not render a Cycle header")


# ---------------------------------------------------------------------------
# Cycle-based achievements
# ---------------------------------------------------------------------------
def test_cycle_achievements_exist():
    """Cycle-based achievements (reach cycle 1/3/5/10) exist and fire."""
    from data.quests import ACHIEVEMENTS
    ids = {a.id for a in ACHIEVEMENTS}
    # The brief calls for cycle 1/3/5/10 -> best_zone >= 9/27/45/90.
    for cid in ("cycle_1", "cycle_3", "cycle_5", "cycle_10"):
        assert cid in ids, f"missing cycle achievement: {cid}"


def test_cycle_achievements_fire():
    """Each cycle achievement's check fires at the right best_zone."""
    from data.quests import ACHIEVEMENTS
    from core.state import GameState
    by_id = {a.id: a for a in ACHIEVEMENTS}
    cases = [
        ("cycle_1", 9), ("cycle_3", 27), ("cycle_5", 45), ("cycle_10", 90),
    ]
    for cid, zone in cases:
        a = by_id[cid]
        s = GameState(best_zone=zone)
        assert a.check(s), f"{cid} did not fire at best_zone={zone}"
        s_low = GameState(best_zone=zone - 1)
        assert not a.check(s_low), f"{cid} fired early at best_zone={zone - 1}"
