from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vw_euda_mqtt.api import ApiError  # noqa: E402
from vw_euda_mqtt.data import Dataset  # noqa: E402
from vw_euda_mqtt.service import (  # noqa: E402
    MqttConfig,
    ServiceConfig,
    _created_on,
    _is_dataset_listing_pending,
    _load_state,
    _mqtt_payload,
    _next_sleep,
    _save_state,
    _state_path,
    publish_carcompat,
    publish_dataset,
    publish_status,
)


class ConfigAndStateTests(unittest.TestCase):
    def test_service_config_from_file_applies_defaults_and_mqtt_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "email": "user@example.com",
                        "password": "example-password",
                        "brand": "AUDI",
                        "vin": "",
                        "state_file": "data/state.json",
                        "mqtt": {
                            "host": "mqtt.example.local",
                            "base_topic": "/cars/euda/",
                            "publish_raw": True,
                            "publish_carcompat": True,
                            "carcompat_base_topic": "/garage/",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = ServiceConfig.from_file(config_path)

        self.assertEqual(config.email, "user@example.com")
        self.assertIsNone(config.vin)
        self.assertEqual(config.portal.oidc_state, "de__de__AUDI")
        self.assertEqual(config.mqtt.host, "mqtt.example.local")
        self.assertEqual(config.mqtt.base_topic, "cars/euda")
        self.assertTrue(config.mqtt.publish_raw)
        self.assertTrue(config.mqtt.publish_carcompat)
        self.assertEqual(config.mqtt.carcompat_base_topic, "garage")

    def test_state_path_resolves_relative_to_config_file_and_roundtrips_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            state_path = _state_path(config_path, "data/state.json")
            self.assertEqual(state_path, Path(tmp) / "data" / "state.json")

            _save_state(state_path, {"last_dataset": "dataset.zip"})
            self.assertEqual(_load_state(state_path), {"last_dataset": "dataset.zip"})
            self.assertEqual(_load_state(Path(tmp) / "missing.json"), {})

    def test_state_path_keeps_absolute_paths(self) -> None:
        absolute = Path.cwd() / "state.json"
        self.assertEqual(_state_path(Path("config.json"), str(absolute)), absolute)


class SchedulingTests(unittest.TestCase):
    def test_created_on_prefers_explicit_timestamp_and_falls_back_to_filename(self) -> None:
        self.assertEqual(
            _created_on({"createdOn": "2026-01-02T03:04:05Z"}),
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(
            _created_on({"name": "partial_20260102030405.zip"}),
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )
        self.assertIsNone(_created_on({"createdOn": "invalid", "name": "no_timestamp.zip"}))

    def test_next_sleep_uses_retry_when_no_timestamp_exists(self) -> None:
        self.assertEqual(_next_sleep([{"name": "no_timestamp.zip"}], 900, 60), 60)

    def test_dataset_listing_pending_only_matches_transient_delivery_errors(self) -> None:
        self.assertTrue(_is_dataset_listing_pending(ApiError("GET /datadelivery/vehicles/abc/list -> HTTP 404")))
        self.assertTrue(_is_dataset_listing_pending(ApiError("GET /datadelivery/vehicles/abc/list -> HTTP 503")))
        self.assertFalse(_is_dataset_listing_pending(ApiError("GET /vehicles -> HTTP 404")))
        self.assertFalse(_is_dataset_listing_pending(ApiError("GET /datadelivery/vehicles/abc/list -> HTTP 401")))


class PublishTests(unittest.TestCase):
    def test_mqtt_payload_serializes_supported_values(self) -> None:
        self.assertEqual(_mqtt_payload(True), "true")
        self.assertEqual(_mqtt_payload(False), "false")
        self.assertEqual(_mqtt_payload(None), "")
        self.assertEqual(_mqtt_payload({"b": 2, "a": 1}), '{"b":2,"a":1}')
        self.assertEqual(_mqtt_payload(12.5), "12.5")

    def test_publish_dataset_emits_status_curated_raw_and_carcompat_topics(self) -> None:
        fake_class = _recording_publisher_class()
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(
                host="mqtt.example.local",
                base_topic="vw/euda",
                publish_raw=True,
                publish_carcompat=True,
                carcompat_base_topic="car",
            ),
        )
        raw_payload = {
            "Data": [
                {"key": "soc", "dataFieldName": "battery_state_report.soc", "value": "80"},
                {"key": "range", "dataFieldName": "range", "value": "321"},
                {"key": "captured", "dataFieldName": "car_captured_time", "value": "2026-01-02T03:04:05Z"},
            ]
        }
        dataset = Dataset.from_json(raw_payload)

        with patch("vw_euda_mqtt.service.MqttPublisher", fake_class):
            publish_dataset(config, "TESTVIN1234567890", "dataset.zip", dataset, raw_payload)

        published = dict(fake_class.instances[-1].published)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/status/online"], True)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/status/last_dataset"], "dataset.zip")
        self.assertEqual(published["vw/euda/TESTVIN1234567890/status/captured_at"], "2026-01-02T03:04:05+00:00")
        self.assertEqual(published["vw/euda/TESTVIN1234567890/battery/soc"], 80)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/range/km"], 321)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/raw/range"], 321)
        self.assertEqual(published["car/garage/TESTVIN1234567890/drives/primary/level"], 80)
        self.assertEqual(published["car/garage/TESTVIN1234567890/drives/primary/range"], 321)

    def test_publish_status_marks_errors_and_service_fallback_vin(self) -> None:
        fake_class = _recording_publisher_class()
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(host="mqtt.example.local", base_topic="vw/euda"),
        )

        with patch("vw_euda_mqtt.service.MqttPublisher", fake_class):
            publish_status(config, connected=False, error="boom", error_type="ApiError")

        published = dict(fake_class.instances[-1].published)
        self.assertEqual(published["vw/euda/_service/status/online"], False)
        self.assertEqual(published["vw/euda/_service/status/connected"], False)
        self.assertEqual(published["vw/euda/_service/status/error"], "boom")
        self.assertEqual(published["vw/euda/_service/status/error_type"], "ApiError")
        self.assertNotEqual(published["vw/euda/_service/status/last_error_at"], "")
        self.assertNotIn("vw/euda/_service/status/last_success_at", published)

    def test_publish_carcompat_only_emits_available_mapped_values(self) -> None:
        publisher = _StandaloneRecorder()
        publish_carcompat(
            publisher,
            MqttConfig(host="mqtt.example.local", carcompat_base_topic="car"),
            "TESTVIN1234567890",
            {"battery/soc": 80, "odometer/km": 12345, "ignored": "value"},
        )

        self.assertEqual(
            publisher.published,
            [
                ("car/garage/TESTVIN1234567890/drives/primary/level", 80),
                ("car/garage/TESTVIN1234567890/odometer", 12345),
            ],
        )


class _StandaloneRecorder:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    def publish(self, topic: str, value: object) -> None:
        self.published.append((topic, value))


def _recording_publisher_class():
    class RecordingPublisher:
        instances: list[RecordingPublisher] = []

        def __init__(self, config: MqttConfig, dry_run: bool = False) -> None:
            self.config = config
            self.dry_run = dry_run
            self.published: list[tuple[str, object]] = []
            self.__class__.instances.append(self)

        def __enter__(self) -> RecordingPublisher:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def publish(self, topic: str, value: object) -> None:
            self.published.append((topic, value))

    return RecordingPublisher


if __name__ == "__main__":
    unittest.main()
