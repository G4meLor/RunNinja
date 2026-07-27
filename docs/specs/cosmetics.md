# Cosmetics Shop — integration spec

A new screen, `ui/screen_cosmetics.py` (`CosmeticsScreen`), lets the
player spend **Amber** on cosmetic and convenience items.  It is
intentionally non-power for the three "look" categories (skins,
particles, UI themes) and slightly power-adjacent for the convenience
items (auto-firefly catch, double offline cap) — those are quality-of-life
tweaks, not stat boosts.

## State fields (on `GameState`)

The screen reads/writes two new fields.  They are **not** added to
`core/state.py` in this patch — the screen accesses them via
`getattr`/`setattr` and lazily creates them on first visit, so older
saves keep working.  When you wire them into `GameState` properly, add:

```python
# Cosmetic ids the player has purchased (excludes cost-0 defaults).
cosmetics: set[str] = field(default_factory=set)
# Equipped cosmetic ids -> True.  One per mutex category; convenience
# items toggle freely.
equipped_cosmetics: dict[str, bool] = field(default_factory=dict)
```

`GameState.to_dict` should serialize `cosmetics` as `sorted(...)` (like
`skill_tree`), and `from_dict` should restore it as a `set`.
`equipped_cosmetics` is a plain dict and round-trips through `asdict`
unchanged.

## `data/cosmetics.py` sketch

The screen currently defines its `CosmeticDef` inline.  Lift it into
`data/cosmetics.py` so other modules (engine, assets) can import it:

```python
from dataclasses import dataclass

@dataclass
class CosmeticDef:
    id: str
    name: str
    category: str        # skin | particle | theme | convenience
    cost: int           # amber
    hue: int            # icon accent hue
    desc: str

COSMETICS: list[CosmeticDef] = [CosmeticDef(*r) for r in _ROWS]
BY_ID: dict[str, CosmeticDef] = {c.id: c for c in COSMETICS}
BY_CAT: dict[str, list[CosmeticDef]] = {}  # category -> list
```

Categories and rules:

| category      | equip rule            | notes                                  |
|---------------|-----------------------|----------------------------------------|
| `skin`        | mutually exclusive    | one ninja skin at a time               |
| `particle`    | mutually exclusive    | one combat-particle theme              |
| `theme`       | mutually exclusive    | one UI color theme                     |
| `convenience` | independent toggles    | each can be on/off independently       |

`MUTEX_CATEGORIES = {"skin", "particle", "theme"}`.  Each mutex category
has a cost-0 default that is auto-equipped on first visit so the game
always has a valid look.

## How equipped cosmetics are applied

The screen only *records* what is equipped.  The engine/assets modules
read `state.equipped_cosmetics` to pick the active look.  Sketches:

### Ninja skins (`assets.ninja_surface`)
Add a `skin_id` parameter (default `"skin_shadow"`) and switch the body
+ headband colors:

```python
def ninja_surface(size=64, skin_id="skin_shadow"):
    body, headband, skin = SKIN_PALETTE.get(skin_id, SKIN_PALETTE["skin_shadow"])
    ...
```

`SKIN_PALETTE = {"skin_shadow": ((40,40,60),(220,60,60),(220,180,150)), ...}`.
The game screen passes the equipped skin id:

```python
skin_id = next((c for c in ("skin_shadow","skin_crimson","skin_jade",
                            "skin_gold","skin_void")
                if state.equipped_cosmetics.get(c)), "skin_shadow")
ns = ninja_surface(72, skin_id=skin_id)
```

### Particle themes (`assets.ParticleSystem.burst`)
Map the equipped particle id to a color palette used by `burst`:

```python
PARTICLE_THEMES = {
    "part_sparks":  (255, 220, 120),
    "part_sakura":  (255, 180, 220),
    "part_ember":   (255, 120,  60),
    "part_frost":   (180, 220, 255),
    "part_soul":    (200, 140, 255),
}
# In main.py _update_particles:
theme_id = next((c for c in PARTICLE_THEMES
                 if state.equipped_cosmetics.get(c)), "part_sparks")
col = PARTICLE_THEMES[theme_id]
self.particles.burst(e.x, ly, col, ...)
```

### UI themes (`theme.C`)
The cleanest hook is to add a `set_theme(theme_id)` that swaps the
class-attribute values on `C` (or, better, turn `C` into a module-level
dict the helpers read).  Lightest-touch version:

```python
UI_THEMES = {
    "ui_midnight":  {"bg_top": (12,14,28), "bg_bottom": (24,18,44)},
    "ui_dawn":      {"bg_top": (40,20,30), "bg_bottom": (90,40,30)},
    "ui_forest":    {"bg_top": (12,28,18), "bg_bottom": (20,44,28)},
    "ui_bloodmoon": {"bg_top": (28,10,14), "bg_bottom": (60,18,24)},
}
def apply_ui_theme(state):
    tid = next((t for t in UI_THEMES if state.equipped_cosmetics.get(t)),
               "ui_midnight")
    for k, v in UI_THEMES[tid].items():
        setattr(C, k, v)
```

Call `apply_ui_theme(state)` once after `GameState.load()` in `main.py`
and again whenever the cosmetics screen changes equipment.  The
full-screen gradient cache in `theme.py` is keyed by color, so a theme
swap will simply populate a new cache entry.

### Convenience items

These are read directly in the engine:

* **`conv_auto_firefly`** — in `Runner.update`, after
  `update_fireflies(...)`, auto-catch any firefly whose life is below a
  threshold (or just catch them all each tick) and award gold via the
  existing `catch_firefly` path:

  ```python
  if state.equipped_cosmetics.get("conv_auto_firefly"):
      for f in self.world.fireflies[:]:
          gold = catch_firefly(f, base_gold=..., ...)
          self._award_gold(gold); self.state.fireflies_today += 1
          self.world.fireflies.remove(f)
  ```

* **`conv_double_offline`** — in `core/offline.py`:

  ```python
  cap = OFFLINE_CAP_SECONDS * (2.0 if state.equipped_cosmetics.get("conv_double_offline") else 1.0)
  elapsed = min(elapsed, cap)
  ```

* **`conv_energy_reserve`** — in `Runner.update`, multiply the regen
  rate:

  ```python
  regen_mult = 1.25 if state.equipped_cosmetics.get("conv_energy_reserve") else 1.0
  regen = (1.0 + evo.get("energy_regen", 0.0)) * 0.5 * regen_mult
  ```

* **`conv_quick_tap`** — in `Runner.tap_at`, widen the firefly catch
  radius:

  ```python
  radius = (20 + f.size) * (1.5 if state.equipped_cosmetics.get("conv_quick_tap") else 1.0)
  if abs(f.x - x) < radius and abs(f.y - y) < radius:
      ...
  ```

## Wiring the screen into the game

In `main.py`:

```python
from ui.screen_cosmetics import CosmeticsScreen
...
self.screens["cosmetics"] = CosmeticsScreen(self)
```

And add a nav button in `GameScreen._build_nav`:

```python
("Cosmetics", lambda: self.game.set_screen("cosmetics")),
```

Optionally bind a hotkey in `main.py` (e.g. `pygame.K_c`).

## Save compatibility

Because the screen creates `state.cosmetics` / `state.equipped_cosmetics`
lazily via `getattr` + `setattr`, no save migration is required for the
screen itself.  The only thing to watch: `GameState.to_dict` uses
`asdict`, which will only include the new fields once they are declared
on the dataclass — so until then they are written to the instance but
not persisted.  **Persisting them requires adding the two fields to
`core/state.py`** as shown above.  Until that happens the cosmetics
screen is effectively session-only (purchases reset on reload), which is
fine for a first cut.
