"""Quest and achievement definitions.

Daily quests refresh every 24h (real time) and reward Medals + Amber.
Achievements are long-term milestones that reward Amber + medals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class DailyQuest:
    id: str
    name: str
    desc: str
    target: float            # numeric target
    progress_key: str        # which state counter to read
    reward_medals: int
    reward_amber: int


# Pool from which 3 daily quests are drawn.
DAILY_POOL: list[DailyQuest] = [
    DailyQuest("q_kill_100", "Slayer", "Defeat 100 enemies today.", 100,
               "kills_today", 5, 2),
    DailyQuest("q_kill_500", "Reaper", "Defeat 500 enemies today.", 500,
               "kills_today", 10, 3),
    DailyQuest("q_gold_1k", "Earner", "Earn 1,000 gold today.", 1000,
               "gold_earned_today", 5, 2),
    DailyQuest("q_gold_100k", "Tycoon", "Earn 100,000 gold today.", 100000,
               "gold_earned_today", 15, 4),
    DailyQuest("q_combo_50", "Combo Master", "Reach a 50 combo today.", 50,
               "best_combo_today", 8, 3),
    DailyQuest("q_combo_100", "Combo Lord", "Reach a 100 combo today.", 100,
               "best_combo_today", 15, 4),
    DailyQuest("q_skills_5", "Technician", "Use 5 active skills today.", 5,
               "skills_used_today", 8, 3),
    DailyQuest("q_ascend", "Reborn", "Ascend once today.", 1,
               "ascensions_today", 20, 6),
    DailyQuest("q_firefly_20", "Light Catcher", "Catch 20 fireflies today.", 20,
               "fireflies_today", 10, 3),
]


@dataclass
class Achievement:
    id: str
    name: str
    desc: str
    check: Callable
    reward_amber: int = 0
    reward_medals: int = 0
    # Hidden/secret achievements (gp-permanent-scaling): the ``desc`` is
    # shown only after unlock; before that, the ``hint`` (a cryptic
    # in-game teaser) is shown instead so the player has an in-game path
    # to the unlock that is NOT wiki-dependent. ``hidden`` controls the
    # display only (the ``check`` still fires normally).
    hidden: bool = False
    hint: str = ""


ACHIEVEMENTS: list[Achievement] = [
    Achievement("first_blood", "First Blood", "Defeat your first enemy.",
                lambda s: s.monsters_killed >= 1, reward_medals=5),
    Achievement("slayer", "Slayer", "Defeat your first boss.",
                lambda s: s.bosses_killed >= 1, reward_amber=1, reward_medals=10),
    Achievement("zone_5", "Trailblazer", "Reach zone 5.",
                lambda s: s.best_zone >= 5, reward_amber=2, reward_medals=20),
    Achievement("zone_9", "Voyager", "Reach the final zone.",
                lambda s: s.best_zone >= 9, reward_amber=5, reward_medals=50),
    # Cycle-based achievements: the 9 themed zones repeat forever; reaching
    # a new cycle (zone 9/27/45/90) is the post-endgame progression.
    Achievement("cycle_1", "Cycler", "Reach cycle 1 (zone 9+).",
                lambda s: s.best_zone >= 9, reward_amber=5, reward_medals=50),
    Achievement("cycle_3", "Looper", "Reach cycle 3 (zone 27+).",
                lambda s: s.best_zone >= 27, reward_amber=15, reward_medals=150),
    Achievement("cycle_5", "Ouroboros", "Reach cycle 5 (zone 45+).",
                lambda s: s.best_zone >= 45, reward_amber=40, reward_medals=400),
    Achievement("cycle_10", "Endless", "Reach cycle 10 (zone 90+).",
                lambda s: s.best_zone >= 90, reward_amber=100, reward_medals=1000),
    Achievement("combo_100", "Centurion", "Reach a 100 combo.",
                lambda s: s.best_combo_ever >= 100, reward_amber=3, reward_medals=30),
    Achievement("combo_500", "Combo Master", "Reach a 500 combo.",
                lambda s: s.best_combo_ever >= 500, reward_amber=8, reward_medals=80),
    Achievement("ascend_1", "Reborn", "Ascend for the first time.",
                lambda s: s.total_ascensions >= 1, reward_amber=5, reward_medals=50),
    Achievement("ascend_10", "Samsara", "Ascend 10 times.",
                lambda s: s.total_ascensions >= 10, reward_amber=20, reward_medals=200),
    Achievement("pets_3", "Pet Collector", "Own 3 pets.",
                lambda s: len(s.pets) >= 3, reward_amber=5, reward_medals=30),
    Achievement("pets_all", "Zoo Keeper", "Collect all 12 pets.",
                lambda s: len(s.pets) >= 12, reward_amber=50, reward_medals=500),
    Achievement("skills_10", "Scholar", "Unlock 10 skill-tree nodes.",
                lambda s: len(s.skill_tree) >= 10, reward_amber=5, reward_medals=40),
    Achievement("skills_50", "Sage", "Unlock 50 skill-tree nodes.",
                lambda s: len(s.skill_tree) >= 50, reward_amber=30, reward_medals=300),
    Achievement("gold_1m", "Midas", "Earn 1 million gold total.",
                lambda s: s.lifetime_gold >= 1e6, reward_amber=10, reward_medals=100),
    Achievement("gold_1b", "Croesus", "Earn 1 billion gold total.",
                lambda s: s.lifetime_gold >= 1e9, reward_amber=50, reward_medals=500),
    # Heritage collection meta-goal: 4 dojos + Earth = 5 heritages.
    Achievement("heritage_all", "Five Ways Master",
                "Collect all 5 heritages (4 Dojos + Earth).",
                lambda s: len(s.heritage) >= 5, reward_amber=100, reward_medals=1000),
    # Hidden / secret achievements (gp-permanent-scaling). The ``desc``
    # is shown only after unlock; before that, the ``hint`` (a cryptic
    # in-game teaser) is shown instead so the player has an in-game path
    # to the unlock that is NOT wiki-dependent. The ``check`` still fires
    # normally -- ``hidden`` controls the display only.
    Achievement("secret_voidwalker", "Voidwalker",
                "Fall in battle and rise again 10 times in a single run.",
                lambda s: getattr(s, "_deaths_this_run", 0) >= 10,
                reward_amber=15, reward_medals=150,
                hidden=True,
                hint="The road remembers those who walk it twice."),
    Achievement("secret_midnight", "Midnight Caller",
                "Catch 100 fireflies in total across all runs.",
                lambda s: getattr(s, "_fireflies_caught_total", 0) >= 100,
                reward_amber=10, reward_medals=100,
                hidden=True,
                hint="Light gathers where the night is longest."),
    Achievement("secret_untouchable", "Untouchable",
                "Reach zone 9 without taking a single hit.",
                lambda s: (s.best_zone >= 9
                           and getattr(s, "_hits_taken_this_run", 0) == 0),
                reward_amber=25, reward_medals=250,
                hidden=True,
                hint="The perfect blade is the one that is never drawn."),
]
