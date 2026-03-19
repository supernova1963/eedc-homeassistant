
# EEDC Handbuch — Teil III: Einstellungen & Sensormapping

**Version 3.1** | Stand: März 2026

> Dieses Handbuch ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Einstellungen](#1-einstellungen)
2. [Datenerfassung](#2-datenerfassung)
3. [Sensor-Mapping](#3-sensor-mapping)
4. [HA-Statistik Import](#4-ha-statistik-import)
5. [Home Assistant Integration](#5-home-assistant-integration)
6. [MQTT-Inbound](#6-mqtt-inbound)
7. [Daten-Checker](#7-daten-checker)
8. [Protokolle](#8-protokolle)
9. [Energieprofile](#9-energieprofile)

---

## 1. Einstellungen

### 1.1 Anlage

Bearbeite die Stammdaten deiner PV-Anlage:
- Name, Adresse, Koordinaten
- Ausrichtung und Neigung (für PVGIS-Prognosen)

**Erweiterte Stammdaten:**
- **MaStR-ID**: Marktstammdatenregister-ID der Anlage mit direktem Link zum MaStR
- **Versorger & Zähler**: Strom-, Gas- und Wasserversorger mit beliebig vielen Zählern
  - Klicke auf "+ Strom-Versorger hinzufügen" etc.
  - Erfasse Versorger-Name, Kundennummer, Portal-URL
  - Füge Zähler hinzu (Bezeichnung wie "Einspeisung", "Bezug", Zählernummer)

**Steuerliche Behandlung:**
- **Keine USt-Auswirkung** (Standard): Für Anlagen ab 2023 mit Nullsteuersatz (≤30 kWp) oder Kleinunternehmer
- **Regelbesteuerung**: USt auf Eigenverbrauch wird als Kostenfaktor berechnet (Pre-2023, >30 kWp, AT/CH)
- USt-Satz ist editierbar (DE: 19%, AT: 20%, CH: 8.1%) und wird bei Land-Wechsel automatisch angepasst

### 1.2 Strompreise

Verwalte deine Stromtarife:
- Mehrere Tarife mit Gültigkeitszeitraum möglich
- Wichtig für korrekte Einsparungsberechnung

**Spezialtarife:**
- Jeder Tarif kann einer Verwendung zugeordnet werden: Standard, Wärmepumpe oder Wallbox
- Aktive Spezialtarife werden in der Info-Box oben angezeigt
- Ohne Spezialtarif wird automatisch der Standard-Tarif für die Komponente verwendet

### 1.3 Investitionen

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
| Sonstiges | - | - |

**Warnung**: PV-Module ohne Wechselrichter-Zuordnung zeigen ein Warnsymbol!

#### Erweiterte Stammdaten

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

**Sonstiges:**
- Kategorie: Erzeuger, Verbraucher oder Speicher
- Beschreibung (optional)
- Monatsdaten-Felder passen sich der Kategorie an

### 1.4 Monatsdaten

Tabelle aller erfassten Monatsdaten mit:
- **Spalten-Toggle**: Wähle welche Spalten angezeigt werden
- **Inline-Bearbeitung**: Direkt in der Tabelle ändern
- **Modal-Bearbeitung**: Für alle Details

#### Aggregierte Darstellung

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

### 1.5 Solarprognose (vormals PVGIS)

Diese Seite kombiniert PVGIS-Langfristprognose mit Wetter-Provider-Einstellungen:

**PVGIS-Prognose:**
- **Systemverluste**: Standard 14% (für Deutschland typisch)
- **TMY-Daten**: Typical Meteorological Year als Referenz
- **Optimale Ausrichtung**: Berechnet optimale Neigung/Azimut für deinen Standort

**Wetter-Provider:**
- Zeigt verfügbare Wetter-Datenquellen für deinen Standort
- Der aktuelle Provider wird in den Anlagen-Stammdaten eingestellt
- Verfügbare Provider:
  - **Auto**: Automatische Auswahl (Bright Sky für DE, sonst Open-Meteo)
  - **Bright Sky (DWD)**: Hochwertige Daten für Deutschland
  - **Open-Meteo**: Historische und Forecast-Daten weltweit
  - **Open-Meteo Solar**: GTI-basierte Prognose für geneigte Module

### 1.6 Allgemein

- **Version**: Aktuelle Software-Version
- **API-Status**: Backend-Verbindung prüfen
- **Datenbank-Statistiken**: Anzahl Datensätze

---

## 2. Datenerfassung

Es gibt viele Wege, Daten in eedc zu bekommen:

### 2.1 Manuelles Formular

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
- Sonstiges: Felder je nach Kategorie (Erzeugung/Verbrauch/Ladung)
- Sonstige Erträge & Ausgaben: Versicherung, Wartung, Einspeisebonus etc.

**Wetter-Auto-Fill:**
- Klicke auf "Wetter abrufen"
- Globalstrahlung und Sonnenstunden werden automatisch gefüllt
- Datenquelle: Open-Meteo (historisch) oder PVGIS TMY (aktuell/Zukunft)

### 2.2 CSV-Import

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

**Balkonkraftwerk-Spalten:**
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

#### Plausibilitätsprüfungen

Der Import prüft deine Daten auf Konsistenz:

**Fehler (Import wird abgebrochen):**
- Negative Werte in kWh/km/€-Feldern
- Legacy-Spalten (`PV_Erzeugung_kWh`) ohne passende PV-Module-Investitionen
- Mismatch zwischen Legacy-Wert und Summe der individuellen Komponenten

**Warnungen (Import wird fortgesetzt):**
- Redundante Legacy-Spalten (gleiche Werte wie Komponenten)
- Unplausible Wetterwerte (Sonnenstunden > 400h/Monat)

#### JSON-Export für Backup & Support

In der Anlagen-Übersicht findest du einen Download-Button (blaues Download-Icon) für den vollständigen JSON-Export:

**Enthaltene Daten (Export-Version 1.1):**
- Anlage-Stammdaten (inkl. MaStR-ID, Versorger-Daten)
- Sensor-Mapping für HA-Integration
- Alle Investitionen mit Monatsdaten
- Strompreise
- PVGIS-Prognosen
- Monatsdaten inkl. Wetterdaten und Sonderkosten

**Anwendungsfälle:**
- **Backup**: Vollständige Sicherung aller Daten
- **Restore**: Import auf anderem System oder nach Neuinstallation
- **Support**: Für Fehleranalyse und Hilfe

#### JSON-Import (Restore)

**Pfad**: Einstellungen → Import → JSON-Datei

1. Wähle eine zuvor exportierte JSON-Datei
2. Optional: "Überschreiben" aktivieren, um existierende Anlage zu ersetzen
3. Klicke auf "Importieren"

**Hinweise zum Import:**
- Bei gleichem Anlagennamen wird automatisch ein Suffix hinzugefügt (außer bei "Überschreiben")
- **Sensor-Mapping**: Wird importiert, aber MQTT-Setup muss erneut durchgeführt werden
  - Grund: Investitions-IDs ändern sich beim Import
  - Gehe nach dem Import zu Einstellungen → Home Assistant → Sensor-Zuordnung und speichere erneut
- Export-Version 1.0 (ohne sensor_mapping) wird weiterhin unterstützt

#### PDF-Dokumentation

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

### 2.3 Cloud-Import

**Pfad**: Einstellungen → Daten → Einrichtung → Cloud-Import

Der Cloud-Import ermöglicht den direkten Abruf historischer Energiedaten aus Hersteller-Cloud-APIs.

**Verfügbare Provider:**

| Provider | Benötigte Zugangsdaten |
|----------|----------------------|
| SolarEdge | API-Key (aus Monitoring-Portal) |
| Fronius SolarWeb | AccessKeyId + AccessKeyValue |
| Huawei FusionSolar | Username + Password (SystemCode) |
| Growatt | Username + Password (+ Anlagen-ID) |
| Deye/Solarman | App-ID + App-Secret + Email + Password |
| EcoFlow PowerOcean | Access Key + Secret Key (+ Seriennummer) |

**Wizard-Ablauf (4 Schritte):**
1. **Verbinden**: Provider wählen und API-Zugangsdaten eingeben
2. **Zeitraum**: Start- und Endmonat für den Import festlegen
3. **Vorschau**: Abgerufene Monatsdaten prüfen und Monate auswählen
4. **Import**: Daten einer Anlage zuordnen und übernehmen

> **Hinweis**: Alle Provider sind derzeit ungetestet und basieren auf der jeweiligen Hersteller-API-Dokumentation. Credentials können pro Anlage gespeichert werden.

### 2.4 Custom-Import (Eigene Datei)

**Pfad**: Einstellungen → Daten → Einrichtung → Eigene Datei importieren

Mit dem Custom-Import kannst du beliebige CSV- oder JSON-Dateien importieren, die monatliche Energiedaten enthalten – z.B. Exports aus anderen Monitoring-Tools oder eigene Tabellen.

**Wizard-Ablauf (4 Schritte):**
1. **Upload**: CSV- oder JSON-Datei per Drag & Drop oder Dateiauswahl hochladen. Die Datei wird automatisch analysiert, Spalten und Beispielwerte werden erkannt.
2. **Mapping**: Jede erkannte Spalte einem EEDC-Zielfeld zuordnen (z.B. "Energy_kWh" → "PV-Erzeugung"). Optionen:
   - **Auto-Detect**: Erkennt gängige Spaltenbezeichnungen automatisch (deutsch + englisch)
   - **Einheit**: Wh, kWh oder MWh – wird automatisch umgerechnet
   - **Dezimalzeichen**: Auto-Erkennung oder manuell (Punkt/Komma)
   - **Datumsspalte**: Kombinierte Spalte (z.B. "2024-01") oder separate Jahr/Monat-Spalten
   - **Templates**: Mapping als Vorlage speichern und bei wiederkehrenden Importen laden
3. **Vorschau**: Umgerechnete Monatsdaten prüfen, einzelne Monate an-/abwählen, Anlage zuordnen
4. **Import**: Daten übernehmen (optional bestehende Monate überschreiben)

**Unterstützte Zielfelder:**
- **Energie**: PV-Erzeugung, Einspeisung, Netzbezug, Eigenverbrauch
- **Batterie**: Ladung, Entladung
- **Wallbox/E-Auto**: Wallbox-Ladung, gefahrene km

### 2.5 Demo-Daten

Zum Ausprobieren ohne echte Daten:

**Pfad**: Einstellungen → Demo-Daten

- Generiert realistische Beispieldaten für 2 Jahre
- Inkludiert alle Komponenten-Typen
- Kann jederzeit gelöscht werden

---

## 3. Sensor-Mapping

Der **Sensor-Mapping-Wizard** ermöglicht die flexible Zuordnung deiner Home Assistant Sensoren zu den EEDC-Feldern.

### 3.1 Wizard starten

**Pfad**: Einstellungen → Sensor-Mapping (im HA-Bereich)

### 3.2 Schritte des Wizards

#### Schritt 1: Basis-Sensoren

Ordne die grundlegenden Energie-Sensoren zu:

| Feld | Beschreibung | Strategie-Optionen |
|------|--------------|-------------------|
| **PV-Erzeugung Gesamt** | Gesamte PV-Produktion | HA-Sensor, Manuell |
| **Einspeisung** | Netz-Einspeisung | HA-Sensor, Manuell |
| **Netzbezug** | Bezug aus dem Netz | HA-Sensor, Manuell |
| **Batterie-Ladung** | Gesamt-Ladung (alle Speicher) | HA-Sensor, Manuell |
| **Batterie-Entladung** | Gesamt-Entladung | HA-Sensor, Manuell |

#### Schritt 2: PV-Module

Für jeden PV-String/Modul-Gruppe:

| Strategie | Beschreibung |
|-----------|--------------|
| **Eigener Sensor** | Separater HA-Sensor für diesen String |
| **kWp-Verteilung** | Anteilige Berechnung aus PV-Gesamt basierend auf kWp |
| **Manuell** | Manuelle Eingabe im Monatsabschluss |

**Beispiel kWp-Verteilung:**
Bei 10 kWp Gesamt und einem String mit 4 kWp erhält dieser String 40% der Gesamt-Erzeugung.

#### Schritt 3: Speicher

Für jeden Speicher:

| Feld | Strategien |
|------|------------|
| **Ladung** | HA-Sensor, Manuell |
| **Entladung** | HA-Sensor, Manuell |
| **Netz-Ladung** | HA-Sensor, Manuell (für Arbitrage) |

#### Schritt 4: Wärmepumpe

| Feld | Strategien |
|------|------------|
| **Stromverbrauch** | HA-Sensor, Manuell (Pflicht) |
| **Heizenergie** | Wärmemengenzähler, COP-Berechnung |
| **Warmwasser** | Wärmemengenzähler, COP-Berechnung, Nicht separat |

**COP-Berechnung:**
Wenn kein Wärmemengenzähler vorhanden, kann die Heizenergie über den COP berechnet werden:
`Heizenergie = Stromverbrauch × COP`

#### Schritt 5: E-Auto

| Feld | Strategien |
|------|------------|
| **km gefahren** | HA-Sensor (Odometer), Manuell |
| **Ladung PV** | HA-Sensor, EV-Quote, Manuell |
| **Ladung Netz** | HA-Sensor, Berechnung, Manuell |
| **V2H-Entladung** | HA-Sensor, Manuell, Nicht aktiv |

**EV-Quote Strategie:**
Berechnet PV-Ladung basierend auf der Eigenverbrauchsquote:
`Ladung PV = Gesamt-Ladung × Eigenverbrauchsquote`

#### Schritt 6: Zusammenfassung

- Übersicht aller konfigurierten Mappings
- Sensoren mit Warnungen (z.B. fehlende Zuordnung)
- Button "Mapping speichern"

### 3.3 Sensor-Auswahl

Bei der Sensor-Auswahl werden automatisch alle verfügbaren HA-Sensoren angezeigt:

- **Filterbar** nach Namen oder Entity-ID
- **Sortiert** nach Relevanz (energy-Sensoren zuerst)
- **Einheit** wird angezeigt (kWh, W, etc.)

---

## 4. HA-Statistik Import

**Pfad**: Einstellungen → Home Assistant → Statistik-Import

### 4.1 Übersicht

Mit dem HA-Statistik Import kannst du **alle historischen Monatsdaten seit der Installation deiner PV-Anlage** automatisch aus der Home Assistant Langzeitstatistik-Datenbank importieren. Das ist besonders nützlich, wenn du:

- EEDC neu installiert hast und Altdaten übernehmen möchtest
- Monatsdaten nachträglich befüllen willst
- Von manueller auf automatische Erfassung umstellen möchtest

### 4.2 Voraussetzungen

- **Sensor-Mapping konfiguriert**: Die HA-Sensoren müssen den EEDC-Feldern zugeordnet sein
- **Home Assistant Langzeitstatistiken**: Deine Sensoren müssen in der HA-Datenbank gespeichert werden
- **EEDC v2.0.0+**: Das Volume-Mapping `config:ro` muss vorhanden sein

> ⚠️ **Wichtig**: Bei Update von v1.x auf v2.0.0 ist eine Neuinstallation des Add-ons erforderlich! Siehe CHANGELOG für Upgrade-Anleitung.

### 4.3 Bulk-Import verwenden

1. **Seite öffnen**: Einstellungen → Home Assistant → Statistik-Import
2. **Datenbank-Status prüfen**: Die Seite zeigt ob die HA-Datenbank verfügbar ist
3. **Anlage auswählen**: Wähle die Anlage für den Import
4. **Vorschau laden**: Klicke auf "Vorschau laden"
5. **Monate auswählen**: Jeder Monat hat eine Checkbox zur individuellen Auswahl
   - **Grün**: Neue Monate ohne vorhandene Daten (standardmäßig ausgewählt)
   - **Grau**: Bereits ausgefüllte Monate (standardmäßig nicht ausgewählt)
   - **Amber (Konflikt)**: Monate mit abweichenden HA-Werten
6. **Individuelle Auswahl**: Aktiviere/Deaktiviere einzelne Monate nach Bedarf
7. **Import starten**: Klicke auf "X Monate importieren"

### 4.4 Einzelne Monate laden

Es gibt zwei Wege, einzelne Monate aus HA-Statistik zu laden:

#### Option A: Über Monatsdaten-Seite

**Pfad**: Einstellungen → Daten → Monatsdaten → "Aus HA laden" Button

1. Klicke auf den Button "Aus HA laden" (neben "Neuer Monat")
2. Wähle den gewünschten Monat aus der Liste verfügbarer HA-Statistik-Monate
3. **Bei neuem Monat**: Die Werte werden direkt ins Formular übernommen
4. **Bei existierendem Monat**: Ein Vergleichs-Modal zeigt die Unterschiede:
   - Spalte "Vorhanden" zeigt aktuelle Werte in EEDC
   - Spalte "HA-Statistik" zeigt Werte aus Home Assistant
   - Spalte "Diff" zeigt die Abweichung (farbcodiert bei >10%)
   - Wähle "HA-Werte übernehmen" oder "Abbrechen"
5. Bearbeite die Werte bei Bedarf und speichere

#### Option B: Über Monatsabschluss-Wizard

**Pfad**: Einstellungen → Daten → Monatsabschluss

1. Wähle den gewünschten Monat
2. Klicke auf "Werte aus HA-Statistik laden"
3. Die Felder werden automatisch befüllt
4. Prüfe die Werte und speichere

### 4.5 Startwerte beim Sensor-Mapping

Beim Speichern des Sensor-Mappings bietet EEDC zwei Optionen für die Startwerte:

1. **Aus HA-Statistik laden (empfohlen)**: Verwendet die gespeicherten Zählerstände vom Monatsanfang aus der HA-Datenbank
2. **Aktuelle Werte verwenden**: Setzt die aktuellen Sensorwerte als Startwerte (Monatswert startet bei 0)

### 4.6 Konflikt-Erkennung

Der Import schützt deine manuell erfassten Daten durch individuelle Auswahl:

| Situation | Standard-Auswahl | Beschreibung |
|-----------|------------------|--------------|
| Neuer Monat | ✓ Ausgewählt | Monat existiert noch nicht in EEDC |
| Leerer Monat | ✓ Ausgewählt | Monatsdaten vorhanden aber alle Felder leer |
| Ausgefüllter Monat | ✗ Nicht ausgewählt | Mindestens ein Feld hat einen Wert |
| Konflikt | ✗ Nicht ausgewählt | Werte in EEDC weichen von HA ab |

**Hinweis**: Du kannst jeden Monat individuell per Checkbox auswählen oder abwählen.

---

## 5. Home Assistant Integration

EEDC kann berechnete KPIs an Home Assistant exportieren und Sensordaten aus Home Assistant für die automatische Monatswertberechnung nutzen.

### 5.1 Voraussetzungen

- Home Assistant mit MQTT-Broker (Mosquitto Add-on)
- MQTT-Benutzer und Passwort

### 5.2 MQTT konfigurieren

**Pfad**: EEDC Add-on Konfiguration in Home Assistant

In der Add-on-Konfiguration:
```yaml
mqtt:
  enabled: true
  host: "core-mosquitto"
  port: 1883
  username: "dein_mqtt_user"
  password: "dein_mqtt_passwort"
```

### 5.3 MQTT Auto-Discovery

Wenn du das **Sensor-Mapping** konfigurierst und speicherst (→ siehe [§3 Sensor-Mapping](#3-sensor-mapping)), erstellt EEDC automatisch MQTT-Entities in Home Assistant. Diese ermöglichen die automatische Berechnung von Monatswerten.

#### Wie funktioniert es?

Für jedes gemappte Feld mit Strategie "HA-Sensor" werden **zwei Entities** erstellt:

| Entity-Typ | Zweck | Beispiel |
|------------|-------|----------|
| **Number** | Speichert den Zählerstand vom Monatsanfang | `number.eedc_winterborn_mwd_inv1_ladung_kwh_start` |
| **Sensor** | Berechnet automatisch den Monatswert | `sensor.eedc_winterborn_mwd_inv1_ladung_kwh_monat` |

**Zusammenspiel:**

```
┌─────────────────────────────────┐     ┌────────────────────────────────┐
│ HA-Sensor (z.B. Batteriezähler) │     │ Number (Startwert Monatsanfang)│
│ aktueller Wert: 12.500 kWh      │     │ gespeicherter Wert: 12.345 kWh │
└───────────────┬─────────────────┘     └──────────────┬─────────────────┘
                │                                      │
                └──────────────┬───────────────────────┘
                               ▼
                 ┌─────────────────────────────┐
                 │ Berechneter Sensor (Monat)  │
                 │ = 12.500 - 12.345 = 155 kWh │
                 └─────────────────────────────┘
```

#### Entity-Benennung

Die Entity-IDs enthalten den technischen Key für Eindeutigkeit:
- `number.eedc_{anlage}_{key}_start` - Startwert
- `sensor.eedc_{anlage}_{key}_monat` - Monatswert

Die **Friendly Names** enthalten den Investitionsnamen für bessere Lesbarkeit:
- "EEDC BYD HVS 12.8 Ladung Monatsanfang"
- "EEDC SMA eCharger 22 Ladung Monat"

### 5.4 Monatsstartwerte initialisieren

**Wichtig:** Damit die automatische Monatswert-Berechnung funktioniert, müssen einmalig die Startwerte (Zählerstände vom Monatsanfang) gesetzt werden.

#### Wann ist das nötig?

1. **Erstmalige Einrichtung** - Nach dem Speichern des Sensor-Mappings
2. **Nach MQTT-Bereinigung** - Wenn Discovery-Messages gelöscht wurden
3. **Korrektur falscher Werte** - Bei Fehlern in den Startwerten

#### Methode 1: Über den Sensor-Mapping-Wizard (empfohlen)

1. Gehe zu **Einstellungen → Sensor-Zuordnung**
2. Nach dem Speichern erscheint ein Dialog "Startwerte initialisieren?"
3. Klicke auf **"Startwerte initialisieren"**
4. EEDC liest die aktuellen Zählerstände aus HA und setzt sie als Startwerte

#### Methode 2: Manuell in Home Assistant

1. Gehe zu **Einstellungen → Geräte & Dienste → Entitäten**
2. Suche nach `number.eedc_`
3. Klicke auf eine Number-Entity (z.B. `number.eedc_winterborn_mwd_inv1_ladung_kwh_start`)
4. Gib den aktuellen Zählerstand als Wert ein

#### Methode 3: Über die HA-Entwicklerwerkzeuge

1. Gehe zu **Entwicklerwerkzeuge → Dienste**
2. Wähle `number.set_value`
3. Entity: `number.eedc_winterborn_mwd_inv1_ladung_kwh_start`
4. Value: Der aktuelle Zählerstand

### 5.5 MQTT-Bereinigung bei Problemen

Falls Entities doppelt erscheinen (mit `_2` Suffix) oder andere Probleme auftreten:

#### Lösung: Discovery-Messages löschen

Mit **mosquitto_pub** (im Terminal/SSH):

```bash
# Beispiel für eine Number-Entity löschen:
mosquitto_pub -h core-mosquitto -t "homeassistant/number/eedc_1_mwd_inv1_ladung_kwh_start/config" -r -n

# Beispiel für eine Sensor-Entity löschen:
mosquitto_pub -h core-mosquitto -t "homeassistant/sensor/eedc_1_mwd_inv1_ladung_kwh_monat/config" -r -n
```

Oder im **MQTT Explorer**:
1. Navigiere zu `homeassistant/number/` und `homeassistant/sensor/`
2. Lösche alle Topics die mit `eedc_` beginnen
3. Home Assistant neu starten
4. In EEDC: Sensor-Mapping erneut speichern

### 5.6 KPI-Export (klassisch)

Zusätzlich zur automatischen Monatswertberechnung kannst du KPIs exportieren:

**Pfad**: Einstellungen → HA-Export → Sensoren publizieren

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| `sensor.eedc_pv_erzeugung` | kWh | Gesamte PV-Erzeugung |
| `sensor.eedc_eigenverbrauch` | kWh | Selbst verbrauchter PV-Strom |
| `sensor.eedc_autarkie` | % | Autarkiegrad |
| `sensor.eedc_eigenverbrauchsquote` | % | EV-Quote |
| `sensor.eedc_einsparung` | € | Finanzielle Einsparung |
| `sensor.eedc_co2_einsparung` | kg | Vermiedene Emissionen |

### 5.7 Alternative: REST API

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

## 6. MQTT-Inbound

MQTT-Inbound ermöglicht es, Live-Leistungsdaten und Monatswerte von **jedem Smarthome-System** an EEDC zu senden.

### Voraussetzungen

- MQTT-Broker (z.B. Mosquitto)
- Smarthome-System mit MQTT-Publish-Fähigkeit (HA, ioBroker, FHEM, openHAB, Node-RED)

### Topic-Struktur

EEDC definiert zwei Topic-Typen:

```
eedc/{anlage_id}/live/{key}    → Echtzeit-Leistung in Watt (W)
eedc/{anlage_id}/energy/{key}  → Zählerstände in kWh (monoton steigend)
```

**Live-Topics** werden für das Live Dashboard verwendet (→ siehe [Teil II, §2 Live Dashboard](HANDBUCH_BEDIENUNG.md#2-live-dashboard)), **Energy-Topics** für den Monatsabschluss (→ siehe [Teil I, §4 Monatsabschluss-Wizard](HANDBUCH_INSTALLATION.md#4-monatsabschluss-wizard)).

### Einrichtung

**Pfad**: Einstellungen → Home Assistant → MQTT-Inbound

1. **MQTT-Verbindung** konfigurieren (Host, Port, User, Passwort)
2. **Topics** werden automatisch basierend auf deinen Investitionen generiert
3. **Monitor** zeigt eingehende Werte in Echtzeit
4. **Beispiel-Flows** für dein Smarthome-System kopieren (HA, Node-RED, ioBroker, FHEM, openHAB)

### Home Assistant Automation Generator

Für HA-Nutzer gibt es einen integrierten **Automation Generator** — kein manuelles YAML-Schreiben nötig:

1. **HA Automation Generator** aufklappen
2. Pro Topic deine HA-Entity eintragen (z.B. `sensor.pv_power`)
3. Intervall wählen und fertiges YAML kopieren
4. In Home Assistant einfügen (Einstellungen → Automatisierungen → YAML-Modus)

Der Generator erzeugt zwei Automationen: **Live** (Echtzeit-Leistung) und **Energy** (Zählerstände für Monatsabschluss).

### Energy → Monatsabschluss

MQTT Energy-Daten erscheinen als Vorschläge im Monatsabschluss-Wizard (Konfidenz 91%). Tageswerte werden aus SQLite-Snapshots berechnet (alle 5 Minuten gespeichert, 31 Tage Retention).

---

## 7. Daten-Checker

**Pfad**: Einstellungen → System → Daten-Checker

Der Daten-Checker prüft die Qualität deiner erfassten Daten in 5 Kategorien:

### Prüfkategorien

| Kategorie | Prüfungen |
|-----------|-----------|
| **Stammdaten** | Koordinaten, Anlagenleistung, Ausrichtung |
| **Strompreise** | Lücken im Tarifzeitraum, fehlende Preise |
| **Investitionen** | Fehlende PV-Module, WR ohne Module, Parameter |
| **Vollständigkeit** | Fehlende Monate, leere Pflichtfelder |
| **Plausibilität** | PV-Produktion vs. PVGIS, unrealistische Werte |

### PVGIS-Prüfung

Die PV-Produktionsprüfung vergleicht deine tatsächliche Erzeugung mit der PVGIS-Prognose unter Berücksichtigung einer dynamischen Performance Ratio. Zu hohe Systemverluste werden erkannt.

### Ergebnisse

- **KPI-Karten** mit Gesamtbewertung
- **Fortschrittsbalken** für Monatsabdeckung
- **Klappbare Kategorien** mit einzelnen Befunden
- **"Beheben"-Links** verweisen direkt zum betroffenen Monatsabschluss

---

## 8. Protokolle

**Pfad**: Einstellungen → System → Protokolle

Das Protokoll-System protokolliert automatisch alle wichtigen Aktivitäten:

### Protokollierte Ereignisse

- **Monatsabschluss** — Wann welcher Monat abgeschlossen wurde
- **Connector-Abruf** — Geräte-Connector Datenabfragen
- **Cloud-Fetch** — Cloud-Import-Abrufe
- **Portal-Import** — Portal-CSV-Imports

### Funktionen

- **Live-Filter** nach Kategorie und Zeitraum
- **In-Memory Log-Buffer** für schnellen Zugriff
- **DB-Persistierung** für langfristige Historie

---

## 9. Energieprofile

**Pfad**: Einstellungen → System → Energieprofile

EEDC sammelt automatisch stündliche Energiedaten und verdichtet sie zu Tages- und Monatswerten. Dies geschieht im Hintergrund — du musst nichts konfigurieren, solange ein Sensor-Mapping eingerichtet ist (→ siehe [§3 Sensor-Mapping](#3-sensor-mapping)).

### Wie funktioniert es?

1. **Stündliche Sammlung:** Täglich um 00:15 wird der Vortag aggregiert. Für jede Stunde werden PV-Erzeugung, Verbrauch, Einspeisung, Netzbezug, Batterie-Leistung, SoC und Wetterdaten (Open-Meteo) gespeichert.
2. **Tageszusammenfassung:** Aus den 24 Stundenwerten wird eine Tageszusammenfassung berechnet: Überschuss/Defizit (kWh), Peak-Leistungen (kW), Batterie-Vollzyklen, Performance Ratio.
3. **Monats-Rollup:** Beim Monatsabschluss werden die Tageszusammenfassungen zu Monatswerten verdichtet (Überschuss, Defizit, Vollzyklen, Performance Ratio, Peak-Netzbezug).

### Voraussetzungen für Energieprofile

- Ein **Sensor-Mapping** muss eingerichtet sein (Live-Sensoren für PV, Verbrauch etc.)
- Funktioniert mit HA-Sensoren und MQTT-Inbound

### Warum?

HA-History hat nur ~10 Tage Retention. EEDC sichert die Daten dauerhaft in seiner eigenen Datenbank, sodass auch langfristige Analysen (Jahresvergleiche, Speicher-Dimensionierung) möglich sind.

### Datenbestand

Unter Einstellungen → System → Energieprofile siehst du den Datenbestand: wie viele Tage pro Anlage bereits gesammelt wurden.

---

*Letzte Aktualisierung: März 2026*
