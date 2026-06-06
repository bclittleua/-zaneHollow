from __future__ import annotations

import argparse
import configparser
import importlib.util
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

BASE_DIR = Path(__file__).resolve().parent


def _import_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {module_name!r} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Import the live project files instead of copying their rules.
farm_module = _import_module_from_path("FASE", BASE_DIR / "FASE.py")
population_module = _import_module_from_path("FASEpop", BASE_DIR / "FASEpop.py")

# Use the exact classes the current simulator loads.
Alignment = farm_module.Alignment
Deity = farm_module.Deity
Role = farm_module.Role
Actor = farm_module.Actor

# Inject the same globals population_v18 expects during normal sim startup.
population_module.MALE_FIRST_NAMES = list(farm_module.MALE_FIRST_NAMES)
population_module.FEMALE_FIRST_NAMES = list(farm_module.FEMALE_FIRST_NAMES)
population_module.SURNAMES = list(farm_module.SURNAMES)
population_module.TRAITS = list(farm_module.TRAITS)
population_module.ROLE_WEIGHTS = list(farm_module.ROLE_WEIGHTS)
population_module.WIZARD_PROMOTION_CHANCE = farm_module.WIZARD_PROMOTION_CHANCE
population_module.MONTH_NAMES = list(farm_module.MONTH_NAMES)
population_module.Alignment = Alignment
population_module.Role = Role
population_module.Deity = Deity
population_module.MonsterKind = farm_module.MonsterKind
population_module.Actor = Actor

PopulationMixin = population_module.PopulationMixin

ALIGNMENT_LOOKUP = {a.value.lower(): a for a in Alignment}
DEITY_LOOKUP = {d.value.lower(): d for d in Deity}
ROLE_LOOKUP = {r.value.lower(): r for r in Role}
SEX_CHOICES = {"m": "M", "male": "M", "f": "F", "female": "F"}
ADVENTURER_ROLES = [Role.FIGHTER, Role.WARDEN, Role.WIZARD, Role.BARD]
ADVENTURER_ROLE_PAIRS = [
    (role, weight) for role, weight in farm_module.ROLE_WEIGHTS if role in ADVENTURER_ROLES
]


@dataclass
class SeedCharacter:
    name: str
    surname: str
    sex: str
    role: Role
    alignment: Alignment
    deity: object
    locked_deity: bool
    age: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    luck: int
    birth_year: int
    birth_month: int
    birth_day: int
    title: str = ""
    preferred_region: str = ""
    reputation: int = 0
    experience: int = 0
    traits: tuple[str, str] = ("", "")
    hp_override: Optional[int] = None
    locked: bool = True
    seed_source: str = "fantag"
    version: int = 8
    active_for_run: bool = False
    active_champion: bool = False
    starting_relic_name: str = ""
    starting_relic_type: str = "custom"
    starting_relic_slot: str = "misc"
    starting_relic_power_bonus: int = 0
    starting_relic_reputation_bonus: int = 0
    starting_relic_description: str = ""

    @property
    def hp(self) -> int:
        if self.hp_override is not None:
            return int(self.hp_override)
        return FantagRules.base_hp_for(self.role, self.constitution)

    @property
    def max_hp(self) -> int:
        return self.hp


