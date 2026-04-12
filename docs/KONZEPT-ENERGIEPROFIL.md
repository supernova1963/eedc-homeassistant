# Konzept: Energieprofil-Datenbestand (Etappe 1 Revision)

## Ausgangslage und Motivation

Das Energieprofil wurde in v3.1.x als Etappe 1 eingeführt mit dem Ziel, einen persönlichen
IST-Datenbestand aufzubauen, auf dessen Basis später **personalisierte Prognosen** möglich
werden — statt generischer Durchschnittswerte aus dem Internet.

Im Rahmen der Fehleranalyse zu Issue #64 (Batterie-kWh zu hoch im Live-Dashboard) wurde
der Energieprofil-Code eingehend untersucht. Dabei wurden mehrere strukturelle Mängel
identifiziert, die eine Revision von Etappe 1 notwendig machen, **bevor** mit Etappe 2
(Nutzung der Daten) begonnen werden kann.

---

## Implementierungsstand (Stand v3.12.0)

| Etappe | Inhalt | Status |
|---|---|---|
| **Etappe 1** | Datenbestand aufbauen (Revision + Scheduler) | ✅ v3.1.x / v3.9.0 |
| **Etappe 2** | Tagesdetail + Wochenvergleich | ✅ v3.11.0 |
| **Backfill** | Vollbackfill aus HA Long-Term Statistics | ✅ v3.12.x (heute) |
| **Etappe 3** | Monatsauswertung (Heatmap, PR-Trend, Batterie-Zyklen) | ⏳ nächster Sprint |
| **Etappe 4** | Saisonale Muster | ⏳ später |

---

## Datenquellen und Aggregations-Hierarchie

### Level 0 — Rohdaten (Quellen)

Es gibt vier voneinander unabhängige Datenquellen. Welche genutzt werden kann, hängt von der Systemkonfiguration ab:

```
┌─────────────────────────────────┬────────────────────────────────────────────────────────────────┐
│ Quelle                          │ Beschreibung                                                   │
├─────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ HA Sensor History               │ Rohe Zustandswerte aus HA Recorder (W/kW-Sensoren).            │
│ (ha_state_service)              │ Verfügbarkeit: ~10 Tage (HA-Recorder-Retention).               │
│                                 │ Auflösung: jede Zustandsänderung (Sekunden bis Minuten).       │
│                                 │ Nur verfügbar: HA-Add-on-Umgebung                              │
├─────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ HA Long-Term Statistics         │ Stündliche Mittelwerte (mean) aus HA statistics-Tabelle.       │
│ (ha_statistics_service)         │ Verfügbarkeit: gesamte HA-History (Jahre).                     │
│                                 │ Auflösung: 1 Stunde (mean-Wert je Stunde).                     │
│                                 │ Nur verfügbar: HA-Add-on + sensors mit has_mean=True           │
│                                 │ kWh-Zähler (has_sum) werden für Profile NICHT genutzt          │
├─────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ MQTT Snapshots                  │ Periodische Leistungs-Snapshots (alle 5 Min) aus MQTT-Inbound. │
│ (mqtt_live_history_service)     │ Verfügbarkeit: solange gespeichert (konfigurierbar).           │
│                                 │ Auflösung: 5 Minuten.                                          │
│                                 │ Standalone-Fallback: wenn kein HA verfügbar                    │
├─────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ Open-Meteo Archive API          │ Historische Wetter-IST-Daten (temperature_2m,                  │
│ (archive-api.open-meteo.com)    │ shortwave_radiation). Verfügbar für beliebige Vergangenheit.   │
│                                 │ Wird für alle Tage außer heute genutzt.                        │
├─────────────────────────────────┼────────────────────────────────────────────────────────────────┤
│ Open-Meteo Forecast API         │ Wetter-Prognose für den heutigen Tag.                          │
│ (api.open-meteo.com)            │ Wird durch Archive-Daten ersetzt sobald Tag abgeschlossen.     │
└─────────────────────────────────┴────────────────────────────────────────────────────────────────┘
```

### Level 1 — TagesEnergieProfil (24 Zeilen / Tag / Anlage)

**Was:** Stündlich aggregierte Leistungswerte. Eine Zeile pro Stunde (0–23), pro Tag, pro Anlage.

**Woher kommen die Daten (Quellen-Auswahl):**

