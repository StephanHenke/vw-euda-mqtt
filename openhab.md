# openHAB Integration

## Deutsch

openHAB kann die von `vwgroup-vehicle2mqtt` veröffentlichten Topics über das MQTT
Binding als Generic MQTT Thing einbinden. Die Integration ist read-only: Das
Projekt stellt Fahrzeugdaten bereit, sendet aber keine Steuerbefehle an das
Fahrzeug.

Die Beispiele orientieren sich am offiziellen openHAB MQTT Things and Channels
Binding. openHAB benötigt zuerst ein Broker Thing, danach ein Topic Thing mit
Channels für die einzelnen MQTT-State-Topics.

## Dateien

Beispiele liegen unter:

```text
openhab/vwgroup-vehicle2mqtt.things
openhab/vwgroup-vehicle2mqtt.items
openhab/vwgroup-vehicle2mqtt-history.items
openhab/vwgroup-vehicle2mqtt-history.js
```

## Vorbereitung

1. In openHAB das MQTT Binding installieren.
2. Einen MQTT Broker als Thing anlegen oder das Beispiel in
   `openhab/vwgroup-vehicle2mqtt.things` anpassen.
3. In den Beispielen ersetzen:
   - `mqtt.example.local` durch deinen MQTT-Broker.
   - `TESTVIN1234567890` durch deine VIN.
   - optional `vw/euda`, falls du `mqtt.base_topic` geändert hast.

## Things-Beispiel

Die Datei `openhab/vwgroup-vehicle2mqtt.things` legt ein Broker Thing und ein Generic
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
- History Batch JSON

## Items-Beispiel

Die Datei `openhab/vwgroup-vehicle2mqtt.items` verlinkt die Channels auf Items. Die
Zahlenwerte werden bewusst als einfache `Number` Items angelegt, damit die
Beispiele ohne zusätzliche Unit- oder Transformation-Konfiguration funktionieren.

Beispiel:

```text
Number Audi_Battery_SOC "Battery SOC [%.0f %%]" {
  channel="mqtt:topic:local:vw_euda_vehicle:battery_soc"
}
```

## Historischer Backfill

Wenn `mqtt.publish_history=true` aktiv ist, sendet der Dienst zusätzlich
`vw/euda/<VIN>/history/batch/json`. Dieses Topic enthält mehrere Werte eines
Datenpunkts mit ihrem jeweiligen `car_captured_at`.

Die Datei `openhab/vwgroup-vehicle2mqtt-history.js` zeigt, wie openHAB diese
Werte mit `item.persistence.persist(timestamp, state, 'timescaledb')` in
TimescaleDB injiziert. Passe in der Rule `PERSISTENCE_SERVICE` und
`ITEM_BY_CURATED_TOPIC` an deine Umgebung an. Die ausführliche Beschreibung steht
in [history.md](history.md).

## Hinweise

- `status/error` kann längere Texte enthalten und ist als `String` eingebunden.
- `status/stale` ist ein guter Indikator für Automationen, wenn das Portal keine
  frischen Fahrzeugdaten liefert.
- `status/car_captured_at` ist der Fahrzeug-/Backend-Zeitpunkt aus dem Dataset.
  `status/last_success_at` ist der Zeitpunkt, an dem der Dienst erfolgreich
  publiziert hat.
- MQTT selbst kann Persistence-Zeitstempel nicht rückdatieren. Für historische
  Werte mit Originalzeitpunkt den History-Batch und die openHAB-History-Rule
  verwenden.
- Empfohlen ist: Live-Items zeigen den letzten Wert an, laufen aber nicht
  zusätzlich automatisch per `everyChange` oder `everyUpdate` in dieselbe
  Persistence. Die historischen Punkte werden kontrolliert durch die Rule
  injiziert.

## English

openHAB can consume the topics published by `vwgroup-vehicle2mqtt` through the MQTT
Binding as a Generic MQTT Thing. The integration is read-only: this project
publishes vehicle data but does not send vehicle control commands.

Example files:

```text
openhab/vwgroup-vehicle2mqtt.things
openhab/vwgroup-vehicle2mqtt.items
openhab/vwgroup-vehicle2mqtt-history.items
openhab/vwgroup-vehicle2mqtt-history.js
```

Setup:

1. Install the openHAB MQTT Binding.
2. Configure an MQTT Broker Thing.
3. Replace `mqtt.example.local`, `TESTVIN1234567890`, and optionally `vw/euda`
   in the example files.
4. Copy or adapt the Things and Items into your openHAB configuration.

The Generic MQTT Thing uses `vw/euda/<VIN>/status/online` as availability topic
with `true` and `false` payloads.

For historical backfill, enable `mqtt.publish_history=true` and use the
`vwgroup-vehicle2mqtt-history.js` example. It injects batch events into
TimescaleDB with `item.persistence.persist(timestamp, state, 'timescaledb')` and
their original `car_captured_at` timestamp. Keep live Items for the latest state,
but avoid automatic `everyChange` or `everyUpdate` persistence for the same
service. See [history.md](history.md) for details.

Official reference:

- https://www.openhab.org/addons/bindings/mqtt.generic/
- https://www.openhab.org/docs/configuration/persistence
