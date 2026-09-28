"""Vision signal extraction from mock wafer-map records."""


def extract_vision_signal(wafer_record: dict) -> dict:
    """Pass through pattern/pattern_group from a wafer_mock record."""
    return {
        "pattern": wafer_record["failureType"],
        "pattern_group": wafer_record["pattern_group"],
    }
