"""Procedural asset generation for Tap Ninja.

ninja, enemies, fireflies, buildings, backgrounds — all pygame
primitives, no external image files.
"""
from __future__ import annotations

import math
import colorsys
from typing import Tuple

import numpy as np
import pygame

import config as cfg
from utils import rng


def hsl(h: int, s: float, l: float) -> Tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


# === Outline + shading ramp (Task 32 / gfx-outline-shading-squash) ===
# Two cheap, high-impact graphics upgrades applied at CACHE TIME (zero
# per-frame cost):
#
# 1. ``outline_array(surf)`` — a vectorized 1px alpha-dilation outline.
#    The "looks like real pixel art" trick: a dark 1px ring around each
#    sprite so it reads against any background. The outline is the
#    dilation of the alpha channel by 1px (the 4-neighbors), minus the
#    original mask (the ring around the sprite). The original sprite is
#    blitted on top of the outline so the sprite covers the inner part
#    and the outline shows as a 1px ring.
#
# 2. ``apply_shading_ramp(surf, steps=5)`` — a 4-6 step hue-shifted
#    shading ramp. Shadows shift hue cool (toward blue), highlights warm
#    (toward red/orange). The ramp is computed from the sprite's
#    luminance range (quantized to N levels); each level gets a hue
#    shift in RGB space (cool = more blue/less red, warm = more
#    red/less blue). Applied in-place to the surface's RGB (the alpha is
#    unchanged).
#
# Both are applied at cache-miss time (before ``convert_alpha``), so the
# per-frame blit cost is identical to the unprocessed sprite (the outline
# + shading are baked into the cached surface). The squash-and-stretch
# (Task 32, part 3) is applied per-frame in ``ui.screen_game`` (gated by
# ``reduced_motion``); the outline + shading are NOT gated by
# ``reduced_motion`` (they are static cache-time enhancements, not motion).


def outline_array(surf: pygame.Surface) -> pygame.Surface:
    """Build a 1px alpha-dilation outline around the sprite.

    The "looks like real pixel art" trick: a dark 1px ring around the
    sprite so it reads against any background. The outline is the
    dilation of the alpha channel by 1px (the 4-neighbors), minus the
    original mask (the ring around the sprite). The original sprite is
    blitted on top of the outline so the sprite covers the inner part
    and the outline shows as a 1px ring.

    Vectorized with numpy (the alpha channel is read into an array, the
    dilation is a shift-and-OR, the outline mask is written back to a
    fresh surface). Returns a new SRCALPHA surface (the original is
    unchanged); the caller caches the result.

    The outline is applied at CACHE TIME (zero per-frame cost) — the
    cached sprite has the outline baked in.
    """
    w, h = surf.get_size()
    # Read the alpha channel as a numpy array (W, H).
    alpha = pygame.surfarray.array_alpha(surf).astype(np.uint8)
    mask = (alpha > 0).astype(np.uint8)
    # Dilate by 1px (4-neighbors): a pixel is "on" if any of its 4
    # neighbors (or itself) is on. This is a shift-and-OR in each
    # direction.
    dilated = mask.copy()
    dilated[1:] |= mask[:-1]    # shift right
    dilated[:-1] |= mask[1:]    # shift left
    dilated[:, 1:] |= mask[:, :-1]  # shift down
    dilated[:, :-1] |= mask[:, 1:]  # shift up
    # Outline = dilated - original (the ring around the sprite).
    outline_mask = dilated & ~mask
    # Build the outline surface: dark color at the outline pixels,
    # transparent elsewhere.
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    if outline_mask.any():
        rgb = pygame.surfarray.pixels3d(out)
        a = pygame.surfarray.pixels_alpha(out)
        rgb[outline_mask.astype(bool)] = (20, 20, 30)
        a[outline_mask.astype(bool)] = 255
        del rgb, a  # release the locked surface
    # Blit the original sprite on top (the sprite covers the inner
    # part; the outline shows as a 1px ring around the sprite).
    out.blit(surf, (0, 0))
    return out


def apply_shading_ramp(surf: pygame.Surface, steps: int = 5) -> pygame.Surface:
    """Apply a 4-6 step hue-shifted shading ramp to the sprite.

    Shadows shift hue cool (toward blue), highlights warm (toward
    red/orange). The ramp is computed from the sprite's luminance range
    (quantized to N levels); each level gets a hue shift in RGB space
    (cool = more blue/less red, warm = more red/less blue). Applied
    in-place to the surface's RGB (the alpha is unchanged).

    The ramp is applied at CACHE TIME (zero per-frame cost) — the cached
    sprite has the ramp baked in.

    ``steps`` is the number of ramp levels (4-6 per the brief; default 5).
    """
    w, h = surf.get_size()
    # Read the RGB + alpha as numpy arrays (copies, not views).
    rgb = pygame.surfarray.array3d(surf).astype(np.float32)
    alpha = pygame.surfarray.array_alpha(surf).astype(np.float32)
    mask = alpha > 0
    if not mask.any():
        return surf  # nothing to shade
    # Compute per-pixel luminance (Rec. 601).
    lum = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    opaque_lum = lum[mask]
    lo, hi = float(opaque_lum.min()), float(opaque_lum.max())
    if hi <= lo:
        return surf  # flat luminance; no ramp
    # Quantize to N levels (0..steps-1) based on the luminance range.
    t = (lum - lo) / (hi - lo)  # 0..1
    level = (t * (steps - 1)).astype(np.int32).clip(0, steps - 1)
    # Hue shift per level: level 0 (darkest) -> cool (toward blue),
    # level steps-1 (brightest) -> warm (toward red/orange). The shift
    # is (level - mid) * 15, so for 5 steps: -30, -15, 0, +15, +30.
    mid = (steps - 1) / 2.0
    shift = (level - mid) * 15.0
    # Apply: red += shift (warm = more red), blue -= shift (cool = more
    # blue). Green is slightly reduced at the extremes for a more
    # natural ramp (so the warm end is red/orange, not yellow; the cool
    # end is blue, not cyan).
    rgb_out = rgb.copy()
    rgb_out[:, :, 0] = np.where(
        mask, (rgb[:, :, 0] + shift).clip(0, 255), rgb[:, :, 0])
    rgb_out[:, :, 2] = np.where(
        mask, (rgb[:, :, 2] - shift).clip(0, 255), rgb[:, :, 2])
    rgb_out[:, :, 1] = np.where(
        mask, (rgb[:, :, 1] - np.abs(shift) * 0.3).clip(0, 255), rgb[:, :, 1])
    # Write back to the surface's RGB only (preserve the alpha channel).
    # ``pixels3d`` returns a view that locks the surface for in-place
    # RGB writes — unlike ``blit_array``, it does NOT touch the alpha
    # channel, so the sprite's transparency is preserved.
    rgb_view = pygame.surfarray.pixels3d(surf)
    rgb_view[:] = rgb_out.astype(np.uint8)
    del rgb_view  # release the locked surface
    return surf


