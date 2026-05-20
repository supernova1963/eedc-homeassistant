# Konzept: Wallbox / E-Auto — Datenarchitektur

> **Status (2026-05-20): Phase 1 (Pool-Konsolidierung) vollständig.** Der ursprüngliche Quick-Fix (v3.25.11: getrennte Akkumulatoren EAuto/WB + **Max-pro-Feld**, siehe Memory `project_pool_fix_emob.md`) hat sich selbst als Drift-Quelle erwiesen: feldweises `max()` über `gesamt`/`pv`/`netz` als drei unabhängige Aufrufe konnte die Felder aus verschiedenen Quellen mischen und einen PV-Anteil > 100 % erzeugen (#262 junky84: Komponenten zeigte 48 % PV + 85 % Netz = 133 %). v3.31.6 ersetzt das Max-pro-Feld durch den SoT-Helper `aggregiere_emob_ladung` (`eedc/backend/services/eauto_wirtschaftlichkeit.py`): die Quelle mit der größeren Heimladung gewinnt die **komplette, in sich konsistente Trias** (`pv + netz == ladung` garantiert). **Alle fünf Read-Sites sprechen jetzt dieselbe Pool-Logik:** Wallbox-Dashboard, Komponenten-Zeitreihe, Cockpit-Übersicht und AktuellerMonat über `aggregiere_emob_ladung`, das E-Auto-Dashboard über `compute_emob_pool_attribution` + `attribute_emob_pool_by_km` (km-anteilige Verteilung, selbe use-wb-pool-Entscheidung). **Phase 2 (Vehicle-Sensor-Mapping) und Phase 3 (Multi-Fahrzeug-Dashboard) noch nicht angefangen** — in Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) als „Ideen / Konzeptphase"-Item; Trigger-Stand siehe Abschnitt »Phase-2-Trigger«.

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

## Dashboard-Darstellung (Ziel)

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

## Migrationspfad

### Phase 1: Bug-Fix (jetzt)
- Ladevorgänge aus Wallbox-Monatsdaten lesen (nicht nur E-Auto)
- Kein Datenmodell-Umbau nötig

### Phase 2a: Feldzuordnung geradeziehen (Schulden-getrieben)
- Eindeutige Feld-Rollen: die Heimladungs-Trias (`ladung_kwh`/`pv`/`netz`) gehört kanonisch an die **Wallbox** (Infrastruktur misst den Stromfluss), das E-Auto trägt Nutzung + km. Read-Sites lesen die kanonische Quelle statt eines Pools.
- Migration des bestehenden `verbrauch_daten`-JSON nötig — Daten-Reconnaissance vorher (siehe Daten-Checker-Warnung unten).
- **Trigger: bereits gefeuert.** Der wiederkehrende evcc-Pool-Patch-Bedarf (#260, #262, ~8 Fix-Commits seit v3.31.0) ist das Symptom der Mehrdeutigkeit; jeder Read-seitige Heuristik-Fix (zuletzt `aggregiere_emob_ladung`) ist nur ein Aufschub. Profitiert auch das 1+1-Setup.

### Phase 2b: Vehicle-Sensor-Mapping (Feature-getrieben)
- `ladung_heim_kwh` und `ladung_heim_pv_kwh` als neue E-Auto-Felder
- Sensor-Mapping erweitern für evcc Vehicle-Topics
- Wallbox-Dashboard liest eigene Daten, E-Auto die Vehicle-Sicht
- Bestehende `ladung_pv_kwh`/`ladung_netz_kwh` am E-Auto bleiben als Fallback
- **Trigger: „wenn Vehicle-Sensoren nachgefragt werden"** — hier stimmt die ursprünglich notierte Bedingung (Power-User mit Per-Vehicle-Aufschlüsselung). Bislang nicht erfüllt.

**Daten-Checker-Warnung bei Pool-Pflege-Mismatch:** wenn EAuto + WB beide gepflegt sind und die Werte erkennbar ähnlich (≈ derselbe Stromfluss aus zwei Perspektiven) bzw. beide Felder voll sind aber `WB.ladung_pv_kwh > Σ EAuto.ladung_heim_pv_kwh` ist, INFO/WARNING ausgeben — lenkt den User auf eine bewusste Entscheidung, welche Quelle die Wahrheit liefert. Hintergrund: 2026-05-02 fielen bei Joachim und Gernot inkonsistente Pool-Werte auf (PV-Anteil > 100 %, doppelter `kWh/100km`); der Quick-Fix in v3.25.x machte Max-pro-Feld-Auswahl, was sich selbst als Drift-Quelle erwies und in v3.31.6 durch den Gewinner-Pool `aggregiere_emob_ladung` ersetzt wurde. Die Phase-2-Trennung beseitigt die Doppelzählung strukturell, der Daten-Checker bleibt für Altbestand und Pool-Mode. **Diese Warnung braucht kein neues Datenmodell und ist als eigenständiges Stück vor Phase 2 ziehbar** (siehe »Phase-2-Trigger«: junky84 #262 hatte ~3.300 kWh Streudaten auf der E-Auto-Investition, die der Daten-Checker proaktiv sichtbar gemacht hätte).

### Phase 3: Aufschlüsselung im Wallbox-Dashboard (optional)
- Wenn E-Autos Vehicle-Sensoren haben, kann das Wallbox-Dashboard
  die Gesamt-kWh pro Fahrzeug aufschlüsseln
- Konsistenzprüfung WB-Gesamt vs. Σ E-Autos

### Kein Breaking Change
- Nutzer ohne evcc/RFID merken nichts — manuelle Eingabe funktioniert weiter
- 1:1-Setups (eine WB, ein Auto) bleiben identisch
- Pool-Aggregation bleibt Fallback wenn keine Vehicle-Sensoren gemappt sind

## Phase-2-Trigger — Stand 2026-05-20

Der dokumentierte Phase-2-Trigger lautet »wenn Vehicle-Sensoren nachgefragt werden«. Per-Vehicle-/Multi-Fahrzeug-Bedarf ist bislang **nicht** aufgetreten — junky84 (#262) und NongJoWo (#260) fahren beide 1 Wallbox + 1 E-Auto.

Ein *anderes* Signal wird aber deutlich: der **evcc-Portal-Import erzeugt seit v3.31.0 anhaltenden Patch-Bedarf** — #262 (vier Fix-Runden), #260 (zwei Runden), EVCC-Parser DE/EN, insgesamt ~8 emob-Fix-Commits in zwei Wochen. Ursache ist strukturell: evcc schreibt die Heimladung architektonisch an die **Wallbox** (`data_import.py`), während Read-Seite und Datenmodell historisch E-Auto-zentriert sind (siehe »Motivation«). Jeder Fix legt eine weitere Heuristik auf den Pool. Der `aggregiere_emob_ladung`-Gewinner-Pool aus v3.31.6 ist die bestmögliche Heuristik, bleibt aber eine Heuristik — er wählt die falsche Quelle, wenn verirrte Streudaten die echte Quelle übertreffen (bei junky84 lagen ~3.300 kWh Streudaten auf der E-Auto-Investition; die Wallbox gewann nur, weil ihre Heimladung noch größer war).

**Bewertung:**

- **Phase 2 (neue Felder `ladung_heim_*` + Vehicle-Sensor-Mapping)** — der dokumentierte Trigger ist noch nicht erfüllt (kein Multi-Vehicle-Bedarf), aber das evcc-Import-Churn-Signal nähert sich dem Punkt, an dem die strukturelle Lösung günstiger ist als die nächste Heuristik-Runde. Maintainer-Entscheidung; bei der nächsten evcc-Pool-Meldung neu bewerten.
- **Ohne Phase 2 vorziehbar:** die oben verortete »Daten-Checker-Warnung bei Pool-Pflege-Mismatch« braucht kein geändertes Datenmodell. Sie hätte junky84s Streudaten proaktiv sichtbar gemacht und ist ein kleines, eigenständiges Stück.

## Offene Fragen

1. Liefern SMA eCharger und Wattpilot ähnliche Per-Vehicle-Topics wie evcc?
2. Gibt es EEDC-Nutzer mit Multi-WB/Multi-E-Auto-Setup? (Joachim-xo prüfen)
3. Braucht das Monatsabschluss-Formular ein geändertes Layout für die neuen Felder?
