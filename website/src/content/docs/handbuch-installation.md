---
title: "Installation & Einrichtung"
description: "Teil I: Installation, Setup-Wizard, Monatsabschluss, Tipps und Fehlerbehebung"
---


# EEDC Handbuch — Teil I: Installation & Einrichtung

**Version 3.6** | Stand: März 2026

> Dieses Handbuch ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Einführung](#1-einführung)
2. [Installation](#2-installation)
3. [Ersteinrichtung (Setup-Wizard)](#3-ersteinrichtung-setup-wizard)
4. [Monatsabschluss-Wizard](#4-monatsabschluss-wizard)
5. [Tipps & Best Practices](#5-tipps--best-practices)
6. [Fehlerbehebung](#6-fehlerbehebung)

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

- **Standalone**: Docker oder Python 3.11+ mit Node.js 20+
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

Das Docker-Image ist für `amd64` und `arm64` (Raspberry Pi 4/5, Apple Silicon) verfügbar.

**Empfohlen: Docker Compose**

```bash
# Standalone-Repository klonen
git clone https://github.com/supernova1963/eedc.git
cd eedc

# Mit Docker Compose starten (holt pre-built Image automatisch)
docker compose up -d

# Browser öffnen
open http://localhost:8099
```

**Alternativ: Manuell bauen**

```bash
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
| **Grundpreis** | Monatlicher Grundpreis | 10-15 €/Monat |
| **Gültig ab** | Seit wann gilt dieser Tarif | 01.01.2024 |
| **Verwendung** | Standard, Wärmepumpe oder Wallbox | Standard |

**Hinweis**: Du kannst mehrere Tarife mit unterschiedlichen Gültigkeitszeiträumen anlegen.

**Grundpreis:** Der monatliche Stromgrundpreis wird zu den Netzbezugskosten addiert und fließt so in die Gesamtkostenberechnung ein.

**Spezialtarife:** Für Wärmepumpe oder Wallbox mit separatem Stromzähler und günstigerem Tarif kann ein eigener Strompreis angelegt werden. Ohne Spezialtarif wird der Standard-Tarif verwendet.

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
- Optional: Dienstfahrzeug – bei dienstlichen Fahrzeugen wird die ROI-Berechnung auf AG-Erstattung statt Benzinvergleich umgestellt

#### Wärmepumpe
- **Berechnungsmodus:** Wähle zwischen drei Effizienz-Modi:
  - **JAZ (Jahresarbeitszahl):** Gemessener Wert am eigenen Standort - der genaueste Wert, wenn verfügbar. Typisch 3,0-4,0 für Luft-WP, 4,0-5,0 für Sole-WP.
  - **SCOP (EU-Label):** Saisonaler COP vom EU-Energielabel - realistischer als Hersteller-COP, aber standortunabhängig. Wähle die passende Vorlauftemperatur (35°C für Fußbodenheizung, 55°C für Heizkörper).
  - **Getrennte COPs:** Separate Werte für Heizung (~3,5-4,5 bei 35°C) und Warmwasser (~2,5-3,5 bei 55°C) - präziser bei unterschiedlichen Betriebspunkten.
- **Wärmebedarf:** Heiz- und Warmwasserbedarf in kWh/Jahr (aus Energieausweis)
- **Vergleich:** Alter Energieträger (Gas/Öl/Strom) und Preis für ROI-Berechnung

#### Wallbox
- Kaufpreis, Installationsdatum
- Optional: Dienstliches Laden – ROI berücksichtigt AG-Erstattung

#### Weitere Komponenten
- Balkonkraftwerk, Sonstiges

### Schritt 7: Zusammenfassung

- Übersicht aller Eingaben
- Individualisierte nächste Schritte
- Klicke "Einrichtung abschließen"

---

## 4. Monatsabschluss-Wizard

Der **Monatsabschluss-Wizard** führt dich durch die monatliche Datenerfassung mit intelligenten Vorschlägen.

### 4.1 Wizard starten

**Pfad**: Einstellungen → Monatsabschluss (im Daten-Bereich)

Oder direkt über die URL: `/monatsabschluss`

### 4.2 Funktionsweise

#### Automatische Vorschläge

Für jedes Feld werden automatisch Vorschläge berechnet:

| Quelle | Konfidenz | Beschreibung |
|--------|-----------|--------------|
| **Vormonat** | 80% | Wert vom Vormonat (beste Quelle für kontinuierliche Werte) |
| **Vorjahr** | 70% | Gleicher Monat im Vorjahr (saisonale Korrelation) |
| **Berechnung** | 60% | COP- oder EV-Quote-basierte Berechnung |
| **Durchschnitt** | 50% | Durchschnitt aller vorhandenen Werte |

#### Vorschläge nutzen

Jedes Feld zeigt:
- **Aktueller Wert** (falls vorhanden)
- **Vorschlag** mit Quelle und Konfidenz
- **Übernehmen-Button** zum direkten Übernehmen
- **Manuelles Eingabefeld** für Anpassungen

#### Workflow

1. **Monat wählen** - Der nächste offene Monat wird vorgeschlagen
2. **Basis-Daten prüfen** - Einspeisung, Netzbezug, PV-Erzeugung
3. **Komponenten-Daten** - Speicher, Wärmepumpe, E-Auto, etc.
4. **Speichern** - Alle Daten werden als Monatsdaten gespeichert

### 4.3 Sensor-Werte aus HA

Wenn Sensor-Mapping konfiguriert ist (→ siehe [Teil III, §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping)):
- Werte werden automatisch aus HA abgerufen
- Bei `manuell`-Strategie: Vorschläge aus historischen Daten
- Bei `sensor`-Strategie: Aktueller Sensor-Wert als Vorschlag

### 4.4 Historie

Die letzten Abschlüsse werden angezeigt:
- Monat/Jahr
- Abschlussdatum
- Wichtige Kennzahlen

---

## 5. Tipps & Best Practices

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

## 6. Fehlerbehebung

> **Tipp:** Die **Protokolle-Seite** (Einstellungen → System → Protokolle) ist das wichtigste Werkzeug zur Fehlersuche. Dort kannst du den **Debug-Modus** aktivieren, System-Logs nach Fehlern filtern und **Logs per Copy-Button** direkt in ein GitHub Issue einfügen. Details siehe [Handbuch Einstellungen §9](HANDBUCH_EINSTELLUNGEN.md#9-protokolle).

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
4. **Protokolle → System-Logs**: Suche nach "Open-Meteo" oder "Bright Sky" für Details

### MQTT-Verbindung fehlgeschlagen

**Problem**: Test-Verbindung zu MQTT schlägt fehl.

**Lösung**:
1. MQTT-Broker läuft? (`docker ps` oder HA Add-on Status)
2. Host/Port korrekt? (`core-mosquitto` bei HA, sonst IP)
3. Benutzer/Passwort korrekt?
4. Firewall-Regeln prüfen
5. **Protokolle → Aktivitäten**: Kategorie "MQTT" zeigt Start-/Verbindungsfehler
6. **Protokolle → Aktivitäten**: Kategorie "Connector-Test" zeigt Verbindungstest-Details

### Dashboard zeigt keine Daten

**Problem**: Alle KPIs zeigen 0 oder "-".

**Lösung**:
1. Monatsdaten vorhanden? (Einstellungen → Monatsdaten)
2. Richtiges Jahr ausgewählt?
3. Strompreise konfiguriert?
4. Browser-Cache leeren (Strg+Shift+R)
5. **Protokolle → Aktivitäten**: Kategorie "HA-Statistiken" prüfen ob HA-Import funktioniert hat

### Setup-Wizard erscheint erneut

**Problem**: Nach Abschluss startet der Wizard wieder.

**Lösung**:
1. Browser localStorage prüfen/löschen:
   - `eedc_setup_wizard_completed`
   - `eedc_setup_wizard_state`
2. Oder: Wizard erneut durchlaufen

---

*Letzte Aktualisierung: März 2026*
