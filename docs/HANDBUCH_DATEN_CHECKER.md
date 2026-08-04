
# eedc Handbuch — Daten-Checker

**Version 4.0** | Stand: 2026-08-02

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Infothek](HANDBUCH_INFOTHEK.md) | [Glossar](GLOSSAR.md)

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
   10. [Energieprofil – fehlende Tageswerte](#410-energieprofil--fehlende-tageswerte)
   11. [Geräte-Connector ohne Monatswert](#411-geraete-connector-ohne-monatswert)
5. [Behebungs-Workflows](#5-behebungs-workflows)
6. [Beziehung zu anderen Werkzeugen](#6-beziehung-zu-anderen-werkzeugen)

---

## 1. Was ist der Daten-Checker?

**Pfad:** Einstellungen → Daten → Daten-Checker

Der Daten-Checker prüft systematisch, ob deine Anlage so konfiguriert ist, dass alle Auswertungen verlässlich rechnen können. Er meldet fehlende Stammdaten, Plausibilitäts-Auffälligkeiten in den Monatsdaten und Drift-Probleme zwischen der Datenquellen-Zuordnung und den tatsächlich verfügbaren Datenquellen — jeweils mit „Beheben"-Link direkt zur betroffenen Stelle in der App.

Der Daten-Checker ist eine der Kacheln in der Einstellungs-Kategorie **Daten** (neben Monatsdaten, Energieprofil-Pflege und Ersteinrichtung). Prüf-Lauf, Befund-Kategorien und die Reparatur-Werkbank laufen **inline im Block** — der große Voll-Blick über die Vollbild-Ansicht (⤢). Ein eigener Seitenwechsel ist nicht mehr nötig.

### Aufruf

Die Prüfung läuft pro Anlage, ist nicht zeitgesteuert und liest immer den aktuellen Stand. Beim Öffnen des Blocks wird automatisch geprüft; **Erneut prüfen** im Block-Kopf startet die Prüfung neu (z. B. nach einer Korrektur).

### Aufbau der Ergebnis-Fläche

- **KPI-Karten** oben: Gesamtzahl Fehler / Warnungen / Hinweise / OK über alle Kategorien.
- **Monatsdaten-Abdeckung**: Fortschrittsbalken „X von Y Monaten erfasst" ab Installationsdatum bis Vormonat.
- **Klappbare Kategorie-Sektionen**: Jede Kategorie zeigt im Kopf eine Sammel-Bewertung (z. B. *„2 Warnungen, 1 Hinweis"* oder *OK*) und enthält die Einzelbefunde.
- **Befund-Zeilen** mit Symbol (Severity), Meldung, optionalen Details und „Beheben"-Link zur betroffenen Stelle (Datenquellen, Monatsdaten, Komponenten-Formular usw.).

> Der Daten-Checker umfasst inzwischen mehr Kategorien als die hier dokumentierten Kern-Kategorien (u. a. Datenquelle-Drift, Daten-Quellen-Konflikte, Batterie-Vorzeichen-Historie, PV-Doppelerfassungs-Verdacht, E-Mobilität-Pool-Pflege). Sie folgen derselben Severity- und „Beheben"-Logik. Eine vollständige Dokumentation dieser jüngeren Kategorien ist ein separater Redaktions-Schritt (kein Bestandteil des reinen IA-Umbaus).

### Wann sollte ich den Daten-Checker nutzen?

- **Nach der Erst-Einrichtung** — sofortige Rückmeldung, was zur Vollständigkeit fehlt.
- **Wenn Auswertungen leer wirken** — der Checker zeigt, ob es an fehlenden Stammdaten, der Datenquellen-Zuordnung oder fehlenden Monatsdaten liegt.
- **Bei Plausibilitäts-Auffälligkeiten** — z. B. wenn eine Monats-Erzeugung deutlich vom Erwartungswert abweicht.
- **Nach Anlagen-Updates** (neue Komponente, Datenquellen-Zuordnung geändert, Re-Import) — er erkennt Drift.
- **Vor Community-Teilung** — Stammdaten-Vollständigkeit ist Voraussetzung für sinnvolle Vergleiche.

---

## 2. Severity-Logik

Jeder Befund hat genau eine von vier Schweregraden. Sie sind nicht zu addieren — eine WARNING wird nicht durch viele OKs aufgewogen.

| Symbol | Schweregrad | Bedeutung | Erwartete Reaktion |
|--------|-------------|-----------|-------------------|
| ❌ | **ERROR** (rot) | Kerndaten fehlen oder Werte sind logisch unmöglich (z. B. Einspeisung > PV-Erzeugung). Ohne Behebung sind die zugehörigen Auswertungen entweder leer oder produzieren falsche Ergebnisse. | Beheben, **bevor** du den Auswertungen vertraust. |
| ⚠️ | **WARNING** (amber) | Plausibilitäts-Abweichung oder fehlende Pflicht-Parameter, die einzelne Auswertungen einschränken (ROI, Heizenergie-Vergleich, kWh-basierte Reparatur-Werkzeuge). Die App rechnet trotzdem, blendet aber Bereiche aus oder rechnet mit Defaults. | Anschauen, in der Regel beheben. Manche Warnungen sind anlagenbedingt (z. B. ungewöhnlich gute Erzeugung) — dann zur Kenntnis nehmen. |
| ℹ️ | **INFO** (blau) | Hinweis auf optionale Felder oder einen Konfigurations-Aspekt, der für deinen aktuellen Anwendungsfall vielleicht nicht relevant ist. Beispiel: „Wärmepumpe rechnet mit dem allgemeinen Tarif" — zu tun ist da nur etwas, wenn du tatsächlich einen separaten Wärmestrom-Tarif hast. | Lesen, dann entscheiden. Keine Pflicht. |
| ✅ | **OK** (grün) | Prüfung bestanden. | Nichts zu tun. |

### Wann wechseln Severity-Stufen?

Einzelne Befunde haben über Releases hinweg ihre Stufe gewechselt. Beispiele:

- **Counter-Sensoren ohne `state_class`** wurden von INFO → WARNING hochgestuft, weil ohne `state_class` die Reparatur-Werkzeuge in der Energieprofil-Pflege nicht greifen (vorher beruhigend als „Snapshot-Service erfasst's trotzdem" beschrieben). Siehe §4.9.
- **Fehlendes Anschaffungsdatum** wurde mit v4.0.1 von INFO → **ERROR** hochgestuft: ohne das Datum zählt eine Komponente in *jeder* Auswertung über den ganzen Zeitraum mit — auch vor ihrer Anschaffung — und die Amortisationskurve hat keinen Nullpunkt. Der Befund springt per Klick direkt in das Formular der betroffenen Komponente. Siehe §4.3.8.
- **Kategorien werden still übersprungen**, wenn ihre technische Voraussetzung fehlt (HA-LTS nicht erreichbar, MQTT-Import nicht aktiviert) — du siehst dann gar keine Befunde dieser Kategorie, nicht „OK".

> **Daten-Checker kennt kein „Akzeptiert".** Ein Befund lässt sich nicht wegklicken oder als „gesehen" markieren — er verschwindet erst, wenn die Ursache behoben ist (oder, bei anlagenbedingten Warnungen, bewusst bestehen bleibt). Das ist Absicht: der Checker ist Diagnose, kein Aufgaben-Abhaken.
>
> **Umgekehrt gilt die Pflicht auf unserer Seite:** ein Befund, den du **nicht** auflösen kannst, ist ein Fehler im Checker und keine Aufgabe für dich. Entweder die Bedingung ist zu weit gefasst (Beispiel: bis v4.0.6 verlangte der Checker von einer **Split-Klimaanlage** einen Wärmemengenzähler, den es dort gar nicht gibt — §4.6), oder der Text muss sagen, **was ohne Handlung gilt**. Ein paar INFO-Hinweise bleiben deshalb dauerhaft stehen und sind trotzdem in Ordnung — sie sind mit dieser Auskunft formuliert (§4.1 Systemverluste, §4.2 WP-Tarif und Ladetarif). Wenn dir ein Hinweis begegnet, den keine Eingabe abstellt und der auch nicht erklärt, warum das so bleiben darf: **melden**, das ist ein Bug.

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
| 6 | Energieprofil – Zähler-Abdeckung | greift (Zuordnung zu HA-Entitäten `sensor.…`) | greift (Zuordnung zu MQTT-Topics) |
| 7 | Energieprofil – Plausibilität | greift | greift |
| 8 | MQTT-Topic-Abdeckung | nur wenn MQTT-Import aktiv | nur wenn MQTT-Import aktiv |
| 9 | Sensor-Mapping – HA-Statistics | greift | **wird übersprungen** (keine HA-LTS verfügbar) |

### Was bedeutet „wird übersprungen"?

- **Stiller Skip:** Die Kategorie erscheint gar nicht in der Ergebnisliste — keine Sektion, keine Meldung. So bleibt die Übersicht für Nicht-Betroffene aufgeräumt.
  - *MQTT-Topic-Abdeckung* (§4.8) bei nicht aktiviertem MQTT-Import.
  - *Sensor-Mapping HA-Statistics* (§4.9) wenn keine Datenquellen-Zuordnung mit HA-Sensoren vorhanden ist.
- **INFO-Skip:** Die Kategorie erscheint mit einem einzelnen INFO-Eintrag, der den Grund des Überspringens erklärt.
  - *Sensor-Mapping HA-Statistics* (§4.9) bei Standalone, weil HA-Long-Term-Statistics nicht erreichbar sind.
  - *MQTT-Topic-Abdeckung* (§4.8) wenn der MQTT-Import aktiviert ist, der Subscriber aber nicht läuft.

### Beziehung zu Datenquellen-Zuordnung und HA/MQTT

Im **HA Add-on** liefern Sensoren ihre Werte über zwei Kanäle: den aktuellen Zustand (`state`, für Live-Anzeigen) und Long-Term-Statistics (LTS, für Monatswerte und Reparatur-Werkzeuge). Kategorie 9 prüft, ob beide Kanäle für die zugeordneten HA-Sensoren verfügbar sind.

Im **Standalone-Betrieb** kommen die Werte über MQTT (`eedc/<anlage>/…`-Topics) oder Connector-Pulls. HA-LTS gibt es nicht; dafür greift Kategorie 8, die die MQTT-Topic-Abdeckung gegen die `field_definitions.py`-Erwartung prüft. Beide Kategorien lösen dasselbe Grundproblem („Zuordnung passt nicht zur Realität") in der jeweiligen Welt.

> **Wo die Zuordnung entsteht:** Welche Quelle (HA-Sensor / MQTT / Connector) welches Feld speist, legst du zentral unter [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) fest — die feld-zentrische Zuordnungs-Fläche hat die früheren getrennten Assistenten „Sensor-Mapping" und „MQTT-Inbound" abgelöst. Die Verbindungen (HA-Token, MQTT-Broker) richtest du unter [Einstellungen → Integration](HANDBUCH_EINSTELLUNGEN.md#6-integration) ein.

---

## 4. Kategorien im Detail

### 4.1 Stammdaten

**Was wird geprüft:** Pflicht-Stammdaten der Anlage, kWp-Konsistenz zwischen Anlage und PV-Modul-Komponenten, optionale Felder für PVGIS und Community-Vergleich, sowie Performance-Ratio-Plausibilität gegenüber PVGIS (sobald genug Historie vorliegt).

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Installationsdatum nicht gesetzt** | ⚠️ WARNING | Wird zur Bestimmung des erwarteten Monatsdaten-Zeitraums benötigt. Ohne Datum kann der Checker nicht sagen, welche Monate erfasst sein sollten. | Einstellungen → Stammdaten → Anlage → Installationsdatum eintragen. |
| **Anlagenleistung fehlt oder ist 0** | ❌ ERROR | Leistung in kWp ist Bezugsgröße für sämtliche Soll-/Ist-Vergleiche und PVGIS-Plausibilität. | Einstellungen → Stammdaten → Anlage → Leistung in kWp eintragen. Der Wert sollte mit der Summe der PV-Modul-Komponenten übereinstimmen (siehe nächste Zeile). |
| **Keine Koordinaten hinterlegt** | ℹ️ INFO | Koordinaten werden nur für die PVGIS-Solarprognose benötigt. Ohne sie funktionieren PV-Auswertungen mit dynamischer Performance-Ratio nicht; statische Plausibilität bleibt aktiv. | Einstellungen → Stammdaten → Anlage → Koordinaten setzen (oder „Aus Adresse ermitteln"). |
| **Kein Standort hinterlegt (Ort/PLZ)** | ℹ️ INFO | Wird für den Community-Benchmark-Vergleich nach Region benötigt. Ohne Ort/PLZ teilst du keine regionalen Vergleichswerte. | Einstellungen → Stammdaten → Anlage → Ort oder PLZ setzen. |
| **Keine PV-Module als Komponente angelegt** | ❌ ERROR | Ohne PV-Modul-Komponenten fehlen Erzeugungsdaten in der Aufschlüsselung. (Sonderfall: nur Balkonkraftwerk → INFO statt ERROR.) | Einstellungen → Komponenten → PV-Module hinzufügen. |
| **Nur Balkonkraftwerk, keine PV-Module angelegt** | ℹ️ INFO | BKW-only Setup. PVGIS-Prognose und String-Vergleich sind nicht verfügbar, alles andere funktioniert. | Keine Aktion nötig — Hinweis dokumentiert die Einschränkung. |
| **PV-Module kWp stimmt nicht mit Anlagenleistung überein** | ⚠️ WARNING | Summe `leistung_kwp` aller aktiven PV-Modul- und BKW-Komponenten weicht > 0,1 kWp von `Anlagenleistung` ab. Verfälscht alle Soll-Werte. | Entweder die Anlagen-Stammdaten an die Modulsumme anpassen, oder die Modul-Komponenten vervollständigen. |
| **PVGIS-Systemverluste ggf. zu hoch (X %)** | ℹ️ INFO | Ø Performance Ratio (IST/PVGIS) > 1,1 über mindestens 6 Monate — die Anlage produziert systematisch über der Prognose. Der Verlust-Wert (Standard 14 %) ist eine **Annahme der Prognose**, keine Messung. | Einstellungen → Solarprognose → *Neue Prognose abrufen* → Systemverluste senken (z. B. 10 % statt 14 %) → **„Speichern & Aktivieren"**. Ohne neuen Abruf ändert sich nichts — die Monatswerte der Prognose sind gespeichert. **Folge:** das SOLL steigt, deshalb sinken Performance Ratio und SOLL-Erfüllung in *Prognose vs. IST* und im Jahresbericht; **die IST-Werte ändern sich nicht**. Umkehrbar: die bisherige Prognose bleibt in der Historie und lässt sich wieder aktivieren. Erst nach mindestens einem Sommer mit verlässlicher IST-Erfassung sinnvoll — die Prognose bewusst als konservative Untergrenze zu behalten ist ebenfalls in Ordnung. |
| **Installationsdatum vorhanden / Anlagenleistung: X kWp / PV-Module: X kWp (N Modul-Gruppen)** | ✅ OK | Pflichtfelder gesetzt und konsistent. | – |

> **Hinweis:** Die früheren Felder „Ausrichtung" und „Neigung" am Anlage-Modell werden seit der Umstellung auf PV-Modul-Komponenten nicht mehr geprüft — diese Werte gehören jetzt pro Modul-String an die jeweilige Komponente (siehe [HANDBUCH_EINSTELLUNGEN.md §3](HANDBUCH_EINSTELLUNGEN.md#3-komponenten)).

---

### 4.2 Strompreise

**Was wird geprüft:** Vorhandensein mindestens eines allgemeinen Tarifs, Lücken zwischen Tarif-Zeiträumen ab Installationsdatum, Existenz von Spezialtarifen für vorhandene WP- bzw. Lade-Komponenten sowie Plausibilität der Preisangaben.

> **Die beiden Spezialtarif-Hinweise sind INFO und bleiben bei Einheitstarif dauerhaft stehen.** Ob jemand einen Spezialtarif *hat*, lässt sich in den Daten nicht von „noch nicht eingetragen" unterscheiden — deshalb sagen beide Hinweise stattdessen, **womit eedc ohne sie rechnet** (allgemeiner Tarif). Sie sind Auskunft, keine Aufgabe.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Kein Strompreis vorhanden** | ❌ ERROR | Es gibt keinen einzigen Tarif mit Verwendung *allgemein*. Finanz-Auswertungen, ROI-Berechnungen und Monatsabschluss greifen ins Leere. | Einstellungen → Stammdaten → Strompreise → Tarif anlegen mit Arbeitspreis und Einspeisevergütung. |
| **Strompreis-Lücke: TT.MM.JJJJ bis TT.MM.JJJJ** | ⚠️ WARNING | Zwischen Installationsdatum und erstem Tarif (oder zwischen aufeinanderfolgenden Tarifen) klafft ein nicht abgedeckter Zeitraum. Für diese Monate fehlen Strompreise und damit Kostenrechnung. | Einstellungen → Stammdaten → Strompreise → Tarif für den Lückenzeitraum anlegen, oder den vorhandenen Tarif rückwirkend gültig machen. |
| **Wärmepumpe rechnet mit dem allgemeinen Tarif** | ℹ️ INFO | Eine aktive Wärmepumpe ist vorhanden, aber kein Tarif mit Verwendung *waermepumpe* — der WP-Strom wird deshalb mit dem allgemeinen Arbeitspreis bewertet. *(Hieß bis v4.0.6 „Kein WP-Spezialtarif hinterlegt".)* | Nur wenn du einen eigenen Wärmestrom-Tarif hast (§14a, HT/NT, eigener Zähler): Einstellungen → Stammdaten → Strompreise → Tarif anlegen, Verwendung *Wärmepumpe*. **Bei Einheitstarif ist nichts zu tun** — die Rechnung stimmt bereits, der Hinweis bleibt als Information stehen und lässt sich nicht abstellen (siehe Kasten in §2). |
| **Kein Ladetarif hinterlegt** | ℹ️ INFO | Aktives E-Auto oder aktive Wallbox vorhanden, aber kein Tarif mit Verwendung *wallbox*. Ohne ihn rechnet eedc die Ladung mit dem allgemeinen Tarif. *(Der Hinweis fragte bis v4.0.4 nach einer Verwendung „e-auto", die es nie gab — er war damit unerfüllbar.)* | Nur bei separatem Ladetarif: Strompreis mit Verwendung *Wallbox* anlegen — das ist die Verwendung, die beide Dashboards lesen. Sonst nichts zu tun. |
| **Arbeitspreis ungewöhnlich: X,X ct/kWh (Tarifname)** | ⚠️ WARNING | Wert liegt außerhalb des erwarteten Bereichs 5–80 ct/kWh — typischerweise Eingabefehler (Komma vs. Punkt, ct vs. €/kWh). | Einstellungen → Stammdaten → Strompreise → Tarif öffnen, Arbeitspreis prüfen. |
| **Einspeisevergütung ungewöhnlich: X,X ct/kWh (Tarifname)** | ⚠️ WARNING | Wert außerhalb 0–30 ct/kWh. Negative Werte oder zweistellige Vergütungen sind seit den 2010er Jahren untypisch. | Einstellungen → Stammdaten → Strompreise → Tarif öffnen, Vergütung prüfen. Bei dynamischen Vergütungsmodellen (Direktvermarktung) eine sinnvolle Schätzung eintragen. |
| **N Strompreis-Tarif(e) vorhanden** | ✅ OK | Mindestens ein allgemeiner Tarif vorhanden — Anzahl ist informativ. | – |

---

### 4.3 Investitionen

**Was wird geprüft:** Pro aktive Komponente werden typ-spezifische Pflicht- und Plausibilitäts-Parameter geprüft, anschließend für jeden Komponententyp die Vollständigkeit der monatlichen Verbrauchs- bzw. Erzeugungs-Daten ab Anschaffungsdatum. Allgemeine ROI-Parameter (Anschaffungsdatum, -kosten) werden für alle Typen geprüft.

> **Lesart der „Beheben"-Spalten:** Die meisten Befunde dieser Kategorie führen direkt nach *Einstellungen → Komponenten → \[Komponente\] öffnen*. Die Spalte nennt nur den fehlenden Parameter konkret. Fehlende Monatswerte führen zum Monatsdaten-Formular unter *Einstellungen → Daten → Monatsdaten*.

#### 4.3.1 PV-Module

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Leistung (kWp) fehlt** | ⚠️ WARNING | Ohne `leistung_kwp` greift die kWp-Konsistenzprüfung in §4.1 nicht und PVGIS-Soll pro String fehlt. | Komponente öffnen, Leistung in kWp eintragen. |
| **\[Name\]: Ausrichtung/Neigung fehlt** | ℹ️ INFO | Wird für PVGIS-Solarprognose pro String benötigt. Ohne sie nutzt die Prognose Anlagen-Defaults. | Komponente öffnen, Ausrichtung (Süd/Ost/West) und Neigung in Grad eintragen. |

**PV-Erzeugung wird anlagenweit geprüft, nicht pro Modul.** Ein einzelner Gesamtwert deckt alle Strings ab (er füllt zur Lesezeit die Lücken, verteilt nach kWp) — eine Prüfung pro Modul meldete deshalb „fehlt" für jeden String, obwohl die Anlage vollständig gepflegt ist. Vier Zustände je Monat:

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **PV-Erzeugung: Monatsdaten vollständig (N Monate)** | ✅ OK | Jedes im Monat aktive Modul hat einen **eigenen** Messwert. | – |
| **PV-Erzeugung über kWp-Anteil geschätzt in N Monat(en)** | ℹ️ INFO | Mindestens ein Modul hat keinen eigenen Wert; für **diese** Module wird der Rest des Gesamtwerts (Gesamtwert − Summe der gemessenen) anteilig nach Nennleistung verteilt. Bereits gemessene Module behalten ihren Messwert. Die Zahlen stimmen in der Summe, die Pro-String-Genauigkeit ist eingeschränkt — deshalb nennen die String-Sichten in diesen Monaten bewusst keinen besten/schwächsten String. | Kein Mangel. Wer echte Pro-String-Werte will, gibt jedem Modul einen eigenen Erzeugungs-Sensor (Einstellungen → Datenquellen). |
| **PV-Erzeugung unvollständig in N Monat(en)** | ⚠️ WARNING | Nur ein **Teil** der Strings ist erfasst und es gibt **keinen** Gesamtwert zum Verteilen. Die Pro-Modul-Sicht behält ihre Messwerte, die Anlagen-Summe bleibt für diese Monate bewusst leer — eine Teilsumme als „Gesamt-PV" wäre systematisch zu klein. | Entweder die fehlenden Module nachtragen **oder** den Monats-Gesamtwert eintragen. |
| **PV-Erzeugung fehlt in N Monat(en)** | ❌ ERROR | Für diese Monate gibt es **gar keine** PV-Quelle — weder Pro-Modul-Werte noch einen Gesamtwert. | Wo ein PV-Sensor zugeordnet ist: **Einstellungen → Datenverwaltung → Import aus HA-Statistik** oder der **Monatsabschluss** des betreffenden Monats — beide schreiben die Werte je Modul. Ohne zugeordneten Sensor von Hand nachtragen. |

> **Nicht die Reparatur-Werkbank dafür nehmen.** „Tag neu aggregieren" / „Mehrere Tage neu aggregieren" (§4.7, §5.6) baut das **stündliche Energieprofil** neu — es schreibt weder den Monats-Gesamtwert noch die Monatswerte je Komponente. Für fehlende **Monats**-PV-Werte sind die beiden oben genannten Wege die richtigen.
>
> **Warum ein Monat ohne dein Zutun leer sein kann:** Eine Start-Migration früherer Versionen hat den Gesamtwert bei Anlagen mit eigenem Balkonkraftwerk-Sensor mitgeleert. Details und was sich retten lässt: [Was ist neu](WAS-IST-NEU.md).

#### 4.3.2 Balkonkraftwerk

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Leistung (Wp) fehlt** | ⚠️ WARNING | Ohne `leistung_wp` (× Anzahl) ist die kWp-Summe der Anlage unvollständig. | Komponente öffnen, Wp pro Modul und Modulanzahl eintragen. |
| **\[Name\]: PV-Erzeugung fehlt in N Monat(en)** | ⚠️ WARNING | Wie PV-Module: `pv_erzeugung_kwh` fehlt in den genannten Monaten. | Monatsdaten nachtragen. |

#### 4.3.3 Speicher

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Kapazität (kWh) fehlt** | ⚠️ WARNING | `kapazitaet_kwh` ist Bezugsgröße für Vollzyklen, Wirkungsgrad-Berechnung und Live-SoC-Skalierung. | Komponente öffnen, Brutto-Kapazität in kWh eintragen. |
| **\[Name\]: Arbitrage aktiv, aber Ø Ladepreis fehlt** | ⚠️ WARNING | `nutzt_arbitrage` ist gesetzt, aber `lade_durchschnittspreis_cent` fehlt. Arbitrage-Einsparung kann nicht berechnet werden. | Komponente öffnen, durchschnittlichen Ladepreis (z. B. negative Börsenpreise) eintragen. |
| **\[Name\]: Arbitrage aktiv, aber Ø Entladepreis fehlt** | ⚠️ WARNING | Analog zum Ladepreis: ohne `entlade_vermiedener_preis_cent` kein Arbitrage-Erlös berechenbar. | Vermiedenen Entladepreis (z. B. Endkundentarif zur Spitzenlastzeit) eintragen. |
| **\[Name\]: Speicher-Ladung fehlt in N Monat(en)** | ⚠️ WARNING | `ladung_kwh` fehlt in den genannten Monaten — Vollzyklen und Wirkungsgrad lassen sich für diese Monate nicht berechnen. | Monatsdaten nachtragen. |

#### 4.3.4 E-Auto (privat)

> Dienstwagen (`ist_dienstlich`) werden von dieser Prüfung übersprungen — kein PV-Bezug, kein Investment-ROI.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Fahrleistung/Verbrauch fehlt** | ℹ️ INFO | Weder `km_jahr` noch `verbrauch_kwh_100km` gesetzt. Einsparungs-Berechnung gegenüber Verbrenner ist nicht möglich. | Komponente öffnen, Jahres-Fahrleistung und/oder Verbrauch eintragen. |
| **\[Name\]: Alternativkosten (Verbrenner) fehlen** | ⚠️ WARNING | `anschaffungskosten_alternativ` fehlt. ROI gegenüber Verbrenner-Alternative wird ohne diesen Wert nicht berechnet. | Komponente öffnen, geschätzte Anschaffungskosten eines vergleichbaren Verbrenners eintragen. |
| **\[Name\]: V2H aktiv, aber Entladepreis fehlt** | ℹ️ INFO | `nutzt_v2h` ist gesetzt, aber `v2h_entlade_preis_cent` fehlt. V2H-Einsparung wird nicht berechnet. | Vermiedenen Entladepreis eintragen (analog Speicher-Arbitrage). |
| **\[Name\]: Ladung PV fehlt in N Monat(en)** | ℹ️ INFO | `ladung_pv_kwh` fehlt — Anteil PV-Ladung am Gesamt-Ladestrom unbekannt. Geringere Severity als andere Pflichtfelder, weil V2H/Wallbox-Aufschlüsselung optional ist. **Hinweis:** Bei vorhandener Wallbox liegt die Heimladung kanonisch dort — die Heim-Felder am E-Auto sind dann erwartungsgemäß leer und kein Mangel. | Ohne Wallbox: Monatsdaten nachtragen. Mit Wallbox: an der Wallbox erfassen (Loadpoint-Sensor), nicht am E-Auto. |

#### 4.3.5 Wallbox

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Ladeleistung (kW) fehlt** | ⚠️ WARNING | Weder `max_ladeleistung_kw` noch `leistung_kw` (Legacy) gesetzt. Auslegung und Lade-Profile lassen sich nicht plausibilisieren. | Komponente öffnen, max. Ladeleistung in kW eintragen. |
| **\[Name\]: Ladung gesamt fehlt in N Monat(en)** | ℹ️ INFO | `ladung_kwh` fehlt in den genannten Monaten. | Monatsdaten nachtragen. |

#### 4.3.6 Wechselrichter

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Leistung (kW) fehlt** | ⚠️ WARNING | Weder `max_leistung_kw` noch `leistung_ac_kw` (Legacy) gesetzt. WR-Auslastungs-Auswertung und Cockpit-Kopf rechnen ohne diesen Wert nicht. | Komponente öffnen, AC-Nennleistung des Wechselrichters in kW eintragen. |

#### 4.3.7 Wärmepumpe

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Alternativkosten (Gas-/Ölheizung) fehlen** | ⚠️ WARNING | `anschaffungskosten_alternativ` fehlt. ROI gegenüber konventioneller Heizung wird nicht berechnet. | Komponente öffnen, geschätzte Anschaffungskosten einer vergleichbaren Gas-/Ölheizung eintragen. |
| **\[Name\]: JAZ nicht gesetzt** | ⚠️ WARNING | Effizienz-Modus ist *Gesamt-JAZ*, aber `jaz` fehlt. COP-Berechnung der Heizenergie geht nicht. | Komponente öffnen, Jahresarbeitszahl eintragen (typischer Bereich 2,5–4,5 Luft-WP, 3,5–5,5 Sole-WP). |
| **\[Name\]: JAZ unplausibel (X,X)** | ⚠️ WARNING | `jaz` liegt außerhalb 1,5–7,0. Wahrscheinlich Eingabefehler (Komma vs. Punkt, Prozent-Wert statt Faktor). | Wert prüfen und korrigieren. |
| **\[Name\]: SCOP-Werte fehlen (Modus: EU-Label SCOP)** | ⚠️ WARNING | Effizienz-Modus *SCOP*, aber `scop_heizung` und/oder `scop_warmwasser` fehlen. Einsparung wird nicht berechnet. | Werte vom EU-Label / Datenblatt der WP eintragen. |
| **\[Name\]: COP-Werte fehlen (Modus: Getrennte COPs)** | ⚠️ WARNING | Modus *Getrennte COPs*, aber `cop_heizung` und/oder `cop_warmwasser` fehlen. | Beide Werte eintragen oder Modus auf JAZ wechseln. |
| **\[Name\]: Alter Energiepreis nicht gesetzt** | ℹ️ INFO | `alter_preis_cent_kwh` fehlt — Einsparungs-Berechnung gegen Gas/Öl nutzt Default-Preis. | Aktuellen Gas-/Ölpreis in ct/kWh eintragen für realistische Einsparung. |
| **\[Name\]: Heizwärmebedarf nicht gesetzt** | ℹ️ INFO | `heizwaermebedarf_kwh` fehlt — Jahres-Einsparungsschätzung greift auf Defaults zurück. | Geschätzten Jahres-Heizwärmebedarf in kWh eintragen (z. B. aus Energieausweis). |
| **\[Name\]: Strom Heizen/Warmwasser fehlt in N Monat(en)** | ⚠️ WARNING | Bei aktivierter `getrennte_strommessung`: `strom_heizen_kwh` und `strom_warmwasser_kwh` fehlen für die genannten Monate. | Monatsdaten nachtragen mit getrennten Werten. |
| **\[Name\]: Stromverbrauch fehlt in N Monat(en)** | ⚠️ WARNING | Ohne getrennte Strommessung: `stromverbrauch_kwh` fehlt. | Monatsdaten nachtragen. |
| **\[Name\]: Heizenergie fehlt in N Monat(en)** | ℹ️ INFO | `heizenergie_kwh` fehlt — JAZ und COP-Vergleich für die Monate nicht möglich, Stromverbrauch bleibt aber erfasst. | Wenn Wärmemengenzähler vorhanden: Werte nachtragen; sonst akzeptieren. |

> **Split-Klimaanlagen sind ausgenommen.** Ist die Wärmepumpenart **Luft-Luft (Klimaanlage)** eingetragen, verlangt der Checker weder die monatliche Heizwärme noch die Tages-Zusatzzähler aus §4.6: beides setzt einen Wärmemengenzähler voraus, den solche Geräte praktisch nie haben, und einen Warmwasserkreis gibt es dort gar nicht. Der **Stromverbrauch** bleibt Pflicht, die Stromauswertung funktioniert vollständig; JAZ/COP zeigen „—" statt einer Scheinzahl. Eine Wärmepumpe **ohne** eingetragene Art gilt als klassische Wärmepumpe — eine fehlende Angabe schaltet die Erwartung nicht ab.
>
> **Ebenfalls ausgenommen: die drei Hinweise zum Gas-/Öl-Vergleich** — *Alternativkosten (Gas-/Ölheizung) fehlen*, *Alter Energiepreis nicht gesetzt* und *Heizwärmebedarf nicht gesetzt*. Sie versorgen ausschließlich die Ersparnis-Rechnung gegenüber einer ersetzten Heizung, und die wird für Klimaanlagen nicht mehr durchgeführt (siehe *Auswertungen → ROI*: die Zeile steht dort mit „—" und dem Vermerk *nicht bewertet*). Der Hinweis zum Heizwärmebedarf wäre für Klimaanlagen sogar **unauflösbar**, weil das Feld im Komponenten-Formular für diese Art gar nicht mehr angeboten wird — genau der Fall, den §2 als Fehler auf unserer Seite beschreibt.

#### 4.3.8 Allgemein (alle Komponententypen)

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Anschaffungsdatum fehlt** | ❌ ERROR | Das Datum ist die **Grenze jeder Auswertung** — ohne es zählt die Komponente auch für Zeiträume **vor** der Anschaffung mit — und der Nullpunkt der Amortisationskurve. Für neue Komponenten ist es seit v4.0.1 Pflichtfeld; dieser Befund betrifft den Bestand. *(Bis v4.0.0 nur ℹ️ INFO.)* | Der „Beheben"-Link springt direkt in das Formular **dieser** Komponente. |
| **\[Name\]: Anschaffungskosten fehlen** | ℹ️ INFO | `anschaffungskosten_gesamt` fehlt. ROI- und Amortisations-Berechnung greift mit 0 €. | Komponente öffnen, Brutto-Anschaffungskosten eintragen. |
| **\[Name\]: Monatsdaten vollständig (N Monate)** | ✅ OK | Alle Pflicht-Monatsfelder ab Anschaffungsdatum sind erfasst. | – |
| **Keine aktiven Komponenten vorhanden** | ℹ️ INFO | Anlage hat keine aktive Komponente. Cockpit, ROI und Aufschlüsselungen sind leer. | Einstellungen → Komponenten → mindestens PV-Module oder Balkonkraftwerk anlegen. |

#### 4.3.9 E-Auto + Wallbox – Heimladungs-Pflegekonflikt

> Greift nur, wenn **sowohl** eine (private) E-Auto- **als auch** eine Wallbox-Komponente existiert. Die Heimladung ist kanonisch an der Wallbox geführt; die Migration verschiebt bestehende E-Auto-Heimladung automatisch dorthin. Diese Prüfung flaggt die **Reste**, die nicht verlustfrei auflösbar waren — also Monate, in denen beide Seiten weiterhin Heimladung tragen.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **E-Auto- und Wallbox-Komponente werden parallel gepflegt** | ℹ️ INFO | In mehreren der letzten Monate tragen sowohl E-Auto als auch Wallbox nennenswerte, ähnlich große Heimladung. Beide messen meist denselben Stromfluss aus zwei Perspektiven — die doppelte Pflege ist überflüssig. | Nur **eine** Quelle pflegen: bei vorhandener Wallbox die Wallbox; die Heim-Felder am E-Auto leer lassen. |
| **Pflege-Konflikt: E-Auto- und Wallbox-PV-Anteil weichen voneinander ab** | ⚠️ WARNING | Zusätzlich weicht der PV-Anteil beider Seiten um mehr als 10 % ab, obwohl sie denselben Stromfluss messen sollten. Indiz für echte Doppelzählung bzw. widersprüchliche Daten (z. B. verirrte Streudaten auf der falschen Komponente). | Bewusst entscheiden, welche Quelle die Wahrheit liefert (in der Regel die Wallbox), und die andere Seite leeren. |

---

### 4.4 Monatsdaten – Vollständigkeit <a name="44-monatsdaten--vollstaendigkeit"></a>

**Was wird geprüft:** Welche Monate zwischen Installationsdatum (oder erstem Monatsdaten-Eintrag) und Vormonat sind in der Datenbank erfasst? Der laufende Monat wird ausgeklammert, weil er noch nicht abgeschlossen ist. Das Ergebnis fließt zusätzlich in den Fortschrittsbalken „Monatsdaten-Abdeckung" oben ein.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Keine Monatsdaten vorhanden** | ⚠️ WARNING | Es gibt keinen einzigen Monatsdaten-Eintrag. Cockpit, Aussicht, ROI und Community-Vergleich sind leer. | Monatsdaten-Formular für den ersten Monat ab Installation öffnen (Einstellungen → Daten → Monatsdaten), oder per CSV-Import bestehende Daten einlesen. |
| **MM/JJJJ fehlt** | ⚠️ WARNING | Konkreter Monat zwischen Installationsdatum und Vormonat ist nicht erfasst. Wird einzeln gelistet (max. 12 Monate), darüber hinaus zusammengefasst. | Der „Beheben"-Link öffnet das Monatsdaten-Formular direkt für den fehlenden Monat. |
| **... und N weitere Monate fehlen** | ⚠️ WARNING | Mehr als 12 fehlende Monate — Sammelmeldung, um die Liste nicht zu überschwemmen. | Einstellungen → Daten → Monatsdaten öffnen, dort Monate nachtragen. Bei vielen Lücken: Statistik-Import nutzen, der mehrere Monate auf einmal aus HA-Long-Term-Statistics holt. |
| **Alle N Monate vollständig** | ✅ OK | Vom Installationsdatum bis Vormonat ist jeder Monat erfasst. | – |

> **Hinweis zur Abdeckungs-KPI:** Der Prozentwert oben bezieht sich auf erwartete Monate, nicht auf Datenfelder *innerhalb* eines Monats. Ein zu 100 % abgedeckter Monatsdaten-Stand kann trotzdem unvollständige Pflichtfelder enthalten — das prüft §4.5.

---

### 4.5 Monatsdaten – Plausibilität <a name="45-monatsdaten--plausibilitaet"></a>

**Was wird geprüft:** Pro vorhandenem Monatsdaten-Eintrag werden Pflichtfelder, Werte-Ranges, logische Konsistenz und (sobald verfügbar) Vergleich gegen Vorjahresmonat sowie PVGIS-Prognose geprüft. Die PV-Maximum-Prüfung nutzt eine **dynamische Obergrenze** aus PVGIS-Soll × aktueller Performance Ratio × 1,45 (sobald 6+ Monate Historie verfügbar) — sonst statisches Maximum nach Monat und kWp. Der 1,45-Faktor deckt die natürliche Monatsvariation ab.

#### Pflichtfelder

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: Einspeisung nicht erfasst** | ❌ ERROR | Kernfeld `einspeisung_kwh` ist `NULL`. Eigenverbrauch und Autarkie nicht berechenbar. | Monatsdaten öffnen, Einspeisung eintragen. |
| **MM/JJJJ: Netzbezug nicht erfasst** | ❌ ERROR | Kernfeld `netzbezug_kwh` ist `NULL`. Hausverbrauch und Stromkosten nicht berechenbar. | Monatsdaten öffnen, Netzbezug eintragen. |
| **MM/JJJJ: Batterie-Ladung nicht erfasst (Speicher vorhanden)** | ⚠️ WARNING | Aktive Speicher-Komponente vorhanden, aber weder Legacy-Feld `batterie_ladung_kwh` noch neues `InvestitionMonatsdaten.ladung_kwh`. Hausverbrauchs-Berechnung wird falsch. | Monatsdaten öffnen, Batterie-Ladung in der Speicher-Komponente eintragen. |
| **MM/JJJJ: Batterie-Entladung nicht erfasst (Speicher vorhanden)** | ⚠️ WARNING | Analog zur Ladung — `entladung_kwh` fehlt. | Monatsdaten öffnen, Batterie-Entladung eintragen. |

#### Werte-Plausibilität

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: \[Feld\] ist negativ (X,X kWh)** | ❌ ERROR | Einspeisung, Netzbezug, PV-Erzeugung oder Batteriewerte sind < 0. Energiemengen können physikalisch nicht negativ sein. | Monatsdaten öffnen, Vorzeichen-/Eingabefehler korrigieren. Bei Sensor-Drift: Zählerstand-Differenz prüfen. |
| **MM/JJJJ: PV-Erzeugung ungewöhnlich hoch (X kWh)** | ⚠️ WARNING | Wert übersteigt das dynamische Maximum (PVGIS × max(PR; 1,0) × 1,45) bzw. das statische Maximum (kWp × Monatsfaktor). Details nennen den verwendeten Schwellwert. | Wert prüfen — Eingabefehler? Falscher Multiplikator? Falls echt: vermutlich war der Monat außergewöhnlich strahlungsreich, dann WARNING ignorieren. |
| **MM/JJJJ: Einspeisung (X kWh) > PV-Erzeugung (Y kWh)** | ❌ ERROR | Logisch unmöglich — du kannst nicht mehr einspeisen als erzeugen. | Beide Werte prüfen. Häufige Ursache: PV-Erzeugung wurde nur teilweise erfasst (z. B. ein String fehlt in den Komponenten), oder Einspeisung enthält fälschlich Bezug. |
| **MM/JJJJ: mehr PV verwendet als erzeugt?** | ⚠️ WARNING | Einspeisung **plus** die aus PV geladene Speichermenge ist größer als die Erzeugung des Monats. Beides kommt aus derselben Quelle — zusammen kann es nicht mehr sein, als die Anlage geliefert hat. Bewusst als **Frage**: die häufigste Ursache ist kein Messfehler. | In dieser Reihenfolge prüfen: **(1)** Wird der Speicher auch aus dem Netz geladen (Arbitrage, Notladung), ohne dass das Feld **Ladung aus Netz** gepflegt ist? Dann stimmt die Energie, nur die Zuordnung fehlt. **(2)** Ist die Erzeugung zu niedrig erfasst (ausgesetzter String-Sensor)? **(3)** Sind Einspeisung und Netzbezug vertauscht — dann meldet die Zeile darüber meist zusätzlich. Kleine Abweichungen (bis 2 % der Erzeugung, mindestens 5 kWh) bleiben still. |
| **MM/JJJJ: Einspeisung und Netzbezug sind beide 0** | ⚠️ WARNING | Beide Kernfelder sind 0 — wahrscheinlich fehlende Daten, kein echter Null-Verbrauch. | Monatsdaten öffnen, Werte eintragen. Falls die Anlage tatsächlich den ganzen Monat aus war (Umzug, Defekt): WARNING akzeptieren. |
| **MM/JJJJ: \[Feld\] > 3× Vorjahr (X vs. Y kWh)** | ⚠️ WARNING | Einspeisung oder Netzbezug ist mehr als dreimal so groß wie der gleiche Monat im Vorjahr (Vorjahr > 50 kWh). Häufig Eingabefehler (Faktor 10) oder Zählerwechsel ohne Reset. **Zwei Ausnahmen bei der Einspeisung:** der Vergleichsmonat liegt vor oder in der Inbetriebnahme, **oder** die installierte Erzeugerleistung ist zwischen beiden Monaten um mindestens 10 % gewachsen (Anlagen-Ausbau) — dann wird die Prüfung für dieses Monatspaar ausgesetzt. Beim **Netzbezug** greift die Ausbau-Ausnahme bewusst nicht: der sinkt mit mehr PV und steigt mit neuen Verbrauchern. | Werte beider Monate prüfen. Bei echter Veränderung (neue Wallbox, neue WP): WARNING akzeptieren. |

#### Energiebilanz

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: Energiebilanz ergibt negativen Hausverbrauch (X,X kWh)** | ❌ ERROR | `PV − Einspeisung + Netzbezug + Bat.Entladung − Bat.Ladung` ist deutlich negativ (< −0,5 kWh). Logisch unmöglich. Details listen alle Summanden auf. | Häufige Ursache: fehlende Batterie-Daten verzerren die Bilanz. Erst Batterie-Werte vervollständigen, dann erneut prüfen. Wenn weiterhin negativ: PV-Erzeugung oder Einspeisung enthält Eingabefehler. |
| **Keine Auffälligkeiten in den Monatsdaten** | ✅ OK | Alle vorhandenen Monatsdaten haben Pflichtfelder, plausible Werte und konsistente Bilanz. | – |

> **Hintergrund zur PV-Obergrenze:** Mit ≥ 6 Monaten Historie ohne Lücken passt sich die Obergrenze an die tatsächliche Performance der Anlage an. Eine systematisch über PVGIS produzierende Anlage (PR > 1,0) bekommt einen entsprechend höheren Schwellwert. Mindestschwellwert ist immer PVGIS × 1,5 — neue Anlagen ohne genug Historie bleiben damit großzügig im grünen Bereich.

---

### 4.6 Energieprofil – Zähler-Abdeckung <a name="46-energieprofil--zaehler-abdeckung"></a>

> **Variantenhinweis:** Im **HA Add-on** sind die Zähler HA-Entitäten (`sensor.…`) mit `state_class: total_increasing`. Im **Standalone-Betrieb** sind sie kumulative MQTT-Topics (`eedc/<anlage>/inv/<id>/<feld>`). Die Prüflogik ist in beiden Fällen identisch — sie schaut nur, ob in der Datenquellen-Zuordnung pro Komponente ein kWh-Zähler eingetragen ist.

**Was wird geprüft:** Welche kumulativen kWh-Zähler sind in der Datenquellen-Zuordnung der Anlage gesetzt? Ohne diese Zähler bleibt das Energieprofil für die betroffenen Komponenten leer (strikte NULL-Semantik) — und damit auch Prognose-IST, Lernfaktor und die Monatsauswertungen. Live-Anzeigen aus `*_leistung_w` funktionieren weiter, integrieren aber nicht zu Energiemengen.

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
| **Kein Basis-Zähler für: \[Einspeisung, Netzbezug\]** | ⚠️ WARNING | In der Datenquellen-Zuordnung fehlt der Basis-Zähler für Einspeisung und/oder Netzbezug. Ohne diesen bleibt der bilanzielle Hausverbrauch im Energieprofil leer. | Einstellungen → Datenquellen öffnen, im Block *Anlage / Zähler* den kumulativen kWh-Zähler zuordnen. **Wichtig:** den kWh-Zähler wählen, nicht den `*_leistung_w`-Sensor. |
| **N von M Komponenten ohne vollständige kWh-Zähler-Abdeckung** | ⚠️ WARNING | Mindestens eine aktive Komponente hat nicht alle erwarteten kWh-Zähler zugeordnet. Details listen die betroffenen Komponenten und fehlenden Felder. Folgen für diese Komponenten: Prognose-IST, Lernfaktor und Monatsauswertungen bleiben leer. | Einstellungen → Datenquellen öffnen, pro Komponente die fehlenden Zähler zuordnen. Bei Speichern: beide Felder (`ladung_kwh` + `entladung_kwh`) sind nötig. |
| **N Komponente(n) ohne Zusatz-Zähler für Tageswerte** | ℹ️ INFO | Betrifft **zusätzliche** Messstellen, nicht die Abdeckung oben: Wärmepumpe `heizenergie_kwh` / `warmwasser_kwh` (Wärmemengenzähler) sowie `ladung_pv_kwh` an Wallbox bzw. E-Auto. Ohne sie bleiben genau diese Werte in *Cockpit → Tag* auf „—"; die **Monats**auswertungen sind nicht betroffen, dort lassen sich die Werte von Hand pflegen. Bewusst INFO — solche Zähler hat längst nicht jede Anlage. | Wenn vorhanden: Einstellungen → Datenquellen → das jeweilige kWh-Feld zuordnen. Sonst nichts zu tun. |

> **Wer hier ausgenommen ist** — damit der Befund nicht etwas verlangt, das es bei dir nicht geben kann: **Split-Klimaanlagen** (Wärmepumpenart *Luft-Luft*) werden gar nicht gefragt, sie haben weder Wärmemengenzähler noch Warmwasserkreis. Das **E-Auto** wird übersprungen, wenn eine **Wallbox** existiert (dort wird die Heimladung geführt) oder wenn es als **Dienstwagen** markiert ist. Stillgelegte und inaktive Komponenten zählen ohnehin nicht mit.
| **Basis-Zähler (Einspeisung + Netzbezug) gemappt** | ✅ OK | Beide Basis-Zähler zugeordnet. | – |
| **Alle N aktiven Komponenten haben kWh-Zähler gemappt** | ✅ OK | Alle aktiven Komponenten mit erwarteten Zählern sind vollständig zugeordnet. | – |

> **Hinweis:** Diese Kategorie prüft nur das **Vorhandensein** der Zuordnung — ob der Zähler tatsächlich Daten liefert, prüft §4.8 (MQTT-Topic-Abdeckung) bzw. §4.9 (Sensor-Mapping HA-Statistics). Plausibilität der bereits aggregierten Stundenwerte (Counter-Spikes durch Update-Restarts) erfasst §4.7.

---

### 4.7 Energieprofil – Plausibilität <a name="47-energieprofil--plausibilitaet"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten identisch — sie liest ausschließlich die bereits gespeicherten Stundenwerte des `tages_energie_profil`.

**Was wird geprüft:** Enthält das Tagesprofil der letzten 30 Tage Stundenwerte, die physikalisch unmöglich sind? Konkret: `pv_kw` oder `einspeisung_kw` größer als die Anlagen-Nennleistung × 1.5. Tritt typischerweise nach Update-Restarts während des Tages auf, wenn der Counter-Snapshot-Service einen verzerrten kumulativen Wert speichert.

**Schwelle:** `Anlagen-kWp × 1.5`. Eine eindeutige Wahnschwelle — eine Aufdach-PV-Anlage erzeugt selbst bei optimalem Sonnenstand nicht mehr als ~1500 W pro kWp. Werte darüber sind keine Naturereignisse, sondern Rechen-/Snapshot-Artefakte.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Counter-Spike am YYYY-MM-DD: N Stundenwert(e) > X kW** | ⚠️ WARNING | Ein einzelner Tag enthält mindestens eine Stunde, deren `pv_kw` oder `einspeisung_kw` über der Wahnschwelle liegt. Detail-Liste nennt Stunde und Wert. | Einstellungen → Daten → Energieprofil-Pflege → **Reparatur-Werkbank** öffnen, Operation *„Tag neu aggregieren"* wählen und den betroffenen Tag angeben. Der Lauf zieht zuerst die SensorSnapshots des Tages frisch aus HA-Statistics und baut danach das Aggregat neu — beides in einem Schritt. Bei mehreren betroffenen Tagen die Operation *„Mehrere Tage neu aggregieren"* mit dem passenden Von-/Bis-Bereich nutzen. |
| **Keine Counter-Spikes in den letzten 30 Tagen** | ✅ OK | Alle Stundenwerte liegen innerhalb der physikalisch plausiblen Bandbreite. | – |

> **Hinweis:** Ältere Tage (> 30 Tage) werden nicht geprüft, weil dort entweder bereits korrigierte Werte stehen oder sie für die aktuelle Lernfaktor-Basis nicht mehr relevant sind. Wer ältere Tage trotzdem reparieren will, nutzt in der Reparatur-Werkbank *„Mehrere Tage neu aggregieren"* über den entsprechenden Bereich — das Werkzeug greift bis zur HA-LTS-Reichweite zurück.

---

### 4.8 MQTT-Topic-Abdeckung <a name="48-mqtt-topic-abdeckung"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten — aber **nur**, wenn der MQTT-Import bewusst aktiviert ist (Einstellungen → Integration → MQTT-Broker-Verbindung, Schalter *„Daten über MQTT empfangen (Import)"*). Ohne aktivierten Import wird die Kategorie still übersprungen, damit Anwender ohne MQTT sie gar nicht erst sehen.

**Was wird geprüft:** Werden die aus `field_definitions.py` und der Datenquellen-Zuordnung erwarteten MQTT-Topics tatsächlich vom Subscriber empfangen? Diese Kategorie schließt die Lücke zwischen der dynamischen Konsumenten-Seite (Erwartungsliste aus dem eedc-Code) und der statisch hartkodierten Publisher-Seite (HA-Automation, ioBroker, Node-RED). Wenn dort jemand neue Felder vergisst oder Komponenten-IDs nach einem Re-Import nicht nachzieht, läuft die Erwartung gegen die Realität auseinander — diese Kategorie macht's sichtbar.

**Schwellwerte für „veraltet":**

| Topic-Kategorie | Maximales Alter |
|----------------|-----------------|
| Live-Topics (sensorgetrieben) | 2 Minuten |
| Energy-Topics (alle-5-min-Pattern + Puffer) | 10 Minuten |

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MQTT-Import aktiviert, Subscriber läuft jedoch nicht** | ℹ️ INFO | Der Import ist aktiviert, aber der Subscriber konnte nicht starten (z. B. Broker nicht erreichbar, falsche Zugangsdaten). | Einstellungen → Integration → MQTT-Broker-Verbindung öffnen, Broker-Adresse und Zugangsdaten prüfen. Oder den Import-Schalter deaktivieren, wenn keine Live-Daten via MQTT gewünscht. |
| **N MQTT-Topic(s) erwartet, nie empfangen** | ⚠️ WARNING | Subscriber läuft, aber für die genannten Topics liefert noch keine Quelle Daten. Beispiele werden gelistet (max. 6, Rest aggregiert). | Mögliche Ursachen: (a) Publisher-Automation noch nicht eingerichtet — siehe [HANDBUCH_EINSTELLUNGEN.md §7.5 MQTT-Topic zuordnen](HANDBUCH_EINSTELLUNGEN.md#75-ein-mqtt-topic-zuordnen). (b) Komponenten-IDs nach Re-Import nicht in der Automation nachgezogen — die Topic-Struktur enthält die eedc-interne ID. (c) Wenn die Topics gar nicht gebraucht werden: MQTT-Import deaktivieren. |
| **N MQTT-Topic(s) mit veralteten Werten** | ⚠️ WARNING | Topics werden grundsätzlich empfangen, aber älter als der Schwellwert. Beispiele zeigen Topic + Alter in Minuten. | Publisher-Automation prüfen: läuft sie noch? Hat sie ihre Quelle verloren (z. B. Wechselrichter offline)? Bei dauerhaft fehlenden Quellen die Automation aufräumen oder die Datenquellen-Zuordnung anpassen. |
| **Alle N erwarteten MQTT-Topics aktuell empfangen** | ✅ OK | Subscriber läuft, alle erwarteten Topics liefern frische Daten innerhalb der Toleranz. | – |

> **Wichtig zur Skip-Logik:** Wenn der MQTT-Import nicht aktiviert ist, erscheint diese Kategorie gar nicht — nicht „OK", nicht „leer". So bleibt die Daten-Checker-Übersicht für Nutzer ohne MQTT übersichtlich.

---

### 4.9 Sensor-Mapping – HA-Statistics <a name="49-sensor-mapping--ha-statistics"></a>

> **Variantenhinweis:** Diese Kategorie greift nur im **HA Add-on**. Im Standalone-Betrieb gibt es keine HA-Long-Term-Statistics; ein eventuell vorhandener INFO-Befund weist auf den Skip hin. Funktional wird die analoge Drift-Erkennung im Standalone-Betrieb über §4.8 *MQTT-Topic-Abdeckung* abgedeckt.

**Was wird geprüft:** Liefert jeder zugeordnete HA-Sensor tatsächlich Long-Term-Statistics nach Home Assistant? Geprüft werden alle zugeordneten kWh-Felder — Einspeisung, Netzbezug, **PV Erzeugung Gesamt** und die Komponenten-Felder. Reine Live-Felder (W, %, °C) bleiben außen vor, sie lesen den Momentanwert und brauchen keine Statistik. Beim Gesamt-PV-Zähler prüft eedc die **Zuordnung**, nicht ob die Rechnung ihn diesen Monat gerade liest: fällt ein String-Sensor aus, wird er unmittelbar wieder zur einzigen Quelle. Sensoren ohne `state_class` haben keine LTS-Einträge und damit greifen die **Reparatur-Werkzeuge in der Energieprofil-Pflege** (Lücken aus HA-LTS nachfüllen, Tag/Bereich neu aggregieren) nicht — sie lesen alle aus HA-LTS. Live-Anzeigen funktionieren weiter (über `state`), aber jeder Aussetzer im Snapshot-Pfad ist permanent verloren, weil er nicht aus LTS nachgeholt werden kann.

Der Sensor-Picker in den Datenquellen zeigt alle Sensoren ohne harten Filter — damit lassen sich z. B. Nibe-Roh-Counter ohne Metadaten zuordnen, aber genau dieser Spielraum verlangt nach dieser Prüfkategorie. (Der Picker warnt beim Zuordnen bereits vor fehlender Langzeitstatistik — siehe [HANDBUCH_EINSTELLUNGEN.md §7.6](HANDBUCH_EINSTELLUNGEN.md#76-validierung--probleme-je-feld).)

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **HA Long-Term-Statistics nicht erreichbar — Prüfung übersprungen** | ℹ️ INFO | eedc kann HA-LTS gerade nicht abfragen (z. B. Standalone-Betrieb, oder HA-API zwischenzeitlich nicht erreichbar). Die Kategorie wird übersprungen. | Standalone: keine Aktion nötig — die Kategorie ist hier irrelevant. HA Add-on: HA-Verbindung prüfen ([Einstellungen → Integration → HA-Verbindung](HANDBUCH_EINSTELLUNGEN.md#62-ha-verbindung)). |
| **N kWh-Sensor(en) nicht in HA-Long-Term-Statistics** | ⚠️ WARNING | Mindestens ein zugeordneter kWh-Sensor (z. B. für *Einspeisung*, *PV Erzeugung Gesamt* oder *WP-Stromverbrauch*) zeigt auf einen Sensor ohne `state_class`. Reparatur-Werkzeuge greifen für diese Felder nicht; vergangene Monate bleiben leer, wenn der Snapshot-Pfad eine Lücke hatte. | Bevorzugt: einen **Verbrauchszähler-Helfer** auf diesen Sensor legen (§5.1) — **ohne Zyklus**. Alternativ: einen anderen Sensor wählen, der bereits LTS liefert. Siehe [HANDBUCH_EINSTELLUNGEN.md §7 Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung). |
| **N Counter-Sensor(en) ohne state_class — Reparatur-Werkzeuge wirken nicht** | ⚠️ WARNING | Counter-Felder (z. B. WP-Kompressor-Starts) werden über den stündlichen Snapshot-Service erfasst und funktionieren live. Ohne `state_class` greifen aber dieselben Reparatur-Werkzeuge nicht: Aussetzer (Neustart, Polling-Hänger) sind permanent verloren, häufig fehlt zusätzlich die letzte Tagesstunde (23–24 Uhr). | Einen **Verbrauchszähler-Helfer** auf diesen Sensor legen (§5.1), **ohne Zyklus** — dann laufen alle Reparatur-Werkzeuge auf diesem Zähler. |
| **N kWh-Sensor(en) ohne Summen-Spalte — Tages- und Stundenwerte bleiben leer** | ⚠️ WARNING | Der Sensor steht in HA's Langzeitstatistik, aber mit `state_class: measurement` statt `total_increasing`: HA führt dann nur Mittel-/Min-/Max-Werte und keine Zählerstände, aus denen eedc Stunden- und Tagesdeltas bilden könnte. Die **Live-Ansicht ist nicht betroffen** — sie rechnet aus den Watt-Sensoren; deshalb sieht man dort Werte, während Cockpit → Tag auf 0 steht. | **Verbrauchszähler-Helfer** auf diesen Sensor legen (§5.1), **ohne Zyklus** — er führt die Summen-Spalte. Danach die betroffenen Tage über die Reparatur-Werkbank neu berechnen; HA sammelt die Summenwerte erst ab der Umstellung. |
| **N Counter-Sensor(en) ohne Summen-Spalte — Reparatur-Werkzeuge wirken nicht** | ⚠️ WARNING | Dasselbe für Counter-Felder: der laufende Betrieb erfasst sie über den Snapshot-Service und funktioniert, aber ohne Summen-Spalte lässt sich ein Aussetzer nicht nachholen. | Wie eine Zeile darüber: **Verbrauchszähler-Helfer** (§5.1), **ohne Zyklus**. |
| **Alle N kWh-Sensor(en) in HA-Long-Term-Statistics verfügbar** | ✅ OK | Jeder zugeordnete kWh-Sensor liefert LTS — Reparatur-Werkzeuge wirken auf alle Felder. | – |

> **Wichtige Lektion:** Frühere Hinweistexte sagten „vergangene Tage bleiben leer". Das ist irreführend, weil HA-Long-Term-Statistics ohnehin erst ab Aktivierung von `state_class` angelegt werden — vor der Aktivierung existieren keine Werte zum Holen, egal auf welchem Weg du den Zähler in Ordnung bringst. Der eigentliche Schmerzpunkt ist daher: ohne `state_class` **wirken die Reparatur-Werkzeuge in der Energieprofil-Pflege nicht**. Ab Aktivierung läuft's lückenfrei, davor bleibt's leer.

---

### 4.10 Energieprofil – fehlende Tageswerte <a name="410-energieprofil--fehlende-tageswerte"></a>

> **Variantenhinweis:** Nur im **HA Add-on** (bzw. Docker mit HA-Recorder-Zugriff). Im Standalone-Betrieb fehlt die unabhängige Referenz, gegen die eedc prüfen könnte — die Kategorie wird dann still übersprungen.

**Was wird geprüft:** Gibt es in den letzten 90 Tagen Tage, an denen ein Zähler zugeordnet ist und die **HA-Langzeitstatistik einen Wert liefert**, die gespeicherte Tageszeile aber leer oder 0 ist? Das ist der typische Fall nach einer nachträglich korrigierten Zuordnung: die Zuordnung steht heute, aber für die Tage davor hat nie ein Aggregator-Lauf stattgefunden. Die Zähler-Abdeckung (§4.6) meldet dort völlig zu Recht „OK" — der Zähler *ist* ja zugeordnet.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Tag(e) ohne Werte trotz zugeordnetem Zähler (von … bis …)** | ⚠️ WARNING | Für die genannten Tage hat HA Werte, eedc nicht. Die Details nennen die betroffenen Komponenten beim Namen. | Knopf **„Zeitraum neu aggregieren"** (max. 31 Tage pro Lauf; ältere Tage bleiben für einen zweiten Lauf stehen) oder **„Tag reparieren"** je Zeile. |
| **YYYY-MM-DD: keine Tageswerte, HA hat …** | ⚠️ WARNING | Einzeltag-Zeile zum selben Sachverhalt, mit den Werten, die HA für diesen Tag führt. | **„Tag reparieren"** |
| **Keine reparierbaren Tages-Lücken gefunden (letzte 90 Tage)** | ✅ OK | Es gibt leere Tage, aber HA hat für sie ebenfalls nichts. Solche Lücken sind keine Fehlfunktion — eedc reicht nur so weit zurück wie HA selbst. | – |
| **Alle Tage mit zugeordnetem Zähler tragen Werte (letzte 90 Tage)** | ✅ OK | Nichts offen. | – |

**Nur Zeiträume, in denen die Komponente auch gelaufen ist.** Die Prüfung fordert für jeden Tag genau das ein, was der Reparatur-Lauf an diesem Tag auch schreiben darf: Komponenten, die an dem Tag noch nicht angeschafft, bereits stillgelegt oder auf *inaktiv* gesetzt waren, tauchen für diesen Zeitraum nicht auf. Vorher konnte eine Meldung samt Reparatur-Knopf für Tage erscheinen, die eedc gar nicht rechnen darf — der Knopf lief durch, schrieb nichts, und die Meldung blieb stehen. Die Anlagen-Grenze wirkt genauso: vor dem Inbetriebnahme-Datum wird nichts eingefordert.

**Kein Knopf ohne Deckung.** Braucht der Tages-Lauf für diese Anlage etwas, das nicht da ist — eine Leistungs-Zuordnung (W) bzw. MQTT-Energie —, dann erscheint der Befund weiterhin, aber **ohne** Reparatur-Knopf; die Meldung sagt stattdessen, was zuerst zuzuordnen ist.

**Reichweite:** Die Tagesreparatur heilt Tages- und Stundenwerte, **nicht** die Monatswerte. Für abgeschlossene Monate danach Einstellungen → Integration → **Statistik-Import**.

> **Abgrenzung:** PV-Werte auf einer *bestehenden* Tageszeile gehören der Drift-Prüfung (§4.7-Umfeld, Meldung „PV x → HA y kWh") — kein zweiter Turm über denselben Sachverhalt. Der Speicher-Netto-Wert (`batterie_*`) bleibt hier außen vor, er darf legitim ~0 sein.

---

### 4.11 Geräte-Connector ohne Monatswert <a name="411-geraete-connector-ohne-monatswert"></a>

> **Variantenhinweis:** Nur relevant, wenn unter *Einstellungen → Datenquellen* ein **Geräte-Connector** eingerichtet ist. Ohne Connector wird die Kategorie still übersprungen — sie meldet nie etwas, das du nicht auflösen könntest.

**Was wird geprüft:** Kann eedc aus den gespeicherten Zählerständen des Connectors für den **laufenden Monat** überhaupt einen Wert bilden? Ein Connector-Wert ist immer die **Differenz zweier Snapshots** — einer muss vor dem Monatsbeginn liegen, einer danach. Fehlt einer davon, liefert der Connector für diesen Monat gar nichts, und das war bisher nirgends zu sehen: In *Cockpit → Monat* stand einfach eine Quelle weniger, ohne Hinweis darauf, dass eine eingerichtete Quelle gerade schweigt.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Connector „…" liefert für MM/JJJJ keinen Wert** | ⚠️ WARNING | Es liegen nicht genügend Zählerstände vor, um den laufenden Monat zu berechnen — entweder erst einer insgesamt, oder der jüngste ist mehrere Tage alt (der Abruf steht still). Die Details nennen den Bestand und ob der tägliche Abruf eingeschaltet ist. | Einstellungen → Datenquellen → Connector: **täglichen Abruf einschalten** bzw. die Verbindung prüfen (Gerät erreichbar? Zugangsdaten noch gültig?). Sobald ein zweiter Zählerstand vorliegt, verschwindet der Befund von selbst. |

**Kein Lärm am Monatsersten.** Solange der Connector aktiv liefert, fehlt ihm am 1. eines Monats bis zum ersten Abruf naturgemäß der Snapshot *im* Monat. Dieser Zustand erledigt sich innerhalb eines Tages und wird deshalb nicht gemeldet — der Befund erscheint erst, wenn der jüngste Zählerstand älter als zwei Tage ist (oder es überhaupt erst einen gibt).

> **Abgrenzung:** Liefert der Connector einen Wert, misst er aber nur einen **Teil** des Monats (frisch eingerichtet), ist das kein Befund — dort steht eine Zahl, und sie wird in *Cockpit → Monat* mit ihrem Zeitraum beschriftet: „Connector (28.–30.07.2025)". Siehe [HANDBUCH_BEDIENUNG.md §2.3](HANDBUCH_BEDIENUNG.md#23-monat).

---

## 5. Behebungs-Workflows

Diese Querschnitts-Anleitungen bündeln Schritte, die mehrere Befunde gleichzeitig betreffen — typischerweise weil ein einzelner Konfigurationsfehler in mehreren Kategorien aufschlägt.

### 5.1 `state_class`-Probleme bei HA-Sensoren beheben

**Symptom:** Jeder der vier WARNING-Befunde aus §4.9 — *„kWh-Sensor(en) nicht in HA-Long-Term-Statistics"*, *„Counter-Sensor(en) ohne state_class"*, *„kWh-Sensor(en) ohne Summen-Spalte"* und *„Counter-Sensor(en) ohne Summen-Spalte"*. Alle vier führen auf denselben Handgriff.

**Ursache:** HA legt für einen Sensor erst dann Long-Term-Statistics an, wenn dessen Attribut `state_class` gesetzt ist. Typisch sind kumulative Zähler ohne diese Metadaten bei Modbus-Roh-Werten oder Hersteller-Integrationen.

**Lösung (empfohlen): Verbrauchszähler-Helfer über die HA-Oberfläche**

1. In Home Assistant **Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → Verbrauchszähler** wählen.
2. Als **Eingangssensor** den betroffenen Sensor auswählen, beim **Zurücksetzen-Zyklus** **„nie"** stehen lassen — also **ohne Zyklus**.
3. In eedc unter **Einstellungen → Datenquellen** das betroffene Feld auf den **neuen Helfer** umstellen.
4. Daten-Checker erneut prüfen — der Befund muss verschwinden.

Warum dieser Weg: Der Helfer bringt `state_class` und die Summen-Spalte von sich aus mit, und sein Name überlebt einen Gerätetausch — du wechselst später nur die Quelle, alle Zuordnungen bleiben stehen. **Ohne Zyklus** deshalb, weil ein zurückgesetzter Zähler bei jedem Reset einen Sprung erzeugt, den eedc erkennen muss; ein durchlaufender Zähler hat das Problem nicht.

> **Der Helfer fängt bei null an.** Seine Historie beginnt mit dem Anlegen — vergangene Monate holt Home Assistant nicht nach. Das gilt für jeden Weg (siehe Kasten unten), nicht nur für den Helfer.

**Alternative für alle, die die YAML ohnehin pflegen:** Für jeden betroffenen Sensor einen `customize`-Block in der `configuration.yaml` ergänzen und Home Assistant neu starten:

```yaml
homeassistant:
  customize:
    sensor.dein_zaehler:
      state_class: total_increasing
      device_class: energy
      unit_of_measurement: kWh
```

> **Wichtig:** HA legt LTS **erst ab Aktivierung** an. Vergangene Tage vor der `state_class`-Aktivierung bleiben permanent leer — das ist eine HA-Eigenschaft, kein eedc-Bug. Reparatur-Werkzeuge (Lücken aus HA-LTS nachfüllen, Tag/Bereich neu aggregieren) wirken erst auf den Zeitraum **nach** Aktivierung.

### 5.2 Fehlende kWh-Zähler in der Datenquellen-Zuordnung ergänzen

**Symptom:** Befunde aus §4.6 *„Kein Basis-Zähler für …"* oder *„N von M Komponenten ohne vollständige kWh-Zähler-Abdeckung"*.

**Lösung:**

1. Einstellungen → Datenquellen öffnen.
2. Die genannten Komponenten-Blöcke bzw. den Block *Anlage / Zähler* durchgehen.
3. Pro Pflichtfeld einen kumulativen kWh-Zähler zuordnen — **nicht** den `*_leistung_w`-Sensor (Live-Leistung in Watt taugt nicht für Energiemengen).
4. Erwartete Felder pro Komponententyp siehe Tabelle in §4.6.
5. Zuordnung speichern.
6. Daten-Checker erneut prüfen.

> **Hinweis:** Ordnest du einen kWh-Sensor ohne Standard-Metadaten zu (kein `state_class`), erscheint er in §4.9 — siehe Workflow 5.1. Der Sensor-Picker in den Datenquellen warnt beim Zuordnen bereits vor fehlender Langzeitstatistik.

### 5.3 Monatsdaten-Lücken aufholen

**Symptom:** Befunde aus §4.4 *„MM/JJJJ fehlt"* oder *„… und N weitere Monate fehlen"*.

**Drei Wege, je nach Lückengröße:**

| Anzahl fehlender Monate | Empfohlener Weg |
|------------------------|-----------------|
| 1–3 Monate | Monatsdaten-Formular pro Monat (Klick auf den „Beheben"-Link führt direkt dorthin). |
| 4+ Monate, HA-Add-on | Statistik-Import nutzen — holt mehrere Monate aus HA-LTS auf einmal. Siehe [HANDBUCH_EINSTELLUNGEN.md §6.4](HANDBUCH_EINSTELLUNGEN.md#64-statistik-import). Voraussetzung: §4.9 ist OK (state_class gesetzt). |
| Bestehende Daten aus anderem System | CSV-Import über Einstellungen → Integration → Import-Assistenten (Template via Download-Link im Import-Overlay). |

Nach jedem Schritt: Daten-Checker erneut prüfen.

### 5.4 MQTT-Drift zwischen Publisher und eedc schließen

**Symptom:** Befunde aus §4.8 *„N MQTT-Topic(s) erwartet, nie empfangen"* nach einem Re-Import oder neuer Komponente.

**Lösung:**

1. Daten-Checker → §4.8 öffnen, betroffene Topics notieren — sie enthalten typischerweise eine Komponenten-ID, die nach dem Re-Import neu vergeben wurde.
2. Publisher-Quelle öffnen (HA-Automation YAML, ioBroker Skript, Node-RED Flow).
3. Komponenten-IDs in den Topic-Pfaden anpassen — die neuen IDs findest du in eedc unter Einstellungen → Komponenten am jeweiligen Eintrag.
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

1. Einstellungen → Daten → Energieprofil-Pflege → **Reparatur-Werkbank** öffnen.
2. Im Auswahlfeld die Operation *„Tag neu aggregieren"* wählen und den betroffenen Tag angeben.
3. Bestätigen — der Lauf zieht zuerst die SensorSnapshots des Tages frisch aus HA-Statistics und baut danach Tagesprofil + Tageszusammenfassung neu.
4. Der Spike ist danach weg, vorausgesetzt der zugrunde liegende kWh-Zähler hat den fraglichen Stundenslot in HA-LTS plausibel.

**Vorgehen für mehrere Tage / längere Bereiche:**

1. Dieselbe Reparatur-Werkbank, Operation *„Mehrere Tage neu aggregieren"*.
2. Von-/Bis-Bereich angeben (Snapshots pro Tag werden frisch gezogen, Default an).
3. Ausführen — Resnap des gesamten Bereichs + Aggregat-Neuaufbau in einem Schritt. Kann bei mehreren Monaten Bestand einige Minuten dauern.

> Die Reparatur-Werkbank fasst die Operationen in einem einzigen Auswahlfeld zusammen (Tag / Mehrere Tage / Lücken nachfüllen / Kraftstoffpreise / Energieprofil-Daten löschen), gruppiert mit Trennlinien. Die frühere Bedienung über ein grünes Reload-Symbol pro Zeile in der Tages-Tabelle entfällt — die Tages-Tabelle selbst ist als **Anzeige** ins [Cockpit → Tag](HANDBUCH_BEDIENUNG.md#22-tag) umgezogen; repariert wird ausschließlich über die Werkbank.

**Was die Rückmeldung sagt:** Nach einem Einzeltag-Lauf steht dort nicht nur, ob sich der PV-Wert bewegt hat, sondern auch, **für welche Komponenten der Lauf einen Wert schreiben konnte** — und, falls nicht für alle, welche leer geblieben sind. Ein „durchgelaufen" ohne geschriebenen Wert (typisch: kein Leistungssensor zugeordnet, oder die HA-Historie reicht nicht so weit zurück) erscheint als **Hinweis**, nicht als Erfolg. Beim Bereichs-Lauf ist es dieselbe Aussage je Tag: *„N Tag(e) neu aggregiert, M ohne verwertbare Daten übersprungen."*

> **Hinweis:** Tage **löschen** ist *keine* sinnvolle Reparaturstrategie. Eine gelöschte Lerngrundlage kostet die Solarprognose den saisonalen Lernfaktor (Monatsfaktor ≥ 15 Tage), und der eigentliche Defekt sitzt im Snapshot-Cache, nicht in den HA-LTS-Werten. Resnap holt die Daten zurück — Löschen tut das nicht.

---

## 6. Beziehung zu anderen Werkzeugen

Der Daten-Checker ist Diagnose, nicht Behebung. Er **zeigt** Probleme und verlinkt zu den jeweiligen Werkzeugen, die sie lösen. Die folgende Übersicht zeigt, welches Werkzeug welche Befund-Kategorie adressiert.

| Befund aus | Adressiert über |
|------------|----------------|
| §4.1 Stammdaten | Einstellungen → Stammdaten → Anlage |
| §4.2 Strompreise | Einstellungen → Stammdaten → Strompreise |
| §4.3 Investitionen (Parameter) | Einstellungen → Komponenten → \[Komponente\] |
| §4.3 Investitionen (Monatsdaten) | Einstellungen → Daten → Monatsdaten |
| §4.4 Vollständigkeit | Monatsdaten-Formular (Einzelmonat), Statistik-Import (Bulk), CSV-Import |
| §4.5 Plausibilität | Monatsdaten-Formular (Einzelmonat), bei Sensor-Drift: Datenquellen-Zuordnung / Connector prüfen |
| §4.6 Energieprofil-Zähler | Einstellungen → Datenquellen |
| §4.7 Energieprofil-Plausibilität | Reparatur-Werkbank: *„Tag neu aggregieren"* bzw. *„Mehrere Tage neu aggregieren"* (zieht Snapshots frisch + baut Aggregate neu) |
| §4.8 MQTT-Topic-Abdeckung | Externe Publisher-Quelle (HA-Automation YAML, ioBroker, Node-RED), MQTT-Broker-Verbindung |
| §4.9 Sensor-Mapping HA-Statistics | HA-Helfer „Verbrauchszähler" (ohne Zyklus), ersatzweise `customize` (state_class), Datenquellen-Zuordnung (alternativen Sensor wählen) |
| §4.10 Fehlende Tageswerte | Knopf am Befund: *„Zeitraum neu aggregieren"* / *„Tag reparieren"*; ohne Leistungs-Zuordnung zuerst Einstellungen → Datenquellen |

### Reparatur-Werkzeuge in der Energieprofil-Pflege

Diese Werkzeuge laufen über die **Reparatur-Werkbank** unter Einstellungen → Daten → Energieprofil-Pflege (dieselbe Werkbank ist auch inline im Daten-Checker-Block erreichbar). Sie greifen aber **nur**, wenn die Voraussetzungen aus §4.9 erfüllt sind (Sensoren in HA-Long-Term-Statistics):

| Werkzeug (Werkbank-Operation) | Zweck | Voraussetzung |
|---------|-------|---------------|
| **Lücken aus HA-LTS nachfüllen** | Holt fehlende Tage aus HA-LTS für zugeordnete kWh-Felder (additiv, bestehende Tage bleiben unverändert). | §4.9 OK für betroffene Sensoren |
| **Mehrere Tage neu aggregieren** | Zieht Snapshots des Bereichs aus HA-LTS frisch (Resnap) **und** baut Tages-/Monats-Aggregate neu. Repariert Counter-Spikes wie aus §4.7. | §4.9 OK |
| **Tag neu aggregieren** | Wie *Mehrere Tage neu aggregieren*, aber für einen einzelnen Tag. | §4.9 OK |
| **Kraftstoffpreise nachpflegen** | Holt EU-Oil-Bulletin-Preise für E-Auto- und Verbrenner-Vergleich rückwirkend. | unabhängig von §4.9 |

> **Wichtig:** Wenn §4.9 für einen Sensor WARNING meldet, sind die ersten drei Werkzeuge für diesen Sensor wirkungslos — sie lesen alle aus HA-LTS, die für state_class-lose Sensoren leer ist. Erst §4.9 beheben, dann Reparatur-Werkzeuge laufen lassen.

### Wo erscheint der Daten-Checker noch?

- **In-App-Hilfe** (Menüpunkt Hilfe): Diese Doku ist dort als kuratiertes Hilfe-Dokument verfügbar.
- **„Beheben"-Links innerhalb der App**: Befund-Zeilen verlinken direkt zur betroffenen Einstellungs-Kachel — kein Suchen in den Kategorien nötig.
- **Komponenten-Achse**: Jede [Komponenten-Sicht](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse) hat einen Block **Daten-Qualität** mit den offenen Daten-Checker-Befunden genau dieser Komponente und Sprung zur Reparatur-Werkbank.
- **Aktivitäten-Log** (Einstellungen → System → Protokolle, Tab *Aktivitäten*): Bestimmte Befund-Kategorien (z. B. Connector-Test-Ergebnisse) finden sich auch dort historisch.

---

> **Verwandte Doku:**
> [Teil III §7 Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) · [Teil III §6.4 Statistik-Import](HANDBUCH_EINSTELLUNGEN.md#64-statistik-import) · [Teil III §6.1 MQTT-Broker-Verbindung](HANDBUCH_EINSTELLUNGEN.md#61-mqtt-broker-verbindung) · [Teil III §5.2 Energieprofil-Pflege](HANDBUCH_EINSTELLUNGEN.md#52-energieprofil-pflege) · [Teil III §9 Energieprofile-Hintergrund](HANDBUCH_EINSTELLUNGEN.md#9-hintergrund-energieprofile--snapshot-architektur)

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
