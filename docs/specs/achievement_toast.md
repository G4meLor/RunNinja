# Achievement Toast — integration spec

A dedicated **achievement toast** system so achievement unlocks feel
rewarding.  Currently `Runner.update` calls `self.notify(...)` for each
newly-unlocked achievement, which renders as a plain one-line
notification centered over the road.  This spec replaces that with a
slide-in card from the top-right: the achievement name, a medal/amber
reward line, a brief glow, and a small particle burst.  Up to 3 toasts
stack vertically; each has its own life timer.

## Files

| Path | Role |
|---|---|
| `ui/achievement_toast.py` | New. `AchievementToastSystem` — slide-in cards + glow + particle burst. |
| `engine/runner.py` | Existing. `Runner.update` calls `show(achievement)` for each newly-unlocked achievement. |
| `core/quests.py` | Existing. `check_achievements` returns the list of newly-unlocked `Achievement` objects. |
| `data/quests.py` | Existing. `Achievement` dataclass (`name`, `reward_amber`, `reward_medals`). |
| `main.py` | Existing. Owns the system, ticks it once per frame, draws it on top of every screen. |
| `theme.py` | Existing. Cached fonts + palette used by the cards. |
| `ui/screen_game.py` | Existing. The plain `runner.notifications` block stays for non-achievement toasts. |

## `AchievementToastSystem` API

```python
toasts = AchievementToastSystem()
toasts.show(achievement)    # enqueue a card for a newly-unlocked Achievement
toasts.update(dt)           # slide-in, hold, slide-out; re-stack on expiry
toasts.draw(surf)           # card with name + "+N amber/medals" + glow + particles
toasts.active               # True while any toast/particle is animating
toasts.reduced_motion       # set from state.reduced_motion each frame
toasts.clear()              # drop everything (e.g. on reset)
```

- `show(achievement)` reads `achievement.name`, `achievement.reward_amber`,
  and `achievement.reward_medals` (all present on `data.quests.Achievement`).
  It renders the name + reward text **once** (cached on the toast) and
  enqueues the card at the top of the stack; existing cards shift down.
  The stack is capped at 3 (oldest dropped).  An arrival particle burst
  fires at the new card's icon center (skipped under `reduced_motion`).
- `update(dt)` decrements each toast's life timer, eases its Y toward its
  slot (so the stack reflows smoothly when a card is removed), culls
  expired toasts, and re-indexes the survivors.  Particles live in a
  fixed-size pool and are deactivated (not removed) when their life hits 0.
- `draw(surf)` draws each card at its current X (slide-in from the right
  edge, hold, slide-out to the right) and Y (its slot), then the
  particles on top.  Call it **after** the active screen has drawn so the
  toasts overlay every screen.

### Card lifecycle (per toast)

| phase | duration | behavior |
|---|---|---|
| slide-in | 0.30 s | X eases from off the right edge to rest (ease-out-cubic); text + body fade in. |
| hold | 3.00 s | Card sits at rest at the top-right; full opacity. |
| slide-out | 0.40 s | X eases back off the right edge (ease-in-cubic); text + body fade out. |

Total per-toast life: ~3.70 s.  The arrival glow fades over 0.80 s from
the slide-in start.  The particle burst is a short ~0.6 s gold/amber
fountain at the card's icon center.

### Stacking

New toasts insert at index 0 (top of the stack).  Each toast's target Y
is `_TOP_Y + index * (_CARD_H + _GAP)`.  When a toast expires and is
culled, the survivors are re-indexed and their `target_y` is updated;
`update` eases each toast's Y toward its target, so the stack reflows
smoothly instead of jumping.  The stack is capped at 3 toasts; the oldest
is dropped when a fourth arrives.

## Integration

### 1. `main.py` owns the system

`Game.__init__` (after `self.runner` exists):

```python
from ui.achievement_toast import AchievementToastSystem
...
self.achievement_toasts = AchievementToastSystem()
```

### 2. `main.py._update` ticks it every frame

The simulation runs on every screen (so achievements can unlock while
the player browses buildings/upgrades/etc.), and the toast overlay must
animate regardless of the active screen.  Tick it once per frame,
unconditionally:

```python
# main.py._update, near the screen update:
self.achievement_toasts.reduced_motion = self.state.reduced_motion
self.achievement_toasts.update(dt)
```

### 3. `main.py.run` draws it on top of every screen

After `self.screens[self.current_screen].draw(self.screen)` (and after
the FPS / pause overlays so the toast sits on top of everything):

```python
self.screens[self.current_screen].draw(self.screen)
self.achievement_toasts.draw(self.screen)      # <<< new: overlay on every screen
if self.show_fps:
    self._draw_fps()
```

