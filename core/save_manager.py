"""Save export / backup / integrity for Tap Ninja.

A small, stdlib-only companion to ``core.state``.  ``GameState`` knows
how to serialize itself to one fixed ``SAVE_FILE``; this module adds the
surrounding workflow a real player wants around that single file:

* **Export** the current save to a timestamped file in a chosen folder
  (so a run can be archived or shared without touching the live save).
* **Import** a save file: read it, validate it, and replace the live
  ``SAVE_FILE`` with its contents.
* **Backup** the live save to a rotating set of ``.bak.1`` / ``.bak.2``
  / ``.bak.3`` files (keep the last three).
* **Validate** a save dict's required fields and their types, so a
  corrupt or hand-edited file is rejected before it overwrites progress.
* **Cloud-ish sync** — a one-line copy of ``SAVE_FILE`` to a second
  location (a synced folder, a USB stick, etc.).  No network, just
  ``shutil``.

Only the standard library is used (``json``, ``os``, ``shutil``,
``time``, ``dataclasses``).  Nothing here imports pygame, so it is safe
to call from headless scripts too.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.state import GameState, SAVE_FILE, _migrate


# ---------------------------------------------------------------------------
# Schema for validate_save
# ---------------------------------------------------------------------------
# Every field the live GameState serializes, mapped to its expected JSON
# type.  ``skill_tree`` and ``achievements`` are stored as *lists* on disk
# (GameState.to_dict sorts them), so they are listed as ``list`` here.
# A subset of these are REQUIRED for a file to count as a Tap Ninja save;
# the rest are type-checked only if present (forward-compatible: a future
# save that adds a field won't fail import).
_SCHEMA: dict[str, type] = {
    # Currencies
    "gold": float,
    "elixir": int,
    "amber": int,
    "medals": int,
    # Buildings / upgrades / skill tree
    "buildings": dict,
    "upgrades": dict,
    "skill_tree": list,
    # Pets
    "pets": dict,
    "equipped_pets": list,
    "pet_pulls": int,
    "pet_pity": dict,
    # Quests
    "achievements": list,
    "daily_quests": list,
    "daily_refresh": float,
    # Ascension
    "ascend_tier": int,
    "total_ascensions": int,
    # Energy
    "energy": float,
    "energy_max": float,
    "energy_active": bool,
    "energy_lockout": float,
    # Combo
    "combo": int,
    "combo_timer": float,
    "best_combo_ever": int,
    # World
    "zone_index": int,
    "zone_distance": float,
    "total_distance": float,
    "best_zone": int,
    "monsters_killed": int,
    "bosses_killed": int,
    "lifetime_gold": float,
    # Daily counters
    "gold_earned_today": float,
    "best_combo_today": int,
    "skills_used_today": int,
    "ascensions_today": int,
    "fireflies_today": int,
    "kills_today": int,
    # Settings
    "sound_on": bool,
    "reduced_motion": bool,
    # v3 settings (big bang enhance) — type-checked only if present; the
    # v2 -> v3 migration seeds them, but an imported file may pre-date the
    # migration and omit them. Forward-compatible: missing fields are not
    # errors (only the _REQUIRED set is hard-required).
    "render_quality": str,
    "music_on": bool,
    "volume": float,
    "text_scale": float,
    "dyslexia_font": bool,
    "high_contrast": bool,
    "seen_hints": list,
    "attuned_element": str,
    "dojo": str,
    "heritage": list,
    "rhythm_streak": int,
    "combo_charges": int,
    "tokens": dict,
    "gear": dict,
    "souls": int,
    "soul_tree": list,
    "epic_research": list,
    "pet_stars": dict,
    "spirit_embers": int,
    "pet_prestiges": dict,
    "pity_tokens": int,
    "banner_pulls": int,
    "dungeon_active": bool,
    "dungeon_type": str,
    "dungeon_floor": int,
    "dungeon_seed": int,
    "cosmic_forge": int,
    # cnt-quest-codex (Task 26): weekly + chapter quest state.
    "weekly_quests": list,
    "weekly_refresh": float,
    "chapter_quests": list,
    # Meta
    "playtime": float,
    "save_version": int,
    "last_saved": float,
}

# Fields that MUST be present for a file to be accepted as a Tap Ninja
# save.  Missing any of these is a hard error; missing an optional field
# is not (GameState.from_dict fills in defaults).
_REQUIRED: tuple[str, ...] = (
    "save_version",
    "gold",
    "elixir",
    "amber",
    "medals",
    "zone_index",
    "ascend_tier",
    "playtime",
    "last_saved",
)


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Outcome of ``validate_save``.

    ``valid`` is True only when ``errors`` is empty.  ``warnings`` notes
    non-fatal oddities (e.g. a negative currency) so the UI can show a
    "this looks off, import anyway?" prompt without rejecting the file.
    """
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# ---------------------------------------------------------------------------
# Save summary (for UI display)
# ---------------------------------------------------------------------------
@dataclass
class SaveSummary:
    """A compact, display-ready snapshot of a save file.

    Built from a file on disk (``SaveSummary.from_path``) so the
    settings screen can list exports / backups with one line each
    without loading a full GameState.
    """
    path: str
    mtime: float
    size: int
    save_version: int
    gold: float
    elixir: int
    amber: int
    medals: int
    ascend_tier: int
    zone_index: int
    playtime: float
    last_saved: float

    @classmethod
    def from_path(cls, path: str) -> Optional["SaveSummary"]:
        """Read ``path`` and return a SaveSummary, or None if it is
        missing or unreadable (so a UI listing never crashes on a
        corrupt/deleted file)."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            st = os.stat(path)
        except (OSError, json.JSONDecodeError):
            return None
        return cls(
            path=path,
            mtime=st.st_mtime,
            size=st.st_size,
            save_version=int(d.get("save_version", 0)),
            gold=float(d.get("gold", 0.0)),
            elixir=int(d.get("elixir", 0)),
            amber=int(d.get("amber", 0)),
            medals=int(d.get("medals", 0)),
            ascend_tier=int(d.get("ascend_tier", 0)),
            zone_index=int(d.get("zone_index", 0)),
            playtime=float(d.get("playtime", 0.0)),
            last_saved=float(d.get("last_saved", 0.0)),
        )

    def format_when(self) -> str:
        """Human-readable mtime (e.g. '2026-07-26 14:03')."""
        if self.mtime <= 0:
            return "unknown"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))

    def describe(self) -> str:
        """One-line description suitable for a UI list row."""
        return (f"v{self.save_version}  gold {self.gold:.0f}  "
                f"elixir {self.elixir}  tier {self.ascend_tier}  "
                f"zone {self.zone_index}  {self.format_when()}")


# ---------------------------------------------------------------------------
# Type checking helper
# ---------------------------------------------------------------------------
def _type_ok(value: Any, expected: type) -> bool:
    """True if ``value`` matches ``expected`` type, with the usual
    Python gotchas handled: ``bool`` is not accepted as ``int``, and an
    ``int`` is accepted where a ``float`` is expected (JSON drops the
    distinction, and GameState's float fields routinely hold ints)."""
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, expected)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def validate_save(d: Any) -> ValidationResult:
    """Check that ``d`` is a dict with the required Tap Ninja save fields
    and that every known field has the right type.

    Returns a ``ValidationResult``.  A file with missing required fields
    or wrong-typed fields is invalid; a file with extra unknown fields
    is fine (forward-compatible), and negative currencies etc. are
    warnings, not errors.
    """
    res = ValidationResult()
    if not isinstance(d, dict):
        res.errors.append("save is not a JSON object")
        res.valid = False
        return res

    for name in _REQUIRED:
        if name not in d:
            res.errors.append(f"missing required field: {name}")
        elif not _type_ok(d[name], _SCHEMA[name]):
            res.errors.append(
                f"field {name!r} has wrong type: "
                f"expected {_SCHEMA[name].__name__}, got {type(d[name]).__name__}"
            )
    if res.errors:
        res.valid = False
        return res

    # Type-check the remaining (non-required) known fields if present.
    for name, expected in _SCHEMA.items():
        if name in d and not _type_ok(d[name], expected):
            res.errors.append(
                f"field {name!r} has wrong type: "
                f"expected {expected.__name__}, got {type(d[name]).__name__}"
            )

    # Soft warnings: currencies / progress should not be negative.
    for name in ("gold", "elixir", "amber", "medals", "lifetime_gold",
                 "playtime", "monsters_killed"):
        if name in d and isinstance(d[name], (int, float)) and d[name] < 0:
            res.warnings.append(f"field {name!r} is negative ({d[name]})")

    res.valid = not res.errors
    return res