```
Schreibzeitpunkt          Energiedaten-Quelle              Wetter-Quelle
─────────────────────────────────────────────────────────────────────────────────────
Rollierend (15 Min)       HA Sensor History (heute)        Open-Meteo Forecast
                           oder MQTT Snapshots (Standalone)
─────────────────────────────────────────────────────────────────────────────────────
Täglich 00:15             HA Sensor History (gestern)      Open-Meteo Archive
                           oder MQTT Snapshots (Standalone)
─────────────────────────────────────────────────────────────────────────────────────
Monatsabschluss           HA Sensor History (bis ~10 Tage) Open-Meteo Archive
(backfill_range)           → nur innerhalb Recorder-Fenster
─────────────────────────────────────────────────────────────────────────────────────
Vollbackfill              HA Long-Term Statistics (years)  Open-Meteo Archive
(backfill_from_statistics) → beliebig weit zurück
                           → keine MQTT-Entsprechung
─────────────────────────────────────────────────────────────────────────────────────
```

**Verdichtung zur nächsten Ebene (Level 2):**

Alle 24 Stunden-Zeilen eines Tages werden zu einer `TagesZusammenfassung`-Zeile aggregiert:

```
TagesEnergieProfil (24×)          →    TagesZusammenfassung (1×)
──────────────────────────────────────────────────────────────────
pv_kw (24 Stundenwerte)           →    peak_pv_kw = MAX(pv_kw)
                                        (kWh via Summe, in Monatsdaten)
netzbezug_kw (24 Stundenwerte)    →    peak_netzbezug_kw = MAX(netzbezug_kw)
einspeisung_kw (24 Stundenwerte)  →    peak_einspeisung_kw = MAX(einspeisung_kw)
ueberschuss_kw (24 Stundenwerte)  →    ueberschuss_kwh = SUM(ueberschuss_kw) × 1h
defizit_kw (24 Stundenwerte)      →    defizit_kwh = SUM(defizit_kw) × 1h
soc_prozent (24 Stundenwerte)     →    batterie_vollzyklen = ΔSOC-Summe / 200 %
                                        (ein Vollzyklus = 200 % Δ)
globalstrahlung_wm2 (24×)        →    strahlung_summe_wh_m2 = SUM × 1h
temperatur_c (24 Stundenwerte)    →    temperatur_min_c, temperatur_max_c
pv_kw + globalstrahlung_wm2      →    performance_ratio = ΣPV / (Σstrahlung × kWp / 1000)
stunden_verfuegbar                →    stunden_verfuegbar = COUNT(Zeilen mit Daten)
komponenten (24 JSON-Dicts)       →    komponenten_kwh = SUM je Key × 1h
```

**Retention:** 2 Jahre (Cleanup täglich um 00:15). `TagesZusammenfassung` bleibt dauerhaft.

### Level 2 — TagesZusammenfassung (1 Zeile / Tag / Anlage)

**Was:** Tageskennzahlen, dauerhaft gespeichert. Basis für Etappe 3 (Monatsauswertung).

**Verdichtung zur nächsten Ebene (Level 3, via `rollup_month()`):**

```
TagesZusammenfassung (N Tage eines Monats)    →    Monatsdaten-Felder
──────────────────────────────────────────────────────────────────────
ueberschuss_kwh (alle Tage)       →    Monatsdaten.ueberschuss_kwh = SUM
defizit_kwh (alle Tage)           →    Monatsdaten.defizit_kwh = SUM
batterie_vollzyklen (alle Tage)   →    Monatsdaten.batterie_vollzyklen = SUM
performance_ratio (alle Tage)     →    Monatsdaten.performance_ratio = Ø (Mittelwert)
peak_netzbezug_kw (alle Tage)     →    Monatsdaten.peak_netzbezug_kw = MAX
```

**Trigger für rollup_month():** Am Ende des Monatsabschlusses (nach `save_monatsabschluss()`).

### Level 3 — Monatsdaten (1 Zeile / Monat / Anlage)

**Was:** Monatskennzahlen aus Energieprofil-Rollup (zusätzlich zu den Zählerwerten aus HA Statistics / Portal-Import / manueller Eingabe).

**Achtung:** `Monatsdaten` enthält zwei verschiedene Daten-Ebenen:
- **Zählerwerte** (pv_erzeugung_kwh, netzbezug_kwh etc.) → aus Monatsabschluss-Import (HA Statistics / Portal-Import / manuell)
- **Energieprofil-Rollup** (ueberschuss_kwh, performance_ratio etc.) → aus `rollup_month()` / TagesZusammenfassung

