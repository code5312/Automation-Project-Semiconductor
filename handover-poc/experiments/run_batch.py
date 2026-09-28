"""Batch experiment: generate scenarios x seeds events and score them
against expected_dept via a confusion matrix.

Never adjust numbers here to make results look better -- if accuracy comes
out low, report it as-is; the fix belongs in config/rules.yaml, not here.
"""
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from src.cli import build_event, load_rules
from src.scenarios.catalog import build_sampling_context
from src.storage import repository as repo


def run_batch(seeds: int, out_dir: Path, db_path: Optional[str] = None) -> None:
    out_dir = Path(out_dir)
    events_dir = out_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    rules = load_rules()
    ctx = build_sampling_context()
    scenario_ids = list(ctx.scenarios.keys())

    confusion: Counter = Counter()
    per_scenario_correct: Counter = Counter()
    per_scenario_total: Counter = Counter()

    for scenario_id in scenario_ids:
        expected = ctx.scenarios[scenario_id]["expected_dept"]
        for seed in range(seeds):
            event = build_event(scenario_id, seed, ctx, rules)
            with open(events_dir / f"{event['event_id']}.json", "w", encoding="utf-8") as f:
                json.dump(event, f, indent=2, ensure_ascii=False)
            if db_path is not None:
                repo.save_event(db_path, event)

            predicted = event["diagnosis"]["primary_dept"]
            confusion[(str(expected), str(predicted))] += 1
            per_scenario_total[scenario_id] += 1
            if predicted == expected:
                per_scenario_correct[scenario_id] += 1

    csv_path = out_dir / "confusion_matrix.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write("expected_dept,predicted_dept,count\n")
        for (expected, predicted), count in sorted(confusion.items(), key=lambda kv: str(kv[0])):
            f.write(f"{expected},{predicted},{count}\n")

    total_events = sum(per_scenario_total.values())
    print(f"Wrote {total_events} events to {events_dir}")
    if db_path is not None:
        print(f"Saved {total_events} events to {db_path}")
    print(f"Wrote confusion matrix to {csv_path}")
    print("Per-scenario accuracy:")
    for scenario_id in scenario_ids:
        total = per_scenario_total[scenario_id]
        correct = per_scenario_correct[scenario_id]
        acc = correct / total if total else 0.0
        print(f"  {scenario_id}: {correct}/{total} = {acc:.1%}")

    overall_correct = sum(per_scenario_correct.values())
    overall_acc = overall_correct / total_events if total_events else 0.0
    print(f"Overall accuracy: {overall_acc:.1%}")
    if overall_acc < 0.8:
        print("Accuracy is low -- this is reported as-is. Consider tuning config/rules.yaml, not this script.")
