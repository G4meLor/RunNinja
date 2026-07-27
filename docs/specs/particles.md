# Particles — `engine/particles.py`

`ParticleSystem2` is the polished successor to
`assets.ParticleSystem`. It keeps the old `burst` / `trail` /
`update(dt)` / `draw(surf)` API (so a one-line swap works) and adds
ring bursts, spark bursts, particle shapes, gravity variation, color
fade over life, additive-blended glows, and an optional screen-edge
bounce — all **pooled**, with **no per-frame allocations** after
warm-up.

## What's new vs `assets.ParticleSystem`

| feature | old | new |
|---|---|---|
| shapes | plain circle | `circle`, `spark` (elongated diamond along velocity), `star` (5-point) |
| gravity | fixed 200 | per-call `gravity=…` (0 for trails/rings, 200 for bursts, 120 for sparks) |
| color fade | alpha only | alpha fade *and* optional lerp to `fade_color` over life |
| blending | normal blit | `glow=True` particles blit with `pygame.BLEND_RGBA_ADD` (neon-arcade additive) |
| ring burst | — | `burst_ring(x,y,color,radius=…)` — particles placed evenly on a circle |
| spark burst | — | `spark_burst(x,y,color,…)` — elongated sparks aligned with velocity |
| bounce | — | optional `bounce=True` (or system-wide `bounce=`) — reflect off `bounce_bounds` with `damping` |
| pooling | list comprehension each frame | `Particle` objects recycled through a free list; `update` compacts in place (swap-and-pop); scratch surfaces cached per `(shape, size-bucket)` |

## API

```python
class ParticleSystem2:
    def __init__(self, *, bounce: bool = False,
                 bounce_bounds: tuple[int,int,int,int] | None = None,
                 default_glow: bool = False) -> None

    # Compatible with assets.ParticleSystem.burst — same positional args.
    def burst(self, x, y, color, count=12, speed=120, life=0.4, size=3, *,
              shape="circle", gravity=200.0, glow=None,
              fade_color=None, bounce=None, damping=0.6) -> None

    # Compatible with assets.ParticleSystem.trail — same positional args.
    def trail(self, x, y, color, count=1, size=2, *,
              shape="circle", life=0.3, glow=None, fade_color=None) -> None

    # NEW — particles on a circle of `radius`, swelling outward by `expand`.
    def burst_ring(self, x, y, color, radius=60, count=24, life=0.5,
                   size=3, *, shape="star", gravity=0.0, expand=80.0,
                   glow=None, fade_color=None, spin=True) -> None

    # NEW — elongated spark diamonds aligned with velocity. Defaults glow=True.
    def spark_burst(self, x, y, color, count=10, speed=200, life=0.3,
                    size=4, *, gravity=120.0, glow=None, fade_color=None,
                    bounce=None, damping=0.6) -> None

    def update(self, dt: float) -> None
    def draw(self, surf: pygame.Surface) -> None
    def clear(self) -> None
    @property
    def active(self) -> bool
    def __len__(self) -> int
```

`glow=None` means "use the system default"; pass `True`/`False` to
override per-call. Shape constants: `SHAPE_CIRCLE`, `SHAPE_SPARK`,
`SHAPE_STAR` (importable from `engine.particles`).

## Shapes

- **`circle`** — soft disc. Matches the old look; the default for
  `burst` and `trail`.
- **`spark`** — elongated 4-point diamond aligned with the particle's
  velocity vector (so a burst reads as a starburst of streaks). Used by
  `spark_burst` for crits / impact lines.
- **`star`** — 5-point star, rotated by `spin` (which advances with
  `spin_speed`). Default for `burst_ring` so the ring reads as a
  sparkle halo, not a dotted line.

## Drawing & blending

Each particle is drawn onto a cached per-`(shape, size-bucket)`
SRCALPHA scratch surface (cleared with `fill((0,0,0,0))` each draw),
then blitted to the screen. `glow=True` particles blit with
`pygame.BLEND_RGBA_ADD`, so overlapping glows brighten (the neon-arcade
look) and the additive dimming tracks the life fraction (premultiplied
RGB × `life/max_life`). Non-glow particles blit normally with alpha =
`255 × life/max_life`. With `fade_color` set, the RGB lerps from
`color` → `fade_color` over life and the alpha still fades.

## Integration

`ParticleSystem2` **replaces / augments** `assets.ParticleSystem`.
The two share the same `burst` / `trail` / `update` / `draw` shape, so
the swap is one line; the new calls are additive.

### 1. `Game` owns the system

`main.py`, in `Game.__init__` (next to the existing
`self.particles = ParticleSystem()`):

```python
from engine.particles import ParticleSystem2, SHAPE_SPARK, SHAPE_STAR
...
self.particles2 = ParticleSystem2(default_glow=True)
```

