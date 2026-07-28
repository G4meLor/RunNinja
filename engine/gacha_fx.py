"""Pet gacha pull FX: a dramatic, rarity-tiered summon sequence.

Replaces the quick card scale-in with a suspenseful reveal:

  face-down suspense (~0.4s, longer for rarer pets)
      A face-down card sits at center with a building glow that pulses
      in the pet's hue.  A dim veil darkens the backdrop so the reveal
      lands hard.

  reveal flash (~0.15s)
      A bright radial flash explodes from the card, the card flips from
      face-down to face-up with an ease-out scale-in, and a particle
      burst (colored by the pet's hue) fountains from the reveal.

  hold (~0.5s, longer for rarer pets)
      The revealed card holds at full size, the pet sprite + name +
      "NEW!" tag (if applicable) sit on top, and the glow lingers.

For 10-pulls the sequence plays per-card (a brief suspense + reveal
each), then a final grid of all 10 results slides in and holds.

Pure state + pygame primitives.  No per-frame Surface allocations in
the hot loop:

  * The face-down + face-up card images are pre-rendered once at
    ``start`` (spawn time, on a button click) and reused.
  * The dim veil, the flash scratch, the particle scratch, and the
    glow scratch are created once (lazily) and only ``fill`` /
    ``set_alpha`` / ``draw`` / ``blit`` per frame.
  * Particle / burst lists are built once at ``start`` and mutated in
    place; the cull rebuild is bounded by the small, transient count.
  * ``pet_surface`` is cached by ``(pid, size)`` in ``assets``; the
    module never re-renders a sprite after ``start``.

Integration (see ``docs/specs/gacha_fx.md``):

    from engine.gacha_fx import GachaFxSystem
    fx = GachaFxSystem()
    fx.start(results)              # list[PetPullResult]
    while fx.active:
        fx.update(dt)
        fx.draw(surf)
    # fx.done is True once the sequence finishes
"""
from __future__ import annotations

import math

import pygame

import config as cfg
from assets import hsl, pet_surface
from theme import (
    C, font_xs, font_sm, font_md, font_lg, font_xl,
    draw_text_center,
)
from utils import rng, clamp, ease_out_cubic, ease_in_out_cubic, lerp, lerp_color
from core.gacha import PetPullResult
from data import pets as pet_def


# ---------------------------------------------------------------------------
# Phase constants (small ints for cheap comparisons)
# ---------------------------------------------------------------------------
_IDLE = 0
_SUSPENSE = 1
_FLASH = 2
_HOLD = 3
_GRID = 4
_DONE = 5

# --- Durations (seconds) ----------------------------------------------------
# Per-card suspense: 0.4s common, scaling up with rarity so rarer pets
# get a longer, more agonizing build.  ``_suspense_dur(rarity)`` returns
# the value; the constants here are the per-rarity ceilings.
_SUSPENSE_COMMON = 0.40
_SUSPENSE_RARE = 0.55
_SUSPENSE_EPIC = 0.70
_SUSPENSE_LEGENDARY = 0.90
_SUSPENSE_MYTHIC = 1.10

_FLASH_DUR = 0.15          # the reveal flash window
_FLASH_PEAK = 0.04         # the flash hits max brightness early

# Per-card hold: 0.5s common, longer for rarer pets so the player has
# time to appreciate a rare pull.  Multi-pulls use the shortest hold so
# the sequence doesn't drag across 10 cards.
_HOLD_COMMON = 0.50
_HOLD_RARE = 0.65
_HOLD_EPIC = 0.80
_HOLD_LEGENDARY = 1.00
_HOLD_MYTHIC = 1.20
_HOLD_MULTIPULL = 0.30      # per-card hold in a 10-pull (short, snappy)

_GRID_IN_DUR = 0.45         # final 10-pull grid scale-in
_GRID_HOLD_DUR = 1.20       # final grid hold before done

# --- Rarity-scaled screen shake + hit-stop (gp-gacha-fairness) ---------------
# Rarer pets shake harder + hitstop longer so the reveal lands with weight.
# The caller (Game.shake / Game.hitstop_for) gates these on the render tier
# (low disables), so the values here are the per-rarity magnitudes.
SHAKE_AMPS = {
    "common": 0.0,
    "rare": 2.0,
    "epic": 4.0,
    "legendary": 7.0,
    "mythic": 10.0,
}
HITSTOP_DURS = {
    "common": 0.0,
    "rare": 0.02,
    "epic": 0.05,
    "legendary": 0.09,
    "mythic": 0.14,
}

# The skip-allowed window: after this many seconds into a card's suspense,
# a skip input (click/key) jumps the card straight to the hold. The tell
# (rarity color in the glow) is visible by this point.
_SKIP_TELL = 0.15

# --- Layout -----------------------------------------------------------------
_CARD_W, _CARD_H = 360, 300
_CARD_RADIUS = 16

