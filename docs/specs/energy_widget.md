# Energy / Auto Katana Widget — integration spec

A new module, `ui/energy_widget.py` (`EnergyWidget`), replaces the flat
`btn_energy` button + the 6px `draw_bar` strip in `ui/screen_game.py`
with a single self-contained widget: a status label showing remaining
time, a gradient-filled energy bar, a "ready" pulse when full, a
"depleting" warning glow when low, a lockout indicator with diagonal
stripes, and a toggle button whose label cycles between **Engage** /
**Active** / **Recharging**.

All rendering uses pygame primitives + the cached theme fonts.  The hot
path performs no per-frame allocations: the glow overlays are drawn into
a single reused SRCALPHA scratch surface (allocated once when the bar
size is known, then reused), the gradient fill is drawn line-by-line
with `pygame.draw.line` (no surface allocation), and the static title
surface is rendered once at construction.

## `EnergyWidget` API

```python
class EnergyWidget:
    def __init__(self, rect, game) -> None: ...
    def handle(self, event: pygame.event.Event) -> None: ...  # click to toggle
    def update(self, dt: float) -> None: ...                 # pulse / warn / label
    def draw(self, surf: pygame.Surface) -> None: ...       # label + bar + button
```

| method | purpose |
|--------|---------|
| `__init__(rect, game)` | construct with the widget rect and the game handle |
| `handle(event)` | route mouse events to the toggle button (click toggles energy) |
| `update(dt)` | advance the pulse/warn clocks and refresh the button label / enabled / tint |
| `draw(surf)` | render the status label, the gradient bar with glow, and the toggle button |

The widget reads state from `game.state` and toggles through
`game.runner.toggle_energy()`.  It writes no state itself.

## State fields (read-only)

The widget reads the existing fields on `GameState` — no new fields, no
save migration:

| field | type | meaning |
|-------|------|---------|
| `state.energy` | `float` | current energy (seconds of auto-katana left) |
| `state.energy_max` | `float` | max energy (seconds) |
| `state.energy_active` | `bool` | is auto-katana running |
| `state.energy_lockout` | `float` | brief lockout after disabling |
| `state.reduced_motion` | `bool` | gate the pulse/warn animation |

## Visual states

The bar fill is a vertical gradient.  When the auto-katana is **idle**
the gradient is a cool blue (`(170,220,255)` → `(90,160,220)`, the mp
palette).  When the auto-katana is **active** the gradient switches to a
warm gold (`(255,230,150)` → `(220,170,80)`) so the player can tell at a
glance whether it is running.

| state | fill | overlay | button label |
|-------|------|---------|---------------|
| idle, full | blue gradient | soft green "ready" pulse | `Engage` |
| idle, charging | blue gradient | none | `Engage` |
| active, healthy | gold gradient | none | `Active` |
| active, low (< 20%) | gold gradient | fast red "depleting" warn glow | `Active` |
| active, depleted → lockout | (bar empty) | dim + diagonal stripes | `Recharging` |
| lockout (5s after disable) | (bar empty) | dim + diagonal stripes | `Recharging` |

The button is **disabled** during lockout (a cosmetic signal that the
player cannot toggle again yet; `toggle_energy` also guards, so this is
purely visual).

The status label (right) shows:

- `READY` (green) when idle and full,
- the remaining time as `Nh Nm` / `Nm SSs` / `s.s` (dim) while charging,
- the remaining time (green) while active,
- the lockout countdown (warn) while locked out.

The title `Auto Katana` is cached as a surface at construction (it never
changes), so it does not allocate per frame.

## Animation clocks

`update(dt)` advances two phase clocks:

- `_pulse_t` — drives the "ready" pulse (period `1.6s`), a soft green
  sin-wave glow around the bar.
- `_warn_t` — drives the "depleting" warn glow (period `0.8s`), a faster
  red sin-wave glow while the auto-katana is running low.

Both clocks are gated by `state.reduced_motion`: when reduced motion is
on they hold still so the glow is shown statically (no oscillation),
matching how the rest of the codebase handles the setting.

## Wiring into `ui/screen_game.py`

### 1. Construct the widget (`__init__`)