def export_save(state: GameState, dest_dir: str) -> str:
    """Write ``state`` to a timestamped file in ``dest_dir`` and return
    the path written.

    The file is plain JSON in the same shape as ``SAVE_FILE`` (so it can
    be imported back with ``import_save``), named
    ``tap_ninja_YYYYMMDD_HHMMSS.json``.  The write is atomic (tmp file +
    ``os.replace``) and never touches the live ``SAVE_FILE``.
    """
    os.makedirs(dest_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    path = os.path.join(dest_dir, f"tap_ninja_{ts}.json")
    payload = state.to_dict()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
    return path


def import_save(path: str) -> GameState:
    """Load, validate, and replace the live save with the file at ``path``.

    Reads the file, parses JSON, runs ``validate_save``, and on success
    rebuilds a ``GameState`` and writes it to ``SAVE_FILE`` (via the
    state's own atomic ``save``).  On a validation failure or read error
    the live save is left untouched and ``ValueError`` is raised.
    Returns the newly installed ``GameState``.
    """
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    # Migrate the dict before validation + from_dict so an imported v2 save
    # is upgraded to v3 in the same way ``GameState.load`` does it.
    d = _migrate(d)
    res = validate_save(d)
    if not res.valid:
        raise ValueError(
            "save file failed validation: " + "; ".join(res.errors)
        )
    state = GameState.from_dict(d)
    state.save()  # writes to SAVE_FILE atomically
    return state


def backup_save(src: str = SAVE_FILE, keep: int = 3) -> Optional[str]:
    """Rotate ``src`` into a set of ``.bak.N`` backups, keeping the last
    ``keep`` (default 3).

    The newest backup is ``src + ".bak.1"``; older ones shift down to
    ``.bak.2``, ``.bak.3``, ... and the oldest (``.bak.{keep}``) is
    removed.  If ``src`` does not exist, this is a no-op and ``None`` is
    returned.  Returns the path of the newest backup written.
    """
    if not os.path.exists(src):
        return None
    # Remove the oldest slot so the top shift has room.
    oldest = f"{src}.bak.{keep}"
    if os.path.exists(oldest):
        os.remove(oldest)
    # Shift .bak.{i} -> .bak.{i+1} from the top down.
    for i in range(keep - 1, 0, -1):
        cur = f"{src}.bak.{i}"
        nxt = f"{src}.bak.{i + 1}"
        if os.path.exists(cur):
            os.replace(cur, nxt)
    # Copy the live save into the newest slot.
    newest = f"{src}.bak.1"
    shutil.copy2(src, newest)
    return newest


def cloud_sync(dest: str) -> str:
    """Copy ``SAVE_FILE`` to a second location (a "cloud-ish" sync).

    ``dest`` may be a directory (the save keeps its ``save.json`` name)
    or a full file path.  Parent directories are created if needed.  The
    copy preserves mtime (``shutil.copy2``).  Raises ``FileNotFoundError``
    if there is no live save to sync.  Returns the destination path
    written.
    """
    if not os.path.exists(SAVE_FILE):
        raise FileNotFoundError(f"no save to sync: {SAVE_FILE}")
    if os.path.isdir(dest):
        dest = os.path.join(dest, os.path.basename(SAVE_FILE))
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    shutil.copy2(SAVE_FILE, dest)
    return dest
