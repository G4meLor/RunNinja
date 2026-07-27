# Bestiary — integration spec

A research menu that catalogs every enemy the player has encountered,
grouped by zone.  Each of the 9 zones renders as a section: a header
(zone index, name, boss-status pill) followed by a row of 3 enemy
cards and one boss card beneath them.  Zones the player has not yet
reached show silhouettes and no names; a zone's boss card stays locked
(silhouette) until that zone's boss has been defeated.

## Files

| Path | Role |
|---|---|
| `ui/screen_bestiary.py` | New. `BestiaryScreen(game)` with `handle` / `update` / `draw`. |
| `ui/screen_game.py` | Existing. Add a "Bestiary" nav button. |
| `main.py` | Existing. Register the screen in `self.screens`. |
| `data/enemies.py` | Existing. `ZONES`, `EnemyDef`, `BOSSES` — source of the roster. |
| `assets.py` | Existing. `enemy_surface(edef, size)` — cached sprite factory. |
| `core/state.py` | Existing. `state.best_zone`, `state.bosses_killed`. |

## `BestiaryScreen` API

```python
screen = BestiaryScreen(game)
screen.handle(event)   # mouse wheel (scroll) + back button
screen.update(dt)      # smooth-scroll + button hover
screen.draw(surf)      # full screen render
```

`BestiaryScreen` is self-contained — it reads `game.state.best_zone`
and `game.state.bosses_killed` every frame (both are plain ints on
`GameState`), so no wiring beyond construction is required.

## State contract

- `state.best_zone` — highest zone index the player has reached.  A
  zone `i` is **revealed** when `i <= state.best_zone`.
- `state.bosses_killed` — total bosses slain across the run.  Zone
  `i`'s boss is **revealed as defeated** when `i < state.bosses_killed`
  (the runner increments `bosses_killed` after each boss kill, so the
  first defeated boss unlocks zone 0's boss card, etc.).

Both fields already exist on `GameState` (`core/state.py`) and are
maintained by `engine/runner.py` — no new state is introduced.

## Layout

- 9 zones, one section each, stacked vertically inside a viewport
  `Rect(40, 110, 1200, 540)`.
- Each section: a 30px header (hue dot, "Zone N", zone name,
  boss-status pill), then a row of 3 enemy cards (`_CARD_H = 92`)
  and one full-width boss card (`_BOSS_H = 96`) beneath them.
- Smooth vertical scroll (mouse wheel), eased toward
  `target_scroll`; a thin scrollbar on the right edge when content
  overflows the viewport.
- A "Back" button (`ui.widgets.Button`) at the bottom-left returns
  to the `"game"` screen via `game.set_screen("game")`.

## Reveal rules

| Zone `i` | Enemies | Boss card |
|---|---|---|
| `i <= best_zone` | Full sprite, name, HP/DMG/Gold multipliers, speed/size/rare-drop | Sprite + stats only if `i < bosses_killed`; otherwise silhouette + "Defeat this zone's boss to reveal." |
| `i > best_zone` | Silhouette + "???" + "Locked zone" | Silhouette + "Locked" pill |

Silhouettes are built once per `(edef.id, size)` by multiplying the
cached `enemy_surface` with a near-black fill (`BLEND_RGBA_MULT`,
which preserves the alpha outline while crushing RGB) and cached in
`_SIL_CACHE`.  No surfaces or caches are allocated per frame.

## `GameScreen` integration — add a "Bestiary" nav button

`ui/screen_game.py` builds its top-right nav rail in `_build_nav`.
Append one entry so a "Bestiary" button appears alongside Records,
Settings, etc.:

```python
def _build_nav(self) -> None:
    y = 8
    x = cfg.WINDOW_W - 8
    labels = [
        ("Bestiary", lambda: self.game.set_screen("bestiary")),   # NEW
        ("Records", lambda: self.game.set_screen("records")),
        ("Settings", lambda: self.game.set_screen("settings")),
        ("Quests", lambda: self.game.set_screen("quests")),
        ("Pets", lambda: self.game.set_screen("pets")),
        ("Skills", lambda: self.game.set_screen("skilltree")),
        ("Upgrades", lambda: self.game.set_screen("upgrades")),
        ("Buildings", lambda: self.game.set_screen("buildings")),
        ("Ascend", lambda: self.game.set_screen("ascend")),
    ]
    for label, cb in reversed(labels):
        w = 78
        x -= w + 6
        btn = Button((x, y, w, 32), label, on_click=cb)
        self.nav_buttons.insert(0, btn)
```

The rail lays out right-to-left, so the new entry lands at the
leftmost end of the row (after "Ascend").  No width/position changes
are needed — the existing 78px button slots fit one more.

## `main.py` integration — register the screen

Add the import and the `self.screens` entry:

```python
from ui.screen_bestiary import BestiaryScreen
# ...
self.screens = {
    # ... existing entries ...
    "bestiary": BestiaryScreen(self),
}
```

Optional: bind a hotkey (e.g. `K_b`) in the `KEYDOWN` handler to
`self.set_screen("bestiary")` for quick access.

## Constraints honored

- Pygame primitives only (rects, circles, lines, polygons); no
  external image assets.
- Cached `assets.enemy_surface(edef, size)` for every sprite;
  silhouettes cached in `_SIL_CACHE` by `(id, size)`.
- Cached `theme` fonts (`font_xs` / `font_sm` / `font_md` /
  `font_lg` / `font_xl`); no per-frame `SysFont` calls.
- No per-frame surface/list allocations — only the small
  `font.render` text images the rest of the UI already produces.
- Reads `state.best_zone` and `state.bosses_killed` directly; no
  new state, no save-schema change.