### Zusammenfassung Datenfluss

```
HA Sensor History (~10 Tage)  ──┐
HA Long-Term Statistics (Jahre) ──┤
MQTT Snapshots (Standalone)    ──┤──→ TagesEnergieProfil ──→ TagesZusammenfassung ──→ Monatsdaten
Open-Meteo Archive (Wetter)    ──┘    (24 Zeilen/Tag)        (1 Zeile/Tag)            (Rollup-Felder)
                                       2 Jahre Retention       dauerhaft
```

---

## Ziele des Energieprofils

### Primäres Ziel: Personalisierte IST-Prognosen

**Erzeugungsprognose:** Statt "durchschnittliche PV-Anlage in Deutschland" soll EEDC
sagen können: "Basierend auf deinen letzten 12 Monaten produzierst du an einem bewölkten
Dienstag im März typischerweise X kWh bis 14:00 Uhr."

**Verbrauchsprognose:** Statt allgemeiner Lastprofile soll EEDC sagen können: "Dein
typischer Haushaltsverbrauch an einem Werktag im Winter liegt zwischen 7:00–9:00 Uhr
bei X kW — deine WP läuft dann erfahrungsgemäß auf Y % Last." Personalisierte
Verbrauchsmuster ermöglichen es, Überschuss, Eigenverbrauch und Netzbezug für den
kommenden Tag realistisch vorherzusagen.

### Weitere Nutzungsmöglichkeiten
| Use Case | Erläuterung | Stündlich ausreichend? |
|---|---|---|
| Autarkie-Analyse | Welche Stunden sind typischerweise netzunabhängig? | ✓ ja |
| Überschuss-Management | Wann lohnt Wallbox/WP-Steuerung? | ✓ ja |
| Tarif-Optimierung | Netzbezug in teuren Stunden minimieren (Tibber etc.) | ✓ ja (Tarife sind stündlich) |
| WP-Effizienz-Trends | JAZ-Verlauf gegen Außentemperatur über Monate | ✓ ja |
| Anomalie-Erkennung | Ungewöhnliche Verbrauchsmuster | ⚠ nur persistente Anomalien |
| Batterie-Zyklen | Optimale Lade-/Entladezeiten | ✓ ja |
| Community-Benchmarks | Normierte Profile vergleichen | ✓ ja |
| Saisonale Muster | Sommer/Winter, Werktag/Wochenende | ✓ ja |

**Entscheidung: Stündliche Auflösung beibehalten.** 7 von 8 Use Cases funktionieren
vollständig stündlich. Feinere Auflösung (5 Min) wäre für Anomalie-Erkennung von
Kurzzeit-Spikes besser, aber die wird ohnehin auf Live-Daten aufgebaut, nicht auf
historischen Profilen.

---

## Identifizierte Mängel in der aktuellen Implementierung

### Mangel 1: Falsche Sign-basierte Aggregation

**Problem:** Die Aggregat-Felder werden kategorie-basiert berechnet (nach Investitionstyp),
nicht vorzeichenbasiert (nach tatsächlichem Energiefluss).

**Konkrete Fehler:**
- `batterie_kw`: enthält nur `speicher`-Typ, **V2H (E-Auto mit V2H-Funktion) fehlt**
  → V2H-Entladung ins Haus wird weder als Erzeugung noch als Batterie-Entladung gezählt
- `verbrauch_kw`: schließt E-Auto bewusst aus (korrekt), aber **Sonstiges mit positiven
  Werten (BHKW, Notstromaggregat)** wird durch `if werte.get(k, 0) < 0` herausgefiltert
  → ein BHKW taucht weder in `pv_kw` noch in `verbrauch_kw` auf — es verschwindet
- `pv_kw`: enthält nur `pv-module` und `balkonkraftwerk`, kein BHKW

**Prinzip der Lösung:** Vorzeichenbasierte Aggregation statt kategorie-basierter.
Im Butterfly-Chart gilt: positiv = Quelle, negativ = Senke. Das muss auch im Profil gelten.

### Mangel 2: Batterie-Datenqualität (gleiche Ursache wie #64)

**Problem:** `aggregate_day()` ruft `get_tagesverlauf()` auf, das dieselbe
W-Sensor + Trapez-Integration verwendet. Bei Batterien mit Sensor-Rauschen um 0 W
akkumuliert das Rauschen über eine Stunde zu falschen kWh-Werten.

