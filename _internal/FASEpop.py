from __future__ import annotations
import random
from typing import TYPE_CHECKING, Dict, List, Set, Tuple
from FASEcfg import *
from FASEclass import *

if TYPE_CHECKING:
    from FASE import Actor, Alignment, Deity, MonsterKind, Region, Role


class PopulationMixin:
    BIRTH_COOLDOWN_TICKS = 810  # 9 months at 90 ticks/month
    PREGNANCY_DURATION_TICKS = 810
    MAX_SOFT_CHILDREN_PER_COUPLE = 13
    
    def _random_person_identity(self) -> Tuple[str, str, str]:
        sex = self.rng.choice(["M", "F"])
        if sex == "M":
            first = self.rng.choice(MALE_FIRST_NAMES)
        else:
            first = self.rng.choice(FEMALE_FIRST_NAMES)
        return first, self.rng.choice(SURNAMES), sex

    def _random_person_name(self) -> Tuple[str, str]:
        first, surname, _sex = self._random_person_identity()
        return first, surname

    def _weighted_random_deity(self, alignment: "Alignment", region_id: int | None = None, parent_deities=None) -> "Deity":
        if alignment.moral_axis > 0:
            deities = [Deity.LORD_OF_LIGHT, Deity.GOD_OF_CHANCE, Deity.LORD_OF_DARKNESS]
            weights = [65, 25, 10]
        elif alignment.moral_axis < 0:
            deities = [Deity.LORD_OF_DARKNESS, Deity.GOD_OF_CHANCE, Deity.LORD_OF_LIGHT]
            weights = [65, 25, 10]
        else:
            deities = [Deity.GOD_OF_CHANCE, Deity.LORD_OF_LIGHT, Deity.LORD_OF_DARKNESS]
            weights = [45, 30, 25]

        if parent_deities:
            for deity in parent_deities:
                if deity in deities:
                    weights[deities.index(deity)] += 15

        if region_id is not None and hasattr(self, 'world') and getattr(self, 'world', None) is not None:
            world = self.world
            region = world.regions.get(region_id)
            if region is not None:
                ruler_id = getattr(region, 'ruler_id', None)
                polity_id = getattr(region, 'polity_id', None)
                favored = None
                if polity_id is not None and hasattr(world, 'polities') and polity_id in world.polities:
                    ruler = world.actors.get(world.polities[polity_id].ruler_id)
                    if ruler is not None and ruler.alive:
                        favored = ruler.deity
                if favored is None and ruler_id is not None and ruler_id in world.actors:
                    ruler = world.actors.get(ruler_id)
                    if ruler is not None and ruler.alive:
                        favored = ruler.deity
                if hasattr(world, "commoner_faith_by_region") and region_id in getattr(world, "commoner_faith_by_region", {}):
                    faith_map = world.commoner_faith_by_region.get(region_id, {})
                    if faith_map:
                        dominant_commoner = max(deities, key=lambda d: faith_map.get(d, 0))
                        weights[deities.index(dominant_commoner)] += 10
                if favored in deities:
                    weights[deities.index(favored)] += 140 if polity_id is not None else 70
        return self.rng.choices(deities, weights=weights, k=1)[0]

    def _roll_stats(self, role: "Role") -> Tuple[int, int, int, int, int, int, int]:
        stats = [self.rng.randint(6, 15) for _ in range(7)]

        if role == Role.FIGHTER:
            stats[0] += 2
            stats[2] += 1
        elif role == Role.WIZARD:
            stats[3] += 4
            stats[4] += 2
            stats[6] += 1
        elif role == Role.WARDEN:
            stats[1] += 2
            stats[4] += 1
        elif role == Role.BARD:
            stats[5] += 3
            stats[4] += 1
            stats[6] += 1

        return tuple(min(stat, 18) for stat in stats)

    def _base_hp(self, role: "Role", constitution: int) -> int:
        con_mod = max(-2, (constitution - 10) // 2)

        if role == Role.COMMONER:
            return max(3, 6 + con_mod)
        if role == Role.FIGHTER:
            return max(6, 12 + con_mod)
        if role == Role.WIZARD:
            return max(5, 9 + con_mod)
        if role == Role.BARD:
            return max(5, 8 + con_mod)
        return max(5, 10 + con_mod)

    def _generate_population(self, count: int, regions: Dict[int, "Region"]) -> Dict[int, "Actor"]:
        actors: Dict[int, Actor] = {}
        role_choices = [role for role, _ in ROLE_WEIGHTS]
        role_weights = [weight for _, weight in ROLE_WEIGHTS]

        current_year = 1

        for actor_id in range(1, count + 1):
            role = self.rng.choices(role_choices, weights=role_weights, k=1)[0]
            alignment = self.rng.choice(list(Alignment))
            deity = self._weighted_random_deity(alignment)
            stats = self._roll_stats(role)
            hp = self._base_hp(role, stats[2])
            region_id = self.rng.choice(list(regions.keys()))
            first, surname, sex = self._random_person_identity()
            traits = self.rng.sample(TRAITS, k=2)

            age = self._initial_age_for_role(role)
            birth_year = current_year - age

            actors[actor_id] = Actor(
                id=actor_id,
                name=first,
                surname=surname,
                role=role,
                alignment=alignment,
                deity=deity,
                strength=stats[0],
                dexterity=stats[1],
                constitution=stats[2],
                intelligence=stats[3],
                wisdom=stats[4],
                charisma=stats[5],
                luck=stats[6],
                hp=hp,
                max_hp=hp,
                region_id=region_id,
                traits=traits,
                birth_year=birth_year,
                birth_month=self.rng.randint(1, 12),
                birth_day=self.rng.randint(1, 30),
                spouse_id=None,
                sex=sex,
                mother_label="Unknown",
                father_label="Unknown",
            )
        self._seed_initial_households(actors)
        return actors

    def _observe_birthdays_and_commemorations(self) -> None:
        world = self.world
        _, month, day, _, _ = world.current_calendar()

        for actor in world.living_actors():
            if actor.birth_month == month and actor.birth_day == day:
                region = world.regions[actor.region_id]
                chance = 0.015 if actor.role == Role.COMMONER else 0.06 + min(0.12, actor.reputation * 0.01)

                if region.order >= 40:
                    chance += 0.03

                if self.rng.random() < chance:
                    if actor.reputation >= 12:
                        holiday_name = f"{actor.name}'s Day"
                        world.add_commemoration(
                            holiday_name,
                            month,
                            day,
                            f"Observed in honor of {actor.short_name()}.",
                            region_id=actor.region_id,
                            actor_id=actor.id,
                        )
                        world.log(
                            f"The people of {world.region_name(actor.region_id)} proclaim {holiday_name} in honor of {actor.short_name()}.",
                            importance=3,
                            category="commemoration",
                        )
                    else:
                        world.log(
                            f"A small gathering in {world.region_name(actor.region_id)} marks the birthday of {actor.short_name()}.",
                            importance=1,
                            category="birthday",
                        )

    def _eligible_commoner_singles_by_region(self) -> Dict[int, List["Actor"]]:
        buckets: Dict[int, List[Actor]] = {}
        for actor in self.world.living_actors():
            if actor.role != Role.COMMONER or actor.spouse_id is not None or self._calculate_age(actor) < 18:
                continue
            buckets.setdefault(actor.region_id, []).append(actor)
        return buckets

    def _pair_key(self, actor_a: "Actor", actor_b: "Actor") -> Tuple[int, int]:
        if actor_a.id <= actor_b.id:
            return (actor_a.id, actor_b.id)
        return (actor_b.id, actor_a.id)

    def _share_known_parent(self, actor_a: "Actor", actor_b: "Actor") -> bool:
        for field in ("mother_id", "father_id"):
            a_parent = getattr(actor_a, field, None)
            b_parent = getattr(actor_b, field, None)
            if a_parent is not None and a_parent == b_parent:
                return True
        return False

    def _is_parent_child_pair(self, actor_a: "Actor", actor_b: "Actor") -> bool:
        return (getattr(actor_a, "mother_id", None) == actor_b.id
                or getattr(actor_a, "father_id", None) == actor_b.id
                or getattr(actor_b, "mother_id", None) == actor_a.id
                or getattr(actor_b, "father_id", None) == actor_a.id)

    def _can_form_family_pair(self, actor_a: "Actor", actor_b: "Actor") -> bool:
        if actor_a.id == actor_b.id:
            return False
        if self._share_known_parent(actor_a, actor_b):
            return False
        if self._is_parent_child_pair(actor_a, actor_b):
            return False
        return True

    def _commoner_turn(self, actor: "Actor") -> None:
        world = self.world

        threats = [
            other
            for other in world.actors_in_region(actor.region_id)
            if other.alive and other.is_adventurer() and other.is_evil()
        ]
        monsters = [
            monster
            for monster in world.monsters_in_region(actor.region_id)
            if monster.kind in (
                MonsterKind.GOBLIN,
                MonsterKind.GIANT,
                MonsterKind.DRAGON,
                MonsterKind.ANCIENT_HORROR,
            )
        ]

        if threats or monsters:
            region = world.regions[actor.region_id]

            if region.neighbors:
                world.move_actor(actor, self.rng.choice(region.neighbors)) if hasattr(world, "move_actor") else setattr(actor, "region_id", self.rng.choice(region.neighbors))

            if self.rng.random() < 0.10:
                world.log(
                    f"Commoners flee {world.region_name(region.id)} after reports of oppression and monsters.",
                    importance=1,
                    category="flight",
                )

            world.adjust_region_state(region.id, control_delta=-1, order_delta=-1)
            return

        if self.rng.random() < 0.04:
            region = world.regions[actor.region_id]
            if region.neighbors:
                world.move_actor(actor, self.rng.choice(region.neighbors)) if hasattr(world, "move_actor") else setattr(actor, "region_id", self.rng.choice(region.neighbors))

    # =========================
    # --- v4 longevity system ---
    # =========================

    def _initial_age_for_role(self, role: "Role") -> int:
        if role == Role.COMMONER:
            roll = self.rng.random()
            if roll < 0.18:
                return self.rng.randint(0, 15)
            if roll < 0.80:
                return self.rng.randint(16, 45)
            if roll < 0.97:
                return self.rng.randint(46, 70)
            return self.rng.randint(71, 90)

        roll = self.rng.random()
        if roll < 0.15:
            return self.rng.randint(16, 24)
        if roll < 0.75:
            return self.rng.randint(25, 50)
        if roll < 0.96:
            return self.rng.randint(51, 75)
        return self.rng.randint(76, 95)

    def _calculate_age(self, actor: "Actor") -> int:
        year = getattr(self, "_current_year", None)
        if year is None:
            year, _, _, _, _ = self.world.current_calendar()
        return max(0, year - actor.birth_year)

    def _longevity_score(self, actor: "Actor") -> float:
        return (
            actor.constitution * 1.5 +
            actor.wisdom * 1.3 +
            actor.luck * 1.4 +
            actor.dexterity * 1.1 +
            actor.strength * 0.9 +
            actor.intelligence * 1.2 +
            actor.charisma * 0.8
        ) / 7.0

    def _biome_profile(self, region: "Region") -> dict:
        profiles = globals().get("BIOME_PROFILES", {}) or {}
        biome = str(getattr(region, "biome", "") or "")
        profile = profiles.get(biome) or profiles.get(biome.title()) or profiles.get(biome.replace("_", " ").title())
        return profile if isinstance(profile, dict) else {}


    def _biome_hardship(self, region: "Region") -> int:
        profile = self._biome_profile(region)
        try:
            return max(0, min(100, int(profile.get("hardship", 45))))
        except Exception:
            return 45


    def _environment_modifier(self, region: "Region") -> float:
        mod = 1.0
        mod *= (1.0 - (region.order - 50) * 0.002)
        mod *= (1.0 + abs(min(region.control, 0)) * 0.002)
        mod *= (1.0 + region.danger * 0.02)
        # Hardship is deliberately soft: a 15 hardship farmland is slightly safer,
        # a 95 hardship tundra/badland is noticeably harsher, but stats/age still dominate.
        hardship = self._biome_hardship(region)
        mod *= (0.90 + hardship / 200.0)
        return max(0.5, min(1.9, mod))

    def _age_curve(self, age: int) -> float:
        if age < 45:
            return 0.0002
        if age < 55:
            return 0.002
        if age < 65:
            return 0.009
        if age < 75:
            return 0.028
        if age < 85:
            return 0.07
        if age < 95:
            return 0.15
        if age < 105:
            return 0.28
        if age < 115:
            return 0.48
        return 0.72 + min(0.22, (age - 115) * 0.025)

    def _retirement_check(self, actor: "Actor") -> None:
        if not getattr(actor, "alive", True):
            return
        # Rulers rule until death, overthrow, or explicit succession. They do
        # not quietly retire out of the political layer.
        polity_id = getattr(actor, "polity_id", None)
        if polity_id is not None and hasattr(self.world, "polities"):
            polity = self.world.polities.get(polity_id)
            if polity is not None and getattr(polity, "ruler_id", None) == getattr(actor, "id", None):
                return
        if not getattr(actor, "can_retire", lambda: False)():
            return
        if getattr(actor, "retired", False):
            return
        age = self._calculate_age(actor)
        if age < actor.retirement_age():
            return
        actor.retired = True
        actor.retirement_year = self.world.current_calendar()[0]
        actor.party_id = None
        actor.loyalty = actor.id if actor.polity_id is not None else actor.loyalty
        if getattr(actor, "first_in_class_year", None) is not None:
            deity = getattr(actor, "first_in_class_deity", None) or getattr(actor, "deity", None)
            if hasattr(self, "_is_formal_school_deity") and not self._is_formal_school_deity(deity):
                deity = None
            school = self._school_for_deity(deity) if deity is not None and hasattr(self, "_school_for_deity") else None
            if school is not None and getattr(school, "region_id", None) in self.world.regions:
                self.world.move_actor(actor, school.region_id) if hasattr(self.world, "move_actor") else setattr(actor, "region_id", school.region_id)
                self.world.log(
                    f"{actor.short_name()} lays down the adventurer's life and returns to teach at the {getattr(deity, 'value', str(deity))} adventurer school in {self.world.region_name(actor.region_id)}.",
                    importance=3,
                    category="retirement",
                )
                return
        self.world.log(
            f"{actor.short_name()} lays down the adventurer's life and retires in {self.world.region_name(actor.region_id)}.",
            importance=2,
            category="retirement",
        )

    def _natural_death_check(self, actor: "Actor") -> None:
        age = self._calculate_age(actor)
        region = self.world.regions[actor.region_id]

        base = self._age_curve(age)
        stats = self._longevity_score(actor)
        env = self._environment_modifier(region)

        stat_mod = max(0.55, 1.45 - (stats - 10) * 0.03)
        death_chance = max(0.0, min(0.98, base * stat_mod * env))
        if actor.role != Role.WIZARD and age >= 110:
            death_chance = max(death_chance, 0.92)

        if self.rng.random() < death_chance:
            self._mark_actor_dead(actor, "old age", importance=2)

    def _school_teacher_score(self, teacher: "Actor", deity) -> int:
        if teacher is None or not getattr(teacher, "alive", False):
            return 0
        if not getattr(teacher, "retired", False):
            return 0
        if getattr(teacher, "deity", None) != deity:
            return 0
        score = 1
        profile = getattr(getattr(self, "world", None), "god_profiles", {}).get(deity)
        domains = set(getattr(profile, "domains", []) or [])
        favored_traits = set(getattr(profile, "favored_traits", []) or [])
        traits = set(getattr(teacher, "traits", []) or [])
        if traits.intersection(favored_traits):
            score += 1
        if domains.intersection({"knowledge", "protection", "order", "growth"}):
            score += 1
        if teacher.role in (Role.WARDEN, Role.FIGHTER):
            score += 1
        if teacher.role == Role.BARD and teacher.charisma >= 13:
            score += 1
        if teacher.role == Role.WIZARD and teacher.intelligence >= 13:
            score += 1
        if teacher.is_evil() and not domains.intersection({"domination", "war", "knowledge"}):
            score = max(0, score - 1)
        # First-in-class graduates who survive to retirement become unusually
        # valuable academy instructors. This turns the school system into an
        # institutional lineage instead of a one-off graduation bonus.
        if getattr(teacher, "first_in_class_year", None) is not None:
            score += int(globals().get("SCHOOL_FIRST_IN_CLASS_TEACHER_SCORE_BONUS", 2))
        return max(0, score)

    def _school_teacher_bonus(self, deity) -> int:
        cap = int(globals().get("SCHOOL_TEACHER_BONUS_CAP", 10))
        total = 0
        # Only retired actors of matching deity can contribute; skip all others early.
        for teacher in self.world.living_actors():
            if not getattr(teacher, "retired", False) or getattr(teacher, "deity", None) != deity:
                continue
            total += self._school_teacher_score(teacher, deity)
            if total >= cap:
                return cap
        return max(0, min(cap, total))

    def _school_deity_abbrev(self, deity) -> str:
        value = str(getattr(deity, "value", getattr(deity, "name", deity)) or "")
        custom = globals().get("SCHOOL_DEITY_ABBREVIATIONS", {}) or {}
        if value in custom:
            return str(custom[value])
        upper_words = [word[0].upper() for word in value.replace("_", " ").split() if word]
        if upper_words:
            return "".join(upper_words)[:6]
        return "UNK"

    def _is_first_in_class_title(self, title: object) -> bool:
        return str(title or "").startswith("First in Class of ")

    def _graduate_from_school(self, actor: "Actor", new_role: "Role", *, cohort_rank: int | None = None, cohort_count: int | None = None, first_in_class: bool = False) -> None:
        deity = getattr(actor, "school_deity", None) or getattr(actor, "deity", None)
        if cohort_rank is None or cohort_count is None:
            ranked_students = self._update_school_class_ranks(deity) if hasattr(self, "_update_school_class_ranks") else []
            pre_grad_rank = int(getattr(actor, "school_class_rank", 0) or 0)
            pre_grad_count = len(ranked_students)
            first_in_class = pre_grad_rank == 1 and pre_grad_count > 1
        else:
            pre_grad_rank = int(cohort_rank or 0)
            pre_grad_count = int(cohort_count or 0)
            first_in_class = bool(first_in_class)
        teacher_bonus = self._school_teacher_bonus(deity)
        prestige_bonus = self._school_prestige_bonus(deity) if hasattr(self, "_school_prestige_bonus") else 0
        actor.school_teacher_bonus = teacher_bonus
        actor.in_school = False
        # Children are protected while in school, but graduate back into the world.
        if actor.region_id not in self.world.regions:
            self.world.move_actor(actor, self.rng.choice(list(self.world.regions.keys()))) if hasattr(self.world, "move_actor") else setattr(actor, "region_id", self.rng.choice(list(self.world.regions.keys())))
        # Prefer returning near a living parent; otherwise pick a safe-ish region.
        parents = [
            self.world.actors.get(getattr(actor, "mother_id", None)),
            self.world.actors.get(getattr(actor, "father_id", None)),
        ]
        living_parents = [p for p in parents if p is not None and p.alive and p.region_id in self.world.regions]
        if living_parents:
            self.world.move_actor(actor, self.rng.choice(living_parents).region_id) if hasattr(self.world, "move_actor") else setattr(actor, "region_id", self.rng.choice(living_parents).region_id)
        else:
            _target_region = max(self.world.regions, key=lambda rid: (self.world.regions[rid].order, self.world.regions[rid].control, self.rng.random()))
            self.world.move_actor(actor, _target_region) if hasattr(self.world, "move_actor") else setattr(actor, "region_id", _target_region)
        total_school_bonus = max(0, teacher_bonus + prestige_bonus)
        if total_school_bonus > 0:
            actor.experience = (
                max(0, getattr(actor, "experience", 0))
                + int(globals().get("SCHOOL_BASE_XP_BONUS", 10))
                + teacher_bonus * int(globals().get("SCHOOL_XP_PER_TEACHER_BONUS", 12))
                + prestige_bonus * int(globals().get("SCHOOL_XP_PER_PRESTIGE_YEAR", 2))
            )
            chance = min(
                0.75,
                teacher_bonus * float(globals().get("SCHOOL_STAT_BONUS_CHANCE_PER_TEACHER_BONUS", 0.03))
                + prestige_bonus * float(globals().get("SCHOOL_STAT_BONUS_CHANCE_PER_PRESTIGE_YEAR", 0.004)),
            )
            for stat in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma", "luck"):
                if self.rng.random() < chance:
                    setattr(actor, stat, int(getattr(actor, stat, 0)) + 1)
        if first_in_class:
            actor.experience = max(0, getattr(actor, "experience", 0)) + int(globals().get("SCHOOL_FIRST_IN_CLASS_XP_BONUS", 75))
            year = self.world.current_calendar()[0]
            actor.first_in_class_year = year
            actor.first_in_class_deity = deity
            actor.first_in_class_deity_abbrev = self._school_deity_abbrev(deity)
            if not getattr(actor, "title", None) or self._is_first_in_class_title(getattr(actor, "title", None)):
                actor.title = f"First in Class of {year} ({actor.first_in_class_deity_abbrev})"
        self._promote_commoner_to_role(actor, new_role)
        if teacher_bonus > 0 and hasattr(actor, "sync_progression"):
            actor.sync_progression(reset_base=True)
        rank_text = ""
        if pre_grad_rank > 0:
            rank_text = f" Rank: {pre_grad_rank}/{pre_grad_count} in combat training."
        if first_in_class:
            rank_text += " First in class."
        self.world.log(
            f"{actor.short_name()} graduates from the {getattr(deity, 'value', str(deity))} adventurer school with teacher strength {teacher_bonus} and prestige {prestige_bonus}.{rank_text}",
            importance=2 if pre_grad_rank != 1 else 3,
            category="adventurer_school",
        )
        if hasattr(self, "_update_school_class_ranks"):
            self._update_school_class_ranks(deity)

    def _adventurer_parent_count(self, actor: "Actor") -> int:
        mother = self.world.actors.get(getattr(actor, "mother_id", None))
        father = self.world.actors.get(getattr(actor, "father_id", None))
        count = 0
        if mother is not None and mother.is_adventurer():
            count += 1
        if father is not None and father.is_adventurer():
            count += 1
        return count

    def _annual_school_graduation_tick(self) -> None:
        year, month, day, _tod, _season = self.world.current_calendar()
        goldfire_month = 5
        if month != goldfire_month or day != 1:
            return
        if int(getattr(self.world, "_last_school_graduation_year", -1) or -1) == int(year):
            return
        self.world._last_school_graduation_year = int(year)

        schools = getattr(self.world, "adventurer_schools", {}) or {}
        if schools:
            deities = list(schools.keys())
        else:
            deities = sorted(
                {getattr(a, "school_deity", None) or getattr(a, "deity", None) for a in self.world.living_actors() if getattr(a, "in_school", False)},
                key=lambda d: str(getattr(d, "value", getattr(d, "name", d))),
            )

        for deity in deities:
            if deity is None:
                continue
            ranked = self._update_school_class_ranks(deity) if hasattr(self, "_update_school_class_ranks") else []
            cohort = [a for a in ranked if getattr(a, "alive", False) and getattr(a, "in_school", False) and self._calculate_age(a) >= 16]
            if not cohort:
                continue
            cohort_count = len(cohort)
            cohort_ids = {a.id for a in cohort}
            first_id = cohort[0].id if cohort_count > 1 else None
            self.world.log(
                f"Goldfire commencement begins at the {getattr(deity, 'value', str(deity))} adventurer school; {cohort_count} students stand for graduation.",
                importance=2,
                category="adventurer_school",
            )
            for actor in list(cohort):
                # Rank is fixed once for the graduating cohort, preventing rolling
                # first-in-class churn as earlier graduates leave the school list.
                cohort_rank = 1 + sum(1 for other in cohort if int(getattr(other, "school_class_rank", 999999)) < int(getattr(actor, "school_class_rank", 999999)))
                new_role = self._roll_new_adventurer_role(actor)
                self._graduate_from_school(
                    actor,
                    new_role,
                    cohort_rank=cohort_rank,
                    cohort_count=cohort_count,
                    first_in_class=(actor.id == first_id),
                )
            if hasattr(self, "_update_school_class_ranks"):
                self._update_school_class_ranks(deity)

    def _coming_of_age_check(self, actor: "Actor") -> None:
        if actor.role != Role.COMMONER:
            return

        age = self._calculate_age(actor)
        if age != 16:
            return

        region = self.world.regions[actor.region_id]

        chance = 0.2
        if actor.strength >= 13 or actor.constitution >= 13:
            chance += 0.01
        if actor.dexterity >= 13 or actor.wisdom >= 13:
            chance += 0.01
        if actor.intelligence >= 14 or actor.luck >= 14:
            chance += 0.01

        if region.order >= 70:
            chance += 0.005
        if region.control >= 50:
            chance += 0.005
        if region.control <= -20:
            chance -= 0.01
        adventurer_parent_count = self._adventurer_parent_count(actor)

        # Adventurer children are not lottery tickets. They come from an adventuring
        # household and enter the adventurer pool automatically at 16.
        if adventurer_parent_count > 0:
            if getattr(actor, "in_school", False):
                # School children now graduate as annual cohorts on Goldfire 1.
                # If they turn 16 after that date, they wait until the next year's ceremony.
                return
            new_role = self._roll_new_adventurer_role(actor)
            self._promote_commoner_to_role(actor, new_role)
            return

        # Commoner promotions now act as recovery pressure instead of endless
        # background adventurer inflation. If the adventurer pool is healthy,
        # commoner children stay commoners.
        recovery_state = self._recovery_state() if hasattr(self, "_recovery_state") else "normal"
        if recovery_state == "normal":
            return
        if recovery_state == "crisis":
            chance += 0.10
        elif recovery_state == "low":
            chance += 0.04

        chance = max(0.01, min(0.99, chance))

        if self.rng.random() >= chance:
            return

        new_role = self._roll_new_adventurer_role(actor)
        self._promote_commoner_to_role(actor, new_role)

    def _roll_new_adventurer_role(self, actor: "Actor") -> "Role":
        wizard_weight = WIZARD_PROMOTION_CHANCE
        bard_weight = WIZARD_PROMOTION_CHANCE
        fighter_weight = 0.58
        warden_weight = max(0.10, 1.0 - fighter_weight - wizard_weight - bard_weight)

        if actor.intelligence >= 14 or actor.wisdom >= 14:
            wizard_weight += 0.01
        if actor.charisma >= 14 or actor.wisdom >= 14:
            bard_weight += 0.01
        if actor.luck >= 15:
            wizard_weight += 0.005
            bard_weight += 0.005

        if actor.dexterity >= actor.strength:
            warden_weight += 0.04
        else:
            fighter_weight += 0.04
        if actor.charisma >= max(actor.strength, actor.dexterity):
            bard_weight += 0.03

        total = fighter_weight + warden_weight + wizard_weight + bard_weight
        roll = self.rng.random() * total

        if roll < fighter_weight:
            return Role.FIGHTER
        if roll < fighter_weight + warden_weight:
            return Role.WARDEN
        if roll < fighter_weight + warden_weight + wizard_weight:
            return Role.WIZARD
        return Role.BARD

    def _promote_commoner_to_role(self, actor: "Actor", new_role: "Role") -> None:
        actor.role = new_role
        if getattr(actor, "mother_id", None) is None and not getattr(actor, "mother_label", None):
            actor.mother_label = "Commoner"
        if getattr(actor, "father_id", None) is None and not getattr(actor, "father_label", None):
            actor.father_label = "Commoner"

        stats = self._roll_stats(new_role)
        actor.strength = stats[0]
        actor.dexterity = stats[1]
        actor.constitution = stats[2]
        actor.intelligence = stats[3]
        actor.wisdom = stats[4]
        actor.charisma = stats[5]
        actor.luck = stats[6]

        actor.max_hp = self._base_hp(new_role, actor.constitution)
        actor.hp = max(actor.hp, actor.max_hp)
        if hasattr(actor, 'sync_progression'):
            actor.sync_progression(reset_base=True)

        self.world.generated_by_role[new_role] += 1

        self.world.log(
            f"{actor.short_name()} comes of age in {self.world.region_name(actor.region_id)} and takes up the life of a {new_role.value.lower()}.",
            importance=2,
            category="coming_of_age",
        )


    # =========================
    # --- v4 population tick ---
    # =========================

    def _population_tick(self) -> None:
        world = self.world
        _, month, day, _, _ = world.current_calendar()

        self._annual_school_graduation_tick()

        for actor in list(world.living_actors()):
            if actor.birth_month == month and actor.birth_day == day:
                self._coming_of_age_check(actor)
                self._retirement_check(actor)
                self._natural_death_check(actor)

        for actor in list(world.living_actors()):
            age = self._calculate_age(actor)
            if age < 5:
                region = world.regions[actor.region_id]

                infant_risk = 0.0015

                if region.order <= 35:
                    infant_risk += 0.003
                elif region.order >= 85:
                    infant_risk -= 0.001
                elif region.order >= 70:
                    infant_risk -= 0.0007

                if region.control <= -20:
                    infant_risk += 0.002
                elif region.control >= 80:
                    infant_risk -= 0.001
                elif region.control >= 50:
                    infant_risk -= 0.0007

                infant_risk += region.danger * 0.0005

                infant_risk -= max(0, actor.constitution - 10) * 0.0002
                infant_risk -= max(0, actor.luck - 10) * 0.0002

                adv_parent_count = self._adventurer_parent_count(actor) if hasattr(self, "_adventurer_parent_count") else 0
                if adv_parent_count == 1:
                    infant_risk *= 0.65
                elif adv_parent_count >= 2:
                    infant_risk *= 0.45

                infant_risk = max(0.0, min(0.015, infant_risk))

                if self.rng.random() < infant_risk:
                    self._mark_actor_dead(actor, "childhood illness", importance=1)

        self._cleanup_spouses()
        self._handle_pairing()
        self._handle_births()

    def _cleanup_spouses(self) -> None:
        for actor in self.world.living_actors():
            if actor.spouse_id is None:
                continue
            spouse = self.world.actors.get(actor.spouse_id)
            if spouse is None or not spouse.alive:
                actor.spouse_id = None

    def _seed_initial_households(self, actors: Dict[int, "Actor"]) -> None:
        by_region: Dict[int, List[Actor]] = {}
        for actor in actors.values():
            if actor.role == Role.COMMONER and actor.spouse_id is None and self._calculate_age_static(actor, current_year=1) >= 18:
                by_region.setdefault(actor.region_id, []).append(actor)

        for region_id, people in by_region.items():
            self.rng.shuffle(people)
            pair_count = int(len(people) * 0.25)
            i = 0
            made = 0
            while i + 1 < len(people) and made < pair_count:
                a = people[i]
                b = people[i + 1]
                if a.spouse_id is None and b.spouse_id is None and getattr(a, "sex", None) != getattr(b, "sex", None) and self._can_form_family_pair(a, b):
                    a.spouse_id = b.id
                    b.spouse_id = a.id
                    made += 1
                i += 2

    def _calculate_age_static(self, actor: "Actor", current_year: int) -> int:
        return max(0, current_year - actor.birth_year)

    def _handle_pairing(self) -> None:
        world = self.world

        candidates = [
            a for a in world.living_actors()
            if a.role == Role.COMMONER
            and a.spouse_id is None
            and self._calculate_age(a) >= 18
        ]

        self.rng.shuffle(candidates)

        for actor in candidates:
            if actor.spouse_id is not None:
                continue

            locals_ = [
                other for other in world.actors_in_region(actor.region_id)
                if other.id != actor.id
                and other.role == Role.COMMONER
                and other.spouse_id is None
                and self._calculate_age(other) >= 18
                and getattr(other, "sex", None) != getattr(actor, "sex", None)
                and self._can_form_family_pair(actor, other)
            ]

            if not locals_:
                continue
                
            region = world.regions[actor.region_id]
            chance = 0.002
            if region.order >= 55:
                chance += 0.0015
            if region.control >= 20:
                chance += 0.001
            if region.control <= -20:
                chance -= 0.0015
            if region.order <= 35:
                chance -= 0.001

            if self.rng.random() < max(0.001, chance):
                partner = self.rng.choice(locals_)
                actor.spouse_id = partner.id
                partner.spouse_id = actor.id

    def _living_children_of_pair(self, parent_a: "Actor", parent_b: "Actor") -> int:
        return self.world.pair_children_count.get(self._pair_key(parent_a, parent_b), 0)

    def _pair_last_birth_tick(self, parent_a: "Actor", parent_b: "Actor") -> int:
        a_tick = getattr(parent_a, "last_birth_tick", -999999)
        b_tick = getattr(parent_b, "last_birth_tick", -999999)
        return max(a_tick, b_tick)
    
    def _handle_births(self) -> None:
        world = self.world

        for actor in list(world.living_actors()):
            if actor.spouse_id is None:
                continue
            if actor.role != Role.COMMONER:
                continue

            spouse = world.actors.get(actor.spouse_id)
            if spouse is None or not spouse.alive or spouse.role != Role.COMMONER:
                continue

            age_a = self._calculate_age(actor)
            age_b = self._calculate_age(spouse)
            if age_a < 18 or age_b < 18:
                continue
            if actor.sex == spouse.sex:
                continue
            female = actor if getattr(actor, "sex", "F") == "F" else spouse
            male = spouse if female is actor else actor
            female_age = self._calculate_age(female)
            male_age = self._calculate_age(male)
            if female_age > 39 or male_age > 60:
                continue
            if getattr(female, "pregnant_until_tick", -1) > self.world.tick:
                continue

            if actor.id > spouse.id:
                continue

            children = self._living_children_of_pair(actor, spouse)
            last_birth_tick = self._pair_last_birth_tick(actor, spouse)

            if self.world.tick - last_birth_tick < self.BIRTH_COOLDOWN_TICKS:
                continue

            chance = self._birth_chance_for_pair(actor, spouse)

            if children >= self.MAX_SOFT_CHILDREN_PER_COUPLE:
                chance *= 0.35
            if children >= self.MAX_SOFT_CHILDREN_PER_COUPLE + 1:
                chance *= 0.15
            if children >= self.MAX_SOFT_CHILDREN_PER_COUPLE + 2:
                chance = 0.0

            if self.rng.random() < chance:
                self._create_child(actor, spouse)
                actor.last_birth_tick = self.world.tick
                spouse.last_birth_tick = self.world.tick

    def _birth_chance_for_pair(self, parent_a: "Actor", parent_b: "Actor") -> float:
        region = self.world.regions[parent_a.region_id]

        chance = 0.003

        if region.order >= 60:
            chance += 0.002
        if region.order <= 35:
            chance -= 0.0015

        if region.control >= 20:
            chance += 0.001
        if region.control <= -20:
            chance -= 0.0015

        chance -= region.danger * 0.0005

        hardship = self._biome_hardship(region)
        # Easier settlement biomes nudge families upward; harsh frontiers nudge them down.
        chance += (50 - hardship) * 0.000025

        avg_luck = (parent_a.luck + parent_b.luck) / 2.0
        chance += (avg_luck - 10) * 0.0003

        
        population = getattr(self.world, "commoners_by_region", {}).get(parent_a.region_id, 0)
        capacity = max(1, getattr(region, "base_capacity", 1))
        pressure = population / capacity
        chance *= (0.4 + (region.order / 100.0))
        chance *= max(0.55, min(1.25, 1.15 - (hardship / 250.0)))
        if pressure > 1.0:
            chance *= max(0.05, 1.5 - pressure)

        return max(0.00005, min(0.008, chance))

    def _create_child(self, parent_a: "Actor", parent_b: "Actor") -> None:
        world = self.world
        new_id = world.next_actor_id
        world.next_actor_id += 1

        alignment = self.rng.choice([parent_a.alignment, parent_b.alignment, self.rng.choice(list(Alignment))])
        deity = self._weighted_random_deity(alignment, region_id=parent_a.region_id, parent_deities=[parent_a.deity, parent_b.deity])

        stats = self._inherit_stats(parent_a, parent_b)
        hp = self._base_hp(Role.COMMONER, stats[2])

        mother = parent_a if getattr(parent_a, "sex", "F") == "F" else parent_b
        father = parent_b if mother is parent_a else parent_a
        child_name, _child_surname_rand, child_sex = self._random_person_identity()

        child = Actor(
            id=new_id,
            name=child_name,
            surname=(father.surname if child_sex == "M" else mother.surname),
            role=Role.COMMONER,
            alignment=alignment,
            deity=deity,
            strength=stats[0],
            dexterity=stats[1],
            constitution=stats[2],
            intelligence=stats[3],
            wisdom=stats[4],
            charisma=stats[5],
            luck=stats[6],
            hp=hp,
            max_hp=hp,
            region_id=parent_a.region_id,
            traits=self.rng.sample(TRAITS, 2),
            birth_year=self.world.current_calendar()[0],
            birth_month=self.rng.randint(1, 12),
            birth_day=self.rng.randint(1, 30),
            spouse_id=None,
            sex=child_sex,
            mother_id=mother.id,
            father_id=father.id,
            mother_label=None,
            father_label=None,
            last_birth_tick=-999999,
            pregnant_until_tick=-1,
            pregnancy_partner_id=None,
        )

        if hasattr(world, "register_actor"):
            world.register_actor(child)
        else:
            world.actors[new_id] = child
        world.generated_by_role[Role.COMMONER] += 1
        world.commoner_births += 1
        pair_key = self._pair_key(parent_a, parent_b)
        world.pair_children_count[pair_key] = world.pair_children_count.get(pair_key, 0) + 1
        if hasattr(mother, "children_ids"):
            mother.children_ids.append(new_id)
        if hasattr(father, "children_ids"):
            father.children_ids.append(new_id)

    def _inherit_stats(self, a: "Actor", b: "Actor") -> Tuple[int, ...]:
        stats = []
        for stat in [
            "strength", "dexterity", "constitution",
            "intelligence", "wisdom", "charisma", "luck"
        ]:
            avg = (getattr(a, stat) + getattr(b, stat)) / 2
            rolled = int(round(avg + self.rng.randint(-2, 2)))
            stats.append(max(3, min(18, rolled)))
        return tuple(stats)


# injected globals
MALE_FIRST_NAMES: List[str]
FEMALE_FIRST_NAMES: List[str]
SURNAMES: List[str]
TRAITS: List[str]
ROLE_WEIGHTS: List[Tuple["Role", int]]
WIZARD_PROMOTION_CHANCE: float

Alignment: type
Role: type
Deity: type
MonsterKind: type
Actor: type
