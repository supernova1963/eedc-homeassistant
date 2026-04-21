
# EEDC Handbuch — Teil II: Bedienung

**Version 3.16.1** | Stand: April 2026

> Dieses Handbuch ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Navigation & Menüstruktur](#1-navigation--menüstruktur)
2. [Live Dashboard](#2-live-dashboard)
3. [Cockpit (Dashboards)](#3-cockpit-dashboards)
4. [Aktueller Monat](#4-aktueller-monat)
5. [Auswertungen](#5-auswertungen)
6. [Community](#6-community)
7. [Aussichten (Prognosen)](#7-aussichten-prognosen)
8. [Infothek](#8-infothek)

---

## 1. Navigation & Menüstruktur

### Hauptnavigation (oben)

Die horizontale Navigation enthält vier Hauptbereiche:

| Bereich | Funktion |
|---------|----------|
| **Live** | Echtzeit-Leistungsdaten mit animiertem Energiefluss-Diagramm |
| **Cockpit** | Übersicht mit KPIs, Energie-Fluss und Charts |
| **Auswertungen** | Detaillierte Analysen in 6 Tabs |
| **Community** | Anonymer Benchmark-Vergleich mit anderen PV-Anlagen |
| **Aussichten** | Prognosen: 7-Tage, Langfristig, Trend, Finanzen |

Plus ein Dropdown-Menü für **Einstellungen** und – sobald mindestens ein Eintrag existiert – den Hauptmenüpunkt **Infothek**.

### Einstellungen-Dropdown

Das Dropdown-Menü ist in fünf Kategorien unterteilt:

**Stammdaten:**
- Anlage – PV-Anlage bearbeiten
- Strompreise – Tarife verwalten
- Investitionen – Komponenten konfigurieren

**Daten:**
- Monatsdaten – Energiedaten eingeben/bearbeiten
- Monatsabschluss – Geführter Monatsabschluss-Wizard
- Import – CSV-Import/Export
- Datenerfassung – Automatische Datenerfassung konfigurieren
- Demo-Daten – Testdaten laden

**System:**
- Solarprognose – PVGIS-Prognose und Wetter-Provider
- Daten-Checker – Datenqualitäts-Prüfung
- Protokolle – Aktivitäts-Logging
- Allgemein – Version, Status

**Home Assistant** (nur bei HA-Nutzung sichtbar):
- Sensor-Zuordnung – HA-Sensoren zu EEDC-Feldern zuordnen
- Statistik-Import – Bulk-Import aus HA-Langzeitstatistik
- MQTT-Export – MQTT Auto-Discovery Konfiguration
- MQTT-Inbound – Universelle Datenbrücke konfigurieren

**Community:**
- Daten teilen – Anonyme Daten an Community-Server senden

### Sub-Navigation (kontextabhängig)

Unter der Hauptnavigation erscheinen kontextabhängige Links:

**Cockpit Sub-Seiten:**
- Übersicht | Aktueller Monat | PV-Anlage | E-Auto | Wärmepumpe | Speicher | Wallbox | Balkonkraftwerk | Sonstiges

(Jede Komponente hat ein eigenes Dashboard mit spezifischen KPIs.)

---

## 2. Live Dashboard

Das Live Dashboard zeigt dir **Echtzeit-Leistungsdaten** deiner gesamten PV-Anlage auf einen Blick.

### Energiefluss-Diagramm

Das zentrale Element ist ein **animiertes Energiefluss-Diagramm** (ähnlich dem HA Energy Dashboard):

- **Haus** in der Mitte als Senke
- **Erzeuger** (PV-Module) oben
- **Netz** links (bidirektional: Bezug/Einspeisung)
- **Speicher** (Batterie) rechts (bidirektional: Laden/Entladen)
- **Verbraucher** (Wärmepumpe, Wallbox, E-Auto, Sonstige) unten

**Animierte Flusslinien** zeigen Richtung und Stärke des Energieflusses:
- Liniendicke proportional zur Leistung (logarithmisch skaliert)
- Animationsgeschwindigkeit proportional zur Leistung
- Farbcodierung nach Komponententyp

**SoC-Anzeige:** Bei Batterien und E-Autos wird der Ladezustand als Pegel im Knoten dargestellt (rot <20%, gelb 20-50%, grün >50%).

### Gauges

Halbkreis-Gauges zeigen den **State of Charge** (SoC) von Speichern und E-Autos in Prozent.

### Tageswerte

Unter den Knoten werden die **heutigen kWh-Werte** als Tooltip angezeigt (Datenquelle: HA-Statistik oder MQTT-Snapshots).

### Datenquellen

Das Live Dashboard nutzt Echtzeit-Daten aus:
1. **Home Assistant Sensoren** — via konfiguriertem Sensor-Mapping (→ siehe [Teil III, §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping))
2. **MQTT-Inbound** — universelle Datenbrücke für beliebige Smarthome-Systeme (→ siehe [Teil III, §6 MQTT-Inbound](HANDBUCH_EINSTELLUNGEN.md#6-mqtt-inbound))

### Demo-Modus

Ohne konfigurierte Sensoren zeigt das Dashboard einen **Demo-Modus** mit simulierten Werten, damit du die Darstellung vorab testen kannst.

---

## 3. Cockpit (Dashboards)

Das Cockpit zeigt dir alle wichtigen Kennzahlen auf einen Blick.

### 3.1 Übersicht

Das Cockpit zeigt alle wichtigen Kennzahlen auf einen Blick – ab v2.3.0 modernisiert:

#### Hero-Leiste (oben)
Die drei wichtigsten KPIs prominent dargestellt, jeweils mit Trend-Pfeil zum Vorjahr:
- **Autarkie** (%), **Spezifischer Ertrag** (kWh/kWp), **Netto-Ertrag** (€)

#### Energie-Fluss-Diagramm
Zwei gestapelte Balkendiagramme zeigen:
- **PV-Verteilung**: Wohin fließt der erzeugte Strom? (Direktverbrauch / Speicher / Einspeisung)
- **Haus-Versorgung**: Woher kommt der Strom im Haus? (PV direkt / Speicher / Netzbezug)

#### Energiebilanz
- **PV-Erzeugung** – Gesamte Stromerzeugung in kWh
- **Direktverbrauch** – Sofort selbst verbrauchter PV-Strom
- **Einspeisung** – Ins Netz eingespeister Überschuss
- **Netzbezug** – Aus dem Netz bezogener Strom
- **Sparkline** – Monatserträge als kompaktes Balkendiagramm über den Gesamtzeitraum

#### Effizienz-Quoten (Ring-Gauges)
Anschauliche Ringdiagramme statt reiner Zahlen:
- **Autarkie** = (Gesamtverbrauch - Netzbezug) / Gesamtverbrauch × 100%
- **Eigenverbrauchsquote** = Eigenverbrauch / PV-Erzeugung × 100%

#### Komponenten-Status
Schnellstatus für alle Komponenten mit Klick-Navigation zu Details.

#### Finanzielle Auswertung
- Einspeiseerlös, eingesparte Stromkosten, Gesamt-Einsparung (€)
- **Amortisations-Fortschrittsbalken**: Wie viel % der Investition ist zurückgeflossen? Mit geschätztem Amortisationsjahr (nur in der Gesamtansicht)
- **Methodenhinweis**: Amortisationsbalken und Komponenten-Dashboards (E-Auto, WP, BKW) zeigen einen Basis-Hinweis zur Berechnungsmethode

#### CO2-Bilanz
- Vermiedene CO2-Emissionen (kg)
- Vergleich zu reinem Netzbezug

#### Social-Media-Textvorlage

Über das **Share-Icon** (↗) im Dashboard-Header kannst du einen kopierfertigen Text für Social-Media-Posts generieren:

1. **Monat/Jahr wählen** – Standard: letzter verfügbarer Monat
2. **Variante wählen**:
   - **Kompakt** – Für Twitter/X und kurze Posts (mit Hashtags)
   - **Ausführlich** – Für Facebook-Gruppen und Foren (mit Emojis und Details)
3. **Vorschau** – Der generierte Text wird sofort angezeigt
4. **Kopieren** – Mit einem Klick in die Zwischenablage

Der Text enthält automatisch:
- Anlagenleistung (kWp), Ausrichtung, Bundesland
- Erzeugung, Autarkie, Eigenverbrauchsquote
- PVGIS-Prognose-Vergleich (wenn vorhanden)
- Speicher, Wärmepumpe, E-Auto (nur wenn vorhanden)
- CO₂-Einsparung und Netto-Ertrag

### 3.2 PV-Anlage Dashboard

Detailansicht für deine Photovoltaik:

- **Wechselrichter-Übersicht** mit zugeordneten Modulen
- **String-Vergleich** nach Ausrichtung (Süd, Ost, West)
- **Spezifischer Ertrag** (kWh/kWp) – wichtig für Vergleiche
- **SOLL-IST Vergleich** gegen PVGIS-Prognose

#### SOLL-IST Vergleich verstehen

| Kennzahl | Bedeutung |
|----------|-----------|
| **SOLL (PVGIS)** | Erwarteter Ertrag basierend auf Standort, Ausrichtung, Neigung |
| **IST** | Tatsächlich gemessener Ertrag |
| **Abweichung** | Positiv = besser als erwartet, Negativ = schlechter |

**Typische Abweichungen:**
- ±5% – Normal (Wetterschwankungen)
- ±10-15% – Prüfen (Verschattung? Verschmutzung?)
- >20% – Handlungsbedarf (Defekt? Fehlkonfiguration?)

### 3.3 E-Auto Dashboard

- **Gefahrene Kilometer** im Zeitraum
- **Verbrauch** (kWh)
- **Ladequellen-Aufteilung**:
  - PV-Ladung (kostenlos)
  - Netz-Ladung (zu Hause)
  - Externe Ladung (unterwegs)
- **Kostenersparnis** vs. Benziner/Diesel
- **V2H-Entladung** (wenn aktiviert)

### 3.4 Speicher Dashboard

- **Ladezyklen** (Vollzyklen)
- **Effizienz** = Entladung / Ladung × 100%
- **Degradation** (Kapazitätsverlust über Zeit)
- **Arbitrage-Analyse** (wenn aktiviert):
  - Netzladung zu günstigem Strom
  - Entladung bei hohem Preis
  - Arbitrage-Gewinn

### 3.5 Wärmepumpe Dashboard

- **Stromverbrauch** (kWh)
- **Erzeugte Wärme** (kWh)
- **COP** (Coefficient of Performance) = Wärme / Strom
- **Aufteilung**: Heizung vs. Warmwasser
- **Einsparung** vs. Gas/Öl-Heizung

### 3.6 Wallbox Dashboard

- **Geladene Energie** (kWh)
- **Ladevorgänge** (Anzahl)
- **Durchschnittliche Lademenge**
- **PV-Anteil** der Ladungen

### 3.7 Balkonkraftwerk Dashboard

- **Erzeugung** (kWh) - Stromerzeugung des BKW
- **Eigenverbrauch** (kWh) - Selbst genutzter BKW-Strom
- **Einspeisung** (kWh) - Unvergütete Einspeisung (= Erzeugung - Eigenverbrauch)
- **Optional**: Speicher-Nutzung (Ladung/Entladung)

### KPI-Tooltips

Jede Kennzahl zeigt bei Hover einen Tooltip mit:
- **Formel**: Wie wird der Wert berechnet?
- **Berechnung**: Konkrete Zahlen eingesetzt
- **Ergebnis**: Der angezeigte Wert

---

## 4. Aktueller Monat

**Pfad**: Cockpit → Aktueller Monat

Das Aktueller-Monat-Dashboard zeigt den **laufenden Monat** mit Daten aus verschiedenen Quellen:

### Datenquellen (nach Priorität)

| Quelle | Konfidenz | Beschreibung |
|--------|-----------|--------------|
| **HA-Statistik** | 95% | Direkt aus der HA Recorder-Datenbank |
| **MQTT-Inbound** | 91% | Aus MQTT Energy-Snapshots |
| **Connector** | 90% | Aus Geräte-Connector-Abfrage |
| **Gespeichert** | 85% | Bereits abgeschlossene Monatsdaten |

### Anzeige

- **Energie-Bilanz-Charts** — PV-Erzeugung, Einspeisung, Netzbezug, Eigenverbrauch
- **Komponenten-Karten** — Status jeder Investition mit kWh-Werten
- **Datenquellen-Badges** — Farbige Indikatoren zeigen pro Feld die Herkunft
- **Finanz-Übersicht** — Geschätzte Einsparung im laufenden Monat
- **Vorjahresvergleich** — Delta zum gleichen Monat im Vorjahr
- **SOLL/IST-Vergleich** — Gegen PVGIS-Prognose

### Leerer Zustand

Wenn keine Daten vorliegen, werden konkrete Import-Möglichkeiten als Aktionskarten angeboten (Monatsabschluss, Connector, Cloud-Import, Portal-Import).

---

## 5. Auswertungen

Detaillierte Analysen in 6 Kategorien. Der Community-Vergleich ist seit v2.1.0 ein eigenständiger Hauptmenüpunkt.

### 5.1 Energie-Tab

**Jahresvergleich** mit:
- Monats-Charts für alle Energieflüsse
- Delta-Indikatoren (Δ%) zum Vorjahr
- Jahres-Summentabelle

**Visualisierungen:**
- Gestapelte Balkendiagramme (Erzeugung, Verbrauch, Einspeisung)
- Liniendiagramme für Trends
- Torten-/Donut-Charts für Anteile

### 5.2 PV-Anlage Tab

- **String-Performance** über Zeit
- **Ertrag pro Modul** in kWh und kWh/kWp
- **Ausrichtungs-Vergleich**: Welcher String performt am besten?
- **Degradations-Analyse** (Jahr-über-Jahr)

### 5.3 Komponenten Tab

Detaillierte Zeitreihen für jede Komponente:

**Speicher:**
- Ladung/Entladung im Zeitverlauf
- Arbitrage-Gewinne (wenn aktiviert)
- Vollzyklen und Effizienz

**E-Auto:**
- Ladequellen-Aufteilung (PV/Netz/Extern)
- V2H-Entladung (wenn aktiviert)
- Kostenentwicklung

**Wärmepumpe:**
- Heizung vs. Warmwasser getrennt
- COP-Entwicklung über die Saison

### 5.4 Finanzen Tab

- **Einspeiseerlös** = Einspeisung × Einspeisevergütung
- **Eingesparte Stromkosten** = Eigenverbrauch × Bezugspreis
- **Sonderkosten** (Reparaturen, Wartung)
- **Netto-Einsparung** = Erlöse + Einsparungen - Sonderkosten

### 5.5 CO2 Tab

- **Vermiedene Emissionen** (kg CO2)
- **Berechnung**: Eigenverbrauch × CO2-Faktor Strommix
- **Zeitreihe** der CO2-Einsparung
- **Äquivalente**: z.B. "entspricht X km Autofahren"

### 5.6 Investitionen Tab (ROI)

Das **ROI-Dashboard** zeigt:

#### Amortisationskurve
- X-Achse: Zeit (Jahre)
- Y-Achse: Kumulierte Einsparung vs. Investition
- **Break-Even-Punkt**: Wann ist die Investition zurückverdient?

#### ROI pro Komponente
Tabelle mit:
| Spalte | Bedeutung |
|--------|-----------|
| **Investition** | Kaufpreis + Installation |
| **Jährliche Einsparung** | Durchschnitt pro Jahr |
| **ROI** | (Einsparung - Kosten) / Kosten × 100% |
| **Amortisation** | Jahre bis Break-Even |

#### Realisierungsquote

Ein neues Panel vergleicht die historischen Erträge mit der konfigurierten Prognose:
- **≥90%** (grün): Ertrag entspricht oder übertrifft die Erwartung
- **≥70%** (gelb): Leichte Abweichung, ggf. prüfen
- **<70%** (rot): Deutliche Abweichung, Handlungsbedarf

#### PV-System Aggregation

**Wichtig**: Wechselrichter + zugeordnete PV-Module + DC-Speicher werden als "PV-System" zusammengefasst!

- Die ROI-Berechnung erfolgt auf System-Ebene
- Einzelkomponenten sind in aufklappbaren Unterzeilen sichtbar
- Einsparungen werden proportional nach kWp verteilt

### 5.7 Tabellen-Tab (Energie-Explorer)

Der **Tabellen-Tab** bietet einen interaktiven Überblick aller Monatswerte in einer sortierbaren Tabelle — ideal für eigene Analysen und schnelle Jahresvergleiche.

#### Inhalt

- **22 Spalten**: Alle Energiefelder (Erzeugung, Einspeisung, Bezug, Direktverbrauch, Speicher, Wärmepumpe, E-Auto, Wallbox, Finanzen, CO2, ...)
- **Vorjahresvergleich**: Jede Zeile zeigt optional den Δ-Wert zum gleichen Monat im Vorjahr, farbkodiert (grün = besser, rot = schlechter)
- **Deutsches Zahlenformat**: Komma als Dezimaltrennzeichen, Punkt als Tausender

#### Sortierung

Klicke auf einen Spalten-Header, um nach dieser Spalte zu sortieren. Erneuter Klick wechselt die Richtung. Standard: chronologisch.

#### Spaltenauswahl

Über den Button **"Spalten"** (oben rechts in der Tabelle) wählst du aus, welche Spalten angezeigt werden. Die Auswahl wird im Browser gespeichert (localStorage) und bleibt auch nach einem Neustart erhalten.

#### Export

Den sichtbaren Tabelleninhalt kannst du als **CSV exportieren** (Button "CSV" oben rechts). Exportiert werden alle Zeilen und die aktuell eingeblendeten Spalten.

---

## 6. Community

Der Community-Vergleich ermöglicht anonyme Benchmarks mit anderen PV-Anlagen-Besitzern.
Community ist seit v2.1.0 ein eigenständiger Hauptmenüpunkt (gleichwertig mit Cockpit, Auswertungen, Aussichten).

### 6.1 Daten teilen

**Pfad**: Community → Tab "Übersicht" → Button "Jetzt teilen"

Hier kannst du deine Anlagendaten anonym mit der Community teilen:
- **Vorschau**: Zeigt welche Daten geteilt werden
- **Anonymisierung**: Nur Bundesland, keine Adresse/PLZ
- **Jederzeit löschbar**: Button "Meine Daten löschen"

### 6.2 Community-Bereich (6 Tabs)

Nach dem Teilen stehen alle 6 Community-Tabs mit detaillierten Benchmarks zur Verfügung.

#### Zeitraum-Auswahl
- Letzter Monat
- Letzte 12 Monate
- Letztes vollständiges Jahr
- Bestimmtes Jahr
- Seit Installation

#### Tab: Übersicht
- **Radar-Chart**: Eigene Performance vs. Community auf 6 Achsen
- **Ranking**: Platz X von Y Anlagen (gesamt und regional)
- **7 Achievements**: Autarkiemeister, Effizienzwunder, Solarprofi, Speicherheld, Klimaschützer, Frühstarter, Vorreiter

#### Tab: PV-Ertrag
- **Dein spezifischer Ertrag** (kWh/kWp) vs. Community-Durchschnitt
- **Monatlicher Vergleich**: Deine Werte vs. Community als Chart
- **Histogramm**: Wo stehst du in der Verteilung?

#### Tab: Komponenten
Detaillierte Benchmarks für jede Komponente:

| Komponente | KPIs |
|------------|------|
| **Speicher** | Zyklen, Effizienz, Autarkie-Beitrag |
| **Wärmepumpe** | JAZ vs. Community, PV-Anteil |
| **E-Auto** | km/Monat, Ø kWh/100km, PV-Anteil |
| **Wallbox** | Ladung kWh/Mon, PV-Anteil % |
| **Balkonkraftwerk** | Ertrag kWh/Mon, Vergleich |

#### Tab: Regional
- **Choropleth Deutschlandkarte**: Interaktive Karte mit Farbkodierung nach spezifischem Ertrag
  - Hover über ein Bundesland zeigt Performance-Details: Speicher-Lade/Entlade-kWh, WP-JAZ, E-Auto km + kWh, Wallbox kWh + PV-Anteil, BKW kWh
- **Bundesland-Tabelle**: Direkter Vergleich aller Bundesländer mit Performance-Metriken (Ø kWh/Mon, JAZ, etc.)
- **Regionale Einordnung**: Wie schneidet dein Bundesland ab?

#### Tab: Trends
- **Ertragsverlauf**: Community-Trend über Zeit
- **Saisonale Performance**: Beste und schlechteste Monate
- **Jahresvergleich**: Entwicklung der Community

#### Tab: Statistiken
- **Ausstattungsquoten**: Wie viele Anlagen haben Speicher, WP, E-Auto etc.?
- **Top-10-Listen**: Beste Anlagen nach verschiedenen Kategorien
- **Community-Übersicht**: Gesamtanzahl Anlagen, Regionen, Durchschnittswerte

### 6.3 Datenschutz

- Nur aggregierte Statistiken werden angezeigt
- Kein Rückschluss auf einzelne Anlagen möglich
- Daten können jederzeit wieder gelöscht werden
- Server: https://energy.raunet.eu (Open Source)

---

## 7. Aussichten (Prognosen)

Die **Aussichten**-Seite bietet 4 Prognose-Tabs für zukunftsorientierte Analysen.

### 7.1 Kurzfristig (7 Tage)

Wetterbasierte Ertragsschätzung für die nächsten 7 Tage:

- **Datenquelle**: Open-Meteo Wetterprognose
- **Anzeige**: Tägliche Erzeugungsschätzung basierend auf Globalstrahlung
- **Wettersymbole**: Sonnig, bewölkt, regnerisch
- **Datenquelle-Kürzel** pro Tag: MS (MeteoSwiss ICON-CH2), D2 (ICON-D2), EU (ICON-EU), EC (ECMWF IFS), BM (best_match)
- **Solar Forecast ML (SFML)**: Wenn SFML konfiguriert ist, erscheint im Chart eine zweite Linie mit dem KI-basierten Ertrag zum Vergleich mit der EEDC-Prognose und dem tatsächlichen IST-Wert

Das verwendete Wettermodell lässt sich pro Anlage im Dropdown **Anlage → Wettermodell** auf einen fixen Anbieter umstellen (z.B. MeteoSwiss ICON-CH2 für alpine Standorte). Ohne Auswahl wählt EEDC automatisch (auto).

### 7.2 Langfristig (12 Monate)

PVGIS-basierte Jahresprognose:

- **Datenquelle**: PVGIS-Erwartungswerte oder TMY
- **Performance-Ratio**: Historischer Vergleich IST vs. SOLL
- **Monatliche Aufschlüsselung**: Erwartete Erzeugung pro Monat

### 7.3 Trend-Analyse

Langfristige Entwicklung und Degradation:

- **Jahresvergleich**: Alle bisherigen Jahre im Vergleich
- **Saisonale Muster**: Beste und schlechteste Monate identifizieren
- **Degradation**: Geschätzter Leistungsrückgang pro Jahr
  - Primär: Nur vollständige Jahre (12 Monate)
  - Fallback: TMY-Auffüllung für unvollständige Jahre

### 7.4 Finanzen

Amortisations-Prognose und Komponenten-Beiträge:

**Amortisations-Fortschritt:**
- Zeigt wie viel % der Investition bereits amortisiert ist
- **Wichtig**: Dies ist der *kumulierte* Fortschritt, nicht die Jahres-Rendite!

**Mehrkosten-Ansatz für Investitionen:**
- **PV-System**: Volle Kosten (keine Alternative)
- **Wärmepumpe**: Kosten minus Gasheizung (konfigurierbar über `alternativ_kosten_euro`)
- **E-Auto**: Kosten minus Verbrenner (konfigurierbar über `alternativ_kosten_euro`)

**Komponenten-Beiträge:**
- Speicher: Eigenverbrauchserhöhung
- E-Auto (V2H): Rückspeisung ins Haus
- E-Auto (vs. Benzin): Ersparnis gegenüber Verbrenner (ab v3.17.0 mit echten monatlichen Benzinpreisen aus EU Oil Bulletin)
- Wärmepumpe (PV): Direktverbrauch aus PV
- Wärmepumpe (vs. Gas): Ersparnis gegenüber Gasheizung

> **Hinweis:** Die Finanz-Prognose zeigt den **Amortisations-Fortschritt** (kumulierte Erträge / Investition).
> Im Cockpit und in Auswertung/Investitionen wird dagegen die **Jahres-Rendite** (Jahres-Ertrag / Investition) angezeigt.
> Beide Metriken sind korrekt, aber für unterschiedliche Zwecke gedacht.

---

---

## 8. Infothek

Die **Infothek** ist ein optionales Modul für Verträge, Zähler, Kontakte und Dokumente rund um deine Energieversorgung. Der Menüpunkt erscheint sobald der erste Eintrag angelegt wurde.

**Funktionen im Überblick:**
- 14 Kategorien mit passenden Vorlagen-Feldern (Strom-, Gas-, Wasservertrag, Versicherung, Wartung, MaStR, ...)
- Bis zu 3 Fotos oder PDFs pro Eintrag (JPEG, PNG, HEIC, PDF)
- Optionale Verknüpfung mit EEDC-Investitionen
- PDF-Export aller Einträge für den Hefter
- Archivierung statt Löschung

Eine vollständige Beschreibung aller Kategorien, Upload-Optionen und des PDF-Exports findest du im separaten Handbuch:

→ [HANDBUCH_INFOTHEK.md](HANDBUCH_INFOTHEK.md)

---

*Letzte Aktualisierung: März 2026*
