# Currency Pill FX — integration spec

A new module, `ui/currency_fx.py` (`CurrencyFxSystem`), polishes the
**currency pills** in the HUD (Gold / Elixir / Amber / Medals) that
`ui/screen_game._draw_hud` draws via `ui.widgets.currency_pill`.

It adds three things over the flat pills:

1. **Animated icons** — each pill's icon circle breathes with a soft
   glow ring that pulses on a ~2.4s sine, and briefly flashes a brighter
   ring when its currency ticks up.
2. **+N floaters** — when a currency increases over a short window
   (~0.5s), a green "+N" text rises above the pill and fades.  Deltas are
   tracked per-currency; decreases (spending, ascension reset) are
   re-baselined immediately so a subsequent gain doesn't show a stale
   delta.
3. **Tooltips** — `tooltip(currency_name)` returns a description string
   the screen feeds to its hover-tooltip manager so hovering a pill
   explains what that currency is for.

All rendering uses pygame primitives + the cached theme fonts.  The
per-frame hot path performs zero allocations once warm: floater slots
live in a fixed pool (`_MAX_FLOATS`), text surfaces are rendered once at
spawn time and reused, and the glow/flash rings use a single reusable
SRCALPHA scratch surface (grown lazily to the largest size seen, then
reused — never re-allocated per frame).

## The system

`CurrencyFxSystem` exposes:

| method | purpose |
|--------|---------|
| `snapshot(state)` | record current currency values as the delta baseline (call once at construction) |
| `update(dt, state)` | advance the delta window, decay flashes, advance floaters; emit new floaters on window flush |
| `draw(surf, pill_rects)` | render the animated icons (breathing glow + flash) and the +N floaters over the pills |
| `tooltip(currency_name)` | return a description string (newlines: first line is the title) for the hover tooltip |

`pill_rects` is a `dict[str, pygame.Rect]` mapping the currency label
("Gold", "Elixir", "Amber", "Medals") to the pill's screen rect.  The
screen builds it in `_draw_hud` while laying out the pills (it already
tracks `x`/`y` and `currency_pill` returns the width), then passes it to
`draw` so the fx can position the icon glow/flash and the floaters.

## Constructing and owning the system

`GameScreen` owns one instance, created in `__init__` and snapshotted
once so the initial values aren't treated as a gain:

```python
from ui.currency_fx import CurrencyFxSystem

class GameScreen:
    def __init__(self, game) -> None:
        ...
        self.currency_fx = CurrencyFxSystem()
        self.currency_fx.snapshot(self.game.state)
```

If you prefer, hang it on `game` instead and share it across screens —
the system is self-contained and has no per-screen state beyond the
active floaters and the delta baseline.

## Wiring the update

In `GameScreen.update`, advance the fx each frame:

```python
def update(self, dt: float) -> None:
    ...
    self.currency_fx.reduced_motion = self.game.state.reduced_motion
    self.currency_fx.update(dt, self.game.state)
```

`update(dt, state)` reads the current currency values from `state`
(`state.gold` / `state.elixir` / `state.amber` / `state.medals`), diffs
them against the baseline, and emits a floater when the window flushes.
Decreases (spending on a building, an ascension reset) re-baseline
immediately so the next gain doesn't show a stale delta.

## Wiring the draw

In `GameScreen._draw_hud`, build the `pill_rects` dict while laying out
the pills, then call `currency_fx.draw` after the pills are drawn so the
animated icons and floaters overlay them:

```python
def _draw_hud(self, surf, state, world) -> None:
    pygame.draw.rect(surf, C.panel_lo, (0, 0, cfg.WINDOW_W, cfg.HUD_H))
    pygame.draw.line(surf, C.panel_border,
                     (0, cfg.HUD_H), (cfg.WINDOW_W, cfg.HUD_H), 1)
    x = 16; y = 10
    pill_rects: dict[str, pygame.Rect] = {}
    for name, color in (("Gold", C.gold),
                        ("Elixir", (120, 220, 200)),
                        ("Amber", (255, 180, 60)),
                        ("Medals", (200, 200, 220))):
        w = currency_pill(surf, x, y, name,
                          format_number(getattr(state, name.lower())), color)
        pill_rects[name] = pygame.Rect(x, y, w, 28)
        x += w + 10
    # Zone bar (unchanged) ...
    # Animated icons + floaters over the pills.
    self.currency_fx.draw(surf, pill_rects)
```

