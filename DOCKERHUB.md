# VW Group Vehicle2MQTT

Docker image for `vwgroup-vehicle2mqtt`, a small bridge that retrieves vehicle
datasets made available through the Volkswagen Group EU Data Act portal and
publishes structured values to MQTT.

Project and source code:

https://github.com/StephanHenke/vwgroup-vehicle2mqtt

## Pull

```bash
docker pull stephanhenke/vwgroup-vehicle2mqtt:latest
```

The same image is also available from GitHub Container Registry:

```bash
docker pull ghcr.io/stephanhenke/vwgroup-vehicle2mqtt:latest
```

## Purpose

The service is intended to make VW/Audi EU Data Act vehicle data available to
smart home systems, energy management systems, and local automation platforms by
publishing selected data points to MQTT. MQTT retain is disabled by default and
must be enabled explicitly with `mqtt.retain=true`. When `publish_raw` is
enabled, it publishes cataloged datapoints under `structured/...` and original
ZIP members under `raw/file/<index>/...`. Raw file contents are live-published
only and are not retained.
Home Assistant MQTT autodiscovery can be enabled through
`mqtt.publish_homeassistant_discovery`. Discovery config topics are retained by
default through the separate `mqtt.homeassistant_discovery_retain` setting, even
when vehicle state retention stays disabled. openHAB Generic MQTT Thing examples
are available in the GitHub repository.

Typical topics include:

```text
vw/euda/<vin>/battery/soc
vw/euda/<vin>/range/km
vw/euda/<vin>/charging/state
vw/euda/<vin>/odometer/km
vw/euda/<vin>/status/car_captured_at
vw/euda/<vin>/status/connected
vw/euda/<vin>/structured/by_name/soc/value
vw/euda/<vin>/structured/by_key/<datapoint_key>/name
vw/euda/<vin>/raw/file/0/filename
vw/euda/<vin>/raw/file/0/content
```

## Quick Start

Create a `config.json` from the example in the GitHub repository, then run:

```bash
docker run --rm \
  -v "$PWD/config.json:/config/config.json:ro" \
  -v "$PWD/data:/config/data" \
  stephanhenke/vwgroup-vehicle2mqtt:latest \
  --config /config/config.json
```

Docker Compose examples and full configuration documentation are maintained in
the GitHub repository:

https://github.com/StephanHenke/vwgroup-vehicle2mqtt

## Diagnostics and Health

Check portal, vehicle, dataset listing, and MQTT access without printing
configured secrets:

```bash
docker run --rm \
  -v "$PWD/config.json:/config/config.json:ro" \
  -v "$PWD/data:/config/data" \
  stephanhenke/vwgroup-vehicle2mqtt:latest \
  --config /config/config.json --diagnose
```

The image includes a Docker `HEALTHCHECK`. It reads the configured `state_file`
and reports unhealthy when no successful dataset publish is recorded or the last
one is older than four polling intervals, with a minimum threshold of one hour.

## Current Limitation

The bridge is built against the data transfer that Volkswagen Group exposes
through the EU Data Act portal. Current Audi/VW portal tests have shown that
real datasets can appear, but the datadelivery list endpoint can still
intermittently return backend errors.

This means the container can publish the last successful vehicle data as
retained MQTT state only when `mqtt.retain=true`; otherwise it publishes live
values while also reporting transient `PendingData` status during later polls.

## Tags and Architectures

Published tags include:

```text
latest
main
0.2.0
0.1.3
0.1.2
```

The image is built for:

```text
linux/amd64
linux/arm64
```

## License

MIT License. See the GitHub repository for source code and license details:

https://github.com/StephanHenke/vwgroup-vehicle2mqtt
