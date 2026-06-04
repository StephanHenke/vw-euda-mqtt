# openHAB Integration

## Deutsch

openHAB kann die von `vw-euda-mqtt` veröffentlichten Topics über das MQTT
Binding als Generic MQTT Thing einbinden. Die Integration ist read-only: Das
Projekt stellt Fahrzeugdaten bereit, sendet aber keine Steuerbefehle an das
Fahrzeug.

Die Beispiele orientieren sich am offiziellen openHAB MQTT Things and Channels
Binding. openHAB benötigt zuerst ein Broker Thing, danach ein Topic Thing mit
Channels für die einzelnen MQTT-State-Topics.

## Dateien

Beispiele liegen unter:

```text
openhab/vw-euda-mqtt.things
openhab/vw-euda-mqtt.items
```

## Vorbereitung

1. In openHAB das MQTT Binding installieren.
2. Einen MQTT Broker als Thing anlegen oder das Beispiel in
   `openhab/vw-euda-mqtt.things` anpassen.
3. In den Beispielen ersetzen:
   - `mqtt.example.local` durch deinen MQTT-Broker.
   - `WAUZZZ00000000000` durch deine VIN.
   - optional `vw/euda`, falls du `mqtt.base_topic` geändert hast.

## Things-Beispiel

Die Datei `openhab/vw-euda-mqtt.things` legt ein Broker Thing und ein Generic
MQTT Topic Thing an. Das Topic Thing nutzt:

```text
availabilityTopic="vw/euda/<VIN>/status/online"
payloadAvailable="true"
payloadNotAvailable="false"
```

Dadurch wird das openHAB Thing offline, wenn der Dienst `status/online=false`
publiziert.

Enthaltene Channels:

- Battery SOC
- Target SOC
- Charge Power
- Odometer
- Range
- Charging State
- Connected
- Data Stale
- Doors Locked
- Car Captured At
- Last Success
- Service Version
- Error Type
- Error

## Items-Beispiel

Die Datei `openhab/vw-euda-mqtt.items` verlinkt die Channels auf Items. Die
Zahlenwerte werden bewusst als einfache `Number` Items angelegt, damit die
Beispiele ohne zusätzliche Unit- oder Transformation-Konfiguration funktionieren.

Beispiel:

```text
Number Audi_Battery_SOC "Battery SOC [%.0f %%]" {
  channel="mqtt:topic:local:vw_euda_vehicle:battery_soc"
}
```

## Hinweise

- `status/error` kann längere Texte enthalten und ist als `String` eingebunden.
- `status/stale` ist ein guter Indikator für Automationen, wenn das Portal keine
  frischen Fahrzeugdaten liefert.
- `status/car_captured_at` ist der Fahrzeug-/Backend-Zeitpunkt aus dem Dataset.
  `status/last_success_at` ist der Zeitpunkt, an dem der Dienst erfolgreich
  publiziert hat.

## English

openHAB can consume the topics published by `vw-euda-mqtt` through the MQTT
Binding as a Generic MQTT Thing. The integration is read-only: this project
publishes vehicle data but does not send vehicle control commands.

Example files:

```text
openhab/vw-euda-mqtt.things
openhab/vw-euda-mqtt.items
```

Setup:

1. Install the openHAB MQTT Binding.
2. Configure an MQTT Broker Thing.
3. Replace `mqtt.example.local`, `WAUZZZ00000000000`, and optionally `vw/euda`
   in the example files.
4. Copy or adapt the Things and Items into your openHAB configuration.

The Generic MQTT Thing uses `vw/euda/<VIN>/status/online` as availability topic
with `true` and `false` payloads.

Official reference:

- https://www.openhab.org/addons/bindings/mqtt.generic/
