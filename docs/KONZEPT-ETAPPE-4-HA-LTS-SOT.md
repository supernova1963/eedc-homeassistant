# Konzept Etappe 4 — HA-Statistics-LTS als Source-of-Truth

**Status:** Konzept-Phase, 2026-05-16
**Ziel-Release:** v3.31.0 (Major-vs-Patch siehe Abschnitt 9)
**Trigger:** Rainer-PN 2026-05-16 mit drei Werten für 15.05.2026 PV-Erzeugung (72,1 / 67 / 64,49 kWh) aus drei Berechnungspfaden.
**Vorgänger-Etappen:** Etappe 3 (v3.19, kWh aus Counter-Snapshots) hat den Grundstein gelegt, aber die Daily-/Hourly-Aggregat-Tabellen blieben dual-source.

## 1. Problem

### 1.1 Drei Werte für denselben Tag

| Sicht | Wert | Quelle |
|---|---|---|
| Genauigkeits-Tracking IST | 72,1 kWh | `Σ komponenten_kwh[v > 0, k ∉ {strompreis, netzbezug, einspeisung}]` |
| Tages-Energieprofile → PV-Ertrag | 67 kWh | `Σ komponenten_kwh[pv_*, bkw_*]` (HA-konformes Tagesfenster aus `get_komponenten_tageskwh()`) |
| Monatsbericht-Energieprofil → Σ Stunden | 64,49 kWh | `Σ TagesEnergieProfil.pv_kw` (24 Stunden-Snapshots aus `kwh_pro_stunde`) |

### 1.2 Drift-Hot-Spots

1. **Bug Genauigkeits-Tracking** (`backend/api/routes/prognosen.py:640-644`): Filter `v > 0 and k not in {strompreis, netzbezug, einspeisung}` schließt Batterie-Netto-Ladung nicht aus. An Tagen mit netto positiver Batterie-Ladung wird das fälschlich als „IST-Erzeugung" mitgezählt. **5 kWh Drift** bei Rainer.

2. **Aggregations-Fenster-Versatz**: `komponenten_kwh` wird in `services/snapshot/aggregator.py:431` aus `get_komponenten_tageskwh()` befüllt — HA-konformes Tagesfenster `[00:00, Folgetag 00:00)`. `TagesEnergieProfil.pv_kw` dagegen wird aus 24 Stunden-Snapshots (`kwh_pro_stunde`) befüllt — Boundary-Snapshots zwischen voller Stunde, mit Sub-Stunden-Lücken-Interpolation. Beide aus derselben Counter-Tabelle, aber unterschiedliche Boundaries → **2,5 kWh Drift** bei Rainer.

3. **Dual-Source-Drift bei Quellenwechsel**: Snapshot-Reader hat Self-Healing-Fallback (HA-LTS direkt) wenn `sensor_snapshots`-Tabelle Lücken hat. Live-Cron schreibt aus `kwh_pro_stunde`, Backfill schreibt aus HA-LTS direkt — laufzeitabhängig, welcher Pfad gewinnt.

### 1.3 Was Etappe 3 nicht zu Ende geführt hat

Etappe 3 (v3.19) hat **kWh aus Counter-Snapshots statt Power-Integration** etabliert (`sensor_snapshots`-Tabelle, Boundary-Diff). Das war ein massiver Schritt weg von Riemann. ABER:

- Snapshot-Boundary ist per-Stunde, nicht per-Tag — sub-stunden-Drift bleibt
- HA-LTS-Hourly direkt zu lesen wäre einfacher und konsistenter als per-Stunde-Self-Healing
- `komponenten_kwh` (Daily) und `pv_kw`-Σ (Hourly aufsummiert) müssen dieselbe Counter-Truth haben — heute nicht garantiert

## 2. Architektur-Ziel

### 2.1 Source-of-Truth-Hierarchie