**Lösung:** Gleicher Ansatz wie v3.6.8: In `get_tagesverlauf()` (bzw. in der
Stunden-Aggregation) prüfen ob separate `ladung_kwh`/`entladung_kwh` aus dem
Monatsabschluss-Mapping verfügbar sind, und diese statt Trapez verwenden.

### Mangel 3: Heute-Daten nie vorhanden

**Problem:** Der Scheduler läuft täglich um 00:15 und schreibt **nur den Vortag**.
Heute's Profil ist immer leer — für Intraday-Analysen und Tages-Vergleiche nutzlos.

**Lösung:** Zusätzlicher rollierender Scheduler alle 15 Minuten (tagsüber).

### Mangel 4: Fehlende Detailauflösung bei Verbrauchern

**Problem:** `verbrauch_kw` ist ein Sammelbecken. Für WP-Effizienz-Analyse und
Wallbox-Muster braucht man Einzelwerte.

**Lösung:** Separate Spalten für wichtige Verbraucher.

---

## Datenmodell: TagesEnergieProfil (neu)

### Geänderte/neue Spalten

```
-- Erzeuger (alle positiven Quellen, vorzeichenbasiert)
pv_kw           FLOAT   -- PV-Module + BKW + BHKW + Sonstiges (wenn positiv/Quelle)

-- Verbraucher (alle negativen Senken, als Absolutwert)
verbrauch_kw    FLOAT   -- Alle Senken gesamt (haushalt + WP + Wallbox + Sonstiges-negativ)
waermepumpe_kw  FLOAT   -- WP separat (für JAZ-Effizienz-Trends) NEU
wallbox_kw      FLOAT   -- Wallbox/E-Auto separat (für Lademuster) NEU

-- Netz
einspeisung_kw  FLOAT   -- Grid Export
netzbezug_kw    FLOAT   -- Grid Import

-- Speicher (alle Speicher inkl. V2H, vorzeichenbehaftet)
batterie_kw     FLOAT   -- positiv=Entladung(Quelle), negativ=Ladung(Senke), inkl. V2H NEU

-- Bilanz
ueberschuss_kw  FLOAT   -- max(0, pv - verbrauch) unverändertt
defizit_kw      FLOAT   -- max(0, verbrauch - pv) unverändert

-- Wetter (unverändert)
temperatur_c          FLOAT
globalstrahlung_wm2   FLOAT

-- Batterie-SoC (unverändert)
soc_prozent     FLOAT

-- Alle Einzelkomponenten (Quelle der Wahrheit, unverändert)
komponenten     JSON    -- {pv_3: 2.1, waermepumpe_5: -0.8, batterie_2: 1.2, ...}
```

### Aggregationslogik (neu, vorzeichenbasiert)

```python
for komp_key, kw in werte.items():
    if kw is None:
        continue
    # Erzeuger: alle positiven Werte (PV, BHKW, Sonstiges-positiv, Batterie-Entladung)
    # Senken: alle negativen Werte (Verbraucher, Batterie-Ladung)

# pv_kw: Summe aller pv_* und bkw_* Keys + alle anderen positiven außer batterie/netz
# batterie_kw: Summe aller batterie_* und v2h_* Keys (signed)
# waermepumpe_kw: Summe aller waermepumpe_* Keys (Absolutwert)
# wallbox_kw: Summe aller wallbox_* und eauto_* Keys (Absolutwert)
# verbrauch_kw: alle negativen Nicht-Netz-Nicht-Batterie Keys (Absolutwert)
```

---

## Schreibzeitpunkte

### Trigger 1: Rollierend alle 15 Minuten (neu)
- **Was:** Schreibt die vergangenen Stunden-Slots für heute (mit 10 Min Puffer)
- **Warum:** Heute's Profil wächst laufend mit → Intraday-Vergleiche möglich
- **Bedingung:** Nur wenn Live-Sensoren konfiguriert
- **Quelle:** HA-History für abgeschlossene Stunden (→ Daten garantiert vorhanden)

### Trigger 2: Täglich 00:15 Uhr (erweitert)
- **Was:** Vollständige Qualitätssicherung des gestrigen Tages
  1. Lückenfüllung (fehlende Stunden ergänzen)
  2. Wetter-IST finalisieren (Archive-API statt Forecast)
  3. `TagesZusammenfassung` berechnen und speichern
  4. Retention-Cleanup: `TagesEnergieProfil`-Einträge älter als **2 Jahre** löschen
     (`TagesZusammenfassung` bleibt dauerhaft erhalten)
