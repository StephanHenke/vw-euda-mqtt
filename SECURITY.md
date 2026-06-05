# Security Policy

## English

`vwgroup-vehicle2mqtt` logs in to the VW Group EU Data Act portal and can handle account
credentials, MQTT credentials, VINs, dataset payloads, and local runtime state.
Treat all of those as sensitive.

Do not open a public issue with passwords, access tokens, full VINs, email
addresses, MQTT broker credentials, deployment host details, or unredacted ZIP
payloads. For new data-point reports, use a redacted sample shaped like
`tests/fixtures/audi_dataset_redacted.json`.

When sharing a dataset, replace at least:

- real VINs with `TESTVIN1234567890`
- account/user IDs with `redacted-user`
- email addresses, names, addresses, coordinates, tokens, and hostnames
- any values that can identify a vehicle owner or location history

For a security-sensitive report, please contact the repository owner privately
before publishing details in an issue.

## Deutsch

`vwgroup-vehicle2mqtt` meldet sich am VW Group EU Data Act Portal an und kann Konto-
Zugangsdaten, MQTT-Zugangsdaten, FIN/VIN, Dataset-Inhalte und lokalen
Laufzeitstatus verarbeiten. Diese Daten sind als sensibel zu behandeln.

Bitte keine öffentlichen Issues mit Passwörtern, Tokens, vollständigen FINs,
E-Mail-Adressen, MQTT-Zugangsdaten, Deployment-Zugängen oder unredigierten
ZIP-Payloads erstellen. Für neue Datenpunkt-Meldungen bitte ein redigiertes
Beispiel nach dem Muster `tests/fixtures/audi_dataset_redacted.json` verwenden.

Beim Teilen eines Datensatzes mindestens ersetzen:

- echte FIN/VIN durch `TESTVIN1234567890`
- Konto-/User-IDs durch `redacted-user`
- E-Mail-Adressen, Namen, Adressen, Koordinaten, Tokens und Hostnamen
- alle Werte, die Fahrzeughalter oder Standortverläufe identifizieren könnten

Bei sicherheitsrelevanten Meldungen bitte zuerst den Repository-Owner privat
kontaktieren, bevor Details öffentlich in einem Issue beschrieben werden.
