"""Persistent game state — Tap Ninja schema, save/load to JSON.

Single source of truth for the player's progress across the four
currencies (gold, elixir, amber, medals), buildings, run upgrades, the
elixir skill tree, pets, quests, ascension, energy, combo, and the
road.  The schema is flat and additive so older saves load under newer
code.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any


SAVE_DIR = os.path.join(os.path.expanduser("~"), ".tap_ninja")
SAVE_FILE = os.path.join(SAVE_DIR, "save.json")


@dataclass
class GameState:
    # ---- Currencies ----
    gold: float = 0.0
    elixir: int = 0
    amber: int = 0
    medals: int = 0

    # ---- Buildings: id -> level ----
    buildings: dict[str, int] = field(default_factory=dict)

    # ---- Run upgrades (reset on ascension): key -> level ----
    upgrades: dict[str, int] = field(default_factory=dict)

    # ---- Elixir skill tree: set of unlocked node ids ----
    skill_tree: set[str] = field(default_factory=set)

    # ---- Pets: id -> bond level (0..10); equipped list (up to 3) ----
    pets: dict[str, int] = field(default_factory=dict)
    equipped_pets: list[str] = field(default_factory=list)
    pet_pulls: int = 0
    pet_pity: dict[str, int] = field(default_factory=dict)  # rarity -> pulls since last drop (gp-gacha-fairness)

    # ---- Quests ----
    achievements: set[str] = field(default_factory=set)
    daily_quests: list[dict] = field(default_factory=list)   # [{id, target, progress}]
    daily_refresh: float = 0.0     # epoch when daily quests refresh
    # Weekly quests (Task 26 / cnt-quest-codex): same shape as
    # daily_quests (``[{id, target, progress, baseline}]``) but refreshed
    # every 7d. The ``baseline`` is the cumulative-counter value at
    # refresh time so the quest tracks this week's progress, not the
    # lifetime total. ``weekly_refresh`` is the epoch for the next refresh.
    weekly_quests: list[dict] = field(default_factory=list)
    weekly_refresh: float = 0.0
    # Chapter quests (Task 26 / cnt-quest-codex): one-time milestones tied
    # to zone progression. Same shape as daily_quests (``[{id, target,
    # progress, claimed}]``) but no refresh -- once claimed, they stay
    # claimed. Initialized lazily on first ``update_chapter_progress`` call
    # (so a new player starts with the full chapter list, not an empty one).
    chapter_quests: list[dict] = field(default_factory=list)

    # ---- Ascension ----
    ascend_tier: int = 0
    total_ascensions: int = 0

    # ---- Energy / Auto Katana ----
    energy: float = 0.0          # current energy (seconds of auto-katana left)
    energy_max: float = 600.0    # max energy (seconds)
    energy_active: bool = False  # is auto-katana running
    energy_lockout: float = 0.0  # brief lockout after disabling

    # ---- Combo ----
    combo: int = 0
    combo_timer: float = 0.0     # seconds until combo decays
    best_combo_ever: int = 0

    # ---- World ----
    zone_index: int = 0
    zone_distance: float = 0.0
    total_distance: float = 0.0
    best_zone: int = 0
    monsters_killed: int = 0
    bosses_killed: int = 0
    lifetime_gold: float = 0.0     # total gold ever earned (for elixir calc)

    # ---- Daily counters (reset on daily refresh) ----
    gold_earned_today: float = 0.0
    best_combo_today: int = 0
    skills_used_today: int = 0
    ascensions_today: int = 0
    fireflies_today: int = 0
    kills_today: int = 0

    # ---- Settings ----
    sound_on: bool = True
    reduced_motion: bool = False

    # ---- Meta ----
    playtime: float = 0.0
    save_version: int = 3
    last_saved: float = 0.0

    # ---- v3 fields (big bang enhance) ----
    # Seeded by the v2 -> v3 migration (see _migrate_v2_to_v3). Each later
    # task adds its logic on top of these defaults; the migration ensures a
    # v2 save loaded under v3+ code has every field the dataclass expects.
    render_quality: str = "med"          # high, med, low (gfx-render-tier)
    attuned_element: str = "none"        # none, void, wind, fire, water (gp-godai-fusion)
    dojo: str = "none"                   # none, kage_bunshin, iaijutsu, shikigami, kusari_gama (gp-build-spec)
    heritage: set[str] = field(default_factory=set)  # collected heritage dojos (gp-build-spec)
    rhythm_streak: int = 0               # tap-rhythm bonus, cap 20 (gp-skill-synergy-rhythm)
    combo_charges: int = 0              # banked combo-finisher charges (gp-combo-finishers)
    tokens: dict[str, int] = field(default_factory=dict)  # strike/crit/coin/elixir -> count (gp-permanent-scaling)
    gear: dict[str, dict] = field(default_factory=dict)   # slot -> {affix, value, rarity} (cnt-gear-loot)
    souls: int = 0                      # reincarnation currency (gp-reincarnation)
    soul_tree: set[str] = field(default_factory=set)     # permanent soul-tree perks (gp-reincarnation)
    epic_research: set[str] = field(default_factory=set)  # permanent meta-tree nodes (gp-epic-research)
    pet_stars: dict[str, int] = field(default_factory=dict)  # pid -> star level 1-12 (cnt-pet-depth)
    spirit_embers: int = 0             # nested pet-prestige currency (cnt-pet-depth)
    pet_prestiges: dict[str, int] = field(default_factory=dict)  # pid -> prestige count (cnt-pet-depth)
    pity_tokens: int = 0               # gacha spark-shop currency (gp-gacha-fairness)
    banner_pulls: int = 0              # pulls on the current banner (gp-gacha-fairness)
    dungeon_active: bool = False       # is a shadow dungeon running (cnt-shadow-dungeon)
    dungeon_type: str = "none"         # story, endless, daily (cnt-shadow-dungeon)
    dungeon_floor: int = 0            # current dungeon floor (cnt-shadow-dungeon)
    dungeon_seed: int = 0             # daily dungeon seed (cnt-shadow-dungeon)
    # Task 34 (cnt-shadow-dungeon-variants): the best floor reached across
    # all dungeon runs (a record-keeping field). Updated by the
    # DungeonRunner when a floor is cleared. The variant (story/endless/
    # daily) is in ``dungeon_type``; this is the depth record.
    dungeon_best_floor: int = 0       # best dungeon floor reached (cnt-shadow-dungeon-variants)
    music_on: bool = False            # separate from SFX (pl-music-sfx)
    volume: float = 0.5              # master volume slider (pl-music-sfx)
    text_scale: float = 1.0          # 0.8x-1.6x font scale (pl-accessibility)
    dyslexia_font: bool = False      # dyslexia-friendly font toggle (pl-accessibility)
    high_contrast: bool = False     # high-contrast palette toggle (pl-accessibility)
    seen_hints: list[str] = field(default_factory=list)  # dismissed hint ids (pl-hints-nav-tooltips)
    cosmic_forge: int = 0           # persistent reincarnation anchor, max 10 (gp-reincarnation-perks)
    auto_ascend_threshold: int = 0  # zone index at which auto-ascend fires (0 = use base requirement) (pl-automation)

    # -----------------------------------------------------------------
    # Render-quality tier
    # -----------------------------------------------------------------
    def effective_render_quality(self) -> str:
        """The effective render tier — ``low`` if reduced_motion is on.

        This is the single read-point for the render tier: every FX
        feature that respects the tier calls this and passes the result
        to the ``core.quality`` helpers (``particle_mult``,
        ``glow_enabled``, ``parallax_enabled``). ``reduced_motion``
        forces ``"low"`` so the accessibility gate and the tier never
        diverge — toggling reduced_motion on is equivalent to (and a
        superset of) selecting the low tier.
        """
        if self.reduced_motion:
            return "low"
        return self.render_quality

    # -----------------------------------------------------------------
    # Building helpers
    # -----------------------------------------------------------------
    def building_level(self, bid: str) -> int:
        return self.buildings.get(bid, 0)

    def add_building_levels(self, bid: str, n: int) -> None:
        self.buildings[bid] = self.building_level(bid) + n

    # -----------------------------------------------------------------
    # Upgrade helpers
    # -----------------------------------------------------------------
    def upgrade_level(self, key: str) -> int:
        return self.upgrades.get(key, 0)

    # -----------------------------------------------------------------
    # Pet helpers
    # -----------------------------------------------------------------
    def pet_bond(self, pid: str) -> int:
        return self.pets.get(pid, 0)

    def equip_pet(self, pid: str) -> bool:
        if pid not in self.pets:
            return False
        if pid in self.equipped_pets:
            return True
        if len(self.equipped_pets) >= 3:
            self.equipped_pets.append(pid)
            self.equipped_pets.pop(0)
        else:
            self.equipped_pets.append(pid)
        return True

    def unequip_pet(self, pid: str) -> None:
        if pid in self.equipped_pets:
            self.equipped_pets.remove(pid)

    # -----------------------------------------------------------------
    # Save / load
    # -----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Sets are stored as sorted lists on disk (stable JSON + diffable).
        d["skill_tree"] = sorted(self.skill_tree)
        d["achievements"] = sorted(self.achievements)
        d["heritage"] = sorted(self.heritage)
        d["soul_tree"] = sorted(self.soul_tree)
        d["epic_research"] = sorted(self.epic_research)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GameState":
        s = cls()
        for k, v in d.items():
            if k in ("skill_tree", "achievements", "heritage", "soul_tree", "epic_research"):
                setattr(s, k, set(v))
            elif hasattr(s, k):
                setattr(s, k, v)
        return s

    def save(self, path: str = SAVE_FILE) -> None:
        self.last_saved = time.time()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str = SAVE_FILE) -> "GameState":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            d = _migrate(d)
            state = cls.from_dict(d)
            if state.last_saved <= 0:
                state.last_saved = time.time()
            return state
        except (json.JSONDecodeError, OSError, ValueError):
            backup = path + ".bak"
            try:
                os.replace(path, backup)
            except OSError:
                pass
            return cls()


# ---------------------------------------------------------------------------
# Save-version migration chain
# ---------------------------------------------------------------------------
# ``save_version`` was decorative: ``from_dict`` used ``hasattr+setattr``
# with no migration logic, so the "forward-compatible additive schema" claim
# was a time bomb (the first field rename or type change would silently
# destroy player progress). The chain below walks from the file's
# ``save_version`` up to ``CURRENT_SAVE_VERSION``, applying each migration
# in order. Each migration is a PURE function (takes a dict, returns a new
# dict) so the live save on disk is never mutated during migration: the
# migrated dict is constructed in memory, ``from_dict`` builds the state,
# and the next ``save()`` writes the new version atomically.

CURRENT_SAVE_VERSION = 3


def _migrate_v2_to_v3(d: dict) -> dict:
    """v2 -> v3: seed new-field defaults for the big bang enhance.

    Every field a later task adds to ``GameState`` is seeded here with the
    same default the dataclass uses, so a v2 save loaded under v3+ code
    has every field the dataclass expects (no KeyError, no AttributeError).
    ``setdefault`` preserves any field already present (forward-compatible:
    a v3 save re-loaded is a no-op for these fields).
    """
    d = dict(d)  # pure: don't mutate the input
    # gfx-render-tier
    d.setdefault("render_quality", "med")
    # gp-godai-fusion
    d.setdefault("attuned_element", "none")
    # gp-build-spec
    d.setdefault("dojo", "none")
    d.setdefault("heritage", [])
    # gp-skill-synergy-rhythm
    d.setdefault("rhythm_streak", 0)
    # gp-combo-finishers
    d.setdefault("combo_charges", 0)
    # gp-permanent-scaling
    d.setdefault("tokens", {})
    # cnt-gear-loot
    d.setdefault("gear", {})
    # gp-reincarnation
    d.setdefault("souls", 0)
    d.setdefault("soul_tree", [])
    # gp-epic-research
    d.setdefault("epic_research", [])
    # cnt-pet-depth
    d.setdefault("pet_stars", {})
    d.setdefault("spirit_embers", 0)
    d.setdefault("pet_prestiges", {})
    # gp-gacha-fairness
    d.setdefault("pity_tokens", 0)
    d.setdefault("banner_pulls", 0)
    d.setdefault("pet_pity", {})
    # cnt-shadow-dungeon
    d.setdefault("dungeon_active", False)
    d.setdefault("dungeon_type", "none")
    d.setdefault("dungeon_floor", 0)
    d.setdefault("dungeon_seed", 0)
    # cnt-shadow-dungeon-variants (Task 34): the best dungeon floor
    # reached. Seeded with the same default the dataclass uses so a v2
    # save loaded under v3+ code has the field the dungeon-variant logic
    # expects.
    d.setdefault("dungeon_best_floor", 0)
    # pl-music-sfx
    d.setdefault("music_on", False)
    d.setdefault("volume", 0.5)
    # pl-accessibility
    d.setdefault("text_scale", 1.0)
    d.setdefault("dyslexia_font", False)
    d.setdefault("high_contrast", False)
    # pl-hints-nav-tooltips
    d.setdefault("seen_hints", [])
    # gp-reincarnation-perks
    d.setdefault("cosmic_forge", 0)
    # pl-automation (Task 28): the auto-ascend threshold (the zone index
    # at which auto-ascend fires; 0 = use the base ascend requirement).
    d.setdefault("auto_ascend_threshold", 0)
    # cnt-quest-codex (Task 26): weekly + chapter quest state. Seeded
    # with the same defaults the dataclass uses so a v2 save loaded under
    # v3+ code has the fields the weekly/chapter logic expects.
    d.setdefault("weekly_quests", [])
    d.setdefault("weekly_refresh", 0.0)
    d.setdefault("chapter_quests", [])
    d["save_version"] = 3
    return d


MIGRATIONS = {
    2: _migrate_v2_to_v3,
}


def _migrate(d: dict) -> dict:
    """Walk the migration chain from the dict's ``save_version`` up to
    ``CURRENT_SAVE_VERSION``.

    Each migration is a pure function ``(d) -> d`` that bumps
    ``save_version`` by one; the chain stops when the dict's version is no
    longer in ``MIGRATIONS`` (i.e. it has reached ``CURRENT_SAVE_VERSION``).
    A dict with no ``save_version`` is treated as v1 (the pre-versioning
    era) and migrated from v2 onward; a dict already at or above
    ``CURRENT_SAVE_VERSION`` is returned unchanged.
    """
    v = d.get("save_version", 1)
    while v in MIGRATIONS:
        d = MIGRATIONS[v](d)
        v = d.get("save_version", v + 1)
    return d
