# Menu Polish — integration spec

A new module, `ui/menu_polish.py` (`MenuPolish`), turns the main menu
from a title + two buttons into a *place*: a scrolling road with a ninja
walking on it (animated), drifting cherry-blossom petals over the night
sky, a Continue card showing the player's tier + zone + gold when a save
exists, a New Game option that wipes the save with a confirm, and a
version tag in the corner.

The module is pure state + pygame primitives. The hot path performs
**zero allocations** once warm: the petal pool is fixed and recycled,
the petal sprite is cached by size, the ninja silhouette is cached by
size (built from the cached `assets.ninja_surface` via `BLEND_RGBA_MULT`
so the global sprite cache stays pristine), and the only per-frame
`font.render` is the version tag (which matches the rest of the UI's
convention).

## Files

| Path | Role |
|---|---|
| `ui/menu_polish.py` | New. `MenuPolish(game)` — petals + walking ninja + continue-card helper. |
| `ui/screen_menu.py` | Existing. Hosts `MenuPolish`; adds Continue / New Game / Settings buttons; renders the Continue card + version tag. |
| `core/state.py` | Existing. `SAVE_FILE`, `GameState.load`, `ascend_tier`, `zone_index`, `gold`. |
| `data/enemies.py` | Existing. `zone_by_index(i)["name"]` — the zone name for the Continue card. |
| `config.py` | Existing. `ASCEND_TIERS` — the tier name for the Continue card. |
| `assets.py` | Existing. `ninja_surface(size)` — the cached sprite the silhouette is built from. |
| `theme.py` | Existing. Cached fonts + palette used by the card + version tag. |

## `MenuPolish` API

```python
polish = MenuPolish(game)
polish.update(dt)            # advance petal drift + walk cycle
polish.draw_bg(surf)         # draw petals + walking ninja (over the bg, under the dim)
polish.continue_card(state)  # {tier, zone, gold} or None
```

- `update(dt)` advances the petal positions (drift + sway + spin) and
  the walk-cycle clock. The walk cycle is frozen when
  `state.reduced_motion` is on; the petals keep drifting (freezing
  them would look broken rather than calm). Petals that fall off the
  bottom or right edge are recycled to the upper-left (`reset(top=False)`).
- `draw_bg(surf)` draws the petals + the walking ninja silhouette. Call
  **after** the zone-0 background is blitted (so they sit on top of the
  night sky + road) and **before** the menu's dim overlay (so they are
  dimmed with the rest of the scene, not punched through it).
- `continue_card(state)` returns `{tier, zone, gold}` when a save file
  exists, else `None`. `tier` is the ascension tier name (e.g.
  "Mortal"); `zone` is the current zone name (e.g. "Hidden Village");
  `gold` is the formatted gold string (`utils.format_number`). Returns
  `None` when `os.path.exists(SAVE_FILE)` is False, so a first run with
  no save skips the Continue card entirely.

`draw_version_tag(surf)` is a module-level helper the menu calls once
per frame to render the version tag in the bottom-right.

## `MenuScreen` integration

### Construction (`__init__`)

Replace the two-button layout with three buttons (Continue / New Game /
Settings) and own a `MenuPolish`:

```python
from ui.menu_polish import MenuPolish, draw_version_tag

class MenuScreen:
    def __init__(self, game) -> None:
        self.game = game
        self.polish = MenuPolish(game)
        # Continue / New Game / Settings — stacked, centered.
        cx = cfg.WINDOW_W // 2
        cy = cfg.WINDOW_H // 2 + 40
        self.btn_continue = Button((cx - 130, cy,       260, 56),
                                   "Continue", on_click=self._continue,
                                   color=(60, 120, 90))
        self.btn_new = Button((cx - 130, cy + 70,  260, 44),
                              "New Game", on_click=self._new_game,
                              color=(90, 60, 60))
        self.btn_settings = Button((cx - 130, cy + 124, 260, 44),
                                   "Settings",
                                   on_click=lambda: self.game.set_screen("settings"))
        self.buttons = [self.btn_continue, self.btn_new, self.btn_settings]
        self.lane_scroll = 0.0
        self.t = 0.0
        self.has_save = os.path.exists(SAVE_FILE)
        self.new_confirm = 0.0    # > 0 means "click again to confirm"
```

