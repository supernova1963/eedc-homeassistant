# Konzept: eedc → HA Sensor-Export-Architektur

> ## **Status (gemessen 2026-08-08): Rahmen verbindlich · Lücken-Klassen bewusst offen**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** Es hält fest, **was** eedc nach Home Assistant exportieren darf (exportiere, was HA nicht selbst hat) und **wie** die Sensoren strukturiert sind — die Regel hinter jedem Eintrag der [Sensor-Referenz](SENSOR-REFERENZ.md). Der Roadmap-Punkt **HA-Export-Sensor-Auswahl** ([#110](https://github.com/supernova1963/eedc-homeassistant/issues/110)) hängt daran.
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Offen:** **HX-4** (weitere Lücken-Klassen — Reihenfolge nach Nachfrage, kein Bau auf Vorrat) · **HX-5** (Pass-Through-Sensoren prunen, opportunistisch) · **HX-6** (hartcodierte `sw_version` im Device-Block) · **HX-7** (Sensor-Auswahl durch den Nutzer — **vertagt**, der `recorder.yaml`-Weg reicht dem Melder).
>
> ⚠ **Zirkulär bleibt zirkulär:** rohe Tages-/Stunden-kWh werden **nie** exportiert — sie stammen im Add-on-Modus selbst aus HA-LTS.


## Maßnahmen-Register (fortschreibbar — Stand 2026-07-28)

