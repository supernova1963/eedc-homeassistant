# eedc Berechnungsreferenz

**Version 3.24.1** | Stand: April 2026

Dieses Dokument beschreibt alle Berechnungsketten im eedc-System: von den Eingabefeldern
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
Alte_Kosten          = Gesamtwärmebedarf * Alter_Preis / 100
                     + alternativ_zusatzkosten_jahr        # Schornsteinfeger / Wartung / Grundpreis Gaszähler

Jahres-Einsparung    = Alte_Kosten - WP_Kosten

CO2_alt               = Gesamtwärmebedarf * CO2_Faktor[gas|oel|strom]
CO2_WP                = WP_Strom * Netz_Anteil * 0.38
CO2-Einsparung        = CO2_alt - CO2_WP
```

> **Alternativ-Zusatzkosten (v3.21.0, #141):** `alternativ_zusatzkosten_jahr` (€/Jahr) deckt laufende Fixkosten der Alt-Heizung (Schornsteinfeger, Wartung, Gaszähler-Grundpreis) ab. Wird in **fünf** Berechnungs-Pfaden berücksichtigt: Aussichten historisch + Prognose, HA-Sensor-Export inkl. WP-Sensor, PDF-Jahresbericht, Investitions-Vorschau. In historischen Aggregaten anteilig pro erfasstem Monat (`alternativ_zusatzkosten_jahr / 12`).

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
| Alter Preis | `alter_preis_cent_kwh` | 12 (Fallback wenn `Monatsdaten.gaspreis_cent_kwh` leer) |
| Alternativ-Zusatzkosten | `alternativ_zusatzkosten_jahr` | 0 (€/Jahr) |
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
PV_Ertrag_Tag = GTI_kWh_m2 * Anlagenleistung_kWp * (1 - System_Losses) * Lernfaktor

Wenn Temperatur > 25°C:
    Temp_Verlust = (Temperatur - 25) * 0.004
    PV_Ertrag_Tag *= (1 - Temp_Verlust)
```

| Parameter | Quelle | Default |
|-----------|--------|---------|
| `System_Losses` | `PVGISPrognose.system_losses / 100` | 0.14 (14%) |
| `Anlagenleistung_kWp` | Σ(PV-Module) + Σ(BKW) | `Anlage.leistung_kwp` |
| `GTI_kWh_m2` | **Global Tilted Irradiance** aus Open-Meteo Solar (modul-projiziert mit Tilt + Azimut). Bei Multi-String-Anlagen werden parallele Calls pro Orientierungsgruppe abgesetzt und kWp-gewichtet kombiniert. | – |
| `Lernfaktor` | Anlagenspezifischer Korrekturfaktor (siehe §4.1c) | 1.0 (vor 7 Tagen Daten) |

> **GTI vs. GHI:** Bis v3.19.x rechnete eedc mit GHI (`shortwave_radiation`, horizontal). Bei steilen Modulen und tiefstehender Wintersonne ist die Modul-projizierte GTI 2–3× höher — der GHI-basierte „theoretische Ertrag" lag im Winter systematisch zu niedrig (PR-Werte > 1 möglich). Seit v3.20.0 werden GTI-Werte für Prognose und Performance Ratio verwendet.

> **Multi-String / PV-Parameter-Quelle (v3.20.2/v3.20.3):** kWp, Neigung und Azimut werden über den Helper `services/pv_orientation.py` gelesen, der in dieser Reihenfolge prüft: Top-Level-Spalte der Investition → `parameter.{neigung,ausrichtung}_grad` (Zahl) → `parameter.{neigung,ausrichtung}` (Zahl oder String mit Mapping `{"süd": 0, "ost": -90, "west": 90, ...}`) → Default. Damit liefern alle drei Prognose-Pfade (Energieprofil-Tagesprognose, Aussichten-Kurzfrist, Prefetch-Cache) identische Eingabe-Parameter an Open-Meteo.

