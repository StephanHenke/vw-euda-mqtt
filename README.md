# VW EU Data Act MQTT Service

[Deutsch](README.de.md)

This project retrieves vehicle data made available through the Volkswagen Group
EU Data Act portal and forwards it in a structured form to an MQTT broker. The
goal is to make these values available to smart home systems, energy management
systems, and similar local automation platforms.

The service logs in to `eu-data-act.drivesomethinggreater.com`, follows the
portal's brand-specific login redirect, downloads the latest continuous-data ZIP
for a VIN, extracts useful data points, and publishes them as retained MQTT
topics.

The login and dataset approach is based on
<https://github.com/mikrohard/hass-vw-eu-data-act> (MIT).

## What It Does

- Logs in with the VW Group account configured in `config.json`.
- Selects the configured brand through the portal redirect, for example
  `brand=AUDI&method=login`.
- Handles required VW/Audi Identity onboarding steps.
- Reads continuous-data metadata and dataset ZIP files.
- Skips `*_no_content_found.zip` files because they do not contain vehicle
  payload.
- Publishes normalized vehicle values and optional raw data to MQTT.
- Makes the data available for smart home and energy management use cases.

This service does not create the EU Data Act data request. It only consumes ZIP
datasets that the portal has already generated.

## Current Limitation

The service is implemented against the data transfer that Volkswagen Group
exposes through the EU Data Act portal: it logs in, reads the active data
request metadata, lists generated ZIP datasets, skips empty placeholder ZIPs,
downloads real ZIP payloads, and publishes their contents to MQTT.

In practice, current Audi/VW portal tests have only produced
`*_no_content_found.zip` placeholder files so far. At the moment, no reliable
procedure is known in this project that makes vehicle data appear cleanly in the
portal after the data request has been created. This means the bridge can be
technically connected and healthy while still having no vehicle values to
publish.

## Portal Setup

1. Open <https://eu-data-act.drivesomethinggreater.com/> in a browser.
2. Select the correct brand, for example `Audi`.
3. Log in with the same myAudi/VW account used in `config.json`.
4. Complete any terms, registration, country/language, or consent prompts.
5. Make sure the vehicle is connected and the VIN is correct.
6. Enable a continuous/customised data request with a 15-minute frequency.
7. Wait until ZIP datasets are visible for the vehicle.

Right after setup this state is normal:

```text
No content datasets available yet
```

It means login, brand selection, and metadata access work, but the portal has
only generated `*_no_content_found.zip` files so far. The service keeps polling
and will process the first ZIP with real content automatically.

## VW/Audi Identity Onboarding

Even when `brand` is set to `AUDI`, the login pages can still say
`Volkswagen ID`. Audi uses the VW Group Identity backend.

For login, the service first calls the portal's official brand redirect
endpoint, for example:

```text
/services/redirect/authentication?brand=AUDI&method=login
```

It then follows the returned OIDC authorize URL. This avoids using the wrong
Identity client for Audi vehicles.

Depending on account state, the first non-browser login can hit these pages:

- `terms-and-conditions`: required IdentityKit terms and privacy documents are
  confirmed automatically.
- `consent/users`: required OAuth scopes for basic profile and vehicle access
  are granted automatically.
- `consent/marketing`: optional marketing or personalised communication consent
  is skipped automatically.
- `verification/email-sent`: Volkswagen sent a verification email. Open the link
  in that email, then restart the service.

## Configuration

Copy the example configuration:

```bash
cp config.example.json config.json
```

Important fields:

- `email` / `password`: myAudi/VW account credentials.
- `brand`: use `AUDI` for Audi vehicles.
- `country` / `language`: locale used by the portal, for example `de`.
- `vin`: vehicle VIN. If empty, the service tries to auto-select a single
  vehicle.
- `identifier`: can stay empty. The service reads the continuous-data
  identifier from portal metadata.
- `poll_interval_seconds`: default `900`, matching 15-minute datasets.
- `mqtt.host`, `mqtt.port`, `mqtt.username`, `mqtt.password`: MQTT broker
  settings.
- `mqtt.base_topic`: default `vw/euda`.
- `mqtt.publish_raw`: also publish all raw data fields under `raw/...`.
- `mqtt.publish_carcompat`: optionally mirror selected values under
  `car/garage/<vin>/...`.

`config.json` contains secrets and is intentionally ignored by Git.

## Local Usage

Debug once without publishing to MQTT:

```bash
uv run vw-euda-mqtt --config config.json --once --dry-run --debug
```

Run once without MQTT publishing:

```bash
uv run vw-euda-mqtt --config config.json --once --dry-run
```

Run once and publish to MQTT:

```bash
uv run vw-euda-mqtt --config config.json --once
```

Run continuously:

```bash
uv run vw-euda-mqtt --config config.json
```

## Docker

Prebuilt images are published to GitHub Container Registry. No Docker Hub
account is required:

```bash
docker pull ghcr.io/stephanhenke/vw-euda-mqtt:latest
```

Use the published image with Docker Compose:

```bash
cp config.example.json config.json
cp docker-compose.example.yml docker-compose.yml
mkdir -p data
docker compose up -d
docker logs -f vw-euda-mqtt
```

For local development, build the image from this checkout:

```bash
cp config.example.json config.json
mkdir -p data
docker compose up -d --build
docker logs -f vw-euda-mqtt
```

Rebuild after code changes:

```bash
docker compose up -d --build
```

## MQTT Topics

Default base topic:

```text
vw/euda/<vin>/
```

Selected topics:

- `status/online`
- `status/connected`
- `status/error`
- `status/error_type`
- `status/last_status_at`
- `status/last_success_at`
- `status/last_error_at`
- `status/last_dataset`
- `status/captured_at`
- `battery/soc`
- `battery/target_soc`
- `battery/charge_power_kw`
- `odometer/km`
- `range/km`
- `charging/state`
- `charging/mode`
- `charging/scenario`
- `doors/locked`
- `parking_brake`
- `json`

If login or polling fails, the service publishes retained error state under:

```text
vw/euda/<vin>/status/...
```

If no VIN is configured, it uses:

```text
vw/euda/_service/status/...
```

## Troubleshooting

`Authentication failed: terms-and-conditions`

VW Identity still requested terms or registration. The service now handles this
automatically. If it appears again, run with `--debug` and check the landing URL.

`verification/email-sent`

Volkswagen sent a verification email. Open the link in that email, then restart
the service.

`No continuous-data Identifier returned`

The VIN does not have an active continuous/customised data request in the EU
Data Act portal.

`No content datasets available yet`

Login, brand selection, and identifier lookup work. The portal currently only
generates `*_no_content_found.zip` files. Wait until a ZIP with real content is
available. Current testing has not yet identified a reliable way to make Audi/VW
vehicle data arrive in the EU Data Act portal; the service will process it
automatically once the portal provides a non-empty dataset.

`HTTP 401`

Usually means the wrong brand/Identity client was used or the portal login
expired. Run with `--debug` and check whether login lands on `/de/de/user.html`.

`HTTP 500` while listing datasets

Can be a transient portal backend error. The service retries after
`retry_interval_seconds`.

## Security Notes

Using account email and password is a pragmatic workaround for the current
browser-oriented portal flow. It is not the preferred long-term design. In this
project's view, a cleaner solution would be a dedicated API key or token issued
through the user's VW/Audi account, so third-party services can be authorized
without storing the account password.

- `config.json` is ignored because it contains account and MQTT credentials.
- `access.txt` is ignored because it can contain deployment host credentials.
- `data/` is ignored and only stores runtime state.
- Do not commit real passwords, personal VINs, or tokens if the repository is
  public.
