# Sensor-Referenz: Feldnamen, Einheiten, Anforderungen

**Version 4.0** | Stand: 2026-07-25 — Referenz für UI-Beschreibungen in der Datenquellen-Zuordnung und im MQTT-Setup

> Siehe auch: [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md) — welcher der Wärmepumpen-Zähler unten welche Kennzahl möglich macht, und was ohne ihn passiert.

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
| `ladung_kwh` | Ladung — bei Speichern mit Netzladung: **„Ladung (gesamt, inkl. Netz)"** | kWh | Kumulativ oder Tagessensor | Gesamte im Monat in den Speicher geladene Energie, **Netzladung eingeschlossen**. Muss ≥ 0 sein. `ladung_netz_kwh` ist ein *davon*-Anteil, kein zweiter Summand — ein Gerät, das PV- und Netzladung getrennt zählt, braucht hier die Summe beider (HA-Helfer). **Messstelle:** die zur [Kopplung](HANDBUCH_EINSTELLUNGEN.md#34-typ-spezifische-parameter) passende Seite — bei AC-Kopplung hausseitig hinter dem Batterie-Wechselrichter, bei DC-Kopplung am Batterie-Anschluss. |
| `entladung_kwh` | Entladung | kWh | Kumulativ oder Tagessensor | Gesamte im Monat aus dem Speicher entladene Energie. Muss ≥ 0 sein. **Dieselbe Messstelle wie die Ladung** — kommen die beiden von verschiedenen Seiten (etwa Ladung DC aus der Hersteller-Cloud, Entladung AC aus einem Riemann-Sensor), enthält der Wirkungsgrad die Wandlung nur in eine Richtung. |
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
| `leistung_kuehlen_w` | Leistung Kühlen | W | Momentan | Nur bei getrennter Messung: Leistungsaufnahme Kühlbetrieb. Optional, reine Anzeige — die Mengen kommen aus dem kWh-Zähler. |
| `warmwasser_temperatur_c` | Warmwassertemperatur | °C | Momentan | Aktuelle Warmwassertemperatur. Optional, wird als Gauge angezeigt. |

### MQTT Energy Topics

| MQTT-Topic | Feld | Hinweis |
|------------|------|---------|
| `eedc/.../energy/inv/{inv_id}_{name}/stromverbrauch_kwh` | `stromverbrauch_kwh` | |
| `eedc/.../energy/inv/{inv_id}_{name}/heizenergie_kwh` | `heizenergie_kwh` | |
| `eedc/.../energy/inv/{inv_id}_{name}/warmwasser_kwh` | `warmwasser_kwh` | |
| ⚠️ `strom_heizen_kwh` / `strom_warmwasser_kwh` | — | **Kein MQTT-Topic** — nur via HA-Sensor |

### 4a. Verbrauch je Betriebsart und je Innengerät

> **Bei einer Klimaanlage stehen diese Felder gleich mit da.** An jeder anderen
> Wärmepumpenart findest du sie unter *Einstellungen → Datenquellen* beim Gerät
> hinter **„Weitere Größen erfassen"** — sie sind dort seltener, aber genauso
> zuordenbar. Wer einen getrennten Kühlzähler an seiner
> Luft-Wasser- oder Sole-Wasser-Wärmepumpe hat, trägt ihn dort ein; sobald ein
> Sensor zugeordnet ist, steht das Feld oben bei den anderen.
>
> Alle Felder sind **optional**: kein Sensor, keine Anzeige.

Ein Gerät, das heizt, kühlt, lüftet und entfeuchtet, tut das oft über
**denselben** Zähler. Wer die Anteile getrennt messen kann, trägt sie hier ein —
sie sind **Teilmengen** des Gesamtverbrauchs und werden nie dazuaddiert.

⚠️ **Kühlen, Lüften und Entfeuchten zählen nicht in die Arbeitszahl.** Sie
erzeugen keine Wärme, die sich messen ließe; läge ihr Strom im Nenner, sähe eine
Anlage, die im Sommer kühlt oder viel lüftet, wie eine schlechte Heizung aus.
Für Wirtschaftlichkeit und CO₂ gilt beim Kühlen dasselbe schon länger. Ist der
ganze Verbrauch eines Zeitraums Kühlbetrieb, steht statt der Arbeitszahl der
Grund dafür.