```
HA-Statistics-LTS (kumulative Counter pro Entity, hourly + daily)
       ↓ (Cache-Refresh)
TagesEnergieProfil (Stunden) + TagesZusammenfassung (Tage)
       ↓ (Read)
UI-Sichten (Cockpit, Energieprofil, Genauigkeits-Tracking, Heatmap, Lernfaktor, …)
```

**Prinzip:** Sichten lesen aus den Aggregat-Tabellen wie bisher. Die Aggregat-Tabellen werden aber ausschließlich aus HA-LTS gefüllt — keine parallele Riemann-Integration, keine Sub-Stunden-Boundary-Interpretation mehr.

### 2.2 Standalone-Fallback (eedc ohne HA-Add-on)

Wenn keine HA-Verfügbarkeit:
- Pfad 1: MQTT-Cache (`MqttEnergySnapshot`) liefert kumulative Counter analog zu HA-LTS-Hourly
- Pfad 2: Live-Tagesverlauf-Service als letzter Fallback (Riemann)

Pfad 2 wird in der UI als „eingeschränkte Genauigkeit" markiert (Provenance-Source `fallback:tagesverlauf_riemann`).

### 2.3 Schreib-Provenance erweitern

Neue Source-Labels in `backend/core/source_priority.py`:

- `external:ha_statistics:hourly` — Stundenwerte aus HA-LTS für `TagesEnergieProfil.*_kw` (Priorität: EXTERNAL_AUTHORITATIVE)
- `external:ha_statistics:daily` — Tagessumme aus HA-LTS-Daily für `TagesZusammenfassung.komponenten_kwh` (Priorität: EXTERNAL_AUTHORITATIVE)

Bestehendes `external:ha_statistics` (Priorität EXTERNAL_AUTHORITATIVE) bleibt für punktuelle Lese-Operationen (Snapshot-Self-Healing).

## 3. Inventar der betroffenen Pfade

### 3.1 Write-Pfade — werden umgestellt

| Pfad | Datei:Zeile | Heute | Etappe 4 |
|---|---|---|---|
| `aggregate_day()` Stundenwerte | `services/energie_profil/aggregator.py:344-369` | `kwh_pro_stunde` aus Snapshot-Boundary-Diff | HA-LTS-Hourly direkt lesen (`get_statistics_during_period` mit Stunden-Auflösung) |
| `aggregate_day()` Tageszusammenfassung | `services/energie_profil/aggregator.py:430-465` | `get_komponenten_tageskwh()` aus HA-konformem Boundary-Diff | HA-LTS-Daily direkt lesen (`sum_during_period` mit Tag-Resolution) |
| `backfill_from_statistics()` | `services/energie_profil/backfill.py:563-637` | Liest schon HA-LTS, schreibt aber in dieselben dual-source-anfälligen Spalten | Identisch, aber jetzt alleiniger Schreiber; Riemann-Pfad entfällt |
| `monatsabschluss_aggregator.py` | `services/monatsabschluss_aggregator.py:53-126` | Ruft `backfill_range()` → `aggregate_day()` | Bleibt strukturell gleich, nur Datenquelle wechselt |

**Was bleibt:** Die `seed_tep_provenance()`- und `seed_tz_provenance()`-Aufrufe, die Audit-Log-Logik, die Upsert-Semantik (delete+insert pro Tag).

### 3.2 Read-Pfade — Bug-Fix + Vereinheitlichung

| Pfad | Datei:Zeile | Heute-Bug | Fix |
|---|---|---|---|
| Genauigkeits-Tracking IST | `routes/prognosen.py:640-644` | `sum(v for k,v if v > 0 and k not in NICHT_PV)` zählt Batterie-Netto-Ladung mit | Prefix-Filter `pv_*` + `bkw_*` analog zu `EnergieprofilTageTabelle.tsx:93` |
| Tages-Energieprofile-Tabelle | Frontend `EnergieprofilTageTabelle.tsx:93` | `sumKomponentenKwhByPrefix(['pv_', 'bkw_'])` — korrekt | Keine Änderung, ist die Referenz-Aggregation |
| Monatsbericht-Stunden-Σ | `routes/energie_profil/views.py` | Σ aus `TagesEnergieProfil.pv_kw` | Nach Etappe 4 = identisch mit Tages-Energieprofile, weil beide aus HA-LTS |

