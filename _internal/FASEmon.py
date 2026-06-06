from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from FASEclass import Actor, Monster, MonsterKind
from FASEcfg import *

class MonsterMixin:
    def _monster_grace_active(self) -> bool:
        years = getattr(self, "_monster_grace_years_actual", None)
        if years is None:
            base_years = max(0, int(globals().get("MONSTER_GRACE_YEARS", 0)))
            variance = max(0, int(globals().get("MONSTER_GRACE_VARIANCE", 0)))
            if base_years > 0 and variance > 0:
                years = max(0, self.rng.randint(base_years - variance, base_years + variance))
            else:
                years = base_years
            self._monster_grace_years_actual = years
        years = max(0, int(years))
        return years > 0 and getattr(self.world, "tick", 0) < years * TICKS_PER_YEAR

    def _living_commoner_total_for_dragon_dormancy(self) -> int:
        return max(0, int(sum(getattr(self.world, "commoners_by_region", {}).values())))

    def _dragon_dormancy_enabled(self) -> bool:
        return bool(globals().get("DRAGON_DORMANCY_ENABLED", True))

    def _dragon_dormancy_floor(self) -> int:
        threshold = max(0.0, float(globals().get("DRAGON_DORMANCY_POP_THRESHOLD", 0.20)))
        return max(0, int(globals().get("INITIAL_POPULATION", 0) * threshold))

    def _dragon_wake_floor(self) -> int:
        wake = max(0.0, float(globals().get("DRAGON_WAKE_POP_THRESHOLD", 1.00)))
        dormancy = max(0.0, float(globals().get("DRAGON_DORMANCY_POP_THRESHOLD", 0.20)))
        wake = max(wake, dormancy)
        return max(0, int(globals().get("INITIAL_POPULATION", 0) * wake))

    def _dragon_spawn_suppressed_by_dormancy(self) -> bool:
        if not self._dragon_dormancy_enabled():
            return False
        return self._living_commoner_total_for_dragon_dormancy() < self._dragon_wake_floor()

    def _update_dragon_dormancy(self, monster: Monster) -> bool:
        if monster.kind != MonsterKind.DRAGON or not self._dragon_dormancy_enabled():
            return False

        commoners = self._living_commoner_total_for_dragon_dormancy()
        dormant = bool(getattr(monster, "dormant", False))

        if dormant:
            if commoners >= self._dragon_wake_floor():
                monster.dormant = False
                self.world.log(
                    f"{monster.name} stirs from its long sleep as civilization again grows fat enough to trouble it.",
                    importance=2,
                    category="dragon_dormancy",
                )
                return False
            return True

        if commoners <= self._dragon_dormancy_floor():
            monster.dormant = True
            monster.patron_actor_id = None
            monster.retreat_until_tick = -1
            if not hasattr(monster, "last_action_tick"):
                monster.last_action_tick = -1
            if not hasattr(monster, "last_move_tick"):
                monster.last_move_tick = -1
            if not hasattr(monster, "last_retreat_tick"):
                monster.last_retreat_tick = -1
            self.world.log(
                f"{monster.name} withdraws into dormancy as the living world thins beneath it.",
                importance=2,
                category="dragon_dormancy",
            )
            return True

        return False

    def _giant_is_neutral(self, monster: Monster) -> bool:
        return monster.kind == MonsterKind.GIANT and getattr(monster, "name", "") in {"Hill Giant", "Green Giant"}

    def _giant_is_evil_aligned(self, monster: Monster) -> bool:
        return monster.kind == MonsterKind.GIANT and getattr(monster, "name", "") in {"Stone Giant", "Frost Giant"}

    def _monster_can_be_evil_follower(self, monster: Monster) -> bool:
        # Only goblins become true monster-followers. Evil-aligned giants may
        # drift with armies, but they are not worshippers or loyal subjects.
        return monster.kind == MonsterKind.GOBLIN

    def _evil_monster_patron_candidates(self, region_id: int, min_rep: int = 8, min_charisma: int = 12) -> list:
        world = self.world
        return [
            actor for actor in world.actors_in_region(region_id)
            if getattr(actor, "alive", False)
            and actor.is_adventurer()
            and actor.is_evil()
            and getattr(actor, "reputation", 0) >= min_rep
            and getattr(actor, "charisma", 0) >= min_charisma
        ]

    def _bind_monster_to_evil_patron(self, monster: Monster, leader: Actor, category: str = "monster_loyalty") -> None:
        monster.patron_actor_id = leader.id
        monster.patron_deity = leader.deity
        if monster.kind == MonsterKind.GOBLIN:
            monster.horde_size = max(monster.horde_size, monster.horde_size + self.rng.randint(0, 2))
        else:
            monster.monster_xp = getattr(monster, "monster_xp", 0) + 1
        self.world.log(
            f"{leader.short_name()} binds {monster.name} to the cause of {getattr(leader.deity, 'value', str(leader.deity))} in {self.world.region_name(monster.region_id)}.",
            importance=2,
            category=category,
        )

    def _neutral_giant_turn(self, monster: Monster) -> None:
        """Hill and Green Giants are territorial neutrals: no raiding, no evil patronage."""
        world = self.world
        region = world.regions.get(monster.region_id)
        if region is None:
            return

        # Neutral giants mostly keep to themselves. They may wander within neighboring territory.
        if region.neighbors and self.rng.random() < globals().get("NEUTRAL_GIANT_WANDER_CHANCE", 0.03):
            world.move_monster(monster, self.rng.choice(region.neighbors)) if hasattr(world, "move_monster") else setattr(monster, "region_id", self.rng.choice(region.neighbors))
            world.log(f"{monster.name} lumbers from {region.name} to {world.region_name(monster.region_id)}.", importance=1, category="monster_movement")
            return

        # They create territorial pressure, but not evil oppression.
        if self.rng.random() < globals().get("NEUTRAL_GIANT_TERRITORY_CHANCE", 0.015):
            if monster.name == "Green Giant":
                world.adjust_region_state(monster.region_id, control_delta=0, order_delta=1)
                world.log(f"{monster.name} keeps to the deep green places of {world.region_name(monster.region_id)}, more guardian than raider.", importance=1, category="giant_territory")
            else:
                world.adjust_region_state(monster.region_id, control_delta=0, order_delta=-1)
                world.log(f"{monster.name} blocks old roads through {world.region_name(monster.region_id)}, demanding distance rather than tribute.", importance=1, category="giant_territory")

    def _biome_monster_pressure(self, region) -> int:
        profiles = globals().get("BIOME_PROFILES", {}) or {}
        biome = str(getattr(region, "biome", "") or "")
        profile = profiles.get(biome) or profiles.get(biome.title()) or profiles.get(biome.replace("_", " ").title())
        if not isinstance(profile, dict):
            return 45
        try:
            return max(0, min(100, int(profile.get("monster_pressure", 45))))
        except Exception:
            return 45


    def _weighted_monster_spawn_region_id(self) -> int:
        regions = list(getattr(self.world, "regions", {}).values())
        if not regions:
            return 0
        weighted = []
        for region in regions:
            pressure = self._biome_monster_pressure(region)
            danger = max(0, int(getattr(region, "danger", 0) or 0))
            # Keep every region eligible; monster-pressure biases location, not spawn volume.
            weight = max(1, int(10 + pressure + danger * 4))
            weighted.append((region.id, weight))
        total = sum(w for _rid, w in weighted)
        pick = self.rng.randint(1, max(1, total))
        running = 0
        for rid, weight in weighted:
            running += weight
            if pick <= running:
                return rid
        return weighted[-1][0]


    def _monster_spawn_scale(self) -> float:
        state = self._recovery_state()
        if state == 'crisis':
            return RECOVERY_MONSTER_SPAWN_SCALE_CRISIS
        if state == 'low':
            return RECOVERY_MONSTER_SPAWN_SCALE_LOW
        return 1.0


    def _build_region_threat_snapshot(self) -> Dict[int, Dict[str, bool]]:
        world = self.world
        snapshot: Dict[int, Dict[str, bool]] = {}
        for region_id in world.regions:
            local_actors = world.actors_in_region(region_id)
            local_monsters = world.monsters_in_region(region_id)
            snapshot[region_id] = {
                "evil_adventurers": any(actor.is_adventurer() and actor.is_evil() for actor in local_actors),
                "major_monsters": any(
                    monster.alive and monster.kind in (MonsterKind.GOBLIN, MonsterKind.GIANT, MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR)
                    for monster in local_monsters
                ),
            }
        return snapshot


    def _dragon_temperament(self, color: str) -> str:
        if color in BENEVOLENT_DRAGONS:
            return "benevolent"
        if color in AMBIVALENT_DRAGONS:
            return "ambivalent"
        return "malevolent"


    def _monster_hostile_to_actor(self, monster: Monster, actor: Actor) -> bool:
        if self._giant_is_neutral(monster):
            return getattr(monster, "provoked_until_tick", -1) > getattr(self.world, "tick", 0)
        if monster.kind == MonsterKind.DRAGON:
            patron_id = getattr(monster, "patron_actor_id", None)
            if patron_id is not None:
                patron = self.world.actors.get(patron_id)
                same_party = patron is not None and getattr(actor, "party_id", None) is not None and actor.party_id == getattr(patron, "party_id", None)
                same_polity = patron is not None and getattr(actor, "polity_id", None) is not None and actor.polity_id == getattr(patron, "polity_id", None)
                if actor.id == patron_id or same_party or same_polity:
                    return False
            temperament = getattr(monster, "dragon_temperament", "malevolent")
            if temperament == "benevolent":
                return actor.is_evil()
            if temperament == "ambivalent":
                return actor.is_evil() or actor.reputation >= 80
            return True
        return True


    def _monster_strength_bonus(self, monster: Monster) -> int:
        age_bonus = min(MONSTER_MAX_AGE_BONUS, getattr(monster, 'age_ticks', 0) // MONSTER_AGE_POWER_STEP_TICKS)
        xp_bonus = min(MONSTER_MAX_XP_BONUS, getattr(monster, 'monster_xp', 0) // MONSTER_XP_POWER_STEP)
        return age_bonus + xp_bonus


    def _monster_survival_ratio(self, monster: Monster) -> float:
        base = max(1, monster.power)
        effective = max(1, monster.effective_power())
        return min(2.0, effective / base)


    def _monster_should_retreat_from_actor(self, monster: Monster, actor: Actor) -> bool:
        world = self.world
        if getattr(monster, 'retreat_until_tick', -1) > world.tick:
            return True
        side = world.side_members(actor)
        side_power = sum(member.power_rating() for member in side if member.alive)
        monster_power = monster.effective_power()
        party = world.get_party(actor)
        party_size = len(party.member_ids) if party is not None else 1
        if party_size >= 3 and monster.kind == MonsterKind.GIANT and self.rng.random() < 0.75:
            return True
        if party_size >= 4 and monster.kind == MonsterKind.DRAGON and self.rng.random() < 0.85:
            return True
        if side_power >= monster_power * MONSTER_RETREAT_AVOID_RATIO and self.rng.random() < 0.90:
            return True
        if side_power >= monster_power * 0.75 and monster.kind in (MonsterKind.DRAGON, MonsterKind.GIANT) and self.rng.random() < 0.70:
            return True
        return False


    def _monster_retreat(self, monster: Monster) -> bool:
        world = self.world
        region = world.regions[monster.region_id]
        if not region.neighbors:
            monster.retreat_until_tick = world.tick + self.rng.randint(MONSTER_RETREAT_COOLDOWN_MIN, MONSTER_RETREAT_COOLDOWN_MAX)
            monster.last_retreat_tick = world.tick
            self._mark_monster_acted(monster)
            return False
        destination = min(
            region.neighbors,
            key=lambda rid: (
                len([a for a in world.actors_in_region(rid) if a.alive and a.is_adventurer()]),
                -world.regions[rid].danger,
                self.rng.random(),
            ),
        )
        old_region = monster.region_id
        world.move_monster(monster, destination) if hasattr(world, "move_monster") else setattr(monster, "region_id", destination)
        monster.retreat_until_tick = world.tick + self.rng.randint(MONSTER_RETREAT_COOLDOWN_MIN, MONSTER_RETREAT_COOLDOWN_MAX)
        monster.last_retreat_tick = world.tick
        self._mark_monster_moved(monster)
        if monster.kind != MonsterKind.GOBLIN:
            world.log(f"{monster.name} slips away from {world.region_name(old_region)} to {world.region_name(destination)}.", importance=1, category="monster_retreat")
        return True

    def _monster_lifespan_label(self, monster: Monster) -> str:
        if monster.kind == MonsterKind.ANCIENT_HORROR:
            return "ageless"
        max_age_ticks = int(getattr(monster, "max_age_ticks", 0) or 0)
        if max_age_ticks <= 0:
            return "unknown"
        return f"{max_age_ticks / TICKS_PER_YEAR:.1f}y"

    def _monster_old_age_check(self, monster: Monster) -> bool:
        if monster.kind == MonsterKind.ANCIENT_HORROR:
            return False
        max_age_ticks = int(getattr(monster, "max_age_ticks", 0) or 0)
        if max_age_ticks <= 0 or int(getattr(monster, "age_ticks", 0) or 0) < max_age_ticks:
            return False
        grace_ticks = max(0, int(globals().get("MONSTER_OLD_AGE_GRACE_YEARS", 10))) * TICKS_PER_YEAR
        overage = max(0, int(getattr(monster, "age_ticks", 0) or 0) - max_age_ticks)
        base_chance = max(0.0, float(globals().get("MONSTER_OLD_AGE_DEATH_CHANCE", 0.015)))
        extra = 0.0 if grace_ticks <= 0 else min(0.25, overage / grace_ticks * base_chance)
        if self.rng.random() >= min(0.40, base_chance + extra):
            return False
        monster.alive = False
        if hasattr(self.world, "kill_monster_cache_update"):
            self.world.kill_monster_cache_update(monster)
        self.world.log(
            f"{monster.name} passes from the world in {self.world.region_name(monster.region_id)} after {getattr(monster, 'age_ticks', 0) / TICKS_PER_YEAR:.1f} years.",
            importance=2 if monster.kind in (MonsterKind.GIANT, MonsterKind.DRAGON) else 1,
            category="monster_old_age",
        )
        return True

    def _tick_monster_age_and_terror(self) -> None:
        if self._monster_grace_active():
            return
        world = self.world
        for monster in list(world.living_monsters()):
            monster.age_ticks = getattr(monster, 'age_ticks', 0) + 1
            if self._monster_old_age_check(monster):
                continue
            if getattr(monster, 'retreat_until_tick', -1) < world.tick and monster.kind != MonsterKind.ANCIENT_HORROR and self.rng.random() < 0.02:
                monster.monster_xp = getattr(monster, 'monster_xp', 0) + 1
        if world.tick % MONSTER_TERROR_ORDER_DECAY_INTERVAL != 0:
            return
        for monster in world.living_monsters():
            terror = 0
            if monster.kind == MonsterKind.GOBLIN:
                terror = 1 + self._monster_strength_bonus(monster) // 12 if monster.horde_size >= 8 else 0
            elif monster.kind == MonsterKind.GIANT:
                if self._giant_is_neutral(monster):
                    terror = 0
                else:
                    terror = 4 + self._monster_strength_bonus(monster) // 6
            elif monster.kind == MonsterKind.DRAGON:
                if self._update_dragon_dormancy(monster):
                    continue
                terror = 2 + self._monster_strength_bonus(monster) // 8
            elif monster.kind == MonsterKind.ANCIENT_HORROR:
                terror = 6 + self._monster_strength_bonus(monster) // 4
            if terror:
                world.adjust_region_state(monster.region_id, control_delta=0, order_delta=-terror)


    def _active_adventurers_for_necromancer_crisis(self) -> List[Actor]:
        return [
            actor for actor in self.world.living_actors()
            if getattr(actor, "alive", False)
            and actor.is_adventurer()
            and not getattr(actor, "retired", False)
            and not getattr(actor, "withdrawn", False)
            and not getattr(actor, "in_school", False)
        ]


    def _necromancer_crisis_should_check_today(self) -> bool:
        if not bool(globals().get("ADVENTURER_SURPLUS_NECROMANCER_ENABLED", True)):
            return False
        year, month, day, tod, _season = self.world.current_calendar()
        if tod != "Morning":
            return False
        if month != int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_CHECK_MONTH", 6)):
            return False
        if day != int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_CHECK_DAY", 6)):
            return False
        if getattr(self.world, "last_adventurer_surplus_necromancer_check_year", None) == year:
            return False
        return True


    def _necromancer_origin_region(self):
        regions = list(getattr(self.world, "regions", {}).values())
        if not regions:
            return None
        evil_regions = []
        for region in regions:
            if getattr(region, "control", 0) < 0:
                evil_regions.append(region)
                continue
            ruler = self.world.actors.get(getattr(region, "ruler_id", None))
            if ruler is not None and getattr(ruler, "alive", False) and ruler.is_evil():
                evil_regions.append(region)
                continue
            polity = self.world.polities.get(getattr(region, "polity_id", None)) if hasattr(self.world, "polities") else None
            ruler = self.world.actors.get(getattr(polity, "ruler_id", None)) if polity is not None else None
            if ruler is not None and getattr(ruler, "alive", False) and ruler.is_evil():
                evil_regions.append(region)
        return self.rng.choice(evil_regions or regions)


    def _necromancer_title(self) -> str:
        titles = list(globals().get("ADVENTURER_SURPLUS_NECROMANCER_TITLES", [])) or ["She Who Counts the Dead"]
        used = set(getattr(self.world, "used_necromancer_titles", set()) or set())
        available = [title for title in titles if title not in used]
        if not available:
            available = titles
            used = set()
        title = self.rng.choice(available)
        used.add(title)
        self.world.used_necromancer_titles = used
        return title


    def _apply_necromancer_commoner_collateral(self, amount: int) -> int:
        world = self.world
        if amount <= 0 or not hasattr(world, "commoners_by_region"):
            return 0
        remaining = int(amount)
        killed = 0
        region_ids = [rid for rid, count in world.commoners_by_region.items() if int(count) > 0]
        self.rng.shuffle(region_ids)
        while remaining > 0 and region_ids:
            rid = region_ids.pop(0)
            current = int(world.commoners_by_region.get(rid, 0))
            if current <= 0:
                continue
            loss = min(current, max(1, min(remaining, int(round(current * 0.15)))))
            world.commoners_by_region[rid] = max(0, current - loss)
            remaining -= loss
            killed += loss
            if world.commoners_by_region.get(rid, 0) > 0 and remaining > 0:
                region_ids.append(rid)
        return killed


    def _necromancer_victim_batch(self, count: int) -> List[Actor]:
        adventurers = self._active_adventurers_for_necromancer_crisis()
        if count <= 0 or not adventurers:
            return []
        adventurers.sort(key=lambda a: (a.power_rating(), getattr(a, "level", 1), getattr(a, "reputation", 0), getattr(a, "max_hp", 1), getattr(a, "luck", 10), self.rng.random()))
        count = min(count, len(adventurers))
        q1 = max(1, len(adventurers) // 4)
        q3 = max(q1 + 1, (len(adventurers) * 3) // 4)
        pools = {"weak": adventurers[:q1], "mid": adventurers[q1:q3] or adventurers, "strong": adventurers[q3:] or adventurers}
        slots = ["weak"] * int(round(count * 0.75)) + ["mid"] * int(round(count * 0.20))
        while len(slots) < count:
            slots.append("strong")
        self.rng.shuffle(slots)
        victims = []
        used = set()
        for slot in slots:
            pool = [a for a in pools.get(slot, adventurers) if a.id not in used and a.alive]
            if not pool:
                pool = [a for a in adventurers if a.id not in used and a.alive]
            if not pool:
                break
            actor = pool[0] if slot == "weak" else self.rng.choice(pool)
            victims.append(actor)
            used.add(actor.id)
        return victims


    def _reward_necromancer_survivors(self, crisis: dict, final: bool = False) -> None:
        survivors = self._active_adventurers_for_necromancer_crisis()
        if not survivors:
            return
        survivors.sort(key=lambda a: (a.reputation, a.power_rating(), getattr(a, "level", 1), self.rng.random()), reverse=True)
        title = crisis.get("title", "the necromancer")
        for actor in survivors[:min(len(survivors), 3 if final else 2)]:
            actor.black_host_waves_survived = int(getattr(actor, "black_host_waves_survived", 0) or 0) + 1
            if final:
                actor.black_host_victories = int(getattr(actor, "black_host_victories", 0) or 0) + 1
            rep_gain = self.rng.randint(2, 5) if final else self.rng.randint(1, 3)
            try:
                self._change_actor_rep(actor, rep_gain)
            except Exception:
                actor.reputation += rep_gain
            if hasattr(actor, "gain_experience"):
                actor.gain_experience(75 if final else 35)
            current_title = getattr(actor, "title", None)
            if final and (current_title is None or str(current_title).startswith("First in Class of ")) and self.rng.random() < 0.50:
                self._grant_title(actor, self.rng.choice(["Ash-Walker", "Gravebreaker", "Host-Breaker", "Dawn Survivor"]))
            if hasattr(self, "_story_note"):
                self._story_note(actor, f"Survived the war against {title}'s undead host.")


    def _maybe_start_adventurer_surplus_necromancer_crisis(self) -> bool:
        world = self.world
        if not self._necromancer_crisis_should_check_today():
            return False
        year = world.current_calendar()[0]
        world.last_adventurer_surplus_necromancer_check_year = year
        if getattr(world, "adventurer_surplus_necromancer_crisis", None):
            return False
        cooldown_years = int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_COOLDOWN_YEARS", 10))
        last_year = getattr(world, "last_adventurer_surplus_necromancer_year", None)
        if last_year is not None and year - int(last_year) < cooldown_years:
            return False
        adventurers = self._active_adventurers_for_necromancer_crisis()
        commoners = sum(int(v) for v in getattr(world, "commoners_by_region", {}).values())
        # School children, retired adventurers, and other living actors count as population,
        # but not as active adventurers for surplus pressure.
        living_non_aggregate = len(world.living_actors())
        total = max(1, commoners + living_non_aggregate)
        current_ratio = len(adventurers) / total
        if current_ratio <= float(globals().get("ADVENTURER_SURPLUS_NECROMANCER_RATIO", 0.04)):
            return False
        if self.rng.random() >= float(globals().get("ADVENTURER_SURPLUS_NECROMANCER_CHANCE", 1.0)):
            world.log(f"Midsummer passes under a strained omen: adventurers make up {current_ratio * 100:.1f}% of the living population, but no grave-banner rises.", importance=2, category="necromancer_crisis_check")
            return False
        target_ratio = max(0.0, float(globals().get("ADVENTURER_SURPLUS_NECROMANCER_TARGET_RATIO", 0.04)))
        min_ratio = max(0.0, float(globals().get("ADVENTURER_SURPLUS_NECROMANCER_MIN_RATIO", 0.02)))
        target_survivors = max(int(total * target_ratio), int(total * min_ratio))
        target_survivors = min(target_survivors, len(adventurers))
        purge_needed = max(0, len(adventurers) - target_survivors)
        if purge_needed <= 0:
            return False
        origin = self._necromancer_origin_region()
        title = self._necromancer_title()
        collateral_total = int(total * max(0.0, float(globals().get("ADVENTURER_SURPLUS_NECROMANCER_COMMONER_COLLATERAL_RATE", 0.01))))
        world.adventurer_surplus_necromancer_crisis = {"active": True, "title": title, "origin_region_id": getattr(origin, "id", None), "started_tick": world.tick, "started_year": year, "starting_adventurers": len(adventurers), "starting_total": total, "target_adventurers": target_survivors, "initial_purge_needed": purge_needed, "remaining_purge": purge_needed, "purged": 0, "phase": "losing", "commoner_collateral_remaining": collateral_total, "commoner_collateral": 0, "last_pulse_tick": -999999}
        world.last_adventurer_surplus_necromancer_year = year
        origin_name = getattr(origin, "name", "an unnamed region")
        world.log(f"At midsummer, {title} rises from {origin_name} with a host of the dead. All adventurers are called beneath one banner, but the first marches go badly.", importance=5, category="necromancer_crisis")
        return True


    def _advance_adventurer_surplus_necromancer_crisis(self) -> bool:
        world = self.world
        crisis = getattr(world, "adventurer_surplus_necromancer_crisis", None)
        if not crisis or not crisis.get("active"):
            return False
        if world.tick - int(crisis.get("last_pulse_tick", -999999)) < TICKS_PER_MONTH:
            return False
        crisis["last_pulse_tick"] = world.tick
        remaining = int(crisis.get("remaining_purge", 0))
        if remaining <= 0:
            crisis["active"] = False
            world.adventurer_surplus_necromancer_crisis = None
            return False
        initial = max(1, int(crisis.get("initial_purge_needed", remaining)))
        fraction = max(0.01, float(globals().get("ADVENTURER_SURPLUS_NECROMANCER_MONTHLY_PURGE_FRACTION", 0.16)))
        min_kills = max(1, int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_MIN_MONTHLY_KILLS", 5)))
        pulse = min(remaining, max(min_kills, int(round(initial * fraction))))
        victims = self._necromancer_victim_batch(pulse)
        actual_dead = 0
        title = crisis.get("title", "the necromancer")
        for actor in victims:
            actor.death_killer_id = None
            actor.death_monster_id = None
            self._mark_actor_dead(actor, f"fell in the war against {title}'s undead host", importance=2)
            if not actor.alive:
                actual_dead += 1
        crisis["purged"] = int(crisis.get("purged", 0)) + actual_dead
        crisis["remaining_purge"] = max(0, int(crisis.get("remaining_purge", 0)) - actual_dead)
        collateral_remaining = int(crisis.get("commoner_collateral_remaining", 0))
        collateral_this_pulse = min(collateral_remaining, max(0, int(round(collateral_remaining * 0.25))))
        commoner_deaths = self._apply_necromancer_commoner_collateral(collateral_this_pulse)
        crisis["commoner_collateral_remaining"] = max(0, collateral_remaining - commoner_deaths)
        crisis["commoner_collateral"] = int(crisis.get("commoner_collateral", 0)) + commoner_deaths
        progress = crisis["purged"] / max(1, initial)
        if progress >= 0.50 and crisis.get("phase") == "losing":
            crisis["phase"] = "counterattack"
            self._reward_necromancer_survivors(crisis, final=False)
            world.log(f"After terrible losses, the living finally begin to push back against {title}. New heroes rise from the ash as the Black Host falters.", importance=5, category="necromancer_crisis")
        elif crisis.get("remaining_purge", 0) > 0:
            if crisis.get("phase") == "losing":
                world.log(f"The war against {title} is being lost. The adventurer host gives ground, and {actual_dead} more fall beneath the dead banners.", importance=4, category="necromancer_crisis")
            else:
                world.log(f"The allied host presses the counterattack against {title}. The undead line breaks in places, but {actual_dead} adventurers do not return.", importance=4, category="necromancer_crisis")
        if crisis.get("remaining_purge", 0) <= 0 or len(self._active_adventurers_for_necromancer_crisis()) <= int(crisis.get("target_adventurers", 0)):
            self._reward_necromancer_survivors(crisis, final=True)
            after_adventurers = len(self._active_adventurers_for_necromancer_crisis())
            after_commoners = sum(int(v) for v in getattr(world, "commoners_by_region", {}).values())
            after_living_non_aggregate = len(world.living_actors())
            after_total = max(1, after_commoners + after_living_non_aggregate)
            world.log(f"{title}'s host is broken at last. The necromancer is rumored destroyed, but her remains have vanished. {crisis.get('purged', 0)} adventurers fell; {crisis.get('commoner_collateral', 0)} commoners died in the terror. Adventurers now stand at {(after_adventurers / after_total) * 100:.1f}% of the living population.", importance=5, category="necromancer_crisis")
            crisis["active"] = False
            world.adventurer_surplus_necromancer_crisis = None
        if hasattr(world, "cleanup_parties"):
            world.cleanup_parties()
        if hasattr(self, "_rebuild_world_caches"):
            self._rebuild_world_caches()
        return True


    def _maybe_spawn_horror_for_adventurer_surplus(self) -> bool:
        """Legacy compatibility wrapper. Surplus is now handled by the necromancer crisis."""
        return self._maybe_start_adventurer_surplus_necromancer_crisis()


    def _monster_spawn_check(self) -> None:
        if self._monster_grace_active():
            return
        world = self.world
        # Ancient horrors use calendar-gated omen/summon days, not monthly random spawning.
        if world.tick % TICKS_PER_DAY == 0 and self._recovery_state() != 'crisis' and self._maybe_spawn_horror_for_dominance():
            return
        if world.tick % TICKS_PER_TENDAY != 0:
            return
        spawn_scale = self._monster_spawn_scale()
        if spawn_scale <= 0:
            return
        if (not self._dragon_spawn_suppressed_by_dormancy()) and self._recovery_state() != 'crisis' and self._maybe_spawn_dragon_for_polities():
            return
        region_id = self._weighted_monster_spawn_region_id()
        roll = self.rng.random() / max(0.01, spawn_scale)
        new_monster: Optional[Monster] = None
        if roll < 0.20:
            new_monster = self._make_goblin(region_id)
        elif roll < 0.225:
            giants = [m for m in world.living_monsters() if m.kind == MonsterKind.GIANT]
            if len(giants) < MAX_WILD_GIANTS:
                new_monster = self._make_giant(region_id)
        elif roll < 0.228 and not self._dragon_spawn_suppressed_by_dormancy():
            dragons = [m for m in world.living_monsters() if m.kind == MonsterKind.DRAGON]
            if len(dragons) < MAX_WILD_DRAGONS:
                new_monster = self._make_dragon(region_id)
        if new_monster is not None:
            if hasattr(world, "register_monster"):
                world.register_monster(new_monster)
            else:
                world.monsters[new_monster.id] = new_monster
            world.generated_monsters_by_kind[new_monster.kind] += 1
            if new_monster.kind != MonsterKind.GOBLIN:
                world.log(f"Rumors spread of a {new_monster.name} appearing near {world.region_name(region_id)}.", importance=2, category="monster_spawn")



    def _large_evil_army_in_region(self, region_id: int):
        world = self.world
        candidates = []
        for party in list(getattr(world, "parties", {}).values()):
            if getattr(party, "goal", "") != "military" or not getattr(party, "member_ids", None):
                continue
            members = [world.actors[mid] for mid in party.member_ids if mid in world.actors and world.actors[mid].alive]
            if len(members) < 12:
                continue
            leader = world.actors.get(getattr(party, "leader_id", None))
            if leader is None or leader.region_id != region_id:
                continue
            evil_count = len([a for a in members if a.is_evil()])
            if leader.is_evil() or evil_count >= max(4, len(members) // 2):
                candidates.append((len(members) + evil_count, party, leader))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0]


    def _evil_giant_follow_army(self, monster: Monster) -> bool:
        if not self._giant_is_evil_aligned(monster):
            return False
        world = self.world
        attached_id = getattr(monster, "attached_party_id", None)
        if attached_id is not None:
            party = world.parties.get(attached_id)
            leader = world.actors.get(getattr(party, "leader_id", None)) if party is not None else None
            if party is not None and leader is not None and leader.alive:
                world.move_monster(monster, leader.region_id) if hasattr(world, "move_monster") else setattr(monster, "region_id", leader.region_id)
                if self.rng.random() < 0.08:
                    monster.monster_xp = getattr(monster, "monster_xp", 0) + 1
                return True
            monster.attached_party_id = None
        army = self._large_evil_army_in_region(monster.region_id)
        if army is None:
            return False
        _score, party, leader = army
        if self.rng.random() < 0.18:
            monster.attached_party_id = party.id
            world.log(
                f"{monster.name} is drawn to the marching ruin of {party.name or 'an evil army'} under {leader.short_name()}.",
                importance=2,
                category="giant_warhost",
            )
            return True
        return False


    def _try_ambivalent_dragon_bargain(self, monster: Monster) -> bool:
        if monster.kind != MonsterKind.DRAGON:
            return False
        if getattr(monster, "dragon_temperament", "malevolent") != "ambivalent":
            return False
        world = self.world
        patron = world.actors.get(getattr(monster, "patron_actor_id", None)) if getattr(monster, "patron_actor_id", None) is not None else None
        if patron is not None and patron.alive and patron.is_evil():
            if self.rng.random() < 0.16:
                world.move_monster(monster, patron.region_id) if hasattr(world, "move_monster") else setattr(monster, "region_id", patron.region_id)
            return True
        candidates = self._evil_monster_patron_candidates(monster.region_id, min_rep=35, min_charisma=13)
        candidates = [a for a in candidates if getattr(a, "intelligence", 0) >= 11 or getattr(a, "reputation", 0) >= 60]
        if not candidates or self.rng.random() >= 0.08:
            return False
        leader = max(candidates, key=lambda a: (a.reputation, a.charisma, a.intelligence, a.luck))
        monster.patron_actor_id = leader.id
        monster.patron_deity = leader.deity
        monster.monster_xp = getattr(monster, "monster_xp", 0) + 1
        leader.reputation += 2
        self.world.log(
            f"{leader.short_name()} strikes a dangerous bargain with {monster.name}; neither side mistakes it for loyalty.",
            importance=3,
            category="dragon_bargain",
        )
        return True


    def _try_horror_pact(self, monster: Monster) -> bool:
        if monster.kind != MonsterKind.ANCIENT_HORROR:
            return False
        world = self.world
        # Ancient horrors are never controlled. Only evil wizards may risk a pact.
        candidates = [
            a for a in world.actors_in_region(monster.region_id)
            if a.alive and a.is_evil() and a.role == Role.WIZARD and not getattr(a, "retired", False)
            and getattr(a, "reputation", 0) >= 18
        ]
        if not candidates or self.rng.random() >= 0.035:
            return False
        wizard = max(candidates, key=lambda a: (a.reputation, a.intelligence, a.wisdom, a.luck))
        pact_score = wizard.reputation + wizard.intelligence * 2 + wizard.wisdom + wizard.luck + self.rng.randint(1, 40)
        horror_score = monster.effective_power() + 35 + self.rng.randint(1, 50)
        if pact_score >= horror_score:
            monster.patron_actor_id = wizard.id
            monster.patron_deity = wizard.deity
            wizard.reputation += 6
            wizard.experience = getattr(wizard, "experience", 0) + 250
            if hasattr(wizard, "sync_progression"):
                wizard.sync_progression()
            world.adjust_region_state(monster.region_id, control_delta=-4, order_delta=-8)
            world.log(
                f"{wizard.short_name()} survives a pact with {monster.name}; the bargain poisons {world.region_name(monster.region_id)} but leaves the horror free.",
                importance=3,
                category="horror_pact",
            )
            return True

        # Failed pact: the horror rampages, and the wizard has a hard but real escape chance.
        escape_score = wizard.luck + wizard.wisdom + wizard.dexterity + self.rng.randint(1, 30)
        escape_target = 48 + max(0, monster.effective_power() // 3)
        if escape_score < escape_target:
            wizard.death_monster_id = monster.id
            self._mark_actor_dead(wizard, f"failed pact with {monster.name}", importance=3)
            monster.monster_kills_adventurers = getattr(monster, "monster_kills_adventurers", 0) + 1
            outcome = "is consumed by the failed bargain"
        else:
            wizard.hp = max(1, wizard.hp - self.rng.randint(1, max(2, wizard.max_hp // 2)))
            wizard.recovering = max(getattr(wizard, "recovering", 0), self.rng.randint(8, 24))
            wizard.reputation = max(0, wizard.reputation - 4)
            outcome = "escapes the failed bargain, broken but alive"
        commoners = int(getattr(world, "commoners_by_region", {}).get(monster.region_id, 0)) if hasattr(world, "commoners_by_region") else 0
        deaths = min(commoners, self.rng.randint(8, 35)) if commoners > 0 else 0
        if deaths > 0:
            world.commoners_by_region[monster.region_id] = max(0, commoners - deaths)
            self._remove_commoner_deaths(monster.region_id, deaths, cause="failed horror pact")
        world.adjust_region_state(monster.region_id, control_delta=-8, order_delta=-15)
        monster.monster_xp = getattr(monster, "monster_xp", 0) + 3
        world.log(
            f"{wizard.short_name()} attempts a pact with {monster.name} and {outcome}; the horror rampages through {world.region_name(monster.region_id)}.",
            importance=3,
            category="horror_pact_failed",
        )
        return True


    def _dragon_giant_rival_kind(self, monster: Monster):
        if monster.kind == MonsterKind.DRAGON:
            return MonsterKind.GIANT
        if monster.kind == MonsterKind.GIANT:
            return MonsterKind.DRAGON
        return None


    def _dragon_giant_rival_candidates(self, monster: Monster, *, same_region: bool) -> List[Monster]:
        rival_kind = self._dragon_giant_rival_kind(monster)
        if rival_kind is None:
            return []
        world = self.world
        region = world.regions.get(getattr(monster, "region_id", None))
        if region is None:
            return []
        region_ids = {monster.region_id} if same_region else set(getattr(region, "neighbors", []) or [])
        rivals: List[Monster] = []
        for rival in world.living_monsters():
            if getattr(rival, "id", None) == getattr(monster, "id", None):
                continue
            if not getattr(rival, "alive", False) or getattr(rival, "kind", None) != rival_kind:
                continue
            if rival.kind == MonsterKind.DRAGON and bool(getattr(rival, "dormant", False)):
                continue
            if getattr(rival, "region_id", None) in region_ids:
                rivals.append(rival)
        rivals.sort(key=lambda m: (m.effective_power(), getattr(m, "monster_xp", 0), self.rng.random()), reverse=True)
        return rivals


    def _dragon_giant_rival_move(self, monster: Monster, rival: Monster) -> bool:
        world = self.world
        old_region = getattr(monster, "region_id", None)
        target_region = getattr(rival, "region_id", None)
        if old_region is None or target_region is None or old_region == target_region:
            return False
        region = world.regions.get(old_region)
        if region is None or target_region not in (getattr(region, "neighbors", []) or []):
            return False
        world.move_monster(monster, target_region) if hasattr(world, "move_monster") else setattr(monster, "region_id", target_region)
        cooldown = max(1, int(globals().get("DRAGON_GIANT_RIVALRY_COOLDOWN_TICKS", TICKS_PER_TENDAY)))
        monster.retreat_until_tick = max(getattr(monster, "retreat_until_tick", -1), world.tick + max(1, cooldown // 2))
        self._mark_monster_moved(monster)
        world.log(
            f"{monster.name} abandons other prey and moves from {world.region_name(old_region)} toward {rival.name} in {world.region_name(target_region)}.",
            importance=2,
            category="monster_rivalry",
        )
        return True


    def _apply_dragon_giant_rivalry_collateral(self, region_id: int) -> int:
        world = self.world
        order_damage = max(0, int(globals().get("DRAGON_GIANT_RIVALRY_ORDER_DAMAGE", 2)))
        if order_damage:
            world.adjust_region_state(region_id, control_delta=0, order_delta=-order_damage)
        commoners = int(getattr(world, "commoners_by_region", {}).get(region_id, 0)) if hasattr(world, "commoners_by_region") else 0
        if commoners <= 0:
            return 0
        rate = max(0.0, float(globals().get("DRAGON_GIANT_RIVALRY_COLLATERAL_COMMONER_RATE", 0.01)))
        deaths = min(commoners, max(0, self._stochastic_round(commoners * rate)))
        if deaths <= 0:
            return 0
        world.commoners_by_region[region_id] = max(0, commoners - deaths)
        if hasattr(self, "_remove_commoner_deaths"):
            self._remove_commoner_deaths(region_id, deaths, cause="dragon-giant rivalry")
        return deaths


    def _resolve_dragon_giant_rivalry(self, monster: Monster, rival: Monster) -> bool:
        if not getattr(monster, "alive", False) or not getattr(rival, "alive", False):
            return False
        if monster.kind not in (MonsterKind.DRAGON, MonsterKind.GIANT):
            return False
        if rival.kind not in (MonsterKind.DRAGON, MonsterKind.GIANT) or monster.kind == rival.kind:
            return False
        if getattr(monster, "region_id", None) != getattr(rival, "region_id", None):
            return False
        if self._monster_acted_this_tick(monster) or self._monster_acted_this_tick(rival):
            return False

        world = self.world
        region_id = monster.region_id
        monster_score = monster.effective_power() + self.rng.randint(1, 20)
        rival_score = rival.effective_power() + self.rng.randint(1, 20)
        if monster_score == rival_score:
            monster_score += self.rng.random()
        winner, loser = (monster, rival) if monster_score > rival_score else (rival, monster)
        winning_score = max(monster_score, rival_score)
        losing_score = max(1, min(monster_score, rival_score))

        self._mark_monster_acted(winner)
        self._mark_monster_acted(loser)
        winner.monster_battles_won = int(getattr(winner, "monster_battles_won", 0) or 0) + 1
        loser.monster_battles_lost = int(getattr(loser, "monster_battles_lost", 0) or 0) + 1
        winner.monster_xp = int(getattr(winner, "monster_xp", 0) or 0) + max(0, int(globals().get("DRAGON_GIANT_RIVALRY_WINNER_XP", 3)))
        if hasattr(self, "_mark_monster_terror_region"):
            self._mark_monster_terror_region(winner, region_id)
            self._mark_monster_terror_region(loser, region_id)

        collateral = self._apply_dragon_giant_rivalry_collateral(region_id)
        cooldown = max(1, int(globals().get("DRAGON_GIANT_RIVALRY_COOLDOWN_TICKS", TICKS_PER_TENDAY)))
        winner.retreat_until_tick = max(getattr(winner, "retreat_until_tick", -1), world.tick + cooldown)
        loser.retreat_until_tick = max(getattr(loser, "retreat_until_tick", -1), world.tick + cooldown)

        base_death = max(0.0, float(globals().get("DRAGON_GIANT_RIVALRY_LOSER_DEATH_BASE", 0.15)))
        power_gap_bonus = min(0.20, max(0.0, (winning_score - losing_score) / losing_score) * 0.15)
        death_chance = min(0.75, base_death + power_gap_bonus)
        if self.rng.random() < death_chance:
            loser.alive = False
            if hasattr(world, "kill_monster_cache_update"):
                world.kill_monster_cache_update(loser)
            collateral_text = f"; {collateral} commoners die in the devastation" if collateral > 0 else ""
            world.log(
                f"{winner.name} destroys {loser.name} in {world.region_name(region_id)} as the ancient hatred of dragon and giant erupts{collateral_text}.",
                importance=3,
                category="monster_rivalry",
            )
            return True

        retreated = False
        if self.rng.random() < max(0.0, float(globals().get("DRAGON_GIANT_RIVALRY_LOSER_RETREAT_CHANCE", 0.60))):
            retreated = self._monster_retreat(loser)
        if not retreated:
            loser.monster_xp = max(0, int(getattr(loser, "monster_xp", 0) or 0) - 1)
        collateral_text = f", killing {collateral} commoners in the chaos" if collateral > 0 else ""
        outcome = "drives it from the field" if retreated else "leaves it wounded and wary"
        world.log(
            f"{winner.name} clashes with {loser.name} in {world.region_name(region_id)} and {outcome}{collateral_text}.",
            importance=2,
            category="monster_rivalry",
        )
        return True


    def _try_dragon_giant_rivalry(self, monster: Monster) -> bool:
        if not bool(globals().get("DRAGON_GIANT_RIVALRY_ENABLED", True)):
            return False
        if monster.kind not in (MonsterKind.DRAGON, MonsterKind.GIANT):
            return False
        if monster.kind == MonsterKind.DRAGON and bool(getattr(monster, "dormant", False)):
            return False
        world = self.world
        interval = max(1, int(globals().get("DRAGON_GIANT_RIVALRY_CHECK_TICKS", TICKS_PER_TENDAY)))
        last_key = "last_dragon_giant_rivalry_tick"
        if world.tick - int(getattr(monster, last_key, -999999)) < interval:
            return False

        same_region = self._dragon_giant_rival_candidates(monster, same_region=True)
        if same_region:
            setattr(monster, last_key, world.tick)
            if self.rng.random() < max(0.0, float(globals().get("DRAGON_GIANT_RIVALRY_SAME_REGION_CHANCE", 0.85))):
                return self._resolve_dragon_giant_rivalry(monster, same_region[0])
            return False

        neighboring = self._dragon_giant_rival_candidates(monster, same_region=False)
        if neighboring and self.rng.random() < max(0.0, float(globals().get("DRAGON_GIANT_RIVALRY_NEIGHBOR_SEEK_CHANCE", 0.35))):
            setattr(monster, last_key, world.tick)
            return self._dragon_giant_rival_move(monster, neighboring[0])
        return False

    def _monster_turn(self, monster: Monster) -> None:
        if self._monster_grace_active():
            return
        world = self.world
        if getattr(monster, "retreat_until_tick", -1) > world.tick:
            return
        if monster.kind == MonsterKind.DRAGON and self._update_dragon_dormancy(monster):
            return
        # Dragon/giant hatred is species-level and runs before human-facing
        # temperament rules. Neutral giants still hate dragons; benevolent
        # dragons still hate giants.
        if self._try_dragon_giant_rivalry(monster):
            return
        if not getattr(monster, "alive", False):
            return
        if self._giant_is_neutral(monster):
            self._neutral_giant_turn(monster)
            return
        if monster.kind == MonsterKind.GOBLIN:
            self._goblin_turn(monster)
            return
        if self._giant_is_evil_aligned(monster):
            # Stone/Frost giants are not allies or pact creatures. They may
            # drift with large evil armies because power and destruction attract them.
            self._evil_giant_follow_army(monster)
        if monster.kind == MonsterKind.DRAGON:
            dragons = [m for m in world.living_monsters() if m.kind == MonsterKind.DRAGON]
            if (not self._dragon_spawn_suppressed_by_dormancy()) and len(dragons) < MAX_WILD_DRAGONS and self.rng.random() < DRAGON_REPRO_CHANCE:
                baby = self._make_dragon(monster.region_id)
                if hasattr(world, "register_monster"):
                    world.register_monster(baby)
                else:
                    world.monsters[baby.id] = baby
                world.generated_monsters_by_kind[baby.kind] += 1
            self._try_ambivalent_dragon_bargain(monster)
        if monster.kind == MonsterKind.ANCIENT_HORROR:
            if self._try_horror_pact(monster):
                return
        if monster.kind != MonsterKind.ANCIENT_HORROR and self.rng.random() < 0.18:
            region = world.regions[monster.region_id]
            if region.neighbors:
                world.move_monster(monster, self.rng.choice(region.neighbors)) if hasattr(world, "move_monster") else setattr(monster, "region_id", self.rng.choice(region.neighbors))
        locals_ = world.actors_in_region(monster.region_id)
        aggression = 0.10 * self._monster_spawn_scale()
        aggression += min(0.08, self._monster_strength_bonus(monster) * 0.004)
        commoners = world.commoners_by_region.get(monster.region_id, 0) if hasattr(world, 'commoners_by_region') else 0
        if commoners > 0 and monster.kind in (MonsterKind.GOBLIN, MonsterKind.GIANT, MonsterKind.DRAGON) and not self._giant_is_neutral(monster):
            raid_rate = MONSTER_COMMONER_RAID_BASE + self._monster_strength_bonus(monster) * MONSTER_COMMONER_RAID_SCALE
            if monster.kind == MonsterKind.DRAGON:
                raid_rate += globals().get("DRAGON_RAID_RATE_BONUS", 0.01)
            elif monster.kind == MonsterKind.ANCIENT_HORROR:
                raid_rate += 0.02
            if self.rng.random() < min(0.35, raid_rate):
                loss = 0
                if monster.kind == MonsterKind.GOBLIN:
                    loss = self.rng.randint(1, max(2, monster.horde_size))
                elif monster.kind == MonsterKind.GIANT:
                    loss = self.rng.randint(4, 14 + self._monster_strength_bonus(monster))
                elif monster.kind == MonsterKind.DRAGON:
                    loss = self.rng.randint(12, 40 + self._monster_strength_bonus(monster) * 2)
                else:
                    loss = self.rng.randint(20, 60 + self._monster_strength_bonus(monster) * 3)
                terror = min(commoners, loss)
                if terror > 0:
                    # Split rampage impact into actual deaths and displacement.
                    # The previous aggregate behavior counted every scattered
                    # commoner as dead, creating mass extinction via
                    # "uncategorized aggregate loss."
                    if monster.kind == MonsterKind.GOBLIN:
                        death_fraction = 0.10
                    elif monster.kind == MonsterKind.GIANT:
                        death_fraction = 0.15
                    elif monster.kind == MonsterKind.DRAGON:
                        death_fraction = globals().get("DRAGON_COMMONER_DEATH_FRACTION", 0.20)
                    else:
                        death_fraction = 0.55
                    death_fraction *= MONSTER_COMMONER_DEATH_MULTIPLIER
                    deaths = min(terror, max(1, self._stochastic_round(terror * death_fraction)))
                    # Displacement is now driven by visible deaths, not by the full
                    # terror roll. This keeps raids disruptive without turning
                    # every dragon pass into a continent-scale leaf blower.
                    kind_key = getattr(monster.kind, "value", str(monster.kind))
                    scatter_ranges = globals().get("MONSTER_SCATTER_MULTIPLIER_BY_KIND", {}) or {}
                    scatter_caps = globals().get("MONSTER_SCATTER_CAP_BY_KIND", {}) or {}
                    lo, hi = scatter_ranges.get(kind_key, (5, 20))
                    try:
                        lo = int(lo); hi = int(hi)
                    except Exception:
                        lo, hi = 5, 20
                    if hi < lo:
                        lo, hi = hi, lo
                    scatter_multiplier = self.rng.randint(max(0, lo), max(0, hi)) if hi > 0 else 0
                    raw_scattered = max(0, int(deaths) * scatter_multiplier)
                    scatter_cap = scatter_caps.get(kind_key, None)
                    if scatter_cap is not None:
                        try:
                            raw_scattered = min(raw_scattered, max(0, int(scatter_cap)))
                        except Exception:
                            pass
                    scattered = min(max(0, commoners - deaths), raw_scattered)
                    world.commoners_by_region[monster.region_id] = max(0, commoners - deaths - scattered)
                    if scattered > 0:
                        region = world.regions.get(monster.region_id)
                        destinations = list(getattr(region, 'neighbors', []) or []) if region is not None else []
                        if destinations:
                            for _ in range(scattered):
                                dest = self.rng.choice(destinations)
                                world.commoners_by_region[dest] = world.commoners_by_region.get(dest, 0) + 1
                                if hasattr(self, '_shift_commoner_faith'):
                                    self._shift_commoner_faith(monster.region_id, dest, 1)
                                if hasattr(self, '_shift_commoner_demographics'):
                                    self._shift_commoner_demographics(monster.region_id, dest, 1)
                        else:
                            world.commoners_by_region[monster.region_id] += scattered
                            scattered = 0
                    self._remove_commoner_deaths(monster.region_id, deaths, cause=f"monster raid: {monster.kind.value}")
                    monster.monster_raids = getattr(monster, "monster_raids", 0) + 1
                    monster.monster_kills_commoners = getattr(monster, "monster_kills_commoners", 0) + int(deaths)
                    monster.monster_scattered_commoners = getattr(monster, "monster_scattered_commoners", 0) + int(scattered)
                    monster.monster_xp = getattr(monster, 'monster_xp', 0) + max(1, deaths // 5)
                    world.adjust_region_state(monster.region_id, control_delta=-2, order_delta=-(2 + min(8, terror // 8)))
                    if scattered > 0:
                        self._mark_monster_terror_region(monster, monster.region_id)
                        world.log(f"{monster.name} terrorizes {world.region_name(monster.region_id)}, killing {deaths} commoners and scattering {scattered} more.", importance=2, category="monster_attack")
                    else:
                        self._mark_monster_terror_region(monster, monster.region_id)
                        world.log(f"{monster.name} terrorizes {world.region_name(monster.region_id)}, killing {deaths} commoners.", importance=2, category="monster_attack")
                    if monster.kind != MonsterKind.ANCIENT_HORROR and self.rng.random() < 0.65:
                        self._monster_retreat(monster)
                    return
        if monster.kind == MonsterKind.DRAGON:
            temperament = getattr(monster, "dragon_temperament", "malevolent")
            if temperament == "benevolent":
                targets = [a for a in locals_ if a.alive and a.is_evil()]
                if targets and self.rng.random() < 0.20:
                    target = self.rng.choice(targets)
                    if self.rng.random() < 0.35:
                        target.death_monster_id = monster.id
                        self._mark_actor_dead(target, f"judgment of {monster.name}", importance=2)
                        target.death_killer_id = None
                        monster.monster_kills_adventurers = getattr(monster, "monster_kills_adventurers", 0) + 1
                        monster.monster_xp = getattr(monster, "monster_xp", 0) + 2
                        world.log(f"{monster.name} descends on {target.short_name()} in {world.region_name(monster.region_id)}.", importance=2, category="dragon_judgment")
                    else:
                        target.recovering = max(target.recovering, 3)
                        monster.monster_xp = getattr(monster, "monster_xp", 0) + 1
                    world.adjust_region_state(monster.region_id, control_delta=1, order_delta=1)
                return
            if temperament == "ambivalent":
                rich_region = getattr(world, "commoners_by_region", {}).get(monster.region_id, 0) >= 700
                targets = [a for a in locals_ if a.alive and a.is_evil()]
                if targets and self.rng.random() < 0.15:
                    target = self.rng.choice(targets)
                    if self.rng.random() < 0.28:
                        target.death_monster_id = monster.id
                        self._mark_actor_dead(target, f"wrath of {monster.name}", importance=2)
                        monster.monster_kills_adventurers = getattr(monster, "monster_kills_adventurers", 0) + 1
                        monster.monster_xp = getattr(monster, "monster_xp", 0) + 2
                    else:
                        target.recovering = max(target.recovering, 2)
                        monster.monster_xp = getattr(monster, "monster_xp", 0) + 1
                    world.adjust_region_state(monster.region_id, control_delta=1, order_delta=0)
                    return
                if not rich_region:
                    return

        if monster.kind in (MonsterKind.DRAGON, MonsterKind.GIANT, MonsterKind.ANCIENT_HORROR) and locals_ and self.rng.random() < aggression:
            if monster.kind == MonsterKind.ANCIENT_HORROR:
                hostile_targets = [a for a in locals_ if a.alive and a.is_adventurer() and a.id != getattr(monster, "patron_actor_id", None)]
            elif monster.kind == MonsterKind.DRAGON:
                hostile_targets = [a for a in locals_ if a.alive and self._monster_hostile_to_actor(monster, a)]
            else:
                hostile_targets = [a for a in locals_ if a.alive]
            if not hostile_targets:
                return
            strongest_group = max((world.side_power(a) for a in hostile_targets), default=0)
            if strongest_group >= monster.effective_power() * MONSTER_RETREAT_AVOID_RATIO and monster.kind != MonsterKind.ANCIENT_HORROR:
                self._monster_retreat(monster)
                return
            victims = self.rng.sample(hostile_targets, k=min(len(hostile_targets), self.rng.randint(1, 3)))
            deaths = 0
            for victim in victims:
                if self.rng.random() < 0.30:
                    victim.death_monster_id = monster.id
                    self._mark_actor_dead(victim, f"monster attack by {monster.name}")
                    deaths += 1
                else:
                    victim.recovering = max(victim.recovering, 2)
            monster.monster_raids = getattr(monster, "monster_raids", 0) + 1
            monster.monster_kills_adventurers = getattr(monster, "monster_kills_adventurers", 0) + int(deaths)
            monster.monster_xp = getattr(monster, "monster_xp", 0) + max(1, deaths + len(victims))
            world.adjust_region_state(monster.region_id, control_delta=-2, order_delta=-3)
            self._mark_monster_terror_region(monster, monster.region_id)
            world.log(f"{monster.name} brings ruin to {world.region_name(monster.region_id)}, leaving {deaths} dead.", importance=2, category="monster_attack")
            if monster.kind != MonsterKind.ANCIENT_HORROR and self.rng.random() < 0.35:
                self._monster_retreat(monster)


    def _goblin_turn(self, monster: Monster) -> None:
        world = self.world
        if monster.patron_actor_id is not None:
            patron = world.actors.get(monster.patron_actor_id)
            if patron and patron.alive:
                monster.patron_deity = patron.deity
                world.move_monster(monster, patron.region_id) if hasattr(world, "move_monster") else setattr(monster, "region_id", patron.region_id)
                if self.rng.random() < 0.30:
                    monster.horde_size += 1
                return
            monster.patron_actor_id = None
        evil_leaders = self._evil_monster_patron_candidates(monster.region_id, min_rep=8, min_charisma=12)
        if evil_leaders and self.rng.random() < 0.30:
            leader = max(evil_leaders, key=lambda a: (a.reputation, a.charisma))
            self._bind_monster_to_evil_patron(monster, leader, category="goblin_loyalty")
            return
        if self.rng.random() < 0.25:
            region = world.regions[monster.region_id]
            if region.neighbors:
                world.move_monster(monster, self.rng.choice(region.neighbors)) if hasattr(world, "move_monster") else setattr(monster, "region_id", self.rng.choice(region.neighbors))
        locals_ = world.actors_in_region(monster.region_id)
        raid_chance = 0.30 * self._monster_spawn_scale()
        if locals_ and self.rng.random() < raid_chance:
            commoners = [actor for actor in locals_ if actor.role == Role.COMMONER and not getattr(actor, "in_school", False)]
            if commoners:
                losses = min(len(commoners), self.rng.randint(0, 2))
                if losses > 0:
                    victims = self.rng.sample(commoners, k=losses)
                    for victim in victims:
                        victim.death_monster_id = monster.id
                        self._mark_actor_dead(victim, f"goblin raid by {monster.name}")
                if self.rng.random() < 0.35:
                    monster.horde_size += 1
                world.adjust_region_state(monster.region_id, control_delta=-2, order_delta=-2)
                world.log(f"{monster.name} raids {world.region_name(monster.region_id)} with {monster.horde_size} goblins at its back.", importance=2, category="goblin_raid")



    def _monster_deity_contributions(self) -> Dict[object, int]:
        """Influence support from evil-bound goblins.

        Giants can be drawn to evil armies, but they are not counted as loyal
        followers. Dragons and ancient horrors are bargains/omens, not flock.
        """
        support: Dict[object, int] = {}
        world = self.world
        for monster in world.living_monsters():
            if monster.kind != MonsterKind.GOBLIN:
                continue
            deity = getattr(monster, "patron_deity", None)
            if deity is None and getattr(monster, "patron_actor_id", None) is not None:
                patron = world.actors.get(monster.patron_actor_id)
                if patron is not None and patron.alive and patron.is_evil():
                    deity = patron.deity
                    monster.patron_deity = deity
            if deity is None:
                continue
            value = max(1, int(getattr(monster, "horde_size", 1)))
            support[deity] = support.get(deity, 0) + value
        return support


    def _hunt_monsters(self, actor: Actor) -> bool:
        world = self.world
        monsters = [
            monster for monster in world.monsters_in_region(actor.region_id)
            if monster.alive
            and not self._monster_acted_this_tick(monster)
            and getattr(monster, "retreat_until_tick", -1) <= world.tick
        ]
        if not monsters:
            return False
        if actor.is_good() or actor.reputation >= 8:
            hostile_monsters = [m for m in monsters if self._monster_hostile_to_actor(m, actor)]
            if not hostile_monsters:
                return False
            target = max(hostile_monsters, key=lambda m: m.effective_power())
            if target.kind == MonsterKind.DRAGON:
                party = world.get_party(actor)
                party_size = len(party.member_ids) if party else 1
                if actor.reputation < 12 and party_size < 3 and actor.mind_score() >= 10:
                    return False
            return self._resolve_monster_battle(actor, target)
        return False


    def _monster_slayer_member_ids(self, slayer: Actor) -> list[int]:
        world = self.world
        party = world.get_party(slayer)
        member_ids = [slayer.id]
        if party is not None:
            for mid in party.member_ids:
                member = world.actors.get(mid)
                if member is not None and member.alive and member.is_adventurer() and mid not in member_ids:
                    member_ids.append(mid)
        if len(member_ids) < PARTY_FOUNDING_MIN_MEMBERS:
            locals_ = [a for a in world.actors_in_region(slayer.region_id) if a.alive and a.is_adventurer() and a.id not in member_ids]
            locals_.sort(key=lambda a: (a.reputation, a.power_rating(), a.charisma, a.luck), reverse=True)
            for other in locals_:
                if len(member_ids) >= max(PARTY_FOUNDING_MIN_MEMBERS, 6):
                    break
                member_ids.append(other.id)
        return member_ids

    def _elevate_monster_slayer(self, slayer: Actor, monster: Monster) -> None:
        world = self.world
        region = world.regions[slayer.region_id]
        commoners = getattr(world, 'commoners_by_region', {}).get(region.id, 0)
        gratitude = 1 + min(18, commoners // 40)
        if monster.kind == MonsterKind.DRAGON:
            gratitude += 6
        elif monster.kind == MonsterKind.GIANT:
            gratitude += 3
        elif monster.kind == MonsterKind.ANCIENT_HORROR:
            gratitude += 12
        slayer.reputation += gratitude
        region_control_boost = 3 if monster.kind == MonsterKind.GIANT else 5 if monster.kind == MonsterKind.DRAGON else 8 if monster.kind == MonsterKind.ANCIENT_HORROR else 1
        world.adjust_region_state(region.id, control_delta=region_control_boost if not slayer.is_evil() else -region_control_boost, order_delta=2 + region_control_boost)

        if monster.kind not in (MonsterKind.GIANT, MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR):
            return

        if getattr(region, 'polity_id', None) is None:
            chance = 0.20
            if monster.kind == MonsterKind.GIANT:
                chance = 0.35
            elif monster.kind == MonsterKind.DRAGON:
                chance = 0.60
            elif monster.kind == MonsterKind.ANCIENT_HORROR:
                chance = 1.00
            if commoners >= 100:
                chance += 0.15
            if region.order < 50:
                chance += 0.10
            if self.rng.random() < min(1.0, chance):
                member_ids = self._monster_slayer_member_ids(slayer)
                polity = world.create_polity(slayer, region.id, member_ids)
                if polity is not None:
                    polity.stability = 15 if monster.kind == MonsterKind.GIANT else 22 if monster.kind == MonsterKind.DRAGON else 28
                    polity.legitimacy = max(polity.legitimacy, 35 + min(45, gratitude))
                    world.log(f"The people of {world.region_name(region.id)} raise {slayer.full_name()} to the throne after the fall of {monster.name}.", importance=3, category='polity')
            return

        polity = world.polities.get(region.polity_id) if hasattr(world, 'polities') else None
        if polity is None:
            return
        ruler = world.actors.get(polity.ruler_id) if polity.ruler_id is not None else None
        slayer.polity_id = polity.id
        slayer.loyalty = None
        slayer.polity_favor = min(getattr(slayer, 'polity_favor', 50), -40)
        polity.stability = max(0, polity.stability - (6 if monster.kind == MonsterKind.GIANT else 10 if monster.kind == MonsterKind.DRAGON else 16))
        world.adjust_region_state(region.id, control_delta=-3 if slayer.is_evil() else 0, order_delta=-2)
        if ruler is not None and ruler.id != slayer.id:
            if hasattr(self, '_register_nemesis'):
                self._register_nemesis(slayer, ruler)
                self._register_nemesis(ruler, slayer)
            world.log(f"The fall of {monster.name} makes {slayer.full_name()} a threat to the rule of {polity.name} in {world.region_name(region.id)}.", importance=3, category='polity')


    def _mark_monster_terror_region(self, monster: Monster, region_id: int | None = None) -> None:
        if monster is None or getattr(monster, "kind", None) == MonsterKind.GOBLIN:
            return
        rid = getattr(monster, "region_id", None) if region_id is None else region_id
        if rid is None:
            return
        if not hasattr(monster, "terror_region_ids") or getattr(monster, "terror_region_ids", None) is None:
            monster.terror_region_ids = set()
        try:
            monster.terror_region_ids.add(int(rid))
        except Exception:
            pass

    def _is_organized_eradication_attempt(self, actor: Actor, monster: Monster, side_power: float, monster_power: float, party_size: int) -> bool:
        if monster is None or getattr(monster, "kind", None) == MonsterKind.GOBLIN:
            return False
        min_ratio = float(globals().get("MONSTER_ERADICATION_MIN_SIDE_POWER_RATIO", 0.75))
        min_party = int(globals().get("MONSTER_ERADICATION_MIN_PARTY_SIZE", 6))
        if side_power < monster_power * min_ratio:
            return False
        if party_size >= min_party:
            return True
        if bool(globals().get("MONSTER_ERADICATION_CHAMPION_BONUS", True)) and getattr(actor, "champion_of", None) is not None:
            return True
        if getattr(actor, "relic_id", None) is not None:
            return True
        return False

    def _record_failed_eradication_if_any(self, actor: Actor, monster: Monster, side_power: float, monster_power: float, party_size: int) -> None:
        if not self._is_organized_eradication_attempt(actor, monster, side_power, monster_power, party_size):
            return
        monster.eradication_survivals = int(getattr(monster, "eradication_survivals", 0) or 0) + 1
        self._mark_monster_terror_region(monster, getattr(actor, "region_id", None))
        try:
            self.world.log(
                f"{monster.name} survives an organized eradication attempt in {self.world.region_name(actor.region_id)}.",
                importance=3,
                category="monster_eradication_failed",
            )
        except Exception:
            pass


    def _resolve_monster_battle(self, actor: Actor, monster: Monster) -> bool:
        world = self.world
        if self._monster_acted_this_tick(monster):
            return False
        if self._giant_is_neutral(monster):
            monster.provoked_until_tick = max(getattr(monster, "provoked_until_tick", -1), world.tick + 90)
            world.log(f"{actor.short_name()} provokes {monster.name} in {world.region_name(monster.region_id)}.", importance=2, category="giant_provoked")
        party = world.get_party(actor)
        party_size = len(party.member_ids) if party else 1

        if monster.kind == MonsterKind.DRAGON and party_size < 5:
            return False

        if monster.kind == MonsterKind.ANCIENT_HORROR and party_size < 9:
            return False
        if self._monster_should_retreat_from_actor(monster, actor):
            self._monster_retreat(monster)
            world.log(f"{monster.name} avoids a stand-up fight against {actor.short_name()}.", importance=1, category="monster_retreat")
            return True
        world = self.world
        side_power = world.side_power(actor)
        side_power += world.side_charisma(actor) // 4
        side_power += max(0, actor.luck - 10) // 2
        if actor.role == Role.WIZARD:
            side_power += 3
        monster_power = monster.effective_power()
        own_mind = world.side_mind(actor)
        battle_roll = side_power + self.rng.randint(1, 10) + max(0, actor.luck - 10) // 2
        monster_roll = monster_power + self.rng.randint(1, 10)

        if monster.kind == MonsterKind.DRAGON:
            monster_roll += 8
        if monster.kind == MonsterKind.ANCIENT_HORROR:
            monster_roll += 15
        if monster.kind == MonsterKind.DRAGON and side_power < monster_power and own_mind >= 9 and self.rng.random() < 0.85:
            self._retreat(actor, reason=f"{monster.name} is too dangerous")
            return True
        if monster_power > side_power and own_mind >= 10 and self.rng.random() < 0.65:
            self._retreat(actor, reason=f"{monster.name} is too dangerous")
            return True

        battle_roll = side_power + self.rng.randint(1, 10) + max(0, actor.luck - 10) // 2
        monster_roll = monster_power + self.rng.randint(1, 10)
        if monster.kind == MonsterKind.DRAGON:
            monster_roll += 8
        if battle_roll >= monster_roll:
            monster.monster_battles_lost = getattr(monster, "monster_battles_lost", 0) + 1
            self._mark_monster_acted(monster)
            monster.alive = False
            world.kill_monster_cache_update(monster) if hasattr(world, "kill_monster_cache_update") else None
            credited_members = self._distribute_monster_rewards(actor, monster, party)
            slayer = credited_members[0] if credited_members else actor
            if monster.kind == MonsterKind.DRAGON:
                self._grant_title(slayer, "Dragonslayer")
                world.log(f"{self._champion_log_name(slayer)} slays {monster.name} in {world.region_name(actor.region_id)}.", importance=3, category="legendary_monster_kill")
                if getattr(slayer, "champion_of", None) is not None:
                    slayer.champion_monster_kills = getattr(slayer, "champion_monster_kills", 0) + 1
                    world.log(f"Later songs credit {self._champion_log_name(slayer)} with breaking {monster.name}'s terror.", importance=2, category="champion_impact")
            elif monster.kind == MonsterKind.GIANT:
                self._grant_title(slayer, "Giantbreaker")
                world.log(f"{self._champion_log_name(slayer)} fells {monster.name} in {world.region_name(actor.region_id)}.", importance=2, category="monster_kill")
                if getattr(slayer, "champion_of", None) is not None:
                    slayer.champion_monster_kills = getattr(slayer, "champion_monster_kills", 0) + 1
                    world.log(f"Local accounts credit {self._champion_log_name(slayer)} with freeing the roads from {monster.name}.", importance=2, category="champion_impact")
            elif monster.kind == MonsterKind.ANCIENT_HORROR:
                self._grant_title(slayer, "Bane of the Deep")
                world.log(f"{self._champion_log_name(slayer)} destroys the {monster.name} in {world.region_name(actor.region_id)}.", importance=3, category="legendary_monster_kill")
                if getattr(slayer, "champion_of", None) is not None:
                    slayer.champion_monster_kills = getattr(slayer, "champion_monster_kills", 0) + 1
                    world.log(f"The cults and courts alike credit {self._champion_log_name(slayer)} with ending the horror beneath {world.region_name(actor.region_id)}.", importance=3, category="champion_impact")
            else:
                world.log(f"{self._champion_log_name(slayer)} defeats {monster.name} in {world.region_name(actor.region_id)}.", importance=2, category="monster_kill")
                if getattr(slayer, "champion_of", None) is not None:
                    slayer.champion_monster_kills = getattr(slayer, "champion_monster_kills", 0) + 1
                    world.log(f"Common rumor credits {self._champion_log_name(slayer)} with the kill.", importance=2, category="champion_impact")
            if hasattr(self, "_resolve_monster_revenge_if_needed"):
                self._resolve_monster_revenge_if_needed(monster, [member.id for member in credited_members])
            self._elevate_monster_slayer(slayer, monster)
            world.adjust_region_state(actor.region_id, control_delta=3, order_delta=3)
            self._apply_combat_cooldown(world.side_members(actor))
            for member in world.side_members(actor):
                self._apply_fatigue(member, 4 if monster.kind in (MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR) else 3)
            self._post_battle_rest(world.side_members(actor), legendary=monster.kind in (MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR))
            return True

        self._mark_monster_acted(monster)
        monster.monster_battles_won = getattr(monster, "monster_battles_won", 0) + 1
        self._mark_monster_terror_region(monster, getattr(actor, "region_id", None))
        self._record_failed_eradication_if_any(actor, monster, side_power, monster_power, party_size)
        monster.monster_xp = getattr(monster, 'monster_xp', 0) + max(1, len(world.side_members(actor)))
        casualties = self._apply_losses(world.side_members(actor), severity=0.12 + monster_power / 100, cause=f"monster attack by {monster.name}")
        monster.monster_kills_adventurers = getattr(monster, "monster_kills_adventurers", 0) + int(casualties)
        routed_members = world.side_members(actor)
        self._apply_rout(routed_members)
        world.adjust_region_state(actor.region_id, control_delta=-1, order_delta=-2)
        self._apply_combat_cooldown(routed_members)
        if monster.kind != MonsterKind.ANCIENT_HORROR and self.rng.random() < 0.75:
            self._monster_retreat(monster)
        for member in routed_members:
            self._apply_fatigue(member, 5 if monster.kind in (MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR) else 3)
        self._post_battle_rest(routed_members, routed=True, legendary=monster.kind in (MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR))
        world.log(f"{monster.name} repels {self._champion_log_name(actor)} in {world.region_name(actor.region_id)}, leaving {casualties} dead.", importance=2, category="monster_attack")
        return True


    def _distribute_monster_rewards(self, actor: Actor, monster: Monster, party: Optional[Party]) -> List[Actor]:
        world = self.world
        participants = world.side_members(actor)
        if not participants:
            return []

        xp_values = {
            MonsterKind.GOBLIN: MONSTER_XP_GOBLIN,
            MonsterKind.GIANT: MONSTER_XP_GIANT,
            MonsterKind.DRAGON: MONSTER_XP_DRAGON,
            MonsterKind.ANCIENT_HORROR: MONSTER_XP_HORROR,
        }
        total_xp = xp_values.get(monster.kind, 50)
        if not hasattr(world, "region_activity"):
            world.region_activity = {rid: 0 for rid in world.regions}
        activity = world.region_activity.get(actor.region_id, 0)
        reduction_steps = activity // REGION_ACTIVITY_XP_STEP
        reduction = min(REGION_ACTIVITY_XP_REDUCTION_CAP, reduction_steps * REGION_ACTIVITY_XP_REDUCTION)
        total_xp = max(1, int(round(total_xp * (1.0 - reduction))))

        scored: List[Tuple[int, Actor]] = []
        for member in participants:
            score = member.power_rating() + self.rng.randint(1, 6)
            if member.role == Role.WIZARD:
                score += 2
            elif member.role == Role.WARDEN:
                score += 1
            if member.hp < max(2, member.max_hp // 2):
                score -= 2
            if party is not None and party.leader_id == member.id:
                score = int(score * LEADER_XP_WEIGHT_MULTIPLIER)
            score = max(1, score)
            scored.append((score, member))

        total_weight = sum(score for score, _ in scored) or len(scored)
        scored.sort(key=lambda item: item[0], reverse=True)

        credit_count = max(1, (len(scored) + 3) // 4)
        credited_ids = {member.id for _, member in scored[:credit_count]}
        if party is not None and party.leader_id is not None:
            credited_ids.add(party.leader_id)

        xp_remaining = total_xp
        for i, (weight, member) in enumerate(scored):
            if i == len(scored) - 1:
                xp_gain = xp_remaining
            else:
                xp_gain = int(total_xp * weight / total_weight)
                xp_remaining -= xp_gain
            if hasattr(member, 'gain_experience'):
                member.gain_experience(xp_gain)
            else:
                member.experience += xp_gain
            self._change_actor_rep(member, xp_gain // XP_TO_REP_DIVISOR)

        credited_members: List[Actor] = []
        for member in participants:
            if member.id not in credited_ids:
                continue
            credited_members.append(member)
            member.monster_kills += 1
            kill_desc = getattr(monster.kind, 'value', str(monster.kind)).lower()
            if hasattr(member, 'kill_log'):
                member.kill_log.append(kill_desc)
            if monster.kind == MonsterKind.DRAGON:
                member.dragon_kills += 1
                member.kills += 1
            elif monster.kind == MonsterKind.ANCIENT_HORROR:
                member.horror_kills += 1
                member.kills += 1
            elif monster.kind == MonsterKind.GIANT:
                member.giant_kills += 1
                member.kills += 1
            elif monster.kind != MonsterKind.GOBLIN:
                member.kills += 1

        world.region_activity[actor.region_id] = world.region_activity.get(actor.region_id, 0) + 1
        return credited_members


