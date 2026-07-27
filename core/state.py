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

    # ---- Quests ----
    achievements: set[str] = field(default_factory=set)
    daily_quests: list[dict] = field(default_factory=list)   # [{id, target, progress}]
    daily_refresh: float = 0.0     # epoch when daily quests refresh

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
    save_version: int = 2
    last_saved: float = 0.0

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
        d["skill_tree"] = sorted(self.skill_tree)
        d["achievements"] = sorted(self.achievements)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GameState":
        s = cls()
        for k, v in d.items():
            if k in ("skill_tree",):
                s.skill_tree = set(v)
            elif k in ("achievements",):
                s.achievements = set(v)
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
                state = cls.from_dict(json.load(f))
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
