
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import argparse
from fractions import Fraction
import random
import time
from typing import Dict, List, Optional, Tuple
import importlib.util
import json
import sys
from pathlib import Path
from FASEclass import (
    Alignment, Role, MonsterKind, Deity,
    Region, Party, Actor, Monster, Event,
    Commemoration, World, Polity, PolityLeaderRecord, AdventurerSchool,
)
from FASEimm import build_pantheon, deity_value, GodProfile, GodState, DivineBoon, load_imrt_file, change_actor_deity, ensure_actor_religion_tracking, clear_actor_protocult_membership
try:
    from FASEimm import ImmortalAIMixin
except Exception:
    class ImmortalAIMixin:
        def _ai_immortal_tick(self):
            return None
from FASEcfg import *
from FASEeco import ensure_stockpile, region_economy_tick
from FASErg import CREATED_RELIC_TEMPLATES, BOON_DEFS as RELIC_BOON_DEFS, TIER_DEFS as RELIC_TIER_DEFS, build_relic_payload
from FASEmrg import Morgue, morgue_path
from FASEtome import Historian, tome_path

DATA_DIR = Path(__file__).resolve().parent
BASE_DIR = DATA_DIR
SUMMARY_MODULE_PATH = BASE_DIR / "FASEsum.py"
POPULATION_MODULE_PATH = BASE_DIR / "FASEpop.py"
LEGACY_MODULE_PATH = BASE_DIR / "FASEleg.py"
RELICS_MODULE_PATH = BASE_DIR / "FASErlc.py"
LORE_MODULE_PATH = BASE_DIR / "FASElore.py"

def _import_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {module_name!r} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def _story_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def _story_parse_traits(raw: str) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]

def _story_parse_sectioned_file(path: Path) -> Dict[str, Dict[str, str]]:
    data: Dict[str, Dict[str, str]] = {}
    section = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            data.setdefault(section, {})
            continue
        if "=" not in line or section is None:
            continue
        key, value = line.split("=", 1)
        data.setdefault(section, {})[key.strip().lower()] = value.strip()
    return data

def _story_safe_int(value: Optional[str], default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default

def _parse_population_scale(raw: str) -> float:
    text = str(raw).strip()
    if not text:
        raise argparse.ArgumentTypeError("Population scale cannot be empty.")
    try:
        scale = float(Fraction(text))
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            "Population scale must be a positive number or fraction like 2, 0.25, or 1/4."
        ) from exc
    if scale <= 0:
        raise argparse.ArgumentTypeError("Population scale must be greater than 0.")
    return scale

def _make_run_output_dir(seed: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(seed))
    safe = safe.strip("._") or "seed"
    return BASE_DIR / "seedRuns_v162" / safe #HEY STUPID, UPDATE THIS LINE TOO!


def _env_bool(name: str, default: bool) -> bool:
    import os
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    import os
    raw = os.environ.get(name)
    try:
        value = int(str(raw).strip()) if raw is not None and str(raw).strip() != "" else int(default)
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    return value

combat_runtime_module = _import_module_from_path("fantfarm_combat_runtime", BASE_DIR / "FASEcom.py")
CombatMixin = combat_runtime_module.CombatMixin
monster_runtime_module = _import_module_from_path("fantfarm_monster_runtime", BASE_DIR / "FASEmon.py")
MonsterMixin = monster_runtime_module.MonsterMixin
party_runtime_module = _import_module_from_path("fantfarm_party_runtime", BASE_DIR / "FASEprty.py")
PartyMixin = party_runtime_module.PartyMixin
politics_runtime_module = _import_module_from_path("fantfarm_politics_runtime", BASE_DIR / "FASEpoli.py")
PoliticsMixin = politics_runtime_module.PoliticsMixin
world_runtime_module = _import_module_from_path("fantfarm_world_runtime", BASE_DIR / "FASEworld.py")
WorldBuildMixin = world_runtime_module.WorldBuildMixin




summary = _import_module_from_path("fantfarm_summary", SUMMARY_MODULE_PATH)
population_module = _import_module_from_path("fantfarm_population", POPULATION_MODULE_PATH)
PopulationMixin = population_module.PopulationMixin
legacy_module = _import_module_from_path("fantfarm_legacy", LEGACY_MODULE_PATH)
LegacyMixin = legacy_module.LegacyMixin
relic_module = _import_module_from_path("fantfarm_relics", RELICS_MODULE_PATH)
RelicMixin = relic_module.RelicMixin
Relic = relic_module.Relic
RELIC_SPECS = relic_module.RELIC_SPECS
lore_module = _import_module_from_path("fantfarm_lore_runtime", LORE_MODULE_PATH)
LoreMixin = lore_module.LoreMixin
Song = lore_module.Song
ProtoCult = lore_module.ProtoCult
population_module.MALE_FIRST_NAMES = MALE_FIRST_NAMES
population_module.FEMALE_FIRST_NAMES = FEMALE_FIRST_NAMES
population_module.SURNAMES = SURNAMES
population_module.TRAITS = TRAITS
population_module.ROLE_WEIGHTS = ROLE_WEIGHTS
population_module.WIZARD_PROMOTION_CHANCE = WIZARD_PROMOTION_CHANCE
population_module.MONTH_NAMES = MONTH_NAMES
population_module.Alignment = Alignment
population_module.Role = Role
population_module.Deity = Deity
population_module.MonsterKind = MonsterKind
population_module.Actor = Actor
legacy_module.MALE_FIRST_NAMES = MALE_FIRST_NAMES
legacy_module.FEMALE_FIRST_NAMES = FEMALE_FIRST_NAMES
legacy_module.TRAITS = TRAITS
legacy_module.Alignment = Alignment
legacy_module.Role = Role
legacy_module.Deity = Deity
legacy_module.Actor = Actor

_RUNTIME_MODULES = [
    population_module,
    legacy_module,
    relic_module,
    party_runtime_module,
    politics_runtime_module,
    monster_runtime_module,
    combat_runtime_module,
    world_runtime_module,
    lore_module,
]

def _inject_runtime_globals() -> None:
    shared = {
        "Alignment": Alignment,
        "Role": Role,
        "MonsterKind": MonsterKind,
        "Deity": Deity,
        "Region": Region,
        "Party": Party,
        "Actor": Actor,
        "Monster": Monster,
        "Event": Event,
        "Commemoration": Commemoration,
        "World": World,
        "Polity": Polity,
        "PolityLeaderRecord": PolityLeaderRecord,
        "GodState": GodState,
        "deity_value": deity_value,
        "Path": Path,
        "random": random,
        "time": time,
    }
    for name, value in list(globals().items()):
        if name.isupper():
            shared[name] = value
    for module in _RUNTIME_MODULES:
        module.__dict__.update(shared)

_inject_runtime_globals()

def _wrapper_target_from_source(source: str) -> Optional[str]:
    """Return the versioned module named by a lightweight FASE wrapper, if any."""
    import re as _re
    try:
        text = Path(source).read_text(encoding="utf-8")
    except Exception:
        return None
    m = _re.search(r"import_module\(\s*[\"']([^\"']+)[\"']", text)
    if m:
        return m.group(1) + ".py"
    m = _re.search(r"from\s+([A-Za-z_]+_v\d+)\s+import\s+\*", text)
    if m:
        return m.group(1) + ".py"
    m = _re.search(r"run_module\(\s*[\"']([^\"']+)[\"']", text)
    if m:
        return m.group(1) + ".py"
    return None

def _runtime_source_name(module_name: str, fallback: str) -> str:
    module = sys.modules.get(module_name)
    source = getattr(module, "__file__", None) if module is not None else None
    if source:
        try:
            src_path = Path(source)
            if src_path.name.startswith("FASE"):
                target = _wrapper_target_from_source(str(src_path))
                if target:
                    return target
            return src_path.name
        except Exception:
            return str(source)
    return fallback

def _runtime_module_source(module, fallback: str) -> str:
    source = getattr(module, "__file__", None)
    if source:
        try:
            src_path = Path(source)
            if src_path.name.startswith("FASE"):
                target = _wrapper_target_from_source(str(src_path))
                if target:
                    return target
            return src_path.name
        except Exception:
            return str(source)
    return fallback

def _glob_latest(pattern: str) -> str:
    """Return the filename of the highest-versioned match for a glob in DATA_DIR."""
    matches = sorted(DATA_DIR.glob(pattern))
    return matches[-1].name if matches else pattern

def _parse_fase_runmodule(fase_filename: str) -> str:
    """Extract the versioned module name from a FASEux-style runpy.run_module() call."""
    import re as _re
    try:
        src = (BASE_DIR / fase_filename).read_text(encoding="utf-8")
        m = _re.search(r"run_module\(\s*[\"']([^\"\']+)[\"']", src)
        if m:
            return m.group(1) + ".py"
    except OSError:
        pass
    return fase_filename



_BARD_ALLOWED_ALIGNMENTS = [
    Alignment.LAWFUL_GOOD,
    Alignment.NEUTRAL_GOOD,
    Alignment.CHAOTIC_GOOD,
    Alignment.LAWFUL_NEUTRAL,
    Alignment.TRUE_NEUTRAL,
    Alignment.CHAOTIC_NEUTRAL,
]

def _pick_alignment_for_role(self, role: Role) -> Alignment:
    if role == Role.BARD:
        return self.rng.choice(_BARD_ALLOWED_ALIGNMENTS)
    return self.rng.choice(list(Alignment))


