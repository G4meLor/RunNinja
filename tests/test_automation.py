"""Task 28: Automation nodes (auto-cast, auto-firefly, auto-ascend, farm-when-stuck).

Automation nodes gated behind deep elixir investment (an earned endgame
convenience). Five nodes:
  * auto_cast      — auto-fire Rope Hook + Shuriken under Energy.
  * auto_firefly   — auto-collect all fireflies.
  * auto_energy    — auto-activate Energy when available.
  * auto_ascend    — auto-ascend at the player's threshold (respects it).
  * auto_progress  — auto-progress + farm-when-stuck fallback (the road
    never dead-ends an idle player; farm state advances lifetime_gold).
"""
import pytest


# ---------------------------------------------------------------------------
# 1. Automation nodes exist in the skill tree
# ---------------------------------------------------------------------------
def test_automation_nodes_exist():
    """The 5 automation nodes exist in the skill tree."""
    from data import skill_tree as st
    for nid in ("auto_cast", "auto_firefly", "auto_energy",
                "auto_ascend", "auto_progress"):
        assert nid in st.BY_ID, f"missing automation node {nid}"


def test_automation_nodes_high_cost():
    """The automation nodes are high-cost (deep elixir investment)."""
    from data import skill_tree as st
    for nid in ("auto_cast", "auto_firefly", "auto_energy",
                "auto_ascend", "auto_progress"):
        node = st.BY_ID[nid]
        assert node.cost >= 500, f"{nid} cost {node.cost} < 500 (not high-cost)"


def test_automation_nodes_have_prereqs():
    """The automation nodes have prereqs (deep elixir investment)."""
    from data import skill_tree as st
    for nid in ("auto_cast", "auto_firefly", "auto_energy",
                "auto_ascend", "auto_progress"):
        node = st.BY_ID[nid]
        assert node.prereq is not None, f"{nid} has no prereq"


# ---------------------------------------------------------------------------
# 2. Auto-cast (Rope Hook + Shuriken under Energy)
# ---------------------------------------------------------------------------
def test_auto_cast_under_energy(pygame_headless):
    """Auto-cast fires Rope Hook + Shuriken when off cooldown under Energy."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_rope", "ab_shuriken", "auto_cast"}
    state.energy_active = True
    state.energy = 100.0  # enough to stay active through the tick
    r = Runner(state)
    assert "rope" in r.skills
    assert "shuriken" in r.skills
    # Skills start off cooldown.
    assert r.skills["rope"].timer <= 0
    assert r.skills["shuriken"].timer <= 0
    # Run one tick — auto-cast fires the skills (they go on cooldown).
    r.update(1 / 60)
    assert r.skills["rope"].timer > 0
    assert r.skills["shuriken"].timer > 0


def test_auto_cast_requires_energy(pygame_headless):
    """Auto-cast does NOT fire when Energy is not active."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_rope", "ab_shuriken", "auto_cast"}
    state.energy_active = False
    state.energy = 100.0
    r = Runner(state)
    r.update(1 / 60)
    assert r.skills["rope"].timer <= 0
    assert r.skills["shuriken"].timer <= 0


def test_auto_cast_requires_unlock(pygame_headless):
    """Auto-cast does NOT fire without the auto_cast node."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root", "ab_rope", "ab_shuriken"}
    state.energy_active = True
    r = Runner(state)
    r.update(1 / 60)
    assert r.skills["rope"].timer <= 0
    assert r.skills["shuriken"].timer <= 0


# ---------------------------------------------------------------------------
# 3. Auto-firefly (auto-collect fireflies)
# ---------------------------------------------------------------------------
def test_auto_firefly(pygame_headless):
    """Auto-firefly auto-catches fireflies (gold awarded, firefly removed)."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.firefly import spawn_firefly
    state = GameState()
    state.skill_tree = {"auto_firefly"}
    r = Runner(state)
    f = spawn_firefly(500, 250)
    r.world.fireflies.append(f)
    gold_before = state.lifetime_gold
    r.update(1 / 60)
    assert f not in r.world.fireflies
    assert state.lifetime_gold > gold_before


