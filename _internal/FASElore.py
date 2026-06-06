from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import sys
import time
from FASEclass import Role, MonsterKind
from FASEimm import GodProfile, ensure_actor_religion_tracking, set_actor_protocult_membership, worship_duration_years
_G = globals()


def _cfg_value(name: str, default):
    """Read live config when available, falling back to lore module globals/default."""
    for module_name in ("FASEcfg", "config", "fantfarm_config"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            return getattr(module, name)
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("config_v") and hasattr(module, name):
            return getattr(module, name)
    return _G.get(name, default)


def _cfg_bool(name: str, default: bool = True) -> bool:
    return bool(_cfg_value(name, default))


@dataclass
class Song:
    id: int
    title: str
    composer_id: Optional[int]
    subject_actor_ids: List[int] = field(default_factory=list)
    subject_relic_id: Optional[int] = None
    subject_event: str = ""
    origin_region_id: int = -1
    known_region_ids: Set[int] = field(default_factory=set)
    subject_deity: Any = None
    # Deprecated compatibility field. Older saves may contain this, but new
    # code should not assign/display/use it as song subject or affiliation.
    deity: Any = None
    tone: str = "heroic"
    popularity: float = 1.0
    historical_weight: float = 1.0
    created_tick: int = 0
    last_performed_tick: int = 0
    performances: int = 0
    age_years: int = 0
    forgotten: bool = False
    visibility: str = "public"
    song_type: str = "mythic"  # mythic, love, folly, personal, relic
    fame_credit_actor_id: Optional[int] = None
    fame_credit_awarded: bool = False
    cultural_effect_applied_count: int = 0
    rediscovered: bool = False
    source_ref: str = ""
    performer_actor_ids: Set[int] = field(default_factory=set)
    subject_monster_id: Optional[int] = None
    anonymized_subject: bool = False


@dataclass
class ProtoCult:
    id: int
    name: str
    subject_actor_id: int
    subject_name: str
    origin_region_id: int
    subject_kind: str = "actor"
    subject_monster_id: Optional[int] = None
    deity_object: Any = None
    legend_pressure: float = 0.0
    mythic_legacy_score: float = 0.0
    mythic_profile: Dict[str, float] = field(default_factory=dict)
    domain_weights: Dict[str, float] = field(default_factory=dict)
    trait_weights: Dict[str, float] = field(default_factory=dict)
    public_title: str = ""
    hidden_affinity_by_actor_id: Dict[int, float] = field(default_factory=dict)
    hidden_commoner_affinity_by_region: Dict[int, int] = field(default_factory=dict)
    known_region_ids: Set[int] = field(default_factory=set)
    founded_tick: int = 0
    last_pressure_tick: int = 0
    ascended: bool = False
    open_worship: bool = False
    open_worship_tick: int = -1
    open_worship_actor_id: Optional[int] = None
    open_worship_actor_name: str = ""
    open_worship_reason: str = ""
    formalized: bool = False
    failed: bool = False


class LoreMixin:
    """Bardic cultural memory, songs, legend pressure, and proto-cult scaffolding.

    This intentionally begins as a light system. It creates durable cultural
    artifacts first; deification is built from accumulated memory instead of
    spawning new gods from nothing.
    """

    def _ensure_lore_state(self) -> None:
        world = getattr(self, "world", None)
        if world is None:
            return
        if not hasattr(world, "songs") or getattr(world, "songs", None) is None:
            world.songs = {}
        if not hasattr(world, "song_title_norm_cache") or getattr(world, "song_title_norm_cache", None) is None:
            world.song_title_norm_cache = None
        if not hasattr(world, "next_song_id"):
            world.next_song_id = 1
        if not hasattr(world, "legend_pressure_by_actor_id") or getattr(world, "legend_pressure_by_actor_id", None) is None:
            world.legend_pressure_by_actor_id = {}
        if not hasattr(world, "proto_cults") or getattr(world, "proto_cults", None) is None:
            world.proto_cults = {}
        if not hasattr(world, "next_proto_cult_id"):
            world.next_proto_cult_id = 1
        if not hasattr(world, "last_lore_tick"):
            world.last_lore_tick = -999999
        if not hasattr(world, "last_deification_check_tick"):
            world.last_deification_check_tick = -999999
        if not hasattr(world, "ai_god_last_action_tick") or getattr(world, "ai_god_last_action_tick", None) is None:
            world.ai_god_last_action_tick = {}
        if not hasattr(world, "last_open_worship_check_tick"):
            world.last_open_worship_check_tick = -999999
        if not hasattr(world, "last_morgue_rediscovery_tick"):
            world.last_morgue_rediscovery_tick = -999999
        if not hasattr(world, "rediscovered_story_ids") or getattr(world, "rediscovered_story_ids", None) is None:
            world.rediscovered_story_ids = set()
        if not hasattr(world, "legend_pressure_by_relic_id") or getattr(world, "legend_pressure_by_relic_id", None) is None:
            world.legend_pressure_by_relic_id = {}
        if not hasattr(world, "legend_pressure_by_monster_id") or getattr(world, "legend_pressure_by_monster_id", None) is None:
            world.legend_pressure_by_monster_id = {}
        if not hasattr(world, "hymn_pressure_by_deity") or getattr(world, "hymn_pressure_by_deity", None) is None:
            world.hymn_pressure_by_deity = {}

    def _lore_tick(self) -> None:
        self._ensure_lore_state()
        world = self.world
        cadence = int(_cfg_value("LORE_TICK_INTERVAL", _G.get("TICKS_PER_MONTH", 120)))
        offset = int(_cfg_value("LORE_TICK_OFFSET_TICKS", _cfg_value("MONTH_PHASE_LORE_OFFSET_TICKS", 0)))
        if cadence > 1 and ((world.tick - offset) % cadence) != 0:
            return

        profiling = _cfg_bool("LORE_PROFILING_ENABLED", False)
        slow_stage_seconds = float(_cfg_value("LORE_PROFILE_SLOW_STAGE_SECONDS", 0.25))
        max_records = max(1, int(_cfg_value("LORE_PROFILE_MAX_RECORDS", 36)))
        log_slow = _cfg_bool("LORE_PROFILE_LOG_SLOW_STAGES", False)

        if profiling and not hasattr(world, "lore_profile_records"):
            world.lore_profile_records = []
        stage_records = []

        def run_stage(label, fn):
            if not profiling:
                return fn()
            start = time.perf_counter()
            try:
                return fn()
            finally:
                elapsed = time.perf_counter() - start
                stage_records.append((label, elapsed))
                if log_slow and elapsed >= slow_stage_seconds:
                    try:
                        world.log(
                            f"Lore profiler: {label} took {elapsed:.3f}s at tick {world.tick}.",
                            importance=1,
                            category="profiling",
                        )
                    except Exception:
                        pass

        total_start = time.perf_counter() if profiling else None

        run_stage("decay_songs", self._decay_songs)
        run_stage("bardic_memory", self._bardic_memory_turn)
        run_stage("song_legend_pressure", self._apply_song_legend_pressure)
        run_stage("proto_cults", self._update_proto_cults)
        run_stage("religious_drift", self._update_actor_religious_drift)

        # God-making lives in FASEimm/immortals. When present, it replaces the
        # old hidden-ascension/open-worship bridge.
        if hasattr(self, "_maybe_trigger_apotheosis"):
            run_stage("apotheosis", self._maybe_trigger_apotheosis)
        else:
            run_stage("ascend_proto_cult", self._maybe_ascend_proto_cult)
            run_stage("open_worship", self._maybe_open_worship)

        if profiling:
            total_elapsed = time.perf_counter() - total_start
            try:
                songs = len([s for s in getattr(world, "songs", {}).values() if not getattr(s, "forgotten", False)])
            except Exception:
                songs = len(getattr(world, "songs", {}) or {})
            record = {
                "tick": int(getattr(world, "tick", 0) or 0),
                "total_seconds": float(total_elapsed),
                "stages": [(name, float(seconds)) for name, seconds in stage_records],
                "songs": int(songs),
                "proto_cults": len(getattr(world, "proto_cults", {}) or {}),
                "living_bards": len([
                    a for a in world.living_actors()
                    if getattr(a, "role", None) == Role.BARD and not getattr(a, "in_school", False)
                ]) if hasattr(world, "living_actors") else 0,
            }
            records = list(getattr(world, "lore_profile_records", []) or [])
            records.append(record)
            world.lore_profile_records = records[-max_records:]

    def _song_age_years(self, song: Song) -> int:
        return max(0, int((getattr(self.world, "tick", 0) - getattr(song, "created_tick", 0)) // _G.get("TICKS_PER_YEAR", 1440)))

    def _decay_songs(self) -> None:
        self._ensure_lore_state()
        world = self.world
        decay = float(_G.get("SONG_POPULARITY_MONTHLY_DECAY", 0.965))
        preserve_floor = float(_G.get("SONG_HISTORICAL_WEIGHT_DECAY_FLOOR", 0.35))
        forget_under = float(_G.get("SONG_FORGET_POPULARITY_UNDER", 0.08))
        for song in list(world.songs.values()):
            if getattr(song, "forgotten", False):
                continue
            song.age_years = self._song_age_years(song)
            # Historical weight makes very good songs decay slowly; popularity still breathes.
            resistance = max(preserve_floor, min(0.95, song.historical_weight / 200.0))
            effective_decay = 1.0 - ((1.0 - decay) * (1.0 - resistance))
            song.popularity *= effective_decay
            if song.popularity < forget_under and song.age_years > 3 and self.rng.random() < 0.35:
                song.forgotten = True
                cache = getattr(world, "song_title_norm_cache", None)
                if isinstance(cache, set):
                    cache.discard(self._normalize_song_title(song.title))
                world.log(f"{song.title} fades from living memory.", importance=1, category="lore")

    def _build_bardic_song_indexes(self) -> Dict[str, Any]:
        """Build tick-local song indexes for bard composition checks.

        These replace repeated full world.songs scans inside bard/candidate
        loops. The indexes are intentionally rebuilt per bardic memory turn so
        they stay simple and cannot drift across long simulations.
        """
        index: Dict[str, Any] = {
            "bard_subject_song_type": set(),
            "bard_subject_visibility": set(),
            "recent_public_subject_counts": {},
            "bard_relic_song_type": set(),
            "bard_monster_song_type": set(),
        }
        now = int(getattr(self.world, "tick", 0) or 0)
        window_years = float(_G.get("BARD_RECENT_SONG_WINDOW_YEARS", 20))
        window_ticks = int(window_years * _G.get("TICKS_PER_YEAR", 1440))
        for song in getattr(self.world, "songs", {}).values():
            self._index_song_for_bardic_memory(song, index, now=now, window_ticks=window_ticks)
        return index

    def _index_song_for_bardic_memory(self, song, index: Optional[Dict[str, Any]], now: Optional[int] = None, window_ticks: Optional[int] = None) -> None:
        if song is None or index is None or getattr(song, "forgotten", False):
            return
        composer_id = getattr(song, "composer_id", None)
        visibility = str(getattr(song, "visibility", "public") or "public").lower()
        song_type = str(getattr(song, "song_type", visibility) or visibility).lower()
        subjects = list(getattr(song, "subject_actor_ids", []) or [])
        for subject_id in subjects:
            index.setdefault("bard_subject_song_type", set()).add((composer_id, subject_id, song_type))
            index.setdefault("bard_subject_visibility", set()).add((composer_id, subject_id, visibility))
            try:
                int_subject_id = int(subject_id)
                index.setdefault("bard_subject_song_type", set()).add((composer_id, int_subject_id, song_type))
                index.setdefault("bard_subject_visibility", set()).add((composer_id, int_subject_id, visibility))
            except Exception:
                int_subject_id = subject_id
            if visibility == "public":
                if now is None:
                    now = int(getattr(self.world, "tick", 0) or 0)
                if window_ticks is None:
                    window_years = float(_G.get("BARD_RECENT_SONG_WINDOW_YEARS", 20))
                    window_ticks = int(window_years * _G.get("TICKS_PER_YEAR", 1440))
                created = int(getattr(song, "created_tick", 0) or 0)
                if window_ticks <= 0 or now - created <= window_ticks:
                    counts = index.setdefault("recent_public_subject_counts", {})
                    counts[subject_id] = int(counts.get(subject_id, 0) or 0) + 1
                    if int_subject_id != subject_id:
                        counts[int_subject_id] = int(counts.get(int_subject_id, 0) or 0) + 1
        relic_id = getattr(song, "subject_relic_id", None)
        if relic_id is not None:
            index.setdefault("bard_relic_song_type", set()).add((composer_id, relic_id, song_type))
        monster_id = getattr(song, "subject_monster_id", None)
        if monster_id is not None:
            index.setdefault("bard_monster_song_type", set()).add((composer_id, monster_id, song_type))

    def _bardic_memory_turn(self) -> None:
        world = self.world
        # Tick-local cache for expensive mythic actor profiles. Bard subject selection
        # may evaluate the same actors repeatedly across several bards in one lore turn;
        # those profiles are stable enough within this turn to avoid rebuilding them.
        mythic_profile_cache: Dict[int, Dict[str, float]] = {}
        bardic_song_index = self._build_bardic_song_indexes()
        # Tick-local song-by-subject index for _mythic_legacy_profile_for_actor.
        # Avoids two O(songs) list comprehensions per actor per lore-tick.
        _songs_by_subject: Dict[int, List] = {}
        _credited_songs_by_actor: Dict[int, List] = {}
        for _s in getattr(self.world, "songs", {}).values():
            if getattr(_s, "forgotten", False):
                continue
            if str(getattr(_s, "visibility", "public") or "public").lower() != "private" and str(getattr(_s, "song_type", "mythic") or "mythic").lower() == "mythic":
                for _aid in (getattr(_s, "subject_actor_ids", []) or []):
                    _songs_by_subject.setdefault(_aid, []).append(_s)
            _cid = int(getattr(_s, "fame_credit_actor_id", -1) or -1)
            if _cid >= 0 and str(getattr(_s, "song_type", "mythic") or "mythic").lower() != "mythic" and self._song_public_credit_reached(_s):
                _credited_songs_by_actor.setdefault(_cid, []).append(_s)
        self.world._lore_songs_by_subject = _songs_by_subject
        self.world._lore_credited_songs_by_actor = _credited_songs_by_actor
        # Tick-local founder/ruler sets for _actor_public_song_eligibility.
        # Avoids O(party_history + polity_history + parties) scan per actor.
        _party_founder_ids: set = {
            getattr(ph, "founder_id", None)
            for ph in getattr(self.world, "party_history", {}).values()
            if getattr(ph, "founder_id", None) is not None
        }
        _polity_founder_ids: set = {
            getattr(ph, "founder_id", None)
            for ph in getattr(self.world, "polity_history", {}).values()
            if getattr(ph, "founder_id", None) is not None
        }
        _polity_ruler_ids: set = {
            getattr(ph, "current_ruler_id", None)
            for ph in getattr(self.world, "polity_history", {}).values()
            if getattr(ph, "current_ruler_id", None) is not None
        }
        _large_party_leader_ids: set = {
            getattr(pty, "leader_id", None)
            for pty in getattr(self.world, "parties", {}).values()
            if getattr(pty, "leader_id", None) is not None
            and len(getattr(pty, "member_ids", []) or []) >= int(_G.get("BARD_PUBLIC_SUBJECT_MIN_PARTY_SIZE", 8))
        }
        self.world._lore_party_founder_ids = _party_founder_ids
        self.world._lore_polity_founder_ids = _polity_founder_ids
        self.world._lore_polity_ruler_ids = _polity_ruler_ids
        self.world._lore_large_party_leader_ids = _large_party_leader_ids
        # Tick-local caches for _mythic_legacy_profile_for_actor history scans.
        # party_history and polity_history grow unboundedly; indexing by actor ID
        # avoids O(history) linear scans per actor per profile build.
        _party_history_by_founder: Dict[int, list] = {}
        _party_history_by_actor: Dict[int, list] = {}  # all parties involving actor as leader
        for _ph in getattr(self.world, "party_history", {}).values():
            fid = getattr(_ph, "founder_id", None)
            if fid is not None:
                _party_history_by_founder.setdefault(fid, []).append(_ph)
            lid = getattr(_ph, "leader_id", None)
            if lid is not None:
                _party_history_by_actor.setdefault(lid, []).append(_ph)
        _current_party_by_leader: Dict[int, object] = {}
        for _pty in getattr(self.world, "parties", {}).values():
            lid = getattr(_pty, "leader_id", None)
            if lid is not None:
                _current_party_by_leader[lid] = _pty
        _polity_history_by_actor: Dict[int, list] = {}
        for _polh in getattr(self.world, "polity_history", {}).values():
            for _attr in ("founder_id", "current_ruler_id"):
                _aid = getattr(_polh, _attr, None)
                if _aid is not None:
                    _polity_history_by_actor.setdefault(_aid, []).append(_polh)
        self.world._lore_party_history_by_founder = _party_history_by_founder
        self.world._lore_current_party_by_leader = _current_party_by_leader
        self.world._lore_polity_history_by_actor = _polity_history_by_actor
        # Mark the tick so _update_proto_cults skips rebuilding these same indexes.
        self.world._lore_songs_index_tick = world.tick
        bards = [a for a in world.living_actors() if getattr(a, "role", None) == Role.BARD and not getattr(a, "in_school", False)]
        if not bards:
            return
        self.rng.shuffle(bards)
        max_bards = int(_G.get("LORE_MAX_BARDS_PER_TICK", 12))
        for bard in bards[:max_bards]:
            last = int(getattr(bard, "bard_last_song_tick", -999999))
            if world.tick - last < int(_G.get("BARD_SONG_COOLDOWN_TICKS", _G.get("TICKS_PER_MONTH", 120))):
                continue
            chance = float(_G.get("BARD_SONG_ACTION_CHANCE", 0.20))
            chance += max(0, getattr(bard, "charisma", 10) - 10) * 0.01
            chance += max(0, getattr(bard, "wisdom", 10) - 10) * 0.005
            if self.rng.random() >= min(0.65, chance):
                continue
            # First maintain bard culture: each bard has a personal target
            # for top-chart standards and total repertoire size. Learning a song
            # may immediately become the performed song for this turn.
            pressure_song = self._bard_repertoire_pressure_song(bard)
            if pressure_song is not None:
                self._perform_song(bard, pressure_song)
                bard.bard_last_song_tick = world.tick
                continue

            known_song = self._choose_song_for_bard(bard)
            compose_chance = float(_G.get("BARD_COMPOSE_NEW_SONG_CHANCE", 0.08))
            total_target, _top_target = self._bard_repertoire_targets(bard)
            if len(self._bard_known_song_ids(bard)) < total_target:
                compose_chance = max(compose_chance, float(_G.get("BARD_REPERTOIRE_COMPOSE_FILL_CHANCE", 0.22)))
            if known_song is not None and self.rng.random() >= compose_chance:
                self._perform_song(bard, known_song)
            else:
                composed = self._compose_song(bard, profile_cache=mythic_profile_cache, song_index=bardic_song_index)
                if composed is None and known_song is not None and bool(_G.get("BARD_COMPOSITION_FALLBACK_TO_PERFORMANCE", True)):
                    self._perform_song(bard, known_song)
            bard.bard_last_song_tick = world.tick

    def _song_subject_name(self, actor_id: int) -> str:
        actor = self.resolve_actor(actor_id) if hasattr(self, "resolve_actor") else self.world.actors.get(actor_id)
        if actor is not None:
            return actor.short_name() if hasattr(actor, "short_name") else str(actor_id)
        tomb = (getattr(self.world, "dead_actor_index", {}) or {}).get(actor_id, {})
        return str(tomb.get("name") or f"Actor {actor_id}")

    def _deity_abbrev_for_lore(self, deity) -> str:
        name = str(getattr(deity, "value", getattr(deity, "name", deity)) or "").strip()
        aliases = {
            "Lord of Light": "LOL",
            "Lord of Darkness": "LOD",
            "God of Chance": "GOC",
        }
        if name in aliases:
            return aliases[name]
        letters = "".join(part[0].upper() for part in name.replace("'", "").split() if part)
        return (letters or "GOD")[:5]

    def _bard_known_song_ids(self, bard) -> Set[int]:
        if not isinstance(getattr(bard, "known_song_ids", None), list):
            bard.known_song_ids = []
        clean: List[int] = []
        seen: Set[int] = set()
        for raw in getattr(bard, "known_song_ids", []) or []:
            try:
                sid = int(raw)
            except Exception:
                continue
            if sid in seen:
                continue
            if sid in getattr(self.world, "songs", {}):
                clean.append(sid)
                seen.add(sid)
        if clean != list(getattr(bard, "known_song_ids", []) or []):
            bard.known_song_ids = clean
        return set(clean)

    def _bard_repertoire_targets(self, bard) -> Tuple[int, int]:
        """Stable per-bard repertoire goals without adding new Actor fields.

        Bards should not all know the same catalogue. The target is derived
        from durable actor properties, so it is stable across ticks/saves but
        still varies across the bard population.
        """
        min_total = int(_G.get("BARD_REPERTOIRE_MIN_SIZE", 12))
        max_total = int(_G.get("BARD_REPERTOIRE_MAX_SIZE", 32))
        if max_total < min_total:
            max_total = min_total
        min_top = int(_G.get("BARD_TOP_SONG_TARGET_MIN", 5))
        max_top = int(_G.get("BARD_TOP_SONG_TARGET_MAX", 8))
        if max_top < min_top:
            max_top = min_top
        chart_count = max(1, int(_G.get("TOP_SONG_CHART_COUNT", 10)))
        max_top = min(max_top, chart_count, max_total)
        min_top = min(min_top, max_top)
        bid = int(getattr(bard, "id", 0) or 0)
        luck = int(getattr(bard, "luck", 10) or 10)
        charisma = int(getattr(bard, "charisma", 10) or 10)
        wisdom = int(getattr(bard, "wisdom", 10) or 10)
        total_span = max_total - min_total + 1
        top_span = max_top - min_top + 1
        total_target = min_total + ((bid * 7 + luck * 3 + wisdom) % total_span)
        top_target = min_top + ((bid * 5 + charisma + luck) % top_span)
        return total_target, top_target

    def _trim_bard_repertoire(self, bard) -> None:
        if not isinstance(getattr(bard, "known_song_ids", None), list):
            bard.known_song_ids = []
            return
        max_rep = int(_G.get("BARD_REPERTOIRE_MAX_SIZE", 32))
        if max_rep <= 0:
            bard.known_song_ids = []
            return
        seen: Set[int] = set()
        cleaned: List[int] = []
        for raw in getattr(bard, "known_song_ids", []) or []:
            try:
                sid = int(raw)
            except Exception:
                continue
            if sid in seen or sid not in getattr(self.world, "songs", {}):
                continue
            cleaned.append(sid)
            seen.add(sid)
        if len(cleaned) > max_rep:
            top_ids = [int(getattr(song, "id", -1) or -1) for song in self._top_song_chart()]
            keep: List[int] = []
            for sid in cleaned:
                if sid in top_ids and sid not in keep:
                    keep.append(sid)
            for sid in reversed(cleaned):
                if len(keep) >= max_rep:
                    break
                if sid not in keep:
                    keep.insert(0, sid)
            cleaned = keep[-max_rep:]
        bard.known_song_ids = cleaned

    def _learn_song_for_bard(self, bard, song: Optional[Song]) -> bool:
        if song is None or not bool(_G.get("BARD_REPERTOIRE_ENABLED", True)):
            return False
        if not isinstance(getattr(bard, "known_song_ids", None), list):
            bard.known_song_ids = []
        sid = int(getattr(song, "id", -1) or -1)
        if sid < 0:
            return False
        if sid in self._bard_known_song_ids(bard):
            return False
        bard.known_song_ids.append(sid)
        self._trim_bard_repertoire(bard)
        return True

    def _top_song_chart(self) -> List[Song]:
        # Cache per tick: _top_song_chart is called 3-5 times per active bard
        # (from _bard_repertoire_pressure_song, _choose_missing_top_song_for_bard,
        # _trim_bard_repertoire). With up to 12 bards per lore tick that's 36-60
        # redundant sorts. Cache keyed by tick auto-invalidates each tick.
        world = getattr(self, "world", None)
        if world is not None:
            cached_tick = getattr(world, "_lore_top_chart_tick", -1)
            if cached_tick == world.tick:
                return getattr(world, "_lore_top_chart_cache", [])
        count = max(1, int(_G.get("TOP_SONG_CHART_COUNT", 10)))
        songs = [s for s in getattr(self.world, "songs", {}).values() if not getattr(s, "forgotten", False)]
        songs.sort(
            key=lambda song: (
                float(getattr(song, "popularity", 0.0) or 0.0),
                float(getattr(song, "historical_weight", 0.0) or 0.0),
                int(getattr(song, "performances", 0) or 0),
            ),
            reverse=True,
        )
        result = songs[:count]
        if world is not None:
            world._lore_top_chart_cache = result
            world._lore_top_chart_tick = world.tick
        return result

    def _weighted_song_choice(self, weighted: List[Tuple[float, Song]]) -> Optional[Song]:
        weighted = [(max(0.0, float(weight)), song) for weight, song in weighted if song is not None and float(weight or 0.0) > 0]
        if not weighted:
            return None
        total = sum(weight for weight, _song in weighted)
        if total <= 0:
            return None
        roll = self.rng.random() * total
        acc = 0.0
        for weight, song in weighted:
            acc += weight
            if roll <= acc:
                return song
        return weighted[-1][1]

    def _choose_missing_top_song_for_bard(self, bard) -> Optional[Song]:
        known = self._bard_known_song_ids(bard)
        chart = self._top_song_chart()
        missing = [(rank, song) for rank, song in enumerate(chart, start=1) if int(getattr(song, "id", -1) or -1) not in known]
        if not missing:
            return None
        flatness = float(_G.get("BARD_TOP_SONG_RANK_WEIGHT_FLATNESS", 0.65))
        flatness = max(0.0, min(1.0, flatness))
        max_rank = max(1, len(chart))
        weighted: List[Tuple[float, Song]] = []
        for rank, song in missing:
            rank_weight = (max_rank + 1 - rank)
            weight = 1.0 + (rank_weight * flatness)
            # #1 is likely, not mandatory. Local/deity relevance can beat pure chart rank.
            if getattr(bard, "region_id", None) in getattr(song, "known_region_ids", set()):
                weight += 1.0
            weighted.append((weight, song))
        return self._weighted_song_choice(weighted)

    def _choose_repertoire_fill_song_for_bard(self, bard) -> Optional[Song]:
        known = self._bard_known_song_ids(bard)
        songs = [s for s in getattr(self.world, "songs", {}).values() if not getattr(s, "forgotten", False) and int(getattr(s, "id", -1) or -1) not in known]
        if not songs:
            return None
        weighted: List[Tuple[float, Song]] = []
        for song in songs:
            weight = 1.0
            weight += float(getattr(song, "popularity", 0.0) or 0.0) * 0.25
            weight += float(getattr(song, "historical_weight", 0.0) or 0.0) * 0.03
            if getattr(bard, "region_id", None) in getattr(song, "known_region_ids", set()):
                weight += 4.0
            age = int(getattr(song, "age_years", self._song_age_years(song)) or 0)
            if age <= 3:
                weight += 2.0
            weighted.append((weight, song))
        return self._weighted_song_choice(weighted)

    def _bard_repertoire_pressure_song(self, bard) -> Optional[Song]:
        if not bool(_G.get("BARD_REPERTOIRE_ENABLED", True)):
            return None
        known = self._bard_known_song_ids(bard)
        total_target, top_target = self._bard_repertoire_targets(bard)
        top_ids = {int(getattr(song, "id", -1) or -1) for song in self._top_song_chart()}
        known_top = len(known.intersection(top_ids))
        if known_top < top_target and self.rng.random() < float(_G.get("BARD_TOP_SONG_LEARN_CHANCE", 0.60)):
            song = self._choose_missing_top_song_for_bard(bard)
            if song is not None and self._learn_song_for_bard(bard, song):
                return song
        if len(known) < total_target and self.rng.random() < float(_G.get("BARD_REPERTOIRE_FILL_CHANCE", 0.45)):
            song = self._choose_repertoire_fill_song_for_bard(bard)
            if song is not None and self._learn_song_for_bard(bard, song):
                return song
        return None

    def _choose_song_for_bard(self, bard) -> Optional[Song]:
        songs = [s for s in getattr(self.world, "songs", {}).values() if not getattr(s, "forgotten", False)]
        if not songs:
            return None
        known_ids = self._bard_known_song_ids(bard)
        scored = []
        for song in songs:
            sid = int(getattr(song, "id", -1) or -1)
            performers = set(getattr(song, "performer_actor_ids", set()) or set())
            score = float(getattr(song, "popularity", 0.0))
            score += float(getattr(song, "historical_weight", 0.0)) * 0.08
            score += len(performers) * float(_G.get("BARD_UNIQUE_PERFORMER_WEIGHT", 1.25))
            score += len(getattr(song, "known_region_ids", set()) or set()) * float(_G.get("BARD_REGION_SPREAD_WEIGHT", 1.4))
            if sid in known_ids:
                score += float(_G.get("BARD_KNOWN_SONG_BONUS", 10.0))
            else:
                score *= float(_G.get("BARD_UNKNOWN_SONG_PENALTY", 0.55))
                if getattr(bard, "region_id", None) in getattr(song, "known_region_ids", set()):
                    score += 5.0
            if getattr(bard, "region_id", None) in getattr(song, "known_region_ids", set()):
                score += 4.0
            if getattr(bard, "id", None) in getattr(song, "subject_actor_ids", []):
                score += 8.0
            personal_ids = set(getattr(bard, "children_ids", []) or [])
            for attr in ("mother_id", "father_id", "spouse_id", "best_friend_id", "nemesis_id", "revenge_target_id", "revenge_for_actor_id"):
                val = getattr(bard, attr, None)
                if val is not None:
                    personal_ids.add(val)
            party = self.world.parties.get(getattr(bard, "party_id", None)) if getattr(bard, "party_id", None) is not None else None
            if party is not None:
                personal_ids.update(getattr(party, "member_ids", []) or [])
            if personal_ids.intersection(set(getattr(song, "subject_actor_ids", []) or [])):
                score += 10.0
            # Stale megahits should remain possible, not automatic.
            age = int(getattr(song, "age_years", self._song_age_years(song)) or 0)
            stale_age = int(_G.get("BARD_STALE_HIT_AGE_YEARS", 12))
            if age >= stale_age and int(getattr(song, "performances", 0) or 0) > len(performers) * 3:
                score *= float(_G.get("BARD_STALE_HIT_EXTRA_DECAY", 0.985))
            score += self.rng.random() * max(1.0, getattr(bard, "luck", 10) / 10.0)
            if score > 0:
                scored.append((score, song))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        pool_size = max(1, int(_G.get("BARD_PERFORMANCE_CANDIDATE_POOL", 8)))
        exponent = max(0.10, float(_G.get("BARD_PERFORMANCE_SCORE_EXPONENT", 0.75)))
        pool = scored[:pool_size]
        chosen = self._weighted_song_choice([(max(0.01, score) ** exponent, song) for score, song in pool]) or pool[0][1]
        if bool(_G.get("BARD_REPERTOIRE_ENABLED", True)) and int(getattr(chosen, "id", -1) or -1) not in known_ids:
            local = getattr(bard, "region_id", None) in getattr(chosen, "known_region_ids", set())
            learn_chance = float(_G.get("BARD_LEARN_REGIONAL_SONG_CHANCE", 0.22)) if local else float(_G.get("BARD_LEARN_GLOBAL_SONG_CHANCE", 0.08))
            learn_chance += min(0.12, max(0, getattr(bard, "charisma", 10) - 10) * 0.01)
            if self.rng.random() < learn_chance:
                self._learn_song_for_bard(bard, chosen)
        return chosen

    def _perform_song(self, bard, song: Song) -> None:
        if not isinstance(getattr(bard, "known_song_ids", None), list):
            bard.known_song_ids = []
        sid = int(getattr(song, "id", -1) or -1)
        if sid >= 0 and sid not in set(bard.known_song_ids):
            bard.known_song_ids.append(sid)
            self._trim_bard_repertoire(bard)
        if not hasattr(song, "performer_actor_ids") or getattr(song, "performer_actor_ids", None) is None:
            song.performer_actor_ids = set()
        try:
            song.performer_actor_ids.add(int(getattr(bard, "id")))
        except Exception:
            pass
        song.performances += 1
        song.last_performed_tick = self.world.tick
        song.known_region_ids.add(getattr(bard, "region_id", getattr(song, "origin_region_id", -1)))
        boost = 1.0 + max(0, getattr(bard, "charisma", 10) - 10) * 0.10 + max(0, getattr(bard, "level", 1) - 1) * 0.15
        if getattr(bard, "first_in_class_year", None) is not None:
            boost += 0.75
        song.popularity += boost
        song.historical_weight += boost * 0.35
        self._apply_cultural_song_effect(song, bard)
        if self.rng.random() < float(_G.get("BARD_SONG_LOG_CHANCE", 0.10)):
            self.world.log(f"{bard.short_name()} performs {song.title} in {self.world.region_name(bard.region_id)}.", importance=1, category="lore")

    def _local_faith_share_for_deity(self, region_id: int, deity) -> float:
        if deity is None:
            return 0.0
        faith = getattr(self.world, "commoner_faith_by_region", {}).get(region_id, {})
        if not isinstance(faith, dict) or not faith:
            return 0.0
        total = sum(max(0, int(v or 0)) for v in faith.values())
        if total <= 0:
            return 0.0
        return max(0.0, min(1.0, int(faith.get(deity, 0) or 0) / float(total)))

    def _mood_song_material_for_kind(self, bard, kind: str) -> Optional[Dict[str, Any]]:
        rid = getattr(bard, "region_id", -1)
        region = getattr(self.world, "regions", {}).get(rid)
        rname = self.world.region_name(rid) if region is not None else "the Road"
        title_pools = {
            "pastoral": [f"Goldfire Beneath {rname}", f"The Orchard Roads of {rname}", "Riches Fall from the Trees", "Everything Is Green Again"],
            "protest": [f"The Taxman's Lantern", f"What Are Our Leaders Doing", f"No Crown Heard {rname}", "Bread for the Banners"],
            "lament": [f"No Sons Left in {rname}", "The Empty Summer", "All Roads Led Away", f"The Ashes of {rname}"],
            "existential": ["What Is This Life", "Why the Wheel Turns", "Where Was the Light", "The Road Asks Nothing"],
            "tavern": ["The Mug That Would Not Empty", "Three Coins and a Lie", "The Bard Forgot the Words", "A Very Bad Mule"],
            "seasonal": ["Rainmoot Windows", "The Frostturn Door", "Goldfire Dances", "Yearsend Candles"],
        }
        title = self._song_title_unique(title_pools.get(kind, ["A Song of the Road"]))
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": kind,
            "subject_actor_ids": [],
            "subject_event": f"regional mood in {rname}",
            "title": title,
            "historical_weight": self._mood_song_world_weight(bard, kind, region),
            "tone": kind,
            "source_ref": "regional-mood",
        }

    def _mood_song_world_weight(self, bard, kind: str, region=None) -> float:
        if region is None:
            region = getattr(self.world, "regions", {}).get(getattr(bard, "region_id", -1))
        order = float(getattr(region, "order", 50.0) if region is not None else 50.0)
        danger = float(getattr(region, "danger", 0.0) if region is not None else 0.0)
        control = float(getattr(region, "control", 0.0) if region is not None else 0.0)
        local_bards = 0
        local_party_members = 0
        rid = getattr(bard, "region_id", -1)
        try:
            for actor in self.world.actors_in_region(rid):
                if getattr(actor, "role", None) == Role.BARD and getattr(actor, "alive", False):
                    local_bards += 1
                if getattr(actor, "party_id", None) is not None:
                    local_party_members += 1
        except Exception:
            pass

        if kind == "pastoral":
            return 8.0 + max(0.0, order - 45.0) * 0.55 + max(0.0, 8.0 - danger) * 0.4
        if kind == "protest":
            return 8.0 + max(0.0, 42.0 - order) * 0.55 + max(0.0, -control) * 0.75
        if kind == "lament":
            deaths = int(getattr(self.world, "commoner_deaths_by_region", {}).get(rid, 0) or 0)
            return 8.0 + danger * 0.85 + min(50.0, deaths / 250.0) + max(0.0, 45.0 - order) * 0.25
        if kind == "tavern":
            return 8.0 + local_bards * 5.0 + local_party_members * 0.35 + max(0.0, order - 40.0) * 0.20
        if kind == "seasonal":
            return 8.0 + max(0.0, order - 50.0) * 0.28 + self.rng.random() * 8.0
        if kind == "existential":
            return 8.0 + abs(50.0 - order) * 0.16 + danger * 0.18 + self.rng.random() * 10.0
        return 8.0 + self.rng.random() * 8.0

    def _actor_song_material(self, bard, profile_cache: Optional[Dict[int, Dict[str, float]]] = None, song_index: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        subject_id, subject_score, visibility = self._choose_bard_subject_actor(bard, profile_cache=profile_cache, song_index=song_index)
        if subject_id is None:
            return None
        subject = self.resolve_actor(subject_id) if hasattr(self, "resolve_actor") else self.world.actors.get(subject_id)
        title = self._song_title_for_actor(subject_id, bard)
        if not self._song_title_is_available(title):
            return None
        if self._bard_has_song_for_subject(bard, subject_id, visibility, song_index=song_index):
            return None
        song_type = "personal" if visibility == "private" else "mythic"
        hist_mult = 0.22 if visibility == "public" else 0.08
        return {
            "song_type": song_type,
            "visibility": visibility,
            "subject_actor_ids": [subject_id],
            "title": title,
            "historical_weight": max(2.0, float(subject_score or 0.0) * hist_mult),
            "tone": self._tone_for_bard(bard),
            "fame_credit_actor_id": getattr(bard, "id", None) if visibility == "private" else None,
            "rediscovered": bool(getattr(subject, "alive", True) is False),
            "source_ref": "morgue" if bool(getattr(subject, "alive", True) is False) else "living-memory",
        }

    def _withdrawn_friend_song_title(self, actor) -> Optional[str]:
        pool = [
            "The Quiet Road Home",
            "Where the Lantern Went",
            "When the Captain Put Down His Sword",
            "The Door Beyond the Road",
            "No Banner at the Window",
            "The Hearth After Battle",
            "The Cup Left Warm",
            "The Road That Let Them Go",
        ]
        return self._song_title_unique(pool)


    def _withdrawn_friend_song_material(self, bard) -> Optional[Dict[str, Any]]:
        candidates = []
        ties = set(getattr(bard, "friend_ids", []) or [])
        for attr in ("best_friend_id", "spouse_id"):
            val = getattr(bard, attr, None)
            if val is not None:
                ties.add(val)
        party = self.world.parties.get(getattr(bard, "party_id", None)) if getattr(bard, "party_id", None) is not None else None
        if party is not None:
            ties.update(getattr(party, "member_ids", []) or [])
        for aid in list(ties):
            actor = self.world.actors.get(aid)
            if actor is None or not getattr(actor, "alive", False) or not getattr(actor, "withdrawn", False):
                continue
            score = 18.0 + float(getattr(actor, "reputation", 0) or 0) * 0.12
            score += float(getattr(actor, "military_service_ticks", 0) or 0) / float(max(1, _G.get("TICKS_PER_YEAR", 1440)))
            if getattr(actor, "veteran", False):
                score += 8.0
            if getattr(actor, "military_rank", None) in {"general", "captain", "lieutenant"}:
                score += 10.0
            candidates.append((score + self.rng.random() * 5.0, actor))
        if not candidates:
            return None
        score, actor = max(candidates, key=lambda item: item[0])
        if score < float(_G.get("BARD_WITHDRAWN_FRIEND_SONG_MIN_WEIGHT", 18.0)):
            return None
        title = self._withdrawn_friend_song_title(actor)
        if not self._song_title_is_available(title):
            return None
        kind = self.rng.choice(["pastoral", "existential", "lament", "tavern"])
        return {
            "song_type": kind,
            "subject_actor_ids": [getattr(actor, "id", None)],
            "subject_event": "a friend who stepped out of history",
            "title": title,
            "historical_weight": max(8.0, score * 0.45),
            "tone": "quiet remembrance",
            "source_ref": "withdrawn-friend",
            "anonymized_subject": True,
        }


    def _song_material_world_weight(self, bard, material: Dict[str, Any]) -> float:
        if not material:
            return 0.0
        kind = str(material.get("song_type") or "").lower()
        weight = max(1.0, float(material.get("historical_weight", 1.0) or 1.0))
        rid = getattr(bard, "region_id", -1)
        region = getattr(self.world, "regions", {}).get(rid)
        order = float(getattr(region, "order", 50.0) if region is not None else 50.0)
        danger = float(getattr(region, "danger", 0.0) if region is not None else 0.0)
        control = float(getattr(region, "control", 0.0) if region is not None else 0.0)

        subjects = set(material.get("subject_actor_ids") or [])
        personal_ids = {getattr(bard, "id", None)}
        for attr in ("spouse_id", "best_friend_id", "nemesis_id", "revenge_target_id", "revenge_for_actor_id", "mother_id", "father_id"):
            val = getattr(bard, attr, None)
            if val is not None:
                personal_ids.add(val)
        personal_ids.update(set(getattr(bard, "children_ids", []) or []))
        personal_overlap = len(subjects.intersection(personal_ids))

        if personal_overlap:
            weight += 35.0 * personal_overlap
        if kind == "personal":
            weight += 25.0
        if kind == "love":
            weight += 16.0 + personal_overlap * 35.0 + max(0.0, order - 45.0) * 0.18
        elif kind == "folly":
            weight += 12.0 + max(0.0, 55.0 - order) * 0.12 + max(0.0, -control) * 0.20
        elif kind in {"pastoral", "protest", "lament", "tavern", "seasonal", "existential"}:
            weight += self._mood_song_world_weight(bard, kind, region)
            if material.get("source_ref") == "withdrawn-friend":
                weight += 28.0
        elif kind == "hymn":
            deity = material.get("subject_deity", None)
            faith_share = self._local_faith_share_for_deity(rid, deity)
            if deity is not None and deity == getattr(bard, "deity", None):
                weight += 20.0
            weight += 45.0 * faith_share
            weight += float(getattr(bard, "deity_conviction", 50) or 50) * 0.10
        elif kind == "relic":
            relic = getattr(self.world, "relics", {}).get(material.get("subject_relic_id", None))
            weight += self._relic_story_score(relic, bard) * 0.30 if relic is not None else 8.0
        elif kind == "terror":
            monster = getattr(self.world, "monsters", {}).get(material.get("subject_monster_id", None))
            weight += self._monster_story_score(monster, bard) * 0.24 if monster is not None else danger * 0.5
        elif kind == "villain":
            for aid in subjects:
                actor = self.resolve_actor(aid) if hasattr(self, "resolve_actor") else self.world.actors.get(aid)
                weight += self._villain_story_score(actor) * 0.22 if actor is not None else 0.0
        elif kind == "mythic":
            weight += 18.0

        # A little actor preference, not a command. This is personality pressure,
        # not a category quota.
        alignment = getattr(bard, "alignment", None)
        if getattr(alignment, "law_axis", 0) > 0 and kind in {"hymn", "mythic", "seasonal"}:
            weight *= 1.08
        if getattr(alignment, "law_axis", 0) < 0 and kind in {"tavern", "folly", "protest"}:
            weight *= 1.10
        if getattr(alignment, "moral_axis", 0) > 0 and kind in {"love", "pastoral", "lament", "hymn"}:
            weight *= 1.06
        if getattr(alignment, "moral_axis", 0) < 0 and kind in {"villain", "folly", "protest"}:
            weight *= 1.08

        return max(0.0, weight + self.rng.random() * max(1.0, getattr(bard, "luck", 10) / 2.0))

    def _weighted_material_choice(self, weighted: List[Tuple[float, Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        weighted = [(max(0.0, float(weight)), material) for weight, material in weighted if material and float(weight or 0.0) > 0]
        if not weighted:
            return None
        exponent = max(0.10, float(_G.get("BARD_MENTAL_HAT_WEIGHT_EXPONENT", 0.70)))
        adjusted = [(max(0.01, weight) ** exponent, material) for weight, material in weighted]
        total = sum(weight for weight, _material in adjusted)
        if total <= 0:
            return None
        roll = self.rng.random() * total
        acc = 0.0
        for weight, material in adjusted:
            acc += weight
            if roll <= acc:
                return material
        return adjusted[-1][1]

    def _bard_song_material_pool(self, bard, profile_cache: Optional[Dict[int, Dict[str, float]]] = None, song_index: Optional[Dict[str, Any]] = None) -> List[Tuple[float, Dict[str, Any]]]:
        """Build the bard's mental hat from valid world impressions."""
        materials: List[Dict[str, Any]] = []

        # Personal/social material.
        for fn in (
            self._choose_love_song_material,
            self._choose_folly_song_material,
            self._hymn_song_material,
            self._relic_song_material,
            self._monster_song_material,
            self._villain_song_material,
            self._withdrawn_friend_song_material,
        ):
            try:
                material = fn(bard)
            except Exception:
                material = None
            if material is not None:
                materials.append(material)

        try:
            material = self._actor_song_material(bard, profile_cache=profile_cache, song_index=song_index)
        except Exception:
            material = None
        if material is not None:
            materials.append(material)

        # Regional mood material: add each valid kind separately so mood songs
        # do not hide behind another category roll.
        for kind in ("pastoral", "protest", "lament", "existential", "tavern", "seasonal"):
            try:
                material = self._mood_song_material_for_kind(bard, kind)
            except Exception:
                material = None
            if material is not None:
                materials.append(material)

        weighted: List[Tuple[float, Dict[str, Any]]] = []
        seen_titles: Set[str] = set()
        for material in materials:
            title = " ".join(str(material.get("title", "") or "").lower().split())
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            weight = self._song_material_world_weight(bard, material)
            if weight > 0:
                weighted.append((weight, material))
        return weighted

    def _bard_composition_category_weights(self) -> List[Tuple[float, str]]:
        """Return category-first composition weights.

        This deliberately avoids the old mental-hat sweep that built every
        possible song category before choosing one.  A bard now rolls the kind
        of song first, then only builds candidates for that single category.
        """
        configured = _G.get("BARD_COMPOSITION_CATEGORY_WEIGHTS", None)
        default = {
            "love": 1.0,
            "folly": 1.0,
            "hymn": 1.0,
            "relic": 1.0,
            "terror": 1.0,
            "villain": 1.0,
            "withdrawn_friend": 1.0,
            "actor": 1.0,
            "mood": 1.0,
        }
        weights = configured if isinstance(configured, dict) else default
        out: List[Tuple[float, str]] = []
        for key, value in weights.items():
            key = str(key or "").strip().lower()
            if key not in default:
                continue
            try:
                weight = float(value or 0.0)
            except Exception:
                weight = 0.0
            if weight > 0.0:
                out.append((weight, key))
        return out or [(1.0, key) for key in default]

    def _weighted_category_choice(self, weighted: List[Tuple[float, str]]) -> Optional[str]:
        weighted = [(max(0.0, float(weight)), key) for weight, key in weighted if key and float(weight or 0.0) > 0.0]
        if not weighted:
            return None
        total = sum(weight for weight, _key in weighted)
        if total <= 0.0:
            return None
        roll = self.rng.random() * total
        acc = 0.0
        for weight, key in weighted:
            acc += weight
            if roll <= acc:
                return key
        return weighted[-1][1]

    def _choose_mood_song_material(self, bard) -> Optional[Dict[str, Any]]:
        mood_weights = [
            (float(_G.get("BARD_PASTORAL_SONG_WEIGHT", 0.22)), "pastoral"),
            (float(_G.get("BARD_PROTEST_SONG_WEIGHT", 0.18)), "protest"),
            (float(_G.get("BARD_LAMENT_SONG_WEIGHT", 0.16)), "lament"),
            (float(_G.get("BARD_EXISTENTIAL_SONG_WEIGHT", 0.30)), "existential"),
            (float(_G.get("BARD_TAVERN_SONG_WEIGHT", 0.08)), "tavern"),
            (float(_G.get("BARD_SEASONAL_SONG_WEIGHT", 0.06)), "seasonal"),
        ]
        kind = self._weighted_category_choice(mood_weights) or "existential"
        try:
            return self._mood_song_material_for_kind(bard, kind)
        except Exception:
            return None

    def _choose_bard_song_material(self, bard, profile_cache: Optional[Dict[int, Dict[str, float]]] = None, song_index: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Choose one composition category first, then build only that material.

        Old behavior built love, folly, hymn, relic, monster, villain, withdrawn
        friend, actor/mythic, and all regional mood candidates for every
        composition attempt.  That made each composing bard perform a miniature
        world-summary pass.  Category-first selection keeps the d9 behavior: roll
        category, try that category, then let the caller fall back if invalid.
        """
        category = self._weighted_category_choice(self._bard_composition_category_weights())
        if category is None:
            return None

        try:
            if category == "love":
                return self._choose_love_song_material(bard)
            if category == "folly":
                return self._choose_folly_song_material(bard)
            if category == "hymn":
                return self._hymn_song_material(bard)
            if category == "relic":
                return self._relic_song_material(bard)
            if category == "terror":
                return self._monster_song_material(bard)
            if category == "villain":
                return self._villain_song_material(bard)
            if category == "withdrawn_friend":
                return self._withdrawn_friend_song_material(bard)
            if category == "actor":
                return self._actor_song_material(bard, profile_cache=profile_cache, song_index=song_index)
            if category == "mood":
                return self._choose_mood_song_material(bard)
        except Exception:
            return None
        return None

    def _compose_song(self, bard, profile_cache: Optional[Dict[int, Dict[str, float]]] = None, song_index: Optional[Dict[str, Any]] = None) -> Optional[Song]:
        """Compose one category-first song attempt.

        A bard rolls the kind of song before doing candidate work.  Invalid
        categories return None and the caller may fall back to performance.
        """
        material = self._choose_bard_song_material(bard, profile_cache=profile_cache, song_index=song_index)
        if material is None:
            return None
        return self._compose_cultural_song(bard, material, song_index=song_index)

    def _compose_cultural_song(self, bard, material: Dict[str, Any], song_index: Optional[Dict[str, Any]] = None) -> Optional[Song]:
        song_type = str(material.get("song_type") or "love").lower()
        visibility = str(material.get("visibility") or "public").lower()
        subjects = list(material.get("subject_actor_ids") or [])
        title = str(material.get("title") or "").strip()
        if not self._song_title_is_available(title):
            return None
        if subjects and all(self._bard_has_song_for_subject(bard, aid, song_type, song_index=song_index) for aid in subjects):
            return None
        relic_id = material.get("subject_relic_id", None)
        monster_id = material.get("subject_monster_id", None)
        if relic_id is not None or monster_id is not None:
            bard_id = getattr(bard, "id", None)
            if song_index is not None:
                if relic_id is not None and (bard_id, relic_id, song_type) in song_index.get("bard_relic_song_type", set()):
                    return None
                if monster_id is not None and (bard_id, monster_id, song_type) in song_index.get("bard_monster_song_type", set()):
                    return None
            else:
                for existing in getattr(self.world, "songs", {}).values():
                    if getattr(existing, "forgotten", False):
                        continue
                    if getattr(existing, "composer_id", None) != bard_id:
                        continue
                    if str(getattr(existing, "song_type", "") or "").lower() != song_type:
                        continue
                    if relic_id is not None and getattr(existing, "subject_relic_id", None) == relic_id:
                        return None
                    if monster_id is not None and getattr(existing, "subject_monster_id", None) == monster_id:
                        return None

        song_id = int(getattr(self.world, "next_song_id", 1))
        self.world.next_song_id = song_id + 1
        song = Song(
            id=song_id,
            title=title,
            composer_id=getattr(bard, "id", None),
            subject_actor_ids=subjects,
            subject_event=str(material.get("subject_event") or ""),
            subject_relic_id=material.get("subject_relic_id", None),
            subject_monster_id=material.get("subject_monster_id", None),
            subject_deity=material.get("subject_deity", None),
            anonymized_subject=bool(material.get("anonymized_subject", False)),
            origin_region_id=getattr(bard, "region_id", -1),
            known_region_ids={getattr(bard, "region_id", -1)},
            tone=str(material.get("tone") or ("satire" if song_type == "folly" else "love song")),
            popularity=2.5 + max(0, getattr(bard, "charisma", 10) - 10) * 0.45 + self.rng.random() * 3.5,
            historical_weight=float(material.get("historical_weight", 10.0) or 10.0),
            created_tick=self.world.tick,
            last_performed_tick=self.world.tick,
            performances=1,
            visibility=visibility,
            song_type=song_type,
            fame_credit_actor_id=material.get("fame_credit_actor_id", getattr(bard, "id", None)),
            rediscovered=bool(material.get("rediscovered", False)),
            source_ref=str(material.get("source_ref") or ""),
        )
        self.world.songs[song_id] = song
        cache = self._ensure_song_title_norm_cache()
        if isinstance(cache, set):
            cache.add(self._normalize_song_title(song.title))
        self._index_song_for_bardic_memory(song, song_index)
        self._register_song_composer_performer(song, bard)
        self._apply_cultural_song_effect(song, bard)
        labels = {
            "love": "a love-song", "folly": "a biting folly-song", "relic": "a relic-song",
            "terror": "a terror-song", "villain": "a villain-song", "lament": "a lament",
            "cautionary": "a cautionary song", "conquest": "a conquest ballad", "existential": "an existential song",
            "pastoral": "a pastoral song", "protest": "a protest song", "tavern": "a tavern song",
            "seasonal": "a seasonal song", "hymn": "a hymn", "labor": "a labor song",
            "mythic": "a mythic song", "personal": "a private song",
        }
        label = labels.get(song_type, "a song")
        src = " from old records" if song.rediscovered else ""
        importance = 1 if visibility == "private" else 2
        self.world.log(f"{bard.short_name()} composes {label}, {song.title},{src} in {self.world.region_name(bard.region_id)}.", importance=importance, category="lore")
        return song

    def _register_song_composer_performer(self, song: Song, bard) -> None:
        if bard is None or song is None:
            return
        if not isinstance(getattr(bard, "known_song_ids", None), list):
            bard.known_song_ids = []
        sid = int(getattr(song, "id", -1) or -1)
        if sid >= 0 and sid not in set(bard.known_song_ids):
            bard.known_song_ids.append(sid)
        if not hasattr(song, "performer_actor_ids") or getattr(song, "performer_actor_ids", None) is None:
            song.performer_actor_ids = set()
        try:
            song.performer_actor_ids.add(int(getattr(bard, "id")))
        except Exception:
            pass

    def _tone_for_bard(self, bard) -> str:
        alignment = getattr(bard, "alignment", None)
        if getattr(alignment, "law_axis", 0) > 0:
            return self.rng.choice(["hymn", "chronicle", "founding lay"])
        if getattr(alignment, "law_axis", 0) < 0:
            return self.rng.choice(["rebellious ballad", "wild lay", "lament"])
        if getattr(alignment, "moral_axis", 0) > 0:
            return self.rng.choice(["heroic ballad", "hymn", "lament"])
        return self.rng.choice(["popular ballad", "chronicle", "wandering song"])


    def _song_public_credit_reached(self, song: Song) -> bool:
        if str(getattr(song, "visibility", "public") or "public").lower() == "private":
            return self._private_song_has_public_reach(song)
        return (
            int(getattr(song, "performances", 0) or 0) >= int(_G.get("CULTURAL_SONG_PUBLIC_PERFORMANCES", 6))
            or len(getattr(song, "known_region_ids", set()) or set()) >= int(_G.get("CULTURAL_SONG_PUBLIC_REGIONS", 2))
            or float(getattr(song, "popularity", 0.0) or 0.0) >= float(_G.get("CULTURAL_SONG_PUBLIC_POPULARITY", 18.0))
            or float(getattr(song, "historical_weight", 0.0) or 0.0) >= float(_G.get("CULTURAL_SONG_PUBLIC_HISTORICAL_WEIGHT", 14.0))
        )

    def _award_song_bard_fame_if_ready(self, song: Song) -> None:
        if getattr(song, "fame_credit_awarded", False):
            return
        if not self._song_public_credit_reached(song):
            return
        credit_id = getattr(song, "fame_credit_actor_id", None) or getattr(song, "composer_id", None)
        if credit_id is None:
            return
        composer = self.resolve_actor(credit_id) if hasattr(self, "resolve_actor") else self.world.actors.get(credit_id)
        if composer is not None and getattr(composer, "alive", False):
            rep_key = "FOLLY_SONG_BARD_REP_AWARD" if str(getattr(song, "song_type", "")).lower() == "folly" else "CULTURAL_SONG_BARD_REP_AWARD"
            composer.reputation = int(getattr(composer, "reputation", 0) or 0) + int(_G.get(rep_key, 1))
        song.fame_credit_awarded = True

    def _apply_cultural_song_effect(self, song: Song, bard=None) -> None:
        song_type = str(getattr(song, "song_type", "mythic") or "mythic").lower()
        if song_type not in {"love", "folly"}:
            return
        every = max(1, int(_G.get("CULTURAL_SONG_EFFECT_EVERY_PERFORMANCES", 5)))
        performances = int(getattr(song, "performances", 0) or 0)
        applied = int(getattr(song, "cultural_effect_applied_count", 0) or 0)
        should_have = performances // every
        if performances <= 1:
            should_have = max(should_have, 1)
        if should_have <= applied:
            return
        delta_count = should_have - applied
        song.cultural_effect_applied_count = should_have

        rid = getattr(bard, "region_id", None) if bard is not None else getattr(song, "origin_region_id", None)
        if rid in getattr(self.world, "regions", {}):
            if song_type == "love":
                order_delta = int(_G.get("LOVE_SONG_REGION_ORDER_BONUS", 1)) * delta_count
                if order_delta and hasattr(self.world, "adjust_region_state"):
                    self.world.adjust_region_state(rid, order_delta=order_delta)
            elif song_type == "folly":
                order_delta = int(_G.get("FOLLY_SONG_REGION_ORDER_BONUS", 0)) * delta_count
                if order_delta and hasattr(self.world, "adjust_region_state"):
                    self.world.adjust_region_state(rid, order_delta=order_delta)

        # Ruling-couple love songs support legitimacy. Folly songs about rulers
        # erode legitimacy. Non-ruling cultural songs remain regional/cultural.
        subject_ids = list(getattr(song, "subject_actor_ids", []) or [])
        for polity in getattr(self.world, "polities", {}).values():
            ruler_id = getattr(polity, "ruler_id", None)
            ruler = getattr(self.world, "actors", {}).get(ruler_id)
            spouse_id = getattr(ruler, "spouse_id", None) if ruler is not None else None
            if song_type == "love" and ruler_id in subject_ids and spouse_id in subject_ids:
                bonus = int(_G.get("LOVE_SONG_RULING_COUPLE_LEGITIMACY_BONUS", 1)) * delta_count
                polity.legitimacy = max(0, min(100, int(getattr(polity, "legitimacy", 50) or 50) + bonus))
            elif song_type == "folly" and ruler_id in subject_ids:
                penalty = int(_G.get("FOLLY_SONG_RULER_LEGITIMACY_PENALTY", 1)) * delta_count
                polity.legitimacy = max(0, min(100, int(getattr(polity, "legitimacy", 50) or 50) - penalty))

    def _couple_song_score(self, a, b) -> float:
        if a is None or b is None:
            return 0.0
        score = 20.0
        score += max(0, int(getattr(a, "reputation", 0) or 0)) * 0.35
        score += max(0, int(getattr(b, "reputation", 0) or 0)) * 0.35
        score += max(0, int(getattr(a, "level", 1) or 1) - 1) * 2.0
        score += max(0, int(getattr(b, "level", 1) or 1) - 1) * 2.0
        score += (int(getattr(a, "monster_kills", 0) or 0) + int(getattr(b, "monster_kills", 0) or 0)) * 2.0
        score += (int(getattr(a, "dragon_kills", 0) or 0) + int(getattr(b, "dragon_kills", 0) or 0)) * 20.0
        if getattr(a, "alignment", None) != getattr(b, "alignment", None):
            score += 8.0
        if getattr(a, "is_evil", lambda: False)() != getattr(b, "is_evil", lambda: False)():
            score += 18.0
        if getattr(a, "polity_id", None) is not None or getattr(b, "polity_id", None) is not None:
            score += 10.0
        return score + self.rng.random() * 5.0

    def _love_song_title(self, a, b) -> str:
        an = a.short_name() if hasattr(a, "short_name") else str(getattr(a, "id", "Unknown"))
        bn = b.short_name() if hasattr(b, "short_name") else str(getattr(b, "id", "Unknown"))
        pool = [
            f"The Vow of {an} and {bn}",
            f"{an} and {bn} Beneath the Stars",
            f"The Road Between {an} and {bn}",
            f"Two Hearts at {self.world.region_name(getattr(a, 'region_id', -1)) if getattr(a, 'region_id', -1) in getattr(self.world, 'regions', {}) else 'the Crossroads'}",
            f"The Rose and the Blade",
            f"The Lantern and the Crown",
            f"Where {an} Waited",
        ]
        self.rng.shuffle(pool)
        existing = self._existing_song_titles_normalized()
        for title in pool:
            if " ".join(title.lower().split()) not in existing:
                return title
        return None

    def _folly_song_title(self, actor) -> str:
        name = actor.short_name() if hasattr(actor, "short_name") else str(getattr(actor, "id", "Unknown"))
        region = self.world.region_name(getattr(actor, "region_id", -1)) if getattr(actor, "region_id", -1) in getattr(self.world, "regions", {}) else "the Road"
        pool = [
            f"The Folly of {name}",
            f"The Last Mistake of {name}",
            f"When {name} Miscounted the Spears",
            f"The Bridge That Failed at {region}",
            f"{name} and the Bad Idea",
            f"The Crown That Slipped",
            f"The Lesson of {name}",
        ]
        self.rng.shuffle(pool)
        existing = self._existing_song_titles_normalized()
        for title in pool:
            if " ".join(title.lower().split()) not in existing:
                return title
        return None

    def _morgue_story_candidates(self, kind: str = "mythic", limit: Optional[int] = None) -> List[Any]:
        if not bool(_G.get("LORE_MORGUE_REDISCOVERY_ENABLED", True)):
            return []
        limit = int(limit or _G.get("LORE_MORGUE_MAX_CANDIDATES", 24))
        min_dead_years = int(_G.get("LORE_MORGUE_MIN_DEAD_YEARS", 10))
        current_year = self.world.current_calendar()[0] if hasattr(self.world, "current_calendar") else 0
        tombs = list((getattr(self.world, "dead_actor_index", {}) or {}).values())
        morgue = getattr(self, "morgue", None) or getattr(self, "mortuary", None)
        if morgue is not None and hasattr(morgue, "story_candidate_index"):
            try:
                min_rep = int(_G.get("BARD_PUBLIC_SUBJECT_MIN_REP", 18)) if kind == "mythic" else 0
                morgue_rows = morgue.story_candidate_index(limit=max(limit * 3, 100), min_reputation=min_rep)
                tomb_by_id = {int(t.get("id")): t for t in tombs if isinstance(t, dict) and t.get("id") is not None}
                for row in morgue_rows:
                    rid = int(row.get("id"))
                    tomb_by_id.setdefault(rid, row)
                tombs = list(tomb_by_id.values())
            except Exception:
                pass
        actors = []
        for tomb in tombs:
            aid = tomb.get("id") if isinstance(tomb, dict) else None
            actor = self.resolve_actor(aid) if aid is not None and hasattr(self, "resolve_actor") else None
            if actor is None or getattr(actor, "role", None) == Role.COMMONER:
                continue
            death_year = None
            try:
                ts = str(getattr(actor, "death_timestamp", "") or "")
                if ts.startswith("Year "):
                    death_year = int(ts.split(",", 1)[0].replace("Year", "").strip())
            except Exception:
                death_year = None
            if death_year is not None and current_year - death_year < min_dead_years:
                continue
            score = 0.0
            if kind == "mythic":
                eligible, _ = self._actor_public_song_eligibility(actor)
                if not eligible:
                    continue
                score += float(getattr(actor, "reputation", 0) or 0)
                score += float(getattr(actor, "mythic_legacy_score", 0.0) or 0.0) * 0.25
                score += int(getattr(actor, "dragon_kills", 0) or 0) * 40
                score += int(getattr(actor, "horror_kills", 0) or 0) * 50
            elif kind == "love":
                if getattr(actor, "spouse_id", None) is None:
                    continue
                score += float(getattr(actor, "reputation", 0) or 0) + float(getattr(actor, "charisma", 10) or 10)
            else:
                cause = str(getattr(actor, "death_cause", "") or "").lower()
                if not any(word in cause for word in ("failed", "flee", "rout", "assassination", "coup", "slain", "battle")) and int(getattr(actor, "reputation", 0) or 0) < int(_G.get("FOLLY_SONG_MIN_REP", 20)):
                    continue
                score += float(getattr(actor, "reputation", 0) or 0) + float(getattr(actor, "regions_oppressed", 0) or 0) * 8
            actors.append((score + self.rng.random(), actor))
        actors.sort(key=lambda item: item[0], reverse=True)
        return [actor for _score, actor in actors[:limit]]

    def _historian_story_events(self, kind: str, limit: Optional[int] = None):
        if not bool(_G.get("LORE_TOME_REDISCOVERY_ENABLED", True)):
            return []
        historian = getattr(self, "historian", None) or getattr(self.world, "historian", None)
        if historian is None:
            return []
        limit = int(limit or _G.get("LORE_TOME_EVENT_SAMPLE_LIMIT", 40))
        if kind == "love":
            cats = {"marriage", "legacy_birth", "succession", "diplomacy"}
        elif kind == "folly":
            cats = {"party_coup", "polity_challenge", "succession", "corruption", "notable_death"}
        else:
            cats = {"legendary_monster_kill", "champion_death", "notable_death", "necromancer_crisis", "polity"}
        try:
            if hasattr(historian, "story_events"):
                return historian.story_events(kind, limit=limit)
            return historian.events_by_category(cats, limit=limit)
        except Exception:
            return []

    def _choose_love_song_material(self, bard) -> Optional[Dict[str, Any]]:
        candidates = []
        # Bard's own spouse is always valid cultural material.
        spouse = self.world.actors.get(getattr(bard, "spouse_id", None)) if getattr(bard, "spouse_id", None) is not None else None
        if spouse is not None:
            candidates.append((80.0 + self.rng.random() * 10.0, bard, spouse, False))

        seen = set()
        # Only check adventurers (non-commoners) since commoners never qualify for love songs.
        for actor in self.world.living_actors():
            if getattr(actor, "role", None) == Role.COMMONER:
                continue
            sid = getattr(actor, "spouse_id", None)
            if sid is None or (getattr(actor, "id", None), sid) in seen or (sid, getattr(actor, "id", None)) in seen:
                continue
            spouse = self.world.actors.get(sid)
            if spouse is None:
                continue
            seen.add((getattr(actor, "id", None), sid))
            score = self._couple_song_score(actor, spouse)
            if score >= float(_G.get("LOVE_SONG_MIN_COUPLE_SCORE", 55.0)):
                candidates.append((score, actor, spouse, False))

        for actor in self._morgue_story_candidates("love", limit=12):
            spouse = self.resolve_actor(getattr(actor, "spouse_id", None)) if hasattr(self, "resolve_actor") else None
            if spouse is not None:
                score = self._couple_song_score(actor, spouse) + 8.0
                candidates.append((score, actor, spouse, True))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        _score, a, b, rediscovered = candidates[0]
        title = self._love_song_title(a, b)
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": "love",
            "subject_actor_ids": [getattr(a, "id", None), getattr(b, "id", None)],
            "title": title,
            "historical_weight": max(8.0, _score * 0.18),
            "tone": "love song",
            "rediscovered": rediscovered,
            "source_ref": "morgue" if rediscovered else "",
        }

    def _choose_folly_song_material(self, bard) -> Optional[Dict[str, Any]]:
        candidates = []
        min_rep = int(_G.get("FOLLY_SONG_MIN_REP", 20))
        for actor in self.world.living_actors():
            if getattr(actor, "role", None) == Role.COMMONER:
                continue
            bad_state = int(getattr(actor, "regions_oppressed", 0) or 0) > 0 or str(getattr(actor, "nemesis_reason", "") or "").lower().find("failed") >= 0
            if int(getattr(actor, "reputation", 0) or 0) >= min_rep and bad_state:
                candidates.append((float(getattr(actor, "reputation", 0) or 0) + self.rng.random() * 10.0, actor, False))
        for actor in self._morgue_story_candidates("folly", limit=18):
            score = float(getattr(actor, "reputation", 0) or 0) + float(getattr(actor, "regions_oppressed", 0) or 0) * 8 + self.rng.random() * 8.0
            candidates.append((score, actor, True))
        if not candidates:
            events = self._historian_story_events("folly", limit=20)
            if events:
                event = self.rng.choice(events)
                return {
                    "song_type": "folly",
                    "subject_actor_ids": [],
                    "subject_event": getattr(event, "text", ""),
                    "title": self._folly_title_for_event(event),
                    "historical_weight": 10.0 + int(getattr(event, "importance", 1) or 1) * 2.0,
                    "tone": "satire",
                    "rediscovered": True,
                    "source_ref": "tome",
                }
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        score, actor, rediscovered = candidates[0]
        title = self._folly_song_title(actor)
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": "folly",
            "subject_actor_ids": [getattr(actor, "id", None)],
            "title": title,
            "historical_weight": max(8.0, score * 0.16),
            "tone": "satire",
            "rediscovered": rediscovered,
            "source_ref": "morgue" if rediscovered else "",
        }

    def _folly_title_for_event(self, event) -> str:
        text = str(getattr(event, "text", "") or "")
        seed = "the Crown" if "kingdom" in text.lower() or "ruler" in text.lower() else "the Road"
        pool = [f"The Folly of {seed}", "The Song of the Bad Decision", "The Crown That Slipped", "A Lesson Paid in Blood"]
        self.rng.shuffle(pool)
        return pool[0]


    def _song_title_unique(self, pool: List[str], fallback: str = "") -> Optional[str]:
        self.rng.shuffle(pool)
        existing = self._existing_song_titles_normalized() if hasattr(self, "_existing_song_titles_normalized") else set()
        for title in pool:
            if " ".join(str(title).lower().split()) not in existing:
                return title
        if fallback and not bool(_G.get("BARD_DUPLICATE_TITLE_BLOCK", True)):
            return fallback
        return None

    def _relic_is_publicly_revealed(self, relic) -> bool:
        if relic is None or getattr(relic, "destroyed", False):
            return False
        if bool(getattr(relic, "is_revealed", False)):
            return True
        if int(getattr(relic, "revealed_tick", -1) or -1) >= 0:
            return True
        if int(getattr(relic, "released_tick", -1) or -1) >= 0:
            return True
        if getattr(relic, "holder_id", None) is not None:
            return True
        return False

    def _relic_story_score(self, relic, bard=None) -> float:
        if not self._relic_is_publicly_revealed(relic):
            return 0.0
        score = float(getattr(relic, "power_bonus", 0) or 0) * 5.0 + float(getattr(relic, "reputation_bonus", 0) or 0) * 2.0
        score += len(getattr(relic, "discovered_by", set()) or set()) * float(_G.get("RELIC_SONG_DISCOVERY_WEIGHT", 2.0))
        score += len(getattr(relic, "possession_history", []) or []) * float(_G.get("RELIC_SONG_POSSESSION_EVENT_WEIGHT", 4.0))
        score += int(getattr(relic, "failed_claims", 0) or 0) * float(_G.get("RELIC_SONG_FAILED_ATTEMPT_WEIGHT", 7.0))
        score += int(getattr(relic, "quest_deaths", 0) or 0) * float(_G.get("RELIC_SONG_FAILED_ATTEMPT_WEIGHT", 7.0))
        released = int(getattr(relic, "released_tick", -1) or -1)
        if released >= 0:
            score += max(0.0, (int(getattr(self.world, "tick", 0)) - released) / float(_G.get("TICKS_PER_YEAR", 1440))) * float(_G.get("RELIC_SONG_AGE_ACTIVE_WEIGHT", 0.35))
        if bard is not None and getattr(relic, "region_id", None) == getattr(bard, "region_id", None):
            score += 20.0
        return score + self.rng.random() * 8.0

    def _relic_song_material(self, bard) -> Optional[Dict[str, Any]]:
        candidates = []
        for relic in getattr(self.world, "relics", {}).values():
            score = self._relic_story_score(relic, bard)
            if score >= float(_G.get("RELIC_SONG_MIN_SCORE", 55.0)):
                candidates.append((score, relic))
        if not candidates:
            return None
        score, relic = max(candidates, key=lambda item: item[0])
        title = self._song_title_for_relic(relic) if hasattr(self, "_song_title_for_relic") else f"The Rumor of {getattr(relic, 'name', 'the Relic')}"
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": "relic",
            "subject_relic_id": getattr(relic, "id", None),
            "subject_event": f"Rumors and failed quests gather around {getattr(relic, 'name', 'a relic')}",
            "title": title,
            "historical_weight": max(10.0, score * 0.22),
            "tone": "relic warning",
            "source_ref": "relic",
        }

    def _monster_story_score(self, monster, bard=None) -> float:
        if monster is None or not getattr(monster, "alive", True):
            return 0.0
        if getattr(monster, "kind", None) == MonsterKind.GOBLIN:
            return 0.0
        age_years = max(0.0, float(getattr(monster, "age_ticks", 0) or 0) / float(_G.get("TICKS_PER_YEAR", 1440) or 1080))
        kills = int(getattr(monster, "monster_kills_adventurers", 0) or 0)
        commoners = int(getattr(monster, "monster_kills_commoners", 0) or 0)
        regions = len(getattr(monster, "terror_region_ids", set()) or set())
        erad = int(getattr(monster, "eradication_survivals", 0) or 0)
        score = 0.0
        score += kills * float(_G.get("MONSTER_SONG_KILL_WEIGHT", 2.0))
        score += commoners * float(_G.get("MONSTER_SONG_COMMONER_KILL_WEIGHT", 0.03))
        score += age_years * float(_G.get("MONSTER_SONG_AGE_WEIGHT", 1.0))
        score += regions * float(_G.get("MONSTER_SONG_REGION_WEIGHT", 12.0))
        score += erad * float(_G.get("MONSTER_SONG_ERADICATION_WEIGHT", 35.0))
        score += int(getattr(monster, "reputation", 0) or 0) * 1.5
        if getattr(monster, "kind", None) == MonsterKind.DRAGON:
            score += 40.0
        if getattr(monster, "kind", None) == MonsterKind.ANCIENT_HORROR:
            score += 80.0
        if bard is not None and getattr(monster, "region_id", None) == getattr(bard, "region_id", None):
            score += 20.0
        min_kills = int(_G.get("MONSTER_SONG_MIN_KILLS", 25))
        min_age = float(_G.get("MONSTER_SONG_MIN_AGE_YEARS", 12))
        if kills + commoners < min_kills and age_years < min_age and erad <= 0:
            return 0.0
        return score + self.rng.random() * 10.0

    def _monster_song_title(self, monster) -> str:
        name = str(getattr(monster, "name", "the Beast") or "the Beast")
        region = self.world.region_name(getattr(monster, "region_id", -1)) if getattr(monster, "region_id", -1) in getattr(self.world, "regions", {}) else "the Wilds"
        pool = [
            f"Do Not Wake {name}", f"The Terror of {region}", f"The Teeth Beneath {region}",
            f"When {name} Came", f"The Road Away from {name}", f"The Children Hide from {name}",
            f"The Ballad of the Unslain", f"No Spear Could End {name}",
        ]
        return self._song_title_unique(pool)

    def _monster_song_material(self, bard) -> Optional[Dict[str, Any]]:
        candidates = []
        for monster in getattr(self.world, "monsters", {}).values():
            score = self._monster_story_score(monster, bard)
            if score >= float(_G.get("MONSTER_SONG_MIN_SCORE", 90.0)):
                candidates.append((score, monster))
        if not candidates:
            return None
        score, monster = max(candidates, key=lambda item: item[0])
        title = self._monster_song_title(monster)
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": "terror",
            "subject_monster_id": getattr(monster, "id", None),
            "subject_event": f"{getattr(monster, 'name', 'A monster')} persists in living fear",
            "title": title,
            "historical_weight": max(12.0, score * 0.20),
            "tone": "terror",
            "source_ref": "monster",
        }

    def _villain_story_score(self, actor) -> float:
        if actor is None or getattr(actor, "role", None) == Role.COMMONER:
            return 0.0
        if not getattr(actor, "is_evil", lambda: False)() and int(getattr(actor, "regions_oppressed", 0) or 0) <= 0:
            return 0.0
        rep = int(getattr(actor, "reputation", 0) or 0)
        if rep < int(_G.get("VILLAIN_SONG_MIN_REP", 18)) and int(getattr(actor, "regions_oppressed", 0) or 0) <= 0:
            return 0.0
        score = rep * 1.1
        score += int(getattr(actor, "kills", 0) or 0) * float(_G.get("VILLAIN_SONG_KILL_WEIGHT", 1.8))
        score += int(getattr(actor, "regions_oppressed", 0) or 0) * float(_G.get("VILLAIN_SONG_OPPRESSION_WEIGHT", 24.0))
        try:
            score += self._calculate_age(actor) * float(_G.get("VILLAIN_SONG_AGE_WEIGHT", 0.6))
        except Exception:
            pass
        if getattr(actor, "relic_id", None) is not None:
            score += 20.0
        return score + self.rng.random() * 8.0

    def _villain_song_title(self, actor) -> str:
        name = actor.short_name() if hasattr(actor, "short_name") else str(getattr(actor, "id", "the Tyrant"))
        region = self.world.region_name(getattr(actor, "region_id", -1)) if getattr(actor, "region_id", -1) in getattr(self.world, "regions", {}) else "the Road"
        pool = [f"The Warning of {name}", f"The Shadow of {name}", f"Do Not Kneel to {name}", f"The Black Road to {region}", f"The Widows Name {name}", f"The Tyrant's Lantern", f"The Ballad Against {name}"]
        return self._song_title_unique(pool)

    def _villain_song_material(self, bard) -> Optional[Dict[str, Any]]:
        candidates = []
        source = [a for a in self.world.living_actors() if getattr(a, "role", None) != Role.COMMONER]
        source.extend(self._morgue_story_candidates("folly", limit=20))
        seen = set()
        for actor in source:
            aid = getattr(actor, "id", None)
            if aid in seen:
                continue
            seen.add(aid)
            score = self._villain_story_score(actor)
            if score >= float(_G.get("VILLAIN_SONG_MIN_SCORE", 80.0)):
                candidates.append((score, actor))
        if not candidates:
            return None
        score, actor = max(candidates, key=lambda item: item[0])
        title = self._villain_song_title(actor)
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": "villain",
            "subject_actor_ids": [getattr(actor, "id", None)],
            "title": title,
            "historical_weight": max(10.0, score * 0.18),
            "tone": "warning",
            "rediscovered": not bool(getattr(actor, "alive", False)),
            "source_ref": "morgue" if not bool(getattr(actor, "alive", False)) else "living-memory",
        }

    def _deity_label_for_song(self, deity) -> str:
        return str(getattr(deity, "value", getattr(deity, "name", deity)) or "Unknown God")

    def _hymn_song_title(self, deity) -> Optional[str]:
        name = self._deity_label_for_song(deity)
        abbrev = self._deity_abbrev_for_lore(deity) if deity is not None else "GOD"
        pool = [
            f"Hymn to {name}",
            f"The Praise of {name}",
            f"The {abbrev} Canticle",
            f"Light the Road for {name}",
            f"The Vow Before {name}",
            f"The Bells of {name}",
            f"When {name} Heard Us",
            f"The Road Under {name}",
        ]
        return self._song_title_unique(pool)

    def _hymn_song_material(self, bard) -> Optional[Dict[str, Any]]:
        deity = getattr(bard, "deity", None)
        if deity is None:
            return None
        title = self._hymn_song_title(deity)
        if not self._song_title_is_available(title):
            return None
        return {
            "song_type": "hymn",
            "subject_deity": deity,
            "subject_event": self._deity_label_for_song(deity),
            "title": title,
            "historical_weight": float(_G.get("HYMN_SONG_BASE_HISTORICAL_WEIGHT", 12.0)) + max(0, getattr(bard, "charisma", 10) - 10) * 0.4,
            "tone": "hymn",
            "source_ref": "religion",
        }

    def _actor_is_personal_song_subject(self, bard, actor) -> bool:
        """Private songs are allowed for actual personal ties only."""
        if bard is None or actor is None:
            return False
        aid = getattr(actor, "id", None)
        if aid is None:
            return False
        if aid in set(getattr(bard, "friend_ids", []) or []):
            return True
        if aid in set(getattr(bard, "children_ids", []) or []):
            return True
        for attr in ("mother_id", "father_id", "spouse_id", "best_friend_id", "nemesis_id", "revenge_target_id", "revenge_for_actor_id"):
            if getattr(bard, attr, None) == aid:
                return True
        party = self.world.parties.get(getattr(bard, "party_id", None)) if getattr(bard, "party_id", None) is not None else None
        return bool(party is not None and aid in (getattr(party, "member_ids", []) or []))

    def _actor_public_song_eligibility(self, actor, profile: Optional[Dict[str, float]] = None) -> Tuple[bool, List[str]]:
        """Hard gate for public/myth-bearing songs.

        Locality, death, personal connection, and randomness are not enough.
        A public song subject must already have a real claim on public memory.
        """
        if actor is None or getattr(actor, "role", None) == Role.COMMONER:
            return False, []

        # Reputation is a hard public-memory floor, not merely one possible
        # qualifier. Private songs may exist for personal ties, but they are
        # credited to the bard and must never turn a low-reputation subject
        # into public myth/proto-cult material.
        min_rep = int(_G.get("BARD_PUBLIC_SUBJECT_MIN_REP", 18))
        if int(getattr(actor, "reputation", 0) or 0) < min_rep:
            return False, []

        profile = profile if profile is not None else (self._mythic_legacy_profile_for_actor(actor) if hasattr(self, "_mythic_legacy_profile_for_actor") else {})
        reasons: List[str] = ["reputation"]
        def add(cond: bool, label: str) -> None:
            if cond:
                reasons.append(label)

        add(int(getattr(actor, "level", 1) or 1) >= int(_G.get("BARD_PUBLIC_SUBJECT_MIN_LEVEL", 6)), "level")
        add(int(getattr(actor, "monster_kills", 0) or 0) >= int(_G.get("BARD_PUBLIC_SUBJECT_MIN_MONSTER_KILLS", 3)), "monster-kills")
        add(int(getattr(actor, "giant_kills", 0) or 0) > 0, "giant-kill")
        add(int(getattr(actor, "dragon_kills", 0) or 0) > 0, "dragon-kill")
        add(int(getattr(actor, "horror_kills", 0) or 0) > 0, "horror-kill")
        add(int(getattr(actor, "regions_defended", 0) or 0) > 0, "defender")
        add(int(getattr(actor, "regions_oppressed", 0) or 0) > 0, "oppressor")
        add(int(getattr(actor, "black_host_waves_survived", 0) or 0) > 0, "black-host")
        add(int(getattr(actor, "black_host_victories", 0) or 0) > 0, "black-host-victory")
        add(getattr(actor, "champion_of", None) is not None, "champion")
        add(getattr(actor, "relic_id", None) is not None, "relic")
        add(getattr(actor, "first_in_class_year", None) is not None, "first-in-class")
        add(bool(getattr(actor, "office_title", None) or getattr(actor, "military_rank", None)), "office")
        aid = getattr(actor, "id", None)
        if aid is not None:
            # Use tick-local index sets when available (built by _bardic_memory_turn).
            _pf = getattr(self.world, "_lore_party_founder_ids", None)
            _polh_f = getattr(self.world, "_lore_polity_founder_ids", None)
            _polh_r = getattr(self.world, "_lore_polity_ruler_ids", None)
            _lpl = getattr(self.world, "_lore_large_party_leader_ids", None)
            if _pf is not None:
                if aid in _pf:
                    reasons.append("party-founder")
            else:
                for ph in getattr(self.world, "party_history", {}).values():
                    if getattr(ph, "founder_id", None) == aid:
                        reasons.append("party-founder")
                        break
            if _polh_f is not None and _polh_r is not None:
                if aid in _polh_f or aid in _polh_r:
                    reasons.append("polity")
            else:
                for polh in getattr(self.world, "polity_history", {}).values():
                    if getattr(polh, "founder_id", None) == aid or getattr(polh, "current_ruler_id", None) == aid:
                        reasons.append("polity")
                        break
            if _lpl is not None:
                if aid in _lpl:
                    reasons.append("party-leader")
            else:
                for pty in getattr(self.world, "parties", {}).values():
                    if getattr(pty, "leader_id", None) == aid and len(getattr(pty, "member_ids", []) or []) >= int(_G.get("BARD_PUBLIC_SUBJECT_MIN_PARTY_SIZE", 8)):
                        reasons.append("party-leader")
                        break
        mythic_score = self._mythic_legacy_score(profile) if hasattr(self, "_mythic_legacy_score") else 0.0
        add(mythic_score >= float(_G.get("BARD_PUBLIC_SUBJECT_MIN_MYTHIC_SCORE", 45.0)), "mythic-score")
        return bool(reasons), reasons


    def _bard_has_song_for_subject(self, bard, subject_actor_id: int, visibility: str, song_index: Optional[Dict[str, Any]] = None) -> bool:
        """Return True if this bard already wrote this visibility of song for this actor.

        A bard may write at most one private and one public song about the
        same actor. Performances/variants should spread existing work instead
        of creating infinite near-duplicate titles.
        """
        bard_id = getattr(bard, "id", None)
        if bard_id is None or subject_actor_id is None:
            return False
        wanted_visibility = str(visibility or "public").lower()
        if song_index is not None:
            if wanted_visibility in {"love", "folly", "mythic", "personal", "relic"}:
                return (bard_id, subject_actor_id, wanted_visibility) in song_index.get("bard_subject_song_type", set())
            return (bard_id, subject_actor_id, wanted_visibility) in song_index.get("bard_subject_visibility", set())
        for song in getattr(self.world, "songs", {}).values():
            if getattr(song, "forgotten", False):
                continue
            if getattr(song, "composer_id", None) != bard_id:
                continue
            song_visibility = str(getattr(song, "visibility", "public") or "public").lower()
            song_type = str(getattr(song, "song_type", song_visibility) or song_visibility).lower()
            if wanted_visibility in {"love", "folly", "mythic", "personal", "relic"}:
                if song_type != wanted_visibility:
                    continue
            elif song_visibility != wanted_visibility:
                continue
            try:
                subjects = {int(aid) for aid in (getattr(song, "subject_actor_ids", []) or [])}
            except Exception:
                subjects = set(getattr(song, "subject_actor_ids", []) or [])
            try:
                if int(subject_actor_id) in subjects:
                    return True
            except Exception:
                if subject_actor_id in subjects:
                    return True
        return False

    def _recent_public_song_count_for_subject(self, subject_actor_id: int, song_index: Optional[Dict[str, Any]] = None) -> int:
        """Count recent public songs about a subject for composition fatigue only.

        This is not a memory/history penalty. It only nudges bards away from
        dogpiling the same subject while that subject already has many fresh
        songs in circulation.
        """
        if subject_actor_id is None:
            return 0
        if song_index is not None:
            return int(song_index.get("recent_public_subject_counts", {}).get(subject_actor_id, 0) or 0)
        window_years = float(_G.get("BARD_RECENT_SONG_WINDOW_YEARS", 20))
        window_ticks = int(window_years * _G.get("TICKS_PER_YEAR", 1440))
        now = int(getattr(self.world, "tick", 0) or 0)
        count = 0
        for song in getattr(self.world, "songs", {}).values():
            if getattr(song, "forgotten", False):
                continue
            if str(getattr(song, "visibility", "public") or "public").lower() != "public":
                continue
            if subject_actor_id not in (getattr(song, "subject_actor_ids", []) or []):
                continue
            created = int(getattr(song, "created_tick", 0) or 0)
            if window_ticks <= 0 or now - created <= window_ticks:
                count += 1
        return count

    def _subject_song_fatigue_multiplier(self, subject_actor_id: int, song_index: Optional[Dict[str, Any]] = None) -> float:
        """Return a temporary new-composition multiplier based on recent songs.

        Does not affect legend pressure, mythic score, proto-cult pressure, or
        future rediscovery after the recent-song window expires.
        """
        count = self._recent_public_song_count_for_subject(subject_actor_id, song_index=song_index)
        free = int(_G.get("BARD_SUBJECT_FATIGUE_FREE_SONGS", 3))
        if count <= free:
            return 1.0
        step = float(_G.get("BARD_SUBJECT_FATIGUE_STEP", 0.12))
        floor = float(_G.get("BARD_SUBJECT_FATIGUE_MIN_MULT", 0.35))
        return max(floor, 1.0 - ((count - free) * step))

    def _mythic_legacy_profile_cached(self, actor, profile_cache: Optional[Dict[int, Dict[str, float]]] = None) -> Dict[str, float]:
        if actor is None:
            return {}
        if not hasattr(self, "_mythic_legacy_profile_for_actor"):
            return {}
        if profile_cache is None:
            return self._mythic_legacy_profile_for_actor(actor)
        try:
            aid = int(getattr(actor, "id"))
        except Exception:
            return self._mythic_legacy_profile_for_actor(actor)
        if aid not in profile_cache:
            profile_cache[aid] = self._mythic_legacy_profile_for_actor(actor)
        return profile_cache[aid]

    def _candidate_actor_score_for_song(self, bard, actor, *, public: bool, profile_cache: Optional[Dict[int, Dict[str, float]]] = None, song_index: Optional[Dict[str, Any]] = None) -> float:
        if actor is None:
            return 0.0
        if getattr(actor, "role", None) == Role.COMMONER:
            return 0.0
        score = 0.0
        personal = self._actor_is_personal_song_subject(bard, actor)
        if public:
            profile = self._mythic_legacy_profile_cached(actor, profile_cache)
            eligible, _reasons = self._actor_public_song_eligibility(actor, profile)
            if not eligible:
                return 0.0
            score += self._mythic_legacy_score(profile) if hasattr(self, "_mythic_legacy_score") else 0.0
            score += max(0, int(getattr(actor, "reputation", 0))) * 0.65
            if getattr(actor, "champion_of", None) is not None:
                score += 30.0
            if getattr(actor, "relic_id", None) is not None:
                score += 25.0
            if getattr(actor, "first_in_class_year", None) is not None:
                score += 12.0
            if getattr(actor, "region_id", None) == getattr(bard, "region_id", None):
                score += 4.0
            if personal:
                score += 10.0
            score += self.rng.random() * 5.0
            score *= self._subject_song_fatigue_multiplier(getattr(actor, "id", None), song_index=song_index)
        else:
            if not personal:
                return 0.0
            score += 18.0
            score += max(0, int(getattr(actor, "reputation", 0))) * 0.20
            score += min(15.0, max(0, int(getattr(actor, "kills", 0))) * 0.25)
            if not getattr(actor, "alive", True):
                score += 4.0
            if getattr(actor, "region_id", None) == getattr(bard, "region_id", None):
                score += 4.0
            score += self.rng.random() * 4.0
        # Good/neutral bards can remember villains, but usually as warnings or tragedies.
        if getattr(actor, "is_evil", lambda: False)():
            score *= 0.75
            if getattr(bard, "alignment", None) and getattr(bard.alignment, "law_axis", 0) < 0:
                score += 8.0
        return score

    def _choose_bard_subject_actor(self, bard, profile_cache: Optional[Dict[int, Dict[str, float]]] = None, song_index: Optional[Dict[str, Any]] = None) -> Tuple[Optional[int], float, str]:
        public_candidates = []
        private_candidates = []

        for actor in self.world.actors_in_region(getattr(bard, "region_id", -1)):
            if actor.id == bard.id or not actor.is_adventurer():
                continue
            public_candidates.append(actor)
            if self._actor_is_personal_song_subject(bard, actor):
                private_candidates.append(actor)

        # Add important living actors globally, capped.
        living_adv = [a for a in self.world.living_actors() if a.is_adventurer()]
        living_adv.sort(key=lambda a: (getattr(a, "reputation", 0), getattr(a, "dragon_kills", 0), getattr(a, "horror_kills", 0), getattr(a, "level", 1)), reverse=True)
        public_candidates.extend(living_adv[:40])

        # Add remembered dead actors from the morgue. This is the mythic
        # rediscovery lane: a worthy high-rep dead hero who was undersung in life
        # can still become public song material later, but never bypasses public
        # eligibility or mythic gates.
        for actor in self._morgue_story_candidates("mythic", limit=int(_G.get("LORE_MORGUE_MYTHIC_CANDIDATES", 60))):
            public_candidates.append(actor)
            if self._actor_is_personal_song_subject(bard, actor):
                private_candidates.append(actor)

        def best_from(candidates, *, public: bool):
            best_id = None
            best_score = 0.0
            seen = set()
            visibility = "public" if public else "private"
            for actor in candidates:
                if actor.id in seen:
                    continue
                seen.add(actor.id)
                if self._bard_has_song_for_subject(bard, actor.id, visibility, song_index=song_index):
                    continue
                score = self._candidate_actor_score_for_song(bard, actor, public=public, profile_cache=profile_cache, song_index=song_index)
                if score > best_score:
                    best_score = score
                    best_id = actor.id
            return best_id, best_score

        public_id, public_score = best_from(public_candidates, public=True)
        public_floor = float(_G.get("BARD_PUBLIC_SUBJECT_MIN_SCORE", _G.get("BARD_MIN_SUBJECT_SCORE", 32.0)))
        if public_id is not None and public_score >= public_floor:
            return public_id, public_score, "public"

        private_id, private_score = best_from(private_candidates, public=False)
        private_floor = float(_G.get("BARD_PRIVATE_SUBJECT_MIN_SCORE", 16.0))
        if private_id is not None and private_score >= private_floor:
            return private_id, private_score, "private"

        return None, 0.0, "public"

    def _choose_bard_subject_relic(self, bard):
        candidates = []
        for relic in getattr(self.world, "relics", {}).values():
            if getattr(relic, "destroyed", False):
                continue
            score = self._relic_story_score(relic, bard) if hasattr(self, "_relic_story_score") else 0.0
            if score >= float(_G.get("RELIC_SONG_MIN_SCORE", 55.0)):
                candidates.append((score, relic))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _actor_title_context(self, actor) -> Dict[str, Any]:
        """Gather facts used for non-duplicate, deed-aware song titles."""
        world = self.world
        ctx: Dict[str, Any] = {
            "name": actor.short_name() if actor is not None and hasattr(actor, "short_name") else "the Unknown",
            "region": "",
            "role": str(getattr(getattr(actor, "role", None), "value", getattr(actor, "role", "")) or "").lower(),
            "epithet": "",
            "polity": "",
            "relic": "",
        }
        if actor is None:
            return ctx
        rid = getattr(actor, "region_id", None)
        if rid in getattr(world, "regions", {}):
            ctx["region"] = world.region_name(rid)
        title = str(getattr(actor, "title", "") or "").strip()
        if title:
            ctx["epithet"] = title
        elif int(getattr(actor, "dragon_kills", 0) or 0) > 0:
            ctx["epithet"] = "Dragonslayer"
        elif int(getattr(actor, "horror_kills", 0) or 0) > 0:
            ctx["epithet"] = "Bane of the Deep"
        elif int(getattr(actor, "giant_kills", 0) or 0) > 0:
            ctx["epithet"] = "Giantbreaker"
        elif int(getattr(actor, "regions_defended", 0) or 0) > 0:
            ctx["epithet"] = "Defender"
        aid = getattr(actor, "id", None)
        for polh in getattr(world, "polity_history", {}).values():
            if getattr(polh, "founder_id", None) == aid or getattr(polh, "current_ruler_id", None) == aid:
                ctx["polity"] = getattr(polh, "name", "") or ""
                break
        for relic in getattr(world, "relics", {}).values():
            if getattr(relic, "holder_id", None) == aid or getattr(relic, "original_recipient_id", None) == aid:
                ctx["relic"] = getattr(relic, "name", "") or ""
                break
        return ctx

    def _normalize_song_title(self, title: Optional[str]) -> str:
        return " ".join(str(title or "").lower().split())

    def _ensure_song_title_norm_cache(self) -> Set[str]:
        world = getattr(self, "world", None)
        if world is None:
            return set()
        cache = getattr(world, "song_title_norm_cache", None)
        if isinstance(cache, set):
            return cache
        cache = {
            self._normalize_song_title(getattr(song, "title", ""))
            for song in getattr(world, "songs", {}).values()
            if not getattr(song, "forgotten", False)
            and str(getattr(song, "title", "") or "").strip()
        }
        world.song_title_norm_cache = cache
        return cache

    def _existing_song_titles_normalized(self) -> Set[str]:
        return self._ensure_song_title_norm_cache()

    def _song_title_is_available(self, title: Optional[str]) -> bool:
        title = str(title or "").strip()
        if not title:
            return False
        if not bool(_G.get("BARD_DUPLICATE_TITLE_BLOCK", True)):
            return True
        return self._normalize_song_title(title) not in self._ensure_song_title_norm_cache()

    def _song_title_candidates_for_actor(self, actor_id: int, bard) -> List[str]:
        actor = self.resolve_actor(actor_id) if hasattr(self, "resolve_actor") else self.world.actors.get(actor_id)
        ctx = self._actor_title_context(actor)
        name = ctx["name"]
        region = ctx["region"]
        role = ctx["role"] or "wanderer"
        epithet = ctx["epithet"]
        polity = ctx["polity"]
        relic = ctx["relic"]

        candidates: List[str] = []

        # Personal forms: still allowed, but no longer the whole title system.
        candidates.extend([
            f"The Lay of {name}",
            f"The Ballad of {name}",
            f"{name}'s Road",
            f"The Song of {name}",
            f"The Remembering of {name}",
        ])

        # Place / route forms.
        if region:
            candidates.extend([
                f"The Road to {region}",
                f"The Ballad of {region}",
                f"{name} at {region}",
                f"The {region} Lay",
                f"When {name} Came to {region}",
            ])

        # Deed / epithet forms.
        if epithet:
            candidates.extend([
                f"The {epithet}",
                f"{name} the {epithet}",
                f"The {epithet}'s Road",
                f"The Last Song of the {epithet}",
            ])
        if int(getattr(actor, "monster_kills", 0) or 0) > 0:
            candidates.extend([
                f"The Beasts That Broke on {name}",
                f"{name} and the Teeth Below",
                f"The Hunt at {region}" if region else f"The Hunt of {name}",
            ])
        if int(getattr(actor, "dragon_kills", 0) or 0) > 0:
            candidates.extend([
                f"Dragonfire and {name}",
                f"The Dragon's End",
                f"Smoke Over {region}" if region else f"Smoke Over the Road",
            ])
        if int(getattr(actor, "horror_kills", 0) or 0) > 0:
            candidates.extend([
                f"The Deep Thing Fell",
                f"{name} Against the Deep",
                f"The Horror Beneath {region}" if region else "The Horror Beneath",
            ])

        # Office / state / relic forms.
        if polity:
            candidates.extend([
                f"The Crown of {polity}",
                f"{name} Beneath the Crown",
                f"The Fall and Oath of {polity}",
            ])
        if relic:
            candidates.extend([
                f"{name} and {relic}",
                f"The Road to {relic}",
                f"The Hand That Held {relic}",
            ])

        # Poetic / legendary forms.
        surname = str(getattr(actor, "surname", "") or "").strip() if actor is not None else ""
        seed = surname or name.split()[-1]
        candidates.extend([
            f"Ashes and Crowns",
            f"The Broken Banner",
            f"Blood on the High Road",
            f"When {name} Rode West",
            f"The {role.title()}'s Last Dawn",
            f"{seed} Beneath the Stars",
            f"The Road That Remembered",
            f"No Grave for {name}",
        ])

        # Preserve order while removing exact duplicates from the candidate pool.
        out: List[str] = []
        seen: Set[str] = set()
        for title in candidates:
            title = " ".join(str(title or "").split())
            norm = title.lower()
            if title and norm not in seen:
                seen.add(norm)
                out.append(title)
        return out

    def _song_title_for_actor(self, actor_id: int, bard) -> str:
        candidates = self._song_title_candidates_for_actor(actor_id, bard)
        existing = self._existing_song_titles_normalized()
        self.rng.shuffle(candidates)
        for title in candidates:
            if " ".join(title.lower().split()) not in existing:
                return title
        # Last-resort uniqueness without numbering the title.
        name = self._song_subject_name(actor_id)
        region = self.world.region_name(getattr(bard, "region_id", -1)) if getattr(bard, "region_id", -1) in getattr(self.world, "regions", {}) else "the Road"
        fallback_pool = [
            f"Another Road to {region}",
            f"The Unfinished Lay of {name}",
            f"The Lost Verse of {name}",
            f"The Quiet Road Beyond {region}",
        ]
        self.rng.shuffle(fallback_pool)
        for title in fallback_pool:
            if " ".join(title.lower().split()) not in existing:
                return title
        return None

    def _song_title_for_relic(self, relic) -> Optional[str]:
        name = getattr(relic, "name", "the Lost Relic")
        return self._song_title_unique([
            f"The Whisper of {name}",
            f"The Road to {name}",
            f"The Lament of {name}",
            f"The Seeking of {name}",
        ])

    def _song_pressure_value(self, song: Song) -> float:
        return max(
            0.0,
            float(getattr(song, "popularity", 0.0) or 0.0) * 0.10
            + float(getattr(song, "historical_weight", 0.0) or 0.0) * 0.035
            + len(getattr(song, "known_region_ids", set()) or set()) * 0.20,
        )

    def _private_song_has_public_reach(self, song: Song) -> bool:
        return (
            int(getattr(song, "performances", 0) or 0) >= int(_G.get("PRIVATE_SONG_PUBLIC_PERFORMANCES", 8))
            or len(getattr(song, "known_region_ids", set()) or set()) >= int(_G.get("PRIVATE_SONG_PUBLIC_REGIONS", 3))
            or float(getattr(song, "popularity", 0.0) or 0.0) >= float(_G.get("PRIVATE_SONG_PUBLIC_POPULARITY", 25.0))
            or float(getattr(song, "historical_weight", 0.0) or 0.0) >= float(_G.get("PRIVATE_SONG_PUBLIC_HISTORICAL_WEIGHT", 18.0))
        )

    def _mythic_song_type_feeds_legend(self, song_type: str) -> bool:
        return str(song_type or "").lower() in {"mythic", "relic", "terror", "villain", "lament", "cautionary", "conquest", "hymn"}

    def _apply_hymn_religious_pressure(self, song: Song, value: float) -> None:
        deity = getattr(song, "subject_deity", None)
        if deity is None:
            return
        world = self.world
        world.hymn_pressure_by_deity[deity] = float(world.hymn_pressure_by_deity.get(deity, 0.0) or 0.0) + float(value or 0.0)
        known_regions = set(getattr(song, "known_region_ids", set()) or set())
        if not known_regions:
            rid = getattr(song, "origin_region_id", None)
            if rid is not None:
                known_regions.add(rid)
        if not hasattr(world, "commoner_faith_by_region"):
            return
        base_rate = float(_G.get("HYMN_COMMONER_CONVERSION_RATE", 0.0015))
        cap = int(_G.get("HYMN_COMMONER_CONVERSION_CAP", 30))
        conviction_bonus = int(_G.get("HYMN_ACTOR_CONVICTION_BONUS", 1))
        doubt_reduction = float(_G.get("HYMN_ACTOR_DOUBT_REDUCTION", 0.01))
        pressure_scale = min(3.0, max(0.25, float(value or 0.0) / 10.0))
        for rid in known_regions:
            faith = getattr(world, "commoner_faith_by_region", {}).get(rid)
            commoners = int(getattr(world, "commoners_by_region", {}).get(rid, 0) or 0)
            if not isinstance(faith, dict) or commoners <= 0:
                continue
            faith.setdefault(deity, 0)
            sources = [d for d in list(faith.keys()) if d != deity and int(faith.get(d, 0) or 0) > 0]
            pool = sum(int(faith.get(d, 0) or 0) for d in sources)
            moved = min(pool, cap, int(max(0, commoners) * base_rate * pressure_scale))
            if moved > 0 and sources:
                # Pull from the largest local faith first. Crude, but stable and cheap.
                sources.sort(key=lambda d: int(faith.get(d, 0) or 0), reverse=True)
                remaining = moved
                for src in sources:
                    take = min(remaining, int(faith.get(src, 0) or 0))
                    if take <= 0:
                        continue
                    faith[src] = int(faith.get(src, 0) or 0) - take
                    faith[deity] = int(faith.get(deity, 0) or 0) + take
                    remaining -= take
                    if remaining <= 0:
                        break
            # Local adventurers of the same faith are steadied by living hymns.
            for actor in list(getattr(world, "actors_in_region", lambda r: [])(rid)):
                if not getattr(actor, "alive", False):
                    continue
                if getattr(actor, "deity", None) == deity:
                    if conviction_bonus and hasattr(actor, "deity_conviction"):
                        actor.deity_conviction = min(100, int(getattr(actor, "deity_conviction", 50) or 50) + conviction_bonus)
                    if doubt_reduction and hasattr(actor, "faith_doubt"):
                        actor.faith_doubt = max(0.0, float(getattr(actor, "faith_doubt", 0.0) or 0.0) - doubt_reduction)

    def _apply_song_legend_pressure(self) -> None:
        self._ensure_lore_state()
        world = self.world
        world.legend_pressure_by_actor_id = {}
        world.legend_pressure_by_relic_id = {}
        world.legend_pressure_by_monster_id = {}
        world.hymn_pressure_by_deity = {}
        for song in getattr(world, "songs", {}).values():
            if getattr(song, "forgotten", False):
                continue
            value = self._song_pressure_value(song)
            performers = len(getattr(song, "performer_actor_ids", set()) or set())
            if performers:
                value += performers * float(_G.get("BARD_UNIQUE_PERFORMER_WEIGHT", 2.5))
            visibility = str(getattr(song, "visibility", "public") or "public").lower()
            song_type = str(getattr(song, "song_type", "mythic" if visibility == "public" else "personal") or "mythic").lower()

            if not self._mythic_song_type_feeds_legend(song_type):
                self._award_song_bard_fame_if_ready(song)
                continue

            if visibility == "private":
                if self._private_song_has_public_reach(song):
                    credit_id = getattr(song, "fame_credit_actor_id", None) or getattr(song, "composer_id", None)
                    if credit_id is not None:
                        fame_value = value * float(_G.get("PRIVATE_SONG_BARD_FAME_MULTIPLIER", 0.75))
                        world.legend_pressure_by_actor_id[credit_id] = float(world.legend_pressure_by_actor_id.get(credit_id, 0.0)) + fame_value
                        self._award_song_bard_fame_if_ready(song)
                continue

            if song_type == "hymn":
                self._apply_hymn_religious_pressure(song, value)
                self._award_song_bard_fame_if_ready(song)
                continue

            actor_mult = 1.0
            if song_type == "villain":
                actor_mult = float(_G.get("VILLAIN_SONG_LEGEND_PRESSURE_MULT", 0.85))
            for actor_id in getattr(song, "subject_actor_ids", []) or []:
                world.legend_pressure_by_actor_id[actor_id] = float(world.legend_pressure_by_actor_id.get(actor_id, 0.0)) + value * actor_mult

            relic_id = getattr(song, "subject_relic_id", None)
            if relic_id is not None:
                world.legend_pressure_by_relic_id[relic_id] = float(world.legend_pressure_by_relic_id.get(relic_id, 0.0)) + value * float(_G.get("RELIC_LEGEND_PRESSURE_MULT", 0.65))

            monster_id = getattr(song, "subject_monster_id", None)
            if monster_id is not None:
                world.legend_pressure_by_monster_id[monster_id] = float(world.legend_pressure_by_monster_id.get(monster_id, 0.0)) + value * float(_G.get("MONSTER_LEGEND_PRESSURE_MULT", 1.0))

    def _mythic_legacy_profile_for_actor(self, actor) -> Dict[str, float]:
        """Build a broad mythic profile so no one deed can create a god alone."""
        if actor is None:
            return {}
        profile = {
            "martial": 0.0,
            "leadership": 0.0,
            "cultural": 0.0,
            "religious": 0.0,
            "social": 0.0,
            "infamy": 0.0,
        }
        profile["martial"] += max(0, int(getattr(actor, "monster_kills", 0))) * 4.0
        profile["martial"] += max(0, int(getattr(actor, "giant_kills", 0))) * 24.0
        profile["martial"] += max(0, int(getattr(actor, "dragon_kills", 0))) * 70.0
        profile["martial"] += max(0, int(getattr(actor, "horror_kills", 0))) * 90.0
        waves = max(0, int(getattr(actor, "black_host_waves_survived", 0)))
        if waves:
            profile["martial"] += sum(25.0 * i for i in range(1, waves + 1))
        profile["martial"] += max(0, int(getattr(actor, "black_host_victories", 0))) * 100.0
        profile["martial"] += max(0, int(getattr(actor, "regions_defended", 0))) * 18.0

        world = self.world
        aid = int(getattr(actor, "id", -1))
        # Use tick-local indexes if available; fall back to full scans otherwise.
        _ph_by_founder = getattr(world, "_lore_party_history_by_founder", None)
        _pty_by_leader = getattr(world, "_lore_current_party_by_leader", None)
        _polh_by_actor = getattr(world, "_lore_polity_history_by_actor", None)
        party_histories = _ph_by_founder.get(aid, []) if _ph_by_founder is not None else [
            ph for ph in getattr(world, "party_history", {}).values() if getattr(ph, "founder_id", None) == aid
        ]
        for ph in party_histories:
            profile["leadership"] += 55.0 + min(80.0, float(getattr(ph, "peak_size", 0) or 0)) * 0.8
            profile["leadership"] += min(120.0, float(getattr(ph, "peak_reputation", 0) or 0) * 0.15)
        current_party = _pty_by_leader.get(aid) if _pty_by_leader is not None else next(
            (pty for pty in getattr(world, "parties", {}).values() if getattr(pty, "leader_id", None) == aid), None
        )
        if current_party is not None:
            profile["leadership"] += 30.0 + len(getattr(current_party, "member_ids", []) or []) * 1.5
        polity_histories = _polh_by_actor.get(aid, []) if _polh_by_actor is not None else [
            polh for polh in getattr(world, "polity_history", {}).values()
            if getattr(polh, "founder_id", None) == aid or getattr(polh, "current_ruler_id", None) == aid
        ]
        for polh in polity_histories:
            if getattr(polh, "founder_id", None) == aid:
                profile["leadership"] += 100.0 + max(0, int(getattr(polh, "peak_regions", 0) or 0)) * 45.0
            if getattr(polh, "current_ruler_id", None) == aid:
                profile["leadership"] += 55.0 + max(0, int(getattr(polh, "peak_regions", 0) or 0)) * 20.0
        if getattr(actor, "office_title", None) or getattr(actor, "military_rank", None):
            profile["leadership"] += 15.0

        # Use tick-local index if available (built by _bardic_memory_turn and _update_proto_cults).
        # Falls back to a full scan on first call or outside bardic context.
        _sbs = getattr(world, "_lore_songs_by_subject", None)
        if _sbs is not None:
            songs = [s for s in _sbs.get(aid, []) if not getattr(s, "forgotten", False)]
        else:
            songs = [
                song for song in getattr(world, "songs", {}).values()
                if aid in (getattr(song, "subject_actor_ids", []) or [])
                and not getattr(song, "forgotten", False)
                and str(getattr(song, "visibility", "public") or "public").lower() != "private"
                and str(getattr(song, "song_type", "mythic") or "mythic").lower() == "mythic"
            ]
        _csba = getattr(world, "_lore_credited_songs_by_actor", None)
        if _csba is not None:
            credited_private_songs = [s for s in _csba.get(aid, []) if not getattr(s, "forgotten", False)]
        else:
            credited_private_songs = [
                song for song in getattr(world, "songs", {}).values()
                if int(getattr(song, "fame_credit_actor_id", -1) or -1) == aid
                and not getattr(song, "forgotten", False)
                and str(getattr(song, "song_type", "mythic") or "mythic").lower() != "mythic"
                and self._song_public_credit_reached(song)
            ]
        profile["cultural"] += len(songs) * 8.0
        profile["cultural"] += sum(min(50.0, float(getattr(song, "historical_weight", 0.0) or 0.0) * 0.02) for song in songs[:50])
        profile["cultural"] += sum(min(25.0, float(getattr(song, "popularity", 0.0) or 0.0) * 0.05) for song in songs[:50])
        profile["cultural"] += len(credited_private_songs) * float(_G.get("PRIVATE_SONG_BARD_CULTURAL_BONUS", 6.0))
        profile["cultural"] += sum(min(30.0, float(getattr(song, "historical_weight", 0.0) or 0.0) * 0.015) for song in credited_private_songs[:50])
        profile["cultural"] += sum(1 for c in getattr(world, "commemorations", []) if getattr(c, "actor_id", None) == aid) * 35.0
        profile["cultural"] += min(200.0, float(getattr(world, "legend_pressure_by_actor_id", {}).get(aid, 0.0)) * 0.08)

        if getattr(actor, "champion_of", None) is not None:
            profile["religious"] += 80.0
        profile["religious"] += max(0, int(getattr(actor, "converted_followers", 0))) * 0.08
        if getattr(actor, "relic_id", None) is not None:
            profile["religious"] += 70.0

        profile["social"] += len(getattr(actor, "children_ids", []) or []) * 4.0
        profile["social"] += len(getattr(actor, "friend_ids", []) or []) * 3.0
        if getattr(actor, "spouse_id", None) is not None:
            profile["social"] += 8.0
        if getattr(actor, "best_friend_id", None) is not None:
            profile["social"] += 8.0

        profile["infamy"] += max(0, int(getattr(actor, "kills", 0))) * 3.0
        profile["infamy"] += max(0, int(getattr(actor, "regions_oppressed", 0))) * 22.0
        if getattr(actor, "is_evil", lambda: False)():
            profile["infamy"] += max(0, int(getattr(actor, "reputation", 0))) * 0.45
        else:
            profile["cultural"] += max(0, int(getattr(actor, "reputation", 0))) * 0.35
        return {k: round(max(0.0, v), 2) for k, v in profile.items() if v > 0.0}

    def _mythic_legacy_score(self, profile: Dict[str, float]) -> float:
        if not profile:
            return 0.0
        # Diminishing returns by axis keeps one spectacular deed from doing all the work.
        return round(sum(min(260.0, float(v)) for v in profile.values()), 2)

    def _mythic_axis_count(self, profile: Dict[str, float], floor: float = 35.0) -> int:
        return sum(1 for v in (profile or {}).values() if float(v) >= floor)

    def _cult_weights_from_profile(self, actor, profile: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
        domains: Dict[str, float] = {}
        traits: Dict[str, float] = {}
        def add(target, key, amount):
            target[key] = float(target.get(key, 0.0)) + float(amount)
        martial = float(profile.get("martial", 0.0))
        leadership = float(profile.get("leadership", 0.0))
        cultural = float(profile.get("cultural", 0.0))
        religious = float(profile.get("religious", 0.0))
        social = float(profile.get("social", 0.0))
        infamy = float(profile.get("infamy", 0.0))
        if martial:
            add(domains, "war", martial); add(domains, "protection", martial * 0.75)
            add(traits, "guardian", martial * 0.55); add(traits, "enduring", martial * 0.45)
        if max(0, int(getattr(actor, "black_host_waves_survived", 0))) > 0:
            add(domains, "protection", 120); add(domains, "death", 70)
            add(traits, "unbroken", 120); add(traits, "sentinel", 90)
        if leadership:
            add(domains, "order", leadership); add(traits, "sovereign", leadership * 0.8)
        if cultural:
            add(domains, "knowledge", cultural * 0.7); add(domains, "inspiration", cultural)
            add(traits, "remembered", cultural * 0.8)
        if religious:
            add(domains, "fate", religious); add(traits, "chosen", religious * 0.8)
        if social:
            add(domains, "life", social * 0.5); add(traits, "kinbound", social * 0.6)
        if infamy:
            add(domains, "war", infamy * 0.7); add(domains, "shadow", infamy)
            add(traits, "dread", infamy); add(traits, "tyrant", infamy * 0.65)
        role = getattr(actor, "role", None)
        if role == Role.BARD:
            add(domains, "inspiration", 80); add(domains, "trickery", 45)
        elif role == Role.WARDEN:
            add(domains, "protection", 70); add(domains, "growth", 35)
        elif role == Role.WIZARD:
            add(domains, "knowledge", 80); add(domains, "mystery", 55)
        return domains, traits

    def _apply_cult_archetype_weights(self, title: str, domains: Dict[str, float], traits: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Let the claimed public archetype steer the final domain/trait mix.

        The raw mythic profile intentionally preserves the factual record: conquest,
        rulership, infamy, songs, religion, family.  The public title is the
        culture's interpretation of that record.  Without this pass, villainous
        archetypes collapse too often into shadow/order/war regardless of whether
        the title suggests thief, tyrant, or ruthless victor.
        """
        domains = dict(domains or {})
        traits = dict(traits or {})

        def add(target, key, amount):
            target[key] = float(target.get(key, 0.0) or 0.0) + max(0.0, float(amount or 0.0))

        def scale(target, key, factor):
            if key in target:
                target[key] = max(0.0, float(target.get(key, 0.0) or 0.0) * max(0.0, float(factor)))

        norm = self._normalized_cult_title(title) if hasattr(self, "_normalized_cult_title") else " ".join(str(title or "").lower().split())
        if not norm:
            return domains, traits

        seed = max(40.0, max([float(v or 0.0) for v in domains.values()] + [0.0]), max([float(v or 0.0) for v in traits.values()] + [0.0]) * 0.75)

        if "hand" in norm:
            # Hand archetypes are clandestine: thieves, spies, conspirators,
            # assassins, secret teachers.  They can be dangerous without reading
            # as open conquerors.
            add(domains, "shadow", seed * 0.25)
            add(domains, "trickery", seed * 0.80)
            add(domains, "knowledge", seed * 0.55)
            scale(domains, "war", 0.55)
            scale(domains, "order", 0.45)
            add(traits, "dread", seed * 0.20)
            add(traits, "cunning", seed * 0.75)
            add(traits, "secretive", seed * 0.65)
            add(traits, "remembered", seed * 0.18)
            scale(traits, "sovereign", 0.35)
            scale(traits, "tyrant", 0.50)
        elif "crown" in norm or "seat" in norm or "law giver" in norm or "oath crowned" in norm:
            # Crown archetypes rule in the open.  Dread can remain, but shadow
            # should not dominate an ideology built around public sovereignty.
            scale(domains, "shadow", 0.12)
            add(domains, "war", seed * 0.55)
            add(domains, "order", seed * 0.70)
            add(domains, "inspiration", seed * 0.38)
            add(traits, "sovereign", seed * 0.70)
            add(traits, "commanding", seed * 0.48)
            add(traits, "dread", seed * 0.30)
            scale(traits, "secretive", 0.20)
        elif "victor" in norm or "banner" in norm:
            # Victor archetypes are not necessarily rulers; they are remembered
            # for victory-at-any-cost, ambush, betrayal, conquest, and the
            # ugly utility of winning.
            add(domains, "shadow", seed * 0.45)
            add(domains, "war", seed * 0.75)
            add(domains, "trickery", seed * 0.55)
            scale(domains, "order", 0.40)
            add(traits, "dread", seed * 0.45)
            add(traits, "ruthless", seed * 0.65)
            add(traits, "cunning", seed * 0.42)
            add(traits, "conqueror", seed * 0.55)
            scale(traits, "sovereign", 0.45)

        domains = {k: round(v, 2) for k, v in domains.items() if float(v) > 0.0}
        traits = {k: round(v, 2) for k, v in traits.items() if float(v) > 0.0}
        return domains, traits


    def _normalized_cult_title(self, title: str) -> str:
        return " ".join(str(title or "").strip().lower().replace("-", " ").split())

    def _reserved_cult_titles(self, exclude_cult_id: Optional[int] = None) -> Set[str]:
        """Titles are global mythic archetypes. Once claimed, another cult cannot reuse them."""
        reserved: Set[str] = set()
        world = getattr(self, "world", None)
        if world is None:
            return reserved
        for cult in getattr(world, "proto_cults", {}).values():
            if exclude_cult_id is not None and getattr(cult, "id", None) == exclude_cult_id:
                continue
            if getattr(cult, "failed", False):
                continue
            title = getattr(cult, "public_title", "") or ""
            norm = self._normalized_cult_title(title)
            if norm:
                reserved.add(norm)
        for god in getattr(world, "gods", []) or []:
            norm = self._normalized_cult_title(getattr(god, "name", "") or "")
            if norm:
                reserved.add(norm)
        return reserved

    def _title_candidates_for_ascended_cult(self, actor, domains: Dict[str, float], traits: Dict[str, float]) -> List[str]:
        """Return title candidates in profile-weight order, not random order.

        A title is an archetype, not a person's name. This list should be broad
        enough that bard, ruler, tyrant, guardian, scholar, and warrior cults can
        each claim a distinct mythic niche.
        """
        trait_titles = {
            "unbroken": ["The Unbroken Shield", "The Last Sentinel", "The Grave-Host Survivor", "The One Who Stood"],
            "sentinel": ["The Watcher at the Gate", "The Dead-Banner Breaker", "The Last Watch", "The Gate-Warden"],
            "sovereign": ["The Iron Crown", "The High Seat", "The Crown Unbowed", "The Oath-Crowned"],
            "dread": ["The Red Hand", "The Dread Crown", "The Black Victor", "The Fear Below"],
            "tyrant": ["The Dread Crown", "The Chain-Lord", "The Iron Heel", "The Black Victor"],
            "guardian": ["The Defender", "The Shield-Bearer", "The Hearth-Warden", "The Wall That Held"],
            "enduring": ["The One Who Endures", "The Stone Heart", "The Last Ember", "The Unfallen"],
            "remembered": ["The Voice Remembered", "The Living Song", "The Road-Singer", "The Keeper of Echoes"],
            "chosen": ["The Chosen Flame", "The Marked One", "The Hand of Fate", "The Omen-Bearer"],
            "kinbound": ["The Hearth-Bound", "The Blood-Keeper", "The Root and Branch", "The House-Mother"],
        }
        domain_titles = {
            "protection": ["The Defender", "The Shield-Bearer", "The Hearth-Warden", "The Wall That Held"],
            "war": ["The Spear-Saint", "The Battle-Father", "The Sword Below", "The Red Banner"],
            "inspiration": ["The Living Song", "The Voice Remembered", "The Road-Singer", "The Wandering Verse", "The Last Balladeer"],
            "knowledge": ["The Lantern Mind", "The Hidden Teacher", "The Keeper of Names", "The Quiet Oracle"],
            "order": ["The Iron Crown", "The High Seat", "The Law-Giver", "The Oath-Crowned"],
            "shadow": ["The Red Hand", "The Black Victor", "The Knife in Prayer", "The Fear Below"],
            "death": ["The Grave Sentinel", "The Dead-Banner Breaker", "The Keeper of Ashes", "The Last Rite"],
            "fate": ["The Hand of Fate", "The Omen-Bearer", "The Turning Star", "The Thread-Keeper"],
            "life": ["The Hearth-Bound", "The Green Hand", "The Root and Branch", "The Life-Giver"],
            "trickery": ["The Laughing Mask", "The Silver Tongue", "The Road-Singer", "The Hidden Jest"],
            "growth": ["The Green Hand", "The Root and Branch", "The Spring-Warden", "The Seed-Keeper"],
            "mystery": ["The Hidden Teacher", "The Quiet Oracle", "The Veiled Star", "The Locked Door"],
        }
        ranked_keys: List[Tuple[str, str, float]] = []
        ranked_keys.extend(("trait", k, float(v)) for k, v in (traits or {}).items())
        ranked_keys.extend(("domain", k, float(v)) for k, v in (domains or {}).items())
        ranked_keys.sort(key=lambda item: item[2], reverse=True)
        candidates: List[str] = []
        seen: Set[str] = set()
        for kind, key, _weight in ranked_keys:
            pool = trait_titles.get(key, []) if kind == "trait" else domain_titles.get(key, [])
            for title in pool:
                norm = self._normalized_cult_title(title)
                if norm and norm not in seen:
                    seen.add(norm)
                    candidates.append(title)
        if not candidates:
            candidates.append("The Remembered")
        return candidates

    def _title_for_ascended_cult(self, actor, domains: Dict[str, float], traits: Dict[str, float], reserved_titles: Optional[Set[str]] = None) -> str:
        reserved_titles = reserved_titles or set()
        candidates = self._title_candidates_for_ascended_cult(actor, domains, traits)
        for title in candidates:
            if self._normalized_cult_title(title) not in reserved_titles:
                return title
        return ""

    def _enforce_unique_cult_titles(self) -> None:
        """Repair/maintain global title uniqueness, including old saves with duplicates."""
        world = getattr(self, "world", None)
        if world is None:
            return
        cults = [c for c in getattr(world, "proto_cults", {}).values() if not getattr(c, "failed", False) and not getattr(c, "formalized", False)]
        cults.sort(key=lambda c: (bool(getattr(c, "ascended", False)), float(getattr(c, "legend_pressure", 0.0) or 0.0), float(getattr(c, "mythic_legacy_score", 0.0) or 0.0)), reverse=True)
        reserved = {self._normalized_cult_title(getattr(god, "name", "") or "") for god in getattr(world, "gods", []) or []}
        reserved.discard("")
        for cult in cults:
            actor = self.resolve_actor(getattr(cult, "subject_actor_id", None)) if hasattr(self, "resolve_actor") else None
            current = self._normalized_cult_title(getattr(cult, "public_title", "") or "")
            if current and current not in reserved:
                reserved.add(current)
                continue
            if actor is not None:
                profile = self._mythic_legacy_profile_for_actor(actor)
                cult.mythic_profile = profile
                cult.mythic_legacy_score = self._mythic_legacy_score(profile)
                domains, traits = self._cult_weights_from_profile(actor, profile)
                cult.domain_weights = domains
                cult.trait_weights = traits
            else:
                domains = getattr(cult, "domain_weights", {}) or {}
                traits = getattr(cult, "trait_weights", {}) or {}
            new_title = self._title_for_ascended_cult(actor, domains, traits, reserved)
            if new_title:
                old_title = getattr(cult, "public_title", "") or "untitled"
                cult.public_title = new_title
                reserved.add(self._normalized_cult_title(new_title))
                if current:
                    world.log(f"{cult.name} abandons the duplicate title {old_title} and is now whispered of as {new_title}.", importance=2, category="proto_cult")
            else:
                cult.failed = True
                world.log(f"{cult.name} fades before becoming distinct; every fitting divine title has already been claimed.", importance=2, category="proto_cult")

    def _religious_doubt_drivers_for_actor(self, actor, cults, state, max_influence: float) -> Dict[str, float]:
        """Return per-drift-tick doubt pressure from lived conditions.

        These values are intentionally incremental. The stored faith_doubt still
        decays each drift tick, so persistent hardship accumulates while stable
        regions recover instead of permanently ratcheting upward.
        """
        world = self.world
        drivers: Dict[str, float] = {}

        def add(name: str, value: float, cap: Optional[float] = None) -> None:
            try:
                value = float(value or 0.0)
            except Exception:
                return
            if value <= 0.0:
                return
            if cap is not None:
                value = min(float(cap), value)
            drivers[name] = drivers.get(name, 0.0) + value

        rid = getattr(actor, "region_id", None)
        region = getattr(world, "regions", {}).get(rid)
        deity = getattr(actor, "deity", None)

        # Long worship becomes brittle: not a lock-in, just accumulated exposure
        # to disappointment. This now matters but should not dominate by itself.
        duration_years = worship_duration_years(self, actor)
        add("worship-duration", max(0.0, duration_years) * 0.00015, 0.025)

        st = state.get(deity) if isinstance(state, dict) else None
        influence = float(getattr(st, "influence", 0.0) or 0.0) if st is not None else 0.0
        if influence < max_influence * 0.20:
            add("weak-god", 0.018)
        elif influence < max_influence * 0.40:
            add("lagging-god", 0.008)

        if region is not None:
            order = float(getattr(region, "order", 50.0) or 0.0)
            control = float(getattr(region, "control", 0.0) or 0.0)
            danger = float(getattr(region, "danger", 0.0) or 0.0)
            if order < 55:
                add("low-order", ((55.0 - order) / 55.0) * 0.020, 0.020)
            if control < -15:
                add("oppression", ((-15.0 - control) / 85.0) * 0.018, 0.018)
            if danger > 0:
                add("regional-danger", (danger / 100.0) * 0.018, 0.018)

            # Cumulative regional deaths are crude, but they are the available
            # signal. Convert them to a trauma ratio against known local history.
            deaths = int(getattr(world, "commoner_deaths_by_region", {}).get(rid, 0) or 0)
            living_commoners = int(getattr(world, "commoners_by_region", {}).get(rid, 0) or 0)
            if deaths > 0:
                death_ratio = deaths / max(1, deaths + living_commoners)
                add("local-death-memory", death_ratio * 0.030, 0.030)

            # Active monster threat is immediate religious stress.
            monsters = []
            try:
                monsters = list(world.monsters_in_region(rid))
            except Exception:
                monsters = [m for m in getattr(world, "monsters", {}).values() if getattr(m, "alive", False) and getattr(m, "region_id", None) == rid]
            threat = 0.0
            for monster in monsters:
                if not getattr(monster, "alive", False):
                    continue
                kind = getattr(monster, "kind", None)
                if kind == MonsterKind.ANCIENT_HORROR or str(getattr(kind, "value", kind)).lower().find("horror") >= 0:
                    threat += 0.030
                elif kind == MonsterKind.DRAGON or str(getattr(kind, "value", kind)).lower().find("dragon") >= 0:
                    threat += 0.024
                elif kind == MonsterKind.GIANT or str(getattr(kind, "value", kind)).lower().find("giant") >= 0:
                    threat += 0.012
                elif kind == MonsterKind.GOBLIN or str(getattr(kind, "value", kind)).lower().find("goblin") >= 0:
                    threat += 0.005
            add("monster-threat", threat, 0.040)

            # Local political/religious mismatch. Being under a hostile public
            # order should make private doubts easier to sustain.
            polity = getattr(world, "polities", {}).get(getattr(actor, "polity_id", None))
            if polity is None and getattr(region, "polity_id", None) is not None:
                polity = getattr(world, "polities", {}).get(getattr(region, "polity_id", None))
            ruler = None
            if polity is not None:
                ruler = getattr(world, "actors", {}).get(getattr(polity, "ruler_id", None))
                stability = float(getattr(polity, "stability", 50.0) or 0.0)
                legitimacy = float(getattr(polity, "legitimacy", 50.0) or 0.0)
                challenges = float(getattr(polity, "succession_challenges", getattr(polity, "challenges", 0)) or 0.0)
                if stability < 60:
                    add("state-instability", ((60.0 - stability) / 60.0) * 0.018, 0.018)
                if legitimacy < 55:
                    add("low-legitimacy", ((55.0 - legitimacy) / 55.0) * 0.012, 0.012)
                if challenges > 0:
                    add("succession-strain", challenges * 0.0025, 0.015)
            if ruler is None and getattr(region, "ruler_id", None) is not None:
                ruler = getattr(world, "actors", {}).get(getattr(region, "ruler_id", None))
            if ruler is not None and getattr(ruler, "alive", False) and getattr(ruler, "deity", None) != deity:
                add("ruler-faith-pressure", 0.012 if polity is not None else 0.007)

            faith = getattr(world, "commoner_faith_by_region", {}).get(rid, {})
            if faith:
                dominant = max(faith, key=lambda d: faith.get(d, 0))
                if dominant != deity:
                    total = sum(max(0, int(v)) for v in faith.values()) or 1
                    share = int(faith.get(dominant, 0)) / total
                    add("local-faith-mismatch", share * 0.012, 0.012)

        # Personal social damage. We do not need perfect cause tracking here;
        # dead spouse/friends/family are enough to create religious stress.
        actors = getattr(world, "actors", {})
        def live_actor(aid):
            return actors.get(aid) if aid is not None else None
        spouse_id = getattr(actor, "spouse_id", None)
        if spouse_id is not None and live_actor(spouse_id) is None:
            add("lost-spouse", 0.018)
        best_id = getattr(actor, "best_friend_id", None)
        if best_id is not None and live_actor(best_id) is None:
            add("lost-best-friend", 0.012)
        dead_friends = 0
        for fid in getattr(actor, "friend_ids", []) or []:
            if fid is not None and live_actor(fid) is None:
                dead_friends += 1
        add("lost-friends", dead_friends * 0.004, 0.020)
        dead_family = 0
        for fid in (getattr(actor, "mother_id", None), getattr(actor, "father_id", None)):
            if fid is not None and live_actor(fid) is None:
                dead_family += 1
        add("lost-family", dead_family * 0.006, 0.012)
        if getattr(actor, "revenge_target_ids", None) or getattr(actor, "revenge_monster_ids", None):
            add("vengeance-burden", 0.008)

        # Nearby cult pressure should increase doubt even before membership.
        if rid is not None and cults:
            local_pressure = 0.0
            local_commoners = 0
            for cult in cults:
                if rid not in getattr(cult, "known_region_ids", set()):
                    continue
                local_pressure = max(local_pressure, float(getattr(cult, "legend_pressure", 0.0) or 0.0))
                local_commoners += int(getattr(cult, "hidden_commoner_affinity_by_region", {}).get(rid, 0) or 0)
            add("cult-pressure", min(1.0, local_pressure / 100000.0) * 0.020, 0.020)
            add("hidden-commoner-cult", min(1.0, local_commoners / 1000.0) * 0.012, 0.012)

        return drivers

    def _update_actor_religious_drift(self) -> None:
        """Update faith doubt and singular proto-cult membership pressure."""
        world = self.world
        cadence = int(_G.get("RELIGIOUS_DRIFT_INTERVAL_TICKS", _G.get("TICKS_PER_MONTH", 120)))
        if world.tick - int(getattr(world, "last_religious_drift_tick", -999999)) < cadence:
            return
        world.last_religious_drift_tick = world.tick
        if not bool(_G.get("RELIGIOUS_DRIFT_ENABLED", True)):
            return
        pantheon = list(getattr(world, "gods", []) or [])
        if not pantheon:
            return
        state = getattr(world, "god_state", {}) or {}
        max_influence = 1.0
        for god in pantheon:
            st = state.get(god)
            max_influence = max(max_influence, float(getattr(st, "influence", 0.0) or 0.0))
        cults = [c for c in getattr(world, "proto_cults", {}).values() if not getattr(c, "failed", False) and not getattr(c, "formalized", False)]
        decay = float(_G.get("FAITH_DOUBT_DECAY_PER_DRIFT", 0.97))
        for actor in world.living_actors():
            if getattr(actor, "role", None) == Role.COMMONER or getattr(actor, "in_school", False):
                continue
            ensure_actor_religion_tracking(self, actor)
            prior = float(getattr(actor, "faith_doubt", 0.0) or 0.0)
            drivers = self._religious_doubt_drivers_for_actor(actor, cults, state, max_influence)
            doubt = prior * decay + sum(drivers.values())
            dampers: Dict[str, float] = {}
            if getattr(actor, "champion_of", None) is not None:
                dampers["champion"] = 0.72
                doubt *= 0.72
            if getattr(actor, "locked_deity", False):
                dampers["locked-deity"] = 0.60
                doubt *= 0.60
            actor.faith_doubt = max(0.0, min(1.0, doubt))
            actor.faith_doubt_drivers = dict(sorted(drivers.items(), key=lambda item: item[1], reverse=True))
            actor.faith_doubt_dampers = dampers
            if not cults or actor.faith_doubt < float(_G.get("CULT_AFFINITY_MIN_DOUBT", 0.08)):
                continue
            rid = getattr(actor, "region_id", None)
            if not isinstance(getattr(actor, "cult_affinity", None), dict):
                actor.cult_affinity = {}

            # Affinity is a distribution of secret religious attention, not an
            # independent 0..1 score per cult. Update raw pressures first, then
            # normalize so sum(actor.cult_affinity.values()) never exceeds 1.0.
            touched_keys = set()
            cult_by_key = {}
            for cult in cults:
                key = str(getattr(cult, "id", ""))
                if not key:
                    continue
                cult_by_key[key] = cult
                if rid not in getattr(cult, "known_region_ids", set()):
                    continue
                pressure = min(1.0, float(getattr(cult, "legend_pressure", 0.0) or 0.0) / 50000.0)
                local_commoner = int(getattr(cult, "hidden_commoner_affinity_by_region", {}).get(rid, 0) or 0)
                local_factor = min(1.0, local_commoner / 1000.0)
                actor_bonus = 0.0
                subject = self.resolve_actor(getattr(cult, "subject_actor_id", None)) if hasattr(self, "resolve_actor") else None
                if subject is not None:
                    if getattr(subject, "role", None) == getattr(actor, "role", None):
                        actor_bonus += 0.012
                    if getattr(subject, "alignment", None) == getattr(actor, "alignment", None):
                        actor_bonus += 0.010
                    if getattr(actor, "mother_id", None) == getattr(subject, "id", None) or getattr(actor, "father_id", None) == getattr(subject, "id", None):
                        actor_bonus += 0.040
                gain = (0.004 + pressure * 0.012 + local_factor * 0.010 + actor_bonus) * (0.5 + actor.faith_doubt)
                actor.cult_affinity[key] = max(0.0, float(actor.cult_affinity.get(key, 0.0) or 0.0) + gain)
                touched_keys.add(key)

            # Drop extinct/formalized/failed cult keys and clamp noise.
            valid_keys = set(cult_by_key.keys())
            actor.cult_affinity = {
                key: max(0.0, float(value or 0.0))
                for key, value in actor.cult_affinity.items()
                if key in valid_keys and float(value or 0.0) > 0.0001
            }
            total_affinity = sum(actor.cult_affinity.values())
            if total_affinity > 1.0:
                actor.cult_affinity = {
                    key: value / total_affinity
                    for key, value in actor.cult_affinity.items()
                }

            actor_id = getattr(actor, "id", -1)
            best_key = None
            best_affinity = 0.0
            for key, cult in cult_by_key.items():
                affinity = float(actor.cult_affinity.get(key, 0.0) or 0.0)
                if affinity > 0.15:
                    cult.hidden_affinity_by_actor_id[actor_id] = affinity
                else:
                    getattr(cult, "hidden_affinity_by_actor_id", {}).pop(actor_id, None)
                if affinity > best_affinity:
                    best_key = key
                    best_affinity = affinity

            if best_key is not None and best_affinity > 0.15:
                set_actor_protocult_membership(self, actor, cult_by_key[best_key], affinity=best_affinity)


    def _monster_mythic_profile(self, monster) -> Dict[str, float]:
        if monster is None or getattr(monster, "kind", None) == MonsterKind.GOBLIN:
            return {}
        age_years = max(0.0, float(getattr(monster, "age_ticks", 0) or 0) / float(_G.get("TICKS_PER_YEAR", 1440) or 1080))
        profile = {
            "terror": 0.0,
            "persistence": 0.0,
            "destruction": 0.0,
            "forbidden": 0.0,
        }
        profile["terror"] += int(getattr(monster, "monster_kills_adventurers", 0) or 0) * 6.0
        profile["terror"] += int(getattr(monster, "monster_kills_commoners", 0) or 0) * 0.12
        profile["persistence"] += age_years * 4.0
        profile["persistence"] += int(getattr(monster, "eradication_survivals", 0) or 0) * 90.0
        profile["destruction"] += len(getattr(monster, "terror_region_ids", set()) or set()) * 45.0
        profile["destruction"] += int(getattr(monster, "monster_raids", 0) or 0) * 3.0
        if getattr(monster, "kind", None) == MonsterKind.DRAGON:
            profile["forbidden"] += 160.0
        if getattr(monster, "kind", None) == MonsterKind.ANCIENT_HORROR:
            profile["forbidden"] += 260.0
        if getattr(monster, "kind", None) == MonsterKind.GIANT:
            profile["forbidden"] += 80.0
        return {k: round(max(0.0, v), 2) for k, v in profile.items() if v > 0.0}

    def _monster_cult_weights(self, monster, profile: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
        domains = {}
        traits = {}
        def add(target, key, amount):
            target[key] = float(target.get(key, 0.0)) + float(amount)
        terror = float(profile.get("terror", 0.0))
        persistence = float(profile.get("persistence", 0.0))
        destruction = float(profile.get("destruction", 0.0))
        forbidden = float(profile.get("forbidden", 0.0))
        if terror:
            add(domains, "domination", terror); add(traits, "dread", terror)
        if persistence:
            add(domains, "fate", persistence); add(traits, "undying", persistence)
        if destruction:
            add(domains, "war", destruction); add(traits, "devouring", destruction)
        if forbidden:
            add(domains, "decay", forbidden); add(traits, "forbidden", forbidden)
        return domains, traits

    def _monster_cult_title(self, monster) -> str:
        name = str(getattr(monster, "name", "The Beast") or "The Beast")
        kind = getattr(monster, "kind", None)
        if kind == MonsterKind.DRAGON:
            return f"The Wyrm-God {name}"
        if kind == MonsterKind.ANCIENT_HORROR:
            return f"The God Beneath {name}"
        if kind == MonsterKind.GIANT:
            return f"The Giant-Saint {name}"
        return f"The Living God {name}"

    def _monster_cult_ready(self, monster, pressure: float, profile: Dict[str, float]) -> bool:
        if monster is None or not getattr(monster, "alive", False) or getattr(monster, "kind", None) == MonsterKind.GOBLIN:
            return False
        age_years = max(0.0, float(getattr(monster, "age_ticks", 0) or 0) / float(_G.get("TICKS_PER_YEAR", 1440) or 1080))
        total_kills = int(getattr(monster, "monster_kills_adventurers", 0) or 0) + int(getattr(monster, "monster_kills_commoners", 0) or 0)
        return (
            bool(_G.get("MONSTER_CULT_ENABLED", True))
            and pressure >= float(_G.get("MONSTER_CULT_MIN_PRESSURE", 900.0))
            and self._mythic_legacy_score(profile) >= float(_G.get("MONSTER_CULT_MIN_MYTHIC_LEGACY", 700.0))
            and len(getattr(monster, "terror_region_ids", set()) or set()) >= int(_G.get("MONSTER_CULT_MIN_REGIONS", 3))
            and age_years >= float(_G.get("MONSTER_CULT_MIN_AGE_YEARS", 35))
            and total_kills >= int(_G.get("MONSTER_CULT_MIN_KILLS", 100))
            and int(getattr(monster, "eradication_survivals", 0) or 0) >= int(_G.get("MONSTER_CULT_MIN_ERADICATION_SURVIVALS", 3))
        )

    def _update_proto_cults(self) -> None:
        world = self.world
        # Prime the tick-local songs index so _mythic_legacy_profile_for_actor can use it.
        if not hasattr(world, "_lore_songs_by_subject") or getattr(world, "_lore_songs_index_tick", -1) != world.tick:
            _sbs: Dict[int, List] = {}
            _csba: Dict[int, List] = {}
            for _s in getattr(world, "songs", {}).values():
                if getattr(_s, "forgotten", False):
                    continue
                if str(getattr(_s, "visibility", "public") or "public").lower() != "private" and str(getattr(_s, "song_type", "mythic") or "mythic").lower() == "mythic":
                    for _aid in (getattr(_s, "subject_actor_ids", []) or []):
                        _sbs.setdefault(_aid, []).append(_s)
                _cid = int(getattr(_s, "fame_credit_actor_id", -1) or -1)
                if _cid >= 0 and str(getattr(_s, "song_type", "mythic") or "mythic").lower() != "mythic" and self._song_public_credit_reached(_s):
                    _csba.setdefault(_cid, []).append(_s)
            world._lore_songs_by_subject = _sbs
            world._lore_credited_songs_by_actor = _csba
            # Also build history indexes used by _mythic_legacy_profile_for_actor.
            _ph_by_founder: Dict[int, list] = {}
            for _ph in getattr(world, "party_history", {}).values():
                _fid = getattr(_ph, "founder_id", None)
                if _fid is not None:
                    _ph_by_founder.setdefault(_fid, []).append(_ph)
            world._lore_party_history_by_founder = _ph_by_founder
            _pty_by_leader: Dict[int, object] = {}
            for _pty in getattr(world, "parties", {}).values():
                _lid = getattr(_pty, "leader_id", None)
                if _lid is not None:
                    _pty_by_leader[_lid] = _pty
            world._lore_current_party_by_leader = _pty_by_leader
            _polh_by_actor: Dict[int, list] = {}
            for _polh in getattr(world, "polity_history", {}).values():
                for _attr in ("founder_id", "current_ruler_id"):
                    _aid = getattr(_polh, _attr, None)
                    if _aid is not None:
                        _polh_by_actor.setdefault(_aid, []).append(_polh)
            world._lore_polity_history_by_actor = _polh_by_actor
            world._lore_songs_index_tick = world.tick
        min_pressure = float(_G.get("PROTO_CULT_MIN_LEGEND_PRESSURE", 60.0))
        min_dead_years = int(_G.get("PROTO_CULT_MIN_DEAD_YEARS", 20))
        existing_subjects = {getattr(c, "subject_actor_id", None) for c in getattr(world, "proto_cults", {}).values()}
        current_year = world.current_calendar()[0]
        for actor_id, pressure in list(getattr(world, "legend_pressure_by_actor_id", {}).items()):
            if pressure < min_pressure or actor_id in existing_subjects:
                continue
            actor = self.resolve_actor(actor_id) if hasattr(self, "resolve_actor") else world.actors.get(actor_id)
            if actor is None or getattr(actor, "alive", False):
                continue
            profile = self._mythic_legacy_profile_for_actor(actor)
            legacy_score = self._mythic_legacy_score(profile)
            axis_count = self._mythic_axis_count(profile, float(_G.get("PROTO_CULT_MYTHIC_AXIS_FLOOR", 35.0)))
            setattr(actor, "mythic_legacy_profile", profile)
            setattr(actor, "mythic_legacy_score", legacy_score)
            if legacy_score < float(_G.get("PROTO_CULT_MIN_MYTHIC_LEGACY", 220.0)):
                continue
            if axis_count < int(_G.get("PROTO_CULT_MIN_MYTHIC_AXES", 2)):
                continue
            death_ts = getattr(actor, "death_timestamp", "") or ""
            death_year = None
            try:
                if str(death_ts).startswith("Year "):
                    death_year = int(str(death_ts).split(",", 1)[0].replace("Year", "").strip())
            except Exception:
                death_year = None
            if death_year is not None and current_year - death_year < min_dead_years:
                continue
            cult_id = int(getattr(world, "next_proto_cult_id", 1))
            world.next_proto_cult_id = cult_id + 1
            origin = getattr(actor, "region_id", -1)
            name = f"Cult of {actor.short_name()}"
            domains, traits = self._cult_weights_from_profile(actor, profile)
            public_title = self._title_for_ascended_cult(actor, domains, traits, self._reserved_cult_titles())
            if not public_title:
                # No available archetype remains for this profile. Do not spawn a duplicate cult.
                continue
            domains, traits = self._apply_cult_archetype_weights(public_title, domains, traits)
            cult = ProtoCult(
                id=cult_id,
                name=name,
                subject_actor_id=actor_id,
                subject_name=actor.short_name(),
                origin_region_id=origin,
                legend_pressure=float(pressure),
                mythic_legacy_score=legacy_score,
                mythic_profile=profile,
                domain_weights=domains,
                trait_weights=traits,
                public_title=public_title,
                known_region_ids={origin} if origin in getattr(world, "regions", {}) else set(),
                founded_tick=world.tick,
                last_pressure_tick=world.tick,
            )
            world.proto_cults[cult_id] = cult
            world.log(f"Whispers harden into devotion: {name} takes root among the remembered dead.", importance=4, category="proto_cult")
        # Monster cults are fear/taboo cults around living non-goblin monsters.
        existing_monsters = {getattr(c, "subject_monster_id", None) for c in getattr(world, "proto_cults", {}).values() if getattr(c, "subject_kind", "actor") == "monster"}
        for monster_id, pressure in list(getattr(world, "legend_pressure_by_monster_id", {}).items()):
            if monster_id in existing_monsters:
                continue
            monster = getattr(world, "monsters", {}).get(monster_id)
            if monster is None or not getattr(monster, "alive", False) or getattr(monster, "kind", None) == MonsterKind.GOBLIN:
                continue
            profile = self._monster_mythic_profile(monster)
            if not self._monster_cult_ready(monster, float(pressure), profile):
                continue
            cult_id = int(getattr(world, "next_proto_cult_id", 1))
            world.next_proto_cult_id = cult_id + 1
            origin = getattr(monster, "region_id", -1)
            domains, traits = self._monster_cult_weights(monster, profile)
            public_title = self._monster_cult_title(monster)
            cult = ProtoCult(
                id=cult_id,
                name=f"Cult of {getattr(monster, 'name', 'the Beast')}",
                subject_actor_id=-int(getattr(monster, "id", cult_id)),
                subject_name=str(getattr(monster, "name", "the Beast")),
                subject_kind="monster",
                subject_monster_id=int(getattr(monster, "id", -1)),
                origin_region_id=origin,
                legend_pressure=float(pressure),
                mythic_legacy_score=self._mythic_legacy_score(profile),
                mythic_profile=profile,
                domain_weights=domains,
                trait_weights=traits,
                public_title=public_title,
                known_region_ids=set(getattr(monster, "terror_region_ids", set()) or ({origin} if origin in getattr(world, "regions", {}) else set())),
                founded_tick=world.tick,
                last_pressure_tick=world.tick,
            )
            world.proto_cults[cult_id] = cult
            monster.worshipped_as_living_god = True
            world.log(f"Fear hardens into taboo worship: {public_title} is whispered as a living god.", importance=5, category="proto_cult")

        # Existing cults gather latent affinity from active songs.
        # Build a one-pass index: subject_actor_id/monster_id -> list of relevant songs.
        # This replaces an O(cults * songs) nested scan with a single O(songs) pass.
        songs_by_actor: Dict[int, List] = {}
        songs_by_monster: Dict[int, List] = {}
        for _song in getattr(world, "songs", {}).values():
            if getattr(_song, "forgotten", False):
                continue
            if str(getattr(_song, "visibility", "public") or "public").lower() == "private":
                continue
            for _aid in (getattr(_song, "subject_actor_ids", []) or []):
                songs_by_actor.setdefault(_aid, []).append(_song)
            _mid = getattr(_song, "subject_monster_id", None)
            if _mid is not None:
                songs_by_monster.setdefault(_mid, []).append(_song)

        for cult in getattr(world, "proto_cults", {}).values():
            if getattr(cult, "ascended", False) or getattr(cult, "failed", False):
                continue
            if getattr(cult, "subject_kind", "actor") == "monster":
                current_pressure = float(getattr(world, "legend_pressure_by_monster_id", {}).get(getattr(cult, "subject_monster_id", None), 0.0) or 0.0)
            else:
                current_pressure = float(world.legend_pressure_by_actor_id.get(cult.subject_actor_id, 0.0) or 0.0)
            if current_pressure > 0.0:
                cult.legend_pressure = current_pressure
            else:
                cult.legend_pressure = max(0.0, float(getattr(cult, "legend_pressure", 0.0) or 0.0) * float(_G.get("PROTO_CULT_PRESSURE_MEMORY_DECAY", 0.985)))
            if getattr(cult, "subject_kind", "actor") == "monster":
                monster = getattr(world, "monsters", {}).get(getattr(cult, "subject_monster_id", None))
                if monster is not None:
                    profile = self._monster_mythic_profile(monster)
                    cult.mythic_profile = profile
                    cult.mythic_legacy_score = self._mythic_legacy_score(profile)
                    domains, traits = self._monster_cult_weights(monster, profile)
                    cult.domain_weights = domains
                    cult.trait_weights = traits
            else:
                actor = self.resolve_actor(getattr(cult, "subject_actor_id", None)) if hasattr(self, "resolve_actor") else None
                if actor is not None:
                    profile = self._mythic_legacy_profile_for_actor(actor)
                    cult.mythic_profile = profile
                    cult.mythic_legacy_score = self._mythic_legacy_score(profile)
                    domains, traits = self._cult_weights_from_profile(actor, profile)
                    if not getattr(cult, "public_title", ""):
                        cult.public_title = self._title_for_ascended_cult(actor, domains, traits, self._reserved_cult_titles(exclude_cult_id=getattr(cult, "id", None)))
                    domains, traits = self._apply_cult_archetype_weights(getattr(cult, "public_title", ""), domains, traits)
                    cult.domain_weights = domains
                    cult.trait_weights = traits
            # Use pre-built index instead of scanning all songs per cult.
            if getattr(cult, "subject_kind", "actor") == "monster":
                relevant_songs = songs_by_monster.get(getattr(cult, "subject_monster_id", None), [])
            else:
                relevant_songs = songs_by_actor.get(cult.subject_actor_id, [])
            for song in relevant_songs:
                # Private check already handled by index construction above.
                for rid in getattr(song, "known_region_ids", set()) or set():
                    if rid not in getattr(world, "regions", {}):
                        continue
                    cult.known_region_ids.add(rid)
                    commoners = int(getattr(world, "commoners_by_region", {}).get(rid, 0) or 0)
                    rate_cap = float(_G.get("MONSTER_CULT_COMMONER_FEAR_RATE", 0.015)) if getattr(cult, "subject_kind", "actor") == "monster" else 0.02
                    add = int(max(0, min(commoners * rate_cap, song.popularity * 0.10)))
                    if add > 0:
                        cult.hidden_commoner_affinity_by_region[rid] = int(cult.hidden_commoner_affinity_by_region.get(rid, 0)) + add

    def _maybe_ascend_proto_cult(self) -> None:
        world = self.world
        cadence = int(_G.get("DEIFICATION_CHECK_INTERVAL_TICKS", _G.get("TICKS_PER_YEAR", 1440)))
        if world.tick - int(getattr(world, "last_deification_check_tick", -999999)) < cadence:
            return
        world.last_deification_check_tick = world.tick
        if not bool(_G.get("DEIFICATION_ENABLED", True)):
            return
        threshold = float(_G.get("DEIFICATION_LEGEND_PRESSURE_THRESHOLD", 700.0))
        region_min = int(_G.get("DEIFICATION_MIN_REGIONS", 2))
        candidates = [c for c in getattr(world, "proto_cults", {}).values() if not c.ascended and not c.failed and c.legend_pressure >= threshold and len(c.known_region_ids) >= region_min]
        if not candidates:
            return
        cult = max(candidates, key=lambda c: (c.legend_pressure, len(c.known_region_ids), self.rng.random()))
        chance = min(0.85, float(_G.get("DEIFICATION_BASE_CHANCE", 0.12)) + cult.legend_pressure / 5000.0 + len(cult.known_region_ids) * 0.03)
        if self.rng.random() < chance:
            self._ascend_proto_cult(cult)


    def _open_worship_actor_weight(self, actor, cult: ProtoCult) -> Tuple[float, str]:
        """Return influence weight and human-readable reason for a possible open-worship catalyst.

        This does not convert anyone and does not create a god. It only identifies
        actors with enough public standing to make an underground/ascended cult
        visible in the world.
        """
        if actor is None or not getattr(actor, "alive", False) or getattr(actor, "in_school", False):
            return 0.0, ""
        reasons: List[str] = []
        weight = 0.0
        aid = getattr(actor, "id", None)
        # Chosen servants are hard to sway, but if they do break, it matters.
        if getattr(actor, "champion_of", None) is not None:
            weight = max(weight, 2.50)
            reasons.append("champion")

        # Rulers and ruler-spouses can legitimize a cult at court.
        for pol in getattr(self.world, "polities", {}).values():
            rid = getattr(pol, "ruler_id", None)
            if aid == rid:
                weight = max(weight, 2.40)
                reasons.append(f"ruler of {getattr(pol, 'name', 'a polity')}")
            else:
                ruler = self.resolve_actor(rid) if hasattr(self, "resolve_actor") else None
                if ruler is not None and getattr(ruler, "spouse_id", None) == aid:
                    weight = max(weight, 2.00)
                    reasons.append(f"spouse of {getattr(ruler, 'short_name', lambda: 'a ruler')()}")
            if aid in (getattr(pol, "general_ids", []) or []) or aid == getattr(pol, "general_id", None):
                weight = max(weight, 1.75)
                reasons.append("general")
            if aid in (getattr(pol, "captain_ids", []) or []):
                weight = max(weight, 1.45)
                reasons.append("captain")

        # Large party leaders can move public opinion without formal office.
        pid = getattr(actor, "party_id", None)
        party = getattr(self.world, "parties", {}).get(pid) if pid is not None else None
        if party is not None and getattr(party, "leader_id", None) == aid:
            size = len(getattr(party, "member_ids", []) or [])
            party_weight = 1.25 + min(0.50, size / 120.0)
            weight = max(weight, party_weight)
            reasons.append(f"leader of {getattr(party, 'name', 'a party')}")

        # Famous bards are specifically allowed to make bardic cults public.
        if getattr(actor, "role", None) == Role.BARD and int(getattr(actor, "reputation", 0) or 0) >= int(_G.get("OPEN_WORSHIP_FAMOUS_BARD_REP", 60)):
            weight = max(weight, 1.35)
            reasons.append("famous bard")

        # Very famous non-bards can still matter, but this is intentionally weaker.
        if int(getattr(actor, "reputation", 0) or 0) >= int(_G.get("OPEN_WORSHIP_FAMOUS_ACTOR_REP", 90)):
            weight = max(weight, 1.20)
            reasons.append("renowned adventurer")

        if weight <= 0.0:
            return 0.0, ""
        # Avoid duplicate reason spam while preserving order.
        clean: List[str] = []
        seen: Set[str] = set()
        for reason in reasons:
            if reason not in seen:
                seen.add(reason)
                clean.append(reason)
        return weight, ", ".join(clean) if clean else "influential adherent"

    def _maybe_open_worship(self) -> None:
        """Let an ascended cult become public through an influential living believer.

        This is the diegetic bridge stage only:
            ascended cult -> open worship

        It intentionally does NOT formalize the cult as a new god, does NOT add it
        to world.gods, and does NOT begin follower siphoning.
        """
        world = getattr(self, "world", None)
        if world is None:
            return
        if not bool(_G.get("OPEN_WORSHIP_ENABLED", True)):
            return
        cadence = int(_G.get("OPEN_WORSHIP_CHECK_INTERVAL_TICKS", _G.get("TICKS_PER_YEAR", 1440)))
        if world.tick - int(getattr(world, "last_open_worship_check_tick", -999999)) < cadence:
            return
        world.last_open_worship_check_tick = world.tick

        min_affinity = float(_G.get("OPEN_WORSHIP_MIN_AFFINITY", 0.85))
        min_doubt = float(_G.get("OPEN_WORSHIP_MIN_DOUBT", 0.25))
        min_regions = int(_G.get("OPEN_WORSHIP_MIN_REGIONS", 2))
        min_pressure = float(_G.get("OPEN_WORSHIP_MIN_LEGEND_PRESSURE", 2500.0))
        min_mythic = float(_G.get("OPEN_WORSHIP_MIN_MYTHIC_LEGACY", 350.0))
        base_chance = float(_G.get("OPEN_WORSHIP_BASE_CHANCE", 0.06))
        max_chance = float(_G.get("OPEN_WORSHIP_MAX_CHANCE", 0.35))

        candidates = [
            c for c in getattr(world, "proto_cults", {}).values()
            if getattr(c, "ascended", False)
            and not getattr(c, "open_worship", False)
            and not getattr(c, "formalized", False)
            and not getattr(c, "failed", False)
            and len(getattr(c, "known_region_ids", set()) or set()) >= min_regions
            and float(getattr(c, "legend_pressure", 0.0) or 0.0) >= min_pressure
            and float(getattr(c, "mythic_legacy_score", 0.0) or 0.0) >= min_mythic
            and bool(getattr(c, "public_title", "") or "")
        ]
        if not candidates:
            return

        # Build per-cult candidate lists in one O(actors) pass instead of O(cults * actors).
        cult_keys = {str(getattr(c, "id", "")): c for c in candidates}
        best_by_cult: Dict[str, tuple] = {}  # key -> (score, actor, reason)
        for actor in world.living_actors():
            if getattr(actor, "role", None) == Role.COMMONER or getattr(actor, "in_school", False):
                continue
            doubt = float(getattr(actor, "faith_doubt", 0.0) or 0.0)
            if doubt < min_doubt:
                continue
            aff_map = getattr(actor, "cult_affinity", {}) or {}
            if not isinstance(aff_map, dict):
                continue
            for key, cult in cult_keys.items():
                affinity = float(aff_map.get(key, 0.0) or 0.0)
                if affinity < min_affinity:
                    continue
                weight, reason = self._open_worship_actor_weight(actor, cult)
                if weight <= 0.0:
                    continue
                score = affinity * (0.50 + doubt) * weight
                prev = best_by_cult.get(key)
                if prev is None or score > prev[0]:
                    best_by_cult[key] = (score, actor, reason)

        for cult in sorted(candidates, key=lambda c: float(getattr(c, "legend_pressure", 0.0) or 0.0), reverse=True):
            key = str(getattr(cult, "id", ""))
            best = best_by_cult.get(key)
            best_actor = best[1] if best else None
            best_reason = best[2] if best else ""
            best_score = best[0] if best else 0.0

            if best_actor is None:
                continue

            pressure_bonus = min(0.10, float(getattr(cult, "legend_pressure", 0.0) or 0.0) / 250000.0)
            region_bonus = min(0.08, len(getattr(cult, "known_region_ids", set()) or set()) * 0.015)
            score_bonus = min(0.12, best_score * 0.05)
            chance = min(max_chance, base_chance + pressure_bonus + region_bonus + score_bonus)
            if self.rng.random() >= chance:
                continue

            cult.open_worship = True
            cult.open_worship_tick = getattr(world, "tick", -1)
            cult.open_worship_actor_id = getattr(best_actor, "id", None)
            cult.open_worship_actor_name = best_actor.short_name() if hasattr(best_actor, "short_name") else getattr(best_actor, "name", "Unknown")
            cult.open_worship_reason = best_reason or "influential adherent"
            title = getattr(cult, "public_title", "") or getattr(cult, "name", "the remembered dead")
            world.log(
                f"Open worship begins: {cult.open_worship_actor_name}, {cult.open_worship_reason}, publicly honors {title}. "
                f"{getattr(cult, 'name', 'A hidden cult')} steps from whispers into the open.",
                importance=5,
                category="proto_cult",
            )
            return

    def _domains_for_ascended_actor(self, actor, cult: Optional[ProtoCult] = None) -> List[str]:
        weights = getattr(cult, "domain_weights", {}) if cult is not None else {}
        if not weights and actor is not None:
            profile = self._mythic_legacy_profile_for_actor(actor)
            weights, _traits = self._cult_weights_from_profile(actor, profile)
        ranked = [k for k, _v in sorted((weights or {}).items(), key=lambda item: float(item[1]), reverse=True)]
        return (ranked or ["memory"])[:3]

    def _ascend_proto_cult(self, cult: ProtoCult) -> bool:
        """Mark a proto-cult as an ascended memory, not a public god.

        This intentionally does NOT append the cult object to world.gods, does
        NOT create public schools, does NOT spawn champions, and does NOT move
        commoner faith into the overt immortal-influence table. The cult remains
        underground until a later explicit full-deity registration mechanic.
        """
        world = self.world
        actor = self.resolve_actor(cult.subject_actor_id) if hasattr(self, "resolve_actor") else None
        if actor is None:
            return False
        reserved_titles = self._reserved_cult_titles(exclude_cult_id=getattr(cult, "id", None))
        if getattr(cult, "public_title", "") and self._normalized_cult_title(cult.public_title) in reserved_titles:
            profile_for_title = self._mythic_legacy_profile_for_actor(actor)
            domains_for_title, traits_for_title = self._cult_weights_from_profile(actor, profile_for_title)
            cult.public_title = self._title_for_ascended_cult(actor, domains_for_title, traits_for_title, reserved_titles)
            domains_for_title, traits_for_title = self._apply_cult_archetype_weights(getattr(cult, "public_title", ""), domains_for_title, traits_for_title)
            cult.domain_weights = domains_for_title
            cult.trait_weights = traits_for_title
            if not cult.public_title:
                cult.failed = True
                world.log(f"{cult.name} fails to rise because its divine title has already been claimed.", importance=3, category="proto_cult")
                return False
        mortal_name = cult.subject_name
        name = getattr(cult, "public_title", "") or mortal_name
        if not getattr(cult, "public_title", ""):
            profile_for_title = self._mythic_legacy_profile_for_actor(actor)
            domains_for_title, traits_for_title = self._cult_weights_from_profile(actor, profile_for_title)
            cult.public_title = self._title_for_ascended_cult(actor, domains_for_title, traits_for_title, self._reserved_cult_titles(exclude_cult_id=getattr(cult, "id", None)))
            domains_for_title, traits_for_title = self._apply_cult_archetype_weights(getattr(cult, "public_title", ""), domains_for_title, traits_for_title)
            cult.domain_weights = domains_for_title
            cult.trait_weights = traits_for_title
            if not cult.public_title:
                cult.failed = True
                world.log(f"{cult.name} fails to rise because no distinct divine title remains for its memory.", importance=3, category="proto_cult")
                return False
            name = cult.public_title
        profile = GodProfile(
            name=name,
            alignment=getattr(getattr(actor, "alignment", None), "value", "True Neutral"),
            favored_classes=[getattr(getattr(actor, "role", None), "value", "Fighter")],
            favored_traits=list(getattr(actor, "traits", []) or [])[:2],
            domains=self._domains_for_ascended_actor(actor, cult),
            conversion_bias=1.05,
            order_modifier=0.0,
            volatility_modifier=0.05,
            description=f"An ascended hero-cult born from songs remembering {mortal_name}; worshiped as {name}.",
            is_player=False,
            color="white",
            starting_souls=0,
            source_path="emergent_lore",
            profile_id=f"ascended_{cult.subject_actor_id}",
            active_for_run=False,
        )
        cult.deity_object = profile
        cult.ascended = True

        # Preserve underground / latent affinity only. This is social memory, not
        # public immortal infrastructure.
        latent_commoners = sum(max(0, int(v)) for v in getattr(cult, "hidden_commoner_affinity_by_region", {}).values())
        latent_actors = 0
        for living in world.living_actors():
            if getattr(living, "region_id", None) in cult.known_region_ids:
                latent_actors += 1
            elif getattr(living, "mother_id", None) == cult.subject_actor_id or getattr(living, "father_id", None) == cult.subject_actor_id:
                latent_actors += 1
            elif getattr(living, "best_friend_id", None) == cult.subject_actor_id or getattr(living, "spouse_id", None) == cult.subject_actor_id:
                latent_actors += 1

        # Defensive cleanup for earlier scaffold runs that accidentally leaked
        # ascended memories into god/school infrastructure.
        if hasattr(self, "_purge_nonformal_school_state"):
            self._purge_nonformal_school_state()
        world.log(
            f"{mortal_name} is lifted from song into a hidden ascended memory as {name}. "
            f"Its cult remains underground ({latent_commoners} latent commoners, {latent_actors} nearby sympathizers).",
            importance=5,
            category="deification",
        )
        return True
