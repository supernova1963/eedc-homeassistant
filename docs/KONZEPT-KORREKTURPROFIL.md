# Konzept: Anlagenspezifisches Korrekturprofil

## Motivation

EEDC verwendet aktuell einen **skalaren Lernfaktor** pro Anlage und Prognose-Quelle
(`live_wetter.py:_get_lernfaktor_detail`), der über die saisonale Kaskade
„Monat → Quartal → Gesamt" die Tagessummen-Abweichung zwischen Prognose und IST
nivelliert. Begrenzt auf [0.5 ; 1.3], gerundet auf 3 Nachkommastellen,
tagesweise gecacht.

**Was der Skalar gut kann:**

- Pauschale Anlagen-Eigenarten (allgemeine Modul-Degradation, WR-Wirkungsgrad,
  systematischer GTI-Bias der Wetterquelle)
- Saisonale Verschiebung über Sonnenstand-Höhe (April vs. Dezember)

**Was der Skalar NICHT kann:**

- **Verschattung im Tagesverlauf**: Baum/Gebäude/Geländekante schluckt morgens
  oder abends einen Teil der Strahlung. Tagessumme fällt z.B. um 5 % → Faktor
  geht auf 0.95. Aber: Live-Dashboard skaliert _alle_ Stunden mit 0.95 — die
  betroffenen Stunden bräuchten 0.5, die unbetroffenen 1.0. Tagessumme stimmt
  rechnerisch, das Stundenprofil nicht.
- **String-spezifische Effekte**: Ostflügel verschattet, Westflügel nicht. Mit
  einem Anlagen-Skalar werden beide gleich behandelt.
- **Wetterabhängige Asymmetrie**: bei klarem Himmel wirkt Verschattung stark, bei
  diffuser Strahlung kaum — wird aktuell nicht differenziert.

### Auslöser

- **Tom-HA-Kontext** (April 2026): Skalarer Lernfaktor ist eine offene Flanke,
  die in Community-Diskussionen als „Pauschalierung" angreifbar ist. Strategisch
  relevant, ein präziseres Modell konzeptionell vorbereitet zu haben — auch wenn
  die Umsetzung erst bei breiter Datenbasis sinnvoll ist.
- **Etappe 4 Energieprofil** (saisonale Muster): braucht ohnehin 6+ Monate
  Datenbestand, gleicher Grundzeitpunkt für Korrekturprofil-Aggregation.
- **Realwelt-Anlagen mit Verschattung**: detLAN, Joachim und andere mit Bäumen
  oder Nachbargebäuden im Schatten-Wurf zu typischen Sonnenständen.

### Abgrenzung

**Nicht Teil dieses Konzepts:**

- Explizites Schatten-Geometrie-Modell (3D-Hinderniskarte, Ray-Tracing) — dafür
  bräuchte EEDC Höhen-/Distanz-Eingabe pro Hindernis. Nicht praktikabel im
  Self-Service-Kontext.
- Wetterklassifikation (klar/diffus) als separate Dimension — wird im aktuellen
  Lernfaktor nicht getrennt, soll auch hier zunächst nicht.
- ML-Modell mit Black-Box-Charakter — Ziel ist explizite, nachvollziehbare
  Aggregation. Transparenz-Vorteil gegen ML-Konkurrenten.

---

## Bestandsaufnahme

### Datenquellen heute

| Baustein | Status | Wo | Granularität |
|---|---|---|---|
| `TagesZusammenfassung.pv_prognose_kwh` | Produktiv | `models/tageszusammenfassung.py` | Tagessumme |
| `TagesZusammenfassung.solcast_prognose_kwh` | Produktiv | dito | Tagessumme |
| `TagesEnergieProfil` (24 Stunden je Tag, Snapshot-basiert) | Produktiv ab v3.19 | `models/tagesenergieprofil.py` | **Stunden-Slot, IST** |
| OpenMeteo `hourly` (GTI, Temperatur, Wolken, …) | Produktiv | `services/live_wetter.py` | **Stunden-Slot, Prognose** |
| Solcast `hourly` (PV-Leistung) | Produktiv ab v3.16 | `services/solcast.py` | **Stunden-Slot, Prognose** |
| Solar-Position (EOT für Solar-Noon-Split) | Produktiv ab v3.22 | `services/solar_noon.py` | berechnet on-the-fly |

