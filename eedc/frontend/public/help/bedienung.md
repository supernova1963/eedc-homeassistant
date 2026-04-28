
# EEDC Handbuch — Teil II: Bedienung

**Version 3.24.1** | Stand: April 2026

> Dieses Handbuch ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Navigation & Menüstruktur](#1-navigation--menüstruktur)
2. [Live Dashboard](#2-live-dashboard)
3. [Cockpit (Dashboards)](#3-cockpit-dashboards)
4. [Monatsberichte](#4-monatsberichte)
5. [Auswertungen](#5-auswertungen)
6. [Community](#6-community)
7. [Aussichten (Prognosen)](#7-aussichten-prognosen)
8. [Infothek](#8-infothek)
9. [Hilfe (in der App)](#9-hilfe-in-der-app)

---

## 1. Navigation & Menüstruktur

### Hauptnavigation (oben)

Die horizontale Navigation enthält fünf Hauptbereiche:

| Bereich | Funktion |
|---------|----------|
| **Live** | Echtzeit-Leistungsdaten mit animiertem Energiefluss-Diagramm |
| **Cockpit** | Übersicht, Monatsberichte und Komponenten-Dashboards |
| **Auswertungen** | 8 Tabs für detaillierte Analysen, inkl. Energieprofil (Beta) |
| **Community** | Anonymer Benchmark-Vergleich mit anderen PV-Anlagen |
| **Aussichten** | Prognosen: Kurzfristig, Prognosen-Vergleich, Langfristig, Trend, Finanzen |

Plus ein Dropdown-Menü für **Einstellungen**, der Hauptmenüpunkt **Hilfe** und – sobald mindestens ein Eintrag existiert – die **Infothek**.

### Einstellungen-Dropdown

Das Dropdown-Menü ist in Kategorien unterteilt:

**Stammdaten:**
- Anlage – PV-Anlage bearbeiten
- Strompreise – Tarife verwalten
- Investitionen – Komponenten konfigurieren
- Solarprognose – PVGIS-Prognose und Wetter-Provider

**Daten:**
- Monatsdaten – Energiedaten eingeben/bearbeiten + Kraftstoffpreis-Backfill (Monatsebene)
- Energieprofil – Tages-Tabelle, Vollbackfill, Datenverwaltung pro Anlage
- Monatsabschluss – Geführter Monatsabschluss-Wizard
- Import – CSV-Import/Export
- Datenerfassung – Automatische Datenerfassung konfigurieren
- Demo-Daten – Testdaten laden

**System:**
- Daten-Checker – Datenqualitäts-Prüfung
- Protokolle – Aktivitäts-Logging
- Allgemein – Theme, HA-Integration, Datenbank-Info

**Home Assistant** (nur bei HA-Nutzung sichtbar):
- Sensor-Zuordnung – HA-Sensoren zu EEDC-Feldern zuordnen
- Statistik-Import – Bulk-Import aus HA-Langzeitstatistik
- MQTT-Export – MQTT Auto-Discovery Konfiguration
- MQTT-Inbound – Universelle Datenbrücke konfigurieren

**Community:**
- Daten teilen – Anonyme Daten an Community-Server senden

### Sub-Navigation (kontextabhängig)

Unter der Hauptnavigation erscheinen kontextabhängige Links:

**Cockpit-Sub-Tabs** (Reihenfolge: Erzeuger oben, Speicher in der Mitte, Verbraucher unten):
Übersicht → Monatsberichte → PV-Anlage → Balkonkraftwerk → Speicher → Wärmepumpe → Wallbox → E-Auto → Sonstiges

Jeder Investitions-Tab erscheint nur, wenn mindestens ein Investment des passenden Typs angelegt ist.

> **Hinweis zum Layout:** EEDC ist als datendichte Analyse-App primär für den Desktop konzipiert. Live-Dashboard, Cockpit-Übersicht und Monatsberichte funktionieren am Smartphone gut. Für die datendichten Tabellen in Auswertung → Energieprofil und Aussichten → Prognosen empfehlen wir Querformat oder Desktop. Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom) können einzelne Layouts eng werden — eine bewusste Designentscheidung statt Layout-Patches, die den datendichten Charakter aufweichen würden.

---

## 2. Live Dashboard

Das Live Dashboard zeigt dir **Echtzeit-Leistungsdaten** deiner gesamten PV-Anlage auf einen Blick. Aktualisiert sich alle 5 Sekunden.

### Energiefluss-Diagramm

Das zentrale Element ist ein **animiertes Energiefluss-Diagramm** (ähnlich dem HA Energy Dashboard):

- **Haus** in der Mitte als Senke
- **Erzeuger** (PV-Module, Balkonkraftwerk) oben
- **Netz** links (bidirektional: Bezug/Einspeisung)
- **Speicher** (Batterie) rechts (bidirektional: Laden/Entladen)
- **Verbraucher** (Wärmepumpe, Wallbox, E-Auto, Sonstige) unten

**Animierte Flusslinien** zeigen Richtung und Stärke des Energieflusses:
- Liniendicke proportional zur Leistung (logarithmisch skaliert)
- Animationsgeschwindigkeit proportional zur Leistung (höhere kW = schnellerer Fluss)
- Farbcodierung nach Komponententyp
- Netz-Farbe dynamisch: grün (Balance), orange (Einspeisung), rot (Netzbezug)

**SoC-Anzeige:** Bei Batterien und E-Autos wird der Ladezustand als Pegel im Knoten dargestellt (rot <20%, gelb 20-50%, grün >50%).

**Hintergrund-Varianten** (Auswahl im Live-Header): Sterne (Default), Sunset, Alps oder eigenes Foto aus der Anlagen-Galerie. Dezent und animiert.

**Lite- vs. Effekt-Modus:** Auf iPads und schwächeren Mobile-Geräten erkennt EEDC die Plattform automatisch und schaltet auf einen reduzierten Lite-Modus (CSS-animierte Stromlinien, ohne SVG-Partikel und Filter). Im Effekt-Modus laufen zusätzlich Sonnenstrahlen, Reflexionen, Schneefunkeln und SoC-Partikel. Manueller Toggle im Header möglich.

### Tageswerte (Bilanz-Sortierung)

Unterhalb des Diagramms zeigt EEDC die Heute-Werte als Kacheln in dieser Reihenfolge — **bilanztreu**, von Quellen über Eigenverbrauch zu Verbrauchern:

1. **PV-Erzeugung** (Heute, kWh)
2. **Batterie** (Lade- und Entladebilanz)
3. **Eigenverbrauch** (in % der PV-Erzeugung, gecappt auf 100 % — bei zusätzlicher Batterie-Entladung aus Vortagen kann die Quote rechnerisch über 100 % laufen, das ist visuell nicht sinnvoll)
4. **Netzbezug**
5. **Hausverbrauch**
6. **Einspeisung** (PV-Überschuss ins Netz)

### Tagesverlauf-Chart

Linien-/Flächendiagramm für PV/Verbrauch/Speicher mit gepunkteter **Strompreis-Overlay-Linie** auf sekundärer Y-Achse:

- **Eigener Strompreis-Sensor** im Sensor-Mapping (Tibber, aWATTar, EPEX, eigener Template-Sensor) → Linie heißt „Strompreis"
- **Kein eigener Sensor** → automatischer EPEX-Börsenpreis-Fallback (DE/AT via aWATTar API) → Linie heißt „Börsenpreis (EPEX)"
- Auch die frühen Morgenstunden vor dem ersten Sensor-Datenpunkt werden vom Börsenpreis-Fallback aufgefüllt.
- Klick auf einen Legenden-Eintrag schaltet die Serie ein/aus.

### Wetter-Widget

Aktuelle Außentemperatur, Wolkenbedeckung und Stunden-Prognose als kleines Tile. Stunden-Werte werden als arithmetisches Mittel der 10-Min-Slots aggregiert (konsistent mit der Mean-Konvention der Prognose-Linien).

### Datenquellen

Das Live Dashboard nutzt Echtzeit-Daten aus:
1. **Home Assistant Sensoren** — via konfiguriertem Sensor-Mapping (→ siehe [Teil III, §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping))
2. **MQTT-Inbound** — universelle Datenbrücke für beliebige Smarthome-Systeme (→ siehe [Teil III, §6 MQTT-Inbound](HANDBUCH_EINSTELLUNGEN.md#6-mqtt-inbound))

### Demo-Modus

Ohne konfigurierte Sensoren zeigt das Dashboard einen **Demo-Modus** mit simulierten Werten, damit du die Darstellung vorab testen kannst.

---

## 3. Cockpit (Dashboards)

Das Cockpit zeigt dir alle wichtigen Kennzahlen auf einen Blick, gruppiert in einer Übersicht und Detail-Dashboards pro Komponententyp.

### 3.1 Übersicht

Das Cockpit zeigt alle wichtigen Kennzahlen auf einen Blick.

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
Schnellstatus für alle Komponenten mit Klick-Navigation zu den Detail-Dashboards. Wärmepumpe-, Speicher-, E-Auto- und Wallbox-KPIs verwenden konsistente Icons, Farben und Reihenfolgen über alle Cockpit-Sichten und Auswertungen hinweg.

#### Finanzielle Auswertung
- Einspeiseerlös, eingesparte Stromkosten, Gesamt-Einsparung (€)
- **Amortisations-Fortschrittsbalken**: Wie viel % der Investition ist zurückgeflossen? Mit geschätztem Amortisationsjahr (nur in der Gesamtansicht)
- **„Sicht"-Tooltip** an jeder ROI-/Amortisations-Anzeige: Klärt explizit, ob die Zahl pro Investition oder gesamt, Jahres-ROI oder kumuliert, IST oder Prognose darstellt — die App zeigt mehrere ROI-Sichten parallel, der Tooltip macht die jeweilige Bedeutung sofort sichtbar.

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

### 3.2 Monatsberichte

Eigener Tab im Cockpit für die Monatssicht (ersetzt seit v3.12.0 den früheren „Aktueller Monat"-Tab). Details siehe [§4 Monatsberichte](#4-monatsberichte).

### 3.3 PV-Anlage Dashboard

Detailansicht für deine Photovoltaik:

- **Wechselrichter-Übersicht** mit zugeordneten Modulen
- **String-Vergleich** nach Ausrichtung (Süd, Ost, West)
- **Spezifischer Ertrag** (kWh/kWp) – wichtig für Vergleiche
- **SOLL-IST Vergleich** gegen PVGIS-Prognose

Bei **Einzel-String-Anlagen** (genau eine PV-Modul-Investition) wird die „Stringsumme"-Zeile ausgeblendet — sie wäre identisch mit der einzigen Detail-Zeile.

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

### 3.4 Balkonkraftwerk Dashboard

- **Erzeugung** (kWh) — Stromerzeugung des BKW
- **Eigenverbrauch** (kWh) — Selbst genutzter BKW-Strom
- **Einspeisung** (kWh) — Unvergütete Einspeisung (= Erzeugung − Eigenverbrauch)
- **Optional**: Speicher-Nutzung (Ladung/Entladung)

### 3.5 Speicher Dashboard

- **Ladezyklen** (Vollzyklen) — basieren ausschließlich auf dem stationären Speicher-SoC, E-Auto-SoC wird seit v3.22.0 zuverlässig ausgeschlossen
- **Effizienz** = Entladung / Ladung × 100% (Activity-Icon, cyan — konsistent über alle Sichten)
- **Degradation** (Kapazitätsverlust über Zeit)
- **Arbitrage-Analyse** (wenn aktiviert):
  - Netzladung zu günstigem Strom
  - Entladung bei hohem Preis
  - Arbitrage-Gewinn

### 3.6 Wärmepumpe Dashboard

KPI-Reihenfolge (konsistent über Cockpit-Übersicht, WP-Dashboard, Auswertung→Komponenten und Monatsabschluss):

1. **JAZ** (Jahresarbeitszahl) — Wärme ÷ Strom über den gewählten Zeitraum (Thermometer-Icon, orange)
2. **Wärme** (kWh) — erzeugte Heizwärme + Warmwasser (Flame-Icon, rot)
3. **Strom** (kWh) — verbrauchter Strom der Wärmepumpe (Zap-Icon, gelb)
4. **Ersparnis** (€) — vs. Alternative (Gas/Öl) (TrendingUp-Icon, grün)

Innerhalb des Tabs zusätzlich: JAZ-Heizen / JAZ-Warmwasser, Monatsvergleichs-Toggle, Detail-Tabellen mit Spalte „JAZ" pro Monat.

> **Hinweis JAZ vs. COP:** Im Cockpit/Dashboard-Periodenwert nutzen wir konsistent **JAZ** (Jahresarbeitszahl, ggf. periodenanteilig). Der Begriff **COP** (Coefficient of Performance) bleibt für mathematisch-technische Berechnungen im Backend reserviert. Im Sensor-Zuordnungs-Wizard ist das Feld als „Jahresarbeitszahl (JAZ)" beschriftet.

> **WP-Anschaffungsdatum-Filter:** Aggregate (JAZ, Wärme, Strom, Ersparnis) im Cockpit und in der Auswertung ignorieren Monatsdaten **vor** dem Anschaffungsdatum der WP-Investition. Bei Migration von einer alten Erfassungs-Methode zu einer neuen (z. B. von WP-eigener Strommessung auf Shelly-PM) bleiben die alten Werte historisch erhalten, fließen aber nicht mehr in die aktuelle JAZ-Berechnung ein.

### 3.7 Wallbox Dashboard

- **Geladene Energie** (kWh)
- **Ladevorgänge** (Anzahl)
- **Durchschnittliche Lademenge**
- **PV-Anteil** der Ladungen

### 3.8 E-Auto Dashboard

- **Gefahrene Kilometer** im Zeitraum
- **Verbrauch** (kWh)
- **Ladequellen-Aufteilung**:
  - PV-Ladung (kostenlos)
  - Netz-Ladung (zu Hause)
  - Externe Ladung (unterwegs)
- **Kostenersparnis** vs. Benziner/Diesel — basiert seit v3.17.0 auf echten **monatlichen Benzinpreisen** aus dem EU Weekly Oil Bulletin (Fallback: statischer Investitions-Parameter)
- **V2H-Entladung** (wenn aktiviert)

### 3.9 Sonstiges

Eigener Tab für sonstige Erzeuger (BHKW etc.) und sonstige Verbraucher mit komponentenspezifischen KPIs.

### Tab-Header und Layout

- Der Tab-Header der Komponenten-Dashboards zeigt den **Anlagennamen** (PV-Anlage) bzw. die **Bezeichnung** des konkreten Investments (z. B. „Wärmepumpe Erdgeschoss") — der Investment-Typ steht bereits im aktiven grünen Sub-Tab und wird nicht doppelt als Überschrift wiederholt.
- Bei **mehreren Investments desselben Typs** trennt eine durchgezogene Linie statt Card-Boxen, die Card-Header tragen die jeweilige `bezeichnung` zur Unterscheidung.

### KPI-Tooltips

Jede Kennzahl zeigt bei Hover/Tap einen Tooltip mit:
- **Formel**: Wie wird der Wert berechnet?
- **Berechnung**: Konkrete Zahlen eingesetzt
- **Ergebnis**: Der angezeigte Wert
- **Sicht**: Bei ROI- und Amortisations-KPIs zusätzlich, welche Bezugsbasis (pro Investition vs. gesamt, IST vs. Prognose)

---

## 4. Monatsberichte

**Pfad**: Cockpit → Monatsberichte

Die Monatsberichte zeigen den **gewählten Monat** mit Daten aus verschiedenen Quellen und ersetzen seit v3.12.0 den früheren „Aktueller Monat"-Tab. Über den Zeitstrahl unter dem Header kannst du zu beliebigen Vormonaten navigieren.

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
- **Finanzen / T-Konto** — Erlöse, Einsparungen, Kosten gegenübergestellt; Vorjahresvergleich mit Δ. Auf Mobile als 2-Spalten-Layout (Label | Wert+VJ+Δ gestapelt).
- **Wärmepumpen-Sektion** — JAZ, Wärme, Strom, Ersparnis (in dieser Reihenfolge). VM-Vergleich nur, wenn der Vormonat tatsächlich WP-Daten hat — bei einer WP, die im Berichtsmonat zum ersten Mal Daten liefert, werden die VM-Spalten unterdrückt statt mit „0"/„NaN" verwirrend angezeigt.
- **Vorjahresvergleich** — Delta zum gleichen Monat im Vorjahr
- **SOLL/IST-Vergleich** — Gegen PVGIS-Prognose
- **Community-Vergleich** — Eingebettet, wo Daten geteilt sind

### Leerer Zustand

Wenn keine Daten vorliegen, werden konkrete Import-Möglichkeiten als Aktionskarten angeboten (Monatsabschluss, Connector, Cloud-Import, Portal-Import).

---

## 5. Auswertungen

Detaillierte Analysen in 8 Tabs (der **Energieprofil**-Tab ist als Beta gekennzeichnet). Reihenfolge:

Energie | PV-Anlage | Komponenten | Finanzen | CO2 | Investitionen | Tabelle | Energieprofil (Beta)

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
- **Performance Ratio**: Seit v3.20.0 auf Basis der **Global Tilted Irradiance (GTI)** statt der horizontalen Globalstrahlung (GHI) — bei steilen Modulen und tiefstehender Wintersonne realistischere Werte (vorher konnten PR-Werte > 1 entstehen, die physikalisch nicht möglich sind).
- **SOLL/IST-Diagramme**: Konsistente Farben (SOLL blau, IST amber, positive Abweichung grün) über alle Charts.

### 5.3 Komponenten Tab

Detaillierte Zeitreihen für jede Komponente:

**Speicher:**
- Ladung/Entladung im Zeitverlauf
- Arbitrage-Gewinne (wenn aktiviert)
- Vollzyklen und Effizienz (cyan, Activity-Icon — konsistent zu Cockpit und Monatsabschluss)

**E-Auto:**
- Ladequellen-Aufteilung (PV/Netz/Extern)
- V2H-Entladung (wenn aktiviert)
- Kostenentwicklung (mit echten monatlichen Benzinpreisen ab v3.17.0)

**Wärmepumpe:**
- Heizung vs. Warmwasser getrennt
- JAZ-Entwicklung über die Saison
- Aggregate respektieren das **Anschaffungsdatum** — Daten aus der Zeit vor der aktuellen Erfassungs-Konfiguration verzerren die Kennzahlen nicht mehr.

### 5.4 Finanzen Tab

- **Einspeiseerlös** = Einspeisung × Einspeisevergütung
- **Eingesparte Stromkosten** = Eigenverbrauch × Bezugspreis
- **Sonderkosten** (Reparaturen, Wartung)
- **Netto-Einsparung** = Erlöse + Einsparungen − Sonderkosten

### 5.5 CO2 Tab

- **Vermiedene Emissionen** (kg CO2)
- **Berechnung**: Eigenverbrauch × CO2-Faktor Strommix
- **Zeitreihe** der CO2-Einsparung
- **Äquivalente**: z. B. „entspricht X km Autofahren"

### 5.6 Investitionen Tab (ROI)

Das **ROI-Dashboard** wurde in v3.21.0 (#140) verschlankt. Es zeigt zwei klar getrennte Sichten und nicht mehr eine Vielzahl paralleler ROI-Werte ohne Bezugsangabe:

#### Amortisationskurve
- X-Achse: Zeit (Jahre)
- Y-Achse: Kumulierte Einsparung vs. Investition
- **Break-Even-Punkt**: Wann ist die Investition zurückverdient?

#### ROI pro Komponente — zwei Sichten

| Sicht | Bezugsbasis | Wann nutzen? |
|---|---|---|
| **Jahres-ROI** | Jahres-Ertrag / Investition | Vergleich mit Geldanlagen, „Wie viel % rendiert die Anlage pro Jahr?" |
| **Kumulierte Amortisation** | Σ Erträge / Investition | Fortschritt zur Refinanzierung, „Wie viel % ist schon zurückgeflossen?" |

Jeder ROI-/Amortisations-Wert in der Tabelle und in den Cards trägt einen **„Sicht"-Tooltip**, der erklärt, welche Variante du gerade siehst (Pro Investition vs. Gesamt-Anlage, Mehrkosten- vs. Vollkosten-Ansatz, IST vs. Prognose).

Tabelle pro Komponente:

| Spalte | Bedeutung |
|--------|-----------|
| **Investition** | Kaufpreis + Installation, bei WP/E-Auto auch der Mehrkosten-Ansatz (Kosten minus Alternativsystem) |
| **Jährliche Einsparung** | Durchschnitt pro Jahr inkl. WP-/E-Auto-/BKW-Komponenten-Beiträgen |
| **ROI** | Jahres-ROI in % |
| **Amortisation** | Jahre bis Break-Even |

#### Realisierungsquote

Vergleicht historische Erträge mit der konfigurierten Prognose:
- **≥90%** (grün): Ertrag entspricht oder übertrifft die Erwartung
- **≥70%** (gelb): Leichte Abweichung, ggf. prüfen
- **<70%** (rot): Deutliche Abweichung, Handlungsbedarf

#### PV-System Aggregation

**Wichtig**: Wechselrichter + zugeordnete PV-Module + DC-Speicher werden als „PV-System" zusammengefasst.

- Die ROI-Berechnung erfolgt auf System-Ebene
- Einzelkomponenten sind in aufklappbaren Unterzeilen sichtbar
- Einsparungen werden proportional nach kWp verteilt

### 5.7 Tabellen-Tab (Energie-Explorer)

Der **Tabellen-Tab** bietet einen interaktiven Überblick aller Monatswerte in einer sortierbaren Tabelle — ideal für eigene Analysen und schnelle Jahresvergleiche.

#### Inhalt
- **22 Spalten**: Alle Energiefelder (Erzeugung, Einspeisung, Bezug, Direktverbrauch, Speicher, Wärmepumpe, E-Auto, Wallbox, Finanzen, CO2, …)
- **Vorjahresvergleich**: Jede Zeile zeigt optional den Δ-Wert zum gleichen Monat im Vorjahr, farbkodiert (grün = besser, rot = schlechter)
- **Deutsches Zahlenformat**: Komma als Dezimaltrennzeichen, Punkt als Tausender

#### Sortierung
Klicke auf einen Spalten-Header, um nach dieser Spalte zu sortieren. Erneuter Klick wechselt die Richtung. Standard: chronologisch.

#### Spaltenauswahl
Über den Button **„Spalten"** (oben rechts) wählst du aus, welche Spalten angezeigt werden. Die Auswahl wird im Browser gespeichert (localStorage) und bleibt auch nach einem Neustart erhalten.

#### Export
Den sichtbaren Tabelleninhalt kannst du als **CSV exportieren** (Button „CSV" oben rechts). Exportiert werden alle Zeilen und die aktuell eingeblendeten Spalten.

### 5.8 Energieprofil-Tab (Beta)

Der **Energieprofil-Tab** macht die feingranularen Stunden-Daten direkt in der Auswertung sichtbar. Er teilt sich Sub-Tabs:

#### Sub-Tab Tagesdetail
- 24h-Tabelle mit Spalten in Gruppen (Peak-Leistungen, Verbrauchs-Komponenten, Performance, Wetter, Strompreise/§51).
- Spalten-Selektor: Welche Gruppen anzeigen? Auswahl persistiert pro Browser.
- **WP-Kompressor-Starts** (Spalte „WP-Starts", default ausgeblendet) — optional pro WP-Investition über einen kumulativen Total-Increasing-Sensor. Stundenwerte und Tagessumme im Footer (#136, v3.24.0).
- Tagessummen im Footer.

#### Sub-Tab Monat
Aufklappbare Sektionen (`<CollapsibleSection>`, Status pro Sektion persistiert):

1. **KPI-Strips** (fix) — Monats-Summen und Δ zum Vormonat
2. **§51 Negativpreis-Analyse** (offen) — Anzahl Stunden mit negativem Börsenpreis, betroffene Einspeisung
3. **Kategorien-Leiste** (offen) — Erzeuger / Verbraucher / Speicher / Wärme im Monat
4. **Tage des Monats** (offen) — komplette Tagestabelle mit Heatmap-Zellfärbung, sticky Σ-Footer (Σ/Ø/max/min je nach Spalte), Negativpreis-Tage mit amber-Streifen + §51-Badge. Pro Zeile ein Refresh-Knopf für „diesen Tag neu aggregieren" (siehe [Teil III, §1 Energieprofil-Seite](HANDBUCH_EINSTELLUNGEN.md))
5. **Heatmap** (offen) — 24h × N Tage, Energie pro Stunde
6. **Geräte / Tagesprofil / Peaks** (zu) — wann läuft welcher Verbraucher

#### Sub-Tab Prognose

Kombinierte Verbrauchs- + PV- + Batterie-Prognose für einen Tag (Etappe 3b Phase A, v3.16.16):

- **Verbrauchsprofil** aus historischen Stundenmitteln (gewichteter Ø, Wochentag-Kaskade, Halbwertszeit 14 Tage)
- **PV-Stundenprofil** aus OpenMeteo GTI (kalibriert mit Lernfaktor) oder Solcast (wenn konfiguriert)
- **Batterie-SoC-Simulation** mit Speicher-voll/leer-Zeitpunkt
- Chart (PV / Verbrauch / Netto + SoC-Overlay), KPI-Cards, Stundentabelle

> **Datenbasis:** Stunden-kWh stammen seit v3.19.0 aus kumulativen Zähler-Snapshots (statt aus 10-Min-Leistungs-Integration), Tageswerte über die Backward-Slot-Konvention (Slot N = Energie [N-1, N), Industriestandard). Bei fehlenden Snapshots zeigt EEDC ein ⚠-Badge — siehe [§7.2 Prognosen-Tab](#72-prognosen) für den klickbaren Reparatur-Popover.

---

## 6. Community

Der Community-Vergleich ermöglicht anonyme Benchmarks mit anderen PV-Anlagen-Besitzern. Community ist seit v2.1.0 ein eigenständiger Hauptmenüpunkt.

### 6.1 Daten teilen

**Pfad**: Community → Tab „Übersicht" → Button „Jetzt teilen"

Hier kannst du deine Anlagendaten anonym mit der Community teilen:
- **Vorschau**: Zeigt welche Daten geteilt werden
- **Anonymisierung**: Nur Bundesland, keine Adresse/PLZ
- **Jederzeit löschbar**: Button „Meine Daten löschen"

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
| **Wärmepumpe** | JAZ vs. Community (typ-spezifischer Vergleich), PV-Anteil |
| **E-Auto** | km/Monat, Ø kWh/100km, PV-Anteil |
| **Wallbox** | Ladung kWh/Mon, PV-Anteil % |
| **Balkonkraftwerk** | Ertrag kWh/Mon, Anzahl × Wp pro Modul |

#### Tab: Regional
- **Choropleth Deutschlandkarte**: Interaktive Karte mit Farbkodierung nach spezifischem Ertrag
  - Hover über ein Bundesland zeigt Performance-Details: Speicher-Lade/Entlade-kWh, WP-JAZ, E-Auto km + kWh, Wallbox kWh + PV-Anteil, BKW kWh
- **Bundesland-Tabelle**: Direkter Vergleich aller Bundesländer mit Performance-Metriken
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

Die **Aussichten**-Seite bietet 5 Tabs für zukunftsorientierte Analysen:

Kurzfristig | Prognosen | Langfristig | Trend | Finanzen

### 7.1 Kurzfristig

Wetterbasierte Ertragsschätzung für die nächsten 7–14 Tage:

- **Datenquelle**: Open-Meteo Wetterprognose
- **Anzeige**: Tägliche Erzeugungsschätzung basierend auf Globalstrahlung (kalibriert mit dem **EEDC-Lernfaktor**, sobald genug IST-Daten vorliegen)
- **Wettersymbole**: Sonnig, bewölkt, regnerisch
- **Datenquelle-Kürzel** pro Tag: MS (MeteoSwiss ICON-CH2), D2 (ICON-D2), EU (ICON-EU), EC (ECMWF IFS), BM (best_match)
- **Solar Forecast ML (SFML)**: Wenn SFML konfiguriert ist, erscheint im Chart eine zweite Linie mit dem KI-basierten Ertrag

Das verwendete Wettermodell lässt sich pro Anlage im Dropdown **Anlage → Wettermodell** auf einen fixen Anbieter umstellen (z. B. MeteoSwiss ICON-CH2 für alpine Standorte). Ohne Auswahl wählt EEDC automatisch (auto).

### 7.2 Prognosen

Der **Prognosen-Tab** ist die Vergleichs- und Evaluierungsfläche für mehrere PV-Prognosequellen (eingeführt v3.16.4, kontinuierlich erweitert bis v3.23.x). Er zeigt vier Quellen nebeneinander:

| Quelle | Bedeutung |
|---|---|
| **OpenMeteo (OM)** | Wetterbasierte Prognose, Standardquelle |
| **EEDC (kalibriert)** | OM × aktueller Lernfaktor — die anlagenspezifisch korrigierte Prognose |
| **Solcast** | Optionale dritte Quelle, entweder via Solcast-API-Key oder über die HA-Integration „BJReplay" |
| **IST** | Tatsächlich gemessener Ertrag (sobald verfügbar) |

#### KPI-Matrix Heute / Morgen / Übermorgen
Tageswerte aller Quellen, mit VM/NM-Split (Vormittag/Nachmittag) — der Split erfolgt am astronomischen **Solar Noon** (proportional, je nach Standort und Datum kann das bis ~30 min von 12:00 abweichen).

#### Stundenprofil-Chart
Vier Linien (IST grün, EEDC orange, Solcast blau, OpenMeteo gelb).

#### 24h-Stundenvergleich + 7-Tage-Vergleich
Tabellarisch, mit Wetter-Symbolen pro Tag und Δ-Spalten farbkodiert (grün < 15 %, gelb 15–30 %, rot > 30 %). Spaltenstruktur ist über alle vier Tabellen des Tabs konsistent (`table-fixed`, `<colgroup>`), OM/EEDC/Solcast/IST stehen vertikal in derselben Linie übereinander.

#### Genauigkeits-Tracking
Über alle Tage mit gleichzeitig verfügbarer Prognose und IST:

- **MAE** (Mean Absolute Error, %): Streuung — Maß für die Schwankungsbreite
- **MBE** (Mean Bias Error, %): systematischer Bias — neutral gefärbt, Vorzeichen ist Information, nicht Wertung
- **Modus „Diagnostisch"** (Toggle im Card-Header): zeigt pro Quelle zwei Boxen — **darüber** (Tage mit Überschätzung, amber) und **darunter** (Tage mit Unterschätzung, sky-blau) mit jeweils Ø-Abweichung in % und Anzahl Tage. Damit wird Asymmetrie sichtbar — z. B. „bei dichten Wolken systematisch zu hoch, bei klarem Himmel zu niedrig" lässt sich nur mit asymmetrischen Lernfaktoren auflösen.

#### Restzeit-Banner Lernfaktor
Wenn der EEDC-Lernfaktor noch nicht aktiv ist, zeigt ein Hinweis-Banner, wie viele Tage mit gültiger Prognose + IST > 0,5 kWh bereits gesammelt sind und wie viele noch bis zur 7-Tage-Schwelle fehlen (z. B. „3 von 7 Tagen, noch 4 Tage").

#### Saisonaler Lernfaktor (MOS-Kaskade)
Sobald genug Daten verfügbar sind, wechselt der Lernfaktor automatisch in eine saisonale Kaskade:

1. **Monatsfaktor** — wenn ≥ 15 Tage im selben Kalendermonat vorhanden
2. **Quartalsfaktor** — wenn ≥ 15 Tage im selben Quartal
3. **30-Tage-Fenster** — Fallback (≥ 7 Tage)

Die jeweils aktive Stufe wird oberhalb der Genauigkeits-Tracking-Card angezeigt.

#### Klickbarer Reparatur-Popover bei IST-Datenlücke
Wenn IST-Werte unvollständig sind (z. B. Snapshot-Lücke durch HA-Statistics-Latenz oder Add-on-Restart), erscheint ein **⚠-Symbol** neben dem Tageswert. Ein Klick auf das Symbol öffnet einen Popover mit:

- konkreter Auflistung der fehlenden Stunden
- kurzer Erklärungstext
- Button **„Tag neu berechnen"** (triggert die Pro-Tag-Reaggregation, holt fehlende Snapshots aus HA-Statistics nach)
- Fallback-Link zum Sensor-Mapping

#### Backward-Slot-Konvention

Alle Quellen im Prognosen-Tab nutzen seit v3.20.0 die **Backward-Slot-Konvention**: Slot N enthält die Energie aus dem Intervall **[N−1, N)** — also „die letzte Stunde". Damit liefert IST um 06:00 noch 0 kWh (Sonne geht erst auf), Slot 0 eines Tages enthält die Energie von 23:00–24:00 des Vortags, und Tagessummen passen exakt zur Stundensummenbildung. Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber).

#### Mobil-Hinweis

Im Hochformat zeigt EEDC anstelle der drei datendichten Tabellen (KPI-Matrix, 7-Tage, Genauigkeits-Tracking) einen Hinweis „Querformat oder Desktop nutzen". Die Stundenvergleich-Tabelle, der Ertrags-Chart und die MAE/MBE-KPIs bleiben auf allen Geräten sichtbar.

### 7.3 Langfristig

PVGIS-basierte Jahresprognose:
- **Datenquelle**: PVGIS-Erwartungswerte oder TMY
- **Performance-Ratio**: Historischer Vergleich IST vs. SOLL (auf GTI-Basis ab v3.20.0)
- **Monatliche Aufschlüsselung**: Erwartete Erzeugung pro Monat

### 7.4 Trend-Analyse

Langfristige Entwicklung und Degradation:
- **Jahresvergleich**: Alle bisherigen Jahre im Vergleich
- **Saisonale Muster**: Beste und schlechteste Monate identifizieren
- **Degradation**: Geschätzter Leistungsrückgang pro Jahr
  - Primär: Nur vollständige Jahre (12 Monate)
  - Fallback: TMY-Auffüllung für unvollständige Jahre

### 7.5 Finanzen

Amortisations-Prognose und Komponenten-Beiträge:

**Amortisations-Fortschritt:**
- Zeigt, wie viel % der Investition bereits amortisiert ist
- **Wichtig**: Dies ist der *kumulierte* Fortschritt, nicht die Jahres-Rendite!

**Mehrkosten-Ansatz für Investitionen:**
- **PV-System**: Volle Kosten (keine Alternative)
- **Wärmepumpe**: Kosten minus Gasheizung (konfigurierbar über `alternativ_kosten_euro`)
- **E-Auto**: Kosten minus Verbrenner (konfigurierbar über `alternativ_kosten_euro`)

**Komponenten-Beiträge:**
- Speicher: Eigenverbrauchserhöhung
- E-Auto (V2H): Rückspeisung ins Haus
- E-Auto (vs. Benzin): Ersparnis gegenüber Verbrenner — seit v3.17.0 mit echten monatlichen Benzinpreisen aus dem EU Weekly Oil Bulletin (Fallback: statischer Investitions-Parameter)
- Wärmepumpe (PV): Direktverbrauch aus PV
- Wärmepumpe (vs. Gas): Ersparnis gegenüber Gasheizung — seit v3.21.0 mit zwei Verfeinerungen:
  - **Zusatzkosten**: Investitions-Parameter `alternativ_zusatzkosten_jahr` (Schornsteinfeger, Wartung, Gaszähler-Grundpreis) wird zu den Alt-Heizungs-Kosten addiert.
  - **Monats-Gaspreis**: Optionales `gaspreis_cent_kwh`-Feld pro Monatsdaten — wenn gepflegt, wird historisch Monat für Monat der gepflegte Preis verwendet. Tarifwechsel ändern damit nicht mehr rückwirkend die ganze Historie.

> **Hinweis:** Die Finanz-Prognose zeigt den **Amortisations-Fortschritt** (kumulierte Erträge / Investition).
> Im Cockpit und in Auswertung/Investitionen wird dagegen die **Jahres-Rendite** (Jahres-Ertrag / Investition) angezeigt.
> Beide Metriken sind korrekt, aber für unterschiedliche Zwecke gedacht — der „Sicht"-Tooltip an jeder Anzeige erklärt jeweils die Bezugsbasis.

---

## 8. Infothek

Die **Infothek** ist ein optionales Modul für Verträge, Zähler, Kontakte und Dokumente rund um deine Energieversorgung. Der Menüpunkt erscheint, sobald der erste Eintrag angelegt wurde.

**Funktionen im Überblick:**
- 14 Kategorien mit passenden Vorlagen-Feldern (Strom-, Gas-, Wasservertrag, Versicherung, Wartung, MaStR, …)
- Bis zu 3 Fotos oder PDFs pro Eintrag (JPEG, PNG, HEIC, PDF)
- Optionale N:M-Verknüpfung mit EEDC-Investitionen (ein Datenblatt für mehrere Investments möglich)
- PDF-Export aller Einträge für den Hefter
- Archivierung statt Löschung

Eine vollständige Beschreibung aller Kategorien, Upload-Optionen und des PDF-Exports findest du im separaten Handbuch:

→ [HANDBUCH_INFOTHEK.md](HANDBUCH_INFOTHEK.md)

---

## 9. Hilfe (in der App)

Die in v3.24.0 eingeführte **Hilfe-Seite** (Menüpunkt „Hilfe" in der Hauptnavigation) rendert das gesamte Benutzerhandbuch direkt in der App. Damit funktioniert die Dokumentation in der HA-Companion-App identisch zum Browser, ohne Tab-Wechsel und ohne Ingress-Login-Probleme.

- **Linke Sidebar** (Desktop) / **Dropdown** (Mobile): Auswahl des Dokuments aus Einstieg / Handbuch / Referenz.
- **URL-Parameter** `?doc=<slug>`: Direktlinks teilbar (z. B. `?doc=bedienung#7-aussichten-prognosen`).
- **Markdown-Links** zwischen den Hilfe-Dokumenten werden intern aufgelöst, externe `.md`-Verweise zur GitHub-Quelle umgeleitet.

> Die Hilfe ist die offizielle Single-Source-of-Truth-Sicht der Doku — siehe auch die jeweilige Web-Version unter https://supernova1963.github.io/eedc-homeassistant/.

---

*Letzte Aktualisierung: April 2026 (v3.24.1)*
