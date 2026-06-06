
from __future__ import annotations
from typing import Optional, Tuple, List, Dict
import csv
import io
import re
import sys
from pathlib import Path
from contextlib import redirect_stdout

try:
    from FASEimm import actor_current_protocult, protocult_duration_years
except Exception:
    actor_current_protocult = None
    def protocult_duration_years(_world, _actor):
        return 0.0


def _env_bool(name: str, default: bool) -> bool:
    import os
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _config_module_value(name: str, default):
    """Read a value from the live config module, not only summary globals.

    ``summary`` is imported as its own runtime module and is not part of the
    simulator's normal runtime-global injection list.  Section switches such as
    SUMMARY_ADVENTURER_LISTS_ENABLED therefore must be read from FASEcfg/config
    explicitly, otherwise ``globals().get(...)`` falls back to the hard-coded
    default and the knobs appear to do nothing.  Annoying, but at least finite.
    """
    for module_name in ("FASEcfg", "config", "fantfarm_config"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            return getattr(module, name)

    # Fallback for direct testing with a versioned config file imported by name.
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("config_v") and hasattr(module, name):
            return getattr(module, name)

    return globals().get(name, default)


def _config_bool(sim, name: str, default: bool = True) -> bool:
    """Read a boolean knob from live config, environment, runtime options, or sim attrs.

    Precedence is intentionally generous for older launchers:
    live config module -> summary globals fallback -> FANTFARM_<NAME> env ->
    world.runtime_options -> sim attr. Lower-case aliases are accepted for
    runtime options and sim attrs.
    """
    value = bool(_config_module_value(name, default))
    value = _env_bool(f"FANTFARM_{name}", value)

    world = getattr(sim, "world", None)
    opts = getattr(world, "runtime_options", {}) if world is not None else {}
    if isinstance(opts, dict):
        for key in (name, name.lower()):
            if key in opts:
                value = bool(opts.get(key))
                break

    for key in (name, name.lower()):
        if hasattr(sim, key):
            value = bool(getattr(sim, key))
            break
    return bool(value)


def _summary_output_enabled(sim) -> bool:
    return _config_bool(sim, "SUMMARY_ENABLED", True)


def _summary_section_enabled(sim, name: str, default: bool = True) -> bool:
    return _summary_output_enabled(sim) and _config_bool(sim, name, default)


def _legendarium_output_enabled(sim) -> bool:
    return _config_bool(sim, "LEGENDARIUM_ENABLED", True)


def _legendarium_section_enabled(sim, name: str, default: bool = True) -> bool:
    return _legendarium_output_enabled(sim) and _config_bool(sim, name, default)


def _csv_file_enabled(sim, name: str, legacy_attr: str | None = None) -> bool:
    """Return whether a specific CSV export should be written.

    CSV toggles are stricter than ordinary summary display toggles: a False in
    live config or FANTFARM_* env is a hard stop.  Older simulator instances
    also carry legacy attrs such as ``csv_metrics_enabled`` that defaulted True
    at run start; those must not silently re-enable CSV after config says off.
    Legacy runtime attrs/options may still disable CSV, but they cannot override
    an explicit config/env False.
    """
    master = bool(_config_module_value("CSV_EXPORTS_ENABLED", True))
    specific = bool(_config_module_value(name, True))

    master = _env_bool("FANTFARM_CSV_EXPORTS_ENABLED", master)
    specific = _env_bool(f"FANTFARM_{name}", specific)

    enabled = bool(master and specific)
    if not enabled:
        return False

    if legacy_attr:
        world = getattr(sim, "world", None)
        opts = getattr(world, "runtime_options", {}) if world is not None else {}
        if isinstance(opts, dict) and legacy_attr in opts and not bool(opts.get(legacy_attr)):
            return False
        if hasattr(sim, legacy_attr) and not bool(getattr(sim, legacy_attr)):
            return False
    return True


def _csv_exports_enabled(sim) -> bool:
    # Legacy name retained for callers that treated this as "metrics CSV enabled."
    return _csv_file_enabled(sim, "CSV_METRICS_ENABLED", legacy_attr="csv_metrics_enabled")


def _csv_metrics_enabled(sim) -> bool:
    return _csv_file_enabled(sim, "CSV_METRICS_ENABLED", legacy_attr="csv_metrics_enabled")


def _csv_history_enabled(sim) -> bool:
    return _csv_file_enabled(sim, "CSV_HISTORY_ENABLED", legacy_attr="csv_history_enabled")


def _csv_events_enabled(sim) -> bool:
    return _csv_file_enabled(sim, "CSV_EVENTS_ENABLED", legacy_attr="csv_events_enabled")


def _aggregate_commoners(world) -> int:
    return sum(getattr(world, 'commoners_by_region', {}).values()) if hasattr(world, 'commoners_by_region') else 0


def _living_population(world) -> int:
    return len(world.living_actors()) + _aggregate_commoners(world)


def _living_by_role(world, sim):
    living_by_role = {role: 0 for role in sim.Role}
    for actor in world.living_actors():
        living_by_role[actor.role] += 1
    if hasattr(world, 'commoners_by_region'):
        living_by_role[sim.Role.COMMONER] = _aggregate_commoners(world)
    return living_by_role


def _pantheon(sim):
    """Return the run's full pantheon, including custom gods.

    v51 accidentally returned only ``sim.Deity``. That stabilized CSV columns
    for the three built-in gods but hid player/custom .imrt gods from UI
    callers such as ux_curses._draw_immortal_summary().

    ``sim.pantheon`` is the correct stable source: it is built at run start
    from the default Deity enum plus active .imrt gods. If unavailable, fall
    back to world.gods, then the legacy enum.
    """
    pantheon = getattr(sim, "pantheon", None)
    if pantheon:
        return list(pantheon)
    world = getattr(sim, "world", None)
    if world is not None and hasattr(world, "gods"):
        return list(getattr(world, "gods", []))
    return list(sim.Deity)


def _is_formal_school_deity(sim, deity) -> bool:
    if deity is None:
        return False
    if hasattr(sim, "_is_formal_school_deity"):
        try:
            return bool(sim._is_formal_school_deity(deity))
        except Exception:
            pass
    profile = getattr(getattr(sim, "world", None), "god_profiles", {}).get(deity) or getattr(sim, "god_profiles", {}).get(deity)
    if str(getattr(profile, "source_path", "") or "") == "emergent_lore":
        return False
    if str(getattr(profile, "profile_id", "") or "").startswith("ascended_"):
        return False
    pantheon = list(getattr(sim, "pantheon", []) or [])
    return deity in pantheon if pantheon else True


def _commoner_deity_counts(world, sim) -> Dict[object, int]:
    deities = _pantheon(sim)
    counts = {deity: 0 for deity in deities}
    faith = getattr(world, "commoner_faith_by_region", {})
    for region_map in faith.values():
        for deity in deities:
            counts[deity] += region_map.get(deity, 0)
    return counts


def _deity_influence_summary(sim) -> List[Tuple[object, int, int, int, int, float]]:
    surviving = sim.world.living_actors()
    soul_weight = 2
    commoner_counts = _commoner_deity_counts(sim.world, sim)
    results = []
    total_influence = 0
    for deity in _pantheon(sim):
        living = len([actor for actor in surviving if actor.deity == deity])
        commoners = commoner_counts.get(deity, 0)
        souls = sim.world.souls_by_deity.get(deity, 0)
        influence = living + commoners + (souls * soul_weight)
        results.append((deity, living, commoners, souls, influence, 0.0))
        total_influence += influence
    if total_influence <= 0:
        return [(deity, living, commoners, souls, influence, 0.0) for deity, living, commoners, souls, influence, _ in results]
    final = []
    for deity, living, commoners, souls, influence, _ in results:
        final.append((deity, living, commoners, souls, influence, influence / total_influence * 100.0))
    return final


def _pick_top_hero_and_villain(sim) -> Tuple[Optional[object], Optional[object]]:
    source = sim.world.living_actors() if hasattr(sim.world, "living_actors") else sim.world.actors.values()
    everyone = [a for a in source if a.is_adventurer()]
    heroes = [a for a in everyone if not a.is_evil()]
    villains = [a for a in everyone if a.is_evil()]
    hero = max(heroes, key=_adventurer_score, default=None)
    villain = max(villains, key=_villain_score, default=None)
    return hero, villain


def _adventurer_score(actor):
    return (
        actor.reputation,
        actor.dragon_kills,
        actor.horror_kills,
        actor.monster_kills,
        actor.kills,
        actor.power_rating(),
    )


def _villain_score(actor):
    return (
        actor.reputation,
        actor.regions_oppressed,
        actor.kills,
        actor.monster_kills,
        actor.power_rating(),
    )


def _dead_actor_count(world) -> int:
    index = getattr(world, "dead_actor_index", {}) or {}
    return max(int(getattr(world, "dead_actor_count", 0) or 0), len(index))


def _dead_adventurer_count(world) -> int:
    index = getattr(world, "dead_actor_index", {}) or {}
    return len([item for item in index.values() if str(item.get("role", "")).lower() != "commoner"])


def _historical_population_estimate(world):
    living_adventurers = len(world.living_actors())
    dead_adventurers = _dead_adventurer_count(world)
    living_commoners = sum(world.commoners_by_region.values()) if hasattr(world, "commoners_by_region") else 0
    return living_adventurers + dead_adventurers + living_commoners


def _source_files(world):
    if hasattr(world, "source_files"):
        return world.source_files
    return {}


def _month_names(sim, world):
    return getattr(sim, "MONTH_NAMES", None) or getattr(world, "MONTH_NAMES", None) or [
        "Dawnsreach", "Rainmoot", "Bloomtide", "Suncrest", "Goldfire", "Highsun",
        "Harvestwane", "Emberfall", "Duskmarch", "Frostturn", "Deepcold", "Yearsend",
    ]


def _short_date_from_parts(day, month, year, month_names):
    if day is None or month is None or year is None:
        return "Unknown"
    if not isinstance(month, int) or month < 1 or month > len(month_names):
        return f"{int(day):02d} ? {int(year)}"
    return f"{int(day):02d} {month_names[month - 1]} {int(year)}"


def _short_date_from_timestamp(timestamp: Optional[str]) -> str:
    if not timestamp:
        return "Unknown"
    m = re.match(r"Year\s+(-?\d+),\s+\w+,\s+([A-Za-z]+)\s+(\d+),", str(timestamp))
    if not m:
        return "Unknown"
    year = int(m.group(1))
    month_name = m.group(2)
    day = int(m.group(3))
    return f"{day:02d} {month_name} {year}"


def _short_birth_date(sim, world, actor) -> str:
    return _short_date_from_parts(
        getattr(actor, "birth_day", None),
        getattr(actor, "birth_month", None),
        getattr(actor, "birth_year", None),
        _month_names(sim, world),
    )


def _death_line(actor) -> str:
    if not getattr(actor, "death_timestamp", None):
        return "—"
    cause = getattr(actor, "death_cause", None) or "Unknown"
    return f"{_short_date_from_timestamp(actor.death_timestamp)} — {cause}"


def _print_section(title: str) -> None:
    print(title)
    print("-" * 72)



def _historian(sim):
    world = getattr(sim, "world", None)
    return getattr(sim, "historian", None) or getattr(world, "historian", None)


def _summary_event_source(sim):
    world = sim.world
    historian = _historian(sim)
    if historian is not None:
        try:
            historian.flush()
            lookback = int(getattr(sim, "HISTORIAN_SUMMARY_LOOKBACK_TICKS", globals().get("HISTORIAN_SUMMARY_LOOKBACK_TICKS", 0)) or 0)
            limit = int(getattr(sim, "historian_event_limit", 0) or 0)
            if limit <= 0:
                import os
                env_limit = os.environ.get("FANTFARM_HISTORIAN_EVENT_LIMIT")
                limit = int(env_limit) if env_limit and str(env_limit).strip().isdigit() else int(getattr(sim, "HISTORIAN_SUMMARY_EVENT_LIMIT", globals().get("HISTORIAN_SUMMARY_EVENT_LIMIT", 5000)) or 5000)
            events = historian.summary_events(current_tick=getattr(world, "tick", None), lookback_ticks=lookback, limit=limit)
            if events:
                return events
        except Exception:
            pass
    return list(getattr(world, "events", []) or [])


def _historian_category_events(sim, categories, *, limit=100):
    historian = _historian(sim)
    if historian is not None:
        try:
            historian.flush()
            lookback = int(getattr(sim, "HISTORIAN_SUMMARY_LOOKBACK_TICKS", globals().get("HISTORIAN_SUMMARY_LOOKBACK_TICKS", 0)) or 0)
            start_tick = None
            if lookback > 0:
                start_tick = max(0, int(getattr(sim.world, "tick", 0)) - lookback)
            events = historian.events_by_category(categories, limit=limit, start_tick=start_tick)
            if events:
                return events
        except Exception:
            pass
    cats = set(categories)
    return [event for event in getattr(sim.world, "events", []) if getattr(event, "category", "") in cats][-limit:]




def _historic_major_monster_lifecycle_events(sim, limit: int = 40):
    """Major non-goblin monster introductions/removals only; no movement noise."""
    categories = {
        "monster_spawn",
        "monster_old_age",
        "monster_kill",
        "legendary_monster_kill",
        "horror_pact",
        "horror_pact_failed",
        "horror_summon_failed",
    }
    events = _historian_category_events(sim, categories, limit=max(limit * 4, 100))
    keep = []
    for event in events:
        text = getattr(event, "text", "") or ""
        low = text.lower()
        if "goblin" in low:
            continue
        is_major = any(term in low for term in ("dragon", "giant", "ancient horror", "horror", "whispering maw", "sleeper below", "many-eyed tide", "void saint", "eldritch terror", "the nothing"))
        if not is_major:
            continue
        is_lifecycle = any(phrase in low for phrase in (
            "rumors spread of a",
            "descends upon",
            "awakens beneath",
            "summons",
            "slays",
            "fells",
            "destroys",
            "passes from the world",
            "merged with",  # harmless if absent; keeps future lifecycle phrasing flexible
        )) or getattr(event, "category", "") in {"monster_old_age", "legendary_monster_kill", "horror_pact", "horror_pact_failed"}
        if not is_lifecycle:
            continue
        keep.append(event)
    return keep[-limit:]

def _event_bucket(events):
    births, deaths, feats, monsters, parties, politics, retirements, immortals = [], [], [], [], [], [], [], []
    for event in events:
        cat = getattr(event, "category", "") or ""
        text = getattr(event, "text", "")
        low = text.lower()

        if cat in {"birth", "legacy_birth", "coming_of_age"}:
            births.append(event)
            continue
        if cat in {"notable_death", "champion_death"} or " dies " in low or low.startswith("an assassination plot"):
            deaths.append(event)
            continue
        if cat in {"retirement"} or " retires " in low or "lays down the adventurer's life" in low:
            retirements.append(event)
            continue
        if cat in {"monster_attack", "monster_spawn", "monster_retreat", "goblin_raid", "goblin_loyalty", "dragon_judgment", "legendary_monster_kill", "necromancer_crisis", "necromancer_crisis_check"} or any(
            term in low for term in ["dragon", "giant", "goblin", "ancient horror", "horror", "necromancer", "undead", "black host", "dead banners", "terrorizes", "brings ruin", "rumors spread of a"]
        ):
            monsters.append(event)
            continue
        if cat in {"party_coup", "party_split"} or "party forms" in low or "seizes control of" in low or "fractures" in low:
            parties.append(event)
            continue
        if cat in {"polity", "polity_challenge", "succession", "diplomacy", "corruption"} or any(
            term in low for term in ["kingdom of", "succeeds to the rule", "collapses after the death of its ruler", "subjugating", "claims ", "revolt tears", "preserves "]
        ):
            politics.append(event)
            continue
        if cat in {"champion", "champion_death", "recovery"} or any(
            term in low for term in ["champion of", "worship of", "fracture under its own weight", "shield", "curse", "god of chance", "lord of light", "lord of darkness"]
        ):
            immortals.append(event)
            continue
        feats.append(event)
    return births, deaths, feats, monsters, parties, politics, retirements, immortals




class _SummaryLabel:
    def __init__(self, value='', name=None):
        self.value = str(value or '-')
        self.name = str(name if name not in (None, '') else self.value).upper().replace(' ', '_')


class _AdventurerSnapshot:
    """Lightweight dead-actor record built from world.dead_actor_index.

    It deliberately mimics the tiny subset of Actor used by summary leaderboards
    so top adventurer lists do not hydrate full actors from the morgue.
    """
    def __init__(self, tomb):
        self._tomb = dict(tomb or {})
        self.id = self._safe_int('id', -1)
        self.name = str(self._tomb.get('name') or self._tomb.get('full_name') or self.id)
        self.alive = bool(self._tomb.get('alive', False))
        self.retired = bool(self._tomb.get('retired', False))
        self.role = _SummaryLabel(self._tomb.get('role', '-'), self._tomb.get('role_name'))
        self.alignment = _SummaryLabel(self._tomb.get('alignment', '-'), self._tomb.get('alignment_name'))
        self.deity = _SummaryLabel(self._tomb.get('deity', '-')) if self._tomb.get('deity') else None
        self.level = self._safe_int('level', 1)
        self.experience = self._safe_int('experience', 0)
        self.reputation = self._safe_int('reputation', 0)
        self.kills = self._safe_int('kills', 0)
        self.monster_kills = self._safe_int('monster_kills', 0)
        self.dragon_kills = self._safe_int('dragon_kills', 0)
        self.horror_kills = self._safe_int('horror_kills', 0)
        self.regions_oppressed = self._safe_int('regions_oppressed', 0)
        self.birth_day = self._tomb.get('birth_day')
        self.birth_month = self._tomb.get('birth_month')
        self.birth_year = self._tomb.get('birth_year')
        self.death_timestamp = self._tomb.get('death_timestamp')
        self.death_cause = self._tomb.get('death_cause')
        self.region_id = self._tomb.get('region_id')
        self.mother_id = self._tomb.get('mother_id')
        self.father_id = self._tomb.get('father_id')
        self.mother_label = self._tomb.get('mother_label')
        self.father_label = self._tomb.get('father_label')
        self.spouse_id = self._tomb.get('spouse_id')
        self.best_friend_id = self._tomb.get('best_friend_id')
        self.nemesis_id = self._tomb.get('nemesis_id')
        self.friend_ids = list(self._tomb.get('friend_ids') or [])

    def _safe_int(self, key, default=0):
        try:
            return int(self._tomb.get(key, default) or default)
        except Exception:
            return int(default)

    def full_name(self):
        return str(self._tomb.get('full_name') or self._tomb.get('name') or self.id)

    def short_name(self):
        return str(self._tomb.get('name') or self._tomb.get('full_name') or self.id)

    def is_adventurer(self):
        return str(self._tomb.get('role', '')).lower() != 'commoner'

    def power_rating(self):
        return self._safe_int('power_rating', self.level)

    def notable_deeds_summary(self):
        return str(self._tomb.get('notable_deeds') or '')


def _actor_from_tombstone(tomb):
    if not isinstance(tomb, dict):
        return None
    role = str(tomb.get('role', '') or '').lower()
    if role == 'commoner':
        return None
    return _AdventurerSnapshot(tomb)

def _is_adventurer_like(actor) -> bool:
    if actor is None:
        return False
    if hasattr(actor, "is_adventurer"):
        try:
            return bool(actor.is_adventurer())
        except Exception:
            pass
    role = getattr(actor, "role", None)
    role_name = str(getattr(role, "value", getattr(role, "name", role)) or "").lower()
    return role_name not in {"", "commoner"}


def _all_adventurer_records(sim):
    """Return living adventurers plus dead adventurer snapshots.

    Dead actors are read from ``world.dead_actor_index`` tombstones only. Do not
    call ``sim.resolve_actor`` here; summary leaderboards should not deserialize
    the morgue just to rebuild top lists.
    """
    world = sim.world
    records = []
    seen_ids = set()

    live_source = world.living_actors() if hasattr(world, "living_actors") else getattr(world, "actors", {}).values()
    for actor in live_source:
        if _is_adventurer_like(actor):
            records.append(actor)
            try:
                seen_ids.add(int(getattr(actor, "id", -1)))
            except Exception:
                pass

    dead_index = getattr(world, "dead_actor_index", {}) or {}
    for raw_id, tomb in dead_index.items():
        try:
            actor_id = int(raw_id)
        except Exception:
            actor_id = (tomb or {}).get("id") if isinstance(tomb, dict) else None
        if actor_id in seen_ids:
            continue
        actor = _actor_from_tombstone(tomb)
        if actor is not None and _is_adventurer_like(actor):
            records.append(actor)
            if actor_id is not None:
                seen_ids.add(actor_id)
    return records


def _actor_age_for_record(sim, actor) -> int:
    if getattr(actor, "alive", False):
        try:
            return int(sim._calculate_age(actor))
        except Exception:
            pass
    death_timestamp = getattr(actor, "death_timestamp", None)
    if death_timestamp:
        m = re.match(r"Year\s+(-?\d+),", str(death_timestamp))
        if m:
            return max(0, int(m.group(1)) - int(getattr(actor, "birth_year", 0) or 0))
    try:
        return int(sim._calculate_age(actor))
    except Exception:
        year, _, _, _, _ = sim.world.current_calendar()
        return max(0, int(year) - int(getattr(actor, "birth_year", 0) or 0))


def _top_adventurers(world, sim=None):
    if sim is not None:
        source = _all_adventurer_records(sim)
    else:
        source = world.living_actors() if hasattr(world, "living_actors") else world.actors.values()
    return sorted(
        [actor for actor in source if _is_adventurer_like(actor)],
        key=_adventurer_score,
        reverse=True,
    )




def _actor_ref_label(sim, world, actor_id, none_label: str = "None", include_id: bool = False) -> str:
    if actor_id is None:
        return none_label
    try:
        actor_id_int = int(actor_id)
    except Exception:
        return str(actor_id)
    actor = getattr(world, "actors", {}).get(actor_id_int)
    if actor is not None:
        if hasattr(actor, "short_name"):
            name = actor.short_name()
        elif hasattr(actor, "full_name"):
            name = actor.full_name()
        else:
            name = str(actor_id_int)
        return f"{name} ({actor_id_int})" if include_id else name
    tomb = (getattr(world, "dead_actor_index", {}) or {}).get(actor_id_int)
    if tomb:
        name = tomb.get("name") or tomb.get("short_name") or str(actor_id_int)
        return f"{name} ({actor_id_int})" if include_id else str(name)
    return f"Unknown actor ({actor_id_int})" if include_id else f"Unknown actor {actor_id_int}"




def _cult_status_label(cult) -> str:
    if getattr(cult, "formalized", False):
        return "formalized"
    if getattr(cult, "open_worship", False):
        return "open"
    if getattr(cult, "ascended", False):
        return "ascended"
    return "hidden"


def _cult_title_label(cult) -> str:
    title = str(getattr(cult, "public_title", "") or "").strip()
    if title:
        return title
    return str(getattr(cult, "name", "Unnamed Cult") or "Unnamed Cult")

def _actor_protocult(world, actor):
    """Return the actor's actual singular proto-cult membership.

    Falls back to old affinity-derived display only for older saves that do not
    yet have current_protocult_id populated.
    """
    if actor is None:
        return None, 0.0
    cults = getattr(world, "proto_cults", {}) or {}

    if actor_current_protocult is not None:
        cult = actor_current_protocult(world, actor)
        if cult is not None:
            cid = getattr(cult, "id", None)
            aff = getattr(actor, "cult_affinity", {}) or {}
            raw = aff.get(cid, aff.get(str(cid), 0.0)) if isinstance(aff, dict) else 0.0
            try:
                return cult, float(raw or 0.0)
            except Exception:
                return cult, 0.0

    cid = getattr(actor, "current_protocult_id", None)
    if cid is not None:
        cult = cults.get(cid)
        if cult is None:
            try:
                cult = cults.get(int(cid))
            except Exception:
                cult = None
        if cult is not None and not getattr(cult, "failed", False) and not getattr(cult, "formalized", False) and not getattr(cult, "ascended", False):
            aff = getattr(actor, "cult_affinity", {}) or {}
            raw = aff.get(cid, aff.get(str(cid), 0.0)) if isinstance(aff, dict) else 0.0
            try:
                return cult, float(raw or 0.0)
            except Exception:
                return cult, 0.0

    # Legacy fallback: before v48/v11/v6 there was no true membership field.
    aff_map = getattr(actor, "cult_affinity", {}) or {}
    best = None
    best_val = 0.0
    for cid, raw_val in aff_map.items():
        try:
            val = float(raw_val or 0.0)
        except Exception:
            val = 0.0
        if val <= best_val:
            continue
        cult = cults.get(cid)
        if cult is None:
            try:
                cult = cults.get(int(cid))
            except Exception:
                cult = None
        if cult is None or getattr(cult, "failed", False) or getattr(cult, "formalized", False) or getattr(cult, "ascended", False):
            continue
        best = cult
        best_val = val
    return best, best_val


def _actor_protocult_label(world, actor, none_label: str = "—", include_value: bool = False) -> str:
    cult, val = _actor_protocult(world, actor)
    if cult is None:
        return none_label
    label = _cult_title_label(cult)
    if include_value:
        return f"{label} ({val:.2f})"
    return label




def _faith_doubt_driver_label(actor, limit: int = 4) -> str:
    drivers = getattr(actor, "faith_doubt_drivers", {}) or {}
    if not isinstance(drivers, dict) or not drivers:
        return ""
    parts = []
    for key, value in sorted(drivers.items(), key=lambda item: float(item[1] or 0.0), reverse=True)[:limit]:
        try:
            val = float(value or 0.0)
        except Exception:
            continue
        if val <= 0.0:
            continue
        parts.append(f"{key}+{val:.3f}")
    return ("; drivers=" + ", ".join(parts)) if parts else ""

def _cult_for_actor(world, actor_id):
    try:
        actor_id = int(actor_id)
    except Exception:
        return None
    cults = getattr(world, "proto_cults", {}) or {}
    matches = [
        cult for cult in cults.values()
        if int(getattr(cult, "subject_actor_id", -1) or -1) == actor_id
        and not getattr(cult, "failed", False)
    ]
    if not matches:
        return None
    return max(matches, key=lambda cult: float(getattr(cult, "mythic_legacy_score", 0.0) or 0.0))


def _mythic_snapshot_for_actor(sim, world, actor_id):
    try:
        actor_id_int = int(actor_id)
    except Exception:
        actor_id_int = actor_id
    actor = getattr(world, "actors", {}).get(actor_id_int)

    score = float(getattr(actor, "mythic_legacy_score", 0.0) or 0.0) if actor is not None else 0.0
    profile = dict(getattr(actor, "mythic_legacy_profile", {}) or {}) if actor is not None else {}

    cult = _cult_for_actor(world, actor_id_int)
    cult_score = float(getattr(cult, "mythic_legacy_score", 0.0) or 0.0) if cult is not None else 0.0
    if score <= 0.0 and cult_score > 0.0:
        score = cult_score
        profile = dict(getattr(cult, "mythic_profile", {}) or {})
    elif cult_score > score:
        # Actor records can vanish into archive/tombstone paths; cults preserve the snapshot used for cult logic.
        score = cult_score
        if not profile:
            profile = dict(getattr(cult, "mythic_profile", {}) or {})

    return score, profile, cult


def _format_weight_map(weights, limit: int = 5) -> str:
    items = sorted((weights or {}).items(), key=lambda item: float(item[1]), reverse=True)[:limit]
    return ", ".join(f"{k}={float(v):.1f}" for k, v in items) if items else "-"


def _resource_snapshot_text(values, limit: int = 6) -> str:
    """Compact resource map for economy summary lines."""
    if not isinstance(values, dict) or not values:
        return "none"
    items = []
    for key in ("grain", "livestock", "wood", "metal", "weapons", "armor"):
        try:
            val = int(values.get(key, 0) or 0)
        except Exception:
            val = 0
        if val > 0:
            items.append(f"{key}={val}")
    return ", ".join(items[:limit]) if items else "none"

def _print_economy_summary(sim) -> None:
    world = sim.world
    _print_section("ECONOMY AND TRADE")
    regions = list((getattr(world, "regions", {}) or {}).values())
    if not regions:
        print("  No regions.")
        print()
        return
    stressed = sorted(
        regions,
        key=lambda r: int(getattr(r, "economy_shortage_pressure", 0) or 0),
        reverse=True,
    )[:8]
    if any(int(getattr(r, "economy_shortage_pressure", 0) or 0) > 0 for r in stressed):
        print("Regional shortages:")
        for region in stressed:
            pressure = int(getattr(region, "economy_shortage_pressure", 0) or 0)
            if pressure <= 0:
                continue
            print(f"  {getattr(region, 'name', region.id)} — pressure={pressure}; deficits={_resource_snapshot_text(getattr(region, 'economy_deficit', {}) or {})}; imports={_resource_snapshot_text(getattr(region, 'economy_imports', {}) or {})}")
    else:
        print("Regional shortages: none significant.")

    polities = list((getattr(world, "polities", {}) or {}).values())
    if polities:
        print("Polity economies:")
        ranked = sorted(
            polities,
            key=lambda p: (int(getattr(p, "shortage_pressure", 0) or 0), sum(int(v or 0) for v in (getattr(p, "trade_imports", {}) or {}).values()), len(getattr(p, "region_ids", []) or [])),
            reverse=True,
        )[:10]
        for polity in ranked:
            imports = getattr(polity, "trade_imports", {}) or {}
            exports = getattr(polity, "trade_exports", {}) or {}
            deficits = getattr(polity, "economic_deficit", {}) or {}
            surplus = getattr(polity, "economic_surplus", {}) or {}
            dependency = int(getattr(polity, "trade_dependency_score", 0) or 0)
            pressure = int(getattr(polity, "shortage_pressure", 0) or 0)
            partners = []
            for pid, vol in sorted((getattr(polity, "economic_trade_partners", {}) or {}).items(), key=lambda item: int(item[1] or 0), reverse=True)[:4]:
                other = getattr(world, "polities", {}).get(pid)
                if other is not None:
                    partners.append(f"{other.name}:{int(vol or 0)}")
            print(f"  {polity.name} — dependency={dependency}% shortage={pressure}; imports={_resource_snapshot_text(imports)}; exports={_resource_snapshot_text(exports)}")
            print(f"    deficits={_resource_snapshot_text(deficits)} | surplus={_resource_snapshot_text(surplus)} | trade_partners={', '.join(partners) if partners else 'none'}")
    print()


def _legendarium_base_name(seed: str, label: str) -> str:
    return f"legendarium_{_safe_filename_part(seed)}_{_safe_filename_part(label)}year"

def _actor_parent_label(world, actor, side: str, sim=None) -> str:
    parent_id = getattr(actor, f"{side}_id", None)
    if parent_id is not None:
        return _actor_ref_label(sim, world, parent_id, none_label="Unknown", include_id=True)
    label = getattr(actor, f"{side}_label", None)
    if label:
        return str(label)
    return "Unknown"


def _sparkline(values, width: int = 72) -> str:
    if not values:
        return ""
    values = list(values)
    if len(values) > width:
        step = len(values) / float(width)
        values = [values[int(i * step)] for i in range(width)]
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return "─" * len(values)
    chars = "▁▂▃▄▅▆▇█"
    span = hi - lo
    out = []
    for value in values:
        idx = int(round((float(value) - lo) / span * (len(chars) - 1)))
        idx = max(0, min(idx, len(chars) - 1))
        out.append(chars[idx])
    return "".join(out)


def _print_history_graphs(sim) -> None:
    world = sim.world
    history = getattr(world, "history", None)
    if not history:
        print("No history samples recorded.")
        return
    ticks = history.get("tick", [])
    if ticks:
        print(f"Samples: {len(ticks)}  tick range: {ticks[0]} -> {ticks[-1]}")
    for key, label in (("total_population", "Population"), ("adventurers", "Adventurers"), ("monsters", "Monsters")):
        values = history.get(key, [])
        if not values:
            print(f"{label}: no samples")
            continue
        print(f"{label}: min={min(values)} max={max(values)} last={values[-1]}")
        print(f"  {_sparkline(values)}")


def _print_parentage_audit(sim) -> None:
    world = sim.world
    actors = list(getattr(world, "actors", {}).values())
    known = []
    labeled = []
    missing_backlinks = []
    for actor in actors:
        if getattr(actor, "mother_id", None) is not None or getattr(actor, "father_id", None) is not None:
            known.append(actor)
            for side in ("mother", "father"):
                parent_id = getattr(actor, f"{side}_id", None)
                if parent_id is None:
                    continue
                parent = world.actors.get(parent_id)
                if parent is not None and actor.id not in (getattr(parent, "children_ids", []) or []):
                    missing_backlinks.append((actor.id, side, parent_id))
        elif getattr(actor, "mother_label", None) or getattr(actor, "father_label", None):
            labeled.append(actor)
    print(f"Actors with explicit actor parents: {len(known)}")
    print(f"Actors with labeled non-actor parentage: {len(labeled)}")
    print(f"Missing parent children_ids back-links: {len(missing_backlinks)}")
    if missing_backlinks[:5]:
        print("Sample missing back-links:")
        for child_id, side, parent_id in missing_backlinks[:5]:
            print(f"  child {child_id}: absent from {side} {parent_id}'s children_ids")



def _print_lore_profiler(sim, limit: int = 12) -> None:
    world = sim.world
    records = list(getattr(world, "lore_profile_records", []) or [])
    _print_section("LORE PROFILER")
    if not records:
        print("  No lore profiler records captured.")
        print("  Ensure LORE_PROFILING_ENABLED = True and at least one lore tick has fired.")
        print()
        return

    print(f"Recent lore ticks captured: {len(records)}")
    slowest = sorted(records, key=lambda r: float(r.get("total_seconds", 0.0) or 0.0), reverse=True)[:max(1, int(limit))]
    print("Slowest recent lore ticks:")
    for rec in slowest:
        tick = int(rec.get("tick", 0) or 0)
        total = float(rec.get("total_seconds", 0.0) or 0.0)
        songs = int(rec.get("songs", 0) or 0)
        cults = int(rec.get("proto_cults", 0) or 0)
        bards = int(rec.get("living_bards", 0) or 0)
        print(f"  tick={tick} total={total:.3f}s songs={songs} proto_cults={cults} living_bards={bards}")
        stages = sorted(list(rec.get("stages", []) or []), key=lambda item: float(item[1] or 0.0), reverse=True)
        if stages:
            bits = [f"{name}={float(seconds):.3f}s" for name, seconds in stages]
            print("    " + "; ".join(bits))
    # Aggregate totals across captured records to expose recurring offenders.
    aggregate = {}
    counts = {}
    for rec in records:
        for name, seconds in list(rec.get("stages", []) or []):
            aggregate[name] = aggregate.get(name, 0.0) + float(seconds or 0.0)
            counts[name] = counts.get(name, 0) + 1
    if aggregate:
        print("Aggregate captured stage time:")
        for name, total in sorted(aggregate.items(), key=lambda item: item[1], reverse=True):
            avg = total / max(1, counts.get(name, 1))
            print(f"  {name:24} total={total:.3f}s avg={avg:.3f}s n={counts.get(name, 0)}")
    print()



def _print_adventurer_block(world, sim, title, adventurers, limit):
    print(f"\n{title}")
    print("  |------------------------------------------------------------------")
    for actor in adventurers[:limit]:
        spouse_label = _actor_ref_label(sim, world, getattr(actor, "spouse_id", None))
        bff_label = _actor_ref_label(sim, world, getattr(actor, "best_friend_id", None))
        friend_count = len(getattr(actor, "friend_ids", []) or [])
        nemesis_label = _actor_ref_label(sim, world, getattr(actor, "nemesis_id", None))
        retired = getattr(actor, "retired", False)
        print(f"  | {actor.full_name()}")
        deity_label = getattr(getattr(actor, "deity", None), "value", getattr(getattr(actor, "deity", None), "name", getattr(actor, "deity", "-")))
        print(f"  |   role={actor.role.value}  alignment={actor.alignment.name}")
        print(f"  |   religion={deity_label}")
        print(f"  |   protocult={_actor_protocult_label(world, actor)}")
        print(f"  |   lvl={getattr(actor, 'level', 1)}  rep={actor.reputation}  xp={getattr(actor, 'experience', 0)}")
        print(f"  |   kills={actor.kills}  mkills={actor.monster_kills}  dragons={actor.dragon_kills}  horrors={actor.horror_kills}")
        print(f"  |   Born: {_short_birth_date(sim, world, actor)}")
        print(f"  |   parents={_actor_parent_label(world, actor, 'mother', sim)} / {_actor_parent_label(world, actor, 'father', sim)}")
        print(f"  |   Died: {_death_line(actor)}")
        print(f"  |   spouse={spouse_label}  bfForever={bff_label}  nemesis={nemesis_label}")
        status = "living" if actor.alive else "dead"
        if retired and actor.alive:
            status += " retired"
        print(f"  |   status={status}  region={world.region_name(actor.region_id)}")
        print("  |------------------------------------------------------------------")



def _living_adventurer_records(world):
    """Living-only adventurer records for current-authority legendarium views.

    This intentionally avoids the all-time morgue/hall-of-fame records used by
    the main summary. These lists answer: who matters in the world right now?
    """
    live_source = world.living_actors() if hasattr(world, "living_actors") else getattr(world, "actors", {}).values()
    return [actor for actor in live_source if getattr(actor, "alive", False) and _is_adventurer_like(actor)]


def _actor_sort_key_for_current_authority(actor):
    return (
        getattr(actor, "reputation", 0),
        getattr(actor, "dragon_kills", 0),
        getattr(actor, "horror_kills", 0),
        getattr(actor, "monster_kills", 0),
        getattr(actor, "kills", 0),
        getattr(actor, "level", 1),
        actor.power_rating() if hasattr(actor, "power_rating") else 0,
    )


def _unique_living_actors_by_id(world, actor_ids):
    actors = []
    seen = set()
    actor_map = getattr(world, "actors", {}) or {}
    for raw_id in actor_ids:
        try:
            actor_id = int(raw_id)
        except Exception:
            continue
        if actor_id in seen:
            continue
        actor = actor_map.get(actor_id)
        if actor is None or not getattr(actor, "alive", False):
            continue
        seen.add(actor_id)
        actors.append(actor)
    return actors


def _living_ruler_and_spouse_records(world):
    ids = []
    for polity in (getattr(world, "polities", {}) or {}).values():
        ruler_id = getattr(polity, "ruler_id", None)
        if ruler_id is not None:
            ids.append(ruler_id)
            ruler = getattr(world, "actors", {}).get(ruler_id)
            spouse_id = getattr(ruler, "spouse_id", None) if ruler is not None else None
            if spouse_id is not None:
                ids.append(spouse_id)
    for region in (getattr(world, "regions", {}) or {}).values():
        ruler_id = getattr(region, "ruler_id", None)
        if ruler_id is not None:
            ids.append(ruler_id)
            ruler = getattr(world, "actors", {}).get(ruler_id)
            spouse_id = getattr(ruler, "spouse_id", None) if ruler is not None else None
            if spouse_id is not None:
                ids.append(spouse_id)
    return _unique_living_actors_by_id(world, ids)


def _living_party_leader_records(world):
    ids = []
    for party in (getattr(world, "parties", {}) or {}).values():
        leader_id = getattr(party, "leader_id", None)
        if leader_id is not None:
            ids.append(leader_id)
    actors = _unique_living_actors_by_id(world, ids)
    return [a for a in actors if _is_adventurer_like(a)]


def _living_champion_records(world):
    live_source = world.living_actors() if hasattr(world, "living_actors") else getattr(world, "actors", {}).values()
    return [actor for actor in live_source if getattr(actor, "alive", False) and getattr(actor, "champion_of", None) is not None]



def _actor_polity_roles(world, actor):
    """Return current polity roles and related polity objects for a living actor."""
    roles = []
    polities = []
    actor_id = getattr(actor, "id", None)
    spouse_synergy = False
    if actor_id is None:
        return roles, polities, spouse_synergy
    for polity in (getattr(world, "polities", {}) or {}).values():
        ruler_id = getattr(polity, "ruler_id", None)
        if actor_id == ruler_id:
            roles.append(f"ruler of {getattr(polity, 'name', 'a polity')}")
            polities.append(polity)
            spouse_id = getattr(actor, "spouse_id", None)
            spouse = getattr(world, "actors", {}).get(spouse_id) if spouse_id is not None else None
            # Synergy is cult-specific and is checked in _compute_religious_clout.
        else:
            ruler = getattr(world, "actors", {}).get(ruler_id)
            if ruler is not None and getattr(ruler, "spouse_id", None) == actor_id:
                roles.append(f"spouse of ruler of {getattr(polity, 'name', 'a polity')}")
                polities.append(polity)
        if actor_id in (getattr(polity, "general_ids", []) or []) or actor_id == getattr(polity, "general_id", None):
            roles.append(f"general of {getattr(polity, 'name', 'a polity')}")
            polities.append(polity)
        if actor_id in (getattr(polity, "captain_ids", []) or []):
            roles.append(f"captain of {getattr(polity, 'name', 'a polity')}")
            polities.append(polity)
    # Deduplicate while preserving order.
    clean_roles = []
    seen = set()
    for role in roles:
        if role not in seen:
            seen.add(role)
            clean_roles.append(role)
    clean_polities = []
    seenp = set()
    for pol in polities:
        pid = getattr(pol, "id", id(pol))
        if pid not in seenp:
            seenp.add(pid)
            clean_polities.append(pol)
    return clean_roles, clean_polities, spouse_synergy


def _actor_party_leadership(world, actor):
    actor_id = getattr(actor, "id", None)
    if actor_id is None:
        return None, 0
    for party in (getattr(world, "parties", {}) or {}).values():
        if getattr(party, "leader_id", None) == actor_id:
            return party, len(getattr(party, "member_ids", []) or [])
    return None, 0


def _actor_relics_held(world, actor):
    actor_id = getattr(actor, "id", None)
    if actor_id is None:
        return []
    held = []
    for relic in (getattr(world, "relics", {}) or {}).values():
        if getattr(relic, "holder_id", None) == actor_id:
            held.append(relic)
    return held


def _best_polity_strength(polity) -> float:
    # Prefer current strength if available, then peak strength, then region count / stability / legitimacy.
    strength = float(getattr(polity, "strength", 0) or 0)
    peak = float(getattr(polity, "peak_strength", 0) or 0)
    regions = len(getattr(polity, "region_ids", []) or [])
    stability = float(getattr(polity, "stability", 0) or 0)
    legitimacy = float(getattr(polity, "legitimacy", 0) or 0)
    return max(strength, peak, regions * 1000.0 + stability * 10.0 + legitimacy * 10.0)


def _compute_religious_clout(actor, world, cult=None):
    """Compute on-demand religious clout for inspection/godbirth tuning.

    This is deliberately not stored on Actor. It is a reporting calculation for:
    who could plausibly disavow an established god and pull others into a new faith?
    """
    if actor is None or not getattr(actor, "alive", False) or getattr(actor, "in_school", False):
        return 0.0, []
    score = 0.0
    parts = []

    def add(label, value):
        nonlocal score
        value = float(value or 0.0)
        if value <= 0.0:
            return
        score += value
        parts.append(f"{label}+{value:.1f}")

    roles, polities, _ = _actor_polity_roles(world, actor)
    role_text = " ".join(roles).lower()
    if "ruler of" in role_text:
        add("ruler", 80)
    if "spouse of ruler" in role_text:
        add("ruler-spouse", 50)
    if "general of" in role_text:
        add("general", 35)
    if "captain of" in role_text:
        add("captain", 25)

    if getattr(actor, "champion_of", None) is not None:
        add("champion", 65)

    party, party_size = _actor_party_leadership(world, actor)
    if party is not None:
        add("party-leader", 25)
        add("party-size", min(35, party_size * 0.5))

    relics = _actor_relics_held(world, actor)
    if relics:
        add("relic-bearer", 35 + min(25, (len(relics) - 1) * 10))

    add("reputation", min(80, float(getattr(actor, "reputation", 0) or 0) * 0.8))
    add("level", min(30, float(getattr(actor, "level", 1) or 1) * 3.0))
    add("xp", min(25, float(getattr(actor, "experience", 0) or 0) / 250.0))
    add("monster-kills", min(30, float(getattr(actor, "monster_kills", 0) or 0) * 1.5))
    add("dragon-kills", float(getattr(actor, "dragon_kills", 0) or 0) * 30.0)
    add("horror-kills", float(getattr(actor, "horror_kills", 0) or 0) * 45.0)

    # State backing modifies clout. For rulers/spouses this represents institutional force;
    # for non-rulers it is only an amplifier/suppressor.
    if polities:
        strongest = max(polities, key=_best_polity_strength)
        strength = _best_polity_strength(strongest)
        stability = float(getattr(strongest, "stability", 0) or 0)
        legitimacy = float(getattr(strongest, "legitimacy", 0) or 0)
        regions = len(getattr(strongest, "region_ids", []) or [])
        institutional = min(45.0, strength / 400.0) + min(20.0, stability / 5.0) + min(20.0, legitimacy / 5.0) + min(15.0, regions * 5.0)
        if "ruler of" in role_text or "spouse of ruler" in role_text:
            add("state-backing", institutional)
        else:
            add("state-modifier", institutional * 0.45)

    # Theodora/Justinian effect: ruler and spouse both attached to same cult.
    if cult is not None and roles:
        cult_id = getattr(cult, "id", None)
        actor_id = getattr(actor, "id", None)
        for pol in polities:
            ruler = getattr(world, "actors", {}).get(getattr(pol, "ruler_id", None))
            if ruler is None:
                continue
            spouse_id = getattr(ruler, "spouse_id", None)
            spouse = getattr(world, "actors", {}).get(spouse_id) if spouse_id is not None else None
            if spouse is None:
                continue
            pair = [ruler, spouse]
            if actor not in pair:
                continue
            both = True
            for member in pair:
                aff = getattr(member, "cult_affinity", {}) or {}
                val = aff.get(cult_id, aff.get(str(cult_id), 0.0))
                try:
                    val = float(val or 0.0)
                except Exception:
                    val = 0.0
                if val < 0.50:
                    both = False
                    break
            if both:
                add("ruling-household", 40)
                break

    return score, parts


def _cult_gate_snapshot(cult):
    pressure = float(getattr(cult, "legend_pressure", 0.0) or 0.0)
    mythic = float(getattr(cult, "mythic_legacy_score", 0.0) or 0.0)
    regions = len(getattr(cult, "known_region_ids", set()) or set())
    return pressure, mythic, regions


def _potential_religious_catalyst_rows(sim, limit=25):
    if hasattr(sim, "_apotheosis_candidate_rows"):
        try:
            rows = sim._apotheosis_candidate_rows(limit=limit)
            out = []
            for row in rows:
                cult = row.get("cult")
                gate = row.get("gate", {})
                out.append((
                    float(row.get("readiness", 0.0) or 0.0),
                    row.get("actor"),
                    cult,
                    float(row.get("affinity", 0.0) or 0.0),
                    float(row.get("doubt", 0.0) or 0.0),
                    float(row.get("clout", 0.0) or 0.0),
                    list(row.get("parts", []) or []),
                    float(gate.get("pressure", getattr(cult, "legend_pressure", 0.0)) or 0.0),
                    float(gate.get("mythic", getattr(cult, "mythic_legacy_score", 0.0)) or 0.0),
                    int(gate.get("regions", len(getattr(cult, "known_region_ids", set()) or set())) or 0),
                    bool(row.get("eligible", False)),
                    gate,
                ))
            return out[:limit]
        except Exception:
            pass

    world = sim.world
    cults = [c for c in (getattr(world, "proto_cults", {}) or {}).values() if not getattr(c, "failed", False) and not getattr(c, "formalized", False)]
    living = list(world.living_actors()) if hasattr(world, "living_actors") else list(getattr(world, "actors", {}).values())
    rows = []
    for actor in living:
        if not getattr(actor, "alive", False) or getattr(actor, "in_school", False) or not _is_adventurer_like(actor):
            continue
        aff_map = getattr(actor, "cult_affinity", {}) or {}
        doubt = float(getattr(actor, "faith_doubt", 0.0) or 0.0)
        if not aff_map and doubt <= 0.0:
            continue
        for cult in cults:
            cid = getattr(cult, "id", None)
            aff = aff_map.get(cid, aff_map.get(str(cid), 0.0))
            try:
                aff = float(aff or 0.0)
            except Exception:
                aff = 0.0
            if aff <= 0.0 and doubt <= 0.0:
                continue
            clout, parts = _compute_religious_clout(actor, world, cult)
            pressure, mythic, regions = _cult_gate_snapshot(cult)
            readiness = (aff * 100.0) + (doubt * 100.0) + clout + min(100.0, pressure / 2500.0) + min(100.0, mythic / 10.0) + min(40.0, regions * 4.0)
            rows.append((readiness, actor, cult, aff, doubt, clout, parts, pressure, mythic, regions, False, {}))
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows[:limit]

def _print_potential_religious_catalysts(sim, limit: int = 25) -> None:
    _print_section("POTENTIAL RELIGIOUS CATALYSTS")
    rows = _potential_religious_catalyst_rows(sim, limit=limit)
    if not rows:
        print("None. No living actors currently combine faith doubt or cult affinity with measurable clout.")
        print()
        return
    world = sim.world
    for readiness, actor, cult, aff, doubt, clout, parts, pressure, mythic, regions, eligible, gate in rows:
        deity = getattr(getattr(actor, "deity", None), "value", getattr(getattr(actor, "deity", None), "name", getattr(actor, "deity", "-")))
        print(f"{_actor_ref_label(sim, world, getattr(actor, 'id', None), include_id=True)} -> {_cult_title_label(cult)}")
        pc_years = protocult_duration_years(world, actor)
        pc_dur = f"; pc_years={pc_years:.1f}" if pc_years > 0 else ""
        status = "ELIGIBLE" if eligible else "watch"
        print(f"  religion={deity}; protocult={_actor_protocult_label(world, actor)}{pc_dur}; doubt={doubt:.2f}; affinity={aff:.2f}; clout={clout:.1f}; readiness={readiness:.1f}; status={status}")
        if gate:
            print(f"  cult_gate: members={int(gate.get('members', 0))}; affinity_mass={float(gate.get('affinity_mass', 0.0)):.1f}; pressure={pressure:.1f}; mythic={mythic:.1f}; regions={regions}; age={float(gate.get('age_years', 0.0)):.1f}; cult_status={_cult_status_label(cult)}")
        else:
            print(f"  cult_gate: pressure={pressure:.1f}; mythic={mythic:.1f}; regions={regions}; cult_status={_cult_status_label(cult)}")
        print(f"  clout_parts: {', '.join(parts[:12]) if parts else '-'}")
    print()


def _print_living_authority_legendarium(sim) -> None:
    """Mirror the all-time summary lists with living-only lists for cult/godbirth review."""
    world = sim.world
    living_adv = sorted(_living_adventurer_records(world), key=_actor_sort_key_for_current_authority, reverse=True)
    _print_section("LIVING AUTHORITY AND ADVENTURER LISTS")
    if not living_adv:
        print("No living adventurers.")
        print()
        return

    _print_adventurer_block(world, sim, "Top 25 living adventurers:", living_adv, 25)

    for role_name in ("FIGHTER", "WARDEN", "WIZARD", "BARD"):
        role = getattr(sim.Role, role_name, None)
        if role is None:
            continue
        role_adv = [a for a in living_adv if getattr(a, "role", None) == role]
        _print_adventurer_block(world, sim, f"Top 10 living {role.value}s:", role_adv, 10)

    champions = sorted(_living_champion_records(world), key=_actor_sort_key_for_current_authority, reverse=True)
    if champions:
        _print_adventurer_block(world, sim, "Top 10 living champions:", champions, 10)
    else:
        print("\nTop 10 living champions:")
        print("  None.")

    rulers = sorted(_living_ruler_and_spouse_records(world), key=_actor_sort_key_for_current_authority, reverse=True)
    if rulers:
        _print_adventurer_block(world, sim, "Top 10 living rulers and ruler spouses:", rulers, 10)
    else:
        print("\nTop 10 living rulers and ruler spouses:")
        print("  None.")

    party_leaders = sorted(_living_party_leader_records(world), key=_actor_sort_key_for_current_authority, reverse=True)
    if party_leaders:
        _print_adventurer_block(world, sim, "Top 10 living party leaders:", party_leaders, 10)
    else:
        print("\nTop 10 living party leaders:")
        print("  None.")
    print()

def _tick_to_short_date(sim, tick: Optional[int]) -> str:
    if tick is None:
        return "Unknown"
    tick = int(tick)
    tod_count = len(getattr(sim, "TIME_OF_DAY", ["Morning", "Midday", "Evening", "Night"]))
    ticks_per_day = max(1, int(getattr(sim, "TICKS_PER_DAY", tod_count) or tod_count))
    day_index = tick // ticks_per_day
    year = day_index // 360 + 1
    day_of_year = day_index % 360
    month = day_of_year // 30 + 1
    day = day_of_year % 30 + 1
    return _short_date_from_parts(day, month, year, _month_names(sim, sim.world))




def _format_leader_term(sim, leader, current_tick: Optional[int] = None) -> str:
    start = getattr(leader, "start_tick", None)
    end = getattr(leader, "end_tick", None)
    if start is None and end is None:
        return ""
    start_text = _tick_to_short_date(sim, start) if start is not None else "?"
    end_text = "present" if end is None else _tick_to_short_date(sim, end)
    return f"{start_text}–{end_text}"


def _format_leader_claim(leader) -> str:
    claim = str(getattr(leader, "claim_type", "") or "").strip()
    predecessor = str(getattr(leader, "predecessor", "") or "").strip()
    bits = []
    if claim and claim.lower() not in {"founder", "unknown"}:
        bits.append(f"{claim} claim")
    elif claim.lower() == "founder":
        bits.append("founder")
    if predecessor and predecessor.lower() not in {"unknown", "its fallen ruler"}:
        bits.append(f"after {predecessor}")
    return f" ({', '.join(bits)})" if bits else ""

def _print_event_list(title, events, limit):
    print(title)
    if not events:
        print("  None.")
        print()
        return
    for event in events[-limit:]:
        print(f"  [{event.timestamp}] {event.text}")
    print()


def _story_note_sort_key(sim, note: str) -> Tuple[int, int, int, int, int]:
    match = re.match(r"\[Year\s+(-?\d+),\s+[^,]+,\s+([A-Za-z]+)\s+(\d+),\s+([A-Za-z]+)\]", str(note))
    if not match:
        return (-999999, 0, 0, 0, 0)
    year = int(match.group(1))
    month_name = match.group(2)
    day = int(match.group(3))
    tod = match.group(4)
    month_names = _month_names(sim, sim.world)
    try:
        month = month_names.index(month_name) + 1
    except ValueError:
        month = 0
    tod_index = {"Morning": 0, "Midday": 1, "Evening": 2, "Night": 3}.get(tod, 0)
    return (year, month, day, tod_index, 0)


def _story_note_parts(note: str) -> Tuple[str, str]:
    match = re.match(r"^(\[[^\]]+\])\s*(.*)$", str(note))
    if not match:
        return ("[Unknown]", str(note))
    return match.group(1), match.group(2).strip()


def _is_high_level_story_note(note_text: str) -> bool:
    low = note_text.lower().strip()
    if not low:
        return False
    ignored_prefixes = (
        "entered the world",
        "now has ",
    )
    if low.startswith(ignored_prefixes):
        return False
    ignored_fragments = (
        "region visit",
        "travel",
        "moved to",
        "set out for",
    )
    return not any(fragment in low for fragment in ignored_fragments)


def _main_character_actions(sim, limit: int = 20) -> List[Tuple[Tuple[int, int, int, int, int], str]]:
    world = sim.world
    actions: List[Tuple[Tuple[int, int, int, int, int], str]] = []
    story_actors = [
        actor for actor in world.actors.values()
        if getattr(actor, "is_story_actor", False)
        and str(getattr(actor, "story_status", "active")).lower() not in {"inactive", "disabled"}
    ]
    for actor in story_actors:
        for note in getattr(actor, "story_notes", []) or []:
            stamp, body = _story_note_parts(note)
            if not _is_high_level_story_note(body):
                continue
            actor_name = actor.full_name() if hasattr(actor, "full_name") else getattr(actor, "name", "Unknown")
            actions.append((_story_note_sort_key(sim, note), f"  {stamp} {actor_name}: {body}"))
    actions.sort(key=lambda item: item[0])
    return actions[-limit:]


def _print_main_character_actions(sim, limit: int = 20) -> None:
    _print_section("MAIN CHARACTER ACTIONS")
    actions = _main_character_actions(sim, limit)
    if not actions:
        print("  None.")
        print()
        return
    for _key, line in actions:
        print(line)
    print()


def _print_bard_repertoire_summary(sim) -> None:
    world = sim.world
    bards = [
        actor for actor in world.living_actors()
        if getattr(getattr(actor, "role", None), "name", "") == "BARD"
        or getattr(getattr(actor, "role", None), "value", "") == "Bard"
    ]
    songs = [song for song in getattr(world, "songs", {}).values() if not getattr(song, "forgotten", False)]
    if not bards or not songs:
        return
    chart_count = int(globals().get("TOP_SONG_CHART_COUNT", 10) or 10)
    top_songs = sorted(
        songs,
        key=lambda song: (
            float(getattr(song, "popularity", 0.0) or 0.0),
            float(getattr(song, "historical_weight", 0.0) or 0.0),
            int(getattr(song, "performances", 0) or 0),
        ),
        reverse=True,
    )[:chart_count]
    top_ids = {int(getattr(song, "id", -1) or -1) for song in top_songs}
    known_counts = []
    top_known_counts = []
    empty = 0
    for bard in bards:
        known = set()
        for raw in getattr(bard, "known_song_ids", []) or []:
            try:
                known.add(int(raw))
            except Exception:
                continue
        known_counts.append(len(known))
        top_known_counts.append(len(known.intersection(top_ids)))
        if not known:
            empty += 1
    avg_known = sum(known_counts) / len(known_counts) if known_counts else 0.0
    avg_top = sum(top_known_counts) / len(top_known_counts) if top_known_counts else 0.0
    target_min = int(globals().get("BARD_TOP_SONG_TARGET_MIN", 5) or 5)
    fully_literate = len([n for n in top_known_counts if n >= target_min])
    print("Bard repertoire:")
    print(f"  living_bards={len(bards)} avg_known={avg_known:.1f} avg_top{chart_count}_known={avg_top:.1f} empty_repertoires={empty}")
    print(f"  bards_at_min_top_standard={fully_literate}/{len(bards)} target_min={target_min}")
    if top_songs:
        spread = []
        for song in top_songs[:5]:
            sid = int(getattr(song, "id", -1) or -1)
            knowers = 0
            for bard in bards:
                try:
                    ids = {int(x) for x in (getattr(bard, "known_song_ids", []) or [])}
                except Exception:
                    ids = set()
                if sid in ids:
                    knowers += 1
            spread.append(f"{getattr(song, 'title', 'Untitled')}={knowers}")
        print("  top-song bard literacy: " + "; ".join(spread))

def _print_lore_summary(sim) -> None:
    world = sim.world
    _print_section("LORE AND LIVING MEMORY")
    songs = [song for song in getattr(world, "songs", {}).values() if not getattr(song, "forgotten", False)]
    if not songs:
        print("  No songs have entered living memory yet.")
    else:
        print("Top remembered songs:")
        ranked = sorted(
            songs,
            key=lambda song: (float(getattr(song, "historical_weight", 0.0)), float(getattr(song, "popularity", 0.0)), int(getattr(song, "performances", 0))),
            reverse=True,
        )[:10]
        for song in ranked:
            subjects = []
            for aid in getattr(song, "subject_actor_ids", []) or []:
                subjects.append(_actor_ref_label(sim, world, aid))
            relic_id = getattr(song, "subject_relic_id", None)
            if relic_id is not None:
                relic = getattr(world, "relics", {}).get(relic_id)
                subjects.append(getattr(relic, "name", f"relic {relic_id}"))
            subject_text = ", ".join(subjects) if subjects else (getattr(song, "subject_event", "") or "Unknown")
            composer = _actor_ref_label(sim, world, getattr(song, "composer_id", None), none_label="Unknown")
            regions = len(getattr(song, "known_region_ids", set()) or set())
            visibility = str(getattr(song, "visibility", "public") or "public")
            fame_credit = ""
            if visibility.lower() == "private":
                fame_actor = _actor_ref_label(sim, world, getattr(song, "fame_credit_actor_id", None) or getattr(song, "composer_id", None), none_label="Unknown")
                fame_credit = f"; fame_credit={fame_actor}"
            subject_deity = getattr(song, "subject_deity", None)
            if subject_deity is not None:
                subject_text = getattr(subject_deity, "value", getattr(subject_deity, "name", str(subject_deity)))
            print(f"  {getattr(song, 'title', 'Untitled')} — visibility={visibility}; subject={subject_text}; composer={composer}; pop={float(getattr(song, 'popularity', 0.0)):.1f}; weight={float(getattr(song, 'historical_weight', 0.0)):.1f}; regions={regions}; bards={len(getattr(song, 'performer_actor_ids', set()) or set())}; age={int(getattr(song, 'age_years', 0))}y{fame_credit}")
        old = sorted(songs, key=lambda song: int(getattr(song, "age_years", 0)), reverse=True)[:5]
        if old:
            print("Oldest surviving songs:")
            for song in old:
                print(f"  {getattr(song, 'title', 'Untitled')} — visibility={getattr(song, 'visibility', 'public')}; age={int(getattr(song, 'age_years', 0))}y; pop={float(getattr(song, 'popularity', 0.0)):.1f}; performances={int(getattr(song, 'performances', 0))}")
    _print_bard_repertoire_summary(sim)
    legends = sorted((getattr(world, "legend_pressure_by_actor_id", {}) or {}).items(), key=lambda item: float(item[1]), reverse=True)[:10]
    if legends:
        print("Strongest remembered figures:")
        for actor_id, pressure in legends:
            legacy, profile, cult = _mythic_snapshot_for_actor(sim, world, actor_id)
            axes = ", ".join(f"{k}={float(v):.0f}" for k, v in sorted((profile or {}).items(), key=lambda item: float(item[1]), reverse=True)[:3])
            title = _cult_title_label(cult) if cult is not None else ""
            suffix = f"; mythic={legacy:.1f}" + (f" ({axes})" if axes else "") + (f"; archetype={title}" if title else "")
            print(f"  {_actor_ref_label(sim, world, actor_id)} — legend_pressure={float(pressure):.1f}{suffix}")
    cults = [c for c in getattr(world, "proto_cults", {}).values() if not getattr(c, "failed", False)]
    if cults:
        print("Proto-cults and ascended memories:")
        for cult in sorted(cults, key=lambda c: (bool(getattr(c, "ascended", False)), float(getattr(c, "legend_pressure", 0.0))), reverse=True)[:10]:
            status = _cult_status_label(cult)
            regions = len(getattr(cult, "known_region_ids", set()) or set())
            hidden = sum(int(v) for v in (getattr(cult, "hidden_commoner_affinity_by_region", {}) or {}).values())
            title = getattr(cult, "public_title", "") or "-"
            mythic = float(getattr(cult, "mythic_legacy_score", 0.0) or 0.0)
            domains = ",".join(k for k, _v in sorted((getattr(cult, "domain_weights", {}) or {}).items(), key=lambda item: float(item[1]), reverse=True)[:3]) or "-"
            actor_aff = len(getattr(cult, "hidden_affinity_by_actor_id", {}) or {})
            open_note = ""
            if getattr(cult, "open_worship", False):
                catalyst = getattr(cult, "open_worship_actor_name", "") or "unknown catalyst"
                reason = getattr(cult, "open_worship_reason", "") or "influential adherent"
                open_note = f"; catalyst={catalyst} ({reason})"
            print(f"  {getattr(cult, 'name', 'Unknown cult')} — title={title}; status={status}; pressure={float(getattr(cult, 'legend_pressure', 0.0)):.1f}; mythic={mythic:.1f}; domains={domains}; regions={regions}; latent_commoners={hidden}; actor_affinity={actor_aff}{open_note}")
    doubters = [a for a in getattr(world, "actors", {}).values() if getattr(a, "alive", False) and float(getattr(a, "faith_doubt", 0.0) or 0.0) > 0.05]
    if doubters:
        print("Highest faith doubt:")
        for actor in sorted(doubters, key=lambda a: float(getattr(a, "faith_doubt", 0.0) or 0.0), reverse=True)[:10]:
            deity = getattr(getattr(actor, "deity", None), "value", getattr(getattr(actor, "deity", None), "name", getattr(actor, "deity", "-")))
            aff = getattr(actor, "cult_affinity", {}) or {}
            top_aff = ""
            if aff:
                cid, val = max(aff.items(), key=lambda item: float(item[1]))
                cult = getattr(world, "proto_cults", {}).get(int(cid)) if str(cid).isdigit() else None
                cname = getattr(cult, "public_title", "") or getattr(cult, "name", cid)
                top_aff = f"; top_cult={cname}:{float(val):.2f}"
            print(f"  {actor.short_name()} — religion={deity}; protocult={_actor_protocult_label(world, actor)}; doubt={float(getattr(actor, 'faith_doubt', 0.0)):.2f}{top_aff}{_faith_doubt_driver_label(actor, 3)}")
    print()

def _print_commoner_death_breakdown(world) -> None:
    deaths_by_cause = getattr(world, "commoner_deaths_by_cause", {}) or {}
    deaths_by_region = getattr(world, "commoner_deaths_by_region", {}) or {}

    _print_section("COMMONER DEATH BREAKDOWN")
    if not deaths_by_cause and not deaths_by_region:
        print("  No aggregate commoner death causes recorded.")
        print("  Older runs may not include this data.")
        print()
        return

    total = sum(int(v) for v in deaths_by_cause.values())
    print(f"Recorded aggregate commoner deaths: {total}")
    if deaths_by_cause:
        print("By cause:")
        for cause, count in sorted(deaths_by_cause.items(), key=lambda item: (-int(item[1]), str(item[0]))):
            pct = (int(count) / total * 100.0) if total else 0.0
            print(f"  {str(cause):32} {int(count):8}  {pct:5.1f}%")
    if deaths_by_region:
        print("By region, top 10:")
        ranked_regions = sorted(deaths_by_region.items(), key=lambda item: (-int(item[1]), world.region_name(item[0]) if item[0] in world.regions else str(item[0])))[:10]
        for region_id, count in ranked_regions:
            region_name = world.region_name(region_id) if region_id in world.regions else str(region_id)
            print(f"  {region_name:32} {int(count):8}")
    print()


def _world_condition_assessment(good_regions: int, evil_regions: int, contested: int, avg_order: float, total_regions: int, living_population: int, initial_population: int | None = None) -> str:
    population_ratio = None
    if initial_population is not None and initial_population > 0:
        population_ratio = living_population / initial_population

    good_majority = good_regions > evil_regions
    evil_majority = evil_regions > good_regions
    good_dominant = good_regions >= max(1, int(total_regions * 0.60))
    evil_dominant = evil_regions >= max(1, int(total_regions * 0.60))
    near_total_evil = evil_regions >= max(1, total_regions - 1)
    near_total_good = good_regions >= max(1, total_regions - 1)
    population_collapsing = population_ratio is not None and population_ratio < 0.45
    population_growing = population_ratio is not None and population_ratio >= 1.05

    if near_total_evil and avg_order < 25:
        return "The continent is fully lost to darkness. Little hope remains."
    if population_collapsing and evil_majority:
        return "The continent is being hollowed out by violence, fear, and oppressive rule."
    if evil_dominant and avg_order >= 55:
        return "A harsh and orderly darkness grips much of the continent."
    if evil_dominant:
        return "Evil powers dominate the continent, but their rule remains unstable."
    if near_total_good and avg_order >= 60:
        return "The continent stands in broad peace under strong and mostly benevolent rule."
    if good_dominant and avg_order < 35 and population_growing:
        return "The continent is unruly and fractured, but life persists and good powers hold the wider field."
    if good_dominant and avg_order < 35:
        return "The continent is disorderly, but good powers still hold the wider field."
    if good_dominant and avg_order >= 60:
        return "The continent is broadly stable and still capable of thriving."
    if good_majority and avg_order < 35:
        return "The continent is unstable and conflict-worn, but good regions still outnumber evil ones."
    if evil_majority and avg_order < 35:
        return "The continent is sliding toward chaotic oppression, with evil regions gaining the edge."
    if avg_order < 25:
        return "The continent is deeply unstable, with no side able to impose lasting order."
    if avg_order >= 65:
        return "The continent is broadly orderly, though its moral balance remains contested."
    return "The continent remains divided, with regional powers struggling to turn survival into lasting order."


def print_summary(sim, years=None) -> None:
    world = sim.world
    for region_id in world.regions:
        world.evaluate_region_rule(region_id)

    hero = villain = None
    all_adv = []
    living_population = _living_population(world)
    historical_population_estimate = _historical_population_estimate(world)
    living_by_role = _living_by_role(world, sim)
    aggregate_commoners = _aggregate_commoners(world)
    source_files = _source_files(world)

    good_regions = len([r for r in world.regions.values() if r.control >= 20])
    evil_regions = len([r for r in world.regions.values() if r.control <= -20])
    contested = len(world.regions) - good_regions - evil_regions
    avg_order = sum(region.order for region in world.regions.values()) / len(world.regions)

    births, deaths, feats, monsters, parties, politics, retirements, immortals = _event_bucket(_summary_event_source(sim))

    if _summary_section_enabled(sim, "SUMMARY_RUN_METRICS_ENABLED", True):
        _print_section("RUN METRICS")
        print(f"Seed: {world.seed_used}")
        print(f"Ticks simulated: {world.tick}")
        if years is not None:
            print(f"Summary label: {years}")
            print(f"Legendarium: {_legendarium_base_name(str(world.seed_used), str(years))}.txt")
        if hasattr(world, "initial_population"):
            print(f"Initial population target: {getattr(world, 'initial_population', 'unknown')}")
        if hasattr(world, "population_scale"):
            print(f"Population scale: {getattr(world, 'population_scale', 1.0):g}")
        runtime_seconds = getattr(world, "runtime_seconds", None)
        if runtime_seconds is not None:
            print(f"Realtime duration: {runtime_seconds:.2f} seconds ({runtime_seconds / 60.0:.2f} minutes)")
        year, month, day, tod, season = world.current_calendar()
        print(f"Current date: Year {year}, {season}, {_month_names(sim, world)[month - 1]} {day}, {tod}")
        print(f"Living population: {living_population}")
        print(f"Historical population estimate: {historical_population_estimate}")
        print(f"Living adventurers: {len([a for a in world.living_actors() if a.is_adventurer() and not getattr(a, 'retired', False) and not getattr(a, 'in_school', False)])}")
        print(f"Dead adventurers archived: {_dead_adventurer_count(world)}")
        print(f"Living monsters: {len(world.living_monsters())} / {sum(world.generated_monsters_by_kind.values())}")
        print(f"Active parties: {len(world.parties)}")
        if source_files:
            ordered_keys = ["simulator", "config", "class", "population", "legacy", "lore", "relics", "immortals", "summary", "economy", "combat", "monsters", "party", "politics", "world", "start_game", "ux", "fantag", "fantgg"]
            ordered = []
            for key in ordered_keys:
                if key in source_files:
                    ordered.append(f"{key}={source_files[key]}")
            for key, value in sorted(source_files.items()):
                if key not in ordered_keys:
                    ordered.append(f"{key}={value}")
            print("Source files: " + "; ".join(ordered))
        print()

    if _summary_section_enabled(sim, "SUMMARY_DEMOGRAPHICS_ENABLED", True):
        _print_section("DEMOGRAPHICS")
        print("Population by role:")
        for role in sim.Role:
            print(f"  {role.value:10} {living_by_role[role]:8} / {world.generated_by_role.get(role, 0):8}")
        retired_living = [a for a in world.living_actors() if getattr(a, "retired", False)]
        retired_dead = [a for a in world.actors.values() if getattr(a, "retired", False) and not getattr(a, "alive", False)]
        print("Retirement:")
        print(f"  Living retired adventurers: {len(retired_living)}")
        print(f"  Dead retired adventurers recorded: {len(retired_dead)}")
        if retired_living:
            retired_by_role = {}
            for actor in retired_living:
                retired_by_role[actor.role.value] = retired_by_role.get(actor.role.value, 0) + 1
            detail = ", ".join(f"{role}={count}" for role, count in sorted(retired_by_role.items()))
            print(f"  Living retired by role: {detail}")
        print("Birth metrics:")
        print(f"  Commoner births: {getattr(world, 'commoner_births', 0)}")
        print(f"  Adventurer-lineage births: {getattr(world, 'adventurer_lineage_births', 0)}")
        print(f"  Commoner pregnancies started: {getattr(world, 'commoner_pregnancies_started', 0)}")
        print(f"  Commoner births delivered from pregnancy queue: {getattr(world, 'commoner_births_due', 0)}")
        pending_pregnancies = sum(sum(q) for q in getattr(world, 'commoner_pregnancy_queue_by_region', {}).values())
        fertile_females = sum(getattr(world, 'commoner_fertile_females_by_region', {}).values())
        print(f"  Pending aggregate pregnancies: {pending_pregnancies}")
        print(f"  Fertile aggregate females: {fertile_females}")
        print(f"  Living commoners (aggregate): {aggregate_commoners}")
        school_children = [
            a for a in world.living_actors()
            if getattr(a, "in_school", False)
            and _is_formal_school_deity(sim, getattr(a, "school_deity", None) or getattr(a, "deity", None))
        ]
        if school_children:
            school_by_deity = {}
            for child in school_children:
                deity_obj = getattr(child, "school_deity", None) or getattr(child, "deity", "Unknown")
                deity = getattr(deity_obj, "value", str(deity_obj))
                school_by_deity[deity] = school_by_deity.get(deity, 0) + 1
            print(f"  Adventurer-school children: {len(school_children)}")
            schools = {d: school for d, school in (getattr(world, "adventurer_schools", {}) or {}).items() if _is_formal_school_deity(sim, d)}
            for deity, count in sorted(school_by_deity.items()):
                print(f"    {deity}: {count}")
            if schools:
                print("  Adventurer schools:")
                for deity_obj, school in sorted(schools.items(), key=lambda item: getattr(item[0], "value", str(item[0]))):
                    deity_name = getattr(deity_obj, "value", str(deity_obj))
                    region = world.regions.get(getattr(school, "region_id", None))
                    region_name = getattr(region, "name", "Unknown")
                    age_years = max(0.0, (getattr(world, "tick", 0) - int(getattr(school, "founded_tick", 0))) / 1080.0)
                    last_moved_years = max(0.0, (getattr(world, "tick", 0) - int(getattr(school, "last_moved_tick", 0))) / 1080.0)
                    teachers = []
                    if hasattr(sim, "_school_teacher_ids"):
                        for tid in sim._school_teacher_ids(deity_obj)[:6]:
                            teacher = world.actors.get(tid)
                            if teacher is not None:
                                score = sim._school_teacher_score(teacher, deity_obj) if hasattr(sim, "_school_teacher_score") else 0
                                teachers.append(f"{teacher.short_name()} ({teacher.role.value}, score {score})")
                    teacher_text = "; ".join(teachers) if teachers else "none"
                    prestige = sim._school_prestige_bonus(deity_obj) if hasattr(sim, "_school_prestige_bonus") else int(age_years)
                    enrolled = len([a for a in school_children if (getattr(a, "school_deity", None) or getattr(a, "deity", None)) == deity_obj])
                    capacity = sim._school_capacity(deity_obj) if hasattr(sim, "_school_capacity") else enrolled
                    cap_bonus = sim._school_capacity_bonus(deity_obj) if hasattr(sim, "_school_capacity_bonus") else 0
                    rank = sim._school_influence_rank(deity_obj) if hasattr(sim, "_school_influence_rank") else None
                    combat = sim._update_school_class_ranks(deity_obj) if hasattr(sim, "_update_school_class_ranks") else []
                    top_student = combat[0].short_name() if combat else "none"
                    print(f"    {deity_name}: {region_name}, age={age_years:.1f}y, since move={last_moved_years:.1f}y, prestige={prestige}, enrollment={enrolled}/{capacity} (+{cap_bonus}, rank={rank or '-'}) combat_top={top_student}, teachers={teacher_text}")
        refugee_arrivals = getattr(world, 'refugee_arrivals', 0)
        refugee_commoners = getattr(world, 'refugee_commoners', 0)
        if refugee_arrivals or refugee_commoners:
            print(f"  Refugee waves: {refugee_arrivals}")
            print(f"  Refugees settled: {refugee_commoners}")
        print("Immortal influence:")
        for deity, living, commoners, souls, influence, pct in _deity_influence_summary(sim):
            deity_name = getattr(deity, "value", getattr(deity, "name", str(deity)))
            print(f"  {deity_name:16} living={living:4} commoners={commoners:8} souls={souls:5} influence={influence:9} share={pct:5.1f}%")
        if hasattr(sim, "_player_god"):
            player = sim._player_god()
            if player is not None:
                pname = getattr(player, "value", getattr(player, "name", str(player)))
                grace = sim._god_immortal_grace_remaining(player) if hasattr(sim, "_god_immortal_grace_remaining") else 0
                locked = player in set(getattr(world, "school_locked_deities", set()) or set()) and player not in set(getattr(world, "school_unlocked_deities", set()) or set())
                origin = getattr(world, "player_god_origin", "") or "existing"
                grace_text = f"; immortal grace {grace / 1080.0:.1f}y" if grace > 0 else ""
                school_text = "school locked" if locked else "school unlocked/formal"
                print(f"  Player god status: {pname} origin={origin}; {school_text}{grace_text}")
        print()

    if _summary_section_enabled(sim, "SUMMARY_COMMONER_DEATH_BREAKDOWN_ENABLED", True):
        _print_commoner_death_breakdown(world)

    if _summary_section_enabled(sim, "SUMMARY_WORLD_CONDITION_ENABLED", True):
        _print_section("WORLD CONDITION")
        assessment = _world_condition_assessment(
            good_regions,
            evil_regions,
            contested,
            avg_order,
            len(world.regions),
            living_population,
            getattr(world, "initial_population", None),
        )
        print(f"Good-leaning regions: {good_regions}")
        print(f"Evil-leaning regions: {evil_regions}")
        print(f"Contested regions: {contested}")
        print(f"Average order: {avg_order:.1f}")
        print(f"Assessment: {assessment}")
        print()

    if _summary_section_enabled(sim, "SUMMARY_ADVENTURER_LISTS_ENABLED", True):
        _print_section("TOP ADVENTURER LISTS")
        hero, villain = _pick_top_hero_and_villain(sim)
        all_adv = _top_adventurers(world, sim)
        if hero is not None:
            print("Most celebrated hero:")
            print(f"  {hero.full_name()} — {hero.alignment.value}, {hero.role.value}, rep={hero.reputation}, region={world.region_name(hero.region_id)}")
            print(f"  Born: {_short_birth_date(sim, world, hero)}")
            print(f"  Parents: {_actor_parent_label(world, hero, 'mother')} / {_actor_parent_label(world, hero, 'father')}")
            print(f"  Died: {_death_line(hero)}")
            print(f"  Deeds: {hero.notable_deeds_summary()}")
            print()
        if villain is not None:
            print("Most feared villain:")
            print(f"  {villain.full_name()} — {villain.alignment.value}, {villain.role.value}, rep={villain.reputation}, region={world.region_name(villain.region_id)}")
            print(f"  Born: {_short_birth_date(sim, world, villain)}")
            print(f"  Parents: {_actor_parent_label(world, villain, 'mother')} / {_actor_parent_label(world, villain, 'father')}")
            print(f"  Died: {_death_line(villain)}")
            print(f"  Deeds: {villain.notable_deeds_summary()}")
            print()

        _print_adventurer_block(world, sim, "Top 25 adventurers, living and dead:", all_adv, 25)

        oldest_all_time = sorted(
            _all_adventurer_records(sim),
            key=lambda a: (_actor_age_for_record(sim, a), getattr(a, "reputation", 0), getattr(a, "level", 1)),
            reverse=True,
        )
        _print_adventurer_block(world, sim, "Top 3 oldest adventurers of all time:", oldest_all_time, 3)

        oldest_living = sorted(
            [a for a in world.actors.values() if getattr(a, "alive", False) and a.is_adventurer()],
            key=lambda a: (sim._calculate_age(a), getattr(a, "reputation", 0), getattr(a, "level", 1)),
            reverse=True,
        )
        _print_adventurer_block(world, sim, "Top 10 oldest living adventurers:", oldest_living, 10)
        for role_name in ("FIGHTER", "WARDEN", "WIZARD", "BARD"):
            role = getattr(sim.Role, role_name, None)
            if role is None:
                continue
            role_adv = [a for a in all_adv if a.role == role]
            _print_adventurer_block(world, sim, f"Top 10 {role.value}s:", role_adv, 10)
        print()

    if _summary_section_enabled(sim, "SUMMARY_NOTABLE_BIRTHS_ENABLED", True):
        _print_section("NOTABLE BIRTHS")
        _print_event_list("", births, 20)

    if _summary_section_enabled(sim, "SUMMARY_NOTABLE_DEATHS_ENABLED", True):
        _print_section("NOTABLE DEATHS")
        _print_event_list("", deaths, 30)

    if _summary_section_enabled(sim, "SUMMARY_NOTABLE_FEATS_ENABLED", True):
        _print_section("NOTABLE FEATS")
        _print_event_list("", feats, 30)

    if _summary_section_enabled(sim, "SUMMARY_RECENT_RETIREMENTS_ENABLED", True):
        _print_section("RECENT RETIREMENTS")
        _print_event_list("", retirements, 20)

    if _summary_section_enabled(sim, "SUMMARY_MAIN_CHARACTER_ACTIONS_ENABLED", True):
        _print_main_character_actions(sim, 20)

    if _summary_section_enabled(sim, "SUMMARY_LORE_ENABLED", True):
        _print_lore_summary(sim)

    if _summary_section_enabled(sim, "SUMMARY_RELIC_HISTORY_ENABLED", True):
        _print_section("RELIC HISTORY")
        relics = sorted(getattr(world, "relics", {}).values(), key=lambda r: (getattr(r, "name", ""), getattr(r, "id", 0)))
        if relics:
            for relic in relics:
                holder = world.actors.get(getattr(relic, "holder_id", None))
                holder_name = holder.short_name() if holder is not None else "unclaimed"
                status = "destroyed" if getattr(relic, "destroyed", False) else "held" if holder is not None else "active" if getattr(relic, "active", False) else "hidden"
                region_name = world.region_name(getattr(relic, "region_id", -1)) if getattr(relic, "region_id", None) in getattr(world, "regions", {}) else "unknown"
                tier = getattr(relic, "tier", "world")
                creator = getattr(relic, "creator_deity", None)
                creator_name = getattr(creator, "value", getattr(creator, "name", creator)) if creator is not None else "world"
                original_id = getattr(relic, "original_recipient_id", None)
                original = world.actors.get(original_id) if original_id is not None else None
                original_name = original.short_name() if original is not None else (str(original_id) if original_id is not None else "-")
                boon = getattr(relic, "boon_label", "") or "-"
                stolen = ""
                if holder is not None and creator is not None and getattr(relic, "created_by_player", False):
                    holder_god = getattr(holder, "champion_of", None) or getattr(holder, "deity", None)
                    hkey = str(getattr(holder_god, "value", getattr(holder_god, "name", holder_god))).lower()
                    ckey = str(getattr(creator, "value", getattr(creator, "name", creator))).lower()
                    stolen = "; STOLEN" if hkey != ckey else "; reclaimed/held by creator faith"
                print(f"  {relic.name} — tier={tier}; status={status}; creator={creator_name}; original={original_name}; holder={holder_name}; region={region_name}; boon={boon}; power=+{getattr(relic, 'power_bonus', 0)} rep=+{getattr(relic, 'reputation_bonus', 0)}{stolen}")
                history = getattr(relic, "possession_history", []) or []
                if history:
                    brief = []
                    for item in history[-5:]:
                        try:
                            tick, action, aid, rid = item
                        except Exception:
                            continue
                        actor = world.actors.get(aid)
                        actor_name = actor.short_name() if actor is not None else str(aid)
                        region = world.region_name(rid) if rid in getattr(world, "regions", {}) else str(rid)
                        brief.append(f"{action}:{actor_name}@{region}")
                    if brief:
                        print(f"    history: {'; '.join(brief)}")
            relic_events = _historian_category_events(sim, {"relic", "relic_quest", "relic_pressure"}, limit=30)
            if relic_events:
                print("\n  Recent relic events:")
                for event in relic_events[-30:]:
                    print(f"  [{getattr(event, 'timestamp', '')}] {getattr(event, 'text', '')}")
        else:
            print("  No relics seeded.")

    if _summary_section_enabled(sim, "SUMMARY_MONSTER_ACTIVITY_ENABLED", True):
        _print_section("MONSTER ACTIVITY")
        print("Monsters still abroad:")
        living_monsters_by_kind = {kind: 0 for kind in sim.MonsterKind}
        for monster in world.living_monsters():
            living_monsters_by_kind[monster.kind] += 1
        for kind in sim.MonsterKind:
            print(f"  {kind.value:14} {living_monsters_by_kind[kind]:3} / {world.generated_monsters_by_kind[kind]:3}")
        print()
        major_lifecycle = _historic_major_monster_lifecycle_events(sim, limit=40)
        if major_lifecycle:
            print("Historic major monster lifecycle (no goblins):")
            for event in major_lifecycle[-40:]:
                print(f"  [{getattr(event, 'timestamp', '')}] {getattr(event, 'text', '')}")
            print()
        _print_event_list("", monsters, 25)

    if _summary_section_enabled(sim, "SUMMARY_PARTY_ACTIVITY_ENABLED", True):
        _print_section("PARTY ACTIVITY")
        party_history = list(getattr(world, 'party_history', {}).values())
        if party_history:
            print("Top parties in history:")
            ranked_parties = sorted(party_history, key=lambda p: (p.peak_size, p.peak_reputation, p.founded_tick), reverse=True)[:10]
            for party in ranked_parties:
                region_name = world.region_name(party.last_region_id) if party.last_region_id is not None and party.last_region_id in world.regions else "Unknown"
                print(f"  {party.name} — founder={party.founder_name}, peak_size={party.peak_size}, peak_rep={party.peak_reputation}, last_region={region_name}, fate={party.fate}")
            print()
        influential_party = max(
            world.parties.values(),
            key=lambda p: (len(p.member_ids), sum(world.actors[mid].reputation for mid in p.member_ids if mid in world.actors)),
            default=None,
        )
        if influential_party is not None:
            leader_name = world.actors[influential_party.leader_id].short_name() if influential_party.leader_id in world.actors else "Unknown"
            print(f"Most influential active party: {influential_party.name or f'Party {influential_party.id}'} — leader={leader_name}, size={len(influential_party.member_ids)}, large_group={influential_party.is_large_group}")
            print()
        _print_event_list("", parties, 25)

    if _summary_section_enabled(sim, "SUMMARY_POLITICAL_ACTIVITY_ENABLED", True):
        _print_section("POLITICAL ACTIVITY")
        polity_history = list(getattr(world, 'polity_history', {}).values())
        if polity_history:
            print("Top polities in history:")
            ranked_polities = sorted(polity_history, key=lambda p: (p.peak_regions, p.peak_strength, p.founded_tick), reverse=True)[:10]
            for polity in ranked_polities:
                capital_name = world.region_name(polity.capital_region_id) if polity.capital_region_id is not None and polity.capital_region_id in world.regions else "Unknown"
                print("  /" + "=" * 66 + "\\")
                print(f"  | {polity.name}")
                print(f"  |   founded={_tick_to_short_date(sim, getattr(polity, 'founded_tick', None))}")
                print(f"  |   founder={polity.founder_name}")
                print(f"  |   current_ruler={getattr(polity, 'current_ruler_name', 'Unknown')}")
                print(f"  |   alignment={polity.alignment}")
                print(f"  |   peak_regions={polity.peak_regions}  peak_strength={polity.peak_strength}")
                print(f"  |   capital={capital_name}")
                print(f"  |   fate={polity.fate}")
                if getattr(polity, 'leaders', None):
                    print("  |   ruler history:")
                    for leader in polity.leaders:
                        term = _format_leader_term(sim, leader, getattr(world, "tick", None))
                        claim = _format_leader_claim(leader)
                        term_prefix = f"{term}, " if term else ""
                        print(f"  |     - {leader.name}: {term_prefix}{leader.fate}{claim}")
                print("  \\" + "=" * 66 + "/")
            print()
        if hasattr(world, 'polities') and world.polities:
            print("Active polities:")
            for polity in sorted(world.polities.values(), key=lambda p: (len(getattr(p, 'region_ids', [])), getattr(p, 'strength', 0), p.name), reverse=True)[:12]:
                ruler_name = world.actors[polity.ruler_id].short_name() if polity.ruler_id in world.actors and world.actors[polity.ruler_id].alive else 'None'
                grace = max(0, int(getattr(polity, 'succession_grace_until', -999999)) - int(getattr(world, 'tick', 0)))
                grace_text = f", grace={grace / 1080.0:.1f}y" if grace > 0 else ""
                relationship_scores = getattr(polity, 'relationship_scores', {}) or {}
                def _rel_label(pid):
                    other = world.polities.get(pid)
                    if other is None:
                        return None
                    try:
                        score = int(relationship_scores.get(pid, 0))
                    except Exception:
                        score = 0
                    return f"{other.name}({score:+d})"
                major_allies = [_rel_label(pid) for pid in getattr(polity, 'major_ally_ids', []) if pid in getattr(world, 'polities', {})]
                major_allies = [item for item in major_allies if item]
                major_rivals = [_rel_label(pid) for pid in getattr(polity, 'major_rival_ids', []) if pid in getattr(world, 'polities', {})]
                major_rivals = [item for item in major_rivals if item]
                allies = [world.polities[pid].name for pid in getattr(polity, 'allied_polity_ids', []) if pid in getattr(world, 'polities', {}) and pid not in set(getattr(polity, 'major_ally_ids', []) or [])]
                trade = [world.polities[pid].name for pid in getattr(polity, 'trade_partner_ids', []) if pid in getattr(world, 'polities', {})]
                prev = getattr(polity, 'previous_ruler_name', 'Unknown')
                approval = getattr(polity, 'previous_ruler_approval', 50)
                print(f"  {polity.name} — ruler={ruler_name}, alignment={polity.alignment.value}, regions={len(polity.region_ids)}, stability={getattr(polity, 'stability', 0)}, legitimacy={getattr(polity, 'legitimacy', 0)}, challenges={getattr(polity, 'challenge_count', 0)}{grace_text}")
                if major_allies or major_rivals or allies or trade or prev != 'Unknown':
                    print(f"    major_allies={', '.join(major_allies) if major_allies else 'none'} | major_rivals={', '.join(major_rivals) if major_rivals else 'none'}")
                    print(f"    allies={', '.join(allies) if allies else 'none'} | trade={', '.join(trade) if trade else 'none'} | previous={prev} approval={approval}")
                imports = getattr(polity, 'trade_imports', {}) or {}
                exports = getattr(polity, 'trade_exports', {}) or {}
                deficits = getattr(polity, 'economic_deficit', {}) or {}
                dependency = int(getattr(polity, 'trade_dependency_score', 0) or 0)
                shortage = int(getattr(polity, 'shortage_pressure', 0) or 0)
                if imports or exports or deficits or dependency or shortage:
                    print(f"    economy: dependency={dependency}% shortage={shortage}; imports={_resource_snapshot_text(imports)}; exports={_resource_snapshot_text(exports)}; deficits={_resource_snapshot_text(deficits)}")
            print()
    if _summary_section_enabled(sim, "SUMMARY_ECONOMY_ENABLED", True):
        _print_economy_summary(sim)
    if _summary_section_enabled(sim, "SUMMARY_POLITICAL_ACTIVITY_ENABLED", True):
        _print_event_list("", politics, 25)

    if _summary_section_enabled(sim, "SUMMARY_HISTORY_GRAPHS_ENABLED", True):
        _print_section("HISTORY GRAPHS")
        _print_history_graphs(sim)

    if _summary_section_enabled(sim, "SUMMARY_PARENTAGE_AUDIT_ENABLED", True):
        _print_section("PARENTAGE AUDIT")
        _print_parentage_audit(sim)

    if _summary_section_enabled(sim, "SUMMARY_LORE_PROFILER_ENABLED", True):
        _print_lore_profiler(sim, 12)

    if _summary_section_enabled(sim, "SUMMARY_HOLY_WAR_ENABLED", True):
        _print_section("HOLY WAR")
        holy_events = _historian_category_events(sim, ("holy_war", "god_death"), limit=20)
        if holy_events:
            _print_event_list("", holy_events[-20:], 20)
        else:
            print("  No holy wars recorded.")

    if _summary_section_enabled(sim, "SUMMARY_IMMORTAL_ACTIONS_ENABLED", True):
        _print_section("IMMORTAL ACTIONS")
        _print_event_list("", immortals, 20)


def _csv_clean(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _safe_filename_part(value) -> str:
    text = str(value or "random").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    text = text.strip("._-")
    return text or "random"


def _summary_base_name(seed, label: str) -> str:
    safe_seed = _safe_filename_part(seed)
    safe_label = _safe_filename_part(label)
    return f"fantfarm_{safe_seed}_{safe_label}year_summary" if str(label).isdigit() else f"fantfarm_{safe_seed}_{safe_label}_summary"


def _csv_base_path(sim, suffix: str) -> Path:
    world = sim.world
    output_dir = Path(getattr(world, "output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = _safe_filename_part(getattr(world, "seed_used", "random"))
    return output_dir / f"fantfarm_{seed}_{suffix}.csv"


def _append_csv_rows(path: Path, header: list[str], rows: list[list[object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(header)
        for row in rows:
            writer.writerow([_csv_clean(value) for value in row])
    return path


def _read_existing_csv_header(path: Path) -> list[str]:
    """Return the existing CSV header, if present.

    Metrics CSV used to drift because each append recomputed a different
    field list while the original header stayed behind.  Once a file exists,
    its first row is the schema contract.  Future writes must obey it exactly.
    """
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
        return [str(col) for col in header if str(col) != ""]
    except Exception:
        return []


def _write_csv_records(path: Path, fieldnames: list[str], records: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_header = _read_existing_csv_header(path)
    write_header = not existing_header
    schema = existing_header or list(fieldnames)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=schema, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for record in records:
            writer.writerow({key: _csv_clean(record.get(key, "")) for key in schema})
    return path


def _csv_metric_key(*parts) -> str:
    text = "_".join(str(part) for part in parts if part is not None and str(part) != "")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text or "metric"

def _csv_fixed_slot_count(name: str, default: int) -> int:
    try:
        return max(0, int(globals().get(name, default)))
    except Exception:
        return int(default)


def _csv_pantheon_slots(sim) -> list[object]:
    """Return a fixed-length deity slot list for CSV metrics.

    The first slots are the run pantheon in stable order. Empty/future slots
    are written as blanks/zeroes so emergent gods do not add columns mid-run.
    """
    max_gods = _csv_fixed_slot_count("PANTHEON_MAX_ACTIVE_GODS", 7)
    gods = list(_pantheon(sim))[:max_gods]
    while len(gods) < max_gods:
        gods.append(None)
    return gods


def _csv_relic_slots(world) -> list[object]:
    """Return a fixed-length relic slot list for CSV metrics.

    Relic names are dynamic and player-created relics can appear after the
    first metrics row.  Slots keep the schema fixed while still exposing the
    current identity/status of each relic.
    """
    max_relics = _csv_fixed_slot_count("CSV_RELIC_SLOTS", 24)
    relics = sorted(getattr(world, "relics", {}).values(), key=lambda r: int(getattr(r, "id", 0) or 0))[:max_relics]
    while len(relics) < max_relics:
        relics.append(None)
    return relics


def _stable_summary_metric_fieldnames(sim, row: dict[str, object]) -> list[str]:
    """Build a deterministic wide metrics schema for append-safe CSV output.

    No field in this schema is generated from a deity name, relic name, or any
    entity that may appear later in the run.  Dynamic entities are represented
    by fixed slots.  This prevents row-width drift during long simulations.
    """
    world = sim.world
    fields: list[str] = ["seed", "summary_label", "tick"]

    def add(*parts):
        key = _csv_metric_key(*parts)
        if key not in fields:
            fields.append(key)

    for metric in (
        "ticks_simulated", "current_year", "current_month", "current_day",
        "current_time_of_day", "current_season", "initial_population",
        "population_scale", "runtime_seconds",
    ):
        add("run", metric)

    for metric in (
        "living_population", "historical_population_estimate", "living_commoners",
        "living_actors", "active_adventurers", "school_children",
        "dead_adventurers", "adventurer_ratio",
    ):
        add("population", metric)

    for role in sim.Role:
        role_name = getattr(role, "value", str(role))
        add("role", role_name, "living")
        add("role", role_name, "generated")

    for metric in ("regions", "good_leaning_regions", "evil_leaning_regions", "contested_regions", "average_order"):
        add("world", metric)

    for region in sorted(world.regions.values(), key=lambda r: getattr(r, "id", 0)):
        region_key = f"region_{getattr(region, 'id', ''):02d}" if isinstance(getattr(region, "id", None), int) else _csv_metric_key("region", getattr(region, "name", "unknown"))
        for metric in ("name", "biome", "order", "control", "commoners", "grain", "livestock", "wood", "metal", "weapons", "armor"):
            add(region_key, metric)

    for kind in sim.MonsterKind:
        kind_name = getattr(kind, "value", str(kind))
        add("monster", kind_name, "living")
        add("monster", kind_name, "generated")

    add("groups", "active_parties")
    add("groups", "active_polities")

    for idx in range(_csv_fixed_slot_count("PANTHEON_MAX_ACTIVE_GODS", 7)):
        slot = f"deity_slot_{idx:02d}"
        for metric in ("name", "living_adventurers", "commoners", "souls", "influence", "influence_share"):
            add(slot, metric)
        school_slot = f"school_slot_{idx:02d}"
        for metric in ("name", "enrolled", "capacity", "capacity_bonus", "influence_rank", "combat_training_count", "combat_top"):
            add(school_slot, metric)

    for cause in (
        "hardship / regional mortality",
        "divine disaster",
        "monster raid: Goblin",
        "monster raid: Giant",
        "monster raid: Dragon",
        "monster raid: Ancient Horror",
        "holy war: Lord of Darkness",
        "holy war: Lord of Light",
        "holy war: God of Chance",
        "holy war: Dionysus",
        "holy war: Ka!",
        "holy war: KAOS!",
    ):
        add("commoner_deaths", cause)

    # Fixed relic slots. Names/statuses are values, never column identifiers.
    for idx in range(_csv_fixed_slot_count("CSV_RELIC_SLOTS", 24)):
        slot = f"relic_slot_{idx:02d}"
        for metric in ("id", "name", "status", "holder", "region", "power", "rep", "created_by_player", "creator_deity"):
            add(slot, metric)

    return fields

def _write_summary_metrics_csv(sim, years, output_path: Path | None = None) -> Path:
    """Append one wide summary snapshot to the seed-level metrics CSV.

    Output shape is one row per summary/year label. Metrics are columns, so the
    file is useful for spreadsheet filtering and charting without pivoting.
    """
    world = sim.world
    path = _csv_base_path(sim, "metrics")
    seed = getattr(world, "seed_used", "")
    label = str(years)
    tick = getattr(world, "tick", 0)

    row: dict[str, object] = {
        "seed": seed,
        "summary_label": label,
        "tick": tick,
    }

    def set_metric(*parts_and_value):
        *parts, value = parts_and_value
        key = _csv_metric_key(*parts)
        suffix = 2
        base_key = key
        while key in row:
            key = f"{base_key}_{suffix}"
            suffix += 1
        row[key] = value

    living_actors = list(world.living_actors())
    commoners = _aggregate_commoners(world)
    active_adventurers = [a for a in living_actors if a.is_adventurer() and not getattr(a, "retired", False) and not getattr(a, "in_school", False)]
    school_children = [
        a for a in living_actors
        if getattr(a, "in_school", False)
        and _is_formal_school_deity(sim, getattr(a, "school_deity", None) or getattr(a, "deity", None))
    ]
    living_population = commoners + len(living_actors)
    year, month, day, tod, season = world.current_calendar()

    for metric, value in [
        ("ticks_simulated", tick),
        ("current_year", year), ("current_month", month), ("current_day", day),
        ("current_time_of_day", tod), ("current_season", season),
        ("initial_population", getattr(world, "initial_population", "")),
        ("population_scale", getattr(world, "population_scale", "")),
        ("runtime_seconds", getattr(world, "runtime_seconds", "")),
    ]:
        set_metric("run", metric, value)

    for metric, value in [
        ("living_population", living_population),
        ("historical_population_estimate", _historical_population_estimate(world)),
        ("living_commoners", commoners), ("living_actors", len(living_actors)),
        ("active_adventurers", len(active_adventurers)), ("school_children", len(school_children)),
        ("dead_adventurers", _dead_adventurer_count(world)),
        ("adventurer_ratio", (len(active_adventurers) / living_population) if living_population else 0.0),
    ]:
        set_metric("population", metric, value)

    living_by_role = _living_by_role(world, sim)
    for role in sim.Role:
        role_name = getattr(role, "value", str(role))
        set_metric("role", role_name, "living", living_by_role.get(role, 0))
        set_metric("role", role_name, "generated", getattr(world, "generated_by_role", {}).get(role, 0))

    good_regions = len([r for r in world.regions.values() if r.control >= 20])
    evil_regions = len([r for r in world.regions.values() if r.control <= -20])
    contested = len(world.regions) - good_regions - evil_regions
    avg_order = sum(region.order for region in world.regions.values()) / max(1, len(world.regions))
    for metric, value in [("regions", len(world.regions)), ("good_leaning_regions", good_regions), ("evil_leaning_regions", evil_regions), ("contested_regions", contested), ("average_order", avg_order)]:
        set_metric("world", metric, value)

    for region in sorted(world.regions.values(), key=lambda r: getattr(r, "id", 0)):
        region_key = f"region_{getattr(region, 'id', ''):02d}" if isinstance(getattr(region, "id", None), int) else _csv_metric_key("region", getattr(region, "name", "unknown"))
        stock = getattr(region, "stockpile", {}) or {}
        set_metric(region_key, "name", getattr(region, "name", region.id))
        set_metric(region_key, "biome", getattr(region, "biome", ""))
        set_metric(region_key, "order", getattr(region, "order", 0))
        set_metric(region_key, "control", getattr(region, "control", 0))
        set_metric(region_key, "commoners", getattr(world, "commoners_by_region", {}).get(region.id, 0))
        for resource in ("grain", "livestock", "wood", "metal", "weapons", "armor"):
            set_metric(region_key, resource, stock.get(resource, 0))

    living_monsters_by_kind = {kind: 0 for kind in sim.MonsterKind}
    for monster in world.living_monsters():
        living_monsters_by_kind[monster.kind] += 1
    for kind in sim.MonsterKind:
        kind_name = getattr(kind, "value", str(kind))
        set_metric("monster", kind_name, "living", living_monsters_by_kind.get(kind, 0))
        set_metric("monster", kind_name, "generated", getattr(world, "generated_monsters_by_kind", {}).get(kind, 0))

    set_metric("groups", "active_parties", len(getattr(world, "parties", {})))
    set_metric("groups", "active_polities", len(getattr(world, "polities", {})))

    deity_rows = {deity: (living, deity_commoners, souls, influence, pct) for deity, living, deity_commoners, souls, influence, pct in _deity_influence_summary(sim)}
    for idx, deity in enumerate(_csv_pantheon_slots(sim)):
        slot = f"deity_slot_{idx:02d}"
        school_slot = f"school_slot_{idx:02d}"
        name = getattr(deity, "value", getattr(deity, "name", str(deity))) if deity is not None else ""
        living, deity_commoners, souls, influence, pct = deity_rows.get(deity, (0, 0, 0, 0, 0.0)) if deity is not None else (0, 0, 0, 0, 0.0)
        set_metric(slot, "name", name)
        set_metric(slot, "living_adventurers", living)
        set_metric(slot, "commoners", deity_commoners)
        set_metric(slot, "souls", souls)
        set_metric(slot, "influence", influence)
        set_metric(slot, "influence_share", pct)
        set_metric(school_slot, "name", name)
        if deity is not None and hasattr(sim, "_school_capacity"):
            enrolled = len([a for a in school_children if (getattr(a, "school_deity", None) or getattr(a, "deity", None)) == deity])
            combat = sim._update_school_class_ranks(deity) if hasattr(sim, "_update_school_class_ranks") else []
            set_metric(school_slot, "enrolled", enrolled)
            set_metric(school_slot, "capacity", sim._school_capacity(deity))
            set_metric(school_slot, "capacity_bonus", sim._school_capacity_bonus(deity) if hasattr(sim, "_school_capacity_bonus") else 0)
            set_metric(school_slot, "influence_rank", sim._school_influence_rank(deity) if hasattr(sim, "_school_influence_rank") else "")
            set_metric(school_slot, "combat_training_count", len(combat))
            set_metric(school_slot, "combat_top", combat[0].short_name() if combat else "")
        else:
            for metric in ("enrolled", "capacity", "capacity_bonus", "influence_rank", "combat_training_count", "combat_top"):
                set_metric(school_slot, metric, "")

    for cause, count in sorted((getattr(world, "commoner_deaths_by_cause", {}) or {}).items()):
        set_metric("commoner_deaths", cause, count)

    for idx, relic in enumerate(_csv_relic_slots(world)):
        slot = f"relic_slot_{idx:02d}"
        if relic is None:
            for metric in ("id", "name", "status", "holder", "region", "power", "rep", "created_by_player", "creator_deity"):
                set_metric(slot, metric, "")
            continue
        holder = world.actors.get(getattr(relic, "holder_id", None))
        holder_name = holder.short_name() if holder is not None else ""
        status = "destroyed" if getattr(relic, "destroyed", False) else "held" if holder is not None else "active" if getattr(relic, "active", False) else "hidden"
        region_name = world.region_name(getattr(relic, "region_id", -1)) if getattr(relic, "region_id", None) in getattr(world, "regions", {}) else ""
        creator = getattr(relic, "creator_deity", None)
        creator_name = getattr(creator, "value", getattr(creator, "name", str(creator))) if creator is not None else ""
        set_metric(slot, "id", getattr(relic, "id", ""))
        set_metric(slot, "name", getattr(relic, "name", ""))
        set_metric(slot, "status", status)
        set_metric(slot, "holder", holder_name)
        set_metric(slot, "region", region_name)
        set_metric(slot, "power", getattr(relic, "power_bonus", 0))
        set_metric(slot, "rep", getattr(relic, "reputation_bonus", 0))
        set_metric(slot, "created_by_player", int(bool(getattr(relic, "created_by_player", False))))
        set_metric(slot, "creator_deity", creator_name)

    fieldnames = _stable_summary_metric_fieldnames(sim, row)
    return _write_csv_records(path, fieldnames, [row])

def _write_history_csv(sim, output_path: Path | None = None) -> Path:
    """Append new history samples to the seed-level history CSV.

    The function remembers how many samples it has already written during this
    run, so periodic summaries do not duplicate the same history rows.
    """
    world = sim.world
    history = getattr(world, "history", None) or {}
    path = _csv_base_path(sim, "history")
    preferred = ["tick", "year", "month", "day", "total_population", "commoners", "adventurers", "monsters", "parties", "polities"]
    keys = list(history.keys())
    ordered = [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]
    max_len = max((len(history.get(k, [])) for k in ordered), default=0)
    start_index = int(getattr(world, "_summary_history_csv_written", 0) or 0)
    start_index = max(0, min(start_index, max_len))
    seed = getattr(world, "seed_used", "")
    rows = []
    for i in range(start_index, max_len):
        rows.append([seed, i] + [history.get(k, [])[i] if i < len(history.get(k, [])) else "" for k in ordered])
    setattr(world, "_summary_history_csv_written", max_len)
    return _append_csv_rows(path, ["seed", "sample_index"] + ordered, rows)


def _write_events_csv(sim, output_path: Path | None = None) -> Path:
    """Append only the recent RAM event window to CSV without duplicating capped-buffer rows.

    Full event history belongs in the SQLite tome. This CSV is now just a light
    recent-event convenience export, not an authoritative archive.
    """
    world = sim.world
    events = list(getattr(world, "events", []) or [])
    path = _csv_base_path(sim, "events")
    seed = getattr(world, "seed_used", "")
    total_seen = int(getattr(world, "event_counter", len(events)) or len(events))
    first_event_number = max(0, total_seen - len(events))
    last_written = int(getattr(world, "_summary_events_csv_written_counter", 0) or 0)
    rows = []
    for offset, event in enumerate(events):
        event_number = first_event_number + offset + 1
        if event_number <= last_written:
            continue
        rows.append([seed, event_number, getattr(world, "tick", ""), getattr(event, "timestamp", ""), getattr(event, "category", ""), getattr(event, "importance", ""), getattr(event, "text", "")])
    setattr(world, "_summary_events_csv_written_counter", total_seen)
    return _append_csv_rows(path, ["seed", "event_number", "write_tick", "timestamp", "category", "importance", "text"], rows)




def _print_top_song_chart(sim, limit: int | None = None) -> None:
    world = sim.world
    if limit is None:
        limit = int(globals().get("TOP_SONG_CHART_COUNT", 10))
    _print_section("TOP SONGS")
    songs = [song for song in getattr(world, "songs", {}).values() if not getattr(song, "forgotten", False)]
    if not songs:
        print("None.")
        print()
        return
    ranked = sorted(
        songs,
        key=lambda song: (
            float(getattr(song, "popularity", 0.0) or 0.0),
            len(getattr(song, "performer_actor_ids", set()) or set()),
            int(getattr(song, "performances", 0) or 0),
            float(getattr(song, "historical_weight", 0.0) or 0.0),
        ),
        reverse=True,
    )[:max(1, int(limit))]
    for idx, song in enumerate(ranked, 1):
        title = getattr(song, "title", "Untitled") or "Untitled"
        composer = _actor_ref_label(sim, world, getattr(song, "composer_id", None), none_label="Unknown")
        song_type = str(getattr(song, "song_type", "mythic") or "mythic").lower()
        performers = len(getattr(song, "performer_actor_ids", set()) or set())
        print(f"{idx}. [{song_type}] {title} — {composer} ({int(getattr(song, 'performances', 0) or 0)} perf / {performers} bards)")
    print()


def print_legendarium(sim, years=None) -> None:
    world = sim.world
    year, month, day, tod, season = world.current_calendar()

    _print_section("LEGENDARIUM")
    print(f"Seed: {world.seed_used}")
    if years is not None:
        print(f"Legendarium label: {years}")
    print(f"Current date: Year {year}, {season}, {_month_names(sim, world)[month - 1]} {day}, {tod}")
    print()

    if _legendarium_section_enabled(sim, "LEGENDARIUM_LIVING_AUTHORITY_ENABLED", True):
        _print_living_authority_legendarium(sim)

    if _legendarium_section_enabled(sim, "LEGENDARIUM_RELIGIOUS_CATALYSTS_ENABLED", True):
        _print_potential_religious_catalysts(sim, 25)

    if _legendarium_section_enabled(sim, "LEGENDARIUM_REMEMBERED_FIGURES_ENABLED", True):
        legends = sorted((getattr(world, "legend_pressure_by_actor_id", {}) or {}).items(), key=lambda item: float(item[1]), reverse=True)[:25]
        _print_section("REMEMBERED FIGURES")
        if not legends:
            print("None.")
        for actor_id, pressure in legends:
            legacy, profile, cult = _mythic_snapshot_for_actor(sim, world, actor_id)
            print(f"{_actor_ref_label(sim, world, actor_id, include_id=True)}")
            print(f"  legend_pressure={float(pressure):.1f}  mythic={legacy:.1f}")
            print(f"  profile: {_format_weight_map(profile, 8)}")
            if cult is not None:
                print(f"  cult={_cult_title_label(cult)}  status={_cult_status_label(cult)}  pressure={float(getattr(cult, 'legend_pressure', 0.0) or 0.0):.1f}")
                print(f"  domains: {_format_weight_map(getattr(cult, 'domain_weights', {}) or {}, 8)}")
                print(f"  traits: {_format_weight_map(getattr(cult, 'trait_weights', {}) or {}, 8)}")
            print()

    if _legendarium_section_enabled(sim, "LEGENDARIUM_PROTO_CULTS_ENABLED", True):
        _print_section("PROTO-CULTS AND ARCHETYPES")
        cults = [c for c in getattr(world, "proto_cults", {}).values() if not getattr(c, "failed", False)]
        if not cults:
            print("None.")
        for cult in sorted(cults, key=lambda c: float(getattr(c, "legend_pressure", 0.0) or 0.0), reverse=True)[:40]:
            subject_id = getattr(cult, "subject_actor_id", None)
            title = _cult_title_label(cult)
            print(f"{title}")
            if getattr(cult, "subject_kind", "actor") == "monster":
                monster = getattr(world, "monsters", {}).get(getattr(cult, "subject_monster_id", None))
                mname = getattr(monster, "name", getattr(cult, "subject_name", "Unknown monster"))
                print(f"  subject=monster:{mname} ({getattr(cult, 'subject_monster_id', '-')})  status={_cult_status_label(cult)}")
            else:
                print(f"  subject={_actor_ref_label(sim, world, subject_id, include_id=True)}  status={_cult_status_label(cult)}")
            if getattr(cult, "open_worship", False):
                catalyst = getattr(cult, "open_worship_actor_name", "") or "unknown catalyst"
                reason = getattr(cult, "open_worship_reason", "") or "influential adherent"
                print(f"  open_worship_catalyst={catalyst} ({reason})")
            print(f"  pressure={float(getattr(cult, 'legend_pressure', 0.0) or 0.0):.1f}  mythic={float(getattr(cult, 'mythic_legacy_score', 0.0) or 0.0):.1f}  regions={len(getattr(cult, 'known_region_ids', set()) or set())}")
            print(f"  mythic_profile: {_format_weight_map(getattr(cult, 'mythic_profile', {}) or {}, 8)}")
            print(f"  domains: {_format_weight_map(getattr(cult, 'domain_weights', {}) or {}, 8)}")
            print(f"  traits: {_format_weight_map(getattr(cult, 'trait_weights', {}) or {}, 8)}")
            affinities = sorted((getattr(cult, "hidden_affinity_by_actor_id", {}) or {}).items(), key=lambda item: float(item[1]), reverse=True)[:8]
            if affinities:
                print("  strongest actor affinities:")
                for aid, val in affinities:
                    print(f"    {_actor_ref_label(sim, world, aid)}={float(val):.2f}")
            print()

    if _legendarium_section_enabled(sim, "LEGENDARIUM_TOP_SONGS_ENABLED", True):
        _print_top_song_chart(sim, int(globals().get("TOP_SONG_CHART_COUNT", 10)))

    if _legendarium_section_enabled(sim, "LEGENDARIUM_CULTURAL_MEMORY_ENABLED", True):
        _print_section("CULTURAL MEMORY")
        cultural = [
            song for song in getattr(world, "songs", {}).values()
            if not getattr(song, "forgotten", False)
            and str(getattr(song, "song_type", "mythic") or "mythic").lower() in {"love", "folly", "personal", "existential", "pastoral", "protest", "labor", "tavern", "seasonal"}
        ]
        if cultural:
            counts = {}
            for song in cultural:
                st = str(getattr(song, "song_type", "personal") or "personal").lower()
                counts[st] = counts.get(st, 0) + 1
            print("Song types: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            rediscovered = [s for s in cultural if getattr(s, "rediscovered", False)]
            if rediscovered:
                print("Rediscovered cultural material:")
                for song in sorted(rediscovered, key=lambda s: float(getattr(s, "historical_weight", 0.0) or 0.0), reverse=True)[:10]:
                    composer = _actor_ref_label(sim, world, getattr(song, "composer_id", None), none_label="-")
                    print(f"  [{getattr(song, 'song_type', 'cultural')}] {getattr(song, 'title', 'Untitled')} — {composer}")
        else:
            print("None.")
        print()

    songs = [song for song in getattr(world, "songs", {}).values() if not getattr(song, "forgotten", False)]
    if _legendarium_section_enabled(sim, "LEGENDARIUM_SONGS_AND_MEMORY_ENABLED", True):
        _print_section("SONGS AND MEMORY")
        if not songs:
            print("None.")
        for song in sorted(songs, key=lambda s: (float(getattr(s, "popularity", 0.0) or 0.0), float(getattr(s, "historical_weight", 0.0) or 0.0)), reverse=True)[:40]:
            subjects = getattr(song, "subject_actor_ids", []) or []
            subject_text = ", ".join(_actor_ref_label(sim, world, aid) for aid in subjects) if subjects else (getattr(song, "subject_event", "") or "-")
            relic_id = getattr(song, "subject_relic_id", None)
            if relic_id is not None:
                relic = getattr(world, "relics", {}).get(relic_id)
                subject_text = getattr(relic, "name", f"relic {relic_id}")
            monster_id = getattr(song, "subject_monster_id", None)
            if monster_id is not None:
                monster = getattr(world, "monsters", {}).get(monster_id)
                subject_text = getattr(monster, "name", f"monster {monster_id}")
            composer = _actor_ref_label(sim, world, getattr(song, "composer_id", None), none_label="-")
            subject_deity = getattr(song, "subject_deity", None)
            if subject_deity is not None:
                subject_text = getattr(subject_deity, "value", getattr(subject_deity, "name", str(subject_deity)))
            visibility = str(getattr(song, "visibility", "public") or "public").lower()
            song_type = str(getattr(song, "song_type", "mythic" if visibility == "public" else "personal") or "mythic").lower()
            source_ref = str(getattr(song, "source_ref", "") or "")
            redisc = " yes" if bool(getattr(song, "rediscovered", False)) else " no"
            fame_credit = ""
            if song_type in {"personal", "love", "folly"} and hasattr(sim, "_song_public_credit_reached"):
                try:
                    if sim._song_public_credit_reached(song):
                        fame_credit = "  bard_fame_credit=yes"
                except Exception:
                    fame_credit = ""
            elif visibility == "private" and hasattr(sim, "_private_song_has_public_reach"):
                try:
                    if sim._private_song_has_public_reach(song):
                        fame_credit = "  bard_fame_credit=yes"
                except Exception:
                    fame_credit = ""
            print(f"{getattr(song, 'title', 'Untitled')}")
            print(f"  type={song_type}  visibility={visibility}  subject={subject_text}  composer={composer}  rediscovered={redisc.strip()}" + (f"  source={source_ref}" if source_ref else "") + fame_credit)
            print(f"  pop={float(getattr(song, 'popularity', 0.0) or 0.0):.1f}  weight={float(getattr(song, 'historical_weight', 0.0) or 0.0):.1f}  regions={len(getattr(song, 'known_region_ids', set()) or set())}  age={int(getattr(song, 'age_years', 0) or 0)}y  performances={int(getattr(song, 'performances', 0) or 0)}  bards={len(getattr(song, 'performer_actor_ids', set()) or set())}")
            if subjects and song_type == "mythic":
                aid = subjects[0]
                legacy, profile, cult = _mythic_snapshot_for_actor(sim, world, aid)
                print(f"  subject_mythic={legacy:.1f}  profile={_format_weight_map(profile, 5)}" + (f"  archetype={_cult_title_label(cult)}" if cult else ""))
            elif subjects:
                print("  subject_mythic=excluded_from_mythic_pipeline")
            print()

    if _legendarium_section_enabled(sim, "LEGENDARIUM_HYMNS_ENABLED", True):
        hymn_rows = []
        for deity, pressure in (getattr(world, "hymn_pressure_by_deity", {}) or {}).items():
            try:
                pval = float(pressure or 0.0)
            except Exception:
                pval = 0.0
            if pval > 0:
                hymn_rows.append((pval, deity))
        if hymn_rows:
            _print_section("HYMNS AND PUBLIC WORSHIP")
            for pressure, deity in sorted(hymn_rows, key=lambda item: item[0], reverse=True)[:10]:
                label = getattr(deity, "value", getattr(deity, "name", str(deity)))
                hymn_count = len([s for s in songs if str(getattr(s, "song_type", "") or "").lower() == "hymn" and getattr(s, "subject_deity", None) == deity])
                print(f"  {label} — hymn_pressure={pressure:.1f}; hymns={hymn_count}")
            print()

    if _legendarium_section_enabled(sim, "LEGENDARIUM_RELIC_MONSTER_FOLKLORE_ENABLED", True):
        _print_section("RELIC AND MONSTER FOLKLORE")
        relic_rows = []
        for relic in getattr(world, "relics", {}).values():
            if getattr(relic, "destroyed", False):
                continue
            pressure = float(getattr(world, "legend_pressure_by_relic_id", {}).get(getattr(relic, "id", None), 0.0) or 0.0)
            if pressure > 0 or int(getattr(relic, "revealed_tick", -1) or -1) >= 0 or int(getattr(relic, "released_tick", -1) or -1) >= 0:
                relic_rows.append((pressure, relic))
        if relic_rows:
            print("Relics in public memory:")
            for pressure, relic in sorted(relic_rows, key=lambda item: item[0], reverse=True)[:12]:
                print(f"  {getattr(relic, 'name', 'Relic')} — revealed={int(getattr(relic, 'revealed_tick', -1) or -1) >= 0} pressure={pressure:.1f} claims={len(getattr(relic, 'possession_history', []) or [])} failed={int(getattr(relic, 'failed_claims', 0) or 0)} deaths={int(getattr(relic, 'quest_deaths', 0) or 0)}")
        monster_rows = []
        for monster in getattr(world, "monsters", {}).values():
            if getattr(monster, "kind", None) == getattr(sim, "MonsterKind", object()).GOBLIN if hasattr(sim, "MonsterKind") else False:
                continue
            pressure = float(getattr(world, "legend_pressure_by_monster_id", {}).get(getattr(monster, "id", None), 0.0) or 0.0)
            score = pressure + int(getattr(monster, "eradication_survivals", 0) or 0) * 50 + int(getattr(monster, "monster_kills_adventurers", 0) or 0)
            if score > 0:
                monster_rows.append((score, pressure, monster))
        if monster_rows:
            print("Monster folklore:")
            for _score, pressure, monster in sorted(monster_rows, key=lambda item: item[0], reverse=True)[:12]:
                print(f"  {getattr(monster, 'name', 'Monster')} — pressure={pressure:.1f} eradication_survivals={int(getattr(monster, 'eradication_survivals', 0) or 0)} regions={len(getattr(monster, 'terror_region_ids', set()) or set())} living_god={bool(getattr(monster, 'worshipped_as_living_god', False))}")
        if not relic_rows and not monster_rows:
            print("None.")
        print()

    if _legendarium_section_enabled(sim, "LEGENDARIUM_FAITH_DOUBT_ENABLED", True):
        _print_section("FAITH DOUBT AND CULT AFFINITY")
        living = list(world.living_actors()) if hasattr(world, "living_actors") else list(getattr(world, "actors", {}).values())
        current_pc_members = [a for a in living if getattr(a, "current_protocult_id", None) is not None]
        print(f"Current protocult members: {len(current_pc_members)}")
        doubt = sorted([a for a in living if float(getattr(a, "faith_doubt", 0.0) or 0.0) > 0.0], key=lambda a: float(getattr(a, "faith_doubt", 0.0) or 0.0), reverse=True)[:25]
        if doubt:
            print("Highest faith doubt:")
            for actor in doubt:
                deity = getattr(getattr(actor, "deity", None), "value", getattr(getattr(actor, "deity", None), "name", getattr(actor, "deity", "-")))
                print(f"  {_actor_ref_label(sim, world, getattr(actor, 'id', None), include_id=True)} — doubt={float(getattr(actor, 'faith_doubt', 0.0) or 0.0):.2f}; religion={deity}; protocult={_actor_protocult_label(world, actor)}; region={getattr(actor, 'region_id', '-')}{_faith_doubt_driver_label(actor, 4)}")
        else:
            print("Highest faith doubt: none.")
        print()

        affinity_rows = []
        cults_by_id = getattr(world, "proto_cults", {}) or {}
        for actor in living:
            aff = getattr(actor, "cult_affinity", {}) or {}
            for cid, val in aff.items():
                if float(val or 0.0) <= 0.0:
                    continue
                cult = cults_by_id.get(cid)
                if cult is None:
                    try:
                        cult = cults_by_id.get(int(cid))
                    except Exception:
                        cult = None
                affinity_rows.append((float(val), actor, cult, cid))
        affinity_rows.sort(key=lambda row: row[0], reverse=True)
        if affinity_rows:
            print("Strongest actor cult affinities:")
            for val, actor, cult, cid in affinity_rows[:25]:
                cult_name = _cult_title_label(cult) if cult is not None else str(cid)
                current_pc = _actor_protocult_label(world, actor, none_label="—")
                marker = " *current" if current_pc == cult_name else ""
                print(f"  {_actor_ref_label(sim, world, getattr(actor, 'id', None), include_id=True)} — {cult_name}: {val:.2f}{marker}")
        else:
            print("Strongest actor cult affinities: none.")

def write_legendarium(sim, years) -> Path:
    seed = sim.world.seed_used
    filename = _legendarium_base_name(str(seed), str(years)) + ".txt"
    output_dir = Path(getattr(sim.world, "output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    if not _legendarium_output_enabled(sim):
        return output_path

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_legendarium(sim, years)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(buffer.getvalue())

    return output_path


def write_summary(sim, years) -> Path:
    seed = sim.world.seed_used
    filename = _summary_base_name(seed, str(years)) + ".txt"
    output_dir = Path(getattr(sim.world, "output_dir", "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    if _summary_output_enabled(sim):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_summary(sim, years)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(buffer.getvalue())

    if _legendarium_output_enabled(sim):
        write_legendarium(sim, years)

    if _csv_metrics_enabled(sim):
        _write_summary_metrics_csv(sim, years, output_path)
    if _csv_history_enabled(sim):
        _write_history_csv(sim, output_path)
    if _csv_events_enabled(sim):
        _write_events_csv(sim, output_path)
    return output_path
