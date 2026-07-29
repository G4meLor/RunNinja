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
    # Godai elemental affinity (Task 21 / gp-godai-fusion). One of
    # "none", "void", "wind", "fire", "water". Default "none" means the
    # type chart is a no-op for this enemy (1x vs any attunement). Themed
    # per zone (see ZONES below). The field is ADDITIVE — a new field on
    # EnemyDef — so it composes with Task 12 (cycle) + Task 31 (weather
    # key on the ZONES dict) without collision.
    element: str = "none"
    # Lore / Bestiary Codex (Task 26 / cnt-quest-codex): a short lore
    # entry per enemy, shown in the bestiary screen. Pure DATA -- no new
    # mechanic, no stat, no state. The lore is a one-line in-fiction
    # description of the enemy's place in the world (the ninja road's
    # bestiary). Default "" so existing callers that don't set it are
    # unaffected; the bestiary screen shows the lore only when non-empty.
    lore: str = ""


ZONES: list[dict] = [
    {
        # Zone 0: the starting village — neutral (no element). The
        # tutorial zone; the type chart is a no-op here so a new player
        # never sees a damage penalty before they unlock the Godai gate.
        # Weather: "none" (the tutorial zone stays clear so a new player
        # is not overwhelmed — the weather unlocks visually from zone 1).
        "id": "village", "name": "Hidden Village", "hue": 90,
        "weather": "none",
        "enemies": [
            EnemyDef("e_bandit", "Bandit", "bandit", 0, 0.8, 0.7, 1.0, 20, 16,
                     lore="A common thug who preys on travellers leaving the village."),
            EnemyDef("e_rat", "Rat", "beast", 30, 0.6, 0.6, 1.1, 30, 13,
                     lore="Disease-carrying vermin that swarm the village grain stores."),
            EnemyDef("e_thief", "Thief", "bandit", 200, 0.7, 0.8, 1.0, 24, 15, rare_drop=0.02,
                     lore="A quick-fingered pickpocket who steals coin purses in the night."),
        ],
    },
    {
        # Zone 1: the bamboo forest — wind-themed (the swaying grove).
        # Weather: rain (the brief's hero zone).
        "id": "bamboo", "name": "Bamboo Forest", "hue": 120,
        "weather": "rain",
        "enemies": [
            EnemyDef("e_ronin", "Ronin", "bandit", 0, 1.0, 1.0, 1.0, 22, 18, element="wind",
                     lore="A masterless samurai who wanders the grove, seeking a new lord."),
            EnemyDef("e_wolf", "Wolf", "beast", 0, 0.9, 1.1, 1.0, 34, 17, rare_drop=0.03, element="wind",
                     lore="A pack hunter that stalks the bamboo paths at dusk."),
            EnemyDef("e_spider", "Spider", "beast", 300, 0.8, 0.9, 1.2, 26, 15, element="wind",
                     lore="A web-spinner that snares the careless in silken traps."),
        ],
    },
    {
        # Zone 2: the cave — wind-themed (the howling echoes). The bat
        # swarm and the cave drafts are wind-flavored.
        # Weather: "none" (the cave is underground; no weather).
        "id": "cave", "name": "Cave of Echoes", "hue": 220,
        "weather": "none",
        "enemies": [
            EnemyDef("e_bat", "Cave Bat", "beast", 280, 0.7, 0.8, 1.3, 30, 14, element="wind",
                     lore="A swarm-dweller that rides the cave drafts and drinks blood."),
            EnemyDef("e_skeleton", "Skeleton", "skeleton", 0, 1.1, 1.0, 1.1, 24, 18, rare_drop=0.04, element="wind",
                     lore="The remains of a fallen warrior, risen by the cave's whispers."),
            EnemyDef("e_golem", "Stone Golem", "golem", 30, 2.0, 1.4, 1.5, 14, 24, element="wind",
                     lore="A guardian of carved stone, slow but unyielding in the dark."),
        ],
    },
    {
        # Zone 3: the yokai marsh — water-themed (the flooded bog).
        # Weather: "none" (the marsh is already wet; no rain).
        "id": "marsh", "name": "Yokai Marsh", "hue": 160,
        "weather": "none",
        "enemies": [
            EnemyDef("e_yokai", "Yokai", "yokai", 270, 1.2, 1.3, 1.4, 26, 18, rare_drop=0.05, element="water",
                     lore="A mischievous spirit that drowns travellers in the bog's fog."),
            EnemyDef("e_lurker", "Lurker", "beast", 160, 1.1, 1.4, 1.3, 22, 20, element="water",
                     lore="A patient predator that waits beneath the marsh's surface."),
            EnemyDef("e_bog", "Bog Spirit", "yokai", 80, 1.6, 1.2, 1.5, 16, 22, element="water",
                     lore="A vengeful spirit of those the marsh has swallowed."),
        ],
    },
    {
        # Zone 4: the sunken ruins — water-themed (the drowned halls).
        # Weather: "none" (the ruins are already drowned; no rain).
        "id": "ruins", "name": "Sunken Ruins", "hue": 40,
        "weather": "none",
        "enemies": [
            EnemyDef("e_guardian", "Guardian", "golem", 200, 2.2, 1.6, 1.6, 14, 26, rare_drop=0.06, element="water",
                     lore="A stone sentinel who guards the drowned halls, even in death."),
            EnemyDef("e_phantom", "Phantom", "wraith", 260, 1.5, 1.7, 1.7, 28, 20, rare_drop=0.06, element="water",
                     lore="A restless shade of a civilisation the sea claimed."),
            EnemyDef("e_warden", "Warden", "skeleton", 20, 1.8, 1.8, 1.8, 20, 22, element="water",
                     lore="The last jailer of a prison now buried beneath the waves."),
        ],
    },
    {
        # Zone 5: the oni volcano — fire-themed (the molten peak).
        # Weather: ash (the brief's hero zone — falling embers).
        "id": "volcano", "name": "Oni Volcano", "hue": 10,
        "weather": "ash",
        "enemies": [
            EnemyDef("e_imp", "Fire Imp", "demon", 0, 1.4, 1.8, 1.8, 30, 16, rare_drop=0.07, element="fire",
                     lore="A mischievous flame-sprite that dances on the molten rock."),
            EnemyDef("e_hound", "Hellhound", "beast", 10, 1.6, 2.0, 1.9, 32, 20, rare_drop=0.07, element="fire",
                     lore="A burning beast that hunts the living on the volcano's slopes."),
            EnemyDef("e_oni", "Oni", "oni", 350, 2.0, 2.2, 2.2, 26, 22, rare_drop=0.08, element="fire",
                     lore="A fiery ogre-demon who feeds on the heat of the mountain."),
        ],
    },
    {
        # Zone 6: the abyss — fire-themed (the burning deep).
        # Weather: "none" (the abyss is underground; no weather).
        "id": "abyss", "name": "The Abyss", "hue": 280,
        "weather": "none",
        "enemies": [
            EnemyDef("e_demon", "Demon", "demon", 350, 2.0, 2.2, 2.2, 26, 22, rare_drop=0.08, element="fire",
                     lore="A denizen of the deep that burns with the abyss's fire."),
            EnemyDef("e_tentacle", "Tentacle", "beast", 290, 2.2, 2.4, 2.3, 20, 24, element="fire",
                     lore="A many-limbed horror that drags prey into the dark."),
            EnemyDef("e_abomination", "Abomination", "yokai", 120, 2.8, 2.6, 2.6, 14, 30, element="fire",
                     lore="A twisted amalgam of the abyss's many victims."),
        ],
    },
    {
        # Zone 7: the sky citadel — wind-themed (the high winds).
        # Weather: snow (the brief's hero zone — the high cold).
        "id": "sky", "name": "Sky Citadel", "hue": 200,
        "weather": "snow",
        "enemies": [
            EnemyDef("e_valkyrie", "Fallen Valkyrie", "wraith", 200, 2.2, 2.4, 2.4, 30, 22, rare_drop=0.09, element="wind",
                     lore="A winged warrior who fell from the citadel and now haunts it."),
            EnemyDef("e_seraph", "Broken Seraph", "golem", 50, 3.0, 2.6, 2.6, 16, 26, rare_drop=0.09, element="wind",
                     lore="A shattered angel of stone, still guarding the high halls."),
            EnemyDef("e_skyguard", "Sky Guard", "skeleton", 190, 2.4, 2.6, 2.5, 22, 22, element="wind",
                     lore="The skeletal remnant of the citadel's once-proud garrison."),
        ],
    },
    {
        # Zone 8: the cosmic void — void-themed (the end of every road).
        # Weather: drift (the brief's hero zone — void motes drifting).
        "id": "void", "name": "Cosmic Void", "hue": 270,
        "weather": "drift",
        "enemies": [
            EnemyDef("e_voidling", "Voidling", "wraith", 280, 2.6, 2.8, 2.8, 28, 22, rare_drop=0.10, element="void",
                     lore="A fragment of the void given form, hungry for the living."),
            EnemyDef("e_stellarbeast", "Stellar Beast", "beast", 220, 2.8, 3.0, 2.9, 24, 24, rare_drop=0.10, element="void",
                     lore="A beast born of starlight and hunger, prowling the void's edge."),
            EnemyDef("e_singularity", "Singularity Spawn", "demon", 310, 3.4, 3.2, 3.2, 18, 28, rare_drop=0.12, element="void",
                     lore="A demon spawned at the collapse of a dying star."),
        ],
    },
]