class FantagRules(PopulationMixin):
    """Thin adapter around the live population + current generator rules."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.world = None

    @staticmethod
    def base_hp_for(role: Role, constitution: int) -> int:
        helper = FantagRules(random.Random(0))
        return helper._base_hp(role, constitution)

    def pick_role(self) -> Role:
        roles, weights = zip(*ADVENTURER_ROLE_PAIRS)
        return self.rng.choices(roles, weights=weights, k=1)[0]

    def pick_alignment_for_role(self, role: Role) -> Alignment:
        return farm_module._pick_alignment_for_role(self, role)

    def random_identity(self, forced_sex: Optional[str] = None) -> tuple[str, str, str]:
        if forced_sex is None:
            return self._random_person_identity()
        sex = normalize_sex(forced_sex)
        if sex == "M":
            first = self.rng.choice(population_module.MALE_FIRST_NAMES)
        else:
            first = self.rng.choice(population_module.FEMALE_FIRST_NAMES)
        return first, self.rng.choice(population_module.SURNAMES), sex

    def make_character(
        self,
        *,
        role: Optional[Role] = None,
        alignment: Optional[Alignment] = None,
        deity: Optional[object] = None,
        sex: Optional[str] = None,
        age: Optional[int] = None,
        name: Optional[str] = None,
        surname: Optional[str] = None,
        title: str = "",
        preferred_region: str = "",
        reputation: int = 0,
        experience: int = 0,
        traits: Optional[Iterable[str]] = None,
        op: bool = False,
        active_for_run: bool = False,
        active_champion: bool = False,
        starting_relic_name: str = "",
        starting_relic_type: str = "custom",
        starting_relic_slot: str = "misc",
        starting_relic_power_bonus: int = 0,
        starting_relic_reputation_bonus: int = 0,
        starting_relic_description: str = "",
    ) -> SeedCharacter:
        role = role or self.pick_role()
        alignment = alignment or self.pick_alignment_for_role(role)
        if role == Role.BARD:
            allowed = farm_module._BARD_ALLOWED_ALIGNMENTS
            if alignment not in allowed:
                raise ValueError("Bards cannot be generated with evil alignment under the current rules.")

        deity = deity or self._weighted_random_deity(alignment)
        first, random_surname, resolved_sex = self.random_identity(forced_sex=sex)
        if name:
            first = name.strip()
        if surname:
            random_surname = surname.strip()

        stats = self._roll_stats(role)
        if op:
            stats = (99, 99, 99, 99, 99, 99, 99)
        rolled_age = self._initial_age_for_role(role)
        age = rolled_age if age is None else max(16, int(age))

        chosen_traits = [str(t).strip() for t in (traits or []) if str(t).strip()]
        if len(chosen_traits) >= 2:
            trait_pair = (chosen_traits[0], chosen_traits[1])
        elif len(chosen_traits) == 1:
            fallback = self.rng.choice([t for t in population_module.TRAITS if t != chosen_traits[0]])
            trait_pair = (chosen_traits[0], fallback)
        else:
            picked = self.rng.sample(population_module.TRAITS, 2)
            trait_pair = (picked[0], picked[1])

        birth_year = 1 - age
        birth_month = self.rng.randint(1, 12)
        birth_day = self.rng.randint(1, 30)

        return SeedCharacter(
            name=first,
            surname=random_surname,
            sex=resolved_sex,
            role=role,
            alignment=alignment,
            deity=deity,
            locked_deity=True,
            age=age,
            strength=stats[0],
            dexterity=stats[1],
            constitution=stats[2],
            intelligence=stats[3],
            wisdom=stats[4],
            charisma=stats[5],
            luck=stats[6],
            birth_year=birth_year,
            birth_month=birth_month,
            birth_day=birth_day,
            title=title.strip(),
            preferred_region=preferred_region.strip(),
            reputation=max(0, int(reputation)),
            experience=max(0, int(experience)),
            traits=trait_pair,
            hp_override=200 if op else None,
            active_for_run=bool(active_for_run),
            active_champion=bool(active_champion),
            starting_relic_name=starting_relic_name.strip(),
            starting_relic_type=starting_relic_type.strip() or "custom",
            starting_relic_slot=starting_relic_slot.strip() or "misc",
            starting_relic_power_bonus=max(0, int(starting_relic_power_bonus)),
            starting_relic_reputation_bonus=max(0, int(starting_relic_reputation_bonus)),
            starting_relic_description=starting_relic_description.strip(),
        )


def normalize_sex(value: Optional[str]) -> str:
    if value is None:
        raise ValueError("Sex cannot be None when normalization is requested.")
    key = str(value).strip().lower()
    if key not in SEX_CHOICES:
        raise ValueError(f"Unknown sex {value!r}. Use M/F or male/female.")
    return SEX_CHOICES[key]



def parse_role(value: Optional[str]) -> Optional[Role]:
    if value is None:
        return None
    raw = value.strip()
    key = raw.lower()
    role = ROLE_LOOKUP.get(key)
    if role is None:
        enum_key = raw.upper().replace(" ", "_")
        role = Role.__members__.get(enum_key)
    if role is None:
        raise argparse.ArgumentTypeError(f"Unknown role {value!r}.")
    if role == Role.COMMONER:
        raise argparse.ArgumentTypeError("fantag is for adventurers; Commoner is not allowed here.")
    return role



def parse_alignment(value: Optional[str]) -> Optional[Alignment]:
    if value is None:
        return None
    raw = value.strip()
    key = raw.lower()
    alignment = ALIGNMENT_LOOKUP.get(key)
    if alignment is None:
        enum_key = raw.upper().replace(" ", "_")
        alignment = Alignment.__members__.get(enum_key)
    if alignment is None:
        raise argparse.ArgumentTypeError(f"Unknown alignment {value!r}.")
    return alignment



def parse_deity(value: Optional[str]) -> Optional[object]:
    if value is None:
        return None
    raw = value.strip()
    key = raw.lower()
    return DEITY_LOOKUP.get(key, raw)


def deity_name(deity: object) -> str:
    return getattr(deity, "value", getattr(deity, "name", str(deity)))



def slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "unknown"



def unique_story_path(out_dir: Path, char: SeedCharacter) -> Path:
    stem = f"pending+{char.name[:1].upper()}+{slugify(char.surname)}+{slugify(char.role.value)}"
    candidate = out_dir / f"{stem}.stri"
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}_{counter}.stri"
        counter += 1
    return candidate



def write_stri(path: Path, char: SeedCharacter) -> None:
    cfg = configparser.ConfigParser()
    cfg.optionxform = str

    cfg["seed"] = {
        "version": str(char.version),
        "source": char.seed_source,
        "locked": str(char.locked).lower(),
    }
    cfg["identity"] = {
        "id": "",
        "name": char.name,
        "surname": char.surname,
        "sex": char.sex,
    }
    cfg["build"] = {
        "role": char.role.value,
        "alignment": char.alignment.value,
        "deity": deity_name(char.deity),
        "age": str(char.age),
        "strength": str(char.strength),
        "dexterity": str(char.dexterity),
        "constitution": str(char.constitution),
        "intelligence": str(char.intelligence),
        "wisdom": str(char.wisdom),
        "charisma": str(char.charisma),
        "luck": str(char.luck),
        "hp": str(char.hp),
        "max_hp": str(char.max_hp),
        "birth_year": str(char.birth_year),
        "birth_month": str(char.birth_month),
        "birth_day": str(char.birth_day),
        "traits": ", ".join(char.traits),
    }
    cfg["faith"] = {
        "deity": deity_name(char.deity),
        "locked_deity": str(char.locked_deity).lower(),
        "active_champion": str(char.active_champion).lower(),
    }
    cfg["spawn"] = {
        "preferred_region": char.preferred_region,
        "title": char.title,
        "reputation": str(char.reputation),
        "experience": str(char.experience),
    }
    cfg["story"] = {
        "active_for_run": str(char.active_for_run).lower(),
        "status": "seeded",
        "current_region": "",
        "party_id": "",
        "polity_id": "",
        "alive": "true",
        "notes": "Generated by fantag. World generation should assign a real ID and rename this file.",
    }
    if char.starting_relic_name:
        cfg["starting_relic"] = {
            "name": char.starting_relic_name,
            "type": char.starting_relic_type,
            "slot": char.starting_relic_slot,
            "power_bonus": str(char.starting_relic_power_bonus),
            "reputation_bonus": str(char.starting_relic_reputation_bonus),
            "description": char.starting_relic_description,
        }
    cfg["visits"] = {}
    cfg["journal"] = {
        "entry_0001": "Seed file created.",
    }

    with path.open("w", encoding="utf-8") as handle:
        cfg.write(handle)
        handle.write("\n")



def default_story_dir() -> Path:
    """Return the canonical pending/story actor folder.

    fantag usually lives in ./data beside FASE.py, while .stri files are
    consumed from the project-level ./MCE folder. Keep pending files there so
    the launcher/simulator see the same actor pool before and after activation.
    """
    if BASE_DIR.name.lower() == "data":
        return BASE_DIR.parent / "MCE"
    return BASE_DIR / "MCE"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantag",
        description="Fantasy Antfarm Adventurer Generator (.stri seed files).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("count", nargs="?", type=int, default=1, help="Number of .stri files to generate (default: 1).")
    parser.add_argument("--seed", default=None, help="RNG seed for repeatable generation.")
    parser.add_argument("--out", default=None, help="Output directory for .stri files (default: project MCE folder).")
    parser.add_argument("-op", action="store_true", help="Overpowered mode: all stats=99 and hp=200.")
    parser.add_argument("-r", "--role", type=parse_role, default=None, help="Force class/role (Fighter, Wizard, Warden, Bard).")
    parser.add_argument("-a", "--alignment", type=parse_alignment, default=None, help='Force alignment (for example: "Lawful Neutral").')
    parser.add_argument("--deity", type=parse_deity, default=None, help="Force deity. Built-in names are validated; custom god names are accepted as text.")
    parser.add_argument("--sex", default=None, help="Force sex: M/F or male/female.")
    parser.add_argument("--age", type=int, default=None, help="Force age.")
    parser.add_argument("--name", default=None, help="Force first name.")
    parser.add_argument("--surname", default=None, help="Force surname.")
    parser.add_argument("--title", default="", help="Optional title.")
    parser.add_argument("--preferred-region", default="", help="Optional preferred spawn region name.")
    parser.add_argument("--reputation", type=int, default=0, help="Initial reputation seed value.")
    parser.add_argument("--experience", type=int, default=0, help="Initial experience seed value.")
    parser.add_argument("--trait", action="append", default=None, help="Trait override; may be used twice.")
    parser.add_argument("--active-for-run", action="store_true", help="Mark generated .stri as active for the next run.")
    parser.add_argument("--champion", action="store_true", help="Seed this adventurer as an active champion of their deity.")
    parser.add_argument("--relic-name", default="", help="Optional custom starting relic name.")
    parser.add_argument("--relic-type", default="custom", help="Optional starting relic type.")
    parser.add_argument("--relic-slot", default="misc", help="Optional starting relic slot.")
    parser.add_argument("--relic-power", type=int, default=0, help="Optional starting relic power bonus.")
    parser.add_argument("--relic-reputation", type=int, default=0, help="Optional starting relic reputation bonus.")
    parser.add_argument("--relic-description", default="", help="Optional starting relic description.")
    return parser



def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.count < 1:
        parser.error("count must be at least 1")

    out_dir = (Path(args.out).resolve() if args.out else default_story_dir().resolve())
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    generator = FantagRules(rng)

    created: list[Path] = []
    for _ in range(args.count):
        char = generator.make_character(
            role=args.role,
            alignment=args.alignment,
            deity=args.deity,
            sex=args.sex,
            age=args.age,
            name=args.name,
            surname=args.surname,
            title=args.title,
            preferred_region=args.preferred_region,
            reputation=args.reputation,
            experience=args.experience,
            traits=args.trait,
            op=args.op,
            active_for_run=args.active_for_run or args.champion,
            active_champion=args.champion,
            starting_relic_name=args.relic_name,
            starting_relic_type=args.relic_type,
            starting_relic_slot=args.relic_slot,
            starting_relic_power_bonus=args.relic_power,
            starting_relic_reputation_bonus=args.relic_reputation,
            starting_relic_description=args.relic_description,
        )
        path = unique_story_path(out_dir, char)
        write_stri(path, char)
        created.append(path)

    for path in created:
        print(path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
