# VW EU Data Act MQTT Service

[English](README.md)

Dieses Projekt soll Fahrzeugdaten abrufen, die über das EU Data Act Portal des
Volkswagen Konzerns bereitgestellt werden, und sie strukturiert an einen MQTT
Broker weiterleiten. Ziel ist, diese Werte in Smart-Home-Systemen,
Energiemanagementsystemen und ähnlichen lokalen Automatisierungsplattformen
bereitzustellen.

Der Dienst meldet sich bei `eu-data-act.drivesomethinggreater.com` an, wählt die
konfigurierte Marke aus, liest die neueste Continuous-Data-ZIP-Datei für eine
FIN/VIN, extrahiert nützliche Fahrzeugwerte und publiziert sie retained nach
MQTT.

Der Login- und Dataset-Ansatz basiert auf
<https://github.com/mikrohard/hass-vw-eu-data-act> (MIT).

## Was der Dienst tut

- Login beim EU Data Act Portal mit dem Konto aus `config.json`.
- Markenauswahl über den Portal-Redirect, zum Beispiel `brand=AUDI&method=login`.
- Automatische Behandlung der notwendigen VW/Audi Identity Onboarding-Schritte.
- Abruf der Continuous-Data-Metadaten und ZIP-Datasets.
- Überspringen von `*_no_content_found.zip`, weil diese Dateien keine
  Fahrzeugdaten enthalten.
- MQTT-Publish der wichtigsten Werte und optional der Rohdaten.
- Bereitstellung der Daten für Smart-Home- und Energiemanagement-Anwendungen.

Der Dienst erstellt keine Datenanfrage im Portal. Er kann nur ZIP-Dateien
abrufen, die das Portal bereits erzeugt.

## Aktuelle Einschränkung

Der Dienst ist gegen die Datenübertragung entwickelt, die Volkswagen Group über
das EU Data Act Portal bereitstellt: Er meldet sich an, liest die Metadaten der
aktiven Datenanfrage, listet erzeugte ZIP-Datasets, überspringt leere
Platzhalter-ZIPs, lädt echte ZIP-Inhalte herunter und veröffentlicht deren Werte
nach MQTT.

In den bisherigen Audi/VW-Portaltests wurden jedoch nur
`*_no_content_found.zip`-Platzhalterdateien erzeugt. Aktuell ist in diesem
Projekt noch kein verlässlicher Weg bekannt, mit dem Fahrzeugdaten nach dem
Anlegen der Datenanfrage sauber im Portal erscheinen. Der Dienst kann deshalb
technisch verbunden und fehlerfrei laufen, ohne dass bereits Fahrzeugwerte zum
Veröffentlichen vorhanden sind.

## Voraussetzungen im Portal

1. Einmal im Browser auf <https://eu-data-act.drivesomethinggreater.com/>
   anmelden.
2. Die passende Marke auswählen, bei diesem Projekt typischerweise `Audi`.
3. Dasselbe myAudi/VW-Konto verwenden, das auch in `config.json` steht.
4. Offene AGB-, Registrierungs-, Land-/Sprache- und Consent-Dialoge abschließen.
5. Prüfen, dass das Fahrzeug verbunden ist und die FIN/VIN stimmt.
6. Eine `continuous/customised data request` mit 15-Minuten-Frequenz aktivieren.
7. Warten, bis das Portal ZIP-Datensätze für das Fahrzeug anzeigt.

Aktueller erwartbarer Zwischenzustand direkt nach dem Einrichten:

```text
No content datasets available yet
```

Das bedeutet, dass der Login funktioniert, aber Volkswagen bisher nur
`*_no_content_found.zip` erzeugt hat. Der Dienst pollt weiter und verarbeitet
die erste ZIP-Datei mit echtem Inhalt automatisch.

## VW/Audi Identity Onboarding

Auch bei `brand: "AUDI"` können die Login-Seiten `Volkswagen ID` anzeigen.
Audi nutzt hier die VW Group Identity Infrastruktur.

Der Dienst ruft zuerst den offiziellen Brand-Redirect des Portals auf, zum
Beispiel:

```text
/services/redirect/authentication?brand=AUDI&method=login
```

Aus diesem Redirect liest er die korrekte OIDC-Authorize-URL. Das ist wichtig,
weil Audi einen anderen Identity-Client verwenden kann als der generische
GIS-Consent-Client.

Je nach Kontostand können beim ersten nicht-browserbasierten Login diese
Stationen auftreten:

- `terms-and-conditions`: notwendige IdentityKit-Nutzungsbedingungen und
  Datenschutzdokumente werden automatisch bestätigt.
- `consent/users`: notwendige OAuth-Berechtigungen für Basisprofil und
  Fahrzeugzugriff werden automatisch erlaubt.
- `consent/marketing`: optionale Marketing-/Kommunikations-Einwilligung wird
  automatisch übersprungen.
- `verification/email-sent`: Volkswagen hat eine Bestätigungsmail gesendet. Den
  Link in der Mail öffnen und danach den Dienst neu starten.

## Konfiguration

Ausgangspunkt ist `config.example.json`:

```powershell
Copy-Item config.example.json config.json
```

Wichtige Felder:

- `email` / `password`: myAudi/VW-Konto.
- `brand`: für Audi auf `AUDI` setzen.
- `country` / `language`: für Deutschland typischerweise `de`.
- `vin`: FIN/VIN des Fahrzeugs. Wenn leer, versucht der Dienst ein einzelnes
  Fahrzeug automatisch zu finden.
