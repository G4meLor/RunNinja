# Boss Intro FX — integration spec

A new module, `engine/boss_fx.py` (`BossFxSystem`), plays a dramatic
~1.5s intro when a boss enters: the screen darkens, the boss name slams
in huge text with a red glow, a health bar slides in at the top, and a
brief screen shake fires on spawn. After the intro, the health bar
stays visible for as long as the boss is alive and tracks its HP.

The system is pure-state + pygame primitives. Fonts are cached
(`theme.font_*`), the name/glow/darken/label surfaces are cached by
key, and the hot path does **no per-frame allocations** (the only
per-frame work is `set_alpha` on a cached surface, which is restored to
255 after each blit so the cache stays pristine).

## `BossFxSystem` API

```python
class BossFxSystem:
    def start(self, boss_name: str, boss_hue: int) -> None: ...
    def stop(self) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surf: pygame.Surface, boss_hp_pct: float) -> None: ...
    @property
    def active(self) -> bool: ...
    @property
    def wants_shake(self) -> bool: ...
```

* `start` — call when a boss spawns. Builds (and caches) the name
  surface, arms the intro timer, and sets a one-shot `wants_shake`
  flag.
* `stop` — call when the boss dies. Clears the overlay.
* `update(dt)` — advances the intro timer. After `INTRO_DURATION`
  (1.5s) the intro is "done" but `active` stays True until `stop`.
* `draw(surf, boss_hp_pct)` — draws the darken + name slam + health
  bar. `boss_hp_pct` is the boss's `hp / max_hp`, 0..1; pass it every
  frame so the bar tracks damage.
* `active` — True from `start` until `stop`. The screen should only
  call `update`/`draw` while this is True.
* `wants_shake` — True for exactly one read after `start`; the runner
  reads it and calls `Game.shake(...)`. It is one-shot so the shake
  fires once per boss, not every frame.

## Intro timeline (seconds)

```
0.00 ─────────────────────────────────────────────── 1.50 (intro done)
│                                                  │
├─ darken ramps in (0.00–0.35, ease-in-out) ───────┤
│        ├─ name slams in (0.30–0.75, ease-out) ───┤
│        │              ├─ name holds (0.75–1.00) ─┤
│        │              │       ├─ name fades ────┤
│        │              │       │    ├─ bar slides/wipes in (0.75–1.20) ─┤
│        │              │       │    │             ├─ bar holds, label appears ─┤
▼        ▼              ▼       ▼    ▼             ▼
```

After 1.5s the intro is done; the darken drops to a lingering dim
(`DARKEN_ALPHA_HOLD = 90`) and the health bar stays at full width with
the boss-name label until `stop`.

## Integration points

### 1. `engine/world.py` — fire the callback on boss enter

Add an `on_boss_enter` callback slot on `World` and call it from
`_enter_boss`. The runner owns the `BossFxSystem` and wires the
callback, so the world stays drawing-free.

```python
class World:
    def __init__(self) -> None:
        ...
        self.boss_active = False
        # Set by the runner to (boss_name, boss_hue) when a boss enters.
        self.on_boss_enter = None  # callable[[str, int], None] | None

    def _enter_boss(self) -> None:
        if self.boss_active:
            return
        self.boss_active = True
        bdef = ed.boss_for_zone(self.zone_id)
        boss = spawn_boss(bdef, hp=self.zone_hp(bdef), dmg=self.zone_dmg(bdef),
                          gold=self.zone_gold(bdef))
        self.enemies.append(boss)
        if self.on_boss_enter is not None:
            try:
                self.on_boss_enter(boss.name, boss.hue)
            except Exception:
                pass
```

### 2. `engine/runner.py` — own the `BossFxSystem`, wire the callback, trigger the shake

The runner owns the system (it already owns the `FXLayer`), wires the
world callback, and converts the one-shot `wants_shake` flag into a
`Game.shake(...)` call. Because the runner does not import `Game`, the
shake is dispatched via a second callback slot the main loop sets.

```python
from engine.boss_fx import BossFxSystem

class Runner:
    def __init__(self, state: GameState) -> None:
        ...
        self.fx = FXLayer()
        self.boss_fx = BossFxSystem()
        # Set by main.py to trigger a screen shake: callable[[float, float], None].
        self.on_boss_shake = None
        # Wire the world's boss-enter callback to the FX system.
        self.world.on_boss_enter = self._on_boss_enter

    def _on_boss_enter(self, boss_name: str, boss_hue: int) -> None:
        self.boss_fx.start(boss_name, boss_hue)
        # The shake fires on the next update tick (one-shot flag) so it
        # lands right as the name slams in.
        if self.boss_fx.wants_shake and self.on_boss_shake is not None:
            try:
                self.on_boss_shake(8.0, 0.4)
            except Exception:
                pass

    def update(self, dt: float, *, paused: bool = False) -> None:
        ...
        # Tick the boss FX intro.
        self.boss_fx.update(dt)
        ...

    def _on_enemy_killed(self, enemy, combo_m, gold_m, evo) -> None:
        ...
        if enemy.is_boss:
            self.state.bosses_killed += 1
            self.boss_fx.stop()      # clear the overlay when the boss dies
            self.notify(f"Boss slain: {enemy.name}!", (255, 220, 120))
        ...
```

