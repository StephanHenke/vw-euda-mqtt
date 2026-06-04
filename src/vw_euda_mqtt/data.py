"""Dataset parsing and curated value extraction."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
DURATION_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*s$", re.I)
TOPIC_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def parse_value(raw: str | None) -> Any:
    if raw is None:
        return None
    value = raw.strip()
    if value == "":
        return None
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    duration = DURATION_RE.match(value)
    if duration:
        return float(duration.group(1))
    if INT_RE.match(value):
        return int(value)
    if FLOAT_RE.match(value):
        return float(value)
    return value


def parse_timestamp(raw: str | None) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    if INT_RE.match(value) and len(value) >= 12:
        try:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def topic_safe(value: str) -> str:
    cleaned = TOPIC_SAFE_RE.sub("_", value.strip())
    return cleaned.strip("_") or "unknown"


def _unique_topic_segments(values: list[str]) -> dict[str, str]:
    segments: dict[str, str] = {}
    used: set[str] = set()
    for value in sorted(set(values)):
        base = topic_safe(value)
        candidate = base
        index = 2
        while candidate in used:
            candidate = f"{base}_{index}"
            index += 1
        used.add(candidate)
        segments[value] = candidate
    return segments


@dataclass
class DataPoint:
    key: str
    field_name: str
    raw_value: str

    @property
    def value(self):
        return parse_value(self.raw_value)


@dataclass
class Dataset:
    vin: str
    user_id: str | None
    points: dict[str, DataPoint] = field(default_factory=dict)
    captured_at: datetime | None = None

    @classmethod
    def from_json(cls, payload: dict) -> "Dataset":
        points: dict[str, DataPoint] = {}
        captured: list[datetime] = []
        for item in payload.get("Data", []):
            key = item.get("key")
            if not key:
                continue
            field_name = item.get("dataFieldName") or key
            datapoint = DataPoint(
                key=key,
                field_name=field_name,
                raw_value=item.get("value", ""),
            )
            points[key] = datapoint
            if field_name == "car_captured_time":
                timestamp = parse_timestamp(datapoint.raw_value)
                if timestamp:
                    captured.append(timestamp)
        return cls(
            vin=payload.get("vin", ""),
            user_id=payload.get("user_id"),
            points=points,
            captured_at=max(captured) if captured else None,
        )

    def by_field(self, field_name: str) -> DataPoint | None:
        matches = [point for point in self.points.values() if point.field_name == field_name]
        return min(matches, key=lambda point: point.key) if matches else None


CURATED_TOPIC_FIELDS: dict[str, tuple[str, str | None]] = {
    "battery_state_report.soc": ("battery/soc", "%"),
    "settings.target_soc": ("battery/target_soc", "%"),
    "battery_state_report.charge_bulk_threshold": ("battery/charge_bulk_threshold", "%"),
    "battery_state_report.charge_power": ("battery/charge_power_kw", "kW"),
    "mileage.value": ("odometer/km", "km"),
    "range": ("range/km", "km"),
    "charging_state_report.current_charge_state": ("charging/state", None),
    "charging_state_report.charge_mode": ("charging/mode", None),
    "charging_state_report.charging_scenario": ("charging/scenario", None),
    "charging_state_report.immediate_action_state": ("charging/action_state", None),
    "settings.charge_mode_selection": ("charging/mode_selection", None),
    "settings.max_charge_current_ac": ("charging/max_charge_current_ac", None),
    "locked": ("doors/locked", None),
    "parking_brake": ("parking_brake", None),
    "min_temperature": ("battery/min_temperature_c", "C"),
    "max_temperature": ("battery/max_temperature_c", "C"),
    "remaining_climate_time": ("climate/remaining_time_s", "s"),
}


def curated_values(dataset: Dataset) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field_name, (topic, _unit) in CURATED_TOPIC_FIELDS.items():
        point = dataset.by_field(field_name)
        if point is not None:
            values[topic] = point.value
    return values


def raw_values(dataset: Dataset) -> dict[str, Any]:
    values: dict[str, Any] = {}
    points = list(dataset.points.values())
    field_counts = Counter(point.field_name for point in points)
    field_topics = _unique_topic_segments([point.field_name for point in points])
    key_topics = _unique_topic_segments([point.key for point in points])
    topic_index: dict[str, dict[str, str]] = {}

    for point in points:
        field_topic = field_topics[point.field_name]
        key_topic = key_topics[point.key]
        value = point.value
        by_key_topic = f"raw/by_key/{key_topic}"
        by_field_topic = f"raw/by_field/{field_topic}/{key_topic}"

        values[by_key_topic] = value
        values[by_field_topic] = value
        topic_index[point.key] = {
            "field_name": point.field_name,
            "by_key_topic": by_key_topic,
            "by_field_topic": by_field_topic,
        }

        if field_counts[point.field_name] == 1:
            values[f"raw/{field_topic}"] = value

    values["raw/_topic_index"] = topic_index
    return values
