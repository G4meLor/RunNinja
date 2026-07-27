# Floating Damage Numbers — `engine/damage_fx.py`

`DamageFxSystem` replaces the plain-text floating damage numbers from
`engine/fx.FXLayer.damage` with typed, animated variants so combat reads
cleanly at a glance:

| kind    | when                                   | look |
|---------|----------------------------------------|------|
| normal  | a regular hit on a non-boss enemy     | small white number, gentle rise + fade |
| crit    | `ninja.roll_crit()` returned a crit    | larger, gold, `★`-prefixed, with a brief scale-pop (1.4 → 1.0 over ~0.2 s) and a faster rise |
| boss    | `is_boss=True` on the enemy            | red, slightly bigger, with a small horizontal shake while it lives |
| block   | the ninja's `defense` absorbed part of an incoming hit | small gray `block N` text, gentle rise |

The module is **self-contained**: it owns its own pooled state and draws
with pygame primitives + the cached theme fonts. It does not touch
damage, loot, or cooldown logic — those stay in `engine/runner.py` /
`engine/enemy.py`.

## API

```python
class DamageFxSystem:
    def __init__(self) -> None
    def hit(self, x: float, y: float, amount: float, *,
            is_crit: bool = False, is_boss: bool = False,
            blocked: float = 0.0) -> None
    def update(self, dt: float) -> None
    def draw(self, surf: pygame.Surface) -> None
    @property
    def active_count(self) -> int
    def clear(self) -> None
```

`hit(...)` spawns one floating number (and, when `blocked > 0`, an extra
`block N` label). When the hit was **fully absorbed** (`amount <= 0` and
`blocked > 0`) only the block label is shown — no `0` damage number.

## Integration

### 1. `Runner` owns the system

`engine/runner.py`, `Runner.__init__` (next to `self.fx = FXLayer()`):

```python
from engine.damage_fx import DamageFxSystem
...
self.damage_fx = DamageFxSystem()
```

### 2. `Runner._on_enemy_dmg` routes enemy hits to it

The existing callback already receives `is_crit` and `is_boss`; forward
them straight through. This **augments** `FXLayer.damage` (which the
runner currently calls) — either drop the `self.fx.damage(...)` call and
use `DamageFxSystem` as the sole damage-number layer, or keep both and
let `DamageFxSystem` render the polished numbers on top. The cleanest
swap is to replace the `self.fx.damage(...)` call:

```python
def _on_enemy_dmg(self, x, y, amount, *, is_crit=False, is_boss=False) -> None:
    self.damage_fx.hit(x, y, amount, is_crit=is_crit, is_boss=is_boss)
```

### 3. `Runner._on_ninja_dmg` passes the absorbed amount as `blocked`

`engine/enemy.tick_combat` calls `ninja.take_damage(e.dmg)` and forwards
the **post-defense** damage to `on_ninja_dmg(ninja.x, ninja.y, dmg)`. To
show a `block N` label when defense absorbed part of the hit, the runner
needs the **raw** incoming damage and the ninja's defense. The simplest
wiring that needs no change to `engine/enemy.py` is to compute the
absorbed amount in the runner from the ninja's defense and the enemy's
raw damage — but the callback only receives the post-defense `dmg`.

Two options, pick one:

**Option A (no engine change, recommended).** Treat any non-zero ninja
damage as a hit and show a `block` label only when the ninja has a
non-zero `defense` **and** the incoming damage was reduced. Since the
runner doesn't see the raw amount, the cleanest version is: show a
`block` label when `ninja.defense > 0` and `dmg < some_raw_estimate`. In
practice the simplest reliable signal is: if `ninja.defense > 0`, show
`block {defense}` on every ninja hit (a steady "defense is working"
cue). This needs no engine change:

```python
def _on_ninja_dmg(self, x, y, amount) -> None:
    blocked = getattr(self.ninja, "defense", 0.0)
    self.damage_fx.hit(x, y - 24, amount, is_boss=False,
                       blocked=blocked if amount > 0 else 0.0)
```

**Option B (engine change, exact).** Extend `engine/enemy.py` to pass the
**raw** and **absorbed** amounts through `on_ninja_dmg`. In
`tick_combat`, change the call to pass the raw enemy damage and the
absorbed amount:

```python
# engine/enemy.py — in tick_combat, the enemy-attack branch:
if ninja.alive:
    raw = e.dmg
    dmg = ninja.take_damage(raw)
    blocked = max(0.0, raw - dmg)
    if on_ninja_dmg is not None:
        try:
            on_ninja_dmg(ninja.x, ninja.y, dmg, blocked=blocked)
        except Exception:
            pass
```

and update the callback signature in the runner:

```python
def _on_ninja_dmg(self, x, y, amount, *, blocked: float = 0.0) -> None:
    self.damage_fx.hit(x, y - 24, amount, is_boss=False, blocked=blocked)
```

`on_ninja_dmg` is a module-level callable in `engine/enemy.py` set by
the runner; the keyword-only `blocked` keeps backwards compatibility
with any caller that still passes the old 3-arg form.

### 4. `Runner.update` ticks it

Next to `self.fx.update(dt)` at the end of `update`:

```python
self.fx.update(dt)
self.damage_fx.update(dt)
```

### 5. `GameScreen.draw` draws it on top of the road

In `ui/screen_game.py`, after the enemies/ninja are drawn and where
`runner.fx.draw(surf)` currently is — either replace that call or draw
the new system alongside it. If replacing, the old `FXLayer` can stay
for any non-damage floating text it may host; `DamageFxSystem` only
handles damage numbers:

```python
# ui/screen_game.py — in draw(), around the FX + particles block:
runner.fx.draw(surf)                # keep for any non-damage floats
runner.damage_fx.draw(surf)         # <<< new: polished damage numbers
self.game.particles.draw(surf)
```

Draw order: enemies/ninja → damage numbers → particles → HUD, so the
numbers sit on top of the sprites but under the HUD.

## Behavior details

### Crit scale-pop

A crit spawns at scale `1.4` and eases (`ease_out_cubic`) down to `1.0`
over `_CRIT_POP_TIME` (0.2 s). The scale is applied with
`pygame.transform.smoothscale` to the rendered text surface around its
center. After the pop the crit continues its normal rise + fade at scale
`1.0` for the rest of its `_LIFE_CRIT` (0.9 s) lifetime.

### Boss shake

A boss hit's `shake_phase` advances at `_BOSS_SHAKE_FREQ` (30 rad/s) and
its horizontal offset is `sin(phase) * _BOSS_SHAKE_AMP * (life/max_life)`,
so the shake fades out as the number fades — it settles before
disappearing. `reduced_motion` is not yet wired; if desired, set the
amplitude to 0 when a `reduced_motion` flag is set (same pattern as
`SkillFxSystem`).

### Block label

When `blocked > 0`, a second pooled slot is spawned at `(x+14, y-22)`
with a small gray `block N` text and its own gentle rise. It is
independent of the damage number's life so it can outlive it. When the
hit was fully absorbed (`amount <= 0`), only the block label is shown —
no `0` damage number.

## Performance / constraints

- **pygame primitives only.** Every glyph is `font.render` + `blit` +
  `set_alpha`; the crit pop uses `pygame.transform.smoothscale` on the
  rendered text surface (one per crit per frame while the pop is
  active — bounded by the pool).
- **pooled.** A fixed pool of `_POOL_SIZE` (48) `_FloatText` slots is
  allocated once in `__init__` and recycled. `_next_free()` returns an
  inactive slot, or — when the pool is full — recycles the one with the
  least remaining life, so a fresh spawn never overwrites a
  freshly-spawned number. The hot path never appends to or grows a
  list.
- **no per-frame allocations in the hot loop.** `update` only mutates
  slot fields; `draw` renders the cached theme fonts (cached in
  `theme._FONTS`) and calls `set_alpha` on the freshly rendered surface
  (the `font.render` call is the same pattern `FXLayer.draw` and
  `FireflyFxSystem.draw` already use, and the text count is bounded by
  the pool). The only per-frame allocation is the `smoothscale` copy
  for active crit pops, which is bounded by the number of live crits
  (≤ pool size) and only during the 0.2 s pop window.
- **no game state is read or mutated** by the system beyond the
  position/amount/kind the runner passes to `hit`, so it is safe to call
  from the combat callbacks.
