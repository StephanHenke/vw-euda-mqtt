# evcc Integration

[Deutsch](#deutsch) | [English](#english)

## Deutsch

Diese Anleitung beschreibt, wie die von `vwgroup-vehicle2mqtt` veröffentlichten MQTT-
Werte in evcc als Fahrzeugquelle genutzt werden können. Ziel ist, das bestehende
evcc-Fahrzeug zu ersetzen, ohne die bisherigen Ladevorgänge zu verlieren.

### Grundprinzip

`vwgroup-vehicle2mqtt` veröffentlicht Fahrzeugwerte unter:

```text
vw/euda/<VIN>/
```

Für evcc sollte `mqtt.retain=true` gesetzt werden, damit evcc nach einem
Neustart sofort den letzten Wert erhält. Aktuell besonders relevant:

- `battery/soc`
- `battery/target_soc`
- `odometer/km`

Die Reichweite wird nur verwendet, wenn das Portal dafür tatsächlich ein
verlässliches Topic liefert. In den bisherigen Audi-Datensätzen war
`range/km` nicht verfügbar.

### Bestehendes Fahrzeug beibehalten

Wenn Ladevorgänge erhalten bleiben sollen, sollte in evcc kein neues Fahrzeug
angelegt werden. Stattdessen wird der bestehende Fahrzeugeintrag bearbeitet.

Bei YAML-Konfiguration:

- `name` unverändert lassen.
- `title` unverändert lassen, wenn alte und neue Ladevorgänge unter demselben
  Fahrzeugnamen erscheinen sollen.
- Nur die technische Quelle auf `type: custom` mit MQTT umstellen.

Bei evcc-Datenbank-/UI-Konfiguration:

- Den vorhandenen Fahrzeugeintrag öffnen, zum Beispiel `db:1`.
- Nicht löschen und nicht neu anlegen.
- Den Eintrag auf ein Custom-Fahrzeug mit MQTT-Quellen umstellen.
- Den Ladepunkt weiter auf denselben Fahrzeugnamen zeigen lassen, zum Beispiel
  `vehicle: db:1`.

evcc speichert Ladevorgänge separat in der Datenbank. Der Fahrzeugname wird als
Text in der Session gespeichert. Wenn `title` gleich bleibt, bleiben die
Historie und die Anzeige zusammenhängend.

### Beispiel

Ein vollständiges Beispiel liegt unter:

```text
evcc/mqtt-vehicle.example.yaml
```

Die wichtigsten Teile:

```yaml
mqtt:
  broker: mqtt.example.local:1883
  user: mqtt-user
  password: mqtt-password
  topic: evcc

vehicles:
  - name: audi
    type: custom
    title: Audi Q4 e-tron
    icon: car
    capacity: 76
    soc:
      source: mqtt
      topic: vw/euda/TESTVIN1234567890/battery/soc
      timeout: 72h
    limitsoc:
      source: mqtt
      topic: vw/euda/TESTVIN1234567890/battery/target_soc
      timeout: 72h
    odometer:
      source: mqtt
      topic: vw/euda/TESTVIN1234567890/odometer/km
      timeout: 720h
    features:
      - streaming
```

`capacity` muss zur nutzbaren Batteriekapazität des Fahrzeugs passen.

### Ablauf

1. In `vwgroup-vehicle2mqtt` sicherstellen, dass MQTT retained aktiv ist:

   ```json
   "retain": true
   ```

2. Prüfen, ob Werte im Broker liegen:

   ```text
   vw/euda/<VIN>/battery/soc
   vw/euda/<VIN>/battery/target_soc
   vw/euda/<VIN>/odometer/km
   ```

3. evcc-Datenbank oder evcc-Konfiguration sichern.

4. Bestehendes evcc-Fahrzeug bearbeiten und die MQTT-Quellen eintragen.

5. evcc neu starten.

6. Falls evcc nach dem Neustart noch `0` anzeigt, die retained Topics erneut
   veröffentlichen oder den nächsten Lauf von `vwgroup-vehicle2mqtt` abwarten.

### Kilometerstand

`vwgroup-vehicle2mqtt` merkt sich den letzten plausiblen Wert von `odometer/km` in der
lokalen `state_file`. Wenn ein neuer Portalwert `0`, nicht numerisch oder
kleiner als der zuletzt bekannte Kilometerstand ist, wird für das normalisierte
Topic weiter der letzte gültige Wert veröffentlicht.

Die aufbereiteten Daten unter `structured/...` und die Datei-Inhalte unter
`raw/file/<index>/...` bleiben unverändert und zeigen weiterhin, was im VW/Audi-
Datensatz stand.

## English

This guide describes how to use the MQTT values published by `vwgroup-vehicle2mqtt` as
an evcc vehicle source. The goal is to replace the existing evcc vehicle data
source without losing previous charging sessions.

### Basic Idea

`vwgroup-vehicle2mqtt` publishes vehicle values under:

```text
vw/euda/<VIN>/
```

Set `mqtt.retain=true` so evcc receives the last value immediately after a
restart. The most useful evcc topics are:

- `battery/soc`
- `battery/target_soc`
- `odometer/km`

Range should only be added when the portal actually provides a reliable range
topic. In the Audi datasets tested so far, `range/km` was not available.

### Keep The Existing Vehicle

If charging history should remain connected, do not create a new evcc vehicle.
Edit the existing vehicle instead.

For YAML configuration:

- Keep `name` unchanged.
- Keep `title` unchanged if old and new sessions should appear under the same
  displayed vehicle name.
- Only replace the technical source with `type: custom` and MQTT getters.

For evcc database/UI configuration:

- Open the existing vehicle entry, for example `db:1`.
- Do not delete it and do not create a replacement vehicle.
- Change the entry to a custom vehicle using MQTT sources.
- Keep the loadpoint assigned to the same vehicle name, for example
  `vehicle: db:1`.

evcc stores charging sessions separately in its database. The vehicle title is
stored as text in the session. Keeping the title stable keeps the history and UI
display coherent.

### Example

A full example is available at:

```text
evcc/mqtt-vehicle.example.yaml
```

Core snippet:

```yaml
mqtt:
  broker: mqtt.example.local:1883
  user: mqtt-user
  password: mqtt-password
  topic: evcc

vehicles:
  - name: audi
    type: custom
    title: Audi Q4 e-tron
    icon: car
    capacity: 76
    soc:
      source: mqtt
      topic: vw/euda/TESTVIN1234567890/battery/soc
      timeout: 72h
    limitsoc:
      source: mqtt
      topic: vw/euda/TESTVIN1234567890/battery/target_soc
      timeout: 72h
    odometer:
      source: mqtt
      topic: vw/euda/TESTVIN1234567890/odometer/km
      timeout: 720h
    features:
      - streaming
```

Adjust `capacity` to the vehicle's usable battery capacity.

### Steps

1. Make sure retained MQTT publishing is enabled in `vwgroup-vehicle2mqtt`:

   ```json
   "retain": true
   ```

2. Check that the broker has values:

   ```text
   vw/euda/<VIN>/battery/soc
   vw/euda/<VIN>/battery/target_soc
   vw/euda/<VIN>/odometer/km
   ```

3. Back up the evcc database or evcc configuration.

4. Edit the existing evcc vehicle and add the MQTT sources.

5. Restart evcc.

6. If evcc still shows `0` after restart, republish the retained topics or wait
   for the next `vwgroup-vehicle2mqtt` run.

### Odometer

`vwgroup-vehicle2mqtt` stores the last plausible `odometer/km` value in its configured
`state_file`. If a newer portal value is `0`, non-numeric, or lower than the
last known odometer, the normalized MQTT topic keeps publishing the last valid
value.

Structured topics under `structured/...` and file contents under `raw/file/<index>/...`
remain unchanged and still expose the original VW/Audi dataset.