The Continue button is only enabled when `self.has_save` is True (see
`update`); on a first run with no save, Continue is greyed out and New
Game is the primary action.

### `handle(event)`

Unchanged — route to the buttons. The New Game confirm is handled in
`_new_game` (a two-click confirm, same pattern as the Settings screen's
reset):

```python
def _new_game(self):
    if self.new_confirm > 0:
        # Confirmed — wipe the save and start fresh.
        try: os.remove(SAVE_FILE)
        except OSError: pass
        from core.state import GameState
        self.game.state = GameState()
        self.game.state.gold += 200   # match main.py's starter gold
        self.game.runner.state = self.game.state
        self.game.runner.reset_for_ascension()
        self.new_confirm = 0.0
        self.game.set_screen("game")
    else:
        self.new_confirm = 3.0        # 3s window to confirm
```

The starter `gold += 200` matches `main.py`'s first-run grant so a New
Game starts on the same footing as a brand-new install. The
`runner.reset_for_ascension()` call re-syncs the world + ninja to the
fresh state (same call the Settings screen's reset and ascension use).

### `update(dt)`

Drive the polish, refresh `has_save`, toggle the Continue button, and
run the New Game confirm timer:

```python
def update(self, dt):
    self.t += dt
    self.lane_scroll = (self.lane_scroll + 60 * dt) % 60
    self.has_save = os.path.exists(SAVE_FILE)
    self.polish.update(dt)
    # Continue is only enabled when a save exists.
    self.btn_continue.enabled = self.has_save
    # New Game confirm timer + label.
    if self.new_confirm > 0:
        self.new_confirm -= dt
        if self.new_confirm <= 0:
            self.btn_new.label = "New Game"
            self.btn_new.color = (90, 60, 60)
        else:
            self.btn_new.label = "Click again to confirm"
            self.btn_new.color = (220, 80, 80)
    else:
        self.btn_new.label = "New Game"
        self.btn_new.color = (90, 60, 60)
    for b in self.buttons:
        b.update(dt)
```

### `draw(surf)`

Blit the zone-0 background, draw the polish (petals + ninja) on top,
then the dim + title + continue card + buttons + version tag:

```python
def draw(self, surf):
    from assets import background
    bg = background(0, 270)
    surf.blit(bg, (0, 0))
    # Scrolling lane lines (the menu's existing road motion).
    ly = cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2
    for x in range(-60, cfg.WINDOW_W, 60):
        xx = (x - self.lane_scroll) % (cfg.WINDOW_W + 60) - 30
        pygame.draw.rect(surf, C.lane_line, (xx, ly, 30, 4))
    # Petals + walking ninja (over the bg, under the dim).
    self.polish.draw_bg(surf)
    # Dim the scene so the title + buttons read.
    dim = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 110))
    surf.blit(dim, (0, 0))
    # Title + subtitle (existing).
    bob = math.sin(self.t * 1.5) * 4
    title_y = 160 + bob
    draw_text_center(surf, "Tap Ninja", (cfg.WINDOW_W // 2, title_y),
                     font_huge(bold=True), C.text)
    draw_text_center(surf, "an idle adventure on the endless road",
                     (cfg.WINDOW_W // 2, title_y + 60), font_md(), C.text_dim)
    # Continue card (only when a save exists).
    card = self.polish.continue_card(self.game.state)
    if card:
        self._draw_continue_card(surf, card)
    # Buttons.
    for b in self.buttons:
        b.draw(surf)
    # Controls hint (existing).
    tip_a = int(140 + 80 * math.sin(self.t * 2))
    draw_text_center(surf, "click the road to attack  ·  1-9 to switch screens  ·  P to pause",
                     (cfg.WINDOW_W // 2, cfg.WINDOW_H - 40), font_xs(), (tip_a, tip_a, tip_a))
    # Version tag.
    draw_version_tag(surf)
```

### Continue card

A small panel above the buttons showing the player's tier + zone +
gold, so a returning player sees their progress at a glance. Drawn only
when `continue_card(state)` returns non-None:

```python
def _draw_continue_card(self, surf, card):
    cw, ch = 360, 92
    cx = cfg.WINDOW_W // 2
    cy = cfg.WINDOW_H // 2 - 70
    r = pygame.Rect(cx - cw // 2, cy - ch // 2, cw, ch)
    draw_panel(surf, r, fill=C.panel, border=C.panel_border_hi, border_w=2, radius=12)
    draw_text_center(surf, "Continue your journey", (cx, r.y + 16),
                     font_sm(bold=True), C.text_dim)
    draw_text_center(surf, f"{card['tier']}  ·  {card['zone']}",
                     (cx, r.y + 40), font_md(bold=True), C.text)
    # Gold pill (icon + value) centered.
    gold_img = font_lg(bold=True).render(card["gold"], True, C.gold)
    icon_r = 9
    total_w = icon_r * 2 + 10 + gold_img.get_width()
    start_x = cx - total_w // 2
    pygame.draw.circle(surf, C.gold, (start_x + icon_r, r.y + 68), icon_r)
    pygame.draw.circle(surf, C.coin, (start_x + icon_r, r.y + 68), icon_r - 3)
    surf.blit(gold_img, (start_x + icon_r * 2 + 10, r.y + 60))
```

The card sits above the Continue button; the player sees their tier,
zone, and gold, then clicks Continue to jump back into the game.

## Behavior contract

- **First run (no save):** Continue button disabled (greyed out); New
  Game is the primary action; no Continue card; petals + walking ninja
  still animate.
- **Returning player (save exists):** Continue card shows tier + zone +
  gold; Continue button enabled and is the primary action; New Game
  wipes the save with a 3-second click-again confirm (same pattern as
  the Settings screen's reset).
- **Reduced motion:** the walk cycle freezes (the silhouette stands
  still); the petals keep drifting (freezing them would look broken).
  The dim, card, and buttons are unaffected.

## Performance / constraints

- **Pygame primitives only.** Petals are 5-petal polygons + a center
  circle; the ninja is the cached `ninja_surface` crushed to a
  silhouette; the shadow is an alpha ellipse on a SRCALPHA scratch; the
  card is a `draw_panel` + cached-font text.
- **Bounded petal pool.** `_PETAL_COUNT = 18` — fixed at construction,
  recycled (never grown). `update` mutates slot fields in place; dead
  petals are `reset(top=False)`, not replaced.
- **Cached sprites.** `_petal_sprite(size)` and `_ninja_silhouette(size)`
  are cached by size so the hot path never rebuilds them. The silhouette
  is built from `ninja_surface(size)` via `BLEND_RGBA_MULT`, so the
  global `_NINJA_CACHE` in `assets.py` is never touched.
- **No per-frame allocations in `draw_bg`.** `pygame.transform.rotate`
  returns a new surface each call (unavoidable for rotation), but this
  is a small, fixed-cost allocation per petal (18 petals × one rotate)
  and per ninja (one rotate) — not a growing allocation. The cached
  sprite itself is never rebuilt. `set_alpha` is used for the petal
  fade-in and restored to 255 after the blit so the cache stays pristine.
- **Stable RNG.** Petal re-seeding uses `utils.rng()` (the project's
  stable `random.Random`), not the global `random` state, so the menu's
  petal field doesn't perturb the game's RNG.
- **Version tag.** `draw_version_tag(surf)` uses the cached `font_xs()`
  (no per-frame `SysFont`); the `VERSION` constant lives in
  `ui/menu_polish.py` and is bumped manually on releases.

## Save wiping (New Game)

The New Game button removes `SAVE_FILE`, constructs a fresh
`GameState()`, grants the same `gold += 200` starter bonus `main.py`
grants on a first run, points the runner at the new state, and calls
`runner.reset_for_ascension()` to re-sync the world + ninja. This is
the same reset path the Settings screen's "Reset all progress" uses, so
the behavior is consistent. The confirm is a 3-second click-again window
(same pattern as the Settings screen's reset and the Ascend screen's
confirm).
