# Records Charts — `ui/records_charts.py`

A self-contained visual section that turns the Records dashboard from a
grid of stat cards into a real stats panel: a live gold/sec sparkline,
a zone-progress bar, a pet-collection donut, an achievement progress bar
with per-achievement icons, and a nicely formatted playtime readout.

The module is passive — it reads from `game.state` and
`core.game_economy`, draws into a rect the caller supplies, and keeps a
bounded rolling buffer of gold/sec samples. Fonts come from the cached
`theme` helpers, so no surface is created per frame.

## Component

`RecordsCharts(game)` with:

- `update(dt)` — accretes the real frame delta and, once per
  `_SAMPLE_INTERVAL` (1 s), appends `game_economy.total_gps(state)` to a
  `deque(maxlen=60)`. The buffer therefore spans exactly the last 60 s
  of gold/sec regardless of frame rate, and never grows unbounded.
- `draw(surf, rect)` — renders the whole section into `rect` using only
  pygame primitives (`pygame.draw.rect / line / polygon / circle`) and
  the cached `theme.font_*` fonts.

### Layout

`draw` splits `rect` into two rows:

- **Top row** — sparkline (wide) + playtime (narrow, ~¼ width).
- **Bottom row** — three columns of equal width: zone progress, pet
  donut, achievement bar.

### Visuals

| chart | what it draws |
|-------|---------------|
| sparkline | panel with a translucent gold area-fill + a 2px gold line through the last 60 gps samples, a bright coin-coloured dot at the most recent sample, and the current `gps/s` in the header. Falls back to a "collecting…" hint while the buffer has fewer than 2 samples. |
| playtime | panel with a bold `font_xl` main unit and a dim `font_sm` remainder. `_fmt_playtime` picks the largest sensible unit (`s` / `m` / `h` / `d`) and pushes the rest into the sub-line, so `12h 34m 16s` reads as a bold `12h` with `34m 16s` under it. |
| zone progress | panel with `Zone X/9 · <name>`, a percentage in the header, and a `draw_bar` filled to `(zone_index + zone_distance / ZONE_DISTANCE) / len(ZONES)`. Zone count and name come from `data.enemies.ZONES` / `zone_by_index`. |
| pet donut | panel with a ring donut: an outer `mp_bg` disc, an inner `panel` punch, a `soul`-coloured filled wedge sized to `owned/total`, then the hole re-punched so the fill becomes a ring segment matching the track. Center text shows `owned/total`; the right column shows `Collection`, the percentage, and `N left`. |
| achievements | panel with `Achievements` header and `unlocked/total` in gold. An icon row renders a green `✓` per unlocked achievement and a muted `○` per locked one (clipped to the panel width), followed by a `draw_bar` filled to `unlocked/total`. |

All five use `theme.draw_panel` for the card frame and `theme.draw_bar`
for the bars, so they read as part of the same UI as the rest of the
game. Colours come from the `theme.C` palette (`C.gold`, `C.exp`,
`C.soul`, `C.text_good`, `C.text_muted`, `C.mp_bg`, `C.panel` …).

## Integration

`ui/screen_records.py` owns one `RecordsCharts` and delegates the
visual section to it — leaving the existing stat-card grid untouched.

```python
# ui/screen_records.py
from ui.records_charts import RecordsCharts

class RecordsScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.btn_back = Button(...)
        self.buttons = [self.btn_back]
        self.charts = RecordsCharts(game)          # <-- new

    def update(self, dt):
        for b in self.buttons:
            b.update(dt)
        self.charts.update(dt)                     # <-- sample gps

    def draw(self, surf):
        # ... existing title + stat-card grid ...

        # Replace the single-line "Pets … Achievements …" panel with the
        # visual section.  Use the same x0 / grid_w the grid above uses.
        cr = pygame.Rect(x0, y0 + 3 * (card_h + gap) + 8, grid_w, 260)
        self.charts.draw(surf, cr)

        for b in self.buttons:
            b.draw(surf)
```

No change to `main.py` is required: `RecordsScreen` is already
constructed in `Game.__init__` and its `update` / `draw` are already
called from the main loop. The charts sample `game_economy.total_gps`,
which already accounts for buildings, the skill tree, pets, and run
upgrades, so the sparkline reflects the player's real income.