class Simulator(CombatMixin, MonsterMixin, PoliticsMixin, PartyMixin, WorldBuildMixin, RelicMixin, LoreMixin, ImmortalAIMixin, LegacyMixin, PopulationMixin):
    Role = Role
    MonsterKind = MonsterKind
    Deity = Deity
    MONTH_NAMES = MONTH_NAMES

    def __init__(
        self,
        seed: Optional[str] = DEFAULT_SEED,
        verbose: bool = False,
        verbose_delay: float = 0.0,
        verbose_min_importance: int = VERBOSE_EVENT_IMPORTANCE,
        population_scale: float = 1.0,
        load_mce: bool = True,
    ) -> None:
        if seed is None:
            seed = self._random_seed_string()
        self.rng = random.Random(seed)
        self.verbose = verbose
        self.verbose_delay = max(0.0, verbose_delay)
        self.verbose_min_importance = max(1, verbose_min_importance)
        self._last_printed_event_index = 0
        self._monster_id_counter = 1
        self._spawned_horror_titles = set()
        base_grace = max(0, int(MONSTER_GRACE_YEARS))
        grace_variance = max(0, int(MONSTER_GRACE_VARIANCE))
        if base_grace > 0 and grace_variance > 0:
            self._monster_grace_years_actual = max(0, self.rng.randint(base_grace - grace_variance, base_grace + grace_variance))
        else:
            self._monster_grace_years_actual = base_grace
        self.population_scale = max(0.0001, float(population_scale))
        self.load_mce = bool(load_mce)
        mce_dirs = [BASE_DIR / "MCE"] if self.load_mce else []
        self.pantheon, self.god_profiles = build_pantheon(Deity, mce_dirs)
        self.world = self._build_world(seed)
        self.world.output_dir = _make_run_output_dir(seed)
        self.world.output_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_summaries_enabled = _env_bool("FANTFARM_SUMMARIES_ENABLED", True)
        self.csv_metrics_enabled = _env_bool("FANTFARM_CSV_ENABLED", True)
        self.historian_enabled = _env_bool("FANTFARM_HISTORIAN_ENABLED", bool(globals().get("HISTORIAN_ENABLED", True)))
        self.historian_event_limit = _env_int("FANTFARM_HISTORIAN_EVENT_LIMIT", int(globals().get("HISTORIAN_SUMMARY_EVENT_LIMIT", 3000) or 3000), minimum=0)
        self.event_memory_limit = _env_int("FANTFARM_EVENT_MEMORY_LIMIT", int(globals().get("EVENT_MEMORY_LIMIT", 1000) or 1000), minimum=0)
        self.world.runtime_options = {
            "summaries_enabled": self.runtime_summaries_enabled,
            "csv_metrics_enabled": self.csv_metrics_enabled,
            "historian_enabled": self.historian_enabled,
            "historian_event_limit": self.historian_event_limit,
            "event_memory_limit": self.event_memory_limit,
        }
        self._ensure_morgue()
        self._ensure_historian()
        self._ensure_lore_state()
        for _actor in self.world.living_actors():
            ensure_actor_religion_tracking(self, _actor)
        self._init_history_tracking()

    def _safe_filename_component(self, value, fallback="seed") -> str:
        text = str(value or fallback)
        text = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
        return text.strip("._") or fallback

    def _run_started_timestamp(self) -> str:
        stamp = getattr(self, "run_started_timestamp", None)
        if stamp:
            return str(stamp)
        try:
            from datetime import datetime
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        except Exception:
            stamp = str(int(time.time()))
        self.run_started_timestamp = stamp
        return stamp

    def _ensure_morgue(self) -> None:
        """Open/create the per-seed morgue database and restore the tiny dead-actor search index."""
        world = getattr(self, "world", None)
        if world is None:
            return
        seed_dir = Path(getattr(world, "output_dir", _make_run_output_dir(getattr(world, "seed_used", "seed"))))
        seed_dir.mkdir(parents=True, exist_ok=True)
        if not hasattr(world, "dead_actor_index") or getattr(world, "dead_actor_index", None) is None:
            world.dead_actor_index = {}
        if not hasattr(world, "dead_actor_count"):
            world.dead_actor_count = len(world.dead_actor_index)
        # Prefer the new morgue_* name. If an older save carries mortuary_path,
        # keep using it so old databases remain readable.
        existing = getattr(self, "morgue_path", None) or getattr(self, "mortuary_path", None)
        if not existing:
            seed_name = self._safe_filename_component(getattr(world, "seed_used", "seed"))
            self.morgue_path = morgue_path(seed_dir, seed_name=seed_name, timestamp=self._run_started_timestamp())
        else:
            self.morgue_path = Path(existing)
        self.morgue = Morgue(self.morgue_path, actor_class=Actor)
        # Backward-compatible aliases for old save/tooling expectations.
        self.mortuary_path = self.morgue_path
        self.mortuary = self.morgue
        self.dead_actor_index = world.dead_actor_index

    def _ensure_historian(self) -> None:
        """Open/create the per-seed SQLite tome and wire it into world.log()."""
        world = getattr(self, "world", None)
        if world is None:
            return
        enabled = bool(getattr(self, "historian_enabled", _env_bool("FANTFARM_HISTORIAN_ENABLED", bool(globals().get("HISTORIAN_ENABLED", True)))))
        world.event_memory_limit = int(getattr(self, "event_memory_limit", _env_int("FANTFARM_EVENT_MEMORY_LIMIT", int(globals().get("EVENT_MEMORY_LIMIT", 1000) or 1000), minimum=0)) or 0)
        if not enabled:
            world.historian = None
            self.historian = None
            return
        seed_dir = Path(getattr(world, "output_dir", _make_run_output_dir(getattr(world, "seed_used", "seed"))))
        seed_dir.mkdir(parents=True, exist_ok=True)
        existing = getattr(self, "historian_path", None) or getattr(world, "historian_path", None)
        if not existing:
            seed_name = self._safe_filename_component(getattr(world, "seed_used", "seed"))
            self.historian_path = tome_path(seed_dir, seed_name=seed_name, timestamp=self._run_started_timestamp())
        else:
            self.historian_path = Path(existing)
        world.historian_path = self.historian_path
        world.historian_min_importance = _env_int("FANTFARM_HISTORIAN_MIN_IMPORTANCE", int(globals().get("HISTORIAN_MIN_IMPORTANCE", 2) or 2), minimum=1)
        world.historian_archive_all = bool(globals().get("HISTORIAN_ARCHIVE_ALL", False))
        world.historian_force_categories = set(globals().get("HISTORIAN_FORCE_CATEGORIES", set()) or set())
        self.historian = Historian(
            self.historian_path,
            flush_event_count=_env_int("FANTFARM_HISTORIAN_FLUSH_EVENT_COUNT", int(globals().get("HISTORIAN_FLUSH_EVENT_COUNT", 5000) or 5000), minimum=1),
        )
        world.historian = self.historian
        # Backfill any recent RAM events that predate historian attachment.
        if getattr(self.historian, "event_count", lambda **_k: 0)(include_pending=True) == 0:
            try:
                self.historian.record_events(list(getattr(world, "events", []) or []))
            except Exception:
                pass

    def _flush_historian(self) -> None:
        historian = getattr(self, "historian", None) or getattr(getattr(self, "world", None), "historian", None)
        if historian is not None:
            try:
                historian.flush()
            except Exception:
                pass

    def _resolve_deity_object(self, deity):
        if deity is None:
            return None
        wanted = deity_value(deity).strip().lower()
        for known in self._pantheon_deities() if hasattr(self, "_pantheon_deities") else list(getattr(self.world, "gods", [])):
            if deity_value(known).strip().lower() == wanted:
                return known
        return deity

    def _normalize_actor_deities(self, actor: Actor) -> Actor:
        for attr in ("deity", "champion_of", "school_deity", "divine_directive_source"):
            if hasattr(actor, attr):
                setattr(actor, attr, self._resolve_deity_object(getattr(actor, attr)))
        ensure_actor_religion_tracking(self, actor)
        return actor

    # Backward-compatible wrappers for old saves / old UX code.
    def _ensure_mortuary(self) -> None:
        return self._ensure_morgue()

    def _archive_actor_to_mortuary(self, actor: Actor) -> None:
        return self._archive_actor_to_morgue(actor)

    def migrate_dead_actors_to_mortuary(self) -> int:
        return self.migrate_dead_actors_to_morgue()

    def resolve_actor(self, actor_id: Optional[int]):
        """Return a live actor from memory or a dead actor loaded from the morgue."""
        if actor_id is None:
            return None
        try:
            actor_id = int(actor_id)
        except Exception:
            return None
        actor = self.world.actors.get(actor_id)
        if actor is not None:
            return actor
        morgue = getattr(self, "morgue", None) or getattr(self, "mortuary", None)
        if morgue is None:
            self._ensure_morgue()
            morgue = getattr(self, "morgue", None) or getattr(self, "mortuary", None)
        if morgue is None:
            return None
        try:
            actor = morgue.load_actor(actor_id, Actor)
            if actor is not None:
                self._normalize_actor_deities(actor)
            return actor
        except Exception:
            return None

    def actor_name(self, actor_id: Optional[int]) -> str:
        actor = self.resolve_actor(actor_id)
        if actor is not None:
            return actor.short_name() if hasattr(actor, "short_name") else str(actor_id)
        tomb = getattr(self.world, "dead_actor_index", {}).get(actor_id) if actor_id is not None else None
        return tomb.get("name", str(actor_id)) if tomb else str(actor_id)

    def _invalidate_actor_caches(self) -> None:
        # Legacy compatibility hook. Runtime caches are now maintained incrementally.
        if hasattr(self.world, "rebuild_runtime_caches"):
            self.world.rebuild_runtime_caches()

    def _remove_actor_from_active_structures(self, actor: Actor) -> None:
        world = self.world
        if actor.party_id is not None:
            party = world.parties.get(actor.party_id)
            if party is not None and actor.id in party.member_ids:
                party.member_ids = [mid for mid in party.member_ids if mid != actor.id]
            actor.party_id = None
        if actor.polity_id is not None:
            polity = world.polities.get(actor.polity_id)
            if polity is not None:
                if getattr(polity, "ruler_id", None) == actor.id:
                    try:
                        members = [world.actors.get(aid) for aid in getattr(polity, "member_actor_ids", [])]
                        members = [m for m in members if m is not None and getattr(m, "alive", False)]
                        avg_favor = sum(getattr(m, "polity_favor", 50) for m in members) / max(1, len(members)) if members else 50
                        approval = 50 + int((avg_favor - 50) * 0.5) + int((getattr(polity, "legitimacy", 50) - 50) * 0.4) + int((getattr(polity, "stability", 50) - 50) * 0.4)
                        approval += min(20, int(getattr(actor, "reputation", 0) // 8))
                        approval -= min(25, int(getattr(actor, "regions_oppressed", 0) * 4))
                        if getattr(actor, "is_evil", lambda: False)() and avg_favor < 55:
                            approval -= 15
                        polity.previous_ruler_id = actor.id
                        polity.previous_ruler_name = actor.short_name() if hasattr(actor, "short_name") else str(actor.id)
                        polity.previous_ruler_approval = max(0, min(100, int(approval)))
                        polity.previous_ruler_fate = getattr(actor, "death_cause", None) or "death"
                    except Exception:
                        polity.previous_ruler_id = actor.id
                        polity.previous_ruler_name = actor.short_name() if hasattr(actor, "short_name") else str(actor.id)
                        polity.previous_ruler_approval = getattr(polity, "previous_ruler_approval", 50)
                        polity.previous_ruler_fate = getattr(actor, "death_cause", None) or "death"
                polity.member_actor_ids = [aid for aid in getattr(polity, "member_actor_ids", []) if aid != actor.id]
                polity.general_ids = [aid for aid in getattr(polity, "general_ids", []) if aid != actor.id]
                polity.captain_ids = [aid for aid in getattr(polity, "captain_ids", []) if aid != actor.id]
                if getattr(polity, "general_id", None) == actor.id:
                    polity.general_id = None
                polity.lieutenant_by_captain = {
                    cid: lid for cid, lid in getattr(polity, "lieutenant_by_captain", {}).items()
                    if cid != actor.id and lid != actor.id
                }
            actor.polity_id = None
        for region in world.regions.values():
            if getattr(region, "ruler_id", None) == actor.id:
                region.ruler_id = None
            if getattr(region, "contested_by", None) == actor.id:
                region.contested_by = None
            if getattr(region, "under_siege_by", None) == actor.id:
                region.under_siege_by = None
        actor.loyalty = None
        actor.commander_id = None
        actor.military_rank = None
        actor.office_title = None

    def _archive_actor_to_morgue(self, actor: Actor) -> None:
        self._ensure_morgue()
        tombstone = self.morgue.store_actor(actor)
        self.world.dead_actor_index[actor.id] = tombstone
        self.world.dead_actor_count = max(int(getattr(self.world, "dead_actor_count", 0) or 0), len(self.world.dead_actor_index))
        self.dead_actor_index = self.world.dead_actor_index
        self._remove_actor_from_active_structures(actor)
        if hasattr(self.world, "unregister_actor"):
            self.world.unregister_actor(actor)
        else:
            self.world.actors.pop(actor.id, None)
            self._invalidate_actor_caches()

    def migrate_dead_actors_to_morgue(self) -> int:
        """One-time migration for older .fics saves that still carry dead actors in RAM."""
        self._ensure_morgue()
        migrated = 0
        for actor in list(self.world.actors.values()):
            if not getattr(actor, "alive", False):
                self._archive_actor_to_morgue(actor)
                migrated += 1
        return migrated

    def _init_history_tracking(self) -> None:
        self.world.history = {
            "tick": [], "year": [], "month": [], "day": [],
            "total_population": [], "commoners": [], "adventurers": [],
            "monsters": [], "parties": [], "polities": [],
        }
        self._record_history_snapshot(force=True)

    def _record_history_snapshot(self, force: bool = False) -> None:
        world = self.world
        if not hasattr(world, "history"):
            world.history = {
                "tick": [], "year": [], "month": [], "day": [],
                "total_population": [], "commoners": [], "adventurers": [],
                "monsters": [], "parties": [], "polities": [],
            }
        if not force and world.tick % TICKS_PER_MONTH != 0:
            return
        year, month, day, _tod, _season = world.current_calendar()
        living_actors = world.living_actors()
        commoners = sum(getattr(world, "commoners_by_region", {}).values())
        adventurers = len([actor for actor in living_actors if actor.is_adventurer() and not getattr(actor, "retired", False) and not getattr(actor, "in_school", False)])
        monsters = len(world.living_monsters())
        world.history["tick"].append(world.tick)
        world.history["year"].append(year)
        world.history["month"].append(month)
        world.history["day"].append(day)
        world.history["total_population"].append(commoners + len(living_actors))
        world.history["commoners"].append(commoners)
        world.history["adventurers"].append(adventurers)
        world.history["monsters"].append(monsters)
        world.history["parties"].append(len(getattr(world, "parties", {})))
        world.history["polities"].append(len(getattr(world, "polities", {})))


    def _soul_cap(self) -> int:
        return int(globals().get("IMMORTAL_SOUL_CAP", -1))

    def _clamp_souls(self, deity) -> int:
        if not hasattr(self.world, "souls_by_deity") or deity is None:
            return 0
        current = max(0, int(self.world.souls_by_deity.get(deity, 0) or 0))
        cap = self._soul_cap()
        if cap >= 0:
            current = min(current, cap)
        self.world.souls_by_deity[deity] = current
        return current

    def _add_souls(self, deity, amount: int) -> int:
        if not hasattr(self.world, "souls_by_deity") or deity is None:
            return 0
        current = max(0, int(self.world.souls_by_deity.get(deity, 0) or 0))
        current += int(amount or 0)
        cap = self._soul_cap()
        if cap >= 0:
            current = min(current, cap)
        self.world.souls_by_deity[deity] = max(0, current)
        return self.world.souls_by_deity[deity]


    def save_state(self, path):
        """Save the complete simulator state to a .fics file."""
        import pickle
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._story_flush_files(force=True)
        self._flush_historian()
        with path.open("wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        return path

    @staticmethod
    def load_state(path):
        """Load a simulator state from a .fics file."""
        import pickle
        path = Path(path)
        with path.open("rb") as f:
            sim = pickle.load(f)
        if hasattr(sim, "_ensure_morgue"):
            sim._ensure_morgue()
        elif hasattr(sim, "_ensure_mortuary"):
            sim._ensure_mortuary()
        if hasattr(sim, "_ensure_historian"):
            sim._ensure_historian()
        if hasattr(sim, "migrate_dead_actors_to_morgue"):
            sim.migrate_dead_actors_to_morgue()
        elif hasattr(sim, "migrate_dead_actors_to_mortuary"):
            sim.migrate_dead_actors_to_mortuary()
        if hasattr(sim, "_ensure_lore_state"):
            sim._ensure_lore_state()
        if hasattr(sim, "_purge_nonformal_school_state"):
            sim._purge_nonformal_school_state()
        if hasattr(sim, "_refresh_god_state_if_due"):
            sim._refresh_god_state_if_due(force=True)
        return sim

    def _assign_pending_custom_relics(self, world=None) -> None:
        world = world if world is not None else getattr(self, "world", None)
        if world is None:
            return
        for actor in world.actors.values():
            cfg = getattr(actor, "pending_custom_relic", None)
            if not cfg:
                continue
            if getattr(actor, "relic_id", None) is not None:
                continue
            name = cfg.get("name") or f"{actor.short_name()}'s Relic"
            relic_type = cfg.get("type", "custom")
            slot = cfg.get("slot", "misc")
            power_bonus = int(cfg.get("power_bonus", 0))
            reputation_bonus = int(cfg.get("reputation_bonus", 0))
            description = cfg.get("description", "")
            tier = cfg.get("tier", "lesser")
            boon_label = cfg.get("boon_label", "")
            boon_stat = cfg.get("boon_stat", "")
            boon_amount = int(cfg.get("boon_amount", 0) or 0)
            template_key = cfg.get("template_key", "")
            template_label = cfg.get("template_label", relic_type)
            creator_deity = self._resolve_deity_name(cfg.get("creator_deity", getattr(actor.deity, "value", str(actor.deity))), fallback_alignment=actor.alignment) if hasattr(self, "_resolve_deity_name") else getattr(actor, "deity", None)
            original_recipient_id = cfg.get("original_recipient_id", actor.id)
            if hasattr(self, "_create_custom_relic_for_actor"):
                old_world = getattr(self, "world", None)
                self.world = world
                try:
                    self._create_custom_relic_for_actor(
                        actor, name, relic_type, slot, power_bonus, reputation_bonus, description,
                        creator_deity=creator_deity, tier=tier, boon_label=boon_label, boon_stat=boon_stat,
                        boon_amount=boon_amount, template_key=template_key, template_label=template_label,
                        original_recipient_id=original_recipient_id, created_by_player=True,
                    )
                finally:
                    if old_world is not None:
                        self.world = old_world
            actor.pending_custom_relic = None

    def _story_seed_paths(self) -> List[Path]:
        picked: Dict[tuple[str, str, str], Path] = {}
        for path in sorted((BASE_DIR / "MCE").glob("*.stri")):
            parsed = _story_parse_sectioned_file(path)
            story = parsed.get("story", {}) if parsed else {}
            faith = parsed.get("faith", {}) if parsed else {}
            active_for_run = _story_truthy(story.get("active_for_run", "false")) or _story_truthy(faith.get("active_champion", "false"))
            if not active_for_run:
                continue
            parts = path.stem.split("+")
            if len(parts) >= 4:
                key = (parts[1].upper(), parts[2].lower(), parts[3].lower())
            else:
                key = (path.stem.lower(), "", "")
            current = picked.get(key)
            if current is None:
                picked[key] = path
                continue
            current_pending = current.stem.split("+", 1)[0].lower().startswith("pending")
            new_pending = path.stem.split("+", 1)[0].lower().startswith("pending")
            if current_pending and not new_pending:
                picked[key] = path
        return sorted(picked.values())

    def _story_region_id_from_pref(self, raw: str, regions: Dict[int, Region]) -> int:
        text = str(raw or "").strip()
        if text:
            try:
                rid = int(text)
                if rid in regions:
                    return rid
            except Exception:
                pass
            lowered = text.lower()
            for rid, region in regions.items():
                if region.name.lower() == lowered:
                    return rid
        return self.rng.choice(list(regions.keys()))

    def _story_default_name_for_path(self, path: Path) -> tuple[str, str]:
        stem = path.stem
        parts = stem.split("+")
        surname = "Story"
        initial = "A"
        if len(parts) >= 3:
            initial = (parts[1] or "A")[:1]
            surname = parts[2] or surname
        first = next((name for name in FEMALE_FIRST_NAMES + MALE_FIRST_NAMES if name[:1].upper() == initial.upper()), "Aster")
        return first, surname

    def _story_actor_from_file(self, path: Path, actor_id: int, regions: Dict[int, Region]) -> Optional[Actor]:
        parsed = _story_parse_sectioned_file(path)
        identity = parsed.get("identity", {})
        build = parsed.get("build", {})
        faith = parsed.get("faith", {})
        spawn = parsed.get("spawn", {})
        story = parsed.get("story", {})
        first = identity.get("name", "").strip()
        surname = identity.get("surname", "").strip()
        if not first or not surname:
            first, surname = self._story_default_name_for_path(path)
        role_name = build.get("role", "Fighter")
        align_name = build.get("alignment", Alignment.TRUE_NEUTRAL.value)
        deity_name = faith.get("deity", build.get("deity", Deity.GOD_OF_CHANCE.value))
        locked_deity = str(faith.get("locked_deity", build.get("locked_deity", "false"))).strip().lower() in {"1", "true", "yes", "y", "on"}
        champion_seed = str(faith.get("active_champion", "false")).strip().lower() in {"1", "true", "yes", "y", "on"}
        try:
            role = next(role for role in Role if role.value.lower() == role_name.lower())
        except StopIteration:
            return None
        if role == Role.COMMONER:
            return None
        try:
            alignment = next(al for al in Alignment if al.value.lower() == align_name.lower())
        except StopIteration:
            alignment = self._pick_alignment_for_role(role)
        deity = self._resolve_deity_name(deity_name, fallback_alignment=alignment)
        region_id = self._story_region_id_from_pref(spawn.get("preferred_region", ""), regions)
        birth_year = _story_safe_int(build.get("birth_year"), 1 - max(16, _story_safe_int(build.get("age"), self._initial_age_for_role(role))))
        birth_month = min(12, max(1, _story_safe_int(build.get("birth_month"), self.rng.randint(1, 12))))
        birth_day = min(30, max(1, _story_safe_int(build.get("birth_day"), self.rng.randint(1, 30))))
        strength = _story_safe_int(build.get("strength"), 10)
        dexterity = _story_safe_int(build.get("dexterity"), 10)
        constitution = _story_safe_int(build.get("constitution"), 10)
        intelligence = _story_safe_int(build.get("intelligence"), 10)
        wisdom = _story_safe_int(build.get("wisdom"), 10)
        charisma = _story_safe_int(build.get("charisma"), 10)
        luck = _story_safe_int(build.get("luck"), 10)
        hp = _story_safe_int(build.get("hp"), self._base_hp(role, constitution))
        actor = Actor(
            id=actor_id,
            name=first,
            surname=surname,
            role=role,
            alignment=alignment,
            deity=deity,
            strength=strength,
            dexterity=dexterity,
            constitution=constitution,
            intelligence=intelligence,
            wisdom=wisdom,
            charisma=charisma,
            luck=luck,
            hp=hp,
            max_hp=_story_safe_int(build.get("max_hp"), hp),
            region_id=region_id,
            traits=_story_parse_traits(build.get("traits", ""))[:2] or self.rng.sample(TRAITS, k=2),
            birth_year=birth_year,
            birth_month=birth_month,
            birth_day=birth_day,
            spouse_id=None,
            sex=(identity.get("sex", "").strip() or "F")[:1].upper(),
            title=(spawn.get("title", "").strip() or None),
            reputation=_story_safe_int(spawn.get("reputation"), 0),
            experience=_story_safe_int(spawn.get("experience"), 0),
        )
        actor.sync_progression(reset_base=True)
        actor.locked_deity = locked_deity
        if champion_seed:
            actor.champion_of = deity
            actor.locked_deity = True
            actor.deity_conviction = 100
            actor.champion_rep_steps = getattr(actor, "champion_rep_steps", 0) + 1
            actor.starting_champion = True
            actor.invulnerable_until_tick = max(0, int(STARTING_CHAMPION_GRACE_YEARS)) * TICKS_PER_YEAR
        actor.is_story_actor = True
        actor.story_file = str(path)
        actor.story_notes = []
        actor.story_dirty = True
        # Register into the cached story actor ID set maintained by _story_sync_all.
        # During initial world construction, self.world does not exist yet because
        # __init__ is still inside: self.world = self._build_world(seed).  In that
        # pre-world phase, stage IDs on the simulator and transfer them onto the
        # World object after it is created.
        world_obj = getattr(self, "world", None)
        story_ids = getattr(world_obj, "_story_actor_ids", None) if world_obj is not None else None
        if not isinstance(story_ids, set):
            story_ids = getattr(self, "_pending_story_actor_ids", None)
            if not isinstance(story_ids, set):
                story_ids = set()
                self._pending_story_actor_ids = story_ids
        story_ids.add(actor.id)
        actor.story_last_region = actor.region_id
        actor.story_region_visits = {actor.region_id: 1}
        actor.story_last_flush_tick = -999999
        actor.story_snapshot = {}
        actor.story_seed_locked = _story_truthy(parsed.get("seed", {}).get("locked", "true"))
        actor.story_status = (story.get("status", "active").strip() or "active")
        relic_cfg = parsed.get("starting_relic", {})
        if relic_cfg:
            actor.pending_custom_relic = {
                "name": relic_cfg.get("name", "").strip(),
                "type": relic_cfg.get("type", "custom").strip(),
                "slot": relic_cfg.get("slot", "misc").strip(),
                "power_bonus": _story_safe_int(relic_cfg.get("power_bonus"), 0),
                "reputation_bonus": _story_safe_int(relic_cfg.get("reputation_bonus"), 0),
                "description": relic_cfg.get("description", "").strip(),
                "tier": relic_cfg.get("tier", "lesser").strip(),
                "template_key": relic_cfg.get("template_key", "").strip(),
                "template_label": relic_cfg.get("template_label", "").strip(),
                "boon_label": relic_cfg.get("boon_label", "").strip(),
                "boon_stat": relic_cfg.get("boon_stat", "").strip(),
                "boon_amount": _story_safe_int(relic_cfg.get("boon_amount"), 0),
                "creator_deity": relic_cfg.get("creator_deity", deity_name).strip(),
                "original_recipient_id": relic_cfg.get("original_recipient_id", "").strip(),
            }
        return actor

    def _story_filename_for_actor(self, actor: Actor) -> str:
        initial = (actor.name[:1].upper() if actor.name else "X")
        role_name = actor.role.value.replace(" ", "")
        return f"{actor.id}+{initial}+{actor.surname}+{role_name}.stri"

    def _story_rebind_file(self, actor: Actor) -> None:
        if not getattr(actor, "story_file", None):
            actor.story_file = str(BASE_DIR / "MCE" / self._story_filename_for_actor(actor))
            return
        src = Path(actor.story_file)
        dst = BASE_DIR / "MCE" / self._story_filename_for_actor(actor)
        if src.resolve() != dst.resolve():
            if src.exists():
                src.rename(dst)
            actor.story_file = str(dst)

    def _story_load_seed_actors(self, actors: Dict[int, Actor], regions: Dict[int, Region]) -> None:
        next_id = max(actors.keys(), default=0) + 1
        for path in self._story_seed_paths():
            actor = self._story_actor_from_file(path, next_id, regions)
            if actor is None:
                continue
            actors[actor.id] = actor
            next_id += 1
            self._story_rebind_file(actor)

    def _story_snapshot_for_actor(self, actor: Actor) -> Dict[str, object]:
        return {
            "region_id": actor.region_id,
            "party_id": actor.party_id,
            "polity_id": actor.polity_id,
            "spouse_id": actor.spouse_id,
            "best_friend_id": getattr(actor, "best_friend_id", None),
            "nemesis_id": getattr(actor, "nemesis_id", None),
            "nemesis_reason": getattr(actor, "nemesis_reason", ""),
            "kill_log_len": len(getattr(actor, "kill_log", [])),
            "title": actor.title,
            "reputation": actor.reputation,
            "experience": getattr(actor, "experience", 0),
            "level": getattr(actor, "level", 1),
            "kills": actor.kills,
            "monster_kills": actor.monster_kills,
            "dragon_kills": actor.dragon_kills,
            "horror_kills": actor.horror_kills,
            "giant_kills": getattr(actor, "giant_kills", 0),
            "retired": getattr(actor, "retired", False),
            "alive": actor.alive,
        }

    def _story_actor_name(self, actor_id: Optional[int]) -> str:
        if actor_id is None:
            return "None"
        actor = self.resolve_actor(actor_id) if getattr(self, 'world', None) is not None and hasattr(self, 'resolve_actor') else None
        return actor.short_name() if actor is not None else str(actor_id)

    def _story_note(self, actor: Actor, text: str) -> None:
        if not getattr(actor, "is_story_actor", False):
            return
        actor.story_notes.append(f"[{self.world.current_timestamp()}] {text}")
        actor.story_dirty = True

    def _story_update_actor(self, actor: Actor) -> None:
        if not getattr(actor, "is_story_actor", False):
            return
        current = self._story_snapshot_for_actor(actor)
        previous = getattr(actor, "story_snapshot", None) or {}
        region_changed = previous.get("region_id") != current["region_id"]
        if region_changed:
            visits = getattr(actor, "story_region_visits", {})
            visits[current["region_id"]] = visits.get(current["region_id"], 0) + 1
            actor.story_region_visits = visits
            actor.story_last_region = current["region_id"]
            actor.story_dirty = True
        if previous:
            if previous.get("party_id") != current["party_id"]:
                if current["party_id"] is None:
                    self._story_note(actor, "Left their party.")
                else:
                    self._story_note(actor, f"Joined party {current['party_id']}.")
            if previous.get("polity_id") != current["polity_id"]:
                if current["polity_id"] is None:
                    self._story_note(actor, "Lost polity allegiance.")
                else:
                    polity = self.world.polities.get(current["polity_id"])
                    self._story_note(actor, f"Came under the banner of {polity.name if polity else 'a new polity'}.")
            if previous.get("spouse_id") != current["spouse_id"] and current["spouse_id"] is not None:
                self._story_note(actor, f"Bound their fate to {self._story_actor_name(current['spouse_id'])}.")
            if previous.get("best_friend_id") != current["best_friend_id"] and current["best_friend_id"] is not None:
                self._story_note(actor, f"Forged a close bond with {self._story_actor_name(current['best_friend_id'])}.")
            if previous.get("nemesis_id") != current["nemesis_id"] and current["nemesis_id"] is not None:
                reason = current.get("nemesis_reason") or "a hostile encounter"
                self._story_note(actor, f"Marked {self._story_actor_name(current['nemesis_id'])} as a nemesis: {reason}.")
            if previous.get("title") != current["title"] and current["title"]:
                self._story_note(actor, f"Earned the title {current['title']}.")
            if not previous.get("retired") and current["retired"]:
                self._story_note(actor, "Retired from active adventuring.")
            if current["level"] > previous.get("level", current["level"]):
                self._story_note(actor, f"Reached level {current['level']}.")
            kill_details = list(getattr(actor, "kill_log", []))[previous.get("kill_log_len", 0):current.get("kill_log_len", 0)]
            kill_suffix = f" ({'; '.join(kill_details[-3:])})" if kill_details else ""
            for key, label in [("kills", "kills"), ("monster_kills", "monster kills"), ("giant_kills", "giant kills"), ("dragon_kills", "dragon kills"), ("horror_kills", "ancient horror kills")]:
                if current[key] > previous.get(key, current[key]):
                    self._story_note(actor, f"Now has {current[key]} {label}{kill_suffix}.")
        else:
            self._story_note(actor, f"Entered the world in {self.world.region_name(actor.region_id)}.")
        actor.story_snapshot = current

    def _story_sync_all(self) -> None:
        # Only a small set of actors are story actors; use an ID set to avoid
        # scanning all living actors every tick.
        story_ids = getattr(self.world, "_story_actor_ids", None)
        if story_ids is None:
            # Build the set on first call; maintained by mark_actor_as_story_character.
            story_ids = {actor.id for actor in self.world.living_actors() if getattr(actor, "is_story_actor", False)}
            self.world._story_actor_ids = story_ids
        for actor_id in list(story_ids):
            actor = self.world.actors.get(actor_id)
            if actor is None or not getattr(actor, "alive", False):
                story_ids.discard(actor_id)
                continue
            self._story_update_actor(actor)

    def _story_write_actor_file(self, actor: Actor) -> None:
        if not getattr(actor, "is_story_actor", False) or not getattr(actor, "story_file", None):
            return
        path = Path(actor.story_file)
        visits = getattr(actor, "story_region_visits", {})
        lines = []
        lines.append("[seed]")
        lines.append("version=1")
        lines.append("source=fantag")
        lines.append(f"locked={'true' if getattr(actor, 'story_seed_locked', True) else 'false'}")
        lines.append("")
        lines.append("[identity]")
        lines.append(f"id={actor.id}")
        lines.append(f"name={actor.name}")
        lines.append(f"surname={actor.surname}")
        lines.append(f"sex={actor.sex}")
        lines.append("")
        lines.append("[build]")
        lines.append(f"role={actor.role.value}")
        lines.append(f"alignment={actor.alignment.value}")
        lines.append(f"deity={deity_value(getattr(actor, 'deity', None))}")
        for field in ["strength","dexterity","constitution","intelligence","wisdom","charisma","luck"]:
            lines.append(f"{field}={getattr(actor, field)}")
        lines.append(f"hp={actor.hp}")
        lines.append(f"max_hp={actor.max_hp}")
        lines.append(f"birth_year={actor.birth_year}")
        lines.append(f"birth_month={actor.birth_month}")
        lines.append(f"birth_day={actor.birth_day}")
        lines.append(f"traits={','.join(actor.traits)}")
        lines.append("")
        lines.append("[spawn]")
        lines.append(f"preferred_region={actor.region_id}")
        lines.append(f"title={actor.title or ''}")
        lines.append(f"reputation={actor.reputation}")
        lines.append(f"experience={getattr(actor, 'experience', 0)}")
        lines.append("")
        lines.append("[story]")
        status = "dead" if not actor.alive else "retired" if getattr(actor, 'retired', False) else "active"
        lines.append(f"status={status}")
        lines.append(f"current_region={self.world.region_name(actor.region_id)}")
        lines.append(f"party_id={'' if actor.party_id is None else actor.party_id}")
        lines.append(f"polity_id={'' if actor.polity_id is None else actor.polity_id}")
        lines.append(f"alive={'true' if actor.alive else 'false'}")
        lines.append(f"notes=")
        lines.append("")
        lines.append("[visits]")
        for region_id, count in sorted(visits.items(), key=lambda item: self.world.region_name(item[0])):
            lines.append(f"{self.world.region_name(region_id)}={count}")
        lines.append("")
        lines.append("[journal]")
        for note in getattr(actor, "story_notes", []):
            lines.append(note)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        actor.story_dirty = False
        actor.story_last_flush_tick = self.world.tick

    def _story_flush_files(self, force: bool = False) -> None:
        story_ids = getattr(self.world, "_story_actor_ids", None)
        if story_ids is not None:
            for actor_id in list(story_ids):
                actor = self.world.actors.get(actor_id)
                if actor is None or not getattr(actor, "alive", False):
                    story_ids.discard(actor_id)
                    continue
                if force or getattr(actor, "story_dirty", False):
                    self._story_write_actor_file(actor)
        else:
            for actor in self.world.living_actors():
                if not getattr(actor, "is_story_actor", False):
                    continue
                if force or getattr(actor, "story_dirty", False):
                    self._story_write_actor_file(actor)

    def mark_actor_as_story_character(self, actor_id: int) -> tuple[bool, str]:
        actor = self.world.actors.get(actor_id)
        if actor is None:
            return False, "Actor not found."
        if not getattr(actor, "is_adventurer", lambda: False)():
            return False, f"{actor.short_name()} is not an adventurer."
        if not getattr(actor, "alive", False):
            return False, f"{actor.short_name()} is dead."
        if getattr(actor, "is_story_actor", False):
            self._story_rebind_file(actor)
            actor.story_dirty = True
            self._story_write_actor_file(actor)
            return True, f"{actor.short_name()} is already a story character."

        actor.is_story_actor = True
        actor.story_file = str(BASE_DIR / "MCE" / self._story_filename_for_actor(actor))
        actor.story_notes = list(getattr(actor, "story_notes", []) or [])
        actor.story_dirty = True
        actor.story_last_region = actor.region_id
        visits = getattr(actor, "story_region_visits", None)
        actor.story_region_visits = visits if isinstance(visits, dict) and visits else {actor.region_id: 1}
        actor.story_last_flush_tick = -999999
        actor.story_snapshot = {}
        actor.story_seed_locked = False
        actor.story_status = "active"
        self._story_rebind_file(actor)
        self._story_note(actor, "Marked as a story character by the user-god.")
        self._story_update_actor(actor)
        self._story_write_actor_file(actor)
        return True, f"Marked {actor.short_name()} as a story character."

    def _mark_actor_dead(self, actor: Actor, cause: str, importance: int = 1) -> None:
        if not actor.alive:
            return
        grace_until = int(getattr(actor, "invulnerable_until_tick", -1))
        if grace_until > self.world.tick:
            actor.hp = max(1, actor.hp)
            actor.recovering = max(getattr(actor, "recovering", 0), 12)
            actor.combat_cooldown = max(getattr(actor, "combat_cooldown", 0), 12)
            if not getattr(actor, "invulnerability_logged", False):
                actor.invulnerability_logged = True
                self.world.log(
                    f"{actor.full_name()} survives by divine grace during the opening champion protection period.",
                    importance=2,
                    category="champion_grace",
                )
            return
        actor.alive = False
        actor.hp = 0
        actor.recovering = 0
        actor.death_timestamp = self.world.current_timestamp()
        actor.death_cause = cause
        self._add_souls(actor.deity, 1)
        commemorated = any(item.actor_id == actor.id for item in self.world.commemorations)
        notable = bool(actor.title or actor.monster_kills or actor.kills or actor.reputation >= 10 or commemorated)
        self._drop_relic(actor)
        actor.loyalty = None
        killer = self.world.actors.get(actor.death_killer_id) if actor.death_killer_id is not None else None
        self._propagate_revenge_from_death(actor, killer)
        monster_killer = self.world.monsters.get(getattr(actor, "death_monster_id", None)) if getattr(actor, "death_monster_id", None) is not None else None
        self._propagate_monster_revenge_from_death(actor, monster_killer)
        self._resolve_revenge_if_needed(actor)
        if getattr(actor, "is_story_actor", False):
            self._story_note(actor, f"Died in {self.world.region_name(actor.region_id)}. Cause: {cause}.")
        if notable:
            self.world.log(
                f"{actor.full_name()} dies in {self.world.region_name(actor.region_id)}. Cause: {cause}.",
                importance=max(2, importance),
                category="notable_death",
            )
        if getattr(actor, "champion_of", None) is not None:
            self.world.log(
                f"{actor.full_name()}, champion of {deity_value(getattr(actor, 'champion_of', None))}, falls in {self.world.region_name(actor.region_id)}. Cause: {cause}.",
                importance=3,
                category="champion_death",
            )
        if getattr(actor, "is_story_actor", False):
            try:
                self._story_write_actor_file(actor)
            except Exception:
                pass
        self._archive_actor_to_morgue(actor)

    def _living_adventurer_count(self) -> int:
        return len([
            actor for actor in self.world.living_actors()
            if actor.is_adventurer() and not getattr(actor, "retired", False) and not getattr(actor, "in_school", False)
        ])

    def _school_child_count(self) -> int:
        return len([
            actor for actor in self.world.living_actors()
            if getattr(actor, "in_school", False)
        ])

    def _recovery_state(self) -> str:
        living = self._living_adventurer_count()
        if living < RECOVERY_ADVENTURER_CRISIS_THRESHOLD:
            return 'crisis'
        if living < RECOVERY_ADVENTURER_LOW_THRESHOLD:
            return 'low'
        return 'normal'


    def _dynamic_polity_thresholds(self) -> Tuple[int, int]:
        world = self.world
        state = self._recovery_state()
        if not world.polities:
            return (RECOVERY_POLITYLESS_REPUTATION, RECOVERY_POLITYLESS_PARTY_SIZE)
        if state == 'crisis':
            return (RECOVERY_CRISIS_REPUTATION, RECOVERY_CRISIS_PARTY_SIZE)
        return (POLITY_MIN_REPUTATION, POLITY_MIN_PARTY_SIZE)

    def _apply_recovery_pressure(self) -> None:
        world = self.world
        # Called from explicit day/time scheduler; no raw tick modulo gate here.
        state = self._recovery_state()
        if state == 'normal':
            return
        for region in world.regions.values():
            local_monsters = world.monsters_in_region(region.id)
            dangerous = any(m.alive and m.kind in (MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR, MonsterKind.GIANT, MonsterKind.GOBLIN) for m in local_monsters)
            commoners = world.commoners_by_region.get(region.id, 0) if hasattr(world, 'commoners_by_region') else 0
            if dangerous:
                continue
            if commoners >= 100:
                world.adjust_region_state(region.id, control_delta=RECOVERY_REGION_CONTROL_STEP, order_delta=RECOVERY_REGION_ORDER_STEP)
            elif commoners >= 50:
                world.adjust_region_state(region.id, control_delta=1, order_delta=1)
        if not world.polities:
            world.log("With the great powers broken, surviving communities slowly begin to restore order.", importance=2, category="recovery")
        else:
            world.log("Exhausted realms pull back from the brink and begin to gather strength again.", importance=2, category="recovery")


    def _aggregate_commoner_total(self) -> int:
        world = self.world
        return sum(world.commoners_by_region.values()) if hasattr(world, 'commoners_by_region') else 0

    def _safe_refugee_regions(self) -> List[Region]:
        world = self.world
        candidates: List[Region] = []
        for region in world.regions.values():
            local_monsters = world.monsters_in_region(region.id)
            dangerous = any(
                m.alive and m.kind in (MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR, MonsterKind.GIANT)
                for m in local_monsters
            )
            if dangerous:
                continue
            if region.order < 45:
                continue
            candidates.append(region)
        candidates.sort(key=lambda r: (r.order, r.control, -r.danger, self.rng.random()), reverse=True)
        return candidates

    def _maybe_arrive_refugees(self) -> None:
        world = self.world
        if world.tick % TICKS_PER_TENDAY != 0 or not hasattr(world, 'commoners_by_region'):
            return
        total_commoners = self._aggregate_commoner_total()
        avg_order = sum(region.order for region in world.regions.values()) / max(1, len(world.regions))
        if total_commoners >= REFUGEE_COMMONER_THRESHOLD:
            return
        if avg_order >= REFUGEE_ORDER_THRESHOLD:
            return

        chance = REFUGEE_BASE_CHANCE
        state = self._recovery_state()
        if state == 'crisis':
            chance += REFUGEE_CRISIS_BONUS
        elif state == 'low':
            chance += REFUGEE_LOW_BONUS

        chance += min(0.18, max(0, REFUGEE_COMMONER_THRESHOLD - total_commoners) / max(1, REFUGEE_COMMONER_THRESHOLD) * 0.18)
        chance += min(0.12, max(0.0, REFUGEE_ORDER_THRESHOLD - avg_order) / max(1.0, REFUGEE_ORDER_THRESHOLD) * 0.12)

        safe_regions = self._safe_refugee_regions()
        if not safe_regions:
            return
        if self.rng.random() >= min(0.75, chance):
            return

        num_regions = min(len(safe_regions), self.rng.randint(REFUGEE_REGION_MIN, REFUGEE_REGION_MAX))
        arrivals = self.rng.sample(safe_regions, k=num_regions)
        total_arrivals = 0
        for region in arrivals:
            batch = self.rng.randint(REFUGEE_BATCH_MIN, REFUGEE_BATCH_MAX)
            if region.order >= 70:
                batch += self.rng.randint(10, 40)
            world.commoners_by_region[region.id] += batch
            faith_map = world.commoner_faith_by_region.setdefault(region.id, self._empty_faith_map(world))
            favored = self._region_favored_deity(region.id)
            self._bulk_apply_faith_addition(faith_map, batch, favored=favored)
            total_arrivals += batch
            world.adjust_region_state(region.id, control_delta=1, order_delta=-1)

        world.refugee_arrivals = getattr(world, 'refugee_arrivals', 0) + 1
        world.refugee_commoners = getattr(world, 'refugee_commoners', 0) + total_arrivals

        if len(arrivals) == 1:
            world.log(
                f"Refugees from beyond the continent reach {arrivals[0].name}, bringing {total_arrivals} desperate souls to its gates.",
                importance=3,
                category="refugees",
            )
        else:
            names = ", ".join(region.name for region in arrivals[:-1]) + f", and {arrivals[-1].name}" if len(arrivals) > 1 else arrivals[0].name
            world.log(
                f"Refugee caravans from beyond the continent reach {names}, bringing {total_arrivals} desperate souls in search of shelter.",
                importance=3,
                category="refugees",
            )

    def _destabilize_polity_regions(self, polity: Polity, control_loss: int, order_loss: int, max_regions: Optional[int] = None) -> None:
        world = self.world
        region_ids = list(polity.region_ids)
        if max_regions is not None and len(region_ids) > max_regions:
            self.rng.shuffle(region_ids)
            region_ids = region_ids[:max_regions]
        for region_id in region_ids:
            world.adjust_region_state(region_id, control_delta=-abs(control_loss), order_delta=-abs(order_loss))

    def _maybe_fragment_polity(self, polity: Polity) -> bool:
        world = self.world
        if polity.stability > 0 or len(polity.region_ids) < 2:
            return False
        fringe = [rid for rid in polity.region_ids if rid != polity.capital_region_id]
        if not fringe:
            return False
        split_count = max(1, len(fringe) // 3)
        self.rng.shuffle(fringe)
        breakaway = fringe[:split_count]
        for region_id in breakaway:
            polity.region_ids = [rid for rid in polity.region_ids if rid != region_id]
            world.regions[region_id].polity_id = None
            world.regions[region_id].contested_by = None
            world.adjust_region_state(region_id, control_delta=-10, order_delta=-10)
        world.log(f"{polity.name} splinters under the strain, losing hold of {len(breakaway)} region{'s' if len(breakaway) != 1 else ''}.", importance=3, category='polity_challenge')
        return True

    def run(self, ticks: int, periodic_summary_years: int = 0, autosave_years: int = 0) -> None:
        periodic_summary_years = max(0, int(periodic_summary_years))
        autosave_years = max(0, int(autosave_years or 0))
        summary_every_ticks = periodic_summary_years * TICKS_PER_YEAR if periodic_summary_years > 0 else 0
        run_start = time.perf_counter()
        last_autosave_year = int(getattr(self.world, "_last_headless_autosave_year", 0) or 0)

        for _ in range(ticks):
            self.step()

            if bool(getattr(self, "runtime_summaries_enabled", True)) and summary_every_ticks > 0 and self.world.tick % summary_every_ticks == 0:
                elapsed_years = self.world.tick // TICKS_PER_YEAR
                self.world.runtime_seconds = time.perf_counter() - run_start
                self._flush_historian()
                summary.write_summary(self, elapsed_years)

            if autosave_years > 0 and self.world.tick % TICKS_PER_YEAR == 0:
                last_autosave_year = _maybe_headless_autosave(self, autosave_years, last_autosave_year)
                self.world._last_headless_autosave_year = last_autosave_year

            if self.verbose:
                self._print_new_events()
                if self.verbose_delay > 0:
                    time.sleep(self.verbose_delay)


    def _school_display_name(self, deity) -> str:
        return f"{self._deity_display_name(deity)} Adventurer School" if hasattr(self, "_deity_display_name") else f"{getattr(deity, 'value', str(deity))} Adventurer School"

    def _school_initial_region(self, deity):
        """Pick an initial school region. Prefer safer, more ordered regions but keep it random."""
        region_ids = list(self.world.regions.keys())
        if not region_ids:
            return None
        weights = []
        for rid in region_ids:
            region = self.world.regions[rid]
            faith_map = getattr(self.world, "commoner_faith_by_region", {}).get(rid, {})
            faith = int(faith_map.get(deity, 0)) if faith_map else 0
            weight = 10 + max(0, int(region.order)) + max(0, int(region.control)) + min(100, faith // 25)
            weight -= max(0, int(getattr(region, "danger", 0))) * 3
            weights.append(max(1, weight))
        return self.rng.choices(region_ids, weights=weights, k=1)[0]

    def _is_formal_deity(self, deity) -> bool:
        """Full immortal-pantheon membership, independent of school eligibility."""
        if deity is None:
            return False
        dead = set(getattr(self.world, "dead_gods", set()) or set())
        if deity in dead:
            return False
        profile = getattr(self.world, "god_profiles", {}).get(deity) or getattr(self, "god_profiles", {}).get(deity)
        if str(getattr(profile, "source_path", "") or "") == "emergent_lore":
            return False
        if str(getattr(profile, "profile_id", "") or "").startswith("ascended_"):
            return False
        pantheon = list(getattr(self, "pantheon", []) or [])
        return deity in pantheon if pantheon else deity in list(Deity)

    def _is_formal_school_deity(self, deity) -> bool:
        """Only full, school-unlocked gods may own public adventurer schools."""
        if not self._is_formal_deity(deity):
            return False
        locked = set(getattr(self.world, "school_locked_deities", set()) or set())
        unlocked = set(getattr(self.world, "school_unlocked_deities", set()) or set())
        if deity in locked and deity not in unlocked:
            return False
        return True

    def _formal_deities(self) -> List[object]:
        gods = list(getattr(self.world, "gods", []) or getattr(self, "pantheon", list(Deity)))
        return [god for god in gods if self._is_formal_deity(god)]

    def _formal_school_deities(self) -> List[object]:
        return [god for god in self._formal_deities() if self._is_formal_school_deity(god)]

    def _fallback_formal_deity_for_actor(self, actor):
        current = getattr(actor, "deity", None)
        if self._is_formal_school_deity(current):
            return current
        try:
            return self._weighted_random_deity(getattr(actor, "alignment", None), region_id=getattr(actor, "region_id", None))
        except Exception:
            return Deity.GOD_OF_CHANCE

    def _purge_nonformal_school_state(self) -> None:
        """Remove leaked schools/enrollments from proto-cult/ascended-memory objects."""
        world = self.world
        schools = getattr(world, "adventurer_schools", None)
        if not isinstance(schools, dict):
            return
        bad_deities = [deity for deity in list(schools.keys()) if not self._is_formal_school_deity(deity)]
        if bad_deities:
            for deity in bad_deities:
                schools.pop(deity, None)
            if hasattr(world, "log"):
                names = ", ".join(self._deity_display_name(d) if hasattr(self, "_deity_display_name") else str(getattr(d, "value", d)) for d in bad_deities[:4])
                world.log(f"Hidden cult infrastructure is corrected: non-pantheon schools are dissolved ({names}).", importance=2, category="adventurer_school")
        bad_set = set(bad_deities)
        for actor in world.living_actors():
            school_deity = getattr(actor, "school_deity", None)
            if school_deity is None:
                continue
            deity = getattr(actor, "deity", None)
            if not self._is_formal_school_deity(school_deity):
                replacement = self._fallback_formal_deity_for_actor(actor)
                actor.school_deity = replacement
                actor.school_region_id = None
                actor.school_capacity_bypass = False
                if not self._is_formal_deity(deity):
                    change_actor_deity(self, actor, replacement, locked=False)
                if getattr(actor, "in_school", False):
                    if hasattr(world, "set_actor_school_status"):
                        world.set_actor_school_status(actor, False)
                    else:
                        actor.in_school = False
                    self._try_enroll_school_child(actor, replacement, reason="cult_school_cleanup")
            elif deity is not None and not self._is_formal_deity(deity) and getattr(actor, "champion_of", None) is None:
                change_actor_deity(self, actor, self._fallback_formal_deity_for_actor(actor), locked=False)
        # Commoner faith maps must not contain underground cult objects. Their
        # latent cult affinity belongs in proto_cults, not public faith counts.
        formal = set(self._formal_deities())
        for rid, faith in getattr(world, "commoner_faith_by_region", {}).items():
            if not isinstance(faith, dict):
                continue
            leaked = [(d, int(v)) for d, v in list(faith.items()) if d not in formal and int(v) > 0]
            if not leaked:
                for d in list(faith.keys()):
                    if d not in formal:
                        faith.pop(d, None)
                continue
            receiver = max(formal, key=lambda d: int(faith.get(d, 0))) if formal else Deity.GOD_OF_CHANCE
            faith.setdefault(receiver, 0)
            for d, count in leaked:
                faith[receiver] = int(faith.get(receiver, 0)) + count
                faith.pop(d, None)
            for d in list(faith.keys()):
                if d not in formal:
                    faith.pop(d, None)
        # Keep public god lists/soul/state tables formal. Proto-cults remain in world.proto_cults.
        if hasattr(world, "gods"):
            world.gods = [g for g in list(world.gods) if self._is_formal_deity(g)]
        for table_name in ("souls_by_deity", "god_state"):
            table = getattr(world, table_name, None)
            if isinstance(table, dict):
                for d in list(table.keys()):
                    if not self._is_formal_deity(d):
                        table.pop(d, None)

    def _ensure_adventurer_schools(self) -> None:
        """Ensure every active god has a persistent school location."""
        world = self.world
        if not hasattr(world, "adventurer_schools") or world.adventurer_schools is None:
            world.adventurer_schools = {}
        self._purge_nonformal_school_state()
        for deity in self._formal_school_deities():
            if deity in getattr(world, "adventurer_schools", {}):
                continue
            rid = self._school_initial_region(deity)
            if rid is None:
                continue
            world.adventurer_schools[deity] = AdventurerSchool(
                deity=deity,
                region_id=rid,
                founded_tick=getattr(world, "tick", 0),
                last_moved_tick=getattr(world, "tick", 0),
                name=self._school_display_name(deity),
            )
            if hasattr(world, "log"):
                world.log(
                    f"The {self._school_display_name(deity)} is founded in {world.region_name(rid)}.",
                    importance=2,
                    category="adventurer_school",
                )

    def _school_for_deity(self, deity):
        if deity is None or not self._is_formal_school_deity(deity):
            return None
        self._ensure_adventurer_schools()
        return getattr(self.world, "adventurer_schools", {}).get(deity)

    def _school_age_years(self, school) -> float:
        if school is None:
            return 0.0
        return max(0, getattr(self.world, "tick", 0) - int(getattr(school, "founded_tick", 0))) / float(TICKS_PER_YEAR)

    def _school_prestige_bonus(self, deity) -> int:
        school = self._school_for_deity(deity)
        if school is None:
            return 0
        cap = int(globals().get("SCHOOL_PRESTIGE_CAP_YEARS", 50))
        return max(0, min(cap, int(self._school_age_years(school))))

    def _school_move_cooldown_ticks_remaining(self, deity) -> int:
        school = self._school_for_deity(deity)
        if school is None:
            return 0
        cooldown = int(globals().get("SCHOOL_MOVE_COOLDOWN_YEARS", 10)) * TICKS_PER_YEAR
        ready_at = int(getattr(school, "last_moved_tick", -999999)) + cooldown
        return max(0, ready_at - int(getattr(self.world, "tick", 0)))

    def _school_teacher_ids(self, deity):
        teacher_ids = []
        if deity is None:
            return teacher_ids
        scored = []
        for teacher in self.world.living_actors():
            # Retired, matching-deity actors only — matches _school_teacher_score fast-exit.
            if not getattr(teacher, "retired", False) or getattr(teacher, "deity", None) != deity:
                continue
            try:
                score = self._school_teacher_score(teacher, deity) if hasattr(self, "_school_teacher_score") else 0
            except Exception:
                score = 0
            if score > 0:
                scored.append((score, teacher))
        # Sort using pre-computed scores; avoid re-calling _school_teacher_score for sort.
        scored.sort(key=lambda item: (-item[0], -getattr(item[1], "level", 1), -getattr(item[1], "reputation", 0), item[1].short_name() if hasattr(item[1], "short_name") else ""))
        return [t.id for _s, t in scored]

    def _school_status(self, deity=None):
        if deity is None:
            deity = self._player_god() if hasattr(self, "_player_god") else None
        if deity is None:
            return None
        school = self._school_for_deity(deity)
        if school is None:
            return None
        region = self.world.regions.get(getattr(school, "region_id", None))
        teachers = self._school_teacher_ids(deity)
        children = [
            a for a in self.world.living_actors()
            if getattr(a, "in_school", False)
            and (getattr(a, "school_deity", None) or getattr(a, "deity", None)) == deity
        ]
        return {
            "deity": deity,
            "school": school,
            "region": region,
            "teachers": teachers,
            "children": children,
            "teacher_bonus": self._school_teacher_bonus(deity) if hasattr(self, "_school_teacher_bonus") else 0,
            "prestige_bonus": self._school_prestige_bonus(deity),
            "capacity": self._school_capacity(deity),
            "capacity_bonus": self._school_capacity_bonus(deity),
            "influence_rank": self._school_influence_rank(deity),
            "combat_training": self._update_school_class_ranks(deity),
            "age_years": self._school_age_years(school),
            "move_cooldown_ticks": self._school_move_cooldown_ticks_remaining(deity),
        }

    def _move_player_school(self, region_id: int):
        god = self._player_god() if hasattr(self, "_player_god") else None
        if god is None:
            return False, "No player god loaded."
        if region_id not in self.world.regions:
            return False, "No such region."
        self._ensure_adventurer_schools()
        school = self._school_for_deity(god)
        if school is None:
            return False, "No school found."
        remaining = self._school_move_cooldown_ticks_remaining(god)
        if remaining > 0:
            years = remaining / float(TICKS_PER_YEAR)
            return False, f"School move not ready for {years:.1f} more years."
        old_region = self.world.regions.get(getattr(school, "region_id", None))
        old_name = getattr(old_region, "name", "Unknown")
        school.region_id = int(region_id)
        school.last_moved_tick = int(getattr(self.world, "tick", 0))
        for child in self.world.living_actors():
            if getattr(child, "in_school", False) and ((getattr(child, "school_deity", None) or getattr(child, "deity", None)) == god):
                child.school_region_id = int(region_id)
                self.world.move_actor(child, int(region_id)) if hasattr(self.world, "move_actor") else setattr(child, "region_id", int(region_id))
        new_name = self.world.region_name(region_id)
        self.world.log(
            f"{self._deity_display_name(god)} moves the {getattr(school, 'name', self._school_display_name(god))} from {old_name} to {new_name}.",
            importance=3,
            category="adventurer_school",
        )
        return True, f"School moved to {new_name}."

    def _prepare_turn_caches(self) -> None:
        world = self.world

        # Cache the relative reputation threshold once per tick instead of
        # re-sorting living adventurers for every founder check.
        living_reps = [a.reputation for a in world._living_actor_cache if a.is_adventurer()]
        if living_reps:
            living_reps.sort()
            index = min(len(living_reps) - 1, max(0, int((len(living_reps) - 1) * PARTY_FOUNDING_PERCENTILE)))
            world._party_founder_rep_threshold_cache = living_reps[index]
        else:
            world._party_founder_rep_threshold_cache = 0

        # Cache parties by leader region for local join checks.
        parties_by_region = {rid: [] for rid in world.regions}
        for party in world.parties.values():
            if not party.member_ids or party.leader_id is None:
                continue
            leader = world.actors.get(party.leader_id)
            if leader is None or not leader.alive:
                continue
            parties_by_region.setdefault(leader.region_id, []).append(party)
        world._parties_by_region_cache = parties_by_region

    def _actor_is_adventurer_child(self, actor: Actor) -> bool:
        if actor is None or not getattr(actor, "alive", False):
            return False
        if getattr(actor, "role", None) != Role.COMMONER:
            return False
        try:
            if self._calculate_age(actor) >= 16:
                return False
        except Exception:
            return False
        mother = self.world.actors.get(getattr(actor, "mother_id", None))
        father = self.world.actors.get(getattr(actor, "father_id", None))
        return bool(
            (mother is not None and mother.is_adventurer())
            or (father is not None and father.is_adventurer())
        )

    def _actor_is_champion_child(self, actor: Actor) -> bool:
        mother = self.world.actors.get(getattr(actor, "mother_id", None))
        father = self.world.actors.get(getattr(actor, "father_id", None))
        return bool(
            (mother is not None and getattr(mother, "champion_of", None) is not None)
            or (father is not None and getattr(father, "champion_of", None) is not None)
        )

    def _school_active_gods(self) -> List[object]:
        return self._formal_school_deities()

    def _school_influence_rank(self, deity) -> Optional[int]:
        if deity is None:
            return None
        states = getattr(self.world, "god_state", None)
        if not states:
            try:
                states = self._refresh_god_state_if_due()
            except Exception:
                states = {}
        ranked = []
        for god in self._school_active_gods():
            state = states.get(god) if isinstance(states, dict) else None
            influence = float(getattr(state, "influence", 0.0) or 0.0)
            share = float(getattr(state, "influence_share", 0.0) or 0.0)
            ranked.append((influence, share, getattr(god, "value", str(god)), god))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        for index, _item in enumerate(ranked, start=1):
            if _item[3] == deity:
                return index
        return None

    def _school_capacity_bonus(self, deity) -> int:
        god_count = max(0, len(self._school_active_gods()))
        rank = self._school_influence_rank(deity)
        if rank == 1:
            mult = float(globals().get("SCHOOL_CAPACITY_TOP_RANK_MULTIPLIER", 3.0))
        elif rank == 2:
            mult = float(globals().get("SCHOOL_CAPACITY_SECOND_RANK_MULTIPLIER", 2.0))
        elif rank == 3:
            mult = float(globals().get("SCHOOL_CAPACITY_THIRD_RANK_MULTIPLIER", 1.5))
        else:
            mult = 0.0
        return int(god_count * mult)

    def _school_capacity(self, deity) -> int:
        return max(0, int(globals().get("SCHOOL_BASE_CAPACITY", 50)) + self._school_capacity_bonus(deity))

    def _school_enrolled_children(self, deity) -> List[Actor]:
        return [
            a for a in self.world.living_actors()
            if getattr(a, "in_school", False)
            and (getattr(a, "school_deity", None) or getattr(a, "deity", None)) == deity
        ]

    def _school_can_accept(self, deity, actor: Optional[Actor] = None) -> bool:
        if deity is None:
            return False
        if actor is not None and self._actor_is_champion_child(actor):
            return True
        return len(self._school_enrolled_children(deity)) < self._school_capacity(deity)

    def _school_student_merit(self, actor: Actor) -> int:
        deity = getattr(actor, "school_deity", None) or getattr(actor, "deity", None)
        teacher_bonus = self._school_teacher_bonus(deity) if hasattr(self, "_school_teacher_bonus") else 0
        prestige_bonus = self._school_prestige_bonus(deity) if hasattr(self, "_school_prestige_bonus") else 0
        traits = set(getattr(actor, "traits", []) or [])
        trait_bonus = 0
        trait_bonus += 5 if traits.intersection({"disciplined", "brave", "honorable", "patient"}) else 0
        trait_bonus -= 4 if traits.intersection({"cowardly", "impulsive"}) else 0
        merit = (
            int(getattr(actor, "strength", 0)) * 2
            + int(getattr(actor, "dexterity", 0)) * 2
            + int(getattr(actor, "constitution", 0)) * 2
            + int(getattr(actor, "wisdom", 0))
            + int(getattr(actor, "intelligence", 0)) // 2
            + int(getattr(actor, "luck", 0))
            + teacher_bonus * 3
            + prestige_bonus
            + trait_bonus
        )
        return max(0, merit)

    def _school_combat_training_students(self, deity) -> List[Actor]:
        min_age = int(globals().get("SCHOOL_COMBAT_TRAINING_MIN_AGE", 10))
        max_age = int(globals().get("SCHOOL_COMBAT_TRAINING_MAX_AGE", 16))
        students = []
        for actor in self._school_enrolled_children(deity):
            try:
                age = self._calculate_age(actor)
            except Exception:
                continue
            if min_age <= age <= max_age:
                students.append(actor)
        return students

    def _update_school_class_ranks(self, deity) -> List[Actor]:
        students = self._school_combat_training_students(deity)
        students.sort(key=lambda a: (-self._school_student_merit(a), int(getattr(a, "school_started_tick", 0)), a.id))
        for rank, student in enumerate(students, start=1):
            student.school_merit = self._school_student_merit(student)
            student.school_class_rank = rank
        return students

    def _try_enroll_school_child(self, actor: Actor, deity=None, *, reason: str = "") -> bool:
        if actor is None or not getattr(actor, "alive", False):
            return False
        deity = deity or getattr(actor, "deity", None)
        if not self._is_formal_school_deity(deity):
            deity = self._fallback_formal_deity_for_actor(actor)
            change_actor_deity(self, actor, deity, locked=False)
        school = self._school_for_deity(deity)
        if school is None:
            return False
        bypass = self._actor_is_champion_child(actor)
        if not bypass and not self._school_can_accept(deity, actor):
            return False
        actor.school_deity = deity
        actor.school_region_id = getattr(school, "region_id", None)
        actor.school_capacity_bypass = bool(bypass)
        if getattr(school, "region_id", None) is not None:
            self.world.move_actor(actor, school.region_id) if hasattr(self.world, "move_actor") else setattr(actor, "region_id", school.region_id)
        if hasattr(self.world, "set_actor_school_status"):
            self.world.set_actor_school_status(actor, True)
        else:
            actor.in_school = True
        if int(getattr(actor, "school_started_tick", -1)) < 0:
            actor.school_started_tick = getattr(self.world, "tick", 0)
        actor.school_teacher_bonus = self._school_teacher_bonus(deity) if hasattr(self, "_school_teacher_bonus") else 0
        actor.school_merit = self._school_student_merit(actor)
        self._update_school_class_ranks(deity)
        if hasattr(self.world, "log"):
            note = " despite full enrollment" if bypass and len(self._school_enrolled_children(deity)) > self._school_capacity(deity) else ""
            self.world.log(
                f"{actor.short_name()} is taken into the {getattr(deity, 'value', str(deity))} adventurer school{note}.",
                importance=1,
                category="adventurer_school",
            )
        return True

    def _ensure_adventurer_children_in_school(self) -> None:
        """Safety net: adventurer-lineage children belong off-map until age 16."""
        for actor in self.world.living_actors():
            if not self._actor_is_adventurer_child(actor):
                continue
            if getattr(actor, "in_school", False):
                continue
            deity = getattr(actor, "deity", None)
            self._try_enroll_school_child(actor, deity, reason="safety_net")

    def _economy_tick(self) -> None:
        if not bool(globals().get("ECONOMY_ENABLED", True)):
            return
        for region in self.world.regions.values():
            try:
                region_economy_tick(self, region)
            except Exception as exc:
                self.world.log(f"Economy tick failed in {getattr(region, 'name', region.id)}: {exc}", importance=1, category="economy")

    def _divine_maintenance_interval_ticks(self) -> int:
        """Cadence for god-state refresh and divine directive cleanup.

        Default is weekly: 21 ticks in the current calendar model
        (3 ticks/day * 7 days). Player actions still force-refresh god state
        immediately where needed.
        """
        return max(1, int(globals().get("DIVINE_MAINTENANCE_INTERVAL_TICKS", 21)))

    def _god_state_refresh_interval_ticks(self) -> int:
        return max(1, int(globals().get("GOD_STATE_REFRESH_INTERVAL_TICKS", self._divine_maintenance_interval_ticks())))

    def _god_state_refresh_due(self) -> bool:
        world = self.world
        if not getattr(world, "god_state", None):
            return True
        last = int(getattr(world, "last_god_state_refresh_tick", -999999))
        return (int(getattr(world, "tick", 0)) - last) >= self._god_state_refresh_interval_ticks()

    def _refresh_god_state_if_due(self, *, force: bool = False):
        if force or self._god_state_refresh_due():
            state = self._update_god_state()
            self.world.last_god_state_refresh_tick = int(getattr(self.world, "tick", 0))
            if hasattr(self, "_maybe_unlock_revelation_schools"):
                self._maybe_unlock_revelation_schools(state)
            return state
        return getattr(self.world, "god_state", {})

    def _region_dominant_deity(self, region_id: int):
        faith = getattr(self.world, "commoner_faith_by_region", {}).get(region_id, {})
        if not faith:
            return None, 0, 0.0
        total = sum(max(0, int(v)) for v in faith.values())
        if total <= 0:
            return None, 0, 0.0
        deity = max(faith, key=lambda d: faith.get(d, 0))
        count = max(0, int(faith.get(deity, 0)))
        return deity, count, (count / total) * 100.0

    def _monthly_schedule(self, day: int, tod: str = "Morning") -> bool:
        """True once per month for an explicit day + time-of-day anchor."""
        return self._current_day == int(day) and self._current_tod == str(tod)

    def _monthly_schedule_day(self, *days: int) -> bool:
        """Backward-compatible shorthand: Morning tick on selected month days."""
        return self._current_tod == "Morning" and self._current_day in set(int(d) for d in days)

    def _seasonal_schedule_day(self, tod: str = "Morning") -> bool:
        """True once at the opening of each season, used for equinox/solstice-style checks."""
        return self._current_tod == str(tod) and self._current_day == 1 and self._current_month in (1, 4, 7, 10)

    def _season_end_schedule(self, tod: str = "Evening") -> bool:
        """True at the end of the last day of each season."""
        return self._current_tod == str(tod) and self._current_day == 30 and self._current_month in (3, 6, 9, 12)

    def _black_host_start_schedule(self) -> bool:
        """True only on the configured annual Black Host check date."""
        return (
            self._current_tod == "Morning"
            and self._current_month == int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_CHECK_MONTH", 6))
            and self._current_day == int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_CHECK_DAY", 6))
        )

    def _black_host_pulse_schedule(self) -> bool:
        """Monthly Black Host pulse anchor once the crisis is active."""
        return (
            self._current_tod == "Morning"
            and self._current_day == int(globals().get("ADVENTURER_SURPLUS_NECROMANCER_CHECK_DAY", 6))
        )

    def _month_end_schedule(self, tod: str = "Night") -> bool:
        return self._current_tod == str(tod) and self._current_day == 30

    def step(self) -> None:
        world = self.world
        world.tick += 1
        self._apply_divine_boons()
        self._current_year, self._current_month, self._current_day, self._current_tod, self._current_season = world.current_calendar()

        # Actor lifecycle remains birthday-based, but birthday/commemoration logging is disabled below.
        if self._current_tod == "Morning":
            self._actor_lifecycle_tick()

        # Black Host: annual 6/6 Morning surplus check, with monthly pulses only while active.
        if self._black_host_pulse_schedule():
            if getattr(world, "adventurer_surplus_necromancer_crisis", None) and hasattr(self, "_advance_adventurer_surplus_necromancer_crisis"):
                self._advance_adventurer_surplus_necromancer_crisis()
            elif self._black_host_start_schedule() and hasattr(self, "_maybe_start_adventurer_surplus_necromancer_crisis"):
                self._maybe_start_adventurer_surplus_necromancer_crisis()

        # Seasonal omen checks belong at the opening of a season.
        if self._seasonal_schedule_day("Morning"):
            pass

        # Morning: divine/admin setup.
        if self._current_tod == "Morning" and world.tick % self._divine_maintenance_interval_ticks() == 0:
            self._apply_divine_directive_maintenance()

        if self._monthly_schedule(1, "Morning"):
            self._ensure_adventurer_children_in_school()

        # Midday: governance, armies, and rule checks.
        if self._monthly_schedule(10, "Midday"):
            self._update_polities()
            self._apply_recovery_pressure()
            # Refugee mechanic intentionally disabled; it prolonged collapses without fixing them.
            # self._maybe_arrive_refugees()

        if self._monthly_schedule(20, "Midday"):
            for region_id in world.regions:
                world.evaluate_region_rule(region_id)

        # Evening: population, legacy/social rolls, economy, and regional drift.
        if self._monthly_schedule(1, "Evening"):
            self._legacy_tick()

        if self._monthly_schedule(20, "Evening"):
            self._economy_tick()

        if self._monthly_schedule(30, "Evening"):
            self._population_tick()
            self._apply_seasonal_drift()

        if self._season_end_schedule("Evening"):
            self._apply_true_seasonal_drift()

        if self._season_end_schedule("Night") and hasattr(self, "_seasonal_retired_actor_maintenance"):
            self._seasonal_retired_actor_maintenance()

        # Night: cleanup, fragmentation, decay, and month-end bookkeeping.
        if self._monthly_schedule(10, "Night") or self._monthly_schedule(20, "Night") or self._monthly_schedule(30, "Night"):
            world.cleanup_parties()
            self._handle_party_succession()

        if self._monthly_schedule(20, "Night"):
            self._apply_religious_conversion()

        if self._monthly_schedule(24, "Night"):
            self._apply_reputation_decay()
            self._decay_region_activity()

        if self._monthly_schedule(27, "Night"):
            self._apply_party_fragmentation()
            self._apply_evil_party_instability()

        self._rebuild_world_caches()
        self._prepare_turn_caches()

        for actor in world._living_actor_cache:
            if not hasattr(actor, "last_action_tick"):
                actor.last_action_tick = -1
            if not hasattr(actor, "last_move_tick"):
                actor.last_move_tick = -1
            actor.actions_remaining = ACTIONS_PER_TICK
            if not hasattr(actor, "combat_cooldown"):
                actor.combat_cooldown = 0
            if actor.combat_cooldown > 0:
                actor.combat_cooldown -= 1
            if actor.recovering > 0:
                actor.recovering -= 1
            heal_chance = 0.20 + max(0, actor.luck - 10) * 0.01
            if actor.hp < actor.max_hp and (actor.recovering > 0 or actor.combat_cooldown > 0 or self.rng.random() < heal_chance):
                actor.hp = min(actor.max_hp, actor.hp + 1)

        # Birthday/commemoration observer disabled. Cult status and songs carry living memory better.
        # if self._current_tod == "Morning":
        #     self._observe_birthdays_and_commemorations()

        self._tick_monster_age_and_terror()
        self._monster_spawn_check()
        self._relic_tick()
        self._lore_tick()
        if self._month_end_schedule("Night"):
            self._purge_nonformal_school_state()
        self._ai_immortal_tick()
        self._apply_relic_order_floor()

        active_actor_ids = []
        for actor in world._living_actor_cache:
            if not actor.is_adventurer():
                continue
            if getattr(actor, "retired", False) or getattr(actor, "withdrawn", False):
                continue
            if getattr(actor, 'resting_until_tick', -1) > world.tick:
                continue
            if self._is_actor_hot(actor):
                active_actor_ids.append(actor.id)
                continue
            if not self._is_shift_active(actor):
                continue
            if actor.party_id is None:
                active_actor_ids.append(actor.id)
                continue
            party = world.parties.get(actor.party_id)
            if party is None or party.leader_id == actor.id:
                active_actor_ids.append(actor.id)

        self.rng.shuffle(active_actor_ids)
        for actor_id in active_actor_ids:
            actor = world.actors.get(actor_id)
            if actor is None or not actor.alive:
                continue
            self._adventurer_turn(actor)

        monster_ids = [monster.id for monster in world._living_monster_cache]
        self.rng.shuffle(monster_ids)
        for monster_id in monster_ids:
            monster = world.monsters.get(monster_id)
            if monster is not None and monster.alive:
                self._monster_turn(monster)

        self._story_sync_all()

        if self._month_end_schedule("Night"):
            self._emit_monthly_summary()
            self._story_flush_files()
            self._record_history_snapshot(force=True)

        self._refresh_god_state_if_due()
        if self._season_end_schedule("Night"):
            self._emit_season_summary()
    def _observe_birthdays_and_commemorations(self) -> None:
        PopulationMixin._observe_birthdays_and_commemorations(self)
        world = self.world
        for item in world.commemorations_today():
            if self.rng.random() < 0.35:
                if item.region_id is None:
                    world.log(f"The continent observes {item.name}. {item.reason}", importance=2, category="commemoration")
                else:
                    world.log(f"{world.region_name(item.region_id)} observes {item.name}. {item.reason}", importance=2, category="commemoration")

    def _apply_seasonal_drift(self) -> None:
        """Monthly ambient regional drift from local adventurer alignment balance.

        Historical name retained for compatibility, but this is no longer a per-tick
        or per-day seasonal effect.
        """
        world = self.world
        for region in world.regions.values():
            local = [actor for actor in world.actors_in_region(region.id) if actor.is_adventurer()]
            good = len([actor for actor in local if actor.is_good()])
            evil = len([actor for actor in local if actor.is_evil()])
            if good > evil:
                world.adjust_region_state(region.id, control_delta=1, order_delta=1)
            elif evil > good:
                world.adjust_region_state(region.id, control_delta=-1, order_delta=-1)
            else:
                if region.order < 55:
                    world.adjust_region_state(region.id, order_delta=1)

    def _apply_true_seasonal_drift(self) -> None:
        """Actual biome/season drift, applied once at the end of each 90-day season."""
        world = self.world
        _year, _month, _day, _tod, season = world.current_calendar()
        for region in world.regions.values():
            if season == "Winter" and region.biome in ("Forest", "Highlands"):
                world.adjust_region_state(region.id, order_delta=-1)
            elif season == "Summer" and region.biome == "Plains":
                world.adjust_region_state(region.id, order_delta=1)

    def _emit_monthly_summary(self) -> None:
        world = self.world
        _, month, _, _, season = world.current_calendar()
        good_regions = len([r for r in world.regions.values() if r.control >= 20])
        evil_regions = len([r for r in world.regions.values() if r.control <= -20])
        contested = len(world.regions) - good_regions - evil_regions
        world.log(
            f"{MONTH_NAMES[month - 1]} closes in {season}: {good_regions} regions lean toward order, {evil_regions} toward oppression, {contested} remain contested.",
            importance=2,
            category="monthly",
        )

    def _emit_season_summary(self) -> None:
        world = self.world
        _, _, _, _, season = world.current_calendar()
        avg_order = sum(region.order for region in world.regions.values()) / len(world.regions)
        world.log(
            f"{season} ends with the continent's average order at {avg_order:.1f}.",
            importance=2,
            category="seasonal",
        )

    def _print_new_events(self) -> None:
        world = self.world
        last_counter = int(getattr(self, "_last_printed_event_counter", 0) or 0)
        current_counter = int(getattr(world, "event_counter", len(getattr(world, "events", []))) or 0)
        if current_counter <= last_counter:
            return
        delta = current_counter - last_counter
        new_events = list(getattr(world, "events", [])[-delta:])
        for event in new_events:
            if event.importance >= self.verbose_min_importance:
                print(f"[{event.timestamp}] {event.text}")
        self._last_printed_event_counter = current_counter
        self._last_printed_event_index = len(getattr(world, "events", []))

    def _pick_top_hero_and_villain(self) -> Tuple[Optional[Actor], Optional[Actor]]:
        living = self.world.living_actors()
        heroes = [a for a in living if a.is_adventurer() and not a.is_evil()]
        villains = [a for a in living if a.is_adventurer() and a.is_evil()]
        hero = max(heroes, key=lambda a: (a.reputation, a.dragon_kills, a.horror_kills, a.monster_kills, a.kills, a.power_rating()), default=None)
        villain = max(villains, key=lambda a: (a.reputation, a.regions_oppressed, a.kills, a.monster_kills, a.power_rating()), default=None)
        return hero, villain

    def _deity_influence_summary(self) -> List[Tuple[Deity, int, float]]:
        surviving = self.world.living_actors()
        total = len(surviving)
        results: List[Tuple[Deity, int, float]] = []
        for deity in self._pantheon_deities(self.world):
            count = len([actor for actor in surviving if actor.deity == deity])
            pct = (count / total * 100.0) if total else 0.0
            results.append((deity, count, pct))
        return results

    def _top_region(self) -> Region:
        return max(self.world.regions.values(), key=lambda r: (r.order, r.control, -r.danger))

    def _top_deity(self) -> Tuple[Deity, int, float]:
        return max(self._deity_influence_summary(), key=lambda item: item[2])

    def _hero_tale(self, hero: Actor) -> str:
        pieces = []
        if hero.title:
            pieces.append(f"Known as {hero.title}")
        if hero.dragon_kills:
            pieces.append(f"slew {hero.dragon_kills} dragon{'s' if hero.dragon_kills != 1 else ''}")
        if hero.horror_kills:
            pieces.append(f"broke {hero.horror_kills} ancient horror{'s' if hero.horror_kills != 1 else ''}")
        if hero.regions_defended:
            pieces.append(f"defended {hero.regions_defended} threatened frontier{'s' if hero.regions_defended != 1 else ''}")
        if not pieces:
            pieces.append(f"earned renown through {hero.kills} victories")
        return f"{hero.full_name()} {'; '.join(pieces)} from {self.world.region_name(hero.region_id)}."

    def _villain_tale(self, villain: Actor) -> str:
        pieces = []
        if villain.title:
            pieces.append(f"Bearing the name {villain.title}")
        if villain.regions_oppressed:
            pieces.append(f"oppressed {villain.regions_oppressed} region{'s' if villain.regions_oppressed != 1 else ''}")
        if villain.kills:
            pieces.append(f"left {villain.kills} bodies in their wake")
        if not pieces:
            pieces.append(f"spread fear from {self.world.region_name(villain.region_id)}")
        return f"{villain.full_name()} {'; '.join(pieces)}."

    def _chronicle_title(self, hero: Optional[Actor], top_region: Region, top_deity: Deity) -> str:
        if hero is not None:
            return f"The Chronicle of {hero.short_name()}, {top_region.name}, and {top_deity.value}"
        return f"The Chronicle of {top_region.name} under {top_deity.value}"

    def _ideology_similarity(self, actor: Actor, other: Actor) -> float:
        return actor.ideology_similarity(other)

    def _assign_best_friend(self, actor: Actor, other: Actor) -> bool:
        if actor.id == other.id or not actor.alive or not other.alive:
            return False
        spouse = self.world.actors.get(actor.spouse_id) if actor.spouse_id is not None else None
        if spouse is not None and spouse.alive and spouse.id != other.id:
            return False
        if actor.best_friend_id is not None:
            current = self.world.actors.get(actor.best_friend_id)
            if current is not None and current.alive:
                return current.id == other.id
        actor.best_friend_id = other.id
        return True

    def _add_friend(self, actor: Actor, other: Actor) -> bool:
        if actor.id == other.id or not actor.alive or not other.alive:
            return False
        if not actor.can_form_bff_with(other):
            return False
        friends = list(getattr(actor, "friend_ids", []) or [])
        if other.id == getattr(actor, "best_friend_id", None):
            return False
        if other.id in friends:
            return False
        friends = [fid for fid in friends if fid in self.world.actors and self.world.actors[fid].alive and fid != actor.id]
        max_friends = int(globals().get("MAX_FRIENDS", 5))
        if len(friends) >= max_friends:
            candidates = [self.world.actors[fid] for fid in friends if fid in self.world.actors]
            weakest = min(candidates, key=lambda f: (actor.ideology_similarity(f), f.reputation, f.power_rating()), default=None)
            if weakest is None or actor.ideology_similarity(other) <= actor.ideology_similarity(weakest):
                actor.friend_ids = friends[:max_friends]
                return False
            friends.remove(weakest.id)
        friends.append(other.id)
        actor.friend_ids = friends[:max_friends]
        return True

    def _forge_bff_pair(self, actor: Actor, other: Actor) -> bool:
        if not actor.can_form_bff_with(other):
            return False
        changed = self._assign_best_friend(actor, other)
        changed = self._assign_best_friend(other, actor) or changed
        if not changed:
            changed = self._add_friend(actor, other) or changed
            changed = self._add_friend(other, actor) or changed
        return changed

    def _register_nemesis(self, actor: Actor, enemy: Actor, revenge: bool = False, revenge_for: Optional[Actor] = None, reason: str = "") -> bool:
        if actor.id == enemy.id or not actor.alive or not enemy.alive:
            return False
        enemy_power = enemy.power_rating()
        if revenge:
            targets = [tid for tid in (getattr(actor, "revenge_target_ids", []) or []) if tid in self.world.actors and self.world.actors[tid].alive]
            max_targets = int(globals().get("MAX_REVENGE_TARGETS", 5))
            if enemy.id not in targets:
                if len(targets) >= max_targets:
                    weakest_id = min(targets, key=lambda tid: self.world.actors[tid].power_rating())
                    targets.remove(weakest_id)
                targets.append(enemy.id)
            actor.revenge_target_ids = targets[:max_targets]
            if not hasattr(actor, "revenge_for_actor_ids") or actor.revenge_for_actor_ids is None:
                actor.revenge_for_actor_ids = {}
            if revenge_for is not None:
                actor.revenge_for_actor_ids[enemy.id] = revenge_for.id
            # Legacy single-target fields remain populated for old UI/save logic.
            actor.revenge_target_id = enemy.id
            actor.revenge_for_actor_id = revenge_for.id if revenge_for is not None else None
            actor.nemesis_id = enemy.id
            actor.nemesis_power = enemy_power
            actor.nemesis_reason = reason or (f"revenge for {revenge_for.short_name()}" if revenge_for is not None else "revenge")
            return True
        current = self.world.actors.get(actor.nemesis_id) if actor.nemesis_id is not None else None
        if current is not None and current.alive and enemy_power <= getattr(actor, 'nemesis_power', 0):
            return current.id == enemy.id
        actor.nemesis_id = enemy.id
        actor.nemesis_power = enemy_power
        actor.nemesis_reason = reason or "ideological enemy met in battle"
        return True

    def _register_monster_revenge(self, actor: Actor, monster, revenge_for: Optional[Actor] = None) -> bool:
        if actor is None or monster is None or not getattr(actor, "alive", False) or not actor.is_adventurer():
            return False
        targets = [mid for mid in (getattr(actor, "revenge_monster_ids", []) or []) if mid in self.world.monsters and self.world.monsters[mid].alive]
        max_targets = int(globals().get("MAX_REVENGE_TARGETS", 5))
        if monster.id not in targets:
            if len(targets) >= max_targets:
                weakest_id = min(targets, key=lambda mid: self.world.monsters[mid].effective_power())
                targets.remove(weakest_id)
            targets.append(monster.id)
        actor.revenge_monster_ids = targets[:max_targets]
        if not hasattr(actor, "revenge_for_monster_ids") or actor.revenge_for_monster_ids is None:
            actor.revenge_for_monster_ids = {}
        if revenge_for is not None:
            actor.revenge_for_monster_ids[monster.id] = revenge_for.id
        return True

    def _best_nemesis_candidate(self, actor: Actor, enemies: List[Actor]) -> Optional[Actor]:
        candidates = [e for e in enemies if e.alive and e.is_adventurer() and actor.is_ideological_enemy(e)]
        if not candidates:
            return None
        candidates.sort(key=lambda e: (abs(actor.power_rating() - e.power_rating()), -e.power_rating(), self.rng.random()))
        return candidates[0]

    def _update_post_battle_relationships(self, attackers: List[Actor], defenders: List[Actor]) -> None:
        atk_survivors = [a for a in attackers if a.alive and a.is_adventurer()]
        def_survivors = [a for a in defenders if a.alive and a.is_adventurer()]

        for side in (atk_survivors, def_survivors):
            for i, actor in enumerate(side):
                if actor.spouse_id is not None:
                    spouse = self.world.actors.get(actor.spouse_id)
                    if spouse is not None and spouse.alive and spouse.id in [m.id for m in side]:
                        self._forge_bff_pair(actor, spouse)
                        continue
                if actor.best_friend_id is not None:
                    current = self.world.actors.get(actor.best_friend_id)
                    if current is not None and current.alive:
                        friends = [other for other in side[i+1:] if actor.can_form_bff_with(other)]
                        if friends and self.rng.random() < 0.35:
                            friend = max(friends, key=lambda other: (actor.ideology_similarity(other), other.reputation, self.rng.random()))
                            self._add_friend(actor, friend)
                            self._add_friend(friend, actor)
                        continue
                partners = [other for other in side[i+1:] if actor.can_form_bff_with(other)]
                if partners:
                    partner = max(partners, key=lambda other: (actor.ideology_similarity(other), -abs(actor.power_rating() - other.power_rating()), self.rng.random()))
                    self._forge_bff_pair(actor, partner)

        for actor in atk_survivors:
            target = self._best_nemesis_candidate(actor, def_survivors)
            if target is not None:
                self._register_nemesis(actor, target, reason=f"survived battle against {target.short_name()}")
        for actor in def_survivors:
            target = self._best_nemesis_candidate(actor, atk_survivors)
            if target is not None:
                self._register_nemesis(actor, target, reason=f"survived battle against {target.short_name()}")

    def _propagate_revenge_from_death(self, victim: Actor, killer: Optional[Actor]) -> None:
        if killer is None or not killer.alive or killer.id == victim.id:
            return
        avengers: Dict[int, Actor] = {}
        spouse = self.world.actors.get(victim.spouse_id) if victim.spouse_id is not None else None
        if spouse is not None and spouse.alive and spouse.is_adventurer():
            avengers[spouse.id] = spouse
        best_friend = self.world.actors.get(victim.best_friend_id) if victim.best_friend_id is not None else None
        if best_friend is not None and best_friend.alive and best_friend.is_adventurer():
            avengers[best_friend.id] = best_friend
        for friend_id in getattr(victim, "friend_ids", []) or []:
            friend = self.world.actors.get(friend_id)
            if friend is not None and friend.alive and friend.is_adventurer():
                avengers[friend.id] = friend
        if self._calculate_age(victim) < 16:
            for parent_field in ("mother_id", "father_id"):
                parent = self.world.actors.get(getattr(victim, parent_field, None))
                if parent is not None and parent.alive and parent.is_adventurer():
                    avengers[parent.id] = parent
        for child_id in getattr(victim, "children_ids", []) or []:
            child = self.world.actors.get(child_id)
            if child is not None and child.alive and self._calculate_age(child) <= 16:
                avengers[child.id] = child
        party = self.world.get_party(victim)
        if party is not None:
            for mid in party.member_ids:
                if mid == victim.id:
                    continue
                member = self.world.actors.get(mid)
                if member is not None and member.alive and member.is_adventurer():
                    avengers[mid] = member
        for avenger in avengers.values():
            self._register_nemesis(avenger, killer, revenge=True, revenge_for=victim, reason=f"{killer.short_name()} killed {victim.short_name()}")

    def _propagate_monster_revenge_from_death(self, victim: Actor, monster) -> None:
        if monster is None or not getattr(monster, "alive", False):
            return
        avengers: Dict[int, Actor] = {}
        if self._calculate_age(victim) < 16:
            for parent_field in ("mother_id", "father_id"):
                parent = self.world.actors.get(getattr(victim, parent_field, None))
                if parent is not None and parent.alive and parent.is_adventurer():
                    avengers[parent.id] = parent
        for avenger in avengers.values():
            if self._register_monster_revenge(avenger, monster, revenge_for=victim):
                self.world.log(
                    f"{avenger.full_name()} swears vengeance on {monster.name} for the death of {victim.short_name()}.",
                    importance=3,
                    category="revenge",
                )

    def _resolve_revenge_if_needed(self, fallen: Actor) -> None:
        fallen_id = fallen.id
        for actor in self.world.living_actors():
            # Fast skip: most actors have no revenge targets at all.
            rtids = getattr(actor, "revenge_target_ids", None)
            if not rtids or fallen_id not in rtids:
                continue
            targets = [tid for tid in rtids if tid != fallen_id]
            revenge_for_id = getattr(actor, "revenge_for_actor_ids", {}).get(fallen.id)
            revenge_for = self.world.actors.get(revenge_for_id) if revenge_for_id is not None else None
            actor.revenge_target_ids = targets
            if hasattr(actor, "revenge_for_actor_ids"):
                actor.revenge_for_actor_ids.pop(fallen.id, None)
            if getattr(actor, 'revenge_target_id', None) == fallen.id:
                actor.revenge_target_id = targets[-1] if targets else None
                actor.revenge_for_actor_id = getattr(actor, "revenge_for_actor_ids", {}).get(actor.revenge_target_id)
            if getattr(actor, 'nemesis_id', None) == fallen.id:
                actor.nemesis_id = None
                actor.nemesis_power = 0
                actor.nemesis_reason = ""
            if getattr(fallen, "death_killer_id", None) == actor.id:
                self.world.log(
                    f"{actor.full_name()} avenges {revenge_for.short_name() if revenge_for is not None else 'the fallen'} by killing {fallen.full_name()}.",
                    importance=3,
                    category="revenge",
                )
                self._grant_revenge_boon(actor, fallen)
            else:
                self.world.log(
                    f"{actor.full_name()}'s vengeance against {fallen.full_name()} ends with the target dead.",
                    importance=1,
                    category="revenge",
                )

    def _resolve_monster_revenge_if_needed(self, monster, slayer_ids=None) -> None:
        slayer_ids = set(slayer_ids or [])
        monster_id = monster.id
        for actor in self.world.living_actors():
            rmids = getattr(actor, "revenge_monster_ids", None)
            if not rmids or monster_id not in rmids:
                continue
            targets = [mid for mid in rmids if mid != monster_id]
            revenge_for_id = getattr(actor, "revenge_for_monster_ids", {}).get(monster.id)
            revenge_for = self.world.actors.get(revenge_for_id) if revenge_for_id is not None else None
            actor.revenge_monster_ids = targets
            if hasattr(actor, "revenge_for_monster_ids"):
                actor.revenge_for_monster_ids.pop(monster.id, None)
            if actor.id in slayer_ids:
                self.world.log(
                    f"{actor.full_name()} avenges {revenge_for.short_name() if revenge_for is not None else 'the fallen'} by killing {monster.name}.",
                    importance=3,
                    category="revenge",
                )
                self._grant_revenge_boon(actor, monster)
            else:
                self.world.log(
                    f"{actor.full_name()}'s vengeance against {monster.name} ends with the monster dead.",
                    importance=1,
                    category="revenge",
                )

    def _rebuild_world_caches(self) -> None:
        # Incremental helpers (register_actor, unregister_actor, move_actor, etc.)
        # maintain the caches on every structural change. A full rebuild is only
        # needed when the caches haven't been initialized yet; calling it
        # unconditionally every tick iterates all actors and monsters for nothing.
        self.world._ensure_runtime_caches()

    def _apply_reputation_decay(self):
        for actor in self.world.living_actors():
            rep = actor.reputation
            if rep <= 0:
                continue
            if rep > 300:
                rate = 0.03
            elif rep > 100:
                rate = 0.02
            else:
                rate = 0.01
            decay = max(1, int(rep * rate))
            actor.reputation -= decay


def _pantheon_deities(self, world=None):
    world = world if world is not None else getattr(self, "world", None)
    if world is not None and hasattr(world, "gods"):
        return list(world.gods)
    return list(getattr(self, "pantheon", list(Deity)))


def _empty_faith_map(self, world=None):
    return {deity: 0 for deity in self._pantheon_deities(world)}


def _resolve_deity_name(self, name: str, fallback_alignment=None, traits=None):
    wanted = str(name or "").strip().lower()
    for deity in self._pantheon_deities():
        if deity_value(deity).lower() == wanted:
            return deity
    if fallback_alignment is not None:
        return self._weighted_random_deity(fallback_alignment, traits=traits)
    return self._weighted_random_deity(self.rng.choice(list(Alignment)), traits=traits)


def _alignment_distance(self, a, b_name: str) -> int:
    try:
        b = next(al for al in Alignment if al.value.lower() == str(b_name).lower())
    except StopIteration:
        return 2
    return abs(a.law_axis - b.law_axis) + abs(a.moral_axis - b.moral_axis)


def _weighted_random_deity(self, alignment: "Alignment", region_id: int | None = None, parent_deities=None, traits=None):
    deities = self._pantheon_deities()
    profiles = getattr(self, "god_profiles", {})
    traits = [str(t).strip().lower() for t in (traits or [])]
    weights = []

    for deity in deities:
        profile = profiles.get(deity)
        weight = 10.0
        if profile is not None:
            dist = self._alignment_distance(alignment, profile.alignment)
            weight += max(0, 30 - (dist * 8))
            weight *= max(0.10, float(getattr(profile, "conversion_bias", 1.0)))
            favored = {str(t).lower() for t in getattr(profile, "favored_traits", [])}
            disfavored = {str(t).lower() for t in getattr(profile, "disfavored_traits", [])}
            weight += 7.0 * len(favored.intersection(traits))
            weight -= 5.0 * len(disfavored.intersection(traits))
        else:
            # Defensive fallback for unknown deity-like objects.
            if alignment.moral_axis > 0 and deity == Deity.LORD_OF_LIGHT:
                weight += 30
            elif alignment.moral_axis < 0 and deity == Deity.LORD_OF_DARKNESS:
                weight += 30
            elif alignment.moral_axis == 0 and deity == Deity.GOD_OF_CHANCE:
                weight += 25

        if parent_deities:
            for parent_deity in parent_deities:
                if deity == parent_deity:
                    weight += 15

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
                faith_map = getattr(world, "commoner_faith_by_region", {}).get(region_id, {})
                if faith_map:
                    dominant_commoner = max(deities, key=lambda d: faith_map.get(d, 0))
                    if deity == dominant_commoner:
                        weight += 10
                if deity == favored:
                    weight += 140 if polity_id is not None else 70

        weights.append(max(1.0, weight))

    return self.rng.choices(deities, weights=weights, k=1)[0]


def _generate_population(self, count: int, regions: Dict[int, "Region"]) -> Dict[int, Actor]:
    actors: Dict[int, Actor] = {}
    ratio = self.rng.uniform(0.01, 0.025)
    adventurer_count = max(1, int(round(count * ratio)))
    role_choices = [Role.FIGHTER, Role.WARDEN, Role.WIZARD, Role.BARD]
    role_weights = [12, 8, 2, 3]
    current_year = 1
    actor_id = 1
    for _ in range(adventurer_count):
        role = self.rng.choices(role_choices, weights=role_weights, k=1)[0]
        alignment = self._pick_alignment_for_role(role)
        traits = self.rng.sample(TRAITS, k=2)
        deity = self._weighted_random_deity(alignment, traits=traits)
        stats = self._roll_stats(role)
        hp = self._base_hp(role, stats[2])
        region_id = self.rng.choice(list(regions.keys()))
        first, surname, sex = self._random_person_identity()
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
        actor_id += 1
    return actors


def _stochastic_round(self, value: float) -> int:
    whole = int(value)
    if self.rng.random() < max(0.0, value - whole):
        whole += 1
    return max(0, whole)

def _initialize_commoner_demographics(self, world: World) -> None:
    world.commoner_males_by_region = {}
    world.commoner_female_children_by_region = {}
    world.commoner_fertile_females_by_region = {}
    world.commoner_older_females_by_region = {}
    world.commoner_pregnancy_queue_by_region = {}
    for rid in world.regions:
        count = int(world.commoners_by_region.get(rid, 0))
        females = count // 2
        males = count - females
        female_children = int(females * 0.35)
        fertile = int(females * 0.45)
        older = max(0, females - female_children - fertile)
        world.commoner_males_by_region[rid] = males
        world.commoner_female_children_by_region[rid] = female_children
        world.commoner_fertile_females_by_region[rid] = fertile
        world.commoner_older_females_by_region[rid] = older
        world.commoner_pregnancy_queue_by_region[rid] = [0 for _ in range(COMMONER_PREGNANCY_MONTHS)]
    world.commoner_pregnancies_started = 0
    world.commoner_births_due = 0

def _sync_commoner_demographics(self, region_id: int) -> None:
    world = self.world
    count = max(0, int(world.commoners_by_region.get(region_id, 0)))
    total = (world.commoner_males_by_region.get(region_id, 0) + world.commoner_female_children_by_region.get(region_id, 0) + world.commoner_fertile_females_by_region.get(region_id, 0) + world.commoner_older_females_by_region.get(region_id, 0))
    delta = count - total
    if delta > 0:
        add_f = delta // 2
        world.commoner_males_by_region[region_id] = world.commoner_males_by_region.get(region_id, 0) + (delta - add_f)
        world.commoner_fertile_females_by_region[region_id] = world.commoner_fertile_females_by_region.get(region_id, 0) + add_f
    elif delta < 0:
        self._remove_commoner_demographics(region_id, -delta)

def _age_commoner_demographics_monthly(self, region_id: int) -> None:
    world = self.world
    fc = world.commoner_female_children_by_region.get(region_id, 0)
    ff = world.commoner_fertile_females_by_region.get(region_id, 0)
    child_to_fertile = min(fc, self._stochastic_round(fc / (15 * 12)))
    fertile_to_older = min(ff, self._stochastic_round(ff / (25 * 12)))
    world.commoner_female_children_by_region[region_id] = fc - child_to_fertile
    world.commoner_fertile_females_by_region[region_id] = ff + child_to_fertile - fertile_to_older
    world.commoner_older_females_by_region[region_id] = world.commoner_older_females_by_region.get(region_id, 0) + fertile_to_older

def _add_commoner_demographic_births(self, region_id: int, births: int) -> None:
    if births <= 0:
        return
    world = self.world
    male_births = min(births, self._stochastic_round(births * 0.51))
    female_births = births - male_births
    world.commoner_males_by_region[region_id] = world.commoner_males_by_region.get(region_id, 0) + male_births
    world.commoner_female_children_by_region[region_id] = world.commoner_female_children_by_region.get(region_id, 0) + female_births

def _remove_commoner_demographics(self, region_id: int, deaths: int) -> None:
    if deaths <= 0:
        return
    world = self.world
    names = ('commoner_males_by_region', 'commoner_female_children_by_region', 'commoner_fertile_females_by_region', 'commoner_older_females_by_region')
    total = sum(getattr(world, name).get(region_id, 0) for name in names)
    if total <= 0:
        return
    remaining = min(deaths, total)
    for name in names:
        if remaining <= 0:
            break
        mapping = getattr(world, name)
        available = mapping.get(region_id, 0)
        take = min(available, int(deaths * (available / total)))
        mapping[region_id] = available - take
        remaining -= take
    for name in names:
        if remaining <= 0:
            break
        mapping = getattr(world, name)
        take = min(remaining, mapping.get(region_id, 0))
        mapping[region_id] -= take
        remaining -= take

def _shift_commoner_demographics(self, src_region_id: int, dst_region_id: int, amount: int) -> None:
    if amount <= 0:
        return
    world = self.world
    total = max(1, int(world.commoners_by_region.get(src_region_id, 0)))
    names = ('commoner_males_by_region', 'commoner_female_children_by_region', 'commoner_fertile_females_by_region', 'commoner_older_females_by_region')
    remaining = amount
    for name in names:
        mapping = getattr(world, name)
        available = mapping.get(src_region_id, 0)
        moved = min(available, int(amount * (available / total)))
        mapping[src_region_id] = available - moved
        mapping[dst_region_id] = mapping.get(dst_region_id, 0) + moved
        remaining -= moved
    for name in names:
        if remaining <= 0:
            break
        mapping = getattr(world, name)
        take = min(remaining, mapping.get(src_region_id, 0))
        mapping[src_region_id] -= take
        mapping[dst_region_id] = mapping.get(dst_region_id, 0) + take
        remaining -= take

def _build_world(self, seed: str) -> World:
    regions = self._generate_regions(REGION_COUNT)
    scaled_initial_population = max(1, int(round(INITIAL_POPULATION * self.population_scale)))
    actors = self._generate_population(scaled_initial_population, regions)
    # Seed/story actors can be loaded before the World object exists.  Keep their
    # IDs staged here so _story_sync_all can use the fast story actor set once
    # the world is built.
    self._pending_story_actor_ids = set()
    if getattr(self, "load_mce", True):
        self._story_load_seed_actors(actors, regions)
    monsters = self._generate_initial_monsters(regions)
    world = World(rng=self.rng, regions=regions, actors=actors, monsters=monsters, parties={}, seed_used=seed)
    world._story_actor_ids = set(getattr(self, "_pending_story_actor_ids", set()) or set())
    world.gods = list(getattr(self, "pantheon", list(Deity)))
    world.god_profiles = dict(getattr(self, "god_profiles", {}))
    world.souls_by_deity = {deity: max(0, int(getattr(world.god_profiles.get(deity), "starting_souls", 0) or 0)) for deity in world.gods}
    cap = int(globals().get("IMMORTAL_SOUL_CAP", -1))
    if cap >= 0:
        world.souls_by_deity = {deity: min(amount, cap) for deity, amount in world.souls_by_deity.items()}
    world.active_boons = {}
    world.next_boon_id = 1
    world.next_actor_id = max(actors.keys(), default=0) + 1
    self._seed_relics(world)
    if getattr(self, "load_mce", True):
        self._assign_pending_custom_relics(world)
    world.spawned_horror_titles = set(self._spawned_horror_titles)
    world.generated_by_role = self._count_generated_roles(actors)
    world.generated_monsters_by_kind = self._count_generated_monsters(monsters)
    commoner_total = max(0, scaled_initial_population - len(actors))
    world.commoners_by_region = {rid: 0 for rid in regions}
    world.commoner_faith_by_region = {rid: {deity: 0 for deity in world.gods} for rid in regions}
    for _ in range(commoner_total):
        rid = self.rng.choice(list(regions.keys()))
        world.commoners_by_region[rid] += 1
        deity = self._commoner_birth_deity(rid, world=world)
        world.commoner_faith_by_region[rid][deity] += 1
    self._initialize_commoner_demographics(world)
    self.world = world
    self._ensure_adventurer_schools()
    self._ensure_lore_state()
    self._refresh_god_state_if_due(force=True)
    world.generated_by_role[Role.COMMONER] = commoner_total
    world.commoner_deaths_by_cause = {}
    world.commoner_deaths_by_region = {rid: 0 for rid in regions}
    world.aggregate_commoner_mode = True
    world.population_scale = self.population_scale
    world.initial_population = scaled_initial_population
    world.source_files = {
        "simulator": Path(__file__).name,
        "config": _runtime_source_name("FASEcfg", "FASEcfg.py"),
        "class": _runtime_source_name("FASEclass", "FASEclass.py"),
        "population": _runtime_module_source(population_module, "FASEpop.py"),
        "legacy": _runtime_module_source(legacy_module, "FASEleg.py"),
        "lore": _runtime_module_source(lore_module, "FASElore.py"),
        "relics": _runtime_module_source(relic_module, "FASErlc.py"),
        "immortals": _runtime_source_name("FASEimm", "FASEimm.py"),
        "summary": _runtime_module_source(summary, "FASEsum.py"),
        "economy": _runtime_source_name("FASEeco", "FASEeco.py"),
        "morgue": _runtime_source_name("FASEmrg", "FASEmrg.py"),
        "historian": _runtime_source_name("FASEtome", "FASEtome.py"),
        "combat": _runtime_module_source(combat_runtime_module, "FASEcom.py"),
        "monsters": _runtime_module_source(monster_runtime_module, "FASEmon.py"),
        "party": _runtime_module_source(party_runtime_module, "FASEprty.py"),
        "politics": _runtime_module_source(politics_runtime_module, "FASEpoli.py"),
        "world": _runtime_module_source(world_runtime_module, "FASEworld.py"),
        "start_game": _glob_latest("start_game_v*.py"),
        "ux": _parse_fase_runmodule("FASEux.py"),
        "fantag": _runtime_source_name("fantag_v9", "fantag_v9.py"),
        "fantgg": _runtime_source_name("fantgg_v3", "fantgg_v3.py"),
    }
    for actor in actors.values():
        if actor.is_adventurer():
            actor.duty_shift = self.rng.randrange(ADVENTURER_SHIFT_COUNT)
        if getattr(actor, "is_story_actor", False):
            self._story_rebind_file(actor)
            actor.story_snapshot = self._story_snapshot_for_actor(actor)
            actor.story_dirty = True
    world.log(
        "A small continent of forest, plains, and highlands fills with aggregated common folk, wandering adventurers, lurking monsters, and distant divine attention.",
        importance=3,
        category="world",
    )
    return world



def _region_favored_deity(self, region_id: int, world=None):
    world = world if world is not None else getattr(self, "world", None)
    if world is None:
        return None
    region = world.regions.get(region_id)
    if region is None:
        return None
    polity_id = getattr(region, "polity_id", None)
    if polity_id is not None and hasattr(world, "polities") and polity_id in world.polities:
        ruler = world.actors.get(world.polities[polity_id].ruler_id)
        if ruler is not None and ruler.alive:
            return ruler.deity
    ruler_id = getattr(region, "ruler_id", None)
    if ruler_id is not None and ruler_id in world.actors:
        ruler = world.actors.get(ruler_id)
        if ruler is not None and ruler.alive:
            return ruler.deity
    return None

def _bulk_apply_faith_addition(self, faith_map, total, favored=None):
    if total <= 0:
        return 0
    deities = self._pantheon_deities()
    current_total = sum(faith_map.get(d, 0) for d in deities)
    if current_total <= 0:
        weights = {d: 1 for d in deities}
        if favored is not None:
            weights[favored] += 2
    else:
        weights = {d: max(1, faith_map.get(d, 0)) for d in deities}
        if favored is not None:
            weights[favored] += max(1, current_total // 10)

    weight_total = sum(weights.values()) or 1
    assigned = 0
    for i, deity in enumerate(deities):
        if i == len(deities) - 1:
            add = total - assigned
        else:
            add = int(total * (weights[deity] / weight_total))
            assigned += add
        faith_map[deity] = faith_map.get(deity, 0) + add
    return total

def _bulk_apply_faith_loss(self, faith_map, total):
    if total <= 0:
        return 0
    deities = self._pantheon_deities()
    current_total = sum(faith_map.get(d, 0) for d in deities)
    if current_total <= 0:
        return 0
    actual = min(total, current_total)
    assigned = 0
    for i, deity in enumerate(deities):
        available = faith_map.get(deity, 0)
        if i == len(deities) - 1:
            loss = min(available, actual - assigned)
        else:
            loss = min(available, int(actual * (available / current_total)))
            assigned += loss
        faith_map[deity] = max(0, available - loss)

    removed = current_total - sum(faith_map.get(d, 0) for d in deities)
    leftover = actual - removed
    if leftover > 0:
        ranked = sorted(deities, key=lambda d: faith_map.get(d, 0), reverse=True)
        for deity in ranked:
            if leftover <= 0:
                break
            take = min(leftover, faith_map.get(deity, 0))
            faith_map[deity] -= take
            leftover -= take
    return actual


def _shift_commoner_faith(self, src_region_id: int, dst_region_id: int, amount: int) -> int:
    world = self.world
    if amount <= 0 or not hasattr(world, "commoner_faith_by_region"):
        return 0
    deities = self._pantheon_deities(world)
    src = world.commoner_faith_by_region.setdefault(src_region_id, self._empty_faith_map(world))
    dst = world.commoner_faith_by_region.setdefault(dst_region_id, self._empty_faith_map(world))
    available = sum(src.get(d, 0) for d in deities)
    moved = min(amount, available)
    if moved <= 0:
        return 0

    src_total = sum(src.get(d, 0) for d in deities) or 1
    transferred = {d: 0 for d in deities}
    assigned = 0
    for i, deity in enumerate(deities):
        if i == len(deities) - 1:
            take = moved - assigned
        else:
            take = min(src.get(deity, 0), int(moved * (src.get(deity, 0) / src_total)))
            assigned += take
        transferred[deity] = take
        src[deity] = max(0, src.get(deity, 0) - take)
        dst[deity] = dst.get(deity, 0) + take

    leftover = moved - sum(transferred.values())
    if leftover > 0:
        ranked = sorted(deities, key=lambda d: src.get(d, 0), reverse=True)
        for deity in ranked:
            if leftover <= 0:
                break
            take = min(leftover, src.get(deity, 0))
            src[deity] -= take
            dst[deity] += take
            leftover -= take
    return moved

def _add_commoner_births(self, region_id: int, births: int) -> None:
    world = self.world
    if births <= 0:
        return
    faith_map = world.commoner_faith_by_region.setdefault(region_id, self._empty_faith_map(world))
    favored = self._region_favored_deity(region_id)
    self._bulk_apply_faith_addition(faith_map, births, favored=favored)

def _commoner_death_cause_from_context(self, cause: Optional[str] = None) -> str:
    if cause:
        return str(cause)
    try:
        import inspect
        frame = inspect.currentframe()
        frame = frame.f_back if frame is not None else None
        while frame is not None:
            local_monster = frame.f_locals.get("monster")
            if local_monster is not None:
                kind = getattr(getattr(local_monster, "kind", None), "value", None) or str(getattr(local_monster, "kind", "Monster"))
                return f"monster raid: {kind}"
            if frame.f_code.co_name == "_apply_divine_disaster":
                return "divine disaster"
            frame = frame.f_back
    except Exception:
        pass
    return "miscellaneous aggregate loss"

def _record_commoner_deaths(self, region_id: int, deaths: int, cause: Optional[str] = None) -> None:
    if deaths <= 0:
        return
    world = self.world
    cause_key = self._commoner_death_cause_from_context(cause)
    if not hasattr(world, "commoner_deaths_by_cause"):
        world.commoner_deaths_by_cause = {}
    if not hasattr(world, "commoner_deaths_by_region"):
        world.commoner_deaths_by_region = {rid: 0 for rid in getattr(world, "regions", {})}
    world.commoner_deaths_by_cause[cause_key] = world.commoner_deaths_by_cause.get(cause_key, 0) + deaths
    world.commoner_deaths_by_region[region_id] = world.commoner_deaths_by_region.get(region_id, 0) + deaths

def _remove_commoner_deaths(self, region_id: int, deaths: int, cause: Optional[str] = None) -> int:
    world = self.world
    faith_map = world.commoner_faith_by_region.setdefault(region_id, self._empty_faith_map(world))
    if deaths <= 0:
        return 0
    actual = self._bulk_apply_faith_loss(faith_map, deaths)
    self._record_commoner_deaths(region_id, actual, cause)
    return actual

def _allocate_actor_id(self) -> int:
    new_id = self.world.next_actor_id
    self.world.next_actor_id += 1
    return new_id

def _spawn_adventurer_from_commoners(self, region_id: int) -> Optional[Actor]:
    world = self.world
    if world.commoners_by_region.get(region_id, 0) <= 0:
        return None
    world.commoners_by_region[region_id] -= 1
    role = self.rng.choices([Role.FIGHTER, Role.WARDEN, Role.WIZARD, Role.BARD], weights=[55, 34, 3, 8], k=1)[0]
    alignment = self.rng.choice(list(Alignment))
    faith_map = world.commoner_faith_by_region.setdefault(region_id, self._empty_faith_map(world))
    available = [deity for deity in self._pantheon_deities(world) if faith_map.get(deity, 0) > 0]
    if available:
        deity = max(available, key=lambda d: faith_map.get(d, 0) + self.rng.random())
        faith_map[deity] -= 1
    else:
        deity = self._weighted_random_deity(alignment, region_id=region_id)
    stats = self._roll_stats(role)
    hp = self._base_hp(role, stats[2])
    first, surname, sex = self._random_person_identity()
    age = 16
    current_year = self._current_year if hasattr(self, '_current_year') else 1
    actor = Actor(
        id=self._allocate_actor_id(),
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
        traits=self.rng.sample(TRAITS, k=2),
        birth_year=current_year - age,
        birth_month=self.rng.randint(1, 12),
        birth_day=self.rng.randint(1, 30),
        spouse_id=None,
        sex=sex,
        mother_label="Commoner",
        father_label="Commoner",
    )
    local_polities = [p for p in world.polities.values() if region_id in p.region_ids]
    if local_polities:
        strongest = max(local_polities, key=lambda p: (len(p.region_ids), len(p.member_actor_ids), p.legitimacy))
        ruler = world.actors.get(strongest.ruler_id)
        if ruler and ((actor.is_good() and not ruler.is_evil()) or (actor.is_evil() and ruler.is_evil()) or (actor.is_neutral_morality() and not (actor.is_evil() and ruler.is_good()))):
            actor.polity_id = strongest.id
            actor.loyalty = strongest.ruler_id
            strongest.member_actor_ids.append(actor.id)
    actor.duty_shift = self.rng.randrange(ADVENTURER_SHIFT_COUNT)
    if hasattr(world, "register_actor"):
        world.register_actor(actor)
    else:
        world.actors[actor.id] = actor
    world.generated_by_role[role] += 1
    world.log(
        f"{actor.short_name()} rises from the common folk of {world.region_name(region_id)} and takes up the life of a {role.value.lower()}.",
        importance=2,
        category="coming_of_age",
    )
    return actor


def _retirement_check(self, actor: Actor) -> None:
    if not getattr(actor, "alive", True):
        return
    if not getattr(actor, "can_retire", lambda: False)():
        return
    if getattr(actor, "retired", False):
        return
    age = self._calculate_age(actor)
    if age < actor.retirement_age():
        return

    old_party_id = getattr(actor, "party_id", None)
    if old_party_id is not None and hasattr(self.world, "remove_from_party"):
        self.world.remove_from_party(actor)
    else:
        actor.party_id = None
        actor.loyalty = None

    actor.retired = True
    actor.retirement_year = self.world.current_calendar()[0]
    actor.actions_remaining = 0
    actor.recovering = max(getattr(actor, "recovering", 0), 1)
    actor.resting_until_tick = max(getattr(actor, "resting_until_tick", -1), self.world.tick + TICKS_PER_MONTH)

    # Retired rulers can remain political figures; non-rulers drop adventuring loyalty.
    if getattr(actor, "polity_id", None) is not None:
        actor.loyalty = actor.id

    self.world.log(
        f"{actor.short_name()} lays down the adventurer's life and retires in {self.world.region_name(actor.region_id)}.",
        importance=2,
        category="retirement",
    )


def _actor_lifecycle_tick(self) -> None:
    world = self.world
    _, month, day, _, _ = world.current_calendar()

    # The aggregate commoner population bypasses PopulationMixin._population_tick(),
    # so individual actors need their own birthday pass here. This covers adventurer
    # children, retirement, and old-age death without reintroducing individual commoners.
    for actor in list(world.living_actors()):
        if getattr(actor, "birth_month", None) != month or getattr(actor, "birth_day", None) != day:
            continue

        if getattr(actor, "role", None) == Role.COMMONER:
            self._coming_of_age_check(actor)

        if not getattr(actor, "alive", False):
            continue

        if actor.is_adventurer() and not getattr(actor, "retired", False) and not getattr(actor, "in_school", False):
            self._retirement_check(actor)

        if getattr(actor, "alive", False):
            self._natural_death_check(actor)

def _population_tick(self) -> None:
    world = self.world
    if not hasattr(world, 'commoners_by_region'):
        return
    if not (hasattr(self, '_monthly_schedule') and self._monthly_schedule(30, 'Evening')):
        return
    if not hasattr(world, 'commoner_pregnancy_queue_by_region') or not world.commoner_pregnancy_queue_by_region:
        self._initialize_commoner_demographics(world)

    # Pre-compute safety scores once for all regions to avoid repeated calls inside the migration loop.
    safety_scores = {rid: self._region_safety_score(rid) for rid in world.regions}

    for region_id, region in world.regions.items():
        count = world.commoners_by_region.get(region_id, 0)
        if count <= 0:
            continue
        self._sync_commoner_demographics(region_id)
        self._age_commoner_demographics_monthly(region_id)
        local_actors = world.actors_in_region(region_id)
        local_monsters = world.monsters_in_region(region_id)
        # Single pass over actors instead of three separate comprehensions.
        evil_adventurers = 0
        good_adventurers = 0
        for a in local_actors:
            if a.alive and a.is_adventurer():
                if a.is_evil():
                    evil_adventurers += 1
                elif a.is_good():
                    good_adventurers += 1
        monster_threat = sum(1 + (self._monster_strength_bonus(m) // 6) for m in local_monsters if m.alive and m.kind in (MonsterKind.GOBLIN, MonsterKind.GIANT, MonsterKind.DRAGON, MonsterKind.ANCIENT_HORROR))
        pressure = count / max(1, self._effective_region_capacity(region))
        queue = world.commoner_pregnancy_queue_by_region.setdefault(region_id, [0 for _ in range(COMMONER_PREGNANCY_MONTHS)])
        while len(queue) < COMMONER_PREGNANCY_MONTHS:
            queue.append(0)
        births = max(0, int(queue.pop(0)))
        queue.append(0)
        world.commoner_births_due = getattr(world, 'commoner_births_due', 0) + births
        fertile_females = max(0, int(world.commoner_fertile_females_by_region.get(region_id, 0)))
        eligible_females = max(0, fertile_females - sum(queue))
        pregnancy_rate = COMMONER_MONTHLY_PREGNANCY_RATE
        if region.order >= 60:
            pregnancy_rate += 0.002
        if region.control >= 20:
            pregnancy_rate += 0.001
        if region.order <= 35:
            pregnancy_rate *= 0.65
        if region.order < 20:
            pregnancy_rate *= 0.45
        if region.control <= -20:
            pregnancy_rate *= 0.60
        if monster_threat > 0:
            pregnancy_rate *= max(0.20, 1.0 - min(0.70, monster_threat * 0.05))
        if pressure > 0.75:
            pregnancy_rate *= max(0.05, 1.0 - ((pressure - 0.75) * 1.25))
        pregnancy_rate = max(0.0, min(0.018, pregnancy_rate))
        new_pregnancies = min(eligible_females, self._stochastic_round(eligible_females * pregnancy_rate))
        queue[-1] += new_pregnancies
        world.commoner_pregnancies_started = getattr(world, 'commoner_pregnancies_started', 0) + new_pregnancies
        base_death_rate = 0.00022 + region.danger * 0.00015
        death_rate = base_death_rate * HARDSHIP_DEATH_RATE_MULTIPLIER
        if region.order <= 35:
            death_rate += 0.00015
        if region.order < 20:
            death_rate += 0.00020
        if region.control <= -20:
            death_rate += 0.00010
        death_rate += evil_adventurers * 0.000015
        death_rate += monster_threat * 0.000070
        death_rate -= good_adventurers * 0.000020
        if pressure > 1.0:
            death_rate += min(0.02, (pressure - 1.0) * 0.01)
        death_rate = max(0.00005, min(0.008, death_rate))
        deaths = min(count + births, self._stochastic_round(count * death_rate))
        migrants = 0
        overcrowded = pressure > 1.0
        threatened = evil_adventurers > good_adventurers or monster_threat > 0 or region.control <= -20
        if region.neighbors and (threatened or overcrowded):
            migrate_rate = 0.001 + evil_adventurers * 0.0002 + monster_threat * 0.0005
            if region.control <= -20:
                migrate_rate += 0.001
            if overcrowded:
                migrate_rate += min(0.03, (pressure - 1.0) * 0.01)
            migrants = min(count + births - deaths, self._stochastic_round(count * migrate_rate))
            migrants = min(migrants, int(count * 0.03))
            if migrants > 0:
                current_score = safety_scores[region_id]
                better_neighbors = []
                for nid in region.neighbors:
                    neighbor = world.regions[nid]
                    neighbor_pressure = world.commoners_by_region.get(nid, 0) / max(1, self._effective_region_capacity(neighbor))
                    if safety_scores[nid] > current_score and neighbor_pressure < pressure:
                        better_neighbors.append(nid)
                if better_neighbors:
                    top_score = max(safety_scores[nid] for nid in better_neighbors)
                    destinations = [nid for nid in better_neighbors if safety_scores[nid] == top_score]
                    for _ in range(migrants):
                        dest = self.rng.choice(destinations)
                        world.commoners_by_region[dest] += 1
                        self._shift_commoner_faith(region_id, dest, 1)
                        self._shift_commoner_demographics(region_id, dest, 1)
                else:
                    migrants = 0
        world.commoners_by_region[region_id] = max(0, count + births - deaths - migrants)
        self._add_commoner_demographic_births(region_id, births)
        self._remove_commoner_demographics(region_id, deaths)
        self._add_commoner_births(region_id, births)
        self._remove_commoner_deaths(region_id, deaths, cause="hardship / regional mortality")
        world.generated_by_role[Role.COMMONER] += births
        world.commoner_births += births
        self._sync_commoner_demographics(region_id)
        if births >= 3 and self.rng.random() < 0.10:
            world.log(f"{births} children are born among the common folk of {world.region_name(region_id)}.", importance=1, category="birth")
        if deaths >= 3 and self.rng.random() < 0.12:
            world.log(f"{deaths} commoners perish in {world.region_name(region_id)} from hunger, fear, and hard living.", importance=1, category="hardship")
    # Promotion pressure remains part of the monthly population tally.
    if True:
        state = self._recovery_state() if hasattr(self, '_recovery_state') else 'normal'
        for region_id in world.regions:
            count = world.commoners_by_region.get(region_id, 0)
            if count <= 0:
                continue
            pressure = max(0.0, 0.0004 * count)
            region = world.regions[region_id]
            if region.order >= 60:
                pressure += 0.10
            if region.control <= -20:
                pressure += 0.12
            if state == 'low':
                pressure += 0.18
            elif state == 'crisis':
                pressure += 0.35
            promotions = 0
            if self.rng.random() < min(0.95, pressure):
                promotions = 1
                if count >= 800 and self.rng.random() < (0.20 if state == 'normal' else 0.45):
                    promotions += 1
                if state == 'crisis' and count >= 300 and self.rng.random() < 0.35:
                    promotions += 1
            for _ in range(promotions):
                if world.commoners_by_region.get(region_id, 0) <= 0:
                    break
                self._spawn_adventurer_from_commoners(region_id)

def _commoner_turn(self, actor: Actor) -> None:
    return

def _handle_adventurer_births_aggregate(self) -> None:
    world = self.world
    for female in list(world.living_actors()):
        if not female.is_adventurer() or getattr(female, "sex", None) != "F":
            continue
        due_tick = getattr(female, "pregnant_until_tick", -1)
        if due_tick < 0 or world.tick < due_tick:
            continue
        father_id = getattr(female, "pregnancy_partner_id", None) or getattr(female, "spouse_id", None)
        father = world.actors.get(father_id)
        if father is not None:
            child = legacy_module.LegacyMixin._create_adventurer_child(self, female, father)
            female.last_birth_tick = world.tick
            if hasattr(father, "last_birth_tick"):
                father.last_birth_tick = world.tick
            world.log(f"A child is born to {female.short_name()} and {father.short_name()} in {world.region_name(child.region_id)}.", importance=2, category="legacy_birth")
        female.pregnant_until_tick = -1
        female.pregnancy_partner_id = None
    if not (hasattr(self, '_monthly_schedule') and self._monthly_schedule(1, 'Evening')):
        return
    for actor in list(world.living_actors()):
        if not actor.is_adventurer() or actor.spouse_id is None:
            continue
        spouse = world.actors.get(actor.spouse_id)
        if spouse is None or not spouse.alive or not spouse.is_adventurer():
            continue
        if actor.id > spouse.id or actor.sex == spouse.sex:
            continue
        if not legacy_module.LegacyMixin._can_form_legacy_pair(self, actor, spouse):
            continue
        female = actor if getattr(actor, "sex", "F") == "F" else spouse
        male = spouse if female is actor else actor
        female_age = self._calculate_age(female)
        male_age = self._calculate_age(male)
        if female_age < 15 or female_age > 39 or male_age < 15 or male_age > 60:
            continue
        if getattr(female, "pregnant_until_tick", -1) > world.tick:
            continue
        last_birth_tick = max(getattr(female, 'last_birth_tick', -999999), getattr(male, 'last_birth_tick', -999999))
        if world.tick - last_birth_tick < PREGNANCY_DURATION_TICKS:
            continue
        children = legacy_module.LegacyMixin._living_children_of_pair(self, female, male)
        chance = COMMONER_MONTHLY_PREGNANCY_RATE
        region = world.regions[female.region_id]
        if region.order >= 60:
            chance += 0.002
        if region.control >= 20:
            chance += 0.001
        if region.order <= 35:
            chance *= 0.65
        if region.control <= -20:
            chance *= 0.60
        if children >= legacy_module.LegacyMixin.MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR:
            chance *= 0.35
        if children >= legacy_module.LegacyMixin.MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR + 1:
            chance *= 0.10
        if children >= legacy_module.LegacyMixin.MAX_SOFT_CHILDREN_PER_ADVENTURER_PAIR + 2:
            chance = 0.0
        chance = max(0.0002, min(0.018, chance))
        if self.rng.random() < chance:
            female.pregnant_until_tick = world.tick + PREGNANCY_DURATION_TICKS
            female.pregnancy_partner_id = male.id

def _legacy_tick(self) -> None:
    self._cleanup_adventurer_spouses()
    self._handle_adventurer_pairing()
    self._handle_adventurer_births_aggregate()
    self._update_ruling_houses()

def _print_summary_extra(sim, years=None) -> None:
    world = sim.world
    total_commoners = sum(getattr(world, 'commoners_by_region', {}).values())
    true_living_population = len(world.living_actors()) + total_commoners
    print()
    print("AGGREGATE CIVILIAN MODEL")
    print("-" * 72)
    print("Commoners are modeled as regional counts, not individual actors.")
    print(f"Living aggregated commoners: {total_commoners}")
    print(f"True living population estimate: {true_living_population}")
    print("Commoners by region:")
    for region_id, count in world.commoners_by_region.items():
        print(f"  {world.region_name(region_id):14} {count}")

Simulator._generate_population = _generate_population
Simulator._stochastic_round = _stochastic_round
Simulator._initialize_commoner_demographics = _initialize_commoner_demographics
Simulator._sync_commoner_demographics = _sync_commoner_demographics
Simulator._age_commoner_demographics_monthly = _age_commoner_demographics_monthly
Simulator._add_commoner_demographic_births = _add_commoner_demographic_births
Simulator._remove_commoner_demographics = _remove_commoner_demographics
Simulator._shift_commoner_demographics = _shift_commoner_demographics

def _commoner_birth_deity(self, region_id: int, world=None) -> Deity:
    world = world if world is not None else getattr(self, "world", None)
    if world is not None:
        faith = getattr(world, "commoner_faith_by_region", {}).get(region_id, {})
        region = world.regions.get(region_id)
        favored = None
        if region is not None:
            polity_id = getattr(region, "polity_id", None)
            if polity_id is not None and polity_id in world.polities:
                ruler = world.actors.get(world.polities[polity_id].ruler_id)
                if ruler is not None and ruler.alive:
                    favored = ruler.deity
            if favored is None and getattr(region, "ruler_id", None) is not None:
                ruler = world.actors.get(region.ruler_id)
                if ruler is not None and ruler.alive:
                    favored = ruler.deity
        if faith and sum(faith.values()) > 0 and self.rng.random() < 0.75:
            if favored is not None and favored in faith and self.rng.random() < 0.65:
                return favored
            return max(self._pantheon_deities(world), key=lambda d: faith.get(d, 0) + self.rng.random() * 0.25)

    alignment = self.rng.choice(list(Alignment))
    return self._weighted_random_deity(alignment, region_id=region_id)

def _apply_religious_conversion(self) -> None:
    world = self.world
    if not hasattr(world, "commoner_faith_by_region"):
        world.commoner_faith_by_region = {rid: self._empty_faith_map(world) for rid in world.regions}
    if not hasattr(world, "last_religious_conversion_tick_by_region"):
        world.last_religious_conversion_tick_by_region = {rid: -999999 for rid in world.regions}

    for region_id, region in world.regions.items():
        faith = world.commoner_faith_by_region.setdefault(region_id, self._empty_faith_map(world))
        total_commoners = world.commoners_by_region.get(region_id, 0)
        favored = self._region_favored_deity(region_id)
        last_tick = world.last_religious_conversion_tick_by_region.get(region_id, -999999)
        conversion_ready = (world.tick - last_tick) >= RELIGIOUS_CONVERSION_REGION_COOLDOWN_TICKS

        hero_bias = {}
        # Fetch actors once and reuse throughout this region's processing.
        local_actors = list(world.actors_in_region(region_id))
        local_adventurers = [a for a in local_actors if a.alive and a.is_adventurer()]
        for actor in local_adventurers:
            hero_bias[actor.deity] = hero_bias.get(actor.deity, 0) + max(0, actor.reputation)

        moved_any = False
        if conversion_ready and favored is not None and total_commoners > 0:
            converts = max(0, int(total_commoners * RELIGIOUS_FAVORED_CONVERSION_RATE))
            if converts > 0:
                sources = [d for d in self._pantheon_deities(world) if d != favored]
                pool = sum(faith.get(d, 0) for d in sources)
                if pool > 0:
                    moved = min(converts, pool)
                    assigned = 0
                    for i, deity in enumerate(sources):
                        available = faith.get(deity, 0)
                        if i == len(sources) - 1:
                            loss = min(available, moved - assigned)
                        else:
                            loss = min(available, int(moved * (available / pool)))
                            assigned += loss
                        faith[deity] = max(0, available - loss)
                    faith[favored] = faith.get(favored, 0) + moved
                    moved_any = moved_any or moved > 0

        if conversion_ready and hero_bias and total_commoners > 0:
            dominant = max(hero_bias, key=lambda d: hero_bias[d])
            converts = max(0, int(total_commoners * RELIGIOUS_HERO_CONVERSION_RATE))
            if converts > 0:
                sources = [d for d in self._pantheon_deities(world) if d != dominant]
                pool = sum(faith.get(d, 0) for d in sources)
                if pool > 0:
                    moved = min(converts, pool)
                    assigned = 0
                    for i, deity in enumerate(sources):
                        available = faith.get(deity, 0)
                        if i == len(sources) - 1:
                            loss = min(available, moved - assigned)
                        else:
                            loss = min(available, int(moved * (available / pool)))
                            assigned += loss
                        faith[deity] = max(0, available - loss)
                    faith[dominant] = faith.get(dominant, 0) + moved
                    moved_any = moved_any or moved > 0
                    champion_candidates = [a for a in local_adventurers if getattr(a, 'champion_of', None) == dominant]
                    if champion_candidates:
                        champion = max(champion_candidates, key=lambda a: (a.deity_conviction, a.reputation, a.power_rating()))
                        champion.converted_followers = getattr(champion, 'converted_followers', 0) + moved
                        rep_steps = champion.converted_followers // 100
                        new_steps = rep_steps - getattr(champion, 'champion_rep_steps', 0)
                        if new_steps > 0:
                            champion.reputation += new_steps
                            champion.champion_rep_steps = rep_steps

        if conversion_ready and total_commoners > 0:
            hope_rate = 0.0
            if region.control <= -40:
                hope_rate += 0.0008
            if region.control <= -70:
                hope_rate += 0.0012
            if region.order <= 20:
                hope_rate += 0.0006
            if region.order <= 5:
                hope_rate += 0.0004
            if hope_rate > 0.0:
                light = Deity.LORD_OF_LIGHT
                sources = [d for d in self._pantheon_deities(world) if d != light]
                pool = sum(faith.get(d, 0) for d in sources)
                if pool > 0:
                    hope_converts = max(1, int(total_commoners * hope_rate))
                    moved = min(hope_converts, pool)
                    assigned = 0
                    for i, deity in enumerate(sources):
                        available = faith.get(deity, 0)
                        if i == len(sources) - 1:
                            loss = min(available, moved - assigned)
                        else:
                            loss = min(available, int(moved * (available / pool)))
                            assigned += loss
                        faith[deity] = max(0, available - loss)
                    faith[light] = faith.get(light, 0) + moved
                    moved_any = moved_any or moved > 0

        if moved_any:
            world.last_religious_conversion_tick_by_region[region_id] = world.tick

        if local_adventurers:
            dominant_local = max(self._pantheon_deities(world), key=lambda d: faith.get(d, 0))
            for actor in local_adventurers:
                if getattr(actor, "locked_deity", False):
                    actor.deity_conviction = 100
                    continue
                if actor.deity == dominant_local:
                    actor.deity_conviction = min(100, actor.deity_conviction + 1)
                    continue
                last_personal = getattr(actor, 'last_deity_conversion_tick', -999999)
                if world.tick - last_personal < ADVENTURER_DEITY_CONVERSION_COOLDOWN_TICKS:
                    actor.deity_conviction = min(100, actor.deity_conviction + 1)
                    continue
                chance = 0.0
                if favored is not None and actor.deity != favored:
                    chance += 0.08
                if dominant_local != actor.deity:
                    chance += 0.04
                chance += min(0.12, hero_bias.get(dominant_local, 0) / 1200.0)
                chance -= max(0, actor.deity_conviction - 50) / 250.0
                if self.rng.random() < max(0.0, min(0.25, chance)):
                    change_actor_deity(self, actor, dominant_local)
                    actor.deity_conviction = max(10, actor.deity_conviction - 5)
                    actor.last_deity_conversion_tick = world.tick
                else:
                    actor.deity_conviction = min(100, actor.deity_conviction + 1)


Simulator._pantheon_deities = _pantheon_deities
Simulator._empty_faith_map = _empty_faith_map
Simulator._resolve_deity_name = _resolve_deity_name
Simulator._alignment_distance = _alignment_distance
Simulator._weighted_random_deity = _weighted_random_deity
Simulator._build_world = _build_world
Simulator._retirement_check = _retirement_check
Simulator._actor_lifecycle_tick = _actor_lifecycle_tick
Simulator._population_tick = _population_tick
Simulator._commoner_turn = _commoner_turn
Simulator._legacy_tick = _legacy_tick
Simulator._allocate_actor_id = _allocate_actor_id
Simulator._spawn_adventurer_from_commoners = _spawn_adventurer_from_commoners
Simulator._handle_adventurer_births_aggregate = _handle_adventurer_births_aggregate
Simulator._region_favored_deity = _region_favored_deity
Simulator._commoner_birth_deity = _commoner_birth_deity
Simulator._bulk_apply_faith_addition = _bulk_apply_faith_addition
Simulator._bulk_apply_faith_loss = _bulk_apply_faith_loss
Simulator._apply_religious_conversion = _apply_religious_conversion
Simulator._add_commoner_births = _add_commoner_births
Simulator._commoner_death_cause_from_context = _commoner_death_cause_from_context
Simulator._record_commoner_deaths = _record_commoner_deaths
Simulator._remove_commoner_deaths = _remove_commoner_deaths
Simulator._shift_commoner_faith = _shift_commoner_faith



def _parse_years_or_indef(raw: str):
    text = str(raw).strip().lower()
    if text in {"indef", "infinite", "infinity", "forever"}:
        return "indef"
    try:
        years = int(text)
    except Exception as exc:
        raise argparse.ArgumentTypeError("Years must be a positive integer or 'indef'.") from exc
    if years <= 0:
        raise argparse.ArgumentTypeError("Years must be greater than 0, or use 'indef'.")
    return years




def _headless_autosave_path(simulator) -> Path:
    """Rolling headless autosave path. Overwrites the same seed-specific .fics file."""
    world = getattr(simulator, "world", None)
    seed = str(getattr(world, "seed_used", "seed"))
    safe_seed = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in seed)
    safe_seed = safe_seed.strip("._") or "seed"
    save_dir = Path(__file__).resolve().parent / "autosave"
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir / f"{safe_seed}_autosave.fics"


def _maybe_headless_autosave(simulator, autosave_years: int, last_autosave_year: int = 0) -> int:
    """Autosave every N simulated years. Returns the latest autosaved year marker."""
    autosave_years = max(0, int(autosave_years or 0))
    if autosave_years <= 0:
        return last_autosave_year
    world = getattr(simulator, "world", None)
    if world is None:
        return last_autosave_year
    current_year = int(getattr(world, "tick", 0) // TICKS_PER_YEAR)
    if current_year <= 0:
        return last_autosave_year
    if current_year == last_autosave_year:
        return last_autosave_year
    if current_year % autosave_years != 0:
        return last_autosave_year
    try:
        path = _headless_autosave_path(simulator)
        simulator.save_state(path)
        print(f"[autosave] Year {current_year}: {path}")
        return current_year
    except Exception as exc:
        print(f"[autosave failed] Year {current_year}: {exc}")
        return last_autosave_year

def _run_indefinitely(simulator, periodic_summary_years: int = 0, autosave_years: int = 0) -> None:
    periodic_summary_years = max(0, int(periodic_summary_years))
    autosave_years = max(0, int(autosave_years or 0))
    summary_every_ticks = periodic_summary_years * TICKS_PER_YEAR if periodic_summary_years > 0 else 0
    run_start = time.perf_counter()
    last_autosave_year = int(getattr(simulator.world, "_last_headless_autosave_year", 0) or 0)

    while True:
        simulator.step()

        if summary_every_ticks > 0 and simulator.world.tick % summary_every_ticks == 0:
            elapsed_years = simulator.world.tick // TICKS_PER_YEAR
            simulator.world.runtime_seconds = time.perf_counter() - run_start
            simulator._flush_historian() if hasattr(simulator, "_flush_historian") else None
            summary.write_summary(simulator, elapsed_years)

        if autosave_years > 0 and simulator.world.tick % TICKS_PER_YEAR == 0:
            last_autosave_year = _maybe_headless_autosave(simulator, autosave_years, last_autosave_year)
            simulator.world._last_headless_autosave_year = last_autosave_year

        if simulator.verbose:
            simulator._print_new_events()
            if simulator.verbose_delay > 0:
                time.sleep(simulator.verbose_delay)

Simulator._pick_alignment_for_role = _pick_alignment_for_role



def _holy_war_available_targets(self):
    self._refresh_god_state_if_due(force=True)
    god = self._player_god()
    if god is None:
        return []
    attacker = self.world.god_state.get(god)
    if attacker is None:
        return []
    if getattr(self.world, "last_holy_war_tick", -999999) + HOLY_WAR_COOLDOWN_YEARS * TICKS_PER_YEAR > self.world.tick:
        return []
    if attacker.influence_share < HOLY_WAR_MIN_ATTACKER_INFLUENCE:
        return []
    if int(getattr(attacker, "souls", 0)) < HOLY_WAR_SOUL_COST:
        return []
    targets = []
    dead = getattr(self.world, "dead_gods", set())
    for deity, state in self.world.god_state.items():
        if deity == god or deity in dead:
            continue
        if getattr(state, "influence_share", 0.0) > 0:
            targets.append((deity, state))
    # Holy Wars are meant to let the player punch upward, so show stronger faiths first.
    targets.sort(key=lambda item: item[1].influence_share, reverse=True)
    return targets

def _holy_war_status(self):
    self._refresh_god_state_if_due(force=True)
    god = self._player_god()
    state = self.world.god_state.get(god) if god is not None else None
    cooldown_until = getattr(self.world, "last_holy_war_tick", -999999) + HOLY_WAR_COOLDOWN_YEARS * TICKS_PER_YEAR
    cooldown_left = max(0, cooldown_until - self.world.tick)
    targets = self._holy_war_available_targets()
    return {
        "player_god": god,
        "player_share": getattr(state, "influence_share", 0.0) if state else 0.0,
        "soul_cost": HOLY_WAR_SOUL_COST,
        "cooldown_ticks": cooldown_left,
        "targets": targets,
    }



def _holy_war_targets_for_god(self, god):
    self._refresh_god_state_if_due(force=True)
    if god is None:
        return []
    attacker = self.world.god_state.get(god)
    if attacker is None:
        return []
    if getattr(self.world, "dead_gods", None) is None:
        self.world.dead_gods = set()
    if attacker.influence_share < HOLY_WAR_MIN_ATTACKER_INFLUENCE:
        return []
    if int(getattr(attacker, "souls", 0)) < HOLY_WAR_SOUL_COST:
        return []
    targets = []
    for deity, state in self.world.god_state.items():
        if deity == god or deity in self.world.dead_gods:
            continue
        if hasattr(self, "_god_has_immortal_grace") and self._god_has_immortal_grace(deity):
            continue
        if getattr(state, "influence_share", 0.0) > 0:
            targets.append((deity, state))
    targets.sort(key=lambda item: item[1].influence_share, reverse=True)
    return targets


def _launch_holy_war_as_god(self, attacking_god, target_deity=None):
    world = self.world
    god = attacking_god
    if god is None:
        return False, "No attacking god."
    self._refresh_god_state_if_due(force=True)
    attacker = world.god_state.get(god)
    if attacker is None:
        return False, "No attacking god state."
    if getattr(world, "dead_gods", None) is None:
        world.dead_gods = set()
    # Player and AI have separate global cooldowns; this method enforces the AI/general one.
    cooldown = int(globals().get("AI_HOLY_WAR_COOLDOWN_TICKS", HOLY_WAR_COOLDOWN_YEARS * TICKS_PER_YEAR))
    if world.tick < getattr(world, "last_ai_holy_war_tick", -999999) + cooldown:
        return False, "Holy War is still on AI cooldown."
    if attacker.influence_share < float(globals().get("AI_HOLY_WAR_MIN_ATTACKER_INFLUENCE", HOLY_WAR_MIN_ATTACKER_INFLUENCE)):
        return False, f"Influence too low for Holy War ({attacker.influence_share:.1f}%)."
    if attacker.souls < HOLY_WAR_SOUL_COST:
        return False, f"Need {HOLY_WAR_SOUL_COST} souls."
    targets = self._holy_war_targets_for_god(god)
    if not targets:
        return False, "No rival faith is available to challenge."
    if target_deity is None:
        target_deity, target_state = targets[0]
    else:
        matched = [(d, s) for d, s in targets if d == target_deity]
        if not matched:
            return False, "Selected god cannot currently be targeted."
        target_deity, target_state = matched[0]

    world.souls_by_deity[god] = max(0, int(world.souls_by_deity.get(god, 0)) - HOLY_WAR_SOUL_COST)
    world.last_ai_holy_war_tick = world.tick

    ratio = max(0.25, attacker.influence_share / max(0.1, target_state.influence_share))
    success_chance = min(0.90, max(0.15, 0.25 + ratio * 0.12))
    success = self.rng.random() < success_chance

    target_name = self._deity_display_name(target_deity)
    attacker_name = self._deity_display_name(god)

    actor_followers = self._living_actor_followers(target_deity)
    self.rng.shuffle(actor_followers)
    kill_rate = min(HOLY_WAR_MAX_FOLLOWER_LOSS_RATE, 0.08 + ratio * (0.08 if success else 0.035))
    killed = 0
    converted = 0
    for actor in actor_followers:
        roll = self.rng.random()
        if roll < kill_rate * 0.35:
            self._mark_actor_dead(actor, f"holy war between {attacker_name} and {target_name}", importance=3)
            killed += 1
        elif roll < kill_rate:
            change_actor_deity(self, actor, god, locked=False)
            converted += 1

    commoner_losses = 0
    commoner_converts = 0
    for rid, faith in getattr(world, "commoner_faith_by_region", {}).items():
        followers = int(faith.get(target_deity, 0))
        if followers <= 0:
            continue
        loss = min(followers, int(round(followers * kill_rate * (0.45 if success else 0.20))))
        convert = min(followers - loss, int(round(followers * kill_rate * (0.65 if success else 0.20))))
        faith[target_deity] = max(0, followers - loss - convert)
        faith[god] = faith.get(god, 0) + convert
        if loss > 0:
            world.commoners_by_region[rid] = max(0, int(world.commoners_by_region.get(rid, 0)) - loss)
            if hasattr(self, "_remove_commoner_demographics"):
                self._remove_commoner_demographics(rid, loss)
            self._remove_commoner_deaths(rid, loss, cause=f"holy war: {target_name}")
            world.adjust_region_state(rid, control_delta=3 if success else -2, order_delta=-3)
        commoner_losses += loss
        commoner_converts += convert

    if success:
        msg = (
            f"{attacker_name} launches a Holy War against {target_name}, "
            f"breaking {killed + commoner_losses} followers "
            f"({killed} adventurers, {commoner_losses} commoners) and converting "
            f"{converted + commoner_converts} ({converted} adventurers, {commoner_converts} commoners)."
        )
        world.log(msg, importance=4, category="holy_war")
        self._refresh_god_state_if_due(force=True)
        target_after = world.god_state.get(target_deity)
        god_death_msg = ""
        if target_after is not None and target_after.influence_share <= HOLY_WAR_GOD_KILL_TARGET_THRESHOLD:
            world.dead_gods.add(target_deity)
            world.gods = [d for d in world.gods if d != target_deity]
            god_death_msg = f" {target_name} falls silent; their remaining cults scatter into rumor and ash."
            world.log(god_death_msg.strip(), importance=5, category="god_death")
        self._refresh_god_state_if_due(force=True)
        return True, msg + god_death_msg
    else:
        backlash = max(10, int(HOLY_WAR_SOUL_COST * 0.25))
        world.souls_by_deity[god] = max(0, int(world.souls_by_deity.get(god, 0)) - backlash)
        msg = (
            f"{attacker_name}'s Holy War against {target_name} falters. "
            f"The attempt still kills {killed + commoner_losses} and converts {converted + commoner_converts}, "
            f"but backlash burns another {backlash} souls."
        )
        world.log(msg, importance=4, category="holy_war")
        self._refresh_god_state_if_due(force=True)
        return False, msg

def _launch_holy_war(self, target_deity=None):
    world = self.world
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    self._refresh_god_state_if_due(force=True)
    attacker = world.god_state.get(god)
    if attacker is None:
        return False, "No player god state."
    if getattr(world, "dead_gods", None) is None:
        world.dead_gods = set()
    if world.tick < getattr(world, "last_holy_war_tick", -999999) + HOLY_WAR_COOLDOWN_YEARS * TICKS_PER_YEAR:
        return False, "Holy War is still on cooldown."
    if attacker.influence_share < HOLY_WAR_MIN_ATTACKER_INFLUENCE:
        return False, f"Influence too low for Holy War ({attacker.influence_share:.1f}%)."
    if attacker.souls < HOLY_WAR_SOUL_COST:
        return False, f"Need {HOLY_WAR_SOUL_COST} souls."
    targets = self._holy_war_available_targets()
    if not targets:
        return False, "No rival faith is available to challenge."
    if target_deity is None:
        target_deity, target_state = targets[0]
    else:
        matched = [(d, s) for d, s in targets if d == target_deity]
        if not matched:
            return False, "Selected god cannot currently be targeted."
        target_deity, target_state = matched[0]

    world.souls_by_deity[god] = max(0, int(world.souls_by_deity.get(god, 0)) - HOLY_WAR_SOUL_COST)
    world.last_holy_war_tick = world.tick

    ratio = max(0.25, attacker.influence_share / max(0.1, target_state.influence_share))
    success_chance = min(0.90, max(0.15, 0.25 + ratio * 0.12))
    success = self.rng.random() < success_chance

    target_name = self._deity_display_name(target_deity)
    attacker_name = self._deity_display_name(god)

    actor_followers = self._living_actor_followers(target_deity)
    self.rng.shuffle(actor_followers)
    kill_rate = min(HOLY_WAR_MAX_FOLLOWER_LOSS_RATE, 0.08 + ratio * (0.08 if success else 0.035))
    killed = 0
    converted = 0
    for actor in actor_followers:
        roll = self.rng.random()
        if roll < kill_rate * 0.35:
            self._mark_actor_dead(actor, f"holy war between {attacker_name} and {target_name}", importance=3)
            killed += 1
        elif roll < kill_rate:
            change_actor_deity(self, actor, god, locked=False)
            converted += 1

    commoner_losses = 0
    commoner_converts = 0
    for rid, faith in getattr(world, "commoner_faith_by_region", {}).items():
        followers = int(faith.get(target_deity, 0))
        if followers <= 0:
            continue
        loss = min(followers, int(round(followers * kill_rate * (0.45 if success else 0.20))))
        convert = min(followers - loss, int(round(followers * kill_rate * (0.65 if success else 0.20))))
        faith[target_deity] = max(0, followers - loss - convert)
        faith[god] = faith.get(god, 0) + convert
        if loss > 0:
            world.commoners_by_region[rid] = max(0, int(world.commoners_by_region.get(rid, 0)) - loss)
            if hasattr(self, "_remove_commoner_demographics"):
                self._remove_commoner_demographics(rid, loss)
            self._remove_commoner_deaths(rid, loss, cause=f"holy war: {target_name}")
            world.adjust_region_state(rid, control_delta=3 if success else -2, order_delta=-3)
        commoner_losses += loss
        commoner_converts += convert

    if success:
        msg = (
            f"{attacker_name} launches a Holy War against {target_name}, "
            f"breaking {killed + commoner_losses} followers "
            f"({killed} adventurers, {commoner_losses} commoners) and converting "
            f"{converted + commoner_converts} ({converted} adventurers, {commoner_converts} commoners)."
        )
        world.log(msg, importance=4, category="holy_war")
        # If the target is reduced to nearly nothing, mark them dead/silenced.
        self._refresh_god_state_if_due(force=True)
        target_after = world.god_state.get(target_deity)
        god_death_msg = ""
        if target_after is not None and target_after.influence_share <= HOLY_WAR_GOD_KILL_TARGET_THRESHOLD:
            world.dead_gods.add(target_deity)
            world.gods = [d for d in world.gods if d != target_deity]
            god_death_msg = f" {target_name} falls silent; their remaining cults scatter into rumor and ash."
            world.log(god_death_msg.strip(), importance=5, category="god_death")
        self._refresh_god_state_if_due(force=True)
        return True, msg + god_death_msg
    else:
        backlash = max(10, int(HOLY_WAR_SOUL_COST * 0.25))
        world.souls_by_deity[god] = max(0, int(world.souls_by_deity.get(god, 0)) - backlash)
        msg = (
            f"{attacker_name}'s Holy War against {target_name} falters. "
            f"The attempt still kills {killed + commoner_losses} and converts {converted + commoner_converts}, "
            f"but backlash burns another {backlash} souls."
        )
        world.log(msg, importance=4, category="holy_war")
        self._refresh_god_state_if_due(force=True)
        return False, msg


def _update_god_state(self):
    world = self.world
    gods = [g for g in list(getattr(world, "gods", self._pantheon_deities(world))) if g not in getattr(world, "dead_gods", set())]
    profiles = getattr(world, "god_profiles", {})
    faith_by_region = getattr(world, "commoner_faith_by_region", {})
    soul_weight = 2

    monster_support = {}
    if hasattr(self, "_monster_deity_contributions"):
        try:
            monster_support = self._monster_deity_contributions()
        except Exception:
            monster_support = {}

    states = {}
    total_influence = 0
    living = list(world.living_actors())

    # One pass over living actors instead of scanning the full actor list once
    # for followers and again for champions for every deity.
    living_followers_by_deity = {deity: 0 for deity in gods}
    champions_by_deity = {deity: [] for deity in gods}
    for actor in living:
        actor_deity = getattr(actor, "deity", None)
        if actor_deity in living_followers_by_deity:
            living_followers_by_deity[actor_deity] += 1
        champion_of = getattr(actor, "champion_of", None)
        if champion_of in champions_by_deity:
            champions_by_deity[champion_of].append(actor.id)

    # Build a relic-by-deity index in a single pass instead of O(deities * relics).
    relics_by_deity = {deity: [] for deity in gods}
    for relic_id, relic in getattr(world, "relics", {}).items():
        for attr in ("deity", "attuned_deity", "creator_deity"):
            d = getattr(relic, attr, None)
            if d in relics_by_deity:
                if relic_id not in relics_by_deity[d]:
                    relics_by_deity[d].append(relic_id)
                break

    # Build regional commoner totals in a single pass.
    commoners_by_deity = {deity: 0 for deity in gods}
    for region_faith in faith_by_region.values():
        for deity, count in region_faith.items():
            if deity in commoners_by_deity:
                commoners_by_deity[deity] += int(count or 0)

    for deity in gods:
        profile = profiles.get(deity)
        name = deity_value(deity)
        regional = {rid: int(region_faith.get(deity, 0)) for rid, region_faith in faith_by_region.items()}
        living_followers = living_followers_by_deity.get(deity, 0)
        commoner_followers = commoners_by_deity.get(deity, 0)
        followers = commoner_followers + living_followers
        souls = int(getattr(world, "souls_by_deity", {}).get(deity, getattr(profile, "starting_souls", 0)))
        champions = champions_by_deity.get(deity, [])
        relics = relics_by_deity.get(deity, [])
        influence = followers + (souls * soul_weight) + int(monster_support.get(deity, 0)) + len(champions) * 25 + len(relics) * 10
        total_influence += influence
        states[deity] = GodState(
            deity=deity,
            name=name,
            profile=profile,
            is_player_god=bool(getattr(profile, "is_player", False) or getattr(profile, "is_player_god", False)),
            color=(getattr(profile, "color", "") or ("magenta" if getattr(profile, "is_player", False) else "")),
            souls=souls,
            followers=followers,
            champions=champions,
            relics=relics,
            regional_influence=regional,
            influence=influence,
            influence_share=0.0,
        )
    if total_influence > 0:
        for state in states.values():
            state.influence_share = (state.influence / total_influence) * 100.0
    world.god_state = states
    world.last_god_state_refresh_tick = int(getattr(world, "tick", 0))
    return states



def _deity_key_for_lookup(deity) -> str:
    return deity_value(deity).strip().lower() if deity is not None else ""


def _unique_god_name(self, base_name: str) -> str:
    base = str(base_name or "Revealed God").strip() or "Revealed God"
    existing = {_deity_key_for_lookup(g) for g in list(getattr(self.world, "gods", [])) + list(getattr(self, "pantheon", []))}
    if base.lower() not in existing:
        return base
    n = 2
    while f"{base} {n}".lower() in existing:
        n += 1
    return f"{base} {n}"


def _ensure_injection_state(self) -> None:
    world = self.world
    if not hasattr(world, "school_locked_deities") or getattr(world, "school_locked_deities", None) is None:
        world.school_locked_deities = set()
    if not hasattr(world, "school_unlocked_deities") or getattr(world, "school_unlocked_deities", None) is None:
        world.school_unlocked_deities = set()
    if not hasattr(world, "immortal_grace_until_by_deity") or getattr(world, "immortal_grace_until_by_deity", None) is None:
        world.immortal_grace_until_by_deity = {}
    if not hasattr(world, "player_god_origin"):
        world.player_god_origin = ""


def _register_formal_player_god(self, profile: GodProfile, *, origin: str = "revelation", starting_souls=None, school_unlocked: bool = False, grace_years: int = 0):
    self._ensure_injection_state()
    world = self.world
    # Clear older player flag; only one player-god may be active.
    for old_profile in getattr(world, "god_profiles", {}).values():
        if getattr(old_profile, "is_player", False) or getattr(old_profile, "is_player_god", False):
            old_profile.is_player = False
            if hasattr(old_profile, "is_player_god"):
                old_profile.is_player_god = False
    name = self._unique_god_name(getattr(profile, "name", "Revealed God"))
    profile.name = name
    profile.is_player = True
    profile.active_for_run = True
    if not getattr(profile, "color", None):
        profile.color = "magenta"
    if not getattr(profile, "profile_id", ""):
        profile.profile_id = f"player_{name.lower().replace(' ', '_')}"
    if not getattr(profile, "source_path", ""):
        profile.source_path = f"player_{origin}"
    god = profile
    if god not in getattr(self, "pantheon", []):
        self.pantheon.append(god)
    if not hasattr(world, "gods") or world.gods is None:
        world.gods = []
    if god not in world.gods:
        world.gods.append(god)
    if not hasattr(world, "god_profiles") or world.god_profiles is None:
        world.god_profiles = {}
    world.god_profiles[god] = profile
    for rid, faith in getattr(world, "commoner_faith_by_region", {}).items():
        faith.setdefault(god, 0)
    if not hasattr(world, "souls_by_deity") or world.souls_by_deity is None:
        world.souls_by_deity = {}
    if starting_souls is None:
        starting_souls = getattr(profile, "starting_souls", 0)
    world.souls_by_deity[god] = max(0, int(starting_souls or 0))
    if school_unlocked:
        world.school_unlocked_deities.add(god)
        world.school_locked_deities.discard(god)
    else:
        world.school_locked_deities.add(god)
    if grace_years and grace_years > 0:
        world.immortal_grace_until_by_deity[god] = int(getattr(world, "tick", 0)) + int(grace_years) * TICKS_PER_YEAR
    world.player_god_origin = str(origin or "revelation")
    self._purge_nonformal_school_state()
    self._refresh_god_state_if_due(force=True)
    return god


def _god_immortal_grace_remaining(self, deity) -> int:
    self._ensure_injection_state()
    until = int(getattr(self.world, "immortal_grace_until_by_deity", {}).get(deity, -1) or -1)
    return max(0, until - int(getattr(self.world, "tick", 0)))


def _god_has_immortal_grace(self, deity) -> bool:
    return self._god_immortal_grace_remaining(deity) > 0


def _maybe_unlock_revelation_schools(self, state=None) -> None:
    self._ensure_injection_state()
    world = self.world
    locked = set(getattr(world, "school_locked_deities", set()) or set())
    if not locked:
        return
    if state is None:
        state = getattr(world, "god_state", {}) or {}
    threshold = float(globals().get("PLAYER_REVELATION_SCHOOL_UNLOCK_INFLUENCE", 500.0))
    for deity in list(locked):
        if deity in getattr(world, "school_unlocked_deities", set()):
            continue
        st = state.get(deity) if isinstance(state, dict) else None
        influence = float(getattr(st, "influence", 0.0) or 0.0)
        followers = int(getattr(st, "followers", 0) or 0)
        if influence >= threshold or followers >= int(globals().get("PLAYER_REVELATION_SCHOOL_UNLOCK_FOLLOWERS", 250)):
            world.school_unlocked_deities.add(deity)
            world.school_locked_deities.discard(deity)
            self._ensure_adventurer_schools()
            world.log(f"{self._deity_display_name(deity)} has enough mortal presence to found a public adventurer school.", importance=4, category="immortal_revelation")


def _load_injection_profile(self, imrt_path) -> GodProfile:
    profile = load_imrt_file(Path(imrt_path))
    if profile is None:
        raise ValueError(f"Could not load god profile: {imrt_path}")
    profile.is_player = True
    profile.active_for_run = True
    profile.starting_souls = int(globals().get("PLAYER_REVELATION_STARTING_SOULS", 0))
    return profile


def _inject_story_champion_for_god(self, champ_path, god) -> Optional[Actor]:
    if champ_path is None:
        return None
    path = Path(champ_path)
    actor = self._story_actor_from_file(path, int(getattr(self.world, "next_actor_id", 1)), self.world.regions)
    if actor is None:
        return None
    # Starting champion files are age-relative to Year 1. Rebase them to the loaded world's current year.
    try:
        parsed = _story_parse_sectioned_file(path)
        age = _story_safe_int(parsed.get("build", {}).get("age"), max(16, self._calculate_age(actor)))
        year, _m, _d, _tod, _season = self.world.current_calendar()
        actor.birth_year = int(year) - max(16, int(age))
    except Exception:
        pass
    actor.id = int(getattr(self.world, "next_actor_id", 1))
    self.world.next_actor_id = actor.id + 1
    change_actor_deity(self, actor, god, locked=True)
    actor.champion_of = god
    actor.deity_conviction = 100
    actor.title = getattr(actor, "title", None) or "First Champion"
    actor.invulnerable_until_tick = max(int(getattr(actor, "invulnerable_until_tick", 0) or 0), int(getattr(self.world, "tick", 0)) + max(0, int(globals().get("STARTING_CHAMPION_GRACE_YEARS", 3))) * TICKS_PER_YEAR)
    self.world.actors[actor.id] = actor
    if hasattr(self.world, "register_actor"):
        try:
            self.world.register_actor(actor)
        except Exception:
            self.world.actors[actor.id] = actor
    self._assign_pending_custom_relics(self.world)
    if hasattr(self, "_story_note"):
        self._story_note(actor, f"Revealed as first champion of {self._deity_display_name(god)} in an existing world.")
    return actor


def inject_revealed_player_god(self, imrt_path, champion_path=None):
    profile = self._load_injection_profile(imrt_path)
    god = self._register_formal_player_god(
        profile,
        origin="revelation",
        starting_souls=int(globals().get("PLAYER_REVELATION_STARTING_SOULS", 0)),
        school_unlocked=False,
        grace_years=int(globals().get("PLAYER_REVELATION_GRACE_YEARS", 8)),
    )
    champion = self._inject_story_champion_for_god(champion_path, god) if champion_path else None
    self.world.log(
        f"A new god is revealed: {self._deity_display_name(god)} enters the world under a veil of divine obscurity.",
        importance=5,
        category="immortal_revelation",
    )
    if champion is not None:
        self.world.log(f"{champion.full_name()} bears the first open sign of {self._deity_display_name(god)}.", importance=4, category="champion_created")
    self._refresh_god_state_if_due(force=True)
    return True, f"Revealed {self._deity_display_name(god)}" + (f" with champion {champion.short_name()}." if champion is not None else ".")


def eligible_player_cults(self):
    cults = []
    for cult in getattr(self.world, "proto_cults", {}).values():
        if getattr(cult, "failed", False):
            continue
        if not getattr(cult, "subject_name", ""):
            continue
        pressure = float(getattr(cult, "legend_pressure", 0.0) or 0.0)
        regions = len(getattr(cult, "known_region_ids", set()) or set())
        latent = sum(max(0, int(v)) for v in getattr(cult, "hidden_commoner_affinity_by_region", {}).values())
        if pressure <= 0 and latent <= 0:
            continue
        cults.append(cult)
    cults.sort(key=lambda c: (float(getattr(c, "legend_pressure", 0.0) or 0.0), len(getattr(c, "known_region_ids", set()) or set())), reverse=True)
    return cults


def formalize_proto_cult_as_player_god(self, cult_id):
    self._ensure_lore_state() if hasattr(self, "_ensure_lore_state") else None
    cult = getattr(self.world, "proto_cults", {}).get(int(cult_id))
    if cult is None:
        return False, f"No proto-cult with id {cult_id}."
    mortal_name = getattr(cult, "subject_name", f"Cult {cult_id}")
    name = getattr(cult, "public_title", "") or mortal_name
    actor = self.resolve_actor(getattr(cult, "subject_actor_id", None)) if hasattr(self, "resolve_actor") else None
    alignment = getattr(getattr(actor, "alignment", None), "value", "True Neutral") if actor is not None else "True Neutral"
    domain_weights = getattr(cult, "domain_weights", {}) or {}
    domains = [k for k, _v in sorted(domain_weights.items(), key=lambda item: float(item[1]), reverse=True)][:3]
    if not domains:
        domains = ["knowledge"]
        if actor is not None:
            if getattr(actor, "dragon_kills", 0) or getattr(actor, "monster_kills", 0):
                domains.append("protection")
            if getattr(actor, "kills", 0) > 20:
                domains.append("war")
            if getattr(actor, "role", None) == Role.BARD:
                domains.append("inspiration")
        domains = list(dict.fromkeys(domains))[:3]
    profile = GodProfile(
        name=name,
        alignment=alignment,
        favored_classes=[getattr(getattr(actor, "role", None), "value", "Fighter") if actor is not None else "Fighter"],
        favored_traits=list(getattr(actor, "traits", []) or [])[:3] if actor is not None else [],
        disfavored_traits=[],
        domains=domains,
        description=f"A formal god born from the living memory of {mortal_name}; worshiped as {name}.",
        is_player=True,
        color="magenta",
        starting_souls=0,
        source_path="player_cult_ascension",
        profile_id=f"player_cult_{cult.id}",
        active_for_run=True,
    )
    god = self._register_formal_player_god(
        profile,
        origin="cult_ascension",
        starting_souls=0,
        school_unlocked=bool(globals().get("PLAYER_CULT_ASCENSION_SCHOOL_UNLOCKED", True)),
        grace_years=int(globals().get("PLAYER_CULT_ASCENSION_GRACE_YEARS", 3)),
    )
    cult.ascended = True
    cult.formalized = True
    cult.deity_object = god
    converted_commoners = 0
    for rid, count in list(getattr(cult, "hidden_commoner_affinity_by_region", {}).items()):
        count = max(0, int(count))
        if count <= 0:
            continue
        faith = self.world.commoner_faith_by_region.setdefault(rid, self._empty_faith_map(self.world) if hasattr(self, "_empty_faith_map") else {})
        donor = max([d for d in faith.keys() if d != god], key=lambda d: int(faith.get(d, 0)), default=None)
        take = min(count, int(faith.get(donor, 0))) if donor is not None else 0
        if donor is not None and take > 0:
            faith[donor] = max(0, int(faith.get(donor, 0)) - take)
        faith[god] = int(faith.get(god, 0)) + count
        converted_commoners += count
    converted_actors = 0
    for actor in self.world.living_actors():
        if getattr(actor, "region_id", None) in getattr(cult, "known_region_ids", set()):
            if self.rng.random() < min(0.50, 0.08 + float(getattr(cult, "legend_pressure", 0.0) or 0.0) / 20000.0):
                change_actor_deity(self, actor, god, locked=False)
                clear_actor_protocult_membership(self, actor, getattr(cult, "id", None))
                converted_actors += 1
    self.world.log(
        f"The hidden devotion around {mortal_name} becomes an open faith. {self._deity_display_name(god)} enters immortal play with {converted_commoners} commoner converts and {converted_actors} living adherents.",
        importance=5,
        category="immortal_revelation",
    )
    self._refresh_god_state_if_due(force=True)
    return True, f"Ascended {self._deity_display_name(god)} from {cult.name}."

def _player_god(self):
    world = self.world
    for deity, profile in getattr(world, "god_profiles", {}).items():
        if bool(getattr(profile, "is_player", False) or getattr(profile, "is_player_god", False)):
            return deity
    for deity, state in getattr(world, "god_state", {}).items():
        if bool(getattr(state, "is_player_god", False)):
            return deity
    return None



def _living_follower_share(self, deity):
    self._refresh_god_state_if_due()
    total = 0
    for state in getattr(self.world, "god_state", {}).values():
        total += int(getattr(state, "followers", 0) or 0)
    if total <= 0:
        return 0.0
    state = getattr(self.world, "god_state", {}).get(deity)
    if state is None:
        return 0.0
    return (int(getattr(state, "followers", 0) or 0) / total) * 100.0

def _player_living_follower_share(self):
    god = self._player_god()
    if god is None:
        return None
    return self._living_follower_share(god)

def _player_map_dominance_share(self):
    god = self._player_god()
    if god is None:
        return None
    regions = list(getattr(self.world, "regions", {}).values())
    if not regions:
        return 0.0
    held = 0
    for region in regions:
        faith = getattr(self.world, "commoner_faith_by_region", {}).get(region.id, {})
        if faith:
            top = max(faith, key=lambda d: faith.get(d, 0))
            if top == god and int(faith.get(god, 0)) > 0:
                held += 1
                continue
        ruler = self.world.actors.get(getattr(region, "ruler_id", None))
        if ruler is not None and getattr(ruler, "alive", False) and getattr(ruler, "deity", None) == god:
            held += 1
    return (held / max(1, len(regions))) * 100.0

def _update_player_map_dominance_streak(self):
    share = self._player_map_dominance_share()
    if share is None:
        self.world.player_map_dominance_start_tick = None
        return 0
    if share >= 100.0:
        if getattr(self.world, "player_map_dominance_start_tick", None) is None:
            self.world.player_map_dominance_start_tick = self.world.tick
        return max(0, self.world.tick - int(self.world.player_map_dominance_start_tick))
    self.world.player_map_dominance_start_tick = None
    return 0

def _player_god_state(self):
    god = self._player_god()
    if god is None:
        return None
    self._refresh_god_state_if_due()
    return self.world.god_state.get(god)


def _deity_display_name(self, deity):
    return deity_value(deity) if deity is not None else "None"



def _player_god_profile(self):
    god = self._player_god()
    if god is None:
        return None
    return getattr(self.world, "god_profiles", {}).get(god)


def _role_is_favored_by_god(self, actor, god=None):
    if god is None:
        god = self._player_god()
    if god is None or actor is None:
        return False
    profile = getattr(self.world, "god_profiles", {}).get(god)
    favored = [str(c).strip().lower() for c in getattr(profile, "favored_classes", []) or [] if str(c).strip()]
    if not favored:
        return False
    role_name = getattr(getattr(actor, "role", None), "value", getattr(actor, "role", ""))
    return str(role_name).strip().lower() in favored


def _favored_classes_label(self, god=None):
    if god is None:
        god = self._player_god()
    profile = getattr(self.world, "god_profiles", {}).get(god) if god is not None else None
    favored = getattr(profile, "favored_classes", []) or []
    return ", ".join(str(c) for c in favored) if favored else "None"

def _player_followers(self, adventurers_only=True, alive_only=True):
    god = self._player_god()
    if god is None:
        return []
    actors = []
    for actor in self.world.actors.values():
        if alive_only and not getattr(actor, "alive", False):
            continue
        if adventurers_only and not actor.is_adventurer():
            continue
        if getattr(actor, "deity", None) == god:
            actors.append(actor)
    actors.sort(key=lambda a: (getattr(a, "champion_of", None) != god, not self._role_is_favored_by_god(a, god), -getattr(a, "reputation", 0), -getattr(a, "level", 1), a.short_name()))
    return actors


def _player_champions(self, alive_only=True):
    god = self._player_god()
    if god is None:
        return []
    actors = []
    for actor in self.world.actors.values():
        if alive_only and not getattr(actor, "alive", False):
            continue
        if getattr(actor, "champion_of", None) == god:
            actors.append(actor)
    actors.sort(key=lambda a: (-getattr(a, "reputation", 0), -getattr(a, "level", 1), a.short_name()))
    return actors


def _spend_player_souls(self, cost):
    cost = max(0, int(cost))
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    souls = self._clamp_souls(god) if hasattr(self, "_clamp_souls") else int(getattr(self.world, "souls_by_deity", {}).get(god, 0))
    if souls < cost:
        return False, f"Need {cost} souls; only {souls} available."
    self.world.souls_by_deity[god] = souls - cost
    return True, ""


def _promote_player_champion(self, actor_id, cost=50):
    world = self.world
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    actor = world.actors.get(actor_id)
    if actor is None or not getattr(actor, "alive", False):
        return False, "No living actor selected."
    if not actor.is_adventurer():
        return False, "Only adventurers can become champions."
    if getattr(actor, "deity", None) != god:
        return False, f"{actor.short_name()} does not follow {self._deity_display_name(god)}."
    if getattr(actor, "champion_of", None) == god:
        return False, f"{actor.short_name()} is already your champion."
    favored_class = self._role_is_favored_by_god(actor, god)
    effective_cost = max(10, int(round(cost * 0.70))) if favored_class else cost
    ok, msg = self._spend_player_souls(effective_cost)
    if not ok:
        return False, msg
    actor.champion_of = god
    actor.locked_deity = True
    actor.deity_conviction = 100
    rep_gain = 15 if favored_class else 10
    actor.reputation += rep_gain
    actor.champion_rep_steps = getattr(actor, "champion_rep_steps", 0) + 1
    if favored_class:
        world.log(
            f"{self._deity_display_name(god)} anoints {actor.full_name()} as a favored-class champion.",
            importance=3,
            category="champion_created",
        )
        self._refresh_god_state_if_due(force=True)
        return True, f"Promoted {actor.short_name()} as favored-class champion for {effective_cost} souls."
    world.log(f"{self._deity_display_name(god)} anoints {actor.full_name()} as a champion.", importance=3, category="champion_created")
    self._refresh_god_state_if_due(force=True)
    return True, f"Promoted {actor.short_name()} as champion."


_BOON_DEFS = {
    "might": ("strength", 5, 25, 90, "Might"),
    "grace": ("dexterity", 5, 25, 90, "Grace"),
    "endurance": ("constitution", 5, 25, 90, "Endurance"),
    "insight": ("wisdom", 5, 25, 90, "Insight"),
    "fortune": ("luck", 5, 25, 90, "Fortune"),
    "resolve": ("charisma", 5, 25, 90, "Resolve"),
}


def _grant_player_boon(self, actor_id, boon_type="might"):
    world = self.world
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    actor = world.actors.get(actor_id)
    if actor is None or not getattr(actor, "alive", False):
        return False, "No living actor selected."
    if getattr(actor, "champion_of", None) != god:
        return False, "Boons can only be granted to your champions."
    key = str(boon_type or "might").strip().lower()
    if key not in _BOON_DEFS:
        return False, f"Unknown boon: {boon_type}"
    stat, amount, cost, duration, label = _BOON_DEFS[key]
    favored_class = self._role_is_favored_by_god(actor, god)
    effective_cost = max(5, int(round(cost * 0.80))) if favored_class else cost
    effective_amount = amount + 2 if favored_class else amount
    effective_duration = int(round(duration * 1.50)) if favored_class else duration
    ok, msg = self._spend_player_souls(effective_cost)
    if not ok:
        return False, msg
    if not hasattr(world, "active_boons") or world.active_boons is None:
        world.active_boons = {}
    boon_id = int(getattr(world, "next_boon_id", 1))
    world.next_boon_id = boon_id + 1
    boon = DivineBoon(
        id=boon_id,
        source_god=god,
        target_actor_id=actor.id,
        boon_type=key,
        stat=stat,
        amount=effective_amount,
        started_tick=world.tick,
        expires_tick=world.tick + effective_duration,
        label=label,
    )
    current = int(getattr(actor, stat, 0))
    setattr(actor, stat, current + effective_amount)
    if stat == "constitution":
        actor.max_hp += effective_amount
        actor.hp += effective_amount
    world.active_boons[boon_id] = boon
    world.log(f"{self._deity_display_name(god)} grants {label} to {actor.full_name()}." + (" The favored-class boon burns brighter." if favored_class else ""), importance=2, category="divine_boon")
    self._refresh_god_state_if_due(force=True)
    if favored_class:
        return True, f"Granted enhanced {label} to {actor.short_name()} for {effective_cost} souls."
    return True, f"Granted {label} to {actor.short_name()}."


def _grant_revenge_boon(self, actor, fallen=None):
    if actor is None or not getattr(actor, "alive", False):
        return False
    key = self.rng.choice(list(_BOON_DEFS.keys()))
    stat, amount, _cost, _duration, label = _BOON_DEFS[key]
    duration = int(globals().get("REVENGE_BOON_DURATION_TICKS", TICKS_PER_YEAR))
    if not hasattr(self.world, "active_boons") or self.world.active_boons is None:
        self.world.active_boons = {}
    boon_id = int(getattr(self.world, "next_boon_id", 1))
    self.world.next_boon_id = boon_id + 1
    boon = DivineBoon(
        id=boon_id,
        source_god=getattr(actor, "deity", None),
        target_actor_id=actor.id,
        boon_type=f"revenge_{key}",
        stat=stat,
        amount=amount,
        started_tick=self.world.tick,
        expires_tick=self.world.tick + duration,
        label=f"Vengeance: {label}",
    )
    setattr(actor, stat, int(getattr(actor, stat, 0)) + amount)
    if stat == "constitution":
        actor.max_hp += amount
        actor.hp += amount
    self.world.active_boons[boon_id] = boon
    self.world.log(
        f"{actor.full_name()} carries {label.lower()} from fulfilled vengeance for one year.",
        importance=2,
        category="revenge",
    )
    return True


def _active_boons_for_actor(self, actor_id):
    boons = []
    for boon in getattr(self.world, "active_boons", {}).values():
        if getattr(boon, "target_actor_id", None) == actor_id:
            boons.append(boon)
    actor = self.world.actors.get(actor_id)
    relic = None
    if actor is not None and getattr(actor, "relic_id", None) is not None:
        relic = getattr(self.world, "relics", {}).get(actor.relic_id)
    if relic is not None and getattr(relic, "boon_label", ""):
        key = str(getattr(relic, "boon_label", "")).lower()
        label = RELIC_BOON_DEFS.get(key, {}).get("label", key.title())
        stat = getattr(relic, "boon_stat", "") or RELIC_BOON_DEFS.get(key, {}).get("stat", "")
        amount = int(getattr(relic, "boon_amount", 0) or 0)
        boons.append(DivineBoon(
            id=-int(getattr(relic, "id", 0)),
            source_god=getattr(relic, "creator_deity", None),
            target_actor_id=actor_id,
            boon_type=f"relic_{key}",
            stat=stat,
            amount=amount,
            started_tick=getattr(relic, "created_tick", 0),
            expires_tick=10**12,
            label=f"Relic: {label}",
        ))
    boons.sort(key=lambda b: getattr(b, "expires_tick", 0))
    return boons


def _apply_divine_boons(self):
    world = self.world
    active = getattr(world, "active_boons", None)
    if not active:
        return
    expired = []
    for boon_id, boon in list(active.items()):
        if world.tick < getattr(boon, "expires_tick", 0):
            continue
        actor = world.actors.get(getattr(boon, "target_actor_id", None))
        if actor is not None:
            stat = getattr(boon, "stat", "")
            amount = int(getattr(boon, "amount", 0))
            if hasattr(actor, stat):
                setattr(actor, stat, int(getattr(actor, stat)) - amount)
                if stat == "constitution":
                    actor.max_hp = max(1, actor.max_hp - amount)
                    actor.hp = min(actor.hp, actor.max_hp)
            world.log(f"The {getattr(boon, 'label', 'boon')} fades from {actor.full_name()}.", importance=1, category="divine_boon_expired")
        expired.append(boon_id)
    for boon_id in expired:
        active.pop(boon_id, None)
                


def _grant_player_relic(self, actor_id, tier="lesser", template_key="sword", name="", boon_label="might"):
    world = self.world
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    actor = world.actors.get(actor_id)
    if actor is None or not getattr(actor, "alive", False):
        return False, "No living actor selected."
    if getattr(actor, "champion_of", None) != god:
        return False, "Relics can only be granted directly to your champions."
    if getattr(actor, "relic_id", None) is not None:
        return False, f"{actor.short_name()} already bears a relic."
    tier_key = str(tier or "lesser").strip().lower()
    if tier_key not in RELIC_TIER_DEFS:
        return False, f"Unknown relic tier: {tier}."
    if template_key not in CREATED_RELIC_TEMPLATES:
        return False, f"Unknown relic template: {template_key}."
    template = CREATED_RELIC_TEMPLATES[template_key]
    if not template.allows_role(actor.role):
        return False, f"{template.label} is not valid for {actor.role.value}."
    boon_key = str(boon_label or "might").strip().lower()
    if boon_key not in RELIC_BOON_DEFS:
        return False, f"Unknown relic boon: {boon_label}."
    counts = self._created_relic_counts_for_deity(god) if hasattr(self, "_created_relic_counts_for_deity") else {"lesser": 0, "greater": 0}
    limit = int(RELIC_TIER_DEFS[tier_key].get("limit", 0) or 0)
    if limit and counts.get(tier_key, 0) >= limit:
        return False, f"{tier_key.title()} relic limit reached ({counts.get(tier_key, 0)}/{limit})."
    cost = int(RELIC_TIER_DEFS[tier_key].get("cost", 0) or 0)
    ok, msg = self._spend_player_souls(cost)
    if not ok:
        return False, msg
    payload = build_relic_payload(
        name=name or f"{template.label} of {actor.short_name()}",
        template_key=template_key,
        tier=tier_key,
        boon_key=boon_key,
        creator_deity=god,
        original_recipient_id=actor.id,
    )
    relic = self._create_custom_relic_for_actor(
        actor, payload["name"], payload["type"], payload["slot"], payload["power_bonus"], payload["reputation_bonus"], payload["description"],
        creator_deity=god, tier=tier_key, boon_label=boon_key, boon_stat=payload["boon_stat"], boon_amount=payload["boon_amount"],
        template_key=template_key, template_label=payload["template_label"], original_recipient_id=actor.id, created_by_player=True,
    )
    if relic is None:
        return False, "Relic creation failed."
    world.log(f"{self._deity_display_name(god)} forges {relic.name}, a {tier_key} relic, for {actor.full_name()}.", importance=4, category="relic")
    self._refresh_god_state_if_due(force=True)
    counts = self._created_relic_counts_for_deity(god)
    return True, f"Granted {relic.name} to {actor.short_name()} for {cost} souls. Relics: lesser {counts.get('lesser',0)}/{int(RELIC_TIER_DEFS['lesser'].get('limit',0))}, greater {counts.get('greater',0)}/{int(RELIC_TIER_DEFS['greater'].get('limit',0))}."


def _player_majority_control_share(self):
    """Living-faith share across commoners + living actors, excluding souls/influence modifiers."""
    god = self._player_god()
    if god is None:
        return None
    total = 0
    controlled = 0
    for actor in self.world.living_actors():
        total += 1
        if getattr(actor, "deity", None) == god:
            controlled += 1
    for _rid, faith_map in getattr(self.world, "commoner_faith_by_region", {}).items():
        for deity, count in faith_map.items():
            c = max(0, int(count))
            total += c
            if deity == god:
                controlled += c
    if total <= 0:
        return 0.0
    return (controlled / total) * 100.0


def _directive_actor_name(self, actor_id):
    actor = self.world.actors.get(actor_id)
    return actor.short_name() if actor is not None else f"actor {actor_id}"


def _clear_divine_directive(self, actor):
    actor.divine_directive_type = None
    actor.divine_directive_source = None
    actor.divine_directive_target_actor_id = None
    actor.divine_directive_target_region_id = None
    actor.divine_directive_issued_tick = -1
    actor.divine_directive_attempted = False
    actor.divine_directive_ignore_count = 0


def _assign_divine_directive(self, actor, directive_type, source_god, target_actor_id=None, target_region_id=None):
    actor.divine_directive_type = directive_type
    actor.divine_directive_source = source_god
    actor.divine_directive_target_actor_id = target_actor_id
    actor.divine_directive_target_region_id = target_region_id
    actor.divine_directive_issued_tick = int(getattr(self.world, "tick", 0))
    actor.divine_directive_attempted = False
    actor.divine_directive_ignore_count = 0


def _divine_directive_accept_chance(self, actor, directive_type):
    god = getattr(actor, "divine_directive_source", None)
    chance = 0.30
    if getattr(actor, "champion_of", None) == god:
        chance += float(globals().get("DIVINE_DIRECTIVE_CHAMPION_ACCEPT_BONUS", 0.45))
    elif getattr(actor, "deity", None) == god:
        chance += float(globals().get("DIVINE_DIRECTIVE_FOLLOWER_ACCEPT_BONUS", 0.20))
    chance += max(0.0, min(0.25, (float(getattr(actor, "deity_conviction", 50)) - 50.0) / 200.0))
    chance += max(0.0, min(0.10, (float(getattr(actor, "loyalty", 50) or 50) - 50.0) / 500.0))
    if self._role_is_favored_by_god(actor, god):
        chance += 0.08
    if directive_type == "assassinate":
        target = self.world.actors.get(getattr(actor, "divine_directive_target_actor_id", None))
        if target is not None:
            if getattr(target, "deity", None) == getattr(actor, "deity", None):
                chance -= 0.20
            if getattr(actor, "best_friend_id", None) == getattr(target, "id", None):
                chance -= 0.45
            if getattr(actor, "spouse_id", None) == getattr(target, "id", None):
                chance -= 0.65
            if getattr(target, "id", None) in set(getattr(actor, "friend_ids", []) or []):
                chance -= 0.25
            if getattr(actor, "nemesis_id", None) == getattr(target, "id", None):
                chance += 0.25
            if actor.is_good() and target.is_good():
                chance -= 0.25
            if actor.is_evil() and target.is_good():
                chance += 0.10
    elif directive_type == "stabilize":
        if actor.is_good():
            chance += 0.10
        if actor.is_evil():
            chance -= 0.10
    elif directive_type == "destabilize":
        if actor.is_evil():
            chance += 0.10
        if actor.is_good():
            chance -= 0.10
    return max(0.05, min(0.95, chance))


def _path_next_region_toward(self, start_region_id, target_region_id):
    if start_region_id == target_region_id:
        return start_region_id
    regions = getattr(self.world, "regions", {})
    if start_region_id not in regions or target_region_id not in regions:
        return None
    frontier = [(start_region_id, [])]
    seen = {start_region_id}
    while frontier:
        rid, path = frontier.pop(0)
        for nid in getattr(regions[rid], "neighbors", []) or []:
            if nid in seen:
                continue
            new_path = path + [nid]
            if nid == target_region_id:
                return new_path[0] if new_path else target_region_id
            seen.add(nid)
            frontier.append((nid, new_path))
    neighbors = getattr(regions[start_region_id], "neighbors", []) or []
    return self.rng.choice(neighbors) if neighbors else None


def _move_actor_or_party_to_region(self, actor, target_region_id):
    next_region = self._path_next_region_toward(actor.region_id, target_region_id)
    if next_region is None or next_region == actor.region_id:
        return False
    party = self.world.get_party(actor)
    movers = [actor]
    if party is not None and getattr(party, "leader_id", None) == actor.id:
        movers = [self.world.actors[mid] for mid in party.member_ids if mid in self.world.actors and self.world.actors[mid].alive]
    for mover in movers:
        world.move_actor(mover, next_region) if hasattr(world, "move_actor") else setattr(mover, "region_id", next_region)
    self._spend_action(actor)
    return True


def _candidate_player_directive_agents(self):
    god = self._player_god()
    if god is None:
        return []
    agents = []
    for actor in self.world.living_actors():
        if not actor.is_adventurer() or getattr(actor, "retired", False) or getattr(actor, "in_school", False):
            continue
        if getattr(actor, "deity", None) != god and getattr(actor, "champion_of", None) != god:
            continue
        if getattr(actor, "divine_directive_type", None):
            continue
        agents.append(actor)
    agents.sort(key=lambda a: (getattr(a, "champion_of", None) == god, self._role_is_favored_by_god(a, god), getattr(a, "deity_conviction", 50), getattr(a, "reputation", 0), a.power_rating()), reverse=True)
    return agents


def _issue_player_assassination_target(self, target_actor_id):
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    target = self.world.actors.get(target_actor_id)
    if target is None or not getattr(target, "alive", False):
        return False, "No living target selected."
    if getattr(target, "deity", None) == god or getattr(target, "champion_of", None) == god:
        return False, "Cannot target your own faithful."
    cost = int(globals().get("DIVINE_TARGET_SOUL_COST", 75))
    agents = [a for a in self._candidate_player_directive_agents() if a.id != target.id]
    champions = [a for a in agents if getattr(a, "champion_of", None) == god]
    normals = [a for a in agents if getattr(a, "champion_of", None) != god]
    if not champions:
        return False, "Targeting requires at least one available champion."
    picked = champions[:1] + normals[:2]
    if len(picked) < 1:
        return False, "No available agents."
    ok, msg = self._spend_player_souls(cost)
    if not ok:
        return False, msg
    for actor in picked:
        self._assign_divine_directive(actor, "assassinate", god, target_actor_id=target.id)
    names = ", ".join(a.short_name() for a in picked)
    self.world.log(
        f"{self._deity_display_name(god)} marks {target.full_name()} for death. {names} receive the omen.",
        importance=3,
        category="divine_target",
    )
    return True, f"Target marked: {target.short_name()}. Agents: {names}. Cost {cost} souls."


def _cancel_player_assassination_target(self, target_actor_id=None):
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    cleared = 0
    target_name = None
    if target_actor_id is not None:
        target = self.resolve_actor(target_actor_id) if hasattr(self, "resolve_actor") else self.world.actors.get(target_actor_id)
        target_name = target.short_name() if target is not None and hasattr(target, "short_name") else f"actor {target_actor_id}"
    for actor in list(self.world.living_actors()):
        if getattr(actor, "divine_directive_type", None) != "assassinate":
            continue
        if getattr(actor, "divine_directive_source", None) != god:
            continue
        if target_actor_id is not None and getattr(actor, "divine_directive_target_actor_id", None) != target_actor_id:
            continue
        self._clear_divine_directive(actor)
        cleared += 1
    if cleared <= 0:
        return False, "No active target directive to cancel."
    if target_actor_id is None:
        self.world.log(f"{self._deity_display_name(god)} calls off all active target-marks.", importance=2, category="divine_target_cancelled")
        return True, f"Cancelled {cleared} target agent{'s' if cleared != 1 else ''}."
    self.world.log(f"{self._deity_display_name(god)} calls off the target-mark on {target_name}.", importance=2, category="divine_target_cancelled")
    return True, f"Cancelled target on {target_name}; {cleared} agent{'s' if cleared != 1 else ''} stood down."


def _issue_player_region_directive(self, region_id, directive_type):
    god = self._player_god()
    if god is None:
        return False, "No player god loaded."
    if region_id not in getattr(self.world, "regions", {}):
        return False, "No region selected."
    directive_type = str(directive_type).strip().lower()
    if directive_type not in {"stabilize", "destabilize"}:
        return False, "Unknown region directive."
    cost = int(globals().get("DIVINE_REGION_DIRECTIVE_SOUL_COST", 25))
    agents = self._candidate_player_directive_agents()
    if not agents:
        return False, "No available champion or follower can receive the directive."
    # Prefer champions, then nearby/high-conviction followers.
    def score(actor):
        dist_bonus = 0
        if getattr(actor, "region_id", None) == region_id:
            dist_bonus = 50
        elif region_id in (getattr(self.world.regions.get(actor.region_id), "neighbors", []) or []):
            dist_bonus = 25
        return (getattr(actor, "champion_of", None) == god, dist_bonus, getattr(actor, "deity_conviction", 50), getattr(actor, "reputation", 0), actor.power_rating())
    actor = max(agents, key=score)
    ok, msg = self._spend_player_souls(cost)
    if not ok:
        return False, msg
    self._assign_divine_directive(actor, directive_type, god, target_region_id=region_id)
    region_name = self.world.region_name(region_id)
    verb = "stabilize" if directive_type == "stabilize" else "destabilize"
    self.world.log(
        f"{self._deity_display_name(god)} urges {actor.full_name()} to {verb} {region_name}.",
        importance=2,
        category="divine_directive",
    )
    return True, f"Directive sent: {actor.short_name()} will try to {verb} {region_name}. Cost {cost} souls."


def _handle_divine_directive(self, actor):
    directive = getattr(actor, "divine_directive_type", None)
    if not directive:
        return False
    world = self.world
    issued = int(getattr(actor, "divine_directive_issued_tick", -1))
    expiry = int(globals().get("DIVINE_DIRECTIVE_EXPIRATION_TICKS", TICKS_PER_YEAR))
    if issued >= 0 and world.tick - issued > expiry:
        world.log(f"{actor.full_name()} lets a divine directive fade unanswered.", importance=1, category="divine_directive")
        self._clear_divine_directive(actor)
        return False
    if self.rng.random() > self._divine_directive_accept_chance(actor, directive):
        actor.divine_directive_ignore_count = int(getattr(actor, "divine_directive_ignore_count", 0)) + 1
        if actor.divine_directive_ignore_count >= 5 and self.rng.random() < 0.20:
            world.log(f"{actor.full_name()} ignores the omen from {self._deity_display_name(getattr(actor, 'divine_directive_source', None))}.", importance=1, category="divine_directive_ignored")
            self._clear_divine_directive(actor)
        return False
    if directive == "assassinate":
        target = world.actors.get(getattr(actor, "divine_directive_target_actor_id", None))
        if target is None or not getattr(target, "alive", False):
            self._clear_divine_directive(actor)
            return False
        if getattr(actor, "region_id", None) != getattr(target, "region_id", None):
            return self._move_actor_or_party_to_region(actor, target.region_id)
        world.log(f"{actor.full_name()} answers the divine target-mark and strikes at {target.full_name()}.", importance=3, category="divine_target_attempt")
        self._resolve_battle(actor, target)
        source = getattr(actor, "divine_directive_source", None)
        target_id = target.id
        for other in list(world.living_actors()):
            if getattr(other, "divine_directive_type", None) == "assassinate" and getattr(other, "divine_directive_source", None) == source and getattr(other, "divine_directive_target_actor_id", None) == target_id:
                self._clear_divine_directive(other)
        return True
    if directive in {"stabilize", "destabilize"}:
        target_region_id = getattr(actor, "divine_directive_target_region_id", None)
        if target_region_id not in world.regions:
            self._clear_divine_directive(actor)
            return False
        if actor.region_id != target_region_id:
            return self._move_actor_or_party_to_region(actor, target_region_id)
        if directive == "stabilize":
            cd = int(globals().get("DIVINE_STABILIZE_CONTROL_DELTA", 3))
            od = int(globals().get("DIVINE_STABILIZE_ORDER_DELTA", 10))
            verb = "stabilizes"
        else:
            cd = int(globals().get("DIVINE_DESTABILIZE_CONTROL_DELTA", -3))
            od = int(globals().get("DIVINE_DESTABILIZE_ORDER_DELTA", -10))
            verb = "destabilizes"
        world.adjust_region_state(target_region_id, control_delta=cd, order_delta=od)
        actor.reputation = max(0, getattr(actor, "reputation", 0) + 1)
        self._spend_action(actor)
        world.log(f"{actor.full_name()} {verb} {world.region_name(target_region_id)} under divine urging.", importance=2, category="divine_region_directive")
        self._clear_divine_directive(actor)
        return True
    self._clear_divine_directive(actor)
    return False


def _apply_divine_directive_maintenance(self):
    # Hook exists mostly so old saves gain the attributes lazily and expired directives do not linger forever.
    expiry = int(globals().get("DIVINE_DIRECTIVE_EXPIRATION_TICKS", TICKS_PER_YEAR))
    # Only scan living actors — dead actors cannot have active directives.
    for actor in list(self.world.living_actors()):
        if not hasattr(actor, "divine_directive_type"):
            self._clear_divine_directive(actor)
            continue
        directive = getattr(actor, "divine_directive_type", None)
        if not directive:
            continue
        if getattr(actor, "retired", False):
            self._clear_divine_directive(actor)
            continue
        issued = int(getattr(actor, "divine_directive_issued_tick", -1))
        if issued >= 0 and self.world.tick - issued > expiry:
            self._clear_divine_directive(actor)

def _living_actor_followers(self, deity_name):
    return [
        actor for actor in self.world.living_actors()
        if getattr(actor, "deity", None) == deity_name
    ]

Simulator._living_actor_followers = _living_actor_followers        

Simulator._player_majority_control_share = _player_majority_control_share
Simulator._clear_divine_directive = _clear_divine_directive
Simulator._assign_divine_directive = _assign_divine_directive
Simulator._divine_directive_accept_chance = _divine_directive_accept_chance
Simulator._path_next_region_toward = _path_next_region_toward
Simulator._move_actor_or_party_to_region = _move_actor_or_party_to_region
Simulator._candidate_player_directive_agents = _candidate_player_directive_agents
Simulator._issue_player_assassination_target = _issue_player_assassination_target
Simulator._cancel_player_assassination_target = _cancel_player_assassination_target
Simulator._issue_player_region_directive = _issue_player_region_directive
Simulator._handle_divine_directive = _handle_divine_directive
Simulator._apply_divine_directive_maintenance = _apply_divine_directive_maintenance


Simulator._update_god_state = _update_god_state

# Player-god agency hooks for the curses UI.
Simulator._deity_key_for_lookup = staticmethod(_deity_key_for_lookup)
Simulator._unique_god_name = _unique_god_name
Simulator._load_injection_profile = _load_injection_profile
Simulator._ensure_injection_state = _ensure_injection_state
Simulator._register_formal_player_god = _register_formal_player_god
Simulator._god_immortal_grace_remaining = _god_immortal_grace_remaining
Simulator._god_has_immortal_grace = _god_has_immortal_grace
Simulator._maybe_unlock_revelation_schools = _maybe_unlock_revelation_schools
Simulator.inject_revealed_player_god = inject_revealed_player_god
Simulator.eligible_player_cults = eligible_player_cults
Simulator.formalize_proto_cult_as_player_god = formalize_proto_cult_as_player_god
Simulator._inject_story_champion_for_god = _inject_story_champion_for_god
Simulator._player_god = _player_god
Simulator._player_god_state = _player_god_state
Simulator._living_follower_share = _living_follower_share
Simulator._player_living_follower_share = _player_living_follower_share
Simulator._player_map_dominance_share = _player_map_dominance_share
Simulator._update_player_map_dominance_streak = _update_player_map_dominance_streak
Simulator._deity_display_name = _deity_display_name
Simulator._player_god_profile = _player_god_profile
Simulator._role_is_favored_by_god = _role_is_favored_by_god
Simulator._favored_classes_label = _favored_classes_label
Simulator._player_followers = _player_followers
Simulator._player_champions = _player_champions
Simulator._spend_player_souls = _spend_player_souls
Simulator._promote_player_champion = _promote_player_champion
Simulator._grant_player_boon = _grant_player_boon
Simulator._grant_player_relic = _grant_player_relic
Simulator._grant_revenge_boon = _grant_revenge_boon
Simulator._active_boons_for_actor = _active_boons_for_actor
Simulator._apply_divine_boons = _apply_divine_boons
Simulator._holy_war_targets_for_god = _holy_war_targets_for_god
Simulator._launch_holy_war_as_god = _launch_holy_war_as_god
Simulator._holy_war_available_targets = _holy_war_available_targets
Simulator._holy_war_status = _holy_war_status
Simulator._launch_holy_war = _launch_holy_war

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fantasy antfarm simulation.",
        epilog=(
            "Operators: --verbose/-v for live events, --delay for pacing live output, "
            "--seed for reproducible alphanumeric worlds, --years for yearly duration override, "
            "--verbose-importance to filter live event noise."
        ),
    )
    parser.add_argument("--seed", type=str, default=DEFAULT_SEED, help="Alphanumeric seed for world generation. Omit for a fresh random world.")
    parser.add_argument("--year", "--years", dest="years", type=_parse_years_or_indef, default=DEFAULT_YEARS, help="How many years to simulate. Use a whole number, or 'indef' to run until interrupted. Default is 1.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print events as the simulation runs instead of waiting for the final summary.")
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay in seconds between ticks when verbose mode is enabled.")
    parser.add_argument("--verbose-importance", type=int, default=VERBOSE_EVENT_IMPORTANCE, help="1-3, 3 = most. Only print live events at or above this importance level in verbose mode.")
    parser.add_argument("--pop-scale", "--population-scale", dest="pop_scale", type=_parse_population_scale, default=1.0, help="Scale regional population and capacity. Accepts values like 2, 0.25, or 1/4.")
    parser.add_argument("--psum", type=int, default=0, help="Write periodic summary snapshots every N simulated years. Example: --psum 1 or --psum 5. Default is off.")
    parser.add_argument("--no-historian", action="store_true", help="Disable the SQLite historian/tome archive for this run.")
    parser.add_argument("--historian-event-limit", type=int, default=None, help="Override historian event lookback limit used by summaries.")
    parser.add_argument("--event-memory-limit", type=int, default=None, help="Override recent in-memory event buffer size.")
    parser.add_argument("--no-csv", action="store_true", help="Disable summary CSV exports for this run.")
    parser.add_argument("--no-summaries", action="store_true", help="Disable periodic summary writes even if --psum is set.")
    parser.add_argument("--autosave", type=int, default=0, help="Headless autosave every N simulated years; overwrites data/autosave/<seed>_autosave.fics. 0 disables autosave.")
    parser.add_argument("--mce", action="store_true", help="Load MCE .imrt/.stri custom gods, story actors, champions, and starting relics. Headless default is base pantheon only.")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    years = args.years
    ticks = None if years == "indef" else max(1, years) * TICKS_PER_YEAR
    import os
    if args.no_historian:
        os.environ["FANTFARM_HISTORIAN_ENABLED"] = "0"
    if args.historian_event_limit is not None:
        os.environ["FANTFARM_HISTORIAN_EVENT_LIMIT"] = str(max(0, int(args.historian_event_limit)))
    if args.event_memory_limit is not None:
        os.environ["FANTFARM_EVENT_MEMORY_LIMIT"] = str(max(0, int(args.event_memory_limit)))
    if args.no_csv:
        os.environ["FANTFARM_CSV_ENABLED"] = "0"
    if args.no_summaries:
        os.environ["FANTFARM_SUMMARIES_ENABLED"] = "0"
    simulator = Simulator(
        seed=args.seed,
        verbose=args.verbose,
        verbose_delay=args.delay,
        verbose_min_importance=args.verbose_importance,
        population_scale=args.pop_scale,
        load_mce=args.mce,
    )
    # Preserve the source map created during world construction.  That map is
    # populated with direct runtime module objects where available, which lets
    # the report name the real versioned files instead of the FASE wrapper files.
    # The old CLI-side assignment rebuilt this from wrapper module names and
    # clobbered the better data before summaries were written.
    simulator.world.source_files = dict(getattr(simulator.world, "source_files", {}) or {})
    simulator.world.source_files.setdefault("simulator", Path(__file__).name)
    simulator.world.source_files.setdefault("config", _runtime_source_name("FASEcfg", "FASEcfg.py"))
    simulator.world.source_files.setdefault("class", _runtime_source_name("FASEclass", "FASEclass.py"))
    simulator.world.source_files.setdefault("population", _runtime_source_name("FASEpop", "FASEpop.py"))
    simulator.world.source_files.setdefault("legacy", _runtime_source_name("FASEleg", "FASEleg.py"))
    simulator.world.source_files.setdefault("lore", _runtime_source_name("FASElore", "FASElore.py"))
    simulator.world.source_files.setdefault("relics", _runtime_source_name("FASErlc", "FASErlc.py"))
    simulator.world.source_files.setdefault("immortals", _runtime_source_name("FASEimm", "FASEimm.py"))
    simulator.world.source_files.setdefault("summary", _runtime_source_name("FASEsum", "FASEsum.py"))
    simulator.world.source_files.setdefault("economy", _runtime_source_name("FASEeco", "FASEeco.py"))
    simulator.world.source_files.setdefault("morgue", _runtime_source_name("FASEmrg", "FASEmrg.py"))
    simulator.world.source_files.setdefault("historian", _runtime_source_name("FASEtome", "FASEtome.py"))
    simulator.world.source_files.setdefault("combat", _runtime_source_name("FASEcom", "FASEcom.py"))
    simulator.world.source_files.setdefault("monsters", _runtime_source_name("FASEmon", "FASEmon.py"))
    simulator.world.source_files.setdefault("party", _runtime_source_name("FASEprty", "FASEprty.py"))
    simulator.world.source_files.setdefault("politics", _runtime_source_name("FASEpoli", "FASEpoli.py"))
    simulator.world.source_files.setdefault("world", _runtime_source_name("FASEworld", "FASEworld.py"))
    simulator.world.source_files.setdefault("start_game", _glob_latest("start_game_v*.py"))
    simulator.world.source_files.setdefault("ux", _parse_fase_runmodule("FASEux.py"))
    simulator.world.source_files.setdefault("fantag", _runtime_source_name("FASEag", "FASEag.py"))
    simulator.world.source_files.setdefault("fantgg", _runtime_source_name("FASEgg", "FASEgg.py"))

    simulator.world.output_dir = _make_run_output_dir(simulator.world.seed_used)
    simulator.world.output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.perf_counter()
    interrupted = False
    try:
        if years == "indef":
            _run_indefinitely(simulator, periodic_summary_years=args.psum, autosave_years=args.autosave)
        else:
            simulator.run(ticks, periodic_summary_years=args.psum, autosave_years=args.autosave)
    except KeyboardInterrupt:
        interrupted = True
        print()
        print("Simulation interrupted. Writing partial summary from the current world state.")
    end_time = time.perf_counter()

    simulator.world.runtime_seconds = end_time - start_time
    summary_label = ("indef" if years == "indef" and not interrupted else years) if not interrupted else f"partial_{simulator.world.tick}ticks"

    simulator._story_sync_all()
    simulator._story_flush_files(force=True)
    summary.print_summary(simulator, summary_label)
    if simulator.world.polities:
        print()
        print("POLITIES")
        print("-" * 72)
        for polity in simulator.world.polities.values():
            ruler = simulator.world.actors.get(polity.ruler_id)
            ruler_name = ruler.short_name() if ruler and ruler.alive else "None"
            print(f"{polity.name}: ruler={ruler_name}, capital={simulator.world.region_name(polity.capital_region_id)}, regions={len(polity.region_ids)}, members={len(polity.member_actor_ids)}")
    _print_summary_extra(simulator, summary_label)
    summary.write_summary(simulator, summary_label)

if __name__ == "__main__":
    main()
