# Konzept: EEDC-Lernfaktor — Optimierung und Korrekturprofile

> **Status (2026-05-10):** Päckchen 1+2 (Wetter-Layer + O1+O2-Doppel-Variante + stündliches
> Korrekturprofil mit Sonnenstand × Wetter im Live-Pfad) ✅ **ausgeliefert in v3.26.0–v3.26.2**
> (Commits 06558529, 6fc92681). Skalar-Hotfix in v3.26.3, Wetter-Backfill-Hotfix v3.26.4.
> O1 Recency-Boost und O2 Trim-Mean laufen aktuell **parallel zum Legacy-Skalar als
> Diagnose**; Live-Pfad nutzt weiter Legacy. Beobachtungs-Phase läuft seit 2026-05-06
> (Tag 4 von „mehreren Wochen"). **O1+O2-Default-Aktivierung erfolgt frühestens
> nach v3.27.0 und nach Abschluss der empirischen Beobachtung** — Tag 4 ist zu
> früh, eine Aktivierung jetzt würde gegen das eigene Konzept verstoßen.
> Variante A (Anlagenspezifisches Stunden-Korrekturprofil pro Saisonbin) bleibt
> reaktiv — Trigger sind Diagnose-Daten aus der Wetter-Stratifizierung. Variante v1
> archiviert in [`archive/KONZEPT-KORREKTURPROFIL-v1-2026-05-03.md`](archive/KONZEPT-KORREKTURPROFIL-v1-2026-05-03.md).
>
> **Strenger Grundsatz:** Diese Doku enthält **keine Vergleiche** mit
> Tom-HA-SFML, Solcast oder anderen externen Quellen. Der Lernfaktor ist
> EEDC-internes Engineering. Wir haben Tom-HA versprochen, nicht gegen
> „rolling" zu vergleichen — das gilt auch für interne Konzept-Dokumente.
>
> **Gehört zusammen mit:** [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md)
> (separates Konzept-Dokument, das die Quellenwahl-Architektur abbildet —
> dort ist EEDC eine von drei Quellen).

## Motivation

EEDC ist die Default-Quelle für jede Anlage (siehe Quellenwahl-Konzept) —
und damit die Quelle, die *immer* funktioniert (auch ohne HA-Integration,
auch im Standalone). Damit der Default robust und konsistent gut ist,
muss der EEDC-Lernfaktor saisonale Effekte sauber ausgleichen und
Ausreißer-Tage abfangen.

Heutiger Skalar-Lernfaktor in
[`live_wetter.py:_get_lernfaktor_detail`](../eedc/backend/api/routes/live_wetter.py)
hat bekannte Grenzen — siehe Bestandsaufnahme.

## Bestandsaufnahme — heute

### Skalarer Lernfaktor

```text
_berechne_faktor(tage, db_feld) → Σ(IST) / Σ(Prognose), produktionsgewichtet
  Filter pro Tag: Prognose > 0.5 kWh AND IST > 0.5 kWh

Saisonale Kaskade:
  1. Monat   (gleicher Kalendermonat alle Jahre, ≥15 Tage)
  2. Quartal (gleiches Q1-Q4 alle Jahre, ≥15 Tage)
  3. Gesamt  (letzte 30 Tage rollierend, ≥7 Tage)
  Sonst: kein Faktor

Clamp [0.5 ; 1.3], runden auf 3 Nachkommastellen, Cache pro (anlage, quelle).
```

### Was der Skalar gut kann

- Pauschale Anlagen-Eigenarten (allgemeine Modul-Degradation,
  WR-Wirkungsgrad, systematischer GTI-Bias der Wetterquelle)
- Saisonale Verschiebung über Sonnenstand-Höhe (April vs. Dezember)

### Was der Skalar nicht kann

- **Verschattung im Tagesverlauf:** Baum/Gebäude/Geländekante schluckt
  morgens oder abends einen Teil der Strahlung. Tagessumme fällt z. B.
  um 5 % → Faktor geht auf 0.95. Aber: Live-Dashboard skaliert *alle*
  Stunden mit 0.95 — die betroffenen Stunden bräuchten 0.5, die
  unbetroffenen 1.0. Tagessumme stimmt rechnerisch, das Stundenprofil
  nicht.
- **String-spezifische Effekte:** Ostflügel verschattet, Westflügel
  nicht. Mit einem Anlagen-Skalar werden beide gleich behandelt.
- **Wetterabhängige Asymmetrie:** Bei klarem Himmel wirkt Verschattung
  stark, bei diffuser Strahlung kaum — wird aktuell nicht differenziert.

## Skalar-Heuristiken (O1, O2, O3)

Drei Heuristiken, die den Skalar ohne Schema-Änderung robuster machen.
Status revidiert: O1+O2 jetzt umsetzbar **als zweite Variante neben dem
Legacy-Skalar**, nicht als Ersatz. Doppel-Berechnung Legacy / O12 →
empirischer Beleg für oder gegen die Aktivierung als neuer Default.
Methodisch sauber, weil gleiche Tage gleichbewertet werden.

**Wichtig:** Doppel-Vergleich Legacy/O12 ist EEDC-intern — kein
Quellenvergleich. Kompatibel mit dem Tom-HA-Versprechen.

### O1 — Recency-Boost

**Problem:** Saisonbins mitteln über mehrere Wochen bis Monate.
Schleichende Veränderungen (Modul-Verschmutzung, wachsende Bäume, Sensor-
Drift) brauchen entsprechend lange, bis sie durchschlagen.

**Heuristik:** Tage jünger als 30 Tage erhalten +30 % Gewicht in der
Aggregation. Stärke und Schwellwert konservativ wählbar.

**Aufwand:** ~halber Tag. Eine Zeile in `_berechne_faktor`
(Produktionsgewichtung × Recency-Faktor).

**Risiko:** gering. Faktor weiterhin auf [0.5 ; 1.3] geclampt, Saisonbin-
Logik unverändert.

### O2 — Robuste Statistik gegen Ausreißer

**Problem:** Aktuell `Σ(IST) / Σ(Prognose)` produktionsgewichtet. Ein
einzelner Tag mit defektem Sensor, MQTT-Aussetzer oder Snapshot-Lücke
zerrt den Faktor messbar.

**Heuristik:** Vor der Summation die Tagesquotienten `IST_d / Prognose_d`
trimmen — z. B. 10 %-getrimmter Mittelwert (oberste/unterste 10 % der
Tage werden verworfen, Rest gewichtet aggregiert).

**Aufwand:** ~halber Tag. Sortier-Schritt + Slicing in `_berechne_faktor`.

**Risiko:** gering bis null. Bei sauberem Datenbestand identisch zum
heutigen Mittel; bei Ausreißern systematisch besser.

### O3 — Schneeerkennungs-Heuristik (Dez–Feb)

**Problem:** Bei Schneebedeckung produziert die Anlage kaum Strom, das
GTI-Signal aus der Wettervorhersage ist aber „sauberer Sonnentag". eedc
überschätzt systematisch, der Lernfaktor reagiert mit ~30 Tagen Lag.

**Heuristik:** Im Fenster Dez–Feb prüfen: wenn die letzten 2–3 Tage
`IST/Prognose < 30 %` bei klarem GHI (Cloud-Coverage < 30 %), Penalty
50 % auf nächstes-Tag-Prognose ansetzen, bis IST/Prognose wieder > 70 %.

**Aufwand:** mittel. Eigene Detection-Funktion + State im Cache (welche
Anlage „im Schnee-Modus"). UI-Hinweis im Live-Dashboard sinnvoll.

**Risiko:** mittel. Schwellwerte sind heuristisch, falsch ausgelöste
Penalty ist schlimmer als fehlende. Sollte erst nach mindestens einem
Winter-IST-Vergleich an drei Anlagen scharfgeschaltet werden.

**Reihenfolge:** O2 zuerst (geringeres Risiko), O1 zwei Wochen später,
beide parallel zur Legacy-Berechnung tracked. O3 als eigenes Issue,
nach Winter 2026/27.

## Wetter-Stratifizierung — Diagnose und Korrektur-Dimension

EEDC-Lernfaktor wird nach Wetter-Klasse (klar / diffus / wechselhaft)
ausgewertet — und die Wetterklasse fließt zusätzlich als eigene
Bin-Achse in das Korrekturprofil ein (siehe Ziel-Architektur unten).

- **Klassifikation pro Stunde** aus `bewoelkung_prozent` +
  `niederschlag_mm` + `wetter_code`, gespeichert in `TagesEnergieProfil`.
  Tagesklassifikation als Aggregat: dominante Klasse über die
  Tageslicht-Stunden, Schwellen siehe Klassifikations-Helper.
- Logik orientiert sich an der bestehenden
  [`wetter_symbol_aus_tag`](../eedc/backend/services/wetter/utils.py) —
  neue Funktion `klassifiziere_stunde()` reduziert auf 3 Klassen.
- Pro Klasse: separater MAE/MBE auf den letzten 30/90 Tagen,
  zusätzlich Stratifizierung pro Stunde.
- **Strikt EEDC-intern** — keine Quellen-Vergleichs-Statistik daneben.
- Doppelfunktion: (1) Diagnose-Sicht im Prognosen-Tab,
  (2) Bin-Achse in der Korrekturprofil-Tabelle.

## Prognosen-Tab als Übergangs-Diagnose

Aktueller Prognosen-Tab läuft weiter mit **optimiertem EEDC + Wetter-
Stratifizierung**. Andere Quellen (Solcast, SFML) werden in dieser Tab-
Sicht nicht angezeigt — wir vergleichen nicht.

- Zweck: saisonale Beobachtung, ob EEDC über alle Saisonen stabil läuft.
- Geplantes Ende: nach Abschluss der saisonalen Beobachtungsphase
  (12 Monate) wird der Tab entfernt. Diagnose-Werkzeuge bleiben backend-
  seitig als Logging / Metriken erhalten, falls nötig.

**Verhältnis zur Solcast-Evaluierungsphase:** Die ursprüngliche Solcast-
Evaluierungsphase (eingeführt v3.16.4 als Prognosen-Vergleich-Tab,
„Evaluierungsphase") ist mit der Verabschiedung des
[`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md)
**konzept-intern beendet**.

**Solcast-Spalte im Prognosen-Vergleich-Tab:** Mit Verabschiedung des
[`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md) gilt
die Linie, dass alle Mehrwege-Vergleichsanzeigen auf „gewählte Quelle vs.
IST" reduziert werden. Die Solcast-Spalte fällt damit als eigenständige
UI-Spalte im Vergleichs-Tab weg; Solcast bleibt im Picker als wählbare
Vollwert-Quelle erhalten — wer Solcast als Diagnose-Werkzeug nutzt, stellt
sie schlicht als aktive Quelle ein. Der Rückbau der Vergleichs-Spalten
erfolgt im Rahmen von Schritt 5 der Quellenwahl-Roadmap (Frontend-Picker
+ Konsumenten-Umstellung). Die Stratifizierungs-Card und O12-Diagnose-Card
sind bereits additiv ausgeliefert (Päckchen 1, v3.26.0) und unabhängig
vom Vergleichs-Tab.

## Ziel-Architektur — Sonnenstand × Wetterklasse (geplant, nicht reaktiv)

Statt mehrerer reaktiv-anrollender Varianten gibt es **eine** geplante
Ziel-Architektur, auf die wir hinarbeiten:

> **Ein Faktor pro `(azimut_bin, elevation_bin, wetterklasse)` — eine
> kombinierte mehrdimensionale Tabelle pro Anlage.**

Erfasst Verschattung (über Sonnenstand-Bin) und wetterabhängige
Asymmetrie (über Wetterklasse) in einem gemeinsamen Bin, sodass die
Interaktion *„Verschattung wirkt bei klarem Himmel stark, bei diffuser
Strahlung kaum"* sauber abgebildet ist.

### Begründung der Achsen-Wahl

**Sonnenstand statt Saisonbin × Stunde:**
- Physikalisch korrekt — gleicher Sonnenstand = gleiche Verschattung,
  unabhängig von Datum (April × 09:00 und August × 09:00 haben
  unterschiedlichen Sonnenstand und damit unterschiedliche Verschattung)
- Statistisch dichter — mehrere Tage pro Jahr fallen in denselben
  Sonnenstand-Bin
- Sensor-Daten dafür kommen von einem neutralen Solar-Position-Helper
  (`pvlib` oder eigene Astro-Berechnung); keine externe Datenquelle nötig

**Wetterklasse als eigene Bin-Achse statt multiplikativer Trennung:**
- Multiplikative Trennung `f_verschattung × f_wetter` setzt Unabhängigkeit
  der Effekte voraus — die wir empirisch *nicht* haben (Interaktion
  Verschattung × Wetter)
- Multiplikative Faktoren sind ohne Bodenwahrheit auch identifizierungs-
  bedingt ill-posed: aus IST/Prognose lassen sich die Anteile nicht
  trennen
- Eine kombinierte Tabelle ist statistisch trivial (einfacher Mittelwert
  pro Bin) und erfasst Interaktionen exakt

### Bin-Auflösung und Sparsity

- Sonnenstand: Auflösung 10° × 10° → 36 × 9 = 324 mögliche Bins, davon
  in der Praxis ~150–200 belegt (nur halber Himmel relevant, Elevation
  sinnvoll bis ~70°)
- Wetterklasse: 3 Klassen (klar / diffus / wechselhaft)
- Total: ~450–600 Korrektur-Bins pro Anlage
- Datenpunkte pro Bin: bei 2 Jahren historischen Daten (Backfill aus
  Open-Meteo Archive) ≈ 30–80 Stunden pro Bin auf Hauptachsen,
  statistisch robust

### Fallback-Kaskade bei dünn besetzten Bins

Reicht ein Bin nicht für robusten Faktor (zu wenig Datenpunkte),
fällt der Aggregator stufenweise zurück:

1. `(azimut_bin, elevation_bin, wetterklasse)` ≥ 10 Datenpunkte → diesen Faktor
2. `(azimut_bin, elevation_bin)` ohne Wetter ≥ 15 Datenpunkte
3. `(saisonbin, stunde)` ≥ 15 Datenpunkte (klassische Variante-A-Logik)
4. Skalar-Lernfaktor mit O1+O2-Optimierung (siehe oben)

Stufe 3 als Fallback erhalten — Variante A wird damit nicht zur
eigenständigen Variante, sondern zur degradierten Stufe in der Kaskade.

### Anwendung im Live-Pfad

Pro stündlichem GTI-Wert in der Live-Prognose:
1. Sonnenstand für (lat, lon, datum, stunde) berechnen → Azimut, Elevation
2. Wetterklasse für die aktuelle Stunde aus Live-Wetter ableiten
3. Lookup in `Korrekturprofil` mit Fallback-Kaskade → `faktor_h`
4. `gti_h_korrigiert = gti_h × faktor_h`

### Variante C — String-spezifisch — bleibt reaktiv

Ein Korrekturprofil **pro Investition** statt pro Anlage ist eine reine
Erweiterung des bestehenden Schemas (`investition_id` setzen statt
NULL). Wird **nicht** in der Standard-Architektur verbaut, sondern auf
konkrete Multi-WR-Anfrage hin aktiviert.

**Daten-Bedarf:** IST-kWh pro String. Bei den meisten Anlagen heute nicht
erfasst, daher kein produktiver Daten-Pfad ohne Sensor-Mapping-Erweiterung.

**Trigger:** konkrete Multi-WR-Anfrage einer Anlage mit String-Sensorik.

## Datenmodell

Ein flexibles Schema, das die Ziel-Architektur sowie Fallback-Stufen
trägt:

```python
class Korrekturprofil(Base):
    __tablename__ = "korrekturprofile"
    id: Mapped[int] = mapped_column(primary_key=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id"))
    investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id"), nullable=True
    )  # NULL = Anlagensumme, gesetzt = Variante C (reaktiv)
    quelle: Mapped[str]  # heute nur "openmeteo" (EEDC-Eingabe)
    profil_typ: Mapped[str]
    # "sonnenstand_wetter" | "sonnenstand" | "stunde" | "skalar"
    bin_definition: Mapped[dict] = mapped_column(JSON)
    # sonnenstand_wetter: {"azimut_aufloesung": 10, "elevation_aufloesung": 10,
    #                      "wetterklassen": ["klar", "diffus", "wechselhaft"]}
    # sonnenstand: {"azimut_aufloesung": 10, "elevation_aufloesung": 10}
    # stunde: {"saisonbin": "monat|quartal|gesamt"}
    # skalar: {}
    faktoren: Mapped[dict] = mapped_column(JSON)
    # sonnenstand_wetter: {"110_30_klar": 0.72, "110_30_diffus": 0.95, ...}
    # sonnenstand: {"110_30": 0.80, ...}
    # stunde: {"4": {"7": 0.85, ...}, ...}
    # skalar: {"value": 1.01}
    datenpunkte_pro_bin: Mapped[dict] = mapped_column(JSON)
    # für Fallback-Kaskade: {"110_30_klar": 42, ...}
    aktualisiert_am: Mapped[datetime]
```

**Migrationspfad:**

1. **Päckchen 1** — kein Eintrag in `korrekturprofile`. Lernfaktor wie
   heute in `_get_lernfaktor_detail`, jetzt mit O1+O2 als Doppel-Variante.
   Stündliche Wetter-Daten werden in `TagesEnergieProfil` mitgeschrieben,
   2-Jahres-Backfill aus Open-Meteo Archive füllt die Historie.
2. **Päckchen 2** — Aggregator schreibt `profil_typ='sonnenstand_wetter'`
   pro Anlage. Live-Pfad konsumiert die Tabelle mit Fallback-Kaskade. UI
   bekommt Heatmap als Diagnose-Sicht.
3. **Reaktiv (Variante C)** — bei konkreter Multi-WR-Anfrage:
   `investition_id` setzen, das gleiche Schema trägt es ohne Migration.

## Aufwand und Reihenfolge — zwei Päckchen plus Reaktives

> **Status (2026-05-06):** Päckchen 1 ✅ ausgeliefert mit v3.26.0 + Hotfix
> v3.26.1. Päckchen 2 ✅ ausgeliefert mit v3.26.2 + Hotfix v3.26.3
> (Aggregator-Skipped-Pfad zu strikt: Skalar wird jetzt unabhängig von
> Day-Ahead-Stundenprofilen berechnet). Beobachtungs-Phase läuft —
> Sonnenstand-Bins füllen sich ab ~Tag 10, statistisch robust ab ~Tag 30.

### Päckchen 1 (~4 Tage) — Daten-Layer und Skalar-Verbesserung — ✅ v3.26.0/3.26.1

| Schritt | Aufwand |
|---|---|
| Stündliche Wetter-Spalten in `TagesEnergieProfil` | ½ Tag |
| Live-Pfad: Wetter-Werte beim Forecast-Fetch persistieren | ½ Tag |
| Backfill-Job aus Open-Meteo Archive (2 Jahre rückwirkend) | 1 Tag |
| Wetter-Klassifikations-Helper (klar/diffus/wechselhaft) | ½ Tag |
| O2 Trim-Mean + O1 Recency-Boost als Doppel-Variante | ½ Tag |
| Stratifizierungs-Endpoint (MAE/MBE pro Klasse × Stunde) | ½ Tag |
| Frontend: Stratifizierungs-Card + O12-Diagnose-Card (additiv, Solcast-Spalte bleibt — Tester-Pakt mit Rainer) | ½ Tag |

### Päckchen 2 (~5–7 Tage) — Korrekturprofil aktiv — ✅ v3.26.2/3.26.3

| Schritt | Aufwand |
|---|---|
| Solar-Position-Helper (Sonnenstand pro lat/lon/datum/stunde) | ½ Tag |
| `Korrekturprofil`-Schema + DB-Migration | ½ Tag |
| Aggregator-Job (Sonnenstand × Wetter) mit Fallback-Kaskade | 1–2 Tage |
| Live-Pfad: Lookup in `get_live_wetter` mit Kaskade | 1 Tag |
| Frontend-Heatmap als Diagnose-Sicht | 1–2 Tage |
| End-to-end-Test, Backfill-Reaggregation, Edge Cases | 1 Tag |

### Reaktiv

| Schritt | Trigger |
|---|---|
| Aktivierung O1+O2 als neuer Skalar-Default | Doppel-Vergleich zeigt klar Verbesserung über mehrere Wochen — **frühestens nach v3.27.0**, nicht innerhalb der laufenden Beobachtungs-Phase |
| Variante C (String-spezifisch) | Konkrete Multi-WR-Anfrage |
| O3 Schneeerkennung | Eigenes Issue, nach Winter 2026/27 |
| Prognosen-Tab entfernen | Nach 12 Monaten saisonaler Beobachtung, wenn Korrekturprofil sich bewährt |

## Was nicht zu dieser Doku gehört

- Quellenwahl-Architektur (EEDC / Solcast pur / SFML) — siehe
  [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md).
- Vergleichende Decision-Support-Logik zwischen Quellen — explizit
  ausgeschlossen, siehe Tom-HA-Versprechen.
- Tom-HA als strategisches Argument — entwaffnet durch Quellenwahl-
  Architektur, hier nicht mehr Thema.
