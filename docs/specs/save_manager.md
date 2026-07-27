# Save Manager — export / import / backup / sync / integrity

A new module, `core/save_manager.py`, wraps the single `SAVE_FILE`
written by `core.state.GameState` with the workflow a real player wants
around it: **export** a run to a timestamped file, **import** a save
file (validate then replace the live save), **backup** the live save to
a rotating set of `.bak.N` files, **validate** a save dict's schema, and
a one-line **cloud-ish sync** that copies the save to a second location
(a synced folder, USB stick, etc. — no network).

Stdlib only (`json`, `os`, `shutil`, `time`, `dataclasses`). The module
does **not** import pygame, so it is safe to call from headless scripts
and from the settings screen alike.

## Files

| Path | Role |
|---|---|
| `core/save_manager.py` | New. `export_save`, `import_save`, `backup_save`, `validate_save`, `SaveSummary`, `ValidationResult`, `cloud_sync`. |
| `core/state.py` | Existing. `GameState`, `SAVE_FILE`, `SAVE_DIR`, `to_dict` / `from_dict` / `save` / `load`. The source of the schema validated here. |
| `ui/screen_settings.py` | Existing. Settings screen hosts the Export / Import / Backup / Sync buttons (see Integration). |
| `main.py` | Existing. `Game.run` calls `backup_save()` on exit (see Integration). |

## `core/save_manager.py` API

```python
from core import save_manager as sm
from core.state import GameState, SAVE_FILE

# Export the current run to a timestamped file in dest_dir.
path = sm.export_save(state, dest_dir)          # -> "tap_ninja_YYYYMMDD_HHMMSS.json"

# Import a save file: read + validate + replace SAVE_FILE.
state = sm.import_save(path)                   # raises ValueError on bad file

# Rotate the live save into .bak.1/.2/.3 (keep last 3).
newest = sm.backup_save()                       # -> SAVE_FILE + ".bak.1"; None if no live save

# Validate a save dict (e.g. before importing).
res = sm.validate_save(d)                       # ValidationResult(valid, errors, warnings)

# Cloud-ish sync: copy SAVE_FILE to a second location.
dest = sm.cloud_sync(dest_path_or_dir)          # raises FileNotFoundError if no save

# Display info about a save file (for listings).
summary = sm.SaveSummary.from_path(path)        # None if missing/corrupt
summary.describe()                               # one-line row text
```

### `validate_save(d) -> ValidationResult`

Checks that `d` is a `dict` with the **required** Tap Ninja fields and
that every known field has the correct type.

- **Required fields** (missing any is a hard error):
  `save_version`, `gold`, `elixir`, `amber`, `medals`, `zone_index`,
  `ascend_tier`, `playtime`, `last_saved`.
- **Type-checked if present** (all `GameState` serialized fields, see
  `_SCHEMA` in the module). An unknown/extra field is ignored
  (forward-compatible: a newer save that adds a field still imports).
