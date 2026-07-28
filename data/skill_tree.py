"""Elixir skill tree — 200+ permanent nodes across 7 branches.

Each node is purchased with Elixir (the prestige currency) and grants a
permanent bonus that persists across ascensions.  The tree is generated
programmatically: each branch has a chain of tiers (root → t2 → t3 → t4
→ t5 → t6) with costs scaling ~2.5x per tier and effect values scaling
~1.5x per tier, plus a handful of cross-branch "gate" nodes that unlock
new mechanics (Godai Elements, active skills).

The engine consumes the unlocked set via ``aggregate_bonuses`` (in
core/evolution) into a flat ``{effect_key: total_value}`` dict.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SkillNode:
    id: str
    name: str
    branch: str
    cost: int            # elixir cost
    prereq: str | None   # parent node id
    effect_key: str
    effect_value: float
    desc: str


BRANCHES = ("offense", "economy", "elixir", "energy",
            "firefly", "abilities", "godai",
            "defense", "combo", "tap_mastery")


# Branch root configs: (branch, root_id, root_name, root_key, root_val, root_desc)
_ROOTS = [
    ("offense", "off_root", "Way of the Blade", "tap_pct", 0.10,
     "+10% tap damage. The path of the sword begins."),
    ("economy", "eco_root", "Way of Wealth", "gold_pct", 0.10,
     "+10% gold from enemies."),
    ("elixir", "eli_root", "Way of Rebirth", "elixir_pct", 0.10,
     "+10% elixir gain on ascension."),
    ("energy", "eng_root", "Way of Stamina", "energy_timer", 30.0,
     "+30s auto-katana duration."),
    ("firefly", "fly_root", "Way of Lights", "firefly_spawn", 0.10,
     "+10% firefly spawn rate."),
    ("abilities", "ab_root", "Way of Techniques", "unlock_kunai", 1.0,
     "Unlock Kunai Barrage. Throw a storm of blades."),
    # --- Task 22: new branches (Defense/Combo/Tap Mastery) ---
    ("defense", "def_root", "Iron Skin", "def_pct", 0.10,
     "+10% defense. The way of the unbreakable."),
    ("combo", "combo_root", "Combo Flow", "combo_window", 0.5,
     "+0.5s combo window. The way of the endless chain."),
    ("tap_mastery", "tap_mastery_root", "Tap Master", "tap_pct", 0.10,
     "+10% tap damage. The way of the perfect strike."),
]

# Per-tier cost and value multipliers.
_TIER_COST_MULT = (1.0, 2.5, 6.0, 15.0, 40.0, 100.0)
_TIER_VAL_MULT = (1.0, 1.5, 2.2, 3.2, 4.5, 6.5)
_BASE_COST = 5

# Effect key per branch (for the main chain).
_BRANCH_KEY = {
    "offense": "tap_pct",
    "economy": "gold_pct",
    "elixir": "elixir_pct",
    "energy": "energy_timer",
    "firefly": "firefly_spawn",
    "defense": "def_pct",
    "combo": "combo_window",
    "tap_mastery": "tap_pct",
}

# Tier names for flavor.
_TIER_NAMES = {
    "offense": ["Way of the Blade", "Keen Edge", "Iron Storm",
                "Thousand Cuts", "Blade Sage", "Eternal Edge"],
    "economy": ["Way of Wealth", "Golden Touch", "Midas Path",
                "Treasure Road", "Fortune Sage", "Eternal Gold"],
    "elixir": ["Way of Rebirth", "Phoenix Soul", "Reincarnation",
               "Eternal Return", "Samsara Master", "Ouroboros"],
    "energy": ["Way of Stamina", "Iron Lungs", "Endless Breath",
               "Tireless Walker", "Eternal Stamina", "Infinite Wind"],
    "firefly": ["Way of Lights", "Lantern Path", "Firefly Song",
                "Hundred Lights", "Light Sage", "Eternal Glow"],
    # --- Task 22: new branches ---
    "defense": ["Iron Skin", "Stone Body", "Mountain Stance",
                "Unbreakable Will", "Iron Sage", "Eternal Stone"],
    "combo": ["Combo Flow", "River Strike", "Endless Chain",
              "Thousand Combos", "Combo Sage", "Eternal Flow"],
    "tap_mastery": ["Tap Master", "Perfect Strike", "One-Cut Path",
                    "Thousand Strikes", "Strike Sage", "Eternal Strike"],
}

# Extra economic nodes (added alongside the main chain) for variety.
_EXTRA_NODES = [
    # Offense extras (crit)
    ("off_crit1", "Critical Eye", "offense", 20, "off_root",
     "crit_pct", 0.02, "+2% crit chance."),
    ("off_crit2", "Death Strike", "offense", 60, "off_crit1",
     "crit_dmg_pct", 0.10, "+10% crit damage."),
    ("off_atk1", "Auto Blade", "offense", 25, "off_root",
     "atk_pct", 0.10, "+10% auto-attack damage."),
    # Cleave (Task 16): overkill-clears the next K enemies when a tap
    # massively overkills. Gated behind mid-ascension (``ascend_tier >= 3``)
    # in ``Runner.cleave_count()`` so a new player never sees splash in
    # the first runs. The node contributes a flat ``cleave`` count (the
    # number of enemies to chain-clear on a massive overkill); the runner
    # multiplies it by the tier gate. Cost scales with the offense chain.
    ("off_cleave1", "Cleave", "offense", 80, "off_atk1",
     "cleave", 1.0, "+1 enemy chain-cleared on massive overkill (tier 3+)."),
    # Economy extras (building output, away income)
    ("eco_gps1", "Builder's Hand", "economy", 20, "eco_root",
     "gps_pct", 0.10, "+10% building gold/sec."),
    ("eco_gps2", "Master Builder", "economy", 80, "eco_gps1",
     "gps_pct", 0.15, "+15% building gold/sec."),
    ("eco_away1", "Away Fortune", "economy", 30, "eco_root",
     "away_pct", 0.15, "+15% offline gold."),
    ("eco_coin1", "Coin Eye", "economy", 40, "eco_root",
     "coin_pct", 0.10, "+10% coin drop value."),
    ("eco_density1", "Crowded Road", "economy", 50, "eco_root",
     "density_pct", 0.08, "+8% enemy density."),
    # Elixir extras
    ("eli_ascend1", "Quick Rebirth", "elixir", 30, "eli_root",
     "ascend_cost_pct", 0.05, "-5% ascension zone requirement."),
    ("eli_farms1", "Homestead", "elixir", 40, "eli_root",
     "start_farms", 3.0, "Start each ascension with 3 farms."),
    # Energy extras
    ("eng_regen1", "Swift Recovery", "energy", 25, "eng_root",
     "energy_regen", 0.15, "+15% energy regen."),
    ("eng_kill1", "Kill Energy", "energy", 35, "eng_root",
     "energy_from_kill", 0.5, "+0.5 energy per kill."),
    # Firefly extras
    ("fly_gold1", "Light Gold", "firefly", 20, "fly_root",
     "firefly_gold", 0.20, "+20% firefly gold."),
    ("fly_size1", "Big Lights", "firefly", 25, "fly_root",
     "firefly_size", 0.10, "+10% firefly size (easier to catch)."),
    # Abilities (active skills) — unlocked in order.
    ("ab_kunai", "Kunai Barrage", "abilities", 50, "ab_root",
     "unlock_kunai", 1.0, "Unlock Kunai Barrage active skill."),
    ("ab_shuriken", "Shuriken Vortex", "abilities", 200, "ab_kunai",
     "unlock_shuriken", 1.0, "Unlock Shuriken Vortex AOE skill."),
    ("ab_rope", "Rope Hook", "abilities", 400, "ab_shuriken",
     "unlock_rope", 1.0, "Unlock Rope Hook (instant-kill weak enemies)."),
    ("ab_speed", "Speed Step", "abilities", 150, "ab_kunai",
     "unlock_speed", 1.0, "Unlock Speed Step (attack/move burst)."),
    # Dojo nodes — the abilities-branch fork where the player commits to
    # one damage path per ascension. Each dojo maps to a Godai element
    # (Kage-bunshin->Void, Iaijutsu->Wind, Shikigami->Fire,
    # Kusari-gama->Water); Earth is the generalist's utility/defense
    # heritage. The nodes themselves grant a small permanent additive buff
    # toward their stat; the bigger per-ascension buff comes from the
    # dojo provider reading ``state.dojo`` (respec is free -- the player
    # can change dojo any time). Specialization is ADDITIVE (buffs toward
    # the chosen path), NOT a mutually-exclusive capstone.
    ("dojo_kage_bunshin", "Kage-bunshin Dojo", "abilities", 120, "ab_root",
     "atk_pct", 0.05, "+5% auto-attack. Idle shadow-clone path (Void)."),
    ("dojo_iaijutsu", "Iaijutsu Dojo", "abilities", 120, "ab_root",
     "tap_pct", 0.05, "+5% tap damage. Quick-draw tap-burst path (Wind)."),
    ("dojo_shikigami", "Shikigami Dojo", "abilities", 120, "ab_root",
     "crit_dmg_pct", 0.05, "+5% crit damage. Spirit-summon path (Fire)."),
    ("dojo_kusari_gama", "Kusari-gama Dojo", "abilities", 120, "ab_root",
     "speed_pct", 0.05, "+5% attack speed. Chain multi-hit path (Water)."),
    # Godai gate — unlocks the element branch.
    ("godai_gate", "Godai Elements", "godai", 1000, "eli_root",
     "unlock_godai", 1.0, "Unlock the Godai Elements sub-tree."),
    ("godai_void", "Element of Void", "godai", 300, "godai_gate",
     "godai_void", 0.15, "+15% elixir gain."),
    ("godai_wind", "Element of Wind", "godai", 300, "godai_gate",
     "godai_wind", 0.15, "+15% gold/sec."),
    ("godai_fire", "Element of Fire", "godai", 300, "godai_gate",
     "godai_fire", 0.15, "+15% coin gold value."),
    ("godai_water", "Element of Water", "godai", 300, "godai_gate",
     "godai_water", 0.15, "+15% hero power."),
    # Auto-attune toggle (Task 21 / gp-godai-fusion): when unlocked, the
    # runner automatically picks the element that beats the current zone's
    # dominant enemy element (2x advantage) each tick, so idle players get
    # the 2x bonus without micromanaging attunement. WITHOUT this node,
    # ``state.attuned_element`` stays "none" (1x) — idle is never worse
    # than 1x. The node is the COMPLEMENT to the 4 element nodes (the
    # unlock gate for the fusion layer), NOT a competing system: the
    # element nodes still grant their flat +15% stat boosts; the auto-
    # attune + fusion layer on top.
    ("godai_auto_attune", "Auto Attunement", "godai", 500, "godai_gate",
     "auto_attune", 1.0, "Auto-pick the best element for the current zone (idle 2x)."),
    # --- Task 22: active-skill tier upgrades (t2/t3) chaining off ab_* nodes ---
    # These deepen the abilities branch by adding tier-2 and tier-3 upgrades
    # for the kunai and shuriken skill chains. They grant a small permanent
    # buff to the skill's stat (tap_pct for kunai, atk_pct for shuriken) so
    # the upgrade is meaningful without a new verb.
    ("ab_kunai_t2", "Kunai Mastery", "abilities", 150, "ab_kunai",
     "tap_pct", 0.05, "+5% tap damage. Kunai Barrage tier-2 upgrade."),
    ("ab_kunai_t3", "Kunai Storm", "abilities", 400, "ab_kunai_t2",
     "tap_pct", 0.08, "+8% tap damage. Kunai Barrage tier-3 capstone."),
    ("ab_shuriken_t2", "Shuriken Mastery", "abilities", 300, "ab_shuriken",
     "atk_pct", 0.05, "+5% auto-attack. Shuriken Vortex tier-2 upgrade."),
    ("ab_shuriken_t3", "Shuriken Tempest", "abilities", 600, "ab_shuriken_t2",
     "atk_pct", 0.08, "+8% auto-attack. Shuriken Vortex tier-3 capstone."),
    # --- Task 22: Defense branch extras (HP + revive) ---
    ("def_hp1", "Vital Guard", "defense", 30, "def_root",
     "hp_pct", 0.10, "+10% max HP."),
    ("def_hp2", "Mountain Body", "defense", 80, "def_hp1",
     "hp_pct", 0.15, "+15% max HP."),
    ("def_revive1", "Phoenix Shell", "defense", 120, "def_root",
     "revive_pct", 0.25, "Revive once per zone at 25% HP."),
    # --- Task 22: Combo branch extras (grace + step) ---
    ("combo_grace1", "Graceful Chain", "combo", 30, "combo_root",
     "combo_grace_pct", 0.20, "+20% combo grace window."),
    ("combo_grace2", "Eternal Chain", "combo", 80, "combo_grace1",
     "combo_grace_pct", 0.30, "+30% combo grace window."),
    ("combo_step1", "Flowing Strikes", "combo", 50, "combo_root",
     "combo_step_pct", 0.10, "+10% combo multiplier ramp speed."),
    # --- Task 22: Tap Mastery branch extras (crit + speed) ---
    ("tap_mastery_crit1", "Critical Tap", "tap_mastery", 30, "tap_mastery_root",
     "crit_pct", 0.02, "+2% crit chance for taps."),
    ("tap_mastery_crit2", "Perfect Critical", "tap_mastery", 80, "tap_mastery_crit1",
     "crit_dmg_pct", 0.10, "+10% crit damage for taps."),
    ("tap_mastery_speed1", "Lightning Tap", "tap_mastery", 40, "tap_mastery_root",
     "speed_pct", 0.05, "+5% attack speed for taps."),
    # --- Task 22: cross-branch capstones ---
    # These require nodes from a different branch than themselves, so they
    # are true cross-branch capstones that encourage hybrid builds. The
    # prereq is a mid-tier node from another branch (the capstone's own
    # branch is where the node lives, but the prereq is cross-branch).
    ("capstone_off_def", "Blade and Shield", "offense", 200, "defense_t3",
     "tap_pct", 0.10, "+10% tap damage. Requires defense tier 3 (cross-branch)."),
    ("capstone_tap_combo", "Flowing Strike", "tap_mastery", 250, "combo_t3",
     "tap_pct", 0.12, "+12% tap damage. Requires combo tier 3 (cross-branch)."),
    ("capstone_def_combo", "Iron Flow", "defense", 250, "offense_t3",
     "def_pct", 0.10, "+10% defense. Requires offense tier 3 (cross-branch)."),
]


def _build_tree() -> list[SkillNode]:
    nodes: list[SkillNode] = []
    for branch, root_id, root_name, root_key, root_val, root_desc in _ROOTS:
        # Main chain: 6 tiers (only for branches with tier names).
        tier_names = _TIER_NAMES.get(branch)
        if tier_names is None:
            # Abilities branch: only the root; the rest are extra nodes.
            nodes.append(SkillNode(root_id, root_name, branch, _BASE_COST,
                                   None, root_key, root_val, root_desc))
            continue
        prev = None
        for tier in range(6):
            if tier == 0:
                nid = root_id
                name = root_name
                key = root_key
                val = root_val
                desc = root_desc
                cost = _BASE_COST
                prereq = None
            else:
                nid = f"{branch}_t{tier+1}"
                name = tier_names[tier]
                key = root_key
                val = round(root_val * _TIER_VAL_MULT[tier], 4)
                desc = f"+{val*100 if val < 1 else val}{ '%' if root_key != 'energy_timer' else 's'} {root_key}."
                cost = int(_BASE_COST * _TIER_COST_MULT[tier])
                prereq = prev
            nodes.append(SkillNode(nid, name, branch, cost, prereq, key, val, desc))
            prev = nid
    # Extra nodes.
    for row in _EXTRA_NODES:
        nodes.append(SkillNode(*row))
    return nodes


NODES: list[SkillNode] = _build_tree()
BY_ID: dict[str, SkillNode] = {n.id: n for n in NODES}


# ---------------------------------------------------------------------------
# Epic Research -- a permanent meta-tree bought with medals/amber (Task 18).
# ---------------------------------------------------------------------------
# A SEPARATE set of nodes from the elixir skill tree above. They reuse the
# ``SkillNode`` structure (same dataclass) but are bought with the
# underused currencies medals + amber (NOT elixir), and live in
# ``state.epic_research`` (a separate set from ``state.skill_tree``). The
# ``_epic_research_provider`` in ``core.bonuses`` reads
# ``state.epic_research`` and emits the node effects into the flat bonus
# dict -- the keys are the same effect keys the engine already reads
# (``elixir_pct``, ``away_pct``, ``upgrade_cost_pct``, ...), so the
# contributions stack additively with the elixir skill tree without
# collision.
#
# The three nodes from the brief:
#   * **Elixir Resonance** -- +15% elixir gain (the elixir economy's
#     permanent amplifier; stacks with the elixir skill tree + Godai
#     Void + elixir tokens).
#   * **Away Mastery** -- +25% offline gold (the ``away_pct`` key the
#     offline computation reads). The offline module CAPS the total
#     offline earnings strictly below active+boosted earnings (see
#     ``core.offline``), so Away Mastery keeps offline growth
#     meaningful but never makes idling better than playing actively.
#   * **Lab Discipline** -- +10% upgrade_cost_pct (reduces run-upgrade
#     cost; the same key the turtle pet + the Godai Water element use).
# Costs are in medals (the primary sink); the node values are tuned so
# the meta-tree is a long-term medal sink, not a first-purchase rush.
_EPIC_RESEARCH_ROWS = [
    ("elixir_resonance", "Elixir Resonance", "epic", 50, None,
     "elixir_pct", 0.15, "+15% elixir gain on ascension (permanent)."),
    ("away_mastery", "Away Mastery", "epic", 80, None,
     "away_pct", 0.25, "+25% offline gold (capped below active earnings)."),
    ("lab_discipline", "Lab Discipline", "epic", 60, None,
     "upgrade_cost_pct", 0.10, "-10% run upgrade cost (permanent)."),
]


def _build_epic_research() -> list[SkillNode]:
    return [SkillNode(*row) for row in _EPIC_RESEARCH_ROWS]


EPIC_RESEARCH_NODES: list[SkillNode] = _build_epic_research()
EPIC_RESEARCH_BY_ID: dict[str, SkillNode] = {n.id: n for n in EPIC_RESEARCH_NODES}


def all_nodes() -> list[SkillNode]:
    return list(NODES)


def nodes_by_branch(branch: str) -> list[SkillNode]:
    return [n for n in NODES if n.branch == branch]


def roots() -> list[SkillNode]:
    return [n for n in NODES if n.prereq is None]


def children(parent_id: str) -> list[SkillNode]:
    return [n for n in NODES if n.prereq == parent_id]


def can_unlock(node_id: str, unlocked: set[str], elixir: int) -> bool:
    n = BY_ID.get(node_id)
    if n is None or node_id in unlocked:
        return False
    if n.prereq and n.prereq not in unlocked:
        return False
    return elixir >= n.cost


def branch_color(branch: str):
    from theme import C
    return {
        "offense": (255, 120, 110),
        "economy": (255, 205, 90),
        "elixir": (120, 220, 200),
        "energy": (130, 230, 160),
        "firefly": (255, 240, 120),
        "abilities": (180, 130, 255),
        "godai": (255, 90, 160),
        # Task 22: new branches.
        "defense": (140, 180, 255),
        "combo": (255, 160, 80),
        "tap_mastery": (220, 100, 200),
    }.get(branch, (200, 200, 220))
