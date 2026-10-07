# eedc Berechnungsreferenz

Dieses Dokument beschreibt alle Berechnungsketten im eedc-System: von den Eingabefeldern
über die Berechnungslogik bis zur Anzeige im Frontend. Es dient als Referenz zur Fehlersuche
und zum Verständnis der Datenflüsse.

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

> **Grundsatz: ein Zeitraum ist die Differenz zweier Stände** (HA-Bauform, erstes Paket S1/S2, ausgeliefert mit E4a–E4f,
> Stand 07.10.2026). Mit Home Assistant spiegelt eedc für jeden zugeordneten Zähler dessen Langzeitstatistik Stunde für
> Stunde (`kanal_statistik`; ohne HA die eigene Summe aus den MQTT-Rohständen nach HAs Reset-Regel). Die Menge eines
> Tages, Monats oder Jahres ist dann **Stand am Ende − Stand am Anfang** — wie im HA-Energie-Dashboard, ohne Deckel und
> ohne Rücksprung-Verwurf; eine fehlende Stunde im Inneren steckt in der Folgestunde, wie in HA.
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
>   Updates (frühere Monate rechnet eedc nicht neu).
> * **Verweise je Größe:** Netz, PV, Balkonkraftwerk, Speicher, Erzeuger hinter dem Zähler — Kasten „PV je Gerät aus
>   Zeitraum-Differenzen — Regel W2" (unten) · Preis und Kosten — §3.1, Kasten „Der gemessene Ø aus Kosten-Kanälen" ·
>   E-Mobilität und Sonstiges — §3.4, Kasten „E-Mobilität und Sonstiges aus Zeitraum-Differenzen" · Wärmepumpe — §3.5,
>   Kasten „Strom je Betriebsart aus Zeitraum-Differenzen" und „Kein Betrieb ist eine Messung" · Zeitfenster-Tarif
>   (HT/NT) — §3.1 (das Gewicht ist der Netzbezug je Wochentag und Uhrstunde aus den Kanälen, eine Abfrage je Seite).
> * **Was (noch) nicht so rechnet:** Stundenprofile, Kurven, Energieprofil-Stunden, die stundengepaarten Spalten
>   (Direktverbrauch, Überschuss, Defizit), die Tagesebene der E-Mob-Aufteilung, Reparatur-Werkbank und Prognose-Leser
>   bleiben auf den Stunden- und Tageszeilen (nächste Stufe S3). Der Monatsabschluss-Nachlauf rechnet seit E4f nur
>   noch Tage, die fehlen und die HA noch im Verlauf hat (§6b).

**Legacy-Felder (NICHT neu befüllen):**
- `Monatsdaten.batterie_*` - Nutze `InvestitionMonatsdaten` (Speicher)
- `Monatsdaten.pv_erzeugung_kwh` - **kein Schreibziel** für neuen Code (Pro-Modul-Werte gehören in `InvestitionMonatsdaten`) und seit 2026-07-29 auch **keine allgemeine Lesequelle** mehr: das Feld trägt den manuell erfassten oder importierten **PV-Gesamtwert** eines Monats und ist **ausschließlich Eingang** des Read-time-SoT `core/berechnungen/pv_verteilung.py` (`resolve_pv_je_modul`). Der füllt damit die Lücken der Module ohne eigenen Wert und kennzeichnet sie als gerechnet. Der Gesamtwert steht für **alle** PV-Quellen der Anlage: bevor er die Lücken füllt, geht der eigene Monatswert jedes Balkonkraftwerks ab, das in diesem Monat selbst trägt (nicht an Modul-Kinder abgetreten) — das BKW kommt in `pv_erzeugung_kwh = pv_module_kwh + bkw_kwh` als eigener Summand dazu und stünde sonst zweimal darin. Ein BKW **ohne** eigenen Wert, das im Monat selbst trägt, ist seit 04.10.2026 (N-621) eine Lücke wie ein Modul ohne Wert: es bekommt seinen kWp-Anteil am Rest (Gewicht `get_erzeuger_kwp`, auch `leistung_wp × anzahl`), geführt als `erzeugung.bkw_aus_anlagenwert_kwh` und additiv in `pv_kwh` — nicht in `bkw_kwh`, nicht in `pv_je_modul`, nicht in `BkwFakten` (die tragen die eigenen Werte). Ein BKW mit Anteil trägt im Monat keinen Ersatz-Eigenverbrauch (P9) und keinen Tageswert. Nur wo der Gesamtwert **gespeichert** ist — von Hand, mit „Aus HA laden" (N-622), seit HA-Bauform E4b auch über den HA-Statistik-Import (bis dahin verteilte der Import den Zähler selbst nur auf Module, und ein BKW ohne Wert bekam 0). Wer nur einen Gesamt-Sensor hat, pflegt weiterhin ausschließlich hier. Jede einzelne Berechnung liest die Pro-Modul-Schicht bzw. deren Summe — nie das Feld selbst. Ladepfad: `services/pv_monatswerte.py`.

