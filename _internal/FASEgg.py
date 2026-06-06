from __future__ import annotations

import argparse
import configparser
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

try:
    from FASEimm import VALID_ALIGNMENTS, VALID_DOMAINS
except Exception:
    VALID_ALIGNMENTS = [
        "Lawful Good", "Neutral Good", "Chaotic Good",
        "Lawful Neutral", "True Neutral", "Chaotic Neutral",
        "Lawful Evil", "Neutral Evil", "Chaotic Evil",
    ]
    VALID_DOMAINS = [
        "order", "chaos", "war", "domination", "trickery", "growth",
        "decay", "fate", "protection", "knowledge",
    ]

BASE_DIR = Path(__file__).resolve().parent

GOD_NAME_PARTS_A = [
    "Ash", "Black", "Bright", "Crow", "Dawn", "Deep", "Glass", "Grave",
    "Iron", "Moon", "Red", "Salt", "Star", "Storm", "Thorn", "Veil", "Void",
]
GOD_NAME_PARTS_B = [
    "binder", "caller", "crown", "father", "forge", "hand", "keeper",
    "mother", "oracle", "saint", "seeker", "singer", "watcher", "wound",
]
FAVORED_TRAITS_BY_DOMAIN = {
    "order": ["just", "honorable", "disciplined"],
    "chaos": ["impulsive", "curious", "eccentric"],
    "war": ["brave", "ruthless", "ambitious"],
    "domination": ["cruel", "ambitious", "ruthless"],
    "trickery": ["cunning", "impulsive", "eccentric"],
    "growth": ["merciful", "curious", "patient"],
    "decay": ["brooding", "cruel", "ruthless"],
    "fate": ["patient", "disciplined", "curious"],
    "protection": ["just", "merciful", "brave"],
    "knowledge": ["curious", "disciplined", "patient"],
}

FAVORED_CLASSES_BY_DOMAIN = {
    "order": ["Fighter", "Warden"],
    "chaos": ["Bard", "Wizard"],
    "war": ["Fighter", "Warden"],
    "domination": ["Fighter", "Wizard"],
    "trickery": ["Bard", "Wizard"],
    "growth": ["Warden", "Bard"],
    "decay": ["Wizard", "Fighter"],
    "fate": ["Wizard", "Bard"],
    "protection": ["Warden", "Fighter"],
    "knowledge": ["Wizard", "Bard"],
}
VALID_CLASSES = ["Fighter", "Wizard", "Warden", "Bard"]

DISFAVORED_TRAITS_BY_DOMAIN = {
    "order": ["impulsive", "cruel"],
    "chaos": ["disciplined", "patient"],
    "war": ["cowardly", "merciful"],
    "domination": ["merciful", "just"],
    "trickery": ["honorable", "disciplined"],
    "growth": ["cruel", "brooding"],
    "decay": ["merciful", "just"],
    "fate": ["impulsive", "ambitious"],
    "protection": ["cruel", "ruthless"],
    "knowledge": ["impulsive", "cruel"],
}


@dataclass
class ImmortalSeed:
    name: str
    alignment: str = "True Neutral"
    domains: list[str] = field(default_factory=list)
    favored_traits: list[str] = field(default_factory=list)
    disfavored_traits: list[str] = field(default_factory=list)
    conversion_bias: float = 1.0
    order_modifier: float = 0.0
    volatility_modifier: float = 0.0
    description: str = ""
    is_player_god: bool = False
    color: str = "white"
    starting_souls: int = 0
    profile_id: str = ""
    source: str = "fantgg"
    version: int = 2
    favored_classes: list[str] = field(default_factory=list)
    active_for_run: bool = False


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "unknown"


def split_csv(raw: Optional[str]) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def parse_alignment(value: Optional[str]) -> str:
    if value is None:
        return "True Neutral"
    raw = value.strip()
    lookup = {item.lower(): item for item in VALID_ALIGNMENTS}
    found = lookup.get(raw.lower())
    if found is None:
        raise argparse.ArgumentTypeError(f"Unknown alignment {value!r}.")
    return found


def parse_domains(values: Optional[Iterable[str]]) -> list[str]:
    picked: list[str] = []
    for value in values or []:
        for item in split_csv(value.lower()):
            if item not in VALID_DOMAINS:
                raise argparse.ArgumentTypeError(f"Unknown domain {item!r}. Valid domains: {', '.join(VALID_DOMAINS)}")
            if item not in picked:
                picked.append(item)
    return picked


