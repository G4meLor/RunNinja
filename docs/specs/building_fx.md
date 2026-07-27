# Building purchase juice — integration spec

A new module, `ui/building_fx.py` (`BuildingFxSystem`), adds
**purchase feedback** to the Buildings screen so that buying a
building feels good instead of just updating a number.  It is pure
pygame-primitive rendering with no per-frame allocations: all transient
state lives in fixed-size pools that are reused across buys.

## What the player sees

On a successful buy of `N` levels of the selected building:

1. **Icon pulse / scale** — the building icon in the detail panel scales
   up by ~1.18x and eases back to 1.0 over ~0.45s.  A soft gold halo
   expands and fades behind the icon during the same window.
2. **Floating "+N"** — a gold "+N" rises from the icon's center, fading
   as it rises, over ~0.9s.
3. **Gold-coin burst** — ~14 coin-colored particles fountain out of the
   icon center with gravity, life ~0.6s.  Reuses the existing
   `assets.Particle` shape (gravity + life-decay alpha).
4. **G/s counter tick** — the "G/s" currency pill in the header does a
   one-shot scale pulse (1.0 -> 1.25 -> 1.0 over ~0.4s) the next time
   the screen draws, so the player sees the income counter react.

Additionally, every frame, buildings the player **can afford** get a
subtle gold glow on their list row — a low-alpha gold border that
breathes slowly so it reads as "available" without being noisy.

## `BuildingFxSystem` API

```python
class BuildingFxSystem:
    def __init__(self) -> None: ...
    # Called by BuildingsScreen._buy after a successful purchase.
    # (x, y) is the icon center in screen coords; levels_bought is N.
    def on_buy(self, bid: str, x: float, y: float, levels_bought: int) -> None: ...
    # Per-frame; advances pulse timers, floating texts, particles, and
    # the G/s pill pulse.  Safe to call with dt=0.
    def update(self, dt: float) -> None: ...
    # Draws floating texts, coin particles, and the icon pulse halo on
    # top of the detail panel.  The icon scale itself is read via
    # `pulse_scale(bid)` so the screen can blit the icon scaled.
    def draw(self, surf: pygame.Surface) -> None: ...
    # Returns the current scale factor (1.0..~1.18) for the building
    # icon in the detail panel; 1.0 when idle.  The screen uses this to
    # scale-blit the icon.
    def pulse_scale(self, bid: str) -> float: ...
    # Returns a glow alpha (0..255) for the G/s currency pill, used by
    # the screen to draw a brief highlight after a buy.
    def gs_pulse_alpha(self) -> int: ...
    # Returns a glow alpha (0..~70) for a list row the player can
    # afford.  `t` is the current clock seconds (for the breathing
    # modulation); `can_afford` gates it on/off.  Used per-row by the
    # screen when drawing the buildings list.
    def can_afford_glow(self, bid: str, rect: pygame.Rect,
                        can_afford: bool, t: float) -> int: ...
```

The system tracks per-building pulse timers in a `dict[str, float]`
keyed by building id, plus a single small float-text pool and a single
particle pool.  All pools are cleared in-place each frame; no new lists
are allocated after warmup.

## Integration into `ui/screen_buildings.py`

The screen owns one `BuildingFxSystem` instance, created in
`__init__`:

```python
from ui.building_fx import BuildingFxSystem
...
self.fx = BuildingFxSystem()
```

### `_buy` — fire the FX

After `game_economy.buy` returns `bought > 0`, the screen computes the
icon center (the detail panel icon position, `r.x + 16 + 32, r.y + 16 + 32`
where `r` is the detail panel rect) and calls:

```python
def _buy(self, n: int) -> None:
    state = self.game.state
    icon_cx = 500 + 16 + 32          # detail panel r.x + 16 + 32
    icon_cy = 100 + 16 + 32          # detail panel r.y + 16 + 32
    bought = game_economy.buy(state, self.selected, n)
    if bought > 0:
        self.fx.on_buy(self.selected, icon_cx, icon_cy, bought)
        self.game.state.save()
        self._build_list()
        self._build_buy_buttons()
```

(If `self.selected` is None the buy buttons are disabled, so the icon
position is always valid when `_buy` runs.)

### `update` — advance the FX

Add `self.fx.update(dt)` at the end of `update`.  The screen already
refreshes the buy buttons' `enabled` flag each frame; that flag is what
the FX reads for the affordability glow.

### `draw` — apply the pulse + glow

Three touch points, all in `draw`:

