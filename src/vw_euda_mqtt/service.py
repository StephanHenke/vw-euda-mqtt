"""Command-line VW EU Data Act to MQTT bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
import paho.mqtt.client as mqtt

from .api import ApiError, AuthError, EudaApiClient, NO_CONTENT_SUFFIX, PortalConfig
from .data import Dataset, curated_values, raw_values

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "vw-euda-mqtt"
    base_topic: str = "vw/euda"
    retain: bool = True
    qos: int = 0
    publish_raw: bool = False
    publish_carcompat: bool = False
    carcompat_base_topic: str = "car"


@dataclass(frozen=True)
class ServiceConfig:
    email: str
    password: str
    brand: str = "AUDI"
    country: str = "de"
    language: str = "de"
    vin: str | None = None
    identifier: str | None = None
    poll_interval_seconds: int = 900
    retry_interval_seconds: int = 60
    publish_unchanged: bool = False
    state_file: str = "state.json"
    mqtt: MqttConfig | None = None

    @classmethod
    def from_file(cls, path: Path) -> "ServiceConfig":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        mqtt_raw = raw.get("mqtt") or {}
        mqtt_config = MqttConfig(
            host=mqtt_raw.get("host", "localhost"),
            port=int(mqtt_raw.get("port", 1883)),
            username=mqtt_raw.get("username") or None,
            password=mqtt_raw.get("password") or None,
            client_id=mqtt_raw.get("client_id") or "vw-euda-mqtt",
            base_topic=(mqtt_raw.get("base_topic") or "vw/euda").strip("/"),
            retain=bool(mqtt_raw.get("retain", True)),
            qos=int(mqtt_raw.get("qos", 0)),
            publish_raw=bool(mqtt_raw.get("publish_raw", False)),
            publish_carcompat=bool(mqtt_raw.get("publish_carcompat", False)),
            carcompat_base_topic=(mqtt_raw.get("carcompat_base_topic") or "car").strip("/"),
        )
        return cls(
            email=raw["email"],
            password=raw["password"],
            brand=raw.get("brand") or "AUDI",
            country=raw.get("country") or "de",
            language=raw.get("language") or "de",
            vin=raw.get("vin") or None,
            identifier=raw.get("identifier") or None,
            poll_interval_seconds=int(raw.get("poll_interval_seconds", 900)),
            retry_interval_seconds=int(raw.get("retry_interval_seconds", 60)),
            publish_unchanged=bool(raw.get("publish_unchanged", False)),
            state_file=raw.get("state_file") or "state.json",
            mqtt=mqtt_config,
        )

    @property
    def portal(self) -> PortalConfig:
        return PortalConfig(
            email=self.email,
            password=self.password,
            brand=self.brand,
            country=self.country,
            language=self.language,
        )


class MqttPublisher:
    def __init__(self, config: MqttConfig, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run
        self.client: mqtt.Client | None = None

    def __enter__(self):
        if self.dry_run:
            return self
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.config.client_id)
        if self.config.username:
            client.username_pw_set(self.config.username, self.config.password)
        client.connect(self.config.host, self.config.port, keepalive=60)
        client.loop_start()
        self.client = client
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()

    def publish(self, topic: str, value: Any) -> None:
        payload = _mqtt_payload(value)
        if self.dry_run:
            print(f"{topic} {payload}")
            return
        assert self.client is not None
        result = self.client.publish(
            topic,
            payload,
            qos=self.config.qos,
            retain=self.config.retain,
        )
        result.wait_for_publish(timeout=10)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed for {topic}: rc={result.rc}")


def _mqtt_payload(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _state_path(config_path: Path, state_file: str) -> Path:
    path = Path(state_file)
    return path if path.is_absolute() else config_path.parent / path


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _status_vin(config: ServiceConfig, vin: str | None = None) -> str:
    return vin or config.vin or "_service"


def _created_on(entry: dict) -> datetime | None:
    raw = entry.get("createdOn")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    name = entry.get("name", "").rsplit(".", 1)[0]
    for part in reversed(name.split("_")):
        try:
            return datetime.strptime(part, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _next_sleep(listing: list[dict], poll_interval_seconds: int, retry_interval_seconds: int) -> int:
    timestamps = [timestamp for entry in listing if (timestamp := _created_on(entry))]
    if not timestamps:
        return retry_interval_seconds
    newest = max(timestamps)
    target = newest + timedelta(seconds=poll_interval_seconds + 45)
    delta = target - datetime.now(timezone.utc)
    if delta.total_seconds() > 30:
        return max(30, int(delta.total_seconds()))
    return retry_interval_seconds


def _is_dataset_listing_pending(err: ApiError) -> bool:
    text = str(err)
    return (
        "/datadelivery/" in text
        and "/list" in text
        and any(f"HTTP {status}" in text for status in (404, 500, 502, 503, 504))
    )


async def _select_vehicle_and_identifier(client: EudaApiClient, config: ServiceConfig) -> tuple[str, str]:
    vin = config.vin
    if not vin:
        vehicles = await client.async_list_vehicles()
        if not vehicles:
            raise ApiError("No vehicles returned by EU Data Act portal")
        if len(vehicles) > 1:
            names = ", ".join(f"{item.get('vin')} ({item.get('nickname') or 'no name'})" for item in vehicles)
            raise ApiError(f"Multiple vehicles found, set vin in config: {names}")
        vin = vehicles[0]["vin"]

    identifier = config.identifier
    if not identifier:
        metadata = await client.async_get_metadata(vin)
        identifier = metadata.get("Identifier")
        if not identifier:
            raise ApiError(
                "No continuous-data Identifier returned. Enable customised continuous data "
                "for this VIN in the EU Data Act portal first."
            )
    return vin, identifier


async def poll_once(config: ServiceConfig, config_path: Path, dry_run: bool = False) -> int:
    state_path = _state_path(config_path, config.state_file)
    state = _load_state(state_path)

    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
        client = EudaApiClient(session, config.portal)
        vin, identifier = await _select_vehicle_and_identifier(client, config)
        try:
            listing = await client.async_list_datasets(vin, identifier)
        except ApiError as err:
            if not _is_dataset_listing_pending(err):
                raise
            message = f"Dataset listing not available yet for identifier {identifier}: {err}"
            LOG.warning(message)
            publish_status(
                config,
                vin,
                connected=True,
                error=message,
                error_type="PendingData",
                dry_run=dry_run,
            )
            return config.retry_interval_seconds
        content = sorted(
            (entry for entry in listing if entry.get("name") and not entry["name"].endswith(NO_CONTENT_SUFFIX)),
            key=lambda entry: _created_on(entry) or datetime.min.replace(tzinfo=timezone.utc),
        )
        if not content:
            message = "No content datasets available yet"
            LOG.info(message)
            publish_status(
                config,
                vin,
                connected=True,
                error=message,
                error_type="PendingData",
                dry_run=dry_run,
            )
            return _next_sleep(listing, config.poll_interval_seconds, config.retry_interval_seconds)

        newest = content[-1]
        name = newest["name"]
        if not config.publish_unchanged and state.get("last_dataset") == name:
            LOG.info("No new dataset: %s", name)
            publish_status(config, vin, connected=True, dry_run=dry_run)
            return _next_sleep(listing, config.poll_interval_seconds, config.retry_interval_seconds)

        payload = await client.async_download_dataset(vin, identifier, name)
        dataset = Dataset.from_json(payload)
        publish_dataset(config, vin, name, dataset, payload, dry_run=dry_run)

        state.update(
            {
                "vin": vin,
                "identifier": identifier,
                "last_dataset": name,
                "last_publish": datetime.now(timezone.utc).isoformat(),
            }
        )
        if not dry_run:
            _save_state(state_path, state)
        return _next_sleep(listing, config.poll_interval_seconds, config.retry_interval_seconds)


def publish_dataset(
    config: ServiceConfig,
    vin: str,
    dataset_name: str,
    dataset: Dataset,
    raw_payload: dict,
    *,
    dry_run: bool = False,
) -> None:
    assert config.mqtt is not None
    base = f"{config.mqtt.base_topic}/{vin}"
    values: dict[str, Any] = {
        "status/online": True,
        "status/connected": True,
        "status/error": "",
        "status/error_type": "",
        "status/last_dataset": dataset_name,
        "status/captured_at": dataset.captured_at.isoformat() if dataset.captured_at else "",
        "status/car_captured_at": dataset.captured_at.isoformat() if dataset.captured_at else "",
        "status/last_success_at": datetime.now(timezone.utc).isoformat(),
        "json": raw_payload,
    }
    values.update(curated_values(dataset))
    if config.mqtt.publish_raw:
        values.update(raw_values(dataset))

    with MqttPublisher(config.mqtt, dry_run=dry_run) as publisher:
        for topic, value in sorted(values.items()):
            publisher.publish(f"{base}/{topic}", value)
        if config.mqtt.publish_carcompat:
            publish_carcompat(publisher, config.mqtt, vin, values)


def publish_status(
    config: ServiceConfig,
    vin: str | None = None,
    *,
    connected: bool,
    error: str = "",
    error_type: str = "",
    dry_run: bool = False,
) -> None:
    assert config.mqtt is not None
    base = f"{config.mqtt.base_topic}/{_status_vin(config, vin)}/status"
    now = datetime.now(timezone.utc).isoformat()
    values: dict[str, Any] = {
        "online": connected,
        "connected": connected,
        "error": error,
        "error_type": error_type,
        "last_error_at": "",
        "last_status_at": now,
    }
    if connected:
        values["last_success_at"] = now
    else:
        values["last_error_at"] = now

    with MqttPublisher(config.mqtt, dry_run=dry_run) as publisher:
        for topic, value in sorted(values.items()):
            publisher.publish(f"{base}/{topic}", value)


def publish_error_status(
    config: ServiceConfig,
    err: Exception,
    *,
    dry_run: bool = False,
) -> None:
    try:
        publish_status(
            config,
            connected=False,
            error=str(err),
            error_type=type(err).__name__,
            dry_run=dry_run,
        )
    except Exception as publish_err:  # pragma: no cover - logging fallback only
        LOG.error("Could not publish MQTT error status: %s", publish_err)


def publish_carcompat(
    publisher: MqttPublisher,
    mqtt_config: MqttConfig,
    vin: str,
    values: dict[str, Any],
) -> None:
    base = f"{mqtt_config.carcompat_base_topic}/garage/{vin}"
    mapping = {
        "battery/soc": f"{base}/drives/primary/level",
        "range/km": f"{base}/drives/primary/range",
        "odometer/km": f"{base}/odometer",
        "charging/state": f"{base}/charging/state",
    }
    for source, target in mapping.items():
        if source in values:
            publisher.publish(target, values[source])


async def run_service(config: ServiceConfig, config_path: Path, once: bool, dry_run: bool) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    while not stop.is_set():
        try:
            sleep_seconds = await poll_once(config, config_path, dry_run=dry_run)
            LOG.info("Poll completed, next check in %ss", sleep_seconds)
        except AuthError as err:
            LOG.error("Authentication failed: %s", err)
            publish_error_status(config, err, dry_run=dry_run)
            sleep_seconds = config.retry_interval_seconds
        except ApiError as err:
            LOG.error("Poll failed: %s", err)
            publish_error_status(config, err, dry_run=dry_run)
            sleep_seconds = config.retry_interval_seconds
        if once:
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=sleep_seconds)
        except asyncio.TimeoutError:
            pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VW EU Data Act to MQTT bridge")
    parser.add_argument("--config", required=True, type=Path, help="Path to config JSON")
    parser.add_argument("--once", action="store_true", help="Run one poll and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print MQTT publishes instead of sending")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = ServiceConfig.from_file(args.config)
    try:
        asyncio.run(run_service(config, args.config, once=args.once, dry_run=args.dry_run))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
