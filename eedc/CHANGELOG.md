# Changelog

Alle wichtigen Änderungen werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt verwendet [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt
- Nichts geplant

---

## [0.4.0] - 2026-02-04

### Hinzugefügt
- **PVGIS Integration** - EU PVGIS API (v5.2) für PV-Ertragsprognosen
  - Prognose-Abruf pro PV-Modul mit individueller Ausrichtung/Neigung
  - Aggregierte Jahres- und Monatsprognosen
  - Optimum-Berechnung für maximalen Ertrag
  - Speichern/Laden/Aktivieren von Prognosen
- **PV-Module als Investitionen** - Modulare PV-Anlagen-Struktur
  - Jedes PV-Modul kann eigene Ausrichtung, Neigung und Leistung haben
  - Unterstützung für Multi-Dach-Anlagen (z.B. Süd + Ost + West)
  - Erweiterte Demo-Anlage mit 3 PV-Modulen (20 kWp gesamt)
- **Prognose vs. IST Vergleich** - Neue Auswertungsseite
  - Monatlicher Vergleich PVGIS-Prognose mit tatsächlicher Erzeugung
  - Abweichungs-Analyse mit Bewertung
  - Hochrechnung auf Jahresbasis
- **PVGIS Einstellungen** - Neue Settings-Seite
  - Übersicht aller PV-Module mit PVGIS-Parametern
  - Prognose-Vorschau mit Monatswerten
  - Optimum-Anzeige für maximalen Ertrag

### Geändert
- `Investition` Model erweitert um `leistung_kwp`, `ausrichtung`, `neigung_grad`
- `Anlage.ausrichtung` und `Anlage.neigung_grad` als DEPRECATED markiert (nun bei PV-Modulen)
- Demo-Daten enthalten nun 3 PV-Module statt einer pauschalen Anlagen-Leistung

---

## [0.3.0] - 2026-02-03

### Hinzugefügt
- **Home Assistant Ingress Integration** - Nahtlose Sidebar-Integration
- HashRouter für HA-Kompatibilität
- Relative API-Pfade
- CSV Auto-Delimiter Erkennung

---

## [0.2.0] - 2026-02-03

### Hinzugefügt
- **ROI-Dashboard** - Wirtschaftlichkeitsanalyse aller Investitionen
  - Amortisationsberechnung
  - KPI-Cards mit Formeln
  - Amortisations-Chart
  - Einsparungen nach Typ (Pie-Chart)
  - Detailtabelle
- **System-Stats API** - Health-Check und Datenbank-Statistiken
- **Settings-UI** - Echte DB-Stats, HA-Status-Anzeige

---

## [0.1.0] - 2026-02-03

### Hinzugefügt
- MVP Release
- Anlagen-Verwaltung (CRUD)
- Strompreis-Verwaltung mit Zeiträumen
- Investitionen-Verwaltung (alle Typen)
- Monatsdaten-Erfassung (Formular + CSV-Import)
- Basis-Kennzahlen (Autarkie, Eigenverbrauch, spez. Ertrag, CO2)
- Dashboard mit KPIs und Trend-Charts
- Auswertung mit 4 Tabs (Übersicht, PV, Finanzen, CO2)
- Dark Mode Support
- Home Assistant Add-on Konfiguration
- HA Backup (SQLite in /data Volume)