1. **G/s pill pulse.** After the existing
   `currency_pill(surf, x, y, "G/s", ...)` call, if
   `self.fx.gs_pulse_alpha() > 0`, draw a soft gold ring around the pill
   rect at that alpha.  The pill width is returned by `currency_pill`,
   so capture it:

   ```python
   gs_w = currency_pill(surf, x, y, "G/s",
                        format_number(game_economy.total_gps(state)),
                        (120, 220, 200))
   gs_alpha = self.fx.gs_pulse_alpha()
   if gs_alpha > 0:
       gr = pygame.Rect(x, y, gs_w, 28)
       glow = pygame.Surface((gs_w + 16, 44), pygame.SRCALPHA)
       pygame.draw.rect(glow, (255, 205, 90, gs_alpha),
                        glow.get_rect(), border_radius=22)
       surf.blit(glow, (x - 8, y - 8))
   ```

2. **Icon pulse in the detail panel.** Replace the static icon blit with
   a scale-blit driven by `pulse_scale`:

   ```python
   if self.selected:
       b = bd.BY_ID[self.selected]
       r = pygame.Rect(500, 100, 300, 200)
       draw_panel(surf, r, fill=(20, 22, 40), border=C.panel_border)
       from assets import building_surface
       icon = building_surface(b.id, 64)
       scale = self.fx.pulse_scale(b.id)
       if scale != 1.0:
           new_size = max(1, int(64 * scale))
           icon = pygame.transform.smoothscale(icon, (new_size, new_size))
       surf.blit(icon, icon.get_rect(center=(r.x + 16 + 32, r.y + 16 + 32)))
       ...  # rest of the detail panel text unchanged
   ```

   `pygame.transform.smoothscale` is only called when `scale != 1.0`,
   i.e. only during the ~0.45s pulse window — no per-frame allocation
   when idle.

3. **Affordability glow on list rows.** After the existing
   `self.list.draw(surf)` call, overlay the glow on affordable rows.
   The list exposes its item rects via `list.rect`, `list.item_h`, and
   `list.items`; the screen computes each row's affordability with
   `game_economy.can_buy(state, b.id, 1)` (the x1 cost) and asks the FX
   for a glow alpha:

   ```python
   if self.list:
       self.list.draw(surf)
       # Affordable-row glow overlay.
       import time
       t = time.monotonic()
       y0 = self.list.rect.y - int(self.list.scroll)
       for i, item in enumerate(self.list.items):
           b = item["data"]
           if state.zone_index < b.unlock_zone:
               continue
           row = pygame.Rect(self.list.rect.x, y0 + i * self.list.item_h,
                             self.list.rect.w, self.list.item_h)
           if row.bottom < self.list.rect.y or row.top > self.list.rect.bottom:
               continue
           can = game_economy.can_buy(state, b.id, 1)
           alpha = self.fx.can_afford_glow(b.id, row, can, t)
           if alpha > 0:
               glow = pygame.Surface((row.w + 8, row.h + 8), pygame.SRCALPHA)
               pygame.draw.rect(glow, (255, 205, 90, alpha),
                                glow.get_rect(), 2, border_radius=6)
               surf.blit(glow, (row.x - 4, row.y - 4))
   ```

   The glow surface is small (row-sized) and only allocated for rows
   that actually have a non-zero alpha — at most one allocation per
   affordable row per frame, and zero when nothing is affordable.

4. **FX draw.** After the detail panel and list are drawn, call
   `self.fx.draw(surf)` so floating texts and coin particles render on
   top of the panel.

## Reduced motion

The system respects `state.reduced_motion`: when true, `on_buy` skips
the coin burst and the floating "+N", and `pulse_scale` returns 1.0
(the icon does not scale).  The affordability glow is kept because it
is informational, not decorative.  The screen sets
`self.fx.reduced_motion = state.reduced_motion` once per frame (in
`update`); `on_buy`, `pulse_scale`, and `draw` all read that flag.
`can_afford_glow` is unaffected (it does not move).

## Why this shape

- **Per-building pulse timers** (not a single global pulse) so that
  rapid buys of the same building stack the pulse visibly, while buys
  of different buildings don't interfere.  Timers are a flat
  `dict[str, float]`; missing keys read as 0 (idle).
- **`pulse_scale` as a separate read** so the screen can scale-blit the
  cached icon surface rather than the FX having to know about icon
  surfaces.  Keeps the FX module free of asset imports.
- **`can_afford_glow` returns an alpha, not a bool**, so the screen can
  draw a single border rect per row instead of two states.  The
  breathing modulation is computed from `t` inside the FX so the screen
  doesn't have to track time itself.
- **No per-frame allocations when idle**: pulse timers are scalars in a
  dict, the floating-text and particle pools are cleared in-place, and
  the only `pygame.Surface` created per frame is the small glow overlay
  for rows that are actually glowing (and the icon smoothscale, only
  during the pulse window).

## Save compatibility

None.  `BuildingFxSystem` is purely visual and session-scoped; it holds
no persistent state and reads nothing from `GameState` except
`reduced_motion` (passed in by the screen).  No changes to
`core/state.py` or any save schema.