# === Ninja ===
# Task 30 (gfx-sprite-sheet-anim): the ninja is the most-seen sprite and
# the slash_anim/bob timers already exist but are wasted (the screen only
# used a 1px vertical bob). We pre-roll a sprite sheet at cache time:
# 8 frames stacked horizontally into one wide SRCALPHA sheet, blit by
# sub-rect (``subsurface`` is a zero-copy view — no per-frame allocation).
# Frame selection is from ``slash_anim`` (windup/extend/recover) and
# ``bob`` (idle). Frame 0 is the static fallback (graceful degradation).
#
# Frame layout (8 frames, each size x size):
#   0: idle neutral (the static fallback)
#   1: idle bob up   (sin(bob*4) > 0)
#   2: idle bob down (sin(bob*4) < 0)
#   3: slash windup  (0.10 < slash_anim <= 0.15, the crouch before the lunge)
#   4: slash extend  (0.05 < slash_anim <= 0.10, the lunge forward)
#   5: slash recover (0.0  < slash_anim <= 0.05, the return to neutral)
#   6: hit flinch    (last_damage_timer > 0, the recoil when hit)
#   7: dead          (the dimmed corpse frame; the screen tints this further)
_NINJA_CACHE: dict[int, pygame.Surface] = {}
_NINJA_SHEET_CACHE: dict[int, pygame.Surface] = {}
# The 8 frame indices (named for readability; the selector uses the
# integer indices so a typo in a name never breaks the sheet).
_NINJA_FRAME_IDLE = 0
_NINJA_FRAME_IDLE_UP = 1
_NINJA_FRAME_IDLE_DOWN = 2
_NINJA_FRAME_SLASH_WINDUP = 3
_NINJA_FRAME_SLASH_EXTEND = 4
_NINJA_FRAME_SLASH_RECOVER = 5
_NINJA_FRAME_HIT_FLINCH = 6
_NINJA_FRAME_DEAD = 7
_NINJA_FRAME_COUNT = 8


def _draw_ninja_frame(surf: pygame.Surface, size: int, frame: int) -> None:
    """Draw one ninja frame onto ``surf`` (a size x size SRCALPHA surface).

    The frames are deliberately cheap variations on the static ninja:
    the body + headband + eyes + sword are drawn for every frame, then a
    per-frame offset / arm position / tint is applied so the frames read
    as a small animation (idle bob, slash lunge, hit flinch) without
    redrawing the whole sprite from scratch. Frame 0 is the neutral
    static pose (the graceful-degradation fallback).
    """
    cx, cy = size // 2, size // 2
    body = (40, 40, 60)
    headband = (220, 60, 60)
    skin = (220, 180, 150)
    # Per-frame vertical offset (the idle bob + the slash lunge + the
    # hit flinch all manifest as a small y shift so the frames read as
    # motion without redrawing the limbs).
    dy = 0
    if frame == _NINJA_FRAME_IDLE_UP:
        dy = -2  # bob up
    elif frame == _NINJA_FRAME_IDLE_DOWN:
        dy = 2   # bob down
    elif frame == _NINJA_FRAME_SLASH_WINDUP:
        dy = 1   # crouch (compress before the lunge)
    elif frame == _NINJA_FRAME_SLASH_EXTEND:
        dy = -3  # lunge forward + up
    elif frame == _NINJA_FRAME_SLASH_RECOVER:
        dy = 1   # settling back
    elif frame == _NINJA_FRAME_HIT_FLINCH:
        dy = 2   # recoil back
    elif frame == _NINJA_FRAME_DEAD:
        dy = 4   # slumped
    # Draw the body + head + headband + eyes + sword at the per-frame
    # offset. The sword arm shifts forward on the extend frame so the
    # slash reads as a lunge.
    pygame.draw.rect(surf, body, (cx - 14, cy - 6 + dy, 28, 26), border_radius=6)
    pygame.draw.circle(surf, skin, (cx, cy - 14 + dy), 10)
    pygame.draw.rect(surf, headband, (cx - 12, cy - 20 + dy, 24, 5))
    pygame.draw.rect(surf, headband, (cx + 8, cy - 22 + dy, 14, 3))
    pygame.draw.line(surf, (20, 20, 30), (cx - 5, cy - 14 + dy), (cx - 2, cy - 14 + dy), 2)
    pygame.draw.line(surf, (20, 20, 30), (cx + 2, cy - 14 + dy), (cx + 5, cy - 14 + dy), 2)
    # The sword arm: on the extend frame, the arm reaches forward (a
    # longer, more horizontal stroke) so the slash reads as a lunge.
    if frame == _NINJA_FRAME_SLASH_EXTEND:
        pygame.draw.line(surf, (220, 220, 230),
                         (cx - 18, cy - 2 + dy), (cx + 6, cy + 14 + dy), 3)
    else:
        pygame.draw.line(surf, (220, 220, 230),
                         (cx - 18, cy - 2 + dy), (cx - 6, cy + 18 + dy), 3)
    pygame.draw.rect(surf, headband, (cx - 22, cy + 16 + dy, 8, 3))
    # The dead frame is dimmed (the screen tints it further with
    # BLEND_RGBA_MULT on the dead-path; this is the base dim).
    if frame == _NINJA_FRAME_DEAD:
        dim = pygame.Surface((size, size), pygame.SRCALPHA)
        dim.fill((80, 80, 100, 255))
        surf.blit(dim, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)


def ninja_surface(size: int = 64) -> pygame.Surface:
    """The cached static ninja sprite (frame 0 of the sprite sheet).

    Kept for backward compatibility — the bestiary / hero / menu screens
    and the skill-FX afterimage all read this single-sprite API. The
    sprite is frame 0 of the sprite sheet (the static fallback), so the
    two never diverge.

    Task 32 (gfx-outline-shading-squash): the outline + shading ramp are
    applied at cache time (before ``convert_alpha``), so the cached
    sprite has the outline + shading baked in (zero per-frame cost).
    """
    cached = _NINJA_CACHE.get(size)
    if cached is not None:
        return cached
    # Frame 0 is the static sprite; build it once and cache it.
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    _draw_ninja_frame(surf, size, _NINJA_FRAME_IDLE)
    # Task 32: apply the outline + shading ramp at cache time (before
    # convert_alpha) so the cached sprite has them baked in.
    apply_shading_ramp(surf)
    surf = outline_array(surf)
    surf = surf.convert_alpha()
    _NINJA_CACHE[size] = surf
    return surf


def ninja_sprite_sheet(size: int = 64) -> pygame.Surface:
    """The cached ninja sprite sheet (8 frames stacked horizontally).

    Returns a wide SRCALPHA surface (size * 8 x size) with
    ``convert_alpha``. The 8 frames are:
      0: idle neutral (the static fallback)
      1: idle bob up
      2: idle bob down
      3: slash windup
      4: slash extend
      5: slash recover
      6: hit flinch
      7: dead

    Cached per size; the sheet is built once at cache-miss time and the
    per-frame selection (``ninja_frame``) is a zero-copy ``subsurface``
    view, so the per-frame blit cost is identical to the static sprite
    (same pixel count, same format, no allocation).

    Task 32 (gfx-outline-shading-squash): the outline + shading ramp are
    applied per frame at cache time. Each frame is drawn on its own
    surface, the outline + shading are applied, and the frame is blitted
    onto the sheet — this keeps the outline within each frame's bounds
    (the outline does not bleed across frame boundaries, which it would
    if the outline were applied to the whole sheet at once).
    """
    cached = _NINJA_SHEET_CACHE.get(size)
    if cached is not None:
        return cached
    sheet = pygame.Surface((size * _NINJA_FRAME_COUNT, size), pygame.SRCALPHA)
    for i in range(_NINJA_FRAME_COUNT):
        # Task 32: draw each frame on its own surface, apply the outline
        # + shading ramp, then blit onto the sheet. This keeps the
        # outline within each frame's bounds (the outline is a 1px ring
        # around the sprite; if applied to the whole sheet, the ring
        # would bleed across frame boundaries).
        frame = pygame.Surface((size, size), pygame.SRCALPHA)
        _draw_ninja_frame(frame, size, i)
        apply_shading_ramp(frame)
        frame = outline_array(frame)
        sheet.blit(frame, (i * size, 0))
    sheet = sheet.convert_alpha()
    _NINJA_SHEET_CACHE[size] = sheet
    return sheet