- `identifier`: kann leer bleiben. Der Dienst liest den Continuous-Data-
  Identifier aus den Metadaten.
- `poll_interval_seconds`: Standard `900`, passend zu 15 Minuten.
- `mqtt.host`, `mqtt.port`, `mqtt.username`, `mqtt.password`: MQTT-Zugang.
- `mqtt.base_topic`: Standard `vw/euda`.
- `mqtt.publish_raw`: veröffentlicht zusätzlich alle Rohdaten unter `raw/...`.
- `mqtt.publish_carcompat`: spiegelt einzelne Werte optional unter
  `car/garage/<vin>/...`.

`config.json` enthält Zugangsdaten und ist deshalb per `.gitignore` vom Git-Repo
ausgeschlossen.

## Lokal testen

```powershell
uv run vw-euda-mqtt --config config.json --once --dry-run --debug
```

Ohne MQTT-Publish, aber mit echtem Portal-Login:

```powershell
uv run vw-euda-mqtt --config config.json --once --dry-run
```

Einmaliger echter Lauf mit MQTT-Publish:

```powershell
uv run vw-euda-mqtt --config config.json --once
```

Dauerbetrieb lokal:

```powershell
uv run vw-euda-mqtt --config config.json
```

## Docker-Betrieb

Fertige Images werden in der GitHub Container Registry veröffentlicht. Ein
Docker-Hub-Konto ist dafür nicht notwendig:

```bash
docker pull ghcr.io/stephanhenke/vw-euda-mqtt:latest
```

Der GitHub-Actions-Workflow kann dasselbe Image zusätzlich auf Docker Hub
veröffentlichen, wenn die Repository-Secrets `DOCKERHUB_USERNAME` und
`DOCKERHUB_TOKEN` gesetzt sind:

```bash
docker pull <dockerhub-username>/vw-euda-mqtt:latest
```

Nutzung des veröffentlichten Images mit Docker Compose:

```bash
cp config.example.json config.json
cp docker-compose.example.yml docker-compose.yml
mkdir -p data
docker compose up -d
```

Lokaler Entwicklungs-Build im Projektordner:

```bash
cp config.example.json config.json
mkdir -p data
docker compose up -d --build
```

Logs anzeigen:

```bash
docker logs -f vw-euda-mqtt
```

Container neu bauen und starten:

```bash
docker compose up -d --build
```

Auf Servern, auf denen Docker nur mit `sudo` verfügbar ist:

```bash
cd /pfad/zum/vw-euda-mqtt
sudo docker compose up -d --build
sudo docker logs -f vw-euda-mqtt
```

## MQTT-Topics

Standard-Basis:

```text
vw/euda/<vin>/
```

Auswahl der veröffentlichten Topics:

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

Bei Login- oder Polling-Fehlern schreibt der Dienst retained Fehlerstatus nach:

```text
vw/euda/<vin>/status/...
```

Wenn keine VIN konfiguriert ist, nutzt er:

```text
vw/euda/_service/status/...
```

## Fehlersuche

`Authentication failed: terms-and-conditions`

Der alte Fehler bedeutete, dass VW Identity noch AGB/Registrierung verlangte.
Der Dienst kann diesen Schritt inzwischen automatisch bestätigen. Falls der
Fehler erneut auftaucht, mit `--debug` testen und die Ziel-URL prüfen.

`verification/email-sent`

Volkswagen hat eine Bestätigungsmail geschickt. Den Link in der Mail anklicken
und danach den Dienst neu starten.

`No continuous-data Identifier returned`

Im EU Data Act Portal ist für die VIN noch keine Continuous-/Customised-
Datenanfrage aktiv.

`No content datasets available yet`

Login, Marke und Identifier funktionieren. Das Portal erzeugt aber aktuell nur
`*_no_content_found.zip`. Warten, bis eine ZIP-Datei mit echtem Inhalt vorhanden
ist. In den bisherigen Tests wurde noch kein verlässlicher Weg gefunden, wie
Audi/VW-Fahrzeugdaten sauber im EU Data Act Portal ankommen; sobald das Portal
ein nicht-leeres Dataset bereitstellt, verarbeitet der Dienst es automatisch.

`HTTP 401`

Meist wurde der falsche Brand-/Identity-Client verwendet oder der Portal-Login
ist abgelaufen. Mit `--debug` prüfen, ob der Login bei
`/de/de/user.html` landet.

`HTTP 500` beim List-Endpunkt

Kann beim Portal transient auftreten. Der Dienst wiederholt den Poll nach
`retry_interval_seconds`.

## Git- und Sicherheitsnotizen

Die Nutzung von Konto-E-Mail und Passwort ist eine pragmatische Lösung für den
aktuellen, browserorientierten Portalfluss. Sie ist ausdrücklich nicht die
feinste langfristige Lösung. Aus Sicht dieses Projekts wäre ein eigener API-Key
oder Token sauberer, der über das VW/Audi-Benutzerkonto ausgegeben wird, damit
Drittdienste autorisiert werden können, ohne das eigentliche Kontopasswort zu
speichern.

- `config.json` ist ignoriert, weil es Konto- und MQTT-Zugangsdaten enthält.
- `access.txt` ist ignoriert, weil dort VM-Zugangsdaten liegen können.
- `data/` ist ignoriert und enthält nur Laufzeitstatus.
- Niemals echte Passwörter, VINs mit Personenbezug oder Tokens committen, wenn
  das Repo öffentlich werden soll.
