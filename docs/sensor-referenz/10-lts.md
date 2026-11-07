## 10. LTS-Verfügbarkeit (HA Long-Term Statistics)

### Welche Sensoren landen in HA-LTS?

HA persistiert nur Sensoren mit gesetztem `state_class` in seiner `statistics_meta`-Tabelle. Sensoren ohne `state_class` haben **keine** LTS-Einträge — sie funktionieren live (`/api/states`), liefern aber **keine** historischen Stundenwerte für:

- Bulk-Import historischer Monate
- Vollbackfill der Tageszusammenfassungen
- Snapshot-basierte Stunden-kWh-Berechnung (siehe [BERECHNUNGEN §6b](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation))

### Filter in der Datenquellen-Zuordnung (HA-Sensor-Picker)

Bei der HA-Sensor-Auswahl zeigt eedc:

- `state_class` ∈ `total_increasing`/`total` → **immer** zugelassen, Unit egal.
- Sensor mit ganzzahligem State **ohne** Metadaten → zugelassen für Roh-Counter (z. B. Nibe Coils).
- **Fallback-Link** „Sensor nicht in der Auswahl? Alle Sensoren ohne Filter anzeigen" lädt on-demand alle `sensor.*`-Entities mit `filter_energy=false`.

### „ohne Statistik"-Badge

Sensoren ohne `state_class` tragen ein amber-farbiges Badge **„ohne Statistik"** im Picker-Dropdown. Tooltip: „Für kWh-Felder ungeeignet, für Counter unproblematisch." Im Backend trägt `HASensorInfo.has_statistics: bool` (= `state_class is not None`) diese Information. Zur Zuordnungszeit meldet die Datenquellen-Fläche das zusätzlich als Feld-Warnung ([Einstellungen §7.6](HANDBUCH_EINSTELLUNGEN.md#76-validierung--probleme-je-feld)).

#### Anleitung zum Nachrüsten

Trägt ein Sensor das Badge — z. B. der Nibe-Counter `sensor.compressor_number_of_starts_…` —, ist der **empfohlene Weg ein Verbrauchszähler-Helfer über die HA-Oberfläche**: **Einstellungen → Geräte & Dienste → Helfer → Verbrauchszähler**, als Eingang den betroffenen Sensor, Zurücksetzen-Zyklus **„nie"** (also **ohne Zyklus**). Der Helfer bringt die Statistik-Attribute mit, sein Name überlebt einen Gerätetausch — in eedc wird anschließend der Helfer zugeordnet. Details und Begründung: [Handbuch Daten-Checker §5.1](HANDBUCH_DATEN_CHECKER.md#51-state_class-probleme-bei-ha-sensoren-beheben).

Wer die YAML ohnehin pflegt, kann den Sensor stattdessen per `customize` klassifizieren:

```yaml
homeassistant:
  customize:
    sensor.compressor_number_of_starts_eb101_ep14_31490:
      state_class: total_increasing
```

Nach **HA-Neustart** landet der Sensor in HA-Long-Term-Statistics und steht damit für Backfill, Per-Tag-Reaggregation und Snapshot-Self-Healing zur Verfügung. Beide Wege gelten ab jetzt — ein neu angelegter Helfer beginnt seine Historie bei null.

> **Wichtig:** Die Korrektur wirkt **ab dem Zeitpunkt** der `state_class`-Aktivierung. HA legt LTS-Werte erst ab diesem Moment an — vorher existieren keine Werte zum Holen, auch keine rückwirkende Reparatur. Bestehende leere Tage bleiben leer; ab Aktivierung wird lückenfrei erfasst.

**Ohne eedc-Neustart.** Liest eedc die Statistik über die WebSocket-Verbindung (kein Zugriff auf die Recorder-Datenbank, etwa eedc als eigener Container oder Home Assistant mit MariaDB), sieht es einen Sensor, dessen Statistik erst nach dem Start von eedc beginnt, ohne Neustart, spätestens nach fünf Minuten — wie beim Lesen aus der Datenbank. eedc holt die Liste der Statistik-Sensoren dafür neu, wenn ein zugeordneter Sensor darin fehlt, höchstens einmal je fünf Minuten.

### Daten-Checker-Kategorie „Datenquellen – HA-Statistics"

Prüft pro Anlage, ob alle in der Datenquellen-Zuordnung verwendeten **kWh-Sensoren** tatsächlich in HA-LTS landen (siehe [Handbuch Daten-Checker §4.9](HANDBUCH_DATEN_CHECKER.md#49-sensor-mapping--ha-statistics)):

| Befund | Bedeutung |
|---|---|
| **OK** | Alle kWh-Sensoren in LTS verfügbar |
| **WARNING** | kWh-Feld zeigt auf LTS-losen Sensor — Monatsabschluss bleibt leer (still kritisch) |
| **WARNING** | Counter-Feld zeigt auf LTS-losen Sensor — Snapshot läuft, aber Korrektur-Werkzeuge in der Energieprofil-Pflege wirken nicht |

Live-Zuordnungen (`leistung_w`, `soc`) werden nicht geprüft — sie lesen `state` direkt und brauchen kein LTS.

---

