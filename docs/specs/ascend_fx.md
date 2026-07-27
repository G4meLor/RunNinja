# Ascension Ceremony FX — integration spec

`engine/ascend_fx.py` adds a full-screen ascension "ritual" so prestiging
feels monumental instead of a two-click confirm. A ~3 s cinematic plays
on confirm: the screen dims under a deep-indigo veil, elixir-coloured
particles converge from the four screen corners to the centre, the new
tier name slams in with `font_huge`, the stat multiplier flashes below
it, then a quick reverse horizontal sweep "rewinds" the road. The module
is **pure state** — the renderer reads it. It is **not** wired into the
existing game yet; the changes below are the minimal integration.

## System: `engine/ascend_fx.py`

`AscendFxSystem` exposes:

- `start(tier_name, stat_mult, elixir_gained)` — arm the ceremony. Renders
  the reveal text images once (at spawn time, not per frame) and builds
  the converging particle swarm. If `reduced_motion` is on, the ceremony
  short-circuits: the peak fires immediately and the phase jumps to
  `DONE` so the ascension still happens, just without the animation.
- `update(dt)` — advance the phase machine one frame. After this returns,
  read `peak` (one-frame flag: the moment the caller should perform the
  actual ascension + reset).
- `draw(surf, base_draw)` — call the supplied zero-arg callable to render
  the current screen, then overlay the ceremony (dim veil, converging
  particles, reveal text, rewind sweep). No-op outside an active
  ceremony (zero overhead).
- `active` — True during dim / converge / reveal / rewind.
- `done` — True once the rewind has completed.
- `peak` — True for exactly one `update` call (the frame the caller
  should perform the actual ascension on).
- `phase` — human-readable phase name (`idle`, `dim`, `converge`,
  `reveal`, `rewind`, `done`) for debugging.
- `reset()` — return to idle (call after `done` is consumed).
- `reduced_motion` — set from `state.reduced_motion` by the caller.

Phase machine (~3.0 s total):

```
IDLE -> DIM (~0.40s) -> CONVERGE (~1.00s) -> REVEAL (~0.90s) -> REWIND (~0.70s) -> DONE
                          ^
                          peak fires here (start of reveal) -- the caller
                          performs asc.ascend + runner.reset_for_ascension
                          + state.save on this frame.
```

- **DIM** — the screen darkens under a deep-indigo veil (alpha 0 → ~210,
  eased). Elixir-coloured particles begin to drift inward from the four
  corners.
- **CONVERGE** — elixir-coloured particles accelerate toward the screen
  centre, shrinking + fading as they near it; a soft core glow swells.
  The particles ease toward the centre (`ease_out_cubic` on the
  per-mote progress) so the swarm accelerates as it converges.
- **REVEAL** — the new tier name slams in (scaled 1.6x → 1.0x with
  `ease_out_cubic` over the first ~0.35 s, alpha ramping in over the
  same window) in elixir colour using `font_huge`; the stat multiplier
  "x{mult}" appears just below in `font_xl`, fading in after the slam.
  A short radial flash (expanding elixir shockwave ring) marks the peak.
  **This is the frame the caller performs the actual ascension.**
- **REWIND** — a quick horizontal sweep "rewinds" the road: an
  elixir-coloured band (~90 px wide) wipes from the right edge to the
  left (reverse of the normal road direction), ramping in / holding /
  ramping out.

## Integration

### 1. `Game` owns the system

`main.py`, `Game.__init__` (next to `self.particles = ParticleSystem()`):

```python
from engine.ascend_fx import AscendFxSystem
...
self.ascend_fx = AscendFxSystem()
```

### 2. `AscendScreen._do_ascend` arms the ceremony on confirm

`ui/screen_ascend.py` — on the *confirm* click (the second click), instead
of performing the ascension immediately, arm the ceremony. The actual
ascension + reset happens later, at the reveal peak, driven by the main
loop (see step 4). The new tier name + stat multiplier are read from
`cfg.ASCEND_TIERS` for the tier the player is about to enter
(`state.ascend_tier + 1`); the elixir gain is `asc.elixir_gain(state)`.

```python
def _do_ascend(self):
    state = self.game.state
    if self.confirm_pending:
        if not asc.can_ascend(state):
            self.confirm_pending = False
            return
        # Arm the ceremony instead of ascending immediately. The actual
        # ascension + reset happens at the reveal peak (driven by the
        # main loop via self.game.ascend_fx.peak).
        from config import ASCEND_TIERS
        from engine.ascend_fx import AscendFxSystem   # already on Game
        next_tier = min(state.ascend_tier + 1, len(ASCEND_TIERS) - 1)
        tier_name, stat_mult = ASCEND_TIERS[next_tier][0], ASCEND_TIERS[next_tier][1]
        gain = asc.elixir_gain(state)
        self.game.ascend_fx.start(tier_name, stat_mult, gain)
        # Play the ascend sweep SFX to bookend the ceremony.
        from assets import play
        play("ascend", state.sound_on)
        self.confirm_pending = False
    else:
        self.confirm_pending = True
        self.confirm_t = 3.0
```

