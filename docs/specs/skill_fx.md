# Active-Skill VFX — `engine/skill_fx.py`

Dramatic visuals for the four active skills (Kunai Barrage, Shuriken
Vortex, Rope Hook, Speed Step). The module is **self-contained**: it owns
its own short-lived effects and draws them with pygame primitives + the
cached sprite helpers from `assets.py`. It does **not** touch damage,
loot, or cooldown logic — those stay in `engine/runner.py`.

## Effects

| skill    | effect class     | what it draws |
|----------|------------------|---------------|
| `kunai`  | `KunaiEffect`    | one elongated-diamond blade per target (nearest 5 alive enemies), flying from the ninja's leading hand to the enemy with a 3-segment fading trail, then a radial impact flash. ~0.34 s. |
| `shuriken` | `ShurikenEffect` | an expanding ring AOE centred on the ninja: a filled shockwave disc + three concentric rings + four orbiting shuriken sprites (pre-rotated into a 24-bucket cache) riding the leading edge. ~0.6 s. |
| `rope`   | `RopeEffect`     | a zig-zag grappling line that shoots out (`ease_out_cubic`) to the weakest non-boss enemy, a hook triangle at the tip, then a pull-back flash at the target. ~0.5 s. |
| `speed`  | `SpeedEffect`    | motion lines streaking backward from the ninja + three pre-dimmed ninja afterimages (`assets.ninja_surface` × `BLEND_RGBA_MULT`, cached by dim level) offset to the left. ~0.7 s. |

Each effect is a `@dataclass` with a `life` / `max_life` timer; `alive`
is `life > 0` and the system culls dead effects each tick.

## API

```python
class SkillFxSystem:
    def __init__(self) -> None
    def trigger(self, skill_id: str, ninja_x: float, ninja_y: float,
                enemies: list) -> None
    def update(self, dt: float) -> None
    def draw(self, surf: pygame.Surface) -> None
    @property
    def active(self) -> bool
    def clear(self) -> None
    reduced_motion: bool          # set from state.reduced_motion
    on_shake: Callable | None     # set to game.shake for kunai/shuriken
```

Target selection in `trigger` mirrors `Runner.activate_skill` so the
visuals land on the same enemies the damage does:

- `kunai` → nearest 5 alive enemies (smallest `x`)
- `shuriken` → AOE ring centred on the ninja (radius sized to the
  farthest alive enemy, clamped to `[120, WINDOW_W//2]`)
- `rope` → weakest alive non-boss enemy (`min(hp)`)
- `speed` → no targets; aura around the ninja

## Integration

### 1. `Runner` owns the system

`engine/runner.py`, `Runner.__init__` (next to `self.fx = FXLayer()`):

```python
from engine.skill_fx import SkillFxSystem
...
self.skill_fx = SkillFxSystem()
```

### 2. `Runner.activate_skill` triggers the VFX **before** damage

The visual must lead the damage flash, so `trigger(...)` is the first
thing `activate_skill` does after the cooldown check — before
`_apply_damage` / `_on_enemy_killed`. The call passes the ninja's current
position and the live enemy list; the system picks its own targets from
those (it never reads or mutates enemy state).

```python
def activate_skill(self, sid: str) -> None:
    sk = self.skills.get(sid)
    if sk is None or not can_fire(sk):
        return
    fire_skill(sk)
    self.state.skills_used_today += 1
    # >>> VFX first, so the visual leads the damage flash. <<<
    self.skill_fx.trigger(sid, self.ninja.x, self.ninja.y,
                          self.world.enemies)
    combo_m = self.combo_mult()
    gold_m = self.gold_mult()
    if sid == "kunai":
        targets = sorted([e for e in self.world.enemies if e.alive],
                         key=lambda e: e.x)[:5]
        for t in targets:
            from engine.enemy import _apply_damage
            _apply_damage(t, self.ninja.tap_damage * 3 * combo_m,
                          is_crit=True)
            if not t.alive:
                self._on_enemy_killed(t, combo_m, gold_m,
                                      aggregate_bonuses(self.state))
        self.notify("Kunai Barrage!", (255, 120, 110))
    # ... shuriken / rope / speed branches unchanged ...
```

### 3. `Runner.update` ticks the system

Next to `self.fx.update(dt)` at the end of `update`:

```python
self.fx.update(dt)
self.skill_fx.update(dt)
```

### 4. `GameScreen.draw` draws it on top of the road

In `ui/screen_game.py`, after `runner.fx.draw(surf)` and the particles,
before the HUD:

```python
runner.fx.draw(surf)
self.game.particles.draw(surf)
runner.skill_fx.draw(surf)      # <<< new
```

The effects use the same lane Y and ninja X the screen uses, so they line
up with the drawn enemies/ninja without any coordinate plumbing.

### 5. (Optional) screen shake + reduced motion

Wire the accessibility / polish hooks once, e.g. in `Runner.__init__` or
from `GameScreen`:

```python
self.skill_fx.reduced_motion = state.reduced_motion
self.skill_fx.on_shake = self.game.shake
```

`trigger` already calls `on_shake(amp, dur)` for `kunai` (6.0, 0.3) and
`shuriken` (8.0, 0.3), gated by `reduced_motion`. If the runner does not
set these, the system simply skips the shake — no further changes needed.

## Performance / constraints

- **pygame primitives only.** Every shape is `pygame.draw.*` on a small
  per-effect SRCALPHA overlay, then one `blit` to the screen.
- **cached surfaces where possible.** Shuriken sprites are pre-rotated
  into a 24-bucket cache (`_shuriken_sprite`); ninja afterimages are
  pre-dimmed into a 5-level cache (`_ninja_ghost`); the base ninja sprite
  comes from `assets.ninja_surface`. The palette / lane-Y constants are
  module-level.
- **no per-frame allocations in hot loops.** Each effect's overlay
  surface is created once in `__post_init__` (at *spawn* time, inside
  `trigger`, which runs on a button click — not in `update`/`draw`).
  `draw` only `fill`s, `draw`s and `blit`s — none of those allocate.
- **no enemy state is read or mutated** by the system beyond the
  positions/`alive`/`hp`/`is_boss` it needs to pick targets, so it is
  safe to call before the damage pass.
