
# eedc Handbuch — Teil III: Einstellungen & Sensormapping

**Version 3.24.1** | Stand: April 2026

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Einstellungen](#1-einstellungen)
2. [Datenerfassung](#2-datenerfassung)
3. [Sensor-Mapping](#3-sensor-mapping)
4. [HA-Statistik Import](#4-ha-statistik-import)
5. [Home Assistant Integration](#5-home-assistant-integration)
6. [MQTT-Inbound](#6-mqtt-inbound)
7. [MQTT-Gateway](#7-mqtt-gateway)
8. [Daten-Checker](#8-daten-checker)
9. [Protokolle](#9-protokolle)
10. [Energieprofile — Hintergrund](#10-energieprofile--hintergrund)

---

## 1. Einstellungen

Die Einstellungen-Seite ist in mehrere Tabs gegliedert:

**Stammdaten:** Anlage, Strompreise, Investitionen, Solarprognose
**Daten:** Monatsdaten, **Energieprofil**, Monatsabschluss, Import, Datenerfassung, Demo-Daten
**System:** Daten-Checker, Protokolle, Allgemein

### 1.1 Anlage

Bearbeite die Stammdaten deiner PV-Anlage:
- Name, Adresse, Koordinaten
- Bundesland (für regionale Community-Vergleiche)

> Die früheren Felder „Ausrichtung" und „Neigung" am Anlage-Modell werden seit dem Refactoring zu PV-Modul-Investitionen nicht mehr gepflegt. PV-Ausrichtung und Neigung gehören jetzt pro Modul-String in das Investitions-Formular (siehe §1.3) — die DB-Spalte bleibt für Bestandsinstallationen erhalten, der aktive Code greift nicht mehr darauf zu.

**Erweiterte Stammdaten:**
- **MaStR-ID**: Marktstammdatenregister-ID der Anlage mit direktem Link zum MaStR
- **Versorger & Zähler**: Strom-, Gas- und Wasserversorger mit beliebig vielen Zählern
  - Klicke auf „+ Strom-Versorger hinzufügen" etc.
  - Erfasse Versorger-Name, Kundennummer, Portal-URL
  - Füge Zähler hinzu (Bezeichnung wie „Einspeisung", „Bezug", Zählernummer)

> **Hinweis:** Beim Anlegen eines neuen Stromvertrag-Eintrags in der Infothek werden Anbieter, Tarif und Zählernummer automatisch aus diesen Versorger-Daten vorbelegt.

**Wettermodell:**
- **auto** (Standard): eedc wählt automatisch (Bright Sky für DE, sonst Open-Meteo best_match)
- **MeteoSwiss ICON-CH2**: Empfohlen für alpine Standorte in der Schweiz und Südtirol (2 km Auflösung)
- **ICON-D2**: Hochauflösendes DWD-Modell für Deutschland (2,2 km)
- **ICON-EU**: Europäisches Modell mit mittlerer Auflösung
- **ECMWF IFS**: Globales ECMWF-Modell (0,25°)

Bei spezifischer Modellauswahl versucht eedc zuerst das gewählte Modell und fällt bei fehlenden Daten auf den besten verfügbaren Anbieter zurück (Kaskade). Die verwendete Datenquelle wird pro Tag in der Kurzfrist-Ansicht mit einem Kürzel angezeigt (MS/D2/EU/EC/BM).

**Steuerliche Behandlung:**
- **Keine USt-Auswirkung** (Standard): Für Anlagen ab 2023 mit Nullsteuersatz (≤ 30 kWp) oder Kleinunternehmer
- **Regelbesteuerung**: USt auf Eigenverbrauch wird als Kostenfaktor berechnet (Pre-2023, > 30 kWp, AT/CH)
- USt-Satz ist editierbar (DE: 19 %, AT: 20 %, CH: 8.1 %) und wird bei Land-Wechsel automatisch angepasst

### 1.2 Strompreise

Verwalte deine Stromtarife:
- Mehrere Tarife mit Gültigkeitszeitraum möglich
- Wichtig für korrekte Einsparungsberechnung

**Spezialtarife:**
- Jeder Tarif kann einer Verwendung zugeordnet werden: Standard, Wärmepumpe oder Wallbox
- Aktive Spezialtarife werden in der Info-Box oben angezeigt
- Ohne Spezialtarif wird automatisch der Standard-Tarif für die Komponente verwendet

> Den **dynamischen Strompreis** (Tibber, aWATTar, EPEX) konfigurierst du im Sensor-Mapping-Wizard (siehe §3 Schritt 1: Basis-Sensoren). Auch ohne eigenen Sensor wird der EPEX-Börsenpreis automatisch via aWATTar API als Overlay im Live-Tagesverlauf angezeigt (DE/AT).

### 1.3 Investitionen

Alle Komponenten im Überblick:

#### Parent-Child Beziehungen

| Typ | Parent | Pflicht? |
|-----|--------|----------|
| PV-Module | Wechselrichter | **Ja** |
| DC-Speicher | Wechselrichter (Hybrid) | Optional |
| AC-Speicher | – (eigenständig) | – |
| E-Auto | – | – |
| Wärmepumpe | – | – |
| Wallbox | – | – |
| Balkonkraftwerk | – | – |
| Sonstiges | – | – |

**Warnung**: PV-Module ohne Wechselrichter-Zuordnung zeigen ein Warnsymbol.

#### Anschaffungsdatum & Stilllegungsdatum

Jede Investition hat zwei Lebenszyklus-Daten:

- **Anschaffungsdatum**: ab diesem Datum zählt die Investition für Auswertungen. Aggregate (JAZ, Wärme, Strom, Ersparnis bei der Wärmepumpe; analog Speicher, Wallbox, E-Auto, BKW) ignorieren Monatsdaten **vor** diesem Datum. Nützlich bei Migration auf eine neue Erfassungsmethode (z. B. Wechsel von WP-eigener Strommessung auf Shelly-PM): die alten Werte bleiben historisch in der DB, fließen aber nicht mehr in die aktuelle JAZ-Berechnung ein.
- **Stilllegungsdatum** (v3.14.0): Endmarker. Ab diesem Datum zählt die Investition nicht mehr für aktuelle und künftige Auswertungen. Historische Aggregate behalten die deaktivierte Komponente.

#### Stammdaten — Verknüpfung zur Infothek

Seit v3.16.2 (Etappe 3.6) sind Geräte-Detaildaten (Hersteller/Modell/Seriennummer/Garantie), Ansprechpartner und Wartungsvertrag **nicht mehr Teil des Investitionsformulars**. Sie werden über die [Infothek](HANDBUCH_INFOTHEK.md) gepflegt:

- Ein Infothek-Eintrag (Kategorie z. B. „Komponenten-Akte" oder „Wartungsvertrag") kann mit beliebig vielen Investitionen N:M-verknüpft werden.
- Beim Bearbeiten einer Investition werden die verknüpften Infothek-Einträge als kompakte Liste mit Kategorie und Direktlink angezeigt.
- Wer noch Altdaten aus der Zeit vor v3.16.2 hat, bekommt in der Investitions-Übersicht den Migrations-Banner „Stammdaten in Infothek übernehmen?".

#### Typ-spezifische Parameter

**PV-Module:**
- Anzahl Module
- Leistung pro Modul (Wp)
- Ausrichtung (Süd = 0°, Ost = -90°, West = +90°)
- Neigung (0° = flach, 90° = senkrecht)

**Speicher:**
- Kapazität (kWh, Key: `batteriekapazitaet_kwh`)
- Maximale Leistung (kW, Key: `max_leistung_kw`)
- Arbitrage-fähig (Ja/Nein, Key: `arbitrage_faehig`)

**E-Auto:**
- Batteriekapazität (kWh, Key: `batteriekapazitaet_kwh`)
- V2H-fähig (Ja/Nein, Key: `v2h_faehig`)
- Nutzt V2H aktiv (Ja/Nein)

**Wärmepumpe:**
- **Jahresarbeitszahl (JAZ)** — Standardwert für JAZ-basierte Berechnungen, falls Heizenergie nicht über einen Wärmemengenzähler erfasst wird (Key: `jaz`, Strategy: `gesamt_jaz`).
- **alternativ_kosten_euro** — Kosten der Alternativ-Heizung (Gas/Öl) als Mehrkosten-Basis.
- **alternativ_zusatzkosten_jahr** (€/Jahr, v3.21.0) — laufende Zusatzkosten der Alternativ-Heizung: Schornsteinfeger, Wartung, Gaszähler-Grundpreis. Wird in **fünf** Berechnungs-Stellen berücksichtigt (Aussichten historisch, Aussichten Prognose, HA-Export inkl. WP-Sensor, PDF-Jahresbericht, Investitions-Vorschau), in historischen Aggregaten anteilig pro erfasstem Monat.
- **alter_preis_cent_kwh** — Alt-Tarif Gas/Öl (ct/kWh). Wird als Fallback verwendet, wenn die Monatsdaten kein eigenes `gaspreis_cent_kwh` enthalten.

**Wallbox:**
- Maximale Ladeleistung (kW, Key: `max_ladeleistung_kw`)
- Bidirektional (Ja/Nein, Key: `bidirektional`)

**Wechselrichter:**
- Maximale Leistung (kW, Key: `max_leistung_kw`)
- MaStR-ID (nur für Wechselrichter)

**Sonstiges:**
- Kategorie: Erzeuger, Verbraucher oder Speicher
- Beschreibung (optional)
- Monatsdaten-Felder passen sich der Kategorie an

> **Setup-Wizard ↔ Investitionsformular:** Setup-Wizard, InvestitionForm und das Backend-`parameter_schema` halten dieselben Keys (Drift-Bug aus dem Wizard wurde in v3.23.8 final behoben — siehe Issue #167). Felder, die im Setup-Wizard erfasst werden, landen daher direkt unter den oben dokumentierten Keys.

### 1.4 Monatsdaten

Tabelle aller erfassten Monatsdaten:

- **Spalten-Toggle**: Wähle, welche Spalten angezeigt werden
- **Inline-Bearbeitung**: Direkt in der Tabelle ändern
- **Modal-Bearbeitung**: Für alle Details
- **Höhe**: Tabelle ist auf ~12 Zeilen mit eigener vertikaler Scrollbar und sticky Header begrenzt

#### Aggregierte Darstellung

| Spaltengruppe | Inhalt | Farbe |
|---|---|---|
| **Zählerwerte** | Einspeisung, Netzbezug | Blau |
| **PV-Erzeugung** | Summe aller PV-Module | Amber |
| **Speicher** | Ladung, Entladung | Amber |
| **Wärmepumpe** | Strom, Heizung, Warmwasser | Amber |
| **E-Auto** | km, Ladung (PV/Netz) | Amber |
| **Wallbox** | Ladung | Amber |
| **Berechnungen** | Direktverbrauch, Eigenverbrauch, Autarkie | Grün |

**Gruppierte Spaltenauswahl**: Du kannst ganze Gruppen ein-/ausblenden oder einzelne Spalten wählen.

#### Optionale Preisfelder

Zwei Preisfelder werden bei passenden Investitionen automatisch eingeblendet (über `BEDINGTE_BASIS_FELDER` mit Bedingung `hat_e_auto` / `hat_waermepumpe`):

- **`kraftstoffpreis_euro`** (€/L, ab v3.17.0) — bei E-Auto-Investitionen. Echte monatliche Benzinpreise aus dem **EU Weekly Oil Bulletin** für die ROI-Berechnung; Vorschlagswert im Monatsabschluss-Wizard mit Konfidenz 85.
- **`gaspreis_cent_kwh`** (ct/kWh, ab v3.21.0) — bei Wärmepumpen-Investitionen. Pro Monat gepflegter Gas-/Öl-Tarif. Wenn vorhanden, wird er in der historischen Aggregation Monat für Monat verwendet — ein Tarifwechsel ändert dann nicht mehr rückwirkend die ganze Historie. Fallback: `wp.parameter.alter_preis_cent_kwh`.

#### Datenverwaltung Monatsdaten

- **Kraftstoffpreis-Backfill (Monats)** — neuer Abschnitt unten auf der Monatsdaten-Seite (v3.18.0). Sichtbar **nur**, wenn offene Monate existieren. Befüllt rückwirkend `Monatsdaten.kraftstoffpreis_euro` aus dem EU Oil Bulletin (History seit 2005).
- **Bei Fehlern** (z. B. URL-Wechsel des Bulletins, Parsing-Problem) zeigt das Frontend seit v3.20.1 den Service-Fehler explizit als roten Error-Alert — vorher wurde der Fehler stillschweigend verschluckt.

#### Migrations-Warnung

Bei älteren Daten (vor v0.9.7) erscheint eine Warnung:
- Legacy-Daten in `Monatsdaten.batterie_*` werden nicht mehr verwendet
- Beim Bearbeiten werden Werte automatisch migriert
- Nach dem Speichern sind die Daten aktuell

### 1.5 Solarprognose (vormals PVGIS)

Diese Seite kombiniert PVGIS-Langfristprognose mit Wetter-Provider-Einstellungen:

**PVGIS-Prognose:**
- **Systemverluste**: Standard 14 % (für Deutschland typisch)
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

**Prognosequelle (v3.30.0):**

In den Anlagenstammdaten lässt sich die **PV-Prognosequelle** pro Anlage wählen:

| Quelle | Beschreibung | Verfügbarkeit |
|--------|-------------|---------------|
| **eedc-optimiert** (Standard) | OpenMeteo-Rohprognose × anlagenspezifischer Lernfaktor (O1+O2: Recency-Boost + Trim-Mean). Passt sich automatisch an deine Anlage an. | Überall (HA-Add-on + Standalone) |
| **Solcast** (pur) | Satellitenbasierte Prognose direkt von Solcast, ohne eedc-Korrektur. Im HA-Add-on wird die Solcast HA-Integration (BJReplay) automatisch erkannt. Im Standalone-Betrieb wird ein API-Token benötigt (im Sensor-Mapping-Wizard einzutragen). | HA-Add-on (Auto-Discovery) oder Standalone (API-Token) |
| **Solar Forecast ML** (pur) | ML-basierte Prognose aus der Solar Forecast ML Integration (Zara-Toorox), ohne eedc-Korrektur. Sensoren werden automatisch erkannt. | Nur HA-Add-on |

**Automatischer Fallback:** Wenn die gewählte Quelle keine Daten liefert (Sensor unavailable, Tageslimit, Integration nicht installiert), springt eedc automatisch auf die eedc-Prognose zurück — mit einem unauffälligen Hinweis im Live-Dashboard.

**Quellen-Anzeige:** Im WetterWidget und der Solar-Aussicht siehst du, welche Quelle gerade aktiv ist (nur wenn nicht eedc-Standard). Bei Fallback erscheint ein Amber-farbiger Hinweis.

**Migration:** Wer vorher „Solcast" als Prognose-Basis eingestellt hatte, wird automatisch auf `Solcast (pur)` migriert. Der Unterschied: Solcast wird jetzt direkt als Prognose angezeigt, ohne eedc-Lernfaktor darauf.

### 1.6 Energieprofil-Seite

**Pfad**: Einstellungen → Daten → Energieprofil

Eingeführt in v3.18.0 (#133). Bündelt **anlage-spezifisch** alle Tagesauswertungen und Datenverwaltungs-Aktionen, die sich auf das Energieprofil beziehen — vorher waren sie auf mehrere globale Schalter unter „Allgemein" verteilt.

#### Datenbestand-Kacheln

Pro Anlage zeigt die Seite:
- Stundenwerte (Anzahl, Zeitraum)
- Tagessummen (Anzahl, Zeitraum)
- Monatswerte (Anzahl, Zeitraum)
- Abdeckung in % über den verfügbaren Zeitraum

#### Tages-Tabelle

- **Jahr/Monat-Selektor** — zeigt nur Zeiträume mit Daten
- **Spalten-Selektor mit Gruppen**: Peak-Leistungen (PV/Bezug/Einspeisung), Tages-Summen (PV/Verbrauch/Einspeisung/Bezug), Performance (PR, Autarkie, EV-Quote, Vollzyklen), Wetter (Globalstrahlung, GTI, Sonnenstunden), §51-Börsenpreise (Ø, min, Anzahl negativer Stunden, Einspeisung bei negativem Preis)
- **12-Zeilen-Scrollansicht** mit sticky Header und sticky Σ-Footer (Σ/Ø/max/min je nach Spalte)
- **Pro-Tag-Reaggregation**: Refresh-Knopf am Ende jeder Tageszeile (v3.21.0, #146). Klick → Confirmation → API-Aufruf `POST /api/energie-profil/{anlage_id}/reaggregate-tag?datum=YYYY-MM-DD` → Reload. Die Erfolgsmeldung zeigt nicht nur die Anzahl geschriebener Slots, sondern auch die **Slots mit echten Messdaten**: grün bei `> 0`, amber bei `0` (typische Ursache: keine Snapshots in DB, HA-Statistics nicht erreichbar). Idempotent (delete+insert), wirkt nur auf den gewählten Tag.

#### Datenverwaltung

| Aktion | Beschreibung |
|---|---|
| **Vollbackfill aus HA-Statistik** | Liest historische Snapshots aus HA-Statistics und füllt fehlende Tage. Option **„Bestehende Tage überschreiben"** verfügbar — empfohlen nach größeren Releases (v3.19.0 Snapshot-Architektur, v3.20.0 Backward-Slot, v3.20.0 PR auf GTI). |
| **Kraftstoffpreis-Backfill (Tages)** | Sichtbar nur bei offenen Tagen. Befüllt `TagesZusammenfassung.kraftstoffpreis_euro` aus dem EU Weekly Oil Bulletin. |
| **Verlauf nachberechnen** | Aggregiert alle vorhandenen Tage neu — z. B. nach Konfigurations- oder Sensor-Mapping-Änderungen. |
| **Energieprofil-Daten löschen** | Anlage-spezifisch (vorher war es ein globaler Löschen-Button unter „Allgemein"). |

> **Tipp:** Nach Updates, in deren CHANGELOG-Eintrag „Empfohlene Aktion: Verlauf nachberechnen + überschreiben" steht (z. B. v3.19.0 Zähler-Snapshots, v3.20.0 Backward-Slot, v3.20.0 PR-auf-GTI-Umstellung), genau diese Aktion auf der Energieprofil-Seite auslösen — einmalig pro betroffener Anlage.

### 1.7 Allgemein

Nach Entkernung in v3.18.0 zeigt die Seite nur noch:

- **Theme** — Light / Dark / System
- **HA-Integration-Status**
- **Datenbank-Info** — Anzahl Datensätze, DB-Pfad, Größe
- **Version + API-Status**

Der frühere Block „Datenbestand Energieprofile" inkl. globalem Löschen-Button ist auf die Energieprofil-Seite (§1.6) gewandert.

---

## 2. Datenerfassung

Es gibt mehrere Wege, Daten in eedc zu bekommen:

### 2.1 Manuelles Formular

**Pfad**: Einstellungen → Monatsdaten → „Neu"-Button

Das Formular zeigt dynamisch die relevanten Felder. Seit v3.17.1 (Phase E des Refactorings) nutzt `MonatsdatenForm` `getFelderFuerInvestition()` als Single Source of Truth — neue Felder erscheinen automatisch, sobald sie in `field_definitions.py` definiert sind.

**Basis-Felder (immer):**
- Jahr, Monat
- Einspeisung (kWh) – Zählerwert
- Netzbezug (kWh) – Zählerwert

**Komponenten-Felder (je nach Investitionen):**
- PV-Module: Erzeugung pro Modul/String
- Speicher: Ladung, Entladung, Netz-Ladung (Arbitrage)
- E-Auto: km, Verbrauch, Ladung (PV/Netz/Extern), V2H-Entladung, **Kraftstoffpreis €/L** (ab v3.17.0)
- Wärmepumpe: Strom, Heizung, Warmwasser, **Gaspreis ct/kWh** (ab v3.21.0)
- Wallbox: Ladung, Ladevorgänge
- Balkonkraftwerk: Erzeugung, Eigenverbrauch (Einspeisung wird automatisch berechnet)
- Sonstiges: Felder je nach Kategorie (Erzeugung/Verbrauch/Ladung)
- Sonstige Erträge & Ausgaben: Versicherung, Wartung, Einspeisebonus etc.

**Wetter-Auto-Fill:**
- Klicke auf „Wetter abrufen"
- Globalstrahlung und Sonnenstunden werden automatisch gefüllt
- Datenquelle: Open-Meteo (historisch) oder PVGIS TMY (aktuell/Zukunft)

### 2.2 CSV-Import

**Pfad**: Einstellungen → Import

#### Template herunterladen

1. Klicke auf „CSV-Template herunterladen"
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
…
```

> **Hinweis Wärmepumpe:** Die JAZ-Werte werden über das Investitions-Formular konfiguriert, nicht über CSV. Die CSV enthält nur die gemessenen Monatswerte (Strom, Heizung, Warmwasser) und optional `gaspreis_cent_kwh`.

**Balkonkraftwerk-Spalten:**
```
[BKW-Name]_Erzeugung_kWh        (PV-Erzeugung)
[BKW-Name]_Eigenverbrauch_kWh   (Selbst genutzt)
```
Die Einspeisung wird automatisch berechnet (Erzeugung − Eigenverbrauch).

**Beispiel:** Wenn dein E-Auto „Smart #1" heißt:
```
Smart #1_km, Smart #1_Ladung_PV_kWh, Smart #1_Ladung_Netz_kWh
```

#### CSV hochladen

1. Befülle das Template mit deinen Daten
2. Klicke auf „CSV importieren"
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
- Unplausible Wetterwerte (Sonnenstunden > 400 h/Monat)

#### JSON-Export für Backup & Support

In der Anlagen-Übersicht findest du einen Download-Button (blaues Download-Icon) für den vollständigen JSON-Export.

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

> **HA-Companion-Hinweis (v3.23.2):** Backup-, CSV- und PDF-Downloads laufen seit v3.23.2 über `fetch + Blob` statt `window.open`. Damit funktioniert der Download in der iOS HA-Companion-App ohne 401-Fehler (Safari-`_blank` würde extern öffnen und hätte keine Ingress-Session).

#### JSON-Import (Restore)

**Pfad**: Einstellungen → Import → JSON-Datei

1. Wähle eine zuvor exportierte JSON-Datei
2. Optional: „Überschreiben" aktivieren, um existierende Anlage zu ersetzen
3. Klicke auf „Importieren"

**Hinweise zum Import:**
- Bei gleichem Anlagennamen wird automatisch ein Suffix hinzugefügt (außer bei „Überschreiben")
- **Sensor-Mapping**: Wird importiert, aber MQTT-Setup muss erneut durchgeführt werden
  - Grund: Investitions-IDs ändern sich beim Import
  - Gehe nach dem Import zu Einstellungen → Home Assistant → Sensor-Zuordnung und speichere erneut. Die MQTT-Topic-Abdeckung im Daten-Checker (§8) zeigt sofort, ob deine HA-Publisher-Automation noch zu den neuen Topic-Pfaden passt.
- Export-Version 1.0 (ohne sensor_mapping) wird weiterhin unterstützt

#### PDF-Dokumentation

Neben dem JSON-Export gibt es einen **PDF-Export** (orangefarbenes Dokument-Icon) — siehe Dokumente-Dialog der Anlage. Inhalt:

- **Stammdaten**: Anlagenname, Standort, Koordinaten, MaStR-ID
- **Versorger-Daten**: Stromversorger, Kundennummern, Zählernummern mit Zählpunkten
- **Stromtarif**: Aktueller Tarif mit Preisen
- **Investitionen**: Alle Komponenten mit den im Investitionsformular erfassten Parametern und den verknüpften Infothek-Einträgen (Geräte-Detaildaten kommen seit v3.16.2 ausschließlich aus der Infothek).
- **Jahresübersicht**: Alle KPIs (Energie, Autarkie, Finanzen, CO2)
- **Diagramme**: PV-Erzeugung, Energie-Fluss, Autarkie-Verlauf
- **Monatstabellen**: Energie, Speicher, Wärmepumpe, E-Mobilität, Finanzen
- **PV-String Vergleich**: SOLL (PVGIS) vs. IST mit Abweichung

**Layout:**
- Kopfzeile (ab Seite 2): Anlagenname | Titel | eedc-Logo
- Fußzeile: Erstellungsdatum | GitHub-Repository | „Seite X von Y"
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

Mit dem Custom-Import kannst du beliebige CSV- oder JSON-Dateien importieren, die monatliche Energiedaten enthalten – z. B. Exports aus anderen Monitoring-Tools oder eigene Tabellen.

**Wizard-Ablauf (4 Schritte):**
1. **Upload**: CSV- oder JSON-Datei per Drag & Drop oder Dateiauswahl hochladen. Die Datei wird automatisch analysiert, Spalten und Beispielwerte werden erkannt.
2. **Mapping**: Jede erkannte Spalte einem eedc-Zielfeld zuordnen (z. B. „Energy_kWh" → „PV-Erzeugung"). Optionen:
   - **Auto-Detect**: Erkennt gängige Spaltenbezeichnungen automatisch (deutsch + englisch)
   - **Einheit**: Wh, kWh oder MWh – wird automatisch umgerechnet
   - **Dezimalzeichen**: Auto-Erkennung oder manuell (Punkt/Komma)
   - **Datumsspalte**: Kombinierte Spalte (z. B. „2024-01") oder separate Jahr/Monat-Spalten
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

Der **Sensor-Mapping-Wizard** ermöglicht die flexible Zuordnung deiner Home Assistant Sensoren zu den eedc-Feldern.

### 3.1 Wizard starten

**Pfad**: Einstellungen → Sensor-Zuordnung (im HA-Bereich)

Der Wizard scrollt seit v3.23.8 bei jedem Step-Wechsel automatisch zum Seitenanfang.

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
| **Außentemperatur** | Aktuelle Außentemperatur in °C | HA-Sensor (bevorzugt), Open-Meteo Fallback |
| **Strompreis (dynamischer Tarif)** | Optional: aktueller Strompreis (ct/kWh) | HA-Sensor, leer = automatisches EPEX-Fallback |

**Strompreis-Sensor (v3.16.0):**
Geeignet für Tibber, aWATTar, EPEX, eigene Template-Sensoren. Akzeptiert Einheiten `ct/kWh`, `EUR/kWh`, `EUR/MWh` (wird ×0.1 nach ct/kWh normalisiert), `Cent`, `€`. Wird im Live-Tagesverlauf als gepunktete Linie auf sekundärer Y-Achse angezeigt. Ohne eigenen Sensor lädt eedc automatisch den **EPEX-Börsenpreis (DE/AT)** über aWATTar API als Fallback — die Linie heißt dann „Börsenpreis (EPEX)".

**Vorzeichen-Inversion:** Manche Sensoren liefern Leistungswerte mit invertiertem Vorzeichen (z. B. Einspeisung als negativer Wert). Pro Leistungs-Sensor gibt es eine Checkbox **„Vorzeichen invertieren"** — aktiviere sie, wenn der Sensor negative statt positive Werte liefert. eedc rechnet intern immer mit positiven Werten.

**Solcast PV Forecast (v3.16.5, aktualisiert v3.30.0):**

- **Im HA-Add-on:** Solcast wird automatisch per Auto-Discovery erkannt, wenn die Solcast HA-Integration (BJReplay) installiert ist. Kein manuelles Mapping nötig — wähle einfach „Solcast" als Prognosequelle in den Anlagenstammdaten.
- **Im Standalone-Betrieb:** Am Ende des Basis-Schritts erscheint ein Block mit API-Token + Resource-IDs Eingabefeldern. Kostenlosen Solcast-Account anlegen (solcast.com, 10 Abrufe/Tag), Token und Resource-IDs hier eintragen — eedc cached automatisch.

**Solar Forecast ML (SFML, v3.30.0):**

SFML-Sensoren werden automatisch per Auto-Discovery erkannt, wenn die Solar Forecast ML Integration (Zara-Toorox) im HA installiert ist. Kein manuelles Mapping nötig — wähle „Solar Forecast ML" als Prognosequelle in den Anlagenstammdaten. Nur im HA-Add-on verfügbar (im Standalone ausgegraut).

#### Schritt 2: PV-Module

Für jeden PV-String/Modul-Gruppe:

| Strategie | Beschreibung |
|-----------|--------------|
| **Eigener Sensor** | Separater HA-Sensor für diesen String |
| **kWp-Verteilung** | Anteilige Berechnung aus PV-Gesamt basierend auf kWp |
| **Manuell** | Manuelle Eingabe im Monatsabschluss |

**Beispiel kWp-Verteilung:**
Bei 10 kWp Gesamt und einem String mit 4 kWp erhält dieser String 40 % der Gesamt-Erzeugung.

#### Schritt 3: Speicher

Für jeden Speicher:

| Feld | Strategien |
|------|------------|
| **Ladung** | HA-Sensor, Manuell |
| **Entladung** | HA-Sensor, Manuell |
| **Netz-Ladung** | HA-Sensor, Manuell (für Arbitrage) |
| **SoC (State of Charge)** | HA-Sensor (für Live-Anzeige + Vollzyklen) |

> **Multi-Speicher / E-Auto-Trennung:** Batterie-Vollzyklen werden seit v3.22.0 ausschließlich aus stationären Speicher-SoCs berechnet. E-Auto-SoC-Sensoren (auch wenn sie unter `live.soc` an einer E-Auto-Investition liegen) sind ausgeschlossen — vorher konnte der erste SoC-Sensor in der Investitions-Liste fälschlich als Batterie interpretiert werden. **Nutzer-Schritt nach Update auf v3.22.0:** einmal „Verlauf nachberechnen + überschreiben" auslösen, damit historische `batterie_vollzyklen`-Werte korrigiert werden.

#### Schritt 4: Wärmepumpe

| Feld | Strategien |
|------|------------|
| **Stromverbrauch** | HA-Sensor, Manuell (Pflicht) |
| **Heizenergie** | Wärmemengenzähler, JAZ-Berechnung |
| **Warmwasser** | Wärmemengenzähler, JAZ-Berechnung, Nicht separat |
| **Kompressor-Starts** | Optional: kumulativer Total-Increasing-Sensor |

**JAZ-basierte Berechnung (v3.23.8 Wording):**
Wenn kein Wärmemengenzähler vorhanden ist, kann die Heizenergie über die **Jahresarbeitszahl (JAZ)** abgeleitet werden:
`Heizenergie = Stromverbrauch × JAZ`

> **JAZ vs. COP:** Der Wert, den du im Wizard angibst, ist eine über das Jahr gemittelte Größe — also eine JAZ, kein Betriebspunkt-COP. Der Begriff COP bleibt im Backend für mathematisch-technische Berechnungs-Variablen (z. B. `cop_default`, Strategy-Wert `cop_berechnung` für API-Kompatibilität) reserviert.

**WP-Kompressor-Starts-Sensor (v3.24.0, #136):**
Optionaler kumulativer Anzahl-Zähler für den Wärmepumpen-Kompressor — z. B. aus der lokalen Nibe-Heat-Pump-Integration: `sensor.compressor_number_of_starts_…`. Der stündliche Snapshot-Job erfasst den Counter wie kWh-Zähler, der Tagesabschluss berechnet daraus stündliche und tägliche Differenzen. Anzeige in Auswertung → Energieprofil → Tagesdetail (Spalte „WP-Starts", default ausgeblendet) und Auswertung → Energieprofil → Monat (Komponenten-Gruppe). **Bewusst kein Fallback** aus `leistung_w` oder Compressor-Binary — das würde gerade kurze Takte (wo der KPI sticht) systematisch unterzählen.

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

- Übersicht aller konfigurierten Mappings (inkl. Solcast-Status, falls aktiviert)
- Sensoren mit Warnungen (z. B. fehlende Zuordnung, fehlende HA-Long-Term-Statistics)
- Button „Mapping speichern"
- Nach dem Speichern: Dialog „Startwerte initialisieren?" (siehe §5.4)

### 3.3 Sensor-Auswahl

Bei der Sensor-Auswahl werden alle relevanten HA-Sensoren angezeigt:

- **Filterbar** nach Namen oder Entity-ID
- **Sortiert** nach Relevanz (energy-Sensoren zuerst)
- **Einheit** wird angezeigt (kWh, W, etc.)

#### Filter & Fallback

Der Sensor-Filter wurde in v3.24.1 aufgeweicht, damit auch Roh-Counter ohne Standard-Metadaten erkannt werden:

- `state_class` ∈ `total_increasing` / `total` ist **immer** zugelassen (Unit egal — kumulativer Counter ist per Definition Mapping-Kandidat).
- Zusätzlich werden Sensoren mit **ganzzahligem State ohne jegliche Metadaten** (kein `state_class`, keine `unit_of_measurement`) zugelassen — z. B. Coils der Nibe-Heat-Pump-Integration.

Wenn der gesuchte Sensor trotzdem nicht erscheint, gibt es einen **Fallback-Link** über dem Step-Inhalt: „Sensor nicht in der Auswahl? Alle Sensoren ohne Filter anzeigen." On-demand werden alle `sensor.*`-Entities ungefiltert nachgeladen und in die bestehende Liste gemerged. Plan B außerhalb von eedc: in HA `customize.yaml` `state_class: total_increasing` für den Roh-Counter ergänzen.

#### „ohne Statistik"-Badge (v3.24.1)

Sensoren ohne `state_class` haben **keine Einträge in HA's `statistics_meta`-Tabelle** — für **kWh-Felder** (Monatswerte, Vollbackfill) liefern sie still keine Daten. Counter-Felder (z. B. WP-Kompressor-Starts) sind nicht betroffen, weil sie über den Snapshot-Service laufen.

eedc macht dieses Risiko an drei Stellen sichtbar:

1. **Backend-Schema**: `HASensorInfo.has_statistics: bool` (= `state_class is not None`).
2. **Wizard-Dropdown**: kleines amber-farbiges Badge **„ohne Statistik"** neben dem Sensor-Namen — sowohl in der Suchergebnis-Liste als auch in der „bereits gewählt"-Anzeige. Tooltip: „Für kWh-Felder ungeeignet, für Counter unproblematisch."
3. **Daten-Checker-Kategorie „Sensor-Mapping – HA-Statistics"** (siehe §8): meldet `WARNING`, wenn ein kWh-Feld auf einen LTS-losen Sensor zeigt; `INFO` für Counter; `OK`, wenn alle kWh-Sensoren in LTS verfügbar sind.

Live-Mappings (`leistung_w`, `soc`) werden nicht geprüft — sie lesen `state` direkt und brauchen kein LTS.

---

## 4. HA-Statistik Import

**Pfad**: Einstellungen → Home Assistant → Statistik-Import

### 4.1 Übersicht

Mit dem HA-Statistik Import kannst du **alle historischen Monatsdaten seit der Installation deiner PV-Anlage** automatisch aus der Home Assistant Langzeitstatistik-Datenbank importieren. Das ist besonders nützlich, wenn du:

- eedc neu installiert hast und Altdaten übernehmen möchtest
- Monatsdaten nachträglich befüllen willst
- Von manueller auf automatische Erfassung umstellen möchtest

### 4.2 Voraussetzungen

- **Sensor-Mapping konfiguriert**: Die HA-Sensoren müssen den eedc-Feldern zugeordnet sein
- **Home Assistant Langzeitstatistiken**: Deine Sensoren müssen in der HA-Datenbank gespeichert werden
- **eedc v2.0.0+**: Das Volume-Mapping `config:ro` muss vorhanden sein

> **MariaDB/MySQL-Nutzer:** Der HA-Statistik Import unterstützt seit v3.4.11 auch MariaDB und MySQL als Recorder-Backend — nicht nur SQLite. eedc erkennt den Datenbanktyp automatisch anhand der konfigurierten Verbindungsdaten.

> **Tagesreset-Zähler (v3.23.8 Discussion #131):** Bei Sensoren mit Tagesreset (Zähler springt täglich um 0:00 auf 0) nutzt eedc seit v3.23.8 die `MAX(sum) − MIN(sum)`-Spalte aus HA-Statistics statt einer State-Differenz. HA's `sum`-Spalte ist die reset-bereinigte Kumulation — funktioniert auch bei Tagesreset und Mehrfach-Resets. Vorher lieferte `MAX(state) − MIN(state)` über einen Monat fälschlich die größte Tagessumme statt der Monatssumme (Symptom: „Aktueller Monat bleibt bei 60 kWh fest").

> ⚠ **Wichtig**: Bei Update von v1.x auf v2.0.0 ist eine Neuinstallation des Add-ons erforderlich. Siehe CHANGELOG für die Upgrade-Anleitung.

### 4.3 Bulk-Import verwenden

1. **Seite öffnen**: Einstellungen → Home Assistant → Statistik-Import
2. **Datenbank-Status prüfen**: Die Seite zeigt, ob die HA-Datenbank verfügbar ist
3. **Anlage auswählen**: Wähle die Anlage für den Import
4. **Vorschau laden**: Klicke auf „Vorschau laden"
5. **Monate auswählen**: Jeder Monat hat eine Checkbox zur individuellen Auswahl
   - **Grün**: Neue Monate ohne vorhandene Daten (standardmäßig ausgewählt)
   - **Grau**: Bereits ausgefüllte Monate (standardmäßig nicht ausgewählt)
   - **Amber (Konflikt)**: Monate mit abweichenden HA-Werten
6. **Individuelle Auswahl**: Aktiviere/Deaktiviere einzelne Monate nach Bedarf
7. **Import starten**: Klicke auf „X Monate importieren"

### 4.4 Einzelne Monate laden

Es gibt zwei Wege, einzelne Monate aus HA-Statistik zu laden:

#### Option A: Über Monatsdaten-Seite

**Pfad**: Einstellungen → Daten → Monatsdaten → „Aus HA laden"-Button

1. Klicke auf den Button „Aus HA laden" (neben „Neuer Monat")
2. Wähle den gewünschten Monat aus der Liste verfügbarer HA-Statistik-Monate
3. **Bei neuem Monat**: Die Werte werden direkt ins Formular übernommen
4. **Bei existierendem Monat**: Ein Vergleichs-Modal zeigt die Unterschiede:
   - Spalte „Vorhanden" zeigt aktuelle Werte in eedc
   - Spalte „HA-Statistik" zeigt Werte aus Home Assistant
   - Spalte „Diff" zeigt die Abweichung (farbcodiert bei > 10 %)
   - Wähle „HA-Werte übernehmen" oder „Abbrechen"
5. Bearbeite die Werte bei Bedarf und speichere

#### Option B: Über Monatsabschluss-Wizard

**Pfad**: Einstellungen → Daten → Monatsabschluss

1. Wähle den gewünschten Monat
2. Klicke auf „Werte aus HA-Statistik laden"
3. Die Felder werden automatisch befüllt
4. Bei E-Auto-Investitionen: Prüfe den vorgeschlagenen **Ø Benzinpreis** (aus EU Oil Bulletin)
5. Bei Wärmepumpen-Investitionen: Prüfe den vorgeschlagenen **Ø Gaspreis** (wenn `gaspreis_cent_kwh` in vergleichbaren Monaten gepflegt ist)
6. Prüfe die Werte und speichere

### 4.5 Startwerte beim Sensor-Mapping

Beim Speichern des Sensor-Mappings bietet eedc zwei Optionen für die Startwerte:

1. **Aus HA-Statistik laden (empfohlen)**: Verwendet die gespeicherten Zählerstände vom Monatsanfang aus der HA-Datenbank
2. **Aktuelle Werte verwenden**: Setzt die aktuellen Sensorwerte als Startwerte (Monatswert startet bei 0)

### 4.6 Konflikt-Erkennung

Der Import schützt deine manuell erfassten Daten durch individuelle Auswahl:

| Situation | Standard-Auswahl | Beschreibung |
|-----------|------------------|--------------|
| Neuer Monat | ✓ Ausgewählt | Monat existiert noch nicht in eedc |
| Leerer Monat | ✓ Ausgewählt | Monatsdaten vorhanden, aber alle Felder leer |
| Ausgefüllter Monat | ✗ Nicht ausgewählt | Mindestens ein Feld hat einen Wert |
| Konflikt | ✗ Nicht ausgewählt | Werte in eedc weichen von HA ab |

**Hinweis**: Du kannst jeden Monat individuell per Checkbox auswählen oder abwählen.

---

## 5. Home Assistant Integration

eedc kann berechnete KPIs an Home Assistant exportieren und Sensordaten aus Home Assistant für die automatische Monatswertberechnung nutzen.

### 5.1 Voraussetzungen

- Home Assistant mit MQTT-Broker (Mosquitto Add-on)
- MQTT-Benutzer und Passwort

### 5.2 MQTT konfigurieren

**Pfad**: eedc Add-on Konfiguration in Home Assistant

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

Wenn du das **Sensor-Mapping** konfigurierst und speicherst (→ siehe [§3 Sensor-Mapping](#3-sensor-mapping)), erstellt eedc automatisch MQTT-Entities in Home Assistant.

#### Wie funktioniert es?

Für jedes gemappte Feld mit Strategie „HA-Sensor" werden **zwei Entities** erstellt:

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
- `number.eedc_{anlage}_{key}_start` — Startwert
- `sensor.eedc_{anlage}_{key}_monat` — Monatswert

Die **Friendly Names** enthalten den Investitionsnamen für bessere Lesbarkeit:
- „eedc BYD HVS 12.8 Ladung Monatsanfang"
- „eedc SMA eCharger 22 Ladung Monat"

### 5.4 Monatsstartwerte initialisieren

**Wichtig:** Damit die automatische Monatswert-Berechnung funktioniert, müssen einmalig die Startwerte (Zählerstände vom Monatsanfang) gesetzt werden.

#### Wann ist das nötig?

1. **Erstmalige Einrichtung** — nach dem Speichern des Sensor-Mappings
2. **Nach MQTT-Bereinigung** — wenn Discovery-Messages gelöscht wurden
3. **Korrektur falscher Werte** — bei Fehlern in den Startwerten

#### Methode 1: Über den Sensor-Mapping-Wizard (empfohlen)

1. Gehe zu **Einstellungen → Sensor-Zuordnung**
2. Nach dem Speichern erscheint ein Dialog „Startwerte initialisieren?"
3. Klicke auf **„Startwerte initialisieren"**
4. eedc liest die aktuellen Zählerstände aus HA und setzt sie als Startwerte

#### Methode 2: Manuell in Home Assistant

1. Gehe zu **Einstellungen → Geräte & Dienste → Entitäten**
2. Suche nach `number.eedc_`
3. Klicke auf eine Number-Entity (z. B. `number.eedc_winterborn_mwd_inv1_ladung_kwh_start`)
4. Gib den aktuellen Zählerstand als Wert ein

#### Methode 3: Über die HA-Entwicklerwerkzeuge

1. Gehe zu **Entwicklerwerkzeuge → Dienste**
2. Wähle `number.set_value`
3. Entity: `number.eedc_winterborn_mwd_inv1_ladung_kwh_start`
4. Value: Der aktuelle Zählerstand

### 5.5 MQTT-Bereinigung bei Problemen

Falls Entities doppelt erscheinen (mit `_2`-Suffix) oder andere Probleme auftreten:

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
2. Lösche alle Topics, die mit `eedc_` beginnen
3. Home Assistant neu starten
4. In eedc: Sensor-Mapping erneut speichern

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
| `sensor.eedc_jahres_ersparnis_euro` | € | Gesamt-Jahresersparnis inkl. WP-/E-Auto-/BKW-Beiträgen |
| `sensor.eedc_roi_prozent` | % | Jahres-ROI |
| `sensor.eedc_amortisation_jahre` | Jahre | Verbleibende Amortisation |

> **Komponenten-Beiträge in MQTT-Sensoren (v3.19.1):** `jahres_ersparnis_euro`, `roi_prozent` und `amortisation_jahre` rechnen die Alternativkosten-Ersparnisse von Wärmepumpe (vs. Gas/Öl), E-Auto (vs. Benzin) und Balkonkraftwerk mit ein — analog zu Aussichten → Finanzen. Vorher kam bei Anlagen mit WP/E-Auto eine absurd lange Amortisation heraus (z. B. 188,6 Jahre, weil nur PV-Netto-Ertrag gezählt wurde).

### 5.7 Alternative: REST API

Statt MQTT kannst du auch die REST API nutzen:

```yaml
# configuration.yaml
rest:
  - resource: http://localhost:8099/api/ha/export/sensors/1
    scan_interval: 3600
    sensor:
      - name: "eedc PV Erzeugung"
        value_template: "{{ value_json.pv_erzeugung_kwh }}"
        unit_of_measurement: "kWh"
```

---

## 6. MQTT-Inbound

MQTT-Inbound ermöglicht es, Live-Leistungsdaten und Monatswerte von **jedem Smarthome-System** an eedc zu senden.

### Voraussetzungen

- MQTT-Broker (z. B. Mosquitto)
- Smarthome-System mit MQTT-Publish-Fähigkeit (HA, ioBroker, FHEM, openHAB, Node-RED)

### Topic-Struktur

eedc definiert zwei Topic-Typen:

```
eedc/{anlage_id}/live/{key}    → Echtzeit-Leistung in Watt (W)
eedc/{anlage_id}/energy/{key}  → Zählerstände in kWh (monoton steigend)
```

**Live-Topics** werden für das Live Dashboard verwendet (→ siehe [Teil II, §2 Live Dashboard](HANDBUCH_BEDIENUNG.md#2-live-dashboard)), **Energy-Topics** für den Monatsabschluss.

### Einrichtung

**Pfad**: Einstellungen → Home Assistant → MQTT-Inbound

1. **MQTT-Verbindung** konfigurieren (Host, Port, User, Passwort)
2. **Topics** werden automatisch basierend auf deinen Investitionen generiert
3. **Monitor** zeigt eingehende Werte in Echtzeit
4. **Beispiel-Flows** für dein Smarthome-System kopieren (HA, Node-RED, ioBroker, FHEM, openHAB)

### Home Assistant Automation Generator

Für HA-Nutzer gibt es einen integrierten **Automation Generator** — kein manuelles YAML-Schreiben nötig:

1. **HA Automation Generator** aufklappen
2. Pro Topic deine HA-Entity eintragen (z. B. `sensor.pv_power`)
3. Intervall wählen und fertiges YAML kopieren
4. In Home Assistant einfügen (Einstellungen → Automatisierungen → YAML-Modus)

Der Generator erzeugt zwei Automationen: **Live** (Echtzeit-Leistung) und **Energy** (Zählerstände für Monatsabschluss).

### Energy → Monatsabschluss

MQTT Energy-Daten erscheinen als Vorschläge im Monatsabschluss-Wizard (Konfidenz 91 %). Tageswerte werden aus SQLite-Snapshots berechnet (alle 5 Minuten gespeichert, 31 Tage Retention).

> **Topic-Drift erkennen:** Sobald in eedc neue Felder dazukommen oder Investitions-IDs nach einem Re-Import wechseln, kann der statische Publisher (HA-Automation/iobroker/Node-RED) gegen den dynamisch aus `field_definitions.py` erzeugten Konsumenten driften. Der Daten-Checker meldet das in der Kategorie **MQTT-Topic-Abdeckung** (siehe §8) — pro Anlage erscheinen die fehlenden bzw. veralteten Topics mit Beispielen.

---

## 7. MQTT-Gateway

**Pfad**: Einstellungen → Home Assistant → MQTT-Gateway

Das **MQTT-Gateway** ergänzt den MQTT-Inbound um ein flexibles Topic-Mapping: Du kannst die MQTT-Topics deiner eigenen Geräte (Shelly, OpenDTU, Tasmota, …) direkt auf eedc-Felder mappen — ohne dein Smarthome-System zu ändern.

> **Unterschied zu MQTT-Inbound:** MQTT-Inbound erwartet Daten auf fixen eedc-Topics (`eedc/{id}/live/...`). Das Gateway übersetzt beliebige eigene Topics in diese Struktur.

### 7.1 Geräte-Presets

Für gängige Geräte sind fertige Mapping-Vorlagen hinterlegt. Klicke auf **„Preset laden"** und wähle dein Gerät:

| Preset | Unterstützte Geräte |
|--------|-------------------|
| **Shelly** | Shelly Pro 3EM, Shelly EM, Shelly Plus 1PM |
| **OpenDTU** | OpenDTU (alle Wechselrichter-Typen) |
| **Tasmota** | Tasmota Energy-Template |
| **Fronius Push** | Fronius Solar API Push |
| **SMA** | SMA Speedwire MQTT Bridge |

Nach dem Laden eines Presets werden die Topic-Pfade mit deinen Gerätedaten (z. B. Seriennummer) befüllt.

### 7.2 Manuelles Topic-Mapping

Für Geräte ohne Preset kannst du das Mapping manuell konfigurieren:

1. **eedc-Zielfeld wählen** (z. B. „PV-Leistung gesamt")
2. **Quell-Topic eingeben** (z. B. `solar/openDTU12345/total/Power`)
3. **JSON-Pfad** angeben, falls das Payload ein JSON-Objekt ist (z. B. `data.power`)
4. **Einheit** wählen (W oder kW — wird automatisch umgerechnet)
5. **Testen**: Klicke „Letzte Nachricht", um den empfangenen Wert sofort zu prüfen

### 7.3 Bridge-Modus (Connector → MQTT)

Geräte-Connectors (SMA, Fronius etc.) können ihre Messwerte über die MQTT-Bridge regelmäßig auf eedc-Topics publishen — auch wenn das Gerät kein natives MQTT spricht:

**Pfad**: Einstellungen → Datenerfassung → Connector → „Als MQTT-Bridge aktivieren"

- Abruf-Intervall: 30 s, 60 s, 5 min (je nach Gerät)
- Published auf: `eedc/{anlage_id}/live/{key}`
- Ersetzt manuelles MQTT-Senden aus dem Smarthome-System

### 7.4 Diagnose

Der Gateway-Tab zeigt live:
- Verbindungsstatus zum MQTT-Broker
- Letzte empfangene Nachricht pro Topic (Wert, Zeitstempel)
- Fehlermeldungen bei nicht auflösbaren JSON-Pfaden

---

## 8. Daten-Checker

**Pfad**: Einstellungen → System → Daten-Checker

Der Daten-Checker prüft die Qualität deiner erfassten Daten in **8 Kategorien** — von Stammdaten und Strompreisen über Plausibilität der Monatsdaten bis zu MQTT-Topic-Abdeckung und HA-Long-Term-Statistics-Verfügbarkeit der gemappten Sensoren. Pro Befund liefert er Severity (ERROR/WARNING/INFO/OK), erklärenden Text und einen „Beheben"-Link direkt zur betroffenen Stelle.

### Severity-Übersicht

| Symbol | Stufe | Bedeutung |
|--------|-------|-----------|
| ❌ | ERROR | Kerndaten fehlen oder Werte sind logisch unmöglich — Auswertungen sind betroffen. |
| ⚠️ | WARNING | Plausibilitäts-Abweichung oder fehlende Pflicht-Parameter — App rechnet, blendet aber Bereiche aus. |
| ℹ️ | INFO | Hinweis auf optionale Felder; Reaktion abhängig vom Anwendungsfall. |
| ✅ | OK | Prüfung bestanden. |

> **Vollständige Doku** mit allen 8 Kategorien, Befund-Tabellen, Variantenmatrix HA Add-on vs. Standalone und Behebungs-Workflows: **[Daten-Checker-Handbuch](HANDBUCH_DATEN_CHECKER.md)** (auch in der In-App-Hilfe unter *Hilfe → Handbuch → Daten-Checker*).

---

## 9. Protokolle

**Pfad**: Einstellungen → System → Protokolle

Die Protokolle-Seite ist das zentrale Werkzeug zur Fehlersuche. Sie besteht aus zwei Tabs und bietet Debug-Modus sowie Neustart direkt im Header.

### Header-Aktionen

| Button | Funktion |
|--------|----------|
| **Debug** (Käfer-Icon) | Schaltet den Log-Level zwischen INFO und DEBUG um. Debug zeigt alle Detail-Meldungen — ideal für Fehlersuche, danach wieder deaktivieren (erhöhter Speicherverbrauch). Kein Restart nötig. |
| **Neustart** (Pfeil-Icon) | Startet eedc neu. Bei HA über die Supervisor-API, Standalone über Container-Restart. Bestätigungsdialog vor Ausführung. |

### Tab 1: System-Logs

Echtzeit-Logviewer mit In-Memory Ring Buffer (max. 500 Einträge, gehen bei Restart verloren).

**Filter:**
- **Level** — DEBUG, INFO, WARNING, ERROR (Minimum-Filter: WARNING zeigt auch ERROR)
- **Modul** — Freitextsuche im Logger-Namen (z. B. „connector", „mqtt", „wetter")
- **Suche** — Freitextsuche in Log-Nachrichten

**Aktionen:**
- **Auto-Refresh** (Play/Pause) — Aktualisiert alle 5 Sekunden
- **Copy** (Clipboard-Icon) — Kopiert alle sichtbaren Logs als Markdown-Tabelle in die Zwischenablage, ideal zum Einfügen in GitHub Issues
- **Download** (Pfeil-Icon) — Exportiert gefilterte Logs als `.txt`-Datei

**Typische Fehlersuche im System-Logs Tab:**

| Problem | Filter-Tipp |
|---------|-------------|
| API-Fehler | Level: ERROR |
| MQTT-Probleme | Suche: „MQTT" oder Modul: „mqtt" |
| Wetter-API schlägt fehl | Suche: „Open-Meteo" oder „Bright Sky" |
| Solar-Prognose fehlt | Suche: „Solar" |
| Connector liest nicht | Modul: „connector", Level: WARNING |

### Tab 2: Aktivitäten

Persistentes Aktivitätsprotokoll in der Datenbank (überlebt Restarts, automatisch bereinigt nach 90 Tagen / max. 1000 Einträge).

**Filter:**
- **Kategorie** — Dropdown mit allen Kategorien
- **Status** — Erfolgreich / Fehlgeschlagen
- **Suche** — Freitextsuche in Aktion und Details (z. B. „sma_ennexos", „fehlgeschlagen")

**Aktionen:**
- **Copy** (Clipboard-Icon) — Kopiert sichtbare Aktivitäten als Markdown-Liste
- **Bereinigen** (Papierkorb) — Löscht Einträge älter als 90 Tage, zeigt Toast mit Anzahl
- **Pagination** — Blättern durch ältere Einträge

**Protokollierte Kategorien:**

| Kategorie | Was wird protokolliert |
|-----------|----------------------|
| Connector-Test | Verbindungstests zu Geräten (SMA, Fronius etc.) |
| Connector-Einrichtung | Neue Connector-Konfigurationen |
| Connector-Abruf | Zählerstand-Abfragen (Erfolg/Fehler) |
| Portal-Import | CSV-/Portal-Imports |
| Cloud-Import | Cloud-Verbindungstests (Growatt, Fronius etc.) |
| Cloud-Fetch | Monatliche Cloud-Datenabrufe |
| Backup-Export | JSON-Anlagen-Exporte |
| Backup-Import | JSON-Anlagen-Imports mit Details |
| Monatsabschluss | Monatsdaten speichern |
| HA-Statistiken | HA Recorder DB-Abfragen und Bulk-Imports |
| Scheduler-Jobs | Hintergrund-Tasks (Monatswechsel, Energie-Profil, MQTT-Snapshots, Sensor-Snapshots) |
| MQTT | Inbound/Gateway/Bridge Start und Verbindungsverluste |
| Community | Daten teilen/löschen, Server-Timeout |
| Sensor-Mapping | Sensor-Zuordnungen speichern/löschen |
| HA-Export | MQTT-Sensoren publizieren/entfernen |

### Fehlersuche-Workflow

Bei einem Support-Fall empfehlen wir diesen Ablauf:

1. **Debug-Modus aktivieren** (Button im Header)
2. **Problem reproduzieren** (Aktion wiederholen, die fehlschlägt)
3. **System-Logs prüfen** — Level: WARNING, Suche nach dem betroffenen Modul
4. **Aktivitäten prüfen** — Kategorie filtern oder nach Stichwort suchen
5. **Logs kopieren** — Copy-Button drücken, in GitHub Issue einfügen
6. **Debug-Modus deaktivieren** (nicht vergessen!)

---

## 10. Energieprofile — Hintergrund

eedc sammelt automatisch stündliche Energiedaten und verdichtet sie zu Tages- und Monatswerten. Der Datenfluss:

### Snapshot-basierte Architektur (ab v3.19.0, #135)

Stunden-kWh kommen seit v3.19.0 nicht mehr aus der Integration von 10-Min-Leistungs-Samples, sondern aus **kumulativen Zähler-Snapshots**:

1. **Stündlicher Snapshot-Job** (Cron `:05`) schreibt pro Anlage und gemapptem kWh-Sensor den aktuellen kumulativen Zählerstand in die Tabelle `sensor_snapshots`. Quellen: HA Long-Term Statistics (Add-on) oder MQTT-Energy-Snapshots (Standalone/Docker).
2. **`:55`-Live-Preview** (ab v3.21.0): zusätzlich zur :05-Aufnahme wird zum Stundenende ein Live-Snapshot geschrieben — die laufende Stunde ist damit sofort am Stundenende sichtbar statt erst um (h+1):05.
3. **Tageszusammenfassung** (00:15 für den Vortag): aus den 25 Snapshot-Werten (h = -1..23) werden pro Stunde Differenzen gebildet → 24 Stundenwerte. Snapshot-Lücken werden seit v3.20.0 (#145) **linear zwischen Nachbar-Stunden interpoliert**, statt das Delta in eine einzige Folge-Stunde aufzustauen. Tagessumme bleibt in jedem Fall korrekt (`snap[24] − snap[0]`).
4. **Monats-Rollup**: Beim Monatsabschluss werden Tageszusammenfassungen zu Monatswerten verdichtet.

> **Phase D Cleanup (v3.21.0):** Seit v3.21.0 ist der Zähler-Snapshot-Pfad die einzige kWh-Quelle — der frühere W-Integration-Fallback und das `EEDC_ENERGIEPROFIL_QUELLE`-Feature-Flag sind entfernt. Auf Anlagen mit korrekt gemappten Energiezählern unverändert; auf Anlagen ohne Mapping erscheinen Stunden-kWh-Felder als `NULL` statt geschätzter Werte (siehe „Strikte NULL-Semantik").

### Backward-Slot-Konvention (ab v3.20.0, #144)

Slot N enthält die Energie aus dem Intervall **[N−1, N)** — „die letzte Stunde". Industriestandard, konsistent mit HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber. Slot 0 eines Tages enthält die Energie 23:00–24:00 des Vortags. Strompreis-Stunden bleiben Forward (`[N, N+1)`, „gilt ab jetzt"). **Nach Update auf v3.20.0 nötig:** einmalig „Verlauf nachberechnen + überschreiben" auslösen.

### Strikte NULL-Semantik (ab v3.19.0)

Wenn keine kumulativen Zähler gemappt sind, bleiben die betroffenen `TagesEnergieProfil`-Felder `NULL` statt aus Leistungs-Samples geschätzt zu werden. Im Frontend zeigt eedc ein **⚠-Badge** neben IST-Werten bei Datenlücken — Klick öffnet den Reparatur-Popover (siehe Teil II §7.2).

### Restart-Recovery (v3.23.0)

Wird das Add-on zwischen `:55` und `:05` der Folgestunde neu gestartet, fehlten die Snapshots der laufenden und ggf. der gerade abgeschlossenen Stunde, weil die Cron-Trigger keine Misfire-Recovery hatten. **`sensor_snapshot_startup_recovery()`** läuft nach Scheduler-Start im Hintergrund: holt für die letzten 6 Stunden je Anlage HA-Statistics-Snapshots (idempotent dank Upsert) und für die laufende Stunde zusätzlich einen Live-Snapshot. Anschließend `aggregate_today_all` für sofortige Sichtbarkeit.

### Tagesreset-Heuristik für utility_meter

HA-`utility_meter`-Sensoren mit täglichem Reset (z. B. „Erzeugung heute") werfen um Mitternacht ein stark negatives Delta. Seit v3.23.0 erkennt eedc das Daily-Reset-Muster (`s1 < 0.5 ∧ s0 > 0.5`) und nimmt `max(0, s1)` als Slot-0-Wert (Energie seit Reset, typ. ≈ 0 nachts). Vorher war Slot 0 dauerhaft `None` und der ganze Tag wurde als „IST unvollständig" geflaggt.

### WP-Kompressor-Starts (ab v3.24.0, #136)

Optional pro WP-Investition über einen Total-Increasing-Sensor. Architektur trennt Counter-Felder strikt von kWh-Feldern (`KUMULATIVE_COUNTER_FELDER`), damit reine Counter nicht versehentlich in die Energie-Bilanz fließen. Vollbackfill aus HA Long-Term Statistics greift für Tages-Summen (Faktor 1.0 statt 0.001 bei unbekannter Einheit); Stunden-Detail wird ab Live-Erfassung gefüllt.

### Day-Ahead-Stundenprofil-Snapshot (intern, ab v3.23.4)

Zwei JSON-Felder in `TagesZusammenfassung` (`pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil`) speichern den ersten OpenMeteo-/Solcast-Forecast des Tages als 24-Werte-Liste (Backward-Slot-Konvention). First-write-wins: spätere Aufrufe am selben Tag überschreiben das Profil nicht. Reine Hintergrund-Datensammlung für künftige Diagnostik (Korrekturprofil-Konzept).

### Voraussetzungen

- Ein **Sensor-Mapping** muss eingerichtet sein (kumulative kWh-Zähler für PV, Verbrauch etc.)
- Funktioniert mit HA-Sensoren und MQTT-Inbound
- HA-History hat nur ~10 Tage Retention. eedc sichert die Daten dauerhaft, sodass auch langfristige Analysen (Jahresvergleiche, Speicher-Dimensionierung) möglich sind.

### Datenbestand & Aktionen

UI-Bedienung: **Einstellungen → Daten → Energieprofil** — siehe §1.6.

### Kraftstoffpreis-Backfill (ab v3.17.0)

Für die korrekte Berechnung der E-Auto-Ersparnis nutzt eedc echte monatliche Benzinpreise aus dem **EU Weekly Oil Bulletin**. Um Monatsdaten rückwirkend mit Preisen zu befüllen:

**API:**
- `POST /api/energie-profil/{anlage_id}/kraftstoffpreis-backfill/tages` — befüllt `TagesZusammenfassung.kraftstoffpreis_euro`
- `POST /api/energie-profil/{anlage_id}/kraftstoffpreis-backfill/monats` — befüllt `Monatsdaten.kraftstoffpreis_euro`

(Der frühere kombinierte Endpoint ist als Alias erhalten geblieben.)

UI-Bedienung:
- **Tagesebene**: Einstellungen → Daten → Energieprofil → Kraftstoffpreis-Backfill (Tages) — sichtbar nur bei offenen Tagen.
- **Monatsebene**: Einstellungen → Daten → Monatsdaten — Datenverwaltungs-Abschnitt unten, sichtbar nur bei offenen Monaten.

Der Backfill nutzt die Oil Bulletin History (seit 2005) und setzt nur Werte, wo noch keiner vorhanden ist. Kann gefahrlos mehrfach aufgerufen werden (z. B. nach jedem Datenimport).

**Automatisch:** Ein Scheduler-Job läuft wöchentlich (Dienstag 06:00) und befüllt neue Tage automatisch.

---

*Letzte Aktualisierung: April 2026 (v3.24.1)*