### 3.3 Standalone-Pfade — bleiben funktional

| Pfad | Heute | Etappe 4 |
|---|---|---|
| MQTT-Cache-Read in `snapshot/aggregator.py:138-170` | Liest `MqttEnergySnapshot`-Keys für Fallback-Sensor-Enumeration | Bleibt, wird zu Pfad 1 (siehe 2.2) |
| Live-Tagesverlauf-Service als Fallback | `live_history_service.py:74-113` — Riemann | Bleibt explizit als Pfad 2 mit UI-Markierung |

### 3.4 Reaggregation/Repair — strukturell gleich

| Endpoint | Heute | Etappe 4 |
|---|---|---|
| `POST /reaggregate-heute` | Live-Riemann + Snapshot-Mix | Cache-Refresh aus HA-LTS |
| `POST /reaggregate-tag` | `aggregate_day()` mit optionalem `mit_resnap` | `mit_resnap` wird obsolet (HA-LTS ist immer frisch); Parameter bleibt no-op für API-Stabilität |
| `POST /reaggregate-bereich` | `backfill_range()` über Datumsbereich | Identisch, neue Datenquelle |
| `POST /vollbackfill` | Liest schon aus HA-LTS, schreibt additiv | Identisch |

## 4. Migrations-/Reaggregations-Plan

### 4.1 Bestehende Daten

Existierende `TagesEnergieProfil`- und `TagesZusammenfassung`-Rows sind aus Mix-Quellen befüllt. Optionen:

- **A) Hands-off**: Bestehende Rows bleiben, neue Tage werden ab v3.31.0 aus HA-LTS gefüllt. Alte Tage zeigen Drift weiter. Tester können punktuell „Tag neu aggregieren".
- **B) Auto-Migration**: Beim ersten Start nach v3.31.0 lokal Reaggregation aller Tage seit Anlageninstallation aus HA-LTS. Großer Job (kann Minuten dauern), aber heilt alles.
- **C) Per-Anlage-Auto-Vollbackfill**: Setzt `vollbackfill_durchgefuehrt = False` bei v3.31.0-Migration. Beim nächsten Monatsabschluss läuft Auto-Vollbackfill (Hands-off-Wahl an für aktive Nutzer).

**Empfehlung:** C — minimal-invasiv, nutzt den bestehenden Auto-Vollbackfill-Mechanismus, Anwender muss nicht aktiv werden, kein Riesen-Job bei Start.

### 4.2 Standalone-Daten

Anlagen ohne HA-Integration: keine Migration nötig, MQTT-Pfad bleibt aktiv.

### 4.3 Sensor-Mapping-Sanity-Check

Vor erstem Cache-Refresh prüfen: sind alle Counter-Sensoren in `sensor_mapping` als `total_increasing` deklariert und in HA-LTS verfügbar? Falls nein, Pfad 2 (Riemann-Fallback) mit Provenance-Marker.

## 5. Bug-Fix Genauigkeits-Tracking (Parallel-Lieferung)

Unabhängig vom Etappe-4-Hauptweg: der Filter in `routes/prognosen.py:640-644` wird auf `pv_*`/`bkw_*`-Prefix umgestellt — direkter Bug-Fix, ohne Architektur-Wandel.

```python
# Vorher:
ist_kwh = sum(v for k, v in tz.komponenten_kwh.items()
              if v > 0 and k not in _NICHT_PV)
# Nachher:
ist_kwh = sum(v for k, v in tz.komponenten_kwh.items()
              if v > 0 and (k.startswith('pv_') or k.startswith('bkw_')))
```

