# Firefly FX — Integration Spec

`engine/firefly_fx.py` adds a self-contained `FireflyFxSystem` that makes
fireflies feel magical: a spawn sparkle, a gentle pulsing glow while alive, a
"tap me!" pulse on first spawn, and a satisfying catch burst (golden particles
+ a floating "+gold" number + a chime via `assets.play`).

The module is pure state + cached surfaces; it allocates nothing per frame in
the hot loop (transient lists are rebuilt only when culled, and the soft glow
disc is cached by radius).

## Integration points

### 1. Runner — spawn hook

`World._spawn_firefly` (and the kill-driven firefly spawn in
`Runner._on_enemy_killed`) append a firefly to `world.fireflies`.  Right after
that append, call the FX system so the spawn sparkle + "tap me!" pulse fire:

```python
# engine/runner.py — in _on_enemy_killed, after the firefly is appended:
from engine.firefly_fx import firefly_fx
self.world.fireflies.append(f)
firefly_fx.on_spawn(f)
```

```python
# engine/world.py — in _spawn_firefly, after spawn_firefly:
from engine.firefly_fx import firefly_fx
f = spawn_firefly(x, y, size_bonus=self.firefly_size_bonus)
self.fireflies.append(f)
firefly_fx.on_spawn(f)
```

The system is a process-singleton; import and call directly (mirrors
`assets.play`).  If a shared instance is preferred, the runner can own one
(`self.firefly_fx = FireflyFxSystem()`) and forward calls; either works since
the FX is cosmetic and stateless w.r.t. game logic.

### 2. Runner — catch hook

In `Runner.tap_at`, the firefly-catch branch already awards gold and notifies.
Add the catch FX call so the burst, floating "+gold", and chime fire:

```python
# engine/runner.py — inside the firefly-catch branch, after self._award_gold(gold):
from engine.firefly_fx import firefly_fx
firefly_fx.on_catch(f.x, f.y, gold)
```

`on_catch(x, y, gold)` plays the `"firefly"` chime via `assets.play`, so the
runner does not need to call `play` separately for fireflies.

### 3. Runner / GameScreen — update + draw

The system's `update(dt)` and `draw(surf)` must be called each frame:

```python
# engine/runner.py — in update(), alongside self.fx.update(dt):
from engine.firefly_fx import firefly_fx
firefly_fx.update(dt)
```

```python
# ui/screen_game.py — in draw(), after the fireflies are blitted and before/after
# runner.fx.draw(surf):
from engine.firefly_fx import firefly_fx
firefly_fx.draw(surf)
```

Draw order: blit firefly bodies first, then `firefly_fx.draw(surf)` so the
spawn sparkles and catch bursts layer on top of the fireflies but under the
HUD.

### 4. Screen — pulsing glow while alive

The screen currently blits each firefly with a fixed `firefly_surface(...)`.
To add the gentle breathing glow + the "tap me!" pulse on first spawn, scale
the firefly surface by the system's combined pulse scale:

```python
# ui/screen_game.py — the firefly render loop:
from engine.firefly_fx import firefly_fx
import pygame

t = pygame.time.get_ticks() / 1000.0      # seconds
for f in world.fireflies:
    fs = firefly_surface(max(6, int(f.size)), f.hue)
    scale = firefly_fx.spawn_pulse_scale(id(f), t)
    if abs(scale - 1.0) > 0.01:
        w = max(1, int(fs.get_width() * scale))
        h = max(1, int(fs.get_height() * scale))
        fs = pygame.transform.smoothscale(fs, (w, h))
    surf.blit(fs, fs.get_rect(center=(int(f.x) + ox, int(f.y) + oy)))
```

`pulse(t)` returns a gentle `1.0 + 0.15 * sin(t * 3.0)` breathing scale.
`spawn_pulse_scale(fid, t)` blends that with a faster, larger, decaying
oscillation for the first `SPAWN_PULSE_LIFE` (1.2s) after spawn — the
"tap me!" attention pulse.  Once the spawn pulse expires it falls back to the
gentle breathing, so the firefly keeps softly glowing for its whole life.

## API summary

`FireflyFxSystem`:
- `on_spawn(firefly)` — spawn sparkle + register a "tap me!" pulse for the
  firefly's id.
- `on_catch(x, y, gold)` — golden particle burst + central flash ring +
  floating "+gold" text + `"firefly"` chime via `assets.play`.
- `update(dt)` — advance all transient effects; cull dead ones.
- `draw(surf)` — render sparkles, particles, and floating text.
- `pulse(t)` — gentle breathing scale in ~[0.85, 1.15].
- `spawn_pulse_remaining(fid)` — remaining spawn-pulse time for a firefly id.
- `spawn_pulse_scale(fid, t)` — combined breathing + "tap me!" scale the
  screen applies to the firefly glow.

## Constraints honored

- pygame primitives only (circles, rings, `smoothscale`, `set_alpha`).
- Soft glow discs are cached by radius (`_glow_disc`); no per-frame surface
  construction for the sparkles.
- Particle/float-text lists are mutated in place and rebuilt only when culled
  (the cull rebuild is bounded by the small, transient count).
- Chime routed through `assets.play("firefly", ...)` — no new audio path.
