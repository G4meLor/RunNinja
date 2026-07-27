"""Pet definitions — collectible creatures providing passive buffs.

Up to 3 pets can be equipped at once; their bonuses stack additively
into the aggregate bonus dict the engine reads.  Each pet has a bond
level (0–10) raised by feeding (gold or amber).  Some pets are unlocked
by skill-tree nodes (e.g. Squirrel after Rope Hook, Dragon after 5
ascensions).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PetDef:
    id: str
    name: str
    ptype: str           # aquatic, bird, critter, forest, reptile, beast, mythical
    buff_key: str        # effect key contributed per bond level
    buff_per_level: float
    unlock: str          # "default" or a condition description
    hue: int
    desc: str


# (id, name, type, buff_key, buff_per_level, unlock, hue, desc)
_PETS = [
    ("frog", "Frog", "aquatic", "firefly_gold", 0.05, "default", 120,
     "Loves fireflies. +firefly gold per bond."),
    ("chicken", "Chicken", "bird", "gold_pct", 0.015, "default", 50,
     "Lays golden eggs. +% gold per bond."),
    ("panda", "Panda", "critter", "crit_dmg_pct", 0.03,
     "skill:ab_shuriken", 0, "A calm striker. +% crit dmg per bond."),
    ("otter", "Otter", "aquatic", "speed_pct", 0.025, "default", 190,
     "Quick and sleek. +% speed per bond."),
    ("penguin", "Penguin", "aquatic", "firefly_value", 0.04, "default", 210,
     "Values the lights. +% firefly value per bond."),
    ("squirrel", "Squirrel", "forest", "gps_pct", 0.02,
     "skill:ab_rope", 30, "Builds and gathers. +% building gps per bond."),
    ("turtle", "Turtle", "reptile", "upgrade_cost_pct", 0.02, "default", 90,
     "Slow and steady. -% upgrade cost per bond."),
    ("hedgehog", "Hedgehog", "forest", "building_cost_pct", 0.02, "default", 30,
     "Prickly saver. -% building cost per bond."),
    ("cat", "Cat", "beast", "quest_reward_pct", 0.03, "default", 280,
     "Nine lives, nine rewards. +% quest rewards per bond."),
    ("bunny", "Bunny", "beast", "firefly_spawn", 0.03, "default", 320,
     "Hops after lights. +% firefly spawn per bond."),
    ("raccoon", "Raccoon", "forest", "energy_regen", 0.02, "default", 240,
     "Night forager. +% energy regen per bond."),
    ("dragon", "Dragon", "mythical", "elixir_pct", 0.04,
     "ascensions:5", 0, "Ancient and wise. +% elixir gain per bond."),
]


PETS: list[PetDef] = [PetDef(*r) for r in _PETS]
BY_ID: dict[str, PetDef] = {p.id: p for p in PETS}


def is_unlocked(pet: PetDef, state) -> bool:
    """Whether a pet is available given the player's progress."""
    if pet.unlock == "default":
        return True
    if pet.unlock.startswith("skill:"):
        return pet.unlock.split(":", 1)[1] in state.skill_tree
    if pet.unlock.startswith("ascensions:"):
        n = int(pet.unlock.split(":", 1)[1])
        return state.total_ascensions >= n
    return True


def pet_bonus(pet: PetDef, bond: int) -> float:
    return pet.buff_per_level * bond
