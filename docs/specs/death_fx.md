# Death FX — integration notes

`engine/death_fx.py` adds a satisfying, layered enemy death animation
(particle burst tinted by enemy hue, rising "soul" for bosses, gold coins
flying up toward the HUD gold pill, an expanding flash ring, and a
shrinking/fading corpse that reuses the cached `enemy_surface`). It is
**pure state** — the renderer reads it. It is **not** wired into the
existing game yet; the changes below are the minimal integration.

## System ownership

`DeathFxSystem` lives next to the existing `FXLayer` and
`ParticleSystem`:

- `engine/runner.py` — create it in `Runner.__init__` and update it in
  `Runner.update`:
  ```python
  from engine.death_fx import DeathFxSystem
  ...
  self.death_fx = DeathFxSystem()
  # in update(dt, ...), after self.fx.update(dt):
  self.death_fx.update(dt)
  ```
- `main.py` — wire the screen-shake callback at startup so boss deaths
  shake the screen (the same `Game.shake` already used by the legacy
  particle-burst path):
  ```python
  self.runner.death_fx.on_shake = self.shake
  ```
  `Game.shake` already no-ops when `state.reduced_motion` is set, so the
  accessibility gate is handled centrally. Optionally mirror the flag:
  ```python
  self.runner.death_fx.reduced_motion = self.state.reduced_motion
  ```

## Where to spawn

`engine/runner.py` — in `Runner._on_enemy_killed`, right after the
existing combo/loot bookkeeping (so the death animation starts from the
same tick the kill is recorded):
```python
def _on_enemy_killed(self, enemy, combo_m, gold_m, evo):
    ...
    self.world.on_enemy_killed(enemy)
    self.death_fx.spawn(enemy)   # <-- new
```
`DeathFxSystem.spawn` only reads `enemy.x`, `enemy.edef`, `enemy.hue`,
`enemy.size`, and `enemy.is_boss`, so it is safe to call before the
renderer runs and even after `enemy.alive` has been set to `False`.

It is also fine to spawn from the active-skill kill paths in
`Runner.activate_skill` (kunai / shuriken / rope) — they all funnel into
`_on_enemy_killed`, so a single spawn site covers every kill source.

## Where to draw

`ui/screen_game.py` — in `GameScreen.draw`, after the enemies loop and
before/with the existing FX pass, so the death animation overlays the
corpse but sits under the HUD:
```python
# FX + particles.
runner.fx.draw(surf)
self.game.particles.draw(surf)
runner.death_fx.draw(surf)   # <-- new
```
The system draws on the same `surf` and respects the current
`shake_offset` implicitly (the corpse is centered on the enemy's last
`x`, which the screen already offsets). If you want the flash/soul to
also track shake, add `ox, oy` to the draw call:
```python
runner.death_fx.draw(surf, ox=ox, oy=oy)
```
and adjust `_glow`/corpse blit positions accordingly (the module currently
ignores offsets to keep the API minimal).

## Replacing the old fade

The legacy corpse fade lives in two places and can be left in place
(fallback) or trimmed once `DeathFxSystem` is active:

- `ui/screen_game.py` — the `if not e.alive:` branch that copies +
  alpha-fades `enemy_surface`. With death FX active, the corpse is drawn
  by `DeathFxSystem` instead; the on-screen fade can be skipped for
  enemies that have a `DeathFx` in flight (or simply removed).
- `main.py` — `_update_particles` still fires the old
  `self.particles.burst(...)` on dead enemies (the `_bursted` guard).
  This is redundant with `DeathFxSystem.spawn`; once death FX is wired,
  delete that block so kills don't double-burst. The `self.shake(8.0,
  0.4)` / `self.hitstop_for(0.08)` boss handling there is also superseded
  by the `on_shake` callback (hitstop can be added to `DeathFxSystem` if
  desired).

## Cull interaction

`engine/runner.py` culls enemies whose `last_damage_timer <= -0.3`.
`DeathFxSystem` keeps its own `t < max_t` lifetime (0.6s normal, 0.95s
boss), so it is independent of the enemy cull — the animation keeps
playing after the enemy object is gone. No change needed to the cull
logic.

## Performance contract

- No per-frame `Surface` allocations in the hot loop. The translucent
  glow/flash/soul/coin/burst shapes all draw onto a single pre-allocated
  SRCALPHA scratch (`_SCRATCH_SIZE = 128`), cleared per element with
  `s.fill((0,0,0,0))` and blitted. The scratch is created lazily on the
  first draw and reused for the life of the system.
- The shrinking corpse uses `pygame.transform.scale` of the cached
  `enemy_surface` to build a fixed 8-step set of pre-scaled copies at
  **spawn time**; `set_alpha` later only mutates those per-death copies,
  never the global `_ENEMY_CACHE`.
- Particle/coin counts are bounded (12/5 normal, 30/10 boss) and lists
  are filtered each tick, so the system is O(kills) memory.

## Accessibility

Set `DeathFxSystem.reduced_motion = True` to skip the flash ring and the
boss soul (and to suppress the shake callback's effect via `Game.shake`'s
own `reduced_motion` gate). The corpse shrink/fade and the coin/burst
particles remain — they are small and short-lived.
