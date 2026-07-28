"""Pet definitions — collectible creatures providing passive buffs.

Up to 3 pets can be equipped at once; their bonuses stack additively
into the aggregate bonus dict the engine reads.  Each pet has a bond
level (0–10) raised by feeding (gold or amber).  Some pets are unlocked
by skill-tree nodes (e.g. Squirrel after Rope Hook, Dragon after 5
ascensions).

**Pet depth (Task 14):** the 12-pet collection has two second-axis
progression systems on top of bond:

  * **Star levels (1-12)** from duplicate eggs. Each duplicate pull
    (after the pet is already owned) increments ``pet_stars[pid]``
    (capped at 12). Each star adds a small multiplier on top of the
    bond-based bonus — so a maxed pet (bond 10 + 12 stars) still has
    something to chase.

  * **Spirit Embers** from nested pet prestige. A pet at max bond (10)
    can be prestiged: the bond resets to 0, the cap stays at 10, and
    Spirit Embers are paid out (scaling with the prestige count). The
    Ember currency is nested in the existing pet-progression layer —
    it's the re-grind reward, not a separate economy. Each prestige
    applies a permanent multiplier on the pet's bonus so the
    post-prestige bonus (once bond is rebuilt to 10) outpaces the
    pre-prestige bonus at bond 10 — the re-grind is clearly worth it.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Pet depth tunables
# ---------------------------------------------------------------------------
PET_STAR_MAX = 12            # star levels cap (1-12 from duplicate eggs)
PET_STAR_BONUS_PER = 0.01    # +1% of bond-based bonus per star level
PET_PRESTIGE_BONUS_PER = 0.10  # +10% of bond-based bonus per prestige count
# Spirit Ember payout per prestige: base + (prestige_count * step).
# The first prestige pays 50, the second 100, the third 150 — each
# re-grind is clearly worth more than the last.
PET_PRESTIGE_PAYOUT_BASE = 50
PET_PRESTIGE_PAYOUT_STEP = 50


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


def pet_bonus(pet: PetDef, bond: int, stars: int = 0, prestiges: int = 0) -> float:
    """The bonus a pet contributes at ``bond`` with optional depth axes.

    The base is ``buff_per_level * bond`` (unchanged). Two second-axis
    multipliers fold on top:

      * **Stars** (1-12 from duplicate eggs): ``+PET_STAR_BONUS_PER``
        of the base per star, so 12 stars = +12% of the bond-based
        bonus.
      * **Prestiges** (from Spirit Embers): ``+PET_PRESTIGE_BONUS_PER``
        of the base per prestige, so the post-prestige bonus (once
        bond is rebuilt to 10) outpaces the pre-prestige bonus at
        bond 10 — the re-grind is clearly worth it.

    Both multipliers are additive on the base, so the call site can
    pass ``stars`` and ``prestiges`` (or omit them) and get the right
    number without changing the contract for callers that still pass
    just ``(pet, bond)``.
    """
    base = pet.buff_per_level * bond
    if stars <= 0 and prestiges <= 0:
        return base
    star_mult = PET_STAR_BONUS_PER * max(0, min(PET_STAR_MAX, stars))
    prest_mult = PET_PRESTIGE_BONUS_PER * max(0, prestiges)
    return base * (1.0 + star_mult + prest_mult)