def test_auto_firefly_requires_unlock(pygame_headless):
    """Auto-firefly does NOT auto-catch without the node."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.firefly import spawn_firefly
    state = GameState()
    state.skill_tree = set()
    r = Runner(state)
    f = spawn_firefly(500, 250)
    r.world.fireflies.append(f)
    r.update(1 / 60)
    assert f in r.world.fireflies


# ---------------------------------------------------------------------------
# 4. Auto-energy (auto-activate Energy when available)
# ---------------------------------------------------------------------------
def test_auto_energy(pygame_headless):
    """Auto-energy auto-activates Energy when available."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"auto_energy"}
    state.energy = 100.0
    state.energy_active = False
    state.energy_lockout = 0.0
    r = Runner(state)
    r.update(1 / 60)
    assert state.energy_active is True


def test_auto_energy_requires_unlock(pygame_headless):
    """Auto-energy does NOT auto-activate without the node."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = set()
    state.energy = 100.0
    state.energy_active = False
    state.energy_lockout = 0.0
    r = Runner(state)
    r.update(1 / 60)
    assert state.energy_active is False


def test_auto_energy_respects_lockout(pygame_headless):
    """Auto-energy does NOT activate during the lockout."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"auto_energy"}
    state.energy = 100.0
    state.energy_active = False
    state.energy_lockout = 5.0
    r = Runner(state)
    r.update(1 / 60)
    assert state.energy_active is False


# ---------------------------------------------------------------------------
# 5. Auto-ascend (respects the player's threshold)
# ---------------------------------------------------------------------------
def test_auto_ascend_respects_threshold():
    """Auto-ascend fires only when the player's threshold is met."""
    from core.state import GameState
    from core.ascend import should_auto_ascend
    state = GameState()
    state.skill_tree = {"auto_ascend"}
    state.gold = 50000
    state.lifetime_gold = 50000
    # Base requirement is 5; player's threshold is 7.
    state.auto_ascend_threshold = 7
    state.zone_index = 5  # meets base, NOT the threshold
    assert not should_auto_ascend(state)
    state.zone_index = 7  # meets the threshold
    assert should_auto_ascend(state)


def test_auto_ascend_without_threshold():
    """Auto-ascend fires when no threshold is set (0 = use base requirement)."""
    from core.state import GameState
    from core.ascend import should_auto_ascend
    state = GameState()
    state.skill_tree = {"auto_ascend"}
    state.gold = 50000
    state.lifetime_gold = 50000
    state.auto_ascend_threshold = 0
    state.zone_index = 5  # meets the base requirement
    assert should_auto_ascend(state)


def test_auto_ascend_requires_unlock():
    """Auto-ascend does NOT fire without the node."""
    from core.state import GameState
    from core.ascend import should_auto_ascend
    state = GameState()
    state.skill_tree = set()
    state.gold = 50000
    state.lifetime_gold = 50000
    state.zone_index = 5
    assert not should_auto_ascend(state)


def test_auto_ascend_fires_in_runner(pygame_headless):
    """The runner auto-ascends when the threshold is met."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"auto_ascend"}
    state.gold = 50000
    state.lifetime_gold = 50000
    state.zone_index = 5  # meets the base requirement
    state.auto_ascend_threshold = 0
    elixir_before = state.elixir
    r = Runner(state)
    r.update(1 / 60)
    assert state.elixir > elixir_before
    assert state.zone_index == 0  # reset by ascend


def test_auto_ascend_respects_threshold_in_runner(pygame_headless):
    """The runner does NOT auto-ascend below the player's threshold."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"auto_ascend"}
    state.gold = 50000
    state.lifetime_gold = 50000
    state.zone_index = 5  # meets base, NOT the threshold (7)
    state.auto_ascend_threshold = 7
    elixir_before = state.elixir
    r = Runner(state)
    r.update(1 / 60)
    assert state.elixir == elixir_before  # did NOT ascend
    assert state.zone_index == 5  # unchanged


# ---------------------------------------------------------------------------
# 6. Farm-when-stuck (auto-progress + farm advances lifetime_gold)
# ---------------------------------------------------------------------------
def test_farm_when_stuck(pygame_headless):
    """When stuck on a boss, the road farms (lifetime_gold advances)."""
    from core.state import GameState
    from engine.runner import Runner, FARM_STUCK_THRESHOLD
    from engine.enemy import spawn_boss
    from data.enemies import BOSSES
    state = GameState()
    state.skill_tree = {"auto_progress"}
    state.buildings = {"farm": 5}
    r = Runner(state)
    # Spawn a boss with very high HP (so it can't be killed quickly).
    bdef = BOSSES["village"]
    boss = spawn_boss(bdef, hp=1e9, dmg=1.0, gold=1.0)
    boss.x = 500
    r.world.enemies.append(boss)
    r.world.boss_active = True
    # Set the stuck timer just below the threshold.
    r._boss_stuck_timer = FARM_STUCK_THRESHOLD - 0.1
    gold_before = state.lifetime_gold
    # Run 60 ticks (1 second) — the stuck timer crosses the threshold.
    for _ in range(60):
        r.update(1 / 60)
    assert state.lifetime_gold > gold_before
    assert r.farm_mode is True


