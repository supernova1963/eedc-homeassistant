# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

---

## [2.6.0] - 2026-03-05

### Hinzugefügt

- **Portal-Import (CSV-Upload)** – Automatische Erkennung und Import von PV-Portal-Exporten
  - SMA Sunny Portal (PV-Ertrag, Netz, Batterie)
  - SMA eCharger (Wallbox-Ladevorgänge)
  - EVCC (Wallbox-Sessions mit PV-Anteil)
  - Fronius Solarweb (PV-Ertrag, Eigenverbrauch)
- **9 Geräte-Connectors** – Direkte Datenabfrage von Wechselrichtern und Smart-Home-Geräten
  - SMA ennexOS (Tripower X, Wallbox EVC)
  - SMA WebConnect (Sunny Boy, Tripower SE)
  - Fronius Solar API (Symo, Primo, Gen24)
  - go-eCharger (Gemini/HOME v3+)
  - Shelly 3EM (Netz-Monitoring)
  - OpenDTU (Hoymiles/TSUN Mikro-Wechselrichter)
  - Kostal Plenticore (Plenticore plus, PIKO IQ)
  - sonnenBatterie (eco/10 performance)
  - Tasmota SML (Smart Meter via IR-Lesekopf)
- **getestet-Flag** – Parser und Connectors zeigen im UI an ob mit echten Geräten verifiziert
- **Dynamischer Tarif: Monatlicher Durchschnittspreis** – Neues optionales Feld `netzbezug_durchschnittspreis_cent` auf Monatsdaten
  - Wird nur bei dynamischen Tarifen (Tibber, aWATTar) abgefragt
  - Alle Finanzberechnungen nutzen den Monatsdurchschnitt statt des fixen Stammdatenpreises
  - Fallback-Kette: Monats-Durchschnittspreis → Fixer Tarif aus Stammdaten
  - Gewichteter Durchschnittspreis (nach kWh) bei Jahresaggregation im Cockpit
- **Arbitrage-Fallback** – `speicher_ladepreis_cent` → `netzbezug_durchschnittspreis_cent` → Stammdaten-Tarif
- **CSV-Template/Export/Import** – Bedingte Spalte `Durchschnittspreis_Cent` bei dynamischem Tarif
- **JSON-Export/Import** – Neues Feld in Export-Schema
- **MonatsdatenForm** – Bedingtes Eingabefeld "Ø Strompreis (dynamisch)" bei dynamischem Tarif
- **Monatsabschluss-Wizard** – Bedingtes Feld mit HA-Sensor-Vorschlag bei dynamischem Tarif
- **HA-Sensormapping** – Neues Basis-Feld `strompreis` für direktes Sensor-Lesen (kein MWD-Paar)
  - Sensor-Filter erweitert um `monetary` device_class und Preis-Einheiten (EUR/kWh, ct/kWh)
