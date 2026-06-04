# Changelog

All notable changes to this project are documented in this file.

The format follows the spirit of Keep a Changelog, and this project uses
semantic versioning.

## [0.1.1] - 2026-06-04

### Changed

- Publish raw datapoints losslessly under `raw/by_key/...` and
  `raw/by_field/...` when `mqtt.publish_raw` is enabled, so repeated field names
  in real VW/Audi datasets no longer overwrite each other.
- Document the full raw MQTT topic layout and topic index.
- Publish `status/car_captured_at` as an explicit alias for the latest
  `car_captured_time` value from the vehicle dataset.

## [0.1.0] - 2026-06-01

### Added

- Initial VW/Audi EU Data Act to MQTT bridge.
- Login flow for the EU Data Act portal, including VW Identity onboarding,
  terms confirmation, client consent, optional marketing consent skip, and
  email-verification guidance.
- Configurable Audi/VW portal settings, VIN/identifier selection, polling
  intervals, retry handling, and local state tracking.
- MQTT publishing for service status, curated vehicle datapoints, optional raw
  datapoints, and optional car-compatible topics.
- Dockerfile and Docker Compose examples.
- GitHub Actions workflow for multi-architecture Docker image publishing to
  GitHub Container Registry and Docker Hub.
- Docker Hub project description and GitHub linkback.
- German and English README files.
- GitHub social preview image.
- Unit tests for API parsing helpers, dataset extraction, configuration,
  scheduling, MQTT payload formatting, and publishing behavior.

### Changed

- Removed the local MQTT host from public examples.
- Documented the current limitation that VW/Audi appears to provide the data
  delivery structure, but no confirmed path is known yet for clean, timely data
  population in the portal.
- Documented that username/password authentication is only a pragmatic current
  workaround and that an account-issued API key or token would be a cleaner
  long-term solution.

### Security

- Added `.dockerignore` so local configuration, access notes, state data,
  virtual environments, and other private files are excluded from Docker build
  contexts.
