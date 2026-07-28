"""Enemy definitions for the ninja road — re-themed from the generic
monster set into ninja-verse foes (bandits, oni, yokai, etc.).

Each enemy has a visual kit (shape + hue) and stat multipliers that the
engine scales by the zone level.  Bosses are defined per zone.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EnemyDef:
    id: str
    name: str
    shape: str              # bandit, oni, yokai, skeleton, beast, wraith, golem, demon, dragon
    hue: int
    hp_mult: float
    dmg_mult: float
    gold_mult: float
    speed: float
    size: int
    rare_drop: float = 0.0
    desc: str = ""


ZONES: list[dict] = [
    {
        "id": "village", "name": "Hidden Village", "hue": 90,
        "enemies": [
            EnemyDef("e_bandit", "Bandit", "bandit", 0, 0.8, 0.7, 1.0, 20, 16),
            EnemyDef("e_rat", "Rat", "beast", 30, 0.6, 0.6, 1.1, 30, 13),
            EnemyDef("e_thief", "Thief", "bandit", 200, 0.7, 0.8, 1.0, 24, 15, rare_drop=0.02),
        ],
    },
    {
        "id": "bamboo", "name": "Bamboo Forest", "hue": 120,
        "enemies": [
            EnemyDef("e_ronin", "Ronin", "bandit", 0, 1.0, 1.0, 1.0, 22, 18),
            EnemyDef("e_wolf", "Wolf", "beast", 0, 0.9, 1.1, 1.0, 34, 17, rare_drop=0.03),
            EnemyDef("e_spider", "Spider", "beast", 300, 0.8, 0.9, 1.2, 26, 15),
        ],
    },
    {
        "id": "cave", "name": "Cave of Echoes", "hue": 220,
        "enemies": [
            EnemyDef("e_bat", "Cave Bat", "beast", 280, 0.7, 0.8, 1.3, 30, 14),
            EnemyDef("e_skeleton", "Skeleton", "skeleton", 0, 1.1, 1.0, 1.1, 24, 18, rare_drop=0.04),
            EnemyDef("e_golem", "Stone Golem", "golem", 30, 2.0, 1.4, 1.5, 14, 24),
        ],
    },
    {
        "id": "marsh", "name": "Yokai Marsh", "hue": 160,
        "enemies": [
            EnemyDef("e_yokai", "Yokai", "yokai", 270, 1.2, 1.3, 1.4, 26, 18, rare_drop=0.05),
            EnemyDef("e_lurker", "Lurker", "beast", 160, 1.1, 1.4, 1.3, 22, 20),
            EnemyDef("e_bog", "Bog Spirit", "yokai", 80, 1.6, 1.2, 1.5, 16, 22),
        ],
    },
    {
        "id": "ruins", "name": "Sunken Ruins", "hue": 40,
        "enemies": [
            EnemyDef("e_guardian", "Guardian", "golem", 200, 2.2, 1.6, 1.6, 14, 26, rare_drop=0.06),
            EnemyDef("e_phantom", "Phantom", "wraith", 260, 1.5, 1.7, 1.7, 28, 20, rare_drop=0.06),
            EnemyDef("e_warden", "Warden", "skeleton", 20, 1.8, 1.8, 1.8, 20, 22),
        ],
    },
    {
        "id": "volcano", "name": "Oni Volcano", "hue": 10,
        "enemies": [
            EnemyDef("e_imp", "Fire Imp", "demon", 0, 1.4, 1.8, 1.8, 30, 16, rare_drop=0.07),
            EnemyDef("e_hound", "Hellhound", "beast", 10, 1.6, 2.0, 1.9, 32, 20, rare_drop=0.07),
            EnemyDef("e_oni", "Oni", "oni", 350, 2.0, 2.2, 2.2, 26, 22, rare_drop=0.08),
        ],
    },
    {
        "id": "abyss", "name": "The Abyss", "hue": 280,
        "enemies": [
            EnemyDef("e_demon", "Demon", "demon", 350, 2.0, 2.2, 2.2, 26, 22, rare_drop=0.08),
            EnemyDef("e_tentacle", "Tentacle", "beast", 290, 2.2, 2.4, 2.3, 20, 24),
            EnemyDef("e_abomination", "Abomination", "yokai", 120, 2.8, 2.6, 2.6, 14, 30),
        ],
    },
    {
        "id": "sky", "name": "Sky Citadel", "hue": 200,
        "enemies": [
            EnemyDef("e_valkyrie", "Fallen Valkyrie", "wraith", 200, 2.2, 2.4, 2.4, 30, 22, rare_drop=0.09),
            EnemyDef("e_seraph", "Broken Seraph", "golem", 50, 3.0, 2.6, 2.6, 16, 26, rare_drop=0.09),
            EnemyDef("e_skyguard", "Sky Guard", "skeleton", 190, 2.4, 2.6, 2.5, 22, 22),
        ],
    },
    {
        "id": "void", "name": "Cosmic Void", "hue": 270,
        "enemies": [
            EnemyDef("e_voidling", "Voidling", "wraith", 280, 2.6, 2.8, 2.8, 28, 22, rare_drop=0.10),
            EnemyDef("e_stellarbeast", "Stellar Beast", "beast", 220, 2.8, 3.0, 2.9, 24, 24, rare_drop=0.10),
            EnemyDef("e_singularity", "Singularity Spawn", "demon", 310, 3.4, 3.2, 3.2, 18, 28, rare_drop=0.12),
        ],
    },
]


BOSSES: dict[str, EnemyDef] = {
    "village":  EnemyDef("b_bandit_king", "Bandit King", "bandit", 0, 6.0, 2.0, 8.0, 12, 36, rare_drop=0.5, desc="The village's tyrant."),
    "bamboo":   EnemyDef("b_wolf_alpha", "Alpha Wolf", "beast", 0, 7.0, 3.0, 9.0, 16, 38, rare_drop=0.5, desc="The pack leader."),
    "cave":     EnemyDef("b_bone_lord", "Bone Lord", "skeleton", 0, 8.0, 3.5, 10.0, 14, 40, rare_drop=0.6, desc="Ruler of the echo."),
    "marsh":    EnemyDef("b_yokai_king", "Yokai King", "yokai", 260, 9.0, 4.0, 12.0, 18, 40, rare_drop=0.6, desc="The marsh's true face."),
    "ruins":    EnemyDef("b_ancient", "Ancient Guardian", "golem", 200, 12.0, 5.0, 14.0, 10, 46, rare_drop=0.7, desc="Older than the road."),
    "volcano":  EnemyDef("b_oni_lord", "Oni Lord", "oni", 10, 14.0, 6.0, 16.0, 14, 46, rare_drop=0.7, desc="Heart of the mountain."),
    "abyss":    EnemyDef("b_abyssal", "Abyssal Tyrant", "demon", 330, 16.0, 7.0, 18.0, 16, 48, rare_drop=0.8, desc="The deep has a king."),
    "sky":      EnemyDef("b_fallen", "Fallen Sovereign", "wraith", 200, 18.0, 8.0, 20.0, 18, 50, rare_drop=0.8, desc="A god who chose the road."),
    "void":     EnemyDef("b_void_god", "Void God", "dragon", 280, 24.0, 10.0, 24.0, 12, 56, rare_drop=1.0, desc="The end of every road."),
}


def zone_by_id(zone_id: str) -> dict:
    """Look up a zone by its string id. Raises KeyError if unknown."""
    for z in ZONES:
        if z["id"] == zone_id:
            return z
    raise KeyError(f"unknown zone id: {zone_id}")


def zone_by_index(i: int) -> dict:
    """Look up a zone by its 0-based index.

    Negative indices raise ValueError. Indices past the last zone wrap
    modulo 9 (the infinite-zone-cycling mechanism): the 9 themed zones
    repeat forever at scaled stats (see ``World.cycle`` and the
    ``CYCLE_*_MULT`` config). The caller never sees an out-of-range
    zone because the road cycles.
    """
    if i < 0:
        raise ValueError(f"negative zone index: {i}")
    return ZONES[i % len(ZONES)]


def boss_for_zone(zone_id: str) -> EnemyDef:
    return BOSSES[zone_id]
