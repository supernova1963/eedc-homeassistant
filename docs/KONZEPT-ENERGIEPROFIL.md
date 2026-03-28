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
