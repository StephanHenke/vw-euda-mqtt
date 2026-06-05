"""Dataset parsing and curated value extraction."""

from __future__ import annotations

import re
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
    group_index: int | None = None
    car_captured_at: datetime | None = None

    @property
    def value(self):
        return parse_value(self.raw_value)


@dataclass
class DataGroup:
    index: int
    captured_at: datetime | None
    points: list[DataPoint] = field(default_factory=list)


@dataclass(frozen=True)
class DataCatalogEntry:
    name: str
    unit: str = ""
    description: str = ""
    data_type: str = ""
    cluster: str = ""


@dataclass
class Dataset:
    vin: str
    user_id: str | None
    points: dict[str, DataPoint] = field(default_factory=dict)
    groups: list[DataGroup] = field(default_factory=list)
    captured_at: datetime | None = None

    @classmethod
    def from_json(cls, payload: dict) -> "Dataset":
        points: dict[str, DataPoint] = {}
        groups: list[DataGroup] = []
        pending_group: list[DataPoint] = []

        def close_group(captured_at: datetime | None) -> None:
            if not pending_group:
                return
            group_index = len(groups)
            group_points = list(pending_group)
            for point in group_points:
                point.group_index = group_index
                point.car_captured_at = captured_at
            groups.append(DataGroup(index=group_index, captured_at=captured_at, points=group_points))
            pending_group.clear()

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
            pending_group.append(datapoint)
            if field_name == "car_captured_time":
                timestamp = parse_timestamp(datapoint.raw_value)
                close_group(timestamp)

        if pending_group and groups:
            last_group = groups[-1]
            for point in list(pending_group):
                point.group_index = last_group.index
                point.car_captured_at = last_group.captured_at
                last_group.points.append(point)
            pending_group.clear()
        else:
            close_group(None)
        captured = [group.captured_at for group in groups if group.captured_at is not None]
        return cls(
            vin=payload.get("vin", ""),
            user_id=payload.get("user_id"),
            points=points,
            groups=groups,
            captured_at=max(captured) if captured else None,
        )

    def by_field(self, field_name: str) -> DataPoint | None:
        matches = [point for point in self.points.values() if point.field_name == field_name]
        if not matches:
            return None
        latest_capture = max((point.car_captured_at for point in matches if point.car_captured_at), default=None)
        if latest_capture is not None:
            latest_matches = [point for point in matches if point.car_captured_at == latest_capture]
            return min(latest_matches, key=lambda point: point.key)
        return min(matches, key=lambda point: point.key)


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