Test: ein Tag mit positiver Batterie-Netto-Ladung muss in `ist_kwh` ohne Batterie-Anteil rauskommen.

Dieser Fix gehört in v3.31.0 als erstes Commit — heilt sofort die 5-kWh-Drift bei Rainer-Setup-ähnlichen Anlagen, unabhängig von der größeren Etappe-4-Lieferung.

## 6. Implementierungs-Reihenfolge

1. **Bug-Fix Genauigkeits-Tracking** — 1 Commit, 5 Zeilen + Test
2. **Neue Provenance-Labels** in `source_priority.py` — 1 Commit
3. **HA-LTS-Hourly-Reader** in `services/ha_statistics_service.py` — neue Funktion `get_hourly_aggregated_kwh_by_category(anlage, datum)` analog zu bestehender `get_hourly_kwh_by_category` (aus Snapshots)
4. **Aggregator-Pfad-Umstellung** in `services/energie_profil/aggregator.py` — `kwh_pro_stunde` wird optional bevorzugt durch HA-LTS-Hourly, mit MQTT-Fallback
5. **Standalone-Fallback-Path** dokumentieren + UI-Marker
6. **Migration-Trigger** in DB-Migration-Schritt — `vollbackfill_durchgefuehrt = False` für alle Anlagen mit HA-Integration
7. **Tests** — siehe Abschnitt 7
8. **Manueller QS** in HA-App nach Release

## 7. Test-Plan

### 7.1 Unit-Tests

- `test_ha_lts_hourly_reader.py` — Liest HA-LTS-Stundenwerte korrekt, behandelt Lücken, Caps Counter-Resets
- `test_aggregate_day_etappe4.py` — `aggregate_day()` mit HA-LTS-Source schreibt konsistente Werte in `pv_kw` und `komponenten_kwh.pv`
- `test_aggregate_day_standalone_fallback.py` — Ohne HA-Verfügbarkeit greift MQTT-Pfad, ohne MQTT greift Riemann-Pfad mit Marker
- `test_genauigkeit_pv_only.py` — IST-Wert enthält keine Batterie-Anteile mehr
- `test_prov_labels_lts_hourly.py` — Neue Source-Labels werden korrekt geschrieben + von Resolver respektiert

### 7.2 Konsistenz-Tests (Etappe 4 Kern)

- Drei Sichten für denselben Tag müssen denselben PV-Wert liefern:
  - `Σ komponenten_kwh[pv_*, bkw_*]` (TagesZusammenfassung)
  - `Σ TagesEnergieProfil.pv_kw` (24 Stunden)
  - Genauigkeits-Tracking IST

### 7.3 Migrations-Tests

- v3.30.x → v3.31.0 Upgrade-Simulation: `vollbackfill_durchgefuehrt = False`, Auto-Vollbackfill beim nächsten Monatsabschluss läuft korrekt durch

### 7.4 Performance

- HA-LTS-Hourly-Read für 1 Anlage 30 Tage darf nicht länger als bisheriger Snapshot-Read dauern (Benchmark)
- Auto-Vollbackfill bei 2-Jahres-Datenbestand muss in <2 Minuten durchlaufen

## 8. Standalone-Modus — explizite Definition

eedc läuft in drei Modi:

1. **HA-Add-on-Modus**: HA-LTS verfügbar. Etappe-4-Pfad voll aktiv. Source `external:ha_statistics:hourly/daily`.
2. **Docker-Standalone mit HA**: HA über Netzwerk erreichbar via `HA_URL` + LLT. Identisch zu 1.
3. **Docker-Standalone ohne HA**: Pfad 1 (MQTT-Cache) + Pfad 2 (Riemann-Fallback). UI zeigt „eingeschränkte Genauigkeit"-Badge in betroffenen Sichten.

Modus-Erkennung über existierende `HA_AVAILABLE`-Flag in `core/config.py`.

