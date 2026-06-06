from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from FASEcfg import *
from FASEclass import *
_G = globals()


class PoliticsMixin:
    def _change_actor_rep(self, actor: Actor, delta: int) -> None:
        actor.reputation = max(0, actor.reputation + delta)


    def _change_polity_favor(self, actor: Actor, delta: int, polity_id: Optional[int] = None) -> None:
        target_polity = polity_id if polity_id is not None else getattr(actor, "polity_id", None)
        if target_polity is None:
            return
        if getattr(actor, "polity_id", None) == target_polity:
            actor.polity_favor = max(-100, min(100, getattr(actor, "polity_favor", 50) + delta))
            actor.state_loyalty = max(-100, min(100, getattr(actor, "state_loyalty", 50) + int(delta * 0.5)))
            if actor.polity_favor < 0 and actor.loyalty is not None and actor.loyalty != actor.id:
                actor.loyalty = None


    def _apply_selective_polity_penalty(
        self,
        members: List[Actor],
        full_loss: int,
        follower_loss: int,
        instigator_ids: Optional[set[int]] = None,
    ) -> None:
        instigator_ids = instigator_ids or set()
        for member in members:
            if not member.alive or member.polity_id is None:
                continue
            loss = full_loss if member.id in instigator_ids else follower_loss
            if loss:
                self._change_polity_favor(member, -loss)


    def _polity_side_penalty(self, members: List[Actor]) -> None:
        polities = {m.polity_id for m in members if m.alive and m.polity_id is not None}
        if len(polities) <= 1:
            return
        instigators = set()
        for member in members:
            if not member.alive:
                continue
            party = self.world.get_party(member)
            if party is not None and party.leader_id is not None:
                instigators.add(party.leader_id)
            else:
                instigators.add(member.id)
        self._apply_selective_polity_penalty(
            members,
            CROSS_POLITY_PARTY_FAVOR_LOSS,
            CROSS_POLITY_PARTY_FAVOR_LOSS_FOLLOWER,
            instigators,
        )


    def _actor_can_join_polity(self, actor: Actor, ruler: Actor) -> bool:
        if not actor.alive:
            return False
        if ruler.is_good() and actor.is_evil():
            return False
        if ruler.is_evil() and actor.is_good():
            return False
        return True


    def _strongest_party_ally(self, party: Party, exclude_id: Optional[int] = None) -> Optional[Actor]:
        world = self.world
        members = []
        for mid in party.member_ids:
            if mid == exclude_id:
                continue
            actor = world.actors.get(mid)
            if actor and actor.alive and self._eligible_party_leader(actor):
                members.append(actor)
        if not members:
            return None
        return max(
            members,
            key=lambda a: (
                getattr(a, "polity_favor", 50),
                a.reputation,
                a.power_rating(),
                a.charisma,
                a.luck,
            ),
        )



    def _eligible_polity_ruler(self, actor: Actor) -> bool:
        if actor is None or not actor.alive or not actor.is_adventurer():
            return False
        if actor.role == Role.WIZARD and not actor.is_evil():
            return False
        return True

    def _handle_party_succession(self) -> None:
        world = self.world
        for party in list(world.parties.values()):
            if len(party.member_ids) <= 1:
                world.archive_party(party, "Collapsed after attrition")
                continue
            leader = world.actors.get(party.leader_id) if party.leader_id is not None else None
            if leader is not None and leader.alive and leader.id in party.member_ids:
                continue

            successor = None
            if leader is not None:
                if leader.spouse_id is not None:
                    spouse = world.actors.get(leader.spouse_id)
                    if spouse and spouse.alive and spouse.id in party.member_ids and self._eligible_party_leader(spouse):
                        successor = spouse
                if successor is None:
                    children = []
                    for mid in party.member_ids:
                        actor = world.actors.get(mid)
                        if actor is None or not actor.alive:
                            continue
                        if not self._eligible_party_leader(actor):
                            continue
                        if actor.mother_id == leader.id or actor.father_id == leader.id:
                            children.append(actor)
                    if children:
                        successor = max(children, key=lambda a: (a.reputation, a.power_rating(), a.charisma, a.luck))
            if successor is None:
                successor = self._strongest_party_ally(party, exclude_id=leader.id if leader else None)

            if successor is None:
                world.archive_party(party, "Collapsed after leader death")
                continue

            old_name = leader.short_name() if leader is not None else "its fallen leader"
            world._transfer_party_leadership(party, successor, fate_note=f"Succeeded by {successor.short_name()} after the fall of {old_name}")
            world.log(
                f"{successor.short_name()} takes command of {party.name or f'Party {party.id}'} after the fall of {old_name}.",
                importance=2,
                category="succession",
            )


    def _eligible_polity_child_successors(self, polity: Polity, ruler: Actor) -> List[Actor]:
        world = self.world
        children = []
        child_ids = list(getattr(ruler, "children_ids", []) or [])
        if child_ids:
            for child_id in child_ids:
                actor = world.actors.get(child_id)
                if actor is not None and actor.alive:
                    children.append(actor)
            return children
        ruler_id = getattr(ruler, "id", None)
        for actor in world.living_actors():
            if getattr(actor, "mother_id", None) == ruler_id or getattr(actor, "father_id", None) == ruler_id:
                children.append(actor)
        return children


    def _strongest_polity_ally(self, polity: Polity, exclude_id: Optional[int] = None) -> Optional[Actor]:
        world = self.world
        members = []
        for aid in polity.member_actor_ids:
            if aid == exclude_id:
                continue
            actor = world.actors.get(aid)
            if actor and actor.alive and self._actor_can_join_polity(actor, world.actors.get(polity.ruler_id, actor)):
                members.append(actor)
        if not members:
            return None
        return max(
            members,
            key=lambda a: (
                getattr(a, "polity_favor", 50),
                a.reputation,
                a.power_rating(),
                a.charisma,
                a.luck,
            ),
        )



    def _polity_office_name(self, actor: Actor, polity: Polity, rank: str) -> str:
        label = str(rank or "").strip().lower()
        if label == "general":
            return f"General of {polity.name}"
        if label == "captain":
            return f"Captain of {polity.name}"
        if label == "lieutenant":
            return f"Lieutenant of {polity.name}"
        return polity.name


    def _elite_corruption_window_ticks(self) -> Tuple[int, int]:
        ticks_per_year = int(_G.get("TICKS_PER_YEAR", 1080))
        min_years = int(_G.get("ELITE_CORRUPTION_OFFICE_WINDOW_MIN_YEARS", 3))
        max_years = int(_G.get("ELITE_CORRUPTION_OFFICE_WINDOW_MAX_YEARS", 10))
        if max_years < min_years:
            max_years = min_years
        delay_years = self.rng.randint(max(0, min_years), max(0, max_years))
        duration_years = max(1, int(_G.get("ELITE_CORRUPTION_OFFICE_WINDOW_DURATION_YEARS", 1)))
        start = int(getattr(self.world, "tick", 0)) + delay_years * ticks_per_year
        end = start + duration_years * ticks_per_year
        return start, end


    def _set_elite_corruption_clock(self, actor: Optional[Actor], polity: Optional[Polity], role_label: str, *, force: bool = False) -> None:
        if actor is None or polity is None:
            return
        context = f"{getattr(polity, 'id', '')}:{str(role_label or '').lower()}"
        old_context = str(getattr(actor, "elite_corruption_context", "") or "")
        if not force and old_context == context and int(getattr(actor, "elite_corruption_window_start_tick", -1) or -1) >= 0:
            return
        start, end = self._elite_corruption_window_ticks()
        actor.elite_corruption_context = context
        actor.elite_corruption_window_start_tick = start
        actor.elite_corruption_window_end_tick = end
        actor.elite_corruption_window_resolved = False


    def _elite_corruption_actor_ready(self, polity: Polity, actor: Actor, role_label: str) -> bool:
        context = f"{getattr(polity, 'id', '')}:{str(role_label or '').lower()}"
        if str(getattr(actor, "elite_corruption_context", "") or "") != context:
            self._set_elite_corruption_clock(actor, polity, role_label, force=True)
            return False
        if bool(getattr(actor, "elite_corruption_window_resolved", False)):
            return False
        start = int(getattr(actor, "elite_corruption_window_start_tick", -1) or -1)
        end = int(getattr(actor, "elite_corruption_window_end_tick", -1) or -1)
        if start < 0 or end < start:
            self._set_elite_corruption_clock(actor, polity, role_label, force=True)
            return False
        now = int(getattr(self.world, "tick", 0))
        if now > end:
            actor.elite_corruption_window_resolved = True
            return False
        return start <= now <= end


    def _elite_corruption_character_multiplier(self, actor: Actor) -> float:
        mult = 1.0
        alignment = getattr(actor, "alignment", None)
        moral = getattr(alignment, "moral_axis", 0)
        law = getattr(alignment, "law_axis", 0)
        if moral > 0:
            mult *= 0.30
        elif moral < 0:
            mult *= 1.70
        if law > 0:
            mult *= 0.55
        elif law < 0:
            mult *= 1.35

        traits = {str(t).lower() for t in (getattr(actor, "traits", []) or [])}
        for trait, factor in {
            "loyal": 0.25,
            "merciful": 0.55,
            "patient": 0.70,
            "zealous": 0.85,
            "greedy": 1.80,
            "cruel": 1.45,
            "proud": 1.35,
            "suspicious": 1.20,
            "rash": 1.20,
            "cunning": 1.10,
        }.items():
            if trait in traits:
                mult *= factor

        wisdom = int(getattr(actor, "wisdom", 10) or 10)
        if wisdom > 10:
            mult *= max(0.45, 1.0 - ((wisdom - 10) * 0.045))
        elif wisdom < 10:
            mult *= min(1.45, 1.0 + ((10 - wisdom) * 0.045))

        state_loyalty = int(getattr(actor, "state_loyalty", 50) or 50)
        polity_favor = int(getattr(actor, "polity_favor", 50) or 50)
        institutional_loyalty = (state_loyalty + polity_favor) / 2.0
        if institutional_loyalty >= 70:
            mult *= max(0.35, 1.0 - ((institutional_loyalty - 70.0) / 100.0))
        elif institutional_loyalty < 45:
            mult *= min(1.65, 1.0 + ((45.0 - institutional_loyalty) / 80.0))

        return max(
            float(_G.get("ELITE_CORRUPTION_MIN_CHARACTER_MULT", 0.03)),
            min(float(_G.get("ELITE_CORRUPTION_MAX_CHARACTER_MULT", 2.50)), mult),
        )


    def _set_military_office(self, actor: Actor, polity: Polity, rank: str, commander_id: Optional[int] = None, allow_transfer: bool = False) -> bool:
        if actor is None or polity is None:
            return False
        if getattr(actor, "role", None) == Role.BARD:
            return False
        current_polity_id = getattr(actor, "polity_id", None)
        if current_polity_id is not None and current_polity_id != polity.id and not allow_transfer:
            return False
        if getattr(actor, "retired", False) or getattr(actor, "withdrawn", False) or getattr(actor, "in_school", False):
            return False
        if not getattr(actor, "alive", False):
            return False
        if not self._valid_polity_officer(actor, polity):
            return False
        if current_polity_id is None:
            actor.polity_id = polity.id
        if getattr(actor, "polity_id", None) != polity.id:
            return False
        old_rank = getattr(actor, "military_rank", None)
        old_commander = getattr(actor, "commander_id", None)
        actor.military_rank = rank
        actor.commander_id = commander_id
        title_map = {"general": "General", "captain": "Captain", "lieutenant": "Lieutenant"}
        preferred_title = title_map.get(rank)
        if preferred_title:
            actor.office_title = preferred_title
        actor.veteran = True
        actor.military_service_ticks = max(getattr(actor, "military_service_ticks", 0), 1)
        actor.state_loyalty = max(getattr(actor, "state_loyalty", 50), 65)
        actor.polity_favor = max(getattr(actor, "polity_favor", 50), 65)
        self._set_elite_corruption_clock(actor, polity, rank, force=False)
        return old_rank != rank or old_commander != commander_id


    def _clear_military_office(self, actor: Actor) -> None:
        if actor is None:
            return
        actor.military_rank = None
        actor.commander_id = None
        actor.office_title = None
        ctx = str(getattr(actor, "elite_corruption_context", "") or "")
        if any(ctx.endswith(f":{rank}") for rank in ("general", "captain", "lieutenant")):
            actor.elite_corruption_context = ""
            actor.elite_corruption_window_start_tick = -1
            actor.elite_corruption_window_end_tick = -1
            actor.elite_corruption_window_resolved = False


    def _actor_active_rulerships(self, actor: Optional[Actor]) -> List[Polity]:
        if actor is None:
            return []
        return [
            polity for polity in self.world.polities.values()
            if getattr(polity, "ruler_id", None) == actor.id
        ]


    def _actor_rules_active_polity(self, actor: Optional[Actor]) -> bool:
        return bool(self._actor_active_rulerships(actor))


    def _remove_actor_from_polity_military(self, actor_id: int, polity: Polity) -> bool:
        changed = False
        if getattr(polity, "general_id", None) == actor_id:
            polity.general_id = None
            changed = True
        if hasattr(polity, "general_ids") and getattr(polity, "general_ids", None):
            before = list(polity.general_ids)
            polity.general_ids = [aid for aid in polity.general_ids if aid != actor_id]
            changed = changed or before != polity.general_ids
        if hasattr(polity, "captain_ids") and getattr(polity, "captain_ids", None):
            before = list(polity.captain_ids)
            polity.captain_ids = [aid for aid in polity.captain_ids if aid != actor_id]
            changed = changed or before != polity.captain_ids
        if hasattr(polity, "lieutenant_by_captain") and getattr(polity, "lieutenant_by_captain", None):
            before = dict(polity.lieutenant_by_captain)
            polity.lieutenant_by_captain = {
                cid: lid for cid, lid in polity.lieutenant_by_captain.items()
                if cid != actor_id and lid != actor_id
            }
            changed = changed or before != polity.lieutenant_by_captain
        return changed


    def _strip_actor_military_titles(
        self,
        actor: Optional[Actor],
        except_polity_id: Optional[int] = None,
        penalize_foreign: bool = False,
    ) -> None:
        if actor is None:
            return
        old_titles = []
        for polity in list(self.world.polities.values()):
            if except_polity_id is not None and polity.id == except_polity_id:
                continue
            if self._remove_actor_from_polity_military(actor.id, polity):
                old_titles.append(polity.name)
        if old_titles:
            self._clear_military_office(actor)
            if penalize_foreign:
                actor.polity_favor = min(getattr(actor, "polity_favor", 50), -40)
                actor.state_loyalty = min(getattr(actor, "state_loyalty", 50), -20)
                actor.loyalty = None
            if penalize_foreign and hasattr(self.world, "log"):
                self.world.log(
                    f"{actor.short_name()} abandons former military obligations to serve another realm.",
                    importance=2,
                    category="polity",
                )


    def _strip_ruler_military_titles(self, actor: Optional[Actor]) -> None:
        # Rulership and military office are mutually exclusive.  A ruler may
        # command politically, but should not remain a general/captain/lieutenant.
        self._strip_actor_military_titles(actor, except_polity_id=None, penalize_foreign=False)


    def _valid_polity_officer(self, actor: Optional[Actor], polity: Polity) -> bool:
        if actor is None or not actor.alive:
            return False
        if actor.id == polity.ruler_id:
            return False
        if self._actor_rules_active_polity(actor):
            return False
        if actor.polity_id != polity.id:
            return False
        if not actor.is_adventurer() or getattr(actor, "retired", False) or getattr(actor, "withdrawn", False):
            return False
        if getattr(actor, "role", None) == Role.BARD and not bool(_G.get("BARD_ALLOW_MILITARY_OFFICE", False)):
            return False
        ruler = self.world.actors.get(polity.ruler_id)
        if ruler is not None and not self._actor_can_join_polity(actor, ruler):
            return False
        return True


    def _officer_score(self, actor: Actor) -> tuple:
        return (
            getattr(actor, "state_loyalty", 50),
            getattr(actor, "polity_favor", 50),
            actor.reputation,
            actor.power_rating(),
            actor.charisma,
            actor.luck,
        )


    def _polity_region_count(self, polity: Polity) -> int:
        return max(1, len(getattr(polity, "region_ids", []) or []))


    def _polity_officer_caps(self, polity: Polity) -> Tuple[int, int, int]:
        regions = self._polity_region_count(polity)
        return (
            max(0, int(_G.get("MILITARY_GENERALS_PER_REGION", 1)) * regions),
            max(0, int(_G.get("MILITARY_CAPTAINS_PER_REGION", 2)) * regions),
            max(0, int(_G.get("MILITARY_LIEUTENANTS_PER_REGION", 4)) * regions),
        )


    def _region_levy_manpower(self, polity: Polity, region_id: int) -> int:
        world = self.world
        commoners = int(getattr(world, "commoners_by_region", {}).get(region_id, 0) or 0)
        if commoners <= 0:
            return 0
        region = world.regions.get(region_id)
        order = int(getattr(region, "order", 50) if region is not None else 50)
        stability = int(getattr(polity, "stability", 50) or 50)
        loyalty = self._average_state_loyalty(polity) if hasattr(self, "_average_state_loyalty") else 50.0
        crisis = bool(region is not None and getattr(region, "under_siege_by", None) not in (None, polity.id))
        rate = float(_G.get("MILITARY_CRISIS_MOBILIZATION_RATE", 0.60) if crisis else _G.get("MILITARY_NORMAL_MOBILIZATION_RATE", 0.30))
        readiness = max(0.10, min(1.25, (order + stability + loyalty) / 180.0))
        levy = int(commoners * 0.50 * rate * readiness)
        return max(int(_G.get("MILITARY_MIN_LEVY_PER_REGION", 0)), levy)


    def _refresh_polity_levy(self, polity: Polity) -> int:
        if not hasattr(polity, "levy_manpower_by_region") or getattr(polity, "levy_manpower_by_region", None) is None:
            polity.levy_manpower_by_region = {}
        current = {}
        total = 0
        for rid in list(getattr(polity, "region_ids", []) or []):
            levy = self._region_levy_manpower(polity, rid)
            current[int(rid)] = levy
            total += levy
        polity.levy_manpower_by_region = current
        return total


    def _enlisted_capacity_for_levy(self, levy: int) -> int:
        per_100 = max(0, int(_G.get("MILITARY_ENLISTED_ACTORS_PER_100_LEVY", 2)))
        return max(0, (max(0, int(levy)) * per_100) // 100)


    def _military_actor_available(self, actor: Optional[Actor], polity: Polity) -> bool:
        if actor is None or not actor.alive:
            return False
        if not actor.is_adventurer() or getattr(actor, "retired", False) or getattr(actor, "withdrawn", False) or getattr(actor, "in_school", False):
            return False
        if self._actor_rules_active_polity(actor):
            return False
        if getattr(actor, "role", None) == Role.BARD and not bool(_G.get("BARD_ALLOW_MILITARY_ENLISTMENT", False)):
            return False
        if getattr(actor, "polity_id", None) not in (None, polity.id):
            return False
        ruler = self.world.actors.get(polity.ruler_id)
        if ruler is not None and not self._actor_can_join_polity(actor, ruler):
            return False
        return True


    def _enlisted_score(self, actor: Actor) -> tuple:
        role_score = 3 if actor.role == Role.FIGHTER else 2 if actor.role == Role.WARDEN else 1 if actor.role == Role.WIZARD else -5
        return (
            role_score,
            getattr(actor, "state_loyalty", 50),
            getattr(actor, "polity_favor", 50),
            actor.power_rating(),
            actor.reputation,
            actor.luck,
        )


    def _military_unit_name(self, polity: Polity, region_id: Optional[int], index: int = 1) -> str:
        if not hasattr(polity, "military_unit_names") or getattr(polity, "military_unit_names", None) is None:
            polity.military_unit_names = {}
        key = int(region_id if region_id is not None else index)
        existing = polity.military_unit_names.get(key)
        if existing:
            return existing
        region_name = self.world.region_name(region_id) if region_id in getattr(self.world, "regions", {}) else polity.name
        flavored = [
            f"{self._ordinal(index)} Army of {polity.name}",
            f"{region_name} Rangers",
            f"{region_name} Watch",
            f"Red Banner Company",
            f"Iron Wolves",
            f"Oakwatch Rangers",
        ]
        name = flavored[(key + index + len(polity.name)) % len(flavored)]
        polity.military_unit_names[key] = name
        return name


    def _ordinal(self, n: int) -> str:
        n = max(1, int(n))
        if 10 <= n % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"


    def _sync_polity_military_offices(self, polity: Polity) -> None:
        """Maintain polity-owned military offices using hard per-region caps.

        Caps are maximums, not targets.  This routine is idempotent per tick so
        repeated polity-strength/military calls do not spam promotion logs.
        """
        world = self.world
        if getattr(polity, "last_military_sync_tick", -999999) == getattr(world, "tick", 0):
            return
        polity.last_military_sync_tick = getattr(world, "tick", 0)

        self._strip_ruler_military_titles(world.actors.get(getattr(polity, "ruler_id", None)))
        if not hasattr(polity, "general_ids") or getattr(polity, "general_ids", None) is None:
            polity.general_ids = []
        if not hasattr(polity, "captain_ids") or getattr(polity, "captain_ids", None) is None:
            polity.captain_ids = []
        if not hasattr(polity, "lieutenant_by_captain") or getattr(polity, "lieutenant_by_captain", None) is None:
            polity.lieutenant_by_captain = {}

        max_generals, max_captains, max_lieutenants = self._polity_officer_caps(polity)

        def uniq(seq):
            out = []
            seen = set()
            for aid in seq:
                if aid is None or aid in seen:
                    continue
                seen.add(aid)
                out.append(aid)
            return out

        polity.general_ids = uniq([aid for aid in polity.general_ids if self._valid_polity_officer(world.actors.get(aid), polity)])[:max_generals]
        polity.captain_ids = uniq([aid for aid in polity.captain_ids if self._valid_polity_officer(world.actors.get(aid), polity) and aid not in polity.general_ids])[:max_captains]

        clean_lts = {}
        used_lts = set()
        for cid, lid in dict(polity.lieutenant_by_captain).items():
            cap = world.actors.get(cid)
            lt = world.actors.get(lid)
            if len(clean_lts) >= max_lieutenants:
                break
            if cid in polity.captain_ids and self._valid_polity_officer(cap, polity) and self._valid_polity_officer(lt, polity):
                if lid not in polity.general_ids and lid not in polity.captain_ids and lid not in used_lts:
                    clean_lts[cid] = lid
                    used_lts.add(lid)
        polity.lieutenant_by_captain = clean_lts

        candidates = self._polity_general_candidates(polity)
        used = set(polity.general_ids + polity.captain_ids + list(polity.lieutenant_by_captain.values()))

        while len(polity.general_ids) < max_generals:
            pool = [a for a in candidates if a.id not in used and getattr(a, "role", None) != Role.BARD]
            if not pool:
                break
            pick = max(pool, key=self._officer_score)
            if not self._set_military_office(pick, polity, "general", commander_id=polity.ruler_id):
                used.add(pick.id)
                continue
            polity.general_ids.append(pick.id)
            used.add(pick.id)
            world.log(f"{pick.short_name()} is appointed general of {polity.name}.", importance=2, category="polity")

        polity.general_id = polity.general_ids[0] if polity.general_ids else None

        while len(polity.captain_ids) < max_captains:
            pool = [a for a in candidates if a.id not in used and getattr(a, "role", None) != Role.BARD]
            if not pool:
                break
            pick = max(pool, key=self._officer_score)
            commander_id = polity.general_ids[(len(polity.captain_ids)) % max(1, len(polity.general_ids))] if polity.general_ids else polity.ruler_id
            if not self._set_military_office(pick, polity, "captain", commander_id=commander_id):
                used.add(pick.id)
                continue
            polity.captain_ids.append(pick.id)
            used.add(pick.id)
            world.log(f"{pick.short_name()} is promoted to captain of {polity.name}.", importance=1, category="polity")

        # Assign lieutenants round-robin beneath captains until the hard cap is reached.
        captain_cycle = list(polity.captain_ids)
        for cid in captain_cycle:
            if len(polity.lieutenant_by_captain) >= max_lieutenants:
                break
            if cid in polity.lieutenant_by_captain:
                continue
            pool = [a for a in candidates if a.id not in used and getattr(a, "role", None) != Role.BARD]
            if not pool:
                break
            pick = max(pool, key=self._officer_score)
            if not self._set_military_office(pick, polity, "lieutenant", commander_id=cid):
                used.add(pick.id)
                continue
            polity.lieutenant_by_captain[cid] = pick.id
            used.add(pick.id)

        # Re-assert titles/chain without logging.
        for gid in list(polity.general_ids):
            actor = world.actors.get(gid)
            if actor is not None:
                self._set_military_office(actor, polity, "general", commander_id=polity.ruler_id)
        for idx, cid in enumerate(list(polity.captain_ids)):
            actor = world.actors.get(cid)
            if actor is not None:
                commander_id = polity.general_ids[idx % max(1, len(polity.general_ids))] if polity.general_ids else polity.ruler_id
                self._set_military_office(actor, polity, "captain", commander_id=commander_id)
        for cid, lid in list(polity.lieutenant_by_captain.items()):
            actor = world.actors.get(lid)
            if actor is not None:
                self._set_military_office(actor, polity, "lieutenant", commander_id=cid)


    def _polity_generals(self, polity: Polity) -> List[Actor]:
        if not hasattr(polity, "general_ids") or not polity.general_ids:
            legacy = getattr(polity, "general_id", None)
            ids = [legacy] if legacy is not None else []
        else:
            ids = list(polity.general_ids)
        out = []
        for aid in ids:
            actor = self.world.actors.get(aid)
            if self._valid_polity_officer(actor, polity):
                out.append(actor)
        return out


    def _polity_captains(self, polity: Polity) -> List[Actor]:
        out = []
        for aid in list(getattr(polity, "captain_ids", []) or []):
            actor = self.world.actors.get(aid)
            if self._valid_polity_officer(actor, polity):
                out.append(actor)
        return out

    def _polity_officer_ids(self, polity: Polity) -> set[int]:
        ids = set(getattr(polity, "general_ids", []) or [])
        ids.update(getattr(polity, "captain_ids", []) or [])
        ids.update((getattr(polity, "lieutenant_by_captain", {}) or {}).values())
        legacy = getattr(polity, "general_id", None)
        if legacy is not None:
            ids.add(legacy)
        return {int(aid) for aid in ids if aid is not None}


    def _polity_grace_active(self, polity: Polity) -> bool:
        return int(getattr(self.world, "tick", 0)) < int(getattr(polity, "succession_grace_until", -999999))


    def _polity_truce_active(self, polity_a: Polity, polity_b_id: Optional[int]) -> bool:
        if polity_a is None or polity_b_id is None:
            return False
        until = int((getattr(polity_a, "truce_until_by_polity", {}) or {}).get(polity_b_id, -999999))
        return int(getattr(self.world, "tick", 0)) < until


    def _polities_allied(self, polity_a: Optional[Polity], polity_b_id: Optional[int]) -> bool:
        if polity_a is None or polity_b_id is None:
            return False
        self._safe_polity_lists(polity_a)
        return (
            polity_b_id in set(getattr(polity_a, "allied_polity_ids", []) or [])
            or polity_b_id in set(getattr(polity_a, "major_ally_ids", []) or [])
            or self._relationship_score(polity_a, polity_b_id) >= int(_G.get("POLITY_MAJOR_ALLY_THRESHOLD", 60))
        )


    def _set_polity_truce(self, polity_a: Optional[Polity], polity_b: Optional[Polity], ticks: Optional[int] = None) -> None:
        if polity_a is None or polity_b is None or polity_a.id == polity_b.id:
            return
        if ticks is None:
            ticks = int(_G.get("DIPLOMACY_TRUCE_TICKS", TICKS_PER_YEAR * 2))
        until = int(getattr(self.world, "tick", 0)) + max(1, int(ticks))
        if not hasattr(polity_a, "truce_until_by_polity") or getattr(polity_a, "truce_until_by_polity", None) is None:
            polity_a.truce_until_by_polity = {}
        if not hasattr(polity_b, "truce_until_by_polity") or getattr(polity_b, "truce_until_by_polity", None) is None:
            polity_b.truce_until_by_polity = {}
        polity_a.truce_until_by_polity[polity_b.id] = until
        polity_b.truce_until_by_polity[polity_a.id] = until


    def _military_regime_shield(self, polity: Polity) -> int:
        self._sync_polity_military_offices(polity)
        shield = 0
        for officer in self._polity_generals(polity):
            shield += int(getattr(officer, "state_loyalty", 50) * 1.2 + getattr(officer, "polity_favor", 50) * 0.8 + officer.power_rating())
        for officer in self._polity_captains(polity):
            shield += int(getattr(officer, "state_loyalty", 50) * 0.55 + getattr(officer, "polity_favor", 50) * 0.35 + officer.power_rating() * 0.5)
        return shield


    def _average_state_loyalty(self, polity: Polity) -> float:
        members = self._living_polity_members(polity)
        if not members:
            return 50.0
        return sum(float(getattr(a, "state_loyalty", 50)) for a in members) / max(1, len(members))


    def _ruler_approval_score(self, polity: Polity, ruler: Optional[Actor]) -> int:
        if ruler is None:
            return int(getattr(polity, "previous_ruler_approval", 50) or 50)
        members = self._living_polity_members(polity)
        if members:
            avg_favor = sum(getattr(a, "polity_favor", 50) for a in members) / max(1, len(members))
        else:
            avg_favor = 50
        score = 50
        score += int((avg_favor - 50) * 0.5)
        score += int((getattr(polity, "legitimacy", 50) - 50) * 0.4)
        score += int((getattr(polity, "stability", 50) - 50) * 0.4)
        score += min(20, int(getattr(ruler, "reputation", 0) // 8))
        score -= min(25, int(getattr(ruler, "regions_oppressed", 0) * 4))
        if ruler.is_evil() and avg_favor < 55:
            score -= 15
        return max(0, min(100, score))


    def _remember_previous_ruler(self, polity: Polity, ruler: Optional[Actor], fate: str = "Unknown") -> None:
        if polity is None:
            return
        polity.previous_ruler_id = getattr(ruler, "id", getattr(polity, "ruler_id", None))
        polity.previous_ruler_name = ruler.short_name() if ruler is not None else getattr(polity, "previous_ruler_name", "Unknown")
        polity.previous_ruler_approval = self._ruler_approval_score(polity, ruler)
        polity.previous_ruler_fate = fate


    def _close_polity_history_as_merged(self, polity: Polity, merged_name: str) -> None:
        world = self.world
        if not hasattr(world, "_ensure_polity_history"):
            return
        world._ensure_polity_history(polity)
        hist = world.polity_history.get(polity.id)
        if hist is None:
            return
        hist.active = False
        hist.fate = f"Merged with {merged_name}"
        hist.ended_tick = world.tick
        for rec in getattr(hist, "leaders", []) or []:
            if getattr(rec, "fate", "") == "Current ruler":
                rec.fate = f"Merged with {merged_name}"
                if getattr(rec, "end_tick", None) is None:
                    rec.end_tick = world.tick


    def _replace_polity_links_after_merge(self, old_ids: set[int], new_polity: Polity) -> None:
        for polity in self.world.polities.values():
            if polity.id == new_polity.id:
                continue
            self._safe_polity_lists(polity)
            for attr in ("allied_polity_ids", "trade_partner_ids", "hostile_polity_ids"):
                values = [pid for pid in getattr(polity, attr, []) if pid not in old_ids and pid != new_polity.id]
                if any(pid in old_ids for pid in getattr(polity, attr, [])):
                    values.append(new_polity.id)
                setattr(polity, attr, list(dict.fromkeys(values)))
            truce = getattr(polity, "truce_until_by_polity", {}) or {}
            best_until = max([until for pid, until in truce.items() if pid in old_ids] or [-999999])
            polity.truce_until_by_polity = {pid: until for pid, until in truce.items() if pid not in old_ids}
            if best_until > self.world.tick:
                polity.truce_until_by_polity[new_polity.id] = max(polity.truce_until_by_polity.get(new_polity.id, -999999), best_until)
            rel = getattr(polity, "relationship_scores", {}) or {}
            best_rel = max([int(score) for pid, score in rel.items() if pid in old_ids] or [0])
            polity.relationship_scores = {pid: score for pid, score in rel.items() if pid not in old_ids}
            if best_rel:
                polity.relationship_scores[new_polity.id] = self._clamp_relationship_score(best_rel)


    def _merge_duplicate_rulerships(self, ruler: Actor) -> Optional[Polity]:
        world = self.world
        polities = [p for p in list(world.polities.values()) if getattr(p, "ruler_id", None) == getattr(ruler, "id", None)]
        if len(polities) <= 1:
            return None
        polities.sort(key=lambda p: (len(getattr(p, "region_ids", []) or []), getattr(p, "strength", 0), -getattr(p, "founded_tick", 0)), reverse=True)
        primary = polities[0]
        old_ids = {p.id for p in polities}
        region_ids = []
        member_ids = []
        allied = []
        trade = []
        hostile = []
        truce: Dict[int, int] = {}
        for polity in polities:
            self._safe_polity_lists(polity)
            for rid in getattr(polity, "region_ids", []) or []:
                if rid not in region_ids:
                    region_ids.append(rid)
            for aid in getattr(polity, "member_actor_ids", []) or []:
                if aid not in member_ids:
                    member_ids.append(aid)
            allied.extend([pid for pid in getattr(polity, "allied_polity_ids", []) if pid not in old_ids])
            trade.extend([pid for pid in getattr(polity, "trade_partner_ids", []) if pid not in old_ids])
            hostile.extend([pid for pid in getattr(polity, "hostile_polity_ids", []) if pid not in old_ids])
            for pid, until in (getattr(polity, "truce_until_by_polity", {}) or {}).items():
                if pid not in old_ids:
                    truce[pid] = max(truce.get(pid, -999999), until)
        capital_region_id = primary.capital_region_id if primary.capital_region_id in region_ids else (region_ids[0] if region_ids else primary.capital_region_id)
        capital_name = world.region_name(capital_region_id) if hasattr(world, "region_name") else str(capital_region_id)
        new_name = f"United Kingdom of {capital_name}" if ruler.is_good() or ruler.alignment.moral_axis >= 0 else f"United Dominion of {capital_name}"
        new_polity = Polity(
            id=world.next_polity_id,
            name=new_name,
            alignment=ruler.alignment,
            ruler_id=ruler.id,
            capital_region_id=capital_region_id,
            region_ids=region_ids,
            member_actor_ids=list(dict.fromkeys(member_ids + [ruler.id])),
            founded_tick=world.tick,
            legitimacy=max(40, min(100, max(int(getattr(p, "legitimacy", 50)) for p in polities))),
            stability=max(35, min(100, int(sum(int(getattr(p, "stability", 50)) for p in polities) / max(1, len(polities))))),
            strength=sum(int(getattr(p, "strength", 0)) for p in polities),
            succession_grace_until=world.tick + int(_G.get("SUCCESSION_GRACE_TICKS", TICKS_PER_YEAR)),
            allied_polity_ids=list(dict.fromkeys(allied)),
            trade_partner_ids=list(dict.fromkeys(trade)),
            hostile_polity_ids=list(dict.fromkeys(hostile)),
            truce_until_by_polity=truce,
            relationship_scores={},
            major_rival_ids=[],
            major_ally_ids=[],
        )
        world.next_polity_id += 1
        world.polities[new_polity.id] = new_polity
        self._set_elite_corruption_clock(ruler, new_polity, "ruler", force=True)
        for old in polities:
            self._close_polity_history_as_merged(old, new_polity.name)
        for rid in region_ids:
            region = world.regions.get(rid)
            if region is not None:
                region.polity_id = new_polity.id
                region.ruler_id = ruler.id
                region.contested_by = None
                region.under_siege_by = None
                region.siege_progress = 0
        for aid in new_polity.member_actor_ids:
            actor = world.actors.get(aid)
            if actor is not None and actor.alive:
                actor.polity_id = new_polity.id
                if actor.id == ruler.id:
                    actor.loyalty = ruler.id
                    actor.polity_favor = max(getattr(actor, "polity_favor", 50), 90)
                    actor.state_loyalty = max(getattr(actor, "state_loyalty", 50), 90)
        for old in polities:
            world.polities.pop(old.id, None)
        self._replace_polity_links_after_merge(old_ids, new_polity)
        if hasattr(world, "_ensure_polity_history"):
            world._ensure_polity_history(new_polity)
            hist = world.polity_history.get(new_polity.id)
            if hist is not None:
                hist.name = new_polity.name
                hist.founder_id = ruler.id
                hist.founder_name = ruler.short_name()
                hist.current_ruler_id = ruler.id
                hist.current_ruler_name = ruler.short_name()
                hist.alignment = ruler.alignment.value
                hist.capital_region_id = capital_region_id
                hist.peak_regions = len(region_ids)
                hist.peak_strength = new_polity.strength
                hist.leaders = [PolityLeaderRecord(name=ruler.short_name(), fate="Current ruler", start_tick=world.tick, claim_type="dynastic union", predecessor=" / ".join(p.name for p in polities))]
        self._strip_ruler_military_titles(ruler)
        world.log(
            f"{ruler.short_name()} unites {', '.join(p.name for p in polities)} into {new_polity.name} by dynastic succession.",
            importance=4,
            category="succession",
        )
        return new_polity


    def _candidate_claim_type(self, polity: Polity, candidate: Actor, old_ruler: Optional[Actor]) -> str:
        if old_ruler is not None:
            if getattr(old_ruler, "spouse_id", None) == candidate.id:
                return "spouse"
            if getattr(candidate, "mother_id", None) == old_ruler.id or getattr(candidate, "father_id", None) == old_ruler.id:
                return "child"
        if candidate.id in self._polity_officer_ids(polity):
            rank = str(getattr(candidate, "military_rank", "") or "")
            if rank:
                return rank
            return "officer"
        return "loyalist"


    def _succession_candidate_score(self, polity: Polity, candidate: Actor, old_ruler: Optional[Actor], claim_type: str) -> float:
        approval = self._ruler_approval_score(polity, old_ruler)
        if old_ruler is None:
            approval = int(getattr(polity, "previous_ruler_approval", approval) or approval)
        dynastic = claim_type in {"spouse", "child"}
        military = claim_type in {"general", "captain", "lieutenant", "officer"}
        score = 0.0
        score += float(getattr(candidate, "state_loyalty", 50)) * float(_G.get("POLITY_SUCCESSION_STATE_LOYALTY_WEIGHT", 2.0))
        score += float(getattr(candidate, "polity_favor", 50)) * float(_G.get("POLITY_SUCCESSION_FAVOR_WEIGHT", 1.0))
        score += float(getattr(polity, "legitimacy", 50)) * 0.75
        score += float(getattr(polity, "stability", 50)) * 0.50
        score += float(getattr(candidate, "reputation", 0)) * 0.55
        score += float(candidate.power_rating()) * 0.65
        score += float(getattr(candidate, "charisma", 10)) * 2.0
        if dynastic:
            bonus = float(_G.get("POLITY_SUCCESSION_DYNASTIC_BONUS", 45))
            bonus += (approval - 50) * float(_G.get("POLITY_SUCCESSION_PREVIOUS_APPROVAL_WEIGHT", 0.8))
            score += bonus
        if military:
            score += float(_G.get("POLITY_SUCCESSION_MILITARY_BONUS", 30))
        if old_ruler is not None and candidate.id == getattr(old_ruler, "spouse_id", None) and approval < 35:
            score -= 20
        if dynastic and approval < 30:
            score -= 30
        if candidate.is_evil() and getattr(polity, "alignment", None) is not None and getattr(polity.alignment, "moral_axis", 0) > 0:
            score -= 25
        return score


    def _eligible_successor(self, polity: Polity) -> Optional[Actor]:
        world = self.world
        old_ruler = world.actors.get(polity.ruler_id)
        if old_ruler is None and hasattr(self, "resolve_actor"):
            old_ruler = self.resolve_actor(getattr(polity, "previous_ruler_id", polity.ruler_id))

        candidates: Dict[int, Tuple[Actor, str]] = {}

        def add(actor: Optional[Actor], claim_type: str) -> None:
            if actor is None or not getattr(actor, "alive", False):
                return
            if not self._eligible_polity_ruler(actor):
                return
            # Dynastic claimants can come from outside the polity, especially
            # children of two ruling houses.  Military/loyalist claimants must
            # already belong to this state.
            if claim_type not in {"child", "spouse"} and actor.polity_id != polity.id:
                return
            ruler_for_join = old_ruler if old_ruler is not None else actor
            if not self._actor_can_join_polity(actor, ruler_for_join):
                return
            candidates.setdefault(actor.id, (actor, claim_type))

        child_candidates: List[Actor] = []
        if old_ruler is not None:
            for child_id in list(getattr(old_ruler, "children_ids", []) or []):
                child = world.actors.get(child_id)
                if child is not None and getattr(child, "alive", False) and self._eligible_polity_ruler(child):
                    child_candidates.append(child)
            if not getattr(old_ruler, "children_ids", None):
                _ruler_id = getattr(old_ruler, "id", None)
                for actor in world.living_actors():
                    if getattr(actor, "mother_id", None) == _ruler_id or getattr(actor, "father_id", None) == _ruler_id:
                        if self._eligible_polity_ruler(actor):
                            child_candidates.append(actor)
            for child in child_candidates:
                add(child, "child")
            # Spouse is a fallback heir only when no valid child/heir exists.
            if not child_candidates:
                add(world.actors.get(getattr(old_ruler, "spouse_id", None)), "spouse")

        self._sync_polity_military_offices(polity)
        for general in self._polity_generals(polity):
            add(general, "general")
        for captain in self._polity_captains(polity):
            if getattr(captain, "state_loyalty", 50) >= 65 or getattr(captain, "polity_favor", 50) >= 70:
                add(captain, "captain")
        for aid in list(getattr(polity, "member_actor_ids", []) or []):
            actor = world.actors.get(aid)
            if actor is None:
                continue
            if getattr(actor, "state_loyalty", 50) >= 82 and getattr(actor, "polity_favor", 50) >= 70:
                add(actor, "loyalist")

        if not candidates:
            return None
        return max(candidates.values(), key=lambda item: self._succession_candidate_score(polity, item[0], old_ruler, item[1]))[0]


    def _handle_polity_succession(self) -> None:
        world = self.world
        for polity in list(world.polities.values()):
            ruler = world.actors.get(polity.ruler_id)
            if ruler and ruler.alive:
                continue
            if ruler is not None:
                self._remember_previous_ruler(polity, ruler, fate="death")
            successor = self._eligible_successor(polity)
            if successor is None:
                for region_id in polity.region_ids:
                    if region_id in world.regions and world.regions[region_id].polity_id == polity.id:
                        world.regions[region_id].polity_id = None
                        world.regions[region_id].contested_by = None
                world.log(f"{polity.name} collapses after the death of its ruler.", importance=3, category="polity")
                world.archive_polity(polity, 'Collapsed after ruler death')
                continue
            hist = getattr(world, 'polity_history', {}).get(polity.id)
            old_ruler_name = ruler.short_name() if ruler is not None else getattr(polity, "previous_ruler_name", "its fallen ruler")
            old_ruler_id = getattr(ruler, "id", getattr(polity, "previous_ruler_id", None))
            old_approval = int(getattr(polity, "previous_ruler_approval", self._ruler_approval_score(polity, ruler)) or 50)
            claim_type = self._candidate_claim_type(polity, successor, ruler)
            self._remember_previous_ruler(polity, ruler, fate="succession")
            polity.ruler_id = successor.id
            for _rid in list(getattr(polity, "region_ids", []) or []):
                if _rid in world.regions:
                    world.regions[_rid].ruler_id = successor.id
            polity.succession_grace_until = world.tick + int(_G.get("SUCCESSION_GRACE_TICKS", TICKS_PER_YEAR))
            polity.last_challenge_tick = world.tick
            polity.stability = min(100, max(25, int(getattr(polity, "stability", 50)) + int(_G.get("POLITY_GRACE_STABILITY_BONUS", 8))))
            polity.legitimacy = min(100, max(20, int(getattr(polity, "legitimacy", 50)) + int(_G.get("POLITY_GRACE_LEGITIMACY_BONUS", 6))))
            successor.polity_id = polity.id
            if successor.id not in getattr(polity, "member_actor_ids", []):
                polity.member_actor_ids.append(successor.id)
            successor.polity_favor = max(getattr(successor, "polity_favor", 50), 88)
            successor.state_loyalty = max(getattr(successor, "state_loyalty", 50), 85)
            successor.loyalty = successor.id
            self._strip_ruler_military_titles(successor)
            self._set_elite_corruption_clock(successor, polity, "ruler", force=True)

            acceptance_threshold = int(_G.get("POLITY_SUCCESSION_PERSONAL_LOYALTY_THRESHOLD", 55))
            successor_score = self._succession_candidate_score(polity, successor, ruler, claim_type)
            for actor in self._living_polity_members(polity):
                if actor.id == successor.id:
                    continue
                actor.state_loyalty = max(-100, min(100, getattr(actor, "state_loyalty", 50)))
                acceptance = actor.state_loyalty * 0.65 + actor.polity_favor * 0.25 + min(40, successor_score / 12.0)
                if old_ruler_id is not None and getattr(actor, "loyalty", None) == old_ruler_id:
                    acceptance += max(-25, min(25, (old_approval - 50) * 0.35))
                if actor.id in self._polity_officer_ids(polity):
                    acceptance += 12
                if acceptance >= acceptance_threshold:
                    actor.loyalty = successor.id
                elif getattr(actor, "loyalty", None) == old_ruler_id:
                    actor.loyalty = None

            if hist is not None:
                successor_name = successor.short_name()
                # Close any stale active ruler records.  Dirty/long saves can contain more than
                # one "Current ruler"; all prior active terms should end at this succession.
                for rec in getattr(hist, "leaders", []) or []:
                    if getattr(rec, "name", None) == successor_name:
                        continue
                    if getattr(rec, "fate", "") in ("Founder", "Current ruler"):
                        rec.fate = f"Succeeded by {successor_name}"
                        if getattr(rec, "end_tick", None) is None:
                            rec.end_tick = world.tick
                if hist.leaders and hist.leaders[-1].name == successor_name:
                    hist.leaders[-1].fate = "Current ruler"
                    hist.leaders[-1].end_tick = None
                    hist.leaders[-1].claim_type = claim_type
                    hist.leaders[-1].predecessor = old_ruler_name
                    if getattr(hist.leaders[-1], "start_tick", None) is None:
                        hist.leaders[-1].start_tick = world.tick
                else:
                    hist.leaders.append(PolityLeaderRecord(
                        name=successor_name,
                        fate="Current ruler",
                        start_tick=world.tick,
                        end_tick=None,
                        claim_type=claim_type,
                        predecessor=old_ruler_name,
                    ))
                hist.current_ruler_id = successor.id
                hist.current_ruler_name = successor_name
            world.log(f"{successor.short_name()} succeeds to the rule of {polity.name} by {claim_type} claim; the realm enters a year of succession grace.", importance=3, category="succession")
            self._merge_duplicate_rulerships(successor)


    def _claim_region_for_polity(self, polity: Polity, region_id: int) -> None:
        world = self.world
        region = world.regions[region_id]
        old_polity = region.polity_id
        if old_polity == polity.id and region_id in polity.region_ids:
            region.contested_by = None
            region.under_siege_by = None
            region.siege_progress = 0
            return
        region.polity_id = polity.id
        region.contested_by = None
        region.under_siege_by = None
        region.siege_progress = 0
        region.siege_started_tick = -999999
        if region_id not in polity.region_ids:
            polity.region_ids.append(region_id)
        if old_polity is not None and old_polity in world.polities and old_polity != polity.id:
            old = world.polities[old_polity]
            old.region_ids = [rid for rid in old.region_ids if rid != region_id]
            self._set_polity_truce(polity, old)
            self._adjust_polity_relationship(polity, old, int(_G.get("POLITY_RELATIONSHIP_CONQUEST_PENALTY", -35)), reason="conquest")
            self._form_polity_link(polity, old, "hostile_polity_ids")
            for attr in ("allied_polity_ids", "trade_partner_ids"):
                if hasattr(polity, attr):
                    setattr(polity, attr, [pid for pid in getattr(polity, attr) if pid != old.id])
                if hasattr(old, attr):
                    setattr(old, attr, [pid for pid in getattr(old, attr) if pid != polity.id])
        world.log(f"{polity.name} claims {world.region_name(region_id)}.", importance=2, category="polity")

    def _capture_threshold_for_region(self, region: Region) -> int:
        base = 100
        base += max(0, region.order // 2)
        base += region.danger * 4
        if region.polity_id is not None:
            base += 25
        return min(180, base)

    def _capture_progress_gain(self, polity: Polity, region: Region, ruler: Actor, friendly: List[Actor], rivals: List[Actor]) -> int:
        gain = 8
        gain += min(16, len(friendly) * 2)
        gain += min(12, polity.strength // 700)
        gain += min(8, max(0, ruler.reputation - POLITY_REGION_CLAIM_MIN_REPUTATION) // 10)
        gain -= min(18, len(rivals) * 3)
        gain -= min(14, region.order // 8)
        if region.polity_id is not None and region.polity_id != polity.id:
            gain -= 8
        return max(4, gain)

    def _begin_or_progress_region_capture(self, polity: Polity, region_id: int, ruler: Actor, friendly: List[Actor], rivals: List[Actor]) -> None:
        world = self.world
        region = world.regions[region_id]
        if region.polity_id == polity.id:
            region.under_siege_by = None
            region.siege_progress = 0
            region.siege_started_tick = -999999
            return

        if region.under_siege_by not in (None, polity.id):
            current_besieger = world.polities.get(region.under_siege_by)
            current_strength = current_besieger.strength if current_besieger is not None else 0
            challenger_strength = polity.strength + len(friendly) * 20
            if challenger_strength <= current_strength + 150:
                return
            region.siege_progress = max(0, region.siege_progress // 2)

        if region.under_siege_by != polity.id:
            region.under_siege_by = polity.id
            region.siege_progress = 0
            region.siege_started_tick = world.tick
            region.contested_by = polity.id
            if region.polity_id is not None and region.polity_id in world.polities and region.polity_id != polity.id:
                target_polity = world.polities.get(region.polity_id)
                self._adjust_polity_relationship(polity, target_polity, int(_G.get("POLITY_RELATIONSHIP_CLAIM_PRESSURE_PENALTY", -8)), reason="claim pressure")
            world.log(f"{polity.name} begins subjugating {world.region_name(region_id)}.", importance=2, category="polity")
            return

        gain = self._capture_progress_gain(polity, region, ruler, friendly, rivals)
        region.siege_progress = min(self._capture_threshold_for_region(region), region.siege_progress + gain)
        region.contested_by = polity.id

        threshold = self._capture_threshold_for_region(region)
        if region.siege_progress >= threshold:
            self._claim_region_for_polity(polity, region_id)
            region.ruler_id = ruler.id
            if ruler.is_good():
                world.adjust_region_state(region_id, control_delta=3, order_delta=2)
            elif ruler.is_evil():
                world.adjust_region_state(region_id, control_delta=-3, order_delta=-1)
            else:
                world.adjust_region_state(region_id, control_delta=1, order_delta=1)
        elif region.siege_progress >= int(threshold * 0.66) and world.tick % TICKS_PER_MONTH == 0:
            world.log(f"{polity.name} tightens its grip on {world.region_name(region_id)}.", importance=1, category="polity")

    def _decay_region_capture(self, polity: Polity, region_id: int) -> None:
        world = self.world
        region = world.regions[region_id]
        if region.under_siege_by != polity.id:
            return
        decay = 8 + max(0, region.order // 15)
        region.siege_progress = max(0, region.siege_progress - decay)
        if region.siege_progress <= 0:
            region.under_siege_by = None
            region.contested_by = None
            region.siege_started_tick = -999999
            world.log(f"{polity.name} loses its hold on {world.region_name(region_id)}.", importance=1, category="polity")


    def _polity_commoner_total(self, polity: Polity) -> int:
        world = self.world
        if not hasattr(world, 'commoners_by_region'):
            return 0
        return sum(world.commoners_by_region.get(rid, 0) for rid in polity.region_ids)


    def _dominant_polity(self) -> Optional[Polity]:
        world = self.world
        if not world.polities:
            return None
        return max(world.polities.values(), key=lambda p: (len(p.region_ids), p.strength, p.legitimacy))


    def _living_polity_members(self, polity: Polity) -> List[Actor]:
        world = self.world
        members = []
        for aid in polity.member_actor_ids:
            actor = world.actors.get(aid)
            if actor and actor.alive:
                members.append(actor)
        return members


    def _find_internal_claimant(self, polity: Polity) -> Optional[Actor]:
        world = self.world
        ruler = world.actors.get(polity.ruler_id)
        if ruler is None:
            return None
        shield = self._military_regime_shield(polity)
        avg_loyalty = self._average_state_loyalty(polity)
        members = []
        min_rep = max(
            int(_G.get("POLITY_CLAIMANT_MIN_REPUTATION", 90)),
            int(ruler.reputation * float(_G.get("POLITY_CLAIMANT_RULER_REP_FRACTION", 0.65))),
        )
        for actor in self._living_polity_members(polity):
            if actor.id == ruler.id:
                continue
            if not self._eligible_polity_ruler(actor):
                continue
            if actor.id in self._polity_officer_ids(polity) and getattr(actor, "state_loyalty", 50) >= 75:
                continue
            if getattr(actor, "state_loyalty", 50) >= 80 and getattr(actor, "polity_favor", 50) >= 60:
                continue
            if actor.reputation < min_rep:
                continue
            if actor.power_rating() < ruler.power_rating() * float(_G.get("POLITY_CLAIMANT_POWER_MARGIN", 0.85)):
                continue
            if actor.loyalty == ruler.id and actor.reputation < ruler.reputation * 0.90:
                continue
            ambition = actor.reputation + actor.power_rating() + actor.charisma - getattr(actor, "state_loyalty", 50) * 0.6 - getattr(actor, "polity_favor", 50) * 0.35
            ambition += max(0, 55 - polity.stability) + max(0, 50 - polity.legitimacy)
            ambition -= min(45, shield / 40.0)
            ambition -= max(0, avg_loyalty - 55) * 0.7
            if ambition >= 55:
                members.append(actor)
        if not members:
            return None
        return max(members, key=lambda a: (a.reputation, a.power_rating(), a.charisma, a.luck))


    def _polity_assassination_defense(self, polity: Polity, ruler: Actor) -> int:
        world = self.world
        party = world.get_party(ruler)
        party_guard = len(party.member_ids) * ASSASSINATION_GUARD_PER_PARTY_MEMBER if party is not None else 0
        local_loyalists = 0
        for actor in world.actors_in_region(ruler.region_id):
            if not actor.alive or actor.id == ruler.id:
                continue
            if actor.loyalty == ruler.id or actor.polity_id == polity.id:
                local_loyalists += 1
        local_guard = local_loyalists * ASSASSINATION_GUARD_PER_LOCAL_LOYALIST
        legitimacy_guard = int(polity.legitimacy * ASSASSINATION_LEGITIMACY_WEIGHT)
        military_guard = int(self._military_regime_shield(polity) * float(_G.get("POLITY_MILITARY_SHIELD_SCORE_WEIGHT", 0.65)))
        state_guard = int(max(0, self._average_state_loyalty(polity) - 50) * 2)
        return party_guard + local_guard + legitimacy_guard + military_guard + state_guard


    def _resolve_polity_assassination(self, polity: Polity, ruler: Actor, claimant: Optional[Actor]) -> None:
        world = self.world
        polity.last_challenge_tick = world.tick
        polity.challenge_count += 1
        assassin_power = (claimant.reputation if claimant else 40) + (claimant.luck if claimant else 10) + self.rng.randint(1, 30)
        defense = ruler.reputation + ruler.luck + max(0, polity.stability) + self._polity_assassination_defense(polity, ruler) + self.rng.randint(1, 30)
        if assassin_power > defense and self.rng.random() < max(0.08, 0.35 - max(0, self._average_state_loyalty(polity) - 50) * 0.004):
            source = claimant.short_name() if claimant else 'unknown hands'
            world.log(f"An assassination plot from {source} brings down {ruler.full_name()} of {polity.name}.", importance=3, category='polity_challenge')
            if claimant is not None and claimant.alive:
                self._change_actor_rep(claimant, 6)
                self._change_polity_favor(claimant, -10, polity.id)
            self._remember_previous_ruler(polity, ruler, fate='assassination')
            self._mark_actor_dead(ruler, 'assassination', importance=3)
            polity.stability = max(0, polity.stability - 20)
            self._destabilize_polity_regions(polity, 8, 10, max_regions=3)
            self._maybe_fragment_polity(polity)
            self._handle_polity_succession()
            return
        ruler.recovering = max(ruler.recovering, 3)
        polity.stability = max(0, polity.stability - 5)
        polity.last_challenge_tick = world.tick + int(_G.get("POLITY_FAILED_CHALLENGE_EXTRA_COOLDOWN_TICKS", 0))
        if claimant is not None and claimant.alive:
            self._change_actor_rep(claimant, -FAILED_ASSASSINATION_REP_LOSS)
            self._change_polity_favor(claimant, -FAILED_ASSASSINATION_FAVOR_LOSS, polity.id)
        self._destabilize_polity_regions(polity, 3, 4, max_regions=2)
        world.log(f"An assassination plot against {ruler.full_name()} of {polity.name} fails, but the court is shaken.", importance=2, category='polity_challenge')


    def _resolve_polity_claimant_war(self, polity: Polity, ruler: Actor, claimant: Actor) -> None:
        world = self.world
        polity.last_challenge_tick = world.tick
        polity.challenge_count += 1
        loyal_defenders = [a for a in self._living_polity_members(polity) if a.id != ruler.id and (a.loyalty == ruler.id or getattr(a, "state_loyalty", 50) >= 70)]
        claimant_supporters = [a for a in self._living_polity_members(polity) if a.id != claimant.id and a.loyalty == claimant.id and getattr(a, "state_loyalty", 50) < 75]
        ruler_score = (
            ruler.reputation + ruler.power_rating() + polity.legitimacy + polity.stability
            + int(self._military_regime_shield(polity) * float(_G.get("POLITY_MILITARY_SHIELD_SCORE_WEIGHT", 0.65)))
            + len(loyal_defenders) * 3
            + self.rng.randint(1, 40)
        )
        claimant_score = claimant.reputation + claimant.power_rating() + claimant.charisma + len(claimant_supporters) * 4 + self.rng.randint(1, 40)
        if claimant_score > ruler_score:
            self._remember_previous_ruler(polity, ruler, fate='deposed')
            world.log(f"{claimant.short_name()} rises as a claimant against {ruler.full_name()} in {polity.name} and wins the struggle for the throne.", importance=3, category='polity_challenge')
            if self.rng.random() < float(_G.get("POLITY_DEPOSITION_CHANCE", 0.55)):
                ruler.loyalty = None
                ruler.polity_id = None
                ruler.polity_favor = min(getattr(ruler, "polity_favor", 50), -20)
                ruler.recovering = max(getattr(ruler, "recovering", 0), 12)
                ruler.title = None
                world.log(f"{ruler.short_name()} is deposed and driven from power rather than killed.", importance=2, category='polity_challenge')
            else:
                self._mark_actor_dead(ruler, 'civil war', importance=3)
            polity.ruler_id = claimant.id
            for _rid in list(getattr(polity, "region_ids", []) or []):
                if _rid in world.regions:
                    world.regions[_rid].ruler_id = claimant.id
            polity.succession_grace_until = world.tick + int(_G.get("SUCCESSION_GRACE_TICKS", TICKS_PER_YEAR))
            polity.last_challenge_tick = world.tick + int(_G.get("POLITY_SUCCESSFUL_CHALLENGE_EXTRA_COOLDOWN_TICKS", TICKS_PER_YEAR))
            claimant.loyalty = claimant.id
            claimant.polity_id = polity.id
            claimant.polity_favor = 100
            claimant.state_loyalty = max(getattr(claimant, "state_loyalty", 50), 75)
            polity.stability = max(25, polity.stability - 8)
            polity.legitimacy = max(20, polity.legitimacy - 5)
            self._destabilize_polity_regions(polity, 4, 5, max_regions=3)
            for actor in self._living_polity_members(polity):
                if actor.id == claimant.id:
                    continue
                if not self._actor_can_join_polity(actor, claimant):
                    continue
                acceptance = getattr(actor, "state_loyalty", 50) * 0.65 + getattr(actor, "polity_favor", 50) * 0.25 + claimant.reputation * 0.10
                if actor.id in self._polity_officer_ids(polity):
                    acceptance += 10
                if acceptance >= int(_G.get("POLITY_SUCCESSION_PERSONAL_LOYALTY_THRESHOLD", 55)):
                    actor.loyalty = claimant.id
                elif getattr(actor, "loyalty", None) == ruler.id:
                    actor.loyalty = None
            return
        claimant.recovering = max(claimant.recovering, 4)
        self._change_actor_rep(claimant, -FAILED_COUP_REP_LOSS)
        self._change_polity_favor(claimant, -FAILED_COUP_FAVOR_LOSS, polity.id)
        coup_followers = [a for a in self._living_polity_members(polity) if a.id != claimant.id and a.loyalty == claimant.id]
        self._apply_selective_polity_penalty(coup_followers, FAILED_COUP_FAVOR_LOSS // 2, max(1, FAILED_COUP_FAVOR_LOSS // 4), {a.id for a in coup_followers})
        polity.stability = max(0, polity.stability - 3)
        polity.last_challenge_tick = world.tick + int(_G.get("POLITY_FAILED_CHALLENGE_EXTRA_COOLDOWN_TICKS", 0))
        self._destabilize_polity_regions(polity, 1, 2, max_regions=2)
        world.log(f"{ruler.full_name()} defeats the claimant {claimant.short_name()} and holds {polity.name} together.", importance=2, category='polity_challenge')
        if self.rng.random() < 0.12:
            self._mark_actor_dead(claimant, 'failed coup', importance=2)


    def _resolve_polity_regional_revolt(self, polity: Polity, ruler: Actor, claimant: Optional[Actor]) -> None:
        world = self.world
        if len(polity.region_ids) <= 1:
            return
        polity.last_challenge_tick = world.tick
        polity.challenge_count += 1
        revolt_candidates = [rid for rid in polity.region_ids if rid != polity.capital_region_id]
        if not revolt_candidates:
            return
        region_id = self.rng.choice(revolt_candidates)
        region = world.regions[region_id]
        region.contested_by = polity.id
        defense = ruler.reputation + polity.strength // 20 + polity.legitimacy + int(self._military_regime_shield(polity) * 0.30) + int(self._average_state_loyalty(polity)) + self.rng.randint(1, 25)
        challenge = (claimant.reputation if claimant else 60) + len([a for a in world.actors_in_region(region_id) if a.alive]) + self.rng.randint(1, 25)
        if challenge > defense:
            polity.region_ids = [rid for rid in polity.region_ids if rid != region_id]
            region.polity_id = None
            region.contested_by = None
            polity.stability = max(0, polity.stability - 12)
            self._destabilize_polity_regions(polity, 5, 6, max_regions=3)
            self._maybe_fragment_polity(polity)
            world.log(f"Revolt tears {world.region_name(region_id)} away from {polity.name}.", importance=3, category='polity_challenge')
            if claimant and claimant.alive and claimant.polity_id == polity.id:
                self._change_actor_rep(claimant, 8)
                self._change_polity_favor(claimant, -20, polity.id)
                claimant.polity_id = None
                claimant.loyalty = None
                local_members = [a.id for a in world.actors_in_region(region_id) if a.alive and a.is_adventurer() and a.id != claimant.id and claimant.can_join_party_with(a)]
                member_ids = [claimant.id] + local_members[:10]
                if claimant.reputation >= POLITY_REGION_CLAIM_MIN_REPUTATION:
                    new_polity = world.create_polity(claimant, region_id, member_ids)
                    if new_polity:
                        world.log(f"{claimant.short_name()} establishes {new_polity.name} after a successful revolt in {world.region_name(region_id)}.", importance=3, category='polity_challenge')
            return
        if claimant is not None and claimant.alive:
            self._change_actor_rep(claimant, -FAILED_REVOLT_REP_LOSS)
            self._change_polity_favor(claimant, -FAILED_REVOLT_FAVOR_LOSS, polity.id)
            revolt_followers = [a for a in world.actors_in_region(region_id) if a.alive and a.id != claimant.id and a.loyalty == claimant.id]
            self._apply_selective_polity_penalty(revolt_followers, FAILED_REVOLT_FAVOR_LOSS // 2, max(1, FAILED_REVOLT_FAVOR_LOSS // 4), {a.id for a in revolt_followers})
        polity.stability = max(0, polity.stability - 4)
        polity.last_challenge_tick = world.tick + int(_G.get("POLITY_FAILED_CHALLENGE_EXTRA_COOLDOWN_TICKS", 0))
        self._destabilize_polity_regions(polity, 2, 3, max_regions=2)
        self._maybe_fragment_polity(polity)
        world.log(f"{ruler.full_name()} crushes a revolt in {world.region_name(region_id)} and preserves {polity.name}.", importance=2, category='polity_challenge')


    def _maybe_challenge_polities(self) -> None:
        world = self.world
        if world.tick % max(1, int(_G.get("POLITY_CHALLENGE_CHECK_TICKS", POLITY_CHALLENGE_CHECK_TICKS))) != 0:
            return
        for polity in list(world.polities.values()):
            ruler = world.actors.get(polity.ruler_id)
            if ruler is None or not ruler.alive:
                continue
            if world.tick - polity.last_challenge_tick < int(_G.get("POLITY_CHALLENGE_COOLDOWN_TICKS", POLITY_CHALLENGE_COOLDOWN_TICKS)):
                continue
            if self._polity_grace_active(polity):
                continue
            region_count = len(polity.region_ids)
            if region_count < 1:
                continue
            claimant = self._find_internal_claimant(polity)
            age = self._calculate_age(ruler)
            pressure = 0.006 + region_count * 0.006
            pressure += min(0.06, max(0, ruler.reputation - 150) * 0.00012)
            pressure += max(0.0, age - 60) * 0.0012
            pressure += max(0.0, 55 - polity.stability) * 0.0022
            pressure += max(0.0, 45 - polity.legitimacy) * 0.0018
            if ruler.is_evil():
                pressure += EVIL_POLITY_EXTRA_CHALLENGE_PRESSURE * 0.55
            if claimant is not None:
                pressure += 0.045
            if polity.stability >= 70:
                pressure *= (1.0 - float(_G.get("POLITY_HIGH_STABILITY_CHALLENGE_SUPPRESSION", 0.45)))
            if polity.legitimacy >= 70:
                pressure *= (1.0 - float(_G.get("POLITY_HIGH_LEGITIMACY_CHALLENGE_SUPPRESSION", 0.35)))
            avg_loyalty = self._average_state_loyalty(polity)
            if avg_loyalty >= 60:
                pressure *= (1.0 - min(float(_G.get("POLITY_STATE_LOYALTY_CHALLENGE_SUPPRESSION", 0.30)), (avg_loyalty - 60) / 100.0))
            shield = self._military_regime_shield(polity)
            if shield > 0:
                pressure *= (1.0 - min(float(_G.get("POLITY_MILITARY_SHIELD_PRESSURE_REDUCTION", 0.35)), shield / 1800.0))
            pressure = max(0.001, min(0.16, pressure))
            if polity.stability <= 0 and not self._polity_grace_active(polity):
                self._destabilize_polity_regions(polity, 3, 4, max_regions=max(1, len(polity.region_ids) // 3))
                self._maybe_fragment_polity(polity)
            if self.rng.random() >= pressure:
                continue
            challenge_type = self.rng.choices(
                ['claimant', 'assassination', 'revolt'],
                weights=[5 if claimant else 1, 2, 3 if region_count >= 3 else 1],
                k=1,
            )[0]
            if challenge_type == 'claimant' and claimant is not None:
                self._resolve_polity_claimant_war(polity, ruler, claimant)
            elif challenge_type == 'revolt':
                self._resolve_polity_regional_revolt(polity, ruler, claimant)
            else:
                self._resolve_polity_assassination(polity, ruler, claimant)



    def _monster_deity_contributions(self) -> Dict[Deity, int]:
        world = self.world
        contributions = {deity: 0 for deity in self._pantheon_deities(world)}
        for monster in world.living_monsters():
            if monster.kind == MonsterKind.GOBLIN:
                contributions[Deity.LORD_OF_DARKNESS] += max(1, getattr(monster, 'horde_size', 1) * MONSTER_INFLUENCE_GOBLIN_PER_HEAD)
            elif monster.kind == MonsterKind.DRAGON:
                temperament = getattr(monster, 'dragon_temperament', 'malevolent')
                if temperament == 'benevolent':
                    contributions[Deity.LORD_OF_LIGHT] += MONSTER_INFLUENCE_DRAGON
                else:
                    contributions[Deity.GOD_OF_CHANCE] += MONSTER_INFLUENCE_DRAGON
        return contributions

    def _deity_influence_totals(self):
        world = self.world
        soul_weight = 2
        faith_map = getattr(world, 'commoner_faith_by_region', {})
        monster_support = self._monster_deity_contributions()
        deities = list(self._pantheon_deities(world))

        # Single pass over living actors for follower counts.
        living_by_deity = {deity: 0 for deity in deities}
        for actor in world.living_actors():
            deity = getattr(actor, 'deity', None)
            if deity in living_by_deity:
                living_by_deity[deity] += 1

        # Single pass over faith_map to accumulate commoner totals per deity
        # instead of O(deities * regions) per-deity sum.
        commoners_by_deity = {deity: 0 for deity in deities}
        for region_faith in faith_map.values():
            for deity, count in region_faith.items():
                if deity in commoners_by_deity:
                    commoners_by_deity[deity] += int(count or 0)

        totals = {}
        total_influence = 0
        for deity in deities:
            influence = (
                living_by_deity.get(deity, 0)
                + commoners_by_deity.get(deity, 0)
                + int(world.souls_by_deity.get(deity, 0)) * soul_weight
                + int(monster_support.get(deity, 0))
            )
            totals[deity] = influence
            total_influence += influence
        shares = {deity: ((totals[deity] / total_influence) * 100.0 if total_influence > 0 else 0.0) for deity in deities}
        return totals, shares

    def _dominant_deity_regions(self, deity: Deity) -> List[Region]:
        world = self.world
        faith_map = getattr(world, 'commoner_faith_by_region', {})
        ranked = []
        for region in world.regions.values():
            region_faith = faith_map.get(region.id, {})
            total = sum(region_faith.values())
            deity_count = region_faith.get(deity, 0)
            favored = 1 if self._region_favored_deity(region.id) == deity else 0
            ranked.append((deity_count, favored, region.order, world.commoners_by_region.get(region.id, 0), region))
        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
        return [item[-1] for item in ranked]

    def _region_faith_share(self, region_id: int, deity: Deity) -> float:
        faith_map = getattr(self.world, 'commoner_faith_by_region', {}).get(region_id, {})
        total = sum(faith_map.values())
        if total <= 0:
            return 0.0
        return faith_map.get(deity, 0) / total

    def _shift_faith_between_deities(self, region_id: int, from_deity: Deity, to_deity: Deity, amount: int) -> int:
        if amount <= 0 or from_deity == to_deity:
            return 0
        faith_map = self.world.commoner_faith_by_region.setdefault(region_id, self._empty_faith_map(world))
        moved = min(amount, faith_map.get(from_deity, 0))
        if moved <= 0:
            return 0
        faith_map[from_deity] = max(0, faith_map.get(from_deity, 0) - moved)
        faith_map[to_deity] = faith_map.get(to_deity, 0) + moved
        return moved

    def _bleed_dominant_influence(self) -> bool:
        world = self.world
        totals, shares = self._deity_influence_totals()
        leader, leader_share = max(shares.items(), key=lambda item: item[1])
        if leader_share <= IMMORTAL_DOMINANCE_BLEED_THRESHOLD:
            return False
        excess = leader_share - IMMORTAL_DOMINANCE_BLEED_THRESHOLD
        if excess <= 0:
            return False
        regions = self._dominant_deity_regions(leader)[:max(2, IMMORTAL_PRESSURE_MAX_REGIONS)]
        if not regions:
            return False
        shifted_total = 0
        recipients = [d for d in self._pantheon_deities(world) if d != leader]
        recipient_weights = {d: max(1, totals.get(d, 0)) for d in recipients}
        weight_total = sum(recipient_weights.values()) or 1
        for region in regions:
            faith_map = world.commoner_faith_by_region.get(region.id, {})
            deity_count = faith_map.get(leader, 0)
            if deity_count <= 0:
                continue
            region_share = self._region_faith_share(region.id, leader)
            bleed_rate = IMMORTAL_DOMINANCE_BLEED_RATE + (excess / 100.0) * IMMORTAL_DOMINANCE_EXCESS_MULTIPLIER
            bleed_rate *= max(0.35, region_share)
            bleed = min(deity_count, max(1, int(deity_count * bleed_rate)))
            if bleed <= 0:
                continue
            faith_map[leader] = max(0, deity_count - bleed)
            assigned = 0
            for i, deity in enumerate(recipients):
                if i == len(recipients) - 1:
                    add = bleed - assigned
                else:
                    add = int(bleed * (recipient_weights[deity] / weight_total))
                    assigned += add
                faith_map[deity] = faith_map.get(deity, 0) + add
            shifted_total += bleed
        if shifted_total > 0:
            world.log(
                f"The worship of {leader.value} grows complacent and begins to fracture under its own weight.",
                importance=2,
                category='divine_pressure',
            )
            return True
        return False

    def _apply_divine_disaster(self) -> bool:
        world = self.world
        if not hasattr(world, 'last_divine_disaster_tick'):
            world.last_divine_disaster_tick = -999999
        if world.tick - world.last_divine_disaster_tick < IMMORTAL_DISASTER_COOLDOWN_TICKS:
            return False

        totals, shares = self._deity_influence_totals()
        desperate, desperate_share = min(shares.items(), key=lambda item: item[1])
        dominant, dominant_share = max(shares.items(), key=lambda item: item[1])

        if desperate == dominant or desperate_share > IMMORTAL_DESPERATION_THRESHOLD:
            return False

        targets = self._dominant_deity_regions(dominant)[:IMMORTAL_DISASTER_MAX_REGIONS]
        if not targets:
            return False

        world.last_divine_disaster_tick = world.tick
        total_disrupted = 0
        names = []
        for region in targets:
            region_id = region.id
            names.append(world.region_name(region_id))
            region_faith = world.commoner_faith_by_region.setdefault(region_id, self._empty_faith_map(world))
            local_share = self._region_faith_share(region_id, dominant)
            global_shield = min(IMMORTAL_DISASTER_SHIELD_CAP, (dominant_share / 100.0) * 0.20 + local_share * 0.55)
            base_damage = IMMORTAL_DISASTER_BASE_SHAKE + ((dominant_share - IMMORTAL_DESPERATION_THRESHOLD) / 100.0) * IMMORTAL_DISASTER_EXCESS_MULTIPLIER
            effective_damage = max(0.01, min(IMMORTAL_DISASTER_MAX_SHAKE, base_damage * (1.0 - global_shield)))
            dominant_count = region_faith.get(dominant, 0)
            faith_loss = min(dominant_count, max(1, int(dominant_count * effective_damage))) if dominant_count > 0 else 0
            if faith_loss > 0:
                region_faith[dominant] = max(0, dominant_count - faith_loss)
                redirected = max(1, int(faith_loss * 0.60))
                region_faith[desperate] = region_faith.get(desperate, 0) + redirected
                remainder = faith_loss - redirected
                other_targets = [d for d in self._pantheon_deities(world) if d not in (dominant, desperate)]
                for _ in range(remainder):
                    region_faith[self.rng.choice(other_targets or [desperate])] += 1
                total_disrupted += faith_loss
            commoners = getattr(world, 'commoners_by_region', {}).get(region_id, 0)
            if commoners > 0:
                # Most divine backlash should be faith/order disruption, not
                # silent population deletion. Actual deaths are explicit and
                # much smaller than before.
                harm = min(commoners, max(0, int(commoners * (effective_damage * 0.05))))
                if harm > 0:
                    world.commoners_by_region[region_id] = max(0, commoners - harm)
                    if hasattr(self, '_remove_commoner_deaths'):
                        self._remove_commoner_deaths(region_id, harm, cause="divine disaster")
            world.adjust_region_state(region_id, control_delta=-max(1, int(6 * effective_damage)), order_delta=-max(2, int(12 * effective_damage)))

        if total_disrupted > 0:
            target_text = ", ".join(names[:-1]) + (f", and {names[-1]}" if len(names) > 1 else names[0])
            world.log(
                f"With {desperate.value} nearly cast down, the immortal lashes out at the realms of {dominant.value}. Storm, famine, and omen strike {target_text}, shaking the faith of the flock.",
                importance=3,
                category='divine_disaster',
            )
            return True
        return False

    def _apply_immortal_influence_pressure(self) -> None:
        self._bleed_dominant_influence()
        self._apply_divine_disaster()

    def _region_alignment_lean(self, region: Region) -> str:
        if region.control <= -30:
            return 'evil'
        if region.control >= 30:
            return 'good'
        return 'contested'

    def _champion_spawn_regions(self, deity: Deity) -> List[int]:
        world = self.world
        regions = list(world.regions.values())
        contested = [r for r in regions if self._region_alignment_lean(r) == 'contested']
        weakest = sorted(regions, key=lambda r: (r.order, abs(r.control), r.danger))[:max(3, len(regions)//3)]
        if deity == Deity.LORD_OF_DARKNESS:
            aligned = [r for r in regions if self._region_alignment_lean(r) == 'evil']
            fallback = [r for r in weakest if self._region_alignment_lean(r) != 'good'] or contested or weakest
            return [r.id for r in (aligned or fallback)]
        if deity == Deity.LORD_OF_LIGHT:
            aligned = [r for r in regions if self._region_alignment_lean(r) == 'good' or r.order >= 50]
            fallback = contested or weakest
            return [r.id for r in (aligned or fallback)]
        chance_pool = contested or weakest or regions
        return [r.id for r in chance_pool]

    def _spawn_divine_champion(self, deity: Deity) -> Optional[Actor]:
        world = self.world
        candidate_region_ids = self._champion_spawn_regions(deity)
        if not candidate_region_ids:
            return None
        region_id = self.rng.choice(candidate_region_ids)
        role_weights = [(Role.FIGHTER, 5), (Role.WARDEN, 3), (Role.WIZARD, 2)]
        roles, weights = zip(*role_weights)
        role = self.rng.choices(roles, weights=weights, k=1)[0]
        if deity == Deity.LORD_OF_LIGHT:
            alignment = self.rng.choice([Alignment.LAWFUL_GOOD, Alignment.NEUTRAL_GOOD, Alignment.CHAOTIC_GOOD])
        elif deity == Deity.LORD_OF_DARKNESS:
            alignment = self.rng.choice([Alignment.LAWFUL_EVIL, Alignment.NEUTRAL_EVIL, Alignment.CHAOTIC_EVIL])
        else:
            alignment = self.rng.choice([Alignment.LAWFUL_GOOD, Alignment.NEUTRAL_GOOD, Alignment.CHAOTIC_GOOD, Alignment.LAWFUL_EVIL, Alignment.NEUTRAL_EVIL, Alignment.CHAOTIC_EVIL])
        stats = list(self._roll_stats(role))
        banned = {2}
        if role == Role.FIGHTER:
            banned.add(0)
        elif role == Role.WARDEN:
            banned.add(1)
        elif role == Role.WIZARD:
            banned.add(3)
        weakness_choices = [i for i in range(7) if i not in banned]
        weakness = self.rng.choice(weakness_choices)
        for i in range(7):
            stats[i] += 5
        stats[weakness] -= 5
        stats = [max(3, s) for s in stats]
        hp = self._base_hp(role, stats[2])
        first, surname, sex = self._random_person_identity()
        traits = self.rng.sample(TRAITS, k=2)
        year, _, _, _, _ = world.current_calendar()
        actor = Actor(
            id=world.next_actor_id,
            name=first,
            surname=surname,
            role=role,
            alignment=alignment,
            deity=deity,
            strength=stats[0], dexterity=stats[1], constitution=stats[2], intelligence=stats[3], wisdom=stats[4], charisma=stats[5], luck=stats[6],
            hp=hp, max_hp=hp,
            region_id=region_id,
            traits=traits,
            birth_year=year - self.rng.randint(18, 35),
            birth_month=self.rng.randint(1, 12),
            birth_day=self.rng.randint(1, 30),
            spouse_id=None,
            sex=sex,
            mother_label="Unknown",
            father_label="Unknown",
            reputation=12,
            deity_conviction=100,
            champion_of=deity,
        )
        if hasattr(world, "register_actor"):
            world.register_actor(actor)
        else:
            world.actors[world.next_actor_id] = actor
        world.next_actor_id += 1
        world.generated_by_role[role] += 1
        if hasattr(actor, 'sync_progression'):
            actor.sync_progression(initial=True)
        if actor.title is None or str(actor.title).startswith("First in Class of "):
            actor.title = f"Champion of {deity.value}"
        return actor

    def _maybe_spawn_divine_champions(self) -> bool:
        world = self.world
        if world.tick % TICKS_PER_MONTH != 0:
            return False
        if not hasattr(world, 'last_champion_tick_by_deity'):
            world.last_champion_tick_by_deity = {deity: -999999 for deity in self._pantheon_deities(world)}
        _, shares = self._deity_influence_totals()
        spawned = False
        for deity in self._pantheon_deities(world):
            if shares.get(deity, 0.0) >= 10.0:
                continue
            # Use god_state champions list if available; avoid scanning all living actors per deity.
            god_st = getattr(world, "god_state", {}).get(deity)
            if god_st is not None:
                if getattr(god_st, "champions", []):
                    continue
            elif any(getattr(actor, 'champion_of', None) == deity for actor in world.living_actors()):
                continue
            if world.tick - world.last_champion_tick_by_deity.get(deity, -999999) < DIVINE_CHAMPION_COOLDOWN_TICKS:
                continue
            champion = self._spawn_divine_champion(deity)
            if champion is None:
                continue
            world.last_champion_tick_by_deity[deity] = world.tick
            world.log(f"With {deity.value} diminished and desperate, {champion.full_name()} rises in {world.region_name(champion.region_id)} as a divine champion.", importance=3, category='champion')
            spawned = True
        return spawned

    def _maybe_spawn_dragon_for_polities(self) -> bool:
        world = self.world
        dragons = [m for m in world.living_monsters() if m.kind == MonsterKind.DRAGON]
        if len(dragons) >= MAX_WILD_DRAGONS:
            return False
        candidates = []
        for polity in world.polities.values():
            if len(polity.region_ids) < DRAGON_ATTRACTION_MIN_REGIONS:
                continue
            if world.tick - polity.last_dragon_tick < DRAGON_ATTRACTION_COOLDOWN_TICKS:
                continue
            commoners = self._polity_commoner_total(polity)
            if commoners < DRAGON_ATTRACTION_MIN_COMMONERS:
                continue
            candidates.append((commoners + polity.strength + len(polity.region_ids) * 50, polity))
        if not candidates:
            return False
        _, polity = max(candidates, key=lambda item: item[0])
        if self.rng.random() >= 0.35:
            return False
        target_region_id = max(polity.region_ids, key=lambda rid: world.commoners_by_region.get(rid, 0) if hasattr(world, 'commoners_by_region') else 0)
        dragon = self._make_dragon(target_region_id)
        world.register_monster(dragon) if hasattr(world, "register_monster") else world.monsters.__setitem__(dragon.id, dragon)
        world.generated_monsters_by_kind[dragon.kind] += 1
        polity.last_dragon_tick = world.tick
        world.log(f"Drawn by the swelling wealth and population of {polity.name}, a {dragon.name} descends upon {world.region_name(target_region_id)}.", importance=3, category='monster_spawn')
        return True


    def _horror_calendar_matches(self, title: str, key: str) -> bool:
        try:
            _year, month, day, _tod, _season = self.world.current_calendar()
        except Exception:
            return False
        calendar = _G.get("ANCIENT_HORROR_CALENDAR", {}) or {}
        entry = calendar.get(title, {}) if isinstance(calendar, dict) else {}
        target = entry.get(key) if isinstance(entry, dict) else None
        try:
            target_month, target_day = target
        except Exception:
            return False
        return int(month) == int(target_month) and int(day) == int(target_day)

    def _available_horror_titles_for_day(self, key: str) -> List[str]:
        spawned = set(getattr(self, "_spawned_horror_titles", set()) or set())
        spawned.update(set(getattr(self.world, "spawned_horror_titles", set()) or set()))
        titles = [h for h in _G.get("HORROR_TITLES", []) if h not in spawned]
        return [h for h in titles if self._horror_calendar_matches(h, key)]

    def _natural_horror_chance(self, dominance_ratio: float) -> float:
        table = _G.get("ANCIENT_HORROR_NATURAL_CHANCE_BY_DOMINANCE", None)
        if not table:
            return 0.05 if dominance_ratio >= 0.75 else 0.035 if dominance_ratio >= 0.60 else 0.025 if dominance_ratio >= 0.50 else 0.015 if dominance_ratio >= 0.40 else 0.005
        best = 0.0
        for threshold, chance in table:
            try:
                if dominance_ratio >= float(threshold):
                    best = max(best, float(chance))
            except Exception:
                continue
        return max(0.0, min(0.05, best))

    def _horror_world_cooldown_ready(self) -> bool:
        cooldown = int(_G.get("ANCIENT_HORROR_WORLD_COOLDOWN_TICKS", TICKS_PER_YEAR * 25) or 0)
        last = int(getattr(self.world, "last_horror_spawn_tick", -999999) or -999999)
        return int(getattr(self.world, "tick", 0)) - last >= cooldown

    def _horror_living_cap_ready(self) -> bool:
        max_living = int(_G.get("ANCIENT_HORROR_MAX_LIVING", 1) or 1)
        living = [m for m in self.world.living_monsters() if m.kind == MonsterKind.ANCIENT_HORROR]
        return len(living) < max_living

    def _register_horror_spawn(self, horror: Monster, *, title: str, region_id: int, category: str, text: str) -> None:
        world = self.world
        world.register_monster(horror) if hasattr(world, "register_monster") else world.monsters.__setitem__(horror.id, horror)
        world.generated_monsters_by_kind[horror.kind] += 1
        world.last_horror_spawn_tick = world.tick
        if hasattr(world, "spawned_horror_titles"):
            world.spawned_horror_titles.add(title)
        world.log(text, importance=4, category=category)

    def _try_natural_horror_omen(self) -> bool:
        world = self.world
        dominant = self._dominant_polity()
        if dominant is None:
            return False
        dominance = len(getattr(dominant, "region_ids", []) or []) / max(1, len(world.regions))
        if dominance <= float(_G.get("ANCIENT_HORROR_DOMINANCE_RATIO", 0.25)):
            return False
        if world.tick - getattr(dominant, "last_horror_tick", -999999) < int(_G.get("ANCIENT_HORROR_COOLDOWN_TICKS", 540) or 0):
            return False
        titles = self._available_horror_titles_for_day("omen")
        if not titles:
            return False
        chance = self._natural_horror_chance(dominance)
        # Last step is always the roll; natural emergence remains rare.
        if self.rng.random() >= chance:
            return False
        title = self.rng.choice(titles)
        target_region_id = dominant.capital_region_id if dominant.capital_region_id in world.regions else list(dominant.region_ids)[0]
        horror = self._make_horror(target_region_id, title=title)
        if horror is None:
            return False
        dominant.last_horror_tick = world.tick
        self._register_horror_spawn(
            horror,
            title=title,
            region_id=target_region_id,
            category="monster_spawn",
            text=f"On its omen day, the ancient horror {title} awakens beneath {world.region_name(target_region_id)} as {dominant.name} spreads across the continent.",
        )
        return True

    def _try_horror_summon_day(self) -> bool:
        world = self.world
        titles = self._available_horror_titles_for_day("summon")
        if not titles:
            return False
        candidates = [
            a for a in world.living_actors()
            if a.is_adventurer()
            and a.role == Role.WIZARD
            and a.is_evil()
            and not getattr(a, "retired", False)
            and int(getattr(a, "level", 1) or 1) >= int(_G.get("ANCIENT_HORROR_SUMMON_MIN_LEVEL", 6) or 6)
            and int(getattr(a, "reputation", 0) or 0) >= int(_G.get("ANCIENT_HORROR_SUMMON_MIN_REP", 12) or 12)
        ]
        if not candidates:
            return False
        if self.rng.random() >= float(_G.get("ANCIENT_HORROR_SUMMON_ATTEMPT_CHANCE", 0.06) or 0.06):
            return False
        wizard = max(candidates, key=lambda a: (a.level, a.reputation, a.intelligence, a.wisdom, a.luck))
        title = self.rng.choice(titles)
        region_id = getattr(wizard, "region_id", None)
        if region_id not in world.regions:
            region_id = self.rng.choice(list(world.regions.keys()))
        success_score = wizard.level * 10 + wizard.intelligence + wizard.wisdom + wizard.reputation // 2 + self.rng.randint(1, 60)
        target_score = 95 + self.rng.randint(1, 50)
        if success_score < target_score:
            # The ritual does not call the horror. Sometimes the caster pays anyway.
            if self.rng.random() < float(_G.get("ANCIENT_HORROR_SUMMON_CASTER_DEATH_CHANCE", 0.35) or 0.35):
                wizard.death_monster_id = None
                self._mark_actor_dead(wizard, f"failed ritual to summon {title}", importance=3)
                world.log(f"On the forbidden day of {title}, {wizard.short_name()} attempts the rite and is consumed before anything answers.", importance=3, category="horror_summon_failed")
            else:
                wizard.recovering = max(getattr(wizard, "recovering", 0), self.rng.randint(12, 45))
                wizard.reputation = max(0, getattr(wizard, "reputation", 0) - 3)
                world.log(f"On the forbidden day of {title}, {wizard.short_name()} attempts the rite, but the summons fails and leaves only sickness and bad dreams.", importance=2, category="horror_summon_failed")
            return True
        horror = self._make_horror(region_id, title=title)
        if horror is None:
            return False
        pact_score = wizard.level * 10 + wizard.charisma + wizard.intelligence + wizard.wisdom + wizard.luck + self.rng.randint(1, 70)
        pact_target = horror.effective_power() + 75 + self.rng.randint(1, 80)
        pact_success = pact_score >= pact_target and self.rng.random() < float(_G.get("ANCIENT_HORROR_SUMMON_PACT_BASE", 0.55) or 0.55)
        if pact_success:
            horror.patron_actor_id = wizard.id
            horror.patron_deity = wizard.deity
            wizard.reputation += 8
            wizard.gain_experience(350) if hasattr(wizard, "gain_experience") else None
            text = f"On the forbidden day of {title}, {wizard.short_name()} summons {title} in {world.region_name(region_id)} and survives the pact; the horror remains free, but marked by the bargain."
            category = "horror_pact"
        else:
            if self.rng.random() < float(_G.get("ANCIENT_HORROR_SUMMON_CASTER_DEATH_CHANCE", 0.35) or 0.35):
                wizard.death_monster_id = horror.id
                self._mark_actor_dead(wizard, f"failed pact with {title}", importance=3)
                horror.monster_kills_adventurers = getattr(horror, "monster_kills_adventurers", 0) + 1
                outcome = "devours the summoner"
            else:
                wizard.recovering = max(getattr(wizard, "recovering", 0), self.rng.randint(30, 90))
                wizard.reputation = max(0, getattr(wizard, "reputation", 0) - 6)
                outcome = "breaks the pact and leaves the summoner ruined"
            world.adjust_region_state(region_id, control_delta=-8, order_delta=-15)
            text = f"On the forbidden day of {title}, {wizard.short_name()} summons {title} in {world.region_name(region_id)}, but the pact fails; the horror {outcome} and rampages free."
            category = "horror_pact_failed"
        self._register_horror_spawn(horror, title=title, region_id=region_id, category=category, text=text)
        return True

    def _maybe_spawn_horror_for_dominance(self) -> bool:
        world = self.world
        if not self._horror_living_cap_ready():
            return False
        if not self._horror_world_cooldown_ready():
            return False
        # Summoning is checked first because it depends on an actor choosing the rite.
        if self._try_horror_summon_day():
            return True
        return self._try_natural_horror_omen()



    def _is_current_ruler(self, actor: Actor) -> bool:
        if actor is None or not actor.alive or getattr(actor, "polity_id", None) is None:
            return False
        polity = self.world.polities.get(actor.polity_id)
        return polity is not None and polity.ruler_id == actor.id


    def _is_current_general(self, actor: Actor) -> bool:
        if actor is None or not actor.alive or getattr(actor, "polity_id", None) is None:
            return False
        polity = self.world.polities.get(actor.polity_id)
        return polity is not None and getattr(polity, "general_id", None) == actor.id


    def _ruler_governance_turn(self, actor: Actor) -> bool:
        world = self.world
        if not self._is_current_ruler(actor):
            return False
        polity = world.polities.get(actor.polity_id)
        if polity is None:
            return False

        # Rulers usually administer from inside their own realm instead of
        # wandering like normal adventurers.
        if actor.region_id not in polity.region_ids:
            capital = polity.capital_region_id
            if capital in world.regions and self.rng.random() < 0.75:
                world.move_actor(actor, capital) if hasattr(world, "move_actor") else setattr(actor, "region_id", capital)
                self._spend_action(actor)
                if self.rng.random() < 0.20:
                    world.log(f"{actor.short_name()} returns to {world.region_name(capital)} to hold court over {polity.name}.", importance=1, category="polity")
                return True

        if self.rng.random() >= 0.65:
            return False

        target_region_id = actor.region_id if actor.region_id in polity.region_ids else polity.capital_region_id
        if target_region_id in world.regions:
            region = world.regions[target_region_id]
            order_gain = 2 if actor.is_good() else 1
            control_gain = 1 if not actor.is_evil() else -1
            world.adjust_region_state(target_region_id, control_delta=control_gain, order_delta=order_gain)
            polity.legitimacy = min(100, polity.legitimacy + 1)
            polity.stability = min(100, polity.stability + 1)
            actor.recovering = max(actor.recovering, 1)
            self._spend_action(actor)
            if self.rng.random() < 0.20:
                world.log(f"{actor.short_name()} holds court in {region.name}, steadying {polity.name}.", importance=1, category="polity")
            return True
        return False


    def _polity_general_candidates(self, polity: Polity) -> List[Actor]:
        world = self.world
        ruler = world.actors.get(polity.ruler_id)
        candidates = []
        for aid in list(getattr(polity, "member_actor_ids", [])):
            actor = world.actors.get(aid)
            if actor is None or not actor.alive or actor.id == polity.ruler_id:
                continue
            if self._actor_rules_active_polity(actor):
                continue
            if not actor.is_adventurer() or getattr(actor, "retired", False):
                continue
            if ruler is not None and not self._actor_can_join_polity(actor, ruler):
                continue
            candidates.append(actor)
        return candidates


    def _appoint_polity_general(self, polity: Polity) -> Optional[Actor]:
        self._sync_polity_military_offices(polity)
        general = self.world.actors.get(getattr(polity, "general_id", None)) if getattr(polity, "general_id", None) is not None else None
        if general is not None and general.alive and general.polity_id == polity.id and general.id != polity.ruler_id:
            return general
        generals = self._polity_generals(polity)
        if generals:
            primary = max(generals, key=self._officer_score)
            polity.general_id = primary.id
            return primary
        polity.general_id = None
        return None


    def _ensure_polity_military(self, polity: Polity) -> Optional[Party]:
        """Build/refresh polity-owned divisions without spawning soldiers.

        One controlled region maps to one division/army party.  Officers and
        enlisted slots are filled only from existing adventurers.  Numeric levy
        manpower is stored on the party/polity but never instantiated as actors.
        """
        world = self.world
        self._sync_polity_military_offices(polity)
        self._refresh_polity_levy(polity)
        if not hasattr(polity, "military_party_ids") or getattr(polity, "military_party_ids", None) is None:
            polity.military_party_ids = []

        regions = list(getattr(polity, "region_ids", []) or [])
        if not regions:
            return None

        generals = self._polity_generals(polity)
        captains = self._polity_captains(polity)
        lieutenants = [self.world.actors.get(aid) for aid in (getattr(polity, "lieutenant_by_captain", {}) or {}).values()]
        lieutenants = [a for a in lieutenants if self._valid_polity_officer(a, polity)]
        officer_ids = {a.id for a in generals + captains + lieutenants if a is not None}

        available = []
        for aid in list(getattr(polity, "member_actor_ids", []) or []):
            actor = world.actors.get(aid)
            if actor is None or actor.id in officer_ids:
                continue
            if self._military_actor_available(actor, polity):
                available.append(actor)
        available.sort(key=self._enlisted_score, reverse=True)

        parties_by_region = {}
        for pid in list(getattr(polity, "military_party_ids", []) or []):
            party = world.parties.get(pid)
            if party is None or getattr(party, "polity_id", None) != polity.id or getattr(party, "goal", None) != "military":
                continue
            rid = getattr(party, "division_region_id", None)
            if rid in regions and rid not in parties_by_region:
                parties_by_region[rid] = party

        active_party_ids = []
        used_actor_ids = set()
        primary_party = None
        for idx, rid in enumerate(regions, start=1):
            levy = int((getattr(polity, "levy_manpower_by_region", {}) or {}).get(rid, 0) or 0)
            enlisted_cap = min(
                int(_G.get("MILITARY_MAX_ENLISTED_PER_DIVISION", 30)),
                self._enlisted_capacity_for_levy(levy),
            )
            party = parties_by_region.get(rid)
            commander = None
            if generals:
                commander = generals[(idx - 1) % len(generals)]
            elif captains:
                commander = captains[(idx - 1) % len(captains)]
            if party is None:
                party = Party(id=world.next_party_id, goal="military")
                world.next_party_id += 1
                party.polity_id = polity.id
                party.division_region_id = rid
                party.division_index = idx
                party.name = self._military_unit_name(polity, rid, idx)
                party.is_large_group = True
                world.parties[party.id] = party
                world._ensure_party_history(party)
                if commander is not None:
                    world.log(f"{commander.short_name()} musters {party.name} for {polity.name}.", importance=2, category="polity")
            else:
                party.polity_id = polity.id
                party.division_region_id = rid
                party.division_index = idx
                party.name = party.name or self._military_unit_name(polity, rid, idx)
                party.is_large_group = True

            party.levy_manpower = levy
            member_ids = []
            if commander is not None and commander.alive:
                member_ids.append(commander.id)
            # Attach local officers first for flavor/cohesion.
            for officer in captains + lieutenants:
                if officer is None or not officer.alive or officer.id in member_ids or len(member_ids) >= 1 + min(6, enlisted_cap):
                    continue
                if getattr(officer, "polity_id", None) == polity.id:
                    member_ids.append(officer.id)
            for actor in available:
                if len([aid for aid in member_ids if aid not in officer_ids]) >= enlisted_cap:
                    break
                if actor.id in used_actor_ids or actor.id in member_ids:
                    continue
                member_ids.append(actor.id)
                used_actor_ids.add(actor.id)

            party.member_ids = []
            for aid in member_ids:
                actor = world.actors.get(aid)
                if actor is None or not actor.alive:
                    continue
                if actor.party_id is not None and actor.party_id != party.id:
                    old_party = world.parties.get(actor.party_id)
                    if old_party is not None and aid in old_party.member_ids:
                        old_party.member_ids.remove(aid)
                actor.party_id = party.id
                actor.polity_id = polity.id
                actor.veteran = bool(getattr(actor, "veteran", False)) or getattr(actor, "military_rank", None) is not None
                actor.military_service_ticks = int(getattr(actor, "military_service_ticks", 0) or 0) + 1
                actor.state_loyalty = max(getattr(actor, "state_loyalty", 50), 60)
                actor.polity_favor = max(getattr(actor, "polity_favor", 50), 55)
                if getattr(actor, "loyalty", None) is None or getattr(actor, "loyalty", None) == actor.id or getattr(actor, "polity_favor", 50) >= int(_G.get("POLITY_SUCCESSION_PERSONAL_LOYALTY_THRESHOLD", 55)):
                    actor.loyalty = polity.ruler_id
                party.member_ids.append(aid)
            if party.member_ids:
                party.leader_id = party.member_ids[0]
            world._update_party_history(party)
            active_party_ids.append(party.id)
            if primary_party is None:
                primary_party = party

        # Archive stale military parties no longer tied to controlled regions.
        stale = [pid for pid in list(getattr(polity, "military_party_ids", []) or []) if pid not in active_party_ids]
        for pid in stale:
            party = world.parties.get(pid)
            if party is not None:
                world.archive_party(party, f"Disbanded after {polity.name} reorganized its divisions")
        polity.military_party_ids = active_party_ids
        polity.military_party_id = active_party_ids[0] if active_party_ids else None
        return primary_party


    def _polity_threat_score(self, polity: Polity, region_id: int) -> int:
        world = self.world
        region = world.regions[region_id]
        monsters = world.monsters_in_region(region_id)
        monster_score = sum(30 if m.kind == MonsterKind.ANCIENT_HORROR else 20 if m.kind == MonsterKind.DRAGON else 12 if m.kind == MonsterKind.GIANT else 4 for m in monsters if m.alive)
        enemy_polity = 25 if region.polity_id not in (None, polity.id) else 0
        if region.polity_id not in (None, polity.id) and self._polities_major_rivals_pair(polity, region.polity_id):
            enemy_polity += 20
        siege = 20 if region.under_siege_by not in (None, polity.id) else 0
        weak_order = max(0, 55 - region.order)
        border_value = 8 if region_id not in polity.region_ids else 0
        return monster_score + enemy_polity + siege + weak_order + border_value + self.rng.randint(0, 5)


    def _military_target_region(self, polity: Polity, general: Actor) -> Optional[int]:
        world = self.world
        candidates = set(polity.region_ids)
        for rid in list(polity.region_ids):
            candidates.update(world.regions[rid].neighbors)
        candidates = {rid for rid in candidates if rid in world.regions}
        if not candidates:
            return None
        current = general.region_id
        return max(candidates, key=lambda rid: (self._polity_threat_score(polity, rid), -abs(rid - current)))


    def _command_polity_military(self, polity: Polity) -> None:
        world = self.world
        cooldown = int(_G.get("MILITARY_COMMAND_COOLDOWN_TICKS", _G.get("TICKS_PER_MONTH", 120)))
        if world.tick - getattr(polity, "last_military_order_tick", -999999) < cooldown:
            return
        self._ensure_polity_military(polity)
        parties = [world.parties.get(pid) for pid in list(getattr(polity, "military_party_ids", []) or [])]
        parties = [p for p in parties if p is not None and p.member_ids]
        if not parties:
            return
        any_order = False
        for party in parties:
            commander = world.actors.get(party.leader_id) if party.leader_id is not None else None
            if commander is None or not commander.alive:
                continue
            target = self._military_target_region(polity, commander)
            if target is None or target == commander.region_id:
                continue
            for aid in list(party.member_ids):
                soldier = world.actors.get(aid)
                if soldier is not None and soldier.alive:
                    world.move_actor(soldier, target) if hasattr(world, "move_actor") else setattr(soldier, "region_id", target)
                    soldier.recovering = max(soldier.recovering, 1)
            any_order = True
            if self.rng.random() < 0.45:
                world.log(f"{commander.short_name()} leads {party.name} toward {world.region_name(target)}.", importance=2, category="polity")
        if any_order:
            polity.last_military_order_tick = world.tick


    def _adjust_military_loyalty_after_battle(self, actors: List[Actor], delta: int) -> None:
        seen = set()
        for actor in actors:
            if actor is None or not getattr(actor, "alive", False) or actor.id in seen:
                continue
            seen.add(actor.id)
            if getattr(actor, "polity_id", None) is None:
                continue
            actor.veteran = True
            actor.state_loyalty = max(-100, min(100, int(getattr(actor, "state_loyalty", 50) or 50) + delta))
            actor.polity_favor = max(-100, min(100, int(getattr(actor, "polity_favor", 50) or 50) + delta))


    def _share_military_glory(self, winners: List[Actor], casualties: int = 0) -> None:
        world = self.world
        credited = set()
        for actor in winners:
            polity_id = getattr(actor, "polity_id", None)
            if polity_id is None or polity_id in credited:
                continue
            polity = world.polities.get(polity_id)
            if polity is None:
                continue
            party = world.get_party(actor)
            if party is None or party.id != getattr(polity, "military_party_id", None):
                continue
            ruler = world.actors.get(polity.ruler_id)
            general = world.actors.get(getattr(polity, "general_id", None)) if getattr(polity, "general_id", None) is not None else None
            if ruler is not None and ruler.alive:
                ruler.reputation += 1 + (1 if casualties >= 2 else 0)
                polity.legitimacy = min(100, polity.legitimacy + 1)
            if general is not None and general.alive:
                general.reputation += 1
                general.polity_favor = min(100, getattr(general, "polity_favor", 50) + 2)
            credited.add(polity_id)

    def _alignment_compatibility(self, a: Alignment, b: Alignment) -> int:
        return 2 - (abs(a.law_axis - b.law_axis) + abs(a.moral_axis - b.moral_axis))


    def _polities_border(self, a: Polity, b: Polity) -> bool:
        for rid in getattr(a, "region_ids", []) or []:
            region = self.world.regions.get(rid)
            if region is None:
                continue
            if any(nid in set(getattr(b, "region_ids", []) or []) for nid in region.neighbors):
                return True
        return False


    def _safe_polity_lists(self, polity: Polity) -> None:
        for attr in ("allied_polity_ids", "trade_partner_ids", "hostile_polity_ids", "major_rival_ids", "major_ally_ids"):
            if not hasattr(polity, attr) or getattr(polity, attr, None) is None:
                setattr(polity, attr, [])
        if not hasattr(polity, "truce_until_by_polity") or getattr(polity, "truce_until_by_polity", None) is None:
            polity.truce_until_by_polity = {}
        if not hasattr(polity, "relationship_scores") or getattr(polity, "relationship_scores", None) is None:
            polity.relationship_scores = {}
        # Economy snapshots are maintained by FASEeco, but old saves/classes need safe defaults.
        for attr in ("economic_stockpile", "economic_demand", "economic_surplus", "economic_deficit", "trade_imports", "trade_exports"):
            current = getattr(polity, attr, None)
            if not isinstance(current, dict):
                current = {}
            for resource in ("grain", "livestock", "wood", "metal", "weapons", "armor"):
                current.setdefault(resource, 0)
            setattr(polity, attr, current)
        if not isinstance(getattr(polity, "economic_trade_partners", None), dict):
            polity.economic_trade_partners = {}
        if not hasattr(polity, "trade_dependency_score"):
            polity.trade_dependency_score = 0
        if not hasattr(polity, "shortage_pressure"):
            polity.shortage_pressure = 0
        # Normalize old string keys from dirty saves/pickles.
        try:
            polity.relationship_scores = {int(pid): int(score) for pid, score in dict(polity.relationship_scores).items()}
        except Exception:
            polity.relationship_scores = {}


    def _clamp_relationship_score(self, score: int) -> int:
        lo = int(_G.get("POLITY_RELATIONSHIP_MIN", -100))
        hi = int(_G.get("POLITY_RELATIONSHIP_MAX", 100))
        return max(lo, min(hi, int(score)))


    def _relationship_score(self, a: Optional[Polity], b_id: Optional[int]) -> int:
        if a is None or b_id is None:
            return 0
        self._safe_polity_lists(a)
        try:
            return int(getattr(a, "relationship_scores", {}).get(int(b_id), 0))
        except Exception:
            return 0


    def _set_relationship_score(self, a: Optional[Polity], b: Optional[Polity], score: int) -> None:
        if a is None or b is None or a.id == b.id:
            return
        self._safe_polity_lists(a); self._safe_polity_lists(b)
        score = self._clamp_relationship_score(score)
        a.relationship_scores[b.id] = score
        b.relationship_scores[a.id] = score


    def _adjust_polity_relationship(self, a: Optional[Polity], b: Optional[Polity], delta: int, reason: str = "") -> int:
        if a is None or b is None or a.id == b.id:
            return 0
        self._safe_polity_lists(a); self._safe_polity_lists(b)
        current = int(getattr(a, "relationship_scores", {}).get(b.id, getattr(b, "relationship_scores", {}).get(a.id, 0)) or 0)
        updated = self._clamp_relationship_score(current + int(delta))
        a.relationship_scores[b.id] = updated
        b.relationship_scores[a.id] = updated
        return updated


    def _polities_major_rivals(self, polity: Optional[Polity]) -> set[int]:
        if polity is None:
            return set()
        self._safe_polity_lists(polity)
        return set(getattr(polity, "major_rival_ids", []) or [])


    def _polities_major_allies(self, polity: Optional[Polity]) -> set[int]:
        if polity is None:
            return set()
        self._safe_polity_lists(polity)
        return set(getattr(polity, "major_ally_ids", []) or [])


    def _polities_major_rivals_pair(self, a: Optional[Polity], b_id: Optional[int]) -> bool:
        if a is None or b_id is None:
            return False
        return int(b_id) in self._polities_major_rivals(a) or self._relationship_score(a, b_id) <= int(_G.get("POLITY_MAJOR_RIVAL_THRESHOLD", -60))


    def _rulers_married(self, a: Polity, b: Polity) -> bool:
        world = self.world
        actors = getattr(world, "actors", {}) or {}
        ruler_a = actors.get(getattr(a, "ruler_id", None))
        ruler_b = actors.get(getattr(b, "ruler_id", None))
        if ruler_a is None or ruler_b is None:
            return False
        return getattr(ruler_a, "spouse_id", None) == getattr(ruler_b, "id", None) or getattr(ruler_b, "spouse_id", None) == getattr(ruler_a, "id", None)


    def _polity_trade_complementarity(self, a: Polity, b: Polity) -> int:
        """Return a small positive score when one polity's surplus fits the other's deficit."""
        self._safe_polity_lists(a); self._safe_polity_lists(b)
        score = 0
        a_sur = getattr(a, "economic_surplus", {}) or {}
        b_sur = getattr(b, "economic_surplus", {}) or {}
        a_def = getattr(a, "economic_deficit", {}) or {}
        b_def = getattr(b, "economic_deficit", {}) or {}
        for resource in ("grain", "wood", "metal", "weapons", "armor"):
            if int(a_sur.get(resource, 0)) > 0 and int(b_def.get(resource, 0)) > 0:
                score += 1
            if int(b_sur.get(resource, 0)) > 0 and int(a_def.get(resource, 0)) > 0:
                score += 1
        return score


    def _economic_relationship_pressure(self, a: Polity, b: Polity) -> int:
        """Economic diplomacy pressure layered onto feudal relationship memory."""
        self._safe_polity_lists(a); self._safe_polity_lists(b)
        delta = 0
        a_partners = getattr(a, "economic_trade_partners", {}) or {}
        b_partners = getattr(b, "economic_trade_partners", {}) or {}
        trade_volume = int(a_partners.get(b.id, 0) or b_partners.get(a.id, 0) or 0)
        if trade_volume > 0:
            delta += min(8, max(1, trade_volume // 20)) + int(_G.get("ECONOMY_TRADE_RELATIONSHIP_IMPORT_BONUS", 2))
            if int(getattr(a, "trade_dependency_score", 0)) >= 25 or int(getattr(b, "trade_dependency_score", 0)) >= 25:
                delta += int(_G.get("ECONOMY_TRADE_DEPENDENCY_ALLY_BONUS", 4))

        # Complementary economies want peace. Competing shortages create blame and friction.
        complementarity = self._polity_trade_complementarity(a, b)
        if complementarity:
            delta += min(6, complementarity * 2)
        shared_shortage = False
        for resource in ("grain", "wood", "metal", "weapons", "armor"):
            if int((getattr(a, "economic_deficit", {}) or {}).get(resource, 0)) > 0 and int((getattr(b, "economic_deficit", {}) or {}).get(resource, 0)) > 0:
                shared_shortage = True
                break
        if shared_shortage:
            delta += int(_G.get("ECONOMY_TRADE_COMPETITION_PENALTY", -2))
        if (int(getattr(a, "shortage_pressure", 0)) > 0 or int(getattr(b, "shortage_pressure", 0)) > 0) and self._polities_border(a, b):
            # Hungry neighbors get mean, especially when they already share a border.
            delta += int(_G.get("ECONOMY_TRADE_SHORTAGE_RIVAL_PENALTY", -4))
        return delta


    def _relationship_pair_pressure(self, a: Polity, b: Polity) -> int:
        """Compute slow geopolitical drift between two active polities.

        This is not a war declaration. It is persistent feudal memory:
        borders, trade, marriages, shared rivals, hegemon fear, and old hostility
        tug the score toward ally or rival status over time.
        """
        self._safe_polity_lists(a); self._safe_polity_lists(b)
        delta = 0
        if self._polities_border(a, b):
            delta += int(_G.get("POLITY_RELATIONSHIP_BORDER_FRICTION", -3))
        compat = self._alignment_compatibility(a.alignment, b.alignment)
        delta += int(compat * int(_G.get("POLITY_RELATIONSHIP_COMPATIBILITY_WEIGHT", 2)))
        if set(getattr(a, "major_rival_ids", []) or []).intersection(set(getattr(b, "major_rival_ids", []) or [])):
            delta += int(_G.get("POLITY_RELATIONSHIP_SHARED_RIVAL_BONUS", 8))
        if b.id in getattr(a, "trade_partner_ids", []) or a.id in getattr(b, "trade_partner_ids", []):
            delta += int(_G.get("POLITY_RELATIONSHIP_TRADE_BONUS", 6))
        if b.id in getattr(a, "allied_polity_ids", []) or a.id in getattr(b, "allied_polity_ids", []):
            delta += int(_G.get("POLITY_RELATIONSHIP_ALLIANCE_BONUS", 4))
        if self._rulers_married(a, b):
            delta += int(_G.get("POLITY_RELATIONSHIP_MARRIAGE_BONUS", 12))
        if self._polity_truce_active(a, b.id):
            delta += int(_G.get("POLITY_RELATIONSHIP_TRUCE_BONUS", 2))
        if b.id in getattr(a, "hostile_polity_ids", []) or a.id in getattr(b, "hostile_polity_ids", []):
            delta += int(_G.get("POLITY_RELATIONSHIP_HOSTILITY_PENALTY", -10))

        # Hegemon fear: nearby states dislike a realm that is becoming visibly larger.
        a_regions = len(getattr(a, "region_ids", []) or [])
        b_regions = len(getattr(b, "region_ids", []) or [])
        if self._polities_border(a, b) and abs(a_regions - b_regions) >= 2:
            delta += int(_G.get("POLITY_RELATIONSHIP_HEGEMON_FEAR_PENALTY", -6))
        delta += self._economic_relationship_pressure(a, b)
        return delta


    def _sync_major_relationships(self) -> None:
        if not bool(_G.get("POLITY_RELATIONSHIPS_ENABLED", True)):
            return
        world = self.world
        alive_ids = set(world.polities.keys())
        rival_threshold = int(_G.get("POLITY_MAJOR_RIVAL_THRESHOLD", -60))
        ally_threshold = int(_G.get("POLITY_MAJOR_ALLY_THRESHOLD", 60))
        max_rivals = int(_G.get("POLITY_MAX_MAJOR_RIVALS", 2))
        max_allies = int(_G.get("POLITY_MAX_MAJOR_ALLIES", 2))

        # First clean and decay.
        for polity in world.polities.values():
            self._safe_polity_lists(polity)
            clean = {}
            for pid, raw_score in dict(getattr(polity, "relationship_scores", {}) or {}).items():
                try:
                    pid = int(pid)
                    score = int(raw_score)
                except Exception:
                    continue
                if pid not in alive_ids or pid == polity.id:
                    continue
                if pid in set(getattr(polity, "allied_polity_ids", []) or []) and score < 25:
                    score = 35
                if pid in set(getattr(polity, "trade_partner_ids", []) or []) and score < 10:
                    score = 15
                if pid in set(getattr(polity, "hostile_polity_ids", []) or []) and score > -25:
                    score = -35
                if score > 0:
                    score = max(0, score - int(_G.get("POLITY_RELATIONSHIP_DECAY_POSITIVE", 1)))
                elif score < 0:
                    score = min(0, score + int(_G.get("POLITY_RELATIONSHIP_DECAY_NEGATIVE", 0)))
                clean[pid] = self._clamp_relationship_score(score)
            polity.relationship_scores = clean
            polity.major_rival_ids = [pid for pid in getattr(polity, "major_rival_ids", []) if pid in alive_ids]
            polity.major_ally_ids = [pid for pid in getattr(polity, "major_ally_ids", []) if pid in alive_ids]

        # Then apply pair pressure symmetrically.
        polities = list(world.polities.values())
        for i, a in enumerate(polities):
            for b in polities[i + 1:]:
                delta = self._relationship_pair_pressure(a, b)
                if delta:
                    self._adjust_polity_relationship(a, b, delta, reason="geopolitics")

        # Derive major allies/rivals from scores. Major allies cannot also be major rivals.
        for polity in world.polities.values():
            self._safe_polity_lists(polity)
            scored = [(pid, int(score)) for pid, score in getattr(polity, "relationship_scores", {}).items() if pid in alive_ids and pid != polity.id]
            rivals = [pid for pid, score in sorted(scored, key=lambda item: item[1]) if score <= rival_threshold][:max_rivals]
            allies = [pid for pid, score in sorted(scored, key=lambda item: item[1], reverse=True) if score >= ally_threshold and pid not in rivals][:max_allies]
            polity.major_rival_ids = rivals
            polity.major_ally_ids = allies
            # Keep legacy lists useful for old UI/summary/combat logic.
            polity.hostile_polity_ids = list(dict.fromkeys(list(getattr(polity, "hostile_polity_ids", []) or []) + rivals))
            polity.hostile_polity_ids = [pid for pid in polity.hostile_polity_ids if pid in alive_ids and pid != polity.id and self._relationship_score(polity, pid) <= -25]
            polity.allied_polity_ids = [pid for pid in getattr(polity, "allied_polity_ids", []) if pid in alive_ids and pid != polity.id and self._relationship_score(polity, pid) >= 25]
            for pid in allies:
                if pid not in polity.allied_polity_ids:
                    polity.allied_polity_ids.append(pid)

    def _form_polity_link(self, a: Polity, b: Polity, attr: str) -> bool:
        self._safe_polity_lists(a); self._safe_polity_lists(b)
        la = getattr(a, attr)
        lb = getattr(b, attr)
        if b.id not in la:
            la.append(b.id)
        if a.id not in lb:
            lb.append(a.id)
        if attr == "allied_polity_ids":
            self._adjust_polity_relationship(a, b, int(_G.get("POLITY_RELATIONSHIP_ALLIANCE_GAIN", 30)), reason="alliance")
        elif attr == "trade_partner_ids":
            self._adjust_polity_relationship(a, b, int(_G.get("POLITY_RELATIONSHIP_TRADE_PACT_GAIN", 15)), reason="trade")
        elif attr == "hostile_polity_ids":
            self._adjust_polity_relationship(a, b, int(_G.get("POLITY_RELATIONSHIP_HOSTILITY_PENALTY", -10)), reason="hostility")
        return True


    def _try_royal_marriage(self, a: Polity, b: Polity, compat: int) -> bool:
        world = self.world
        ruler_a = world.actors.get(getattr(a, "ruler_id", None))
        ruler_b = world.actors.get(getattr(b, "ruler_id", None))
        if ruler_a is None or ruler_b is None or not ruler_a.alive or not ruler_b.alive:
            return False
        if getattr(ruler_a, "spouse_id", None) is not None or getattr(ruler_b, "spouse_id", None) is not None:
            return False
        if getattr(ruler_a, "id", None) == getattr(ruler_b, "id", None):
            return False
        if compat < 1:
            return False
        if getattr(ruler_a, "sex", None) is not None and getattr(ruler_b, "sex", None) is not None and ruler_a.sex == ruler_b.sex:
            return False
        if self._calculate_age(ruler_a) < 18 or self._calculate_age(ruler_b) < 18:
            return False
        if ruler_a.is_ideological_enemy(ruler_b):
            return False
        friendly = (b.id in getattr(a, "allied_polity_ids", []) or b.id in getattr(a, "trade_partner_ids", []))
        if not friendly:
            return False
        chance = float(_G.get("DIPLOMACY_ROYAL_MARRIAGE_BASE_CHANCE", 0.06)) + max(0, compat) * 0.025
        if self.rng.random() >= min(0.35, chance):
            return False
        ruler_a.spouse_id = ruler_b.id
        ruler_b.spouse_id = ruler_a.id
        if getattr(ruler_a, "best_friend_id", None) is None:
            ruler_a.best_friend_id = ruler_b.id
        if getattr(ruler_b, "best_friend_id", None) is None:
            ruler_b.best_friend_id = ruler_a.id
        self._set_polity_truce(a, b, ticks=int(_G.get("DIPLOMACY_TRUCE_TICKS", TICKS_PER_YEAR * 2)))
        self._adjust_polity_relationship(a, b, int(_G.get("POLITY_RELATIONSHIP_ROYAL_MARRIAGE_GAIN", 45)), reason="royal marriage")
        world.log(
            f"{ruler_a.short_name()} of {a.name} and {ruler_b.short_name()} of {b.name} bind their houses in marriage; both realms remain sovereign.",
            importance=3,
            category="diplomacy",
        )
        return True


    def _update_polity_diplomacy(self) -> None:
        if not bool(_G.get("DIPLOMACY_ENABLED", True)):
            return
        world = self.world
        if world.tick % max(1, int(_G.get("DIPLOMACY_CHECK_TICKS", TICKS_PER_MONTH * 3))) != 0:
            return
        polities = list(world.polities.values())
        for polity in polities:
            self._safe_polity_lists(polity)
            alive_ids = set(world.polities.keys())
            polity.allied_polity_ids = [pid for pid in polity.allied_polity_ids if pid in alive_ids]
            polity.trade_partner_ids = [pid for pid in polity.trade_partner_ids if pid in alive_ids]
            polity.hostile_polity_ids = [pid for pid in polity.hostile_polity_ids if pid in alive_ids]
            polity.truce_until_by_polity = {pid: until for pid, until in polity.truce_until_by_polity.items() if pid in alive_ids and until > world.tick}
        if len(polities) < 2:
            return
        self._sync_major_relationships()
        for i, a in enumerate(polities):
            for b in polities[i+1:]:
                if b.id in getattr(a, "allied_polity_ids", []) and b.id in getattr(a, "trade_partner_ids", []):
                    continue
                if not self._polities_border(a, b) and self.rng.random() > 0.25:
                    continue
                compat = self._alignment_compatibility(a.alignment, b.alignment)
                shared_enemy = bool(set(getattr(a, "hostile_polity_ids", []) or []).intersection(set(getattr(b, "hostile_polity_ids", []) or [])))
                if len(getattr(a, "allied_polity_ids", []) or []) < int(_G.get("POLITY_MAX_MAJOR_ALLIES", _G.get("DIPLOMACY_MAX_ALLIES", 2))) and len(getattr(b, "allied_polity_ids", []) or []) < int(_G.get("POLITY_MAX_MAJOR_ALLIES", _G.get("DIPLOMACY_MAX_ALLIES", 2))):
                    rel_score = self._relationship_score(a, b.id)
                    if rel_score <= int(_G.get("POLITY_MAJOR_RIVAL_THRESHOLD", -60)):
                        continue
                    chance = float(_G.get("DIPLOMACY_ALLIANCE_BASE_CHANCE", 0.10))
                    chance += max(0, compat) * 0.04
                    chance += 0.06 if shared_enemy else 0.0
                    chance += max(0.0, rel_score / 100.0) * 0.10
                    chance += 0.04 if self._polity_truce_active(a, b.id) else 0.0
                    if compat >= -1 and self.rng.random() < chance:
                        self._form_polity_link(a, b, "allied_polity_ids")
                        self._set_polity_truce(a, b)
                        world.log(f"{a.name} and {b.name} swear a defensive alliance.", importance=2, category="diplomacy")
                if len(getattr(a, "trade_partner_ids", []) or []) < int(_G.get("DIPLOMACY_MAX_TRADE_PARTNERS", 4)) and len(getattr(b, "trade_partner_ids", []) or []) < int(_G.get("DIPLOMACY_MAX_TRADE_PARTNERS", 4)):
                    rel_score = self._relationship_score(a, b.id)
                    chance = float(_G.get("DIPLOMACY_TRADE_BASE_CHANCE", 0.18))
                    chance += 0.04 if self._polities_border(a, b) else 0.0
                    chance += max(0, compat) * 0.02
                    chance += max(-0.10, rel_score / 500.0)
                    chance += min(0.12, self._polity_trade_complementarity(a, b) * 0.025)
                    if rel_score > int(_G.get("POLITY_MAJOR_RIVAL_THRESHOLD", -60)) and self.rng.random() < chance:
                        self._form_polity_link(a, b, "trade_partner_ids")
                        world.log(f"{a.name} and {b.name} open a trade pact between their realms.", importance=2, category="diplomacy")
                self._try_royal_marriage(a, b, compat)
        self._sync_major_relationships()
        for polity in polities:
            rival_bonus = min(4, len(getattr(polity, "major_rival_ids", []) or []) * int(_G.get("POLITY_RELATIONSHIP_RIVAL_COHESION_BONUS", 2)))
            ally_bonus = min(6, len(getattr(polity, "allied_polity_ids", []) or []) * int(_G.get("DIPLOMACY_ALLIANCE_STABILITY_BONUS", 2)))
            trade_bonus = min(4, len(getattr(polity, "trade_partner_ids", []) or []) * int(_G.get("DIPLOMACY_TRADE_STABILITY_BONUS", 1)))
            if ally_bonus or trade_bonus or rival_bonus:
                polity.stability = min(100, int(getattr(polity, "stability", 50)) + ally_bonus + trade_bonus + rival_bonus)
                polity.legitimacy = min(100, int(getattr(polity, "legitimacy", 50)) + max(0, ally_bonus // 2))
                for rid in getattr(polity, "region_ids", []) or []:
                    region = world.regions.get(rid)
                    if region is not None and getattr(polity, "trade_partner_ids", None):
                        region.order = min(100, int(getattr(region, "order", 50)) + int(_G.get("DIPLOMACY_TRADE_ORDER_BONUS", 1)))


    def _maybe_shift_actor_alignment_toward_evil(self, actor: Actor) -> bool:
        if actor.alignment.moral_axis < 0:
            return False
        law = actor.alignment.law_axis
        if actor.alignment.moral_axis > 0:
            candidates = [a for a in Alignment if a.law_axis == law and a.moral_axis == 0]
        else:
            candidates = [a for a in Alignment if a.law_axis == law and a.moral_axis < 0]
        if not candidates:
            return False
        actor.alignment = candidates[0]
        return True


    def _apply_elite_corruption_drift(self) -> None:
        if not bool(_G.get("ELITE_CORRUPTION_ENABLED", True)):
            return
        world = self.world
        if world.tick % max(1, int(_G.get("ELITE_CORRUPTION_CHECK_TICKS", TICKS_PER_MONTH))) != 0:
            return
        candidates = []
        stock_threshold = int(_G.get("ELITE_CORRUPTION_PROSPERITY_STOCKPILE_THRESHOLD", 150))
        min_order = int(_G.get("ELITE_CORRUPTION_MIN_ORDER", 65))
        for polity in world.polities.values():
            prosperous_regions = []
            for rid in getattr(polity, "region_ids", []) or []:
                region = world.regions.get(rid)
                if region is None or int(getattr(region, "order", 0)) < min_order:
                    continue
                stock = getattr(region, "stockpile", {}) or {}
                wealth = int(stock.get("grain", 0)) + int(stock.get("livestock", 0)) + int(stock.get("weapons", 0)) * 6 + int(stock.get("armor", 0)) * 8
                if wealth >= stock_threshold:
                    prosperous_regions.append(region)
            if not prosperous_regions:
                continue
            ids = {polity.ruler_id} | self._polity_officer_ids(polity)
            for aid in ids:
                actor = world.actors.get(aid)
                if actor is None or not actor.alive or actor.is_evil():
                    continue
                role_label = "ruler" if aid == polity.ruler_id else str(getattr(actor, "military_rank", "officer") or "officer").lower()
                if not self._elite_corruption_actor_ready(polity, actor, role_label):
                    continue
                if getattr(actor, "reputation", 0) < int(_G.get("ELITE_CORRUPTION_MIN_REPUTATION", 40)) and aid != polity.ruler_id:
                    continue
                candidates.append((polity, actor, len(prosperous_regions)))
        if not candidates:
            return
        self.rng.shuffle(candidates)
        changed = 0
        max_monthly = int(_G.get("ELITE_CORRUPTION_MAX_MONTHLY_ACTORS", 6))
        for polity, actor, prosperity in candidates:
            if changed >= max_monthly:
                break
            chance = float(_G.get("ELITE_CORRUPTION_BASE_CHANCE", 0.035))
            chance += min(0.05, prosperity * 0.008)
            chance += min(0.04, max(0, getattr(actor, "reputation", 0) - 80) * 0.0004)
            chance += 0.01 if actor.id == polity.ruler_id else 0.0
            chance *= self._elite_corruption_character_multiplier(actor)
            chance = max(0.0, min(0.95, chance))
            if self.rng.random() >= chance:
                continue
            did = False
            if self.rng.random() < float(_G.get("ELITE_CORRUPTION_DEITY_SHIFT_CHANCE", 0.35)):
                if getattr(actor, "deity", None) != Deity.LORD_OF_DARKNESS and not getattr(actor, "locked_deity", False):
                    actor.deity = Deity.LORD_OF_DARKNESS
                    actor.deity_conviction = max(20, int(getattr(actor, "deity_conviction", 50)) - 15)
                    did = True
            if self.rng.random() < float(_G.get("ELITE_CORRUPTION_ALIGNMENT_SHIFT_CHANCE", 0.22)):
                did = self._maybe_shift_actor_alignment_toward_evil(actor) or did
            if did:
                changed += 1
                actor.elite_corruption_window_resolved = True
                actor.polity_favor = min(100, getattr(actor, "polity_favor", 50) + 5)
                if changed <= 2:
                    world.log(f"Comfort and privilege begin to corrupt {actor.short_name()} of {polity.name}.", importance=2, category="corruption")


    def _ruler_title_for(self, actor: Actor, region: Region) -> str:
        sex = str(getattr(actor, "sex", "")).upper()
        female = sex.startswith("F")

        if actor.is_good():
            return f"{'Queen' if female else 'King'} of {region.name}"
        if actor.is_evil():
            return f"{'Tyrant Queen' if female else 'Tyrant'} of {region.name}"
        return f"{'Lady' if female else 'Master'} of {region.name}"


    def _update_polities(self) -> None:
        world = self.world
        self._handle_polity_succession()
        self._update_polity_diplomacy()
        self._apply_elite_corruption_drift()
        # Formation
        min_rep, min_party_size = self._dynamic_polity_thresholds()
        for party in list(world.parties.values()):
            if party.leader_id is None or len(party.member_ids) < min_party_size:
                continue
            leader = world.actors.get(party.leader_id)
            if leader is None or not leader.alive or leader.polity_id is not None:
                continue
            if not self._eligible_polity_ruler(leader):
                continue
            if leader.reputation < min_rep:
                continue
            region = world.regions[leader.region_id]
            if abs(region.control) < 30:
                continue
            polity = world.create_polity(leader, leader.region_id, party.member_ids)
            if polity is None:
                continue
            if leader.title is None or str(leader.title).startswith("First in Class of "):
                leader.title = self._ruler_title_for(leader, region)
            polity.succession_grace_until = max(getattr(polity, "succession_grace_until", -999999), world.tick + int(_G.get("SUCCESSION_GRACE_TICKS", TICKS_PER_YEAR)))
            self._ensure_polity_military(polity)
        # Loyalty drift and region claims
        for polity in list(world.polities.values()):
            ruler = world.actors.get(polity.ruler_id)
            if ruler is None or not ruler.alive:
                continue
            # Build member list using region buckets for the region check, then
            # add loyalty/polity_id members in a second pass.  Avoids O(polities*actors).
            _seen_ids: set = set()
            members = []
            for _rid in polity.region_ids:
                for _a in world.actors_in_region(_rid):
                    if _a.id not in _seen_ids:
                        _seen_ids.add(_a.id)
                        members.append(_a)
            for _a in world.living_actors():
                if _a.id in _seen_ids:
                    continue
                if _a.loyalty == ruler.id or getattr(_a, "polity_id", None) == polity.id:
                    _seen_ids.add(_a.id)
                    members.append(_a)
            polity.member_actor_ids = []
            for actor in members:
                existing_polity_id = getattr(actor, "polity_id", None)
                # Passive membership refresh must not steal actors from another polity.
                # Conquest, succession, and explicit defection paths may still transfer
                # actors elsewhere; this routine is not an implicit transfer path.
                if existing_polity_id is not None and existing_polity_id != polity.id:
                    continue
                if self._actor_can_join_polity(actor, ruler):
                    actor.polity_id = polity.id
                    actor.polity_favor = max(getattr(actor, "polity_favor", 50), 55)
                    actor.state_loyalty = max(getattr(actor, "state_loyalty", 50), 55)
                    if getattr(actor, "loyalty", None) is None or getattr(actor, "loyalty", None) == actor.id or getattr(actor, "polity_favor", 50) >= int(_G.get("POLITY_SUCCESSION_PERSONAL_LOYALTY_THRESHOLD", 55)):
                        actor.loyalty = ruler.id
                    polity.member_actor_ids.append(actor.id)
            polity.strength = sum(world.actors[aid].power_rating() for aid in polity.member_actor_ids if aid in world.actors)
            self._sync_polity_military_offices(polity)
            self._ensure_polity_military(polity)
            self._command_polity_military(polity)
            world._update_polity_history(polity)
            # claim adjacent regions with sufficient friendly presence
            candidate_regions = set()
            for region_id in list(polity.region_ids):
                candidate_regions.update(world.regions[region_id].neighbors)
            for region_id in candidate_regions:
                region = world.regions[region_id]
                if region.polity_id is not None:
                    continue
                local_members = [a for a in polity.member_actor_ids if world.actors[a].region_id == region_id]
                if len(local_members) >= 3 and self.rng.random() < 0.08:
                    region.polity_id = polity.id
                    polity.region_ids.append(region_id)
                    world.log(f"{polity.name} extends its protection over {region.name}.", importance=3, category="polity")