DATA_CATALOG_BY_FIELD: dict[str, DataCatalogEntry] = {
    "battery_state_report.soc": DataCatalogEntry(
        name="soc",
        unit="%",
        description="Battery state of charge.",
        data_type="int",
        cluster="Charging",
    ),
    "settings.target_soc": DataCatalogEntry(
        name="target_soc",
        unit="%",
        description="Configured charging target state of charge.",
        data_type="int",
        cluster="Charging",
    ),
    "battery_state_report.charge_bulk_threshold": DataCatalogEntry(
        name="charge_bulk_threshold",
        unit="%",
        description="Configured bulk charging threshold.",
        data_type="int",
        cluster="Charging",
    ),
    "battery_state_report.charge_power": DataCatalogEntry(
        name="charge_power",
        unit="kW",
        description="Reported charging power.",
        data_type="number",
        cluster="Charging",
    ),
    "mileage.value": DataCatalogEntry(
        name="odometer",
        unit="km",
        description="Vehicle odometer value.",
        data_type="number",
        cluster="Vehicle Status",
    ),
    "range": DataCatalogEntry(
        name="range",
        unit="km",
        description="Reported electric range.",
        data_type="number",
        cluster="Vehicle Status",
    ),
    "charging_state_report.current_charge_state": DataCatalogEntry(
        name="charging_state",
        description="Current charging state.",
        data_type="string",
        cluster="Charging",
    ),
    "charging_state_report.charge_mode": DataCatalogEntry(
        name="charge_mode",
        description="Current charging mode.",
        data_type="string",
        cluster="Charging",
    ),
    "charging_state_report.charging_scenario": DataCatalogEntry(
        name="charging_scenario",
        description="Current charging scenario.",
        data_type="string",
        cluster="Charging",
    ),
    "charging_state_report.immediate_action_state": DataCatalogEntry(
        name="immediate_action",
        description="Immediate charging action state.",
        data_type="string",
        cluster="Charging",
    ),
    "settings.charge_mode_selection": DataCatalogEntry(
        name="mode_selection",
        description="Selected charging mode setting.",
        data_type="string",
        cluster="Charging",
    ),
    "settings.max_charge_current_ac": DataCatalogEntry(
        name="max_current",
        description="Maximum AC charging current setting.",
        data_type="string",
        cluster="Charging",
    ),
    "locked": DataCatalogEntry(
        name="locked",
        description="Vehicle lock state.",
        data_type="boolean",
        cluster="Vehicle Status",
    ),
    "parking_brake": DataCatalogEntry(
        name="parking_brake",
        description="Parking brake state.",
        data_type="boolean",
        cluster="Parking Data",
    ),
    "min_temperature": DataCatalogEntry(
        name="min_temperature",
        unit="C",
        description="Minimum reported battery temperature.",
        data_type="number",
        cluster="Charging",
    ),
    "max_temperature": DataCatalogEntry(
        name="max_temperature",
        unit="C",
        description="Maximum reported battery temperature.",
        data_type="number",
        cluster="Charging",
    ),
    "remaining_climate_time": DataCatalogEntry(
        name="remaining_climate_time",
        unit="s",
        description="Remaining climate runtime.",
        data_type="number",
        cluster="Climate",
    ),
    "car_captured_time": DataCatalogEntry(
        name="car_captured_time",
        description="Vehicle-side capture timestamp assigned to the surrounding datapoint group.",
        data_type="timestamp",
        cluster="Metadata",
    ),
}


def curated_values(dataset: Dataset) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field_name, (topic, _unit) in CURATED_TOPIC_FIELDS.items():
        point = dataset.by_field(field_name)
        if point is not None:
            values[topic] = point.value
    return values


def curated_capture_values(dataset: Dataset) -> dict[str, str]:
    values: dict[str, str] = {}
    for field_name, (topic, _unit) in CURATED_TOPIC_FIELDS.items():
        point = dataset.by_field(field_name)
        if point is not None and point.car_captured_at is not None:
            values[f"{topic}/car_captured_at"] = point.car_captured_at.isoformat()
    return values


def data_catalog_entry(point: DataPoint) -> DataCatalogEntry:
    if point.key in DATA_CATALOG_BY_FIELD:
        return DATA_CATALOG_BY_FIELD[point.key]
    if point.field_name in DATA_CATALOG_BY_FIELD:
        return DATA_CATALOG_BY_FIELD[point.field_name]
    return DataCatalogEntry(name=point.field_name)


def datapoint_json(point: DataPoint) -> dict[str, Any]:
    entry = data_catalog_entry(point)
    car_captured_at = point.car_captured_at.isoformat() if point.car_captured_at else ""
    return {
        "id": topic_safe(point.key),
        "key": point.key,
        "field_name": point.field_name,
        "name": entry.name or point.field_name,
        "value": point.value,
        "raw_value": point.raw_value,
        "unit": entry.unit,
        "description": entry.description,
        "data_type": entry.data_type,
        "cluster": entry.cluster,
        "group_index": point.group_index if point.group_index is not None else None,
        "car_captured_at": car_captured_at,
    }