- **Warum:** `TagesZusammenfassung` darf erst nach Tagesende final sein

### Trigger 3: Monatsabschluss (unverändert)
- **Was:** Backfill des gesamten Monats (innerhalb HA-History-Fenster ~10 Tage)
- **Was zusätzlich:** Monats-Rollup aus `TagesZusammenfassung`

---

## Retention-Strategie

| Tabelle | Aufbewahrung | Begründung |
|---|---|---|
| `TagesEnergieProfil` | 2 Jahre (konfigurierbar) | Stundenwerte für Muster-Erkennung ausreichend |
| `TagesZusammenfassung` | Unbegrenzt | Klein, Langzeit-Trends, Basis für Monats-Rollup |

---

## Altdaten

Die bestehenden ~288 Stundenwerte (Stand: März 2026) werden **gelöscht**.
Begründung: Die Aggregation war fehlerhaft (sign-basiert), ein sauberer Neustart
ist sinnvoller als das Fortschreiben von falschen Daten.
Nur Gernot ist betroffen, kein anderer Nutzer weiß von diesen Daten.

---

## Nicht umgesetzt (bewusste Entscheidungen)

| Thema | Entscheidung | Begründung |
|---|---|---|
| 5-Minuten-Auflösung | Nein | Für alle Use Cases stündlich ausreichend; 12× mehr Daten ohne konkreten Mehrwert |
| Arbitrage-Spalte | Nein | Eigenes Feature, braucht Tarif-Integration die noch nicht existiert |
| V2H eigene Spalte | Nein | V2H-Beitrag in `batterie_kw` ausreichend für Analyse |
| Intraday-Steuerung | Nein | Eigenes Thema, läuft auf Live-Daten nicht auf Profilen |

---

## Implementierungsschritte

### Schritt 1: Altdaten löschen + Migration
- Tabellen `TagesEnergieProfil` und `TagesZusammenfassung` leeren
- DB-Migration: neue Spalten `waermepumpe_kw` und `wallbox_kw` hinzufügen

### Schritt 2: Aggregationslogik korrigieren (`energie_profil_service.py`)
- Vorzeichenbasierte Aggregation implementieren
- V2H in `batterie_kw` einbeziehen
- BHKW/Sonstiges-positiv in `pv_kw` einbeziehen
- `waermepumpe_kw` und `wallbox_kw` separat berechnen
- Batterie-Qualität: kWh-Sensoren aus Monatsabschluss-Mapping nutzen (wie v3.6.8)

### Schritt 3: Rollierender Scheduler (alle 15 Min)
- Neuen Job in `scheduler.py` einrichten
- Funktion `aggregate_current_day()` in `energie_profil_service.py` implementieren
- Schreibt abgeschlossene Stunden des laufenden Tages

### Schritt 4: 00:15-Job erweitern
- Retention-Cleanup (> 2 Jahre) ergänzen
- `TagesZusammenfassung` erst nach 00:15 finalisieren (nicht mehr rollierend)

### Schritt 5: Testen + Release

---

## Etappe 2: Analyse & Statistik

### Kontext

Die Datenbasis (TagesEnergieProfil + TagesZusammenfassung) wächst täglich. Etappe 2 nutzt
diese Daten für strukturierte Musteridentifikation, Abhängigkeitsanalyse und — perspektivisch —
personalisierte Prognosen. Berechnungsergebnisse sollen in einem eigenen Tab sichtbar sein und
gleichzeitig Live Dashboard und Aussichten versorgen.

---

### Frontend-Struktur

Die bestehende Seite "Energieprofil" in Auswertungen erhält einen dritten Tab:

```
Energieprofil
├── Tagesdetail          (stündliches Butterfly-Profil — unverändert)
├── Wochenvergleich      (typische Tages-Muster — unverändert)
└── Analyse & Statistik  ← NEU
```

Der Tab "Analyse & Statistik" ist die zentrale Anlaufstelle für Details zu Berechnungen,
Ergebnissen und Wahrscheinlichkeiten. Prognosen aus diesem Modul werden zusätzlich im
Live Dashboard und in Aussichten als Schnellanzeige + Konfidenzintervall eingeblendet.

---

### Inhalt "Analyse & Statistik"

