# Home Assistant MQTT Autodiscovery

## Deutsch

`vwgroup-vehicle2mqtt` kann Home-Assistant-kompatible MQTT-Discovery-Nachrichten
veröffentlichen. Home Assistant legt die Sensoren dann automatisch unter einem
gemeinsamen Gerät an.

Die Umsetzung orientiert sich an der offiziellen Home-Assistant-MQTT-Discovery:
Discovery-Topics liegen standardmäßig unter `homeassistant/.../config`, die
Payloads enthalten `unique_id`, `state_topic`, Device-Informationen und
Availability-Informationen. Die Discovery-Payloads werden retained publiziert,
wenn `mqtt.homeassistant_discovery_retain` aktiv ist. Dieser Schalter ist
standardmäßig `true`, sobald Discovery überhaupt aktiviert wird.

## Voraussetzungen

- Home Assistant mit eingerichteter MQTT-Integration.
- MQTT Discovery ist in Home Assistant aktiviert. Standardmäßig nutzt Home
  Assistant den Discovery-Prefix `homeassistant`.
- `vwgroup-vehicle2mqtt` und Home Assistant nutzen denselben MQTT-Broker.
- `mqtt.homeassistant_discovery_retain` sollte `true` bleiben, damit Home
  Assistant die Discovery-Konfiguration nach einem Neustart sofort wieder
  bekommt.
- `mqtt.retain` kann trotzdem `false` bleiben, wenn Fahrzeugwerte nicht retained
  im Broker liegen sollen.

## Konfiguration

In `config.json` im MQTT-Block aktivieren:

```json
{
  "mqtt": {
    "host": "mqtt.example.local",
    "base_topic": "vw/euda",
    "retain": false,
    "publish_homeassistant_discovery": true,
    "homeassistant_discovery_prefix": "homeassistant",
    "homeassistant_discovery_retain": true
  }
}
```

Ein minimales Beispiel liegt unter:

```text
homeassistant/mqtt-autodiscovery.example.json
```

Danach den Dienst neu starten oder einmalig ausführen:

```bash
docker compose up -d
docker logs -f vwgroup-vehicle2mqtt
```

oder lokal:

```bash
uv run vwgroup-vehicle2mqtt --config config.json --once
```

## Was veröffentlicht wird

Der Dienst veröffentlicht Discovery-Konfigurationen unter:

```text
homeassistant/sensor/vw_euda_<vin>/<object_id>/config
homeassistant/binary_sensor/vw_euda_<vin>/<object_id>/config
```

Beispiele für erzeugte Home-Assistant-Entities:

- Battery SOC
- Battery Target SOC
- Charge Power
- Odometer
- Range
- Charging State
- Doors Locked
- Connected
- Data Stale
- Car Captured At
- Last Success
- Service Version

Alle Entities verwenden:

- `unique_id` im Muster `vw_euda_<vin>_<object>`
- `state_topic` unter `vw/euda/<vin>/...`
- `availability` über `vw/euda/<vin>/status/online`
- ein gemeinsames Gerät `VW Group Vehicle2MQTT <letzte 6 VIN-Zeichen>`

## Historische Werte

Home Assistant speichert MQTT-State-Updates im Recorder mit dem Zeitpunkt, an
dem Home Assistant die Nachricht verarbeitet. `car_captured_at` bleibt als
Fahrzeugzeitpunkt sichtbar, setzt aber nicht den Recorder-Zeitstempel. Für echte
rückdatierte historische Werte ist MQTT Discovery deshalb nicht der passende
Weg. Details und der openHAB-Backfill-Weg stehen in [history.md](history.md).

## Troubleshooting

Wenn in Home Assistant keine Entities erscheinen:

1. Prüfen, ob Home Assistant MQTT eingerichtet hat.
2. Prüfen, ob Discovery aktiv ist und der Prefix zu
   `homeassistant_discovery_prefix` passt.
3. Prüfen, ob `vwgroup-vehicle2mqtt` mindestens einmal ein echtes Dataset publiziert
   hat. Discovery wird bei erfolgreichem Dataset-Publish gesendet.
4. MQTT retained Config prüfen:

```bash
mosquitto_sub -h mqtt.example.local -v -t 'homeassistant/#'
```

5. Falls alte Test-Entities hängen bleiben, die retained Discovery-Topics im
   Broker löschen oder die Entities in Home Assistant entfernen.

## English

`vwgroup-vehicle2mqtt` can publish Home Assistant compatible MQTT discovery messages.
Home Assistant can then create the vehicle sensors automatically as one shared
device.

Enable it in the MQTT section of `config.json`:

```json
{
  "mqtt": {
    "host": "mqtt.example.local",
    "base_topic": "vw/euda",
    "retain": false,
    "publish_homeassistant_discovery": true,
    "homeassistant_discovery_prefix": "homeassistant",
    "homeassistant_discovery_retain": true
  }
}
```

Requirements:

- Home Assistant MQTT integration is configured.
- MQTT discovery is enabled.
- Home Assistant and `vwgroup-vehicle2mqtt` use the same broker.
- Keep `mqtt.homeassistant_discovery_retain=true` for reliable discovery after
  Home Assistant restarts.
- `mqtt.retain` can stay `false` when vehicle state should not be retained.

Discovery configs are published below:

```text
homeassistant/sensor/vw_euda_<vin>/<object_id>/config
homeassistant/binary_sensor/vw_euda_<vin>/<object_id>/config
```

The generated entities share one Home Assistant device and use
`vw/euda/<vin>/status/online` as availability topic.

MQTT state updates are recorded with the Home Assistant receive time. The
vehicle-side `car_captured_at` timestamp is visible as data, but it does not
backdate Recorder history. See [history.md](history.md) for the history
backfill approach.

Official reference:

- https://www.home-assistant.io/integrations/mqtt
- https://www.home-assistant.io/integrations/sensor.mqtt/
- https://www.home-assistant.io/integrations/binary_sensor.mqtt/
