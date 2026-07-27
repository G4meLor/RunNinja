"""Screen transition system: a brief fade between screens.

Switching screens is no longer instant/jarring.  When ``set_screen`` is
called the *old* screen fades out (~0.2s), then the *new* screen fades in
(~0.2s).  ``reduced_motion`` skips the animation entirely (instant swap).

Design notes
------------
* Pure pygame primitives — a single full-window rect filled with the bg
  color and modulated alpha, blitted over the current screen each frame.
* No per-frame allocations: the overlay Surface is created once (lazily)
  and reused; only ``set_alpha`` is called per frame.
* The transition drives the *draw* side.  The caller still draws the
  current screen (via ``draw(surf, current_screen_draw_callable)``) and
  this module overlays the fade on top.  The screen *swap* itself happens
  at the midpoint of the transition (phase "swap"), so the caller keeps a
  reference to the old screen name until ``done`` is True.

Phase machine
------------
``IDLE`` -> ``FADE_OUT`` (~0.2s) -> ``SWAP`` (one frame) -> ``FADE_IN``
(~0.2s) -> ``DONE``.  ``active`` is True during FADE_OUT/FADE_IN; ``done``
becomes True once FADE_IN completes.
"""
from __future__ import annotations

import pygame

import config as cfg

# Phase constants (kept as small ints for cheap comparisons).
_IDLE = 0
_FADE_OUT = 1
_SWAP = 2
_FADE_IN = 3
_DONE = 4

# Durations (seconds).
DURATION_OUT = 0.20
DURATION_IN = 0.20


class ScreenTransition:
    """Drives a fade-out -> swap -> fade-in between two screens.

    Lifecycle
    ---------
    1. ``start(old, new)``        — arm the transition.
    2. each frame: ``update(dt)`` — advance the timer.
    3. each frame: ``draw(surf, current_draw)`` — draw the current screen
       (the caller decides *which* screen is "current" based on phase)
       then overlay the fade.
    4. when ``done`` is True, the transition is finished and the new
       screen is fully visible.

    The caller is responsible for swapping which screen it draws at the
    midpoint.  A helper is provided: ``pending_swap`` is True for exactly
    one ``update`` call (the frame the swap should happen), so the caller
    can flip its ``current_screen`` pointer then.
    """

    def __init__(self, game) -> None:
        self.game = game
        self._phase = _IDLE
        self._t = 0.0          # elapsed time in the current phase
        self.old_screen: str | None = None
        self.new_screen: str | None = None
        # Reusable overlay surface — created lazily on first draw so we
        # don't allocate before ``pygame.display.set_mode``.
        self._overlay: pygame.Surface | None = None
        # One-shot flag: True for the single frame the caller should swap
        # the active screen pointer on.
        self._swap_flag = False
        # Cached window size so we can rebuild the overlay if the window
        # is ever resized (defensive — Tap Ninja is fixed-size).
        self._overlay_size: tuple[int, int] = (0, 0)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        """True while a transition is in progress (fade-out or fade-in)."""
        return self._phase in (_FADE_OUT, _FADE_IN, _SWAP)

    @property
    def done(self) -> bool:
        """True once the transition has fully completed."""
        return self._phase == _DONE

    @property
    def pending_swap(self) -> bool:
        """True for exactly one frame: the moment the caller should swap
        the active screen from ``old_screen`` to ``new_screen``.

        Read this *after* ``update(dt)`` and before ``draw``.
        """
        return self._swap_flag

    @property
    def phase(self) -> str:
        """Human-readable phase name (for debugging/specs)."""
        return {0: "idle", 1: "fade_out", 2: "swap",
                3: "fade_in", 4: "done"}[self._phase]

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def start(self, old_screen_name: str, new_screen_name: str) -> None:
        """Begin a transition from ``old_screen_name`` to ``new_screen_name``.

        If ``reduced_motion`` is on, the transition is effectively
        skipped: phase jumps straight to ``DONE`` so the caller's swap
        happens immediately without any fade frames.
        """
        # No-op if the screen isn't actually changing.
        if old_screen_name == new_screen_name:
            self._phase = _DONE
            self.old_screen = old_screen_name
            self.new_screen = new_screen_name
            self._t = 0.0
            self._swap_flag = True
            return

        self.old_screen = old_screen_name
        self.new_screen = new_screen_name
        self._t = 0.0
        self._swap_flag = False

        if self.game.state.reduced_motion:
            # Instant: signal the swap and finish immediately.
            self._phase = _DONE
            self._swap_flag = True
        else:
            self._phase = _FADE_OUT

    def reset(self) -> None:
        """Return to idle (used after the caller consumes the transition)."""
        self._phase = _IDLE
        self._t = 0.0
        self._swap_flag = False
        self.old_screen = None
        self.new_screen = None

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance the transition by ``dt`` seconds.

        Call once per frame.  After this returns, check
        ``pending_swap`` (to flip the active screen) and then call
        ``draw``.
        """
        self._swap_flag = False
        if self._phase == _IDLE or self._phase == _DONE:
            return

        self._t += dt

        if self._phase == _FADE_OUT:
            if self._t >= DURATION_OUT:
                # Roll over into the swap phase: emit the one-frame flag.
                self._phase = _SWAP
                self._t = 0.0
                self._swap_flag = True
        elif self._phase == _SWAP:
            # Swap lasts exactly one frame; move to fade-in immediately.
            self._phase = _FADE_IN
            self._t = 0.0
        elif self._phase == _FADE_IN:
            if self._t >= DURATION_IN:
                self._phase = _DONE
                self._t = 0.0

    def draw(self, surf: pygame.Surface,
             current_screen_draw: callable) -> None:
        """Draw the current screen, then overlay the fade.

        ``current_screen_draw`` is a zero-arg callable that draws the
        screen the caller considers "current" (i.e. the old screen
        during fade-out, the new screen during/after the swap).  This
        module then overlays a full-window rect whose alpha follows the
        fade curve, so the screen appears to dim out and back in.

        Outside an active transition this just calls the drawable and
        returns — zero overhead.
        """
        # Always draw the current screen first.
        current_screen_draw()

        if self._phase == _IDLE or self._phase == _DONE:
            return

        # Fade alpha curve: 0 (visible) -> 255 (covered) -> 0 (visible).
        if self._phase == _FADE_OUT:
            # 0 at start of fade-out, 255 at end.
            p = self._t / DURATION_OUT
        elif self._phase == _SWAP:
            p = 1.0
        else:  # _FADE_IN
            # 255 at start of fade-in, 0 at end.
            p = 1.0 - (self._t / DURATION_IN)
        # Clamp + ease (smoothstep) so the fade feels natural rather than
        # linear.
        p = 0.0 if p < 0.0 else 1.0 if p > 1.0 else p
        p = p * p * (3 - 2 * p)
        alpha = int(255 * p)
        if alpha <= 0:
            return

        overlay = self._get_overlay()
        overlay.set_alpha(alpha)
        surf.blit(overlay, (0, 0))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _get_overlay(self) -> pygame.Surface:
        """Return the reusable full-window overlay, rebuilding it if the
        window size changed.  Allocated once; reused every frame.
        """
        size = (cfg.WINDOW_W, cfg.WINDOW_H)
        if self._overlay is None or self._overlay_size != size:
            self._overlay = pygame.Surface(size).convert()
            self._overlay.fill((0, 0, 0))
            self._overlay_size = size
        return self._overlay
