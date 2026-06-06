from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, List
from FASEcfg import *
from FASEclass import *

try:
    from FASErg import BOON_DEFS, TIER_DEFS
except Exception:
    BOON_DEFS = {
        "might": {"stat": "strength", "label": "Might"},
        "grace": {"stat": "dexterity", "label": "Grace"},
        "endurance": {"stat": "constitution", "label": "Endurance"},
        "insight": {"stat": "wisdom", "label": "Insight"},
        "fortune": {"stat": "luck", "label": "Fortune"},
        "resolve": {"stat": "charisma", "label": "Resolve"},
    }
    TIER_DEFS = {"lesser": {"boon_amount": 2}, "greater": {"boon_amount": 4}}

# tuple: name, power_bonus, reputation_bonus, difficulty, steps_required, control_bonus, trouble_beacon, description
RELIC_SPECS = [
    ("Excalibur", 6, 10, 2, 4, 3, 1, "A blade that makes rulers and rebels alike larger than life."),
    ("The Black Blade", 6, 8, 2, 4, -3, 2, "A cursed edge that exalts any killer who holds it."),
    ("The Spear of Destiny", 5, 10, 3, 5, 4, 2, "A weapon said to bend the course of wars."),
    ("The Phoenix Crown", 5, 9, 3, 5, 5, 2, "An ancient diadem that draws followers and ambition."),
    ("The Holy Grail", 4, 12, 5, 6, 6, 2, "A vessel of renewal that steadies the hand that bears it."),
    ("The One Ring", 7, 14, 6, 7, 10, 5, "Power condensed into a whispering circle of gold."),
]

RING_DESTROY_MIN_POWER = 85
RING_DESTROY_MIN_REPUTATION = 120
RING_DESTROY_ORDER_BONUS = 15
RING_REPUTATION_TICK = 1
RING_PRESSURE_INTERVAL = TICKS_PER_TENDAY
RELIC_RELEASE_YEAR = 7
MAX_ACTIVE_RELIC_QUESTS = 2
RELIC_RELEASE_CHECK_INTERVAL = TICKS_PER_MONTH
RELIC_STEP_COOLDOWN_MIN = TICKS_PER_MONTH
RELIC_STEP_COOLDOWN_MAX = TICKS_PER_TENDAY * 8
RELIC_ACTION_BASE_CHANCE = 0.05
RELIC_ACTION_MAX_CHANCE = 0.35
CREATED_RELIC_RECLAIM_CHANCE = 0.99
CREATED_RELIC_RIVAL_CLAIM_CHANCE = 0.70
CREATED_RELIC_RECLAIM_MOVE_COOLDOWN_MIN = TICKS_PER_DAY * 3
CREATED_RELIC_RECLAIM_MOVE_COOLDOWN_MAX = TICKS_PER_DAY * 7
CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MIN = TICKS_PER_TENDAY
CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MAX = TICKS_PER_TENDAY * 2
CREATED_RELIC_RECLAIM_SUCCESS_COOLDOWN_MIN = TICKS_PER_MONTH
CREATED_RELIC_RECLAIM_SUCCESS_COOLDOWN_MAX = TICKS_PER_MONTH * 2


@dataclass
class Relic:
    id: int
    name: str
    region_id: int
    holder_id: Optional[int] = None
    power_bonus: int = 4
    reputation_bonus: int = 8
    difficulty: int = 1
    quest_steps_required: int = 2
    control_bonus: int = 0
    trouble_beacon: int = 0
    description: str = ""
    relic_type: str = "artifact"
    slot: str = "misc"
    guardian_monster_id: Optional[int] = None
    quest_progress_by_actor: Dict[int, int] = field(default_factory=dict)
    discovered_by: Set[int] = field(default_factory=set)
    next_progress_tick_by_actor: Dict[int, int] = field(default_factory=dict)
    next_reclaim_tick_by_actor: Dict[int, int] = field(default_factory=dict)
    active: bool = False
    released_tick: int = -1
    destroyed: bool = False
    creator_deity: object = None
    tier: str = "world"
    template_key: str = ""
    template_label: str = ""
    boon_label: str = ""
    boon_stat: str = ""
    boon_amount: int = 0
    original_recipient_id: Optional[int] = None
    created_by_player: bool = False
    created_tick: int = -1
    possession_history: list = field(default_factory=list)
    revealed_tick: int = -1
    public_memory_tick: int = -1
    failed_claims: int = 0
    quest_deaths: int = 0
    folklore_pressure: float = 0.0

    @property
    def is_revealed(self) -> bool:
        return int(getattr(self, "revealed_tick", -1) or -1) >= 0