**Lüften und Entfeuchten bekommen eine eigene Zeile in der Aufteilung, sobald du
einen Zähler dafür zugeordnet hast** — vorher stecken sie in „nicht aufgeteilt".
Eine Kennzahl bekommen sie bewusst nicht: Es gibt keine Nutzenergie, gegen die
man sie rechnen könnte.

| Feld | Label | Einheit | Sensortyp |
|------|-------|---------|-----------|
| `betriebsart_strom_heizen_kwh` | Strom Heizbetrieb | kWh | Kumulativ oder Tagessensor |
| `betriebsart_strom_kuehlen_kwh` | Strom Kühlbetrieb | kWh | Kumulativ oder Tagessensor |
| `betriebsart_strom_lueften_kwh` | Strom Lüftbetrieb | kWh | Kumulativ oder Tagessensor |
| `betriebsart_strom_entfeuchten_kwh` | Strom Entfeuchtungsbetrieb | kWh | Kumulativ oder Tagessensor |
| `betriebsart_nutzenergie_*_kwh` | Nutzenergie je Betriebsart | kWh | Kumulativ, **thermisch** |
| `soll_temperatur_c` / `ist_temperatur_c` | Soll-/Raumtemperatur | °C | Momentan, reine Anzeige |

> **`betriebsart_nutzenergie_kuehlen_kwh` ist die Kältemenge — und der einzige
> Zähler, der die *Arbeitszahl Kühlen* möglich macht** (Kältemenge ÷ Kühlstrom).
> Ohne ihn steht dort der Grund statt einer Zahl; geschätzt wird nichts, weil aus
> einem angenommenen Wirkungsgrad genau der Faktor zurückkäme, mit dem gerechnet
> wurde. **Sie heißt bewusst nicht „SEER"** — das ist eine genormte
> Prüfstandsgröße, dies hier ist der Quotient deiner beiden Zähler. Ausführlich:
> [Wärme & Klima §3](HANDBUCH_WAERME_KLIMA.md#3-was-eedc-bewusst-nicht-sagt).

**Mehrere Innengeräte (Multisplit):** Trag sie beim Gerät unter *Innengeräte*
ein (Bezeichnung, z. B. „Büro"). Danach gibt es **jedes** der Felder oben
zusätzlich je Innengerät — der Feld-Key trägt dessen Nummer
(`betriebsart_strom_kuehlen_kwh-3`), das Label den Raumnamen
(„Büro: Strom Kühlbetrieb").

**Vorrang:** Liegt ein Betriebsart-Zähler vor, gilt er — und zwar für **alle**
Betriebsarten dieses Geräts. Die Aufteilung, die eedc sonst aus dem
`betriebsmodus` ableitet, tritt dann zurück; eine Betriebsart ohne Zähler
erscheint unter „nicht aufgeteilt". Steht ein Wert **am Gerät**, schlägt er die
Summe der Innengeräte — beide beschreiben dieselbe Menge, sie werden nie addiert.

> ⚠️ **Was ein Innengerät NICHT misst.** An einem Multisplit hängt **ein**
> Außengerät an mehreren Innengeräten. Was eine Hersteller-App dort als
> Verbrauch eines Innengeräts anzeigt, ist der Anteil des **Außengeräts**,
> zugeschrieben an das gerade **anfordernde** Innengerät — und welches das ist,
> entscheidet die Einschaltreihenfolge. Mitsubishi sagt es selbst:
> *„It is not possible to attribute the output of the outdoor units to specific
> indoor units."* Die belastbare Menge ist ein eigener Zähler am Außengerät.

#### So bekommst du die vier Zähler in Home Assistant

**Weg 1 — Utility Meter (empfohlen, für die kWh-Felder).** Er *zählt* und
übersteht Neustarts; ein Template-Sensor kann das nicht.

1. *Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → **Utility
   Meter***.
2. **Eingangssensor**: der Energie-Sensor deiner Klimaanlage (kWh).
3. **Tarife**: `heizen`, `kuehlen`, `lueften`, `entfeuchten`.
   HA legt daraus je Tarif einen eigenen zählenden Sensor an.
4. Eine Automatisierung schaltet den aktiven Tarif, ausgelöst vom Zustand der
   `climate`-Entität — Aktion **`select.select_option`** auf die
   `select.…`-Entität, die der Utility Meter mit angelegt hat.
5. In eedc unter *Einstellungen → Datenquellen* die vier Tarif-Sensoren den
   vier Feldern zuordnen.

**Weg 2 — Template-Sensor**, für Momentanwerte und Umrechnungen: Leistung je
Betriebsart (`{{ leistung if modus == 'cool' else 0 }}`), Einheiten- und
Vorzeichenkorrekturen, oder das Zusammenfassen mehrerer Entitäten zu einer.

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

## 7. Sonstiges (Erzeuger / Verbraucher / Speicher / Verbrauchszähler)

### Monatserfassung

| Feld | Kategorie | Label | Einheit | Beschreibung |
|------|-----------|-------|---------|-------------|
| `erzeugung_kwh` | Erzeuger | Erzeugung | kWh | Erzeugte Energie (z.B. BHKW, Windrad). Zählt hinter dem Hauszähler in die Eigenverbrauchs-/Autarkie-Bilanz. |
| `verbrauch_sonstig_kwh` | Verbraucher | Verbrauch | kWh | Verbrauchte Energie (z.B. Sauna, Pool). |
| `bezug_pv_kwh` | Verbraucher | davon PV | kWh | PV-gedeckter Anteil des Verbrauchs. Optional. |
| `bezug_netz_kwh` | Verbraucher | davon Netz | kWh | Netz-gedeckter Anteil des Verbrauchs. Optional. |
| `erzeugung_kwh` | Speicher | Erzeugung/Entladung | kWh | Entladene Energie. |
| `verbrauch_sonstig_kwh` | Speicher | Verbrauch/Ladung | kWh | Geladene Energie. |
| `zaehlerstand` | Verbrauchszähler | Zählerstand | *(vom Gerät)* | #377 — der abgelesene Stand eines Gas-, Wasser- oder Ölzählers. **Erfasst, nicht bewertet:** geht in keine Bilanz, keine Quote, keine Wirtschaftlichkeit, kein CO₂ und nicht in die Gemeinschaftsdaten. |

> ⚠ **Der Zählerstand ist bewusst einheitenlos gespeichert.** Was neben der Zahl
> steht (m³, l, kg, t, kWh), gehört zum **Gerät** (`zaehler_einheit`) und wird
> nur zur Anzeige geholt — eedc rechnet Zählerstände nie um. Genau diese leere
> Einheit ist die Sicherung dagegen, dass ein Gasverbrauch in der Strombilanz
> landet.
>
> **Sensor-Anforderung:** ein monoton steigender Zählerstand
> (`state_class: total_increasing`). Ein Sensor, der den *Verbrauch je Tag*
> liefert und nachts zurückspringt, passt hier **nicht** — eedc bildet die
> Menge aus der Differenz zweier Stände.
>
> **Zählerwechsel:** altes Gerät stilllegen (Stilllegungsdatum setzen, `aktiv`
> **an** lassen) und ein neues anlegen. Details:
> [Handbuch Einstellungen §3.4a](HANDBUCH_EINSTELLUNGEN.md).

### Live-Dashboard

| Feld | Label | Einheit | Beschreibung |
|------|-------|---------|-------------|
| `leistung_w` | Leistung | W | Aktuelle Leistung. |

> Ein **Verbrauchszähler** hat kein Live-Feld: Er führt keine Leistung, und eine
> m³-Reihe auf der kW-Achse des Energieflusses wäre eine Einheiten-Verwechslung.
> Sein aktueller Stand steht stattdessen in *Live → Auf einen Blick* unter
> **Zählerstände**.

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
| `eedc_prognose_heute_rollend_kwh` | **Heute (nachgeführt)** — was heute bereits erzeugt wurde **plus** die Prognose der Reststunden. Folgt dem IST; `…_heute_kwh` folgt dagegen OpenMeteo. Beide stehen bewusst nebeneinander (rapahl-PN 2026-08-23). |
| `eedc_prognose_day_plus_1/2/3_kwh` | Tagesprognose morgen / übermorgen / in 3 Tagen. Attribut `stundenprofil_kwh` = 24 Backward-Slots (kWh); Sensor-State == Σ Slots. |
| `eedc_speicher_voll_um` | Uhrzeit „Speicher voll" aus der SoC-Simulation ab aktuellem Speicherstand — **inkl. Ladeverluste**: gerechnet mit dem gepflegten Wirkungsgrad des Speichers. Vorher lief die Rechnung verlustfrei und meldete deshalb zu früh. |

> ⚠ **Welchen der drei nehme ich?** `…_heute_kwh` beantwortet *was sagt die Vorhersage für
> diesen Tag* — er ist die Zahl, die App, MQTT und Persistenz gemeinsam tragen, und er ändert
> sich nur, wenn OpenMeteo einen neuen Modelllauf liefert. `…_heute_rollend_kwh` beantwortet
> *worauf läuft der Tag tatsächlich hinaus* — er zieht die schon gemessenen Stunden heran und
> reagiert damit auf einen Tag, der besser oder schlechter läuft als vorhergesagt.
> `…_rest_today_kwh` ist der reine Rest. **Ihre Differenz ist keine sinnvolle Größe:**
> `…_heute_kwh` enthält für die vergangenen Stunden die *Vorhersage*, nicht die Messung.
>
> **Warum diese Sensoren kein `device_class` tragen.** Sie liefern kWh, sind aber **keine
> Zähler**: eine Tagesprognose springt jeden Tag zurück, und die Summe zweier Prognosen ergibt
> keine sinnvolle Zahl. Home Assistant verlangt für `device_class: energy` genau einen Zähler
> (`state_class` `total`/`total_increasing`) und nimmt Sensoren mit einer anderen Kombination
> **von der Langzeitstatistik aus** — sie zeigen dann einen Wert, ohne dass HA ihn mitschreibt.
> Ohne `device_class` ist `state_class: measurement` zulässig, und HA führt min/mean/max je
> Stunde. Bis v4.0.27 war das falsch gesetzt (gemeldet von rapahl); die Einheit kWh stand und
> steht unverändert am Sensor.

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
| `investition_gesamt_euro`, `jahres_ersparnis_euro`, `roi_prozent`, `amortisation_jahre` | €, €/Jahr, %, Jahre | Investitions-KPIs — Nenner ist der **Kapitaleinsatz** (siehe Hinweis unten) |
| `speicher_zyklen`, `speicher_effizienz_prozent` | —, % | Speicher-KPIs. `speicher_zyklen` = **Entladung ÷ Brutto-Kapazität** — seit 2026-07-28 dieselbe Definition wie in Komponenten-Hub, Cockpit und PDF ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)). Nicht zu verwechseln mit den „SoC-Hüben" der Energieprofil-Tabelle. |
| `letzter_import_jahr/_monat/_monat_name`, `anzahl_monate_erfasst` | — | Status der Datenbasis (Diagnose-Kategorie — erscheint in HA im Diagnose-Bereich des Geräts) |

| `eedc_grundlast_kw` | kW | **Gemessener** Nacht-Sockel des laufenden Monats (Median der Stunden 0–5 Uhr aus dem Energieprofil) — dieselbe Zahl wie die Kachel in *Cockpit → Monat*. ⚠ **Nicht zu verwechseln mit „Grundlast (Prognose)"** in *Cockpit → Live*: die stammt aus dem Verbrauchsprofil und ist ohne eigene Historie ein Standard-Lastprofil. Ohne gemessene Nachtstunden entsteht **kein** Sensor. |
| `eedc_prognose_heute_vormittag_kwh` / `…_heute_nachmittag_kwh` / `…_morgen_vormittag_kwh` / `…_morgen_nachmittag_kwh` | kWh | PV-Prognose je Tageshälfte, für **heute und morgen** (die Abendentscheidung braucht den Folgetag). ⭐ **Die Grenze ist der Sonnenhöchststand**, nicht 13:00 — dieselbe Aufteilung wie in *Cockpit → Aussicht*. Sie reist als Attribut **`solar_noon`** („13:28") mit, damit eine Automation sie lesen kann statt sie zu raten. |

Zusätzlich erscheinen **pro Komponente** (E-Auto, Wärmepumpe, Speicher, Wallbox …) eigene Sensoren (z. B. `e_auto_pv_anteil_prozent`, `wp_cop_durchschnitt`, `wp_betriebsstunden`) — jeweils unter einem eigenen HA-Gerät.

> ⚠ **Bis August 2026 galt der Satz darüber nur für den REST-Export.** Über **MQTT-Discovery** wurden ausschließlich die *anlagenweiten* Sensoren verschickt; die Geräte-Sensoren erreichten Home Assistant nie. Seither publiziert eedc sie mit — in HA erscheinen dadurch **neue Geräte und Entitäten**. Bestehende Entitäten und ihre Langzeitstatistik sind unberührt.

**Neu je Wärmepumpe/Klimaanlage:** `wp_betriebsmodus` — der **aktuelle** Betrieb im Klartext (*Heizen · Kühlen · Entfeuchten · Lüften · Aus · Unbestimmt*), aus der zugeordneten `climate`-Quelle über den eedc-Kanon normalisiert. Liefert dein Gerät zusätzlich `hvac_action` (den Ist-Betrieb), verfeinert der den eingestellten Modus: Nennt er eine Richtung, hat er Vorrang — steht dort **Leerlauf** (`idle`), bleibt dein eingestellter Modus stehen, denn ein taktendes Gerät verliert seine Betriebsart nicht. **Ohne zugeordnete Quelle gibt es den Sensor nicht** — eedc behauptet keinen Modus, den es nicht kennt.
>
> ⏱ **Aktualisierung im Publish-Takt** (Standard 60 Minuten, einstellbar). Für einen Modus, der in der Praxis saisonal gestellt wird, ist das genug; wer sekundengenau steuern will, liest die `climate`-Entität direkt. Was es **nur** von eedc gibt, ist die über die Stunde stabilisierte, auf den Kanon gebrachte Aussage — und dieselbe Einteilung, nach der eedc den Strom aufteilt.

> **Wertsemantik `netto_ertrag_euro` (ab v4.0):** Der Sensor trägt den kanonischen Netto-Ertrag aus dem Finanz-Aggregat-SoT: **Einspeiseerlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto** (Erträge − Ausgaben aus den Sonstigen Positionen, inklusive der auf **Anlage-Ebene** erfassten Positionen ab v4.0). Der Sensor-Name und die Einheit sind unverändert; nur der **Wert** enthält jetzt die Sonstigen Positionen. Achtung: die frühere Kurzformel „Einspeiseerlös + EV-Ersparnis" (noch als statisches `formel`-Label in der Definition) beschreibt nur zwei der vier Bausteine — maßgeblich ist die Summe in [Berechnungen §3.2](BERECHNUNGEN.md#32-finanzen-cockpit). Der **USt-Eigenverbrauchs-Abzug** (nur bei Regelbesteuerung) ist seit der #326-Inventur ebenfalls enthalten — `ha_export.py` rechnet `netto_ertrag -= ust_eigenverbrauch` über denselben SoT-Helper wie Cockpit und Aussichten. (Bis dahin stand hier das Gegenteil: „bleibt eine Cockpit-Zusatzlogik und ist im Export-Sensor nicht enthalten." Das war der Stand vor v4.0; die Zeile ist beim Fix nicht mitgezogen worden.)
>
> **Ergänzung 2026-07-31 (N-13):** Bei Anlagen mit einem **Dienstwagen** (E-Auto oder Wallbox mit „ausschließlich dienstliches Laden") zieht der Sensor jetzt auch die **dienstlichen Ladekosten** ab — bis dahin tat er das als einzige der drei Sichten nicht und stand damit über der Cockpit-Kachel, auf die er sich bezieht. Für diese Anlagen fällt der Wert einmalig; alle anderen sind unberührt. Formel und Begründung: [Berechnungen §3.10](BERECHNUNGEN.md).
>
> **Damit nennt der Sensor alle vier Abzüge/Bausteine der Cockpit-Kachel** — Einspeiseerlös, EV-Ersparnis, BKW-Ersparnis, Sonstige-Netto, abzüglich Netzbezugskosten, USt-Eigenverbrauch und dienstlicher Ladekosten. Er ist mit ihr deckungsgleich.

> **Wertsemantik `amortisation_jahre` · `roi_prozent` · `jahres_ersparnis_euro` (ab v4.0.12):** Nenner aller drei ist der **Kapitaleinsatz** — relevante Anschaffungskosten **plus** einmalige Ausgaben aus dem Monatsabschluss **minus** einmalige Erträge (Förderung, THG-Quote). Vorher wurde eine einmalige Ausgabe wie eine jährlich wiederkehrende Belastung vom Zähler abgezogen (eine Reparatur verlängerte die Amortisation dauerhaft und wurde jedes Folgejahr schlechter), ein einmaliger Ertrag wurde umgekehrt jedes Prognosejahr gutgeschrieben. Zweite Korrektur an derselben Rechnung: **jeder Ersparnis-Posten wird mit seiner eigenen Laufzeit** hochgerechnet, nicht mit der Monatszahl der Anlage — eine später angeschaffte Komponente wurde im Zähler zeitanteilig verdünnt, während ihre Kosten voll im Nenner standen.
>
> ⚠ **Die drei Sensoren springen dadurch einmalig** (an der Referenzanlage 26,4 → 18,5 Jahre); in der Langzeitstatistik ist das ein Sprung an einem Tag, es gehen keine Daten verloren. **`netto_ertrag_euro` ist unberührt** — die Zeitraum-Bilanz rechnet unverändert. Der ausgeschriebene **Rechenweg** im Attribut nennt seit derselben Version jeden Posten mit seiner Monatszahl und den Betriebskosten-Abzug; vorher wich er um mehrere hundert Euro vom Wert daneben ab. Herleitung: [Berechnungen §3.6](BERECHNUNGEN.md), Begriffe im [Glossar](GLOSSAR.md).

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
| `eedc_speicher_voll_um` | Uhrzeit, zu der der Speicher voraussichtlich voll ist (Simulation ab **aktuellem** Ladestand, **mit** dem gepflegten Wirkungsgrad — bei mehreren Speichern dem niedrigsten). |

> **Vormittag/Nachmittag:** eigene VM/NM-Sensoren gibt es bewusst nicht — beides ist per HA-Template direkt aus `stundenprofil_kwh` ableitbar (z. B. `{{ state_attr('sensor.…_day_plus_1_kwh', 'stundenprofil_kwh')[:13] | sum }}` für die Stunden bis 12 Uhr).

### Börsenpreis-Trigger (`eedc_preis_*`)

Grundlage ist der **Day-Ahead-Börsenpreis** (nicht der Anbieter-Endpreis — der variiert je Vertrag/Region, die Kurvenform ist dieselbe). Tag- und Nacht-Fenster werden **solar-basiert getrennt** bewertet (Sonnenauf-/-untergang, wandert saisonal).

**Welcher Tag gemeint ist:** der Kalendertag der **Strommarkt-Zeitzone** (CET/CEST für DE und AT) — Stunde 0 ist die Stunde nach Mitternacht deiner Uhr, unabhängig davon, in welcher Zeitzone der eedc-Container läuft. Bis v4.0 wurde stattdessen ein UTC-Tag abgefragt: Die Stunden 0 und 1 trugen dadurch die Preise des **Folgetages** (in der Winterzeit die Stunde 0), und in einem Container ohne gesetzte Zeitzone lagen alle Stunden um denselben Betrag daneben. An den beiden Umstellungstagen hat das Rang-Profil folgerichtig 23 bzw. 24 Einträge — im Oktober zählt die erste der beiden Zwei-Uhr-Stunden.

**Wann der Wert wechselt:** mit dem MQTT-Versand, und der läuft **an der Uhr** — bei der Voreinstellung (alle 60 Minuten) also zur vollen Stunde, bei kürzeren Abständen im passenden Raster (`:00`, `:15`, `:30`, `:45`). Bis dahin lief der Versand ab dem Startzeitpunkt des Add-ons durch; der neue Preis kam damit um einen Versatz zu spät an, den allein der letzte Neustart bestimmte (gemeldet: `09:12:56` und, nach einem Update, `11:08:02`). Ein Intervall, das nicht auf die Uhr passt (z. B. 90 Minuten), behält seinen freien Takt — dort würde jede Ausrichtung den eingestellten Abstand verändern.

**Günstig-Definition:** Eine Stunde gilt als günstig, wenn ihr Preis unter der **Günstig-Schwelle** liegt — standardmäßig 10 % unter dem Tagesdurchschnitt ohne die 3 teuersten Stunden („optimierter Ø"). Der Prozentsatz ist je Anlage einstellbar ([MQTT-Export-Seite](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export)). Ohne die Schwelle wären die „günstigsten" Stunden rein relativ — erzwungener Verbrauch oder Netzladung in einer kaum billigeren Stunde ergibt keinen Sinn.

**Rang und „günstig" sind zwei verschiedene Aussagen** (ab v4.0.10). Der **Rang** beantwortet „gehört diese Stunde zu den fünf billigsten ihres Fensters?" und ist deshalb bei 5 gedeckelt. **Günstig** beantwortet „liegt sie unter der Schwelle?" und ist es nicht: liegen sieben Nachtstunden unter der Schwelle, meldet der Zähler auch sieben. Bis v4.0.9 zählte er nur die Ränge und war damit ebenfalls bei 5 gedeckelt — als Anzeige stimmig, als **Divisor** in einer Automation zu klein.

**Was 0 % bedeutet:** Der Prozentsatz gibt an, wie weit *unter* dem optimierten Ø eine Stunde liegen muss. Bei **0 %** liegt die Schwelle damit **genau auf dem Ø** — günstig ist dann alles, was unter dem Tagesdurchschnitt (ohne die 3 Peaks) liegt. Die Schwelle ist also nicht abgeschaltet, sie ist nur nicht zusätzlich abgesenkt. (Bis v4.0 stand hier „0 % deaktiviert die Schwelle, dann zählen wieder die 5 günstigsten". Das hat der Code nie getan; der Top-5-Deckel hat den Unterschied verdeckt.)

| Sensor | Bedeutung |
|---|---|
| `eedc_preis_rang` | Rang der **aktuellen** Stunde: 1–5 = eine der fünf billigsten ihres Fensters **und** unter der Schwelle, 99 = teuer/Rest. Attribute: `rang_profil` (alle 24 Stunden, s. u.), `guenstig_schwelle_cent` und `optimierter_durchschnitt_cent` (beide ct/kWh), `datum` (Kalendertag des Profils) sowie der **Morgen-Satz** `morgen_verfuegbar` · `datum_morgen` · `rang_profil_morgen` · `guenstig_schwelle_cent_morgen` · `optimierter_durchschnitt_cent_morgen` (s. u.). |
| `eedc_preis_guenstige_stunden_anzahl` | Anzahl Stunden heute unter der Schwelle (Tag + Nacht) — **ungedeckelt** |
| `eedc_preis_guenstige_stunden_tag` / `_nacht` | dieselbe Zahl je Fenster |
| `eedc_preis_aktuell_cent` | Day-Ahead-Börsenpreis der laufenden Stunde |
| `eedc_preis_tages_durchschnitt_cent` | Ø **aller** heutigen Preis-Stunden, ohne jeden Ausschluss — was der Strom heute im Mittel kostet. **Nicht** die Bezugsgröße der Günstig-Schwelle |
| `eedc_preis_optimierter_durchschnitt_cent` | Ø der heutigen Preise **ohne** die 3 teuersten Stunden — die Bezugsgröße der Schwelle |
| `eedc_preis_abstand_prozent` | Abstand des aktuellen Preises zu diesem Ø. **Negativ = billiger als der Ø**, positiv = teurer. Bezugsgröße ist der Betrag des Ø, damit das Vorzeichen auch bei negativen Börsenpreisen stimmt. |
| `eedc_preis_abstand_cent` | **Derselbe Abstand in ct/kWh** — die Größe, die sich auf den eigenen Endpreis übertragen lässt (s. u.). Negativ = billiger. |

> ⚠ **Zwei Durchschnitte, zwei Fragen — nicht verwechseln.** `eedc_preis_tages_durchschnitt_cent`
> sagt, was der Strom heute im Mittel kostet; `eedc_preis_optimierter_durchschnitt_cent` sagt,
> ab wann sich das Laden lohnt. Die Günstig-Schwelle und **beide** Abstands-Größen beziehen
> sich auf den **zweiten**, nie auf den ersten. Wer in einer Automation den Tagesschnitt
> meint, nimmt den ersten (rapahl-PN 2026-08-23).
>
> **Die vier letzten sind für eigene Preis-Regeln da** (v4.0.10, Wunsch aus der Tester-Runde): „nur entladen, wenn der Strom gerade teurer ist als der Tagesschnitt" ist damit eine Bedingung auf `eedc_preis_abstand_prozent > 0` — ohne Template und ohne dass eedc eine Lade-/Entlade-Strategie vorgibt.

> ### Prozent oder Cent? Beide, und sie sagen Verschiedenes
>
> Der **Prozentwert** misst gegen den Ø **dieses Tages**: −50 % heißt „halb so teuer wie der Tagesschnitt". Er ist über Tage hinweg vergleichbar, aber **nicht** auf deinen Endpreis übertragbar.
>
> Der **ct-Wert** ist es. Denn du zahlst nicht den Börsenpreis, sondern Börsenpreis **plus** feste Bestandteile (Netzentgelt, Abgaben, Marge). Dieser Aufschlag verschiebt Stundenpreis **und** Tagesmittel um denselben Betrag — die Differenz bleibt gleich, der Prozentwert nicht. An einem echten Tag (Ø 9,92 ct): die billigste Stunde liegt **−9,93 ct** unter dem Mittel, auf der Börsenkurve wie auf dem Endpreis; in Prozent sind das **−100,1 %** bzw. **−33,2 %**. Eine Prozentzahl, die für beide Welten dasselbe bedeutet, kann es folglich nicht geben.
>
> ⚠ **Was −100 % NICHT heißt:** nicht „billigste Stunde des Tages", sondern **„Preis = 0 ct"**. Der Wert kann unter −100 % fallen — jeder negative Börsenpreis tut das. Wer „ist das eine der besten Stunden?" fragt, nimmt `eedc_preis_rang` (1–5), nicht den Prozentwert.
>
> **Faustregel:** Schwellen für Automationen (`< -5` ct) und alles, was mit deinem Tarif zu tun hat → **ct**. Tagesübergreifende Vergleiche → **Prozent**. „Eine der günstigsten Stunden" → **Rang**.

**Das Rang-Profil als Attribut** trägt je Stunde fünf Angaben: `stunde`, `rang`, `preis_cent`, `unter_schwelle` und `abstand_cent`. `preis_cent`/`unter_schwelle` gibt es ab v4.0.10, `abstand_cent` seit dem ct-Sensor — vorher stand dort nur der Rang, und damit ließ sich in HA weder eine eigene Schwelle noch ein eigenes Zeitfenster auswerten.

> ### Morgen steht daneben, sobald es ihn gibt
>
> Die Day-Ahead-Auktion veröffentlicht die Preise des Folgetages gegen **13 Uhr**. Ab dann tragen
> die Attribute von `eedc_preis_rang` einen **zweiten Satz** für morgen — dieselbe Gestalt wie
> heute, damit eine Automation beide mit demselben Code liest:
>
> | Attribut | Bedeutung |
> |---|---|
> | `morgen_verfuegbar` | `true`/`false` — **immer vorhanden**. Vor der Auktion `false`; du musst also nicht auf ein fehlendes Attribut prüfen |
> | `datum_morgen` | Kalendertag, für den der Morgen-Satz gilt |
> | `rang_profil_morgen` | 24 Stunden in derselben Form wie `rang_profil` |
> | `guenstig_schwelle_cent_morgen` | die Günstig-Schwelle **des Folgetages** |
> | `optimierter_durchschnitt_cent_morgen` | dessen Bezugsgröße |
>
> ⚠ **Jeder Tag hat seine eigene Schwelle**, und das ist Absicht: Day-Ahead ist ein Tagesprodukt.
> Ein gemeinsamer Durchschnitt über 48 Stunden würde an einem teuren Tag *keine* günstige Stunde
> ausweisen und am billigen fast alle. Wer das Morgen-Profil auswertet, nimmt deshalb
> `guenstig_schwelle_cent_morgen` — nicht die von heute.
>
> **Warum `datum` und `datum_morgen` dabeistehen:** ein Profil ohne seinen Kalendertag ist nach
> Mitternacht nicht von einem stehengebliebenen zu unterscheiden. Eine Automation, die dann auf
> „morgen" plant, plant auf gestern.
>
> **Vor 13 Uhr fragt eedc gar nicht an.** Das ist keine Sparmaßnahme, sondern der Marktrhythmus:
> vor der Auktion gibt es die Zahlen nicht.

> **Eigene Kriterien:** Wer eine andere Schwelle bevorzugt, stellt den Prozentsatz auf der Export-Seite um — oder rechnet in HA per Template direkt auf den Attributen (`rang_profil` mit den Stundenpreisen, `optimierter_durchschnitt_cent`). eedc liefert bewusst nur die **Trigger-Werte**; die Lade-/Entlade-Strategie baut jeder selbst in seinen Automationen.

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