#### Abschnitt 1 — Tagestyp-Verteilung
- **Tagestyp-Klassifikation** (Schwellwert-basiert auf `TagesZusammenfassung`):
  - `sonnentag`: Performance Ratio > 0.65 oder Strahlung > Saisonschwelle
  - `mischtag`: mittlere Variabilität
  - `schlechtwetter`: PR < 0.25
  - `anomalie`: Verbrauch oder Ertrag > 2× Saisonmedian
- **Visualisierung:**
  - Balkendiagramm Tagestyp-Verteilung (letzten 30/90/180/365 Tage wählbar)
  - Typisches Stundenprofil je Tagestyp als P25/P50/P75-Band ("So sieht dein typischer Sonnentag aus")

#### Abschnitt 2 — Korrelationen & Abhängigkeiten
- **Korrelationsmatrix (Heatmap):**
  - PV-Ertrag ↔ Globalstrahlung (sollte > 0.95 sein — Abweichung deutet auf Degradation hin)
  - Verbrauch ↔ Außentemperatur (Heizperiode vs. Sommer)
  - Autarkie ↔ Tagestyp
  - Batterie-Zyklen ↔ PV-Überschuss
  - Netzbezug ↔ Bewölkung
- **WP-Regression** (wenn WP vorhanden):
  - Streudiagramm: WP-Verbrauch vs. Außentemperatur
  - Regressionsgerade + R²-Koeffizient sichtbar
  - Klartext: "Pro Grad unter 15 °C verbraucht deine WP ~X kWh mehr pro Tag"
- **Technik:** Pearson-Korrelation + lineare Regression mit `numpy` (bereits Dependency)

#### Abschnitt 3 — Prognose-Scorecard *(ab Phase C)*
- MAE (Mean Absolute Error) in kWh
- MAPE (Mean Absolute Percentage Error) in %
- Bias (systematische Über-/Unterschätzung)
- Skill Score vs. Naiv-Prognose (Vorjahreswert)
- Zeitreihe des Prognosefehlers (wird der Algorithmus über Zeit besser?)
- Getrennt für PV-Ertrag und Verbrauch

#### Abschnitt 4 — Wahrscheinlichkeiten & Konfidenz *(ab Phase C)*
- Für jede Prognose: nicht nur Punktwert, sondern Konfidenzintervall
- Beispiel: "18 kWh Verbrauch [14–22 kWh, 80 % Konfidenz]"
- Basiert auf der Streuung der historischen Analogietage (P10/P50/P90)
- Dieselben Werte erscheinen in Live Dashboard und Aussichten als Fehlerbalken

---

### Schema-Vorbereitung: 3 neue Spalten in TagesZusammenfassung

Wird zusammen mit Etappe 1 (Revision) migriert:

```python
tagestyp                 = Column(String(20), nullable=True)
# Prognose-Persistierung (damit Scorecard rückwirkend berechenbar):
verbrauch_prognose_kwh   = Column(Float, nullable=True)
# pv_prognose_kwh existiert bereits → wird für Scorecard genutzt
```

**Warum jetzt:** Wenn Prognosen nicht zum Zeitpunkt der Vorhersage gespeichert werden, ist
der spätere Fehlervergleich (IST vs. Prognose) nicht möglich. Die Rohdaten wachsen sowieso —
nur die Prognose-Persistierung muss früh vorbereitet werden.

---

### Verwendung in Live Dashboard + Aussichten

Die Analyse-Engine liefert Punktwert + Konfidenzintervall an drei Stellen:

| Ort | Anzeige |
|---|---|
| **Analyse-Tab** | Vollständige Methodik, Koeffizienten, Scorecard |
| **Live Dashboard** | "Noch ~3.2 kWh PV bis Abend [2.1–4.8 kWh]" + Speicher-Ladeprognose (#101) |
| **Aussichten** | Tages-Verbrauchsprognose mit Unsicherheitsband, temperaturbereinigt |

Technisch: eine gemeinsame Backend-Funktion `analyse_service.prognose_heute()` /
`prognose_tag(datum)`, die von allen drei Endpunkten aufgerufen wird.

---

### Implementierungsphasen

| Phase | Inhalt | Voraussetzung | Neue Libs |
|---|---|---|---|
| **A** | Tagestyp-Klassifikation, Percentile-Profile, Tab-Grundgerüst | ~30 Tage Daten | keine |
| **B** | Korrelationsmatrix, WP-Regression, Abhängigkeits-Heatmap | ~60 Tage | `numpy` (vorhanden) |
| **C** | Historische Analogie-Prognose + Scorecard + Konfidenz | ~90 Tage | keine |
| **D** | Holt-Winters Trend/Saison-Zerlegung (Monatsebene) | ~6 Monate | `statsmodels` |
| **E** | SARIMAX + Auto-Tuning (optional, bei nachgewiesenem Mehrwert) | ~18 Monate | `pmdarima` |

**Priorität Phase D/E:** Holt-Winters und ARIMA können jederzeit auf historischen Daten
gerechnet werden — kein Datenverlust durch späteren Start. Phasen A–C mit vorhandenen
Abhängigkeiten realisieren, D/E wenn Datenbasis und konkreter Bedarf vorliegen.

---

### Bewusste Entscheidungen (Community)

- **Kein Community-Upload von Profildaten** — Analyse läuft ausschließlich lokal
- Community-Benchmark (normierter PR-Vergleich) ist davon unabhängig und bleibt anonym-aggregiert

---

## Phase A — Implementierungsplan (bereit zur Umsetzung)

### Betroffene Dateien

| Datei | Änderung |
|---|---|
| `backend/models/tages_energie_profil.py` | 2 neue Spalten in TagesZusammenfassung |
| `backend/core/database.py` | Migration für neue Spalten |
| `backend/services/energie_profil_service.py` | Klassifikationsfunktion + Analyse-Service-Funktion + Rückfüllung |
| `backend/api/routes/energie_profil.py` | 3 neue Response Models + 1 neuer Endpoint |
| `frontend/src/api/energie_profil.ts` | TypeScript Interfaces + API-Methode |
| `frontend/src/pages/auswertung/EnergieprofilTab.tsx` | 3. Tab + AnalyseStatistik-Komponente |

### Schritt 1 — DB-Model

`tages_energie_profil.py` — nach `komponenten_kwh` (Zeile ~149):

```python
tagestyp               = Column(String(20), nullable=True)   # sonnentag/mischtag/schlechtwetter/anomalie
verbrauch_prognose_kwh = Column(Float, nullable=True)        # persistierte Vorhersage für spätere Scorecard
```

### Schritt 2 — DB-Migration

`database.py` — nach `sfml_prognose_kwh`-Migration (Zeile ~162):

```python
for col, coltype in [("tagestyp", "VARCHAR(20)"), ("verbrauch_prognose_kwh", "FLOAT")]:
    result = await db.execute(text(
        f"SELECT COUNT(*) FROM pragma_table_info('tages_zusammenfassung') WHERE name='{col}'"
    ))
    if result.scalar() == 0:
        await db.execute(text(f"ALTER TABLE tages_zusammenfassung ADD COLUMN {col} {coltype}"))
```

### Schritt 3 — Klassifikationsfunktion

`energie_profil_service.py` — neue Funktion vor `aggregate_day()`:

```python
def _classify_tagestyp(
    strahlung_wh_m2: float | None,
    performance_ratio: float | None,
    pv_kwh: float,
    verbrauch_kwh: float,
    median_verbrauch: float | None,
) -> str:
    if median_verbrauch and verbrauch_kwh > 2 * median_verbrauch:
        return "anomalie"
    if strahlung_wh_m2 is not None:
        if strahlung_wh_m2 >= 4000:  return "sonnentag"
        if strahlung_wh_m2 >= 1500:  return "mischtag"
        return "schlechtwetter"
    if performance_ratio is not None:
        if performance_ratio >= 0.65: return "sonnentag"
        if performance_ratio >= 0.25: return "mischtag"
        return "schlechtwetter"
    return "mischtag"
```

Einbindung in `aggregate_day()` beim Schreiben der `TagesZusammenfassung` (ca. Zeile 270):

```python
tz.tagestyp = _classify_tagestyp(
    strahlung_wh_m2=strahlung_summe,
    performance_ratio=tz.performance_ratio,
    pv_kwh=pv_kwh_summe,
    verbrauch_kwh=verbrauch_kwh_summe,
    median_verbrauch=None,  # Phase B: aus DB abfragen
)
```

### Schritt 4 — Analyse-Service-Funktion

`energie_profil_service.py` — neue Funktion nach `backfill_range()` (Zeile ~500):

```python
async def get_tagestyp_analyse(anlage_id: int, von: date, bis: date, db: AsyncSession) -> dict:
    """
    Gibt zurück:
    - verteilung: {sonnentag: N, mischtag: N, schlechtwetter: N, anomalie: N}
    - profile: {tagestyp: [{stunde, pv_p25, pv_p50, pv_p75, verbrauch_p25, ...}, ...]}
    """
    # 1. TagesZusammenfassung im Zeitraum → Verteilung + Tage-je-Typ
    # 2. Für jeden Typ: TagesEnergieProfil-Stunden laden
    # 3. Per Stunde: numpy.percentile([25, 50, 75]) auf pv_kw, verbrauch_kw, netzbezug_kw, batterie_kw
```

### Schritt 5 — Pydantic Models + Endpoint

`energie_profil.py` — nach Zeile ~156:

```python
class StundenPerzentile(BaseModel):
    stunde: int
    pv_p25: float | None; pv_p50: float | None; pv_p75: float | None
    verbrauch_p25: float | None; verbrauch_p50: float | None; verbrauch_p75: float | None
    netzbezug_p25: float | None; netzbezug_p50: float | None; netzbezug_p75: float | None
    batterie_p25: float | None; batterie_p50: float | None; batterie_p75: float | None

class TagestypProfil(BaseModel):
    tagestyp: str; anzahl: int; stunden: list[StundenPerzentile]

class TagestypAnalyseResponse(BaseModel):
    verteilung: dict[str, int]
    profile: list[TagestypProfil]
    zeitraum_tage: int
```

Endpoint nach `wochenmuster` (Zeile ~356):

```python
@router.get("/{anlage_id}/analyse/tagestypen", response_model=TagestypAnalyseResponse)
async def get_tagestyp_analyse_endpoint(
    anlage_id: int, von: date = Query(...), bis: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
```

### Schritt 6 — TypeScript API-Client

`energie_profil.ts` — neue Interfaces + Methode:

```typescript
export interface StundenPerzentile {
  stunde: number;
  pv_p25: number | null; pv_p50: number | null; pv_p75: number | null;
  verbrauch_p25: number | null; verbrauch_p50: number | null; verbrauch_p75: number | null;
  netzbezug_p25: number | null; netzbezug_p50: number | null; netzbezug_p75: number | null;
  batterie_p25: number | null; batterie_p50: number | null; batterie_p75: number | null;
}
export interface TagestypProfil { tagestyp: string; anzahl: number; stunden: StundenPerzentile[]; }
export interface TagestypAnalyse {
  verteilung: Record<string, number>; profile: TagestypProfil[]; zeitraum_tage: number;
}
// in energieProfilApi:
getTagestypAnalyse: (anlageId: number, von: string, bis: string) =>
  apiGet<TagestypAnalyse>(`/energie-profil/${anlageId}/analyse/tagestypen?von=${von}&bis=${bis}`),
```

### Schritt 7 — Frontend: 3. Tab + AnalyseStatistik-Komponente

`EnergieprofilTab.tsx`:

**7a — Tab-Eintrag** (Tab-Switcher, Zeile ~450):
```tsx
{ key: 'analyse', label: 'Analyse & Statistik' }
```

**7b — Komponente `AnalyseStatistik`** (vor Export, nach Zeile ~442):

- **Abschnitt 1 — Verteilung:**
  - Zeitraum-Selector: 30 / 90 / 180 / 365 Tage
  - `BarChart`: X = Tagestyp, Y = Anzahl Tage
  - Farben: sonnentag=#f59e0b, mischtag=#94a3b8, schlechtwetter=#6b7280, anomalie=#ef4444
  - Klartext: "In den letzten 90 Tagen: 28 Sonnentage (31%), 35 Mischtage (39%), ..."

- **Abschnitt 2 — Typisches Profil je Tagestyp:**
  - Tagestyp-Toggle (analog Wochentag-Toggle)
  - `ComposedChart`: Area für P25–P75-Band (niedrige Opacity) + Line für P50-Median
  - Getrennt: PV (grün) und Verbrauch (blau/rot)
  - Legende: "Schattierung = 50% der Tage liegen in diesem Bereich"

### Schritt 8 — Rückfüllung bestehender Daten

`energie_profil_service.py` — neue Utility-Funktion:

```python
async def backfill_tagestyp(db: AsyncSession):
    """Klassifiziert alle TagesZusammenfassung-Einträge ohne tagestyp (einmalig beim ersten Start)."""
    result = await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.tagestyp == None))
    for tz in result.scalars():
        tz.tagestyp = _classify_tagestyp(tz.strahlung_summe_wh_m2, tz.performance_ratio, ...)
    await db.commit()
```

Aufruf einmalig in `lifespan` (App-Start) mit Guard gegen Doppelausführung.