def parse_classes(values: Optional[Iterable[str]]) -> list[str]:
    picked: list[str] = []
    lookup = {item.lower(): item for item in VALID_CLASSES}
    for value in values or []:
        for item in split_csv(value):
            found = lookup.get(item.lower())
            if found is None:
                raise argparse.ArgumentTypeError(f"Unknown class {item!r}. Valid classes: {', '.join(VALID_CLASSES)}")
            if found not in picked:
                picked.append(found)
    return picked


def default_favored_classes(domains: list[str]) -> list[str]:
    favored: list[str] = []
    for domain in domains:
        for role in FAVORED_CLASSES_BY_DOMAIN.get(domain, []):
            if role not in favored:
                favored.append(role)
    return favored[:1] or ["Fighter"]


def parse_color(value: Optional[str], *, is_player: bool = False) -> str:
    if is_player:
        return "magenta"
    raw = str(value or "white").strip().lower()
    aliases = {"purple": "magenta", "pink": "magenta", "grey": "white", "none": "white", "default": "white"}
    raw = aliases.get(raw, raw)
    allowed = {"white", "blue", "magenta", "yellow", "red", "green"}
    if raw not in allowed:
        raise argparse.ArgumentTypeError(f"Unknown color {value!r}. Use white, blue, magenta, yellow, red, or green.")
    return raw


def unique_imrt_path(out_dir: Path, god: ImmortalSeed) -> Path:
    prefix = "player" if god.is_player_god else "immortal"
    stem = f"{prefix}+{slugify(god.name)}"
    candidate = out_dir / f"{stem}.imrt"
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{stem}_{counter}.imrt"
        counter += 1
    return candidate


def random_name(rng: random.Random) -> str:
    return f"{rng.choice(GOD_NAME_PARTS_A)} {rng.choice(GOD_NAME_PARTS_B).title()}"


def default_traits(domains: list[str]) -> tuple[list[str], list[str]]:
    favored: list[str] = []
    disfavored: list[str] = []
    for domain in domains:
        for trait in FAVORED_TRAITS_BY_DOMAIN.get(domain, []):
            if trait not in favored:
                favored.append(trait)
        for trait in DISFAVORED_TRAITS_BY_DOMAIN.get(domain, []):
            if trait not in disfavored and trait not in favored:
                disfavored.append(trait)
    return favored[:4], disfavored[:4]


def make_immortal(
    *,
    rng: random.Random,
    name: Optional[str] = None,
    alignment: str = "True Neutral",
    domains: Optional[list[str]] = None,
    favored_traits: Optional[list[str]] = None,
    disfavored_traits: Optional[list[str]] = None,
    conversion_bias: float = 1.0,
    order_modifier: Optional[float] = None,
    volatility_modifier: Optional[float] = None,
    description: str = "",
    is_player_god: bool = False,
    color: str = "white",
    starting_souls: int = 0,
    favored_classes: Optional[list[str]] = None,
    active_for_run: bool = False,
) -> ImmortalSeed:
    domains = list(domains or [])
    if not domains:
        domains = [rng.choice(VALID_DOMAINS)]
    if len(domains) > 3:
        domains = domains[:3]

    if order_modifier is None:
        if "order" in domains or "protection" in domains:
            order_modifier = 0.20
        elif "chaos" in domains or "decay" in domains or "domination" in domains:
            order_modifier = -0.20
        else:
            order_modifier = 0.0
    if volatility_modifier is None:
        if "chaos" in domains or "trickery" in domains or "fate" in domains:
            volatility_modifier = 0.25
        elif "order" in domains or "protection" in domains:
            volatility_modifier = -0.10
        else:
            volatility_modifier = 0.0

    auto_favored, auto_disfavored = default_traits(domains)
    favored_classes = favored_classes if favored_classes is not None else default_favored_classes(domains)
    favored_traits = favored_traits if favored_traits is not None else auto_favored
    disfavored_traits = disfavored_traits if disfavored_traits is not None else auto_disfavored

    resolved_name = (name or random_name(rng)).strip()
    resolved_color = parse_color(color, is_player=is_player_god)

    return ImmortalSeed(
        name=resolved_name,
        alignment=alignment,
        domains=domains,
        favored_traits=favored_traits,
        disfavored_traits=disfavored_traits,
        conversion_bias=float(conversion_bias),
        order_modifier=float(order_modifier),
        volatility_modifier=float(volatility_modifier),
        description=description.strip(),
        is_player_god=bool(is_player_god),
        color=resolved_color,
        starting_souls=max(0, int(starting_souls)),
        profile_id=slugify(resolved_name).lower(),
        favored_classes=favored_classes,
        active_for_run=bool(active_for_run),
    )


