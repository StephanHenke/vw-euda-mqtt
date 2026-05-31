# VW EU Data Act MQTT Service

Small standalone bridge for the Volkswagen EU Data Act portal.

It logs in to `eu-data-act.drivesomethinggreater.com`, downloads the newest
continuous-data ZIP for a VIN, extracts useful datapoints, and publishes them to
MQTT as retained topics.

This is based on the login and dataset approach from
<https://github.com/mikrohard/hass-vw-eu-data-act> (MIT).

## Prerequisites

1. Log in once at <https://eu-data-act.drivesomethinggreater.com/>.
2. Select the correct brand, for example `Audi`.
3. Use the same myAudi/VW account as in `config.json`.
4. Accept any account/portal terms, registration prompts, consent screens, or
   country/language prompts shown by Volkswagen.
5. Connect the vehicle.
6. Enable a continuous/customised data request with 15 minute frequency.
7. Wait until the portal shows ZIP datasets for the vehicle.

The service only downloads datasets that the portal already creates. It does not
create the data request.

## Run Locally

```powershell
cd C:\Users\steph\Documents\Entwicklungen\vw-euda-mqtt
Copy-Item config.example.json config.json
# edit config.json
uv run vw-euda-mqtt --config config.json --once --dry-run
uv run vw-euda-mqtt --config config.json --once
uv run vw-euda-mqtt --config config.json
```

## Run With Docker

```bash
cp config.example.json config.json
mkdir -p data
docker compose -f docker-compose.example.yml up -d --build
```

## MQTT Topics

Default base topic is `vw/euda/<vin>/`.

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

If the portal login or API poll fails, the service publishes retained error
state to `vw/euda/<vin>/status/...` when a VIN is configured. Without a VIN it
uses `vw/euda/_service/status/...`.

Set `mqtt.publish_raw` to `true` to publish all datapoints under
`raw/<sanitized-field-name>`.

Set `mqtt.publish_carcompat` to `true` only if you intentionally want to mirror
selected values to CarConnectivity-like topics under `car/garage/<vin>/...`.
Leave it off while the normal CarConnectivity container also publishes `car/#`.

## Current Notes

- `config.json` is intentionally ignored by Git because it contains account and
  MQTT credentials.
- `data/` is ignored and used only for runtime state.
- Datasets named `*_no_content_found.zip` are skipped; they mean the portal
  created an interval file without vehicle payload.
- Docker deployment currently needs sudo or Docker group access on the OpenHAB
  VM.
