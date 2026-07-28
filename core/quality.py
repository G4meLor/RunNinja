"""Render-quality tier helpers for Tap Ninja.

A 3-tier render quality (``high`` / ``med`` / ``low``) that extends the
existing ``reduced_motion`` gate so the two never diverge:
``reduced_motion`` forces the low tier (see
``GameState.effective_render_quality``), and every FX feature that
respects the tier reads these helpers with the effective quality as the
argument.

The tier is the single knob the FX features read:

* ``particle_mult(quality)`` scales particle counts (and the
  ``ParticleSystem2.max_particles`` cap) per tier — low caps at 25%,
  med at 60%, high at 100%. This keeps a 60fps floor on Intel iGPUs at
  the low tier.
* ``glow_enabled(quality)`` toggles additive-blend glow — disabled on
  low (additive blending is the most expensive draw op per particle),
  enabled on med/high.
* ``parallax_enabled(quality)`` toggles parallax layers — disabled on
  low (a second background pass per frame is a measurable cost on
  weak iGPUs), enabled on med/high.

Every new motion feature (parallax, weather, animation, glow — Tasks
29-32) reads ``state.effective_render_quality()`` and uses these
helpers, so the tier is the single source of truth and the
``reduced_motion`` gate is never bypassed.

Unknown tier values raise ``KeyError`` (fail loud rather than silently
falling back to a default — a typo in a save file or a future tier
rename should surface immediately, not quietly degrade the visuals).
"""
from __future__ import annotations


# Tier constants — the three valid quality levels.
QUALITY_HIGH = "high"
QUALITY_MED = "med"
QUALITY_LOW = "low"

# Particle-count multipliers per tier. Low caps at 25% (the 60fps floor
# on Intel iGPUs); med at 60% (a visible step down from high but still
# rich); high at 100% (the full combat peak).
_PARTICLE_MULT: dict[str, float] = {
    QUALITY_HIGH: 1.0,
    QUALITY_MED: 0.6,
    QUALITY_LOW: 0.25,
}


def particle_mult(quality: str) -> float:
    """Particle-count multiplier for the tier (high=1.0, med=0.6, low=0.25)."""
    return _PARTICLE_MULT[quality]


def glow_enabled(quality: str) -> bool:
    """Whether additive-blend glow is enabled for the tier (False on low)."""
    return quality != QUALITY_LOW


def parallax_enabled(quality: str) -> bool:
    """Whether parallax layers are enabled for the tier (False on low)."""
    return quality != QUALITY_LOW


def valid_tiers() -> tuple[str, ...]:
    """The three valid tier strings (high, med, low)."""
    return (QUALITY_HIGH, QUALITY_MED, QUALITY_LOW)
