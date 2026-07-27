# Pet Detail + Bonding Panel — integration spec

A new module, `ui/pet_detail.py` (`PetDetailPanel`), turns the Pets
screen's flat "click a card to toggle equip" interaction into a proper
detail view: selecting a pet shows its large sprite, buff description,
current bond level with a progress bar, the bonus value at the current
bond, a **Feed** button that spends gold to raise bond, and an
**Equip / Unequip** button.

The panel is self-contained: it owns its two buttons, reads state
through the `game` handle, and persists changes via `state.save()`.
All rendering uses pygame primitives + the cached theme fonts + the
cached `assets.pet_surface`. No per-frame allocations happen in `draw`
once the panel is warm.

## The panel

`PetDetailPanel` exposes:

| method | purpose |
|--------|---------|
| `__init__(rect, game)` | construct with the panel rect and the game handle |
| `set_pet(pid)` | select which pet to show; `None` hides the panel |
| `handle(event) -> bool` | consume clicks on the panel / buttons; returns True if the event was consumed so the grid underneath does not also toggle equip |
| `update(dt)` | refresh button labels / enabled state each frame |
| `draw(surf)` | render the panel; no-op when no pet is set |
| `active` | property — True while a pet is selected |

The panel is **inert** until `set_pet` is called with a real pet id.
`handle` returns True whenever it consumes a click inside the panel
rect (so the grid card underneath does not also toggle equip) or on one
of its buttons.

## Feed economy

Bond ranges `0..10`. Raising bond costs gold scaled with the current
bond level:

```python
feed_cost(bond) = round(100 * max(bond, 1) ** 1.5)
```

The `max(bond, 1)` clamp keeps the first feed from being free
(``0 ** 1.5 == 0``); the curve then follows the spec for bond >= 1.

| current bond | cost to feed | cumulative |
|--------------|-------------|-----------|
| 0 | 100 | 100 |
| 1 | 100 | 200 |
| 2 | 283 | 483 |
| 3 | 520 | 1003 |
| 4 | 800 | 1803 |
| 5 | 1118 | 2921 |
| 6 | 1470 | 4391 |
| 7 | 1852 | 6243 |
| 8 | 2263 | 8506 |
| 9 | 2700 | 11206 |

`feed_cost` is exported from `ui/pet_detail.py` so other modules can
reuse the curve (e.g. a future "feed x10" button).

Feeding deducts gold, increments `state.pets[pid]` (capped at 10), and
saves. The bonus value at the new bond takes effect immediately through
`core.bonuses.aggregate_bonuses`, which the engine reads each frame.

## Wiring into `ui/screen_pets.py`

### 1. Construct the panel

`PetsScreen.__init__` builds the panel once, sized to sit to the right
of the existing grid (or below it). A right-side column fits the
1280x720 layout cleanly:

```python
from ui.pet_detail import PetDetailPanel

class PetsScreen:
    def __init__(self, game) -> None:
        ...
        # Detail panel on the right; grid stays on the left.
        panel_rect = pygame.Rect(cfg.WINDOW_W - 320, 130, 288,
                                 cfg.WINDOW_H - 220)
        self.detail = PetDetailPanel(panel_rect, game)
```

### 2. Selection replaces toggle-equip

`PetsScreen.handle` currently calls `_toggle_equip(pid)` on any grid
click. Replace that with selection: clicking a card selects it and
shows the detail panel; the panel's own buttons handle equip / feed.

```python
def handle(self, event):
    # Detail panel gets the event first; if it consumes, we're done.
    if self.detail.active:
        if self.detail.handle(event):
            return
    for b in self.buttons:
        b.handle(event)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        for pid, r in self.pet_rects.items():
            if r.collidepoint(event.pos):
                self.detail.set_pet(pid)
                break
```

`PetDetailPanel.handle` returns True for any click inside its rect, so
a click on the panel never also toggles the underlying card. A click on
a grid card simply selects it (and the panel's Equip/Unequip button
does the actual equip toggle).

### 3. Update

```python
def update(self, dt):
    state = self.game.state
    self.btn_pull.enabled = gacha.can_afford(state)
    self.btn_pull10.enabled = gacha.can_afford_10(state)
    for b in self.buttons:
        b.update(dt)
    self.detail.update(dt)
    if self.anim_result:
        self.anim_t += dt
        if self.anim_t > 2.0:
            self.anim_result = None
```

### 4. Draw

Draw the panel after the grid so it sits on top. The panel draws
nothing when no pet is selected, so it is safe to call unconditionally.

```python
def draw(self, surf):
    ... existing grid ...
    # Detail panel (right column).
    self.detail.draw(surf)
    # Pull animation on top of everything.
    if self.anim_result:
        self._draw_pull_anim(surf)
    for b in self.buttons:
        b.draw(surf)
```

### 5. Grid layout shift

