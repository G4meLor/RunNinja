"""Save-version migration chain: v2 -> v3 with new-field defaults.

Regression guard for the "decorative save_version" bug: ``from_dict`` used
``hasattr+setattr`` with no migration logic, so the "forward-compatible
additive schema" claim was a time bomb (the first field rename or type
change would silently destroy player progress). The fix adds a
``MIGRATIONS`` dict of pure functions; ``load()`` walks the chain from the
file's ``save_version`` up to ``CURRENT_SAVE_VERSION``.

Covers:
- A v2 save dict loads under v3 code without data loss (gold/elixir/
  upgrades preserved) and the new v3 fields are seeded with defaults
  (``render_quality``, ``attuned_element == "none"``).
- The migration chain has a migration from every version 2..CURRENT.
- The migration is a PURE function (does not mutate the input dict).
- A v2 save round-trips: load -> save -> reload preserves all fields.
- ``load()`` wires the migration (a v2 save file on disk loads under
  v3 code).
"""
import json
import os
import tempfile

import pytest


def test_v2_save_loads_under_v3_code():
    """A v2 dict, migrated then from_dict'd, preserves v2 data and seeds v3."""
    from core.state import GameState, _migrate
    v2_dict = {
        "save_version": 2, "gold": 1000.0, "elixir": 5,
        "skill_tree": [], "achievements": [], "pets": {},
        "upgrades": {"tap_power": 3}, "buildings": {"farm": 2},
    }
    s = GameState.from_dict(_migrate(v2_dict))
    # v2 data preserved.
    assert s.gold == 1000.0
    assert s.elixir == 5
    assert s.upgrades["tap_power"] == 3
    assert s.buildings.get("farm") == 2
    # New v3 fields seeded with defaults.
    assert hasattr(s, "render_quality")
    assert s.render_quality == "med"
    assert s.attuned_element == "none"
    assert s.dojo == "none"
    assert s.rhythm_streak == 0
    assert s.tokens == {}
    assert s.gear == {}
    assert s.souls == 0
    assert s.soul_tree == set()
    assert s.epic_research == set()
    assert s.heritage == set()
    assert s.cosmic_forge == 0
    assert s.music_on is False
    assert s.volume == 0.5
    assert s.text_scale == 1.0
    assert s.dyslexia_font is False
    assert s.high_contrast is False
    assert s.seen_hints == []
    assert s.save_version == 3


def test_migration_chain_walks_all_versions():
    """Every version from 2 up to CURRENT has a migration entry."""
    from core.state import MIGRATIONS, CURRENT_SAVE_VERSION
    assert CURRENT_SAVE_VERSION == 3
    assert 2 in MIGRATIONS
    for v in range(2, CURRENT_SAVE_VERSION):
        assert v in MIGRATIONS, f"missing migration from v{v}"


def test_migration_is_pure_does_not_mutate_input():
    """The migration must not mutate the input dict (it's a pure function)."""
    from core.state import _migrate_v2_to_v3
    v2_dict = {
        "save_version": 2, "gold": 500.0, "elixir": 3, "attuned_element": "fire",
    }
    original = dict(v2_dict)
    result = _migrate_v2_to_v3(v2_dict)
    # The input dict is unchanged.
    assert v2_dict == original
    assert v2_dict["save_version"] == 2  # not bumped in the input
    # The result has the new version and seeded fields.
    assert result["save_version"] == 3
    # Existing v3-ish fields are preserved (not overwritten).
    assert result["attuned_element"] == "fire"
    # Missing fields are seeded.
    assert result["render_quality"] == "med"
    assert result["dojo"] == "none"


def test_v2_save_round_trip():
    """A v2 save on disk: load -> save -> reload preserves all fields."""
    from core.state import GameState, CURRENT_SAVE_VERSION
    v2_dict = {
        "save_version": 2, "gold": 2500.0, "elixir": 7, "amber": 3, "medals": 1,
        "skill_tree": ["off_root"], "achievements": ["first_blood"],
        "pets": {"fox": 2}, "upgrades": {"tap_power": 5},
        "buildings": {"farm": 3, "forge": 1}, "zone_index": 4, "ascend_tier": 1,
        "playtime": 3600.0, "last_saved": 1700000000.0,
    }
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "save.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(v2_dict, f)
        # Load (runs the migration), save (writes v3), reload (reads v3).
        s1 = GameState.load(path)
        assert s1.gold == 2500.0
        assert s1.elixir == 7
        assert s1.skill_tree == {"off_root"}
        assert s1.achievements == {"first_blood"}
        assert s1.save_version == CURRENT_SAVE_VERSION
        s1.save(path)
        s2 = GameState.load(path)
        # v2 data preserved through the round-trip.
        assert s2.gold == 2500.0
        assert s2.elixir == 7
        assert s2.skill_tree == {"off_root"}
        assert s2.achievements == {"first_blood"}
        assert s2.upgrades["tap_power"] == 5
        assert s2.buildings.get("farm") == 3
        # v3 fields are present after the round-trip.
        assert s2.save_version == CURRENT_SAVE_VERSION
        assert s2.attuned_element == "none"
        assert s2.render_quality == "med"


