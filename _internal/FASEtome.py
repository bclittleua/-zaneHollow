from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence


@dataclass
class ArchivedEvent:
    tick: int
    timestamp: str
    text: str
    importance: int = 1
    category: str = "general"
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    time_of_day: str = ""
    season: str = ""


class Historian:
    """Authoritative SQLite event archive for a Fantfarm run.

    world.events should be treated as a small recent-event UI buffer. The
    historian stores the full event stream and exposes light query helpers for
    summaries and tools.
    """

    SCHEMA_VERSION = 2
    MONTH_NAMES = [
        "Dawnsreach", "Rainmoot", "Bloomtide", "Suncrest", "Goldfire", "Highsun",
        "Harvestwane", "Emberfall", "Duskmarch", "Frostburn", "Deepcold", "Yearsend",
    ]

    def __init__(self, path, *, flush_event_count: int = 500, timeout: float = 30.0) -> None:
        self.path = Path(path)
        self.flush_event_count = max(1, int(flush_event_count or 500))
        self.timeout = float(timeout or 30.0)
        self._conn: Optional[sqlite3.Connection] = None
        self._pending: list[tuple] = []
        self._events_seen = 0
        self._open()
        self._events_seen = self._count_events_committed()

    def __getstate__(self):
        self.flush()
        state = dict(self.__dict__)
        state["_conn"] = None
        state["_pending"] = []
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._conn = None
        self._pending = []
        self._open()
        self._events_seen = max(int(getattr(self, "_events_seen", 0) or 0), self._count_events_committed())

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._open()
        assert self._conn is not None
        return self._conn

    def _execute_and_close(self, sql: str, params: Sequence[object] = ()) -> None:
        """Execute a SQLite statement and explicitly drain/close its cursor.

        CPython's sqlite3 usually finalizes short-lived cursors quickly enough
        that commits after PRAGMA/DDL statements work even if the cursor object is
        not assigned. PyPy can keep those statements alive longer, which raises
        "cannot commit transaction - SQL statements in progress". Explicitly
        draining and closing keeps behavior identical while making the historian
        portable across interpreters.
        """
        conn = self._conn
        if conn is None:
            return
        cur = conn.execute(sql, tuple(params))
        try:
            try:
                cur.fetchall()
            except sqlite3.ProgrammingError:
                pass
        finally:
            cur.close()

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=self.timeout)
        self._conn.row_factory = sqlite3.Row
        self._execute_and_close("PRAGMA journal_mode=WAL")
        self._execute_and_close("PRAGMA synchronous=NORMAL")
        self._execute_and_close("PRAGMA temp_store=MEMORY")
        self._create_schema()

    def _create_schema(self) -> None:
        conn = self._conn
        if conn is None:
            return
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tick INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                year INTEGER,
                month INTEGER,
                day INTEGER,
                time_of_day TEXT,
                season TEXT,
                category TEXT,
                importance INTEGER,
                text TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick);
            CREATE INDEX IF NOT EXISTS idx_events_category_tick ON events(category, tick);
            CREATE INDEX IF NOT EXISTS idx_events_importance_tick ON events(importance, tick);

            INSERT OR REPLACE INTO meta(key, value)
            VALUES('schema_version', '{self.SCHEMA_VERSION}');
            """
        )
        conn.commit()

    def _count_events_committed(self) -> int:
        try:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
            return int(row["n"] if row else 0)
        except Exception:
            return 0

    @classmethod
    def _date_parts_from_timestamp(cls, timestamp: str):
        year = month = day = None
        season = time_of_day = ""
        try:
            parts = [part.strip() for part in str(timestamp or "").split(",")]
            if len(parts) >= 4:
                if parts[0].lower().startswith("year"):
                    year = int(parts[0].split()[1])
                season = parts[1]
                md = parts[2].split()
                if len(md) >= 2:
                    month_name = md[0]
                    day = int(md[1])
                    month = cls.MONTH_NAMES.index(month_name) + 1 if month_name in cls.MONTH_NAMES else None
                time_of_day = parts[3]
        except Exception:
            pass
        return year, month, day, time_of_day, season

    def record_event(self, event) -> None:
        timestamp = str(getattr(event, "timestamp", "") or "")
        year, month, day, time_of_day, season = self._date_parts_from_timestamp(timestamp)
        self._pending.append((
            int(getattr(event, "tick", 0) or 0),
            timestamp,
            year,
            month,
            day,
            time_of_day,
            season,
            str(getattr(event, "category", "") or "general"),
            int(getattr(event, "importance", 1) or 1),
            str(getattr(event, "text", "") or ""),
        ))
        self._events_seen += 1
        if len(self._pending) >= self.flush_event_count:
            self.flush()

    def record_events(self, events: Iterable) -> int:
        count = 0
        for event in events:
            self.record_event(event)
            count += 1
        return count

    def flush(self) -> None:
        if not self._pending:
            return
        rows = self._pending
        self._pending = []
        self.conn.executemany(
            """
            INSERT INTO events(
                tick, timestamp, year, month, day, time_of_day, season, category, importance, text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def close(self) -> None:
        self.flush()
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def event_count(self, *, include_pending: bool = True) -> int:
        return int(self._events_seen if include_pending else self._count_events_committed())

    def pending_count(self) -> int:
        return len(self._pending)

    def _rows_to_events(self, rows: Sequence[sqlite3.Row]) -> list[ArchivedEvent]:
        return [
            ArchivedEvent(
                tick=int(row["tick"]),
                timestamp=str(row["timestamp"]),
                year=row["year"],
                month=row["month"],
                day=row["day"],
                time_of_day=str(row["time_of_day"] or ""),
                season=str(row["season"] or ""),
                category=str(row["category"] or "general"),
                importance=int(row["importance"] or 1),
                text=str(row["text"] or ""),
            )
            for row in rows
        ]

    def recent_events(self, *, limit: int = 1000, min_importance: Optional[int] = None) -> list[ArchivedEvent]:
        self.flush()
        clauses = []
        params: list[object] = []
        if min_importance is not None:
            clauses.append("importance >= ?")
            params.append(int(min_importance))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM events {where} ORDER BY tick DESC, id DESC LIMIT ?",
            (*params, max(1, int(limit))),
        ).fetchall()
        return list(reversed(self._rows_to_events(rows)))

    def events_between(self, start_tick: int, end_tick: int, *, categories: Optional[Iterable[str]] = None, limit: Optional[int] = None) -> list[ArchivedEvent]:
        self.flush()
        clauses = ["tick >= ?", "tick <= ?"]
        params: list[object] = [int(start_tick), int(end_tick)]
        if categories:
            cats = [str(c) for c in categories]
            if cats:
                clauses.append("category IN (" + ",".join("?" for _ in cats) + ")")
                params.extend(cats)
        lim = ""
        if limit is not None:
            lim = " LIMIT ?"
            params.append(max(1, int(limit)))
        rows = self.conn.execute(
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY tick ASC, id ASC{lim}",
            params,
        ).fetchall()
        return self._rows_to_events(rows)

    def events_by_category(self, categories: Iterable[str], *, limit: int = 100, start_tick: Optional[int] = None, end_tick: Optional[int] = None) -> list[ArchivedEvent]:
        self.flush()
        cats = [str(c) for c in categories]
        if not cats:
            return []
        clauses = ["category IN (" + ",".join("?" for _ in cats) + ")"]
        params: list[object] = cats[:]
        if start_tick is not None:
            clauses.append("tick >= ?")
            params.append(int(start_tick))
        if end_tick is not None:
            clauses.append("tick <= ?")
            params.append(int(end_tick))
        rows = self.conn.execute(
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY tick DESC, id DESC LIMIT ?",
            (*params, max(1, int(limit))),
        ).fetchall()
        return list(reversed(self._rows_to_events(rows)))

    def story_events(self, kind: str = "mythic", *, limit: int = 100) -> list[ArchivedEvent]:
        """Return event material suitable for bardic rediscovery.

        This is intentionally broad and text-based. Lore decides whether an event
        becomes love, folly, or mythic material; the tome only supplies old
        civilizational memory.
        """
        kind = str(kind or "mythic").lower()
        if kind == "love":
            categories = {"marriage", "legacy_birth", "succession", "diplomacy"}
        elif kind == "folly":
            categories = {"party_coup", "party_split", "polity_challenge", "succession", "corruption", "notable_death"}
        else:
            categories = {"legendary_monster_kill", "champion_death", "notable_death", "necromancer_crisis", "polity", "deification"}
        return self.events_by_category(categories, limit=limit)


    def search_events(self, text: str, *, limit: int = 100) -> list[ArchivedEvent]:
        self.flush()
        needle = f"%{str(text or '').strip()}%"
        if needle == "%%":
            return self.recent_events(limit=limit)
        rows = self.conn.execute(
            "SELECT * FROM events WHERE text LIKE ? ORDER BY tick DESC, id DESC LIMIT ?",
            (needle, max(1, int(limit))),
        ).fetchall()
        return list(reversed(self._rows_to_events(rows)))

    def summary_events(self, *, current_tick: Optional[int] = None, lookback_ticks: Optional[int] = None, limit: int = 5000) -> list[ArchivedEvent]:
        self.flush()
        if current_tick is not None and lookback_ticks is not None and lookback_ticks > 0:
            start = max(0, int(current_tick) - int(lookback_ticks))
            return self.events_between(start, int(current_tick), limit=limit)
        return self.recent_events(limit=limit)


def tome_path(output_dir, *, seed_name: str, timestamp: str) -> Path:
    safe_seed = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(seed_name or "seed"))
    safe_seed = safe_seed.strip("._") or "seed"
    safe_stamp = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(timestamp or "run"))
    safe_stamp = safe_stamp.strip("._") or "run"
    return Path(output_dir) / f"{safe_seed}_tome_{safe_stamp}.sqlite"
