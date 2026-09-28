"""Shared data containers for events, signals, and diagnoses.

These are plain dataclasses with pure to_dict() conversions so a future
web layer (FastAPI etc.) can wrap this logic without touching it.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class VisionSignal:
    source: str
    source_ref: dict[str, Any]
    source_time: Optional[str]
    pattern: str
    pattern_group: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TopSensor:
    sensor_id: str
    z: float
    unit: str = "unknown"
    meaning: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SensorSignal:
    source: str
    source_ref: dict[str, Any]
    source_time: Optional[str]
    anomaly_score: float
    top_sensors: list[TopSensor]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_ref": self.source_ref,
            "source_time": self.source_time,
            "anomaly_score": self.anomaly_score,
            "top_sensors": [s.to_dict() for s in self.top_sensors],
        }


@dataclass
class VibrationSignal:
    source: str
    source_ref: dict[str, Any]
    source_time: Optional[str]
    mode: str  # "full_baseline" | "single_file"
    rms: float
    health_index: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Diagnosis:
    rule_id: str
    scores: dict[str, float]
    contributions: dict[str, dict[str, float]]
    primary_dept: Optional[str]
    secondary_depts: list[str]
    mfg_hold: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    event_id: str
    scenario_id: str
    seed: int
    event_time: str
    vision: VisionSignal
    sensor: SensorSignal
    vibration: VibrationSignal
    diagnosis: Diagnosis
    is_simulated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "is_simulated": self.is_simulated,
            "event_time": self.event_time,
            "signals": {
                "vision": self.vision.to_dict(),
                "sensor": self.sensor.to_dict(),
                "vibration": self.vibration.to_dict(),
            },
            "diagnosis": self.diagnosis.to_dict(),
        }