The screen's `update` keeps the "Confirm Ascend?" label + red colour while
`self.game.ascend_fx.active` is True (so the button reads as committed
during the ceremony); the `confirm_pending` flag is cleared above so a
stray second click can't re-trigger.

### 3. Main loop drives `update` + `draw`; ascension happens at the peak

`main.py` — in `Game._update`, after the per-screen `update(dt)`, advance
the ceremony and consume the one-frame peak flag. **At the peak**, perform
the actual ascension (`asc.ascend`), reset the runner, and save — this is
the visual climax (the tier name slamming in coincides with the state
change):

```python
self.screens[self.current_screen].update(dt)
self.ascend_fx.update(dt)
if self.ascend_fx.peak:
    gained = asc.ascend(self.state)
    if gained > 0:
        self.runner.reset_for_ascension()
        self.shake(10, 0.6)
        self.state.save()
elif self.ascend_fx.done:
    self.ascend_fx.reset()
```

(`asc` is `core.ascend`; import it at the top of `main.py` or locally.) The
`Game.shake(10, 0.6)` already no-ops when `state.reduced_motion` is set,
so the accessibility gate is handled centrally. The `play("ascend", ...)`
SFX is fired once at `start` (step 2) so the sweep plays under the whole
ceremony.

In `Game.run`, replace the direct
`self.screens[self.current_screen].draw(self.screen)` call with the
ceremony-aware draw — the ceremony overlays the current screen:

```python
self.ascend_fx.draw(
    self.screen,
    lambda: self.screens[self.current_screen].draw(self.screen),
)
```

The FPS overlay and pause overlay are drawn *after* the ceremony draw so
they remain visible on top of the FX.

### 4. Screen input is blocked while the ceremony is active

`ui/screen_ascend.py` — in `AscendScreen.handle`, short-circuit while the
ceremony is running so the player can't click buttons (Back / Ascend) or
otherwise interact mid-ritual:

```python
def handle(self, event):
    if self.game.ascend_fx.active:
        return
    for b in self.buttons:
        b.handle(event)
```

(Optionally also skip `update`'s button-hover bookkeeping while active,
but blocking `handle` alone is enough to prevent clicks — the buttons
just won't receive events.)

## Why a callable, not a screen object

`draw(surf, base_draw)` takes a zero-arg callable rather than a screen
reference so the caller can decide which screen is "current" at draw
time. This keeps the ceremony module decoupled from the screen registry
and lets `main.py` own the screen-pointer semantics (the same pattern
`ui/transitions.py:ScreenTransition.draw` uses).

## Performance contract

- **No per-frame `Surface` allocations in the hot loop.** The dim veil,
  the particle scratch, the flash scratch, and the rewind band are all
  created once (lazily, on first draw) and reused for the life of the
  system; only `set_alpha` / `fill` / `draw` / `blit` run per frame.
- **Cached fonts.** The reveal text images are rendered once at `start`
  (spawn time, on a button click) via the cached `theme.font_huge` /
  `font_xl`; per frame, they are only `smoothscale`'d (a near-noop at
  1.0x, ~3 ms / 1000 calls) and `set_alpha`'d — never re-rendered.
- **Bounded particle count.** The converge swarm is 56 motes, built once
  at `start`; the list is mutated in place each tick (no filtering, since
  all motes expire with the ceremony). The per-frame cost is 56 small
  `gfx`-free `pygame.draw.circle` calls on a 16 px scratch + blits.
- **Bounded scratch sizes.** The particle scratch is 16 px; the flash
  scratch is 256 px (fits the max ~120 px flash radius); the dim veil and
  rewind band are full-window / full-height plain Surfaces created once.
- **Plain vs SRCALPHA.** The dim veil and rewind band are plain
  (non-SRCALPHA) Surfaces so `set_alpha` gives a uniform global fade when
  blitted over the opaque screen (the classic dim technique). The
  particle + flash scratches are SRCALPHA so the circle alpha blends
  correctly when blitted (the screen itself is non-SRCALPHA, so direct
  `pygame.draw.circle` with a 4-tuple would *replace* rather than blend —
  the scratch + blit path is what gives real translucency).

## Accessibility

`AscendFxSystem.reduced_motion = True` (set from `state.reduced_motion`)
short-circuits the whole animation: `start` sets `peak` and `done`
immediately, so the only effect is the state change (the caller's
ascension + reset at the peak) — identical to the old instant behaviour
minus the cinematic. `Game.shake`'s own `reduced_motion` gate handles the
shake; the `play("ascend", ...)` SFX is unaffected (it's a 1 s sweep,
not a motion effect).