> **PV je Gerät aus Zeitraum-Differenzen — Regel W2 (HA-Bauform E4a-2, Stand 06.10.2026, Entscheid Gernot).** Wo die
> Kanäle der Bilanz-Gruppe (Netz, PV/Balkonkraftwerk samt Anlagenzähler, Speicher, Erzeuger hinter dem Zähler) einen
> Zeitraum **voll decken** — mit Home Assistant der Spiegel seiner Langzeitstatistik —, rechnet eedc Tag, Monat und Jahr
> aus den Differenzen der Zählerstände über den Zeitraum, und zwar mit **einer** Regel für jeden Zeitraum
> (`core/berechnungen/bilanz_zeitraum.py::komponiere_bilanz_zeitraum`, PV-Teil `pv_verteilung.py::loese_pv_zeitraum_auf`):
>
> 1. **Quelle je Gerät:** ein Gerät, dessen Kanal den Zeitraum voll deckt, trägt sein Δ — auch wenn im Inneren Stunden
>    fehlen (ihre Menge steht wie in HA in der Folgestunde). Gemessene Werte werden nie skaliert.
> 2. **Rest des Anlagenzählers:** `max(0, Δ Anlagenzähler − Σ Δ gemessene Geräte)` geht einmal je Zeitraum nach kWp
>    auf die Geräte ohne deckenden Kanal (Marke „geschätzt (kWp-Anteil)"). Die Modul-Kinder eines Balkonkraftwerks sind
>    dessen Lücke — am Tag wie im Monat.
> 3. **PV-Summe:** Σ der Geräte-Werte nach 1 und 2. Der Anlagenzähler ist nur Füller, nie Ersatz der Geräte-Summe.
>    Liegt Σ Geräte über ihm, wird die Differenz als Wandlungsverluste geführt (`wandlungsverluste_kwh`), nicht
>    bewertet (N-588, offen bis nach dem Umbau). Beispiel Volleinspeiser mit DC-String-Zählern: am Schattentag melden
>    die Strings 12,6 kWh, der AC-Zähler 12,096 — die PV-Summe ist 12,6, der Eigenverbrauch 0,504.
>
>    **Wandlungsverluste als geführte Größe (HA-Bauform E4b, Stand 06.10.2026).** `wandlungsverluste_kwh = max(0, Σ
>    Geräte − Δ Anlagenzähler)` je Zeitraum, mit dem Bezug Σ Geräte (= Σ der String-Zähler vor dem Wechselrichter);
>    Prozent = Verluste ÷ Σ Geräte × 100 (`pv_verteilung.wandlungsverluste_prozent`, Layer). Weg: Kanal-Leser
>    (`services/kanal/bilanz_leser.als_monatssumme`) → Monats-Fakten `ErzeugungFakten.wandlungsverluste_kwh` /
>    `_bezug_kwh` — **auch für abgeschlossene Monate**, deren Mengen aus der Zählerzeile kommen (die Fakten lesen den
>    Kanal-Monat zusätzlich, wenn die Anlage einen Kanal `basis:pv_gesamt` hat) → *Cockpit → Monat*, *Cockpit → Jahr*
>    (Σ der Monate mit Wert, Prozent über die Monate, die Verluste UND Bezug tragen — `quote_paarweise`), Übersicht
>    (Gesamtzeitraum) und die Monatsreihe `/monatsdaten/aggregiert`. `None` ohne Anlagenzähler und ohne Kanal-Deckung
>    — der Bestandspfad liefert keinen Wert. **Nicht bewertet:** PV-Summe, Eigenverbrauch, Autarkie, Ersparnis, CO₂
>    und Ergebnis-Leiter rechnen weiter mit Σ Geräte (Entscheid B2; N-588 bleibt offen). Beispiel: Strings 360 + 180 +
>    Balkonkraftwerk 90 = 630 kWh, Anlagenzähler 594 ⇒ Wandlungsverluste 36,0 kWh (5,7 %); Eigenverbrauch und Ersparnis
>    bleiben auf 630.
> 4. **Entweder-oder:** je Zeitraum der erste Kanal einer Ersatzgruppe mit voller Deckung.
> 5. **Untergrenze 0 einmal je Zeitraum** — Σ Tage ≠ Monat nur in der Aufteilung je Gerät an Tagen, an denen der
>    Rest klemmt.
>
> **Kein Deckel, kein Rücksprung-Verwurf:** eedc nimmt je Sensor seine Messung wie das HA-Energie-Dashboard. Ein
> Zählersprung aus HA steht deshalb in Tag und Monat; der Daten-Checker benennt ihn (Kategorie „Zählerstände – Sprung
> in Home Assistant", Muster Reset und Rückkehr auf den alten Stand). **Lückentag wie HA:** fehlen einem Zähler mehr
> als 24 Stunden, trägt der erste beendete Tag danach die ganze Lückenmenge; ein Tag ganz in der Lücke trägt 0 (er kommt trotzdem
> aus den Kanälen, nicht aus dem Bestand).
> **Quellenwahl:** je Tag und je Monat EINE Wahl für alle Eingänge der Gruppe — die Kanäle nur, wenn jeder benötigte
> Kanal den Zeitraum voll deckt; sonst rechnet der bisherige Leser den ganzen Zeitraum aus Tages- und Stundenzeilen
> mit den unten beschriebenen Regeln (**Bestandspfad**, Übergang bis S5). Nicht umgestellt sind die E-Mobilitäts-
> Aufteilung derselben Monatszeile und die stundengepaarten Spalten (Direktverbrauch, Überschuss, Defizit) — sie
> bleiben aus den Stundenzeilen. Der Kalendermonat je Sensor („Aus HA laden", Import, Monatsabschluss-Vorschlag,
> HA-Weg von *Cockpit → Monat*) nimmt das Kanal-Δ, wenn die Spiegel aller Bilanz-Sensoren den Kalendermonat decken.

> **Die PV-Achse über Tag, laufenden und abgeschlossenen Monat** (Stand 04.10.2026, Bau der sieben Regelfehler; Richter ist die Abnahme-Matrix `backend/tests/test_pv_achse_matrix.py`):
>
> - **Tag, Anlagenzähler trägt ihn** (nicht jeder Erzeuger misst den ganzen Tag): ein Erzeuger mit eigenem Zähler behält seinen **Tageswert** (Σ seiner brauchbaren Stunden-Slots; ein Balkonkraftwerk mit Modul-Kindern den Rest nach ihnen, E4). Gemessen ist er, wenn kein Slot verworfen wurde, kein Tagesreset vorliegt und die Anlagen-Energie seiner Stunden ohne eigenen Slot plus seine Bündel-Energie höchstens **1 %** des Tages ist (`DAEMMERUNGSREST_ANTEIL`, eine Setzung). Die übrigen Träger teilen den Rest nach kWp (Marke `kwp_anteil`); übersteigen die Messungen den Anlagenzähler — oder misst jeder, aber mit anderer Summe —, werden sie gemeinsam auf ihn skaliert. Σ Tages-Keys = Σ Stunden. Layer: `core/berechnungen/pv_tages_praezedenz.py` (`gemessene_tageswerte`, `loese_aggregat_tag_auf`). Bis dahin bekam im Aggregat-Fall jeder Erzeuger nur den kWp-Anteil (seit v4.0.51; gespeicherte Tage heilen durch „Tag neu aggregieren" bzw. die Reparatur-Werkbank).
> - **Tag ohne HA-Stundenwerte:** liefert die Zählertabelle die PV-Achse, stehen in `komponenten_kwh` nur ihre PV-Keys — eine Leistungs-Summe der Kurve (`pv_gesamt`, `pv_<bkw>` neben `bkw_<bkw>`) fällt heraus (seit v3.26.8 stand sie daneben und zählte doppelt).
> - **Laufender Monat (Cockpit → Monat):** die Quellen-Präzedenz steht in `core/berechnungen/datenquellen.py::gewinner_je_feld`; Merge und Teilzeitraum-Marke entstehen beide daraus. Ein Anlagenzähler aus der HA-Monatsstatistik oder MQTT ab Monatsbeginn misst den Monat bis jetzt und geht durch die P7-Auflösung (Quellen mit eigenem Wert gewinnen, er füllt den Rest). Ersetzbar bleiben Tagesebene, MQTT-Rückfall, Connector ohne Abdeckung und im laufenden Monat auch der gespeicherte Zwischenstand und der Connector mit Abdeckung. Die eigene BKW-Zeile aus der Tagesebene nennt nur gemessene Tageswerte (`energie.bkw_gemessen_kwh_je_investition`).
> - **Gemessene 0 (Cockpit → Monat, laufend und ohne Abschluss, seit 04.10.2026):** hat eine Quelle im Monat **gemessen**, gilt ihr Wert auch, wenn er 0 ist — für Einspeisung, Netzbezug und den Anlagen-PV-Zähler sowie die Gerätefelder von Speicher, Balkonkraftwerk, Wallbox und E-Auto. Gemessen heißt bei der HA-Statistik mindestens **ein Intervall** (`SensorMonatswert.intervalle ≥ 1`: Anker + eine Zeile oder zwei Zeilen — eine einzelne Zeile misst nichts), bei der Tagesebene mindestens eine Stunde mit Wert (`TagesMonatsSumme.einspeisung_erfasst`/`netzbezug_erfasst`, nur diese zwei Felder). Ein nicht zugeordneter Zähler und einer ohne Zeilen im Monat bleiben `None` mit Grund. Auch im abgeschlossenen Monat mit Abschluss wirkt sie, wenn die gespeicherte Zeile für das Feld 0 trägt (Balkonkraftwerk, Speicher, Anlagen-PV-Zähler): das Feld zeigt dann 0,0 mit Herkunft Home Assistant statt „kein Wert“; eine gespeicherte Zahl über 0 wird nie verdrängt. Beispiel: Netzbezug-Zähler flach, drei Juli-Tage ⇒ Netzbezug 0,0 · Gesamtverbrauch 42,0 · Autarkie 100 % · Stromrechnung 0,00 € · Ergebnis 16,20 € (vorher alles „—“ und der Rat „Zähler zuordnen“). ⛔ **Nicht** für Wärmepumpe und einzelne Strings: eine WP-0 bräuchte eine Darstellungsregel für „kein Betrieb“, eine String-0 neben dem Anlagenzähler nähme dem String seinen Rest — beide bleiben bei „über 0“. Benannt: ein eingefrorener Sensor mit weiterlaufenden Zeilen ist 0 (wie HA ihn zeigt); im laufenden Monat schlägt eine HA-0 den gespeicherten Zwischenstand wie jeder HA-Wert. Proben: `test_n585_gemessene_null.py`.
> - **Balkonkraftwerk mit Modul-Kindern:** der Monat tritt ab, in jeder Form — laufend, ohne Abschluss, abgeschlossen und im Tageswert-Rückfall der Monats-Fakten (`pv_verteilung.bkw_kinder_luecken_kwh`, Stufe 2 von P7). Der Tag bleibt bei E4.
> - **Modul ohne Wert, kein Gesamtwert:** die **Anzeige-Summe** nimmt die vorhandenen Werte (`pv_monatswerte.pv_teilsumme_je_monat`, `pv_vollstaendig=False`, Hinweis „Teilsumme"; der Daten-Checker nennt den Monat). Die **Prüf-Summe** `pv_summe_je_monat` bleibt `None` — Daten-Checker-PV-Map, Import-Vorschau und `gesamt_pv_kwh` prüfen nur vollständige Monate (Gernot 04.10.2026; N42 gilt nur noch für die Prüf-Leser).

> **Seit 2026-07-31 ist die Lesequelle nicht mehr `lade_pv_je_monat`, sondern eine Schicht darüber:** `services/monats_fakten/::lade_monats_fakten` (ADR-002/**P10**, [Konzept](KONZEPT-MONATS-FAKTEN.md)). Sie liefert die **ganze** Monatszeile kanonisch aufgelöst — die PV ist darin ein Feld (`erzeugung.pv_module_kwh` bzw. `erzeugung.pv_kwh`), daneben stehen Zähler, Speicher, E-Mobilität, Wärmepumpe, Sonstiges, Tarif, §51 und die Verbrauchs-Kennzahlen. Sie **ruft** `lade_pv_je_monat` (die P7-Regel bleibt unverändert), wendet aber zusätzlich **einmal** alle Zeitfilter (`aktiv` · Anschaffung · Stilllegung) und den Dienstwagen-Filter an. Wer eine abgeleitete Monatsgröße auswertet, nimmt sie von dort; `lade_pv_je_monat` direkt zu rufen bleibt richtig, wo **nur** die Pro-Modul-PV gebraucht wird (String-Vergleich, PV-Diagnose). Ausgenommen sind Schreib-, Import- und Checker-Pfade — die Schicht ist reines Lesen.
>
> Die Migration läuft sichtweise (`KONZEPT-MONATS-FAKTEN.md` §10): umgehängt sind **Aussichten**, **Jahresbericht-PDF** und der **Investitions-ROI** (S2). Der baumweite Wächter wird mit S5 scharf gestellt.

> **Achtung, ein Name für zwei Größen:** `pv_erzeugung_kwh` bezeichnet **drei verschiedene Dinge**, je nachdem, wo es steht — die **DB-Spalte** `Monatsdaten.pv_erzeugung_kwh` (manuelles Gesamt-Aggregat, s. o.), den **Schlüssel in `InvestitionMonatsdaten.verbrauch_daten`** (Erzeugung *dieses einen* Moduls) und das **Response-Feld** von `/monatsdaten/aggregiert` (PV-Module **+** Balkonkraftwerk). Der Identifier bleibt bewusst unverändert — er ist zugleich MQTT-Topic-Segment, CSV-Spaltenname und Backup-Feld. Siehe [Glossar](GLOSSAR.md#energie--bilanzen).
>
> ⛔ **Und eine vierte Stelle, die es NICHT gibt: der Wechselrichter.** Er ist kein PV-Erzeuger — `PV_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")`, baumweit. Bis 2026-08-24 bot die Eingabe-Registry trotzdem ein `wechselrichter/pv_erzeugung_kwh` an; **gelesen wurde es von niemandem** (gemessen: 900 kWh dort ⇒ 0,0 kWh Anlagen-PV), und weil es der Alternativ-Gruppe `pv_energie` angehörte, setzte ein dort zugeordneter Zähler den Anlagen-Zähler **und** das Modul-Feld auf „bereits an anderer Stelle zugeordnet". Ergebnis: drei PV-Quellen inaktiv, keine wirksam, und die Live-Kachel fiel auf die Hochrechnung aus der Leistung zurück (#388, rund 31 % zu hoch). Das Feld trägt seither `nur_bestand` — es erscheint nur noch, solange eine alte Zuordnung daran hängt, und der Daten-Checker sagt, wohin sie gehört. **Wer die Gruppe erweitern will, liest zuerst den Wächter** `test_wechselrichter_kein_pv_erzeuger.py::test_es_gibt_genau_drei_pv_energie_quellen`: er hält Eingabe-Registry und Rechen-Kern gegeneinander und meldet rot, sobald sie auseinanderlaufen.

### Schicht 2: Berechnungslogik

| Datei | Funktionen | Beschreibung |
|-------|-----------|-------------|
| `services/monats_fakten/` | `lade_monats_fakten()`, `finanz_zeile_eingabe()`, `kennzahlen_aus_fakten()` | **Eingabe-Aufbereitung, keine Formel** (ADR-002/P10): löst die Monatszeile einmal auf und ruft die SoT-Helfer. Vorschaltet jeder aggregierenden Lese-Sicht |
| `core/calculations.py` | `berechne_monatskennzahlen()`, `berechne_speicher_einsparung()`, `berechne_eauto_einsparung()`, `berechne_waermepumpe_einsparung()`, `berechne_roi()`, `berechne_ust_eigenverbrauch()` | Reine Berechnungsfunktionen ohne DB-Zugriff |
| `api/routes/cockpit.py` | 6 Endpoints | Aggregation aller Daten für Dashboard |
| `api/routes/aussichten/` | 5 Endpunkte (Paket seit 18.09.2026) | Prognosen (`prognose.py`, `trend.py`, `wetter.py`) und Finanz-Prognose (`finanzen.py` als Orchestrator; seine Phasen seit 18.09.2026 in `finanz_eingaenge.py` · `finanz_rueckblick.py` · `finanz_prognose.py` · `finanz_zerlegung.py`) |
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
| [Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) | `GET /api/aussichten/kurzfristig/{id}` | 7-Tage PV-Prognose (**ohne** SFML — `aussichten.py` kennt die Quellenwahl nicht) |
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

Definiert in `core/berechnungen/heizgradtage.py`:

| Konstante | Wert | Einheit | Verwendung |
|-----------|------|---------|-----------|
| `HEIZGRENZE_C` | 15.0 | °C | Heizgradtage — Temperaturkorrektur der Verbrauchsprognose **und** wetternormierter Vergleich (§3.5f). Gradtag-Konvention, **keine** Innenraum-Temperatur. **Eine** Definitionsstelle, gewächtert von `test_berechnungs_layer_konformitaet.py::test_heizgrenze_nur_im_layer` |

Definiert in `api/routes/aussichten/basis.py` (bis 18.09.2026 `aussichten.py`):

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
| `einspeiseverguetung_cent` | Tarif, ggf. Monatswert | `Strompreis.einspeiseverguetung_cent_kwh`; bei variabler Vergütung schlägt `Monatsdaten.einspeise_durchschnittspreis_cent` (#392, `resolve_einspeise_preis_cent`) |
| `netzbezug_preis_cent` | Tarif | `Strompreis.netzbezug_arbeitspreis_cent_kwh` |
| `grundpreis_euro_monat` | Tarif | `Strompreis.grundpreis_euro_monat` |
| `netzbezug_durchschnittspreis_cent` | HA-Sensor oder Monatsdaten | Dynamischer Ø-Preis |
| `leistung_kwp` | Anlage | Summe aller `Investition.leistung_kwp` (pv-module) |

#### Formeln

```
Erzeugung_gesamt    = PV_Erzeugung + BKW + sonstige_Erzeuger   (hinter dem Zähler)
Direktverbrauch     = max(0, Erzeugung_gesamt - Einspeisung - Batterie_Ladung)
Eigenverbrauch      = Direktverbrauch + Batterie_Entladung + V2H_Entladung − Abgabe_an_Dritte   (§9.2, seit 05.09.2026)
Gesamtverbrauch     = Eigenverbrauch + Netzbezug
Restverbrauch       = Gesamtverbrauch − Wärmepumpe − Wallbox/E-Auto − sonstige erfasste Verbraucher   (nur Stunde/Live, s. u.)
EV-Quote (%)        = Eigenverbrauch / Erzeugung_gesamt * 100   (wenn Erzeugung > 0)
Autarkie (%)        = Eigenverbrauch / Gesamtverbrauch * 100    (wenn GV > 0)
Spez. Ertrag        = PV_Erzeugung / Leistung_kWp              (kWh/kWp, NUR PV; zwei Varianten, s. u.)

Einspeise-Erlös (EUR)    = (Einspeisung - Einspeisung_neg_Preis) * Einspeisevergütung / 100
Netzbezug-Kosten (EUR)   = Netzbezug * Netzbezug_Preis / 100 + Grundpreis
Arbeitspreis-Kosten (EUR)= Netzbezug * Netzbezug_Preis / 100            (ohne Grundpreis, reiner Ausweis)
EV-Ersparnis (EUR)       = PV_Eigenverbrauch * EV_Preis / 100          (s. Hinweis; EV_Preis = EV-gewichteter Ø der Stundenpreise, sonst Netzbezug_Preis)
Netto-Ertrag (EUR)       = Einspeise-Erlös + EV-Ersparnis + BKW-Rest-Ersparnis + Erlös_eigener_Satz
                           + Sonstige_Netto − Dienstliche_Ladekosten − USt-Anteil_Eigenverbrauch
                                                                          (Stufe 1 der Ergebnis-Leiter, §3.2)
CO2-Einsparung (kg)      = PV_Erzeugung * 0.38               (VERALTET — s. Kasten)
```

> **Eine Eigenverbrauchs-Formel auf jeder Zeitebene (N-635, 05.10.2026).** Die Formel oben gilt für Monat, Jahr, Live
> **und den Tag**: Cockpit → Tag (Kachel, Bilanz-Zeile, Tageswerte-Tabelle), die Tagessumme im Verlauf von Cockpit → Monat,
> der Monat aus Tageswerten (ohne Abschluss) und die Tagesprognose rechnen sie über dieselbe Layer-Funktion
> `berechne_verbrauchs_kennzahlen` (Tag: `core/berechnungen/tagesbilanz.py`). Das ist auch die Formel des
> HA-Energie-Dashboards (`used_solar` + `used_battery`). Bis 05.10.2026 rechnete der Tag `PV − Einspeisung` und hieß
> deshalb „PV-Eigenverbrauch · inkl. Speicherladung" (F3, 29.07.): mit Speicher zählte er die **Ladung** statt der
> **Entladung**, lag an Ladetagen über dem Gesamtverbrauch und summierte sich nicht zum Monat (Beispiel: PV 18,
> Einspeisung 6, Ladung 3, Entladung 2 ⇒ 12 statt 11 kWh bei 11 kWh Gesamtverbrauch; drei solche Tage 36 statt 33).
> Ohne Speicher sind beide Formeln gleich. Mit dem Tages-Eigenverbrauch rechnen EV-Quote, CO₂ (PV) und
> Eigenverbrauchs-Ersparnis des Tages (die Tagesfinanz bekommt Ladung und Entladung mit); der Tag kennt kein V2H und zieht
> die Abgabe an Dritte als gemessene Tagesmenge ab. Der Verlauf in Cockpit → Monat stapelt die Erzeugung deshalb als
> **Direktverbrauch + Speicherladung + Einspeisung** (wie die Verwendung im PV-Hub), nicht mehr als Eigenverbrauch +
> Einspeisung.
>
> **Benannte Rest-Abweichung — Σ Tage ≠ Monat an Tagen mit Netzladung.** Lädt der Speicher an einem Tag mehr, als PV nach
> der Einspeisung übrig ist (Netzladung), klemmt der Tag den Direktverbrauch bei 0; der Monat rechnet aus den Summen und
> verrechnet die Netzladung mit dem PV-Überschuss anderer Tage. Zwei Tage: Tag 1 PV 1, Netzbezug 10, Ladung 5 ⇒ EV 0;
> Tag 2 PV 10, Einspeisung 2, Netzbezug 1, Ladung 1, Entladung 5 ⇒ EV 12. Σ Tage 12, Monat (11 − 2 − 6) + 5 = 8.
> Dieselbe Netzladung steht im Verlauf als Speicherladung — an solchen Tagen liegt der Stapel um sie über der PV.
> Ein Tag aus dem Altbestand (ohne Regelmarke) mit mehr Einspeisung als PV nennt seit N-635 den Eigenverbrauch 0 statt
> einer negativen Zahl — dieselbe Klemme wie Tag und Monat nach R7 (Vorlage §10).

> **Gesamtverbrauch und Restverbrauch — zwei Wörter, zwei Zahlen (N-603, 03.10.2026).** Der **Gesamtverbrauch** ist
> alles, was das Haus verbraucht hat (Eigenverbrauch + Netzbezug) — Live-Kachel, Tag/Monat/Jahr-Bilanz. Der
> **Restverbrauch** ist der Teil davon, den kein einzeln erfasstes Gerät erklärt. Er entsteht **je Stunde** im Client
> (`components/tag/TagWerteTabelle.tsx::berechneHausverbrauch`, dieselbe Differenz im Stundenverlauf) und **live** als
> Residual der Leistungen (`services/live_komponenten_builder.py`, Tagesverlauf `services/live_tagesverlauf_service.py`).
> **Je Monat oder Jahr gibt es ihn nicht als eigene Kennzahl** (nur als Kategorie „Restverbrauch" in der
> Monatsauswertung „Verbrauch nach Kategorie"). Bis 03.10.2026 hießen beide stellenweise „Hausverbrauch" bzw.
> „Haushalt" — die Live-Kachel meinte den Gesamt-, die Tagessicht den Restverbrauch. Das Wort „Hausverbrauch" steht
> seither nur noch als Herstellerbegriff in Anführungszeichen (s. u.); Wächter `npm run check:begriffe` und
> `backend/tests/test_begriffe_anwendertexte.py`.

> **Hinweis „EV_Preis" (SOLL Flex-Tarife A-2, Tag seit v4.0.46, Monat/Jahr seit 18.09.2026).** Die Ersparnis
> bewertet **vermiedenen** Bezug, und der fällt zu anderen Zeiten an als der tatsächliche: Eigenverbrauch
> mittags (PV), Netzbezug abends. Bei einem dynamischen Tarif wird die vermiedene Menge deshalb mit dem
> Ø der Stundenpreise **in den Stunden des vermiedenen Bezugs** bewertet (Gewicht je Stunde:
> max(0, PV − Einspeisung)), nicht mit dem bezugsgewichteten Ø — der läge systematisch zu hoch.
> Auf der Tagesebene liefert ihn `SlotKosten.ev_mittel_cent`, auf Monatsebene `MonatsPreis.ev_cent`
> aus derselben Messung (`strompreis_aggregator`), und `baue_finanz_zeile` reicht ihn an alle Sichten
> durch. **P-1:** Ein gepflegter (abgerechneter) Bezugs-Ø stellt den Bezugspreis, für die Ersparnis ist
> er nur der Rückfall — unterhalb der Abrechnung gilt die Messung. Ohne Stundenpreise (Festpreis)
> bleibt es beim Netzbezug_Preis; dort bewegt sich keine Zahl.
> ⚠ **Cockpit → Monat folgt der Regel erst seit 03.10.2026** (samt Vorjahresmonat und der Balkonkraftwerk-Zeile des
> T-Kontos): bis dahin nahm diese Route den bezugsgewichteten Ø — im Probemonat 160,00 € statt 40,00 €, während
> Übersicht und Monatsreihe schon 40,00 € nannten. Die Antwort trägt den Preis jetzt als `ev_preis_cent` mit Herkunft
> (`ev_preis_herkunft`: „ev_gemessen" oder die Herkunft des Bezugspreises); die Stromrechnung bleibt beim Bezugspreis.
> Der **Vorjahresmonat** löst seinen Bezugspreis seit 03.10.2026 über dieselbe Kaskade (`aufgeloester_monatspreis`) — bis
> dahin fehlte ihm die Stufe „gemessen" (Probe: 70,00 € als Vorjahr gegen 90,00 € direkt).
>
> **Cockpit → Monat rechnet die Bilanz über den Layer (03.10.2026).** Eigenverbrauch, Direktverbrauch, Gesamtverbrauch,
> Autarkie und EV-Quote des Monats kommen aus `berechne_verbrauchs_kennzahlen` — dieselbe Funktion wie Monats-Fakten,
> Übersicht, Monatsreihe, PDF und HA-Export. Bis dahin stand in `aktueller_monat/aggregation.py` eine eigene Formel ohne
> die **V2H-Entladung**: was ein E-Auto ins Haus zurückspeist, fehlte im Eigenverbrauch von Cockpit → Monat und → Jahr
> (Demo-Anlage 2025: 6 996,5 statt 7 331,4 kWh, Δ = 335 kWh V2H). Die V2H-Menge kommt aus den gespeicherten Gerätewerten
> des Monats; im laufenden Monat ohne gespeicherten Wert zählt sie 0. **Der Vorjahresvergleich ist seither derselbe
> Monat:** der Vorjahres-Block wird aus der Monatsantwort des Vorjahresmonats gelesen, nicht mehr eigens gerechnet
> (Mengen mit zwei statt einer Nachkommastelle). Damit läuft der Vorjahresmonat auch durch die Quellen-Kaskade des
> Monats (gespeicherte Werte, Connector, Home-Assistant-Statistik): mit angebundenem Home Assistant fragt ein Aufruf von
> Cockpit → Monat die Statistik jetzt für zwei Monate ab statt für einen. Schlägt die Berechnung des Vorjahresmonats
> fehl, antwortet der Monat ohne Vorjahresvergleich und nennt das in seinen Hinweisen.
>
> **Hinweis „Eigenverbrauch".** Der Eigenverbrauch, der zu **Geld** wird, ist derselbe wie der in
> der Mengen-Bilanz: die Erzeugung **hinter dem Zähler** — PV-Module, Balkonkraftwerk **und** ein
> Erzeuger unter *Sonstiges* (BHKW, Windrad, Wasserkraft). Der Zähler am einen Netzanschluss misst
> die Summe aller Erzeuger dahinter; was davon nicht eingespeist wurde, hat Netzbezug ersetzt.
> Menge und Betrag meinen deshalb dieselbe Kilowattstunde.
>
> ⚑ **Nicht bewertet wird das GERÄT, nicht sein Strom.** Ein sonstiger Erzeuger bekommt keine eigene
> Ertrags-Zeile und keine Wirtschaftlichkeit — sein Ertrag wird am Gerät als
> `Investition.einsparung_prognose_jahr` („Ertrag/Jahr") gepflegt, weil eedc seinen Brennstoff nicht
> kennt. **Geändert am 2026-09-03** (Maintainer-Entscheid, löst v3.45.4 ab); bis dahin nahm die
> Finanz-Zeile die PV-Achse, und Menge und Betrag zählten verschiedene Erzeuger.
> („Ertrag/Jahr"). Beide Größen liegen in **derselben** Summe (`jahres_netto_ertrag` in `aussichten/finanz_prognose.py::jahres_alternativkosten`)
> — würde die Menge zusätzlich monetarisiert, stünde derselbe Nutzen zweimal darin.
>
> ⭐ **Ausnahme seit 2026-09-06 — die Kategorie *Abgabe an Dritte* (§9.2 Geldseite).** Dort ist der
> Ertrag **gemessen**, nicht geschätzt: Das Gerät führt je Monat ein Feld „Erlös (€)". Der
> Jahres-Ertrag der ROI-Zeile ist deshalb `Σ Monatserlöse ÷ Monate mit Wert × 12` — hochgerechnet
> **mit der eigenen Monatszahl** (F-20), nicht durch zwölf geteilt. **Vorrang: gemessen vor
> geschätzt** — liegt auch nur ein Monatswert vor, schweigt „Ertrag/Jahr" und wird *nicht* addiert
> (Bauform wie ADR-002/P7). Eine gepflegte **0** ist dabei eine Aussage („unentgeltlich abgegeben")
> und macht die Zeile bewertet; ohne beides bleibt sie „nicht bewertet" — nie 0 € (N-87/N-258).
> **Die eine Quelle ist `core/berechnungen/investitions_jahresertrag.py`**, gelesen von
> ROI-Dashboard, Aussichten-Prognose und HA-Export.
>
> ⛔ **Die drei lesen sie mit VERSCHIEDENEN Laufzeit-Filtern, und das ist Absicht:** Das
> ROI-Dashboard ohne Jahresfilter behält stillgelegte Geräte (#123 — „spätere Stilllegung darf
> Vergangenheit nicht löschen"), Aussichten und HA-Export filtern auf *heute aktiv*, weil sie
> Prognosen sind. Zwei Fragen, zwei Umfänge; Wächter ist
> `test_abgabe_geldseite_drei_sichten.py::test_die_zwei_umfaenge_bleiben_verschieden`.
>
> ⚠ **Und eine Asymmetrie zwischen den beiden Prognosen, gemessen am 06.09.2026:** Im **HA-Export**
> steckt der gemessene Erlös bereits in der Anlagenbilanz (`netto_ertrag_euro`); dort zählt nur der
> *geschätzte* Posten zusätzlich, sonst stünde er doppelt — beim ersten Lauf meldete der Sensor
> `jahres_ersparnis_euro` **960 € statt 480 €**. In den **Aussichten** ist er in keiner anderen
> Prognose-Größe enthalten und wird deshalb voll addiert.

> ⚠ **Folge für die Anzeige:** Bei einer Anlage mit sonstigem Erzeuger geht
> `Eigenverbrauch × Preis = EV-Ersparnis` **nicht** auf. Das T-Konto beschriftet die Zeile dann als
> *PV-Eigenverbrauch-Ersparnis* und zeigt die Multiplikation nicht an, statt eine Herleitung zu
> behaupten, die sich nicht nachrechnen lässt (N-131).

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
> **Welcher Preis gilt:** der **abgerechnete** Monatsdurchschnitt
> (`Monatsdaten.netzbezug_durchschnittspreis_cent`), sonst der aus den
> Stundenpreisen **gemessene** verbrauchsgewichtete Ø, sonst der
> Tarif-Arbeitspreis (die Kaskade weiter unten in diesem Dokument). Das gilt für Netzbezug-Kosten, EV-Ersparnis und — ohne eigenen
> WP-Tarif — auch für die WP-Ersparnis. Bis v4.0.6 nahm der **laufende** Monat hier
> den Tarifpreis, während Vorjahres-Vergleich und die per-Investition-Details schon den
> Durchschnitt nahmen; derselbe Monat trug damit je nach Sicht zwei Beträge.
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
> sonst rechnet er wie bisher aus den Stundenzeilen. Gleiche Zahlen, nur schneller: Monat für Monat zwei Stände
> statt aller Stunden (12 Jahre, Kanäle über die ganze Zeit: 386 → 23 ms, gemessen an der Prüfkopie). Der Kanal beginnt mit dem Monat des
> Updates; frühere Monate rechnet die Stundentabelle. Tag (Slot-Kosten) und §51 bleiben bei den Stundenzeilen.
>
> **Zeitfenster-Tarif (HT/NT, Stufe 3 der Kaskade, seit E4f).** Das Gewicht ist der gemessene Netzbezug je Stunde. Aus
> den Kanälen kommt er je **(Wochentag, Uhrstunde)** zusammengefasst — Σ der auf 0 geklemmten Stunden-Zuwächse — und
> der Preis je Zelle aus dem Fenster (`zeittarif.gewichteter_arbeitspreis_aus_zellen`; ein Fenster hängt nur an
> Wochentag und Uhrzeit, deshalb ist Σ Preis × kWh über die Zellen dieselbe Zahl wie über die Stunden). Alle Monate
> einer Seite, in denen ein Zeitfenster-Tarif gilt, kommen in EINER Abfrage (vorher je Monat und Tarif eine, an der
> Prüfkopie 104 je Übersicht). Deckt ein Netzbezugs-Zähler den Monat nicht, gewichten die Stundenzeilen wie bisher.

**§51 EEG im Einspeise-Erlös:** `Einspeisung_neg_Preis` sind die kWh, die in Stunden
mit negativem Börsenpreis eingespeist wurden — für betroffene Anlagen entfällt dafür
die Vergütung (Herleitung des Volumens: Abschnitt „§51 EEG (Negativpreis-Analyse)"). Ist
die Anlage nicht §51-pflichtig oder liegt keine Strompreis-Mitschrift vor, ist der
Wert `null` und es wird nichts abgezogen. Der Abzug gilt **überall** gleich, und es
gibt dafür **eine** Implementierung: `core/berechnungen/einspeise_erloes.py`. Bis
2026-08-04 stand daneben ein Frontend-Spiegel (`lib/calculations.ts::calcEinspeiseErloes`)
für *Auswertungen → Finanzen + Tabelle*; er ist mit Fund **N-22** entfallen, weil die
Monats-Finanzzeile jetzt fertig aus `/monatsdaten/aggregiert` kommt.

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
> **Ein Balkonkraftwerk ohne zugeordnete Module rechnet unverändert wie bisher.**
> SoT: `core/berechnungen/erzeuger_traeger.py`. Melder: Discussion #366, Forum T89667 #172.
>
> #### Dieselbe Abtretung gilt für die Wirtschaftlichkeit (ab v4.0.19, F-33/#381)
>
> Die ROI-Sicht fasst einen **Wechselrichter mit seinen Modulen und seinem DC-Speicher** seit jeher
> zu **einer** Systemzeile zusammen: die drei Positionen teilen sich eine Energiemenge, und ihre
> Ersparnisse sind deshalb **nicht addierbar**. Für ein Balkonkraftwerk als Träger galt das nicht —
> dort bekam jede Ebene ihre eigene Zeile, und die Gesamtzeile addierte sie. An einer gemeldeten
> Anlage (BKW + Modul-Kind + Speicher-Kind) standen so **1.079 €/Jahr** statt der gemessenen
> **606 €**, und die Gesamt-Amortisation bei **1,9 statt 3,3 Jahren**. Das Modul-Kind trug zusätzlich
> die Aufforderung „(ohne WR) — bitte zuordnen", obwohl es zugeordnet **war**.
>
> Seither ist **Trägergerät** die Rolle, nicht der Typ: ein Balkonkraftwerk mit Kindern ist
> Systemkopf wie ein Wechselrichter. Es tritt seine Ersparnis genauso an die Module ab, wie es
> oben seine Erzeugung abtritt — hat es **keine** Modul-Kinder (nur einen Speicher), trägt es sie
> weiterhin selbst und steuert sie der Systemzeile bei. Die Zeile trägt Name und Typ ihres Kopfes,
> damit ein Balkonkraftwerk nicht als „PV-System" mit fremdem Namen erscheint.
>
> ⚠ **Die pauschale BKW-Schätzung ist davon unberührt und bleibt eine Schätzung** (0,9 kWh/Wp,
> 80 % Eigenverbrauch). Sie greift nur noch für ein Balkonkraftwerk ohne Modul-Kinder — dort, wo
> keine gemessenen Modulwerte existieren. Melder: Issue #381 (azywietz-web).

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

Welche Monate der annualisierte Wert zählt, entscheidet für Cockpit-Kachel und HA-Sensor **eine** Funktion
(`services/monats_fakten/ableitungen.py::pv_erzeugungs_monate`, seit 04.10.2026): ein Monat mit Modul-Eintrag,
mit eigenem Balkonkraftwerk-Wert > 0 oder mit dem Anteil eines Balkonkraftwerks am gespeicherten Anlagenwert.
Bis dahin ließ der HA-Sensor Monate aus, in denen nur ein Balkonkraftwerk erzeugt hat — reine
Balkonkraftwerk-Anlage: 143,75 statt 586,73 kWh/kWp.

**Achsen-Trennung (bewusst):** PV-**eigene** Kennzahlen (spez. Ertrag, Performance-
Ratio, SOLL/IST, kWp) nutzen **nur** `PV_Erzeugung`, nicht `Erzeugung_gesamt` — ein
sonstiger Erzeuger ist energetisch Erzeuger, aber kein PV-Modul. Ebenso bleibt
**CO₂ und Geräte-Wirtschaftlichkeit quellenspezifisch**: Ein Erzeuger unter *Sonstiges*
bekommt **keine** PV-artige CO₂-Gutschrift und keine eigene Wirtschaftlichkeit. Der Grund
gilt für die ganze Kategorie, nicht nur fürs BHKW: **eedc kennt den Vergleichswert nicht.**
Ein verbrennender Erzeuger emittiert, statt einzusparen; bei einem Windrad oder einer
Wasserkraftanlage fehlt umgekehrt jede belastbare Grundlage für Anschaffung, Wartung und
Lebensdauer. Beides steht als „nicht bewertet" da, und der Ertrag wird am Gerät gepflegt.
⚑ **Sein Strom ist davon unberührt** — er zählt in Menge *und* Geldwert der Anlage voll mit
(seit 2026-09-03, s. §3.2). **Insel-Anlagen** (kein Netzanschluss, kein Bezug/keine Einspeisung)
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

#### Die Ergebnis-Leiter — Monat, Jahr und Gesamt aus einer Rechnung (seit 03.10.2026)

**SoT:** `core/berechnungen/ergebnis.py` (`berechne_ergebnis`, `soll_erfuellung`, `falte_zeitraum`), der USt-Satz aus
`services/ust_satz.py`. Bis dahin entstanden Netto-Ertrag, Monats-/Jahresergebnis und SOLL-Erfüllung an zwölf
Stellen mit verschiedener Zusammensetzung — Cockpit → Monat nannte bei Regelbesteuerung für denselben Monat 212,00 €,
die Übersicht 206,30 €.

```
Stufe 1  Netto-Ertrag (PV)           = Einspeise-Erlös + EV-Ersparnis + BKW-Rest-Ersparnis + Erlös eigener Satz
                                       + Sonstige Positionen (netto) − Dienstliche Ladekosten
                                       − USt-Anteil auf den Eigenverbrauch
Stufe 2  (Zwischenstand)             = Netto-Ertrag + WP-Ersparnis + E-Mob-Ersparnis − Stromrechnung (inkl. Grundgebühr)
Stufe 3  Monats-/Jahresergebnis      = Stufe 2 − Betriebskosten (anteilig, nur im Monat aktive Komponenten)
```

* **Ein Name je Stufe.** Stufe 1 ist der „Netto-Ertrag" überall — Cockpit → Monat/Jahr, Komponenten → PV-Anlage,
  PDF-Jahresbericht, HA-Sensor `netto_ertrag_euro`. Stufe 2 hat im UI keinen eigenen Namen; sie steht nur als
  Zwischenstand in der Herleitung (Antwortfeld `ergebnis_vor_betriebskosten_euro`). Stufe 3 ist das
  **Monatsergebnis** bzw. **Jahresergebnis** (Feld `ergebnis_euro`).
* **Herleitung aus derselben Rechnung (A6).** Die Antwort trägt je Stufe Formel und eingesetzte Werte
  (`ergebnis_herleitung`); der Tooltip nennt jeden Summanden einzeln — WP-, E-Mob-, BKW-, Erzeuger-, Sonstige-,
  Dienstwagen- und USt-Posten nur, wenn sie etwas beitragen.
* **Dienstliche Ladekosten sind ein eigener Posten (N-633, 05.10.2026).** Die Monats-Fakten bilden ihn
  (`EmobFakten.dienstliche_ladekosten_euro`, Formel §3.10); Cockpit → Monat und → Jahr, Auswertungen → Tabelle und
  → Finanzen, Monats- und Jahresbericht führen ihn als Zeile bzw. Summanden „Dienstliche Ladekosten" (T-Konto SOLL,
  Komponenten-Finanztabelle als Aufwand, nur wenn ≠ 0). Bis dahin zogen nur Übersicht, HA-Sensor und Aussichten ihn ab —
  dieselbe Anlage hatte dort 104,40 €, in Cockpit → Monat/Jahr, Tabelle und PDF 122,40 € (Beispiel: 60 kWh × 30 ct).
  Übersicht, HA-Sensor und Aussichten lesen seither denselben Wert aus den Monats-Fakten, falten ihn aber wie zuvor in
  ihre Sonstigen Positionen (der Netto-Ertrag ist in beiden Formen derselbe). Er steht **nicht** in den Sonstigen
  Ausgaben des Monats — die sind Eingang des Kapitaleinsatzes (F-19), der Posten ist laufender Aufwand.
* **Fehlende Eingänge — eine Regel für Monat, Vorjahr und Jahr.** Eine Stufe gibt es nicht (`—`), wenn einer ihrer
  Pflichtposten fehlt: Stufe 1 braucht Einspeise-Erlös und EV-Ersparnis, Stufe 2 zusätzlich die Stromrechnung.
  Optionale Posten gehen als 0 ein und werden in `fehlende_posten` genannt, wenn die Komponente existiert, aber keinen
  Wert hat. Der **Vorjahresmonat** folgt derselben Regel; ein Vorjahresmonat mit 0 kWh Netzbezug trägt dabei die
  Grundgebühr als Stromrechnung, wie der laufende Monat auch (bis 03.10.2026 zählte die Stromrechnung dort als 0).
* **Betriebskosten des Monats** zählen nur Komponenten, die im Monat aktiv waren (Anschaffungs- und
  Stilllegungsdatum) — dieselbe Filtermenge wie die T-Konto-Zeilen.
* **USt-Anteil eines Monats** = Eigenverbrauch des Monats × USt je kWh **des Jahres** (§3.7). Σ der Monatsanteile
  eines Jahres = der Jahreswert der Übersicht. Im laufenden Jahr wandert der Satz mit jedem Abschluss um Cent-Beträge
  (eine Jahressteuer); die Herleitung nennt Satz und Grundlage. Hat das Jahr noch keinen Abschluss, gilt der Satz des
  Vorjahres; gibt es auch den nicht, wird kein USt-Anteil gerechnet, und die Herleitung sagt es.
* **SOLL-Erfüllung** (`soll_erfuellung_prozent`, `soll_erfuellung_monat_prozent`, `soll_fenster_text`) kommt ebenfalls
  fertig aus der Antwort — Cockpit und PDF-Monatsbericht rechnen sie nicht mehr selbst.
* **Der Layer rundet nicht**; gerundet wird am Antwortrand (Cockpit → Monat je Posten auf Cent).

**Das Jahr (Cockpit → Jahr, Auswertungen → Finanzen im Jahr-Modus)** rechnet seit 03.10.2026 das Backend:
`GET /api/cockpit/jahr/{anlage_id}?jahr=` lädt die Monatsantworten des Jahres (dieselbe Monatsmenge wie bisher: jeder
Monat zwischen Inbetriebnahme und heute, der gemessene Mengen trägt — auch ohne Monatsabschluss) und faltet sie
(`falte_zeitraum`):

* **Summen** (kWh, €) über alle Monate; **Quoten paarweise** — Autarkie, EV-Quote, Speicher-Auslastung und der
  Netzlade-Ø-Preis entstehen aus Summen über genau die Monate, die **beide** Größen tragen. Ein Monat mit
  Eigenverbrauch, aber ohne Gesamtverbrauch, fällt aus Zähler und Nenner (vorher: 198 % Autarkie, #421). Zähler,
  Nenner und Fenster („aus 8 von 9 Monaten") stehen in der Antwort und im Tooltip.
* **Ergebnisgrößen über die Leiter** auf den Jahressummen ihrer Posten, mit derselben None-Regel: fehlt einem Monat die
  Stromrechnung, gibt es kein Jahresergebnis (`fehlende_posten` nennt den Monat). Der Netto-Ertrag hängt nicht an der
  Stromrechnung.
* **Vorjahr / Ø-Jahr** aus der Monatsreihe, beschnitten auf die gemeinsamen Monate (N-37); die Ø-Autarkie ist die Quote
  der gemittelten Mengen, nicht das Mittel der Prozente.
* Kopfzahl = das Jahr bis heute (inkl. laufendem Monat); Vergleich, Vorjahr, Ø-Jahr nur über abgeschlossene Monate.


**Endpoint:** `GET /api/cockpit/uebersicht/{anlage_id}` in `cockpit.py`

Die Cockpit-Übersicht aggregiert alle Monatsdaten für ein Jahr (oder alle Jahre) und berechnet:

#### Finanzielle Kennzahlen

```
Einspeise-Erlös     = Σ(Einspeisung) * Einspeisevergütung / 100
EV-Ersparnis        = Σ(PV_Eigenverbrauch * EV_Preis) / 100         (s. Hinweis; je Monat der EV-gewichtete Ø, sonst Netzbezug_Preis)
Netto-Ertrag        = Einspeise-Erlös + EV-Ersparnis + Erlös_eigener_Satz
                      [- USt_Eigenverbrauch]
BKW-Ersparnis       = Σ(BKW_Eigenverbrauch) * Netzbezug_Preis / 100
Sonstige-Netto      = Σ(sonstige_ertraege) - Σ(sonstige_ausgaben)

Betriebskosten_Zeitraum = Σ(Betriebskosten_Jahr) * Anzahl_Monate / 12

Kumulative Ersparnis = Netto-Ertrag + WP-Ersparnis + E-Mob-Ersparnis
                       + BKW-Ersparnis + Sonstige-Netto
                       - Betriebskosten_Zeitraum

Jahres-Rendite (%)  = Kumulative_Ersparnis / Investition_gesamt * 100
```

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
> **Variable Einspeisevergütung (#392, seit 2026-08-22):** Trägt der Tarif das Häkchen
> „Einspeisevergütung wechselt monatlich“ (`Strompreis.einspeisung_variabel`, z. B.
> OeMAG-Marktpreis in Österreich), bietet der Monatsabschluss das Feld
> `Monatsdaten.einspeise_durchschnittspreis_cent` an. Der gepflegte **Monatssatz schlägt den
> Stammwert** — aufgelöst ausschließlich über `resolve_einspeise_preis_cent`
> (`api/routes/strompreise.py`), mit `is not None`: **0 ct ist ein Wert**. Monate ohne
> Eintrag rechnen mit dem Stammwert. Die Hochrechnung nach vorn (Aussichten-Prognose) und
> die ROI-Rechnung über die Lebensdauer nehmen bewusst weiter den heutigen Stammwert —
> künftige Monate haben keinen Monatswert (dieselbe Begründung wie beim Netzbezug, N-113).
> eedc holt den Satz **nicht** automatisch ab (keine länderspezifische Quelle); er wird
> eingetragen oder per CSV importiert (Spalte `Einspeiseverguetung_Cent`).

> **Kanonisches Finanz-Aggregat (SoT `core/berechnungen/finanz_aggregat.py`):** Netto-Ertrag,
> Einspeise-Erlös, EV-/BKW-Ersparnis und Sonstige-Netto werden **per-Monat** gerechnet und über die
> sichtbaren Monate summiert (nicht mit einem Ø-Preis) — bei Flex-Tarifen (Tibber/aWATTar/EPEX) laufen
> Monats-Preis und EV/Netzbezug-Split sonst auseinander (#326). Der **naive** `netto_ertrag_euro`
> = Einspeise-Erlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto; Sites mit Zusatzlogik (Cockpit
> zieht `USt_Eigenverbrauch` ab) bauen den Netto-Ertrag aus den Einzel-Komponenten selbst zusammen.

> **Der fünfte Summand — Erlös mit eigenem Vergütungssatz (§9.2 Geldseite, 06.09.2026):** Ein
> Gerät der Kategorie *Abgabe an Dritte* oder ein *Sonstiges/Erzeuger* mit eigenem Einspeisetarif
> trägt einen **gepflegten** Monatsbetrag (`einspeise_erloes_euro`). Er ist Teil des Netto-Ertrags
> (`finanz_aggregat.erzeuger_erloes_euro`) und steht **neben** `Einspeise-Erlös`, nicht darin: Jener
> bewertet den **Anlagenzähler** mit dem EINEN Satz der Anlage, dieser trägt einen Satz, den eedc
> nicht kennt und **nicht nachrechnet**. Alle Sichten führen ihn — Cockpit → Monat/Jahr,
> Auswertungen → Finanzen, HA-Sensor `netto_ertrag_euro`, Jahresbericht-PDF und Aussichten.

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
> eigener Kennzahlen-Entscheid. Jahresfaltung (`falte_zeitraum`, Backend seit 03.10.2026): Grundgebühr = Σ, Zählergebühr = letzter Wert.

> **Cockpit-Finanzen-Block = Komponenten-Finanz-Tabelle (G20-1, ab v4.0; fortgeschrieben 03.10.2026):** Der
> Finanzen-Block in Cockpit-Monat/-Jahr zeigt **eine Zeile je Komponente** (Reihenfolge = Typ-SoT) mit den Spalten
> **Erträge** (tatsächliche Zahlungsflüsse) · **Einsparungen** (kalkulatorisch/vermiedene Kosten) · **Aufwand** (inkl.
> anteilig umgelegter Betriebskosten, PV-Zeile bei Regelbesteuerung inkl. USt auf den Eigenverbrauch; die
> Netzladung des Speichers steht an seiner Zeile nur als Ausweis — sie läuft über den Hauszähler und steckt in der
> Stromrechnung, wie im T-Konto) · **Saldo**; die **Summenzeile ist die Block-Kopf-Kennzahl** (Kopf == sichtbare Summe). Bis
> 03.10.2026 stand hier, die Tabellen-Summe sei „bewusst eine dritte Netto-Semantik" — mit #402 (02.09.) trägt das nicht
> mehr: eine Attribution verteilt einen Betrag, sie vervielfacht ihn nicht. Die Tabelle verteilt dieselben Posten wie
> die **Ergebnis-Leiter** (oben) auf die Komponenten; ihre Zusatzzeile heißt seither **„Monatsergebnis"/„Jahresergebnis"**
> und **liest** `ergebnis_euro` (bis dahin „Ergebnis nach Stromrechnung" = Saldo − Netzbezug-Kosten, G20-4). Beide
> Wege führen auf dieselbe Zahl — die Probe P8 misst es an echten Antworten. Die zwei Abweichungen, die sie beim Bau
> fand, sind seit 03.10.2026 geschlossen: die **Wärmepumpen-Ersparnis** der Kachel ist die Σ der Gerätezeilen (Bauform
> wie die E-Mobilität, G20-2; vorher ein Aggregat mit dem Parametersatz der ersten Wärmepumpe), und die
> **Speicher-Netzladung** steht nicht mehr zusätzlich im Aufwand der Speicher-Zeile.
> *(Bis 03.10.2026 stand hier außerdem, die Vergleichs-Asymmetrie `gesamtnettoertrag` Monat vs. Vorjahr sei „kein
> Bug". Sie war einer: ein Vorjahr mit fehlender Stromrechnung zählte sie als 0. Seit der Ergebnis-Leiter folgt das
> Vorjahr derselben Regel wie der Monat; das Feld `gesamtnettoertrag_euro` ist entfallen.)*

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
- **WP-Preis** des Monats: WP-Tarif, sonst allgemeiner Tarif, am Stichtag des Monats (ADR-002/P8), mit Zeitfenstern.

**Eine Zeilenregel** (`services/wp_wirtschaftlichkeit.py::wp_ersparnis_zeile`, Monatssumme `wp_ersparnis_monat`) für
T-Konto und Kachel in *Cockpit → Monat* (auch ohne Gerätezeile), *Cockpit → Jahr* (Σ Monate), *Cockpit → Übersicht*
(Feld `wp_ersparnis_euro`, geht in `jahres_rendite_prozent`) und *Auswertungen → Komponenten*. Grund: zwei Wärmepumpen
haben keine gemeinsame Referenz-WP — bis 04.10.2026 rechneten Übersicht, Komponenten-Zeitreihe und der Monat ohne
Gerätezeile ein Aggregat mit dem Parametersatz der ersten Wärmepumpe, die Übersicht dazu mit dem heutigen Tarif und
ohne Monats-Gaspreis. Beispiel (zwei WP, Gas 10 bzw. 16 ct, je 900 kWh Wärme / 250 kWh Strom, 30 ct): Zeilen 25 € +
85 € = **110 €** in Monat, Jahr, Übersicht und Komponenten (vorher Übersicht 50 €); laufender Monat mit zwei WP
**5,76 €** (vorher 1,44 €). Die Zeilenrundung hält Σ Zeilen = Sicht: fünf Monate à 10,81 € sind 54,05 €, nicht 54,07 €.

Benannte Grenze: Ein Monat mit WP-Strom ohne Wärme (Standby) hat keine Zeile; HA-Export und Aussichten belasten dort
den Strom (gemessen 25 € gegen 19 €). Proben: `test_n605_wp_ersparnis_aus_geraetezeilen.py`,
`test_n609_wp_ersparnis_je_geraet.py`.

#### E-Mob-Ersparnis im Cockpit

```
Benzin_Verbrauch    = Σ(km_gefahren) * 7 / 100    (7 L/100km Annahme)
Benzin_Kosten       = Benzin_Verbrauch * 1.80      (1.80 EUR/L Annahme)
Strom_Kosten        = (Ladung_gesamt - Ladung_PV) * Wallbox_Preis / 100
E-Mob-Ersparnis     = Benzin_Kosten - Strom_Kosten
```

**Hinweis:** Dienstliche E-Autos/Wallboxen (`ist_dienstlich = true`) werden NICHT in die E-Mob-Ersparnis eingerechnet. Deren Ladekosten sind ein eigener Posten der Ergebnis-Leiter („Dienstliche Ladekosten", §3.2, seit N-633) — Formel und Begründung stehen in §3.10 unter **Dienstliche Ladekosten** — der PV-Anteil zählt dort zum **Netzbezugspreis**, nicht zur Einspeisevergütung.

> **G20-2 — Aggregat bei mehreren E-Autos = Σ der Einzel-Fahrzeuge:** Die Gesamt-E-Mob-Ersparnis wird als **Summe der pro Fahrzeug** gerechneten Ersparnisse gebildet — jedes E-Auto mit seinem **eigenen** Vergleichsverbrauch (L/100 km) und Benzinpreis. Sie ist NICHT ein Einmal-Lauf über die Gesamt-Kilometer mit dem Parametersatz des ersten Fahrzeugs (das überschätzte die Ersparnis, sobald zwei E-Autos unterschiedliche Vergleichsverbräuche hatten). Bei genau **einem** E-Auto ist das Ergebnis unverändert. Die Per-Fahrzeug-Zeilen (T-Konto) rechneten schon immer je Fahrzeug korrekt; nur das aggregierte Cockpit-Feld ist jetzt symmetrisch dazu.

**Heimladung je Auto (ab v4.0.51, N-555 Stufe 2):** Die Wallbox ist die **Summe** aller Ladungen an ihr; jedes Auto mit eigener Messung trägt seine eigene Heimladung, die Wallbox den Rest (Regel 2 und 3 unten). Bei mehreren Wallboxen zählt ihre Summe. Die Netzladung **je Fahrzeug** in der Ersparnis ist die Summe seiner Monatsmengen aus dem Entscheid (`EmobFakten.je_auto`), nicht mehr ein km-Anteil an einem gemeinsamen Topf; ein Auto, das geladen hat, aber nicht gefahren ist, trägt seine Stromkosten (Ersparnis negativ statt 0). Zentraler Helper: `entscheide_emob_heimladung()` (`services/eauto_wirtschaftlichkeit.py`; `get_emob_heimladung_canonical()` ist seine Kurzform). *Bis v4.0.50 (Phase 2a, Entscheidung 1):* existierte eine Wallbox mit Heimladung, war sie die einzige Quelle, und Heimlade-Werte am Auto zählten daneben nicht.

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

**Regel 2 — wer welche Heimladung trägt** (je Monat, ab v4.0.51):

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

Beispiel (gemeldet, Johnny_1993): Wallbox mit HA-Sensor, 0 kWh im September, am Auto nur „Verbrauch" 1.364 kWh ⇒
Wallbox 0 ⇒ Rest 0 ⇒ Heimladung **0**. Der Verbrauch zählt nur für die kWh/100 km. Eine Schätzung bekommt denselben aus
der Tagesebene abgeleiteten PV-Anteil wie jede andere Heimladung (s. „PV-Anteil der Heimladung" unten).

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

**Ladevorgänge je Auto — Regel 9 (ab v4.0.51, N-555 Stufe 3):** Trägt ein Auto an „Heim: gesamt" einen **Zähler**, der
am Ende eines Ladevorgangs um dessen Menge springt (evcc-Fahrzeug-Sensor), und hat eine Wallbox in Betrieb einen
Ladezähler, ordnet die Tagesberechnung jeden Sprung den Stunden der Wallbox zu (`services/emob_ladebloecke.py`, Ablage
`emob_ladebloecke`, geschrieben aus `aggregate_day`):

```
Block    vom Sprung rückwärts über die Wallbox-Stunden; aus jeder Stunde, was frühere Blöcke nicht genommen
         haben — in der Sprungstunde höchstens den Bedarf, davor höchstens Bedarf + 0,05 kWh —, bis
         Σ ≥ Sprung − 0,05 kWh, höchstens bis zur Stunde des vorigen Sprungs IRGENDEINES Autos (einschließlich).
         Nullstunden werden übersprungen; eine gemeinsame Stunde wird nach Restmengen geteilt.
Menge    = der Sprung (gemessen am Auto) — nie die Summe der Wallbox-Stunden.
PV       = Σ (Blockstunde × PV-Anteil dieser Stunde nach der Einspeise-Deckung) ÷ Σ Blockstunden × Sprung
           (davon aus dem Speicher ebenso, als Teilmenge);
           eine gebündelte Stunde (Zählerlücke, n > 1) zählt zur Blockenergie, liefert aber keinen Anteil —
           ohne ableitbare Stunde teilt der Wallbox-Monatsanteil. Der Anteil ist eine Schätzung derselben
           Regel wie der PV-Anteil der Heimladung.
Monat    Anteil eines Monats = Σ Blockstunden, die in ihm BEGINNEN, ÷ Σ Blockstunden, angewandt auf den Sprung.
           Ein Sprung ohne Blockstunde zählt im Monat des Sprungs.
Kennzeichen  stunden_gedeckt = Σ Blockstunden ÷ Sprung; unter 0,95 hat die Wallbox den Vorgang nicht voll gezählt.
           Mikrosprünge bis 0,05 kWh (Standby des Fahrzeug-Zählers) zählen als Menge, nicht als Ladevorgang.
```

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

**Zeitraum (Jahr, Übersicht, Hub, Auswertungen) — ab N-557:** Jeder Monat entscheidet für sich (Regel oben), der
Zeitraum ist die **Summe der Monatswerte geteilt durch die Summe der Kilometer**
(`eauto_effizienz_zeitraum`; *Cockpit → Jahr* ruft sie seit 03.10.2026 über die Jahresroute, der frühere Client-Spiegel ist entfallen). Monate ohne jede
Energiemenge zählen weder im Zähler noch im Nenner. „gemessen" steht nur, wenn **jeder** Monat mit Kilometern gemessen
ist, sonst „Näherung über die Ladung". Bis v4.0.50 teilte das Aggregat den Fahrverbrauch der Monate **mit** Sensor
durch die Kilometer **aller** Monate — mit einem Verbrauchssensor ab Juli also rund die halbe Zahl, beschriftet
„gemessen"; *Cockpit → Jahr* bildete sogar Heimladung ÷ km.

**„Ladung gesamt" — ab N-557:** Heimladung **plus Extern**, soweit Extern bekannt ist (mit Sensor im laufenden Monat
sofort, bei Pflege von Hand ab dem Monatsabschluss); darunter „davon extern … kWh". Eine **eigene** Anzeige-Größe
(`emob_ladung_gesamt_kwh`): die Heimladung (`emob_ladung_kwh`) behält ihre Bedeutung, der **PV-Anteil** bleibt auf
die Heimladung bezogen, T-Konto, CO₂ und Community rechnen weiter mit ihr. Extern liegt außerhalb der Hausbilanz.

**Hinweis Kraftstoffpreis (ab v3.17.0):** Im Cockpit werden weiterhin die hardcodierten Defaults verwendet. In der **Finanz-Prognose** ([Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen)), im **HA-Sensor-Export** und im **PDF-Finanzbericht** wird stattdessen pro Monat der echte Kraftstoffpreis aus `Monatsdaten.kraftstoffpreis_euro` verwendet (Quelle: EU Weekly Oil Bulletin). Fallback auf den statischen `benzinpreis_euro`-Parameter der Komponente wenn kein Monatswert vorhanden. Das Formularfeld *Benzinpreis (€/L)* ist seit 27.09.2026 (N-572) nicht mehr vorbelegt: ein geleertes Feld bleibt leer, und die Kette fällt dann auf 1,65 €/L zurück.

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
| `arbitrage_faehig` | `Investition.parameter["arbitrage_faehig"]` (Default: false) — der Kanon; `nutzt_arbitrage` war der Name vor v3.25.0 |
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
Komponenten-Hub (`investitionen/dashboard_*.py`), Cockpit Tag (`energie_profil/tage_werte.py`),
Monat/Jahr (`aktueller_monat.py`) und **Cockpit-Übersicht (`cockpit/uebersicht.py`)**,
PDF-Jahresbericht, HA-Sensor `speicher_zyklen`.
Gewächtert von `backend/tests/test_speicher_zyklen_kapazitaets_basis.py` (inkl. Drei-Pfad-Symmetrie),
`test_tage_werte_symmetrie.py` und `test_speicher_kanon_symmetrie.py`.

> ⚠ **Diese Aufzählung war bis zum 2026-08-04 unvollständig — und genau die fehlende Zeile war die
> fehlerhafte.** `cockpit/uebersicht.py` rechnete weiterhin `Ladung ÷ Kapazität`; der Sweep vom
> 2026-07-28 hatte die Route übersehen, und weil ihr Wert damals keinen Client-Leser hatte, fiel es
> niemandem auf (#358 gab ihm einen). **Lehre:** eine Liste von Aufrufern in der Doku ist eine
> Behauptung über den Code — sie gehört mit einem baumweiten Grep belegt, sonst dokumentiert sie
> den Soll- statt den Ist-Zustand.

**Warum die Entladung:** Ein Vollzyklus meint die einmal *entnommene* Kapazität — die Größe, auf die
sich Hersteller-Garantien beziehen, und unabhängig von den Wandlungsverlusten des Ladepfads. Sie ist
außerdem ein Energiedurchsatz und damit über Tag → Monat → Jahr additiv.

**Warum Brutto im Nenner:** `nutzbare_kapazitaet_kwh` ist optional und meist nicht gepflegt; ein
Nenner, der je nach Pflegezustand wechselt, wäre schlimmer als ein durchgehend leicht konservativer
Wert. Im HA-Export ist das Netto-Feld reiner **Fallback**, falls die Brutto-Kapazität fehlt — die
Lese-Reihenfolge dort ist bewusst brutto → netto und bleibt es auch nach A31-2.

#### Auslastung — zeitraum-normierte Nutzung (#358 Phase 1)

```
Auslastungs-Basis  = Kapazität_brutto_kWh × Tage_im_Zeitraum
Auslastung [%]     = Entladung_kWh ÷ Auslastungs-Basis × 100
```

**SoT:** `core/berechnungen/speicher.py::auslastungs_basis_kwh` + `auslastung_prozent`.
Geliefert von `aktueller_monat.py` (Felder `speicher_auslastungs_basis_kwh` /
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
Aufrufer: T-Konto (`aktueller_monat/tkonto.py::_baue_investition_financial`), Speicher-Dashboard und
Sonstiges-Speicher (`investitionen/dashboard_sonstiges.py`), Aussichten. Gewächtert von
`test_speicher_kanon_symmetrie.py` (drei Achsen, mit **absoluten** Erwartungen — Symmetrie allein
ließe auch drei gleich falsche Zahlen durch, Lehre aus N-130).

**Warum der Spread:** die entladene kWh ersetzt Netzbezug, hätte aber sonst Einspeisevergütung
erbracht. Die entgangene Vergütung ist eine reale Gegenposition (Drift-Audit A3, von Gernot am
2026-08-04 für #358 bestätigt).

**Warum die Netzladung ausgenommen ist:** sie hätte nie eingespeist werden können, der PV-Spread
gilt für sie nicht. Ihr Vorteil ist `Netzbezug − Ladepreis`; ohne gepflegten Ladepreis ist sie
kostenneutrale Durchleitung (z. B. Backup-Vorhaltung).

> ⚠ **Zwei Fundstellen wichen bis zum 2026-08-04 ab** — beide sichtbar: `aktueller_monat.py`
> rechnete `Entladung × Netzbezug` (bei 30/8 ct **36 % zu hoch**), `dashboard_speicher.py` (damals `dashboards.py`) den Spread
> **inline** auf der gesamten Entladung *und* wies den Arbitrage-Gewinn zusätzlich aus — der
> Komponenten-Hub addiert beide Posten, netzgeladene Energie zählte damit doppelt. Die Formel im
> Layer zu haben genügt nicht; sie ist erst durchgesetzt, wenn keine Inline-Kopie mehr danebensteht
> (ADR-001).

#### Welche Stunde gilt — Ladestand, Preis und Menge (N-387, 2026-09-23)

Eine Stundenzeile trägt **zwei Uhren** (SoT `core/berechnungen/slot_konvention.py`): die
`*_kw`-Spalten meinen das Intervall **vor** ihrer Stunde (`[s-1, s)`, Backward-Konvention #144),
`soc_prozent`, `strompreis_cent` und `boersenpreis_cent` dagegen das Intervall **ab** ihrer Stunde
(`[s, s+1)`) — so liefert Home Assistant sie. **Wer beide Hälften verrechnet, nimmt den
Ladestand bzw. Preis deshalb aus der Zeile davor** (über die Tagesgrenze: aus der Zeile 23 des
Vortags). Der eine Ort dafür ist `slot_konvention.forward_werte_je_backward_zeile`.

Das betrifft sichtbar:

* **Speicher-Potential** — „Überschuss bei vollem Speicher" zählte bis dahin auch die Einspeisung
  der Stunde **vor** dem Vollwerden, „Fehlmenge bei leerem Speicher" spiegelbildlich den Netzbezug
  der Stunde, in der er erst leerlief. Das Fenster lag eine Stunde zu früh.
* **Effektiver Ladepreis und Entladewert** — die Netzladung einer Stunde zahlte den Preis der
  Nachbarstunde. Bei einem **Festpreis** ändert das nichts (jede Stunde derselbe Preis); bei einem
  dynamischen Tarif ist es die volle Differenz zweier Nachbarstunden.
* **Tageskosten, Monats-Ø-Preis und Eigenverbrauchs-Ersparnis** der Flex-Kaskade
  ([KONZEPT-FLEX-TARIFE §2](KONZEPT-FLEX-TARIFE.md)) sowie der **§51-Einspeiseerlös**.
* **Die Stundenliste des Tagesdetails** (`GET /energie-profil/{id}/stunden`, N-553): Sie zeigt
  keine Rechnung, aber dieselbe Zeile — wer in *Cockpit → Tag → Stundenwerte* die Spalte „SoC"
  einschaltet, las den Ladestand der Nachbarstunde neben dem Batteriefluss. Die Liste trägt den
  Ladestand jetzt zur Stunde ihrer Zeile.

> ⭐ **„Stand am Tagesende" ist eine andere Frage und hat deshalb eine eigene Größe** (N-553).
> Die Kachel *Ladestand* im Speicher-Block fragt „wie voll war der Speicher **zuletzt**", nicht
> „welcher Stand gehört zu dieser Stunde". Der jüngste Messwert wandert durch die Paarung aus dem
> Tagesraster (sein Intervall `[23, 24)` liegt backward schon im Folgetag), und am **laufenden**
> Tag wäre die Kachel damit eine Stunde älter geworden. Die Antwort führt ihn deshalb ungepaart
> als `soc_zuletzt_prozent` mit. **Spanne** (min/max) ist gegen die Zuordnung unempfindlich und
> kommt weiter aus der Liste.

> ⛔ **Zwei Stellen paaren bewusst OHNE diese Umkehr, beide gemessen.**
> (1) Der **Wirkungsgrad am Periodenrand** (`speicher_wirtschaftlichkeit._lese_soc_am_periodenrand`)
> stellt SoC-Randzeilen gegen **Monatsintegrale**: Zeile 0 liegt ½ h nach dem Periodenbeginn,
> Zeile 23 ½ h vor dem Ende — symmetrisch; die Vorzeile machte daraus 1½ h und wäre schlechter.
> (2) Die **Sizing-Kalibrierung** (`speicher_sizing_service._als_sizing_stunde`) bildet eine
> *Differenz zweier Stundenmittel* und stellt sie einer **einzelnen** Stundenmenge gegenüber:
> `ΔSoC(s−1 → s) ≈ ½ (b_s + b_{s+1})`, verglichen wird aber `b_s` allein. **Beide Fassungen
> verfehlen gleichermaßen** — an einer reinen Demo-Reihe (4 800 Stunden, Wahrheit 10,0 kWh je
> 100 % SoC und Roundtrip 1,00) liefert die Zeilen-Paarung 10,03/11,11 (Roundtrip 1,108), die
> Vorzeile 12,44/13,62 (1,095); **beide fallen aus dem Plausibilitätsband und ergeben `None`**,
> die Sicht nimmt dann die gepflegten Werte. Die Paarung ist hier also nicht die Stellschraube.
> **Die Lösung ist die Formel** — der Hub gehört gegen das *Mittel der zwei angrenzenden
> Stundenmengen*.

#### Wie die Sizing-Kalibrierung Kapazität und Wirkungsgrad misst (N-552, 23.09.2026)

Der *Größerer Speicher?*-Simulator braucht die **tatsächlich nutzbare** Kapazität und den
Roundtrip-Wirkungsgrad. eedc misst beides aus der Bewegung des Ladestands: Wo der Speicher in einer
Stunde deutlich lädt oder entlädt, wird der Hub des Ladestands gegen die bewegte Energie gestellt.

Beide Ladestände sind **Stundenmittel**. Ihre Differenz beschreibt deshalb den Fluss zwischen den
**Mitten** der beiden Stunden, also je zur Hälfte zwei Wanduhr-Stunden — und genau diese zwei
halben Stunden stellt eedc dem Hub seit N-552 gegenüber (`½ (b_s + b_{s+1})` bei heutigen Zeilen,
`½ (b_{s−1} + b_s)` bei Altbestand vor dem 04.06.2026, entschieden je Zeile an ihrer
Aggregationszeit). Läuft die eine Hälfte in die andere Richtung als die zweite, zählt der Hub nicht:
dann mischt er zwei Wirkungsgrade.

**Gemessen an einem echten Jahr** (eine Anlage, 356 vollständige Tage): Der Hub folgt der Formel mit
einer Korrelation von 0,98 (die Einzelstunde vorher: 0,95). Gegen die gemessene Einspeisung und den
gemessenen Netzbezug weicht die simulierte Anlage jetzt um zusammen 3,3 Prozentpunkte ab statt 4,9;
der Wirkungsgrad bleibt über Zeiträume und Schwellen stabil bei 72–74 % (vorher 82–88 %). Die
nutzbare Kapazität hängt weiter am Median der selteneren Entladestunden und kann zwischen Zeiträumen
um einige Zehntel Kilowattstunden schwanken. Die Mindestschwelle von 10 Prozentpunkten Hub bleibt:
eine höhere wäre an dieser Anlage minimal besser, halbierte aber die Entladestunden und ließe
Anlagen mit weniger Daten auf die gepflegten Werte zurückfallen.

> ⛔ **Die Umkehr gilt nicht rückwirkend für jede gespeicherte Zeile.** Der HA-Stundenpfad
> beschriftete seine Energiemengen bis zum **04.06.2026** selbst *forward* — auf einer Zeile, die
> damals aggregiert wurde, ist die Paarung innerhalb **derselben** Zeile die richtige. eedc
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

> ⚑ **Und seit N-238 (2026-08-12) gehört der Wirkungsgrad dazu.** Die Tages-Vorschau rechnete den
> Ladeweg **verlustfrei** — für 12 kWh im Speicher hielt sie 12 kWh Überschuss für ausreichend,
> real sind es bei η = 95 % rund 12,7 und bei 85 % über 14. „Speicher voll um" lag deshalb
> systematisch **vor** der tatsächlichen Uhrzeit. Kapazität **und** Wirkungsgrad kommen jetzt aus
> **einem** Helper (`aggregiere_speicher_basis`: Kapazität summiert, Wirkungsgrad als **Minimum** —
> eine Kette ist nicht besser als ihr schwächstes Glied); der HA-Sensor und die Kachel lesen
> dieselbe Regel, statt sie zweimal zu bilden. Die Verluste sitzen ganz auf der **Ladeseite**, weil
> die übergebene Kapazität die abgabefähige Menge ist — sie zusätzlich beim Entladen anzusetzen wäre
> Doppelzählung (dieselbe Konvention wie `core/berechnungen/speicher_sizing.py`).
>
> ⚑ **Welche Geräte in den Helper gehen, entscheidet der Aufrufer — und für die beiden
> Planungs-Sichten sind es seit N-546 (2026-09-22) nur die HEUTE laufenden.** `Sizing` und
> `Speicher-Potential` holten bis dahin **alle** Investitionen vom Typ Speicher, ohne `aktiv`
> und ohne `stilllegungsdatum`; ein abgelöstes Gerät hob damit die Kapazität, senkte über das
> **Minimum** den Wirkungsgrad und verschob die Leer-Schwelle (beide Summen gehen ein).
> Stichtag ist `date.today()` und nicht das Fenster-Ende: beide Sichten fragen nach vorn, wie
> schon der Tarif im Docstring von `speicher_sizing_service.py`.
>
> ⚠ **Die gepflegte Kapazität bleibt maßgeblich und wird NICHT durch die gemessene ersetzt**
> (Gernots Entscheid 2026-08-12). Sie trägt eine **Absicht**: es gibt Anwender, die ihren Speicher
> bewusst nicht auf 100 % laden, und für die wäre eine Korrektur nach unten falsch — sie wollen
> wissen, wann *ihr* Ziel erreicht ist. Der Sizing-Block weist die gemessene Größe stattdessen
> **daneben** aus und trennt die zwei Ursachen einer Lücke (Ladegrenze ⟷ Ladeverlust) über den
> tatsächlich genutzten Ladestands-Bereich (`messe_soc_nutzung`).

> ⚑ **Seit #379 (2026-08-15) trägt das Netto-Feld eine dritte Aussage: die Entlade-Untergrenze.**
> Aus dem Verhältnis beider Kapazitäten leitet `core/berechnungen/speicher_potential.py::
> leer_schwelle_prozent` ab, ab welchem Ladestand *dieser* Speicher nichts mehr abgibt —
> `(1 − netto ÷ brutto) × 100`, bei 24 von 30 kWh also 20 %. Vorher stand dort die feste Zahl
> **5 %**, und das war ein Fehler mit Folgen: Wer eine eigene Untergrenze fährt, dessen Speicher
> erreicht 5 % **nie**, also lief er nie „leer", also war das *Nutzbare Zusatzpotential*
> **strukturell 0** — die Sicht behauptete „ein größerer Speicher hätte nichts gebracht", obwohl
> sie es gar nicht messen konnte.
>
> Drei Festlegungen gehören dazu, jede aus einer Messung:
>
> * **Aufschlag von 3 Prozentpunkten** (`SOC_LEER_TOLERANZ_PP`). Der Melder hat 20 % eingestellt,
>   seine Kurve dreht bei **21 %** — Wechselrichter schalten mit Puffer ab, der SoC kommt in ganzen
>   Prozent, und diese Auswertung liest Stundenmittel. Ohne Aufschlag träfe die neue Schwelle so
>   zuverlässig daneben wie die alte.
> * **Deckel bei 50 %** (`SOC_LEER_MAX_PROZENT`) gegen die N-235-Klasse: „1 kWh nutzbar von 30"
>   ergäbe sonst 96,7 % und ließe den Speicher fast immer als leer gelten — die Kennzahl fiele zu
>   **hoch** aus, also in die Gegenrichtung der Deckelung.
> * **Die Reserve sitzt unten.** Bei Heimspeichern der Normalfall; die Oberseite deckt
>   `SOC_VOLL_PROZENT` ab, und eine gewollte *Lade*-Grenze erkennt `messe_soc_nutzung` an den Daten.
>   ⛔ **Hier stand bis 2026-08-31 nur diese Annahme, ohne ihren Preis.** Trifft sie nicht zu,
>   fällt die Schwelle zu hoch aus — und die Kennzahl damit zu **hoch**, nicht konservativ.
>   Am Minimalfall gemessen (31.08.): 10 kWh brutto, Fahrweise 10/90 ⇒ Eintrag 8 kWh ⇒ Schwelle
>   **23 % statt 13 %**; `berechne_zusatzpotential` zählt ab da mehr Netzbezug in die Fehlmenge,
>   das nutzbare Zusatzpotential wuchs von **3,0 auf 5,0 kWh**. Das ist die Richtung, gegen die
>   §3.3 gebaut ist. ⚠ **Und es ist kein Einzelfall:** `nutzbare_kapazitaet_kwh` meint vertraglich
>   den **ganzen** fahrbaren SoC-Hub, das Handbuch weist das 10/90-Muster ausdrücklich an — wer
>   eine obere Ladegrenze fährt, pflegt also korrekt und bekommt trotzdem die zu hohe Untergrenze.
>   **Gebaut wurde kein zweites Feld** (Entscheid Gernot 15.08. steht), sondern die Annahme an
>   beiden Anzeigen: im Speicher-Formular beim Eintippen und im Block *Größerer Speicher?*.
>   Auslöser: cbrosius auf [#379](https://github.com/supernova1963/eedc-homeassistant/issues/379).
>
> ⚠ **Wer nichts pflegt, sieht keine geänderte Zahl** — Rückfall auf 5 %, Abnahmekriterium des Baus.
> Umgekehrt heißt das: Die Korrektur erreicht nur Anlagen mit gepflegter nutzbarer Kapazität.
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
> Aussage, für den die Kennzahl gebaut wurde (Dev-Anlage, nie unter 31 %). Ist die Schwelle
> abgeleitet, kennt eedc die Untergrenze, und ein Speicher, der sie nicht erreicht, war wirklich
> groß genug. Wer seinen Boden real berührt (Winter, 6 %), bekommt die klare Aussage ebenfalls.
>
> ⚠ **Die Schwelle gilt im ganzen Speicher-Hub, nicht nur in Phase 2.** `speicher_sizing.py`
> definierte `95.0`/`5.0` bis dahin **selbst** — mit dem Kommentar „dieselben Schwellen wie in
> `speicher_potential.py`". Die Absicht war formuliert, die Kopplung fehlte; ein `==`-Test hätte
> nie angeschlagen, weil beide Werte gleich waren. Jetzt Import statt Kopie, geprüft an der Quelle.

**SoT netto (seit A31-2):** `core/investition_kennwerte.py::get_speicher_nutzbare_kapazitaet_kwh` —
netto, sonst brutto, sonst `None`. Der Brutto-Fallback ist **still** (Entscheidung **E17**): kein
Hinweis, keine Kennzeichnung, **kein P4-Fall**. Der Brutto-Wert ist nicht *unvollständig*, er ist die
andere gültige Lesart derselben Größe; die Zahlenänderung aus A31-2 trifft deshalb ausschließlich
Anlagen, die das optionale Feld bewusst gepflegt haben. Die Leserichtung geht nur netto → brutto und
**nie** zurück — ein Brutto-Helper mit Netto-Fallback wäre genau die Verwechslung, die die Vollzyklen
wieder vom Pflegezustand abhängig machte.

**Nebenwirkung der Vorschau, die dazugehört:** dieselbe Simulation liefert auch Einspeisung,
Eigenverbrauch und Autarkie des Vorschautags. Ein kleinerer Puffer nimmt weniger Überschuss auf —
mehr geht ins Netz. Gemessen an der Demo-Anlage (15,4 kWh brutto gegen
13,9 kWh netto, 28.07.–02.08.2026): Einspeisung +0,75 bis +1,08 kWh/Tag,
Autarkie −1,7 bis −3,2 Prozentpunkte, „Speicher voll" an einem der sechs Tage eine Stunde
früher (die Stundenauflösung verschluckt den Effekt an den übrigen). Der **Eigenverbrauch** sinkt seit N-635
(05.10.2026, Direktverbrauch + Entladung statt PV − Einspeisung) nur noch, wenn der kleinere Speicher den Abend
nicht mehr trägt; trägt er ihn, bleibt er gleich (vorher zählte die Ladung mit, und der größere Speicher
„verbrauchte" mehr).

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

> **Der Layer-SoT `speicher_effizienz_prozent` klemmt bewusst NICHT**
> („Diagnose statt stillem Cap"). Die Diagnose ist der Daten-Checker: meldet ein
> Speicher **kumulativ** mehr Entladung als Ladung, ist das kein Carry-over mehr,
> sondern ein Erfassungsfehler — meist `ladung_kwh` als reine PV-Ladung gepflegt
> (#281). `ladung_netz_kwh` ⊆ `ladung_kwh` ist Vertrag, kein zweiter Posten.

> **Historie (F-22, rapahl 2026-05-22 **und** 2026-08-08):** Bis v4.0.11 stand in
> `aktueller_monat.py` ein Alles-oder-Nichts-Schalter auf `|ΔSoC| > 20 pp` — über
> der Schwelle wurde ausgeblendet, darunter der **rohe** Wert gezeigt; korrigiert
> wurde nie, und ohne SoC-Randwerte ging er **ungeprüft** hinaus. Gemessen an der
> Demo-Anlage: 2025-11 „—" statt 81,6 %, 2025-10 roh 83,1 statt 82,4 %. Die
> korrigierende Funktion existierte seit #264 und erreichte 2 von 12 Sichten —
> dieselbe Klasse wie F-16.

### 3.4 E-Auto-Einsparung

**Funktion:** `berechne_eauto_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`investitionen.py`)

#### Eingabefelder

| Feld | Quelle |
|------|--------|
| `jahresfahrleistung_km` | `Investition.parameter` (Default: 15000) |
| `verbrauch_kwh_100km` | `Investition.parameter` (Default: 18) |
| `pv_ladeanteil_prozent` | `Investition.parameter` (Default: 60) — im Formular **nicht vorbelegt** (N-572, 27.09.2026): ein geleertes Feld bleibt leer, dann gilt der gemessene IST-Anteil, ohne Messung 60 (s. N-188 unten) |
| `benzinpreis_euro` | `Investition.parameter` (Default: 1,65) — im Formular **nicht vorbelegt** (N-572): ein geleertes Feld bleibt leer, dann gilt der Kraftstoffpreis der Monatsdaten, ohne ihn 1,65 |
| `vergleich_verbrauch_l_100km` | `Investition.parameter` (Default: 7,5) — der **fiktive** Vergleichs-Benziner |
| `v2h_faehig` | `Investition.parameter` (Default: false) |
| `eigener_verbrauch_l_100km` | `Investition.parameter` — **kein Default**, s. „Plug-in-Hybrid" unten |
| `elektrischer_fahranteil_prozent` | `Investition.parameter` — **kein Default** |

> ⚠ **Diese Tabelle nannte bis 2026-08-08 vier Schlüssel, die eedc nicht kennt**
> (`km_jahr`, `pv_anteil_prozent`, `benzin_verbrauch_liter_100km`, `nutzt_v2h`) und
> zwei falsche Defaults (1,85 € statt 1,65 €; 7,0 L statt 7,5 L). Es sind genau die
> Legacy-Keys, deren Lesen v3.25.0 im Code als Bugs #1–#4 korrigiert hat —
> die Doku ist damals nicht mitgezogen. Historie: `LEGACY_PARAM_KEYS` in
> `core/investition_parameter.py` führt die Zuordnung alt → neu.

#### Formeln

```
km_elektrisch        = jahresfahrleistung_km                    (BEV — Normalfall)
                     = jahresfahrleistung_km * Fahranteil / 100 (Plug-in-Hybrid, s. u.)
km_verbrenner        = jahresfahrleistung_km - km_elektrisch

Strom_Bedarf         = km_elektrisch * Verbrauch_kWh_100km / 100
PV_Anteil            = pv_ladeanteil_prozent / 100
Netz_Anteil          = 1 - PV_Anteil

Strom_Kosten         = Strom_Bedarf * Netz_Anteil * Strompreis / 100
Benzin_Verbrauch     = jahresfahrleistung_km * Vergleich_L_100km / 100   ← ALLE Kilometer
Benzin_Kosten        = Benzin_Verbrauch * Benzinpreis_EUR
Fossile_Kosten       = km_verbrenner / 100 * Eigener_L_100km * Benzinpreis_EUR

V2H_Einsparung       = V2H_Entladung_kWh * V2H_Preis / 100    (wenn V2H aktiv)
    V2H_Preis        = v2h_entlade_preis_cent                 (Override, optional)
                     = Bezugspreis - Einspeisevergütung       (Normalfall, aus den gepflegten Tarifen)

Jahres-Einsparung    = Benzin_Kosten - Strom_Kosten - Fossile_Kosten + V2H_Einsparung

CO2_Verbrenner       = Benzin_Verbrauch * 2.37
CO2_E-Auto           = Strom_Bedarf * Netz_Anteil * 0.38
CO2_Fossil           = km_verbrenner / 100 * Eigener_L_100km * 2.37
CO2-Einsparung       = CO2_Verbrenner - CO2_E-Auto - CO2_Fossil
```

#### Plug-in-Hybrid: elektrischer und fossiler Anteil (ab #331)

Ein Plug-in-Hybrid fährt einen Teil seiner Kilometer mit Kraftstoff. eedc unterstellte
bis dahin **100 % elektrisch** — Ersparnis und CO₂-Bilanz fielen dadurch zu gut aus.

**Es gibt keinen Fahrzeugtyp und keinen Schalter: das gepflegte Feld ist die Aussage.**
Ist `eigener_verbrauch_l_100km` gesetzt, hat das Fahrzeug einen Verbrenner; ist es leer,
bleibt **jede Zahl exakt wie vorher**. Bestandsfahrzeuge tragen das Feld nicht, für sie
ändert sich nichts.

Wie der elektrische Anteil bestimmt wird (SoT `core/berechnungen/phev_anteil.py`,
dieselbe Funktion für IST **und** Prognose):

| Weg | Bedingung | Rechnung |
| --- | --- | --- |
| **gemessen** | monatlicher Fahrverbrauch (kWh) erfasst | `km_elektrisch = min(km_gefahren, Fahrverbrauch / Verbrauch_kWh_100km × 100)` |
| **geschätzt** | nur `elektrischer_fahranteil_prozent` gepflegt | `km_elektrisch = km_gefahren × Anteil / 100` |
| **unbestimmt** | keines von beiden | `km_elektrisch = km_gefahren` (Verhalten wie vorher) — der Daten-Checker meldet es |

> ⚠ **Die Deckelung auf die gefahrenen Kilometer ist nicht kosmetisch.** Ist der
> Kennwert zu niedrig gepflegt oder der Zähler zu großzügig, käme rechnerisch mehr
> elektrische Strecke heraus als gefahren wurde — und damit negative Verbrenner-Kilometer,
> also eine Ersparnis größer als die Wahrheit.

**Zwei Verbräuche, zwei Bedeutungen:** `vergleich_verbrauch_l_100km` beschreibt weiterhin
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

Für Jahresprognose:
  Prognose_Benzinpreis = Ø(Monatsdaten.kraftstoffpreis_euro)  (historischer Durchschnitt)
                       ∨ Investition.parameter.benzinpreis_euro  (Fallback)
```

**Datenquelle:** EU Weekly Oil Bulletin (Euro-Super 95, inkl. Steuern, wöchentlich, History seit 2005). Befüllung durch den Scheduler-Job (**täglich 06:00 + Startlauf**), den Reparatur-Pfad „Kraftstoffpreise nachpflegen" oder den Backfill-Endpoint. Fehlt der Monatswert, rechnet die Kette mit dem Investitions-Parameter bzw. 1,65 €/L weiter — der Daten-Checker meldet offene Monate deshalb als eigene Kategorie. Das Feld *Benzinpreis (€/L)* am E-Auto ist seit 27.09.2026 (N-572) nicht mehr mit 1,65 vorbelegt: ein geleertes Feld bleibt beim nächsten Speichern leer, und es gilt der Monatspreis bzw. 1,65 €/L. Wer dort eine Zahl einträgt, legt den Preis fest — in der ROI-Sicht (`resolve_eauto_benzinpreis`) hat sie Vorrang vor dem jüngsten Monatspreis.

**Betroffen:** Aussichten (`aussichten/finanzen.py`), HA-Sensor-Export (`ha_export.py`), PDF-Finanzbericht (`pdf_operations.py`).

#### PV-Anteil der Heimladung: gemessen, sonst abgeleitet (ab 2026-08-08, N-141)

Die Formeln oben beschreiben die **Prognose**-Achse, die den von Hand gepflegten
`pv_ladeanteil_prozent` liest — und, wo er fehlt oder leer ist, seit 2026-08-08 den IST-Anteil (s. unten;
das Formularfeld ist seit N-572 nicht mehr vorbelegt, ein geleertes Feld bleibt leer).
Auf der **IST**-Achse gibt es diesen Parameter nicht — dort steht
je Monat das erfasste Paar `ladung_pv_kwh` / `ladung_netz_kwh`. Und genau das fehlte den meisten
Anlagen: **eine Wallbox misst ihren PV-Anteil nicht**, sie zählt nur Kilowattstunden. Ohne evcc
oder einen eigenen Zähler lieferte `get_emob_pv_netz_kwh` deshalb `(0, Gesamtladung)` — die
gesamte Heimladung galt als Netzstrom.

**Reihenfolge (SoT `core/berechnungen/pv_anteil_ladung.py`):**

1. **Ein erfasster Wert gewinnt immer** — auch eine gepflegte **0**. Geprüft wird die Anwesenheit
   des Schlüssels `ladung_pv_kwh`, nicht seine Größe: „diesen Monat kam nichts aus der Sonne" ist
   eine Aussage, keine Lücke.
2. **Sonst leitet eedc den Anteil aus den eigenen Stundenwerten ab**, Regel **Einspeise-Deckung**:

   ```
   je Stunde:  ungedeckt = max(0, Ladung − Netzbezug)          (ab v4.0.51, N-569)
               PV        = min(Ladung, ungedeckt + Einspeisung)
               Netz      = Ladung − PV
               davon aus dem Speicher = min(Speicherentladung, PV)   (nur Ausweis)
   ```
   Der Speicheranteil rechnet mit dem **Stunden-Netto** der Batterie (Entladung − Ladung derselben Stunde): lädt und entlädt der
   Speicher in einer Stunde, untertreibt er (Lab-Fixture 21,7 % netto gegen 24,8 % brutto); der PV-Anteil ist davon unberührt.

   Der zweite Summand fängt die Unschärfe der Stundenmittelung auf: Was in derselben Stunde
   eingespeist wurde, hätte stattdessen laden können. **Die Speicherentladung zählt zur PV-Deckung**
   (bis v4.0.50 wurde sie abgezogen): der PV-Anteil sagt, wie viel der Ladung nicht aus dem Netz kam,
   und gespeicherter Eigenstrom ist Eigenstrom. „Davon aus dem Speicher" ist eine **Teilmenge** des
   PV-Anteils (PV = Direkt + Speicher), gezeigt als Unterzeile im E-Auto-Hub; ohne Speicherzähler gibt
   es sie nicht, und keine Kosten-, Ersparnis-, CO₂- oder Community-Rechnung liest sie.
3. **Angewandt wird der Anteil, nicht die Kilowattstunde.** Der abgeleitete Prozentsatz geht auf
   die kanonische Monatsladung — nur so bleibt `Ladung == PV + Netz` exakt geschlossen, auch wenn
   die Tagesspur eine andere Menge kennt als die Monatszeile.

**Wo die Regel angewandt wird — eine Schicht unter dem Pool** (`services/emob_ladeanteil.py`, seit
2026-08-08, Fund **F-16**): die Monatszeilen werden angereichert, **bevor** irgendjemand sie zu
einer Heimladung poolt. Das ist keine Feinheit, sondern der Unterschied zwischen vier und achtzehn
Sichten: liegt die Ableitung *über* `get_emob_heimladung_canonical`, trifft sie nur die Felder
`EmobFakten.ladung_pv_kwh`/`ladung_netz_kwh` — jede Sicht, die die mitgereichten Rohzeilen selbst
poolt (Cockpit → Jahr, Jahresbericht-PDF) oder `InvestitionMonatsdaten` direkt liest
(Komponenten-Hub, Aussichten, HA-Export), zeigt daneben weiter 0 %. Sichten der zweiten Gruppe
holen dieselbe Anreicherung über `reichere_monatszeilen_an`.

**Zwei Ausnahmen, beide bewusst:**

- Der **Community-Payload** liest `eauto_summe_gemessen`/`wallbox_summe_gemessen` — der Server hat
  die Rohdaten nie gesehen und rechnet nichts nach; eine Schätzung wäre in einem Benchmark nicht
  mehr als solche erkennbar (dieselbe Linie wie beim BKW-Eigenverbrauch).
- **Schreib-, Import- und Checker-Pfade** bleiben außen vor. Die Anreicherung geschieht zur
  **Lesezeit** auf Kopien; programmatisch in `verbrauch_daten` zu schreiben bleibt verboten.

**Die Prognose-Achse rechnet mit derselben Zahl** (N-188, seit 2026-08-08): fehlt am Fahrzeug der
gepflegte `pv_ladeanteil_prozent`, nimmt die ROI-Prognose den IST-Anteil über
`monats_fakten.ist_pv_ladeanteil_prozent` (Σ PV ÷ Σ Ladung, ladungsgewichtet) statt des früheren
Vorgabewerts von 60 %. Der Default greift nur noch, wenn auch das IST keine Heimladung kennt.
**Seit 27.09.2026 (N-572) belegt das Formular das Feld nicht mehr mit 60 vor:** ein geleertes Feld
bleibt beim nächsten Speichern leer, und es gilt der IST-Anteil. Vorher schrieb jedes Speichern die
60 als gepflegten Wert zurück, und der IST-Anteil kam an formular-gespeicherten Fahrzeugen nie zum
Zug. Eine früher gespeicherte 60 bleibt stehen — eedc kann sie nicht von einer Eingabe
unterscheiden; wer den gemessenen Anteil will, leert das Feld. Die
zweite Prognose-Quelle (`aussichten/finanz_prognose.py`, leitet ihre Quote aus der Historie ab) zieht über dieselbe
Anreicherung mit.

**Herkunft:** `EmobFakten.ladung_anteil_abgeleitet` sagt, ob die Aufteilung gerechnet ist; auf der
Tagesebene trägt `source_provenance` die Marke `einspeise_deckung` bzw.
`einspeise_deckung_teilweise` (letztere, wenn nicht jede Ladestunde auswertbar war — dann ist der
Wert eine Teilsumme, P4).

**Vermessen gegen evcc** (2026-08-08, Anlage 1, Feb–Aug 2026, 963 kWh Heimladung, Referenz
`sensor.evcc_helper_pv/net_charged_kwh`):

| Regel | PV-Anteil | Abweichung zu evcc (67,9 %) |
| --- | --- | --- |
| netzbasiert `min(Ladung, Netzbezug)` | 73,8 % | +5,9 pp |
| netz + Speicherentladung | 60,8 % | −7,2 pp |
| Einspeise-Deckung (bis v4.0.50, mit Speicherabzug) | 64,7 % | −3,2 pp |

**Nachgemessen 2026-09-27** (N-569, Lab-Kopie des Recorders, evcc-Solar-%): 15 Ladevorgänge Juni–August
2026 — mit Speicherabzug 76,0 %, **ohne (gebaut ab v4.0.51) 94,5 %**, evcc 93,5 %; anlagenweit Mai–September
79,4 → 92,6 %. Feb–Aug ist dort nicht neu messbar; die Zeiträume stehen getrennt. Im Sommer lädt das Auto
oft aus dem Hausakku — den Fall sah die Messung vom 08.08. kaum.

⚠ **Keine rückwirkende Berechnung.** Der Wert entsteht beim Aggregieren eines Tages; Zeiträume vor
diesem Feature tragen `NULL`, und `NULL` heißt „keine Aussage", nicht „keine Sonne".

> **E-Mobilität und Sonstiges aus Zeitraum-Differenzen (HA-Bauform E4c, Stand 06.10.2026).** Mit Home Assistant (bzw.
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
>   HA-Export) diesen Anteil; sonst die Quote der Tagesebene wie bisher. Angewandt wird er wie bisher auf die Ladung der
>   Zeilen ohne eigene Aufteilung (Punkt 3).
> * **Die Lademengen eines Monats ohne Abschluss** kommen aus den Kanälen der E-Mob-Gruppe (je Gerät jedes Energiefeld
>   mit Zähler — die Felder, die ein Abschluss schriebe) und laufen durch dieselbe Faltung und dieselbe eine Funktion wie
>   eine gespeicherte Monatszeile: Wallbox-Regel, Pool, Rest nach km, Dienstwagen getrennt. Ein Monat mit Zeile behält
>   sie (gespeichert schlägt gerechnet).
> * **Quellenwahl je Monat und Gruppe**, getrennt von der Bilanz-Gruppe: `kanal` nur, wenn jeder Kanal der Gruppe
>   (auch der abgeleitete) den Monat voll deckt — sonst rechnet der Monat wie bisher.
> * **Grenze — eine Stunde ohne Aussage** (fehlende Netzbezugs- oder Einspeisezeile, Zählerlücke über mehr als eine
>   Stunde) trägt im Kanal keinen PV-Teil — ihre Ladung zählt im Anteil zum Netz. Die Tagesebene ließ eine solche Stunde
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

⚠ **Die Auflösung begrenzt die Genauigkeit.** Meldet ein Wallbox-Zähler nur ganze Kilowattstunden
(an der Referenzanlage 218 von 218 Stunden-Deltas ganzzahlig), trifft keine Rechnung die einzelne
Stunde — über den Monat ist die Ableitung brauchbar, über die Stunde nicht.

> ⚠ **Korrektur (2026-08-08):** hier stand bis dahin „Offen: die Prognose zieht noch nicht mit
> (N-188)". Das ist seit demselben Tag erledigt und vier Absätze weiter oben beschrieben — der Satz
> stammte aus dem Paket davor und ist beim Nachziehen stehen geblieben. Ein Dokument, das an zwei
> Stellen dasselbe verschieden behauptet, ist schlechter als eines, das schweigt.

#### Welcher Strompreis die Ladung bewertet (F-18 · ADR-002/P8)

Die Netzladung eines E-Autos wird mit dem Tarif bewertet, der **im jeweiligen Monat galt** — nicht
mit dem heutigen. SoT ist `services/eauto_wirtschaftlichkeit.aufgeloester_strompreis_cent`, gerufen
aus `berechne_eauto_ersparnis_periode`.

Bis 2026-08-08 löste jede Sicht diese eine Größe selbst auf, und zwar auf **vier** Arten:

| Sicht | vorher | jetzt |
| --- | --- | --- |
| Cockpit → Jahr | heutiger Wallbox-Tarif | Monatstarif inkl. Flex-Ø |
| HA-Export (Anlagen-Sensoren) | heutiger **allgemeiner** Tarif | Monats-Wallbox-Tarif |
| HA-Export (Fahrzeug-Sensor) | heutiger **allgemeiner** Tarif | Monats-Wallbox-Tarif |
| Komponenten-Hub | mengengewichteter Monats-Ø | unverändert (jetzt über den SoT) |
| Auswertungen → Aussichten | Monatstarif, aber **allgemein** | Monats-Wallbox-Tarif inkl. Flex-Ø |

**Gewichtet wird nach der Netzladung je Monat**, nicht nach Kilometern: der Preis bepreist
Kilowattstunden. Nur wo eine Monatsaufteilung der Netzladung nicht existiert — bei reinem PV-Laden
— fällt die Mittelung auf die km zurück, den Schlüssel, nach dem der Wallbox-Pool ohnehin
attribuiert.

> ⚠ **Für eine Anlage ohne Tarifwechsel bewegt sich nichts.** Der mengengewichtete Ø eines
> einzigen Tarifs *ist* dieser Tarif. Wer den Tarif gewechselt hat, sieht dagegen vier
> HA-Sensoren einmalig springen (`e_auto_ersparnis_vs_benzin_euro`, `netto_ertrag_euro`,
> `roi_prozent`, `amortisation_jahre`) — an einer vermessenen Anlage um −41,10 €.

> ⚠ **Der P8-Wächter deckt diese Fläche nicht ab.** Alle vier beteiligten Dateien stehen in
> `P8_BASELINE_AUSNAHMEN`, weil sie den heutigen Tarif für die Hochrechnung nach vorn auch
> brauchen. Gesichert wird die Preisachse deshalb durch einen eigenen Wächter
> (`test_wurzelmuster_konformitaet.py::test_p8_emob_ersparnis_bekommt_die_monatspreise`, baumweit)
> und den Sichten-Vergleich `test_emob_preisachse_sichten_symmetrie.py`.

#### Wo die Wallbox die Quelle ist (F-14 · N-196)

Trägt eine Wallbox die Ladeenergie, ist **sie** die Quelle — auch ohne gesetzte Zuordnung
(`parent_investition_id`). Diese Regel gilt seit 2026-08-08 in allen drei Pfaden:

| Pfad | Ort |
| --- | --- |
| Monatsebene | `eauto_wirtschaftlichkeit.get_emob_heimladung_canonical` |
| Tages-**Leistungs**pfad | `services/live_sensor_config.py` (#356) |
| Tages-**Zähler**pfad | `snapshot/komponenten_beitraege.wallbox_deckt_ladung_ab` |

Vorher kannte der Zählerpfad nur die Zuordnung; ein E-Auto mit eigenem kWh-Zähler **ohne** Parent
lief an ihr vorbei, und derselbe Ladevorgang stand zweimal im Tagesverlauf. Bereits gespeicherte
Tage bleiben davon unberührt — dafür meldet der Daten-Checker sie (Kategorie
`emob_doppelzaehlung_tage`) und bietet „Zeitraum neu aggregieren" an. **Bewusst kein
Start-Migrationslauf:** die Heilung überschreibt Messwerte und bleibt eine Entscheidung des
Anwenders.

**Auch in der Live-Bilanz bucht die Wallbox (Cockpit → Live, N-575).** Ist eine Wallbox erfasst,
ist die Heimladung eines E-Autos Gesamtverbrauch — auch beim V2H-fähigen Auto, nie Batterie-Ladung.
Liefert die Wallbox einen Wert, bucht sie, und das Auto steht nur als ihr Kind daneben; liefert sie
gerade keinen, zählt das Auto selbst als Verbraucher. Eine gemessene V2H-**Entladung** zählt wie
eine Speicher-Entladung zum Eigenverbrauch, und zwar einmal: Meldet die Wallbox den negativen Wert,
ist **sie** die Quelle und das Auto zeigt nur seine Richtung; misst nur das Auto, bucht das Auto.
Ohne erfasste Wallbox bleibt das V2H-Auto ein Speicher am Hausanschluss (F-69). Vorzeichentreu
liest eedc die Wallbox nur, wenn ein V2H-fähiges Auto erfasst ist — sonst weiter den Betrag. Ein
invertiert angeschlossener Wallbox-Sensor im V2H-Haushalt gehört deshalb über „Vorzeichen umkehren
(⇅)" an seiner Datenquelle korrigiert. Ort: `services/live_komponenten_builder.py`, Proben
`test_n575_v2h_hinter_wallbox.py`.

### 3.5 Wärmepumpe-Einsparung

**Funktion:** `berechne_waermepumpe_einsparung()` in `core/calculations.py`
**Verwendet in:** ROI-Dashboard (`investitionen.py`)

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
>             + gemessene Betriebsart-Teilmengen          , sonst — oder wenn der
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
> ⛔ **Bis zum 14.09.2026 galt eine erste Stufe davor:** War die feine Aufteilung vollständig,
> wurde der Gesamtzähler verworfen — *„sonst zählte derselbe Strom zweimal"*. Der Satz stimmte für
> die Doppelzählung und war für die Menge falsch; was der Gesamtzähler **mehr** misst, fiel aus
> Strom, Kosten, CO₂ und Arbeitszahl-Nenner heraus (gemessen an einer realen Anlage: 145 von
> 2193 kWh im Jahr). *Doppelzählung entsteht beim **Addieren**, nicht beim **Ersetzen**.*

> #### Die gemessene Wärme eines Geräts — **Gesamtwert vor Summanden** (Regel D1)
>
> **SoT:** `core/berechnungen/waermepumpe_kennzahl.py::waerme_gesamt_kwh`. Jede Sicht, die eine
> Wärmemenge auswertet, bekommt sie von dort — Monats-Fakten, Komponenten-Hub, HA-Export,
> Community-Payload, der Tag, die anlagenweiten Alternativkosten
> (`core/berechnungen/alternativkosten.py` ⇒ Aussichten · ROI · Jahres-Ersparnis des HA-Exports),
> die thermische Gewichtung der WP-Prognose (`api/routes/aussichten/finanz_prognose.py`), die Komponenten-Zeile
> „Ersparnis vs. Alternative“ in *Cockpit → Monat* und die Nicht-DB-Quellen des laufenden Monats
> (MQTT · Connector · HA-Statistik).
>
> ```
> Wärme_kWh = waerme_kwh            , wenn gepflegt        (EIN gemeinsamer Wärmemengenzähler)
>           = heizenergie_kwh + warmwasser_kwh, sonst      (getrennte Zähler)
> ```
>
> ⚠ **Die vier zuletzt genannten standen bis zum 14.09.2026 nicht in dieser Liste — und lasen die
> Regel auch nicht** (N-391c). An einem Gerät mit gemeinsamem Wärmemengenzähler war die thermische
> Menge dort 0; die Jahresformel lieferte damit **−300 € statt 33,33 €** (der WP-Strom wurde weiter
> belastet, die Gas-Ersparnis daneben fiel weg), die Zeile in *Cockpit → Monat* entstand gar nicht,
> und der laufende Monat zeigte keine Wärme. **Diese Liste ist deshalb Teil der Regel, nicht ihre
> Illustration:** Wer eine Wärmemenge liest, steht hier — oder er liest falsch.
>
> ⛔ **`waerme_kwh` ist nie ein dritter Summand.** Wer Gesamtzähler **und** Aufteilung pflegt, zählte
> sonst 3000 + 2100 + 900. Und die Regel fällt **je Gerät vor** dem Summieren: auf Anlagensummen
> angewandt verschwände die Aufteilung des zweiten Geräts hinter dem Gesamtwert des ersten
> (N-391b, ADR-002/P4).
>
> **Warum der Gesamtwert gewinnt (K1):** Die Gesamtmenge ist die Messung; jede Aufteilung steht
> daneben, nie an ihrer Stelle. ⚠ **Bewusst die Gegenrichtung zur Stromseite** (`wp_strom_stufe`):
> Dort gewinnt die vollständige feine Aufteilung, weil das Kennzeichen *Getrennte Strommessung*
> erklärt, dass die zwei Zähler zusammen das Ganze sind. Auf der Wärmeseite gibt es keine solche
> Erklärung.
>
> **Folge für die Kennzahlen je Funktion (N-391, 14.09.2026):** Trägt `waerme_kwh` die Wärme, gibt
> es für die Funktionen ohne eigenen Wärmewert **keine** Arbeitszahl, sondern den Grund
> *„Wärme nicht je Funktion gemessen"*. Vorher landete ein gemeinsamer Zähler mangels Feld unter
> *Heizwärme*, und bei getrennter Strommessung entstand daraus `Gesamtwärme ÷ Heizstrom` — gemessen
> 5,0 statt 3,0. Wer Gesamtwert **und** Aufteilung pflegt, behält seine Funktions-Zahlen: sie sind
> gemessen und tragen dieselbe Abgrenzung.

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
> **Hier stand bis zum 13.09.2026 ein `Netz_Anteil = 1 − pv_anteil_prozent/100`** in
> **beiden** Formeln, Kosten wie CO₂. Er ist ersatzlos entfallen, und mit ihm die
> versteckte 50-%-Konstante `WP_PV_ANTEIL_DEFAULT`, die dieselbe Größe an zwei weiteren
> Stellen anders bildete.
>
> **Der Grund ist keine Vereinfachung, sondern ADR-002/P9:** Der PV-Strom, den die
> Wärmepumpe verbraucht, ist auf der **PV-Seite** bereits gutgeschrieben — im Geld als
> **Eigenverbrauch** (er wird dort mit dem Netzbezugspreis bewertet), im CO₂ als
> **vermiedener Netzstrom**. Ihn in der Wärmepumpen-Rechnung ein zweites Mal abzuziehen,
> zählte dieselbe Kilowattstunde doppelt. Am Zahlenbeispiel: PV 1.000 kWh, davon 300 kWh
> in die Wärmepumpe, Rest eingespeist, Netz 30 ct, Einspeisung 8 ct, Gas-Alternative
> 500 €. Wahr sind 556 € Jahresnutzen; mit PV-Abschlag wies eedc 646 € aus.
>
> Das Feld **„PV-Anteil (%)"** am Gerät bleibt und beantwortet eine **Mengenfrage**
> („wie viel des WP-Stroms kam aus der eigenen Anlage?"). Es speist genau zwei Stellen:
> den Eigenverbrauchs-Fallback der Prognose und die Zuordnung des Eigenverbrauchs auf das
> einzelne Gerät. Es beantwortet **keine Preisfrage**.
>
> Damit rechnen alle vier Ersparnis-Pfade derselben Wärmepumpe nach **einer** Regel:
> Monats-Layer (`services/wp_wirtschaftlichkeit.py` — Komponenten-Hub, *Cockpit → Monat/
> Jahr*, HA-Sensor je Gerät), anlagenweite Alternativkosten
> (`core/berechnungen/alternativkosten.py`), die Jahresformel der Prognose
> (`api/routes/aussichten/finanz_prognose.py`) und diese Planungsformel hier. Die CO₂-Zeile trifft sich
> dabei mit dem gemessenen Pfad `co2_wp_ersparnis_kg`, der schon immer den vollen Strom
> belastete (ADR-001/DI-1).

> **Wirkungsgrad der Altanlage (η_alt):** `Gesamtwärmebedarf` ist **abgegebene Wärme**, nicht Brennstoff — das Eingabefeld heißt „Heizwärmebedarf (kWh/Jahr) — aus Energieausweis", und derselbe Wert wird oben durch die JAZ geteilt (JAZ = Wärme/Strom). Ein Kessel muss dafür `Wärme / η` verfeuern; `Alter_Preis` ist der Preis je kWh **Brennstoff** (so steht er auf der Rechnung). Die Umrechnung macht der Layer-SoT `gas_kosten_altanlage`, die η-Wahl der Resolver `alter_wirkungsgrad` — beide in `core/berechnungen/alternativkosten.py`.
>
> Bis v4.0.1 fehlte die η-Rückrechnung in diesem Pfad: die ROI-Seite wies für dieselbe Wärmepumpe eine niedrigere Ersparnis (und CO₂-Einsparung) aus als Aussichten, HA-Export und WP-Dashboard, die alle über `gas_kosten_altanlage` laufen. **Die fixen Zusatzkosten werden nicht durch η geteilt** — sie sind keine Energie.
>
> **Strom-Direktheizung:** η = 1,0. Eine Widerstandsheizung (Nachtspeicher, Infrarot) setzt Strom verlustfrei in Wärme um; ihr einen Kesselverlust anzurechnen, würde die WP-Ersparnis überhöhen. Die η-Wahl lag vorher an vier Stellen dupliziert vor und kannte diesen Fall nirgends.

> **Diese Rechnung braucht zwei gepflegte Angaben — sonst läuft sie nicht.** ⚠ **Bis 2026-08-16 stand hier das Gegenteil:** „Split-Klimaanlagen (`wp_art = luft_luft`) durchlaufen diese Rechnung gar nicht … ein Luft-Luft-Gerät ersetzt in aller Regel keine Heizung." **Diese Prämisse ist gefallen** — eine Luft-Luft-Wärmepumpe kann sehr wohl eine Gasheizung ersetzen, und viele Anwender heizen damit. Der echte Defekt war nie die Bauart, sondern eine **erfundene Eingabe**: Weil `Heizwärmebedarf`/`Warmwasserbedarf` Defaults hatten (12.000/3.000 kWh), kam die Formel nie ohne Ergebnis heraus — bei den übrigen Standardwerten rund **1.100 €/Jahr** und **2.210 kg CO₂/Jahr** Ersparnis gegen eine Gasheizung, die es nie gab, inklusive Beitrag zu den Anlagen-Summen. **Heute gilt stattdessen:** (1) Ist beim **ersetzten Energieträger** „Nichts ersetzt (Neubau)" gewählt, wird **weder Ersparnis noch CO₂-Ersparnis** konstruiert — für **jede** Wärmepumpenart, nicht nur für Klimaanlagen; das war der Neubau-Fall, der bis dahin still eine Gaskessel-Ersparnis bekam. (2) Ist **kein Wärmebedarf gepflegt**, gibt es keinen Default mehr; die ROI-Zeile trägt „—" und `nicht_bewertet` samt Begründung. Eine halb gepflegte Angabe zählt entsprechend halb (nur Warmwasser gepflegt ⇒ Heizwärme 0). (3) **Bestandsschutz ohne Migration:** Steht an einer Luft-Luft-WP noch **exakt** die alte Vorbelegung 12.000/3.000, zählt sie als offene Frage statt als Antwort — sie war seit v4.0.6 unsichtbar und damit nicht korrigierbar. Bei klassischen Wärmepumpen bleibt sie eine Schätzung und wird gerechnet. Die **gemessenen** Pfade (`services/wp_wirtschaftlichkeit.py`, `co2_wp_ersparnis_kg`, Aussichten, JAZ/COP) haben zusätzlich weiterhin ihren `wp_waerme_kwh <= 0`-Wächter. (4) **Eine Achse, die es am Gerät nicht gibt, geht mit 0 ein** (14.09.2026, WK-15c): Eine **Brauchwasser**-Wärmepumpe gibt keine Heizwärme ab, eine **Split-Klimaanlage** hat keinen Warmwasserkreis (N-304) — der jeweils andere Bedarf wird vor der Formel auf 0 gesetzt, auch wenn eine Zahl im Feld steht. Gemessen an einer Brauchwasser-WP mit der Formular-Vorbelegung: **714,29 €/Jahr und 1.721 kg CO₂** gegenüber **142,86 € und 344 kg** — 571 € Ersparnis für Wärme, die das Gerät nie liefert. Steht auf den geltenden Achsen **nur** die Vorbelegung, greift (3); steht dort gar nichts, greift (2). SoT der Unterscheidung: `core/berechnungen/alternativkosten.py::ersetzt_keine_heizung` für (1) und `field_definitions/bedingungen.py::feld_urteil` für (3) und (4) — **die Registry entscheidet je Achse, nicht die Bauart** (ADR-002/P13). Die Layer-Formel `berechne_waermepumpe_einsparung` bleibt davon unberührt: Sie rechnet, was der Aufrufer ihr gibt.

> ⚠ **Punkt (1) galt bis 2026-08-29 nur je Gerät, nicht in den anlagenweiten Sichten** — und der häufigste Fall fiel genau durch diese Lücke. Wer neben einer Wärmepumpe, die eine Gasheizung ersetzt hat, eine **Split-Klimaanlage** betreibt (in eedc ebenfalls eine Wärmepumpe, meist mit „Nichts ersetzt (Neubau)"), bekam auch deren Wärme als vermiedenes Gas gutgeschrieben: Die Sperre griff erst, wenn **keine einzige** Wärmepumpe etwas ersetzt hatte. Betroffen waren die **CO₂-Ersparnis im Jahresbericht** — bei zwei gleich großen Geräten war sie **doppelt so hoch** (2.458 statt 1.229 kg/Jahr, an einer nachgestellten Anlage gemessen) — und die **Alternativkosten-Ersparnis in der Jahresprognose** unter *Auswertungen → Aussichten*, dort mit umgekehrtem Vorzeichen: Der Strom des Neubau-Geräts wurde von der Ersparnis der ersetzenden Wärmepumpe abgezogen (1.057 → 704 €/Jahr, ebenfalls nachgestellt).
>
> **Heute gilt Punkt (1) überall.** Der fossile Vergleich rechnet auf beiden Seiten mit **den Geräten, die etwas ersetzt haben** — dieselbe Grundmenge im Zähler wie im Abzug. Die Mengen der Anlage (Stromverbrauch, gelieferte Wärme) bleiben davon unberührt; kleiner wird allein die **Grundmenge des Vergleichs**. SoT sind die Teilmengen `WpFakten.waerme_mit_ersatz_kwh` / `strom_mit_ersatz_kwh` aus der Monats-Fakten-Schicht (ADR-002/P10).
>
> ⭐ **Warum Teilsummen und keine Sperre.** Die *Arbeitszahl* wird bei gemischten Bauarten gesperrt, weil ein Quotient über zwei Maßstäbe keine Aussage hat. Eine *CO₂-Menge* dagegen ist additiv — für sie genügt die Teilsumme. **Kennzahlen trennen wir je Bauart, Mengen summieren wir.**


> **Alternativ-Zusatzkosten (v3.21.0, #141):** `alternativ_zusatzkosten_jahr` (€/Jahr) deckt laufende Fixkosten der Alt-Heizung (Schornsteinfeger, Wartung, Gaszähler-Grundpreis) ab. Wird in **fünf** Berechnungs-Pfaden berücksichtigt: Aussichten historisch + Prognose, HA-Sensor-Export inkl. WP-Sensor, PDF-Jahresbericht, Investitions-Vorschau. In historischen Aggregaten anteilig pro erfasstem Monat (`alternativ_zusatzkosten_jahr / 12`). **Seit 05.09.2026 auch im Monats-Layer** (`berechne_wp_ersparnis`: Komponenten-Hub, Cockpit → Monat/Jahr, Vorjahresvergleich, Komponenten-Zeitreihe) — bis dahin wiesen diese Sichten für dieselbe Wärmepumpe eine um die anteiligen Zusatzkosten niedrigere Ersparnis aus als Export und Aussichten (gemessen an einem Monat mit 120 €/Jahr: 166,67 € gegen 176,67 €).

#### Eingabefelder

| Feld | Parameter-Key | Default |
|------|--------------|---------|
| Effizienz-Modus | `effizienz_modus` | `gesamt_jaz` |
| JAZ | `jaz` | 3.5 |
| SCOP Heizung | `scop_heizung` | 4.5 |
| SCOP Warmwasser | `scop_warmwasser` | 3.2 |
| COP Heizung | `cop_heizung` | 3.9 |
| COP Warmwasser | `cop_warmwasser` | 3.0 |
| Heizwärmebedarf | `heizwaermebedarf_kwh` | **kein Default mehr** in der ROI-Rechnung; im Formular Vorbelegung 12000 — **nicht** vorbelegt, wo dem Gerät eine der beiden Wärme-Achsen fehlt (`luft_luft` seit 2026-08-16, `brauchwasser` seit 14.09.2026). Zählt nur auf einer Achse, die es am Gerät gibt, s. (4) oben |
| Warmwasserbedarf | `warmwasserbedarf_kwh` | **kein Default mehr** in der ROI-Rechnung; im Formular Vorbelegung 3000 — **nicht** vorbelegt, wo dem Gerät eine der beiden Wärme-Achsen fehlt (`luft_luft` seit 2026-08-16, `brauchwasser` seit 14.09.2026). Zählt nur auf einer Achse, die es am Gerät gibt, s. (4) oben |
| PV-Anteil | `pv_anteil_prozent` | 30, wenn nie eingetragen — im Formular **nicht vorbelegt** (N-572, 27.09.2026); ein geleertes Feld bleibt leer und nimmt das Gerät aus dem Prognose-Mittel (s. „`WP_PV_Anteil`" in §4.4) |
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
> (#399, 28.08.2026; davor ergab es `unbestimmt`, und bei einem taktenden Inverter-Gerät fiel
> damit der Großteil des Stroms in *nicht aufgeteilt*). Ohne Richtung im Modus — Automatik
> (`heat_cool`/`auto`) oder gar kein Modus — bleibt es `unbestimmt`; geraten wird nicht.

```text
je Tag d, je Gerät i:
  roh_h       = |komponenten["waermepumpe_<i>"]|          # Leistungspfad, NEGATIV gespeichert
  faktor_d    = zaehler_kwh_d / Σ_h roh_h                 # nur wenn Zählersumme vorhanden
  kwh[modus] += roh_h × faktor_d                          # Stunden OHNE Modus: nur in den Nenner

je Monat (ein Gerät):
  modus_strom_heizen_kwh  = Σ_d kwh[heizen]
  modus_strom_kuehlen_kwh = Σ_d kwh[kuehlen]
  modus_abdeckung_h       = Σ_d Stunden mit Modus-Signal
  nicht_aufgeteilt        = Bezug − heizen − kuehlen      # NIE gespeichert

anlagenweit (mehrere Geräte, gleicher Zeitraum):
  modus_strom_*_kwh       = Σ_i  je Gerät                 # Mengen: addieren
  modus_abdeckung_h       = max_i je Gerät                # Zeit: NICHT addieren
```

SoT: `core/berechnungen/modus_split.py` (rein) · `services/energie_profil/modus_split_monat.py`
(Lader) · `…/modus_split_schreiben.py` (Schreiber, Schritt 4 des Monatsabschlusses).

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
> ⭐ **Und genau deshalb nennt die Anzeige diesen Bezug seit v4.0.29 (W-17b).** Die Kachel „Strom
> verbraucht" zeigt `strom_kwh`, der Balken darunter beschreibt `modus_strom_bezug_kwh` — bei
> einem Melder 30 gegen 284 kWh. Beide Zahlen waren richtig, nur stand nirgends, dass es zwei
> verschiedene Grundmengen sind. Die Zeile „Aufgeteilte Menge" erscheint, sobald sie abweichen.

> **Eine Menge ist additiv, ein Zeitraum nicht (W-17).** `modus_abdeckung_h` wird über **Tage**
> summiert und über **Geräte** maximiert. Zwei Wärmepumpen, die dieselben 18 Stunden liefen,
> ergeben 18 Stunden Beobachtung, nicht 36 — im Tag sofort sichtbar, im Monat jahrelang plausibel.
> SoT der Regel: `core/berechnungen/modus_split.py::abdeckung_ueber_geraete`.
>
> ⚠ **Das Maximum ist eine Untergrenze der exakten Vereinigung**, die aus verdichteten Summen
> nicht mehr rekonstruierbar ist (`abdeckung_h` ist eine Anzahl, keine Stundenliste). Zwischen
> einer Zahl, die zu klein sein kann, und einer, die einen Tag mit 36 Stunden behauptet, ist die
> Wahl keine Geschmacksfrage.

> **Strom je Betriebsart aus Zeitraum-Differenzen (HA-Bauform E4d, Stand 06.10.2026).** Mit Home Assistant (bzw. der
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
>   Mitschrift; frühere Monate rechnet eedc nicht neu. Geschrieben wird eine Stunde erst, wenn die Mitschrift sie erreicht
>   hat; hört die Mitschrift auf, bleibt der Kanal stehen und der Monat rechnet wie bisher.
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

Neben der Arbeitszahl **eines Geräts** gibt es seit v4.0.45 eine zweite, anders
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
> **Nachgerechnet am Melder-Fall** (dietmar1968, 14.09.2026): AZ Heizung 3,94 ×
> 1188 kWh + AZ Warmwasser 2,84 × 843 kWh = **7075 kWh** Wärme; Gesamtstrom
> **2193 kWh**, davon **17 kWh** Klima-Kühlen ⇒ 7075 ÷ 2176 = **3,25** — genau
> die Zahl, die sein eigenes Dashboard nennt.
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
3. Sonst rechnet der Pfad wie bisher — **bitgleich** zum Stand vor WK-16h.

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
(ADR-002/**P8**): `wp_preis_cent` ist die ganze Kaskade — Wärmepumpen-Sondertarif →
allgemeiner Tarif → Zeitfenster (HT/NT, über den gemessenen Netzbezug gewichtet) →
Default, je zum **Monatsersten**. Der Tagespfad rechnet mit demselben Wert
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
> `wp_kosten_euro` und werden als `kuehl_kosten_euro` eigens ausgewiesen. Ohne diese Trennung
> gemessen: **−45,04 €** Ersparnis und **−52 kg** CO₂ für eine Klimaanlage, die im Winter geheizt
> und im Sommer gekühlt hat (nachher +2,48 € / +8,2 kg). Default 0.0 ⇒ ohne Split unverändert.
>
> ⭐ **Dieselbe Abgrenzung gilt für die Arbeitszahl — seit W-14 (26.08.2026).** Bis dahin nannte
> dieser Kasten nur Ersparnis und CO₂, und das war keine Unvollständigkeit im Text, sondern im
> Code: **Die Arbeitszahl war die einzige der drei Größen, an der niemand nachgezogen hatte.** Ein
> Gerät, das im Sommer kühlt, sah dadurch aus wie eine schlechte Heizung.
>
> ⭐ **Und sie gilt für alle Funktionen ohne bewertete Nutzenergie — seit E4 (26.08.2026).**
> `arbeitszahl(..., strom_funktionsfremd_kwh=…)` bekommt heute **Kühlen + Lüften + Entfeuchten**
> aus einer einzigen Größe: `WpFakten.modus_strom_funktionsfremd_kwh` bzw.
> `ModusStromZeile.funktionsfremd_kwh`. *Eine Größe statt drei Summanden an vier Aufrufern — die
> Aufzählung war die Bauform, an der W-14 entstanden ist.* **Abgezogen, nicht gesperrt:** die
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
> ⭐ **Die zweite und die vierte Zeile hießen bis zum 14.09.2026 „feine Achse unvollständig" bzw.
> „und vollständiger feiner Achse".** Seit WK-16d entscheidet nicht mehr die Vollständigkeit der
> Achse, sondern ob es einen Gesamtzähler gibt — er ist dann die Menge (K1), auch neben zwei
> gepflegten Achsen. Die Regel selbst ist unverändert: *abgezogen wird, was im Nenner steht.*
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
> ✅ **Der Community-Vergleich zieht mit — beide Lücken geschlossen** (13.09.2026). Hier stand bis
> dahin, dass der **Community-Server** nur den Kühlstrom kennt (Feld `wp_strom_kuehlen_kwh`) und
> deshalb zweimal abweicht: Wer *Lüften* oder *Entfeuchten* getrennt misst, sah dort eine niedrigere
> Arbeitszahl als im eigenen Cockpit, und seit Option A sah eine F5-Anlage mit **abgeleitetem** Split
> dort die höhere (der Server bildete seinen Nenner selbst als `Stromverbrauch −
> wp_strom_kuehlen_kwh`). Beides löst **ein** neues Feld: `wp_strom_funktionsfremd_abzug_kwh` trägt
> die volle Definition (Kühlen · Lüften · Entfeuchten) **und** die Bedingung, weil eedc den fertigen
> **Abzug** schickt statt einer Menge, aus der der Server einen bilden müsste.
>
> ⚠ **`wp_strom_kuehlen_kwh` bleibt unverändert die Menge** und wird weiter gesendet — sie ist die
> Auskunft über den Kühlbetrieb des Monats, und der Server wertet Mengen getrennt von Kennzahlen
> aus. Abgezogen wird sie dort nur noch, wenn das neue Feld fehlt (ältere eedc-Version).
>
> ⚠ **Wirksam wird es mit dem Server-Update**, und rückwirkend erst beim nächsten vollständigen
> Teilen: Bereits übertragene Monate tragen das Feld nicht und rechnen bis dahin wie bisher.



#### 3.5d Der Wärme-Vorschlag im Monatsabschluss: Strom derselben Funktion × JAZ, gekennzeichnet (B1, 05.09.2026)

Neben dem Modus-Split gibt es einen zweiten Weg zu einer **abgeleiteten** Wärme: der Vorschlag im
Monatsabschluss (`vorschlag_service`), der für *Heizwärme* und *Warmwasser-Wärme* `Strom × gepflegte
JAZ` anbietet (bzw. SCOP/COP je Funktion nach `effizienz_modus`). Seit B1 gilt dafür die Regel aus
`core/berechnungen/waerme_vorschlag.py` — SOLL Wärme/Klima §6, Präzisierung F2–F5:

| Feld | Basis-Strom | Sprosse | wenn nicht … |
| --- | --- | --- | --- |
| **Heizwärme** | gemessener Heizbetrieb `betriebsart_strom_heizen_kwh` | F4 | … dann `strom_heizen_kwh` (getrennte Messung, F5) |
| | | | … dann `stromverbrauch_kwh` (F2) — **nur ohne fremde Spur** in der Zeile: kein gemessener Kühl-/Lüft-/Entfeucht-Strom, keine Kältemenge, kein getrennter Warmwasser-Strom. Sonst **kein Vorschlag** |
| **Warmwasser-Wärme** | `strom_warmwasser_kwh` (getrennte Messung, F5) | F5 | ohne getrennte Strommessung **kein Vorschlag** — die Menge steckt im Heizwärme-Vorschlag (Gesamtwärme landet unter „Heizwärme", N-391) |

**Der Vorschlag trägt die Marke `jaz_vorschlag`** (`REGEL_JAZ_VORSCHLAG`, zweite Regel neben
`jaz_modus_split`): der Client meldet sie beim Übernehmen zurück (`abgeleitet_felder`), die
Provenance behält sie, und `heizwaerme_ist_abgeleitet` / `warmwasser_ist_abgeleitet` sperren die
Arbeitszahl (`wp_waerme_abgeleitet` zählt seit B1 **beide** Funktionen). Multiplizieren (Ersparnis,
CO₂) bleibt erlaubt — mit Kennzeichnung. Die Beschreibung des Vorschlags sagt es dem Anwender:
*„Geschätzt: 254 kWh (Strom Heizbetrieb) × JAZ 3,5 — keine Messung"*.

**Was das repariert (gemessen am Code vom 05.09.2026):** (1) ohne getrennte Strommessung wurden
**beide** Wärmefelder aus dem Gesamtstrom vorgeschlagen — „Lücken füllen" übernahm beide, die
Gesamtwärme stand doppelt in der Zeile; (2) an einer Klimaanlage mit Betriebsart-Zählern rechnete
der Dienst `E_gesamt × JAZ` — 254 kWh Kühlstrom wurden 889 kWh „Warmwasser" (dietmar1968, T89667
#295); (3) der übernommene Vorschlag stand als `manual:form` ohne Marke in der Zeile und galt jeder
Lesestelle als Messung. ⚠ **Die Bauart entscheidet hier nichts** (R1, ADR-002/P13): ob der
Gesamtstrom der Heizstrom ist, sagt die Beleglage der Zeile, nicht `wp_art`. Proben:
`test_waerme_vorschlag_b1.py`.
#### 3.5d Arbeitszahl je Funktion und die Arbeitszahl Kühlen (W-4 · W-5)

⛔ **Dieser Abschnitt fehlte bis zum 27.08.2026 vollständig** — beide Größen waren gebaut und in
keiner Referenz beschrieben. Aufgefallen beim Prüfauftrag „§3.5c gegen W-4/W-5 halten": Der
Kasten darüber war richtig, aber er beschreibt eine *dritte* Regel. *Ein Dokument, das niemand
gegen den Code hält, produziert beides — vergessene Arbeit und erfundene Arbeit.*

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

> **Kühlen am Tag — seit Bauschnitt 6 (11.09.2026).** Die Kältemenge eines Tages kommt aus
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

> **R2/Bauart — neu am 28.08.2026** (`GRUND_BAUARTEN_GEMISCHT`, SOLL §5): Trägt ein Block eine
> Luft-Wasser-Wärmepumpe **und** eine Luft-Luft-Split-Klimaanlage, gibt es **keine gemeinsame
> Kennzahl** — verschiedene Nutzenergie, verschiedene Vergleichsmaßstäbe. Die **Mengen** bleiben
> summiert (§5: *„Mengen dürfen nebeneinander stehen, eine gemeinsame JAZ nicht"*), und im
> Komponenten-Hub behält jedes Gerät seine eigene Zahl. ⭐ Erkannt aus den **Stammdaten**
> (`ist_luft_luft_waermepumpe`), nicht aus einer Messreihe — damit ist es nach
> `waerme_deckt_nicht_alle_geraete` die **zweite** Lage, die eedc selbst erkennt. Sie steht
> **vor** ihr in der Reihenfolge: Der allgemeinere Grund riete zu einem Wärmemengenzähler, den
> eine Split-Klimaanlage bauartbedingt nicht haben kann. **Genau daran ist W-4 entstanden:** Die Funktions-Kennzahlen
wurden an einer eigenen Stelle gerechnet und kannten die Sperren nicht. Ein Heizstab auf dem
WP-Zähler ließ die Gesamtzahl mit Begründung verschwinden, während „JAZ Heizen" unbeeindruckt
danebenstand — *dieselbe Anlage, zwei Aussagen*. Dazu stand dort eine **0**, wo „unbekannt"
gemeint war (ADR-002/P4).

> **Warum die Arbeitszahl Kühlen nicht „SEER" heißt** (Entscheid, 26.08.2026): SEER ist eine
> genormte Größe aus definierten Prüfstandsbedingungen. Was eedc bildet, ist der Quotient zweier
> Zähler über einen Zeitraum. Sie „SEER" zu nennen behauptete eine Vergleichbarkeit mit
> Datenblatt-Werten, die sie nicht hat. Anwender-Fassung:
> [Wärme & Klima §3](HANDBUCH_WAERME_KLIMA.md#3-was-eedc-bewusst-nicht-sagt).

> **Warum keine geschätzte Kältemenge:** Aus einem angenommenen Wirkungsgrad käme genau der
> Faktor zurück, mit dem gerechnet wurde — dieselbe Zirkularität, die §3.5c für die abgeleitete
> Heizwärme beschreibt, nur auf der Kälte-Achse.

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
Summe. An der Demo-Anlage im Mai 2026 gemessen: **30,1 Kd** täglich gegen **22,1 Kd** aus dem Ø, also
**−26,6 %**. Ein Monat, der nur einen gepflegten Ø trägt, bekommt deshalb keine Kd, sondern den Grund.

**Die Zahl ist eine SAISON-Größe, nie ein Monatsquotient** (Entscheid K-3): Grundlast,
Warmwasser-Beimischung und Takt-Verluste skalieren nicht mit den Heizgradtagen und dominieren den
Übergangsmonat. An derselben Maschine gemessen: November **0,531**, Mai **3,889** kWh/Kd — **Faktor
7,3**, der nichts über die Wärmepumpe aussagt; im Juni gibt es überhaupt keinen Nenner (0 Kd). Über
ein Saison-Fenster verschwindet der Effekt (Winter 25/26: 0,554 · Heizperiode 25/26: 0,592). Die
Fenster-Summe wird **neu gerechnet, nie gemittelt** (SOLL §5), und ein Monat geht nur ein, wenn er
**Heizgradtage und Heizstrom** trägt.

**Wo nichts steht, steht der Grund** (SOLL §3.3/S3): keine Temperaturreihe · Reihe jünger als die
Verbrauchshistorie (mit dem Monat ihres Beginns) · kein getrennt gemessener Heizstrom · Fenster ohne
Heizgradtage. **Eine normierte Arbeitszahl gibt es nicht** — sie ist bereits ein Quotient.

### 3.6 ROI & Amortisation

**Funktion:** `berechne_roi()` in `core/calculations.py`
**Nenner-SoT:** `core/berechnungen/kapitalrechnung.py`

> **Warum eine Zahl dort steht, wo sie steht:**
> [`docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md`](KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md).
> Dort stehen die Entscheidungen samt den **verworfenen** Alternativen und den
> Messungen, die sie verworfen haben — inklusive der häufigen Einwände mit
> Antwort. Dieses Kapitel hier nennt die Formeln, jenes die Begründung.

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
| **Jahres-Rendite** | Cockpit | Kumul. Ersparnis / Relevante Kosten * 100 | Wie viel % bereits amortisiert (kumuliert) |
| **ROI p.a.** | Auswertungen → ROI (pro Komponente) | Jahres-Einsparung / Relevante Kosten * 100 | Rendite pro Jahr |
| **Amortisations-Fortschritt** | Auswertungen → ROI (Kachel), Jahresbericht-PDF | Bisherige Erträge / Relevante Kosten * 100 | Kumulierter Fortschritt |

> **Ein Nenner für alle drei (N-137, seit 2026-08-04).** „Relevante Kosten" sind die **Mehrkosten**
> `Σ max(0, anschaffungskosten_gesamt − anschaffungskosten_alternativ)` — SoT
> `core/berechnungen/investitionskosten.py::relevante_kosten_aus_investitionen`, identisch mit der
> USt-Bemessungsgrundlage (§3.7). Vorher gab es **drei** Antworten: die ROI-Sicht rechnete ohne
> Klemmung je Position, Aussichten und Cockpit trugen eine Hybrid-Summe, deren WP-/E-Auto-Mehrkosten
> aus `parameter["alternativ_kosten_euro"]` kamen — einem Schlüssel **ohne Schreiber**, der immer auf
> die Festannahmen 8.000 € / 35.000 € zurückfiel. Gepflegt wird die Spalte
> `anschaffungskosten_alternativ`, die der Daten-Checker mit WARNING einfordert.
>
> **Ohne gepflegte Alternativkosten zählen die Vollkosten.** eedc setzt keine Annahme mehr ein; die
> Amortisation fällt dadurch für WP und E-Auto ungünstiger aus als vorher, dafür entspricht sie den
> Daten, die tatsächlich da sind. Gesichert durch `test_amortisation_nenner_symmetrie.py`
> (**Regression**, drei Sichten auf einer Fixture mit Alternativkosten ≠ Festannahme).

> **Sonstige Positionen: Zeitraum-Bilanz ↔ Kapitalrechnung (seit 2026-08-09).**
> Eine Reparatur ist zweierlei, je nach Frage — und seit 2026-08-10 gilt
> dasselbe für eine Förderung:
>
> | Frage | Sicht | Wo die Position steht |
> | --- | --- | --- |
> | „Was hat der Monat gekostet und eingebracht?" | Cockpit, Monatsbericht, Jahresbericht-PDF, CSV-Export, Sensor `netto_ertrag_euro` | **Ertragsseite** — Aufwand bzw. Ertrag des Zeitraums, unverändert |
> | „Wie lange dauert es, bis sich das rechnet?" | ROI, Amortisation, HA-Sensoren, Finanzbericht-PDF | **Kapitaleinsatz** (Nenner): Ausgabe **+**, Ertrag **−** |
>
> **Warum:** vorher wurden sonstige Ausgaben im Zähler über die Laufzeit
> **annualisiert**. Eine einmalige Reparatur von 3.000 € an einer Wärmepumpe
> (Einsparung 1.235 €/Jahr) verlängerte die Amortisation dadurch von **8,1 auf
> 42,6 Jahre**, in der Jahressicht erschien das Gerät als *nie amortisiert* —
> und die Zahl driftete jedes Folgejahr weiter, ohne dass etwas passierte. Im
> Nenner ergibt dieselbe Reparatur **10,5 Jahre**. Bei laufenden Kosten
> (Wartung) liefert die kumulative Rechnung sogar exakt dasselbe Ergebnis wie
> vorher (`K + 180n = 1235n ⇒ n = 9,5`).
>
> **Sonstige *Erträge* stehen seit 2026-08-10 im Nenner** (Bauschritt 7 —
> die Vollkostenrechnung ist damit vollständig). Eine Position im
> Monatsabschluss ist per Form **einmal** geflossen; sie zu mitteln und in
> jedes künftige Jahr zu verlängern unterstellt eine Wiederholung, die niemand
> behauptet hat (spiegelbildlich zur Ausgabenseite, seit demselben Tag). Eine
> THG-Quote oder eine Förderung **mindert deshalb das eingesetzte Kapital**,
> statt eine künftige Jahres-Ersparnis zu erhöhen. In der **Zeitraum-Bilanz**
> bleibt sie unverändert stehen — dort ist sie ein Ertrag des Zeitraums.
>
> **Warum nicht schon mit F-19:** ein *wiederkehrender* Ertrag `E` im Nenner
> ergibt `(K − E·n) ÷ Z`, eine Zahl, die jedes Jahr schrumpft und irgendwann
> negativ wird. Voraussetzung war deshalb ein **Ort für wiederkehrende
> Erträge**, und den gibt es seit demselben Tag gleich zweimal: **„Ertrag/Jahr
> (€)"** an der Investition (Wallbox/Sonstiges) und **„Einspeise-Erlös (€)"**
> bei *Sonstiges/Erzeuger*, per HA-Sensor monatsgenau befüllbar. Praktischer
> Fall: wer zwei Wechselrichter mit **verschiedenen Einspeisetarifen** betreibt
> (eedc kennt genau **einen** Einspeisesatz je Anlage), pflegt den zweiten
> Erlös dort — beide Felder sind wiederkehrend gemeint und wirken im **Zähler**.
> Die monatliche Handpflege bleibt möglich, beschreibt aber die Vergangenheit
> und mindert seither den Kapitaleinsatz; der Daten-Checker weist auf den
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
> **Und der Kapitaleinsatz ist nicht die USt-Bemessungsgrundlage.** Die bleibt
> bei den reinen Mehrkosten (§ 3 Abs. 1b UStG, [§3.7](#37-umsatzsteuer-auf-eigenverbrauch)) —
> weder eine Reparatur noch eine Förderung gehört dort hinein. Gesichert durch
> `test_kapitaleinsatz_vier_sichten_symmetrie.py` (**Regression**, vier Sichten +
> beide Seiten des Bruchs, **beide Erfassungsorte** — an der Investition und auf
> der Monatsdaten-Zeile). ⚠ Die zweite Hälfte kam erst am 2026-08-10 dazu: bis
> dahin trugen anlagenweit erfasste Ausgaben **nur** die HA-Sensoren, und die
> Fixture konnte das nicht sehen, weil sie die Position komponentengebunden
> anlegt.

> **Jede Ersparnis wird mit IHRER eigenen Laufzeit hochgerechnet.** Die
> HA-Sensoren `jahres_ersparnis_euro`, `roi_prozent` und `amortisation_jahre`
> teilten bis 2026-08-09 **alles** durch die Monatszahl der *Anlage* — auch die
> Wärmepumpen- und E-Auto-Ersparnis. Eine 2025 nachgerüstete Komponente wurde
> dadurch anteilig verdünnt, während ihre Kosten voll im Nenner standen. An
> einer vermessenen Anlage (31 Anlagenmonate, Wärmepumpe 25, zweiter Wagen
> **12**) waren dadurch mindestens **3,1 Jahre reine Verdünnung**: **26,4 statt
> höchstens 23,3 Jahre** — eine Schranke, keine Schätzung, denn kein Posten lief
> länger als 25 Monate. Jetzt bringt jeder Posten seine eigene Monatszahl mit,
> und der Sensor-Rechenweg schreibt sie aus.

**Und zwei verschiedene Amortisations-Angaben — Modell neben Messung:**

| Angabe | Wo | Grundlage |
|---|---|---|
| **Amortisationsdauer** — Jahre **und Break-Even-Jahr** | Auswertungen → ROI | **MODELL:** `Relevante Kosten ÷ prognostizierte Jahres-Einsparung`, konstant hochgerechnet. Anker des Kalenderjahres ist das **früheste Anschaffungsjahr** der Investitionen; ohne gepflegtes Anschaffungsdatum bleibt es beim Jahres-Index ohne Jahreszahl. |
| **Amortisations-Fortschritt** | Auswertungen → ROI (Kachel daneben), Jahresbericht-PDF | **MESSUNG:** die tatsächlich erzielten Netto-Erträge seit Inbetriebnahme, geteilt durch dieselben relevanten Kosten. Formel-SoT `core/berechnungen/amortisation.py`. |
| **Amortisation (Prognose)** | PDF-Finanzbericht | **Dieselbe Zahl wie *Auswertungen → ROI*** (seit 2026-08-09). Vorher rechnete das PDF `Gesamt-Anschaffung ÷ Σ einsparung_prognose_jahr` — beide Seiten trugen nicht: der Nenner war die Gesamt- statt der relevanten Kosten, und der Zähler ein Feld **ohne Schreiber** (in keinem Formular, keinem Import, keinem Update-Schema). In der Praxis stand dort deshalb „—". Seit 2026-08-10 ist das Feld als **„Ertrag/Jahr"** pflegbar (Wallbox/Sonstiges) — die Amortisation kommt trotzdem weiter aus dem ROI-Dashboard, damit alle vier Sichten dieselbe Zahl nennen. |
| **Amortisation (HA-Sensor)** | `sensor.*_amortisation_jahre` | `Kapitaleinsatz ÷ Jahres-Ersparnis`, wobei die Jahres-Ersparnis aus der **gemessenen Historie** annualisiert wird — je Posten mit seiner eigenen Laufzeit. Trägt denselben Nenner wie die drei anderen, aber einen Ist- statt Modell-Zähler; die Zahl liegt deshalb je nach Anlage über oder unter der Modell-Sicht. |

> Die beiden ersten beantworten dieselbe Frage verschieden — „laut Rechnung in 9,2 Jahren" gegen
> „4.800 € von 12.000 € sind drin". Das ist gewollt und in beiden Tooltips ausgeschrieben; Bedingung
> ist der **gemeinsame Nenner**, sonst ließen sich die Zahlen nicht ineinander überführen.

> **Die Break-Even-Kurve ist eine Kalender-Treppe (seit 2026-09-18, N-525).** Jede ROI-Zeile
> zählt ihre Mehrkosten und ihre Netto-Jahres-Einsparung ab ihrem eigenen Anschaffungsjahr (ein
> PV-System ab seiner ersten Komponente, seine Kosten je Komponente gestuft), sonstige Ausgaben
> erhöhen und sonstige Erträge mindern den Kapitaleinsatz im Jahr ihrer Buchung. Das
> **Break-Even-Jahr** ist das erste Jahr, ab dem die kumulierte Einsparung den kumulierten
> Kapitaleinsatz dauerhaft nicht mehr unterschreitet — eine spätere Anschaffung kann eine schon
> amortisierte Anlage wieder unter die Linie drücken. Formel-SoT
> `core/berechnungen/kapitalrechnung.py::amortisations_verlauf`; der Client zeichnet die Reihe.
> Die **Dauer** in Jahren bleibt Modell A (Kapitaleinsatz ÷ heutige Jahres-Einsparung); Dauer und
> Jahr fallen nur bei einer Anlage zusammen, die auf einmal gebaut wurde.
>
> *Bis dahin* stand hier: „Verteilen sich die Anschaffungen über mehrere Jahre, ist das
> ausgewiesene Amortisationsjahr optimistisch (der Anker ist die erste Anschaffung, die Kosten
> sind die Summe)." Das war die benannte Näherung, die der Kurve seit v4.0.1 unter dem Text stand
> (Radiocarbonat, T89667 #342).

> **Jede Dauer nennt ihre Annahme (seit 2026-08-10).** Der Fortschritt unterstellt
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

**SoT:** `core/berechnungen/ust_eigenverbrauch.py` (Berechnungs-Layer, ADR-001)
**Bedingung:** Nur wenn `Anlage.steuerliche_behandlung == "regelbesteuerung"`

Die Selbstkosten je kWh sind eine **Jahresgröße**. Gerechnet wird deshalb **je
Kalenderjahr** und summiert — auch wenn die Sicht einen mehrjährigen Zeitraum zeigt:

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
| `Bemessungsgrundlage` | **Mehrkosten** je Investition, geklemmt bei 0 — nicht die Vollkosten. Der volle Kaufpreis eines E-Autos gehört nicht in die Selbstkosten des PV-Stroms; maßgeblich ist, was er gegenüber der Alternative gekostet hat |
| `Betriebskosten_Jahr` | Σ(Investition.betriebskosten_jahr) |
| `Monate_j` | Monate des Jahres `j`, die im ausgewerteten Zeitraum liegen (1–12). Ein angeschnittenes Jahr trägt anteilig AfA — sonst stünden zwölf Monate Abschreibung gegen sieben Monate Ertrag |
| `PV_Erzeugung_j` | PV-Erzeugung des Jahres `j` aus den Monats-Fakten |
| `USt_Satz` | `Anlage.ust_satz_prozent` (DE: 19, AT: 20, CH: 8.1) |

**Auswirkung:** USt wird vom `Netto_Ertrag` abgezogen — Cockpit, Jahresbericht-PDF,
HA-Export, Aussichten und (seit 2026-08-04, Fund **N-22**) auch *Auswertungen →
Finanzen* + *Tabelle*. Bis dahin behauptete dieser Satz den Abzug für die
Auswertungen bereits, während der Client dort ohne ihn rechnete.

> **Je Monat verteilt (Auswertungen):** die Formel ist linear im Eigenverbrauch,
> deshalb trägt jeder Monat `EV_m × Selbstkosten_je_kWh × USt_Satz`. Der Nenner der
> Selbstkosten ist die **Jahres**-PV, damit Σ der Monatsbeträge exakt der
> Jahresbetrag bleibt. **Auf Tagesebene gibt es die Größe nicht** — Investitionssumme
> und Jahresertrag lassen sich keinem Tag zuordnen; bei Regelbesteuerung gilt daher
> Σ Tage ≠ Monat beim Netto-Ertrag (dieselbe bewusste Asymmetrie wie bei CO₂).
>
> **Historie (2026-08-04, Funde N-129/N-130):** Bis dahin standen im Baum *vier*
> Bemessungsgrundlagen nebeneinander — vier Sichten die Vollkosten, das Cockpit eine
> zusammengesetzte Summe, die als einzige `anschaffungskosten_alternativ` nicht las.
> Und die Sichten übergaben die Erzeugung ihres **gesamten Zeitraums** als
> „Jahres-Erzeugung": bei Filter „alle Jahre" stand eine mehrjährige Menge im Nenner
> gegen eine Ein-Jahres-Abschreibung, die USt fiel um den Faktor der Jahresanzahl zu
> niedrig aus. Beides ist mit dem Layer-SoT aufgelöst.
>
> ✅ **Seit 2026-09-03 geht hier nichts mehr auseinander.** Bis dahin setzten Cockpit und
> HA-Export den **Netzpunkt**-Eigenverbrauch ein (inklusive eines sonstigen Erzeugers),
> Jahresbericht, Aussichten und die Monatszeile dagegen den **Finanz**-Eigenverbrauch
> (PV allein) — bei einer Anlage mit Mini-BHKW nannten die beiden Gruppen deshalb
> verschiedene USt-Beträge. Mit der Umstellung von `finanz_zeile_eingabe` auf
> `erzeugung.hinter_zaehler_kwh` liegen **alle** auf dem Netzpunkt-Eigenverbrauch.
> Register **N-131** / **N-375**.
>
> ⚠ **Was dagegen offen bleibt** (Register **N-376**): Die Selbstkosten je kWh teilen die
> Kosten **aller** Investitionen durch die Erzeugung der **PV allein** — Zähler und Nenner
> zählen verschiedene Grundgesamtheiten.

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
> kürzen die Gesamtbilanz nicht). Erzeuger unter **„Sonstiges"** (BHKW, Windrad, Wasserkraft) erzeugen bewusst **keine**
> CO₂-Gutschrift — sie zählen in EV/Autarkie und im Geldwert (hinter dem Zähler), aber nicht als
> vermiedenes CO₂: eedc kennt weder die Emissionen eines verbrennenden Erzeugers noch den
> Vergleichsmaßstab eines emissionsfreien.

#### Äquivalente

```
Bäume          = CO2_gesamt / 20       (kg/Baum/Jahr)
Auto-km        = CO2_gesamt / 0.12     (kg/km)
Flug-km        = CO2_gesamt / 0.25     (kg/km)
```

### 3.9 PV-String SOLL-IST Vergleich

**Endpoint:** `GET /api/cockpit/pv-strings/{anlage_id}?jahr=`

#### Was eine „String"-Zeile ist — die Erzeuger-Abgrenzung (F-10)

> **Die Zeilen dieser Sicht sind PV-*Erzeuger*, nicht PV-*Module*.** Maßgeblich ist
> `PV_ERZEUGER_TYPEN` (SoT `core/berechnungen/spez_ertrag.py`) = `pv-module` **+**
> `balkonkraftwerk`. Ein Balkonkraftwerk trägt alles, was die Sicht braucht: kWp über
> `get_erzeuger_kwp` (beim BKW `leistung_wp × anzahl`), Ausrichtung und Neigung als eigene
> Formularfelder, und seit #367 ein eigenes PVGIS-SOLL.
>
> **Betroffen sind vier Ausgaben derselben Sicht** — `GET /pv-strings`,
> `GET /pv-strings-gesamtlaufzeit`, Abschnitt 10 des Jahresbericht-PDF und die beiden Leertexte
> im Client. #367 hatte nur die *zwei PVGIS*-Endpunkte erweitert und im Issue-Text „zwei
> Endpunkte" behauptet; es waren fünf. Klasse #236 — *ein Filter auf einer Schicht reicht nicht,
> wenn parallele Pfade existieren.*
>
> ⚠ **Die IST-Quelle ist je Typ eine andere, und das ist Absicht.** Ein `pv-module` holt seinen
> Wert aus `ErzeugungFakten.pv_je_modul` (P7-Auflösung); ein `balkonkraftwerk` steht dort
> **nicht**, sondern in `BkwFakten.erzeugung_je_investition`. Grund: die Σ von `pv_je_modul` ist
> `pv_module_kwh`, und die geht in die **ROI-Rechnung**, wo das Balkonkraftwerk eine **eigene**
> Zeile hat (`investitionen/roi.py::get_roi_dashboard`, innere `get_pv_erzeugung`) — läge es in beiden, zählte seine
> Erzeugung dort doppelt. Wer die Sicht erweitert, erweitert deshalb **nicht** `pv_je_modul`.
> Gewächtert in `tests/test_bkw_erzeuger_sichten_f10.py`.
>
> **PV-Module unter einem Balkonkraftwerk sind erlaubt — und zählen trotzdem nur einmal.** Seit N-266
> darf ein `pv-module` das `balkonkraftwerk` als Parent haben (`models/investition.py::ERLAUBTE_PARENT_TYPEN`)
> — der Weg, auf dem ein Balkonkraftwerk mit Modulen über Eck mehrere Ausrichtungen trägt. Hier stand
> bis 03.10.2026 noch „bleibt verboten"; das war der Stand vor N-266. Doppelt erfasst wird dadurch
> nichts: das Balkonkraftwerk **tritt** Nennleistung, Erzeugung und Ausrichtung an seine Kinder **ab**
> (Selektor `core/berechnungen/erzeuger_traeger.py`, [ADR-002/P11](ADR-002-WURZELMUSTER.md)), seine
> AC-Grenze behält es. In der String-Sicht ist es damit keine eigene Zeile mehr, seine Module sind es.
> ⚠ **Die Abtretung gilt je Monat** (N-613, N-614): Hat das Balkonkraftwerk seine Module erst später
> bekommen, trägt es in den Monaten davor Erzeugung und kWp noch selbst — es steht dann in
> *Komponenten → PV-Strings* und im Abschnitt „String-Vergleich" des Jahresbericht-PDF als eigene
> Zeile für genau diese Monate, und im Verteilungsnenner des SOLL steht in jedem Monat entweder das
> Balkonkraftwerk oder seine Module, nie beide. Welcher Weg wann passt (Balkonkraftwerk allein,
> Balkonkraftwerk + PV-Module, Wechselrichter + PV-Module), steht in
> [HANDBUCH_EINSTELLUNGEN §3.5](HANDBUCH_EINSTELLUNGEN.md#35-balkonkraftwerk-mit-mehreren-ausrichtungen--und-wann-wechselrichter--pv-module).
>
> **Dieselbe Erzeuger-Abgrenzung gilt für die Community-Stammdaten** (`services/community_service.py`):
> Neigung und Ausrichtung werden über beide Typen gemittelt — seit N-617 nur über die heute aktiven
> Erzeuger (erst `ist_aktiv_an(heute)`, dann der Selektor; ebenso Wallbox- und Balkonkraftwerk-Leistung). Vorher fiel eine reine
> Balkonkraftwerk-Anlage auf die Annahme *30° / Süd* zurück — der Community-Server rechnet nichts
> nach, die Anlage wurde also gegen die falsche Vergleichsgruppe gemessen.

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
> ⚠ **Mit #363 hebt eedc die API-Version von v5_2 auf v5_3.** Damit wechselt der Strahlungsdatensatz von
> SARAH2 auf SARAH3 — für dieselbe Anlage rund **+2 %** (am 2026-08-07 gemessen: 9,8 kWp Süd 35°,
> 10.495,79 → 10.727,57 kWh). Bestandsprognosen tragen kein `raddatabase` und werden deshalb genau
> einmal automatisch nachgezogen; danach rechnen alle Installationen auf derselben Grundlage.

> **Wann die AC-Kappung NICHT greift (F-11).** Die Grenze begrenzt, was ein Wechselrichter **ins
> Haus abgibt** — nicht, was die Module ernten. Hängt am **Träger der Grenze** ein
> **DC-gekoppelter** Speicher, läuft der Überschuss gleichstromseitig in den Akku, ohne je durch
> den Wechselrichter zu müssen; er ist dann **nicht verloren**, und eine Kappung des
> Erzeugungsprofils würde ihn wegrechnen. SoT `core/berechnungen/wr_kappung.py::_dc_speicher_traeger`.
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
> ⚠ **Damit ändert die Kopplung eines Speichers erstmals eine Zahl.** Bis v4.0.10 war
> `parameter.kopplung` (#351) rein beschreibend — sie sagte, **wo** gemessen wird, und keine
> ADR-001-Formel las sie. Ab F-11 liest `wr_kappung` sie, und die Wirkung bleibt auf **SOLL**-Werte
> beschränkt: Prognose-Kanon und PVGIS-Monatsprognose. Kein IST-Pfad, keine Energiebilanz, keine
> Finanzrechnung. Wer die Kopplung eines Speichers ändert, verschiebt seither sein SOLL.

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
Seit 04.10.2026 (N-616) gilt das auch im Abschnitt „String-Vergleich" des Jahresbericht-PDF — vorher stand dort
je String das SOLL des ganzen Jahres (im Gesamtzeitraum × Jahre) gegen die erfassten Monate. Beide Sichten
nehmen „Monat mit Wert" aus derselben Auflösung (`lade_pv_je_monat`, Quelle gemessen oder verteilt) und kürzen
den Anschaffungs-/Stilllegungsmonat mit derselben Funktion (`core/berechnungen/monatsfenster.py::soll_im_laufmonat`).
Das PDF nennt an der Zeile „n von N Monaten", wenn es weniger als der Berichtszeitraum sind. Sein spezifischer
Ertrag ist im Einzeljahr IST ÷ kWp, im Gesamtzeitraum der saisonal gewichtete Jahreswert der Cockpit-Kachel
(`core/berechnungen/spez_ertrag.py::berechne_spez_ertrag_annualisiert`), je String über seine Monate und mit seinem
Monats-SOLL als Gewicht; ohne Erzeugung oder Nennleistung steht „–".
Das IST je String kommt seit N-620 ebenfalls aus dieser Auflösung — auch für ein Balkonkraftwerk ohne eigenen Wert
in einem Monat mit Anlagenwert: es bekommt den Anteil, den `lade_pv_je_monat` ihm gibt, und ist „geschätzt
(kWp-Anteil)" gekennzeichnet. Gewichtet wird ein Balkonkraftwerk seit N-621 über `get_erzeuger_kwp` — auch wenn seine
Leistung nur in `leistung_wp × anzahl` steht (vorher 0 kWp, Anteil 0). Die Monats-Fakten teilen den Rest seit N-621
genauso (`erzeugung.bkw_aus_anlagenwert_kwh`), Σ des Abschnitts = Monatstabelle = PV-Strings.

**Der laufende Monat zählt anteilig (ab v4.0.9, N-69):**
PVGIS liefert Monatssummen — im laufenden Monat stünde diese volle Summe als Nenner über einem
angefangenen Ertrag. Die Quote maß dann das Datum statt die Anlage: am 4. August meldete eine
gesunde Anlage **19 %** SOLL-Erfüllung (264,8 IST gegen 1.387,9 SOLL), während dieselbe Anlage über
Jan–Jul auf **119 %** kam; in der Jahres-Kachel wurden daraus 104 % statt 119 %.

```
Tage      = min(heutiger Tag, Tage im Monat)   im laufenden Monat, sonst alle Tage
SOLL_kWh  = PVGIS-Monatswert × Tage ÷ Tage im Monat
```

Gekürzt wird der **Nenner**, nicht das Zeitfenster des IST (Entscheid 2026-08-04) — sonst verlöre
die Monatssicht ihre einzige Einordnung des PV-Werts bis zum Monatsabschluss. Der laufende Tag zählt
voll mit: ihn wegzulassen machte den Nenner kleiner und die Quote höher, also genau die Richtung,
aus der der Fehler kam. Innerhalb des Monats gilt Gleichverteilung; am Beispiel oben liegt die
Jahresquote damit bei 119,8 % gegen 119,2 % aus den abgeschlossenen Monaten allein.

Ein Monat in der **Zukunft** hat null Tage und damit kein SOLL — die Sichten lassen die Quote weg,
statt 0 % für einen Monat zu melden, der noch nicht stattgefunden hat. Abgeschlossene Monate und
damit die gesamte Historie bleiben unberührt.

SoT der Formel: `core/berechnungen/monatsfenster.py` (auch die Grundlast-Hochrechnung und die
Speicher-Auslastung zählen ihre Tage dort, statt jede für sich). Die Jahres-Sicht summiert die
Monatswerte und erbt die Kürzung ohne eigene Rechnung; die Oberfläche weist das Fenster aus
(„anteilig · 4 von 31 Tagen").

**Der Anschaffungsmonat zählt ebenso anteilig (ab v4.0.19, F-34):**
Dieselbe Schieflage gibt es am **anderen** Ende — nur kommt die Kante dort nicht aus dem Kalender,
sondern aus den Stammdaten. Eine Anlage, die am 19.03. ans Netz ging, bekam den **vollen**
PVGIS-März gegenübergestellt: 175,1 kWh SOLL gegen 60,8 gemessene, Performance Ratio **0,347** —
während dieselbe Anlage in jedem vollen Monat über 1,0 lag (April 1,039 · Juli 1,139). Nicht die
Anlage war schwach, der Vergleich war schief; das Jahres-PR fiel dadurch von ~1,08 auf 0,973.

```
Tage      = Tage des Monats zwischen Anschaffungs- und Stilllegungsdatum (beide inklusive)
SOLL_kWh  = PVGIS-Monatswert × Tage ÷ Tage im Monat
```

Gekürzt wird wieder der **Nenner**, aus demselben Grund. Der Stilllegungsmonat ist die
Spiegelkante und wird genauso behandelt.

> ⚠ **Zwei Datums-Ebenen, zwei Formeln — bewusst nicht zusammengelegt.**
> `monatsfenster` beantwortet *„wie viel des Monats ist am Stichtag vergangen"* (Kalender),
> `monatsfenster_investition` *„wie lange gab es dieses Gerät in diesem Monat"* (Stammdaten). Wer
> beide braucht, ruft beide und nimmt das kleinere Fenster. Das ist dieselbe Trennung, die
> [ARCHITEKTUR §4](ARCHITEKTUR.md) für `anschaffungsdatum` gegen `Anlage.installationsdatum`
> zieht — ihre Vertauschung hat schon zweimal zu Abstürzen geführt.

Die **saisonale** Zeile der Laufzeit-Sicht kürzt bewusst **nicht**: sie stellt einen IST-Durchschnitt
über mehrere Jahre einem Klimamittel gegenüber und fragt „wie fällt der Mai typischerweise aus".
Ein einzelner angebrochener Anschaffungsmonat verzerrt dort bereits den IST-Durchschnitt; beide
Seiten zu kürzen hieße, ihn doppelt zu bestrafen. Melder: Discussion #366 (azywietz-web).

**SOLL im Monatsbericht:** derselbe Grundsatz — der Monatswert kommt aus den Monatszeilen **genau der
aktiven** Prognose. Vor v4.0.1 stand dort eine Summe über *alle* aktiven Prognosen; bei einem
Bestand mit zwei aktiven war der SOLL-PV-Wert verdoppelt, und mit ihm die SOLL/IST-Abweichung und die
Grundlast-SOLL-Kachel.

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

Damit bleibt PVGIS die **einzige** Ertragsquelle; hier entsteht kein zweiter Ertragswert, nur ein
Faktor ≤ 1. Drei Jahre statt einem, weil der Faktor sonst das Wetter eines Einzeljahres trägt (am
Demo-Standort schwankt der April zwischen 0,804 und 0,875).

> **Die Grenze gehört dem Wechselrichter, nicht der Himmelsrichtung.** Mehrere Strings an einem
> Gerät teilen sich seine AC-Grenze und werden **gemeinsam** gekappt, anteilig nach ihrem
> Stundenbeitrag — auch über Orientierungsgruppen hinweg. Am Demo-Bestand (Süd 12 · Ost 5 ·
> West 3 kWp an einem 10-kW-Fronius) ist das der ganze Effekt: **je String einzeln gekappt bliebe
> das SOLL unverändert**, weil kein einzelner String allein 10 kW erreicht — gemeinsam liefern sie
> 1.227 kWh im Jahr, die das Gerät nie abgeben kann (20.812 → 19.585 kWh, −5,9 %; April −10 %,
> November/Dezember 0).

Woher die Grenze kommt (SoT `core/investition_kennwerte.get_wr_grenze_kw`, Zuordnung
`wr_kappung.zuordne_grenzen`):

| Erzeuger | Grenze | Geteilt? |
| --- | --- | --- |
| `balkonkraftwerk` | eigener Parameter `wechselrichter_leistung_w` | nein — Erzeuger und Wechselrichter sind ein Gerät |
| `pv-module` | `max_leistung_kw` des zugeordneten **Wechselrichters** (Fallback: Legacy `leistung_ac_kw`, dann die Spalte `leistung_kwp`, die dort kW AC trägt) | **ja** — alle Strings desselben Geräts |

**Ohne gepflegte Grenze wird nicht gekappt** (`None`, kein Default) und PVGIS gar nicht zusätzlich
gefragt — die Prognose bleibt dann bitgleich zu vorher. Fällt der `seriescalc`-Abruf aus, gibt es
**keine** Faktoren statt geratener: ein ungekapptes SOLL ist eine bekannte Größe, ein halb
gekapptes wäre keine.

Derselbe Layer kappt seit v4.0.4 die **Tages**-Prognose (`services/prognose_kanon.py`); seit
v4.0.9 sehen beide Pfade dieselben Grenzen und dieselbe Gruppierung.

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

##### Regel 1 gilt nur für echte Messungen (#352, seit v4.0.9)

Die Präzedenz oben liest „ein eigener Wert in der Zeile = gemessen". Das stimmt nur, solange in der
Zeile keine **gerechnete** Zahl steht — und zwei Schreibwege legen genau das dorthin: der Import
einer Legacy-Gesamtspalte (`_distribute_legacy_pv_to_modules`, aus CSV-Backup, Portal- und
Custom-Import) und der Monatsabschluss, wenn der zerlegte Vorschlag von Connector oder Cloud-Import
übernommen wird (`_mapped_or_distribute`). Beide schrieben ihre Aufteilung bis dahin mit derselben
Herkunft wie eine Gerätemessung; danach klassifizierte Regel 1 sie als `gemessen` — mit Ranking und
grünem Daten-Checker als Folge.

Seither vermerken diese Wege am Wert, dass er gerechnet ist:
`InvestitionMonatsdaten.source_provenance["verbrauch_daten.<feld>"]["abgeleitet"]` trägt
`kwp_anteil` (PV) bzw. `kapazitaet_anteil` (Speicher). SoT der Marken und ihrer Positivliste:
`services/provenance.py` (`ABGELEITET_*`, `gepruefte_ableitung`). Der Ladepfad
`services/pv_monatswerte.py` liest sie **aus derselben Zeile** — kein Join, keine zweite Abfrage —
und übergibt sie als `PvModul.eigen_ist_abgeleitet`; `resolve_pv_je_modul` liefert dafür
`QUELLE_VERTEILT` statt `QUELLE_GEMESSEN`, **ohne den Wert anzufassen**.

Drei Grenzen, alle bewusst:

- **Ein Empfänger = keine Zerlegung.** Geht der Gesamtwert an genau ein Modul bzw. einen Speicher,
  ist er unverzerrt dort und bleibt `gemessen` — dieselbe Grenze, die der Monatsabschluss für
  Beschriftung und Konfidenz schon vorher zog (`ist_verteilt`).
- **Der Client meldet die Herkunft, das Backend rät sie nicht.** Nur die Oberfläche weiß, ob der
  Anwender den zerlegten Vorschlag übernommen oder eine eigene Zahl getippt hat; sie schickt die
  Marke im Investitions-Payload als `abgeleitet_felder` mit (gleiches Muster wie `geprueft_gegen`).
  Client-SoT: `lib/erfassungZustand.ts::abgeleiteteMarke` — sie schweigt, wenn ein gleich hoher
  Vorschlag **ohne** Marke danebensteht, weil dann nicht entscheidbar ist, welcher übernommen wurde.
- **Kein Altbestand-Heilen.** Bereits gespeicherte Zeilen bleiben mehrdeutig: derselbe `writer`
  steht dort für „echte Pro-Modul-Spalte aus der CSV" *und* für „verteilt". Rückwirkend trennen geht
  nicht ([[feedback_kein_grosser_heiler_knopf]]); die Marke wirkt ab dem nächsten Schreibvorgang.

Der Daten-Checker zählt markierte Werte nicht als Messung. Damit ein vollständig importierter Monat
dadurch nicht von OK auf ERROR fällt, kennt `klassifiziere_pv_monat` den Parameter `n_abgeleitet`:
decken die gerechneten Werte den Monat ab, ist er `verteilt` (INFO) — die Zahlen sind da, sie sind
nur nicht gemessen.

> **Teil-Lücke ohne Gesamtwert (bis 04.10.2026 die benannte Ausnahme ADR-002/P2-A):** Ist nur ein
> Teil der Module gemessen und **kein** Gesamtwert hinterlegt, behält die Pro-Modul-Sicht ihre
> Messwerte, und die Anlagen-Summe trägt seit dem 04.10.2026 dieselben vorhandenen Werte —
> `Σ Strings = Σ Anlage`, gekennzeichnet als Teilsumme (`pv_vollstaendig=False`), der Daten-Checker
> nennt den Monat (Gernot: ein Modul-Ausfall kann auch korrekt sein). Bis dahin zeigte die
> Anlagen-Summe dort bewusst nichts. Die Prüfungen rechnen weiter nur mit vollständigen Monaten.

**Beim Import und beim Monatsabschluss** gilt dieselbe Rangfolge auf der *Vorschlags*-Seite: Ist ein
Connector-Feld einer Komponente zugeordnet, geht der volle Zählerstand dorthin („Vom Wechselrichter
(Zählerstand-Differenz)"); ohne Zuordnung wird nach Nennleistung verteilt und heißt dann „Gesamtwert,
anteilig nach kWp auf die Strings verteilt" — mit niedrigerer Konfidenz als jede gemessene Quelle.
Der Zuordnungs-Schritt des Import-Wizards schlägt die Anteile ebenfalls **nach Nennleistung** vor
(bzw. nach Kapazität bei Speichern); ist die Bezugsgröße nirgends gepflegt, verteilt er gleichmäßig
**und sagt dazu, dass das keine proportionale Aufteilung ist**.

#### IST je Erzeuger auf **Tagesebene** (ab v4.0.9, #350)

⛔ **Hier stand bis 2026-09-04: „Die Präzedenz oben gilt für Monatswerte. Auf der Tagesebene gibt
es sie nicht — dort wird nicht verteilt."** Mit #406 gibt es sie auch dort (Abschnitt
*Der Anlagen-Zählerstand* weiter unten). Der Unterschied liegt nicht mehr in der Regel, sondern
in ihrer **Bedingung**: verteilt wird nur, wenn ein **Anlagen-Zählerstand** vorliegt und die
Einzelzähler den Tag nicht vollständig tragen.

```
erzeuger_kwh[inv_id] = Σ komponenten_kwh[pv_<id> | bkw_<id>]      (Boundary-Rollup)
                     ∨ Σ TagesEnergieProfil.komponenten je Stunde  (Fallback, kein Rollup)
kein eigener Sensor, kein Anlagen-Zählerstand ⇒ kein Eintrag (kein 0, kein kWp-Anteil)
kein eigener Sensor, Anlagen-Zählerstand da    ⇒ kWp-Anteil am Rest, als abgeleitet markiert
```

SoT der Formel: `core/berechnungen/energie.py::erzeuger_kwh_je_investition`, ausgeliefert als
`TagWerteResponse.erzeuger_kwh` (`GET /api/energie-profil/{id}/tage-werte`). Zwei Eigenschaften
sind dabei nicht optional:

- **Der Schlüssel ist die Investitions-ID, nicht der Komponenten-Key.** Dasselbe Balkonkraftwerk
  heißt im Live-Keyspace `pv_<id>` und im Boundary-Keyspace `bkw_<id>`
  (`snapshot/komponenten_beitraege._TYP_PREFIX` gegen `live_komponenten_builder`). Je Roh-Key
  gruppiert bekäme ein Gerät zwei Spalten, deren Belegung vom Schreibpfad des jeweiligen Tages
  abhängt — dieselbe Mismatch-Klasse wie der BKW-Doppelzählungs-Bug vom 2026-05-19.
- **Eine kWp-Verteilung nur MIT Kennzeichnung — und nur je Tag.** Der Einwand dieses Absatzes
  lautete bis #406 „keine kWp-Verteilung": eine so gefüllte Tageszahl unter der Überschrift
  „Dach Süd" wäre von einer Messung nicht zu unterscheiden (die Klasse aus #352). Der Einwand galt
  der **fehlenden Kennzeichnung**, nicht der Verteilung — der Monatspfad verteilt seit jeher und
  kennzeichnet es. Genau das tut jetzt auch der Tagespfad: `source_provenance` trägt je
  `komponenten_kwh`-Sub-Key die Marke `ABGELEITET_KWP_ANTEIL`. ⚠ **Auf der Stundenebene bleibt es
  bei „keine Verteilung"** — dort trüge der kWp-Schlüssel eine Form, die die Stunde nicht hat
  (Ost und West wären um 8 Uhr formgleich). Ohne Anlagen-Zählerstand bleibt es überall bei
  „kein Eintrag": die Oberfläche nennt das Gerät und den Weg zur Zuordnung.

##### Der Anlagen-Zählerstand: Summe immer, Aufschlüsselung aufgelöst (ab 2026-09-04)

Das Feld *Anlage (Basis) → PV-Erzeugung Zählerstand (kWh)* landet über `basis["pv_gesamt"]` in
`Monatsdaten.pv_erzeugung_kwh` und ist damit **Eingang der Monats-Auflösung** (P7). Seit
2026-08-07 ist es zusätzlich ein **Snapshot-Zähler der Kategorie `pv`**
(`snapshot/keys.py::BASIS_ZAEHLER_FELDER`) und trägt damit auch Tag und Stunde — als **Summe der
ganzen Anlage**. Wer nur einen Summenzähler hat, bekommt also vollständige Tageswerte; was fehlt,
ist allein die Aufschlüsselung je Erzeuger (obenstehende Formel liefert für ihn kein `pv_<id>`).

> ⚠ **Bis dahin galt hier das Gegenteil** („erreicht die Tagesebene gar nicht"), und das war der
> Fehler F-7: eine Anlage mit einem Zähler und mehreren Ausrichtungen hatte gar keine Tages-PV.
> Der naheliegende Ausweg — alle Ausrichtungen als *eine* Investition führen — bleibt **falsch**:
> `services/pv_orientation.py` gruppiert je Investition nach (Neigung, Azimut), eine
> zusammengelegte Anlage bekäme einen systematisch falschen Tagesgang im gesamten
> Prognose-Kanon inklusive HA-Prognose-Sensoren und PVGIS-SOLL.

> ⚑ **Seit HA-Bauform E4a-2 (06.10.2026) ist der folgende Absatz die Regel des Bestandspfads** — Tage, deren
> Kanäle den Tag nicht voll decken (ohne HA-Statistik, vor dem Spiegel, Lücke). Für Kanal-Tage gilt W2 (oben):
> keine Wahl Einzel/Aggregat je Tag, kein 1-%-Kriterium, keine Skalierung gemessener Werte.

**Die Regel ist die Präzedenz je Tag (ab 2026-09-04, #406).** Sie ist die Entsprechung der
Monatsregel `resolve_pv_je_modul`, auf den Tag übertragen — SoT
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
Unterschied zur alten Regel ist *auflösen* statt *verdrängen*, nicht *addieren*.

> ⛔ **Hier stand vom 2026-08-07 bis 2026-09-04 „alles-oder-nichts":** der Anlagen-Zählerstand
> zähle nur mit, solange **kein** Erzeuger einen eigenen kWh-Zähler *trage*; ein halber Umbau
> mache die Tageswerte schlechter, und die Zuordnungs-Fläche warne davor. **Die Bedingung fragte
> die Zuordnung statt die Daten**, und daran brachen zwei Lagen: Wer Zähler zuordnet, die für die
> früheren Stunden nichts liefern, verlor deren gemessene PV (der gemeldete Fall #406 — 21 Stunden
> an einem Tag); und wer nur einen Teil seiner Erzeuger bezählte, bekam eine dauerhaft zu kleine
> Anlagensumme. Die damalige Warnung
> (`datenquellen_validierung.finde_aggregat_teilweise_verdraengt`) ist mit dem Fix **ersatzlos
> entfallen** — sie meldete einen Zustand, den es nicht mehr gibt, und den gemeldeten Fall hat sie
> ohnehin nicht erreicht (dort trugen **alle** Strings einen Zähler).

**Die Monatswerte sind in allen Lagen vollständig** — dort galt die Auflösung schon immer.

Bleibt gar kein kumulativer PV-Zähler übrig — weder je Erzeuger noch für die Anlage —, sagt die
Tagessicht das, statt zu rechnen: `TagesBilanz.pv_erfasst` trennt
„0 kWh gemessen" (Nacht, Schnee — gültig) von „nicht erfasst". Im zweiten Fall bleiben
**Erzeugung, Eigenverbrauch, spezifischer Ertrag, Performance Ratio und CO₂ leer**. Vorher stand
dort `0 − Einspeisung`, also ein **negativer Eigenverbrauch** neben einem Peak-PV-Wert aus dem
Leistungssensor (Forum kaba-kakao, T89667 #109). Regel-SoT:
[KONZEPT-UNVOLLSTAENDIGE-WERTE](KONZEPT-UNVOLLSTAENDIGE-WERTE.md) — eine Summe darf 0 bleiben,
eine Differenz mit fehlendem Summanden nicht. Die Zuordnungs-Seite und der Daten-Checker nennen
in dieser Lage den Weg über einen HA-Integral-Sensor je Erzeuger
([HANDBUCH_DATEN_CHECKER §5.2](HANDBUCH_DATEN_CHECKER.md#52-fehlende-kwh-zähler-in-der-datenquellen-zuordnung-ergänzen)).

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
Ertragsanteil und spezifischer Ertrag bleiben. Die Sicht zeigt sie seit v4.0.9 auch an — bis dahin
brach sie ohne Prognose vollständig ab und verbarg damit auch die gemessenen Werte (#350).

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
Bei `ist_dienstlich == true` (E-Auto/Wallbox) werden Ladekosten als kalkulatorischer Aufwand verbucht — seit N-633
(05.10.2026) als eigener Posten der Ergebnis-Leiter (§3.2), nicht mehr in den Sonstigen Positionen:
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
> **SoT:** `core/berechnungen/dienstliche_ladekosten.py` (ADR-001). Seit N-633 (05.10.2026) ruft ihn **eine** Stelle: die Monats-Fakten-Schicht (`services/monats_fakten/bau.py`, mit dem Tarif des Monats), Feld `EmobFakten.dienstliche_ladekosten_euro`. Daraus lesen alle Sichten — Cockpit → Monat und → Jahr, Auswertungen → Tabelle/Finanzen, Monats- und Jahresbericht als Posten der Leiter, Cockpit → Übersicht, Aussichten/Finanz-Prognose und der HA-Sensor `netto_ertrag_euro` als Abzug in ihren Sonstigen Positionen. Seit HA-Bauform E4e rechnet *Cockpit → Monat* den Posten auch für einen Monat **ohne** Monats-Fakt (laufender Monat ohne Abschluss) wie die Schicht — Mengen aus derselben Entscheidung (`entscheide_emob_heimladung`), Tarif und Bewertung über `monats_fakten.tarif_des_monats` und `dienstliche_ladekosten_euro` (im Beispiel 12,24 € → 10,44 €, gleich dem Jahresverlauf). Bis dahin riefen die letzten drei die Formel je selbst, und die ersten führten den Posten gar nicht (104,40 € gegen 122,40 €); der HA-Export zog die Kosten bis 2026-07-31 **gar nicht** ab und stand damit über der Kachel, auf die er sich bezieht. Hinweis an der Zeile (wortgleich in Backend und Oberfläche): „Strom für den Dienstwagen: Netzanteil zum Wallbox-Tarif, PV-Anteil zum Netzbezugspreis. Die Erstattung des Arbeitgebers steht unter den sonstigen Erträgen."

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
| `auto` | Bright Sky (DWD) für DE, sonst Open-Meteo best_match | variabel | Standard — maßgeblich ist seit #386 das gepflegte **Land**, nicht die Koordinaten-Box |
| `meteoswiss_icon_ch2` | MeteoSwiss ICON-CH2 | 2 km | Alpine Standorte CH/AT/IT |
| `icon_d2` | DWD ICON-D2 | 2,2 km | Deutschland (hochauflösend) |
| `icon_eu` | DWD ICON-EU | ~7 km | Europa |
| `ecmwf_ifs04` | ECMWF IFS | 0,25° | Global |

Bei einem spezifischen Modell versucht eedc zuerst dieses Modell. Schlägt der Abruf fehl oder liefert es keine Daten für den Standort, fällt es auf `best_match` zurück (Kaskade). Die verwendete Quelle pro Tag wird im Response als `datenquelle`-Kürzel (MS/D2/EU/EC/BM) mitgeliefert.

**Geltungsbereich (seit v4.0.2, A30):** Die Modellwahl wirkt auf **alle** Prognose-Pfade, weil der Prognose-Kanon (`services/prognose_kanon.py`) `Anlage.wetter_modell` an `get_solar_prognose` durchreicht — also auch auf die eedc-korrigierte Tagesprognose, die Stundenprofile, die Live-/Persistenz-Werte und den HA-/MQTT-Export (`services/ha_export_prognose.py`). Bis v4.0.1 rechnete dieser Pfad unabhängig von der Einstellung mit `best_match`, während Live-Wetter, 14-Tage-Wettertabelle und die OpenMeteo-Spalte von `/solar-prognose` das Modell bereits nutzten — dieselbe Seite zeigte damit zwei Modelle nebeneinander.

**Am Rand der Modell-Reichweite entscheidet die Abdeckung, nicht die Existenz (seit v4.0.19, F-36).**
Jedes Modell hat eine Reichweite (Spalte oben, hinterlegt in `WETTER_MODELLE`), und am **letzten
Tag innerhalb** dieser Reichweite liefert Open-Meteo häufig nur noch die Stunden bis zum Ende des
Modelllaufs. Gemessen am 2026-08-18: `icon_d2` (2 Tage) endete um **08:00** — die 15 Stunden
danach, also der gesamte Ertragszeitraum, trugen `null`. Die Kaskade holt für solche Fälle
ohnehin zusätzlich `best_match`, verwarf diesen Tag aber, sobald das gewählte Modell für ihn
**irgendetwas** geliefert hatte:

```
falsch:  Primary gewinnt, wenn der Tag in seiner Antwort VORKOMMT
richtig: Primary gewinnt, wenn er den Tag mindestens so weit ABDECKT wie best_match
```

Gezählt werden Stunden mit einem GTI-**Wert**, nicht mit Ertrag — nachts ist GTI `0.0` und damit
vorhanden; ein vollständiger Tag hat 24. **Bei Gleichstand behält das gewählte Modell den
Vorrang**, sonst nähme der Fix stillschweigend die Modellwahl weg. Deckt auch `best_match` den
Tag nur teilweise ab, bleibt er teilweise — die fehlenden Felder bleiben leer, statt zu 0 zu
werden (ADR-002/**P4**). SoT: `solar_forecast_service._gti_abdeckung_je_tag` und
`_merge_nach_abdeckung`; der Ein-Abruf-Zweig (`tage ≤ Reichweite`) holt `best_match` in diesem
Fall nach, sonst wäre die Regel dort blind.

> ⚠ **Diese Lücke war seit dem 2026-07-28 bekannt und wurde zunächst nur umgangen.** Die
> Snapshot-Begrenzung auf den Modellhorizont (`wetter/cache.snapshot_days`, Auflage E15-a) nimmt
> der Kaskade die **ganz leeren** Tage jenseits der Reichweite — den **angeschnittenen** Tag am
> Rand lässt sie stehen, denn der liegt ja im Fenster. Die Begrenzung bleibt richtig (sie spart
> Abrufe und hält den Cache-Kanon), sie ist nur nicht das, was den Fehler verhindert.

**„Keine Daten" schließt die leere Antwort ein.** Open-Meteo kann für ein Modell mit HTTP 200 antworten und trotzdem für jede Stunde `null` liefern; `_hat_nutzbares_gti` behandelt das wie einen Fehlschlag, damit die `best_match`-Kaskade greift statt einen 0-kWh-Tag zu bauen. **Am 2026-07-28 gemessen betrifft das drei der acht wählbaren Werte:** `ecmwf_ifs04` (HTTP 200, 0 von 72 Stundenwerten gesetzt — das Modell läuft nicht mehr, der Name wird noch akzeptiert) sowie `ecmwf_seamless` und `meteoswiss_seamless` (keine gültigen Modellnamen mehr, HTTP-Fehler). Für diese drei rechnet eedc faktisch mit `best_match`; die Bereinigung der Auswahlliste steht aus.

### 4.1b Solar Forecast ML (SFML)

**Endpoint:** `GET /api/aussichten/prognosen/{anlage_id}` (Prognosen-Vergleich) und `GET /api/live-wetter/{anlage_id}` (Live-Cockpit).
⛔ **NICHT** `/aussichten/kurzfristig/` — hier stand das bis 2026-08-30, und `aussichten.py` nennt SFML mit **0 Treffern** (gemessen, Melder Burkard #401).
**Service:** `services/solar_forecast_service.py`
**Externe API:** forecast.solar oder solcast.com (konfigurierbar)

SFML ist eine optionale KI-basierte Prognose-Ergänzung. Sie liefert eine zweite Tages-Prognoselinie neben der eedc-Eigenprognose und den IST-Werten — im **Prognosen-Vergleich** und im **Live-Cockpit**, nicht in der 7–14-Tage-Aussicht.

Ist SFML als Quelle gewählt, kommen seit 2026-08-30 **alle** Prognosezahlen des Live-Blocks aus SFML: Tageswert, verbleibender Ertrag, nachgeführter Tageswert und der VM/NM-Split. Wo SFML einen Tag nicht abdeckt, steht „eedc" dabei. Ohne SFML-Stundenprofil gibt es **keinen** verbleibenden Ertrag — er würde sonst aus der Kurvenform einer anderen Quelle entstehen.

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

> ⚠ **Der Skalar-Lernfaktor hier ist der LEGACY-Faktor** (`live_wetter._get_lernfaktor_detail`) und liest `pv_prognose_kwh`, also die **ungekappte** Rohprognose. Die Skalar-Stufe des **Korrekturprofils** (Stufe 4 der Kaskade) rechnet seit N-547 gegen `lern_soll_kwh`, also gegen die **gekappte** Summe.
>
> ⭐ **Seit N-551 (2026-09-23) gibt es ihn deshalb ZWEIMAL — einmal je Bezugsgröße.** Ein Faktor, der auf der rohen Prognose gelernt ist, rechnet auf einer an der Wechselrichter-Grenze **gekappten** Reihe die Abregelung ein zweites Mal heraus (an einer Messkopie mit 12-kW-Grenze: 0,809 statt 0,923, **−12,4 %**). Ein bloßer Nenner-Tausch wäre aber falsch gewesen: **fünf** Leser wenden denselben Faktor auf die **rohe** Basis an (Genauigkeits-Tracking, Prognosen-Vergleich, Energieprofil-Tages-SOLL, Tagesprognose, Kanon-Schätzpfad) — sie hätten dann um +14,2 % zu hoch gelegen. Gebaut ist daher: `faktor` bleibt Σ IST / Σ `pv_prognose_kwh`; daneben steht `faktor_gekappt` = Σ IST / Σ `lern_soll_kwh` über die Tage **derselben** Kaskadenstufe, die das Feld tragen (Gate ≥ 7 Tage, sonst kein zweiter Faktor). Den gekappten nimmt **nur** der Kanon-Fallback, also die Stelle, die auf gekappte Slots trifft. Ohne Kappung sind beide Zahlen gleich; an einer Anlage ohne AC-Grenze bewegt sich nichts.

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
- **Gebündelte Stunde (ab v4.0.51, Zählerlücken wie HA):** trägt eine IST-Stunde die Energie mehrerer realer Stunden (HA hatte davor keine Zeile), steht sie im Stundenvergleich **nicht** als Stichprobe (Slot leer, Stunde in `buendel_stunden`); ihre Energie zählt in der Tagessumme. Als unvollständig gilt der Tag nur noch bei einem **Mitternachtsbündel** der PV (Energie aus dem Vortag) oder bei verworfener PV — nicht mehr bei jeder fehlenden Stunde.

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
                  + WP_Ersparnis                                 (vs. Alternative)
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
    WP_Netzkosten = Strom * WP_Preis / 100               # der GANZE Strom (SOLL S1b)
    Ersparnis     = Gas_Kosten - WP_Netzkosten
```

> **Der ganze WP-Strom trägt den Netztarif (SOLL Wärme/Klima S1b).** Hier stand bis September 2026 ein fester Abschlag von 50 % („Netzanteil-Annahme"). Er ist ersatzlos entfallen: Der PV-Strom, den die Wärmepumpe verbraucht, ist auf der PV-Seite bereits als Eigenverbrauch gutgeschrieben — ihn hier ein zweites Mal abzuziehen zählte dieselbe Kilowattstunde doppelt (ADR-002/P9). Begründung und Zahlenbeispiel stehen im Kasten zur Planungsformel in [§3.5](#35-wärmepumpe-einsparung).

> **Monats-Gaspreis (v3.21.0):** Wenn `Monatsdaten.gaspreis_cent_kwh` pro Monat gepflegt ist, wird er Monat für Monat verwendet — ein Tarifwechsel ändert dann nicht mehr rückwirkend die ganze Historie. Ohne Eintrag bleibt es beim statischen `alter_preis_cent_kwh` der Investition. Pflege in der assistierten `MonatsdatenForm` (über `BEDINGTE_BASIS_FELDER` mit `bedingung_basis: hat_waermepumpe`) — in V4 der EINE Erfassungsweg; der frühere Monatsabschluss-Wizard ist als V4-Fläche stillgelegt und läuft nur noch über die V3-Route (bis zum Flip).
>
> **Rechenweg neben der Zahl (seit 05.09.2026):** Der Tooltip im Cockpit-Detailblock und im T-Konto zeigt den Rechenweg aus demselben Layer-Ergebnis — mit den anteiligen Zusatzkosten und dem herausgehaltenen Kühlstrom, wenn es sie gibt. Bis dahin stand dort ein Text ohne beides, der bei einer Klimaanlage 10 € ergab, während daneben 100 € standen.
>
> **Kühlstrom (Entscheid E-B, 18.08.2026; in dieser Jahresformel seit 05.09.2026):** Der Strom des Kühlbetriebs (`modus_strom_zeile`, gemessen vor abgeleitet) bleibt aus dem Vergleich — Kühlen ersetzt keine Heizung. Bis dahin kannte nur die Monatsformel (`berechne_wp_ersparnis`) die Regel; Aussichten, ROI, HA-Jahresersparnis und der Vorjahresvergleich im Cockpit rechneten den Kühlstrom weiter gegen die vermiedenen Gaskosten.

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
> bleibt leer (das Formular belegt es seit 27.09.2026, N-572, nicht mehr vor), und das Gerät fällt
> aus dem Mittel heraus. Der Beitrag **je Gerät** rechnet in diesem Fall weiter mit 30 %.
> `sqrt(PV_Faktor)` gibt der Größe ihre **Saisonform** — im Sommer steht mehr PV zur
> Verfügung —, und die `Normierung` über die **zwölf Kalendermonate** sorgt dafür, dass
> die Jahressumme trotz dieser Form genau dem gepflegten Anteil entspricht. Ohne sie
> stünde im Formular 30 % und in der Jahresbilanz 23 %.
>
> ⛔ Hier stand bis zum 13.09.2026 `WP_Strom * 0.5 * sqrt(PV_Faktor)` — der Stand **vor**
> dem 30.08.2026, als der gepflegte Anteil diese Stelle erreichte. Reine Doku-Drift; die
> Zeile darunter (`WP_Strom_Monat`) war die ganze Zeit richtig.
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

> **Die Tages- und Stundenebene rechnet mit ihren eigenen Preisen** (seit
> 2026-09-17). Ein abgerechneter Monatswert ist die Wahrheit über **den Monat**;
> er ist keine Aussage über einen einzelnen Tag. Wo Stundenpreise mitgeschrieben
> sind, bildet eedc die Tageskosten deshalb als **Summe der Stunden-Kosten**
> (Preis der Stunde × Menge der Stunde) und den Tages-Ø als deren Quotienten —
> nicht mehr als Tagesmenge × Monatspreis.
>
> Die Slot-Kaskade lautet: **gemessener Stundenpreis → abgerechneter Monats-Ø
> (über den Monat verteilt) → Vertragspreis → kein Wert.** Bei Festpreis und
> Zeitfenstern ist der Stundenpreis aus dem Vertrag *ableitbar*; dort ändert
> sich gegenüber früher keine Zahl.
>
> ⚠ **Folge:** Σ der Tageskosten kann vom abgerechneten Monatsbetrag
> **abweichen**. Das ist gewollt — die Messung sagt, *wann* das Geld angefallen
> ist, und wird nicht auf die Abrechnung skaliert. Eine große Abweichung ist
> umgekehrt ein Hinweis: entweder ist die Stundenerfassung lückenhaft oder der
> eingetragene Abrechnungswert falsch.

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

> ⚠ **Seit „Zählerlücken wie HA" (v4.0.51) gilt die Interpolation nur noch innen und nur im Zählerstands-Pfad** (Standalone/MQTT ohne HA-Statistik, `snapshot/aggregator.py`). Im HA-Pfad wird nichts aufgefüllt: die Energie einer fehlenden Stunde steht wie im HA-Energie-Dashboard in der Stunde danach (Bündel mit Spanne `n`), und der Rand am Tagesanfang wird über den letzten vorhandenen Stand davor verankert — auch in diesem Pfad, statt die erste Stunde auszulassen. Regeln und Leser: Abschnitt *Zählerlücken wie HA* weiter unten.

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

#### Tageswerte: Zähler und Bezug aus einem Fenster

Aus der Backward-Konvention folgt eine zweite Regel, die **Tages**sichten betrifft: Die Σ der 24 Slots
deckt `[Vortag 23:00, Heute 23:00)` ab — ein Tagesgesamt per Zähler-Diff dagegen `[00:00, 24:00)`.
Beide Fenster sind 24 Stunden lang und meinen **verschiedene** 24 Stunden. Wer in *einer* Zeile eine
Teilmenge (einen Zähler) über einen Bezug stellt, muss beide im **selben** Fenster erheben, sonst ist
der Anteil keine Messung, sondern eine Rechnung über zwei Tage.

Welches Fenster gilt, entscheidet die **Herkunft des Bezugs** — nicht der Gerätetyp und nicht die
Gewohnheit. Die Tabelle steht als Code in `services/snapshot/boundary_range.py`
(`TAGESFENSTER_JE_TYP` / `tagesfenster_fuer`):

| Gerätetyp | Bezug der Tageszeile | Fenster |
|---|---|---|
| Wärmepumpe | `TagesZusammenfassung.komponenten_kwh` | **bedingt**: im HA-Add-on Σ der LTS-Slots ⇒ `[Vortag 23:00, 23:00)`, im Snapshot-Pfad `[00:00, 24:00)` |
| Speicher | Σ der Ladung aus den Stundenzeilen (`batterie_kw`) | **immer** `[Vortag 23:00, 23:00)` |
| Wallbox / E-Auto | Σ der Ladeserien aus den Stundenzeilen (`komponenten`) | **immer** `[Vortag 23:00, 23:00)` |
| alles Übrige | kein Tages-Bezug hinterlegt | `[00:00, 24:00)` |

Betroffen sind die Detailwerte in *Cockpit → Tag*: die Netzladung des Speichers („davon aus dem Netz
(Arbitrage)") und die PV-/Netz-Anteile der E-Mobilität. Sie standen bis dahin in `[00:00, 24:00)`,
ihre Bezüge in den Stundenzeilen — an einem Tag mit Ladung zwischen 23 und 24 Uhr fehlte die Menge
also im einen und tauchte im anderen Tag auf. **Gemessen** an der Demo-Datenbank (187 Tage): 18 von
182 Tagen weichen um mehr als 5 % ab, am 25.11.2025 um +131,9 % (1,11 gegen 2,58 kWh). Der Client
konnte dadurch einen Netz-Anteil über 100 % errechnen — er kappte ihn stillschweigend auf 100 %.

Die Kappung bleibt (der Zähler ist eine **Brutto**-Menge, der Bezug eine **Netto**-Menge — eine
Stunde mit 2,0 kWh Netzladung und 1,5 kWh Entladung ergibt netto 0,5 kWh), aber sie ist nicht mehr
stumm: Greift sie, nennt der Formel-Tooltip der Zeile „Wirkungsverluste" den Grund
([ADR-002/P4](ADR-002-WURZELMUSTER.md)).

Monats-, Jahres- und Auswertungssichten sind **nicht** betroffen — sie rechnen aus den Monatsdaten
bzw. den Monats-Fakten und kennen kein Tagesfenster.

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
(ADR-002/P13). Keine Kühlgrenze. Beispiel (Lernwoche Ø 10 °C = 5 Kd, Heizen 7 × 1,0 kWh, Warmwasser 2,0 kWh): Tag
mit Ø 16 °C **2,7 kWh** (vorher 0,9 — der Warmwasser-Zyklus fiel auf 0,2), Tag mit Ø 0 °C **23 kWh** (vorher 27);
milde Lernwoche (0,5 Kd) bei gleichem Wetter **9,0 kWh** (vorher 9,64), danach ein Tag mit 5 °C 21,79 kWh.

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

#### Wie viele Stunden das Profil wirklich trägt

Das individuelle Profil wird ab **zwei Tagen** je Klasse (Werktag/Wochenende) verwendet — und ein
„Tag" entsteht bereits durch eine **einzige** gemessene Stunde. Zwei solcher Tage ergeben deshalb ein
Profil, dessen übrige Slots aus der Standard-Grundlast kommen. Das ist der oben beschriebene,
vorgesehene Rückfall und **kein Fehler**: Ein dünnes eigenes Profil ist besser als gar keines, und
eine schärfere Schwelle würde einer frisch eingerichteten Anlage ihr individuelles Profil wieder
wegnehmen.

Sichtbar war davon bis v4.0.37 nur die **Tageszahl** — „2 Tage" liest sich aber wie eine Aussage über
die Güte des Profils. Deshalb liefert das Ergebnis je Klasse zusätzlich die **gemessene
Slot-Abdeckung** (`slots_werktag` / `slots_wochenende`, die Route reicht sie als `profil_slots`
durch), und beide Anzeigen — die Legende in *Cockpit → Live* und der Verbrauchs-Tooltip der
3-Tage-Aussicht — nennen sie samt ihrer Folge, z. B. *„Werktag, 2 Tage, 1 von 24 Stunden gemessen —
die übrigen 23 aus der Standard-Grundlast"*. Bei voller Abdeckung entfällt der Zusatz; liefert das
Backend keine Abdeckung, bleibt es bei der Tageszahl, statt eine zu erfinden. Wortlaut-SoT beider
Anzeigen ist `lib/verbrauchsprofilHerkunft.ts`.

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

- **Stundenverbrauch** (R6) nur, wenn PV, Netzbezug und Einspeisung **dieselbe** Spanne tragen; eine fehlende Batterie zählt 0, eine Batterie mit anderer Spanne ⇒ `None`.
- **Tagesverbrauch** (R7) nach der HA-Formel über den Tag; `None` nur im Total-Fall. **Eigenverbrauch** = max(0, ΣPV − ΣEinsp − ΣLadung) + ΣEntladung (seit N-635, 05.10.2026; vorher max(0, ΣPV − ΣEinsp), s. §3.1). Eine fehlende Batterie zählt 0, `verworfen` auf der Batterie sperrt den Eigenverbrauch nicht (wie beim Gesamtverbrauch). Autarkie = (GV − Netzbezug) / GV. Unterdrückt werden EV/EV-Quote bei `verworfen` auf PV oder Einspeisung, die Autarkie bei `verworfen` auf PV, Netzbezug, Einspeisung oder Batterie.
- **Monat** (R8, `monatsbilanz_aus_tagen`): faltet Tagesbilanzen; ein Total-Fall-Tag propagiert nicht; EV mit derselben Formel aus den Summen der Tage (Rest-Abweichung an Tagen mit Netzladung, §3.1).
- **Regelmarke** (R9): `TagesZusammenfassung.verworfen` ist für jeden neu geschriebenen Tag mindestens `{}`; NULL = Altbestand, der bis zur Neuaggregation N-92 rechnet (Daten-Checker §4.6 nennt ihn).
- **Monatswert aus der HA-Statistik** (R10, `get_sensor_monatswert`): Σ der Stundenänderungen ab dem letzten Stand **vor** dem Monat, mit derselben Verwerfung (Rücksprung immer, Deckel × Fenster für PV/Einspeisung aus der Anlagen-kWp). Damit zählt die erste Stunde des Monats (N-563), und eine Lücke über die Monatsgrenze landet im Folgemonat. `intervalle` nennt die Zahl der Stützstellen-Paare hinter dem Wert; 0 heißt „eine einzige Zeile, nichts gemessen“.
- **Stundenzeilen:** jeder Slot mit Zählerwert bekommt eine Zeile, auch ohne Leistungspunkt (dort keine `komponenten`, keine Spitze).
- **Leser:** Stunde-gegen-Stunde-Auswertungen lassen Zeilen mit `spannen > 1` als Stichprobe aus; Tag-gegen-Tag-Auswertungen (Lernfaktor, Prognose-Genauigkeit, PR-Check) lassen beide Tage um ein Mitternachtsbündel mit Energie aus. Die Energie zählt in jeder Summe. Helfer: `core/berechnungen/spannen.py`.
- **Eingefrorener Stand:** Liefert HA Stunden mit unverändertem `sum` und danach den Nachtrag in einer Zeile, bleiben die Nullzeilen Nullstunden und die Menge steht in der Nachtragsstunde (n = 1, wie HA). Der Deckel rechnet dort mit dem Fenster seit der letzten Änderung — der Nachtrag bleibt Menge (Lab 24.05.2026: +37 kWh nach drei stillen Stunden). Grenze: nach einer Nacht mit echten Nullen passiert ein Sprung bis Schwelle × (Nullstunden + 1) — am Tag ab dem Anker Vortag 22:00 (Winter ≈ 150 kWh bei 10 kWp), im Monat bis zur Kappe von 24 Stunden (360 kWh); dazwischen verwirft der Tag, der Monat nimmt (benannte Asymmetrie). Der Spike-Checker (§4.7 im Daten-Checker-Handbuch) liest dieselbe Regel.
- **Daten-Checker:** Tage mit Regelmarke, an denen Σ Einspeisung > Σ PV + Σ Entladung + 0,5 kWh, erscheinen als Hinweis „Einspeisung über Erzeugung" (Entladung ins Netz ist erlaubt).
- **Benannt:** Die Live-Tageskacheln (`live_history_service`) weichen von *Cockpit → Tag* um jedes Mitternachtsbündel ab. Preise einer gebündelten Stunde: s. [KONZEPT-FLEX-TARIFE](KONZEPT-FLEX-TARIFE.md) [A-6].

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

> ⭐ **Der Nenner steht seit v4.0.39 auch in der Zeile — vorher nur in der Rechnung.** Die Aufstellung
> der Tages-Aggregate oben führt `GTI_Summe_Wh_m2` seit v3.20.0, **gespeichert wurde die Größe aber
> nie**: `aggregate_day` bildete sie, teilte durch sie und verwarf sie wieder. Angezeigt wurde
> daneben `Strahlung_Summe_Wh_m2`, also die **horizontale** Globalstrahlung — unter der Formel
> „Ertrag ÷ (Einstrahlung × kWp)", in der sie nicht vorkommt. Wer die Kennzahl nachrechnete,
> bekam damit zwangsläufig eine andere Zahl, und der Widerspruch war nicht auflösbar.
> Seit v4.0.39 trägt `TagesZusammenfassung` die Spalte `gti_summe_wh_m2`, und *Cockpit → Tag*
> nennt sie beim Namen („bei X kWh/m² auf der Modulfläche").
>
> ⚠ **Rückwärts bleibt sie leer.** Für Tage vor der Spalte steht dort `NULL` — „nicht erhoben",
> nicht 0. Die Anzeige lässt die Bezugsgröße dann weg; die horizontale Summe ersatzweise
> einzusetzen wäre derselbe Fehler mit neuem Etikett. Wer sie für ältere Tage haben will, löst in
> der Reparatur-Werkbank (*Einstellungen → Daten*) „Mehrere Tage neu aggregieren" für den
> Zeitraum aus.

> ⭐ **Der Nenner ist an den jüngsten Tagen vorläufig — und wird seit v4.0.39 nachgezogen.** Die
> Einstrahlung der letzten fünf Tage kommt vom **Forecast**-Endpunkt: das Reanalyse-Archiv (ERA5)
> hinkt der Echtzeit zwei bis fünf Tage nach. Der Forecast-Wert ist im Mittel gut (Median-Faktor
> 1,00 über 91 Tage gemessen), an **bewölkten** Tagen aber deutlich zu klein — gemessen bis Faktor
> **8,7**. Eine zu kleine Einstrahlung macht den Nenner zu klein und die PR zu groß; genau daraus
> entstand ein „PV-Doppelerfassungs"-Verdacht ohne Doppelerfassung. Seit v4.0.39 aggregiert eedc
> nachts den einen Tag neu, der die Archiv-Grenze gerade passiert hat, und ersetzt den vorläufigen
> Wert dabei durch den endgültigen. **Für die letzten fünf Tage bleibt er vorläufig** — das lässt
> sich nicht abkürzen, das Archiv hat diese Tage noch nicht.
>
> **Und der Bestand vor diesem Nachzug wird einmalig nachgeholt.** Tage, die vor dem ersten Lauf
> aggregiert wurden, trugen ihren vorläufigen Wert dauerhaft — und die Reparatur-Werkbank kann sie
> nicht heilen, weil ein Tag dort komplett neu aus der HA-Historie gebaut wird und die nur wenige
> Tage zurückreicht. Deshalb schreibt eedc für diese Tage einmalig **nur die Wetterzeile** neu
> (Temperatur, Einstrahlung, Bewölkung, Niederschlag, Wettercode und daraus die Performance Ratio);
> die gemessene Energie bleibt unangetastet. Das passiert von selbst in der Nacht nach dem Update,
> je Anlage genau einmal, bis zwei Jahre zurück. Ein Tag, den der nächtliche Nachzug wegen
> geschrumpfter HA-Historie nicht neu bauen kann, bekommt auf demselben Weg seine Wetterzeile.

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

**Geschrieben wird der Schnappschuss seit N-547 vom Prefetch-Job** (alle 45 min, erster Lauf nach Mitternacht) statt beim ersten Besuch von *Cockpit → Live*. Anlagen ohne täglichen Seitenbesuch bekamen vorher gar keins — und damit nie genug Stunden für die Stufen 1–3 der Kaskade.

#### Das Lern-SOLL des Korrekturprofils (N-547, gebaut 22.09.2026)

⛔ **Wogegen gelernt wird, ist nicht dasselbe wie das, was vorhergesagt wurde.** Bis zum 22.09.2026 las der Korrekturprofil-Aggregator sein SOLL aus `pv_prognose_stundenprofil` — der **korrigierten** Kanon-Ausgabe, also dem Produkt genau der Faktoren, die er gerade lernt. Der gepoolte Quotient `Σ IST / Σ SOLL` folgt dann der Abbildung `f ↦ r/f`, und deren Fixpunkt ist **√r, nicht r**: bei einem wahren Verhältnis r = 0,85 konvergieren die Faktoren auf 0,922 — **+8,5 % an jedem Tag**.

Zwei Felderpaare, zwei Fragen:

| Feld | Frage, die es beantwortet | Inhalt |
| --- | --- | --- |
| `pv_prognose_stundenprofil` / `pv_prognose_kwh` | *Was hat eedc vorhergesagt?* (Genauigkeit, Stratifizierung) | korrigiert + gekappt bzw. **roh** für den Tageswert |
| `lern_soll_stundenprofil_kwh` / `lern_soll_kwh` | *Wogegen darf eedc lernen?* | **roh, unkorrigiert, aber gekappt** (`KanonTag.om_stundenprofil_kwh` / `om_kwh`) |

**Warum gekappt.** Die AC-Grenze des Wechselrichters ist keine Prognoseabweichung, sondern eine physikalische Schranke: oberhalb von ihr *kann* die Anlage nicht liefern. Ein ungekapptes SOLL schriebe diesen Deckel als dauerhaften Fehler in die Mittagsfaktoren.

**Warum der Tageswert `pv_prognose_kwh` roh und UNgekappt bleibt.** Seine drei Leser (Genauigkeits-Tracking, HA-Abweichungs-Ampel, Tages-SOLL im Energieprofil) multiplizieren ihn mit dem Legacy-Lernfaktor; sie erwarten die rohe Lage. Er wurde nur von zwei Schreibern in **zwei verschiedenen** Lagen gefüllt (Prefetch roh, Live korrigiert+gekappt, „letzter gewinnt") — seit N-547 schreiben beide roh (`KanonTag.roh_kwh` = `om_kwh + abregelung_om_kwh`).

**Übergang ohne Bruch (kein Backfill).** Die neuen Felder entstehen ab dem Update; Bestandszeilen bleiben NULL. Damit der erste nächtliche Lauf nicht jeden Bin mit einem leeren Pool überschreibt, gilt je Bin: **der neue Wert ersetzt den alten erst, wenn er das Gate seiner Stufe mit NEUEN Datenpunkten erreicht** (Sonnenstand×Wetter 10 h, Sonnenstand 15 h, Stunde Σ 50 h je Monat, Skalar 7 Tage — dieselben Schwellen, die der Lookup anwendet). Beim Skalar gehören `tage_eingegangen` und `faktor_skalar` zum gehaltenen Wert, sonst fiele Stufe 4 aus. Die Marke je Bin steht in `Korrekturprofil.lern_basis_pro_bin` (`"alt"` | `"neu"`), der Beginn in `lern_umstellung_am`; nach **365 Tagen** endet die Regel (sonst bliebe ein saisonal nie wieder belegter Bin für immer auf seinem alten Wert).

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

> **Was der Monatsabschluss nachrechnet (HA-Bauform E4f, 07.10.2026).** Der Nachlauf nach dem Speichern eines Monats
> (`services/monatsabschluss_aggregator.py`) rechnet nur noch **Tage ohne Tageszeile**, und nur, solange Home Assistant
> sie im Verlauf hat — erkannt an derselben Stelle wie N-596 (die Leistungskurve trägt noch einen Wert;
> `aggregate_day(nur_mit_verlauf=True)`), kein fester Tageswert, denn die Aufbewahrung (`purge_keep_days`, Standard 10
> Tage) ist je Installation anders. **Ein vorhandener Tag wird nie neu gerechnet** — bis E4f schrieb der Nachlauf jeden
> Tag des Monats neu und damit Tage ohne HA-Verlauf mit leerer Leistungskurve (#422). Danach `rollup_month()` (oben) und
> das Festschreiben der Aufteilung nach Betriebsart (§3.5). Der einmalige Auto-Vollbackfill beim ersten Abschluss nach
> einem Upgrade ist entfallen: die Summen der Sichten kommen aus den Kanälen, Lücken der Tageszeilen füllt die
> Reparatur-Werkbank („Lücken aus HA-LTS nachfüllen") auf Knopfdruck. Ohne Home Assistant (MQTT-Zähler) gibt es keinen
> Verlauf, der verfallen könnte: ein fehlender Tag wird wie bisher aus den Zählerständen angelegt.

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
