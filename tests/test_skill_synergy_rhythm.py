"""Task 25: Skill synergies + tap rhythm bonus.

Two cheap active-play rewards:
1. Skill Synergies: firing two active skills within 2s in a specific
   order triggers a named synergy bonus (a sequencing puzzle on the 4
   active skills).
2. Tap rhythm: median of last 5 tap intervals in 0.35-0.55s window
   builds rhythm_streak (cap 20), +2.5% tap damage per level. Rhythm is
   strictly a bonus (floor 0, never a penalty) -- motor-impaired players
   aren't punished.

The Speed Step kill-ramp-with-decay rework is NOT implemented (it
punishes idle).
"""
import time as _time

import pytest


# ---------------------------------------------------------------------------
# 1. Synergy table + window
# ---------------------------------------------------------------------------
def test_synergy_table_exists():
    """The 4 synergy pairs are defined in the SYNERGIES table."""
    from engine.skills import SYNERGIES
    assert len(SYNERGIES) >= 4
    assert ("kunai", "shuriken") in SYNERGIES
    assert ("speed", "kunai") in SYNERGIES
    assert ("rope", "shuriken") in SYNERGIES
    assert ("speed", "rope") in SYNERGIES
    # The names from the brief.
    assert SYNERGIES[("kunai", "shuriken")] == "Storm of Steel"
    assert SYNERGIES[("speed", "kunai")] == "Lightning Strike"
    assert SYNERGIES[("rope", "shuriken")] == "Grinding Vortex"
    assert SYNERGIES[("speed", "rope")] == "Phantom Snare"


def test_synergy_window_is_2s():
    """The synergy window is 2.0 seconds."""
    from engine.skills import SYNERGY_WINDOW
    assert SYNERGY_WINDOW == 2.0


# ---------------------------------------------------------------------------
# 2. Synergy triggers on two skills within 2s
# ---------------------------------------------------------------------------
def test_skill_synergy(pygame_headless):
    """Firing kunai then shuriken within 2s triggers 'Storm of Steel'."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken"}
    r = Runner(state)
    r.activate_skill("kunai")
    r.activate_skill("shuriken")  # within 2s -> synergy
    assert r.last_synergy == "Storm of Steel"


def test_synergy_does_not_trigger_outside_window(pygame_headless):
    """Firing two skills > 2s apart does NOT trigger a synergy."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken"}
    r = Runner(state)
    r.activate_skill("kunai")
    # Force the last skill time to be > 2s ago.
    r.last_skill_time -= 3.0
    r.activate_skill("shuriken")
    assert r.last_synergy is None


def test_synergy_wrong_order_no_trigger(pygame_headless):
    """Firing skills in the wrong order does NOT trigger a synergy."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken"}
    r = Runner(state)
    # shuriken -> kunai is NOT in the table (only kunai -> shuriken).
    r.activate_skill("shuriken")
    r.activate_skill("kunai")
    assert r.last_synergy is None


def test_synergy_all_four_pairs(pygame_headless):
    """All 4 synergy pairs trigger when fired in order within 2s."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.skills import SYNERGIES
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken",
                        "ab_rope", "ab_speed"}
    for (first, second), name in SYNERGIES.items():
        r = Runner(state)
        r.activate_skill(first)
        r.activate_skill(second)
        assert r.last_synergy == name, (
            f"synergy {first}->{second} expected {name}, "
            f"got {r.last_synergy}")


# ---------------------------------------------------------------------------
# 3. Synergy is a bonus (deals damage, never a penalty)
# ---------------------------------------------------------------------------
def test_synergy_deals_bonus_damage(pygame_headless):
    """A synergy deals bonus damage to enemies (a flat burst)."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_enemy
    from data.enemies import ZONES
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken"}
    r = Runner(state)
    edef = ZONES[0]["enemies"][0]
    e = spawn_enemy(edef, hp=1e6, dmg=1.0, gold=1.0)
    e.x = 500
    r.world.enemies.append(e)
    hp_before = e.hp
    r.activate_skill("kunai")
    r.activate_skill("shuriken")  # synergy -> bonus damage
    assert e.hp < hp_before


# ---------------------------------------------------------------------------
# 4. Tap rhythm: median of last 5 tap intervals
# ---------------------------------------------------------------------------
def test_rhythm_bonus_never_penalty(pygame_headless):
    """No rhythm -> no bonus, but never a penalty (mult >= 1.0)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    assert r.rhythm_mult() >= 1.0