Drawing on top of every screen is intentional: achievements unlock from
the idle loop, not from a button click, so the player can be on any
screen when one fires.  The card slides in from the top-right corner,
which is empty on every screen (the HUD's currency pills are top-left;
the nav buttons are top-right but only ~32 px tall, and the toasts start
at `_TOP_Y = 104` to clear them).

### 4. `Runner.update` feeds unlocks into the system

`core.quests.check_achievements(state)` returns the list of newly-
unlocked `Achievement` objects.  `Runner.update` currently does:

```python
newly = check_achievements(self.state)
for a in newly:
    self.notify(f"Achievement: {a.name}  +{a.reward_amber} amber",
                (255, 205, 90))
```

Replace the `self.notify(...)` call with a call into the toast system.
The runner does not own the system (it lives on `Game`), so reach it via
a callback the runner stores, mirroring how `engine/zone_fx.py` reaches
`Game.hitstop_for`:

```python
# engine/runner.py, Runner.__init__ (next to self.notifications = []):
self.on_achievement_unlocked = None   # callable(Achievement) -> None

# engine/runner.py, Runner.update, replacing the self.notify(...) loop:
newly = check_achievements(self.state)
for a in newly:
    if self.on_achievement_unlocked is not None:
        try:
            self.on_achievement_unlocked(a)
        except Exception:
            pass
    # Keep the plain notify as a fallback so the road log still records it.
    self.notify(f"Achievement: {a.name}  +{a.reward_amber} amber",
                (255, 205, 90))
```

Keeping the `self.notify(...)` call is optional but harmless: it still
logs the unlock in the centered road notifications, while the toast card
is the prominent, rewarding presentation.  If you prefer a single
channel, drop the `notify` call and keep only the toast.

`main.py` wires the callback right after constructing both:

```python
# main.py, Game.__init__, after self.runner and self.achievement_toasts exist:
self.runner.on_achievement_unlocked = self.achievement_toasts.show
```

### 5. (Optional) reset on new game

`SettingsScreen._reset` already rebuilds the runner (`self.game.runner =
...; self.game.runner.reset_for_ascension()`).  Add:

```python
self.game.achievement_toasts.clear()
```

so a reset doesn't leave stale toasts animating.

## Behavior contract

- **Unlock**: `check_achievements` returns one or more `Achievement`
  objects; for each, `show(achievement)` enqueues a card at the top of
  the stack, fires a gold/amber particle burst at the card's icon center,
  and (under `reduced_motion`) skips the burst.
- **Slide-in**: the card eases in from the right edge over 0.30 s
  (ease-out-cubic); the name + reward text fade in with it; the arrival
  glow blooms behind the card and fades over 0.80 s.
- **Hold**: the card sits at the top-right for 3.00 s at full opacity.
- **Slide-out**: the card eases back off the right edge over 0.40 s
  (ease-in-cubic); the text + body fade out with it.
- **Stack**: up to 3 cards stack vertically from the top-right; when one
  expires, the survivors re-flow to their new slots smoothly (eased Y).
- **Reduced motion**: the particle burst is skipped; the slide-in /
  hold / slide-out + glow remain (they're gentle and not vestibular).
  If a fully static presentation is preferred, `show` could short-circuit
  to a no-op when `reduced_motion` is set — that's a future enhancement.

## Constraints honored

- **pygame primitives only.** Every shape is `pygame.draw.rect` /
  `circle` / `polygon`; no external image assets.
- **cached fonts.** `font_md(bold=True)` and `font_sm(bold=True)` come
  from `theme._font`, which caches by `(size, bold)` — no `SysFont` calls
  in the hot loop.
- **no per-frame allocations.** Text surfaces are rendered once at
  `show` time and stored on the toast; the glow halo is cached by card
  size in `_GLOW_CACHE` (keyed by `(w, h)`, so one surface total for the
  whole game); particles live in a fixed-size `_Particle` pool reused
  via an `active` flag; the particle draw uses a single reusable
  `_particle_surf` scratch (cleared + refilled per particle); one
  reusable `pygame.Rect` is used for all blits.  `update` and `draw`
  allocate nothing after warmup.
- **uses `utils.clamp` / `ease_out_cubic`** and the existing theme
  palette (`C.panel`, `C.panel_border_hi`, `C.gold`, `C.text`).

## Save compatibility

The toast system is purely visual and holds no persistent state —
nothing to save.  It is safe to construct on every game start and
discard on exit; in-flight toasts simply stop if the game is closed
mid-animation.