def write_imrt(path: Path, god: ImmortalSeed) -> None:
    cfg = configparser.ConfigParser()
    cfg.optionxform = str

    cfg["seed"] = {
        "version": str(god.version),
        "source": god.source,
    }
    cfg["identity"] = {
        "id": god.profile_id,
        "name": god.name,
        "alignment": god.alignment,
        "domain": ", ".join(god.domains),
        "color": god.color,
        "is_player_god": str(god.is_player_god).lower(),
        "active_for_run": str(god.active_for_run).lower(),
    }
    cfg["power"] = {
        "starting_souls": str(god.starting_souls),
        "conversion_bias": f"{god.conversion_bias:.3f}",
        "order_modifier": f"{god.order_modifier:.3f}",
        "volatility_modifier": f"{god.volatility_modifier:.3f}",
    }
    cfg["traits"] = {
        "favored": ", ".join(god.favored_traits),
        "disfavored": ", ".join(god.disfavored_traits),
    }
    cfg["champion_rules"] = {
        "favored_classes": ", ".join(god.favored_classes),
        "favored_traits": ", ".join(god.favored_traits),
        "disfavored_traits": ", ".join(god.disfavored_traits),
        "champion_bias": "1.000",
    }
    cfg["description"] = {
        "text": god.description or f"An immortal power of {', '.join(god.domains)}.",
    }

    with path.open("w", encoding="utf-8") as handle:
        cfg.write(handle)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantgg",
        description="Fantasy Antfarm God Generator (.imrt immortal seed files).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("count", nargs="?", type=int, default=1, help="Number of .imrt files to generate (default: 1).")
    parser.add_argument("--seed", default=None, help="RNG seed for repeatable generation.")
    parser.add_argument("--out", default="MCE", help="Output directory for .imrt files (default: MCE).")
    parser.add_argument("--name", default=None, help="Force immortal name. Only valid when count=1.")
    parser.add_argument("-a", "--alignment", type=parse_alignment, default="True Neutral", help='Force alignment, e.g. "Chaotic Neutral".')
    parser.add_argument("-d", "--domain", action="append", default=None, help=f"Add domain. May be comma-separated or repeated. Valid: {', '.join(VALID_DOMAINS)}")
    parser.add_argument("--favored-trait", action="append", default=None, help="Favored trait. May be repeated; defaults from domain.")
    parser.add_argument("--disfavored-trait", action="append", default=None, help="Disfavored trait. May be repeated; defaults from domain.")
    parser.add_argument("--favored-class", action="append", default=None, help="Favored champion class. Only the first value is used. Valid: Fighter, Wizard, Warden, Bard. Defaults from domain.")
    parser.add_argument("--conversion-bias", type=float, default=1.0, help="Conversion bias modifier (default: 1.0).")
    parser.add_argument("--order-modifier", type=float, default=None, help="Order pressure modifier. Defaults from domain.")
    parser.add_argument("--volatility-modifier", type=float, default=None, help="Volatility modifier. Defaults from domain.")
    parser.add_argument("--starting-souls", type=int, default=0, help="Starting soul budget/currency (default: 0).")
    parser.add_argument("--player", action="store_true", help="Mark this immortal as the single player god. Forces color=magenta.")
    parser.add_argument("--active-for-run", action="store_true", help="Mark generated god as active for the next run.")
    parser.add_argument("--color", default="white", help="Custom non-player UX color: white or blue are recommended. Player gods are always magenta.")
    parser.add_argument("--description", default="", help="Profile description text.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.count < 1:
        parser.error("count must be at least 1")
    if args.name and args.count != 1:
        parser.error("--name can only be used when count=1")
    if args.player and args.count != 1:
        parser.error("--player can only be used when count=1")

    domains = parse_domains(args.domain)
    favored = split_csv(",".join(args.favored_trait or [])) if args.favored_trait else None
    disfavored = split_csv(",".join(args.disfavored_trait or [])) if args.disfavored_trait else None
    favored_classes = parse_classes(args.favored_class)[:1]

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    created: list[Path] = []
    for _ in range(args.count):
        god = make_immortal(
            rng=rng,
            name=args.name,
            alignment=args.alignment,
            domains=domains,
            favored_traits=favored,
            disfavored_traits=disfavored,
            conversion_bias=args.conversion_bias,
            order_modifier=args.order_modifier,
            volatility_modifier=args.volatility_modifier,
            description=args.description,
            is_player_god=args.player,
            color=args.color,
            starting_souls=args.starting_souls,
            favored_classes=favored_classes or None,
            active_for_run=args.active_for_run,
        )
        path = unique_imrt_path(out_dir, god)
        write_imrt(path, god)
        created.append(path)

    for path in created:
        print(path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