**Schlussfolgerung:** Die Datengrundlage für ein stündliches Korrekturprofil
ist bereits vollständig vorhanden. Es fehlt nur die Aggregation-/Speicher-/
Anwendungs-Schicht.

### Aggregations-Logik heute (skalar)

```text
_berechne_faktor(tage, db_feld) → Σ(IST) / Σ(Prognose), produktionsgewichtet
  Filter pro Tag: Prognose > 0.5 kWh AND IST > 0.5 kWh
  
Saisonale Kaskade:
  1. Monat (gleicher Kalendermonat alle Jahre, ≥15 Tage)
  2. Quartal (gleiches Q1-Q4 alle Jahre, ≥15 Tage)
  3. Gesamt (letzte 30 Tage rollierend, ≥7 Tage)
  Sonst: kein Faktor

Clamp [0.5 ; 1.3], runden auf 3 Nachkommastellen, Cache pro (anlage, quelle).
```

---

## Drei Varianten

### Variante A — Stündliches Korrekturprofil

**Schema:** ein Faktor pro `(saisonbin, stunde)` — z.B. „April × 09:00".

**Aggregation:** `Σ(IST_h) / Σ(Prognose_h)` über alle Tage im Saisonbin und
gleicher Stunde h. Saisonale Kaskade analog zum Skalar.

**Daten-Bedarf:** stündliche IST und Prognose. Beide vorhanden.

**Anwendung:**

- Live-Dashboard: `gti_h = gti_h × faktor_h(monat, h)`
- Prognose-Tab: stündliches Profil aus Stundenfaktoren rekonstruiert,
  Tagessumme = Σ aller h

**Erfasst:** Verschattung im Tagesverlauf (Baum am Ostflügel zu typischen
Sonnenständen).

**Erfasst NICHT:** Saisonale Verschiebung des Sonnenstands innerhalb desselben
Monats (Anfang vs. Ende April), wetterabhängige Asymmetrie.

**Aufwand:** Mittel. Aggregation (Background-Job), neues Schema (Tabelle oder
JSONB-Feld in Anlage), Frontend-Heatmap (24×12) als Diagnose-Sicht.

**Tom-Argument:** „Stündlich korrigiert, transparent aggregiert,
nachvollziehbar." Deckt 95 % der real auftretenden Verschattung ab.

### Variante B — Sonnenstand-basiertes Korrekturprofil

**Schema:** ein Faktor pro `(azimut_bin, elevation_bin)` — z.B. „Azimut 110°,
Elevation 30°" als Bin.

**Aggregation:** Sonnenstand für jede `(tag, stunde)` berechnen, Bin zuordnen,
analog `Σ(IST) / Σ(Prognose)` aggregieren.

**Daten-Bedarf:** wie A, plus Solar-Position-Berechnung pro Slot (Library oder
eigene Implementierung mit EOT — wir haben die Hälfte schon für Solar-Noon).

**Anwendung:**

- Live-Dashboard: pro Stunde Sonnenstand → Bin → Faktor → `gti × faktor`
- Prognose-Tab: analog

**Erfasst:** Verschattung physikalisch sauber. Gleicher Sonnenstand =
gleiche Verschattung egal welche Jahreszeit. Sehr genau bei Anlagen mit
Hindernissen.

**Erfasst NICHT:** wetterabhängige Asymmetrie (klar vs. diffus).

**Aufwand:** Höher. Bin-Definition (Auflösung-vs-Datenmenge-Trade-off, z.B.
10°×10° = 36×9 = 324 Bins), Solar-Position-Helper, vermutlich pre-aggregated
Lookup-Tabelle pro Anlage.

**Tom-Argument:** „Echtes Solar-Engineering, keine Stundenraster-Pauschalierung."
Premium-Positionierung.

### Variante C — String-/WR-spezifisches Korrekturprofil

**Schema:** ein Profil (A oder B) **pro Investition** (PV-Modul-Gruppe oder WR)
mit eigener Ausrichtung.

**Daten-Bedarf:** IST-kWh **pro String** (Investitions-MonatsdatenStunde — neue
Tabelle, oder Erweiterung von `TagesEnergieProfil` pro Investition).

**Anwendung:** pro String eigener Faktor → Summe ergibt Anlagen-Prognose.

**Erfasst:** „Ostflügel verschattet, Westflügel nicht" sauber.

