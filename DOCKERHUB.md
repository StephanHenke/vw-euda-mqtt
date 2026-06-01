# VW EU Data Act MQTT Service

Docker image for `vw-euda-mqtt`, a small bridge that retrieves vehicle datasets
made available through the Volkswagen Group EU Data Act portal and publishes
structured values to MQTT.

Project and source code:

https://github.com/StephanHenke/vw-euda-mqtt

## Pull

```bash
docker pull stephanhenke/vw-euda-mqtt:latest
```

The same image is also available from GitHub Container Registry:

```bash
docker pull ghcr.io/stephanhenke/vw-euda-mqtt:latest
```

## Purpose

The service is intended to make VW/Audi EU Data Act vehicle data available to
smart home systems, energy management systems, and local automation platforms by
publishing selected data points as retained MQTT topics.

Typical topics include:

```text
vw/euda/<vin>/battery/soc
vw/euda/<vin>/range/km
vw/euda/<vin>/charging/state
vw/euda/<vin>/odometer/km
vw/euda/<vin>/status/connected
```

## Quick Start

Create a `config.json` from the example in the GitHub repository, then run:

```bash
docker run --rm \
  -v "$PWD/config.json:/config/config.json:ro" \
  -v "$PWD/data:/config/data" \
  stephanhenke/vw-euda-mqtt:latest \
  --config /config/config.json
```

Docker Compose examples and full configuration documentation are maintained in
the GitHub repository:

https://github.com/StephanHenke/vw-euda-mqtt

## Current Limitation

The bridge is built against the data transfer that Volkswagen Group exposes
through the EU Data Act portal. Current Audi/VW portal tests have so far only
produced `*_no_content_found.zip` placeholder files. At the moment, no reliable
procedure is known in this project that makes vehicle data appear cleanly in the
portal after the data request has been created.

This means the container can be technically connected and healthy while still
having no vehicle values to publish.

## Tags and Architectures

Published tags include:

```text
latest
main
```

The image is built for:

```text
linux/amd64
linux/arm64
```

## License

MIT License. See the GitHub repository for source code and license details:

https://github.com/StephanHenke/vw-euda-mqtt