- **Hamburger-Menu auf Mobile** ([#18](https://github.com/supernova1963/eedc-homeassistant/issues/18)): Navigation auf schmalen Displays (< 768px) über ausklappbares Menü statt horizontaler Tab-Leiste
- **Energie-Bilanz Perspektiv-Toggle** ([#19](https://github.com/supernova1963/eedc-homeassistant/issues/19)): Umschaltung zwischen Erzeugungs- und Verbrauchsperspektive im Energie-Chart, optionale Autarkie-Linie
- **WP Monatsvergleich – Toggle zwischen Stromverbrauch und COP**

### Behoben

- **Mobile Tab-Overflow:** Tab-Navigationen auf Auswertung, Aussichten und HA-Export liefen auf schmalen Displays über den Rand – jetzt horizontal scrollbar
- **Backup im Einstellungen-Dropdown ergänzt**
- **PVGIS Monatswerte Export:** list statt dict erlauben bei der Serialisierung
- **Bessere Fehlerbehandlung im JSON-Export Endpoint**

---

## [2.5.3] - 2026-03-02

### Hinzugefügt

- **WP Dashboard: COP Monatsvergleich** – Gleiche Monate über Jahre nebeneinander (z.B. Jan 24 vs Jan 25 vs Jan 26) statt Zeitreihe, volle Breite
- **Monatsabschluss: Fehlende Felder ergänzt**
  - E-Auto: Externe Ladung (kWh) und Externe Ladekosten (€)
  - Wallbox: PV-Ladung (kWh) und Ladevorgänge (Anzahl)

### Behoben

- HA-Statistik Werte wurden nicht ins Monatsabschluss-Formular übernommen (Feldnamen-Mapping fehlte: `einspeisung` → `einspeisung_kwh`)
- Degradation: Positive Werte (+5.92%) durch Wetterschwankungen werden auf 0% gekappt, Warnung bei weniger als 3 Datenjahren

---

## [2.5.2] - 2026-03-01

### Hinzugefügt

- **Backup & Restore** – Neue Seite im System-Menü für einfachen JSON-Export und Drag-and-Drop-Import

### Behoben

- PVGIS Horizont-Abruf: API-Key `horizon` → `horizon_profile` (PVGIS API-Änderung)
- JSON Export/Import auf Vollständigkeit gebracht (Export-Version 1.2): fehlende Felder für Anlage, PVGIS-Prognosen und Monatsdaten ergänzt
- HA-Mapping Hinweis wird nur noch bei verfügbarem Home Assistant angezeigt
- Demo-Daten Menüeintrag scrollt jetzt korrekt zur Demo-Sektion

---

## [2.5.1] - 2026-03-01

### Geändert

- docker-compose.yml: Image von lokalem Build auf ghcr.io (`ghcr.io/supernova1963/eedc`) umgestellt
- Dokumentation aktualisiert

---

## [2.5.0] - 2026-03-01

### Hinzugefügt

- **PVGIS Horizontprofil-Support für genauere Ertragsprognosen**
  - Automatisches Geländeprofil (DEM) bei allen PVGIS-Abfragen aktiv (`usehorizon=1`)
  - Eigenes Horizontprofil hochladen (PVGIS-Textformat) oder automatisch von PVGIS abrufen
  - Horizont-Card in PVGIS-Einstellungen mit Status, Statistik und Upload/Abruf
  - Badge "Eigenes Profil" / "DEM" bei gespeicherten Prognosen
  - Horizontprofil im JSON-Export/Import enthalten

- **GitHub Releases & Update-Hinweis**
  - Automatische GitHub Releases mit Docker-Image auf ghcr.io bei Tag-Push
  - Update-Banner im Frontend wenn neuere Version verfügbar
  - Deployment-spezifische Update-Anleitung (Docker, HA Add-on, Git)

- **Social-Media-Textvorlage** ([#1](https://github.com/supernova1963/eedc/issues/1))
  - Kopierfertige Monatsübersicht für Social-Media-Posts
  - Zwei Varianten: Kompakt (Twitter/X) und Ausführlich (Facebook/Foren)
  - Bedingte Blöcke je nach Anlagenkomponenten (Speicher, E-Auto, Wärmepumpe)
  - PVGIS-Prognose-Vergleich, CO₂-Einsparung, Netto-Ertrag
  - Share-Button im Dashboard-Header mit Modal, Monat/Jahr-Auswahl und Clipboard-Kopie

### Behoben

- **Community-Vorschau zeigte falsche Ausrichtung und Neigung**: Werte wurden aus leerem Parameter-JSON gelesen statt aus Modelfeldern

---

## [2.4.1] - 2026-02-26

### Hinzugefügt

- Standalone Docker-Support mit docker-compose
- Conditional Loading: HA-Features nur mit SUPERVISOR_TOKEN

### Behoben

- TypeScript-Fehler im Frontend-Build
- useHAAvailable Hook: Relativer API-Pfad für HA Ingress

---

## [2.4.0] - 2026-02-26

Initiales Standalone-Release basierend auf eedc-homeassistant v2.4.0.

### Funktionsumfang

- PV-Anlagen-Management mit Investitionen und Stromtarifen
- Monatsdaten-Erfassung (manuell, CSV-Import, HA-Statistik-Import)
- Cockpit-Dashboard mit KPIs, Amortisation und Finanzübersicht
- Auswertungen: Zeitreihen, Investitions-ROI, Realisierungsquote
- Aussichten: PVGIS-Solarprognose, Wettervorhersage, Ertragsaussichten
- Community-Benchmarking (anonymisierter Datenvergleich)
- Steuerliche Behandlung (Kleinunternehmer/Regelbesteuerung)
- Spezialtarife für Wärmepumpe & Wallbox
- Sonstige Positionen bei Investitionen
- Firmenwagen & dienstliches Laden
- Dark Mode
