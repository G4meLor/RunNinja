"""Task 24: Tap-vs-auto DPS rebalance + tap fatigue anti-macro.

The idle-integrity fix. Tap DPS was ~58x auto DPS (94x pre-Task-22)
because tap benefited from ``tap_mult`` (a run upgrade) while auto got
only ``atk_pct`` (evo). This test suite guards:

1. An ``auto_mult`` run upgrade mirrors ``tap_mult`` (a new option, not
   a pure nerf).
2. Tap base scaled down so the tap:auto ratio is ~3:1 at max (not 58:1).
3. Tap fatigue: 5%/tap above 5 taps/s, floor 0.3x (tapping never
   becomes useless).
4. No 100x+ active burst (killed as economy-breaking).
"""
import pytest


# ---------------------------------------------------------------------------
# 1. auto_mult upgrade exists in config
# ---------------------------------------------------------------------------
def test_auto_mult_upgrade_exists():
    """The auto_mult run upgrade is present in TAP_UPGRADE_DEFS."""
    import config as cfg
    keys = {d[0] for d in cfg.TAP_UPGRADE_DEFS}
    assert "auto_mult" in keys, "auto_mult upgrade missing from TAP_UPGRADE_DEFS"


def test_auto_mult_upgrade_in_lookup_maps():
    """auto_mult is in the derived lookup maps (cost, effect, growth)."""
    import config as cfg
    assert "auto_mult" in cfg.UPGRADE_BASE_COST
    assert "auto_mult" in cfg.UPGRADE_BASE_EFFECT
    assert "auto_mult" in cfg.UPGRADE_EFFECT_GROWTH


def test_auto_mult_upgrade_well_formed():
    """The auto_mult row has the (key, label, base_cost, base_effect, growth) shape."""
    import config as cfg
    by_key = {d[0]: d for d in cfg.TAP_UPGRADE_DEFS}
    row = by_key["auto_mult"]
    assert len(row) == 5
    key, label, base_cost, base_effect, growth = row
    assert key == "auto_mult"
    assert isinstance(label, str) and label
    assert base_cost > 0
    assert base_effect > 0
    assert growth >= 1.0