The grid currently starts at `grid_x = 80` and lays out 5 columns of
200px cards + 12px gaps, totaling `5*200 + 4*12 = 1048px`, ending at
`80 + 1048 = 1128`. The right panel starts at `WINDOW_W - 320 = 960`,
so the grid and panel overlap. Shrink the grid to 4 columns or move it
left so the two coexist:

```python
# Option A: 4 columns, grid stays at grid_x = 80.
cols = 4
# Option B: keep 5 columns, shift grid left:
grid_x = 16
```

Either way, the grid must not draw under the panel. The cleanest option
is to keep 5 columns but shrink the card width to ~180 and tighten the
gap so the grid ends before the panel:

```python
card_w, card_h = 180, 90
cols = 5
gap = 10
grid_x = 16
# grid ends at 16 + 5*180 + 4*10 = 16 + 900 + 40 = 956 < 960
```

## What the panel shows

For a **locked** pet: the sprite, name, type, and a "Locked" banner
with the unlock condition (e.g. `skill:ab_rope` or `ascensions:5`).
The Feed and Equip buttons are drawn but disabled.

For an **unlocked but not owned** pet: the sprite, name, type, a "Not
owned yet" banner, and the buff description. Buttons are drawn but
disabled.

For an **owned** pet:

  * large sprite (96px, cached `pet_surface(pid, hue, 96)`)
  * name + type
  * buff description (one line, e.g. "+5% gold from enemies per bond.")
  * flavor `desc` from the pet definition
  * "Bond N/10" label + a soul-colored progress bar
  * "Bonus" label + the current bonus value (e.g. "+25%")
  * equip state tag ("EQUIPPED" in gold, or "not equipped" muted)
  * **Feed** button — label includes the cost: `Feed (283 g)`;
    disabled at max bond or when unaffordable
  * **Equip / Unequip** button — toggles `state.equipped_pets`

## Buff descriptions

`ui/pet_detail._buff_desc(pet)` maps each `buff_key` to a human-readable
line. The mapping mirrors the engine's effect-key semantics so the
panel describes what the pet actually does:

| buff_key | description |
|----------|-------------|
| `gold_pct` | "+X% gold from enemies per bond." |
| `crit_dmg_pct` | "+X% crit damage per bond." |
| `speed_pct` | "+X% move speed per bond." |
| `gps_pct` | "+X% building gold/sec per bond." |
| `upgrade_cost_pct` | "-X% upgrade cost per bond." |
| `building_cost_pct` | "-X% building cost per bond." |
| `quest_reward_pct` | "+X% quest rewards per bond." |
| `firefly_spawn` | "+X% firefly spawn rate per bond." |
| `firefly_gold` | "+X% firefly gold per bond." |
| `firefly_value` | "+X% firefly value per bond." |
| `energy_regen` | "+X% energy regen per bond." |
| `elixir_pct` | "+X% elixir gain per bond." |

The bonus value at the current bond is computed via
`data.pets.pet_bonus(pet, bond)` and formatted as a signed percent for
the percentage keys, or a signed flat value otherwise.

## Performance / constraints

- **pygame primitives only.** The panel is a `draw_panel` rect + text
  + a bar + two `Button` widgets. No external image assets.
- **cached sprite.** `assets.pet_surface(pid, hue, size)` is cached by
  `(pid, size)`; the panel requests the 96px size directly, so no
  per-frame `smoothscale` is needed. The panel also keeps its own
  `(pid, size) -> Surface` cache as a second layer, so even the dict
  lookup is stable across frames.
- **cached fonts.** All text uses `theme.font_*` helpers, which cache
  by `(size, bold)` in `theme._FONTS`.
- **no per-frame allocations in `draw`.** The only objects created per
  call are the small `pygame.Rect` literals used to lay out the bar and
  text positions — those are cheap and local. Buttons are stored on
  the instance and updated in place.
- **no per-frame allocations in `update`.** Button labels are mutated
  in place; no new `Button` objects are created.

## Save compatibility

The panel reads and writes only existing state fields:

- `state.pets[pid]` — bond level (already used by gacha and bonuses)
- `state.equipped_pets` — equip list (already used by `equip_pet` /
  `unequip_pet`)
- `state.gold` — gold currency (deducted on feed)

No new state fields are introduced, so no save migration is required.
`state.save()` persists the bond, equip list, and gold in one call.

## Tunables

The feed curve is defined at the top of `ui/pet_detail.py`:

| constant | default | meaning |
|----------|---------|---------|
| `BOND_MAX` | 10 | maximum bond level |
| `FEED_COST_BASE` | 100.0 | gold coefficient in the cost curve |
| `FEED_COST_EXP` | 1.5 | exponent in the cost curve |

`feed_cost(bond)` is exported so other modules can reuse the exact
curve (e.g. a future "feed x10" or "feed to max" button).
