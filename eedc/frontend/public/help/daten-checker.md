
# eedc Handbuch — Daten-Checker

**Version 4.0** | Stand: 2026-08-22

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Infothek](HANDBUCH_INFOTHEK.md) | [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md) | [Glossar](GLOSSAR.md)

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
   8a. [Zählerstände – Rücksprung](#48a-zaehlerstaende--ruecksprung)
   9. [Sensor-Mapping – HA-Statistics](#49-sensor-mapping--ha-statistics)
   10. [Energieprofil – fehlende Tageswerte](#410-energieprofil--fehlende-tageswerte)
   11. [Geräte-Connector ohne Monatswert](#411-geraete-connector-ohne-monatswert)
   12. [Zeitzone – Abweichung zu Home Assistant](#412-zeitzone--abweichung-zu-home-assistant)
   13. [Sonstige Positionen – der Erfassungsort](#413-sonstige-positionen--der-erfassungsort)
   14. [Klimaanlage – Betriebsmodus](#414-klimaanlage--betriebsmodus)
   15. [Sensor-Zuordnung – Leistung ↔ Energie verwechselt](#415-sensor-zuordnung--leistung--energie)
   16. [Quellen-Konflikte](#416-quellen-konflikte)
   17. [Datenquellen-Drift zu Home Assistant](#417-datenquellen-drift)
   18. [PV-Doppelerfassung (Verdacht)](#418-pv-doppelerfassung)
   19. [Ladung doppelt gezählt (Wallbox + E-Auto)](#419-ladung-doppelt-gezaehlt)
   20. [Plug-in-Hybrid – elektrischer Anteil unbestimmt](#420-phev-anteil)
   21. [Batterie-Vorzeichen in der Historie](#421-batterie-vorzeichen-historie)
   22. [Ladestand bei mehreren Speichern](#422-ladestand-mehrere-speicher)
   23. [Verbrauchszähler – Zählerstände](#423-verbrauchszaehler-zaehlerstaende)
   24. [Vergleichspreise – Ø Benzinpreis](#424-vergleichspreise-benzinpreis)
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

> Der Daten-Checker umfasst inzwischen mehr Kategorien als die hier dokumentierten Kern-Kategorien (u. a. Datenquelle-Drift, Daten-Quellen-Konflikte, Batterie-Vorzeichen-Historie, PV-Doppelerfassungs-Verdacht, E-Mobilität-Pool-Pflege, Plug-in-Hybrid ohne bestimmbaren Fahranteil). Sie folgen derselben Severity- und „Beheben"-Logik. Eine vollständige Dokumentation dieser jüngeren Kategorien ist ein separater Redaktions-Schritt (kein Bestandteil des reinen IA-Umbaus).

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

eedc prüft **26 Kategorien**. Die meisten greifen in jeder Installation identisch; **fünf** hängen an Voraussetzungen, die je nach Installation gegeben sind oder nicht — sie sind unten fett markiert.

| # | Kategorie | HA Add-on | Standalone (Docker / native) |
|---|-----------|-----------|------------------------------|
| 1 | Stammdaten (§4.1) | greift | greift |
| 2 | Strompreise (§4.2) | greift | greift |
| 3 | Investitionen (§4.3) | greift | greift |
| 4 | Monatsdaten – Vollständigkeit (§4.4) | greift | greift |
| 5 | Messwerte ohne Monatszeile (§4.4a) | greift | greift |
| 6 | Monatsdaten – Plausibilität (§4.5) | greift | greift |
| 7 | Energieprofil – Zähler-Abdeckung (§4.6) | greift (Zuordnung zu HA-Entitäten `sensor.…`) | greift (Zuordnung zu MQTT-Topics) |
| 8 | Energieprofil – Plausibilität (§4.7) | greift | greift |
| 9 | **MQTT-Topic-Abdeckung** (§4.8) | nur wenn MQTT-Import aktiv | nur wenn MQTT-Import aktiv |
| 9a | **Zählerstände – Rücksprung** (§4.8a) | nur wenn MQTT-Import aktiv | nur wenn MQTT-Import aktiv |
| 10 | **Sensor-Mapping – HA-Statistics** (§4.9) | greift | **wird übersprungen** (keine HA-LTS verfügbar) |
| 11 | Energieprofil – fehlende Tageswerte (§4.10) | greift | greift |
| 12 | Geräte-Connector ohne Monatswert (§4.11) | greift | greift |
| 13 | **Zeitzone – Abweichung zu HA** (§4.12) | greift | **wird übersprungen** (keine HA-Verbindung) |
| 14 | Sonstige Positionen – wiederkehrend (§4.13) | greift | greift |
| 15 | Sonstige Positionen – Doppelerfassung (§4.13) | greift | greift |
| 16 | Klimaanlage – Betriebsmodus (§4.14) | greift | greift |
| 17 | **Sensor-Zuordnung – Leistung ↔ Energie** (§4.15) | greift | **wird übersprungen** (Einheit kommt aus HA) |
| 18 | Quellen-Konflikte (§4.16) | greift | greift |
| 19 | **Datenquellen-Drift zu HA** (§4.17) | greift | **wird übersprungen** (keine Vergleichsseite) |
| 20 | PV-Doppelerfassung (§4.18) | greift | greift |
| 21 | E-Mobilität – Pflegekonflikt (§4.3.9) | greift | greift |
| 22 | Ladung doppelt gezählt (§4.19) | greift | greift |
| 23 | Plug-in-Hybrid – Anteil unbestimmt (§4.20) | greift | greift |
| 24 | Batterie-Vorzeichen in der Historie (§4.21) | greift | greift |
| 25 | Ladestand bei mehreren Speichern (§4.22) | greift | greift |
| 26 | Verbrauchszähler – Zählerstände (§4.23) | greift | greift |

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
| **Installationsdatum nicht gesetzt** | ❌ ERROR | Ohne dieses Datum weiß eedc nicht, ab wann es Zählerwerte für Einspeisung und Netzbezug erwarten darf — es weicht dann auf das älteste Anschaffungsdatum deiner **Erzeuger** aus, ersatzweise auf die früheste vorhandene Datenzeile. Im letzten Fall wird der Anfang aus der Lücke abgeleitet, und eine fehlende Zeile am Beginn deiner Historie fällt niemandem mehr auf. *(Bis v4.0.15 nur ⚠️ WARNING.)* | Einstellungen → Stammdaten → Anlage → Installationsdatum eintragen. Bei **neuen** Anlagen ist es seit demselben Stand ein Pflichtfeld im Setup; im Anlagen-Formular bleibt es bewusst freiwillig, damit eine andere Änderung nicht daran hängenbleibt — dort steht stattdessen ein Hinweis am Feld. |
| **Erzeuger älter als die Anlage: TT.MM.JJJJ** | ⚠️ WARNING | Ein PV-Modul oder Balkonkraftwerk wurde laut Anschaffungsdatum **vor** dem Installationsdatum der Anlage angeschafft. Dann wurde bereits Strom erzeugt, bevor die Anlage laut Stammdaten existierte — für die Monate dazwischen fragt eedc keine Zählerwerte ab. Eines der beiden Daten stimmt nicht. | Einstellungen → Stammdaten → Anlage → Installationsdatum korrigieren (meist ist es das) — oder das Anschaffungsdatum der Komponente. ⚠ Bei **anderen** Komponenten (E-Auto, Wallbox, Wärmepumpe, Speicher) ist ein früheres Datum völlig normal — sie bekommen deshalb die Zeile darunter als **Hinweis**, nicht diese Warnung. Datiere solche Geräte niemals um, nur damit eine Anzeige ruhig wird; du verlierst dabei ihre echte Historie. |
| **Gerät älter als die Anlage: „Name" seit TT.MM.JJJJ** | ℹ️ INFO | Eine Komponente, die **kein** Erzeuger ist (E-Auto, Wallbox, Wärmepumpe, Speicher, Sonstiges), ist älter als die Anlage. **Das ist normal und kein Defekt** — man hatte das Auto vor der PV-Anlage. Gemeldet wird nicht das Gerät, sondern die Datenlage: Für die Monate davor gibt es keine Einspeisungs- und Netzbezugswerte und damit keine Bilanz; eedc kann dort nicht sagen, ob der Strom gekauft oder selbst erzeugt war. | **Wenn du Zählerwerte aus dieser Zeit hast:** nachtragen. **Wenn das Datum der Anlage nicht stimmt:** dieses korrigieren. **Sonst nichts** — der Hinweis bleibt dann als Auskunft stehen (siehe Kasten in §2). ⚠ **Datiere das Gerät nicht um.** Genau das ist einem Anwender passiert, der die alte Meldung loswerden wollte — die echte Anschaffungshistorie seines Fahrzeugs war danach verloren. |
| **Anlagenleistung fehlt oder ist 0** | ❌ ERROR | Leistung in kWp ist Bezugsgröße für sämtliche Soll-/Ist-Vergleiche und PVGIS-Plausibilität. | Einstellungen → Stammdaten → Anlage → Leistung in kWp eintragen. Gemeint ist die installierte **Modulleistung (DC)**, also die Summe der PV-Modul-Komponenten — **nicht** die Summe der Wechselrichter-Leistungen. Ein Balkonkraftwerk gehört nicht dazu (eigene Anlage mit eigener MaStR-Registrierung). |
| **Keine Koordinaten hinterlegt** | ℹ️ INFO | Koordinaten werden nur für die PVGIS-Solarprognose benötigt. Ohne sie funktionieren PV-Auswertungen mit dynamischer Performance-Ratio nicht; statische Plausibilität bleibt aktiv. | Einstellungen → Stammdaten → Anlage → Koordinaten setzen (oder „Aus Adresse ermitteln"). |
| **Kein Standort hinterlegt (Ort/PLZ)** | ℹ️ INFO | Wird für den Community-Benchmark-Vergleich nach Region benötigt. Ohne Ort/PLZ teilst du keine regionalen Vergleichswerte. | Einstellungen → Stammdaten → Anlage → Ort oder PLZ setzen. |
| **Keine PV-Module als Komponente angelegt** | ❌ ERROR | Ohne PV-Modul-Komponenten fehlen Erzeugungsdaten in der Aufschlüsselung. (Sonderfall: nur Balkonkraftwerk → INFO statt ERROR.) | Einstellungen → Komponenten → PV-Module hinzufügen. |
| **Nur Balkonkraftwerk, keine PV-Module angelegt** | ℹ️ INFO | BKW-only Setup. PVGIS-Prognose und String-Vergleich sind nicht verfügbar, alles andere funktioniert. | Keine Aktion nötig — Hinweis dokumentiert die Einschränkung. |
| **&lt;Wechselrichter&gt;: Modulleistung ist mehr als das 2-fache der Wechselrichter-Leistung** | ⚠️ WARNING | DC/AC-Verhältnis der Strings an diesem Gerät > 2,0. **Überbelegung selbst ist der Normalfall** und wird nicht gemeldet (üblich 1,1–1,3, bei Ost/West bis ~1,5) — oberhalb 2,0 ist ein Pflegefehler wahrscheinlicher als eine Auslegung. | Prüfen, ob in einem „Leistung (kWp)"-Feld eines Strings versehentlich die **Wechselrichter**-Leistung steht. Ins kWp-Feld gehört die Modulleistung (Anzahl × Wp), die Geräteleistung ins Feld „Max. Leistung (kW)" des Wechselrichters. Ist die Auslegung wirklich so, kann die Meldung stehen bleiben — sie ändert keine Berechnung. |
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
| **N Tarif(e) rechnen die Einspeisung mit 0 ct/kWh** | ℹ️ INFO | Mindestens ein Tarif trägt **0 ct/kWh**, und in seinem Gültigkeitszeitraum ist Einspeisung erfasst — der Einspeise-Erlös dieser Monate bleibt damit 0 € (Cockpit, ROI, Jahresbericht). Der Fall entsteht regelmäßig, weil ein neuer Tarif seit v4.0.10 mit 0 startet: eedc rät den EEG-Satz bewusst nicht. **Die Zeile fordert nichts** — sie sagt, womit gerechnet wird; was du einträgst, wird gerechnet. **Ab 50 kWh/Jahr** erfasster Einspeisung; darunter (Nulleinspeisungs-Systeme mit reiner Regelungstoleranz) schweigt sie ganz. | Wer eine Vergütung bekommt: Einstellungen → Stammdaten → Strompreise → Tarif öffnen, Satz aus dem Vergütungsbescheid eintragen; bei gestaffelter Vergütung den nach kWp gewichteten **Mischsatz** (eedc rechnet flat, siehe [Einstellungen §2.2](HANDBUCH_EINSTELLUNGEN.md#22-strompreise)). **Ist deine Einspeisung tatsächlich unvergütet** (Nulleinspeisung, Volleinspeisung ohne Vergütung, ausgelaufene EEG-Förderung), **ist 0 richtig und nichts zu tun**. |
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
| **\[Name\]: Kapazität vermutlich in Wh statt kWh eingetragen** | ⚠️ WARNING | Das Balkonkraftwerk darüber nennt seine Akku-Kapazität in **Wh**, dieser Speicher seine in **kWh** — und beide tragen **denselben Zahlenwert**. Dann ist die Kapazität tausendfach zu groß, und Vollzyklen, Auslastung und Wirtschaftlichkeit rechnen gegen einen Nenner, den es nicht gibt. Geprüft wird der Widerspruch der beiden Felder, **keine Obergrenze** — ein großer Speicher wird nicht angemeckert. | Komponente öffnen, die Kapazität in kWh eintragen (5.376 Wh sind 5,376 kWh). Die Meldung nennt die Zahl. |
| **\[Name\]: Arbitrage aktiv, aber Ø Ladepreis fehlt (Stammdaten-Wert)** | ⚠️ WARNING | `arbitrage_faehig` ist gesetzt, aber `lade_durchschnittspreis_cent` fehlt. Arbitrage-Einsparung kann nicht berechnet werden. ⚠ **Gemeint ist der Erwartungswert in den Stammdaten** — nicht der gemessene Monatswert *Ø Ladepreis* aus dem Monatsabschluss und nicht ein zugeordneter Preis-Sensor. Beide gibt es, beide sind richtig, aber sie messen, was war; dieser schätzt, was kommt. | Komponente öffnen → **Netzladung & Arbitrage** aufklappen → Ø Ladepreis eintragen (der Preis im Niedrigtarif-Fenster, z. B. bei negativen Börsenpreisen). Ohne Angabe rechnet eedc mit 12 ct/kWh. |
| **\[Name\]: Arbitrage aktiv, aber Ø Entladepreis fehlt** | ⚠️ WARNING | Analog zum Ladepreis: ohne `entlade_vermiedener_preis_cent` kein Arbitrage-Erlös berechenbar. | Komponente öffnen → **Netzladung & Arbitrage** → Ø Entladepreis eintragen (der vermiedene Preis zur Spitzenlastzeit). Ohne Angabe rechnet eedc mit 35 ct/kWh. |
| **\[Name\]: Speicher-Ladung fehlt in N Monat(en)** | ⚠️ WARNING | `ladung_kwh` fehlt in den genannten Monaten — Vollzyklen und Wirkungsgrad lassen sich für diese Monate nicht berechnen. | Monatsdaten nachtragen. |

> ⚠ **Die beiden Arbitrage-Preisfelder gab es lange in keinem Formular** — der Hinweis war damit
> nicht abstellbar (Issue #397, MeinerB). Sie stehen jetzt beim Speicher unter *Netzladung &
> Arbitrage*, sobald der Schalter an ist.
>
> **Warum eedc hier überhaupt eine Anwender-Angabe braucht:** Arbitrage lebt davon, dass dieselbe
> Kilowattstunde zu **verschiedenen Uhrzeiten** verschieden viel kostet — und ein eedc-Tarif kennt
> keine Uhrzeit. Wer einen dynamischen Tarif (Tibber/aWATTar/EPEX) angebunden hat, braucht die
> Felder nicht: dort zieht eedc den stundengenauen Preis vor.

#### 4.3.4 E-Auto (privat)

> Dienstwagen (`ist_dienstlich`) werden von dieser Prüfung übersprungen — kein PV-Bezug, kein Investment-ROI.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Name\]: Fahrleistung/Verbrauch fehlt** | ℹ️ INFO | Weder `jahresfahrleistung_km` noch `verbrauch_kwh_100km` gesetzt. Einsparungs-Berechnung gegenüber Verbrenner ist nicht möglich. | Komponente öffnen, Jahres-Fahrleistung und/oder Verbrauch eintragen. |
| **\[Name\]: Alternativkosten (Verbrenner) fehlen** | ⚠️ WARNING | `anschaffungskosten_alternativ` fehlt. ROI gegenüber Verbrenner-Alternative wird ohne diesen Wert nicht berechnet. | Komponente öffnen, geschätzte Anschaffungskosten eines vergleichbaren Verbrenners eintragen. |
| **\[Name\]: Ladung PV fehlt in N Monat(en)** | ℹ️ INFO | `ladung_pv_kwh` fehlt — Anteil PV-Ladung am Gesamt-Ladestrom unbekannt. Geringere Severity als andere Pflichtfelder, weil V2H/Wallbox-Aufschlüsselung optional ist. **Nur bei Fahrzeugen ohne Wallbox:** Mit Wallbox liegt die Heimladung kanonisch dort, das Feld am E-Auto wird gar nicht erst angeboten — dieser Hinweis erscheint dann nicht (bis v4.0.27 erschien er trotzdem und war nicht abstellbar). Dienstwagen sind ebenfalls ausgenommen. | Monatsdaten nachtragen. Wer eine Wallbox hat, erfasst dort (Loadpoint-Sensor), nicht am E-Auto. |

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
| **\[Name\]: Heizwärme fehlt in N Monat(en)** | ℹ️ INFO | Die abgegebene Wärmemenge fehlt — ohne sie gibt es für diese Monate keine gemessene JAZ und keinen COP-Vergleich. Der Stromverbrauch bleibt vollständig erfasst, die Stromauswertung ist unberührt. | **Mit Wärmemengenzähler:** Werte nachtragen. **Ohne Wärmemengenzähler bleibt der Hinweis stehen** — und das ist Absicht: eedc zeigt bei JAZ/COP dann „—" statt einer Scheinzahl. Der Hinweis sagt dir, *warum* dort ein Strich steht. |

> **Split-Klimaanlagen sind ausgenommen.** Ist die Wärmepumpenart **Luft-Luft (Klimaanlage)** eingetragen, verlangt der Checker weder die monatliche Heizwärme noch die Tages-Zusatzzähler aus §4.6: beides setzt einen Wärmemengenzähler voraus, den solche Geräte praktisch nie haben, und einen Warmwasserkreis gibt es dort gar nicht. Der **Stromverbrauch** bleibt Pflicht, die Stromauswertung funktioniert vollständig; JAZ/COP zeigen „—" statt einer Scheinzahl. Eine Wärmepumpe **ohne** eingetragene Art gilt als klassische Wärmepumpe — eine fehlende Angabe schaltet die Erwartung nicht ab.
>
> **Die drei Hinweise zum Gas-/Öl-Vergleich hängen an der Pflege, nicht an der Bauart** (geändert 2026-08-18). Sie verteilen sich auf **zwei verschiedene Fragen**:
>
> * *Alter Energiepreis nicht gesetzt* und *Heizwärmebedarf nicht gesetzt* versorgen die Ersparnis-Rechnung gegenüber einer **ersetzten Heizung**. Sie bleiben aus, sobald bei *Vergleich mit alter Heizung (ROI)* die Option **„Nichts ersetzt (Neubau)"** gewählt ist — bei jeder Wärmepumpe, unabhängig von der Bauart. Heizt du mit deiner Klimaanlage tatsächlich, wähle den ersetzten Energieträger; dann erscheinen sie, und die Wirtschaftlichkeit wird wie bei jeder anderen Wärmepumpe gerechnet.
> * *Alternativkosten (Gas-/Ölheizung) fehlen* ist eine **dritte Frage** und gilt für jede Wärmepumpe: Was hättest du **stattdessen kaufen** müssen? Der Betrag mindert die Anschaffungskosten, nur die Differenz muss sich amortisieren. Ein Neubau ersetzt keine Heizung, hat aber trotzdem keinen Gaskessel gekauft — deshalb hängt dieser Hinweis an keiner der beiden Achsen. Gab es keine Alternative, trag **0** ein: Das ist eine gültige Antwort und lässt den Hinweis verschwinden.
>
> ⚠ **Hier stand bis 2026-08-18:** *„Ebenfalls ausgenommen: die drei Hinweise zum Gas-/Öl-Vergleich … Sie versorgen ausschließlich die Ersparnis-Rechnung … Für Klimaanlagen bleiben sie aus."* **Beide Aussagen waren falsch** (gemeldet als [#383](https://github.com/supernova1963/eedc-homeassistant/issues/383)): Die Alternativkosten versorgen nicht die Ersparnis-Rechnung, sondern die Amortisation — und die Ausnahme lag auf der falschen Achse. Wer im **Neubau** baute, bekam die Hinweise trotzdem und konnte sie nicht auflösen; wer mit einer Klimaanlage **heizte**, bekam sie nie zu sehen.

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
| **N Tag(e) zählen dieselbe Ladung doppelt** | ⚠️ WARNING | Betrifft die bereits **gespeicherten Tageswerte**: Dort steht die Ladung eines Tages sowohl an der Wallbox als auch am Fahrzeug. Die Prüfung nennt Zeitraum und die größten Fälle. | Der Knopf **„Zeitraum neu aggregieren"** rechnet die betroffenen Tage neu — bewusst ein Knopf und kein automatischer Lauf, denn die Reparatur überschreibt vorhandene Tageswerte. Kein Befund heißt „geprüft, soweit Tageswerte vorliegen". |
| **Elektrischer Fahranteil unbestimmt (Plug-in-Hybrid)** | ℹ️ INFO | In N Monaten sind Kilometer erfasst, aber kein elektrischer Fahrverbrauch und kein Fahranteil in Prozent — eedc rechnet diese Monate mit **100 % elektrisch**, Ersparnis und CO₂-Einsparung fallen dadurch zu gut aus. | Entweder den monatlichen Fahrverbrauch in kWh erfassen (dann rechnet eedc den Anteil gemessen) oder am Fahrzeug einen geschätzten **elektrischen Fahranteil (%)** eintragen. |

> ⚠ **Beide Meldungen gab es schon vor August 2026, sichtbar waren sie nicht:** Die Anzeige-Liste
> der Daten-Checker-Seite kannte ihre Kategorien nicht und ließ sie beim Aufbau weg — samt dem
> Reparatur-Knopf. Wer die doppelt gezählten Tage bisher nicht heilen konnte, findet den Weg
> seither an dieser Stelle.

---

### 4.4 Monatsdaten – Vollständigkeit <a name="44-monatsdaten--vollstaendigkeit"></a>

**Was wird geprüft:** Welche Monate zwischen dem **Installationsdatum der Anlage** und dem Vormonat sind in der Datenbank erfasst? Ist kein Installationsdatum gepflegt, gilt das älteste Anschaffungsdatum deiner **Erzeuger** (PV-Module, Balkonkraftwerk), zuletzt der erste vorhandene Monatsdaten-Eintrag. ⚠ Andere Komponenten ziehen den Bereich **nicht** zurück: Ein E-Auto von 2017 an einer Anlage von 2022 fordert keine Zählerwerte ab 2017 — eine Monatszeile ist eine Aussage über die Anlage, nicht über ein einzelnes Gerät. Wovon das unberührt bleibt: Ob eine Komponente in einem Monat *mitrechnet*, entscheidet weiterhin ihr eigenes Anschaffungs- bzw. Stilllegungsdatum. Der laufende Monat wird ausgeklammert, weil er noch nicht abgeschlossen ist. Das Ergebnis fließt zusätzlich in den Fortschrittsbalken „Monatsdaten-Abdeckung" oben ein.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Keine Monatsdaten vorhanden** | ⚠️ WARNING | Es gibt keinen einzigen Monatsdaten-Eintrag. Cockpit, Aussicht, ROI und Community-Vergleich sind leer. | Monatsdaten-Formular für den ersten Monat ab Installation öffnen (Einstellungen → Daten → Monatsdaten), oder per CSV-Import bestehende Daten einlesen. |
| **MM/JJJJ fehlt** | ❌ ERROR | Konkreter Monat zwischen Installationsdatum und Vormonat ist nicht erfasst. Wird einzeln gelistet (max. 12 Monate), darüber hinaus zusammengefasst. *(Bis v4.0.15 nur ⚠️ WARNING — warum das zu milde war, steht im Kasten unter dieser Tabelle.)* | Der „Beheben"-Link öffnet das Monatsdaten-Formular direkt für den fehlenden Monat. |
| **... und N weitere Monate fehlen** | ❌ ERROR | Mehr als 12 fehlende Monate — Sammelmeldung, um die Liste nicht zu überschwemmen. | Einstellungen → Daten → Monatsdaten öffnen, dort Monate nachtragen. Bei vielen Lücken: Statistik-Import nutzen, der mehrere Monate auf einmal aus HA-Long-Term-Statistics holt. |
| **Alle N Monate vollständig** | ✅ OK | Vom Installationsdatum bis Vormonat ist jeder Monat erfasst. | – |

> **Warum ein fehlender Monat ein Fehler ist und keine Warnung.** Einspeisung und Netzbezug sind die Basis, auf der eedc überhaupt eine Bilanz bildet. Ohne sie weiß eedc nicht, woher der Strom eines Geräts kam — **und rechnet trotzdem**: Der Direktverbrauch entsteht als *Erzeugung minus Einspeisung minus Speicherladung*, und eine fehlende Einspeisung liest diese Rechnung als **0**. Dann gilt die ganze Erzeugung als Eigenverbrauch und wird mit dem **Netzpreis** statt der Einspeisevergütung bewertet. An einem echten Monat nachgerechnet: **622 € statt 282 €**, bei einem Hausverbrauch von 1.838 statt 520 kWh. Die alte Zahl war also nicht ungenau, sondern systematisch zu gut — deshalb ist eine Lücke hier kein Schönheitsfehler.
>
> **Hinweis zur Abdeckungs-KPI:** Der Prozentwert oben bezieht sich auf erwartete Monate, nicht auf Datenfelder *innerhalb* eines Monats. Ein zu 100 % abgedeckter Monatsdaten-Stand kann trotzdem unvollständige Pflichtfelder enthalten — das prüft §4.5.

---

### 4.4a Monatsdaten – Messwerte ohne Monatszeile <a name="44a-messwerte-ohne-monatszeile"></a>

**Was wird geprüft:** Gibt es Messwerte einzelner Komponenten (PV je Modul, Speicher-Zyklen, Wallbox-Ladung …) für einen Monat, der selbst nicht mehr erfasst ist?

Ein Monat besteht in eedc aus zwei Teilen: der **Zählerzeile** der Anlage (Einspeisung, Netzbezug …) und den **Messwerten je Komponente** daneben. Wird der Monat gelöscht, verschwindet die Zählerzeile — und damit der Monat aus allen Listen. Die Messwerte der Komponenten blieben bis August 2026 stehen, unsichtbar, aber wirksam: Ein erneuter Import dieses Monats prallte an ihnen ab und meldete lediglich „Felder wurden durch manuell gepflegte Werte geschützt". Wer den Monat vorher bewusst gelöscht hatte, suchte den Fehler dann bei sich.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **MM/JJJJ: Messwerte von N Komponente(n) ohne Monatszeile** | ⚠️ WARNING | Für den Monat liegen Messwerte einzelner Geräte vor, aber keine Zählerzeile (Einspeisung/Netzbezug). Der Monat erscheint deshalb in keiner Monatsliste und fehlt in Autarkie und Community-Vergleich. Der Zustand entsteht auf mehreren Wegen — Statistik-Import ohne Zähler-Sensoren, Cloud-Import einer Station ohne Smartmeter, oder ein früher gelöschter Monat; nachträglich sind sie nicht zu unterscheiden, deshalb nennt die Meldung keine Ursache. **Hängt ein Zählerstand daran** (Gas, Wasser, Öl — *Sonstiges* der Kategorie Zähler), nennt die Meldung ihn zusätzlich beim Namen und warnt vor dem Entfernen. | **Regelfall: nachtragen.** Der Link führt direkt in das Formular dieses Monats — Zählerwerte eintragen, dann gehören die Messwerte wieder dazu. Nur wenn die Werte wirklich weg sollen: Knopf **„Messwerte entfernen"**. |

> ⚠ **Ein Zählerstand ist die Ausnahme von „im Zweifel entfernen".** Bei jeder anderen Größe fehlt nach dem Löschen genau dieser eine Monat. Ein **Stand** ist dagegen kein Monatswert, sondern der **Anfangswert des Folgemonats**: eedc rechnet daraus Ende − Anfang. Entfernst du den Stand von Juni, greift Juli auf den Mai-Stand zurück und weist **zwei Monate als einen** aus — und zwar ohne Hinweis, weil der Zeitraum formal vollständig bleibt. Für Zähler ist Nachtragen deshalb nicht nur der Regelfall, sondern der einzige unschädliche Weg. **Der Knopf bleibt trotzdem stehen:** eedc entscheidet nicht für dich, wann ein Stand entbehrlich ist. Derselbe Hinweis steht im Lösch-Dialog unter *Einstellungen → Daten → Monatsdaten*.

> **Vorbeugen:** Der Lösch-Dialog unter *Einstellungen → Daten → Monatsdaten* nennt seit derselben Version, wie viele Komponenten-Messwerte an einem Monat hängen, und bietet an, sie mitzulöschen. Ohne Haken bleiben sie erhalten — das ist Absicht, denn gemessene Werte sind meist die teureren Daten.

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
| **MM/JJJJ: PV-Erzeugung ungewöhnlich hoch (X kWh)** | ⚠️ WARNING | Wert übersteigt das dynamische Maximum (PVGIS × max(PR; 1,0) × 1,45) bzw. das statische Maximum (kWp × Monatsfaktor). Details nennen den verwendeten Schwellwert. | Wert prüfen — Eingabefehler? Falscher Multiplikator? **Häufigste echte Ursache ist eine Doppelerfassung** (§4.18): dieselbe Erzeugung an zwei Stellen zugeordnet. Danach erst der strahlungsreiche Monat — dann bleibt der Hinweis als Auskunft stehen und sagt, mit welcher Zahl eedc rechnet. |
| **MM/JJJJ: Einspeisung (X kWh) > PV-Erzeugung (Y kWh)** | ❌ ERROR | Logisch unmöglich — du kannst nicht mehr einspeisen als erzeugen. | Beide Werte prüfen. Häufige Ursache: PV-Erzeugung wurde nur teilweise erfasst (z. B. ein String fehlt in den Komponenten), oder Einspeisung enthält fälschlich Bezug. |
| **MM/JJJJ: mehr PV verwendet als erzeugt?** | ⚠️ WARNING | Einspeisung **plus** die aus PV geladene Speichermenge ist größer als die Erzeugung des Monats. Beides kommt aus derselben Quelle — zusammen kann es nicht mehr sein, als die Anlage geliefert hat. Bewusst als **Frage**: die häufigste Ursache ist kein Messfehler. | In dieser Reihenfolge prüfen: **(1)** Wird der Speicher auch aus dem Netz geladen (Arbitrage, Notladung), ohne dass das Feld **Ladung aus Netz** gepflegt ist? Dann stimmt die Energie, nur die Zuordnung fehlt. **(2)** Ist die Erzeugung zu niedrig erfasst (ausgesetzter String-Sensor)? **(3)** Sind Einspeisung und Netzbezug vertauscht — dann meldet die Zeile darüber meist zusätzlich. Kleine Abweichungen (bis 2 % der Erzeugung, mindestens 5 kWh) bleiben still. |
| **\[Gerät\]: PV-Ladung größer als Gesamtladung (MM/JJJJ: X,X kWh von Y,Y kWh)** | ⚠️ WARNING | An einer Wallbox oder einem E-Auto ist die **aus PV geladene** Menge größer als die **gesamte** Ladung dieses Monats. Die PV-Ladung ist ein Teil der Gesamtladung und kann nicht größer sein. ⭐ **Es steht deshalb keine falsche Zahl in deinen Auswertungen** — eedc rechnet in dieser Lage strukturell mit *PV + Netz* weiter. Genau dabei wird aber der von dir eingetragene Gesamtwert **beiseitegelegt**: Die Ladung, die du auf dem Bildschirm siehst, ist dann nicht die, die du erfasst hast. Ohne diese Meldung erfährst du nie, dass einer deiner beiden Werte falsch ist. | Monat öffnen und beide Werte prüfen — der Link führt direkt hinein. Häufige Ursachen: ein Import hat nur eines der beiden Felder aktualisiert, oder Gesamt- und PV-Wert stammen aus zwei verschiedenen Quellen (Wallbox-Sicht gegen Fahrzeug-Sicht, siehe §4.19). **Einen Reparatur-Knopf gibt es bewusst nicht:** eedc kann nicht wissen, welcher der beiden Werte stimmt. |
| **MM/JJJJ: Einspeisung und Netzbezug sind beide 0** | ⚠️ WARNING | Beide Kernfelder sind 0 — in den allermeisten Fällen fehlende Daten, kein echter Null-Verbrauch. Bis v4.0.13 konnte auch der Statistik-Import solche Zeilen anlegen, wenn keine Zähler-Sensoren zugeordnet waren; seither entsteht in dem Fall keine Zeile mehr, bestehende bleiben aber stehen. | **Regelfall: Monatsdaten öffnen, Werte eintragen** — der Link führt direkt in diesen Monat. **Sind beide Werte bei dir tatsächlich 0** — die Anlage hat keinen Netzanschluss (Inselbetrieb), oder sie war den ganzen Monat außer Betrieb (Umzug, Defekt) —, **dann ist 0 richtig und nichts zu tun**: Der Hinweis bleibt als Auskunft stehen und sagt, womit eedc für diesen Monat rechnet (wie die Spezialtarif-Hinweise, siehe Kasten in §2). *(Bis v4.0.15 stand hier als einzige Begründung „wahrscheinlich fehlende Daten" — für Anlagen ohne Netzanschluss war der Befund damit durch keine Eingabe abstellbar.)* |
| **MM/JJJJ: \[Feld\] > 3× Vorjahr (X vs. Y kWh)** | ⚠️ WARNING | Einspeisung oder Netzbezug ist mehr als dreimal so groß wie der gleiche Monat im Vorjahr (Vorjahr > 50 kWh). Häufig Eingabefehler (Faktor 10) oder Zählerwechsel ohne Reset. **Drei Ausnahmen — die Prüfung setzt für das Monatspaar aus:** (1) der Vergleichsmonat liegt vor oder in der Inbetriebnahme (beide Felder); (2) die installierte Erzeugerleistung ist zwischen beiden Monaten um mindestens 10 % gewachsen — dann ist der Sprung der **Einspeisung** erklärt; (3) zwischen beiden Monaten ist ein **Verbraucher dazugekommen** (Wärmepumpe, E-Fahrzeug, Wallbox oder ein „Sonstiges“ der Kategorie Verbraucher) — dann ist der Sprung des **Netzbezugs** erklärt. Ausnahme 2 und 3 sind seitenrein: ein Erzeuger-Zubau entschuldigt den Netzbezug nicht und umgekehrt. Ein **Austausch** ist kein Zubau (alte Komponente stillgelegt, neue angeschafft ⇒ Anzahl unverändert). | Werte beider Monate prüfen. Zeigt eedc die Meldung trotz neuer Wallbox/WP, ist deren Anschaffungsdatum vermutlich nicht gepflegt — dann dort nachtragen, statt die Meldung stehen zu lassen. |

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

> ### ⚠ Die teuerste Folge steht nicht in der Liste oben — sie betrifft **Speicher** und **PV**
>
> Der **bilanzielle Hausverbrauch** einer Stunde entsteht als `PV + Netzbezug − Einspeisung − Speicher`. Fehlt einer dieser Anteile, wird er als **0** gerechnet: Die Stunde bleibt dann nicht leer, sondern fällt **zu niedrig** aus — und sie sieht dabei nicht falsch aus, sondern plausibel.
>
> Daran hängt die **Grundlast** (Median der Nachtstunden 0–5 Uhr) und mit ihr *Cockpit → Monat*, der **Monatsbericht** und der HA-Sensor `eedc_grundlast_kw`. Typisches Bild bei fehlendem Speicher-Zähler: Die Grundlast steht im Sommer nahe null und **steigt scheinbar von selbst**, je weniger der Akku die Nacht trägt.
>
> ⛔ **Nur diese zwei Komponententypen sind betroffen.** Wärmepumpe, Wallbox und E-Auto stehen gar nicht in dieser Formel — sie sind Teil des Hausverbrauchs, keine Bilanzgröße daneben. Ein fehlender Zähler an ihnen lässt ihre eigenen Auswertungen leer, verfälscht aber weder Hausverbrauch noch Grundlast.

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
| **Kein Basis-Zähler für: \[Einspeisung, Netzbezug\]** | ⚠️ WARNING | In der Datenquellen-Zuordnung fehlt der Basis-Zähler für Einspeisung und/oder Netzbezug. Ohne diesen bleibt der bilanzielle Hausverbrauch im Energieprofil leer — **und damit auch die Grundlast**, die als Median der Nachtstunden daraus gebildet wird (*Cockpit → Monat*, Monatsbericht, HA-Sensor `eedc_grundlast_kw`). | Einstellungen → Datenquellen öffnen, im Block *Anlage / Zähler* den kumulativen kWh-Zähler zuordnen. **Wichtig:** den kWh-Zähler wählen, nicht den `*_leistung_w`-Sensor. |
| **N von M Komponenten ohne vollständige kWh-Zähler-Abdeckung** | ⚠️ WARNING | Mindestens eine aktive Komponente hat nicht alle erwarteten kWh-Zähler zugeordnet. Details listen die betroffenen Komponenten und fehlenden Felder. Folgen für diese Komponenten: Prognose-IST, Lernfaktor und Monatsauswertungen bleiben leer. **Bei einem Speicher oder einer PV-Erzeugung kommt die teuerste Folge hinzu:** Der bilanzielle Hausverbrauch je Stunde rechnet den fehlenden Anteil als 0 und fällt damit **zu niedrig** aus — und mit ihm die Grundlast (siehe den Kasten über dieser Tabelle). **Nicht gemeldet wird ein Balkonkraftwerk, an dem PV-Module hängen** — dann tragen die Module die Erzeugung, gemessen wird am Modul, und der Checker sagt das mit einer eigenen OK-Zeile („N Balkonkraftwerk(e) über die zugeordneten PV-Module gedeckt“). Ein BKW **ohne** Modul-Kinder braucht weiterhin seinen eigenen Zähler. | Einstellungen → Datenquellen öffnen, pro Komponente die fehlenden Zähler zuordnen. Bei Speichern: beide Felder (`ladung_kwh` + `entladung_kwh`) sind nötig. |
| **N Komponente(n) ohne Zusatz-Zähler für Tageswerte** | ℹ️ INFO | Betrifft **zusätzliche** Messstellen, nicht die Abdeckung oben: Wärmepumpe `heizenergie_kwh` / `warmwasser_kwh` (Wärmemengenzähler) sowie `ladung_pv_kwh` an Wallbox bzw. E-Auto. Ohne sie bleiben genau diese Werte in *Cockpit → Tag* auf „—"; die **Monats**auswertungen sind nicht betroffen, dort lassen sich die Werte von Hand pflegen. Bewusst INFO — solche Zähler hat längst nicht jede Anlage. | Wenn vorhanden: Einstellungen → Datenquellen → das jeweilige kWh-Feld zuordnen. Sonst nichts zu tun. |

> ### ⭐ Was hier „zugeordnet" heißt — seit v4.0.29 auch MQTT
>
> Alle drei Befunde oben stellen dieselbe Frage: *Trägt dieses Feld einen
> kumulativen Zähler?* Bis v4.0.28 hieß die Antwort darauf **„gibt es dafür
> einen Home-Assistant-Sensor?"** — und wer seine Werte per **MQTT** schickt,
> hat gar keinen Sensor zuzuordnen. Er bekam alle drei Meldungen zu Unrecht,
> ohne sie abstellen zu können: Der „Beheben"-Knopf führte in ein Formular, in
> dem das Feld nicht vorkommt.
>
> **Seit v4.0.29 trägt ein Feld einen Zähler, wenn**
>
> 1. ihm ein **Home-Assistant-Sensor** zugeordnet ist, **oder**
> 2. dafür **Zählerstände per MQTT ankommen**.
>
> Hast du für ein Feld ausdrücklich **„Keine"** gewählt, bleibt das deine
> Absage — sie schlägt beides.
>
> ⚠ **Entscheidend ist der Messwert, nicht der Eintrag.** Ein Feld, das auf
> *MQTT-Inbound* steht, weil eedc das beim Einrichten als Grundeinstellung
> gesetzt hat, gilt **nicht** automatisch als versorgt — sonst würde diese
> Prüfung bei jeder Anlage schweigen, auch bei der, die gar nichts misst. eedc
> sieht nach, ob auf dem Topic tatsächlich etwas angekommen ist.
>
> ⚠ **Das Fenster ist eine Woche.** Bleibt einer der Befunde stehen, obwohl du
> per MQTT publizierst, heißt das: **Auf diesem Topic kam seit über sieben
> Tagen nichts an.** Dann ist die Meldung richtig und einen Blick wert — prüfe
> deinen Publisher, nicht die Zuordnung.

> **Ein „—" in *Cockpit → Tag* sagt seit v4.0.29 selbst, woran es liegt** — und das ist mehr als dieser Befund abdeckt. Drei Lagen führen dorthin, und nur die erste ist eine Aufgabe für dich: *Kein Zähler zugeordnet* · *Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände vor* · *Der Zähler ist an diesem Tag zurückgesprungen*. Der Grund steht sichtbar unter der Zahl.
>
> ⚠ **Der mittlere Fall ist der Regelfall kurz nach einer Zuordnung und keine Fehlfunktion:** Der **Monats**wert steht da, weil er aus der Langzeitstatistik von Home Assistant kommt — **Tages**werte entstehen erst ab dem Zeitpunkt der Zuordnung. Frühere Tage lassen sich über die Reparatur-Werkbank nachrechnen. Bis v4.0.28 stand an dieser Stelle unterschiedslos *„Sensor zuordnen"*, auch wenn er zugeordnet war; ein Melder hat daraufhin zu Recht gefragt, was die Anzeige ihm sagen will.

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
| **N MQTT-Topic(s) erwartet, nie empfangen** | ⚠️ WARNING | Subscriber läuft, aber für die genannten Topics liefert noch keine Quelle Daten. Beispiele werden mit **vollem Topic-Pfad** gelistet (max. 6, Rest aggregiert) — „leistung_w" gibt es an jedem Gerät, erst der Pfad sagt an welchem. **Gemeldet wird nur, was auch über MQTT kommen soll:** Felder, deren Quelle auf **Keine** oder einen **HA-Sensor** steht, tauchen nicht auf. Felder über ein **MQTT-Gateway** schon — dessen Werte laufen durch denselben Kanal. | Mögliche Ursachen: (a) Publisher-Automation noch nicht eingerichtet — siehe [HANDBUCH_EINSTELLUNGEN.md §7.5 MQTT-Topic zuordnen](HANDBUCH_EINSTELLUNGEN.md#75-ein-mqtt-topic-zuordnen). (b) Komponenten-IDs nach Re-Import nicht in der Automation nachgezogen — die Topic-Struktur enthält die eedc-interne ID. (c) Wird ein einzelnes Feld nicht über MQTT versorgt: unter *Einstellungen → Datenquellen* dessen Quelle auf **Keine** stellen. (d) Werden die Topics gar nicht gebraucht: MQTT-Import deaktivieren. |
| **N MQTT-Topic(s) mit veralteten Werten** | ⚠️ WARNING | Topics werden grundsätzlich empfangen, aber älter als der Schwellwert. Beispiele zeigen Topic + Alter in Minuten. | Publisher-Automation prüfen: läuft sie noch? Hat sie ihre Quelle verloren (z. B. Wechselrichter offline)? Bei dauerhaft fehlenden Quellen die Automation aufräumen oder die Datenquellen-Zuordnung anpassen. |
| **Alle N erwarteten MQTT-Topics aktuell empfangen** | ✅ OK | Subscriber läuft, alle erwarteten Topics liefern frische Daten innerhalb der Toleranz. | – |

> **Wichtig zur Skip-Logik:** Wenn der MQTT-Import nicht aktiviert ist, erscheint diese Kategorie gar nicht — nicht „OK", nicht „leer". So bleibt die Daten-Checker-Übersicht für Nutzer ohne MQTT übersichtlich.

---

### 4.8a Zählerstände – Rücksprung <a name="48a-zaehlerstaende--ruecksprung"></a>

> **Variantenhinweis:** Diese Kategorie greift, sobald Zählerstände über MQTT ankommen. Über Home Assistant ist sie gegenstandslos — dort liefert die Langzeitstatistik einen bereits bereinigten Stand, ein Verbrauchszähler mit Tageszyklus ist also unschädlich.

**Was wird geprüft:** Steigt jeder per MQTT gelieferte Zählerstand fortlaufend, oder fällt er zwischendurch auf einen niedrigeren Wert zurück? Geprüft werden die letzten **30 Tage** der mitgeschriebenen Stände.

**Warum das zählt.** eedc bildet aus zwei Ständen eine Menge — Anfang und Ende des Zeitraums, die Differenz dazwischen. Springt der Zähler dazwischen auf null zurück, gehören die beiden Stände zu **verschiedenen Zählerläufen**, und ihre Differenz ist keine Menge. Typisch ist das bei einem Feld, das „heute" oder „diesen Monat" meint statt des Gesamtstandes.

**Was eedc dann tut:** Es liefert für dieses Feld **keinen Wert** — im Monatsabschluss steht kein Vorschlag, in *Cockpit → Monat* bleibt der gespeicherte Wert stehen. Das ist Absicht: Eine Zahl, die aus zwei unzusammenhängenden Zählerläufen entsteht, sähe aus wie eine Messung und wäre keine.

> ⚠ **eedc rechnet den fehlenden Teil auch nicht hoch**, obwohl es die Stundenstände hätte. Was zwischen dem letzten mitgeschriebenen Stand und dem Rücksprung verbraucht wird, taucht in keinem Stand mehr auf — eine hochgerechnete Zahl wäre systematisch zu niedrig und im Monatsabschluss per Knopfdruck ein gespeicherter Wert. Diese Entscheidung ist bewusst gefallen.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Zähler-Feld(er) werden zwischendurch zurückgesetzt** | ⚠️ WARNING | Die Standreihe dieser Felder fällt innerhalb der letzten 30 Tage mindestens einmal. Die Meldung nennt die betroffenen Felder, wie oft es passiert ist, und belegt den jüngsten Fall mit beiden Ständen. | Schicke den **fortlaufenden** Stand statt des Tageswerts. Kommt der Wert aus einem Home-Assistant-Helfer: *Einstellungen → Geräte & Dienste → Helfer*, Verbrauchszähler öffnen, Zurücksetzen auf **„nie" (ohne Zyklus)** stellen. Kommt er aus einer eigenen App oder einem Skript, sende den Lebenszählerstand. eedc bildet Tag, Monat und Jahr daraus selbst — und exakt. |

> **Kein Reparatur-Knopf, und das ist kein Versehen.** eedc kann einen Rücksprung nicht heilen: Die fehlende Energie steht in keiner Quelle. Die Reparatur liegt beim Absender. Sobald die Reihe wieder fortlaufend ist, verschwindet der Befund von selbst — es gibt nichts zu quittieren.

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
>
> ⚠ **Ein Cloud-Import ist kein Geräte-Connector.** Beide stehen unter *Einstellungen → Integration → Import-Assistenten*, sind aber verschiedene Dinge: Der **Geräte-Connector** spricht deinen Wechselrichter **im eigenen Netz** über seine lokale Schnittstelle an; ein **Cloud-Import** (Fronius Solar.web, SolarEdge, Growatt, EcoFlow …) holt Daten vom **Portal des Herstellers**. Wer nur einen Cloud-Import eingerichtet hat, bekommt hier **keinen** Befund. Bis eedc 4.0.22 war das anders — siehe [Was ist neu](WAS-IST-NEU.md).

**Was wird geprüft:** Kann eedc aus den gespeicherten Zählerständen des Connectors für den **laufenden Monat** überhaupt einen Wert bilden? Ein Connector-Wert ist immer die **Differenz zweier Snapshots** — einer muss vor dem Monatsbeginn liegen, einer danach. Fehlt einer davon, liefert der Connector für diesen Monat gar nichts, und das war bisher nirgends zu sehen: In *Cockpit → Monat* stand einfach eine Quelle weniger, ohne Hinweis darauf, dass eine eingerichtete Quelle gerade schweigt.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Connector „…" liefert für MM/JJJJ keinen Wert** | ⚠️ WARNING | Es liegen nicht genügend Zählerstände vor, um den laufenden Monat zu berechnen — entweder erst einer insgesamt, oder der jüngste ist mehrere Tage alt (der Abruf steht still). Die Details nennen den Bestand und wann der tägliche Abruf zuletzt lief. | Der tägliche Abruf läuft bei **jedem** eingerichteten Connector um **3:30 Uhr** — er lässt sich weder ein- noch ausschalten. Steht trotzdem nichts Neues da, die Verbindung prüfen (Gerät erreichbar? Zugangsdaten noch gültig?) und unter *Einstellungen → Integration → Import-Assistenten → **Geräte-Connector*** mit **Jetzt ablesen** von Hand auslösen; scheitert der Abruf, steht der Grund dort und im Aktivitätsprotokoll. Sobald ein zweiter Zählerstand vorliegt, verschwindet der Befund von selbst. |

**Kein Lärm am Monatsersten.** Solange der Connector aktiv liefert, fehlt ihm am 1. eines Monats bis zum ersten Abruf naturgemäß der Snapshot *im* Monat. Dieser Zustand erledigt sich innerhalb eines Tages und wird deshalb nicht gemeldet — der Befund erscheint erst, wenn der jüngste Zählerstand älter als zwei Tage ist (oder es überhaupt erst einen gibt).

> **Abgrenzung:** Liefert der Connector einen Wert, misst er aber nur einen **Teil** des Monats (frisch eingerichtet), ist das kein Befund — dort steht eine Zahl, und sie wird in *Cockpit → Monat* mit ihrem Zeitraum beschriftet: „Connector (28.–30.07.2025)". Siehe [HANDBUCH_BEDIENUNG.md §2.3](HANDBUCH_BEDIENUNG.md#23-monat).

---

### 4.12 Zeitzone – Abweichung zu Home Assistant <a name="412-zeitzone--abweichung-zu-home-assistant"></a>

> **Variantenhinweis:** Nur relevant, wenn eine Verbindung zu Home Assistant besteht — als Add-on oder per Zugriffstoken. Ohne HA-Verbindung wird die Kategorie still übersprungen: Es gäbe nichts zu vergleichen und nichts zu tun.

**Was wird geprüft:** Rechnen eedc und Home Assistant mit derselben Uhrzeit? Verglichen wird der **aktuelle UTC-Abstand** beider Systeme, nicht der Name der Zeitzone — Wien, Zürich und Amsterdam gehen genauso wie Berlin, und dort wäre eine Meldung falsch.

**Warum das zählt:** Läuft eedc in einem Container ohne gesetzte Zeitzone, arbeitet er auf UTC. Der Tag endet dann für eedc um 22:00 Ortszeit, und die letzten Stunden werden dem Folgetag zugerechnet. Betroffen sind alle Tageswerte — Cockpit → Tag, Energieprofil, Tagesabschlüsse.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **eedc und Home Assistant rechnen mit verschiedenen Zeitzonen (… Unterschied)** | ⚠️ WARNING | Die beiden Systeme liegen um mindestens eine Stunde auseinander. Die Details nennen die Zeitzone von Home Assistant und den Abstand. | **Als Add-on:** eedc übernimmt die Zeitzone beim Start von Home Assistant — Add-on einmal neu starten. **Standalone:** `TZ=Europe/Berlin` (bzw. deine Zeitzone) als Umgebungsvariable setzen und den Container neu starten, siehe [HANDBUCH_INSTALLATION.md §2](HANDBUCH_INSTALLATION.md#2-installation). |

**Was der Befund nicht leistet:** Er beschreibt den Zustand von **jetzt**. Bereits gespeicherte Tage werden dadurch nicht korrigiert — die lassen sich nach dem Neustart über *Einstellungen → Datenverwaltung* neu berechnen.

---

### 4.13 Sonstige Positionen – der Erfassungsort <a name="413-sonstige-positionen--der-erfassungsort"></a>

**Was wird geprüft:** Steht ein Betrag, der **jedes Jahr wiederkommt**, an der Stelle, an der er auch in die Zukunft wirkt?

**Warum das zählt:** eedc fragt nie, ob ein Betrag einmalig oder wiederkehrend ist — es liest das am **Ort** deiner Eingabe. Ein Jahresbetrag an der Komponente (*Kosten/Jahr*, *Ertrag/Jahr*) wirkt jedes Jahr, also auch in Prognose und Amortisation. Eine Position im Monatsabschluss ist per Form **einmal** geflossen: Sie zählt in der Bilanz ihres Monats und im Amortisations-Fortschritt, aber nie in der Vorhersage. Das ist der Grund, warum eedc nichts raten muss — und zugleich die einzige Stelle, an der man es verfehlen kann.

**Woran eedc das erkennt: an der Wiederholung, nie an der Bedeutung.** Aus „Restwert", „Verkauf" oder „Förderung" auf etwas zu schließen wäre geraten — genau das tut eedc an keiner Stelle.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Komponente\]: „\[Bezeichnung\]" steht in N Monaten im Monatsabschluss — das sieht wiederkehrend aus** | ℹ️ INFO | Dieselbe Bezeichnung taucht an einer Komponente in **mindestens drei** Monaten auf, und an der Komponente ist **kein** passender Jahresbetrag gepflegt. Als Monatsposition wirkt der Betrag nur in der Bilanz des jeweiligen Monats. | Komponente öffnen (*Bearbeiten → Weitere Angaben & Kosten*) und den Betrag als **Kosten/Jahr** bzw. **Ertrag/Jahr** eintragen. Dort wirkt er auch in Prognose und Amortisation. **Einmaliges bleibt richtig, wo es ist** — der Hinweis verlangt nichts, er zeigt eine bessere Stelle. |
| **\[Komponente\]: „\[Bezeichnung\]" steht in N Monaten im Monatsabschluss, obwohl \[Feld\] gepflegt ist** | ℹ️ INFO | Der Jahresbetrag ist hinterlegt **und** derselbe Posten wird zusätzlich monatlich gebucht — der Betrag zählt damit doppelt. | Entweder den Jahresbetrag anpassen **oder** die Monatspositionen entfernen. In den Monatsabschluss gehört nur die **Abweichung** vom Plan: die Nachzahlung, nicht die ganze Rechnung. |

> **Beides sind Hinweise, keine Fehler.** Deine Erfassung ist nicht falsch — sie steht nur an der Stelle, an der sie weniger kann. Es gibt deshalb auch keinen „Akzeptiert"-Knopf: Wer den Betrag bewusst monatlich pflegt, lässt den Hinweis stehen.
>
> **Das Feld „Ertrag/Jahr" gibt es nur bei *Wallbox* und *Sonstiges*.** Bei allen anderen Komponenten rechnet eedc die Jahres-Einsparung selbst; dort meldet der Checker auf der Ertragsseite bewusst nichts, statt auf ein Feld zu verweisen, das im Formular nicht steht.

Hintergrund und die verworfenen Alternativen: [Berechnungen §3.6](BERECHNUNGEN.md#36-roi--amortisation) und [Bedienung → Auswertungen → ROI](HANDBUCH_BEDIENUNG.md#42-roi).

---

### 4.14 Klimaanlage – Betriebsmodus <a name="414-klimaanlage--betriebsmodus"></a>

**Was wird geprüft:** Ist bei einer Split-Klimaanlage (Wärmepumpenart *Luft-Luft*) der Betriebsmodus-Sensor zugeordnet?

**Warum das zählt:** Deine Klimaanlage heizt im Winter und kühlt im Sommer — über **denselben** Stromzähler. eedc sieht deshalb nur eine Zahl „Stromverbrauch" und kann nicht sagen, welcher Teil davon ins Heizen ging und welcher ins Kühlen. Aus den vorhandenen Werten lässt sich das auch nicht nachrechnen: Es gibt kein Feld, aus dem die Aufteilung ableitbar wäre. Sie entsteht nur, wenn eedc **zur Messzeit mitschreibt**, in welchem Modus das Gerät gerade läuft.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **„\[Gerät\]": Betriebsmodus nicht zugeordnet — Heiz- und Kühlstrom bleiben zusammen** | ℹ️ INFO | Für dieses Gerät gibt es **keinen** der beiden Wege zur Aufteilung (siehe Kasten darunter). Der Stromverbrauch zählt vollständig und richtig; es fehlt nur die Aufteilung. | *Einstellungen → Datenquellen*, beim Gerät das Feld **Betriebsmodus** zuordnen. In Home Assistant ist das die **climate-Entität** deines Geräts (meist `climate.…`) — sie zeigt Heizen/Kühlen/Aus. |
| **Betriebsmodus ist zugeordnet bei N Klimaanlage(n)** | ✅ OK | eedc schreibt stündlich mit, ob geheizt oder gekühlt wurde, und teilt den Strom danach auf. | — |
| **Betriebsart wird gemessen bei N Klimaanlage(n)** | ✅ OK | Der Verbrauch je Betriebsart kommt aus eigenen Zählern. eedc liest ihn ab, statt ihn zu rechnen. | — |
| **Heiz- und Kühlstrom werden getrennt bei N Klimaanlage(n)** | ✅ OK | Gemischt: ein Teil der Geräte misst, beim Rest leitet eedc aus dem Betriebsmodus ab. | — |

> **Es gibt zwei Wege zu dieser Aufteilung, und der gemessene gewinnt.**
>
> 1. **Gemessen** — du ordnest eigene Zähler je Betriebsart zu (*Strom Heizbetrieb*, *Kühlbetrieb*, *Lüftbetrieb*, *Entfeuchtung*), am Gerät oder je Innengerät. Wer sie in Home Assistant nicht direkt bekommt, baut sie sich mit einem **Utility Meter** je Betriebsart.
> 2. **Abgeleitet** — du ordnest den **Betriebsmodus** zu, und eedc schreibt stündlich mit, was das Gerät gerade tat.
>
> Liegen **gemessene** Werte vor, rechnet eedc die abgeleitete Aufteilung für dieses Gerät gar nicht erst — ganz oder gar nicht, nie beides gemischt. Eine Zuordnung des Betriebsmodus wäre dann wirkungslos. Deshalb erscheint der Hinweis oben **nicht mehr**, sobald einer der beiden Wege eingerichtet ist (oder Werte auf einem von beiden angekommen sind).

> ⚠ **Die Aufteilung lässt sich nicht rückwirkend nachtragen — das ist der wichtigste Satz hier.** Home Assistant bewahrt Zustände wie „Heizen"/„Kühlen" nur wenige Tage auf (die Langzeit-Statistik gibt es nur für Zahlen-Sensoren). Wer den Sensor heute zuordnet, bekommt die Aufteilung **ab heute**; die Vergangenheit bleibt ungeteilt, und ein längerer eedc-Ausfall reißt eine Lücke, die bleibt. Deshalb lohnt sich die Zuordnung auch dann, wenn man die Auswertung noch nicht braucht.

> **Der Hinweis erscheint nur bei Wärmepumpenart *Luft-Luft*.** Ob ein Gerät überhaupt kühlen kann, hängt an seiner Bauart — eine Luft-Wasser-Wärmepumpe bekäme sonst einen Hinweis auf eine Aufteilung, die es bei ihr nicht gibt. **Das Feld selbst bietet eedc trotzdem jeder Wärmepumpe an**: Es gibt Luft-Wasser-Geräte mit Kühlfunktion, und wer eines hat, findet den Betriebsmodus auf der Datenquellen-Fläche.

> **Der Betriebsmodus ist nur als HA-Sensor zuordenbar, nicht über MQTT.** Er ist ein Zustand, kein Messwert — der MQTT-Weg von eedc nimmt ausschließlich Zahlen entgegen. Die Fläche blendet die MQTT-Optionen für dieses eine Feld deshalb aus, statt eine Quelle anzubieten, die nichts liefern könnte.


> **Was du nach der Zuordnung siehst** (seit 2026-08-19): Unter *Komponenten → Wärme/Klima* steht
> ein Block **„Aufteilung Heizen/Kühlen"** mit den beiden Strommengen, der Zeile *nicht aufgeteilt*
> und der Zahl der Stunden, in denen eedc mitlesen konnte. Dieselbe Aufteilung erscheint in
> *Cockpit → Monat* und *Cockpit → Jahr*, dazu zwei Sensoren in Home Assistant. Die Aufteilung
> entsteht beim **Monatsabschluss**; für den laufenden Monat wird sie direkt aus den Tageswerten
> gelesen.

#### Verwandter Befund: Aufteilung größer als der Gesamtverbrauch

> **Wo er steht:** nicht in dieser Kategorie, sondern unter **Investitionen** (§4.3) — er hängt an den Monatswerten des Geräts, nicht an der Sensor-Zuordnung. Hier steht er trotzdem, weil er dieselbe Aufteilung betrifft.

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **„\[Gerät\]": Heiz- und Kühlstrom zusammen größer als der Gesamtverbrauch (Monate)** | ⚠️ WARNING | Die Aufteilung ist ein **Teil** des Gesamtverbrauchs — zusammen können beide ihn nicht übersteigen. Das entsteht, wenn der Gesamtwert nachträglich kleiner eingetragen wurde als die bereits erfasste Aufteilung. | Zwei Wege: Prüfe den **Stromverbrauch** dieser Monate im Monatsabschluss — oder schließe den Monat **erneut ab**, dann rechnet eedc die Aufteilung neu und verwirft sie, falls sie nicht passt. |

> **eedc biegt hier nichts zurecht.** Es wäre einfach, die Aufteilung stillschweigend auf den
> Gesamtwert zu kürzen — dann stünde da eine Zahl, die plausibel aussieht und trotzdem falsch ist.
> Stattdessen bleibt der Widerspruch sichtbar, bis du entschieden hast, welche der beiden Angaben
> stimmt. ⚠ **Deine Energiebilanz ist davon nicht betroffen:** dort zählt immer der Gesamtwert.

Hintergrund: [Issue #263](https://github.com/supernova1963/eedc-homeassistant/issues/263).

---

### 4.15 Sensor-Zuordnung – Leistung ↔ Energie verwechselt <a name="415-sensor-zuordnung--leistung--energie"></a>

**Was wird geprüft:** Steht in jedem Feld ein Sensor der passenden Art — ein **Leistungssensor** (W/kW) dort, wo eedc eine Momentanleistung erwartet, und ein **kWh-Zähler** dort, wo es eine Energiemenge erwartet? Verglichen wird die in Home Assistant hinterlegte Einheit, nicht der Wert.

**Warum das zählt:** Die beiden Größen sehen im Sensor-Namen oft gleich aus und bedeuten Verschiedenes. Ein Zählerstand in einem Leistungs-Feld wird als Momentanleistung gelesen — aus 7.130 kWh werden 7.130 W, und der live als Rest berechnete Hausverbrauch klemmt auf 0. Umgekehrt lässt sich aus einem Leistungssensor die Energie nur schätzen.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Leistungs-Slot „\[Feld\]" trägt einen Energie-Sensor (Einheit kWh)** | ❌ ERROR | Ein kWh-Zähler steht in einem Feld, das eine Momentanleistung erwartet. Der Live-Energiefluss rechnet damit falsch. | *Einstellungen → Datenquellen*, für dieses Feld einen Leistungssensor (W/kW) wählen. Die Meldung nennt die aktuell zugeordnete Entität. |
| **Energie-Slot „\[Feld\]" trägt einen Leistungssensor (Einheit W)** | ⚠️ WARNING | Ein Leistungssensor steht in einem kWh-Feld. eedc fällt auf eine Näherung zurück (Integration über die Zeit) — ungenauer und anfällig für Lücken. | *Einstellungen → Datenquellen*, einen kumulativen kWh-Zähler wählen. |

> **Nur diese eine Verwechslung wird gemeldet.** Ladestand (%), Temperatur (°C), Preis (ct/kWh) und Kilometer bleiben ungeprüft: Dort sind mehrere Einheiten legitim, und eine Meldung wäre öfter falsch als richtig. **Ohne HA-Verbindung** wird die Kategorie still übersprungen — die Einheit kommt aus Home Assistant.

---

### 4.16 Quellen-Konflikte <a name="416-quellen-konflikte"></a>

**Was wird geprüft:** Gab es in den letzten Tagen Felder, für die **mehr als eine** Quelle einen Wert geliefert hat — etwa ein HA-Sensor und zusätzlich ein MQTT-Topic?

**Warum das zählt:** Es ist kein Fehler. eedc hat sich bereits entschieden: Bei mehreren Quellen für dasselbe Feld gewinnt die höherwertige, und der angezeigte Wert stammt von ihr. Der Hinweis sagt nur, dass es die Konkurrenz gibt — nützlich, wenn eine Zahl anders aussieht als erwartet.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Felder hatten in den letzten \[X\] Tagen mehrere Quellen** | ℹ️ INFO | Für diese Felder haben zwei oder mehr Quellen geschrieben. Der angezeigte Wert kommt aus der höchstprioren. | **Nichts zu tun.** Wenn du die zweite Quelle nicht willst, entfernst du sie unter *Einstellungen → Datenquellen* — der Hinweis ist aber kein Auftrag. |
| **Keine Quellen-Konflikte in den letzten \[X\] Tagen** | ✅ OK | Jedes Feld hatte höchstens eine Quelle. | — |

---

### 4.17 Datenquellen-Drift zu Home Assistant <a name="417-datenquellen-drift"></a>

> **Variantenhinweis:** Nur mit HA-Verbindung. Ohne sie gibt es keine Vergleichsseite, die Kategorie wird still übersprungen.

**Was wird geprüft:** Stimmt das, was eedc für die letzten 90 Tage gespeichert hat, noch mit dem überein, was Home Assistant für denselben Tag ausweist? Geprüft werden **zwei Achsen**: die **PV-Tagessumme** über alle Erzeuger, und **jede andere zugeordnete Komponente einzeln** — Wallbox, E-Auto, Wärmepumpe, Sonstiges, dazu Einspeisung und Netzbezug.

**Warum das zählt:** eedc hat seine Tageswerte über die Zeit aus verschiedenen Quellen aufgebaut. Ältere Tage können auf einem Stand stehen, den ein heutiger Abruf anders beantwortet. Diese Werte tragen nicht nur die Energiebilanz, sondern auch Wirtschaftlichkeit und CO₂ — eine Abweichung an der Wallbox kostet genauso wie eine an der PV.

> **Warum PV als Summe und alles andere je Gerät.** Mehrere Strings messen dieselbe Sache; ihre Summe ist die Zahl, die du kennst. Zwei **Geräte** messen nicht dieselbe Sache: In einer gemeinsamen Summe würde ein Plus an der Wärmepumpe ein Minus an der Wallbox ausgleichen, und übrig bliebe eine unauffällige Null. *(Bis v4.0.33 verglich diese Prüfung ausschließlich die PV — für alle anderen Geräte gab es überhaupt keinen Abgleich mit Home Assistant.)*

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Tag(e) weichen von HA-Statistics ab** (PV) | ℹ️ INFO | Für diese Tage liegen eedc und HA bei der **PV-Tagessumme** um **mindestens 2 kWh und mindestens 5 %** auseinander. Beide Schwellen zusammen, damit Rundungs-Unterschiede still bleiben. Die Details nennen je Tag beide Zahlen. | Je Tag steht ein Knopf **„Tag reparieren"** daneben — er holt den Tag frisch aus HA. Massen-Reparaturen gibt es bewusst nur in der Reparatur-Werkbank, damit sie aktiv gewählt werden. |
| **\[Gerät\]: N Tag(e) weichen von HA-Statistics ab** | ℹ️ INFO | Dieselbe Frage für **eine** Komponente, mit denselben beiden Schwellen. **Ein Eintrag je Gerät**, nicht je Tag — genannt wird der Tag mit der größten Abweichung, samt beider Zahlen. | Der Knopf **„Tag reparieren"** rechnet den genannten Tag neu. Für alle Tage des Geräts: Reparatur-Werkbank. |
| **Keine signifikanten Abweichungen zu HA-Statistics (letzte 90 Tage)** | ✅ OK | eedc und HA sind sich auf beiden Achsen einig. | — |

> **Verglichen wird nur, was HA für den Tag auch liefern konnte.** Ein Zähler ohne Summen-Spalte (§4.9) taucht hier nicht als Lücke auf — sonst meldete der Vergleich Phantom-Drift und böte einen Knopf an, der korrekte Werte mit 0 überschreibt.
>
> **Und nur, was auf beiden Seiten einen Wert hat.** Liefert HA einen Wert und die gespeicherte Tageszeile nicht, ist das eine **Lücke** und gehört §4.10 *Energieprofil – fehlende Tageswerte* — kein zweiter Turm über denselben Sachverhalt. Der **Speicher** (`batterie_*`) steht in keiner der beiden Achsen: Sein Tages-Netto darf legitim ~0 sein, und sein Vorzeichen hat mit §4.21 *Batterie-Vorzeichen in der Historie* eine eigene Prüfung.

---

### 4.18 PV-Doppelerfassung (Verdacht) <a name="418-pv-doppelerfassung"></a>

**Was wird geprüft:** Liefert deine Anlage an mehreren Tagen **mehr**, als physikalisch plausibel ist? Zwei unabhängige Signale aus den letzten 30 Tagen: eine Performance Ratio über 1,05 und ein spezifischer Tagesertrag über 7 kWh/kWp.

**Warum das zählt:** Der häufigste Grund ist keine Wundertechnik, sondern **dieselbe Erzeugung zweimal gezählt** — etwa ein String-Sensor *und* der Anlagen-Summenzähler, beide zugeordnet. Alles, was auf der Erzeugung aufbaut, wird dadurch zu gut: Eigenverbrauch, Autarkie, Ersparnis, CO₂.

> **Der Verdacht hat zwei Seiten, und die zweite wird leicht übersehen.** Die Performance Ratio ist `Ertrag ÷ (Einstrahlung × kWp)`. Sie steigt also nicht nur, wenn der **Ertrag** zu hoch ist, sondern auch, wenn der **Vergleichsmaßstab** zu klein angesetzt ist — und der hat zwei Faktoren: die eingetragene kWp *und* die Einstrahlung. Wer alle Zuordnungen geprüft hat und nichts Doppeltes findet, sieht deshalb als Nächstes bei **Ausrichtung und Neigung der Module** nach (*Einstellungen → Anlage*): Ohne sie rechnet eedc mit einer Einstrahlung, die nicht zu deinem Dach passt.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **Verdacht auf PV-Doppelerfassung (PR > 1 oder spez. Ertrag zu hoch)** | ⚠️ WARNING | An mindestens drei Tagen liegen die Kennzahlen über dem physikalisch Möglichen. | Zuerst *Einstellungen → Datenquellen* öffnen und prüfen, ob dieselbe Erzeugung an zwei Stellen zugeordnet ist. **Regel:** Entweder je Erzeuger ein eigener Zähler **oder** ein Anlagen-Summenzähler — nicht beides. **Findet sich dort nichts:** unter *Einstellungen → Anlage* die kWp sowie **Ausrichtung und Neigung** der Module prüfen — beide gehen in den Vergleichsmaßstab ein (siehe Kasten oben). |
| **N auffällige(r) Tag(e) fallen mit einem Zähler-Sprung zusammen** | ℹ️ INFO | Die Auffälligkeit hat eine andere, bekannte Ursache: einen Ausreißer im Zählerstand. | Erst den Zähler-Sprung beheben (§5.6), danach erneut prüfen. |

> **eedc kürzt hier nichts.** Es gibt keinen Knopf, der die Erzeugung „gerade zieht" — die Entscheidung, welche Zuordnung die richtige ist, kann nur der Anlagenbetreiber treffen.

---

### 4.19 Ladung doppelt gezählt (Wallbox + E-Auto) <a name="419-ladung-doppelt-gezaehlt"></a>

**Was wird geprüft:** Gibt es gespeicherte Tage, an denen **Wallbox und E-Auto dieselbe Ladung** tragen?

**Warum das zählt:** Wer sein Auto zu Hause lädt, hat oft beide Geräte erfasst — die Wallbox misst, das Auto meldet. Beide Zahlen zu addieren verdoppelt den Verbrauch. eedc kennt die Regel inzwischen (*trägt die Wallbox die Ladeenergie, ist sie die Quelle*), aber **bereits gespeicherte** Tage tragen die alte Rechnung weiter.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Tag(e) zählen dieselbe Ladung doppelt** | ⚠️ WARNING | Für diese Tage steht die Heimladung zweimal in der Bilanz. Die Details nennen die Tage und beide Beträge. | Die betroffenen Tage über *Einstellungen → Datenverwaltung* neu berechnen. |
| **Keine doppelt gezählten Ladetage in den letzten \[X\] Tagen** | ✅ OK | Kein Tag trägt die Ladung zweimal. | — |

> ⚠ **Ein OK heißt hier „geprüft, soweit Tageswerte vorliegen"** — nicht „alles sauber". Tage ohne gespeicherte Komponentenwerte kann die Prüfung nicht ansehen.
>
> **Warum das kein automatischer Lauf beim Start ist:** Die Heilung überschreibt gespeicherte Messwerte. Das passiert in eedc nie ungefragt — du siehst den Befund, die Tage, und entscheidest.

---

### 4.20 Plug-in-Hybrid – elektrischer Anteil unbestimmt <a name="420-phev-anteil"></a>

**Was wird geprüft:** Ist bei einem Fahrzeug mit Verbrenner-Anteil bestimmbar, **welcher Teil der Kilometer elektrisch** gefahren wurde?

**Warum das zählt:** Trägt ein Fahrzeug einen Verbrauch in l/100 km, hat es einen Verbrennungsmotor. Um die Kilometer aufzuteilen, braucht eedc eine von zwei Angaben: den monatlich erfassten Fahrverbrauch in kWh (gemessen) oder einen gepflegten elektrischen Fahranteil in % (geschätzt). **Fehlen beide, rechnet eedc 100 % elektrisch** — Ersparnis und CO₂-Bilanz fallen dadurch zu gut aus. Ein Richtwert wäre erfunden; deshalb sagt eedc es lieber.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Fahrzeug\]: Verbrenner-Verbrauch gepflegt, aber der elektrische Anteil ist nicht bestimmbar** | ⚠️ WARNING | Weder monatlicher Fahrverbrauch noch elektrischer Fahranteil sind vorhanden. Bis dahin rechnet eedc mit 100 % elektrisch. | Entweder den **Fahrverbrauch (kWh)** im Monatsabschluss erfassen — der gemessene Weg — oder am Fahrzeug den **elektrischen Fahranteil (%)** pflegen. |

---

### 4.21 Batterie-Vorzeichen in der Historie <a name="421-batterie-vorzeichen-historie"></a>

**Was wird geprüft:** Tragen gespeicherte Tage die Batterie-Richtung noch **verkehrt herum**?

**Warum das zählt:** Bis eedc 3.45.7 schrieb die Tages-Aggregation das Batterie-Netto in umgekehrter Richtung. Der Fehler steht in bereits gespeicherten Tagen, bis sie neu berechnet werden. **Die Live-Ansicht ist nicht betroffen** — sie hat einen eigenen Weg. Betroffen sind Energieprofil und Tages-Historie.

Erkannt wird das am **Datensignal**, nicht am Datum: Der gespeicherte Tageswert wird gegen einen frischen Abruf verglichen. Zeigen beide in entgegengesetzte Richtungen, ist der Tag mit der alten Logik gerechnet.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Tag(e) mit vertauschtem Batterie-Vorzeichen** | ⚠️ WARNING | Diese Tage tragen Ladung und Entladung vertauscht. | Der Befund bringt einen Knopf mit, der den betroffenen Bereich neu berechnet. |
| **Batterie-Vorzeichen in der Historie konsistent (letzte 90 Tage)** | ✅ OK | Kein Tag zeigt in die falsche Richtung. | — |

> **Eine reine Betrags-Abweichung wird hier bewusst nicht gemeldet** — nur die vertauschte Richtung. Gleiche Richtung mit anderem Betrag ist ein eigenes Thema und kein Vorzeichenfehler.

---

### 4.22 Ladestand bei mehreren Speichern <a name="422-ladestand-mehrere-speicher"></a>

**Was wird geprüft:** Kennt die gespeicherte Historie bei einer Anlage mit **mehreren** Speichern den Ladestand **aller** Geräte — oder nur den eines einzelnen?

**Warum das zählt:** Bis August 2026 nahm eedc den ersten gefundenen Ladestand-Sensor und rechnete mit ihm, als gälte er für die ganze Anlage. Welcher das war, entschied die Reihenfolge der Zuordnung. Vollzyklen, Ladestand-Hübe und die Speicher-Auslegung lasen ihn aber als anlagenweit.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Tag(e) kennen nur den Ladestand eines von \[X\] Speichern** | ⚠️ WARNING | Diese Tage stammen aus der Zeit vor der Korrektur. | Der Befund bringt einen Knopf mit, der den Bereich neu berechnet. |
| **Ladestand aller \[X\] Speicher wird in der Historie geführt** | ✅ OK | Jeder Speicher steht mit seinem eigenen Ladestand da. | — |

> **Anlagen mit einem Speicher erscheinen hier nie.** Dort war die alte Rechnung mit der neuen wertgleich — es gibt nichts zu reparieren.

---

### 4.23 Verbrauchszähler – Zählerstände <a name="423-verbrauchszaehler-zaehlerstaende"></a>

**Was wird geprüft:** Kommt für einen Gas-, Wasser- oder Ölzähler überhaupt ein Stand an, läuft seine Reihe irgendwo **rückwärts**, und ist das Gerät versehentlich auf *nicht aktiv* gesetzt?

**Warum das zählt:** Ein Verbrauchszähler führt genau **einen** Wert — den Zählerstand. Die einzige Rechnung darauf ist *Ende minus Anfang* des angezeigten Zeitraums. Er geht bewusst in **keine** Bewertung ein: nicht in Energiebilanz, Autarkie, Wirtschaftlichkeit, CO₂-Bilanz oder den Community-Vergleich. Genau deshalb fallen Probleme mit ihm nirgends sonst auf — keine Kennzahl wird auffällig, es steht einfach überall „—".

> **Kein Verbrauchszähler eingerichtet ⇒ diese Kategorie erscheint gar nicht.**

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **\[Zähler\]: kein Zählerstand erfasst** | ⚠️ WARNING | Für dieses Gerät liegt kein einziger Stand vor — weder aus einem Sensor noch von Hand. | Zwei gleichwertige Wege: einen Sensor unter *Einstellungen → Datenquellen* zuordnen (eedc schreibt den Stand dann stündlich mit), **oder** den Stand beim Monatsabschluss ablesen und im Feld *Zählerstand* eintragen. Für einen Gaszähler ohne Fernauslesung ist der zweite Weg der vorgesehene. |
| **\[Zähler\]: der Stand ist N-mal gefallen — die Reihe hat einen Bruch** | ⚠️ WARNING | Ein Zählerstand läuft nicht rückwärts. Für Zeiträume über eine solche Stelle hinweg zeigt eedc deshalb **keine** Differenz statt einer negativen Menge. | Drei mögliche Ursachen, s. u. |
| **\[Zähler\]: auf „nicht aktiv" gesetzt — N Ablesung(en) ausgeblendet** | ℹ️ INFO | Der Haken *aktiv* ist entfernt. In eedc heißt das „wie gelöscht": die Ablesungen erscheinen nirgends mehr, **auch nicht für die Vergangenheit**. | War es ein Zählerwechsel, ist der Weg ein anderer — s. u. Ist das Gerät bewusst so gesetzt, ist alles in Ordnung; der Hinweis bleibt dann stehen. |
| **\[Zähler\]: N Zählerstand-Ablesung(en) erfasst** | ✅ OK | Der Zähler liefert. | — |

#### Woher ein Reihenbruch kommt

1. **Zähler gewechselt.** Der neue Zähler beginnt bei einem niedrigeren Stand. → Am **alten** Gerät ein **Stilllegungsdatum** setzen und ein neues anlegen. ⚠ Den Haken *aktiv* dabei **stehen lassen**: er bedeutet „wie gelöscht" und würde die alte Historie aus allen Auswertungen entfernen. Danach ist der Verbrauch über den Wechsel hinweg sauber die **Summe beider** Differenzen.
2. **Sensor getauscht oder Stand von Hand korrigiert**, und der neue Wert liegt unter dem alten.
3. **Der Umstieg auf eedc 4.0.25.** Bis dahin schrieb eedc für Verbrauchszähler die *Verbrauchssumme* von Home Assistant mit statt des *Zählerstands* (s. Changelog 4.0.25). Lag die Summe höher als der Stand, fällt die Reihe an genau einer Stelle — an der Umstellung, **einmalig**, und es ist nichts kaputt. Über *Einstellungen → Daten → „Tag neu berechnen"* zieht eedc die Historie nach, soweit Home Assistant sie noch hat.

> **eedc heilt einen Bruch nicht von selbst** — dafür müsste es raten, welcher der beiden Stände gilt. Diese Entscheidung gehört dir, deshalb steht hier der Weg und kein Knopf.

---

### 4.24 Vergleichspreise – Ø Benzinpreis <a name="424-vergleichspreise-benzinpreis"></a>

**Was wird geprüft:** Trägt jeder Monat, in dem du ein E-Auto hast, den Ø-Benzinpreis dieses Monats?

**Warum das zählt:** Der Vergleich „was hätte dieselbe Strecke mit Benzin gekostet?" ist der Kern der E-Auto-Wirtschaftlichkeit. eedc rechnet ihn **Monat für Monat mit dem Preis des jeweiligen Monats** — ein Monat aus 2023 mit dem Preis von 2023. Die Werte holt eedc täglich selbst aus dem *EU Weekly Oil Bulletin* der Europäischen Kommission (nationale Durchschnittspreise für Super 95 inklusive Steuern, Datenbestand seit 2005); du musst dafür nichts eintragen.

Fehlt der Wert für einen Monat, rechnet eedc trotzdem weiter — dann aber mit dem **Modellwert** aus den Angaben zur Komponente (ersatzweise 1,65 €/L). Das ist der eine Preis von heute statt des damaligen: Der *Fortschritt* behauptet dann eine Messung und liefert eine Schätzung. Genau deshalb steht diese Prüfung hier.

> **Kein E-Auto angelegt ⇒ diese Kategorie erscheint gar nicht.** Und Monate **vor** der Anschaffung des Fahrzeugs zählen nicht mit — es gab dort nichts zu vergleichen.

#### Befunde

| Meldung | Severity | Bedeutung | Behebung |
|---------|----------|-----------|----------|
| **N Monat(e) ohne Ø-Benzinpreis (MM/JJJJ … MM/JJJJ)** | ⚠️ WARNING | Für diese Monate liegt kein Marktpreis vor. Typisch nach einem **Import** älterer Monate oder direkt nach der Einrichtung — der Nachlauf hat sie noch nicht gesehen. | Knopf **„Vergleichspreise nachpflegen"** direkt am Befund. Er holt die Wochenpreise für alle offenen Monate; **bestehende Werte bleiben unberührt**, mehrfaches Ausführen ist gefahrlos. Danach erneut prüfen. |
| **Alle Monate mit E-Auto tragen einen Ø-Benzinpreis** | ✅ OK | Der Vergleich rechnet durchgehend mit den damaligen Preisen. | — |

#### Wo du den Wert siehst

*Einstellungen → Daten → Monatsdaten* → Monat öffnen → Abschnitt **Vergleichspreise** → **„Ø Benzinpreis"**. Dort kannst du auch einen eigenen Wert eintragen — ein von Hand gesetzter Preis wird **nie** überschrieben.

> **Warum das jetzt seltener vorkommt:** Früher lief der Nachlauf **wöchentlich** (dienstags), und ein verpasster Lauf wurde nie nachgeholt. Ein Monat, der kurz nach einem Lauf entstand, wartete bis zu sieben Tage auf seinen Preis — ohne dass irgendetwas darauf hinwies. Seither läuft er **täglich** und zusätzlich kurz nach jedem Start von eedc. Aufgefallen ist das, weil ein Anwender nachgesehen hat, statt der Zusage zu glauben ([Discussion #394](https://github.com/supernova1963/eedc-homeassistant/discussions/394)).

---

## 5. Behebungs-Workflows

Diese Querschnitts-Anleitungen bündeln Schritte, die mehrere Befunde gleichzeitig betreffen — typischerweise weil ein einzelner Konfigurationsfehler in mehreren Kategorien aufschlägt.

### 5.1 `state_class`-Probleme bei HA-Sensoren beheben

**Symptom:** Jeder der vier WARNING-Befunde aus §4.9 — *„kWh-Sensor(en) nicht in HA-Long-Term-Statistics"*, *„Counter-Sensor(en) ohne state_class"*, *„kWh-Sensor(en) ohne Summen-Spalte"* und *„Counter-Sensor(en) ohne Summen-Spalte"*. Alle vier führen auf denselben Handgriff.

**Ursache:** HA legt für einen Sensor erst dann Long-Term-Statistics an, wenn dessen Attribut `state_class` gesetzt ist. Typisch sind kumulative Zähler ohne diese Metadaten bei Modbus-Roh-Werten oder Hersteller-Integrationen.

> ⚠ **Für einen Verbrauchszähler (Gas/Wasser/Öl) gilt nur die halbe Anleitung.** Sein Stand wird aus dem Sensor-*Zustand* gelesen, nicht aus einer Verbrauchssumme — eine **Summen-Spalte braucht er nicht**, `state_class: measurement` genügt vollauf. Deshalb meldet eedc für ihn auch keinen „ohne Summen-Spalte"-Befund, sondern nur *„Zählerstand-Sensor(en) nicht in HA-Long-Term-Statistics"*. Einen Verbrauchszähler-Helfer anzulegen wäre hier die falsche Empfehlung: Der zählt eine Menge, du willst die Zahl auf deinem Zähler.

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

#### Ein Anlagen-Gesamtzähler reicht — aber dann für alle

Der Zählerstand unter *Anlage (Basis) → PV-Erzeugung Zählerstand (kWh)* versorgt **Monat, Tag und Stunde** als **Summe der ganzen Anlage**. Wenn dein Wechselrichter nur einen Gesamtzähler liefert, ist das eine vollständige Erfassung — du musst nichts weiter einrichten. Was dir fehlt, ist die **Aufschlüsselung je Erzeuger**: eedc kann dann nicht sagen, wie viel „Dach Süd" und wie viel „Dach West" beigetragen hat.

> ⚠ **Entweder die Anlagensumme oder die Einzelwerte — nie beides.** Sobald **ein** Erzeuger einen eigenen kWh-Zähler bekommt, zählt für Tag und Stunde nur noch, was je Erzeuger gemessen ist; der Anlagen-Zählerstand ist dort dann aus. Ordnest du also einem von drei Strings einen Zähler zu, siehst du in Cockpit → Tag nur noch diesen einen. **Entweder alle oder keiner.** (Grund: sonst stünde die Anlagensumme neben ihren eigenen Bestandteilen und alles würde doppelt gezählt.) Deine **Monatswerte** bleiben in jedem Fall vollständig.

**Wenn du je String aufschlüsseln willst und dein Wechselrichter dort nur Leistung (W) liefert:** Daraus baut Home Assistant selbst einen Zähler.

1. **Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → „Integral-Sensor"** (Riemannsche Summe) wählen.
2. Als **Eingangssensor** den Leistungssensor des Strings angeben, **Integrationsmethode „Linke Riemann-Summe"**, **metrisches Präfix „k"** und **Zeiteinheit „Stunden"** — so entsteht ein kWh-Wert. Keinen Zyklus einstellen.
3. **Maximales Teilintervall** auf **1 Minute** setzen (Feld `max_sub_interval`). Ohne diese Angabe verbucht der Helfer eine lange Phase konstanter Leistung erst dann, wenn sich der Wert wieder ändert — die Energie geht nicht verloren, landet aber in der falschen Stunde.
4. Schritt 1 bis 3 **für jeden Erzeuger** wiederholen — ein halb erledigter Umbau kostet dich die übrigen (siehe Kasten oben).
5. Die neuen Helfer in eedc beim jeweiligen Erzeuger in der Zeile *PV-Erzeugung (kWh)* zuordnen.
6. Danach die Zuordnung *Anlage (Basis) → PV-Erzeugung Zählerstand (kWh)* entfernen, damit jede Zahl aus einer Quelle kommt.

> **Warum „links" und nicht die voreingestellte Trapezregel?** Home Assistant speichert **keine Wiederholung gleicher Werte** — ein Sensor, der stillsteht, erzeugt in dieser Zeit gar keinen Messpunkt. Die Trapezregel zieht dann eine gerade Linie über die Lücke und erfindet Energie, die es nie gab. **Bei PV trifft das jede Nacht:** Der Sensor meldet abends 0 W und morgens den ersten kleinen Wert — dazwischen liegt eine Lücke von mehreren Stunden, über die die Trapezregel den halben Morgenwert als Erzeugung verbucht. Gemessen an einer realen Anlage (7,5 Stunden Lücke, erster Morgenwert 16 W): rund 60 Wh Scheinertrag pro Nacht, und der Wert wächst **proportional zum ersten Morgenwert** — bei einem Wechselrichter, der erst ab 200 W meldet, sind es knapp 750 Wh. **Nachts irrt die Trapezregel immer nach oben**, während der Fehler der linken Summe tagsüber mal nach oben und mal nach unten geht und sich über den symmetrischen PV-Tag weitgehend aufhebt. Die Voreinstellung „Trapez" passt zu Quellen, die durchgehend neue Werte liefern — ein Wechselrichter, der nachts schweigt, ist keine.

> Auch dieser Helfer **fängt bei null an** — Tageswerte entstehen ab dem Anlegen, rückwirkend geht es nicht. Bereits erfasste Monatswerte bleiben unverändert. Solange die Helfer noch keine Historie haben, ist der Anlagen-Zählerstand für die Vergangenheit die bessere Quelle.

> ⚠ **Hast du den Helfer schon mit „Trapez" angelegt?** Stell die Methode in den Helfer-Optionen einfach um — der Zählerstand läuft weiter, du verlierst nichts. **Rückwirkend korrigiert sich der bereits aufgelaufene Wert nicht**; er trägt den Scheinertrag der bisherigen Nächte weiter mit. Bei einem frisch angelegten Helfer ist das vernachlässigbar. Wenn er schon länger läuft und du es genau haben willst, leg ihn neu an und trage den Monatswert für die Übergangszeit von Hand nach.

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
3. Wenn die Werte korrekt sind: **den Hinweis stehen lassen.** Er wird dann zur Auskunft — er sagt, mit welcher Zahl eedc rechnet, und macht sie für dich und für den Support nachvollziehbar. Einen „Erledigt"-Knopf gibt es bewusst nicht (§1).
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