def structured_values(dataset: Dataset) -> dict[str, Any]:
    values: dict[str, Any] = {}
    points = list(dataset.points.values())
    key_topics = _unique_topic_segments([point.key for point in points])
    point_metadata = [(point, datapoint_json(point)) for point in points]
    name_topics = _unique_topic_segments([metadata["name"] for _point, metadata in point_metadata])
    by_name: dict[str, list[tuple[DataPoint, dict[str, Any], str]]] = {}

    def add_datapoint_tree(prefix: str, metadata: dict[str, Any]) -> None:
        values[f"{prefix}/value"] = metadata["value"]
        values[f"{prefix}/name"] = metadata["name"]
        values[f"{prefix}/key"] = metadata["key"]
        values[f"{prefix}/unit"] = metadata["unit"]
        values[f"{prefix}/description"] = metadata["description"]
        values[f"{prefix}/field_name"] = metadata["field_name"]
        values[f"{prefix}/data_type"] = metadata["data_type"]
        values[f"{prefix}/cluster"] = metadata["cluster"]
        values[f"{prefix}/group_index"] = metadata["group_index"] if metadata["group_index"] is not None else ""
        values[f"{prefix}/car_captured_at"] = metadata["car_captured_at"]
        values[f"{prefix}/json"] = metadata

    for point, metadata in point_metadata:
        key_topic = key_topics[point.key]
        name_topic = name_topics[metadata["name"]]
        by_key_prefix = f"structured/by_key/{key_topic}"
        by_name_prefix = f"structured/by_name/{name_topic}"
        metadata["topics"] = {
            "by_key": by_key_prefix,
            "by_name": by_name_prefix,
        }
        add_datapoint_tree(by_key_prefix, metadata)
        by_name.setdefault(name_topic, []).append((point, metadata, key_topic))

    for name_topic, items in by_name.items():
        sorted_items = sorted(items, key=lambda item: _datapoint_sort_key(item[0]), reverse=True)
        _latest_point, latest_metadata, _latest_key_topic = sorted_items[0]
        add_datapoint_tree(f"structured/by_name/{name_topic}", latest_metadata)
        values[f"structured/by_name/{name_topic}/keys"] = [
            {
                "key": metadata["key"],
                "car_captured_at": metadata["car_captured_at"],
            }
            for _point, metadata, _key_topic in sorted_items
        ]

    return values


def raw_file_values(download: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    files = list(getattr(download, "files", []) or [])
    for index, file in enumerate(files):
        prefix = f"raw/file/{index}"
        values[f"{prefix}/filename"] = file.name
        values[f"{prefix}/content"] = file.content
    return values


def history_batch(dataset: Dataset, dataset_name: str) -> dict[str, Any]:
    eligible_points = [
        point
        for group in dataset.groups
        for point in group.points
        if point.field_name != "car_captured_time" and point.car_captured_at is not None
    ]
    point_metadata = [(point, datapoint_json(point)) for point in eligible_points]
    key_topics = _unique_topic_segments([point.key for point in eligible_points])
    name_topics = _unique_topic_segments([metadata["name"] for _point, metadata in point_metadata])

    events: list[dict[str, Any]] = []
    sorted_items = sorted(point_metadata, key=lambda item: _history_sort_key(item[0]))
    for sequence, (point, metadata) in enumerate(sorted_items):
        key_topic = key_topics[point.key]
        name_topic = name_topics[metadata["name"]]
        event = {
            "event_id": f"{topic_safe(dataset_name)}:{metadata['group_index']}:{sequence}:{key_topic}",
            "dataset": dataset_name,
            "key": metadata["key"],
            "field_name": metadata["field_name"],
            "name": metadata["name"],
            "value": metadata["value"],
            "raw_value": metadata["raw_value"],
            "unit": metadata["unit"],
            "description": metadata["description"],
            "data_type": metadata["data_type"],
            "cluster": metadata["cluster"],
            "group_index": metadata["group_index"],
            "car_captured_at": metadata["car_captured_at"],
            "curated_topic": CURATED_TOPIC_FIELDS.get(point.field_name, ("", None))[0],
            "structured_by_name_topic": f"structured/by_name/{name_topic}",
            "structured_by_key_topic": f"structured/by_key/{key_topic}",
        }
        events.append(event)

    return {
        "vin": dataset.vin,
        "dataset": dataset_name,
        "event_count": len(events),
        "events": events,
    }


def _datapoint_sort_key(point: DataPoint) -> tuple[datetime, str]:
    captured_at = point.car_captured_at or datetime.min.replace(tzinfo=timezone.utc)
    return captured_at, point.key


def _history_sort_key(point: DataPoint) -> tuple[datetime, int]:
    captured_at = point.car_captured_at or datetime.min.replace(tzinfo=timezone.utc)
    group_index = point.group_index if point.group_index is not None else -1
    return captured_at, group_index
