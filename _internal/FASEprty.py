from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from FASEcfg import *
from FASEclass import *

class PartyMixin:
    def _party_founder_rep_threshold(self) -> int:
        cached = getattr(self.world, "_party_founder_rep_threshold_cache", None)
        if cached is not None:
            return cached
        living = [a.reputation for a in self.world.living_actors() if a.is_adventurer()]
        if not living:
            return 0
        living.sort()
        index = min(len(living) - 1, max(0, int((len(living) - 1) * PARTY_FOUNDING_PERCENTILE)))
        return living[index]


    def _party_can_accept_member(self, leader: Actor, member: Actor) -> bool:
        if not leader.alive or not member.alive:
            return False
        if not leader.is_adventurer() or not member.is_adventurer():
            return False
        if leader.id == member.id:
            return False
        # Bards never align with evil parties.
        if leader.role == Role.BARD and member.is_evil():
            return False
        if member.role == Role.BARD and leader.is_evil():
            return False
        if leader.is_good():
            return leader.can_join_party_with(member)
        if leader.is_evil():
            if member.is_good():
                return False
            if member.is_evil():
                return True
            return leader.reputation >= member.reputation + 10 or leader.charisma >= 12
        if member.is_evil():
            return leader.reputation >= member.reputation + 15
        return leader.can_join_party_with(member)


    def _party_internal_fit(self, members: list[Actor], candidate: Actor, leader: Actor) -> bool:
        if not self._party_can_accept_member(leader, candidate):
            return False
        if leader.is_evil():
            for member in members:
                if member.id == leader.id:
                    continue
                if member.is_good() and candidate.is_evil():
                    return False
            return True
        return all(candidate.can_join_party_with(existing_member) for existing_member in members)


    def _apply_evil_party_instability(self) -> None:
        world = self.world
        if world.tick % EVIL_PARTY_COUP_CHECK_TICKS != 0:
            return
        for party in list(world.parties.values()):
            leader = world.actors.get(party.leader_id) if party.leader_id is not None else None
            if leader is None or not leader.alive or not leader.is_evil():
                continue
            members = [world.actors[mid] for mid in party.member_ids if mid in world.actors and world.actors[mid].alive]
            if len(members) < 4:
                continue
            challengers = [
                member for member in members
                if member.id != leader.id and member.is_adventurer()
                and member.reputation >= leader.reputation - EVIL_PARTY_COUP_REP_MARGIN
            ]
            if not challengers:
                continue
            chance = EVIL_PARTY_COUP_BASE_CHANCE + min(0.15, len(challengers) * 0.015)
            chance += 0.05 if getattr(leader, "polity_favor", 50) < 25 else 0.0
            if self.rng.random() >= min(0.30, chance):
                continue

            challenger = max(challengers, key=lambda a: (a.reputation, a.power_rating(), a.charisma, a.luck))
            challenge_score = challenger.reputation + challenger.power_rating() + challenger.charisma + self.rng.randint(1, 20)
            defense_score = leader.reputation + leader.power_rating() + leader.charisma + self.rng.randint(1, 20)

            if challenge_score > defense_score:
                old_name = leader.short_name()
                self._mark_actor_dead(leader, "party coup", importance=2)
                world._transfer_party_leadership(
                    party,
                    challenger,
                    fate_note=f"Usurped by {challenger.short_name()} after a coup against {old_name}",
                )
                world.log(
                    f"{challenger.short_name()} seizes control of {party.name or f'Party {party.id}'} after a bloody coup against {old_name}.",
                    importance=3,
                    category="party_coup",
                )
            else:
                challenger.recovering = max(challenger.recovering, 3)
                challenger.reputation = max(0, challenger.reputation - 6)
                world.log(
                    f"{leader.short_name()} crushes a coup attempt inside {party.name or f'Party {party.id}'}.",
                    importance=2,
                    category="party_coup",
                )



    def _eligible_party_leader(self, actor: Actor) -> bool:
        if actor is None or not actor.alive or not actor.is_adventurer():
            return False
        if actor.role == Role.WIZARD and not actor.is_evil():
            return False
        return True

    def _best_local_party_to_join(self, actor: Actor) -> Optional[Party]:
        world = self.world
        candidates: List[Tuple[int, Party]] = []
        local_parties = getattr(world, "_parties_by_region_cache", {}).get(actor.region_id, list(world.parties.values()))
        for party in local_parties:
            if not party.member_ids or party.leader_id is None:
                continue
            leader = world.actors.get(party.leader_id)
            if leader is None or not leader.alive or leader.region_id != actor.region_id:
                continue
            members = [world.actors[mid] for mid in party.member_ids if mid in world.actors and world.actors[mid].alive]
            if not members:
                continue
            if not self._party_can_accept_member(leader, actor):
                continue
            if leader.is_good():
                if any(not actor.can_join_party_with(member) for member in members):
                    continue
            score = (
                len(members) * 100
                + sum(member.reputation for member in members)
                + max(m.reputation for m in members)
                + (50 if leader.is_evil() and actor.is_neutral_morality() else 0)
            )
            if getattr(actor, "best_friend_id", None) in party.member_ids:
                score += 500
            friend_ids = set(getattr(actor, "friend_ids", []) or [])
            if friend_ids.intersection(set(party.member_ids)):
                score += 150
            if getattr(actor, "nemesis_id", None) in party.member_ids:
                score -= 500
            candidates.append((score, party))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]


    def _join_existing_party(self, actor: Actor, party: Party) -> bool:
        world = self.world
        if actor.party_id is not None:
            return False
        leader = world.actors.get(party.leader_id) if party.leader_id is not None else None
        if leader is None or not leader.alive:
            return False
        members = [world.actors[mid] for mid in party.member_ids if mid in world.actors and world.actors[mid].alive]
        if not self._party_can_accept_member(leader, actor):
            return False
        if leader.is_good():
            if any(not actor.can_join_party_with(member) for member in members):
                return False
        world.remove_from_party(actor)
        actor.party_id = party.id
        actor.loyalty = party.leader_id
        party.member_ids.append(actor.id)
        if len(party.member_ids) >= 6:
            party.is_large_group = True
        world._update_party_history(party)
        return True


    def _decay_region_activity(self) -> None:
        world = self.world
        if not hasattr(world, "region_activity"):
            world.region_activity = {rid: 0 for rid in world.regions}
        if world.tick % TICKS_PER_TENDAY != 0:
            return
        for region_id in world.region_activity:
            world.region_activity[region_id] = max(0, world.region_activity[region_id] - 1)


    def _apply_party_fragmentation(self) -> None:
        world = self.world
        if world.tick % TICKS_PER_TENDAY != 0:
            return
        for party in list(world.parties.values()):
            if len(party.member_ids) <= PARTY_SPLIT_SIZE_THRESHOLD:
                continue
            leader = world.actors.get(party.leader_id) if party.leader_id is not None else None
            if leader is None or not leader.alive:
                continue
            region_activity = getattr(world, "region_activity", {}).get(leader.region_id, 0)
            chance = PARTY_SPLIT_BASE_CHANCE + max(0, len(party.member_ids) - PARTY_SPLIT_SIZE_THRESHOLD) * PARTY_SPLIT_PER_MEMBER
            chance += min(0.20, region_activity * 0.03)
            chance += 0.10 if getattr(leader, "polity_favor", 50) < 25 else 0.0
            if self.rng.random() >= min(0.85, chance):
                continue
            members = [world.actors[mid] for mid in party.member_ids if mid in world.actors and world.actors[mid].alive and mid != leader.id]
            if len(members) < 3:
                continue
            members.sort(key=lambda a: (getattr(a, "polity_favor", 50), -a.reputation, -a.power_rating()))
            split_size = max(2, min(len(members), max(2, len(party.member_ids) // 3)))
            splinters = members[:split_size]
            for member in splinters:
                world.remove_from_party(member)
                if member.polity_id is not None:
                    self._change_polity_favor(member, -8)
            new_party = world.create_party(splinters, goal=party.goal)
            if new_party is not None:
                world._update_party_history(party)
                hist = world.party_history.get(party.id)
                if hist is not None and hist.fate == "Active":
                    hist.fate = f"Fragmented; spawned {new_party.name or 'a splinter band'}"
                world.log(f"{party.name or 'A great host'} fractures in {world.region_name(leader.region_id)}, and {new_party.name or 'a splinter band'} breaks away.", importance=2, category="party_split")


    def _try_form_party(self, actor: Actor) -> None:
        world = self.world
        if actor.party_id is not None:
            return
        if not self._eligible_party_leader(actor):
            return

        existing = self._best_local_party_to_join(actor)
        if existing is not None:
            self._join_existing_party(actor, existing)
            return

        founding_threshold = self._party_founder_rep_threshold()
        if actor.reputation < founding_threshold:
            return

        regional_adventurers = [
            other for other in world.actors_in_region(actor.region_id)
            if other.id != actor.id and other.party_id is None and self._party_can_accept_member(actor, other)
        ]
        if len(regional_adventurers) < PARTY_FOUNDING_MIN_MEMBERS - 1:
            return

        candidates = [actor]
        regional_adventurers.sort(
            key=lambda other: (other.reputation, other.power_rating(), other.charisma, other.luck),
            reverse=True,
        )
        for other in regional_adventurers:
            if len(candidates) >= 50:
                break
            if other.loyalty is not None and other.loyalty != actor.id:
                continue
            if self._party_internal_fit(candidates, other, actor):
                candidates.append(other)

        if len(candidates) < PARTY_FOUNDING_MIN_MEMBERS:
            return

        chance = 0.30
        if actor.is_evil():
            chance += 0.10
        if not world.parties:
            chance += 0.15
        if actor.reputation >= founding_threshold + 25:
            chance += 0.10
        if self._recovery_state() == 'crisis':
            chance += 0.10
        elif self._recovery_state() == 'low':
            chance += 0.05

        if self.rng.random() < min(0.85, chance):
            goal = "dominion" if actor.is_evil() else "quest"
            party = world.create_party(candidates, goal=goal)
            if party is not None:
                mixed = {m.polity_id for m in candidates if m.alive and m.polity_id is not None}
                if len(mixed) > 1:
                    leader = world.actors.get(party.leader_id) if party.leader_id is not None else None
                    instigators = {leader.id} if leader is not None else set()
                    self._apply_selective_polity_penalty(
                        candidates,
                        MIXED_POLITY_PARTY_LEADER_FAVOR_LOSS,
                        MIXED_POLITY_PARTY_FOLLOWER_FAVOR_LOSS,
                        instigators,
                    )


