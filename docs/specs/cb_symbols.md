# Color-blind-safe symbols — integration spec

A new module, `ui/cb_symbols.py`, adds **shape symbols** alongside the
existing rarity and skill-branch colors so color-blind players can
distinguish them by shape alone. Today rarities (`C.rarity` in
`theme.py`) and branches (`branch_color` in `data/skill_tree.py`) are
color-only; this layer keeps the colors and adds a redundant shape cue.

All rendering uses pygame primitives on a per-pixel-alpha surface, and
every surface is cached by `(kind, key, size)` — zero per-frame
allocations after the first call.

## The module

`ui/cb_symbols.py` exposes:

| function | purpose |
|----------|---------|
| `rarity_symbol(rarity, size=20) -> pygame.Surface` | a small surface with the shape for that rarity |
| `branch_symbol(branch, size=20) -> pygame.Surface` | a small surface with the shape for that branch |
| `clear_caches()` | drop all cached surfaces (call after `pygame.display.set_mode`) |

Surfaces are `(size, size)`, `SRCALPHA`, transparent background, drawn in
a high-contrast neutral (`(245, 248, 255)`) with a dark outline
(`(20, 22, 36)`) so the **shape** is the signal, not the hue. Callers
that want the symbol tinted to match the rarity/branch color can
re-tint, but the default is intentionally color-neutral so it works on
any background and against the existing color cue.

### Rarity shapes

| rarity     | shape     |
|------------|-----------|
| common     | circle    |
| rare       | triangle  |
| epic       | square    |
| legendary  | diamond   |
| mythic     | star      |

Unknown rarities fall back to the `common` circle.

### Branch shapes

| branch     | shape     |
|------------|-----------|
| offense    | sword     |
| economy    | coin      |
| elixir     | flask     |
| energy     | bolt      |
| firefly    | light     |
| abilities  | star      |
| godai      | pentagon  |

Unknown branches fall back to the `offense` sword.

## Wiring into `screen_pets.py`

The Pets screen shows pet cards in a grid. Each card already uses the
rarity color for the border when equipped; add the rarity symbol next to
the pet name so the rarity is readable without color.

At the top of `ui/screen_pets.py`:

```python
from ui.cb_symbols import rarity_symbol
```

In `PetsScreen.draw`, inside the per-pet loop, after drawing the pet
name, blit the rarity symbol to the left of the name. The pet's rarity
is derived from its `ptype` / unlock condition (or wherever the rarity
is assigned — see note below). For a pet with rarity `rarity`:

```python
draw_text(surf, p.name, (r.x + 64, r.y + 12), font_sm(bold=True), C.text)
rsym = rarity_symbol(p.rarity, 16)
surf.blit(rsym, (r.x + 64 - 20, r.y + 14))
```

If the pet does not yet carry a `rarity` field, derive one from the
existing data (e.g. `mythical` ptype → `mythic`, others → `rare`), or add
a `rarity` column to `data/pets.py` `PetDef`. The symbol API itself is
rarity-agnostic — pass any string in `{"common","rare","epic",
"legendary","mythic"}`.

In the pull-animation overlay (`_draw_pull_anim`), add the rarity symbol
above the pet name so a newly pulled pet's rarity is visible regardless
of color:

```python
rsym = rarity_symbol(p.rarity, 24)
surf.blit(rsym, rsym.get_rect(center=(cx, rect.y + 110)))
draw_text_center(surf, p.name, (cx, rect.y + 230), font_lg(bold=True), C.text)
```

## Wiring into `screen_skilltree.py`

The skill-tree screen draws one column per branch with the branch color
on the header and on each node. Add the branch symbol to the column
header so the branch is readable without color.

At the top of `ui/screen_skilltree.py`:

```python
from ui.cb_symbols import branch_symbol
```

In `SkillTreeScreen.draw`, inside the per-branch loop, after drawing the
branch header, blit the branch symbol to the left of the branch name:

```python
col = st.branch_color(branch)
header = pygame.Rect(bx + 10, top_y, col_w - 20, 30)
draw_panel(surf, header, fill=(col[0] // 5, col[1] // 5, col[2] // 5), border=col)
bsym = branch_symbol(branch, 18)
surf.blit(bsym, (header.x + 6, header.centery - bsym.get_height() // 2))
draw_text_center(surf, branch.capitalize(),
                 (header.centerx + 6, header.centery),
                 font_sm(bold=True), col)
```

(Shift the title right by the symbol width so it stays centered in the
remaining space, or left-align the title to the right of the symbol —
either reads fine.)

Optionally, also blit a small branch symbol at the top-left of each
node so a node's branch is identifiable even when the column header is
scrolled off-screen:

```python
bsym = branch_symbol(branch, 12)
surf.blit(bsym, (r.x + 4, r.y + 4))
```

## Size guidance

| use site | suggested size |
|----------|----------------|
| pet card next to name | 16 |
| pull-anim overlay | 24 |
| skill-tree branch header | 18 |
| skill-tree node corner | 12 |

Symbols are cached per `(kind, key, size)`, so a handful of sizes is
fine; avoid a unique size per call site.

## Cache lifecycle

Surfaces are created lazily on first request and reused forever. They
are plain `SRCALPHA` surfaces independent of the display format, so no
re-creation is needed on resolution changes — but call
`clear_caches()` after `pygame.display.set_mode` if you want to drop
them on a display-format change.

## Save compatibility

The symbol system is purely visual and holds no persistent state —
nothing to save. It is safe to import at module load; the surfaces are
only created on first call, after `pygame.init`.

## Why shapes (not just colors)

Rarity and branch are the two places the game communicates tier/category
by hue alone. Red-green color blindness (deuteranopia/protanopia) makes
the `rare` (blue) vs `epic` (purple) and `offense` (red) vs `economy`
(gold) distinctions hard to read; achromatopsia makes all of them hard.
A shape per category is a redundant, color-blind-safe cue that costs one
blit per element.