# 10-pull final grid: 5 columns x 2 rows.
_GRID_COLS = 5
_GRID_ROWS = 2
_GRID_CARD_W = 180
_GRID_CARD_H = 112
_GRID_GAP = 14

# --- Particle counts (bounded; built once at start) -------------------------
_BURST_COUNT_SINGLE = 22
_BURST_COUNT_MULTIPULL = 10
_BURST_COUNT_MYTHIC = 36      # extra drama for a mythic single-pull

# --- Scratch sizes ----------------------------------------------------------
# The flash scratch holds the reveal shockwave ring (radius <= 200).
_SCRATCH_FLASH = 440
_FLASH_MAX_R = (_SCRATCH_FLASH - 6) // 2
# The particle scratch holds one particle glow (~10 px radius).
_SCRATCH_PARTICLE = 24
# The glow scratch holds the per-card building glow (card-sized + pad).
_SCRATCH_GLOW_W = _CARD_W + 120
_SCRATCH_GLOW_H = _CARD_H + 120


# ---------------------------------------------------------------------------
# Rarity derivation
# ---------------------------------------------------------------------------
def _rarity_of(pet: pet_def.PetDef) -> str:
    """Map a pet to a rarity tier.

    The pet data has no explicit rarity field, so we derive one from the
    pet's type + unlock condition + buff strength.  This mirrors the
    game's rarity palette (``C.rarity``) and drives the suspense/hold
    durations + the glow color.

    mythical  -> ``mythic``  (the Dragon — the only mythical pet).
    ascension-gated -> ``legendary`` (hard to get, permanent unlock).
    skill-gated -> ``epic`` (requires a skill-tree node).
    buff >= 0.03 -> ``rare`` (stronger passive).
    otherwise -> ``common``.
    """
    if pet.ptype == "mythical":
        return "mythic"
    if pet.unlock.startswith("ascensions:"):
        return "legendary"
    if pet.unlock.startswith("skill:"):
        return "epic"
    if pet.buff_per_level >= 0.03:
        return "rare"
    return "common"


def _suspense_dur(rarity: str) -> float:
    return {
        "common": _SUSPENSE_COMMON,
        "rare": _SUSPENSE_RARE,
        "epic": _SUSPENSE_EPIC,
        "legendary": _SUSPENSE_LEGENDARY,
        "mythic": _SUSPENSE_MYTHIC,
    }.get(rarity, _SUSPENSE_COMMON)


def _hold_dur(rarity: str, multi: bool) -> float:
    if multi:
        return _HOLD_MULTIPULL
    return {
        "common": _HOLD_COMMON,
        "rare": _HOLD_RARE,
        "epic": _HOLD_EPIC,
        "legendary": _HOLD_LEGENDARY,
        "mythic": _HOLD_MYTHIC,
    }.get(rarity, _HOLD_COMMON)


def _rarity_color(rarity: str, hue: int) -> tuple[int, int, int]:
    """The glow color for a card: the rarity palette color blended toward
    the pet's hue so each pull feels distinct but reads as its tier."""
    base = C.rarity.get(rarity, C.rarity["common"])
    pet_tint = hsl(hue, 0.8, 0.6)
    # 60% rarity color, 40% pet hue — the rarity tier dominates but the
    # pet's own color shows through.
    return lerp_color(base, pet_tint, 0.4)


# ---------------------------------------------------------------------------
# Particle (one shard of the reveal burst)
# ---------------------------------------------------------------------------
class _Shard:
    """One colored shard from the reveal burst.  Built once at start;
    mutated each tick."""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color")

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 life: float, size: float, color: tuple[int, int, int]) -> None:
        self.x = x; self.y = y
        self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.size = size; self.color = color


# ---------------------------------------------------------------------------
# Per-card state (built once at start; mutated each tick)
# ---------------------------------------------------------------------------
class _Card:
    """State for one card in the sequence.

    Holds the pre-rendered face-down + face-up surfaces (built once at
    ``start``), the per-card phase timers, and the reveal burst shards.
    """
    __slots__ = (
        "result", "pet", "rarity", "color", "is_new",
        "suspense_dur", "hold_dur",
        "face_down", "face_up", "name_img", "new_img",
        "shards", "flash_life", "flash_max",
        "t", "phase", "revealed",
    )

    def __init__(self) -> None:
        self.result: PetPullResult | None = None
        self.pet: pet_def.PetDef | None = None
        self.rarity: str = "common"
        self.color: tuple[int, int, int] = (200, 200, 220)
        self.is_new: bool = False
        self.suspense_dur: float = _SUSPENSE_COMMON
        self.hold_dur: float = _HOLD_COMMON
        self.face_down: pygame.Surface | None = None
        self.face_up: pygame.Surface | None = None
        self.name_img: pygame.Surface | None = None
        self.new_img: pygame.Surface | None = None
        self.shards: list[_Shard] = []
        self.flash_life: float = 0.0
        self.flash_max: float = 0.0
        self.t: float = 0.0
        self.phase: int = _SUSPENSE
        self.revealed: bool = False


