"""Active skills: Kunai Barrage, Shuriken Vortex, Rope Hook, Speed Step.

Each has an independent cooldown.  The runner tracks cooldown timers and
fires the skill when the player activates it (or auto-fires if unlocked
and off cooldown, for idle-friendliness).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActiveSkill:
    id: str
    name: str
    cooldown: float
    timer: float = 0.0       # current cooldown remaining
    duration: float = 0.0
    duration_timer: float = 0.0   # active-effect remaining
    active: bool = False
    desc: str = ""


SKILL_DEFS = {
    "kunai": {"name": "Kunai Barrage", "cooldown": 30.0, "duration": 0.0,
              "desc": "Throw a storm of kunai for huge burst damage."},
    "shuriken": {"name": "Shuriken Vortex", "cooldown": 60.0, "duration": 5.0,
                 "desc": "AOE damage to all enemies for 5 seconds."},
    "rope": {"name": "Rope Hook", "cooldown": 45.0, "duration": 0.0,
             "desc": "Instant-kill the weakest enemy, bonus gold."},
    "speed": {"name": "Speed Step", "cooldown": 40.0, "duration": 8.0,
              "desc": "Double attack speed for 8 seconds."},
    # Task 35 (gp-reincarnation-perks): the 5th active skill, unlocked by
    # the ``fifth_active_skill`` Soul Tree perk. A ninja-themed blink-burst:
    # a short cooldown nuke that teleports to the nearest enemy and
    # delivers a heavy single-target hit. The cooldown (50s) is in line
    # with the other skills (30-60s). The runner's ``_refresh_skills``
    # adds this skill to the active set only when the perk is in
    # ``state.soul_tree``.
    "shadow_step": {"name": "Shadow Step", "cooldown": 50.0, "duration": 0.0,
                    "desc": "Blink to the nearest enemy for a heavy single-target nuke."},
}


def make_skill(sid: str) -> ActiveSkill:
    d = SKILL_DEFS[sid]
    return ActiveSkill(id=sid, name=d["name"], cooldown=d["cooldown"],
                       duration=d["duration"], desc=d["desc"])


def tick_skill(skill: ActiveSkill, dt: float) -> None:
    if skill.timer > 0:
        skill.timer -= dt
    if skill.active:
        skill.duration_timer -= dt
        if skill.duration_timer <= 0:
            skill.active = False


def can_fire(skill: ActiveSkill) -> bool:
    return skill.timer <= 0


def fire(skill: ActiveSkill) -> None:
    skill.timer = skill.cooldown
    if skill.duration > 0:
        skill.active = True
        skill.duration_timer = skill.duration


# ---------------------------------------------------------------------------
# Skill Synergies (Task 25 / gp-skill-synergy-rhythm)
# ---------------------------------------------------------------------------
# Firing two active skills within 2s in a specific order triggers a named
# synergy bonus. The synergy is a sequencing puzzle on the 4 active skills.
# The bonus is a flat burst (NOT multiplicative with combo_mult), same
# philosophy as the finishers and fusion -- a reward for sequencing, not
# another combo-scaled nuke.
SYNERGIES: dict[tuple[str, str], str] = {
    ("kunai", "shuriken"): "Storm of Steel",
    ("speed", "kunai"):   "Lightning Strike",
    ("rope", "shuriken"): "Grinding Vortex",
    ("speed", "rope"):    "Phantom Snare",
}
# The window: the second skill must fire within this many seconds of the
# first. 2s is tight enough to be a deliberate sequencing puzzle, not an
# accident.
SYNERGY_WINDOW: float = 2.0
# The synergy's bonus damage is a flat multiple of tap_damage (capped,
# NOT multiplicative with combo_mult -- same philosophy as the finishers
# and fusion). Tuned so a synergy is a meaningful burst but not a
# replacement for the skills themselves.
SYNERGY_DMG_MULT: float = 4.0


def synergy_for(prev_sid: str, sid: str) -> str | None:
    """The synergy name for firing ``prev_sid`` then ``sid`` within the
    window, or None if the pair has no synergy (or is in the wrong order)."""
    return SYNERGIES.get((prev_sid, sid))
