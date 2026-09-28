"""CLI entry point.

    python -m src.cli generate --scenario SC-EQ --seed 42 --out output/events/
    python -m src.cli validate --event-file output/events/EVT-xxxx.json
    python -m src.cli batch --seeds 50 --out output/experiments/
    python -m src.cli migrate --events-dir output/events --db output/handover.db
    python -m src.cli list --db output/handover.db --scenario SC-EQ
    python -m src.cli handover --event-id EVT-xxxx --to M-ENG --reason "..."
    python -m src.cli history --event-id EVT-xxxx
"""
import json
import random
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import yaml

from src.diagnosis.engine import diagnose
from src.ingest import validate as validate_mod
from src.models import Diagnosis, Event, SensorSignal, TopSensor, VibrationSignal, VisionSignal
from src.scenarios.catalog import SamplingContext, build_sampling_context, sample
from src.storage import repository as repo
from src.storage.migrate import migrate_json_dir

RULES_PATH = Path("config/rules.yaml")
DEFAULT_DB_PATH = "output/handover.db"


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _event_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"EVT-{ts}-{suffix}"


def _parse_ims_timestamp(filename: str) -> Optional[str]:
    """IMS filenames are the recording timestamp, e.g. '2004.02.12.10.32.39'."""
    try:
        return datetime.strptime(filename, "%Y.%m.%d.%H.%M.%S").isoformat()
    except ValueError:
        return None


