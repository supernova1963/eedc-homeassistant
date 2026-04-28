# EEDC Berechnungsreferenz

**Version 3.16.1** | Stand: April 2026

Dieses Dokument beschreibt alle Berechnungsketten im EEDC-System: von den Eingabefeldern
über die Berechnungslogik bis zur Anzeige im Frontend. Es dient als Referenz zur Fehlersuche
und zum Verständnis der Datenflüsse.

---

## Inhaltsverzeichnis

1. [Datenmodell (3 Schichten)](#1-datenmodell-3-schichten)
2. [Konstanten](#2-konstanten)
3. [Berechnungsketten nach Thema](#3-berechnungsketten-nach-thema)
   - [3.1 Energie-Bilanz (Monatskennzahlen)](#31-energie-bilanz-monatskennzahlen)
   - [3.2 Finanzen (Cockpit)](#32-finanzen-cockpit)
   - [3.3 Speicher-Einsparung](#33-speicher-einsparung)
   - [3.4 E-Auto-Einsparung](#34-e-auto-einsparung)
   - [3.5 Wärmepumpe-Einsparung](#35-wärmepumpe-einsparung)
   - [3.6 ROI & Amortisation](#36-roi--amortisation)
   - [3.7 USt auf Eigenverbrauch](#37-ust-auf-eigenverbrauch)
   - [3.8 CO2-Bilanz](#38-co2-bilanz)
   - [3.9 PV-String SOLL-IST Vergleich](#39-pv-string-soll-ist-vergleich)
   - [3.10 Sonstige Positionen](#310-sonstige-positionen)
4. [Prognosen (Aussichten)](#4-prognosen-aussichten)
   - [4.1 Kurzfrist-Prognose (7-16 Tage)](#41-kurzfrist-prognose-7-16-tage)
   - [4.1b Solar Forecast ML (SFML)](#41b-solar-forecast-ml-sfml)
   - [4.2 Langfrist-Prognose (12 Monate)](#42-langfrist-prognose-12-monate)
   - [4.3 Trend-Analyse & Degradation](#43-trend-analyse--degradation)
   - [4.4 Finanz-Prognose & Amortisation](#44-finanz-prognose--amortisation)
5. [Tarif-System (Spezialtarife)](#5-tarif-system-spezialtarife)
6. [Investitionstyp-spezifische Berechnungen (ROI-Dashboard)](#6-investitionstyp-spezifische-berechnungen-roi-dashboard)
6b. [Energieprofil-Berechnungen (Tages-Aggregation)](#6b-energieprofil-berechnungen-tages-aggregation)
7. [Debugging-Leitfaden](#7-debugging-leitfaden)

---

## 1. Datenmodell (3 Schichten)

### Schicht 1: Rohdaten (Eingabe)

| Tabelle | Felder | Quelle | Beschreibung |
|---------|--------|--------|-------------|
| `Monatsdaten` | `einspeisung_kwh`, `netzbezug_kwh` | Zählerwerte (manuell/HA) | Anlagen-Energiebilanz |
| `InvestitionMonatsdaten` | `verbrauch_daten` (JSON) | Manuell/Wizard/HA | Pro Komponente: PV-Erzeugung, Speicher, WP, E-Auto, etc. |
| `Strompreis` | `netzbezug_arbeitspreis_cent_kwh`, `einspeiseverguetung_cent_kwh`, `grundpreis_euro_monat`, `verwendung` | Manuell | Tarife mit Gültigkeitszeitraum |
| `Investition` | `anschaffungskosten_gesamt`, `parameter` (JSON) | Manuell | Kosten, technische Parameter |
| `Anlage` | `leistung_kwp`, `steuerliche_behandlung`, `ust_satz_prozent` | Manuell | Anlage-Stammdaten |
| `PVGISPrognose` | `monatswerte`, `module_monatswerte`, `jahresertrag_kwh` | PVGIS API | SOLL-Werte pro Monat/Modul |
| `TagesEnergieProfil` | `pv_kw`, `verbrauch_kw`, `einspeisung_kw`, `netzbezug_kw`, `batterie_kw`, `soc_prozent`, `komponenten` (JSON) | Scheduler/Monatsabschluss | 24 Zeilen/Tag, stündliche kW-Werte + Wetter |
| `TagesZusammenfassung` | `ueberschuss_kwh`, `defizit_kwh`, `peak_pv_kw`, `batterie_vollzyklen`, `performance_ratio` | Aggregiert aus TagesEnergieProfil | 1 Zeile/Tag, Tagessummen + KPIs |

**Legacy-Felder (NICHT verwenden):**
- `Monatsdaten.pv_erzeugung_kwh` - Nutze `InvestitionMonatsdaten` (PV-Module)
- `Monatsdaten.batterie_*` - Nutze `InvestitionMonatsdaten` (Speicher)

### Schicht 2: Berechnungslogik

| Datei | Funktionen | Beschreibung |
|-------|-----------|-------------|
| `core/calculations.py` | `berechne_monatskennzahlen()`, `berechne_speicher_einsparung()`, `berechne_eauto_einsparung()`, `berechne_waermepumpe_einsparung()`, `berechne_roi()`, `berechne_ust_eigenverbrauch()` | Reine Berechnungsfunktionen ohne DB-Zugriff |
| `api/routes/cockpit.py` | 6 Endpoints | Aggregation aller Daten für Dashboard |
| `api/routes/aussichten.py` | 4 Endpoints | Prognosen und Finanzberechnungen |
| `api/routes/investitionen.py` | ROI-Dashboard | PV-System-Gruppierung und ROI pro Komponente |
| `api/routes/strompreise.py` | `lade_tarife_fuer_anlage()` | Multi-Tarif-Lookup mit Fallback |
| `utils/sonstige_positionen.py` | `berechne_sonstige_summen()` | Strukturierte Erträge/Ausgaben |
| `services/energie_profil_service.py` | `aggregate_day()`, `rollup_month()`, `backfill_range()` | Tages-Aggregation + Monats-Rollup |

### Schicht 3: Frontend-Anzeige

| Seite | API-Endpoint | Angezeigte Kennzahlen |
|-------|-------------|----------------------|
| Dashboard (Cockpit) | `GET /api/cockpit/uebersicht/{id}?jahr=` | Autarkie, EV-Quote, Netto-Ertrag, Rendite, CO2 |
| Auswertung/Prognose-IST | `GET /api/cockpit/prognose-vs-ist/{id}?jahr=` | Performance Ratio pro Monat |
| Auswertung/Nachhaltigkeit | `GET /api/cockpit/nachhaltigkeit/{id}` | CO2-Zeitreihe, Äquivalente |
| Auswertung/Komponenten | `GET /api/cockpit/komponenten-zeitreihe/{id}` | Speicher-COP, WP-JAZ, E-Auto PV-Anteil |
| PV-Strings | `GET /api/cockpit/pv-strings/{id}?jahr=` | SOLL vs IST pro String |
| Auswertung/Investitionen | `GET /api/investitionen/roi/{id}` | ROI%, Amortisation pro System |
| Auswertung/Tabelle | `GET /api/monatsdaten/aggregiert/{id}` | 22-Spalten-Explorer, Vorjahres-Delta |
| Aussichten/Kurzfristig | `GET /api/aussichten/kurzfristig/{id}` | 7-Tage PV-Prognose + SFML-Vergleich |
| Aussichten/Langfristig | `GET /api/aussichten/langfristig/{id}` | 12-Monats-Prognose |
| Aussichten/Trend | `GET /api/aussichten/trend/{id}` | Degradation, Jahresvergleich |
| Aussichten/Finanzen | `GET /api/aussichten/finanzen/{id}` | Amortisations-Fortschritt, Prognose |

---

## 2. Konstanten

Definiert in `core/calculations.py`:

| Konstante | Wert | Einheit | Verwendung |
|-----------|------|---------|-----------|
| `CO2_FAKTOR_STROM_KG_KWH` | 0.38 | kg CO2/kWh | Deutscher Strommix |
| `CO2_FAKTOR_BENZIN_KG_LITER` | 2.37 | kg CO2/L | Benzinverbrennung |
| `CO2_FAKTOR_GAS_KG_KWH` | 0.201 | kg CO2/kWh | Erdgasverbrennung |
| `CO2_FAKTOR_OEL_KG_KWH` | 0.266 | kg CO2/kWh | Heizölverbrennung |
| `SPEICHER_ZYKLEN_PRO_JAHR` | 250 | Vollzyklen | Für Speicher-Prognose |

Definiert in `api/routes/aussichten.py`:

| Konstante | Wert | Verwendung |
|-----------|------|-----------|
| `DEFAULT_SYSTEM_LOSSES` | 0.14 (14%) | Kurzfrist-PV-Prognose |
| `TEMP_COEFFICIENT` | 0.004 (0.4%/°C) | Leistungsabnahme über 25°C |
| Konfidenz-Faktor | 0.15 (15%) | Langfrist-Konfidenzband |

Hardcodierte Werte in `cockpit.py`:

| Wert | Verwendung |
|------|-----------|
| Gas-Preis: 10.0 ct/kWh | WP-Ersparnis (vs. Gas) |
| Gas-Wirkungsgrad: 0.9 (90%) | WP CO2-Vergleich |
| Benzin-Verbrauch: 7.0 L/100km | E-Mob-Ersparnis |
| Benzin-Preis: 1.80 EUR/L | E-Mob-Ersparnis (Cockpit-Fallback) |

---

## 3. Berechnungsketten nach Thema

### 3.1 Energie-Bilanz (Monatskennzahlen)

**Funktion:** `berechne_monatskennzahlen()` in `core/calculations.py`
**Verwendet in:** Cockpit-Übersicht (inline Berechnung), Monatsdaten-Anzeige

#### Eingabefelder

| Feld | Quelle | Tabelle |
|------|--------|---------|
| `einspeisung_kwh` | Zähler | `Monatsdaten` |
| `netzbezug_kwh` | Zähler | `Monatsdaten` |
| `pv_erzeugung_kwh` | PV-Module | `InvestitionMonatsdaten.verbrauch_daten` (Typ: pv-module) |
| `batterie_ladung_kwh` | Speicher | `InvestitionMonatsdaten.verbrauch_daten` (Typ: speicher) |
| `batterie_entladung_kwh` | Speicher | `InvestitionMonatsdaten.verbrauch_daten` (Typ: speicher) |
| `v2h_entladung_kwh` | E-Auto V2H | `InvestitionMonatsdaten.verbrauch_daten` (Typ: e-auto) |
| `einspeiseverguetung_cent` | Tarif | `Strompreis.einspeiseverguetung_cent_kwh` |
| `netzbezug_preis_cent` | Tarif | `Strompreis.netzbezug_arbeitspreis_cent_kwh` |
| `grundpreis_euro_monat` | Tarif | `Strompreis.grundpreis_euro_monat` |
| `netzbezug_durchschnittspreis_cent` | HA-Sensor oder Monatsdaten | Dynamischer Ø-Preis |
| `leistung_kwp` | Anlage | Summe aller `Investition.leistung_kwp` (pv-module) |

#### Formeln

```
Direktverbrauch     = max(0, PV_Erzeugung - Einspeisung - Batterie_Ladung)
Eigenverbrauch      = Direktverbrauch + Batterie_Entladung + V2H_Entladung
Gesamtverbrauch     = Eigenverbrauch + Netzbezug
EV-Quote (%)        = Eigenverbrauch / PV_Erzeugung * 100        (wenn PV > 0)
Autarkie (%)        = Eigenverbrauch / Gesamtverbrauch * 100     (wenn GV > 0)
Spez. Ertrag        = PV_Erzeugung / Leistung_kWp               (kWh/kWp)

Einspeise-Erlös (EUR)    = Einspeisung * Einspeisevergütung / 100
Netzbezug-Kosten (EUR)   = Netzbezug * Netzbezug_Preis / 100 + Grundpreis
EV-Ersparnis (EUR)       = Eigenverbrauch * Netzbezug_Preis / 100
Netto-Ertrag (EUR)       = Einspeise-Erlös + EV-Ersparnis
CO2-Einsparung (kg)      = PV_Erzeugung * 0.38
```

**Wichtig:** `Netto_Ertrag` enthält NICHT den Abzug der Netzbezugskosten, da diese auch ohne PV angefallen wären.

### 3.2 Finanzen (Cockpit)

**Endpoint:** `GET /api/cockpit/uebersicht/{anlage_id}` in `cockpit.py`

Die Cockpit-Übersicht aggregiert alle Monatsdaten für ein Jahr (oder alle Jahre) und berechnet:

#### Finanzielle Kennzahlen

```
Einspeise-Erlös     = Σ(Einspeisung) * Einspeisevergütung / 100
EV-Ersparnis        = Σ(Eigenverbrauch) * Netzbezug_Preis / 100
Netto-Ertrag        = Einspeise-Erlös + EV-Ersparnis [- USt_Eigenverbrauch]
BKW-Ersparnis       = Σ(BKW_Eigenverbrauch) * Netzbezug_Preis / 100
Sonstige-Netto      = Σ(sonstige_ertraege) - Σ(sonstige_ausgaben)

Betriebskosten_Zeitraum = Σ(Betriebskosten_Jahr) * Anzahl_Monate / 12

Kumulative Ersparnis = Netto-Ertrag + WP-Ersparnis + E-Mob-Ersparnis
                       + BKW-Ersparnis + Sonstige-Netto
                       - Betriebskosten_Zeitraum

Jahres-Rendite (%)  = Kumulative_Ersparnis / Investition_gesamt * 100
```

#### WP-Ersparnis im Cockpit

```
WP-Ersparnis = (WP_Wärme / 0.9 * Gas_Preis - WP_Strom * WP_Preis) / 100
```

Wobei:
- `WP_Wärme` = Σ(heizenergie_kwh + warmwasser_kwh) aus InvestitionMonatsdaten
- `WP_Strom` = Σ(stromverbrauch_kwh) aus InvestitionMonatsdaten
- `0.9` = angenommener Gasheizungs-Wirkungsgrad
- `Gas_Preis` = 10.0 ct/kWh (hardcodiert)
- `WP_Preis` = Spezialtarif waermepumpe (Fallback: allgemein)

#### E-Mob-Ersparnis im Cockpit

```
Benzin_Verbrauch    = Σ(km_gefahren) * 7 / 100    (7 L/100km Annahme)
Benzin_Kosten       = Benzin_Verbrauch * 1.80      (1.80 EUR/L Annahme)
Strom_Kosten        = (Ladung_gesamt - Ladung_PV) * Wallbox_Preis / 100
E-Mob-Ersparnis     = Benzin_Kosten - Strom_Kosten
```

**Hinweis:** Dienstliche E-Autos/Wallboxen (`ist_dienstlich = true`) werden NICHT in die E-Mob-Ersparnis eingerechnet. Deren Ladekosten fließen als kalkulatorische Ausgaben in `sonstige_ausgaben_gesamt`.

**Hinweis Kraftstoffpreis (ab v3.17.0):** Im Cockpit werden weiterhin die hardcodierten Defaults verwendet. In **Aussichten**, **HA-Sensor-Export** und **PDF-Finanzbericht** wird stattdessen pro Monat der echte Kraftstoffpreis aus `Monatsdaten.kraftstoffpreis_euro` verwendet (Quelle: EU Weekly Oil Bulletin). Fallback auf den statischen `benzinpreis_euro`-Parameter der Investition wenn kein Monatswert vorhanden.

#### Investitionskosten (Mehrkosten-Ansatz)

```
PV-System-Kosten     = Σ(Kosten) für pv-module, wechselrichter, speicher, wallbox, bkw
WP-Mehrkosten        = max(0, WP_Kosten - alternativ_kosten_euro)     (Default: 8.000 EUR)
E-Auto-Mehrkosten    = max(0, E-Auto_Kosten - alternativ_kosten_euro) (Default: 35.000 EUR)
Sonstige-Kosten      = Σ(Kosten) für andere Typen

Investition_gesamt   = PV-System + WP-Mehrkosten + E-Auto-Mehrkosten + Sonstige
```

### 3.3 Speicher-Einsparung

**Funktion:** `berechne_speicher_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`investitionen.py`)

#### Eingabefelder

| Feld | Quelle |
|------|--------|
| `kapazitaet_kwh` | `Investition.parameter["kapazitaet_kwh"]` |
| `wirkungsgrad_prozent` | `Investition.parameter["wirkungsgrad_prozent"]` (Default: 95) |
| `nutzt_arbitrage` | `Investition.parameter["nutzt_arbitrage"]` (Default: false) |
| `lade_preis_cent` | `Investition.parameter["lade_durchschnittspreis_cent"]` (Default: 12) |
| `entlade_preis_cent` | `Investition.parameter["entlade_vermiedener_preis_cent"]` (Default: 35) |

#### Formeln

**Ohne Arbitrage (Eigenverbrauchsoptimierung):**
```
Wirkungsgrad         = wirkungsgrad_prozent / 100
Nutzbare_Speicherung = Kapazität * 250 Zyklen * Wirkungsgrad
Standard_Spread      = Netzbezug_Preis - Einspeisevergütung
Jahres-Einsparung    = Nutzbare_Speicherung * Standard_Spread / 100
```

**Mit Arbitrage (70/30-Modell):**
```
PV-Anteil (70%)      = Nutzbare_Speicherung * 0.70
Arbitrage-Anteil (30%) = Nutzbare_Speicherung * 0.30

PV-Einsparung        = PV-Anteil * Standard_Spread / 100
Arbitrage-Spread      = Entlade_Preis - Lade_Preis
Arbitrage-Einsparung  = Arbitrage-Anteil * Arbitrage_Spread / 100
Jahres-Einsparung     = PV-Einsparung + Arbitrage-Einsparung
```

### 3.4 E-Auto-Einsparung

**Funktion:** `berechne_eauto_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`investitionen.py`)

#### Eingabefelder

| Feld | Quelle |
|------|--------|
| `km_jahr` | `Investition.parameter["km_jahr"]` (Default: 15000) |
| `verbrauch_kwh_100km` | `Investition.parameter["verbrauch_kwh_100km"]` (Default: 18) |
| `pv_anteil_prozent` | `Investition.parameter["pv_anteil_prozent"]` (Default: 60) |
| `benzinpreis_euro_liter` | `Investition.parameter["benzinpreis_euro"]` (Default: 1.85) |
| `benzin_verbrauch_liter_100km` | `Investition.parameter["benzin_verbrauch_liter_100km"]` (Default: 7.0) |
| `nutzt_v2h` | `Investition.parameter["nutzt_v2h"]` (Default: false) |

#### Formeln

```
Strom_Bedarf         = km_jahr * Verbrauch_kWh_100km / 100
PV_Anteil            = pv_anteil_prozent / 100
Netz_Anteil          = 1 - PV_Anteil

Strom_Kosten         = Strom_Bedarf * Netz_Anteil * Strompreis / 100
Benzin_Verbrauch     = km_jahr * Benzin_L_100km / 100
Benzin_Kosten        = Benzin_Verbrauch * Benzinpreis_EUR

V2H_Einsparung       = V2H_Entladung_kWh * V2H_Preis / 100    (wenn V2H aktiv)

Jahres-Einsparung    = Benzin_Kosten - Strom_Kosten + V2H_Einsparung

CO2_Verbrenner       = Benzin_Verbrauch * 2.37
CO2_E-Auto           = Strom_Bedarf * Netz_Anteil * 0.38
CO2-Einsparung       = CO2_Verbrenner - CO2_E-Auto
```

#### Dynamischer Kraftstoffpreis (ab v3.17.0)

In **Aussichten (Finanzen)** wird die E-Auto-Ersparnis **pro Monat** mit dem echten Kraftstoffpreis berechnet:

```
Für jeden historischen Monat:
  Benzinpreis = Monatsdaten.kraftstoffpreis_euro       (wenn vorhanden)
              ∨ Investition.parameter.benzinpreis_euro  (Fallback statisch)
  Benzin_Kosten_Monat = km_gefahren / 100 * Vergleich_L_100km * Benzinpreis
  Strom_Kosten_Monat  = ladung_netz_kwh * Netzbezug_Preis / 100

Für Jahresprognose:
  Prognose_Benzinpreis = Ø(Monatsdaten.kraftstoffpreis_euro)  (historischer Durchschnitt)
                       ∨ Investition.parameter.benzinpreis_euro  (Fallback)
```

**Datenquelle:** EU Weekly Oil Bulletin (Euro-Super 95, inkl. Steuern, wöchentlich, History seit 2005). Befüllung via Backfill-Endpoint oder wöchentlichem Scheduler-Job (Dienstags 06:00).

**Betroffen:** Aussichten (`aussichten.py`), HA-Sensor-Export (`ha_export.py`), PDF-Finanzbericht (`pdf_operations.py`).

### 3.5 Wärmepumpe-Einsparung

**Funktion:** `berechne_waermepumpe_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`investitionen.py`)

#### 3 Effizienz-Modi

**Modus A: `gesamt_jaz` (Standard - gemessene Jahresarbeitszahl)**
```
WP_Strom_kWh         = Gesamtwärmebedarf / JAZ
```

**Modus B: `scop` (EU-Label SCOP-Werte)**
```
Strom_Heizung        = Heizwärmebedarf / SCOP_Heizung
Strom_Warmwasser     = Warmwasserbedarf / SCOP_Warmwasser
WP_Strom_kWh         = Strom_Heizung + Strom_Warmwasser
```

**Modus C: `getrennte_cops` (präzise Betriebspunkte)**
```
Strom_Heizung        = Heizwärmebedarf / COP_Heizung
Strom_Warmwasser     = Warmwasserbedarf / COP_Warmwasser
WP_Strom_kWh         = Strom_Heizung + Strom_Warmwasser
```

#### Gemeinsame Formeln (alle Modi)

```
PV_Anteil            = pv_anteil_prozent / 100
Netz_Anteil          = 1 - PV_Anteil

WP_Kosten            = WP_Strom * Netz_Anteil * Strompreis / 100
Alte_Kosten           = Gesamtwärmebedarf * Alter_Preis / 100

Jahres-Einsparung     = Alte_Kosten - WP_Kosten

CO2_alt               = Gesamtwärmebedarf * CO2_Faktor[gas|oel|strom]
CO2_WP                = WP_Strom * Netz_Anteil * 0.38
CO2-Einsparung        = CO2_alt - CO2_WP
```

#### Eingabefelder

| Feld | Parameter-Key | Default |
|------|--------------|---------|
| Effizienz-Modus | `effizienz_modus` | `gesamt_jaz` |
| JAZ | `jaz` | 3.5 |
| SCOP Heizung | `scop_heizung` | 4.5 |
| SCOP Warmwasser | `scop_warmwasser` | 3.2 |
| COP Heizung | `cop_heizung` | 3.9 |
| COP Warmwasser | `cop_warmwasser` | 3.0 |
| Heizwärmebedarf | `heizwaermebedarf_kwh` | 12000 |
| Warmwasserbedarf | `warmwasserbedarf_kwh` | 3000 |
| PV-Anteil | `pv_anteil_prozent` | 30 |
| Alter Energieträger | `alter_energietraeger` | `gas` |
| Alter Preis | `alter_preis_cent_kwh` | 12 |
| WP-Strompreis | Spezialtarif `waermepumpe` | Fallback: allgemein |

### 3.6 ROI & Amortisation

**Funktion:** `berechne_roi()` in `core/calculations.py`

```
Relevante_Kosten     = Anschaffungskosten - Alternativkosten
Netto_Einsparung     = Jahres-Einsparung - Betriebskosten_Jahr
ROI (%)              = Netto_Einsparung / Relevante_Kosten * 100
Amortisation (Jahre) = Relevante_Kosten / Netto_Einsparung
```

Wobei `Betriebskosten_Jahr` = `Investition.betriebskosten_jahr` (Wartung, Versicherung etc., Default: 0).

**WICHTIG - Zwei verschiedene ROI-Metriken:**

| Metrik | Wo angezeigt | Formel | Bedeutung |
|--------|-------------|--------|-----------|
| **Jahres-Rendite** | Cockpit, Auswertung/Investitionen | Kumul. Ersparnis / Investition * 100 | Wie viel % bereits amortisiert (kumuliert) |
| **ROI p.a.** | ROI-Dashboard (Investitionen) | Jahres-Einsparung / Relevante Kosten * 100 | Rendite pro Jahr |
| **Amortisations-Fortschritt** | Aussichten/Finanzen | Bisherige Erträge / Investition * 100 | Kumulierter Fortschritt |

### 3.7 USt auf Eigenverbrauch

**Funktion:** `berechne_ust_eigenverbrauch()` in `core/calculations.py`
**Bedingung:** Nur wenn `Anlage.steuerliche_behandlung == "regelbesteuerung"`

```
Abschreibung_Jahr    = Investition_gesamt / 20        (20 Jahre lineare AfA)
Selbstkosten_pro_kWh = (Abschreibung_Jahr + Betriebskosten_Jahr) / PV_Erzeugung_Jahr
USt_Eigenverbrauch   = Eigenverbrauch * Selbstkosten_pro_kWh * USt_Satz / 100
```

| Feld | Quelle |
|------|--------|
| `Investition_gesamt` | Σ(Investition.anschaffungskosten_gesamt) |
| `Betriebskosten_Jahr` | Σ(Investition.betriebskosten_jahr) |
| `PV_Erzeugung_Jahr` | Aggregierte PV-Erzeugung aus InvestitionMonatsdaten |
| `USt_Satz` | `Anlage.ust_satz_prozent` (DE: 19, AT: 20, CH: 8.1) |

**Auswirkung:** USt wird vom `Netto_Ertrag` abgezogen (in Cockpit und Aussichten/Finanzen).

### 3.8 CO2-Bilanz

**Endpoint:** `GET /api/cockpit/nachhaltigkeit/{anlage_id}`

#### Monatliche CO2-Berechnung

```
CO2_PV    = Eigenverbrauch * 0.38                    (vermiedener Netzstrom)
CO2_WP    = (WP_Wärme / 0.9 * 0.201) - (WP_Strom * 0.38)  (vs. Gasheizung)
CO2_E-Mob = (Benzin_L * 2.37) - ((Ladung - PV_Ladung) * 0.38)  (vs. Benziner)
CO2_gesamt = CO2_PV + max(0, CO2_WP) + max(0, CO2_E-Mob)
```

#### Äquivalente

```
Bäume          = CO2_gesamt / 20       (kg/Baum/Jahr)
Auto-km        = CO2_gesamt / 0.12     (kg/km)
Flug-km        = CO2_gesamt / 0.25     (kg/km)
```

### 3.9 PV-String SOLL-IST Vergleich

**Endpoint:** `GET /api/cockpit/pv-strings/{anlage_id}?jahr=`

#### SOLL-Berechnung (PVGIS)

**Ab v2.3.2 (Per-Modul PVGIS-Daten vorhanden):**
```
SOLL_Monat = PVGISPrognose.module_monatswerte[modul_id][monat].e_m
```

**Fallback (ältere Prognosen - proportional nach kWp):**
```
kWp_Anteil = Modul_kWp / Gesamt_kWp
SOLL_Monat = PVGISPrognose.monatswerte[monat].e_m * kWp_Anteil
```

**Faire Vergleichsbasis (ab v2.3.2):**
SOLL wird NUR für Monate gezählt, die auch IST-Daten haben. Verhindert aufgeblähten SOLL bei Teil-Jahren.

#### IST-Berechnung

```
IST_Monat = InvestitionMonatsdaten.verbrauch_daten["pv_erzeugung_kwh"]
            (pro PV-Modul, für das gewählte Jahr)
```

#### Kennzahlen pro String

```
Abweichung_kWh        = IST - SOLL
Abweichung_%          = (IST - SOLL) / SOLL * 100
Performance_Ratio      = IST / SOLL
Spez. Ertrag (kWh/kWp) = IST_Jahr / Modul_kWp
```

### 3.10 Sonstige Positionen

**Utility:** `utils/sonstige_positionen.py`

Jede `InvestitionMonatsdaten.verbrauch_daten` kann sonstige Positionen enthalten:

```json
{
  "sonstige_positionen": [
    {"bezeichnung": "THG-Quote", "betrag": 200.00, "typ": "ertrag"},
    {"bezeichnung": "Wartung", "betrag": 50.00, "typ": "ausgabe"}
  ]
}
```

**Legacy-Format (backward-kompatibel):**
```json
{"sonderkosten_euro": 50.0, "sonderkosten_notiz": "Wartung"}
```
wird automatisch zu `[{"bezeichnung": "Wartung", "betrag": 50.0, "typ": "ausgabe"}]` konvertiert.

**Aggregation:**
```
Sonstige_Erträge  = Σ(betrag) wo typ == "ertrag"    (alle Investitionstypen)
Sonstige_Ausgaben = Σ(betrag) wo typ == "ausgabe"    (alle Investitionstypen)
Sonstige_Netto    = Erträge - Ausgaben
```

**Dienstliche Ladekosten:**
Bei `ist_dienstlich == true` (E-Auto/Wallbox) werden Ladekosten als kalkulatorische Ausgaben verbucht:
```
Dienstlich_Ladekosten = Netz_kWh * Wallbox_Preis + PV_kWh * Einspeisevergütung
```

---

## 4. Prognosen (Aussichten)

### 4.1 Kurzfrist-Prognose (7-16 Tage)

**Endpoint:** `GET /api/aussichten/kurzfristig/{anlage_id}`
**Datenquelle:** Open-Meteo (konfigurierbar, siehe Wettermodell-Kaskade)

```
PV_Ertrag_Tag = Globalstrahlung_kWh_m2 * Anlagenleistung_kWp * (1 - System_Losses)

Wenn Temperatur > 25°C:
    Temp_Verlust = (Temperatur - 25) * 0.004
    PV_Ertrag_Tag *= (1 - Temp_Verlust)
```

| Parameter | Quelle | Default |
|-----------|--------|---------|
| `System_Losses` | `PVGISPrognose.system_losses / 100` | 0.14 (14%) |
| `Anlagenleistung_kWp` | Σ(PV-Module) + Σ(BKW) | `Anlage.leistung_kwp` |
| Globalstrahlung | Wettermodell (siehe unten) | - |

#### Wettermodell-Kaskade

Das verwendete Wettermodell ist pro Anlage konfigurierbar (`Anlage.wettermodell`):

| Wert | Modell | Auflösung | Einsatz |
|------|--------|-----------|---------|
| `auto` | Bright Sky (DWD) für DE, sonst Open-Meteo best_match | variabel | Standard |
| `meteoswiss_icon_ch2` | MeteoSwiss ICON-CH2 | 2 km | Alpine Standorte CH/AT/IT |
| `icon_d2` | DWD ICON-D2 | 2,2 km | Deutschland (hochauflösend) |
| `icon_eu` | DWD ICON-EU | ~7 km | Europa |
| `ecmwf_ifs04` | ECMWF IFS | 0,25° | Global |

Bei einem spezifischen Modell versucht EEDC zuerst dieses Modell. Schlägt der Abruf fehl oder liefert es keine Daten für den Standort, fällt es auf `best_match` zurück (Kaskade). Die verwendete Quelle pro Tag wird im Response als `datenquelle`-Kürzel (MS/D2/EU/EC/BM) mitgeliefert.

### 4.1b Solar Forecast ML (SFML)

**Endpoint:** `GET /api/aussichten/kurzfristig/{anlage_id}` (SFML-Werte im gleichen Response)
**Service:** `services/solar_forecast_service.py`
**Externe API:** forecast.solar oder solcast.com (konfigurierbar)

SFML ist eine optionale KI-basierte Prognose-Ergänzung. Sie liefert eine zweite Tages-Prognoselinie neben der EEDC-Eigenprognose und den IST-Werten.

#### Datenfluss

```
1. Externer SFML-Anbieter liefert kWh-Prognose pro Tag
2. Werte werden in DB persistiert (Tabelle: SolarForecastML)
3. Endpoint gibt SFML-Werte zusammen mit EEDC-Prognose zurück
```

#### Response-Felder (pro Tag)

```json
{
  "datum": "2026-03-28",
  "eedc_prognose_kwh":  12.4,
  "sfml_prognose_kwh":  11.8,
  "ist_kwh":            13.1,       // null wenn Zukunft
  "datenquelle":        "MS"        // Wettermodell-Kürzel
}
```

#### Abweichungsberechnung (Prognose-Vergleich)

```
EEDC_Abweichung (%) = (IST - EEDC_Prognose) / EEDC_Prognose * 100
SFML_Abweichung (%) = (IST - SFML_Prognose) / SFML_Prognose * 100
```

Beide Abweichungen werden im Frontend als farbige Badges angezeigt (grün = Übererfüllung, rot = Untererfüllung).

### 4.2 Langfrist-Prognose (12 Monate)

**Endpoint:** `GET /api/aussichten/langfristig/{anlage_id}`

```
PVGIS_kWh     = PVGISPrognose.monatswerte[monat].e_m
                (Fallback: TMY * kWp * 0.85)

Monat_PR      = Ø(IST / SOLL) für diesen Monat aus historischen Daten
Gesamt_PR     = Ø(alle monatlichen Performance Ratios)

Trend_kWh     = PVGIS_kWh * Monat_PR
Konfidenz_Min = Trend_kWh * 0.85    (15% Band)
Konfidenz_Max = Trend_kWh * 1.15

Trend-Richtung:
    > 1.05 → "positiv"
    < 0.95 → "negativ"
    sonst  → "stabil"
```

### 4.3 Trend-Analyse & Degradation

**Endpoint:** `GET /api/aussichten/trend/{anlage_id}`

#### Degradation (2 Strategien)

**Primär: Vollständige Jahre (12 Monate)**
```
Wenn >= 2 vollständige Jahre vorhanden:
    Änderung = (Letztes_Jahr_kWh - Erstes_Jahr_kWh) / Erstes_Jahr_kWh * 100
    Degradation = Änderung / Anzahl_Jahre
```

**Fallback: TMY-Ergänzung (>= 6 Monate pro Jahr)**
```
Wenn >= 2 Jahre mit jeweils >= 6 Monaten Daten:
    1. Performance-Ratio aus vorhandenen Monaten berechnen
    2. Fehlende Monate mit TMY * PR ergänzen
    3. Degradation aus ergänzten Jahreswerten ableiten
```

### 4.4 Finanz-Prognose & Amortisation

**Endpoint:** `GET /api/aussichten/finanzen/{anlage_id}`

#### Bisherige Erträge (historisch)

```
Bisherige_Erträge = Σ(Einspeisung * Vergütung / 100)         (PV)
                  + Σ(Eigenverbrauch * Netzbezug_Preis / 100)  (EV)
                  + WP_Ersparnis                                 (vs. Gas)
                  + E-Auto_Ersparnis                             (vs. Benzin)
                  + BKW_Ersparnis                                (Eigenverbrauch)
                  + Sonstige_Netto                               (alle Investitionstypen)
```

#### WP-Ersparnis (historisch, in Finanzen)

```
Für jeden Monat mit WP-Daten:
    Gas_Kosten    = (Heizung + WW) / 0.9 * Gas_Preis / 100
    WP_Netzkosten = Strom * 0.5 * WP_Preis / 100    (50% Netzanteil Annahme)
    Ersparnis     = Gas_Kosten - WP_Netzkosten
```

#### E-Auto-Ersparnis (historisch, in Finanzen)

```
Benzin_Liter  = Σ(km) / 100 * Vergleich_L_100km
Benzin_Kosten = Benzin_Liter * Benzinpreis
Netzstrom_Kosten = Σ(ladung_netz_kwh) * Strompreis / 100
Ersparnis     = Benzin_Kosten - Netzstrom_Kosten
```

#### Monatsprognose (zukünftig)

Für jeden Prognosemonat:
```
PV_kWh             = PVGIS_Monatswert (oder TMY * kWp * 0.85)
Basis_EV            = PV_kWh * Basis_EV_Quote   (historisch ermittelt, 15-70%)
Speicher_Beitrag    = Ø_Speicher_Entladung * PV_Faktor
V2H_Beitrag         = Ø_V2H_Entladung (konstant)
WP_PV_Anteil        = WP_Strom * 0.5 * sqrt(PV_Faktor)

Eigenverbrauch      = min(Basis_EV + Speicher + V2H + WP_PV, PV_kWh)
Einspeisung         = PV_kWh - Eigenverbrauch
Netto_Ertrag        = Einspeisung * Vergütung/100 + Eigenverbrauch * Preis/100
```

WP saisonal gewichtet:
```
WP_SAISON_FAKTOREN = {Jan: 1.8, Feb: 1.6, Mär: 1.3, Apr: 0.8, Mai: 0.4, Jun: 0.2,
                      Jul: 0.2, Aug: 0.2, Sep: 0.4, Okt: 0.8, Nov: 1.3, Dez: 1.7}
WP_Strom_Monat = WP_Strom_Durchschnitt * Saison_Faktor
```

#### Amortisation

```
Investition          = PV_System + WP_Mehrkosten + E-Auto_Mehrkosten + Sonstige

Jahres_Netto_Ertrag  = PV_Einspeise_Erlös + EV_Ersparnis
                     + WP_Ersparnis + E-Auto_Ersparnis
                     + BKW_Ersparnis + Sonstige_Netto
                     - Betriebskosten_Jahr
                     [- USt_Eigenverbrauch]

ROI_Fortschritt (%)  = Bisherige_Erträge / Investition * 100
Amortisation_erreicht = Bisherige_Erträge >= Investition

Wenn nicht amortisiert:
    Rest_Betrag           = Investition - Bisherige_Erträge
    Monate_bis_Amort      = Rest_Betrag / (Jahres_Netto_Ertrag / 12)
    Prognose_Jahr         = Heute + Monate_bis_Amort
```

---

## 5. Tarif-System (Spezialtarife)

**Funktion:** `lade_tarife_fuer_anlage()` in `strompreise.py`

### Funktionsweise

1. Alle gültigen Tarife laden (`gueltig_ab <= heute` UND (`gueltig_bis IS NULL` ODER `gueltig_bis >= heute`))
2. Nach `verwendung` gruppieren (neuester zuerst)
3. Fallback-Kette:

```
waermepumpe → waermepumpe-Tarif || allgemein
wallbox     → wallbox-Tarif     || allgemein
allgemein   → allgemein-Tarif   || Hardcoded Defaults (30.0 / 8.2)
```

### Verwendung in Berechnungen

| Komponente | Tarif-Key | Preis-Feld |
|-----------|-----------|-----------|
| PV Einspeisung/EV | `allgemein` | `einspeiseverguetung_cent_kwh`, `netzbezug_arbeitspreis_cent_kwh` |
| Wärmepumpe Strom | `waermepumpe` | `netzbezug_arbeitspreis_cent_kwh` |
| Wallbox/E-Auto Ladung | `wallbox` | `netzbezug_arbeitspreis_cent_kwh` |
| Grundpreis | `allgemein` | `grundpreis_euro_monat` |

### Hardcoded Defaults (wenn kein Tarif)

```text
Netzbezug_Preis   = 30.0 ct/kWh
Einspeisevergütung = 8.2 ct/kWh
Grundpreis         = 0 EUR/Monat
```

### Dynamischer Tarif / Monatlicher Ø-Strompreis

Für Nutzer mit dynamischem Stromtarif (z.B. Tibber, aWATTar) kann der tatsächliche monatliche Durchschnittspreis verwendet werden statt des festen Tarifpreises.

**Fallback-Kette für `netzbezug_preis_cent`:**

```text
1. Monatsdaten.netzbezug_durchschnittspreis_cent  (manuell pro Monat)
2. HA-Sensor strompreis (via Sensor-Mapping)       (automatisch aus HA)
3. Strompreis.netzbezug_arbeitspreis_cent_kwh      (fester Tarif)
4. Hardcoded Default: 30.0 ct/kWh
```

**Konfiguration:**

- Im Sensor-Mapping kann ein HA-Sensor für `strompreis` zugeordnet werden
- Im Monatsabschluss-Wizard wird der Ø-Preis als Vorschlag angezeigt
- Manuell editierbar unter Monatsdaten

---

## 6. Investitionstyp-spezifische Berechnungen (ROI-Dashboard)

**Endpoint:** `GET /api/investitionen/roi/{anlage_id}`

### PV-System-Gruppierung (3-Pass)

```
Pass 1: Alle Wechselrichter identifizieren → pv_systeme[wr_id]
Pass 2: PV-Module via parent_investition_id zuordnen,
         DC-Speicher via parent_investition_id zuordnen
Pass 3: Verbleibende Investitionen → standalone

PV-Einsparung wird proportional nach kWp auf Module verteilt:
    Modul_Einsparung = Gesamt_PV_Einsparung * (Modul_kWp / Gesamt_kWp)
```

### Hochrechnung bei unvollständigen Jahren

```
Wenn weniger als 12 Monate Daten:
    1. Versuche PVGIS-gewichtete Hochrechnung:
       Faktor = PVGIS_Jahressumme / PVGIS_Summe_vorhandene_Monate
    2. Fallback: Lineare Hochrechnung:
       Faktor = 12 / Anzahl_Monate
```

---

## 6b. Energieprofil-Berechnungen (Tages-Aggregation)

**Service:** `services/energie_profil_service.py`
**Trigger:** Scheduler täglich 00:15 (Vortag) + Monatsabschluss (Backfill + Rollup)

### Stündliche Berechnung (aggregate_day)

Für jede Stunde (0–23) aus dem Tagesverlauf:

```
PV_kW             = Σ(positive kW aller PV-Serien)
Verbrauch_kW      = Σ(|negative kW| aller Verbraucher-Serien, ohne Batterie/Netz)
Netz_kW           = Σ(Netz-Serien)
Einspeisung_kW    = |Netz_kW| wenn Netz_kW < 0, sonst 0
Netzbezug_kW      = Netz_kW wenn Netz_kW > 0, sonst 0
Batterie_kW       = Σ(Batterie-Serien)  (positiv=Entladung, negativ=Ladung)

Überschuss_kW     = max(0, PV_kW - Verbrauch_kW)
Defizit_kW        = max(0, Verbrauch_kW - PV_kW)
```

**Zusätzliche Daten pro Stunde:**

- **Temperatur + Globalstrahlung:** Open-Meteo Historical API (Archiv) bzw. Forecast API (heute)
- **Batterie-SoC:** HA Sensor History (Stundenmittel)
- **Komponenten:** Alle Butterfly-Werte als JSON (für spätere Detail-Analyse)

### Tageszusammenfassung (TagesZusammenfassung)

```
Überschuss_kWh         = Σ(Überschuss_kW × 1h)     alle 24 Stunden
Defizit_kWh            = Σ(Defizit_kW × 1h)
Peak_PV_kW             = max(PV_kW)                  über alle Stunden
Peak_Netzbezug_kW      = max(Netzbezug_kW)
Peak_Einspeisung_kW    = max(Einspeisung_kW)
Temperatur_Min/Max     = min/max(Temperatur_C)       aus Open-Meteo
Strahlung_Summe_Wh_m2  = Σ(Globalstrahlung_W/m²)    × 1h = Wh/m²
```

**Batterie-Vollzyklen:**
```
Δ_SoC_Summe            = Σ |SoC[h] - SoC[h-1]|     für h = 1..23
Vollzyklen              = Δ_SoC_Summe / 200          (0→100→0 = 200% = 1 Vollzyklus)
```

**Performance Ratio:**
```
Theoretisch_kWh        = Strahlung_Wh_m2 × kWp / 1000
Performance_Ratio      = PV_Ertrag_kWh / Theoretisch_kWh
```

### Monats-Rollup (rollup_month)

Aggregiert alle `TagesZusammenfassung` eines Monats in `Monatsdaten`-Felder:

| Monatsdaten-Feld | Aggregation | Beschreibung |
|------------------|-------------|--------------|
| `ueberschuss_kwh` | Σ(Tages-Überschuss) | Monatlicher PV-Überschuss |
| `defizit_kwh` | Σ(Tages-Defizit) | Monatliches Energie-Defizit |
| `batterie_vollzyklen` | Σ(Tages-Vollzyklen) | Monatliche Batterie-Zyklen |
| `performance_ratio` | Ø(Tages-PR) | Durchschnittliche Performance Ratio |
| `peak_netzbezug_kw` | max(Tages-Peak) | Maximaler Netzbezug im Monat |

**Auslöser:** Wird beim Monatsabschluss nach `backfill_range()` aufgerufen, um fehlende Tage nachzuberechnen (begrenzt durch HA-History ~10 Tage).

---

## 7. Debugging-Leitfaden

### Häufige Fehlerquellen

| Symptom | Mögliche Ursache | Prüfung |
|---------|-----------------|---------|
| Autarkie zu hoch/niedrig | Falsche Einspeisung/Netzbezug-Werte | `Monatsdaten` prüfen - sind die Zählerwerte plausibel? |
| EV-Quote > 100% | Speicher-Entladung > PV-Erzeugung | `InvestitionMonatsdaten` für Speicher prüfen |
| Netto-Ertrag = 0 | Kein Tarif angelegt | `Strompreis`-Tabelle prüfen |
| WP-Ersparnis fehlt | Kein WP-Spezialtarif, falscher Gas-Preis | Tarife prüfen; hardcodierter Gas-Preis 10ct im Cockpit |
| ROI weicht ab (Cockpit vs Investitionen) | Verschiedene Berechnungswege | Cockpit: kumuliert; Investitionen: p.a. mit calculations.py |
| SOLL überhöht | Teil-Jahr ohne faire Vergleichsbasis | `months_with_data` prüfen (ab v2.3.2 behoben) |
| PV-Erzeugung = 0 | Legacy-Feld statt InvestitionMonatsdaten | Prüfen ob PV-Module als Investitionen angelegt sind |
| Dienstl. Wallbox in E-Mob | `ist_dienstlich` nicht gesetzt | `Investition.parameter["ist_dienstlich"]` prüfen |
| USt wird nicht abgezogen | Steuerliche Behandlung falsch | `Anlage.steuerliche_behandlung` muss `regelbesteuerung` sein |
| Spezialtarif greift nicht | Falsche `verwendung` oder abgelaufen | `Strompreis.verwendung` und `gueltig_ab/bis` prüfen |

### Datenfluss nachverfolgen

**Schritt 1: Eingabedaten prüfen**
```
API: GET /api/monatsdaten/aggregiert/{anlage_id}
→ Zeigt Monatsdaten + InvestitionMonatsdaten zusammen
```

**Schritt 2: Tarife prüfen**
```
API: GET /api/strompreise?anlage_id={id}&aktuell=true
→ Zeigt alle gültigen Tarife mit Verwendung
```

**Schritt 3: Berechnungsergebnis prüfen**
```
API: GET /api/cockpit/uebersicht/{anlage_id}?jahr=2025
→ Alle aggregierten KPIs für ein Jahr

API: GET /api/investitionen/roi/{anlage_id}
→ ROI pro Komponente mit Detail-Berechnung
```

**Schritt 4: Prognose-Basis prüfen**
```
API: GET /api/cockpit/prognose-vs-ist/{anlage_id}?jahr=2025
→ PVGIS SOLL vs tatsächliche IST-Werte

API: GET /api/cockpit/pv-strings/{anlage_id}?jahr=2025
→ SOLL-IST pro PV-Modul (mit Performance Ratio)
```

### Bekannte Fallstricke

1. **JSON-Felder in SQLAlchemy:** Änderungen an `verbrauch_daten` oder `parameter` werden nur persistiert mit `flag_modified(obj, "feldname")`
2. **0-Werte:** `if val:` wertet 0 als False aus → immer `if val is not None:` verwenden
3. **Legacy-Felder:** `Monatsdaten.pv_erzeugung_kwh` und `Monatsdaten.batterie_*` sind deprecated. PV-Erzeugung kommt aus `InvestitionMonatsdaten` (Typ: pv-module)
4. **PVGIS E_m vs e_m:** Ältere Prognosen verwenden `E_m` (Großbuchstabe), neuere `e_m`
5. **Grundpreis:** Wird zu den Netzbezugskosten addiert, NICHT vom Netto-Ertrag abgezogen
6. **Cockpit vs ROI-Dashboard:** Cockpit berechnet inline (vereinfacht), ROI-Dashboard nutzt `calculations.py` (detaillierter)

---

*Letzte Aktualisierung: März 2026*
