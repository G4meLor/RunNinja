"""Building unlock zone rebalance + persist through ascension.

Regression test for the bug where 8 of 18 buildings had ``unlock_zone``
9-16 (effectively unreachable because ascension resets zone to 0 and the
natural max is ~9-12), and ascension cleared ``state.buildings`` so the
player lost all building progress on every prestige.

The fix:
  - compress ``unlock_zone`` to a smooth 0-8 distribution so every
    building is reachable in a single run to zone 8;
  - buildings persist through ascension (only gold/upgrades/zone reset);
  - building output in ``total_gps`` is scaled by the ascension tier
    ``stat_mult`` so persisted buildings stay relevant;
  - ``elixir_gain`` re-tuned with a diminish factor so the post-ascension
    economy (now stronger because buildings persist) doesn't snowball.
"""
import pytest


# ---------------------------------------------------------------------------
# unlock_zone rebalance
# ---------------------------------------------------------------------------
def test_all_buildings_reachable():
    """All 18 buildings unlock by zone 8 (reachable in one run)."""
    from data.buildings import BUILDINGS
    max_unlock = max(b.unlock_zone for b in BUILDINGS)
    assert max_unlock <= 8, f"max unlock_zone {max_unlock}"


def test_unlock_zone_smooth_distribution():
    """unlock_zone values form a smooth 0-8 distribution (no gaps > 1)."""
    from data.buildings import BUILDINGS
    zones = sorted(b.unlock_zone for b in BUILDINGS)
    assert zones[0] == 0, f"first building should be zone 0, got {zones[0]}"
    assert zones[-1] <= 8
    # No gap larger than 1 between consecutive unlock zones.
    for i in range(1, len(zones)):
        assert zones[i] - zones[i - 1] <= 1, \
            f"gap at index {i}: {zones[i - 1]} -> {zones[i]}"


# ---------------------------------------------------------------------------
# Buildings persist through ascension
# ---------------------------------------------------------------------------
def test_buildings_persist_through_ascension(pygame_headless):
    """Buildings carry over ascension; only gold/upgrades/zone reset."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.buildings = {"farm": 5, "forge": 2}
    state.gold = 100000
    state.lifetime_gold = 100000
    state.zone_index = 5
    state.best_zone = 5
    gained = ascend(state)
    # Buildings persist.
    assert state.buildings.get("farm") == 5
    assert state.buildings.get("forge") == 2
    # Zone resets, gold resets, but buildings stay.
    assert state.zone_index == 0
    assert state.gold == 0.0
    # Elixir was awarded (lifetime_gold > 0).
    assert gained > 0
    assert state.elixir > 0


def test_upgrades_reset_on_ascension(pygame_headless):
    """Run upgrades reset on ascension; buildings persist."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.upgrades = {"tap_power": 10, "auto_attack": 5}
    state.buildings = {"farm": 3}
    state.gold = 50000
    state.lifetime_gold = 50000
    state.zone_index = 5
    ascend(state)
    assert state.upgrades == {}          # upgrades reset
    assert state.buildings.get("farm") == 3  # buildings persist


