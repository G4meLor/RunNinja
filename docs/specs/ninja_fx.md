# Ninja Attack FX — `engine/ninja_fx.py`

The ninja currently just bobs; `ninja.slash_anim` is a timer with no
visible slash. `NinjaFxSystem` makes the ninja **visibly slash** on tap
and auto-attack: a katana arc/trail sweeps from the ninja to the target,
the ninja lunges toward the target and eases back, and a hit spark
flares on the enemy.

The system is pure state + pygame primitives, with **no per-frame
allocations** in the hot loop: each arc owns one SRCALPHA overlay created
at spawn time (inside `on_slash`, which runs on tap / auto-attack — not in
`update` / `draw`), and `draw` only `fill`s, `draw`s, and `blit`s. The
Bezier points and spark-ray directions are pre-computed once per arc.

## Files

| Path | Role |
|---|---|
| `engine/ninja_fx.py` | **New.** `NinjaFxSystem` — slash arcs + lunge + hit sparks. |
| `engine/runner.py` | Existing. Owns the system, calls `on_slash` from `_on_enemy_dmg`, ticks it in `update`. |
| `ui/screen_game.py` | Existing. Applies `lunge_offset()` to the ninja's blit position, draws the arcs after the ninja. |
| `engine/ninja.py` | Existing. `Ninja.x` / `Ninja.y` / `Ninja.slash_anim` (read by the system; `slash_anim` becomes redundant once the arc is visible). |
| `config.py` | Existing. `ROAD_TOP` / `ROAD_H` position the lane Y the arcs use. |
| `theme.py` | Existing. `C.gold` for crit arcs/sparks. |

## `NinjaFxSystem` API

```python
fx = NinjaFxSystem()
fx.on_slash(ninja, target_x, target_y, is_crit=False)  # spawn arc + lunge + hit spark
fx.update(dt)                                          # animate arcs + lunge return
fx.draw(surf)                                          # render arcs + hit sparks
fx.lunge_offset() -> tuple[float, float]               # (dx, dy) to add to ninja render pos
fx.active                                              # True if any arc or lunge is animating
fx.clear()                                             # drop everything (ascension / new run)
fx.reduced_motion: bool                                # skip the lunge when True
```

- `on_slash` reads only `ninja.x` / `ninja.y` (the leading hand sits at
  `x+14, y+14`) and the target position; it never mutates the ninja or
  the enemy. Safe to call before the renderer runs.
- `lunge_offset()` returns the current `(dx, dy)` the screen should add
  to the ninja's blit position; it eases back to `(0, 0)` over
  `_LUNGE_DUR` (0.22 s) with a quadratic ease-out, so the ninja snaps
  forward then settles back. The vertical component is clamped to
  `±_LUNGE_Y_CAP` (8 px) so the ninja doesn't dip off the road.
- `draw` is a cheap no-op when `active` is False.

## What the player sees

On every tap and auto-attack hit (and skill-damage hit — see below):

1. **Katana arc/trail** — a curved polyline (quadratic Bezier) from the
   ninja's leading hand to the target. It sweeps along its path over
   `_SWEEP_TIME` (0.10 s) with a bright leading-edge dot at the tip, then
   the full arc fades over the remaining life (`_ARC_LIFE` 0.28 s normal,
   `_ARC_LIFE_CRIT` 0.34 s crit). The arc bulges perpendicular to the
   line (upward, an overhead chop read) by `_SWEEP_NORMAL` (34 px) or
   `_SWEEP_CRIT` (58 px) for crits. A thin inner core (`hi_color`) sits
   on top of the outer arc for a shiny edge.
2. **Lunge** — the ninja's render position shifts toward the target by
   `_LUNGE_MAX` (22 px) or `_LUNGE_MAX_CRIT` (30 px) for crits, then
   eases back over 0.22 s. The screen reads `lunge_offset()` each frame.
3. **Hit spark** — once the sweep reaches the target, an expanding ring
   (`_SPARK_R_MAX` 22 px normal / 30 px crit) + `_SPARK_RAYS` (7)
   radiating star-burst lines fade out over the post-sweep life.

Crit arcs are **gold** (`C.gold`) and bigger; normal arcs are **cool
steel** (`(230, 240, 255)`). Hit sparks match: gold for crits, warm white
for normal hits.

## Integration

### 1. `Runner` owns the system

`engine/runner.py`, `Runner.__init__` (next to `self.fx = FXLayer()`):