**Aufwand:** Hoch. Daten-Pipeline pro Investition (selten erfasst —
bei den meisten Anlagen liegen nur Anlagensummen vor), neues Tabellen-Layout,
Sensor-Mapping pro String.

**Tom-Argument:** Vermutlich keine Konkurrenz hat das. Sehr nischige Premium-
Funktion, nur sinnvoll bei Multi-WR-Anlagen mit ungleicher Verschattung.

---

## Datenmodell-Skizze (zukunftssicher)

Ein einziges Schema, das alle drei Varianten ohne Migration trägt:

```python
class Korrekturprofil(Base):
    __tablename__ = "korrekturprofile"
    id: Mapped[int] = mapped_column(primary_key=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id"))
    investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id"), nullable=True
    )  # NULL = Anlagensumme (heute), gesetzt = Variante C
    quelle: Mapped[str]  # "openmeteo" | "solcast"
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

1. **Heute** — kein Eintrag in `korrekturprofile`. Lernfaktor wie bisher in
   `_get_lernfaktor_detail` berechnet, kein Cache in DB.
2. **Etappe 1 (Variante A) ohne Migration** — neue Einträge mit
   `profil_typ='stunde'` werden vom Aggregator angelegt. `_get_lernfaktor`
   prüft erst die Tabelle, fällt sonst auf den alten Skalar zurück.
3. **Etappe 2 (Variante B) ohne Migration** — `profil_typ='sonnenstand'`
   ergänzt sich neben Variante A; UI bietet Wahl oder kombiniert beide.
4. **Etappe 3 (Variante C) ohne Migration** — `investition_id` wird gesetzt,
   das gleiche Schema trägt das.

---

## Vorbereitungs-Hooks (jetzt umsetzbar, ohne Surface)

Was sinnvoll **vorgezogen** werden kann, ohne ein leeres Feature zu exponieren:

| Vorbereitung | Aufwand | Kommentar |
|---|---|---|
| **Diese Konzept-Doku** | klein | Internal — sichtbar nur, wenn ich aktiv darauf verweise |
| **Solar-Position-Helper** (`services/solar_position.py`) — Azimut/Elevation pro `(datum, stunde, lat, lon)` | klein-mittel | Ohnehin nützlich für Etappe 4 saisonale Muster, Wetter-Heatmap, evtl. SOLL/IST-Hour-Plot |
| **Datenmodell-Skizze** in dieser Doku | erledigt | siehe oben |
| **Background-Aggregator** als Stub (importierbar, läuft aber noch nicht) | klein | Erst aktivieren, wenn Datenbestand reicht |
| **API-Endpunkt `/api/korrekturprofile/{anlage_id}`** als Stub | minimal | Geringfügige Surface — nur wenn aktiv geprüft wird |

**Was NICHT jetzt:**

- Frontend-UI (würde leeres Feature exponieren — Angriffsfläche statt Schutz)
- Tatsächliche Aggregation (zu wenig Datenbestand bei den meisten Anlagen)
- Migration auf neues Schema (kein produktiver Bedarf)

---

## Trigger-Bedingungen für die Umsetzung

| Bedingung | Erfüllt wann? |
|---|---|
| ≥ 6 Monate Stunden-IST-Daten in mindestens 5 Anlagen | TBD — beobachten ab v3.19 (Snapshot-Rework, Apr 2026) |
| Konkrete Forum-Anfrage zur Stundenprofil-Korrektur | TBD |
| Tom-HA-Vergleichs-Argument konkret im Raum | TBD |
| Kapazität für mehrwöchige Implementierung | TBD |

**Empfehlung:** Variante A als „Etappe 1" planen, Trigger ist „6 Monate Daten
+ konkrete Anfrage". Variante B nur wenn nachweisbarer Bedarf. Variante C nur
auf explizite Multi-String-Anfrage.

---

## Kommunikations-Hinweis

Diese Konzept-Doku ist ein **internes Strategie-Dokument**, kein
Marketing-Material. Sollte Tom-HA-Kontext sich verschärfen oder eine konkrete
Verschattungs-Anfrage kommen, kann die Datenmodell-Skizze und der Migrationspfad
**innerhalb einer Woche** in Code überführt werden — Schema-Design ist die
zeitintensivste Arbeit, und die ist hier vorweggenommen.

Bis dahin: skalarer Lernfaktor mit saisonaler Kaskade ist robust, wird aktiv
genutzt, und ist transparent dokumentiert.
