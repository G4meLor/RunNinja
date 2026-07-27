# Keyboard Navigation — integration spec

A new module, `ui/keyboard_nav.py` (`KeyboardNav` + a process singleton
`keyboard_nav`), makes every screen fully playable without a mouse:

* **Tab / Shift-Tab** cycles focus forward / backward through the
  buttons (and any scroll lists) registered for the current screen.
* **Enter / Space** activates the focused button (calls its
  `on_click`) or, if a scroll list is focused, confirms the current
  list selection.
* **Arrow keys** move the focused scroll list's selection up / down
  and scroll to keep it visible.
* A **pulsing focus ring** is drawn around the focused widget so the
  player always sees where keyboard input will land.

The manager is a process singleton (`keyboard_nav`). `main.py` owns the
three-line wiring (set active screen, handle keyboard events, draw the
ring) and each screen registers its button list once. No existing file
needs to change for the manager to be usable; the integration below is
the *intended* wiring.

## Files

| Path | Role |
|---|---|
| `ui/keyboard_nav.py` | **New.** `KeyboardNav` + `keyboard_nav` singleton + `set_active` hook. |
| `main.py` | Existing. Owns the event / update / draw loop; calls `set_active`, `handle`, `update`, `draw_focus_ring`. |
| `ui/screen_*.py` | Existing. Each screen calls `keyboard_nav.bind(name, buttons, lists=…)` so the manager knows the focusable widgets. |
| `ui/widgets.py` | Existing. `Button` (has `rect` / `on_click` / `enabled`) and `ScrollList` (has `rect` / `items` / `selected_index` / `on_select` / `item_h` / `target_scroll`) are the two widget shapes the manager duck-types. |
| `theme.py` | Existing. `C.panel_border_hi` / `C.gold` / `C.bg_top` drive the ring color. |

## `KeyboardNav` API

```python
from ui.keyboard_nav import keyboard_nav, set_active

keyboard_nav.bind("menu", menu_screen.buttons)
keyboard_nav.bind("buildings", buildings_screen.buttons + buildings_screen.buy_buttons,
                   lists=[buildings_screen.list])
set_active("game")                 # called from Game.set_screen

# in the event loop (KEYDOWN branch):
if keyboard_nav.handle(event):
    continue                       # consumed -- skip the screen's own handle

# in the update loop:
keyboard_nav.update(dt)

# in the draw loop, AFTER the screen draws:
keyboard_nav.draw_focus_ring(surf)
```

`bind(screen_name, buttons, *, lists=None)`:
- `buttons` is a list of `Button` (or any object with a `rect` plus an
  `on_click` / `enabled` pair). `lists` is an optional list of
  scroll-list-like widgets; they are appended after the buttons in Tab
  order.
- Re-binding the same screen **preserves** the focus index (clamped to
  the new length) so dynamic button lists — e.g. the buildings screen's
  `buy_buttons` rebuilt on a purchase — do not reset focus.

`set_active(screen_name)` is the global hook `main.py.set_screen` calls
so the manager tracks the current screen without holding a `Game`
reference.

## Behavior contract

- **Tab / Shift-Tab** moves focus by ±1, wrapping around, and skips
  disabled buttons (lands on the next enabled button or list).
- **Enter / Space** fires the focused button's `on_click` (and a brief
  pressed flash for tactile feedback, skipped under reduced motion) or
  confirms a focused list's current selection via `on_select`. A
  disabled button swallows the key without firing — so Enter never
  leaks through to other handlers.
- **Arrow keys** only act on a focused scroll list: Up/Left →
  previous item, Down/Right → next item, clamped to `[0, len(items))`,
  and the list's `target_scroll` is nudged so the selection stays
  visible. They do nothing on a focused button (so the player can
  still use the 1-9 / ESC / P / F1 shortcuts).
- **Per-screen focus index**: each screen remembers its focus
  position, so switching away and back preserves the player's place.
- **Reduced motion**: `keyboard_nav.reduced_motion = state.reduced_motion`
  freezes the ring at full brightness (no pulse) and skips the pressed
  flash — mirrors the rest of the codebase's accessibility handling.

## `main.py` integration

### 1. Construction (`Game.__init__`)

```python
from ui.keyboard_nav import keyboard_nav, set_active
...
# no per-Game instance; the singleton is owned by the module.
```

### 2. `set_screen(name)`

Call the global hook so the nav tracks the current screen:

```python
def set_screen(self, name):
    if name in self.screens:
        self.current_screen = name
        set_active(name)
```

### 3. Event loop (`run`)

Inside the `KEYDOWN` branch, before `self.screens[…].handle(event)`,
let the nav consume Tab / Enter / Space / arrows. The 1-9 / ESC / P /
F1 shortcuts stay first (they are not Tab/Enter/Space/arrows, so the
nav's `handle` returns `False` for them and they fall through as
before):

