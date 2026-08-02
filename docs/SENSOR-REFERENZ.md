# Sensor-Referenz: Feldnamen, Einheiten, Anforderungen

**Version 4.0** | Stand: 2026-07-25 — Referenz für UI-Beschreibungen in der Datenquellen-Zuordnung und im MQTT-Setup

> **Single Source of Truth:** Die Feld-Hilfetexte (Spalte „Beschreibung") werden im Code als `hinweis`-Attribut in `backend/core/field_definitions.py` gepflegt und über `GET /api/monatsdaten/feld-hinweise` an die Datenquellen-Zuordnung ausgeliefert. Diese Referenz und die `hinweis`-Texte konsistent halten. Die Export-Sensoren (§8a, §11) spiegeln `backend/services/ha_sensors_export.py` bzw. `GET /api/ha/export/definitions`.

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| **Momentan** | Aktueller Messwert zum Zeitpunkt der Abfrage (z.B. aktuelle Leistung in W) |
| **Kumulativ** | Zählerstand der stetig steigt (z.B. Stromzähler in kWh). Delta wird berechnet. |
| **Tagessensor** | Kumulativer Sensor der täglich um 0:00 auf 0 zurückgesetzt wird (HA Utility Meter). Wird unterstützt — Monatswechsel-Reset wird automatisch erkannt. |
| **Counter** | Kumulativer Anzahl-Zähler (Total-Increasing, kein kWh). Wird strikt von kWh-Feldern getrennt — siehe „Counter vs. kWh" unten. |
| **Bidirektional** | Positiv/negativ kodiert die Richtung (z.B. +Ladung/−Entladung) |
| **`state_class`** | HA-Attribut. `total_increasing`/`total` markieren kumulative Sensoren — von HA in Long-Term Statistics persistiert. Sensoren ohne `state_class` haben **keine** LTS-Einträge → für kWh-Felder ungeeignet (siehe „LTS-Verfügbarkeit"). |
| **`*`** | **Pflichtfeld** — ohne diesen Wert fehlt eine Kernauswertung. In der Zuordnungs-Fläche mit rotem `*`; bleibt es ohne Quelle, steht der Hinweis dort rot und aufgeklappt. |
| **Alternativ-Gruppe** | Zwei Erfassungswege, von denen **einer genügt**. Ist ein Weg belegt, gilt der andere als abgedeckt und wird nicht mehr angemahnt. |

> **Wo ordne ich Sensoren zu?** In v4 unter **Einstellungen → Datenquellen** — jedes Feld bekommt **genau eine** Quelle (HA-Sensor, MQTT-Gateway, MQTT-Inbound oder keine). Details zur Fläche: [Handbuch Einstellungen §7](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung). Voraussetzung ist eine stehende Verbindung ([Integration](HANDBUCH_EINSTELLUNGEN.md#6-integration)).

> **Pflicht, optional, oder hier gar nicht?** Die Fläche stuft jedes Feld ein, damit „keine Quelle" nicht pauschal wie ein Mangel aussieht (SoT: `FELD_BEDARF` in `backend/core/field_definitions.py`):
>
> - **Pflicht** (`*`) — Anlage: Einspeisung + Netzbezug (Zählerstand) und die PV-Erzeugung. Je Gerät das jeweilige Kernfeld: Speicher Ladung/Entladung, Wärmepumpe Strom + Heizwärme, Wallbox Ladung gesamt, E-Auto gefahrene km, PV-Modul/Balkonkraftwerk Erzeugung.
> - **Optional** — alles Übrige, insbesondere **alle Live-Felder (W, %, °C)**: ohne sie bleibt nur das Live-Dashboard leer, Statistik und Wirtschaftlichkeit laufen über die kWh-Zählerstände weiter.
> - **Nicht hier zu erfassen** — das Feld ist durch einen anderen Weg abgedeckt und wird mit Begründung ausgegraut: die drei Alternativ-Gruppen (unten) sowie die Heimladung am E-Auto, sobald eine Wallbox existiert (die Wallbox ist die maßgebliche Quelle, siehe §5).
>
> **Alternativ-Gruppen:**
>
> | Gruppe | Weg A | Weg B |
> |--------|-------|-------|
> | PV-Energie | Anlage `pv_gesamt_kwh` | je PV-Modul/Balkonkraftwerk `pv_erzeugung_kwh` |
> | PV-Leistung | Anlage `pv_gesamt_w` | je Modul `leistung_w` |
> | Netz-Leistung | `netz_kombi_w` (ein Sensor mit Vorzeichen) | `einspeisung_w` + `netzbezug_w` getrennt |
>
> **PV-Energie ist kein reines Entweder-oder:** Einzelwerte haben immer Vorrang, der Gesamtwert füllt
> nur die Lücken der Module **ohne** eigenen Wert (anteilig nach kWp, in der Anzeige gekennzeichnet).
> Beides zusammen ist deshalb der normale Übergangszustand, solange noch nicht jeder String misst.
> **Zielbild:** alle Strings erfassen und `pv_gesamt_kwh` auf „keine" setzen — zusammengefasst
> höchstens je Ausrichtung/Neigung, sonst kippt die Prognose für Anlagen mit mehreren Ausrichtungen.
> Bei den beiden Leistungs-Gruppen gilt das Entweder-oder dagegen strikt: ein einziger Einzelsensor
> macht den Gesamtsensor im Live-Dashboard wirkungslos.
>
> **„Keine Quelle" ist kein Fehler:** Alle kWh-Felder lassen sich im Monatsabschluss auch manuell erfassen. Rot heißt „hier fehlt noch etwas", nie „falsch".

---

## 1. Basis-Felder (Zähler / Netzübergabe)

### Monatserfassung (kWh)

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `einspeisung_kwh` | Einspeisung `*` | kWh | Kumulativ oder Tagessensor | Ins Netz eingespeiste Energie. Muss immer ≥ 0 sein. Bei Zweirichtungszähler: nur der Einspeiseanteil. |
| `netzbezug_kwh` | Netzbezug `*` | kWh | Kumulativ oder Tagessensor | Aus dem Netz bezogene Energie. Muss immer ≥ 0 sein. Bei Zweirichtungszähler: nur der Bezugsanteil. |
| `globalstrahlung_kwh_m2` | Globalstrahlung | kWh/m² | Kumulativ | Globalstrahlung im Monat. Wird automatisch von Open-Meteo geholt wenn nicht manuell gepflegt. |
| `sonnenstunden` | Sonnenstunden | h | Kumulativ | Sonnenstunden im Monat. Wird automatisch von Open-Meteo geholt. |
| `durchschnittstemperatur` | Ø Temperatur | °C | — | Monatsdurchschnitt. Wird automatisch von Open-Meteo geholt. |

### Live-Dashboard (W)

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `einspeisung_w` | Einspeisung | W | Momentan | Aktuelle Einspeiseleistung. Muss ≥ 0 sein. Wird alle paar Sekunden abgefragt. |
| `netzbezug_w` | Netzbezug | W | Momentan | Aktuelle Netzbezugsleistung. Muss ≥ 0 sein. |
| `pv_gesamt_w` | PV Gesamt | W | Momentan | Gesamte aktuelle PV-Leistung. Nur nötig wenn keine individuellen PV-Komponenten-Sensoren konfiguriert sind. |
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
| `eigenverbrauch_kwh` | Eigenverbrauch | kWh | Kumulativ oder Tagessensor | Nur BKW: Direkt im Haushalt verbrauchte BKW-Erzeugung. Optional, **nur Monatswert** (siehe Kasten). |
| `speicher_ladung_kwh` | Speicher Ladung | kWh | **kein Sensor** — nur manuell/Import | Nur BKW mit Speicher: Ins BKW-Akku geladene Energie. Altbestand, siehe Kasten. |
| `speicher_entladung_kwh` | Speicher Entladung | kWh | **kein Sensor** — nur manuell/Import | Nur BKW mit Speicher: Aus BKW-Akku entladene Energie. Altbestand, siehe Kasten. |

> **Ein Balkonkraftwerk mit Akku: den Akku als eigene Speicher-Investition erfassen.**
> Neu anlegen, Typ *Speicher*, und unter **Gehört zu** das Balkonkraftwerk wählen. Nur so
> hat der Akku Live-Leistung, Ladestand, einen Knoten im Energiefluss und Tages-/
> Stundenwerte — er nutzt dann die normalen Speicher-Felder `ladung_kwh` /
> `entladung_kwh`, und deren Sensoren ordnest du bei dieser Speicher-Investition zu.
>
> Die beiden BKW-eigenen Felder `speicher_ladung_kwh`/`speicher_entladung_kwh` sind der
> **frühere zweite Weg**. Sie bleiben erfassbar — bereits gepflegte Werte bleiben
> sichtbar und im Monatsabschluss wie im CSV-Import änderbar —, kennen aber nur einen
> **Monatswert** und lassen sich deshalb **nicht mehr als Sensor- oder MQTT-Quelle
> zuordnen**. Wer sie gepflegt hat, bekommt im Daten-Checker einen Hinweis mit dem
> Umstellungsweg; es geht dabei nichts verloren.
>
> **`eigenverbrauch_kwh`** bleibt zuordenbar, liefert aber ebenfalls **nur** den
> Monatswert (HA-Langzeitstatistik oder von Hand/per Import). Es ist kein Bilanz-Zähler,
> sondern eine optionale Verfeinerung — normalerweise leitet eedc den BKW-Eigenverbrauch
> aus Erzeugung − Einspeisung ab. Wer es per **MQTT** publiziert hat: das Topic wurde bis
> v4.0.4 fälschlich auf den Erzeugungs-Kanal gelegt und konnte die „Heute"-PV-Kachel
> überschreiben; das ist behoben.

> **`pv_erzeugung_kwh` steht für drei verschiedene Größen — je nachdem, wo es auftaucht.** Hier in der
> Monatserfassung ist es die Erzeugung **dieses einen** Moduls. Daneben gibt es den monatlichen
> **PV-Gesamtwert** der Anlage (gleicher Name, Anlagen-Ebene — Grundlage der kWp-Verteilung, wenn kein
> Pro-Modul-Wert existiert) und ein **Auswertungs-Feld** gleichen Namens, das PV-Module **+**
> Balkonkraftwerk zusammenfasst. Der Name bleibt bewusst unverändert, weil er zugleich MQTT-Topic,
> CSV-Spalte und Backup-Feld ist — eine Umbenennung wäre nach außen ein Bruch. Siehe
> [Glossar](GLOSSAR.md#energie--bilanzen).

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Leistung | W | Momentan | Aktuelle PV-Erzeugungsleistung dieses Strings. Muss ≥ 0 sein. |

### MQTT Energy Topics

| MQTT-Topic | Feld |
|------------|------|
| `eedc/.../energy/inv/{inv_id}_{name}/pv_erzeugung_kwh` | `pv_erzeugung_kwh` |
| `eedc/.../energy/inv/{inv_id}_{name}/eigenverbrauch_kwh` | `eigenverbrauch_kwh` (nur BKW) — wird für Tages-/Live-Werte **nicht** ausgewertet, s. Kasten oben |

Für den **Akku eines Balkonkraftwerks** gibt es hier bewusst kein Topic: er wird als
eigene Speicher-Investition erfasst und publiziert unter deren ID auf
`…/energy/inv/{speicher_id}_{name}/ladung_kwh` bzw. `…/entladung_kwh` (siehe Speicher).

---

## 3. Speicher (Batterie)

### Monatserfassung

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `ladung_kwh` | Ladung — bei Speichern mit Netzladung: **„Ladung (gesamt, inkl. Netz)"** | kWh | Kumulativ oder Tagessensor | Gesamte im Monat in den Speicher geladene Energie, **Netzladung eingeschlossen**. Muss ≥ 0 sein. `ladung_netz_kwh` ist ein *davon*-Anteil, kein zweiter Summand — ein Gerät, das PV- und Netzladung getrennt zählt, braucht hier die Summe beider (HA-Helfer). |
| `entladung_kwh` | Entladung | kWh | Kumulativ oder Tagessensor | Gesamte im Monat aus dem Speicher entladene Energie. Muss ≥ 0 sein. |
| `ladung_netz_kwh` | Netzladung | kWh | Kumulativ oder Tagessensor | Anteil der Ladung aus dem Netz (Arbitrage). Optional. Muss ≤ `ladung_kwh` sein. **Kanonischer Schlüssel** `ladung_netz_kwh` (Legacy-Fallback `speicher_ladung_netz_kwh` wird noch gelesen). |
| `speicher_ladepreis_cent` | Ø Ladepreis | ct/kWh | **kein Sensor, kein Topic** — nur manuell/Import | Ø Preis der Netzladung. Nur bei echter Arbitrage relevant — Backup-/Notladung läuft zum Bezugspreis. Erfassung im Monatsdaten-Formular, per CSV-Import oder über den errechneten Vorschlag bei dynamischem Tarif; auf der Datenquellen-Fläche wird das Feld **nicht** zur Zuordnung angeboten (seit v4.0.6). |

### Live-Dashboard

| Feld | Label | Einheit | Sensortyp | Beschreibung |
|------|-------|---------|-----------|-------------|
| `leistung_w` | Leistung | W | Momentan, **bidirektional** | Positiv = Ladung (Senke), negativ = Entladung (Quelle). ⚠️ Manche WR liefern umgekehrtes Vorzeichen — dann in der Datenquellen-Zuordnung „±" (Vorzeichen umkehren) aktivieren. |
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
| `wp_starts_anzahl` | Kompressor-Starts | Anzahl | Counter (Total-Increasing) | **Optional, ab v3.24.0 (#136).** Kumulativer Anzahl-Zähler für Kompressor-Starts der Wärmepumpe. Z. B. aus der lokalen „Nibe Heat Pump"-Integration: `sensor.compressor_number_of_starts_…`. Stündlicher Snapshot-Job erfasst den Counter wie kWh-Zähler; Tagesabschluss berechnet Stunden- und Tages-Differenzen. **Bewusst kein Fallback** aus `leistung_w` oder Compressor-Binary — würde gerade kurze Takte (wo der KPI sticht) systematisch unterzählen. Anzeige: [Cockpit → Tag](HANDBUCH_BEDIENUNG.md#22-tag) (Spalte „WP-Starts", default ausgeblendet) und Wärmepumpe-Komponentensicht ([Bedienung §3.4](HANDBUCH_BEDIENUNG.md#34-wärmepumpe)). |
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

> **Heimladung gehört kanonisch an die Wallbox (ab Phase 2a).** Existiert eine Wallbox-Komponente, ist sie die Quelle der Heimladung — die folgenden Felder `ladung_pv_kwh`/`ladung_netz_kwh` werden dann am E-Auto **nicht** erfasst (das Formular blendet sie aus). Sie gelten nur für Setups **ohne** Wallbox (Steckerlader/Schuko). Km-, Verbrauchs-, Extern- und V2H-Felder bleiben in jedem Fall am E-Auto.

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
| `eedc/.../energy/inv/{inv_id}_{name}/ladung_kwh` | — | ⚠️ Gesamt-Ladung, **nicht** PV/Netz-Split. Aufteilung nur im Monatsdaten-Formular via EV-Quote. |
| `eedc/.../energy/inv/{inv_id}_{name}/km_gefahren` | `km_gefahren` | |
| `eedc/.../energy/inv/{inv_id}_{name}/v2h_entladung_kwh` | `v2h_entladung_kwh` | |
| ⚠️ `ladung_pv_kwh` / `ladung_netz_kwh` | — | **Kein MQTT-Topic** — Split wird berechnet, nicht gemessen |

---

## 6. Wallbox

> **Wallbox = kanonische Heimladungs-Quelle (ab Phase 2a).** Ist eine Wallbox angelegt, liefert sie die zu Hause geladene Energie (gesamt/PV/Netz) für alle Auswertungen; die km-anteilige Aufteilung auf ein oder mehrere Fahrzeuge berechnet eedc daraus. Mehrere Wallboxen werden summiert (jeder Ladepunkt zählt). Ordne den Loadpoint-/Wallbox-Energiesensor daher hier zu, nicht am E-Auto.

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
| `erzeugung_kwh` | Erzeuger | Erzeugung | kWh | Erzeugte Energie (z.B. BHKW, Windrad). Zählt hinter dem Hauszähler in die Eigenverbrauchs-/Autarkie-Bilanz. |
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

Solcast als dritte Prognose-Quelle wird über die Datenquellen/Anlagenstammdaten angebunden — zwei alternative Pfade. Wie eedc die Solcast-Werte im Vergleich nutzt, steht im [Handbuch Prognosen §2.3](HANDBUCH_PROGNOSEN.md#23-solcast--optional-dritte-meinung).

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

Direkter API-Aufruf für Standalone-Nutzer ohne HA-Integration. Konfiguration in den Anlagenstammdaten ([Einstellungen → Stammdaten → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)). L1-Cache (in-memory) und L2-Cache (DB) überleben Neustarts.

### Slot-Konvention

30-Min-Buckets aus Solcast werden per `ceil(bucket_ende)` dem **Backward-Slot** zugeordnet (siehe [BERECHNUNGEN §6b](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation)). Ein Bucket am Tagesübergang `[23:00, 23:30)` heute landet damit korrekt in Slot 0 des Folgetags.

---

## 8a. eedc-PV-Prognose nach HA exportieren (MQTT / HA-Sensoren)

eedc **exportiert** zusätzlich die eigene PV-Prognose als Sensoren (immer die **eedc**-Quelle, nie Solcast/SFML — die liegen via eigene HA-Integration bereits in HA). Alle Werte stammen aus dem **Prognose-Kanon** und sind damit identisch mit der App-Anzeige und der „eedc"-Spalte im Vergleich. Einrichtung: [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export).

| Sensor / Schlüssel | Bedeutung |
|---|---|
| `eedc_prognose_heute_kwh` | **PV-Tagesprognose heute** — voller Tageswert (kanonisch, rollt mit OpenMeteo, == Anzeige). |
| `eedc_prognose_rest_today_kwh` | **Rest heute** — Prognose der verbleibenden Stunden, laufende Stunde anteilig nach Restminuten (#339); aus demselben Kanon → rollt synchron mit „heute". |
| `eedc_prognose_day_plus_1/2/3_kwh` | Tagesprognose morgen / übermorgen / in 3 Tagen. Attribut `stundenprofil_kwh` = 24 Backward-Slots (kWh); Sensor-State == Σ Slots. |
| `eedc_speicher_voll_um` | Uhrzeit „Speicher voll" aus der SoC-Simulation ab aktuellem Speicherstand. |

> **Hinweis:** Bis v3.45.5 war `eedc_prognose_heute_kwh` „IST bisher + Rest" und wich damit von der App-Anzeige ab. Seit dem Prognose-Kanon trägt der Sensor den **vollen kanonischen Tageswert** (== Anzeige); „Rest heute" ist der reine Rest. Automationen, die auf den alten „IST+Rest"-Wert gebaut haben, sollten auf `…_rest_today_kwh` umgestellt werden, wenn sie den Rest brauchen.

---

## 9. Counter vs. kWh — strikte Trennung

eedc unterscheidet seit v3.24.0 zwei Klassen kumulativer Sensoren:

| Klasse | Beispiele | Verarbeitung |
|---|---|---|
| **kWh-Felder** | `pv_erzeugung_kwh`, `ladung_kwh`, `entladung_kwh`, `stromverbrauch_kwh`, `einspeisung_kwh`, `netzbezug_kwh` | Fließen in die Energie-Bilanz, Performance Ratio, Lernfaktor. Wh→kWh, MWh→kWh werden automatisch konvertiert. |
| **Counter-Felder** (`KUMULATIVE_COUNTER_FELDER`) | `wp_starts_anzahl`, `wp_betriebsstunden` | Reine Zähler — **keine** Energie-Einheit, **keine** Aufnahme in die Energie-Bilanz. Faktor 1.0 statt 0.001 bei unbekannter Einheit im HA-Statistics-Pfad. |

> **Warum getrennt?** Würde ein Counter-Sensor versehentlich als kWh-Feld konsumiert (z. B. weil seine Unit fehlt), würde er die Energie-Bilanz mit physikalisch sinnlosen Werten (z. B. 50 000 „kWh"-Kompressor-Starts) verfälschen. Die strikte Klassen-Trennung ist Voraussetzung für die Roh-Counter-Unterstützung der Nibe-Integration in v3.24.1.

---

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

### Daten-Checker-Kategorie „Sensor-Mapping – HA-Statistics"

Prüft pro Anlage, ob alle in der Datenquellen-Zuordnung verwendeten **kWh-Sensoren** tatsächlich in HA-LTS landen (siehe [Handbuch Daten-Checker §4.9](HANDBUCH_DATEN_CHECKER.md#49-sensor-mapping--ha-statistics)):

| Befund | Bedeutung |
|---|---|
| **OK** | Alle kWh-Sensoren in LTS verfügbar |
| **WARNING** | kWh-Feld zeigt auf LTS-losen Sensor — Monatsabschluss bleibt leer (still kritisch) |
| **WARNING** | Counter-Feld zeigt auf LTS-losen Sensor — Snapshot läuft, aber Korrektur-Werkzeuge in der Energieprofil-Pflege wirken nicht |

Live-Zuordnungen (`leistung_w`, `soc`) werden nicht geprüft — sie lesen `state` direkt und brauchen kein LTS.

---

## 11. Export-Sensoren (eedc → HA)

Die bisherigen Abschnitte beschreiben Sensoren, die eedc **aus HA liest**. Dieser Abschnitt beschreibt die umgekehrte Richtung: berechnete eedc-Werte, die als **HA-Entitäten** bereitgestellt werden — per MQTT Discovery (empfohlen) oder REST. Einrichtung: [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export).

> **Zeithorizont:** Sofern nicht anders angegeben, beziehen sich die Werte auf die **Gesamtlaufzeit** (alle erfassten Monate, jeweils ab Anschaffungsdatum der Komponenten). Der laufende Monat fließt erst nach dem Monatsabschluss ein. Einzige Ausnahme: der **Spezifische Ertrag** ist aufs Jahr normiert (siehe unten).

> **Nachkommastellen — gleich für MQTT und REST:** Wie viele Nachkommastellen ein Export-Wert trägt, hängt an seiner **Größenart**, nicht am Export-Weg: Energie und Mengen (kWh, kWh/kWp, km, kg) **ganzzahlig**, Geld auf **2** Stellen, Prozent auf **1**, Leistung (kW) auf **2**, Stunden/Jahre auf **1**, übrige Kennwerte (COP, Zyklen, Rang) auf **2**. Ein kleiner, aber echter Wert wird dabei **nie auf 0 gerundet** — er bekommt so viele Stellen wie nötig (höchstens 3), damit aus 0,35 kW keine 0 wird. Sensor-Namen, Einheiten und die Anzahl der Entitäten sind unverändert; die HA-Historie zeigt für zurückliegende Zeitpunkte weiter die alten Werte.
>
> Ab v4.0.6 galt diese Regel zunächst nur für MQTT; der REST-Weg lieferte für dieselbe Größe eine andere Zahl (kWh mit einer Nachkommastelle). **Seit v4.0.7 sagen beide Wege dasselbe.** Wer eedc-Sensoren über die `rest`-Plattform eingebunden hat, sieht dort einmalig kürzere Werte — 39.692,4 kWh wird zu 39.692 kWh. Der Vollzyklen-Sensor geht den umgekehrten Weg (380 → 380,19): er ist eine dimensionslose Kennzahl und trägt jetzt dieselben zwei Stellen wie die Speicher-Anzeige in eedc.

### Anlage-weite Sensoren

| Sensor | Einheit | Bedeutung |
|---|---|---|
| `pv_erzeugung_gesamt_kwh` | kWh | Σ PV-Erzeugung aller erfassten Monate |
| `direktverbrauch_gesamt_kwh` | kWh | PV direkt verbraucht (ohne Speicherumweg) |
| `eigenverbrauch_gesamt_kwh` | kWh | Direktverbrauch + Speicher-Entladung + V2H |
| `einspeisung_gesamt_kwh` / `netzbezug_gesamt_kwh` | kWh | Zählerwerte |
| `gesamtverbrauch_kwh` | kWh | Eigenverbrauch + Netzbezug |
| `autarkie_prozent` / `eigenverbrauch_quote_prozent` | % | Quoten über die Gesamtlaufzeit — cockpit-gleich, inkl. Erzeuger hinter dem Zähler (siehe Wertsemantik unten) |
| `spezifischer_ertrag_kwh_kwp` | kWh/kWp | **Aufs Jahr normiert** — siehe Hinweis unten |
| `netto_ertrag_euro` | € | **Einspeiseerlös + EV-Ersparnis + BKW-Ersparnis + Sonstige (Erträge − Ausgaben)** — siehe Wertsemantik unten |
| `einspeise_erloes_euro` / `eigenverbrauch_ersparnis_euro` | € | Finanz-Bausteine (deckungsgleich mit Cockpit/Berichten) |
| `co2_ersparnis_kg` | kg | **Volle CO₂-Bilanz** (PV-Eigenverbrauch inkl. BKW/sonstige Erzeuger + Wärmepumpe + E-Mobilität) — siehe Wertsemantik unten |
| `investition_gesamt_euro`, `jahres_ersparnis_euro`, `roi_prozent`, `amortisation_jahre` | €, €/Jahr, %, Jahre | Investitions-KPIs |
| `speicher_zyklen`, `speicher_effizienz_prozent` | —, % | Speicher-KPIs. `speicher_zyklen` = **Entladung ÷ Brutto-Kapazität** — seit 2026-07-28 dieselbe Definition wie in Komponenten-Hub, Cockpit und PDF ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)). Nicht zu verwechseln mit den „SoC-Hüben" der Energieprofil-Tabelle. |
| `letzter_import_jahr/_monat/_monat_name`, `anzahl_monate_erfasst` | — | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |

Zusätzlich erscheinen **pro Komponente** (E-Auto, Wärmepumpe, Speicher, Wallbox …) eigene Sensoren (z. B. `e_auto_pv_anteil_prozent`, `wp_cop_durchschnitt`, `wp_betriebsstunden`) — jeweils unter einem eigenen HA-Gerät.

> **Wertsemantik `netto_ertrag_euro` (ab v4.0):** Der Sensor trägt den kanonischen Netto-Ertrag aus dem Finanz-Aggregat-SoT: **Einspeiseerlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto** (Erträge − Ausgaben aus den Sonstigen Positionen, inklusive der auf **Anlage-Ebene** erfassten Positionen ab v4.0). Der Sensor-Name und die Einheit sind unverändert; nur der **Wert** enthält jetzt die Sonstigen Positionen. Achtung: die frühere Kurzformel „Einspeiseerlös + EV-Ersparnis" (noch als statisches `formel`-Label in der Definition) beschreibt nur zwei der vier Bausteine — maßgeblich ist die Summe in [Berechnungen §3.2](BERECHNUNGEN.md#32-finanzen-cockpit). Der **USt-Eigenverbrauchs-Abzug** (nur bei Regelbesteuerung) ist seit der #326-Inventur ebenfalls enthalten — `ha_export.py` rechnet `netto_ertrag -= ust_eigenverbrauch` über denselben SoT-Helper wie Cockpit und Aussichten. (Bis dahin stand hier das Gegenteil: „bleibt eine Cockpit-Zusatzlogik und ist im Export-Sensor nicht enthalten." Das war der Stand vor v4.0; die Zeile ist beim Fix nicht mitgezogen worden.)
>
> **Ergänzung 2026-07-31 (N-13):** Bei Anlagen mit einem **Dienstwagen** (E-Auto oder Wallbox mit „ausschließlich dienstliches Laden") zieht der Sensor jetzt auch die **dienstlichen Ladekosten** ab — bis dahin tat er das als einzige der drei Sichten nicht und stand damit über der Cockpit-Kachel, auf die er sich bezieht. Für diese Anlagen fällt der Wert einmalig; alle anderen sind unberührt. Formel und Begründung: [Berechnungen §3.10](BERECHNUNGEN.md).
>
> **Damit nennt der Sensor alle vier Abzüge/Bausteine der Cockpit-Kachel** — Einspeiseerlös, EV-Ersparnis, BKW-Ersparnis, Sonstige-Netto, abzüglich Netzbezugskosten, USt-Eigenverbrauch und dienstlicher Ladekosten. Er ist mit ihr deckungsgleich.

> **Wertsemantik `co2_ersparnis_kg` (ab v4.0, DI-2/DI-2-B):** Der Sensor trägt die **volle CO₂-Bilanz** aus dem kanonischen Helfer `berechne_co2_bilanz` — **PV-Eigenverbrauch** (inkl. der Erzeugung von BKW/sonstigen Erzeugern hinter dem Zähler) **+ Wärmepumpe** (vermiedenes Gas mit η_gas = 0,90 minus WP-Strom-CO₂) **+ E-Mobilität** (vermiedener Benziner minus Netzladung). Damit ist er **exakt deckungsgleich** mit der Cockpit-CO₂-Kachel (früher rechnete der Sensor nur `PV-Eigenverbrauch × Strom-Faktor`). Ein Brennstoff-Erzeuger (BHKW) zählt zwar in EV/Autarkie, erzeugt aber bewusst **keine** CO₂-Gutschrift. Herleitung: [Berechnungen §3.8](BERECHNUNGEN.md#38-co2-bilanz).

> **Wertsemantik `autarkie_prozent` / `eigenverbrauch_quote_prozent` (ab v4.0, DI-2-B):** Beide Quoten werden **identisch zum Cockpit** gerechnet und beziehen die **Erzeugung hinter dem Zähler** ein (`erzeugung_hinter_zaehler_kwh` = PV inkl. Balkonkraftwerk + sonstige Erzeuger, die in denselben Hauszähler speisen). Der Nenner der Eigenverbrauchsquote ist diese Gesamt-Erzeugung, nicht „nur PV". Der **spezifische Ertrag** bleibt bewusst eine reine PV-Kennzahl (nur `pv_erzeugung`).

> **Spezifischer Ertrag — warum nicht einfach kWh ÷ kWp?** Der Sensor ist **annualisiert** und damit deckungsgleich mit der Cockpit-Kachel: saisonal gewichtet (PVGIS-Monatsverteilung) und mit der pro Monat tatsächlich aktiven PV-Leistung (Erweiterung/Teil-Rückbau wird korrekt gewichtet). Die naive Division *Gesamterzeugung ÷ heutiges kWp* würde bei 3 Jahren Historie etwa das Dreifache des gewohnten Jahreswerts anzeigen.
>
> **Woher die kWp im Nenner kommt (ab v4.0.2):** aus dem Feld **Leistung (kWp)** der jeweiligen Investition; ist es leer, aus den Detail-Feldern der Komponente (`kwp`/`leistung_kwp`, bei Balkonkraftwerken auch `leistung_wp` × `anzahl`). Vorher zählte nur das Leistungsfeld — bei importierten oder sehr alten Komponenten stand dort nichts, der Nenner war zu klein und der Sensorwert entsprechend **zu hoch**. Wer das betrifft, sieht nach dem Update einen einmaligen Sprung nach unten auf den richtigen Wert; Cockpit-Kachel und Sensor bleiben dabei deckungsgleich.

### PV-Prognose-Sensoren (`eedc_prognose_*`)

Quelle ist **immer die eedc-eigene Prognose** (OpenMeteo × Korrekturprofil) — nie Solcast/SFML, denn deren Werte liegen über die jeweilige HA-Integration ohnehin nativ in HA (kein Doppel-Export, keine Drift).

Die Korrektur erfolgt **pro Stunde** über die Korrekturprofil-Kaskade (Sonnenstand × Wetter → Saison-Stunde → Sonnenstand → Skalar; bei Anlagen ohne gelerntes Profil greift wie bisher der Lernfaktor-Skalar). Der Tagessensor ist dabei stets die Σ seiner korrigierten Stundenwerte — Sensor-State und `stundenprofil_kwh`-Attribut passen exakt zusammen. Dieselbe Berechnung speist die Spalte „eedc" im Prognosen-Vergleich: App-Ansicht und HA-Sensor zeigen denselben Tageswert.

| Sensor | Bedeutung |
|---|---|
| `eedc_prognose_heute_kwh` | **Kanonische Tagesprognose** (== App-Anzeige): die volle Prognose für den ganzen Tag, **nicht** IST + Rest. Ändert sich, wenn OpenMeteo einen neuen Modelllauf liefert. Trägt das Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 Werte; Slot N = Energie der Stunde N−1 → N). |
| `eedc_prognose_rest_today_kwh` | **Echter Rest**: Prognose der verbleibenden Stunden ab jetzt (ohne IST) — die **laufende Stunde geht anteilig** nach den noch verbleibenden Minuten ein (#339), der Wert sinkt also gleichmäßig statt in Stundensprüngen. Der Steuerungswert für Automationen — „wie viel PV kommt heute noch?" |
| `eedc_prognose_day_plus_1/2/3_kwh` | Tagesprognose morgen / übermorgen / in 3 Tagen. Trägt jeweils das korrigierte Stundenprofil des Tages als Attribut `stundenprofil_kwh` (24 kWh-Werte, Slot-Konvention wie oben) — z. B. für Lade-Planung per Template. Werte ändern sich, wenn OpenMeteo einen neuen Modelllauf liefert (alle paar Stunden) **oder** das gelernte Korrekturprofil aktualisiert wird (nächtlich) — stundenlang unveränderte Werte sind normal. |
| `eedc_speicher_voll_um` | Uhrzeit, zu der der Speicher voraussichtlich voll ist (Simulation ab **aktuellem** Ladestand). |

> **Vormittag/Nachmittag:** eigene VM/NM-Sensoren gibt es bewusst nicht — beides ist per HA-Template direkt aus `stundenprofil_kwh` ableitbar (z. B. `{{ state_attr('sensor.…_day_plus_1_kwh', 'stundenprofil_kwh')[:13] | sum }}` für die Stunden bis 12 Uhr).

### Börsenpreis-Trigger (`eedc_preis_*`)

Grundlage ist der **Day-Ahead-Börsenpreis** (nicht der Anbieter-Endpreis — der variiert je Vertrag/Region, die Kurvenform ist dieselbe). Tag- und Nacht-Fenster werden **solar-basiert getrennt** bewertet (Sonnenauf-/-untergang, wandert saisonal).

**Günstig-Definition (zweistufig):** Eine Stunde gilt als günstig, wenn sie (1) zu den 5 billigsten ihres Fensters gehört **und** (2) ihr Preis unter der **Günstig-Schwelle** liegt — standardmäßig 10 % unter dem Tagesdurchschnitt ohne die 3 teuersten Stunden. Der Prozentsatz ist je Anlage einstellbar ([MQTT-Export-Seite](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export)); **0 % deaktiviert Stufe (2)**, dann greift wieder allein die Rang-Regel. Ohne die Schwelle wären die „günstigsten" Stunden rein relativ — erzwungener Verbrauch oder Netzladung in einer kaum billigeren Stunde ergibt keinen Sinn.

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

⚠️ Manche Wechselrichter liefern das Vorzeichen umgekehrt. In der [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) gibt es dafür am signierten Leistungs-Feld das **±**-Symbol (Vorzeichen umkehren, `live_invert`) — quellen-unabhängig direkt am Wert.

### Einheiten-Konvertierung

Live-Leistungssensoren werden automatisch konvertiert: `kW → W`, `MW → W`. Für kWh-Sensoren wird `Wh → kWh` und `MWh → kWh` automatisch skaliert. Counter-Felder (siehe §9) bleiben mit Faktor 1.0 — kein automatisches Wh→kWh, da physikalisch keine Energie.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
