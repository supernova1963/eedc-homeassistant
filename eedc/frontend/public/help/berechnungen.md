# eedc Berechnungsreferenz

**Version 4.0** | Stand: 2026-07-25

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

**Legacy-Felder (NICHT neu befüllen):**
- `Monatsdaten.batterie_*` - Nutze `InvestitionMonatsdaten` (Speicher)
- `Monatsdaten.pv_erzeugung_kwh` - **kein Schreibziel** für neuen Code (Pro-Modul-Werte gehören in `InvestitionMonatsdaten`) und seit 2026-07-29 auch **keine allgemeine Lesequelle** mehr: das Feld trägt den manuell erfassten oder importierten **PV-Gesamtwert** eines Monats und ist **ausschließlich Eingang** des Read-time-SoT `core/berechnungen/pv_verteilung.py` (`resolve_pv_je_modul`). Der füllt damit die Lücken der Module ohne eigenen Wert und kennzeichnet sie als gerechnet. Wer nur einen Gesamt-Sensor hat, pflegt weiterhin ausschließlich hier. Jede einzelne Berechnung liest die Pro-Modul-Schicht bzw. deren Summe — nie das Feld selbst. Ladepfad: `services/pv_monatswerte.py`.

> **Seit 2026-07-31 ist die Lesequelle nicht mehr `lade_pv_je_monat`, sondern eine Schicht darüber:** `services/monats_fakten.py::lade_monats_fakten` (ADR-002/**P10**, [Konzept](KONZEPT-MONATS-FAKTEN.md)). Sie liefert die **ganze** Monatszeile kanonisch aufgelöst — die PV ist darin ein Feld (`erzeugung.pv_module_kwh` bzw. `erzeugung.pv_kwh`), daneben stehen Zähler, Speicher, E-Mobilität, Wärmepumpe, Sonstiges, Tarif, §51 und die Verbrauchs-Kennzahlen. Sie **ruft** `lade_pv_je_monat` (die P7-Regel bleibt unverändert), wendet aber zusätzlich **einmal** alle Zeitfilter (`aktiv` · Anschaffung · Stilllegung) und den Dienstwagen-Filter an. Wer eine abgeleitete Monatsgröße auswertet, nimmt sie von dort; `lade_pv_je_monat` direkt zu rufen bleibt richtig, wo **nur** die Pro-Modul-PV gebraucht wird (String-Vergleich, PV-Diagnose). Ausgenommen sind Schreib-, Import- und Checker-Pfade — die Schicht ist reines Lesen.
>
> Die Migration läuft sichtweise (`KONZEPT-MONATS-FAKTEN.md` §10): umgehängt sind **Aussichten**, **Jahresbericht-PDF** und der **Investitions-ROI** (S2). Der baumweite Wächter wird mit S5 scharf gestellt.

> **Achtung, ein Name für zwei Größen:** `pv_erzeugung_kwh` bezeichnet **drei verschiedene Dinge**, je nachdem, wo es steht — die **DB-Spalte** `Monatsdaten.pv_erzeugung_kwh` (manuelles Gesamt-Aggregat, s. o.), den **Schlüssel in `InvestitionMonatsdaten.verbrauch_daten`** (Erzeugung *dieses einen* Moduls) und das **Response-Feld** von `/monatsdaten/aggregiert` (PV-Module **+** Balkonkraftwerk). Der Identifier bleibt bewusst unverändert — er ist zugleich MQTT-Topic-Segment, CSV-Spaltenname und Backup-Feld. Siehe [Glossar](GLOSSAR.md#energie--bilanzen).

### Schicht 2: Berechnungslogik

| Datei | Funktionen | Beschreibung |
|-------|-----------|-------------|
| `services/monats_fakten.py` | `lade_monats_fakten()`, `finanz_zeile_eingabe()`, `kennzahlen_aus_fakten()` | **Eingabe-Aufbereitung, keine Formel** (ADR-002/P10): löst die Monatszeile einmal auf und ruft die SoT-Helfer. Vorschaltet jeder aggregierenden Lese-Sicht |
| `core/calculations.py` | `berechne_monatskennzahlen()`, `berechne_speicher_einsparung()`, `berechne_eauto_einsparung()`, `berechne_waermepumpe_einsparung()`, `berechne_roi()`, `berechne_ust_eigenverbrauch()` | Reine Berechnungsfunktionen ohne DB-Zugriff |
| `api/routes/cockpit.py` | 6 Endpoints | Aggregation aller Daten für Dashboard |
| `api/routes/aussichten.py` | 4 Endpoints | Prognosen und Finanzberechnungen |
| `api/routes/investitionen.py` | ROI-Dashboard | PV-System-Gruppierung und ROI pro Komponente |
| `api/routes/strompreise.py` | `lade_tarife_fuer_anlage()` | Multi-Tarif-Lookup mit Fallback |
| `utils/sonstige_positionen.py` | `berechne_sonstige_summen()` | Strukturierte Erträge/Ausgaben |
| `services/energie_profil_service.py` | `aggregate_day()`, `rollup_month()`, `backfill_range()` | Tages-Aggregation + Monats-Rollup |

### Schicht 3: Frontend-Anzeige

Die API-Endpoints sind unverändert; die **Sicht** (Spalte „Wo in v4") folgt der neuen Achsen-Navigation (Cockpit = Zeit-Achse, Komponenten = Was-Achse, Auswertungen = Wie-Achse — siehe [Bedienung](HANDBUCH_BEDIENUNG.md#1-navigation--grundprinzip)):

| Wo in v4 | API-Endpoint | Angezeigte Kennzahlen |
|-------|-------------|----------------------|
| [Cockpit → Monat/Jahr](HANDBUCH_BEDIENUNG.md#2-cockpit--die-zeit-achse) | `GET /api/cockpit/uebersicht/{id}?jahr=` | Autarkie, EV-Quote, Netto-Ertrag, Rendite, CO2 |
| [Auswertungen → Prognose](HANDBUCH_BEDIENUNG.md#43-prognose-genauigkeit-gegen-ist) | `GET /api/cockpit/prognose-vs-ist/{id}?jahr=` | Performance Ratio pro Monat |
| [Cockpit → Jahr/Gesamt](HANDBUCH_BEDIENUNG.md#24-jahrgesamt) · [Auswertungen → CO₂](HANDBUCH_BEDIENUNG.md#4-auswertungen--die-wie-achse) (§4.4) | `GET /api/cockpit/nachhaltigkeit/{id}` | CO2-Zeitreihe (Block „CO₂-Bilanz"), Äquivalente, Amortisation — **die eine CO₂-Quelle beider Sichten** ([§3.8](#38-co2-bilanz)) |
| [Komponenten](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse) (je Typ) | `GET /api/cockpit/komponenten-zeitreihe/{id}` | Speicher-Effizienz, WP-JAZ, E-Auto PV-Anteil |
| [Komponenten → PV-Anlage](HANDBUCH_BEDIENUNG.md#32-pv-anlage) | `GET /api/cockpit/pv-strings/{id}?jahr=` | SOLL vs IST pro String |
| [Auswertungen → ROI](HANDBUCH_BEDIENUNG.md#42-roi) | `GET /api/investitionen/roi/{id}` | ROI%, Amortisation pro System |
| [Auswertungen → Tabelle](HANDBUCH_BEDIENUNG.md#45-tabelle-werte-werkbank) | `GET /api/monatsdaten/aggregiert/{id}` | Spalten-Explorer, Vorjahres-Delta |
| [Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) | `GET /api/aussichten/kurzfristig/{id}` | 7-Tage PV-Prognose + SFML-Linie |
| [Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) | `GET /api/aussichten/langfristig/{id}` | 12-Monats-Prognose |
| [Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) | `GET /api/aussichten/trend/{id}` | Degradation, Jahresvergleich |
| [Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen) | `GET /api/aussichten/finanzen/{id}` | Amortisations-Fortschritt, Prognose |

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
Erzeugung_gesamt    = PV_Erzeugung + BKW + sonstige_Erzeuger   (hinter dem Zähler)
Direktverbrauch     = max(0, Erzeugung_gesamt - Einspeisung - Batterie_Ladung)
Eigenverbrauch      = Direktverbrauch + Batterie_Entladung + V2H_Entladung
Gesamtverbrauch     = Eigenverbrauch + Netzbezug
EV-Quote (%)        = Eigenverbrauch / Erzeugung_gesamt * 100   (wenn Erzeugung > 0)
Autarkie (%)        = Eigenverbrauch / Gesamtverbrauch * 100    (wenn GV > 0)
Spez. Ertrag        = PV_Erzeugung / Leistung_kWp              (kWh/kWp, NUR PV; zwei Varianten, s. u.)

Einspeise-Erlös (EUR)    = (Einspeisung - Einspeisung_neg_Preis) * Einspeisevergütung / 100
Netzbezug-Kosten (EUR)   = Netzbezug * Netzbezug_Preis / 100 + Grundpreis
Arbeitspreis-Kosten (EUR)= Netzbezug * Netzbezug_Preis / 100            (ohne Grundpreis, reiner Ausweis)
EV-Ersparnis (EUR)       = Eigenverbrauch * Netzbezug_Preis / 100
Netto-Ertrag (EUR)       = Einspeise-Erlös + EV-Ersparnis
CO2-Einsparung (kg)      = PV_Erzeugung * 0.38               (VERALTET — s. Kasten)
```

> **⚠ Die CO₂-Zeile dieser Funktion ist NICHT der Kanon.** `berechne_monatskennzahlen`
> trägt noch die vor DI-2 gültige Formel (Erzeugung statt Eigenverbrauch, ohne WP und
> E-Mobilität). Sie wird ausschließlich von `GET /api/monatsdaten/{id}` als
> `kennzahlen.co2_einsparung_kg` ausgeliefert und dort **von keiner Sicht gelesen**
> (gemessen 2026-07-31: das Feld existiert im Client-Typ `MonatsKennzahlen`, es gibt
> keinen Leser). Sie bewegt also keine angezeigte Zahl — sie steht hier, damit niemand
> sie für die gültige Definition hält. Der Kanon ist **§3.8**.

> **Zwei Kostenzahlen, eine Rechnung — `netzbezug_kosten_euro` vs.
> `netzbezug_arbeitspreis_kosten_euro`:** verrechnet wird immer die **Gesamtsumme
> inkl. Grundpreis**; sie ist das, was auf der Rechnung steht, und hängt an T-Konto,
> Netto-Ertrag und den Finanz-Sichten. Daneben steht der reine **Arbeitspreis-Anteil** als
> *Ausweis* — kein zweiter Kostenposten. Er gehört überall dorthin, wo eine Sicht kWh und €
> so nebeneinander stellt, dass ein Leser sie dividiert: dann muss der Ø-Preis herauskommen.
> Die Ø-Preis-Kachel in Cockpit → Monat tat das mit den Gesamtkosten nicht (559 kWh ·
> 210,45 € ⇒ 37,6 ct statt 33 ct; Forum simon42 #89667). **Faustregel:** neben einem
> **Preis** steht der Arbeitspreis-Anteil, in einer **Kostenaufstellung** die Gesamtsumme.
>
> **Welcher Preis gilt:** bei einem flexiblen Tarif der **verbrauchsgewichtete
> Monatsdurchschnitt** (`Monatsdaten.netzbezug_durchschnittspreis_cent`), sonst der
> Tarif-Arbeitspreis. Das gilt für Netzbezug-Kosten, EV-Ersparnis und — ohne eigenen
> WP-Tarif — auch für die WP-Ersparnis. Bis v4.0.6 nahm der **laufende** Monat hier
> den Tarifpreis, während Vorjahres-Vergleich und die per-Investition-Details schon den
> Durchschnitt nahmen; derselbe Monat trug damit je nach Sicht zwei Beträge.

**§51 EEG im Einspeise-Erlös:** `Einspeisung_neg_Preis` sind die kWh, die in Stunden
mit negativem Börsenpreis eingespeist wurden — für betroffene Anlagen entfällt dafür
die Vergütung (Herleitung des Volumens: Abschnitt „§51 EEG (Negativpreis-Analyse)"). Ist
die Anlage nicht §51-pflichtig oder liegt keine Strompreis-Mitschrift vor, ist der
Wert `null` und es wird nichts abgezogen. Der Abzug gilt **überall** gleich:
Backend-SoT `core/berechnungen/einspeise_erloes.py` und der Frontend-Spiegel
`lib/calculations.ts::calcEinspeiseErloes` (Auswertungen → Finanzen + Tabelle).

**Netzpunkt-Bilanz (Erzeugung_gesamt):** Am EINEN Netzanschluss messen die Zähler
(`Einspeisung`/`Netzbezug`) die Summe **aller** dahinter liegenden Erzeuger. Deshalb
geht in die Eigenverbrauchs-/Autarkie-Ableitung die **Gesamterzeugung** ein —
PV-Module + Balkonkraftwerk + **sonstige Erzeuger** (z. B. Mini-BHKW). Würde ein
Erzeuger ignoriert, drückte der gemessene Einspeise-Zähler `Direktverbrauch` zu
niedrig (auf 0 geklemmt) und Autarkie/EV-Quote würden unterschätzt. SoT-Helper:
`core/berechnungen/energie.erzeugung_hinter_zaehler_kwh` (ADR-001).

**Die Größe ist ein eigenes Response-Feld, kein Rechenschritt je Sicht.** `/monatsdaten/aggregiert`
liefert sie als `erzeugung_hinter_zaehler_kwh` mit — vorher summierte jede Sicht die Einzelteile
selbst, und genau dort entstand die Drift (zwei unterschiedlich hohe Stapel im Komponenten-Hub).
Die Felder derselben Antwort:

| Feld | Bedeutung |
|---|---|
| `pv_module_kwh` | nur die PV-Module (bis v4.0.0 `pv_anlage_kwh` — irreführend, weil „PV-Anlage" im Produkt sonst die *ganze* Anlage inklusive Balkonkraftwerk meint) |
| `bkw_kwh` | nur Balkonkraftwerk(e) |
| `sonstige_erzeugung_kwh` | „Sonstiges" mit Kategorie *Erzeuger* (z. B. Mini-BHKW) |
| `pv_erzeugung_kwh` | `pv_module_kwh + bkw_kwh` — **nicht** die gleichnamige DB-Spalte (s. [Schicht 1](#schicht-1-rohdaten-eingabe)) |
| **`erzeugung_hinter_zaehler_kwh`** | Σ **aller** drei Erzeuger-Felder = der Nenner der EV-Quote |

**Auch die PDF-Berichte rechnen so.** Der Jahresbericht leitete Eigenverbrauch, Autarkie und
EV-Quote bis v4.0.0 allein aus der PV-Erzeugung ab, während der Einspeise-Zähler daneben die Summe
**aller** Erzeuger misst — bei einer Anlage mit sonstigem Erzeuger fielen die Werte dort zu niedrig
aus und widersprachen dem Cockpit. Seit v4.0.1 nutzen alle Bilanz-Pfade (Cockpit, Monatsbericht,
Live, PDF-Jahresbericht, HA-Sensoren) dieselbe Größe.

**Spezifischer Ertrag — zwei Größen, ein Formelname.** Die Roh-Division oben ist nur eine davon:

| Größe | Rechenweg | Wo |
|---|---|---|
| **Annualisiert** | saisonal gewichtet (PVGIS-Monatsverteilung) und mit der im jeweiligen Monat **tatsächlich installierten** Leistung — vergleichbar über verschieden lange Zeiträume | Cockpit, HA-Export, Community-Vergleich (SoT `core/berechnungen/spez_ertrag.py`) |
| **Zeitraum** | Erzeugung des Berichtszeitraums ÷ Anlagen-Nennleistung, ohne Normierung — summiert sich über mehrere Jahre auf | PDF-Jahresbericht (dort seit v4.0.1 als **„Spez. Ertrag (Zeitraum)"** beschriftet), Monatsbericht |

Beide Zahlen sind richtig, sie beantworten verschiedene Fragen. Eine Angleichung der Rechnung steht
aus, weil dieselbe Kennzahl im Community-Vergleich steht.

**Achsen-Trennung (bewusst):** PV-**eigene** Kennzahlen (spez. Ertrag, Performance-
Ratio, SOLL/IST, kWp) nutzen **nur** `PV_Erzeugung`, nicht `Erzeugung_gesamt` — ein
sonstiger Erzeuger ist energetisch Erzeuger, aber kein PV-Modul. Ebenso bleibt
**CO₂/Wirtschaftlichkeit quellenspezifisch**: ein brennstoffbasierter Erzeuger (BHKW)
spart kein CO₂, sondern emittiert, und hat Brennstoffkosten — er bekommt daher keine
PV-artige CO₂-Ersparnis (bewertet als „nicht bewertet", bis ein eigenes BHKW-Modell
existiert). **Insel-Anlagen** (kein Netzanschluss, kein Bezug/keine Einspeisung)
fallen nicht unter diese Bilanz — das ist ein Anlagen-Merkmal (eigenes KZ, geplant).

**Messpunkt der Sensoren (DC vs. AC):** Die Bilanz rechnet mit den Werten, die die Geräte
liefern — sie kann nicht wissen, **wo** gemessen wurde. Viele Hybrid-Wechselrichter (z. B.
E3DC) melden PV-Erzeugung und Speicher-Ladung/-Entladung **DC-seitig** (Modul- bzw.
Batterieklemme), Einspeisung und Netzbezug dagegen **AC-seitig** (Zähler). Dann stecken die
Wandlungsverluste der PV- und Speicherstrecke im bilanzierten `Gesamtverbrauch`: er liegt
typischerweise **3–5 % der Erzeugung** über dem „Hausverbrauch", den das Herstellerportal
ausweist — das rechnet seine Verluste intern heraus. Keiner der beiden Werte ist falsch, sie
beantworten verschiedene Fragen: eedc „was musste die Anlage liefern" (**inklusive** Verluste
— die richtige Basis für Autarkie, EV-Quote und Wirtschaftlichkeit, denn erzeugt und bezahlt
werden muss auch der Verlust), das Portal „was zogen die Verbraucher".

*Diagnose-Rezept* für einen abgeschlossenen Tag:

```
Residuum = PV + Netzbezug + Entladung − Einspeisung − Ladung − Hausverbrauch(Portal)
```

Liegt das Residuum bei wenigen Prozent der Erzeugung, ist es der Verlustanteil und kein
Rechenfehler. Gemessenes Beispiel (E3DC, 03.07.2026, Issues #200/#340): 60,83 + 0,31 + 7,17
− 48,19 − 7,59 − 10,26 = **2,27 kWh = 3,7 % der Erzeugung** — davon 0,42 kWh Batterie-
Rundlauf (DC), der Rest DC→AC-Wandlung. Da die Verluste mit dem Durchsatz skalieren, liegt
ein ertragsstarker Tag über dem Monatsschnitt.

**Bewusst kein Hausverbrauchs-Sensor:** eedc bietet **kein** Mapping eines fremden
Hausverbrauchs-Sensors an. „Hausverbrauch" ist je Hersteller anders definiert (Verluste drin
oder herausgerechnet, Wallbox enthalten oder nicht) — zwei Definitionen derselben Kennzahl
würden Cockpit, Berichte und Community-Vergleich auseinanderlaufen lassen. Die Bilanz aus
Zähler- und Komponentenwerten bleibt die eine Wahrheit; die Differenz wird erklärt, nicht
durch eine zweite Datenquelle ersetzt.

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

> **Kanonisches Finanz-Aggregat (SoT `core/berechnungen/finanz_aggregat.py`):** Netto-Ertrag,
> Einspeise-Erlös, EV-/BKW-Ersparnis und Sonstige-Netto werden **per-Monat** gerechnet und über die
> sichtbaren Monate summiert (nicht mit einem Ø-Preis) — bei Flex-Tarifen (Tibber/aWATTar/EPEX) laufen
> Monats-Preis und EV/Netzbezug-Split sonst auseinander (#326). Der **naive** `netto_ertrag_euro`
> = Einspeise-Erlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto; Sites mit Zusatzlogik (Cockpit
> zieht `USt_Eigenverbrauch` ab) bauen den Netto-Ertrag aus den Einzel-Komponenten selbst zusammen.

> **G19-1 — Sonstige Positionen auf Anlage-Ebene (ab v4.0):** `Sonstige-Netto` umfasst jetzt **auch**
> die auf **Anlage-Ebene** (nicht nur pro Komponente) erfassten Positionen — siehe [§3.10](#310-sonstige-positionen).
> Sie fließen als eigene T-Konto-Zeilen „Anlage — Sonstige Erträge/Ausgaben" in **fünf** Anlage-Finanz-
> Pfade (Cockpit-Monat/-Jahr, Übersichts-Netto, PDF-Jahresbericht, HA-Export-Netto-Sensor). Wichtig für
> Bestandsdaten: die früher rein informativen `Monatsdaten.sonderkosten_euro` (die **nirgends** rechneten)
> werden migriert und wirken ab v4.0 in den Finanz-Summen. **Bewusste Inkonsistenz:** Die Aussichten-
> und ROI-Pfade (investitions-zentrierte Amortisation, s. [§3.6](#36-roi--amortisation) / [§4.4](#44-finanz-prognose--amortisation))
> sehen die **Anlage-Positionen NICHT** — sie fließen dort nicht in Bisherige-Erträge/Amortisation ein.
> Das ist so dokumentiert, kein Bug (offener Entscheid unter „Kennzahlen-Drift-Inventur").

> **Grundgebühr / Zählergebühr (K3, ab v4.0):** Die **Grundgebühr** (`Strompreis.grundpreis_euro_monat`)
> steckt bereits in den Netzbezugskosten (s. [§3.1](#31-energie-bilanz-monatskennzahlen)); der Cockpit-Finanz-Teaser
> (Monat + Jahr) weist sie zusätzlich **nachrichtlich** aus („davon Grundgebühr: … €"). Die **Zählergebühr**
> (neues optionales Tarif-Feld `Strompreis.zaehlergebuehr_euro_jahr`) wird im Jahr-Modus als „Zählergebühr:
> … €/Jahr (nachrichtlich)" gezeigt, aber **nicht** in Kosten/Netto verrechnet — eine Einrechnung wäre ein
> eigener Kennzahlen-Entscheid. `baueJahrAlsMonat`: Grundgebühr = Σ, Zählergebühr = letzter Wert.

> **Cockpit-Finanzen-Block = Komponenten-Finanz-Tabelle (G20-1, ab v4.0):** Der Finanzen-Block in
> Cockpit-Monat/-Jahr zeigt **eine Zeile je Komponente** (Reihenfolge = Typ-SoT) mit den Spalten
> **Erträge** (tatsächliche Zahlungsflüsse) · **Einsparungen** (kalkulatorisch/vermiedene Kosten) ·
> **Aufwand** (inkl. anteilig umgelegter Betriebskosten, Speicher-Zeile inkl. Netzladungs-Kosten) ·
> **Saldo**; die **Summenzeile ist die Block-Kopf-Kennzahl** (Kopf == sichtbare Summe). Diese Tabellen-
> Summe ist bewusst eine **dritte, komponenten-attribuierte Netto-Semantik** neben (a) dem kanonischen
> `netto_ertrag_euro` (PV-Anlage: Einspeise-Erlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto) und
> (b) `gesamtnettoertrag_euro` (Einspeise-Erlös + EV-Ersparnis + WP-Ersparnis + E-Mob-Ersparnis −
> Netzbezug-Kosten). Sie fasst die Beiträge **aller** Komponenten zusammen und wird **rein aus den
> vorhandenen T-Konto-Posten** gebaut — **keine neue Berechnung**: `netto_ertrag_euro`, der HA-Export-
> Sensor und der PDF-Jahresbericht bleiben unangetastet. Netzbezug-Kosten und Grundgebühr stehen
> nachrichtlich (nicht im Saldo). Zusätzlich weist der Block als **zweite Perspektive** die Zeile
> **„Ergebnis nach Stromrechnung" = Tabellen-Saldo − Netzbezug-Kosten** (G20-4) aus — das Haushalts-
> ergebnis; der Komponenten-Saldo bleibt davon unberührt und ist weiterhin die Kopf-Kennzahl. *(Die Vergleichs-Asymmetrie
> `gesamtnettoertrag` Monat vs. Vorjahr ist ein offener Punkt der Kennzahlen-Drift-Inventur, kein Bug.)*

> **Anschaffungsdatum-Grenze auch im Vorjahres-Vergleich (DI-5/DI-2-C):** Der Trend-Pfeil zum Vorjahr
> zieht die Vorjahres-Werte **symmetrisch** zum laufenden Monat — WP- und E-Mob-Ersparnis fließen nur
> für im jeweiligen Vorjahresmonat **aktive** Komponenten ein (`ist_aktiv_im_monat`, also innerhalb
> Anschaffungs-→Stilllegungs-Fenster), und die energieseitige Vorjahres-Aggregation ist gleich gefiltert.
> Dienstwagen (`ist_dienstlich`) bleiben in beiden Jahren aus den E-Mob-Bilanzen. So vergleicht der
> Pfeil gleiche Komponenten-Mengen, statt Alt-Werte vor der Anschaffung mitzuzählen.

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

**Hinweis:** Dienstliche E-Autos/Wallboxen (`ist_dienstlich = true`) werden NICHT in die E-Mob-Ersparnis eingerechnet. Deren Ladekosten fließen als kalkulatorische Ausgaben in `sonstige_ausgaben_gesamt` — Formel und Begründung stehen in §3.10 „Sonstige Positionen" unter **Dienstliche Ladekosten** — der PV-Anteil zählt dort zum **Netzbezugspreis**, nicht zur Einspeisevergütung.

> **G20-2 — Aggregat bei mehreren E-Autos = Σ der Einzel-Fahrzeuge:** Die Gesamt-E-Mob-Ersparnis wird als **Summe der pro Fahrzeug** gerechneten Ersparnisse gebildet — jedes E-Auto mit seinem **eigenen** Vergleichsverbrauch (L/100 km) und Benzinpreis. Sie ist NICHT ein Einmal-Lauf über die Gesamt-Kilometer mit dem Parametersatz des ersten Fahrzeugs (das überschätzte die Ersparnis, sobald zwei E-Autos unterschiedliche Vergleichsverbräuche hatten). Bei genau **einem** E-Auto ist das Ergebnis unverändert. Die Per-Fahrzeug-Zeilen (T-Konto) rechneten schon immer je Fahrzeug korrekt; nur das aggregierte Cockpit-Feld ist jetzt symmetrisch dazu.

**Kanonische Heimladungs-Quelle (ab Phase 2a):** `Ladung_gesamt` und `Ladung_PV` der Heimladung kommen strukturell aus **genau einer** Quelle: existiert eine Wallbox-Investition mit Heimladung, ist sie die Quelle (Infrastruktur misst den Stromfluss am Ladepunkt); ohne Wallbox (Steckerlader/Schuko) liefert das E-Auto die Werte. Bei mehreren Wallboxen ist die Heimladung die **Summe** aller Wallbox-Ladepunkte. Diese Regel ist deterministisch (existiert eine Wallbox?), nicht magnitudenabhängig — der frühere Pool-/„größere Heimladung gewinnt"-Mechanismus entfällt. Die km-anteilige Aufteilung auf mehrere Fahrzeuge (Attribution) bleibt unverändert. Zentraler Helper: `get_emob_heimladung_canonical()`.

**Ø Verbrauch (kWh/100 km) — Quellen-Vorrang:** Die Effizienz-KPI in E-Auto-Dashboard, Monatsbericht und Komponenten-Auswertung kommt aus **einem** Helper (`core/berechnungen/emob.py`, `eauto_effizienz_100km`):

```
1. gemessener Fahrverbrauch:  verbrauch_kwh ÷ km × 100     (Vorrang, exakt)
2. sonst Näherung aus Ladung: Ladung_gesamt ÷ km × 100     (Fallback)
3. sonst:                     —   (nie 0,0 erfinden)
```

Die Ladungs-Näherung **überschätzt** den echten Fahrverbrauch (AC-Ladung an der Wallbox enthält Ladeverluste ~10–15 %, blendet SoC-Drift + nicht erfasste Fremdladung aus) — in der UI als „≈ aus Ladung (inkl. Ladeverluste)" gelabelt. Vorteil: funktioniert auch ohne Verbrauchssensor (den die wenigsten Fahrzeuge liefern). Alle Read-Sites zeigen denselben Wert; das Aggregat rechnet über die **Summen** (Σverbrauch / Σladung / Σkm), nicht über das Mittel der Monats-Prozente. Symmetrie abgesichert durch `test_emob_readsite_symmetrie.py`.

**Hinweis Kraftstoffpreis (ab v3.17.0):** Im Cockpit werden weiterhin die hardcodierten Defaults verwendet. In der **Finanz-Prognose** ([Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen)), im **HA-Sensor-Export** und im **PDF-Finanzbericht** wird stattdessen pro Monat der echte Kraftstoffpreis aus `Monatsdaten.kraftstoffpreis_euro` verwendet (Quelle: EU Weekly Oil Bulletin). Fallback auf den statischen `benzinpreis_euro`-Parameter der Komponente wenn kein Monatswert vorhanden.

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
| `kapazitaet_kwh` | `get_speicher_nutzbare_kapazitaet_kwh(inv)` — **netto**, still auf brutto zurückfallend (A31-2/E17, s. u.). Greift nur im Prognose-Modus; mit gemessener Entladung übernimmt der Spread-Service und liest gar keine Kapazität. |
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

#### Vollzyklen — eine Definition für alle Sichten

```
Vollzyklen = Entladung_kWh ÷ Kapazität_brutto_kWh
```

**SoT:** `core/berechnungen/speicher.py::vollzyklen`. Alle Sichten rufen ihn auf —
Komponenten-Hub (`investitionen/dashboards.py`), Cockpit Tag (`energie_profil/tage_werte.py`) und
Monat/Jahr (`aktueller_monat.py`), PDF-Jahresbericht, HA-Sensor `speicher_zyklen`.
Gewächtert von `backend/tests/test_speicher_zyklen_kapazitaets_basis.py` (inkl. Drei-Pfad-Symmetrie)
und `test_tage_werte_symmetrie.py`.

**Warum die Entladung:** Ein Vollzyklus meint die einmal *entnommene* Kapazität — die Größe, auf die
sich Hersteller-Garantien beziehen, und unabhängig von den Wandlungsverlusten des Ladepfads. Sie ist
außerdem ein Energiedurchsatz und damit über Tag → Monat → Jahr additiv.

**Warum Brutto im Nenner:** `nutzbare_kapazitaet_kwh` ist optional und meist nicht gepflegt; ein
Nenner, der je nach Pflegezustand wechselt, wäre schlimmer als ein durchgehend leicht konservativer
Wert. Im HA-Export ist das Netto-Feld reiner **Fallback**, falls die Brutto-Kapazität fehlt — die
Lese-Reihenfolge dort ist bewusst brutto → netto und bleibt es auch nach A31-2.

#### Brutto oder netto — wann welche Kapazität gilt

Ein Speicher trägt zwei Kapazitäten, beide im Formular. Die Trennlinie läuft **nicht** zwischen
„genau" und „ungefähr", sondern zwischen zwei Fragen:

| Frage | Kapazität | Warum | Stellen |
| --- | --- | --- | --- |
| **Wie oft wurde der Speicher umgeschlagen?** | **brutto** (`kapazitaet_kwh`) | Bezugsgröße der Hersteller-Garantie; ein Nenner, der am Pflegezustand hängt, macht dieselbe Anlage unvergleichbar | Vollzyklen (alle Sichten), graue Last, Community-Datensatz, Anzeige/Beschreibung der Komponente |
| **Wie viel Energie geht durch den Speicher?** | **netto** (`nutzbare_kapazitaet_kwh`, still auf brutto zurückfallend) | Simuliert bzw. prognostiziert wird eine *durchgefahrene Menge* — und durch den Speicher geht nur der nutzbare Hub | Tages-Vorschau „Speicher voll um …" (Planungs-Tab **und** HA-Sensor `eedc_speicher_voll_um`), Wirtschaftlichkeits-**Prognose** ohne IST-Aggregat, η-SoC-Delta |

**SoT netto (seit A31-2):** `core/investition_kennwerte.py::get_speicher_nutzbare_kapazitaet_kwh` —
netto, sonst brutto, sonst `None`. Der Brutto-Fallback ist **still** (Entscheidung **E17**): kein
Hinweis, keine Kennzeichnung, **kein P4-Fall**. Der Brutto-Wert ist nicht *unvollständig*, er ist die
andere gültige Lesart derselben Größe; die Zahlenänderung aus A31-2 trifft deshalb ausschließlich
Anlagen, die das optionale Feld bewusst gepflegt haben. Die Leserichtung geht nur netto → brutto und
**nie** zurück — ein Brutto-Helper mit Netto-Fallback wäre genau die Verwechslung, die die Vollzyklen
wieder vom Pflegezustand abhängig machte.

**Nebenwirkung der Vorschau, die dazugehört:** dieselbe Simulation liefert auch Einspeisung,
Eigenverbrauch und Autarkie des Vorschautags. Ein kleinerer Puffer nimmt weniger Überschuss auf —
mehr geht ins Netz, weniger bleibt im Haus. Gemessen an der Demo-Anlage (15,4 kWh brutto gegen
13,9 kWh netto, 28.07.–02.08.2026): Einspeisung +0,75 bis +1,08 kWh/Tag, Eigenverbrauch entsprechend
niedriger, Autarkie −1,7 bis −3,2 Prozentpunkte, „Speicher voll" an einem der sechs Tage eine Stunde
früher (die Stundenauflösung verschluckt den Effekt an den übrigen).

**Woher die Kapazität kommt (SoT seit A31-1):** `core/investition_kennwerte.py::get_speicher_kapazitaet_kwh`
— brutto (`kapazitaet_kwh`), nur aus dem `parameter`-JSON, **ohne Default**. Ist nichts gepflegt,
liefert er `None`, und der Aufrufer entscheidet (summieren mit `or 0`, Zahl unterdrücken, Rechnung
auslassen); eine Zahl erfindet er nicht (Entscheidung **E16**, ADR-002/P3-a). Bis dahin stand an drei
Stellen ein `.get(…, 10)`: ein Speicher ohne gepflegte Kapazität bekam still 10 kWh und daraus
Vollzyklen und eine Jahres-Ersparnis (**N127**). Der fehlende Wert wird stattdessen ausgewiesen —
Daten-Checker („Kapazität (kWh) fehlt") und die Antwort selbst (`kapazitaet_fehlt` + Hinweis, P4).

> **Abgrenzung „SoC-Hübe"** (`TagesZusammenfassung.batterie_vollzyklen` = ΣΔSoC ÷ 200): eine andere
> Kennzahl, die reale Lade-Hübe misst und damit als einzige eine 10/90-Fahrweise abbildet (ein voller
> Hub = 160 pp = 0,8). Sie ist ein Bestandsmaß, hängt an einem SoC-Sensor und ist **kein** Ersatz für
> die Vollzyklen. Sichtbar in der Energieprofil-Tagestabelle unter diesem Namen.

> **Historie:** Bis 2026-07-28 rechneten vier von fünf Stellen mit der **Ladung** und nur der
> HA-Sensor mit der Entladung; die Tages-Kachel zeigte sogar die ΔSoC-Größe unter dem Namen
> „Vollzyklen". Auf derselben Anlage standen dadurch Zahlen, die um den Speicher-Wirkungsgrad
> auseinanderlagen (gemessen 10,97 gegen 8,57 bei η 78 %). Kein Test hat das bemerkt — daher jetzt
> der Symmetrie-Test über alle Pfade.

> eedc kennt und braucht keinen Ziel-SOC: Vollzyklen und Wirkungsgrad kommen aus **gemessenen**
> Lade-/Entlademengen. Eine Annahme steckt nur in der Wirtschaftlichkeits-**Prognose**
> (250 Vollzyklen × Brutto-Kapazität, `SPEICHER_ZYKLEN_PRO_JAHR`), die vor dem Vorliegen von
> Messdaten greift, sowie in der Tages-**Vorschau** („Speicher voll um …",
> `core/berechnungen/speicher_simulation.py`), die von 0 bis 100 % der Brutto-Kapazität simuliert —
> wer bei 90 % abriegelt, ist real früher voll. **Beides ist mit v4.0.2 erledigt:** Kapazitäts-SoT
> `get_speicher_kapazitaet_kwh` (`52d3714b`) und die Netto-Umstellung von Tagesvorschau und
> Wirtschaftlichkeits-Prognose (`c5c4437c`), baumweit gewächtert (`5dc3f488`, ADR-002 P3-a).
> **Die Vollzyklen bleiben bewusst brutto** (Kanon `f1644cc8`) — die Netto-Umstellung zieht sie nicht mit.

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

In der **Finanz-Prognose** ([Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen), Backend `aussichten.py`) wird die E-Auto-Ersparnis **pro Monat** mit dem echten Kraftstoffpreis berechnet:

```
Für jeden historischen Monat:
  Benzinpreis = Monatsdaten.kraftstoffpreis_euro       (wenn vorhanden)
              ∨ Investition.parameter.benzinpreis_euro  (Fallback statisch)
  Benzin_Kosten_Monat = km_gefahren / 100 * Vergleich_L_100km * Benzinpreis
  Strom_Kosten_Monat  = ladung_netz_kwh * Netzbezug_Preis / 100   # kanonische Heimladungs-Quelle (Wallbox bzw. E-Auto), s. §3.2

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
η_alt                = alter_wirkungsgrad(Energieträger)   # 0,90 Gas · 0,85 Öl · 1,0 Strom

WP_Kosten            = WP_Strom * Netz_Anteil * Strompreis / 100
Alte_Kosten          = Gesamtwärmebedarf / η_alt * Alter_Preis / 100
                     + alternativ_zusatzkosten_jahr        # Schornsteinfeger / Wartung / Grundpreis Gaszähler

Jahres-Einsparung    = Alte_Kosten - WP_Kosten

CO2_alt               = Gesamtwärmebedarf / η_alt * CO2_Faktor[gas|oel|strom]
CO2_WP                = WP_Strom * Netz_Anteil * 0.38
CO2-Einsparung        = CO2_alt - CO2_WP
```

> **Wirkungsgrad der Altanlage (η_alt):** `Gesamtwärmebedarf` ist **abgegebene Wärme**, nicht Brennstoff — das Eingabefeld heißt „Heizwärmebedarf (kWh/Jahr) — aus Energieausweis", und derselbe Wert wird oben durch die JAZ geteilt (JAZ = Wärme/Strom). Ein Kessel muss dafür `Wärme / η` verfeuern; `Alter_Preis` ist der Preis je kWh **Brennstoff** (so steht er auf der Rechnung). Die Umrechnung macht der Layer-SoT `gas_kosten_altanlage`, die η-Wahl der Resolver `alter_wirkungsgrad` — beide in `core/berechnungen/alternativkosten.py`.
>
> Bis v4.0.1 fehlte die η-Rückrechnung in diesem Pfad: die ROI-Seite wies für dieselbe Wärmepumpe eine niedrigere Ersparnis (und CO₂-Einsparung) aus als Aussichten, HA-Export und WP-Dashboard, die alle über `gas_kosten_altanlage` laufen. **Die fixen Zusatzkosten werden nicht durch η geteilt** — sie sind keine Energie.
>
> **Strom-Direktheizung:** η = 1,0. Eine Widerstandsheizung (Nachtspeicher, Infrarot) setzt Strom verlustfrei in Wärme um; ihr einen Kesselverlust anzurechnen, würde die WP-Ersparnis überhöhen. Die η-Wahl lag vorher an vier Stellen dupliziert vor und kannte diesen Fall nirgends.

> **Split-Klimaanlagen (`wp_art = luft_luft`) durchlaufen diese Rechnung gar nicht.** Ein Luft-Luft-Gerät ersetzt in aller Regel keine Heizung und hat keinen Warmwasserkreis — die gesamte Formel oben hätte damit keinen Gegenstand. Bis v4.0.6 lief sie trotzdem, und weil `Heizwärmebedarf`/`Warmwasserbedarf` Defaults haben (12.000/3.000 kWh, Tabelle unten), kam sie nie ohne Ergebnis heraus: bei den übrigen Standardwerten rund **1.100 €/Jahr** und **2.210 kg CO₂/Jahr** Ersparnis gegen eine Gasheizung, die es nie gab — inklusive Beitrag zu den Anlagen-Summen des ROI-Dashboards. Die ROI-Sicht war damit die einzige, die einen fehlenden Wert konstruierte; alle **gemessenen** Pfade (`services/wp_wirtschaftlichkeit.py`, `co2_wp_ersparnis_kg`, Aussichten, JAZ/COP) haben denselben `wp_waerme_kwh <= 0`-Wächter und liefern 0 bzw. „—". Heute gilt: für `luft_luft` wird **weder Ersparnis noch CO₂-Ersparnis** konstruiert, die ROI-Zeile trägt den Leerwert „—" und `nicht_bewertet`; die Bedarfsfelder werden im Formular nicht mehr angeboten. Die Unterscheidung kommt aus dem SoT-Helper `ist_luft_luft_waermepumpe` — eine Wärmepumpe **ohne** `wp_art` zählt weiter als klassische.

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
| Heizwärmebedarf | `heizwaermebedarf_kwh` | 12000 (bei `luft_luft` **nicht** abgefragt und nicht vorbelegt) |
| Warmwasserbedarf | `warmwasserbedarf_kwh` | 3000 (bei `luft_luft` **nicht** abgefragt und nicht vorbelegt) |
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
| **Jahres-Rendite** | Cockpit, Auswertungen → ROI | Kumul. Ersparnis / Investition * 100 | Wie viel % bereits amortisiert (kumuliert) |
| **ROI p.a.** | Auswertungen → ROI (pro Komponente) | Jahres-Einsparung / Relevante Kosten * 100 | Rendite pro Jahr |
| **Amortisations-Fortschritt** | Auswertungen → Finanzen | Bisherige Erträge / Investition * 100 | Kumulierter Fortschritt |

**Und zwei verschiedene Amortisations-Angaben:**

| Angabe | Wo | Grundlage |
|---|---|---|
| **Amortisation (Ist)** — Dauer **und Break-Even-Jahr** | Auswertungen → ROI | die tatsächlich erfassten Erträge, fortgeschrieben. Anker des Kalenderjahres ist das **früheste Anschaffungsjahr** der Investitionen; ohne gepflegtes Anschaffungsdatum bleibt es beim Jahres-Index ohne Jahreszahl. |
| **Amortisation (Prognose)** | PDF-Finanzbericht | `Gesamt-Kosten ÷ prognostizierte Jahres-Einsparung` — eine Projektion, kein gemessener Verlauf. |

> Verteilen sich die Anschaffungen über mehrere Jahre, ist das ausgewiesene Amortisationsjahr
> **optimistisch** (der Anker ist die *erste* Anschaffung, die Kosten sind die Summe). Der
> Break-Even-Text sagt das dazu.

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

**Auswirkung:** USt wird vom `Netto_Ertrag` abgezogen (im Cockpit und in Auswertungen → Finanzen).

### 3.8 CO2-Bilanz

**Endpoint:** `GET /api/cockpit/nachhaltigkeit/{anlage_id}`
**Sichten:** Cockpit → Jahr/Gesamt, Block „CO₂-Bilanz" (seit 2026-07-31) ·
Auswertungen → CO₂, Blöcke „CO₂-Bilanz & Wirkung" und „CO₂-Amortisation" (seit 2026-07-31).

#### Eine Definition — wer sie bildet und wer sie liest

| Rolle | Ort |
| --- | --- |
| **Bildet** die Zahl (einzige erlaubte Stelle) | `core/calculations.py::berechne_co2_bilanz` (ADR-001, DI-2) |
| **Liefert** sie je Monat aus | `GET /api/cockpit/nachhaltigkeit/{id}` (`co2_pv_kg` · `co2_wp_kg` · `co2_emob_kg` · `co2_gesamt_kg` · `co2_kumuliert_kg`) |
| **Zeigt** sie | Cockpit → Jahr (`v4/JahrCo2Chart.tsx`) · Auswertungen → CO₂ (`v4/AuswertungenCo2V4.tsx`, über `useAuswertungBasis().co2`) · HA-Sensor „CO₂ Einsparung" · PDF-Jahresbericht · WP-Dashboard |
| **Rechnet nicht** | der Client. `CO2_FAKTOR_KG_KWH` darf dort nur noch *angezeigt* werden (`× 1000` → g/kWh); gewächtert von `npm run check:co2-roh` (Baseline 0) |

> **Warum das ausgeschrieben dasteht (N-21, 2026-07-31).** Bis dahin standen im Produkt
> **drei** CO₂-Zahlen für denselben Monat: die kanonische im Cockpit — und zwei
> Überlebende der DI-2-Ablösung, die `Erzeugung × 0,38` rechneten, also auch der
> **eingespeisten** kWh die volle Netzstrom-Vermeidung gutschrieben und weder
> Wärmepumpe noch E-Mobilität kannten (`pages/auswertung/types.ts` im Client,
> `services/energie_profil/tage_werte.py` im Backend — ein Spiegelpaar, Monatstabelle
> und Tagestabelle). Beide sind auf den Kanon umgestellt. Das war **keine
> Definitionsfrage, sondern eine unvollendete Migration.**

> **Jahres-Scope:** Der Endpoint kennt **kein** `?jahr=` und liefert die gesamte Historie —
> der Jahresfilter sitzt in der Sicht (`v4/JahrCo2Chart.tsx::baueJahrCo2ChartDaten` bzw.
> `v4/AuswertungenCo2V4.tsx::baueCo2Monatsreihe`) und greift auf die ganze Monatszeile,
> nicht auf einzelne Serien. **Nicht jahresgebunden** ist
> `co2_kumuliert_kg`: eine Lebensdauer-Größe, die deshalb als eigener Kennwert („CO₂ kumuliert")
> steht und **nicht** als Linie im Jahres-Chart — eine kumulierte Kurve, die im Januar auf halber
> Höhe beginnt, erklärt sich nicht selbst. Aus demselben Grund rechnet die
> **CO₂-Amortisation** (Auswertungen → CO₂, Block ②) immer gegen `co2_kumuliert_kg` der
> gesamten Historie, auch wenn ein Einzeljahr gefiltert ist — sichtbar gekennzeichnet.

#### Der Tageswert trägt nur den PV-Anteil

Die Spalte **„CO₂-Einsparung (PV)"** der Werte-Tabelle (Auswertungen → Tabelle,
Monats- **und** Tages-Granularität) zeigt bewusst nur `co2_pv_kg`:

```
CO2-Einsparung (PV) = Eigenverbrauch * 0.38
```

**Warum nicht die volle Bilanz:** WP-**Wärme** und E-Mobilitäts-**Kilometer** sind
Monatsgrößen (`InvestitionMonatsdaten`). Stündlich liegt von der Wärmepumpe nur die
Stromaufnahme vor (`TagesEnergieProfil.waermepumpe_kw`) — ohne Wärmemenge ist die
WP-Ersparnis nicht bestimmbar, und eine allein aus dem Stromverbrauch gebildete
Komponente wäre rein negativ. Eine Spalte, die im Monat drei Quellen und am Tag eine
addiert, wäre über die Granularitäten nicht summierbar.

> **Folge, die nicht stillschweigend bleiben darf: Σ Tage ≠ CO₂-Monatswert**, sobald die
> Anlage eine Wärmepumpe oder ein E-Auto hat. Die Differenz ist genau
> `max(0, CO2_WP) + max(0, CO2_E-Mob)`. Die vollständige Bilanz zeigen Cockpit → Jahr
> und Auswertungen → CO₂.

#### Monatliche CO2-Berechnung

```
CO2_PV    = Eigenverbrauch * 0.38                    (vermiedener Netzstrom)
CO2_WP    = (WP_Wärme / 0.9 * 0.201) - (WP_Strom * 0.38)  (vs. Gasheizung)
CO2_E-Mob = (Benzin_L * 2.37) - ((Ladung - PV_Ladung) * 0.38)  (vs. Benziner)
CO2_gesamt = CO2_PV + max(0, CO2_WP) + max(0, CO2_E-Mob)
```

> **Kanonische CO₂-Helfer (SoT `core/calculations.py`, DI-1/DI-2):** Diese Bilanz läuft über **genau eine**
> Helfer-Familie — `berechne_co2_bilanz` (setzt PV + WP + E-Mob zusammen), intern `co2_wp_ersparnis_kg`
> (WP: vermiedenes Gas MINUS WP-Strom-CO₂; der **Gas-Wirkungsgrad η_gas = 0,90** kommt aus
> `WP_WIRKUNGSGRAD_GAS_DEFAULT`) und `co2_emob_ersparnis_kg`. **Cockpit-CO₂-Kachel, HA-Export-Sensor
> „CO₂ Einsparung", WP-Dashboard und der PDF-Jahresbericht** rufen dieselben Helfer auf und zeigen daher
> **denselben Wert** (vorher rechneten einzelne Pfade `pv_erzeugung × f_strom` bzw. eigene WP-Formeln →
> Drift). Die WP- und E-Mob-Komponente werden für die Summe bei 0 geklammert (negative Einzelwerte
> kürzen die Gesamtbilanz nicht). **Brennstoff-Erzeuger** (BHKW/„sonstiges") erzeugen bewusst **keine**
> CO₂-Gutschrift — sie zählen zwar in EV/Autarkie (hinter dem Zähler), aber nicht als vermiedenes CO₂.

#### Äquivalente

```
Bäume          = CO2_gesamt / 20       (kg/Baum/Jahr)
Auto-km        = CO2_gesamt / 0.12     (kg/km)
Flug-km        = CO2_gesamt / 0.25     (kg/km)
```

### 3.9 PV-String SOLL-IST Vergleich

**Endpoint:** `GET /api/cockpit/pv-strings/{anlage_id}?jahr=`

#### SOLL-Berechnung (PVGIS)

> **Genau eine Prognose ist die aktive.** eedc bewahrt beliebig viele PVGIS-Abrufe einer Anlage auf;
> gelesen wird ausschließlich die als *aktiv* markierte — auch wenn das bewusst eine ältere ist
> (Nutzerwille, [Einstellungen → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)).
> Auswahlregel: `ist_aktiv == True`, `ORDER BY abgerufen_am DESC`, `LIMIT 1`; SoT
> `services/prognose_auswahl.py`, datenbankseitig gesichert durch einen partiellen Unique-Index
> (ADR-002/P5). Ist **keine** Prognose aktiv, bleibt die SOLL-Seite leer, statt eine beliebige zu zeigen.

**Ab v2.3.2 (Per-Modul PVGIS-Daten vorhanden):**
```
SOLL_Monat = PVGISPrognose.module_monatswerte[modul_id][monat].e_m
```

**Fallback (ältere Prognosen - proportional nach kWp):**
```
kWp_Anteil = Modul_kWp / Gesamt_kWp
SOLL_Monat = PVGISPrognose.monatswerte[monat].e_m * kWp_Anteil
```

Der PDF-Jahresbericht nutzt seit v4.0.1 denselben Weg (vorher verteilte sein String-Vergleich die
Prognose *immer* nach kWp, obwohl die Pro-Modul-Werte gespeichert sind — bei Ost-West-Dächern ~20–25 %
Abweichung gegenüber dem Cockpit).

**Faire Vergleichsbasis (ab v2.3.2):**
SOLL wird NUR für Monate gezählt, die auch IST-Daten haben. Verhindert aufgeblähten SOLL bei Teil-Jahren.

**SOLL im Monatsbericht:** derselbe Grundsatz — der Monatswert kommt aus den Monatszeilen **genau der
aktiven** Prognose. Vor v4.0.1 stand dort eine Summe über *alle* aktiven Prognosen; bei einem
Bestand mit zwei aktiven war der SOLL-PV-Wert verdoppelt, und mit ihm die SOLL/IST-Abweichung und die
Grundlast-SOLL-Kachel.

#### IST-Berechnung

Der IST-Wert je Modul kommt aus dem Read-time-SoT `core/berechnungen/pv_verteilung.py`
(`resolve_pv_je_modul`) — **nicht** aus einem rohen Feldzugriff. Präzedenz:

```
1. Messwert       InvestitionMonatsdaten.verbrauch_daten["pv_erzeugung_kwh"]
                  → Quelle „gemessen" — IMMER und AUSNAHMSLOS
2. Lücke füllen   (Monatsdaten.pv_erzeugung_kwh − Σ gemessene) × kWp_Anteil,
                  nur auf die Module OHNE eigenen Wert
                  → Quelle „geschätzt (kWp-Anteil)", in der Anzeige gekennzeichnet
3. keine Quelle   kein Wert (kein 0)
```

**Die Präzedenz ist modulweise, nicht anlagenweit (ab 2026-07-29).** Bis dahin genügte **ein**
Modul ohne eigenen Wert, damit der Gesamtwert über **alle** Module verteilt wurde — die echten
Messwerte der übrigen Strings wurden dabei verworfen und durch kWp-Anteile ersetzt. Dafür ist der
Gesamtwert nicht da: er füllt **Lücken**, er überschreibt keine Messungen. Teil-Messung ist auch
kein Sonderfall — sie entsteht bei jedem Sensor-Aussetzer, jedem neu angelegten String und in jedem
Monat vor der Umstellung auf Pro-String-Messung.

Übersteigt die Summe der Messwerte den Gesamtwert, wird der Rest auf 0 geklemmt statt negativ
verteilt (`Σ > Gesamtwert`) — das ist ein Messfehler und gehört gemeldet, nicht weggerechnet.

**Der Gesamtwert ist ausschließlich Eingang dieser Auflösung.** Er darf in keiner einzelnen
Berechnung direkt gelesen werden; jede PV-Zahl kommt aus der Pro-Modul-Schicht bzw. deren Summe.
Zielbild für die Erfassung: alle Strings erfassen und „PV gesamt" auf „keine" setzen —
zusammengefasst wird höchstens je Ausrichtung/Neigung, sonst kippt die Multi-Orientierungs-Prognose.
Die anteilige Verteilung ist ein Übergangswerkzeug, kein Dauerzustand.

**Der kWp-Anteil ist ein Prognose-, kein Ertragsschlüssel** (ADR-002/P2): auf der IST-Seite verteilt
er nur, wenn kein Messwert existiert — und dann sichtbar beschriftet. Solange die Werte verteilt sind,
nennen die String-Sichten bewusst **keinen besten oder schwächsten String**: eine Platzierung wäre
dort nur die Reihenfolge der Nennleistungen.

> **Benannte Ausnahme (ADR-002/P2-A):** Ist nur ein Teil der Module gemessen und **kein** Gesamtwert
> hinterlegt, behält die Pro-Modul-Sicht ihre Messwerte, während die Anlagen-Summe bewusst nichts
> zeigt. `Σ Strings ≠ Σ Anlage` ist dort **gewollt** — eine Teilsumme als „Gesamt-PV" auszuweisen wäre
> systematisch zu klein.

**Beim Import und beim Monatsabschluss** gilt dieselbe Rangfolge auf der *Vorschlags*-Seite: Ist ein
Connector-Feld einer Komponente zugeordnet, geht der volle Zählerstand dorthin („Vom Wechselrichter
(Zählerstand-Differenz)"); ohne Zuordnung wird nach Nennleistung verteilt und heißt dann „Gesamtwert,
anteilig nach kWp auf die Strings verteilt" — mit niedrigerer Konfidenz als jede gemessene Quelle.
Der Zuordnungs-Schritt des Import-Wizards schlägt die Anteile ebenfalls **nach Nennleistung** vor
(bzw. nach Kapazität bei Speichern); ist die Bezugsgröße nirgends gepflegt, verteilt er gleichmäßig
**und sagt dazu, dass das keine proportionale Aufteilung ist**.

#### Kennzahlen pro String

```
Abweichung_kWh        = IST - SOLL
Abweichung_%          = (IST - SOLL) / SOLL * 100
Performance_Ratio      = IST / SOLL
Spez. Ertrag (kWh/kWp) = IST_Jahr / Modul_kWp
```

### 3.10 Sonstige Positionen

**Utility:** `utils/sonstige_positionen.py`

Sonstige Positionen sind frei erfassbare Erträge/Ausgaben je Monat (Reparaturen, Wartung, THG-Quote, Abschlag, Guthaben-Auszahlung …), erfasst im [Monatsdaten-Formular](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss). Es gibt sie auf **zwei Ebenen**:

- **Komponenten-Ebene:** `InvestitionMonatsdaten.verbrauch_daten["sonstige_positionen"]` (seit jeher).
- **Anlage-/Basis-Ebene (G19-1, ab v4.0):** `Monatsdaten.sonstige_positionen` — für Positionen, die keiner einzelnen Komponente zuzuordnen sind. Gelesen über den Spiegel-Helper `get_md_sonstige_positionen`.

> **Vorrang neues Format:** `get_sonstige_positionen()` liest zuerst `sonstige_positionen`; nur wenn der Schlüssel **fehlt**, greift der Legacy-Fallback `sonderkosten_euro`/`sonderkosten_notiz` (→ eine Ausgabe-Position). Eine additive Start-Migration materialisiert Alt-`sonderkosten_euro > 0` als „… (migriert)"-Ausgabe; die Legacy-Spalten bleiben lesbar (deprecated, nicht neu befüllen). **Wirkung für Bestandsdaten:** Alt-Sonderkosten, die bis v3.45 in **keiner** Berechnung auftauchten, zählen ab v4.0 in den Finanz-Summen (s. [§3.2](#32-finanzen-cockpit)).

Jede `InvestitionMonatsdaten.verbrauch_daten` bzw. `Monatsdaten`-Zeile kann sonstige Positionen enthalten:

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
Sonstige_Erträge  = Σ(betrag) wo typ == "ertrag"    (alle Komponenten + Anlage-Ebene)
Sonstige_Ausgaben = Σ(betrag) wo typ == "ausgabe"    (alle Komponenten + Anlage-Ebene)
Sonstige_Netto    = Erträge - Ausgaben
```

> **Sichtbarkeits-/Doppelzählungs-Regel:** Die Aggregation filtert nach `aktiv` + Laufzeit-Fenster (Anschaffung → Stilllegung) wie jede andere Position; der Caller übergibt das bereits gefilterte `sonstige_netto` als Skalar an das Finanz-Aggregat. Basis-Positionen zählen **genau einmal** in die Totals; die T-Konto-Zeilen sind reiner Ausweis (kein zweiter Kostenposten).

**Dienstliche Ladekosten:**
Bei `ist_dienstlich == true` (E-Auto/Wallbox) werden Ladekosten als kalkulatorische Ausgaben verbucht:
```
Dienstlich_Ladekosten = Netz_kWh * Wallbox_Preis + PV_kWh * Netzbezugspreis
```

> **Warum der PV-Anteil zum Netzbezugspreis zählt, nicht zur Einspeisevergütung (seit 2026-07-31).** Die Formel stand bis dahin andersherum, und die beiden für sich plausiblen Halbschritte gingen zusammen nicht auf: Der Eigenverbrauch ändert sich durch das Dienstwagen-Flag **nicht** — energetisch ist die Ladung Eigenverbrauch hinter dem Zähler —, also schreibt die EV-Ersparnis (`Eigenverbrauch × Netzbezugspreis`) die dienstlich geladenen kWh voll gut. Der Abzug zog dagegen nur die Einspeisevergütung ab. Netto blieben **+22 ct je verschenkter kWh** Gewinn stehen (bei 30/8 ct). Die *entgangene Einspeisevergütung* braucht gar keinen Buchungssatz: sie steckt bereits in der niedrigeren **gemessenen** Einspeisung. Was einen braucht, ist die zurückzunehmende EV-Gutschrift — und die steht zum Netzbezugspreis.
>
> Gemessen (PV 1.000 · Einspeisung 400 · Netzbezug 100 · 30/8 ct · 200 kWh PV in den Wagen):
>
> | Fall | Eigenverbrauch | Netto-Ertrag |
> | --- | ---: | ---: |
> | gar kein Auto (200 kWh eingespeist) | 400 kWh | 168,00 € |
> | Privatwagen | 600 kWh | 212,00 € |
> | Dienstwagen — bis 2026-07-31 | 600 kWh | 196,00 € |
> | **Dienstwagen — seither** | **600 kWh (unverändert)** | **152,00 €** |
>
> **Die Energiebilanz bleibt unangetastet** — Eigenverbrauchs-kWh, Eigenverbrauchsquote und Autarkie ändern sich durch diesen Posten nicht. Korrigiert wurde ausschließlich die Bewertung in Euro.
>
> **Netzanteil:** Wallbox-Stromvertrag, wenn vorhanden, sonst Anlagentarif — jeweils der Monats-Flexpreis vor dem Stammdaten-Arbeitspreis (P8). Die Aussichten nahmen dafür bis 2026-07-31 den allgemeinen Arbeitspreis, das Cockpit den Wallbox-Preis; Kanon ist das Cockpit.
>
> **SoT:** `core/berechnungen/dienstliche_ladekosten.py` (ADR-001). Alle drei Sichten — Cockpit/Übersicht, Aussichten/Finanz-Prognose und der HA-Sensor `netto_ertrag_euro` — rufen ihn; der HA-Export zog die Kosten bis 2026-07-31 **gar nicht** ab und stand damit über der Kachel, auf die er sich bezieht.

---

## 4. Prognosen (Aussichten)

> **Prognose-Kanon — „PV-Tagesprognose heute" ist EIN Wert.** Der „heute"-Wert (sowie Rest heute, morgen/übermorgen, Vor-/Nachmittag, Stundenprofil) wird seit dem Prognose-Kanon-Fix über **einen** Service (`services/prognose_kanon.py`) gebildet und an alle Konsumenten geliefert: Live/Cockpit (`live_wetter`), die „eedc"-Spalte im Vergleich (`api/routes/prognosen`), die HA-/MQTT-Sensoren (`ha_export_prognose`) und den persistierten Tageswert (`TagesZusammenfassung.pv_prognose_kwh`). Rechenweg: **Multi-String-Fan-out** pro Orientierungsgruppe (`pv_orientation.orientierungs_gruppen` → je ein `get_solar_prognose`) → slot-weise Summe = rohes OpenMeteo-kWh-Profil → **eedc-Korrektur pro Energie-Slot** (`core/berechnungen/prognose_korrektur.korrigiere_tagesprofil`, Kaskade `korrekturprofil_lookup`) mit Invariante `Tageswert == Σ Export-Slots`. Der Wert **rollt** mit OpenMeteo, aber überall synchron. Mathematik in `core/berechnungen/` (ADR-001), Orchestrierung im Kanon-Service. Symmetrie-Test: `tests/test_prognose_kanon.py`.
>
> **Was seit v4.0.1 zusätzlich am Kanon hängt.** Der 14-Tage-Balken in Cockpit → Aussicht samt
> 14-Tage-Tabelle und den Kacheln „Morgen"/„Summe"/„Ø_Tag", die Zeilen Morgen/Übermorgen der
> Live-Solar-Aussicht sowie die Blöcke „Stunden-Prognose"/„Stundenwerte" lasen bis dahin die
> **unkorrigierte** OpenMeteo-Zahl bzw. gingen einen eigenen Ein-Abruf-Weg mit der Orientierung einer
> beliebigen PV-Zeile. Sie kommen jetzt aus derselben Rechnung wie der Prognosen-Vergleich und der
> Sensor `eedc_prognose_day_plus_1_kwh`. *(Ausgenommen: die Spalte „OpenMeteo" im Prognosen-Vergleich
> — sie ist der Rohwert und bleibt es.)* Fehlt eine Korrektur, bleibt der Wetterdienst-Wert stehen und
> die Kopfzeile sagt es („Quelle: Open-Meteo (ohne Korrektur)").
>
> **Fällt der Kanon aus** (kein OpenMeteo-Ergebnis, keine kWp, Zieltag jenseits des Abruf-Horizonts),
> springt ein Ersatz-Weg ein — der **fächert seit v4.0.1 ebenfalls je Orientierungsgruppe auf** statt
> die Gesamtleistung mit der Orientierung einer beliebigen PV-Zeile zu rechnen (ADR-002/P1: kein
> Anlagen-Kennwert aus EINER Investition). Liefert eine Gruppe nichts, trägt die **Antwort** den
> Hinweis auf die Teilsumme — nicht das Log (ADR-002/P4). Dasselbe gilt, wenn gar keine Prognose
> vorliegt: 24 Nullen werden als „keine Prognose" ausgewiesen, nicht als Prognose „0 kWh".
>
> **Genauigkeits-Endwert (§6).** Das Genauigkeits-Ranking vergleicht IST gegen `TagesZusammenfassung.pv_prognose_final_kwh` (Fallback `pv_prognose_kwh`): dieser rollt mit, bis OpenMeteo für den Tag nach Sonnenuntergang konvergiert ist (`core/berechnungen/prognose_final.soll_final_einfrieren`), und wird dann via `pv_prognose_final_at` eingefroren. Der Anzeige-Wert bleibt rollend (Drei-Größen-Modell: Anzeige rollend · Lern-Snapshot gefroren · Tracking-Endwert konvergenz-gefroren).

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
| `Anlagenleistung_kWp` | Σ(PV-Module) + Σ(BKW), gelesen über den SoT-Dispatcher `get_erzeuger_kwp` (ADR-002/P3). Reihenfolge: Feld **Leistung (kWp)** der Investition → ersatzweise die Detail-Felder `kwp` bzw. `leistung_kwp` (nur Bestands-/Importdaten) → beim Balkonkraftwerk zusätzlich `leistung_wp` × `anzahl` (Anzahl fehlt ⇒ **1**, nicht die Formular-Vorbelegung 2). Seit v4.0.2 gilt dieselbe Kette an **allen** Lesestellen der Nennleistung — Prognose, Cockpit, PV-Strings, ROI, CO₂, Live und PDF. | `Anlage.leistung_kwp` |
| `GTI_kWh_m2` | **Global Tilted Irradiance** aus Open-Meteo Solar (modul-projiziert mit Tilt + Azimut). Bei Multi-String-Anlagen werden parallele Calls pro Orientierungsgruppe abgesetzt und kWp-gewichtet kombiniert. | – |

> **GTI-Spalte der 14-Tage-Tabelle ist ein kWp-gewichtetes Mittel** („GTI Modulfläche"): die
> Einstrahlung auf die Modulflächen *dieser* Anlage, konsistent zur Ertragssumme derselben Zeile
> (`Ertrag ≈ GTI × kWp × (1 − Verluste)` ist linear in kWp). Bis v4.0.0 wurde ungewichtet gemittelt —
> ein 0,8-kWp-Balkonmodul zählte so viel wie ein 12-kWp-Süddach, und die Spalte passte zu keiner
> anderen Zahl ihrer Zeile. Anlagen mit nur einer Ausrichtung sind nicht betroffen. *(Die Performance
> Ratio läuft über einen anderen Pfad — die Tages-GTI aus der Aggregation, dort schon immer
> kWp-gewichtet.)*
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

**Geltungsbereich (seit v4.0.2, A30):** Die Modellwahl wirkt auf **alle** Prognose-Pfade, weil der Prognose-Kanon (`services/prognose_kanon.py`) `Anlage.wetter_modell` an `get_solar_prognose` durchreicht — also auch auf die eedc-korrigierte Tagesprognose, die Stundenprofile, die Live-/Persistenz-Werte und den HA-/MQTT-Export (`services/ha_export_prognose.py`). Bis v4.0.1 rechnete dieser Pfad unabhängig von der Einstellung mit `best_match`, während Live-Wetter, 14-Tage-Wettertabelle und die OpenMeteo-Spalte von `/solar-prognose` das Modell bereits nutzten — dieselbe Seite zeigte damit zwei Modelle nebeneinander.

**„Keine Daten" schließt die leere Antwort ein.** Open-Meteo kann für ein Modell mit HTTP 200 antworten und trotzdem für jede Stunde `null` liefern; `_hat_nutzbares_gti` behandelt das wie einen Fehlschlag, damit die `best_match`-Kaskade greift statt einen 0-kWh-Tag zu bauen. **Am 2026-07-28 gemessen betrifft das drei der acht wählbaren Werte:** `ecmwf_ifs04` (HTTP 200, 0 von 72 Stundenwerten gesetzt — das Modell läuft nicht mehr, der Name wird noch akzeptiert) sowie `ecmwf_seamless` und `meteoswiss_seamless` (keine gültigen Modellnamen mehr, HTTP-Fehler). Für diese drei rechnet eedc faktisch mit `best_match`; die Bereinigung der Auswahlliste steht aus.

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

### 4.1c Prognose-Vergleich (Auswertungen → Prognose)

Anzeige: [Auswertungen → Prognose (Genauigkeit gegen IST)](HANDBUCH_BEDIENUNG.md#43-prognose-genauigkeit-gegen-ist) — fachlich beschrieben im [Handbuch Prognosen](HANDBUCH_PROGNOSEN.md).

**Endpoint:** `GET /api/aussichten/prognosen/{anlage_id}`
**Service:** `api/routes/prognosen.py` (in v3.16.6 aus `aussichten.py` ausgelagert), `services/solcast_service.py`

Der Prognosen-Tab vergleicht vier Quellen pro Tag/Stunde:

| Quelle | Bedeutung |
|---|---|
| **OpenMeteo (OM)** | Wetterbasierte Roh-Prognose aus GTI × kWp × (1 − System_Losses). **Auch die Stundenkurve „OpenMeteo (roh)" fächert seit v4.0.1 je Orientierungsgruppe auf** — vorher rechnete sie die Gesamtleistung so, als hinge sie an *einer* Dachfläche (Neigung/Ausrichtung der zufällig ersten PV-Zeile, sonst stillschweigend 35° Süd), während der OM-**Tageswert** derselben Spalte längst auffächerte. Kurve, Summenzeile und Tageswert sind jetzt deckungsgleich. |
| **eedc (kalibriert)** | die anlagenspezifisch korrigierte Prognose. Legende und Beschriftung sagen seit v4.0.1 „eedc (kalibriert)" statt „eedc (OpenMeteo × Faktor)" — korrigiert wird **pro Stunden-Slot auf der Energie**, nicht mit einem Tagesfaktor. |
| **Solcast** | Optionale dritte Quelle, entweder Solcast-API (Free/Paid Key) oder HA-Sensor (BJReplay-Integration). 30-Min-Buckets werden per `ceil(bucket_ende)` dem Backward-Slot zugeordnet. |
| **IST** | Tatsächlich gemessener Tageswert aus den Stunden-Snapshots (siehe §6b) |

#### Abweichung und Σ-Zeile im Stundenvergleich (ab v4.0.6)

Die Tabelle „Stundenvergleich heute" annotiert jeden Prognosewert mit seiner Abweichung zum IST **derselben** Stunde. Zwei Regeln, beide client-seitig in `components/prognose/PrognoseVergleichTeile.tsx` (`DevBadge` bzw. `stundenSummeVon`), gepinnt in `PrognoseVergleichTeile.stundenvergleich.test.tsx`:

```
Δ_Stunde   = Prognose_kWh − IST_kWh            (angezeigt: |Δ|, Richtung als ▲/▼, „±" wenn |Δ| < 0,05)
Δ_relativ  = |Δ| / IST × 100                   (nur für die Farbskala bzw. die Σ-Zeile; IST > 0,05 vorausgesetzt)
```

- **Liegt ein IST vor, wird immer annotiert** — auch bei Δ = 0. Eine fehlende Annotation bedeutet damit eindeutig „keine Messung", nicht „kleine Abweichung". *(Bis v4.0.5 unterdrückte die Anzeige jedes |Δ| < 0,03 kWh; das traf je Spalte unterschiedlich zu und sah in der Zeile aus wie eine Datenlücke — PN Rainer 90004.)*
- **Die Σ-Zeile summiert über ein gemeinsames Fenster.** Obergrenze ist die letzte Stunde mit IST, höchstens `aktuelle_stunde` (Slot `aktuelle_stunde + 1` läuft noch, s. Backward-Konvention). Stunden **ohne** IST bleiben in allen vier Spalten außen vor — die vier Summen meinen damit paarweise dieselben Stunden. *(Bis v4.0.5 stand dort die 24-Stunden-Prognosesumme neben `ist_heute_kwh`: mittags z. B. 78,1 gegen 26,1 — die Abweichung maß die Tageszeit.)*
- **Ohne jedes IST** (Zukunftstag) zeigt die Σ-Zeile die volle Prognosesumme und **kein** Δ — ADR-002/P4: kein 0-%-Ergebnis auf einer nicht vorhandenen Referenz. Der Vollständigkeits-Grenzfall „alle 24 Stunden gemessen" verhält sich wie vorher (keine `bis HH:00`-Kennzeichnung).

Nicht zu verwechseln mit der **Tagesprognose** derselben Spalte (`openmeteo_heute_kwh` etc.) in der Kennzahl-Matrix — die bleibt der ganze Tag, ebenso `verbleibend_*` (= IST bisher + Σ Prognose-Slots der Reststunden).

#### Lernfaktor (saisonale MOS-Kaskade, ab v3.16.15)

Die eedc-Prognose ist die korrigierte OpenMeteo-Prognose; der Skalar-Lernfaktor unten ist die
**gröbste Stufe** der Korrektur-Kaskade (feiner: Sonnenstand × Wetter je Stunden-Slot, siehe
[Prognosen §5.3](HANDBUCH_PROGNOSEN.md#53-das-korrekturprofil-sonnenstand--wetter)). Der Lernfaktor wird aus historischen `(Prognose, IST)`-Tag-Paaren berechnet — nur Tage mit gültiger OpenMeteo-Prognose **UND** IST-Ertrag > 0.5 kWh fließen ein (Schlechtwetter-Tage mit ~0 kWh würden den Faktor sonst verzerren).

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
- **Echte Lücken (>1 h alt)** werden mit ⚠ markiert. Klick auf das Symbol öffnet einen Reparatur-Popover mit „Tag neu berechnen" (`POST /api/energie-profil/{anlage_id}/reaggregate-tag`) und einem Fallback-Link zur [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung).

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

> **Monats-Gaspreis (v3.21.0):** Wenn `Monatsdaten.gaspreis_cent_kwh` pro Monat gepflegt ist, wird er Monat für Monat verwendet — ein Tarifwechsel ändert dann nicht mehr rückwirkend die ganze Historie. Ohne Eintrag bleibt es beim statischen `alter_preis_cent_kwh` der Investition. Pflege in der assistierten `MonatsdatenForm` (über `BEDINGTE_BASIS_FELDER` mit `bedingung_basis: hat_waermepumpe`) — in V4 der EINE Erfassungsweg; der frühere Monatsabschluss-Wizard ist als V4-Fläche stillgelegt und läuft nur noch über die V3-Route (bis zum Flip).

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
2. HA-Sensor strompreis (via Datenquellen-Zuordnung) (automatisch aus HA)
3. Strompreis.netzbezug_arbeitspreis_cent_kwh      (fester Tarif)
4. Hardcoded Default: 30.0 ct/kWh
```

**Konfiguration:**

- In der [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) kann ein HA-Sensor (oder MQTT-Topic) für das Feld `strompreis` zugeordnet werden
- Im [Monatsdaten-Formular](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss) wird der Ø-Preis als Vorschlag angezeigt und ist dort manuell editierbar

> **Der Jahres-Ø ist mengengewichtet.** Die Jahres-/Gesamt-Kachel „Ø-Preis Netz" (und ebenso die Ø-Einspeisevergütung) rechnet `Σ(Preis_Monat × Menge_Monat) / Σ Menge_Monat` — nicht das arithmetische Mittel der Monatspreise. Gewichtet wird der **effektive** Monatspreis (also der Ø-Bezugspreis vor dem Tarif-Arbeitspreis, dieselbe Kette wie oben); sonst fiele ein Jahr mit dynamischem Tarif auf den Referenzpreis zurück, obwohl die Kosten darunter mit dem Stundenpreis gerechnet sind. Monate ohne Menge fallen aus Zähler und Nenner; gibt es im Zeitraum überhaupt keine Menge, bleibt das arithmetische Mittel als Rückfall stehen, statt die Kachel zu leeren. **Ohne die Gewichtung passte der Kopfwert nicht zu den kWh und Euro darunter** — ein teurer Winter- und ein billiger Sommermonat wogen gleich viel (Forum simon42 #89667/67).

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

**Die Konvention endet nicht am Backend (v4.0.6).** Wer eine Stunde *beschriftet* oder einen Messwert
in eine Chart-Spalte *einsortiert*, folgt derselben Regel — Client-SoT ist
`frontend/src/lib/stundenSlot.ts` (Spiegel von `core/berechnungen/slot_konvention.py`, Regressionstest
`stundenSlot.test.ts`):

| Funktion | Wofür |
|---|---|
| `slotZeitspanne(h)` | Beschriftung — Slot 11 → „10:00–11:00 Uhr". **Jeder** Tooltip einer Stundengrafik. |
| `slotAusIntervallStart(h)` | Messreihen mit Slot-**Beginn**-Stempel (10-Min-Punkte des Tagesverlaufs) → Slot `h+1`. Rückgabe 24 = Slot 0 des Folgetags, **kein** Modulo. |
| `slotAusZeitpunkt("HH:MM")` | Zeitpunkt-Marker (Sonnenaufgang, Solar Noon) in den Slot, der ihn enthält — 05:56 → Slot 6. |

Auslöser war Rainer (PN 90106, 01.08.2026): der Live-Block „Wetter heute" baute seine Zeitspanne selbst
und **vorwärts** (`[h, h+1)`), während die Prognose-Sicht rückwärts beschriftete; zusätzlich bündelte er
die 10-Minuten-Punkte der Stunde `h` in Spalte `h` statt `h+1`. Gemessen gegen die Live-Box lag die
IST-Kurve dadurch **genau eine Spalte** neben der Prognose im selben Chart. Klasse: nicht das
Beschriftungs-Symptom patchen, sondern die Stelle, die die Zuordnung konstruiert
(`feedback_aggregations_drift`).

**Auch die Verbrauchs-Seite folgt ihr (v4.0.6).** Die gestrichelte Verbrauchs-Prognose im Live-Chart
kommt aus dem individuellen Verbrauchsprofil der letzten 7 vollen Tage
(`services/live_verbrauchsprofil_service.py`), und das hat **drei** Quellen mit Vorrang in dieser
Reihenfolge:

| Quelle | Wann sie greift | Slot-Herkunft |
|---|---|---|
| EEDC-DB (`TagesEnergieProfil.stunde`) | sobald der Scheduler mindestens zwei Tage aggregiert hat | schon backward (Aggregator schreibt über `lts_boundary_index`) |
| HA-History (Leistungsmittel je Stunde) | frische Installation, noch keine DB-Historie | `_slot_fenster` → `backward_slot_aus_period_start` |
| MQTT-Snapshots (Zähler-Delta je Stunde) | Standalone-Betrieb ohne HA | dieselbe Stelle |

Bis v4.0.5 bündelten die beiden **Fallback**-Quellen forward: die Energie aus `[h, h+1)` landete unter
Index `h`, das Profil lag also eine Stunde zu früh — unsichtbar für jeden, der schon DB-Historie hat,
sichtbar bei **Neuinstallation** und im **Standalone-Betrieb**. Seit v4.0.6 ordnet **eine** Stelle im
Modul zu (`_slot_fenster`), und zwar über den Backend-SoT `core/berechnungen/slot_konvention.py`;
das Abfrage-Fenster beginnt dafür eine Stunde vor Mitternacht, weil Slot 0 des ersten Tages das
Intervall `[Vortag 23:00, 00:00)` trägt. Gepinnt in
`tests/test_verbrauchsprofil_slot_konvention.py` — je eine Regression pro Fallback-Pfad plus ein
Symmetrie-Test „gleiche Wirklichkeit, drei Messarten ⇒ **ein** Profil"
(`feedback_aggregator_symmetrie`).

#### Wann eine Stunde als unvollständig gilt (v4.0.6)

Die Zuordnung allein genügt nicht — die drei Quellen müssen sich auch einig sein, **wann eine Stunde
überhaupt gemessen wurde**. Eine unvollständige Stunde liefert in allen dreien **keine Stichprobe**;
sie wird ausgelassen, nicht geschätzt und nicht als 0 kW gezählt:

| Quelle | Stunde gilt als gemessen, wenn … | sonst |
|---|---|---|
| EEDC-DB | eine `TagesEnergieProfil`-Zeile mit `verbrauch_kw IS NOT NULL` existiert | keine Zeile ⇒ keine Stichprobe (galt schon immer) |
| HA-History | mindestens **ein** Netz-Sensor (Bezug, Einspeisung oder Kombi) in dieser Stunde einen Messpunkt hat | Stunde wird übersprungen |
| MQTT-Snapshots | für **jeden** gelieferten Zähler an **beiden** Intervallgrenzen ein Stand vorliegt (höchstens 6 Minuten alt) | Stunde wird übersprungen |

Zu den beiden Fallbacks im Einzelnen:

- **MQTT misst über die Intervallgrenzen**, nicht über die zufällig in der Stunde liegenden Snapshots.
  Bis v4.0.5 war das Stundendelta „letzter minus erster Snapshot *innerhalb* der Stunde"; das letzte
  Snapshot-Intervall fiel damit jede Stunde heraus — bei 5-Minuten-Takt rund **8 % zu wenig**, und ein
  Verbrauch, der erst gegen Ende der Stunde anfiel, ging ganz verloren. Der Randwert ist der letzte
  Zählerstand *bei oder vor* der Grenze; benachbarte Stunden lesen denselben Wert, deshalb geht an der
  Grenze nichts verloren und nichts wird doppelt gezählt. Der Scheduler schreibt alle 5 Minuten, aber
  nicht auf die volle Stunde gerastert — daher die 6 Minuten Toleranz (Reserve für Verzug, aber nicht
  genug für einen ausgefallenen Snapshot).
- **HA zählt eine Stunde ohne Historie nicht mehr als gemessene Null.** Bis v4.0.5 hängte jede Stunde
  eine Stichprobe an, auch wenn der Recorder nichts geliefert hatte: aus *unbekannt* wurde *war
  nichts*, und ein einziger Ausfalltag drückte jeden Werktags-Slot auf 4/5 des wahren Werts. Beleg ist
  bewusst der **Netzanschluss** und dort `any` statt `all`: PV- und WP-Sensoren melden nachts bzw. im
  Stillstand stundenlang keine Zustandsänderung, ohne dass Daten fehlen, und von Bezug und Einspeisung
  bewegt sich immer genau einer. Liefert im ganzen Fenster **kein** Netz-Sensor, gibt es kein
  HA-Profil — sonst stünde die reine PV-Kurve als vermeintlicher Verbrauch da.

Ein Slot ohne jede Stichprobe fehlt im Ergebnis-Dict. Der Konsument
(`api/routes/live_wetter.py::_berechne_verbrauchsprofil`) erkennt das und setzt seine
Standard-Grundlast ein, statt still 0 kW anzunehmen — die lokale Ausprägung von
[ADR-002/P4](ADR-002-WURZELMUSTER.md).

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

Datengrundlage für die §51-Sektion in [Cockpit → Monat](HANDBUCH_BEDIENUNG.md#23-monat) (die Monats-Darstellungen des alten Energieprofils sind dorthin gehoben — siehe [Handbuch Energieprofil](HANDBUCH_ENERGIEPROFIL.md#2-wo-du-das-energieprofil-in-der-app-findest)).

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
3. **Legacy-Felder:** `Monatsdaten.batterie_*` ist deprecated. `Monatsdaten.pv_erzeugung_kwh` ist es **nicht** — kein Schreibziel für neuen Code und nur als **Eingang von `resolve_pv_je_modul`** zu lesen (Anlagen-Aggregat, s. [Schicht 1](#schicht-1-rohdaten-eingabe)); Pro-Modul-Werte kommen aus `InvestitionMonatsdaten` (Typ: pv-module)
4. **PVGIS E_m vs e_m:** Ältere Prognosen verwenden `E_m` (Großbuchstabe), neuere `e_m`
5. **Grundpreis:** Wird zu den Netzbezugskosten addiert, NICHT vom Netto-Ertrag abgezogen. Er ist auch der Grund, warum „Kosten ÷ kWh" **nicht** den Ø-Preis ergibt — dafür gibt es `netzbezug_arbeitspreis_kosten_euro` (s. [§3.1](#31-energie-bilanz-monatskennzahlen))
6. **Cockpit vs ROI-Dashboard:** Cockpit berechnet inline (vereinfacht), ROI-Dashboard nutzt `calculations.py` (detaillierter)

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
