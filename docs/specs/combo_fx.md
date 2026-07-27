# Combo milestone celebration — integration spec

A new module, `engine/combo_fx.py` (`ComboFxSystem`), adds **combo
milestone celebrations**: when the running combo crosses a threshold
(10, 25, 50, 100, 200) the game fires a big animated banner with the
milestone label, an expanding gold ring radiating from the kill, a gold
particle burst, a brief full-screen flash, and a **milestone gold reward**.

Today the combo readout in `GameScreen.draw` only changes text color at
50/100; this replaces that flat feedback with a punchy, juice-driven
celebration that scales with how hard the milestone is.

All rendering uses pygame primitives, cached theme fonts, fixed effect
pools, and reusable scratch surfaces — zero per-frame allocations once
warm.

## Files

| Path | Role |
|---|---|
| `engine/combo_fx.py` | **New.** `ComboFxSystem` — banner + ring + particles + flash. |
| `engine/runner.py` | Existing. Owns the system, calls `check`/`trigger` on kills, awards milestone gold, ticks the fx. |
| `ui/screen_game.py` | Existing. Calls `runner.combo_fx.draw(surf)` after the combo readout. |
| `theme.py` | Existing. Cached fonts (`font_huge`, `font_lg`) + palette (`C.gold`, `C.coin`) used by the banner. |
| `config.py` | Existing. `WINDOW_W` / `WINDOW_H` / `ROAD_TOP` / `ROAD_H` position the banner. |

## `ComboFxSystem` API

```python
fx = ComboFxSystem()
info   = fx.check(combo)            # pure lookup; dict or None
info   = fx.trigger(combo, x, y, *, gold=None)  # fire the celebration; dict or None
fx.update(dt)                      # advance banner / rings / particles / flash
fx.draw(surf)                      # render rings, particles, banner, flash (in that order)
fx.reset()                         # clear all active FX (call on ascension / new run)
fx.active                          # True if anything is animating (cheap draw gate)
```

- `check(combo)` returns `{"milestone", "label", "gold"}` when `combo` is a
  milestone, else `None`. **No side effects** — the runner uses it both to
  decide whether to fire and to read the base gold before its own
  multipliers.
- `trigger(combo, x, y, *, gold=None)` fires the celebration at the kill
  position `(x, y)`. `gold` overrides the displayed/returned amount — the
  runner passes the **post-multiplier** award so the banner shows what the
  player actually gains. Returns the milestone info (with the effective
  gold), or `None` if `combo` is not a milestone.
- `update` / `draw` are safe to call every frame; `draw` is a cheap no-op
  when `active` is False.

## Milestones

| Combo | Label     | Base gold |
|------:|-----------|----------:|
|    10 | "Nice!"   |       100 |
|    25 | "Combo!"  |       500 |
|    50 | "Fury!"   |     2,500 |
|   100 | "Storm!"  |    15,000 |
|   200 | "Legend!" |   100,000 |

`MILESTONES` and `MILESTONE_GOLD` are exported from
`engine/combo_fx.py`. The runner multiplies the base gold by its
`gold_mult()` (upgrades + evolution bonuses) before awarding and
displaying, so late-game milestones pay out much more.

## `Runner` integration

### Construction (`__init__`)

Add the system alongside the existing FX layer:

```python
from engine.combo_fx import ComboFxSystem

class Runner:
    def __init__(self, state: GameState) -> None:
        ...
        self.fx = FXLayer()
        self.combo_fx = ComboFxSystem()
        ...
```

### Kill handling (`_on_enemy_killed`)

After `self.state.combo += 1` and the best-combo bookkeeping, check for
a milestone and fire. The celebration uses the **kill position** for the
ring/particle origin; the enemy's `x` (with a small vertical offset to sit
on the road) is the natural anchor. Award the milestone gold through the
existing `_award_gold` so it flows into lifetime/today totals too.

```python
def _on_enemy_killed(self, enemy, combo_m, gold_m, evo) -> None:
    ...
    self.state.combo += 1
    self.state.combo_timer = COMBO_WINDOW + ...
    if self.state.combo > self.state.best_combo_ever:
        self.state.best_combo_ever = self.state.combo
    if self.state.combo > self.state.best_combo_today:
        self.state.best_combo_today = self.state.combo
    ...
    # --- combo milestone celebration -----------------------------------
    info = self.combo_fx.check(self.state.combo)
    if info is not None:
        award = info["gold"] * gold_m            # apply run gold mult
        self._award_gold(award)
        self.combo_fx.trigger(self.state.combo, enemy.x, enemy.y, gold=award)
        self.notify(f"{info['label']}  +{int(round(award))} gold", C.gold)
    ...
```

Notes:
- `combo_fx.check` is a pure dict lookup, so it is cheap to call on every
  kill; `trigger` only does real work on the 5 milestone values.
- The milestone gold is **separate from** the per-kill `enemy.gold` award
  that already happens above — it is a bonus on top, so the player is
  rewarded for *reaching* the threshold, not just for the kill that
  crossed it.
- Passing `gold=award` (post-multiplier) makes the banner's
  `"+{gold} gold"` subtext match what the player actually received.
- The `notify(...)` keeps the existing notifications feed in sync so the
  HUD surfaces the haul even if the player looks away from the banner.

