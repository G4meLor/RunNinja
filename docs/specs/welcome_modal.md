# Welcome Modal — integration spec

A polished offline-progress "welcome back" overlay that replaces
`GameScreen`'s inline `_draw_welcome` panel with a celebratory modal:
dim backdrop, ease-out scale-in card, count-up gold/enemies counters,
and a particle burst on collect.

## Files

| Path | Role |
|---|---|
| `ui/welcome_modal.py` | New. `WelcomeModal` — self-contained overlay. |
| `ui/screen_game.py` | Existing. Hosts the modal in place of `_draw_welcome`. |
| `core/offline.py` | Existing. `compute` / `apply` / `format_duration`. |
| `theme.py` | Existing. Cached fonts + palette used by the modal. |
| `assets.py` | Existing. `ParticleSystem` for the collect burst. |

## `WelcomeModal` API

```python
modal = WelcomeModal()
modal.set(report)            # dict from offline.compute(state); None deactivates
modal.update(dt)            # drives scale-in + count-up + collect fade
modal.draw(surf)            # dim + card + animated counters + prompt
collected = modal.handle(event)   # True on a collect click/Enter/Space
modal.active                # property — True while the overlay should show
```

- `set(report)` only activates when `report.get("applied")` is truthy, so a
  no-op return (e.g. < 60s away) leaves the modal inactive.
- The count-up is `ease_out_cubic` over 1.5s, starting 0.15s after the
  card begins its scale-in (0.35s ease-out-back). The dim is 0.25s.
- `handle` consumes the collect click **before** the count finishes, so an
  impatient player can skip ahead — the modal just marks itself collected
  and fades out; the caller still applies the full report.

## `GameScreen` integration

### Construction (`__init__`)

Replace the `welcome_pending` / `welcome_t` fields with a single modal:

```python
self.welcome_modal = WelcomeModal()
self._init_welcome()
```

`_init_welcome` becomes:

```python
def _init_welcome(self) -> None:
    from core import offline
    self.welcome_modal.set(offline.compute(self.game.state))
```

### `handle(event)`

While the modal is active it owns input — the rest of the screen does
not see the event:

```python
def handle(self, event: pygame.event.Event) -> None:
    if self.welcome_modal.active:
        if self.welcome_modal.handle(event):
            self._collect_welcome()
        return
    # ... existing tap / nav / skill handling unchanged ...
```

`_collect_welcome` applies the rewards, fires the burst, and shows a toast:

```python
def _collect_welcome(self) -> None:
    from core import offline
    report = self.welcome_modal._report  # the report we set in _init_welcome
    offline.apply(self.game.state, report)
    # Particle burst at screen center — celebratory gold.
    self.game.particles.burst(
        cfg.WINDOW_W // 2, cfg.WINDOW_H // 2,
        C.gold, count=24, speed=260, life=0.6, size=4,
    )
    from assets import play
    play("gacha", self.game.state.sound_on)
    dur = offline.format_duration(int(report.get("seconds", 0)))
    self.notify(f"While away {dur}: +{format_number(report['gold'])} gold", C.gold)
```

Notes:
- `self.game.particles` is the existing `ParticleSystem` (see
  `screen_game.draw`, which already calls `self.game.particles.draw(surf)`).
- The toast / `_welcome_notify` helper is preserved so the HUD still
  surfaces the haul after the modal closes.
- `play("gacha", ...)` reuses an existing celebratory sweep SFX.

### `update(dt)`

Drop the manual `welcome_t` ramp — the modal drives its own clock:

```python
def update(self, dt: float) -> None:
    # ... existing nav / skill / lane / toast updates ...
    self.welcome_modal.update(dt)
```

The modal deactivates itself once the collect fade-out completes, so no
extra teardown is needed.

### `draw(surf)`

Replace the `if self.welcome_pending: self._draw_welcome(surf)` block with:

```python
if self.welcome_modal.active:
    self.welcome_modal.draw(surf)
```

The modal draws its own dim backdrop over the whole window, so it must
be the last thing drawn each frame (after HUD, buttons, toasts).

### Removals

`_draw_welcome` and the `welcome_pending` / `welcome_t` fields can be
deleted once the modal is wired in. `_welcome_notify` is folded into
`_collect_welcome` (or kept and called from it).

## Behavior contract

- **Intro**: dim fades in over 0.25s; card scales in with ease-out-back
  over 0.35s; counters count up over 1.5s starting at 0.15s.
- **Idle**: once the count lands, the "tap to collect" prompt pulses
  softly until input.
- **Collect**: any left-click, Enter, or Space → rewards applied, a gold
  particle burst at screen center, a toast, and the card fades out over
  0.40s before the modal deactivates.
- **No-op return**: if `offline.compute` returns `applied=False` (e.g.
  away < 60s), `set()` leaves the modal inactive and the screen behaves
  exactly as before — no overlay, no input capture.

## Constraints honored

- Pygame primitives only (circles, rects, polygons, lines); no external
  image assets.
- Cached theme fonts (`font_sm` / `font_md` / `font_lg` / `font_xl`); no
  per-frame `SysFont` calls.
- Count-up eased over ~1.5s (`ease_out_cubic`).
- Uses `utils.format_number` and `core.offline.format_duration`.
