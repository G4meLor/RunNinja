# Zone Transition FX (`engine/zone_fx.py`)

A cinematic ~2s overlay that plays when the player advances to a new
zone, replacing the old thin white wipe with a banner + cross-fade +
light sweep + hit-stop.

## Component

`ZoneFxSystem` (in `engine/zone_fx.py`) is a self-contained overlay:
- `trigger(zone_index, zone_name, old_hue, new_hue)` — starts the
  sequence, caches the destination background, and fires `on_hitstop`.
- `update(dt)` — advances the timeline (~2s total).
- `draw(surf)` — renders the banner band + light sweep over the road.
- `active` — True while the sequence is running.
- `crossfade_alpha()` / `crossfade_surface()` — exposed so the screen
  can blend the new zone's background under the overlay.

Phases (seconds):
- `0.00–0.45` **banner-in** — dark band slides down from the top, zone
  name ("Zone 2 — Bamboo Forest") fades/scales in.
- `0.45–1.20` **cross-fade** — the new zone's background (from
  `assets.background`) is blitted as an alpha overlay over the current
  background so the palette shifts from the old hue to the new hue.
- `0.80–1.40` **sweep** — a soft diagonal light band wipes left→right.
- `1.40–2.00` **banner-out** — the band slides back up and fades out.

Rendering uses pygame primitives only: `pygame.draw.rect/line` for the
band, the cached theme fonts (`font_xl`, `font_lg`) for the text, and
the `hsl()` helper from `assets` for the new zone's tint/accent. Fonts
are cached by `theme._font`, so no surface is created per frame.

## Integration

### 1. Own the instance

`Game` (or `Runner`) owns one `ZoneFxSystem` and wires the hit-stop
callback to `main.py`:

```python
# main.py (inside Game.__init__, after self.runner exists)
from engine.zone_fx import ZoneFxSystem
self.zone_fx = ZoneFxSystem()
self.zone_fx.on_hitstop = self.hitstop_for   # Game.hitstop_for exists
```

`Game.hitstop_for(dur)` already exists and feeds the `self.hitstop` that
`_update` uses to scale `dt` by 0.05 for the slow-motion beat. No new
state in main.py is required.

### 2. Trigger on boss kill (before the world advances)

In `engine/runner.py`, `_on_enemy_killed` currently calls
`self.world.on_enemy_killed(enemy)` last, which increments
`zone_index`. Insert the trigger **before** that call so the banner can
show the *destination* zone, then let the world advance:

```python
# engine/runner.py, _on_enemy_killed, replacing the final line:
if enemy.is_boss:
    from data import enemies as ed
    next_index = self.world.zone_index + 1
    if next_index < len(ed.ZONES):
        old_hue = self.world.zone["hue"]
        new_hue = ed.ZONES[next_index]["hue"]
        new_name = ed.ZONES[next_index]["name"]
        # game.zone_fx is set by main.py (see step 1).
        fx = getattr(self, "zone_fx", None) or getattr(self.game, "zone_fx", None)
        if fx is not None:
            fx.trigger(next_index, new_name, old_hue, new_hue)
self.world.on_enemy_killed(enemy)
```

The exact attribute path depends on how `Runner` reaches the `Game`; the
cleanst option is for `main.py` to set `self.runner.zone_fx = self.zone_fx`
right after constructing both, so the runner reads `self.zone_fx`.

### 3. Drive the timeline + draw the overlay

`main.py._update` already calls `self.screens[...].update(dt)`; add the
zone-fx tick there (it's screen-agnostic, so tick it once per frame):

```python
# main.py._update, near the screen update:
self.zone_fx.update(dt)
```

`ui/screen_game.py.GameScreen.draw` starts by blitting
`background(world.zone_index, world.zone["hue"])`. Because the world
already advanced `zone_index` at trigger time, that would draw the *new*
background immediately and the cross-fade would be invisible. During the
transition, draw the **old** background as the base and cross-fade the
new one on top, then the overlay:

```python
# ui/screen_game.py, top of GameScreen.draw, replacing the plain
# `bg = background(world.zone_index, world.zone["hue"]); surf.blit(bg,(ox,oy))`:
from assets import background
cf = self.game.zone_fx
if cf.active:
    # Base = the zone we're leaving, so the palette shift is visible.
    bg = background(cf.old_zone_index(), cf.old_hue)
    surf.blit(bg, (ox, oy))
    a = cf.crossfade_alpha()
    new_bg = cf.crossfade_surface()
    if a > 0 and new_bg is not None:
        new_bg.set_alpha(a)
        surf.blit(new_bg, (ox, oy))
else:
    bg = background(world.zone_index, world.zone["hue"])
    surf.blit(bg, (ox, oy))
```

Then, at the **end** of `draw` (after the HUD, so the band sits over the
road), render the overlay:

```python
# ui/screen_game.py, end of GameScreen.draw:
cf = self.game.zone_fx
if cf.active:
    cf.draw(surf)
```

The cross-fade blit happens *before* `cf.draw` so the banner + sweep
sit on top of the blended background. The HUD is drawn between them and
will be partly covered by the band — that's intentional (the band is the
focal point). If the HUD must stay visible, move the `_draw_hud` call to
after `cf.draw`.

### 4. Hit-stop (slow-motion on the boss kill)

Already handled by step 1: `trigger()` calls `on_hitstop(HITSTOP_DUR)`
(0.12s), which calls `Game.hitstop_for`, which sets `self.hitstop`. The
existing `main.py._update` then scales `dt` by 0.05 for that window so
the boss death + the start of the banner play in slow motion. No
further changes to main.py are needed beyond wiring the callback.

## Notes

- The cross-fade is an alpha overlay of the *new* background over the
  *current* one (both come from `assets.background`, which caches by
  `(zone_index, hue)`), so it's cheap and the palette shift is
  continuous.
- `ZoneFxSystem` caches the destination background surface for the
  duration of the sequence and releases it when inactive.
- Respects `reduced_motion` indirectly: `Game.hitstop_for` already
  no-ops when `state.reduced_motion` is set. For full reduced-motion
  support, `trigger()` could short-circuit to a plain background swap;
  that's a future enhancement.
