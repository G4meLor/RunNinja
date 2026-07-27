"""Building definitions — the idle gold/sec backbone.

18 building types, unlocked progressively by zone.  Each has a base
gold/sec, a base cost, and a geometric cost growth per level.  The
engine sums each building's contribution (level × base_gps × global
multipliers) into the total passive income.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BuildingDef:
    id: str
    name: str
    base_gps: float       # gold per second at level 1
    base_cost: float      # cost of the first level
    cost_growth: float    # multiplicative cost increase per level
    unlock_zone: int      # zone index at which the building becomes available
    icon: str             # procedural icon key
    hue: int
    desc: str


# (id, name, base_gps, base_cost, cost_growth, unlock_zone, icon, hue, desc)
_ROWS = [
    ("farm", "Farm", 1, 15, 1.15, 0, "hut", 90, "A humble rice farm."),
    ("sawmill", "Sawmill", 5, 100, 1.16, 0, "hut", 60, "Wood for the village."),
    ("mine", "Mine", 20, 1.1e3, 1.17, 1, "hut", 30, "Iron from the earth."),
    ("tavern", "Tavern", 80, 12e3, 1.18, 2, "hut", 20, "Sake and stories."),
    ("blacksmith", "Blacksmith", 300, 130e3, 1.18, 3, "hut", 10, "Steel and sparks."),
    ("barracks", "Barracks", 1.0e3, 1.4e6, 1.19, 4, "hut", 0, "House the warriors."),
    ("dojo", "Dojo", 4.0e3, 16e6, 1.19, 5, "torii", 340, "Train the way of the blade."),
    ("shrine", "Shrine", 15e3, 180e6, 1.20, 6, "torii", 300, "Honor the spirits."),
    ("pagoda", "Pagoda", 60e3, 2.0e9, 1.20, 7, "pagoda", 280, "A tower to the sky."),
    ("castle", "Castle", 250e3, 22e9, 1.21, 8, "pagoda", 220, "Seat of the lord."),
    ("forge", "Forge", 1.0e6, 250e9, 1.21, 9, "pagoda", 30, "Forge of legends."),
    ("treasury", "Treasury", 4.0e6, 2.8e12, 1.22, 10, "pagoda", 50, "Gold upon gold."),
    ("observatory", "Observatory", 15e6, 30e12, 1.22, 11, "pagoda", 200, "Read the stars."),
    ("dragon_vein", "Dragon Vein", 60e6, 330e12, 1.23, 12, "pagoda", 0, "The dragon's blood."),
    ("spirit_gate", "Spirit Gate", 250e6, 3.6e15, 1.23, 13, "pagoda", 270, "Gate to the beyond."),
    ("celestial", "Celestial Shrine", 1.0e9, 40e15, 1.24, 14, "pagoda", 50, "Shrine of the heavens."),
    ("void_altar", "Void Altar", 4.0e9, 440e15, 1.24, 15, "pagoda", 280, "Altar of the void."),
    ("infinity", "Infinity Gate", 15e9, 4.8e18, 1.25, 16, "pagoda", 320, "The endless gate."),
]


BUILDINGS: list[BuildingDef] = [BuildingDef(*r) for r in _ROWS]
BY_ID: dict[str, BuildingDef] = {b.id: b for b in BUILDINGS}


def building_cost(b: BuildingDef, current_level: int) -> float:
    """Cost to go from ``current_level`` to the next level."""
    return b.base_cost * (b.cost_growth ** current_level)


def building_gps(b: BuildingDef, level: int) -> float:
    """Gold per second contributed by ``level`` levels of building b."""
    return b.base_gps * level


def buy_max_levels(b: BuildingDef, current_level: int, gold: float) -> int:
    """How many levels ``gold`` can afford for building b (geometric series)."""
    g = b.cost_growth
    c0 = b.base_cost * (g ** current_level)
    if gold < c0:
        return 0
    # Sum of geometric series: c0 * (g^n - 1) / (g - 1) <= gold
    # => n <= log( gold*(g-1)/c0 + 1 ) / log(g)
    import math
    n = math.log(gold * (g - 1) / c0 + 1) / math.log(g)
    return max(0, int(n))


def total_cost(b: BuildingDef, current_level: int, n: int) -> float:
    """Total cost to buy ``n`` levels starting from ``current_level``."""
    g = b.cost_growth
    c0 = b.base_cost * (g ** current_level)
    return c0 * (g ** n - 1) / (g - 1)


def available_buildings(zone_index: int) -> list[BuildingDef]:
    """Buildings unlocked at or before the given zone."""
    return [b for b in BUILDINGS if b.unlock_zone <= zone_index]
