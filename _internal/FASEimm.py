# Expanded pantheon profiles and .imrt loading for Immortal Champions / Fantasy Antfarm.
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Any
import configparser
from FASEcfg import *
from FASEclass import *

VALID_DOMAINS = [
    "order", "chaos", "war", "domination", "trickery", "growth",
    "decay", "fate", "protection", "knowledge",
]

VALID_ALIGNMENTS = [
    "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "True Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil",
]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def infer_immortal_modifiers(alignment: str = "True Neutral", domains: Optional[Iterable[str]] = None) -> tuple[float, float]:
    """Infer canonical order/volatility modifiers from alignment + domains.

    This is the shared rule used by both the generator and start-game flow so
    custom gods do not accidentally become mechanically bland or contradictory
    to their stated identity. Explicit defaults are intentionally in the same
    rough range as the hardcoded Light/Darkness/Chance profiles.
    """
    alignment_key = str(alignment or "True Neutral").strip().lower()
    alignment_defaults = {
        "lawful good": (0.35, -0.15),
        "neutral good": (0.20, 0.00),
        "chaotic good": (0.05, 0.20),
        "lawful neutral": (0.20, -0.05),
        "true neutral": (0.00, 0.00),
        "chaotic neutral": (-0.05, 0.30),
        "lawful evil": (-0.25, -0.05),
        "neutral evil": (-0.35, 0.10),
        "chaotic evil": (-0.40, 0.30),
    }
    order, volatility = alignment_defaults.get(alignment_key, (0.0, 0.0))

    domain_adjustments = {
        "order": (0.20, -0.10),
        "protection": (0.15, -0.05),
        "growth": (0.10, -0.05),
        "knowledge": (0.05, -0.05),
        "chaos": (-0.15, 0.25),
        "trickery": (-0.05, 0.25),
        "fate": (0.00, 0.20),
        "war": (-0.05, 0.15),
        "domination": (-0.20, 0.05),
        "decay": (-0.20, 0.10),
    }
    for domain in domains or []:
        d_order, d_volatility = domain_adjustments.get(str(domain).strip().lower(), (0.0, 0.0))
        order += d_order
        volatility += d_volatility

    return (_clamp(order, -0.60, 0.60), _clamp(volatility, -0.25, 0.75))




@dataclass
class DivineBoon:
    id: int
    source_god: object
    target_actor_id: int
    boon_type: str
    stat: str
    amount: int
    started_tick: int
    expires_tick: int
    label: str = ""

    def is_active(self, tick: int) -> bool:
        return tick < self.expires_tick

@dataclass
class GodState:
    deity: object
    name: str
    profile: object = None
    is_player_god: bool = False
    color: str = ""
    souls: int = 0
    followers: int = 0
    champions: list = field(default_factory=list)
    relics: list = field(default_factory=list)
    regional_influence: dict = field(default_factory=dict)
    influence: int = 0
    influence_share: float = 0.0


@dataclass
class GodProfile:
    name: str
    alignment: str = "True Neutral"
    favored_classes: List[str] = field(default_factory=list)
    favored_traits: List[str] = field(default_factory=list)
    disfavored_traits: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    conversion_bias: float = 1.0
    order_modifier: float = 0.0
    volatility_modifier: float = 0.0
    description: str = ""
    is_player: bool = False
    color: Optional[str] = None
    starting_souls: int = 0
    source_path: str = ""
    profile_id: str = ""
    active_for_run: bool = False

    @property
    def value(self) -> str:
        # Existing sim code expects deity-like objects to expose .value.
        return self.name

    def __hash__(self) -> int:
        return hash(self.name.lower())

    def __eq__(self, other) -> bool:
        return getattr(other, "value", getattr(other, "name", str(other))).lower() == self.name.lower()