#### Wettermodell-Kaskade

Das verwendete Wettermodell ist pro Anlage konfigurierbar (`Anlage.wettermodell`):

| Wert | Modell | Auflösung | Einsatz |
|------|--------|-----------|---------|
| `auto` | Bright Sky (DWD) für DE, sonst Open-Meteo best_match | variabel | Standard |
| `meteoswiss_icon_ch2` | MeteoSwiss ICON-CH2 | 2 km | Alpine Standorte CH/AT/IT |
| `icon_d2` | DWD ICON-D2 | 2,2 km | Deutschland (hochauflösend) |
| `icon_eu` | DWD ICON-EU | ~7 km | Europa |
| `ecmwf_ifs04` | ECMWF IFS | 0,25° | Global |

Bei einem spezifischen Modell versucht eedc zuerst dieses Modell. Schlägt der Abruf fehl oder liefert es keine Daten für den Standort, fällt es auf `best_match` zurück (Kaskade). Die verwendete Quelle pro Tag wird im Response als `datenquelle`-Kürzel (MS/D2/EU/EC/BM) mitgeliefert.

### 4.1b Solar Forecast ML (SFML)

**Endpoint:** `GET /api/aussichten/kurzfristig/{anlage_id}` (SFML-Werte im gleichen Response)
**Service:** `services/solar_forecast_service.py`
**Externe API:** forecast.solar oder solcast.com (konfigurierbar)

SFML ist eine optionale KI-basierte Prognose-Ergänzung. Sie liefert eine zweite Tages-Prognoselinie neben der eedc-Eigenprognose und den IST-Werten.

#### Datenfluss

```
1. Externer SFML-Anbieter liefert kWh-Prognose pro Tag
2. Werte werden in DB persistiert (Tabelle: SolarForecastML)
3. Endpoint gibt SFML-Werte zusammen mit eedc-Prognose zurück
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

### 4.1c Prognose-Vergleich (Aussichten → Prognosen)

**Endpoint:** `GET /api/aussichten/prognosen/{anlage_id}`
**Service:** `api/routes/prognosen.py` (in v3.16.6 aus `aussichten.py` ausgelagert), `services/solcast_service.py`

Der Prognosen-Tab vergleicht vier Quellen pro Tag/Stunde:

| Quelle | Bedeutung |
|---|---|
| **OpenMeteo (OM)** | Wetterbasierte Roh-Prognose aus Globalstrahlung × kWp × (1 − System_Losses) |
| **eedc (kalibriert)** | OM × aktueller Lernfaktor — die anlagenspezifisch korrigierte Prognose |
| **Solcast** | Optionale dritte Quelle, entweder Solcast-API (Free/Paid Key) oder HA-Sensor (BJReplay-Integration). 30-Min-Buckets werden per `ceil(bucket_ende)` dem Backward-Slot zugeordnet. |
| **IST** | Tatsächlich gemessener Tageswert aus den Stunden-Snapshots (siehe §6b) |

#### Lernfaktor (saisonale MOS-Kaskade, ab v3.16.15)

Die eedc-Prognose ist `OpenMeteo × Lernfaktor`. Der Lernfaktor wird aus historischen `(Prognose, IST)`-Tag-Paaren berechnet — nur Tage mit gültiger OpenMeteo-Prognose **UND** IST-Ertrag > 0.5 kWh fließen ein (Schlechtwetter-Tage mit ~0 kWh würden den Faktor sonst verzerren).

```
faktor = Σ(IST_kWh) / Σ(EEDC_Roh_Prognose_kWh)
```

Seit v3.16.15 nutzt eedc eine **saisonale Kaskade** mit den jeweils vorhandenen Daten:

| Stufe | Bedingung | Bezugszeitraum |
|---|---|---|
| **Monatsfaktor** | ≥ 15 gültige Tage im selben Kalendermonat | Tage des Kalendermonats über alle Jahre |
| **Quartalsfaktor** | ≥ 15 gültige Tage im selben Quartal | Tage des Quartals über alle Jahre |
| **30-Tage-Fenster** | ≥ 7 gültige Tage | Letzte 30 Kalendertage |
| **Inaktiv** | < 7 Tage | Lernfaktor = 1.0, eedc-Spalte gedämpft mit `—` und Tooltip-Verweis |

Die aktive Stufe wird im Status-Banner und im KPI-Card-Header angezeigt.

**Restzeit-Banner (v3.22.0):** Wenn die 7-Tage-Schwelle noch nicht erreicht ist, zeigt das Banner: „X von 7 Tagen, noch Y Tage" — Y berücksichtigt nur Tage mit gültiger Prognose UND IST > 0.5 kWh, also dieselbe Filterregel wie der Faktor selbst.

**Persistierung:** Lernfaktor pro Quelle separat gecacht. Backfill-Kandidat-Felder (`pv_prognose_kwh`, Solcast-Tageswerte) werden seit v3.16.14 alle 45 Min automatisch aus dem **Prefetch-Job** in `TagesZusammenfassung` geschrieben — vorher hing die Persistierung als Nebeneffekt am Dashboard-Besuch und der Lernfaktor konnte ohne Nutzer-Interaktion nicht berechnet werden.

#### Genauigkeits-Tracking: MAE + MBE getrennt (v3.22.0, #151)

Über alle Tage mit gleichzeitig verfügbarer Prognose und IST werden zwei Kennzahlen pro Quelle (OM, eedc, Solcast) berechnet, auf **vorzeichenbehafteten relativen Fehlern**:

```
err_rel(tag) = (Prognose_kWh - IST_kWh) / IST_kWh

