from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vw_euda_mqtt import __version__  # noqa: E402
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
    healthcheck,
    publish_carcompat,
    publish_dataset,
    publish_homeassistant_discovery,
    publish_status,
    run_service,
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
                            "publish_homeassistant_discovery": True,
                            "homeassistant_discovery_prefix": "/ha/",
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
        self.assertTrue(config.mqtt.publish_homeassistant_discovery)
        self.assertEqual(config.mqtt.homeassistant_discovery_prefix, "ha")

    def test_service_config_from_file_accepts_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "email": "file@example.com",
                        "password": "file-password",
                        "vin": "FILEVIN1234567890",
                        "identifier": "file-identifier",
                        "mqtt": {
                            "host": "file-mqtt.local",
                            "username": "file-user",
                            "password": "file-mqtt-password",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "VW_EUDA_EMAIL": "env@example.com",
                    "VW_EUDA_PASSWORD": "env-password",
                    "VW_EUDA_VIN": "ENVVIN12345678901",
                    "VW_EUDA_IDENTIFIER": "env-identifier",
                    "VW_EUDA_MQTT_HOST": "env-mqtt.local",
                    "VW_EUDA_MQTT_USERNAME": "env-user",
                    "VW_EUDA_MQTT_PASSWORD": "env-mqtt-password",
                },
            ):
                config = ServiceConfig.from_file(config_path)

        self.assertEqual(config.email, "env@example.com")
        self.assertEqual(config.password, "env-password")
        self.assertEqual(config.vin, "ENVVIN12345678901")
        self.assertEqual(config.identifier, "env-identifier")
        self.assertEqual(config.mqtt.host, "env-mqtt.local")
        self.assertEqual(config.mqtt.username, "env-user")
        self.assertEqual(config.mqtt.password, "env-mqtt-password")

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

    def test_healthcheck_accepts_recent_successful_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = ServiceConfig(
                email="user@example.com",
                password="example-password",
                poll_interval_seconds=900,
                state_file="data/state.json",
                mqtt=MqttConfig(host="mqtt.example.local"),
            )
            state_path = _state_path(config_path, config.state_file)
            _save_state(state_path, {"last_success_at": datetime.now(timezone.utc).isoformat()})

            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(healthcheck(config, config_path), 0)

    def test_healthcheck_rejects_missing_or_stale_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = ServiceConfig(
                email="user@example.com",
                password="example-password",
                poll_interval_seconds=900,
                state_file="data/state.json",
                mqtt=MqttConfig(host="mqtt.example.local"),
            )
            with patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(healthcheck(config, config_path), 1)

            state_path = _state_path(config_path, config.state_file)
            old = datetime.now(timezone.utc) - timedelta(hours=3)
            _save_state(state_path, {"last_success_at": old.isoformat()})
            with patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(healthcheck(config, config_path), 1)


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
        self.assertEqual(published["vw/euda/TESTVIN1234567890/status/car_captured_at"], "2026-01-02T03:04:05+00:00")
        self.assertNotEqual(published["vw/euda/TESTVIN1234567890/status/last_poll_at"], "")
        self.assertEqual(published["vw/euda/TESTVIN1234567890/status/service_version"], __version__)
        self.assertIsInstance(published["vw/euda/TESTVIN1234567890/status/data_age_seconds"], int)
        self.assertIsInstance(published["vw/euda/TESTVIN1234567890/status/stale"], bool)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/battery/soc"], 80)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/range/km"], 321)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/raw/range"], 321)
        self.assertEqual(published["car/garage/TESTVIN1234567890/drives/primary/level"], 80)
        self.assertEqual(published["car/garage/TESTVIN1234567890/drives/primary/range"], 321)

    def test_publish_dataset_stores_last_valid_odometer(self) -> None:
        fake_class = _recording_publisher_class()
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(host="mqtt.example.local", base_topic="vw/euda"),
        )
        raw_payload = {
            "Data": [
                {"key": "odometer", "dataFieldName": "mileage.value", "value": "63151"},
            ]
        }
        dataset = Dataset.from_json(raw_payload)
        state: dict[str, object] = {}

        with patch("vw_euda_mqtt.service.MqttPublisher", fake_class):
            publish_dataset(config, "TESTVIN1234567890", "dataset.zip", dataset, raw_payload, state=state)

        published = dict(fake_class.instances[-1].published)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/odometer/km"], 63151)
        self.assertEqual(state["last_odometer_km"], 63151)

    def test_publish_dataset_keeps_previous_odometer_when_new_value_is_zero(self) -> None:
        fake_class = _recording_publisher_class()
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(host="mqtt.example.local", base_topic="vw/euda", publish_carcompat=True),
        )
        raw_payload = {
            "Data": [
                {"key": "odometer", "dataFieldName": "mileage.value", "value": "0"},
            ]
        }
        dataset = Dataset.from_json(raw_payload)
        state: dict[str, object] = {"last_odometer_km": 63151}

        with patch("vw_euda_mqtt.service.MqttPublisher", fake_class):
            publish_dataset(config, "TESTVIN1234567890", "dataset.zip", dataset, raw_payload, state=state)

        published = dict(fake_class.instances[-1].published)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/odometer/km"], 63151)
        self.assertEqual(published["car/garage/TESTVIN1234567890/odometer"], 63151)
        self.assertEqual(state["last_odometer_km"], 63151)

    def test_publish_dataset_keeps_previous_odometer_when_new_value_decreases(self) -> None:
        fake_class = _recording_publisher_class()
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(host="mqtt.example.local", base_topic="vw/euda"),
        )
        raw_payload = {
            "Data": [
                {"key": "odometer", "dataFieldName": "mileage.value", "value": "60000"},
            ]
        }
        dataset = Dataset.from_json(raw_payload)
        state: dict[str, object] = {"last_odometer_km": 63151}

        with patch("vw_euda_mqtt.service.MqttPublisher", fake_class):
            publish_dataset(config, "TESTVIN1234567890", "dataset.zip", dataset, raw_payload, state=state)

        published = dict(fake_class.instances[-1].published)
        self.assertEqual(published["vw/euda/TESTVIN1234567890/odometer/km"], 63151)
        self.assertEqual(state["last_odometer_km"], 63151)

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
        self.assertNotEqual(published["vw/euda/_service/status/last_poll_at"], "")
        self.assertEqual(published["vw/euda/_service/status/service_version"], __version__)
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

    def test_publish_homeassistant_discovery_emits_sensor_and_binary_sensor_configs(self) -> None:
        publisher = _StandaloneRecorder()
        mqtt_config = MqttConfig(
            host="mqtt.example.local",
            base_topic="vw/euda",
            homeassistant_discovery_prefix="ha",
        )

        publish_homeassistant_discovery(publisher, mqtt_config, "TESTVIN1234567890")

        published = dict(publisher.published)
        soc = published["ha/sensor/vw_euda_testvin1234567890/battery_soc/config"]
        self.assertEqual(soc["name"], "Battery SOC")
        self.assertEqual(soc["unique_id"], "vw_euda_testvin1234567890_battery_soc")
        self.assertEqual(soc["state_topic"], "vw/euda/TESTVIN1234567890/battery/soc")
        self.assertEqual(soc["device_class"], "battery")
        self.assertEqual(soc["unit_of_measurement"], "%")
        self.assertEqual(soc["state_class"], "measurement")
        self.assertEqual(soc["availability"][0]["topic"], "vw/euda/TESTVIN1234567890/status/online")
        self.assertEqual(soc["availability"][0]["payload_available"], "true")
        self.assertEqual(soc["device"]["identifiers"], ["vw_euda_TESTVIN1234567890"])
        self.assertEqual(soc["device"]["sw_version"], __version__)

        doors = published["ha/binary_sensor/vw_euda_testvin1234567890/doors_locked/config"]
        self.assertEqual(doors["state_topic"], "vw/euda/TESTVIN1234567890/doors/locked")
        self.assertEqual(doors["payload_on"], "true")
        self.assertEqual(doors["payload_off"], "false")
        self.assertEqual(doors["device_class"], "lock")

    def test_publish_dataset_can_include_homeassistant_discovery(self) -> None:
        fake_class = _recording_publisher_class()
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(
                host="mqtt.example.local",
                base_topic="vw/euda",
                publish_homeassistant_discovery=True,
            ),
        )
        raw_payload = {
            "Data": [
                {"key": "soc", "dataFieldName": "battery_state_report.soc", "value": "80"},
            ]
        }
        dataset = Dataset.from_json(raw_payload)

        with patch("vw_euda_mqtt.service.MqttPublisher", fake_class):
            publish_dataset(config, "TESTVIN1234567890", "dataset.zip", dataset, raw_payload)

        published = dict(fake_class.instances[-1].published)
        self.assertEqual(
            published["homeassistant/sensor/vw_euda_testvin1234567890/battery_soc/config"]["state_topic"],
            "vw/euda/TESTVIN1234567890/battery/soc",
        )


class RunServiceTests(unittest.TestCase):
    def test_run_service_catches_unexpected_errors_in_once_mode(self) -> None:
        config = ServiceConfig(
            email="user@example.com",
            password="example-password",
            mqtt=MqttConfig(host="mqtt.example.local"),
        )

        with (
            patch("vw_euda_mqtt.service.poll_once", side_effect=RuntimeError("boom")),
            patch("vw_euda_mqtt.service.publish_error_status") as publish_error,
            patch("vw_euda_mqtt.service.LOG.exception"),
        ):
            asyncio.run(run_service(config, Path("config.json"), once=True, dry_run=True))

        publish_error.assert_called_once()


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