```python
from engine.ninja_fx import NinjaFxSystem
...
self.fx = FXLayer()
self.ninja_fx = NinjaFxSystem()
```

### 2. `Runner._on_enemy_dmg` fires the slash

The runner already wires `engine.enemy.on_enemy_dmg` to
`Runner._on_enemy_dmg` (line 44), and `_apply_damage` calls that callback
on **every** enemy damage event — tap (`engine.enemy.tap` →
`_apply_damage`), auto-attack (`tick_combat` → `_apply_damage`), and the
active-skill damage paths (`Runner.activate_skill` → `_apply_damage`).
So a single call in `_on_enemy_dmg` covers tap + auto-attack (the
requirement) without editing `engine/enemy.py`:

```python
def _on_enemy_dmg(self, x, y, amount, *, is_crit=False, is_boss=False) -> None:
    self.fx.damage(x, y, amount, crit=is_crit)
    # Katana slash arc + lunge + hit spark. Fires on tap, auto-attack,
    # and skill damage (the slash is a fine accompaniment to the skill
    # visuals; the lunge reinforces that the ninja is attacking).
    self.ninja_fx.on_slash(self.ninja, x, y, is_crit=is_crit)
```

`x, y` is the enemy's lane position (the screen sets `enemy.y` each frame
to `ly + 8 + oy`; `on_slash` uses it as the arc terminus + spark anchor).
`self.ninja.x` / `self.ninja.y` are the ninja's current render position
(the screen sets `ninja.y` in `draw`; on the very first frame before the
screen has run, `on_slash` falls back to the lane base so the arc still
lands roughly on the ninja).

> **Note:** because this routes through `_on_enemy_dmg`, skill damage
> (kunai / shuriken) also fires a slash arc + lunge. This is intentional
> and looks good — the ninja is attacking, so the lunge + arc reinforce
> it. If you want skill hits to skip the slash, gate the call on a
> source flag threaded through `_apply_damage` (a larger change) or move
> the `on_slash` call into `Runner.tap` + a new auto-attack callback in
> `tick_combat` (which would require editing `engine/enemy.py`).

### 3. `Runner.update` ticks the system

Next to `self.fx.update(dt)` at the end of `update`:

```python
self.fx.update(dt)
self.ninja_fx.update(dt)
```

Also tick it in `Runner.update_fx` (the off-screen path, line 313) so the
arcs keep animating while the player browses other screens:

```python
def update_fx(self, dt: float) -> None:
    self.fx.update(dt)
    self.ninja_fx.update(dt)
```

### 4. `GameScreen.draw` applies the lunge + draws the arcs

In `ui/screen_game.py`, in the ninja block (lines 160–172), add the lunge
offset to the ninja's blit position; after the ninja is drawn, call
`runner.ninja_fx.draw(surf)` so the arcs overlay the ninja + enemies:

```python
# Ninja.
from assets import ninja_surface
ns = ninja_surface(72)
bob = math.sin(runner.ninja.bob * 4) * 2
nx = 180 + ox
ny = ly - 30 + bob + oy
runner.ninja.y = ny
# Lunge offset from the ninja FX system (eases back to 0).
ldx, ldy = runner.ninja_fx.lunge_offset()
nx += ldx
ny += ldy
if not runner.ninja.alive:
    gs = ns.copy()
    gs.fill((10, 10, 20, 120), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(gs, gs.get_rect(midbottom=(nx, ny + 50)))
else:
    surf.blit(ns, ns.get_rect(midbottom=(nx, ny + 50)))
if runner.ninja.max_hp > 0:
    br = pygame.Rect(nx - 24, ny - 16, 48, 5)
    draw_bar(surf, br, runner.ninja.hp / runner.ninja.max_hp,
             fill=C.hp, bg=C.hp_bg, border=C.panel_border)
```

Then after the existing FX + particles pass (lines 184–186), draw the
slash arcs + hit sparks on top of the road:

```python
# FX + particles.
runner.fx.draw(surf)
self.game.particles.draw(surf)
runner.ninja_fx.draw(surf)      # <<< new: katana arcs + hit sparks
```

The arcs use the same lane Y and ninja X the screen uses
(`_NINJA_X = 180`, `_LANE_Y = ROAD_TOP + ROAD_H//2 - 2`), so they line
up with the drawn ninja + enemies without any coordinate plumbing. The
lunge offset is applied only to the ninja sprite (not the HP bar above
it, which already moves with `nx`/`ny` — so the bar lunges with the
ninja, which reads as the whole ninja leaning into the slash).

