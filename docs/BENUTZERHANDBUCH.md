# EEDC Benutzerhandbuch

**Version 1.0.0-beta.12** | Stand: Februar 2026

---

## Inhaltsverzeichnis

1. [Einführung](#1-einführung)
2. [Installation](#2-installation)
3. [Ersteinrichtung (Setup-Wizard)](#3-ersteinrichtung-setup-wizard)
4. [Navigation & Menüstruktur](#4-navigation--menüstruktur)
5. [Cockpit (Dashboards)](#5-cockpit-dashboards)
6. [Auswertungen](#6-auswertungen)
7. [Aussichten (Prognosen)](#7-aussichten-prognosen)
8. [Einstellungen](#8-einstellungen)
9. [Datenerfassung](#9-datenerfassung)
10. [Home Assistant Integration](#10-home-assistant-integration-optional)
11. [Tipps & Best Practices](#11-tipps--best-practices)
12. [Fehlerbehebung](#12-fehlerbehebung)

---

## 1. Einführung

### Was ist eedc?

**eedc** (Energie Effizienz Data Center) ist eine lokale Software zur Analyse deiner Photovoltaik-Anlage. Die Software hilft dir:

- **Energieflüsse zu verstehen** – Wieviel erzeugst du? Wieviel verbrauchst du selbst?
- **Wirtschaftlichkeit zu analysieren** – Wann amortisiert sich die Investition?
- **Optimierungspotenziale zu erkennen** – Wie kannst du mehr Eigenverbrauch erreichen?
- **Alle Komponenten im Blick zu behalten** – PV-Anlage, Speicher, E-Auto, Wärmepumpe

### Grundprinzipien

1. **Standalone-First**: EEDC funktioniert komplett ohne Home Assistant
2. **Lokale Datenspeicherung**: Alle Daten bleiben auf deinem Server
3. **Monatliche Granularität**: Daten werden pro Monat erfasst und ausgewertet
4. **Flexible Datenquellen**: CSV-Import, manuelle Eingabe, oder Wetter-API

### Systemanforderungen

- **Standalone**: Docker oder Python 3.11+ mit Node.js 18+
- **Home Assistant Add-on**: Home Assistant OS oder Supervised
- **Browser**: Moderner Browser (Chrome, Firefox, Safari, Edge)

---

## 2. Installation

### Option A: Home Assistant Add-on (empfohlen)

1. **Repository hinzufügen**:
   - Gehe zu *Einstellungen → Add-ons → Add-on Store*
   - Klicke auf das Menü (⋮) → *Repositories*
   - Füge hinzu: `https://github.com/supernova1963/eedc-homeassistant`

2. **Add-on installieren**:
   - Suche nach "EEDC" im Add-on Store
   - Klicke auf *Installieren*
   - Aktiviere "In Sidebar anzeigen"
   - Starte das Add-on

3. **Öffnen**:
   - Klicke in der HA-Sidebar auf "eedc"
   - Oder öffne direkt: `http://homeassistant.local:8099`

### Option B: Docker (Standalone)

```bash
# In das eedc-Verzeichnis wechseln
cd eedc

# Image bauen
docker build -t eedc .

# Container starten mit persistentem Datenverzeichnis
docker run -d \
  --name eedc \
  -p 8099:8099 \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  eedc

# Browser öffnen
open http://localhost:8099
```

### Option C: Entwicklungsumgebung

Siehe [DEVELOPMENT.md](DEVELOPMENT.md) für die lokale Entwicklungsumgebung.

---

## 3. Ersteinrichtung (Setup-Wizard)

Beim ersten Start führt dich ein 7-Schritt-Wizard durch die Einrichtung.

### Schritt 1: Willkommen

- Übersicht der Features
- Option: **Demo-Daten laden** zum Ausprobieren
- Klicke "Weiter" um zu starten

### Schritt 2: Anlage erstellen

Hier legst du deine PV-Anlage an:

| Feld | Beschreibung | Beispiel |
|------|--------------|----------|
| **Name** | Bezeichnung der Anlage | "Haus Musterstraße" |
| **Adresse** | Straße, PLZ, Ort | Musterstraße 1, 12345 Musterstadt |
| **Koordinaten** | Werden automatisch ermittelt | 48.1234, 11.5678 |
| **Anlagenleistung** | Gesamt-kWp (wird später durch Module überschrieben) | 10.5 kWp |

**Tipp**: Die Adresse wird für die Wetter-API und PVGIS-Prognosen benötigt. Klicke auf "Koordinaten ermitteln" nachdem du die Adresse eingegeben hast.

### Schritt 3: Home Assistant (optional)

- Prüft die Verbindung zu Home Assistant
- Nur relevant wenn du HA-Features nutzen möchtest
- Kann übersprungen werden

### Schritt 4: Strompreise

Konfiguriere deine Stromtarife:

| Feld | Beschreibung | Typischer Wert (2026) |
|------|--------------|----------------------|
| **Bezugspreis** | Was du pro kWh zahlst | 32-40 ct/kWh |
| **Einspeisevergütung** | Was du pro eingespeister kWh bekommst | 8-12 ct/kWh |
| **Gültig ab** | Seit wann gilt dieser Tarif | 01.01.2024 |

**Hinweis**: Du kannst mehrere Tarife mit unterschiedlichen Gültigkeitszeiträumen anlegen.

### Schritt 5: Geräte-Erkennung (optional)

Falls Home Assistant verbunden ist:
- Automatische Erkennung von Wechselrichtern, Speichern, E-Autos
- Erkannte Geräte werden als Investitionen vorgeschlagen

### Schritt 6: Investitionen

Hier konfigurierst du alle Komponenten deiner Anlage:

#### Wechselrichter
- Kaufpreis, Installationsdatum
- Lebensdauer (typisch: 15-20 Jahre)

#### PV-Module
- **Wichtig**: Müssen einem Wechselrichter zugeordnet werden!
- Anzahl Module, Leistung pro Modul (Wp)
- Ausrichtung (Süd, Ost, West, ...)
- Neigung in Grad

#### Speicher
- Kapazität in kWh
- Optional: Arbitrage-fähig (Netzbezug bei günstigem Strom)
- Optional: Parent = Wechselrichter (für Hybrid-WR mit DC-Speicher)

#### E-Auto
- Optional: V2H-fähig (Vehicle-to-Home)
- Optional: Nutzt V2H aktiv

#### Wärmepumpe
- **Berechnungsmodus:** Wähle zwischen drei Effizienz-Modi (NEU: SCOP in beta.10):
  - **JAZ (Jahresarbeitszahl):** Gemessener Wert am eigenen Standort - der genaueste Wert, wenn verfügbar. Typisch 3,0-4,0 für Luft-WP, 4,0-5,0 für Sole-WP.
  - **SCOP (EU-Label):** Saisonaler COP vom EU-Energielabel - realistischer als Hersteller-COP, aber standortunabhängig. Wähle die passende Vorlauftemperatur (35°C für Fußbodenheizung, 55°C für Heizkörper).
  - **Getrennte COPs:** Separate Werte für Heizung (~3,5-4,5 bei 35°C) und Warmwasser (~2,5-3,5 bei 55°C) - präziser bei unterschiedlichen Betriebspunkten.
- **Wärmebedarf:** Heiz- und Warmwasserbedarf in kWh/Jahr (aus Energieausweis)
- **Vergleich:** Alter Energieträger (Gas/Öl/Strom) und Preis für ROI-Berechnung

#### Weitere Komponenten
- Wallbox, Balkonkraftwerk, Sonstiges

### Schritt 7: Zusammenfassung

- Übersicht aller Eingaben
- Individualisierte nächste Schritte
- Klicke "Einrichtung abschließen"

---

## 4. Navigation & Menüstruktur

### Hauptnavigation (oben)

Die horizontale Navigation enthält zwei Hauptbereiche:

| Bereich | Funktion |
|---------|----------|
| **Cockpit** | Live-Dashboards mit KPIs und Charts |
| **Auswertungen** | Detaillierte Analysen und Reports |

Plus ein Dropdown-Menü für **Einstellungen**.

### Einstellungen-Dropdown

Das Dropdown-Menü ist in vier Kategorien unterteilt:

**Stammdaten:**
- Anlage – PV-Anlage bearbeiten
- Strompreise – Tarife verwalten
- Investitionen – Komponenten konfigurieren

**Daten:**
- Monatsdaten – Energiedaten eingeben/bearbeiten
- Import – CSV-Import/Export
- Demo-Daten – Testdaten laden

**System:**
- Solarprognose – PVGIS-Prognose und Wetter-Provider
- Allgemein – Version, Status

**Optional:**
- HA-Export – MQTT-Konfiguration (nur bei HA-Nutzung)

### Sub-Tabs (kontextabhängig)

Unter der Hauptnavigation erscheinen kontextabhängige Tabs:

**Cockpit Sub-Tabs:**
- Übersicht | PV-Anlage | E-Auto | Wärmepumpe | Speicher | Wallbox | Balkonkraftwerk | Sonstiges

**Einstellungen Sub-Tabs:**
- Anlage | Strompreise | Investitionen | Monatsdaten | Import/Export | Solarprognose | Allgemein

---

## 5. Cockpit (Dashboards)

Das Cockpit zeigt dir alle wichtigen Kennzahlen auf einen Blick.

### 5.1 Übersicht

Die Hauptansicht zeigt 7 Sektionen:

#### Energiebilanz
- **PV-Erzeugung** – Gesamte Stromerzeugung in kWh
- **Direktverbrauch** – Sofort selbst verbrauchter PV-Strom
- **Einspeisung** – Ins Netz eingespeister Überschuss
- **Netzbezug** – Aus dem Netz bezogener Strom

#### Effizienz-Kennzahlen
- **Autarkie** = (Gesamtverbrauch - Netzbezug) / Gesamtverbrauch × 100%
  - Wie viel Prozent deines Verbrauchs deckst du selbst?
- **Eigenverbrauchsquote** = Eigenverbrauch / PV-Erzeugung × 100%
  - Wie viel deines PV-Stroms nutzt du selbst?

#### Komponenten-Status
Schnellstatus für alle Komponenten mit Klick-Navigation zu Details.

#### Finanzielle Auswertung
- Einspeiseerlös (€)
- Eingesparte Stromkosten (€)
- Gesamt-Einsparung (€)

#### CO2-Bilanz
- Vermiedene CO2-Emissionen (kg)
- Vergleich zu reinem Netzbezug

### 5.2 PV-Anlage Dashboard

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

### 5.3 E-Auto Dashboard

- **Gefahrene Kilometer** im Zeitraum
- **Verbrauch** (kWh)
- **Ladequellen-Aufteilung**:
  - PV-Ladung (kostenlos)
  - Netz-Ladung (zu Hause)
  - Externe Ladung (unterwegs)
- **Kostenersparnis** vs. Benziner/Diesel
- **V2H-Entladung** (wenn aktiviert)

### 5.4 Speicher Dashboard

- **Ladezyklen** (Vollzyklen)
- **Effizienz** = Entladung / Ladung × 100%
- **Degradation** (Kapazitätsverlust über Zeit)
- **Arbitrage-Analyse** (wenn aktiviert):
  - Netzladung zu günstigem Strom
  - Entladung bei hohem Preis
  - Arbitrage-Gewinn

### 5.5 Wärmepumpe Dashboard

- **Stromverbrauch** (kWh)
- **Erzeugte Wärme** (kWh)
- **COP** (Coefficient of Performance) = Wärme / Strom
- **Aufteilung**: Heizung vs. Warmwasser
- **Einsparung** vs. Gas/Öl-Heizung

### 5.6 Wallbox Dashboard

- **Geladene Energie** (kWh)
- **Ladevorgänge** (Anzahl)
- **Durchschnittliche Lademenge**
- **PV-Anteil** der Ladungen

### 5.7 Balkonkraftwerk Dashboard

- **Erzeugung** (kWh) - Stromerzeugung des BKW
- **Eigenverbrauch** (kWh) - Selbst genutzter BKW-Strom (NEU)
- **Einspeisung** (kWh) - Unvergütete Einspeisung (= Erzeugung - Eigenverbrauch)
- **Optional**: Speicher-Nutzung (Ladung/Entladung)

### KPI-Tooltips

Jede Kennzahl zeigt bei Hover einen Tooltip mit:
- **Formel**: Wie wird der Wert berechnet?
- **Berechnung**: Konkrete Zahlen eingesetzt
- **Ergebnis**: Der angezeigte Wert

---

## 6. Auswertungen

Detaillierte Analysen in 6 Kategorien.

### 6.1 Energie-Tab

**Jahresvergleich** mit:
- Monats-Charts für alle Energieflüsse
- Delta-Indikatoren (Δ%) zum Vorjahr
- Jahres-Summentabelle

**Visualisierungen:**
- Gestapelte Balkendiagramme (Erzeugung, Verbrauch, Einspeisung)
- Liniendiagramme für Trends
- Torten-/Donut-Charts für Anteile

### 6.2 PV-Anlage Tab

- **String-Performance** über Zeit
- **Ertrag pro Modul** in kWh und kWh/kWp
- **Ausrichtungs-Vergleich**: Welcher String performt am besten?
- **Degradations-Analyse** (Jahr-über-Jahr)

### 6.3 Komponenten Tab

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

### 6.4 Finanzen Tab

- **Einspeiseerlös** = Einspeisung × Einspeisevergütung
- **Eingesparte Stromkosten** = Eigenverbrauch × Bezugspreis
- **Sonderkosten** (Reparaturen, Wartung)
- **Netto-Einsparung** = Erlöse + Einsparungen - Sonderkosten

### 6.5 CO2 Tab

- **Vermiedene Emissionen** (kg CO2)
- **Berechnung**: Eigenverbrauch × CO2-Faktor Strommix
- **Zeitreihe** der CO2-Einsparung
- **Äquivalente**: z.B. "entspricht X km Autofahren"

### 6.6 Investitionen Tab (ROI)

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

#### PV-System Aggregation

**Wichtig**: Wechselrichter + zugeordnete PV-Module + DC-Speicher werden als "PV-System" zusammengefasst!

- Die ROI-Berechnung erfolgt auf System-Ebene
- Einzelkomponenten sind in aufklappbaren Unterzeilen sichtbar
- Einsparungen werden proportional nach kWp verteilt

---

## 7. Aussichten (Prognosen)

Die **Aussichten**-Seite bietet 4 Prognose-Tabs für zukunftsorientierte Analysen.

### 7.1 Kurzfristig (7 Tage)

Wetterbasierte Ertragsschätzung für die nächsten 7 Tage:

- **Datenquelle**: Open-Meteo Wetterprognose
- **Anzeige**: Tägliche Erzeugungsschätzung basierend auf Globalstrahlung
- **Wettersymbole**: Sonnig, bewölkt, regnerisch

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
- E-Auto (vs. Benzin): Ersparnis gegenüber Verbrenner
- Wärmepumpe (PV): Direktverbrauch aus PV
- Wärmepumpe (vs. Gas): Ersparnis gegenüber Gasheizung

> **Hinweis:** Die Finanz-Prognose zeigt den **Amortisations-Fortschritt** (kumulierte Erträge / Investition).
> Im Cockpit und in Auswertung/Investitionen wird dagegen die **Jahres-Rendite** (Jahres-Ertrag / Investition) angezeigt.
> Beide Metriken sind korrekt, aber für unterschiedliche Zwecke gedacht.

---

## 8. Einstellungen

### 8.1 Anlage

Bearbeite die Stammdaten deiner PV-Anlage:
- Name, Adresse, Koordinaten
- Ausrichtung und Neigung (für PVGIS-Prognosen)

**Erweiterte Stammdaten (NEU in beta.6):**
- **MaStR-ID**: Marktstammdatenregister-ID der Anlage mit direktem Link zum MaStR
- **Versorger & Zähler**: Strom-, Gas- und Wasserversorger mit beliebig vielen Zählern
  - Klicke auf "+ Strom-Versorger hinzufügen" etc.
  - Erfasse Versorger-Name, Kundennummer, Portal-URL
  - Füge Zähler hinzu (Bezeichnung wie "Einspeisung", "Bezug", Zählernummer)

### 8.2 Strompreise

Verwalte deine Stromtarife:
- Mehrere Tarife mit Gültigkeitszeitraum möglich
- Wichtig für korrekte Einsparungsberechnung

### 8.3 Investitionen

Alle Komponenten im Überblick:

#### Parent-Child Beziehungen

| Typ | Parent | Pflicht? |
|-----|--------|----------|
| PV-Module | Wechselrichter | **Ja** |
| DC-Speicher | Wechselrichter (Hybrid) | Optional |
| AC-Speicher | - (eigenständig) | - |
| E-Auto | - | - |
| Wärmepumpe | - | - |
| Wallbox | - | - |
| Balkonkraftwerk | - | - |

**Warnung**: PV-Module ohne Wechselrichter-Zuordnung zeigen ein Warnsymbol!

#### Erweiterte Stammdaten (NEU in beta.6)

Jede Investition kann zusätzlich mit detaillierten Stammdaten versehen werden:

**Gerätedaten:**
- Hersteller, Modell, Seriennummer
- Garantie-Datum
- MaStR-ID (nur für Wechselrichter)
- Typ-spezifische Felder (z.B. Garantie-Zyklen für Speicher, Kennzeichen für E-Auto)

**Ansprechpartner (klappbare Sektion):**
- Firma, Name, Telefon, E-Mail
- Ticketsystem/Support-Portal mit direktem Link
- Kundennummer, Vertragsnummer

**Wartungsvertrag (klappbare Sektion):**
- Vertragsnummer, Anbieter
- Gültig bis, Kündigungsfrist
- Leistungsumfang

**Vererbung für PV-System:**
PV-Module und DC-Speicher (mit Parent = Wechselrichter) erben automatisch Ansprechpartner und Wartungsvertrag vom Wechselrichter. Leere Felder zeigen "(erbt von Wechselrichter)". Nur bei Abweichung ausfüllen.

#### Typ-spezifische Parameter

**PV-Module:**
- Anzahl Module
- Leistung pro Modul (Wp)
- Ausrichtung (Süd = 0°, Ost = -90°, West = +90°)
- Neigung (0° = flach, 90° = senkrecht)

**Speicher:**
- Kapazität (kWh)
- Arbitrage-fähig (Ja/Nein)

**E-Auto:**
- V2H-fähig (Ja/Nein)
- Nutzt V2H aktiv (Ja/Nein)

### 8.4 Monatsdaten

Tabelle aller erfassten Monatsdaten mit:
- **Spalten-Toggle**: Wähle welche Spalten angezeigt werden
- **Inline-Bearbeitung**: Direkt in der Tabelle ändern
- **Modal-Bearbeitung**: Für alle Details

#### Aggregierte Darstellung (NEU in beta.3)

Die Monatsdaten-Seite zeigt jetzt alle Daten aggregiert:

| Spaltengruppe | Inhalt | Farbe |
|---------------|--------|-------|
| **Zählerwerte** | Einspeisung, Netzbezug | Blau |
| **PV-Erzeugung** | Summe aller PV-Module | Amber |
| **Speicher** | Ladung, Entladung | Amber |
| **Wärmepumpe** | Strom, Heizung, Warmwasser | Amber |
| **E-Auto** | km, Ladung (PV/Netz) | Amber |
| **Wallbox** | Ladung | Amber |
| **Berechnungen** | Direktverbrauch, Eigenverbrauch, Autarkie | Grün |

**Gruppierte Spaltenauswahl**: Du kannst ganze Gruppen ein-/ausblenden oder einzelne Spalten wählen.

#### Migrations-Warnung

Bei älteren Daten (vor v0.9.7) erscheint eine Warnung:
- Legacy-Daten in `Monatsdaten.batterie_*` werden nicht mehr verwendet
- Beim Bearbeiten werden Werte automatisch migriert
- Nach dem Speichern sind die Daten aktuell

### 8.5 Solarprognose (vormals PVGIS)

Diese Seite kombiniert PVGIS-Langfristprognose mit Wetter-Provider-Einstellungen:

**PVGIS-Prognose:**
- **Systemverluste**: Standard 14% (für Deutschland typisch)
- **TMY-Daten**: Typical Meteorological Year als Referenz
- **Optimale Ausrichtung**: Berechnet optimale Neigung/Azimut für deinen Standort

**Wetter-Provider (NEU in beta.10):**
- Zeigt verfügbare Wetter-Datenquellen für deinen Standort
- Der aktuelle Provider wird in den Anlagen-Stammdaten eingestellt
- Verfügbare Provider:
  - **Auto**: Automatische Auswahl (Bright Sky für DE, sonst Open-Meteo)
  - **Bright Sky (DWD)**: Hochwertige Daten für Deutschland
  - **Open-Meteo**: Historische und Forecast-Daten weltweit
  - **Open-Meteo Solar**: GTI-basierte Prognose für geneigte Module

### 8.6 Allgemein

- **Version**: Aktuelle Software-Version
- **API-Status**: Backend-Verbindung prüfen
- **Datenbank-Statistiken**: Anzahl Datensätze

---

## 9. Datenerfassung

Es gibt drei Wege, Daten in eedc zu bekommen:

### 9.1 Manuelles Formular

**Pfad**: Einstellungen → Monatsdaten → "Neu" Button

Das Formular zeigt dynamisch die relevanten Felder:

**Basis-Felder (immer):**
- Jahr, Monat
- Einspeisung (kWh) – Zählerwert
- Netzbezug (kWh) – Zählerwert

**Komponenten-Felder (je nach Investitionen):**
- PV-Module: Erzeugung pro Modul/String
- Speicher: Ladung, Entladung, Netz-Ladung (Arbitrage)
- E-Auto: km, Verbrauch, Ladung (PV/Netz/Extern), V2H-Entladung
- Wärmepumpe: Strom, Heizung, Warmwasser
- Wallbox: Ladung, Ladevorgänge
- Balkonkraftwerk: Erzeugung

**Wetter-Auto-Fill:**
- Klicke auf "Wetter abrufen"
- Globalstrahlung und Sonnenstunden werden automatisch gefüllt
- Datenquelle: Open-Meteo (historisch) oder PVGIS TMY (aktuell/Zukunft)

### 9.2 CSV-Import

**Pfad**: Einstellungen → Import

#### Template herunterladen

1. Klicke auf "CSV-Template herunterladen"
2. Das Template enthält alle relevanten Spalten basierend auf deinen Investitionen

#### Spalten-Struktur

**Pflicht-Spalten:**
```
Jahr, Monat, Einspeisung_kWh, Netzbezug_kWh
```

**Komponenten-Spalten (dynamisch):**
```
[Investitions-Name]_PV_Erzeugung_kWh     (für PV-Module)
[Investitions-Name]_Ladung_kWh           (für Speicher)
[Investitions-Name]_Entladung_kWh        (für Speicher)
[Investitions-Name]_km                   (für E-Auto)
[Investitions-Name]_Ladung_PV_kWh        (für E-Auto)
[Investitions-Name]_Ladung_Netz_kWh      (für E-Auto)
[Investitions-Name]_Strom_kWh            (für Wärmepumpe)
[Investitions-Name]_Heizung_kWh          (für Wärmepumpe)
[Investitions-Name]_Warmwasser_kWh       (für Wärmepumpe)
...
```

> **Hinweis Wärmepumpe:** Die JAZ/COP-Werte werden über das Investitions-Formular konfiguriert, nicht über CSV. Die CSV enthält nur die gemessenen Monatswerte (Strom, Heizung, Warmwasser).

**Balkonkraftwerk-Spalten (NEU):**
```
[BKW-Name]_Erzeugung_kWh        (PV-Erzeugung)
[BKW-Name]_Eigenverbrauch_kWh   (Selbst genutzt)
```
Die Einspeisung wird automatisch berechnet (Erzeugung - Eigenverbrauch).

**Beispiel:** Wenn dein E-Auto "Smart #1" heißt:
```
Smart #1_km, Smart #1_Ladung_PV_kWh, Smart #1_Ladung_Netz_kWh
```

#### CSV hochladen

1. Befülle das Template mit deinen Daten
2. Klicke auf "CSV importieren"
3. Wähle die Datei aus
4. Duplikate werden automatisch überschrieben

#### Plausibilitätsprüfungen (NEU in beta.8)

Der Import prüft deine Daten auf Konsistenz:

**Fehler (Import wird abgebrochen):**
- Negative Werte in kWh/km/€-Feldern
- Legacy-Spalten (`PV_Erzeugung_kWh`) ohne passende PV-Module-Investitionen
- Mismatch zwischen Legacy-Wert und Summe der individuellen Komponenten

**Warnungen (Import wird fortgesetzt):**
- Redundante Legacy-Spalten (gleiche Werte wie Komponenten)
- Unplausible Wetterwerte (Sonnenstunden > 400h/Monat)

#### JSON-Export für Support

In der Anlagen-Übersicht findest du einen Download-Button (blaues Download-Icon) für den vollständigen JSON-Export:
- Enthält alle Anlage-Daten, Investitionen, Monatsdaten, Strompreise
- Nützlich für Support-Anfragen oder Backup
- Hierarchische Struktur mit allen verknüpften Daten

#### PDF-Dokumentation (NEU in beta.12)

Neben dem JSON-Export gibt es jetzt einen **PDF-Export** (orangefarbenes Dokument-Icon):

**Inhalt der PDF-Dokumentation:**
- **Stammdaten**: Anlagenname, Standort, Koordinaten, MaStR-ID
- **Versorger-Daten**: Stromversorger, Kundennummern, Zählernummern mit Zählpunkten
- **Stromtarif**: Aktueller Tarif mit Preisen
- **Investitionen**: Alle Komponenten mit vollständigen Details:
  - Technische Daten (Leistung, Kapazität, etc.)
  - Gerätedaten (Hersteller, Modell, Seriennummer, Garantie)
  - Ansprechpartner (Service-Firma, Kontaktdaten)
  - Wartungsverträge (Vertragsnummer, Leistungsumfang)
- **Jahresübersicht**: Alle KPIs (Energie, Autarkie, Finanzen, CO2)
- **Diagramme**: PV-Erzeugung, Energie-Fluss, Autarkie-Verlauf
- **Monatstabellen**: Energie, Speicher, Wärmepumpe, E-Mobilität, Finanzen
- **PV-String Vergleich**: SOLL (PVGIS) vs. IST mit Abweichung

**Layout:**
- Kopfzeile (ab Seite 2): Anlagenname | Titel | eedc-Logo
- Fußzeile: Erstellungsdatum | GitHub-Repository | "Seite X von Y"
- Wiederholende Tabellenköpfe bei Seitenumbrüchen

**Zeitraum:**
- Standard: Gesamtzeitraum (alle Jahre seit Installation)
- Der Export erfolgt direkt über die Anlagen-Seite

### 9.3 Demo-Daten

Zum Ausprobieren ohne echte Daten:

**Pfad**: Einstellungen → Demo-Daten

- Generiert realistische Beispieldaten für 2 Jahre
- Inkludiert alle Komponenten-Typen
- Kann jederzeit gelöscht werden

---

## 10. Home Assistant Integration (optional)

EEDC kann berechnete KPIs an Home Assistant exportieren.

### 10.1 Voraussetzungen

- Home Assistant mit MQTT-Broker (Mosquitto)
- MQTT-Benutzer und Passwort

### 10.2 MQTT konfigurieren

**Pfad**: Einstellungen → HA-Export

1. **MQTT aktivieren**: Toggle auf "Ein"
2. **Verbindungsdaten**:
   - Host: `core-mosquitto` (oder IP des Brokers)
   - Port: `1883`
   - Benutzer/Passwort: Deine MQTT-Credentials
3. **Verbindung testen**: Klicke "Test"
4. **Sensoren publizieren**: Klicke "Publizieren"

### 10.3 Verfügbare Sensoren

Nach dem Publizieren erscheinen in HA neue Sensoren:

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| `sensor.eedc_pv_erzeugung` | kWh | Gesamte PV-Erzeugung |
| `sensor.eedc_eigenverbrauch` | kWh | Selbst verbrauchter PV-Strom |
| `sensor.eedc_autarkie` | % | Autarkiegrad |
| `sensor.eedc_eigenverbrauchsquote` | % | EV-Quote |
| `sensor.eedc_einsparung` | € | Finanzielle Einsparung |
| `sensor.eedc_co2_einsparung` | kg | Vermiedene Emissionen |

### 10.4 Alternative: REST API

Statt MQTT kannst du auch die REST API nutzen:

```yaml
# configuration.yaml
rest:
  - resource: http://localhost:8099/api/ha/export/sensors/1
    scan_interval: 3600
    sensor:
      - name: "EEDC PV Erzeugung"
        value_template: "{{ value_json.pv_erzeugung_kwh }}"
        unit_of_measurement: "kWh"
```

---

## 11. Tipps & Best Practices

### Datenqualität

1. **Zählerstände nutzen**: Einspeisung und Netzbezug sollten Zählerwerte sein
2. **Monatlich erfassen**: Mindestens monatlich Daten eintragen
3. **Konsistenz prüfen**: Eigenverbrauch ≤ Erzeugung

### Investitionen richtig anlegen

1. **Wechselrichter zuerst**: Dann PV-Module zuordnen
2. **Realistische Werte**: Lebensdauer, Kaufpreis, Installation
3. **Alle Kosten**: Auch Montage, Gerüst, Elektriker

### Auswertungen interpretieren

1. **Jahresvergleich**: Gleicher Monat, unterschiedliche Jahre
2. **Wetter berücksichtigen**: Schlechtes Jahr ≠ schlechte Anlage
3. **PVGIS als Referenz**: ±10% Abweichung ist normal

### Performance-Optimierung

1. **Eigenverbrauch erhöhen**: Verbraucher tagsüber laufen lassen
2. **Speicher nutzen**: Überschuss für abends speichern
3. **E-Auto laden**: Mittags bei Sonne laden

---

## 12. Fehlerbehebung

### SOLL-IST Vergleich zeigt 0 kWh

**Problem**: Im PV-Anlage Dashboard werden keine IST-Werte angezeigt.

**Lösung**:
1. Prüfe ob PV-Module als Investitionen angelegt sind
2. Prüfe ob Monatsdaten mit PV-Erzeugung existieren
3. Prüfe ob das richtige Jahr ausgewählt ist

### CSV-Import schlägt fehl

**Problem**: Beim Import erscheint eine Fehlermeldung.

**Lösung**:
1. Template neu herunterladen (Spalten können sich ändern)
2. Spaltentrennzeichen prüfen (Semikolon `;` oder Komma `,`)
3. Dezimaltrennzeichen prüfen (Punkt `.` verwenden)
4. Bei Legacy-Spalten-Fehlern: Verwende die individuellen Komponenten-Spalten statt `PV_Erzeugung_kWh`
5. Prüfe ob negative Werte in den Daten sind (nicht erlaubt)

### Wetter-Daten nicht verfügbar

**Problem**: "Wetter abrufen" zeigt Fehler.

**Lösung**:
1. Koordinaten der Anlage prüfen
2. Internetverbindung prüfen
3. Open-Meteo API könnte überlastet sein (später erneut versuchen)

### MQTT-Verbindung fehlgeschlagen

**Problem**: Test-Verbindung zu MQTT schlägt fehl.

**Lösung**:
1. MQTT-Broker läuft? (`docker ps` oder HA Add-on Status)
2. Host/Port korrekt? (`core-mosquitto` bei HA, sonst IP)
3. Benutzer/Passwort korrekt?
4. Firewall-Regeln prüfen

### Dashboard zeigt keine Daten

**Problem**: Alle KPIs zeigen 0 oder "-".

**Lösung**:
1. Monatsdaten vorhanden? (Einstellungen → Monatsdaten)
2. Richtiges Jahr ausgewählt?
3. Strompreise konfiguriert?
4. Browser-Cache leeren (Strg+Shift+R)

### Setup-Wizard erscheint erneut

**Problem**: Nach Abschluss startet der Wizard wieder.

**Lösung**:
1. Browser localStorage prüfen/löschen:
   - `eedc_setup_wizard_completed`
   - `eedc_setup_wizard_state`
2. Oder: Wizard erneut durchlaufen

---

## Glossar

| Begriff | Bedeutung |
|---------|-----------|
| **Autarkie** | Grad der Unabhängigkeit vom Stromnetz |
| **Eigenverbrauch** | Selbst genutzter PV-Strom |
| **Direktverbrauch** | Sofort verbrauchter PV-Strom (ohne Speicher) |
| **Einspeisung** | Ins Netz abgegebener Überschuss |
| **Netzbezug** | Aus dem Netz bezogener Strom |
| **kWp** | Kilowatt Peak (Nennleistung der PV-Anlage) |
| **kWh** | Kilowattstunde (Energiemenge) |
| **ROI** | Return on Investment (Kapitalrendite) |
| **COP** | Coefficient of Performance (momentane Wärmepumpen-Effizienz) |
| **SCOP** | Seasonal COP (saisonale Effizienz vom EU-Energielabel) |
| **JAZ** | Jahresarbeitszahl (gemessene Effizienz am Standort) |
| **V2H** | Vehicle-to-Home (E-Auto als Stromspeicher) |
| **Arbitrage** | Speicher-Strategie: Billig laden, teuer nutzen |
| **PVGIS** | EU-Dienst für PV-Ertragsprognosen |
| **TMY** | Typical Meteorological Year (Durchschnittswetter) |

---

## Support

Bei Fragen oder Problemen:

1. **GitHub Issues**: [github.com/supernova1963/eedc-homeassistant/issues](https://github.com/supernova1963/eedc-homeassistant/issues)
2. **Dokumentation**: [docs/](.)

---

*Letzte Aktualisierung: Februar 2026*
