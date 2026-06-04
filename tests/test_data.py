from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vw_euda_mqtt.data import (  # noqa: E402
    Dataset,
    curated_values,
    parse_timestamp,
    parse_value,
    raw_values,
    topic_safe,
)


class ValueParsingTests(unittest.TestCase):
    def test_parse_value_converts_common_scalar_types(self) -> None:
        cases = {
            None: None,
            "": None,
            "  ": None,
            "true": True,
            "FALSE": False,
            "42": 42,
            "-7": -7,
            "12.5": 12.5,
            "-3.25": -3.25,
            "90 s": 90.0,
            "1.5S": 1.5,
            "ready": "ready",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_value(raw), expected)

    def test_parse_timestamp_accepts_epoch_milliseconds_and_iso_strings(self) -> None:
        self.assertEqual(
            parse_timestamp("1700000000000"),
            datetime.fromtimestamp(1700000000, tz=timezone.utc),
        )
        self.assertEqual(
            parse_timestamp("2026-01-02T03:04:05Z"),
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp("not-a-timestamp"))

    def test_topic_safe_removes_mqtt_topic_unfriendly_characters(self) -> None:
        self.assertEqual(topic_safe(" range / km "), "range_km")
        self.assertEqual(topic_safe("battery.state"), "battery.state")
        self.assertEqual(topic_safe("###"), "unknown")


class DatasetTests(unittest.TestCase):
    def test_dataset_from_json_parses_points_and_latest_capture_time(self) -> None:
        dataset = Dataset.from_json(
            {
                "vin": "TESTVIN1234567890",
                "user_id": "user-1",
                "Data": [
                    {"key": "b", "dataFieldName": "car_captured_time", "value": "2026-01-02T03:04:05Z"},
                    {"key": "a", "dataFieldName": "car_captured_time", "value": "2026-01-02T03:05:05Z"},
                    {"key": "ignored-no-key", "value": "123"},
                    {"key": "soc", "dataFieldName": "battery_state_report.soc", "value": "77"},
                ],
            }
        )

        self.assertEqual(dataset.vin, "TESTVIN1234567890")
        self.assertEqual(dataset.user_id, "user-1")
        self.assertEqual(dataset.captured_at, datetime(2026, 1, 2, 3, 5, 5, tzinfo=timezone.utc))
        self.assertEqual(dataset.by_field("battery_state_report.soc").value, 77)
        self.assertIsNone(dataset.by_field("missing"))

    def test_by_field_returns_stable_lowest_key_match(self) -> None:
        dataset = Dataset.from_json(
            {
                "Data": [
                    {"key": "z", "dataFieldName": "range", "value": "300"},
                    {"key": "a", "dataFieldName": "range", "value": "301"},
                ]
            }
        )

        self.assertEqual(dataset.by_field("range").key, "a")
        self.assertEqual(dataset.by_field("range").value, 301)

    def test_curated_and_raw_values_use_expected_topics(self) -> None:
        dataset = Dataset.from_json(
            {
                "Data": [
                    {"key": "soc", "dataFieldName": "battery_state_report.soc", "value": "80"},
                    {"key": "range", "dataFieldName": "range", "value": "321"},
                    {"key": "door", "dataFieldName": "locked", "value": "true"},
                    {"key": "odd", "dataFieldName": "bad field/name", "value": "text"},
                ]
            }
        )

        self.assertEqual(
            curated_values(dataset),
            {
                "battery/soc": 80,
                "range/km": 321,
                "doors/locked": True,
            },
        )
        raw = raw_values(dataset)
        self.assertEqual(raw["raw/bad_field_name"], "text")
        self.assertEqual(raw["raw/by_key/odd"], "text")
        self.assertEqual(raw["raw/by_field/bad_field_name/odd"], "text")
        self.assertEqual(
            raw["raw/_topic_index"]["odd"],
            {
                "field_name": "bad field/name",
                "by_key_topic": "raw/by_key/odd",
                "by_field_topic": "raw/by_field/bad_field_name/odd",
            },
        )

    def test_raw_values_keep_duplicate_field_names_without_overwriting(self) -> None:
        dataset = Dataset.from_json(
            {
                "Data": [
                    {"key": "timestamp_a", "dataFieldName": "timestamp", "value": "1"},
                    {"key": "timestamp_b", "dataFieldName": "timestamp", "value": "2"},
                ]
            }
        )

        raw = raw_values(dataset)

        self.assertEqual(raw["raw/by_key/timestamp_a"], 1)
        self.assertEqual(raw["raw/by_key/timestamp_b"], 2)
        self.assertEqual(raw["raw/by_field/timestamp/timestamp_a"], 1)
        self.assertEqual(raw["raw/by_field/timestamp/timestamp_b"], 2)
        self.assertNotIn("raw/timestamp", raw)

    def test_redacted_audi_fixture_exposes_expected_normalized_topics(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "audi_dataset_redacted.json"
        dataset = Dataset.from_json(json.loads(fixture.read_text(encoding="utf-8")))

        values = curated_values(dataset)
        self.assertEqual(values["battery/soc"], 52)
        self.assertEqual(values["battery/target_soc"], 100)
        self.assertEqual(values["battery/charge_power_kw"], 0)
        self.assertEqual(values["odometer/km"], 63151)
        self.assertEqual(values["charging/state"], "not_charging")
        self.assertEqual(values["charging/mode"], "manual")
        self.assertEqual(values["charging/scenario"], "default")
        self.assertEqual(values["doors/locked"], True)
        self.assertEqual(values["parking_brake"], True)
        self.assertEqual(values["battery/min_temperature_c"], 17.5)
        self.assertEqual(values["battery/max_temperature_c"], 19.0)
        self.assertEqual(values["climate/remaining_time_s"], 0.0)

        raw = raw_values(dataset)
        self.assertEqual(raw["raw/by_key/captured_main"], "2026-05-31T15:35:00Z")
        self.assertEqual(raw["raw/by_key/captured_secondary"], "2026-05-31T15:36:00Z")
        self.assertEqual(raw["raw/by_field/car_captured_time/captured_main"], "2026-05-31T15:35:00Z")
        self.assertEqual(raw["raw/by_field/car_captured_time/captured_secondary"], "2026-05-31T15:36:00Z")
        self.assertNotIn("raw/car_captured_time", raw)


if __name__ == "__main__":
    unittest.main()
