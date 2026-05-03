# Konzept: EEDC-Lernfaktor — Optimierung und Korrekturprofile

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

## Wetter-Stratifizierung (interne EEDC-Diagnose)

EEDC-Lernfaktor wird nach Wetter-Klasse (klar / diffus / wechselhaft)
ausgewertet: zeigt, ob bei bestimmten Wetterlagen systematisch verzerrt
wird.

- Klassifikation pro Tag aus `cloud_cover_mean` + `precipitation_sum`
  (Logik in [`wetter/utils.py`](../eedc/backend/services/wetter/utils.py)
  `wetter_symbol_aus_tag` als Inspiration).
- Pro Klasse: separater MAE/MBE auf den letzten 30/90 Tagen.
- **Strikt EEDC-intern** — keine Quellen-Vergleichs-Statistik daneben.
- Hilft bei der Frage: rechtfertigt sich Variante A (stündliches Profil)
  oder reicht der Skalar?

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
**formell beendet**. Der Tab in seiner heutigen Form (mit Solcast-Spalte,
Genauigkeits-Tracking, Asymmetrie-Cards) wird auf reine EEDC-Diagnose
umgestellt — Solcast-Spalte raus, Wetter-Stratifizierung rein.

## Varianten A / B / C — technische Optionen, reaktiv

Drei Granularitäten für ein anlagenspezifisches Korrekturprofil. Werden
**nur** umgesetzt, wenn Diagnose-Schwellen aus Wetter-Stratifizierung
oder konkrete Anfragen es nahelegen — keine kalenderbasierten Trigger
(„6 Monate warten" gibt's nicht mehr).

### Variante A — Stündliches Korrekturprofil

**Schema:** ein Faktor pro `(saisonbin, stunde)` — z. B. „April × 09:00".

**Aggregation:** `Σ(IST_h) / Σ(Prognose_h)` über alle Tage im Saisonbin
und gleicher Stunde h. Saisonale Kaskade analog zum Skalar.

**Anwendung:**

- Live-Dashboard: `gti_h = gti_h × faktor_h(monat, h)`
- Stündliches Profil aus Stundenfaktoren rekonstruiert, Tagessumme = Σ
  aller h

**Erfasst:** Verschattung im Tagesverlauf (Baum am Ostflügel zu typischen
Sonnenständen). Deckt 95 % der real auftretenden Verschattung ab.

**Aufwand:** mittel. Aggregation (Background-Job), neues Schema (siehe
Datenmodell), Frontend-Heatmap (24×12) als Diagnose-Sicht.

**Trigger:** Wetter-Stratifizierungs-Daten zeigen systematisches
Stunden-Bias bei mindestens N Anlagen.

### Variante B — Sonnenstand-basiertes Korrekturprofil

**Schema:** ein Faktor pro `(azimut_bin, elevation_bin)` — z. B.
„Azimut 110°, Elevation 30°" als Bin (Auflösung 10°×10° = 324 Bins).

**Anwendung:** pro Stunde Sonnenstand → Bin → Faktor → `gti × faktor`.

**Erfasst:** Verschattung physikalisch sauber. Gleicher Sonnenstand =
gleiche Verschattung egal welche Jahreszeit.

**Aufwand:** höher. Solar-Position-Helper (~1 Tag, neutraler Helper),
pre-aggregated Lookup-Tabelle pro Anlage.

**Trigger:** konkrete Verschattungs-Anfrage UND Variante A reicht nicht.

### Variante C — String-/WR-spezifisches Korrekturprofil

**Schema:** ein Profil (A oder B) **pro Investition** (PV-Modul-Gruppe
oder WR) mit eigener Ausrichtung.

**Daten-Bedarf:** IST-kWh pro String — bei den meisten Anlagen aktuell
nicht erfasst.

**Erfasst:** „Ostflügel verschattet, Westflügel nicht" sauber.

**Aufwand:** hoch. Daten-Pipeline pro Investition, neues Tabellen-Layout,
Sensor-Mapping pro String.

**Trigger:** konkrete Multi-WR-Anfrage.

## Datenmodell

Ein einziges Schema, das alle drei Varianten ohne Migration trägt:

```python
class Korrekturprofil(Base):
    __tablename__ = "korrekturprofile"
    id: Mapped[int] = mapped_column(primary_key=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id"))
    investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id"), nullable=True
    )  # NULL = Anlagensumme, gesetzt = Variante C
    quelle: Mapped[str]  # heute nur "openmeteo" (EEDC-Eingabe)
    profil_typ: Mapped[str]  # "skalar" | "stunde" | "sonnenstand"
    bin_definition: Mapped[dict] = mapped_column(JSON)
    # skalar: {}
    # stunde: {"saisonbin": "monat|quartal|gesamt"}
    # sonnenstand: {"azimut_aufloesung": 10, "elevation_aufloesung": 10}
    faktoren: Mapped[dict] = mapped_column(JSON)
    # skalar: {"value": 1.01}
    # stunde: {"4": {"7": 0.85, "8": 0.90, ...}, "5": {...}}
    # sonnenstand: {"110_30": 0.70, "120_40": 0.85, ...}
    aktualisiert_am: Mapped[datetime]
```

**Migrationspfad:**

1. **Heute** — kein Eintrag in `korrekturprofile`. Lernfaktor wie bisher
   in `_get_lernfaktor_detail` berechnet, kein Cache in DB.
2. **Etappe 1 (Variante A) ohne Migration** — neue Einträge mit
   `profil_typ='stunde'` werden vom Aggregator angelegt. `_get_lernfaktor`
   prüft erst die Tabelle, fällt sonst auf den alten Skalar zurück.
3. **Etappe 2 (Variante B) ohne Migration** — `profil_typ='sonnenstand'`
   ergänzt sich neben Variante A.
4. **Etappe 3 (Variante C) ohne Migration** — `investition_id` wird
   gesetzt, das gleiche Schema trägt das.

## Aufwand und Reihenfolge

| Schritt | Aufwand | Voraussetzung |
|---|---|---|
| O2 Trim-Mean als Doppel-Variante | ~halber Tag | nichts |
| O1 Recency als Doppel-Variante | ~halber Tag | nach O2 |
| Wetter-Stratifizierung im Prognosen-Tab | ~1-2 Tage | Doppel-Vergleich aktiv |
| Aktivierung O1+O2 als neuer Default | ~Stunde | Doppel-Vergleich zeigt klar Verbesserung |
| Variante A planen + implementieren | mehrere Wochen | Stratifizierung zeigt Stunden-Bias |
| Variante B / C | hoch | reaktiv, nur auf konkrete Anfrage |
| O3 Schneeerkennung | mittel | eigenes Issue, nach Winter 2026/27 |
| Prognosen-Tab entfernen | ~halber Tag | nach 12 Monaten Saison-Beobachtung |

## Was nicht zu dieser Doku gehört

- Quellenwahl-Architektur (EEDC / Solcast pur / SFML) — siehe
  [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md).
- Vergleichende Decision-Support-Logik zwischen Quellen — explizit
  ausgeschlossen, siehe Tom-HA-Versprechen.
- Tom-HA als strategisches Argument — entwaffnet durch Quellenwahl-
  Architektur, hier nicht mehr Thema.