class RelicMixin:
    def _reveal_relic(self, relic, reason: str = "revealed") -> None:
        if relic is None:
            return
        if int(getattr(relic, "revealed_tick", -1) or -1) < 0:
            relic.revealed_tick = getattr(self.world, "tick", 0)
            relic.public_memory_tick = getattr(self.world, "tick", 0)
            try:
                self.world.log(f"Rumors of {relic.name} enter living memory: {reason}.", importance=3, category="relic")
            except Exception:
                pass

    def _seed_relics(self, world) -> None:
        if getattr(world, "relics", None):
            return
        chosen = self.rng.sample(list(world.regions.keys()), k=min(len(RELIC_SPECS), len(world.regions)))
        for region_id, spec in zip(chosen, RELIC_SPECS):
            name, power_bonus, reputation_bonus, difficulty, steps, control_bonus, trouble_beacon, description = spec
            relic = Relic(
                id=world.next_relic_id,
                name=name,
                region_id=region_id,
                power_bonus=power_bonus,
                reputation_bonus=reputation_bonus,
                difficulty=difficulty,
                quest_steps_required=steps,
                control_bonus=control_bonus,
                trouble_beacon=trouble_beacon,
                description=description,
            )
            world.relics[relic.id] = relic
            world.next_relic_id += 1
        world.relic_release_started = False


    def _deity_key(self, deity) -> str:
        return str(getattr(deity, "value", getattr(deity, "name", deity))).strip().lower()

    def _same_deity(self, a, b) -> bool:
        return self._deity_key(a) == self._deity_key(b)

    def _apply_relic_boon(self, actor, relic) -> None:
        key = str(getattr(relic, "boon_label", "") or "").strip().lower()
        if not key:
            return
        stat = getattr(relic, "boon_stat", "") or BOON_DEFS.get(key, {}).get("stat", "")
        amount = int(getattr(relic, "boon_amount", 0) or TIER_DEFS.get(getattr(relic, "tier", "lesser"), {}).get("boon_amount", 0) or 0)
        if not stat or amount <= 0 or not hasattr(actor, stat):
            return
        actor.relic_boon_stat = stat
        actor.relic_boon_amount = amount
        setattr(actor, stat, int(getattr(actor, stat, 0)) + amount)
        if stat == "constitution":
            actor.max_hp += amount
            actor.hp += amount

    def _remove_relic_boon(self, actor, relic=None) -> None:
        stat = getattr(actor, "relic_boon_stat", "")
        amount = int(getattr(actor, "relic_boon_amount", 0) or 0)
        if stat and amount and hasattr(actor, stat):
            setattr(actor, stat, int(getattr(actor, stat, 0)) - amount)
            if stat == "constitution":
                actor.max_hp = max(1, actor.max_hp - amount)
                actor.hp = min(actor.hp, actor.max_hp)
        actor.relic_boon_stat = ""
        actor.relic_boon_amount = 0

    def _created_relic_counts_for_deity(self, deity) -> dict:
        counts = {"lesser": 0, "greater": 0}
        for relic in getattr(self.world, "relics", {}).values():
            if getattr(relic, "created_by_player", False) and self._same_deity(getattr(relic, "creator_deity", None), deity):
                tier = str(getattr(relic, "tier", "lesser")).lower()
                if tier in counts:
                    counts[tier] += 1
        return counts

    def _create_custom_relic_for_actor(self, actor, name: str, relic_type: str, slot: str, power_bonus: int, reputation_bonus: int, description: str = "", creator_deity=None, tier: str = "custom", boon_label: str = "", boon_stat: str = "", boon_amount: int = 0, template_key: str = "", template_label: str = "", original_recipient_id=None, created_by_player: bool = False):
        world = self.world
        if getattr(actor, "relic_id", None) is not None:
            return None
        if creator_deity is None:
            creator_deity = getattr(actor, "deity", None)
        relic = Relic(
            id=world.next_relic_id,
            name=name,
            region_id=actor.region_id,
            holder_id=actor.id,
            power_bonus=max(0, int(power_bonus)),
            reputation_bonus=max(0, int(reputation_bonus)),
            difficulty=1,
            quest_steps_required=1,
            control_bonus=0,
            trouble_beacon=0,
            description=description or f"A custom {relic_type} carried by {actor.short_name()}.",
            relic_type=str(relic_type or "custom"),
            slot=str(slot or "misc"),
            active=False,
            creator_deity=creator_deity,
            tier=str(tier or "custom").lower(),
            template_key=str(template_key or ""),
            template_label=str(template_label or relic_type or "Relic"),
            boon_label=str(boon_label or "").lower(),
            boon_stat=str(boon_stat or BOON_DEFS.get(str(boon_label or "").lower(), {}).get("stat", "")),
            boon_amount=int(boon_amount or 0),
            original_recipient_id=actor.id if original_recipient_id in (None, "") else int(original_recipient_id),
            created_by_player=bool(created_by_player),
            created_tick=getattr(world, "tick", 0),
        )
        relic.possession_history.append((getattr(world, "tick", 0), "created", actor.id, actor.region_id))
        relic.revealed_tick = getattr(world, "tick", 0)
        relic.public_memory_tick = getattr(world, "tick", 0)
        world.relics[relic.id] = relic
        world.next_relic_id += 1
        actor.relic_id = relic.id
        actor.relic_power_bonus = relic.power_bonus
        actor.reputation += relic.reputation_bonus
        self._apply_relic_boon(actor, relic)
        world.log(f"{actor.short_name()} receives {relic.name}.", importance=3, category="relic")
        if hasattr(self, "_story_note"):
            self._story_note(actor, f"Received relic {relic.name}: {relic.description}")
        return relic


    def _relic_release_tick(self) -> None:
        world = self.world
        if world.tick < RELIC_RELEASE_YEAR * TICKS_PER_YEAR:
            return
        if world.tick % RELIC_RELEASE_CHECK_INTERVAL != 0:
            return

        active = [
            relic for relic in world.relics.values()
            if getattr(relic, "active", False)
            and not getattr(relic, "destroyed", False)
            and relic.holder_id is None
        ]
        if len(active) >= MAX_ACTIVE_RELIC_QUESTS:
            return

        hidden = [
            relic for relic in world.relics.values()
            if not getattr(relic, "active", False)
            and not getattr(relic, "destroyed", False)
            and relic.holder_id is None
        ]
        if not hidden:
            return

        slots = MAX_ACTIVE_RELIC_QUESTS - len(active)
        # Easier martial relics surface first; mythic relics tend to stay legendary longer.
        hidden.sort(key=lambda relic: (relic.difficulty, relic.quest_steps_required, self.rng.random()))
        for relic in hidden[:slots]:
            relic.active = True
            relic.released_tick = world.tick
            self._reveal_relic(relic, "old roads, rumors, and omens begin to point toward it")
            if getattr(relic, "guardian_monster_id", None) is None:
                self._assign_relic_guardian(world, relic)
            world.log(
                f"Old roads, rumors, and omens begin to point toward {relic.name} in {world.region_name(relic.region_id)}.",
                importance=3,
                category="relic_quest",
            )

    def _set_relic_step_cooldown(self, actor, relic) -> None:
        relic.next_progress_tick_by_actor[actor.id] = self.world.tick + self.rng.randint(
            RELIC_STEP_COOLDOWN_MIN,
            RELIC_STEP_COOLDOWN_MAX,
        )

    def _relic_step_ready(self, actor, relic) -> bool:
        return self.world.tick >= relic.next_progress_tick_by_actor.get(actor.id, -1)

    def _set_created_relic_reclaim_cooldown(self, actor, relic, min_ticks: int, max_ticks: int) -> None:
        if actor is None or relic is None:
            return
        try:
            min_ticks = max(1, int(min_ticks))
            max_ticks = max(min_ticks, int(max_ticks))
            relic.next_reclaim_tick_by_actor[int(actor.id)] = self.world.tick + self.rng.randint(min_ticks, max_ticks)
        except Exception:
            pass

    def _created_relic_reclaim_ready(self, actor, relic) -> bool:
        if actor is None or relic is None:
            return False
        try:
            return self.world.tick >= relic.next_reclaim_tick_by_actor.get(int(actor.id), -1)
        except Exception:
            return True

    def _clear_created_relic_reclaim_cooldown(self, actor, relic) -> None:
        if actor is None or relic is None:
            return
        try:
            relic.next_reclaim_tick_by_actor.pop(int(actor.id), None)
        except Exception:
            pass

    def _assign_relic_guardian(self, world, relic) -> None:
        monster = None
        if relic.name == "The One Ring":
            monster = self._make_horror(relic.region_id) if hasattr(self, "_make_horror") else None
            if monster is None and hasattr(self, "_make_dragon"):
                monster = self._make_dragon(relic.region_id)
        elif relic.name == "The Holy Grail":
            monster = self._make_dragon(relic.region_id) if hasattr(self, "_make_dragon") else None
        elif relic.difficulty >= 3:
            monster = self._make_dragon(relic.region_id) if hasattr(self, "_make_dragon") else None
        elif relic.name == "The Black Blade" and hasattr(self, "_make_giant"):
            monster = self._make_giant(relic.region_id)
        elif hasattr(self, "_make_giant"):
            monster = self._make_giant(relic.region_id)

        if monster is None and hasattr(self, "_make_goblin"):
            monster = self._make_goblin(relic.region_id)

        if monster is None:
            return
        monster.name = f"Guardian of {relic.name}: {monster.name}"
        monster.power += relic.difficulty * 3
        monster.reputation += relic.difficulty
        world.monsters[monster.id] = monster
        relic.guardian_monster_id = monster.id

    def _local_unclaimed_relics(self, region_id: int):
        return [
            relic for relic in self.world.relics.values()
            if not getattr(relic, "destroyed", False)
            and getattr(relic, "active", False)
            and relic.holder_id is None
            and relic.region_id == region_id
        ]

    def _relic_for_actor(self, actor):
        if getattr(actor, "relic_id", None) is None:
            return None
        return self.world.relics.get(actor.relic_id)

    def _claim_relic(self, actor, relic) -> None:
        if getattr(actor, "relic_id", None) is not None or getattr(relic, "destroyed", False):
            return
        if getattr(relic, "created_by_player", False) and getattr(actor, "champion_of", None) is None:
            return
        previous_holder = getattr(relic, "holder_id", None)
        self._reveal_relic(relic, f"{actor.short_name()} claims it")
        actor.relic_id = relic.id
        actor.relic_power_bonus = relic.power_bonus
        relic.holder_id = actor.id
        relic.active = False
        actor.reputation += relic.reputation_bonus
        self._apply_relic_boon(actor, relic)
        relic.possession_history.append((getattr(self.world, "tick", 0), "claimed", actor.id, actor.region_id))
        if getattr(relic, "created_by_player", False):
            self._clear_created_relic_reclaim_cooldown(actor, relic)
            creator = getattr(relic, "creator_deity", None)
            if self._same_deity(getattr(actor, "champion_of", None), creator) or self._same_deity(getattr(actor, "deity", None), creator):
                self.world.log(f"{actor.short_name()} reclaims {relic.name} for {getattr(creator, 'value', creator)}.", importance=4, category="relic")
            else:
                self.world.log(f"{actor.short_name()} steals {relic.name}, a relic of {getattr(creator, 'value', creator)}.", importance=4, category="relic")
        region = self.world.regions.get(actor.region_id)
        if region is not None and relic.control_bonus:
            delta = relic.control_bonus if not actor.is_evil() else -abs(relic.control_bonus)
            self.world.adjust_region_state(region.id, control_delta=delta, order_delta=1)
        self.world.log(
            f"{actor.short_name()} claims {relic.name} in {self.world.region_name(actor.region_id)}.",
            importance=4,
            category="relic",
        )
        if hasattr(self, "_story_note"):
            self._story_note(actor, f"Claimed {relic.name}: {relic.description}")

    def _drop_relic(self, actor) -> None:
        if getattr(actor, "relic_id", None) is None:
            return
        relic = self.world.relics.get(actor.relic_id)
        if relic is not None and not getattr(relic, "destroyed", False):
            self._remove_relic_boon(actor, relic)
            relic.holder_id = None
            relic.region_id = actor.region_id
            self._reveal_relic(relic, f"it is lost after the fall of {actor.short_name()}")
            relic.active = True
            relic.possession_history.append((getattr(self.world, "tick", 0), "dropped", actor.id, actor.region_id))
            self.world.log(
                f"{relic.name} is lost in {self.world.region_name(actor.region_id)} after the fall of {actor.short_name()}.",
                importance=3 if relic.name == "The One Ring" else 2,
                category="relic",
            )
        actor.relic_id = None
        actor.relic_power_bonus = 0

    def _is_rightful_created_relic_reclaimer(self, actor, relic) -> bool:
        return (
            getattr(relic, "created_by_player", False)
            and getattr(relic, "holder_id", None) is None
            and getattr(actor, "champion_of", None) is not None
            and self._same_deity(getattr(actor, "champion_of", None), getattr(relic, "creator_deity", None))
        )

    def _created_relic_reclaim_chance(self, actor, relic) -> float:
        # Divine-crafted relics are not meant to behave like mythic world relics.
        # If a same-deity champion finds their god's lost relic, they should almost
        # always recover it; the global RELIC_ACTION_MAX_CHANCE remains for baked relics.
        return max(0.0, min(1.0, float(globals().get("CREATED_RELIC_RECLAIM_CHANCE", 0.99))))

    def _relic_action_chance(self, actor, relic) -> float:
        party = self.world.get_party(actor)
        party_size = len(party.member_ids) if party else 1
        chance = RELIC_ACTION_BASE_CHANCE
        chance += min(0.15, actor.reputation / 1000.0)
        chance += min(0.08, max(0, actor.power_rating() - 20) / 700.0)
        chance += min(0.10, party_size * 0.012)
        if actor.is_good() and relic.name == "The Holy Grail":
            chance += 0.06
        if actor.is_evil() and relic.name in ("The One Ring", "The Black Blade"):
            chance += 0.06
        if relic.name == "The One Ring" and actor.deity == Deity.LORD_OF_DARKNESS:
            chance += 0.05
        if getattr(relic, "created_by_player", False) and getattr(actor, "champion_of", None) is not None:
            if self._same_deity(getattr(actor, "champion_of", None), getattr(relic, "creator_deity", None)):
                chance += 0.25
        return min(RELIC_ACTION_MAX_CHANCE, chance)

    def _guardian_alive(self, relic):
        gid = getattr(relic, "guardian_monster_id", None)
        if gid is None:
            return None
        guardian = self.world.monsters.get(gid)
        if guardian is not None and guardian.alive:
            return guardian
        return None

    def _record_relic_guardian_confrontation(self, actor, relic, guardian, before_alive_ids=None, battle_result=True) -> None:
        """Record failed relic-claim pressure from guardian confrontations.

        A guardian confrontation is not merely a monster fight. If the guardian
        survives the confrontation, the relic quest has failed for now. If any
        adventurer dies in that confrontation, that death should also feed the
        relic's failed-quest folklore instead of only the monster's kill stats.
        """
        if relic is None or guardian is None:
            return
        world = self.world
        before_alive_ids = set(before_alive_ids or [])
        after_alive_ids = {
            int(getattr(member, "id"))
            for member in world.side_members(actor)
            if getattr(member, "alive", False)
        }
        deaths = len(before_alive_ids - after_alive_ids)
        guardian_alive = bool(getattr(guardian, "alive", False))
        if deaths > 0:
            relic.quest_deaths = int(getattr(relic, "quest_deaths", 0) or 0) + deaths
            self._reveal_relic(relic, f"blood is spilled before its guardian, {guardian.name}")
        if guardian_alive:
            relic.failed_claims = int(getattr(relic, "failed_claims", 0) or 0) + 1
            self._reveal_relic(relic, f"its guardian turns back a would-be claimant")
            try:
                actor_name = actor.short_name() if hasattr(actor, "short_name") else str(getattr(actor, "id", "someone"))
                death_text = f", killing {deaths}" if deaths > 0 else ""
                world.log(
                    f"The guardian of {relic.name} repels {actor_name}{death_text}; the failed claim enters rumor.",
                    importance=2 if deaths <= 0 else 3,
                    category="relic_quest",
                )
            except Exception:
                pass
        elif deaths > 0:
            try:
                world.log(
                    f"The quest for {relic.name} is won at a cost: {deaths} fall before its guardian.",
                    importance=3,
                    category="relic_quest",
                )
            except Exception:
                pass

    def _advance_relic_quest(self, actor, relic) -> bool:
        if not getattr(relic, "active", False):
            return False
        if not self._relic_step_ready(actor, relic):
            return False

        progress = relic.quest_progress_by_actor.get(actor.id, 0)
        if actor.id not in relic.discovered_by:
            relic.discovered_by.add(actor.id)
            relic.quest_progress_by_actor[actor.id] = max(progress, 1)
            self.world.log(
                f"{actor.short_name()} discovers a trail of rumors leading toward {relic.name} in {self.world.region_name(relic.region_id)}.",
                importance=2,
                category="relic_quest",
            )
            self._set_relic_step_cooldown(actor, relic)
            self._spend_action(actor)
            return True

        guardian = self._guardian_alive(relic)
        if progress >= max(1, relic.quest_steps_required - 1) and guardian is not None:
            self.world.log(
                f"{actor.short_name()} confronts the guardian of {relic.name}: {guardian.name}.",
                importance=3,
                category="relic_quest",
            )
            before_alive_ids = {
                int(getattr(member, "id"))
                for member in self.world.side_members(actor)
                if getattr(member, "alive", False)
            }
            self._set_relic_step_cooldown(actor, relic)
            self._spend_action(actor)
            battle_result = False
            if hasattr(self, "_resolve_monster_battle"):
                battle_result = bool(self._resolve_monster_battle(actor, guardian))
            self._record_relic_guardian_confrontation(actor, relic, guardian, before_alive_ids, battle_result)
            return True

        if progress < relic.quest_steps_required:
            relic.quest_progress_by_actor[actor.id] = progress + 1
            self.world.log(
                f"{actor.short_name()} advances the quest for {relic.name} ({progress + 1}/{relic.quest_steps_required}).",
                importance=2,
                category="relic_quest",
            )
            self._set_relic_step_cooldown(actor, relic)
            self._spend_action(actor)
            return True

        if guardian is None:
            self._claim_relic(actor, relic)
            self._spend_action(actor)
            return True
        return False

    def _created_relic_priority_score(self, actor, relic, holder=None) -> int:
        score = 0
        if getattr(relic, "created_by_player", False):
            score += 100
        if self._same_deity(getattr(actor, "champion_of", None), getattr(relic, "creator_deity", None)):
            score += 1000
        if getattr(relic, "region_id", None) == getattr(actor, "region_id", None):
            score += 500
        if holder is not None and getattr(holder, "region_id", None) == getattr(actor, "region_id", None):
            score += 400
        score += int(getattr(relic, "power_bonus", 0) or 0) * 5
        score += int(getattr(relic, "reputation_bonus", 0) or 0) * 3
        return score

    def _lost_created_relic_target(self, actor):
        if getattr(actor, "champion_of", None) is None:
            return None
        if getattr(actor, "relic_id", None) is not None:
            return None
        candidates = []
        for relic in getattr(self.world, "relics", {}).values():
            if not getattr(relic, "created_by_player", False) or getattr(relic, "destroyed", False):
                continue
            if not getattr(relic, "active", False):
                continue
            if getattr(relic, "holder_id", None) is not None:
                continue
            if getattr(relic, "region_id", None) is None:
                continue
            candidates.append((self._created_relic_priority_score(actor, relic), relic))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def _stolen_created_relic_target_pair(self, actor):
        if getattr(actor, "champion_of", None) is None:
            return None
        candidates = []
        for relic in getattr(self.world, "relics", {}).values():
            if not getattr(relic, "created_by_player", False) or getattr(relic, "destroyed", False):
                continue
            if not self._same_deity(getattr(actor, "champion_of", None), getattr(relic, "creator_deity", None)):
                continue
            if not self._created_relic_reclaim_ready(actor, relic):
                continue
            holder_id = getattr(relic, "holder_id", None)
            if holder_id is None or holder_id == actor.id:
                continue
            holder = self.world.actors.get(holder_id)
            if holder is not None and getattr(holder, "alive", False):
                candidates.append((self._created_relic_priority_score(actor, relic, holder), relic, holder))
        if not candidates:
            return None
        _, relic, holder = max(candidates, key=lambda item: item[0])
        return relic, holder

    def _stolen_created_relic_holder_target(self, actor):
        pair = self._stolen_created_relic_target_pair(actor)
        return pair[1] if pair is not None else None

    def _next_step_toward_region(self, start_region_id: int, target_region_id: int):
        if start_region_id == target_region_id:
            return start_region_id
        regions = getattr(self.world, "regions", {})
        if start_region_id not in regions or target_region_id not in regions:
            return None
        frontier = [(start_region_id, [])]
        seen = {start_region_id}
        while frontier:
            region_id, path = frontier.pop(0)
            for neighbor_id in getattr(regions[region_id], "neighbors", []) or []:
                if neighbor_id in seen:
                    continue
                next_path = path + [neighbor_id]
                if neighbor_id == target_region_id:
                    return next_path[0] if next_path else target_region_id
                seen.add(neighbor_id)
                if neighbor_id in regions:
                    frontier.append((neighbor_id, next_path))
        return None

    def _move_actor_or_party_toward_region(self, actor, target_region_id: int, reason: str = "a relic call") -> bool:
        step_region_id = self._next_step_toward_region(getattr(actor, "region_id", None), target_region_id)
        if step_region_id is None or step_region_id == getattr(actor, "region_id", None):
            return False
        world = self.world
        party = world.get_party(actor) if hasattr(world, "get_party") else None
        if party is not None:
            for member_id in list(getattr(party, "member_ids", []) or []):
                member = world.actors.get(member_id)
                if member is not None and getattr(member, "alive", False):
                    world.move_actor(member, step_region_id) if hasattr(world, "move_actor") else setattr(member, "region_id", step_region_id)
            self._spend_action(actor)
            if self.rng.random() < 0.35:
                world.log(f"{self._format_side_names([world.actors[mid] for mid in party.member_ids if mid in world.actors and world.actors[mid].alive])} turns toward {world.region_name(target_region_id)} under {reason}.", importance=2, category="relic_pressure")
        else:
            world.move_actor(actor, step_region_id) if hasattr(world, "move_actor") else setattr(actor, "region_id", step_region_id)
            self._spend_action(actor)
            if self.rng.random() < 0.25:
                world.log(f"{actor.short_name()} turns toward {world.region_name(target_region_id)} under {reason}.", importance=2, category="relic_pressure")
        return True

    def _champion_created_relic_compulsion(self, actor) -> bool:
        if getattr(actor, "champion_of", None) is None:
            return False

        # First priority: if a created relic is already here and this champion can carry it, grab it now.
        if getattr(actor, "relic_id", None) is None:
            local = []
            for relic in self._local_unclaimed_relics(getattr(actor, "region_id", None)):
                if getattr(relic, "created_by_player", False):
                    local.append((self._created_relic_priority_score(actor, relic), relic))
            if local:
                relic = max(local, key=lambda item: item[0])[1]
                if self._is_rightful_created_relic_reclaimer(actor, relic):
                    if self.rng.random() < self._created_relic_reclaim_chance(actor, relic):
                        self._claim_relic(actor, relic)
                        self._spend_action(actor)
                        return True
                    return False
                # Any champion may claim a dropped player-created relic. Same-faith reclaim is nearly certain;
                # rival champions still feel a strong divine pull, but theft is not guaranteed.
                steal_chance = float(globals().get("CREATED_RELIC_RIVAL_CLAIM_CHANCE", 0.70))
                if self.rng.random() < max(0.0, min(1.0, steal_chance)):
                    self._claim_relic(actor, relic)
                    self._spend_action(actor)
                    return True
                return False

        # Second priority: if this champion's god's relic is carried by another actor, hunt the thief.
        # This pressure is deliberately cooled down separately from ordinary relic quest progress; otherwise
        # champions can spam the event log and burn every action cycle chasing the same stolen relic.
        stolen_pair = self._stolen_created_relic_target_pair(actor)
        if stolen_pair is not None:
            stolen_relic, stolen_holder = stolen_pair
            if getattr(stolen_holder, "region_id", None) == getattr(actor, "region_id", None):
                if hasattr(self, "_should_attack") and self._should_attack(actor, stolen_holder):
                    self.world.log(f"{actor.short_name()} moves to reclaim a stolen divine relic from {stolen_holder.short_name()}.", importance=3, category="relic_pressure")
                    self._resolve_battle(actor, stolen_holder)
                    if getattr(actor, "alive", False) and getattr(actor, "relic_id", None) == getattr(stolen_relic, "id", None):
                        self._set_created_relic_reclaim_cooldown(actor, stolen_relic, CREATED_RELIC_RECLAIM_SUCCESS_COOLDOWN_MIN, CREATED_RELIC_RECLAIM_SUCCESS_COOLDOWN_MAX)
                    else:
                        self._set_created_relic_reclaim_cooldown(actor, stolen_relic, CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MIN, CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MAX)
                    return True
                if hasattr(self, "_should_retreat") and self._should_retreat(actor, stolen_holder):
                    self._retreat(actor, reason="a stolen divine relic is guarded by stronger hands")
                    self._set_created_relic_reclaim_cooldown(actor, stolen_relic, CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MIN, CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MAX)
                    return True
                self._set_created_relic_reclaim_cooldown(actor, stolen_relic, CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MIN, CREATED_RELIC_RECLAIM_FAILED_COOLDOWN_MAX)
                return False
            if self._move_actor_or_party_toward_region(actor, stolen_holder.region_id, reason="a stolen divine relic's call"):
                self._set_created_relic_reclaim_cooldown(actor, stolen_relic, CREATED_RELIC_RECLAIM_MOVE_COOLDOWN_MIN, CREATED_RELIC_RECLAIM_MOVE_COOLDOWN_MAX)
                return True

        # Third priority: pursue dropped player-created relics anywhere in the connected map.
        lost_relic = self._lost_created_relic_target(actor)
        if lost_relic is not None and getattr(lost_relic, "region_id", None) != getattr(actor, "region_id", None):
            if not self._created_relic_reclaim_ready(actor, lost_relic):
                return False
            moved = self._move_actor_or_party_toward_region(actor, lost_relic.region_id, reason="a lost divine relic's call")
            if moved:
                self._set_created_relic_reclaim_cooldown(actor, lost_relic, CREATED_RELIC_RECLAIM_MOVE_COOLDOWN_MIN, CREATED_RELIC_RECLAIM_MOVE_COOLDOWN_MAX)
            return moved

        return False

    def _seek_relic(self, actor) -> bool:
        return self._maybe_handle_relic_action(actor)

    def _maybe_handle_relic_action(self, actor) -> bool:
        if getattr(actor, "relic_id", None) is not None:
            relic = self._relic_for_actor(actor)
            if relic is not None and self._can_destroy_one_ring(actor, relic):
                return self._destroy_one_ring(actor, relic)
            return False
        relics = self._local_unclaimed_relics(actor.region_id)
        if getattr(actor, "champion_of", None) is None:
            relics = [r for r in relics if not getattr(r, "created_by_player", False)]
        if not relics:
            return False
        relic = max(relics, key=lambda r: (
            1000 if getattr(r, "created_by_player", False) and self._same_deity(getattr(actor, "champion_of", None), getattr(r, "creator_deity", None)) else 0,
            r.difficulty, r.power_bonus, r.reputation_bonus
        ))
        if self._is_rightful_created_relic_reclaimer(actor, relic):
            if self.rng.random() >= self._created_relic_reclaim_chance(actor, relic):
                return False
            self._claim_relic(actor, relic)
            self._spend_action(actor)
            return True
        if self.rng.random() >= self._relic_action_chance(actor, relic):
            return False
        return self._advance_relic_quest(actor, relic)

    def _can_destroy_one_ring(self, actor, relic) -> bool:
        return (
            relic.name == "The One Ring"
            and not getattr(relic, "destroyed", False)
            and actor.alive
            and actor.is_good()
            and actor.deity == Deity.LORD_OF_LIGHT
            and actor.power_rating() >= RING_DESTROY_MIN_POWER
            and actor.reputation >= RING_DESTROY_MIN_REPUTATION
        )

    def _destroy_one_ring(self, actor, relic) -> bool:
        relic.destroyed = True
        relic.holder_id = None
        relic.active = False
        actor.relic_id = None
        actor.relic_power_bonus = 0
        for region in self.world.regions.values():
            region.permanent_order_bonus = getattr(region, "permanent_order_bonus", 0) + RING_DESTROY_ORDER_BONUS
            region.order = min(100, max(getattr(region, "permanent_order_bonus", 0), region.order + RING_DESTROY_ORDER_BONUS))
        actor.reputation += 50
        self.world.log(
            f"{actor.full_name()} casts The One Ring into Hell, breaking its dominion. Order rises permanently across the continent.",
            importance=5,
            category="relic",
        )
        if hasattr(self, "_story_note"):
            self._story_note(actor, "Destroyed The One Ring by casting it into Hell.")
        self._spend_action(actor)
        return True

    def _spawn_or_move_monster_toward_relic(self, region_id: int) -> None:
        living = [m for m in self.world.living_monsters() if m.alive]
        if not living:
            return

        monster = max(living, key=lambda m: (m.effective_power(), self.rng.random()))
        old = monster.region_id
        monster.region_id = region_id
        if old != region_id:
            self.world.log(
                f"{monster.name} is drawn toward the shadow of The One Ring in {self.world.region_name(region_id)}.",
                importance=2,
                category="relic_pressure",
            )

    def _tempt_actor_toward_evil(self, actor) -> None:
        if actor.is_evil():
            return
        if actor.alignment == Alignment.LAWFUL_GOOD:
            actor.alignment = Alignment.LAWFUL_NEUTRAL
        elif actor.alignment == Alignment.NEUTRAL_GOOD:
            actor.alignment = Alignment.TRUE_NEUTRAL
        elif actor.alignment == Alignment.CHAOTIC_GOOD:
            actor.alignment = Alignment.CHAOTIC_NEUTRAL
        elif actor.alignment == Alignment.LAWFUL_NEUTRAL:
            actor.alignment = Alignment.LAWFUL_EVIL
        elif actor.alignment == Alignment.TRUE_NEUTRAL:
            actor.alignment = Alignment.NEUTRAL_EVIL
        elif actor.alignment == Alignment.CHAOTIC_NEUTRAL:
            actor.alignment = Alignment.CHAOTIC_EVIL
        self.world.log(
            f"The One Ring darkens {actor.short_name()}'s judgment toward {actor.alignment.value}.",
            importance=3,
            category="relic_pressure",
        )

    def _apply_one_ring_pressure(self, actor, relic) -> None:
        actor.reputation += RING_REPUTATION_TICK
        region = self.world.regions.get(actor.region_id)
        if region is not None:
            control_delta = abs(relic.control_bonus) if actor.is_evil() else max(1, relic.control_bonus // 3)
            if actor.is_evil():
                control_delta = -control_delta
            self.world.adjust_region_state(region.id, control_delta=control_delta, order_delta=-max(1, relic.trouble_beacon // 2))
        if self.rng.random() < min(0.35, 0.04 * relic.trouble_beacon):
            self._spawn_or_move_monster_toward_relic(actor.region_id)
        if self.rng.random() < 0.08:
            self._tempt_actor_toward_evil(actor)
        enemies = [a for a in self.world.actors_in_region(actor.region_id) if a.alive and a.id != actor.id and a.is_adventurer() and a.is_good()]
        if enemies and hasattr(self, "_register_nemesis"):
            enemy = max(enemies, key=lambda a: (a.reputation, a.power_rating(), self.rng.random()))
            self._register_nemesis(enemy, actor, reason=f"drawn to oppose the bearer of {relic.name}")
            self._register_nemesis(actor, enemy, reason=f"challenged over possession of {relic.name}")

    def _relic_tick(self) -> None:
        self._relic_release_tick()
        if self.world.tick % RING_PRESSURE_INTERVAL != 0:
            return
        for relic in list(self.world.relics.values()):
            if getattr(relic, "destroyed", False) or relic.holder_id is None:
                continue
            actor = self.world.actors.get(relic.holder_id)
            if actor is None or not actor.alive:
                relic.holder_id = None
                relic.active = True
                continue
            actor.relic_power_bonus = getattr(relic, "power_bonus", 4)
            if relic.name == "The One Ring":
                self._apply_one_ring_pressure(actor, relic)

    def _apply_relic_order_floor(self) -> None:
        for region in self.world.regions.values():
            floor = getattr(region, "permanent_order_bonus", 0)
            if floor:
                region.order = max(floor, region.order)
