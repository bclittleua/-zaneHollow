from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Tuple
from FASEcfg import *
from FASEclass import *

if TYPE_CHECKING:
    from fantfarm_v130 import Actor, Alignment, Deity, Role


class LegacyMixin:
    """
    Adventurer lineage / dynasty layer.

    This module is intentionally conservative:
    - adventurers can pair
    - adventurers can have children
    - children are born as COMMONER by default
    - parentage is tracked for future dynasty / succession systems

    It is designed to be mixed in alongside PopulationMixin.
    It expects the simulator to already provide:
        - self.world
        - self.rng
        - self._calculate_age(actor)
        - self._weighted_random_deity(alignment)
        - self._base_hp(role, constitution)
        - self._inherit_stats(parent_a, parent_b)
    """

    ADVENTURER_BIRTH_COOLDOWN_TICKS = 810  # 9 months at 90 ticks/month
    PREGNANCY_DURATION_TICKS = 810
    MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR = 6

    def _legacy_tick(self) -> None:
        self._cleanup_adventurer_spouses()
        self._handle_adventurer_pairing()
        self._handle_adventurer_births()
        self._update_ruling_houses()

    def _cleanup_adventurer_spouses(self) -> None:
        for actor in self.world.living_actors():
            if not actor.is_adventurer():
                continue
            if actor.spouse_id is None:
                continue
            spouse = self.world.actors.get(actor.spouse_id)
            if spouse is None or not spouse.alive:
                actor.spouse_id = None
                continue
            # Spouses should normally become each other's closest bond unless
            # an existing living best friend already occupies that slot.
            if getattr(actor, "best_friend_id", None) is None:
                actor.best_friend_id = spouse.id
            if getattr(spouse, "best_friend_id", None) is None:
                spouse.best_friend_id = actor.id

    def _eligible_adventurer_singles_by_region(self) -> Dict[int, List["Actor"]]:
        buckets: Dict[int, List[Actor]] = {}
        for actor in self.world.living_actors():
            if not actor.is_adventurer() or actor.spouse_id is not None or self._calculate_age(actor) < 18:
                continue
            buckets.setdefault(actor.region_id, []).append(actor)
        return buckets

    def _handle_adventurer_pairing(self) -> None:
        world = self.world

        candidates = [
            a for a in world.living_actors()
            if a.is_adventurer()
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
                and other.alive
                and other.is_adventurer()
                and other.spouse_id is None
                and self._calculate_age(other) >= 18
                and self._can_form_legacy_pair(actor, other)
            ]

            if not locals_:
                continue

            mutual_bff = [
                other for other in locals_
                if getattr(actor, 'best_friend_id', None) == other.id
                and getattr(other, 'best_friend_id', None) == actor.id
                and getattr(actor, 'sex', None) != getattr(other, 'sex', None)
            ]
            if mutual_bff:
                partner = max(mutual_bff, key=lambda other: (actor.ideology_similarity(other), -abs(actor.power_rating() - other.power_rating()), self.rng.random()))
                actor.spouse_id = partner.id
                partner.spouse_id = actor.id
                actor.best_friend_id = partner.id
                partner.best_friend_id = actor.id
                world.log(
                    f"{actor.short_name()} and {partner.short_name()} bind their fates in {world.region_name(actor.region_id)} after proving inseparable companions.",
                    importance=2,
                    category="legacy_pairing",
                )
                continue

            region = world.regions[actor.region_id]
            chance = 0.0015

            if region.order >= 55:
                chance += 0.001
            if region.control >= 20:
                chance += 0.001
            if region.control <= -20:
                chance -= 0.001

            if actor.party_id is not None:
                chance += 0.0005

            if self.rng.random() < max(0.0005, chance):
                partner = self.rng.choice(locals_)
                actor.spouse_id = partner.id
                partner.spouse_id = actor.id
                if getattr(actor, "best_friend_id", None) is None:
                    actor.best_friend_id = partner.id
                if getattr(partner, "best_friend_id", None) is None:
                    partner.best_friend_id = actor.id
                world.log(
                    f"{actor.short_name()} and {partner.short_name()} bind their fates in {world.region_name(actor.region_id)}.",
                    importance=2,
                    category="legacy_pairing",
                )

    def _share_known_parent(self, actor: "Actor", other: "Actor") -> bool:
        for field in ("mother_id", "father_id"):
            a_parent = getattr(actor, field, None)
            b_parent = getattr(other, field, None)
            if a_parent is not None and a_parent == b_parent:
                return True
        return False

    def _is_parent_child_pair(self, actor: "Actor", other: "Actor") -> bool:
        return (getattr(actor, "mother_id", None) == other.id
                or getattr(actor, "father_id", None) == other.id
                or getattr(other, "mother_id", None) == actor.id
                or getattr(other, "father_id", None) == actor.id)

    def _can_form_legacy_pair(self, actor: "Actor", other: "Actor") -> bool:
        if actor.id == other.id:
            return False
        if not actor.alive or not other.alive:
            return False
        if not actor.is_adventurer() or not other.is_adventurer():
            return False
        # Keep adventurer pairings in a plausible age band. This blocks cases
        # like a century-old bard marrying a thirty-something adventurer.
        if abs(self._calculate_age(actor) - self._calculate_age(other)) > 20:
            return False
        if self._share_known_parent(actor, other):
            return False
        if self._is_parent_child_pair(actor, other):
            return False

        actor_law, actor_moral = actor.ideology()
        other_law, other_moral = other.ideology()
        law_gap = abs(actor_law - other_law)
        moral_gap = abs(actor_moral - other_moral)

        if getattr(actor, "sex", None) == getattr(other, "sex", None):
            return False
        return law_gap <= 2 and moral_gap <= 1

    def _handle_adventurer_births(self) -> None:
        world = self.world

        for actor in list(world.living_actors()):
            if not actor.is_adventurer():
                continue
            if actor.spouse_id is None:
                continue

            spouse = world.actors.get(actor.spouse_id)
            if spouse is None or not spouse.alive or not spouse.is_adventurer():
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

            if self.world.tick - last_birth_tick < self.ADVENTURER_BIRTH_COOLDOWN_TICKS:
                continue

            chance = self._adventurer_birth_chance_for_pair(actor, spouse)

            if children >= self.MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR:
                chance *= 0.35
            if children >= self.MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR + 1:
                chance *= 0.10
            if children >= self.MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR + 2:
                chance = 0.0

            if self.rng.random() < chance:
                child = self._create_adventurer_child(actor, spouse)
                actor.last_birth_tick = self.world.tick
                spouse.last_birth_tick = self.world.tick
                world.log(
                    f"A child is born to {actor.short_name()} and {spouse.short_name()} and sent to the {getattr(child.deity, 'value', str(child.deity))} adventurer school.",
                    importance=2,
                    category="legacy_birth",
                )

    def _adventurer_birth_chance_for_pair(self, parent_a: "Actor", parent_b: "Actor") -> float:
        region = self.world.regions[parent_a.region_id]

        chance = 0.0015

        if region.order >= 60:
            chance += 0.0015
        if region.control >= 20:
            chance += 0.001
        if region.control <= -20:
            chance -= 0.001

        chance -= region.danger * 0.0003

        avg_luck = (parent_a.luck + parent_b.luck) / 2.0
        avg_rep = (parent_a.reputation + parent_b.reputation) / 2.0

        chance += (avg_luck - 10) * 0.00015
        chance += min(0.001, avg_rep * 0.00002)

        if getattr(parent_a, 'best_friend_id', None) == parent_b.id and getattr(parent_b, 'best_friend_id', None) == parent_a.id:
            chance += 0.0025

        return max(0.0002, min(0.012, chance))

    def _create_adventurer_child(self, parent_a: "Actor", parent_b: "Actor") -> "Actor":
        world = self.world
        new_id = world.next_actor_id
        world.next_actor_id += 1

        alignment = self._inherit_alignment(parent_a, parent_b)
        deity = self._inherit_deity(parent_a, parent_b, alignment)

        stats = self._inherit_stats(parent_a, parent_b)
        hp = self._base_hp(Role.COMMONER, stats[2])

        mother = parent_a if getattr(parent_a, "sex", "F") == "F" else parent_b
        father = parent_b if mother is parent_a else parent_a
        child_name, _child_surname_rand, child_sex = self._random_person_identity()
        surname = father.surname if child_sex == "M" else mother.surname

        child = Actor(
            id=new_id,
            name=child_name,
            surname=surname,
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
            region_id=getattr(self._school_for_deity(deity), "region_id", parent_a.region_id) if hasattr(self, "_school_for_deity") else parent_a.region_id,
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
            in_school=False,
            school_deity=deity,
            school_region_id=None,
            school_started_tick=self.world.tick,
            school_teacher_bonus=0,
        )

        if hasattr(world, "register_actor"):
            world.register_actor(child)
        else:
            world.actors[new_id] = child
        if hasattr(self, "_try_enroll_school_child"):
            self._try_enroll_school_child(child, deity, reason="legacy_birth")
        world.generated_by_role[Role.COMMONER] += 1
        world.adventurer_lineage_births += 1
        pair_key = self._pair_key(parent_a, parent_b)
        world.pair_children_count[pair_key] = world.pair_children_count.get(pair_key, 0) + 1
        if hasattr(mother, "children_ids"):
            mother.children_ids.append(new_id)
        if hasattr(father, "children_ids"):
            father.children_ids.append(new_id)
        return child

    def _inherit_alignment(self, parent_a: "Actor", parent_b: "Actor") -> "Alignment":
        if self.rng.random() < 0.40:
            return parent_a.alignment
        if self.rng.random() < 0.80:
            return parent_b.alignment
        return self.rng.choice([parent_a.alignment, parent_b.alignment, self.rng.choice(list(Alignment))])

    def _inherit_deity(self, parent_a: "Actor", parent_b: "Actor", alignment: "Alignment") -> "Deity":
        if parent_a.deity == parent_b.deity and self.rng.random() < 0.75:
            return parent_a.deity
        if self.rng.random() < 0.40:
            return self.rng.choice([parent_a.deity, parent_b.deity])
        return self._weighted_random_deity(alignment, region_id=parent_a.region_id, parent_deities=[parent_a.deity, parent_b.deity])

    def _living_children_of_pair(self, parent_a: "Actor", parent_b: "Actor") -> int:
        return self.world.pair_children_count.get(self._pair_key(parent_a, parent_b), 0)

    def _pair_last_birth_tick(self, parent_a: "Actor", parent_b: "Actor") -> int:
        a_tick = getattr(parent_a, "last_birth_tick", -999999)
        b_tick = getattr(parent_b, "last_birth_tick", -999999)
        return max(a_tick, b_tick)

    def _update_ruling_houses(self) -> None:
        """
        Placeholder hook for dynasty / kingdom logic.

        Intended future behavior:
        - identify stable ruling bloodlines
        - prefer succession by child / lineage before free-for-all rulership
        - found houses / dynasties for notable rulers
        """
        return


# injected globals
FIRST_NAMES: List[str]
TRAITS: List[str]

MALE_FIRST_NAMES: List[str]
FEMALE_FIRST_NAMES: List[str]
TRAITS: List[str]

Alignment: type
Role: type
Deity: type
Actor: type