MAE = Ø |err_rel|     # Mean Absolute Error — Streuung
MBE = Ø  err_rel      # Mean Bias Error — systematischer Bias
```

| Kennzahl | Aussage |
|---|---|
| **MAE** | Wie weit liegen Prognose und IST im Schnitt auseinander, **unabhängig von der Richtung**? Maß für Streuung/Schwankungsbreite. |
| **MBE** | Liegt die Quelle im Mittel **über** (positiv) oder **unter** (negativ) dem IST? Bias ist neutral gefärbt — Vorzeichen ist Information, keine Wertung. |

#### Asymmetrie-Diagnostik (v3.23.3, #151 Variante B)

MAE/MBE bleiben blind für Asymmetrie: eine Quelle, die in 50 % der Tage 30 % zu hoch und in 50 % der Tage 30 % zu niedrig liegt, hat MAE = 30 % und MBE ≈ 0 % — sie sieht „im Mittel ausgewogen" aus, ist aber nicht mit einem einzigen Lernfaktor korrigierbar. Im Diagnostisch-Modus splittet das Backend die signed errors an 0:

```
darüber: nur Tage mit err_rel > 0
  over_count       = Anzahl
  over_avg_prozent = Ø err_rel * 100

darunter: nur Tage mit err_rel ≤ 0
  under_count       = Anzahl
  under_avg_prozent = Ø |err_rel| * 100
