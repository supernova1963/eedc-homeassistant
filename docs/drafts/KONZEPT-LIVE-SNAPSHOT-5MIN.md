# Konzept: Kaskadierte Live-Snapshots (5-Min heute, 1h historisch)

> Status: **Draft**, nicht implementiert. Trigger und Reife siehe §11.

## 1. Motivation

EEDC hat zwei parallele Pfade zur Berechnung von kWh-Werten:

1. **Snapshot-Pfad** (seit v3.19, Issue #135): kumulative Counter-Snapshots
   alle 60 Min in `sensor_snapshots`, Delta zwischen zwei Snapshots = exakte
   kWh im Intervall. Quelle für Auswertungen, Cockpit, Monatsberichte,
   Aussichten → Prognosen → IST.
2. **Power-Pfad** (älter, vor v3.19): Power-Sensor-History (W) per Trapezregel
   integriert oder zum Stunden-Mittelwert aggregiert. Quelle für Live-
   Tagesverlauf-Linie, Wetter-Widget IST-Stunden-Linie, 7-Tage-
   Verbrauchsprofil.

Die zwei Pfade weichen typisch um 1–3 % ab. HA-Power-Sensoren senden
„on-change" (bei Wertänderung), nicht im festen Sekundenraster — die
Trapezregel über ungleichmäßig verteilte Stützstellen weicht systematisch
vom Counter-Delta ab. Bei steilen Anstiegen/Abfällen mehr, im flachen Mittag
weniger.

### Auslöser

- **Rainer-PN (2026-04-30):** „IST-Kurve ist eine Prognose oder Mischung."
  Tatsächlich liest die Live-IST-Linie den Power-Sensor, der HA Energy
  Dashboard liest den kWh-Counter — 6,54 kW vs. 6,35 kWh = 3 % Drift im
  Stundenmittel. Aus Anwendersicht sieht das wie eine fabrizierte Linie aus.
- **Strategisch:** Der Drift macht es schwer, „IST = Realität" zu kommunizieren,
  und stützt den Eindruck einer Black-Box. Nicht-Power-basierte Quellen
  würden das Versprechen „eine Wahrheit, identisch mit HA" einlösen.
- **Nebeneffekt:** `live_verbrauchsprofil_service` lädt 7 Tage × 24 h
  Power-History für die Verbrauchs-Prognose-Linie — performance-relevant.

### Abgrenzung

**Nicht Teil dieses Konzepts:**

- **Live-Animation (5-s-Updates) im Energiefluss-Diagramm** — bleibt auf
  Power-Sensor. Counter-Delta auf 5 Sekunden ist zu grob (ein einzelnes
  Counter-Update kann Sprünge erzeugen). Klar getrennte Aufgaben:
  Power → Echtzeit-Animation, Counter → alles was in kWh kommuniziert wird.
- **MQTT-Inbound-Anlagen** — `mqtt_live_history_service` und
  `mqtt_energy_history_service` haben eigene Snapshot-Logik. Skizze
  überträgt sich konzeptionell, Implementierung ist separat.
- **15-Min-Strompreis-Slots** — können später aus 5-Min-Snapshots aggregiert
  werden (3 × 5 Min = 15 Min); kein Schema-Change nötig. Ist eigene
  Konzept-Skizze, falls Anwender-Wunsch entsteht.

---

## 2. Bestandsaufnahme

### Datenmodell heute

| Tabelle | Granularität | Lebensdauer | Quelle |
|---|---|---|---|
| `sensor_snapshots` (`zeitpunkt: DateTime`, `wert_kwh: Float`) | beliebig (Schema), heute 1h | dauerhaft | HA-Statistics + `:55`-Live-Preview |
| `tages_energie_profil` (`stunde: int 0-23`) | 1h | dauerhaft | aggregiert aus `sensor_snapshots` |
| `tages_zusammenfassung` (Tageswert pro Anlage) | 1d | dauerhaft | aggregiert aus `tages_energie_profil` |

**Entscheidend:** `SensorSnapshot.zeitpunkt` ist bereits ein `DateTime`, kein
hour-only-Feld. Das Schema verkraftet beliebige Sub-Stunden-Granularitäten
ohne Migration.

### Snapshot-Jobs heute

| Job | Trigger | Aufgabe |
|---|---|---|
| `sensor_snapshot_job` | `CronTrigger(minute=5)` (stündlich :05) | kumulative Zählerstände aus HA-Statistics in `sensor_snapshots` schreiben |
| `sensor_snapshot_preview_job` | `CronTrigger(minute=55)` (stündlich :55) | Live-Wert als Preview für laufende Stunde (Issue #146) |
| `energie_profil_heute_job` | `IntervalTrigger(minutes=15)` | `tages_energie_profil` für heute aus Snapshots neu aggregieren |
| `energie_profil_aggregation_job` | `CronTrigger(hour=0, minute=15)` | Vortag finalisieren |
| `energie_profil_aggregation_recovery_job` | `CronTrigger(hour=2, minute=15)` | Self-Healing für verspätete LTS-Counter (Issue #136) |

### Power-basierte Pfade (Audit-Ergebnis)

| # | Pfad | Datei | Nutzt Power-Sensor weil |
|---|---|---|---|
| 1 | Live-Tagesverlauf-Butterfly + Wetter-Widget IST-Stunden-Linie | `live_tagesverlauf_service.py` | 10-Min-Punkte (kein 1h-Snapshot in dieser Auflösung verfügbar) |
| 2 | 7-Tage-Verbrauchsprofil (Verbrauchs-Prognose-Linie + Werktag/WE-Muster) | `live_verbrauchsprofil_service.py` | historisch, nie umgestellt |

Die Heute-Tageswerte-Kacheln (Issue #64) lesen bereits priorisiert kWh-
Sensoren aus dem Monatsabschluss-Mapping; Power ist nur Fallback.

---

## 3. Vorschlag — kaskadierte Auflösung

### Idee

Counter-Snapshots in zwei Schichten halten, analog zu HA's
`statistics_short_term` (5-Min) + `statistics` (hourly):

| Schicht | Auflösung | Lebensdauer | Use Cases |
|---|---|---|---|
| **Live-Heute** | 5 Min | rolling 24 h, beim Tagesabschluss verdichtet | Live-Tagesverlauf-Linie, Wetter-Widget IST-Stunden-Linie, Live-Heute-Tooltips |
| **Historisch** | 1 h | dauerhaft | Aussichten, Auswertungen, Monatsberichte, Cockpit, Community |

Datenmenge im Steady-State: **~288 zusätzliche Rows aktiv** (1 Tag à 5-Min) +
historisch unverändert (24 Rows/Tag). DB-Wachstum = 1–2 % gegenüber heute.

### Eine Tabelle, zwei Granularitäten

`sensor_snapshots.zeitpunkt: DateTime` ist bereits granularitätsfrei. Konkret:

- 5-Min-Snapshots schreiben in dieselbe Tabelle, nur mit `zeitpunkt.minute ∈ {0,5,10,…,55}`
- Cleanup-Job löscht `zeitpunkt.minute != 0 AND zeitpunkt < jetzt - 24h`
- 1h-Snapshots (`minute == 0`) bleiben dauerhaft — bestehende Aggregations-
  Logik in `tages_energie_profil` arbeitet unverändert auf ihnen weiter

**Vorteil:** Kein neues Datenmodell, keine Migration für Bestandsanlagen.
Bestehender Snapshot-Code (`sensor_snapshot_service.snapshot_anlage`) wird
mit zusätzlichem Cron-Trigger aufgerufen. Counter-Robustheit (Reset-
Erkennung, `max(0, delta)`-Clamp) bleibt im selben Code-Pfad.

---

## 4. Datenmodell-Entscheidung

| Variante | Vorteil | Nachteil |
|---|---|---|
| **A: SensorSnapshot bleibt SoT, Cleanup-Job für Sub-Stunden-Slots** | kein Schema-Change, kein Code-Pfad-Split, Counter-Robustheit zentral | Tabelle wächst tagsüber 6× (288 statt 24 rows pro Anlage), wird abends auf 24 verdichtet |
| B: Neue Tabelle `live_snapshot_kurzfrist` mit `slot_index 0-287` | konzeptionell expliziter | Code-Doppelung, neue Migration, zwei Wege für Counter-Reset-Erkennung |
| C: TagesEnergieProfil um `slot_minute`-Spalte erweitern | Aggregat und Roh-Daten in einer Tabelle | TEP-Schema dreht sich um, alte Stundenwerte hätten `slot_minute=0`; Migration für Bestand mit `1h × 24` rows |

**Empfehlung: Variante A.** Minimale Eingriffstiefe, gleiche Counter-Logik
für 5-Min und 1h, Cleanup ist eine Single-Query.

---

## 5. Job-Schedule (Variante A)

| Job | Trigger | Was |
|---|---|---|
| `sensor_snapshot_5min_job` | `IntervalTrigger(minutes=5)` | Counter-Snapshots für laufenden Tag, schreibt `zeitpunkt = floor(now, 5min)` |
| `sensor_snapshot_job` | wie heute (`CronTrigger(minute=5)`) | unverändert — der :05-Snapshot ist auch ein 5-Min-Snapshot mit `minute=0` und bleibt dauerhaft |
| `sensor_snapshot_preview_job` | wie heute (`CronTrigger(minute=55)`) | unverändert |
| `sensor_snapshot_5min_cleanup_job` | `CronTrigger(hour=0, minute=30)` (täglich) | löscht Snapshots wo `minute != 0` und `zeitpunkt < jetzt - 24h` |
| `energie_profil_heute_job` | wie heute (`IntervalTrigger(minutes=15)`) | unverändert |
| `energie_profil_aggregation_job` | wie heute (`CronTrigger(hour=0, minute=15)`) | unverändert — aggregiert nur über `minute=0`-Snapshots |

Der **5-Min-Job ersetzt nichts**, er **ergänzt** den stündlichen `:05`-Job
um 11 zusätzliche Stützstellen pro Stunde. Der `:05`-Snapshot ist gleichzeitig
ein 5-Min-Slot — keine Doppel-Insertion (UniqueConstraint
`anlage_id, sensor_key, zeitpunkt` greift).

---

## 6. Restart-Recovery

Wenn EEDC um 14:23 startet, fehlen 5-Min-Slots 00:00–14:20 für heute.

**Lösung:** Init-Hook in `sensor_snapshot_service`, der beim Service-Start
die HA-Statistics-Short-Term-Auflösung (5 Min, default ~10–14 Tage) abfragt
und fehlende 5-Min-Slots des laufenden Tages backfillt. HA hält die Daten
ohnehin vor — wir fragen nur einmal beim Start.

Implementierung analog zu Issue #136 (Self-Healing für stündliche Snapshots),
nur mit `period: '5minute'` statt `period: 'hour'` in der HA-WebSocket-API
(`recorder/get_statistics`).

**Edge Case:** Wenn `state_class != total_increasing` für einen Sensor
gesetzt ist, sind weder hourly noch 5-Min in `statistics` verfügbar — der
Anwender hat kein Long-Term-Statistics-Tracking aktiviert. Verhalten heute:
Daten-Checker WARNING. Bleibt unverändert; 5-Min-Pfad funktioniert nur,
wenn 1h-Pfad funktioniert.

---

## 7. Verdichtungs-Garantie

Beim Tagesabschluss muss gelten:

```
SUM(5-Min-Delta(slot_h:00, slot_h:05, …, slot_h:55)) == 1h-Delta(snapshot_h:00, snapshot_(h+1):00)
```

**Trivial in der Theorie** (gleiche Counter-Quelle, gleicher Zeitraum).
**Test in der Praxis:** Synthetischen 24-h-Tag mit monoton steigendem
Counter durchsimulieren, beide Wege rechnen, Drift muss exakt 0 sein.
Test-Suite-Eintrag in `tests/test_sensor_snapshot_service.py`.

**Realer Edge Case:** Wenn der Counter zwischen zwei 5-Min-Slots resettet
(z.B. Wechselrichter über Nacht), klemmt der `:05`-Snapshot der nächsten
Stunde das Reset weg. Bei 5-Min-Auflösung sieht man den Reset im Bruchteil-
Slot — Reset-Erkennung muss konsistent zwischen 5-Min und 1h sein. Heute
in `_compute_delta` (sensor_snapshot_service): `max(0, current - previous)`.
Das funktioniert für beide Auflösungen, aber 5-Min hat 12× mehr Gelegenheiten,
einen kurzen Counter-Glitch (HA-Restart, Sensor-Aussetzer) zu sehen. Empirisch
in der Implementierungsphase prüfen.

---

## 8. Frontend-Änderungen

### `live_tagesverlauf_service.py`

Neuer Pfad: liest 5-Min-Snapshots aus `sensor_snapshots` für heute, berechnet
Delta zwischen aufeinanderfolgenden Slots, multipliziert mit 12 → kW-Mittelwert
pro 5-Min-Slot. Liefert das in `punkte`, wie heute.

Power-Sensor-Pfad bleibt als Fallback, wenn:
- Anlage keinen Counter-Sensor pro Komponente hat (häufig bei WP/Wallbox)
- 5-Min-Snapshots fehlen (Service frisch gestartet, Self-Healing läuft noch)

Frontend `WetterWidget.tsx` braucht keine Änderung — die `punkte`-Struktur
ist quellen-agnostisch.

### `live_verbrauchsprofil_service.py`

Liest historische 7 Tage × 24 h aus `tages_energie_profil` statt
Power-History. Für *heute* nutzt es 5-Min-Snapshots, für gestern und älter
die stündlichen Snapshots.

Performance-Vorteil: 7 × 24 = 168 DB-Reads + 1× 5-Min-Read statt 7 Tage
HA-History-API-Call mit allen Power-Punkten.

---

## 9. Performance & Footprint

| Ressource | Heute | Mit 5-Min-Schicht | Faktor |
|---|---|---|---|
| HA-API-Calls (Snapshots) pro Anlage/h | 1 | 12 | 12× |
| DB-rows aktiv (Sub-Stunden) | 0 | ~288 | — |
| DB-rows historisch pro Anlage | 24/Tag | unverändert | 1× |
| Aktiv-Storage Single-Anlage | ~50 KB | ~50 KB + ~12 KB transient | +25 % transient |
| L1/L2-Cache-Invalidierung | 1×/h | 12×/h für „heute"-Aggregate | 12× |

Die HA-Last (12 Statistics-Calls/h) ist auf einer einzelnen Anlage
unauffällig. Bei einer hypothetischen Multi-Anlagen-Instanz mit 100
Anlagen wären es 1200 Calls/h — kann man dann immer noch auf einen
Sammel-Call pro 5-Min-Slot bündeln (`get_statistics(start, end, sensor_ids)`
arbeitet bereits batch-fähig).

L1/L2-Cache: aktuelle Aggregate fürs heutige Datum müssen 5-Min
invalidiert werden. Cache-TTL für „heute" auf ≤5 Min senken oder
Cache-Key um `floor(jetzt, 5min)` ergänzen.

---

## 10. Migration

**Kein Schema-Change** (Variante A). Konkret:

1. Neuer 5-Min-Cron-Job ergänzt
2. Neuer Cleanup-Job (täglich :30)
3. Self-Healing-Init-Hook
4. Feature-Flag `LIVE_SNAPSHOT_5MIN_ENABLED` (default: aus) — schaltbar in
   Anlage-Einstellung oder Add-on-Config
5. Tagesverlauf-/Verbrauchsprofil-Service liest neuen Pfad nur, wenn Flag an
   und 5-Min-Snapshots vorhanden; sonst Power-Pfad

**Bestandsdaten:** unverändert. Stündliche Snapshots bleiben, historische
Tagesverlauf-Linien rendern weiterhin aus Power-History (nur „heute"
profitiert von 5-Min, alte Tage waren schon immer stundengenau in EEDC und
HA Energy Dashboard).

**Roll-out:** Flag aus → an, mehrere Tage Beobachtung mit Winterborn als
Test-Anlage. Wenn Drift gegen HA Energy Dashboard = 0 und keine
Counter-Glitch-Häufungen, Default auf an.

---

## 11. Trigger / Wann umsetzen

**Kurzfristig priorisiert.** Auslöser-Update 2026-04-30: Rainer (einer der
aktivsten Tester) hat seine Energieprofil-Daten gelöscht „weil die eh
falsch sind" und Drift-Screenshots geliefert. Das ist nicht *eine
Beschwerde*, sondern verlorenes Vertrauen beim Power-User — qualitativ
schwerwiegender als die nominellen 1–3 % Drift. Im HA-Add-on-Kontext ist
HA Energy Dashboard die Referenz; jede Abweichung von dort wirkt wie ein
Bug, unabhängig von der theoretischen Korrektheit des Power-Pfads.

**Strategischer Hintergrund:** Live-Dashboard war v3.0 ein Nebenfeature
mit einer gerade-noch-tragbaren Aggregations-Implementierung. Es ist seit
v3.9 (Generalüberholung) das prominenteste Feature der App. Die alten
Hack-Entscheidungen sind unter dieser neuen Sichtbarkeit als
Qualitätsschuld zu werten.

**Reihenfolge:**

1. **Phase 0 (sofort):** Rainer-PN-Antwort mit der ehrlichen Drift-Erklärung
   (power-vs-energy-Sensor) — nimmt akuten Vertrauens-Druck, kostet keine
   Code-Änderung. Fertig formuliert in dieser Session.
2. **Phase 1 (1–2 Wochen):** Variante A implementieren, Feature-Flag default
   aus, Winterborn als Test-Anlage. Drift gegen HA Energy Dashboard messen,
   Counter-Glitch-Häufigkeit beobachten.
3. **Phase 2 (nach ~1 Woche Beobachtung):** Feature-Flag default an, Release-
   Notes mit „IST-Werte sind jetzt 1:1 mit HA Energy Dashboard" — das ist
   die kommunikativ wichtige Aussage.
4. **Phase 3 (später):** `:55`-Preview entfernen (durch 5-Min obsolet),
   `live_verbrauchsprofil_service` umstellen.

**Vor Phase 1 zu klären:**

- 5-Min-Pfad für alle Sensor-Typen oder nur PV? (Empfehlung: alle, sonst
  bleibt Drift bei WP/Wallbox/Speicher und wir lösen das Problem nur halb.)
- Welche Counter-Glitch-Quote zeigt Winterborn empirisch über die
  Phase-1-Beobachtungswoche?
- Brauchen wir Anwender-sichtbare Statusanzeige „Live-Datenpfad: Counter /
  Power-Fallback", damit Anwender ohne Counter-Mapping wissen, warum sie
  weiter Drift sehen?

---

## 12. Out of Scope (Klarstellung)

- **Live-Animation-Frequenz** bleibt 5 s aus Power-Sensor.
- **Kein neues Datenmodell** in v1. Variante A explizit gewählt.
- **Keine 5-Min-Auflösung für historische Tage** — Storage-Argument greift
  nicht (Linie wäre kosmetisch besser, Anwender-Nutzen marginal, HA Energy
  Dashboard kann es selbst auch nicht).
- **Keine MQTT-Inbound-Anpassung in v1.** Eigene Refactoring-Welle.
- **Strompreis-15-Min-Aggregation** — separates Konzept, kein Blocker hier.

---

## Anhang: Verweise

- Audit-Tabelle Power-Trapez vs. Snapshot — Memory-Eintrag
  `project_konvention_refactor_v320.md` (v3.20-Bündel) erweitern, sobald
  dieses Konzept umgesetzt
- Issue #135 — Energieprofil Snapshot-Rework (Phase A–D), Grundlage
- Issue #136 — Snapshot-Restart-Recovery + Self-Healing, Vorlage für 5-Min-Recovery
- Issue #146 — :55-Preview, ggf. obsolet nach 5-Min-Roll-out
- Rainer-PN 2026-04-30 — Auslöser
- HA-Doku: `recorder.statistics_short_term`, 5-Min-Slots, default ~10–14 Tage
