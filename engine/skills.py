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