(The legacy `self.particles` can stay as a fallback or be removed once
screens migrate; both can coexist.)

### 2. `Game._update_particles` ticks it

`main.py`, in `_update_particles`, next to
`self.particles.update(dt)`:

```python
self.particles2.update(dt)
```

### 3. `GameScreen.draw` draws it on top of the road

`ui/screen_game.py`, after `self.game.particles.draw(surf)` (and
before/with `runner.fx.draw(surf)` / `runner.skill_fx.draw(surf)`):

```python
self.game.particles.draw(surf)
self.game.particles2.draw(surf)      # <<< new
runner.fx.draw(surf)
runner.skill_fx.draw(surf)
```

### 4. Use `burst_ring` for skill AOE

Where a skill hits an area, call `burst_ring` at the AOE center so the
ring reads as the skill's footprint. For the **Shuriken Vortex**
(`shuriken`) — already an expanding ring in `engine/skill_fx.py` — add a
one-shot sparkle ring at the ninja to sell the cast:

`engine/runner.py`, in `Runner.activate_skill`, in the `shuriken`
branch (before/after the damage pass):

```python
elif sid == "shuriken":
    from engine.enemy import _apply_damage
    self.particles2.burst_ring(
        self.ninja.x, self.ninja.y, (180, 130, 255),
        radius=120, count=20, life=0.5, size=3,
        expand=60.0, glow=True)
    for t in self.world.enemies:
        if t.alive:
            _apply_damage(t, self.ninja.auto_damage * 2 * combo_m)
            ...
```

(For `kunai`, a `spark_burst` at each target's impact reads as the
blade connecting; see below.)

### 5. Use `spark_burst` for crits

In the combat damage path, when a hit is a crit, fire a short
`spark_burst` at the impact point so crits pop as a starburst of
streaks (additive by default). The crit hook is `Runner._on_enemy_dmg`
(or `engine.enemy`'s damage callback), which already receives
`(x, y, amount, is_crit=…)`:

`engine/runner.py`:

```python
def _on_enemy_dmg(self, x, y, amount, *, is_crit=False, is_boss=False) -> None:
    self.fx.damage(x, y, amount, crit=is_crit)
    if is_crit:
        self.particles2.spark_burst(x, y, (255, 220, 140),
                                     count=8, speed=180, life=0.3, size=4)
    elif is_boss:
        self.particles2.burst(x, y, (255, 200, 120),
                              count=10, speed=140, life=0.4, size=3,
                              shape="star", glow=True)
```

For the **Kunai Barrage** (`kunai`), a `spark_burst` at each target
marks the blade impact:

```python
for t in targets:
    from engine.enemy import _apply_damage
    _apply_damage(t, self.ninja.tap_damage * 3 * combo_m, is_crit=True)
    self.particles2.spark_burst(t.x, t.y, (255, 120, 110),
                                count=6, speed=160, life=0.25, size=3)
    if not t.alive:
        self._on_enemy_killed(t, combo_m, gold_m,
                              aggregate_bonuses(self.state))
```

### 6. (Optional) screen-edge bounce

Pass `bounce=True` (per-call) or set `bounce=True` on the system for
particles that reflect off `bounce_bounds` (default: the whole window)
with `damping=0.6`. Useful for confetti-style celebrations that should
not vanish off the bottom edge.

## Performance / constraints

- **pygame primitives only.** Every shape is `pygame.draw.circle` /
  `polygon` on a small SRCALPHA scratch, then one `blit` to the screen.
- **pooled.** Dead `Particle` objects return to a free list and are
  reused by the next spawner — no `Particle` is allocated after
  warm-up. `update` compacts the active list in place
  (swap-and-pop), so there is no per-frame list comprehension either.
- **no per-frame allocations in hot loops.** The per-`(shape,
  size-bucket)` scratch surfaces are cached lazily on first draw and
  reused forever; `draw` only `fill`s, `draw`s and `blit`s. The
  scratch cache is keyed by `(shape, size)` so different sizes do not
  share a surface (no per-frame `Surface` resize).
- **bounded counts.** `burst`/`burst_ring`/`spark_burst`/`trail` take
  explicit `count` arguments; keep them modest (8–24). The system is
  O(active) memory.
- **additive blending** is `pygame.BLEND_RGBA_ADD` on the final blit;
  the scratch is premultiplied by the life fraction so glow dimming
  tracks life without a per-pixel alpha multiply.

## Accessibility

Set `ParticleSystem2.default_glow = False` (the default) and pass
`glow=False` on the spawners to render in normal-blend mode. The
additive path is brighter; for reduced-motion / low-flash modes, prefer
non-glow circles with shorter `life`. The bounce option is independent
of glow and can be used with either.