### 5. (Optional) reduced motion + ascension reset

Wire the accessibility flag once (e.g. in `Runner.__init__` or from
`GameScreen`):

```python
self.ninja_fx.reduced_motion = state.reduced_motion
```

With `reduced_motion = True` the lunge is skipped (the ninja stays
planted); the arcs + hit sparks still play — they are brief flashes, not
unsettling motion. `Game.shake` is not triggered by this system.

In `Runner.reset_for_ascension`, clear any in-flight arcs + lunge:

```python
def reset_for_ascension(self) -> None:
    self.world.reset_for_ascension()
    self.ninja = make_ninja(self.state)
    self._refresh_skills()
    self.state.energy = self.state.energy_max
    self.state.energy_active = False
    self.ninja_fx.clear()
```

## Performance / constraints

- **pygame primitives only.** Every shape is `pygame.draw.lines` /
  `pygame.draw.circle` / `pygame.draw.line` on a small per-arc SRCALPHA
  overlay, then one `blit` to the screen.
- **no per-frame allocations in hot loops.** Each arc's overlay surface
  is created once in `__post_init__` (at *spawn* time, inside `on_slash`,
  which runs on tap / auto-attack — not in `update` / `draw`). The
  Bezier points and spark-ray directions are pre-computed once per arc
  and stored on the instance; `draw` only `fill`s, `draw`s, and `blit`s —
  none of those allocate.
- **bounded list.** Arcs are culled each tick (`alive` is `life > 0`),
  so the list is O(active slashes) — typically 1–2 at a time (one tap +
  the auto-attack rate of ~1–2/s).
- **no enemy / ninja state is mutated** by the system beyond the
  positions it reads, so it is safe to call before the renderer runs.

## Tunables

All timing / size constants live at the top of `engine/ninja_fx.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_ARC_LIFE`        | 0.28 s | normal arc lifetime |
| `_ARC_LIFE_CRIT`   | 0.34 s | crit arc lifetime |
| `_SWEEP_TIME`      | 0.10 s | arc sweep reaches target at this t |
| `_SWEEP_NORMAL`    | 34 px  | normal arc perpendicular bulge |
| `_SWEEP_CRIT`      | 58 px  | crit arc perpendicular bulge |
| `_ARC_SEGMENTS`    | 14     | Bezier sample points per arc |
| `_ARC_WIDTH`       | 3      | normal polyline thickness |
| `_ARC_WIDTH_CRIT`  | 4      | crit polyline thickness |
| `_SPARK_R_MAX`     | 22 px  | normal hit-spark ring peak radius |
| `_SPARK_R_MAX_CRIT`| 30 px  | crit hit-spark ring peak radius |
| `_SPARK_RAYS`      | 7      | radiating spark lines |
| `_SPARK_RAY_LEN`   | 14 px  | spark ray length beyond the ring |
| `_LUNGE_DUR`       | 0.22 s | lunge return time |
| `_LUNGE_MAX`       | 22 px  | peak lunge distance (normal) |
| `_LUNGE_MAX_CRIT`  | 30 px  | peak lunge distance (crit) |
| `_LUNGE_Y_CAP`     | 8 px   | vertical lunge clamp |

Tune by editing the constants; no other module needs to change.

## Save / state compatibility

No `GameState` fields are added. The `NinjaFxSystem` is transient
(runtime-only), so no save migration is needed. `ninja.slash_anim` in
`engine/ninja.py` becomes redundant once the arc is visible — it can be
left in place (harmless timer) or removed in a follow-up cleanup.

## Wiring checklist

1. `engine/runner.py` — `from engine.ninja_fx import NinjaFxSystem`;
   create `self.ninja_fx = NinjaFxSystem()` in `__init__`; call
   `self.ninja_fx.on_slash(self.ninja, x, y, is_crit=is_crit)` in
   `_on_enemy_dmg`; call `self.ninja_fx.update(dt)` in `update` and in
   `update_fx`; call `self.ninja_fx.clear()` in `reset_for_ascension`;
   optionally set `self.ninja_fx.reduced_motion = state.reduced_motion`.
2. `ui/screen_game.py` — in `draw`, add `runner.ninja_fx.lunge_offset()`
   to the ninja's `nx`/`ny` before blitting; call
   `runner.ninja_fx.draw(surf)` after `self.game.particles.draw(surf)`.