def test_farm_when_stuck_requires_unlock(pygame_headless):
    """Farm-when-stuck does NOT engage without the auto_progress node."""
    from core.state import GameState
    from engine.runner import Runner, FARM_STUCK_THRESHOLD
    from engine.enemy import spawn_boss
    from data.enemies import BOSSES
    state = GameState()
    state.skill_tree = set()
    state.buildings = {"farm": 5}
    r = Runner(state)
    bdef = BOSSES["village"]
    boss = spawn_boss(bdef, hp=1e9, dmg=1.0, gold=1.0)
    boss.x = 500
    r.world.enemies.append(boss)
    r.world.boss_active = True
    r._boss_stuck_timer = FARM_STUCK_THRESHOLD + 1.0
    for _ in range(60):
        r.update(1 / 60)
    assert r.farm_mode is False


def test_farm_when_stuck_clears_on_boss_death(pygame_headless):
    """Farm mode clears when the boss is killed (no longer stuck)."""
    from core.state import GameState
    from engine.runner import Runner, FARM_STUCK_THRESHOLD
    from engine.enemy import spawn_boss
    from data.enemies import BOSSES
    state = GameState()
    state.skill_tree = {"auto_progress"}
    r = Runner(state)
    bdef = BOSSES["village"]
    boss = spawn_boss(bdef, hp=1e9, dmg=1.0, gold=1.0)
    boss.x = 500
    r.world.enemies.append(boss)
    r.world.boss_active = True
    r._boss_stuck_timer = FARM_STUCK_THRESHOLD + 1.0
    r.farm_mode = True
    # Kill the boss.
    boss.alive = False
    boss.hp = 0
    r.world.boss_active = False
    r.update(1 / 60)
    assert r.farm_mode is False
    assert r._boss_stuck_timer == 0.0


# ---------------------------------------------------------------------------
# 7. Farm-when-stuck offline (core/offline.py farm gold)
# ---------------------------------------------------------------------------
def test_farm_when_stuck_offline():
    """The offline farm_when_stuck returns farm gold when auto_progress is unlocked."""
    from core.state import GameState
    from core.offline import farm_when_stuck
    state = GameState()
    state.skill_tree = {"auto_progress"}
    state.buildings = {"farm": 5}
    assert farm_when_stuck(state, 60) > 0
    # Without auto_progress, the farm gold is 0.
    state.skill_tree = set()
    assert farm_when_stuck(state, 60) == 0


def test_farm_when_stuck_offline_added_to_compute():
    """The offline compute adds farm gold when auto_progress is unlocked."""
    from core.state import GameState
    from core.offline import compute, farm_when_stuck
    state = GameState()
    state.skill_tree = {"auto_progress"}
    state.buildings = {"farm": 5}
    # Set last_saved far in the past so compute returns a report.
    import time as _time
    state.last_saved = _time.time() - 7200  # 2 hours ago
    report = compute(state)
    assert report.get("applied") is True
    # The report's gold is > 0 (farm gold + normal offline gold).
    assert report["gold"] > 0


# ---------------------------------------------------------------------------
# 8. State field + migration
# ---------------------------------------------------------------------------
def test_auto_ascend_threshold_field():
    """GameState has an auto_ascend_threshold field (default 0)."""
    from core.state import GameState
    s = GameState()
    assert hasattr(s, "auto_ascend_threshold")
    assert s.auto_ascend_threshold == 0


def test_auto_ascend_threshold_migrated():
    """A v2 save migrated to v3 has auto_ascend_threshold."""
    from core.state import _migrate_v2_to_v3
    d = {"save_version": 2}
    d = _migrate_v2_to_v3(d)
    assert "auto_ascend_threshold" in d
    assert d["auto_ascend_threshold"] == 0