> Dieses Dokument ist ein **Rahmen**, kein Bau-Plan: es legt fest, *was* exportiert werden darf
> („exportiere, was HA nicht selbst hat") und *wie* es strukturiert ist. Die Lücken-Klassen sind
> **bewusst** offen — sie werden auf Bedarf gezogen, nicht auf Vorrat.

| # | Maßnahme | Status | Beleg / Rest |
| --- | --- | --- | --- |
| **HX-1** | Auswahl-Prinzip + Struktur-Regeln (Sensor vs. Attribut · Granularität · `eedc_`-Präfix · Device-Gruppierung · Quellen-Regel · zwei Schienen aus einem Chokepoint) | ✅ verbindlich | `api/routes/ha_export.py::calculate_anlage_sensors()` |
| **HX-2** | HA-Device-Gruppierung vorhanden? | ✅ **geprüft 2026-06-09** — ist da | `services/mqtt_client.py:177-184`; Attribut-Hook ebenfalls da |
| **HX-3** | **#150 Slice A/B** (PV-Prognose Rest-heute + Tag+1/2/3 · „Speicher voll um" · Börsenpreis-Rang) | ✅ Issue #150 geschlossen 2026-07-25 | Referenz-Muster für alle weiteren Klassen |
| **HX-4** | Lücken-Klassen (je ein kleiner Slice, **auf Bedarf**): Performance Ratio (Tag) · Autarkie/EV-Quote (heute/30 T) · Korrektur-/Lernfaktor · CO₂-Amortisations-Status · Speicher-η/Zyklen rollierend | ⬜ offen, **absichtlich** | Reihenfolge nach Tester-/Community-Nachfrage. Beim ersten Zugriff: **rollierende Fenster einheitlich definieren** (heute/30 T) |
| **HX-5** | Pass-Through-/zirkuläre Bestands-Sensoren prunen | ⬜ opportunistisch beim Touch | kein Big-Bang |
| **HX-6** | **Nebenbefund:** `sw_version` im Device-Block hartcodiert, `_build_device_info` ungenutzt | ✅ **erledigt — am 2026-08-08 gegen den Code geprüft** | `services/mqtt_client.py:181` setzt `"sw_version": APP_VERSION`, der tote Helper ist entfernt (CHANGELOG „MQTT-Discovery: `sw_version` zeigt die echte eedc-Version"). ⚠ Die Zeile stand seit 2026-06-08 als offen und beschrieb einen Zustand, den es nicht mehr gab — **ein Konzept, das niemand gegen den Code hält, erfindet Arbeit** (Fund N-184) |
| **HX-7** | HA-Export-**Sensor-Auswahl** durch den Nutzer | ⏸ vertagt — `recorder.yaml`-Workaround reicht dem Melder | Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) („HA-Export-Sensor-Auswahl") |

**Zirkulär bleibt zirkulär:** rohe Tages-/Stunden-kWh werden **nie** exportiert — sie stammen im
Add-on-Modus selbst aus HA-LTS (SoT seit v3.31.0), ein Rück-Push wäre ein Kreis.

---

> **Status:** Design-Rahmen (2026-06-08). **#150** (Prognose + Börsenpreis-Trigger) ist der **erste konkrete Slice** unter diesem Rahmen (ausgeliefert). Weitere Analytik-Klassen kommen **inkrementell / auf Bedarf** dazu — kein Big-Bang.
> Verwandt: `services/ha_sensors_export.py` (Sensor-Definitionen), `api/routes/ha_export.py:calculate_anlage_sensors()` (Berechnung, zentraler Chokepoint), `services/ha_mqtt_sync.py` (MQTT-Auslieferung), `core/berechnungen/` (SoT-Rechenlogik). SoT-Überblick: `UEBERBLICK-20260606.md`.

## Problem / Anlass
Der heutige eedc→HA-Export liefert vor allem **Monats-/kumulativ-Kennzahlen** und teils nur **durchgeleitete** Werte (Pass-Through eines HA-Sensors ohne eedc-Mehrwert). Die eigentliche eedc-Rechenleistung auf **Tages-/aktueller/Vorausschau-Ebene** (Energieprofil + Berechnungs-Layer) ist **nicht** exportiert. Gleichzeitig droht bei „einfach mehr Sensoren" Wildwuchs. Dieser Rahmen legt fest, **was** exportiert wird und **wie** es strukturiert ist.

## Auswahl-Prinzip — was wird exportiert?
Leitsatz: **Exportiere, was HA nicht selbst hat.**

| Klasse | Regel | Beispiele |
|---|---|---|
| ✅ **Export-würdig** | eedc-eigene Rechenleistung, die HA nicht rekonstruieren kann | Prognose, Börsenpreis-Rang, Performance Ratio, Autarkie-/EV-Verlauf, Korrekturfaktor/Lernfaktor, „Speicher voll um"/SoC-Prognose, ROI-/CO₂-Amortisations-**Status** |
| 🚫 **Zirkulär — NICHT exportieren** | rohe Tages-/Stunden-kWh, die im Add-on-Modus **selbst aus HA-LTS** stammen (SoT seit v3.31.0) → Rück-Push wäre ein Kreis | Tages-PV-kWh, Tages-Verbrauch-kWh, Stunden-Rohwerte |
| 🚫 **Pass-Through — NICHT (neu) exportieren, ggf. prunen** | bloßes Weiterreichen eines HA-Sensorwerts ohne Berechnung | durchgeleitete Zählerstände |

Konsequenz: Das Prinzip rechtfertigt auch das **Ausmisten** bestehender Pass-Through-/zirkulärer Export-Sensoren (opportunistisch beim Touch, nicht als Big-Bang).

## Struktur-Regeln
1. **Sensor vs. Attribut** (HA-Nuance — Attribute landen NICHT in den Long-Term-Statistics):
   - **Wert wird historisiert/geplottet/numerisch automatisiert → eigener Sensor** mit `device_class`/`state_class`.
   - **Vorausschau-Profil / Begleitinfo → Attribut** (Forecast.Solar-/Solcast-Stil: Stunden-Array als Attribut, nicht 24 Topics).
2. **Granularität:** **aktuelle/rollierende Kennzahl** als Sensor (z. B. „Performance Ratio heute", „Autarkie 30 T"); **historische Tagesreihen NICHT** als Sensoren (dafür HA-LTS / eedc-eigene Auswertung).
3. **Namen:** einheitliches Präfix `eedc_…`, Kategorie im Namen erkennbar.
4. **Gruppierung:** alle eedc-Sensoren einer Anlage unter **einem HA-Device** (MQTT-Discovery-`device`-Block) — statt loser Einzel-Entities. *(Vorhandensein prüfen; falls nicht da, größter sichtbarer Struktur-Gewinn.)*
5. **Quellen-Regel Prognose:** nur eedc-eigene Werte (OpenMeteo+Lernfaktor); Solcast/SFML nicht re-exportieren (in HA via eigene Integration vorhanden).
6. **Zwei Schienen parallel:** HA-Sensor (Add-on) + MQTT-Topic, beide aus demselben Chokepoint `calculate_anlage_sensors()` — kein Per-Schienen-Duplikat.

## Backlog — export-würdige Analytik-Klassen (inkrementell)
Status: ✅ schon (Monats-Export) · 🟢 #150 · ❌ Lücke (Kandidat) · 🚫 nicht exportieren.

| Wert / Klasse | SoT (`core/berechnungen/` bzw. Energieprofil) | Status |
|---|---|---|
| PV-Prognose Rest-heute + Tag+1/2/3 (+ Stundenprofil) | prognose_adapter / prognose_router | 🟢 #150 A |
| „Speicher voll um" / SoC-Prognose (aktueller SoC) | energie_profil/views (SoC-Sim) | 🟢 #150 A |
| Börsenpreis-Rang + günstige-Stunden-Anzahl (+ Profil) | NEU + boersenpreis_cent | 🟢 #150 B |
| **Performance Ratio (Tag/aktuell, GTI-basiert)** | energie_profil (PR seit v3.20) | ❌ Lücke |
| **Autarkie / Eigenverbrauchsquote (heute / rollierend 30 T)** | `verbrauch.py` `berechne_verbrauchs_kennzahlen` | ❌ Lücke (heute nur Monat) |
| **Korrekturfaktor / Lernfaktor (aktueller Stand)** | Korrekturprofil/Lernfaktor | ❌ Lücke |
| **CO₂-Amortisations-Status** („ab wann klimapositiv", Fortschritt) | `co2_amortisation.py` | ❌ Lücke |
| **Speicher: Wirkungsgrad-Verlauf / Zyklen (rollierend)** | `speicher.py` / η-Tracking | ❌ Lücke (heute nur Monat) |
| Autarkie/EV/ROI/CO₂/WP-COP/Speicher-Zyklen **(Monat, kumulativ)** | diverse | ✅ schon |
| Rohe Tages-/Stunden-kWh | Energieprofil (aus HA-LTS) | 🚫 zirkulär |

Reihenfolge der Lücken-Umsetzung **nach Bedarf/Anfrage**, nicht auf Vorrat. Jede Klasse ist ein eigener kleiner Slice mit eigener Changelog-Zeile.

## Umsetzungs-Disziplin
- **#150 zuerst** (Prognose + Preis) — setzt die Struktur-Regeln erstmals um (inkl. Device-Gruppierung-Check) und ist damit das Referenz-Muster.
- Weitere Klassen **inkrementell**, getrieben von Community-/Tester-Bedarf — kein „alles exportieren".
- Bestands-Sensoren: Pass-Through/zirkuläre **opportunistisch prunen**, neue Werte der Konvention folgen.
- **Feature-Titel nicht aufblähen** — der Rahmen lebt hier, nicht im Issue-Titel. Kein Profi-/Experten-Schalter.

## Offene Entscheidungen
- ~~HA-Device-Gruppierung: schon vorhanden?~~ ✅ **Vorhanden** (Koordinator-Verifikation 2026-06-09): `mqtt_client.py:177-184` setzt `payload["device"]`; Anlage-Sensoren → Device `eedc_anlage_{id}`, Investitions-Sensoren → `eedc_inv_{id}`. Auch der Attribut-Hook (`SensorValue.zusatz_attribute` → `{state_topic}/attributes` + `json_attributes_topic`) steht schon. #150 baut keine Struktur, sondern nutzt sie. *(Nebenbefund: `sw_version` hartcodiert/driftend, `_build_device_info` ungenutzt — eigener Aufräum-Anlass.)*
- Rollierende Fenster (30 T / heute) — einheitliche Definition, sobald die erste Lücken-Klasse drankommt.