```

Response-Schema `AsymmetrieEintrag` mit Feldern `over_count`, `over_avg_prozent`, `under_count`, `under_avg_prozent` — pro Quelle als `openmeteo_asymmetrie` / `eedc_asymmetrie` / `solcast_asymmetrie` zurückgegeben.

#### VM/NM-Split an Solar Noon (v3.22.0)

Tageshälften (Vormittag/Nachmittag) werden nicht hart bei 12:00 Uhr Clockzeit gesplittet, sondern an der astronomischen Tagesmitte (**Solar Noon**, via Equation of Time + Standortlängengrad). Die Abweichung von 12:00 kann je nach Standort und Datum bis ~30 min betragen. Slots, die Solar Noon enthalten, werden proportional auf VM und NM verteilt — konsistent zum `solar_forecast_service`.

#### IST-Slot-Behandlung

- **Backward-Slot-Konvention** (siehe §6b): Slot N enthält Energie aus dem Intervall `[N-1, N)`.
- **Gerade abgeschlossene Stunde (v3.23.0):** wird nicht als Lücke geflaggt — HA Long-Term Statistics schreibt die Stunden-Row erst am Ende der Stunde, das Zeitfenster zwischen Stundenwechsel und HA-Stats-Write (typisch ~5–60 Min) wird mit `<` (statt `<=`) toleriert.
- **Echte Lücken (>1 h alt)** werden mit ⚠ markiert. Klick auf das Symbol öffnet einen Reparatur-Popover mit „Tag neu berechnen" (`POST /api/energie-profil/{anlage_id}/reaggregate-tag`) und Sensor-Mapping-Fallback.

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
    Gas_Preis     = Monatsdaten.gaspreis_cent_kwh        # ab v3.21.0, wenn pro Monat gepflegt
                  ∨ Investition.parameter.alter_preis_cent_kwh   # Fallback statisch
    Gas_Kosten    = (Heizung + WW) / 0.9 * Gas_Preis / 100
                  + alternativ_zusatzkosten_jahr / 12     # Zusatzkosten anteilig pro Monat
    WP_Netzkosten = Strom * 0.5 * WP_Preis / 100         # 50% Netzanteil-Annahme
    Ersparnis     = Gas_Kosten - WP_Netzkosten
```

> **Monats-Gaspreis (v3.21.0):** Wenn `Monatsdaten.gaspreis_cent_kwh` pro Monat gepflegt ist, wird er Monat für Monat verwendet — ein Tarifwechsel ändert dann nicht mehr rückwirkend die ganze Historie. Ohne Eintrag bleibt es beim statischen `alter_preis_cent_kwh` der Investition. Anzeige & Pflege im Monatsabschluss-Wizard und im `MonatsdatenForm` (über `BEDINGTE_BASIS_FELDER` mit `bedingung_basis: hat_waermepumpe`).

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

**Service:** `services/energie_profil_service.py`, `services/sensor_snapshot_service.py`
**Trigger:** Scheduler stündlich `:05` (Snapshot) und `:55` (Live-Preview), täglich 00:15 (Vortag-Aggregation) + Monatsabschluss (Backfill + Rollup)

### Snapshot-basierte Architektur (ab v3.19.0, #135)

Stunden-kWh werden **nicht mehr** aus 10-Min-Leistungs-Samples integriert (±5–15 % Drift), sondern als **Differenz kumulativer Zähler-Snapshots** berechnet — analog zum HA Energy Dashboard.

```
1. Stündlicher Snapshot-Job (Cron :05) schreibt pro Anlage und gemapptem
   kWh-Sensor den aktuellen Zählerstand in die Tabelle `sensor_snapshots`.
   Quellen: HA Long-Term Statistics (Add-on)
            oder MQTT-Energy-Snapshots (Standalone/Docker).
2. :55-Live-Preview (v3.21.0) schreibt zum Stundenende einen Zählerstand
   für die anstehende volle Stunde — laufende Stunde sofort sichtbar
   statt erst um (h+1):05.
3. Tagesaggregation (00:15) bildet Differenzen: kWh[h] = snap[h] - snap[h-1]
   für h = 0..23 (Snapshot-Range -1..23, damit Slot 0 aus Vortag-23:00 fließt).
```

