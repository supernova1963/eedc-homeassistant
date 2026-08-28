# Regel — Wallbox & E-Auto: wer misst was

> ## **Status (gemessen 2026-08-28): gebaut. Die Domäne hat keinen offenen Bau-Strang mehr.**
>
> **Was hier steht:** wie eedc Ladeenergie zwischen **Wallbox** (Infrastruktur, misst den
> Stromfluss) und **E-Auto** (Fahrzeug, misst Nutzung) aufteilt, welche Quelle bei beidem gewinnt
> und was daraus in Geld und CO₂ wird. **22 Stellen im Code zitieren dieses Dokument**, meist nach
> Entscheidungsnummer — die Nummerierung bleibt deshalb stehen.
>
> **Gebaut und in Betrieb:** kanonische Heimladungs-Quelle samt Migration (Phase 2a) · PHEV-Anteil
> elektrisch/fossil ([#331](https://github.com/supernova1963/eedc-homeassistant/issues/331),
> v4.0.11) · abgeleiteter PV-Anteil der Heimladung statt Abfrage (Phase 5, v4.0.11) ·
> Achse-2-Magnitude-Drift geschlossen ([#356](https://github.com/supernova1963/eedc-homeassistant/issues/356)) ·
> die beiden Daten-Checker-Fehlalarme A + B.
>
> ⛔ **Verworfen am 2026-08-28 (Entscheid Gernot): die Aufschlüsselung je Fahrzeug** — weder
> eigene `ladung_heim_*`-Felder mit evcc-Vehicle-Topics (vormals „Phase 2b") noch die Zerlegung
> der Wallbox-Summe auf einzelne Autos (vormals „Phase 3"). Der Trigger dafür ist seit Mai 2026
> nicht eingetreten, und die Pool-Aggregation deckt jedes gemeldete Setup. **Kein Rückstand,
> sondern eine Entscheidung** — Einzelheiten und die damit gegenstandslosen offenen Fragen im
> [archivierten Bau-Vertrag](archive/KONZEPT-WALLBOX-EAUTO-BAUVERTRAG.md).
>
> **Zwei Dinge, die neben diesem Dokument entstanden sind und hier hingehören:** Der Dienstwagen
> **kostet**, statt zu verdienen (v4.0.5, `core/berechnungen/dienstliche_ladekosten.py`) — die
> vierte Stelle, an der E-Auto-Ladung in Geld umgerechnet wird, im ursprünglichen Entwurf nicht
> vorgesehen. Und die Monatszeile wird genau einmal aufbereitet (ADR-002/P10): Read-Sites lesen
> sie aus `services/monats_fakten.py`, statt `InvestitionMonatsdaten` selbst zu falten.
>
> ⚠ **Sprachliche Altlast:** Wo unten „Wallbox-Dashboard" steht, ist die Wallbox-Fläche des
> **Komponenten-Hubs** gemeint (`frontend/src/v4/WallboxHubBloecke.tsx`); die Backend-Route heißt
> weiterhin `api/routes/investitionen/dashboards.py`.

---

## Motivation

Die Feldzuordnung zwischen Wallbox und E-Auto ist **mehrdeutig**: `ladung_kwh`/`ladung_pv_kwh`/`ladung_netz_kwh` können auf beiden Investitionstypen liegen, und das Wallbox-Dashboard aggregiert sie über einen Pool, der raten muss, welche Quelle die Wahrheit ist. Diese Mehrdeutigkeit ist die eigentliche Schuld, die das Konzept abträgt — nicht (nur) ein fehlendes Multi-Fahrzeug-Feature.

**Auch das 1-Wallbox-+-1-E-Auto-Setup bricht** — entgegen einer früheren Annahme dieses Konzepts: #260 (NongJoWo) und #262 (junky84) sind beide 1+1-Setups, in denen der Pool inkonsistente Werte lieferte (PV-Anteil > 100 %). Die Mehrdeutigkeit wird in komplexeren Szenarien nur *sichtbarer*:

- Privatauto + Firmenwagen an derselben Wallbox (steuerlich trennbar)
- Mehrere Wallboxen (Garage + Carport)
- Gast-Ladungen ohne zugeordnetes E-Auto
- RFID-basierte Zuordnung (evcc, SMA eCharger, Wattpilot)

## Kernprinzip: Jeder speichert was er misst

### Wallbox = Infrastruktur (misst den Stromfluss)

```
verbrauch_daten:
  ladung_kwh          ← Zählerstand-Differenz (Gesamt am Ladepunkt)
  ladung_pv_kwh       ← davon PV (evcc/Sensor)
  ladung_netz_kwh     ← davon Netz (evcc/Sensor oder abgeleitet)
  ladevorgaenge       ← Zähler (alle Sessions am Ladepunkt)
```

### E-Auto = Fahrzeug (misst Nutzung + eigene Heimladung)

```
verbrauch_daten:
  km_gefahren          ← Tacho
  verbrauch_kwh        ← Gesamtverbrauch
  ladung_heim_kwh      ← Heimladung dieses Autos (NEU, per Vehicle-Sensor)
  ladung_heim_pv_kwh   ← davon PV (NEU, per Vehicle-Sensor)
  ladung_extern_kwh    ← Fremdladung
  ladung_extern_euro   ← Fremdladung Kosten
  v2h_entladung_kwh    ← Vehicle-to-Home
```

### Zuordnung über Sensor-Mapping, nicht über DB-Modell

Die RFID-Intelligenz bleibt bei evcc/Wallbox. EEDC konsumiert die
bereits aufgeschlüsselten Daten über die passenden Sensor-Topics:

```
Wallbox "Garage" (Loadpoint-Perspektive):
├── ladung_kwh      → evcc/loadpoints/1/chargeTotalImport
├── ladung_pv_kwh   → evcc/loadpoints/1/pvCharged
└── ladevorgaenge   → evcc/loadpoints/1/sessions

E-Auto "BMW i4" (Vehicle-Perspektive):
├── ladung_heim_kwh    → evcc/vehicles/BMW/chargeTotalImport
├── ladung_heim_pv_kwh → evcc/vehicles/BMW/pvCharged
└── ladevorgaenge      → evcc/vehicles/BMW/sessions

E-Auto "Firmenwagen" (Vehicle-Perspektive):
├── ladung_heim_kwh    → evcc/vehicles/Firma/chargeTotalImport
├── ladung_heim_pv_kwh → evcc/vehicles/Firma/pvCharged
└── ladevorgaenge      → evcc/vehicles/Firma/sessions
```

## Zwei Perspektiven, gleiche Realität

evcc liefert dieselben kWh aus zwei Blickwinkeln:

```
PRO LOADPOINT (= Wallbox)               PRO VEHICLE (= E-Auto)
evcc/loadpoints/1/pvCharged → 732 kWh   evcc/vehicles/BMW/pvCharged   → 520 kWh
                                         evcc/vehicles/Firma/pvCharged → 212 kWh
                                                                        ─────────
                                                                  Σ     732 kWh ✓
```

### Konsistenzregel

| Prüfung | Formel |
|---------|--------|
| Wallbox-Gesamt ≥ Σ E-Autos Heim | `WB.ladung_kwh ≥ Σ EAuto.ladung_heim_kwh` |
| PV-Gesamt ≥ Σ PV pro Auto | `WB.ladung_pv_kwh ≥ Σ EAuto.ladung_heim_pv_kwh` |

`≥` statt `=` weil Gast-Ladungen keinem E-Auto zugeordnet sein können.

## Was die Flächen zeigen

> ⚠ **2026-08-08: Die Sichten heißen seit v4.0.0 anders.** „Wallbox-Dashboard" ist heute die
> **Wallbox-Fläche des Komponenten-Hubs** (`frontend/src/v4/WallboxHubBloecke.tsx`),
> „E-Auto-Dashboard" die **E-Auto-Fläche** (`v4/EAutoHubBloecke.tsx`). Die Backend-Route heißt
> weiterhin `api/routes/investitionen/dashboards.py`. Die Skizzen darunter beschreiben den
> **Inhalt**, nicht das heutige Layout — wer sie umsetzt, tut das im Hub und nach Regel 0a.

### Wallbox-Dashboard

```
SMA eCharger 22 (11 kW) · 34 Monate Daten
┌────────────────┬───────────────┬───────────────────┬──────────────┐
│ Heimladung     │ PV-Anteil     │ Ersparnis vs. Ext │ Ladevorgänge │
│ 1.200 kWh      │ 61%           │ -583 €            │ 48           │
└────────────────┴───────────────┴───────────────────┴──────────────┘
Aufschlüsselung (wenn Vehicle-Sensoren vorhanden):
  BMW i4:       880 kWh (59% PV) · 35 Vorgänge
  Firmenwagen:  320 kWh (66% PV) · 13 Vorgänge
```

### E-Auto-Dashboard

```
BMW i4
┌────────────┬──────────────┬──────────────┬──────────────┐
│ km         │ Heimladung   │ Extern       │ vs. Benzin   │
│ 12.400     │ 880 kWh      │ 340 kWh/170€ │ +1.240 €     │
└────────────┴──────────────┴──────────────┴──────────────┘
```

## Abgrenzung: Was NICHT Teil dieses Konzepts ist

- **RFID-Karten als eigene Entität** — Zuordnung bleibt bei evcc
- **Externe Ladekarten** (EnBW, ADAC etc.) — separates Thema, aktuell `ladung_extern_*` am E-Auto
- **Session-Level-Tracking** — EEDC bleibt bei Monatsaggregaten
- **Wallbox↔E-Auto Zuordnungs-UI** — nicht nötig, Sensor-Mapping reicht

## Was gebaut ist — und was bewusst nicht

**Gebaut und in Betrieb:** Die Heimladungs-Trias (`ladung_kwh` / `ladung_pv_kwh` /
`ladung_netz_kwh`) hat eine kanonische Quelle — die **Wallbox**, wo es eine gibt, sonst das
E-Auto (Steckerlader-Fall). Aufgelöst wird sie an genau einer Stelle
(`services/eauto_wirtschaftlichkeit.py::get_emob_heimladung_canonical`), die Bestandsdaten hat
eine Migration geradegezogen (`services/migrations/migrate_emob_canonical_source.py`). Dazu:
**PHEV-Anteile** (#331, `core/berechnungen/phev_anteil.py`), der **abgeleitete PV-Anteil** der
Heimladung (`services/emob_ladeanteil.py`, `core/berechnungen/pv_anteil_ladung.py`) und der
geschlossene **Achse-2-Drift** (#356).

⛔ **Bewusst nicht gebaut — verworfen am 2026-08-28 (Entscheid Gernot):** die Aufschlüsselung der
Heimladung **je Fahrzeug**. Weder eigene `ladung_heim_*`-Felder am E-Auto mit evcc-Vehicle-Topics
(vormals „Phase 2b") noch die Zerlegung der Wallbox-Summe auf einzelne Autos (vormals „Phase 3").
Ihr Trigger — „wenn Vehicle-Sensoren nachgefragt werden" — ist seit Mai 2026 nicht eingetreten,
und die Pool-Aggregation deckt jedes gemeldete Setup: Wer zwei Autos an einer Wallbox lädt, sieht
die Summe, nicht die Aufteilung. **Das ist eine Entscheidung, kein Rückstand.** Der Bauplan dazu
liegt im [archivierten Bau-Vertrag](archive/KONZEPT-WALLBOX-EAUTO-BAUVERTRAG.md).

**Kein Breaking Change, unverändert gültig:** Wer ohne evcc/RFID arbeitet, merkt von alledem
nichts — die manuelle Eingabe funktioniert wie am ersten Tag, und ein 1:1-Setup (eine Wallbox,
ein Auto) rechnet identisch.

---

## Phase 2a — die Entscheidungen dahinter (2026-06-02, gebaut)

> Der strukturelle Ausweg aus dem Read-seitigen Heuristik-Flickwerk — gebaut in einer eigenen Session — echtes Release mit Daten-Migration, kein Read-Pfad-Hotfix (Tester-Zyklus, Pre-Release-Daten-Checker-Scan, DB-Backup-Hinweis).

### Leitprinzip
An die Stelle der **datenabhängigen** Laufzeit-Heuristik (`use_wb_pool` hieß einmal „größere Heimladung gewinnt" und kippte bei Streudaten) ist eine **strukturelle, deterministische** Quellen-Regel ersetzt. Die km-anteilige *Attribution* (`attribute_emob_pool_by_km`, `attribute_month_share`) bleibt unverändert — nur das *Raten der Quelle* fällt weg.

### Getroffene Entscheidungen
1. **Fallback ja.** Nutzer **ohne** Wallbox-Investition (inkl. **Steckerlader**/Schuko — sehr häufig!) behalten die E-Auto-Trias als kanonische Quelle. Kein Breaking Change. Regel: *Wallbox-Investition vorhanden + hat Heimladung → Wallbox ist Quelle; sonst → E-Auto.* Strukturell (existiert eine Wallbox?), nicht magnitudenabhängig → kippt nicht.
2. **Migration löst automatisch auf, „höherer Wert gewinnt".** Wo historisch BEIDE Seiten Heimladung tragen, gewinnt pro aktivem Monat der **höhere** Heimladungs-Wert als überlebender kanonischer Wert (in die Wallbox geschrieben, E-Auto-Trias geräumt). Nur Fälle, die diese Regel **nicht** sauber auflösen kann (z. B. Total auf der einen, PV-Split nur auf der anderen Seite → keine konsistente Trias bildbar), bleiben stehen und tauchen im Daten-Checker (`_check_emob_pool_pflege`) auf. Ziel: möglichst wenig manuelle Fälle, kein „großer Heiler-Knopf" für das Unauflösbare.
3. **Nur aktive Monate.** Migration und Auflösung respektieren Anschaffungs-/Stilllegungsdatum (konsistent mit der Aktiv-Filter-Invariante).
4. **Multi-Wallbox:** Liegen mehrere Wallboxen vor, ist jede ein eigener Ladepunkt (Garage + Carport); die Heimladung gesamt = **Summe aller Wallbox-IMD** (entschieden 2026-06-04, physikalisch korrekt, keine Unterzählung). „Größtes Ladevolumen" greift damit nur als Wallbox-vs-E-Auto-Quellenwahl, nicht als Auswahl *einer* Wallbox; für den 0/1-Wallbox-Fall ist das identisch.

## Bekannte Schwächen — Phase-2a-Fehlalarme bei Wallbox+E-Auto (Live-Check 2026-06-04)

> **✅ Behoben und ausgeliefert:** Beide Fehlalarme A+B sind gefixt.
> A — `_check_emob_pool_pflege` liest die E-Auto-Heimladung jetzt nur aus dem
> expliziten `ladung_kwh` (kein `verbrauch_kwh`-Fahrverbrauch-Fallback mehr).
> B — `_check_energieprofil_abdeckung` überspringt den E-Auto-kWh-Zähler-Bedarf,
> wenn eine aktive Wallbox mit gemapptem `ladung_kwh`-Zähler die Ladeenergie
> deckt. Tests: `test_daten_checker_wallbox_schwaeche_ab.py`. Die folgenden
> Abschnitte dokumentieren den Befund (historisch).

### A) `verbrauch_kwh` überladen → False-Positive-Pflege-Konflikt

**Symptom:** Bei einer Anlage mit Wallbox (= kanonische Quelle) **und** einem
E-Auto, das sein Feld „Verbrauch (kWh)" (Fahrverbrauch, für kWh/100 km) pflegt,
feuert der Daten-Checker `_check_emob_pool_pflege` einen **falschen** Pflege-
Konflikt — und der kanonische Helfer zählt das E-Auto als „Heimladung tragend".

**Ursache:** `get_eauto_ladung_kwh(data)` = `ladung_kwh or verbrauch_kwh`. Der
`verbrauch_kwh`-Zweig ist ein **Legacy-Fallback** für Alt-E-Auto-Daten, in denen
die Heimladung historisch in `verbrauch_kwh` lag (vor den `ladung_pv/netz`-
Feldern). Heute ist `verbrauch_kwh` am E-Auto aber der **Fahrverbrauch** — das
Feld ist also doppelt belegt (Fahrverbrauch ∧ Legacy-Heimladung). Hat das E-Auto
kein `ladung_kwh`, wird sein Fahrverbrauch als Heimladung gelesen.

**Wirkung:** Anzeige bleibt korrekt (die Wallbox gewinnt strukturell), aber der
Pflege-Konflikt-Hinweis ist ein False Positive. Anlass: Gernots Smart #1 —
deshalb steht „Verbrauch" dort jetzt bewusst auf Manuell/leer (kWh/100 km
entfällt). Real auch: evcc liefert für viele Fahrzeuge ohnehin keinen echten
kumulativen Fahr-Verbrauchszähler (nur Lade-Energie + Momentan-Durchschnitt in W).

**Kandidat-Fix (Variante offen → eher ein eigenes Issue):**
Den `verbrauch_kwh`→Heimladung-Fallback nur greifen lassen, wenn **keine
Wallbox** als kanonische Quelle existiert (bzw. im Pflege-Check die Heimladung
des E-Autos nur aus den expliziten `ladung_*`-Feldern bilden, nicht aus
`verbrauch_kwh`). Risiko: echte Legacy-Daten ohne `ladung_*` dürfen nicht
verloren gehen → sorgfältig abgrenzen. Post-Phase-2a, kein Release-Blocker.

### B) Zähler-Abdeckungs-Check verlangt E-Auto-Zähler trotz Wallbox-Deckung

**Symptom:** Räumt man (korrekt) alle Heimladungs-/Verbrauchs-Sensoren vom E-Auto
(weil die Wallbox die kanonische Quelle ist), meldet der Daten-Checker
»Energieprofil – Zähler-Abdeckung«: „Komponente ohne vollständige kWh-Zähler-
Abdeckung … Smart #1 (e-auto): verbrauch_kwh oder ladung_kwh".

**Ursache:** Der Abdeckungs-Check prüft jede Investition **einzeln** und weiß
nicht, dass die Lade-Energie des E-Autos bereits über den **Wallbox-Zähler**
(`ladung_kwh` → Energiefluss-Kategorie „ladung_wallbox") erfasst ist. Ein
zusätzlicher E-Auto-Zähler würde dieselbe Energie **doppelt zählen**.

**Wirkung:** Reiner Fehlalarm in der „Wallbox = Zähler, E-Auto = Fahrzeug"-
Topologie. Die E-Auto-Linie im Tages-Energieprofil/Heatmap bleibt leer (Energie
steckt korrekt in der Wallbox-Linie); Autarkie, Gesamtverbrauch und Monats-
Auswertungen sind unberührt. **Nicht** auf »Beheben« klicken — das würde Doppel-
zählung + Pflege-Konflikt zurückbringen.

**Kandidat-Fix:** Der Zähler-Abdeckungs-Check soll den kWh-Zähler-Bedarf eines
E-Autos **überspringen, wenn eine Wallbox mit kWh-Zähler** in derselben Anlage
existiert (analog zur strukturellen Quellen-Regel). Gleiche Issue-Familie wie A.

## Achse-2-Magnitude-Drift — vermessen und gebaut ([#356](https://github.com/supernova1963/eedc-homeassistant/issues/356), geschlossen 2026-08-08)

> **Status (2026-08-28): vermessen, beide Fix-Richtungen gebaut, Alt-Tage-Erkennung gebaut — nichts offen.** Siehe den Abschnitt „✅ Vermessen und gebaut" am Ende. Der Text darunter beschreibt den Stand vom 2026-06-29 und bleibt als Herkunftsbeleg wörtlich stehen; zwei seiner drei Hypothesen sind widerlegt. Aufgetaucht beim Live-Gegencheck der v3.45.9-Achse-2-Diagnose (`GET /api/energie-profil/{id}/achse2-drift`) an Gernots Anlage. SoT für die Weiterarbeit ist dieser Abschnitt + Memory `project_achse2_magnitude_drift`.
>
> ⚠ **Nachtrag 2026-08-08: Dieser Abschnitt hat ein Issue — [#356](https://github.com/supernova1963/eedc-homeassistant/issues/356)** (seit 30.07., offen). Bis dahin stand die Lücke nur hier und im Memory; wer nur die Issue-Liste las, hat sie nicht gesehen. Die Linie dort ist dieselbe wie hier: **Diagnose zuerst, Korrektur alter Tage nur über den Reparatur-Knopf, nie als Start-Migration.**

### Befund (Daten, Gernots Anlage 1, v3.45.9)

Die Achse-2-Invariante (`pruefe_tep_komponenten_intern_konsistenz`) meldet für die Kategorie **„Wallbox+E-Auto"** eine **gegenläufige ~2×-Drift** zwischen den beiden gespeicherten Stunden-Repräsentationen:

| Tag | Zählerpfad (`wallbox_kw`-Spalte) | Leistungspfad (Σ `komponenten[wallbox_*]+[eauto_*]`) | Faktor |
|-----|----------------------------------|------------------------------------------------------|--------|
| 2026-06-22 | **+7,00** kWh | **−14,00** kWh | −2,00× |
| 2026-06-24 | **+3,00** kWh | **−6,43** kWh | −2,14× |

Setup: Wallbox (SMA eCharger, inv 2, `parent=None`) + E-Auto (Smart #1, inv 1, `parent=None`) — **getrennt, unverlinkt**. Genau die im Kopf dieses Dokuments (Update 2026-06-03) notierte „Verbleibende Lücke": *Wallbox + E-Auto mit getrennten Sensoren, unverlinkt → Live-/Aggregations-Pfad poolen mit divergenten Heuristiken.*

### Warum das eine eigene Lücke ist (Abgrenzung zu Phase 2a)

- **Phase 2a (v3.36.0)** kanonisierte die **Monats-Read-Sites** (Wallbox/E-Auto-Dashboard, Cockpit, jahresbericht, ha_export) + die einmalige Migration auf die strukturelle Regel „Wallbox vorhanden → Wallbox ist Quelle". Der **tägliche Energieprofil-/Tagesverlauf-Pfad** (die `komponenten`-JSON-**Leistungsserien** aus `live_tagesverlauf_service`/`live_komponenten_builder`, gespeichert in `TagesEnergieProfil.komponenten`) war **nicht** Teil davon.
- **Nicht heilbar durch Re-Aggregation:** 2026-06-22 wurde am 2026-06-29 manuell neu aggregiert → Drift **unverändert** (+7 / −14). Also **kein** Stale-Mapping-Artefakt, sondern laufendes Verhalten des Tages-Leistungspfads mit aktuellem Mapping.
- **Kein aktuelles Sensor-Doppelmapping:** `_check_emob_sensor_doppelmapping` ist auf der Anlage **grün** (Gernot hat `evcc_pv_charged` vom E-Auto entfernt; E-Auto trägt nur noch `km_gefahren`). Die Drift besteht **trotzdem** → sie kommt **nicht** aus einem doppelt gemappten Sensor, sondern aus der Pfad-internen Serien-Bildung.
- **Monats-Pool separat:** `_check_emob_pool_pflege` warnt weiterhin (Monats-Altdaten, EA = WB identisch in 01/2026, 12/2025, 08/2025) — das ist der **Monats**-Pflege-Konflikt, nicht die Tages-Drift.

### Diagnose-only — keine falschen Anzeige-Werte

Die **angezeigten** Werte (Kacheln, Bilanz, Charts, Tages-/Monats-Auswertung) stammen aus dem **Zählerpfad** (`*_kw`-Spalten / `komponenten_kwh` Boundary) und sind **korrekt** (+7). Nur das interne `komponenten`-JSON (Leistungspfad, butterfly-signiert) driftet. Symptom ist die dauerhafte Achse-2-Log-Warnung, jetzt auch im Diagnose-Endpoint sichtbar. Kein Anwender-sichtbarer Wert ist falsch.

### ✅ Vermessen und gebaut 2026-08-08 — beide Fix-Richtungen umgesetzt

> **Der Text oben bleibt wörtlich stehen** (Herkunftsbeleg, N-164-Muster). Was er als Hypothesen
> führte, ist jetzt gemessen — **eine bestätigt, zwei widerlegt.**

**Die Vermessung** (Endpunkt `achse2-drift`, Anlage 1, 2026-01-01…08-07): **48 Tage mit Drift**.
Die Kategorie zerfällt in **zwei** Ursachen, nicht in eine:

| Klasse | Fälle | Faktor Leistung/Zähler | Ursache |
| --- | --- | --- | --- |
| Vorzeichen-Konvention | 19 (WB) + 15 (Batt) | **−1,01** (Median) | Prüferfehler, s. u. |
| Doppelzählung Wallbox **+** E-Auto | 10 (WB) | ≈ **−2** | echter Fehler im Leistungspfad |

**Die „~2×-Drift" war überwiegend gar keine Magnitude-Drift.** In 39 von 39 Wallbox-Fällen lag der
Leistungspfad „unter", in **keinem** darüber — die Invariante verglich die **positive**
`wallbox_kw`-Spalte gegen das **negativ** butterfly-signierte JSON. Für Senken-Kategorien konnte
sie damit **nie** grün werden. April/Mai sind nicht grün, sondern von der Skip-Semantik
übersprungen (kein Komponenten-Key) — es gibt kein Gegenbeispiel.

**Widerlegt — Hypothese 1 (Wallbox-Selbst-Verdopplung):** `baue_investitions_serien` hängt an jede
Serie **genau eine** Entity (`serie_entities[key] = [live["leistung_w"]]`); `ladung_pv_kwh` geht
nicht in die Kurve ein.

**Widerlegt — Hypothese 2 in ihrer Begründung, bestätigt in ihrer Wirkung:** „E-Auto hat keinen
Lade-Sensor mehr" trifft nicht zu. Das Fahrzeug trägt `leistung_w` = `sensor.smart_ladeleistung`
(Datenquellen-Fläche, gemessen). Es ist keine Phantom-Serie, sondern eine **zweite echte Messung
desselben Stromflusses**: die HA-Historie beider Sensoren zeigt am 2026-08-06 Ladung in genau
denselben fünf Stunden (893/779 W · 8237/8773 W · 4239/4406 W · 979/920 W · 2067/2445 W).
**Keine Fremdladung** — das Auto lädt in keiner Stunde, in der die Wallbox nicht liefert.

**Warum die Beträge trotzdem auseinanderliegen:** die Wallbox hat einen kWh-Zähler, ihre Kurve wird
per `counter_overlay` auf Zähler-Deltas normiert (glatte Werte: −1,00 · −4,00 · −4,00 …); das
Fahrzeug hat keinen, seine bleibt W-integriert (−0,78 · −8,77 · −4,41 …). **Zwei
Bildungsvorschriften in einem JSON** — deshalb 12,00 gegen 17,32 kWh statt exakt 2×.

**⚠ Korrektur an „Diagnose-only — keine falschen Anzeige-Werte" (Abschnitt oben):** das gilt für
Kacheln, Bilanz und Monats-Auswertung (Zählerpfad) — **nicht** für den Tagesverlauf-Chart.
`GET /energie-profil/{id}/stunden` liefert für den 2026-08-06 **beide** Serien mit Label aus
(`SMA eCharger 22` **und** `Smart #1`); der Chart zeichnet denselben Ladevorgang zweimal, in Summe
**29,32 statt 12,00 kWh**.

**Gebaut — beide Punkte der Fix-Richtung oben:**

1. **Strukturelle Quellen-Regel auf dem Tages-Leistungspfad** (`live_sensor_config.py::baue_investitions_serien`,
   SoT für Live **und** Backfill): existiert eine Wallbox-Serie, entfällt jede E-Auto-Serie —
   dieselbe Regel wie monatlich in `get_emob_heimladung_canonical`, deterministisch statt
   magnitudenabhängig. Die beiden Bestandsregeln (Parent gesetzt · geteilte Entity) deckten nur
   Sonderfälle ab. **Abgrenzung:** ohne Wallbox behält das Fahrzeug seine Serie (Steckerlader) —
   eigener Test, sonst verlöre diese Anlage ihre Ladung ganz.
2. **Senken-Vorzeichen in der Achse-2-Invariante** (`core/berechnungen/invarianten.py`):
   `_ACHSE2_KATEGORIEN` trägt je Kategorie, ob der Leistungspfad negativ schreibt. PV (`quelle`)
   und Batterie (`bidirektional`) werden **nicht** angeglichen — je eigene Abgrenzungsprobe.

⚠ **Alt-Tage heilen nicht von selbst.** Bereits gespeicherte `TagesEnergieProfil.komponenten`
tragen ihre `eauto_*`-Keys weiter, der Chart zeigt sie weiter doppelt. Der Weg dorthin ist der
**bestehende** Reparatur-Knopf (`reaggregate_range`, Cap 31 Tage) — **keine Start-Migration**.
✅ **Der Daten-Checker findet die betroffenen Tage inzwischen selbst** und stellt den Knopf
daneben: Kategorie `EMOB_DOPPELZAEHLUNG_TAGE` (`services/daten_checker/emob.py`,
`action_kind="reaggregate_range"`). Damit ist auch die letzte Restarbeit dieses Abschnitts
erledigt — hier stand bis 2026-08-28 „noch nicht gebaut".

---

## Phase 4 — PHEV: elektrischen und fossilen Anteil trennen (#331)

> **Status: GEBAUT 2026-08-08.** Ausspezifiziert am Vormittag desselben Tages, gebaut im
> Anschluss — alle neun Etappen, beide Achsen, Anzeige und Daten-Checker. Melder **Safi105**,
> [Discussion #330](https://github.com/supernova1963/eedc-homeassistant/discussions/330)
> vom 09.06.2026 — der erste Punkt dieser Domäne mit einem **wartenden Melder**.
> Issue: [#331](https://github.com/supernova1963/eedc-homeassistant/issues/331).
>
> ⚠ **Eine Präzisierung gegenüber der Spezifikation, gemessen statt angenommen:** Entscheidung 5
> sagt „die Strom-Kosten bleiben unberührt" und begründet das damit, dass eedc die geladene
> Energie ohnehin misst. Das gilt für die **IST**-Achse. Auf der **Prognose**-Achse leitet
> `berechne_eauto_einsparung` den Strombedarf aber aus der Fahrleistung ab
> (`km × verbrauch_kwh_100km / 100`) — dort *muss* der elektrische Anteil den Bedarf begrenzen,
> sonst zahlt ein Plug-in-Hybrid in der ROI-Prognose Strom für alle Kilometer **und** Benzin für
> die verbrennergefahrenen, also dieselbe Strecke zweimal. Gebaut ist deshalb:
> `Strom_Bedarf = km_elektrisch × verbrauch / 100`, Vergleichs-Benziner weiterhin über alle km.
>
> ⚠ **Zwei Etappen-Angaben trugen nicht** (am Code geprüft, statt sie abzuarbeiten): Etappe 1
> nennt „Response-Model" und `core/field_definitions.py`. Das Response-Model führt `parameter` als
> freies `dict[str, Any]` (`investitionen/crud.py`), es strippt nichts; und `field_definitions.py`
> ist die Registry der **Monatsdaten-** und Live-Felder, nicht der Investitions-Parameter — ein
> Eintrag dort wäre am falschen Ort. Die tatsächlichen Pflicht-Stellen für einen
> `parameter`-Schlüssel sind `core/investition_parameter.py` **und** sein Frontend-Spiegel
> `lib/investitionParameter.ts`; beide sind gepflegt.

### Das Problem

Die Fahrzeug-Investition unterstellt in Ersparnis **und** CO₂-Rechnung **100 % elektrisch
gefahrene Kilometer**. Für ein BEV ist das richtig; für einen Plug-in-Hybrid werden dadurch
**Ersparnis und CO₂-Bilanz zu gut** dargestellt — der Benzin-Anteil fällt unter den Tisch, und
zwar zweimal: er wird weder als Kosten noch als Emission gezählt, obwohl er real anfällt.

### ⚠ Zwei Rechenachsen, nicht eine

Der Issue-Text nennt `core/calculations.py` — das ist richtig, aber **nur die halbe Fläche**.
Gemessen am Code gibt es zwei voneinander unabhängige Pfade, und ein Anteil, der nur in einem
von beiden wirkt, erzeugt genau die Drift-Klasse, die dieses Projekt wiederholt getroffen hat
(Aggregations-Drift):

| Achse | Ort | Rechnet mit | Wer liest sie |
| --- | --- | --- | --- |
| **IST** (Vergangenheit) | `services/eauto_wirtschaftlichkeit.py` | **gemessenen** `km_gefahren` + **tatsächlicher** Ladung + `vergleich_verbrauch_l_100km` | Komponenten-Hub, Cockpit, Monatsbericht, HA-Export, Aussichten-Historie, CO₂ |
| **Prognose/ROI** (Zukunft) | `core/calculations.py:310-364` (`berechne_eauto_einsparung`) | **geplanter** `jahresfahrleistung_km` × `verbrauch_kwh_100km` × `pv_ladeanteil_prozent` | ausschließlich `api/routes/investitionen/crud.py:1508` (ROI-Tabelle) |

Beide müssen den Anteil kennen — **aber sie bestimmen ihn verschieden**, weil die Zukunft keine
Messung hat. Das ist kein Sonderfall, sondern die schon bestehende Trennung des Systems.

### Getroffene Entscheidungen (2026-08-08)

**1. Der Anteil wird gemessen, nicht geschätzt — wo eine Messung existiert.**
Die elektrisch gefahrenen Kilometer folgen aus dem **elektrischen Fahrverbrauch** und dem
Fahrzeug-Kennwert:

```text
km_elektrisch  = min( km_gefahren ,  fahrverbrauch_kwh / verbrauch_kwh_100km × 100 )
km_verbrenner  = km_gefahren − km_elektrisch
```

Beide Eingangsgrößen **existieren heute**: `fahrverbrauch_kwh` ist das E-Auto-Feld `verbrauch_kwh`
(„der reine Fahrverbrauch, NICHT pro Fahrt und NICHT kWh/100 km", `core/field_definitions.py`),
`verbrauch_kwh_100km` ist ein gepflegter Parameter (`PARAM_E_AUTO`, Default 18). **Keine
Schema-Erweiterung für die Messung**, und keine Schätzung — das ist die Zusage aus #330.

> ⚠ **Das `min(…)` ist nicht kosmetisch.** Ist `verbrauch_kwh_100km` zu niedrig gepflegt oder der
> Fahrverbrauchs-Zähler zu großzügig, kommt rechnerisch mehr elektrische Strecke heraus als
> überhaupt gefahren wurde. Ohne Deckelung entstünden **negative Verbrenner-Kilometer** und damit
> eine Ersparnis, die größer ist als die Wahrheit. Gedeckelt bleibt der Fehler sichtbar
> (Verbrenner-Anteil 0) statt sich in einen Gewinn zu verwandeln.

**2. Ein eigenes Feld für den realen Verbrenner-Verbrauch — `vergleich_verbrauch_l_100km` bleibt,
was es ist.**
Neuer Parameter **`eigener_verbrauch_l_100km`**. Das bestehende Feld beschreibt einen **fiktiven
Vergleichs-Benziner** („was hätte ein gleichwertiges Verbrenner-Fahrzeug gebraucht", Default 7,5)
und hat **sieben** Produktions-Leser (`aussichten.py` ×2 · `ha_export.py` ×2 ·
`cockpit/nachhaltigkeit.py` · `investitionen/crud.py` · `eauto_wirtschaftlichkeit.py`). Es beim
PHEV umzudeuten würde Zahlen bei allen Nicht-PHEV-Nutzern bewegen und wäre dieselbe Doppelbelegung,
die bei `verbrauch_kwh` als **Schwäche A** dokumentiert ist und dort einen Daten-Checker-Fehlalarm
erzeugt hat. **Zwei Bedeutungen brauchen zwei Felder.**

**3. Das gesetzte Feld IST die Aussage — kein Fahrzeugtyp, kein Flag.**
eedc kennt keinen „Fahrzeugtyp PHEV" und bekommt auch keinen. Die Regel ist strukturell, nicht
magnitudenabhängig — dieselbe Linie wie Entscheidung 1 von Phase 2a („existiert eine Wallbox?"):

> **Ist `eigener_verbrauch_l_100km` gesetzt (> 0), hat das Fahrzeug einen Verbrenner.**
> Ist es leer, ist es ein BEV und **jede Zahl bleibt exakt wie heute.**

Damit gibt es keine Erkennungsheuristik, die kippen kann, und **keinen Breaking Change**: Bestands-
anlagen haben das Feld nicht, also ändert sich für sie nichts — auch nicht um einen Cent.

**4. Die Prognose-Achse nutzt den Prozentwert als Fallback, nicht als Primärweg.**
Neuer Parameter **`elektrischer_fahranteil_prozent`** (0–100). Er greift **genau zwei Mal**:
in der Prognose/ROI-Achse (dort gibt es keine Messung) und im IST, wenn `verbrauch_kwh` **nicht
gepflegt** ist. **Kein Zahlen-Default für PHEV** — kein „Richtwert 40–60 %", wie der Issue-Body
ihn erwägt: ein erfundener Mittelwert ist eine Behauptung über ein fremdes Fahrzeug. Fehlt der
Wert, gilt **100 % elektrisch** (heutiges Verhalten) und der Daten-Checker sagt, dass die Angabe
fehlt.

**5. Die Vergleichsrechnung wird nicht angefasst — der fossile Anteil ist eine eigene Kostenposition.**
Der entscheidende Kunstgriff, der Entscheidung 2 erst trägt:

```text
benzin_kosten_vergleich = km_gefahren   / 100 × vergleich_verbrauch_l_100km × benzinpreis   ← UNVERÄNDERT
fossile_restkosten      = km_verbrenner / 100 × eigener_verbrauch_l_100km   × benzinpreis   ← NEU
strom_kosten            = (wie heute, aus der tatsächlich gemessenen Ladung)                ← UNVERÄNDERT

ersparnis = benzin_kosten_vergleich − strom_kosten − fossile_restkosten
```

Die Frage „was hätte ein Benziner gekostet" bleibt über **alle** Kilometer gestellt — sonst
verglichen wir ein Auto mit einem halben Auto. Neu ist nur, dass die **real angefallenen**
Benzinkosten des PHEV als Kosten danebenstehen. Analog CO₂: die vermiedene Emission wird um
`km_verbrenner / 100 × eigener_verbrauch_l_100km × CO2_FAKTOR_BENZIN_KG_LITER` **reduziert**.

> ⚠ **Die Strom-Kosten bleiben unberührt, und das ist kein Versehen.** eedc misst die geladene
> Energie ohnehin — sie ist nicht aus der Fahrleistung abgeleitet. Ein PHEV lädt weniger, also
> steht dort schon die kleinere Zahl. Wer die Ladung zusätzlich mit dem Anteil skalierte, zöge sie
> **zweimal** ab.

### Bekannte Schwäche, die Phase 4 erbt

`verbrauch_kwh` am E-Auto ist **doppelt belegt** (Fahrverbrauch ∧ Legacy-Heimladung, s. Schwäche A)
— `get_eauto_ladung_kwh(data)` = `ladung_kwh or verbrauch_kwh`. Phase 4 macht dieses Feld erstmals
**rechnerisch tragend** für eine Anzeige-Zahl. Zwei Folgerungen:

- Der Anteil darf **nur** aus dem expliziten `verbrauch_kwh` gebildet werden, nie über
  `get_eauto_ladung_kwh` — sonst wird eine Heimladung als Fahrverbrauch gelesen.
- Gernots eigenes Fahrzeug (Smart #1) führt das Feld **bewusst leer** (s. Schwäche A). Die
  Fallback-Kette aus Entscheidung 4 ist deshalb kein Randfall, sondern der Normalfall der einzigen
  Anlage, an der live gegengeprüft werden kann. **Ein Live-Gegencheck an einem echten PHEV fehlt
  — Safi105 hat einen und hat die Datenlage in #330 selbst beschrieben.**

### Was NICHT dazugehört

- **Kein Feld für getankte Liter.** Wurde erwogen und verworfen: die wenigsten Fahrzeuge liefern
  einen kumulativen Liter-Zähler an HA, und der gemessene Weg aus Entscheidung 1 kommt ohne aus.
  Wird ein solcher Zähler später verbreitet, ist er ein additiver dritter Weg, kein Umbau.
- **Kein Fahrzeugtyp-Feld** (s. Entscheidung 3).
- **Keine Session-/Fahrten-Ebene.** eedc bleibt bei Monatsaggregaten — unverändert seit
  §„Abgrenzung" ganz oben.

---

## Phase 5 — Der PV-Anteil der Heimladung wird abgeleitet, nicht abgefragt (N-141 Weg c)

> **Stand 2026-08-08: vermessen, gebaut und angeschlossen.** Der Layer-SoT
> `core/berechnungen/pv_anteil_ladung.py` ist gegen echte Anlagendaten belegt, der Aggregator legt
> den Tageswert ab, und die Monats-Fakten ziehen ihn heran, wo kein gepflegter Wert existiert.
> ~~**Offen bleibt allein Rahmenbedingung 7** (Prognose, N-188).~~ ⚠ **Korrektur 2026-08-13:
> auch das ist erledigt** — zwei Abschnitte tiefer steht es selbst („⚑ Rahmenbedingung 7 (N-188)
> ist damit erledigt: die Prognose rät den Anteil nicht mehr"), und N-188 ist mit v4.0.11 gebaut.
> Dieser Kasten wurde beim Fortschreiben nicht mitgezogen — **N-182-Klasse, am selben Tag der
> dritte Fall** (vgl. HX-6 im HA-Export-Konzept und der Statuskopf des Speicher-Konzepts).
> ⇒ **Aus den Rahmenbedingungen ist damit nichts mehr offen.** ⚠ **Das heißt nicht „Konzept
> leer":** **Phase 2b** (Vehicle-Sensor-Mapping) und **Phase 3** (Multi-Fahrzeug) bleiben
> unverändert **trigger-gebunden geparkt** — Trigger ist die nächste evcc-Pool-Meldung, so führt
> es auch [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110). *Geparkt mit
> Trigger ist nicht dasselbe wie offener Arbeitsvorrat; ein erster Korrektur-Entwurf hier hat
> genau das verwechselt.*

### Das Problem

**Eine Wallbox misst ihren PV-Anteil nicht.** Sie zählt Kilowattstunden, nicht deren Herkunft.
Wer kein evcc betreibt, hat für `ladung_pv_kwh` gar keine Quelle — und der Leser
`get_emob_pv_netz_kwh` setzt den PV-Anteil dann auf **0**: die gesamte Heimladung gilt als
Netzstrom. Gleichzeitig liest die ROI-**Prognose** einen von Hand gepflegten
`pv_ladeanteil_prozent` (Default 60 %). Dieselbe Anlage steht damit auf **60 % PV in der Prognose
und 0 % im IST**.

### Die Lösung ist von evcc geborgt

evcc kennt ebenfalls keinen PV-Sensor an der Wallbox. Es kennt PV-Leistung, Netzbezug/Einspeisung
und Ladeleistung und rechnet je Zeitschritt, welcher Teil der Ladung gerade durch Überschuss
gedeckt war. „Sonne (%)" pro Session ist bei evcc ein **Rechenergebnis, keine Messung**. eedc hat
dieselben Eingänge stündlich vorliegen.

### Vermessen am 2026-08-08 gegen evcc

Anlage 1, Feb–Aug 2026, **963 kWh Heimladung**. Referenz waren nicht eedc-Monatswerte (die tragen
an dieser Anlage frühe Schätzungen), sondern **HA-Rohsensoren**: `sensor.evcc_helper_pv_charged_kwh`
und `…_net_charged_kwh`. Konsistenzprobe: März 175,19 + 64,81 = **240,00 kWh** = exakt die
Differenz des Wallbox-Zählers.

| Regel | PV-Anteil | Abweichung zu evcc (67,9 %) |
| --- | --- | --- |
| netzbasiert `min(Ladung, Netzbezug)` | 73,8 % | +5,9 pp (überschätzt) |
| netz + Speicherentladung | 60,8 % | −7,2 pp |
| **Einspeise-Deckung** — gebaut | **64,7 %** | **−3,2 pp** |

**Entscheid: Einspeise-Deckung.** Sie trifft die Referenz am besten und irrt in die unverdächtige
Richtung — sie schreibt die Ersparnis eher zu klein als zu groß.

### Zwei Messbefunde, die die Bauform bestimmen

1. ⚠ **Der Wallbox-Zähler dieser Anlage meldet nur ganze Kilowattstunden** — 218 von 218
   Stunden-Deltas ganzzahlig; am 05.06. landeten 20 kWh vollständig in der Stunde 05:00. **Wo ein
   Zähler so grob meldet, hilft keine feinere Rechnung.** Die ursprünglich vorgesehenen
   5-Min-Overlays bringen dort nichts; sie lohnen nur, wo der Zähler selbst feiner ist. Der Ort der
   Rechnung (**im Aggregator**) bleibt davon unberührt.
2. ⚠ **evcc-gespeiste Zähler springen am Session-Ende, statt mitzulaufen** (29.04.: fünf Stunden
   konstant, dann +44,49 kWh in einem Schritt). Für Monatswerte harmlos, für Tageswerte nicht — wer
   damit **stundengenau** prüft, misst einen Zeitversatz und hält ihn für einen Fehler.

### Rahmenbedingungen (Gernots Freigabe, unverändert gültig)

1. **Ein gepflegter echter Wert gewinnt immer** — die Ableitung füllt nur Lücken.
2. Rechnung **im Aggregator**, nicht nachträglich aus gespeicherten Stunden.
3. Nur wo Zeitreihen existieren; **Handeingabe bleibt beim heutigen Weg und sagt das**.
4. Der Wert wird als **abgeleitet gekennzeichnet** (P4-Linie, Muster „geschätzt (kWp-Anteil)").
5. **Keine rückwirkende Neuberechnung.** Gernot am 08.08.: *„Lass die historischen Werte in der
   Verantwortung des Benutzers und kümmere dich darum, dass es ab jetzt korrekt funktioniert."*
6. Zuerst die Messung — **erledigt**, siehe oben.
7. Die **Prognose zieht mit**: kann eedc den Anteil ableiten, braucht auch die ROI-Prognose keine
   Anwenderschätzung mehr, sonst lebt `pv_ladeanteil_prozent` neben der neuen Rechnung weiter.

### Der Anschluss — gebaut 2026-08-08

Drei Stellen, in dieser Reihenfolge:

1. **`services/energie_profil/aggregator.py`** — die Stundenschleife sammelt die vier Eingänge und
   ruft `leite_pv_anteil_ab`. Die Vorzeichen-Übersetzung macht der Layer-Helfer
   `stunde_aus_bilanzwerten`, **nicht** ein Ausdruck in der Schleife (Begründung unten).
2. **`TagesZusammenfassung`** — zwei Spalten `emob_ladung_{pv,netz}_abgeleitet_kwh` + Migration +
   `source_provenance`-Marke (Rahmenbedingung 4).
3. **`services/monats_fakten.py`** — `EmobFakten` zieht den Wert heran, wo kein gepflegter existiert,
   und weist das mit `ladung_anteil_abgeleitet` aus (Rahmenbedingung 1).

**Zwei Befunde haben die Bauform gegenüber dem Schnitt vom Vormittag geändert:**

⚠ **Die Eingänge sind NICHT „sämtlich positiv".** Der Satz galt für die Kategorie-Deltas
(`lts_aggregator.py:160-166` verwirft negative), **nicht** für den Ausgang: `batterie_netto` ist
`ladung − entladung`, die Entladung also **negativ**. Der Layer verlangt sie positiv und klemmt eine
negative mit `max(0, …)` auf 0 — die Speicherdeckung wäre **still** ausgefallen und die Regel
heimlich eine andere (netzbasiert + Einspeisung, an Gernots Anlage +9 pp). Deshalb übersetzt
`stunde_aus_bilanzwerten` aus der **Spalten-Konvention** (`batterie_kw_spalte`, Entladung positiv)
und ist mit eigenen Proben abgesichert. Dieselbe Klasse wie die F-14-Fixture vom selben Tag.

⚠ **Übernommen wird der ANTEIL, nicht die Kilowattstunde.** Tagesebene und Monatszeile müssen nicht
dieselbe Ladungsmenge kennen. Wer die abgeleiteten kWh direkt in die Monatszeile schreibt, zerbricht
die Trias `ladung == pv + netz` — und in der einen Richtung entsteht genau der #262-Fehler
(PV-Anteil > 100 %). Der Anteil auf die kanonische `ladung_kwh` angewandt hält sie exakt geschlossen.

**Reichweite (Entscheid Gernot, 2026-08-08):** Die Tagesebene wird **bedingt nachgeladen** — nur wenn
ein Monat Heimladung ohne gepflegten PV-Anteil trägt (`_RohMonat.emob_ladung_ohne_pv_anteil`, liest
nur bereits gefaltete Rohzeilen). Ohne dieses Nachladen sähe **genau eine** Sicht einen PV-Anteil
(Cockpit → Monat, der einzige Aufrufer mit `inkl_nur_tageswerte`), während Komponenten-Hub,
CO₂-Bilanz und E-Auto-Ersparnis weiter 0 % behaupteten. Eine Anlage ohne E-Mobilität zahlt nichts.
⚠ Die **Grundgesamtheit** erweitert das Nachladen ausdrücklich **nicht** — dafür bleibt das Flag
zuständig (N-121).

**Was sich für Anwender ändert:** Wer den PV-Anteil bisher gepflegt hat (evcc-Nutzer), sieht
**nichts** — der echte Wert gewinnt. Wer ihn nicht hatte, sah bisher 0 % PV und sieht künftig einen
abgeleiteten Anteil: der Komponenten-Hub zeigt statt 0 % einen Wert, die E-Mob-Netzladung in der
CO₂-Bilanz sinkt, die E-Auto-Ersparnis steigt. **Gehört in die Release-Kommunikation.**
⚠ **Rückwirkend passiert nichts** (Rahmenbedingung 5): Bestandstage tragen NULL, und NULL heißt
„keine Aussage". Ein Monat bewegt sich erst, wenn seine Tage neu aggregiert wurden.

Offen bleibt **Rahmenbedingung 7** (Prognose, **N-188**): solange `pv_ladeanteil_prozent` von Hand
gepflegt wird, steht die Prognose-Achse neben der neuen Rechnung.

> ⚠ **Korrektur 2026-08-08 (F-16 · N-198) — der Absatz darüber war in zwei von drei Wirkungen
> falsch, und die Zeile zu Rahmenbedingung 7 ist erledigt.** Er bleibt wörtlich stehen, weil er den
> Stand nach `a7a50abc` beschreibt; was tatsächlich galt, steht hier.
>
> **Der Fehler war die Methode, nicht die Formulierung.** Die Wirkungen waren aus der **Bauabsicht**
> geschrieben, nicht aus den **Lesestellen** ausgezählt. Die Ableitung saß in `monats_fakten.py`
> *oberhalb* von `get_emob_heimladung_canonical` und traf damit nur die Felder
> `EmobFakten.ladung_pv_kwh`/`ladung_netz_kwh`. Von **achtzehn** Lesestellen sahen sie **vier**:
>
> - **„Der Komponenten-Hub zeigt statt 0 % einen Wert"** traf eine **andere** Sicht — *Auswertungen
>   → Komponenten* (`cockpit/komponenten.py`). Der **Hub** selbst (`investitionen/dashboards.py`)
>   liest `InvestitionMonatsdaten` direkt und blieb bei 0 %.
> - **„Die E-Auto-Ersparnis steigt"** traf **keine** Sicht. Alle drei Ersparnis-Rechner
>   (`cockpit/uebersicht.py`, `investitionen/dashboards.py`, `aussichten.py`) poolen die Rohzeilen
>   neu; keiner las `EmobFakten.ladung_netz_kwh`.
> - **„Die E-Mob-Netzladung in der CO₂-Bilanz sinkt"** war die einzige zutreffende Aussage.
>
> **Kein Bestandstest schlug an:** `test_emob_readsite_symmetrie.py` prüft die Heimladungs-**Summe**,
> und die bleibt unberührt — die Ableitung ändert nur die **Aufteilung**. Ein Symmetrie-Test kann die
> falsche Größe prüfen und dabei grün bleiben, während die Drift danebensteht.
>
> **Gebaut wurde die Schicht, nicht der Anschluss je Sicht** (Entscheid Gernot: *alle IST-Sichten*).
> `services/emob_ladeanteil.py` reichert die Monatszeilen an, **bevor** irgendjemand sie poolt; die
> Sichten, die ihre IMD selbst laden, holen dieselbe Anreicherung über
> `reichere_monatszeilen_an`. Seitdem gilt die Wirkungsbeschreibung so, wie sie oben steht — für
> Hub, Cockpit → Jahr, Aussichten, Jahresbericht-PDF, Monats-Tabelle **und** die HA-Sensoren.
>
> ⚑ **Zwei Ausnahmen, beide bewusst:** der **Community-Payload** bleibt gemessen (der Server hat die
> Rohdaten nie gesehen und rechnet nichts nach — `eauto_summe_gemessen`/`wallbox_summe_gemessen`,
> kein neuer Anlagen-Hash), und ein **gepflegter Wert gewinnt** weiterhin überall, auch die
> gepflegte 0.
>
> ⚑ **Rahmenbedingung 7 (N-188) ist damit erledigt.** Die Prognose rät den Anteil nicht mehr:
> `investitionen/crud.py` nimmt den IST-Anteil aus den Monats-Fakten
> (`monats_fakten.ist_pv_ladeanteil_prozent`), wenn kein `pv_ladeanteil_prozent` gepflegt ist —
> Default 60 % nur noch, wenn auch das IST schweigt. Die **zweite**, im ursprünglichen Text nicht
> genannte Prognose-Quelle (`aussichten.py`, leitet die Quote aus der Historie ab) zieht über
> dieselbe Anreicherung mit.
>
> ⚑ **Wertänderung an einem ausgelieferten HA-Sensor:** `e_auto_pv_anteil_prozent` springt bei
> jedem, der keinen PV-Ladesensor pflegt, einmalig in der Langzeitstatistik — dasselbe Muster wie
> beim CO₂-Sensor zu v4.0.0. **Gehört in die Release-Kommunikation.**
>
> Der Wächter über die **Aufteilung** (nicht die Summe) ist
> `backend/tests/test_emob_pv_anteil_sichten_symmetrie.py`.