BOSSES: dict[str, EnemyDef] = {
    # Each boss inherits its zone's element theme (the boss is the zone's
    # capstone — same element as the trash enemies). The village boss is
    # neutral so the first boss fight is a clean 1x for a new player.
    "village":  EnemyDef("b_bandit_king", "Bandit King", "bandit", 0, 6.0, 2.0, 8.0, 12, 36, rare_drop=0.5, desc="The village's tyrant.",
                         lore="The self-styled king of the village bandits, who hoards the stolen gold in a den beneath the well."),
    "bamboo":   EnemyDef("b_wolf_alpha", "Alpha Wolf", "beast", 0, 7.0, 3.0, 9.0, 16, 38, rare_drop=0.5, desc="The pack leader.", element="wind",
                         lore="The alpha of the bamboo wolf-pack, whose howl summons the whole pack to the hunt."),
    "cave":     EnemyDef("b_bone_lord", "Bone Lord", "skeleton", 0, 8.0, 3.5, 10.0, 14, 40, rare_drop=0.6, desc="Ruler of the echo.", element="wind",
                         lore="The master of the cave's skeleton host, who commands the echoes to rise and fight."),
    "marsh":    EnemyDef("b_yokai_king", "Yokai King", "yokai", 260, 9.0, 4.0, 12.0, 18, 40, rare_drop=0.6, desc="The marsh's true face.", element="water",
                         lore="The true face of the marsh, whose mask hides a thousand drowned souls."),
    "ruins":    EnemyDef("b_ancient", "Ancient Guardian", "golem", 200, 12.0, 5.0, 14.0, 10, 46, rare_drop=0.7, desc="Older than the road.", element="water",
                         lore="A guardian older than the road itself, who has outlasted the civilisation it was built to protect."),
    "volcano":  EnemyDef("b_oni_lord", "Oni Lord", "oni", 10, 14.0, 6.0, 16.0, 14, 46, rare_drop=0.7, desc="Heart of the mountain.", element="fire",
                         lore="The heart of the volcano, whose rage fuels the mountain's fire."),
    "abyss":    EnemyDef("b_abyssal", "Abyssal Tyrant", "demon", 330, 16.0, 7.0, 18.0, 16, 48, rare_drop=0.8, desc="The deep has a king.", element="fire",
                         lore="The tyrant of the abyss, whose crown is the bones of those who came before."),
    "sky":      EnemyDef("b_fallen", "Fallen Sovereign", "wraith", 200, 18.0, 8.0, 20.0, 18, 50, rare_drop=0.8, desc="A god who chose the road.", element="wind",
                         lore="A god who chose to walk the road and fell; now the citadel is their tomb."),
    "void":     EnemyDef("b_void_god", "Void God", "dragon", 280, 24.0, 10.0, 24.0, 12, 56, rare_drop=1.0, desc="The end of every road.", element="void",
                         lore="The end of every road, whose hunger is the void itself, and whose voice is the silence between the stars."),
}


