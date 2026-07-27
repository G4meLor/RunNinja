# Screen Transitions — integration spec

Switching screens is no longer instant/jarring: a brief fade-out (~0.2s)
then fade-in (~0.2s) plays between the old and new screen. The transition
is driven by `ui/transitions.py:ScreenTransition`, which the `Game` owns
and threads through `set_screen` and the main draw loop.

## Module: `ui/transitions.py`

`ScreenTransition` exposes:

- `start(old_screen_name, new_screen_name)` — arm a transition. If the two
  names are equal, or `state.reduced_motion` is on, it jumps straight to
  the `done` phase with `pending_swap` set so the swap is instant.
- `update(dt)` — advance the phase machine one frame. After this returns,
  read `pending_swap` (one-frame flag the caller uses to flip its active
  screen pointer from `old_screen` to `new_screen`).
- `draw(surf, current_screen_draw)` — call the supplied zero-arg callable
  to render the current screen, then overlay a full-window rect whose
  alpha follows a smoothstep fade curve (0 → 255 during fade-out, 255 → 0
  during fade-in). No-op outside an active transition (zero overhead).
- `active` — True during fade-out / swap / fade-in.
- `done` — True once fade-in has completed.
- `phase` — human-readable phase name (`idle`, `fade_out`, `swap`,
  `fade_in`, `done`) for debugging.
- `reset()` — return to idle (call after `done` is consumed).

Phase machine:

```
IDLE -> FADE_OUT (~0.20s) -> SWAP (one frame) -> FADE_IN (~0.20s) -> DONE
```

The overlay Surface is created once (lazily, on first draw) and reused;
only `set_alpha` is called per frame. No per-frame allocations.

## Integration into `main.py`

### 1. Construction (`Game.__init__`)

```python
from ui.transitions import ScreenTransition
...
self.transition = ScreenTransition(self)
```

### 2. `set_screen(name)`

`set_screen` no longer flips `current_screen` directly. Instead it arms the
transition; the actual pointer swap happens in the update loop when
`pending_swap` becomes True.

```python
def set_screen(self, name):
    if name not in self.screens:
        return
    # Ignore re-entries to the same screen while a transition is mid-flight.
    if self.transition.active and self.transition.new_screen == name:
        return
    # If a transition is already running, complete it instantly so the new
    # request takes over cleanly.
    if self.transition.active:
        self.transition.reset()
        self.current_screen = self.transition.new_screen or self.current_screen
    self.transition.start(self.current_screen, name)
```

### 3. Update loop (`_update`)

After the per-screen `update(dt)`, advance the transition and consume the
one-frame swap flag:

```python
self.screens[self.current_screen].update(dt)
self.transition.update(dt)
if self.transition.pending_swap:
    self.current_screen = self.transition.new_screen
elif self.transition.done:
    self.transition.reset()
```

### 4. Draw loop (`run`)

Replace the direct `self.screens[self.current_screen].draw(self.screen)`
call with the transition-aware draw — the current screen is whichever the
phase dictates (old during fade-out, new after the swap):

```python
self.transition.draw(
    self.screen,
    lambda: self.screens[self.current_screen].draw(self.screen),
)
```

The FPS overlay and pause overlay are drawn *after* the transition draw so
they remain visible on top of the fade.

### 5. Input handling

During an active transition, input is still routed to the *current* screen
(the old one during fade-out). This is fine because the fade is short
(~0.2s) and the old screen is the visible one. No change needed to the
event loop.

## Why a callable, not a screen object

`draw(surf, current_screen_draw)` takes a zero-arg callable rather than a
screen reference so the caller can decide which screen is "current" at
draw time (it changes at the swap midpoint). This keeps the transition
module decoupled from the screen registry and lets `main.py` own the
screen-pointer semantics.

## Reduced motion

`state.reduced_motion` short-circuits the whole animation: `start` sets
`pending_swap` and `done` immediately, so the only effect is the screen
pointer swap — identical to the old instant behaviour.