def test_start_farms_does_not_overwrite_existing(pygame_headless):
    """The start_farms skill guarantees a minimum, not an overwrite."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.skill_tree = {"eli_root", "eli_farms1"}  # start_farms = 3
    state.buildings = {"farm": 10}
    state.gold = 50000
    state.lifetime_gold = 50000
    state.zone_index = 5
    ascend(state)
    # Player had 10 farms; start_farms(3) should not reduce them.
    assert state.buildings.get("farm") >= 10


# ---------------------------------------------------------------------------
# elixir_gain re-tune
# ---------------------------------------------------------------------------
def test_elixir_gain_first_ascension(pygame_headless):
    """A first ascension with ~10k lifetime gold gives ~50 elixir."""
    from core.state import GameState
    from core.ascend import elixir_gain
    state = GameState()
    state.lifetime_gold = 10000
    state.ascend_tier = 0
    gained = elixir_gain(state)
    assert 40 <= gained <= 60, \
        f"first ascension elixir {gained}, expected ~50"


def test_elixir_gain_no_gold_returns_zero(pygame_headless):
    """No lifetime gold → no elixir (can't prestige nothing)."""
    from core.state import GameState
    from core.ascend import elixir_gain
    state = GameState()
    state.lifetime_gold = 0
    assert elixir_gain(state) == 0


def test_elixir_gain_diminishes_with_tier(pygame_headless):
    """The diminish factor reduces elixir per gold on higher tiers."""
    from core.state import GameState
    from core.ascend import elixir_gain
    state = GameState()
    state.lifetime_gold = 100000
    state.ascend_tier = 0
    e0 = elixir_gain(state)
    state.ascend_tier = 1
    e1 = elixir_gain(state)
    state.ascend_tier = 2
    e2 = elixir_gain(state)
    # Same lifetime_gold: higher tier → less elixir.
    assert e0 > e1 > e2, f"not diminishing: {e0} {e1} {e2}"


def test_elixir_pct_skill_still_applies(pygame_headless):
    """The elixir_pct skill-tree bonus still boosts elixir gain."""
    from core.state import GameState
    from core.ascend import elixir_gain
    state = GameState()
    state.lifetime_gold = 10000
    base = elixir_gain(state)
    state.skill_tree = {"eli_root"}  # +10% elixir_pct
    boosted = elixir_gain(state)
    assert boosted > base, f"elixir_pct not applied: {base} -> {boosted}"


# ---------------------------------------------------------------------------
# total_gps scaled by tier stat_mult
# ---------------------------------------------------------------------------
def test_total_gps_scaled_by_tier(pygame_headless):
    """Building output in total_gps is scaled by the ascension tier stat_mult."""
    from core.state import GameState
    from core.game_economy import total_gps
    import config as cfg
    state = GameState()
    state.buildings = {"farm": 10, "sawmill": 5}
    # Tier 0: stat_mult = 1.0
    gps_t0 = total_gps(state)
    state.ascend_tier = 1
    gps_t1 = total_gps(state)
    expected_mult = cfg.ASCEND_TIERS[1][1]  # 1.25
    assert gps_t1 == pytest.approx(gps_t0 * expected_mult, rel=1e-6), \
        f"tier scaling: {gps_t0} -> {gps_t1}, expected x{expected_mult}"


def test_total_gps_tier_zero_no_scaling(pygame_headless):
    """At tier 0, total_gps equals the raw building output (no tier bonus)."""
    from core.state import GameState
    from core.game_economy import total_gps
    from data import buildings as bd
    state = GameState()
    state.buildings = {"farm": 10, "sawmill": 5}
    # Raw building gps: farm 10*1 + sawmill 5*5 = 35
    raw = sum(bd.building_gps(b, state.building_level(b.id))
              for b in bd.BUILDINGS if b.id in state.buildings)
    assert total_gps(state) == pytest.approx(raw, rel=1e-6)


# ---------------------------------------------------------------------------
# First 3 ascensions feel balanced (no snowball)
# ---------------------------------------------------------------------------
def test_first_three_ascensions_balanced(pygame_headless):
    """Simulate 3 ascensions with growing lifetime_gold; no snowball.

    With buildings persisting + tier stat_mult accelerating earning,
    lifetime_gold grows ~5x per ascension. The diminish factor should
    keep elixir growth bounded (comparable to the soul_reward curve:
    10 -> 40 -> 120, i.e. ~4x then ~3x).
    """
    from core.state import GameState
    from core.ascend import elixir_gain
    # lifetime_gold grows ~5x per ascension (buildings persist + tier_mult).
    lifetime_golds = [10000, 50000, 200000]
    elixirs = []
    for tier, lg in enumerate(lifetime_golds):
        state = GameState()
        state.lifetime_gold = lg
        state.ascend_tier = tier
        elixirs.append(elixir_gain(state))
    # Each ascension gives more elixir than the previous (incentive to ascend).
    assert elixirs[0] < elixirs[1] < elixirs[2], \
        f"not increasing: {elixirs}"
    # Growth ratio is bounded (no snowball): < 6x per ascension.
    ratio1 = elixirs[1] / elixirs[0]
    ratio2 = elixirs[2] / elixirs[1]
    assert ratio1 < 6.0, f"snowball ratio1 {ratio1}"
    assert ratio2 < 6.0, f"snowball ratio2 {ratio2}"
    # Absolute values are reasonable for the first 3 ascensions.
    assert elixirs[0] >= 40, f"first ascension too low: {elixirs[0]}"
    assert elixirs[2] <= 2000, f"third ascension too high: {elixirs[2]}"