**Snapshot-Lücken-Interpolation (v3.20.0, #145):**

Wenn ein Snapshot fehlt (Scheduler-Ausfall, HA-Statistics-Timeout, MQTT-Cache leer), interpoliert eedc linear zwischen den vorhandenen Nachbar-Stunden:

```
Beispiel: snap[10] = 1500 kWh, snap[11] = None, snap[12] = 1505 kWh
        → interpoliert: snap[11] = 1502.5 kWh
        → kWh[11] = 2.5, kWh[12] = 2.5  (statt fälschlich kWh[11]=0, kWh[12]=5 als Spike)
```

Ränder (h0 fehlend am Tagesanfang, h24 am Tagesende) werden **nicht** extrapoliert — der Wert bleibt None und die betroffene Stunde fällt aus der Delta-Bildung. Tagessumme bleibt in jedem Fall korrekt (`snap[24] − snap[0]`).

**HA-Statistics-Toleranz (v3.20.0, #145):** Reduziert von 120 min auf **10 min**. Wenn die Zielstunde in HA-Statistics noch nicht vorhanden ist, schreibt der Job nichts (statt einen Nachbar-Wert zu liefern, der Slot N als 0 und Slot N+1 als 2-Stunden-Delta entstehen ließ). Der nächste `aggregate_day`-Lauf 15 Min später holt den Wert via Self-Healing nach.

**Restart-Recovery (v3.23.0):** Beim Scheduler-Start läuft `sensor_snapshot_startup_recovery()` im Hintergrund — holt für die letzten 6 Stunden je Anlage HA-Statistics-Snapshots (idempotent dank Upsert) plus für die laufende Stunde einen Live-Snapshot, anschließend `aggregate_today_all`.

**Tagesreset-Heuristik (v3.23.0):** HA-`utility_meter`-Sensoren mit täglichem Reset werfen um Mitternacht ein stark negatives Delta. Erkannt am Muster `s1 < 0.5 ∧ s0 > 0.5`, eedc nimmt dann `max(0, s1)` als Slot-0-Wert (Energie seit Reset, typ. ≈ 0 nachts). Bei untypischen negativen Deltas mitten am Tag bleibt die Reset-Warnung wie bisher.

**Phase D Cleanup (v3.21.0, #138):** Seit v3.21.0 ist der Zähler-Snapshot-Pfad die einzige kWh-Quelle. Der frühere W-Integration-Fallback (`_val()`-Helper, `else`-Branch in `backfill_from_statistics`) und das Feature-Flag `EEDC_ENERGIEPROFIL_QUELLE` sind entfernt. Auf Anlagen ohne kumulative Zähler erscheinen Stunden-kWh-Felder als `NULL` statt geschätzter Werte.

### Backward-Slot-Konvention (ab v3.20.0, #144)

Alle Stunden-Slots im Energieprofil und in den Prognose-Quellen folgen seit v3.20.0 der **Backward-Konvention**:

| Konvention | Slot N enthält Energie aus … |
|---|---|
| **Backward** (eedc, ab v3.20.0) | `[N-1, N)` — „die letzte Stunde". Slot 0 = Energie 23:00–24:00 des Vortags. |
| Forward (Strompreis, weiterhin) | `[N, N+1)` — „gilt ab jetzt". Industrieüblich für aWATTar/Tibber/EPEX. |

Industriestandard für Energie: HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber.

**Migration auf Backward (v3.20.0):**
- `sensor_snapshot_service.get_hourly_kwh_by_category`: Delta `snap[h] − snap[h-1]` → Slot h (vorher: `snap[h+1] − snap[h]` → Slot h)
- `solcast_service` (API + HA-Sensor): 30-Min-Buckets per `ceil(bucket_ende)` → richtigen Backward-Slot. Ein Bucket am Tagesübergang `[23:00, 23:30)` heute landet damit korrekt in Slot 0 des **Folgetags**, nicht in Slot 0 von heute.
- **Nach Update auf v3.20.0 nötig:** einmal „Verlauf nachberechnen + überschreiben" auslösen, damit alle historischen Stundenwerte umverteilt werden. Tagessummen und alle abgeleiteten Kennzahlen (Autarkie, PR, Lernfaktor) sind konventionsunabhängig korrekt.

### Stündliche Berechnung (aggregate_day)

```
PV_kWh            = snap_pv[h] - snap_pv[h-1]                  # für jede gemappte PV-Investition
Einspeisung_kWh   = snap_einspeisung[h] - snap_einspeisung[h-1]
Netzbezug_kWh     = snap_netzbezug[h] - snap_netzbezug[h-1]
Bat_Ladung_kWh    = snap_ladung[h] - snap_ladung[h-1]
Bat_Entladung_kWh = snap_entladung[h] - snap_entladung[h-1]

Verbrauch_kWh     = PV + Netzbezug + Bat_Entladung - Einspeisung - Bat_Ladung
Überschuss_kWh    = max(0, PV - Verbrauch_kWh - Bat_Ladung)
Defizit_kWh       = max(0, Verbrauch_kWh + Bat_Ladung - PV)
```

**Strikte NULL-Semantik:** Wenn ein Zähler nicht gemappt ist, bleibt das zugehörige Feld `NULL` (statt aus Leistungs-Samples zu schätzen). Im Frontend zeigt eedc ein ⚠-Badge bei Datenlücken — siehe Reparatur-Popover in §4.1c.

**Peaks aus W-Integration (für Spitzenwerte):**

```
Peak_PV_kW              = max(W-Sample) / 1000   # 10-Min-Auflösung
Peak_Netzbezug_kW       = max(W-Sample) / 1000
Peak_Einspeisung_kW     = max(W-Sample) / 1000
```

Peaks brauchen die Leistungssamples — die kWh-Aggregation läuft separat über die Snapshots.

**Zusätzliche Daten pro Stunde:**

- **Temperatur + Globalstrahlung + GTI:** Open-Meteo Historical API (Archiv) bzw. Forecast API (heute), inkl. `global_tilted_irradiance` mit Modul-Tilt/Azimut
- **Stunden-Aggregation IST von Wetter-Samples:** seit v3.23.6 als arithmetisches Mittel der 10-Min-Slots (vorher „last") — konsistent mit der Mean-Konvention der Open-Meteo-Stundenwerte, behebt einen ~25-min-Versatz im Live-Heute-Chart.
- **Batterie-SoC:** HA Sensor History (Stundenmittel) — gefiltert auf `inv.typ == "speicher"`, siehe Vollzyklen-Hinweis unten
- **Strompreis (zwei Felder):** `strompreis_cent` (Endpreis aus HA-Sensor) + `boersenpreis_cent` (EPEX, immer befüllt)

### Tageszusammenfassung (TagesZusammenfassung)

```
Überschuss_kWh         = Σ(Überschuss_kWh)            alle 24 Stunden
Defizit_kWh            = Σ(Defizit_kWh)
Peak_PV_kW             = max(PV_kW)                   über alle Stunden
Peak_Netzbezug_kW      = max(Netzbezug_kW)
Peak_Einspeisung_kW    = max(Einspeisung_kW)
Temperatur_Min/Max     = min/max(Temperatur_C)        aus Open-Meteo
Strahlung_Summe_Wh_m2  = Σ(Globalstrahlung_W/m²)     × 1h
GTI_Summe_Wh_m2        = Σ(global_tilted_irradiance) × 1h        # ab v3.20.0
```

**Batterie-Vollzyklen (v3.22.0 verschärft):**

```
Δ_SoC_Summe   = Σ |SoC[h] - SoC[h-1]|     für h = 1..23,
                AUSSCHLIESSLICH aus Investitionen mit typ == "speicher"
Vollzyklen    = Δ_SoC_Summe / 200          # 0→100→0 = 200 % = 1 Vollzyklus
```

> **E-Auto-SoC-Trennung:** Vor v3.22.0 nahm `_get_soc_history` den **ersten** `live.soc`-Sensor aus den Investitionen — bei Anlagen mit E-Auto landete dessen SoC zuerst in der Liste, der eigentliche stationäre Speicher wurde nicht angefasst. Folge: `batterie_vollzyklen` reflektierten den ΔSoC des Autos. Seit v3.22.0 filtern beide Selektions-Pfade (`_get_soc_history`, Bulk-Fetch in `backfill_from_statistics`) auf `inv.typ == "speicher"`. **Nach Update auf v3.22.0:** einmal „Verlauf nachberechnen + überschreiben" auslösen.

**Performance Ratio (v3.20.0 auf GTI):**

```
Theoretisch_kWh   = GTI_Wh_m2 × kWp / 1000     # ab v3.20.0
Performance_Ratio = PV_Ertrag_kWh / Theoretisch_kWh

# Vor v3.20.0 (deprecated, GHI-basiert):
# Theoretisch_kWh = Strahlung_Wh_m2 × kWp / 1000   # horizontale Globalstrahlung
```

Bei Multi-String-Anlagen werden GTI-Werte pro Orientierungsgruppe parallel abgerufen und kWp-gewichtet kombiniert (analog Live-Wetter-Pfad). Ohne gemappte PV-Module bleibt PR bewusst `None` statt einen verzerrten GHI-Wert zu melden.

> **Validation Winterborn 2025-12-28:** GHI 1317 Wh/m² vs. GTI Süd35° 3358 Wh/m² (Faktor 2.55×). PR vorher 2.16 (physikalisch unmöglich), nachher 0.85 (plausibel für einen kalten Wintertag). Betrifft historische `TagesZusammenfassung.performance_ratio`, `MonatsAuswertungResponse.performance_ratio_avg` und die PR-Spalte im PDF-Jahresbericht — **nach Update einmalig „Verlauf nachberechnen + überschreiben" auslösen**. PV-kWh-Werte selbst bleiben unverändert.

**§51 EEG (Negativpreis-Analyse):**

```
boersenpreis_avg              = Ø(boersenpreis_cent[h])
boersenpreis_min              = min(boersenpreis_cent[h])
neg_stunden                   = Anzahl h mit boersenpreis_cent[h] < 0
einspeisung_neg_preis_kwh     = Σ(Einspeisung_kWh[h]) für h mit boersenpreis_cent[h] < 0
```

Datengrundlage für die §51-Sektion in Auswertung → Energieprofil → Monat (siehe Bedienungs-Handbuch §5.8).

**WP-Kompressor-Starts (v3.24.0, #136):**

```
TagesEnergieProfil.wp_starts_anzahl[h]   = snap_starts[h] - snap_starts[h-1]
                                            # Summe aller WP-Investitionen pro Stunde
TagesZusammenfassung.komponenten_starts  = {"wp_starts_anzahl": {"<inv_id>": <int>, ...}}
                                            # Tages-Differenz pro WP-Investition
```

Architektur trennt Counter-Felder strikt von kWh-Feldern in `KUMULATIVE_COUNTER_FELDER`, damit reine Counter nicht versehentlich in die Energie-Bilanz fließen. Vollbackfill aus HA Long-Term Statistics greift für Tages-Summen (Faktor 1.0 statt 0.001 bei unbekannter Einheit). Stunden-Detail wird ab Live-Erfassung gefüllt.

**Day-Ahead-Stundenprofil-Snapshot (v3.23.4, intern):**

Zwei JSON-Felder in `TagesZusammenfassung` (`pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil`) speichern den ersten OpenMeteo-/Solcast-Forecast des Tages als 24-Werte-Liste in kWh (Backward-Slot). First-write-wins: spätere Aufrufe am selben Tag überschreiben das Profil nicht. Reine Hintergrund-Datensammlung für künftige Diagnostik (Korrekturprofil-Konzept). Speicher ~80 KB/Jahr/Anlage.

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

*Letzte Aktualisierung: April 2026 (v3.24.1)*
