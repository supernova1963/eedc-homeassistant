# Sensor-Referenz: Feldnamen, Einheiten, Anforderungen

**Version 3.36.0** | Stand: Juni 2026 — Referenz für UI-Beschreibungen in Sensor-Zuordnung und MQTT-Setup

> **Single Source of Truth:** Die Feld-Hilfetexte (Spalte „Beschreibung") werden im Code als `hinweis`-Attribut in `backend/core/field_definitions.py` gepflegt und über `GET /api/monatsdaten/feld-hinweise` an den Sensor-Zuordnungs- (und künftigen MQTT-Inbound-) Wizard ausgeliefert. Diese Referenz und die `hinweis`-Texte konsistent halten.

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| **Momentan** | Aktueller Messwert zum Zeitpunkt der Abfrage (z.B. aktuelle Leistung in W) |
| **Kumulativ** | Zählerstand der stetig steigt (z.B. Stromzähler in kWh). Delta wird berechnet. |
| **Tagessensor** | Kumulativer Sensor der täglich um 0:00 auf 0 zurückgesetzt wird (HA Utility Meter). Wird unterstützt — Monatswechsel-Reset wird automatisch erkannt. |
| **Counter** | Kumulativer Anzahl-Zähler (Total-Increasing, kein kWh). Wird strikt von kWh-Feldern getrennt — siehe „Counter vs. kWh" unten. |
| **Bidirektional** | Positiv/negativ kodiert die Richtung (z.B. +Ladung/−Entladung) |
| **`state_class`** | HA-Attribut. `total_increasing`/`total` markieren kumulative Sensoren — von HA in Long-Term Statistics persistiert. Sensoren ohne `state_class` haben **keine** LTS-Einträge → für kWh-Felder ungeeignet (siehe „LTS-Verfügbarkeit"). |

---

## 1. Basis-Felder (Zähler / Netzübergabe)

### Monatserfassung (kWh)

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `einspeisung_kwh` | Einspeisung | kWh | Kumulativ oder Tagessensor | Ins Netz eingespeiste Energie. Muss immer ≥ 0 sein. Bei Zweirichtungszähler: nur der Einspeiseanteil. |
| `netzbezug_kwh` | Netzbezug | kWh | Kumulativ oder Tagessensor | Aus dem Netz bezogene Energie. Muss immer ≥ 0 sein. Bei Zweirichtungszähler: nur der Bezugsanteil. |
| `globalstrahlung_kwh_m2` | Globalstrahlung | kWh/m² | Kumulativ | Globalstrahlung im Monat. Wird automatisch von Open-Meteo geholt wenn nicht manuell gepflegt. |
| `sonnenstunden` | Sonnenstunden | h | Kumulativ | Sonnenstunden im Monat. Wird automatisch von Open-Meteo geholt. |
| `durchschnittstemperatur` | Ø Temperatur | °C | — | Monatsdurchschnitt. Wird automatisch von Open-Meteo geholt. |

### Live-Dashboard (W)

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `einspeisung_w` | Einspeisung | W | Momentan | Aktuelle Einspeiseleistung. Muss ≥ 0 sein. Wird alle paar Sekunden abgefragt. |
| `netzbezug_w` | Netzbezug | W | Momentan | Aktuelle Netzbezugsleistung. Muss ≥ 0 sein. |
| `pv_gesamt_w` | PV Gesamt | W | Momentan | Gesamte aktuelle PV-Leistung. Nur nötig wenn keine individuellen PV-Investitions-Sensoren konfiguriert sind. |
| `netz_kombi_w` | Kombinierter Netz-Sensor | W | Momentan, bidirektional | Alternative zu getrennt `einspeisung_w`/`netzbezug_w`. Positiv = Netzbezug, negativ = Einspeisung. Nur verwenden wenn kein getrennter Zähler vorhanden. |
| `strompreis` | Strompreis (dynamischer Tarif) | ct/kWh | Momentan | **Optional, ab v3.16.0.** Aktueller Strompreis aus Tibber, aWATTar, EPEX oder eigenem Template-Sensor. Akzeptierte Einheiten: `ct/kWh`, `EUR/kWh`, `EUR/MWh` (×0.1 → ct/kWh), `Cent`, `€`. Wird im Live-Tagesverlauf als gepunktete Linie auf sekundärer Y-Achse gezeigt. Ohne eigenen Sensor lädt eedc automatisch den EPEX-Börsenpreis (DE/AT) via aWATTar API als Fallback. |

### MQTT-Topic-Mapping (Basis)

| MQTT-Topic | Entspricht | Hinweis |
|------------|-----------|---------|
| `eedc/{id}_{name}/live/einspeisung_w` | `einspeisung_w` | |
| `eedc/{id}_{name}/live/netzbezug_w` | `netzbezug_w` | |
| `eedc/{id}_{name}/live/pv_gesamt_w` | `pv_gesamt_w` | |
| `eedc/{id}_{name}/live/netz_kombi_w` | `netz_kombi_w` | |
| `eedc/{id}_{name}/energy/einspeisung_kwh` | `einspeisung_kwh` | Tagessensor (Utility Meter), alle 5 Min publishen |
| `eedc/{id}_{name}/energy/netzbezug_kwh` | `netzbezug_kwh` | Tagessensor (Utility Meter), alle 5 Min publishen |
| `eedc/{id}_{name}/energy/pv_gesamt_kwh` | Σ `pv_erzeugung_kwh` | ⚠️ Heißt im Monatsdaten `pv_erzeugung_kwh` — Namensunterschied! |

---

## 2. PV-Module / Balkonkraftwerk

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `pv_erzeugung_kwh` | PV-Erzeugung | kWh | Kumulativ oder Tagessensor | Erzeugte Energie dieses PV-Strings/Moduls. Muss ≥ 0 sein. Alternativ: automatische kWp-Verteilung aus dem Gesamt-PV-Sensor. |
| `eigenverbrauch_kwh` | Eigenverbrauch | kWh | Kumulativ oder Tagessensor | Nur BKW: Direkt im Haushalt verbrauchte BKW-Erzeugung. Optional. |
| `speicher_ladung_kwh` | Speicher Ladung | kWh | Kumulativ oder Tagessensor | Nur BKW mit Speicher: Ins BKW-Akku geladene Energie. Optional. |
| `speicher_entladung_kwh` | Speicher Entladung | kWh | Kumulativ oder Tagessensor | Nur BKW mit Speicher: Aus BKW-Akku entladene Energie. Optional. |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Leistung | W | Momentan | Aktuelle PV-Erzeugungsleistung dieses Strings. Muss ≥ 0 sein. |

### MQTT Energy Topics

| MQTT-Topic | Feld |
|------------|------|
| `eedc/.../energy/inv/{inv_id}_{name}/pv_erzeugung_kwh` | `pv_erzeugung_kwh` |
| `eedc/.../energy/inv/{inv_id}_{name}/eigenverbrauch_kwh` | `eigenverbrauch_kwh` (nur BKW) |
| `eedc/.../energy/inv/{inv_id}_{name}/speicher_ladung_kwh` | `speicher_ladung_kwh` (nur BKW) |
| `eedc/.../energy/inv/{inv_id}_{name}/speicher_entladung_kwh` | `speicher_entladung_kwh` (nur BKW) |

---

## 3. Speicher (Batterie)

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `ladung_kwh` | Ladung | kWh | Kumulativ oder Tagessensor | Gesamte im Monat in den Speicher geladene Energie. Muss ≥ 0 sein. |
| `entladung_kwh` | Entladung | kWh | Kumulativ oder Tagessensor | Gesamte im Monat aus dem Speicher entladene Energie. Muss ≥ 0 sein. |
| `ladung_netz_kwh` | Netzladung | kWh | Kumulativ oder Tagessensor | Anteil der Ladung aus dem Netz (Arbitrage). Optional. Muss ≤ `ladung_kwh` sein. |
| `speicher_ladepreis_cent` | Ø Ladepreis | ct/kWh | Manuell | Ø Preis der Netzladung. Nur bei echter Arbitrage relevant — Backup-/Notladung läuft zum Bezugspreis. Manuell im Monatsabschluss. |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Leistung | W | Momentan, **bidirektional** | Positiv = Ladung (Senke), negativ = Entladung (Quelle). ⚠️ Manche WR liefern umgekehrtes Vorzeichen — dann "Invertieren" aktivieren. |
| `ladung_kwh` | Ladung heute | kWh | Tagessensor | Tages-Ladeenergie. Optional — wenn vorhanden, wird für heute-kWh-Anzeige bevorzugt (genauer als Trapez-Integration aus W-Sensor). Wird täglich um 0:00 auf 0 zurückgesetzt. |
| `entladung_kwh` | Entladung heute | kWh | Tagessensor | Tages-Entladeenergie. Optional — wie `ladung_kwh`. Wird täglich auf 0 zurückgesetzt. |
| `soc` | Ladezustand | % | Momentan | State of Charge. 0–100%. |

### MQTT Energy Topics

| MQTT-Topic | Feld | Hinweis |
|------------|------|---------|
| `eedc/.../energy/inv/{inv_id}_{name}/ladung_kwh` | `ladung_kwh` | Tagessensor empfohlen |
| `eedc/.../energy/inv/{inv_id}_{name}/entladung_kwh` | `entladung_kwh` | Tagessensor empfohlen |
| ⚠️ `ladung_netz_kwh` | — | **Kein MQTT-Topic vorhanden** — nur via HA-Sensor oder manuell |

---

## 4. Wärmepumpe

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `stromverbrauch_kwh` | Stromverbrauch | kWh | Kumulativ oder Tagessensor | Gesamter elektrischer Energieverbrauch der WP im Monat. Bei getrennter Messung: Summe aus Heizen + Warmwasser. |
| `strom_heizen_kwh` | Strom Heizen | kWh | Kumulativ oder Tagessensor | Nur bei getrennter Strommessung. Elektrische Energie für Heizbetrieb. |
| `strom_warmwasser_kwh` | Strom Warmwasser | kWh | Kumulativ oder Tagessensor | Nur bei getrennter Strommessung. Elektrische Energie für Warmwasserbereitung. |
| `heizenergie_kwh` | Heizwärme | kWh | Kumulativ oder Tagessensor | Bereitgestellte Wärmeenergie (thermisch, **nicht** Strom). Für JAZ-Berechnung: `heizenergie / stromverbrauch`. Kann alternativ via JAZ-Strategie aus Strom × JAZ berechnet werden. |
| `warmwasser_kwh` | Warmwasser | kWh | Kumulativ oder Tagessensor | Bereitgestellte Warmwasserenergie (thermisch). Optional. |
| `wp_starts_anzahl` | Kompressor-Starts | Anzahl | Counter (Total-Increasing) | **Optional, ab v3.24.0 (#136).** Kumulativer Anzahl-Zähler für Kompressor-Starts der Wärmepumpe. Z. B. aus der lokalen „Nibe Heat Pump"-Integration: `sensor.compressor_number_of_starts_…`. Stündlicher Snapshot-Job erfasst den Counter wie kWh-Zähler; Tagesabschluss berechnet Stunden- und Tages-Differenzen. **Bewusst kein Fallback** aus `leistung_w` oder Compressor-Binary — würde gerade kurze Takte (wo der KPI sticht) systematisch unterzählen. Anzeige: Auswertung → Energieprofil → Tagesdetail (Spalte „WP-Starts", default ausgeblendet) und Auswertung → Energieprofil → Monat (Komponenten-Gruppe). |
| `wp_betriebsstunden` | Betriebsstunden | h | Counter (Total-Increasing) | **Optional, ab v3.34 (#238).** Kumulativer Zähler der Gesamt-Betriebsstunden der WP. Kombiniert mit `wp_starts_anzahl` ergibt sich „Ø Laufzeit pro Start" als Auslegungs-/Verschleiß-Maß. Wird wie ein Counter behandelt — keine Energie-Einheit, keine Aufnahme in die Energie-Bilanz (siehe §9). |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Leistung | W | Momentan | Aktuelle elektrische Leistungsaufnahme der WP. Muss ≥ 0 sein. Alternativ: getrennte Sensoren (s.u.). |
| `leistung_heizen_w` | Leistung Heizen | W | Momentan | Nur bei getrennter Messung: Leistungsaufnahme Heizbetrieb. Optional. |
| `leistung_warmwasser_w` | Leistung Warmwasser | W | Momentan | Nur bei getrennter Messung: Leistungsaufnahme Warmwasser. Optional. |
| `warmwasser_temperatur_c` | Warmwassertemperatur | °C | Momentan | Aktuelle Warmwassertemperatur. Optional, wird als Gauge angezeigt. |

### MQTT Energy Topics

| MQTT-Topic | Feld | Hinweis |
|------------|------|---------|
| `eedc/.../energy/inv/{inv_id}_{name}/stromverbrauch_kwh` | `stromverbrauch_kwh` | |
| `eedc/.../energy/inv/{inv_id}_{name}/heizenergie_kwh` | `heizenergie_kwh` | |
| `eedc/.../energy/inv/{inv_id}_{name}/warmwasser_kwh` | `warmwasser_kwh` | |
| ⚠️ `strom_heizen_kwh` / `strom_warmwasser_kwh` | — | **Kein MQTT-Topic** — nur via HA-Sensor |

---

## 5. E-Auto

> **Heimladung gehört kanonisch an die Wallbox (ab Phase 2a).** Existiert eine Wallbox-Investition, ist sie die Quelle der Heimladung — die folgenden Felder `ladung_pv_kwh`/`ladung_netz_kwh` werden dann am E-Auto **nicht** erfasst (das Formular blendet sie aus). Sie gelten nur für Setups **ohne** Wallbox (Steckerlader/Schuko). Km-, Verbrauchs-, Extern- und V2H-Felder bleiben in jedem Fall am E-Auto.

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `ladung_pv_kwh` | Heim: PV | kWh | Kumulativ oder Tagessensor | Zu Hause aus PV geladene Energie. **Nur ohne Wallbox** (sonst an der Wallbox). Kann via EV-Quote aus Gesamt-Ladung berechnet werden. |
| `ladung_netz_kwh` | Heim: Netz | kWh | Kumulativ oder Tagessensor | Zu Hause aus Netz geladene Energie. **Nur ohne Wallbox.** Kann via EV-Quote berechnet werden. |
| `ladung_extern_kwh` | Externe Ladung | kWh | — | Extern geladene Energie (Autobahn, Arbeit). Manuell erfassen. Optional. |
| `ladung_extern_euro` | Externe Ladekosten | € | — | Kosten der externen Ladung. Manuell. Optional. |
| `verbrauch_kwh` | Verbrauch gesamt | kWh | Kumulativ oder Tagessensor | Gefahrener Energieverbrauch des E-Autos (reiner Fahrverbrauch), für die kWh/100 km-Effizienz mit `km_gefahren` verrechnet. Optional — fehlt der Wert, nähert eedc die kWh/100 km aus der geladenen Energie an (inkl. Ladeverluste). |
| `km_gefahren` | Gefahrene km | km | Kumulativ oder Tagessensor | Gefahrene Kilometer im Monat. Sensor (Auto-Integration, OBD) oder manuell. |
| `v2h_entladung_kwh` | V2H Entladung | kWh | Kumulativ oder Tagessensor | Vehicle-to-Home Entladung. Nur bei V2H-fähigem Fahrzeug. Optional. |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Ladeleistung | W | Momentan | Aktuelle Ladeleistung. ≥ 0 (Laden) oder bidirektional bei V2H (negativ = Entladung ins Haus). ⚠️ Wenn gleicher Sensor wie Wallbox: wird automatisch dedupliziert. |
| `soc` | Ladezustand | % | Momentan | State of Charge des Fahrzeugakkus. 0–100%. |

### MQTT Energy Topics

| MQTT-Topic | Feld | Hinweis |
|------------|------|---------|
| `eedc/.../energy/inv/{inv_id}_{name}/ladung_kwh` | — | ⚠️ Gesamt-Ladung, **nicht** PV/Netz-Split. Aufteilung nur beim Monatsabschluss via EV-Quote. |
| `eedc/.../energy/inv/{inv_id}_{name}/km_gefahren` | `km_gefahren` | |
| `eedc/.../energy/inv/{inv_id}_{name}/v2h_entladung_kwh` | `v2h_entladung_kwh` | |
| ⚠️ `ladung_pv_kwh` / `ladung_netz_kwh` | — | **Kein MQTT-Topic** — Split wird berechnet, nicht gemessen |

---

## 6. Wallbox

> **Wallbox = kanonische Heimladungs-Quelle (ab Phase 2a).** Ist eine Wallbox angelegt, liefert sie die zu Hause geladene Energie (gesamt/PV/Netz) für alle Auswertungen; die km-anteilige Aufteilung auf ein oder mehrere Fahrzeuge berechnet eedc daraus. Mehrere Wallboxen werden summiert (jeder Ladepunkt zählt). Mappe den Loadpoint-/Wallbox-Energiesensor daher hier, nicht am E-Auto.

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `ladung_kwh` | Ladung gesamt | kWh | Kumulativ oder Tagessensor | Gesamte von der Wallbox abgegebene Ladeenergie im Monat. |
| `ladung_pv_kwh` | Ladung PV | kWh | Kumulativ oder Tagessensor | Anteil aus PV. Optional — manche Wallboxen (z.B. go-e) messen das separat. |
| `ladevorgaenge` | Ladevorgänge | Anzahl | Kumulativ oder Tagessensor | Anzahl der Ladevorgänge. Optional. |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Ladeleistung | W | Momentan | Aktuelle Wallbox-Ladeleistung. Muss ≥ 0 sein. |

### MQTT Energy Topics

| MQTT-Topic | Feld | Hinweis |
|------------|------|---------|
| `eedc/.../energy/inv/{inv_id}_{name}/ladung_kwh` | `ladung_kwh` | |
| `eedc/.../energy/inv/{inv_id}_{name}/ladevorgaenge` | `ladevorgaenge` | |
| ⚠️ `ladung_pv_kwh` | — | **Kein MQTT-Topic** — nur via Wallbox-API oder manuell |

---

## 7. Sonstiges (Erzeuger / Verbraucher / Speicher)

### Monatserfassung

| Feld | Kategorie | Label | Einheit | Beschreibung |
|------|-----------|-------|---------|-------------|
| `erzeugung_kwh` | Erzeuger | Erzeugung | kWh | Erzeugte Energie (z.B. BHKW, Windrad). |
| `verbrauch_sonstig_kwh` | Verbraucher | Verbrauch | kWh | Verbrauchte Energie (z.B. Sauna, Pool). |
| `bezug_pv_kwh` | Verbraucher | davon PV | kWh | PV-gedeckter Anteil des Verbrauchs. Optional. |
| `bezug_netz_kwh` | Verbraucher | davon Netz | kWh | Netz-gedeckter Anteil des Verbrauchs. Optional. |
| `erzeugung_kwh` | Speicher | Erzeugung/Entladung | kWh | Entladene Energie. |
| `verbrauch_sonstig_kwh` | Speicher | Verbrauch/Ladung | kWh | Geladene Energie. |

### Live-Dashboard

| Feld | Label | Einheit | Beschreibung |
|------|-------|---------|-------------|
| `leistung_w` | Leistung | W | Aktuelle Leistung. |

---

## 8. Solcast PV Forecast (optional, ab v3.16.5)

Zwei alternative Pfade — Toggle „Solcast PV Forecast" am Ende von Schritt 1 im Sensor-Mapping-Wizard.

### Variante A: HA-Integration (BJReplay)

Setzt die [BJReplay Solcast HA-Integration](https://github.com/BJReplay/ha-solcast-solar) voraus. eedc liest die 7-Tage-Prognose direkt als Sensor-State — kein API-Key in eedc nötig.

**Auto-Discovery (v3.16.10):** Sensoren werden über `/api/states` per Suffix-Pattern gematcht:

| Suffix-Pattern | Bedeutung |
|---|---|
| `_heute` / `_today` | Tagesprognose Heute |
| `_morgen` / `_tomorrow` | Tagesprognose Morgen |
| `_uebermorgen` / `_ubermorgen` / `_tag_3` / `_day_3` | Übermorgen |
| `_tag_4` … `_tag_7` / `_day_4` … `_day_7` | Tag 4–7 |

Filter (v3.16.11): nur Sensoren mit `unit_of_measurement=kWh` und ohne „verbleibend"/„remaining" im Namen — sonst würde z. B. `prognose_verbleibende_leistung_heute` fälschlich als Tagesprognose gematcht.

**Stundenprofil:** Kommt aus dem `DetailedForecast`-Attribut der HA-Sensoren (v3.16.13 — vorher fälschlich `detailedHourly` gesucht, was bei Multi-Dach-Anlagen leer war).

### Variante B: Solcast-API (Free/Paid Key)

Direkter API-Aufruf für Standalone-Nutzer ohne HA-Integration. Konfiguration in den Anlagenstammdaten. L1-Cache (in-memory) und L2-Cache (DB) überleben Neustarts.

### Slot-Konvention

30-Min-Buckets aus Solcast werden per `ceil(bucket_ende)` dem **Backward-Slot** zugeordnet (siehe BERECHNUNGEN.md §6b). Ein Bucket am Tagesübergang `[23:00, 23:30)` heute landet damit korrekt in Slot 0 des Folgetags.

---

## 9. Counter vs. kWh — strikte Trennung

eedc unterscheidet seit v3.24.0 zwei Klassen kumulativer Sensoren:

| Klasse | Beispiele | Verarbeitung |
|---|---|---|
| **kWh-Felder** | `pv_erzeugung_kwh`, `ladung_kwh`, `entladung_kwh`, `stromverbrauch_kwh`, `einspeisung_kwh`, `netzbezug_kwh` | Fließen in die Energie-Bilanz, Performance Ratio, Lernfaktor. Wh→kWh, MWh→kWh werden automatisch konvertiert. |
| **Counter-Felder** (`KUMULATIVE_COUNTER_FELDER`) | `wp_starts_anzahl` | Reine Zähler — **keine** Energie-Einheit, **keine** Aufnahme in die Energie-Bilanz. Faktor 1.0 statt 0.001 bei unbekannter Einheit im HA-Statistics-Pfad. |

> **Warum getrennt?** Würde ein Counter-Sensor versehentlich als kWh-Feld konsumiert (z. B. weil seine Unit fehlt), würde er die Energie-Bilanz mit physikalisch sinnlosen Werten (z. B. 50 000 „kWh"-Kompressor-Starts) verfälschen. Die strikte Klassen-Trennung ist Voraussetzung für die Roh-Counter-Unterstützung der Nibe-Integration in v3.24.1.

---

## 10. LTS-Verfügbarkeit (HA Long-Term Statistics)

### Welche Sensoren landen in HA-LTS?

HA persistiert nur Sensoren mit gesetztem `state_class` in seiner `statistics_meta`-Tabelle. Sensoren ohne `state_class` haben **keine** LTS-Einträge — sie funktionieren live (`/api/states`), liefern aber **keine** historischen Stundenwerte für:

- Bulk-Import historischer Monate
- Vollbackfill der Tageszusammenfassungen
- Snapshot-basierte Stunden-kWh-Berechnung (siehe BERECHNUNGEN.md §6b)

### Filter im Sensor-Mapping-Wizard (v3.24.1)

Seit v3.24.1 zeigt der Wizard:

- `state_class` ∈ `total_increasing`/`total` → **immer** zugelassen, Unit egal.
- Sensor mit ganzzahligem State **ohne** Metadaten → zugelassen für Roh-Counter (z. B. Nibe Coils).
- **Fallback-Link** „Sensor nicht in der Auswahl? Alle Sensoren ohne Filter anzeigen" lädt on-demand alle `sensor.*`-Entities mit `filter_energy=false`.

### „ohne Statistik"-Badge (v3.24.1)

Sensoren ohne `state_class` tragen ein amber-farbiges Badge **„ohne Statistik"** im Wizard-Dropdown. Tooltip: „Für kWh-Felder ungeeignet, für Counter unproblematisch." Im Backend trägt `HASensorInfo.has_statistics: bool` (= `state_class is not None`) diese Information.

#### Anleitung zum Nachrüsten

Trägt ein Sensor das Badge — z. B. der Nibe-Counter `sensor.compressor_number_of_starts_…` —, lässt er sich in HA's `customize.yaml` nachträglich klassifizieren:

```yaml
homeassistant:
  customize:
    sensor.compressor_number_of_starts_eb101_ep14_31490:
      state_class: total_increasing
```

Nach **HA-Neustart** landet der Sensor in HA-Long-Term-Statistics und steht damit für Backfill, Per-Tag-Reaggregation und Snapshot-Self-Healing zur Verfügung.

> **Wichtig:** Die Korrektur wirkt **ab dem Zeitpunkt** der `state_class`-Aktivierung. HA legt LTS-Werte erst ab diesem Moment an — vorher existieren keine Werte zum Holen, auch keine rückwirkende Reparatur. Bestehende leere Tage bleiben leer; ab Aktivierung wird lückenfrei erfasst.

### Daten-Checker-Kategorie „Sensor-Mapping – HA-Statistics"

Prüft pro Anlage, ob alle im Mapping verwendeten **kWh-Sensoren** tatsächlich in HA-LTS landen:

| Befund | Bedeutung |
|---|---|
| **OK** | Alle kWh-Sensoren in LTS verfügbar |
| **WARNING** | kWh-Feld zeigt auf LTS-losen Sensor — Monatsabschluss bleibt leer (still kritisch) |
| **WARNING** | Counter-Feld zeigt auf LTS-losen Sensor — Snapshot läuft, aber Korrektur-Werkzeuge in der Datenverwaltung wirken nicht |

Live-Mappings (`leistung_w`, `soc`) werden nicht geprüft — sie lesen `state` direkt und brauchen kein LTS.

---

## 11. Export-Sensoren (eedc → HA)

Die bisherigen Abschnitte beschreiben Sensoren, die eedc **aus HA liest**. Dieser Abschnitt beschreibt die umgekehrte Richtung: berechnete eedc-Werte, die als **HA-Entitäten** bereitgestellt werden — per MQTT Discovery (empfohlen) oder REST. Einrichtung: *Einstellungen → Home Assistant → MQTT-Export* (siehe Handbuch Einstellungen, Kap. 5).

> **Zeithorizont:** Sofern nicht anders angegeben, beziehen sich die Werte auf die **Gesamtlaufzeit** (alle erfassten Monate, jeweils ab Anschaffungsdatum der Komponenten). Der laufende Monat fließt erst nach dem Monatsabschluss ein. Einzige Ausnahme: der **Spezifische Ertrag** ist aufs Jahr normiert (siehe unten).

### Anlage-weite Sensoren

| Sensor | Einheit | Bedeutung |
|---|---|---|
| `pv_erzeugung_gesamt_kwh` | kWh | Σ PV-Erzeugung aller erfassten Monate |
| `direktverbrauch_gesamt_kwh` | kWh | PV direkt verbraucht (ohne Speicherumweg) |
| `eigenverbrauch_gesamt_kwh` | kWh | Direktverbrauch + Speicher-Entladung + V2H |
| `einspeisung_gesamt_kwh` / `netzbezug_gesamt_kwh` | kWh | Zählerwerte |
| `gesamtverbrauch_kwh` | kWh | Eigenverbrauch + Netzbezug |
| `autarkie_prozent` / `eigenverbrauch_quote_prozent` | % | Quoten über die Gesamtlaufzeit |
| `spezifischer_ertrag_kwh_kwp` | kWh/kWp | **Aufs Jahr normiert** — siehe Hinweis unten |
| `netto_ertrag_euro` | € | Einspeiseerlös + EV-Ersparnis + Sonstige Erträge/Ausgaben |
| `einspeise_erloes_euro` / `eigenverbrauch_ersparnis_euro` | € | Finanz-Bausteine (deckungsgleich mit Cockpit/Berichten) |
| `co2_ersparnis_kg` | kg | CO₂-Einsparung |
| `investition_gesamt_euro`, `jahres_ersparnis_euro`, `roi_prozent`, `amortisation_jahre` | €, €/Jahr, %, Jahre | Investitions-KPIs |
| `speicher_zyklen`, `speicher_effizienz_prozent` | —, % | Speicher-KPIs |
| `letzter_import_jahr/_monat/_monat_name`, `anzahl_monate_erfasst` | — | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |

Zusätzlich erscheinen **pro Investition** (E-Auto, Wärmepumpe, Speicher, Wallbox …) eigene Sensoren (z. B. `e_auto_pv_anteil_prozent`, `wp_cop_durchschnitt`, `wp_betriebsstunden`) — jeweils unter einem eigenen HA-Gerät.

> **Spezifischer Ertrag — warum nicht einfach kWh ÷ kWp?** Der Sensor ist **annualisiert** und damit deckungsgleich mit der Cockpit-Kachel: saisonal gewichtet (PVGIS-Monatsverteilung) und mit der pro Monat tatsächlich aktiven PV-Leistung (Erweiterung/Teil-Rückbau wird korrekt gewichtet). Die naive Division *Gesamterzeugung ÷ heutiges kWp* würde bei 3 Jahren Historie etwa das Dreifache des gewohnten Jahreswerts anzeigen.

### PV-Prognose-Sensoren (`eedc_prognose_*`)

Quelle ist **immer die eedc-eigene Prognose** (OpenMeteo × Korrekturprofil) — nie Solcast/SFML, denn deren Werte liegen über die jeweilige HA-Integration ohnehin nativ in HA (kein Doppel-Export, keine Drift).

Die Korrektur erfolgt **pro Stunde** über die Korrekturprofil-Kaskade (Sonnenstand × Wetter → Saison-Stunde → Sonnenstand → Skalar; bei Anlagen ohne gelerntes Profil greift wie bisher der Lernfaktor-Skalar). Der Tagessensor ist dabei stets die Σ seiner korrigierten Stundenwerte — Sensor-State und `stundenprofil_kwh`-Attribut passen exakt zusammen. Dieselbe Berechnung speist die Spalte „eedc" im Prognosen-Vergleich: Add-on-Ansicht und HA-Sensor zeigen denselben Tageswert.

| Sensor | Bedeutung |
|---|---|
| `eedc_prognose_heute_kwh` | **Rollender Tageswert**: bisheriges IST + Prognose der verbleibenden Stunden. Läuft im Tagesverlauf mit dem IST mit — abends ≈ tatsächlicher Tagesertrag. Trägt das Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 Werte; Slot N = Energie der Stunde N−1 → N). |
| `eedc_prognose_rest_today_kwh` | **Echter Rest**: nur die Σ Prognose der verbleibenden Stunden (ohne IST). Der Steuerungswert für Automationen — „wie viel PV kommt heute noch?" |
| `eedc_prognose_day_plus_1/2/3_kwh` | Tagesprognose morgen / übermorgen / in 3 Tagen. Trägt jeweils das korrigierte Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 kWh-Werte, Slot-Konvention wie oben) — z. B. für Lade-Planung per Template. Werte ändern sich, wenn OpenMeteo einen neuen Modelllauf liefert (alle paar Stunden) **oder** das gelernte Korrekturprofil aktualisiert wird (nächtlich) — stundenlang unveränderte Werte sind normal. |
| `eedc_speicher_voll_um` | Uhrzeit, zu der der Speicher voraussichtlich voll ist (Simulation ab **aktuellem** Ladestand). |

> **Vormittag/Nachmittag:** eigene VM/NM-Sensoren gibt es bewusst nicht — beides ist per HA-Template direkt aus `stundenprofil_kwh` ableitbar (z. B. `{{ state_attr('sensor.…_day_plus_1_kwh', 'stundenprofil_kwh')[:13] | sum }}` für die Stunden bis 12 Uhr).

### Börsenpreis-Trigger (`eedc_preis_*`)

Grundlage ist der **Day-Ahead-Börsenpreis** (nicht der Anbieter-Endpreis — der variiert je Vertrag/Region, die Kurvenform ist dieselbe). Tag- und Nacht-Fenster werden **solar-basiert getrennt** bewertet (Sonnenauf-/-untergang, wandert saisonal).

**Günstig-Definition (zweistufig):** Eine Stunde gilt als günstig, wenn sie (1) zu den 5 billigsten ihres Fensters gehört **und** (2) ihr Preis unter der **Günstig-Schwelle** liegt — standardmäßig 10 % unter dem Tagesdurchschnitt ohne die 3 teuersten Stunden. Der Prozentsatz ist je Anlage einstellbar (MQTT-Export-Seite). Ohne die Schwelle wären die „günstigsten" Stunden rein relativ — erzwungener Verbrauch oder Netzladung in einer kaum billigeren Stunde ergibt keinen Sinn.

| Sensor | Bedeutung |
|---|---|
| `eedc_preis_rang` | Rang der **aktuellen** Stunde: 1–5 = günstig (1 = billigste ihres Fensters), 99 = teuer/Rest. Attribute: `rang_profil` (alle 24 Stunden) und `guenstig_schwelle_cent` (die heutige Schwelle in ct/kWh). |
| `eedc_preis_guenstige_stunden_anzahl` | Anzahl günstiger Stunden heute (Tag + Nacht) |
| `eedc_preis_guenstige_stunden_tag` / `_nacht` | Anzahl je Fenster (max. 5) |

> **Eigene Kriterien:** Wer eine andere Schwelle bevorzugt, stellt den Prozentsatz auf der Export-Seite um — oder rechnet in HA per Template direkt auf den Attributen (`rang_profil`, `guenstig_schwelle_cent`). eedc liefert bewusst nur die **Trigger-Werte**; die Lade-/Entlade-Strategie baut jeder selbst in seinen Automationen.

---

## Allgemeine Regeln für Sensoren

### Tagessensoren (Utility Meter)

HA Utility Meter setzen den Zählerstand täglich um 0:00 auf 0 zurück. **eedc unterstützt das** — sowohl in der HA-History-Auswertung als auch in MQTT Energy Snapshots. Der Monatswechsel-Reset (negativer Delta) wird automatisch erkannt: `end_val` wird dann direkt als Tageswert verwendet.

**Empfehlung:** Für MQTT Energy Topics sind Tagessensoren (HA Utility Meter) ideal — sie liefern direkt den Tageswert ohne Delta-Berechnung.

### Vorzeichen-Konvention

| Kategorie | Positiv | Negativ |
|-----------|---------|---------|
| PV-Leistung | Erzeugung | — (immer positiv) |
| Einspeisung | Ins Netz | — (immer positiv) |
| Netzbezug | Aus dem Netz | — (immer positiv) |
| Netz-Kombi | Netzbezug | Einspeisung |
| Batterie-Leistung | Ladung (Senke) | Entladung (Quelle) |
| E-Auto V2H | Ladung | Entladung ins Haus |

⚠️ Manche Wechselrichter liefern das Vorzeichen umgekehrt. In der Sensor-Zuordnung gibt es dafür die Option **"Invertieren"** (`live_invert`).

### Einheiten-Konvertierung

Live-Leistungssensoren werden automatisch konvertiert: `kW → W`, `MW → W`. Für kWh-Sensoren wird `Wh → kWh` und `MWh → kWh` automatisch skaliert. Counter-Felder (siehe §9) bleiben mit Faktor 1.0 — kein automatisches Wh→kWh, da physikalisch keine Energie.

---

*Letzte Aktualisierung: Juni 2026 (v3.44.x — Prognose-Export: Korrekturprofil-Kaskade + Stundenprofil-Attribute Tag+1/2/3)*
