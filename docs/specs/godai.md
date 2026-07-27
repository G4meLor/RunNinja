# Godai Elements screen — integration spec

A dedicated **research sub-menu** for the Godai branch of the elixir
skill tree (`data/skill_tree.py`, `godai_gate` + `godai_void` /
`godai_wind` / `godai_fire` / `godai_water`).  The screen is a
pentagon/circle diagram — the gate at the centre, the four elements
around it — that shows each element's accumulated bonus value (read from
`aggregate_bonuses`) and routes clicks to the skill-tree screen to
unlock/upgrade the path.

## Files

| Path | Role |
|---|---|
| `ui/screen_godai.py` | New. `GodaiScreen(game)` with `handle`/`update`/`draw`. |
| `ui/screen_game.py` | Existing. Add a "Godai" nav button in `_build_nav`. |
| `main.py` | Existing. Register the screen in `self.screens`. |
| `data/skill_tree.py` | Existing, read-only. `godai_*` nodes + `branch_color("godai")`. |
| `core/bonuses.py` | Existing, read-only. `aggregate_bonuses(state)` returns `godai_void`/`godai_wind`/`godai_fire`/`godai_water` + `unlock_godai`. |

## `GodaiScreen` API

```python
screen = GodaiScreen(game)
screen.handle(event)   # routes node clicks to the skill-tree screen
screen.update(dt)      # ticks the buttons
screen.draw(surf)      # background + pentagon diagram + detail panel
screen.selected        # node id shown in the detail panel (gate or an element)
screen.hover           # node id under the mouse, or None
```

The screen is **read-only + routing**: it does not unlock nodes itself.
Unlocking stays on the skill-tree screen (`core/skill_unlock.unlock`),
so the Godai screen is purely a visualisation + entry point for the
deeper progression path.

## Layout

The diagram occupies the left ~720px of the 1280×720 window; the detail
panel fills the right 480px.  All coordinates are module-level constants
in `ui/screen_godai.py`, computed once — not per frame.

```
+--------------------------------------------------------------+
|  Godai Elements                              Gate: Unlocked   |
|  The five-element path...                                    |
|  Elixir 5.0k                                                 |
|                                                              |
|              VOID                                            |
|               *     ┌──────────────────────────────┐         |
|              / \    │ Element of Void               │         |
|             /   \   │ Branch: Godai                 │         |
|            /     \  │ UNLOCKED                       │         |
|         GATE       │ Accumulated bonus              │         |
|            \     /  │   +15%                        │         |
|             \   /   │ Effect: +15% elixir gain.    │         |
|              \ /    │ Applied to: Ascension elixir  │         |
|               *     │  multiplier                  │         |
|              FIRE   │                               │         |
|                     │ Upgrade path                  │         |
|                     │ Prerequisite: Godai Elements  │         |
|                     │ Cost: 300 Elixir              │         |
|                     │ [████████░░░░░░░░░░░░]        │         |
|                     │ Click the node or "Open Skill │         |
|                     │  Tree" to unlock.             │         |
|                     │                               │         |
|                     │      [ Open Skill Tree ]      │         |
|                     └──────────────────────────────┘         |
|                                                              |
|  [ Back ]                                                    |
+--------------------------------------------------------------+
```

- **Gate node** at `(_DIAG_CX, _DIAG_CY) = (480, 410)`, radius `_GATE_R`
  = 62.  Labelled "GATE / Godai"; shows "OPEN" when unlocked or the
  elixir cost (`1000 e`) when locked.
- **Four element nodes** on a ring of radius `_DIAG_R` = 170 around the
  gate, each radius `_ELEM_R` = 50.  Angles measured from straight-up,
  clockwise:
  - `godai_void` (Void, Elixir gain) — top (0°)
  - `godai_wind` (Wind, Gold/sec) — right (90°)
  - `godai_fire` (Fire, Coin gold) — bottom (180°)
  - `godai_water` (Water, Hero power) — left (270°)
- **Connecting lines** from the gate to each element, drawn under the
  circles so the nodes cap them.  Line color is the element color when
  the element is unlocked, else `C.panel_border`; width 3 unlocked / 2
  locked.
- **Faint outer ring** through the four elements (`pygame.draw.circle`
  radius `_DIAG_R`, color `C.panel_lo`, width 1) — the pentagon guide.

Each element node shows three lines: the element label (e.g. "VOID"),
the effect label (e.g. "Elixir gain"), and the accumulated bonus value
(`+15%` when unlocked, `—` when at 0).  The value is read live from
`aggregate_bonuses(state)` so it updates the moment a node is unlocked
elsewhere.

## Detail panel

The right-hand panel (`_DETAIL_RECT = Rect(780, 130, 480, 560)`) shows
the currently selected node (`self.selected`, one of `godai_gate` or the
four element ids).  It contains:

