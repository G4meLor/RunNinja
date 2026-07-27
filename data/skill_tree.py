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
            "firefly", "abilities", "godai")


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
    }.get(branch, (200, 200, 220))
