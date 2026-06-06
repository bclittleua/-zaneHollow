from __future__ import annotations

"""morgue_v4.py - SQLite archive for dead Fantasy Antfarm actors.

The database stores full actor data. Runtime memory only needs tiny search tags:
    {id, name, role}

Intended path:
    GAMEBASE/seedRuns_vX/<seed>/morgue_<seed>_<realworld_timestamp>.sqlite
"""

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import enum
import importlib
import json
import sqlite3


def safe_filename_component(value: Any, fallback: str = "seed") -> str:
    text = str(value or fallback)
    text = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
    return text.strip("._") or fallback


def realworld_timestamp() -> str:
    """Return a filesystem-safe real-world timestamp for run-start naming."""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def morgue_path(seed_dir: str | Path, seed_name: str = "seed", timestamp: str | None = None) -> Path:
    """Return GAMEBASE/seedRuns_vX/<seed>/morgue_<seed>_<timestamp>.sqlite."""
    seed_path = Path(seed_dir)
    seed_path.mkdir(parents=True, exist_ok=True)
    safe_seed = safe_filename_component(seed_name)
    stamp = safe_filename_component(timestamp or realworld_timestamp(), fallback="run")
    return seed_path / f"morgue_{safe_seed}_{stamp}.sqlite"


# Backward-compatible alias for old code/saves. New code should use morgue_path().
def mortuary_path(seed_dir: str | Path, day: int | None = None, month: int | None = None, year: int | None = None, *, seed_name: str = "seed", timestamp: str | None = None) -> Path:
    return morgue_path(seed_dir, seed_name=seed_name, timestamp=timestamp)



def _enum_to_data(value: enum.Enum) -> dict:
    return {
        "__enum__": True,
        "module": value.__class__.__module__,
        "class": value.__class__.__name__,
        "name": value.name,
        "value": value.value,
    }


