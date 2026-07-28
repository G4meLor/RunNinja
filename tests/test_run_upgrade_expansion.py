"""Task 22: Run upgrade expansion + new skill-tree branches.

Two content additions that deepen the per-run build without adding a new
verb:

1. **Run upgrade expansion** -- 7 new rows in ``TAP_UPGRADE_DEFS``
   (13 -> 20): tap-specialist (tap_crit, tap_speed, tap_mastery),
   active-skill-adjacent (skill_dmg, skill_cd), combo-decay-resistance
   (combo_grace, combo_sustain). Run upgrades reset on ascension so
   there is no save-migration risk.

2. **New skill-tree branches** -- Defense, Combo, Tap Mastery branches
   with 6-tier chains + cross-branch capstones, plus active-skill tier
   upgrades (t2/t3) chaining off existing ``ab_*`` nodes. The new nodes
   are permanent (bought with elixir); the ``skill_tree`` set just grows,
   so no save migration is needed.

The new upgrade keys are wired into the engine so they actually DO
something (crit chance, attack speed, skill damage, skill cooldown,
combo grace, combo decay, tap damage).
"""
import pytest


# ---------------------------------------------------------------------------
# Run upgrade expansion (config.py)
# ---------------------------------------------------------------------------
def test_upgrade_count_expanded():
    """TAP_UPGRADE_DEFS expanded from 13 to >= 20."""
    import config as cfg
    assert len(cfg.TAP_UPGRADE_DEFS) >= 20


def test_new_upgrade_keys_present():
    """The 7 new upgrade keys are present in TAP_UPGRADE_DEFS."""
    import config as cfg
    keys = {d[0] for d in cfg.TAP_UPGRADE_DEFS}
    for k in ("tap_crit", "tap_speed", "skill_dmg", "skill_cd",
              "combo_grace", "combo_sustain", "tap_mastery"):
        assert k in keys, f"missing upgrade key {k}"


def test_new_upgrade_keys_in_maps():
    """All 7 new keys are in the derived lookup maps."""
    import config as cfg
    new_keys = ("tap_crit", "tap_speed", "skill_dmg", "skill_cd",
                "combo_grace", "combo_sustain", "tap_mastery")
    for k in new_keys:
        assert k in cfg.UPGRADE_BASE_COST, f"missing {k} in UPGRADE_BASE_COST"
        assert k in cfg.UPGRADE_BASE_EFFECT, f"missing {k} in UPGRADE_BASE_EFFECT"
        assert k in cfg.UPGRADE_EFFECT_GROWTH, f"missing {k} in UPGRADE_EFFECT_GROWTH"


def test_new_upgrade_rows_well_formed():
    """Each new row has the (key, label, base_cost, base_effect, growth) shape."""
    import config as cfg
    by_key = {d[0]: d for d in cfg.TAP_UPGRADE_DEFS}
    for k in ("tap_crit", "tap_speed", "skill_dmg", "skill_cd",
              "combo_grace", "combo_sustain", "tap_mastery"):
        row = by_key[k]
        assert len(row) == 5, f"{k} row has {len(row)} fields, expected 5"
        key, label, base_cost, base_effect, growth = row
        assert key == k
        assert isinstance(label, str) and label
        assert base_cost > 0, f"{k} base_cost must be > 0"
        assert base_effect > 0, f"{k} base_effect must be > 0"
        assert growth >= 1.0, f"{k} growth must be >= 1.0"


# ---------------------------------------------------------------------------
# New skill-tree branches (data/skill_tree.py)
# ---------------------------------------------------------------------------
def test_new_skill_tree_branches():
    """Defense, Combo, Tap Mastery branches exist in the tree."""
    from data.skill_tree import NODES, BRANCHES
    branches = set(n.branch for n in NODES)
    assert "defense" in branches, "missing defense branch"
    assert "combo" in branches, "missing combo branch"
    assert "tap_mastery" in branches, "missing tap_mastery branch"
    # The BRANCHES tuple also includes the new branches.
    assert "defense" in BRANCHES
    assert "combo" in BRANCHES
    assert "tap_mastery" in BRANCHES