# ---------------------------------------------------------------------------
# The system
# ---------------------------------------------------------------------------
class GachaFxSystem:
    """Drives the gacha pull sequence.

    Lifecycle
    ---------
    1. ``start(results)`` -- arm the sequence with a list of
       ``PetPullResult`` (one for a single pull, ten for a 10-pull).
       Pre-renders the face-down + face-up card surfaces and builds the
       reveal burst shards (one allocation, at start -- not per frame).
    2. each frame: ``update(dt)`` -- advance the per-card phase machine.
    3. each frame: ``draw(surf)`` -- render the dim veil, the active
       card (face-down suspense or face-up reveal + hold), the flash,
       the burst shards, and (for 10-pulls) the final grid.
    4. ``active`` is True while the sequence is in progress; ``done``
       is True once it has fully completed.

    The caller is responsible for blocking screen input while
    ``active`` is True (the spec documents the integration).
    """

    def __init__(self) -> None:
        self._phase: int = _IDLE
        self._t: float = 0.0                  # elapsed in the current phase
        self._cards: list[_Card] = []
        self._idx: int = 0                    # index of the active card
        self._multi: bool = False             # True for a 10-pull
        # Reusable scratch surfaces -- created lazily so we don't allocate
        # before ``pygame.display.set_mode``.  All are kept for the life
        # of the system and only mutated (set_alpha / fill / draw / blit)
        # per frame.
        self._dim: pygame.Surface | None = None
        self._flash_scratch: pygame.Surface | None = None
        self._particle_scratch: pygame.Surface | None = None
        self._glow_scratch: pygame.Surface | None = None
        # Reduced-motion gate (set from state.reduced_motion by the caller).
        # When True the sequence short-circuits: each card skips the
        # suspense + flash and jumps straight to the hold, so the player
        # still sees the result without the dramatic build.
        self.reduced_motion: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        """True while the sequence is in progress (suspense through grid)."""
        return self._phase in (_SUSPENSE, _FLASH, _HOLD, _GRID)

    @property
    def done(self) -> bool:
        """True once the sequence has fully completed."""
        return self._phase == _DONE

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def start(self, results: list[PetPullResult]) -> None:
        """Begin the pull sequence.

        ``results`` is the list returned by ``gacha.pull`` (one) or
        ``gacha.multi_pull`` (ten).  Empty lists are a no-op.

        Pre-renders the face-down + face-up card surfaces and builds the
        reveal burst shards once here (at spawn time, on a button click
        -- not in the hot loop).  If ``reduced_motion`` is set, each card
        skips the suspense + flash and jumps straight to the hold so the
        player still sees the result without the animation.
        """
        if not results:
            self._phase = _DONE
            return
        self._multi = len(results) > 1
        self._t = 0.0
        self._idx = 0

        # Build a _Card for each result.  The face-down surface is shared
        # across all cards (it's identical -- a plain card back); the
        # face-up surface is per-card (it shows the pet sprite + name).
        face_down = self._build_face_down()
        cards: list[_Card] = []
        for r in results:
            pet = pet_def.BY_ID.get(r.pet_id)
            if pet is None:
                # Defensive: skip unknown pet ids (gacha never produces
                # these, but be safe).
                continue
            c = _Card()
            c.result = r
            c.pet = pet
            c.rarity = _rarity_of(pet)
            c.color = _rarity_color(c.rarity, pet.hue)
            c.is_new = bool(r.is_new)
            c.suspense_dur = _suspense_dur(c.rarity)
            c.hold_dur = _hold_dur(c.rarity, self._multi)
            c.face_down = face_down
            c.face_up = self._build_face_up(pet, c.rarity, c.is_new)
            c.name_img = font_lg(bold=True).render(pet.name, True, C.text)
            c.new_img = (font_md(bold=True).render("NEW!", True, C.text_good)
                         if c.is_new else None)
            # Build the reveal burst shards (one allocation, at start).
            c.shards = self._build_shards(c.color, self._multi, c.rarity)
            c.flash_max = _FLASH_DUR
            c.flash_life = 0.0
            c.t = 0.0
            c.phase = _SUSPENSE
            c.revealed = False
            if self.reduced_motion:
                # Skip suspense + flash; jump straight to the hold.
                c.phase = _HOLD
                c.revealed = True
            cards.append(c)
        self._cards = cards

        if not cards:
            self._phase = _DONE
            return

        # If reduced motion, the first card is already in HOLD; otherwise
        # start the sequence at the first card's suspense, OR jump straight
        # to the grid for a 10-pull (batch-summary-first: show all 10
        # results at once, not card-by-card).
        if self.reduced_motion:
            self._phase = self._cards[0].phase
        elif self._multi:
            # Batch-summary-first: the 10-pull opens on the grid of all
            # results. The caller can still drive card-by-card via skip()
            # if it wants the dramatic path, but the default is the grid.
            self._phase = _GRID
            self._t = 0.0
        else:
            self._phase = _SUSPENSE

    def reset(self) -> None:
        """Return to idle (call after the caller consumes the sequence)."""
        self._phase = _IDLE
        self._t = 0.0
        self._cards = []
        self._idx = 0
        self._multi = False

    # ------------------------------------------------------------------
    # Skip (gp-gacha-fairness)
    # ------------------------------------------------------------------
    def skip(self) -> bool:
        """Skip the current card's suspense/flash straight to the hold.

        Activates only after the rarity tell (``_SKIP_TELL`` seconds into
        the card's suspense) so the player has seen the rarity color
        before they can skip. Returns ``True`` if a skip happened,
        ``False`` if it was too early or not in a skippable phase.

        For a 10-pull in the grid phase, skip() advances straight to
        done (dismiss the batch summary).
        """
        if self._phase == _GRID:
            self._phase = _DONE
            return True
        if self._phase not in (_SUSPENSE, _FLASH):
            return False
        card = self._active_card()
        if card is None:
            return False
        # Only allow the skip after the rarity tell is visible (the glow
        # has been on screen long enough to read the color).
        if card.phase == _SUSPENSE and card.t < _SKIP_TELL:
            return False
        # Jump to the hold: reveal the card, fire the burst, skip the
        # remaining suspense + flash.
        card.phase = _HOLD
        card.t = 0.0
        card.revealed = True
        card.flash_life = 0.0
        self._phase = _HOLD
        return True

    # ------------------------------------------------------------------
    # Rarity-scaled shake + hit-stop (gp-gacha-fairness)
    # ------------------------------------------------------------------
    def shake_amp(self) -> float:
        """The screen-shake amplitude for the active card's rarity.

        0.0 for common, scaling up for rarer pets. The caller (Game.shake)
        gates this on the render tier (low disables shake).
        """
        card = self._active_card()
        if card is None:
            return 0.0
        return SHAKE_AMPS.get(card.rarity, 0.0)

    def hitstop_dur(self) -> float:
        """The hit-stop duration for the active card's rarity.

        0.0 for common, scaling up for rarer pets. The caller
        (Game.hitstop_for) gates this on the render tier.
        """
        card = self._active_card()
        if card is None:
            return 0.0
        return HITSTOP_DURS.get(card.rarity, 0.0)

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance the sequence by ``dt`` seconds.  Call once per frame."""
        if self._phase == _IDLE or self._phase == _DONE:
            return

        # Advance the active card.
        if self._phase in (_SUSPENSE, _FLASH, _HOLD):
            card = self._active_card()
            if card is None:
                self._advance_or_grid()
                return
            card.t += dt

            if card.phase == _SUSPENSE:
                if card.t >= card.suspense_dur:
                    # Reveal: flip to flash, fire the burst, mark revealed.
                    card.phase = _FLASH
                    card.t = 0.0
                    card.revealed = True
                    card.flash_life = card.flash_max
            elif card.phase == _FLASH:
                # Advance the flash + the burst shards.
                if card.flash_life > 0.0:
                    card.flash_life -= dt
                self._update_shards(card, dt)
                if card.t >= _FLASH_DUR:
                    card.phase = _HOLD
                    card.t = 0.0
            elif card.phase == _HOLD:
                self._update_shards(card, dt)
                if card.t >= card.hold_dur:
                    # Move to the next card, or the final grid for 10-pulls.
                    self._idx += 1
                    if self._idx >= len(self._cards):
                        if self._multi:
                            self._phase = _GRID
                            self._t = 0.0
                        else:
                            self._phase = _DONE
                    else:
                        # Next card begins its suspense (or hold, if
                        # reduced motion).
                        nxt = self._cards[self._idx]
                        self._phase = nxt.phase
                        nxt.t = 0.0
        elif self._phase == _GRID:
            self._t += dt
            # Keep the last card's burst shards alive during the grid-in
            # so the reveal particles linger over the grid.
            if self._cards:
                self._update_shards(self._cards[-1], dt)
            if self._t >= _GRID_IN_DUR + _GRID_HOLD_DUR:
                self._phase = _DONE

    def _active_card(self) -> _Card | None:
        if 0 <= self._idx < len(self._cards):
            return self._cards[self._idx]
        return None

    def _advance_or_grid(self) -> None:
        self._idx += 1
        if self._idx >= len(self._cards):
            if self._multi:
                self._phase = _GRID
                self._t = 0.0
            else:
                self._phase = _DONE
        else:
            nxt = self._cards[self._idx]
            self._phase = nxt.phase
            nxt.t = 0.0

    def _update_shards(self, card: _Card, dt: float) -> None:
        """Advance the reveal burst shards for one tick.

        Each shard flies out on its initial velocity, falls under gravity,
        and fades as its life ticks down.  The list is rebuilt only when
        culled (bounded by the small, transient count).
        """
        for s in card.shards:
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.vy += 260.0 * dt
            s.vx *= math.exp(-dt * 2.0)
            s.life -= dt
        if any(s.life <= 0.0 for s in card.shards):
            card.shards = [s for s in card.shards if s.life > 0.0]

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface) -> None:
        """Draw the sequence overlay.  No-op outside an active sequence."""
        if self._phase == _IDLE or self._phase == _DONE:
            return

        # --- Dim veil (ramps in over the first card's suspense, holds
        # through the sequence, fades out at the very end of the grid). ---
        self._draw_dim(surf)

        if self._phase in (_SUSPENSE, _FLASH, _HOLD):
            card = self._active_card()
            if card is not None:
                self._draw_card(surf, card)
        elif self._phase == _GRID:
            # Final 10-pull grid: scale-in + hold, with the last card's
            # burst shards lingering on top.
            self._draw_grid(surf)
            if self._cards:
                self._draw_shards(surf, self._cards[-1])

    # ------------------------------------------------------------------
    # Phase renderers
    # ------------------------------------------------------------------
    def _draw_dim(self, surf: pygame.Surface) -> None:
        """Overlay the dim veil.

        Ramps from 0 -> ~170 alpha over the first card's suspense, then
        holds for the rest of the sequence so the reveal lands on a dark
        backdrop.  Fades out over the last 0.3s of the grid hold so the
        screen returns cleanly.  The dim surface is a plain (non-SRCALPHA)
        full-screen Surface created once and reused; only ``set_alpha``
        is called per frame.
        """
        # Ramp during the first card's suspense, then hold.
        first = self._cards[0] if self._cards else None
        if self._phase == _SUSPENSE and first is not None and first.phase == _SUSPENSE:
            p = first.t / max(0.01, first.suspense_dur)
            p = clamp(p, 0.0, 1.0)
            p = p * p * (3 - 2 * p)        # smoothstep
            alpha = int(170 * p)
        elif self._phase == _GRID:
            # Fade out over the last 0.3s of the grid hold.
            remaining = (_GRID_IN_DUR + _GRID_HOLD_DUR) - self._t
            if remaining < 0.3:
                alpha = int(170 * clamp(remaining / 0.3, 0.0, 1.0))
            else:
                alpha = 170
        else:
            alpha = 170
        if alpha <= 0:
            return
        veil = self._get_dim()
        veil.set_alpha(alpha)
        surf.blit(veil, (0, 0))

    def _draw_card(self, surf: pygame.Surface, card: _Card) -> None:
        """Draw the active card: face-down suspense or face-up reveal."""
        cx, cy = cfg.WINDOW_W // 2, cfg.WINDOW_H // 2

        # --- Building glow (pulses in the card's color during suspense,
        # lingers + fades during the hold). ---
        self._draw_glow(surf, cx, cy, card)

        if card.phase == _SUSPENSE:
            # Face-down card with a subtle pulse.
            pulse = 1.0 + 0.04 * math.sin(card.t * 10.0)
            self._blit_card_scaled(surf, card.face_down, cx, cy, pulse, 255)
            return

        # --- Reveal flash (expanding shockwave ring in the card color). ---
        if card.flash_life > 0.0 and card.flash_max > 0.0:
            self._draw_flash(surf, cx, cy, card)

        # --- Face-up card: scale-in with ease-out over the flash window,
        # then hold at full size. ---
        if card.phase == _FLASH:
            p = clamp(card.t / _FLASH_DUR, 0.0, 1.0)
            scale = 0.6 + 0.4 * ease_out_cubic(p)        # 0.6 -> 1.0
            alpha = int(255 * ease_out_cubic(p))
        else:  # _HOLD
            scale = 1.0
            alpha = 255
        self._blit_card_scaled(surf, card.face_up, cx, cy, scale, alpha)

        # --- Burst shards (colored by the pet's hue). ---
        self._draw_shards(surf, card)

    def _draw_glow(self, surf: pygame.Surface, cx: int, cy: int,
                   card: _Card) -> None:
        """Draw the building glow behind the card.

        During suspense the glow pulses + grows in the card's **rarity
        color** from t=0 (the early tell -- the player can read the
        rarity tier from the glow color before the card flips). During
        the flash + hold it lingers at full size, fading out over the
        hold so the reveal settles. Drawn via the reusable glow scratch
        (cleared per frame).
        """
        if card.phase == _SUSPENSE:
            # Early tell: the glow starts at the rarity color from t=0
            # (not a neutral color that fades in). The opacity ramps up
            # so the color is visible immediately, then intensifies.
            p = clamp(card.t / max(0.01, card.suspense_dur), 0.0, 1.0)
            p = ease_in_out_cubic(p)
            radius = int(60 + 120 * p)         # 60 -> 180
            # Alpha starts at a visible floor (60) so the rarity color
            # is readable from t=0, then ramps up to the full glow.
            alpha = int(60 + 90 * p)
            # Pulse on top of the ramp so the glow breathes.
            pulse = 1.0 + 0.18 * math.sin(card.t * 9.0)
            radius = int(radius * pulse)
        elif card.phase == _FLASH:
            # Bright pulse at the reveal moment, then settle.
            p = clamp(card.t / _FLASH_DUR, 0.0, 1.0)
            radius = int(180 + 40 * (1.0 - p))
            alpha = int(200 * (1.0 - p) + 80)
        else:  # _HOLD
            p = clamp(card.t / max(0.01, card.hold_dur), 0.0, 1.0)
            radius = 180
            alpha = int(120 * (1.0 - p))
        if alpha <= 0 or radius <= 0:
            return
        if radius > _FLASH_MAX_R:
            radius = _FLASH_MAX_R
        s = self._get_flash_scratch()
        s.fill((0, 0, 0, 0))
        mid = _SCRATCH_FLASH // 2
        # A few concentric rings for a soft falloff.
        for i in range(4, 0, -1):
            rr = int(radius * i / 4)
            a = int(alpha * (1 - (i / 4)) * 0.6 + alpha * 0.4)
            pygame.draw.circle(s, (*card.color, min(220, a)),
                               (mid, mid), rr)
        surf.blit(s, (cx - mid, cy - mid))

    def _draw_flash(self, surf: pygame.Surface, cx: int, cy: int,
                    card: _Card) -> None:
        """Draw the reveal flash: a bright expanding shockwave ring.

        Fires over the flash window; expands outward and fades.  Drawn
        via the reusable flash scratch (cleared per frame).
        """
        fp = 1.0 - (card.flash_life / card.flash_max)      # 0 -> 1
        radius = int(20 + 180 * ease_out_cubic(fp))
        if radius > _FLASH_MAX_R:
            radius = _FLASH_MAX_R
        alpha = int(230 * (1.0 - fp))
        if alpha <= 0 or radius <= 0:
            return
        s = self._get_flash_scratch()
        s.fill((0, 0, 0, 0))
        mid = _SCRATCH_FLASH // 2
        # Filled disc (faint) + ring (brighter) for the shockwave.
        pygame.draw.circle(s, (*card.color, alpha // 4),
                           (mid, mid), radius)
        pygame.draw.circle(s, (*card.color, alpha),
                           (mid, mid), radius, max(2, radius // 8))
        # A bright white core for the first ~40% of the flash.
        if fp < 0.4:
            core_a = int(220 * (1.0 - fp / 0.4))
            core_r = int(radius * 0.5)
            pygame.draw.circle(s, (255, 255, 255, core_a),
                               (mid, mid), core_r)
        surf.blit(s, (cx - mid, cy - mid))

    def _draw_shards(self, surf: pygame.Surface, card: _Card) -> None:
        """Draw the reveal burst shards.

        Each shard is a translucent colored circle drawn via the reusable
        particle scratch (cleared per shard).  The scratch is SRCALPHA so
        the shard's alpha blends correctly when blitted onto the opaque
        screen.
        """
        if not card.shards:
            return
        s = self._get_particle_scratch()
        mid = _SCRATCH_PARTICLE // 2
        for sh in card.shards:
            life_frac = clamp(sh.life / sh.max_life, 0.0, 1.0)
            a = int(255 * life_frac)
            if a <= 0:
                continue
            r = max(1, int(sh.size * (0.4 + 0.6 * life_frac)))
            if r > mid - 1:
                r = mid - 1
            s.fill((0, 0, 0, 0))
            pygame.draw.circle(s, (*sh.color, a), (mid, mid), r)
            surf.blit(s, (int(sh.x) - mid, int(sh.y) - mid))

    def _draw_grid(self, surf: pygame.Surface) -> None:
        """Draw the final 10-pull grid: a 5x2 layout of all results.

        The grid scales in with an ease-out over ``_GRID_IN_DUR``, then
        holds at full size for ``_GRID_HOLD_DUR``.  Each cell shows the
        pet's face-up card (small) with its sprite + name + "NEW!" tag.
        A dim panel sits behind the grid so it reads against the dark
        backdrop.
        """
        p = clamp(self._t / _GRID_IN_DUR, 0.0, 1.0)
        scale = 0.7 + 0.3 * ease_out_cubic(p)           # 0.7 -> 1.0
        alpha = int(255 * ease_out_cubic(p))

        # Grid geometry (centered).
        gw = _GRID_COLS * _GRID_CARD_W + (_GRID_COLS - 1) * _GRID_GAP
        gh = _GRID_ROWS * _GRID_CARD_H + (_GRID_ROWS - 1) * _GRID_GAP
        ox = (cfg.WINDOW_W - gw) // 2
        oy = (cfg.WINDOW_H - gh) // 2 - 10

        # Backing panel behind the grid (a dark rounded rect).
        pad = 24
        panel_rect = pygame.Rect(ox - pad, oy - pad, gw + pad * 2, gh + pad * 2)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (16, 18, 32, min(220, alpha)),
                         panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, (*C.panel_border_hi, alpha),
                         panel.get_rect(), 2, border_radius=18)
        if alpha < 255:
            panel.set_alpha(alpha)
        surf.blit(panel, panel_rect.topleft)

        # Title above the grid.
        title = font_xl(bold=True).render("Summon Results", True, C.text)
        if alpha < 255:
            title.set_alpha(alpha)
        surf.blit(title, title.get_rect(
            midbottom=(cfg.WINDOW_W // 2, oy - pad + 4)))

        # Each cell: a small face-up card with the pet sprite + name.
        for i, card in enumerate(self._cards):
            if card is None or card.pet is None:
                continue
            r_idx, c_idx = divmod(i, _GRID_COLS)
            x = ox + c_idx * (_GRID_CARD_W + _GRID_GAP)
            y = oy + r_idx * (_GRID_CARD_H + _GRID_GAP)
            self._draw_grid_cell(surf, card, x, y, _GRID_CARD_W, _GRID_CARD_H,
                                 scale, alpha)

    def _draw_grid_cell(self, surf: pygame.Surface, card: _Card,
                        x: int, y: int, w: int, h: int,
                        scale: float, alpha: int) -> None:
        """Draw one cell of the final 10-pull grid."""
        # Card panel.
        rect = pygame.Rect(x, y, w, h)
        border = card.color if alpha > 120 else C.panel_border
        fill = (20, 22, 40) if alpha > 120 else C.panel_lo
        # Draw via a small scratch so the border color + alpha blend.
        cell = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(cell, (*fill, min(255, alpha)),
                         cell.get_rect(), border_radius=8)
        pygame.draw.rect(cell, (*border, alpha),
                         cell.get_rect(), 2, border_radius=8)
        # Pet sprite (cached pet_surface, scaled up from 48px).
        sprite = pet_surface(card.pet.id, card.pet.hue, 96)
        sw = max(1, int(sprite.get_width() * scale * 0.6))
        sh = max(1, int(sprite.get_height() * scale * 0.6))
        sprite_s = pygame.transform.smoothscale(sprite, (sw, sh))
        if alpha < 255:
            sprite_s.set_alpha(alpha)
        cell.blit(sprite_s, sprite_s.get_rect(
            center=(w // 2, h // 2 - 6)))
        # Name.
        name = font_sm(bold=True).render(card.pet.name, True, C.text)
        if alpha < 255:
            name.set_alpha(alpha)
        cell.blit(name, name.get_rect(midbottom=(w // 2, h - 18)))
        # "NEW!" tag.
        if card.new_img is not None:
            tag = card.new_img
            if alpha < 255:
                tag = tag.copy()
                tag.set_alpha(alpha)
            cell.blit(tag, tag.get_rect(midtop=(w // 2, 4)))
        surf.blit(cell, rect.topleft)

    # ------------------------------------------------------------------
    # Card pre-rendering (one allocation, at start)
    # ------------------------------------------------------------------
    def _build_face_down(self) -> pygame.Surface:
        """Pre-render the face-down card back.

        A dark rounded rect with a subtle pattern (a centered "?" + a
        faint border) so it reads as a mystery card.  Cached for the life
        of the sequence and shared across all cards.
        """
        surf = pygame.Surface((_CARD_W, _CARD_H), pygame.SRCALPHA)
        # Card body.
        pygame.draw.rect(surf, (22, 24, 44), surf.get_rect(),
                         border_radius=_CARD_RADIUS)
        pygame.draw.rect(surf, C.panel_border_hi, surf.get_rect(),
                         3, border_radius=_CARD_RADIUS)
        # A subtle inner border for depth.
        inner = pygame.Rect(8, 8, _CARD_W - 16, _CARD_H - 16)
        pygame.draw.rect(surf, (40, 44, 70), inner, 1,
                         border_radius=_CARD_RADIUS - 4)
        # Centered "?" — the mystery.
        q = font_xl(bold=True).render("?", True, (90, 100, 140))
        surf.blit(q, q.get_rect(center=(_CARD_W // 2, _CARD_H // 2)))
        # A faint diamond accent above + below the "?" for ornament.
        cx, cy = _CARD_W // 2, _CARD_H // 2
        for dy in (-80, 80):
            pts = [(cx, cy + dy - 10), (cx + 14, cy + dy),
                   (cx, cy + dy + 10), (cx - 14, cy + dy)]
            pygame.draw.polygon(surf, (60, 70, 110), pts, 2)
        return surf.convert_alpha()

    def _build_face_up(self, pet: pet_def.PetDef, rarity: str,
                       is_new: bool) -> pygame.Surface:
        """Pre-render the face-up card for one pet.

        A dark rounded rect with a rarity-colored border, the pet sprite
        (cached ``pet_surface`` at 120px), the pet name, and a "NEW!"
        tag if applicable.  Built once at start; only ``set_alpha`` /
        ``smoothscale`` per frame.
        """
        surf = pygame.Surface((_CARD_W, _CARD_H), pygame.SRCALPHA)
        # Card body.
        col = C.rarity.get(rarity, C.rarity["common"])
        pygame.draw.rect(surf, (20, 22, 40), surf.get_rect(),
                         border_radius=_CARD_RADIUS)
        pygame.draw.rect(surf, col, surf.get_rect(), 3,
                         border_radius=_CARD_RADIUS)
        # A subtle inner border for depth (faint, in the rarity color).
        inner = pygame.Rect(8, 8, _CARD_W - 16, _CARD_H - 16)
        faint = lerp_color(col, (20, 22, 40), 0.6)
        pygame.draw.rect(surf, faint, inner, 1,
                         border_radius=_CARD_RADIUS - 4)
        # Pet sprite (cached, 120px).
        sprite = pet_surface(pet.id, pet.hue, 120)
        surf.blit(sprite, sprite.get_rect(
            center=(_CARD_W // 2, _CARD_H // 2 - 30)))
        # Pet name.
        name = font_lg(bold=True).render(pet.name, True, C.text)
        surf.blit(name, name.get_rect(
            center=(_CARD_W // 2, _CARD_H - 70)))
        # "NEW!" tag.
        if is_new:
            new = font_md(bold=True).render("NEW!", True, C.text_good)
            surf.blit(new, new.get_rect(
                center=(_CARD_W // 2, _CARD_H - 40)))
        # Rarity label at the top.
        rar_label = font_xs(bold=True).render(rarity.upper(), True, col)
        surf.blit(rar_label, rar_label.get_rect(
            midtop=(_CARD_W // 2, 10)))
        return surf.convert_alpha()

    def _build_shards(self, color: tuple[int, int, int], multi: bool,
                      rarity: str) -> list[_Shard]:
        """Build the reveal burst shards for one card.

        Count scales with rarity (more shards for rarer pets) and is
        smaller for multi-pulls (so the sequence doesn't get noisy
        across 10 cards).  Built once at start; mutated each tick.
        """
        if multi:
            count = _BURST_COUNT_MULTIPULL
        elif rarity == "mythic":
            count = _BURST_COUNT_MYTHIC
        else:
            count = _BURST_COUNT_SINGLE
        cx = float(cfg.WINDOW_W // 2)
        cy = float(cfg.WINDOW_H // 2)
        shards: list[_Shard] = []
        # Two color variants: the card color + a brighter tint for spark.
        bright = lerp_color(color, (255, 255, 255), 0.4)
        for i in range(count):
            ang = rng().uniform(0.0, math.tau)
            sp = rng().uniform(140.0, 280.0)
            life = rng().uniform(0.35, 0.6)
            size = rng().uniform(2.5, 5.0)
            col = color if (i % 3) else bright
            shards.append(_Shard(
                cx, cy,
                math.cos(ang) * sp, math.sin(ang) * sp - 40.0,
                life, size, col,
            ))
        return shards

    # ------------------------------------------------------------------
    # Internals -- lazy reusable surfaces + blit helpers
    # ------------------------------------------------------------------
    def _get_dim(self) -> pygame.Surface:
        """Reusable full-screen dim veil (plain Surface, set_alpha'd per frame).

        Plain (non-SRCALPHA) so ``set_alpha`` gives a uniform global fade
        when blitted over the opaque screen.  Created once; reused every
        frame.
        """
        if self._dim is None:
            self._dim = pygame.Surface(
                (cfg.WINDOW_W, cfg.WINDOW_H)).convert()
            self._dim.fill((4, 6, 18))
        return self._dim

    def _get_flash_scratch(self) -> pygame.Surface:
        """Reusable SRCALPHA scratch for the flash / glow ring.

        Cleared per frame; never reallocated in the loop.
        """
        if self._flash_scratch is None:
            self._flash_scratch = pygame.Surface(
                (_SCRATCH_FLASH, _SCRATCH_FLASH),
                pygame.SRCALPHA).convert_alpha()
        return self._flash_scratch

    def _get_particle_scratch(self) -> pygame.Surface:
        """Reusable SRCALPHA scratch for one particle glow.

        Cleared per shard; never reallocated in the loop.
        """
        if self._particle_scratch is None:
            self._particle_scratch = pygame.Surface(
                (_SCRATCH_PARTICLE, _SCRATCH_PARTICLE),
                pygame.SRCALPHA).convert_alpha()
        return self._particle_scratch

    def _blit_card_scaled(self, surf: pygame.Surface, card: pygame.Surface,
                          cx: int, cy: int, scale: float,
                          alpha: int) -> None:
        """Blit a card surface scaled by ``scale`` with ``alpha``.

        ``smoothscale`` returns a new Surface (the cached card is never
        mutated); ``set_alpha`` is applied to the scaled copy.  The
        scale is clamped so we never smoothscale to 0.
        """
        if card is None or alpha <= 0:
            return
        scale = max(0.05, scale)
        sw = max(1, int(_CARD_W * scale))
        sh = max(1, int(_CARD_H * scale))
        img = pygame.transform.smoothscale(card, (sw, sh))
        if alpha < 255:
            img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(cx, cy)))