- **Header** — node name + "Branch: Godai".
- **Status** — "UNLOCKED" (green) or "LOCKED" (muted).
- **Accumulated bonus** — the headline number: `+{int(round(value*100))}%`
  for an element, or "Active" for the gate when unlocked.  Read from
  `evo.get(node.effect_key, 0.0)`.
- **Effect** — the node's `desc` (e.g. "+15% elixir gain."), wrapped to
  the panel width.
- **Applied to** — a short engine-use label (see table below).
- **Upgrade path** — prerequisite name + cost, with an elixir
  affordability bar (`state.elixir / cost`).
- **Hint** — "Click the node or 'Open Skill Tree' to unlock." (locked)
  or "Unlocked. Open the skill tree to deepen this path." (unlocked).
- **Open Skill Tree button** — routes to the skill-tree screen so the
  player can actually spend elixir.

### Element effect labels

| id           | label | effect (node.desc)        | applied to (engine use)            |
|--------------|-------|---------------------------|------------------------------------|
| `godai_void` | VOID  | +15% elixir gain.         | Ascension elixir multiplier        |
| `godai_wind` | WIND  | +15% gold/sec.            | Passive building income            |
| `godai_fire` | FIRE  | +15% coin gold value.     | Enemy gold multiplier              |
| `godai_water`| WATER | +15% hero power.          | Max HP / defence                   |
| `godai_gate` | GATE  | Unlock the Godai Elements sub-tree. | Enables Void/Wind/Fire/Water |

The "applied to" labels mirror where the engine actually consumes each
key (`core/ascend.py` `elixir_gain` for `godai_void`,
`core/game_economy.py` `total_gps` for `godai_wind`,
`engine/runner.py` `gold_mult` for `godai_fire`, `engine/ninja.py`
`compute_ninja_stats` for `godai_water`).

## Integration

### 1. Register the screen in `main.py`

```python
from ui.screen_godai import GodaiScreen
...
self.screens = {
    ...
    "godai": GodaiScreen(self),
    ...
}
```

### 2. Add a "Godai" nav button in `GameScreen._build_nav`

In `ui/screen_game.py`, add a row to the `labels` list in `_build_nav`:

```python
labels = [
    ("Records", lambda: self.game.set_screen("records")),
    ("Settings", lambda: self.game.set_screen("settings")),
    ("Quests", lambda: self.game.set_screen("quests")),
    ("Pets", lambda: self.game.set_screen("pets")),
    ("Skills", lambda: self.game.set_screen("skilltree")),
    ("Godai", lambda: self.game.set_screen("godai")),   # <<< new
    ("Upgrades", lambda: self.game.set_screen("upgrades")),
    ("Buildings", lambda: self.game.set_screen("buildings")),
    ("Ascend", lambda: self.game.set_screen("ascend")),
]
```

The nav bar builds right-to-left, so the new button lands between
"Skills" and "Upgrades" — appropriate, since Godai is the deep
progression branch off the elixir skill tree.  (The nav buttons are 78px
wide each; nine buttons fit in the 1280px window with the existing
layout.)

### 3. (Optional) hotkey

Bind a hotkey in `main.py` if desired — e.g. `pygame.K_g` for Godai.
Not required for the nav-button integration.

## Behavior contract

- **Hover**: moving the mouse over a node sets `self.hover`; the node's
  border brightens and a thin outer ring is drawn.
- **Click**: a left-click on the gate or any element node sets
  `self.selected` and routes to the skill-tree screen
  (`game.set_screen("skilltree")`) so the player can unlock/upgrade the
  Godai branch there.  Clicking off-diagram does nothing.
- **Detail panel**: always shows the currently selected node; defaults
  to the gate on screen entry.
- **Live values**: the diagram + detail panel re-read
  `aggregate_bonuses(state)` every `draw`, so accumulated bonuses
  update the instant a node is unlocked on the skill-tree screen — no
  stale values.

## Constraints honored

- **Pygame primitives only.** Circles, lines, rects, text — no external
  image assets.
- **Cached theme fonts** (`font_xs` / `font_sm` / `font_md` / `font_lg`
  / `font_xl`); no per-frame `SysFont` calls.
- **No per-frame allocations in the hot path.** Node positions are
  precomputed in `__init__` (`self._positions`); the only per-frame
  allocations are the `pygame.Rect` objects in `self.node_rects`
  (5 small rects) and the tiny `_wrap` list (detail panel only, not the
  diagram loop).  The background full-screen gradient is cached by
  `theme.gradient_v`.
- **Read-only state.** The screen never mutates `GameState`; it only
  reads `state.elixir`, `state.skill_tree`, and
  `aggregate_bonuses(state)`.  All unlocking happens on the skill-tree
  screen.

## Save compatibility

No new state fields.  The screen reads existing `state.skill_tree` (the
set of unlocked node ids) and `state.elixir`, both already persisted by
`core/state.py`.  No save migration is required.