def test_new_branches_have_roots():
    """Each new branch has a root node (prereq is None)."""
    from data.skill_tree import NODES, roots
    root_branches = {n.branch for n in roots()}
    assert "defense" in root_branches
    assert "combo" in root_branches
    assert "tap_mastery" in root_branches


def test_new_branches_have_tier_chains():
    """Each new branch has a multi-tier chain (at least 4 nodes)."""
    from data.skill_tree import nodes_by_branch
    for branch in ("defense", "combo", "tap_mastery"):
        nodes = nodes_by_branch(branch)
        assert len(nodes) >= 4, f"{branch} has only {len(nodes)} nodes"
        # At least one node has a prereq (a chain, not just a root).
        assert any(n.prereq is not None for n in nodes), (
            f"{branch} has no chain (all roots)")


def test_active_skill_tier_upgrades_exist():
    """t2/t3 active-skill upgrades chain off existing ab_* nodes."""
    from data.skill_tree import NODES, BY_ID
    ids = {n.id for n in NODES}
    # t2/t3 upgrades chain off existing ab_* nodes.
    for nid in ("ab_kunai_t2", "ab_kunai_t3",
                "ab_shuriken_t2", "ab_shuriken_t3"):
        assert nid in ids, f"missing active-skill tier upgrade {nid}"
        node = BY_ID[nid]
        # The prereq is an ab_* node (chains off the abilities branch).
        assert node.prereq is not None
        assert node.prereq.startswith("ab_"), (
            f"{nid} prereq {node.prereq} does not chain off an ab_* node")


def test_cross_branch_capstones_exist():
    """Cross-branch capstones exist (a node whose prereq is in another branch)."""
    from data.skill_tree import NODES, BY_ID
    # A cross-branch capstone has a prereq in a different branch than itself.
    cross = []
    for n in NODES:
        if n.prereq is None:
            continue
        parent = BY_ID.get(n.prereq)
        if parent is None:
            continue
        if parent.branch != n.branch:
            cross.append((n.id, n.branch, parent.branch))
    assert len(cross) >= 1, "no cross-branch capstones found"


# ---------------------------------------------------------------------------
# Engine wiring -- the new upgrade keys actually DO something
# ---------------------------------------------------------------------------
def test_tap_crit_affects_crit_chance(pygame_headless):
    """tap_crit upgrade adds to crit_chance in compute_ninja_stats."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    base = compute_ninja_stats(state)["crit_chance"]
    state.upgrades = {"tap_crit": 5}
    upgraded = compute_ninja_stats(state)["crit_chance"]
    assert upgraded > base, "tap_crit did not increase crit_chance"


def test_tap_speed_affects_attack_speed(pygame_headless):
    """tap_speed upgrade adds to attack_speed in compute_ninja_stats."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    base = compute_ninja_stats(state)["attack_speed"]
    state.upgrades = {"tap_speed": 5}
    upgraded = compute_ninja_stats(state)["attack_speed"]
    assert upgraded > base, "tap_speed did not increase attack_speed"


def test_tap_mastery_affects_tap_damage(pygame_headless):
    """tap_mastery upgrade adds to tap damage in compute_ninja_stats."""
    from core.state import GameState
    from engine.ninja import compute_ninja_stats
    state = GameState()
    base = compute_ninja_stats(state)["tap_damage"]
    state.upgrades = {"tap_mastery": 5}
    upgraded = compute_ninja_stats(state)["tap_damage"]
    assert upgraded > base, "tap_mastery did not increase tap_damage"


def test_skill_dmg_affects_skill_damage(pygame_headless):
    """skill_dmg upgrade increases the damage dealt by activate_skill."""
    from core.state import GameState
    from engine.runner import Runner
    from engine.enemy import Enemy, spawn_enemy
    from data.enemies import zone_by_id
    # Set up a runner with a kunai skill unlocked and an enemy in range.
    state = GameState()
    state.skill_tree = {"ab_root"}  # unlock kunai
    r = Runner(state)
    # Spawn an enemy with high HP so we can measure the damage dealt.
    edef = zone_by_id("village")["enemies"][0]
    e = spawn_enemy(edef, hp=10000, dmg=0, gold=0)
    e.x = 200
    r.world.enemies.append(e)
    # Damage without the skill_dmg upgrade.
    e.hp = 10000
    r.activate_skill("kunai")
    dmg_base = 10000 - e.hp
    assert dmg_base > 0, "kunai did no damage"
    # Reset and damage with the skill_dmg upgrade.
    state.upgrades = {"skill_dmg": 10}
    r._refresh_skills()  # recompute cooldowns after upgrade change
    e.hp = 10000
    r.activate_skill("kunai")
    dmg_upgraded = 10000 - e.hp
    assert dmg_upgraded > dmg_base, "skill_dmg did not increase skill damage"