# ---------------------------------------------------------------------------
# Boss soft-phase attack pattern library (Task 13)
# ---------------------------------------------------------------------------
# The boss phase is DERIVED from HP each tick (no new state machine, just
# scaling -- see ``engine.enemy._boss_phase_from_hp``). These labels name
# the attack layer the boss gains at each HP milestone:
#   phase 0 (100-75% HP): melee      -- base attack (the boss attacks the
#                                       ninja on its attack_timer at 1.0s)
#   phase 1 (75-50% HP):   projectile -- +faster attacks (interval = 1.0/1.3)
#   phase 2 (50-25% HP):   hazard     -- +faster attacks (interval = 1.0/1.6)
#   phase 3 (25-0% HP):    summon+shield -- +fastest attacks (interval = 1.0/1.9)
#                                      + a shield (flat HP buffer that
#                                      sustained auto-attack DPS breaks
#                                      through; no regeneration)
# These scale the existing attack_timer (faster attacks as HP drops), not a
# new attack-type state machine. The boss never gains a new attack type that
# requires a separate state machine; it just attacks faster and gains a
# damage-absorbing shield at the final phase.
BOSS_PHASE_PATTERNS: dict[int, str] = {
    0: "melee",
    1: "projectile",
    2: "hazard",
    3: "summon_shield",
}

# Shield size at phase 3: a fraction of the boss's max HP. The shield is a
# flat HP buffer that sustained auto-attack DPS breaks through; it does NOT
# regenerate, so once it's depleted the boss takes full damage. Tuned for
# the current auto-attack DPS; **gap #4:** re-test after Task 24
# (gp-tap-auto-rebalance) lands -- the auto vs tap DPS ratio will change.
BOSS_SHIELD_FRACTION = 0.3


