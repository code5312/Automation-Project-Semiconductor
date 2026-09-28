"""One-off migration of existing output/events/*.json files into SQLite."""
import json
from pathlib import Path

from src.storage.repository import save_event


def migrate_json_dir(json_dir: str | Path, db_path: str | Path) -> int:
    """Load every *.json file in `json_dir` and upsert it into `db_path`.
    Returns the number of events migrated."""
    json_dir = Path(json_dir)
    count = 0
    for path in sorted(json_dir.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            event = json.load(f)
        save_event(db_path, event)
        count += 1
    return count