Replace the `btn_energy` button with an `EnergyWidget`.  The widget
occupies the same screen region as the old button + the 6px bar above it,
so it fits the existing bottom-right layout without disturbing the nav
row or the skill buttons:

```python
from ui.energy_widget import EnergyWidget

class GameScreen:
    def __init__(self, game) -> None:
        ...
        # Energy widget (replaces btn_energy + the flat bar).
        self.energy_widget = EnergyWidget(
            (cfg.WINDOW_W - 180, cfg.WINDOW_H - 90, 160, 74),
            game,
        )
```

The 74px height accommodates the 16px label row + 4px gap + 10px bar +
4px gap + the button.  (Drop `self.btn_energy = Button(...)`.)

### 2. `handle(event)`

Replace `self.btn_energy.handle(event)` with the widget:

```python
def handle(self, event: pygame.event.Event) -> None:
    if self.welcome_pending:
        ...
        return
    # Tap on the road.
    ...
    for b in self.nav_buttons + self.skill_buttons:
        b.handle(event)
    self.energy_widget.handle(event)
```

### 3. `update(dt)`

Replace `self.btn_energy.update(dt)`:

```python
def update(self, dt: float) -> None:
    for b in self.nav_buttons + self.skill_buttons:
        b.update(dt)
    self.energy_widget.update(dt)
    ...
```

### 4. `draw(surf)`

Replace the `btn_energy.draw(surf)` call **and** the four-line
"Energy bar above the button" block (`ebr = ...; draw_bar(...)`) with a
single call:

```python
# Skill buttons + energy widget.
for b in self.skill_buttons:
    b.draw(surf)
self.energy_widget.draw(surf)
```

The widget draws its own bar + label + button, so the separate
`draw_bar` call for the energy bar is removed.

### Removals

After wiring in the widget, delete from `screen_game.py`:

- `self.btn_energy = Button(...)` in `__init__`,
- `self.btn_energy.handle(event)` in `handle`,
- `self.btn_energy.update(dt)` in `update`,
- `self.btn_energy.draw(surf)` and the `ebr = ...; draw_bar(...)` block
  in `draw`.

`_toggle_energy` can be deleted (the widget calls
`game.runner.toggle_energy()` directly), or kept if other code calls it.

## Performance / constraints

- **pygame primitives only.** The widget is a label + a bar + a glow + a
  `Button`.  No external image assets.
- **no per-frame allocations in `draw`.** The glow overlays are drawn
  into a single reused SRCALPHA scratch surface (`self._glow_surf`),
  allocated once when the bar size is known (lazily on the first
  `_draw_*_glow` call) and then reused — the same pattern as
  `SkillTreeFxSystem._ring_surf` and `BossFxSystem`'s cached surfaces.
  The gradient fill uses `theme.gradient_v`, which draws line-by-line
  with `pygame.draw.line` and allocates nothing.  The title surface is
  rendered once at construction.  The only per-frame `font.render` is the
  dynamic remaining-time label, which changes every frame — this matches
  the codebase convention (see `theme.draw_text_center`, which renders
  per call).
- **no per-frame allocations in `update`.** The button label is mutated
  in place; no new `Button` objects are created.
- **cached fonts.** All text uses `theme.font_*` helpers, which cache by
  `(size, bold)` in `theme._FONTS`.
- **reduced motion.** The pulse/warn clocks hold still when
  `state.reduced_motion` is on, so the glow is shown statically without
  oscillation.

## Save compatibility

The widget reads only existing state fields and writes none, so no save
migration is required.  Toggling flows through the existing
`Runner.toggle_energy`, which already handles the lockout + notify.

## Tunables

Defined at the top of `ui/energy_widget.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_LABEL_H` | 16 | status + remaining-time row height |
| `_BAR_H` | 10 | gradient energy bar height |
| `_GAP` | 4 | spacing between rows |
| `_LOW_PCT` | 0.20 | below this fraction of max → "depleting" warn |
| `_READY_PCT` | 0.999 | at/above this → "ready" pulse |
| `_PULSE_PERIOD` | 1.6 | seconds per ready-pulse cycle |
| `_WARN_PERIOD` | 0.8 | seconds per warn-glow cycle |
| `_GLOW_PAD` | 4 | padding around the bar for the glow scratch |
