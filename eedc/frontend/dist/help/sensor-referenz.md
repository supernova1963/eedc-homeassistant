# Sensor-Referenz: Feldnamen, Einheiten, Anforderungen

> Stand: 2026-04-02 — Referenz für UI-Beschreibungen in Sensor-Zuordnung und MQTT-Setup

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| **Momentan** | Aktueller Messwert zum Zeitpunkt der Abfrage (z.B. aktuelle Leistung in W) |
| **Kumulativ** | Zählerstand der stetig steigt (z.B. Stromzähler in kWh). Delta wird berechnet. |
| **Tagessensor** | Kumulativer Sensor der täglich um 0:00 auf 0 zurückgesetzt wird (HA Utility Meter). Wird unterstützt — Monatswechsel-Reset wird automatisch erkannt. |
| **Bidirektional** | Positiv/negativ kodiert die Richtung (z.B. +Ladung/−Entladung) |

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
| `heizenergie_kwh` | Heizenergie | kWh | Kumulativ oder Tagessensor | Bereitgestellte Wärmeenergie (thermisch). Für COP-Berechnung: `heizenergie / stromverbrauch`. Kann alternativ via COP-Strategie berechnet werden. |
| `warmwasser_kwh` | Warmwasser | kWh | Kumulativ oder Tagessensor | Bereitgestellte Warmwasserenergie (thermisch). Optional. |

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

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `ladung_pv_kwh` | Ladung PV | kWh | Kumulativ oder Tagessensor | Zu Hause aus PV geladene Energie. Kann via EV-Quote aus Gesamt-Ladung berechnet werden. |
| `ladung_netz_kwh` | Ladung Netz | kWh | Kumulativ oder Tagessensor | Zu Hause aus Netz geladene Energie. Kann via EV-Quote berechnet werden. |
| `ladung_extern_kwh` | Externe Ladung | kWh | — | Extern geladene Energie (Autobahn, Arbeit). Manuell erfassen. Optional. |
| `ladung_extern_euro` | Externe Ladekosten | € | — | Kosten der externen Ladung. Manuell. Optional. |
| `verbrauch_kwh` | Verbrauch gesamt | kWh | Kumulativ oder Tagessensor | Gesamtstromverbrauch des E-Autos. Optional — wird sonst aus Ladung berechnet. |
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
| `erzeugung_kwh` | Speicher | Erzeugung/Entladung | kWh | Entladene Energie. |
| `verbrauch_sonstig_kwh` | Speicher | Verbrauch/Ladung | kWh | Geladene Energie. |

### Live-Dashboard

| Feld | Label | Einheit | Beschreibung |
|------|-------|---------|-------------|
| `leistung_w` | Leistung | W | Aktuelle Leistung. |

---

## Allgemeine Regeln für Sensoren

### Tagessensoren (Utility Meter)

HA Utility Meter setzen den Zählerstand täglich um 0:00 auf 0 zurück. **EEDC unterstützt das** — sowohl in der HA-History-Auswertung als auch in MQTT Energy Snapshots. Der Monatswechsel-Reset (negativer Delta) wird automatisch erkannt: `end_val` wird dann direkt als Tageswert verwendet.

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

Live-Leistungssensoren werden automatisch konvertiert: `kW → W`, `MW → W`. Für kWh-Sensoren wird `Wh → kWh` und `MWh → kWh` automatisch skaliert.