def ninja_frame(size: int = 64, slash_anim: float = 0.0,
                bob: float = 0.0, last_damage_timer: float = 0.0,
                reduced_motion: bool = False) -> pygame.Surface:
    """Select the ninja frame sub-rect from the cached sprite sheet.

    Returns a ``subsurface`` (zero-copy view) of the sheet — no
    per-frame allocation, same pixel count + format as the static
    sprite, so the per-frame blit cost is identical.

    Frame selection:
      * ``reduced_motion`` pins to frame 0 (the static fallback).
      * ``last_damage_timer > 0`` selects the hit-flinch frame (the
        ninja recoils when hit; this takes priority over slash so a hit
        mid-slash reads as a flinch, not a slash).
      * ``slash_anim > 0.10`` selects the windup frame (the crouch
        before the lunge).
      * ``0.05 < slash_anim <= 0.10`` selects the extend frame (the
        lunge forward).
      * ``0.0 < slash_anim <= 0.05`` selects the recover frame (the
        return to neutral).
      * ``slash_anim == 0`` (idle): the bob timer selects the idle
        frame. ``sin(bob * 4) > 0`` -> idle up; ``sin(bob * 4) < 0`` ->
        idle down; else neutral (frame 0).

    Frame 0 is the graceful-degradation fallback (any unknown state
    lands on frame 0).
    """
    sheet = ninja_sprite_sheet(size)
    if reduced_motion:
        idx = _NINJA_FRAME_IDLE
    elif last_damage_timer > 0:
        idx = _NINJA_FRAME_HIT_FLINCH
    elif slash_anim > 0.10:
        idx = _NINJA_FRAME_SLASH_WINDUP
    elif slash_anim > 0.05:
        idx = _NINJA_FRAME_SLASH_EXTEND
    elif slash_anim > 0.0:
        idx = _NINJA_FRAME_SLASH_RECOVER
    else:
        # Idle: the bob timer selects the idle frame. sin(bob * 4) is
        # the same function the screen used for the 1px vertical bob, so
        # the frame selection lines up with the old bob phase.
        phase = math.sin(bob * 4)
        if phase > 0:
            idx = _NINJA_FRAME_IDLE_UP
        elif phase < 0:
            idx = _NINJA_FRAME_IDLE_DOWN
        else:
            idx = _NINJA_FRAME_IDLE
    return sheet.subsurface((idx * size, 0, size, size))


# === Enemy ===
# Task 30 (gfx-sprite-sheet-anim): the bandit shape gets a multi-frame
# idle cycle (3 frames) so at least one enemy shape has a visible idle
# animation. Other shapes keep the single static sprite (graceful
# degradation — ``enemy_frame`` returns frame 0 of a 1-frame sheet,
# which is the static sprite, so the per-frame blit cost is identical).
_ENEMY_CACHE: dict[tuple, pygame.Surface] = {}
_ENEMY_SHEET_CACHE: dict[tuple, pygame.Surface] = {}
# The bandit idle cycle: 3 frames (neutral, lean forward, lean back).
# The bandit bobs slightly as it walks; the cycle reads as a shuffling
# gait. Frame 0 is the neutral (the static fallback).
_BANDIT_FRAME_COUNT = 3


