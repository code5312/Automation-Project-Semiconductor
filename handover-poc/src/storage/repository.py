"""SQLite persistence for generated events.

Events are still plain dicts assembled by src/cli.py's build_event();
this module only adds a storage layer on top of that -- signal extraction,
scenario sampling and diagnosis logic never depend on this module, so a
future web layer can reuse both independently.

Each event is stored twice: as indexed columns for filtering (scenario_id,
primary_dept, etc., used by list_events) and as a raw_json blob for full
fidelity (used by get_event) -- the columns are a query index, not the
source of truth.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    seed INTEGER NOT NULL,
    is_simulated INTEGER NOT NULL,
    event_time TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    primary_dept TEXT,
    mfg_hold INTEGER NOT NULL,
    vision_pattern_group TEXT NOT NULL,
    sensor_anomaly_score REAL NOT NULL,
    vibration_mode TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_scenario ON events(scenario_id);
CREATE INDEX IF NOT EXISTS idx_events_primary_dept ON events(primary_dept);
CREATE INDEX IF NOT EXISTS idx_events_event_time ON events(event_time);
"""


@contextmanager
def _connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    """Create the events table (and indexes) if they don't already exist."""
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)


def _row_from_event(event: dict) -> tuple:
    diagnosis = event["diagnosis"]
    signals = event["signals"]
    return (
        event["event_id"],
        event["scenario_id"],
        event["seed"],
        1 if event["is_simulated"] else 0,
        event["event_time"],
        diagnosis["rule_id"],
        diagnosis["primary_dept"],
        1 if diagnosis["mfg_hold"] else 0,
        signals["vision"]["pattern_group"],
        signals["sensor"]["anomaly_score"],
        signals["vibration"]["mode"],
        json.dumps(event, ensure_ascii=False),
    )


def save_event(db_path: str | Path, event: dict) -> None:
    """Insert one event, or overwrite it in place if event_id already exists."""
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO events (
                event_id, scenario_id, seed, is_simulated, event_time,
                rule_id, primary_dept, mfg_hold, vision_pattern_group,
                sensor_anomaly_score, vibration_mode, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                scenario_id=excluded.scenario_id,
                seed=excluded.seed,
                is_simulated=excluded.is_simulated,
                event_time=excluded.event_time,
                rule_id=excluded.rule_id,
                primary_dept=excluded.primary_dept,
                mfg_hold=excluded.mfg_hold,
                vision_pattern_group=excluded.vision_pattern_group,
                sensor_anomaly_score=excluded.sensor_anomaly_score,
                vibration_mode=excluded.vibration_mode,
                raw_json=excluded.raw_json
            """,
            _row_from_event(event),
        )


def get_event(db_path: str | Path, event_id: str) -> Optional[dict]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT raw_json FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return json.loads(row[0]) if row else None


def list_events(
    db_path: str | Path,
    scenario_id: Optional[str] = None,
    primary_dept: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Most recent events first, optionally filtered by scenario_id/primary_dept."""
    query = "SELECT raw_json FROM events"
    conditions = []
    params: list = []
    if scenario_id is not None:
        conditions.append("scenario_id = ?")
        params.append(scenario_id)
    if primary_dept is not None:
        conditions.append("primary_dept = ?")
        params.append(primary_dept)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY event_time DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [json.loads(r[0]) for r in rows]


def count_events(db_path: str | Path) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    return row[0] if row else 0