`reset_for_ascension` should also call `self.boss_fx.stop()` so a
pending intro does not leak across an ascension reset.

### 3. `main.py` — set the shake callback, tick the FX on every screen

The runner runs on every screen (idle loop keeps simulating while the
player browses buildings/etc.), so the boss FX must tick on every
screen too. Wire the shake callback once after constructing the runner.

```python
self.runner = Runner(self.state)
self.particles = ParticleSystem()
self.runner.on_boss_shake = lambda amp, dur: self.shake(amp, dur)
```

`Game.shake` already respects `state.reduced_motion`, so the shake is
automatically skipped for players who opted out of motion effects.

### 4. `ui/screen_game.py` — draw the overlay, pass the boss HP pct

In `GameScreen.draw`, after the existing FX/particles and before the
HUD, draw the boss overlay. The screen reads the boss's current HP
from the world's enemy list (the boss is the `is_boss` enemy) and
passes `hp / max_hp` to `draw`. The existing thin "BOSS" banner (lines
210–216) is superseded by the new overlay and should be removed or
gated on `not boss_fx.active` to avoid stacking.

```python
def draw(self, surf: pygame.Surface) -> None:
    runner = self.game.runner
    world = runner.world
    ...
    # FX + particles.
    runner.fx.draw(surf)
    self.game.particles.draw(surf)

    # Boss intro + health bar overlay.
    boss_fx = runner.boss_fx
    if boss_fx.active:
        # Find the boss enemy to read its current HP pct.
        boss = next((e for e in world.enemies if e.is_boss and e.alive), None)
        hp_pct = (boss.hp / boss.max_hp) if boss else 0.0
        boss_fx.draw(surf, hp_pct)

    # HUD.
    self._draw_hud(surf, state, world)
    ...
```

The boss-enemy lookup is a short scan (≤6 enemies + 1 boss), so it is
cheap; the alternative is to cache the boss reference on the runner
when `_on_boss_enter` fires. If the boss has already died this frame
(`boss is None`), pass `0.0` so the bar empties before `stop` clears it
on the next runner tick.

### 5. Removing the old banner

The existing block in `screen_game.draw`:

```python
# Boss banner.
if world.boss_active:
    banner = pygame.Rect(0, cfg.ROAD_TOP, cfg.WINDOW_W, 28)
    bg2 = pygame.Surface(banner.size, pygame.SRCALPHA)
    pygame.draw.rect(bg2, (40, 10, 20, 200), bg2.get_rect())
    surf.blit(bg2, banner.topleft)
    draw_text_center(surf, "BOSS", (cfg.WINDOW_W // 2, cfg.ROAD_TOP + 14),
                     font_md(bold=True), C.text_bad)
```

allocates a `Surface` per frame and is replaced by the cached
`BossFxSystem` overlay. Remove it (or gate it on
`not boss_fx.active` during a transition) when wiring the new system.

## Wiring checklist

1. `engine/world.py` — add `self.on_boss_enter = None` in `__init__`;
   call it from `_enter_boss` with `(boss.name, boss.hue)`.
2. `engine/runner.py` — `from engine.boss_fx import BossFxSystem`;
   create `self.boss_fx = BossFxSystem()` in `__init__`; set
   `self.world.on_boss_enter = self._on_boss_enter`; add
   `self.on_boss_shake = None`; add the `_on_boss_enter` method;
   call `self.boss_fx.update(dt)` in `update`; call
   `self.boss_fx.stop()` in `_on_enemy_killed` (boss branch) and in
   `reset_for_ascension`.
3. `main.py` — after `self.runner = Runner(self.state)`, set
   `self.runner.on_boss_shake = lambda amp, dur: self.shake(amp, dur)`.
4. `ui/screen_game.py` — in `draw`, after `self.game.particles.draw`,
   draw `runner.boss_fx` with the boss's HP pct; remove the old
   per-frame "BOSS" banner.

## Save / state compatibility

No `GameState` fields are added. The `BossFxSystem` is transient
(runtime-only), so no save migration is needed.

## Reduced motion

`Game.shake` already early-returns when `state.reduced_motion` is True,
so the spawn shake is skipped for those players. The visual intro
(darken + name + bar) still plays; if a fully static intro is desired
for reduced-motion users, gate the `boss_fx.start` call in
`_on_boss_enter` on `not state.reduced_motion` and instead call
`boss_fx.start` followed by `boss_fx.update(INTRO_DURATION)` to snap
straight to the steady-state bar.
