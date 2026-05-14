
# eedc Handbuch — Daten-Checker

**Version 3.24.5** | Stand: April 2026

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen & Sensormapping](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was ist der Daten-Checker?](#1-was-ist-der-daten-checker)
2. [Severity-Logik](#2-severity-logik)
3. [Verfügbarkeit nach Installationsvariante](#3-verfuegbarkeit-nach-installationsvariante)
4. [Kategorien im Detail](#4-kategorien-im-detail)
   1. [Stammdaten](#41-stammdaten)
   2. [Strompreise](#42-strompreise)
   3. [Investitionen](#43-investitionen)
   4. [Monatsdaten – Vollständigkeit](#44-monatsdaten--vollstaendigkeit)
   5. [Monatsdaten – Plausibilität](#45-monatsdaten--plausibilitaet)
   6. [Energieprofil – Zähler-Abdeckung](#46-energieprofil--zaehler-abdeckung)
   7. [Energieprofil – Plausibilität](#47-energieprofil--plausibilitaet)
   8. [MQTT-Topic-Abdeckung](#48-mqtt-topic-abdeckung)
   9. [Sensor-Mapping – HA-Statistics](#49-sensor-mapping--ha-statistics)
5. [Behebungs-Workflows](#5-behebungs-workflows)
6. [Beziehung zu anderen Werkzeugen](#6-beziehung-zu-anderen-werkzeugen)

---

## 1. Was ist der Daten-Checker?

**Pfad:** Einstellungen → System → Daten-Checker

Der Daten-Checker prüft systematisch, ob deine Anlage so konfiguriert ist, dass alle Auswertungen verlässlich rechnen können. Er meldet fehlende Stammdaten, Plausibilitäts-Auffälligkeiten in den Monatsdaten und Drift-Probleme zwischen Sensor-Mapping und tatsächlich verfügbaren Datenquellen — jeweils mit „Beheben"-Link direkt zur betroffenen Stelle in der App.

### Aufruf

Die Prüfung läuft pro Anlage, ist nicht zeitgesteuert und liest immer den aktuellen Stand. Beim Öffnen der Seite wird automatisch geprüft; **Erneut prüfen** im Header startet die Prüfung neu (z. B. nach einer Korrektur).

### Aufbau der Ergebnisseite

- **KPI-Karten** oben: Gesamtzahl Fehler / Warnungen / Hinweise / OK über alle Kategorien.
- **Monatsdaten-Abdeckung**: Fortschrittsbalken „X von Y Monaten erfasst" ab Installationsdatum bis Vormonat.
- **Klappbare Kategorie-Sektionen**: Jede Kategorie zeigt im Header eine Sammel-Bewertung (z. B. *„2 Warnungen, 1 Hinweis"* oder *OK*) und enthält die Einzelbefunde.
- **Befund-Zeilen** mit Symbol (Severity), Meldung, optionalen Details und „Beheben"-Link zur betroffenen Seite (Sensor-Mapping, Monatsabschluss, Investitionsformular usw.).

### Wann sollte ich den Daten-Checker nutzen?

- **Nach der Erst-Einrichtung** — sofortige Rückmeldung, was zur Vollständigkeit fehlt.
- **Wenn Auswertungen leer wirken** — der Checker zeigt, ob es an fehlenden Stammdaten, Sensor-Mapping oder Monatsdaten liegt.
- **Bei Plausibilitäts-Auffälligkeiten** — z. B. wenn eine Monats-Erzeugung deutlich vom Erwartungswert abweicht.
- **Nach Anlagen-Updates** (neue Investition, Sensor-Mapping geändert, Re-Import) — er erkennt Drift.
- **Vor Community-Teilung** — Stammdaten-Vollständigkeit ist Voraussetzung für sinnvolle Vergleiche.

---

## 2. Severity-Logik

Jeder Befund hat genau eine von vier Schweregraden. Sie sind nicht zu addieren — eine WARNING wird nicht durch viele OKs aufgewogen.

| Symbol | Schweregrad | Bedeutung | Erwartete Reaktion |
|--------|-------------|-----------|-------------------|
| ❌ | **ERROR** (rot) | Kerndaten fehlen oder Werte sind logisch unmöglich (z. B. Einspeisung > PV-Erzeugung). Ohne Behebung sind die zugehörigen Auswertungen entweder leer oder produzieren falsche Ergebnisse. | Beheben, **bevor** du den Auswertungen vertraust. |
| ⚠️ | **WARNING** (amber) | Plausibilitäts-Abweichung oder fehlende Pflicht-Parameter, die einzelne Auswertungen einschränken (ROI, Heizenergie-Vergleich, kWh-basierte Korrektur-Werkzeuge). Die App rechnet trotzdem, blendet aber Bereiche aus oder rechnet mit Defaults. | Anschauen, in der Regel beheben. Manche Warnungen sind anlagenbedingt (z. B. ungewöhnlich gute Erzeugung) — dann zur Kenntnis nehmen. |
| ℹ️ | **INFO** (blau) | Hinweis auf optionale Felder oder einen Konfigurations-Aspekt, der für deinen aktuellen Anwendungsfall vielleicht nicht relevant ist. Beispiel: „Kein WP-Spezialtarif hinterlegt" — nur relevant, wenn du tatsächlich einen separaten Wärmestrom-Tarif hast. | Lesen, dann entscheiden. Keine Pflicht. |
| ✅ | **OK** (grün) | Prüfung bestanden. | Nichts zu tun. |

### Wann wechseln Severity-Stufen?

Einzelne Befunde haben über Releases hinweg ihre Stufe gewechselt. Aktuell:

- **Counter-Sensoren ohne `state_class`** wurden in v3.24.3 von INFO → WARNING hochgestuft, weil ohne `state_class` die Korrektur-Werkzeuge in der Datenverwaltung nicht greifen (vorher beruhigend als „Snapshot-Service erfasst's trotzdem" beschrieben). Siehe §4.9.
- **Kategorien werden still übersprungen**, wenn ihre technische Voraussetzung fehlt (HA-LTS nicht erreichbar, MQTT-Inbound nicht aktiviert) — du siehst dann gar keine Befunde dieser Kategorie, nicht „OK".

---

## 3. Verfügbarkeit nach Installationsvariante <a name="3-verfuegbarkeit-nach-installationsvariante"></a>

Zwei Kategorien hängen an Voraussetzungen, die je nach Installation gegeben sind oder nicht. Die anderen sieben sind variantenneutral und greifen identisch.

| # | Kategorie | HA Add-on | Standalone (Docker / native) |
|---|-----------|-----------|------------------------------|
| 1 | Stammdaten | greift | greift |
| 2 | Strompreise | greift | greift |
| 3 | Investitionen | greift | greift |
| 4 | Monatsdaten – Vollständigkeit | greift | greift |
| 5 | Monatsdaten – Plausibilität | greift | greift |
| 6 | Energieprofil – Zähler-Abdeckung | greift (Mapping zu HA-Entitäten `sensor.…`) | greift (Mapping zu MQTT-Topics) |
| 7 | Energieprofil – Plausibilität | greift | greift |
| 8 | MQTT-Topic-Abdeckung | nur wenn MQTT-Inbound aktiv | nur wenn MQTT-Inbound aktiv |
| 9 | Sensor-Mapping – HA-Statistics | greift | **wird übersprungen** (keine HA-LTS verfügbar) |

### Was bedeutet „wird übersprungen"?

- **Stiller Skip:** Die Kategorie erscheint gar nicht in der Ergebnisliste — keine Sektion, keine Meldung. So bleibt die Übersicht für Nicht-Betroffene aufgeräumt.
  - *MQTT-Topic-Abdeckung* (§4.8) bei nicht aktiviertem MQTT-Inbound.
  - *Sensor-Mapping HA-Statistics* (§4.9) wenn kein Sensor-Mapping vorhanden.
- **INFO-Skip:** Die Kategorie erscheint mit einem einzelnen INFO-Eintrag, der den Grund des Überspringens erklärt.
  - *Sensor-Mapping HA-Statistics* (§4.9) bei Standalone, weil HA-Long-Term-Statistics nicht erreichbar sind.
  - *MQTT-Topic-Abdeckung* (§4.8) wenn MQTT-Inbound aktiviert ist, der Subscriber aber nicht läuft.

### Beziehung zu Sensor-Mapping und Datenquellen

Im **HA Add-on** liefern Sensoren ihre Werte über zwei Kanäle: den aktuellen Zustand (`state`, für Live-Anzeigen) und Long-Term-Statistics (LTS, für Monatswerte und Korrektur-Werkzeuge). Kategorie 9 prüft, ob beide Kanäle für die im Mapping verwendeten Sensoren verfügbar sind.

Im **Standalone-Betrieb** kommen die Werte über MQTT (`eedc/<anlage>/…`-Topics) oder Connector-Pulls. HA-LTS gibt es nicht; dafür greift Kategorie 8, die die MQTT-Topic-Abdeckung gegen die `field_definitions.py`-Erwartung prüft. Beide Kategorien lösen dasselbe Grundproblem („Mapping passt nicht zur Realität") in der jeweiligen Welt.

---

## 4. Kategorien im Detail

### 4.1 Stammdaten

**Was wird geprüft:** Pflicht-Stammdaten der Anlage, kWp-Konsistenz zwischen Anlage und PV-Modul-Investitionen, optionale Felder für PVGIS und Community-Vergleich, sowie Performance-Ratio-Plausibilität gegenüber PVGIS (sobald genug Historie vorliegt).

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Installationsdatum nicht gesetzt** | ⚠️ WARNING | Wird zur Bestimmung des erwarteten Monatsdaten-Zeitraums benötigt. Ohne Datum kann der Checker nicht sagen, welche Monate erfasst sein sollten. | Einstellungen → Anlage → Installationsdatum eintragen. |
| **Anlagenleistung fehlt oder ist 0** | ❌ ERROR | Leistung in kWp ist Bezugsgröße für sämtliche Soll-/Ist-Vergleiche und PVGIS-Plausibilität. | Einstellungen → Anlage → Leistung in kWp eintragen. Der Wert sollte mit der Summe der PV-Modul-Investitionen übereinstimmen (siehe nächste Zeile). |
| **Keine Koordinaten hinterlegt** | ℹ️ INFO | Koordinaten werden nur für die PVGIS-Solarprognose benötigt. Ohne sie funktionieren PV-Auswertungen mit dynamischer Performance-Ratio nicht; statische Plausibilität bleibt aktiv. | Einstellungen → Anlage → Koordinaten setzen (oder „Aus Adresse ermitteln"). |
| **Kein Standort hinterlegt (Ort/PLZ)** | ℹ️ INFO | Wird für den Community-Benchmark-Vergleich nach Region benötigt. Ohne Ort/PLZ teilst du keine regionalen Vergleichswerte. | Einstellungen → Anlage → Ort oder PLZ setzen. |
| **Keine PV-Module als Investition angelegt** | ❌ ERROR | Ohne PV-Modul-Investitionen fehlen Erzeugungsdaten in der Aufschlüsselung. (Sonderfall: nur Balkonkraftwerk → INFO statt ERROR.) | Einstellungen → Investitionen → PV-Module hinzufügen. |
| **Nur Balkonkraftwerk, keine PV-Module angelegt** | ℹ️ INFO | BKW-only Setup. PVGIS-Prognose und String-Vergleich sind nicht verfügbar, alles andere funktioniert. | Keine Aktion nötig — Hinweis dokumentiert die Einschränkung. |
| **PV-Module kWp stimmt nicht mit Anlagenleistung überein** | ⚠️ WARNING | Summe `leistung_kwp` aller aktiven PV-Modul- und BKW-Investitionen weicht > 0,1 kWp von `Anlagenleistung` ab. Verfälscht alle Soll-Werte. | Entweder die Anlagen-Stammdaten an die Modulsumme anpassen, oder die Modul-Investitionen vervollständigen. |
| **PVGIS-Systemverluste ggf. zu hoch (X %)** | ℹ️ INFO | Ø Performance Ratio (IST/PVGIS) > 1,1 über mindestens 6 Monate — die Anlage produziert systematisch über der Prognose. Standardwert für Systemverluste ist 14 %. | Einstellungen → Solarprognose → Systemverluste reduzieren (z. B. 10 % statt 14 %). Erst nach mindestens einem Sommer mit verlässlicher IST-Erfassung sinnvoll. |
| **Installationsdatum vorhanden / Anlagenleistung: X kWp / PV-Module: X kWp (N Modul-Gruppen)** | ✅ OK | Pflichtfelder gesetzt und konsistent. | – |

> **Hinweis:** Die früheren Felder „Ausrichtung" und „Neigung" am Anlage-Modell werden seit dem Refactoring zu PV-Modul-Investitionen nicht mehr geprüft — diese Werte gehören jetzt pro Modul-String an die jeweilige Investition (siehe [HANDBUCH_EINSTELLUNGEN.md §1.3](HANDBUCH_EINSTELLUNGEN.md)).

---

### 4.2 Strompreise

**Was wird geprüft:** Vorhandensein mindestens eines allgemeinen Tarifs, Lücken zwischen Tarif-Zeiträumen ab Installationsdatum, Existenz von Spezialtarifen für vorhandene WP- und E-Auto-Investitionen sowie Plausibilität der Preisangaben.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Kein Strompreis vorhanden** | ❌ ERROR | Es gibt keinen einzigen Tarif mit Verwendung *allgemein*. Finanz-Auswertungen, ROI-Berechnungen und Monatsabschluss greifen ins Leere. | Einstellungen → Strompreise → Tarif anlegen mit Arbeitspreis und Einspeisevergütung. |
| **Strompreis-Lücke: TT.MM.JJJJ bis TT.MM.JJJJ** | ⚠️ WARNING | Zwischen Installationsdatum und erstem Tarif (oder zwischen aufeinanderfolgenden Tarifen) klafft ein nicht abgedeckter Zeitraum. Für diese Monate fehlen Strompreise und damit Kostenrechnung. | Einstellungen → Strompreise → Tarif für den Lückenzeitraum anlegen, oder den vorhandenen Tarif rückwirkend gültig machen. |
| **Kein WP-Spezialtarif hinterlegt** | ℹ️ INFO | Eine aktive Wärmepumpe ist vorhanden, aber kein Tarif mit Verwendung *waermepumpe*. Nur relevant, wenn du tatsächlich einen separaten Wärmestrom-Tarif hast (HT/NT, eigener Zähler). | Wenn ein Wärmestrom-Tarif existiert: Einstellungen → Strompreise → Tarif anlegen, Verwendung *Wärmepumpe* wählen. Sonst Hinweis ignorieren. |
| **Kein E-Auto-Spezialtarif hinterlegt** | ℹ️ INFO | Aktives E-Auto vorhanden, aber kein Tarif mit Verwendung *e-auto*. Nur relevant bei separatem Ladetarif (z. B. Wallbox-Stromzähler mit eigenem Tarif). | Analog zum WP-Hinweis: Tarif mit Verwendung *E-Auto* anlegen oder ignorieren. |
| **Arbeitspreis ungewöhnlich: X,X ct/kWh (Tarifname)** | ⚠️ WARNING | Wert liegt außerhalb des erwarteten Bereichs 5–80 ct/kWh — typischerweise Eingabefehler (Komma vs. Punkt, ct vs. €/kWh). | Einstellungen → Strompreise → Tarif öffnen, Arbeitspreis prüfen. |
| **Einspeisevergütung ungewöhnlich: X,X ct/kWh (Tarifname)** | ⚠️ WARNING | Wert außerhalb 0–30 ct/kWh. Negative Werte oder zweistellige Vergütungen sind seit den 2010er Jahren untypisch. | Einstellungen → Strompreise → Tarif öffnen, Vergütung prüfen. Bei dynamischen Vergütungsmodellen (Direktvermarktung) eine sinnvolle Schätzung eintragen. |
| **N Strompreis-Tarif(e) vorhanden** | ✅ OK | Mindestens ein allgemeiner Tarif vorhanden — Anzahl ist informativ. | – |

---

### 4.3 Investitionen

**Was wird geprüft:** Pro aktive Investition werden typ-spezifische Pflicht- und Plausibilitäts-Parameter geprüft, anschließend für jeden Komponententyp die Vollständigkeit der monatlichen Verbrauchs- bzw. Erzeugungs-Daten ab Anschaffungsdatum. Allgemeine ROI-Parameter (Anschaffungsdatum, -kosten) werden für alle Typen geprüft.

> **Lesart der „Beheben"-Spalten:** Die meisten Befunde dieser Kategorie führen direkt nach *Einstellungen → Investitionen → \[Komponente\] öffnen*. Die Spalte nennt nur den fehlenden Parameter konkret.

#### 4.3.1 PV-Module

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Leistung (kWp) fehlt** | ⚠️ WARNING | Ohne `leistung_kwp` greift die kWp-Konsistenzprüfung in §4.1 nicht und PVGIS-Soll pro String fehlt. | Investition öffnen, Leistung in kWp eintragen. |
| **\[Name\]: Ausrichtung/Neigung fehlt** | ℹ️ INFO | Wird für PVGIS-Solarprognose pro String benötigt. Ohne sie nutzt die Prognose Anlagen-Defaults. | Investition öffnen, Ausrichtung (Süd/Ost/West) und Neigung in Grad eintragen. |
| **\[Name\]: PV-Erzeugung fehlt in N Monat(en)** | ⚠️ WARNING | `pv_erzeugung_kwh` fehlt in `InvestitionMonatsdaten` für mindestens einen Monat ab Anschaffungsdatum. Aufschlüsselung pro String funktioniert für diese Monate nicht. | Monatsabschluss-Wizard für die genannten Monate erneut durchlaufen, oder direkt in *Einstellungen → Monatsdaten* nachtragen. |

#### 4.3.2 Balkonkraftwerk

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Leistung (Wp) fehlt** | ⚠️ WARNING | Ohne `leistung_wp` (× Anzahl) ist die kWp-Summe der Anlage unvollständig. | Investition öffnen, Wp pro Modul und Modulanzahl eintragen. |
| **\[Name\]: PV-Erzeugung fehlt in N Monat(en)** | ⚠️ WARNING | Wie PV-Module: `pv_erzeugung_kwh` fehlt in den genannten Monaten. | Monatsabschluss nachholen. |

#### 4.3.3 Speicher

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Kapazität (kWh) fehlt** | ⚠️ WARNING | `kapazitaet_kwh` ist Bezugsgröße für Vollzyklen, Wirkungsgrad-Berechnung und Live-SoC-Skalierung. | Investition öffnen, Brutto-Kapazität in kWh eintragen. |
| **\[Name\]: Arbitrage aktiv, aber Ø Ladepreis fehlt** | ⚠️ WARNING | `nutzt_arbitrage` ist gesetzt, aber `lade_durchschnittspreis_cent` fehlt. Arbitrage-Einsparung kann nicht berechnet werden. | Investition öffnen, durchschnittlichen Ladepreis (z. B. negative Börsenpreise) eintragen. |
| **\[Name\]: Arbitrage aktiv, aber Ø Entladepreis fehlt** | ⚠️ WARNING | Analog zum Ladepreis: ohne `entlade_vermiedener_preis_cent` kein Arbitrage-Erlös berechenbar. | Vermiedenen Entladepreis (z. B. Endkundentarif zur Spitzenlastzeit) eintragen. |
| **\[Name\]: Speicher-Ladung fehlt in N Monat(en)** | ⚠️ WARNING | `ladung_kwh` fehlt in den genannten Monaten — Vollzyklen und Wirkungsgrad lassen sich für diese Monate nicht berechnen. | Monatsabschluss nachholen. |

#### 4.3.4 E-Auto (privat)

> Dienstwagen (`ist_dienstlich`) werden von dieser Prüfung übersprungen — kein PV-Bezug, kein Investment-ROI.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Fahrleistung/Verbrauch fehlt** | ℹ️ INFO | Weder `km_jahr` noch `verbrauch_kwh_100km` gesetzt. Einsparungs-Berechnung gegenüber Verbrenner ist nicht möglich. | Investition öffnen, Jahres-Fahrleistung und/oder Verbrauch eintragen. |
| **\[Name\]: Alternativkosten (Verbrenner) fehlen** | ⚠️ WARNING | `anschaffungskosten_alternativ` fehlt. ROI gegenüber Verbrenner-Alternative wird ohne diesen Wert nicht berechnet. | Investition öffnen, geschätzte Anschaffungskosten eines vergleichbaren Verbrenners eintragen. |
| **\[Name\]: V2H aktiv, aber Entladepreis fehlt** | ℹ️ INFO | `nutzt_v2h` ist gesetzt, aber `v2h_entlade_preis_cent` fehlt. V2H-Einsparung wird nicht berechnet. | Vermiedenen Entladepreis eintragen (analog Speicher-Arbitrage). |
| **\[Name\]: Ladung PV fehlt in N Monat(en)** | ℹ️ INFO | `ladung_pv_kwh` fehlt — Anteil PV-Ladung am Gesamt-Ladestrom unbekannt. Geringere Severity als andere Pflichtfelder, weil V2H/Wallbox-Aufschlüsselung optional ist. | Monatsabschluss nachholen, oder im Live-Betrieb über Wallbox-/EV-Sensor automatisch erfassen lassen. |

#### 4.3.5 Wallbox

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Ladeleistung (kW) fehlt** | ⚠️ WARNING | Weder `max_ladeleistung_kw` noch `leistung_kw` (Legacy) gesetzt. Auslegung und Lade-Profile lassen sich nicht plausibilisieren. | Investition öffnen, max. Ladeleistung in kW eintragen. |
| **\[Name\]: Ladung gesamt fehlt in N Monat(en)** | ℹ️ INFO | `ladung_kwh` fehlt in den genannten Monaten. | Monatsabschluss nachholen. |

#### 4.3.6 Wechselrichter

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Leistung (kW) fehlt** | ⚠️ WARNING | Weder `max_leistung_kw` noch `leistung_ac_kw` (Legacy) gesetzt. WR-Auslastungs-Auswertung und Cockpit-Header rechnen ohne diesen Wert nicht. | Investition öffnen, AC-Nennleistung des Wechselrichters in kW eintragen. |

#### 4.3.7 Wärmepumpe

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Alternativkosten (Gas-/Ölheizung) fehlen** | ⚠️ WARNING | `anschaffungskosten_alternativ` fehlt. ROI gegenüber konventioneller Heizung wird nicht berechnet. | Investition öffnen, geschätzte Anschaffungskosten einer vergleichbaren Gas-/Ölheizung eintragen. |
| **\[Name\]: JAZ nicht gesetzt** | ⚠️ WARNING | Effizienz-Modus ist *Gesamt-JAZ*, aber `jaz` fehlt. COP-Berechnung der Heizenergie geht nicht. | Investition öffnen, Jahresarbeitszahl eintragen (typischer Bereich 2,5–4,5 Luft-WP, 3,5–5,5 Sole-WP). |
| **\[Name\]: JAZ unplausibel (X,X)** | ⚠️ WARNING | `jaz` liegt außerhalb 1,5–7,0. Wahrscheinlich Eingabefehler (Komma vs. Punkt, Prozent-Wert statt Faktor). | Wert prüfen und korrigieren. |
| **\[Name\]: SCOP-Werte fehlen (Modus: EU-Label SCOP)** | ⚠️ WARNING | Effizienz-Modus *SCOP*, aber `scop_heizung` und/oder `scop_warmwasser` fehlen. Einsparung wird nicht berechnet. | Werte vom EU-Label / Datenblatt der WP eintragen. |
| **\[Name\]: COP-Werte fehlen (Modus: Getrennte COPs)** | ⚠️ WARNING | Modus *Getrennte COPs*, aber `cop_heizung` und/oder `cop_warmwasser` fehlen. | Beide Werte eintragen oder Modus auf JAZ wechseln. |
| **\[Name\]: Alter Energiepreis nicht gesetzt** | ℹ️ INFO | `alter_preis_cent_kwh` fehlt — Einsparungs-Berechnung gegen Gas/Öl nutzt Default-Preis. | Aktuellen Gas-/Ölpreis in ct/kWh eintragen für realistische Einsparung. |
| **\[Name\]: Heizwärmebedarf nicht gesetzt** | ℹ️ INFO | `heizwaermebedarf_kwh` fehlt — Jahres-Einsparungsschätzung greift auf Defaults zurück. | Geschätzten Jahres-Heizwärmebedarf in kWh eintragen (z. B. aus Energieausweis). |
| **\[Name\]: Strom Heizen/Warmwasser fehlt in N Monat(en)** | ⚠️ WARNING | Bei aktivierter `getrennte_strommessung`: `strom_heizen_kwh` und `strom_warmwasser_kwh` fehlen für die genannten Monate. | Monatsabschluss nachholen mit getrennten Werten. |
| **\[Name\]: Stromverbrauch fehlt in N Monat(en)** | ⚠️ WARNING | Ohne getrennte Strommessung: `stromverbrauch_kwh` fehlt. | Monatsabschluss nachholen. |
| **\[Name\]: Heizenergie fehlt in N Monat(en)** | ℹ️ INFO | `heizenergie_kwh` fehlt — JAZ und COP-Vergleich für die Monate nicht möglich, Stromverbrauch bleibt aber erfasst. | Wenn Wärmemengenzähler vorhanden: Werte nachtragen; sonst akzeptieren. |

#### 4.3.8 Allgemein (alle Komponententypen)

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Anschaffungsdatum fehlt** | ℹ️ INFO | `anschaffungsdatum` fehlt — Aggregate ab Inbetriebnahme können nicht eingegrenzt werden, Monatsdaten-Vollständigkeitsprüfung greift für diese Investition nicht. | Investition öffnen, Anschaffungsdatum eintragen. |
| **\[Name\]: Anschaffungskosten fehlen** | ℹ️ INFO | `anschaffungskosten_gesamt` fehlt. ROI- und Amortisations-Berechnung greift mit 0 €. | Investition öffnen, Brutto-Anschaffungskosten eintragen. |
| **\[Name\]: Monatsdaten vollständig (N Monate)** | ✅ OK | Alle Pflicht-Monatsfelder ab Anschaffungsdatum sind erfasst. | – |
| **Keine aktiven Investitionen vorhanden** | ℹ️ INFO | Anlage hat keine aktive Investition. Cockpit, ROI und Aufschlüsselungen sind leer. | Einstellungen → Investitionen → mindestens PV-Module oder Balkonkraftwerk anlegen. |

---

### 4.4 Monatsdaten – Vollständigkeit <a name="44-monatsdaten--vollstaendigkeit"></a>

**Was wird geprüft:** Welche Monate zwischen Installationsdatum (oder erstem Monatsdaten-Eintrag) und Vormonat sind in der Datenbank erfasst? Der laufende Monat wird ausgeklammert, weil er noch nicht abgeschlossen ist. Das Ergebnis fließt zusätzlich in den Fortschrittsbalken „Monatsdaten-Abdeckung" oben auf der Seite ein.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Keine Monatsdaten vorhanden** | ⚠️ WARNING | Es gibt keinen einzigen Monatsdaten-Eintrag. Cockpit, Aussichten, ROI und Community-Vergleich sind leer. | Monatsabschluss-Wizard für den ersten Monat ab Installation starten, oder per CSV-Import bestehende Daten einlesen. |
| **MM/JJJJ fehlt** | ⚠️ WARNING | Konkreter Monat zwischen Installationsdatum und Vormonat ist nicht erfasst. Wird einzeln gelistet (max. 12 Monate), darüber hinaus zusammengefasst. | „Beheben"-Link öffnet den Monatsabschluss-Wizard direkt für den fehlenden Monat. |
| **... und N weitere Monate fehlen** | ⚠️ WARNING | Mehr als 12 fehlende Monate — Sammelmeldung, um die Liste nicht zu überschwemmen. | Einstellungen → Monatsdaten öffnen, dort Monate per Wizard oder Import nachziehen. Bei vielen Lücken: HA-Statistik-Import nutzen, der mehrere Monate auf einmal aus HA-Long-Term-Statistics holt. |
| **Alle N Monate vollständig** | ✅ OK | Vom Installationsdatum bis Vormonat ist jeder Monat erfasst. | – |

> **Hinweis zur Abdeckungs-KPI:** Der Prozentwert oben auf der Seite bezieht sich auf erwartete Monate, nicht auf Datenfelder *innerhalb* eines Monats. Ein zu 100 % abgedeckter Monatsdaten-Stand kann trotzdem unvollständige Pflichtfelder enthalten — das prüft §4.5.

---

### 4.5 Monatsdaten – Plausibilität <a name="45-monatsdaten--plausibilitaet"></a>

**Was wird geprüft:** Pro vorhandenem Monatsdaten-Eintrag werden Pflichtfelder, Werte-Ranges, logische Konsistenz und (sobald verfügbar) Vergleich gegen Vorjahresmonat sowie PVGIS-Prognose geprüft. Die PV-Maximum-Prüfung nutzt eine **dynamische Obergrenze** aus PVGIS-Soll × aktueller Performance Ratio × 1,45 (sobald 6+ Monate Historie verfügbar) — sonst statisches Maximum nach Monat und kWp. Der 1,45-Faktor deckt die natürliche Monatsvariation ab.

#### Pflichtfelder

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: Einspeisung nicht erfasst** | ❌ ERROR | Kernfeld `einspeisung_kwh` ist `NULL`. Eigenverbrauch und Autarkie nicht berechenbar. | Monatsabschluss öffnen, Einspeisung eintragen. |
| **MM/JJJJ: Netzbezug nicht erfasst** | ❌ ERROR | Kernfeld `netzbezug_kwh` ist `NULL`. Hausverbrauch und Stromkosten nicht berechenbar. | Monatsabschluss öffnen, Netzbezug eintragen. |
| **MM/JJJJ: Batterie-Ladung nicht erfasst (Speicher vorhanden)** | ⚠️ WARNING | Aktive Speicher-Investition vorhanden, aber weder Legacy-Feld `batterie_ladung_kwh` noch neues `InvestitionMonatsdaten.ladung_kwh`. Hausverbrauchs-Berechnung wird falsch. | Monatsabschluss öffnen, Batterie-Ladung in der Speicher-Komponente eintragen. |
| **MM/JJJJ: Batterie-Entladung nicht erfasst (Speicher vorhanden)** | ⚠️ WARNING | Analog zur Ladung — `entladung_kwh` fehlt. | Monatsabschluss öffnen, Batterie-Entladung eintragen. |

#### Werte-Plausibilität

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: \[Feld\] ist negativ (X,X kWh)** | ❌ ERROR | Einspeisung, Netzbezug, PV-Erzeugung oder Batteriewerte sind < 0. Energiemengen können physikalisch nicht negativ sein. | Monatsabschluss öffnen, Vorzeichen-/Eingabefehler korrigieren. Bei Sensor-Drift: Zählerstand-Differenz prüfen. |
| **MM/JJJJ: PV-Erzeugung ungewöhnlich hoch (X kWh)** | ⚠️ WARNING | Wert übersteigt das dynamische Maximum (PVGIS × max(PR; 1,0) × 1,45) bzw. das statische Maximum (kWp × Monatsfaktor). Details nennen den verwendeten Schwellwert. | Wert prüfen — Eingabefehler? Falscher Multiplikator? Falls echt: vermutlich war der Monat aussergewöhnlich strahlungsreich, dann WARNING ignorieren. |
| **MM/JJJJ: Einspeisung (X kWh) > PV-Erzeugung (Y kWh)** | ❌ ERROR | Logisch unmöglich — du kannst nicht mehr einspeisen als erzeugen. | Beide Werte prüfen. Häufige Ursache: PV-Erzeugung wurde nur teilweise erfasst (z. B. ein String fehlt in den Investitionen), oder Einspeisung enthält fälschlich Bezug. |
| **MM/JJJJ: Einspeisung und Netzbezug sind beide 0** | ⚠️ WARNING | Beide Kernfelder sind 0 — wahrscheinlich fehlende Daten, kein echter Null-Verbrauch. | Monatsabschluss öffnen, Werte eintragen. Falls die Anlage tatsächlich den ganzen Monat aus war (Umzug, Defekt): WARNING akzeptieren. |
| **MM/JJJJ: \[Feld\] > 3× Vorjahr (X vs. Y kWh)** | ⚠️ WARNING | Einspeisung oder Netzbezug ist mehr als dreimal so groß wie der gleiche Monat im Vorjahr (Vorjahr > 50 kWh). Häufig Eingabefehler (Faktor 10) oder Zählerwechsel ohne Reset. | Werte beider Monate prüfen. Bei echter Veränderung (neue Wallbox, neue WP): WARNING akzeptieren. |

#### Energiebilanz

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: Energiebilanz ergibt negativen Hausverbrauch (X,X kWh)** | ❌ ERROR | `PV − Einspeisung + Netzbezug + Bat.Entladung − Bat.Ladung` ist deutlich negativ (< −0,5 kWh). Logisch unmöglich. Details listen alle Summanden auf. | Häufige Ursache: fehlende Batterie-Daten verzerren die Bilanz. Erst Batterie-Werte vervollständigen, dann erneut prüfen. Wenn weiterhin negativ: PV-Erzeugung oder Einspeisung enthält Eingabefehler. |
| **Keine Auffälligkeiten in den Monatsdaten** | ✅ OK | Alle vorhandenen Monatsdaten haben Pflichtfelder, plausible Werte und konsistente Bilanz. | – |

> **Hintergrund zur PV-Obergrenze:** Mit ≥ 6 Monaten Historie ohne Lücken passt sich die Obergrenze an die tatsächliche Performance der Anlage an. Eine systematisch über PVGIS produzierende Anlage (PR > 1,0) bekommt einen entsprechend höheren Schwellwert. Mindestschwellwert ist immer PVGIS × 1,5 — neue Anlagen ohne genug Historie bleiben damit großzügig im grünen Bereich.

---

### 4.6 Energieprofil – Zähler-Abdeckung <a name="46-energieprofil--zaehler-abdeckung"></a>

> **Variantenhinweis:** Im **HA Add-on** sind die Zähler HA-Entitäten (`sensor.…`) mit `state_class: total_increasing`. Im **Standalone-Betrieb** sind sie kumulative MQTT-Topics (`eedc/<anlage>/inv/<id>/<feld>`). Die Prüflogik ist in beiden Fällen identisch — sie schaut nur, ob im Sensor-Mapping pro Komponente ein kWh-Zähler eingetragen ist.

**Was wird geprüft:** Welche kumulativen kWh-Zähler sind im `sensor_mapping` der Anlage gesetzt? Ohne diese Zähler bleibt das Energieprofil für die betroffenen Komponenten leer (strikte NULL-Semantik) — und damit auch Prognosen-IST, Heatmap, Lernfaktor und Monatsberichte. Live-Anzeigen aus `*_leistung_w` funktionieren weiter, integrieren aber nicht zu Energiemengen.

**Erwartete Zähler pro Komponententyp:**

| Komponententyp | Erwartete kWh-Zähler-Felder |
|---------------|------------------------------|
| pv-module, balkonkraftwerk | `pv_erzeugung_kwh` |
| speicher | `ladung_kwh`, `entladung_kwh` |
| waermepumpe | `stromverbrauch_kwh` |
| wallbox, e-auto | `ladung_kwh` |
| wechselrichter, sonstiges | (keine — werden übersprungen) |

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Kein Basis-Zähler für: \[Einspeisung, Netzbezug\]** | ⚠️ WARNING | Im Sensor-Mapping fehlt der Basis-Zähler für Einspeisung und/oder Netzbezug. Ohne diesen bleibt der bilanzielle Hausverbrauch im Energieprofil leer. | Sensor-Mapping-Wizard öffnen, in der Sektion *Basis* den kumulativen kWh-Zähler eintragen. **Wichtig:** den kWh-Zähler wählen, nicht den `*_leistung_w`-Sensor. |
| **N von M Komponenten ohne vollständige kWh-Zähler-Abdeckung** | ⚠️ WARNING | Mindestens eine aktive Komponente hat nicht alle erwarteten kWh-Zähler im Mapping. Details listen die betroffenen Komponenten und fehlenden Felder. Folgen für diese Komponenten: Prognosen-IST, Heatmap, Lernfaktor und Monatsberichte bleiben leer. | Sensor-Mapping-Wizard öffnen, pro Komponente die fehlenden Zähler ergänzen. Bei Speichern: beide Felder (`ladung_kwh` + `entladung_kwh`) sind nötig. |
| **Basis-Zähler (Einspeisung + Netzbezug) gemappt** | ✅ OK | Beide Basis-Zähler im Mapping vorhanden. | – |
| **Alle N aktiven Komponenten haben kWh-Zähler gemappt** | ✅ OK | Alle aktiven Komponenten mit erwarteten Zählern sind vollständig gemappt. | – |

> **Hinweis:** Diese Kategorie prüft nur das **Vorhandensein** des Mappings — ob der Zähler tatsächlich Daten liefert, prüft §4.8 (MQTT-Topic-Abdeckung) bzw. §4.9 (Sensor-Mapping HA-Statistics). Plausibilität der bereits aggregierten Stundenwerte (Counter-Spikes durch Update-Restarts) erfasst §4.7.

---

### 4.7 Energieprofil – Plausibilität <a name="47-energieprofil--plausibilitaet"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten identisch — sie liest ausschließlich die bereits gespeicherten Stundenwerte des `tages_energie_profil`.

**Was wird geprüft:** Enthält das Tagesprofil der letzten 30 Tage Stundenwerte, die physikalisch unmöglich sind? Konkret: `pv_kw` oder `einspeisung_kw` größer als die Anlagen-Nennleistung × 1.5. Tritt typischerweise nach Update-Restarts während des Tages auf, wenn der Counter-Snapshot-Service einen verzerrten kumulativen Wert speichert (z. B. der `get_value_at`-Off-by-one-Bug aus Befund 2026-05-01, behoben in v3.25.10).

**Schwelle:** `Anlagen-kWp × 1.5`. Eine eindeutige Wahnschwelle — eine Aufdach-PV-Anlage erzeugt selbst bei optimalem Sonnenstand nicht mehr als ~1500 W pro kWp. Werte darüber sind keine Naturereignisse, sondern Rechen-/Snapshot-Artefakte.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Counter-Spike am YYYY-MM-DD: N Stundenwert(e) > X kW** | ⚠️ WARNING | Ein einzelner Tag enthält mindestens eine Stunde, deren `pv_kw` oder `einspeisung_kw` über der Wahnschwelle liegt. Detail-Liste nennt Stunde und Wert. | Im Tages-Energieprofil-Tab das Reload-Symbol rechts neben dem betroffenen Tag klicken („Tag neu aggregieren"). Seit v3.25.x repariert dieser Klick zuerst die SensorSnapshots aus HA-Statistics und baut danach das Aggregat neu — beides in einem Schritt. Bei mehreren betroffenen Tagen alternativ in *Einstellungen → Energieprofil → Datenverwaltung* den Knopf *„Verlauf nachberechnen"* mit aktiviertem Überschreiben nutzen. |
| **Keine Counter-Spikes in den letzten 30 Tagen** | ✅ OK | Alle Stundenwerte liegen innerhalb der physikalisch plausiblen Bandbreite. | – |

> **Hinweis:** Ältere Tage (> 30 Tage) werden nicht geprüft, weil dort entweder bereits korrigierte Werte stehen oder sie für die aktuelle Lernfaktor-Basis nicht mehr relevant sind. Wer ältere Tage trotzdem reparieren will, nutzt *„Verlauf nachberechnen"* mit Überschreiben — das Werkzeug greift bis zur HA-LTS-Reichweite zurück.

---

### 4.8 MQTT-Topic-Abdeckung <a name="48-mqtt-topic-abdeckung"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten — aber **nur**, wenn der Nutzer MQTT-Inbound bewusst aktiviert hat (Daten → Einrichtung → MQTT-Inbound). Ohne aktivierten Inbound wird die Kategorie still übersprungen, damit Anwender ohne MQTT sie gar nicht erst sehen.

**Was wird geprüft:** Werden die aus `field_definitions.py` und dem Sensor-Mapping erwarteten MQTT-Topics tatsächlich vom Subscriber empfangen? Diese Kategorie schließt die Lücke zwischen der dynamischen Konsumenten-Seite (Erwartungsliste aus dem eedc-Code) und der statisch hartkodierten Publisher-Seite (HA-Automation, ioBroker, Node-RED). Wenn dort jemand neue Felder vergisst oder Investitions-IDs nach einem Re-Import nicht nachzieht, läuft die Erwartung gegen die Realität auseinander — diese Kategorie macht's sichtbar.

**Schwellwerte für „veraltet":**

| Topic-Kategorie | Maximales Alter |
|----------------|-----------------|
| Live-Topics (sensorgetrieben) | 2 Minuten |
| Energy-Topics (alle-5-min-Pattern + Puffer) | 10 Minuten |

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MQTT-Inbound aktiviert, Subscriber läuft jedoch nicht** | ℹ️ INFO | Inbound ist in den Einstellungen aktiviert, aber der Subscriber konnte nicht starten (z. B. Broker nicht erreichbar, falsche Zugangsdaten). | Daten → Einrichtung → MQTT-Inbound öffnen, Broker-Adresse und Zugangsdaten prüfen. Oder MQTT-Inbound deaktivieren, wenn keine Live-Daten via MQTT gewünscht. |
| **N MQTT-Topic(s) erwartet, nie empfangen** | ⚠️ WARNING | Subscriber läuft, aber für die genannten Topics liefert noch keine Quelle Daten. Beispiele werden gelistet (max. 6, Rest aggregiert). | Mögliche Ursachen: (a) Publisher-Automation noch nicht eingerichtet — siehe [HANDBUCH_EINSTELLUNGEN.md §6 MQTT-Inbound](HANDBUCH_EINSTELLUNGEN.md#6-mqtt-inbound). (b) Investitions-IDs nach Re-Import nicht in der Automation nachgezogen — Topic-Struktur enthält die eedc-interne ID. (c) Wenn die Topics gar nicht gebraucht werden: MQTT-Inbound deaktivieren. |
| **N MQTT-Topic(s) mit veralteten Werten** | ⚠️ WARNING | Topics werden grundsätzlich empfangen, aber älter als der Schwellwert. Beispiele zeigen Topic + Alter in Minuten. | Publisher-Automation prüfen: läuft sie noch? Hat sie ihre Quelle verloren (z. B. Wechselrichter offline)? Bei dauerhaft fehlenden Quellen die Automation aufräumen oder die Sensoren neu zuordnen. |
| **Alle N erwarteten MQTT-Topics aktuell empfangen** | ✅ OK | Subscriber läuft, alle erwarteten Topics liefern frische Daten innerhalb der Toleranz. | – |

> **Wichtig zur Skip-Logik:** Wenn MQTT-Inbound nicht aktiviert ist, erscheint diese Kategorie gar nicht — nicht „OK", nicht „leer". So bleibt die Daten-Checker-Übersicht für Nutzer ohne MQTT übersichtlich.

---

### 4.9 Sensor-Mapping – HA-Statistics <a name="49-sensor-mapping--ha-statistics"></a>

> **Variantenhinweis:** Diese Kategorie greift nur im **HA Add-on**. Im Standalone-Betrieb gibt es keine HA-Long-Term-Statistics; ein eventuell vorhandener INFO-Befund weist auf den Skip hin. Funktional wird die analoge Drift-Erkennung im Standalone-Betrieb über §4.8 *MQTT-Topic-Abdeckung* abgedeckt.

**Was wird geprüft:** Liefert jeder im Sensor-Mapping verwendete Sensor tatsächlich Long-Term-Statistics nach Home Assistant? Sensoren ohne `state_class` haben keine LTS-Einträge und damit greifen die **Korrektur-Werkzeuge in der Datenverwaltung** (Vollbackfill, *Verlauf nachrechnen*, Per-Tag-Reaggregation) nicht — sie lesen alle aus HA-LTS. Live-Anzeigen funktionieren weiter (über `state`), aber jeder Aussetzer im Snapshot-Pfad ist permanent verloren, weil er nicht aus LTS nachgeholt werden kann.

Der Wizard-Filter wurde in v3.24.1 aufgeweicht („Alle Sensoren ohne Filter anzeigen") — damit lassen sich z. B. Nibe-Roh-Counter ohne Metadaten auswählen, aber genau dieser Spielraum verlangt nach dieser Prüfkategorie.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **HA Long-Term-Statistics nicht erreichbar — Mapping-Prüfung übersprungen** | ℹ️ INFO | eedc kann HA-LTS gerade nicht abfragen (z. B. Standalone-Betrieb, oder HA-API zwischenzeitlich nicht erreichbar). Die Kategorie wird übersprungen. | Standalone: keine Aktion nötig — die Kategorie ist hier irrelevant. HA Add-on: HA-API-Zugriff prüfen ([Einstellungen → Home Assistant](HANDBUCH_EINSTELLUNGEN.md#5-home-assistant-integration)). |
| **N kWh-Sensor(en) nicht in HA-Long-Term-Statistics** | ⚠️ WARNING | Mindestens ein kWh-Feld im Sensor-Mapping (z. B. *Basis: einspeisung*, *Wärmepumpe: stromverbrauch_kwh*) zeigt auf einen Sensor ohne `state_class`. Korrektur-Werkzeuge greifen für diese Felder nicht; vergangene Monate bleiben leer, wenn der Snapshot-Pfad eine Lücke hatte. | Bevorzugt: `state_class: total_increasing` über HA-`customize.yaml` ergänzen. Alternativ: einen anderen Sensor wählen, der bereits LTS liefert. Siehe [HANDBUCH_EINSTELLUNGEN.md §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping). |
| **N Counter-Sensor(en) ohne state_class — Korrektur-Werkzeuge wirken nicht** | ⚠️ WARNING | Counter-Felder (z. B. WP-Kompressor-Starts) werden über den stündlichen Snapshot-Service erfasst und funktionieren live. Ohne `state_class` greifen aber dieselben Korrektur-Werkzeuge nicht: Aussetzer (Neustart, Polling-Hänger) sind permanent verloren, häufig fehlt zusätzlich die letzte Tagesstunde (23–24 Uhr). | `state_class: total_increasing` per `customize.yaml` ergänzen, dann laufen alle Reparatur-Werkzeuge auf diesem Sensor. |
| **Alle N kWh-Sensor(en) im Mapping in HA-Long-Term-Statistics verfügbar** | ✅ OK | Jeder kWh-Sensor des Mappings liefert LTS — Korrektur-Werkzeuge wirken auf alle Felder. | – |

> **Wichtige Lektion (v3.24.3):** Frühere Hinweistexte sagten „vergangene Tage bleiben leer". Das ist irreführend, weil HA-Long-Term-Statistics ohnehin erst ab Aktivierung von `state_class` angelegt werden — vor der Aktivierung existieren keine Werte zum Holen, egal wann du `customize.yaml` setzt. Der eigentliche Schmerzpunkt ist daher: ohne `state_class` **wirken die Korrektur-Werkzeuge in der Datenverwaltung nicht**. Ab Aktivierung läuft's lückenfrei, davor bleibt's leer.

---

## 5. Behebungs-Workflows

Diese Querschnitts-Anleitungen bündeln Schritte, die mehrere Befunde gleichzeitig betreffen — typischerweise weil ein einzelner Konfigurationsfehler in mehreren Kategorien aufschlägt.

### 5.1 `state_class`-Probleme bei HA-Sensoren beheben

**Symptom:** Befunde aus §4.9 *„kWh-Sensor(en) nicht in HA-Long-Term-Statistics"* oder *„Counter-Sensor(en) ohne state_class"*.

**Ursache:** HA legt für einen Sensor erst dann Long-Term-Statistics an, wenn dessen Attribut `state_class` gesetzt ist. Typisch sind kumulative Zähler ohne diese Metadata bei Modbus-Roh-Werten oder Hersteller-Integrationen.

**Lösung:**

1. In Home Assistant `configuration.yaml` (oder `customize.yaml`) öffnen.
2. Für jeden betroffenen Sensor einen `customize`-Block ergänzen:

   ```yaml
   homeassistant:
     customize:
       sensor.dein_zaehler:
         state_class: total_increasing
         device_class: energy
         unit_of_measurement: kWh
   ```

3. Home Assistant neu starten.
4. In eedc: Daten-Checker erneut prüfen — der Befund muss verschwinden.

> **Wichtig:** HA legt LTS **erst ab Aktivierung** an. Vergangene Tage vor der `state_class`-Aktivierung bleiben permanent leer — das ist eine HA-Eigenschaft, kein eedc-Bug. Korrektur-Werkzeuge (Vollbackfill, *Verlauf nachrechnen*, Per-Tag-Reaggregation) wirken erst auf den Zeitraum **nach** Aktivierung.

### 5.2 Fehlende kWh-Zähler im Sensor-Mapping ergänzen

**Symptom:** Befunde aus §4.6 *„Kein Basis-Zähler für …"* oder *„N von M Komponenten ohne vollständige kWh-Zähler-Abdeckung"*.

**Lösung:**

1. Einstellungen → Datenerfassung → Sensor-Mapping-Wizard öffnen.
2. Im Wizard die genannten Komponenten durchgehen.
3. Pro Pflichtfeld einen kumulativen kWh-Zähler wählen — **nicht** den `*_leistung_w`-Sensor (Live-Leistung in Watt taugt nicht für Energiemengen).
4. Erwartete Felder pro Komponententyp siehe Tabelle in §4.6.
5. Wizard durchlaufen und speichern.
6. Daten-Checker erneut prüfen.

> **Hinweis:** Wenn dir kein passender kWh-Sensor angezeigt wird, ist er möglicherweise vom Filter ausgeschlossen. v3.24.1 hat einen Fallback-Link „Alle Sensoren ohne Filter anzeigen" eingeführt — siehe [HANDBUCH_EINSTELLUNGEN.md §3.6](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping). Vorsicht: Sensoren ohne Standard-Metadata führen dann zu §4.9-Befunden — siehe Workflow 5.1.

### 5.3 Monatsdaten-Lücken aufholen

**Symptom:** Befunde aus §4.4 *„MM/JJJJ fehlt"* oder *„… und N weitere Monate fehlen"*.

**Drei Wege, je nach Lückengröße:**

| Anzahl fehlender Monate | Empfohlener Weg |
|------------------------|-----------------|
| 1–3 Monate | Monatsabschluss-Wizard pro Monat (Klick auf den „Beheben"-Link führt direkt dorthin). |
| 4+ Monate, HA-Add-on | HA-Statistik-Import nutzen — holt mehrere Monate aus HA-LTS auf einmal. Siehe [HANDBUCH_EINSTELLUNGEN.md §4](HANDBUCH_EINSTELLUNGEN.md#4-ha-statistik-import). Voraussetzung: §4.9 ist OK (state_class gesetzt). |
| Bestehende Daten aus anderem System | CSV-Import in Einstellungen → Daten → Import (Template via Download-Link auf der Importseite). |

Nach jedem Schritt: Daten-Checker erneut prüfen.

### 5.4 MQTT-Drift zwischen Publisher und eedc schließen

**Symptom:** Befunde aus §4.8 *„N MQTT-Topic(s) erwartet, nie empfangen"* nach einem Re-Import oder neuer Komponente.

**Lösung:**

1. Daten-Checker → §4.8 öffnen, betroffene Topics notieren — sie enthalten typischerweise eine Investitions-ID, die nach dem Re-Import neu vergeben wurde.
2. Publisher-Quelle öffnen (HA-Automation YAML, ioBroker Skript, Node-RED Flow).
3. Investitions-IDs in den Topic-Pfaden anpassen — die neuen IDs findest du in eedc unter Einstellungen → Investitionen am jeweiligen Komponenten-Eintrag.
4. Publisher neu starten / Automation reloaden.
5. 2 Minuten warten (Live-Topics) bzw. 10 Minuten (Energy-Topics), dann Daten-Checker erneut prüfen.

> **Vorbeugend:** Nach jedem Re-Import einer Anlage einmal §4.8 prüfen — dort wird Drift sofort sichtbar.

### 5.5 Plausibilitäts-WARNINGs bewerten

**Symptom:** Befunde aus §4.5 (PV-Erzeugung ungewöhnlich hoch, Wert > 3× Vorjahr, Bilanz-Auffälligkeit).

**Vorgehen:**

1. Befund-Details lesen — sie nennen den verwendeten Schwellwert und die Eingangsgrößen.
2. Eingabefehler ausschließen: Komma vs. Punkt, Faktor 10, Vorzeichen, Verwechslung Einspeisung/Bezug.
3. Wenn Werte korrekt sind: WARNING als „zur Kenntnis genommen" akzeptieren — der Daten-Checker hat keine Snooze-Funktion, der Hinweis bleibt sichtbar.
4. Bei Energiebilanz-ERRORs: zuerst Batterie-Daten vervollständigen, dann erneut prüfen — fehlende Batteriewerte sind die häufigste Ursache.

---

### 5.6 Counter-Spike im Tagesprofil reparieren

**Symptom:** Befunde aus §4.7 *„Counter-Spike am YYYY-MM-DD: N Stundenwert(e) > X kW"*. Tritt vor allem nach Update-Restarts während des Tages auf, wenn der Snapshot-Service einen verzerrten kumulativen Counter-Wert aufnimmt.

**Vorgehen für einen einzelnen Tag:**

1. *Aussichten → Energieprofil* öffnen, in der Tages-Tabelle den betroffenen Tag suchen.
2. Auf das grüne Reload-Symbol rechts in der Zeile klicken (*„Tag X neu aggregieren"*).
3. Dialog bestätigen — der Endpoint zieht zuerst die SensorSnapshots des Tages frisch aus HA-Statistics (Resnap mit korrigiertem `get_value_at`) und baut danach Tagesprofil + Tageszusammenfassung neu.
4. Tabelle aktualisiert sich; der Spike ist weg, vorausgesetzt der zugrunde liegende kWh-Zähler hat den fraglichen Stundenslot in HA-LTS plausibel.

**Vorgehen für mehrere Tage / längere Bereiche:**

1. *Einstellungen → Energieprofil → Datenverwaltung* öffnen.
2. Checkbox *„Bestehende Tage überschreiben"* aktivieren.
3. *„Verlauf nachberechnen"* klicken. Resnap der gesamten Range + Aggregat-Neuaufbau in einem Schritt. Kann bei mehreren Monaten Bestand einige Minuten dauern.

> **Hinweis:** Tage **löschen** ist *keine* sinnvolle Reparaturstrategie. Eine gelöschte Lerngrundlage kostet die Solarprognose den saisonalen Lernfaktor (Memory: Monatsfaktor ≥ 15 Tage), und der eigentliche Defekt sitzt im Snapshot-Cache, nicht in den HA-LTS-Werten. Resnap holt die Daten zurück — Löschen tut das nicht.

---

## 6. Beziehung zu anderen Werkzeugen

Der Daten-Checker ist Diagnose, nicht Behebung. Er **zeigt** Probleme und verlinkt zu den jeweiligen Werkzeugen, die sie lösen. Die folgende Übersicht zeigt, welches Werkzeug welche Befund-Kategorie adressiert.

| Befund aus | Adressiert über |
|------------|----------------|
| §4.1 Stammdaten | Einstellungen → Anlage |
| §4.2 Strompreise | Einstellungen → Strompreise |
| §4.3 Investitionen (Parameter) | Einstellungen → Investitionen → \[Komponente\] |
| §4.3 Investitionen (Monatsdaten) | Monatsabschluss-Wizard, Einstellungen → Monatsdaten |
| §4.4 Vollständigkeit | Monatsabschluss-Wizard (Einzelmonat), HA-Statistik-Import (Bulk), CSV-Import |
| §4.5 Plausibilität | Monatsabschluss-Wizard (Einzelmonat), bei Sensor-Drift: Connector / Sensor-Mapping prüfen |
| §4.6 Energieprofil-Zähler | Sensor-Mapping-Wizard |
| §4.7 Energieprofil-Plausibilität | „Tag neu aggregieren" oder „Verlauf nachberechnen" mit Überschreiben (zieht Snapshots frisch + baut Aggregate neu) |
| §4.8 MQTT-Topic-Abdeckung | Externe Publisher-Quelle (HA-Automation YAML, ioBroker, Node-RED), MQTT-Inbound-Einstellungen |
| §4.9 Sensor-Mapping HA-Statistics | HA-`customize.yaml` (state_class), Sensor-Mapping-Wizard (alternativen Sensor wählen) |

### Korrektur-Werkzeuge in der Datenverwaltung

Diese Werkzeuge laufen nicht aus dem Daten-Checker heraus, sondern unter Einstellungen → Daten → Datenverwaltung. Sie greifen aber **nur**, wenn die Voraussetzungen aus §4.9 erfüllt sind (Sensoren in HA-Long-Term-Statistics):

| Werkzeug | Zweck | Voraussetzung |
|---------|-------|---------------|
| **Vollbackfill** | Holt rückwirkend alle stündlichen Snapshots aus HA-LTS für gemappte kWh-Felder (Initial-Befüllung historischer Bereiche). | §4.9 OK für betroffene Sensoren |
| **Verlauf nachrechnen** (Vollbackfill mit Überschreiben) | Schreibt Snapshots des Bereichs aus HA-LTS frisch (Resnap mit korrigiertem `get_value_at`-Pfad) **und** baut Tages-/Monats-Aggregate neu. Repariert Counter-Spikes wie aus §4.7. | §4.9 OK |
| **Tag neu aggregieren** (Per-Tag-Reaggregation) | Wie *Verlauf nachrechnen*, aber für einen ausgewählten Tag (grünes Reload-Symbol in der Tages-Tabelle). Seit v3.25.x ebenfalls mit Resnap-Vorlauf. | §4.9 OK |
| **Kraftstoffpreis-Backfill** | Holt EU-Oil-Bulletin-Preise für E-Auto- und Verbrenner-Vergleich rückwirkend. | unabhängig von §4.9 |

> **Wichtig:** Wenn §4.8 für einen Sensor WARNING meldet, sind die ersten drei Werkzeuge für diesen Sensor wirkungslos — sie lesen alle aus HA-LTS, die für state_class-lose Sensoren leer ist. Erst §4.8 beheben, dann Korrektur-Werkzeuge laufen lassen.

### Wo erscheint der Daten-Checker noch?

- **In-App-Hilfe** (Einstellungen → Hilfe ab v3.24.2): Diese Doku ist dort als kuratiertes Hilfe-Dokument verfügbar.
- **„Beheben"-Links innerhalb der App**: Befund-Zeilen verlinken direkt zur betroffenen Settings-Seite — kein Suchen in den Untermenüs nötig.
- **Aktivitäten-Log** (Einstellungen → System → Protokolle, Tab *Aktivitäten*): Bestimmte Befund-Kategorien (z. B. Connector-Test-Ergebnisse) finden sich auch dort historisch.

---

> **Verwandte Doku:**
> [Teil III §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping) · [Teil III §4 HA-Statistik-Import](HANDBUCH_EINSTELLUNGEN.md#4-ha-statistik-import) · [Teil III §6 MQTT-Inbound](HANDBUCH_EINSTELLUNGEN.md#6-mqtt-inbound) · [Teil III §10 Energieprofile-Hintergrund](HANDBUCH_EINSTELLUNGEN.md#10-energieprofile--hintergrund)
