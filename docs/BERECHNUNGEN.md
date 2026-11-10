# eedc Berechnungsreferenz

Dieses Dokument beschreibt die **Regeln und Grenzen** der Berechnungen in eedc: wie eine Größe gebildet wird,
welche Quelle Vorrang hat und wo eine Zahl bewusst fehlt. Es dient als Referenz zur Fehlersuche und zum Verständnis der
Datenflüsse. **Welche Größen es gibt** — Bedeutung, Einheit, Herkunft, Code-Ort und der Test, der sie hält — steht je Größe
in einer Zeile in der aus dem Code erzeugten [Übersicht der Größen](UEBERSICHT-GROESSEN.md); deren Spalte «Regel» verweist
hierher. Fund- und Issue-Nummern im Text (N-…, F-…, #…) nennen die Herkunft einer Regel.

> **Fachliche Fassung für Anwender:** Die Wärmepumpen-, Klimaanlagen- und Heizstab-Formeln aus §3.5 sind in [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md) ohne Formelzeichen beschrieben — samt der Frage, warum eine Arbeitszahl verschwindet.

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
   - [3.11 Community-Datensatz: abgeleitete Stammdaten](#311-community-datensatz-abgeleitete-stammdaten)
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

**Einspeisung und Netzbezug des Monats** (`ZaehlerFakten`, `services/monats_fakten/bau.py::_zaehler_fakten`): die Monatszeile
trägt beide Felder. Ein Netzfeld, das sie nicht erfasst (0 ohne Herkunftseintrag, `roh.netzfeld_ist_erfasst`, N-734), füllt die
Monatssumme der Tagesebene — nur dieses Feld und nur, wenn die Tagesebene es erfasst hat, also mindestens eine Stunde mit Wert trägt
(N-736). Ohne Monatszeile füllt die Tagesebene beide Felder; erfasst ist ein Feld dann ebenso nur mit mindestens einer Stunde mit Wert
(N-751). Die Tagesebene steht dafür bereit, wenn sie geladen ist (mit `inkl_nur_tageswerte` oder für den Ladeanteil,
`monats_fakten/laden.py`; an Monaten mit voller Kanal-Deckung kommt ihre Summe aus den Kanälen). Ein nicht erfasstes Feld bleibt 0,0
mit der Marke „nicht erfasst" und gilt den Sichten nicht als gemessene 0; `meta.netz_erfasst` verlangt Monatszeile **und** beide
Felder erfasst.

> **Grundsatz: ein Zeitraum ist die Differenz zweier Stände** (HA-Bauform S1/S2). Mit Home Assistant spiegelt eedc für jeden
> zugeordneten Zähler dessen Langzeitstatistik Stunde für Stunde (`kanal_statistik`; ohne HA die eigene Summe aus den
> MQTT-Rohständen nach HAs Reset-Regel). Die Menge eines Tages, Monats oder Jahres ist **Stand am Ende − Stand am Anfang** — wie
> im HA-Energie-Dashboard, ohne Deckel und ohne Rücksprung-Verwurf; eine fehlende Stunde im Inneren steckt in der Folgestunde.
>
> * **Abdeckung:** ein Kanal deckt einen Zeitraum voll, wenn er einen Stand vor dem Anfang hat, sein Stand das Ende
>   erreicht (im laufenden Zeitraum mit 70 Minuten Schreibverzug) und der Zeitraum nicht feiner ist als die Spanne
>   zweier Stände über einen Rand. Ohne volle Abdeckung gibt es keinen Kanal-Wert.
> * **Quellenwahl je Zeitraum** (ADR-002/**P14**): je Tag bzw. Monat und Gruppe EINE Wahl — die Kanäle nur, wenn
>   **jeder** Eingang der Formel deckt (in einer Entweder-oder-Gruppe der erste deckende); sonst rechnet der bisherige
>   Leser den **ganzen** Zeitraum aus Stunden-, Tages- und Monatszeilen (*Lesart 1*). Gruppen: Bilanz (Netz ·
>   PV/Balkonkraftwerk samt Anlagenzähler · Speicher · Erzeuger hinter dem Zähler), E-Mobilität, Sonstiges, Wärmepumpe,
>   Preis. *Gespeichert schlägt gerechnet* (P8): ein abgeschlossener Monat behält seine gespeicherten Mengen.
> * **Abgeleitete Kanäle** schreibt eedc im Stundenlauf aus den gespiegelten: den PV-Anteil der Heimladung je Gerät,
>   den Strom je Betriebsart der Wärmepumpe und die Kosten-Summen bei Stundenpreis. Sie beginnen mit dem Monat des
>   Updates; frühere Monate rechnet eedc nicht neu.
> * **Verweise je Größe:** Netz, PV, Balkonkraftwerk, Speicher, Erzeuger hinter dem Zähler — Kasten „PV je Gerät aus
>   Zeitraum-Differenzen — Regel W2" (unten) · Preis und Kosten — §3.1, Kasten „Der gemessene Ø aus Kosten-Kanälen" ·
>   E-Mobilität und Sonstiges — §3.4, Kasten „E-Mobilität und Sonstiges aus Zeitraum-Differenzen" · Wärmepumpe — §3.5,
>   Kasten „Strom je Betriebsart aus Zeitraum-Differenzen" und „Kein Betrieb ist eine Messung" · Zeitfenster-Tarif
>   (HT/NT) — §3.1 (das Gewicht ist der Netzbezug je Wochentag und Uhrstunde aus den Kanälen, eine Abfrage je Seite).
> * **Stunden (S3):** an einem Kanal-Tag kommen auch die **Stunden** aus den Kanälen — der Stunden-Verlauf von *Cockpit → Tag*,
>   die stundengepaarten Spalten (Direktverbrauch, Überschuss, Defizit, Zahl der Stunden, WP-Strom) in den Tageswerten und
>   *Energieprofil → Monat* und die Stundenform der Wärme-Sichten; Regeln in §6b, Kasten „Der Kanal-Stundentag".
> * **Kennzahlen und Analyse-Leser (S5):** an einem Kanal-Tag lesen auch die Kennzahl- und Prognose-Leser auf Stundenwerten
>   (Speicher-Simulation, Ladepreis, Grundlast, Lern- und Korrekturprofil), der Daten-Checker und die HA-Export-Steuerung die
>   Stunden aus den Kanälen; Performance Ratio, §51-Menge und Heimladungs-Anteil kommen dort aus den Kanal-Stunden, und die
>   Stunden- und Tageszeilen tragen an Kanal-Tagen keine Mengen der Kanal-Gruppen (§6b, Tabelle „Stand der HA-Bauform").
> * **Was nicht so rechnet (bleibt):** Spitzen und Vollzyklen (Tageszeile), Ladestand, Preise, Wetter, Zählwerke und die
>   Leistungswerte je Gerät der Stunde bleiben Bahnen der Stunden- und Tageszeilen (die Mittelwert-Kanäle — HA-Spiegel und
>   MQTT-Mitschrift — lesen nur der Temperatur-Verlauf der Wärmepumpe und der Stundenpreis); Tage und Monate ohne volle
>   Kanal-Deckung (Lesart 1) rechnen aus den Stunden- und Tageszeilen. Der Monatsabschluss-Nachlauf rechnet nur Tage, die fehlen
>   und die HA noch im Verlauf hat (§6b).

**Legacy-Felder (NICHT neu befüllen):**
- `Monatsdaten.batterie_*` — Speicherwerte gehören in `InvestitionMonatsdaten` (Speicher).
- `Monatsdaten.pv_erzeugung_kwh` — **kein Schreibziel** für neuen Code (Pro-Modul-Werte gehören in `InvestitionMonatsdaten`) und
  **keine allgemeine Lesequelle**: das Feld trägt den manuell erfassten oder importierten **PV-Gesamtwert** eines Monats und ist
  **ausschließlich Eingang** des Read-time-SoT `core/berechnungen/pv_verteilung.py` (`resolve_pv_je_modul`), der damit die Lücken
  der Module ohne eigenen Wert füllt und sie als gerechnet kennzeichnet. Der Gesamtwert steht für **alle** PV-Quellen: bevor er die
  Lücken füllt, geht der eigene Monatswert jedes Balkonkraftwerks ab, das im Monat selbst trägt (nicht an Modul-Kinder abgetreten) —
  es steht in `pv_erzeugung_kwh = pv_module_kwh + bkw_kwh` als eigener Summand. Ein selbst tragendes BKW **ohne** eigenen Wert ist
  eine Lücke wie ein Modul ohne Wert (N-621): es bekommt seinen kWp-Anteil am Rest (Gewicht `get_erzeuger_kwp`, auch
  `leistung_wp × anzahl`), geführt als `erzeugung.bkw_aus_anlagenwert_kwh` und additiv in `pv_kwh` — nicht in `bkw_kwh`, nicht in
  `pv_je_modul`, nicht in `BkwFakten`; ein BKW mit Anteil trägt im Monat keinen Ersatz-Eigenverbrauch (P9) und keinen Tageswert.
  Das gilt nur, wo der Gesamtwert **gespeichert** ist — von Hand, mit „Aus HA laden" (N-622) oder über den HA-Statistik-Import.
  Wer nur einen Gesamt-Sensor hat, pflegt ausschließlich hier. Jede Berechnung liest die Pro-Modul-Schicht bzw. deren Summe, nie
  das Feld selbst. Ladepfad: `services/pv_monatswerte.py`.

> **PV je Gerät aus Zeitraum-Differenzen — Regel W2 (HA-Bauform E4a-2).** Wo die Kanäle der Bilanz-Gruppe (Netz,
> PV/Balkonkraftwerk samt Anlagenzähler, Speicher, Erzeuger hinter dem Zähler) einen Zeitraum **voll decken**, rechnet eedc Tag,
> Monat und Jahr mit **einer** Regel aus den Differenzen der Zählerstände
> (`core/berechnungen/bilanz_zeitraum.py::komponiere_bilanz_zeitraum`, PV-Teil `pv_verteilung.py::loese_pv_zeitraum_auf`):
>
> 1. **Quelle je Gerät:** ein Gerät, dessen Kanal den Zeitraum voll deckt, trägt sein Δ — auch wenn im Inneren Stunden fehlen
>    (ihre Menge steht wie in HA in der Folgestunde). Gemessene Werte werden nie skaliert.
> 2. **Rest des Anlagenzählers:** `max(0, Δ Anlagenzähler − Σ Δ gemessene Geräte)` geht einmal je Zeitraum nach kWp auf die
>    Geräte ohne deckenden Kanal (Marke „geschätzt (kWp-Anteil)"); die Modul-Kinder eines Balkonkraftwerks sind dessen Lücke — am
>    Tag wie im Monat. Ein negatives Δ (HAs Summe fiel im Zeitraum, N-639) ist neben einem Anlagenzähler keine Messung für diese
>    Verteilung: das Gerät wird Lücke und bekommt seinen kWp-Anteil, wie im Bestandspfad ein Rücksprung (N-732). Ohne
>    Anlagenzähler bleibt das Δ stehen wie in HA.
> 3. **PV-Summe:** Σ der Geräte-Werte nach 1 und 2; der Anlagenzähler ist nur Füller, nie Ersatz der Geräte-Summe. Liegt Σ Geräte
>    über ihm, wird die Differenz als Wandlungsverluste geführt (`wandlungsverluste_kwh`) und — unter dem Messpunkt-Vertrag unten —
>    in Geld, USt und CO₂ abgezogen (N-588).
>
>    **Wandlungsverluste als geführte Größe (HA-Bauform E4b):** `wandlungsverluste_kwh = max(0, Σ Geräte − Δ Anlagenzähler)` je
>    Zeitraum, mit dem Bezug Σ Geräte (= Σ der String-Zähler vor dem Wechselrichter); Prozent = Verluste ÷ Σ Geräte × 100
>    (`pv_verteilung.wandlungsverluste_prozent`, Layer). Weg: Kanal-Leser (`services/kanal/bilanz_leser.als_monatssumme`) →
>    Monats-Fakten `ErzeugungFakten.wandlungsverluste_kwh` / `_bezug_kwh` — auch für abgeschlossene Monate, deren Mengen aus der
>    Zählerzeile kommen (die Fakten lesen den Kanal-Monat zusätzlich, wenn die Anlage einen Kanal `basis:pv_gesamt` hat) →
>    *Cockpit → Monat*, *Cockpit → Jahr* (Σ der Monate mit Wert, Prozent über die Monate, die Verluste UND Bezug tragen —
>    `quote_paarweise`), Übersicht und die Monatsreihe `/monatsdaten/aggregiert`. `None` ohne Anlagenzähler und ohne
>    Kanal-Deckung. **Bilanz und Bewertung (N-588, ADR-002/P15):** PV-Summe, Eigenverbrauch, Autarkie und Eigenverbrauchsquote
>    rechnen mit Σ Geräte — die Bilanz trägt die Verluste; **Ersparnis, Umsatzsteuer auf den Eigenverbrauch und CO₂** bewerten den
>    Eigenverbrauch **ohne** sie (`pv_verteilung.eigenverbrauch_ohne_verluste_kwh`) — eine im Wechselrichter verlorene kWh hätte
>    ohne PV-Anlage niemand gekauft (dieselbe Regel wie beim Speicher). Abgezogen wird nur unter dem **Messpunkt-Vertrag**
>    (`wandlungsverluste_grund`): (i) Anlagenzähler-Kanal mit voller Deckung; (iii) kein im Zeitraum aktiver DC-gekoppelter Speicher
>    (sonst misst der AC-Zähler Batterieflüsse mit; eine nicht gepflegte Kopplung gilt als DC, sobald der Speicher einem
>    Wechselrichter zugeordnet ist); (iv) Verluste ≤ 10 % der Σ Strings; (v) nicht ≥ 80 % der Erzeugung eines gemessenen
>    Balkonkraftwerks (dann misst der Anlagenzähler es offenbar nicht). Ein Gerät ohne eigenen Zähler braucht keinen eigenen Punkt:
>    bekommt es einen Rest des Anlagenzählers > 0, ist die Differenz 0; bei Rest 0 ist sie eine Untergrenze der echten Verluste.
>    Ohne gemessene Verluste kein Abzug — kein Verlustfaktor, keine Schätzung. Hält der Vertrag nicht, nennt `verluste_grund` den
>    Grund, und der Daten-Checker (Kategorie „Messpunkt") sagt, was zu tun ist. ⚠ Benannte Grenzen: die Schwellen 10 % und 80 %
>    sind konservativ gesetzt, nicht gemessen; bei einem sehr kleinen Balkonkraftwerk neben großen Strings kann (v) auch mit echten
>    Verlusten greifen — dann entfällt der Abzug. Die **Prognose** (Aussichten) nimmt ihre Eigenverbrauchsquote aus der Historie
>    inklusive Verluste.
> 4. **Entweder-oder:** je Zeitraum der erste Kanal einer Ersatzgruppe mit voller Deckung.
> 5. **Untergrenze 0 einmal je Zeitraum:** die Klemme wirkt je Zeitraum, nicht je Tag — in der Aufteilung je Gerät und, wenn ein
>    Gerät ohne eigenen Kanal den Rest des Anlagenzählers trägt, auch in der **PV-Summe und den Wandlungsverlusten**; an Tagen, an
>    denen der Rest klemmt, ist deshalb Σ Tage ≠ Monat um genau die am Tag geklemmte Menge (benannte Grenze, N-760).
>
> **Kein Deckel, kein Rücksprung-Verwurf:** eedc nimmt je Sensor seine Messung wie das HA-Energie-Dashboard. Ein
> Zählersprung aus HA steht deshalb in Tag und Monat; der Daten-Checker benennt ihn (Kategorie „Zählerstände – Sprung
> in Home Assistant", Muster Reset und Rückkehr auf den alten Stand). **Lückentag wie HA:** fehlen einem Zähler mehr
> als 24 Stunden, trägt der erste beendete Tag danach die ganze Lückenmenge; ein Tag ganz in der Lücke trägt 0 (er kommt trotzdem
> aus den Kanälen, nicht aus dem Bestand).
> **Quellenwahl:** je Tag und je Monat EINE Wahl für alle Eingänge der Gruppe — die Kanäle nur, wenn jeder benötigte
> Kanal den Zeitraum voll deckt; sonst rechnet der bisherige Leser den ganzen Zeitraum aus Tages- und Stundenzeilen
> mit den unten beschriebenen Regeln (**Bestandspfad**, Lesart 1 — für die Mengen nur Tage und Monate ohne volle Kanal-Deckung).
> Nicht umgestellt sind die E-Mobilitäts-Aufteilung derselben Monatszeile und die stundengepaarten Spalten (Direktverbrauch,
> Überschuss, Defizit) — sie bleiben aus den Stundenzeilen. Der Kalendermonat je Sensor („Aus HA laden", Import,
> Monatsabschluss-Vorschlag, HA-Weg von *Cockpit → Monat*) nimmt das Kanal-Δ, wenn die Spiegel aller Bilanz-Sensoren den
> Kalendermonat decken, sonst HAs Monatswert — auch dort ohne Deckel (§6b, „Wo der Plausibilitätsdeckel gilt").

> **Die PV-Achse über Tag, laufenden und abgeschlossenen Monat** (Richter ist die Abnahme-Matrix `backend/tests/test_pv_achse_matrix.py`):
>
> - **Tag, Anlagenzähler trägt ihn** (nicht jeder Erzeuger misst den ganzen Tag): ein Erzeuger mit eigenem Zähler behält seinen **Tageswert** (Σ seiner brauchbaren Stunden-Slots; ein Balkonkraftwerk mit Modul-Kindern den Rest nach ihnen, E4). Gemessen ist er, wenn kein Slot verworfen wurde, kein Tagesreset vorliegt und die Anlagen-Energie seiner Stunden ohne eigenen Slot plus seine Bündel-Energie höchstens **1 %** des Tages ist (`DAEMMERUNGSREST_ANTEIL`, eine Setzung). Die übrigen Träger teilen den Rest nach kWp (Marke `kwp_anteil`); übersteigen die Messungen den Anlagenzähler — oder misst jeder, aber mit anderer Summe —, werden sie gemeinsam auf ihn skaliert. Σ Tages-Keys = Σ Stunden. Layer: `core/berechnungen/pv_tages_praezedenz.py` (`gemessene_tageswerte`, `loese_aggregat_tag_auf`). Gespeicherte Tage nach älterer Regel heilen durch „Tag neu aggregieren" bzw. die Reparatur-Werkbank.
> - **Tag ohne HA-Stundenwerte:** liefert die Zählertabelle die PV-Achse, stehen in `komponenten_kwh` nur ihre PV-Keys — eine Leistungs-Summe der Kurve (`pv_gesamt`, `pv_<bkw>` neben `bkw_<bkw>`) steht nicht daneben (sie zählte doppelt).
> - **Laufender Monat (Cockpit → Monat):** die Quellen-Präzedenz steht in `core/berechnungen/datenquellen.py::gewinner_je_feld`; Merge und Teilzeitraum-Marke entstehen beide daraus. Ein Anlagenzähler aus der HA-Monatsstatistik oder MQTT ab Monatsbeginn misst den Monat bis jetzt und geht durch die P7-Auflösung: Quellen mit eigenem Wert gewinnen, er füllt den Rest (N-587). Grundgesamtheit sind die aktiven `pv-module` **und** Balkonkraftwerke (`erzeuger_traeger`, ein BKW mit Modul-Kindern tritt an sie ab); nur die Quellen HA-Statistik und MQTT, ein gespeicherter Wert (`gespeichert`) bleibt unberührt, ebenso der Connector mit Abdeckung (#361). Der abgeschlossene Monat liest den Zähler genauso (N-611, `pv_monatswerte.lade_pv_je_monat`). Code-Ort `aktueller_monat/aggregation.py::_anlagen_pv_zaehler` (Formel unten). Ersetzbar bleiben Tagesebene, MQTT-Rückfall, Connector ohne Abdeckung und im laufenden Monat auch der gespeicherte Zwischenstand und der Connector mit Abdeckung. Die eigene BKW-Zeile aus der Tagesebene nennt nur gemessene Tageswerte (`energie.bkw_gemessen_kwh_je_investition`).
>
>   ```
>   PV-Achse (Monat) = Σ gemessene Quellen + max(0, Anlagenzähler − Σ gemessene Quellen)   (Rest nach kWp auf die Quellen ohne Wert)
>   ```
>
> - **Gemessene 0 (Cockpit → Monat, laufend und ohne Abschluss):** hat eine Quelle im Monat **gemessen**, gilt ihr Wert auch, wenn er 0 ist — für Einspeisung, Netzbezug und den Anlagen-PV-Zähler sowie die Gerätefelder von Speicher, Balkonkraftwerk, Wallbox und E-Auto. Gemessen heißt bei der HA-Statistik mindestens **ein Intervall** (`SensorMonatswert.intervalle ≥ 1`: Anker + eine Zeile oder zwei Zeilen — eine einzelne Zeile misst nichts), bei der Tagesebene mindestens eine Stunde mit Wert (`TagesMonatsSumme.einspeisung_erfasst`/`netzbezug_erfasst`, nur diese zwei Felder). Ein nicht zugeordneter Zähler und einer ohne Zeilen im Monat bleiben `None` mit Grund. Auch im abgeschlossenen Monat mit Abschluss wirkt sie, wenn die gespeicherte Zeile für das Feld 0 trägt (Balkonkraftwerk, Speicher, Anlagen-PV-Zähler): das Feld zeigt dann 0,0 mit Herkunft Home Assistant statt „kein Wert"; eine gespeicherte Zahl über 0 wird nie verdrängt. ⛔ **Nicht** für Wärmepumpe und einzelne Strings: eine WP-0 bräuchte eine Darstellungsregel für „kein Betrieb", eine String-0 neben dem Anlagenzähler nähme dem String seinen Rest — beide bleiben bei „über 0". Benannt: ein eingefrorener Sensor mit weiterlaufenden Zeilen ist 0 (wie HA ihn zeigt); im laufenden Monat schlägt eine HA-0 den gespeicherten Zwischenstand wie jeder HA-Wert. Proben: `test_n585_gemessene_null.py`.
> - **Balkonkraftwerk mit Modul-Kindern:** der Monat tritt ab, in jeder Form — laufend, ohne Abschluss, abgeschlossen und im Tageswert-Rückfall der Monats-Fakten (`pv_verteilung.bkw_kinder_luecken_kwh`, Stufe 2 von P7; N-627). Gezählt werden nur Kinder, die im Monat aktiv sind (ADR-002/P11); der BKW-Wert füllt ihre Lücken (`max(0, BKW − Σ gemessene Kinder)` nach kWp), gemessene Kinder gewinnen, und das BKW trägt danach weder die PV-Achse noch eine eigene Zeile. Code-Ort `aktueller_monat/aggregation.py::_bkw_abtretung`. Der Tag bleibt bei E4.
> - **Modul ohne Wert, kein Gesamtwert:** die **Anzeige-Summe** nimmt die vorhandenen Werte (`pv_monatswerte.pv_teilsumme_je_monat`, `pv_vollstaendig=False`, Hinweis „Teilsumme"; der Daten-Checker nennt den Monat). Die **Prüf-Summe** `pv_summe_je_monat` bleibt `None` — Daten-Checker-PV-Map, Import-Vorschau und `gesamt_pv_kwh` prüfen nur vollständige Monate (N42 gilt nur für die Prüf-Leser).
> - **Tageswert-Rückfall der Monats-Fakten** (`services/monats_fakten/bau.py`, Phasen von `_baue_fakt`; N-121/N-627/N-626/N-725): ergibt die P7-Auflösung für einen Monat **nichts** (`None` — kein Modulwert, kein Anlagenwert) und ist die Tagesebene geladen (mit `inkl_nur_tageswerte` oder für den Ladeanteil, `laden.py::_tagesebene`), trägt die **Modulsumme der Tage**: die Tages-Keys der Module plus die Tages-Keys der Balkonkraftwerke, die im Monat an aktive Modul-Kinder abgetreten haben (`abgetretene_bkw_ids` über die aktiven `pv-module`/`balkonkraftwerk`; N-627 — eine Umbuchung zwischen den beiden Gruppen, die Summe bleibt). Ein aufgelöster Wert, auch ein teilweise geschätzter, wird nie überschrieben; erst danach nimmt der Monat die Teilsumme der vorhandenen Modulwerte (N-626). Reihenfolge: **vollständige Summe → Tageswert → Teilsumme**. `pv_vollstaendig` folgt den Modulen auch im Rückfall (N-725): wahr nur, wenn die P7-Summe vollständig war oder der Monat gar keinen Modulwert trägt (der laufende Monat) — ein Monat mit Modul-Lücke bleibt „Teilsumme", auch wenn die Tagesebene die Zahl liefert. Code-Ort `_pv_aus_tagen`.
>
>   **BKW-Rest (N-640):** trägt der Monat weder eine BKW-Zeile noch einen BKW-Anteil am Anlagenwert (N-621), kommt die BKW-Erzeugung aus den Tagen (`Tages_BKW` = BKW-Tages-Keys ohne die abgetretenen). Ist ein Teil davon nur ein kWp-Anteil am Anlagenzähler der Tage (Balkonkraftwerk ohne eigenen kWh-Zähler, Tages-Key mit Marke `kwp_anteil`, N-628) und kommen die Module aus **gespeicherten, vollständigen** Monatswerten (nicht aus den Tagen), bekommt das Balkonkraftwerk den Rest des Anlagenzählers:
>
>   ```
>   BKW_Monat = Tageswert_BKW_gemessen + max(0, Σ Tages_Module + Σ Tages_BKW − Modulsumme_Monat − Tageswert_BKW_gemessen)
>     Tages_Module           = Tages-Keys der Module + abgetretene BKW-Tages-Keys (N-627)
>     Tageswert_BKW_gemessen = min(Tages_BKW, Σ BKW-Tages-Keys ohne kwp_anteil)
>   ```
>
>   Kommen die Module selbst aus den Tagen oder sind sie nur eine Teilsumme, bleibt der Tageswert (dann sind beide Seiten Anteile derselben Tage). Ein Ergebnis 0 setzt keine Tageswert-Marke. Code-Ort `_bkw_rest`; `pv_kwh = Modulsumme + BKW + BKW-Anteil am Anlagenwert` steht in `_erzeugung` (N-621), dort auch die Wandlungsverluste aus dem Kanal-Monat (N-588).

**Die übrigen BKW-Monatsgrößen** (`BkwFakten.eigenverbrauch_gemessen_kwh`, `.speicher_ladung_kwh`, `.speicher_entladung_kwh`) sind die
Summen der Felder `eigenverbrauch_kwh`, `speicher_ladung_kwh` und `speicher_entladung_kwh` aller BKW-Zeilen des Monats
(`imd_typ_beitrag` → `monats_fakten/roh.py::_falte_bkw` → `bau.py::_bkw_fakten`) — auch für ein Balkonkraftwerk, das an Modul-Kinder
abgetreten hat oder einen Anteil am Anlagenwert bekommt; dort fallen nur Erzeugung und Rest-Eigenverbrauch weg.
`eigenverbrauch_gemessen_kwh` ist der rohe Wert für die Anzeige; die Finanz-Zeile nimmt `rest_eigenverbrauch_kwh` (P9, §3.2 „Finanzielle
Kennzahlen").
Aus dem angezeigten Paar Erzeugung/Eigenverbrauch bildet die Cockpit-Antwort (Monat, Jahr-Kopf nach der Faltung, Jahr-Monate) **Einspeisung**
`bkw_einspeisung_kwh` = Erzeugung − Eigenverbrauch und **EV-Quote** `bkw_eigenverbrauch_quote_prozent` = Eigenverbrauch ÷ Erzeugung × 100
(`core/berechnungen/bkw_finanz.py`, `computed_field` am Antwortmodell; ohne Eigenverbrauch — etwa am Tag — fehlen beide). Seit Päckchen
Z-Client (9.11.2026); vorher rechnete der Block Balkonkraftwerk sie im Client.

> **Lesequelle der Monatsgrößen ist `services/monats_fakten/::lade_monats_fakten`** (ADR-002/**P10**, [Konzept](KONZEPT-MONATS-FAKTEN.md)).
> Sie liefert die **ganze** Monatszeile kanonisch aufgelöst — die PV ist darin ein Feld (`erzeugung.pv_module_kwh` bzw.
> `erzeugung.pv_kwh`), daneben stehen Zähler, Speicher, E-Mobilität, Wärmepumpe, Sonstiges, Tarif, §51 und die
> Verbrauchs-Kennzahlen. Sie **ruft** `lade_pv_je_monat` (die P7-Regel bleibt unverändert) und wendet **einmal** alle Zeitfilter
> (`aktiv` · Anschaffung · Stilllegung) und den Dienstwagen-Filter an. Wer eine abgeleitete Monatsgröße auswertet, nimmt sie von
> dort; `lade_pv_je_monat` direkt zu rufen bleibt richtig, wo **nur** die Pro-Modul-PV gebraucht wird (String-Vergleich,
> PV-Diagnose). Ausgenommen sind Schreib-, Import- und Checker-Pfade — die Schicht ist reines Lesen.

> **Ein Name, drei Größen:** `pv_erzeugung_kwh` ist die **DB-Spalte** `Monatsdaten.pv_erzeugung_kwh` (manuelles
> Gesamt-Aggregat, s. o.), der **Schlüssel in `InvestitionMonatsdaten.verbrauch_daten`** (Erzeugung *dieses einen* Moduls) und das
> **Response-Feld** von `/monatsdaten/aggregiert` (PV-Module **+** Balkonkraftwerk). Der Identifier bleibt, weil er zugleich
> MQTT-Topic-Segment, CSV-Spaltenname und Backup-Feld ist. Siehe [Glossar](GLOSSAR.md#energie--bilanzen).
>
> ⛔ **Der Wechselrichter ist kein PV-Erzeuger:** `PV_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")`, baumweit. Das Feld
> `wechselrichter/pv_erzeugung_kwh` liest niemand; es trägt `nur_bestand`, erscheint nur, solange eine alte Zuordnung daran hängt,
> und der Daten-Checker sagt, wohin sie gehört (#388). **Wer die Gruppe `pv_energie` erweitern will, liest zuerst den Wächter**
> `test_wechselrichter_kein_pv_erzeuger.py::test_es_gibt_genau_drei_pv_energie_quellen`: er hält Eingabe-Registry und Rechen-Kern
> gegeneinander.

### Schicht 2: Berechnungslogik

| Datei | Funktionen | Beschreibung |
|-------|-----------|-------------|
| `services/monats_fakten/` | `lade_monats_fakten()`, `finanz_zeile_eingabe()`, `kennzahlen_aus_fakten()` | **Eingabe-Aufbereitung, keine Formel** (ADR-002/P10): löst die Monatszeile einmal auf und ruft die SoT-Helfer. Vorschaltet jeder aggregierenden Lese-Sicht |
| `core/calculations.py` | `berechne_monatskennzahlen()`, `berechne_speicher_einsparung()`, `berechne_eauto_einsparung()`, `berechne_waermepumpe_einsparung()`, `berechne_roi()` | Reine Berechnungsfunktionen ohne DB-Zugriff |
| `core/berechnungen/ust_eigenverbrauch.py` | `berechne_ust_eigenverbrauch()` | USt auf den Eigenverbrauch (§3.7) |
| `api/routes/cockpit/` | Endpunkte `uebersicht`, `prognose-vs-ist`, `nachhaltigkeit`, `komponenten-zeitreihe`, `pv-strings` u. a. | Aggregation aller Daten für Dashboard |
| `api/routes/aussichten/` | 5 Endpunkte | Prognosen (`prognose.py`, `trend.py`, `wetter.py`) und Finanz-Prognose (`finanzen.py` als Orchestrator, Phasen in `finanz_eingaenge.py` · `finanz_rueckblick.py` · `finanz_prognose.py` · `finanz_zerlegung.py`) |
| `api/routes/investitionen/` | ROI-Dashboard (`roi.py::get_roi_dashboard`) | PV-System-Gruppierung und ROI pro Komponente |
| `api/routes/strompreise.py` | `lade_tarife_fuer_anlage()` | Multi-Tarif-Lookup mit Fallback |
| `utils/sonstige_positionen.py` | `berechne_sonstige_summen()` | Strukturierte Erträge/Ausgaben |
| `services/energie_profil/` (Fassade `services/energie_profil_service.py`) | `aggregate_day()`, `rollup_month()`, `backfill_range()` | Tages-Aggregation + Monats-Rollup |

### Schicht 3: Frontend-Anzeige

Die **Sicht** (Spalte „Wo in v4") folgt der Achsen-Navigation (Cockpit = Zeit-Achse, Komponenten = Was-Achse, Auswertungen = Wie-Achse — siehe [Bedienung](HANDBUCH_BEDIENUNG.md#1-navigation--grundprinzip)):

| Wo in v4 | API-Endpoint | Angezeigte Kennzahlen |
|-------|-------------|----------------------|
| [Cockpit → Monat/Jahr](HANDBUCH_BEDIENUNG.md#2-cockpit--die-zeit-achse) | `GET /api/cockpit/uebersicht/{id}?jahr=` | Autarkie, EV-Quote, Netto-Ertrag, Rendite, CO2 |
| [Auswertungen → Prognose](HANDBUCH_BEDIENUNG.md#43-prognose-genauigkeit-gegen-ist) | `GET /api/cockpit/prognose-vs-ist/{id}?jahr=` | Performance Ratio pro Monat |
| [Cockpit → Jahr/Gesamt](HANDBUCH_BEDIENUNG.md#24-jahrgesamt) · [Auswertungen → CO₂](HANDBUCH_BEDIENUNG.md#4-auswertungen--die-wie-achse) (§4.4) | `GET /api/cockpit/nachhaltigkeit/{id}` | CO2-Zeitreihe (Block „CO₂-Bilanz"), Äquivalente, Amortisation — **die eine CO₂-Quelle beider Sichten** ([§3.8](#38-co2-bilanz)) |
| [Komponenten](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse) (je Typ) | `GET /api/cockpit/komponenten-zeitreihe/{id}` | Speicher-Effizienz, WP-JAZ, E-Auto PV-Anteil |
| [Komponenten → PV-Anlage](HANDBUCH_BEDIENUNG.md#32-pv-anlage) | `GET /api/cockpit/pv-strings/{id}?jahr=` | SOLL vs IST pro String |
| [Auswertungen → ROI](HANDBUCH_BEDIENUNG.md#42-roi) | `GET /api/investitionen/roi/{id}` | ROI%, Amortisation pro System |
| [Auswertungen → Tabelle](HANDBUCH_BEDIENUNG.md#45-tabelle-werte-werkbank) | `GET /api/monatsdaten/aggregiert/{id}` | Spalten-Explorer, Vorjahres-Delta |
| — (nur API, ohne Aufrufer in der Oberfläche) | `GET /api/aussichten/kurzfristig/{id}` | 7-Tage PV-Prognose (**ohne** SFML — `api/routes/aussichten/` kennt die Quellenwahl nicht) |
| [Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) | `GET /api/aussichten/langfristig/{id}` | 12-Monats-Prognose |
| [Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) | `GET /api/aussichten/trend/{id}` | Degradation, Jahresvergleich |
| [Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen) | `GET /api/aussichten/finanzen/{id}` | Amortisations-Fortschritt, Prognose |

**Anzeige-Ableitungen im Client (benannte Grenzen, Stand Päckchen BB 9.11.2026).** Der Client rechnet nichts (ADR-001) —
bis auf zwei Kennwerte der Werte-Tabelle, die er im Monat aus zwei Feldern der Antwort von `GET /api/monatsdaten/aggregiert`
bildet (`pages/auswertung/types.ts::createMonatsZeitreihe`); der Tag kommt bei beiden fertig aus `services/energie_profil/tage_werte.py`.
Eine Backend-Größe des Monats gibt es für sie nicht, eine neue braucht Regel-Abschnitt und Entscheid:

| Kennwert | Client-Bildung im Monat | Warum (noch) kein Backend-Feld |
| --- | --- | --- |
| `spezErtrag` (M2) | `pv_erzeugung_kwh ÷ anlagen_kwp` (`lib/calculations.ts::calcSpezifischerErtrag`) | Der Sensor `spezifischer_ertrag_kwh_kwp` ist **aufs Jahr normiert** (§3.1, `core/berechnungen/spez_ertrag.py`) — eine andere Größe; der Tageswert steht in `tage_werte.py` ohne Layer-Funktion. |
| `ev_ersparnis` (M2) | `ev_ersparnis_euro + bkw_ersparnis_euro` | Das Finanz-Aggregat weist beide Posten getrennt aus (§3.2); eine Summe beider gibt es im Backend nicht. |

Seit Päckchen Y nicht mehr darunter: die **CO₂-Äquivalente** (§3.8 «Äquivalente», Layer `co2_aequivalente`) und die
**Speicher-Effizienz** des Monats (`speicher_effizienz_prozent`, Layer `speicher_wirkungsgrad` auf Ladung und Entladung der Zeile, §3.3);
seit Päckchen Z-Client der **Wallbox-PV-Anteil** (`wallbox_pv_anteil_prozent`, Layer `pv_anteil_prozent` auf den zwei Feldern der Zeile,
ungerundet — die Tabelle rundet und mittelt, §3.4 «PV-Anteil der Heimladung»); seit Päckchen BB die **Speicher-Bilanz**
(Bilanz, Verlust, Wirkungsverluste, Netzlade-Kosten, PV-Ladung, Solar-Anteil, Jahresbilanz — Layer `speicher_bilanz`, §3.3
«Speicher-Bilanz») und die **SOLL-Erreichung des Tages** (`tag-detail.soll_erreichung_prozent`, §3.5d «Die Tageszahlen von *Cockpit → Tag*»);
im Nachlauf von Päckchen BB der **PV-Anteil (Heim) der E-Mobilität** (`emob_pv_anteil_prozent` an Monat/Jahr und am Tagesdetail,
Layer `pv_anteil_prozent`; am Tag samt der Ladung selbst, «Ladung des Tages» bei *Fahrt heute*) und der **spezifische Ertrag der
PV-Strings** (Jahr: `pv-strings.spezifischer_ertrag_kwh_kwp`, «alle Jahre»: die Laufzeit-Route, §3.9 «Alle Jahre»).

**Die übrigen Rechenstellen der Sichten** stehen in der Baseline des Wächters (`frontend/rechenstellen-baseline.txt`, Stand
Päckchen BB: 23) und haben einen dieser Gründe:

| Grund | Stellen |
| --- | --- |
| **Vorzeichen / Richtung** — kein Fachwert, nur «bezieht» oder «speist ein» | `EnergieFluss.tsx::netzRichtung`, `TagVerlaufChart.tsx::baueChartDaten` |
| **Hinweis-Delta / Bedingung** — die Differenz wird nicht als Zahl gezeigt, sie entscheidet nur, ob ein Satz erscheint (die Zahlen daneben kommen aus der Antwort) | `SolarAussicht3Tage.tsx` (2), `waermeVerteilung.ts::verteilungHinweise` (2), Wärmepumpe «Aufgeteilte Menge X von Y kWh» (`KomponentenSektionen.tsx` 2, `WaermepumpeModusSplit.tsx`; W-17b, §3.5e) |
| **Vergleichs-Delta / Sortierung** — Abstand zweier gelieferter Werte | Community (`CommunityPVErtragTeile.tsx` 3, `CommunityRegionalTeile.tsx` 4, `CommunityTrendsTeile.tsx`), `StrompreiseTeile.tsx` (Preis-Delta), `SpeicherSizingIST.tsx` (Delta zur Basis) |
| **Balkenbreite** — Geometrie | `AussichtTeile.tsx` (2) |
| **Live-Auslastung kW ÷ kWp** — die PV-Gruppe faltet der Client aus ihren Mitgliedern (`energieFlussLayout.ts`), ein Feld je Komponente deckte sie nicht | `EnergieFluss.tsx` (Kachel-Tooltip), `GruppenListeOverlay.tsx` |

**Eine Formel, ein Ort — gewächtert (Päckchen Z3, 9.11.2026):** eine neue Rechenstelle außerhalb des Layers (Quote oder
Differenz zweier Mengen, Menge × Preis oder × Literal, Preis ÷ Menge, im Client auch Menge ÷ Leistung) macht
`backend/tests/test_dezentrale_rechenstellen.py` bzw. `npm run check:rechenstellen` rot; der Bestand steht in einer Baseline,
die nur schrumpft (ADR-001).

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

Definiert in `core/berechnungen/heizgradtage.py`:

| Konstante | Wert | Einheit | Verwendung |
|-----------|------|---------|-----------|
| `HEIZGRENZE_C` | 15.0 | °C | Heizgradtage — Temperaturkorrektur der Verbrauchsprognose **und** wetternormierter Vergleich (§3.5f). Gradtag-Konvention, **keine** Innenraum-Temperatur. **Eine** Definitionsstelle, gewächtert von `test_berechnungs_layer_konformitaet.py::test_heizgrenze_nur_im_layer` |

Prognose-Konstanten:

| Konstante | Wert | Ort | Verwendung |
|-----------|------|-----|-----------|
| `DEFAULT_SYSTEM_LOSSES` | 0.14 (14%) | `services/pv_orientation.py` | Kurzfrist-PV-Prognose |
| `TEMP_COEFFICIENT` | 0.004 (0.4%/°C) | `api/routes/aussichten/basis.py` | Leistungsabnahme über 25°C |
| Konfidenz-Faktor | 0.15 (15%) | `api/routes/aussichten/prognose.py` (`konfidenz_faktor`) | Langfrist-Konfidenzband |

**Vorgabewerte, wenn nichts gepflegt ist** (Gaspreis, Wirkungsgrade des alten Energieträgers, Benzin-Verbrauch und -Preis,
Einspeisevergütung, Netzbezugspreis, externe Ladung), stehen in `core/wirtschaftlichkeit_defaults.py` — die Zahlen nur dort; gelesen
u. a. von `services/wp_wirtschaftlichkeit.py`, `services/eauto_wirtschaftlichkeit.py` und `core/calculations.py`.

---

## 3. Berechnungsketten nach Thema

### 3.1 Energie-Bilanz (Monatskennzahlen)

**Funktion:** `berechne_monatskennzahlen()` in `core/calculations.py`
**Verwendet in:** `GET /api/monatsdaten/{id}` (`api/routes/monatsdaten.py`, Antwortfeld `kennzahlen`); die übrigen Sichten rechnen
die Bilanz über die Layer-Funktion `berechne_verbrauchs_kennzahlen` (Kästen unten).

#### Eingabefelder

Felder, Einheiten und Quellen je Typ stehen in der [Übersicht der Größen §1](UEBERSICHT-GROESSEN.md#1-eingabefelder) und in der
[Sensor-Referenz](SENSOR-REFERENZ.md). Regeln an den Eingängen dieser Rechnung:

- **Erzeugung:** die PV-Achse des Monats aus den Monats-Fakten (`ErzeugungFakten.pv_kwh`, PV-Module + Balkonkraftwerk, P7).
- **Einspeisevergütung:** Tarif (`Strompreis.einspeiseverguetung_cent_kwh`); bei variabler Vergütung schlägt der Monatswert
  `Monatsdaten.einspeise_durchschnittspreis_cent` (#392, `resolve_einspeise_preis_cent`).
- **Netzbezugspreis:** Tarif-Arbeitspreis, ein gepflegter dynamischer Ø (`netzbezug_durchschnittspreis_cent`, HA-Sensor oder
  Monatsdaten) schlägt ihn (Kaskade im Kasten „Welcher Preis gilt").
- **Grundpreis:** Σ `Strompreis.grundpreis_euro_monat` aller im Monat gültigen Tarife — allgemein plus ein **eigener**
  Wärmepumpen-/Wallbox-Tarif (N-769, `monats_fakten.grundpreis_des_monats`).
- **Netzbezug zum WP- bzw. Wallbox-Tarif** (`netzbezug_eigener_tarif_kwh`, Typ waermepumpe bzw. wallbox, optional): die Menge, die
  der Versorger zum eigenen Komponenten-Tarif abrechnet (N-770/N-771). Wirkt nur mit eigenem Tarif dieser Verwendung; je Typ im
  Monat summiert; ohne Feld an einem Gerät mit Strom bzw. Ladung > 0 gilt der Monat als nicht gemessen (F3).
- **Leistung (kWp)** für den spezifischen Ertrag: Σ der am Monatsende aktiven Erzeuger, Module **und** Balkonkraftwerke (ein an
  Modul-Kinder abgetretenes Balkonkraftwerk zählt über seine Kinder, N-266); `Anlage.leistung_kwp` nur, wenn diese Summe 0 ist
  (`core/berechnungen/anlagen_kwp.py::anlagen_kwp`, `mit_bkw=True`). Zähler und Nenner dieselbe Grundgesamtheit (F-58, N-386).

#### Formeln

```
Erzeugung_gesamt    = PV_Erzeugung + BKW + sonstige_Erzeuger   (hinter dem Zähler)
Direktverbrauch     = max(0, Erzeugung_gesamt - Einspeisung - Batterie_Ladung)
Eigenverbrauch      = Direktverbrauch + Batterie_Entladung + V2H_Entladung − Abgabe_an_Dritte   (§9.2)
Gesamtverbrauch     = Eigenverbrauch + Netzbezug
Restverbrauch       = Gesamtverbrauch − Wärmepumpe − Wallbox/E-Auto − sonstige erfasste Verbraucher   (nur Stunde/Live, s. u.)
EV-Quote (%)        = Eigenverbrauch / Erzeugung_gesamt * 100   (wenn Erzeugung > 0)
Autarkie (%)        = Eigenverbrauch / Gesamtverbrauch * 100    (wenn GV > 0)
Spez. Ertrag        = PV_Erzeugung / Leistung_kWp              (kWh/kWp, NUR PV; zwei Varianten, s. u.)

Einspeise-Erlös (EUR)    = (Einspeisung - Einspeisung_neg_Preis) * Einspeisevergütung / 100
Netzbezug-Kosten (EUR)   = (Netzbezug − N_WP − N_WB) * Netzbezug_Preis / 100
                           + N_WP * WP_Tarif / 100 + N_WB * Wallbox_Tarif / 100 + Grundpreis   (N-770/N-771, s. Kasten)
                           gemeinsamer Zähler WP + Wallbox (F12): (Netzbezug − N_g) * Netzbezug_Preis / 100
                           + N_g * W_g / 100 + Grundpreis (W_g einmal)   (s. Kasten „Gemeinsamer Zähler")
Arbeitspreis-Kosten (EUR)= dieselbe Summe ohne Grundpreis                (reiner Ausweis)
EV-Ersparnis (EUR)       = (PV_Eigenverbrauch − P_WP) * EV_Preis / 100 + P_WP * WP_Tarif / 100
                                                                          (s. Hinweis; EV_Preis = EV-gewichteter Ø der Stundenpreise, sonst Netzbezug_Preis)
Netto-Ertrag (EUR)       = Einspeise-Erlös + EV-Ersparnis + BKW-Rest-Ersparnis + Erlös_eigener_Satz
                           + Sonstige_Netto − Dienstliche_Ladekosten − USt-Anteil_Eigenverbrauch
                                                                          (Stufe 1 der Ergebnis-Leiter, §3.2)
CO2-Einsparung (kg)      = Eigenverbrauch_ohne_Wandlungsverluste * 0.38   (berechne_co2_bilanz, nur PV-Anteil; N-647 — s. Kasten)
```

> **Eine Eigenverbrauchs-Formel auf jeder Zeitebene (N-635).** Die Formel oben gilt für Monat, Jahr, Live **und den Tag**:
> Cockpit → Tag (Kachel, Bilanz-Zeile, Tageswerte-Tabelle), die Tagessumme im Verlauf von Cockpit → Monat, der Monat aus
> Tageswerten (ohne Abschluss) und die Tagesprognose rechnen sie über dieselbe Layer-Funktion `berechne_verbrauchs_kennzahlen`
> (Tag: `core/berechnungen/tagesbilanz.py`) — die Formel des HA-Energie-Dashboards (`used_solar` + `used_battery`). Mit dem
> Tages-Eigenverbrauch rechnen EV-Quote, CO₂ (PV) und Eigenverbrauchs-Ersparnis des Tages (die Tagesfinanz bekommt Ladung und
> Entladung mit); der Tag zieht die Abgabe an Dritte als gemessene Tagesmenge ab. **V2H am Tag** (#110, Konzept
> `KONZEPT-110-RESTPUNKTE.md` §2): die V2H-Rückspeisung ist eine Tagesgröße aus dem Zählerpfad (Snapshot/MQTT und
> HA-Langzeitstatistik über die Beitragsschicht, Tagesschlüssel `komponenten_kwh["v2h_<id>"]`); Stunden tragen sie nicht, einen
> Kanal hat sie nicht. Sie geht als eigener Summand in Eigenverbrauch und Gesamtverbrauch (`tagesbilanz.mit_v2h_entladung` →
> `gesamtverbrauch_ha_formel_kwh`, `berechne_verbrauchs_kennzahlen(v2h_entladung_kwh=…)`), an einem Kanal-Tag nach dem Mischen —
> genau einmal. Der laufende Monat aus Tagen trägt V2H nicht (bis zum Abschluss 0, §2.6). Der Verlauf in Cockpit → Monat stapelt die
> Erzeugung als **Direktverbrauch + Speicherladung + Einspeisung** (wie die Verwendung im PV-Hub).
>
> **Benannte Rest-Abweichung — Σ Tage ≠ Monat an Tagen mit Netzladung.** Lädt der Speicher an einem Tag mehr, als PV nach der
> Einspeisung übrig ist (Netzladung), klemmt der Tag den Direktverbrauch bei 0; der Monat rechnet aus den Summen und verrechnet die
> Netzladung mit dem PV-Überschuss anderer Tage. Dieselbe Netzladung steht im Verlauf als Speicherladung — an solchen Tagen liegt der
> Stapel um sie über der PV. Ein Tag aus dem Altbestand (ohne Regelmarke) mit mehr Einspeisung als PV nennt den Eigenverbrauch 0 statt
> einer negativen Zahl (N-635) — dieselbe Klemme wie Tag und Monat nach R7 (Vorlage §10).

> **Gesamtverbrauch und Restverbrauch — zwei Wörter, zwei Zahlen (N-603).** Der **Gesamtverbrauch** ist alles, was das Haus
> verbraucht hat (Eigenverbrauch + Netzbezug) — Live-Kachel, Tag/Monat/Jahr-Bilanz. Der **Restverbrauch** ist der Teil davon, den
> kein einzeln erfasstes Gerät erklärt; er entsteht **je Stunde** im Client (`components/tag/TagWerteTabelle.tsx::berechneHausverbrauch`,
> dieselbe Differenz im Stundenverlauf) und **live** als Residual der Leistungen (`services/live_komponenten_builder.py`, Tagesverlauf
> `services/live_tagesverlauf_service.py`). **Je Monat oder Jahr gibt es ihn nicht als eigene Kennzahl** (nur als Kategorie
> „Restverbrauch" in der Monatsauswertung „Verbrauch nach Kategorie"). Das Wort „Hausverbrauch" steht nur als Herstellerbegriff in
> Anführungszeichen (s. u.); Wächter `npm run check:begriffe` und `backend/tests/test_begriffe_anwendertexte.py`.

> **Hinweis „EV_Preis" (SOLL Flex-Tarife A-2).** Die Ersparnis bewertet **vermiedenen** Bezug, und der fällt zu anderen Zeiten an
> als der tatsächliche (Eigenverbrauch mittags, Netzbezug abends). Bei einem dynamischen Tarif wird die vermiedene Menge deshalb mit
> dem Ø der Stundenpreise **in den Stunden des vermiedenen Bezugs** bewertet (Gewicht je Stunde: max(0, PV − Einspeisung)), nicht mit
> dem bezugsgewichteten Ø. Tag: `SlotKosten.ev_mittel_cent`, Monat: `MonatsPreis.ev_cent` aus derselben Messung
> (`strompreis_aggregator`); `baue_finanz_zeile` reicht ihn an alle Sichten durch — auch an Cockpit → Monat samt Vorjahresmonat und
> Balkonkraftwerk-Zeile des T-Kontos (Antwortfeld `ev_preis_cent`, Herkunft `ev_preis_herkunft`: „ev_gemessen" oder die Herkunft des
> Bezugspreises; die Stromrechnung bleibt beim Bezugspreis). **P-1:** ein gepflegter (abgerechneter) Bezugs-Ø stellt den Bezugspreis,
> für die Ersparnis ist er nur der Rückfall — unterhalb der Abrechnung gilt die Messung. Ohne Stundenpreise (Festpreis) bleibt es beim
> Netzbezug_Preis. Der **Vorjahresmonat** löst seinen Bezugspreis über dieselbe Kaskade (`aufgeloester_monatspreis`).
>
> **Cockpit → Monat rechnet die Bilanz über den Layer.** Eigenverbrauch, Direktverbrauch, Gesamtverbrauch, Autarkie und EV-Quote des
> Monats kommen aus `berechne_verbrauchs_kennzahlen` — dieselbe Funktion wie Monats-Fakten, Übersicht, Monatsreihe, PDF und
> HA-Export —, mit der **V2H-Entladung** aus den gespeicherten Gerätewerten des Monats (im laufenden Monat ohne gespeicherten Wert 0).
> Der Vorjahres-Block wird aus der Monatsantwort des Vorjahresmonats gelesen, nicht eigens gerechnet; damit läuft der Vorjahresmonat
> durch dieselbe Quellen-Kaskade (gespeicherte Werte, Connector, Home-Assistant-Statistik — mit angebundenem HA fragt ein Aufruf die
> Statistik für zwei Monate ab). Schlägt die Berechnung des Vorjahresmonats fehl, antwortet der Monat ohne Vorjahresvergleich und nennt
> das in seinen Hinweisen.
>
> **Hinweis „Eigenverbrauch".** Der Eigenverbrauch, der zu **Geld** wird, ist derselbe wie der in der Mengen-Bilanz: die Erzeugung
> **hinter dem Zähler** — PV-Module, Balkonkraftwerk **und** ein Erzeuger unter *Sonstiges* (BHKW, Windrad, Wasserkraft). Der Zähler
> am einen Netzanschluss misst die Summe aller Erzeuger dahinter; Menge und Betrag meinen dieselbe Kilowattstunde.
>
> ⚑ **Nicht bewertet wird das GERÄT, nicht sein Strom.** Ein sonstiger Erzeuger bekommt keine eigene Ertrags-Zeile und keine
> Wirtschaftlichkeit — sein Ertrag wird am Gerät als `Investition.einsparung_prognose_jahr` („Ertrag/Jahr") gepflegt, weil eedc seinen
> Brennstoff nicht kennt. Beide Größen liegen in **derselben** Summe (`jahres_netto_ertrag` in
> `aussichten/finanz_prognose.py::jahres_alternativkosten`) — würde die Menge zusätzlich monetarisiert, stünde derselbe Nutzen zweimal darin.
>
> ⭐ **Ausnahme — die Kategorie *Abgabe an Dritte* (§9.2 Geldseite).** Dort ist der Ertrag **gemessen**: das Gerät führt je Monat ein
> Feld „Erlös (€)", und der Jahres-Ertrag der ROI-Zeile ist `Σ Monatserlöse ÷ Monate mit Wert × 12` — hochgerechnet **mit der eigenen
> Monatszahl** (F-20). **Vorrang: gemessen vor geschätzt** — liegt auch nur ein Monatswert vor, schweigt „Ertrag/Jahr" und wird nicht
> addiert (Bauform wie ADR-002/P7). Eine gepflegte **0** ist eine Aussage („unentgeltlich abgegeben") und macht die Zeile bewertet; ohne
> beides bleibt sie „nicht bewertet" — nie 0 € (N-87/N-258). **Die eine Quelle ist `core/berechnungen/investitions_jahresertrag.py`**,
> gelesen von ROI-Dashboard, Aussichten-Prognose und HA-Export.
>
> ⛔ **Die drei lesen sie mit VERSCHIEDENEN Laufzeit-Filtern, und das ist Absicht:** das ROI-Dashboard ohne Jahresfilter behält
> stillgelegte Geräte (#123 — „spätere Stilllegung darf Vergangenheit nicht löschen"), Aussichten und HA-Export filtern auf *heute
> aktiv*, weil sie Prognosen sind. Wächter: `test_abgabe_geldseite_drei_sichten.py::test_die_zwei_umfaenge_bleiben_verschieden`.
>
> ⚠ **Asymmetrie zwischen den beiden Prognosen:** im **HA-Export** steckt der gemessene Erlös bereits in der Anlagenbilanz
> (`netto_ertrag_euro`); dort zählt nur der *geschätzte* Posten zusätzlich (sonst stünde er in `jahres_ersparnis_euro` doppelt). In
> den **Aussichten** ist er in keiner anderen Prognose-Größe enthalten und wird voll addiert.

> ⚠ **Folge für die Anzeige:** bei einer Anlage mit sonstigem Erzeuger geht `Eigenverbrauch × Preis = EV-Ersparnis` **nicht** auf;
> das T-Konto beschriftet die Zeile dann als *PV-Eigenverbrauch-Ersparnis* und zeigt die Multiplikation nicht an (N-131).

> **Die CO₂-Zeile von `berechne_monatskennzahlen`** (`kennzahlen.co2_einsparung_kg` in `GET /api/monatsdaten/{id}`) rechnet über
> `berechne_co2_bilanz` auf dem Eigenverbrauch ohne Wandlungsverluste (`eigenverbrauch_ohne_verluste_kwh`; N-647, DI-2/P15) und trägt
> nur den PV-Anteil (`co2_pv_kg`), ohne Wärmepumpe und E-Mobilität; keine Sicht liest das Feld. Die CO₂-Bilanz der Anlage ist **§3.8**.

> **Die Stromrechnung mit Anteilen zum Komponenten-Tarif (N-770/N-771).** Gilt ein **eigener** Wärmepumpen- bzw. Wallbox-Tarif und
> ist an der Komponente das Feld **„Netzbezug zum WP-Tarif"** bzw. **„Netzbezug zum Wallbox-Tarif"** gemessen (N, die Menge, die der
> Versorger zu diesem Tarif abrechnet), rechnet die Stromrechnung zwei bzw. drei Arbeitspreise: der Rest des Netzbezugs zum
> Haushaltspreis, N zum Komponenten-Tarif (WP: `TarifFakten.wp_preis_cent`, Wallbox: `wallbox_preis_effektiv_cent` — derselbe Preis,
> zu dem die E-Mob-Ersparnis die Netzladung bewertet). Ohne Feld oder ohne eigenen Tarif fließt kein Anteil ein. Gemessen wird N z. B.
> in einer Zählerkaskade als *Z1-Bezug − Z2-Bezug*; ein eigener Zähler, der nicht hinter der PV hängt, ist N selbst. Mit N rechnet
> zusätzlich die EV-Ersparnis den PV-Anteil der Wärmepumpe P = S − N zum WP-Tarif (§3.5, N-767).
> **Klemme (F7):** N_WP auf `[0, min(WP-Strom, Netzbezug)]`, N_WB auf `[0, min(Ladung aller Wallboxen, Netzbezug − N_WP)]`; die
> Herleitung (`netzbezug_anteile[].geklemmt`, „gemessen … kWh, begrenzt") sagt, wenn begrenzt wurde. **Eine Bildungsstelle** (N-770
> E2): die Anteile entstehen in `services/monats_fakten/tarif.py::komponenten_anteile` (aus den Monats-Fakten
> `WpFakten.netz_eigener_tarif_kwh`, `EmobFakten.wallbox_netz_eigener_tarif_kwh`), die Formel im Layer
> (`core/berechnungen/netzbezug_kosten.py::berechne_netzbezug_kosten` mit `anteile`, Klemme `klemme_netzanteil`), und jede Sicht ruft
> `monats_fakten.stromrechnung_euro` — *Cockpit → Monat* (samt Vorjahr und Jahr, mit dem Monatstarif der Fakten), Übersicht,
> Komponenten-Zeitreihe, Auswertungen → Tabelle, `GET /monatsdaten/{id}`. Der **laufende Monat ohne Abschluss** (kein Monats-Fakt)
> nimmt N aus der Kanal-Zeile der WP-Gruppe (der Kanal des Felds zählt zu ihrem Kanal-Bedarf) und den Tarif über `tarif_des_monats`;
> die **Wallbox** (N-771) ebenso aus den Kanal-Zeilen der E-Mob-Gruppe — Ladung aller Wallboxen und N_WB über dieselbe Faltung wie der
> Fakt (`monats_fakten.wallbox_aus_zeilen`), nur wenn die Gruppe den Monat bis jetzt deckt (ein Zuordnungsmonat deckt also nicht);
> Klemme und F6 wie im Monat (`netzanteil_preise_des_monats(…, ["waermepumpe", "wallbox"])`). `GET /monatsdaten/{id}` behält seinen
> eigenen Haushaltspreis (gepflegt → Stamm, ohne die gemessene Stufe).

> **Gemeinsamer Zähler Wärmepumpe + Wallbox (F12; F12a = A, Entscheid Gernot).** Hängen Wärmepumpe **und** Wallbox hinter einem
> Unterzähler mit einem Tarif (§14a Modul 2, Wallbox am WP-Zähler), gilt die Tarif-Verwendung **„Wärmepumpe und Wallbox (gemeinsamer
> Zähler)"** (`waermepumpe_wallbox`). **Auflösung** (P8, die eine Regel `strompreise.tarife_zum_stichtag`): `waermepumpe` und
> `wallbox` zeigen auf **denselben** Datensatz; ein eigener WP- bzw. Wallbox-Tarif zum selben Stichtag hat Vorrang für seine
> Verwendung (dann ist es kein gemeinsamer Tarif mehr, der Daten-Checker sagt es). Damit tragen WP-Kosten S × W, der Wallbox-Preis,
> Heimladekosten und E-Mob-Ersparnis den gemeinsamen Tarif W_g ohne eigene Regel. Kennung `TarifFakten.komponenten_tarif_gemeinsam`
> (`tarife["waermepumpe"] is tarife["wallbox"] is not tarife["allgemein"]`); der **Grundpreis** des gemeinsamen Datensatzes zählt
> **einmal** (`grundpreis_des_monats`, Schlüssel `waermepumpe_wallbox` der Aufteilung). **Messgröße:** das Feld „Netzbezug zum
> WP-/Wallbox-Tarif (gemeinsamer Zähler)" **an der Wärmepumpe** trägt den gemeinsamen Netzbezug N_g (Zähler vor beiden Geräten minus
> Zähler danach; mehrere WPs: Σ der Felder, F3 bleibt); ein Feld an einer Wallbox zählt unter dem gemeinsamen Tarif nicht als N_g
> (sonst doppelt, Checker WARNING). **Formel** (`monats_fakten/tarif.py::_anteile_gemeinsam`): Stromrechnung = (Netzbezug − N_g) ×
> Haushalt + N_g × W_g + Grundpreise (allgemein + W_g einmal), N_g auf `[0, min(S_wp + L_wb, Netzbezug)]` (L_wb = Ladung aller
> Wallboxen). **Aufteilung nach F12a = A — wie zwei getrennte Zähler:** N_wb = die Netzladung der Wallbox-Zeilen nach der Regel der
> E-Mob-Zeile (gemessener Netzbezug zum Wallbox-Tarif an der Zeile außerhalb ihres Zuordnungsmonats, F11 — sonst evcc-Wert, sonst
> Ladung − PV nach der Tagesquote; `bau.wallbox_netzladung_der_zeilen` → `reader.get_emob_pv_netz_kwh`,
> `EmobFakten.wallbox_netzladung_kwh`) auf `[0, min(L_wb, N_g)]`; N_wp = N_g − N_wb auf `[0, S_wp]`; der PV-Anteil der WP
> P_wp = S_wp − N_wp wird in der Eigenverbrauchs-Ersparnis zum Tarif W_g bewertet (wie E2), die PV-Ladung der Wallbox wie bei
> getrennten Zählern. Folge: dieselbe Bewertung wie bei getrennten Zählern; Σ P_wp + PV_wb = S_wp + L_wb − N_g, solange nichts
> klemmt. Prognose/ROI (F4) nehmen P_wp/S_wp. (Verworfen, B: P = S_wp + L_wb − N_g als Ganzes zu W_g — dieselbe PV-Ladung hätte je
> nach Zählerbau zwei Bewertungen.) ⚑ **Benannte Grenzen:** die Netzladung der E-Mob-Zeile bleibt deren Regel (der gemeinsame Zähler
> teilt nicht je Gerät; der Checker nennt Monate, in denen N_wb > N_g geklemmt wird). **Tag:** die Stunde rechnet N_g,h × W_g,h +
> Rest × H_h (Stunden des Felds an der WP, Σ Tage = Monat in voll gedeckten Monaten); die **EV-Ersparnis des Tages teilt nicht** —
> ohne Stundenwerte der Wallbox ist N_wp des Tages unbekannt, der Monat trägt den Wert (Σ Tage ≠ Monat bei der Ersparnis, analog F9;
> Checker INFO mit den Monaten).

> **Tag und Stunde mit Netzbezug zum Komponenten-Tarif (N-770/N-771; F5, F6, F9 = A, F10).**
> Stündlich gibt es N **nur im Kanal des Felds** (`inv:<id>:netzbezug_eigener_tarif_kwh`, Spiegel der HA-Langzeitstatistik
> bzw. eigene Summe auf MQTT; `services/kanal/netzanteil_leser.py`) — die Stundentabelle trägt das Feld nicht. Setzt der
> Monat den Anteil an und decken die Kanäle aller Geräte der Verwendung den Kalendermonat voll, rechnet jede Stunde
> `(Netzbezug_h − N_h) × Slot-Preis_h + N_h × Komponenten-Preis_h` (`strompreis_aggregator.slot_kosten_aus_zeilen` mit
> `netzanteile`, Layer `berechne_netzbezug_kosten` je Stunde; der Rest wird je Stunde nicht geklemmt, damit Σ Stunden =
> Monat) und die EV-Ersparnis des Tages den PV-Anteil der WP P_d = WP-Strom_d − N_d zum WP-Tarif des Monats
> (`bewerte_eigenverbrauch`, `energie_profil/tage_netzanteil.py`). Hat der Monat geklemmt (F7), tragen die Stunden die
> Klemme im Verhältnis *angesetzt ÷ gemessen*. Damit gilt **Σ Tage = Monat** für Stromrechnung und EV-Ersparnis, auch mit
> HT/NT (Probe `test_n770_e3_tag_stunde.py`). Nichts wird geschrieben.
> **HT/NT (F6):** trägt der Haushaltstarif Zeitfenster, gewichtet sein Ø im Monat über **(Netzbezug − N)** statt über den
> ganzen Netzbezug (`gewichteter_arbeitspreis_netto_aus_zellen`, Antwortfeld `netzbezug_rest_preis_cent`; die Kopfzahl
> der Ø-Preis-Kachel bleibt der Haushaltspreis über den ganzen Netzbezug); ein Komponenten-Tarif mit Zeitfenstern über
> **N** statt über den Haus-Netzbezug (`TarifFakten.netzanteil_preise`, `NetzanteilZumTarif.zeitfenster`) — beides nur,
> wenn der Kanal den Monat deckt, sonst über den ganzen Netzbezug. Die WP-Kosten (S × W) und der Preis des PV-Anteils der WP bleiben
> der Preis des Geräteverbrauchs.
> **Zuordnungsmonat (F10):** beginnt der Kanal des Felds im Monat (er hat dort keinen Stand vor dem Monatsbeginn), ist
> der Monatswert eine Teilmenge ⇒ der Monat gilt als **nicht gemessen** (Monat und Tage ohne Anteil;
> `monats_fakten/laden.py::_zuordnungsmonate_nicht_gemessen`). ⚑ Benannte Grenze: ein **von Hand** eingetragener
> Monatswert im Zuordnungsmonat gilt nicht — der Monatsabschluss stempelt jedes gesendete Feld `manual:form`, den
> getippten Wert und den übernommenen HA-Vorschlag gleich; die Herkunft unterscheidet sie nicht.
> **Benannte Grenze (F9):** ein Netzbezug zum WP-/Wallbox-Tarif, der nur als **Monatswert** vorliegt (Hand, CSV, Monate
> ohne Kanal), teilt den Tag nicht — der Monat rechnet mit ihm (E2), die Tage tragen den ganzen Netzbezug zum
> Haushaltspreis, Σ Tage ≠ Monat.
> **Prognose und ROI-Jahresformel (F4, E4):** mit dem **gemessenen** PV-Anteil der WP P/S der letzten 12 abgeschlossenen
> Monate (`monats_fakten.gemessener_wp_pv_anteil`): die Monatsprognose bewertet Anteil × prognostizierten WP-Strom zum
> heutigen WP-Tarif (`finanz_prognose._ev_ersparnis_prognose`, Antwortfeld `ev_wp_pv_anteil_gemessen_prozent`), die
> ROI-Jahresformel der PV den Jahreswert P_jahr (`roi_pv._ev_ersparnis_jahr`, Detail `ev_wp_pv_anteil_gemessen_prozent`).
> Ohne Messung rechnen beide ohne diesen Anteil. Nicht betroffen: die BKW-Pauschale (`roi.py::_bkw_pauschal_beitrag` — eine angenommene
> Eigenverbrauchsquote des Balkonkraftwerks, kein WP-Anteil) und die E-Auto-Prognose (Netzladung zum heutigen
> allgemeinen Tarif).

> **Zwei Kostenzahlen, eine Rechnung — `netzbezug_kosten_euro` vs. `netzbezug_arbeitspreis_kosten_euro`:** verrechnet wird immer die
> **Gesamtsumme inkl. Grundpreis** — das, was auf der Rechnung steht, an T-Konto, Netto-Ertrag und den Finanz-Sichten. Daneben steht
> der reine **Arbeitspreis-Anteil** als *Ausweis*, kein zweiter Kostenposten — überall dort, wo eine Sicht kWh und € so
> nebeneinanderstellt, dass ein Leser sie dividiert: dann muss der Ø-Preis herauskommen (Ø-Preis-Kachel in Cockpit → Monat, Forum
> simon42 #89667). **Faustregel:** neben einem **Preis** steht der Arbeitspreis-Anteil, in einer **Kostenaufstellung** die Gesamtsumme.
>
> **Welcher Preis gilt:** der **abgerechnete** Monatsdurchschnitt (`Monatsdaten.netzbezug_durchschnittspreis_cent`), sonst der aus den
> Stundenpreisen **gemessene** verbrauchsgewichtete Ø, sonst der Tarif-Arbeitspreis (die Kaskade weiter unten in diesem Dokument). Das
> gilt für Netzbezug-Kosten, EV-Ersparnis und — ohne eigenen WP-Tarif — auch für die WP-Ersparnis, in jeder Sicht und auch für den
> laufenden Monat.
>
> **Der gemessene Ø aus Kosten-Kanälen (HA-Bauform E4e).** Mit einem Preissensor, für den Home Assistant
> eine Langzeitstatistik führt, schreibt eedc stündlich dieselben Summen wie HAs Kostensensor:
>
> ```
> Kosten_Netzbezug (€)   += max(0, Δ Netzbezug_h) × Preis_h / 100       — nur Stunden mit Preis
> Netzbezug_bewertet     += max(0, Δ Netzbezug_h)                        — nur Stunden mit Preis
> Kosten_EV_vermieden (€)+= max(0, Δ PV_h − Δ Einspeisung_h) × Preis_h / 100
> EV_bewertet            += max(0, Δ PV_h − Δ Einspeisung_h)
> Preis_Summe (ct)       += Preis_h                                       — nur Stunden mit Preis
> Preis_Stunden (h)      += 1                                             — nur Stunden mit Preis
>
> Ø gemessen (Monat)     = Δ Kosten_Netzbezug × 100 / Δ Netzbezug_bewertet
> EV-Ø (Monat)           = Δ Kosten_EV_vermieden × 100 / Δ EV_bewertet
> Ø arithmetisch (Monat) = Δ Preis_Summe / Δ Preis_Stunden;  Stunden mit Preis = Δ Preis_Stunden
> ```
>
> Einen Kanal für den Einspeise-Erlös gibt es bewusst nicht: der Erlös rechnet weiter Einspeisung × Satz des Monats
> − §51; als Kanal käme er nur mit eigenem Leser und Neuaufbau bei einer Tarifänderung.
>
> Preis_h ist das Stundenmittel des Sensors (Einheit wie die Mitschrift: €/kWh × 100), PV_h die PV der Stunde samt
> Erzeugern hinter dem Zähler nach derselben Regel wie Tag und Monat (der Anlagenzähler füllt nur Geräte ohne eigenen
> Zähler). Ein Monat kommt aus den Kanälen nur, wenn **alle** diese Summen ihn ganz decken;
> sonst rechnet er aus den Stundenzeilen — mit denselben Zahlen (Monat für Monat zwei Stände statt aller Stunden). Der Kanal beginnt
> mit dem Monat des Updates; frühere Monate rechnet die Stundentabelle. Tag (Slot-Kosten) und §51 bleiben bei den Stundenzeilen.
>
> **Zeitfenster-Tarif (HT/NT, Stufe 3 der Kaskade).** Das Gewicht ist der gemessene Netzbezug je Stunde. Aus den Kanälen kommt er je
> **(Wochentag, Uhrstunde)** zusammengefasst — Σ der auf 0 geklemmten Stunden-Zuwächse — und der Preis je Zelle aus dem Fenster
> (`zeittarif.gewichteter_arbeitspreis_aus_zellen`; ein Fenster hängt nur an Wochentag und Uhrzeit, deshalb ist Σ Preis × kWh über die
> Zellen dieselbe Zahl wie über die Stunden). Alle Monate einer Seite, in denen ein Zeitfenster-Tarif gilt, kommen in EINER Abfrage.
> Deckt ein Netzbezugs-Zähler den Monat nicht, gewichten die Stundenzeilen. **Die Eigenverbrauchs-Ersparnis** bewertet den vermiedenen
> Bezug dagegen mit dem HT/NT-Preis **seiner** Stunde (A-2, N-669): Σ(max(0, PV − Einspeisung) × Fensterpreis) ÷ Σ max(0, PV −
> Einspeisung) über die Stundenzeilen des Monats — dieselben Zeilen und dieselbe Slot-Regel wie der Tag, deshalb ist die
> Monats-Ersparnis die Summe der Tage (`strompreis_aggregator.ev_preis_zeitfenster_cent`). Ohne Stundenzeilen bleibt der Bezugs-Ø der
> Rückfall.

**§51 EEG im Einspeise-Erlös:** `Einspeisung_neg_Preis` sind die kWh, die in Stunden mit negativem Börsenpreis eingespeist wurden —
für betroffene Anlagen entfällt dafür die Vergütung (Herleitung des Volumens: Abschnitt „§51 EEG (Negativpreis-Analyse)"). Ist die
Anlage nicht §51-pflichtig oder liegt keine Strompreis-Mitschrift vor, ist der Wert `null` und es wird nichts abgezogen. Der Abzug gilt
**überall** gleich, mit **einer** Implementierung: `core/berechnungen/einspeise_erloes.py`; einen Frontend-Spiegel gibt es nicht — die
Monats-Finanzzeile kommt fertig aus `/monatsdaten/aggregiert` (N-22).

**Netzpunkt-Bilanz (Erzeugung_gesamt):** Am EINEN Netzanschluss messen die Zähler (`Einspeisung`/`Netzbezug`) die Summe **aller**
dahinter liegenden Erzeuger. Deshalb geht in die Eigenverbrauchs-/Autarkie-Ableitung die **Gesamterzeugung** ein — PV-Module +
Balkonkraftwerk + **sonstige Erzeuger** (z. B. Mini-BHKW); würde ein Erzeuger ignoriert, drückte der gemessene Einspeise-Zähler
`Direktverbrauch` zu niedrig (auf 0 geklemmt), und Autarkie/EV-Quote würden unterschätzt. SoT-Helper:
`core/berechnungen/energie.erzeugung_hinter_zaehler_kwh` (ADR-001).

**Die Größe ist ein eigenes Response-Feld, kein Rechenschritt je Sicht.** `/monatsdaten/aggregiert` liefert sie als
`erzeugung_hinter_zaehler_kwh` mit — keine Sicht summiert die Einzelteile selbst. Die Felder derselben Antwort:

| Feld | Bedeutung |
|---|---|
| `pv_module_kwh` | nur die PV-Module |
| `bkw_kwh` | nur Balkonkraftwerk(e) |
| `sonstige_erzeugung_kwh` | „Sonstiges" mit Kategorie *Erzeuger* (z. B. Mini-BHKW) |
| `pv_erzeugung_kwh` | `pv_module_kwh + bkw_kwh` — **nicht** die gleichnamige DB-Spalte (s. [Schicht 1](#schicht-1-rohdaten-eingabe)) |
| **`erzeugung_hinter_zaehler_kwh`** | Σ **aller** drei Erzeuger-Felder = der Nenner der EV-Quote |

> ### Ein Balkonkraftwerk mit zugeordneten PV-Modulen (ADR-002/**P11**)
>
> Ein Balkonkraftwerk trägt **eine** Ausrichtung und **eine** Neigung. Wer seine Module über Eck
> hängen hat (Balkon und Terrasse, Ost und West), legt sie deshalb als **PV-Module** an und ordnet
> sie unter *Gehört zu* dem Balkonkraftwerk zu — jedes Modul trägt dann seine eigene Ausrichtung,
> und die Prognose rechnet sie getrennt.
>
> **Damit tritt das Balkonkraftwerk drei Größen an seine Module ab**, und zwar immer gemeinsam:
> die **Nennleistung** (die Anzeige am Gerät zeigt die Σ seiner Module), die **Ausrichtung/Neigung**
> und die **Erzeugung**. Für die Erzeugung gilt dieselbe Leserichtung wie beim Anlagen-Aggregat
> (**P7**), nur eine Ebene tiefer — **die Präzedenz hat damit drei Stufen**:
>
> 1. der **gemessene Wert des Moduls** gewinnt,
> 2. der **Monatswert des Balkonkraftwerks** füllt die Lücken *seiner* Module (nach kWp verteilt),
> 3. das **Anlagen-Aggregat** `Monatsdaten.pv_erzeugung_kwh` füllt, was danach noch offen ist —
>    gemindert um die eigenen Werte der Balkonkraftwerke, die in diesem Monat **selbst** tragen
>    (ein abtretendes BKW steckt schon in Stufe 2); ein selbst tragendes BKW **ohne** eigenen Wert
>    teilt sich den Rest nach kWp mit den Modul-Lücken (N-621).
>
> Der Monatswert am Balkonkraftwerk bleibt also voll erfassbar und zuordenbar — bei einem Set ist
> der Wechselrichter oft der einzige Zähler, und die Module darunter haben gar keinen eigenen. Er
> zählt dann aber **nicht mehr zusätzlich** in `bkw_kwh`: `pv_erzeugung_kwh` wäre sonst doppelt, mit
> Folgen für Autarkie, EV-Quote, CO₂, Finanzen, Community-Datensatz und HA-Sensoren.
>
> ⚠ **Nicht abgetreten wird die AC-Grenze.** Die *Wechselrichter-Leistung (W)* gehört dem Gerät und
> gilt weiter für die **Summe** seiner Module — sie ergibt sich gerade nicht aus ihnen. Das sind zwei
> unabhängige Grenzen: 800 VA am Wechselrichter-Ausgang und (regulatorisch) 2.000 Wp an den Modulen;
> nur die zweite wächst mit den Kindern. Für die Kappung wechselt das Balkonkraftwerk deshalb die
> Rolle vom Erzeuger zum **Träger** — genau die Rolle, die ein Wechselrichter für seine Strings hat.
>
> **Ein Balkonkraftwerk ohne zugeordnete Module rechnet unverändert.**
> SoT: `core/berechnungen/erzeuger_traeger.py`. Melder: Discussion #366, Forum T89667 #172.
>
> #### Dieselbe Abtretung gilt für die Wirtschaftlichkeit (ab v4.0.19, F-33/#381)
>
> Die ROI-Sicht fasst einen **Wechselrichter mit seinen Modulen und seinem DC-Speicher** zu **einer** Systemzeile zusammen: die drei
> Positionen teilen sich eine Energiemenge, ihre Ersparnisse sind deshalb **nicht addierbar**. **Trägergerät** ist die Rolle, nicht der
> Typ: ein Balkonkraftwerk mit Kindern ist Systemkopf wie ein Wechselrichter und tritt seine Ersparnis genauso an die Module ab, wie es
> oben seine Erzeugung abtritt — hat es **keine** Modul-Kinder (nur einen Speicher), trägt es sie selbst und steuert sie der
> Systemzeile bei. Die Zeile trägt Name und Typ ihres Kopfes (kein „PV-System" mit fremdem Namen), und ein zugeordnetes Modul-Kind
> trägt keine Aufforderung „(ohne WR) — bitte zuordnen".
>
> ⚠ **Die pauschale BKW-Schätzung bleibt eine Schätzung** (0,9 kWh/Wp, 80 % Eigenverbrauch / 20 % Einspeisung — Pauschale und Anzeige lesen
> das Paar `BKW_EIGENVERBRAUCH_ANTEIL_SCHAETZUNG`/`BKW_EINSPEISE_ANTEIL_SCHAETZUNG` aus `core/berechnungen/bkw_finanz.py`) und greift nur für ein Balkonkraftwerk
> ohne Modul-Kinder — dort, wo keine gemessenen Modulwerte existieren (#381). Ist gar keine Leistung gepflegt (weder `leistung_kwp`
> noch `parameter.kwp`/`leistung_kwp` noch `leistung_wp × anzahl`, `get_bkw_kwp` = 0), rechnet die Pauschale mit **800 Wp**, und die
> Zeile nennt diese Leistung im Hinweis („Balkonkraftwerk 800 Wp") — eine Annahme, keine Messung (N-273;
> `roi.py::_bkw_pauschal_beitrag`, Anzeige `roi_standalone.py::_bkw_bewertung`).
>
> **«Entgangener Erlös» im Balkonkraftwerk-Hub — Annahme 8 ct/kWh.** Ein Balkonkraftwerk ohne Anmeldung als EEG-Anlage bekommt für
> seine Einspeisung nichts; die Kachel «Entgangener Erlös» und der Hinweis unter der Wirtschaftlichkeit zeigen rechnerisch, was sie
> zum Satz einer kleinen Anlage wert wäre: `Einspeisung × 8 ct/kWh` (`BKW_UNVERGUETET_ANNAHME_CENT` in `core/berechnungen/bkw_finanz.py`,
> gerechnet über `einspeise_erloes_euro` in `dashboard_balkonkraftwerk.py`, Felder `entgangener_erloes_euro` und
> `entgangener_erloes_annahme_cent`; bis Päckchen Z2 rechnete der Client). Kein Posten der Wirtschaftlichkeit, nur ein Hinweis.
> Grenze: der Satz ist fest — er folgt weder dem gepflegten Tarif noch dem Jahr der Inbetriebnahme.

**Auch die PDF-Berichte rechnen so:** alle Bilanz-Pfade (Cockpit, Monatsbericht, Live, PDF-Jahresbericht, HA-Sensoren) nehmen für
Eigenverbrauch, Autarkie und EV-Quote dieselbe Gesamterzeugung hinter dem Zähler.

**Spezifischer Ertrag — zwei Größen, ein Formelname.** Die Roh-Division oben ist nur eine davon:

| Größe | Rechenweg | Wo |
|---|---|---|
| **Annualisiert** | saisonal gewichtet (PVGIS-Monatsverteilung) und mit der im jeweiligen Monat **tatsächlich installierten** Leistung — vergleichbar über verschieden lange Zeiträume | Cockpit, HA-Export, Community-Vergleich (SoT `core/berechnungen/spez_ertrag.py`) |
| **Zeitraum** | Erzeugung des Berichtszeitraums ÷ Anlagen-Nennleistung, ohne Normierung — summiert sich über mehrere Jahre auf | PDF-Jahresbericht (beschriftet **„Spez. Ertrag (Zeitraum)"**), Monatsbericht |

Beide Zahlen sind richtig, sie beantworten verschiedene Fragen; eine Angleichung steht aus, weil dieselbe Kennzahl im
Community-Vergleich steht. Welche Monate der annualisierte Wert zählt, entscheidet für Cockpit-Kachel und HA-Sensor **eine** Funktion
(`services/monats_fakten/ableitungen.py::pv_erzeugungs_monate`): ein Monat mit Modul-Eintrag, mit eigenem Balkonkraftwerk-Wert > 0
oder mit dem Anteil eines Balkonkraftwerks am gespeicherten Anlagenwert.

**Achsen-Trennung (bewusst):** PV-**eigene** Kennzahlen (spez. Ertrag, Performance-Ratio, SOLL/IST, kWp) nutzen **nur**
`PV_Erzeugung`, nicht `Erzeugung_gesamt` — ein sonstiger Erzeuger ist energetisch Erzeuger, aber kein PV-Modul. Ebenso bleibt **die
Geräte-Wirtschaftlichkeit quellenspezifisch**: ein Erzeuger unter *Sonstiges* bekommt keine eigene Wirtschaftlichkeit, weil eedc für
die ganze Kategorie (BHKW, Windrad, Wasserkraft) den Vergleichswert nicht kennt — er steht als „nicht bewertet" da, der Ertrag wird
am Gerät gepflegt. ⚑ **Sein Strom ist davon unberührt** — er zählt in Menge *und* Geldwert der Anlage voll mit (§3.2), und **CO₂ folgt
der Geldregel** (DI-2, P15: CO₂ auf den Eigenverbrauch): der selbst verbrauchte Strom eines sonstigen Erzeugers gilt wie PV-Strom als
vermiedener Netzstrom (0,38 kg/kWh); die Emission des Erzeugers selbst (etwa das Gas eines BHKW) zieht eedc **nicht** ab, und am
Hauszähler lässt sich der Eigenverbrauch nicht in PV- und BHKW-Anteil trennen — die CO₂-Gutschrift ist „vermiedener Netzstrom", keine
Klimabilanz des BHKW (§3.8). **Insel-Anlagen** (kein Netzanschluss) fallen nicht unter diese Bilanz — ein Anlagen-Merkmal (eigenes
KZ, geplant).

**Messpunkt der Sensoren (DC vs. AC):** die Bilanz rechnet mit den Werten, die die Geräte liefern, und kann nicht wissen, **wo**
gemessen wurde. Viele Hybrid-Wechselrichter (z. B. E3DC) melden PV-Erzeugung und Speicher-Ladung/-Entladung **DC-seitig**, Einspeisung
und Netzbezug **AC-seitig** (Zähler); dann stecken die Wandlungsverluste der PV- und Speicherstrecke im bilanzierten `Gesamtverbrauch`,
typisch **3–5 % der Erzeugung** über dem „Hausverbrauch" des Herstellerportals, das seine Verluste herausrechnet. eedc beantwortet „was
musste die Anlage liefern" (**inklusive** Verluste — die Basis für Autarkie und EV-Quote), das Portal „was zogen die Verbraucher".
**Für Ersparnis, USt und CO₂ gilt das Gegenteil (N-588):** kennt eedc die Wechselrichterverluste (String-Zähler und Anlagenzähler,
Messpunkt-Vertrag in §1), bewertet es den Eigenverbrauch **ohne** sie. Die DC-gemessene Speicherstrecke bleibt davon unberührt: mit
einem DC-gekoppelten Speicher zieht eedc nichts ab.

*Diagnose-Rezept* für einen abgeschlossenen Tag (Issues #200/#340):

```
Residuum = PV + Netzbezug + Entladung − Einspeisung − Ladung − Hausverbrauch(Portal)
```

Liegt das Residuum bei wenigen Prozent der Erzeugung, ist es der Verlustanteil und kein Rechenfehler (darin Batterie-Rundlauf (DC)
und DC→AC-Wandlung); da die Verluste mit dem Durchsatz skalieren, liegt ein ertragsstarker Tag über dem Monatsschnitt.

**Bewusst kein Hausverbrauchs-Sensor:** eedc bietet **kein** Mapping eines fremden Hausverbrauchs-Sensors an. „Hausverbrauch" ist je
Hersteller anders definiert (Verluste drin oder herausgerechnet, Wallbox enthalten oder nicht) — zwei Definitionen derselben Kennzahl
ließen Cockpit, Berichte und Community-Vergleich auseinanderlaufen. Die Bilanz aus Zähler- und Komponentenwerten bleibt die eine
Wahrheit; die Differenz wird erklärt, nicht durch eine zweite Datenquelle ersetzt.

**Wichtig:** `Netto_Ertrag` enthält NICHT den Abzug der Netzbezugskosten, da diese auch ohne PV angefallen wären.

### 3.2 Finanzen (Cockpit)

#### Die Ergebnis-Leiter — Monat, Jahr und Gesamt aus einer Rechnung (seit 03.10.2026)

**SoT:** `core/berechnungen/ergebnis.py` (`berechne_ergebnis`, `soll_erfuellung`, `falte_zeitraum`), der USt-Satz aus
`services/ust_satz.py`. Netto-Ertrag, Monats-/Jahresergebnis und SOLL-Erfüllung entstehen in jeder Sicht aus dieser
einen Rechnung (N-601).

```
Stufe 1  Netto-Ertrag (PV)           = Einspeise-Erlös + EV-Ersparnis + BKW-Rest-Ersparnis + Erlös eigener Satz
                                       + Sonstige Positionen (netto) − Dienstliche Ladekosten
                                       − USt-Anteil auf den Eigenverbrauch
Stufe 2  (Zwischenstand)             = Netto-Ertrag + WP-Ersparnis + E-Mob-Ersparnis − Stromrechnung (inkl. Grundgebühr)
Stufe 3  Monats-/Jahresergebnis      = Stufe 2 − Betriebskosten (anteilig, nur im Monat aktive Komponenten)
```

* **Mit gemessenem Netzbezug zum Komponenten-Tarif (N-770/N-771)** trägt die Stromrechnung zwei bzw. drei
  Arbeitspreise (§3.1, Kasten) und die EV-Ersparnis bewertet den PV-Anteil der Wärmepumpe zum WP-Tarif (§3.5, N-767).
  Die Posten der Leiter bleiben dieselben; Monats- und Jahresergebnis bewegen sich um `(N_WP − P_WP) × (Haushalt −
  WP-Tarif) + N_WB × (Haushalt − Wallbox-Tarif)`. Die Antwort nennt die Anteile (`netzbezug_anteile`,
  `ev_ersparnis_wp_tarif_kwh`/`_cent`, im Jahr Σ je Verwendung), der Tooltip der Ø-Preis-Kachel und des Netto-Ertrags
  ebenso.

* **Ein Name je Stufe.** Stufe 1 ist der „Netto-Ertrag" überall — Cockpit → Monat/Jahr, Komponenten → PV-Anlage,
  PDF-Jahresbericht, HA-Sensor `netto_ertrag_euro`. Stufe 2 hat im UI keinen eigenen Namen; sie steht nur als
  Zwischenstand in der Herleitung (Antwortfeld `ergebnis_vor_betriebskosten_euro`). Stufe 3 ist das
  **Monatsergebnis** bzw. **Jahresergebnis** (Feld `ergebnis_euro`).
* **Herleitung aus derselben Rechnung (A6).** Die Antwort trägt je Stufe Formel und eingesetzte Werte
  (`ergebnis_herleitung`); der Tooltip nennt jeden Summanden einzeln — WP-, E-Mob-, BKW-, Erzeuger-, Sonstige-,
  Dienstwagen- und USt-Posten nur, wenn sie etwas beitragen.
* **Dienstliche Ladekosten sind ein eigener Posten (N-633).** Die Monats-Fakten bilden ihn
  (`EmobFakten.dienstliche_ladekosten_euro`, Formel §3.10); Cockpit → Monat und → Jahr, Auswertungen → Tabelle und
  → Finanzen, Monats- und Jahresbericht führen ihn als Zeile bzw. Summanden „Dienstliche Ladekosten" (T-Konto SOLL,
  Komponenten-Finanztabelle als Aufwand, nur wenn ≠ 0). Übersicht, HA-Sensor und Aussichten lesen denselben Wert aus
  den Monats-Fakten und falten ihn in ihre Sonstigen Positionen (der Netto-Ertrag ist in beiden Formen derselbe). Er steht **nicht** in den Sonstigen
  Ausgaben des Monats — die sind Eingang des Kapitaleinsatzes (F-19), der Posten ist laufender Aufwand.
* **Fehlende Eingänge — eine Regel für Monat, Vorjahr und Jahr.** Eine Stufe gibt es nicht (`—`), wenn einer ihrer
  Pflichtposten fehlt: Stufe 1 braucht Einspeise-Erlös und EV-Ersparnis, Stufe 2 zusätzlich die Stromrechnung.
  Optionale Posten gehen als 0 ein und werden in `fehlende_posten` genannt, wenn die Komponente existiert, aber keinen
  Wert hat. Der **Vorjahresmonat** folgt derselben Regel; ein Vorjahresmonat mit 0 kWh Netzbezug trägt dabei die
  Grundgebühr als Stromrechnung, wie der laufende Monat auch.
* **Betriebskosten des Monats** zählen nur Komponenten, die im Monat aktiv waren (Anschaffungs- und
  Stilllegungsdatum) — dieselbe Filtermenge wie die T-Konto-Zeilen, gerechnet mit der Laufzeit-Regel
  (`core/berechnungen/betriebskosten.py`, s. Cockpit-Übersicht unten) und **ungerundet** ausgeliefert: so ist die Summe
  der Monate eines Jahres der Jahresbetrag (N-699).
* **USt-Anteil eines Monats** = Eigenverbrauch des Monats × USt je kWh **des Jahres** (§3.7). Σ der Monatsanteile
  eines Jahres = der Jahreswert der Übersicht. Im laufenden Jahr wandert der Satz mit jedem Abschluss um Cent-Beträge
  (eine Jahressteuer); die Herleitung nennt Satz und Grundlage. Hat das Jahr noch keinen Abschluss, gilt der Satz des
  Vorjahres; gibt es auch den nicht, wird kein USt-Anteil gerechnet, und die Herleitung sagt es.
* **SOLL-Erfüllung** (`soll_erfuellung_prozent`, `soll_erfuellung_monat_prozent`, `soll_fenster_text`) kommt ebenfalls
  fertig aus der Antwort — Cockpit und PDF-Monatsbericht rechnen sie nicht selbst.
* **Der Layer rundet nicht**; gerundet wird am Antwortrand (Cockpit → Monat je Posten auf Cent — außer den
  Betriebskosten, die erst die Darstellung rundet).

**Das Jahr (Cockpit → Jahr, Auswertungen → Finanzen im Jahr-Modus)** rechnet das Backend:
`GET /api/cockpit/jahr/{anlage_id}?jahr=` lädt die Monatsantworten des Jahres (jeder Monat zwischen Inbetriebnahme und
heute, der gemessene Mengen trägt — auch ohne Monatsabschluss) und faltet sie (`falte_zeitraum`):

* **Summen** (kWh, €) über alle Monate; **Quoten paarweise** — Autarkie, EV-Quote, Speicher-Auslastung und der
  Netzlade-Ø-Preis entstehen aus Summen über genau die Monate, die **beide** Größen tragen. Ein Monat mit
  Eigenverbrauch, aber ohne Gesamtverbrauch, fällt aus Zähler und Nenner (#421). Zähler,
  Nenner und Fenster („aus 8 von 9 Monaten") stehen in der Antwort und im Tooltip.
* **Ergebnisgrößen über die Leiter** auf den Jahressummen ihrer Posten, mit derselben None-Regel: fehlt einem Monat die
  Stromrechnung, gibt es kein Jahresergebnis (`fehlende_posten` nennt den Monat). Der Netto-Ertrag hängt nicht an der
  Stromrechnung.
* **Vorjahr / Ø-Jahr** aus der Monatsreihe, beschnitten auf die gemeinsamen Monate (N-37); die Ø-Autarkie ist die Quote
  der gemittelten Mengen, nicht das Mittel der Prozente.
* Kopfzahl = das Jahr bis heute (inkl. laufendem Monat); Vergleich, Vorjahr, Ø-Jahr nur über abgeschlossene Monate.

Die übrigen Faltungsregeln, die eine eigene Formel tragen (M = Monate des Zeitraums):

```
η Speicher (Jahr)        = speicher_wirkungsgrad(Σ_M Ladung, Σ_M Entladung)      Quelle „fenster_lang"
                           (eine Quote der Jahressummen — kein Mittel der Monats-η)
Netzbezug-Preis (Ø)      = Σ(Preis_m × Netzbezug_m) ÷ Σ Netzbezug_m               Preis_m = Kaskaden-Preis des
                           über die Monate mit Preis UND Menge; Σ Menge = 0        Monats (N-680)
                           ⇒ ungewichtetes Mittel der Monatspreise
Einspeise-Preis (Ø)      = Σ(Preis_m × Einspeisung_m) ÷ Σ Einspeisung_m          dieselbe Regel
…_durchschnittspreis     = der gewichtete Ø oben, nur wenn ein Monat ihn trägt, sonst None
Grundlast-Anteil         = Σ Grundlast_kWh ÷ Σ Gesamtverbrauch_m × 100           Nenner NUR über Monate mit
                                                                                  Grundlast; Nenner 0 ⇒ None
Grundlast (kW)           = Mittel der Monate
WP nicht aufgeteilt      = Übersicht des Jahres (P12), sonst
                           max(0, Σ WP-Strom − Σ Modus Heizen − Σ Kühlen − Σ Warmwasser)
Quote paarweise          = Σ Zähler ÷ Σ Nenner × 100, Nenner 0 ⇒ None
```

Die WP-Kennzahlen (JAZ, Gründe, Geräte, Kälte) kommen aus der Übersicht des Jahres, ohne sie bleiben nur die Mengen.
Investitions-Finanzzeilen werden je Investition summiert (Identität vom ersten Vorkommen, die Monats-Formeln entfallen;
zwei fehlende Erlöse bleiben fehlend), sonstige Geräte je Kategorie und Bezeichnung (0 ⇒ kein Wert). **Code-Ort:**
`falte_zeitraum` setzt die Antwort aus den Teilstücken seiner Phasen zusammen (RF-52) — `_falte_kopf_und_bilanz` (Mengen,
Autarkie/EV-Quote/Wandlungsverluste paarweise) · `_falte_speicher` (η, Auslastung, Netzlade-Preis) · `_falte_wp` ·
`_falte_emob_bkw_sonstiges` · `_falte_leiter_und_soll` (Leiter, SOLL) · `_falte_preise` (gewichtete Preise, Grundgebühr) ·
`_falte_grundlast_und_details`; gerundet wird erst am Rand der Jahresroute (`services/jahres_aggregat.py::runde_rand`).


**Endpoint:** `GET /api/cockpit/uebersicht/{anlage_id}` in `api/routes/cockpit/uebersicht.py`

Die Cockpit-Übersicht aggregiert alle Monatsdaten für ein Jahr (oder alle Jahre) und berechnet:

#### Finanzielle Kennzahlen

```
Einspeise-Erlös     = Σ(Einspeisung) * Einspeisevergütung / 100
EV-Ersparnis        = Σ(PV_Eigenverbrauch * EV_Preis) / 100         (s. Hinweis; je Monat der EV-gewichtete Ø, sonst Netzbezug_Preis)
BKW-Ersparnis       = Σ(BKW_Rest_Eigenverbrauch * EV_Preis) / 100   (P9: nur BKW-Monate ohne erfasste Erzeugung; Preis wie EV-Ersparnis, A-2)
Sonstige-Netto      = Σ(sonstige_ertraege) - Σ(sonstige_ausgaben)
Netto-Ertrag        = Stufe 1 der Ergebnis-Leiter (berechne_ergebnis):
                      Einspeise-Erlös + EV-Ersparnis + BKW-Ersparnis + Erlös_eigener_Satz + Sonstige-Netto
                      [- USt_Eigenverbrauch]

Betriebskosten_Zeitraum = Σ_Komponente Betriebskosten_Jahr × aktive_Monate_im_Zeitraum / 12

Kumulative Ersparnis = Netto-Ertrag + WP-Ersparnis + E-Mob-Ersparnis
                       - Betriebskosten_Zeitraum
                       (BKW-Ersparnis und Sonstige-Netto stecken im Netto-Ertrag und zählen nicht ein zweites Mal; #326, P9)

Rendite (%)         = Kumulative_Ersparnis / Investition_gesamt * 100   (Antwortfeld jahres_rendite_prozent)
                      Investition_gesamt = relevante Kosten (Mehrkosten, N-137; s. „Investitionskosten" unten)
                      Investition_gesamt im Einzeljahr: nur Investitionen mit Anschaffung ≤ 31.12. (N-720)
```

**Netto-Bilanz der Werte-Tabelle** (Kennwert `netto_bilanz`; *Auswertungen → Tabelle* und *Cockpit → Tag*) = Netto-Ertrag −
Netzbezugskosten. Sie ist eine eigene Größe der Tabelle, **keine** Stufe der Ergebnis-Leiter: ohne WP- und E-Mob-Ersparnis und ohne
Betriebskosten (benannte Ausnahme im Wächter `test_ergebnis_leiter_nur_im_layer.py`). **Monat**
(`api/routes/monatsdaten_aggregiert.py::_zeile_bilanz_und_geld`, Feld `netto_bilanz_euro`): Netto-Ertrag = Stufe 1 der Leiter mit
Sonstigen Positionen (A1), Dienstlichen Ladekosten (N-633) und USt-Anteil (N-588); Netzbezugskosten = die Stromrechnung des Monats
samt Grundgebühr und Komponenten-Tarifen (`monats_fakten.stromrechnung_euro`, N-770); auf Cent gerundet. Sind Einspeisung oder
Netzbezug des Monats nicht erfasst, bleibt das Feld leer wie die Geldfelder der Zeile, die aus Einspeisung oder Netzbezug folgen
(`monatsdaten.py::_NETZ_ABHAENGIGE_FELDER`; Erlös eigener Satz, Dienstliche Ladekosten und USt bleiben stehen — N-736, §1 «Einspeisung
und Netzbezug des Monats»). **Tag** (`services/energie_profil/tage_werte.py::_geld_spalten`, Feld `netto_bilanz`): Netto-Ertrag ohne USt-Anteil und ohne
Dienstliche Ladekosten, Netzbezugskosten = Σ der Slot-Kosten des Tages (`strompreis_aggregator.slot_kosten_aus_zeilen` über
`tage_werte.py::_slot_kosten_der_bestandstage`/`_slot_kosten_der_kanal_tage`, ohne Grundgebühr) — Σ Tage ≠ Monat. Fehlt eine Seite (Netzbezug nicht erfasst, keine Stundenzeilen, kein Eigenverbrauch), ist der Wert
leer statt 0 (T89667 #162); gerundet wird erst in der Anzeige. Die Spalte summiert über die gezeigten Monate bzw. Tage.

> **`BKW_Rest_Eigenverbrauch` entsteht in der Faltung der Monats-Fakten** (`monats_fakten/roh.py::_RohMonat._falte_bkw`,
> ADR-002/P9): je BKW-Zeile entscheidet `bkw_finanz_beitrag`, welcher Wert die Finanz-Zeile trägt — mit erfasster
> Erzeugung die Erzeugung (Rest 0, der selbst verbrauchte Teil steckt in `PV − Einspeisung − Speicherladung`), ohne sie
> der gemessene Eigenverbrauch. Für ein Balkonkraftwerk, das an Modul-Kinder abgetreten hat (N-266), und für eines mit
> Anteil am gespeicherten Anlagenwert (N-621) entfällt er ganz — seine Erzeugung steht über die Kinder bzw. den Anteil
> schon in der PV-Summe:
>
> ```
> BKW_Rest_Eigenverbrauch(Monat) = Σ_BKW-Zeilen  ( 0                     wenn abgetreten oder Anteil am Anlagenwert
>                                                 0                     wenn Erzeugung > 0
>                                                 Eigenverbrauch_gemessen sonst )
> ```

> **Betriebskosten des Zeitraums — die Laufzeit-Regel (N-228), eine Funktion.** Jede Komponente trägt ihre
> gepflegten Betriebskosten nur über **ihre** aktiven Monate des Zeitraums (Anschaffung bis Stilllegung), ungerundet:
> `core/berechnungen/betriebskosten.py::betriebskosten_im_zeitraum` (je Komponente `betriebskosten_je_investition`,
> ein Monat `betriebskosten_monatsanteil`). Die Monate des Zeitraums sind die der Monats-Fakten. Dieselben Funktionen
> rufen Cockpit → Übersicht, Cockpit → Monat (und über die Faltung Cockpit → Jahr samt T-Konto-Zeilen), die
> Aussichten (bisherige Erträge der ROI-Kachel) und der Jahresbericht-PDF (N-699).

> **Das Cockpit zeigt diese Rendite nicht an.** `jahres_rendite_prozent` steht in der Antwort von
> `/cockpit/uebersicht`; der **Jahresbericht-PDF** druckt sie als „Rendite" (Berichtsjahr bzw.
> Gesamtzeitraum, mit ihrem Nenner beschriftet, N-699). Die Rendite einer Anlage steht unter *Auswertungen → ROI*
> (ROI pro Jahr = jährliche Einsparung ÷ Kapitaleinsatz, s. „ROI & Amortisation“).
> **Im Einzeljahr** stehen im Nenner nur die Investitionen, die bis zum 31.12. des Jahres angeschafft waren (ohne
> Anschaffungsdatum: immer) — dieselbe Grenze wie der Kapitaleinsatz des Fortschritts „Stand 31.12." (N-720). Der
> Gesamtzeitraum kennt alle.

> **Die Einspeisevergütung ist ein flacher Satz — eedc kennt keine EEG-Leistungsstaffel.**
> `Einspeisevergütung` ist genau der Wert aus dem für den Monat gültigen Tarif
> (`Strompreis.einspeiseverguetung_cent_kwh`); es gibt keine Ableitung aus `leistung_kwp`, keine
> Stufengrenze und keine Aufteilung der eingespeisten Menge auf mehrere Sätze. Wer gestaffelt
> vergütet wird, trägt den nach kWp gewichteten **Mischsatz** ein — mathematisch identisch, weil
> das EEG nach *installierter Leistung* staffelt und nicht nach eingespeister Menge. Der einzige
> Automatismus ist der Fallback `EINSPEISEVERGUETUNG_DEFAULT_CENT`
> (`core/wirtschaftlichkeit_defaults.py`), der ausschließlich greift, wenn **gar kein** Tarif
> gepflegt ist — und genau das meldet der Daten-Checker. Anwendersicht:
> [Einstellungen §2.2](HANDBUCH_EINSTELLUNGEN.md#22-strompreise).
>
> **Variable Einspeisevergütung (#392):** Trägt der Tarif das Häkchen
> „Einspeisevergütung wechselt monatlich“ (`Strompreis.einspeisung_variabel`, z. B.
> OeMAG-Marktpreis in Österreich), bietet der Monatsabschluss das Feld
> `Monatsdaten.einspeise_durchschnittspreis_cent` an. Der gepflegte **Monatssatz schlägt den
> Stammwert** — aufgelöst ausschließlich über `resolve_einspeise_preis_cent`
> (`api/routes/strompreise.py`), mit `is not None`: **0 ct ist ein Wert**. Monate ohne
> Eintrag rechnen mit dem Stammwert. Die Hochrechnung nach vorn (Aussichten-Prognose) und
> die ROI-Rechnung über die Lebensdauer nehmen bewusst den heutigen Stammwert —
> künftige Monate haben keinen Monatswert (dieselbe Begründung wie beim Netzbezug, N-113).
> eedc holt den Satz **nicht** automatisch ab (keine länderspezifische Quelle); er wird
> eingetragen oder per CSV importiert (Spalte `Einspeiseverguetung_Cent`).

> **Kanonisches Finanz-Aggregat (SoT `core/berechnungen/finanz_aggregat.py`):** Netto-Ertrag,
> Einspeise-Erlös, EV-/BKW-Ersparnis und Sonstige-Netto werden **per-Monat** gerechnet und über die
> sichtbaren Monate summiert (nicht mit einem Ø-Preis) — bei Flex-Tarifen (Tibber/aWATTar/EPEX) laufen
> Monats-Preis und EV/Netzbezug-Split sonst auseinander (#326). Der **naive** `netto_ertrag_euro`
> = Σ der fünf Summanden (Einspeise-Erlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto + Erlös eigener Satz,
> nächster Kasten); Sichten mit USt-Abzug bilden den Netto-Ertrag über die Ergebnis-Leiter (`berechne_ergebnis`, oben).

> **Der fünfte Summand — Erlös mit eigenem Vergütungssatz (§9.2 Geldseite):** Ein
> Gerät der Kategorie *Abgabe an Dritte* oder ein *Sonstiges/Erzeuger* mit eigenem Einspeisetarif
> trägt einen **gepflegten** Monatsbetrag (`einspeise_erloes_euro`). Er ist Teil des Netto-Ertrags
> (`finanz_aggregat.erzeuger_erloes_euro`) und steht **neben** `Einspeise-Erlös`, nicht darin: Jener
> bewertet den **Anlagenzähler** mit dem EINEN Satz der Anlage, dieser trägt einen Satz, den eedc
> nicht kennt und **nicht nachrechnet**. Alle Sichten führen ihn — Cockpit → Monat/Jahr,
> Auswertungen → Finanzen, HA-Sensor `netto_ertrag_euro`, Jahresbericht-PDF und Aussichten.

> **G19-1 — Sonstige Positionen auf Anlage-Ebene:** `Sonstige-Netto` umfasst **auch**
> die auf **Anlage-Ebene** (nicht nur pro Komponente) erfassten Positionen — siehe [§3.10](#310-sonstige-positionen).
> Sie fließen als eigene T-Konto-Zeilen „Anlage — Sonstige Erträge/Ausgaben" in **fünf** Anlage-Finanz-
> Pfade (Cockpit-Monat/-Jahr, Übersichts-Netto, PDF-Jahresbericht, HA-Export-Netto-Sensor); die migrierten
> `Monatsdaten.sonderkosten_euro` rechnen dort mit. In den Aussichten- und ROI-Pfaden (investitions-zentrierte
> Amortisation, s. [§3.6](#36-roi--amortisation) / [§4.4](#44-finanz-prognose--amortisation)) wirken sie im
> **Kapitaleinsatz** — Ausgaben erhöhend, Erträge mindernd —, gelesen aus den Monats-Fakten; auf einer ROI-Zeile stehen
> sie nicht, weil sie keine Investition haben (Wirtschaftlichkeits-Konzept Bauschritt 4, §3.6 „Anlagenweite Positionen").

> **Grundgebühr / Zählergebühr (K3):** Die **Grundgebühr** (`Strompreis.grundpreis_euro_monat`)
> steckt bereits in den Netzbezugskosten (s. [§3.1](#31-energie-bilanz-monatskennzahlen)); der Cockpit-Finanz-Teaser
> (Monat + Jahr) weist sie zusätzlich **nachrichtlich** aus („davon Grundgebühr: … €"). Sie ist die **Summe der
> Grundpreise aller im Monat gültigen Tarife** (N-769): der allgemeine Tarif plus ein **eigener**
> Wärmepumpen- oder Wallbox-Tarif (zweiter Zähler). Ein Komponenten-Tarif zählt nur mit einem eigenen Datensatz dieser
> Verwendung — ohne ihn rechnet die Komponente mit dem allgemeinen Tarif, und dessen Grundpreis zählt nicht doppelt.
> Gebildet an **einer** Stelle (`services/monats_fakten/tarif.py::grundpreis_des_monats`): Tarif-Fakten
> (`TarifFakten.grundpreis_euro_monat` — Übersicht, Auswertungen → Tabelle, Komponenten-Zeitreihe), *Cockpit → Monat*
> samt Vorjahresmonat und Jahr, `GET /monatsdaten/{id}`. Trägt ein Komponenten-Tarif bei, nennen Herleitung, Teaser und
> PDF-Monatsbericht die Grundgebühr je Tarif (`grundgebuehr_aufteilung`, im Jahr Σ je Tarif; Monate ohne Aufteilung
> zählen als „Standard"). Der Grundpreis des Komponenten-Tarifs steht **nur** in der Stromrechnung — nicht zusätzlich in
> WP-Kosten, WP- oder E-Mobilitäts-Ersparnis (sonst stünde er im Ergebnis doppelt). Die **Zählergebühr**
> (optionales Tarif-Feld `Strompreis.zaehlergebuehr_euro_jahr`) wird im Jahr-Modus als „Zählergebühr:
> … €/Jahr (nachrichtlich)" gezeigt, aber **nicht** in Kosten/Netto verrechnet — eine Einrechnung wäre ein
> eigener Kennzahlen-Entscheid. Jahresfaltung (`falte_zeitraum`): Grundgebühr = Σ, Zählergebühr = letzter Wert.

> **Cockpit-Finanzen-Block = Komponenten-Finanz-Tabelle (G20-1):** Der
> Finanzen-Block in Cockpit-Monat/-Jahr zeigt **eine Zeile je Komponente** (Reihenfolge = Typ-SoT) mit den Spalten
> **Erträge** (tatsächliche Zahlungsflüsse) · **Einsparungen** (kalkulatorisch/vermiedene Kosten) · **Aufwand** (inkl.
> anteilig umgelegter Betriebskosten, PV-Zeile bei Regelbesteuerung inkl. USt auf den Eigenverbrauch; die
> Netzladung des Speichers steht an seiner Zeile nur als Ausweis — sie läuft über den Hauszähler und steckt in der
> Stromrechnung, wie im T-Konto) · **Saldo**; die **Summenzeile ist die Block-Kopf-Kennzahl** (Kopf == sichtbare Summe).
> Eine Attribution verteilt einen Betrag, sie vervielfacht ihn nicht (#402): die Tabelle verteilt dieselben Posten wie
> die **Ergebnis-Leiter** (oben) auf die Komponenten; ihre Zusatzzeile **„Monatsergebnis"/„Jahresergebnis"** **liest**
> `ergebnis_euro` (G20-4). Beide Wege führen auf dieselbe Zahl — die Probe P8 misst es an echten Antworten. Die
> **Wärmepumpen-Ersparnis** der Kachel ist die Σ der Gerätezeilen (Bauform wie die E-Mobilität, G20-2), und die
> **Speicher-Netzladung** steht nicht zusätzlich im Aufwand der Speicher-Zeile. Das Vorjahr folgt derselben Regel
> wie der Monat (Ergebnis-Leiter, „Fehlende Eingänge").

> **Die Zeile „Balkonkraftwerk" im T-Konto (Cockpit → Monat/Jahr, N-724/N-607).**
>
> ```
> BKW-Zeile (Ersparnis) = Anteil_bewertet × EV_Preis / 100      (EV_Preis: EV-gewichteter Ø des Monats, sonst Netzbezug_Preis)
> Anteil_bewertet       = bkw_beitrag_im_monat(…).anteil_bewertet (an Modul-Kinder abgetreten ⇒ 0; ohne Zählerzeile nicht bewertbar)
> BKW-Zeile (Erlös)     = Einspeisung_BKW × Einspeisevergütung / 100
> ```
>
> Die Ersparnis ist ein **Teil** der Eigenverbrauchs-Ersparnis — T-Konto und Komponenten-Tabelle schneiden sie dort
> heraus, sie ist kein zweiter Posten — und trägt deshalb deren Preis (N-607). Den bewerteten Anteil an der Hausbilanz
> rechnet dieselbe Stelle wie *Komponenten → Balkonkraftwerk* (`services/monats_fakten/ableitungen.py::bkw_beitrag_im_monat`
> ⇒ `core/berechnungen/bkw_finanz.py::bkw_eigenverbrauch_anteil`, ADR-002/P9, ohne bewertbare Wandlungsverluste N-588):
> ein an Modul-Kinder abgetretenes Gerät (ADR-002/P11) trägt 0, ohne Zählerzeile ist der Anteil nicht bewertbar (P4) —
> keine 0 und nie die ganze Erzeugung. Ohne Monats-Fakt (Einzelaufruf) trägt nur ein gemessener Eigenverbrauch der
> Zeile. Code-Ort
> `aktueller_monat/tkonto.py::_bkw_zeile`; Probe `test_n724_bkw_hub_gleich_tkonto.py`.

> **Anschaffungsdatum-Grenze auch im Vorjahres-Vergleich (DI-5/DI-2-C):** Der Trend-Pfeil zum Vorjahr
> zieht die Vorjahres-Werte **symmetrisch** zum laufenden Monat — WP- und E-Mob-Ersparnis fließen nur
> für im jeweiligen Vorjahresmonat **aktive** Komponenten ein (`ist_aktiv_im_monat`, also innerhalb
> Anschaffungs-→Stilllegungs-Fenster), und die energieseitige Vorjahres-Aggregation ist gleich gefiltert.
> Dienstwagen (`ist_dienstlich`) bleiben in beiden Jahren aus den E-Mob-Bilanzen. So vergleicht der
> Pfeil gleiche Komponenten-Mengen, statt Alt-Werte vor der Anschaffung mitzuzählen.

#### WP-Ersparnis im Cockpit — Σ der Gerätezeilen je Monat

```
Zeile(Gerät, Monat) = (Wärme / η × Gaspreis + Zusatzkosten / 12) − (Strom − Kühlstrom) × WP-Preis
                      — nur bei Wärme > 0 UND Strom > 0, je Zeile auf 2 Stellen gerundet
WP-Ersparnis        = Σ Monate Σ Geräte Zeile
```

Wobei:
- **Mengen je Gerät** — Monat mit Gerätezeile: Monats-Fakten `WpFakten.je_geraet` (Strom nach K3, Wärme nach D1,
  Kühlanteil nach der Betriebsart-Weiche, auch der nachgetragene Modus-Split eines Monats ohne Abschluss); Monat ohne
  Gerätezeile (laufend, bzw. abgeschlossen ohne Abschluss): die Quellen-Kaskade je Gerät
  (`inv_<id>__strom_k3_kwh` / `inv_<id>__waerme_d1_kwh`).
- **η, Gaspreis-Default, Zusatzkosten** aus den Parametern **des Geräts** (`berechne_wp_ersparnis`).
- **Gaspreis** des Monats (`Monatsdaten.gaspreis_cent_kwh`), sonst der des Geräts.
- **WP-Preis** des Monats (`TarifFakten.wp_preis_cent`, am Stichtag des Monats, ADR-002/P8): mit **eigenem**
  Wärmepumpen-Tarif dessen Kaskade (WP-Tarif, mit Zeitfenstern); **ohne** ihn hängt die Wärmepumpe am Hauszähler und
  trägt dessen Preis mit der ganzen Kaskade — abgerechneter Monats-Ø → gemessener Ø → Zeitfenster → Stammpreis (N-663).

**Eine Zeilenregel** (`services/wp_wirtschaftlichkeit.py::wp_ersparnis_zeile`, Monatssumme `wp_ersparnis_monat`) für
T-Konto und Kachel in *Cockpit → Monat* (auch ohne Gerätezeile), *Cockpit → Jahr* (Σ Monate), *Cockpit → Übersicht*
(Feld `wp_ersparnis_euro`, geht in `jahres_rendite_prozent`) und *Auswertungen → Komponenten* (N-605/N-609). Grund:
zwei Wärmepumpen haben keine gemeinsame Referenz-WP — kein Aggregat mit dem Parametersatz eines Geräts, kein heutiger
Tarif für vergangene Monate. Die Zeilenrundung hält Σ Zeilen = Sicht.

**Standby-Monat** (N-670): Ein Monat mit gemessenem WP-Strom und gemessener Wärme 0 ist eine Zeile
mit **0 €** (Etikett „Standby", Stromkosten echt, kein Vergleich gegen die Alternative). Dieselbe Regel gilt im
HA-Sensor je Wärmepumpe und in der Jahresformel `berechne_wp_alternativkosten_ersparnis` (Aussichten, ROI-Fortschritt,
Jahres-Ersparnis des HA-Exports): ein Monat mit Strom ohne Wärme trägt dort weder Stromkosten noch den Zwölftel
Zusatzkosten. Proben: `test_n605_wp_ersparnis_aus_geraetezeilen.py`, `test_n609_wp_ersparnis_je_geraet.py`,
`test_n670_wp_standby_zeile.py`.

#### E-Mob-Ersparnis im Cockpit

```
Benzin_Verbrauch    = Σ(km_gefahren) * Vergleichsverbrauch / 100   (Parameter des Autos, Default 7,5 L/100 km)
Benzin_Kosten       = Benzin_Verbrauch * Benzinpreis               (Kraftstoffpreis des Monats, sonst Parameter, sonst 1,65 €/L)
Strom_Kosten        = Ladung_Netz * Wallbox_Preis / 100
                    + Ladung_PV   * EV_Preis      / 100   (N-672: Preis der Eigenverbrauchs-Ersparnis des Monats)
                    + Kosten_externe_Ladung
Fossile_Kosten      = km_Verbrenner / 100 * eigener_Verbrauch * Benzinpreis   (nur Plug-in-Hybrid, #331; sonst 0)
E-Mob-Ersparnis     = Benzin_Kosten - Strom_Kosten - Fossile_Kosten
```

`Fossile_Kosten` und die Aufteilung der Kilometer stehen in §3.4
([Plug-in-Hybrid](#plug-in-hybrid-elektrischer-und-fossiler-anteil-ab-331)).

> ⭐ **Eine kWh ist einmal Geld (N-672).** Die PV-Ladung steckt im Eigenverbrauch der Anlage und ist
> dort schon zum Strompreis gutgeschrieben; „kostenlos" wäre sie zweimal Geld. Sie trägt genau den Preis, zu dem die Eigenverbrauchs-Ersparnis derselben
> Sicht sie gutschreibt (gepflegt · gemessen · Zeitfenster · Stamm, §3.1); die Netzladung behält den Wallbox-Tarif.
> „Davon aus PV" bleibt als Menge und Anteil sichtbar — als Information, nicht als eigener Geldposten. Eine Formel
> für alle Sichten: `core/berechnungen/heimladung_kosten.py`.

> **Wallbox-Tarif und Stromrechnung (N-771).** Die E-Mob-Ersparnis zieht die Netzladung zum Wallbox-Tarif ab; ohne
> Messung rechnet die Stromrechnung denselben Strom zum Haushaltstarif (mit einer Wallbox hinter dem Netzbezug-Messpunkt
> fehlt dem Ergebnis dann Netzladung × (Haushalt − Wallbox-Tarif)). eedcs Netzladung ist eine **Zuteilung** (N-569),
> keine Messung der abgerechneten Menge. Deshalb dieselbe Messgröße wie an der Wärmepumpe: das optionale Feld
> **„Netzbezug zum Wallbox-Tarif"** an der Wallbox — gemessen, rechnet die Stromrechnung diese Menge zum Wallbox-Tarif
> (`wallbox_preis_effektiv_cent`, §3.1, Kasten).
> **Die Netzladung aus dem Zähler (F11):** wo das Feld an einer Wallbox-Zeile steht, **ist** N_wb ihre
> Netzladung — auch gegen einen gepflegten evcc-Wert; PV-Ladung = Ladung − N_wb (Trias geschlossen), N_wb auf
> `[0, Ladung]` geklemmt (`core/field_definitions/reader.py::netzladung_des_zaehlers`, gelesen von
> `get_emob_pv_netz_kwh` und damit vom Pool der Monats-Fakten, T-Konto, Wallbox-Hub, HA-Export E-Mob; die Tagesquote
> überschreibt eine solche Zeile nicht). Vorrang der Netzladung für Geld: *Zähler des Versorgers* → *evcc-Regel* →
> *eedc-Tagesquote*. **Zuordnungsmonat (N-771 Rest 1, E6):** dieselbe F10-Regel wie die Stromrechnung, je Gerät — im
> Kalendermonat, in dem der Kanal des Felds dieser Wallbox beginnt, ist der Monatswert eine Teilmenge und gilt auch an der
> Wallbox-Zeile nicht; es greift die Regel ohne Feld (evcc-Wert bzw. Gesamt − PV, danach die Tagesquote). Die Zuordnungsmonate
> kennt eine Stelle (`kanal/netzanteil_leser.zuordnungsmonate_der_wallboxen`, je Anfrage gemerkt, eine Abfrage nur, wenn
> eine Zeile das Feld trägt); die Auskunft reist an der Zeile (`reader.ZeileImZuordnungsmonat`) zu
> `netzladung_des_zaehlers` (Parameter `zuordnungsmonat`). E-Mob-Ersparnis und Heimladekosten lesen diese Netzladung; die Herleitung der Wallbox-Zeile und
> eines E-Autos, dessen Heimladung aus der Wallbox kommt, nennt «Netzladung: Zähler des Versorgers». Wirkung: Netz und PV
> der Wallbox-Zeile tauschen (N_wb − Netz_vorher) kWh; die E-Mob-Ersparnis bewegt sich um den Teil davon, der beim Auto
> ankommt, × (Preis der Eigenverbrauchs-Ersparnis − Wallbox-Tarif). ⚑ Ein E-Auto **mit eigener Messung** der Heimladung
> behält sie (Regel 2 Schritt 1, N-555) — der Zähler teilt dann nur den Rest der Wallbox; neben einer Wallbox, die das
> Feld trägt, wird die Wallbox-Zeile zudem als PV-Ladung-Zeile im T-Konto sichtbar (Teil der Eigenverbrauchs-Ersparnis,
> kein Posten). Die zweite Klemme der Stromrechnung (N_wb ≤
> Netzbezug − N_WP) gilt nur dort; die E-Mob-Zeile behält N_wb bis zur Ladung (Daten-Checker nennt den Monat). Der
> Daten-Checker warnt, wenn ein gepflegter evcc-Anteil und N_wb abweichen.

**Hinweis:** Dienstliche E-Autos/Wallboxen (`ist_dienstlich = true`) werden NICHT in die E-Mob-Ersparnis eingerechnet. Deren Ladekosten sind ein eigener Posten der Ergebnis-Leiter („Dienstliche Ladekosten", §3.2, N-633) — Formel und Begründung stehen in §3.10 unter **Dienstliche Ladekosten** — der PV-Anteil zählt dort zum **Netzbezugspreis**, nicht zur Einspeisevergütung.

> **G20-2 — Aggregat bei mehreren E-Autos = Σ der Einzel-Fahrzeuge:** Die Gesamt-E-Mob-Ersparnis wird als **Summe der pro Fahrzeug** gerechneten Ersparnisse gebildet — jedes E-Auto mit seinem **eigenen** Vergleichsverbrauch (L/100 km) und Benzinpreis, wie die Per-Fahrzeug-Zeilen im T-Konto. Sie ist NICHT ein Einmal-Lauf über die Gesamt-Kilometer mit dem Parametersatz des ersten Fahrzeugs.

**Heimladung je Auto (N-555 Stufe 2):** Die Wallbox ist die **Summe** aller Ladungen an ihr; jedes Auto mit eigener Messung trägt seine eigene Heimladung, die Wallbox den Rest (Regel 2 und 3 unten). Bei mehreren Wallboxen zählt ihre Summe. Die Netzladung **je Fahrzeug** in der Ersparnis ist die Summe seiner Monatsmengen aus dem Entscheid (`EmobFakten.je_auto`), kein km-Anteil an einem gemeinsamen Topf; ein Auto, das geladen hat, aber nicht gefahren ist, trägt seine Stromkosten (Ersparnis negativ statt 0). Zentraler Helper: `entscheide_emob_heimladung()` (`services/eauto_wirtschaftlichkeit.py`; `get_emob_heimladung_canonical()` ist seine Kurzform).

#### Heimladung und Fahrverbrauch — zwei verschiedene Mengen (ab N-555)

Am E-Auto gibt es zwei Energiemengen, die leicht zu verwechseln sind:

- **Heimladung** — was zu Hause ins Auto geladen wird. Gemessen an der **Wallbox** („Ladung gesamt", „Ladung PV")
  und, wo vorhanden, am Auto („Heim: PV", „Heim: Netz", der alte Gesamtwert `ladung_kwh`). Das sind die
  **Heimlade-Felder** (`core/field_definitions/heimladung.py::HEIMLADE_FELDER`).
- **Fahrverbrauch** — das Feld **„Verbrauch"** am E-Auto (`verbrauch_kwh`): was das Auto beim Fahren aus seiner
  Batterie verbraucht. Daraus rechnet eedc die kWh/100 km und beim Plug-in-Hybrid den elektrischen Anteil.

**Regel 1 — der Fahrverbrauch springt nur ein, wenn über die Heimladung nichts bekannt ist:** Er zählt nur dann als
Heimladung, wenn für die Heimladung **weder ein Wert erfasst** (auch **0** ist ein Wert) **noch** — im laufenden Monat,
am Tag, in der Stunde — **eine Quelle zugeordnet** ist (HA-Sensor oder angekommene MQTT-Zählerstände; eine Quelle
„keine" zählt nicht). Dann ist er eine **Schätzung**: ausdrücklich so gekennzeichnet (`quelle = "schaetzung"`), nie
gespeichert. Abgeschlossene Monate entscheiden nur nach dem gespeicherten Wert; ergänzt *Cockpit → Monat* einen Monat
ohne Monatsabschluss aus der HA-Statistik, zählt deren Wert wie ein gespeicherter, auch 0, sofern die Statistik Daten
hat. Die Entscheidung fällt **je Monat**; ein Jahr, eine Übersicht, ein Hub-Zeitraum ist die **Summe seiner Monate**.

**Regel 2 — wer welche Heimladung trägt** (je Monat):

```
Schritt 1  Jedes Auto mit EIGENER Messung trägt sie — privat und Dienstwagen, auch neben
           einer Wallbox, unabhängig von den km. Eigene Messung = „Heim: PV", „Heim: Netz"
           oder „Heim: gesamt" (`ladung_kwh`) mit Wert (auch 0) oder — laufend — Quelle.
             · „Heim: PV/Netz" gehen vor; ist nur eines erfasst, zählt das andere als 0.
             · „Heim: gesamt" wird mit dem PV-Anteil der Wallbox im Monat geteilt
               (ohne Wallbox wie jede Heimladung abgeleitet).
             · `ladung_kwh` mit Herkunft „legacy:unknown" oder ohne Herkunft ist der ALTE
               Gesamtwert: er zählt nur ohne Wallbox in Betrieb.
Schritt 2  Rest = Σ private Wallboxen − Σ eigene Messungen, nie unter 0;
           Rest-PV = Wallbox-PV − Auto-PV, in [0, Rest]   ⇒  Autos + Rest = Wallbox
Schritt 3  Der Rest geht nach km an die privaten Autos in Betrieb OHNE eigene Messung
           (auch ohne Monatszeile; bei 0 km zu gleichen Teilen). Gibt es keines, ist er
           NICHT ZUGEORDNET (Gast, Verluste): nur Verbrauch, keine Ersparnis — außer es ist
           gar kein Fahrzeug (privat oder dienstlich) in Betrieb: dann ist die Wallbox das
           private Auto und der Rest geht in die Heimladung.
Wallbox leer (kein Wert, keine Quelle)  ⇒ Regel 1 für die Autos ohne Messung (Schätzung)
Wallbox 0                               ⇒ Rest 0
Ohne private Wallbox in Betrieb         ⇒ jedes Auto seine Messung (auch der alte Gesamtwert), sonst Regel 1
```

Beispiel: Wallbox 400 kWh (200 PV / 200 Netz). Auto A misst 100 (70/30), der Dienstwagen „Heim: gesamt" 150
(Wallbox-Anteil 50 % ⇒ 75/75), Auto B ohne Messung ⇒ Rest 400 − 250 = 150, davon PV 200 − 145 = 55, Netz 95 an B.

Misst die Wallbox 0, ist die Heimladung der Autos ohne eigene Messung **0** (Rest 0) — ihr „Verbrauch" zählt dann nur
für die kWh/100 km. Eine Schätzung bekommt denselben aus der Tagesebene abgeleiteten PV-Anteil wie jede andere
Heimladung (s. „PV-Anteil der Heimladung" unten).

**Regel 3 — wozu die Menge zählt, und was „die Heimladung" ist:** Die Heimladung (`EmobFakten.ladung_*`, gelesen von
Cockpit, CO₂-Bilanz, PV-Anteil der Heimladung, HA-Anlagen-Sensoren, Jahresbericht, Aussichten, Community E-Auto-Seite)
ist die **Summe der privaten Autos** — eigene Messungen, zugeordneter Rest, Schätzungen (`Σ je_auto`). Daneben stehen
mit eigenem Namen: die **Messung der Wallbox** (`wallbox_summe` — Energiebilanz, Tag, Stunde, Wallbox-Sichten), der
**nicht zugeordnete Rest** (`rest_*` bei `rest_zugeordnet = False`) und die **dienstliche Ladung**. Trägt die Wallbox über
0, gilt `Wallbox = Heimladung + nicht zugeordnet + Dienstwagen gemessen`, solange die Autos die Wallbox nicht übersteigen
(sonst rechnen sie mit ihren Werten weiter und der Daten-Checker warnt). Die **Wallbox-Sicht** zeigt als kWh die
Messung der Wallbox, rechnet ihre „Ersparnis gegenüber externem Laden" und die Amortisation aber mit der Heimladung.

Der **Dienstwagen**: mit eigener Messung ist sie seine dienstliche Ladung und fehlt im Rest; an einer **dienstlichen
Wallbox in Betrieb** ist deren Menge die dienstliche Ladung, Felder und Schätzung des Dienstwagens zählen dann nicht;
ohne eigene Messung ist sein Fahrverbrauch die Schätzung (als Netzstrom, `EmobFakten.dienstlich_geschaetzt`) und wird
**nie** vom Rest abgezogen (sie enthält auch das Laden beim Arbeitgeber).

**Ladevorgänge je Auto — Regel 9 (N-555 Stufe 3):** Trägt ein Auto an „Heim: gesamt" einen **Zähler**, der
am Ende eines Ladevorgangs um dessen Menge springt (evcc-Fahrzeug-Sensor), und hat eine Wallbox in Betrieb einen
Ladezähler, ordnet die Tagesberechnung jeden Sprung den Stunden der Wallbox zu (`services/emob_ladebloecke.py`, Ablage
`emob_ladebloecke`, geschrieben aus `aggregate_day`):

```
Block    vom Sprung rückwärts über die Wallbox-Stunden; aus jeder Stunde, was frühere Blöcke nicht genommen
         haben — in der Sprungstunde höchstens den Bedarf, davor höchstens Bedarf + 0,05 kWh —, bis
         Σ ≥ Sprung − 0,05 kWh, höchstens bis zur Stunde des vorigen Sprungs IRGENDEINES Autos (einschließlich).
         Nullstunden werden übersprungen; eine gemeinsame Stunde wird nach Restmengen geteilt.
Menge    = der Sprung (gemessen am Auto) — nie die Summe der Wallbox-Stunden.
PV       = Σ (Blockstunde × PV-Anteil dieser Stunde nach der Einspeise-Deckung) ÷ Σ ableitbare Blockstunden × Sprung
           (ableitbar = Anteil bekannt und keine gebündelte Stunde; davon aus dem Speicher ebenso, als Teilmenge,
           höchstens der PV-Teil);
           eine gebündelte Stunde (Zählerlücke, n > 1) zählt zur Blockenergie, liefert aber keinen Anteil —
           ohne ableitbare Stunde teilt der Wallbox-Monatsanteil. Der Anteil ist eine Schätzung derselben
           Regel wie der PV-Anteil der Heimladung.
Monat    Anteil eines Monats = Σ Blockstunden, die in ihm BEGINNEN, ÷ Σ Blockstunden, angewandt auf den Sprung.
           Ein Sprung ohne Blockstunde zählt im Monat des Sprungs.
Kennzeichen  stunden_gedeckt = Σ Blockstunden ÷ Sprung; unter 0,95 hat die Wallbox den Vorgang nicht voll gezählt.
           Mikrosprünge bis 0,05 kWh (Standby des Fahrzeug-Zählers) zählen als Menge, nicht als Ladevorgang.
```

Code-Orte (RF-80): `emob_ladebloecke.py::bilde_ladebloecke` sammelt die Blöcke über `_wallbox_achse` (mehrfach genannte
Stunden summiert, Stunden ≤ 0 fallen weg, Restmenge nach den schon gespeicherten Blöcken), `_spruenge_nach_zeit`
(Reihenfolge nach Zeit, dann Auto; ein Sprung ≤ 0 bildet keinen Block und setzt keine Schranke), `_block_rueckwaerts`
(Zeile «Block») und `_block_anteile` (Zeilen «Menge», «PV», «Kennzeichen»).

In Regel 2 Schritt 1 ist die Summe der monatsverteilten Sprünge dann die eigene Messung des Autos (Menge **und**
PV-Anteil) an der Stelle von „Heim: gesamt"; „Heim: PV/Netz" gehen weiter vor. Der Daten-Checker (Regel 7) vergleicht
dieselbe Größe mit dem Wallbox-Monatswert. **Bedingung:** die Blöcke eines Autos gelten für einen Monat nur, wenn jeder
Tag des Monats bis gestern, an dem das Auto in Betrieb war, nach dem Lückenhandling gerechnet ist (Tageszeile mit
Regelmarke); die Blöcke von heute zählen, sobald die heutige Tageszeile existiert. Sonst rechnet der Monat ohne sie. *Grund:* die Blöcke entstehen nur an so gerechneten Tagen; ein Monat mit
nur einem Teil davon hätte eine zu kleine Menge je Auto und einen zu großen Rest.

**Tag und Stunde** wählen über **eine** Auswahl (`snapshot/komponenten_beitraege.py`): Ist eine Wallbox mit Zähler
**in Betrieb**, zählt die Wallbox, und die Heimlade-Zähler der Autos zählen nicht zusätzlich — auch nicht in der Stunde.
Sonst zählt je Auto „Heim: PV" + „Heim: Netz", sonst der alte Gesamtwert, sonst „Heim: PV" allein, und der
Fahrverbrauch nur, wenn keines davon eine Quelle hat. Gewählt wird nach der **Quelle**, nicht nach den Tagesdaten;
die Summe der Stunden ergibt den Tag.

**Ø Verbrauch (kWh/100 km) — Quellen-Vorrang:** Die Effizienz-KPI in E-Auto-Dashboard, Monatsbericht und Komponenten-Auswertung kommt aus **einem** Helper (`core/berechnungen/emob.py`, `eauto_effizienz_100km`):

```
1. gemessener Fahrverbrauch:  verbrauch_kwh ÷ km × 100                  (Vorrang, exakt)
2. sonst Näherung aus Ladung: (Heimladung + Extern) ÷ km × 100          (Fallback)
3. sonst:                     —   (nie 0,0 erfinden)
```

Die Ladungs-Näherung **überschätzt** den echten Fahrverbrauch (AC-Ladung an der Wallbox enthält Ladeverluste ~10–15 %, blendet SoC-Drift + nicht erfasste Fremdladung aus) — in der UI als „≈ aus Ladung (inkl. Ladeverluste)" gelabelt. Vorteil: funktioniert auch ohne Verbrauchssensor (den die wenigsten Fahrzeuge liefern). Alle Read-Sites zeigen denselben Wert. Symmetrie abgesichert durch `test_emob_readsite_symmetrie.py` und `test_n555_fahrverbrauch_bleibt_fahrverbrauch.py`.

**Zeitraum (Jahr, Übersicht, Hub, Auswertungen) — N-557:** Jeder Monat entscheidet für sich (Regel oben), der
Zeitraum ist die **Summe der Monatswerte geteilt durch die Summe der Kilometer**
(`eauto_effizienz_zeitraum`; *Cockpit → Jahr* ruft sie über die Jahresroute). Monate ohne jede
Energiemenge zählen weder im Zähler noch im Nenner. „gemessen" steht nur, wenn **jeder** Monat mit Kilometern gemessen
ist, sonst „Näherung über die Ladung".

**„Ladung gesamt" — N-557:** Heimladung **plus Extern**, soweit Extern bekannt ist (mit Sensor im laufenden Monat
sofort, bei Pflege von Hand ab dem Monatsabschluss); darunter „davon extern … kWh". Eine **eigene** Anzeige-Größe
(`emob_ladung_gesamt_kwh`): die Heimladung (`emob_ladung_kwh`) behält ihre Bedeutung, der **PV-Anteil** bleibt auf
die Heimladung bezogen, T-Konto, CO₂ und Community rechnen mit ihr. Extern liegt außerhalb der Hausbilanz.

**Externe Ladung je Monat — eine Quelle (N-728):** Externe Ladung kann am Auto stehen oder (Altbestand)
an der Wallbox-Zeile. Welches Paar (kWh, €) zählt, entscheidet die Topf-Regel `waehle_extern_paar` **je Monat** — ist die
Wallbox im Monat die Heimlade-Quelle, gewinnt das Paar mit den höheren Kosten aus dem km-Anteil am Extern der
Wallbox-Zeilen und dem Extern des Autos (`emob_extern_im_monat`, dieselbe Funktion wie HA-Export und Aussichten). Der
E-Auto-Hub summiert diese Monatswerte, und seine Monatszeilen (Verlauf, Tabelle, Jahresvergleich) tragen genau sie.
Bei **Kosten-Gleichstand** gewinnt die **größere Menge**, erst bei gleicher Menge die Wallbox — extern am Auto ohne
Euro neben einer Wallbox zählt damit in jeder Sicht.

**Hinweis Kraftstoffpreis:** Cockpit (#260), **Finanz-Prognose** ([Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen)), **HA-Sensor-Export** und **PDF-Finanzbericht** nehmen je Monat den Kraftstoffpreis des Monats aus `Monatsdaten.kraftstoffpreis_euro` (Quelle: EU Weekly Oil Bulletin), ohne Monatswert den `benzinpreis_euro`-Parameter der Komponente, sonst 1,65 €/L. Das Formularfeld *Benzinpreis (€/L)* ist nicht vorbelegt (N-572): ein geleertes Feld bleibt leer, und die Kette fällt dann auf 1,65 €/L zurück.

#### Investitionskosten (Mehrkosten-Ansatz)

```
Investition_gesamt   = relevante Kosten = Σ_Investitionen max(0, anschaffungskosten_gesamt − anschaffungskosten_alternativ)
                       Einzeljahr: nur Investitionen mit Anschaffung ≤ 31.12. (ohne Datum: immer; N-720)
```

Eine Definition für Rendite, ROI, Amortisation und USt-Bemessung (N-137, SoT
`core/berechnungen/investitionskosten.py::relevante_kosten_aus_investitionen`): ohne gepflegte Alternativkosten zählen die
Vollkosten, Festannahmen setzt eedc nicht ein (§3.6).

### 3.3 Speicher-Einsparung

**Funktion:** `berechne_speicher_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`GET /api/investitionen/roi/{anlage_id}`, Paket `api/routes/investitionen/`; Aufruf in
`roi.py::_speicher_roi`)

#### Eingabefelder

Die Monats-Messgrößen des Speichers (Ladung, Entladung, Netzladung, Ladepreis) stehen in der
[Übersicht der Größen §1](UEBERSICHT-GROESSEN.md#1-eingabefelder) und in der
[Sensor-Referenz §3](SENSOR-REFERENZ.md#3-speicher-batterie); ihre Monatsregel steht unten unter „Ladung, Entladung und
Netzladung des Monats". Diese Rechnung liest die Investitions-Parameter (`core/investition_parameter.py`,
`PARAM_SPEICHER_DEFAULTS`); gemessener Wirkungsgrad und gemessener Ladepreis gehen den Parametern vor
(`roi.py::_aufloesen_wirkungsgrad`, `_aufloesen_ladepreis`):

| Feld | Quelle |
|------|--------|
| `kapazitaet_kwh` | `get_speicher_nutzbare_kapazitaet_kwh(inv)` — **netto**, still auf brutto zurückfallend (A31-2/E17, s. u.). Greift nur im Prognose-Modus; mit gemessener Entladung übernimmt der Spread-Service und liest gar keine Kapazität. |
| `wirkungsgrad_prozent` | `Investition.parameter["wirkungsgrad_prozent"]` (Default: 95) |
| `arbitrage_faehig` | `Investition.parameter["arbitrage_faehig"]` (Default: false) — der Kanon; den Altnamen `nutzt_arbitrage` übersetzt `LEGACY_PARAM_KEYS` |
| `lade_preis_cent` | `Investition.parameter["lade_durchschnittspreis_cent"]` (Default: 12) |
| `entlade_preis_cent` | `Investition.parameter["entlade_vermiedener_preis_cent"]` (Default: 35) |

#### Formeln

Prognose-Modus — ohne gemessene Jahres-Entladung; mit ihr rechnet die Funktion den Spread
([Der Nutzen in Euro](#der-nutzen-in-euro--spread-nicht-voll-strompreis)). `250 Zyklen` = `SPEICHER_ZYKLEN_PRO_JAHR`.

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

#### Ladung, Entladung und Netzladung des Monats

`SpeicherFakten.ladung_kwh`, `.entladung_kwh` und `.netzladung_kwh` sind Summen über die Monatszeilen aller Geräte vom Typ
Speicher (`monats_fakten/roh.py::_RohMonat._falte_speicher`): Ladung aus `ladung_kwh`, Entladung aus `entladung_kwh`,
Netzladung (Arbitrage) aus `ladung_netz_kwh` (Lesetür `get_speicher_netzladung_kwh`, Rückfall auf den Altnamen
`speicher_ladung_netz_kwh`). Dieselbe Faltung bildet den mengengewichteten Ladepreis
([Der Nutzen in Euro](#der-nutzen-in-euro--spread-nicht-voll-strompreis)). Die Akku-Felder eines Balkonkraftwerks zählen
hier nicht mit (`BkwFakten.speicher_*`).

**Monat ohne Speicher-Zeile:** trägt kein Gerät vom Typ Speicher eine Zeile, die Tagessumme des Monats aber Ladung oder
Entladung > 0, kommen alle drei aus den Tagen (`monats_fakten/bau.py::_speicher_aus_tagen`, #427, Entscheid Gernot
13.10.2026) — Ladung und Entladung aus der Tagessumme, die Netzladung samt Preis aus `monats_fakten/netzladung_tage.py`
(`netzladung_aus_tagen`; die Menge über `speicher_netzladung_aus_tagen`, die auch *Cockpit → Monat* ruft); ohne
Netzlade-Zähler ist sie 0. Der Fakt trägt dann die Marke der Tageswert-Gruppe Speicher (`TAGESWERT_SPEICHER`). Eine
Speicher-Zeile ersetzt die Tageswerte (P8). Fenster und Grenzen des Rückfalls:
[§6b „Tageswerte: Zähler und Bezug aus einem Fenster"](#tageswerte-zähler-und-bezug-aus-einem-fenster).

Die Werte-Tabelle zeigt die Netzladung im Monat als `speicher_netzladung_kwh` = `SpeicherFakten.netzladung_kwh`
(`monatsdaten_aggregiert.py::_zeile_komponenten`), sobald der Monat eine Speicher- oder BKW-Zeile oder Speicher-Tageswerte
trägt (`monatsdaten.py`, `hat_speicher_imd`).

**Kosten der Netzladung am Tag** (Kachel «Batterieladung Netz», Cockpit → Tag): `speicher_ladung_netz_kosten_euro` des Tagesdetails =
`speicher_ladung_netz_kwh × speicher_effektiver_ladepreis_cent ÷ 100` — genau die zwei Faktoren, die die Kachel nennt
(`core/berechnungen/speicher_wirtschaftlichkeit.py::netzladung_kosten_euro`, ungerundet; ohne Preis `None`, auch bei 0 kWh). Anders als die
Monats-Kette `berechne_netzladung_kosten` (TEP → IMD → Bezugspreis, 0 kWh ⇒ 0 €). Seit Päckchen Z-Client; vorher im Client.

#### Vollzyklen — eine Definition für alle Sichten

```
Vollzyklen = Entladung_kWh ÷ Kapazität_brutto_kWh
```

**SoT:** `core/berechnungen/speicher.py::vollzyklen`. Alle Sichten rufen ihn auf —
Komponenten-Hub (`investitionen/dashboard_*.py`), Cockpit Tag (`energie_profil/tage_werte.py`),
Monat/Jahr (`aktueller_monat/komponenten.py::_speicher_detail`), **Cockpit-Übersicht (`cockpit/uebersicht.py`)**,
PDF-Jahresbericht, HA-Sensor `speicher_zyklen` (`ha_export/anlage_komponenten.py`) und die Speicher-Potential-Monate
(`services/speicher_potential_service.py`).
Gewächtert von `backend/tests/test_speicher_zyklen_kapazitaets_basis.py` (inkl. Drei-Pfad-Symmetrie),
`test_tage_werte_symmetrie.py` und `test_speicher_kanon_symmetrie.py`.

> ⚠ **Eine Liste von Aufrufern ist eine Behauptung über den Code** — sie ist am baumweiten Grep (`vollzyklen(`)
> belegt, sonst dokumentiert sie den Soll- statt den Ist-Zustand.

**Warum die Entladung:** Ein Vollzyklus meint die einmal *entnommene* Kapazität — die Größe, auf die
sich Hersteller-Garantien beziehen, und unabhängig von den Wandlungsverlusten des Ladepfads. Sie ist
außerdem ein Energiedurchsatz und damit über Tag → Monat → Jahr additiv.

**Warum Brutto im Nenner:** `nutzbare_kapazitaet_kwh` ist optional und meist nicht gepflegt; ein
Nenner, der je nach Pflegezustand wechselt, wäre schlimmer als ein durchgehend leicht konservativer
Wert. Im HA-Export ist das Netto-Feld reiner **Fallback**, falls die Brutto-Kapazität fehlt — die
Lese-Reihenfolge dort ist bewusst brutto → netto (A31-2).

#### Auslastung — zeitraum-normierte Nutzung (#358 Phase 1)

```
Auslastungs-Basis  = Kapazität_brutto_kWh × Tage_im_Zeitraum
Auslastung [%]     = Entladung_kWh ÷ Auslastungs-Basis × 100
```

**SoT:** `core/berechnungen/speicher.py::auslastungs_basis_kwh` + `auslastung_prozent`.
Geliefert von `aktueller_monat/komponenten.py::_speicher_detail` (Felder `speicher_auslastungs_basis_kwh` /
`speicher_auslastung_prozent`), angezeigt in *Cockpit → Monat* und *→ Jahr*.

**Warum die Basis ein eigenes Feld ist:** Auslastungen mehrerer Monate lassen sich **nicht
mitteln** — ein Februar wiegt weniger als ein Juli, ein angefangener Monat noch weniger. Wer ein
Jahr bildet, summiert **Entladung und Basis** und teilt einmal. Ein Prozent-Mittelwert wäre die
Drift-Klasse, die diese Trennung von vornherein ausschließt (Beleg:
`test_speicher_kanon_symmetrie.py::test_auslastungs_basis_ist_additiv_ueber_monate` — 40 % und
61 % ergeben zusammen 50 %, nicht 50,5 %).

**Im laufenden Monat zählen nur die abgelaufenen Tage.** Sonst stünde am 3. eines Monats eine
Auslastung von 10 %, die nichts über den Speicher aussagt, sondern über das Datum — ein voller
Nenner gegen einen angefangenen Zähler, genau der Fall aus
[KONZEPT-UNVOLLSTAENDIGE-WERTE](KONZEPT-UNVOLLSTAENDIGE-WERTE.md) §3.

**Kein Deckel bei 100 %:** zwei Zyklen an einem Tag sind real, und die Zahl soll das sagen dürfen.
Ohne gepflegte Kapazität liefern beide Funktionen `None` — „unbekannt", nicht 0.

#### Der Nutzen in Euro — Spread, nicht Voll-Strompreis

```
PV-Anteil der Entladung   = Entladung − min(Entladung, Netzladung × η)
Netz-Anteil der Entladung = min(Entladung, Netzladung × η)

Ersparnis = PV-Anteil   × (Netzbezug − Einspeisevergütung) / 100
          + Netz-Anteil × (Netzbezug − Ladepreis)          / 100
```

**SoT:** `core/berechnungen/speicher_wirtschaftlichkeit.py::berechne_speicher_ersparnis`.
Aufrufer: T-Konto (`aktueller_monat/tkonto.py::_speicher_zeile`), Speicher-Dashboard und
Sonstiges-Speicher (`investitionen/dashboard_sonstiges.py`), Aussichten, ROI im IST-Modus (`berechne_speicher_einsparung`).
**Beide Preise je Monat aus den Monats-Fakten** (`TarifFakten.netzbezug_preis_cent` und `einspeiseverguetung_cent`:
#392-Monatssatz → Tarif des Monats → Vorbelegung 8,2 ct), in T-Konto und Hubs dieselben — auch für V2H und den
Erlös eines sonstigen Erzeugers (`investitionen/dashboard_basis.py::_gewichtete_monatspreise`; N-715/N-716: auch vor dem
ersten Tarif nie die heutige Vergütung). Gewächtert von
`test_speicher_kanon_symmetrie.py` (drei Achsen, mit **absoluten** Erwartungen — Symmetrie allein
ließe auch drei gleich falsche Zahlen durch, Lehre aus N-130).

**Warum der Spread:** die entladene kWh ersetzt Netzbezug, hätte aber sonst Einspeisevergütung
erbracht. Die entgangene Vergütung ist eine reale Gegenposition (Drift-Audit A3, #358).

**Warum die Netzladung ausgenommen ist:** sie hätte nie eingespeist werden können, der PV-Spread
gilt für sie nicht. Ihr Vorteil ist `Netzbezug − Ladepreis`; ohne gepflegten Ladepreis ist sie
kostenneutrale Durchleitung (z. B. Backup-Vorhaltung).

**Der Ladepreis eines Monats ist verbrauchsgewichtet** — die Faltung der Monats-Fakten
(`monats_fakten/roh.py::_RohMonat._falte_speicher`) summiert je Speicher-Zeile Preis × Menge und Menge, der Ø entsteht
erst beim Lesen (`SpeicherFakten.netzladung_preis_cent`):

```
Ladepreis_Monat = Σ (Ladepreis_Zeile × Netzladung_Zeile) / Σ Netzladung_Zeile
                  nur Zeilen mit Ladepreis > 0 und Netzladung > 0; Σ Gewicht = 0 ⇒ None (Leser fallen auf den Bezugspreis)
```

Gewichtet wird nach Menge, nicht über das Mittel der Preise. Ohne Speicher-Zeile trägt der Tageswert-Rückfall dieselben
zwei Felder TEP-gewichtet aus den Tagen (#427, §6b).

> ⚠ **Keine Sicht rechnet die Entladung zum vollen Bezugspreis oder den Spread inline**, und keine weist den
> Netz-Anteil zusätzlich als Arbitrage-Gewinn aus — sonst zählte netzgeladene Energie doppelt. Die Formel im Layer zu
> haben genügt nicht; sie ist erst durchgesetzt, wenn keine Inline-Kopie mehr danebensteht (ADR-001).

#### Preis- und Speicher-Sensoren des HA-Exports (Stufe 3b)

Neun anlagenweite Sensoren für Automationen in Home Assistant — **Momentwerte je kWh** der laufenden Stunde, keine
Monats- oder Jahresgröße. Rechenort `api/routes/ha_export/anlage_preise_speicher.py::preise_speicher_sensoren` (eine
Phase von `calculate_anlage_sensors`; sie lädt nichts — Bezugspreis-Reihen und Wirkungsgrade je Speicher holt der
Orchestrator vorher, weil die Steuerungs-Sensoren dieselben brauchen). Die Formeln darunter liegen im Layer
(`core/berechnungen/preis_reihe.py`, `speicher_kosten.py`). `Slot` = die laufende Stunde in Backward-Konvention
(`jetzt_stunde + 1`).

```
Bezugspreis jetzt     = (1 + USt) × Börsenpreis_Slot + Aufschlag     dynamischer Tarif mit ableitbarem Aufschlag
                      = Börsenpreis_Slot                              dynamisch ohne Aufschlag (Näherung, „unvollständig")
                      = Arbeitspreis des Zeitfensters / des Tarifs    Zeitfenster / Festpreis
Einspeisevergütung    = Vergütung des Tarifs bzw. gepflegter Monatswert
Eigenverbrauch-Wert   = Bezugspreis jetzt − Einspeisevergütung        NUR bei vollständigem Bezugspreis (Flex P-5)
η Anlage              = min(η je Speicher)                            None, sobald EIN Speicher weder gemessenen noch
                                                                      gepflegten Wirkungsgrad hat (kein Vorgabewert)
Speicherstrom-Kosten  = Einspeisevergütung ÷ η Anlage                 entgangene Vergütung je entnommener kWh
Netzladekosten        = Bezugspreis jetzt ÷ η Anlage                  nur wenn ein Speicher „lädt aus dem Netz" hat
Leer um               = Ende des ersten Slots NACH dem Sim-Start mit SoC_vorher > 2 % und SoC ≤ 2 %
Reicht bis Mitternacht= kein solcher Übergang UND End-SoC (letzter Slot des Tages) > 2 %
Abregelung heute      = Σ_Stunden (Rohprognose − an der Wechselrichter-Grenze gekappt)   Skala der Rohprognose
Einspeisung unerwünscht (§51) = Börsenpreis_Stunde < 0  UND  PV-Prognose_Slot > 0
```

* **Kein Wert ⇒ kein Sensor** (ADR-002/P4): fehlt ein Eingang (Vergütung, η, Bezugspreise, SoC-Reihe, AC-Grenze,
  Börsenpreis der Stunde), entsteht der Sensor nicht — eine 0 wäre in HA eine Messung. Ausnahme in die andere Richtung:
  Abregelung **0** ist ein Wert („heute wird nichts abgeregelt").
* Die beiden Speicher-Sensoren und die Abregelung/§51 laufen auch ohne Bezugspreise; Bezugspreis, Vergütung und
  Eigenverbrauch-Wert nur mit ihnen. «Leer um» und «reicht» kommen aus **einem** Simulationslauf
  (`_leer_um_und_reicht`, Start beim zuletzt gemessenen Ladestand, V1) — «leer um» darf deshalb in der Vergangenheit
  liegen. §51 ist **nicht tarifgebunden**: es zählt die Börse, nicht der eigene Bezugspreis.
* **Abgrenzung zum Spread oben:** der Spread bewertet die **Ersparnis** einer entladenen kWh über einen Monat
  (Bezug − Vergütung bzw. Bezug − Ladepreis). Die Speicherstrom-Kosten sind der **Preis** einer entnommenen kWh jetzt
  (Vergütung ÷ η) — eine andere Größe für eine andere Frage (lohnt es, jetzt aus dem Speicher zu verbrauchen?).
* **Code-Ort je Phase (RF-51):** `_bezugspreis_jetzt` (Bezugspreis, Vergütung; Formeltext `_bezug_berechnung`) ·
  `_eigenverbrauchswert` · `_speicher_kosten` (η Anlage, Speicherstrom, Netzladen) · `_speicher_reichweite` (leer um,
  reicht bis Mitternacht) · `_abregelung_und_51`. Anwender-Wortlaut und Attribute:
  [SENSOR-REFERENZ §11](SENSOR-REFERENZ.md#11-export-sensoren-eedc--ha).

#### Welche Stunde gilt — Ladestand, Preis und Menge (N-387, 2026-09-23)

Eine Stundenzeile trägt **zwei Uhren** (SoT `core/berechnungen/slot_konvention.py`): die
`*_kw`-Spalten meinen das Intervall **vor** ihrer Stunde (`[s-1, s)`, Backward-Konvention #144),
`soc_prozent`, `strompreis_cent` und `boersenpreis_cent` dagegen das Intervall **ab** ihrer Stunde
(`[s, s+1)`) — so liefert Home Assistant sie. **Wer beide Hälften verrechnet, nimmt den
Ladestand bzw. Preis deshalb aus der Zeile davor** (über die Tagesgrenze: aus der Zeile 23 des
Vortags). Der eine Ort dafür ist `slot_konvention.forward_werte_je_backward_zeile`.

Das betrifft sichtbar:

* **Speicher-Potential** — „Überschuss bei vollem Speicher" und „Fehlmenge bei leerem Speicher" paaren den
  Ladestand der Zeile davor mit der Menge der Stunde; ohne die Umkehr läge das Fenster eine Stunde zu früh (es zählte
  die Einspeisung der Stunde **vor** dem Vollwerden und den Netzbezug der Stunde, in der er erst leerlief).
* **Effektiver Ladepreis und Entladewert** — die Netzladung einer Stunde zahlt den Preis ihrer eigenen Stunde, nicht den
  der Nachbarstunde. Bei einem **Festpreis** ändert das nichts (jede Stunde derselbe Preis); bei einem
  dynamischen Tarif ist es die volle Differenz zweier Nachbarstunden.
* **Tageskosten, Monats-Ø-Preis und Eigenverbrauchs-Ersparnis** der Flex-Kaskade
  ([KONZEPT-FLEX-TARIFE §2](KONZEPT-FLEX-TARIFE.md)) sowie der **§51-Einspeiseerlös**.
* **Die Stundenliste des Tagesdetails** (`GET /energie-profil/{id}/stunden`, N-553): Sie zeigt
  keine Rechnung, aber dieselbe Zeile — sie trägt den Ladestand zur Stunde ihrer Zeile, die Spalte „SoC" in
  *Cockpit → Tag → Stundenwerte* steht also neben dem Batteriefluss derselben Stunde.

> ⭐ **„Stand am Tagesende" ist eine andere Frage und hat deshalb eine eigene Größe** (N-553).
> Die Kachel *Ladestand* im Speicher-Block fragt „wie voll war der Speicher **zuletzt**", nicht
> „welcher Stand gehört zu dieser Stunde". Der jüngste Messwert wandert durch die Paarung aus dem
> Tagesraster (sein Intervall `[23, 24)` liegt backward schon im Folgetag), und am **laufenden**
> Tag wäre die Kachel damit eine Stunde älter geworden. Die Antwort führt ihn deshalb ungepaart
> als `soc_zuletzt_prozent` mit. **Spanne** (min/max) ist gegen die Zuordnung unempfindlich und
> kommt aus der Liste.

> ⛔ **Zwei Stellen paaren bewusst OHNE diese Umkehr, beide gemessen.**
> (1) Der **Wirkungsgrad am Periodenrand** (`speicher_wirtschaftlichkeit._lese_soc_am_periodenrand`)
> stellt SoC-Randzeilen gegen **Monatsintegrale**: Zeile 0 liegt ½ h nach dem Periodenbeginn,
> Zeile 23 ½ h vor dem Ende — symmetrisch; die Vorzeile machte daraus 1½ h und wäre schlechter.
> (2) Die **Sizing-Kalibrierung** (`speicher_sizing_service._als_sizing_stunde`) bildet eine
> *Differenz zweier Stundenmittel*, keine Paarung: sie stellt den Hub dem *Mittel der zwei angrenzenden
> Stundenmengen* gegenüber (N-552, nächster Abschnitt) — eine Verschiebung des Ladestands bräche das.

#### Wie die Sizing-Kalibrierung Kapazität und Wirkungsgrad misst (N-552, 23.09.2026)

Der *Größerer Speicher?*-Simulator braucht die **tatsächlich nutzbare** Kapazität und den
Roundtrip-Wirkungsgrad. eedc misst beides aus der Bewegung des Ladestands: Wo der Speicher in einer
Stunde deutlich lädt oder entlädt, wird der Hub des Ladestands gegen die bewegte Energie gestellt.

Beide Ladestände sind **Stundenmittel**. Ihre Differenz beschreibt deshalb den Fluss zwischen den
**Mitten** der beiden Stunden, also je zur Hälfte zwei Wanduhr-Stunden — und genau diese zwei
halben Stunden stellt eedc dem Hub gegenüber (N-552: `½ (b_s + b_{s+1})` bei heutigen Zeilen,
`½ (b_{s−1} + b_s)` bei Altbestand vor dem 04.06.2026, entschieden je Zeile an ihrer
Aggregationszeit). Läuft die eine Hälfte in die andere Richtung als die zweite, zählt der Hub nicht:
dann mischt er zwei Wirkungsgrade.

Die Formel ist an einem echten Jahr gemessen (Korrelation des Hubs 0,98 gegen 0,95 der Einzelstunde). Die
nutzbare Kapazität hängt am Median der selteneren Entladestunden und kann zwischen Zeiträumen
um einige Zehntel Kilowattstunden schwanken. Die Mindestschwelle ist 10 Prozentpunkte Hub
(`MIN_SOC_HUB_PROZENTPUNKTE`): eine höhere halbierte die Entladestunden und ließe Anlagen mit weniger Daten auf die
gepflegten Werte zurückfallen.

> ⛔ **Die Umkehr gilt nicht rückwirkend für jede gespeicherte Zeile.** Zeilen, die der HA-Stundenpfad vor dem
> **04.06.2026** aggregiert hat, tragen ihre Energiemengen *forward* beschriftet — auf ihnen ist die Paarung innerhalb
> **derselben** Zeile die richtige. eedc
> entscheidet das je Zeile an ihrer **Aggregationszeit** (`created_at`, Grenze
> `slot_konvention.SLOT_PAARUNG_VORZEILE_AB`), nicht an ihrem Datum. **Reparaturweg: neu
> aggregieren stellt einen alten Tag um** — `aggregate_day` löscht den Tag und schreibt ihn neu,
> die Zeilen tragen danach die heutige Konvention und werden auch so gepaart.

#### Brutto oder netto — wann welche Kapazität gilt

Ein Speicher trägt zwei Kapazitäten, beide im Formular. Die Trennlinie läuft **nicht** zwischen
„genau" und „ungefähr", sondern zwischen zwei Fragen:

| Frage | Kapazität | Warum | Stellen |
| --- | --- | --- | --- |
| **Wie oft wurde der Speicher umgeschlagen?** | **brutto** (`kapazitaet_kwh`) | Bezugsgröße der Hersteller-Garantie; ein Nenner, der am Pflegezustand hängt, macht dieselbe Anlage unvergleichbar | Vollzyklen (alle Sichten), graue Last, Community-Datensatz, Anzeige/Beschreibung der Komponente |
| **Wie viel Energie geht durch den Speicher?** | **netto** (`nutzbare_kapazitaet_kwh`, still auf brutto zurückfallend) | Simuliert bzw. prognostiziert wird eine *durchgefahrene Menge* — und durch den Speicher geht nur der nutzbare Hub | Tages-Vorschau „Speicher voll um …" (Planungs-Tab **und** HA-Sensor `eedc_speicher_voll_um`), Wirtschaftlichkeits-**Prognose** ohne IST-Aggregat, η-SoC-Delta |

> ⚑ **Der Wirkungsgrad gehört dazu (N-238).** Die Tages-Vorschau rechnet den Ladeweg mit Verlust — verlustfrei
> läge „Speicher voll um" systematisch **vor** der tatsächlichen Uhrzeit. Kapazität **und** Wirkungsgrad kommen aus
> **einem** Helper (`aggregiere_speicher_basis`: Kapazität summiert, Wirkungsgrad als **Minimum** —
> eine Kette ist nicht besser als ihr schwächstes Glied); der HA-Sensor und die Kachel lesen
> dieselbe Regel, statt sie zweimal zu bilden. Die Verluste sitzen ganz auf der **Ladeseite**, weil
> die übergebene Kapazität die abgabefähige Menge ist — sie zusätzlich beim Entladen anzusetzen wäre
> Doppelzählung (dieselbe Konvention wie `core/berechnungen/speicher_sizing.py`).
>
> ⚑ **Welche Geräte in den Helper gehen, entscheidet der Aufrufer — und für die beiden
> Planungs-Sichten sind es nur die HEUTE laufenden (N-546).** `Sizing` und `Speicher-Potential` nehmen die
> Investitionen vom Typ Speicher mit `aktiv` und ohne Stilllegung vor heute; ein abgelöstes Gerät höbe sonst die
> Kapazität, senkte über das **Minimum** den Wirkungsgrad und verschöbe die Leer-Schwelle (beide Summen gehen ein).
> Stichtag ist `date.today()` und nicht das Fenster-Ende: beide Sichten fragen nach vorn, wie
> der Tarif im Docstring von `speicher_sizing_service.py`.
>
> ⚠ **Die gepflegte Kapazität bleibt maßgeblich und wird NICHT durch die gemessene ersetzt**
> (Entscheid Gernot). Sie trägt eine **Absicht**: es gibt Anwender, die ihren Speicher
> bewusst nicht auf 100 % laden, und für die wäre eine Korrektur nach unten falsch — sie wollen
> wissen, wann *ihr* Ziel erreicht ist. Der Sizing-Block weist die gemessene Größe stattdessen
> **daneben** aus und trennt die zwei Ursachen einer Lücke (Ladegrenze ⟷ Ladeverlust) über den
> tatsächlich genutzten Ladestands-Bereich (`messe_soc_nutzung`).

> ⚑ **Das Netto-Feld trägt eine dritte Aussage: die Entlade-Untergrenze (#379).**
> Aus dem Verhältnis beider Kapazitäten leitet `core/berechnungen/speicher_potential.py::
> leer_schwelle_prozent` ab, ab welchem Ladestand *dieser* Speicher nichts mehr abgibt —
> `(1 − netto ÷ brutto) × 100`, bei 24 von 30 kWh also 20 %. Eine feste Schwelle verfehlt jede eigene Untergrenze:
> ein Speicher, der sie nie erreicht, liefe nie „leer", und das *Nutzbare Zusatzpotential* wäre **strukturell 0** —
> die Sicht behauptete „ein größerer Speicher hätte nichts gebracht", ohne es messen zu können.
>
> Drei Festlegungen gehören dazu, jede aus einer Messung:
>
> * **Aufschlag von 3 Prozentpunkten** (`SOC_LEER_TOLERANZ_PP`): Wechselrichter schalten mit Puffer ab, der SoC kommt
>   in ganzen Prozent, und diese Auswertung liest Stundenmittel — ohne Aufschlag träfe die Schwelle die eingestellte
>   Untergrenze knapp nicht.
> * **Deckel bei 50 %** (`SOC_LEER_MAX_PROZENT`) gegen die N-235-Klasse: „1 kWh nutzbar von 30"
>   ergäbe sonst 96,7 % und ließe den Speicher fast immer als leer gelten — die Kennzahl fiele zu
>   **hoch** aus, also in die Gegenrichtung der Deckelung.
> * **Die Reserve sitzt unten.** Bei Heimspeichern der Normalfall; die Oberseite deckt
>   `SOC_VOLL_PROZENT` ab, und eine gewollte *Lade*-Grenze erkennt `messe_soc_nutzung` an den Daten.
>   ⛔ **Die Annahme hat einen Preis:** trifft sie nicht zu, fällt die Schwelle zu hoch aus — und die Kennzahl damit
>   zu **hoch**, nicht konservativ; `berechne_zusatzpotential` zählt dann mehr Netzbezug in die Fehlmenge. Das trifft
>   jede obere Ladegrenze (Fahrweise 10/90): `nutzbare_kapazitaet_kwh` meint vertraglich den **ganzen** fahrbaren
>   SoC-Hub, wer so pflegt, pflegt korrekt und bekommt trotzdem die zu hohe Untergrenze. **Gebaut ist kein zweites
>   Feld** (Entscheid Gernot 15.08.), sondern der Hinweis auf die Annahme an beiden Anzeigen: im Speicher-Formular beim
>   Eintippen und im Block *Größerer Speicher?* (#379).
>
> ⚠ **Ohne gepflegte nutzbare Kapazität gilt die feste Schwelle 5 %** (`SOC_LEER_PROZENT`) — die abgeleitete Schwelle
> erreicht nur Anlagen mit gepflegtem Netto-Feld.
>
> ⚑ **Und die Umkehrung gehört dazu (N-254):** Ohne gepflegte nutzbare Kapazität ist „der Speicher
> wurde nie leer" **zweideutig** — er kann groß genug sein (dann hätte mehr Kapazität nichts
> gebracht) oder an einer Untergrenze hängen (dann hätte sie geholfen). Zwei Ursachen,
> **entgegengesetzte** Antworten, und eedc kann sie ohne die Pflege nicht trennen.
> `boden_nie_erreicht(soc_min, schwelle, schwelle_ist_abgeleitet)` erkennt genau diesen Zustand;
> die Sicht sagt dann „nicht beurteilbar" und die Kachel zeigt **„—" statt 0** — dieselbe Doktrin
> wie „nicht gemessen statt 0".
>
> ⚠ **Die Regel hängt an der Pflege, nicht am Abstand allein** — sonst verlöre auch der Fall seine
> Aussage, für den die Kennzahl gebaut wurde. Ist die Schwelle abgeleitet, kennt eedc die Untergrenze, und ein
> Speicher, der sie nicht erreicht, war wirklich groß genug. Wer seinen Boden real berührt, bekommt die klare
> Aussage ebenfalls.
>
> ⚠ **Die Schwelle gilt im ganzen Speicher-Hub, nicht nur in Phase 2.** `speicher_sizing.py` importiert
> `SOC_VOLL_PROZENT`/`SOC_LEER_PROZENT` aus `speicher_potential.py` — Import statt Kopie: bei einer Kopie hätte ein
> `==`-Test nie angeschlagen, solange beide Werte gleich sind.

**SoT netto (A31-2):** `core/investition_kennwerte.py::get_speicher_nutzbare_kapazitaet_kwh` —
netto, sonst brutto, sonst `None`. Der Brutto-Fallback ist **still** (Entscheidung **E17**): kein
Hinweis, keine Kennzeichnung, **kein P4-Fall**. Der Brutto-Wert ist nicht *unvollständig*, er ist die
andere gültige Lesart derselben Größe; netto wirkt deshalb nur, wo das optionale Feld gepflegt ist.
Die Leserichtung geht nur netto → brutto und
**nie** zurück — ein Brutto-Helper mit Netto-Fallback wäre genau die Verwechslung, die die Vollzyklen
wieder vom Pflegezustand abhängig machte.

**Nebenwirkung der Vorschau, die dazugehört:** dieselbe Simulation liefert auch Einspeisung,
Eigenverbrauch und Autarkie des Vorschautags (die Σ-Zeile «Netto» der Tabelle ist `netto_summe_kwh` = PV-Summe − Verbrauchssumme der
Antwort, `kennzahlen.netto_kwh` — Überschuss +, Defizit −, vor dem Speicher; seit Päckchen Z-Client, vorher im Client). Ein kleinerer Puffer nimmt weniger Überschuss auf —
mehr geht ins Netz, die Autarkie sinkt, „Speicher voll" kommt früher (in Stundenauflösung nicht an jedem Tag
sichtbar). Der **Eigenverbrauch** (Direktverbrauch + Entladung, N-635) sinkt nur, wenn der kleinere Speicher den Abend
nicht mehr trägt; trägt er ihn, bleibt er gleich.

**Woher die Kapazität kommt (SoT A31-1):** `core/investition_kennwerte.py::get_speicher_kapazitaet_kwh`
— brutto (`kapazitaet_kwh`), nur aus dem `parameter`-JSON, **ohne Default**. Ist nichts gepflegt,
liefert er `None`, und der Aufrufer entscheidet (summieren mit `or 0`, Zahl unterdrücken, Rechnung
auslassen); eine Zahl erfindet er nicht — kein stilles „10 kWh" mit Vollzyklen und Jahres-Ersparnis daraus
(Entscheidung **E16**, ADR-002/P3-a, **N127**). Der fehlende Wert wird stattdessen ausgewiesen —
Daten-Checker („Kapazität (kWh) fehlt") und die Antwort selbst (`kapazitaet_fehlt` + Hinweis, P4).

> **Abgrenzung „SoC-Hübe"** (`TagesZusammenfassung.batterie_vollzyklen` = ΣΔSoC ÷ 200): eine andere
> Kennzahl, die reale Lade-Hübe misst und damit als einzige eine 10/90-Fahrweise abbildet (ein voller
> Hub = 160 pp = 0,8). Sie ist ein Bestandsmaß, hängt an einem SoC-Sensor und ist **kein** Ersatz für
> die Vollzyklen. Sichtbar in der Energieprofil-Tagestabelle unter diesem Namen.

> eedc kennt und braucht keinen Ziel-SOC: Vollzyklen und Wirkungsgrad kommen aus **gemessenen**
> Lade-/Entlademengen. Eine Annahme steckt nur in der Wirtschaftlichkeits-**Prognose**
> (250 Vollzyklen × nutzbare Kapazität, `SPEICHER_ZYKLEN_PRO_JAHR`), die vor dem Vorliegen von
> Messdaten greift, sowie in der Tages-**Vorschau** („Speicher voll um …",
> `core/berechnungen/speicher_simulation.py`) über die nutzbare Kapazität — beide netto mit Brutto-Rückfall
> (`get_speicher_nutzbare_kapazitaet_kwh`, Tabelle oben; ADR-002 P3-a). **Die Vollzyklen bleiben bewusst brutto.**

#### Round-Trip-Wirkungsgrad (η) — SoC-korrigiert, nicht roh

**Funktion:** `services/speicher_wirtschaftlichkeit.py::berechne_ist_wirkungsgrad`
**Verwendet in:** Cockpit → Monat, Komponenten-Hub, ROI-Analyse

η ist **kein** einfacher Quotient über einen Zeitraum. Ladung und Entladung sind
*Flüsse*, der Speicher ist ein *Bestand*: Was am Periodenende im Akku steht, wird
erst danach entladen. Über eine Monatsgrenze verrutscht dadurch Energie, und der
rohe Quotient zappelt — er kann 100 % überschreiten oder zu niedrig ausfallen.

Zwei Pfade, in dieser Reihenfolge:

| Lage | Rechnung | `quelle` |
| --- | --- | --- |
| Fenster ≥ `WIRKUNGSGRAD_FENSTER_MONATE_MIN` (6) | `entladung ÷ ladung` — ΔSoC mittelt sich aus | `fenster_lang` |
| Kurzes Fenster, SoC am Rand bekannt | `(entladung + ΔSoC_kwh) ÷ ladung`, geklemmt auf 0…100 % | `soc_korrigiert` |
| Kurzes Fenster, **kein** SoC | roher Quotient, **nur wenn ≤ 100 %** | `roh-unkorrigiert` |
| sonst | kein Wert, Grund steht an der Kachel (P4) | `fenster-zu-kurz` |

> **Warum der rohe Wert nicht einfach verworfen wird:** Die meisten Anlagen haben
> keinen SoC-Sensor. Ihn zu unterdrücken hieße, für sie **dauerhaft** „—"
> anzuzeigen — P4 verlangt „sagen, was man weiß und wie sicher", nicht Schweigen.
> Deshalb wird er ausgewiesen **und gekennzeichnet**. Unterdrückt wird nur, was
> nachweislich falsch ist: über 100 % kann kein Speicher.

> **In *Cockpit → Monat*** (`aktueller_monat/komponenten.py::_speicher_detail`) wird die Funktion für den Kalendermonat
> gerufen (`fenster_monate=1`, nie das lange Fenster), nur mit Ladung **und** Entladung > 0. Liefert sie keinen Wert
> (kein SoC am Rand), steht der rohe Quotient, wenn er ≤ 100 % ist (`roh-unkorrigiert`); schlägt die Ermittlung fehl,
> gibt es **keinen** rohen Rückfall, sondern den Grund `nicht-ermittelbar`. `speicher_soc_drift_flag` heißt
> „kein belastbarer η" (F-22, Probe `test_rf47_aktueller_monat_phasen.py`).

> **Der Layer-SoT `speicher_effizienz_prozent` klemmt bewusst NICHT**
> („Diagnose statt stillem Cap"). Die Diagnose ist der Daten-Checker: meldet ein
> Speicher **kumulativ** mehr Entladung als Ladung, ist das kein Carry-over mehr,
> sondern ein Erfassungsfehler — meist `ladung_kwh` als reine PV-Ladung gepflegt
> (#281). `ladung_netz_kwh` ⊆ `ladung_kwh` ist Vertrag, kein zweiter Posten.

**Speicher-Bilanz (Päckchen BB, 9.11.2026)** — Layer `core/berechnungen/speicher_bilanz.py`; bis dahin rechnete der Client sie
an acht Stellen. Die Antworten tragen das Ergebnis als Feld, der Client zeigt:

| Größe | Formel | Feld (Antwort) |
| --- | --- | --- |
| Bilanz | Entladung − Ladung (negativ ist der Normalfall) | `speicher_bilanz_kwh` — *Cockpit → Monat/Jahr* (`computed_field` an `AktuellerMonatResponse`: Monat, Jahr-Kopf, Jahr-Monate), *Cockpit → Tag* (`tag-detail`) |
| Wirkungsverluste € | Verlust × PV-Anteil × Einspeisepreis ÷ 100 + Verlust × Netz-Anteil × Bezugspreis ÷ 100; nur bei Ladung > Entladung und mit Einspeise- oder Tarif-Bezugspreis; Bezugspreis = Ø-Bezugspreis des Monats, sonst Tarif (am Tag: Preis des Tages); Netz-Anteil = Netzladung ÷ Ladung, auf 1 gekappt (`speicher_netzladung_anteil_gekappt`, N-444/K2) | `speicher_wirkungsverluste_euro` mit den Teilen `speicher_verlust_pv_kwh` / `speicher_verlust_netz_kwh`, `speicher_netzladung_anteil_prozent` — dieselben Antworten |
| Verlust | Ladung − Entladung, nie < 0 | `speicher_verlust_kwh` (Monat/Jahr), `jahresbilanz[].verlust_kwh` (Speicher-Hub, Σ der `monatsreihe` je Jahr) |
| Verlust (Hub-Kachel) | Ladung − Entladung **ungeklemmt** aus den gerundeten Summen (bei vertauschten Zählern negativ, daneben der Hinweis «Durchsatz inkonsistent») | `dashboard/speicher.zusammenfassung.verlust_kwh` |
| PV-Ladung (Hub) | Ladung − Netzladung | `zusammenfassung.pv_ladung_kwh` (die Monatsreihe klemmt je Monat auf 0) |
| Netzladung-Kosten (Hub) | Netzladung × Ø-Ladepreis ÷ 100 (`effektiver_ladepreis_cent`, sonst `arbitrage_avg_preis_cent`; ohne Preis kein Wert) | `zusammenfassung.netzladung_kosten_euro` (Layer `speicher_wirtschaftlichkeit.netzladung_kosten_euro`) |
| Solar-Anteil der Ladung | max(0, Ladung − Netzladung) ÷ Ladung × 100; ohne erfasste Netzladung kein Wert (P4) | `speicher_solaranteil_prozent` — Speicher-Tabelle in *Cockpit → Jahr*; die Fußzeile liest den Jahr-Kopf und zeigt «—», solange im Jahr keine Netzladung über 0 erfasst ist |

Am Tag kommen Ladung und Entladung aus der Tag-Zeile von `tage-werte` (`baue_tage_werte` für genau diesen Tag, Phase
`tag.py::_speicher_und_soll`) — dieselbe Zeile, die die Sicht anzeigt. Proben: `test_bb_speicher_tag_felder.py` (Layer bitgleich
zur früheren Client-Formel), Vitest `bbSpeicherBackendFelder.test.tsx`.

### 3.4 E-Auto-Einsparung

**Funktion:** `berechne_eauto_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`GET /api/investitionen/roi/{anlage_id}`, Paket `api/routes/investitionen/`; Aufruf in
`roi_standalone.py::_eauto_bewertung`)

#### Eingabefelder

Die Monats-Messgrößen des E-Autos (Kilometer, Ladung, Fahrverbrauch, V2H) stehen in der
[Übersicht der Größen §1](UEBERSICHT-GROESSEN.md#1-eingabefelder) und in der
[Sensor-Referenz §5](SENSOR-REFERENZ.md#5-e-auto); Kilometer, V2H und Ladevorgänge des Monats stehen unten. Diese
Prognose liest die Investitions-Parameter (`core/investition_parameter.py`, `PARAM_E_AUTO_DEFAULTS`):

| Feld | Quelle |
|------|--------|
| `jahresfahrleistung_km` | `Investition.parameter` (Default: 15000) |
| `verbrauch_kwh_100km` | `Investition.parameter` (Default: 18) |
| `pv_ladeanteil_prozent` | `Investition.parameter` (Default: 60) — im Formular **nicht vorbelegt** (N-572): ein geleertes Feld bleibt leer, dann gilt der gemessene IST-Anteil, ohne Messung 60 (s. N-188 unten) |
| `benzinpreis_euro` | `Investition.parameter` (Default: 1,65) — im Formular **nicht vorbelegt** (N-572): ein geleertes Feld bleibt leer, dann gilt der Kraftstoffpreis der Monatsdaten, ohne ihn 1,65 |
| `vergleich_verbrauch_l_100km` | `Investition.parameter` (Default: 7,5) — der **fiktive** Vergleichs-Benziner |
| `v2h_faehig` | `Investition.parameter` (Default: false) |
| `v2h_entladung_kwh_jahr` | `Investition.parameter` — ohne Wert rechnet die ROI-Prognose mit 0 (`roi_standalone.py::_eauto_bewertung`) |
| `v2h_entlade_preis_cent` | `Investition.parameter` — **kein Default**; der Override zu `V2H_Preis` (Formeln unten) |
| `eigener_verbrauch_l_100km` | `Investition.parameter` — **kein Default**, s. „Plug-in-Hybrid" unten |
| `elektrischer_fahranteil_prozent` | `Investition.parameter` — **kein Default** |

> Die Altnamen `km_jahr`, `pv_anteil_prozent`, `benzin_verbrauch_liter_100km` und `nutzt_v2h` übersetzt
> `LEGACY_PARAM_KEYS` in `core/investition_parameter.py` auf die Schlüssel der Tabelle.

#### Formeln

```
km_elektrisch        = jahresfahrleistung_km                    (BEV — Normalfall)
                     = jahresfahrleistung_km * Fahranteil / 100 (Plug-in-Hybrid, s. u.)
km_verbrenner        = jahresfahrleistung_km - km_elektrisch

Strom_Bedarf         = km_elektrisch * Verbrauch_kWh_100km / 100
PV_Anteil            = pv_ladeanteil_prozent / 100
Netz_Anteil          = 1 - PV_Anteil

Strom_Kosten         = Strom_Bedarf * Netz_Anteil * Strompreis / 100
                     + Strom_Bedarf * PV_Anteil   * EV_Preis   / 100   ← N-672: PV-Ladung ist nicht kostenlos
                       (EV_Preis = der Strompreis, mit dem die ROI-Prognose den Eigenverbrauch bewertet)
Benzin_Verbrauch     = jahresfahrleistung_km * Vergleich_L_100km / 100   ← ALLE Kilometer
Benzin_Kosten        = Benzin_Verbrauch * Benzinpreis_EUR
Fossile_Kosten       = km_verbrenner / 100 * Eigener_L_100km * Benzinpreis_EUR

V2H_Einsparung       = V2H_Entladung_kWh * V2H_Preis / 100    (wenn V2H aktiv)
    V2H_Preis        = v2h_entlade_preis_cent                 (Override, optional)
                     = Bezugspreis - Einspeisevergütung       (Normalfall, aus den gepflegten Tarifen)

Jahres-Einsparung    = Benzin_Kosten - Strom_Kosten - Fossile_Kosten + V2H_Einsparung

CO2_Verbrenner       = Benzin_Verbrauch * 2.37
CO2_E-Auto           = Strom_Bedarf * 0.38        ← N-672: die GANZE Ladung (die PV-CO₂ schreibt den Eigenverbrauch schon gut)
CO2_Fossil           = km_verbrenner / 100 * Eigener_L_100km * 2.37
CO2-Einsparung       = CO2_Verbrenner - CO2_E-Auto - CO2_Fossil
```

#### Kilometer, V2H und Ladevorgänge des Monats

Die IST-Achse liest diese Mengen aus den Monats-Fakten (`EmobFakten`, ohne Dienstwagen):

- **Kilometer** (`EmobFakten.km`): Σ `km_gefahren` der E-Auto-Zeilen des Monats (`monats_fakten/roh.py::_RohMonat._falte_emob`).
  Ein Dienstwagen (`ist_dienstlich`) zählt nicht mit — seine Zeile geht in den dienstlichen Zweig (`dienstlich_je_inv`, F-7).
  `EmobFakten.km_je_fahrzeug` ist dieselbe Summe je Fahrzeug (`Investition.id`, nur Zeilen mit km): die Ersparnis je
  Fahrzeug rechnet mit dessen Verbrauchs-Parametern (G20-2). Der HA-Sensor `e_auto_km_gesamt` eines Fahrzeugs summiert
  `km_gefahren` seiner Monatszeilen über die Monate, in denen es aktiv ist (`ha_export/investition_sensoren.py::_emob_summen`).
- **V2H-Entladung** (`EmobFakten.v2h_entladung_kwh`): Σ `v2h_entladung_kwh` der E-Auto-Zeilen ohne Dienstwagen — die
  V2H eines Dienstwagens ist keine eigene Bilanz.
- **Ladevorgänge** (`EmobFakten.ladevorgaenge`): das **Maximum** aus der Summe der privaten Wallbox-Zeilen und der Summe
  der privaten E-Auto-Zeilen (`services/emob_heimladung_phasen.py::_topf_des_monats`, Topf der einen Funktion
  `entscheide_emob_heimladung`), nicht die Summe beider — dieselbe Ladung, an Wallbox und Auto gezählt, wäre sonst doppelt.

Die Werte-Tabelle zeigt beide Zählgrößen im Monat aus diesen Fakten (`monatsdaten_aggregiert.py`: `eauto_km` in
`_zeile_komponenten`, `emob_ladevorgaenge` in `_zeile_emob_zusatz`, dort 0 ⇒ leer); am Tag summiert sie über die privaten,
am Tag aktiven Geräte (`energie_profil/tage_werte_zusatz.py::_emob`): Kilometer aus der Fahrt der E-Autos, Ladevorgänge
als Wechsel des Ladezustands der Wallboxen nach „lädt".

#### Plug-in-Hybrid: elektrischer und fossiler Anteil (ab #331)

Ein Plug-in-Hybrid fährt einen Teil seiner Kilometer mit Kraftstoff; als **100 % elektrisch** gerechnet fielen
Ersparnis und CO₂-Bilanz zu gut aus.

**Es gibt keinen Fahrzeugtyp und keinen Schalter: das gepflegte Feld ist die Aussage.**
Ist `eigener_verbrauch_l_100km` gesetzt, hat das Fahrzeug einen Verbrenner; ist es leer,
rechnet eedc das Fahrzeug als reines Elektroauto.

Wie der elektrische Anteil bestimmt wird (SoT `core/berechnungen/phev_anteil.py`,
dieselbe Funktion für IST **und** Prognose):

| Weg | Bedingung | Rechnung |
| --- | --- | --- |
| **gemessen** | monatlicher Fahrverbrauch (kWh) erfasst | `km_elektrisch = min(km_gefahren, Fahrverbrauch / Verbrauch_kWh_100km × 100)` |
| **geschätzt** | nur `elektrischer_fahranteil_prozent` gepflegt | `km_elektrisch = km_gefahren × Anteil / 100` |
| **unbestimmt** | keines von beiden | `km_elektrisch = km_gefahren` (wie ein reines Elektroauto) — der Daten-Checker meldet es |

> ⚠ **Die Deckelung auf die gefahrenen Kilometer ist nicht kosmetisch.** Ist der
> Kennwert zu niedrig gepflegt oder der Zähler zu großzügig, käme rechnerisch mehr
> elektrische Strecke heraus als gefahren wurde — und damit negative Verbrenner-Kilometer,
> also eine Ersparnis größer als die Wahrheit.

**Zwei Verbräuche, zwei Bedeutungen:** `vergleich_verbrauch_l_100km` beschreibt
den **fiktiven** Vergleichs-Benziner, und die Frage „was hätte ein Benziner gekostet"
bleibt über **alle** Kilometer gestellt — sonst verglichen wir ein Auto mit einem halben.
`eigener_verbrauch_l_100km` ist der **real getankte** Verbrauch und erzeugt eine eigene
Kostenposition daneben. Die geladene Energie wird **nicht** zusätzlich skaliert: sie ist
im IST gemessen, ein Hybrid lädt ohnehin weniger.

#### Dynamischer Kraftstoffpreis (ab v3.17.0)

In der **Finanz-Prognose** ([Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen), Backend `aussichten/finanz_rueckblick.py`) wird die E-Auto-Ersparnis **pro Monat** mit dem echten Kraftstoffpreis berechnet:

```
Für jeden historischen Monat:
  Benzinpreis = Monatsdaten.kraftstoffpreis_euro       (wenn vorhanden)
              ∨ Investition.parameter.benzinpreis_euro  (Fallback statisch)
  Benzin_Kosten_Monat = km_gefahren / 100 * Vergleich_L_100km * Benzinpreis
  Strom_Kosten_Monat  = ladung_netz_kwh * Netzbezug_Preis / 100   # kanonische Heimladungs-Quelle (Wallbox bzw. E-Auto), s. §3.2
                      + ladung_pv_kwh   * EV_Preis        / 100   # N-672: Preis der Eigenverbrauchs-Ersparnis des Monats

Für Jahresprognose (aussichten/finanz_prognose.py):
  Prognose_Benzinpreis = Ø(Monatsdaten.kraftstoffpreis_euro)  (historischer Durchschnitt)
                       ∨ Investition.parameter.benzinpreis_euro  (Fallback)
```

In der **ROI-Sicht** ([Auswertungen → ROI](HANDBUCH_BEDIENUNG.md#42-roi)) rechnet die E-Auto-Zeile mit **einem**
Preis für die Jahres-Prognose, aufgelöst in dieser Rangfolge (`services/eauto_wirtschaftlichkeit.py::resolve_eauto_benzinpreis`,
die Quelle steht im Detail als `benzinpreis_quelle`):

```
Benzinpreis_ROI = Query benzinpreis_euro (Slider)                         → "slider"
                ∨ Investition.parameter.benzinpreis_euro (gepflegt)        → "parameter"
                ∨ letzter Monatsdaten.kraftstoffpreis_euro der Anlage     → "monatsdaten"
                ∨ 1,65 €/L                                                → "default"
```

Die Antwort nennt daneben `benzinpreis_hinweis_euro` = letzter Monatspreis; fehlt er, 1,65 €/L
(`roi_eingaenge.py::_kraftstoffpreise`).

**Datenquelle:** EU Weekly Oil Bulletin (Euro-Super 95, inkl. Steuern, wöchentlich, History seit 2005). Befüllung durch den Scheduler-Job (**täglich 06:00 + Startlauf**), den Reparatur-Pfad „Kraftstoffpreise nachpflegen" oder den Backfill-Endpoint. Fehlt der Monatswert, rechnet die Kette mit dem Investitions-Parameter bzw. 1,65 €/L weiter — der Daten-Checker meldet offene Monate deshalb als eigene Kategorie. Das Feld *Benzinpreis (€/L)* am E-Auto ist nicht vorbelegt (N-572): ein geleertes Feld bleibt beim nächsten Speichern leer, und es gilt der Monatspreis bzw. 1,65 €/L. Wer dort eine Zahl einträgt, legt den Preis fest — in der ROI-Sicht (`resolve_eauto_benzinpreis`) hat sie Vorrang vor dem jüngsten Monatspreis.

**Leser des Monatspreises:** Aussichten (`aussichten/finanz_rueckblick.py`, `finanz_prognose.py`, `finanz_eingaenge.py`), Cockpit
(`cockpit/uebersicht.py`, #260; *Cockpit → Monat* `aktueller_monat/finanzen.py`), Komponenten-Hub (`investitionen/dashboard_eauto.py`), HA-Sensor-Export
(`ha_export/anlage_komponenten.py`, `investition_sensoren.py`), ROI (Rangfolge oben, `investitionen/roi_eingaenge.py`) und
über das ROI-Dashboard der PDF-Finanzbericht (`services/pdf/builders/finanzbericht.py`).

#### PV-Anteil der Heimladung: gemessen, sonst abgeleitet (ab 2026-08-08, N-141)

Die Formeln oben beschreiben die **Prognose**-Achse, die den von Hand gepflegten
`pv_ladeanteil_prozent` liest — und, wo er fehlt oder leer ist, den IST-Anteil (N-188, unten;
das Formularfeld ist nicht vorbelegt, N-572).
Auf der **IST**-Achse gibt es diesen Parameter nicht — dort steht
je Monat das erfasste Paar `ladung_pv_kwh` / `ladung_netz_kwh`. **Eine Wallbox misst ihren PV-Anteil meist nicht**,
sie zählt nur Kilowattstunden; ohne Messung (evcc, eigener Zähler) leitet eedc den Anteil ab, statt die gesamte
Heimladung als Netzstrom zu zählen.

**Reihenfolge (SoT `core/berechnungen/pv_anteil_ladung.py`):**

1. **Ein erfasster Wert gewinnt immer** — auch eine gepflegte **0**. Geprüft wird die Anwesenheit
   des Schlüssels `ladung_pv_kwh`, nicht seine Größe: „diesen Monat kam nichts aus der Sonne" ist
   eine Aussage, keine Lücke.
2. **Sonst leitet eedc den Anteil aus den eigenen Stundenwerten ab**, Regel **Einspeise-Deckung**:

   ```
   je Stunde:  ungedeckt = max(0, Ladung − Netzbezug)          (N-569)
               PV        = min(Ladung, ungedeckt + Einspeisung)
               Netz      = Ladung − PV
               davon aus dem Speicher = min(Speicherentladung, PV)   (nur Ausweis)
   ```
   Der Speicheranteil rechnet mit dem **Stunden-Netto** der Batterie (Entladung − Ladung derselben Stunde): lädt und entlädt der
   Speicher in einer Stunde, untertreibt er; der PV-Anteil ist davon unberührt.

   Der zweite Summand fängt die Unschärfe der Stundenmittelung auf: Was in derselben Stunde
   eingespeist wurde, hätte stattdessen laden können. **Die Speicherentladung zählt zur PV-Deckung**
   (N-569): der PV-Anteil sagt, wie viel der Ladung nicht aus dem Netz kam,
   und gespeicherter Eigenstrom ist Eigenstrom. „Davon aus dem Speicher" ist eine **Teilmenge** des
   PV-Anteils (PV = Direkt + Speicher), gezeigt als Unterzeile im E-Auto-Hub; ohne Speicherzähler gibt
   es sie nicht, und keine Kosten-, Ersparnis-, CO₂- oder Community-Rechnung liest sie.
3. **Angewandt wird der Anteil, nicht die Kilowattstunde.** Der abgeleitete Prozentsatz geht auf
   die kanonische Monatsladung — nur so bleibt `Ladung == PV + Netz` exakt geschlossen, auch wenn
   die Tagesspur eine andere Menge kennt als die Monatszeile.

**Wo die Regel angewandt wird — eine Schicht unter dem Pool** (`services/emob_ladeanteil.py`, Fund **F-16**): die
Monatszeilen werden angereichert, **bevor** irgendjemand sie zu einer Heimladung poolt. Läge die Ableitung *über*
`get_emob_heimladung_canonical`, träfe sie nur die Felder `EmobFakten.ladung_pv_kwh`/`ladung_netz_kwh` — jede Sicht,
die die mitgereichten Rohzeilen selbst poolt (Cockpit → Jahr, Jahresbericht-PDF) oder `InvestitionMonatsdaten` direkt
liest (Komponenten-Hub, Aussichten, HA-Export), zeigte daneben 0 %. Sichten der zweiten Gruppe
holen dieselbe Anreicherung über `reichere_monatszeilen_an`.

**Zwei Ausnahmen, beide bewusst:**

- Der **Community-Payload** liest `eauto_summe_gemessen`/`wallbox_summe_gemessen` — der Server hat
  die Rohdaten nie gesehen und rechnet nichts nach; eine Schätzung wäre in einem Benchmark nicht
  mehr als solche erkennbar (dieselbe Linie wie beim BKW-Eigenverbrauch).
- **Schreib-, Import- und Checker-Pfade** bleiben außen vor. Die Anreicherung geschieht zur
  **Lesezeit** auf Kopien; programmatisch in `verbrauch_daten` zu schreiben bleibt verboten.

**Die Prognose-Achse rechnet mit derselben Zahl** (N-188): fehlt am Fahrzeug der
gepflegte `pv_ladeanteil_prozent`, nimmt die ROI-Prognose den IST-Anteil über
`monats_fakten.ist_pv_ladeanteil_prozent` (Σ PV ÷ Σ Ladung, ladungsgewichtet); der Vorgabewert 60 % greift nur,
wenn auch das IST keine Heimladung kennt. **Das Formular belegt das Feld nicht mit 60 vor** (N-572): ein geleertes Feld
bleibt beim nächsten Speichern leer, und es gilt der IST-Anteil. Eine gespeicherte 60 bleibt stehen — eedc kann sie
nicht von einer Eingabe unterscheiden; wer den gemessenen Anteil will, leert das Feld. Die
zweite Prognose-Quelle (`aussichten/finanz_prognose.py`, leitet ihre Quote aus der Historie ab) zieht über dieselbe
Anreicherung mit.

**Herkunft:** `EmobFakten.ladung_anteil_abgeleitet` sagt, ob die Aufteilung gerechnet ist; auf der
Tagesebene trägt `source_provenance` die Marke `einspeise_deckung` bzw.
`einspeise_deckung_teilweise` (letztere, wenn nicht jede Ladestunde auswertbar war — dann ist der
Wert eine Teilsumme, P4).

**Gegen evcc vermessen:** die Einspeise-Deckung lag näher an evccs PV-Anteil als die netzbasierte Regel
`min(Ladung, Netzbezug)` und „Netz + Speicherentladung"; ohne Speicherabzug (N-569) trifft sie evcc in der Nachmessung
auf rund einen Prozentpunkt, mit Abzug lag sie deutlich darunter — im Sommer lädt das Auto oft aus dem Hausakku.

⚠ **Keine rückwirkende Berechnung.** Der Wert entsteht beim Aggregieren eines Tages; Tage, die ohne diese Ableitung
aggregiert wurden, tragen `NULL`, und `NULL` heißt „keine Aussage", nicht „keine Sonne".

> **E-Mobilität und Sonstiges aus Zeitraum-Differenzen (HA-Bauform E4c).** Mit Home Assistant (bzw.
> der eigenen Summe aus MQTT) führt eedc die Aufteilung der Heimladung als **abgeleiteten Kanal** je Gerät:
> `abgeleitet:inv:<id>:ladung_pv_kwh` (`services/kanal/abgeleitet.py`). Der Stundenlauf schreibt ihn nach dem Spiegel
> fort — je Stunde dieselbe Regel wie oben (`pv_anteil_ladung.pv_der_stunde`, Einspeise-Deckung) auf die Δ der Stunde:
> `L` = Σ Ladung der Wallbox-Achse (Auswahl des Tagespfads, also mit Wallbox-Regel und Heimlade-Kaskade),
> `PV = pv_der_stunde(L, Netzbezug, Einspeisung)`, je Gerät **ohne** gemessene Aufteilung `Ladung_Gerät × PV / L`. Ein
> Gerät mit eigenem „Heim: PV"/„Heim: Netz"-Zähler bekommt keinen Kanal (der gepflegte bzw. gemessene Wert gewinnt).
> Ein Zeitraum — Tag, Monat, Kalendermonat — nennt seinen Anteil damit als **ein Δ**: `Σ Δ abgeleitet / Σ Δ Ladung`.
>
> * **Derselbe Anteil mit und ohne Abschluss** (N-631): deckt die E-Mob-Gruppe den Monat, nehmen die Monats-Fakten,
>   *Cockpit → Monat* und die Sichten außerhalb der Fakten (`lade_abgeleitete_ladeanteile`: Komponenten-Hub, Aussichten,
>   HA-Export) diesen Anteil; sonst die Quote der Tagesebene. Angewandt wird er auf die Ladung der
>   Zeilen ohne eigene Aufteilung (Punkt 3).
> * **Die Lademengen eines Monats ohne Abschluss** kommen aus den Kanälen der E-Mob-Gruppe (je Gerät jedes Energiefeld
>   mit Zähler — die Felder, die ein Abschluss schriebe) und laufen durch dieselbe Faltung und dieselbe eine Funktion wie
>   eine gespeicherte Monatszeile: Wallbox-Regel, Pool, Rest nach km, Dienstwagen getrennt. Ein Monat mit Zeile behält
>   sie (gespeichert schlägt gerechnet).
> * **Quellenwahl je Monat und Gruppe**, getrennt von der Bilanz-Gruppe: `kanal` nur, wenn jeder Kanal der Gruppe
>   (auch der abgeleitete) den Monat voll deckt — sonst rechnet der Monat aus Zeilen und Tagesebene.
> * **Grenze — eine Stunde ohne Aussage** (fehlende Netzbezugs- oder Einspeisezeile, Zählerlücke über mehr als eine
>   Stunde) trägt im Kanal keinen PV-Teil — ihre Ladung zählt im Anteil zum Netz. Die Tagesebene lässt eine solche Stunde
>   ganz aus (Entscheid: so belassen; die Abweichung irrt zur kleineren Ersparnis).
> * **Rückwirkung nur für den laufenden Monat:** ein neuer Kanal beginnt beim ersten Lauf mit dem laufenden Monat
>   (`aufbaubar_ab` eine Stunde vor dem Monatsfenster), sobald der Spiegel die Stunden trägt; kein abgeschlossener Monat
>   wird aus ihm neu gerechnet. Korrigiert der Konsistenzlauf den Spiegel, wird der Kanal ab der korrigierten Stunde neu
>   geschrieben, nie davor.
> * **„Davon aus dem Speicher"** (Ausweis) und die **Ladeblöcke je Auto** bleiben bei der Tagesebene.
>
> **Sonstiges** genauso: die Verbraucher (und die Abgabe an Dritte) eines Monats ohne Abschluss aus ihrer Gruppe — je
> Gerät die Energiefelder in der Reihenfolge seiner Kategorie, der erste mit voller Deckung trägt (Entweder-oder) —, die
> **Erzeuger hinter dem Zähler** aus dem Kanal-Monat der Bilanz-Gruppe (§3.1). Damit rechnen Eigenverbrauch, Autarkie
> und „Erzeugung hinter dem Zähler" eines Monats ohne Abschluss mit dem BHKW, wie nach dem Abschluss.

⚠ **Die Auflösung begrenzt die Genauigkeit.** Meldet ein Wallbox-Zähler nur ganze Kilowattstunden, trifft keine
Rechnung die einzelne Stunde — über den Monat ist die Ableitung brauchbar, über die Stunde nicht.

**Werte-Tabelle (Spalte «Wallbox PV-Anteil», Monat):** `wallbox_pv_anteil_prozent` der Zeile von `GET /monatsdaten/aggregiert` =
`wallbox_ladung_pv_kwh ÷ wallbox_ladung_kwh × 100` auf den zwei (auf 0,1 kWh gerundeten) Feldern der Zeile, über
`pv_anteil_prozent` ungerundet — die Tabelle rundet auf eine Stelle und mittelt über Jahre (`aggregation: 'avg'`). Seit Päckchen Z-Client.

#### Welcher Strompreis die Ladung bewertet (F-18 · ADR-002/P8)

Die Netzladung eines E-Autos wird mit dem Tarif bewertet, der **im jeweiligen Monat galt** — nicht
mit dem heutigen. SoT ist `services/eauto_wirtschaftlichkeit.aufgeloester_strompreis_cent`, gerufen
aus `berechne_eauto_ersparnis_periode`.

Cockpit → Jahr, HA-Export (Anlagen- und Fahrzeug-Sensoren), Komponenten-Hub und Auswertungen → Aussichten lösen diese
eine Größe nicht selbst auf, sondern über diese Funktion — Monats-Wallbox-Tarif inkl. Flex-Ø, nie der heutige Tarif und
nie der allgemeine statt eines eigenen Wallbox-Tarifs (F-18).

**Gewichtet wird nach der Netzladung je Monat**, nicht nach Kilometern: der Preis bepreist
Kilowattstunden. Nur wo eine Monatsaufteilung der Netzladung nicht existiert — bei reinem PV-Laden
— fällt die Mittelung auf die km zurück, den Schlüssel, nach dem der Wallbox-Pool ohnehin
attribuiert.

> **Der Monatspreis der Netzladung kommt aus den Monats-Fakten** (`TarifFakten.wallbox_preis_effektiv_cent`, in allen
> Sichten einschließlich Fahrzeug-Sensor, N-712/N-717): gepflegter Monats-Ø → gemessener Ø → Zeitfenster →
> Arbeitspreis — **Zeitfenster und Arbeitspreis vom Tarif derselben Verwendung** (eigener Wallbox-Tarif, sonst der
> allgemeine; N-717: nie die HT/NT-Fenster des allgemeinen Tarifs für einen eigenen Wallbox-Tarif). N-433: der
> Komponenten-Tarif ist Stufe 4 und geht nicht verloren.

> ⚠ **Ein einziger Tarif bleibt ein einziger Preis.** Der mengengewichtete Ø eines
> einzigen Tarifs *ist* dieser Tarif.

> ⚠ **Der P8-Wächter deckt diese Fläche nicht ab.** Alle vier beteiligten Dateien stehen in
> `P8_BASELINE_AUSNAHMEN`, weil sie den heutigen Tarif für die Hochrechnung nach vorn auch
> brauchen. Gesichert wird die Preisachse deshalb durch einen eigenen Wächter
> (`test_wurzelmuster_konformitaet.py::test_p8_emob_ersparnis_bekommt_die_monatspreise`, baumweit)
> und den Sichten-Vergleich `test_emob_preisachse_sichten_symmetrie.py`.

#### Wo die Wallbox die Quelle ist (F-14 · N-196)

Trägt eine Wallbox die Ladeenergie, ist **sie** die Quelle — auch ohne gesetzte Zuordnung
(`parent_investition_id`). Die Regel gilt in allen drei Pfaden: Monatsebene
`eauto_wirtschaftlichkeit.entscheide_emob_heimladung` (die eine Funktion, N-555; Kurzform `get_emob_heimladung_canonical`),
Tages-**Leistungs**pfad `services/live_sensor_config.py::emob_auto_verdraengt` (#356; HA- und MQTT-Weg, N-779),
Tages-**Zähler**pfad `snapshot/komponenten_beitraege.wallbox_deckt_ladung_ab` — sonst stünde ein E-Auto mit eigenem
kWh-Zähler **ohne** Parent mit demselben Ladevorgang zweimal im Tagesverlauf. Tage, die vor der Regel gespeichert
wurden, meldet der Daten-Checker (Kategorie `emob_doppelzaehlung_tage`) und bietet „Zeitraum neu aggregieren" an.
**Bewusst kein Start-Migrationslauf:** die Heilung überschreibt Messwerte und bleibt eine Entscheidung des
Anwenders.

**Auch in der Live-Bilanz bucht die Wallbox (Cockpit → Live, N-575).** Ist eine Wallbox erfasst,
ist die Heimladung eines E-Autos Gesamtverbrauch — auch beim V2H-fähigen Auto, nie Batterie-Ladung.
Liefert die Wallbox einen Wert, bucht sie, und das Auto steht nur als ihr Kind daneben; liefert sie
gerade keinen, zählt das Auto selbst als Verbraucher. Eine gemessene V2H-**Entladung** zählt wie
eine Speicher-Entladung zum Eigenverbrauch, und zwar einmal: Meldet die Wallbox den negativen Wert,
ist **sie** die Quelle und das Auto zeigt nur seine Richtung; misst nur das Auto, bucht das Auto.
Ohne erfasste Wallbox bleibt das V2H-Auto ein Speicher am Hausanschluss (F-69). Vorzeichentreu
liest eedc die Wallbox nur, wenn ein V2H-fähiges Auto erfasst ist — sonst den Betrag. Ein
invertiert angeschlossener Wallbox-Sensor im V2H-Haushalt gehört deshalb über „Vorzeichen umkehren
(⇅)" an seiner Datenquelle korrigiert. Ort: `services/live_komponenten_builder.py`, Proben
`test_n575_v2h_hinter_wallbox.py`.

### 3.5 Wärmepumpe-Einsparung

**Funktion:** `berechne_waermepumpe_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`GET /api/investitionen/roi/{anlage_id}`, Paket `api/routes/investitionen/`; Aufruf in
`roi_standalone.py::_wp_bewertung`)

> #### Die Strommenge eines Geräts — **der Gesamtzähler ist die Menge** (K1/K3)
>
> **SoT:** `core/field_definitions/wp_strom.py::wp_strom_aufteilung`; die Lesetür für die reine Menge heißt
> weiterhin `get_wp_strom_kwh`. Jede Sicht, die einen WP-Stromverbrauch auswertet, bekommt ihn von
> dort — Monats-Fakten, Komponenten-Hub, Cockpit, HA-Export, Community-Payload, Alternativkosten,
> Daten-Checker und der laufende Monat aus Nicht-DB-Quellen.
>
> ```
> Menge_kWh = stromverbrauch_kwh                          , wenn gepflegt          (K1)
>           = Strom Heizen + Strom Warmwasser
>             + gemessene funktionsfremde Teilmengen       , sonst — oder wenn der
>                                                           Gesamtzähler darunter liegt
> Rest_kWh  = Menge − (Strom Heizen + Strom Warmwasser + gemessene Teilmengen) ≥ 0
> ```
>
> Der **Rest** heißt *nicht aufgeteilt* (K5) und steht als `WpFakten.strom_nicht_aufgeteilt_kwh`
> neben der Menge: Standby, Steuerung, Umwälzpumpen. ⚠ **Nicht zu verwechseln mit**
> `modus_nicht_aufgeteilt_kwh` — das ist der Rest der **Betriebsart**-Aufteilung (Stunden ohne
> Modus-Signal). Zwei Aufteilungen derselben Menge, zwei Reste, nie addiert.
>
> **Die Toleranz steht an einer Stelle** (`wp_strom_toleranz_kwh`): 1 % der Summe, mindestens
> 0,5 kWh im Monat bzw. 0,05 kWh im Tag. Liegt der Gesamtzähler weiter darunter, tragen die Achsen
> und der Daten-Checker meldet den Widerspruch.
>
> **Was der Daten-Checker aus derselben Auflösung fragt** (`services/daten_checker/monatsdaten.py`,
> Phasen von `MonatsdatenChecks._check_wp_monatsdaten`, RF-50):
>
> ```
> Widerspruch   (Warnung) : gesamtzaehler_zu_klein                         — Toleranz wie oben
> Rest-Frage    (INFO)    : Rest_kWh > 0,25 × Menge_kWh, nur wenn Σ Achsen > 0  (_REST_AUFFAELLIG_ANTEIL;
>                                                                            genau 25 % fragt nicht)
> Modus-Teilmengen (Warnung): Σ modus_strom_* > get_wp_strom_kwh + 0,5 kWh (#263 K-2)
> Wärme-Teile   (Warnung) : Heizwärme (D1-Weiche) + Warmwasser-Wärme > waerme_kwh + 0,5 kWh (N-391)
> Wärme 0 neben Achsen (Warnung): waerme_kwh = 0 (gemessen) und Heizwärme (D1-Weiche) + Warmwasser-Wärme > 0,5 kWh
> ```
>
> Die Rest-Frage ist **kein Fehler** — Standby, Steuerung und Umwälzpumpen laufen auf keiner Achse;
> ein Viertel trennt „Systemverbrauch" von „da hängt vermutlich noch etwas anderes am Zähler". Eine
> Zeile, deren Achsen nichts tragen (nur Gesamtzähler, oder nur eine gemessene 0), hat keine
> Aufteilung und deshalb keine Frage. **Fehlende Monate je Messmodus** (`_wp_fehlende_monate`): ohne
> getrennte Strommessung fehlt `stromverbrauch_kwh`; mit getrennter Strommessung fehlen beide Achsen
> ⇒ **eine** Meldung („Strom Heizen/Warmwasser", an einer Klimaanlage ohne Warmwasser-Seite „Strom
> Heizen"), fehlt nur **eine** Achse ⇒ je Seite eine Meldung, aber nur, wenn die Wärme dieser Seite
> erfasst ist (sonst zählte jede reine Heiz-Anlage zwölf Lücken im Jahr). Heizwärme fehlt nur, wenn
> weder `heizenergie_kwh` noch `waerme_kwh` steht (Gruppe `wp_waerme`). Wortlaut und Handgriffe:
> [HANDBUCH_DATEN_CHECKER §4.3.7](HANDBUCH_DATEN_CHECKER.md#437-wärmepumpe).
>
> ⛔ **Eine vollständige feine Aufteilung verwirft den Gesamtzähler nicht** (K1): was er **mehr** misst, gehört zu Strom,
> Kosten, CO₂ und Arbeitszahl-Nenner. *Doppelzählung entsteht beim **Addieren**, nicht beim **Ersetzen**.*

#### Die Achsen Strom Heizen und Strom Warmwasser des Monats

`WpFakten.strom_heizen_kwh` und `.strom_warmwasser_kwh` sind die Summe der Zeilenfelder `strom_heizen_kwh` bzw.
`strom_warmwasser_kwh` über die Wärmepumpen-Zeilen des Monats (`imd_monatsaggregat.py::imd_typ_beitrag` →
`monats_fakten/roh.py::_RohMonat._falte_wp`). Die Summe filtert nicht: auch ein Warmwasser-Strom an einem Gerät ohne
Warmwasser-Achse ist über den Zähler geflossen — gefiltert wird die Wärme (N-379), nicht der Strom. **Summanden der Menge**
sind die Felder nur mit dem Kennzeichen *Getrennte Strommessung* (`summanden_gelten`): ohne Gesamtzähler ist die Menge ihre
Summe plus die gemessenen **funktionsfremden** Teilmengen (Kühlen, Lüften, Entfeuchten — W-16; ein gemessener Heiz-Betriebsart-Zähler
stünde doppelt zu `strom_heizen_kwh`; `wp_strom.py::wp_feine_summe_kwh`), mit Gesamtzähler stehen sie unter ihm, und der Rest heißt *nicht
aufgeteilt* (K5, Kasten oben). `WpFakten.hat_split` sagt, ob ein Gerät des Monats das Kennzeichen trägt; nur dann zeigt die
Monatstabelle Strom Heizen und Strom Warmwasser (`monatsdaten_aggregiert.py`). Ein fehlender Wert zählt 0; ob eine Achse
gemessen ist (auch als 0), sagen `strom_heizen_gemessen`/`strom_warmwasser_gemessen` — ein ODER über die Geräte (N-479).

> #### Die gemessene Wärme eines Geräts — **Gesamtwert vor Summanden** (Regel D1)
>
> **SoT:** `core/berechnungen/waermepumpe_kennzahl.py::waerme_gesamt_kwh`. Jede Sicht, die eine
> Wärmemenge auswertet, bekommt sie von dort — Monats-Fakten, Komponenten-Hub, HA-Export,
> Community-Payload, der Tag, die anlagenweiten Alternativkosten
> (`core/berechnungen/alternativkosten.py` ⇒ Aussichten · ROI · Jahres-Ersparnis des HA-Exports),
> die thermische Gewichtung der WP-Prognose (gebildet in `api/routes/aussichten/finanz_rueckblick.py`, gelesen von
> `finanz_prognose.py`), die Komponenten-Zeile „Ersparnis vs. Alternative“ in *Cockpit → Monat*, die Monatsspalte „WP Wärme“
> in *Auswertungen → Tabelle* (`monatsdaten_aggregiert._zeile_komponenten` ⇒ `wp_waerme_kwh`, N-778), die Zahlen je Gerät
> (`services/waermepumpe_kennzahlen_je_geraet.py`), der Wärme/Klima-Block in *Cockpit → Monat* (`aktueller_monat/waerme.py`),
> der Daten-Checker (`daten_checker/waermepumpe.py`) und die Nicht-DB-Quellen des laufenden Monats (MQTT · Connector ·
> HA-Statistik) — belegt am Grep `waerme_gesamt_kwh(`.
>
> ```
> Wärme_kWh = waerme_kwh            , wenn gepflegt        (EIN gemeinsamer Wärmemengenzähler)
>           = heizenergie_kwh + warmwasser_kwh, sonst      (getrennte Zähler)
> ```
>
> **„Gepflegt" heißt > 0** (Entscheid 8.11.2026, bewusste Ausnahme von der 0-Regel): Eine gemessene 0 des Gesamtzählers
> gilt nicht als Gesamtwert, die Achsen zählen — ein Zähler ohne neuen Stand im Zeitraum (eingefroren, Statistik-Lücke, erst
> seit kurzem zugeordnet) ergibt Δ = 0, und die Achsen tragen dann die bessere Zahl. Dieselbe Weiche in Monat, Tag, Stunde
> (`geraete_mit_gesamtwaerme`) und laufendem Monat; der Daten-Checker meldet den Fall (Meldung „‚Wärme gesamt‘ ist 0, Heizwärme +
> Warmwasser-Wärme sind größer“, Warnung). Festgeschrieben in `test_n391_gesamtwaerme.py::test_k13_gemessene_null_ist_kein_gesamtwert`.
>
> ⚠ **Diese Liste ist Teil der Regel, nicht ihre Illustration** (N-391c): Wer eine Wärmemenge liest, steht hier — oder er
> liest falsch; eine Sicht ohne D1 sieht an einem Gerät mit gemeinsamem Wärmemengenzähler die Wärme 0.
>
> ⛔ **`waerme_kwh` ist nie ein dritter Summand.** Wer Gesamtzähler **und** Aufteilung pflegt, zählte
> sonst Gesamtwert und Aufteilung zusammen. Und die Regel fällt **je Gerät vor** dem Summieren: auf Anlagensummen
> angewandt verschwände die Aufteilung des zweiten Geräts hinter dem Gesamtwert des ersten
> (N-391b, ADR-002/P4).
>
> **Warum der Gesamtwert gewinnt (K1):** Die Gesamtmenge ist die Messung; jede Aufteilung steht
> daneben, nie an ihrer Stelle. **Dieselbe Richtung wie auf der Stromseite** (K1/K3, `wp_strom_stufe` Regel 1): auch dort
> ist der Gesamtzähler die Menge und die Aufteilung steht darunter. Nur dort tritt die Aufteilung an seine Stelle, wenn er mehr
> als die Toleranz unter ihr liegt; auf der Wärmeseite gilt der Gesamtwert auch dann, und der Daten-Checker meldet den
> Widerspruch (N-391, Kasten oben).
>
> **Folge für die Kennzahlen je Funktion (N-391):** Trägt `waerme_kwh` die Wärme, gibt es für die Funktionen ohne eigenen
> Wärmewert **keine** Arbeitszahl, sondern den Grund *„Wärme nicht je Funktion gemessen"* — ein gemeinsamer Zähler ist keine
> Heizwärme, und `Gesamtwärme ÷ Heizstrom` wäre keine Kennzahl. Wer Gesamtwert **und** Aufteilung pflegt, behält seine
> Funktions-Zahlen: sie sind gemessen und tragen dieselbe Abgrenzung.

#### Die Achsen Heizwärme und Warmwasser des Monats

Die **Heizwärme** einer Zeile liest `core/berechnungen/waermepumpe_kennzahl.py::heizwaerme_kwh` (N-398): `heizenergie_kwh`,
sonst der Legacy-Name `heizung_kwh` (der erste Wert > 0, bitgleich zu `get_wp_heizenergie_kwh`), sonst die gemessene
*Nutzenergie Heizbetrieb* (`betriebsart_nutzenergie_heizen_kwh`, Gerätefeld vor Σ Innengeräte), sonst keine Angabe. Eine
gepflegte 0 in einem der ersten beiden Felder ist eine Messung und verdrängt die Nutzenergie (F-42); addiert wird nichts. Die
**Warmwasser-Wärme** liest `core/field_definitions/reader.py::get_wp_warmwasser_kwh` (N-379): `warmwasser_kwh`, aber nur, wenn
das Gerät die Größe laut Registry hat (`groesse_gibt_es_am_geraet`) — eine Split-Klimaanlage hat keinen Warmwasserkreis, ein
dort gespeicherter Wert zählt 0 und bleibt stehen (der Daten-Checker benennt ihn).

`WpFakten.heizung_kwh` und `.warmwasser_kwh` sind die Summe dieser Werte über die Wärmepumpen-Zeilen des Monats
(`imd_typ_beitrag` → `roh.py::_RohMonat._falte_wp`). **Ohne gemessene Achse keine Angabe** (N-673, `bau.py::_wp_fakten`): misst
kein Gerät des Monats die Achse, ist der Wert `None` — eine Wärmepumpe nur mit Gesamtwärme hat keine Heizwärme 0, sondern eine
unbekannte Aufteilung; eine gemessene 0 bleibt 0. Gemessen heißt: eine Stufe der Lesetür trägt einen Wert bzw. die Zeile trägt
einen Warmwasser-Wert an einem Gerät mit dieser Achse (`hat_wp_warmwasser_wert`); die Marke ist ein ODER über die Geräte
(N-479). Wer summiert, liest `or 0.0` und fragt die Marke. Beide Achsen sind die Summanden der Wärme nach D1, nie neben
`waerme_kwh` addiert (Kasten oben).

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
η_alt                = alter_wirkungsgrad(Energieträger)   # 0,90 Gas · 0,85 Öl · 1,0 Strom

WP_Kosten            = WP_Strom * Strompreis / 100
Alte_Kosten          = Gesamtwärmebedarf / η_alt * Alter_Preis / 100
                     + alternativ_zusatzkosten_jahr        # Schornsteinfeger / Wartung / Grundpreis Gaszähler

Jahres-Einsparung    = Alte_Kosten - WP_Kosten

CO2_alt               = Gesamtwärmebedarf / η_alt * CO2_Faktor[gas|oel|strom]
CO2_WP                = WP_Strom * 0.38
CO2-Einsparung        = CO2_alt - CO2_WP
```

> ### ⛔ Der WP-Strom trägt den vollen Netztarif — auch der Teil aus der eigenen PV
>
> **Kein `Netz_Anteil`-Abschlag** in Kosten oder CO₂ und keine PV-Anteil-Konstante (S1b, `core/calculations.py`): der
> ganze WP-Strom trägt den Strompreis und den CO₂-Faktor.
>
> **Der Grund ist keine Vereinfachung, sondern ADR-002/P9:** Der PV-Strom, den die
> Wärmepumpe verbraucht, ist auf der **PV-Seite** bereits gutgeschrieben — im Geld als
> **Eigenverbrauch** (er wird dort mit dem Netzbezugspreis bewertet), im CO₂ als
> **vermiedener Netzstrom**. Ihn in der Wärmepumpen-Rechnung ein zweites Mal abzuziehen,
> zählte dieselbe Kilowattstunde doppelt.
>
> Das Feld **„PV-Anteil (%)"** am Gerät bleibt und beantwortet eine **Mengenfrage**
> („wie viel des WP-Stroms kam aus der eigenen Anlage?"). Es speist genau zwei Stellen:
> den Eigenverbrauchs-Fallback der Prognose und die Zuordnung des Eigenverbrauchs auf das
> einzelne Gerät. Es beantwortet **keine Preisfrage**.
>
> **Mit eigenem WP-Tarif gilt der Satz genau, wenn N gemessen ist (N-770):** misst die Anlage den Netzbezug zum
> WP-Tarif, wird der PV-Strom der Wärmepumpe auf der PV-Seite zum **WP-Tarif** gutgeschrieben (Abschnitt N-767 unten) —
> die WP-Kosten bleiben WP-Strom × WP-Tarif, und die kWh ist weiter einmal Geld.
>
> Damit rechnen alle vier Ersparnis-Pfade derselben Wärmepumpe nach **einer** Regel:
> Monats-Layer (`services/wp_wirtschaftlichkeit.py` — Komponenten-Hub, *Cockpit → Monat/
> Jahr*, HA-Sensor je Gerät), anlagenweite Alternativkosten
> (`core/berechnungen/alternativkosten.py`), die Jahresformel der Prognose
> (`api/routes/aussichten/finanz_prognose.py`) und diese Planungsformel hier. Die CO₂-Zeile trifft sich
> dabei mit dem gemessenen Pfad `co2_wp_ersparnis_kg`, der den vollen Strom
> belastet (ADR-001/DI-1).
>
> #### Mit eigenem Wärmepumpen-Tarif — Netzbezug zum WP-Tarif oder Grenze (N-767, N-770)
>
> Die Regel oben setzt voraus, dass PV-Seite und Geräteseite **denselben** Preis tragen. Mit einem Tarif *Verwendung
> Wärmepumpe*, dessen Arbeitspreis vom allgemeinen abweicht, tun sie das nicht mehr. Je Monat ist der WP-Strom
> **S = P + N** — P aus der PV, N aus dem Netz; Haushaltstarif H, WP-Tarif W:
>
> | Größe | ohne Messung von N | mit gemessenem N (N-770) |
> | --- | --- | --- |
> | Stromrechnung | Netzbezug × H — zu hoch um N·(H−W) | (Netzbezug − N) × H + N × W |
> | EV-Ersparnis | EV × H — zu hoch um P·(H−W) | (EV − P) × H + P × W, P = S − N |
> | WP-Kosten / WP-Ersparnis | S × W | S × W (unverändert, P9) |
> | Monats-/Jahresergebnis | zusammen (P − N)·(H−W) daneben | exakt |
>
> **Die Messgröße** ist das optionale Feld **„Netzbezug zum WP-Tarif"** an der Wärmepumpe (`netzbezug_eigener_tarif_kwh`,
> kWh, kumulativ): die Menge, die der Versorger zum WP-Tarif abrechnet. In einer **Zählerkaskade** (Z1 am Netzanschluss,
> Z2 für Haus und PV, die Wärmepumpe dazwischen) ist sie *Z1-Bezug − Z2-Bezug* — die PV deckt hinter Z2 zuerst das Haus,
> nur der Überschuss erreicht die Wärmepumpe, und was sie darüber hinaus braucht, zieht sie durch Z1 aus dem Netz. Ein
> **eigener WP-Zähler, der nicht hinter der PV hängt**, ist N selbst (derselbe Sensor wie „Stromverbrauch", P = 0).
> Mehrere Wärmepumpen: N je Gerät, im Monat summiert; fehlt N an einem Gerät mit Strom > 0, gilt der Monat als nicht
> gemessen (keine Mischung aus gemessen und geschätzt). Klemme: N auf `[0, min(S, Netzbezug)]` (§3.1). Bildungsstelle
> `monats_fakten/tarif.py::komponenten_anteile`, Formel `finanz_aggregat.bewerte_eigenverbrauch` (P auf den bewerteten
> Eigenverbrauch begrenzt, P15-Grundmenge unverändert).
>
> **Ohne Messung bleibt es bei der Grenze** — sie hängt dann am Messpunkt. Sitzt die Wärmepumpe hinter dem Messpunkt, an
> dem eedc Netzbezug und Einspeisung liest (Netzanschluss), stehen die Ersparnis um P·(H−W) und die Stromrechnung um
> N·(H−W) zu hoch, zusammen höchstens S·|H−W|; liest eedc am Hauszähler einer Kaskade, steckt der PV-Anteil der
> Wärmepumpe in der „Einspeisung". Eine Zuteilung (etwa WP-Strom × Eigenverbrauchsquote) wäre erfundene Genauigkeit —
> deshalb die Messgröße statt einer Schätzung (Entscheid Gernot, N-767). Der **Daten-Checker** (Kategorie *Strompreise – eigener
> WP-/Wallbox-Tarif*, E4) nennt Monate ohne das Feld mit der Obergrenze für Ersparnis UND Stromrechnung
> zusammen (S × |H − W| der ungemessenen Monate der letzten zwölf) und dem Rat «Netzbezug zum WP-Tarif zuordnen»; still,
> wenn jeder Monat mit WP-Strom gemessen ist. Dazu WARNING bei N > S (2 %) bzw. N > Netzbezug (geklemmte Monate) und INFO,
> wenn derselbe Sensor in «Stromverbrauch» und im Feld steht (paralleler Zähler: der Netzbezug der Anlage muss ihn
> enthalten, Summe beider Zähler). Tag/Stunde (E3) und Prognose/ROI (E4) folgen der Messung (§3.1). Eine **Wallbox** mit
> eigenem Tarif hat dieselbe Messgröße („Netzbezug zum Wallbox-Tarif", N-771); sie ist dort zugleich die Netzladung
> (F11, E-Mob-Abschnitt).

> **Wirkungsgrad der Altanlage (η_alt):** `Gesamtwärmebedarf` ist **abgegebene Wärme**, nicht Brennstoff — das Eingabefeld heißt „Heizwärmebedarf (kWh/Jahr) — aus Energieausweis", und derselbe Wert wird oben durch die JAZ geteilt (JAZ = Wärme/Strom). Ein Kessel muss dafür `Wärme / η` verfeuern; `Alter_Preis` ist der Preis je kWh **Brennstoff** (so steht er auf der Rechnung). Die Umrechnung macht der Layer-SoT `gas_kosten_altanlage`, die η-Wahl der Resolver `alter_wirkungsgrad` — beide in `core/berechnungen/alternativkosten.py`.
>
> Dieselbe Rückrechnung gilt für die CO₂-Zeile und in Aussichten, HA-Export und WP-Dashboard (alle über `gas_kosten_altanlage`). **Die fixen Zusatzkosten werden nicht durch η geteilt** — sie sind keine Energie.
>
> **Strom-Direktheizung:** η = 1,0. Eine Widerstandsheizung (Nachtspeicher, Infrarot) setzt Strom verlustfrei in Wärme um; ihr einen Kesselverlust anzurechnen, würde die WP-Ersparnis überhöhen.

> **Diese Rechnung braucht zwei gepflegte Angaben — sonst läuft sie nicht.** Die Bauart entscheidet das nicht: auch eine Luft-Luft-Wärmepumpe kann eine Gasheizung ersetzen; ausgeschlossen wird allein eine **erfundene Eingabe**. (1) Ist beim **ersetzten Energieträger** „Nichts ersetzt (Neubau)" gewählt, wird **weder Ersparnis noch CO₂-Ersparnis** konstruiert — für **jede** Wärmepumpenart (N-88). (2) Ist **kein Wärmebedarf gepflegt**, gibt es keinen Default; die ROI-Zeile trägt „—" und `nicht_bewertet` samt Begründung. Eine halb gepflegte Angabe zählt entsprechend halb (nur Warmwasser gepflegt ⇒ Heizwärme 0). (3) **Bestandsschutz ohne Migration:** Steht an einer Luft-Luft-WP noch **exakt** die alte Vorbelegung 12.000/3.000, zählt sie als offene Frage statt als Antwort — sie war im Formular unsichtbar und damit nicht korrigierbar. Bei klassischen Wärmepumpen bleibt sie eine Schätzung und wird gerechnet. Die **gemessenen** Pfade (`services/wp_wirtschaftlichkeit.py`, `co2_wp_ersparnis_kg`, Aussichten, JAZ/COP) haben zusätzlich ihren `wp_waerme_kwh <= 0`-Wächter. (4) **Eine Achse, die es am Gerät nicht gibt, geht mit 0 ein** (WK-15c): Eine **Brauchwasser**-Wärmepumpe gibt keine Heizwärme ab, eine **Split-Klimaanlage** hat keinen Warmwasserkreis (N-304) — der jeweils andere Bedarf wird vor der Formel auf 0 gesetzt, auch wenn eine Zahl im Feld steht. Steht auf den geltenden Achsen **nur** die Vorbelegung, greift (3); steht dort gar nichts, greift (2). SoT der Unterscheidung: `core/berechnungen/alternativkosten.py::ersetzt_keine_heizung` für (1) und `field_definitions/bedingungen.py::feld_urteil` für (3) und (4) — **die Registry entscheidet je Achse, nicht die Bauart** (ADR-002/P13). Die Layer-Formel `berechne_waermepumpe_einsparung` bleibt davon unberührt: Sie rechnet, was der Aufrufer ihr gibt.

> **Punkt (1) gilt auch in den anlagenweiten Sichten** — CO₂-Ersparnis im Jahresbericht und Alternativkosten-Ersparnis der Jahresprognose unter *Auswertungen → Aussichten*: Der fossile Vergleich rechnet auf beiden Seiten mit **den Geräten, die etwas ersetzt haben** — dieselbe Grundmenge im Zähler wie im Abzug. Eine Split-Klimaanlage mit „Nichts ersetzt (Neubau)" neben einer Wärmepumpe, die eine Gasheizung ersetzt hat, bekommt keine vermiedene Gas-Wärme gutgeschrieben, und ihr Strom mindert die Ersparnis der anderen nicht. Die Mengen der Anlage (Stromverbrauch, gelieferte Wärme) bleiben davon unberührt; kleiner wird allein die **Grundmenge des Vergleichs**. SoT sind die Teilmengen `WpFakten.waerme_mit_ersatz_kwh` / `strom_mit_ersatz_kwh` aus der Monats-Fakten-Schicht (ADR-002/P10).
>
> **Faltung der Teilmengen** (`monats_fakten/roh.py::_RohMonat._falte_wp`, N-256): je WP-Zeile gehen Strom und Wärme
> zusätzlich in die `*_mit_ersatz`-Summen, wenn das Gerät eine Heizung ersetzt hat (`not ersetzt_keine_heizung(ersetzter
> Energieträger)`; ein ungesetztes Feld zählt wie bisher als ersetzt) — keine Aufteilung je Gerät, zwei Summen neben den
> Anlagenmengen: `strom_mit_ersatz = Σ_{Geräte mit Ersatz} Strom`, `waerme_mit_ersatz = Σ_{Geräte mit Ersatz} Wärme`.
>
> ⭐ **Warum Teilsummen und keine Sperre.** Die *Arbeitszahl* wird bei gemischten Bauarten gesperrt, weil ein Quotient über zwei Maßstäbe keine Aussage hat. Eine *CO₂-Menge* dagegen ist additiv — für sie genügt die Teilsumme. **Kennzahlen trennen wir je Bauart, Mengen summieren wir.**


> **Alternativ-Zusatzkosten (#141):** `alternativ_zusatzkosten_jahr` (€/Jahr) deckt laufende Fixkosten der Alt-Heizung (Schornsteinfeger, Wartung, Gaszähler-Grundpreis) ab. Berücksichtigt in Aussichten (historisch und Prognose), im HA-Sensor-Export inkl. WP-Sensor, im PDF-Jahresbericht, in der Investitions-Vorschau und im Monats-Layer (`berechne_wp_ersparnis`: Komponenten-Hub, Cockpit → Monat/Jahr, Vorjahresvergleich, Komponenten-Zeitreihe) — überall dieselbe Ersparnis. In historischen Aggregaten anteilig pro erfasstem Monat (`alternativ_zusatzkosten_jahr / 12`).

#### Eingabefelder

Die Monats-Messgrößen der Wärmepumpe (Strom, Wärme, Achsen, Betriebsarten) stehen in der
[Übersicht der Größen §1](UEBERSICHT-GROESSEN.md#1-eingabefelder) und in der [Sensor-Referenz §4](SENSOR-REFERENZ.md#4-wärmepumpe);
ihre Monatsregeln stehen oben. Diese Planungsrechnung liest die Investitions-Parameter (`core/investition_parameter.py`,
`PARAM_WAERMEPUMPE_DEFAULTS`):

| Feld | Parameter-Key | Default |
|------|--------------|---------|
| Effizienz-Modus | `effizienz_modus` | `gesamt_jaz` |
| JAZ | `jaz` | 3.5 |
| SCOP Heizung | `scop_heizung` | 4.5 |
| SCOP Warmwasser | `scop_warmwasser` | 3.2 |
| COP Heizung | `cop_heizung` | 3.9 |
| COP Warmwasser | `cop_warmwasser` | 3.0 |
| Heizwärmebedarf | `heizwaermebedarf_kwh` | **kein Default mehr** in der ROI-Rechnung; im Formular Vorbelegung 12000 — **nicht** vorbelegt, wo dem Gerät eine der beiden Wärme-Achsen fehlt (`luft_luft`, `brauchwasser`). Zählt nur auf einer Achse, die es am Gerät gibt, s. (4) oben |
| Warmwasserbedarf | `warmwasserbedarf_kwh` | **kein Default mehr** in der ROI-Rechnung; im Formular Vorbelegung 3000 — **nicht** vorbelegt, wo dem Gerät eine der beiden Wärme-Achsen fehlt (`luft_luft`, `brauchwasser`). Zählt nur auf einer Achse, die es am Gerät gibt, s. (4) oben |
| PV-Anteil | `pv_anteil_prozent` | 30, wenn nie eingetragen — im Formular **nicht vorbelegt** (N-572); ein geleertes Feld bleibt leer und nimmt das Gerät aus dem Prognose-Mittel (s. „`WP_PV_Anteil`" in §4.4) |
| Alter Energieträger | `alter_energietraeger` | `gas` |
| Alter Preis | `alter_preis_cent_kwh` | 12 (Fallback wenn `Monatsdaten.gaspreis_cent_kwh` leer) |
| Alternativ-Zusatzkosten | `alternativ_zusatzkosten_jahr` | 0 (€/Jahr) |
| WP-Strompreis | Spezialtarif `waermepumpe` | Fallback: allgemein |

#### 3.5b Modus-Split: Heizen und Kühlen trennen (#263 K-2)

Eine Split-Klimaanlage heizt und kühlt über **denselben** Zähler. Die Aufteilung ist aus keinem
gespeicherten Wert rekonstruierbar — sie entsteht nur, wenn eedc den Betriebsmodus **zur Messzeit**
mitschreibt (`TagesEnergieProfil.betriebsmodus_je_wp`, seit S2).

> **Welcher Wert die Stunde bestimmt** (`core/betriebsmodus.py::normalisiere_betriebsmodus`):
> der eingestellte Modus (`hvac_mode`), **verfeinert** durch den Ist-Betrieb (`hvac_action`),
> wo die Integration ihn liefert (D2). ⚠ **Verfeinern heißt nicht verwerfen** — der Ist-Betrieb
> schlägt den Modus nur, wo er eine **Richtung** nennt (`heating`/`cooling`/`drying`/`fan`) oder
> `off`. **`idle` (Leerlauf) nennt keine und fällt deshalb auf den eingestellten Modus zurück**
> (#399 — sonst fiele bei einem taktenden Inverter-Gerät der Großteil des Stroms in *nicht aufgeteilt*). Ohne Richtung im Modus — Automatik
> (`heat_cool`/`auto`) oder gar kein Modus — bleibt es `unbestimmt`; geraten wird nicht.

```text
je Tag d, je Gerät i:
  roh_h       = |komponenten["waermepumpe_<i>"]|          # Leistungspfad, NEGATIV gespeichert
  faktor_d    = zaehler_kwh_d / Σ_h roh_h                 # nur wenn Zählersumme vorhanden
  kwh[modus] += roh_h × faktor_d                          # Stunden OHNE Modus: nur in den Nenner

je Monat (ein Gerät):
  modus_strom_heizen_kwh     = Σ_d kwh[heizen]
  modus_strom_warmwasser_kwh = Σ_d kwh[warmwasser]                 # N-336
  modus_strom_kuehlen_kwh    = Σ_d kwh[kuehlen]
  modus_abdeckung_h          = Σ_d Stunden mit Modus-Signal
  modus_nicht_aufgeteilt_kwh = max(0; modus_strom_bezug_kwh − heizen − warmwasser − kuehlen
                                      − lueften − entfeuchten)     # Property, NIE gespeichert

anlagenweit (mehrere Geräte, gleicher Zeitraum):
  modus_strom_*_kwh       = Σ_i  je Gerät                 # Mengen: addieren
  modus_abdeckung_h       = max_i je Gerät                # Zeit: NICHT addieren
```

SoT: `core/berechnungen/modus_split.py` (rein) · `services/energie_profil/modus_split_monat.py`
(Lader) · `…/modus_split_schreiben.py` (Schreiber, Schritt 4 des Monatsabschlusses).

**Die Teilmengen der Monatszeile** liest `core/berechnungen/betriebsart_gemessen.py::modus_strom_zeile` — *gemessen schlägt
abgeleitet*, ganz oder gar nicht je Zeile (F-56). **Abgeleitet** (der Modus-Split oben bzw. der Kanal E4d unten) trägt die
Zeile Heizen, Warmwasser (N-336) und Kühlen (`MODUS_STROM_FELD`). **Gemessen** — sobald ein Betriebsart-Strom-Zähler einen Wert
trägt — gelten die Betriebsart-Zähler Heizen, Kühlen, Lüften und Entfeuchten (Gerätefeld vor Σ Innengeräte); Warmwasser kommt
dort aus dem Summanden `strom_warmwasser_kwh` und Heizen ohne eigenen Zähler aus `strom_heizen_kwh`, beides nur mit dem
Kennzeichen *Getrennte Strommessung* (N-766). Lüften und Entfeuchten gibt es deshalb nur im gemessenen Zweig.
`WpFakten.modus_strom_warmwasser_kwh`, `.modus_strom_lueften_kwh` und `.modus_strom_entfeuchten_kwh` sind wie Heizen und Kühlen
die Summe je Zeile über die Geräte (`imd_typ_beitrag` → `roh.py::_RohMonat._falte_wp`). Altmonate ohne das Warmwasser-Feld
behalten den Anteil im Rest — eedc rechnet die Historie nicht nach.

> **Teilmengen, keine Summanden.** `stromverbrauch_kwh` bleibt die einzige Bilanzgröße; die zwei
> Anteile werden **ausgewiesen und nie addiert** (Präzedenz `ladung_pv_kwh` bei der Wallbox).
> Wächter: `test_263_k2_modus_split.py::test_teilmengen_werden_nirgends_addiert`.

> **Zwei Vorzeichen-Welten.** `TagesEnergieProfil.komponenten` führt die Wärmepumpe **negativ**
> (Leistungspfad, `seite: "senke"` ⇒ `-abs(...)`), `TagesZusammenfassung.komponenten_kwh`
> **positiv** (Zählerpfad). `waermepumpe_kwh_je_investition` liefert für beide Beträge — und ist
> zugleich die Stelle, die `waermepumpe_1` von `waermepumpe_12` unterscheidet (die ID ist **kein**
> Präfix) und Suffix-Keys (`…_heizen`) demselben Gerät zuschlägt.

> **Normierung ist opportunistisch, die Invariante ist der Schutz.** Wo der Zählerpfad eine
> Tagesmenge kennt, wird die Stundenform darauf normiert (Präzedenz v3.45.5). Er kennt sie nicht
> immer — dann gilt die Roh-Summe. Was `Σ Teilmengen ≤ Gesamt` hält, ist die Regel im Schreibpfad:
> **größer ⇒ gar nicht schreiben**, vorhandene Werte entfernen, Daten-Checker meldet die Monate.

> **Der Bezug von „nicht aufgeteilt" ist nicht der Gesamtstrom.** Anlagenweit trägt `strom_kwh`
> auch Wärmepumpen **ohne** Modus-Sensor; ihr Verbrauch erschiene sonst als unbeobachtete Zeit der
> Klimaanlage. Bezug ist `WpFakten.modus_strom_bezug_kwh` — der Strom nur der Geräte mit Split.
>
> ⭐ **Und genau deshalb nennt die Anzeige diesen Bezug (W-17b).** Die Kachel „Strom verbraucht" zeigt `strom_kwh`, der Balken
> darunter beschreibt `modus_strom_bezug_kwh` — zwei verschiedene Grundmengen. Die Zeile „Aufgeteilte Menge" erscheint, sobald sie abweichen.

> **Eine Menge ist additiv, ein Zeitraum nicht (W-17).** `modus_abdeckung_h` wird über **Tage**
> summiert und über **Geräte** maximiert. Zwei Wärmepumpen, die dieselben 18 Stunden liefen,
> ergeben 18 Stunden Beobachtung, nicht 36 — im Tag sofort sichtbar, im Monat jahrelang plausibel.
> SoT der Regel: `core/berechnungen/modus_split.py::abdeckung_ueber_geraete`.
>
> ⚠ **Das Maximum ist eine Untergrenze der exakten Vereinigung**, die aus verdichteten Summen
> nicht mehr rekonstruierbar ist (`abdeckung_h` ist eine Anzahl, keine Stundenliste). Zwischen
> einer Zahl, die zu klein sein kann, und einer, die einen Tag mit 36 Stunden behauptet, ist die
> Wahl keine Geschmacksfrage.

> **Strom je Betriebsart aus Zeitraum-Differenzen (HA-Bauform E4d).** Mit Home Assistant (bzw. der
> eigenen Summe aus MQTT) führt eedc für jede Wärmepumpe mit Betriebsart-Signal und **ohne** eigene Betriebsart-Zähler
> einen **abgeleiteten Kanal** je Betriebsart (`services/kanal/modus_strom.py`):
>
> ```text
> je Stunde h, je Gerät i (nur ohne gemessene Betriebsart-Zähler — K2):
>   strom_h       = K3-Menge der Stunde (wp_strom_aufteilung auf die Δ von Gesamtzähler / Strom Heizen + Warmwasser)
>   anteil_h[m]   = Verweildauer der Betriebsart m in der Stunde / 3600   # Mitschrift aus dem Betriebsmodus
>   strom[m]     += strom_h × anteil_h[m]        # m ∈ heizen · warmwasser · kuehlen · lueften · entfeuchten
>   rest         += strom_h − Σ_m …              # ohne Signal, „aus", „unbestimmt", Zählerlücke
>   abdeckung    += 1, wenn die Stunde ein Signal hat
> ```
>
> Ein Zeitraum nennt die Aufteilung damit als **ein Δ** je Kanal, wie jede andere Menge. Die Regel der Stunde steht im
> Layer (`modus_split.modus_strom_der_stunde`). Wechselt die Betriebsart innerhalb einer Stunde, teilt der Kanal nach der
> Verweildauer; die Tagesebene oben gibt die ganze Stunde dem länger gelaufenen Modus.
>
> **Lüften und Entfeuchten sind erfasst, nicht bewertet** (Konzept Wärme/Klima §5.4, D11; `modus_split.py::MODUS_STROM_ERFASST`):
> der Kanal führt alle fünf Betriebsarten, in die Monatszeile überträgt die WP-Gruppe aber nur Heizen, Warmwasser und Kühlen
> (`MODUS_STROM_FELD`, `kanal/wp_leser.py`). Kein Leser faltet den abgeleiteten Lüftungs- oder Entfeuchtungsstrom in eine Zahl;
> er bleibt im Rest des Monats. `modus_strom_lueften_kwh`/`_entfeuchten_kwh` der Monats-Fakten kommen nur aus gemessenen
> Betriebsart-Zählern (Teilmengen der Monatszeile, oben).
>
> * **Monat ohne Abschluss:** deckt die **WP-Gruppe** (alle Strom-, Wärme- und Betriebsart-Zähler der aktiven
>   Wärmepumpen und die abgeleiteten Kanäle, `kanal/wp_leser.py`) den Monat, nehmen die Monats-Fakten und *Cockpit →
>   Monat* Strom, Wärme je Feld, Betriebsart-Strom, Kälte, Strom je Betriebsart und Abdeckung aus den Kanälen — in der
>   Form, die der Abschluss in die Monatszeile schriebe, durch dieselbe Faltung. Die Wärme wird dabei **nicht** nach der
>   Betriebsart geteilt: ein Wärmezähler ohne Funktionstrennung bleibt Gesamtwärme. Wie beim Abschluss entsteht aus dem
>   abgeleiteten Heizstrom eine **geschätzte** Heizwärme (`Heizstrom × gepflegte JAZ`, gekennzeichnet, nie
>   Kennzahl-Basis, §3.5c), wenn kein Heizwärme-Zähler da ist.
> * **Abgeschlossene Monate bleiben**, wie sie sind (gespeichert schlägt gerechnet). Trägt eine Monatszeile keine
>   gespeicherte Aufteilung, kommt die Ergänzung im gedeckten Monat aus dem Kanal (dieselben Regeln wie oben), sonst aus
>   der Tagesebene — und die Tagesebene lädt gedeckte Monate gar nicht mehr.
> * **Beginn:** ein neuer Kanal beginnt beim ersten Lauf mit dem laufenden Monat, frühestens mit der Betriebsart-
>   Mitschrift; frühere Monate rechnet eedc nicht neu. Geschrieben wird eine Stunde erst, wenn die Mitschrift **und jeder
>   Strom-Kanal des Geräts** sie erreicht haben (ein neuer Kanal zudem erst ab einer Stunde, in der jeder Strom-Kanal einen
>   Vorstand hat); hört die Mitschrift auf, bleibt der Kanal stehen und der Monat rechnet wie bisher.
> * **Code-Orte (RF-56):** `schreibe_modus_strom` ist der eine Schreibweg (beide Einstiege, Rückgabe = geschriebene
>   Zeilen) und ruft die Phasen `_modus_strom_kontext` (Geräte mit Mitschrift ohne Betriebsart-Zähler, Fenster bis zur
>   Stunde vor dem Lauf) · `_modus_strom_eingaenge` (Stand je Gerät, Beginn/`aufbaubar_ab`, Strom-Kanäle) ·
>   `_modus_strom_stunden` (die Schreibbedingungen oben) · `_modus_strom_stunde` (der Formelblock oben je Stunde) ·
>   `_modus_strom_schreiben` (Kanäle, `aufbaubar_ab` = erste Stunde, Quelle `modus_anteil_je_stunde`).
> * **Der Monatsabschluss schreibt im gedeckten Monat dieselbe Aufteilung** (`modus_split_schreiben.kanal_split_des_monats`):
>   Strom je Betriebsart und Abdeckung kommen aus dem abgeleiteten Kanal, derselbe Monat nennt vor und nach dem
>   Abschluss dieselben Zahlen. Deckt die WP-Gruppe den Monat nicht, schreibt er die Aufteilung der Tagesebene
>   (Leistungspfad) wie bisher.

> **Kein Betrieb ist eine Messung (HA-Bauform E4d, Rest N-585).** Eine **gemessene 0** beim Strom ist erfasst: Sind
> Strom **und** Wärme einer Wärmepumpe im Zeitraum gemessen 0, zeigen Monat, Jahr, Tag, Community-Meldung und PDF die
> Mengen mit 0 (nicht leer), die Arbeitszahl steht als „—" mit dem Zeitraum-Grund *„kein Heizbetrieb in diesem
> Zeitraum"* (eine Brauchwasser-WP: *„keine Warmwasserbereitung in diesem Zeitraum"*; im Jahr und in der Übersicht, wenn
> jede Messung des Zeitraums 0 ist und eine Strom- und eine Wärmemessung darunter sind), die Ersparnis ist 0 € und die
> Ergebnis-Leiter führt die Zeile nicht als fehlend. Ohne Messung bleibt es bei „kein Stromverbrauch erfasst". Strom 0
> bei gemessener Wärme hat keine eigene Regel (keine Ersparnis-Zeile). Strom gemessen 0 **ohne** Wärmemessung nennt
> „kein Wärmemengenzähler zugeordnet" — der Strom ist erfasst, es fehlt die Wärme.
> Liegt eine **Gesamtwärme** vor (ein Wärmezähler ohne Funktionstrennung) und ist der gemessene Strom der Funktion im
> Zeitraum 0, gilt der Zeitraum-Grund *„kein Heizbetrieb in diesem Zeitraum"* vor dem Ausstattungs-Grund *„Wärme nicht je
> Funktion gemessen"* (Konzept §4.3 Zeile 3′): ein Zeitraum ohne Betrieb hat keinen Handgriff.

#### 3.5b-E1b Die **Systemarbeitszahl der Wärmeerzeugung** — die Zahl der ANLAGE (14.09.2026)

Neben der Arbeitszahl **eines Geräts** gibt es eine zweite, anders
benannte Größe für die **Anlage**:

```text
Systemarbeitszahl = Σ gemessene Wärme aller Wärmeerzeuger
                  ÷ (Σ Strom aller Wärmeerzeuger − Kühlstrom)
```

SoT: `core/berechnungen/waermepumpe_kennzahl.py::systemarbeitszahl`, unmittelbar
neben `arbeitszahl` und mit **denselben** Wortlauten für ihre Sperren (zwei
Sprachen für einen Sachverhalt wären die N-327-Klasse). Der Kühlstrom-Abzug ist
derselbe wie dort — **E7/Option A**, also der **Abzug** und nicht die Menge.

> ⭐ **Warum es sie gibt, und warum sie ein „≥" tragen darf.** Trägt ein Gerät
> Strom bei, dem **keine** gemessene Wärme gegenübersteht (Split-Klimaanlage
> ohne Wärmemengenzähler, Heizstab auf eigenem Zähler), steht im Nenner mehr,
> als der Zähler abdeckt — der Quotient kann dann nur **zu klein** sein. Das
> Ergebnis ist eine **untere Schranke** und wird so gezeigt: **„≥ 3,25"**, mit
> dem Satz *„<Gerät>: Strom ohne Wärmemessung enthalten"*. ADR-002/**P4**
> verbietet eine *falsche* Zahl, nicht eine *wahre Schranke*.
>
> ⛔ **In der Gegenrichtung gibt es keine Schranke.** Steht im **Zähler** Wärme,
> deren Strom fehlt, kippt die Zahl nach **oben**; dort sperren
> `GRUND_GERAETE_VERSCHIEDEN`, `GRUND_FREMDWAERME` und
> `GRUND_GERAETE_VERSCHIEDENE_MONATE` unverändert. Ebenso `GRUND_ZEITRAUM`: Die
> Richtung ist unbekannt, und eine Schranke ohne bekannte Richtung ist keine.
>
> ⛔ **Der PDF-Jahresbericht liest weiterhin `arbeitszahl`** — eine Zahl ohne
> sichtbares „≥" im Druck wäre genau das, was P4 verbietet.
>
> ⚠ **E1 ist damit nicht aufgeweicht:** Eine Kennzahl **eines Geräts** entsteht
> unverändert nur, wo Zähler und Nenner dasselbe Gerät und dieselbe Funktion
> meinen. Die Systemzahl ist eine dritte Größe mit eigenem Namen, und im Block
> steht die Zahl **je Gerät** direkt daneben.

**In *Cockpit → Monat*** (`api/routes/aktueller_monat/waerme.py::waerme_klima_monat`) gelten drei Regeln, die nur
diese Sicht braucht — sie ist die einzige mit Vier-Quellen-Auflösung und laufendem Monat zugleich:

```text
Zeitraum versetzt   ⇔ genau EINE von {wp_waerme_kwh, wp_strom_kwh} misst nur einen Ausschnitt des Monats (Teilzeitraum)
Kennzahl je Gerät   = Zeile des Geräts, wenn sie eine Menge trägt (Strom > 0 oder Wärme > 0)
                      sonst Kanal-Zeile des Geräts (Faltung wie eine Monatszeile)
                      sonst Tagesmengen des Geräts im Monat
Funktions-Eingänge  = Monatszeile, wenn sie eine Menge trägt — sonst Faltung derselben Geräte-Mengen (S5)
```

* **Zeitraum-Versatz** (SOLL §4.2 Fall 3, #361): Der Quotient wäre einer aus zwei Zeiträumen — `GRUND_ZEITRAUM`
  sperrt die Systemzahl (keine Schranke, die Richtung ist unbekannt) und jede Funktion (§3.5d). Messen beide Seiten
  denselben Ausschnitt, gibt es keinen Versatz. Bewusst **nicht** aus „Tagen mit Wert" erkannt: das kann „das Gerät
  stand" nicht von „der Sensor fehlte" unterscheiden.
* **Ersatz leerer Gerätekennzahlen** (HA-Bauform E4d, N-472/A-5): Den Dienst `lade_kennzahlen_je_geraet` speisen die
  Monatszeilen, die es im laufenden Monat nicht gibt; ersetzt wird nur, was leer ist, und die Kanal-Zeile geht der Tagesebene vor.
* **S5 anlagenweit** (WK-16i, N-503): Die Eingänge der Funktions-Arbeitszahlen und die Deckung je Funktion kommen aus der
  Monatszeile, wenn sie eine Menge trägt, sonst aus der Faltung der Geräte-Mengen — sie steht an einer Stelle
  (`services/waerme_klima_block.py::funktions_eingaenge_der_anlage`).

Die Systemarbeitszahl bekommt die **sperrende** Kette ohne die beiden Schranken-Glieder (Bauarten gemischt, Geräte
ohne Wärme): Anwender-Angabe, Zeitraum-Versatz, verschiedene Geräte. Code-Orte (RF-67): die
Phase `_wp_abgrenzung` (R2-Lagen, S5, SOLL §3.2b, Schranken-Eingang, sperrende Kette), `_kennzahlen_aus_kanal_zeilen`
und `_kennzahlen_aus_tagesebene`; Proben `test_rf67_aktueller_monat_pv_strings_phasen.py`.

#### 3.5b-H Die **Arbeitszahl ohne Zusatzheizung** — Ausweis-Zahl neben der Hauptzahl (P-433-3, 25.10.2026)

Wer den Heizstab-Strom als kumulativen Zähler erfasst (*Strom Zusatzheizung*, `heizstab_strom_kwh`; Fall **H-B**:
Heizstab hinter dem WP-Zähler), bekommt neben der Arbeitszahl eine zweite, gerechnete Zahl:

```text
AZ ohne Zusatzheizung = (Zähler der Hauptzahl − Heizstab-Strom)
                      ÷ (Nenner der Hauptzahl − Heizstab-Strom)      Heizstab mit Wirkungsgrad 1
```

SoT: `core/berechnungen/waermepumpe_kennzahl.py::arbeitszahl_ohne_zusatzheizung(system, heizstab_kwh)`. Eingang ist
die **fertige Hauptzahl** der Sicht — am Tag die Systemarbeitszahl, im Komponenten-Hub und je Monatszeile die
Arbeitszahl des Geräts. Damit sind der Kühlstrom-Abzug (E7/Option A) und die Sperren **geerbt**: ohne Hauptzahl
keine zweite, mit demselben Grund; eine Schranke (≥) wird keine zweite Zahl. Eigene Gründe: *„Zusatzheizung größer
als der Gerätestrom"* (Nenner ≤ 0), *„Wärme nicht größer als die Zusatzheizung"* (Zähler ≤ 0); Herkunft
*„gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen"*. Mengen: Tag `TAGESDETAIL_AUSGABE` → `wp_heizstab_kwh`;
Monat `imd_typ_beitrag` (`wp_heizstab`) → Hub und `WpFakten.heizstab_kwh` → Cockpit → Monat; Jahr = Σ der Monate
(Übersicht → Jahreskopf). **Geräte-Regel der anlagenweiten Sichten** (Tag, Monat, Jahr;
`waerme_klima_block.ohne_zusatzheizung_felder`): die Zahl nur, wenn jede Wärmepumpe mit Strom-Beitrag einen
Heizstab-Zähler trägt (`WpFakten.geraete_mit_strom ⊆ geraete_mit_heizstab`, im Jahr die Vereinigung über die Monate),
sonst *„nicht alle Geräte melden Zusatzheizung"*; der Hub rechnet je Gerät.

> ⛔ **Keine Wirkung auf Mengen, Ersparnis, CO₂, Community oder HA-Sensoren.** Der Heizstab-Strom ist eine Teilmenge
> des Gerätestroms (kein Komponenten-Beitrag, keine Bilanz-Kategorie); die Hauptzahl bleibt die Zahl, die eedc
> bewertet (#432).

#### 3.5b-A Die **Achsen des Geräts** entscheiden über die Funktions-Arbeitszahl (WK-16h, 15.09.2026)

**Die Frage:** *„Für welche Funktion darf es überhaupt eine eigene Arbeitszahl geben?"*

| | |
| --- | --- |
| **Wer antwortet** | die **Registry** — `core/field_definitions/bedingungen.py::wp_waerme_achsen`, über `feld_urteil(...) == URTEIL_GILT` auf `heizenergie_kwh` bzw. `warmwasser_kwh` |
| **Wer sie auswertet** | `core/berechnungen/waermepumpe_kennzahl.py::arbeitszahl_je_funktion(achsen=…, gesamt=…)` — **eine** Stelle für alle fünf Aufrufer |
| **Anlagenweit** | `services/waerme_klima_block.py::achsen_der_anlage` — Vereinigung über die Geräte, die im Zeitraum **Strom beitragen** |
| **Ergebnis je Bauart** | `brauchwasser` ⇒ {Warmwasser} · `luft_luft` ⇒ {Heizen} · sonst beide |

**Die Regel in drei Zeilen:**

1. Eine Achse, die nicht gilt, bekommt `ARBEITSZAHL_GILT_NICHT` — **weder Wert noch Grund**.
2. Gilt genau **eine** Achse und hat die eigene Rechnung keinen Wert, tritt die
   **Gesamt-Arbeitszahl** an ihre Stelle: Strom und Wärme sind per Bauart dieser
   Funktion zugeordnet.
3. Sonst gilt die eigene Rechnung der Funktion (§3.5d).

> ⭐ **Die Grund-Rangfolge fällt daraus heraus, ohne zweite Regel.** An einem
> Ein-Achsen-Gerät ohne Wärmemengenzähler sagt die Gesamtzahl *„kein
> Wärmemengenzähler zugeordnet"* — und das ist der zutreffende Grund; *„Strom
> nicht getrennt je Funktion gemessen"* nannte die falsche Seite, denn getrennte
> Stromzähler brächten ohne Wärmemessung keine einzige Kennzahl.
>
> ⛔ **Eine Schranke wird nie zur Funktions-Arbeitszahl** (`als_arbeitszahl`
> liefert dort `None`): Die Funktions-Zeilen haben keine Bauform für ein „≥",
> und eine Schranke ohne ihr Zeichen behauptete mehr, als sie weiß (**P4**).
>
> ⛔ **Sie ersetzt einen Grund, nie eine Zahl.** Wo die feinen Zähler eine
> Funktions-Arbeitszahl hergeben, bleibt sie stehen — sie ist eine Messung
> *dieser* Funktion, und der Gesamtzähler wäre der gröbere Nenner (K1: er misst
> Standby und Steuerung mit).
>
> ⚠ **`feld_urteil` und nicht `groesse_gibt_es_am_geraet`** — dieselbe Trennlinie
> wie in WK-15c: Jenes prüft `!= URTEIL_NEIN` und liefert an der Brauchwasser-WP
> für die Heiz-Achse `True`, weil die Bedingung dort **weich** ist. Für eine
> gemessene **Menge** ist das richtig, für eine **Kennzahl** zu weit.

#### 3.5b-V Verteilung des Wärme/Klima-Stroms und **Kosten je Funktion** (WK-16c, 14.09.2026)

**Die Frage:** *„Wohin ist der Strom dieses Geräts gegangen — und was hat es gekostet?"*
SoT der Aufteilung: `core/berechnungen/waerme_verteilung.py::verteile_geraet_strom`;
SoT der Eingänge, Preise und Perioden: `services/waerme_verteilung.py`.

**Die Segmente je Gerät** (Konzept Wärme/Klima Kap. 3 — der Erfassungs-Kanon entscheidet
je Gerät, welche **Familie** gilt; addiert wird erst danach, Kap. 7/E1):

```text
Summanden-Familie (getrennte Strommessung, mindestens eine gepflegte Achse):
    heizen      = strom_heizen_kwh                     (gemessen)
    warmwasser  = strom_warmwasser_kwh                 (gemessen)
    kuehlen/lueften/entfeuchten = die Betriebsart-Zähler, NUR wenn gemessen  (K4/W-16)
    system      = wp_strom_aufteilung(...).nicht_aufgeteilt_kwh              (K5)
  ⇒ Σ Segmente = Menge des Geräts

Teilmengen-Familie (sonst, wenn eine Betriebsart-Aufteilung vorliegt):
    heizen … entfeuchten = modus_strom_zeile(...)      (gemessen ODER abgeleitet)
    ohne_modus  = max(0; modus_bezug − Σ Teilmengen)                          (K5)
  ⇒ Σ Segmente = Bezugsmenge der Aufteilung

sonst: keine Segmente — die Menge bleibt, die Differenz wird GENANNT (W-17b).
```

⛔ **Nie beide Familien für dasselbe Gerät.** Ein **abgeleiteter** Modus-Split verteilt
die Menge, die die Summanden schon tragen — ihn danebenzustellen zählte denselben Strom
zweimal (W-16b). Die Weiche ist dieselbe, die `wp_strom_aufteilung` für die **Menge**
stellt; sie steht an **einer** Stelle.

⚠ **Zwei Reste, nie addiert:** `system` (*System/Standby*) ist der **Zähler**-Rest —
Gesamtzähler minus Summanden-Achsen, also Steuerung, Umwälzpumpen, Standby (WK-16d).
`ohne_modus` ist der **Modus**-Rest — Stunden ohne Signal, nicht gemessene Betriebsarten.
Sie beschreiben zwei **verschiedene** Aufteilungen derselben Menge; ein Gerät trägt immer
nur einen von beiden.

**Die Kosten je Funktion:**

```text
Kosten(Segment, Monat) = kWh(Segment, Monat) × TarifFakten.wp_preis_cent(Monat) / 100
Kosten(Segment, Zeitraum) = Σ über die Monate
Preis(Segment, Zeitraum)  = Kosten × 100 / kWh      (mengengewichtet)
```

⭐ **Der Preis kommt aus den Monats-Fakten und wird nicht selbst aufgelöst**
(ADR-002/**P8**): `TarifFakten.wp_preis_cent` mit den Tarifen zum **Monatsersten** — mit **eigenem** Wärmepumpen-Tarif
dessen Kaskade (WP-Tarif, mit Zeitfenstern über den Netzbezug des Hauses gewichtet, `monats_fakten/tarif.py::_komponenten_preis`);
**ohne** ihn hängt die Wärmepumpe am Hauszähler und trägt dessen Preis mit der ganzen Kaskade — abgerechneter Monats-Ø →
gemessener Ø → Zeitfenster → Stammpreis (N-663). Der Tagespfad rechnet
(*„Tagestarif = Monatstarif je Tag"*), und genau deshalb steht hier eine Quelle statt
zweier. Über ein Jahr wird **je Monat** gerechnet; der gezeigte Preis ist der
mengengewichtete Mittelwert, damit `kWh × Preis = Kosten` aufgeht (**A6**).

⛔ **Es sind die Kosten des VERBRAUCHTEN Stroms, nicht des Netzbezugs.** Welcher Anteil
einer Gerätestunde aus der PV kam, ist ohne eine Zuteilungsannahme nicht bekannt —
dieselbe Begründung, mit der `monats_fakten/tarif.py::_komponenten_preis` den Zeittarif über
den **Haus**-Netzbezug gewichtet.

⚠ **Ein Segment unterhalb der Anzeigegenauigkeit erscheint nicht** (0,02 kWh). Steht ein
Gesamtzähler exakt auf der Summe seiner Achsen, ist der Rest ein Fließkomma-Wert; als
Zeile *„System/Standby 0,0 kWh"* stünde eine Größe im Bild, die es nicht gibt. **Die
Menge bleibt unberührt** (K1).

#### 3.5c Abgeleitete Heizwärme und die JAZ-Sperre (#263 K-2, Konzept §3.4/§3.5)

Ohne Wärmemengenzähler wird die Heizwärme aus dem modus-aufgeteilten Strom gerechnet:

```text
heizenergie_kwh = modus_strom_heizen_kwh × Heiz-Effizienz     # NUR wenn gepflegt
```

Die Heiz-Effizienz kommt je nach `effizienz_modus` aus `jaz` / `scop_heizung` / `cop_heizung`
(`heiz_effizienz_gepflegt`). ⚠ **Nie aus einem Default** — `PARAM_WAERMEPUMPE_DEFAULTS` trägt
`jaz: 3.5`, und wer den anwendet, erfindet für jede ungepflegte Wärmepumpe eine Wärmemenge und
damit eine Ersparnis, eine CO₂-Zahl und einen Kostenvergleich.

Geschrieben wird mit Quelle `auto:monatsabschluss` (`AUTO_AGGREGATION`, Priorität 3) und der
Provenance-Marke `jaz_modus_split`. **„Gemessen schlägt abgeleitet" folgt daraus per
Konstruktion:** `MANUAL` ist 1, `EXTERNAL_AUTHORITATIVE` 2 — beide gewinnen.

**Die eine Regel, die daraus folgt** — sie trennt *teilen* von *multiplizieren*:

| | darf abgeleitete Wärme verwenden? | warum |
|---|---|---|
| **teilt** Wärme durch Strom → JAZ/COP | **nein** | heraus käme exakt die gepflegte JAZ — eine Zahl, die nichts misst |
| **multipliziert** Wärme mit Preis / η / CO₂-Faktor | **ja**, mit Kennzeichnung | die Wärmemenge ist die beste verfügbare Schätzung |

Getragen wird die Sperre von `WpFakten.jaz_belastbar` (Fakten-Leser) bzw.
`heizwaerme_ist_abgeleitet(source_provenance)` (Direktleser). Sie hängt am **Wert**, nicht an der
Bauart: eine Luft-Wasser-WP ohne Wärmemengenzähler fällt unter dieselbe Regel, eine Klimaanlage
**mit** Zähler ist gemessen wie jede andere. Wächter:
`test_263_k2_modus_split.py::test_keine_jaz_stelle_rechnet_mit_abgeleiteter_waerme` (fünf Dateien,
sieben Formeln).

> ⚠ **Kühlen ersetzt keine Heizung (Konzept E-B).** `berechne_wp_ersparnis` und
> `co2_wp_ersparnis_kg` nehmen `strom_kuehlen_kwh` aus dem Vergleich heraus; die Kosten bleiben in
> `wp_kosten_euro` und werden als `kuehl_kosten_euro` eigens ausgewiesen. Default 0.0 ⇒ ohne Split unverändert.
>
> ⭐ **Dieselbe Abgrenzung gilt für die Arbeitszahl (W-14)** — sonst sähe ein Gerät, das im Sommer kühlt, aus wie eine
> schlechte Heizung.
>
> ⭐ **Und sie gilt für alle Funktionen ohne bewertete Nutzenergie (E4).**
> `arbeitszahl(..., strom_funktionsfremd_kwh=…)` bekommt heute **Kühlen + Lüften + Entfeuchten**
> aus einer einzigen Größe: `WpFakten.modus_strom_funktionsfremd_kwh` bzw.
> `ModusStromZeile.funktionsfremd_kwh` — eine Größe statt drei Summanden an jedem Aufrufer. **Abgezogen, nicht gesperrt:** die
> Mengen bleiben in jeder Bilanz, es ändert sich allein der Nenner.
>
> ⭐ **Und abgezogen wird nur, was im Nenner steht — SOLL §4.1, „Ergänzung zu E7"
> (Option A, Entscheid Gernot 12.09.2026).** Ein Abzug ist nur dann eine *Abgrenzung*, wenn die
> abgezogene Menge im Nenner **enthalten** ist. Die Bedingung steht als eigene Layer-Regel in
> `core/berechnungen/betriebsart_gemessen.py::funktionsfremd_abzug_kwh`:
>
> | Zweig | im Nenner enthalten? | Abzug |
> | --- | --- | --- |
> | **ohne** getrennte Strommessung | ja — `stromverbrauch_kwh` ist der Zählerstand des ganzen Geräts | ganz (**W-14**) |
> | F5, ein **Gesamtzähler** ist zugeordnet bzw. gepflegt | ja — der Nenner **ist** der Gesamtzähler (K1), und der trägt den Kühlstrom wie in Zeile 1 | **ganz** |
> | F5 ohne Gesamtzähler, **mit gemessenem** Betriebsart-Zähler | ja — die Menge addiert ihn zu den Achsen (**W-16**) | ganz (**W-16b**) |
> | F5 ohne Gesamtzähler, **abgeleiteter** Modus-Split | **nein** — der Split *verteilt* `strom_heizen_kwh + strom_warmwasser_kwh` | **0** |
>
> ⭐ **Es entscheidet, ob es einen Gesamtzähler gibt, nicht die Vollständigkeit der Achse** (WK-16d) — er ist dann die Menge
> (K1), auch neben zwei gepflegten Achsen.
>
> **Warum das keine Ausnahme, sondern derselbe Grundsatz ist:** SOLL-§9-**E7** begründet an der
> Kategorie, dass eine *Verteilung* kein Nenner sein darf — *„eine Verteilung erbt jede Unschärfe
> ihres Schlüssels, eine Messung nicht."* Das gilt genauso, wenn eine Verteilung einen gemessenen
> Nenner **kürzt**: Aus `Messung − Verteilung` wird keine Messung. eedc trifft die Unterscheidung
> auf der **Additionsseite** bereits (`get_wp_strom_kwh` addiert nur den *gemessenen* Anteil) —
> Option A stellt die Symmetrie her, die dort schon stand.
>
> ⚠ **Zwei Namen für zwei Fragen.** `ModusStromZeile.funktionsfremd_kwh` bleibt die **Definition**
> („welche Betriebsarten haben keine bewertete Nutzenergie?") und trägt weiter Aufteilung, Balken
> und Restmenge (**K1**: die Mengen ändern sich nicht). `funktionsfremd_abzug_kwh` ist die
> **Abzugsregel**. Der Nenner liest `WpFakten.modus_strom_funktionsfremd_abzug_kwh` bzw.
> `TagesStapel.funktionsfremd_abzug_kwh`.
>
> ⛔ **Die Entscheidung fällt je GERÄT, nie anlagenweit** (K2). Eine Anlage darf ein F5-Gerät neben
> einem nicht-F5-Gerät haben; `WpFakten.hat_split` ist dort schon `any(...)`. Deshalb ist der Abzug
> ein aufsummiertes **Feld** und keine Property über den Anlagen-Summen.
>
> ⚠ **Die Funktions-Arbeitszahlen sind unberührt** (E7): Ihr Nenner ist der gemessene F5-Zähler,
> dort wird nichts abgezogen.
>
> ✅ **Der Community-Vergleich rechnet denselben Nenner:** eedc schickt `wp_strom_funktionsfremd_abzug_kwh` — die volle
> Definition (Kühlen · Lüften · Entfeuchten) **und** die Bedingung, also den fertigen **Abzug** statt einer Menge, aus der der
> Server einen bilden müsste.
>
> ⚠ **`wp_strom_kuehlen_kwh` bleibt unverändert die Menge** und wird weiter gesendet — sie ist die
> Auskunft über den Kühlbetrieb des Monats, und der Server wertet Mengen getrennt von Kennzahlen
> aus. Abgezogen wird sie dort nur, wenn `wp_strom_funktionsfremd_abzug_kwh` fehlt (ältere eedc-Version).
>
> ⚠ Monate, die ohne das Feld übertragen wurden, rechnen dort mit dem Kühlstrom-Abzug, bis sie erneut vollständig geteilt
> werden.



#### 3.5d Der Wärme-Vorschlag im Monatsabschluss: Strom derselben Funktion × JAZ, gekennzeichnet (B1, 05.09.2026)

Neben dem Modus-Split gibt es einen zweiten Weg zu einer **abgeleiteten** Wärme: der Vorschlag im
Monatsabschluss (`vorschlag_service`), der für *Heizwärme* und *Warmwasser-Wärme* `Strom × gepflegte
JAZ` anbietet (bzw. SCOP/COP je Funktion nach `effizienz_modus`). Es gilt die Regel aus
`core/berechnungen/waerme_vorschlag.py` (B1) — SOLL Wärme/Klima §6, Präzisierung F2–F5:

| Feld | Basis-Strom | Sprosse | wenn nicht … |
| --- | --- | --- | --- |
| **Heizwärme** | gemessener Heizbetrieb `betriebsart_strom_heizen_kwh` | F4 | … dann `strom_heizen_kwh` (getrennte Messung, F5), sonst **kein Vorschlag** |
| **Warmwasser-Wärme** | `strom_warmwasser_kwh` (getrennte Messung, F5) | F5 | ohne getrennte Strommessung **kein Vorschlag** — die Menge steckt im Vorschlag *Wärme gesamt* |
| **Wärme gesamt** (`waerme_kwh`) | `stromverbrauch_kwh` (F2) — **nur ohne getrennte Strommessung und ohne fremde Spur** in der Zeile: kein gemessener Kühl-/Lüft-/Entfeucht-Strom, keine Kältemenge, kein getrennter Warmwasser-Strom | F2 | sonst **kein Vorschlag**. Der F2-Zweig steht hier, nicht unter *Heizwärme* (N-391), und er braucht die gepflegte **JAZ** — eine Funktions-Arbeitszahl (SCOP/COP) auf dem Gesamtstrom ergäbe eine Menge, die keine Funktion beschreibt |

**Der Vorschlag trägt die Marke `jaz_vorschlag`** (`REGEL_JAZ_VORSCHLAG`, zweite Regel neben
`jaz_modus_split`): der Client meldet sie beim Übernehmen zurück (`abgeleitet_felder`), die
Provenance behält sie, und `heizwaerme_ist_abgeleitet` / `warmwasser_ist_abgeleitet` sperren die
Arbeitszahl (`wp_waerme_abgeleitet` zählt **beide** Funktionen, B1). Multiplizieren (Ersparnis,
CO₂) bleibt erlaubt — mit Kennzeichnung. Die Beschreibung des Vorschlags sagt es dem Anwender:
*„Geschätzt: 254 kWh (Strom Heizbetrieb) × JAZ 3,5 — keine Messung"*.

⚠ **Die Bauart entscheidet hier nichts** (R1, ADR-002/P13): ob der
Gesamtstrom der Heizstrom ist, sagt die Beleglage der Zeile, nicht `wp_art`. Proben:
`test_waerme_vorschlag_b1.py`.

**Alle berechneten Vorschläge des Monatsabschlusses** (`vorschlag_service.py::VorschlagService._get_berechnete_werte`,
nur an einem Gerätefeld, `investition_id` gesetzt; die Liste sortiert `get_vorschlaege` nach Konfidenz — Vormonat 80,
Vorjahr 70, Ø 12 Monate 50):

```
Wärme (Heiz-/WW-/Gesamt) = round(Basis-Strom × Arbeitszahl, 1)          Konfidenz 60 · berechnung · Marke jaz_vorschlag
    Arbeitszahl:  Wärme gesamt → jaz (N-391)
                  Heiz/WW: effizienz_modus gesamt_jaz (Default) → jaz · scop → scop_heizung | scop_warmwasser
                           getrennte_cops → cop_heizung | cop_warmwasser · anderer Modus → keine
                  keine oder 0 ⇒ kein Vorschlag
Gesamtstrom (stromverbrauch_kwh) = round(strom_heizen_kwh + strom_warmwasser_kwh, 1)
                                   nur bei getrennter Strommessung und beiden Werten   Konfidenz 95 · berechnung
Speicher-Ladepreis (speicher_ladepreis_cent) = round(effektiver Ladepreis des Monats, 2)   (#264, R15-2)
    stundengewichtet aus Netzladung × Strompreis-Mitschrift, Fenster Monatserster … Monatsletzter (`speicher_wirtschaftlichkeit.berechne_effektiver_ladepreis`)
    Konfidenz 90 bei Quelle dyn-tarif | boersenpreis, sonst 55 (Text nennt dann die Abdeckung in %)
    ohne Preis oder bei einem Fehler im Lesen: kein Vorschlag (der Abschluss stirbt nie daran)
km aus Tachostand (km_gefahren) = round(km_stand − km_stand des Vormonats, 0)        Konfidenz 95 · berechnung
    nur mit beiden Ständen und Ende ≥ Anfang — ein rückwärts laufender Stand gibt keinen Vorschlag (#407, #396)
km aus Jahresfahrleistung       = round(jahresfahrleistung_km / 12, 0)                Konfidenz 30 · parameter
    nur bei gepflegter Jahresfahrleistung > 0
```

Code-Orte (RF-84): `_wp_vorschlaege` (Wärme mit `_arbeitszahl`, Gesamtstrom) · `_speicher_ladepreis` ·
`_eauto_km` (Tachostand, Jahresfahrleistung). Proben: `test_vorschlag_ladepreis_r15_2.py`, `test_407_tachostand.py`,
`test_rf83_community_vorschlag_korrektur_phasen.py`.

#### 3.5d Arbeitszahl je Funktion und die Arbeitszahl Kühlen (W-4 · W-5)

**Alle vier Arbeitszahlen kommen aus derselben Funktion** (`core/berechnungen/waermepumpe_kennzahl.py`),
und das ist der Punkt: Was für eine gilt, gilt für alle.

```text
Arbeitszahl gesamt     = waerme_kwh              ÷ (strom_kwh − funktionsfremd_ABZUG_kwh)
Arbeitszahl Heizen     = heizenergie_kwh         ÷ strom_heizen_kwh
Arbeitszahl Warmwasser = warmwasser_kwh          ÷ strom_warmwasser_kwh
Arbeitszahl Kühlen     = nutzenergie_kuehlen_kwh ÷ betriebsart_strom_kuehlen_kwh
```

| | Voraussetzung | Grund, wenn sie fehlt |
|---|---|---|
| **je Funktion** (W-4) | `getrennte_strommessung` **und** die zugehörige Wärmemenge | `GRUND_STROM_NICHT_JE_FUNKTION` |
| **Kühlen** (W-5) | Kühlstrom **und** Kältemengenzähler | `GRUND_KEINE_KAELTEMENGE` · `"kein Kühlbetrieb in diesem Zeitraum"` · nur Tag: `GRUND_KEINE_KAELTE_ABGEGEBEN` (Zähler meldet 0 bei Kühlstrom > 0) |

> **Kühlen am Tag (Bauschnitt 6).** Die Kältemenge eines Tages kommt aus
> `get_tagesdetail_kwh` (`wp_kaelte_kwh`) — **Gerätefeld, sonst Σ Innengeräte, nie addiert**
> (`geraetefeld_oder_innengeraete`, dieselbe Regel wie der Monat), im **Fenster der Tageszeile**
> wie der Kühlstrom (N-435). Der Kühlstrom ist der des Tages-Stapels. ⚠ **Die Geräte-Deckung
> prüft der Tag selbst:** Kälte trägt jedes Gerät mit Zähler bei, Kühlstrom nur, wer den Stapel
> besteht; deshalb vergleicht er beide Geräte-Mengen (`deckung_aus_geraeten`, die seit N-441
> die **Identität** prüft statt der Anzahl) statt die Deckung aus dem Monat zu übernehmen — sonst stünde die Kälte
> eines herausgefallenen Geräts im Zähler und sein Strom nirgends.

⚠ **Die R2-Sperren gelten für alle vier** — Anwender-Angabe `abgrenzung`, abgeleitete Wärme,
**gemischte Bauarten**, Geräte ohne Wärme, Zeitraum-Versatz, **verschiedene Geräte** und
**verschiedene Monate** (die letzten beiden seit N-441; die Kette steht in `abgrenzungs_grund`).
Die Kette `abgrenzungs_grund` sperrt dabei die **anlagenweite** Zahl. Die zwei Funktions-Kennzahlen und Kühlen
bekommen in Monat, Jahr und Tag ihren Grund **je Funktion** aus `abgrenzung_je_funktion` (SOLL §3.2b), und dann gilt
nur er — `arbeitszahl_je_funktion` liest `abgrenzung_verletzt` allein ohne dieses Dict (Hub je Gerät). «Verschiedene
Geräte» erreicht die Funktionen dort als Deckung je Funktion (beidseitig gezählt), «verschiedene Monate» im Jahr als
Perioden je Funktion — nicht über die N-441-Glieder der Kette.

> **R2/Bauart** (`GRUND_BAUARTEN_GEMISCHT`, SOLL §5): Trägt ein Block eine
> Luft-Wasser-Wärmepumpe **und** eine Luft-Luft-Split-Klimaanlage, gibt es **keine gemeinsame
> Kennzahl** — verschiedene Nutzenergie, verschiedene Vergleichsmaßstäbe. Die **Mengen** bleiben
> summiert (§5: *„Mengen dürfen nebeneinander stehen, eine gemeinsame JAZ nicht"*), und im
> Komponenten-Hub behält jedes Gerät seine eigene Zahl. ⭐ Erkannt aus den **Stammdaten**
> (`ist_luft_luft_waermepumpe`), nicht aus einer Messreihe — damit ist es nach
> `waerme_deckt_nicht_alle_geraete` die **zweite** Lage, die eedc selbst erkennt. Sie steht
> **vor** ihr in der Reihenfolge: Der allgemeinere Grund riete zu einem Wärmemengenzähler, den
> eine Split-Klimaanlage bauartbedingt nicht haben kann.

> **Die Bauart-Zählung der Monats-Fakten** (`monats_fakten/roh.py::_RohMonat._falte_wp`): je WP-Zeile mit
> Strom > 0 zählt das Gerät als Split-Klimaanlage (`ist_luft_luft_waermepumpe`) **oder** als klassische Wärmepumpe —
> `WpFakten.geraete_luft_luft` / `geraete_luft_wasser`; beide > 0 ⇒ `bauarten_gemischt`. Gezählt wird je Zeile, also je
> Gerät und Monat; ein stillstehendes Zweitgerät sperrt nichts. Der Zähler bleibt bewusst bei „Strom > 0" und nicht bei
> der Geräte-Regel des Nenners (`zaehlt_fuer_geraete_regel`, nach Abzug des funktionsfremden Stroms): er zählt
> Stammdaten, nicht den Nenner — ein reines Kühlgerät bleibt ein Gerät der Anlage.

> **Warum die Arbeitszahl Kühlen nicht „SEER" heißt** (Entscheid, 26.08.2026): SEER ist eine
> genormte Größe aus definierten Prüfstandsbedingungen. Was eedc bildet, ist der Quotient zweier
> Zähler über einen Zeitraum. Sie „SEER" zu nennen behauptete eine Vergleichbarkeit mit
> Datenblatt-Werten, die sie nicht hat. Anwender-Fassung:
> [Wärme & Klima §3](HANDBUCH_WAERME_KLIMA.md#3-was-eedc-bewusst-nicht-sagt).

> **Warum keine geschätzte Kältemenge:** Aus einem angenommenen Wirkungsgrad käme genau der
> Faktor zurück, mit dem gerechnet wurde — dieselbe Zirkularität, die §3.5c für die abgeleitete
> Heizwärme beschreibt, nur auf der Kälte-Achse.

**Nutzenergie Lüften und Entfeuchten** (`WpFakten.nutzenergie_lueften_kwh`, `.nutzenergie_entfeuchten_kwh`; E4, N-398): je
Zeile `core/berechnungen/betriebsart_gemessen.py::nutzenergie_ohne_kennzahl_kwh` — Gerätefeld `betriebsart_nutzenergie_lueften_kwh`
bzw. `…_entfeuchten_kwh`, sonst Σ Innengeräte, nie addiert (`_aufgeloest`); der Monat ist die Summe je Zeile über die Geräte
(`roh.py::_RohMonat._falte_wp`), ohne Zähler 0. Es sind **Mengen ohne Kennzahl** — die Nutzenergie Heizen trägt die Heizwärme
nach D1, die Kältemenge die Arbeitszahl Kühlen, Lüften und Entfeuchten keine: eedc kennt ihren Nutzen nicht (erfasst, nicht
bewertet). Die Mengenzeile erscheint nur mit Zahl (*Cockpit → Monat/Jahr*, Komponenten-Hub).

> **Die Tageszahlen von *Cockpit → Tag*** (`api/routes/energie_profil/tag.py::get_tag_detail`, Phasen RF-71). Neben
> den vier Arbeitszahlen trägt die Tag-Antwort drei Größen, deren Regel nur dort steht:
>
> ```text
> Tages-SOLL PV         = round(pv_prognose_kwh × Lernfaktor(openmeteo), 1); ohne Prognose oder ohne Lernfaktor die
>                         Prognose selbst (None bleibt None)                                  — Phase _tages_soll_pv
> Netzbezugspreis (Tag) = Slot-Ø des Tages (lade_slot_kosten_je_tag → mittel_cent), sonst der Arbeitspreis des Monats
>                         (baue_finanz_zeile mit der Monatsdaten-Zeile; bei dynamischem Tarif ihr abgerechneter Monats-Ø);
>                         Herkunft = die des Slot-Tags, ohne Slot-Tag None (SOLL P-2; dieselbe Quelle wie die
>                         Tages-Tabelle, sonst die F-18-Klasse)                                — Phase _tag_preis
> SOLL-Erreichung (Tag) = Erzeugung der Tag-Zeile von tage-werte ÷ Tages-SOLL PV × 100 (ergebnis.quote, nur mit SOLL > 0
>                         und Erzeugung; Päckchen BB — bis dahin teilte der Client zwei Antworten)  — Phase _speicher_und_soll
> Nenner je Funktion    = Strom Heizen bzw. Warmwasser aus der Faltung funktions_eingaenge_der_anlage, wo sie > 0 trägt,
>                         sonst der Tageswert samt seiner None-heit (_nenner_der_funktion — nur die Faltung kennt die
>                         Ein-Achsen-Regel R-4); Zähler = die Tagessumme (aufgelöste Heizwärme D1, Warmwasser)
>                                                                                            — Phase _funktions_deckung
> ```
>
> Code-Orte je Phase: `_tag_laden` (Tageseingänge `tages_eingaenge`, W-18-Grund, Ladepreis) · `_wp_strom_je_geraet`
> (R-4/N-482/N-491, Tages-Stapel) · `_waerme_tag` (D1 je Gerät, N-391b) · `_geraete_mengen` (D-Sicht 3, Schranken-Eingang) ·
> `_funktions_deckung` (§3.2b, Kühlen beidseitig) · `_abgrenzung_tag` (R2/Bauart nur über Geräte mit Strom des Tages, §4.2 Fall 1
> und N-441 aus den Monats-Fakten des Monats für die anlagenweite Zahl; je Funktion der Grund aus der Tages-Deckung
> von `_funktions_deckung` — N-441 wirkt dort nicht) · `_schranke_und_kasten` (E1b: die Gegenrichtung am Tag gezählt,
> W-18-Kurzformen, Systemarbeitszahl) · `_arbeitszahl_je_funktion` (N-348, Kühlen) · `_antwort`. Proben: `test_rf71_tag_phasen.py`.

#### 3.5e Anzeige-Regeln der Betriebsart-Aufteilung (W-17 · W-17b · W-18)

Drei Regeln, die keine Formel sind und trotzdem in jede Sicht gehören:

| Regel | Kurz |
|---|---|
| **Zeit ist nicht additiv** (W-17) | `modus_abdeckung_h` wird über **Tage** summiert, über **Geräte** maximiert (`abdeckung_ueber_geraete`). Zwei Geräte mit je 18 h ergeben 18, nicht 36. |
| **Eine Aufteilung nennt ihre Grundmenge** (W-17b) | Der Balken bezieht sich auf `modus_strom_bezug_kwh`, die Kachel darüber auf `strom_kwh`. Weichen sie ab, steht die Zeile *„Aufgeteilte Menge"* darunter. |
| **Ein fehlender Wert nennt seinen Grund** (W-18) | Drei unterscheidbare Zustände (`core/tageswert_grund.py`): kein Zähler · zugeordnet, aber für diesen Tag ohne Zählerstände · Zählerrücksprung. **Der Grund wird hergeleitet, nie behauptet** — `arbeitszahl(waerme_fehlt_grund=…)` nimmt ihn entgegen, weil der Layer ihn nicht kennen kann. |

#### 3.5f Wetternormierung — Strom je Heizgradtag (SOLL §4.1, 12.09.2026)

**Layer:** `core/berechnungen/heizgradtage.py` · **Eingabe-Builder:**
`services/mitteltemperatur.py::lade_heizgradtage_je_monat` · **Anzeige:** Komponenten-Hub →
Wärme/Klima → Vergleich, Achse *Saison*.

```
HDD_Tag   = max(0; 15 °C − Tagesmittel der Außentemperatur)     # Heizgrenze = HEIZGRENZE_C
Kd_Monat  = Σ HDD_Tag über die Tage MIT Temperatur
kWh/Kd    = Σ Heizstrom (F5) ÷ Σ Kd   über ein Saison-Fenster
```

**Der Zähler ist der getrennt gemessene Heizstrom** (`strom_heizen_kwh`, im Hub als
`jaz_je_monat[].heizen_nenner_kwh`). Warmwasser geht nie ein — es hängt nicht vom Wetter ab —, der
Gesamtstrom nie, weil er es enthält. Ein aus dem Betriebsmodus abgeleiteter Heizstrom ist eine
**Verteilung** und kein Zähler (dieselbe Kategorie wie SOLL-§9-E7); ein *gemessener*
Betriebsart-Zähler *Heizen* scheidet zusätzlich aus, weil er den Warmwasser-Strom enthält
(`MESSBARE_MODI`, N-336).

**Die Vorrangkette des Nenners ist KÜRZER als die der Ø-Anzeige** (Entscheid K-2): Stufe 1
(Stundenmittel) und Stufe 2 (Tages-Min/Max) ja, **Stufe 3 (gepflegter
`Monatsdaten.durchschnittstemperatur`) nein**. `max(0; 15 − T)` ist **konvex** — in einem
Übergangsmonat mit Tagen beidseits der Heizgrenze unterschätzt der Weg über den Monatsmittelwert die
Summe. Ein Monat, der nur einen gepflegten Ø trägt, bekommt deshalb keine Kd, sondern den Grund.

**Die Zahl ist eine SAISON-Größe, nie ein Monatsquotient** (Entscheid K-3): Grundlast,
Warmwasser-Beimischung und Takt-Verluste skalieren nicht mit den Heizgradtagen und dominieren den
Übergangsmonat; im Sommer gibt es gar keinen Nenner (0 Kd). Über ein Saison-Fenster verschwindet der Effekt. Die
Fenster-Summe wird **neu gerechnet, nie gemittelt** (SOLL §5), und ein Monat geht nur ein, wenn er
**Heizgradtage und Heizstrom** trägt.

**Wo nichts steht, steht der Grund** (SOLL §3.3/S3): keine Temperaturreihe · Reihe jünger als die
Verbrauchshistorie (mit dem Monat ihres Beginns) · kein getrennt gemessener Heizstrom · Fenster ohne
Heizgradtage. **Eine normierte Arbeitszahl gibt es nicht** — sie ist bereits ein Quotient.

#### 3.5g Steuerungs-Sensoren der Wärmepumpe (HA-Export E2/P4/P7/P8)

**Orchestrator:** `api/routes/ha_export/investition_sensoren.py::_wp_steuerung_und_plan` (je Wärmepumpe, gerufen von
`_wp_sensoren`; Phasen RF-76) · **gemeinsamer Eingang:** der Fenster-Kontext
`services/ha_export_fenster.py::FensterKontext` (einmal je Anlage aus Prognose, Preis und Bezugspreisen) · **Formeln:**
`core/berechnungen/fenster.py` (`bestes_fenster`, `kosten_profil`, `verteile_auf_guenstigste`) über
`ha_export_fenster.fenster_fuer_menge` · **Anwender-Referenz:** `docs/SENSOR-REFERENZ.md`, «Stufe 3 je Gerät — Fenster mit
Betrag». Hier wird **kein** Fenster gerechnet — die Phasen sagen nur, welche Menge, welche Dauer und welche Frist für
dieses Gerät gilt. Slots liegen auf der backward-Achse (Slot `h` deckt `[h−1, h)`, s. «Backward-Slot-Konvention»).

| Phase (Code-Ort) | Sensor | Regel |
|---|---|---|
| E2 `_warmwasser_betrieb` | `wp_warmwasserbetrieb` | an, wenn der live gelesene Betriebsmodus (`modus_map`, #398) Warmwasser ist; ohne Modus-Zuordnung **kein** Sensor |
| P4 `_warmwasser_fenster` | `wp_warmwasser_fenster_ab` | s. Formelblock; ohne Menge oder ohne Fenster kein Sensor |
| P7 `_heizfenster` | `wp_heizfenster_stunden` | günstigste Stunden der erwarteten Heizzeit; ohne WP-Stundenprofil (N-332) oder ohne Verteilung kein Sensor |
| P8 `_kuehlfenster` | `wp_kuehlfenster_ab` | Kühl-Zähler **und** Kühlstrom-Menge; Frist = Spitzen-Slot der Temperatur |

Ohne Fenster-Kontext (kein Preis **und** kein Überschuss) entsteht nur E2.

```
P4  Monate     = die letzten 3 abgeschlossenen Monate (_MENGE_MONATE)
    Menge      = Σ wp_strom_warmwasser (imd_typ_beitrag, gemessen)        wenn ein Monat gemessen ist UND Σ > 0
               = Σ modus_strom_zeile(…).warmwasser_kwh (abgeleitet)       sonst                        # F-56
    je_Tag     = Menge ÷ Σ Kalendertage dieser Monate (nur Monate mit Zeile)
    Fenster    = fenster_fuer_menge(ctx, je_Tag, dauer_h = 2,
                                    frist_slot = min(24, ctx.frist_slot oder 24))                     # N-544
    kosten_cent             = round(Fenster.kosten_cent_kwh × je_Tag)
    ersparnis_cent_vs_jetzt = round(−Fenster.delta_vs_jetzt × je_Tag)      (None ohne Vergleich)

P7  Heizzeit   = Slots i mit WP-Profil[i] > 0 und i ≥ ctx.jetzt_slot
    Verteilung = verteile_auf_guenstigste(ctx.kosten, WP-Profil, Heizzeit)  # gleiche Menge, günstigere Stunden
    Wert       = Anzahl der gewählten Slots;  guenstige_heizstunden = "(h−1) % 24 : 00" je Slot h  # N-544: Beginn
    ersparnis_cent_vs_profil = round(Verteilung.ersparnis_cent);  heizzeit_stunden = |Heizzeit|

P8  Bedingung  = kuehl_je_monat nicht leer  ∧  hat_kuehl_zaehler(Gerät, Zeilen, Mapping, Quellen)   # Zähler, keine Kältemenge
    je_Tag     = Σ Kühlstrom der letzten 3 abgeschlossenen Monate ÷ Σ Kalendertage derer davon mit Kühlstrom-Eintrag
    Spitze     = Slot der höchsten Temperatur in ctx.temperatur_c[0 … 24]
    Fenster    = fenster_fuer_menge(ctx, je_Tag, dauer_h = 2, frist_slot = Spitze)
                 nur wenn je_Tag > 0 und Spitze ≥ ctx.jetzt_slot                                    # N-544: Frist = Spitze
    temperatur_max_um = "Spitze % 24 : 00" (Zeitpunkt, kein Slot-Beginn); ueberschuss_kwh_im_fenster = Σ Überschuss[ab … bis)
```

**Warum je Gerät und nicht aus den Monats-Fakten:** `WpFakten.strom_warmwasser_kwh` ist eine anlagenweite Summe über
alle Wärmepumpen; P4 liest deshalb die Gerätezeilen über `imd_typ_beitrag`, dieselbe Lesetür, die die Monats-Fakten
benutzen (P10-Eintrag `_warmwasser_fenster` in `P10_PER_INVESTITION_PHASE`, Lader `calculate_investition_sensors`).
`herkunft` sagt dem Anwender, ob die Menge gemessen oder abgeleitet ist — beides trägt das Fenster. **Kosten** sind der
effektive Ø-Preis des Fensters (Überschuss eingerechnet, Preis der Verwendung) × Menge, **Ersparnis** der Abstand zum
Kostenwert des laufenden Slots (`ctx.jetzt_slot`) × Menge. P7 ist eine Obergrenze: wie weit eine Verschiebung trägt, entscheidet die Regelung
der Wärmepumpe (`verteile_auf_guenstigste`, Docstring).

### 3.6 ROI & Amortisation

**Funktion:** `berechne_roi()` in `core/calculations.py`
**Nenner-SoT:** `core/berechnungen/kapitalrechnung.py`

> **Warum eine Zahl dort steht, wo sie steht:**
> [`docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md`](KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md) — die Entscheidungen samt
> den **verworfenen** Alternativen und den häufigen Einwänden mit Antwort. Dieses Kapitel nennt die Formeln, jenes die
> Begründung.

```
Relevante_Kosten     = Anschaffungskosten - Alternativkosten
Netto_Einsparung     = Jahres-Einsparung - Betriebskosten_Jahr
ROI (%)              = Netto_Einsparung / Relevante_Kosten * 100
Amortisation (Jahre) = Relevante_Kosten / Netto_Einsparung
```

Wobei `Betriebskosten_Jahr` = `Investition.betriebskosten_jahr` (Wartung, Versicherung etc., Default: 0).

**Gesamt-Zeile** (Auswertungen → ROI, `investitionen/roi.py::_gesamt_zeile`, N-774):

```
Gesamt_Einsparung          = Σ angezeigte Jahres-Einsparung der Zeilen (− USt bei Regelbesteuerung, §3.7)
Betriebskosten_unbewertet  = Σ Betriebskosten_Jahr der Zeilen mit detail.nicht_bewertet
Gesamt-ROI (%)             = (Gesamt_Einsparung − Betriebskosten_unbewertet) / Gesamt_Kapitaleinsatz * 100
Gesamt-Amortisation (J.)   = Gesamt_Kapitaleinsatz / (Gesamt_Einsparung − Betriebskosten_unbewertet)
```

Eine **nicht bewertete** Zeile (Wärmepumpe ohne Wärmebedarf, Wallbox/Sonstiges ohne „Ertrag/Jahr") zeigt in der Spalte
*Jahres-Einsparung* „—" und trägt **0** zur Spaltensumme `gesamt_jahres_einsparung` bei — nicht `0 − Betriebskosten` (N-258:
eine Zahl in der Einsparungs-Spalte behauptete sonst eine negative Ersparnis eines Geräts, das eedc gar nicht bewertet). Ihre
Betriebskosten fallen trotzdem an: sie gehen als eigenes Argument `betriebskosten_jahr` in den Gesamt-`berechne_roi` und als
negative Zeile `ErsparnisZeile(Zeilenjahr, −Betriebskosten)` in die Kalender-Treppe, damit Dauer und Break-Even-Jahr dieselbe
Rechnung meinen. Bewertete Zeilen tragen ihre Betriebskosten schon in ihrer Netto-Einsparung und werden **nicht** noch einmal
abgezogen. Die Annahme-Zeile `amortisation_annahme` („inkl. N €/Jahr Betriebskosten") nennt die Summe **aller** Zeilen
(`gesamt_betriebskosten`) und stimmt damit mit der Zahl überein. PV-System- und Orphan-Zeilen (`roi_pv.py`) kennen kein `nicht_bewertet`. Gesichert durch
`test_n774_gesamt_roi_betriebskosten_unbewertet.py` (**Probe**, mit Gegenfall ohne unbewertete Zeilen).

**WICHTIG - Zwei verschiedene ROI-Metriken:**

| Metrik | Wo angezeigt | Formel | Bedeutung |
|--------|-------------|--------|-----------|
| **Rendite** (`jahres_rendite_prozent`) | Antwortfeld von `/cockpit/uebersicht`; angezeigt nur im Jahresbericht-PDF („Rendite") | Kumul. Ersparnis / Relevante Kosten * 100 (Einzeljahr: Investitionen bis 31.12., auch vorher stillgelegte; das PDF druckt genau diesen Nenner als Zeile „Investition Mehrkosten", N-731) | Wie viel % bereits amortisiert (kumuliert) |
| **ROI p.a.** | Auswertungen → ROI (pro Komponente) | Jahres-Einsparung / Relevante Kosten * 100 | Rendite pro Jahr |
| **Amortisations-Fortschritt** | Auswertungen → ROI (Kachel), Jahresbericht-PDF (Einzeljahr: Stand 31.12.) | Bisherige Erträge / Kapitaleinsatz * 100 | Kumulierter Fortschritt |

> **Ein Nenner für alle drei (N-137).** „Relevante Kosten" sind die **Mehrkosten**
> `Σ max(0, anschaffungskosten_gesamt − anschaffungskosten_alternativ)` — SoT
> `core/berechnungen/investitionskosten.py::relevante_kosten_aus_investitionen`, identisch mit der
> USt-Bemessungsgrundlage (§3.7), in ROI-Sicht, Aussichten und Cockpit dieselbe Summe. Gepflegt wird die Spalte
> `anschaffungskosten_alternativ`, die der Daten-Checker mit WARNING einfordert.
>
> **Ohne gepflegte Alternativkosten zählen die Vollkosten.** eedc setzt keine Annahme (Festbetrag) ein — die
> Amortisation entspricht den Daten, die tatsächlich da sind. Gesichert durch `test_amortisation_nenner_symmetrie.py`
> (**Regression**, drei Sichten auf einer Fixture mit Alternativkosten ≠ Festannahme).

> **Sonstige Positionen: Zeitraum-Bilanz ↔ Kapitalrechnung (F-19).**
> Eine Reparatur ist zweierlei, je nach Frage — und dasselbe gilt für eine Förderung:
>
> | Frage | Sicht | Wo die Position steht |
> | --- | --- | --- |
> | „Was hat der Monat gekostet und eingebracht?" | Cockpit, Monatsbericht, Jahresbericht-PDF, CSV-Export, Sensor `netto_ertrag_euro` | **Ertragsseite** — Aufwand bzw. Ertrag des Zeitraums, unverändert |
> | „Wie lange dauert es, bis sich das rechnet?" | ROI, Amortisation, HA-Sensoren, Finanzbericht-PDF | **Kapitaleinsatz** (Nenner): Ausgabe **+**, Ertrag **−** |
>
> **Warum:** eine einmalige Ausgabe, im Zähler über die Laufzeit **annualisiert**, verlängert die Amortisation
> unverhältnismäßig und lässt die Zahl jedes Folgejahr weiterdriften, ohne dass etwas passiert; im **Nenner** zählt sie
> einmal. Bei laufenden Kosten (Wartung) liefern beide Rechnungen dasselbe Ergebnis.
>
> **Sonstige *Erträge* stehen ebenfalls im Nenner** (Bauschritt 7 —
> die Vollkostenrechnung ist damit vollständig). Eine Position im
> Monatsabschluss ist per Form **einmal** geflossen; sie zu mitteln und in
> jedes künftige Jahr zu verlängern unterstellt eine Wiederholung, die niemand
> behauptet hat (spiegelbildlich zur Ausgabenseite). Eine
> THG-Quote oder eine Förderung **mindert deshalb das eingesetzte Kapital**,
> statt eine künftige Jahres-Ersparnis zu erhöhen. In der **Zeitraum-Bilanz**
> bleibt sie unverändert stehen — dort ist sie ein Ertrag des Zeitraums.
>
> **Warum nicht schon mit F-19:** ein *wiederkehrender* Ertrag `E` im Nenner
> ergibt `(K − E·n) ÷ Z`, eine Zahl, die jedes Jahr schrumpft und irgendwann
> negativ wird. Wiederkehrende Erträge haben deshalb einen eigenen **Ort im
> Zähler**, zweimal: **„Ertrag/Jahr
> (€)"** an der Investition (Wallbox/Sonstiges) und **„Einspeise-Erlös (€)"**
> bei *Sonstiges/Erzeuger*, per HA-Sensor monatsgenau befüllbar. Praktischer
> Fall: wer zwei Wechselrichter mit **verschiedenen Einspeisetarifen** betreibt
> (eedc kennt genau **einen** Einspeisesatz je Anlage), pflegt den zweiten
> Erlös dort — beide Felder sind wiederkehrend gemeint und wirken im **Zähler**.
> Die monatliche Handpflege bleibt möglich, beschreibt aber die Vergangenheit
> und mindert den Kapitaleinsatz; der Daten-Checker weist auf den
> besseren Ort hin, wenn derselbe Posten mehrfach auftaucht.
>
> ⚠ **Der Nenner kann dadurch unter die Anschaffungskosten fallen** — das ist
> die Aussage: eine Förderung ist Geld, das nie eingesetzt wurde. Fällt er auf
> ≤ 0, zeigt eedc **keine** Amortisationsdauer und keinen ROI statt einer
> negativen Zahl.
>
> Die Unterscheidung kostet **keine zusätzliche Pflege**: `typ: ertrag|ausgabe`
> wird beim Erfassen ohnehin gewählt, und der Ort sagt die Häufigkeit.
>
> **Anlagenweite Positionen** (Monatsabschluss ohne Komponente) haben **keine** Investition und stehen
> deshalb auf keiner ROI-Zeile: sie wirken nur auf die Gesamt-Zahlen — `gesamt_sonstige_ausgaben_euro`/
> `gesamt_sonstige_ertraege_euro`, Gesamt-Kapitaleinsatz, Gesamt-ROI und die Kalender-Treppe im Jahr
> ihres Monats (Bauschritt 4). Gelesen über die Monats-Fakten (`sonstiges.anlage_ausgaben_euro`/
> `anlage_ertraege_euro`, ohne die schon gezählten Beträge der Komponenten); Code
> `investitionen/roi_eingaenge.py::_anlagenweite_positionen` und `roi.py::_gesamt_zeile`.
>
> **Und der Kapitaleinsatz ist nicht die USt-Bemessungsgrundlage.** Die bleibt
> bei den reinen Mehrkosten (§ 3 Abs. 1b UStG, [§3.7](#37-ust-auf-eigenverbrauch)) —
> weder eine Reparatur noch eine Förderung gehört dort hinein. Gesichert durch
> `test_kapitaleinsatz_vier_sichten_symmetrie.py` (**Regression**, vier Sichten +
> beide Seiten des Bruchs, **beide Erfassungsorte** — an der Investition und auf
> der Monatsdaten-Zeile).

> **Jede Ersparnis wird mit IHRER eigenen Laufzeit hochgerechnet.** Die
> HA-Sensoren `jahres_ersparnis_euro`, `roi_prozent` und `amortisation_jahre`
> teilen nicht alles durch die Monatszahl der *Anlage*: jeder Posten (auch Wärmepumpen- und E-Auto-Ersparnis)
> bringt seine eigene Monatszahl mit — eine nachgerüstete Komponente wird nicht verdünnt, während ihre Kosten voll im
> Nenner stehen —, und der Sensor-Rechenweg schreibt sie aus.

**Und zwei verschiedene Amortisations-Angaben — Modell neben Messung:**

| Angabe | Wo | Grundlage |
|---|---|---|
| **Amortisationsdauer** — Jahre **und Break-Even-Jahr** | Auswertungen → ROI | **MODELL:** `Relevante Kosten ÷ prognostizierte Jahres-Einsparung`, konstant hochgerechnet. Anker des Kalenderjahres ist das **früheste Anschaffungsjahr** der Investitionen; ohne gepflegtes Anschaffungsdatum bleibt es beim Jahres-Index ohne Jahreszahl. |
| **Amortisations-Fortschritt** | Auswertungen → ROI (Kachel daneben), Jahresbericht-PDF | **MESSUNG:** die tatsächlich erzielten Netto-Erträge seit Inbetriebnahme, geteilt durch dieselben relevanten Kosten. Formel-SoT `core/berechnungen/amortisation.py`; der Jahresbericht-PDF übernimmt die Zahl der Kachel (`get_finanz_prognose`, N-699): im Gesamtzeitraum bis heute, im **Einzeljahr kumuliert bis zum 31.12. des Berichtsjahres** (`stichtag`: Investitionen mit Anschaffung bis zum Stichtag, Monatswerte und Monats-Fakten bis zu seinem Monat — ein Stand 31.12.2024 kennt kein 2025 gekauftes Auto). |
| **Amortisation (Prognose)** | PDF-Finanzbericht | **Dieselbe Zahl wie *Auswertungen → ROI*** — sie kommt aus dem ROI-Dashboard, damit alle vier Sichten dieselbe Zahl nennen (auch neben dem pflegbaren **„Ertrag/Jahr"** an Wallbox/Sonstiges). |
| **Amortisation (HA-Sensor)** | `sensor.*_amortisation_jahre` | `Kapitaleinsatz ÷ Jahres-Ersparnis`, wobei die Jahres-Ersparnis aus der **gemessenen Historie** annualisiert wird — je Posten mit seiner eigenen Laufzeit. Trägt denselben Nenner wie die drei anderen, aber einen Ist- statt Modell-Zähler; die Zahl liegt deshalb je nach Anlage über oder unter der Modell-Sicht. |

> Die beiden ersten beantworten dieselbe Frage verschieden — „laut Rechnung in 9,2 Jahren" gegen
> „4.800 € von 12.000 € sind drin". Das ist gewollt und in beiden Tooltips ausgeschrieben; Bedingung
> ist der **gemeinsame Nenner**, sonst ließen sich die Zahlen nicht ineinander überführen.

> **Die Break-Even-Kurve ist eine Kalender-Treppe (N-525).** Jede ROI-Zeile
> zählt ihre Mehrkosten und ihre Netto-Jahres-Einsparung ab ihrem eigenen Anschaffungsjahr (ein
> PV-System ab seiner ersten Komponente, seine Kosten je Komponente gestuft), sonstige Ausgaben
> erhöhen und sonstige Erträge mindern den Kapitaleinsatz im Jahr ihrer Buchung. Das
> **Break-Even-Jahr** ist das erste Jahr, ab dem die kumulierte Einsparung den kumulierten
> Kapitaleinsatz dauerhaft nicht mehr unterschreitet — eine spätere Anschaffung kann eine schon
> amortisierte Anlage wieder unter die Linie drücken. Formel-SoT
> `core/berechnungen/kapitalrechnung.py::amortisations_verlauf`; der Client zeichnet die Reihe.
> Die **Dauer** in Jahren bleibt Modell A (Kapitaleinsatz ÷ heutige Jahres-Einsparung); Dauer und
> Jahr fallen nur bei einer Anlage zusammen, die auf einmal gebaut wurde.

> **Jede Dauer nennt ihre Annahme.** Der Fortschritt unterstellt
> nichts, die Dauer **muss** etwas unterstellen — gewählt ist **Modell A**
> („es geht nie wieder etwas kaputt", Begründung und die verworfenen Modelle B/C
> in [`KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md`](KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md) §5).
> Formuliert wird der Satz **einmal**, im Layer-SoT
> `core/berechnungen/kapitalrechnung.py::annahme_dauer_text`, und von allen
> Ausgabewegen abgeholt: ROI-Dashboard (gesamt **und** je Zeile), PDF-Finanzbericht,
> HA-Sensor `amortisation_jahre` (dort im Rechenweg-Attribut — ein Sensor hat
> keinen Tooltip) und die **Restlaufzeit** der Finanz-Prognose
> (`amortisation_prognose_jahr`): sie steht zwar in der *gemessenen* Kachel,
> rechnet aber den offenen Rest mit der Jahres-Prognose hoch und ist damit selbst
> eine Dauer-Aussage. Das Client-Pendant `lib/amortisationAnnahme.ts` trägt nur den
> einen Fall, für den es keine Backend-Zahl gibt: die Wallbox-Dauer im
> Komponenten-Hub, die aus `Anschaffung ÷ Ersparnis` im Client entsteht.
>
> ⚠ **Der Satz richtet sich nach den Daten, nicht nach dem Modellnamen.** Sobald
> `betriebskosten_jahr` gepflegt ist, rechnet eedc **Modell C** — der Betrag steht
> als Abzug im Zähler, und „ohne künftige Instandhaltung" wäre dann eine falsche
> Aussage über die eigene Rechnung. Gesichert durch
> `test_konzept_wirtschaftlichkeit_konformitaet.py::test_schritt6_*`
> (**Regression** — die vier Quellen werden namentlich aufgerufen).

### 3.7 USt auf Eigenverbrauch

**SoT:** `core/berechnungen/ust_eigenverbrauch.py` (Berechnungs-Layer, ADR-001); welche Investitionen, Monate und
Mengen eingehen, wählt **ein** Eingang für alle Sichten: `services/ust_satz.py` (N-601)
**Bedingung:** Nur wenn `Anlage.steuerliche_behandlung == "regelbesteuerung"`

Die Selbstkosten je kWh sind eine **Jahresgröße**. Gerechnet wird deshalb **je
Kalenderjahr** und summiert — auch wenn die Sicht einen mehrjährigen Zeitraum zeigt (N-130):

```
Bemessungsgrundlage  = Σ max(0, anschaffungskosten_gesamt − anschaffungskosten_alternativ)
Abschreibung_Jahr    = Bemessungsgrundlage / 20        (20 Jahre lineare AfA)

je Kalenderjahr j:
  Jahreskosten_j     = (Abschreibung_Jahr + Betriebskosten_Jahr) × Monate_j / 12
  Selbstkosten_kWh_j = Jahreskosten_j / PV_Erzeugung_j
  USt_j              = Eigenverbrauch_j × Selbstkosten_kWh_j × USt_Satz / 100

USt_Eigenverbrauch   = Σ USt_j
```

| Feld | Quelle |
|------|--------|
| `Bemessungsgrundlage` | **Mehrkosten** je Investition, geklemmt bei 0 — nicht die Vollkosten (N-129). Der volle Kaufpreis eines E-Autos gehört nicht in die Selbstkosten des PV-Stroms; maßgeblich ist, was er gegenüber der Alternative gekostet hat. Es zählen die im Jahr `j` aktiven Investitionen (`ist_aktiv_im_zeitraum`, N-601) |
| `Betriebskosten_Jahr` | Σ(Investition.betriebskosten_jahr) derselben im Jahr `j` aktiven Investitionen (N-601) |
| `Monate_j` | Monate des Jahres `j` im ausgewerteten Zeitraum, die eine Zählerzeile mit erfassten Netzfeldern (N-736) und einen aktiven Erzeuger tragen (1–12). Ein angeschnittenes Jahr trägt anteilig AfA — sonst stünden zwölf Monate Abschreibung gegen sieben Monate Ertrag |
| `PV_Erzeugung_j` | PV-Erzeugung derselben Monate aus den Monats-Fakten |
| `Eigenverbrauch_j` | Σ der Monats-Eigenverbräuche derselben Monate, ohne bewertbare Wandlungsverluste (N-588) |
| `USt_Satz` | `Anlage.ust_satz_prozent` (DE: 19, AT: 20, CH: 8.1) |

**Auswirkung:** USt wird vom `Netto_Ertrag` abgezogen — Cockpit, Jahresbericht-PDF,
HA-Export, Aussichten und *Auswertungen → Finanzen* + *Tabelle* (N-22).

> **Je Monat verteilt (Auswertungen):** die Formel ist linear im Eigenverbrauch,
> deshalb trägt jeder Monat `EV_m × Selbstkosten_je_kWh × USt_Satz`. Der Nenner der
> Selbstkosten ist die **Jahres**-PV, damit Σ der Monatsbeträge exakt der
> Jahresbetrag bleibt. **Auf Tagesebene gibt es die Größe nicht** — Investitionssumme
> und Jahresertrag lassen sich keinem Tag zuordnen; bei Regelbesteuerung gilt daher
> Σ Tage ≠ Monat beim Netto-Ertrag (dieselbe bewusste Asymmetrie wie bei CO₂).
>
> **Ein Eigenverbrauch für alle Sichten (N-131/N-375):** der **Netzpunkt**-Eigenverbrauch — `finanz_zeile_eingabe`
> rechnet ihn aus `erzeugung.hinter_zaehler_kwh`, also inklusive eines sonstigen Erzeugers (Mini-BHKW).
>
> ⚠ **Benannte Grenze (N-376):** Die Selbstkosten je kWh teilen die
> Kosten **aller** Investitionen durch die Erzeugung der **PV allein** — Zähler und Nenner
> zählen verschiedene Grundgesamtheiten.

### 3.8 CO2-Bilanz

**Endpoint:** `GET /api/cockpit/nachhaltigkeit/{anlage_id}`
**Sichten:** Cockpit → Jahr/Gesamt, Block „CO₂-Bilanz" ·
Auswertungen → CO₂, Blöcke „CO₂-Bilanz & Wirkung" und „CO₂-Amortisation".

#### Eine Definition — wer sie bildet und wer sie liest

| Rolle | Ort |
| --- | --- |
| **Bildet** die Zahl (einzige erlaubte Stelle) | `core/calculations.py::berechne_co2_bilanz` (ADR-001, DI-2) |
| **Liefert** sie je Monat aus | `GET /api/cockpit/nachhaltigkeit/{id}` (`co2_pv_kg` · `co2_wp_kg` · `co2_emob_kg` · `co2_gesamt_kg` · `co2_kumuliert_kg`) |
| **Zeigt** sie | Cockpit → Jahr (`v4/JahrCo2Chart.tsx`) · Auswertungen → CO₂ (`v4/AuswertungenCo2V4.tsx`, über `useAuswertungBasis().co2`) · HA-Sensor „CO₂ Einsparung" · PDF-Jahresbericht · WP-Dashboard |
| **Rechnet nicht** | der Client. `CO2_FAKTOR_KG_KWH` darf dort nur *angezeigt* werden (`× 1000` → g/kWh); gewächtert von `npm run check:co2-roh` (Baseline 0) |

> **Keine Sicht rechnet `Erzeugung × 0,38` (N-21, N-647).** Das schriebe auch der **eingespeisten** kWh die volle
> Netzstrom-Vermeidung gut und kennte weder Wärmepumpe noch E-Mobilität. Die Tagestabelle
> (`services/energie_profil/tage_werte.py`), die PV-Zeile in **Auswertungen → ROI** (`investitionen/roi_pv.py`) und die
> Monatskennzahlen von `GET /monatsdaten/{id}` (`core/calculations.py::berechne_monatskennzahlen`) nehmen
> `berechne_co2_bilanz(...).co2_pv_kg` auf dem Eigenverbrauch ohne Wandlungsverluste (§1); die Monatstabelle
> (`pages/auswertung/types.ts`) liest `co2_pv_kg` aus diesem Endpoint. Die ROI-Zeile rechnet die **Module** (das Balkonkraftwerk hat eine
> eigene Zeile), hochgerechnet auf zwölf Monate wie ihre Ersparnis. Gewächtert von ADR-002/P15: jede
> `× CO2_FAKTOR_STROM_KG_KWH` in Routen und Services trägt den Beleg oder steht klassifiziert (Komponenten-Bilanzen
> DI-1, die synthetische BKW-Pauschale).

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
CO2_WP    = (WP_Wärme / 0.9 * 0.201) - ((WP_Strom - Kühlstrom) * 0.38)  (vs. Gasheizung; Kühlstrom ersetzt keine Heizung, #263 K-2)
CO2_E-Mob = (Benzin_L * 2.37) - ((Netz_Ladung + PV_Ladung) * 0.38)  (vs. Benziner — die ganze Heimladung, N-672)
            - Fossil_getankt_L * 2.37                               (Plug-in-Hybrid, #331; sonst 0)
CO2_gesamt = CO2_PV + max(0, CO2_WP) + max(0, CO2_E-Mob)
```

> ⭐ **Eine kWh ist einmal CO₂ (N-672).** `CO2_PV` schreibt den ganzen Eigenverbrauch als vermiedenen
> Netzstrom gut — die PV-Ladung des E-Autos steckt darin und gilt in `CO2_E-Mob` nicht noch einmal als CO₂-frei.
> Dieselbe Regel wie beim Geld (§3.2) und bei der Wärmepumpe (ganzer WP-Strom, N-459).

> **Kanonische CO₂-Helfer (SoT `core/calculations.py`, DI-1/DI-2):** Diese Bilanz läuft über **genau eine**
> Helfer-Familie — `berechne_co2_bilanz` (setzt PV + WP + E-Mob zusammen), intern `co2_wp_ersparnis_kg`
> (WP: vermiedenes Gas MINUS WP-Strom-CO₂; der **Gas-Wirkungsgrad η_gas = 0,90** kommt aus
> `WP_WIRKUNGSGRAD_GAS_DEFAULT`) und `co2_emob_ersparnis_kg`. **Cockpit-CO₂-Kachel, HA-Export-Sensor
> „CO₂ Einsparung", WP-Dashboard und der PDF-Jahresbericht** rufen dieselben Helfer auf und zeigen daher
> **denselben Wert**. Die WP- und E-Mob-Komponente werden für die Summe bei 0 geklammert (negative Einzelwerte
> kürzen die Gesamtbilanz nicht). Erzeuger unter **„Sonstiges"** (BHKW, Windrad, Wasserkraft) speisen hinter
> denselben Zähler: ihr selbst verbrauchter Strom steckt im Eigenverbrauch und zählt deshalb — wie im Geldwert
> (§3.2) — auch im CO₂-PV-Anteil als **vermiedener Netzstrom** (0,38 kg/kWh); CO₂ folgt der Geldregel (P15).
> Die Emission des Erzeugers selbst (z. B. das Gas eines BHKW) zieht eedc **nicht** ab, weil es sie nicht kennt,
> und am Hauszähler lässt sich der Eigenverbrauch nicht in PV- und BHKW-Anteil trennen. Für ein BHKW ist die
> Zahl deshalb „vermiedener Netzstrom", keine Klimabilanz des BHKW.

#### Äquivalente

**Eine Formel, ein Ort (DI-2, Päckchen Y 9.11.2026):** `core/berechnungen/co2_aequivalente.py::co2_aequivalente(co2_kg)` bildet
aus einer CO₂-Menge vier Anschauungsgrößen; `None` und negative Mengen ergeben 0.

```
Bäume          = CO2 / KG_CO2_JE_BAUM_JAHR                         (12,5 kg je Baum und Jahr)
Auto-km        = CO2 / KG_CO2_JE_AUTO_KM                           (0,12 kg je km = 120 g/km)
Flug-km        = CO2 / KG_CO2_JE_FLUG_KM                           (0,23 kg je Flug-km)
Flüge          = CO2 / (KG_CO2_JE_FLUG_KM × KM_JE_KURZSTRECKENFLUG) (0,23 kg/km × 1000 km = 230 kg je Kurzstreckenflug)
```

Flug und Flug-km hängen an denselben zwei Konstanten; die 1000 km sind die der Kachel-Unterzeile «à 1000 km». **Herkunft der
Faktoren — eine Annahme:** die Anschauungswerte der Auswertung seit dem 3.2.2026 (Commit `a3884af5c`: «Ein Baum bindet ca.
12.5 kg CO2/Jahr», «ca. 120g CO2/km»); eine Literaturquelle nennt weder der Code noch die Historie. Es sind Größenordnungen zum
Veranschaulichen, keine Bilanzgrößen.

`GET /api/cockpit/nachhaltigkeit` liefert je Monat `co2_aequivalente` (`baeume`, `auto_km`, `fluege`, `fluege_km`, ungerundet,
aus dem angezeigten Monatswert `co2_gesamt_kg`), gesamt `aequivalent_baeume`, `aequivalent_auto_km`, `aequivalent_fluege_km`
(ganzzahlig abgeschnitten) und `aequivalent_fluege` (eine Stelle) sowie einmal `co2_faktoren` (die fünf Faktoren für
Methodik-Texte). *Auswertungen → CO₂* summiert die Monats-Äquivalente des gewählten Zeitraums — alle vier Größen sind
linear, die Summe der Monate ist das Äquivalent der Summe — und nimmt die Zahlen der Methodik-Texte aus `co2_faktoren`.
Bis Päckchen Y rechnete die Sicht mit eigenen Konstanten im Client und die Route mit ÷ 20 (Bäume) und ÷ 0,25 (Flug-km) —
zwei Faktorensätze; `aequivalent_baeume` und `aequivalent_fluege_km` rechnen seitdem mit den Faktoren der Auswertung. Gewächtert: `npm run check:co2-roh` Regel 2 (keine
Faktor-Konstante, keine CO₂-Größe × | ÷ Zahl außer `× 1000`, keine Literale 12,5/230 in CO₂-Dateien) und
`test_wurzelmuster_konformitaet.py::test_p15_co2_faktor_in_routen_und_services_nur_mit_beleg` (CO₂-Größe × | ÷ Zahl in
`api/routes/`).

### 3.9 PV-String SOLL-IST Vergleich

**Endpoint:** `GET /api/cockpit/pv-strings/{anlage_id}?jahr=`

#### Was eine „String"-Zeile ist — die Erzeuger-Abgrenzung (F-10)

> **Die Zeilen dieser Sicht sind PV-*Erzeuger*, nicht PV-*Module*.** Maßgeblich ist `PV_ERZEUGER_TYPEN` (SoT
> `core/berechnungen/spez_ertrag.py`) = `pv-module` **+** `balkonkraftwerk`. Ein Balkonkraftwerk trägt alles, was die Sicht braucht:
> kWp über `get_erzeuger_kwp` (beim BKW `leistung_wp × anzahl`), Ausrichtung und Neigung als eigene Formularfelder und ein eigenes
> PVGIS-SOLL (#367). Das gilt für alle Ausgaben der Sicht — `GET /pv-strings`, `GET /pv-strings-gesamtlaufzeit`, Abschnitt 10 des
> Jahresbericht-PDF und die Leertexte im Client (Klasse #236 — *ein Filter auf einer Schicht reicht nicht, wenn parallele Pfade
> existieren*).
>
> ⚠ **Die IST-Quelle ist je Typ eine andere, und das ist Absicht.** Ein `pv-module` holt seinen Wert aus
> `ErzeugungFakten.pv_je_modul` (P7-Auflösung); ein `balkonkraftwerk` steht dort **nicht**, sondern in
> `BkwFakten.erzeugung_je_investition`. Grund: die Σ von `pv_je_modul` ist `pv_module_kwh`, und die geht in die **ROI-Rechnung**, wo
> das Balkonkraftwerk eine **eigene** Zeile hat (`investitionen/roi.py::get_roi_dashboard`, innere `get_pv_erzeugung`) — läge es in
> beiden, zählte seine Erzeugung dort doppelt. Wer die Sicht erweitert, erweitert deshalb **nicht** `pv_je_modul`. Gewächtert in
> `tests/test_bkw_erzeuger_sichten_f10.py`.
>
> **PV-Module unter einem Balkonkraftwerk sind erlaubt — und zählen trotzdem nur einmal** (N-266,
> `models/investition.py::ERLAUBTE_PARENT_TYPEN`): das Balkonkraftwerk **tritt** Nennleistung, Erzeugung und Ausrichtung an seine
> Kinder **ab** (Selektor `core/berechnungen/erzeuger_traeger.py`, [ADR-002/P11](ADR-002-WURZELMUSTER.md)), seine AC-Grenze behält es.
> In der String-Sicht ist es damit keine eigene Zeile, seine Module sind es. ⚠ **Die Abtretung gilt je Monat** (N-613, N-614): hat das
> Balkonkraftwerk seine Module erst später bekommen, trägt es in den Monaten davor Erzeugung und kWp selbst — es steht dann in
> *Komponenten → PV-Strings* und im Abschnitt „String-Vergleich" des Jahresbericht-PDF als eigene Zeile für genau diese Monate, und im
> Verteilungsnenner des SOLL steht in jedem Monat entweder das Balkonkraftwerk oder seine Module, nie beide. Welcher Weg wann passt
> (Balkonkraftwerk allein, Balkonkraftwerk + PV-Module, Wechselrichter + PV-Module), steht in
> [HANDBUCH_EINSTELLUNGEN §3.5](HANDBUCH_EINSTELLUNGEN.md#35-balkonkraftwerk-mit-mehreren-ausrichtungen--und-wann-wechselrichter--pv-module).
>
> **Dieselbe Erzeuger-Abgrenzung gilt für die Community-Stammdaten** (`services/community_service.py`, §3.11): Neigung und Ausrichtung
> werden über beide Typen gemittelt, nur über die heute aktiven Erzeuger (erst `ist_aktiv_an(heute)`, dann der Selektor; ebenso
> Wallbox- und Balkonkraftwerk-Leistung; N-617) — der Community-Server rechnet nichts nach, eine falsche Ausrichtung misst die Anlage
> gegen die falsche Vergleichsgruppe.

#### SOLL-Berechnung (PVGIS)

> **Genau eine Prognose ist die aktive.** eedc bewahrt beliebig viele PVGIS-Abrufe einer Anlage auf;
> gelesen wird ausschließlich die als *aktiv* markierte — auch wenn das bewusst eine ältere ist
> (Nutzerwille, [Einstellungen → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)).
> Auswahlregel: `ist_aktiv == True`, `ORDER BY abgerufen_am DESC`, `LIMIT 1`; SoT
> `services/prognose_auswahl.py`, datenbankseitig gesichert durch einen partiellen Unique-Index
> (ADR-002/P5). Ist **keine** Prognose aktiv, bleibt die SOLL-Seite leer, statt eine beliebige zu zeigen.

> **Wann eine Prognose von selbst nachgezogen wird (#363).** Eine Prognose wird beim
> Abruf eingefroren; ändert sich die Anlage danach, rechnet jede SOLL-Sicht gegen eine Anlage, die
> es nicht mehr gibt (gemeldeter Extremfall: 357 MWh Jahres-SOLL für ein 2,4-kWp-Balkonkraftwerk).
> Der nächtliche Job `pvgis_aktualitaet` prüft deshalb je Anlage, **ob die aktive Prognose noch
> passt** — SoT `services/pvgis_aktualitaet.py`, dieselbe Funktion versorgt die Statusanzeige der
> Einstellungs-Kachel. Auslöser sind ausschließlich:
>
> | Auslöser | Vergleich |
> | --- | --- |
> | Nennleistung | Σ `get_erzeuger_kwp` der aktiven Erzeuger gegen `gesamt_leistung_kwp` |
> | Ausrichtung / Neigung | nach kWp gewichtet, wie im Speicherpfad |
> | Standort | `latitude`/`longitude` der Anlage |
> | Horizontprofil | hinzugekommen oder entfernt |
> | Strahlungsdatensatz | `raddatabase` der Zeile gegen den der konfigurierten API-Version |
>
> **Das Alter ist ausdrücklich KEIN Auslöser.** PVGIS rechnet auf einem abgeschlossenen Klimamittel
> (API v5_2 → PVGIS-SARAH2 2005–2020, v5_3 → PVGIS-SARAH3 2005–2023); bei unveränderten Eingaben
> liefert ein zweiter Abruf dieselbe Zahl, ein turnusmäßiger Abruf wäre Last ohne Wirkung. Die
> Systemverluste sind ebenfalls kein Auslöser, sondern werden in den Neuabruf **übernommen** — sie
> sind nirgends sonst gespeichert. Die abgelöste Prognose bleibt als inaktive Zeile erhalten.
>
> eedc fragt PVGIS mit der API-Version v5_3 (Strahlungsdatensatz SARAH3, #363); Bestandsprognosen ohne `raddatabase` werden genau
> einmal automatisch nachgezogen, danach rechnen alle Installationen auf derselben Grundlage.

> **Wann die AC-Kappung NICHT greift (F-11).** Die Grenze begrenzt, was ein Wechselrichter **ins Haus abgibt** — nicht, was die
> Module ernten. Hängt am **Träger der Grenze** ein **DC-gekoppelter** Speicher, läuft der Überschuss gleichstromseitig in den Akku,
> ohne je durch den Wechselrichter zu müssen; er ist dann **nicht verloren**, und eine Kappung des Erzeugungsprofils würde ihn
> wegrechnen. SoT `core/berechnungen/wr_kappung.py::_dc_speicher_traeger`.
>
> | Lage | Kappung |
> | --- | --- |
> | kein Speicher am Träger | **ja** (#347/#354 unverändert) |
> | **DC**-gekoppelter Speicher am Träger | **nein** — der Überschuss lädt den Akku |
> | **AC**-gekoppelter Speicher am Träger | **ja** — alles läuft durch den Wechselrichter |
> | Speicher ohne Zuordnung, oder an einem *anderen* Wechselrichter | **ja** — er kann den Überschuss dieses Erzeugers nicht aufnehmen |
>
> **Warum die IST-Größe die Ernte *vor* dem Speicher ist** — das entscheidet nicht der Hersteller,
> sondern die eigene Bilanz: `direktverbrauch = max(0, pv − einspeisung − speicher_ladung)`
> (§3.1). Die Speicherladung wird von der PV-Summe **abgezogen**, sie muss darin enthalten sein.
> Die [Sensor-Referenz](SENSOR-REFERENZ.md) sagt dasselbe in Worten, und der BKW-Akku-Kanon führt
> Ladung/Entladung als eigene Speicher-Investition daneben.
>
> **Die Kopplung eines Speichers** (`parameter.kopplung`, #351) liest `wr_kappung` für **SOLL**-Werte (Prognose-Kanon und
> PVGIS-Monatsprognose) — wer sie ändert, verschiebt sein SOLL. Auf der IST-Seite rechnet mit ihr nur der Messpunkt-Vertrag (iii) der
> Wandlungsverluste (N-588, §1: ein DC-gekoppelter Speicher sperrt den Abzug in Ersparnis, USt und CO₂); die Energiebilanz liest sie
> nicht.

**Mit Pro-Modul-PVGIS-Daten:**
```
SOLL_Monat = PVGISPrognose.module_monatswerte[modul_id][monat].e_m
```

**Fallback (ältere Prognosen — proportional nach kWp):**
```
kWp_Anteil = Modul_kWp / Gesamt_kWp
SOLL_Monat = PVGISPrognose.monatswerte[monat].e_m * kWp_Anteil
```

`Gesamt_kWp` sind die kWp, für die die aktive Prognose gerechnet ist (N-661; `PVGISPrognose.gesamt_leistung_kwp`,
`core/berechnungen/erzeuger_traeger.py::soll_nenner_kwp`) — in *Komponenten → PV-Strings*, *Auswertungen → Prognose* und im
Jahresbericht-PDF gleich; nur eine Prognose ohne gespeicherte kWp fällt auf die Σ der Strings zurück. Das saisonale Mittel
(„typischer Monat") der Gesamtlaufzeit folgt derselben Regel (N-683): das SOLL eines Strings ist das Mittel seines Monats-SOLL über die
Jahre, in denen er in diesem Monat **aktiv** war (Anschaffung, Stilllegung), mit demselben Nenner wie seine Jahreswerte; die
Anlagen-Zeile ist je Jahr die Σ der in diesem Monat aktiven Strings, über die Jahre gemittelt. Ein String ohne aktiven Monat hat dort
kein SOLL (0 wie sein IST-Mittel). Der Hinweis über der Sicht, die gespeicherte PVGIS-Prognose passe nicht zur Anlage, vergleicht die
Prognose-kWp mit den **heute aktiven** Strings (N-684). Der PDF-Jahresbericht nutzt denselben Weg (Pro-Modul-Werte vor kWp-Verteilung).

**Faire Vergleichsbasis:** SOLL wird NUR für Monate gezählt, die auch IST-Daten haben (kein aufgeblähtes SOLL bei Teil-Jahren). In
*Komponenten → PV-Strings* (Jahressicht) trägt ein Monat ohne IST-Wert die Zeile mit SOLL **0** (keine Abweichung, keine Performance
Ratio) und geht nicht in das Jahres-SOLL des Strings ein (`api/routes/cockpit/pv_strings.py::_string_im_jahr`). Dasselbe gilt im
Abschnitt „String-Vergleich" des Jahresbericht-PDF (N-616): beide Sichten nehmen „Monat mit Wert" aus derselben Auflösung
(`lade_pv_je_monat`, Quelle gemessen oder verteilt) und kürzen den Anschaffungs-/Stilllegungsmonat mit derselben Funktion
(`core/berechnungen/monatsfenster.py::soll_im_laufmonat`). Das PDF nennt an der Zeile „n von N Monaten", wenn es weniger als der
Berichtszeitraum sind. Sein spezifischer Ertrag ist im Einzeljahr IST ÷ kWp, im Gesamtzeitraum der saisonal gewichtete Jahreswert der
Cockpit-Kachel (`core/berechnungen/spez_ertrag.py::berechne_spez_ertrag_annualisiert`), je String über seine Monate und mit seinem
Monats-SOLL als Gewicht; ohne Erzeugung oder Nennleistung steht „–". Das IST je String kommt ebenfalls aus dieser Auflösung (N-620) —
auch für ein Balkonkraftwerk ohne eigenen Wert in einem Monat mit Anlagenwert: es bekommt den Anteil, den `lade_pv_je_monat` ihm gibt,
gekennzeichnet „geschätzt (kWp-Anteil)", gewichtet über `get_erzeuger_kwp`, auch wenn seine Leistung nur in `leistung_wp × anzahl`
steht (N-621). Die Monats-Fakten teilen den Rest genauso (`erzeugung.bkw_aus_anlagenwert_kwh`), Σ des Abschnitts = Monatstabelle =
PV-Strings.

**Der laufende Monat zählt anteilig (N-69):** PVGIS liefert Monatssummen; im laufenden Monat stünde die volle Summe als Nenner über
einem angefangenen Ertrag, und die Quote mäße das Datum statt die Anlage.

```
Tage      = min(heutiger Tag, Tage im Monat)   im laufenden Monat, sonst alle Tage
SOLL_kWh  = PVGIS-Monatswert × Tage ÷ Tage im Monat
```

Gekürzt wird der **Nenner**, nicht das Zeitfenster des IST — sonst verlöre die Monatssicht ihre einzige Einordnung des PV-Werts bis
zum Monatsabschluss. Der laufende Tag zählt voll mit (ihn wegzulassen machte den Nenner kleiner und die Quote höher); innerhalb des
Monats gilt Gleichverteilung. Ein Monat in der **Zukunft** hat null Tage und damit kein SOLL — die Sichten lassen die Quote weg, statt
0 % zu melden. Abgeschlossene Monate bleiben unberührt. SoT der Formel: `core/berechnungen/monatsfenster.py` (auch die
Grundlast-Hochrechnung und die Speicher-Auslastung zählen ihre Tage dort). Die Jahres-Sicht summiert die Monatswerte und erbt die
Kürzung ohne eigene Rechnung; die Oberfläche weist das Fenster aus („anteilig · 4 von 31 Tagen").

**Der Anschaffungsmonat zählt ebenso anteilig (F-34):** dieselbe Schieflage am anderen Ende — die Kante kommt aus den Stammdaten,
nicht aus dem Kalender.

```
Tage      = Tage des Monats zwischen Anschaffungs- und Stilllegungsdatum (beide inklusive)
SOLL_kWh  = PVGIS-Monatswert × Tage ÷ Tage im Monat
```

Gekürzt wird wieder der **Nenner**; der Stilllegungsmonat ist die Spiegelkante und wird genauso behandelt.

> ⚠ **Zwei Datums-Ebenen, zwei Formeln — bewusst nicht zusammengelegt.**
> `monatsfenster` beantwortet *„wie viel des Monats ist am Stichtag vergangen"* (Kalender),
> `monatsfenster_investition` *„wie lange gab es dieses Gerät in diesem Monat"* (Stammdaten). Wer
> beide braucht, ruft beide und nimmt das kleinere Fenster. Das ist dieselbe Trennung, die
> [ARCHITEKTUR §4](ARCHITEKTUR.md) für `anschaffungsdatum` gegen `Anlage.installationsdatum`
> zieht — ihre Vertauschung hat schon zweimal zu Abstürzen geführt.

Die **saisonale** Zeile der Laufzeit-Sicht kürzt bewusst **nicht**: sie stellt einen IST-Durchschnitt über mehrere Jahre einem
Klimamittel gegenüber; ein angebrochener Anschaffungsmonat verzerrt dort bereits den IST-Durchschnitt, beide Seiten zu kürzen hieße,
ihn doppelt zu bestrafen (#366).

**SOLL im Monatsbericht:** derselbe Grundsatz — der Monatswert kommt aus den Monatszeilen **genau der aktiven** Prognose, nie aus einer
Summe über mehrere.

#### AC-Kappung im SOLL (ab v4.0.9, #354/#367)

Das PVGIS-SOLL rechnet aus der **Modulleistung (DC)** und kennt die Grenze des Wechselrichters
nicht. Bei einer überbelegten Anlage ist es damit systematisch unerreichbar: was das Gerät mittags
abriegelt, taucht im SOLL/IST-Vergleich als Minus auf, das der Betreiber nicht zu verantworten hat.

Die Kappung wirkt **stündlich**, nie als kWp-Deckel — ein 7-kW-Gerät begrenzt die Mittagsspitze,
nicht den Morgen (Begründung im Modul-Docstring `core/berechnungen/wr_kappung.py`). Weil `PVcalc`
nur Monatssummen liefert, entsteht der Faktor aus einem eigenen **`seriescalc`**-Stundenprofil
derselben Anlage:

```
Faktor_Monat = Σ min(Stunde, AC-Grenze) ÷ Σ Stunde      (über 2018–2020, ertragsgewichtet)
SOLL_Monat   = PVcalc.e_m × Faktor_Monat
```

Damit bleibt PVGIS die **einzige** Ertragsquelle; hier entsteht kein zweiter Ertragswert, nur ein Faktor ≤ 1. Drei Jahre statt einem,
damit der Faktor nicht das Wetter eines Einzeljahres trägt.

> **Die Grenze gehört dem Wechselrichter, nicht der Himmelsrichtung.** Mehrere Strings an einem Gerät teilen sich seine AC-Grenze und
> werden **gemeinsam** gekappt, anteilig nach ihrem Stundenbeitrag — auch über Orientierungsgruppen hinweg (je String einzeln gekappt
> erreichte oft keiner allein die Grenze, die gemeinsame Mittagsspitze aber schon).

Woher die Grenze kommt (SoT `core/investition_kennwerte.get_wr_grenze_kw`, Zuordnung
`wr_kappung.zuordne_grenzen`):

| Erzeuger | Grenze | Geteilt? |
| --- | --- | --- |
| `balkonkraftwerk` | eigener Parameter `wechselrichter_leistung_w` | nein — Erzeuger und Wechselrichter sind ein Gerät |
| `pv-module` | `max_leistung_kw` des zugeordneten **Wechselrichters** (Fallback: Legacy `leistung_ac_kw`, dann die Spalte `leistung_kwp`, die dort kW AC trägt) | **ja** — alle Strings desselben Geräts |

**Ohne gepflegte Grenze wird nicht gekappt** (`None`, kein Default) und PVGIS gar nicht zusätzlich
gefragt — die Prognose bleibt dann ungekappt. Fällt der `seriescalc`-Abruf aus, gibt es
**keine** Faktoren statt geratener: ein ungekapptes SOLL ist eine bekannte Größe, ein halb
gekapptes wäre keine.

Derselbe Layer kappt die **Tages**-Prognose (`services/prognose_kanon.py`) mit denselben Grenzen und derselben Gruppierung.

#### IST-Berechnung

Der IST-Wert je Modul kommt aus dem Read-time-SoT `core/berechnungen/pv_verteilung.py`
(`resolve_pv_je_modul`) — **nicht** aus einem rohen Feldzugriff. Präzedenz:

```
1. Messwert       InvestitionMonatsdaten.verbrauch_daten["pv_erzeugung_kwh"]
                  → Quelle „gemessen" — IMMER und AUSNAHMSLOS
2. Lücke füllen   (Monatsdaten.pv_erzeugung_kwh − Σ eigene BKW-Werte − Σ gemessene) × kWp_Anteil,
                  auf die Module UND die selbst tragenden Balkonkraftwerke OHNE eigenen Wert
                  (Rest nie unter 0; BKW-Gewicht über get_erzeuger_kwp, N-621)
                  → Quelle „geschätzt (kWp-Anteil)", in der Anzeige gekennzeichnet
3. keine Quelle   kein Wert (kein 0)
```

**Die Präzedenz ist modulweise, nicht anlagenweit:** der Gesamtwert füllt **Lücken**, er überschreibt keine Messungen — auch wenn nur
ein Modul keinen eigenen Wert hat (Teil-Messung entsteht bei jedem Sensor-Aussetzer, jedem neu angelegten String und in jedem Monat vor
der Umstellung auf Pro-String-Messung).

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

##### Regel 1 gilt nur für echte Messungen (#352, seit v4.0.9)

Die Präzedenz oben liest „ein eigener Wert in der Zeile = gemessen". Das gilt nur für echte Messungen: zwei Schreibwege legen eine
**gerechnete** Zahl in die Zeile — der Import einer Legacy-Gesamtspalte (`_distribute_legacy_pv_to_modules`, aus CSV-Backup, Portal-
und Custom-Import) und der Monatsabschluss, wenn der zerlegte Vorschlag von Connector oder Cloud-Import übernommen wird
(`_mapped_or_distribute`). Diese Wege vermerken am Wert, dass er gerechnet ist:
`InvestitionMonatsdaten.source_provenance["verbrauch_daten.<feld>"]["abgeleitet"]` trägt
`kwp_anteil` (PV) bzw. `kapazitaet_anteil` (Speicher). SoT der Marken und ihrer Positivliste:
`services/provenance.py` (`ABGELEITET_*`, `gepruefte_ableitung`). Der Ladepfad
`services/pv_monatswerte.py` liest sie **aus derselben Zeile** — kein Join, keine zweite Abfrage —
und übergibt sie als `PvModul.eigen_ist_abgeleitet`; `resolve_pv_je_modul` liefert dafür
`QUELLE_VERTEILT` statt `QUELLE_GEMESSEN`, **ohne den Wert anzufassen**.

Drei Grenzen, alle bewusst:

- **Ein Empfänger = keine Zerlegung.** Geht der Gesamtwert an genau ein Modul bzw. einen Speicher,
  ist er unverzerrt dort und bleibt `gemessen` — dieselbe Grenze, die der Monatsabschluss für
  Beschriftung und Konfidenz zieht (`ist_verteilt`).
- **Der Client meldet die Herkunft, das Backend rät sie nicht.** Nur die Oberfläche weiß, ob der
  Anwender den zerlegten Vorschlag übernommen oder eine eigene Zahl getippt hat; sie schickt die
  Marke im Investitions-Payload als `abgeleitet_felder` mit (gleiches Muster wie `geprueft_gegen`).
  Client-SoT: `lib/erfassungZustand.ts::abgeleiteteMarke` — sie schweigt, wenn ein gleich hoher
  Vorschlag **ohne** Marke danebensteht, weil dann nicht entscheidbar ist, welcher übernommen wurde.
- **Kein Altbestand-Heilen.** Bereits gespeicherte Zeilen bleiben mehrdeutig: derselbe `writer`
  steht dort für „echte Pro-Modul-Spalte aus der CSV" *und* für „verteilt". Rückwirkend trennen geht
  nicht ([[feedback_kein_grosser_heiler_knopf]]); die Marke wirkt ab dem nächsten Schreibvorgang.

Der Daten-Checker zählt markierte Werte nicht als Messung. Damit ein vollständig importierter Monat dadurch nicht von OK auf ERROR
fällt, kennt `klassifiziere_pv_monat` den Parameter `n_abgeleitet`: decken die gerechneten Werte den Monat ab, ist er `verteilt` (INFO)
— die Zahlen sind da, sie sind nur nicht gemessen.

> **Teil-Lücke ohne Gesamtwert (ADR-002/P2):** ist nur ein Teil der Module gemessen und **kein** Gesamtwert hinterlegt, behält die
> Pro-Modul-Sicht ihre Messwerte, und die Anlagen-Summe trägt dieselben vorhandenen Werte — `Σ Strings = Σ Anlage`, gekennzeichnet als
> Teilsumme (`pv_vollstaendig=False`); der Daten-Checker nennt den Monat (ein Modul-Ausfall kann auch korrekt sein). Die Prüfungen
> rechnen nur mit vollständigen Monaten.

**Beim Import und beim Monatsabschluss** gilt dieselbe Rangfolge auf der *Vorschlags*-Seite: Ist ein
Connector-Feld einer Komponente zugeordnet, geht der volle Zählerstand dorthin („Vom Wechselrichter
(Zählerstand-Differenz)"); ohne Zuordnung wird nach Nennleistung verteilt und heißt dann „Gesamtwert,
anteilig nach kWp auf die Strings verteilt" — mit niedrigerer Konfidenz als jede gemessene Quelle.
Der Zuordnungs-Schritt des Import-Wizards schlägt die Anteile ebenfalls **nach Nennleistung** vor
(bzw. nach Kapazität bei Speichern); ist die Bezugsgröße nirgends gepflegt, verteilt er gleichmäßig
**und sagt dazu, dass das keine proportionale Aufteilung ist**.

#### IST je Erzeuger auf **Tagesebene** (ab v4.0.9, #350)

Die Präzedenz gilt auch auf der Tagesebene (#406, Abschnitt *Der Anlagen-Zählerstand* unten); verteilt wird dort nur, wenn ein
**Anlagen-Zählerstand** vorliegt und die Einzelzähler den Tag nicht vollständig tragen.

```
erzeuger_kwh[inv_id] = Σ komponenten_kwh[pv_<id> | bkw_<id>]      (Boundary-Rollup)
                     ∨ Σ TagesEnergieProfil.komponenten je Stunde  (Fallback, kein Rollup)
kein eigener Sensor, kein Anlagen-Zählerstand ⇒ kein Eintrag (kein 0, kein kWp-Anteil)
kein eigener Sensor, Anlagen-Zählerstand da    ⇒ kWp-Anteil am Rest, als abgeleitet markiert
```

SoT der Formel: `core/berechnungen/energie.py::erzeuger_kwh_je_investition`, ausgeliefert als
`TagWerteResponse.erzeuger_kwh` (`GET /api/energie-profil/{id}/tage-werte`). Zwei Eigenschaften
sind dabei nicht optional:

- **Der Schlüssel ist die Investitions-ID, nicht der Komponenten-Key.** Dasselbe Balkonkraftwerk heißt im Live-Keyspace `pv_<id>` und
  im Boundary-Keyspace `bkw_<id>` (`snapshot/komponenten_beitraege._TYP_PREFIX` gegen `live_komponenten_builder`); je Roh-Key gruppiert
  bekäme ein Gerät zwei Spalten, deren Belegung vom Schreibpfad des Tages abhängt.
- **Eine kWp-Verteilung nur MIT Kennzeichnung — und nur je Tag.** Eine so gefüllte Tageszahl wäre ohne Marke von einer Messung nicht zu
  unterscheiden (Klasse #352): `source_provenance` trägt je `komponenten_kwh`-Sub-Key die Marke `ABGELEITET_KWP_ANTEIL`. ⚠ **Auf der
  Stundenebene gibt es keine Verteilung** — dort trüge der kWp-Schlüssel eine Form, die die Stunde nicht hat (Ost und West wären um
  8 Uhr formgleich). Ohne Anlagen-Zählerstand bleibt es überall bei „kein Eintrag": die Oberfläche nennt das Gerät und den Weg zur
  Zuordnung.

##### Der Anlagen-Zählerstand: Summe immer, Aufschlüsselung aufgelöst (ab 2026-09-04)

Das Feld *Anlage (Basis) → PV-Erzeugung Zählerstand (kWh)* landet über `basis["pv_gesamt"]` in `Monatsdaten.pv_erzeugung_kwh` und ist
damit **Eingang der Monats-Auflösung** (P7). Zugleich ist es ein **Snapshot-Zähler der Kategorie `pv`**
(`snapshot/keys.py::BASIS_ZAEHLER_FELDER`) und trägt damit auch Tag und Stunde — als **Summe der ganzen Anlage** (F-7): wer nur einen
Summenzähler hat, bekommt vollständige Tageswerte; was fehlt, ist allein die Aufschlüsselung je Erzeuger. Alle Ausrichtungen als *eine*
Investition zu führen bleibt **falsch**: `services/pv_orientation.py` gruppiert je Investition nach (Neigung, Azimut), eine
zusammengelegte Anlage bekäme einen systematisch falschen Tagesgang im gesamten Prognose-Kanon inklusive HA-Prognose-Sensoren und
PVGIS-SOLL.

> ⚑ **Der folgende Absatz ist die Regel des Bestandspfads** — Tage, deren Kanäle den Tag nicht voll decken (ohne HA-Statistik, vor dem
> Spiegel, Lücke). Für Kanal-Tage gilt W2 (§1): keine Wahl Einzel/Aggregat je Tag, kein 1-%-Kriterium, keine Skalierung gemessener Werte.

**Die Regel ist die Präzedenz je Tag (#406)** — die Entsprechung der Monatsregel `resolve_pv_je_modul`, auf den Tag übertragen, SoT
`core/berechnungen/pv_tages_praezedenz.py`:

1. Liefern **alle** am Tag aktiven Erzeuger über den ganzen Tag einen eigenen Zählerwert, gilt
   ihre Summe. Der Anlagen-Zählerstand zählt dann nicht mit.
2. Sonst trägt der **Anlagen-Zählerstand** den Tag — und auf der Tagesebene wird er über
   `resolve_pv_je_modul` in die Erzeuger **aufgelöst**: gemessene behalten ihren Wert, die übrigen
   bekommen den kWp-gewichteten Anteil am Rest und tragen in `source_provenance` die Marke
   „abgeleitet".
3. Gibt es keinen Anlagen-Zählerstand, bleibt es bei den gemessenen Erzeugern.

⚠ **Auf der Stundenebene wird NICHT verteilt** — dort wählt die Präzedenz nur die Summe. Über
einen Tag mittelt sich der Ost/West-Unterschied der kWp-Gewichtung weitgehend aus, über eine
Stunde nicht: Ost und West bekämen um 8 Uhr formgleiche Kurven. Was sich stündlich nicht zuordnen
lässt, steht im Tagesverlauf als **„PV (übrige)"**.

⛔ **Was unverändert gilt: nie beides zusammen.** `komponenten_kwh` hat einen flachen Keyspace, und
die Tages-PV ist die Summe aller `pv_`/`bkw_`-Schlüssel (`summe_pv_bkw_kwh`). Stünde `pv_gesamt`
neben `pv_7`, wäre die Anlagensumme neben ihrem eigenen Summanden gebucht — Doppelzählung. Der
Anlagen-Zählerstand wird *aufgelöst*, nicht *verdrängt* und nicht *addiert*.
Eine Bedingung, die die Zuordnung statt die Daten fragt („der Anlagen-Zählerstand zählt nur, solange kein Erzeuger einen eigenen
Zähler trägt"), gilt nicht: sie nähme zugeordneten Zählern ohne frühere Werte deren gemessene PV und hielte eine teilweise bezählte
Anlage dauerhaft zu klein (#406). **Die Monatswerte sind in allen Lagen vollständig.**

Bleibt gar kein kumulativer PV-Zähler übrig — weder je Erzeuger noch für die Anlage —, sagt die Tagessicht das, statt zu rechnen:
`TagesBilanz.pv_erfasst` trennt „0 kWh gemessen" (Nacht, Schnee — gültig) von „nicht erfasst". Im zweiten Fall bleiben **Erzeugung,
Eigenverbrauch, spezifischer Ertrag, Performance Ratio und CO₂ leer** — nie ein negativer Eigenverbrauch aus `0 − Einspeisung`
(T89667 #109). Regel-SoT: [KONZEPT-UNVOLLSTAENDIGE-WERTE](KONZEPT-UNVOLLSTAENDIGE-WERTE.md) — eine Summe darf 0 bleiben, eine Differenz
mit fehlendem Summanden nicht. Die Zuordnungs-Seite und der Daten-Checker nennen in dieser Lage den Weg über einen HA-Integral-Sensor
je Erzeuger ([HANDBUCH_DATEN_CHECKER §5.2](HANDBUCH_DATEN_CHECKER.md#52-fehlende-kwh-zähler-in-der-datenquellen-zuordnung-ergänzen)).

Der Client schlüsselt **ab zwei Erzeugern** auf (`lib/erzeugerSpalten.ts`, geteilt von
*Cockpit → Tag* und *Auswertungen → Tabelle*) und berücksichtigt Anschaffungs-/Stilllegungsdatum.
Im Stundenverlauf **ersetzen** die Geräte-Flächen die PV-Fläche, statt auf ihr zu liegen; der
ungedeckte Rest (`pvRestKw`) steht als „PV (übrige)" daneben, damit die Stapelhöhe die Erzeugung
bleibt. Die Energie-Bilanz (`erzeugung`, `pv_anlage`, `bkw`) rechnet unverändert aus ihren eigenen
Quellen — die Aufschlüsselung ist eine Auskunft, keine Summe.

#### Kennzahlen pro String

```
Abweichung_kWh        = IST - SOLL
Abweichung_%          = (IST - SOLL) / SOLL * 100
Performance_Ratio      = IST / SOLL
Spez. Ertrag (kWh/kWp) = IST_Jahr / Modul_kWp
```

**Ohne aktive PVGIS-Prognose** entfallen Abweichung und Performance Ratio (`None`); IST,
Ertragsanteil und spezifischer Ertrag bleiben, und die Sicht zeigt sie (#350).

**Anlagenzeile der Gesamtlaufzeit** (`GET /cockpit/pv-strings-gesamtlaufzeit`, Spalte/Karte «kWh/kWp»): `spezifischer_ertrag_zeitraum_kwh_kwp`
= IST gesamt ÷ Anlagen-kWp über `kennzahlen.spezifischer_ertrag_kwh_kwp` — der Wert **der ganzen Laufzeit, nicht aufs Jahr normiert**
(anders als der Sensor `spezifischer_ertrag_kwh_kwp`, §3.1). Seit Päckchen Z-Client; vorher im Client. Die Jahressicht trägt
dasselbe als `spezifischer_ertrag_kwh_kwp` am Kopf von `GET /cockpit/pv-strings` (IST des Jahres ÷ Anlagen-kWp, Päckchen BB4).

**Alle Jahre** (*Auswertungen → Prognose*, Jahr = «Alle Jahre», Päckchen BB4): Kacheln, String-Tabelle, Balken, Platzierung und
Monatsverlauf «Summe aller Jahre» lesen `GET /cockpit/pv-strings-gesamtlaufzeit` (der Client benennt nur um,
`PvStringsTeile.tsx::laufzeitAlsJahr`) — bis dahin faltete der Client die Jahres-Antworten (Σ gerundeter Jahre). Dazu trägt
jeder String `abweichung_gesamt_kwh` (IST − SOLL) und `monatswerte_summe[]`:

```
prognose_summe_kwh(Monat) = Σ über die Jahre des Monats-SOLL der Jahressicht (nur Monate mit IST, F-34 im Lauf-Monat)
ist_summe_kwh(Monat)      = Σ über die Jahre des Monats-IST
```

Das ist **die Summe**, nicht das Saisonal-Mittel (`saisonalwerte`, ohne F-34 und über die Monate, in denen der String aktiv war).
Die Platzierung entscheidet `_ranking` über die Laufzeit-Quelle je String (ein verteiltes Jahr macht ihn «verteilt»); ein Jahr,
in dem ein String noch keinen Wert hatte (`fehlt`), sperrt sie nicht — anders als die Jahressicht jenes Jahres. Der Mehrjahres-Chart
(Performance je Jahr) liest weiter die Jahres-Antworten selbst.

**Bester und schwächster String** (`api/routes/cockpit/pv_strings.py::_ranking`, beide Sichten):

```
Platzierung nur, wenn ≥ 2 Strings UND jeder String durchgängig gemessen (Quelle des Zeitraums = gemessen)
bester        = String mit der höchsten Performance Ratio des Zeitraums
schwächster   = String mit der niedrigsten — nur, wenn mindestens zwei Strings eine Performance Ratio tragen
```

Strings ohne Performance Ratio (ohne Prognose, ohne SOLL) oder mit 0 zählen nicht mit; trägt keiner eine, bleibt die Platzierung
leer, ohne Hinweis. Ist auch nur ein String verteilt statt gemessen, steht statt der Platzierung der Erklärsatz —
im Mischfall (mindestens ein String gemessen) der Satz „Nicht alle Module haben gemessene Werte …" (N-653), sonst
„Die Werte je Modul sind nicht gemessen …" (A4/E3, s. oben „Der kWp-Anteil ist ein Prognose-, kein Ertragsschlüssel").
Ist nichts verteilt, aber ein String hat im Zeitraum **gar keinen** Wert (`fehlt`, etwa ein Jahr vor seiner Anschaffung),
bleibt die Sperre — der Satz lautet dann „Nicht alle Module haben in diesem Jahr (bzw. im Zeitraum) Werte …" (Päckchen CC;
bis dahin stand dort der Mischfall-Satz „ein Teil ist anteilig verteilt", der nicht zutraf). Das Feld `vergleich_grund`
(`verteilt` · `teilweise_verteilt` · `nicht_alle_werte`) sagt der Anzeige, welches Zeichen sie setzt («geschätzt
(kWp-Anteil)» bzw. «offen»).

### 3.10 Sonstige Positionen

**Utility:** `utils/sonstige_positionen.py`

Sonstige Positionen sind frei erfassbare Erträge/Ausgaben je Monat (Reparaturen, Wartung, THG-Quote, Abschlag, Guthaben-Auszahlung …), erfasst im [Monatsdaten-Formular](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss). Es gibt sie auf **zwei Ebenen**:

- **Komponenten-Ebene:** `InvestitionMonatsdaten.verbrauch_daten["sonstige_positionen"]`.
- **Anlage-/Basis-Ebene (G19-1):** `Monatsdaten.sonstige_positionen` — für Positionen, die keiner einzelnen Komponente zuzuordnen sind. Gelesen über den Spiegel-Helper `get_md_sonstige_positionen`.

> **Vorrang neues Format:** `get_sonstige_positionen()` liest zuerst `sonstige_positionen`; nur wenn der Schlüssel **fehlt**, greift der Legacy-Fallback `sonderkosten_euro`/`sonderkosten_notiz` (→ eine Ausgabe-Position). Eine additive Start-Migration materialisiert Alt-`sonderkosten_euro > 0` als „… (migriert)"-Ausgabe; die Legacy-Spalten bleiben lesbar (deprecated, nicht neu befüllen). Alt-Sonderkosten zählen damit in den Finanz-Summen (s. [§3.2](#32-finanzen-cockpit)).

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

**Dienstliche Ladekosten:** bei `ist_dienstlich == true` (E-Auto/Wallbox) werden Ladekosten als kalkulatorischer Aufwand verbucht —
als eigener Posten der Ergebnis-Leiter (§3.2, N-633), nicht in den Sonstigen Positionen:
```
Dienstlich_Ladekosten = Netz_kWh * Wallbox_Preis + PV_kWh * Netzbezugspreis
```

> **Warum der PV-Anteil zum Netzbezugspreis zählt, nicht zur Einspeisevergütung.** Der Eigenverbrauch ändert sich durch das Dienstwagen-Flag **nicht** — energetisch ist die Ladung Eigenverbrauch hinter dem Zähler —, also schreibt die EV-Ersparnis (`Eigenverbrauch × Netzbezugspreis`) die dienstlich geladenen kWh voll gut; zurückzunehmen ist genau diese EV-Gutschrift, und die steht zum Netzbezugspreis. Die *entgangene Einspeisevergütung* braucht keinen Buchungssatz: sie steckt bereits in der niedrigeren **gemessenen** Einspeisung.
>
> **Die Energiebilanz bleibt unangetastet** — Eigenverbrauchs-kWh, Eigenverbrauchsquote und Autarkie ändern sich durch diesen Posten nicht; er bewertet nur in Euro.
>
> **Netzanteil:** Wallbox-Stromvertrag, wenn vorhanden, sonst Anlagentarif — jeweils der Monats-Flexpreis vor dem Stammdaten-Arbeitspreis (P8); Aussichten und Cockpit gleich.
>
> **SoT:** `core/berechnungen/dienstliche_ladekosten.py` (ADR-001). Ihn ruft **eine** Stelle (N-633): die Monats-Fakten-Schicht (`services/monats_fakten/bau.py`, mit dem Tarif des Monats), Feld `EmobFakten.dienstliche_ladekosten_euro`. Daraus lesen alle Sichten — Cockpit → Monat und → Jahr, Auswertungen → Tabelle/Finanzen, Monats- und Jahresbericht als Posten der Leiter, Cockpit → Übersicht, Aussichten/Finanz-Prognose und der HA-Sensor `netto_ertrag_euro` als Abzug in ihren Sonstigen Positionen. *Cockpit → Monat* rechnet den Posten auch für einen Monat **ohne** Monats-Fakt (laufender Monat ohne Abschluss) wie die Schicht (HA-Bauform E4e) — Mengen aus derselben Entscheidung (`entscheide_emob_heimladung`), Tarif und Bewertung über `monats_fakten.tarif_des_monats` und `dienstliche_ladekosten_euro`. Hinweis an der Zeile (wortgleich in Backend und Oberfläche): „Strom für den Dienstwagen: Netzanteil zum Wallbox-Tarif, PV-Anteil zum Netzbezugspreis. Die Erstattung des Arbeitgebers steht unter den sonstigen Erträgen."

#### Energie der Sonstiges-Geräte — die Kategorie-Weiche

Welche Menge eines *Sonstiges*-Geräts zählt, entscheidet seine gepflegte Kategorie (`parameter.kategorie`) an **einer** Stelle je
Zeile: `core/berechnungen/imd_monatsaggregat.py::imd_typ_beitrag`. Dieselbe Weiche gilt für die Monatszeile und für die Zeilen aus den
Kanälen (`services/monats_fakten/bau.py::sonstiges_aus_zeilen`, HA-Bauform E4c); gefaltet wird als Anlagensumme (`SonstigesFakten`)
und je Gerät (`SonstigesFakten.je_geraet` → `SonstigesGeraetFakten`, `monats_fakten/roh.py::_falte_sonstiges`) — Σ der Geräte = Summe.

| Kategorie | zählt | auf 0 gesetzt |
|---|---|---|
| `zaehler` (#377) | nichts — Zählerstände sind kein Strom, auch alte Energiefelder eines umgestellten Geräts zählen nicht | alle Mengen und der Erlös |
| `abgabe` (§9.2) | Abgabe an Dritte (`abgabe_kwh`) und den Erlös | Erzeugung, Verbrauch, Eigenverbrauch, Einspeisung, Bezug PV/Netz |
| `erzeuger` | Erzeugung, Eigenverbrauch, Einspeisung, Erlös; trägt die Zeile kein `erzeugung_kwh`, ist das Verbrauchsfeld (`verbrauch_sonstig_kwh` vor `verbrauch_kwh`) die Erzeugung (N-667; eine gepflegte 0 bleibt 0) | Verbrauch, Bezug PV/Netz |
| `verbraucher` | Verbrauch (`verbrauch_sonstig_kwh` vor `verbrauch_kwh`), Bezug PV, Bezug Netz | Erzeugung, Eigenverbrauch, Einspeisung, Erlös |
| leer | alles, wie gepflegt (Abgabe nur im Zweig abgabe) | — |

Die Monatsgrößen, je Anlagensumme und je Gerät gleich:

- **Erzeugung** (`SonstigesFakten.erzeugung_kwh`, je Gerät `SonstigesGeraetFakten.erzeugung_kwh`) — Zweige `erzeuger` und leer; dieselbe
  Summe ist `ErzeugungFakten.sonstige_erzeuger_kwh`, der dritte Summand der Erzeugung hinter dem Zähler (§3.1 „Netzpunkt-Bilanz").
- **Abgabe** (`abgabe_kwh`) — nur Zweig `abgabe`; sie wird vom Eigenverbrauch abgezogen (§3.1 „Formeln").
- **Verbrauch** (`verbrauch_kwh`) — Zweige `verbraucher` und leer.
- **Eigenverbrauch** und **Einspeisung** (`eigenverbrauch_kwh`, `einspeisung_kwh`) — die Erzeugerseite: Zweige `erzeuger` und leer.
- **Bezug PV** und **Bezug Netz** (`bezug_pv_kwh`, `bezug_netz_kwh`) — die Verbraucherseite: Zweige `verbraucher` und leer.

Der **PV-Anteil** eines Verbrauchers im Cockpit (Kachel je Gerät, Monat und Jahr) ist `pv_anteil_prozent` der Gerätezeile =
Bezug PV ÷ (Bezug PV + Bezug Netz) × 100 auf den Werten, die die Zeile trägt (`pv_anteil_ladung.bezug_pv_anteil_prozent`; ein fehlender
Teil zählt 0, ohne Bezug `None`). Seit Päckchen Z-Client; vorher im Client. Dieselbe Definition trägt das Attribut
`pv_anteil_prozent` des HA-Sensors `sonstiges_verbrauch_monat_kwh` (laufender Monat, eine Nachkommastelle;
`ha_export/investition_sensoren.py`, seit Päckchen DD 10.11.2026 — bis dahin teilte es durch den Verbrauch, gleich, solange
Verbrauch = Bezug PV + Bezug Netz).

**Am Tag** (`TagesZusammenfassung.komponenten_kwh`, `TagesEnergieProfil.komponenten`) trägt jedes Gerät **eine** Zahl; die Weiche
dort ist `core/berechnungen/energie.py::sonstiges_kwh_je_richtung` — Richtung aus der Kategorie, Menge als Betrag (das Vorzeichen
unterscheidet sich je Schreibpfad). `erzeuger` ⇒ Erzeugung, `abgabe` ⇒ Abgabe, **eine leere Kategorie zählt am Tag als Verbrauch**
(dieselbe Vorgabe, mit der beide Tages-Schreibpfade den Wert erzeugen); `zaehler` und `speicher` zählen am Tag nicht (beim Speicher
ist die eine Zahl ein Netto-Wert). Der Monat nimmt bei leerer Kategorie **beide** Felder (`SonstigesFakten`, Zeile «leer» oben) —
dort stehen Erzeugung und Verbrauch getrennt gepflegt.

---

### 3.11 Community-Datensatz: abgeleitete Stammdaten

Der Datensatz, den eedc an den Community-Server schickt (`services/community_service.py::prepare_community_data`,
Aufrufer: Vorschau/Teilen `api/routes/community.py`, Monatsabschluss, nächtliches Nachsenden), beschreibt die
**heutige Ausstattung** der Anlage. Der Server rechnet nichts nach — jede Zahl hier geht so in den Benchmark ein, wie
eedc sie bildet. Schlüssel, Namen und Rundungen sind der Vertrag mit `eedc-community` (Kopf des Datensatzes,
`monatswerte` je Monat nach `backend/schemas.py::MonatswertInput`).

```
Region          = Land (AT/CH/IT) | Bundesland aus der PLZ (DE) | "XX"
kwp             = round(Anlagen-kWp, 1)
Jetzt-Menge     = Investitionen mit ist_aktiv_an(heute)                               (F-24, N-617)
speicher_kwh    = round(Σ Brutto-Kapazität der heute aktiven Speicher, 1)  | None bei 0  (F-24)
wallbox_kw      = max Ladeleistung der heute aktiven Wallboxen             | None bei 0  (N-617)
bkw_wp          = Σ je heute aktivem Balkonkraftwerk:
                    Σ kWp der heute aktiven Modul-Kinder × 1000, falls es Kinder hat     (E5, N-266)
                    sonst leistung_wp × anzahl (anzahl fehlt oder 0 ⇒ 1)
                  | None bei 0
neigung_grad    = int(Ø Neigung der Erzeuger)        Erzeuger = Selektor(Jetzt-Menge ∩ {pv-module, balkonkraftwerk})
ausrichtung     = genau ein Erzeuger, und der trägt „Ost-West"     ⇒ "ost-west"
                  sonst Azimute (Kompass, 180 = Süd) mit Spanne > 45°:
                      einer in 60–120° UND einer in 240–300°        ⇒ "ost-west", sonst "gemischt"
                  sonst Label von int(Ø Azimut)  (8 Sektoren à 45°)
                  ohne Erzeuger: 30° und "süd" (Defaults)
sonstiges       = die ersten 3 nicht leeren Bezeichnungen der Sonstiges-Geräte, mit „, " verbunden
hat_* / wp_art  = alle erfassten Geräte (ohne Zeitfilter); wp_art und kuehlung_art der ersten Wärmepumpe
installation_jahr = Jahr des Installationsdatums, sonst das laufende Jahr
soll_jahr_kwh   = round(Jahresertrag der aktiven PVGIS-Prognose, 1)  | None ohne aktive Prognose oder bei 0 (#387)
```

Die Monatswerte kommen aus den **Monats-Fakten** (ADR-002/P10, `_monatswert` je Fakt mit seinen Filtern — u. a. ohne
Zählerzeile bzw. erfasste Netzfelder und ohne PV kein Monatswert); `monate_vollstaendig` sagt dem Server, dass der Datensatz alle teilbaren
Monate trägt (N18-2). Die Ausstattungs-Merkmale `hat_*` und `wp_art` laufen bewusst ohne Zeitfilter — sie öffnen auf
dem Server den Vergleich der historischen Monatswerte (N-617, Abgrenzung im Test `test_n617_community_stammdaten_heute.py`).

Code-Orte: `_stammdaten` (Region, Investitionen, `hat_*`, Sonstiges, Stichtag und Jetzt-Menge) ·
`_speicher_und_wallbox` · `_bkw_wp` · `_neigung_ausrichtung` · `_payload` (Schlüssel-Reihenfolge, Installationsjahr,
Wärmepumpen-Art) · `_monatswerte` (SOLL-Jahr, Monatswerte).

## 4. Prognosen (Aussichten)

> **Prognose-Kanon — „PV-Tagesprognose heute" ist EIN Wert.** Der „heute"-Wert (sowie Rest heute, morgen/übermorgen, Vor-/Nachmittag, Stundenprofil) wird über **einen** Service (`services/prognose_kanon.py`) gebildet und an alle Konsumenten geliefert: Live/Cockpit (`live_wetter`), die „eedc"-Spalte im Vergleich (`api/routes/prognosen`), die HA-/MQTT-Sensoren (`ha_export_prognose`) und den persistierten Tageswert (`TagesZusammenfassung.pv_prognose_kwh`). Rechenweg: **Multi-String-Fan-out** pro Orientierungsgruppe (`pv_orientation.orientierungs_gruppen` → je ein `get_solar_prognose`) → slot-weise Summe = rohes OpenMeteo-kWh-Profil → **eedc-Korrektur pro Energie-Slot** (`core/berechnungen/prognose_korrektur.korrigiere_tagesprofil`, Kaskade `korrekturprofil_lookup`) mit Invariante `Tageswert == Σ Export-Slots`. Der Wert **rollt** mit OpenMeteo, aber überall synchron. Mathematik in `core/berechnungen/` (ADR-001), Orchestrierung im Kanon-Service. Symmetrie-Test: `tests/test_prognose_kanon.py`.
>
> **Am Kanon hängen außerdem** (v4.0.1) der 14-Tage-Balken in Cockpit → Aussicht samt 14-Tage-Tabelle und den Kacheln
> „Morgen"/„Summe"/„Ø_Tag", die Zeilen Morgen/Übermorgen der Live-Solar-Aussicht und die Blöcke
> „Stunden-Prognose"/„Stundenwerte" — dieselbe Rechnung wie der Prognosen-Vergleich und der Sensor
> `eedc_prognose_day_plus_1_kwh`. *(Ausgenommen: die Spalte „OpenMeteo" im Prognosen-Vergleich — sie ist der Rohwert.)*
> Fehlt eine Korrektur, bleibt der Wetterdienst-Wert stehen und die Kopfzeile sagt es („Quelle: Open-Meteo (ohne Korrektur)").
>
> **Heute nachgeführt** (`KanonPrognose.heute_rollend_kwh`, Sensor `eedc_prognose_heute_rollend_kwh`) = **bereits erzeugt**
> + **Rest heute**. Bereits erzeugt ist gemessen: Σ der PV-Stunden von heute über `kanal_stunden.stunden_der_tage` (an einem
> Kanal-Tag die Mischzeilen, wie *Prognosen → Vergleich*) — es hängt an keiner Prognose und bleibt auch stehen, wenn der
> Wetterabruf ausfällt. **Raster (N-784):** `prognose_adapter.ist_profil` legt jede Zeile auf ihren **Backward-Slot**
> (`slot_konvention.backward_slot_der_zeile`): eine Mischzeile (Beginn-Raster, Zeile h = [h, h+1)) auf Slot h + 1, ihre
> Stunde 23 auf Slot 0 des Folgetags (aus dem Profil, im Tageswert); eine Bestandszeile bleibt. Damit ist die IST-Grenze
> `ist_bisher_bis_slot` (N-544, der höchste Slot mit Messwert) an jedem Tag ein Backward-Index, und Stundenvergleich,
> Abweichungs-Ampel und Nachführung paaren IST und Prognose an derselben Stunde. Dieselbe Paarung nehmen die
> Verbrauchsprofil-Bauer (`verbrauch_prognose_service`, `live_verbrauchsprofil_service._profil_from_db`) und das
> Korrekturprofil (`lade_ist_wetter_stunden`).
>
> **Rest heute** = der **Modell-Rest** — Σ der korrigierten Slots nach der laufenden Stunde plus die laufende Stunde anteilig
> nach den verstrichenen Minuten (`prognose_kanon.rest_aus_slots`, #339, Backward-Slots; `KanonPrognose.rest_modell_kwh`) —
> **× Nachführ-Faktor** aus dem gemessenen Vormittag (Phase `prognose_kanon._nachfuehrung`, Formeln in
> `core/berechnungen/prognose_nachfuehrung.py`):
>
>     SOLL bisher = Σ Slots bis einschließlich ist_bisher_bis_slot   (soll_bisher_kwh, N-544 — dieselbe Summe wie die Ampel)
>     r = IST bisher ÷ SOLL bisher      w = SOLL bisher ÷ SOLL Tag (Σ Slots)
>     f = clip(1 + (r − 1)·√w, 0,4, 1,6)
>
> `f = 1,0` ohne IST-Messung, bei SOLL bisher < 1 kWh oder w < 10 % (Annahmen: Morgen-Rauschen; ebenso die Klemme 0,4…1,6).
> Herkunft: Backtest Winterborn 1.9.–8.11.2026 (69 Tage) — MAE des Tagesendwerts im Okt/Nov um 10–14 Uhr
> 28,6/24,7/19,7/14,6/10,6 % ⇒ 24,4/19,6/17,5/12,6/9,4 %, Nebeltage halbiert, September ≤ 1,5 Punkte schlechter um 10 Uhr.
> `KanonPrognose.nachfuehr_faktor` (gerundet 3 Stellen; `None` ohne Profil), `soll_bisher_kwh`; Live `pv_prognose_nachfuehr_faktor`,
> `pv_prognose_nachfuehr_prozent` (`round((f − 1)·100)`, nur ab ±5 %, Satz der Solar-Aussicht), `pv_prognose_rest_modell_kwh`,
> `pv_prognose_soll_bisher_kwh` — mit Solcast/SFML als gewählter Quelle folgt der Live-Rest dieser Quelle und die Felder sind
> `None`; HA-Attribute `nachfuehr_faktor` (beide Sensoren) und `rest_modell_kwh` («Rest heute»). **Folgen** dem nachgeführten
> Rest: «Rest heute», «heute (nachgeführt)», die Live-Kopfzahl, der Mittagsstand des Genauigkeits-Trackings und «Speicher voll
> um» samt `eedc_speicher_voll_um_ts` und End-SoC — die Simulation des HA-Exports bekommt die Slots ab `sim_start` × `f`
> (`prognose_nachfuehrung.slots_nachgefuehrt`, Entscheid Master H-N2; die Tagesprognose-Route `energie_profil/prognose.py`
> simuliert weiter mit dem Modellprofil). **Bleiben Modell:** «PV-Prognose heute» samt Stundenprofil, Vormittag/Nachmittag, Day-Ahead- und Abendstand, der Abregelungs-Rest
> (`eedc_abregelung_heute_kwh.rest_heute_kwh` — die Kappung `max(0, P − Grenze)` skaliert nicht linear mit einem Faktor), die
> Abweichungs-Ampel (sie ist der Eingang, keine Ausgabe der Nachführung). Ohne Stundenprofil des Tages gibt es keinen Rest und keinen nachgeführten Wert
> (`None`, auch bei teilweise ausgefallenem Fan-out). Der Tageswert `…_heute_kwh` folgt OpenMeteo, der nachgeführte dem
> IST; *bereits erzeugt + Rest = nachgeführt* (#401).
>
> **Fällt der Kanon aus** (kein OpenMeteo-Ergebnis, keine kWp, Zieltag jenseits des Abruf-Horizonts),
> springt ein Ersatz-Weg ein — er **fächert ebenfalls je Orientierungsgruppe auf** (ADR-002/P1: kein
> Anlagen-Kennwert aus EINER Investition). Liefert eine Gruppe nichts, trägt die **Antwort** den
> Hinweis auf die Teilsumme — nicht das Log (ADR-002/P4). Dasselbe gilt, wenn gar keine Prognose
> vorliegt: 24 Nullen werden als „keine Prognose" ausgewiesen, nicht als Prognose „0 kWh".
>
> **Genauigkeits-Endwert (§6).** Das Genauigkeits-Ranking vergleicht IST gegen `TagesZusammenfassung.pv_prognose_final_kwh` (Fallback `pv_prognose_kwh`): dieser rollt mit, bis OpenMeteo für den Tag nach Sonnenuntergang konvergiert ist (`core/berechnungen/prognose_final.soll_final_einfrieren`), und wird dann via `pv_prognose_final_at` eingefroren. Der Anzeige-Wert bleibt rollend (Drei-Größen-Modell: Anzeige rollend · Lern-Snapshot gefroren · Tracking-Endwert konvergenz-gefroren). Seit N-782 ist das der OpenMeteo-Wert des Zeitpunkts „Abend"; daneben friert `pv_prognose_eedc_final_kwh` (Σ der korrigierten Kanon-Reihe) mit derselben Regel ein — Abschnitt „Genauigkeits-Tracking" unten.

### 4.1 Kurzfrist-Prognose (7-16 Tage)

**Endpoint:** `GET /api/aussichten/kurzfristig/{anlage_id}`
**Datenquelle:** Open-Meteo (konfigurierbar, siehe Wettermodell-Kaskade)

```
PV_Ertrag_Tag = Globalstrahlung_kWh_m2 * Anlagenleistung_kWp * (1 - System_Losses)

Wenn Temperatur_max > 25°C:
    Temp_Verlust = (Temperatur_max - 25) * 0.004
    PV_Ertrag_Tag *= (1 - Temp_Verlust)
```

| Parameter | Quelle | Default |
|-----------|--------|---------|
| `System_Losses` | `PVGISPrognose.system_losses / 100` der aktiven Prognose (`pv_orientation.resolve_system_losses`) | 0.14 (14%) |
| `Anlagenleistung_kWp` | Σ(PV-Module) + Σ(BKW), gelesen über den SoT-Dispatcher `get_erzeuger_kwp` (ADR-002/P3). Reihenfolge: Feld **Leistung (kWp)** der Investition → ersatzweise die Detail-Felder `kwp` bzw. `leistung_kwp` (nur Bestands-/Importdaten) → beim Balkonkraftwerk zusätzlich `leistung_wp` × `anzahl` (Anzahl fehlt ⇒ **1**, nicht die Formular-Vorbelegung 2). Dieselbe Kette gilt an **allen** Lesestellen der Nennleistung — Prognose, Cockpit, PV-Strings, ROI, CO₂, Live und PDF (v4.0.2). | `Anlage.leistung_kwp` |
| `Globalstrahlung_kWh_m2` | Tagessumme der **horizontalen** Globalstrahlung (`shortwave_radiation_sum`) aus `fetch_open_meteo_forecast`, Wettermodell der Anlage | – |
| `Temperatur_max` | Tageshöchstwert derselben Vorhersage (Lufttemperatur, kein Modul-Aufheizungsmodell) | – |

Code: `services/prognose_service.py::berechne_pv_ertrag_tag` (Probe `test_prognose_ertrag_tag.py`). Dieselbe Formel trägt die
OpenMeteo-Tageswerte des Prognosen-Vergleichs ab Tag 4 (`prognosen.py::_openmeteo_tageswerte`, N-317; Tag 0–3 aus dem Kanon).
Die **eedc-Prognose** rechnet nicht hier, sondern im Kanon (Kasten oben): je Orientierungsgruppe mit der **GTI** (Global
Tilted Irradiance aus Open-Meteo Solar, modul-projiziert mit Neigung und Azimut; parallele Abrufe, kWp-gewichtet kombiniert)
und korrigiert je Stunden-Slot (Lernfaktor als gröbste Stufe, §4.1c).

> **GTI-Spalte der 14-Tage-Tabelle ist ein kWp-gewichtetes Mittel** („GTI Modulfläche"): die
> Einstrahlung auf die Modulflächen *dieser* Anlage, konsistent zur Ertragssumme derselben Zeile
> (`Ertrag ≈ GTI × kWp × (1 − Verluste)` ist linear in kWp). *(Die Performance Ratio nimmt die Tages-GTI
> aus der Aggregation, ebenfalls kWp-gewichtet.)*

> **GTI statt GHI (v3.20.0):** Kanon-Prognose und Performance Ratio rechnen mit der modul-projizierten GTI. Bei steilen
> Modulen und tiefstehender Wintersonne ist sie 2–3× höher als die horizontale GHI (`shortwave_radiation`) — ein GHI-basierter
> „theoretischer Ertrag" läge im Winter systematisch zu niedrig (PR-Werte > 1). Die Tagesformel oben rechnet weiter mit der GHI.

> **Ersatzweg ohne Stundenwerte — Annahme GTI ≈ GHI × 1,1.** Ergibt die stündliche GTI-Rechnung eines Prognose-Tags keinen
> Ertrag, schätzt `solar_forecast_service._prognose_tag` ihn aus der Tagessumme der Globalstrahlung: `GTI = GHI × 1,1`
> («~10 % mehr durch optimale Neigung», Konstante `GTI_AUS_GHI_FAKTOR`), dann `Ertrag = GTI × kWp × (1 − Verluste)`.
> Eine Annahme, keine Messung — sie kennt weder Neigung noch Ausrichtung der Anlage (Grenze: bei steilen Modulen im Winter
> liegt die echte GTI deutlich höher, s. o.).

> **Multi-String / PV-Parameter-Quelle (v3.20.2/v3.20.3):** kWp, Neigung und Azimut werden über den Helper `services/pv_orientation.py` gelesen, der in dieser Reihenfolge prüft: Top-Level-Spalte der Investition → `parameter.{neigung,ausrichtung}_grad` (Zahl) → `parameter.{neigung,ausrichtung}` (Zahl oder String mit Mapping `{"süd": 0, "ost": -90, "west": 90, ...}`) → Default. Damit liefern alle drei Prognose-Pfade (Energieprofil-Tagesprognose, Aussichten-Kurzfrist, Prefetch-Cache) identische Eingabe-Parameter an Open-Meteo.

#### Wettermodell-Kaskade

Das verwendete Wettermodell ist pro Anlage konfigurierbar (`Anlage.wetter_modell`). Die wählbaren Werte, ihre Reichweite in
Tagen und ihre Anzeigenamen stehen in `services/wetter/models.py` (`WETTER_MODELLE`, `MODELL_ANZEIGE`). `auto` ist für die
Prognose Open-Meteo `best_match`; für die Wetterwerte des Monats heißt `auto` Bright Sky (DWD), wenn das **gepflegte Land** es
erlaubt (#386, `wetter/orchestrator.py::nutze_brightsky`), sonst Open-Meteo.

Bei einem spezifischen Modell versucht eedc zuerst dieses Modell. Schlägt der Abruf fehl oder liefert es keine Daten für den Standort, fällt es auf `best_match` zurück (Kaskade). Das Modell, das einen Tag geliefert hat, steht je Tag in `datenquelle` (`solar_forecast_service.DayForecast`); die Kopfzeile nennt es mit seinem Anzeigenamen.

**Geltungsbereich (seit v4.0.2, A30):** Die Modellwahl wirkt auf **alle** Prognose-Pfade, weil der Prognose-Kanon (`services/prognose_kanon.py`) `Anlage.wetter_modell` an `get_solar_prognose` durchreicht — also auch auf die eedc-korrigierte Tagesprognose, die Stundenprofile, die Live-/Persistenz-Werte und den HA-/MQTT-Export (`services/ha_export_prognose.py`).

**Am Rand der Modell-Reichweite entscheidet die Abdeckung, nicht die Existenz (seit v4.0.19, F-36).**
Jedes Modell hat eine Reichweite (`WETTER_MODELLE`), und am **letzten Tag innerhalb** dieser Reichweite liefert Open-Meteo
häufig nur noch die Stunden bis zum Ende des Modelllaufs — der Rest des Tages, oft der ganze Ertragszeitraum, trägt `null`.
Die Kaskade holt für solche Fälle zusätzlich `best_match`:

```
Primary gewinnt einen Tag, wenn er ihn mindestens so weit ABDECKT wie best_match — nicht schon, wenn der Tag VORKOMMT
```

Gezählt werden Stunden mit einem GTI-**Wert**, nicht mit Ertrag — nachts ist GTI `0.0` und damit
vorhanden; ein vollständiger Tag hat 24. **Bei Gleichstand behält das gewählte Modell den
Vorrang**, sonst nähme der Fix stillschweigend die Modellwahl weg. Deckt auch `best_match` den
Tag nur teilweise ab, bleibt er teilweise — die fehlenden Felder bleiben leer, statt zu 0 zu
werden (ADR-002/**P4**). SoT: `solar_forecast_service._gti_abdeckung_je_tag` und
`_merge_nach_abdeckung`; der Ein-Abruf-Zweig (`tage ≤ Reichweite`) holt `best_match` in diesem
Fall nach, sonst wäre die Regel dort blind.

> ⚠ Die Snapshot-Begrenzung auf den Modellhorizont (`wetter/cache.snapshot_days`, Auflage E15-a) nimmt der Kaskade nur
> die **ganz leeren** Tage jenseits der Reichweite (sie spart Abrufe und hält den Cache-Kanon); den **angeschnittenen** Tag
> am Rand löst allein die Abdeckungsregel oben.

**„Keine Daten" schließt die leere Antwort ein.** Open-Meteo kann für ein Modell mit HTTP 200 antworten und trotzdem für jede Stunde `null` liefern; `_hat_nutzbares_gti` behandelt das wie einen Fehlschlag, damit die `best_match`-Kaskade greift statt einen 0-kWh-Tag zu bauen. Drei der acht wählbaren Werte bedient Open-Meteo nicht mehr (gemessen: `ecmwf_ifs04` antwortet mit HTTP 200 ohne einen Stundenwert, `ecmwf_seamless` und `meteoswiss_seamless` mit HTTP-Fehler) — sie rechnen faktisch mit `best_match`; die Auswahlliste führt sie weiter.

### 4.1b Solar Forecast ML (SFML)

**Endpoint:** `GET /api/aussichten/prognosen/{anlage_id}` (Prognosen-Vergleich) und `GET /api/live/{anlage_id}/wetter` (Live-Cockpit).
**Quelle:** die Home-Assistant-Integration *Solar Forecast ML* (`solar_forecast_ml`) — nur im HA-Add-on, als Prognosequelle
der Anlage gewählt (`services/prognose_router.py`: „SFML pur, ohne Korrektur"; ohne erreichbare HA-Instanz Rückfall auf eedc
mit Hinweis).

SFML ist eine optionale KI-basierte Prognose-Ergänzung. Sie liefert eine zweite Tages-Prognoselinie neben der eedc-Eigenprognose und den IST-Werten — im **Prognosen-Vergleich** und im **Live-Cockpit**, nicht in der 7–14-Tage-Aussicht.

Ist SFML als Quelle gewählt, kommen **alle** Prognosezahlen des Live-Blocks aus SFML (#401): Tageswert, verbleibender Ertrag, nachgeführter Tageswert und der VM/NM-Split. Wo SFML einen Tag nicht abdeckt, steht „eedc" dabei. Ohne SFML-Stundenprofil gibt es **keinen** verbleibenden Ertrag — er würde sonst aus der Kurvenform einer anderen Quelle entstehen.

#### Datenfluss

```
1. Erkennung der SFML-Sensoren über die Integration (services/prognose_discovery.py, Rolle aus der unique_id —
   Kaskade in ha_integration_aufloeser.py, #401)
2. Tageswerte und Stundenprofil aus den Sensoren lesen
3. je Tag persistieren (Schreibstelle api/routes/live_wetter.py, derselbe Lauf wie der Day-Ahead-Schnappschuss §6b):
   TagesZusammenfassung.sfml_prognose_kwh und .sfml_prognose_stundenprofil (24 Backward-Slots, erster Wert bleibt)
```

#### Response-Felder (pro Tag)

```
PrognosenVergleichResponse — gefüllt nur, wenn SFML die gewählte Quelle ist:
  sfml_verfuegbar                                       ohne ihn keine SFML-Spalte
  sfml_heute_kwh · sfml_morgen_kwh · sfml_uebermorgen_kwh
  sfml_stundenprofil                                    24 StundenProfilEintrag (Backward-Slots)
  sfml_tageshaelften                                    Vormittag/Nachmittag je Tag
```

#### Abweichungsberechnung (Prognose-Vergleich)

SFML wird angezeigt, aber **nicht eingewertet**: keine Δ-Spalte neben dem Wert und kein Platz im Genauigkeits-Ranking
(MAE/MBE kennen OM, eedc, Solcast); im 7-Tage-Vergleich stehen heute und morgen, nichts Vergangenes (Probe
`PrognoseVergleichTeile.stundenvergleich.test.tsx`). Die Δ der übrigen Quellen: Absatz *Abweichung und Σ-Zeile* unten.

### 4.1c Prognose-Vergleich (Auswertungen → Prognose)

Anzeige: [Auswertungen → Prognose (Genauigkeit gegen IST)](HANDBUCH_BEDIENUNG.md#43-prognose-genauigkeit-gegen-ist) — fachlich beschrieben im [Handbuch Prognosen](HANDBUCH_PROGNOSEN.md).

**Endpoint:** `GET /api/aussichten/prognosen/{anlage_id}`
**Service:** `api/routes/prognosen.py`, `services/solcast_service.py`

Der Prognosen-Tab vergleicht vier Quellen pro Tag/Stunde:

| Quelle | Bedeutung |
|---|---|
| **OpenMeteo (OM)** | Wetterbasierte Roh-Prognose aus GTI × kWp × (1 − System_Losses) je Orientierungsgruppe: Tageswert, Stundenkurve „OpenMeteo (roh)" und Summenzeile sind deckungsgleich (v4.0.1). Ab Tag 4 trägt die Tageszeile die Tagesformel aus §4.1 (GHI, N-317). |
| **eedc (kalibriert)** | die anlagenspezifisch korrigierte Prognose — korrigiert wird **pro Stunden-Slot auf der Energie**, nicht mit einem Tagesfaktor. |
| **Solcast** | Optionale dritte Quelle, entweder Solcast-API (Free/Paid Key) oder HA-Sensor (BJReplay-Integration). 30-Min-Buckets werden per `ceil(bucket_ende)` dem Backward-Slot zugeordnet — die API liefert `period_end` (`backward_slot_aus_period_end`), die HA-Integration `period_start` (`backward_slot_aus_period_start`: volle Stunde des Beginns + 1 h; für 30-Min-Buckets derselbe Slot). Der HA-Pfad im Einzelnen: Absatz „Solcast über die HA-Integration" unten. |
| **IST** | Tatsächlich gemessener Tageswert aus den Stunden-Snapshots (siehe §6b) |

**Solcast über die HA-Integration** (`solcast_service.py::_fetch_solcast_ha_auto`, Cache 5 min): die sieben
Tages-Sensoren (heute … Tag 7, gefunden über `ha_integration_aufloeser.py`) werden in einem Abruf gelesen; je Sensor:

```
Tageswert_d      = State des Sensors, 1 Nachkommastelle (unknown/unavailable/leer/keine Zahl ⇒ der Tag fehlt)
p10_d / p90_d    = Attribut estimate10 / estimate90, 1 Nachkommastelle; fehlt oder leer ⇒ 0
Slot_d[s]        = Σ pv_estimate × 0,5 über die 30-Min-Buckets aus detailedForecast (Leistung in kW → Energie in kWh),
                   s = backward_slot_aus_period_start(period_start); ein Bucket zählt nur, wenn sein Slot auf den Tag
                   SEINES Sensors fällt (#357) — 23:00/23:30 gehören zu Slot 0 des Folgetags und fallen dort weg
                   (p10/p90 ebenso aus pv_estimate10/pv_estimate90; fehlt ein Wert ⇒ 0); Slots auf 2 Stellen
Stundenprofil_d  nur, wenn ein Slot ≠ 0; Heute-Sicht hourly_kw = Profil von heute, sonst 24 × 0
Morgen           = der Tag mit Datum heute + 1 (wie der direkte API-Pfad); ist der Morgen-Sensor nicht lesbar ⇒ 0 (N-776)
```

Der Auflöser `ha_integration_aufloeser.py::loese_integration_auf` rechnet nicht: er ordnet die Entitäten der
Integration je Rolle in drei Stufen zu (unique_id → Anzeigename → Entity-ID-Muster, der erste Treffer bleibt; RF-78:
`_stufe_unique_id`, `_stufe_name`, `_stufe_muster`). Ohne Heute-Sensor (nicht gefunden oder nicht lesbar) liefert der
Pfad keine Prognose. `period_start` ohne Zeitzone
gilt als Europe/Berlin. Code-Orte (RF-77): Phasen `_lese_states`, `_tageswerte_aus_states`, `_stundenprofil_aus_detail`,
`_heute_morgen`.

#### Abweichung und Σ-Zeile im Stundenvergleich (ab v4.0.6)

Die Tabelle „Stundenvergleich heute" annotiert jeden Prognosewert mit seiner Abweichung zum IST **derselben** Stunde. Zwei Regeln, beide client-seitig in `components/prognose/PrognoseVergleichTeile.tsx` (`DevBadge` bzw. `stundenSummeVon`), gepinnt in `PrognoseVergleichTeile.stundenvergleich.test.tsx`:

```
Δ_Stunde   = Prognose_kWh − IST_kWh            (angezeigt: |Δ|, Richtung als ▲/▼, „±" wenn |Δ| < 0,05)
Δ_relativ  = |Δ| / IST × 100                   (nur für die Farbskala bzw. die Σ-Zeile; IST > 0,05 vorausgesetzt)
```

- **Liegt ein IST vor, wird immer annotiert** — auch bei Δ = 0. Eine fehlende Annotation bedeutet damit eindeutig „keine Messung", nicht „kleine Abweichung".
- **Die Σ-Zeile summiert über ein gemeinsames Fenster.** Obergrenze ist die letzte Stunde mit IST, höchstens `aktuelle_stunde` (Slot `aktuelle_stunde + 1` läuft noch, s. Backward-Konvention). Stunden **ohne** IST bleiben in allen vier Spalten außen vor — die vier Summen meinen damit paarweise dieselben Stunden.
- **Ohne jedes IST** (Zukunftstag) zeigt die Σ-Zeile die volle Prognosesumme und **kein** Δ — ADR-002/P4: kein 0-%-Ergebnis auf einer nicht vorhandenen Referenz. Sind alle 24 Stunden gemessen, entfällt die `bis HH:00`-Kennzeichnung.

Nicht zu verwechseln mit der **Tagesprognose** derselben Spalte (`openmeteo_heute_kwh` etc.) in der Kennzahl-Matrix — die bleibt der ganze Tag, ebenso `verbleibend_*` (= IST bisher + Σ Prognose-Slots der Reststunden).

#### Lernfaktor (saisonale MOS-Kaskade, ab v3.16.15)

Die eedc-Prognose ist die korrigierte OpenMeteo-Prognose; der Skalar-Lernfaktor unten ist die
**gröbste Stufe** der Korrektur-Kaskade (feiner: Sonnenstand × Wetter je Stunden-Slot, siehe
[Prognosen §5.3](HANDBUCH_PROGNOSEN.md#53-das-korrekturprofil-sonnenstand--wetter)). Der Lernfaktor wird aus historischen `(Prognose, IST)`-Tag-Paaren berechnet — nur Tage mit gültiger OpenMeteo-Prognose **UND** IST-Ertrag > 0.5 kWh fließen ein (Schlechtwetter-Tage mit ~0 kWh würden den Faktor sonst verzerren).

```
faktor = Σ(IST_kWh) / Σ(EEDC_Roh_Prognose_kWh)
```

> ⚠ **Der Skalar-Lernfaktor hier ist der LEGACY-Faktor** (`live_wetter._get_lernfaktor_detail`) und liest `pv_prognose_kwh`, also die **ungekappte** Rohprognose. Die Skalar-Stufe des **Korrekturprofils** (Stufe 4 der Kaskade) rechnet seit N-547 gegen `lern_soll_kwh`, also gegen die **gekappte** Summe.
>
> ⭐ **Es gibt ihn deshalb ZWEIMAL — einmal je Bezugsgröße (N-551).** Ein auf der rohen Prognose gelernter Faktor rechnete auf einer an der Wechselrichter-Grenze **gekappten** Reihe die Abregelung ein zweites Mal heraus; ein bloßer Nenner-Tausch wäre falsch, denn **vier** Leser wenden denselben Faktor auf die **rohe** Basis an (Prognosen-Vergleich, Energieprofil-Tages-SOLL, Tagesprognose, Kanon-Schätzpfad; das Genauigkeits-Tracking bis N-782 als fünfter). Darum: `faktor` = Σ IST / Σ `pv_prognose_kwh`; daneben `faktor_gekappt` = Σ IST / Σ `lern_soll_kwh` über die Tage **derselben** Kaskadenstufe, die das Feld tragen (Gate ≥ 7 Tage, sonst kein zweiter Faktor). Den gekappten nimmt **nur** der Kanon-Fallback, die Stelle, die auf gekappte Slots trifft. Ohne Kappung sind beide Zahlen gleich.

eedc nutzt eine **saisonale Kaskade** mit den jeweils vorhandenen Daten:

| Stufe | Bedingung | Bezugszeitraum |
|---|---|---|
| **Monatsfaktor** | ≥ 15 gültige Tage im selben Kalendermonat | Tage des Kalendermonats über alle Jahre |
| **Quartalsfaktor** | ≥ 15 gültige Tage im selben Quartal | Tage des Quartals über alle Jahre |
| **30-Tage-Fenster** | ≥ 7 gültige Tage | Letzte 30 Kalendertage |
| **Inaktiv** | < 7 Tage | Lernfaktor = 1.0, eedc-Spalte gedämpft mit `—` und Tooltip-Verweis |

Die aktive Stufe wird im Status-Banner und im KPI-Card-Header angezeigt.

**Restzeit-Banner (v3.22.0):** Wenn die 7-Tage-Schwelle noch nicht erreicht ist, zeigt das Banner: „X von 7 Tagen, noch Y Tage" — Y berücksichtigt nur Tage mit gültiger Prognose UND IST > 0.5 kWh, also dieselbe Filterregel wie der Faktor selbst.

**Persistierung:** Lernfaktor pro Quelle separat gecacht. Backfill-Kandidat-Felder (`pv_prognose_kwh`, Solcast-Tageswerte) schreibt der **Prefetch-Job** alle 45 Min in `TagesZusammenfassung` (v3.16.14) — unabhängig vom Seitenbesuch, sonst entstünde ohne Besuch kein Lernfaktor.

#### Das Korrekturprofil: vier Stufen aus den Stundenpaaren (`korrekturprofil_aggregator.py`)

Der nächtliche Aggregator (`aggregiere_korrekturprofil_anlage`, Aufrufer Scheduler und `POST …/korrekturprofil`)
lernt je Anlage vier Profile; der Lookup nimmt die feinste Stufe, die ihr Gate erreicht. SOLL ist das **Lern-SOLL**
(gekappt, unkorrigiert, N-547, siehe §6b), IST die Stundenzeile bzw. an einem Kanal-Tag die Mischzeile (S5-R1).

```
Lookback           = 730 Tage vor dem Stichtag (Default heute)
Stunden-Stichprobe = Stunde mit Day-Ahead-Snapshot des Tages, IST ≥ 0,05 kW und SOLL ≥ 0,05 kWh,
                     PV-Spanne der Zeile = 1 (eine Zählerlücken-Stunde fällt aus, bleibt in jeder Summe — §6b, §2)
Faktor(Bin)        = clamp(Σ IST / Σ SOLL, 0,5, 1,3), gerundet 0,001;  Σ SOLL < 1 kWh ⇒ kein Faktor
Stufe 1  sonnenstand_wetter : Bin (Azimut, Elevation, Wetterklasse klar|diffus|wechselhaft); Sonne über dem Horizont
                              und Wetterklasse bestimmbar
Stufe 2  stunde (Variante A): Zelle (Monat, Stunde) — die Stunde braucht keinen Sonnenstand (Dämmerung zählt);
                              Saisonbin-Kaskade je Zelle: Monat ≥ 15 Stunden-Tage → Quartal ≥ 15 → Gesamt (letzte
                              30 Tage) ≥ 7, sonst keine Zelle — der Schlüsselraum bleibt Monat 1–12
Stufe 3  sonnenstand        : Bin (Azimut, Elevation), Sonne über dem Horizont
Stufe 4  skalar (O1+O2)     : je Tag q = Σ IST / lern_soll_kwh; Gewicht = SOLL × 1,30 für Tage < 30 Tage alt, sonst × 1;
                              je int(n × 0,1) kleinste und größte q fallen weg (Trim); Faktor = clamp(Σ q·w / Σ w, 0,5, 1,3)
Status             = "skipped" ohne Koordinaten oder wenn keine Stufe einen Wert hat; sonst Zählungen und
                     tage_eingegangen = Tage mit Sonnenstand-Stichprobe, ohne solche die Skalar-Tage
```

Dieselbe Kaskade Monat → Quartal → 30 Tage mit 15/15/7 trägt der Skalar-Lernfaktor oben; hier gilt sie je
(Monat, Stunde)-Zelle. Bestandsprofile wechseln je Bin erst auf das neue Lern-SOLL, wenn das Gate der Stufe mit
neuen Datenpunkten erreicht ist (Keep-Regel N-547, §6b). Code-Orte (RF-85): `_tage_und_snapshots`
(Lookback, Snapshots, Filter; `_akkumuliere` füllt die Pools) · `_stufe_sonnenstand_wetter` und
`_stufe_sonnenstand` (beide über `_flache_faktoren`) · `_stufe_stunde` (Kaskade `_stunde_zelle`) · `_stufe_skalar`
· `_ergebnis`.

#### Korrektur nur, wenn sie hilft

Die Korrektur (Kaskade oben) soll die OpenMeteo-Rohprognose **verbessern**. Ein Wächter prüft das je Anlage einmal am
Tag (`services/prognose_korrektur_nutzen.korrektur_nutzen`, Tagescache; Regel im Layer
`core/berechnungen/prognose_korrektur_nutzen.korrektur_aussetzen`) über die letzten 30 Tage vor heute, Zeitpunkt
Day-Ahead:

```
je Tag (ohne Zählerlücken-Tage, IST > 0,5 kWh):  e_kaskade = (Σ Kaskaden-Reihe − IST) ÷ IST
                                                  e_roh     = (Σ lern_soll_stundenprofil_kwh − IST) ÷ IST
gepaart nur Tage, an denen beide einen Fehler haben;  MAE_kaskade, MAE_roh wie im Genauigkeits-Tracking
aussetzen,          wenn MAE_kaskade > MAE_roh + 2 Punkte
wieder einschalten, wenn MAE_kaskade ≤ MAE_roh + 2 − 1 Punkte;  dazwischen bleibt der Zustand des Vortags
nie aussetzen unter 14 gepaarten Tagen und nie ohne beide MAE
```

Kaskaden-Reihe ist `pv_prognose_kaskade_stundenprofil` (first-write wie die übrigen Day-Ahead-Profile, **immer** die
Kaskade); für Tage vor dieser Spalte die gezeigte Reihe `pv_prognose_stundenprofil` (bis dahin identisch, weil nie
ausgesetzt). **Ausgesetzt** heißt: der Kanon rechnet für alle Tage des Horizonts mit Faktor 1,0 (die gekappte Rohreihe;
ohne Stundenprofil der Tageswert ohne Skalar) — Tageswert, Stundenprofil, Rest, Sensoren und `pv_prognose_stundenprofil`
zeigen dann OpenMeteo roh. Die Kaskade wird trotzdem gerechnet und eingefroren, damit der Wächter weiter misst und die
Korrektur von selbst wieder einschaltet. **Das Lernen ist unberührt:** der Aggregator lernt weiter gegen das Lern-SOLL.
Toleranz, Hysterese und Mindesttage sind Annahmen (Konzept 9.11.2026 §7, Zielmarke Z1 «nie dauerhaft schlechter als
OpenMeteo roh»). Sichtbar: Live-Antwort `korrektur_status`, Genauigkeits-Antwort `korrektur_status` (Kopfzeile in
*Auswertungen → Prognose*, Block ④, nur wenn ausgesetzt), HA-Attribute `korrektur_ausgesetzt`,
`korrektur_mae_30_prozent`, `roh_mae_30_prozent` am Sensor `eedc_prognose_heute_kwh`.

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

**Welcher Prognosewert (N-782, 9.11.2026; «Mittag» seit Päckchen CC).** `Prognose_kWh` ist je Quelle der Stand eines
festen **Zeitpunkts** (Query `zeitpunkt`, Standard `day_ahead`; Auswahl in
`services/prognose_genauigkeit_service.prognosen_zum_zeitpunkt`):

| Quelle | Day-Ahead (Σ des first-write-Stundenprofils) | Mittag (first-write ab 12:00) | Abend (eingefrorener Tageswert) |
| --- | --- | --- | --- |
| eedc | `pv_prognose_stundenprofil` — die angezeigte Kanon-Reihe | `pv_prognose_eedc_mittag_kwh` = `heute_rollend_kwh` (IST bisher + nachgeführter Rest) | `pv_prognose_eedc_final_kwh` (ab N-782, älter NULL) |
| OpenMeteo | `lern_soll_stundenprofil_kwh` — roh, **gekappt** | `pv_prognose_om_mittag_kwh` = `KanonTag.om_kwh` des Laufs — roh, **gekappt** | `pv_prognose_final_kwh`, Fallback `pv_prognose_kwh` — roh, **ungekappt** |
| Solcast | `solcast_prognose_stundenprofil` | `solcast_mittag_kwh` (per Satellit nachgeführt) | `solcast_prognose_kwh` (letzter Schreiber, per Satellit nachgeführt) |
| SFML (nur Wert, keine Kennzahl) | `sfml_prognose_stundenprofil` | `sfml_mittag_kwh` (nur die Live-Sicht schreibt) | `sfml_prognose_kwh` |

**Mittag** ist der Stand des ersten Laufs ab 12:00 lokal (`live_wetter._mittag_einfrieren`, je Spalte first-write): der
Prefetch läuft alle 45 Minuten und schreibt also bis 12:45, die Live-Sicht schreibt, wenn sie vorher geöffnet wird. Er
vergleicht, was die Quellen um die Tagesmitte wissen — eedc das gemessene IST des Vormittags plus den nachgeführten Rest, Solcast
seine Satelliten-Nachführung, OpenMeteo den Modelllauf. Rückwärts leer («nicht erhoben»).

Ohne aufgezeichneten Stand `None` („nicht erhoben"), kein Rückfall auf den anderen Zeitpunkt; ein Profil mit Σ ≤ 0 gilt
als nicht erhoben (Nullreihe = keine Daten). Ausreißer-Markierung (#296) und MAE/MBE/Asymmetrie rechnen mit den Werten
des gewählten Zeitpunkts. Bis N-782 war eedc hier `OM-Endwert × heutiger Skalar-Lernfaktor`, rückwirkend für alle
Tage. Die HA-Abweichungs-Ampel (`eedc_mae_prozent`) nimmt den eedc-Day-Ahead-Stand; ohne Day-Ahead-Profile keine Reihe
und keine Schwelle (P4). Benannte Grenze: OpenMeteo wechselt mit dem Zeitpunkt zwischen gekappter und ungekappter
Größe (an Anlagen ohne AC-Grenze gleich).

**Quellen-Empfehlung (Päckchen CC).** Die Antwort trägt je Zeitpunkt `beste_quelle` und `beste_quelle_mae_prozent`: die
Quelle mit der kleinsten MAE unter eedc, OpenMeteo und Solcast, die im Zeitraum mindestens **14 Tage** mit Tagesfehler
haben (Layer `prognose_genauigkeit.beste_quelle`; SFML nicht — Tom-HA-Regel; bei gleicher MAE eedc). Unter 14 Tagen
`None`. Die Wahl trifft das Backend, der Client zeigt den Satz; ist Solcast vorn und nicht die gewählte Quelle
(`prognose_quelle`, Einstellung), nennt er den Weg *Einstellungen → Stammdaten → Anlage* («PV-Prognose-Quelle»).

**SOLL bis zur IST-Grenze (Päckchen CC).** Die Abweichungs-Ampel (`eedc_prognose_abweichung_heute_prozent`) summiert das
SOLL über `core/berechnungen/prognose_nachfuehrung.soll_bisher_kwh` (Σ Slots bis einschließlich `ist_bisher_bis_slot`,
N-544). Im selben Modul steht der Nachführ-Faktor für «Rest heute» (`nachfuehr_faktor`, `f = clip(1 + (r − 1)·√w, 0,4,
1,6)`, Backtest Winterborn 1.9.–8.11.2026) — verdrahtet im Kanon (Kasten «Heute nachgeführt» oben). Die Grenze ist seit
N-784 an jedem Tag ein Backward-Index: an einem Kanal-Tag lag das IST bis dahin im Beginn-Raster (eine Stunde vor dem
Prognose-Slot), und die Ampel verglich das IST mit dem SOLL bis eine Stunde vorher (5.11.2026 12:30: +95 % statt +16 %).

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
- **Gebündelte Stunde (ab v4.0.51, Zählerlücken wie HA):** trägt eine IST-Stunde die Energie mehrerer realer Stunden (HA hatte davor keine Zeile), steht sie im Stundenvergleich **nicht** als Stichprobe (Slot leer, Stunde in `buendel_stunden`); ihre Energie zählt in der Tagessumme. Als unvollständig gilt der Tag nur bei einem **Mitternachtsbündel** der PV (Energie aus dem Vortag) oder bei verworfener PV, nicht bei jeder fehlenden Stunde.

### 4.2 Langfrist-Prognose (12 Monate)

**Endpoint:** `GET /api/aussichten/langfristig/{anlage_id}`

Die Kachel «Spez. Ertrag (Prognose)» (Cockpit → Aussicht) liest `spezifischer_ertrag_zeitraum_kwh_kwp` = Jahresprognose ÷ kWp
(`kennzahlen.spezifischer_ertrag_kwh_kwp`; seit Päckchen Z-Client, vorher im Client).

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

**Kappung und Zuverlässigkeit** (`api/routes/aussichten/trend.py::_degradation_kappen`, beide Strategien)
```
Degradation > 0 (Ertrag gestiegen)  ⇒  Degradation = 0,0
                                        Hinweis + „Ertragssteigerung durch Wetterschwankungen, keine messbare Degradation"
Datenjahre = vollständige Jahre (Primär) | ergänzte Jahre (TMY-Fallback)
Datenjahre ≥ 3  ⇒  degradation_zuverlaessig = true
sonst           ⇒  false, Hinweis + „Wert mit Vorsicht interpretieren (min. 3 Jahre empfohlen)"
```
Eine Ertragssteigerung ist physikalisch keine negative Degradation, sondern Wetter — deshalb 0 statt eines positiven Werts.

### 4.4 Finanz-Prognose & Amortisation

**Endpoint:** `GET /api/aussichten/finanzen/{anlage_id}`

#### Bisherige Erträge (historisch)

```
Bisherige_Erträge = Σ(Einspeisung * Vergütung / 100)         (PV)
                  + Σ(Eigenverbrauch * Netzbezug_Preis / 100)  (EV)
                  + WP_Ersparnis                                 (vs. Alternative)
                  + E-Auto_Ersparnis                             (vs. Benzin)
                  + BKW_Ersparnis                                (Eigenverbrauch)
                  + Sonstige_Netto                               (alle Investitionstypen)
```

#### WP-Ersparnis (historisch, in Finanzen)

```
Je Wärmepumpe, die eine Heizung ersetzt (N-88: Energieträger „keiner" bringt nichts ein), je Monat:
    Wärme         = waerme_gesamt_kwh(waerme_kwh, Heizwärme, Warmwasser)      # D1, §3.5 (N-391/N-398/N-379)
    Strom         = WP-Strom − Kühlstrom (modus_strom_zeile, gemessen vor abgeleitet)   # Kühlen ersetzt keine Heizung
    Strom > 0, Wärme ≤ 0  ⇒  der Monat zählt nicht (N-670: Standby, kein Vergleich)
    Gas_Preis     = Monatsdaten.gaspreis_cent_kwh                  # Monatswert, wenn gepflegt (#141)
                  ∨ Investition.parameter.alter_preis_cent_kwh     # sonst der Wert an der WP
                  ∨ 12 ct                                          # sonst die Vorgabe (PARAM_WAERMEPUMPE_DEFAULTS = GASPREIS_DEFAULT_CENT)
    Gas_Kosten    = Wärme / η_alt(Energieträger) * Gas_Preis / 100   # 0,90 Gas · 0,85 Öl · 1,0 Strom
    WP_Netzkosten = Strom * wp_preis_cent / 100                    # der GANZE Strom (SOLL S1b); Preis des Monats, §3.5b-V (N-663)
    Ersparnis     = Gas_Kosten - WP_Netzkosten
  + alternativ_zusatzkosten_jahr × erfasste Monate / 12            # Zusatzkosten anteilig (#141)
```

> **Der ganze WP-Strom trägt den Netztarif (SOLL Wärme/Klima S1b, N-459), ohne Abschlag für den PV-Anteil.** Der PV-Strom, den die Wärmepumpe verbraucht, ist auf der PV-Seite bereits als Eigenverbrauch gutgeschrieben — ihn hier ein zweites Mal abzuziehen zählte dieselbe Kilowattstunde doppelt (ADR-002/P9). Code: `core/berechnungen/alternativkosten.py::berechne_wp_alternativkosten_ersparnis` (Aussichten, ROI-Fortschritt, Jahres-Ersparnis des HA-Exports); Begründung und Zahlenbeispiel im Kasten zur Planungsformel in [§3.5](#35-wärmepumpe-einsparung).

> **Monats-Gaspreis (v3.21.0):** Ist `Monatsdaten.gaspreis_cent_kwh` gepflegt, gilt er Monat für Monat — ein Tarifwechsel ändert nicht rückwirkend die Historie. Ohne Eintrag gilt `alter_preis_cent_kwh` der Wärmepumpe, ohne beide die Vorgabe (12 ct, `GASPREIS_DEFAULT_CENT`). Pflege in der assistierten `MonatsdatenForm` (über `BEDINGTE_BASIS_FELDER` mit `bedingung_basis: hat_waermepumpe`) — in V4 der eine Erfassungsweg.
>
> **Rechenweg neben der Zahl:** Der Tooltip im Cockpit-Detailblock und im T-Konto zeigt den Rechenweg aus demselben Layer-Ergebnis — mit den anteiligen Zusatzkosten und dem herausgehaltenen Kühlstrom, wenn es sie gibt.
>
> **Kühlstrom (Entscheid E-B; B5/X-5):** Der Strom des Kühlbetriebs (`modus_strom_zeile`, gemessen vor abgeleitet) bleibt aus dem Vergleich — Kühlen ersetzt keine Heizung. Dieselbe Regel gilt in der Monatsformel (`berechne_wp_ersparnis`) und in dieser Jahresformel (Aussichten, ROI, HA-Jahresersparnis, Vorjahresvergleich im Cockpit).

#### E-Auto-Ersparnis (historisch, in Finanzen)

```
Benzin_Kosten  = Σ_Monat km_m / 100 * Vergleich_L_100km * Benzinpreis_m   # Kraftstoffpreis des Monats ∨ Parameter ∨ 1,65 €/L (#260)
Strom_Kosten   = Heim-Netzladung * Netzbezug_Preis / 100
               + Heim-PV-Ladung  * EV_Preis        / 100                   # N-672: Preis der Eigenverbrauchs-Ersparnis des Monats
               + Kosten externer Ladung
Fossile_Kosten = km_Verbrenner / 100 * eigener_Verbrauch * Benzinpreis     # nur Plug-in-Hybrid (#331), sonst 0
Ersparnis      = Benzin_Kosten - Strom_Kosten - Fossile_Kosten
```

#### Monatsprognose (zukünftig)

Für jeden Prognosemonat:
```
PV_kWh             = PVGIS_Monatswert (oder TMY * kWp * 0.85)
Basis_EV            = PV_kWh * Basis_EV_Quote   (historisch ermittelt, 15-70%)
Speicher_Beitrag    = Ø_Speicher_Entladung * PV_Faktor
V2H_Beitrag         = Ø_V2H_Entladung (konstant)
WP_PV_Anteil        = WP_Strom * PV_Anteil_gepflegt * sqrt(PV_Faktor) * Normierung

Eigenverbrauch      = min(Basis_EV + Speicher + V2H + WP_PV, PV_kWh)
Einspeisung         = PV_kWh - Eigenverbrauch
Netto_Ertrag        = Einspeisung * Vergütung/100 + Eigenverbrauch * Preis/100
```

WP saisonal gewichtet:
```
WP_SAISON_FAKTOREN = {Jan: 1.8, Feb: 1.6, Mär: 1.3, Apr: 0.8, Mai: 0.4, Jun: 0.2,
                      Jul: 0.2, Aug: 0.2, Sep: 0.4, Okt: 0.8, Nov: 1.3, Dez: 1.7}
WP_Strom_Monat = WP_Strom_Durchschnitt * Saison_Faktor

Normierung     = Σ_Monate(Saison_Faktor) / Σ_Monate(Saison_Faktor * sqrt(PV_Faktor))
```

> ⚠ **`WP_PV_Anteil` hat zwei Bestandteile, die leicht verwechselt werden.**
> `PV_Anteil_gepflegt` ist der am Gerät eingetragene *PV-Anteil (%)* (Vorgabe 30 %, wenn nie
> eingetragen; bei mehreren Wärmepumpen ihr Mittel). Ein **geleertes** Feld ist eine Rücknahme: es
> bleibt leer (N-572: das Formular belegt es nicht vor), und das Gerät fällt
> aus dem Mittel heraus. Der Beitrag **je Gerät** rechnet in diesem Fall weiter mit 30 %.
> `sqrt(PV_Faktor)` gibt der Größe ihre **Saisonform** — im Sommer steht mehr PV zur
> Verfügung —, und die `Normierung` über die **zwölf Kalendermonate** sorgt dafür, dass
> die Jahressumme trotz dieser Form genau dem gepflegten Anteil entspricht.
>
> ⚠ Diese Größe ist eine **Mengen**-Aussage und wirkt nur im Eigenverbrauchs-Modell der
> Prognose. Auf die **Kosten** der Wärmepumpe wirkt sie nicht — siehe den Kasten in
> [§3.5](#35-wärmepumpe-einsparung).

#### Amortisation

**SoT:** `core/berechnungen/amortisation.py::berechne_amortisations_fortschritt`
(Berechnungs-Layer, ADR-001) — dieselbe Formel speist die Kachel
„Amortisations-Fortschritt" in *Auswertungen → ROI*.

```
Investition          = Σ max(0, Anschaffung − Alternative)   # relevante Kosten, §3.6

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

> **Der Fortschritt ist reine Messung** — `Jahres_Netto_Ertrag` geht ausschließlich in die
> Restlaufzeit ein. Ist er ≤ 0 (Anlaufjahr), gibt es keine Prognose statt einer geratenen;
> sind die relevanten Kosten 0, gibt es nichts zu amortisieren (0 %, nicht „fertig"). Der
> Fortschritt ist **nicht bei 100 % gedeckelt**: eine Anlage, die sich doppelt bezahlt gemacht
> hat, darf das sagen.

---

## 5. Tarif-System (Spezialtarife)

**Funktion:** `lade_tarife_fuer_anlage()` in `strompreise.py`

### Funktionsweise

1. Alle gültigen Tarife laden (`gueltig_ab <= heute` UND (`gueltig_bis IS NULL` ODER `gueltig_bis >= heute`))
2. Nach `verwendung` gruppieren (neuester zuerst)
3. Fallback-Kette:

```
waermepumpe → waermepumpe-Tarif || Tarif „Wärmepumpe und Wallbox (gemeinsamer Zähler)" || allgemein
wallbox     → wallbox-Tarif     || Tarif „Wärmepumpe und Wallbox (gemeinsamer Zähler)" || allgemein
allgemein   → allgemein-Tarif   || Vorgaben (unten)
```

### Verwendung in Berechnungen

| Komponente | Tarif-Key | Preis-Feld |
|-----------|-----------|-----------|
| PV Einspeisung/EV | `allgemein` | `einspeiseverguetung_cent_kwh`, `netzbezug_arbeitspreis_cent_kwh` |
| Wärmepumpe Strom | `waermepumpe` | `netzbezug_arbeitspreis_cent_kwh` |
| Wallbox/E-Auto Ladung | `wallbox` | `netzbezug_arbeitspreis_cent_kwh` |
| Grundpreis | `allgemein` + eigener `waermepumpe`/`wallbox`-Tarif (N-769, kein Rückfall) | `grundpreis_euro_monat` (Σ) |
| Stromrechnung, Anteil zum Komponenten-Tarif | eigener `waermepumpe`/`wallbox`-Tarif + gemessenes Feld „Netzbezug zum WP-/Wallbox-Tarif" (N-770/N-771) | `netzbezug_arbeitspreis_cent_kwh` der Komponente (Kaskade wie WP-Kosten bzw. Netzladung) |

### Hardcoded Defaults (wenn kein Tarif)

```text
Netzbezug_Preis    = NETZBEZUG_DEFAULT_CENT             (core/wirtschaftlichkeit_defaults.py)
Einspeisevergütung = EINSPEISEVERGUETUNG_DEFAULT_CENT
Grundpreis         = 0 EUR/Monat                        (ohne Tarif kein Grundpreis)
```

### Dynamischer Tarif / Monatlicher Ø-Strompreis

Für Nutzer mit dynamischem Stromtarif (z.B. Tibber, aWATTar) kann der tatsächliche monatliche Durchschnittspreis verwendet werden statt des festen Tarifpreises.

**Die Kaskade des Monatspreises** (`services/strompreis_aggregator.py::aufgeloester_monatspreis`):

```text
1. abgerechnet  Monatsdaten.netzbezug_durchschnittspreis_cent (aus deiner Rechnung)
2. gemessen     Ø der mitgeschriebenen Stundenpreise, verbrauchsgewichtet
3. zeitfenster  bei HT/NT der über den Netzbezug gewichtete Tarifpreis
4. stamm        Strompreis.netzbezug_arbeitspreis_cent_kwh
```

Jede gelieferte Zahl trägt ihre **Herkunft** (`netzbezug_preis_herkunft`) und bei
Stufe 2 zusätzlich die **Abdeckung** — ein Ø aus 40 % der Stunden hat dieselbe
Herkunft wie einer aus 98 %, aber nicht dieselbe Belastbarkeit.

> **Die Tages- und Stundenebene rechnet mit ihren eigenen Preisen.** Ein abgerechneter Monatswert ist die Wahrheit über
> **den Monat**; er ist keine Aussage über einen einzelnen Tag. Wo Stundenpreise mitgeschrieben sind, bildet eedc die
> Tageskosten deshalb als **Summe der Stunden-Kosten** (Preis der Stunde × Menge der Stunde) und den Tages-Ø als deren
> Quotienten — nicht als Tagesmenge × Monatspreis.
>
> Die Slot-Kaskade lautet: **gemessener Stundenpreis → abgerechneter Monats-Ø
> (über den Monat verteilt) → Vertragspreis → kein Wert.** Bei Festpreis und
> Zeitfenstern ist der Stundenpreis aus dem Vertrag *ableitbar*.
>
> ⚠ **Folge:** Σ der Tageskosten kann vom abgerechneten Monatsbetrag
> **abweichen**. Das ist gewollt — die Messung sagt, *wann* das Geld angefallen
> ist, und wird nicht auf die Abrechnung skaliert. Eine große Abweichung ist
> umgekehrt ein Hinweis: entweder ist die Stundenerfassung lückenhaft oder der
> eingetragene Abrechnungswert falsch.

**Konfiguration:**

- In der [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) kann ein HA-Sensor (oder MQTT-Topic) für das Feld `strompreis` zugeordnet werden
- Im [Monatsdaten-Formular](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss) wird der Ø-Preis als Vorschlag angezeigt und ist dort manuell editierbar

> **Der Jahres-Ø ist mengengewichtet.** Die Jahres-/Gesamt-Kachel „Ø-Preis Netz" (und ebenso die Ø-Einspeisevergütung) rechnet `Σ(Preis_Monat × Menge_Monat) / Σ Menge_Monat` — nicht das arithmetische Mittel der Monatspreise. Gewichtet wird der **effektive** Monatspreis — das Ergebnis der vollen Kaskade des Monats (abgerechneter Ø → gemessene Stundenpreise → Zeittarif HT/NT → Tarif-Arbeitspreis), also genau der Preis, den die Monatskachel zeigt und mit dem der Monat seine Kosten rechnet. Die Faltung überspringt keine Stufe der Kette (N-680) — sonst passte der Jahres-Ø nicht zur Kostenzeile derselben Kachel, und ein Jahr mit dynamischem Tarif fiele auf den Referenzpreis zurück, obwohl die Kosten darunter mit dem Stundenpreis gerechnet sind. Monate ohne Menge fallen aus Zähler und Nenner; gibt es im Zeitraum überhaupt keine Menge, bleibt das arithmetische Mittel als Rückfall stehen, statt die Kachel zu leeren. **Ohne die Gewichtung passte der Kopfwert nicht zu den kWh und Euro darunter** — ein teurer Winter- und ein billiger Sommermonat wögen gleich viel.

---

## 6. Investitionstyp-spezifische Berechnungen (ROI-Dashboard)

**Endpoint:** `GET /api/investitionen/roi/{anlage_id}`

### PV-System-Gruppierung (3-Pass)

```
Pass 1: Trägergeräte registrieren → pv_systeme[traeger_id]: jeder Wechselrichter und jedes Balkonkraftwerk,
        an dem ein PV-Modul oder Speicher hängt (F-33, #381; ein BKW ohne Kinder bleibt standalone)
Pass 2: PV-Module und Speicher via parent_investition_id dem Träger zuordnen (Speicher am Träger = DC-gekoppelt);
        ein PV-Modul ohne Träger → orphan_pv_module (eigene Zeile „ohne WR")
Pass 3: Verbleibende Investitionen (AC-Speicher, BKW ohne Kinder, E-Auto, Wärmepumpe, Wallbox, Sonstiges) → standalone

PV-Einsparung wird proportional nach kWp auf Module verteilt:
    Modul_Einsparung = Gesamt_PV_Einsparung * (Modul_kWp / Gesamt_kWp)
```

> **Der Eigenverbrauch der PV-System-Zeile kommt aus den Monats-Fakten (N-723).** Je Monat der
> Anlagen-Eigenverbrauch wie im Cockpit (`kennzahlen.eigenverbrauch_kwh`: Erzeugung hinter dem Zähler **inklusive**
> sonstiger Erzeuger, abzüglich Abgabe an Dritte, Speicher nach der Bilanzformel) **minus** der Anteil der
> Balkonkraftwerke (`bkw_eigenverbrauch_anteil`, dieselbe Zahl wie im BKW-Hub) — das Balkonkraftwerk hat seine eigene
> ROI-Zeile (ADR-002/P9). Dann ohne die bewertbaren Wandlungsverluste (P15) und hochgerechnet wie die Mengen; PV-Zeile +
> Speicher-Zeile ergeben die Cockpit-Ersparnis. ⚑ Nicht abgezogen ist die V2H-Rückspeisung, die zusätzlich parametrisch in der
> E-Auto-Zeile steht.

#### Speicher-Anteil aus dem PV-Topf (F-37, seit v4.0.20)

Der PV-Topf (`Eigenverbrauch × Strompreis + Einspeisung × Vergütung`) enthält schon alles, was durch einen Speicher
lief — was in den Akku ging und wieder heraus, wurde nicht eingespeist. Deshalb bekommt jeder Speicher seinen PV-Anteil
**aus** dem Topf, nicht daneben (Zerlegung statt Addition, dieselbe Doktrin wie `aussichten/finanz_zerlegung.py`):

```
Speicher_PV_€   = Σ pv_anteil_euro      aller Speicher der Anlage   (`_speicher_roi`, IST- oder Prognose-Modus)
Speicher_CO2_kg = Σ co2_einsparung_kg   aller Speicher der Anlage
PV_Topf_€'      = max(0, PV_Topf_€  − Speicher_PV_€)
PV_CO2_kg'      = max(0, PV_CO2_kg  − Speicher_CO2_kg)
Modul_Einsparung = PV_Topf_€' · (Modul_kWp / Gesamt_kWp)          (Gesamt_kWp inkl. Module ohne Träger)
```

| Feld | Quelle |
|------|--------|
| `pv_anteil_euro` | `berechne_speicher_ersparnis` — nur der PV-Anteil; der **Netz-Anteil** (Arbitrage) steckt nicht im Eigenverbrauch und wird nicht gekürzt |
| Speicher | **alle** Speicher der Anlage — DC am Träger (Systemzeile) und eigenständige AC-Speicher (eigene Zeile), die Kürzung steht vor beiden |
| `Modul_kWp` | `get_pv_kwp` (ADR-002/P3-a); ein Modul ohne Nennleistung bekommt 0 € und 0 kg |

Die Klemmung bei 0 greift bei dünner oder widersprüchlicher Datenlage, wenn der zugerechnete Speicher-Anteil über der
ganzen PV-Ersparnis liegt: die Module stehen dann mit 0 statt einer negativen Zeile, und die Summe der Zeilen liegt nicht
über der physikalischen Menge.
Code: `api/routes/investitionen/roi_pv.py::_f37_speicher_aus_pv_topf`
(Phase von `pv_systeme_zeilen`, RF-43). Gesichert durch `test_roi_summe_symmetrie_f37.py`.

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

Stunden-kWh entstehen als **Differenz kumulativer Zähler-Snapshots**, nicht aus integrierten Leistungs-Samples — analog zum HA Energy Dashboard.

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

Wenn ein Snapshot fehlt (Scheduler-Ausfall, HA-Statistics-Timeout, MQTT-Cache leer), interpoliert eedc linear zwischen den vorhandenen Nachbar-Stunden (`snapshot/aggregator.py::_fill_gaps_linear`) — die Energie der Lücke verteilt sich auf ihre Stunden, statt als Spike in der nächsten zu stehen:

```
snap[h] = snap[a] + (snap[b] − snap[a]) × (h − a) / (b − a)      a < h < b, a und b die belegten Nachbarn
```

Ränder (h0 fehlend am Tagesanfang, h24 am Tagesende) werden **nicht** extrapoliert — der Wert bleibt None und die betroffene Stunde fällt aus der Delta-Bildung. Tagessumme bleibt in jedem Fall korrekt (`snap[24] − snap[0]`).

> ⚠ **Die Interpolation gilt nur innen und nur im Zählerstands-Pfad** („Zählerlücken wie HA", v4.0.51) (Standalone/MQTT ohne HA-Statistik, `snapshot/aggregator.py`). Im HA-Pfad wird nichts aufgefüllt: die Energie einer fehlenden Stunde steht wie im HA-Energie-Dashboard in der Stunde danach (Bündel mit Spanne `n`), und der Rand am Tagesanfang wird über den letzten vorhandenen Stand davor verankert — auch in diesem Pfad, statt die erste Stunde auszulassen. Regeln und Leser: Abschnitt *Zählerlücken wie HA* weiter unten.

**HA-Statistics-Toleranz (v3.20.0, #145):** **10 min**. Wenn die Zielstunde in HA-Statistics noch nicht vorhanden ist, schreibt der Job nichts (statt einen Nachbar-Wert zu liefern, der Slot N als 0 und Slot N+1 als 2-Stunden-Delta entstehen ließ). Der nächste `aggregate_day`-Lauf 15 Min später holt den Wert via Self-Healing nach.

**Restart-Recovery (v3.23.0):** Beim Scheduler-Start läuft `sensor_snapshot_startup_recovery()` im Hintergrund — holt für die letzten 6 Stunden je Anlage HA-Statistics-Snapshots (idempotent dank Upsert) plus für die laufende Stunde einen Live-Snapshot, anschließend `aggregate_today_all`.

**Tagesreset-Heuristik (v3.23.0):** HA-`utility_meter`-Sensoren mit täglichem Reset werfen um Mitternacht ein stark negatives Delta. Erkannt am Muster `s1 < 0.5 ∧ s0 > 0.5`, eedc nimmt dann `max(0, s1)` als Slot-0-Wert (Energie seit Reset, typ. ≈ 0 nachts). Bei untypischen negativen Deltas mitten am Tag bleibt es bei der Reset-Warnung.

**Phase D Cleanup (v3.21.0, #138):** Der Zähler-Snapshot-Pfad ist die einzige kWh-Quelle; einen W-Integration-Fallback und ein Feature-Flag gibt es nicht. Auf Anlagen ohne kumulative Zähler erscheinen Stunden-kWh-Felder als `NULL` statt geschätzter Werte.

### Backward-Slot-Konvention (ab v3.20.0, #144)

Alle Stundenzeilen des Energieprofils (`TagesEnergieProfil`) und die Prognose-Quellen folgen der
**Backward-Konvention**. Die Stunden eines **Kanal-Tags** (Tag, den der HA-Spiegel bzw. die eigene Summe für eine Gruppe
deckt) tragen seit HA-Bauform S4 ihren **Beginn** `[h, h+1)` wie HAs Statistik-Zeile (Kasten „Der Kanal-Stundentag"
unten); für die gespeicherten Stundenzeilen gilt weiter:

| Konvention | Slot N enthält Energie aus … |
|---|---|
| **Backward** (eedc, ab v3.20.0) | `[N-1, N)` — „die letzte Stunde". Slot 0 = Energie 23:00–24:00 des Vortags. |
| Forward (Strompreis, weiterhin) | `[N, N+1)` — „gilt ab jetzt". Industrieüblich für aWATTar/Tibber/EPEX. |

Industriestandard für Energie: HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber.

**Zuordnung auf Backward-Slots (v3.20.0):**
- `sensor_snapshot_service.get_hourly_kwh_by_category`: Delta `snap[h] − snap[h-1]` → Slot h.
- `solcast_service` (API + HA-Sensor): 30-Min-Buckets per `ceil(bucket_ende)` → richtigen Backward-Slot (API über `period_end`, HA-Sensor über `period_start` + 1 h, s. §4.1c). Ein Bucket am Tagesübergang `[23:00, 23:30)` heute landet damit in Slot 0 des **Folgetags**, nicht in Slot 0 von heute.
- Tagessummen und alle abgeleiteten Kennzahlen (Autarkie, PR, Lernfaktor) sind konventionsunabhängig.

#### Tageswerte: Zähler und Bezug aus einem Fenster

Aus der Backward-Konvention folgt eine zweite Regel, die **Tages**sichten betrifft: An einem **Bestandstag** deckt die
Σ der 24 Slots `[Vortag 23:00, Heute 23:00)` ab — ein Tagesgesamt per Zähler-Diff dagegen `[00:00, 24:00)`. An einem
**Kanal-Tag** deckt die Σ der 24 Stunden seit HA-Bauform S4 den Kalendertag `[00:00, 24:00)` — Bezug und Zähler-Diff
liegen dort im selben Fenster.
Beide Fenster sind 24 Stunden lang und meinen **verschiedene** 24 Stunden. Wer in *einer* Zeile eine
Teilmenge (einen Zähler) über einen Bezug stellt, muss beide im **selben** Fenster erheben, sonst ist
der Anteil keine Messung, sondern eine Rechnung über zwei Tage.

Welches Fenster gilt, entscheidet die **Herkunft des Bezugs** — nicht der Gerätetyp und nicht die
Gewohnheit. Die Tabelle steht als Code in `services/snapshot/boundary_range.py`
(`TAGESFENSTER_JE_TYP` / `tagesfenster_fuer`); sie gilt für **Bestandstage**. An einem **Kanal-Tag** ist der Bezug
(Bilanz-Ladung, Wallbox-Ladung, WP-Strom) der Kalendertag, und `tagesfenster_fuer(…, kanal_tag=True)` liefert für jeden
Typ `[00:00, 24:00)` (`for_day_total`) — dieselbe Regel N-444, angewandt auf den Bezug des Kanal-Tags (HA-Bauform S4):

| Gerätetyp | Bezug der Tageszeile | Fenster |
|---|---|---|
| Wärmepumpe | `TagesZusammenfassung.komponenten_kwh` | **bedingt**: im HA-Add-on Σ der LTS-Slots ⇒ `[Vortag 23:00, 23:00)`, im Snapshot-Pfad `[00:00, 24:00)` |
| Speicher | Σ der Ladung aus den Stundenzeilen (`batterie_kw`) | **immer** `[Vortag 23:00, 23:00)` |
| Wallbox / E-Auto | Σ der Ladeserien aus den Stundenzeilen (`komponenten`) | **immer** `[Vortag 23:00, 23:00)` |
| alles Übrige | kein Tages-Bezug hinterlegt | `[00:00, 24:00)` |

Der Leser je Tag ist `services/snapshot/aggregator.py::get_tagesdetail_kwh` (Phasen seit RF-72): `_fenster_je_typ` fragt
`tagesfenster_fuer` je Gerät, `_typ_summe` überspringt das E-Auto mit Wallbox-Parent oder mit deckender Wallbox (N-555,
`_wallbox_deckt`) und summiert je Ausgabe-Key über die Geräte des Typs, `_geraet_oder_innengeraete` liest Gerätefeld und
Innengerät-Kopien (Gerätefeld ODER Σ der Kopien, nie addiert), `_merke_grund`/`_gruende` führen den W-18-Grund (der
aussagekräftigste gewinnt; ein Grund nur für Keys ohne Wert). Proben: `test_rf71_tag_phasen.py`.

Betroffen sind die Detailwerte in *Cockpit → Tag*: die Netzladung des Speichers („davon aus dem Netz
(Arbitrage)") und die PV-/Netz-Anteile der E-Mobilität — Zähler und Bezug im selben Fenster, sonst fehlte die Ladung
zwischen 23 und 24 Uhr im einen Tag und tauchte im anderen auf. Die Wirkungsverluste kappen den Netz-Anteil auf 100 % (Layer
`speicher_bilanz.netzladung_anteil`, seit Päckchen BB im Backend; der Zähler ist
eine **Brutto**-Menge, der Bezug eine **Netto**-Menge — eine Stunde mit 2,0 kWh Netzladung und 1,5 kWh Entladung ergibt
netto 0,5 kWh); greift die Kappung, nennt der Formel-Tooltip der Zeile „Wirkungsverluste" den Grund
([ADR-002/P4](ADR-002-WURZELMUSTER.md)).

Monats-, Jahres- und Auswertungssichten sind **nicht** betroffen — sie rechnen aus den Monatsdaten
bzw. den Monats-Fakten und kennen kein Tagesfenster.

> **Eine Ausnahme: die Speicher-Netzladung im Tageswert-Rückfall der Monats-Fakten (Entscheid Gernot).**
> Ein Monat **ohne Speicher-Zeile** (laufend oder vergangen ohne Abschluss), dessen Tage Speicherwerte tragen, bekommt
> Ladung und Entladung aus der Tagesebene — und auch die **Netzladung samt Preis**, als Σ der abgelaufenen
> Tage, dieselbe Boundary-Differenz und dasselbe Fenster wie *Cockpit → Tag*: ein Bestandstag im Speicher-Fenster
> `[Vortag 23:00, 23:00)`, ein **Kanal-Tag** (`bilanz_leser.kanal_tage`, HA-Bauform S4) im Kalendertag
> (`tagesfenster_fuer(…, kanal_tag=True)` ⇒ `for_day_total`) — Σ der Tage ≡ Monat (H-3, S4-Nachlauf). Die eine
> Rechenstelle ist `services/monats_fakten/netzladung_tage.py`: `speicher_netzladung_aus_tagen` (Menge über den
> Bereichs-Leser, `TAGESDETAIL_AUSGABE` + `TAGESFENSTER_JE_TYP`, nur Tage bis gestern; ein Tag mit Rücksprung oder
> ohne Rand fehlt, ohne Netzlade-Zähler keine Menge) und `netzladung_aus_tagen` (dazu der TEP-gewichtete Ladepreis
> über `berechne_effektiver_ladepreis`, nur bei dynamischem Tarif ein Wert). Die Monats-Fakten füllen damit
> `SpeicherFakten.netzladung_kwh` und `netzladung_preis_summe_cent_kwh`/`netzladung_gewicht_kwh` — dieselbe Bedeutung
> wie mit Speicher-Zeile („Preis, zu dem die Netzladung gekauft wurde"), andere Quelle (dort der Ø der Handeingabe).
> Ohne Stundenpreis bleibt das Gewicht 0, jeder Leser fällt dann auf den Bezugspreis (`berechne_netzladung_kosten`),
> wie am Tag. *Cockpit → Monat* hat für solche Monate keinen Fakt (der Kontext lädt ohne `inkl_nur_tageswerte`,
> Ladung/Entladung kommen dort aus der Vier-Quellen-Auflösung) und ruft deshalb dieselbe Funktion für jeden Monat
> ohne Speicher-Zeile, **in dem ihr Speicherblock auch Ladung oder Entladung trägt** (Entscheid Master: keine
> halbe Anzeige — ohne HA hat ein vergangener Monat ohne Abschluss dort keine, N-472/N-677; die Fakten tragen alle
> drei aus demselben Rückfall; #427). Eine Speicher-Zeile ersetzt den Wert (P8). Proben: `test_427_netzladung_laufender_monat.py`,
> Matrix-Form M04 (`test_achsen_matrix.py`).

**Die Konvention endet nicht am Backend (v4.0.6).** Wer eine Stunde *beschriftet* oder einen Messwert
in eine Chart-Spalte *einsortiert*, folgt derselben Regel — Client-SoT ist
`frontend/src/lib/stundenSlot.ts` (Spiegel von `core/berechnungen/slot_konvention.py`, Regressionstest
`stundenSlot.test.ts`):

| Funktion | Wofür |
|---|---|
| `slotZeitspanne(h)` | Beschriftung — Slot 11 → „10:00–11:00 Uhr". **Jeder** Tooltip einer Stundengrafik. |
| `slotAusIntervallStart(h)` | Messreihen mit Slot-**Beginn**-Stempel (10-Min-Punkte des Tagesverlaufs) → Slot `h+1`. Rückgabe 24 = Slot 0 des Folgetags, **kein** Modulo. |
| `slotAusZeitpunkt("HH:MM")` | Zeitpunkt-Marker (Sonnenaufgang, Solar Noon) in den Slot, der ihn enthält — 05:56 → Slot 6. |

Regel: wer eine Stunde beschriftet oder einsortiert, nimmt die Zuordnung von dieser einen Stelle — nicht das
Beschriftungs-Symptom patchen, sondern die Stelle, die die Zuordnung konstruiert.

**Auch die Verbrauchs-Seite folgt ihr (v4.0.6).** Die gestrichelte Verbrauchs-Prognose im Live-Chart
kommt aus dem individuellen Verbrauchsprofil der letzten 7 vollen Tage
(`services/live_verbrauchsprofil_service.py`), und das hat **drei** Quellen mit Vorrang in dieser
Reihenfolge:

| Quelle | Wann sie greift | Slot-Herkunft |
|---|---|---|
| EEDC-DB (`TagesEnergieProfil.stunde`) | sobald der Scheduler mindestens zwei Tage aggregiert hat | schon backward (Aggregator schreibt über `lts_boundary_index`) |
| HA-History (Leistungsmittel je Stunde) | frische Installation, noch keine DB-Historie | `_slot_fenster` → `backward_slot_aus_period_start` |
| MQTT-Snapshots (Zähler-Delta je Stunde) | Standalone-Betrieb ohne HA | dieselbe Stelle |

Die beiden **Fallback**-Quellen ordnet **eine** Stelle im Modul zu (`_slot_fenster`), über den Backend-SoT
`core/berechnungen/slot_konvention.py` (v4.0.6);
das Abfrage-Fenster beginnt dafür eine Stunde vor Mitternacht, weil Slot 0 des ersten Tages das
Intervall `[Vortag 23:00, 00:00)` trägt. Gepinnt in
`tests/test_verbrauchsprofil_slot_konvention.py` — je eine Regression pro Fallback-Pfad plus ein
Symmetrie-Test „gleiche Wirklichkeit, drei Messarten ⇒ **ein** Profil"
(`feedback_aggregator_symmetrie`).

**Die Stunde im HA-Pfad** (`live_verbrauchsprofil_service.py::_profil_from_ha`, Phasen `_history_je_sensor`,
`_stunden_mittel`, `_verbrauch_und_wp_anteil`, `_profil_ergebnis`): je Sensor das arithmetische Mittel seiner
History-Punkte im Intervall `[h_start, h_end)` des Slots, in kW:

```
PV_h          = Σ Mittel(PV-Sensor) / 1000       leistung_w der aktiven pv-module/balkonkraftwerk; ohne einen pv_gesamt_w
Bezug_h       = Mittel(netzbezug_w) / 1000        Einspeisung_h = Mittel(einspeisung_w) / 1000
  Kombi-Sensor (nur ohne beide): Mittel ≥ 0 ⇒ Bezug_h = Mittel / 1000, sonst Einspeisung_h = |Mittel| / 1000
Verbrauch_h   = max(0, PV_h + Bezug_h − Einspeisung_h)
WP_h          = Σ |Mittel(WP-Sensor)| / 1000      (wp_werktag / wp_wochenende nur, wenn ein WP-Sensor zugeordnet ist)
Profil[slot]  = Mittel der Stichproben je Slot, 3 Stellen    Werktag = Slot-Datum Mo–Fr, Wochenende = Sa–So
```

Ein Sensor ohne Punkt in der Stunde trägt dort 0 bei; ob die Stunde überhaupt zählt, entscheidet der Netz-Beleg (N-46,
unten). Die Temperatur-Mittel je Stunde (`aussentemperatur_c`) ergeben über den Tag die Heizgradtage der Lernwoche
`referenz_hdd_kd` (N-593, wie im DB-Pfad). **N-536:** Die Entity eines Balkonkraftwerks entfällt aus der PV-Summe genau
dann, wenn **jedes** seiner `pv-module`-Kinder selbst einen Leistungssensor hat (`bkw_kinder_decken_vollstaendig`); fehlt
einem Kind die Zuordnung, bleibt das Gerät drin — sonst verlöre das Profil die einzige Quelle dieses Kindes, und der
Rest-Anteil, den es dann zu viel trägt, ist dieselbe Teil-Deckung wie im Tagespfad.

#### Temperaturkorrektur des Wärmepumpen-Anteils (N-593, N-594)

Das Profil trägt den Wärmepumpen-Anteil je Stunde (`wp_werktag` / `wp_wochenende`, Zählermenge
`TagesEnergieProfil.waermepumpe_kw`) und die Heizgradtage der Lernwoche (`referenz_hdd_kd`, Mittel der
Tages-Heizgradtage). Der Prognosetag bekommt **einen** Faktor aus dem Tagesmittel seiner Temperaturvorhersage
(`core/berechnungen/heizgradtage.py::wp_tagesfaktor`):

```
Referenz ≥ 1 Kd:  Faktor = HDD_Tag / HDD_Ref
Referenz < 1 Kd:  Faktor = 1 + max(0; HDD_Tag − HDD_Ref) × 0,15          (milde Lernwoche)
gekappt auf 0,1 … 3,0
```

Skaliert wird **nur der wetterabhängige Teil** der Stunde (`wp_strom_skaliert`):

```
fest      = Kühlen + Warmwasser         (Referenz ≥ 1 Kd)
          = Kühlen                      (milde Lernwoche: dort trägt das Profil keinen Heizanteil)
WP_Stunde = fest + (WP − fest) × Faktor     (fest gedeckelt auf WP)
```

Warmwasser und Kühlen lernt der DB-Pfad (`_profil_from_db`) als **Teilmengen** der WP-Reihe über dieselben
Stichproben (`wp_ww_<tagtyp>`, `wp_kuehlen_<tagtyp>`, nur wenn die Lernwoche eine davon trägt): aus getrennten
Leistungssensoren (`waermepumpe_<id>_warmwasser` / `_kuehlen`) oder aus dem Betriebsmodus-Etikett der Stunde × der
Stundenmenge des Geräts (Leistungssensor; bei genau einer aktiven Wärmepumpe die Zählermenge). Nie aus der Bauart
(ADR-002/P13). Keine Kühlgrenze.

Benannte Grenzen: mehrere Wärmepumpen ohne Leistungssensor ⇒ keine Trennung (die Zählermenge gehört keinem Gerät);
Betriebsart-Zähler und getrennte Strom-Zähler trennen hier nicht; das Etikett ist der überwiegende Modus der Stunde;
die Lerner aus HA-Verlauf und MQTT trennen nicht; der Sprung bei 1,0 Kd bleibt. Leser: Kachel und Live-Kurve
(`live_wetter._berechne_verbrauchsprofil`), Sensor „Verbrauchsprognose heute/morgen“ und die WP-Stundenreihe des
HA-Exports samt Heizfenster (`verbrauchsprognose_heute._rechne_tagesprognose`). Proben:
`test_n593_wp_tagesfaktor.py`, `test_n594_wp_korrektur_nur_wetterabhaengig.py`.

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
  Der Randwert ist der letzte
  Zählerstand *bei oder vor* der Grenze; benachbarte Stunden lesen denselben Wert, deshalb geht an der
  Grenze nichts verloren und nichts wird doppelt gezählt. Der Scheduler schreibt alle 5 Minuten, aber
  nicht auf die volle Stunde gerastert — daher die 6 Minuten Toleranz (Reserve für Verzug, aber nicht
  genug für einen ausgefallenen Snapshot).
- **HA zählt eine Stunde ohne Historie nicht als gemessene Null** — aus *unbekannt* würde *war nichts*, und ein einziger
  Ausfalltag drückte jeden Werktags-Slot auf 4/5 des wahren Werts. Beleg ist
  bewusst der **Netzanschluss** und dort `any` statt `all`: PV- und WP-Sensoren melden nachts bzw. im
  Stillstand stundenlang keine Zustandsänderung, ohne dass Daten fehlen, und von Bezug und Einspeisung
  bewegt sich immer genau einer. Liefert im ganzen Fenster **kein** Netz-Sensor, gibt es kein
  HA-Profil — sonst stünde die reine PV-Kurve als vermeintlicher Verbrauch da.

Ein Slot ohne jede Stichprobe fehlt im Ergebnis-Dict. Der Konsument
(`api/routes/live_wetter.py::_berechne_verbrauchsprofil`) erkennt das und setzt seine
Standard-Grundlast ein, statt still 0 kW anzunehmen — die lokale Ausprägung von
[ADR-002/P4](ADR-002-WURZELMUSTER.md).

#### Wie viele Stunden das Profil wirklich trägt

Das individuelle Profil wird ab **zwei Tagen** je Klasse (Werktag/Wochenende) verwendet — und ein
„Tag" entsteht bereits durch eine **einzige** gemessene Stunde. Zwei solcher Tage ergeben deshalb ein
Profil, dessen übrige Slots aus der Standard-Grundlast kommen. Das ist der oben beschriebene,
vorgesehene Rückfall und **kein Fehler**: Ein dünnes eigenes Profil ist besser als gar keines, und
eine schärfere Schwelle würde einer frisch eingerichteten Anlage ihr individuelles Profil wieder
wegnehmen.

Die **Tageszahl** allein („2 Tage") läse sich wie eine Aussage über
die Güte des Profils. Deshalb liefert das Ergebnis je Klasse zusätzlich die **gemessene
Slot-Abdeckung** (`slots_werktag` / `slots_wochenende`, die Route reicht sie als `profil_slots`
durch), und beide Anzeigen — die Legende in *Cockpit → Live* und der Verbrauchs-Tooltip der
3-Tage-Aussicht — nennen sie samt ihrer Folge, z. B. *„Werktag, 2 Tage, 1 von 24 Stunden gemessen —
die übrigen 23 aus der Standard-Grundlast"*. Bei voller Abdeckung entfällt der Zusatz; liefert das
Backend keine Abdeckung, bleibt es bei der Tageszahl, statt eine zu erfinden. Wortlaut-SoT beider
Anzeigen ist `lib/verbrauchsprofilHerkunft.ts`.

### Der Kanal-Stundentag (HA-Bauform, zweites Paket S3)

Die Stundenzeilen schreibt `aggregate_day` weiter wie bisher (unten). **Gelesen** werden die Stunden eines Tages aber
dort, wo die Kanäle den Tag decken, aus dem HA-Spiegel bzw. der eigenen Summe (`services/kanal/stunden_leser.py`) —
nach denselben Regeln wie die Tagessummen:

* **Eine Wahl je Tag und Gruppe** (ADR-002/P14): Bilanz (Netz · PV/Balkonkraftwerk samt Anlagenzähler · Speicher ·
  Erzeuger hinter dem Zähler), Geräte (E-Mobilität, Sonstiges), Wärmepumpe. Ein Kanal-Tag einer Gruppe liest auch ihre
  Stunden aus den Kanälen, ein Bestandstag aus den Stundenzeilen; kein Tag halb und halb. ⚑ Die Bilanz-Gruppe hält einen
  Tag mit einer Lücke über die Tagesgrenze als Kanal-Tag (Lückentag wie HA); die **Geräte- und die WP-Gruppe kennen diese
  Regel nicht** — ein 25-Stunden-Loch in einem WP-Kanal macht beide berührten Tage zu WP-Bestandstagen. Beide Wege nennen
  an solchen Tagen dieselbe Zahl aus dem Bestand (Entscheid: so belassen).
* **Kalendertag, Stunde = Beginn (seit HA-Bauform S4, R-3):** ein Kanal-Tag ist der Kalendertag `[D 00:00, D+1 00:00)`
  in der Prozesszone (`services/kanal/fenster.py::tagesfenster`), ein Kanal-Monat der Kalendermonat — Σ Kalendertage ≡
  Kalendermonat ≡ Jahr per Konstruktion, eine Monatsgrenze für alle Monatsleser. Stunde `h` ist HAs `change` der Zeile mit
  lokalem Beginn `h`, also `[h, h+1)` (`stunden_leser.stunde_des_beginns`): die Zeile `start_ts = 23:00` trägt den Stand um
  00:00 und liegt damit genau auf der Tagesgrenze. Umstellungstage: im Herbst trägt Stunde 2 beide Zeilen (Zuwachs und
  Spanne addiert), im Frühjahr bleibt Stunde 2 leer; es bleiben 24 Spalten. Jede Stunde trägt `raster = "beginn"` (die
  Stundenzeile eines Bestandstags `raster = "ende"`), das Frontend beschriftet beide als Bereich („11–12",
  `lib/stundenBereich.ts`). Gegen das Bestands-Fenster `[Vortag 23:00, 23:00)` (Backward-Raster, `lts_boundary_index`)
  unterscheidet sich ein Kanal-Tag je Kanal um die **Randstunde** `change(D 23:00) − change(D−1 23:00)`.
  **Bestandstage** bleiben, wie sie geschrieben sind (Backward-Slots, Tagesfenster `[Vortag 23:00, 23:00)`); zwischen einem
  Bestandstag D und einem Kanal-Tag D+1 fehlt die Stunde `[D 23:00, D+1 00:00)`, in umgekehrter Reihenfolge zählt sie
  doppelt (benannte Naht S4-R-3c; sie bleibt, solange ein Bestandstag neben einem Kanal-Tag liegt — Lesart 1). Fehlt eine Stunde, trägt die nächste belegte ihren Zuwachs und ihre Spanne (`spannen`, „enthält n Stunden"); eine
  Stunde ohne Zeile ist **keine 0**. HA-Kanäle wörtlich: kein Deckel, keine Reset-Regel, keine Lückenfüllung.
* **Weg 2 je Stunde:** die Bilanz-Gruppe komponiert jede Stunde mit derselben Layer-Funktion wie den Tag
  (`core/berechnungen/bilanz_zeitraum.py::komponiere_bilanz_zeitraum`, W2-R1…R5). Die Entweder-oder-Wahl des Tages gilt
  für jede Stunde; ein PV-Gerät ohne Zeile in einer Stunde ist in ihr weder gemessen noch Empfänger des Rests (sein
  Zuwachs steht in der Folgestunde).
* **Σ Stunden ≡ Tag — per Konstruktion, auch für den Rest:** der Rest des Anlagenzählers je Stunde (für Geräte ohne
  eigenen Zähler) wird auf den Rest des Tages skaliert, `rest_h′ = rest_h × Rest_Tag / Σ_h rest_h` (ohne Lücke und ohne
  Klemmung ist der Faktor 1). So zählt die Lückenmenge eines Zählers nicht doppelt, und jedes Gerät, die PV-Summe,
  Gesamt- und Eigenverbrauch des Tages sind die Summe ihrer Stunden. Wächter `test_kanal_stunden_summe.py` (streng, alle
  Gruppen, beide Abnahme-Matrizen).
* **Stundengepaarte Größen** (Direktverbrauch, Überschuss, Defizit, Gesamtverbrauch je Stunde) über dieselben
  Layer-Formeln (`stundenbilanz.py`, `tagesbilanz.bilanz_aus_stundenrows`), Eingang die Kanal-Stunden; Tageswert = Σ.
  **Spitzen, Vollzyklen und Performance Ratio bleiben Tageszeile** (nicht additiv).
* **Mischzeilen** (`services/energie_profil/kanal_stunden.py`, der eine Tages-Leser der Stunden-Sichten): an einem
  Kanal-Tag kommen die Mengen der Gruppen mit Wahl Kanal (PV, Verbrauch, Einspeisung, Netzbezug, Speicher, Überschuss,
  Defizit; WP-Strom; Wallbox) aus den Kanälen; **Ladestand, Wetter, Preise, Zählwerke und `komponenten`** (der
  Leistungspfad — die Aufteilung je Gerät im Verlauf kommt vom Leistungssensor) aus der Stundenzeile **nach Bahn**
  (S4-R-3b): die backward-Bahnen (`komponenten`, Wetter, Zählwerke, Betriebsart) aus der Bestandszeile `h+1`, Stunde 23 aus
  Slot 0 des Folgetags (`slot_konvention.bestandszeile_fuer_stundenbeginn`, die eine Umrechnung); die forward-Bahnen
  (Ladestand, Preise) zeilengleich. `spannen` je Achse gemischt. Stundengepaarte Größen in `tage-werte` (Grundlast,
  ΔSoC-Wirkungsgrad, Slot-Kosten) nehmen an Kanal-Tagen die Mischzeilen (`strompreis_aggregator.slot_kosten_aus_zeilen`,
  dieselbe Kaskade). Leer bleibt eine Kanal-Stunde ohne Zeile auch in den Geräte-Spalten (`serien.geraete_spalte_kw`, #263,
  fällt nur an Bestandstagen auf den Leistungspfad zurück). Eine Stunde gibt es, wenn sie eine Stundenzeile oder einen Kanal-Wert hat. Die
  Tageswerte und *Energieprofil → Monat* fragen nur Bilanz und WP; `/stunden` alle Gruppen.
* **Wärme je Stunde:** die Wärme-Sichten verteilen weiter den Tageswert (`core/berechnungen/tages_stapel.py`, Σ Stunden =
  Balken); an einem WP-Kanal-Tag kommt nur die **Form** aus den Kanälen (`change` je Zähler, Betriebsart-Stunden aus
  `abgeleitet:inv:<id>:modus_strom_<art>_kwh`; hat dieser Kanal am Tag keine Zeile, je Gerät die Modus-Spur der
  Stundenzeile als backward-Bahn — `kanal_stunden.modus_stunden_mit_rueckfall`). Die Tageswerte von `tag-detail` und der
  Wärme-Sichten (WP-Strom, Wärme/Kälte, Modus-Stapel, E-Mob-Ladung) kommen an einem Kanal-Tag aus dem Kanal-Stundentag bzw.
  seinem Tages-Δ (eine Umschaltstelle `kanal_stunden.tages_eingaenge`). Stunden einer Spanne ohne eigene Zeile sind
  **leer** (S5-R5), nicht 0,0: an einem WP-Kanal-Tag trägt eine Stunde, in der keiner der Zähler einer Linie (Wärme,
  Kälte, Funktions-Strom) eine Zeile hat, `None` (`waerme._verteile_linie`; der Funktions-Stapel ist dort ganz leer); die
  Folgestunde mit der Spanne trägt die Energie, Σ Stunden = Balken. Bestandstage unverändert. Der Betriebsart-Stapel
  verteilt weiter über die Modus-Form (die Modus-Spur der Stundenzeile hat in einer Spannen-Stunde eine Form, H-2a).
  Die Stunden-Route `/waerme-verlauf-stunden` (`api/routes/energie_profil/waerme.py::get_waerme_verlauf_stunden`, Phasen
  RF-58: `_waerme_tag` · `_stunden_verteilung` · `_waerme_linie_d1` · `_funktions_stapel` · `_antwort`) trägt je Slot `h`
  zwei Stapel nebeneinander, nie überlagert:

  ```
  Wärme-Linie(h)      = Σ je Gerät nach D1 (N-391b): Gesamt-Wärmezähler, wo er den Tageswert trug, sonst Heizen + WW
  Wärme-Stapel(h)     = heizen, warmwasser (Summanden-Formen der Achsen-Geräte), übrige = max(0, Linie − heizen − ww)
                        — alle drei auf 3 Stellen; ohne Linien-Wert keine Segmente (P-433-3 S3)
  Funktions-Stapel(h) = heizen = Linie strom_heizen_kwh, warmwasser = Linie strom_warmwasser_kwh,
                        übrige  = round(max(0, Gesamt(h) − heizen − warmwasser), 3),  Gesamt(h) = wp_strom_kwh des Slots
                                  (die Zählerspalte, Σ = Kachel «Strom verbraucht»)
                        Gesamt(h) fehlt ⇒ übrige = None (keine Aussage, nicht 0); Funktions-Stapel nur, wenn ein
                        Funktions-Zähler am TAG einen Wert > 0 trägt; Stunde ohne eigene Zeile an einem WP-Kanal-Tag ⇒
                        heizen/warmwasser None (S5-R5)
  ```
* **Wärme-Verlauf (Tagesreihe, Beiträge, Monatsmengen) an einem WP-Kanal-Tag (W-3, S5a):** Modus-Split und gemessene
  Betriebsart-Zähler kommen wie in *Cockpit → Tag* aus den Kanälen (`kanal_stunden.wp_modus_der_kanal_tage`: Σ der
  abgeleiteten Kanäle «Strom je Betriebsart» im Kalendertag, Abdeckung `modus_abdeckung_h`, Bezug der Kanal-Strom; die
  Betriebsart-Zähler aus den Tages-Δ der WP-Gruppe) — eine Umschaltstelle `waerme_verlauf._modus_eingaenge`; ein Gerät
  ohne Zeile im abgeleiteten Kanal behält den Split der Modus-Spur der Stundenzeilen (H-2a, `splits_mit_kanal`).
  Wärme, Kälte und die Funktions-Achsen liest der Verlauf an einem WP-Kanal-Tag nur aus dem Kanal
  (`wp_werte_der_kanal_tage`, E-S5-4); die Zählerstände (`snapshot/bereichs_leser.lade_tageswerte_je_geraet`) nur für die
  Tage ohne WP-Kanal-Wahl (Lesart 1, je Lauf solcher Tage ein Bereichs-Leser). Ein WP- oder Bilanz-Kanal-Tag
  **ohne Tageszeile** (`aggregate_day` schreibt nicht jeden Tag eine) hat
  seinen Bezug aus dem Kanal wie in *Cockpit → Tag* (Nachmessung E2 A-2).
* **Tage älter als zwei Jahre:** die Stundenzeilen werden nach 730 Tagen gelöscht (`scheduler_jobs.py`); der HA-Spiegel
  reicht so weit zurück wie HAs Langzeitstatistik. Ein solcher Kanal-Tag zeigt seinen Stunden-Verlauf wieder — Mengen aus
  den Kanälen, Ladestand und Wetter leer.
* **Eigene Zählerstände vor dem ersten Kanal-Wert (Nachbau 2, HA-Bauform S4):** `nachfuellen_eigene_summe` füllt **jeden**
  Zähler — auch mit HA-Sensor — aus seinen gespeicherten Stundenständen (`sensor_snapshots`; `live_fallback`/`unknown`
  gezählt, nicht übernommen), aber nur vor `min(erste Kanal-Zeile, gueltig_ab der ersten Quelle)`: keine inneren Lücken,
  eine verworfene Zeit bleibt leer, und ein später auftauchender HA-Spiegel ersetzt diese Zeilen nicht. Stände mit Herkunft
  `ha_statistics` gehen **wörtlich** ein (Mitschrift `sensor_snapshots:<key>`, kein Deckel, keine Reset-Regel), MQTT-Stände
  über die Eigene Summe des Stundenlaufs (90-%-Regel, Deckel als Schreibfilter). **Tagesstand-Reihen** jeder Taktung: ein
  Stand um 00:00 ist die Zeile 23:00 und liegt mit dem Kalendertag auf der Tagesgrenze ⇒ das Tages-Δ ist exakt, die
  Stundenansicht zeigt eine Spanne von 24 Stunden; Paare 23:00/00:00 ergeben Stunde 22 (Tag minus eine Stunde) und Stunde
  23 (die letzte Stunde), je als Spanne sichtbar.
* **Wo der Plausibilitätsdeckel gilt (HA-Bauform S4, R-5):**

  | Weg | Deckel |
  | --- | --- |
  | Kanal-Tag, Kanal-Monat, Kanal-Stunde (HA-Spiegel, Lese-Schicht) | **nein** — HAs Zahl wörtlich (seit S1/S3) |
  | HA-Monatsleser `get_sensor_monatswert` an *Cockpit → Monat* (HA-Weg), „Aus HA laden", alle Monatswerte, Import-Vorschau, Sammelimport, Monatsabschluss-Vorschlag | **nein** (S4, E-S5-4: kein Deckel im Monatsleser, auch kein Parameter dafür) |
  | Kanal-Schreiber, Eigene Summe aus MQTT-Rohständen (Stundenlauf und Nachfüllen) | **ja, als Schreibfilter** (`schreiber._deckel_achse`, Achse PV/Einspeisung, kWp der Anlage) |
  | Bestands-Tagespfad `snapshot/tages_tabelle.py` (Stundenzeilen, Bestandstage, HA wie MQTT) | **ja** (R3, Lesart 1 — an Kanal-Tagen schreibt der Lauf keine Mengen, S5b) |

  Ein Sprung in HAs Statistik steht damit in Tag und Monat wie im HA-Energie-Dashboard; der Daten-Checker
  `ha_zaehlersprung` benennt das Phantom-Muster (Reset und Rückkehr).
* **Stand der HA-Bauform nach S5 (abgeschlossen)** (Konzept §5, Regel → Stand):

  | Regel | Stand |
  | --- | --- |
  | R-3 Kalendertag, Stunde = Beginn | gebaut für die Kanal-Schicht (Kanal-Tage, -Monate, -Stunden); Bestandstage und Lesart-1-Monate bleiben im Bestands-Raster (Lesart 1, S5-E2) |
  | R-5 kein Deckel auf HA-Werten | gebaut im Lesepfad (Kanäle und die fünf HA-Monatsleser-Aufrufer); Bestands-Tagespfad deckelt an Lesart-1-Tagen weiter (R3), MQTT-Schreibfilter bleibt |
  | R-6 HAs Reset-Regel | gebaut am Kanal (Eigene Summe, `core/berechnungen/ha_summe.py`, 90-%-Regel) |
  | R-7 Tagesreset-Zähler | Kanal ja (Tag, Monat, Jahr); Live, Monatsabschluss-Vorschlag und Geräte-Tageswerte vor dem Kanal nein (benannte Grenze, S5-E4: Live ist nicht Teil der Bauform) — der Daten-Checker sagt es |
  | R-8 Komposition als Konfiguration | Weg 2 (W2-R1…R5) für Kanal-Zeiträume plus Checker-Hinweis „PV gesamt neben Balkonkraftwerk" (#428), seit S1/S2 |
  | R-10 Herkunft am Kanal | `kanal_quelle(familie, gueltig_ab, verworfen_ts)` seit S1; `source_provenance` je Zelle bleibt an der Stundenzeile |
  | R-11 jeder Zeitraum gleich billig und gleich vollständig | *Cockpit → Monat*: ein vergangener Monat ohne Abschluss und ohne HA-Antwort nimmt die fünfte Quelle, wenn die Bilanz-Kanäle ihn voll decken (`kanal_monate`, dieselbe Wahl wie die Monats-Fakten; `aktueller_monat._summen_der_tagesebene`) — erledigt mit N-758; ohne volle Deckung bleibt er bis zum Abschluss leer (N-472) |
  | S5a (Teil 1, E-S5-1) eine Mengenquelle je Tag für die Stundenleser | gebaut: jede Kennzahl, die Stundenmengen braucht (Speicher-Potenzial, -Sizing, effektiver Ladepreis, Ladeblöcke, Verbrauchsprognose, Verbrauchs- und Korrekturprofil, Preis-Aggregator, Grundlast, Prognose-IST, Wochenmuster, Tagesvergleich), liest die Stunden über `kanal_stunden.stunden_der_tage` — an einem Kanal-Tag die Mischzeilen wie *Cockpit → Tag*, an einem Bestandstag die Stundenzeile; Tagesmengen der Tageszeile (PV-IST, Komponenten, Regelmarke) an Kanal-Tagen aus `kanal_tage`. Daten-Checker, HA-Export-Steuerung (S5a Teil 2) siehe nächste Zeile, der Schreiber (S5b) die übernächste. Laufzeit (E-S5-1c): abgeschlossene Kanal-Tage (Adapter-Zeilen und Tageswahl der Bilanz; auch die Tageswerte der Geräte-Gruppen Wärmepumpe, E-Mobilität und Sonstiges je Tag und Gruppe, Speicher `GERAETE`, E-S5-4) merkt eedc je Prozess (`services/kanal/merken.py`, invalidiert beim Schreiben der Kanäle und bei jeder Änderung an Anlage, Investition, Kanal oder Quelle) — Sichten über die ganze Historie (Speicher-Sizing, -Potenzial, -Dashboard, aktueller Monat, HA-Export) brauchen ab dem zweiten Aufruf je Prozess wieder etwa so lange wie vor S5a. Benannte Grenze: der **erste** Aufruf je Prozess (nach einem Neustart oder nach einem Schreiben, das die Tage verwirft) rechnet die Kanal-Tage neu; der Speicher hält je Prozess höchstens 3 000 Tage (im Vollzustand ≈ 92 MB); fragt eine Sicht mehr Tage ab, als der Speicher hält, verdrängt sie sich selbst und rechnet jeden Aufruf neu |
  | S5a (Teil 2, E-S5-2) Daten-Checker, HA-Export-Steuerung, Wärme-Sichten, Vormerkungen | gebaut: die Checker-Regeln auf Mengen (PV-Doppelerfassung, Σ PV-Tageswerte des Monats, Drift zu HA, Batterie-Vorzeichen, leere Tage trotz Zähler, E-Mob-Doppelzählung, Einspeisung über Erzeugung, Spitzen) lesen die Lesestelle (`pv_ist_je_tag`, `komponenten_der_tage`, `verworfen_der_tage`, `stunden_der_tage`) — an einem Kanal-Tag ist die eedc-Seite des Vergleichs der Spiegel selbst; «Nachtrag nach eingefrorenem Zähler» nimmt Kanal-Tage aus; neu INFO «n Tage ohne Kanal-Deckung» (Lesart 1 sichtbar, S5-E2 b). HA-Export E1/E2/E5 aus `stunden_der_tage`, Überschuss heute an Kanal-Tagen Σ der Mischzeilen (`tagesbilanz.bilanz_aus_stundenrows`), Zeitangaben am Raster der Zeile. Wärme-Verlauf Modus-Split/Betriebsart aus dem Kanal (W-3), Spannen-Stunden leer statt 0,0 (S5-R5), Wochenmuster ohne gebündelte Zeilen (M-1). Wächter S5-R6 `test_tep_mengen_leser_waechter.py` (Empfänger-Regel). Benannt: die E-Mob-Schlüssel (`wallbox_<id>`/`eauto_<id>`) bleiben an jedem Tag die der Tageszeile (seit E-S5-3 aus dem Kanal) |
  | S5b (Teil 1, E-S5-3) der Schreiber lässt Mengen an Kanal-Tagen weg | gebaut: `aggregate_day` gibt die fertig gebauten Zeilen durch die **Mengen-Weiche** (`services/energie_profil/mengen_weiche.py`, EIN Kanal-Stundentag, Uhr der Lese-Schicht): an einem **Kanal-Tag** (Bilanz-Gruppe mit Wahl `kanal`) bleiben je Gruppe mit Wahl `kanal` die TEP-Mengen (`pv_kw` … `defizit_kw` der Bilanz, `waermepumpe_kw`, `wallbox_kw`), ihre `spannen`-Achsen, TZ `ueberschuss/defizit_kwh`, ihre `komponenten_kwh`-Schlüssel (Bilanz wie `mische_komponenten`, Wärmepumpe/Sonstiges die Ziel-Schlüssel ihrer Zähler, E-Mobilität der ganze Präfix `wallbox_*`/`eauto_*`) und ihre `verworfen`/`nachtrag`-Achsen leer (`None`; die Regelmarke `{}` bleibt). Bahnen und Kennzahlen bleiben; PR, §51-Menge und Heimladungs-Anteil an Kanal-Tagen aus den Kanal-Stunden (`kanal_stunden.performance_ratio_des_kanal_tags`, `einspeisung_neg_preis_der_kanal_stunden`, `ladeanteil_der_kanal_stunden`; der Archiv-Nachzug ruft die PR-Stelle). Herkunft `TZ_QUELLE_KANAL` (`auto:kanal_tag`, Gruppen im Eintrag), `tageszeile_ist_rueckwaerts` ⇒ `False`. Richtung beidseitig (die Wahl zum Schreibzeitpunkt). Lesestelle vervollständigt: `komponenten_der_tage` mischt an Kanal-Tagen alle Gruppen (Tagesliste, `tage-werte`, *Energieprofil → Monat*, Modus-Split-Bezug), `ueberschuss_defizit_der_tage` (Tagesliste, Monats-Rollup, HA-Export). Werkbank-Vorschau und -Rückmeldung nennen die leeren Gruppen. **Lesart-1-Monate mit Kanal-Tagen** (Rand der Kanal-Deckung, laufender Monat mit Wahl `bestand`): `monats_aus_tagen.lade_monats_summen_aus_tagen` faltet die Bestandstage aus den Zeilen und die Kanal-Tage aus der Lesestelle (`KanalTag`: Bilanz, PV/BKW-Schlüssel, Marken; Heimladungs-Anteile aus der Tageszeile) — Monat = Σ Tage wie *Cockpit → Tag* (Entscheid Master H-1 → B). In der einen Mischung `komponenten_der_tage` schlägt die Bilanz-Komposition die Sonstiges-Gruppe für jeden Schlüssel, den sie trägt (Sonstiges-Erzeuger hinter dem Anlagenzähler; Entscheid Gernot 19.10. H-2 → B). Benannt: ein vor 4.1.8 gespeicherter Monatsabschluss (Bestand) kann von Σ der Kanal-Tage abweichen (Naht S4-R-3c-Klasse); die Alt/Neu-Tabelle der Reaggregat-Vorschau nennt seit E-S5-4 an einem Kanal-Tag nur die Achsen der Bestandsgruppen |
  | S5b (Teil 2, E-S5-4) Bestands-Tagespfad nur Lesart 1, Reste | gebaut: **eine PR-Stelle für jeden gespeicherten Tag** (`kanal_stunden.performance_ratio_des_tages`: Kanal-Tag aus den Kanal-Stunden wie `aggregate_day`, Bestandstag aus den Stundenzeilen ohne die Sonstiges-Erzeuger über den Schlüssel der Konstante `SONSTIGES_KOMPONENTEN_PREFIX` — N-759). Wärme-Verlauf: Zählerstände nur für Tage ohne WP-Kanal-Wahl, A-2 (Kanal-Tag ohne Tageszeile). Netzladung der Monats-Fakten: die Wahl zuerst, das Fenster `TAGESFENSTER_JE_TYP` nur für Bestandstage. Merken der Geräte-Tageswerte (`kanal/merken.py`, dritter Speicher `GERAETE`, Schlüssel Anlage/Tag/Gruppe, dieselbe Generation, Invalidierung und Verfall, eigene Obergrenze 9 000 Einträge = 3 000 Tage × drei Gruppen; ≈ 610–630 B je Eintrag, Vollzustand ≈ 5,7 MB). HA-Monatsleser ohne Deckel und ohne `state`-Rückfall. Achse-2-Diagnose nennt die Kanal-Tage. **Benannt, nicht geschnitten:** *Cockpit → Tag* (`tages_eingaenge`) fragt an Kanal-Tagen weiter `get_tagesdetail_kwh`/`get_betriebsart_strom_tageswerte` (Kalendertag) — die Gründe «nicht zugeordnet»/«keine Zählerstände» der Tagesdetail-Zeilen (W-18), die Speicher-Netzladung und Gerätegruppen mit Wahl `bestand` kommen nur von dort; `_fill_gaps_linear` läuft an Kanal-Tagen weiter im Schreiber (Snapshot-Tabelle ohne HA) und für einen WP-Zähler ohne Kanal (`wp_stundenformen`); die Tagestabelle des Schreibers (`lts_tagestabelle`/`snapshot_tagestabelle`) wird an Kanal-Tagen weiter ganz gerechnet — ohne die Teile der Kanal-Gruppen änderte sich die Tageszeile (Leistungspfad-PV-Schlüssel ohne Zähler-Gegenstück, Heimladung bei E-Mob-Wahl `bestand`, Zeilen für Stunden ohne Leistungspunkt) |
  | **S5 abgeschlossen (E-S5-0 … E-S5-5)** | **gilt:** eine Mengenquelle je Tag für alle Leser — jede Sicht, Kennzahl, Prognose-Lernfunktion und Checker-Regel, die Stunden- oder Tagesmengen braucht, liest sie über die Lesestelle (`kanal_stunden.stunden_der_tage`, `komponenten_der_tage`, `pv_ist_je_tag`, `verworfen_der_tage`, `ueberschuss_defizit_der_tage`): an einem Kanal-Tag aus den Kanälen, an einem Bestandstag aus der Stunden- bzw. Tageszeile; außerhalb der erlaubten Liste liest kein Modul TEP/TZ-Mengen (Wächter `test_tep_mengen_leser_waechter.py`, Stand leer). An einem Kanal-Tag schreibt `aggregate_day` keine Mengen der Kanal-Gruppen (Mengen-Weiche); Tage und Monate ohne volle Kanal-Deckung (Lesart 1) lesen wie vor S5, der Daten-Checker zählt sie (INFO). `TagesEnergieProfil` und `TagesZusammenfassung` bleiben als Tabellen für Bahnen, Kennzahlen und Lesart-1-Tage — keine Tabelle, keine Spalte gelöscht, Retention 730 Tage unverändert. **Benannt bleibt:** (a) *Cockpit → Tag* (`tages_eingaenge`) fragt an Kanal-Tagen weiter den Bestands-Tagespfad (`get_tagesdetail_kwh`/`get_betriebsart_strom_tageswerte`, Kalendertag) — nur von dort kommen die Gründe der Tagesdetail-Zeilen (W-18), die Speicher-Netzladung und Gerätegruppen mit Wahl `bestand`; die Snapshot-Kaskade schrumpft darum nicht; (b) die Tagestabelle des Schreibers (`lts_tagestabelle`/`snapshot_tagestabelle`) wird an Kanal-Tagen weiter ganz gerechnet (≈ 90 % der Laufzeit von `aggregate_day`); ohne die Teile der Kanal-Gruppen änderte sich die Tageszeile; (c) `_fill_gaps_linear` läuft an Kanal-Tagen weiter im Schreiber und für einen WP-Zähler ohne Kanal; (d) **W2-R5-Klemme** — Σ Tage ≠ Monat in PV-Summe und Wandlungsverlusten an Tagen, an denen der Rest des Anlagenzählers für ein Gerät ohne Kanal klemmt (Regel W2-5, N-760 widerlegt); (e) die Naht S4-R-3c zwischen Bestandstag und Kanal-Tag und ein vor 4.1.8 gespeicherter Abschluss gegen Σ der Kanal-Tage; (f) Tagesreset-Zähler in Live und im Monatsabschluss-Vorschlag ohne Kanal (S5-E4) |

### Stündliche Berechnung (aggregate_day)

```
PV_kWh            = snap_pv[h] - snap_pv[h-1]                  # für jede gemappte PV-Investition
Einspeisung_kWh   = snap_einspeisung[h] - snap_einspeisung[h-1]
Netzbezug_kWh     = snap_netzbezug[h] - snap_netzbezug[h-1]
Bat_Ladung_kWh    = snap_ladung[h] - snap_ladung[h-1]
Bat_Entladung_kWh = snap_entladung[h] - snap_entladung[h-1]

Verbrauch_kWh     = max(0, PV + Netzbezug + Bat_Entladung - Einspeisung - Bat_Ladung)   # nur bei gleicher Spanne (R6)
Überschuss_kWh    = max(0, PV - Verbrauch_kWh)      # nur, wenn PV und Verbrauch einen Wert haben
Defizit_kWh       = max(0, Verbrauch_kWh - PV)
```

> **An einem Kanal-Tag schreibt `aggregate_day` keine Mengen (HA-Bauform S5b, E-S5-3, S5-R2).** Kommt die
> Bilanz-Gruppe des Tages zum Schreibzeitpunkt aus den Kanälen (HA-Spiegel bzw. eigene Summe; am laufenden Tag die Wahl
> bis zur fälligen Stunde), gibt der Lauf jede fertig gebaute Stundenzeile vor `db.add` und die Tageszeile vor Provenance
> und Restore durch die **Mengen-Weiche** (`services/energie_profil/mengen_weiche.py`): die Mengen der Gruppen mit Wahl
> `kanal` bleiben `NULL` — die Sichten lesen sie aus den Kanälen (Mischzeilen). Gerechnet wird wie bisher (kein Zweig in
> `verrechne_stunde`/`baue_*`); die Weiche gewinnt auch über die Preserve-Logik. Verliert ein Tag die Kanal-Deckung,
> schreibt die nächste Aggregation wieder Mengen (Richtung beidseitig). Die Invarianten (Σ Stunden ↔ Tag, Achse 2)
> bleiben still: beide Seiten sind leer.

**Strikte NULL-Semantik:** Wenn ein Zähler nicht gemappt ist, bleibt das zugehörige Feld `NULL` (statt aus Leistungs-Samples zu schätzen). Im Frontend zeigt eedc ein ⚠-Badge bei Datenlücken — siehe Reparatur-Popover in §4.1c.

**Leistungskurve älterer Tage** (`services/energie_profil/lts_tagesverlauf.py::lade_tagesverlauf_aus_lts`, Vollbackfill und
Reparatur-Werkbank): beschafft für Tage außerhalb der HA-Historie die Stunden-Leistungen aus der Langzeitstatistik (ein
gebündelter Read ab dem Vortag, Serien je Tag über `baue_investitions_serien`, Vorzeichen-Invertierung, Vortagsrand
Stunde 23) und **rechnet nichts** — Mengen, Peaks und Bilanz bildet `aggregate_day`. **Balkonkraftwerk mit Modul-Kindern
(N-777, Werte-Regel N-536 wie der Live-Zwilling `live_tagesverlauf_service._bkw_kuerzung_slot`):** je Stunde trägt das BKW
über `kuerze_bkw_in_werte_map` nur `max(0, BKW − Σ Kinder mit Wert in dieser Stunde)`, Rest 0 ⇒ kein Wert; fehlt den Kindern
die Stunde, bleibt der BKW-Wert (Lücke gedeckt); als Kind zählt nur ein am Tag aktives Modul.
⚠ **Anders als der Peak (N-775, unten)**, der bei voller
Deckung die BKW-Entity gar nicht liest: hier bleibt der Rest beim BKW (die Summe ist der BKW-Wert), und
eine Stunde, in der das BKW 0,0 meldet und kein Kind einen Wert hat, verliert den BKW-Key (Rest 0) — beides wie im Live-Pfad.
Der technische Grund der Asymmetrie: der Tages-Peak summiert je Stunde die **Maxima** der Entities, und die Maxima verschiedener
Entities fallen auf verschiedene Minuten — eine Differenz der Maxima wäre kein Rest; deshalb liest der Peak bei voller Deckung
die BKW-Entity nicht (Entity-Regel), während Live und Kurve Werte derselben Stunde haben und den Rest bilden können (Werte-Regel).
Code: `_bkw_abtretung`, `_bkw_rest_einsetzen`. Auch die Serienwahl
`live_sensor_config.py::baue_investitions_serien` (Live-Kurve und LTS-Kurve) rechnet nicht: sie wählt je Investition
die Serien, behält je Entity eine (#227, Wallbox vor E-Auto) und lässt bei einer am Tag in Betrieb befindlichen Wallbox
die E-Auto-Serie weg (#356, N-555) — Phasen `_serien_je_investition`, `_pool_schutz`, `_emob_quelle` (RF-79).
Die Regel «Wallbox in Betrieb ⇒ Auto-Serie fällt» gilt für HA- und MQTT-Weg: beide rufen `emob_auto_verdraengt`
(der MQTT-Tagesverlauf über `_mqtt_emob_quelle`, N-779); in der
Mischform (Wallbox über HA, Auto über MQTT oder umgekehrt) gilt sie einmal über die Serien beider Wege (`_emob_quelle_ueber_beide_wege`).

#### Zählerlücken wie HA (ab v4.0.51)

Fehlt in Home Assistant eine Stundenzeile eines Zählers, zeigt HA die Energie der Lücke in der
ersten Stunde danach. eedc legt je Stunde genau das ab (G1: Σ Stunden = Tag = HA). SoT der
Slot-Rechnung ist **eine** Tabelle für Stunde und Tag (`services/snapshot/tages_tabelle.py`, gespeist
aus `ha_statistics_service.get_hourly_slots_for_day` bzw. im Standalone aus den Snapshots):

```
Anker(h)      = letzte Zeile mit sum vor Slot h (beliebig weit zurück; R1)
Slot h        = sum(h) − sum(Anker)              n = reale Stunden seit dem Anker (R2)
verworfen     wenn Slot < 0 (Rücksprung, R4)
              oder bei PV/Einspeisung Slot > kWp × 1,5 × Fenster (je Sensor und Achsensumme, R3)
Fenster       = Stunden seit der letzten Zeile desselben Sensors mit Delta ≠ 0 (ab Anker),
                nie unter n, der Anteil aus Nullzeilen höchstens 24 h (spannen.deckel_fenster_stunden)
spannen[achse]= n, nur für n > 1 (TagesEnergieProfil.spannen)
komponenten_kwh = Σ derselben Geräte-Slots (R5)
```

Die Slot-Tabelle selbst (`get_hourly_slots_for_day`, Phasen `_slot_fenster`, `_anker_vor_fenster`, `_slot_werte`):

```
Fenster       = HA-Zeilen mit start_ts in [Vortag 22:00 − 5 min, heute 22:00 + 5 min], Index über lts_boundary_index
                (−1 … 23); sum NULL ist keine Zeile; zwei Zeilen auf einem Index (Herbst-Doppelstunde) ⇒ die spätere
Stand         = sum × Faktor(Einheit des Zählers)      Wh 0,001 · kWh 1 · MWh 1000 · GWh 10⁶; ohne/unbekannt 1
Anker(h)      = höchster belegter Index < h (W1, über den Index, nicht den Zeitstempel);
                sonst Index −1, sonst die letzte Zeile mit sum vor dem Fenster (SQL eine Abfrage,
                WebSocket rückwärts über 1 · 8 · 32 · 128 · 1024 Tage)
Slot h        = round(Stand(h) − Stand(Anker), 3)      n = 1 bei Slot h = 0 (R2), sonst max(1, round(Δstart_ts / 3600))
kein Anker    ⇒ der erste belegte Slot bleibt leer (die Reihe beginnt im Fenster) — benannte Abweichung zu HA,
                das dort 0 als Anker nimmt und die erste Stunde zeigt
```

Die Einheit wird **beim Lesen** umgerechnet (Fenster und Anker), die Differenz entsteht in kWh. Lesefehler (SQL oder
WebSocket) ⇒ Warnung im Log und ein leeres Ergebnis für alle Zähler des Tages.

**Tageswert je Gerät aus der Standreihe** (Bereichs-Leser `services/snapshot/bereichs_leser.py::lade_tageswerte_je_geraet`,
Wärme/Klima-Verlauf je Tag und Speicher-Netzladung im Monats-Rückfall; dieselbe Regel wie `get_tagesdetail_kwh` für einen
Tag, hier über einen Bereich mit **einer** Standreihe je Zähler):

```
Fenster(tag)  = [00:00, 24:00); an den Rückwärts-Tagen des Aufrufers [Vortag 23:00, 23:00) (N-435: die Tageszeile trägt
                ihren WP-Strom aus den HA-LTS-Slots)                                     — Phase _tagesfenster
Ränder        = die Menge aller Fenster-Enden; benachbarte Tage mit gleichem Fenster teilen ihren Rand
Reihe         = EINE Abfrage je Zähler über [erster Rand − 5 min, letzter Rand + 5 min] (Snapshot-Tabelle)
Stand(Rand)   = der Stand der Reihe, der dem Rand am nächsten liegt (±5 min); fehlt er, die Heilungs-Kaskade get_snapshot
                (HA-Langzeitstatistik → MQTT-Backup, schreibt zurück) — nur für die fehlenden Ränder
Anker (R1)    = fehlt Stand(Beginn) und ist Stand(Ende) da: der letzte Stand der Reihe vor dem Beginn, sonst der letzte
                Stand beliebig weit zurück (letzter_stand_vor); die Energie der Lücke gehört zu diesem Tag (wie HA)
Tageswert     = tageswert_aus_reihe(Anker bzw. Stand(Beginn), Stand(Ende), Stände dazwischen) = max(0, Ende − Anfang);
                Rücksprung (Randdifferenz < −Toleranz oder fallende Folge, auch ein Tagesreset) ⇒ kein Tag
                                                                                          — Phase _randstaende
Gerät         = Gerätefeld ODER Σ der Innengerät-Kopien (geraetefeld_oder_innengeraete, nie addiert); laufen mehrere
                (typ, feld) eines Geräts in denselben Ausgabe-Key, addieren sie sich       — Phase _auffalten
übersprungen  = Gerät None · E-Auto mit Parent (die Wallbox misst die Ladung, sonst Doppelzählung) · Feld ohne Zähler
                (feld_hat_zaehler, auch Quelle «keine»)                                   — Phase _geraete_aufloesung
```

Ein Tag ohne Anfangs- oder Endstand und ein Tag mit Rücksprung **fehlen** im Ergebnis `{datum: {ausgabe_key: {inv_id: kWh}}}`
— keine 0 als Platzhalter (ADR-002/P4); der Rücksprung steht als Debug-Zeile im Log. Die Hülle `lade_tageswerte_je_feld`
summiert die Geräte. Proben: `test_waerme_verlauf_bereichs_leser.py`, `test_zaehlerluecken_waerme_leser.py`,
`test_rf56_kanal_leser_phasen.py`.

- **Stundenverbrauch** (R6) nur, wenn PV, Netzbezug und Einspeisung **dieselbe** Spanne tragen; eine fehlende Batterie zählt 0, eine Batterie mit anderer Spanne ⇒ `None`.
- **Tagesverbrauch** (R7) nach der HA-Formel über den Tag; `None` nur im Total-Fall. **Eigenverbrauch** = max(0, ΣPV − ΣEinsp − ΣLadung) + ΣEntladung (N-635, §3.1). Eine fehlende Batterie zählt 0, `verworfen` auf der Batterie sperrt den Eigenverbrauch nicht (wie beim Gesamtverbrauch). Autarkie = (GV − Netzbezug) / GV. Unterdrückt werden EV/EV-Quote bei `verworfen` auf PV oder Einspeisung, die Autarkie bei `verworfen` auf PV, Netzbezug, Einspeisung oder Batterie.
- **Monat** (R8, `monatsbilanz_aus_tagen`): faltet Tagesbilanzen; ein Total-Fall-Tag propagiert nicht; EV mit derselben Formel aus den Summen der Tage (Rest-Abweichung an Tagen mit Netzladung, §3.1).
- **Regelmarke** (R9): `TagesZusammenfassung.verworfen` ist für jeden neu geschriebenen Tag mindestens `{}`; NULL = Altbestand, der bis zur Neuaggregation N-92 rechnet (Daten-Checker §4.6 nennt ihn).
- **Monatswert aus der HA-Statistik** (R10, `get_sensor_monatswert`): Σ der Stundenänderungen ab dem letzten Stand **vor** dem Monat, mit Verwerfung des Rücksprungs; ohne Deckel — der Monat nennt HAs Zahl wie Tag und Kanal-Monat (Tabelle „Wo der Plausibilitätsdeckel gilt" oben). Trägt der Kalendermonat keine `sum`-Zeile, hat er keinen Monatswert (`None`, wie HA; kein Rückfall auf `state`) — der Sensor fehlt dann bei „Aus HA laden", Import und Monatsabschluss-Vorschlag (Anzeige «–»). Damit zählt die erste Stunde des Monats (N-563), und eine Lücke über die Monatsgrenze landet im Folgemonat. `intervalle` nennt die Zahl der Stützstellen-Paare hinter dem Wert; 0 heißt „eine einzige Zeile, nichts gemessen“.
- **Stundenzeilen:** jeder Slot mit Zählerwert bekommt eine Zeile, auch ohne Leistungspunkt (dort keine `komponenten`, keine Spitze).
- **Leser:** Stunde-gegen-Stunde-Auswertungen lassen Zeilen mit `spannen > 1` als Stichprobe aus; Tag-gegen-Tag-Auswertungen (Lernfaktor, Prognose-Genauigkeit, PR-Check) lassen beide Tage um ein Mitternachtsbündel mit Energie aus. Die Energie zählt in jeder Summe. Helfer: `core/berechnungen/spannen.py`.
- **Grundlast des Tages** (Spalte der Tage-Ansicht, `tage_werte.py`; Formel `core/berechnungen/grundlast.py::berechne_grundlast`): Median der Stunden-Verbrauchsleistung `verbrauch_kw` der Stunden 0–4 mit Wert > 0, auf 0,01 kW; eine Zeile, deren Verbrauchs-Achsen mehr als eine reale Stunde tragen, ist keine Stichprobe (`verbrauch_gebuendelt`). An einem Kanal-Tag aus den Mischzeilen `[00:00, 05:00)` des Kalendertags, sonst aus den Slots 0–4. Ohne eine Nachtstunde kein Wert (`None`, Anzeige «—»), eine Teilabdeckung bleibt stehen. Derselbe Filter wie die Monats-Kachel (`aktueller_monat/vergleich.py::_load_grundlast_nacht_kw`).
- **Eingefrorener Stand:** Liefert HA Stunden mit unverändertem `sum` und danach den Nachtrag in einer Zeile, bleiben die Nullzeilen Nullstunden und die Menge steht in der Nachtragsstunde (n = 1, wie HA). Der Deckel rechnet dort mit dem Fenster seit der letzten Änderung — der Nachtrag bleibt Menge. Grenze: nach einer Nacht mit echten Nullen passiert ein Sprung bis Schwelle × (Nullstunden + 1) — am Tag (Bestands-Tagespfad, Lesart 1) ab dem Anker Vortag 22:00 (Winter ≈ 150 kWh bei 10 kWp); der Monatsleser deckelt seit S4 nicht (benannte Asymmetrie zum Bestandstag). Der Spike-Checker (§4.7 im Daten-Checker-Handbuch) liest dieselbe Regel.
- **Daten-Checker:** Tage mit Regelmarke, an denen Σ Einspeisung > Σ PV + Σ Entladung + 0,5 kWh, erscheinen als Hinweis „Einspeisung über Erzeugung" (Entladung ins Netz ist erlaubt).
- **Benannt:** Die Live-Tageskacheln (`live_history_service`) weichen von *Cockpit → Tag* um jedes Mitternachtsbündel ab. Preise einer gebündelten Stunde: s. [KONZEPT-FLEX-TARIFE](KONZEPT-FLEX-TARIFE.md) [A-6].

**Tagesbilanz aus den Stundenzeilen** (`core/berechnungen/tagesbilanz.py::bilanz_aus_stundenrows`, Layer ADR-001; Tag, Monat aus
Stunden, Kanal-Tag, Zeitraum) — Σ über die Zeilen, eine Stunde ohne Wert (`NULL`) zählt **nicht** als 0:

```
Mengen        = Σ pv_kw · Σ verbrauch_kw · Σ einspeisung_kw · Σ netzbezug_kw · Σ waermepumpe_kw (je Achse nur Stunden mit Wert;
                *_erfasst = mindestens eine Stunde, *_stunden = Abdeckung je Achse)       — Phase _stunden_summen
Speicher      = Ladung Σ max(0, −batterie_kw) · Entladung Σ max(0, batterie_kw)              — Phase _stunden_summen
nur Stunden mit PV UND Verbrauch:
Überschuss    = Σ max(0, PV − V)    Defizit = Σ max(0, V − PV)    Direktverbrauch = Σ min(PV, V)  — Phase _stunden_summen
Regelmarke (R9) = verworfen ist nicht None (auch {} — Tag der neuen Regel); sonst N-92 (Altbestand, Monatsfaltung roh)
R7  Gesamtverbrauch = gesamtverbrauch_ha_formel_kwh (PV + Netzbezug + Entladung − Einspeisung − Ladung, einmal ≥ 0)
                      nur ohne Total-Fall (PV, Netzbezug und Einspeisung je ≥ 1 Stunde), sonst None (Anzeige «—»)
    Eigenverbrauch  = _eigenverbrauch_kwh (Direktverbrauch + Entladung, N-635) bei PV und Einspeisung erfasst und
                      ohne verworfen.pv / verworfen.einspeisung                              — Phase _eigenverbrauch_je_regel
    Autarkie        = (GV − Netzbezug) / GV × 100 bei GV > 0 und ohne verworfen auf pv/netzbezug/einspeisung/batterie
N-92 Eigenverbrauch = dieselbe Formel, nur bei PV erfasst und GLEICHER Abdeckung pv_stunden = einspeisung_stunden
                      = Stunden mit beiden (Teilabdeckung PV 24 h / Einspeisung 18 h ⇒ None statt 48 − 18 = 30)
    Autarkie        = (Σ V − Σ Netzbezug) / Σ V × 100 bei Σ V > 0, Netzbezug erfasst und gleicher Abdeckung
                      verbrauch_stunden = netzbezug_stunden = Stunden mit beiden               — Phase _autarkie_je_regel
EV-Quote      = min(100, EV / Σ PV × 100) nur bei PV erfasst, EV nicht None und Σ PV > 0 (sonst None, nicht 0 %)
Speicher-Eff. = Entladung / Ladung × 100 nur bei Ladung > 0,1 kWh (sonst None)              — Phase _bilanz_aus_summen
V2H (#110)    = nur mit Regelmarke über mit_v2h_entladung (Summand in GV und EV, dieselben Sperren)
```

Eine Differenz ohne gemeinsame Grundlage wird unterdrückt, nicht beschriftet (`KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3). Die
Phasen lesen die Zeilen genau einmal (ein Iterator genügt). Proben: `test_tagesbilanz_pv_nicht_erfasst.py`, `test_v2h_tageswert.py`,
`test_n635_eine_eigenverbrauchs_formel.py`, `test_rf73_tagesbilanz_lts_phasen.py`.

**Drift-Prüfung Datenquellen (Daten-Checker)** — die gespeicherten Tageswerte gegen HAs Tageswert aus der
Langzeitstatistik (`snapshot/lts_aggregator.get_komponenten_tageskwh_lts`, je Tag **ein** Lesen für beide Achsen). Nur mit
HA-Statistik; im Standalone keine Zeile.

```
Fenster       = die 90 Tage bis gestern mit Tageszeile; eedc-Seite je Tag über die Lesestelle
                (kanal_stunden.komponenten_der_tage — an einem Kanal-Tag PV/Netz/Speicher aus dem Spiegel)
aktiv(tag)    = Investitionen mit ist_aktiv_an(tag); die HA-Seite liest nur deren Sensoren (N-64)
Achse 1 (PV)  Σ_eedc, Σ_HA = Σ der positiven Werte über die PV-/BKW-Keys, die der LTS-Read für den Tag liefern konnte
              (#311: nicht gelesen ≠ 0); kein lesbarer PV-Key oder Σ_eedc ≤ 0 ∧ Σ_HA ≤ 0 ⇒ kein Vergleich —
              eine Seite 0 gegen die andere > 0 IST ein Vergleich
Achse 2       je übriger Key einzeln (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung, Netzbezug; nie batterie_*),
              nur wenn beide Seiten > 0 (sonst Lücke ⇒ «fehlende Tageswerte», N-201)
Δ             = |Σ_eedc − Σ_HA|
Drift         wenn Δ ≥ 2 kWh ∧ Δ / max(Σ_eedc, Σ_HA) ≥ 5 %          (beide Achsen, beide Schwellen zugleich)
Ausgabe       Achse 1: je Drift-Tag eine Zeile, |Δ| absteigend, höchstens 20; der Rest als «… plus N weitere Tag(e)»
              Achse 2: je Komponente EINE Zeile — Zahl der Drift-Tage, der Tag mit dem größten |Δ| als Beleg und
              Reparatur-Ziel; die Komponente mit dem größten |Δ| zuerst
```

Reihenfolge der Zeilen: die PV-Tage, dann die Komponenten, zuletzt die Rest-Zeile; ohne Drift eine OK-Zeile. Die Meldung
nennt `HA − eedc` mit Vorzeichen und den Anteil an `max(Σ_eedc, Σ_HA)`. Ein Lesefehler an einem Tag nimmt den Tag aus beiden
Achsen. Code: `services/daten_checker/datenquelle/quellen.py::QuellenChecks._check_datenquelle_drift` (Phasen
`_drift_pv_achse`, `_drift_komponenten_achse`, `_drift_tageszeilen`, `_drift_komponentenzeilen`, RF-64). Meldungen und
Behebung: [HANDBUCH_DATEN_CHECKER §4.17](HANDBUCH_DATEN_CHECKER.md#417-datenquellen-drift).

**Peaks aus W-Integration (für Spitzenwerte):**

```
Peak_PV_kW              = max(W-Sample) / 1000   # 10-Min-Auflösung
Peak_Netzbezug_kW       = max(W-Sample) / 1000
Peak_Einspeisung_kW     = max(W-Sample) / 1000
```

Peaks brauchen die Leistungssamples — die kWh-Aggregation läuft separat über die Snapshots.

**Peaks aus der HA-Langzeitstatistik (Vorrang, Etappe 5 v3.31.0):** Liefert HA für die Leistungssensoren je Stunde
`statistics.min`/`statistics.max` (Sensoren mit `has_mean`, in kW umgerechnet von `get_hourly_minmax_sensor_data`), ersetzt
`aggregate_day` jeden der drei Peaks, für den dieser Pfad einen Wert hat; sonst bleibt der Wert aus den W-Samples oben:

```
PV-Sensoren   = leistung_w der pv-module/balkonkraftwerk-Investitionen; ohne einen davon pv_gesamt_w
                außer der Entity eines Balkonkraftwerks, dessen pv-module-Kinder ALLE selbst messen (N-775)
BKW teilgedeckt (ein Teil seiner Kinder misst): je Stunde max_h(BKW) → max(0, max_h(BKW) − Σ max_h(messende Kinder))
Netz-Sensoren = netzbezug_w / einspeisung_w; netz_kombi_w nur, wenn beide fehlen
live_invert   : min' = −max, max' = −min                      (Basis- oder Investitions-Flag)

Peak_PV_kW          = max über h=0…23 von Σ max_h(PV-Sensor)  nur positive max_h; Stunde ohne einen zählt nicht
Peak_Netzbezug_kW   = max über h von max_h(netzbezug_w)       nur > 0
Peak_Einspeisung_kW = max über h von max_h(einspeisung_w)     nur > 0
  Kombi-Sensor:  Peak_Netzbezug_kW = max über h von max_h > 0,  Peak_Einspeisung_kW = max über h von |min_h < 0|
```

Σ max je Stunde ist bei mehreren PV-Sensoren eine **obere Schranke** (die Einzelspitzen können in verschiedene Minuten
der Stunde fallen). **Balkonkraftwerk mit Modul-Kindern (N-775, Regel N-536):** das BKW zählt nie neben seinen Kindern —
messen alle Kinder, wird seine Entity nicht gelesen (`bkw_kinder_decken_vollstaendig`); misst nur ein Teil, trägt es je
Stunde den Rest (`bkw_restwerte`, unverteilt).
Die Elternschaft lädt der Pfad nur, wenn ein BKW und ein Modul beide einen Leistungssensor haben; als Kind zählt
nur ein Modul, das am Tag aktiv war (`aktiv_am_tag` — der Selektor läuft nach dem Zeitfilter). Kein Sensor, Statistik nicht erreichbar, Lesefehler oder leere Antwort ⇒ alle drei `None` und der
W-Sample-Wert bleibt. Code: `services/energie_profil/_helpers.py::_get_tagespeaks_aus_ha_lts` (Phasen
`_lts_sensoren_je_rolle`, `_peak_pv_aus_lts`, `_peak_netz_aus_lts`; Invert-Tausch in `_PeakKontext.slot_for`; Eltern-Regel in
`_pv_elternschaft`, `_bkw_teil_deckung`, `_bkw_rest_der_stunde`), Aufrufer
`aggregator.py` am Ende des Stundenteils; geschrieben als `peak_pv_kw`/`peak_netzbezug_kw`/`peak_einspeisung_kw` der
Tageszusammenfassung (unten).

**Zusätzliche Daten pro Stunde:**

- **Temperatur + Globalstrahlung + GTI:** Open-Meteo Historical API (Archiv) bzw. Forecast API (heute), inkl. `global_tilted_irradiance` mit Modul-Tilt/Azimut
- **Stunden-Aggregation IST von Wetter-Samples:** arithmetisches Mittel der 10-Min-Slots (v3.23.6) — konsistent mit der Mean-Konvention der Open-Meteo-Stundenwerte (ein „last"-Wert läge im Live-Heute-Chart ≈ 25 min versetzt).
- **Batterie-SoC:** HA Sensor History (Stundenmittel) — gefiltert auf `inv.typ == "speicher"`, siehe Vollzyklen-Hinweis unten
- **Strompreis (zwei Felder):** `strompreis_cent` (Endpreis aus HA-Sensor) + `boersenpreis_cent` (EPEX, immer befüllt)

### Tageszusammenfassung (TagesZusammenfassung)

> **Kanal-Tag (S5b, E-S5-3):** `ueberschuss_kwh`/`defizit_kwh` und die `komponenten_kwh`-Schlüssel der Gruppen mit Wahl
> `kanal` bleiben leer (Lesestellen `kanal_stunden.ueberschuss_defizit_der_tage` und `komponenten_der_tage`); Peaks,
> Vollzyklen, Wetter und Börse wie unten. **Performance Ratio, `einspeisung_neg_preis_kwh` und
> `emob_ladung_*_abgeleitet_kwh` bleiben in der Zeile**, an einem Kanal-Tag aus den Kanal-Stunden gerechnet — dieselben
> Formeln (`berechne_performance_ratio`, `stunde_aus_bilanzwerten`/`leite_pv_anteil_ab`); die §51-Menge paart die
> Kanal-Stunde `h` (Beginn-Raster) direkt mit dem Börsenpreis `h`, ohne die Vortag-23-Verschiebung des Backward-Slots; die
> Heimladung nur, wenn auch die E-Mob-Gruppe Wahl `kanal` hat. Die Kennzahl ist ein Stand zum Schreibzeitpunkt (eine
> spätere Korrektur im Spiegel heilt die nächste Neu-Aggregation). Herkunft `TZ_QUELLE_KANAL` (`auto:kanal_tag`).

```
Überschuss_kWh         = Σ(Überschuss_kWh)            alle 24 Stunden
Defizit_kWh            = Σ(Defizit_kWh)
Peak_PV_kW             ┐ Tagesspitzen nach «Peaks» oben: HA-LTS-Stundenmaximum, wo HA es liefert,
Peak_Netzbezug_kW      │ sonst das Maximum aus den Leistungswerten des Tagesverlaufs (W-Samples)
Peak_Einspeisung_kW    ┘ (_get_tagespeaks_aus_ha_lts; nie das Maximum der stündlichen kWh)
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

> **E-Auto-SoC-Trennung (v3.22.0):** Beide Selektions-Pfade (`_get_soc_history`, Bulk-Fetch in `backfill_from_statistics`) lesen den Ladestand nur von Investitionen mit `inv.typ == "speicher"` — der SoC eines E-Autos zählt nie in die `batterie_vollzyklen`.

**Performance Ratio (v3.20.0 auf GTI):**

```
Theoretisch_kWh   = GTI_Wh_m2 × kWp / 1000     # ab v3.20.0
Performance_Ratio = PV_Ertrag_kWh / Theoretisch_kWh
```

Bei Multi-String-Anlagen werden GTI-Werte pro Orientierungsgruppe parallel abgerufen und kWp-gewichtet kombiniert (analog Live-Wetter-Pfad). Ohne gemappte PV-Module bleibt PR bewusst `None` statt einen verzerrten GHI-Wert zu melden.

> ⭐ **Der Nenner steht in der Zeile** (v4.0.39): `TagesZusammenfassung.gti_summe_wh_m2`, und *Cockpit → Tag* nennt ihn beim
> Namen („bei X kWh/m² auf der Modulfläche"). Neben der Formel „Ertrag ÷ (Einstrahlung × kWp)" steht nie die horizontale
> `Strahlung_Summe_Wh_m2` — mit ihr ginge die Rechnung nicht auf.
>
> ⚠ **Rückwärts bleibt sie leer.** Für Tage vor der Spalte steht dort `NULL` — „nicht erhoben",
> nicht 0. Die Anzeige lässt die Bezugsgröße dann weg; die horizontale Summe ersatzweise
> einzusetzen wäre derselbe Fehler mit neuem Etikett. Wer sie für ältere Tage haben will, löst in
> der Reparatur-Werkbank (*Einstellungen → Daten*) „Mehrere Tage neu aggregieren" für den
> Zeitraum aus.

> ⭐ **Der Nenner ist an den jüngsten Tagen vorläufig und wird nachgezogen** (v4.0.39). Die Einstrahlung der letzten fünf
> Tage kommt vom **Forecast**-Endpunkt: das Reanalyse-Archiv (ERA5) hinkt der Echtzeit zwei bis fünf Tage nach. Der
> Forecast-Wert ist im Mittel gut, an **bewölkten** Tagen aber deutlich zu klein — der Nenner wird zu klein, die PR zu groß
> (bis zum Schein einer PV-Doppelerfassung). eedc aggregiert deshalb nachts den einen Tag neu, der die Archiv-Grenze gerade
> passiert hat, und ersetzt den vorläufigen Wert durch den endgültigen. **Für die letzten fünf Tage bleibt er vorläufig.**
>
> **Bestand vor diesem Nachzug:** eedc schreibt für Tage, die ihren vorläufigen Wert dauerhaft trugen, einmalig **nur die
> Wetterzeile** neu (Temperatur, Einstrahlung, Bewölkung, Niederschlag, Wettercode und daraus die Performance Ratio) — je
> Anlage genau einmal, bis zwei Jahre zurück; die gemessene Energie bleibt unangetastet. Denselben Weg nimmt ein Tag, den
> der nächtliche Nachzug wegen geschrumpfter HA-Historie nicht neu bauen kann (die Reparatur-Werkbank baut einen Tag ganz
> aus der HA-Historie und reicht nur so weit zurück wie sie).
>
> **Die Einstrahlung je Tag mit den Dachflächen dieses Tages (N-730).** Auch der Wetter-Nachzug gewichtet die Einstrahlung
> auf die Modulfläche nur mit den Modulen und Balkonkraftwerken, die **an dem Tag** in Betrieb waren — wie die
> Tagesaggregation (`aktiv_am_tag`) und wie der kWp-Nenner. Ein Archiv-Abruf je Modulmenge, nicht je Tag.

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
TagesEnergieProfil.wp_starts_anzahl[h]   = snap_starts[h] - snap_starts[h-1]          (Summe aller WP-Investitionen je Stunde)
TagesEnergieProfil.wp_betriebsstunden[h] = dasselbe für den Betriebsstunden-Zähler (Stunden, ungerundet)
TagesZusammenfassung.komponenten_starts  = {"wp_starts_anzahl":   {"<inv_id>": <int>, ...},
                                            "wp_betriebsstunden": {"<inv_id>": <h>, ...}}
                                            # Tages-Differenz je WP (Boundary-Diff, get_daily_counter_deltas_by_inv);
                                            # die Stunden-Σ wird auf sie skaliert (verteile_counter_auf_stunden)

Kennwert wp_starts (Tag)            = Σ komponenten_starts.wp_starts_anzahl   der am Tag aktiven WPs, nur Werte > 0
Kennwert wp_betriebszeit_min (Tag)  = Σ komponenten_starts.wp_betriebsstunden der am Tag aktiven WPs × 60, ganze Minuten
                                      (tage_werte_zusatz.py::_wp_zaehler; beide None ohne Wert > 0)
Sensor wp_kompressor_starts (je WP) = Σ der Tageswerte > 0 dieser WP über alle Tage in Monaten, in denen sie aktiv ist
Sensor wp_betriebsstunden (je WP)   = dasselbe für die Betriebsstunden; ohne einen Wert kein Sensor (#238,
                                      ha_export/investition_sensoren.py::_wp_zaehler)
```

Architektur trennt Counter-Felder strikt von kWh-Feldern in `KUMULATIVE_COUNTER_FELDER`, damit reine Counter nicht versehentlich in die Energie-Bilanz fließen. Vollbackfill aus HA Long-Term Statistics greift für Tages-Summen (Faktor 1.0 statt 0.001 bei unbekannter Einheit). Stunden-Detail wird ab Live-Erfassung gefüllt.

**Day-Ahead-Stundenprofil-Snapshot (v3.23.4, intern):**

Zwei JSON-Felder in `TagesZusammenfassung` (`pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil`) speichern den ersten OpenMeteo-/Solcast-Forecast des Tages als 24-Werte-Liste in kWh (Backward-Slot). First-write-wins: spätere Aufrufe am selben Tag überschreiben das Profil nicht. Leser: Genauigkeit und Stratifizierung (Tabelle im Lern-SOLL-Abschnitt unten); das Korrekturprofil lernt nicht gegen diesen Schnappschuss, sondern gegen das Lern-SOLL (N-547). Bei gewählter SFML-Quelle kommt `sfml_prognose_stundenprofil` dazu (§4.1b). Speicher ~80 KB/Jahr/Anlage.

**Geschrieben wird der Schnappschuss vom Prefetch-Job** (N-547; alle 45 min, erster Lauf nach Mitternacht; Schreibstelle `api/routes/live_wetter.py`) — unabhängig vom Seitenbesuch. Derselbe Lauf schreibt das Lern-SOLL (unten), aus dem die Stufen 1–3 der Kaskade lernen, und seit N-782 das Solcast-Profil (über das Datum, `SolcastForecast.profil_fuer`, weil der Solcast-Cache über Mitternacht reicht). Das SFML-Profil schreibt nur die Live-Sicht beim ersten Aufruf des Tages, ebenso Solcast vor N-782. Ein Profil aus lauter Nullen wird nicht eingefroren.

#### Das Lern-SOLL des Korrekturprofils (N-547, gebaut 22.09.2026)

⛔ **Wogegen gelernt wird, ist nicht dasselbe wie das, was vorhergesagt wurde.** Das SOLL des Lernens darf nicht die **korrigierte** Kanon-Ausgabe (`pv_prognose_stundenprofil`) sein — das Produkt genau der Faktoren, die gelernt werden: der gepoolte Quotient `Σ IST / Σ SOLL` folgte dann der Abbildung `f ↦ r/f`, deren Fixpunkt **√r, nicht r** ist (bei einem wahren Verhältnis r = 0,85 lernten die Faktoren 0,922 — **+8,5 % an jedem Tag**). Der Aggregator liest deshalb nur das Lern-SOLL (`korrekturprofil_aggregator._lade_tagesprognose`).

Zwei Felderpaare, zwei Fragen:

| Feld | Frage, die es beantwortet | Inhalt |
| --- | --- | --- |
| `pv_prognose_stundenprofil` / `pv_prognose_kwh` | *Was hat eedc vorhergesagt?* (Genauigkeit, Stratifizierung) | korrigiert + gekappt bzw. **roh** für den Tageswert |
| `lern_soll_stundenprofil_kwh` / `lern_soll_kwh` | *Wogegen darf eedc lernen?* | **roh, unkorrigiert, aber gekappt** (`KanonTag.om_stundenprofil_kwh` / `om_kwh`) |

**Warum gekappt.** Die AC-Grenze des Wechselrichters ist keine Prognoseabweichung, sondern eine physikalische Schranke: oberhalb von ihr *kann* die Anlage nicht liefern. Ein ungekapptes SOLL schriebe diesen Deckel als dauerhaften Fehler in die Mittagsfaktoren.

**Warum der Tageswert `pv_prognose_kwh` roh und UNgekappt bleibt.** Sein Leser Tages-SOLL im Energieprofil multipliziert ihn mit dem Legacy-Lernfaktor und erwartet die rohe Lage; das Genauigkeits-Tracking zeigt ihn im Zeitpunkt „Abend" als OpenMeteo-Rohwert (Fallback hinter `pv_prognose_final_kwh`) ohne Faktor. Bis N-782 multiplizierten auch Genauigkeits-Tracking und HA-Abweichungs-Ampel ihn mit dem Faktor. Beide Schreiber (Prefetch und Live) schreiben ihn roh (`KanonTag.roh_kwh` = `om_kwh + abregelung_om_kwh`, N-547).

**Übergang ohne Bruch (kein Backfill).** Die neuen Felder entstehen ab dem Update; Bestandszeilen bleiben NULL. Damit der erste nächtliche Lauf nicht jeden Bin mit einem leeren Pool überschreibt, gilt je Bin: **der neue Wert ersetzt den alten erst, wenn er das Gate seiner Stufe mit NEUEN Datenpunkten erreicht** (Sonnenstand×Wetter 10 h, Sonnenstand 15 h, Stunde Σ 50 h je Monat, Skalar 7 Tage — dieselben Schwellen, die der Lookup anwendet). Beim Skalar gehören `tage_eingegangen` und `faktor_skalar` zum gehaltenen Wert, sonst fiele Stufe 4 aus. Die Marke je Bin steht in `Korrekturprofil.lern_basis_pro_bin` (`"alt"` | `"neu"`), der Beginn in `lern_umstellung_am`; nach **365 Tagen** endet die Regel (sonst bliebe ein saisonal nie wieder belegter Bin für immer auf seinem alten Wert).

### Stunden je Zustand

*Betriebsart-Mitschrift, typoffen — Karte «Betrieb heute» an Wärmepumpe, Wallbox und E-Auto (P-433-2c, P-433-2b K3).*

**Eingang.** Für jeden mitgeschriebenen Zustand schreibt eedc je Gerät und **abgeschlossener** Stunde den **Anteil der
Stunde je Kanon-Wert** (0 … 1) in einen Mittelwert-Kanal — eine Zeile in **jedem** Wert, 0 heißt „gemessen nicht in
diesem Wert", eine Stunde ohne Signal hat in keinem Wert eine Zeile:

| Gerät | Feld | Kanal | Werte mit Stunden (Karte) |
| --- | --- | --- | --- |
| Wärmepumpe | Betriebsmodus | `modus:inv:<id>:<betriebsart>` | Heizen · Warmwasser · Kühlen · Lüften · Entfeuchten |
| Wallbox | Ladezustand | `zustand:inv:<id>:ladezustand:<wert>` | Lädt · Verbunden · Wartet · Fertig |
| E-Auto | Ladezustand (Fahrzeug) | `zustand:inv:<id>:ladezustand_fahrzeug:<wert>` | Lädt · Lädt DC · Verbunden |
| E-Auto | Zu Hause | `zustand:inv:<id>:zu_hause:<wert>` | Zu Hause · Unterwegs |

Welche Felder mitgeschrieben werden, sagt die Registry (`mitschrift: True` an einem Zustandsfeld mit Kanon, abgeleitete
Menge `MITSCHRIFT_LIVE_FELDER`); der Betriebsmodus behält seinen eigenen Pfad unverändert. Kein Betrieb sind `aus`,
`unbestimmt` (Wärmepumpe) und `kein_fahrzeug`, `gesperrt`, `fehler`, `nicht_verbunden` (E-Mobilität).

**Woher die Anteile kommen.** *Home Assistant:* aus der State-History der zugeordneten Entität (Vortag + Tag), je Stunde
die **Verweildauer** je Wert — der letzte Punkt vor der Stunde trägt fort, das letzte Intervall läuft bis zum Stundenende
(`energie_profil/_helpers.py::_get_zustand_history`, eine Schleife `_verweildauer_der_stunde` für alle Felder). Bei evcc
über Home Assistant ohne Ladezustand-Entität (**Option A**) werden die drei Binär-Verläufe „verbunden · lädt · freigegeben"
zu einer Zeitlinie verschränkt (`_verschraenke`: Wechselpunkte vereinigt, Zustand nach jedem Punkt = dieselbe Regel wie
der Live-Chip, `zustands_kanon.ladezustand_aus_werten`); ein gemessener Ladezustand geht immer vor. *MQTT:* das
Haltezeit-Fenster je (Gerät, Feld) im Inbound („ein Zustand gilt bis zur nächsten Meldung"), alle 5 Minuten als Anteil
abgeschlossen; die Stunde ist das **längengewichtete** Mittel ihrer Fenster (`modus_anteile_je_stunde`) — eine Lücke zählt
nicht als gemessene Zeit.

**Formel.** `stunden_je_zustand(anteile_je_stunde, werte_mit_stunden)` in `core/berechnungen/betriebsstunden.py`:

    Stunden(wert) = Σ über die Stunden des Tages  Anteil(stunde, wert)     — nur für werte_mit_stunden, gerundet auf 0,1 h

Eine gemessene 0 bleibt stehen („Heute kein Betrieb"), ohne eine einzige Zeile ist das Ergebnis `None` (keine Karte). Die
Wärmepumpe ruft dieselbe Formel mit ihren Betriebsarten (`stunden_je_betriebsart`, bitgleich). In der Herbst-Doppelstunde
zählen beide realen Stunden (die Zeilen tragen eigene `start_ts`). Der Tag liegt im Raster der Kanal-Gruppe des Geräts
(Kanal-Tag ⇒ `[D 00:00, D+1 00:00)`, Bestandstag ⇒ Backward-Slot).

**Ladevorgänge heute (Wallbox).** Ein zweiter Kanal `wechsel:inv:<id>:ladezustand:laedt` (`sum`, fortlaufender Stand ab 0)
zählt je Stunde die **Übergänge nach „Lädt"** aus einem **anderen, bekannten** Zustand; der Tageswert ist der Zuwachs des
Tages (`kanal_stunden.zustand_wechsel_je_tag`). Der erste Wert ohne Vorgänger (Neustart, erster Tag) zählt nicht.

**Grenzen.** Ab der Zuordnung, nicht rückwirkend (Zustände haben in Home Assistant keine Langzeitstatistik); nur
abgeschlossene Stunden, eine geschriebene Stunde wird nie überschrieben; MQTT-Auflösung 5 Minuten, Broker-Lücke = Stunde
ohne Zeile; der Wechsel-Zähler schreibt nur vorwärts ab seiner letzten Zeile. Ein Wert außerhalb des Kanons (etwa eine
andere HA-Zone als `home`/`not_home`, ein fremder Status) zählt zu keinem Wert; die Summe der Stunden kann deshalb unter der
Tageslänge liegen. Leerlauf der Wärmepumpe zählt als ihre Betriebsart. Stunden je Zustand sind Anzeige, keine Menge: Monats-Fakten, Bilanz, Kosten und CO₂ lesen sie nicht.

**Aufrufer.** Tag-Detail `api/routes/energie_profil/tag.py::_mit_betrieb_stunden` (Wärmepumpe, `wp_geraete[].betrieb_stunden`)
und `::_mit_emob_betrieb` (`emob_betrieb[]` mit `stunden`, `labels`, `wechsel`); Leser
`services/energie_profil/kanal_stunden.py::zustand_anteile_je_stunde` (die WP-Fassung `wp_betriebsart_anteile_je_stunde` ist
seine Hülle); Schreiber `services/kanal/schreiber.py` (Kern `_schreibe_betriebsart_anteile`, Hüllen HA/MQTT).

### PV-Anteil heute

*Kopfzahl der Wallbox-Karte «Heute» (P-433-2b K4) — eine Quote zweier gemessener Mengen, keine Schätzung.*

```
pv_anteil_prozent = round( ladung_pv_kwh ÷ ladung_kwh × 100 )      (core/berechnungen/pv_anteil_ladung.pv_anteil_prozent, stellen=0, nur_gemessen)
```

**Eingänge, beide aus den Tageswerten derselben Wallbox (ein Pfad, Ü5):** `ladung_kwh` = Tageswert `wallbox_<id>` aus
`kanal_stunden.komponenten_der_tage` (die eine Mischung der Tageskomponenten, E-Mob-Gruppe: Kanal schlägt Tageszeile);
`ladung_pv_kwh` = Tagesdetail `werte_je_inv["emob_ladung_pv_kwh"][<id>]` (Boundary-Diff des PV-Ladezählers bzw. Kanal-Δ),
**nur**, wenn `grund_je_feld` für `emob_ladung_pv_kwh` leer ist — ein Wert mit Grund (geschätzt, teilweise) trägt keine
Kopfzahl. Nie der Live-Tageswert (`heute_kwh_pro_komponente`) gegen das Tag-Detail. Kommt der Tageswert aus dem
Leistungspfad (Live-Leistung ohne Zähler), trägt er das Vorzeichen der Senke (negativ); eedc nimmt für „Ladung heute" (Wallbox
und E-Auto) den **Betrag** — dieselbe Regel wie die Tage-Ansicht.

**Kein Wert** („keine Aussage", nie 0 %): ohne eine der beiden Mengen, bei `ladung_kwh ≤ 0`, bei negativem PV-Wert und bei
`ladung_pv_kwh > ladung_kwh` (Zähler-Drift; keine Kopfzahl, kein eigener Checker-Hinweis — der Rücksprung-Checker deckt die
Zähler). Die Herleitung „9,8 kWh PV ÷ 14,7 kWh" steht aus denselben zwei Zahlen darunter.

**Abgrenzung.** `leite_pv_anteil_ab` (§3.4) **schätzt** den PV-Teil einer Ladung aus Netzbezug und Einspeisung je Stunde
(Einspeise-Deckung) und bleibt der Weg für Wallboxen ohne PV-Ladezähler; die Kopfzahl zeigt ihn nicht. Dieselbe Quote
gemessener Mengen steht für den Zeitraum in `monats_fakten/ableitungen.ist_pv_ladeanteil_prozent` (Σ PV ÷ Σ Ladung) und im
Wallbox-Dashboard (`wb_pv_anteil`). Die Gleichheit zur Layer-Funktion ist nur für `ist_pv_ladeanteil_prozent` belegt (Probe
`test_p433_2b_k4_fahrt_pvanteil.py`, gerundet); `wb_pv_anteil` liefert bei einer Ladung von 0 kWh eine 0, die Layer-Funktion
«keine Aussage» — die Zusammenführung beider Stellen in den Layer ist ein eigenes Päckchen.

### Fahrt heute

*«Gefahren heute» und «Fahrverbrauch heute» der E-Auto-Karte «Heute» (P-433-2b K4).*

```
km_heute            = Σ change der Stunden des Tages im Kanal inv:<id>:km_gefahren   (stand, Tachostand)
fahrverbrauch_heute = Σ change der Stunden des Tages im Kanal inv:<id>:verbrauch_kwh (sum)
```

`change` ist der Zuwachs einer Stundenzeile gegen den vorigen Stand (auch über Mitternacht, `lesen.stunden_stapel`); das
Tagesfenster ist das der E-Mob-Gruppe (`_tag_raster`, wie «Stunden je Zustand»). ⛔ **Eine Zeile ohne Vorstand** (die erste
eines Kanals) **zählt 0** — ihr Wert ist ein Tachostand bzw. Zählerstand, keine Tagesmenge. Leser
`services/energie_profil/kanal_stunden.py::fahrt_je_tag`, Tag-Detail `emob_heute[]` (`km`, `fahrverbrauch_kwh`).

**Grenzen.** Nur abgeschlossene Stunden (die laufende fehlt); ab dem ersten Spiegel- bzw. Mitschrift-Lauf nach der
Zuordnung, nicht rückwirkend; ein Zähler, der selten meldet, zeigt die Fahrt mit dem nächsten Stand (in der Stunde des
Sprungs). Meldet der Kilometerzähler tage- oder wochenlang nicht und dann wieder, steht die gesamte Strecke der Lücke am
Tag der Rückkehr in «Gefahren heute» (in der Stunde der nächsten Meldung; wie HAs `change`) — dasselbe gilt für den
Fahrverbrauch. Der Kanal entsteht aus HA (Spiegel der Langzeitstatistik, mit Datenquellen-Wahl HA) oder aus MQTT (Mitschrift des
Stands); eine Zuordnung nur im Sensor-Mapping ohne Datenquellen-Wahl wird nicht gespiegelt (vorbestehend, alle Zähler).
Anzeige, keine Menge der Monats-Fakten: die Monatskilometer kommen weiter aus dem Monatsabschluss.

### Ladung des Tages (Block «E-Mobilität», *Cockpit → Tag*)

*Päckchen BB2 (Fund N-783, 9.11.2026) — die Zahl «Ladung gesamt» und «PV-Anteil (Heim)» des Blocks am Tag.*

```
Zählerpfad  = Σ |wallbox_<id>| der privaten, am Tag aktiven Wallboxen aus komponenten_der_tage
              + Σ |eauto_<id>| der privaten E-Autos, nur ohne deckende Wallbox (N-555)
Leistungspfad (nur, wenn der Zählerpfad keinen Schlüssel trägt)
            = Σ über die Serien wallbox/eauto derselben Geräte | Σ Stunden komponenten[key] |
              (Zeilen wie /stunden; N-555 beim Lesen: steht eine Wallbox-Serie, fällt die E-Auto-Serie)
emob_ladung_kwh        = der gewählte Pfad, nur > 0 (sonst kein Wert — der Tag ohne Ladung zeigt keinen Block)
emob_ladung_quelle     = zaehler | leistung
emob_pv_anteil_prozent = emob_ladung_pv_kwh ÷ emob_ladung_kwh × 100   (pv_anteil_ladung.pv_anteil_prozent, ungerundet)
emob_km                = Σ km_heute der privaten E-Autos (Fahrt heute)
```

**Zählerpfad hat Vorrang, der Leistungspfad ist der Rückfall** — «Zählerlücken wie HA», dieselbe Regel wie Balkonkraftwerk und
Sonstiges am Tag. Bis dahin summierte der Client nur die Stunden-Serien (`TagKomponenten.tsx::baueTagAlsMonat`): an einem Tag mit
Wallbox-Zähler, aber ohne Leistungspfad-Komponente, fehlte der Block (Produktiv-Box 108 von 130 Ladetagen). **Gerätemenge privat**
(`ist_dienstlich` nein) wie *Cockpit → Monat* (Heimladung) und `tage-werte.wallbox_ladung`; die Karten «Heute» (`emob_heute`,
*PV-Anteil heute*, *Fahrt heute*) bleiben **je Gerät** und zeigen auch Dienstgeräte. Phase `tag.py::_emob_ladung_tag`, Zeilen über
`serien.py::zeilen_der_stunden_sicht`; Monat und Jahr tragen `emob_pv_anteil_prozent` als `computed_field` an
`AktuellerMonatResponse`. Proben: `test_bb_speicher_tag_felder.py`, Vitest `bbSpeicherBackendFelder.test.tsx`.

### Monats-Rollup (rollup_month)

Aggregiert alle `TagesZusammenfassung` eines Monats in `Monatsdaten`-Felder:

| Monatsdaten-Feld | Aggregation | Beschreibung |
|------------------|-------------|--------------|
| `ueberschuss_kwh` | Σ(Tages-Überschuss) | Monatlicher PV-Überschuss |
| `defizit_kwh` | Σ(Tages-Defizit) | Monatliches Energie-Defizit |
| `batterie_vollzyklen` | Σ(Tages-Vollzyklen) | Monatliche Batterie-Zyklen |
| `performance_ratio` | Ø(Tages-PR) | Durchschnittliche Performance Ratio |
| `peak_netzbezug_kw` | max(Tages-Peak) | Maximaler Netzbezug im Monat |

**Auslöser:** der Nachlauf des Monatsabschlusses, nach dem Nachrechnen fehlender Tage (`backfill_range`, Kasten unten).

**Überschuss und Defizit an Kanal-Tagen (S5b, E-S5-3):** die Tageszeile trägt sie dort nicht; `rollup_month` liest
sie je Tag über `kanal_stunden.ueberschuss_defizit_der_tage` (Kanal-Tag: Σ der Mischzeilen in der Form der Tageszeile —
zwei Stellen, 0 ⇒ leer; sonst die Tageszeile).

> **Was der Monatsabschluss nachrechnet (HA-Bauform E4f).** Der Nachlauf nach dem Speichern eines Monats
> (`services/monatsabschluss_aggregator.py`) rechnet nur **Tage ohne Tageszeile**, und nur, solange Home Assistant
> sie im Verlauf hat — erkannt an derselben Stelle wie N-596 (die Leistungskurve trägt noch einen Wert;
> `aggregate_day(nur_mit_verlauf=True)`), kein fester Tageswert, denn die Aufbewahrung (`purge_keep_days`, Standard 10
> Tage) ist je Installation anders. **Ein vorhandener Tag wird nie neu gerechnet** — sonst bekämen Tage ohne HA-Verlauf eine leere
> Leistungskurve (#422). Danach `rollup_month()` (oben) und
> das Festschreiben der Aufteilung nach Betriebsart (§3.5). Einen Auto-Vollbackfill gibt es nicht: die Summen der Sichten kommen aus den Kanälen, Lücken der Tageszeilen füllt die
> Reparatur-Werkbank („Lücken aus HA-LTS nachfüllen") auf Knopfdruck. Ohne Home Assistant (MQTT-Zähler) gibt es keinen
> Verlauf, der verfallen könnte: ein fehlender Tag wird aus den Zählerständen angelegt.

---

## 7. Debugging-Leitfaden

### Häufige Fehlerquellen

| Symptom | Mögliche Ursache | Prüfung |
|---------|-----------------|---------|
| Autarkie zu hoch/niedrig | Falsche Einspeisung/Netzbezug-Werte | `Monatsdaten` prüfen - sind die Zählerwerte plausibel? |
| EV-Quote > 100% | Speicher-Entladung > PV-Erzeugung | `InvestitionMonatsdaten` für Speicher prüfen |
| Netto-Ertrag = 0 | Kein Tarif angelegt | `Strompreis`-Tabelle prüfen |
| WP-Ersparnis fehlt oder 0 | Monat mit Strom, aber ohne Wärme (Standby-Zeile 0 €, N-670) · alter Energieträger „keiner" (N-88) · Gaspreis | Wärme- und Stromwerte der WP prüfen; Gaspreis = Monatswert `Monatsdaten.gaspreis_cent_kwh` vor `alter_preis_cent_kwh` der WP vor Vorgabe `GASPREIS_DEFAULT_CENT` (12 ct), §4.4 |
| ROI weicht ab (Cockpit vs. Auswertungen → ROI) | Verschiedene Kennzahlen | Rendite (`/cockpit/uebersicht`, Jahresbericht-PDF) = kumulierte Ersparnis ÷ relevante Kosten; ROI p.a. (Auswertungen → ROI) = Jahres-Einsparung ÷ relevante Kosten (Tabelle §3.6) |
| SOLL überhöht | Teil-Jahr ohne faire Vergleichsbasis | `months_with_data` prüfen (PV-Strings: SOLL nur über Monate mit IST) |
| PV-Erzeugung = 0 | Legacy-Feld statt InvestitionMonatsdaten | Prüfen ob PV-Module als Investitionen angelegt sind |
| Dienstl. Wallbox in E-Mob | `ist_dienstlich` nicht gesetzt | `Investition.parameter["ist_dienstlich"]` prüfen |
| USt wird nicht abgezogen | Steuerliche Behandlung falsch | `Anlage.steuerliche_behandlung` muss `regelbesteuerung` sein |
| Spezialtarif greift nicht | Falsche `verwendung` oder abgelaufen | `Strompreis.verwendung` und `gueltig_ab/bis` prüfen |

### Datenfluss nachverfolgen

**Schritt 1: Eingabedaten prüfen**
```
API: GET /api/monatsdaten/aggregiert/{anlage_id}
→ Monatszeilen aus den Monats-Fakten (Monatsdaten + InvestitionMonatsdaten gefaltet, P10)
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
6. **Cockpit vs ROI-Dashboard:** beide rechnen über den Layer (Cockpit `core/berechnungen/ergebnis.py::berechne_ergebnis`, ROI-Dashboard die Typkette in `api/routes/investitionen/`), messen aber Verschiedenes — kumulierte Rendite (`/cockpit/uebersicht`) gegen ROI p.a. (Tabelle [§3.6](#36-roi--amortisation))

---

*Letzte Aktualisierung: 2026-11-08 (Kap. 1–7 auf Regeln gekürzt, U5)*
