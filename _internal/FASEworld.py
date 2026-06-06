from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import random
from FASEcfg import *
from FASEclass import *

class WorldBuildMixin:
    def _build_world(self, seed: str) -> World:
        regions = self._generate_regions(REGION_COUNT)
        scaled_initial_population = max(1, int(round(INITIAL_POPULATION * self.population_scale)))
        actors = self._generate_population(scaled_initial_population, regions)
        for actor in actors.values():
            if actor.is_adventurer():
                actor.duty_shift = self.rng.randrange(ADVENTURER_SHIFT_COUNT)
        monsters = self._generate_initial_monsters(regions)
        world = World(rng=self.rng, regions=regions, actors=actors, monsters=monsters, parties={}, seed_used=seed)
        world.rebuild_runtime_caches()
        world.next_actor_id = max(actors.keys(), default=0) + 1
        world.spawned_horror_titles = set(self._spawned_horror_titles)
        world.generated_by_role = self._count_generated_roles(actors)
        world.generated_monsters_by_kind = self._count_generated_monsters(monsters)
        world.region_activity = {rid: 0 for rid in regions}
        world.refugee_arrivals = 0
        world.refugee_commoners = 0
        world.population_scale = self.population_scale
        world.source_files = {
            "simulator": "FASE.py",
            "class": "FASEclass.py",
            "population": "FASEpop.py",
            "legacy": "FASEleg.py",
            "relics": "FASErlc.py",
            "summary": "FASEsum.py",
            "economy": "FASEeco.py",
            "monsters": "FASEmon.py",
            "politics": "FASEpoli.py",
        }
        self._seed_relics(world)
        world.initial_population = scaled_initial_population
        world.log(
            "A small continent of farms, forests, rivers, highlands, mountains, swamps, wastelands, and cold frontiers fills with common folk, wandering adventurers, lurking monsters, and distant divine attention.",
            importance=3,
            category="world",
        )
        return world


    def _count_generated_roles(self, actors: Dict[int, Actor]) -> Dict[Role, int]:
        counts = {role: 0 for role in Role}
        for actor in actors.values():
            counts[actor.role] += 1
        return counts


    def _count_generated_monsters(self, monsters: Dict[int, Monster]) -> Dict[MonsterKind, int]:
        counts = {kind: 0 for kind in MonsterKind}
        for monster in monsters.values():
            counts[monster.kind] += 1
        return counts


    def _generate_regions(self, count: int) -> Dict[int, Region]:
        regions: Dict[int, Region] = {}
        used_names = set()

        for region_id in range(count):
            biome = BIOMES[region_id % len(BIOMES)]
            size_factor = self.rng.uniform(REGION_SIZE_MIN, REGION_SIZE_MAX)
            profile = self._biome_profile(biome)
            cap_min, cap_max = self._biome_capacity_range(profile, biome)
            base_capacity = int(self.rng.randint(cap_min, cap_max) * size_factor * self.population_scale)
            regions[region_id] = Region(
                id=region_id,
                name=self._unique_region_name(used_names),
                biome=biome,
                danger=self.rng.randint(1, 5),
                base_capacity=base_capacity,
                size_factor=size_factor,
            )
        for region_id in range(count):
            neighbors = set()
            if region_id > 0:
                neighbors.add(region_id - 1)
            if region_id < count - 1:
                neighbors.add(region_id + 1)
            while len(neighbors) < min(3, count - 1) and self.rng.random() < 0.55:
                pick = self.rng.randrange(count)
                if pick != region_id:
                    neighbors.add(pick)
            regions[region_id].neighbors = sorted(neighbors)
        for region_id, region in regions.items():
            for neighbor_id in list(region.neighbors):
                if region_id not in regions[neighbor_id].neighbors:
                    regions[neighbor_id].neighbors.append(region_id)
                    regions[neighbor_id].neighbors.sort()
        return regions


    def _unique_region_name(self, used_names: set[str]) -> str:
        while True:
            name = f"{self.rng.choice(REGION_PREFIXES)}{self.rng.choice(REGION_SUFFIXES)}"
            if name not in used_names:
                used_names.add(name)
                return name


    def _biome_profile(self, biome_or_region) -> dict:
        """Return config profile for either a biome name or a Region object.

        Population/economy/UX callers may pass a Region, while worldgen passes
        the biome string directly. Region is unhashable, so normalize before
        looking up BIOME_PROFILES.
        """
        profiles = globals().get("BIOME_PROFILES", {}) or {}
        if hasattr(biome_or_region, "biome"):
            biome = getattr(biome_or_region, "biome", "")
        else:
            biome = biome_or_region
        key = str(biome or "")
        profile = (
            profiles.get(key)
            or profiles.get(key.title())
            or profiles.get(key.replace("_", " ").title())
        )
        if isinstance(profile, dict):
            return profile
        return {}


    def _biome_capacity_range(self, profile: dict, biome: str) -> Tuple[int, int]:
        cap = profile.get("capacity") if isinstance(profile, dict) else None
        if isinstance(cap, (tuple, list)) and len(cap) >= 2:
            return int(cap[0]), int(cap[1])
        if biome == "Plains":
            return PLAINS_CAP_MIN, PLAINS_CAP_MAX
        if biome == "Forest":
            return FOREST_CAP_MIN, FOREST_CAP_MAX
        return HIGHLANDS_CAP_MIN, HIGHLANDS_CAP_MAX


    def _region_base_capacity(self, biome: str) -> int:
        profile = self._biome_profile(biome)
        low, high = self._biome_capacity_range(profile, biome)
        size_factor = self.rng.uniform(REGION_SIZE_MIN, REGION_SIZE_MAX)
        return int(self.rng.randint(low, high) * size_factor)


    def _effective_region_capacity(self, region) -> int:
        capacity = max(1, getattr(region, "base_capacity", 1_000_000))
        modifier = 1.0
        modifier *= 0.75 + (region.order / 200.0)          # 0.75 .. 1.25
        modifier *= 0.85 + (max(-50, region.control) / 400.0)  # ~0.725 .. 1.10
        modifier *= max(0.70, 1.05 - (region.danger * 0.05))   # danger pressure
        return max(1000, int(capacity * modifier))


    def _generate_initial_monsters(self, regions: Dict[int, Region]) -> Dict[int, Monster]:
        # Monster grace period: default is no initial monsters when the
        # world starts under a monster delay. Set MONSTER_GRACE_YEARS = 0
        # in fantfarm to restore immediate monster seeding.
        if max(0, int(globals().get("MONSTER_GRACE_YEARS", 0))) > 0:
            return {}
        monsters: Dict[int, Monster] = {}
        seeded_horror = False
        for region_id in regions:
            goblins = self.rng.randint(2, 5)
            for _ in range(goblins):
                monster = self._make_goblin(region_id)
                monsters[monster.id] = monster
            if self.rng.random() < 0.15:
                monster = self._make_giant(region_id)
                monsters[monster.id] = monster
            if self.rng.random() < 0.01:
                monster = self._make_dragon(region_id)
                monsters[monster.id] = monster
            if (not seeded_horror) and self.rng.random() < 0.03:
                monster = self._make_horror(region_id)
                if monster is not None:
                    monsters[monster.id] = monster
                    seeded_horror = True
        return monsters

    def _monster_birth_tick(self) -> int:
        world = getattr(self, "world", None)
        return int(getattr(world, "tick", 0)) if world is not None else 0

    def _roll_lifespan_ticks(self, lifespan_years) -> int:
        try:
            low, high = lifespan_years
            years = self.rng.randint(int(low), int(high))
            return max(1, years) * TICKS_PER_YEAR
        except Exception:
            return 0

    def _monster_default_deity(self, kind: MonsterKind, *, dragon_temperament: str = "", giant_type: str = ""):
        """Assign loose monster religious leaning. This is not human-style worship.

        Goblins are the only consistent monster-followers. Benevolent dragons
        lean toward Light. Other dragons and horrors do not worship human gods.
        Giants are usually atheistic/unaligned, with a small Chance lean.
        """
        if kind == MonsterKind.GOBLIN:
            return self.rng.choices(
                [Deity.LORD_OF_DARKNESS, Deity.GOD_OF_CHANCE, None],
                weights=[55, 35, 10],
                k=1,
            )[0]
        if kind == MonsterKind.DRAGON:
            if dragon_temperament == "benevolent":
                return self.rng.choices([Deity.LORD_OF_LIGHT, None], weights=[75, 25], k=1)[0]
            return None
        if kind == MonsterKind.GIANT:
            return self.rng.choices([Deity.GOD_OF_CHANCE, None], weights=[20, 80], k=1)[0]
        return None

    def _make_goblin(self, region_id: int) -> Monster:
        monster_id = self._consume_monster_id()
        return Monster(
            id=monster_id,
            name=f"Goblin rabble {monster_id}",
            kind=MonsterKind.GOBLIN,
            region_id=region_id,
            power=self.rng.randint(2, 4),
            hostility=6,
            charisma=self.rng.randint(2, 6),
            intelligence=self.rng.randint(4, 8),
            horde_size=self.rng.randint(4, 12),
            reputation=1,
            patron_deity=self._monster_default_deity(MonsterKind.GOBLIN),
            birth_tick=self._monster_birth_tick(),
            max_age_ticks=self._roll_lifespan_ticks(GOBLIN_LIFESPAN_YEARS),
        )



    def _weighted_giant_type_for_region(self, region_id: int) -> str:
        region = self.world.regions.get(region_id) if hasattr(self, "world") else None
        biome = str(getattr(region, "biome", "")).lower() if region is not None else ""
        weights = {
            "Hill Giant": 3,
            "Stone Giant": 3,
            "Frost Giant": 2,
            "Green Giant": 2,
        }
        if any(term in biome for term in ("forest", "wood", "swamp", "jungle", "green")):
            weights["Green Giant"] += 8
            weights["Hill Giant"] += 2
        if any(term in biome for term in ("hill", "plain", "field", "badland", "heath")):
            weights["Hill Giant"] += 8
        if any(term in biome for term in ("mount", "high", "stone", "rock", "pass", "crest")):
            weights["Stone Giant"] += 8
            weights["Frost Giant"] += 2
        if any(term in biome for term in ("frost", "snow", "cold", "tundra", "ice")):
            weights["Frost Giant"] += 10
        names = list(weights.keys())
        return self.rng.choices(names, weights=[weights[name] for name in names], k=1)[0]

    def _make_giant(self, region_id: int) -> Monster:
        monster_id = self._consume_monster_id()
        giant_type = self._weighted_giant_type_for_region(region_id)
        neutral = giant_type in {"Hill Giant", "Green Giant"}
        return Monster(
            id=monster_id,
            name=giant_type,
            kind=MonsterKind.GIANT,
            region_id=region_id,
            power=self.rng.randint(12, 18),
            hostility=3 if neutral else 7,
            charisma=4,
            intelligence=6,
            horde_size=1,
            reputation=2 if neutral else 5,
            giant_temperament="territorial" if neutral else "hostile",
            patron_deity=self._monster_default_deity(MonsterKind.GIANT, giant_type=giant_type),
            birth_tick=self._monster_birth_tick(),
            max_age_ticks=self._roll_lifespan_ticks(GIANT_LIFESPAN_YEARS),
        )


    def _make_dragon(self, region_id: int) -> Monster:
        monster_id = self._consume_monster_id()
        color = self.rng.choice(CHROMATIC_DRAGONS)
        temperament = self._dragon_temperament(color)
        hostility = 4 if temperament == "benevolent" else 6 if temperament == "ambivalent" else 9
        return Monster(
            id=monster_id,
            name=f"{color} Dragon",
            kind=MonsterKind.DRAGON,
            region_id=region_id,
            power=self.rng.randint(28, 40),
            hostility=hostility,
            charisma=8,
            intelligence=12,
            horde_size=1,
            reputation=12,
            dragon_color=color,
            dragon_temperament=temperament,
            patron_deity=self._monster_default_deity(MonsterKind.DRAGON, dragon_temperament=temperament),
            birth_tick=self._monster_birth_tick(),
            max_age_ticks=self._roll_lifespan_ticks(DRAGON_LIFESPAN_YEARS.get(color, (500, 1000))),
        )


    def _make_horror(self, region_id: int, title: Optional[str] = None) -> Optional[Monster]:
        available = [h for h in HORROR_TITLES if h not in self._spawned_horror_titles]
        if not available:
            return None

        if title is not None and title in available:
            name = title
        else:
            name = self.rng.choice(available)
        self._spawned_horror_titles.add(name)

        monster_id = self._consume_monster_id()
        return Monster(
            id=monster_id,
            name=name,
            kind=MonsterKind.ANCIENT_HORROR,
            region_id=region_id,
            power=self.rng.randint(35, 50),
            hostility=9,
            charisma=12,
            intelligence=16,
            horde_size=1,
            reputation=20,
            birth_tick=self._monster_birth_tick(),
            max_age_ticks=0,
        )


    def _consume_monster_id(self) -> int:
        monster_id = self._monster_id_counter
        self._monster_id_counter += 1
        return monster_id


    def _random_seed_string(self) -> str:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(random.SystemRandom().choice(alphabet) for _ in range(12))