```python
for event in pygame.event.get():
    if event.type == pygame.QUIT:
        running = False
    elif event.type == pygame.KEYDOWN:
        # ... existing ESC / P / F1 / 0-9 shortcuts unchanged ...
        # Let the nav consume Tab/Enter/Space/arrows before the screen.
        if keyboard_nav.handle(event):
            continue
    self.screens[self.current_screen].handle(event)
```

### 4. Update loop (`_update`)

Next to the per-screen `update(dt)`:

```python
self.screens[self.current_screen].update(dt)
keyboard_nav.reduced_motion = self.state.reduced_motion
keyboard_nav.update(dt)
```

### 5. Draw loop (`run`)

Draw the focus ring *after* the screen so it sits on top:

```python
self.screens[self.current_screen].draw(self.screen)
keyboard_nav.draw_focus_ring(self.screen)
if self.show_fps:
    self._draw_fps()
```

The FPS overlay and pause overlay are drawn after the ring so they stay
on top during a fade.

## Per-screen registration

Each screen registers its button list once (in `__init__` or at the
top of `update` — wherever the list is fresh). The manager duck-types
the widgets, so it works for any `Button`-like or `ScrollList`-like
object without a change to `ui/widgets.py`.

| Screen | Buttons | Lists |
|---|---|---|
| `menu` | `MenuScreen.buttons` (`Play`, `Settings`) | — |
| `game` | `GameScreen.nav_buttons + [btn_energy] + skill_buttons` | — |
| `buildings` | `BuildingsScreen.buttons + buy_buttons` | `[BuildingsScreen.list]` |
| `upgrades` | `UpgradesScreen.buttons + upgrade_buttons` | — |
| `skilltree` | `SkillTreeScreen.buttons` | — (nodes are rects, not buttons) |
| `pets` | `PetsScreen.buttons` | — (pet grid is a rect dict) |
| `ascend` | `AscendScreen.buttons` | — |
| `quests` | `QuestsScreen.buttons` | — |
| `records` | `RecordsScreen.buttons` | — |
| `settings` | `SettingsScreen.buttons` | — |
| `bestiary` | `BestiaryScreen.buttons` | — (custom scroll, no `ScrollList`) |
| `cosmetics` | `CosmeticsScreen.buttons` | — (card grid is a rect dict) |

### Dynamic button lists

Screens whose button list changes at runtime (buildings, upgrades,
pets) re-bind each frame from `update` so the nav always sees the
current set. Re-binding preserves the focus index (clamped), so a
purchase that rebuilds `buy_buttons` does not yank focus back to the
first button:

```python
# ui/screen_buildings.py — in update(dt):
from ui.keyboard_nav import keyboard_nav
keyboard_nav.bind("buildings", self.buttons + self.buy_buttons,
                   lists=[self.list] if self.list else None)
```

### Static screens

Screens whose button list is fixed (menu, ascend, quests, records,
settings, skilltree) bind once in `__init__`:

```python
# ui/screen_menu.py — in __init__:
from ui.keyboard_nav import keyboard_nav
keyboard_nav.bind("menu", self.buttons)
```

### The game screen

The game screen's button list is `nav_buttons + [btn_energy] +
skill_buttons`. `skill_buttons` is rebuilt when the runner's skill set
changes, so re-bind from `update`:

```python
# ui/screen_game.py — in update(dt):
from ui.keyboard_nav import keyboard_nav
keyboard_nav.bind("game", self.nav_buttons + [self.btn_energy] + self.skill_buttons)
```

## Focus ring

`draw_focus_ring(surf)` renders two `pygame.draw.rect` outlines around
the focused widget's `rect`:

1. an outer faint halo (lerped toward the bg color so it reads as a
   glow without alpha),
2. an inner bright ring (lerped between `C.panel_border_hi` and
   `C.gold` by a `sin` pulse, 2..4 px thick, corner radius 8).

Under `reduced_motion` the pulse is frozen at full brightness and the
pressed flash is skipped. No `Surface` is allocated per frame — the
ring is drawn directly on the screen surface, and the only per-frame
objects are the two small `pygame.Rect.inflate` results (stack-local,
same as every other draw in the codebase).

## Constraints honored

- **pygame primitives only.** The ring is `pygame.draw.rect` on the
  screen surface; no external image assets, no `Surface` creation.
- **no per-frame allocations.** The pulse is a `sin` of an
  accumulating time; the ring color is an int lerp between two palette
  colors; the ring rect is a `pygame.Rect.inflate` (cheap, stack-local).
- **per-screen focus index.** Each screen remembers its focus position
  so switching away and back preserves the player's place; re-binding
  preserves the index (clamped) so dynamic button lists do not reset
  focus.
- **duck-typed widgets.** The manager works with any `Button`-like or
  `ScrollList`-like object — no change to `ui/widgets.py` is required.
- **no shortcut conflicts.** The manager only acts on Tab / Enter /
  Space / arrows, so the 1-9 / ESC / P / F1 shortcuts in `main.py` are
  untouched and continue to work exactly as before.