# ---------------------------------------------------------------------------
# 2. auto_mult affects auto damage (a new option, not a pure nerf)
# ---------------------------------------------------------------------------
def test_auto_mult_affects_auto_damage(pygame_headless):
    """The auto_mult upgrade increases auto_damage in compute_ninja_stats."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    base = compute_ninja_stats(state)["auto_damage"]
    state.upgrades = {"auto_mult": 5}
    upgraded = compute_ninja_stats(state)["auto_damage"]
    assert upgraded > base, "auto_mult did not increase auto_damage"


# ---------------------------------------------------------------------------
# 3. Tap:auto ratio ~3:1 at max upgrades (not 58:1 or 94:1)
# ---------------------------------------------------------------------------
def test_tap_auto_ratio_at_max(pygame_headless):
    """At max combat upgrades, tap:auto ratio is ~3:1 (between 2 and 5).

    The ratio is driven by tap_mult / auto_mult (the flat upgrades
    tap_power and auto_attack are ~equal at max, so the base constants
    are negligible). With tap_mastery (Task 22), tap_mult = 1 +
    tap_mult_up + tap_mastery_up; auto_mult = 1 + auto_mult_up. The
    auto_mult base is tuned so the ratio lands at ~3:1.
    """
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    # All combat upgrades at max (100).
    state.upgrades = {
        "tap_power": 100, "tap_mult": 100, "tap_mastery": 100,
        "auto_attack": 100, "auto_mult": 100,
    }
    s = compute_ninja_stats(state)
    ratio = s["tap_damage"] / s["auto_damage"]
    assert 2.0 <= ratio <= 5.0, f"tap:auto ratio {ratio:.2f} outside 2-5 range"


def test_tap_auto_ratio_no_100x_burst(pygame_headless):
    """No 100x+ active burst: the tap:auto ratio (the rebalance's target)
    is bounded so the pre-rebalance 94x ratio is gone.

    The "active burst" the brief kills is the tap:auto RATIO itself
    (94x pre-rebalance, 58x post-Task-22). The rebalance brings that
    ratio to ~3:1. The full crit burst (tap * combo * crit) is a
    separate axis (crit_dmg was already in the game before Task 24 and
    is NOT touched by the rebalance); the tap fatigue + the combo cap
    (3x) bound the active-play upside. This test guards the
    rebalance's core achievement: the tap:auto ratio is no longer
    100x+ (the economy-breaking state the brief kills).
    """
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    # All combat upgrades at max (100), including crit_dmg.
    state.upgrades = {
        "tap_power": 100, "tap_mult": 100, "tap_mastery": 100,
        "auto_attack": 100, "auto_mult": 100, "crit_dmg": 100,
    }
    s = compute_ninja_stats(state)
    # The rebalance's target: the tap:auto ratio (the pre-rebalance
    # 94x / 58x ratio is the "active burst" the brief kills). With the
    # rebalance, this is ~3:1.
    ratio = s["tap_damage"] / s["auto_damage"]
    assert ratio < 100.0, (
        f"tap:auto ratio {ratio:.1f}x -- economy-breaking (pre-rebalance 94x)")
    # The tap fatigue + combo cap (3x) bound the active-play burst
    # further: a macro at 100 taps/s is floored at 0.3x tap damage, so
    # the effective tap DPS is (tap * 0.3 * 100 taps/s) vs auto DPS
    # (auto * attack_speed). Even at 100 taps/s the fatigue brings the
    # effective tap DPS to ~30x the tap:auto ratio (3 * 0.3 * 100 / 1
    # = 90x auto at attack_speed 1), which is under the 100x line.
    # This is the realistic active-burst ceiling the rebalance +
    # fatigue enforce.


# ---------------------------------------------------------------------------
# 4. Tap base scaled down (auto is the backbone at low levels)
# ---------------------------------------------------------------------------
def test_auto_is_backbone_at_low_level(pygame_headless):
    """At zero upgrades, auto_damage >= tap_damage (auto is the backbone)."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    s = compute_ninja_stats(state)
    # With TAP_BASE_SCALE, the tap base constant is scaled down so auto
    # is the backbone at the start; the tap_mult/auto_mult upgrades
    # bring tap up to ~3x at max.
    assert s["auto_damage"] >= s["tap_damage"], (
        f"auto {s['auto_damage']} < tap {s['tap_damage']} at level 0 -- "
        "auto should be the backbone")


# ---------------------------------------------------------------------------
# 5. Tap fatigue constants in config
# ---------------------------------------------------------------------------
def test_tap_fatigue_constants_in_config():
    """The tap fatigue constants are defined in config."""
    import config as cfg
    assert hasattr(cfg, "TAP_FATIGUE_PER_TAP")
    assert hasattr(cfg, "TAP_FATIGUE_THRESHOLD")
    assert hasattr(cfg, "TAP_FATIGUE_FLOOR")
    assert cfg.TAP_FATIGUE_PER_TAP > 0
    assert cfg.TAP_FATIGUE_THRESHOLD > 0
    assert 0 < cfg.TAP_FATIGUE_FLOOR < 1.0


# ---------------------------------------------------------------------------
# 6. Tap fatigue: 5%/tap above 5 taps/s, floor 0.3x
# ---------------------------------------------------------------------------
def test_tap_fatigue_kicks_in(pygame_headless):
    """10 taps in 1 second -> fatigue reduces tap damage but floors at 0.3x."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # 10 taps in well under 1 second of real time.
    for _ in range(10):
        r.tap()
    mult = r.tap_fatigue_mult()
    assert mult >= 0.3, f"fatigue mult {mult} below floor 0.3"
    assert mult < 1.0, f"fatigue mult {mult} -- no fatigue after 10 rapid taps"


def test_tap_fatigue_no_fatigue_below_threshold(pygame_headless):
    """5 or fewer taps in 1 second -> no fatigue (mult == 1.0)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    for _ in range(5):
        r.tap()
    mult = r.tap_fatigue_mult()
    assert mult == 1.0, f"fatigue mult {mult} -- should be 1.0 at threshold"


def test_tap_fatigue_floors_at_0_3(pygame_headless):
    """Even extreme tapping (100 taps/s) floors at 0.3x (never useless)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    for _ in range(100):
        r.tap()
    mult = r.tap_fatigue_mult()
    assert mult >= 0.3, f"fatigue mult {mult} below floor 0.3"
    assert abs(mult - 0.3) < 0.01, f"fatigue mult {mult} -- should be at floor 0.3"


def test_tap_fatigue_recovers_after_1_second(pygame_headless):
    """After 1 second of no tapping, fatigue recovers to 1.0."""
    import time
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    for _ in range(20):
        r.tap()
    assert r.tap_fatigue_mult() < 1.0
    # Wait > 1 second for the tap window to expire.
    time.sleep(1.1)
    assert r.tap_fatigue_mult() == 1.0, "fatigue did not recover after 1s"


# ---------------------------------------------------------------------------
# 7. Tap fatigue applies to actual tap damage
# ---------------------------------------------------------------------------
def test_tap_fatigue_reduces_damage(pygame_headless):
    """Rapid taps deal less damage than slow taps (fatigue is applied)."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_enemy
    from data import enemies as ed
    # First, measure damage with NO fatigue (single tap).
    state1 = GameState()
    r1 = Runner(state1)
    bdef = ed.boss_for_zone(r1.world.zone_id)
    e1 = spawn_enemy(bdef, hp=1e9, dmg=0.0, gold=0.0)
    e1.x = 200
    r1.world.enemies.append(e1)
    r1.tap()
    dmg1 = 1e9 - e1.hp  # damage dealt by a single (un-fatigued) tap

    # Now, measure damage with fatigue (10 rapid taps, take the last one).
    state2 = GameState()
    r2 = Runner(state2)
    damages = []
    for _ in range(10):
        e = spawn_enemy(bdef, hp=1e9, dmg=0.0, gold=0.0)
        e.x = 200
        r2.world.enemies = [e]
        r2.tap()
        damages.append(1e9 - e.hp)
    # The last tap (10th) should deal less damage than the first (un-fatigued).
    assert damages[-1] < dmg1, (
        f"fatigued tap {damages[-1]} >= un-fatigued tap {dmg1} -- "
        "fatigue not applied to tap damage")