### `update(dt)`

Tick the combo fx alongside the existing FX layer (near the end of
`update`, after `self.fx.update(dt)`):

```python
self.fx.update(dt)
self.combo_fx.update(dt)
```

### `reset_for_ascension`

Clear any in-flight celebration when the run resets:

```python
def reset_for_ascension(self) -> None:
    self.world.reset_for_ascension()
    self.ninja = make_ninja(self.state)
    self._refresh_skills()
    self.state.energy = self.state.energy_max
    self.state.energy_active = False
    self.combo_fx.reset()
```

`reset()` is also the right call if the combo ever resets to 0 on death
(the existing respawn block sets `self.state.combo = 0`); a mid-air
banner is fine to let finish, but `reset()` is available if you want a
clean slate.

## `GameScreen` integration

### `draw(surf)`

Call `runner.combo_fx.draw(surf)` **after** the existing combo readout
and notifications, so the celebration overlays the HUD. The flash fills
the whole window, so it must be one of the last things drawn each frame:

```python
# Combo (big, center) — unchanged.
if state.combo >= 1:
    ...
# Notifications — unchanged.
...
# Combo milestone celebration (banner + ring + particles + flash).
runner.combo_fx.draw(surf)
```

The existing combo text color logic (`C.gold` / `C.text_warn` /
`C.text_bad` at 50/100) can stay as-is — the banner is the *celebration*,
the readout is the *status*. They do not conflict.

`update(dt)` needs no change beyond the runner's own `combo_fx.update`
(it is ticked by the runner, not the screen).

## Behavior contract

- **Trigger**: on any kill that brings `state.combo` to exactly a
  milestone value (10/25/50/100/200), the runner fires `combo_fx.trigger`
  and awards `MILESTONE_GOLD[milestone] * gold_mult()`.
- **Banner**: the label scales in from 0.55 → 1.0 over 0.30s
  (`ease_out_cubic`), holds at full size for 0.80s, then fades out over
  0.55s. A drop shadow sits behind it for punch. A subtext line
  (`"Combo x{N}   +{gold} gold"`) sits below the label and fades with it.
- **Ring**: an expanding gold ring (lerping `C.gold` → near-white) radiates
  from the kill position over 0.70s, peaking at 180px radius, thickening
  from 6px down to 2px as it expands.
- **Particles**: 26 gold sparks burst from the kill position with upward
  bias, gravity, and air drag; they fade by life over ~0.5–0.9s.
- **Flash**: a warm full-screen flash (`(255, 235, 180)`, peak 0.45 alpha)
  decays over 0.32s.
- **No-op**: `check` returns `None` for non-milestone combos, so kills
  between thresholds do exactly nothing extra — no allocations, no draws.

## Why no per-frame allocations

- **Particles** live in a fixed pool (`_MAX_PARTICLES = 96`); dead slots
  are recycled via `reset`, and the pool only grows lazily up to the cap.
- **Rings** live in a fixed pool (`_MAX_RINGS = 4`); the oldest slot is
  reused when full.
- **Banner label + shadow** are pre-rendered at `_SCALE_STEPS = 14`
  discrete scale steps per milestone and cached on the system; the draw
  just picks the step for the current intro progress and sets its alpha.
  No `font.render` or `smoothscale` happens per frame.
- **Subtext** (`"Combo x{N}   +{gold} gold"`) is rendered once per
  `trigger` (not per frame) using the cached `font_lg(bold=True)`.
- **Scratch surfaces** (`_ring_scratch`, `_part_scratch`, `_flash_surf`)
  are allocated lazily once, `convert_alpha`-converted, and reused via
  `fill((0,0,0,0))` resets — never re-allocated.
- `font_huge(bold=True)` and `font_lg(bold=True)` are cached by
  `theme._font`, so no `SysFont` calls happen after the first render.

## Tunables

All timing/size constants live at the top of `engine/combo_fx.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_BANNER_INTRO`  | 0.30s | banner scale-in (ease-out) |
| `_BANNER_HOLD`   | 0.80s | banner hold at full scale |
| `_BANNER_FADE`   | 0.55s | banner fade-out |
| `_RING_DUR`      | 0.70s | expanding ring lifetime |
| `_RING_MAX_R`    | 180px | peak ring radius |
| `_FLASH_DUR`     | 0.32s | full-screen flash lifetime |
| `_FLASH_PEAK`    | 0.45  | peak flash alpha fraction |
| `_PARTICLE_COUNT`| 26    | gold particles per burst |
| `_MAX_PARTICLES` | 96    | particle pool size |
| `_MAX_RINGS`     | 4     | ring slot pool size |
| `_SCALE_STEPS`   | 14    | cached banner scale steps |
| `_SCALE_MIN`     | 0.55  | smallest intro scale |

Tune by editing the constants; no other module needs to change. Milestone
thresholds/labels/gold live in the `MILESTONES` and `MILESTONE_GOLD`
dicts at the top of the same file.

## Save compatibility

The fx system is purely visual and holds no persistent state — nothing
to save. It is safe to construct on every runner construction and discard
on exit; effects simply stop if the run is abandoned mid-animation.
Milestone gold, once awarded, is part of `state.gold` /
`state.lifetime_gold` / `state.gold_earned_today` and persists normally.
