"""Integrity checks for assembled events.

Each check is a standalone function so tests can call them individually.
All raise ValueError (or let the underlying loader's exception propagate)
on failure -- none of them substitute a fallback value.
"""
from typing import Any, Callable

from src.ingest.loaders import SECOM_LABEL_FAIL, SECOM_LABEL_PASS


def check_join_keys(
    event: dict,
    secom_row_count: int,
    vibration_file_count: int,
    wm811k_row_count: int | None = None,
) -> None:
    """Every signal must reference a source record that actually exists."""
    sensor_ref = event["signals"]["sensor"]["source_ref"]
    row = sensor_ref.get("row")
    if row is None or not (0 <= row < secom_row_count):
        raise ValueError(f"SECOM row index out of range: {row} (n_rows={secom_row_count})")

    vision_ref = event["signals"]["vision"]["source_ref"]
    if not vision_ref.get("lotName") or vision_ref.get("waferIndex") is None:
        raise ValueError(f"Vision source_ref missing lotName/waferIndex: {vision_ref}")
    vision_row = vision_ref.get("row")
    if wm811k_row_count is not None and vision_row is not None:
        if not (0 <= vision_row < wm811k_row_count):
            raise ValueError(f"WM-811K row index out of range: {vision_row} (n_rows={wm811k_row_count})")

    vibration = event["signals"]["vibration"]
    vib_ref = vibration["source_ref"]
    order = vib_ref.get("order")
    if vibration["mode"] == "single_file":
        if order != 0:
            raise ValueError(f"single_file mode must reference order=0, got {order}")
    elif vibration["mode"] == "full_baseline":
        if order is None or not (0 <= order < vibration_file_count):
            raise ValueError(
                f"Vibration file order out of range: {order} (n_files={vibration_file_count})"
            )
    else:
        raise ValueError(f"Unknown vibration mode: {vibration['mode']}")


def check_time_separation(event: dict) -> None:
    """event_time (virtual) and each signal's source_time (real, or None) are distinct fields."""
    if not isinstance(event.get("event_time"), str) or not event["event_time"]:
        raise ValueError("event_time must be a non-empty ISO8601 string")

    for name in ("vision", "sensor", "vibration"):
        signal = event["signals"][name]
        if "source_time" not in signal:
            raise ValueError(f"Signal '{name}' is missing the source_time field")

    if event["signals"]["vision"]["source_time"] is not None:
        raise ValueError("Vision (WM-811K mock) signal must have source_time=None")


def _walk_unit_meaning(obj: Any) -> None:
    if isinstance(obj, dict):
        for key in ("unit", "meaning"):
            if key in obj:
                val = obj[key]
                if not isinstance(val, str) or not val.strip():
                    raise ValueError(f"'{key}' field present but empty/invalid in {obj}")
        for v in obj.values():
            _walk_unit_meaning(v)
    elif isinstance(obj, list):
        for item in obj:
            _walk_unit_meaning(item)


def check_unit_semantics(event: dict) -> None:
    """Every unit/meaning field present must be a non-empty string (e.g. "unknown")."""
    _walk_unit_meaning(event)


def check_secom_label_encoding(values) -> None:
    """SECOM Pass/Fail must only ever be -1 (pass) or 1 (fail)."""
    allowed = {SECOM_LABEL_PASS, SECOM_LABEL_FAIL}
    bad = {v for v in values if v not in allowed}
    if bad:
        raise ValueError(f"Unexpected Pass/Fail values: {bad}")


def load_or_fail(loader: Callable[..., Any], *args, **kwargs) -> Any:
    """Call `loader` and return its result. Never catches -- a failed load
    must abort event generation rather than fall back to a placeholder."""
    return loader(*args, **kwargs)
