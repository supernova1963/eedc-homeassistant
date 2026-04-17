# Konzept: Stündliche Strompreis-Mitschrift

## Motivation

EEDC kennt Strompreise bisher nur als **feste Monatswerte** (`Strompreis`-Model mit
Gültigkeitszeiträumen). Für Nutzer mit dynamischen Tarifen (Tibber, aWATTar, EPEX Spot)
oder zeitabhängigen Netzentgelten (AT SNAP-Tarif) ist der tatsächliche Durchschnittspreis
aber **verbrauchsgewichtet und stundenvariabel** — ein pauschaler Monatspreis bildet das
nicht ab.

### Auslöser

- **Rainer:** EPEX-Börsenpreis-Overlay im Tagesverlauf-Chart (umgesetzt in v3.15.8)
- **vandecook (#122):** Österreichischer SNAP-Tarif (zeitabhängiger Netzentgelt-Rabatt)
- **av3 (#315):** §14a-Netzentgeltreduzierung (DE, steuerbare Verbraucher)
- **Joachim-xo:** Live-Preis-Sensor allgemein

### Abgrenzung

**Nicht Teil dieses Konzepts:**
- Einspeisevergütung bei negativen Börsenpreisen (#120) — eigener Track, Gesetzeslage offen
- Direkter API-Connector für Tibber/aWATTar (Stufe 2) — erst nach Stufe 1
- Flexibler Einspeisepreis — vertagt bis Vergütungssystematik geklärt

---

## Bestandsaufnahme

### Was existiert

| Baustein | Status | Wo |
|----------|--------|----|
| `Strompreis`-Model (fix, pro Verwendung) | Produktiv | `models/strompreis.py` |
| `verwendung`-Feld (allgemein/waermepumpe/wallbox) | Produktiv | `models/strompreis.py:48` |
| `netzbezug_durchschnittspreis_cent` im Monatsabschluss | Produktiv | `models/monatsdaten.py:57` |
| Sensor-Mapping `strompreis` (entity_id) | Produktiv | `sensor_mapping.py:56` |
| Tagesverlauf-Overlay (Lese-Pfad) | v3.15.8 | `live_tagesverlauf_service.py` |
| `TagesEnergieProfil` (stündlich, 24 Zeilen/Tag) | Produktiv | `models/tages_energie_profil.py` |
| Scheduler: alle 15 Min + Tagesabschluss 00:15 | Produktiv | `services/scheduler.py` |

### Was fehlt

| Baustein | Beschreibung |
|----------|-------------|
| **Feld `strompreis_cent`** im TagesEnergieProfil | Stündlicher Preis neben den kW-Werten |
| **Schreib-Pfad** im Scheduler | Preis aus HA-Sensor lesen + ins Profil schreiben |
| **Monatsabschluss-Vorschlag** | Verbrauchsgewichteter Ø automatisch berechnen |
| **Backfill** | Historische Preise aus HA Long-Term Statistics nachladen |

---

## Architektur

### Datenfluss

```
HA-Sensor (Tibber/aWATTar/Template)
       │
       │ entity_id aus sensor_mapping.basis.strompreis
       ▼
┌──────────────────────────────┐
│ Scheduler (alle 15 Min)      │
│ energie_profil_service.py    │
│                              │
│ Liest aktuellen Preis-Wert   │
│ Schreibt in TagesEnergieProfil│
│ Feld: strompreis_cent        │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ TagesEnergieProfil           │
│ (pro Stunde, pro Anlage)     │
│                              │
│ pv_kw, verbrauch_kw, ...     │
│ + strompreis_cent  ← NEU     │
└──────────┬───────────────────┘
           │
     ┌─────┴──────────┐
     ▼                ▼
┌────────────┐  ┌─────────────────────┐
│ Tagesverlauf│  │ Monatsabschluss     │
│ Chart       │  │                     │
│ (Overlay,   │  │ Ø = Σ(kWh×ct) /    │
│  bereits    │  │     Σ(kWh)          │
│  umgesetzt) │  │                     │
│             │  │ → Vorschlag für     │
│             │  │   durchschnittspreis│
└─────────────┘  └─────────────────────┘
```

### Einheiten-Normalisierung

HA-Sensoren liefern Preise in unterschiedlichen Einheiten:

| Integration | Einheit | Normalisierung |
|-------------|---------|----------------|
| Tibber | EUR/kWh (0.28) | × 100 → ct/kWh |
| aWATTar | EUR/MWh (280) | ÷ 10 → ct/kWh |
| Nordpool/EPEX | EUR/MWh | ÷ 10 → ct/kWh |
| Template-Sensor | ct/kWh (28) | passthrough |
| SNAP-Template | ct/kWh | passthrough |

Die Normalisierung auf **ct/kWh** erfolgt beim Lesen (bereits im Tagesverlauf-Overlay
implementiert für EUR/kWh, erweiterbar für EUR/MWh).

---

## Implementierung

### Phase 1 — Stündliche Mitschrift (Kern)

**1a. Neues DB-Feld**

`TagesEnergieProfil`:
```python
strompreis_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

Migration in `database.py` → `run_migrations()`:
```python
# Spalte strompreis_cent in tages_energie_profil
_add_column_if_missing(conn, "tages_energie_profil", "strompreis_cent", "REAL")
```

**1b. Scheduler-Integration**

In `aggregate_day()` (`energie_profil_service.py`):
1. `strompreis_eid` aus `anlage.sensor_mapping.basis.strompreis.entity_id` lesen
2. Wenn vorhanden: Stundenmittel aus HA-History holen (analog zu Temperatur/Strahlung)
3. Einheit normalisieren (EUR/kWh → ct/kWh)
4. In `TagesEnergieProfil.strompreis_cent` schreiben

Im Backfill (`backfill_from_statistics()`):
- Gleiche Logik, aber aus HA Long-Term Statistics statt Sensor-History
- Preis-Sensor hat `has_mean=True` in HA Statistics → Stundenmittel verfügbar

**1c. TagesZusammenfassung erweitern**

Neues Feld:
```python
strompreis_avg_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

Berechnung: Tages-Durchschnitt (ungewichtet, nur für Anzeige).

### Phase 2 — Monatsabschluss-Vorschlag

**2a. Verbrauchsgewichteter Ø-Preis berechnen**

Beim Öffnen des Monatsabschluss-Wizards:
```python
# Alle Stunden des Monats mit Preis UND Bezug
stunden = SELECT strompreis_cent, netzbezug_kw
          FROM tages_energie_profil
          WHERE anlage_id = X AND monat = Y
            AND strompreis_cent IS NOT NULL
            AND netzbezug_kw > 0

# Verbrauchsgewichteter Durchschnitt
avg_preis = Σ(netzbezug_kw × strompreis_cent) / Σ(netzbezug_kw)
```

**2b. Im Monatsabschluss-UI anzeigen**

- Feld `netzbezug_durchschnittspreis_cent` automatisch vorausfüllen
- Hinweistext: *"Berechnet aus X Stunden mit Preisdaten (verbrauchsgewichtet)"*
- Wert überschreibbar (User hat immer das letzte Wort)
- Wenn keine Preisdaten vorhanden: Feld bleibt leer, kein Vorschlag

### Phase 3 — Tagesverlauf-Chart (bereits umgesetzt)

Das Overlay im Tagesverlauf-Chart ist in v3.15.8 fertig:
- Sekundäre Y-Achse (ct/kWh)
- Pink Step-Linie für Strompreis
- Tooltip mit Einheit
- Klickbare Legende zum Ein-/Ausblenden

---

## Anwendungsfälle und Eingabequellen

### Fall 1: Tibber / aWATTar / EPEX (dynamischer Tarif)

- HA-Integration liefert Sensor direkt (z.B. `sensor.tibber_prices`)
- Nutzer trägt Entity-ID im Sensor-Mapping ein
- EEDC schreibt stündlich mit, berechnet Monats-Ø

**Konfiguration:** Sensor-Mapping → Basis → Strompreis → Entity-ID auswählen

### Fall 2: SNAP-Tarif Österreich (zeitabhängiger Netzentgelt-Rabatt)

Schema: Apr–Sep, 10:00–16:00 Uhr → 20% Reduktion auf Netzentgelt-Arbeitspreis.
Betrifft ausschließlich den Arbeitspreis der Netzentgelte, nicht den Energieliefer-Arbeitspreis.
Beispielwert (Netzebene H7, AT): 6,290 ct/kWh → 5,032 ct/kWh im SNAP-Fenster.

**Konfiguration (2 Schritte):**

**Schritt 1 — HA-Template-Sensor erstellen:**
```yaml
template:
  - sensor:
      - name: "Strompreis mit SNAP"
        unit_of_measurement: "ct/kWh"
        state: >
          {% set basis = 28.5 %}
          {% set netzentgelt = 6.29 %}
          {% if now().month in [4,5,6,7,8,9] and 10 <= now().hour < 16 %}
            {{ basis - netzentgelt * 0.2 }}
          {% else %}
            {{ basis }}
          {% endif %}
```

**Schritt 2 — In EEDC Sensor-Mapping eintragen:**
Sensor-Mapping → Basis → Strompreis → den Template-Sensor zuordnen.

EEDC braucht keine SNAP-spezifische Logik — der Template-Sensor liefert den
korrekten Preis pro Stunde, die stündliche Mitschrift (Phase 1) schreibt ihn ins
Energieprofil, und der Monatsabschluss-Vorschlag (Phase 2) berechnet daraus
automatisch den verbrauchsgewichteten Monatsdurchschnitt.

So bekommt Roland (Discussion #122) genau das, was wir zugesagt haben: SNAP-Sensor
mappen → automatischer Ø-Preis im Monatsabschluss, der die Tageszeit-Abhängigkeit
korrekt berücksichtigt.

**Dokumentation:** Template-Vorlage + Anleitung im Benutzerhandbuch aufnehmen.

### Fall 3: §14a Netzentgelt-Reduzierung (DE)

Steuerbare Verbrauchseinrichtungen (WP, Wallbox) bekommen reduzierten Netzentgelt-Arbeitspreis.
Die Abrechnungspraxis ist in der Realität **extrem heterogen** (Stadtwerke vs. MSB vs.
Lieferant, pauschale Erstattung vs. kWh-Rabatt, teils rückwirkend). Das macht eine
saubere Automatisierung aktuell unmöglich.

**Varianten in der Praxis:**
- **Pauschale Erstattung** (z.B. 110 €/Jahr) → kein ct/kWh-Bezug, nicht über Strompreis abbildbar
- **kWh-Rabatt** (reduzierter Arbeitspreis) → über `verwendung: waermepumpe` abbildbar
- **Rückwirkende Gutschrift** → erst nach Jahresabrechnung bekannt
- **Getrennte Zähler** vs. **gemeinsamer Zähler** → unterschiedliche Erfassungswege

**Aktueller Workaround:** Erstattung manuell als reduzierten Strompreis in den
betroffenen Monaten eintragen, dann rechnet die Amortisation korrekt.

**Empfehlung:** Keine dedizierte §14a-Funktion, solange die Abrechnungspraxis nicht
standardisiert ist. Der manuelle Weg über das bestehende `Strompreis`-Model
(separater Tarif mit `verwendung: waermepumpe`) deckt den kWh-Rabatt-Fall ab.
Pauschale Erstattungen gehören als Sonstige-Position in die Finanzen, nicht in den
Strompreis.

### Fall 4: Fester Tarif (Standard)

Kein Sensor-Mapping nötig. Monatsabschluss nutzt weiterhin den festen Preis aus
dem `Strompreis`-Model. Kein Vorschlag aus Energieprofil, da keine Preisdaten existieren.

---

## Priorisierung und Aufwand

| Phase | Aufwand | Abhängigkeiten |
|-------|---------|----------------|
| **1a** DB-Feld + Migration | Klein | — |
| **1b** Scheduler-Integration | Mittel | 1a |
| **1c** TagesZusammenfassung | Klein | 1a |
| **2a** Monatsabschluss-Berechnung | Mittel | 1b (braucht Daten) |
| **2b** Monatsabschluss-UI | Klein | 2a |
| **3** Tagesverlauf-Overlay | ✅ erledigt | — |

**Empfohlene Reihenfolge:** 1a → 1b → 1c → 2a → 2b

Phase 1 ist in einem Sprint machbar. Phase 2 kann im Folge-Sprint kommen,
sobald erste Nutzer Preisdaten gesammelt haben.

---

## Offene Fragen

1. **Backfill-Reichweite:** Wie weit zurück haben HA Long-Term Statistics den Preis-Sensor?
   Tibber-Integration schreibt seit Installation, Template-Sensoren erst ab Erstellung.
   → Backfill holt was da ist, kein Fehler wenn leer.

2. **Mehrere Preiszonen?** Bezugspreis (dynamisch) vs. WP-Strom (fest/§14a).
   Aktuell nur ein Strompreis-Sensor im Basis-Mapping.
   → Reicht für Phase 1. Falls später getrennte Preise pro Verwendung nötig:
   Sensor-Mapping um `strompreis_wp`, `strompreis_wallbox` erweitern.

3. **Einspeisepreis stündlich?** Bei negativen Börsenpreisen fällt die Vergütung weg.
   → Bewusst ausgeklammert (eigener Track, #120). Kann später als zweites
   Overlay im Tagesverlauf ergänzt werden.