def test_skill_cd_affects_skill_cooldown(pygame_headless):
    """skill_cd upgrade reduces the effective skill cooldown."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    state.skill_tree = {"ab_root"}  # unlock kunai
    r = Runner(state)
    # Base cooldown for kunai.
    base_cd = r.skills["kunai"].cooldown
    # With the skill_cd upgrade, the effective cooldown should be lower.
    state.upgrades = {"skill_cd": 10}
    r._refresh_skills()
    eff_cd = r.skills["kunai"].cooldown
    assert eff_cd < base_cd, "skill_cd did not reduce cooldown"


def test_combo_grace_affects_combo_decay(pygame_headless):
    """combo_grace upgrade extends the combo grace window."""
    from core.state import GameState
    from engine.runner import Runner, COMBO_GRACE
    state = GameState()
    r = Runner(state)
    base_grace = r.combo_grace()
    assert base_grace == COMBO_GRACE
    state.upgrades = {"combo_grace": 5}
    upgraded_grace = r.combo_grace()
    assert upgraded_grace > base_grace, "combo_grace did not extend grace window"


def test_combo_sustain_affects_combo_decay(pygame_headless):
    """combo_sustain upgrade slows combo decay (slower timer drain)."""
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    base_decay = r.combo_decay_rate()
    state.upgrades = {"combo_sustain": 5}
    upgraded_decay = r.combo_decay_rate()
    assert upgraded_decay < base_decay, "combo_sustain did not slow decay"


def test_combo_window_skill_tree_bonus_is_read(pygame_headless):
    """The combo branch main chain's ``combo_window`` effect key is read
    by the engine (the skill-tree bonus, not just the run upgrade).

    The combo branch root (``combo_root``) uses ``combo_window`` as its
    effect key. The runner's ``_on_enemy_killed`` must read
    ``evo.get("combo_window", 0.0)`` (the skill-tree bonus) IN ADDITION
    to ``_upgrade_val(state, "combo_window")`` (the run upgrade) so the
    skill-tree combo branch main chain actually does something.
    """
    from core.state import GameState
    from engine.runner import Runner, COMBO_WINDOW
    state = GameState()
    r = Runner(state)
    # No combo_window run upgrade, no skill-tree bonus -> base window.
    state.combo = 0
    r._on_enemy_killed.__wrapped__ if hasattr(r._on_enemy_killed, "__wrapped__") else None
    # Simulate a kill to set the combo timer.
    from engine.enemy import spawn_enemy
    from data.enemies import zone_by_id
    edef = zone_by_id("village")["enemies"][0]
    e = spawn_enemy(edef, hp=1, dmg=0, gold=0)
    e.alive = False  # already dead so _on_enemy_killed doesn't re-kill
    from core.bonuses import aggregate_bonuses
    evo = aggregate_bonuses(state)
    r._on_enemy_killed(e, 1.0, 1.0, evo)
    base_timer = state.combo_timer
    assert base_timer == pytest.approx(COMBO_WINDOW), (
        f"base combo_timer {base_timer} != COMBO_WINDOW {COMBO_WINDOW}")
    # Now unlock the combo_root skill-tree node (combo_window +0.5).
    state.combo = 0
    state.skill_tree = {"combo_root"}
    evo = aggregate_bonuses(state)
    r._on_enemy_killed(e, 1.0, 1.0, evo)
    skilled_timer = state.combo_timer
    assert skilled_timer > base_timer, (
        f"combo_root skill-tree bonus did not extend combo_timer: "
        f"{skilled_timer} <= {base_timer}")


def test_revive_pct_skill_tree_bonus_is_read(pygame_headless):
    """The ``revive_pct`` skill-tree bonus (from the defense branch's
    Phoenix Shell node) is read by the engine in the ninja respawn.

    The runner's respawn block must read ``evo.get("revive_pct", 0.0)``
    and raise the respawn HP above the base 0.3 * max_hp.
    """
    from core.state import GameState
    from engine.runner import Runner
    state = GameState()
    r = Runner(state)
    # Kill the ninja so the respawn block fires on the next update.
    r.ninja.alive = False
    r.ninja.hp = 0
    base_max_hp = r.ninja.max_hp
    # Without the revive_pct bonus, the ninja respawns at 0.3 * max_hp.
    r.update(0.1)
    base_respawn_hp = r.ninja.hp
    assert base_respawn_hp == pytest.approx(base_max_hp * 0.3), (
        f"base respawn hp {base_respawn_hp} != 0.3 * {base_max_hp}")
    # With the revive_pct bonus (from the def_revive1 node, +0.25),
    # the ninja respawns at (0.3 + 0.25) * max_hp = 0.55 * max_hp.
    r.ninja.alive = False
    r.ninja.hp = 0
    state.skill_tree = {"def_revive1"}
    r.update(0.1)
    skilled_respawn_hp = r.ninja.hp
    assert skilled_respawn_hp > base_respawn_hp, (
        f"revive_pct skill-tree bonus did not raise respawn hp: "
        f"{skilled_respawn_hp} <= {base_respawn_hp}")
    assert skilled_respawn_hp == pytest.approx(base_max_hp * 0.55), (
        f"revive_pct respawn hp {skilled_respawn_hp} != 0.55 * {base_max_hp}")


# ---------------------------------------------------------------------------
# Reset on ascension -- run upgrades reset (no save-migration risk)
# ---------------------------------------------------------------------------
def test_run_upgrades_reset_on_ascension(pygame_headless):
    """Run upgrades (including the new keys) reset on ascension."""
    from core.state import GameState
    from core.ascend import ascend
    state = GameState()
    state.gold = 0.0
    state.lifetime_gold = 100000.0  # enough for elixir
    state.zone_index = 10  # past the ascend requirement
    state.upgrades = {"tap_crit": 5, "tap_speed": 5, "skill_dmg": 5,
                      "skill_cd": 5, "combo_grace": 5, "combo_sustain": 5,
                      "tap_mastery": 5, "tap_power": 5}
    gained = ascend(state)
    assert gained > 0
    assert state.upgrades == {}, "upgrades were not reset on ascension"


# ---------------------------------------------------------------------------
# No save-migration risk -- the new skill-tree nodes are additive
# ---------------------------------------------------------------------------
def test_new_skill_tree_nodes_additive(pygame_headless):
    """New skill-tree nodes load fine in a fresh state (no migration needed)."""
    from core.state import GameState
    from data.skill_tree import NODES, BY_ID
    state = GameState()
    # A fresh state has an empty skill_tree set; the new nodes are just
    # additional entries in NODES/BY_ID, so they load without migration.
    assert state.skill_tree == set()
    # The new branches' nodes are in NODES/BY_ID.
    for nid in ("def_root", "combo_root", "tap_mastery_root",
                "ab_kunai_t2", "ab_kunai_t3",
                "ab_shuriken_t2", "ab_shuriken_t3"):
        assert nid in BY_ID, f"missing node {nid}"


# ---------------------------------------------------------------------------
# UI guard -- the records screen skill count uses the live node count
# ---------------------------------------------------------------------------
def test_records_screen_uses_live_node_count(pygame_headless):
    """The records screen 'Skills' stat uses len(st.NODES), not a hardcoded
    number, so the new nodes are reflected."""
    import importlib
    import ui.screen_records as sr
    # The module must reference len(st.NODES) or st.NODES (not a hardcoded
    # "54"). Re-import to be safe.
    importlib.reload(sr)
    src = open(sr.__file__).read()
    # The old hardcoded "/54" should be gone (replaced with the live count).
    assert "/54" not in src, (
        "screen_records.py still hardcodes /54 -- should use len(st.NODES)")