def build_event(scenario_id: str, seed: int, ctx: SamplingContext, rules: dict) -> dict:
    """Pure(ish) event assembly: sample -> diagnose -> validate -> dict.

    Note on reproducibility: signals and diagnosis are fully deterministic
    for a given (scenario_id, seed). event_id/event_time are generation-time
    metadata (like a created_at timestamp) and are intentionally NOT
    reproduced between runs -- only the substance of the event is.
    """
    sampled = sample(scenario_id, seed, ctx)
    wafer = sampled["wafer_record"]

    vision = VisionSignal(
        source="WM-811K (LSWMD.pkl)",
        source_ref={
            "lotName": wafer["lotName"],
            "waferIndex": wafer["waferIndex"],
            "row": wafer.get("source_row"),
        },
        source_time=None,
        pattern=wafer["failureType"],
        pattern_group=wafer["pattern_group"],
    )

    sensor_sig = sampled["sensor_signal"]
    sensor = SensorSignal(
        source="UCI SECOM",
        source_ref={"row": sampled["sensor_row"]},
        source_time=sampled["sensor_time"],
        anomaly_score=sensor_sig["anomaly_score"],
        top_sensors=[TopSensor(**s) for s in sensor_sig["top_sensors"]],
    )

    vib_sig = sampled["vibration_signal"]
    vibration = VibrationSignal(
        source="NASA IMS Set 2, channel 1",
        source_ref={"file": vib_sig["file"], "order": vib_sig["order"]},
        source_time=_parse_ims_timestamp(vib_sig["file"]),
        mode=vib_sig["mode"],
        rms=vib_sig["rms"],
        health_index=vib_sig["health_index"],
        kurtosis=vib_sig.get("kurtosis"),
        crest_factor=vib_sig.get("crest_factor"),
        peak_to_peak=vib_sig.get("peak_to_peak"),
    )

    diag_result = diagnose(
        {"pattern": vision.pattern, "pattern_group": vision.pattern_group},
        {"anomaly_score": sensor.anomaly_score, "top_sensors": sensor_sig["top_sensors"]},
        {
            "mode": vibration.mode,
            "rms": vibration.rms,
            "health_index": vibration.health_index,
            "kurtosis": vibration.kurtosis,
            "crest_factor": vibration.crest_factor,
        },
        rules,
    )
    diagnosis = Diagnosis(**diag_result)

    event = Event(
        event_id=_event_id(),
        scenario_id=scenario_id,
        seed=seed,
        event_time=datetime.now(timezone.utc).isoformat(),
        vision=vision,
        sensor=sensor,
        vibration=vibration,
        diagnosis=diagnosis,
    )
    event_dict = event.to_dict()

    # Never write an event that fails its own integrity checks.
    validate_mod.check_join_keys(
        event_dict,
        secom_row_count=len(ctx.secom_df),
        vibration_file_count=len(ctx.vibration_load_result["files"]),
        wm811k_row_count=len(ctx.wm811k_df),
    )
    validate_mod.check_time_separation(event_dict)
    validate_mod.check_unit_semantics(event_dict)

    if sampled["notes"]:
        event_dict["_notes"] = sampled["notes"]

    return event_dict


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--scenario", "scenario_id", required=True, help="Scenario id, e.g. SC-EQ")
@click.option("--seed", required=True, type=int)
@click.option("--out", default="output/events", type=click.Path(), help="Output directory")
@click.option("--db", default=DEFAULT_DB_PATH, type=click.Path(), help="SQLite database path")
@click.option("--no-db", is_flag=True, default=False, help="Skip writing to the database")
def generate(scenario_id: str, seed: int, out: str, db: str, no_db: bool) -> None:
    """Generate one event, writing it to a JSON file and (by default) to SQLite."""
    rules = load_rules()
    ctx = build_sampling_context()
    event_dict = build_event(scenario_id, seed, ctx, rules)

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{event_dict['event_id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(event_dict, f, indent=2, ensure_ascii=False)
    click.echo(f"Wrote {out_path}")

    if not no_db:
        repo.save_event(db, event_dict)
        click.echo(f"Saved to {db}")

    diagnosis = event_dict["diagnosis"]
    click.echo(f"rule_id={diagnosis['rule_id']} primary_dept={diagnosis['primary_dept']} mfg_hold={diagnosis['mfg_hold']}")


@cli.command()
@click.option("--event-file", required=True, type=click.Path(exists=True))
def validate(event_file: str) -> None:
    """Run integrity checks against an already-generated event JSON."""
    with open(event_file, "r", encoding="utf-8") as f:
        event_dict = json.load(f)

    ctx = build_sampling_context()

    validate_mod.check_join_keys(
        event_dict,
        secom_row_count=len(ctx.secom_df),
        vibration_file_count=len(ctx.vibration_load_result["files"]),
        wm811k_row_count=len(ctx.wm811k_df),
    )
    validate_mod.check_time_separation(event_dict)
    validate_mod.check_unit_semantics(event_dict)
    validate_mod.check_secom_label_encoding(ctx.secom_df["Pass/Fail"].tolist())

    click.echo("OK: all integrity checks passed")


@cli.command()
@click.option("--seeds", required=True, type=int, help="Seeds per scenario (0..seeds-1)")
@click.option("--out", default="output/experiments", type=click.Path(), help="Output directory")
@click.option("--db", default=DEFAULT_DB_PATH, type=click.Path(), help="SQLite database path")
@click.option("--no-db", is_flag=True, default=False, help="Skip writing to the database")
def batch(seeds: int, out: str, db: str, no_db: bool) -> None:
    """Generate scenarios x seeds events and score them into a confusion matrix."""
    from experiments.run_batch import run_batch as _run_batch

    _run_batch(seeds, Path(out), db_path=None if no_db else db)


@cli.command()
@click.option("--events-dir", required=True, type=click.Path(exists=True), help="Directory of event *.json files")
@click.option("--db", default=DEFAULT_DB_PATH, type=click.Path(), help="SQLite database path")
def migrate(events_dir: str, db: str) -> None:
    """Migrate existing event JSON files into the SQLite database."""
    count = migrate_json_dir(events_dir, db)
    click.echo(f"Migrated {count} events from {events_dir} into {db}")


@cli.command("list")
@click.option("--db", default=DEFAULT_DB_PATH, type=click.Path(exists=True), help="SQLite database path")
@click.option("--scenario", "scenario_id", default=None, help="Filter by scenario id")
@click.option("--dept", "primary_dept", default=None, help="Filter by primary_dept")
@click.option("--limit", default=20, type=int)
def list_events_cmd(db: str, scenario_id: Optional[str], primary_dept: Optional[str], limit: int) -> None:
    """List events stored in the database (most recent first)."""
    events = repo.list_events(db, scenario_id=scenario_id, primary_dept=primary_dept, limit=limit)
    if not events:
        click.echo("No events found")
        return
    for event in events:
        diagnosis = event["diagnosis"]
        click.echo(
            f"{event['event_id']}  scenario={event['scenario_id']}  "
            f"rule_id={diagnosis['rule_id']}  primary_dept={diagnosis['primary_dept']}  "
            f"event_time={event['event_time']}"
        )


@cli.command()
@click.option("--event-id", required=True)
@click.option("--to", "to_dept", required=True, help="Target department (YI/MFG/M-ENG/P-ENG)")
@click.option("--reason", required=True)
@click.option("--db", default=DEFAULT_DB_PATH, type=click.Path(exists=True), help="SQLite database path")
def handover(event_id: str, to_dept: str, reason: str, db: str) -> None:
    """Record a department reassignment ("핑퐁") for an existing event."""
    try:
        record = repo.add_handover(db, event_id, to_dept, reason)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"{event_id}: {record['from_dept']} -> {record['to_dept']}  ({record['reason']})")


@cli.command()
@click.option("--event-id", required=True)
@click.option("--db", default=DEFAULT_DB_PATH, type=click.Path(exists=True), help="SQLite database path")
def history(event_id: str, db: str) -> None:
    """Show handover ("핑퐁") history for an event."""
    records = repo.list_handovers(db, event_id)
    if not records:
        click.echo("No handovers recorded")
        return
    for r in records:
        click.echo(f"{r['created_at']}  {r['from_dept']} -> {r['to_dept']}  ({r['reason']})")
    click.echo(f"pingpong_count={len(records)}")


if __name__ == "__main__":
    cli()
