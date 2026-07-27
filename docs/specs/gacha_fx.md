# Pet Gacha Pull FX — integration spec

A new module, `engine/gacha_fx.py` (`GachaFxSystem`), replaces the Pets
screen's quick card scale-in with a **dramatic, rarity-tiered summon
sequence** so pulling a pet feels exciting instead of like a number
ticking up.

The module is **pure state + pygame primitives**. It is **not** wired
into the existing game yet; the changes below are the minimal
integration. No per-frame `Surface` allocations happen in the hot loop:
the face-down + face-up card images are pre-rendered once at `start`
(spawn time, on a button click), and the dim veil, flash scratch,
particle scratch, and glow scratch are created once (lazily) and only
`fill` / `set_alpha` / `draw` / `blit` per frame. `pet_surface` is
cached by `(pid, size)` in `assets`, so the module never re-renders a
sprite after `start`.

## What the player sees

### Single pull (`_pull1`)

1. **Dim veil** — the screen darkens under a deep-indigo veil (ramps
   over ~0.4s).
2. **Face-down suspense** (~0.4s common, up to ~1.1s for mythic) — a
   face-down card sits at center with a **building glow** that pulses
   and grows in the pet's hue (blended with the rarity color). The
   longer the suspense, the rarer the pet.
3. **Reveal flash** (~0.15s) — a bright radial flash explodes from the
   card center, the card flips from face-down to face-up with an
   ease-out scale-in (0.6x → 1.0x), and a **particle burst** (colored
   by the pet's hue) fountains from the reveal.
4. **Hold** (~0.5s common, up to ~1.2s for mythic) — the revealed card
   holds at full size showing the pet sprite + name + "NEW!" tag (if a
   new pet), the glow lingers and fades, and the burst shards settle.
5. The dim veil fades and the sequence ends.

### 10-pull (`_pull10`)

1. The same per-card sequence plays for **each of the 10 results** in
   order, but with a **short per-card hold** (~0.3s) so the sequence
   doesn't drag — the suspense + flash + brief reveal still land for
   each pet.
2. After the 10th card, a **final grid** of all 10 results slides in
   (a 5×2 layout, ease-out scale-in over ~0.45s) with a "Summon
   Results" title, then holds for ~1.2s.
3. The dim veil fades out over the last 0.3s of the grid hold so the
   screen returns cleanly.

## Rarity derivation

`data/pets.py` has no explicit rarity field, so `gacha_fx._rarity_of`
derives one from the pet's type + unlock condition + buff strength.
This mirrors the `C.rarity` palette and drives the suspense/hold
durations + the glow color:

| condition | rarity | suspense | hold (single) |
|-----------|--------|----------|----------------|
| `ptype == "mythical"` | mythic | 1.10s | 1.20s |
| `unlock.startswith("ascensions:")` | legendary | 0.90s | 1.00s |
| `unlock.startswith("skill:")` | epic | 0.70s | 0.80s |
| `buff_per_level >= 0.03` | rare | 0.55s | 0.65s |
| otherwise | common | 0.40s | 0.50s |

The glow color is `lerp_color(C.rarity[rarity], hsl(pet.hue, 0.8, 0.6),
0.4)` — the rarity tier dominates but the pet's own hue shows through,
so each pull feels distinct.

## `GachaFxSystem` API

```python
class GachaFxSystem:
    def __init__(self) -> None
    def start(self, results: list[PetPullResult]) -> None
    def update(self, dt: float) -> None
    def draw(self, surf: pygame.Surface) -> None
    def reset(self) -> None
    @property
    def active(self) -> bool          # True while the sequence is in progress
    @property
    def done(self) -> bool           # True once the sequence has completed
    reduced_motion: bool             # set from state.reduced_motion
```

- `start(results)` — arm the sequence with the list returned by
  `gacha.pull` (one) or `gacha.multi_pull` (ten). Pre-renders the
  face-down + face-up card surfaces and builds the reveal burst shards
  once here (at spawn time, not per frame). Empty list is a no-op
  (`done` immediately). If `reduced_motion` is set, each card skips the
  suspense + flash and jumps straight to the hold so the player still
  sees the result without the dramatic build.
- `update(dt)` — advance the per-card phase machine. Call once per
  frame while `active`.
- `draw(surf)` — render the dim veil, the active card (face-down
  suspense or face-up reveal + hold), the flash, the burst shards, and
  (for 10-pulls) the final grid. No-op outside an active sequence.
- `active` — True while the sequence is in progress (suspense through
  grid). The screen should only call `update`/`draw` while this is
  True.
- `done` — True once the sequence has fully completed. The screen
  should call `reset()` after consuming the sequence.
- `reduced_motion` — set from `state.reduced_motion` by the caller.
  When True the sequence short-circuits to the holds so the pulls still
  happen, just without the suspense/flash animation.

## Integration into `ui/screen_pets.py`

### 1. Construct the system

`PetsScreen.__init__` builds the system once:

```python
from engine.gacha_fx import GachaFxSystem

class PetsScreen:
    def __init__(self, game) -> None:
        ...
        self.gacha_fx = GachaFxSystem()
```

### 2. `start` is called by `_pull1` / `_pull10`

`_pull1` and `_pull10` currently set `self.anim_result` and
`self.anim_t` and let `_draw_pull_anim` render a quick card scale-in.
Replace that with `gacha_fx.start(results)`:

```python
def _pull1(self):
    state = self.game.state
    if gacha.pay(state):
        r = gacha.pull(state)
        from assets import play
        play("gacha", state.sound_on)
        self.game.state.save()
        self.gacha_fx.reduced_motion = state.reduced_motion
        self.gacha_fx.start([r])              # <-- new

def _pull10(self):
    state = self.game.state
    if gacha.pay_10(state):
        results = gacha.multi_pull(state)
        from assets import play
        play("gacha", state.sound_on)
        self.game.state.save()
        self.gacha_fx.reduced_motion = state.reduced_motion
        self.gacha_fx.start(results)          # <-- new
```

The `play("gacha", ...)` chime stays where it is — it fires once at the
start of the sequence. The system itself does not play sounds (the
existing gacha chime is the right call for the whole sequence).

### 3. Drive `update` / `draw` and block input while active

`update` advances the sequence; `draw` renders the overlay. While the
sequence is active the screen should **block input** so the player
can't toggle equip or pull again mid-reveal. The existing
`self.anim_result` gate can be replaced by `self.gacha_fx.active`:

```python
def handle(self, event):
    # Block all input while the gacha FX sequence is playing.
    if self.gacha_fx.active:
        return
    for b in self.buttons:
        b.handle(event)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        for pid, r in self.pet_rects.items():
            if r.collidepoint(event.pos):
                self._toggle_equip(pid)
                break

def update(self, dt):
    state = self.game.state
    self.btn_pull.enabled = gacha.can_afford(state) and not self.gacha_fx.active
    self.btn_pull10.enabled = gacha.can_afford_10(state) and not self.gacha_fx.active
    for b in self.buttons:
        b.update(dt)
    self.gacha_fx.update(dt)
    if self.gacha_fx.done:
        self.gacha_fx.reset()

def draw(self, surf):
    ... existing grid ...
    # Gacha FX overlay on top of everything.
    self.gacha_fx.draw(surf)
    for b in self.buttons:
        b.draw(surf)
```

The pull buttons are disabled while the sequence is active (and the
`handle` guard short-circuits anyway, so a click can't fire a new pull
mid-reveal). The old `self.anim_result` / `self.anim_t` /
`_draw_pull_anim` are no longer needed and can be removed once the FX
system is wired.

### 4. Draw order

1. Background gradient + title + currency pills (unchanged).
2. Pet grid (unchanged).
3. `self.gacha_fx.draw(surf)` — dim veil, active card, flash, shards,
   and (for 10-pulls) the final grid, all on top.
4. Buttons (unchanged — they're disabled while the sequence is active,
   but drawing them on top keeps the layout readable).

## Performance / constraints

- **pygame primitives only.** The cards, glow, flash, shards, and grid
  are all `pygame.draw.rect` / `circle` / `polygon` + `smoothscale` +
  `set_alpha` + `blit`. No external image assets.
- **cached sprites.** `assets.pet_surface(pid, hue, size)` is cached by
  `(pid, size)`; the module requests 120px (single-pull card) and 96px
  (grid cell) directly, so no per-frame `smoothscale` of the *sprite* is
  needed (the 96px sprite is itself the cache hit). The face-up card
  pre-render at `start` is the only place the sprite is blitted.
- **cached fonts.** All text uses `theme.font_*` helpers, which cache
  by `(size, bold)` in `theme._FONTS`.
- **no per-frame allocations in `draw`.** The dim veil, flash scratch,
  particle scratch, and glow scratch are created once (lazily) and
  reused; only `fill` / `set_alpha` / `draw` / `blit` run per frame.
  The face-down + face-up card surfaces are pre-rendered once at
  `start` (one allocation, at spawn time). `smoothscale` returns a new
  Surface (the cached card is never mutated), but the scale is clamped
  so we never smoothscale to 0.
- **no per-frame allocations in `update`.** The shard list is built once
  at `start` and mutated in place; the cull rebuild (when shards die)
  is bounded by the small, transient count (≤ 36).
- **bounded shard counts.** 22 for a single pull, 36 for a mythic
  single pull, 10 per card in a 10-pull (so the sequence doesn't get
  noisy across 10 cards).

## Save compatibility

The FX system is purely visual and holds no persistent state — nothing
to save. It is safe to construct on every screen entry and discard on
exit; the sequence simply stops if the screen is left mid-animation
(call `reset()` on the next entry, or let `start` overwrite the stale
state).

## Tunables

The timing / layout / particle constants live at the top of
`engine/gacha_fx.py`:

| constant | default | meaning |
|----------|---------|---------|
| `_SUSPENSE_COMMON` | 0.40s | face-down suspense for a common pet |
| `_SUSPENSE_RARE` | 0.55s | … rare |
| `_SUSPENSE_EPIC` | 0.70s | … epic |
| `_SUSPENSE_LEGENDARY` | 0.90s | … legendary |
| `_SUSPENSE_MYTHIC` | 1.10s | … mythic |
| `_FLASH_DUR` | 0.15s | reveal flash window |
| `_HOLD_COMMON` | 0.50s | face-up hold for a common pet (single pull) |
| `_HOLD_RARE` | 0.65s | … rare |
| `_HOLD_EPIC` | 0.80s | … epic |
| `_HOLD_LEGENDARY` | 1.00s | … legendary |
| `_HOLD_MYTHIC` | 1.20s | … mythic |
| `_HOLD_MULTIPULL` | 0.30s | per-card hold in a 10-pull (short, snappy) |
| `_GRID_IN_DUR` | 0.45s | final 10-pull grid scale-in |
| `_GRID_HOLD_DUR` | 1.20s | final grid hold before done |
| `_CARD_W` / `_CARD_H` | 360 / 300 | single-pull card size |
| `_GRID_COLS` / `_GRID_ROWS` | 5 / 2 | final 10-pull grid layout |
| `_GRID_CARD_W` / `_GRID_CARD_H` | 180 / 112 | final grid cell size |
| `_BURST_COUNT_SINGLE` | 22 | shards per single-pull reveal |
| `_BURST_COUNT_MULTIPULL` | 10 | shards per card in a 10-pull |
| `_BURST_COUNT_MYTHIC` | 36 | shards for a mythic single-pull |

Tune by editing the constants; no other module needs to change.

## Accessibility

Set `GachaFxSystem.reduced_motion = True` (the screen sets it from
`state.reduced_motion` at `start`) to skip the suspense + flash for
every card and jump straight to the hold. The face-up card + "NEW!" tag
+ final grid still show, so the player sees the result — just without
the dramatic build, the building glow, the flash, and the particle
burst. The dim veil still ramps + fades so the reveal reads as a
distinct moment, but it's gentler (the suspense ramp that drives the
dim ramp is skipped, so the dim snaps to its hold level immediately).