- **Type rules**: `bool` is not accepted as `int`; `int` is accepted
  where `float` is expected (JSON drops the distinction and
  `GameState`'s float fields routinely hold ints).
- **Warnings** (non-fatal, surfaced to the UI): negative currencies,
  `playtime`, or `monsters_killed`.

Returns `ValidationResult(valid, errors, warnings)`; `bool(result)` is
`True` only when `errors` is empty. `import_save` raises `ValueError`
with the joined `errors` when `valid` is `False`.

### `export_save(state, dest_dir) -> str`

Writes `state.to_dict()` to `dest_dir/tap_ninja_YYYYMMDD_HHMMSS.json`
as pretty JSON, atomically (tmp file + `os.replace`). Does **not**
touch `SAVE_FILE`. Returns the path written. `dest_dir` is created if
missing.

### `import_save(path) -> GameState`

Reads `path`, parses JSON, runs `validate_save`. On success, rebuilds a
`GameState` via `from_dict` and writes it to `SAVE_FILE` through the
state's own atomic `save()`. On any validation failure or read error,
the live save is left untouched and `ValueError` (or the underlying
`OSError` / `json.JSONDecodeError`) is raised. Returns the newly
installed `GameState`.

### `backup_save(src=SAVE_FILE, keep=3) -> Optional[str]`

Rotating backup. If `src` does not exist, returns `None` (no-op).
Otherwise removes the oldest `.bak.{keep}`, shifts
`.bak.{i}` -> `.bak.{i+1}` for `i` from `keep-1` down to 1, then
`shutil.copy2(src, src + ".bak.1")` (preserves mtime). Returns the
newest backup path. Default `keep=3` means the last three saves are
retained as `SAVE_FILE.bak.1` (newest), `.bak.2`, `.bak.3` (oldest).

### `cloud_sync(dest) -> str`

"Cloud-ish" sync: `shutil.copy2(SAVE_FILE, dest)`. `dest` may be a
directory (the save keeps its `save.json` name) or a full file path.
Parent dirs are created. Raises `FileNotFoundError` if there is no live
save to sync. Returns the destination path written. This is deliberately
just a file copy — no network, no conflict resolution — so the player
can point it at a Dropbox / Syncthing / USB folder and get a second
copy without any new dependencies.

### `SaveSummary`

```python
@dataclass
class SaveSummary:
    path, mtime, size, save_version, gold, elixir, amber, medals,
    ascend_tier, zone_index, playtime, last_saved

    @classmethod
    def from_path(path) -> Optional[SaveSummary]   # None if missing/corrupt
    def format_when() -> str                       # "2026-07-26 14:03"
    def describe() -> str                          # one-line row for a UI list
```

A compact, display-ready snapshot of a save file, built from the file
on disk so the settings screen can list exports/backups without
loading a full `GameState`. `from_path` returns `None` for a missing
or unreadable file (a UI listing never crashes on a corrupt/deleted
file).

## Integration

### Settings screen (`ui/screen_settings.py`)

The settings screen gains four buttons under a new "Save management"
panel, wired to this module. (No other screen is touched.)

- **Export save** — `sm.export_save(self.game.state, cfg.EXPORT_DIR)`
  (default `~/.tap_ninja/exports/`); show the written path with
  `SaveSummary.describe()` in a toast/confirmation line.
- **Import save** — opens a file picker (or a text input for a path),
  calls `sm.import_save(path)`, then refreshes `self.game.state` and
  `self.game.runner.state` to the returned `GameState` (mirroring the
  pattern already used by the existing `_reset` handler in
  `screen_settings.py`). On `ValueError`, show the `errors` list and
  leave the live save untouched. Recommended: call `backup_save()`
  **before** the import so the player can undo a bad import from
  `.bak.1`.
- **Backup now** — `sm.backup_save()`; show the returned path.
- **Cloud sync** — `sm.cloud_sync(cfg.SYNC_DIR)` (a path the player
  configures, e.g. a Dropbox folder); show the destination path or a
  `FileNotFoundError` message if there is no save yet.

A read-only listing of the last three backups can be rendered with
`SaveSummary.from_path(f"{SAVE_FILE}.bak.{i}")` for `i in 1..3`,
showing `summary.describe()` for each existing one.

### `main.py` — backup on exit

`Game.run` already ends with `self.state.save(); pygame.quit()`. Add a
`backup_save()` call so each session leaves a fresh `.bak.1` and the
last three sessions are retained:

```python
# at the end of Game.run, after the autosave but before pygame.quit
self.state.save()
try:
    from core.save_manager import backup_save
    backup_save()
except OSError:
    pass
pygame.quit()
```

The `try/except OSError` matches the defensive style already used in
`GameState.load`'s backup path, so a full disk or a missing
`SAVE_DIR` never crashes the exit.

## Why no network

"Cloud-ish" is intentionally local. Real cloud sync needs credentials,
conflict resolution, and retry logic that doesn't belong in a
single-player idle game. Pointing `cloud_sync` at a folder the player
already syncs with their tool of choice (Dropbox, Syncthing, rsync,
git) gives the same result with zero new dependencies and zero new
failure modes.

## Testing notes

The module is pure stdlib and side-effect-free except for filesystem
writes, so it is testable without pygame:

```python
from core.state import GameState
from core import save_manager as sm

state = GameState(); state.gold = 1234.5; state.zone_index = 5
path = sm.export_save(state, "/tmp/tn_exports")
assert sm.validate_save(__import__("json").load(open(path))).valid

state2 = sm.import_save(path)
assert state2.gold == 1234.5 and state2.zone_index == 5

for _ in range(4): sm.backup_save("/tmp/tn_bak.json", keep=3)
# .bak.1/.2/.3 exist, no .bak.4
```