# ---------------------------------------------------------------------------
# Shadow Dungeon boss pool (Task 34 / cnt-shadow-dungeon-variants)
# ---------------------------------------------------------------------------
# A pool of fire-themed bosses for the dungeon variants. The dungeon is
# fire-themed (Task 23 — the dungeon's enemies + boss use the Fire Godai
# element), so the boss pool is a set of fire-element EnemyDefs. The pool
# is the source of bosses for the dungeon variants: the Story variant
# picks bosses in a fixed order (a narrative progression), the Endless
# variant cycles the pool with scaling, and the Daily variant uses the
# daily seed to deterministically pick a boss per floor (the same daily
# seed produces the same sequence of bosses — the daily challenge is the
# same for all players on the same day).
#
# The pool lives in data/enemies.py (not engine/runner.py) so the boss
# definitions are owned by the data layer, not the runner — the runner
# picks from the pool; the pool is content data. The existing
# ``DUNGEON_BOSS`` (defined in engine/runner.py for the Task 23
# DungeonRunner) is the first entry in the pool (the original dungeon
# boss, "Shadow Inferno"); the pool adds more fire-themed bosses for
# variety across the variants.
DUNGEON_BOSS_POOL: list[EnemyDef] = [
    # The original dungeon boss (Task 23's DUNGEON_BOSS) — the dungeon's
    # heart of fire. Kept here as the first entry so the Story variant's
    # first floor is the familiar dungeon boss.
    EnemyDef("d_boss", "Shadow Inferno", "demon", 10, 14.0, 6.0, 16.0, 14, 46,
             rare_drop=0.7, desc="The dungeon's heart of fire.",
             element="fire",
             lore="The dungeon's heart of fire, whose rage fuels the shadow deep."),
    # A flame-winged wraith — a fiercer dungeon capstone.
    EnemyDef("d_phoenix", "Ashen Phoenix", "wraith", 20, 16.0, 7.0, 18.0, 16, 48,
             rare_drop=0.8, desc="A phoenix born of the dungeon's ashes.",
             element="fire",
             lore="A phoenix reborn from the dungeon's ashes, whose wings scorch the shadow."),
    # A molten oni warlord — the dungeon's fiercest guardian.
    EnemyDef("d_oni_lord", "Molten Oni Lord", "oni", 30, 18.0, 8.0, 20.0, 16, 50,
             rare_drop=0.9, desc="The warlord of the molten deep.",
             element="fire",
             lore="The warlord of the molten deep, whose crown is the fire of the dungeon's heart."),
    # A void-touched flame dragon — the dungeon's final guardian (the
    # deepest boss, the capstone of the Story variant).
    EnemyDef("d_void_dragon", "Voidfire Dragon", "dragon", 40, 22.0, 9.0, 22.0, 18, 54,
             rare_drop=1.0, desc="A dragon of void and fire.",
             element="fire",
             lore="A dragon of void and fire, the deepest guardian of the shadow dungeon."),
]


def dungeon_boss_for_floor(floor: int, seed: int = 0) -> EnemyDef:
    """Pick a dungeon boss for the given floor.

    The floor is 1-indexed (floor 1 is the first floor). The boss is
    picked from ``DUNGEON_BOSS_POOL``: the Story variant picks in a
    fixed order (floor N -> pool[(N-1) % len(pool)]), the Endless
    variant cycles the pool with scaling, and the Daily variant uses the
    seed to deterministically pick (a seeded shuffle of the pool so the
    same seed produces the same sequence).

    This helper is the single pick point for the dungeon boss pool; the
    runner delegates to it so the boss-pick logic is owned by the data
    layer (the pool) + a single function, not duplicated across the
    variants. The ``seed`` is 0 for Story/Endless (deterministic by
    floor) and the daily seed for Daily (deterministic per day).
    """
    if floor < 1:
        floor = 1
    if seed:
        # Daily variant: a seeded pick so the same daily seed produces
        # the same boss for the same floor (the daily challenge is the
        # same for all players on the same day). We use a simple
        # deterministic hash of (seed, floor) to pick an index — no need
        # for a full RNG; the pick is a single index into the pool.
        idx = (seed + floor * 31) % len(DUNGEON_BOSS_POOL)
    else:
        # Story / Endless: a fixed order by floor (floor N -> pool index
        # N-1, cycling). The Story variant uses the first STORY_FLOORS
        # floors; the Endless variant cycles forever.
        idx = (floor - 1) % len(DUNGEON_BOSS_POOL)
    return DUNGEON_BOSS_POOL[idx]


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
