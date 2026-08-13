
# EEDC Architektur-Dokumentation

**Stand: 2026-08-07** — Frontend-Kapitel (3 · 6 · 9) gegen den Baum neu erhoben.
**Nachgezogen am 2026-08-11:** der Berechnungs-Layer im Schichtenbild (Kapitalrechnung + Ertrags-Zerlegung).

> **Dieses Dokument trägt bewusst keine Versionsnummer.** Versions-SoT ist
> [CHANGELOG.md](../CHANGELOG.md) bzw. `eedc/backend/core/config.py::APP_VERSION`;
> `scripts/release.sh` bumpt `docs/` nicht. Der vorige Kopf stand auf „v3.24.1, April 2026" und
> beschrieb eine Oberfläche, die es seit v4.0.0 nicht mehr gibt.
>
> **Wo dieses Dokument nicht die letzte Instanz ist:**
>
> | Frage | SoT |
> | --- | --- |
> | Informationsarchitektur, Oberflächen-Invarianten I1–I16, Redirects | [KONZEPT-IA-V4.md](KONZEPT-IA-V4.md) |
> | Darstellung (Farben, Komponenten, Typografie, Charts), Regel 0/0a | [KONZEPT-STYLE-GUIDE.md](KONZEPT-STYLE-GUIDE.md) |
> | *Wo* eine Aggregat-Formel definiert wird | [ADR-001](ADR-001-BERECHNUNGS-LAYER.md) |
> | *Was* ein Wert behaupten darf, woher er kommt (P1–P10) | [ADR-002](ADR-002-WURZELMUSTER.md) |
> | die Monatszeile als **eine** Schicht (P10) | [KONZEPT-MONATS-FAKTEN.md](KONZEPT-MONATS-FAKTEN.md) |
> | Formeln je Kennzahl | [BERECHNUNGEN.md](BERECHNUNGEN.md) |
> | Einrichtung, Befehle, Gates, Dateibestand | [DEVELOPMENT.md](DEVELOPMENT.md) |
>
> Dieses Dokument beschreibt die **Gesamtsicht**: Schichten, Datenmodell, Services,
> Design-Entscheidungen. Wo eine Regel woanders steht, wird sie **verwiesen, nicht kopiert** — eine
> zweite Fassung daneben ist der Anfang der nächsten Drift.

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Technologie-Stack](#2-technologie-stack)
3. [Projektstruktur](#3-projektstruktur)
4. [Datenmodell](#4-datenmodell)
5. [API-Architektur](#5-api-architektur)
6. [Frontend-Architektur](#6-frontend-architektur)
7. [Services](#7-services)
8. [Design-Entscheidungen](#8-design-entscheidungen)
9. [Entwickler-Workflow](#9-entwickler-workflow)

---

## 1. Übersicht

### Architektur-Prinzipien

1. **Standalone-First:** eedc funktioniert ohne externe Abhängigkeiten — Home Assistant ist eine
   Option, keine Voraussetzung. Kernfunktionen dürfen nicht an HA hängen; HA-only-Funktionen sind
   sichtbar als solche gekennzeichnet und werden ausgeblendet, wenn kein HA da ist.
2. **Lokale Datenspeicherung:** SQLite unter `/data/eedc.db`, alle Daten bleiben beim Nutzer. Der
   Community-Server bekommt nur anonymisierte, ausdrücklich geteilte Aggregate.
3. **Vier Zeitebenen, eine Wahrheit je Größe:** Live (5-Minuten-Snapshots) · Tag (Stundenprofile) ·
   **Monat** (Zählerwerte, die abrechnungsrelevante Ebene) · Jahr. Die Monatsebene ist der Kern,
   aber längst nicht mehr die einzige — Tages- und Stundenebene entstehen aus eigenen Snapshots
   bzw. der HA-Langzeitstatistik.
4. **Datenquellen getrennt:** `Monatsdaten` trägt **Zählerwerte**, `InvestitionMonatsdaten` die
   **Komponenten-Details**. Legacy-Felder (`Monatsdaten.batterie_*`, das computed-Trio) werden nicht
   gelesen; `Monatsdaten.pv_erzeugung_kwh` ist ausschließlich **Eingang** der PV-Auflösung
   (ADR-002/P7).
5. **Ein Wert, eine Konstruktionsstelle:** jede Aggregat-Größe wird an genau einem Ort gebildet
   (ADR-001) und sagt, woher sie kommt (ADR-002). Zwei Sichten dürfen nicht zwei Zahlen für
   dieselbe Frage nennen — die häufigste Fehlerklasse dieses Projekts.
6. **Unvollständig heißt unvollständig:** eine Teilsumme wird als solche ausgewiesen, nicht als
   niedriger Wert ausgeliefert (ADR-002/P4). Eine Lücke ist keine 0.

### System-Architektur

```text
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│         React (HashRouter — HA-Ingress-Pfad ist dynamisch)   │
│   v4/ Sichten · components/ SoT-Bausteine · lib/ Ableitungen │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/REST  (/api/…)
┌────────────────────────┴────────────────────────────────────┐
│                     FastAPI Backend                         │
│  ┌────────┐  ┌──────────┐  ┌───────────────┐  ┌──────────┐  │
│  │ Routes │→ │ Services │→ │ berechnungen/ │  │  Models  │  │
│  │  HTTP  │  │ Beschaff.│  │  ADR-001-SoT  │  │  Tabellen│  │
│  └────────┘  └──────────┘  └───────────────┘  └──────────┘  │
│         APScheduler: Snapshot- · Prognose- · Korrektur-Jobs │
└────────────────────────┬────────────────────────────────────┘
                         │ SQLAlchemy (async)
┌────────────────────────┴────────────────────────────────────┐
│                      SQLite  /data/eedc.db                  │
│  Monatsdaten · InvestitionMonatsdaten · TagesEnergieProfil   │
│  TagesZusammenfassung · sensor_snapshots · MQTT-Snapshots     │
└─────────────────────────────────────────────────────────────┘

Externe Quellen (alle optional):
┌────────────┐ ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
│ Open-Meteo │ │ Bright Sky │ │  PVGIS   │ │ Solcast  │ │ EU Oil Bull. │
│  Wetter/   │ │   (DWD)    │ │ Jahres-  │ │ PV-Prog- │ │ Kraftstoff-  │
│  Solar-GTI │ │            │ │ prognose │ │  nose    │ │   preise     │
└────────────┘ └────────────┘ └──────────┘ └──────────┘ └──────────────┘
┌──────────────────────────────────────────┐ ┌────────────────────────┐
│ Home Assistant                           │ │ Geräte / Cloud-APIs    │
│  REST (States) · WebSocket (LTS) ·        │ │  9 Connectors (LAN)    │
│  Recorder-DB/-Datei · MQTT in UND out     │ │  12 Cloud-Provider     │
└──────────────────────────────────────────┘ └────────────────────────┘
                                             ┌────────────────────────┐
                                             │ eedc-community (opt-in)│
                                             │  anonyme Aggregate     │
                                             └────────────────────────┘
```

**Drei Wege zur HA-Langzeitstatistik**, in dieser Vorrangfolge: externe Recorder-DB
(`HA_RECORDER_DB_URL`, SQL) · eingehängte Recorder-Datei (`/config`, SQL) · **WebSocket**
`recorder/statistics_during_period` (braucht nur Token — der einzige Weg für einen
Standalone-Container neben HA). Alle drei liefern **dieselbe** Quelle; verzweigt wird ausschließlich
die Zeilen-Beschaffung, nicht die Aggregation.

---

## 2. Technologie-Stack

### Backend

> SoT ist `eedc/backend/requirements.txt` — dort stehen auch die **Obergrenzen**, die es aus
> Erfahrung gibt (FastAPI ist gedeckelt, damit ein Major-Sprung nicht still in ein HA-Add-on-Image
> gerät).

| Technologie | Version | Zweck |
|-------------|---------|-------|
| **Python** | 3.11+ | Programmiersprache |
| **FastAPI** | ≥ 0.109, **< 0.137** | REST-API-Framework (bewusst gedeckelt) |
| **Uvicorn** | ≥ 0.27 | ASGI-Server |
| **SQLAlchemy** | ≥ 2.0.25 | ORM, async |
| **aiosqlite** | ≥ 0.19 | async-SQLite-Treiber (**loop-gebunden** — sync-Aufrufer brauchen eine Brücke) |
| **SQLite** | 3.x | Datenbank |
| **Pydantic** | ≥ 2.5 (+ pydantic-settings) | Datenvalidierung, Settings |
| **httpx** | ≥ 0.26 | HTTP-Client für externe APIs |
| **websockets** | ≥ 12.0 | HA-WebSocket (Langzeitstatistik ohne DB-Zugang) |
| **aiomqtt** | ≥ 2.0 | MQTT — Export **und** Inbound |
| **APScheduler** | ≥ 3.10 | Snapshot-, Prognose- und Korrektur-Jobs |
| **WeasyPrint + Jinja2** | ≥ 62.0 / ≥ 3.1 | PDF-Berichte (HTML→PDF, SVG-Charts) |

### Frontend

| Technologie | Version | Zweck |
|-------------|---------|-------|
| **React** | 18.x | UI Framework |
| **TypeScript** | 5.x | Typsichere Programmierung |
| **Vite** | 5.x | Build Tool & Dev Server |
| **Tailwind CSS** | 3.x | Styling |
| **Recharts** | 2.x | Diagramme |
| **react-simple-maps** | 3.x | Choropleth Deutschlandkarte |
| **Lucide React** | - | Icons |
| **React Router** | 6.x | Routing |

### Deployment

| Variante | Technologie |
|----------|-------------|
| **Home Assistant Add-on** | Docker (Ingress) |
| **Standalone** | Docker |
| **Entwicklung** | Uvicorn + Vite Dev Server |

---

## 3. Projektstruktur

> **Den vollständigen Dateibestand führt [DEVELOPMENT.md §Projektstruktur](DEVELOPMENT.md#projektstruktur)**
> — bewusst an **einem** Ort. Zwei vollständige Listen in zwei Dokumenten driften garantiert
> auseinander; genau so ist die V3-Liste entstanden, die hier bis 2026-08-07 stand. Dieses Kapitel
> beschreibt die **Schichten und ihre Zuständigkeiten**.

### Die drei Repositories

| Repository | Rolle | Wird wie gepflegt |
| --- | --- | --- |
| **eedc-homeassistant** | **Source of Truth** — Backend, Frontend, Docs, HA-Add-on-Konfiguration, Website | hier wird gearbeitet |
| **eedc** | Standalone-Distribution für Nutzer ohne HA | **Spiegel**, ausschließlich per `scripts/release.sh` |
| **eedc-community** | anonymer Community-Benchmark-Server (FastAPI + PostgreSQL) | unabhängig; bei Datenmodell-Änderungen **synchron** anpassen |

Die Anwendung liegt vollständig unter `eedc/` — dasselbe Verzeichnis, das ins Standalone-Repo
gespiegelt wird. HA-spezifisch sind nur `config.yaml`, `Dockerfile`, `run.sh` und die Icons.

### Backend-Schichten (`eedc/backend/`)

Die Reihenfolge ist die Abhängigkeitsrichtung — **nach oben wird nie gerufen**:

| Schicht | Verzeichnis | Zuständig für | Darf nicht |
| --- | --- | --- | --- |
| **Routen** | `api/routes/` | HTTP, Validierung, Response-Form | rechnen — Aggregat-Formeln gehören in den Layer (ADR-001) |
| **Services** | `services/` | Beschaffung, Aufbereitung, externe APIs, Persistenz-Abläufe | eigene Fassungen einer Formel halten |
| **Berechnungs-Layer** | `core/berechnungen/` | **alle** Aggregat-Formeln, je Größe genau eine | I/O oder DB-Zugriff |
| **Modelle** | `models/` | SQLAlchemy-Tabellen | Fachlogik |
| **Kern** | `core/` | Config, Engine, Schema-Nachzug, SoT-Helper | — |

Drei Stellen sind dabei die tragenden **Single Sources of Truth**:

- **`services/monats_fakten.py`** — die Monatszeile wird **einmal** aufgelöst und gefiltert
  (`aktiv` · Anschaffung · Stilllegung · Dienstwagen), dann ruft sie die Layer-Formeln. Keine
  Read-Site faltet `InvestitionMonatsdaten` mehr selbst (ADR-002/P10,
  [KONZEPT-MONATS-FAKTEN.md](KONZEPT-MONATS-FAKTEN.md)).
- **`core/investition_kennwerte.py`** — Nennleistung je Typ, gleich ob sie in der Spalte oder im
  `parameter`-JSON liegt (ADR-002/P3-a).
- **`core/berechnungen/slot_konvention.py`** — Slot N ist die Energie in `[N-1, N)`, baumweit
  (Backward-Konvention, Industriestandard).

### Frontend-Schichten (`eedc/frontend/src/`)

| Schicht | Verzeichnis | Zuständig für |
| --- | --- | --- |
| **Sichten** | `v4/` | die ausgelieferte Oberfläche: eine Datei je Sicht bzw. Block |
| **Geteilte Bausteine** | `components/` | SoT-Komponenten (eine Klasse = eine Komponente), Block-Modell, Park-Mechanik |
| **Einstellungs-Flächen** | `pages/` | Stammdaten, Import-Assistenten, Datenverwaltung — von V4 eingebunden |
| **Ableitungen** | `lib/` | reine Funktionen + Farb-/Datums-/Einheiten-SoT |
| **Transport** | `api/` | ein Modul je Backend-Router, `client.ts` als Basis |
| **Zustand** | `hooks/`, `context/` | `useApiData` (inkl. SWR-Sicht-Cache), Auswahl, Theme, Status |
| **Wege** | `routes/`, `config/` | Route-Manifest + Redirects, Einstellungs-Katalog, Version |

⚠ **`eedc/frontend/dist/` ist versioniert** — das Add-on liefert diesen Build aus. Wer lokal mit
Demo-Flags baut, stellt `dist/` danach wieder her, sonst landet ein Demo-Build im Release.

---

## 4. Datenmodell

### Entity-Relationship Diagramm

```
┌─────────────────────────────────────────────────────────────┐
│                          Anlage                             │
│  id, name, adresse, koordinaten, ausrichtung, neigung       │
└──────┬──────────────┬──────────────┬──────────────┬─────────┘
       │              │              │              │
       │ 1:n          │ 1:n          │ 1:n          │ 1:n
       ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ Monatsdaten  │ │ Strompreise  │ │ Investitionen│ │ InfothekEintrag  │
│ (Zählerwerte)│ │ (Tarife)     │ │ (Komponenten)│ │ (Verträge, Daten)│
└──────────────┘ └──────────────┘ └──────┬───────┘ └────────┬─────────┘
                                        │                   │
                                        │ 1:n               │ 1:n
                                        ▼                   ▼
                              ┌──────────────────┐ ┌──────────────────┐
                              │ Investition-     │ │ InfothekDatei    │
                              │ Monatsdaten      │ │ (Fotos, PDFs)    │
                              └──────────────────┘ └──────────────────┘

                    Investitionen ◄── N:M ──► InfothekEintrag
                                  (infothek_investition Junction Table)
```

### Tabellen im Detail

#### Anlage

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlagenname | VARCHAR(255) | Bezeichnung |
| leistung_kwp | FLOAT | Anlagenleistung in kWp |
| installationsdatum | DATE | Inbetriebnahme (optional) |
| standort_land | VARCHAR(5) | Land: DE, AT oder CH |
| standort_plz | VARCHAR(10) | Postleitzahl |
| standort_ort | VARCHAR(255) | Ort |
| standort_strasse | VARCHAR(255) | Adresse |
| latitude | FLOAT | Breitengrad (für PVGIS) |
| longitude | FLOAT | Längengrad (für PVGIS) |
| ausrichtung | VARCHAR(50) | DEPRECATED – jetzt bei PV-Modul Investitionen |
| neigung_grad | FLOAT | DEPRECATED – jetzt bei PV-Modul Investitionen |
| wechselrichter_hersteller | VARCHAR(50) | sma, fronius, kostal, etc. |
| mastr_id | VARCHAR(20) | MaStR-ID der Anlage |
| versorger_daten | JSON | Versorger & Zähler |
| wettermodell | VARCHAR(30) | auto, meteoswiss_icon_ch2, icon_d2, icon_eu, ecmwf_ifs04 |
| sensor_mapping | JSON | HA-Sensor-Mapping |
| community_hash | VARCHAR(64) | Hash für Community-Löschung |
| steuerliche_behandlung | VARCHAR(30) | `keine_ust` oder `regelbesteuerung` |
| ust_satz_prozent | FLOAT | USt-Satz: DE=19, AT=20, CH=8.1 |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

#### Monatsdaten

**Wichtig**: Diese Tabelle enthält primär Zählerwerte (Einspeisung, Netzbezug).

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| jahr | INTEGER | Jahr |
| monat | INTEGER | Monat (1-12) |
| einspeisung_kwh | FLOAT | Zählerwert Einspeisung |
| netzbezug_kwh | FLOAT | Zählerwert Netzbezug |
| direktverbrauch_kwh | FLOAT | Berechnet |
| eigenverbrauch_kwh | FLOAT | Berechnet |
| gesamtverbrauch_kwh | FLOAT | Berechnet |
| globalstrahlung_kwh_m2 | FLOAT | Wetter-API |
| sonnenstunden | FLOAT | Wetter-API |
| durchschnittstemperatur | FLOAT | Wetter-API |
| netzbezug_durchschnittspreis_cent | FLOAT | Ø Strompreis bei dynamischem Tarif (ct/kWh) |
| kraftstoffpreis_euro | FLOAT | Ø Benzinpreis des Monats (€/L, aus EU Oil Bulletin) |
| sonderkosten_euro | FLOAT | Manuelle Eingabe |
| sonderkosten_beschreibung | VARCHAR(500) | Beschreibung der Sonderkosten |
| datenquelle | VARCHAR(50) | manual, csv, ha_import |
| notizen | VARCHAR(1000) | Freitext |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**Legacy-Felder (nicht mehr verwenden):**
- `pv_erzeugung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_ladung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_entladung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_ladung_netz_kwh` → Arbitrage (Legacy)
- `batterie_ladepreis_cent` → Arbitrage (Legacy)

#### Investitionen

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| typ | VARCHAR(50) | Investitionstyp (siehe InvestitionTyp Enum) |
| bezeichnung | VARCHAR(255) | Name der Komponente |
| anschaffungsdatum | DATE | Inbetriebnahme |
| anschaffungskosten_gesamt | FLOAT | Kaufpreis + Installation |
| anschaffungskosten_alternativ | FLOAT | Alternativkosten (z.B. neuer Verbrenner) |
| betriebskosten_jahr | FLOAT | Jährliche Betriebskosten |
| leistung_kwp | FLOAT | Leistung in kWp (PV-Module) |
| ausrichtung | VARCHAR(50) | Modulausrichtung (PV-Module) |
| neigung_grad | FLOAT | Modulneigung in Grad (PV-Module) |
| ha_entity_id | VARCHAR(255) | HA Entity-ID (für String-IST-Erfassung) |
| parameter | JSON | Typ-spezifische Parameter |
| einsparung_prognose_jahr | FLOAT | „Ertrag/Jahr" — wiederkehrender Ertrag/Einsparung, pflegbar bei Wallbox/Sonstiges (`ERTRAGSFELD_TYPEN`) |
| co2_einsparung_prognose_kg | FLOAT | CO2-Einsparungsprognose |
| aktiv | BOOLEAN | Aktiv/Inaktiv |
| parent_investition_id | INTEGER | Foreign Key → Investitionen (für Parent-Child) |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**Investitionstypen:**

| Typ | Parameter (JSON) |
|-----|------------------|
| `wechselrichter` | - |
| `pv-module` | anzahl_module, modul_leistung_wp, ausrichtung, neigung_grad |
| `speicher` | kapazitaet_kwh, arbitrage_faehig |
| `e-auto` | v2h_faehig, nutzt_v2h, ist_dienstlich |
| `waermepumpe` | effizienz_modus, jaz, cop_heizung, cop_warmwasser, heizwaermebedarf_kwh, warmwasserbedarf_kwh, leistung_kw, pv_anteil_prozent, alter_energietraeger, alter_preis_cent_kwh, sg_ready |
| `wallbox` | ist_dienstlich |
| `balkonkraftwerk` | leistung_wp, anzahl, hat_speicher, speicher_kapazitaet_wh |
| `sonstiges` | kategorie (erzeuger/verbraucher/speicher), beschreibung |

**Legacy-Felder im `parameter` JSON (nicht mehr im Formular):**

Die folgenden Felder (`stamm_*`, `ansprechpartner_*`, `wartung_*`) wurden aus dem Investitionsformular entfernt. Gerätedaten, Ansprechpartner und Wartungsverträge werden jetzt über die **Infothek** verwaltet (N:M-Verknüpfung). Bestehende Daten bleiben im `parameter`-JSON erhalten und können über den Migrations-Service (`infothek_migration.py`) automatisch in Infothek-Einträge überführt werden.

#### InvestitionMonatsdaten

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| investition_id | INTEGER | Foreign Key → Investitionen |
| jahr | INTEGER | Jahr |
| monat | INTEGER | Monat (1-12) |
| verbrauch_daten | JSON | Typ-spezifische Messwerte |
| einsparung_monat_euro | FLOAT | Berechnet |
| co2_einsparung_kg | FLOAT | Berechnet |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**Hinweis:** Sonstige Erträge/Ausgaben werden in `verbrauch_daten` als `sonstige_ertraege` / `sonstige_ausgaben` Arrays gespeichert (v2.4.0).

**verbrauch_daten Struktur je nach Investitionstyp:**

```json
// PV-Module
{
  "pv_erzeugung_kwh": 450.5
}

// Speicher
{
  "ladung_kwh": 200.0,
  "entladung_kwh": 185.0,
  "ladung_netz_kwh": 50.0,        // Arbitrage
  "ladepreis_cent": 15.5          // Arbitrage
}

// E-Auto
{
  "km_gefahren": 1200,
  "verbrauch_kwh": 216.0,
  "ladung_pv_kwh": 130.0,
  "ladung_netz_kwh": 86.0,
  "ladung_extern_kwh": 50.0,
  "ladung_extern_euro": 25.0,
  "v2h_entladung_kwh": 25.0
}

// Wärmepumpe
{
  "stromverbrauch_kwh": 450.0,
  "heizenergie_kwh": 1800.0,
  "warmwasser_kwh": 200.0
}

// Wallbox
{
  "ladung_kwh": 150.5,
  "ladevorgaenge": 10
}

// Balkonkraftwerk (mit optionalem Speicher)
{
  "pv_erzeugung_kwh": 45.0,
  "eigenverbrauch_kwh": 40.0,
  "speicher_ladung_kwh": 10.0,
  "speicher_entladung_kwh": 8.0
}

// Sonstiges - Erzeuger (v2.4.0)
{
  "erzeugung_kwh": 120.0,
  "eigenverbrauch_kwh": 100.0,
  "einspeisung_kwh": 20.0
}

// Sonstiges - Verbraucher (v2.4.0)
{
  "verbrauch_kwh": 200.0,
  "bezug_pv_kwh": 80.0,
  "bezug_netz_kwh": 120.0
}

// Sonstiges - Speicher (v2.4.0)
{
  "ladung_kwh": 50.0,
  "entladung_kwh": 45.0
}

// Sonstige Erträge & Ausgaben (alle Typen, v2.4.0)
{
  "sonstige_ertraege": [{"bezeichnung": "Einspeisebonus", "betrag": 15.0}],
  "sonstige_ausgaben": [{"bezeichnung": "Versicherung", "betrag": 8.50}]
}
```

**versorger_daten Struktur (Anlage):**

```json
{
  "strom": {
    "name": "Stadtwerke München",
    "kundennummer": "12345678",
    "portal_url": "https://kundenportal.swm.de",
    "notizen": "",
    "zaehler": [
      {"bezeichnung": "Einspeisung", "nummer": "1EMH0012345678", "notizen": ""},
      {"bezeichnung": "Bezug", "nummer": "1EMH0087654321", "notizen": "Zweirichtungszähler"}
    ]
  },
  "gas": {
    "name": "Stadtwerke München",
    "kundennummer": "G-98765",
    "zaehler": [{"bezeichnung": "Erdgas", "nummer": "G12345678", "notizen": ""}]
  },
  "wasser": {
    "name": "Wasserwerke XY",
    "kundennummer": "W-11111",
    "zaehler": [{"bezeichnung": "Kaltwasser", "nummer": "WZ-123", "notizen": ""}]
  }
}
```

#### Strompreise

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| netzbezug_arbeitspreis_cent_kwh | FLOAT | Preis pro kWh Netzbezug |
| einspeiseverguetung_cent_kwh | FLOAT | Vergütung pro kWh Einspeisung |
| grundpreis_euro_monat | FLOAT | Monatlicher Grundpreis |
| gueltig_ab | DATE | Gültigkeitsbeginn |
| gueltig_bis | DATE | Gültigkeitsende (NULL = aktuell gültig) |
| tarifname | VARCHAR(255) | Name des Tarifs |
| anbieter | VARCHAR(255) | Stromanbieter |
| vertragsart | VARCHAR(50) | fix, dynamisch, etc. |
| verwendung | VARCHAR(30) | `allgemein`, `waermepumpe` oder `wallbox` |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

#### InfothekEintrag (v3.5.0, N:M v3.15.2)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| bezeichnung | VARCHAR(255) | Name des Eintrags |
| kategorie | VARCHAR(50) | Kategorie (15 Typen, siehe Handbuch) |
| notizen | TEXT | Freitext-Notizen (Markdown) |
| parameter | JSON | Kategorie-spezifische Felder |
| investition_id | INTEGER | Legacy 1:1 FK (deprecated, nur Migration) |
| ansprechpartner_id | INTEGER | FK → InfothekEintrag (Vertragspartner-Verweis) |
| sortierung | INTEGER | Reihenfolge |
| aktiv | BOOLEAN | Archiviert = false |
| in_anlagendoku | BOOLEAN | In Anlagendokumentation-PDF anzeigen |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**15 Kategorien:** stromvertrag, einspeisevertrag, gasvertrag, wasservertrag, fernwaerme, brennstoff, versicherung, ansprechpartner, wartungsvertrag, marktstammdatenregister, foerderung, garantie (Komponente/Datenblatt), steuerdaten, messstellenbetreiber, sonstiges

#### InfothekInvestition (Junction Table, N:M)

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| infothek_eintrag_id | INTEGER | FK → InfothekEintrag (CASCADE) |
| investition_id | INTEGER | FK → Investitionen (CASCADE) |

#### InfothekDatei

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| eintrag_id | INTEGER | FK → InfothekEintrag (CASCADE) |
| dateiname | VARCHAR(255) | Originaler Dateiname |
| dateityp | VARCHAR(10) | `image` oder `pdf` |
| mime_type | VARCHAR(50) | MIME-Typ |
| beschreibung | VARCHAR(255) | Optionale Beschreibung |
| daten | LARGEBINARY | Datei-BLOB (Bilder max ~500 KB, PDFs max 10 MB) |
| thumbnail | LARGEBINARY | Vorschaubild (nur für Bilder) |
| created_at | DATETIME | Erstellungsdatum |

### Parent-Child Beziehungen

```
Wechselrichter (Parent)
├── PV-Module (Child) [Pflicht]
└── DC-Speicher (Child) [Optional, für Hybrid-WR]

AC-Speicher [Eigenständig]
E-Auto [Eigenständig]
Wärmepumpe [Eigenständig]
Wallbox [Eigenständig]
Balkonkraftwerk [Eigenständig]
Sonstiges [Eigenständig]
```

**PV-System ROI-Aggregation:**
- Wechselrichter + zugeordnete PV-Module + DC-Speicher = "PV-System"
- ROI wird auf System-Ebene berechnet
- Einsparungen werden proportional nach kWp verteilt

---

## 5. API-Architektur

### Route-Übersicht

> **Die Prefix-Tabelle steht in [DEVELOPMENT.md §API-Routen Übersicht](DEVELOPMENT.md#api-routen-übersicht)**
> — an **einem** Ort, erhoben aus `backend/main.py`. Die Kopie, die hier bis 2026-08-07 stand, war
> an sechs Stellen falsch (`/api/daten-checker` und `/api/system-logs` liegen beide unter
> `/api/system`, `/api/data-import` heißt `/api/portal-import`, `mqtt_gateway` und `mqtt_presets`
> liegen unter `/api/live`, `ha_export` hat gar kein eigenes Prefix).

**Was architektonisch daran wichtig ist:**

- **Ein Modulname sagt nichts über sein Prefix.** Mehrere Module teilen sich eines (`/api/live`
  trägt fünf, `/api/system` zwei, `/api/aussichten` zwei), und drei Module hängen direkt unter
  `/api` (Monatsabschluss, Community, HA-Export). SoT sind die `include_router`-Aufrufe.
- **HA-only-Router werden bedingt eingehängt** (`HA_MODE`): `ha_integration`, `ha_import`,
  `sensor_mapping`, `ha_statistics`. `ha_remote` **nicht** — die Verbindung per Token gehört zum
  Standalone-Betrieb.
- **Einige System-Endpunkte liegen inline in `main.py`**, nicht in einem Router:
  `/api/health` · `/api/settings` · `/api/scheduler` (+ `/api/scheduler/monthly-snapshot`) ·
  `/api/updates/check` · `/api/stats` — dazu die SPA-Auslieferung als Catch-all.
- ⚠ **Die SPA beantwortet JEDEN Pfad mit HTTP 200 und HTML.** Ein Statuscode belegt daher **keinen**
  Endpunkt; wer eine API prüft, prüft den **Inhalt** und macht die Gegenprobe mit einem frei
  erfundenen Pfad.

### Wichtige Endpoints

#### Cockpit (Dashboard-Daten)

```
GET /api/cockpit/uebersicht/{anlage_id}?jahr=2025       # Haupt-Dashboard
GET /api/cockpit/prognose-vs-ist/{anlage_id}             # PVGIS SOLL vs IST
GET /api/cockpit/nachhaltigkeit/{anlage_id}              # CO2-Bilanz — die EINE CO₂-Quelle: Cockpit/Jahr + Auswertungen/CO₂ (ganze Historie, kein ?jahr=)
GET /api/cockpit/komponenten-zeitreihe/{anlage_id}       # Komponenten-Zeitreihen
GET /api/cockpit/pv-strings/{anlage_id}                  # String-Vergleich (Jahres-Ansicht)
GET /api/cockpit/pv-strings-gesamtlaufzeit/{anlage_id}   # String-Vergleich (Gesamtlaufzeit)
```

`uebersicht` liefert aggregierte Daten für alle Dashboard-Sektionen:
- Energiebilanz (Erzeugung, Verbrauch, Einspeisung)
- Effizienz (Autarkie, EV-Quote)
- Komponenten-Status
- Finanzen (inkl. `jahres_rendite_prozent` = Jahres-Ertrag / Investition), CO2

**Datenquellen:**
- Monatsdaten: Einspeisung, Netzbezug
- InvestitionMonatsdaten: Alle Komponenten-Details

Beides kommt **aufbereitet** aus `services/monats_fakten.py` (s. §7 „Lese-Schichtung"), nicht als Roh-Faltung im Endpoint — dort greifen auch die Zeitfilter. Der Umbau läuft sichtweise (S2–S6); bis dahin faltet ein Teil der Endpoints noch selbst.

#### Aussichten (Prognosen)

```
GET /api/aussichten/kurzfristig/{anlage_id}   # 7-Tage Wetterprognose
GET /api/aussichten/wetter/{anlage_id}        # Wetterdaten für Prognose
GET /api/aussichten/langfristig/{anlage_id}   # 12-Monats-Prognose (PVGIS)
GET /api/aussichten/trend/{anlage_id}         # Trend-Analyse + Degradation
GET /api/aussichten/finanzen/{anlage_id}      # Finanz-Prognose + Amortisation
```

**4 Prognose-Tabs:**
- **Kurzfristig**: 7-Tage Wetterprognose (Open-Meteo) mit Erzeugungsschätzung
- **Langfristig**: 12-Monats-Prognose basierend auf PVGIS und Performance-Ratio
- **Trend**: Jahresvergleich, saisonale Muster, Degradationsberechnung
- **Finanzen**: Amortisations-Fortschritt, Komponenten-Beiträge, Mehrkosten-Ansatz

**ROI-Metrik**: `amortisations_fortschritt_prozent` = Kumulierte Erträge / Investition
(Unterscheidet sich von Cockpit `jahres_rendite_prozent`!)

#### Sensor-Mapping API

```
GET    /api/sensor-mapping/{anlage_id}/suggest            # Vorschläge aus der HA-Energiekonfiguration (#197)
```

> **Seit 2026-08-13 ist das der einzige Endpunkt dieses Routers** (Fund N-241). Fünf
> weitere — Mapping lesen · Sensor-Liste · speichern · löschen · Status — sind stillgelegt:
> ihre Oberfläche ist mit dem IA-V4-Flip gefallen, und `POST` schrieb weiter auf
> `Anlage.sensor_mapping`, ohne den Historie-Hinweis auszulösen, den die
> Datenquellen-Fläche seit Konzept #192 B zeigt. Die heutigen Wege sind
> `GET/POST /api/datenquellen/{id}/felder` (lesen · speichern) und
> `GET /api/datenquellen/{id}/ha/sensoren` (Sensor-Liste).
>
> Der Router bleibt supervisor-gebunden gemountet (`main.py`, `HA_INTEGRATION_AVAILABLE`).
> ⚠ Diese Liste nannte bis dahin ein `POST …/init-start-values`, **das es baumweit nie gab**.

**Mapping-Strategien:**
- `sensor` - Direkter HA-Sensor
- `kwp_verteilung` - Anteilige Verteilung nach kWp
- `cop_berechnung` - COP-basierte Berechnung (Wärmepumpe)
- `ev_quote` - Eigenverbrauchsquote-Berechnung
- `manuell` - Manuelle Eingabe im Wizard
- `keine` - Nicht erfassen

#### Monatsabschluss API

```
GET  /api/monatsabschluss/{anlage_id}/{jahr}/{monat}    # Status + Vorschläge
POST /api/monatsabschluss/{anlage_id}/{jahr}/{monat}    # Abschluss durchführen
GET  /api/monatsabschluss/naechster/{anlage_id}         # Nächster offener Monat
GET  /api/monatsabschluss/historie/{anlage_id}          # Letzte Abschlüsse
```

**VorschlagService liefert intelligente Vorschläge:**
- `vormonat` (Konfidenz 80%) - Wert vom Vormonat
- `vorjahr` (Konfidenz 70%) - Wert vom gleichen Monat im Vorjahr
- `berechnung` (Konfidenz 60%) - COP/EV-Quote basierte Berechnung
- `durchschnitt` (Konfidenz 50%) - Durchschnitt aller vorhandenen Werte

#### Scheduler API

```
GET  /api/scheduler                               # Scheduler-Status
POST /api/scheduler/monthly-snapshot              # Manueller Monatswechsel-Trigger
```

#### Aggregierte Monatsdaten

```
GET /api/monatsdaten/aggregiert/{anlage_id}?jahr=2025[&inkl_ohne_zaehlerzeile=true]
```

Liefert Monatsdaten mit allen Komponenten-Summen:
- Zählerwerte aus Monatsdaten (Einspeisung, Netzbezug)
- PV-Erzeugung aggregiert aus allen PV-Modulen
- Speicher-Daten (Ladung, Entladung)
- WP/E-Auto/Wallbox-Daten
- Berechnete Kennzahlen (Direktverbrauch, Eigenverbrauch, Autarkie)

Die Monatsgrößen kommen seit **C1a** aus der Monats-Fakten-Schicht (§7, ADR-002/P10).

**`inkl_ohne_zaehlerzeile`** (Default `false`, seit **N-68**) entscheidet über die
**Zeilenmenge**, nicht über die Werte. Eine `Monatsdaten`-Zeile entsteht erst beim
**Monatsabschluss**; die Schicht kennt einen gelaufenen Monat auch ohne sie
(`meta.hat_zaehlerzeile is False`). Die Trennlinie verläuft zwischen zwei
Konsumenten-Arten:

| Konsument | Flag | Warum |
| --- | --- | --- |
| **Datensatz-Liste** (*Auswertungen → Tabelle*) | aus | eine Zeile ohne Datensatz kann man weder bearbeiten noch löschen |
| **Zeitreihe** (*Cockpit → Jahr*: Verlauf, Rail, Vorjahr/Ø-Spalten) | an | sonst zeichnet sie weniger Monate, als die Kennzahl darüber zählt |

Zeilen ohne Zählerzeile tragen `id: null`, keine Zählerwerte (Einspeisung/Netzbezug
`0.0` aus der Schicht) und weder `globalstrahlung_kwh_m2` noch `sonnenstunden` noch
`netzbezug_durchschnittspreis_cent` — **`None`, nicht 0**. Die aus den
`InvestitionMonatsdaten` gerechneten Größen sind vollständig. Monate **ohne jede
Spur** liefert die Schicht ohnehin nicht, das Flag holt also keine Null-Zeilen ins
Bild.

#### CSV Import

```
POST /api/import/csv/{anlage_id}
Content-Type: multipart/form-data

file: [CSV-Datei]
```

**Verarbeitung:**
1. CSV parsen (flexible Spalten-Erkennung)
2. Basis-Felder → Monatsdaten-Tabelle
3. Investitions-Felder → InvestitionMonatsdaten-Tabelle
4. Duplikate: Upsert (überschreiben)
5. `flag_modified()` für JSON-Felder

**Plausibilitätsprüfungen:**
- Legacy-Spalten (`PV_Erzeugung_kWh`, `Batterie_*_kWh`) werden validiert
- Fehler wenn NUR Legacy und PV-Module/Speicher existieren
- Fehler bei Mismatch Legacy vs. Summe Komponenten-Werte
- Warnung wenn redundant (±0.5 kWh Toleranz)
- Negative Werte werden blockiert
- Plausibilitätswarnungen (Sonnenstunden > 400h, Globalstrahlung > 250)

#### JSON Export/Import (Export-Version 1.1)

```
GET  /api/import/export/{anlage_id}          # Vollständiger JSON-Export
GET  /api/import/template/{anlage_id}        # CSV-Template herunterladen
GET  /api/import/template/{anlage_id}/download  # CSV-Template Download
GET  /api/import/pdf/{anlage_id}             # PDF-Export
POST /api/import/demo                        # Demo-Daten erstellen
DELETE /api/import/demo                      # Demo-Daten löschen
```

**Export** - Vollständige Anlage mit allen verknüpften Daten:
- Anlage-Stammdaten (inkl. versorger_daten, mastr_id, wetter_provider)
- **sensor_mapping** - HA Sensor-Zuordnungen
- Strompreise
- Investitionen (hierarchisch mit Children)
- Monatsdaten mit InvestitionMonatsdaten (inkl. durchschnittstemperatur, sonderkosten)
- PVGIS-Prognosen

**Import** - Restore aus JSON-Export:
- Erstellt neue Anlage (oder überschreibt bei gleichem Namen)
- sensor_mapping wird importiert, aber `mqtt_setup_complete=false`
- Rückwärtskompatibel mit Export-Version 1.0
### Request/Response Pattern

```python
# Typisches Schema-Pattern
class MonatsdatenCreate(BaseModel):
    anlage_id: int
    jahr: int
    monat: int
    einspeisung_kwh: float
    netzbezug_kwh: float
    investitions_daten: Optional[Dict[int, Dict]] = None

class MonatsdatenResponse(MonatsdatenCreate):
    id: int
    direktverbrauch_kwh: Optional[float]
    eigenverbrauch_kwh: Optional[float]
    # ... berechnete Felder
```

---

## 6. Frontend-Architektur

> **Verbindlich für die Informationsarchitektur ist [KONZEPT-IA-V4.md](KONZEPT-IA-V4.md)**
> (Achsen, Invarianten I1–I16, Redirect-Mechanik), für die Darstellung
> [KONZEPT-STYLE-GUIDE.md](KONZEPT-STYLE-GUIDE.md) (Regel 0/0a). Dieses Kapitel beschreibt, **wie**
> das im Code liegt — es definiert keine Regeln daneben.

### Drei Achsen, eine Frage je Achse

Seit dem IA-V4-Flip (v4.0.0) ist die Oberfläche nach **Fragen** geschnitten, nicht nach Geräten:

| Achse | Frage | Sektion | Unterteilung |
| --- | --- | --- | --- |
| Zeit | **Wann?** | **Cockpit** | Live · Tag · Monat · Jahr · Aussicht |
| Gerät | **Was?** | **Komponenten** | je Typ: Status → Verlauf → Vergleich → Wirtschaftlichkeit |
| Methode | **Wie?** | **Auswertungen** | Finanzen · ROI · Prognose-vs-IST · CO₂ · Tabelle |
| — | Vergleich | **Community** | Übersicht · PV-Ertrag · Komponenten · Regional · Trends · Statistiken |
| — | Einrichtung | **Einstellungen** | Kachel-Übersicht je Kategorie |

Eine zeitbezogene Auswertung gehört damit ins **Cockpit**, eine über die Lebensdauer einer
Komponente in den **Hub** — diese Zuordnung ist die häufigste Entscheidung beim Bau einer neuen
Sicht.

### Routing-Struktur

**`HashRouter`** (nicht `BrowserRouter`), weil der HA-Ingress-Pfad dynamisch ist: URLs erscheinen
als `/#/cockpit/live`. Die V4-Routen sind **prefix-frei** — der frühere `/v4`-Präfix ist mit dem
Flip gefallen.

```text
/                          → Navigate → /cockpit/live
├── cockpit                → Navigate → /cockpit/live
├── cockpit/:zeit          → CockpitV4      (live · tag · monat · jahr · aussicht)
├── komponenten            → KomponentenV4  (Auswahl)
├── komponenten/:typ       → KomponentenV4  (pv-anlage · speicher · bkw · waermepumpe ·
│                                            wallbox · e-auto · sonstiges)
├── auswertungen           → Navigate → /auswertungen/finanzen
├── auswertungen/:sub      → AuswertungenV4 (finanzen · roi · prognose · co2 · tabelle)
├── community              → Navigate → /community/uebersicht
├── community/:sub         → CommunityV4    (uebersicht · pv-ertrag · komponenten ·
│                                            regional · trends · statistiken)
├── hilfe                  → HilfeV4
├── einstellungen          → Navigate → /einstellungen/stammdaten
├── einstellungen/:kategorie → EinstellungenV4 (stammdaten · komponenten · infothek · daten ·
│                                               integration · datenquellen · system)
└── dev/design-preview     → DesignPreview   (nur Entwicklung)
```

**Alle Alt-Pfade werden umgeleitet, keiner läuft in ein 404.** SoT dafür ist
`src/routes/routeManifest.ts`:

- `LEGACY_REDIRECTS` — die Alt→Neu-Tabelle, von `App.tsx` als `<Navigate replace>` gerendert.
  Sie trägt drei Klassen: V3-Top-Level (`live` → `/cockpit/live`), **Achsenwechsel** der
  Gerätepfade (`cockpit/speicher` → `/komponenten/speicher` — Geräte sind keine Zeit-Frage mehr)
  und die **Re-Kategorisierung** der Einstellungs-Routen (`einstellungen/sensor-mapping` →
  `/einstellungen/datenquellen`).
- `REAL_ROUTE_PATHS` — das Inventar der echten Routen; es muss mit den `<Route>`-Pfaden in
  `App.tsx` synchron bleiben.
- `src/routes/redirects.test.tsx` prüft beides maschinell: jeder Alt-Pfad landet auf einer echten
  Route, **ohne Redirect-Kette**.

Dazu drei Sonderfälle in `App.tsx`: Splat-Fänger für gelöschte dynamische Alt-Sektionen
(`aussichten/*`, `monatsabschluss/*`) und eine Versicherung für `/v4/*`-Bookmarks.

### Komponenten-Hierarchie

```text
main.tsx
├── ThemeProvider                    # Light/Dark (context/ThemeContext)
└── AppWithSetup                     # Ersteinrichtung vor der App
    └── App.tsx
        └── HashRouter
            └── AppErrorBoundary     # um den GANZEN Routenbaum (#207)
                └── Suspense         # LayoutV4 → Cockpit → Live lazy, für langsame Zugänge
                    └── LayoutV4 (v4/)
                        ├── AnlagenSelektor · ReloadButton
                        ├── GlobalStatusProvider + StatusFusszeile (v4/status/)
                        └── <Outlet />
                            └── CockpitV4 · KomponentenV4 · AuswertungenV4 ·
                                CommunityV4 · EinstellungenV4 · HilfeV4
```

### Das Block-Modell

Eine V4-Sicht ist eine **Liste von Blöcken**, nicht ein Seitenlayout. Jeder Block ist verschiebbar,
fokussierbar (⤢) und parkbar:

| Baustein | Ort | Aufgabe |
| --- | --- | --- |
| `BlockShell` | `components/blocks/` | Rahmen, Titel, Fokus-Knopf, Parken-Geste |
| `FokusVollbild` · `FokusKachel` | `components/blocks/` | **ein** geteiltes Overlay für alle Sichten |
| `BlockStackSkeleton` | `components/blocks/` | Ladezustand als Block-Stapel statt Spinner |
| `KpiStrip` · `VerteilungsBalken` · `HerkunftZeile` | `components/blocks/` | wiederkehrende Block-Inhalte |
| `Parkbar` · `GeparktBlock` · `ParkContext` · `ParkFuss` | `components/park/` | Park-Zustand je Sicht (persistiert) |
| `useSectionOrder` | `hooks/` | Reihenfolge der Blöcke je Sicht (persistiert) |

**Park-Doktrin (I3):** eine Parkbar trägt **eine atomare Anzeige**. Wer einen Block parkt, parkt
genau das, was er sieht — nicht eine Gruppe, aus der später etwas Unerwartetes wieder auftaucht.

### State Management

**Kein globaler Store.** Vier Mechanismen, jeder mit klarer Zuständigkeit:

1. **`useApiData(fetcher, deps, opts)`** für Server-State — inklusive **SWR-Sicht-Cache** (opt-in
   über `swrKey`). Ohne ihn fetchte jede Sicht beim Tab-Wechsel neu und zeigte ein Skeleton,
   obwohl die Daten Sekunden alt waren (#218). Mit `swrKey` stehen beim Remount die alten Daten
   sofort, still revalidiert wird trotzdem (`reloading`). Der Cache ist ein **Modul-Singleton**
   mit LRU-Grenze und stirbt mit dem Browser-Tab; Tests leeren ihn über
   `_clearSwrCacheForTests()`.
2. **Context** für Theme (`ThemeContext`) und den globalen Status (`GlobalStatusProvider`).
3. **`localStorage`** für Präferenzen: Anlagen-Auswahl, Block-Reihenfolge, Park-Zustand,
   Spalten-Toggles, Wizard-Fortschritt.
4. **URL** für alles, was ein Link tragen muss: Sektion, Zeitraum-Achse, Gerätetyp, Unter-Sicht.

### Custom Hooks (`src/hooks/`)

| Hook | Zweck |
| --- | --- |
| `useApiData` | async Fetch mit Loading/Error + SWR-Sicht-Cache |
| `useSelectedAnlage` | Anlagen-Auswahl mit Auto-Select und Persistierung |
| `useAnlagen` · `useInvestitionen` · `useMonatsdaten` · `useStrompreise` | Bestandsdaten |
| `useYearSelection` | verfügbare Jahre + Auswahl |
| `useSectionOrder` | Block-Reihenfolge je Sicht |
| `useEinstellungenStatus` | Status-Ampeln der Einstellungs-Kacheln |
| `useHelpKatalog` · `useFeldHinweise` | In-App-Hilfe und Feld-Hinweise |
| `useHAAvailable` | HA-only-Funktionen ausblenden, wenn kein HA da ist |
| `useLegendenToggle` · `useSchmaleAchse` · `useScrollErhalt` · `useTouchTitleTooltip` | Anzeige-Verhalten (auch mobil) |
| `useSetupWizard` | Ersteinrichtung |

### Geteilte SoT-Komponenten (`src/components/`)

**Eine Komponenten-Klasse = EINE Komponente** (I12). Eine zweite Fassung neben einer bestehenden
ist ein Regelbruch, nicht eine Variante:

| Verzeichnis | Inhalt |
| --- | --- |
| `ui/` | Card · Button · Modal · Table/WerteTabelle · ChartTooltip · Badge · CsvExport … |
| `blocks/` · `park/` | Block-Modell und Park-Mechanik (siehe oben) |
| `charts/` | Chart-Bausteine (Achsen, Legende) — Konventionen im Style-Guide |
| `forms/` | Formular-Controls; **Roh-Controls sind gewächtert** (`check:roh-controls`, `check:form-controls`) |
| `live/` | `EnergieFluss` (animiertes SVG), `EnergieBilanz`, `WetterWidget` … |
| `monatsabschluss/` | das Monatsabschluss-**Formular** (seit v4.0.0 ein Formular statt 7 Schritten) |
| `sensor-mapping/` · `connector/` · `import/` · `setup-wizard/` | Einrichtung und Import |
| gerätespezifisch | `pv/` · `speicher/` · `waermepumpe/` · `wallbox/` · `eauto/` · `balkonkraftwerk/` |
| fachlich | `finanzen/` · `roi/` · `aussicht/` · `prognose/` · `tag/` · `werte/` · `infothek/` · `repair/` |

### Utility-Library (`src/lib/`)

| Modul | Inhalt |
| --- | --- |
| `colors.ts` | **Farb-SoT.** Eine Datenrolle = eine Farbe; Inline-Hex außerhalb ist gewächtert (`check:design`) |
| `einheiten.ts` | Zahl-/Einheiten-Formatierung (kWh, €, %, CO₂) — deutsche Konvention, `%` mit Leerzeichen |
| `datum.ts` | `heuteIso` · `toIsoDatum` · `verschiebeIsoTage` — **lokale** Uhr, nie UTC (`check:datum-utc`) |
| `monatsLuecken.ts` | „welcher Monat ist offen" inkl. **Binnen**-Lücken |
| `chartAchse.ts` · `blockStyle.ts` · `komponentenStyle.ts` | Achsen- und Stil-Ableitungen |
| `investitionAktiv.ts` | die drei Achsen von „aktiv" (Flag · Anschaffung · Stilllegung) |
| `investitionParameter.ts` | Parameter-Keys **gemeinsam mit dem Backend** (`core/investition_parameter.py`) |
| `erzeugerSpalten.ts` · `pvHerkunft.ts` · `erfassungZustand.ts` · `sollErfuellung.ts` | Tabellen- und Zustands-Ableitungen |
| `stundenSlot.ts` | Slot-Konvention im Client (Backward, wie `core/berechnungen/slot_konvention.py`) |
| `prognoseAnzeige.ts` · `prognoseHinweise.ts` | Prognose-Darstellung und ihre Hinweistexte |
| `calculations.ts` · `constants.ts` · `fieldDefinitions.ts` · `flags.ts` · `download.ts` | Rest |

### Was der Client NICHT tut

- **Keine CO₂-Menge konstruieren** — sie kommt aus `/cockpit/nachhaltigkeit` (ADR-001/DI-2,
  Wächter `check:co2-roh`).
- **Keine Nennleistung aus der Rohspalte rechnen** — Anzeige und Rechnung lesen
  `leistung_kwp_effektiv` aus der Response; die Rohspalte gehört Formularen (P3-a, Wächter
  `check:kennwert-roh`).
- **Keine Monatsgröße selbst falten** — das ist Aufgabe der Monats-Fakten im Backend (P10).

---

## 7. Services

### Lese-Schichtung: von der Tabelle zur Kennzahl

Zwischen den Tabellen und den auswertenden Endpoints liegen **drei** Schichten, und die Reihenfolge ist keine Geschmacksfrage — sie ist das Ergebnis von zwei Drift-Inventuren (#326 und der Inventur der Lese-Sichten vom 2026-07-31):

```
Monatsdaten · InvestitionMonatsdaten · Strompreise · TagesZusammenfassung
        │
        ▼   services/monats_fakten.py        ← Aufbereitung  (ADR-002/P10)
   MonatsFakt je (jahr, monat): zaehler · erzeugung · bkw · speicher · emob ·
   wp · sonstiges · tarif · eeg · kennzahlen · meta
   Hier — und nur hier — greifen die Zeitfilter (aktiv · Anschaffung ·
   Stilllegung) und der Dienstwagen-Filter. Nutzt intern pv_monatswerte.py (P7).
        │
        ▼   core/berechnungen/               ← Formeln       (ADR-001)
   berechne_verbrauchs_kennzahlen · berechne_finanz_aggregat · imd_typ_beitrag ·
   bkw_finanz_beitrag · erzeugung_hinter_zaehler_kwh ·
   berechne_dienstliche_ladekosten · kapitalrechnung (Nenner + Dauer-Annahme) ·
   ertrag_zerlegung (Fortschritt je ROI-Zeile) …        (DB-frei, rein)
        │
        ▼   api/routes/…                     ← Darstellung
   Cockpit · Aussichten · HA-Export · PDF · Community
```

**Die frühere Aufteilung — „`Monatsdaten` und `InvestitionMonatsdaten` sind die Quellen, jede Read-Site aggregiert daraus selbst" — gilt nicht mehr.** Genau sie war die Fehlerursache: der Berechnungs-Layer war fehlerfrei, aber jede Sicht faltete die Rohdaten anders, und dabei fiel jedes Mal etwas anderes weg (V2H, der Erzeuger hinter dem Zähler, der Aggregat-Fallback, der Monatstarif, der Dienstwagen-Filter). Bei einer Anlage, die nur das Anlagen-Aggregat pflegt, standen für denselben Monat 1.000 kWh und 0 kWh auf zwei Seiten derselben Anwendung.

| Schicht | Darf | Darf nicht |
| --- | --- | --- |
| `services/monats_fakten.py` | laden, filtern, kanonisch auflösen, Layer-Helfer **rufen** | selbst rechnen (das wäre eine Formel-Duplikation) |
| `core/berechnungen/` | rechnen | eine Session sehen |
| `api/routes/…` | darstellen, Zeiträume wählen | `InvestitionMonatsdaten` selbst laden und falten (P10) |

Ausgenommen von P10 sind die **Schreib-, Import- und Checker-Pfade** — sie schreiben oder prüfen die Zeilen, sie leiten nichts ab. Details: `docs/KONZEPT-MONATS-FAKTEN.md`, `docs/ADR-002-WURZELMUSTER.md` (P7 · P8 · P9 · P10), `docs/ADR-001-BERECHNUNGS-LAYER.md`.

> **Migrationsstand:** Die Schicht steht seit S1 mit ihren Einheitstests; die Sichten sind in den Schritten S2–S6 nacheinander umgehängt worden (Reihenfolge und Beweis-Fixture je Schritt in `KONZEPT-MONATS-FAKTEN.md` §5/§10). **Der Bauplan ist mit S6 abgearbeitet — alle sechs Schritte sind gebaut. Seit S5 ist P10 baumweit gewächtert** (`test_wurzelmuster_konformitaet.py::test_p10_*`), nicht mehr nur durch Regressionstests gedeckt. Die danach übrig gebliebene Restschuld ist in vier Nachträgen (C1a–C1d) abgearbeitet und steht seit **C1d (2026-08-04) auf 0** — anlagenweit faltet keine Sicht mehr selbst.
>
> **Umgehängt (S2, 2026-07-31):** `api/routes/aussichten.py` (Finanz-Prognose), `services/pdf/builders/jahresbericht.py` und `api/routes/investitionen/crud.py` (ROI-Dashboard) — Befund **F-5**. Der PDF-Builder lädt `InvestitionMonatsdaten` seither gar nicht mehr selbst.
>
> **Umgehängt (S3, 2026-07-31):** `cockpit/nachhaltigkeit.py` (CO₂-Zeitreihe) und `cockpit/social.py` (geteilter Monatstext) — Befund **F-1**. Beide hatten **keinen einzigen** Zeilen-SoT benutzt und die Eigenverbrauchs-Formel selbst nachgebaut; CO₂ kommt jetzt zusätzlich aus `berechne_co2_bilanz` (ADR-001/DI-2) statt aus drei lokalen Formeln. Damit ist auch die P7-Ausnahme `cockpit/social.py::md` gestrichen. **Nachtrag (Paket B, 2026-07-31):** `cockpit/social.py` ist danach **ganz zurückgebaut** worden — die Oberfläche dazu ist beim IA-V4-Flip entfallen, der Endpoint hatte keinen Konsumenten mehr. Von den beiden S3-Sichten bleibt die CO₂-Zeitreihe. Nicht betroffen ist das **Community-Teilen** (`api/routes/community.py`) — eine andere Funktion. **Nachtrag (Paket B', 2026-07-31):** die CO₂-Zeitreihe hat jetzt auch einen **Konsumenten** — bis dahin war sie die tote Hälfte des Paares (`getNachhaltigkeit` stand im api-Client, aber keine Sicht rief es). Sie hängt im **Cockpit/Jahr** als Block „CO₂-Bilanz" (`v4/JahrCo2Chart.tsx`), nicht unter Auswertungen: sie ist eine **zeitbezogene** Verlaufssicht, während die CO₂-**Amortisation** (`AuswertungenCo2V4.tsx`, `getCO2Amortisation`) die **Lebensdauer**-Frage beantwortet. Der Endpoint bleibt ohne `?jahr=` — das Jahr filtert die Sicht. **Nachtrag (F-6/N-21, 2026-07-31):** die Zeitreihe hat einen **zweiten** Konsumenten bekommen — **Auswertungen → CO₂** (`v4/AuswertungenCo2V4.tsx`) rechnete bis dahin `Erzeugung × 0,38` im Client und stand damit als zweite Zahl neben dem neuen Cockpit-Block; sie liest ihn jetzt über `useAuswertungBasis().co2` (EIN Abruf, geteilt mit der Werte-Tabelle). Dasselbe Spiegelbild im Backend war `services/energie_profil/tage_werte.py` — auch dort jetzt der Kanon, allerdings bewusst nur der **PV-Anteil** (`co2_pv_kg`), weil WP-Wärme und E-Mob-Kilometer auf Tagesebene nicht gemessen werden. Client-Wächter: `npm run check:co2-roh` (Baseline 0).
>
> **Umgehängt (S4, 2026-07-31):** `cockpit/uebersicht.py` und `ha_export.py::calculate_anlage_sensors` — der Schritt **ohne** Inventur-Befund. Beide rechneten richtig und wurden trotzdem umgehängt, weil eine selbst faltende Sicht die nächste Drift-Quelle ist. Der Beweis ist entsprechend negativ (Vier-Wege- und CO₂-Symmetrie unverändert grün, Antworten gegen die Demo-DB wertgleich), plus eine **gemessene** Ladezeit: Cockpit/Übersicht 83 → 60 ms, HA-Export 133 → 115 ms (warm, Median über 10 Läufe) — ein Tarif-Cache statt zwei, §51 als Bulk-Query, vier IMD-Queries weniger. Drei Ränder haben sich dabei doch bewegt, alle drei waren vorher unsichtbar: der Jahres-Filter des Cockpits erfasste `lade_pv_je_monat` nicht, der HA-Export blendete stillgelegte Komponenten rückwirkend aus (`aktiv_jetzt()` als Vorfilter über der Historie) und filterte den Dienstwagen nicht aus der V2H-Bilanz.
>
> **Umgehängt (S5, 2026-07-31):** `investitionen/dashboards.py` — Befunde **F-4** (BKW-Wirtschaftlichkeit: 30-ct-Query-Default und bewerteter *gemessener* Eigenverbrauch → im Normalfall 0 € im Hub) und **F-7** (die Datei enthielt keinen einzigen `ist_dienstlich`-Aufruf). Dazu zwei Funde derselben F-5-Klasse, die vor dem Scharfstellen fallen mussten, weil der Wächter sie sonst gemeldet hätte: die beiden Performance-Ratio-Pfade in `aussichten.py` (**N-1**) und der Prognose-vs-IST-Vergleich in `cockpit/prognose.py` (**N-14**, in der Inventur nicht erhoben). Neue Layer-Formel `bkw_eigenverbrauch_anteil` (`core/berechnungen/bkw_finanz.py`): der Eigenverbrauchs-Anteil **eines** Balkonkraftwerks, anteilig an der Erzeugung hinter dem Zähler — und ausdrücklich *nicht bewertbar*, wo mangels Zählerzeile keine Hausbilanz existiert (P4).
>
> **Umgehängt (S6, 2026-07-31):** `services/community_service.py::prepare_community_data` — die letzte Sicht des Bauplans und der einzige befristete Eintrag in `P10_NOCH_NICHT_MIGRIERT`. Sie verlor **drei** Achsen: die P7-Auflösung der PV (**F-5** — eine Anlage, die ihre Erzeugung als Anlagen-Aggregat pflegt, lieferte eine *leere* Monatsliste, und `/community/share` bricht darauf mit HTTP 400 ab: diese Anlagen konnten am Benchmark gar nicht teilnehmen), V2H und den Erzeuger hinter dem Zähler in der Autarkie (**F-1** — der Server bekam 85,7 %, wo das Cockpit derselben Anlage 90,9 % zeigte) und den **Dienstwagen-Filter** (km, Ladung und V2H eines dienstlichen Fahrzeugs gingen in den öffentlichen Benchmark ein). `ertrag_kwh` bleibt bewusst die PV-Achse **ohne** sonstigen Erzeuger — der Server bildet daraus den spezifischen Ertrag je kWp. **Cross-Repo (Konzept §11):** das Datenmodell von `eedc-community` blieb strukturell unverändert (der Payload validiert unverändert gegen `backend/schemas.py`); geändert hat sich die *Bedeutung* dreier Feldgruppen, die deshalb im selben Paket als Vertrag in den Docstring von `MonatswertInput` gewandert ist.
>
> **Der Wächter ist funktions-granular**, nicht modul-granular: eine ausgenommene Datei ist nicht als Ganzes freigestellt, eine *neue* Funktion darin ist ein Treffer. Seine Ausnahmen stehen in drei getrennten Kategorien, weil zwei davon Schuld sind und nicht Freispruch:
>
> **Umgehängt (C1a, 2026-08-03):** `monatsdaten.py::list_monatsdaten_aggregiert` (**N-15**) — die sichtbarste der Restschuld-Sichten, denn sie speist *Auswertungen → Tabelle* **und** *Cockpit → Jahr*. Zwei Zahlen bewegen sich: die E-Mob-Ladung wird über `summiere_emob_quelle` abgeleitet statt roh addiert (wer nur Gesamt-Ladung und PV-Anteil pflegt, verlor die Netzladung still), und die §51-Menge ist ohne Mitschrift `None` statt 0,0. Der BKW-Akku zählt hier bewusst **weiter** in die anlagenweite Speicher-Summe (**N-28**, Altbestand) — still zu vereinheitlichen hätte die Summe genau bei denen gesenkt, die noch auf dem alten Weg pflegen. Zwei additive Erweiterungen der Schicht waren erzwungen: `MetaFakten.typen_mit_zeile` und `SonstigesFakten.anlage_*_euro`.
>
> **Umgehängt (C1b, 2026-08-03):** `cockpit/komponenten.py::get_komponenten_zeitreihe` (**N-17**) — *Auswertungen → Komponenten*. Der Schritt war als deckungsgleich geplant und ist es auch: sechs der sieben neuen Tests sind **auch gegen die Fassung vor dem Umbau grün**, und die vorhandenen liefen ohne Anpassung durch. Die Route lädt keine `InvestitionMonatsdaten` und keine `Monatsdaten` mehr; §51 kostet statt N Rundreisen nur noch eine, und der Tarif-Stichtag löst je Monat einmal auf (geteilter Cache). **Eine** sichtbare Änderung: ein Monat, dessen einzige Spur ein **Dienstwagen** ist, erzeugt keine Zeile aus lauter Nullen mehr — der alte Loop legte den Monatseintrag an, *bevor* er den Dienstwagen übersprang. Seine **Finanz-Positionen** zählen unverändert weiter und tragen den Monat (#310): er fällt aus dem Energie-Pool, nicht aus der Buchhaltung.
>
> **Umgehängt (C1c, 2026-08-03):** `aktueller_monat.py` — *Cockpit → Monat*. Die einzige Etappe mit einer echten **Abgrenzung**: die Route mischt vier Datenquellen (`saved` · `connector` · `mqtt_energy` · `ha_stats`) nach Präzedenz, die Schicht kennt nur die erste. Umgezogen ist deshalb genau der DB-Zweig — `_collect_saved_data` (der als „Formular füllen" fehlklassifizierte fünfte Eintrag, **N-98**), `_load_vorjahr` (**N-16a**) und die Sonstige-Positionen des Monatsberichts. Die Präzedenz-Regeln, die `> 0`-Gates beim Setzen und die Teilzeitraum-Logik (#361) sind unberührt. Sichtbar sind fünf Zahlen: die PV des Monatsberichts ist **P7-aufgelöst** (F-5 an der Sicht, die S1–S6 nicht angefasst haben), der BKW-Eigenverbrauch fällt ohne Messwert nicht mehr auf die volle Erzeugung zurück (D5-Quirk), und der Vorjahresvergleich verliert die drei als „D6 / IST-Stand erhalten" konservierten Divergenzen: PV ohne P7-Auflösung, Eigenverbrauch/Autarkie ohne V2H, E-Mob als `max()` je Feld statt der kanonischen Trias (#262 — **öffentlich geladener Strom zählte im Vorjahr als Heimladung**, im laufenden Monat nicht).
>
> **Umgehängt (C1d, 2026-08-04):** der **Komponenten-Detailblock** von `get_aktueller_monat` (**N-107**) — die letzte anlagenweite Faltung des Baums. Sie hatte **zwei Fehler**, die die Schicht nicht hat, und beide waren am Datenbestand messbar:
>
> * **E-Auto und Wallbox wurden roh addiert.** Beide messen denselben Fluss aus zwei Perspektiven; wo beide gepflegt sind, stand der Netzanteil doppelt — in der Kachel *Cockpit → Monat*, im **T-Konto** (dort × Arbeitspreis, also geldwirksam) und in der Jahressumme. Am Demo-Bestand über 25 Monate **5.976 statt 3.831 kWh (+56 %)**, betroffen war **jeder** Monat mit Ladung. Die Route hatte die Doppelzählung an anderer Stelle (`typ_aggregation`) längst benannt und vermieden — im Detailblock nicht.
> * **Kein Laufzeit-Filter.** Die Batch nahm jede IMD-Zeile ihres Typs, auch aus Monaten **vor der Anschaffung** (#236-Klasse, die alle anderen Read-Sites seit v3.29 hinter sich haben). Am Demo-Bestand trug die Route vier Monate lang Wärme einer Wärmepumpe, die es noch nicht gab — 3.400 kWh davon im Jahresaggregat 2024, weil `JahrAggregat` die Monate summiert.
>
> Dafür sind der Schicht die vier Größen additiv nachgezogen worden, die ihr fehlten (`SonstigesFakten`: Eigenverbrauch, Einspeisung, Bezug PV, Bezug Netz) — samt `je_geraet`, damit auch die Pro-Gerät-Darstellung nicht mehr selbst faltet. Sie sind **kategorie-bewusst** aufgelöst wie Erzeugung/Verbrauch: ein Erzeuger trägt keinen Netzbezug, ein Verbraucher speist nicht ein. Gemessen wurde der ganze Umbau als Dump gegen den Vorstand: **die einzigen Abweichungen sind die beiden oben** — Speicher, Ø-Ladepreis, BKW, alle sechs Sonstiges-Mengen und die Geräteliste sind bitgleich.
>
> | Kategorie | Bedeutung | Stand nach C1d |
> | --- | --- | --- |
> | `P10_SCHREIBEN_IMPORT_CHECKER` | schreibt, prüft oder reicht durch — leitet nichts ab; auf Dauer legitim | 15 Funktionen |
> | `P10_PER_INVESTITION` | Aggregat **je Gerät**; die Schicht hat dafür keine Sicht (Register **N-2**) | 13 Funktionen |
> | `P10_NOCH_NICHT_MIGRIERT` | faltet eine **anlagenweite** Monatszeile selbst — die Klasse, die P10 schließen soll | **0 — getilgt** |
>
> **Die anlagenweite Restschuld ist getilgt** (5 nach S5 → 4 nach S6 → 3 nach C1a → 2 nach C1b → 1 nach C1c → **0 nach C1d**). `test_p10_offene_schuld_waechst_nicht` deckelt sie nicht mehr, sondern hält die Liste **leer**: ein neuer Eintrag eröffnet die Schuld neu, statt sie unter einer Obergrenze wachsen zu lassen. `get_aktueller_monat` steht seither in `P10_PER_INVESTITION` — selbst geladen wird dort nur noch die Zuordnung `inv → verbrauch_daten` für die Financial-Zeile **je** Investition. **Teilmigriert** bleiben `aussichten.py` und `ha_export.py`: ihre Monatsgrößen kommen aus der Schicht, die per-Investition-Aggregate (WP-Alternativkosten, E-Auto je Fahrzeug, `calculate_investition_sensors`) falten sie weiter selbst.

> **Nachtrag 2026-08-03 (N-121) — die Grundgesamtheit kann jetzt auch die Tagesebene:** Die Schicht kannte einen Monat nur mit DB-Spur (`Monatsdaten` **oder** `InvestitionMonatsdaten`); der Docstring sagte es offen („Monate ohne jede Spur fehlen"). Weil es **keinen automatischen Monatsabschluss** gibt — `scheduler.py::monthly_snapshot_job` setzt nur einen Log-Zeitstempel —, fehlte dem *laufenden* Monat die Spur immer, und dem Vormonat bis zum Abschluss. In *Cockpit → Jahr* stand deshalb eine Kopfzahl über acht Monate über einem Verlauf mit sechs Balken; **N-68 hatte nur die Zählerzeilen-Bedingung aufgehoben**, nicht die Grundgesamtheit. `lade_monats_fakten(..., inkl_nur_tageswerte=True)` (Default **aus**, angefragt allein von der Jahres-Zeitreihe) nimmt solche Monate auf und füllt die Lücken der übrigen **feldgruppen-weise** — Präzedenz wie P7: was in der DB steht, gewinnt. Gefüllt werden nur Zähler, PV/BKW und Speicher-Mengen; die Netzladung bleibt außen vor, weil sie eine **Preis**-Aussage ist. Die Herkunft steht in `MetaFakten.tageswert_gruppen` und geht als `aus_tageswerten` bis in die Antwort — eine Sicht muss nicht aus einer 0 raten (P4). **Es entsteht keine zweite Tag→Monat-Faltung:** gefaltet wird mit dem Layer-Helfer `bilanz_aus_stundenrows` über die Stunden des Monats (Σ ist assoziativ, additive Symmetrie zum Tag bleibt) plus `summe_pv_anlage_kwh`/`summe_bkw_kwh` auf `komponenten_kwh`; `rollup_month` ist **kein** Konkurrent, es faltet fünf andere Felder und schreibt sie. **Null zusätzliche HA-Last** — die Quelle liegt lokal, was die mit L-1 gewonnene Entlastung unangetastet lässt. Vor dem Bau gemessen (Anlage 1, v4.0.8): Δ ≤ 0,8 kWh über sechs Vergleichsmonate, Juli/August deckungsgleich mit der HA-Statistics-Kaskade der Kachel. Lesepfad und Grenzen: `services/energie_profil/monats_aus_tagen.py`, Konzept-Nachtrag in [KONZEPT-MONATS-FAKTEN §4](KONZEPT-MONATS-FAKTEN.md).

> **Nachtrag 2026-07-31 (Nebenfunde-Runde, Paket A):** Die **dienstlichen Ladekosten** stehen nicht mehr auf dieser Liste. Sie waren der letzte Posten, den `aussichten.py` je Investition selbst faltete — und er driftete gleich zweifach: der Netzanteil lief dort über den allgemeinen Arbeitspreis statt über den Wallbox-Tarif (**N-12**), und der HA-Export zog ihn **gar nicht** ab (**N-13**). Beide Sichten beziehen die Mengen jetzt aus `MonatsFakt.emob.dienstlich_*` und bewerten sie über die neue Layer-Formel `berechne_dienstliche_ladekosten` (`core/berechnungen/dienstliche_ladekosten.py`, ADR-001). Dabei ist eine dritte, größere Sache mitgefallen — **N-18**: der PV-Anteil wurde zur Einspeisevergütung abgezogen, während die EV-Ersparnis dieselben kWh zum Netzbezugspreis gutschrieb, sodass ein Dienstwagen der Anlage netto **+22 ct je verschenkter kWh** einbrachte. Der Abzug bewertet den PV-Anteil seither mit dem Netzbezugspreis; die **Energiebilanz** (Eigenverbrauch, Quote, Autarkie) bleibt unverändert, korrigiert wurde ausschließlich die Bewertung. Herleitung: [BERECHNUNGEN §3.10](BERECHNUNGEN.md).

### Wetter-Service (Multi-Provider)

**Dateien:**
- `backend/services/wetter_service.py` – Multi-Provider Orchestrierung
- `backend/services/brightsky_service.py` – DWD-Daten via Bright Sky API
- `backend/services/solar_forecast_service.py` – Open-Meteo Solar mit GTI

**Funktion:** Wetterdaten für Globalstrahlung und Sonnenstunden aus verschiedenen Quellen.

**Verfügbare Provider:**

| Provider | Region | Beschreibung |
|----------|--------|--------------|
| **auto** (Standard) | - | Automatische Auswahl basierend auf Standort |
| **brightsky** | Deutschland | DWD-Daten via Bright Sky REST API (höchste Qualität) |
| **open-meteo** | Weltweit | Open-Meteo Archive API |
| **open-meteo-solar** | Weltweit | Open-Meteo Solar mit GTI für geneigte Module |

**Fallback-Kette:**
1. Gewählter Provider
2. Alternative (z.B. Open-Meteo wenn Bright Sky fehlschlägt)
3. PVGIS TMY (langjährige Durchschnittswerte)
4. Statische Defaults (Mitteleuropa-Durchschnitt)

**API-Endpoints:**
```
GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}?provider=auto
GET /api/wetter/monat/koordinaten/{lat}/{lon}/{jahr}/{monat}  # Direkt per Koordinaten
GET /api/wetter/provider/{anlage_id}                          # Verfügbare Provider
GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}          # Provider-Vergleich
GET /api/solar-prognose/{anlage_id}?tage=7                    # GTI-basierte PV-Prognose
```

**GTI (Global Tilted Irradiance):**
Open-Meteo Solar berechnet Strahlung für geneigte PV-Module:
- Neigung und Ausrichtung aus PV-Modul-Konfiguration
- Temperaturkorrektur (Wirkungsgradminderung bei Hitze)
- Multi-String-Unterstützung für verschiedene Ausrichtungen

### Sensor-Export Service

**Datei:** `backend/services/ha_sensors_export.py`

**Funktion:** Definition und Berechnung aller exportierbaren KPIs.

**Sensor-Kategorien:**
- `ANLAGE_SENSOREN` – PV-Gesamt
- `INVESTITION_SENSOREN` – ROI, Amortisation
- `E_AUTO_SENSOREN` – Mobilität
- `WAERMEPUMPE_SENSOREN` – Wärme
- `SPEICHER_SENSOREN` – Batterie

**Sensor-Definition:**
```python
SensorDefinition(
    key="pv_erzeugung_kwh",
    name="PV Erzeugung",
    unit="kWh",
    icon="mdi:solar-power",
    device_class="energy",
    state_class="total_increasing",
    formel="Σ(PV-Module.pv_erzeugung_kwh)"
)
```

### MQTT Client

**Datei:** `backend/services/mqtt_client.py`

**Funktion:** Publizieren von Sensoren via MQTT Auto-Discovery.

**Erweiterte Methoden:**
- `publish_number_discovery()` - Erstellt Number-Entities für Monatsstarts
- `publish_calculated_sensor()` - Erstellt Sensoren mit value_template
- `update_month_start_value()` - Aktualisiert retained Startwerte
- `publish_monatsdaten()` - Publiziert finale Monatswerte

**Topics:**
```
homeassistant/sensor/eedc_{anlage_id}_{key}/config  → Discovery
eedc/{anlage_id}/{key}                              → State
eedc/{anlage_id}/{key}/attributes                   → Attributes
```

### HA Statistics Service

**Datei:** `backend/services/ha_statistics_service.py`

**Funktion:** Zugriff auf die Home-Assistant-Langzeitstatistik.

**Drei Transporte, eine Quelle** (Reihenfolge = Vorrang):

| # | Transport | Voraussetzung |
| --- | --- | --- |
| 1 | `HA_RECORDER_DB_URL` (SQL) | externer Recorder, MariaDB/MySQL |
| 2 | Recorder-Datei (SQL) | Volume-Mapping `config:ro` auf `/config/home-assistant_v2.db` |
| 3 | **WebSocket** `recorder/statistics_during_period` | nur die HA-Verbindung (Supervisor oder Long-Lived-Token) |

Die SQL-Wege behalten den Vorrang, wo sie verfügbar sind — synchron, kein Netz,
gebündeltes Lesen. Fehlt beides, liefert der WebSocket-Weg **dieselbe** Quelle:
`sum` · `state` · `mean` · `min` · `max` aus derselben Recorder-Statistik.
Aggregator, Rücksetzer-Behandlung und Slot-Konvention bleiben unberührt; der
Unterschied liegt allein in der Zeilen-Beschaffung
(`backend/services/ha_statistics_ws.py`).

Gemessen 2026-08-05 gegen eine produktive Anlage, beide Wege parallel: 27
Monatswerte und 26 Monatsanfangswerte **bitgleich**, verfügbare Monate
identisch bis auf den Tag.

⚠ **Warum der dritte Weg gebraucht wird:** Wer eedc als eigenen Container neben
HA betreibt, hat weder `/config` noch `HA_RECORDER_DB_URL` — Tageswerte
entstanden dort ausschließlich aus eedcs eigenen 5-Minuten-Snapshots, also ab
Installation **vorwärts**. `config:ro` hilft dort auch nicht generell: es setzt
denselben Host **und** eine laufende HA voraus (eine WAL-Datenbank braucht auch
als Leser eine schreibbare `-shm`) und trägt bei MariaDB-Recorder gar nicht.

⚠ **Die Grenze, die auch der dritte Weg nicht verschiebt:** die LTS reicht nur
so weit zurück, wie der Sensor in HA existiert. Für alles davor ist der
Datei-Import die Antwort.

**Weitere Voraussetzung:** Sensor-Mapping konfiguriert.

**Hauptfunktionen:**
- `get_monatswerte()` - Einzelner Monat aus HA-Statistik
- `get_alle_monatswerte()` - Bulk-Abfrage aller historischen Monate
- `get_verfuegbare_monate()` - Liste aller Monate mit Daten
- `get_monatsanfang_wert()` - Zählerstand am Monatsanfang für MQTT-Startwerte

**API-Endpoints:**
```
GET  /api/ha-statistics/status                                     # Prüft DB-Verfügbarkeit
GET  /api/ha-statistics/monatswerte/{anlage_id}/{jahr}/{monat}     # Einzelner Monat
GET  /api/ha-statistics/verfuegbare-monate/{anlage_id}             # Alle Monate mit Daten
GET  /api/ha-statistics/alle-monatswerte/{anlage_id}               # Bulk-Abfrage
GET  /api/ha-statistics/monatsanfang/{anlage_id}/{jahr}/{monat}    # Zählerstand am Monatsanfang
GET  /api/ha-statistics/import-vorschau/{anlage_id}                # Vorschau mit Konflikten
POST /api/ha-statistics/import/{anlage_id}                         # Import mit Überschreib-Schutz
```

### VorschlagService

**Datei:** `backend/services/vorschlag_service.py`

**Funktion:** Intelligente Vorschläge für Monatsabschluss-Wizard.

**Vorschlags-Hierarchie:**
1. **Vormonat** (Konfidenz 80%) - Bester Indikator für kontinuierliche Werte
2. **Vorjahr** (Konfidenz 70%) - Gleicher Monat, saisonale Korrelation
3. **Berechnung** (Konfidenz 60%) - COP/EV-Quote basiert
4. **Durchschnitt** (Konfidenz 50%) - Fallback aus allen vorhandenen Werten

### Scheduler Service

**Datei:** `backend/services/scheduler.py`

**Funktion:** APScheduler-basierte Cron-Jobs für automatische Aufgaben.

**Jobs** (vollständig aus `scheduler.py` erhoben, 2026-08-07 — die Job-`id` ist der Name, unter dem
`GET /api/scheduler` sie ausweist):

| Job-ID | Takt | Aufgabe |
| --- | --- | --- |
| `sensor_snapshot` | stündlich :05 | Zählerstände je Sensor in `sensor_snapshots` — **die kWh-Quelle** der Stunden-/Tageswerte |
| `sensor_snapshot_preview` | stündlich :55 | Vorschau-Snapshot kurz vor dem Stundenwechsel |
| `sensor_snapshot_5min` | alle 5 min (:30 s) | 5-Minuten-Snapshots für den Live-Tagesverlauf |
| `sensor_snapshot_5min_cleanup` | täglich 00:30 | 5-Minuten-Daten aufräumen |
| `energie_profil_heute` | alle 15 min | den **laufenden** Tag fortschreiben |
| `energie_profil_aggregation` | täglich 00:15 | Vortag aggregieren → `TagesEnergieProfil` + `TagesZusammenfassung` |
| `energie_profil_aggregation_recovery` | täglich 02:15 | zweiter Anlauf für Tage, die 00:15 verpasst hat (Neustart, Ausfall) |
| `korrekturprofil_aggregation` | täglich 02:30 | gelernte eedc-Prognose-Korrektur neu bilden |
| `prognose_prefetch` | alle 45 min | Wetter-/Prognosedaten vorhalten |
| `connector_daily_poll` | täglich 03:30 | Geräte-Connectors im lokalen Netz abfragen |
| `api_cache_cleanup` | täglich 04:00 | `api_cache` aufräumen |
| `kraftstoffpreis` | Di 06:00 | EU Weekly Oil Bulletin → `TagesZusammenfassung.kraftstoffpreis_euro` + `Monatsdaten.kraftstoffpreis_euro` |
| `monthly_snapshot` | 1. des Monats 00:01 | ⚠ setzt **nur einen Log-Zeitstempel** — es gibt **keinen automatischen Monatsabschluss** |
| `mqtt_auto_publish` | Intervall (konfigurierbar) | HA-Export per MQTT, mit Start-Publish beim Hochlauf |
| `mqtt_energy_snapshot` · `mqtt_live_snapshot` | je alle 5 min | MQTT-Inbound: Energie-Zählerstände bzw. Live-Werte sichern |
| `mqtt_energy_cleanup` · `mqtt_live_cleanup` | täglich 03:00 / 03:05 | MQTT-Snapshots älter als die Aufbewahrung löschen |

⚠ **Dass `monthly_snapshot` nichts abschließt, hat Folgen für jede Monats-Auswertung:** eine
`Monatsdaten`-Zeile entsteht erst, wenn der Nutzer den Abschluss macht. Dem laufenden Monat fehlt sie
immer, dem Vormonat bis zum Abschluss — Sichten müssen einen gelaufenen Monat also auch **ohne**
Zählerzeile kennen (`meta.hat_zaehlerzeile`, Flag `inkl_ohne_zaehlerzeile`).

### Kraftstoffpreis Service (v3.16.16)

**Datei:** `backend/services/kraftstoff_preis_service.py`

**Funktion:** Wöchentliche nationale Benzindurchschnittspreise aus dem EU Weekly Oil Bulletin.

**Datenquelle:** EU-Kommission XLSX (stabile URL, History seit 2005, Euro-Super 95 inkl. Steuern).

**Hauptfunktionen:**
- `get_kraftstoffpreise(land)` — Gibt Preisliste für ein Land zurück (24h Cache)
- `get_monatsdurchschnitt(anlage_id, jahr, monat, db)` — Ø aus TagesZusammenfassung
- `backfill_kraftstoffpreise(anlage_id, land, db)` — Befüllt TagesZusammenfassung
- `backfill_monatsdaten_kraftstoffpreise(anlage_id, land, db)` — Befüllt Monatsdaten

### HA MQTT Sync Service

**Datei:** `backend/services/ha_mqtt_sync.py`

**Funktion:** Koordiniert MQTT-Sensoren basierend auf Sensor-Mapping.

**Hauptfunktionen:**
- `setup_sensors_for_anlage()` - Erstellt alle MQTT Entities
- `trigger_month_rollover()` - Führt Monatswechsel durch

### Live Power Service (v3.0.0, refactored v3.9.0)

**Dateien:** 7 Module in `backend/services/`

| Modul | Verantwortlichkeit |
|---|---|
| `live_power_service.py` (313 Z.) | Orchestrierung: ruft die anderen Module auf |
| `live_sensor_config.py` | Konstanten, `extract_live_config()`, `normalize_to_w()` |
| `live_kwh_cache.py` | TTL-Caches für heute/gestern/profil kWh-Werte |
| `live_history_service.py` | HA-History-Abruf, Trapez-Integration, Tages-kWh |
| `live_verbrauchsprofil_service.py` | Verbrauchsprofil aus HA-History oder MQTT |
| `live_tagesverlauf_service.py` | Butterfly-Chart Datenaufbereitung |
| `live_komponenten_builder.py` | Komponenten, Gauges, Summenbildung |

**Datenquellen (Priorität):**
1. HA-Sensoren (via Sensor-Mapping) — direkte REST-API-Abfrage
2. MQTT-Inbound Cache — In-Memory-Werte von subscribten Topics

**Berechnung:**
- Jede Investition wird als `LiveKomponente` mit `erzeugung_kw` / `verbrauch_kw` geliefert
- Haushalt = Residual: `max(0, Σ Quellen - Σ Senken)` (keine eigene Messung nötig)
- SoC-Gauges für Speicher und E-Auto (Key: `soc_{invId}`)
- Tages-kWh: HA-Statistiken → MQTT-Snapshots → leer (Fallback-Kette)

**API-Router** (3 Dateien in `backend/api/routes/`):

| Router | Endpoints |
|---|---|
| `live_dashboard.py` (356 Z.) | `GET /api/live/{id}`, `GET /api/live/{id}/tagesverlauf` |
| `live_mqtt_inbound.py` | `GET/POST/DELETE /api/live/mqtt/*` |
| `live_wetter.py` | `GET /api/live/{id}/wetter` + Helfer |

### MQTT Inbound Service (NEU v3.0.0)

**Datei:** `backend/services/mqtt_inbound_service.py`

**Funktion:** Subscribt EEDC-definierte MQTT-Topics und cached Werte im Speicher.

**Topic-Struktur:**
```
eedc/{anlage_id}/live/{key}    → Echtzeit-Leistung (kW)
eedc/{anlage_id}/energy/{key}  → Zählerstände (kWh, monoton steigend)
```

**Hauptfunktionen:**
- `MqttInboundCache` — Thread-safe In-Memory-Cache für Live- und Energy-Werte
- `get_all_energy_raw()` — Aktuelle Zählerstände für Snapshot-Service

### MQTT Energy History Service (NEU v3.0.0)

**Datei:** `backend/services/mqtt_energy_history_service.py`

**Funktion:** SQLite-basierte Mini-History für Tageswerte aus MQTT Energy-Daten.

**Mechanismus:**
- Tabelle `mqtt_energy_snapshots` speichert Zählerstand-Snapshots alle 5 Minuten
- Tageswert = Differenz zwischen aktuellem Stand und Mitternacht-Snapshot
- Retention: 31 Tage, automatischer Cleanup um 03:00

### Energieprofil Service (NEU v3.1.0)

**Dateien:**

- `backend/services/energie_profil_service.py` — Aggregationslogik
- `backend/models/tages_energie_profil.py` — Datenmodelle

**Funktion:** Langfristige Persistierung stündlicher Energiedaten. HA-History hat nur ~10 Tage Retention — dieser Service sichert die Daten dauerhaft in SQLite.

**Datenmodelle:**

| Tabelle | Granularität | Inhalt |
| --- | --- | --- |
| `TagesEnergieProfil` | 24 Zeilen/Tag/Anlage | Stündliche kW-Werte: PV, Verbrauch, Einspeisung, Netzbezug, Batterie, Überschuss, Defizit + Wetter (Temperatur, Globalstrahlung) + SoC + Komponenten-JSON |
| `TagesZusammenfassung` | 1 Zeile/Tag/Anlage | Tagessummen (Überschuss/Defizit kWh), Peaks (PV, Netzbezug, Einspeisung kW), Batterie-Vollzyklen, Wetter-Min/Max, Performance Ratio, Datenqualität (stunden_verfuegbar) |

**Datenfluss-Pipeline:**

```
                           Scheduler (00:15 täglich)
                                    │
                    ┌───────────────┼──────────────────┐
                    ▼               ▼                  ▼
            HA Sensor History   MQTT Snapshots    Open-Meteo Archive
            (via get_tagesverlauf)                (Wetter-IST)
                    │               │                  │
                    └───────┬───────┘                  │
                            ▼                          │
                   aggregate_day()  ◄──────────────────┘
                     │          │
                     ▼          ▼
         TagesEnergieProfil   TagesZusammenfassung
         (24 Stunden-Zeilen)  (1 Tages-Zeile)
                                │
                                ▼  (beim Monatsabschluss)
                         rollup_month()
                                │
                                ▼
                     Monatsdaten-Felder aktualisiert
                     (ueberschuss_kwh, defizit_kwh,
                      batterie_vollzyklen, performance_ratio,
                      peak_netzbezug_kw)
```

**Hauptfunktionen:**

| Funktion | Trigger | Beschreibung |
| --- | --- | --- |
| `aggregate_day()` | Scheduler / Monatsabschluss | Holt Tagesverlauf + Wetter + SoC, berechnet 24 Stundenprofile + Tageszusammenfassung |
| `aggregate_yesterday_all()` | Scheduler 00:15 | Ruft `aggregate_day()` für alle Anlagen mit Sensor-Mapping auf |
| `rollup_month()` | Monatsabschluss | Aggregiert `TagesZusammenfassung` → `Monatsdaten`-Felder (Summe/Durchschnitt/Max) |
| `backfill_range()` | Monatsabschluss | Nachberechnung eines Datumsbereichs (limitiert durch HA-History ~10 Tage) |

**Berechnungsdetails:**

- **Überschuss/Defizit:** Pro Stunde `max(0, PV - Verbrauch)` bzw. umgekehrt, Summe = kWh (kW × 1h)
- **Batterie-Vollzyklen:** `Σ |ΔSoC| / 200` (ein Vollzyklus = 0→100→0 = 200% ΔSoC)
- **Performance Ratio:** `PV_Ertrag_kWh / (Strahlung_Wh/m² × kWp / 1000)`
- **Wetter:** Open-Meteo Historical API (Archiv) oder Forecast API (heute)
- **SoC:** Aus HA Sensor History (Stundenmittel)

**Integration mit Monatsabschluss:**

Beim Monatsabschluss werden zwei Schritte ausgeführt:
1. `backfill_range()` — Fehlende Tage nachberechnen (soweit HA-History reicht)
2. `rollup_month()` — Tagesdaten in Monatsdaten verdichten

---

## 8. Design-Entscheidungen

### Warum Standalone-First?

**Problem:** Komplexe HA-Integration erwies sich als problematisch:
- EVCC liefert andere Datenstrukturen als erwartet
- Utility Meter können nicht programmatisch zugeordnet werden
- Jede Haus-Automatisierung ist anders

**Lösung:** EEDC ist primär Standalone:
- Datenerfassung: CSV-Import oder manuelles Formular
- Wetter-Daten: Open-Meteo/PVGIS (HA-unabhängig)
- HA-Export: Optional, nur für berechnete KPIs

### Warum InvestitionMonatsdaten statt Monatsdaten?

**Problem:** Ursprünglich wurden Speicher-Daten in `Monatsdaten` gespeichert.

**Probleme:**
- Nicht skalierbar für mehrere Speicher
- Inkonsistent mit anderen Komponenten
- Schwer erweiterbar

**Lösung:** Alle Komponenten-Details in `InvestitionMonatsdaten`:
- `Monatsdaten` = Nur Zählerwerte (Einspeisung, Netzbezug)
- `InvestitionMonatsdaten` = Alle Komponenten-Details

**Was diese Trennung NICHT bedeutet** (Lehre aus der Drift-Inventur 2026-07-31): dass jede Read-Site sich ihre Monatszeile selbst aus beiden Tabellen zusammenfaltet. Genau das war jahrelang der Fall und genau daraus entstanden sechs Befunde mit derselben Ursache. Die Auflösung — welcher Wert gilt, welche Lücke wird gefüllt, welche Investition zählt im Monat überhaupt — liegt seit ADR-002/P10 in `services/monats_fakten.py` (§7 „Lese-Schichtung").

### Warum Parent-Child für PV-Module?

**Grund:** PV-System ROI-Berechnung:
- Wechselrichter-Kosten müssen auf PV-System verteilt werden
- Einzelne Module haben keine eigene Amortisation
- Aggregation ermöglicht realistische ROI-Aussagen

### Warum JSON für Parameter?

**Grund:** Flexibilität bei typ-spezifischen Feldern:
- Speicher braucht `kapazitaet_kwh`, E-Auto braucht `v2h_faehig`
- Schema-Evolution ohne DB-Migrationen
- SQLite unterstützt JSON-Queries

**Achtung:** SQLAlchemy erkennt JSON-Änderungen nicht automatisch!
```python
from sqlalchemy.orm.attributes import flag_modified
investition.parameter["key"] = "value"
flag_modified(investition, "parameter")
db.commit()
```

### Warum 0-Werte explizit prüfen?

**Problem:** Python wertet `0` als `False`:
```python
if val:  # Falsch! 0 wird als False gewertet
if val is not None:  # Richtig!
```

**Konsequenz:** Überall `is not None` statt `if val`.

### ROI-Metriken (Wichtig: Unterschiedliche Bedeutungen!)

| Metrik | Wo | Formel | Bedeutung |
|--------|-----|--------|-----------|
| **Jahres-Rendite** | Cockpit, Auswertung/Investitionen | `Jahres-Ertrag / Investition × 100` | Rendite pro Jahr (p.a.) |
| **Amortisations-Fortschritt** | Aussichten/Finanzen | `Kum. Erträge / Investition × 100` | Wie viel % bereits abbezahlt |

**Mehrkosten-Ansatz für Investitionen:**
Bei der ROI-Berechnung werden **Mehrkosten** gegenüber Alternativen berücksichtigt:
- **PV-System**: Volle Kosten (keine Alternative)
- **Wärmepumpe**: Kosten minus Gasheizung (`alternativ_kosten_euro` Parameter)
- **E-Auto**: Kosten minus Verbrenner (`alternativ_kosten_euro` Parameter)

### Community-Integration

```
EEDC Add-on                              Community Server
┌──────────────────────┐                 ┌──────────────────┐
│ v4/CommunityShare-   │ ── POST ──────→ │ /api/submit      │
│   Block.tsx          │ ── DELETE ────→ │ /api/submit/{h}  │
│ v4/CommunityV4.tsx   │ ── Proxy ─────→ │ /api/benchmark/  │
│   (+ 6 Unter-Sichten)│                 │   anlage/{hash}  │
│ "Im Browser öffnen"  │ ── Link ──────→ │ /?anlage=HASH    │
└──────────────────────┘                 └──────────────────┘
```

**Relevante Dateien:**

- `backend/services/community_service.py` – Datenaufbereitung + Anonymisierung; die Monatswerte
  kommen aus den **Monats-Fakten** (ADR-002/P10), nicht aus eigener Faltung
- `backend/services/plz_to_state.py` – PLZ→Bundesland (8.308 Einträge, O(1))
- `backend/api/routes/community.py` – Routen + Benchmark-**Proxy**; der Client spricht den
  Community-Server nie direkt an
- `frontend/src/v4/CommunityShareBlock.tsx` – teilen und rückwirkend entfernen
- `frontend/src/v4/CommunityV4.tsx` – Benchmark-Sicht mit sechs Unter-Sichten
  (`CommunityUebersichtV4` · `PVErtragV4` · `KomponentenV4` · `RegionalV4` · `TrendsV4` ·
  `StatistikenV4`)
- `frontend/src/api/community.ts` – API-Client

⚠ **Der Community-Server rechnet nichts nach** — er hat die Rohdaten nie gesehen. Was ein Feld
bedeutet, steht als Vertrag im Docstring von `MonatswertInput` **im Community-Repo**; wer die
Bedeutung ändert, ändert sie dort mit. Altbestand heilt beim nächsten Voll-Submit.

### Cloud-Import-Provider (v2.7.0+)

**Verzeichnis:** `backend/services/cloud_import/`

**Architektur:** ABC-Pattern mit `@register_provider` Decorator und Provider-Registry.

**Verfügbare Provider (12, SoT ist `services/cloud_import/registry.py`):**

| Provider | Status |
|----------|--------|
| Anker SOLIX | ✅ an einem echten Konto bestätigt |
| Victron VRM | ✅ an einem echten Konto bestätigt |
| Deye / Solarman · EcoFlow PowerOcean · EcoFlow PowerStream · Fronius Solar.web · Growatt · Hoymiles S-Miles · Huawei FusionSolar · SolarEdge · Sungrow iSolarCloud · Viessmann GridBox | ⚠ `getestet=False` |

**`getestet` ist eine Aussage über die Wirklichkeit, kein Ausdruck von Zuversicht.** Das Flag geht
erst auf `True`, wenn ein Nutzer mit einem echten Konto Einrichtung **und** Zeitraum-Import
gemeldet hat — rot verifizierte Tests genügen nicht: eine Fixture ist eine **Behauptung** über eine
fremde API. Genau daran ist der Solarman-Import zweimal gescheitert (die Fixture erfand eine
`body`-Hülle, die es nicht gibt).

**Output:** Alle Provider liefern `ParsedMonthData` als einheitliches Format.

### Custom-Import (v2.8.0)

**Verzeichnis:** `backend/api/routes/custom_import/`

**Funktion:** Beliebige CSV/JSON-Dateien mit benutzerdefinierbarem Feld-Mapping importieren.

**Features:**
- Automatische CSV-Dialekt-Erkennung (Trennzeichen, Dezimalformat)
- Auto-Mapping anhand von Spaltenbezeichnungen (deutsch + englisch)
- Einheiten-Umrechnung (Wh/kWh/MWh)
- Mapping-Templates in Settings-Tabelle speicherbar
- 4-Schritt-Wizard: Upload → Mapping → Vorschau → Import

**API-Endpoints:**
```
POST   /api/custom-import/analyze          # Datei analysieren, Spalten erkennen
POST   /api/custom-import/preview          # Mapping anwenden, Vorschau
GET    /api/custom-import/templates        # Gespeicherte Templates laden
POST   /api/custom-import/templates/{name} # Template speichern
DELETE /api/custom-import/templates/{name} # Template löschen
GET    /api/custom-import/fields           # Verfügbare EEDC-Zielfelder
```

---

## 9. Entwickler-Workflow

> **SoT für Einrichtung, Befehle und Gates ist [DEVELOPMENT.md](DEVELOPMENT.md)**, für den Release
> [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md). Hier stand bis 2026-08-07 eine Kopie beider — mit
> vier statt fünf Versionsdateien und dem Satz „Frontend Tests (noch nicht implementiert)", während
> längst eine Vitest-Suite und die `check:*`-Wächter liefen. **Kopierte Befehle veralten
> unbemerkt**; deshalb bleibt hier nur, was architektonisch ist.

### Der Fluss zwischen den Repositories

```text
eedc-homeassistant (Source of Truth)
├── eedc/backend/          ─── scripts/release.sh ───→  eedc (Standalone-Spiegel)
├── eedc/frontend/         ─── scripts/release.sh ───→  eedc (Standalone-Spiegel)
├── docs/                  ── website/scripts/sync-docs.sh ─→ website/ (GitHub Pages)
│                          └── scripts/sync-help.sh ──→  In-App-Hilfe (versioniert!)
└── CHANGELOG.md           ─── release.sh ────────────→  eedc/CHANGELOG.md
                                                         (die Datei, die HA-Nutzer im Store lesen)

eedc-community (unabhängig — bei Datenmodell-Änderungen synchron anpassen)
```

**Regeln, die daraus folgen:**

- Alle Änderungen in `eedc-homeassistant`, **nie** direkt im `eedc`-Spiegel.
- Immer auf `main` (Einzelentwickler-Projekt, keine Feature-Branches), kein `git subtree`.
- Nur explizite Pfade committen — es laufen parallele Sessions im selben Arbeitsbaum.
- **Zwei Kopien hängen an `docs/`**: die Website-Kopie ist gitignored, die **In-App-Hilfe-Kopie
  ist versioniert** und gehört in denselben Commit (`scripts/sync-help.sh`).

### Was ein Release technisch bedeutet

`release.sh` bumpt **fünf** Versionsdateien (Backend, Frontend, `config.yaml`, `run.sh`,
`Dockerfile`), kopiert den CHANGELOG, committet, taggt und pusht **beide** Repos. Danach laufen
drei Workflows: `tests.yml`, `release.yml` (baut die Add-on-Images) und `deploy-website.yml`.

⚠ **Das Add-on zieht ein vorgebautes Image** (`eedc/config.yaml` →
`ghcr.io/supernova1963/eedc-homeassistant-{arch}`). Zwischen Tag und fertigem Image ist die Version
im Store sichtbar, aber nicht installierbar (`[404] manifest unknown`). Der Prüf-Einzeiler samt
seiner beiden Pflicht-Header steht in [DEVELOPMENT.md §Versionierung](DEVELOPMENT.md#versionierung).

### Community-Datenfluss

```text
eedc Add-on                                   Community Server
┌───────────────────────────────┐             ┌────────────────────────┐
│ v4/CommunityShareBlock.tsx    │ ─ POST ───→ │ /api/submit            │
│   (teilen / rückwirkend weg)  │ ─ DELETE ─→ │ /api/submit/{hash}     │
│ v4/CommunityV4.tsx            │ ─ Proxy ──→ │ /api/benchmark/        │
│                               │             │   anlage/{hash}        │
└───────────────────────────────┘             └────────────────────────┘
```

Der Client spricht den Community-Server **nie direkt** an — alles läuft über
`api/routes/community.py` (Proxy + Aufbereitung). **Der Server rechnet nichts nach**: er hat die
Rohdaten nie gesehen, und was ein Feld bedeutet, steht als Vertrag im Docstring von
`MonatswertInput` (Community-Repo). Wer die Bedeutung ändert, ändert sie dort mit.

---

## Anhang: API-Referenz

Vollständige API-Dokumentation nach dem Start des Backends:

- Swagger UI: `http://localhost:8099/api/docs`
- ReDoc: `http://localhost:8099/api/redoc`
- OpenAPI JSON: `http://localhost:8099/api/openapi.json`

Die Prefix-Übersicht je Modul steht in
[DEVELOPMENT.md §API-Routen Übersicht](DEVELOPMENT.md#api-routen-übersicht) — erhoben aus
`backend/main.py`, das der SoT der Prefixe ist.
