"""CLI entry point.

    python -m src.cli generate --scenario SC-EQ --seed 42 --out output/events/
    python -m src.cli validate --event-file output/events/EVT-xxxx.json
    python -m src.cli batch --seeds 50 --out output/experiments/
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

RULES_PATH = Path("config/rules.yaml")


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
def generate(scenario_id: str, seed: int, out: str) -> None:
    """Generate one event JSON file."""
    rules = load_rules()
    ctx = build_sampling_context()
    event_dict = build_event(scenario_id, seed, ctx, rules)

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{event_dict['event_id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(event_dict, f, indent=2, ensure_ascii=False)

    click.echo(f"Wrote {out_path}")
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
def batch(seeds: int, out: str) -> None:
    """Generate scenarios x seeds events and score them into a confusion matrix."""
    from experiments.run_batch import run_batch as _run_batch

    _run_batch(seeds, Path(out))


if __name__ == "__main__":
    cli()