def _object_to_data(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return _enum_to_data(value)
    if isinstance(value, Path):
        return {"__path__": str(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_object_to_data(v) for v in value]
    if isinstance(value, tuple):
        return {"__tuple__": [_object_to_data(v) for v in value]}
    if isinstance(value, set):
        return {"__set__": [_object_to_data(v) for v in value]}
    if isinstance(value, dict):
        return {"__dict__": [[_object_to_data(k), _object_to_data(v)] for k, v in value.items()]}
    # Custom deity/profile objects are not safely reconstructable here. Preserve
    # their display identity instead of exploding JSON serialization.
    if hasattr(value, "value") or hasattr(value, "name"):
        return {
            "__object_ref__": True,
            "module": value.__class__.__module__,
            "class": value.__class__.__name__,
            "value": getattr(value, "value", getattr(value, "name", str(value))),
        }
    return {"__repr__": repr(value)}


def _data_to_object(value: Any) -> Any:
    if isinstance(value, list):
        return [_data_to_object(v) for v in value]
    if not isinstance(value, dict):
        return value
    if value.get("__enum__"):
        try:
            module = importlib.import_module(value["module"])
            enum_class = getattr(module, value["class"])
            return enum_class[value["name"]]
        except Exception:
            return value.get("value")
    if "__path__" in value:
        return Path(value["__path__"])
    if "__tuple__" in value:
        return tuple(_data_to_object(v) for v in value["__tuple__"])
    if "__set__" in value:
        return set(_data_to_object(v) for v in value["__set__"])
    if "__dict__" in value:
        return {_data_to_object(k): _data_to_object(v) for k, v in value["__dict__"]}
    if value.get("__object_ref__"):
        return value.get("value")
    if "__repr__" in value:
        return value["__repr__"]
    return {k: _data_to_object(v) for k, v in value.items()}


def actor_to_dict(actor: Any) -> dict:
    """Serialize dataclass fields plus dynamic attrs from an Actor-like object."""
    data: Dict[str, Any] = {}
    if is_dataclass(actor):
        for f in fields(actor):
            data[f.name] = _object_to_data(getattr(actor, f.name))
    for key, value in getattr(actor, "__dict__", {}).items():
        if key not in data:
            data[key] = _object_to_data(value)
    return data


def actor_from_dict(data: dict, actor_class: type) -> Any:
    """Rebuild an actor instance from serialized data."""
    restored = {key: _data_to_object(value) for key, value in data.items()}
    if is_dataclass(actor_class):
        field_names = {f.name for f in fields(actor_class)}
        init_kwargs = {k: v for k, v in restored.items() if k in field_names}
        actor = actor_class(**init_kwargs)
        for key, value in restored.items():
            if key not in field_names:
                setattr(actor, key, value)
        return actor
    actor = actor_class.__new__(actor_class)
    actor.__dict__.update(restored)
    return actor


class Morgue:
    def __init__(self, path: str | Path, actor_class: Optional[type] = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.actor_class = actor_class
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS actors (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    data TEXT NOT NULL
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_actors_name ON actors(name)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_actors_role ON actors(role)")
            db.commit()

    @staticmethod
    def tombstone_for(actor: Any) -> dict:
        role_obj = getattr(actor, "role", "")
        role = getattr(role_obj, "value", getattr(role_obj, "name", role_obj))
        alignment_obj = getattr(actor, "alignment", "")
        alignment_name = getattr(alignment_obj, "name", None)
        alignment_value = getattr(alignment_obj, "value", alignment_obj)
        name = actor.short_name() if hasattr(actor, "short_name") else f"{getattr(actor, 'name', '')} {getattr(actor, 'surname', '')}".strip()
        full_name = actor.full_name() if hasattr(actor, "full_name") else name

        def _label(value: Any) -> str | None:
            if value is None:
                return None
            return str(getattr(value, "value", getattr(value, "name", value)))

        def _safe_int(attr: str, default: int = 0) -> int:
            try:
                return int(getattr(actor, attr, default) or default)
            except Exception:
                return int(default)

        def _safe_bool(attr: str, default: bool = False) -> bool:
            try:
                return bool(getattr(actor, attr, default))
            except Exception:
                return bool(default)

        try:
            power_snapshot = int(actor.power_rating()) if hasattr(actor, "power_rating") else _safe_int("level", 1)
        except Exception:
            power_snapshot = _safe_int("level", 1)

        deeds = ""
        try:
            if hasattr(actor, "notable_deeds_summary"):
                deeds = str(actor.notable_deeds_summary() or "")
        except Exception:
            deeds = ""

        tomb = {
            "id": int(actor.id),
            "name": str(name),
            "full_name": str(full_name),
            "role": str(role),
            "role_name": str(getattr(role_obj, "name", role)).upper(),
            "alignment": str(alignment_value or ""),
            "alignment_name": str(alignment_name or alignment_value or "").upper(),
            "alive": bool(getattr(actor, "alive", False)),
            "retired": _safe_bool("retired", False),
            "level": _safe_int("level", 1),
            "experience": _safe_int("experience", 0),
            "reputation": _safe_int("reputation", 0),
            "kills": _safe_int("kills", 0),
            "monster_kills": _safe_int("monster_kills", 0),
            "dragon_kills": _safe_int("dragon_kills", 0),
            "horror_kills": _safe_int("horror_kills", 0),
            "regions_oppressed": _safe_int("regions_oppressed", 0),
            "power_rating": power_snapshot,
            "birth_day": getattr(actor, "birth_day", None),
            "birth_month": getattr(actor, "birth_month", None),
            "birth_year": getattr(actor, "birth_year", None),
            "death_timestamp": getattr(actor, "death_timestamp", None),
            "death_cause": getattr(actor, "death_cause", None),
            "region_id": getattr(actor, "region_id", None),
            "mother_id": getattr(actor, "mother_id", None),
            "father_id": getattr(actor, "father_id", None),
            "mother_label": getattr(actor, "mother_label", None),
            "father_label": getattr(actor, "father_label", None),
            "spouse_id": getattr(actor, "spouse_id", None),
            "best_friend_id": getattr(actor, "best_friend_id", None),
            "nemesis_id": getattr(actor, "nemesis_id", None),
            "friend_ids": list(getattr(actor, "friend_ids", []) or []),
            "notable_deeds": deeds,
        }
        # v4: keep enough display/stat data in the runtime index for summary
        # leaderboards. Summary should not hydrate full dead actors from SQLite
        # just to print top adventurer lists.
        champion_of = _label(getattr(actor, "champion_of", None))
        deity = _label(getattr(actor, "deity", None))
        if champion_of:
            tomb["champion_of"] = champion_of
        if deity:
            tomb["deity"] = deity
        return tomb

    def store_actor(self, actor: Any) -> dict:
        tombstone = self.tombstone_for(actor)
        payload = json.dumps(actor_to_dict(actor), ensure_ascii=False, separators=(",", ":"))
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO actors(id, name, role, data) VALUES (?, ?, ?, ?)",
                (tombstone["id"], tombstone["name"], tombstone["role"], payload),
            )
            db.commit()
        return tombstone

    def load_actor(self, actor_id: int, actor_class: Optional[type] = None) -> Any:
        cls = actor_class or self.actor_class
        if cls is None:
            raise ValueError("Morgue.load_actor requires actor_class or Morgue(actor_class=...).")
        with self._connect() as db:
            row = db.execute("SELECT data FROM actors WHERE id = ?", (int(actor_id),)).fetchone()
        if row is None:
            return None
        return actor_from_dict(json.loads(row[0]), cls)

    def search_index(self, query: str, limit: int = 50) -> list[dict]:
        q = str(query or "").strip().lower()
        if not q:
            return []
        tokens = [tok for tok in q.split() if tok]
        where = " AND ".join(["(lower(name) LIKE ? OR lower(role) LIKE ?)"] * len(tokens))
        params = []
        for tok in tokens:
            like = f"%{tok}%"
            params.extend([like, like])
        with self._connect() as db:
            rows = db.execute(
                f"SELECT id, name, role FROM actors WHERE {where} ORDER BY name LIMIT ?",
                (*params, int(limit)),
            ).fetchall()
        return [{"id": int(aid), "name": name, "role": role} for aid, name, role in rows]

    def story_candidate_index(self, *, limit: int = 100, min_reputation: int = 0) -> list[dict]:
        """Return lightweight dead-actor candidates for lore rediscovery.

        Full actor hydration remains the caller's responsibility. The morgue
        stores complete JSON payloads, but this method only returns compact
        fields so lore can sample without dragging the entire archive into RAM.
        """
        rows_out = []
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, name, role, data FROM actors ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        for aid, name, role, payload in rows:
            rep = 0
            level = 1
            try:
                data = json.loads(payload)
                rep = int(data.get("reputation", 0) or 0)
                level = int(data.get("level", 1) or 1)
            except Exception:
                pass
            if rep < int(min_reputation or 0):
                continue
            rows_out.append({"id": int(aid), "name": name, "role": role, "reputation": rep, "level": level})
        rows_out.sort(key=lambda item: (int(item.get("reputation", 0)), int(item.get("level", 1))), reverse=True)
        return rows_out[:max(1, int(limit))]


    def actor_exists(self, actor_id: int) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM actors WHERE id = ? LIMIT 1", (int(actor_id),)).fetchone()
        return row is not None


# Backward-compatible alias for old imports/saves.
Mortuary = Morgue