def test_load_wires_migration_for_v2_file():
    """load() applies the migration: a v2 file on disk loads as v3."""
    from core.state import GameState, CURRENT_SAVE_VERSION
    v2_dict = {
        "save_version": 2, "gold": 100.0, "elixir": 1, "amber": 0, "medals": 0,
        "zone_index": 0, "ascend_tier": 0, "playtime": 0.0, "last_saved": 0.0,
    }
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "save.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(v2_dict, f)
        s = GameState.load(path)
        assert s.save_version == CURRENT_SAVE_VERSION
        assert s.gold == 100.0
        # v3 fields seeded by the migration.
        assert s.attuned_element == "none"
        assert s.render_quality == "med"


def test_import_save_wires_migration_for_v2_file():
    """save_manager.import_save applies the migration too (it has its own
    load path separate from GameState.load)."""
    from core.state import CURRENT_SAVE_VERSION, SAVE_FILE
    from core.save_manager import import_save
    v2_dict = {
        "save_version": 2, "gold": 200.0, "elixir": 2, "amber": 0, "medals": 0,
        "zone_index": 1, "ascend_tier": 0, "playtime": 0.0, "last_saved": 0.0,
    }
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "import.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump(v2_dict, f)
        # Point SAVE_FILE at a temp path so import_save doesn't clobber the
        # real live save. The default arg was bound at function-definition
        # time, so we patch the module attribute AND pass it explicitly by
        # monkeypatching SAVE_FILE before the call (state.save reads the
        # module-global at call time via the default-arg binding, so we
        # rebind the module global and also rebind the default by calling
        # state.save with the explicit path through import_save's own
        # state.save() call — which uses SAVE_FILE's default). The cleanest
        # approach: patch core.state.SAVE_FILE and also the default arg.
        import core.state as _st
        import core.save_manager as _sm
        orig_save_file = _st.SAVE_FILE
        tmp_save = os.path.join(td, "save.json")
        _st.SAVE_FILE = tmp_save
        # Rebind the default arg of GameState.save by wrapping it.
        orig_save = _st.GameState.save
        def _patched_save(self, path=tmp_save):
            return orig_save(self, path)
        _st.GameState.save = _patched_save
        try:
            state = import_save(src)
            assert state.save_version == CURRENT_SAVE_VERSION
            assert state.gold == 200.0
            assert state.attuned_element == "none"
            # The live save file was written with the migrated version.
            with open(tmp_save, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            assert on_disk["save_version"] == CURRENT_SAVE_VERSION
            assert on_disk["attuned_element"] == "none"
        finally:
            _st.SAVE_FILE = orig_save_file
            _st.GameState.save = orig_save


def test_every_state_field_is_in_save_schema():
    """Every ``GameState`` dataclass field is a key in
    ``save_manager._SCHEMA``.

    Regression guard for the whole class of "field added to the dataclass
    + migration but not the schema" bug (the Task 34
    ``dungeon_best_floor`` and the Task 28 ``auto_ascend_threshold`` were
    both this bug: a corrupted value passed ``validate_save`` silently).
    ``GameState.__dataclass_fields__`` is the source of truth for the
    fields the live state serializes; ``_SCHEMA`` is the type-check map
    ``validate_save`` walks. The two must cover the same set of fields so
    a corrupted value in any field is flagged.
    """
    from core.state import GameState
    from core import save_manager
    state_fields = set(GameState.__dataclass_fields__)
    schema_fields = set(save_manager._SCHEMA)
    missing = state_fields - schema_fields
    assert not missing, (
        f"State fields missing from _SCHEMA: {sorted(missing)}")