`currency_pill` returns the pill width, so the rect is `(x, y, w, 28)`
(the pill height is hardcoded at 28 in `ui.widgets.currency_pill`).  The
icon center is at `(x + 14, y + 14)` — the fx system uses that offset to
position the glow/flash rings.

## Wiring the tooltip

`GameScreen` does not currently use `ui.tooltip.TooltipManager`.  When
it does (or if a shared tooltip manager is added to `Game`), register
the pill rects as hover regions with the fx system's `tooltip` text:

```python
# in _draw_hud, after building pill_rects:
if hasattr(self, 'tooltip_mgr'):
    self.tooltip_mgr.clear()
    for name, rect in pill_rects.items():
        self.tooltip_mgr.register(
            f"currency_{name}", rect, self.currency_fx.tooltip(name))
```

`tooltip(name)` returns a string with newlines; the first line is the
title (rendered bold by `TooltipManager`), the rest are the body.  This
matches the `TooltipManager._wrap` contract (it splits on `\n` and
renders the first line bold).  Until a tooltip manager is wired in, the
`tooltip` method is still safe to call — it just returns the string.

## Full draw order in `_draw_hud`

1. HUD background strip + border (unchanged).
2. Currency pills (unchanged) — track each pill's rect in `pill_rects`.
3. Zone name + zone progress bar (unchanged).
4. `self.currency_fx.draw(surf, pill_rects)` — animated icons + floaters
   on top of the pills.

The fx must draw *after* the pills so the glow/flash rings and floaters
overlay them.

## Tunables

The fx module exposes these constants at the top of
`ui/currency_fx.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_WINDOW` | 0.50s | delta accumulation window |
| `_MIN_GAIN` | 1.0 | don't floater for sub-1 gains (avoids "+0") |
| `_FLOAT_DUR` | 1.00s | floater lifetime |
| `_FLOAT_RISE` | 20px | pixels the floater rises over its life |
| `_PULSE_PERIOD` | 2.4s | icon breathing period |
| `_FLASH_DUR` | 0.40s | icon flash duration on tick |
| `_FLASH_MAX_R` | 16px | peak flash ring radius |
| `_MAX_FLOATS` | 12 | floater slot pool size (3 per currency) |
| `_GLOW_COLOR` | (130, 230, 160) | +N floater color (C.text_good) |

Tune by editing the constants; no other module needs to change.

## Accessibility

Set `currency_fx.reduced_motion = state.reduced_motion` each frame (see
the update wiring above).  When True, the breathing pulse is skipped so
the icons hold still; the +N floaters and the on-tick flash still play
(s they are brief and informational, not ambient motion).  This matches
the codebase convention (`engine.death_fx`, `engine.skill_fx` skip
flash/shake but keep essential feedback).

## Why no per-frame allocations

* Floater slots (`_Floater`) are stored in a fixed list, recycled via
  `_next_free` (oldest slot reused if pool is full).
* The floater text + shadow surfaces are rendered once at spawn time
  (inside `_spawn_floater`, which runs on the window flush — at most
  once per ~0.5s) and reused every frame until the floater retires.
* The glow/flash rings use a single reusable SRCALPHA scratch surface
  (`_scratch`), grown lazily to the largest radius seen and then reused
  — `draw` only `fill`s, `draw.circle`s, and `blit`s; no allocations.
* `font_sm(bold=True)` is cached by `theme._font`, so no font object is
  created per frame.

## Save compatibility

The fx system is purely visual and holds no persistent state — nothing
to save.  It is safe to construct on every screen entry and discard on
exit; effects simply stop if the screen is left mid-animation.  The
delta baseline is re-snapshotted on construction, so a screen re-entry
after an ascension (which resets gold) does not show a spurious "+N".
