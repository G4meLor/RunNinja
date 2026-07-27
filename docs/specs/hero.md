# Hero / Ninja Loadout — integration spec

A new screen, `ui/screen_hero.py` (`HeroScreen`), is the ninja's
character sheet: it shows a large sprite, the current ascension tier +
stat multiplier, all effective combat stats (tap damage, auto damage,
attack speed, crit chance, crit dmg, max HP, defense), a per-source
breakdown of where each stat's power comes from (base + run upgrades +
skill tree + equipped pets + ascension tier), the equipped pets row,
and an ascension-tier ladder mini-view.

The screen reads ninja stats live every frame via
`engine.ninja.compute_ninja_stats(state)` and
`core.bonuses.aggregate_bonuses(state)`, so the numbers always reflect
the current run — no caching, no new state, no save-schema change.

## Files

| Path | Role |
|---|---|
| `ui/screen_hero.py` | New. `HeroScreen(game)` with `handle` / `update` / `draw`. |
| `ui/screen_game.py` | Existing. Add a "Hero" nav button in `_build_nav`. |
| `main.py` | Existing. Register the screen in `self.screens`; optionally bind a hotkey. |
| `engine/ninja.py` | Existing. `compute_ninja_stats`, `_upgrade_value`, `_ascend_tier_mult`. |
| `core/bonuses.py` | Existing. `aggregate_bonuses` — the combined skill-tree + pet effect dict. |
| `data/skill_tree.py` | Existing. `NODES`, `BY_ID` — source of the skill-tree breakdown. |
| `data/pets.py` | Existing. `BY_ID`, `pet_bonus` — source of the pet breakdown. |
| `assets.py` | Existing. `ninja_surface`, `pet_surface` — cached sprite factories. |
| `theme.py` | Existing. Cached fonts + palette. |
| `config.py` | Existing. `ASCEND_TIERS`, `TAP_UPGRADE_DEFS`, window geometry. |

## `HeroScreen` API

```python
screen = HeroScreen(game)
screen.handle(event)   # back button
screen.update(dt)      # button hover
screen.draw(surf)      # full screen render
```

`HeroScreen` is self-contained — it reads `game.state` and
`game.runner.ninja` directly every frame, so no wiring beyond
construction and the nav button is required.

## Layout

- **Title** at the top: "Hero" + subtitle.
- **Left panel** (`Rect(40, 100, 360, 370)`): a large 192px ninja
  sprite (scaled once from the 64px cached `assets.ninja_surface` and
  held in `self._ninja_big`), the current ascension tier name, the stat
  multiplier (`x1.00` at Mortal), the ascension count, and a live HP
  bar (`ninja.hp / ninja.max_hp`, using `game.runner.ninja`).
- **Stat table** (`Rect(420, 100, 820, 370)`): one row per effective
  stat — label on the left, big colored value on the right, and a
  compact per-source breakdown underneath. The seven rows are:
  `tap_damage`, `auto_damage`, `attack_speed`, `crit_chance`,
  `crit_dmg`, `max_hp`, `defense`. Each value is formatted (HP and
  damage as compact integers via `format_number`, attack speed as
  `x.xx/s`, crit chance as `xx.x%`, crit dmg as `x.xxx`).
- **Ascension ladder** (`Rect(40, 490, 1200, 60)`): a mini-view of all
  7 `ASCEND_TIERS` as equal-width slots; the current tier is filled
  with the tier accent, past tiers are dimmed, future tiers are
  muted. Each slot shows the tier name and `x{mult}`.
- **Equipped pets** (`Rect(40, 560, 1200, 90)`): up to 3 cards showing
  the equipped pet's sprite, name, bond level, and current bonus
  value (e.g. "+3.0% Crit Dmg"). Empty slots show "Empty".
- **Back button** at the bottom-left returns to the `"game"` screen.

## Per-source breakdown

For each stat the breakdown string lists the contributing sources in
order, mirroring the `compute_ninja_stats` formula in
`engine/ninja.py`:

| Stat | Sources |
|---|---|
| Tap Damage | base 10 + `tap_power` upgrade + `tap_mult` upgrade% + skill `tap_pct`% + pet `tap_pct`% + tier multiplier |
| Auto Damage | base 8 + `auto_attack` upgrade + skill `atk_pct`% + pet `atk_pct`% + tier multiplier |
| Attack Speed | base 1.00/s + skill `speed_pct` (×0.5) + pet `speed_pct` (×0.5) |
| Crit Chance | base 5% + `crit_chance` upgrade + skill `crit_pct`% + pet `crit_pct`% |
| Crit Damage | base 1.50x + `crit_dmg` upgrade + skill `crit_dmg_pct`% + pet `crit_dmg_pct`% |
| Max HP | base 100 + `vitality` upgrade + skill `godai_water`% + pet `godai_water`% + tier multiplier |
| Defense | `defense` upgrade (flat) |

The skill-tree and pet contributions are split out by re-deriving them
from `data.skill_tree.NODES` (filtering by `state.skill_tree`) and
`data.pets.BY_ID` (filtering by `state.equipped_pets` + bond), so the
breakdown matches `aggregate_bonuses` exactly while attributing each
contribution to its source.

## `GameScreen` integration — add a "Hero" nav button

`ui/screen_game.py` builds its top-right nav rail in `_build_nav`.
Prepend one entry so a "Hero" button appears at the leftmost end of
the row (the rail lays out right-to-left):

```python
def _build_nav(self) -> None:
    y = 8
    x = cfg.WINDOW_W - 8
    labels = [
        ("Records", lambda: self.game.set_screen("records")),
        ("Settings", lambda: self.game.set_screen("settings")),
        ("Quests", lambda: self.game.set_screen("quests")),
        ("Pets", lambda: self.game.set_screen("pets")),
        ("Skills", lambda: self.game.set_screen("skilltree")),
        ("Upgrades", lambda: self.game.set_screen("upgrades")),
        ("Buildings", lambda: self.game.set_screen("buildings")),
        ("Ascend", lambda: self.game.set_screen("ascend")),
        ("Hero", lambda: self.game.set_screen("hero")),   # NEW
    ]
    for label, cb in reversed(labels):
        w = 78
        x -= w + 6
        btn = Button((x, y, w, 32), label, on_click=cb)
        self.nav_buttons.insert(0, btn)
```

The existing 78px button slots fit one more without any width or
position changes.

## `main.py` integration — register the screen

Add the import and the `self.screens` entry:

```python
from ui.screen_hero import HeroScreen
# ...
self.screens = {
    # ... existing entries ...
    "hero": HeroScreen(self),
}
```

Optionally bind a hotkey (e.g. `K_h`) in the `KEYDOWN` handler:

```python
elif event.key == pygame.K_h:
    self.set_screen("hero")
```

## Constraints honored

- Pygame primitives only (rects, circles, lines, polygons); no
  external image assets.
- Cached `theme` fonts (`font_xs` / `font_sm` / `font_md` /
  `font_lg` / `font_xl`); no per-frame `SysFont` calls.
- The large ninja sprite is scaled once from the cached
  `assets.ninja_surface(64)` and stored in `self._ninja_big`; the
  pet sprites use the cached `assets.pet_surface`. No per-frame
  surface allocations in the hot path.
- Reads `state` and `runner.ninja` directly; no new state, no
  save-schema change.
