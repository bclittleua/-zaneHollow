from __future__ import annotations

"""fantrg_v1.py - Fantasy Antfarm relic generator rules.

Shared by start_game, curses UX, and the simulator.  This module intentionally
contains no curses/game-loop code.  It defines the legal created-relic universe,
boon descriptions, tier stats/costs, and simple validation helpers.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

try:
    from FASEcfg import (
        LESSER_RELIC_SOUL_COST,
        GREATER_RELIC_SOUL_COST,
        PLAYER_LESSER_RELIC_LIMIT,
        PLAYER_GREATER_RELIC_LIMIT,
    )
except Exception:
    LESSER_RELIC_SOUL_COST = 75
    GREATER_RELIC_SOUL_COST = 125
    PLAYER_LESSER_RELIC_LIMIT = 2
    PLAYER_GREATER_RELIC_LIMIT = 1


@dataclass(frozen=True)
class RelicTemplate:
    key: str
    label: str
    relic_type: str
    slot: str
    allowed_roles: tuple[str, ...]
    description: str

    def allows_role(self, role: object) -> bool:
        if "any" in self.allowed_roles:
            return True
        value = getattr(role, "value", str(role))
        return value in self.allowed_roles or str(role) in self.allowed_roles


CREATED_RELIC_TEMPLATES: Dict[str, RelicTemplate] = {
    "sword": RelicTemplate("sword", "Sword", "sword", "weapon", ("any",), "A universal champion weapon."),
    "shield": RelicTemplate("shield", "Shield", "shield", "offhand", ("any",), "A universal champion shield."),
    "axe": RelicTemplate("axe", "Axe", "axe", "weapon", ("Fighter",), "A fighter's brutal divine weapon."),
    "bow": RelicTemplate("bow", "Bow", "bow", "weapon", ("Warden",), "A warden's divine hunting weapon."),
    "staff": RelicTemplate("staff", "Staff", "staff", "weapon", ("Wizard",), "A wizard's divine focus weapon."),
    "rapier": RelicTemplate("rapier", "Rapier", "rapier", "weapon", ("Bard",), "A bard's precise divine weapon."),
    "heavy_armor_set": RelicTemplate("heavy_armor_set", "Heavy Armor Set", "heavy_armor_set", "armor", ("Fighter",), "A fighter's complete heavy armor set."),
    "medium_armor_set": RelicTemplate("medium_armor_set", "Medium Armor Set", "medium_armor_set", "armor", ("Bard",), "A bard's complete medium armor set."),
    "light_armor_set": RelicTemplate("light_armor_set", "Light Armor Set", "light_armor_set", "armor", ("Warden",), "A warden's complete light armor set."),
}

BOON_DEFS: Dict[str, dict] = {
    "might": {"stat": "strength", "label": "Might", "description": "+Strength / melee power"},
    "grace": {"stat": "dexterity", "label": "Grace", "description": "+Dexterity / accuracy / evasion"},
    "endurance": {"stat": "constitution", "label": "Endurance", "description": "+Constitution / HP / toughness"},
    "insight": {"stat": "wisdom", "label": "Insight", "description": "+Wisdom / magic / judgment"},
    "fortune": {"stat": "luck", "label": "Fortune", "description": "+Luck / favorable outcomes"},
    "resolve": {"stat": "charisma", "label": "Resolve", "description": "+Charisma / morale / leadership"},
}

TIER_DEFS = {
    "lesser": {
        "label": "Lesser",
        "cost": LESSER_RELIC_SOUL_COST,
        "limit": PLAYER_LESSER_RELIC_LIMIT,
        "power_bonus": 3,
        "reputation_bonus": 5,
        "boon_amount": 2,
    },
    "greater": {
        "label": "Greater",
        "cost": GREATER_RELIC_SOUL_COST,
        "limit": PLAYER_GREATER_RELIC_LIMIT,
        "power_bonus": 6,
        "reputation_bonus": 10,
        "boon_amount": 4,
    },
}


def normalize_tier(tier: str) -> str:
    key = str(tier or "lesser").strip().lower()
    if key not in TIER_DEFS:
        raise ValueError(f"Unknown relic tier: {tier!r}")
    return key


def valid_templates_for_role(role: object) -> list[RelicTemplate]:
    return [template for template in CREATED_RELIC_TEMPLATES.values() if template.allows_role(role)]


def template_label(template_key: str) -> str:
    return CREATED_RELIC_TEMPLATES[template_key].label


def boon_label(boon_key: str) -> str:
    return BOON_DEFS[str(boon_key).strip().lower()]["label"]


def relic_limit_text() -> str:
    return f"You are only allowed {PLAYER_LESSER_RELIC_LIMIT} lesser and {PLAYER_GREATER_RELIC_LIMIT} greater relics this game."


def build_relic_payload(*, name: str, template_key: str, tier: str, boon_key: str, creator_deity: object, original_recipient_id: Optional[int] = None) -> dict:
    tier_key = normalize_tier(tier)
    template = CREATED_RELIC_TEMPLATES[template_key]
    boon = BOON_DEFS[str(boon_key).strip().lower()]
    tier_info = TIER_DEFS[tier_key]
    display_name = str(name or "Unnamed Relic").strip() or "Unnamed Relic"
    return {
        "name": display_name,
        "type": template.relic_type,
        "slot": template.slot,
        "template_key": template.key,
        "template_label": template.label,
        "tier": tier_key,
        "power_bonus": int(tier_info["power_bonus"]),
        "reputation_bonus": int(tier_info["reputation_bonus"]),
        "boon_label": str(boon_key).strip().lower(),
        "boon_stat": boon["stat"],
        "boon_amount": int(tier_info["boon_amount"]),
        "creator_deity": getattr(creator_deity, "value", getattr(creator_deity, "name", str(creator_deity))),
        "original_recipient_id": "" if original_recipient_id is None else str(original_recipient_id),
        "description": f"A {tier_info['label'].lower()} divine {template.label.lower()} bearing {boon['label']}.",
    }