def _draw_enemy_frame(surf: pygame.Surface, edef, size: int, frame: int,
                      frame_count: int) -> None:
    """Draw one enemy frame onto ``surf`` (a size x size SRCALPHA surface).

    For the bandit shape with ``frame_count > 1``, the frame is a small
    horizontal lean (a walking gait). Other shapes draw the static
    sprite (frame 0 only).
    """
    base = hsl(edef.hue, 0.6, 0.5)
    dark = hsl(edef.hue, 0.5, 0.30)
    light = hsl(edef.hue, 0.5, 0.7)
    cx, cy = size // 2, size // 2
    r = size // 3
    shape = edef.shape
    # Per-frame horizontal offset for the bandit's walking gait.
    dx = 0
    if shape == "bandit" and frame_count > 1:
        if frame == 1:
            dx = -1  # lean forward (left)
        elif frame == 2:
            dx = 1   # lean back (right)
    if shape == "bandit":
        pygame.draw.rect(surf, base, (cx - r + dx, cy - 4, r * 2, r + 4), border_radius=4)
        pygame.draw.circle(surf, dark, (cx + dx, cy - 8), r - 2)
        pygame.draw.rect(surf, (180, 40, 40), (cx - r + 2 + dx, cy - 12, r * 2 - 4, 3))
        pygame.draw.circle(surf, (255, 80, 80), (cx - 4 + dx, cy - 6), 2)
        pygame.draw.circle(surf, (255, 80, 80), (cx + 4 + dx, cy - 6), 2)
    elif shape in ("oni", "demon"):
        pygame.draw.rect(surf, base, (cx - r, cy - 4, r * 2, r + 4), border_radius=4)
        pygame.draw.polygon(surf, dark, [(cx - 8, cy - 4), (cx - 12, cy - 16), (cx - 4, cy - 8)])
        pygame.draw.polygon(surf, dark, [(cx + 8, cy - 4), (cx + 12, cy - 16), (cx + 4, cy - 8)])
        pygame.draw.circle(surf, (255, 240, 60), (cx - 4, cy - 2), 2)
        pygame.draw.circle(surf, (255, 240, 60), (cx + 4, cy - 2), 2)
    elif shape in ("yokai", "wraith"):
        ghost = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.ellipse(ghost, (*base, 180), (cx - r, cy - r, r * 2, r * 2))
        surf.blit(ghost, (0, 0))
        pygame.draw.circle(surf, (255, 255, 255), (cx - 4, cy - 4), 2)
        pygame.draw.circle(surf, (255, 255, 255), (cx + 4, cy - 4), 2)
    elif shape == "skeleton":
        pygame.draw.circle(surf, hsl(0, 0, 0.85), (cx, cy - 6), r - 2)
        pygame.draw.rect(surf, hsl(0, 0, 0.8), (cx - r + 4, cy + 2, r * 2 - 8, r))
        pygame.draw.circle(surf, (20, 0, 0), (cx - 4, cy - 6), 3)
        pygame.draw.circle(surf, (20, 0, 0), (cx + 4, cy - 6), 3)
    elif shape == "beast":
        pygame.draw.ellipse(surf, base, (cx - r, cy - r // 2, r * 2, r))
        pygame.draw.circle(surf, dark, (cx - r + 4, cy - 2), 6)
        pygame.draw.circle(surf, (255, 80, 80), (cx - r + 4, cy - 2), 2)
    elif shape == "golem":
        pygame.draw.rect(surf, base, (cx - r, cy - r + 2, r * 2, r * 2 - 2), border_radius=3)
        pygame.draw.rect(surf, dark, (cx - r, cy - r + 2, r * 2, 6))
        pygame.draw.rect(surf, light, (cx - 4, cy - 4, 8, 8))
    elif shape == "dragon":
        pygame.draw.ellipse(surf, base, (cx - r, cy - r // 2, r * 2, r + 4))
        pygame.draw.polygon(surf, dark, [(cx - r, cy), (cx - r - 8, cy - 8), (cx - r + 6, cy + 6)])
        pygame.draw.polygon(surf, light, [(cx, cy - 6), (cx + r, cy - 14), (cx + r, cy)])
        pygame.draw.circle(surf, (255, 200, 60), (cx - r + 4, cy), 2)
    else:
        pygame.draw.circle(surf, base, (cx, cy), r)


def _enemy_frame_count(edef) -> int:
    """The number of frames in this enemy's sprite sheet.

    The bandit shape gets a 3-frame idle cycle; other shapes get 1
    frame (the static sprite — graceful degradation).
    """
    if getattr(edef, "shape", "") == "bandit":
        return _BANDIT_FRAME_COUNT
    return 1


def enemy_surface(edef, size: int = 48) -> pygame.Surface:
    """The cached static enemy sprite (frame 0 of the sprite sheet).

    Kept for backward compatibility — the bestiary / death-FX / silhouette
    screens all read this single-sprite API. The sprite is frame 0 of
    the sprite sheet (the static fallback), so the two never diverge.

    Task 32 (gfx-outline-shading-squash): the outline + shading ramp are
    applied at cache time (before ``convert_alpha``), so the cached
    sprite has the outline + shading baked in (zero per-frame cost).
    """
    key = (getattr(edef, "id", str(edef)), size)
    cached = _ENEMY_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    _draw_enemy_frame(surf, edef, size, 0, _enemy_frame_count(edef))
    # Task 32: apply the outline + shading ramp at cache time.
    apply_shading_ramp(surf)
    surf = outline_array(surf)
    surf = surf.convert_alpha()
    _ENEMY_CACHE[key] = surf
    return surf


def enemy_sprite_sheet(edef, size: int = 48) -> pygame.Surface:
    """The cached enemy sprite sheet (frames stacked horizontally).

    Returns a wide SRCALPHA surface (size * frame_count x size) with
    ``convert_alpha``. The bandit shape gets a 3-frame idle cycle; other
    shapes get a 1-frame sheet (the static sprite). Cached per
    (edef id, size); the sheet is built once at cache-miss time and the
    per-frame selection (``enemy_frame``) is a zero-copy ``subsurface``
    view, so the per-frame blit cost is identical to the static sprite.

    Task 32 (gfx-outline-shading-squash): the outline + shading ramp are
    applied per frame at cache time (each frame is drawn on its own
    surface, the outline + shading are applied, and the frame is blitted
    onto the sheet — this keeps the outline within each frame's bounds).
    """
    key = (getattr(edef, "id", str(edef)), size)
    cached = _ENEMY_SHEET_CACHE.get(key)
    if cached is not None:
        return cached
    frame_count = _enemy_frame_count(edef)
    sheet = pygame.Surface((size * frame_count, size), pygame.SRCALPHA)
    for i in range(frame_count):
        # Task 32: draw each frame on its own surface, apply the outline
        # + shading ramp, then blit onto the sheet (keeps the outline
        # within each frame's bounds).
        frame = pygame.Surface((size, size), pygame.SRCALPHA)
        _draw_enemy_frame(frame, edef, size, i, frame_count)
        apply_shading_ramp(frame)
        frame = outline_array(frame)
        sheet.blit(frame, (i * size, 0))
    sheet = sheet.convert_alpha()
    _ENEMY_SHEET_CACHE[key] = sheet
    return sheet


def enemy_frame(edef, size: int = 48, bob: float = 0.0,
                reduced_motion: bool = False) -> pygame.Surface:
    """Select the enemy frame sub-rect from the cached sprite sheet.

    Returns a ``subsurface`` (zero-copy view) of the sheet — no
    per-frame allocation, same pixel count + format as the static
    sprite, so the per-frame blit cost is identical.

    Frame selection:
      * ``reduced_motion`` pins to frame 0 (the static fallback).
      * The bandit shape has a 3-frame idle cycle: the bob timer selects
        the frame (sin(bob * 4) > 0 -> lean forward, < 0 -> lean back,
        == 0 -> neutral). Other shapes have a 1-frame sheet (frame 0,
        the static sprite — graceful degradation).

    Frame 0 is the graceful-degradation fallback.
    """
    sheet = enemy_sprite_sheet(edef, size)
    frame_count = _enemy_frame_count(edef)
    if reduced_motion or frame_count == 1:
        idx = 0
    else:
        # The bandit's idle cycle: the bob timer selects the frame.
        phase = math.sin(bob * 4)
        if phase > 0:
            idx = 1  # lean forward
        elif phase < 0:
            idx = 2  # lean back
        else:
            idx = 0  # neutral
    return sheet.subsurface((idx * size, 0, size, size))


# === Firefly ===
_FIREFLY_CACHE: dict[tuple, pygame.Surface] = {}


def firefly_surface(size: int = 10, hue: int = 60) -> pygame.Surface:
    key = (size, hue)
    cached = _FIREFLY_CACHE.get(key)
    if cached is not None:
        return cached
    s = pygame.Surface((size * 4, size * 4), pygame.SRCALPHA)
    cx = size * 2
    col = hsl(hue, 0.9, 0.7)
    for i in range(4):
        r = size * 2 - i * 3
        a = 60 - i * 12
        glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, a), (r, r), r)
        s.blit(glow, (cx - r, cx - r))
    pygame.draw.circle(s, col, (cx, cx), size // 2 + 1)
    pygame.draw.circle(s, (255, 255, 255), (cx, cx), max(1, size // 3))
    # Task 32 (gfx-outline-shading-squash): apply the shading ramp at
    # cache time (the outline is skipped for the firefly — the firefly
    # is a soft glow, not a hard sprite; a 1px outline would clash with
    # the soft glow halo. The shading ramp still applies so the core
    # reads as warm).
    apply_shading_ramp(s)
    s = s.convert_alpha()
    _FIREFLY_CACHE[key] = s
    return s


# === Building icons ===
_BUILDING_CACHE: dict[tuple, pygame.Surface] = {}


def building_surface(bid: str, size: int = 48) -> pygame.Surface:
    key = (bid, size)
    cached = _BUILDING_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    roof = (180, 60, 60)
    wall = (60, 50, 50)
    if bid in ("farm", "sawmill", "mine"):
        pygame.draw.rect(surf, wall, (cx - 14, cy - 4, 28, 18))
        pygame.draw.polygon(surf, roof, [(cx - 16, cy - 4), (cx + 16, cy - 4), (cx, cy - 18)])
    elif bid in ("tavern", "blacksmith", "barracks"):
        pygame.draw.rect(surf, wall, (cx - 16, cy - 6, 32, 22))
        pygame.draw.rect(surf, roof, (cx - 18, cy - 8, 36, 5))
    elif bid == "dojo":
        pygame.draw.rect(surf, (200, 80, 80), (cx - 16, cy - 2, 4, 22))
        pygame.draw.rect(surf, (200, 80, 80), (cx + 12, cy - 2, 4, 22))
        pygame.draw.rect(surf, (200, 80, 80), (cx - 20, cy - 6, 40, 5))
        pygame.draw.rect(surf, (200, 80, 80), (cx - 18, cy - 14, 36, 4))
    else:
        for i in range(3):
            w = 30 - i * 6
            y = cy - 6 + i * 8
            pygame.draw.rect(surf, wall, (cx - w // 2, y, w, 6))
            pygame.draw.polygon(surf, roof, [(cx - w // 2 - 2, y), (cx + w // 2 + 2, y), (cx, y - 6)])
    # Task 32: apply the outline + shading ramp at cache time.
    apply_shading_ramp(surf)
    surf = outline_array(surf)
    surf = surf.convert_alpha()
    _BUILDING_CACHE[key] = surf
    return surf


# === Pet icons ===
_PET_CACHE: dict[tuple, pygame.Surface] = {}


def pet_surface(pid: str, hue: int, size: int = 40) -> pygame.Surface:
    key = (pid, size)
    cached = _PET_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    col = hsl(hue, 0.6, 0.55)
    pygame.draw.ellipse(surf, col, (cx - 12, cy - 6, 24, 18))
    pygame.draw.circle(surf, col, (cx - 10, cy - 8), 5)
    pygame.draw.circle(surf, col, (cx + 10, cy - 8), 5)
    pygame.draw.circle(surf, (20, 20, 30), (cx - 5, cy - 2), 2)
    pygame.draw.circle(surf, (20, 20, 30), (cx + 5, cy - 2), 2)
    # Task 32: apply the outline + shading ramp at cache time.
    apply_shading_ramp(surf)
    surf = outline_array(surf)
    surf = surf.convert_alpha()
    _PET_CACHE[key] = surf
    return surf


# === Background ===
_BG_CACHE: dict[tuple, pygame.Surface] = {}


def background(zone_index: int, zone_hue: int) -> pygame.Surface:
    key = ("bg", zone_index, zone_hue)
    cached = _BG_CACHE.get(key)
    if cached is not None:
        return cached
    from theme import C, gradient_v
    surf = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H)).convert()
    sky_top = hsl(zone_hue, 0.5, 0.15)
    sky_bottom = hsl(zone_hue, 0.4, 0.25)
    gradient_v(surf, pygame.Rect(0, 0, cfg.WINDOW_W, cfg.ROAD_TOP), sky_top, sky_bottom)
    pygame.draw.circle(surf, (240, 235, 220), (cfg.WINDOW_W - 120, 50), 28)
    moon = pygame.Surface((70, 70), pygame.SRCALPHA)
    pygame.draw.circle(moon, (240, 235, 220, 60), (35, 35), 34)
    surf.blit(moon, (cfg.WINDOW_W - 155, 15))
    for _ in range(60):
        x = rng().randint(0, cfg.WINDOW_W)
        y = rng().randint(0, cfg.ROAD_TOP - 10)
        b = rng().randint(120, 200)
        surf.set_at((x, y), (b, b, min(255, b + 30)))
    hill_col = hsl(zone_hue, 0.4, 0.18)
    pts = [(0, cfg.ROAD_TOP)]
    x = 0
    while x < cfg.WINDOW_W + 40:
        pts.append((x, cfg.ROAD_TOP - 30 - (math.sin(x * 0.02) * 20 + 20)))
        x += 40
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(surf, hill_col, pts)
    mid_col = hsl(zone_hue, 0.45, 0.13)
    pts = [(0, cfg.ROAD_TOP)]
    x = 0
    while x < cfg.WINDOW_W + 60:
        pts.append((x, cfg.ROAD_TOP - 14 - (math.sin(x * 0.035 + 1.2) * 12 + 12)))
        x += 60
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(surf, mid_col, pts)
    pygame.draw.rect(surf, C.road, (0, cfg.ROAD_TOP, cfg.WINDOW_W, cfg.ROAD_H))
    pygame.draw.rect(surf, C.road_edge, (0, cfg.ROAD_TOP, cfg.WINDOW_W, 4))
    pygame.draw.rect(surf, C.road_edge, (0, cfg.ROAD_BOTTOM - 4, cfg.WINDOW_W, 4))
    for x in range(0, cfg.WINDOW_W, 60):
        pygame.draw.rect(surf, C.lane_line, (x + 20, cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2, 30, 4))
    for x in range(80, cfg.WINDOW_W, 200):
        pygame.draw.rect(surf, (40, 30, 30), (x, cfg.ROAD_TOP - 8, 3, 10))
        pygame.draw.circle(surf, (255, 140, 60), (x + 1, cfg.ROAD_TOP - 12), 5)
        glow = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 140, 60, 40), (12, 12), 12)
        surf.blit(glow, (x - 11, cfg.ROAD_TOP - 24))
    _BG_CACHE[key] = surf
    return surf


# === Parallax layers (Task 29 / gfx-parallax) ===
# 5 pre-baked scrollable background layers (sky, far hills, mid hills,
# near foliage, road) blit at parallax offsets [0, 0.15, 0.35, 0.6, 1.0]
# from a single scroll accumulator. Cached per (zone_in_cycle, hue) so
# the cache is bounded (9 zones x hues x 5 layers, not unbounded across
# cycles). Each layer is a full-screen SRCALPHA surface; scrollable
# layers tile horizontally at WINDOW_W so they wrap seamlessly.
_PARALLAX_CACHE: dict[tuple, list] = {}


def parallax_layers(zone_index: int, hue: int) -> list:
    """Return 5 cached parallax background layers.

    Layers (in draw order, with their parallax offsets):
      0. Sky         (offset 0.0  — no scroll; gradient + moon + stars)
      1. Far hills   (offset 0.15 — scrolls slowly; tileable silhouette)
      2. Mid hills   (offset 0.35 — scrolls medium; tileable silhouette)
      3. Near foliage(offset 0.6  — scrolls faster; bushes + torches)
      4. Road        (offset 1.0  — scrolls full; road rect + lane lines)

    Each layer is a full-screen (WINDOW_W x WINDOW_H) SRCALPHA surface
    cached per (zone_in_cycle, hue) with ``convert_alpha`` so the cache
    is bounded (9 zones x hues, not unbounded across cycles). The
    scrollable layers (1-4) use sine frequencies that are integer
    multiples of 2*pi/WINDOW_W so the hill silhouettes tile seamlessly
    at WINDOW_W (the y at x=0 and x=WINDOW_W match, so wrapping is
    invisible). The caller blits each layer at ``-int(scroll * offset)
    % WINDOW_W`` and ``- int(scroll * offset) % WINDOW_W - WINDOW_W`` to
    cover the screen.
    """
    in_cycle = zone_index % 9
    key = ("parallax", in_cycle, hue)
    cached = _PARALLAX_CACHE.get(key)
    if cached is not None:
        return cached
    from theme import C, gradient_v
    layers = []
    # Layer 0: Sky (offset 0, no scroll). Gradient + moon + stars in the
    # top portion (0..ROAD_TOP); transparent below so the hill + road
    # layers composite underneath.
    sky = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    sky_top = hsl(hue, 0.5, 0.15)
    sky_bottom = hsl(hue, 0.4, 0.25)
    gradient_v(sky, pygame.Rect(0, 0, cfg.WINDOW_W, cfg.ROAD_TOP),
               sky_top, sky_bottom)
    pygame.draw.circle(sky, (240, 235, 220), (cfg.WINDOW_W - 120, 50), 28)
    moon = pygame.Surface((70, 70), pygame.SRCALPHA)
    pygame.draw.circle(moon, (240, 235, 220, 60), (35, 35), 34)
    sky.blit(moon, (cfg.WINDOW_W - 155, 15))
    for _ in range(60):
        x = rng().randint(0, cfg.WINDOW_W)
        y = rng().randint(0, cfg.ROAD_TOP - 10)
        b = rng().randint(120, 200)
        sky.set_at((x, y), (b, b, min(255, b + 30)))
    layers.append(sky.convert_alpha())
    # Layer 1: Far hills (offset 0.15, tileable at WINDOW_W). The hill
    # line uses sin(x * 2*pi*4/WINDOW_W) so 4 peaks tile seamlessly.
    fh = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    hill_col = hsl(hue, 0.4, 0.18)
    pts = [(0, cfg.ROAD_TOP)]
    for x in range(0, cfg.WINDOW_W + 1, 20):
        y = cfg.ROAD_TOP - 30 - (math.sin(x * 2 * math.pi * 4 / cfg.WINDOW_W) * 20 + 20)
        pts.append((x, y))
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(fh, hill_col, pts)
    layers.append(fh.convert_alpha())
    # Layer 2: Mid hills (offset 0.35, tileable at WINDOW_W). 5 peaks.
    mh = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    mid_col = hsl(hue, 0.45, 0.13)
    pts = [(0, cfg.ROAD_TOP)]
    for x in range(0, cfg.WINDOW_W + 1, 30):
        y = cfg.ROAD_TOP - 14 - (math.sin(x * 2 * math.pi * 5 / cfg.WINDOW_W + 1.2) * 12 + 12)
        pts.append((x, y))
    pts.append((cfg.WINDOW_W, cfg.ROAD_TOP))
    pygame.draw.polygon(mh, mid_col, pts)
    layers.append(mh.convert_alpha())
    # Layer 3: Near foliage (offset 0.6, tileable at WINDOW_W). Bushes
    # at 80px intervals + roadside torches at 160px intervals along the
    # road edge. 80 and 160 both divide WINDOW_W (1280/80=16, 1280/160=8)
    # so the foliage tiles seamlessly at WINDOW_W.
    nf = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    foliage_col = hsl(hue, 0.5, 0.10)
    for x in range(0, cfg.WINDOW_W, 80):
        pygame.draw.circle(nf, foliage_col, (x + 20, cfg.ROAD_TOP - 4), 8)
        pygame.draw.circle(nf, foliage_col, (x + 40, cfg.ROAD_TOP - 2), 6)
    for x in range(80, cfg.WINDOW_W, 160):
        pygame.draw.rect(nf, (40, 30, 30), (x, cfg.ROAD_TOP - 8, 3, 10))
        pygame.draw.circle(nf, (255, 140, 60), (x + 1, cfg.ROAD_TOP - 12), 5)
    layers.append(nf.convert_alpha())
    # Layer 4: Road (offset 1.0, tileable at WINDOW_W). The road rect +
    # lane lines. Lane lines at 64px intervals (64 divides WINDOW_W =
    # 1280) so the lines tile seamlessly.
    rd = pygame.Surface((cfg.WINDOW_W, cfg.WINDOW_H), pygame.SRCALPHA)
    pygame.draw.rect(rd, C.road, (0, cfg.ROAD_TOP, cfg.WINDOW_W, cfg.ROAD_H))
    pygame.draw.rect(rd, C.road_edge, (0, cfg.ROAD_TOP, cfg.WINDOW_W, 4))
    pygame.draw.rect(rd, C.road_edge, (0, cfg.ROAD_BOTTOM - 4, cfg.WINDOW_W, 4))
    for x in range(0, cfg.WINDOW_W, 64):
        pygame.draw.rect(rd, C.lane_line,
                         (x + 32, cfg.ROAD_TOP + cfg.ROAD_H // 2 - 2, 30, 4))
    layers.append(rd.convert_alpha())
    _PARALLAX_CACHE[key] = layers
    return layers


# === Particles ===
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity")
    def __init__(self, x, y, vx, vy, life, color, size=3, gravity=0.0):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.color = color; self.size = size; self.gravity = gravity
    def update(self, dt):
        self.x += self.vx * dt; self.y += self.vy * dt
        self.vy += self.gravity * dt; self.life -= dt
    @property
    def alive(self): return self.life > 0


class ParticleSystem:
    def __init__(self):
        self.particles: list[Particle] = []
    def burst(self, x, y, color, count=12, speed=120, life=0.4, size=3):
        for _ in range(count):
            ang = rng().uniform(0, math.tau)
            sp = rng().uniform(speed * 0.4, speed)
            self.particles.append(Particle(x, y, math.cos(ang) * sp, math.sin(ang) * sp,
                                            life * rng().uniform(0.6, 1.2), color, size, 200))
    def trail(self, x, y, color, count=1, size=2):
        for _ in range(count):
            self.particles.append(Particle(x + rng().uniform(-2, 2), y + rng().uniform(-2, 2),
                                           rng().uniform(-10, 10), rng().uniform(-10, 10), 0.3, color, size))
    def update(self, dt):
        for p in self.particles: p.update(dt)
        self.particles = [p for p in self.particles if p.alive]
    def draw(self, surf):
        for p in self.particles:
            a = max(0, min(255, int(255 * (p.life / p.max_life))))
            r = max(1, int(p.size))
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*p.color, a), (r, r), r)
            surf.blit(s, (p.x - r, p.y - r))


# === Procedural SFX ===
_SFX: dict[str, object] = {}
_SFX_OK = False


# ---------------------------------------------------------------------------
# Layered SFX (Task 37 / pl-music-sfx)
# ---------------------------------------------------------------------------
# The single-sine tones above are upgraded to layered SFX: an ADSR
# envelope (attack/decay/sustain/release) replaces the pure exponential
# decay; a filtered noise burst layers with the tone for a richer
# transient; a small random detune (±2%) per build adds subtle variation
# so repeated taps don't sound identical. Noise-layer gains are
# conservative (a small fraction of the tone gain) for sound-sensitive
# players. The ``play(name, sound_on)`` API and the ``_SFX`` dict are
# unchanged -- callers still pass ``state.sound_on``; only the timbre is
# richer.

def _adsr(n, sr, dur, *, attack, decay_t, sustain, release_t):
    """An ADSR envelope of length ``n``.

    ``attack`` is in seconds; ``decay_t`` and ``release_t`` are fractions
    of ``dur``; ``sustain`` is the held level (0..1). Falls back to a
    flat envelope if the segments don't fit (no crash on very short
    sounds).
    """
    env = np.zeros(n, dtype=np.float32)
    if n <= 0:
        return env
    a = int(sr * attack)
    d = int(n * decay_t)
    r = int(n * release_t)
    # Clamp segments so attack + decay + release never exceeds n.
    a = min(a, n)
    d = min(d, max(0, n - a))
    r = min(r, max(0, n - a - d))
    if a > 0:
        env[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if d > 0:
        env[a:a + d] = np.linspace(1, sustain, d, dtype=np.float32)
    sus_end = n - r
    if sus_end > a + d:
        env[a + d:sus_end] = sustain
    if r > 0:
        env[-r:] = np.linspace(sustain, 0, r, dtype=np.float32)
    return env


def _noise_burst(n, sr, dur, *, decay=10.0):
    """A noise burst with an exponential decay (a transient layer).

    Normalized to ~unit peak so the caller can scale it by a small gain.
    """
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    noise = np.random.standard_normal(n).astype(np.float32)
    noise *= np.exp(-np.arange(n) / sr * decay)
    m = float(np.max(np.abs(noise)) + 1e-9)
    return noise / m


def _make_tone(freq, dur, vol=0.3, decay=8.0, harmonics=1, noise=0.0):
    """Layered SFX tone: ADSR envelope + optional noise layer + pitch variation.

    Replaces the single-sine tone (Task 37 / pl-music-sfx). ``noise`` is
    the noise-layer gain as a fraction of ``vol`` (conservative: 0.0-0.1).
    """
    try:
        sr = 22050; n = int(sr * dur); t = np.arange(n) / sr
        # Pitch variation: a small random detune per build (±2%).
        detune = 1.0 + rng().uniform(-0.02, 0.02)
        f = freq * detune
        wave = np.zeros(n, dtype=np.float32)
        for h in range(1, harmonics + 1):
            wave += (1.0 / h) * np.sin(2 * np.pi * f * h * t)
        # ADSR envelope (fast attack, decay to sustain, release).
        env = _adsr(n, sr, dur, attack=0.005, decay_t=0.1,
                   sustain=0.7, release_t=0.05)
        # A long-decay tail (the original exponential) layered under the
        # ADSR so short taps still decay naturally.
        wave *= vol * env * np.exp(-t * decay)
        # Noise layer (filtered noise burst) at a conservative gain.
        if noise > 0:
            wave += _noise_burst(n, sr, dur, decay=decay) * (vol * noise)
        stereo = np.column_stack([wave, wave])
        return pygame.sndarray.make_sound((stereo * 32767).astype(np.int16))
    except Exception:
        return None


def _make_sweep(f0, f1, dur, vol=0.3, noise=0.0):
    """Layered SFX sweep: ADSR + pitch sweep + pitch variation + noise layer."""
    try:
        sr = 22050; n = int(sr * dur); t = np.arange(n) / sr
        # Pitch variation: a small random detune per build (±2%).
        detune = 1.0 + rng().uniform(-0.02, 0.02)
        freq = (f0 + (f1 - f0) * (t / dur)) * detune
        phase = 2 * np.pi * np.cumsum(freq) / sr
        wave = np.sin(phase)
        env = _adsr(n, sr, dur, attack=0.005, decay_t=0.1,
                   sustain=0.7, release_t=0.1)
        wave *= vol * env * np.exp(-t * 4)
        if noise > 0:
            wave += _noise_burst(n, sr, dur, decay=8.0) * (vol * noise)
        stereo = np.column_stack([wave, wave])
        return pygame.sndarray.make_sound((stereo * 32767).astype(np.int16))
    except Exception:
        return None


def init_sfx():
    global _SFX_OK
    if _SFX_OK:
        return
    try:
        if not pygame.mixer.get_init():
            return
        _SFX["tap"] = _make_tone(330, 0.05, 0.15, 20, noise=0.05)
        _SFX["crit"] = _make_tone(660, 0.10, 0.22, 10, 2, noise=0.06)
        _SFX["kill"] = _make_tone(220, 0.08, 0.18, 12, noise=0.05)
        _SFX["boss"] = _make_tone(110, 0.5, 0.35, 4, 3, noise=0.08)
        _SFX["firefly"] = _make_sweep(600, 1200, 0.3, 0.25, noise=0.04)
        _SFX["skill"] = _make_sweep(300, 900, 0.4, 0.25, noise=0.05)
        _SFX["ascend"] = _make_sweep(200, 1200, 1.0, 0.35, noise=0.06)
        _SFX["gacha"] = _make_sweep(400, 800, 0.3, 0.25, noise=0.04)
        # Task 25 (gp-skill-synergy-rhythm): a soft, short, high-pitched
        # tick for the rhythm streak increment -- a non-visual cue for
        # reduced_motion players (the visual rhythm display is suppressed
        # when reduced_motion is on; the tick is the alternative cue).
        _SFX["tick"] = _make_tone(880, 0.03, 0.08, 30)
        # Task 27 (pl-juice-polish): a soft, high-pitched chime for the
        # skill cooldown-ready cue. The chime respects ``sound_on`` (the
        # screen passes ``state.sound_on`` to ``play``); the visual glow
        # + cooldown progress fill are the non-visual cues for
        # ``reduced_motion`` players (the chime is the audio cue).
        _SFX["skill_ready"] = _make_sweep(600, 1200, 0.25, 0.20)
        # Task 37 (pl-music-sfx): UI sounds -- a short click for button
        # presses and a soft confirm for confirmations. Conservative
        # volumes + a small noise layer so they read as a real click, not
        # a pure sine beep.
        _SFX["ui_click"] = _make_tone(520, 0.04, 0.10, 25, noise=0.04)
        _SFX["ui_confirm"] = _make_tone(740, 0.08, 0.14, 14, 2, noise=0.04)
        _SFX_OK = True
    except Exception:
        _SFX_OK = False


def play(name, sound_on=True):
    if not sound_on or not _SFX_OK:
        return
    snd = _SFX.get(name)
    if snd is None:
        return
    try:
        # Guard against the mixer being quit between init_sfx() and play()
        # (e.g. a test fixture quits pygame; _SFX_OK stays True but the
        # mixer is gone, and snd.play() segfaults). The get_init() check
        # is cheap and prevents the segfault.
        if not pygame.mixer.get_init():
            return
        snd.play()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Generative ambient music (Task 37 / pl-music-sfx)
# ---------------------------------------------------------------------------
# A NumPy generative engine: a slow drone (a low sustained note with a
# slow amplitude LFO) + a plucked koto-like melody (a random walk over the
# 5 notes of the major pentatonic scale relative to ``root_hz`` -- root,
# min3, 4th, 5th, octave -- plucked = fast attack + exponential decay)
# + taiko percussion (a low boom = a noise burst with a fast decay + a
# low sine thump on the downbeats). The segment is ``bars`` bars at a
# tempo (default 90 BPM -> 4 bars ~= 10.7s). The root_hz is mapped from
# the zone hue (the zone's element/color -> a base frequency).
#
# The segment is returned as a stereo int16 NumPy array (the raw array is
# more testable than a ``pygame.Sound`` -- the brief's specimen test calls
# ``generate_music_segment(root_hz=220, bars=4)`` and asserts no crash).
# ``make_music_sound`` wraps the array in a ``pygame.Sound`` for playback.
#
# Volumes are CONSERVATIVE (the drone + melody + percussion mix at low
# individual gains so the total is gentle -- sound-sensitive players).
# The music loop in ``main.py`` scales the output by ``state.volume``.

# The 5 notes of the major pentatonic scale, as frequency ratios relative
# to the root: root, min3, 4th, 5th, octave. (The major pentatonic is
# root, M2, M3, 5, M6 -- but the brief specifies "root, min3, 4th, 5th,
# octave", which is the minor pentatonic shape; we follow the brief.)
_PENTATONIC_RATIOS = (1.0, 6.0 / 5.0, 4.0 / 3.0, 3.0 / 2.0, 2.0)

# A conservative per-layer gain (the drone + melody + percussion mix at
# low individual volumes so the total is gentle).
_DRONE_GAIN = 0.06
_MELODY_GAIN = 0.10
_PERCUSSION_GAIN = 0.12

_MUSIC_SR = 22050          # sample rate for the music segments
_MUSIC_BPM = 90            # tempo (beats per minute)
_MUSIC_BEATS_PER_BAR = 4   # 4/4 time


def _music_seconds(bars: int) -> float:
    """The duration in seconds of ``bars`` bars at the music tempo."""
    return bars * _MUSIC_BEATS_PER_BAR * 60.0 / _MUSIC_BPM


def _pluck(freq, dur, sr, *, decay=6.0, harmonics=4):
    """A plucked string/koto note: fast attack + exponential decay + harmonics.

    A simple decaying-sine-with-harics model (a Karplus-Strong-style
    approximation without the delay line -- the decaying harmonics give
    the plucked timbre). Returns a float32 mono array.
    """
    n = int(sr * dur)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n) / sr
    wave = np.zeros(n, dtype=np.float32)
    for h in range(1, harmonics + 1):
        wave += (1.0 / h) * np.sin(2 * np.pi * freq * h * t)
    # Fast attack (2ms) + exponential decay.
    a = max(1, int(sr * 0.002))
    env = np.ones(n, dtype=np.float32)
    env[:a] = np.linspace(0, 1, a, dtype=np.float32)
    env *= np.exp(-t * decay)
    return wave * env


def _taiko_hit(dur, sr, nrng=None):
    """A taiko boom: a low sine thump + a noise burst with a fast decay.

    ``nrng`` is an optional numpy Generator for deterministic noise (the
    per-cycle seed). If None, the global numpy RNG is used.
    """
    n = int(sr * dur)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n) / sr
    # Low sine thump (60 Hz) with a fast pitch drop + decay.
    thump = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 12)
    # Noise burst with a fast decay (the "body" of the drum).
    if nrng is not None:
        noise = nrng.standard_normal(n).astype(np.float32)
    else:
        noise = np.random.standard_normal(n).astype(np.float32)
    noise *= np.exp(-t * 25)
    m = float(np.max(np.abs(noise)) + 1e-9)
    noise /= m
    return thump * 0.7 + noise * 0.3


def generate_music_segment(root_hz: float, bars: int = 4, *, seed: int | None = None):
    """Generate a 4-bar ambient music segment keyed to ``root_hz``.

    A slow drone (a low sustained note at ``root_hz`` / 2 with a slow
    amplitude LFO) + a plucked koto-like melody (a random walk over the
    pentatonic notes, re-rolled each cycle for non-repetition) + taiko
    percussion (a low boom on the downbeats). Returns a stereo int16
    NumPy array, or ``None`` if NumPy/pygame is unavailable (degrades
    gracefully -- the caller checks for None).

    ``seed`` is for deterministic generation within a cycle (the music
    loop re-rolls each cycle so the melody doesn't repeat; the seed is
    per-cycle, not global). If ``None``, the per-run RNG is used. The
    seed drives BOTH the melodic random walk (a Python ``Random``) and
    the percussion noise (a numpy ``default_rng``) so a given seed
    reproduces the segment exactly.
    """
    try:
        sr = _MUSIC_SR
        dur = _music_seconds(bars)
        n = int(sr * dur)
        if n <= 0:
            return None
        t = np.arange(n) / sr
        # Per-cycle RNGs: a Python Random for the melodic random walk +
        # a numpy default_rng for the percussion noise (both seeded by
        # ``seed`` so a given seed reproduces the segment exactly).
        r = rng() if seed is None else __import__("random").Random(seed)
        nrng = np.random.default_rng() if seed is None else np.random.default_rng(seed)

        # --- Drone: a low sustained note at root_hz / 2 with a slow LFO ---
        drone_freq = root_hz / 2.0
        drone = np.sin(2 * np.pi * drone_freq * t)
        # Slow amplitude LFO (0.1 Hz) so the drone breathes.
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
        drone = drone * lfo * _DRONE_GAIN

        # --- Melody: a random walk over the pentatonic notes ---
        # The melody plays a note every beat; each note is a pluck with
        # an exponential decay. A random walk over the pentatonic notes
        # (re-rolled each cycle) gives a gentle, non-repeating melody.
        beats_per_bar = _MUSIC_BEATS_PER_BAR
        total_beats = bars * beats_per_bar
        beat_dur = dur / total_beats
        beat_n = int(sr * beat_dur)
        melody = np.zeros(n, dtype=np.float32)
        # The pentatonic notes relative to root_hz.
        notes = [root_hz * ratio for ratio in _PENTATONIC_RATIOS]
        # Random walk over the pentatonic notes (start at the root).
        idx = 0
        for b in range(total_beats):
            # Pluck the current note.
            note = _pluck(notes[idx], beat_dur * 1.5, sr,
                         decay=5.0 + r.uniform(0, 2))
            # Place it at the beat (with a small human timing jitter).
            jitter = int(r.uniform(-0.05, 0.05) * sr)
            start = b * beat_n + jitter
            end = start + len(note)
            if 0 <= start < n and end <= n:
                melody[start:end] += note * _MELODY_GAIN
            # Random walk: step up/down/stay in the pentatonic scale.
            step = r.choice((-1, 0, 0, 1))
            idx = max(0, min(len(notes) - 1, idx + step))

        # --- Taiko percussion: a low boom on the downbeats ---
        # A "downbeat" is beat 0 of each bar; the other beats are quiet
        # or silent (a gentle, not driving, rhythm).
        percussion = np.zeros(n, dtype=np.float32)
        for b in range(total_beats):
            if b % beats_per_bar == 0:
                hit = _taiko_hit(0.25, sr, nrng=nrng)
                start = b * beat_n
                end = start + len(hit)
                if end <= n:
                    percussion[start:end] += hit * _PERCUSSION_GAIN

        # --- Mix to stereo ---
        mix = drone + melody + percussion
        # Soft clip to avoid harsh peaks (the mix is already conservative).
        mix = np.tanh(mix * 1.2) * 0.9
        stereo = np.column_stack([mix, mix])
        return (stereo * 32767).astype(np.int16)
    except Exception:
        # Degrade gracefully: return None (the caller checks for None).
        return None


def make_music_sound(root_hz: float, bars: int = 4, *, seed: int | None = None):
    """Wrap a generated music segment in a ``pygame.Sound`` for playback.

    Returns ``None`` if the mixer is unavailable or the segment fails to
    generate (degrades gracefully -- no crash, no sound).
    """
    try:
        if not pygame.mixer.get_init():
            return None
        arr = generate_music_segment(root_hz, bars=bars, seed=seed)
        if arr is None:
            return None
        return pygame.sndarray.make_sound(arr)
    except Exception:
        return None


def root_hz_for_zone(zone_index: int, zone_hue: int) -> float:
    """Map a zone's hue to a base frequency for the ambient music.

    The hue (0..360) is mapped to a frequency in a gentle range
    (220..440 Hz, roughly A3 to A4) so the root note is always in a
    pleasant register. The zone_index adds a slow drift so later zones
    are slightly lower (darker) -- a subtle audio cue for progression.
    """
    # Hue -> frequency: map 0..360 to 220..440 Hz (A3 to A4).
    base = 220.0 + (zone_hue % 360) / 360.0 * 220.0
    # Slow drift: later zones are slightly lower (darker).
    drift = -5.0 * (zone_index % 9)
    return max(110.0, base + drift)