## 9. Major-vs-Patch — Release-Strategie

### Argument für Major (v3.31.0)

- Architektur-Wandel der Datenpipeline (Cache statt Live-Berechnung)
- Bestehende Werte können sich bei aktiven Anlagen leicht ändern (innerhalb Drift-Toleranz)
- Neue Provenance-Labels in Source-Vokabular
- Auto-Vollbackfill-Trigger bei Upgrade

### Argument für Patch (v3.30.4)

- Sicht-Werte werden konsistent, nicht „anders"
- Schreib-Provenance-Hierarchie unverändert
- Keine API-Breaking-Changes

**Entscheidung:** Nach Implementation. Wenn die migrierten Werte bei den vier Test-Anlagen (HA-Add-on, Standalone-Docker mit/ohne HA, Demo) sichtbar abweichen → v3.31.0. Wenn drift-frei → v3.30.4 möglich.

## 10. Risiken

| Risiko | Wahrscheinlich | Schwere | Gegenmaßnahme |
|---|---|---|---|
| HA-LTS-Hourly-Performance bei großen Anlagen | mittel | mittel | Read-Cache + Batch-Window (1 Monat pro Read) + Performance-Tests in Akzeptanz |
| Counter-Resets in HA-LTS nach Sensor-Tausch | mittel | hoch | Plausibility-Cap aus v3.30.2 erweitern auf HA-LTS-Pfad |
| Bestehende manuell gepflegte `komponenten_kwh`-Subkeys werden überschrieben | niedrig | hoch | Provenance-Hierarchie: `manual:*` ist unverhandelbar (FrodoVDR-Fix v3.30.3) |
| Standalone-User bricht durch Pfad-2-Riemann-Drift | niedrig | mittel | UI-Marker + Hilfe-Doku |
| Migration läuft nicht durch (HA-LTS-Lücken) | mittel | mittel | Per-Tag-Commit, robuste Fehlerbehandlung, klare Fehlermeldungen im Daten-Checker |

## 11. Akzeptanz-Kriterien

- [ ] Drei Sichten (Genauigkeits-Tracking IST, Tages-Energieprofile PV-Ertrag, Monatsbericht-Stunden-Σ) zeigen identischen Wert für denselben Tag (innerhalb <0,1 kWh Round-Tolerance)
- [ ] Bug Batterie-im-IST ist gefixt (Test bestanden)
- [ ] Standalone-Modus ohne HA funktioniert mit Pfad-Marker
- [ ] Auto-Vollbackfill nach v3.31.0-Upgrade läuft durch ohne Datenverlust
- [ ] Performance: kein Sicht-Endpoint mehr als 1,5× langsamer als vorher
- [ ] Alle bestehenden Tests grün (86+)
- [ ] Neue Tests grün (siehe Test-Plan)

## 12. Verbundene Memory-Linien

- [[etappe-4-ha-lts-sot]] — Memory-Projekt-Eintrag mit Status-Tracking
- [[user_rainer]] — Auslöser, verloren wegen genau dieser Drift
- [[feedback_aggregations_drift]] — zentraler Helper statt Einzel-Patch (selbe Linie)
- [[feedback_grenze_externe_daten_diagnose]] — eedc fixt eigene Logik konsequent

## Anti-Pattern dokumentiert

**„Eine Etappe nicht zu Ende ziehen"** — Etappe 3 (v3.19) etablierte kWh-aus-Counter-Snapshots, aber die Aggregat-Tabellen blieben aus zwei Boundary-Modellen (HA-konformes Tagesfenster vs Per-Stunde-Snapshot) befüllt. Das war keine vergessene Stelle, sondern eine ganze nicht-durchgezogene Schicht. Bei künftigen Architektur-Etappen: vollständiges Inventar **vor** Implementation, Sicht-Konsistenz als explizites Akzeptanz-Kriterium.