def _split_csv(raw: str) -> List[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def _canonical_color(raw: Optional[str], *, is_player: bool = False) -> Optional[str]:
    value = str(raw or "").strip().lower()
    aliases = {"purple": "magenta", "pink": "magenta", "grey": "white", "none": "", "default": ""}
    value = aliases.get(value, value)
    allowed = {"", "white", "blue", "magenta", "yellow", "red", "green"}
    if value not in allowed:
        value = ""
    if is_player:
        return "magenta"
    return value or None


def _get_first(parser: configparser.ConfigParser, options: list[tuple[str, str]], fallback: str = "") -> str:
    for section, key in options:
        if parser.has_option(section, key):
            return parser.get(section, key, fallback=fallback)
    return fallback


def _get_first_float(parser: configparser.ConfigParser, options: list[tuple[str, str]], fallback: float = 0.0) -> float:
    for section, key in options:
        if parser.has_option(section, key):
            return parser.getfloat(section, key, fallback=fallback)
    return fallback


def _get_first_int(parser: configparser.ConfigParser, options: list[tuple[str, str]], fallback: int = 0) -> int:
    for section, key in options:
        if parser.has_option(section, key):
            return parser.getint(section, key, fallback=fallback)
    return fallback


def _get_first_bool(parser: configparser.ConfigParser, options: list[tuple[str, str]], fallback: bool = False) -> bool:
    for section, key in options:
        if parser.has_option(section, key):
            return parser.getboolean(section, key, fallback=fallback)
    return fallback


def default_god_profiles(deity_enum) -> Dict[object, GodProfile]:
    """Return profiles keyed by the existing Deity enum values."""
    return {
        deity_enum.LORD_OF_LIGHT: GodProfile(
            name=deity_enum.LORD_OF_LIGHT.value,
            alignment="Lawful Good",
            favored_classes=["Fighter", "Warden"],
            favored_traits=["just", "honorable", "brave"],
            disfavored_traits=["cruel", "ruthless"],
            domains=["order", "protection"],
            conversion_bias=1.0,
            order_modifier=0.50,
            volatility_modifier=-0.20,
            description="A god of order, justice, mercy, and protection. Their name is unknowable.",
            color="yellow",
        ),
        deity_enum.LORD_OF_DARKNESS: GodProfile(
            name=deity_enum.LORD_OF_DARKNESS.value,
            alignment="Chaotic Evil",
            favored_classes=["Fighter", "Wizard"],
            favored_traits=["cruel", "ambitious", "ruthless"],
            disfavored_traits=["just", "merciful"],
            domains=["domination", "decay"],
            conversion_bias=1.20,
            order_modifier=-0.50,
            volatility_modifier=0.20,
            description="A god of domination, fear, hunger, and collapse. Its name must not be uttered.",
            color="red",
        ),
        deity_enum.GOD_OF_CHANCE: GodProfile(
            name=deity_enum.GOD_OF_CHANCE.value,
            alignment="True Neutral",
            favored_classes=["Bard", "Wizard"],
            favored_traits=["impulsive", "curious", "eccentric"],
            disfavored_traits=["disciplined"],
            domains=["chaos", "fate"],
            conversion_bias=0.80,
            order_modifier=0.0,
            volatility_modifier=0.60,
            description="A god of fortune, accident, fate, and unstable possibility. It is all a game to them.",
            color="green",
        ),
    }


def load_imrt_file(path: str | Path) -> Optional[GodProfile]:
    path = Path(path)
    if not path.exists() or path.suffix.lower() != ".imrt":
        return None

    parser = configparser.ConfigParser()
    parser.optionxform = str.lower
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return None

    name = parser.get("identity", "name", fallback=path.stem).strip() or path.stem
    profile_id = parser.get("identity", "id", fallback="").strip()

    alignment = _get_first(parser, [("identity", "alignment"), ("alignment", "type")], "True Neutral").strip()
    if alignment not in VALID_ALIGNMENTS:
        alignment = "True Neutral"

    domain_text = _get_first(parser, [("identity", "domain"), ("domains", "tags"), ("domains", "primary")], "")
    domains = [d for d in _split_csv(domain_text.lower()) if d in VALID_DOMAINS]

    description = _get_first(parser, [("description", "text"), ("identity", "description")], "").strip()
    is_player = _get_first_bool(parser, [("identity", "is_player_god"), ("identity", "is_player")], False)
    active_for_run = _get_first_bool(parser, [("identity", "active_for_run"), ("run", "active")], False)
    color = _canonical_color(_get_first(parser, [("identity", "color"), ("visual", "color")], ""), is_player=is_player)

    return GodProfile(
        name=name,
        alignment=alignment,
        favored_classes=_split_csv(_get_first(parser, [("champion_rules", "favored_classes"), ("classes", "favored")], "")),
        favored_traits=_split_csv(_get_first(parser, [("traits", "favored"), ("champion_rules", "favored_traits")], "")),
        disfavored_traits=_split_csv(_get_first(parser, [("traits", "disfavored"), ("champion_rules", "disfavored_traits")], "")),
        domains=domains,
        conversion_bias=_get_first_float(parser, [("modifiers", "conversion_bias"), ("power", "conversion_bias")], 1.0),
        order_modifier=_get_first_float(parser, [("modifiers", "order_modifier"), ("power", "order_modifier")], 0.0),
        volatility_modifier=_get_first_float(parser, [("modifiers", "volatility_modifier"), ("power", "volatility_modifier")], 0.0),
        description=description,
        is_player=is_player,
        color=color,
        starting_souls=_get_first_int(parser, [("economy", "starting_souls"), ("power", "starting_souls")], 0),
        source_path=str(path),
        profile_id=profile_id,
        active_for_run=active_for_run,
    )


def load_imrt_directory(directory: str | Path) -> List[GodProfile]:
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        return []

    gods: List[GodProfile] = []
    seen = set()
    for path in sorted(directory.glob("*.imrt")):
        god = load_imrt_file(path)
        if god is None:
            continue
        key = god.name.lower()
        if key in seen:
            continue
        seen.add(key)
        gods.append(god)
    return gods


def build_pantheon(deity_enum, imrt_dirs: Iterable[str | Path]) -> tuple[list[object], dict[object, GodProfile]]:
    profiles: Dict[object, GodProfile] = default_god_profiles(deity_enum)
    pantheon: List[object] = list(profiles.keys())
    known_names = {profile.name.lower() for profile in profiles.values()}
    player_claimed = False

    for directory in imrt_dirs:
        for god in load_imrt_directory(directory):
            if not getattr(god, "active_for_run", False):
                continue
            if god.name.lower() in known_names:
                continue
            if god.is_player:
                if player_claimed:
                    # Only one custom immortal can be player-controlled at world load.
                    # Extra .imrt files still load as ordinary custom immortals.
                    god.is_player = False
                    god.color = _canonical_color(god.color, is_player=False)
                else:
                    player_claimed = True
                    god.color = "magenta"
            pantheon.append(god)
            profiles[god] = god
            known_names.add(god.name.lower())

    return pantheon, profiles


def deity_value(deity) -> str:
    return getattr(deity, "value", getattr(deity, "name", str(deity)))





# ---------------------------------------------------------------------------
# Worship and proto-cult membership helpers
# ---------------------------------------------------------------------------
# Overt religion is mutable. Proto-cult membership is also mutable, but singular:
# one actor may openly worship one formal god and may secretly belong to at most
# one proto-cult. Cult affinity remains a pressure/history map, not membership.


def _world_tick_from_owner(owner) -> int:
    world = getattr(owner, "world", owner)
    try:
        return int(getattr(world, "tick", 0) or 0)
    except Exception:
        return 0


def ensure_actor_religion_tracking(owner, actor) -> None:
    """Backfill worship-duration fields for old saves/newly created actors."""
    if actor is None:
        return
    tick = _world_tick_from_owner(owner)
    if not hasattr(actor, "deity_since_tick") or int(getattr(actor, "deity_since_tick", -1) or -1) < 0:
        actor.deity_since_tick = tick
    if not hasattr(actor, "current_protocult_id"):
        actor.current_protocult_id = None
    if not hasattr(actor, "protocult_since_tick"):
        actor.protocult_since_tick = -1


def change_actor_deity(owner, actor, deity, *, conviction: Optional[int] = None, locked: Optional[bool] = None) -> bool:
    """Set an actor's overt god and update duration bookkeeping only on real conversion."""
    if actor is None or deity is None:
        return False
    ensure_actor_religion_tracking(owner, actor)
    changed = getattr(actor, "deity", None) != deity
    if changed:
        actor.deity = deity
        actor.deity_since_tick = _world_tick_from_owner(owner)
    else:
        actor.deity = deity
    if conviction is not None:
        actor.deity_conviction = int(conviction)
    if locked is not None:
        actor.locked_deity = bool(locked)
    return changed


def _proto_cult_is_valid(cult) -> bool:
    if cult is None:
        return False
    if bool(getattr(cult, "failed", False)):
        return False
    # Once a cult has become a formal god/religion, it is no longer a proto-cult.
    if bool(getattr(cult, "formalized", False)) or bool(getattr(cult, "ascended", False)):
        return False
    return True


def actor_current_protocult(world, actor):
    if actor is None:
        return None
    ensure_actor_religion_tracking(world, actor)
    cid = getattr(actor, "current_protocult_id", None)
    if cid is None:
        return None
    cults = getattr(world, "proto_cults", {}) or {}
    cult = cults.get(cid)
    if cult is None:
        try:
            cult = cults.get(int(cid))
        except Exception:
            cult = None
    if _proto_cult_is_valid(cult):
        return cult
    actor.current_protocult_id = None
    actor.protocult_since_tick = -1
    return None


def set_actor_protocult_membership(owner, actor, cult, *, affinity: float = 0.0, force: bool = False) -> bool:
    """Assign/switch one secret proto-cult membership without touching overt religion.

    cult_affinity remains a many-cult pressure map. This field is the actual
    current secret worship state. Switching is allowed, but the challenger must
    beat the current cult by a configurable margin unless forced.
    """
    world = getattr(owner, "world", owner)
    if actor is None:
        return False
    ensure_actor_religion_tracking(world, actor)
    if not _proto_cult_is_valid(cult):
        current = actor_current_protocult(world, actor)
        if current is not None and getattr(current, "id", None) == getattr(cult, "id", None):
            actor.current_protocult_id = None
            actor.protocult_since_tick = -1
            return True
        return False

    try:
        affinity = float(affinity or 0.0)
    except Exception:
        affinity = 0.0
    min_affinity = float(globals().get("PROTOCULT_MEMBERSHIP_MIN_AFFINITY", 0.15))
    switch_margin = float(globals().get("PROTOCULT_MEMBERSHIP_SWITCH_MARGIN", 0.12))
    retention_floor = float(globals().get("PROTOCULT_MEMBERSHIP_RETENTION_FLOOR", 0.04))

    cid = int(getattr(cult, "id"))
    current = actor_current_protocult(world, actor)
    current_id = getattr(current, "id", None) if current is not None else None
    if current_id == cid:
        return False

    aff_map = getattr(actor, "cult_affinity", {}) or {}
    if not isinstance(aff_map, dict):
        aff_map = {}
        actor.cult_affinity = aff_map
    current_aff = 0.0
    if current_id is not None:
        raw = aff_map.get(current_id, aff_map.get(str(current_id), 0.0))
        try:
            current_aff = float(raw or 0.0)
        except Exception:
            current_aff = 0.0

    if force or current is None:
        if force or affinity >= min_affinity:
            actor.current_protocult_id = cid
            actor.protocult_since_tick = _world_tick_from_owner(world)
            return True
        return False

    if current_aff < retention_floor or affinity >= current_aff + switch_margin:
        actor.current_protocult_id = cid
        actor.protocult_since_tick = _world_tick_from_owner(world)
        return True
    return False


def clear_actor_protocult_membership(owner, actor, cult_id: Optional[int] = None) -> bool:
    if actor is None:
        return False
    ensure_actor_religion_tracking(owner, actor)
    current = getattr(actor, "current_protocult_id", None)
    if current is None:
        return False
    if cult_id is not None and current != cult_id and str(current) != str(cult_id):
        return False
    actor.current_protocult_id = None
    actor.protocult_since_tick = -1
    return True


def worship_duration_years(owner, actor) -> float:
    if actor is None:
        return 0.0
    ensure_actor_religion_tracking(owner, actor)
    tick = _world_tick_from_owner(owner)
    start = int(getattr(actor, "deity_since_tick", tick) or tick)
    return max(0.0, (tick - start) / float(globals().get("TICKS_PER_YEAR", 1080) or 1080))


def protocult_duration_years(owner, actor) -> float:
    if actor is None:
        return 0.0
    ensure_actor_religion_tracking(owner, actor)
    start = int(getattr(actor, "protocult_since_tick", -1) or -1)
    if start < 0:
        return 0.0
    tick = _world_tick_from_owner(owner)
    return max(0.0, (tick - start) / float(globals().get("TICKS_PER_YEAR", 1080) or 1080))


class ImmortalAIMixin:
    """Conservative autonomous immortal actions for non-player and emergent gods."""


    # -----------------------------------------------------------------------
    # Apotheosis / emergent pantheon elevation
    # -----------------------------------------------------------------------

    def _apotheosis_cult_members(self, cult):
        cid = getattr(cult, "id", None)
        out = []
        if cid is None:
            return out
        cid_str = str(cid)
        for actor in self.world.living_actors():
            if getattr(actor, "in_school", False):
                continue
            proto = getattr(actor, "current_protocult_id", None)
            if proto == cid or str(proto) == cid_str:
                out.append(actor)
        return out

    def _apotheosis_cult_affinity_mass(self, cult) -> float:
        cid = getattr(cult, "id", None)
        total = 0.0
        if cid is None:
            return 0.0
        cid_str = str(cid)
        for actor in self.world.living_actors():
            aff = getattr(actor, "cult_affinity", {}) or {}
            if not isinstance(aff, dict):
                continue
            raw = aff.get(cid, aff.get(cid_str, 0.0))
            try:
                total += max(0.0, float(raw or 0.0))
            except Exception:
                pass
        return total

    def _apotheosis_cult_members_and_affinity(self, cult):
        """Return (members_list, affinity_mass) in a single pass over living actors."""
        cid = getattr(cult, "id", None)
        if cid is None:
            return [], 0.0
        cid_str = str(cid)
        members = []
        total_affinity = 0.0
        for actor in self.world.living_actors():
            if getattr(actor, "in_school", False):
                continue
            proto = getattr(actor, "current_protocult_id", None)
            is_member = (proto == cid or str(proto) == cid_str)
            if is_member:
                members.append(actor)
            aff = getattr(actor, "cult_affinity", {}) or {}
            if isinstance(aff, dict):
                raw = aff.get(cid, aff.get(cid_str, 0.0))
                try:
                    total_affinity += max(0.0, float(raw or 0.0))
                except Exception:
                    pass
        return members, total_affinity

    def _apotheosis_polity_strength(self, polity) -> float:
        if polity is None:
            return 0.0
        strength = float(getattr(polity, "strength", 0) or 0)
        peak = float(getattr(polity, "peak_strength", 0) or 0)
        regions = len(getattr(polity, "region_ids", []) or [])
        stability = float(getattr(polity, "stability", 0) or 0)
        legitimacy = float(getattr(polity, "legitimacy", 0) or 0)
        return max(strength, peak, regions * 1000.0 + stability * 10.0 + legitimacy * 10.0)

    def _apotheosis_actor_roles(self, actor):
        roles = []
        polities = []
        aid = getattr(actor, "id", None)
        if aid is None:
            return roles, polities
        for polity in getattr(self.world, "polities", {}).values():
            rid = getattr(polity, "ruler_id", None)
            if aid == rid:
                roles.append("ruler")
                polities.append(polity)
            else:
                ruler = self.world.actors.get(rid)
                if ruler is not None and getattr(ruler, "spouse_id", None) == aid:
                    roles.append("ruler-spouse")
                    polities.append(polity)
            if aid in (getattr(polity, "general_ids", []) or []) or aid == getattr(polity, "general_id", None):
                roles.append("general")
                polities.append(polity)
            if aid in (getattr(polity, "captain_ids", []) or []):
                roles.append("captain")
                polities.append(polity)
        clean_roles = []
        seen = set()
        for role in roles:
            if role not in seen:
                seen.add(role)
                clean_roles.append(role)
        clean_polities = []
        seenp = set()
        for polity in polities:
            pid = getattr(polity, "id", id(polity))
            if pid not in seenp:
                seenp.add(pid)
                clean_polities.append(polity)
        return clean_roles, clean_polities

    def _apotheosis_party_leadership(self, actor):
        aid = getattr(actor, "id", None)
        if aid is None:
            return None, 0
        for party in getattr(self.world, "parties", {}).values():
            if getattr(party, "leader_id", None) == aid:
                return party, len(getattr(party, "member_ids", []) or [])
        return None, 0

    def _apotheosis_actor_clout(self, actor, cult=None):
        """Runtime-only score for who can openly break with a god and make a new one."""
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

        roles, polities = self._apotheosis_actor_roles(actor)
        if "ruler" in roles:
            add("ruler", 80)
        if "ruler-spouse" in roles:
            add("ruler-spouse", 50)
        if "general" in roles:
            add("general", 35)
        if "captain" in roles:
            add("captain", 25)

        if getattr(actor, "champion_of", None) is not None:
            add("champion", 65)

        party, party_size = self._apotheosis_party_leadership(actor)
        if party is not None:
            add("party-leader", 25)
            add("party-size", min(35, party_size * 0.5))

        if getattr(actor, "relic_id", None) is not None:
            add("relic-bearer", 45)

        add("reputation", min(80, float(getattr(actor, "reputation", 0) or 0) * 0.8))
        add("level", min(30, float(getattr(actor, "level", 1) or 1) * 3.0))
        add("xp", min(25, float(getattr(actor, "experience", 0) or 0) / 250.0))
        add("monster-kills", min(30, float(getattr(actor, "monster_kills", 0) or 0) * 1.5))
        add("dragon-kills", float(getattr(actor, "dragon_kills", 0) or 0) * 30.0)
        add("horror-kills", float(getattr(actor, "horror_kills", 0) or 0) * 45.0)

        if polities:
            strongest = max(polities, key=self._apotheosis_polity_strength)
            strength = self._apotheosis_polity_strength(strongest)
            stability = float(getattr(strongest, "stability", 0) or 0)
            legitimacy = float(getattr(strongest, "legitimacy", 0) or 0)
            regions = len(getattr(strongest, "region_ids", []) or [])
            institutional = min(45.0, strength / 400.0) + min(20.0, stability / 5.0) + min(20.0, legitimacy / 5.0) + min(15.0, regions * 5.0)
            if "ruler" in roles or "ruler-spouse" in roles:
                add("state-backing", institutional)
            else:
                add("state-modifier", institutional * 0.45)

        if cult is not None and polities:
            cid = getattr(cult, "id", None)
            for polity in polities:
                ruler = self.world.actors.get(getattr(polity, "ruler_id", None))
                if ruler is None:
                    continue
                spouse = self.world.actors.get(getattr(ruler, "spouse_id", None)) if getattr(ruler, "spouse_id", None) is not None else None
                if spouse is None or actor not in (ruler, spouse):
                    continue
                both = True
                for member in (ruler, spouse):
                    aff = getattr(member, "cult_affinity", {}) or {}
                    raw = aff.get(cid, aff.get(str(cid), 0.0)) if isinstance(aff, dict) else 0.0
                    try:
                        val = float(raw or 0.0)
                    except Exception:
                        val = 0.0
                    if val < 0.50 or getattr(member, "current_protocult_id", None) != cid:
                        both = False
                        break
                if both:
                    add("ruling-household", 40)
                    break

        return score, parts

    def _apotheosis_cult_ready(self, cult):
        if cult is None or getattr(cult, "failed", False) or getattr(cult, "formalized", False):
            return False, {}
        if getattr(cult, "deity_object", None) is not None or getattr(cult, "ascended", False):
            return False, {}
        members, affinity_mass = self._apotheosis_cult_members_and_affinity(cult)
        age_years = max(0.0, (int(getattr(self.world, "tick", 0)) - int(getattr(cult, "founded_tick", 0) or 0)) / float(globals().get("TICKS_PER_YEAR", 1080) or 1080))
        gate = {
            "members": len(members),
            "affinity_mass": affinity_mass,
            "pressure": float(getattr(cult, "legend_pressure", 0.0) or 0.0),
            "mythic": float(getattr(cult, "mythic_legacy_score", 0.0) or 0.0),
            "regions": len(getattr(cult, "known_region_ids", set()) or set()),
            "age_years": age_years,
        }
        ready = (
            gate["members"] >= int(globals().get("APOTHEOSIS_MIN_CULT_MEMBERS", 12))
            and gate["affinity_mass"] >= float(globals().get("APOTHEOSIS_MIN_CULT_AFFINITY_MASS", 4.0))
            and gate["pressure"] >= float(globals().get("APOTHEOSIS_MIN_LEGEND_PRESSURE", 60.0))
            and gate["mythic"] >= float(globals().get("APOTHEOSIS_MIN_MYTHIC_LEGACY", 220.0))
            and gate["regions"] >= int(globals().get("APOTHEOSIS_MIN_REGIONS", 2))
            and gate["age_years"] >= float(globals().get("APOTHEOSIS_MIN_CULT_AGE_YEARS", 3))
        )
        return ready, gate

    def _apotheosis_candidate_rows(self, limit=None):
        world = self.world
        rows = []
        cults = [c for c in getattr(world, "proto_cults", {}).values() if not getattr(c, "failed", False) and not getattr(c, "formalized", False) and not getattr(c, "ascended", False)]
        if not cults:
            return rows

        # Build actor-by-protocult and affinity-mass indexes in one O(actors) pass.
        # Replaces O(cults * actors) repeated scans in _apotheosis_cult_ready + candidate loop.
        actors_by_cult: Dict[Any, list] = {}
        affinity_by_cult: Dict[Any, float] = {}
        for actor in world.living_actors():
            if getattr(actor, "role", None) == Role.COMMONER or getattr(actor, "in_school", False):
                continue
            proto = getattr(actor, "current_protocult_id", None)
            if proto is None:
                continue
            actors_by_cult.setdefault(proto, []).append(actor)
            aff_map = getattr(actor, "cult_affinity", {}) or {}
            if isinstance(aff_map, dict):
                raw = aff_map.get(proto, aff_map.get(str(proto), 0.0))
                try:
                    affinity_by_cult[proto] = affinity_by_cult.get(proto, 0.0) + max(0.0, float(raw or 0.0))
                except Exception:
                    pass

        for cult in cults:
            cid = getattr(cult, "id", None)
            # Use pre-built index for cult_ready check instead of separate actor scan.
            cult_actors = actors_by_cult.get(cid, actors_by_cult.get(str(cid), []))
            cult_affinity = affinity_by_cult.get(cid, affinity_by_cult.get(str(cid), 0.0))
            age_years = max(0.0, (int(getattr(world, "tick", 0)) - int(getattr(cult, "founded_tick", 0) or 0)) / float(globals().get("TICKS_PER_YEAR", 1080) or 1080))
            gate = {
                "members": len(cult_actors),
                "affinity_mass": cult_affinity,
                "pressure": float(getattr(cult, "legend_pressure", 0.0) or 0.0),
                "mythic": float(getattr(cult, "mythic_legacy_score", 0.0) or 0.0),
                "regions": len(getattr(cult, "known_region_ids", set()) or set()),
                "age_years": age_years,
            }
            cult_ready = (
                gate["members"] >= int(globals().get("APOTHEOSIS_MIN_CULT_MEMBERS", 12))
                and gate["affinity_mass"] >= float(globals().get("APOTHEOSIS_MIN_CULT_AFFINITY_MASS", 4.0))
                and gate["pressure"] >= float(globals().get("APOTHEOSIS_MIN_LEGEND_PRESSURE", 60.0))
                and gate["mythic"] >= float(globals().get("APOTHEOSIS_MIN_MYTHIC_LEGACY", 220.0))
                and gate["regions"] >= int(globals().get("APOTHEOSIS_MIN_REGIONS", 2))
                and gate["age_years"] >= float(globals().get("APOTHEOSIS_MIN_CULT_AGE_YEARS", 3))
            )
            for actor in cult_actors:
                # actor is already non-commoner and not in-school from the index build
                aff = getattr(actor, "cult_affinity", {}) or {}
                raw_aff = aff.get(cid, aff.get(str(cid), 0.0)) if isinstance(aff, dict) else 0.0
                try:
                    affinity = float(raw_aff or 0.0)
                except Exception:
                    affinity = 0.0
                doubt = float(getattr(actor, "faith_doubt", 0.0) or 0.0)
                clout, parts = self._apotheosis_actor_clout(actor, cult)
                readiness = (
                    clout
                    + affinity * 100.0
                    + doubt * 80.0
                    + min(120.0, float(gate.get("pressure", 0.0)) * 0.5)
                    + min(120.0, float(gate.get("mythic", 0.0)) / 3.0)
                    + min(40.0, float(gate.get("regions", 0.0)) * 6.0)
                    + min(40.0, float(gate.get("affinity_mass", 0.0)) * 2.0)
                )
                eligible = (
                    bool(cult_ready)
                    and affinity >= float(globals().get("APOTHEOSIS_MIN_AFFINITY", 0.50))
                    and doubt >= float(globals().get("APOTHEOSIS_MIN_DOUBT", 0.20))
                    and clout >= float(globals().get("APOTHEOSIS_MIN_CLOUT", 180.0))
                    and readiness >= float(globals().get("APOTHEOSIS_MIN_DECLARATION_SCORE", 420.0))
                )
                rows.append({
                    "readiness": readiness,
                    "eligible": eligible,
                    "actor": actor,
                    "cult": cult,
                    "affinity": affinity,
                    "doubt": doubt,
                    "clout": clout,
                    "parts": parts,
                    "gate": gate,
                })
        rows.sort(key=lambda row: (row["eligible"], row["readiness"]), reverse=True)
        if limit is not None:
            return rows[:int(limit)]
        return rows

    def _active_pantheon_gods(self) -> List[object]:
        """Formal gods with agency. Dead/vanquished gods remain historical records but do not occupy active pantheon slots."""
        gods = list(getattr(self.world, "gods", []) or getattr(self, "pantheon", []) or [])
        dead = set(getattr(self.world, "dead_gods", set()) or set())
        out = []
        seen = set()
        for god in gods:
            if god in dead:
                continue
            key = deity_value(god).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(god)
        return out

    def _pantheon_has_open_slot(self) -> bool:
        cap = int(globals().get("PANTHEON_MAX_ACTIVE_GODS", -1))
        if cap < 0:
            return True
        return len(self._active_pantheon_gods()) < cap

    def _maybe_trigger_apotheosis(self) -> None:
        world = self.world
        if not bool(globals().get("APOTHEOSIS_ENABLED", True)):
            return
        if not self._pantheon_has_open_slot():
            return
        cadence = int(globals().get("APOTHEOSIS_CHECK_INTERVAL_TICKS", globals().get("TICKS_PER_YEAR", 1080)))
        if world.tick - int(getattr(world, "last_apotheosis_check_tick", -999999)) < cadence:
            return
        world.last_apotheosis_check_tick = world.tick
        rows = [row for row in self._apotheosis_candidate_rows(limit=None) if row.get("eligible")]
        if not rows:
            return
        row = rows[0]
        chance = min(
            float(globals().get("APOTHEOSIS_MAX_CHANCE", 0.35)),
            float(globals().get("APOTHEOSIS_BASE_CHANCE", 0.04))
            + float(row["readiness"]) / float(globals().get("APOTHEOSIS_DECLARATION_SCORE_DIVISOR", 1800.0)),
        )
        if self.rng.random() >= chance:
            return
        self._perform_apotheosis(row["cult"], row["actor"], row)

    def _unique_apotheosis_name(self, base_name: str) -> str:
        base = str(base_name or "The Remembered").strip() or "The Remembered"
        existing = {deity_value(g).strip().lower() for g in list(getattr(self.world, "gods", [])) + list(getattr(self, "pantheon", []))}
        if base.lower() not in existing:
            return base
        n = 2
        while f"{base} {n}".lower() in existing:
            n += 1
        return f"{base} {n}"

    def _create_apotheosis_profile(self, cult, founder):
        subject = None
        monster = None
        if getattr(cult, "subject_kind", "actor") == "monster":
            monster = getattr(self.world, "monsters", {}).get(getattr(cult, "subject_monster_id", None))
        elif hasattr(self, "resolve_actor"):
            subject = self.resolve_actor(getattr(cult, "subject_actor_id", None))
        base_name = getattr(cult, "public_title", "") or getattr(cult, "subject_name", "") or getattr(cult, "name", "The Remembered")
        name = self._unique_apotheosis_name(base_name)
        if monster is not None:
            alignment = "Neutral Evil"
            role_name = "Monster"
            traits = ["dread", "undying"]
        else:
            alignment = getattr(getattr(subject, "alignment", None), "value", getattr(getattr(founder, "alignment", None), "value", "True Neutral"))
            role_name = getattr(getattr(subject, "role", None), "value", getattr(getattr(founder, "role", None), "value", "Fighter"))
            traits = list(getattr(subject, "traits", []) or getattr(founder, "traits", []) or [])[:2]
        domains = []
        weights = getattr(cult, "domain_weights", {}) or {}
        if weights:
            domains = [k for k, _v in sorted(weights.items(), key=lambda item: float(item[1]), reverse=True)[:3]]
        if not domains:
            domains = ["fate", "knowledge"]
        profile = GodProfile(
            name=name,
            alignment=alignment,
            favored_classes=[role_name],
            favored_traits=traits,
            disfavored_traits=[],
            domains=domains,
            conversion_bias=1.05,
            order_modifier=0.0,
            volatility_modifier=0.08,
            description=(f"A living monster-god born from fear and taboo around {getattr(cult, 'subject_name', name)}." if getattr(cult, "subject_kind", "actor") == "monster" else f"An apotheosized cult of memory born from open worship of {getattr(cult, 'subject_name', name)}."),
            is_player=False,
            color="white",
            starting_souls=int(globals().get("APOTHEOSIS_STARTING_SOULS", 150)),
            source_path="apotheosis",
            profile_id=(f"monster_apotheosis_{getattr(cult, 'subject_monster_id', getattr(cult, 'id', 0))}" if getattr(cult, "subject_kind", "actor") == "monster" else f"apotheosis_{getattr(cult, 'subject_actor_id', getattr(cult, 'id', 0))}"),
            active_for_run=True,
        )
        return profile

    def _convert_actor_to_apotheosis(self, actor, deity, cult, founder_row=None, force=False) -> bool:
        if actor is None or deity is None:
            return False
        if not force:
            cid = getattr(cult, "id", None)
            aff_map = getattr(actor, "cult_affinity", {}) or {}
            raw = aff_map.get(cid, aff_map.get(str(cid), 0.0)) if isinstance(aff_map, dict) else 0.0
            try:
                affinity = float(raw or 0.0)
            except Exception:
                affinity = 0.0
            doubt = float(getattr(actor, "faith_doubt", 0.0) or 0.0)
            clout, _parts = self._apotheosis_actor_clout(actor, cult)
            chance = (
                float(globals().get("APOTHEOSIS_ACTOR_BASE_CONVERSION_CHANCE", 0.12))
                + affinity * float(globals().get("APOTHEOSIS_ACTOR_AFFINITY_WEIGHT", 0.62))
                + doubt * float(globals().get("APOTHEOSIS_ACTOR_DOUBT_WEIGHT", 0.18))
                + min(float(globals().get("APOTHEOSIS_ACTOR_CLOUT_BONUS_CAP", 0.12)), clout / 2000.0)
            )
            if getattr(actor, "locked_deity", False):
                chance = min(chance, float(globals().get("APOTHEOSIS_ACTOR_LOCKED_MAX_CHANCE", 0.03)))
            if getattr(actor, "champion_of", None) is not None and getattr(actor, "champion_of", None) != deity:
                chance = min(chance, float(globals().get("APOTHEOSIS_ACTOR_CHAMPION_MAX_CHANCE", 0.12)))
            if self.rng.random() >= max(0.0, min(0.95, chance)):
                return False
        changed = change_actor_deity(self, actor, deity, conviction=int(globals().get("APOTHEOSIS_CONVERTED_ACTOR_CONVICTION", 70)), locked=False)
        clear_actor_protocult_membership(self, actor, getattr(cult, "id", None))
        if isinstance(getattr(actor, "cult_affinity", None), dict):
            actor.cult_affinity.pop(getattr(cult, "id", None), None)
            actor.cult_affinity.pop(str(getattr(cult, "id", None)), None)
        return True or changed

    def _convert_commoners_to_apotheosis(self, deity, cult, founder) -> int:
        world = self.world
        total_converted = 0
        if not hasattr(world, "commoner_faith_by_region"):
            return 0
        known = set(getattr(cult, "known_region_ids", set()) or set())
        founder_region = getattr(founder, "region_id", None)
        founder_polity_id = getattr(founder, "polity_id", None)
        for rid, faith in world.commoner_faith_by_region.items():
            commoners = int(getattr(world, "commoners_by_region", {}).get(rid, 0) or 0)
            if commoners <= 0:
                faith.setdefault(deity, 0)
                continue
            latent = int(getattr(cult, "hidden_commoner_affinity_by_region", {}).get(rid, 0) or 0)
            if rid not in known and latent <= 0:
                faith.setdefault(deity, 0)
                continue
            rate = float(globals().get("APOTHEOSIS_COMMONER_BASE_CONVERSION_RATE", 0.02))
            rate += min(0.30, (latent / max(1, commoners)) * float(globals().get("APOTHEOSIS_COMMONER_LATENT_MULT", 0.80)))
            if rid == founder_region:
                rate += float(globals().get("APOTHEOSIS_COMMONER_FOUNDER_REGION_BONUS", 0.06))
            region = getattr(world, "regions", {}).get(rid)
            if founder_polity_id is not None and region is not None and getattr(region, "polity_id", None) == founder_polity_id:
                rate += float(globals().get("APOTHEOSIS_COMMONER_POLITY_REGION_BONUS", 0.04))
            rate = max(0.0, min(float(globals().get("APOTHEOSIS_COMMONER_MAX_REGION_RATE", 0.45)), rate))
            convert = min(commoners, int(commoners * rate))
            if convert <= 0:
                faith.setdefault(deity, 0)
                continue
            sources = [d for d in list(faith.keys()) if d != deity and int(faith.get(d, 0) or 0) > 0]
            pool = sum(int(faith.get(d, 0) or 0) for d in sources)
            if pool <= 0:
                faith[deity] = int(faith.get(deity, 0) or 0) + convert
                total_converted += convert
                continue
            moved = min(convert, pool)
            assigned = 0
            for i, src in enumerate(sources):
                available = int(faith.get(src, 0) or 0)
                if i == len(sources) - 1:
                    take = min(available, moved - assigned)
                else:
                    take = min(available, int(moved * (available / pool)))
                    assigned += take
                faith[src] = max(0, available - take)
                faith[deity] = int(faith.get(deity, 0) or 0) + take
                total_converted += take
            faith.setdefault(deity, 0)
        return total_converted

    def _perform_apotheosis(self, cult, founder, row=None) -> bool:
        world = self.world
        if cult is None or founder is None:
            return False
        if not self._pantheon_has_open_slot():
            return False
        profile = self._create_apotheosis_profile(cult, founder)
        deity = profile

        if not hasattr(world, "gods") or getattr(world, "gods", None) is None:
            world.gods = list(getattr(self, "pantheon", []))
        if deity not in world.gods:
            world.gods.append(deity)
        if not hasattr(self, "pantheon") or getattr(self, "pantheon", None) is None:
            self.pantheon = list(world.gods)
        elif deity not in self.pantheon:
            self.pantheon.append(deity)

        if not hasattr(world, "god_profiles") or getattr(world, "god_profiles", None) is None:
            world.god_profiles = {}
        world.god_profiles[deity] = profile
        if not hasattr(self, "god_profiles") or getattr(self, "god_profiles", None) is None:
            self.god_profiles = {}
        self.god_profiles[deity] = profile

        if not hasattr(world, "souls_by_deity") or getattr(world, "souls_by_deity", None) is None:
            world.souls_by_deity = {}
        world.souls_by_deity[deity] = int(getattr(profile, "starting_souls", 0) or 0)

        # Add the new god key everywhere before conversion so influence counts are immediate.
        for faith in getattr(world, "commoner_faith_by_region", {}).values():
            faith.setdefault(deity, 0)

        founder_changed = self._convert_actor_to_apotheosis(founder, deity, cult, row, force=True)
        converted_actors = 1 if founder_changed else 0
        cid = getattr(cult, "id", None)
        for actor in list(world.living_actors()):
            if getattr(actor, "id", None) == getattr(founder, "id", None):
                continue
            if getattr(actor, "current_protocult_id", None) == cid or str(getattr(actor, "current_protocult_id", "")) == str(cid):
                if self._convert_actor_to_apotheosis(actor, deity, cult, row, force=False):
                    converted_actors += 1

        converted_commoners = self._convert_commoners_to_apotheosis(deity, cult, founder)

        cult.deity_object = deity
        cult.ascended = True
        cult.open_worship = True
        cult.formalized = True
        cult.open_worship_tick = int(getattr(world, "tick", -1))
        cult.open_worship_actor_id = getattr(founder, "id", None)
        cult.open_worship_actor_name = founder.short_name() if hasattr(founder, "short_name") else str(getattr(founder, "id", "Unknown"))
        parts = row.get("parts", []) if isinstance(row, dict) else []
        cult.open_worship_reason = ", ".join(parts[:4]) if parts else "public declaration"

        self._refresh_god_state_if_due(force=True)
        title = deity_value(deity)
        world.log(
            (f"APOTHEOSIS: {cult.open_worship_actor_name} openly venerates {getattr(cult, 'subject_name', title)} as {title}. "
             f"The hidden cult becomes a god of the pantheon; {converted_actors} actors and {converted_commoners} commoners convert in the first wave."),
            importance=5,
            category="deification",
        )
        return True


    def _ai_immortal_tick(self) -> None:
        """Very conservative AI god activity. Uses existing world actions; does not replace player actions."""
        world = self.world
        if not bool(globals().get("AI_IMMORTAL_ACTIONS_ENABLED", True)):
            return
        cadence = int(globals().get("AI_IMMORTAL_ACTION_INTERVAL_TICKS", globals().get("TICKS_PER_SEASON", 270)))
        if cadence > 1 and world.tick % cadence != 0:
            return
        self._refresh_god_state_if_due(force=True)
        if hasattr(self, "_formal_school_deities"):
            gods = list(self._formal_school_deities())
        else:
            gods = [g for g in getattr(world, "gods", []) if g not in getattr(world, "dead_gods", set())]
        self.rng.shuffle(gods)
        ai_gods = []
        for god in gods:
            profile = getattr(world, "god_profiles", {}).get(god)
            if bool(getattr(profile, "is_player", False) or getattr(profile, "is_player_god", False)):
                continue
            ai_gods.append(god)
        for god in ai_gods[: int(globals().get("AI_IMMORTAL_MAX_GODS_PER_TICK", 2))]:
            state = getattr(world, "god_state", {}).get(god)
            if state is None:
                continue
            last = int(getattr(world, "ai_god_last_action_tick", {}).get(god, -999999))
            if world.tick - last < int(globals().get("AI_IMMORTAL_ACTION_COOLDOWN_TICKS", globals().get("TICKS_PER_YEAR", 1080))):
                continue
            acted = self._ai_immortal_take_action(god, state)
            if acted:
                world.ai_god_last_action_tick[god] = world.tick
                break

    def _ai_immortal_take_action(self, god, state) -> bool:
        # 1) Suppress dangerous proto-cults in regions dominated by this god.
        if self._ai_god_suppress_proto_cult(god, state):
            return True
        # 2) Emergency champions remain the primary active defense for weak gods.
        if hasattr(self, "_maybe_spawn_divine_champions"):
            self._maybe_spawn_divine_champions()
        # 3) Rare holy wars for established or threatened gods.
        if self._ai_god_holy_war(god, state):
            return True
        return False

    def _ai_god_suppress_proto_cult(self, god, state) -> bool:
        world = self.world
        cults = [c for c in getattr(world, "proto_cults", {}).values() if not getattr(c, "ascended", False) and not getattr(c, "failed", False)]
        if not cults:
            return False
        candidates = []
        for cult in cults:
            overlap = 0
            for rid in getattr(cult, "known_region_ids", set()):
                faith = getattr(world, "commoner_faith_by_region", {}).get(rid, {})
                if faith and max(faith, key=lambda d: faith.get(d, 0)) == god:
                    overlap += 1
            if overlap:
                candidates.append((cult.legend_pressure * overlap, cult))
        if not candidates:
            return False
        if int(getattr(state, "souls", 0)) < int(globals().get("AI_PROTO_CULT_SUPPRESS_SOUL_COST", 50)):
            return False
        candidates.sort(key=lambda item: item[0], reverse=True)
        cult = candidates[0][1]
        cost = int(globals().get("AI_PROTO_CULT_SUPPRESS_SOUL_COST", 50))
        world.souls_by_deity[god] = max(0, int(world.souls_by_deity.get(god, 0)) - cost)
        cult.legend_pressure *= float(globals().get("AI_PROTO_CULT_SUPPRESS_PRESSURE_MULT", 0.82))
        for rid in list(getattr(cult, "hidden_commoner_affinity_by_region", {}).keys()):
            cult.hidden_commoner_affinity_by_region[rid] = int(cult.hidden_commoner_affinity_by_region[rid] * 0.75)
        world.log(f"{deity_value(god)} moves quietly against {cult.name}, dimming its songs and scattering its devotees.", importance=3, category="immortal_ai")
        return True

    def _ai_god_holy_war(self, god, state) -> bool:
        world = self.world
        if not bool(globals().get("AI_HOLY_WARS_ENABLED", True)):
            return False
        if int(getattr(state, "souls", 0)) < int(globals().get("HOLY_WAR_SOUL_COST", 250)):
            return False
        if getattr(state, "influence_share", 0.0) < float(globals().get("AI_HOLY_WAR_MIN_ATTACKER_INFLUENCE", 18.0)):
            return False
        if world.tick < getattr(world, "last_ai_holy_war_tick", -999999) + int(globals().get("AI_HOLY_WAR_COOLDOWN_TICKS", globals().get("TICKS_PER_YEAR", 1080) * 8)):
            return False
        rivals = [(d, s) for d, s in getattr(world, "god_state", {}).items() if d != god and d not in getattr(world, "dead_gods", set()) and getattr(s, "influence_share", 0.0) > 3.0]
        if not rivals:
            return False
        # Only fairly rare: don't let AI holy wars become constant sawblades.
        if self.rng.random() > float(globals().get("AI_HOLY_WAR_CHANCE", 0.12)):
            return False
        target, target_state = max(rivals, key=lambda item: (item[1].influence_share, self.rng.random()))
        if not hasattr(self, "_launch_holy_war_as_god"):
            return False
        ok, _msg = self._launch_holy_war_as_god(god, target)
        if ok:
            world.last_ai_holy_war_tick = world.tick
        return bool(ok)
