"""ParticleSystem2 must be pooled — no per-frame Surface allocations after warm-up.

The legacy ``assets.ParticleSystem`` allocated a fresh ``SRCALPHA`` Surface
per particle per frame in its ``draw()``, which at combat peak is ~100-300
Surface allocations/sec. ``engine.particles.ParticleSystem2`` instead caches
per-(shape, size-bucket) scratch surfaces in ``_scratch_cache`` and reuses
them forever; dead particles return to a free list and are recycled.

Acceptance criteria covered:
- ``main.py`` instantiates ``ParticleSystem2`` instead of
  ``assets.ParticleSystem`` (checked by an attribute-type assertion on a
  constructed ``Game``).
- No per-frame Surface allocations after warm-up — checked by counting
  ``len(ps._scratch_cache)`` across 60 frames of update+draw+burst. The
  cache may grow during warm-up (the first frames populate the per-size
  buckets) but must stabilise once every visited bucket exists.
- Particle count capped per quality tier — ``ParticleSystem2`` honours a
  ``max_particles`` cap; once the active list reaches the cap, further
  ``burst`` calls do not exceed it. (For now the cap is a fixed max; Task
  10's render-tier will rebind it later.)
- Visual parity with the legacy system at the default tier (smoke test
  passes — checked separately in ``test_smoke.py``).
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def test_no_per_frame_scratch_allocations(pygame_headless):
    """After warm-up, draw+update+burst must not grow the scratch cache."""
    import pygame
    from engine.particles import ParticleSystem2

    ps = ParticleSystem2()
    surf = pygame.Surface((1280, 720))
    # Prime the pump: a burst + a draw populates every (shape, size) bucket
    # the loop below will visit.
    ps.burst(100, 100, (255, 200, 90), count=20)
    ps.draw(surf)
    allocs_before = len(ps._scratch_cache)
    # Drive 60 frames, spawning fresh bursts each frame to exercise the
    # pool's reuse path. The cache must not grow.
    for _ in range(60):
        ps.update(1 / 60)
        ps.draw(surf)
        ps.burst(100, 100, (255, 200, 90), count=5, life=0.3)
    allocs_after = len(ps._scratch_cache)
    assert allocs_after == allocs_before, (
        f"leaked {allocs_after - allocs_before} scratch surfaces "
        f"(before={allocs_before}, after={allocs_after})"
    )


def test_particle_pool_reuses_after_warmup(pygame_headless):
    """Dead particles return to the pool and are recycled — no Particle growth."""
    from engine.particles import ParticleSystem2

    ps = ParticleSystem2()
    # Warm up with a few bursts so the pool has some particles to recycle.
    for _ in range(5):
        ps.burst(100, 100, (255, 200, 90), count=12, life=0.3)
        ps.update(1 / 60)
    # Drain.
    for _ in range(60):
        ps.update(1 / 60)
    pool_size_after_warm = len(ps._pool)
    # Now run a steady-state loop: bursts spawn, particles die, the pool
    # hands them back. Neither the active list nor the pool should grow
    # without bound.
    for _ in range(120):
        ps.burst(100, 100, (255, 200, 90), count=8, life=0.3)
        ps.update(1 / 60)
        # Active count must stay bounded by the cap (default large; here
        # we just assert it never escapes to thousands).
        assert len(ps._active) < 5000
    # The pool may have grown if more particles were simultaneously alive
    # than warm-up reached, but after the drain the active list is empty
    # and the pool is stable.
    for _ in range(120):
        ps.update(1 / 60)
    assert len(ps._active) == 0
    # After everything dies, the pool holds every Particle ever allocated;
    # a second burst reuses them (no new Particle() calls).
    pool_before = len(ps._pool)
    ps.burst(100, 100, (255, 200, 90), count=20, life=0.3)
    # All 20 should come from the pool, not from new allocations.
    assert len(ps._active) == 20
    assert len(ps._pool) == pool_before - 20


def test_max_particles_cap(pygame_headless):
    """ParticleSystem2 must cap active particles per quality tier."""
    from engine.particles import ParticleSystem2

    # A small cap simulates a low-quality tier. The system must not exceed
    # it even under sustained burst pressure.
    cap = 40
    ps = ParticleSystem2(max_particles=cap)
    # Hammer it with far more bursts than the cap can hold.
    for _ in range(50):
        ps.burst(100, 100, (255, 200, 90), count=20, life=2.0)
        ps.update(1 / 60)
    assert len(ps._active) <= cap, (
        f"active {len(ps._active)} exceeded cap {cap}"
    )


def test_main_uses_particle_system2():
    """main.Game must instantiate ParticleSystem2, not the legacy ParticleSystem."""
    import main
    from engine.particles import ParticleSystem2

    g = main.Game()
    assert isinstance(g.particles, ParticleSystem2), (
        f"main.Game.particles is {type(g.particles).__name__}, "
        "expected ParticleSystem2"
    )
    # Cleanup: quit pygame so later tests can re-init.
    import pygame
    pygame.quit()