def test_rhythm_mult_formula(pygame_headless):
    """rhythm_mult = 1.0 + 0.025 * rhythm_streak (floor 1.0)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.rhythm_streak = 0
    assert r.rhythm_mult() == 1.0
    state.rhythm_streak = 10
    assert abs(r.rhythm_mult() - 1.25) < 0.001
    state.rhythm_streak = 20
    assert abs(r.rhythm_mult() - 1.5) < 0.001


def test_rhythm_streak_caps_at_20(pygame_headless):
    """The rhythm cap is 20 (RHYTHM_CAP)."""
    from engine.runner import RHYTHM_CAP
    assert RHYTHM_CAP == 20


def test_rhythm_in_window_increments(pygame_headless):
    """Tapping at ~0.45s intervals (in the 0.35-0.55s window) increments
    the rhythm streak."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    base = _time.monotonic()
    r._rhythm_taps = [base + i * 0.45 for i in range(5)]
    r._update_rhythm_streak()
    assert state.rhythm_streak == 1


def test_rhythm_outside_window_resets(pygame_headless):
    """Tapping too fast (< 0.35s) resets the streak to 0."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.rhythm_streak = 5
    base = _time.monotonic()
    r._rhythm_taps = [base + i * 0.2 for i in range(5)]
    r._update_rhythm_streak()
    assert state.rhythm_streak == 0


def test_rhythm_too_slow_resets(pygame_headless):
    """Tapping too slow (> 0.55s) resets the streak to 0."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    state.rhythm_streak = 5
    base = _time.monotonic()
    r._rhythm_taps = [base + i * 0.8 for i in range(5)]
    r._update_rhythm_streak()
    assert state.rhythm_streak == 0


def test_rhythm_applies_to_tap_damage(pygame_headless):
    """The rhythm multiplier applies to tap damage (a bonus, never a penalty)."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import spawn_enemy
    from data.enemies import ZONES
    # Measure damage with no rhythm.
    state1 = GameState()
    r1 = Runner(state1)
    r1.ninja.crit_chance = 0.0  # deterministic (no crit variance)
    edef = ZONES[0]["enemies"][0]
    e1 = spawn_enemy(edef, hp=1e9, dmg=0.0, gold=0.0)
    e1.x = 200
    r1.world.enemies.append(e1)
    r1.tap()
    dmg1 = 1e9 - e1.hp
    # Measure damage with rhythm streak = 20 (max bonus).
    state2 = GameState()
    r2 = Runner(state2)
    r2.ninja.crit_chance = 0.0
    state2.rhythm_streak = 20
    e2 = spawn_enemy(edef, hp=1e9, dmg=0.0, gold=0.0)
    e2.x = 200
    r2.world.enemies.append(e2)
    r2.tap()
    dmg2 = 1e9 - e2.hp
    assert dmg2 > dmg1, (
        f"rhythm tap {dmg2} <= no-rhythm tap {dmg1} -- rhythm not applied")


# ---------------------------------------------------------------------------
# 5. Rhythm constants
# ---------------------------------------------------------------------------
def test_rhythm_constants_exist():
    """The rhythm constants are defined with the brief's values."""
    from engine.runner import (RHYTHM_CAP, RHYTHM_BONUS_PER_LEVEL,
                               RHYTHM_MIN_INTERVAL, RHYTHM_MAX_INTERVAL,
                               RHYTHM_WINDOW_SIZE)
    assert RHYTHM_CAP == 20
    assert RHYTHM_BONUS_PER_LEVEL == 0.025
    assert RHYTHM_MIN_INTERVAL == 0.35
    assert RHYTHM_MAX_INTERVAL == 0.55
    assert RHYTHM_WINDOW_SIZE == 5


# ---------------------------------------------------------------------------
# 6. Speed Step kill-ramp-with-decay is NOT implemented
# ---------------------------------------------------------------------------
def test_no_speed_step_kill_ramp_decay():
    """The Speed Step skill does NOT implement a kill-ramp-with-decay
    (it punishes idle). The speed skill is a simple energy burst, not a
    ramp that decays on no-kills."""
    from engine.runner import Runner
    import inspect
    src = inspect.getsource(Runner.activate_skill)
    assert "kill_ramp" not in src
    assert "ramp_decay" not in src


def test_speed_skill_is_simple_burst(pygame_headless):
    """The speed skill is a simple energy burst (sets energy_active +
    tops up energy), NOT a kill-ramp-with-decay."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_speed"}
    r = Runner(state)
    energy_before = state.energy
    r.activate_skill("speed")
    assert state.energy_active is True
    assert state.energy >= energy_before


# ---------------------------------------------------------------------------
# 7. Reset on ascension
# ---------------------------------------------------------------------------
def test_synergy_rhythm_reset_on_ascension(pygame_headless):
    """reset_for_ascension clears the synergy + rhythm tracking state."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_kunai", "ab_shuriken"}
    r = Runner(state)
    r.activate_skill("kunai")
    r.activate_skill("shuriken")
    assert r.last_synergy is not None
    state.rhythm_streak = 10
    r.reset_for_ascension()
    assert r.last_synergy is None
    assert r.last_skill_id is None
    assert state.rhythm_streak == 0
