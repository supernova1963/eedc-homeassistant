
# eedc Handbuch — Daten-Checker

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Infothek](HANDBUCH_INFOTHEK.md) | [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was ist der Daten-Checker?](#1-was-ist-der-daten-checker)
2. [Severity-Logik](#2-severity-logik)
3. [Befunde und Verfügbarkeit](#3-verfuegbarkeit-nach-installationsvariante) — [alle Befunde](#alle-befunde) (erzeugt)
4. [Kategorien im Detail](#4-kategorien-im-detail)
   1. [Stammdaten](#41-stammdaten)
   2. [Strompreise](#42-strompreise)
   2a. [Strompreise – eigener WP-/Wallbox-Tarif](#42a-eigener-waermepumpen-tarif)
   3. [Investitionen](#43-investitionen)
   4. [Monatsdaten – Vollständigkeit](#44-monatsdaten--vollstaendigkeit)
   5. [Monatsdaten – Plausibilität](#45-monatsdaten--plausibilitaet)
   6. [Energieprofil – Zähler-Abdeckung](#46-energieprofil--zaehler-abdeckung)
   7. [Energieprofil – Plausibilität](#47-energieprofil--plausibilitaet)
   8. [MQTT-Topic-Abdeckung](#48-mqtt-topic-abdeckung)
   8a. [Zählerstände – Rücksprung](#48a-zaehlerstaende--ruecksprung)
   8b. [Zählerstände – Sprung in Home Assistant](#48b-zaehlerstaende--sprung-in-home-assistant)
   8c. [Zählerstände – Rückgang in Home Assistant](#48c-zaehlerstaende--rueckgang-in-home-assistant)
   8d. [PV – Messpunkt (Anlagenzähler und Strings)](#48d-pv--messpunkt)
   8e. [PV – Zähler steht](#48e-pv--zaehler-steht)
   9. [Datenquellen – HA-Statistics](#49-sensor-mapping--ha-statistics)
   9a. [Datenquellen – Status](#49a-datenquellen--status)
   10. [Energieprofil – fehlende Tageswerte](#410-energieprofil--fehlende-tageswerte)
   11. [Geräte-Connector ohne Monatswert](#411-geraete-connector-ohne-monatswert)
   12. [Zeitzone – Abweichung zu Home Assistant](#412-zeitzone--abweichung-zu-home-assistant)
   13. [Sonstige Positionen – der Erfassungsort](#413-sonstige-positionen--der-erfassungsort)
   14. [Klimaanlage – Betriebsmodus](#414-klimaanlage--betriebsmodus)
   14a. [Betriebsmodus – unbekannter Wert](#414a-betriebsmodus--unbekannter-wert)
   15. [Sensor-Zuordnung – Leistung ↔ Energie verwechselt](#415-sensor-zuordnung--leistung--energie)
   15a. [Sensor ohne Langzeitstatistik](#415a-sensor-ohne-langzeitstatistik)
   16. [Quellen-Konflikte](#416-quellen-konflikte)
   17. [Datenquellen-Drift zu Home Assistant](#417-datenquellen-drift)
   18. [PV-Doppelerfassung (Verdacht)](#418-pv-doppelerfassung)
   19. [Ladung doppelt gezählt (Wallbox + E-Auto)](#419-ladung-doppelt-gezaehlt)
   20. [Plug-in-Hybrid – elektrischer Anteil unbestimmt](#420-phev-anteil)
   21. [Batterie-Vorzeichen in der Historie](#421-batterie-vorzeichen-historie)
   22. [Ladestand bei mehreren Speichern](#422-ladestand-mehrere-speicher)
   23. [Verbrauchszähler – Zählerstände](#423-verbrauchszaehler-zaehlerstaende)
   24. [Vergleichspreise – Ø Benzinpreis](#424-vergleichspreise-benzinpreis)
   25. [Wetterwerte – fehlende Monatswerte](#425-wetterwerte-fehlende-monatswerte)
   26. [E-Mobilität – unbekannter Zustand](#426-e-mobilitaet--unbekannter-zustand)
   27. [E-Mobilität – Fahrzeug der Steuerung unbekannt](#427-e-mobilitaet--fahrzeug-unbekannt)
5. [Behebungs-Workflows](#5-behebungs-workflows)
6. [Beziehung zu anderen Werkzeugen](#6-beziehung-zu-anderen-werkzeugen)

---

## 1. Was ist der Daten-Checker?

**Pfad:** Einstellungen → Daten → Daten-Checker

Der Daten-Checker prüft systematisch, ob deine Anlage so konfiguriert ist, dass alle Auswertungen verlässlich rechnen können. Er meldet fehlende Stammdaten, Plausibilitäts-Auffälligkeiten in den Monatsdaten und Drift-Probleme zwischen der Datenquellen-Zuordnung und den tatsächlich verfügbaren Datenquellen — jeweils mit **einem** Knopf: einer Reparatur mit Vorschau, einem Sprung an die betroffene Stelle in der App oder der Auskunft „Was gilt“, und dem Lösungsweg in Schritten.

Der Daten-Checker ist eine der Kacheln in der Einstellungs-Kategorie **Daten** (neben Monatsdaten, Energieprofil-Pflege und Ersteinrichtung). Prüf-Lauf, Befund-Kategorien und die Reparatur-Werkbank laufen **inline im Block** — der große Voll-Blick über die Vollbild-Ansicht (⤢). Ein eigener Seitenwechsel ist nicht mehr nötig.

### Aufruf

Die Prüfung läuft pro Anlage, ist nicht zeitgesteuert und liest immer den aktuellen Stand. Beim Öffnen des Blocks wird automatisch geprüft; **Aktualisieren** im Kopf startet die Prüfung neu (z. B. nach einer Korrektur).

### Aufbau der Ergebnis-Fläche

- **Kopf:** die Zählung als Chips (*„2 Fehler · 6 Warnungen · 4 Hinweise · 17 bestanden“*), der Stand der Prüfung und —
  wo eine Prüfung in deiner Installation nicht laufen kann — *„n Prüfungen nicht ausführbar (Standalone / MQTT-Import
  aus)“* (etwa die Prüfungen gegen Home Assistant im Standalone-Betrieb). Rechts **Diagnose-Paket** ([unten](#diagnose-paket))
  und **Aktualisieren** (prüft neu).
- **„Das kannst du jetzt tun“:** oben alle Befunde mit einem Reparatur-Knopf aus allen Kategorien, mit Kategorie und
  Lösungsweg — dieselben Zeilen wie in ihrer Kategorie. Ohne einen solchen Befund fehlt die Leiste.
- **Monatsdaten-Abdeckung**: Fortschrittsbalken „X von Y Monaten erfasst" ab Installationsdatum bis Vormonat.
- **Kategorien:** Jede Kategorie zeigt im Kopf ihre Chips. Sie steht **offen**, wenn sie einen Fehler, eine Warnung oder
  einen Befund mit Reparatur-Knopf trägt, sonst **zu** — ein Klick auf den Kopf öffnet sie. **Bestandene Prüfungen**
  stehen nicht in der Liste; am Ende der Kategorie klappt *„n Prüfungen bestanden“* sie auf.
- **Gruppenzeilen:** Gleiche Befunde (etwa fehlende Monate, Tage mit Abweichung zu Home Assistant) stehen als **eine**
  Zeile mit einem Glied je Monat bzw. Tag — *„7 Monate fehlen: 01/2026 · 02/2026 · …“*. Ein Glied handelt genau für
  sich (öffnet den Monat bzw. zeigt die Vorschau für den Tag); der Knopf rechts handelt am ersten Glied. Hat eedc über
  eine Grenze hinaus weitere gezählt, steht *„+ n weitere“* dabei. Befunde eines Geräts (PV-Ladung größer als
  Gesamtladung, unplausibel hohe Arbeitszahl) stehen **je Gerät** in einer eigenen Zeile; die Grenze gilt je Gerät, jedes
  Gerät zeigt seine Monate und seine eigene Zahl.
- **Befund-Zeilen** mit Symbol (Severity), Meldung, optionalen Details, dem Link **„Lösungsweg“** und rechts **einem**
  Knopf, der sagt, was er tut <a name="sprung-aufs-feld"></a>:
  - **Ändert eedc etwas** (z. B. „Temperatur aus Messung übernehmen“, „Wert entfernen“, „Benzinpreise nachtragen“, „Wetterreihe nachziehen“, „Tag neu aufbauen“, „Tage neu aufbauen“, „Aus Home Assistant neu übernehmen“), zeigt der erste Klick eine **Vorschau** unter der Zeile: eine Zeile, was sich ändert (etwa „Monate erhalten eine Ø Temperatur: 7 (09/2025, …)“), darunter die Hinweise der Reparatur-Werkbank. Erst **„Anwenden“** führt aus; **„Abbrechen“** verwirft die Vorschau. Danach steht über der Liste ein Satz, was geschehen ist, und der Daten-Checker prüft neu. Lösch-Aktionen tragen in der Vorschau das Wort **„endgültig“** und einen roten Knopf; eine zusätzliche Rückfrage gibt es nicht. Ist nichts zu tun (etwa weil das Feld am Gerät vorgesehen ist), sagt die Vorschau das und bietet kein „Anwenden“. „Aus Home Assistant neu übernehmen“ nennt dazu die Bedingung: wirksam, wenn du in Home Assistant korrigiert hast. Die Vorschau gilt eine Stunde („gültig bis …“); **„Details in der Werkbank“** öffnet sie in der Reparatur-Werkbank. Es läuft immer nur ein Vorgang.
  - **Musst du etwas eintragen oder auswählen**, führt der Knopf auf das betroffene **Feld** — er heißt nach dem Ziel, etwa „Gerät bearbeiten“, „Monat erfassen“, „Monat öffnen“, „Sensor zuordnen“, „Tarif bearbeiten“, „Anlage bearbeiten“: in der **Datenquellen-Zuordnung** klappen Block und Gerät auf, die Feldzeile ist markiert (auch in „Weitere Größen erfassen“); im **Komponenten-Formular** steht der Cursor im Feld — liegt es in einem zugeklappten Abschnitt (etwa „Weitere Angaben & Kosten“ oder „Netzladung & Arbitrage“), öffnet er sich; beim Sprung sind alle zugeklappten Abschnitte dieses Formulars offen. Unter **Strompreise** öffnet sich der betroffene Tarif am Feld oder „Neuen Tarif anlegen“ mit Verwendung und Beginn vorbelegt (etwa für eine Lücke); unter **Anlage** die gewählte Anlage am Feld (z. B. Inbetriebnahme), unter **Solarprognose** „Neue Prognose abrufen“ an den Systemverlusten; im **Monatsabschluss** der Monat am Feld des Geräts. Der Geräte-Connector öffnet direkt. Kennt der Befund das Gerät nicht (etwa eine Summe über alle Autos), landet der Knopf beim ersten passenden Gerät bzw. auf der Seite. Fehlt einem Reparatur-Befund die Quelle (keine Leistungs-Zuordnung), heißt sein Knopf „Sensor zuordnen“ und führt zur fehlenden Zuordnung.
  - **Ist nichts zu tun oder liegt der Weg außerhalb von eedc**, öffnet **„Was gilt“** den Lösungsweg. Ein Weg in **Home Assistant** (Entwicklerwerkzeuge, Statistik, „Wert anpassen“; Helfer; `state_class`) steht im Text des Befunds; Wege in eedc nennt der Text nicht — der Knopf ist der Weg.
- **Lösungsweg:** Der Link öffnet **den Abschnitt dieses Befunds** ([alle Befunde](#alle-befunde)) **neben der Liste** (auf dem Handy als Fenster): *Was eedc sieht* · *Lösungsweg* in nummerierten Schritten — Schritte in eedc sind anklickbar, Schritte in Home Assistant stehen als Text, der letzte ist *Erneut prüfen* — · *Was ohne Handlung gilt*. Bei Abweichungen zu Home Assistant ist der letzte Schritt, das Diagnose-Paket zu kopieren und mit deiner Frage zu melden. Das Fenster bleibt beim Scrollen neben der Liste stehen und holt sich ins Bild, auch wenn du es aus der letzten Kategorie öffnest. Im Browser öffnet **„In eigenem Fenster öffnen“** den Abschnitt in einem eigenen Tab; innerhalb von Home Assistant (Seitenmenü oder App) fehlt dieser Knopf, weil ein eigenes Fenster dort keine Anmeldung hätte — direkt geöffnet (Port 8099) gibt es ihn.

Die Komponenten-Seiten (Block **Daten-Qualität**) zeigen die Befunde ihres Geräts mit denselben Knöpfen.

### Diagnose-Paket <a name="diagnose-paket"></a>

Wenn du im Forum oder auf GitHub nach Hilfe fragst, schick das Diagnose-Paket mit:
**Einstellungen → Daten → Daten-Checker → Diagnose-Paket → Kopieren.**

Der Knopf öffnet ein Fenster mit einem Text (Markdown) in 13 Abschnitten: Kopf (eedc-Version, Betriebsart Add-on oder
Standalone, Home Assistant erreichbar und seine Version, Zeitzone), Anlage, Komponenten mit ihren Fach-Parametern,
Zuordnungen je Feld (Quelle und Sensor), Strompreise, alle Befunde des Daten-Checkers (auch die OK-Zeilen, ohne die langen
Erklärtexte), HA-Spiegel, Nachtlauf und Reparaturen aus dem Aktivitätsprotokoll, Kanal-Tage der letzten 90 Tage, Monate,
die Tageswerte der betroffenen Monate (höchstens zwei), Zeitpläne und die letzten Warnungen aus dem Log.

- **Bearbeiten:** Das Textfeld ist bearbeitbar. Es enthält Entity-Namen, Standort und Preise — entferne, was du nicht
  teilen willst, bevor du kopierst.
- **Kopieren** übernimmt den Text aus dem Fenster in die Zwischenablage. Diese Fassung bleibt unter 20 KB; ist sie
  größer, kürzt eedc nacheinander: das Log, den zweiten Monat der Tageswerte, die Spiegel-Abschnitte, die OK-Zeilen,
  die Zuordnungen auf Felder mit Quelle, die Komponenten auf ihre Kennwerte (ohne Parameter), die Befunde auf Warnungen
  und Fehler (Hinweise als Zahl) und zuletzt die Tageswerte ganz. Reicht das nicht, fallen ganze Abschnitte weg —
  Strompreise, Monate, Komponenten, Kanal-Tage, Zuordnungen, Anlage, in dieser Reihenfolge; **Kopf, Befunde, HA-Spiegel,
  Nachtlauf und Reparaturen sowie Zeitpläne bleiben immer**. Was gekürzt ist, steht im Kopf unter „Kürzungen“.
- **Als Datei herunterladen** speichert die ungekürzte Fassung als `.md`-Datei. Innerhalb von Home Assistant (Seitenmenü
  oder App) lädt eedc die Datei direkt über ihre Adresse. Speichert die App keine Datei, kopiere den Text und füge ihn in
  eine Notiz ein — so steht es auch unter dem Knopf. Für ein Forum ist **Kopieren** der Weg (viele Foren nehmen keine
  Datei als Anhang); auf GitHub lässt sich die `.md`-Datei anhängen.

Zugangsdaten enthält das Paket nie: keine Token, keine Passwörter, keine Adresse einer Home-Assistant-Verbindung, nicht
die Zugangsdaten eines Geräte-Connectors (nur seinen Namen), keinen Solcast-Schlüssel, keine Versorger-Daten wie die
Kundennummer. eedc schickt das Paket nirgendwohin — du entscheidest, wem du es gibst. Erstellt wird es nur lesend:
eedc ändert dabei nichts und gleicht nichts mit Home Assistant ab.

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

## 3. Befunde und Verfügbarkeit <a name="3-verfuegbarkeit-nach-installationsvariante"></a>

### 3.1 Alle Befunde <a name="alle-befunde"></a>

<!-- erzeugt: scripts/daten-checker-handbuch.py §3 Anfang — nicht von Hand ändern -->
eedc prüft **38 Kategorien** mit **182 Befunden** (gezählt an `CheckKategorie` und am Katalog der Handgriffe). Jeder Befund trägt genau einen Handgriff: eine **Aktion** mit Vorschau, einen **Sprung** an die Stelle, wo du ihn behebst, oder die **Auskunft** «Was gilt»; bestandene Prüfungen stehen gefaltet im Kopf ihrer Kategorie.

| Befund | Abschnitt | Klasse | Knopf |
| --- | --- | --- | --- |
| [Geräte-Connector liefert für den laufenden Monat keinen Wert](#connector_monatswert_fehlt) `connector_monatswert_fehlt` | §4.11 | Sprung | Zum Connector |
| [Zählerstand in der Statistik von Home Assistant gefallen](#ha_zaehler_rueckgang) `ha_zaehler_rueckgang` | §4.8c | Aktion | Aus Home Assistant neu übernehmen |
| [Zählersprung in der Statistik von Home Assistant](#ha_zaehlersprung) `ha_zaehlersprung` | §4.8b | Aktion | Aus Home Assistant neu übernehmen |
| [Betriebsmodus-Sensor liefert einen Wert, den eedc nicht kennt](#klima_modus_wert_unbekannt) `klima_modus_wert_unbekannt` | §4.14a | Auskunft | Was gilt |
| [Kühlanteil wird geschätzt — Stromzähler für den Kühlbetrieb fehlt](#klima_kuehlanteil_geschaetzt) `klima_kuehlanteil_geschaetzt` | §4.14 | Sprung | Sensor zuordnen |
| [Heiz- und Kühlstrom werden aufgeteilt](#klima_modus_ok) `klima_modus_ok` | §4.14 | bestanden | — |
| [Mehrere verschiedene Modus-Quellen an einem Gerät](#klima_modus_quellen_mehrdeutig) `klima_modus_quellen_mehrdeutig` | §4.14 | Sprung | Zuordnung prüfen |
| [Betriebsmodus nicht zugeordnet — Heiz- und Kühlstrom bleiben zusammen](#klima_modus_nicht_zugeordnet) `klima_modus_nicht_zugeordnet` | §4.14 | Sprung | Sensor zuordnen |
| [Anlagenzähler und String-Zähler messen verschiedene Dinge](#messpunkt_anlagenzaehler_vs_strings) `messpunkt_anlagenzaehler_vs_strings` | §4.8d | Sprung | Zur Zuordnung |
| [Der Anlagenzähler misst das Balkonkraftwerk offenbar nicht](#messpunkt_bkw_nicht_im_anlagenzaehler) `messpunkt_bkw_nicht_im_anlagenzaehler` | §4.8d | Sprung | Zur Zuordnung |
| [Anlagenzähler zählt mehr als die Strings](#messpunkt_zaehler_mehr_als_strings) `messpunkt_zaehler_mehr_als_strings` | §4.8d | Sprung | Zur Zuordnung |
| [DC-Speicher: der AC-Zähler misst die Batterie mit](#messpunkt_dc_speicher) `messpunkt_dc_speicher` | §4.8d | Sprung | Gerät bearbeiten |
| [„PV gesamt“ gilt als Zähler einschließlich Balkonkraftwerk](#messpunkt_pv_gesamt_inkl_bkw) `messpunkt_pv_gesamt_inkl_bkw` | §4.8d | Auskunft | Was gilt |
| [Volleinspeisung ohne AC-Ertragszähler](#messpunkt_volleinspeisung_ac_zaehler_fehlt) `messpunkt_volleinspeisung_ac_zaehler_fehlt` | §4.8d | Sprung | Sensor zuordnen |
| [Keine Quellen-Konflikte](#provenance_ok) `provenance_ok` | §4.16 | bestanden | — |
| [Felder mit Werten aus mehreren Quellen](#provenance_konflikte) `provenance_konflikte` | §4.16 | Auskunft | Was gilt |
| [Tageswerte kommen aus der Langzeitstatistik von Home Assistant](#datenquelle_ha_lts_ok) `datenquelle_ha_lts_ok` | §4.9a | bestanden | — |
| [Tageswerte kommen aus dem gespiegelten Home-Assistant-Zähler](#datenquelle_kanal_ok) `datenquelle_kanal_ok` | §4.9a | bestanden | — |
| [Noch keine Tageswerte](#datenquelle_noch_keine_tageswerte) `datenquelle_noch_keine_tageswerte` | §4.9a | Auskunft | Was gilt |
| [Tageswerte stammen noch aus einer älteren Quelle](#datenquelle_aggregate_aeltere_quelle) `datenquelle_aggregate_aeltere_quelle` | §4.9a | Aktion | Tage neu aufbauen |
| [Betrieb ohne Langzeitstatistik von Home Assistant](#betriebsart_standalone) `betriebsart_standalone` | §4.9a | Auskunft | Was gilt |
| [Keine Abweichung zu Home Assistant](#drift_ok) `drift_ok` | §4.17 | bestanden | — |
| [Abweichung zu Home Assistant an einem Tag (PV)](#drift_tag) `drift_tag` | §4.17 | Aktion | Aus Home Assistant neu übernehmen |
| [Ein Gerät weicht an Tagen von Home Assistant ab](#drift_komponente) `drift_komponente` | §4.17 | Aktion | Aus Home Assistant neu übernehmen |
| [Zählerstand springt zwischendurch zurück](#zaehler_ruecksprung) `zaehler_ruecksprung` | §4.8a | Sprung | Sensor wechseln |
| [Batterie-Richtung in der Historie stimmt](#batterie_vorzeichen_ok) `batterie_vorzeichen_ok` | §4.21 | bestanden | — |
| [Tage mit vertauschtem Batterie-Vorzeichen](#batterie_vorzeichen_tage) `batterie_vorzeichen_tage` | §4.21 | Aktion | Tage neu aufbauen |
| [Ein Tag mit vertauschtem Batterie-Vorzeichen](#batterie_vorzeichen_tag) `batterie_vorzeichen_tag` | §4.21 | Aktion | Tag neu aufbauen |
| [Ladestand aller Speicher wird getrennt geführt](#soc_ok) `soc_ok` | §4.22 | bestanden | — |
| [Tage kennen nur den Ladestand eines Speichers](#soc_nur_ein_speicher_tage) `soc_nur_ein_speicher_tage` | §4.22 | Aktion | Tage neu aufbauen |
| [Keine reparierbaren Tages-Lücken](#tageswerte_ok) `tageswerte_ok` | §4.10 | bestanden | — |
| [Tage ohne Werte trotz zugeordnetem Zähler](#tageswerte_fehlen_tage) `tageswerte_fehlen_tage` | §4.10 | Aktion | Tage neu aufbauen |
| [Ein Tag ohne Tageswerte, Home Assistant hat Werte](#tageswerte_fehlen_tag) `tageswerte_fehlen_tag` | §4.10 | Aktion | Tag neu aufbauen |
| [PV-Zähler steht, obwohl erzeugt wird](#pv_zaehler_steht) `pv_zaehler_steht` | §4.8e | Auskunft | Was gilt |
| [eedc und Home Assistant rechnen mit verschiedenen Zeitzonen](#zeitzone_abweichung) `zeitzone_abweichung` | §4.12 | Sprung | Zum Neustart |
| [Autos haben mehr zu Hause geladen, als die Wallbox gemessen hat](#emob_autos_mehr_als_wallbox) `emob_autos_mehr_als_wallbox` | §4.3.9 | Sprung | Monat öffnen |
| [Heimladung am Dienstwagen fehlt](#emob_dienstwagen_heimladung_fehlt) `emob_dienstwagen_heimladung_fehlt` | §4.3.9 | Sprung | Monat öffnen |
| [PV-Ladung größer als Gesamtladung](#emob_pv_ladung_groesser_gesamt) `emob_pv_ladung_groesser_gesamt` | §4.5 | Sprung | Monat öffnen |
| [Elektrischer Anteil eines Plug-in-Hybrids unbestimmt](#phev_anteil_unbestimmt) `phev_anteil_unbestimmt` | §4.20 | Sprung | Gerät bearbeiten |
| [Gleicher Sensor an Wallbox und E-Auto](#emob_gleicher_sensor_wallbox_eauto) `emob_gleicher_sensor_wallbox_eauto` | §4.3.9 | Sprung | Zuordnung prüfen |
| [Keine doppelt gezählte Ladung](#emob_doppelzaehlung_ok) `emob_doppelzaehlung_ok` | §4.19 | bestanden | — |
| [Tage zählen dieselbe Ladung doppelt](#emob_doppelzaehlung_tage) `emob_doppelzaehlung_tage` | §4.19 | Aktion | Tage neu aufbauen |
| [Jeder Monat mit E-Auto trägt einen Benzinpreis](#vergleichspreis_ok) `vergleichspreis_ok` | §4.24 | bestanden | — |
| [Monate ohne Ø-Benzinpreis](#vergleichspreis_fehlt) `vergleichspreis_fehlt` | §4.24 | Aktion | Benzinpreise nachtragen |
| [Zustand der E-Mobilität mit unbekanntem Wert](#emob_zustand_wert_unbekannt) `emob_zustand_wert_unbekannt` | §4.26 | Auskunft | Was gilt |
| [Fahrzeug der Steuerung unbekannt](#emob_kennung_unbekannt) `emob_kennung_unbekannt` | §4.27 | Sprung | Kennung eintragen |
| [Basis-Zähler über eine andere Quelle befüllt](#basis_zaehler_manuell_ok) `basis_zaehler_manuell_ok` | §4.6 | bestanden | — |
| [Kein Basis-Zähler für Einspeisung oder Netzbezug](#basis_zaehler_fehlt) `basis_zaehler_fehlt` | §4.6 | Sprung | Sensor zuordnen |
| [Basis-Zähler zugeordnet](#basis_zaehler_ok) `basis_zaehler_ok` | §4.6 | bestanden | — |
| [Komponenten ohne vollständige kWh-Zähler](#komponenten_ohne_zaehler) `komponenten_ohne_zaehler` | §4.6 | Sprung | Sensor zuordnen |
| [Balkonkraftwerk über die PV-Module gedeckt](#bkw_ueber_module_ok) `bkw_ueber_module_ok` | §4.6 | bestanden | — |
| [Alle aktiven Komponenten haben kWh-Zähler](#komponenten_zaehler_ok) `komponenten_zaehler_ok` | §4.6 | bestanden | — |
| [Erzeuger über den Anlagen-Zählerstand gedeckt](#erzeuger_ueber_anlagenzaehler_ok) `erzeuger_ueber_anlagenzaehler_ok` | §4.6 | bestanden | — |
| [Komponenten über eine andere Quelle befüllt](#komponenten_manuell_ok) `komponenten_manuell_ok` | §4.6 | bestanden | — |
| [Komponenten ohne Zusatz-Zähler für Tageswerte](#komponenten_ohne_zusatzzaehler) `komponenten_ohne_zusatzzaehler` | §4.6 | Sprung | Sensor zuordnen |
| [Tage vor dem Umbau gerechnet](#tage_vor_umbau_ohne_regelmarke) `tage_vor_umbau_ohne_regelmarke` | §4.6 | Aktion | Tage neu aufbauen |
| [Tage mit Mengen aus den gespeicherten Stundenwerten](#tage_ohne_kanal_deckung) `tage_ohne_kanal_deckung` | §4.6 | Auskunft | Was gilt |
| [Tage mit mehr Einspeisung als Erzeugung](#einspeisung_groesser_erzeugung_tage) `einspeisung_groesser_erzeugung_tage` | §4.7 | Aktion | Tage neu aufbauen |
| [Nachtrag nach eingefrorenem Zähler](#nachtrag_nach_eingefrorenem_zaehler) `nachtrag_nach_eingefrorenem_zaehler` | §4.7 | Auskunft | Was gilt |
| [Keine unmöglichen Stundenwerte](#counter_spikes_ok) `counter_spikes_ok` | §4.7 | bestanden | — |
| [Unmöglicher Stundenwert an einem Tag](#counter_spike_tag) `counter_spike_tag` | §4.7 | Aktion | Tag neu aufbauen |
| [PV-Erzeugung fehlt in Monaten](#pv_erzeugung_fehlt_monate) `pv_erzeugung_fehlt_monate` | §4.3 | Sprung | Monat öffnen |
| [PV-Erzeugung nur teilweise erfasst](#pv_erzeugung_unvollstaendig) `pv_erzeugung_unvollstaendig` | §4.3 | Sprung | Monat öffnen |
| [PV-Erzeugung über den kWp-Anteil verteilt](#pv_erzeugung_geschaetzt) `pv_erzeugung_geschaetzt` | §4.3 | Auskunft | Was gilt |
| [PV-Erzeugung: Monatsdaten vollständig](#pv_erzeugung_ok) `pv_erzeugung_ok` | §4.3 | bestanden | — |
| [Auffällige PV-Tage mit Zählersprung — kein Doppelerfassungs-Verdacht](#pv_ueber_erfassung_spike_ueberdeckt) `pv_ueber_erfassung_spike_ueberdeckt` | §4.18 | Auskunft | Was gilt |
| [Verdacht auf PV-Doppelerfassung](#pv_ueber_erfassung_verdacht) `pv_ueber_erfassung_verdacht` | §4.18 | Sprung | Zur Zuordnung |
| [Messwerte ohne Monatszeile](#geraetewerte_ohne_monatszeile) `geraetewerte_ohne_monatszeile` | §4.4a | Sprung | Monat erfassen |
| [Keine Monatsdaten vorhanden](#keine_monatsdaten) `keine_monatsdaten` | §4.4 | Sprung | Monat erfassen |
| [Alle Monate vollständig](#monate_vollstaendig_ok) `monate_vollstaendig_ok` | §4.4 | bestanden | — |
| [Monat fehlt](#monat_fehlt) `monat_fehlt` | §4.4 | Sprung | Monat erfassen |
| [Keine Auffälligkeiten in den Monatsdaten](#monatsdaten_plausi_ok) `monatsdaten_plausi_ok` | §4.5 | bestanden | — |
| [Monatswert eines Geräts fehlt](#geraet_feld_fehlt_monate) `geraet_feld_fehlt_monate` | §4.3 | Sprung | Monat öffnen |
| [Monatsdaten eines Geräts vollständig](#geraet_monate_ok) `geraet_monate_ok` | §4.3 | bestanden | — |
| [Wert in einem Feld, das das Gerät nicht führt](#feldwert_nicht_gefuehrt) `feldwert_nicht_gefuehrt` | §4.3 | Aktion | Wert entfernen |
| [Heiz- und Kühlstrom größer als der Gesamtverbrauch](#wp_heiz_kuehl_groesser_gesamt) `wp_heiz_kuehl_groesser_gesamt` | §4.3 | Sprung | Monat öffnen |
| [Wärme gesamt kleiner als die Einzelwerte](#wp_gesamtwaerme_kleiner_teile) `wp_gesamtwaerme_kleiner_teile` | §4.3 | Sprung | Monat öffnen |
| [Wärme gesamt ist 0, die Einzelwerte nicht](#wp_waerme_gesamt_null) `wp_waerme_gesamt_null` | §4.3 | Sprung | Monat öffnen |
| [Gesamtzähler kleiner als Strom Heizen und Strom Warmwasser](#wp_gesamtzaehler_kleiner_achsen) `wp_gesamtzaehler_kleiner_achsen` | §4.3 | Sprung | Monat öffnen |
| [Gesamtzähler misst deutlich mehr als die Achsen](#wp_gesamtzaehler_mehr_als_achsen) `wp_gesamtzaehler_mehr_als_achsen` | §4.3 | Sprung | Zuordnung prüfen |
| [Strom der Wärmepumpe fehlt](#wp_strom_fehlt_monate) `wp_strom_fehlt_monate` | §4.3 | Sprung | Monat öffnen |
| [Eine Stromseite der Wärmepumpe fehlt](#wp_seite_fehlt_monate) `wp_seite_fehlt_monate` | §4.3 | Sprung | Monat öffnen |
| [Heizwärme der Wärmepumpe fehlt](#wp_heizwaerme_fehlt_monate) `wp_heizwaerme_fehlt_monate` | §4.3 | Sprung | Monat öffnen |
| [Monatsdaten der Wärmepumpe vollständig](#wp_monate_ok) `wp_monate_ok` | §4.3 | bestanden | — |
| [Aufteilung nach Betriebsart nicht gespeichert](#monatsabschluss_hinweis_geraet) `monatsabschluss_hinweis_geraet` | §4.3 | Sprung | Monat öffnen |
| [Wetterreihe uneinheitlich oder lückenhaft](#wetterreihe_nachziehen) `wetterreihe_nachziehen` | §4.25 | Aktion | Wetterreihe nachziehen |
| [Jeder Monat trägt eine Ø Temperatur](#temperatur_ok) `temperatur_ok` | §4.25 | bestanden | — |
| [Ø Temperatur fehlt — keine eigene Messreihe](#temperatur_fehlt_ohne_messreihe) `temperatur_fehlt_ohne_messreihe` | §4.25 | Sprung | Monat öffnen |
| [Ø Temperatur fehlt — eigene Messwerte reichen](#temperatur_aus_messung_moeglich) `temperatur_aus_messung_moeglich` | §4.25 | Aktion | Temperatur aus Messung übernehmen |
| [Jahresbetrag gepflegt und zusätzlich monatlich gebucht](#position_doppelerfassung) `position_doppelerfassung` | §4.13 | Sprung | Gerät bearbeiten |
| [Monatsposition sieht wiederkehrend aus](#position_wiederkehrend) `position_wiederkehrend` | §4.13 | Sprung | Gerät bearbeiten |
| [Einspeisung oder Netzbezug nicht erfasst](#md_feld_nicht_erfasst) `md_feld_nicht_erfasst` | §4.5 | Sprung | Monat öffnen |
| [Batterie-Ladung nicht erfasst](#md_batterie_ladung_fehlt) `md_batterie_ladung_fehlt` | §4.5 | Sprung | Monat öffnen |
| [Batterie-Entladung nicht erfasst](#md_batterie_entladung_fehlt) `md_batterie_entladung_fehlt` | §4.5 | Sprung | Monat öffnen |
| [Entladung an einem Speicher nicht erfasst](#md_geraet_entladung_fehlt) `md_geraet_entladung_fehlt` | §4.5 | Sprung | Monat öffnen |
| [Energiemenge im Monat negativ](#md_feld_negativ) `md_feld_negativ` | §4.5 | Sprung | Monat öffnen |
| [PV-Erzeugung ungewöhnlich hoch](#md_pv_ungewoehnlich_hoch) `md_pv_ungewoehnlich_hoch` | §4.5 | Sprung | Monat öffnen |
| [Einspeisung und Netzbezug sind beide 0](#md_einspeisung_netzbezug_null) `md_einspeisung_netzbezug_null` | §4.5 | Sprung | Monat öffnen |
| [Energiebilanz ergibt negativen Gesamtverbrauch](#md_negativer_gesamtverbrauch) `md_negativer_gesamtverbrauch` | §4.5 | Sprung | Monat öffnen |
| [Einspeisung größer als PV-Erzeugung](#md_einspeisung_groesser_pv) `md_einspeisung_groesser_pv` | §4.5 | Sprung | Monat öffnen |
| [Mehr PV verwendet als erzeugt?](#md_mehr_pv_verwendet_als_erzeugt) `md_mehr_pv_verwendet_als_erzeugt` | §4.5 | Sprung | Monat öffnen |
| [Mehr als dreimal so viel wie im Vorjahr](#md_feld_dreifach_vorjahr) `md_feld_dreifach_vorjahr` | §4.5 | Sprung | Monat öffnen |
| [Wärmepumpen-Sensor ohne Langzeitstatistik — Live ja, Tagesverlauf nein](#sensor_ohne_langzeitstatistik) `sensor_ohne_langzeitstatistik` | §4.15a | Auskunft | Was gilt |
| [MQTT-Empfang eingeschaltet, aber nicht verbunden](#mqtt_subscriber_laeuft_nicht) `mqtt_subscriber_laeuft_nicht` | §4.8 | Sprung | Zur Verbindung |
| [MQTT-Topics erwartet, nie empfangen](#mqtt_topics_nie_empfangen) `mqtt_topics_nie_empfangen` | §4.8 | Sprung | Topics prüfen |
| [MQTT-Topics mit veralteten Werten](#mqtt_topics_veraltet) `mqtt_topics_veraltet` | §4.8 | Sprung | Topics prüfen |
| [Alle erwarteten MQTT-Topics aktuell](#mqtt_ok) `mqtt_ok` | §4.8 | bestanden | — |
| [kWh-Sensoren nicht in der Langzeitstatistik von Home Assistant](#kwh_sensoren_nicht_in_lts) `kwh_sensoren_nicht_in_lts` | §4.9 | Sprung | Anderen Sensor wählen |
| [Zähler-Sensoren ohne state_class — Reparatur-Werkzeuge wirken nicht](#counter_ohne_state_class) `counter_ohne_state_class` | §4.9 | Sprung | Anderen Sensor wählen |
| [kWh-Sensoren ohne Summen-Spalte — Tages- und Stundenwerte bleiben leer](#kwh_ohne_summen_spalte) `kwh_ohne_summen_spalte` | §4.9 | Sprung | Anderen Sensor wählen |
| [Zähler-Sensoren ohne Summen-Spalte — Reparatur-Werkzeuge wirken nicht](#counter_ohne_summen_spalte) `counter_ohne_summen_spalte` | §4.9 | Sprung | Anderen Sensor wählen |
| [Zählerstand-Sensoren nicht in der Langzeitstatistik von Home Assistant](#stand_sensoren_nicht_in_lts) `stand_sensoren_nicht_in_lts` | §4.9 | Sprung | Anderen Sensor wählen |
| [Alle kWh- und Zählerstand-Sensoren in der Langzeitstatistik](#stand_sensoren_ok) `stand_sensoren_ok` | §4.9 | bestanden | — |
| [Energie-Sensor in einem Leistungs-Feld](#leistungs_slot_energie_sensor) `leistungs_slot_energie_sensor` | §4.15 | Sprung | Sensor wechseln |
| [Leistungssensor in einem Energie-Feld](#energie_slot_leistungssensor) `energie_slot_leistungssensor` | §4.15 | Sprung | Sensor wechseln |
| [Installationsdatum fehlt](#installationsdatum_fehlt) `installationsdatum_fehlt` | §4.1 | Sprung | Anlage bearbeiten |
| [Installationsdatum vorhanden](#installationsdatum_ok) `installationsdatum_ok` | §4.1 | bestanden | — |
| [Erzeuger älter als die Anlage](#erzeuger_aelter_als_anlage) `erzeuger_aelter_als_anlage` | §4.1 | Sprung | Anlage bearbeiten |
| [Gerät älter als die Anlage](#geraet_aelter_als_anlage) `geraet_aelter_als_anlage` | §4.1 | Sprung | Anlage bearbeiten |
| [Anlagenleistung fehlt](#anlagenleistung_fehlt) `anlagenleistung_fehlt` | §4.1 | Sprung | Anlage bearbeiten |
| [Anlagenleistung eingetragen](#anlagenleistung_ok) `anlagenleistung_ok` | §4.1 | bestanden | — |
| [Standort fehlt](#standort_fehlt) `standort_fehlt` | §4.1 | Sprung | Anlage bearbeiten |
| [Keine PV-Module angelegt](#keine_pv_module) `keine_pv_module` | §4.1 | Sprung | Komponente anlegen |
| [PV-Module angelegt](#pv_module_ok) `pv_module_ok` | §4.1 | bestanden | — |
| [Modul-Details passen nicht zur Leistung](#modul_details_passen_nicht) `modul_details_passen_nicht` | §4.1 | Sprung | Gerät bearbeiten |
| [PVGIS-Systemverluste vielleicht zu hoch](#pvgis_systemverluste_hoch) `pvgis_systemverluste_hoch` | §4.1 | Sprung | Prognose bearbeiten |
| [Anlagenleistung passt nicht zu den Modulen](#anlagenleistung_passt_nicht_zu_modulen) `anlagenleistung_passt_nicht_zu_modulen` | §4.1 | Sprung | Anlage bearbeiten |
| [Modulleistung weit über der Wechselrichter-Leistung](#wr_modulleistung_vielfach) `wr_modulleistung_vielfach` | §4.1 | Sprung | Gerät bearbeiten |
| [Kein Strompreis vorhanden](#kein_strompreis) `kein_strompreis` | §4.2 | Sprung | Tarif anlegen |
| [Strompreis-Tarife vorhanden](#strompreise_ok) `strompreise_ok` | §4.2 | bestanden | — |
| [Einspeisung wird mit 0 ct/kWh gerechnet](#einspeisung_null_cent) `einspeisung_null_cent` | §4.2 | Sprung | Tarif bearbeiten |
| [Monate vor dem ersten Tarif](#monate_vor_erstem_tarif) `monate_vor_erstem_tarif` | §4.2 | Sprung | Tarif bearbeiten |
| [Lücke zwischen Tarifen](#strompreis_luecke) `strompreis_luecke` | §4.2 | Sprung | Tarif anlegen |
| [Zeittarif ohne Stundenwerte](#zeittarif_ohne_stundenwerte) `zeittarif_ohne_stundenwerte` | §4.2 | Sprung | Sensor zuordnen |
| [Zwei Tarife beginnen am selben Tag](#tarife_gleicher_tag) `tarife_gleicher_tag` | §4.2 | Sprung | Tarif bearbeiten |
| [Wärmepumpe rechnet mit dem allgemeinen Tarif](#wp_allgemeiner_tarif) `wp_allgemeiner_tarif` | §4.2 | Auskunft | Was gilt |
| [Kein eigener Ladetarif](#kein_ladetarif) `kein_ladetarif` | §4.2 | Auskunft | Was gilt |
| [Arbeitspreis ungewöhnlich](#arbeitspreis_ungewoehnlich) `arbeitspreis_ungewoehnlich` | §4.2 | Sprung | Tarif bearbeiten |
| [Einspeisevergütung ungewöhnlich](#einspeiseverguetung_ungewoehnlich) `einspeiseverguetung_ungewoehnlich` | §4.2 | Sprung | Tarif bearbeiten |
| [Speicher-Kapazität vermutlich in Wh statt kWh](#kapazitaet_wh_statt_kwh) `kapazitaet_wh_statt_kwh` | §4.3 | Sprung | Gerät bearbeiten |
| [«Strom Heizbetrieb» und «Strom Heizen» beide belegt](#wp_strom_heizbetrieb_und_heizen_belegt) `wp_strom_heizbetrieb_und_heizen_belegt` | §4.3 | Sprung | Zuordnung prüfen |
| [Strom Heizen/Warmwasser zugeordnet, getrennte Messung aus](#wp_strom_zugeordnet_getrennte_messung_aus) `wp_strom_zugeordnet_getrennte_messung_aus` | §4.3 | Sprung | Gerät bearbeiten |
| [PV-Zuordnung am Wechselrichter wird nicht ausgewertet](#wr_pv_zuordnung_nicht_ausgewertet) `wr_pv_zuordnung_nicht_ausgewertet` | §4.3 | Sprung | Zuordnung prüfen |
| [Gibt dieses Gerät Strom an Dritte ab?](#geraet_abgabe_an_dritte_frage) `geraet_abgabe_an_dritte_frage` | §4.3 | Sprung | Gerät bearbeiten |
| [Akku des Balkonkraftwerks nur als Monatswert erfasst](#akku_werte_nur_monatswert) `akku_werte_nur_monatswert` | §4.3 | Sprung | Sensor zuordnen |
| [Keine aktiven Komponenten](#keine_aktiven_investitionen) `keine_aktiven_investitionen` | §4.3 | Sprung | Komponente anlegen |
| [Leistung der PV-Module fehlt](#pv_leistung_kwp_fehlt) `pv_leistung_kwp_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Ausrichtung oder Neigung der PV-Module fehlt](#pv_ausrichtung_fehlt) `pv_ausrichtung_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Leistung des Balkonkraftwerks fehlt](#bkw_leistung_wp_fehlt) `bkw_leistung_wp_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Wechselrichter-Leistung des Balkonkraftwerks fehlt](#wr_leistung_fehlt) `wr_leistung_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Kapazität des Speichers fehlt](#speicher_kapazitaet_fehlt) `speicher_kapazitaet_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Arbitrage aktiv, Ø Ladepreis fehlt](#arbitrage_ladepreis_fehlt) `arbitrage_ladepreis_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Arbitrage aktiv, Ø Entladepreis fehlt](#arbitrage_entladepreis_fehlt) `arbitrage_entladepreis_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Netzladung übersteigt die Gesamtladung](#speicher_netzladung_groesser_gesamt) `speicher_netzladung_groesser_gesamt` | §4.3 | Sprung | Jahresbilanz prüfen |
| [Entladung übersteigt die Ladung](#speicher_entladung_groesser_ladung) `speicher_entladung_groesser_ladung` | §4.3 | Sprung | Jahresbilanz prüfen |
| [Fahrleistung oder Verbrauch des E-Autos fehlt](#eauto_fahrleistung_fehlt) `eauto_fahrleistung_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Alternativkosten des E-Autos fehlen](#eauto_alternativkosten_fehlen) `eauto_alternativkosten_fehlen` | §4.3 | Sprung | Gerät bearbeiten |
| [Ladeleistung der Wallbox fehlt](#wallbox_ladeleistung_fehlt) `wallbox_ladeleistung_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Leistung des Wechselrichters fehlt](#geraet_leistung_kw_fehlt) `geraet_leistung_kw_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Alternativkosten der Wärmepumpe fehlen](#wp_alternativkosten_fehlen) `wp_alternativkosten_fehlen` | §4.3 | Sprung | Gerät bearbeiten |
| [Jahresarbeitszahl der Wärmepumpe fehlt](#wp_jaz_fehlt) `wp_jaz_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Jahresarbeitszahl der Wärmepumpe unplausibel](#wp_jaz_unplausibel) `wp_jaz_unplausibel` | §4.3 | Sprung | Gerät bearbeiten |
| [SCOP- oder COP-Werte der Wärmepumpe fehlen](#wp_stammdatum_hinweis) `wp_stammdatum_hinweis` | §4.3 | Sprung | Gerät bearbeiten |
| [Alter Energiepreis der Wärmepumpe fehlt](#wp_alter_energiepreis_fehlt) `wp_alter_energiepreis_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Heizwärmebedarf der Wärmepumpe fehlt](#wp_heizwaermebedarf_fehlt) `wp_heizwaermebedarf_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Warmwasserbedarf der Wärmepumpe fehlt](#wp_warmwasserbedarf_fehlt) `wp_warmwasserbedarf_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Anschaffungsdatum fehlt](#anschaffungsdatum_fehlt) `anschaffungsdatum_fehlt` | §4.3 | Sprung | Gerät bearbeiten |
| [Anschaffungskosten fehlen](#anschaffungskosten_fehlen) `anschaffungskosten_fehlen` | §4.3 | Sprung | Gerät bearbeiten |
| [Arbeitszahl höher, als eine Wärmepumpe leisten kann](#wp_arbeitszahl_zu_hoch) `wp_arbeitszahl_zu_hoch` | §4.5 | Sprung | Monat öffnen |
| [Netzbezug zum Wallbox-Tarif zählt unter dem gemeinsamen Tarif nicht](#wp_tarif_wallbox_netzbezug_zaehlt_nicht) `wp_tarif_wallbox_netzbezug_zaehlt_nicht` | §4.2a | Sprung | Tarif bearbeiten |
| [Paralleler Zähler am Gerät](#paralleler_zaehler) `paralleler_zaehler` | §4.2a | Sprung | Zuordnung prüfen |
| [Netzladung aus evcc weicht vom Netzbezug zum Wallbox-Tarif ab](#evcc_netzladung_abweichung) `evcc_netzladung_abweichung` | §4.2a | Sprung | Zuordnung prüfen |
| [Eigener Tarif hat Vorrang vor dem gemeinsamen Tarif](#eigener_tarif_vorrang) `eigener_tarif_vorrang` | §4.2a | Sprung | Tarif bearbeiten |
| [Gemeinsamer Zähler: Tage teilen die Ersparnis nicht](#gemeinsamer_zaehler_tage_ohne_teilung) `gemeinsamer_zaehler_tage_ohne_teilung` | §4.2a | Auskunft | Was gilt |
| [Netzladung der Wallbox größer als der gemeinsame Netzbezug](#wallbox_netzladung_groesser_gemeinsamer_netzbezug) `wallbox_netzladung_groesser_gemeinsamer_netzbezug` | §4.2a | Sprung | Zuordnung prüfen |
| [Eigener Tarif ohne gemessenen Netzbezug zum Tarif](#wp_eigener_tarif_obergrenze) `wp_eigener_tarif_obergrenze` | §4.2a | Auskunft | Was gilt |
| [Netzbezug zum Tarif größer als der Verbrauch des Geräts](#tarif_mengenfeld_groesser_als_menge) `tarif_mengenfeld_groesser_als_menge` | §4.2a | Sprung | Zuordnung prüfen |
| [Netzbezug zum Tarif größer als der Netzbezug der Anlage](#tarif_mengenfeld_groesser_als_rest) `tarif_mengenfeld_groesser_als_rest` | §4.2a | Sprung | Zuordnung prüfen |
| [Verbrauchszähler liefert Zählerstände](#zaehlerstand_ablesungen_ok) `zaehlerstand_ablesungen_ok` | §4.23 | bestanden | — |
| [Verbrauchszähler ohne Zählerstand](#zaehlerstand_kein_stand) `zaehlerstand_kein_stand` | §4.23 | Sprung | Zählerstand erfassen |
| [Zählerstand eines Verbrauchszählers ist gefallen](#zaehlerstand_reihe_bruch) `zaehlerstand_reihe_bruch` | §4.23 | Auskunft | Was gilt |
| [Verbrauchszähler auf „nicht aktiv“ gesetzt](#zaehler_nicht_aktiv) `zaehler_nicht_aktiv` | §4.23 | Sprung | Gerät bearbeiten |
<!-- erzeugt: scripts/daten-checker-handbuch.py §3 Ende — nicht von Hand ändern -->

### 3.2 Verfügbarkeit nach Installationsvariante

Die meisten Kategorien greifen in jeder Installation identisch; **vierzehn** hängen an Voraussetzungen, die je nach Installation gegeben sind oder nicht — sie sind unten fett markiert. Die Kategorie *Datenquelle – aktiver Pfad* trägt zwei Befund-Familien (Zeile 12 und die Statusmeldungen der Datenquellen, Zeile 12a) und zählt deshalb einmal.

| # | Kategorie | HA Add-on | Standalone (Docker / native) |
|---|-----------|-----------|------------------------------|
| 1 | Stammdaten (§4.1) | greift | greift |
| 2 | Strompreise (§4.2) | greift | greift |
| 2a | Strompreise – eigener WP-/Wallbox-Tarif (§4.2a) | greift | greift |
| 3 | Investitionen (§4.3) | greift | greift |
| 4 | Monatsdaten – Vollständigkeit (§4.4) | greift | greift |
| 5 | Messwerte ohne Monatszeile (§4.4a) | greift | greift |
| 6 | Monatsdaten – Plausibilität (§4.5) | greift | greift |
| 7 | Energieprofil – Zähler-Abdeckung (§4.6) | greift (Zuordnung zu HA-Entitäten `sensor.…`) | greift (Zuordnung zu MQTT-Topics) |
| 8 | Energieprofil – Plausibilität (§4.7) | greift | greift |
| 9 | **MQTT-Topic-Abdeckung** (§4.8) | nur wenn MQTT-Import aktiv | nur wenn MQTT-Import aktiv |
| 9a | **Zählerstände – Rücksprung** (§4.8a) | nur wenn MQTT-Import aktiv | nur wenn MQTT-Import aktiv |
| 9b | **Zählerstände – Sprung in Home Assistant** (§4.8b) | greift | **wird übersprungen** (keine HA-Statistik) |
| 9c | **Zählerstände – Rückgang in Home Assistant** (§4.8c) | greift | **wird übersprungen** (keine HA-Statistik) |
| 9d | **PV – Messpunkt** (§4.8d) | greift, sobald die PV-Zähler Kanäle haben (Spiegel der HA-Statistik); der Hinweis zu „PV gesamt“ neben einem Balkonkraftwerk greift aus der Zuordnung | greift mit MQTT-Zählern (eigene Summe); ohne Zähler-Kanäle **wird übersprungen** (außer dem Zuordnungs-Hinweis) |
| 9e | **PV – Zähler steht** (§4.8e) | greift, sobald die PV-Zähler Kanäle haben (Spiegel der HA-Statistik) | greift mit MQTT-Zählern (eigene Summe); ohne Zähler-Kanäle **wird übersprungen** |
| 10 | **Datenquellen – HA-Statistics** (§4.9) | greift | **wird übersprungen** (keine HA-LTS verfügbar) |
| 11 | Energieprofil – fehlende Tageswerte (§4.10) | greift | greift |
| 12 | Geräte-Connector ohne Monatswert (§4.11) | greift | greift |
| 12a | Datenquelle – aktiver Pfad: Status (§4.9a) | greift — OK, wenn die Tageswerte aus der HA-Statistik oder dem HA-Spiegel (Kanal) kommen, sonst ein Hinweis mit der Quelle | greift als Hinweis „Standalone-Modus aktiv“ (keine HA-Verbindung) |
| 13 | **Zeitzone – Abweichung zu HA** (§4.12) | greift | **wird übersprungen** (keine HA-Verbindung) |
| 14 | Sonstige Positionen – wiederkehrend (§4.13) | greift | greift |
| 15 | Sonstige Positionen – Doppelerfassung (§4.13) | greift | greift |
| 16 | Klimaanlage – Betriebsmodus (§4.14) | greift | greift |
| 16a | **Betriebsmodus – unbekannter Wert** (§4.14a) | greift | **wird übersprungen** (der Wert kommt aus HA) |
| 17 | **Sensor-Zuordnung – Leistung ↔ Energie** (§4.15) | greift | **wird übersprungen** (Einheit kommt aus HA) |
| 17a | **Sensor ohne Langzeitstatistik** (§4.15a) | greift | **wird übersprungen** (`state_class` kommt aus HA; über MQTT schreibt eedc die Stundenmittel selbst mit) |
| 18 | Quellen-Konflikte (§4.16) | greift | greift |
| 19 | **Datenquellen-Drift zu HA** (§4.17) | greift | **wird übersprungen** (keine Vergleichsseite) |
| 20 | PV-Doppelerfassung (§4.18) | greift | greift |
| 21 | E-Mobilität – Pflegekonflikt (§4.3.9) | greift | greift |
| 22 | Ladung doppelt gezählt (§4.19) | greift | greift |
| 23 | Plug-in-Hybrid – Anteil unbestimmt (§4.20) | greift | greift |
| 24 | Batterie-Vorzeichen in der Historie (§4.21) | greift | greift |
| 25 | Ladestand bei mehreren Speichern (§4.22) | greift | greift |
| 26 | Verbrauchszähler – Zählerstände (§4.23) | greift | greift |
| 27 | Vergleichspreise – Ø Benzinpreis (§4.24) | greift | greift |
| 28 | Wetterwerte – fehlende Monatswerte (§4.25) | greift | greift |
| 29 | **E-Mobilität – unbekannter Zustand** ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)) | nur wenn ein Zustand der E-Mobilität (Ladezustand, Lademodus, Fahrzeug-Ladezustand, Standort) zugeordnet ist — gelesen wird der aktuelle HA-Zustand | nur wenn ein Zustand zugeordnet ist — gelesen wird der letzte MQTT-Wert |
| 30 | **E-Mobilität – Fahrzeug der Steuerung unbekannt** ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)) | nur wenn „Fahrzeug am Ladepunkt“ an einer Wallbox zugeordnet ist | nur wenn „Fahrzeug am Ladepunkt“ zugeordnet ist (MQTT) |

### Was bedeutet „wird übersprungen"?

- **Stiller Skip:** Die Kategorie erscheint gar nicht in der Ergebnisliste — keine Sektion, keine Meldung. So bleibt die Übersicht für Nicht-Betroffene aufgeräumt.
  - *MQTT-Topic-Abdeckung* (§4.8) bei nicht aktiviertem MQTT-Import.
  - *Datenquellen – HA-Statistics* (§4.9) wenn keine Datenquellen-Zuordnung mit HA-Sensoren vorhanden ist.
- **INFO-Skip:** Die Kategorie erscheint mit einem einzelnen INFO-Eintrag, der den Grund des Überspringens erklärt.
  - *Datenquellen – HA-Statistics* (§4.9) bei Standalone, weil HA-Long-Term-Statistics nicht erreichbar sind.
  - *MQTT-Topic-Abdeckung* (§4.8) wenn der MQTT-Import aktiviert ist, der Subscriber aber nicht läuft.

### Beziehung zu Datenquellen-Zuordnung und HA/MQTT

Im **HA Add-on** liefern Sensoren ihre Werte über zwei Kanäle: den aktuellen Zustand (`state`, für Live-Anzeigen) und Long-Term-Statistics (LTS, für Monatswerte und Reparatur-Werkzeuge). Kategorie 9 prüft, ob beide Kanäle für die zugeordneten HA-Sensoren verfügbar sind.

Im **Standalone-Betrieb** kommen die Werte über MQTT (`eedc/<anlage>/…`-Topics) oder Connector-Pulls. HA-LTS gibt es nicht; dafür greift Kategorie 8, die die MQTT-Topic-Abdeckung gegen die `field_definitions.py`-Erwartung prüft. Beide Kategorien lösen dasselbe Grundproblem („Zuordnung passt nicht zur Realität") in der jeweiligen Welt.

> **Wo die Zuordnung entsteht:** Welche Quelle (HA-Sensor / MQTT / Connector) welches Feld speist, legst du zentral unter [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) fest — die feld-zentrische Zuordnungs-Fläche hat die früheren getrennten Assistenten „Sensor-Mapping" und „MQTT-Inbound" abgelöst. Die Verbindungen (HA-Token, MQTT-Broker) richtest du unter [Einstellungen → Integration](HANDBUCH_EINSTELLUNGEN.md#6-integration) ein.
>
> **Vom Befund zur Zuordnung:** Der Sprung-Knopf an einem Befund der Kategorien 7, 9, 10 oder 16 (etwa „Sensor zuordnen“) öffnet die Datenquellen-Zuordnung beim betroffenen Gerät mit markiertem Feld ([Sprung aufs Feld](#sprung-aufs-feld)); in Home Assistant liegt der Weg (Helfer, `state_class`, „Wert anpassen“) im Text des Befunds.

---

<!-- erzeugt: scripts/daten-checker-handbuch.py §4 Anfang — nicht von Hand ändern -->
## 4. Kategorien im Detail

### 4.1 Stammdaten

**Was wird geprüft:** Pflicht-Stammdaten der Anlage (Inbetriebnahme, Leistung), die kWp-Konsistenz zwischen Anlage,
PV-Modulen und Wechselrichtern, optionale Felder für PVGIS und Community-Vergleich (Koordinaten, Ort/PLZ) sowie die
Performance Ratio gegenüber der PVGIS-Prognose, sobald genug Historie vorliegt.

Bei Datumsbefunden unterscheidet eedc **Erzeuger** (PV-Module, Balkonkraftwerk) von allen anderen Geräten: Ein Erzeuger,
der älter ist als die Anlage, deutet auf ein falsches Datum; ein E-Auto oder eine Heizung aus der Zeit davor ist normal
und wird nur als Auskunft genannt.

> **Hinweis:** Ausrichtung und Neigung stehen nicht an der Anlage, sondern je Dachfläche an der PV-Modul-Komponente
> (siehe [HANDBUCH_EINSTELLUNGEN.md §3](HANDBUCH_EINSTELLUNGEN.md#3-komponenten)); der Daten-Checker prüft sie dort.

---

#### Installationsdatum fehlt <a name="installationsdatum_fehlt"></a>

**Was eedc sieht**
An der Anlage ist kein Datum der Inbetriebnahme eingetragen. Ohne dieses Datum weiß eedc nicht, ab wann es Zählerwerte
für Einspeisung und Netzbezug erwarten darf. Es weicht auf das älteste Anschaffungsdatum deiner Erzeuger (PV-Module,
Balkonkraftwerk) aus, ersatzweise auf den ersten vorhandenen Monat — dann fällt eine fehlende Zeile am Anfang deiner
Historie niemandem auf.

**Lösungsweg**
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich am Feld «Inbetriebnahme (Anlage)».
2. Das Datum eintragen, an dem deine Anlage in Betrieb ging, und **«Speichern»**. Gemeint ist die Gesamt-Anlage, nicht
   das älteste Gerät — ein E-Auto oder eine Heizung aus der Zeit davor zieht das Datum nicht zurück.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile steht unter den bestandenen Prüfungen. Fehlen ab dem
   Datum Monate, meldet sie der Daten-Checker jetzt einzeln.

**Was ohne Handlung gilt**
eedc erwartet Monate ab dem ältesten Erzeuger bzw. ab dem ersten erfassten Monat. Fehlt der Anfang deiner Historie,
zeigt das keine Prüfung an.

#### Installationsdatum vorhanden <a name="installationsdatum_ok"></a>

**Was eedc sieht**
An der Anlage ist das Datum der Inbetriebnahme eingetragen. Ab diesem Monat erwartet eedc Zählerwerte für Einspeisung
und Netzbezug.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt unter den bestandenen Prüfungen.

**Was ohne Handlung gilt**
Der erwartete Monatsbereich beginnt mit diesem Datum.

#### Erzeuger älter als die Anlage <a name="erzeuger_aelter_als_anlage"></a>

**Was eedc sieht**
Ein PV-Modul oder Balkonkraftwerk wurde laut Anschaffungsdatum vor der Inbetriebnahme der Anlage angeschafft. Dann wurde
bereits Strom erzeugt, bevor die Anlage laut Stammdaten existierte — für die Monate dazwischen fragt eedc keine
Zählerwerte ab. Eines der beiden Daten stimmt nicht; der Befund nennt den ältesten Erzeuger und, wenn es mehrere sind,
ihre Zahl.

**Lösungsweg**
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich am Feld «Inbetriebnahme (Anlage)».
2. Stimmt das Datum der Anlage nicht (der häufige Fall), es korrigieren und **«Speichern»**.
3. Stimmt stattdessen das «Anschaffungsdatum» des Erzeugers nicht, es unter
   [Komponenten](eedc:/einstellungen/komponenten) beim Gerät korrigieren. Andere Geräte (E-Auto, Wallbox, Wärmepumpe,
   Speicher) nie umdatieren, nur damit eine Zeile verschwindet — ihre echte Historie ginge verloren.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Fehlen danach Monate ab dem neuen
   Datum, meldet sie der Daten-Checker einzeln.

**Was ohne Handlung gilt**
Der erwartete Monatsbereich beginnt mit dem Datum der Anlage; für die Monate davor, in denen schon erzeugt wurde, gibt es
keine Bilanz und keine Meldung.

#### Gerät älter als die Anlage <a name="geraet_aelter_als_anlage"></a>

**Was eedc sieht**
Ein Gerät, das kein PV-Erzeuger ist (E-Auto, Wallbox, Wärmepumpe, Speicher, Wechselrichter, Sonstiges), wurde vor der
Inbetriebnahme der Anlage angeschafft. Das ist normal und kein Fehler — man hatte das Auto vor der PV-Anlage. Die Zeile
meldet die Datenlage: Für die Monate davor gibt es keine Einspeisungs- und Netzbezugswerte und damit keine Bilanz; eedc
kann dort nicht sagen, ob der Strom gekauft oder selbst erzeugt war.

**Lösungsweg**
1. Hast du Zählerwerte aus dieser Zeit: unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) die Monate nachtragen.
2. Stimmt das Datum der Anlage nicht: am Befund **«Anlage bearbeiten»** klicken, im Feld «Inbetriebnahme (Anlage)»
   korrigieren und **«Speichern»**.
3. Sonst nichts — die Zeile ist eine Auskunft. Das Gerät nie umdatieren: seine Anschaffungshistorie ginge verloren.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt als Hinweis stehen, solange das Gerät älter
   ist als die Anlage; das ist der richtige Zustand.

**Was ohne Handlung gilt**
Das Gerät rechnet ab seinem eigenen Anschaffungsdatum mit. Für die Monate vor der Anlage fehlt die Bilanz; Monate davor
fordert eedc nicht ein.

#### Anlagenleistung fehlt <a name="anlagenleistung_fehlt"></a>

**Was eedc sieht**
An der Anlage ist keine Leistung in kWp eingetragen (oder 0). Sind PV-Module oder ein Balkonkraftwerk angelegt, rechnen
spezifischer Ertrag, Performance Ratio und Plausibilität mit deren Summe; die Anlagenleistung ist dann der Wert für den
Community-Vergleich, die Berichte und die Beschriftung «PV Gesamt» — und der Rückfall, solange keine Erzeuger angelegt
sind.

**Lösungsweg**
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich am Feld «Leistung (kWp)».
2. Die installierte Modulleistung (DC) eintragen, also die Summe deiner PV-Module — nicht die Summe der
   Wechselrichter-Leistungen. Ein Balkonkraftwerk gehört nicht dazu, es ist eine eigene Anlage. **«Speichern»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile steht mit der Leistung unter den bestandenen
   Prüfungen.

**Was ohne Handlung gilt**
Ohne angelegte Erzeuger bleiben die Kennzahlen, die durch die Anlagenleistung teilen, leer; mit Erzeugern rechnen sie mit
deren Summe. Der Community-Vergleich kennt deine Anlagengröße nicht.

#### Anlagenleistung eingetragen <a name="anlagenleistung_ok"></a>

**Was eedc sieht**
An der Anlage ist eine Leistung in kWp eingetragen; die Zeile nennt sie.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt unter den bestandenen Prüfungen.

**Was ohne Handlung gilt**
eedc rechnet die Kennzahlen mit der Summe deiner Erzeuger-Komponenten; diese Leistung gilt nur ohne Erzeuger als Rückfall
und ist der Wert für den Community-Vergleich und die Berichte.

#### Standort fehlt <a name="standort_fehlt"></a>

**Was eedc sieht**
An der Anlage fehlen die Koordinaten, Ort und PLZ oder beides; die Zeile sagt, was fehlt. Die Koordinaten braucht die
PVGIS-Solarprognose, Ort oder PLZ braucht der Community-Vergleich nach Region.

**Lösungsweg**
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich im Abschnitt «Standort».
2. «PLZ» und «Ort» eintragen. Sind die Koordinaten leer, ermittelt eedc «Breitengrad (Latitude)» und «Längengrad
   (Longitude)» beim Verlassen der Adresse selbst; sonst trägst du sie von Hand ein. **«Speichern»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Ohne Koordinaten gibt es keine PVGIS-Prognose; ohne Ort oder PLZ teilst du keine regionalen Vergleichswerte. Alle
übrigen Auswertungen rechnen unverändert.

#### Keine PV-Module angelegt <a name="keine_pv_module"></a>

**Was eedc sieht**
Die Anlage hat weder PV-Module noch ein Balkonkraftwerk als Komponente. Ohne Erzeuger fehlt die Erzeugung in der
Aufschlüsselung, es gibt keinen String-Vergleich und keine Prognose je Dachfläche. Ein Balkonkraftwerk allein genügt —
dann erscheint diese Zeile nicht.

**Lösungsweg**
1. Am Befund **«Komponente anlegen»** klicken — das Formular für eine neue Komponente vom Typ PV-Module öffnet sich.
2. Je Dachfläche (String) eine Komponente mit «Leistung (kWp)», Ausrichtung und Neigung anlegen und **«Erstellen»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile steht mit der Summe der Module unter den bestandenen
   Prüfungen.

**Was ohne Handlung gilt**
eedc wertet die Gesamterzeugung aus, ohne sie auf Dachflächen aufzuteilen; Prognose und String-Vergleich bleiben leer.

#### PV-Module angelegt <a name="pv_module_ok"></a>

**Was eedc sieht**
Es sind PV-Module als Komponenten angelegt; die Zeile nennt ihre Summe in kWp und die Zahl der Modul-Gruppen. Das Feld
«Leistung (kWp)» der Anlage meint diese Modulleistung (DC); ein Balkonkraftwerk zählt nicht mit.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt unter den bestandenen Prüfungen.

**Was ohne Handlung gilt**
eedc rechnet spezifischen Ertrag und Prognose mit der Summe aller aktiven Erzeuger — ein Balkonkraftwerk zählt dort mit,
auch wenn die Zeile nur die Modulsumme nennt.

#### Modul-Details passen nicht zur Leistung <a name="modul_details_passen_nicht"></a>

**Was eedc sieht**
An einem PV-Modul weicht «Anzahl Module» × «Leistung pro Modul (Wp)» um mehr als 0,1 kWp vom Feld «Leistung (kWp)» ab;
die Zeile nennt beide Werte. Geprüft wird nur, wenn «Anzahl Module» und «Leistung pro Modul (Wp)» beide eingetragen
sind. Einer der drei Einträge stimmt nicht.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular dieses PV-Moduls öffnet sich bei «Anzahl Module».
2. Anzahl, «Leistung pro Modul (Wp)» und «Leistung (kWp)» prüfen, den falschen Wert korrigieren und **«Speichern»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet mit dem Feld «Leistung (kWp)»; die Modul-Details sind nur Angabe und ändern keine Zahl.

#### PVGIS-Systemverluste vielleicht zu hoch <a name="pvgis_systemverluste_hoch"></a>

**Was eedc sieht**
Deine Anlage erzeugt über mindestens sechs Monate im Schnitt mehr als 10 % über der PVGIS-Prognose (Performance Ratio
über 1,1). Die Systemverluste der Prognose (Standard 14 %) sind eine Annahme, keine Messung — sie sind für deine Anlage
vermutlich zu hoch angesetzt.

**Lösungsweg**
1. Am Befund **«Prognose bearbeiten»** klicken — die Solarprognose öffnet sich bei «Neue Prognose abrufen» am Feld
   «Systemverluste (%)».
2. Einen kleineren Wert eintragen (z. B. 10 statt 14), **«Von PVGIS abrufen»**, die Vorschau ansehen und
   **«Speichern & Aktivieren»**. Ohne neuen Abruf ändert sich nichts.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Ist-Werte nicht mehr
   deutlich über der neuen Prognose liegen.

**Was ohne Handlung gilt**
Die Prognose bleibt eine vorsichtige Untergrenze; das ist zulässig. Eine neue Prognose hebt das Soll, deshalb sinken
Performance Ratio und Soll-Erfüllung — die Ist-Werte ändern sich nicht. Die bisherige Prognose bleibt in der Historie
und lässt sich wieder aktivieren.

#### Anlagenleistung passt nicht zu den Modulen <a name="anlagenleistung_passt_nicht_zu_modulen"></a>

**Was eedc sieht**
Die «Leistung (kWp)» der Anlage weicht um mehr als 0,1 kWp von der Summe deiner aktiven PV-Module ab — sowohl ohne als
auch mit Balkonkraftwerk gerechnet. eedc rechnet spezifischen Ertrag, Performance Ratio und die Plausibilitätsprüfungen
mit der Modulsumme; die Anlagenleistung geht an den Community-Vergleich. Solange beide auseinanderliegen, vergleichst du
dich dort mit einer anderen Anlagengröße als der, die du auswertest.

**Lösungsweg**
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich am Feld «Leistung (kWp)».
2. Stimmt die Anlagenleistung nicht: korrigieren und **«Speichern»**.
3. Stimmt die Leistung eines Moduls nicht: unter [Komponenten](eedc:/einstellungen/komponenten) beim PV-Modul die
   «Leistung (kWp)» korrigieren.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc überschreibt keine der beiden Angaben: Die Auswertungen rechnen mit der Modulsumme, der Community-Vergleich mit der
Anlagenleistung.

#### Modulleistung weit über der Wechselrichter-Leistung <a name="wr_modulleistung_vielfach"></a>

**Was eedc sieht**
An diesem Wechselrichter hängen mehr als doppelt so viele kWp Module, wie er Leistung hat. Überbelegung ist normal
(üblich 1,1 bis 1,3, bei Ost/West bis etwa 1,5) und wird nicht gemeldet — über 2 ist ein Eingabefehler
wahrscheinlicher als eine Auslegung, etwa die Wechselrichter-Leistung im kWp-Feld eines Strings.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Wechselrichters öffnet sich am Feld «Max. Leistung (kW)».
2. Dort gehört die Geräteleistung hin. Dann unter [Komponenten](eedc:/einstellungen/komponenten) die PV-Module an
   diesem Wechselrichter prüfen: in «Leistung (kWp)» gehört die Modulleistung (Anzahl × Wp).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Ist die Auslegung wirklich so,
   bleibt sie stehen.

**Was ohne Handlung gilt**
Die Zeile ändert keine Berechnung; eedc rechnet mit den eingetragenen Werten.

### 4.2 Strompreise

**Was wird geprüft:** ob mindestens ein allgemeiner Tarif besteht, ob ab der Inbetriebnahme jeder Zeitraum von einem
Tarif gedeckt ist, ob für vorhandene Wärmepumpe bzw. Wallbox ein eigener Tarif besteht, ob Zeitfenster gemessene
Stundenwerte haben und ob die Preise plausibel sind.

> **Die beiden Hinweise zu Spezialtarifen (Wärmepumpe, Laden) sind Auskunft und bleiben bei Einheitstarif dauerhaft
> stehen.** Ob jemand einen Spezialtarif *hat*, lässt sich in den Daten nicht von „noch nicht eingetragen“
> unterscheiden — deshalb sagen beide, **womit eedc ohne ihn rechnet** (allgemeiner Tarif). Sie sind keine Aufgabe.

---

#### Kein Strompreis vorhanden <a name="kein_strompreis"></a>

**Was eedc sieht**
Es gibt keinen Tarif mit der Verwendung «Standard (allgemein)». Ohne ihn fehlt dein Preis für Netzbezug und
Einspeisung — Finanz-Auswertungen, Amortisation und der Monatsabschluss rechnen nicht mit deinen Zahlen.

**Lösungsweg**
1. Am Befund **«Tarif anlegen»** klicken — das Formular «Neuen Tarif anlegen» öffnet sich.
2. «Netzbezug (ct/kWh)», «Einspeisevergütung (ct/kWh)» und «Gültig ab» (spätestens die Inbetriebnahme der Anlage)
   eintragen, Verwendung «Standard (allgemein)» lassen und **«Anlegen»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile steht mit der Zahl der Tarife unter den bestandenen
   Prüfungen.

**Was ohne Handlung gilt**
eedc rechnet Kosten und Erlöse mit einer Vorbelegung statt mit deinem Tarif; Ersparnis und Amortisation sind damit nur
grobe Schätzungen.

#### Strompreis-Tarife vorhanden <a name="strompreise_ok"></a>

**Was eedc sieht**
Mindestens ein Tarif mit der Verwendung «Standard (allgemein)» ist angelegt; die Zeile nennt die Zahl der Tarife.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt unter den bestandenen Prüfungen.

**Was ohne Handlung gilt**
eedc rechnet Kosten und Erlöse mit diesen Tarifen.

#### Einspeisung wird mit 0 ct/kWh gerechnet <a name="einspeisung_null_cent"></a>

**Was eedc sieht**
Mindestens ein Tarif der Verwendung «Standard (allgemein)», bei dem «Einspeisevergütung wechselt monatlich» nicht
eingeschaltet ist, trägt 0 ct/kWh Einspeisevergütung, und in seinem Zeitraum ist Einspeisung erfasst (auf ein Jahr
hochgerechnet ab 50 kWh). eedc rechnet den Einspeise-Erlös so, wie es im Tarif steht — in Cockpit, Amortisation und
Jahresbericht bleibt er 0 €. Ein neuer Tarif startet mit 0; eedc rät den Satz bewusst nicht.

**Lösungsweg**
1. Ist deine Einspeisung wirklich unvergütet (Nulleinspeisung, Volleinspeisung ohne Vergütung, ausgelaufene
   EEG-Förderung): nichts zu tun — 0 ist dann richtig.
2. Bekommst du eine Vergütung: am Befund **«Tarif bearbeiten»** klicken — der Tarif öffnet sich am Feld
   «Einspeisevergütung (ct/kWh)». Den Satz aus deinem Vergütungsbescheid eintragen; bei gestaffelter Vergütung den nach
   kWp gewichteten Mischsatz, denn eedc rechnet mit einem Satz. **«Speichern»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach Schritt 2 ist die Zeile verschwunden; nach Schritt 1
   bleibt sie als Auskunft stehen.

**Was ohne Handlung gilt**
Der Einspeise-Erlös dieser Zeiträume bleibt 0 €; alles andere rechnet unverändert.

#### Monate vor dem ersten Tarif <a name="monate_vor_erstem_tarif"></a>

**Was eedc sieht**
Es gibt erfasste Monate, deren Monatserster vor dem «Gültig ab» deines ältesten Tarifs liegt — ein Tarif ab dem 15.
zählt erst für den Folgemonat; die Zeile nennt ihre Zahl und den Tarifbeginn. Diese Monate rechnen nicht mit deinem
Preis, sondern mit der Vorbelegung von eedc (bzw. mit einem im Monat gepflegten Durchschnittspreis).

**Lösungsweg**
1. Am Befund **«Tarif bearbeiten»** klicken — der älteste Tarif öffnet sich am Feld «Gültig ab».
2. Das Datum auf den Beginn deiner Daten zurücksetzen und **«Speichern»**. Galt damals ein anderer Preis, stattdessen
   unter [Strompreise](eedc:/einstellungen/stammdaten?block=strompreise) mit **«Neuer Tarif»** einen Tarif für diesen
   Zeitraum anlegen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; die Auswertungen rechnen sofort
   neu.

**Was ohne Handlung gilt**
Netzbezug und Einspeisung dieser Monate werden mit der Vorbelegung bewertet; Kosten, Ersparnis und Amortisation weichen
entsprechend ab.

#### Lücke zwischen Tarifen <a name="strompreis_luecke"></a>

**Was eedc sieht**
Ab dem früheren von Inbetriebnahme der Anlage und erstem erfassten Monat gibt es einen Zeitraum, für den kein Tarif gilt
— zwischen zwei aufeinanderfolgenden Tarifen oder vor dem ersten. Die Zeile nennt Anfang und Ende. Für diese Monate
fehlt dein Strompreis in der Kostenrechnung.

**Lösungsweg**
1. Am Befund **«Tarif anlegen»** klicken — das Formular «Neuen Tarif anlegen» öffnet sich mit «Gültig ab» am Beginn der
   Lücke.
2. Die Preise dieses Zeitraums eintragen und **«Anlegen»**. Galt einfach der vorige Tarif weiter, stattdessen bei ihm
   das «Gültig bis» auf den Tag vor dem nächsten Tarif setzen; liegt die Lücke vor dem ersten Tarif, dessen «Gültig ab»
   auf den Beginn zurücksetzen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Monate der Lücke rechnen nicht mit deinem Tarif, sondern mit der Vorbelegung von eedc — Netzbezug 30 ct/kWh,
Einspeisung 8,2 ct/kWh (bzw. mit im Monat gepflegten Durchschnittspreisen); Kosten und Ersparnis dieser Monate weichen
entsprechend ab.

#### Zeittarif ohne Stundenwerte <a name="zeittarif_ohne_stundenwerte"></a>

**Was eedc sieht**
Ein Tarif hat Zeitfenster (etwa Hoch- und Niedertarif), aber es gibt keine gemessenen Stundenwerte des Netzbezugs. Die
Fenster gewichtet eedc über diese Stundenwerte — die gibt es nur, wo der Netzbezug über einen zugeordneten Sensor läuft.
Ohne sie rechnet eedc mit dem Arbeitspreis des Tarifs, also dem Hochtarif: deine Stromkosten stehen zu hoch, Ersparnis
und Amortisation zu niedrig.

**Lösungsweg**
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich am Feld für den Netzbezug. Den
   Sensor deines Netzbezugszählers zuordnen.
2. Ohne Sensor: Steht der Tarif auf der Vertragsart «Dynamischer Tarif», zeigt der Monatsabschluss das Feld
   «Ø Strompreis (dynamisch)» — dort den Durchschnittspreis aus deiner Abrechnung eintragen; er gilt vor dem Tarif.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald Stundenwerte vorliegen.

**Was ohne Handlung gilt**
Der Netzbezug wird zum Arbeitspreis des Tarifs bewertet; die günstigeren Zeitfenster bleiben unberücksichtigt.

#### Zwei Tarife beginnen am selben Tag <a name="tarife_gleicher_tag"></a>

**Was eedc sieht**
Zwei oder mehr Tarife derselben Verwendung haben dasselbe «Gültig ab»; die Zeile nennt sie. Dann ist nicht bestimmt,
welcher Satz rechnet — eedc nimmt einen davon, ohne dass eine Regel entscheidet.

**Lösungsweg**
1. Am Befund **«Tarif bearbeiten»** klicken — einer der betroffenen Tarife öffnet sich.
2. Sein «Gültig ab» auf den richtigen Tag setzen und **«Speichern»** — oder einen doppelten Tarif unter
   [Strompreise](eedc:/einstellungen/stammdaten?block=strompreise) löschen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet ab diesem Tag mit einem der Tarife; welcher, ist zufällig und kann sich ändern.

#### Wärmepumpe rechnet mit dem allgemeinen Tarif <a name="wp_allgemeiner_tarif"></a>

**Was eedc sieht**
Eine aktive Wärmepumpe ist vorhanden, aber kein Tarif mit der Verwendung «Wärmepumpe (Spezialtarif)». Der Strom der
Wärmepumpe wird deshalb mit dem allgemeinen Arbeitspreis bewertet. Ob du einen eigenen Tarif hast, kann eedc nicht von
„noch nicht eingetragen“ unterscheiden — deshalb sagt die Zeile, womit gerechnet wird.

**Lösungsweg**
1. Mit Einheitstarif: nichts zu tun — die Rechnung stimmt bereits.
2. Mit eigenem Wärmestrom-Tarif (§14a, Hoch-/Niedertarif, eigener Zähler): unter
   [Strompreise](eedc:/einstellungen/stammdaten?block=strompreise) **«Neuer Tarif»**, Verwendung «Wärmepumpe
   (Spezialtarif)», Preise und «Gültig ab» eintragen, **«Anlegen»**. Hängen Wärmepumpe und Wallbox an einem Zähler:
   Verwendung «Wärmepumpe und Wallbox (gemeinsamer Zähler)».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach Schritt 2 ist die Zeile verschwunden; mit Einheitstarif
   bleibt sie als Auskunft stehen.

**Was ohne Handlung gilt**
Der Strom der Wärmepumpe wird zum allgemeinen Arbeitspreis bewertet — bei Einheitstarif ist das richtig.

#### Kein eigener Ladetarif <a name="kein_ladetarif"></a>

**Was eedc sieht**
Ein E-Auto oder eine Wallbox ist aktiv, aber es gibt keinen Tarif mit der Verwendung «Wallbox (Spezialtarif)». eedc
rechnet die Ladung deshalb mit dem allgemeinen Tarif. Ob du einen eigenen Ladetarif hast, kann eedc nicht von „noch
nicht eingetragen“ unterscheiden — deshalb sagt die Zeile, womit gerechnet wird.

**Lösungsweg**
1. Ohne eigenen Ladetarif: nichts zu tun — die Rechnung stimmt bereits.
2. Mit eigenem Ladetarif: unter [Strompreise](eedc:/einstellungen/stammdaten?block=strompreise) **«Neuer Tarif»**,
   Verwendung «Wallbox (Spezialtarif)», Preise und «Gültig ab» eintragen, **«Anlegen»**. Hängen Wärmepumpe und Wallbox
   an einem Zähler: Verwendung «Wärmepumpe und Wallbox (gemeinsamer Zähler)».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach Schritt 2 ist die Zeile verschwunden; ohne Ladetarif
   bleibt sie als Auskunft stehen.

**Was ohne Handlung gilt**
Die Ladung wird zum allgemeinen Arbeitspreis bewertet — ohne eigenen Ladetarif ist das richtig.

#### Arbeitspreis ungewöhnlich <a name="arbeitspreis_ungewoehnlich"></a>

**Was eedc sieht**
Der Arbeitspreis eines Tarifs liegt außerhalb von 5 bis 80 ct/kWh; die Zeile nennt Wert und Tarif. Meist ist es ein
Eingabefehler — Komma statt Punkt oder €/kWh statt ct/kWh.

**Lösungsweg**
1. Am Befund **«Tarif bearbeiten»** klicken — der Tarif öffnet sich am Feld «Netzbezug (ct/kWh)».
2. Den Preis in Cent je kWh eintragen (z. B. 32 statt 0,32) und **«Speichern»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Ist der Preis wirklich so, bleibt
   sie stehen.

**Was ohne Handlung gilt**
eedc rechnet mit dem eingetragenen Preis; Kosten und Ersparnis stimmen nur, wenn er stimmt.

#### Einspeisevergütung ungewöhnlich <a name="einspeiseverguetung_ungewoehnlich"></a>

**Was eedc sieht**
Die Einspeisevergütung eines Tarifs liegt außerhalb von 0 bis 30 ct/kWh; die Zeile nennt Wert und Tarif. Negative oder
sehr hohe Sätze sind meist ein Eingabefehler.

**Lösungsweg**
1. Am Befund **«Tarif bearbeiten»** klicken — der Tarif öffnet sich am Feld «Einspeisevergütung (ct/kWh)».
2. Den Satz in Cent je kWh eintragen und **«Speichern»**. Bei Direktvermarktung mit wechselnder Vergütung
   «Einspeisevergütung wechselt monatlich» einschalten **und** als Satz eine Schätzung zwischen 0 und 30 ct/kWh
   eintragen — der Schalter allein lässt die Zeile stehen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Ist der Satz wirklich so, bleibt
   sie stehen.

**Was ohne Handlung gilt**
eedc rechnet den Einspeise-Erlös mit dem eingetragenen Satz.

### 4.2a Strompreise – eigener WP-/Wallbox-Tarif <a name="42a-eigener-waermepumpen-tarif"></a>

**Was wird geprüft:** Gilt im laufenden Monat ein Tarif mit Verwendung *Wärmepumpe*, *Wallbox* oder *Wärmepumpe und
Wallbox (gemeinsamer Zähler)*, dessen Arbeitspreis vom Standard-Tarif abweicht — und ist in den letzten zwölf
abgeschlossenen Monaten der **Netzbezug zum Tarif** gemessen, plausibel und richtig angeschlossen?

**Warum das zählt:** Mit eigenem Tarif rechnet dein Versorger einen Teil des Netzbezugs zu diesem Tarif ab. Misst du diese
Menge (Feld **«Netzbezug zum WP-Tarif»** bzw. **«Netzbezug zum Wallbox-Tarif»**,
[Wärme & Klima, Schritt 6b](HANDBUCH_WAERME_KLIMA.md#schritt-6b--netzbezug-zum-wp-tarif-optional-nur-mit-eigenem-wärmepumpen-tarif)),
rechnet eedc Stromrechnung und Eigenverbrauchs-Ersparnis genau. Ohne sie bewertet eedc den PV-Strom der Wärmepumpe zum
Haushaltstarif und rechnet ihren bzw. den Netzbezug der Wallbox in der Stromrechnung zum Haushaltstarif — beide Zahlen
liegen dann zusammen um bis zu *Gerätemenge × Tarifdifferenz* daneben
([Berechnungen, „Mit eigenem Wärmepumpen-Tarif“](BERECHNUNGEN.md#mit-eigenem-wärmepumpen-tarif--netzbezug-zum-wp-tarif-oder-grenze-n-767-n-770)).

**Gemeinsamer Zähler:** Hängen Wärmepumpe und Wallbox hinter einem Zähler, trägt das Feld «Netzbezug zum WP-/Wallbox-Tarif
(gemeinsamer Zähler)» an der Wärmepumpe den gemeinsamen Netzbezug; die Proben rechnen dann mit WP-Strom **und** Ladung
aller Wallboxen als Gerätemenge.

---

#### Netzbezug zum Wallbox-Tarif zählt unter dem gemeinsamen Tarif nicht <a name="wp_tarif_wallbox_netzbezug_zaehlt_nicht"></a>

**Was eedc sieht**
Für Wärmepumpe und Wallbox gilt ein gemeinsamer Tarif (ein Zähler vor beiden Geräten). Den gemeinsamen Netzbezug trägt
das Feld «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)» an der Wärmepumpe. An der Wallbox ist zusätzlich
«Netzbezug zum Wallbox-Tarif» zugeordnet oder in einer Monatszeile der letzten zwölf abgeschlossenen Monate gefüllt —
dieser Wert zählt in der Stromrechnung nicht, er stünde sonst doppelt.

**Lösungsweg**
1. Am Befund **«Tarif bearbeiten»** klicken — der gemeinsame Tarif öffnet sich. Prüfen, ob er stimmt: Haben die Geräte
   getrennte Zähler, ist die Verwendung «Wärmepumpe und Wallbox (gemeinsamer Zähler)» falsch.
2. Stimmt der gemeinsame Tarif: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) die Zuordnung
   «Netzbezug zum Wallbox-Tarif» an der Wallbox lösen und den gemeinsamen Zähler an der Wärmepumpe zuordnen (Handbuch
   «Wärme & Klima», Schritt 6b).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald weder eine Zuordnung noch
   ein Monatswert der letzten zwölf abgeschlossenen Monate das Feld an der Wallbox trägt.

**Was ohne Handlung gilt**
eedc rechnet den gemeinsamen Netzbezug von der Wärmepumpe; der Wert an der Wallbox bleibt in der Stromrechnung
unberücksichtigt.

#### Paralleler Zähler am Gerät <a name="paralleler_zaehler"></a>

**Was eedc sieht**
Das Gerät misst seinen Stromverbrauch (bzw. die Ladung) und den Netzbezug zum eigenen Tarif mit demselben Sensor: ein
eigener Zähler parallel zum Hauszähler, das Gerät bezieht keinen PV-Strom. Das ist zulässig — dann muss aber der
Netzbezug der Anlage diesen Zähler enthalten. Fehlt er dort, ist der Netzbezug zu klein, und eedc begrenzt den Anteil
zum eigenen Tarif auf den Netzbezug. Dasselbe gilt beim gemeinsamen Zähler für Wärmepumpe und Wallbox.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät.
2. Prüfen, ob der [Netzbezug der Anlage](eedc:/einstellungen/datenquellen?feld=netzbezug_kwh) beide Zähler enthält:
   Netzbezug der Anlage = Hauszähler + Zähler des Geräts. Wenn nicht, dort einen Sensor zuordnen, der beide Zähler
   zusammen misst.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt als Hinweis, solange der parallele Zähler
   besteht; eine Warnung, der Netzbezug zum Tarif sei größer als der Netzbezug der Anlage, verschwindet, wenn der
   Netzbezug stimmt.

**Was ohne Handlung gilt**
eedc rechnet mit dem zugeordneten Netzbezug; enthält er den Gerätezähler nicht, ist er zu klein und der Anteil zum
eigenen Tarif wird darauf begrenzt.

#### Netzladung aus evcc weicht vom Netzbezug zum Wallbox-Tarif ab <a name="evcc_netzladung_abweichung"></a>

**Was eedc sieht**
Die Wallbox trägt in den genannten Monaten neben «Netzbezug zum Wallbox-Tarif» einen PV-/Netz-Anteil der Ladung (etwa
aus evcc), und beide nennen eine andere Netzladung (Unterschied um mehr als 0,5 kWh und zugleich mehr als 2 % der
Ladung — die größere der beiden Grenzen). eedc rechnet mit dem
Zähler des Versorgers: Netzladung = Netzbezug zum Wallbox-Tarif, PV-Ladung = Ladung minus Netzladung — für Ersparnis,
Heimladekosten und Stromrechnung.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der Wallbox (ein eigenes Feld
   für die Netzladung gibt es dort nicht; der PV-/Netz-Anteil steht in der Monatszeile der Wallbox).
2. Prüfen, ob beide Sensoren dieselbe Wallbox messen. Misst einer ein anderes Gerät oder einen anderen Zeitraum, die
   Zuordnung berichtigen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind
   und beide Werte übereinstimmen.

**Was ohne Handlung gilt**
eedc nimmt den Netzbezug zum Wallbox-Tarif als Netzladung; der PV-/Netz-Anteil aus der anderen Quelle bleibt für diese
Monate unberücksichtigt.

#### Eigener Tarif hat Vorrang vor dem gemeinsamen Tarif <a name="eigener_tarif_vorrang"></a>

**Was eedc sieht**
Zum selben Stichtag gelten ein Tarif «Wärmepumpe (Spezialtarif)» bzw. «Wallbox (Spezialtarif)» und ein Tarif «Wärmepumpe
und Wallbox (gemeinsamer Zähler)». eedc rechnet das Gerät mit seinem eigenen Tarif; der gemeinsame gilt nur noch für
das andere Gerät — dann ist es kein gemeinsamer Zähler mehr.

**Lösungsweg**
1. Am Befund **«Tarif bearbeiten»** klicken — der eigene Tarif des Geräts öffnet sich.
2. Hängen beide Geräte hinter einem Zähler: beim eigenen Tarif «Gültig bis» auf den Tag vor dem gemeinsamen Tarif
   setzen und **«Speichern»**; löschen nur, wenn er nie allein gegolten hat (sonst ändern sich die Stromrechnungen der
   Monate davor). Haben die Geräte wirklich getrennte Zähler, stattdessen den
   gemeinsamen Tarif beenden und für das andere Gerät einen eigenen anlegen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Das Gerät mit eigenem Tarif rechnet zu diesem, das andere zum gemeinsamen Tarif.

#### Gemeinsamer Zähler: Tage teilen die Ersparnis nicht <a name="gemeinsamer_zaehler_tage_ohne_teilung"></a>

**Was eedc sieht**
Beim gemeinsamen Zähler für Wärmepumpe und Wallbox rechnet die Stromrechnung je Tag mit den Stunden des gemeinsamen
Netzbezugs. Die Eigenverbrauchs-Ersparnis teilt der einzelne Tag aber nicht in Wärmepumpe und Wallbox, weil Stundenwerte
der Netzladung der Wallbox fehlen. Der Monat trägt den genauen Wert; die Summe der Tage weicht bei der Ersparnis davon
ab. Das ist eine bekannte Grenze, kein Fehler deiner Daten.

**Lösungsweg**
1. Der Knopf **«Was gilt»** am Befund öffnet diesen Abschnitt: Für Monat und Jahr gilt der Monatswert; die Tagesansicht im Cockpit
   rechnet die Ersparnis ohne die Teilung.
2. Nichts zu tun.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt als Auskunft stehen, solange der gemeinsame
   Tarif gilt.

**Was ohne Handlung gilt**
Monats- und Jahreswerte stimmen; einzelne Tage zeigen die Ersparnis ohne Teilung zwischen Wärmepumpe und Wallbox.

#### Netzladung der Wallbox größer als der gemeinsame Netzbezug <a name="wallbox_netzladung_groesser_gemeinsamer_netzbezug"></a>

**Was eedc sieht**
Beim gemeinsamen Zähler für Wärmepumpe und Wallbox ist in den genannten Monaten die Netzladung der Wallbox (Wert aus
evcc bzw. Tagesquote) größer als «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)». eedc setzt den Wallbox-Teil
auf den gemeinsamen Netzbezug; der Wärmepumpe bleibt dann kein Netzanteil.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der Wärmepumpe am Feld
   «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)»; ist nicht eindeutig, welche Wärmepumpe den gemeinsamen Zähler
   trägt, öffnet sie sich ohne Feld.
2. Den gemeinsamen Zähler prüfen (Zähler vor beiden Geräten minus Zähler danach) und die Netzladung der Wallbox: misst
   ihr Sensor wirklich nur Netzstrom dieser Wallbox?
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind.

**Was ohne Handlung gilt**
Der gemeinsame Netzbezug geht ganz an die Wallbox; die Wärmepumpe rechnet in diesen Monaten ohne Netzanteil zum Tarif.

#### Eigener Tarif ohne gemessenen Netzbezug zum Tarif <a name="wp_eigener_tarif_obergrenze"></a>

**Was eedc sieht**
Für Wärmepumpe oder Wallbox gilt ein eigener Tarif mit anderem Arbeitspreis als der Haushaltstarif, aber in Monaten der
letzten zwölf fehlt das Feld «Netzbezug zum WP-Tarif» bzw. «Netzbezug zum Wallbox-Tarif» (beim gemeinsamen Zähler
«Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)»). Ohne diese Menge bewertet eedc den Strom des Geräts zum
Haushaltstarif. Die Zeile nennt die Obergrenze, um die Ersparnis und Stromrechnung zusammen daneben liegen können:
Gerätemenge dieser Monate × Tarifdifferenz.

**Lösungsweg**
1. Der Knopf **«Was gilt»** am Befund öffnet diesen Abschnitt: eedc rechnet ohne das Feld mit dem Haushaltstarif; die genannte
   Summe ist eine Obergrenze, keine gemessene Abweichung.
2. Misst dein Versorger den Tarif-Strom über einen Zähler, ihn in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen?feld=netzbezug_eigener_tarif_kwh) beim Gerät im Block
   «Gerät gesamt» zuordnen — gemeint ist der Zähler des Versorgers: Zähler vor dem Gerät minus Zähler nach dem Gerät.
   Mehr dazu im Handbuch «Wärme & Klima», Schritt 6b.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald das Feld in allen Monaten
   mit Gerätestrom einen Wert hat; ohne Zähler bleibt sie als Auskunft stehen.

**Was ohne Handlung gilt**
Ersparnis und Stromrechnung rechnen den Strom des Geräts zum Haushaltstarif und liegen zusammen höchstens um die
genannte Summe daneben.

#### Netzbezug zum Tarif größer als der Verbrauch des Geräts <a name="tarif_mengenfeld_groesser_als_menge"></a>

**Was eedc sieht**
In den genannten Monaten ist «Netzbezug zum WP-Tarif» bzw. «Netzbezug zum Wallbox-Tarif» größer als der Stromverbrauch
bzw. die Ladung des Geräts (Toleranz 2 %). Beim gemeinsamen Zähler ist die Vergleichsmenge WP-Strom und Ladung
zusammen. Mehr, als das Gerät verbraucht, kann der Versorger nicht zum eigenen Tarif abgerechnet haben — eedc begrenzt
den Monat auf den Verbrauch; die Herleitung zeigt es als «begrenzt».

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim betroffenen Gerät
   (Wärmepumpe bzw. Wallbox; beim gemeinsamen Zähler die Wärmepumpe) am Feld für den Netzbezug zum Tarif; ist nicht
   eindeutig, welches Gerät es trägt, öffnet sie sich ohne Feld.
2. Prüfen, ob dort der richtige Sensor steht: der Zähler des Versorgers, also Zähler vor dem Gerät minus Zähler nach dem
   Gerät — und ob der Verbrauch des Geräts vollständig zugeordnet ist.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind.

**Was ohne Handlung gilt**
eedc rechnet in diesen Monaten mit dem Verbrauch des Geräts als Netzbezug zum Tarif, nicht mit dem höheren Wert.

#### Netzbezug zum Tarif größer als der Netzbezug der Anlage <a name="tarif_mengenfeld_groesser_als_rest"></a>

**Was eedc sieht**
In den genannten Monaten ist «Netzbezug zum WP-Tarif» bzw. «Netzbezug zum Wallbox-Tarif» größer als der Netzbezug der
Anlage — an der Wallbox größer als der Rest, der nach der Wärmepumpe bleibt. Mehr kann nicht zum eigenen Tarif
abgerechnet sein; die Stromrechnung begrenzt den Anteil darauf, die Herleitung zeigt es als «begrenzt». Die Zeile der
E-Mobilität behält die Netzladung bis zur Ladung. Häufige Ursache: ein paralleler Zähler, der im Netzbezug der Anlage
fehlt.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim betroffenen Gerät
   (Wärmepumpe bzw. Wallbox; beim gemeinsamen Zähler die Wärmepumpe) am Feld für den Netzbezug zum Tarif; ist nicht
   eindeutig, welches Gerät es trägt, öffnet sie sich ohne Feld.
2. Hängt das Gerät an einem eigenen Zähler neben dem Hauszähler, muss der Netzbezug der Anlage beide enthalten:
   Netzbezug der Anlage = Hauszähler + Zähler des Geräts. Den
   [Netzbezug der Anlage](eedc:/einstellungen/datenquellen?feld=netzbezug_kwh) entsprechend zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind.

**Was ohne Handlung gilt**
Der Anteil zum eigenen Tarif wird auf den Netzbezug der Anlage begrenzt; der Netzbezug selbst bleibt zu klein, wenn der
parallele Zähler darin fehlt.

### 4.3 Investitionen

**Was wird geprüft:** Je aktive Komponente die Pflicht- und Plausibilitätsangaben ihres Typs, danach je Komponententyp
die Vollständigkeit der monatlichen Verbrauchs- bzw. Erzeugungswerte ab dem Anschaffungsdatum. Anschaffungsdatum und
-kosten werden für alle Typen geprüft — Ausnahmen: ein Dienstwagen bekommt keine dieser Prüfungen, ein Verbrauchszähler
keine Kosten-Frage. Die PV-Erzeugung wird anlagenweit geprüft, nicht je Modul.

**Wohin die Knöpfe führen:** «Gerät bearbeiten» öffnet das Formular der Komponente beim fehlenden Feld
(*Einstellungen → Komponenten*); «Monat öffnen» öffnet den Monatsabschluss des ersten betroffenen Monats beim Feld des
Geräts (*Einstellungen → Daten → Monatsdaten*); «Zuordnung prüfen» und «Sensor zuordnen» öffnen die
*Einstellungen → Datenquellen → Datenquellen-Zuordnung* beim Gerät.

**Gefragt wird nur nach Größen, die eedc an deinem Gerät erwartet** — das sagt die Einstellung des Geräts (etwa die
Wärmepumpenart, «Getrennte Strommessung» oder die «Kategorie» unter Sonstiges), nicht ein fester Katalog je Bauart. Ein
Wert in einem Feld, das das Gerät danach nicht führt, wird eigens gemeldet und lässt sich mit «Wert entfernen» löschen.

#### PV-Erzeugung fehlt in Monaten <a name="pv_erzeugung_fehlt_monate"></a>

**Was eedc sieht**
Für diese Monate gibt es gar keine PV-Quelle — weder einen Wert je PV-Modul noch einen Gesamtwert der Anlage. Ohne
PV-Erzeugung fehlen Eigenverbrauch, Autarkie und Ersparnis dieser Monate. Geprüft wird anlagenweit, nicht je Modul: ein
einziger Gesamtwert deckt alle Strings ab. Bei Anlagen mit eigenem Zähler am Balkonkraftwerk kann ein Monat auch ohne
dein Zutun leer sein — eine frühere Start-Migration hat dort den Gesamtwert mitgeleert. Zurückholen kann eedc ihn nicht;
die Schritte unten füllen die Monate neu.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «PV-Erzeugung» eines PV-Moduls.
2. Ist ein PV-Sensor zugeordnet, holt
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) die Monate auf
   einmal; der Monatsabschluss tut es für seinen Monat. Beide schreiben die Werte je Modul.
3. Ohne zugeordneten Sensor die Werte von Hand eintragen — je Modul oder als Gesamtwert der Anlage — und speichern.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

Die Reparatur-Werkbank hilft hier nicht: «Tag neu aggregieren» und «Mehrere Tage neu aggregieren» bauen das stündliche
Energieprofil neu, nicht die Monatswerte.

**Was ohne Handlung gilt**
Die Monate bleiben ohne PV-Erzeugung: Bilanz, Jahreswerte und Wirtschaftlichkeit rechnen ohne sie. eedc setzt keine 0
und schätzt nichts.

#### PV-Erzeugung nur teilweise erfasst <a name="pv_erzeugung_unvollstaendig"></a>

**Was eedc sieht**
In diesen Monaten hat nur ein Teil der PV-Module (Strings) einen Wert, und es gibt keinen Gesamtwert der Anlage, den eedc
auf die übrigen verteilen könnte. Die Monatssichten zeigen die Summe der erfassten Strings (und des Balkonkraftwerks);
die Monats- und die Jahresansicht im Cockpit sagen dazu, dass es eine Teilsumme ist. Die Prüfungen des Daten-Checkers
rechnen mit einer Teilsumme nicht — sonst meldeten sie Abweichungen, die es nicht gibt.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «PV-Erzeugung» eines PV-Moduls.
2. Entweder für die fehlenden Module den Wert eintragen **oder** den Gesamtwert der Anlage — eedc verteilt ihn dann nach
   kWp auf die Module ohne eigenen Wert. Speichern; die übrigen Monate der Meldung ebenso. Mit zugeordneten Sensoren
   holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere
   Monate auf einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die vervollständigten Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Die Sichten zeigen die Teilsumme. Sie ist zu niedrig, wenn dem fehlenden String Erzeugung fehlt; war er wirklich aus,
stimmt sie.

#### PV-Erzeugung über den kWp-Anteil verteilt <a name="pv_erzeugung_geschaetzt"></a>

**Was eedc sieht**
In diesen Monaten hat mindestens ein PV-Modul keinen eigenen Wert, die Anlage aber einen Gesamtwert. eedc verteilt den
Rest (Gesamtwert minus die gemessenen Module) nach Nennleistung auf die Module ohne Wert; gemessene Module behalten ihren
Wert. Die Summe stimmt, nur die Aufteilung je String ist geschätzt — deshalb nennen die String-Sichten in diesen Monaten
keinen besten oder schwächsten String. Ein Balkonkraftwerk mit zugeordneten PV-Modulen ist selbst ein Gesamtwert für
seine Module: hat es einen Wert und eines seiner Module nicht, gilt der Monat ebenso als abgedeckt.

**Lösungsweg**
1. Am Befund **«Was gilt»** klicken — dieser Text. Das ist kein Mangel; wenn dir die Summe genügt, ist nichts zu tun.
2. Wer echte Werte je String will, ordnet jedem PV-Modul einen eigenen Erzeugungs-Zähler zu, in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim jeweiligen Modul. Vergangene Monate füllt danach
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein Modul in diesen Monaten keinen
   eigenen Wert hat.

**Was ohne Handlung gilt**
Die PV-Erzeugung der Anlage stimmt; die Werte je String sind in diesen Monaten nach kWp verteilt und keine Messung.

#### PV-Erzeugung: Monatsdaten vollständig <a name="pv_erzeugung_ok"></a>

**Was eedc sieht**
Jedes im Monat aktive PV-Modul hat für jeden Monat einen eigenen Messwert — die PV-Erzeugung der Anlage ist lückenlos
erfasst.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange jeder Monat einen Wert je Modul
   hat.

**Was ohne Handlung gilt**
Monats-, Jahres- und String-Sichten rechnen mit den gemessenen Werten je Modul.

#### Monatswert eines Geräts fehlt <a name="geraet_feld_fehlt_monate"></a>

**Was eedc sieht**
Ein Pflichtfeld des Geräts ist in den genannten Monaten ab dem Anschaffungsdatum leer; die Meldung nennt Gerät und Feld.
Typische Fälle: «Speicher-Ladung» (ohne sie gibt es für diese Monate keine Vollzyklen und keinen Wirkungsgrad), «Ladung
gesamt» an der Wallbox, «Ladung PV» an einem E-Auto ohne Wallbox (der PV-Anteil der Ladung bleibt unbekannt) und
«PV-Erzeugung» am Balkonkraftwerk. Das Balkonkraftwerk wird nur gemeldet, wenn es weder einen eigenen Wert noch einen
Anteil am PV-Gesamtwert der Anlage hat — mit gespeichertem Gesamtwert bekommt es seinen kWp-Anteil, dann fehlt nichts.
E-Autos mit Wallbox und Dienstwagen werden nach «Ladung PV» nicht gefragt.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld des
   Geräts. Im Formular heißt es am Speicher «Ladung», am E-Auto «Heim: PV», am Balkonkraftwerk «Erzeugung».
2. Den Wert eintragen (auch 0 ist ein Wert) und speichern, die übrigen Monate der Meldung ebenso. Ist am Gerät ein Sensor
   zugeordnet, holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import)
   mehrere Monate auf einmal. Am Balkonkraftwerk genügt auch der PV-Gesamtwert der Anlage im selben Monat.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Die Monate bleiben ohne diesen Wert; die Auswertungen des Geräts rechnen für sie nicht oder unvollständig. eedc setzt
keine 0.

#### Monatsdaten eines Geräts vollständig <a name="geraet_monate_ok"></a>

**Was eedc sieht**
Alle Pflicht-Monatsfelder dieses Geräts sind für jeden erfassten Monat der Anlage ab dem Anschaffungsmonat gefüllt.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange jeder Monat seinen Wert hat.

**Was ohne Handlung gilt**
Die Auswertungen des Geräts rechnen mit vollständigen Monaten.

#### Wert in einem Feld, das das Gerät nicht führt <a name="feldwert_nicht_gefuehrt"></a>

**Was eedc sieht**
In den genannten Monaten steht ein Wert (nicht 0) in einem Feld, das dieses Gerät nach seinen Einstellungen nicht führt:
Netzladung an einem Speicher ohne «Lädt aus dem Netz», V2H-Entladung an einem E-Auto ohne «V2H-fähig», Speicherwerte an
einem Balkonkraftwerk ohne «Mit Speicher», getrennte Ströme Heizen/Warmwasser nach Abschalten der getrennten
Strommessung, Warmwasser-Wärme an einer Split-Klimaanlage — oder unter Sonstiges ein Feld, das die gewählte «Kategorie»
nicht liest. Das Feld fehlt deshalb im Monatsabschluss, der Wert ist dort nicht erreichbar und zählt in keiner Bilanz.
Eine Meldung je Feld, nicht je Monat.

**Lösungsweg**
1. Prüfen, ob die Einstellung am Gerät stimmt.
2. Stimmt sie: am Befund **«Wert entfernen»** klicken, die Vorschau lesen, **«Anwenden»** — der Wert verschwindet aus
   allen genannten Monaten. Das ist endgültig.
3. Soll der Wert weiter zählen: stattdessen die Einstellung am Gerät zurückstellen (*Einstellungen → Komponenten*, das
   Gerät bearbeiten; unter Sonstiges die «Kategorie») — dann erscheint das Feld wieder im Monatsabschluss.
4. Vorher umtragen, wo der Wert woanders hingehört: Warmwasser-Wärme einer Split-Klimaanlage, die aus dem Kühlbetrieb
   stammt, im Monatsabschluss unter «Nutzenergie Kühlbetrieb» — daraus rechnet eedc die Arbeitszahl Kühlen. Ein Gerät,
   das von «Erzeuger» auf «Abgabe an Dritte» umgestellt wurde: die alte Menge aus «Erzeugung» oder «Verbrauch» unter
   *Einstellungen → Daten → Monatsdaten* ins Feld «Abgabe» eintragen. Danach Schritt 2.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Der Wert bleibt gespeichert, zählt aber nirgends mit. eedc löscht und verschiebt nichts von allein.

#### Heiz- und Kühlstrom größer als der Gesamtverbrauch <a name="wp_heiz_kuehl_groesser_gesamt"></a>

**Was eedc sieht**
Die Aufteilung des Wärmepumpen-Stroms nach Heizen und Kühlen ist ein Teil des Gesamtverbrauchs — zusammen kann sie ihn
nicht übersteigen. In den genannten Monaten übersteigt sie ihn um mehr als 0,5 kWh; meist, weil der Gesamtwert
nachträglich kleiner eingetragen wurde als die schon gespeicherte Aufteilung. Die Energiebilanz ist nicht betroffen,
dort zählt immer der Gesamtwert.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «Stromverbrauch» der Wärmepumpe.
2. Den Stromverbrauch prüfen und berichtigen, falls er zu klein ist.
3. Den Monat erneut speichern — eedc rechnet die Aufteilung neu und verwirft sie, wenn sie nicht passt. Die übrigen
   Monate der Meldung ebenso.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Bilanz, Kosten und CO₂ rechnen mit dem Gesamtwert; nur die Aufteilung nach Heizen und Kühlen ist in diesen Monaten
widersprüchlich.

#### Wärme gesamt kleiner als die Einzelwerte <a name="wp_gesamtwaerme_kleiner_teile"></a>

**Was eedc sieht**
«Wärme gesamt» ist die Wärme des ganzen Geräts — Heizung und Warmwasser zusammen. In diesen Monaten steht dort um mehr als
0,5 kWh weniger als in «Heizwärme» und «Warmwasser-Wärme» zusammen; einer der Werte meint also etwas anderes als
gedacht, häufig ist die Heizwärme unter «Wärme gesamt» gelandet. eedc rechnet mit der Gesamtwärme — Wärmemenge,
Arbeitszahl, Ersparnis und CO₂ dieser Monate fallen deshalb zu niedrig aus.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich bei den
   Wärmewerten der Wärmepumpe.
2. Prüfen, welcher Zähler welchen Wert liefert: Mit **einem** gemeinsamen Wärmemengenzähler gehört sein Wert unter
   «Wärme gesamt», «Heizwärme» und «Warmwasser-Wärme» bleiben leer. Mit getrennten Zählern ist es umgekehrt —
   «Wärme gesamt» leer lassen.
3. Berichtigen und speichern, die übrigen Monate der Meldung ebenso.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc rechnet weiter mit der zu kleinen Gesamtwärme; Arbeitszahl, Ersparnis und CO₂ dieser Monate bleiben zu niedrig.

#### Wärme gesamt ist 0, die Einzelwerte nicht <a name="wp_waerme_gesamt_null"></a>

**Was eedc sieht**
In diesen Monaten steht unter «Wärme gesamt» eine 0, während «Heizwärme» und «Warmwasser-Wärme» zusammen mehr als
0,5 kWh tragen. eedc rechnet hier mit den beiden Einzelwerten. Häufigster Grund: Der Wärmemengenzähler hat im Monat
keinen neuen Stand geliefert — keine Statistik in Home Assistant, eingefroren oder erst seit kurzem zugeordnet.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich bei den
   Wärmewerten der Wärmepumpe.
2. Prüfen, ob der Zähler Werte liefert. Misst **ein** Zähler Heizung und Warmwasser zusammen, gehört sein Monatswert
   unter «Wärme gesamt». Mit getrennten Zählern bleibt das Feld leer — die 0 löschen.
3. Speichern, die übrigen Monate der Meldung ebenso.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc rechnet mit Heizwärme und Warmwasser-Wärme; die 0 unter «Wärme gesamt» bleibt gespeichert.

#### Gesamtzähler kleiner als Strom Heizen und Strom Warmwasser <a name="wp_gesamtzaehler_kleiner_achsen"></a>

**Was eedc sieht**
Bei getrennter Strommessung mit zusätzlichem Gesamtzähler sind «Strom Heizen» und «Strom Warmwasser» Teile des
Gesamtverbrauchs und können zusammen nicht mehr sein. In diesen Monaten sind sie es. Meist misst der Gesamtzähler nur
einen Teil des Geräts (nur das Außengerät, nur einen Stromkreis), oder eine der Achsen zählt fremden Verbrauch mit.
Nur diese Richtung ist ein Fehler; ein höherer Gesamtzähler ist der Normalfall (Standby, Steuerung, Umwälzpumpen).

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «Stromverbrauch» der Wärmepumpe.
2. Prüfen, welcher Zähler welchen Wert liefert, und den falschen berichtigen. Kommt er aus Home Assistant, die Zuordnung
   in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen?feld=stromverbrauch_kwh) prüfen.
3. Sagt die Meldung, dass der Gesamtwert aus dem Monatsformular stammt, kann er ein stehen gebliebener alter Stand sein:
   das Feld «Stromverbrauch» leeren und speichern — eedc rechnet ihn dann aus Heizen und Warmwasser. Ist er der Wert
   eines eigenen Gesamtzählers, lass ihn stehen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc rechnet in diesen Monaten mit der Summe der beiden Achsen, damit nichts verloren geht.

#### Gesamtzähler misst deutlich mehr als die Achsen <a name="wp_gesamtzaehler_mehr_als_achsen"></a>

**Was eedc sieht**
Mehr als ein Viertel des Wärmepumpen-Stroms liegt weder auf «Strom Heizen» noch auf «Strom Warmwasser»; eedc führt diese
Menge als „nicht aufgeteilt“. Das ist oft richtig — Standby, Steuerung und Umwälzpumpen laufen auf keiner der beiden
Achsen. Es kann aber auch heißen, dass am Gesamtzähler noch etwas anderes hängt als die Wärmepumpe. Eine Frage, kein
Fehler: eedc weiß nicht, was am Zähler hängt, und behauptet es nicht.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gesamtzähler
   («Stromverbrauch») dieser Wärmepumpe.
2. Prüfen, ob der zugeordnete Sensor nur die Wärmepumpe misst. Stimmt er, ist nichts zu tun.
3. Sagt die Meldung, dass der Gesamtwert aus dem Monatsformular stammt, kann er ein stehen gebliebener alter Stand sein:
   im Monatsabschluss das Feld «Stromverbrauch» leeren und speichern — eedc rechnet ihn dann aus Heizen und Warmwasser.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — stimmt der Zähler, bleibt die Zeile als Hinweis mit dem
   Knopf «Zuordnung prüfen» stehen; sie ist eine Frage, kein Fehler.

**Was ohne Handlung gilt**
Der Rest steht weiter als „nicht aufgeteilt“; Verbrauch, Kosten und CO₂ rechnen mit dem vollen Gesamtzähler.

#### Strom der Wärmepumpe fehlt <a name="wp_strom_fehlt_monate"></a>

**Was eedc sieht**
Für die genannten Monate fehlt der Strom der Wärmepumpe — ohne getrennte Strommessung «Stromverbrauch», mit getrennter
Messung «Strom Heizen» und «Strom Warmwasser» (an einer Split-Klimaanlage nur «Strom Heizen»). Ohne ihn fehlen der
Verbrauch der Wärmepumpe und ihre Arbeitszahl in diesen Monaten.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Stromfeld
   der Wärmepumpe.
2. Den Wert eintragen und speichern, die übrigen Monate der Meldung ebenso. Mit zugeordnetem Sensor holt
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere Monate auf
   einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Die Monate bleiben ohne Wärmepumpen-Strom; Verbrauch, Kosten und Arbeitszahl des Geräts rechnen für sie nicht.

#### Eine Stromseite der Wärmepumpe fehlt <a name="wp_seite_fehlt_monate"></a>

**Was eedc sieht**
Bei getrennter Strommessung ist in diesen Monaten die Wärme einer Seite erfasst, der Strom dafür nicht: «Strom Heizen»
neben einer erfassten «Heizwärme» oder «Strom Warmwasser» neben einer erfassten «Warmwasser-Wärme». eedc bildet jede
Arbeitszahl aus abgegebener Wärme ÷ eingesetztem Strom und setzt dafür beide Seiten voraus. Die Zeile dieser Funktion
sagt es bereits („kein Stromverbrauch erfasst“); die Gesamt-Arbeitszahl rechnet dann die Wärme beider Seiten über dem
Strom einer und fällt zu hoch aus.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim fehlenden
   Feld.
2. Den Wert eintragen und speichern, die übrigen Monate der Meldung ebenso.
3. Soll dieser Zähler künftig von allein mitlaufen, ihn zusätzlich in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei dieser Wärmepumpe zuordnen. Die Zuordnung wirkt nach
   vorn; vergangene Monate füllt nur der Monatsabschluss.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Die Gesamt-Arbeitszahl dieser Monate rechnet mit einem unvollständigen Nenner und fällt zu hoch aus.

#### Heizwärme der Wärmepumpe fehlt <a name="wp_heizwaerme_fehlt_monate"></a>

**Was eedc sieht**
Die abgegebene Wärme fehlt — weder «Heizwärme» noch «Wärme gesamt» noch die «Nutzenergie Heizbetrieb» ist eingetragen.
Ohne sie gibt es für diese Monate keine gemessene Arbeitszahl und keinen COP-Vergleich. Über den Strom sagt diese Zeile
nichts — fehlt er, nennt ihn eine eigene Zeile. Gefragt wird nur an Geräten, an denen eedc eine Heiz-Achse erwartet; an einer Split-Klimaanlage und an einer
Brauchwasser-Wärmepumpe nicht.

**Lösungsweg**
1. Mit Wärmemengenzähler: am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats
   öffnet sich beim Feld «Heizwärme». Den Wert eintragen (ein gemeinsamer Zähler für Heizung und Warmwasser gehört unter
   «Wärme gesamt») und speichern, die übrigen Monate ebenso.
2. Ohne Wärmemengenzähler ist nichts zu tun — der Hinweis bleibt stehen und sagt dir, warum bei der Arbeitszahl ein
   Strich steht.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Arbeitszahl und COP zeigen für diese Monate „—“ statt einer Scheinzahl.

#### Monatsdaten der Wärmepumpe vollständig <a name="wp_monate_ok"></a>

**Was eedc sieht**
Strom (bei getrennter Messung beide Seiten) und Wärme der Wärmepumpe sind für jeden erfassten Monat der Anlage ab dem
Anschaffungsmonat eingetragen.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange jeder Monat seine Werte hat.

**Was ohne Handlung gilt**
Verbrauch, Arbeitszahl und Ersparnis der Wärmepumpe rechnen mit vollständigen Monaten.

#### Aufteilung nach Betriebsart nicht gespeichert <a name="monatsabschluss_hinweis_geraet"></a>

**Was eedc sieht**
Die gemessenen Stunden ergeben für Heizen, Kühlen und Warmwasser zusammen mehr Strom, als im Monatsabschluss für das
ganze Gerät eingetragen ist — oder für den Monat ist gar kein Stromverbrauch eingetragen. Eine Teilmenge kann nicht
größer sein als das Ganze; deshalb hat eedc die Aufteilung beim Abschluss nicht gespeichert, und die Auswertungen zeigen
den Monat als „nicht aufgeteilt“. Die Meldung nennt den Monat und beide Mengen.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss dieses Monats öffnet sich bei der Wärmepumpe.
2. Den Stromverbrauch prüfen: Stimmt er, oder fehlt ein Zähler? Fehlt der Wert, eintragen.
3. Oder in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) prüfen, ob die Leistung des Geräts richtig
   zugeordnet ist.
4. Nach dem Berichtigen den Monat erneut speichern — eedc rechnet die Aufteilung dann neu.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Der Monat bleibt „nicht aufgeteilt“: die Sichten der Wärmepumpe zeigen für ihn keinen Heiz-, Kühl- oder
Warmwasserstrom.

#### Speicher-Kapazität vermutlich in Wh statt kWh <a name="kapazitaet_wh_statt_kwh"></a>

**Was eedc sieht**
Das Balkonkraftwerk, zu dem dieser Speicher gehört, nennt seine Akku-Kapazität in Wh, dieser Speicher seine in kWh — und
beide tragen denselben Zahlenwert. Dann ist die Kapazität tausendfach zu groß, und Vollzyklen, Auslastung und
Wirtschaftlichkeit des Speichers rechnen gegen einen Nenner, den es nicht gibt. Geprüft wird nur dieser Widerspruch der
beiden Felder, keine Obergrenze — ein großer Speicher wird nicht gemeldet.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich beim Feld «Kapazität (kWh)».
2. Die Kapazität in kWh eintragen (die Meldung nennt die Zahl; 5.376 Wh sind 5,376 kWh) und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Vollzyklen, Auslastung und Wirtschaftlichkeit des Speichers bleiben um den Faktor 1000 verzerrt.

#### «Strom Heizbetrieb» und «Strom Heizen» beide belegt <a name="wp_strom_heizbetrieb_und_heizen_belegt"></a>

**Was eedc sieht**
An der Wärmepumpe sind der Betriebsart-Zähler «Strom Heizbetrieb» und der Zähler «Strom Heizen» zugeordnet
(Home-Assistant-Sensor oder MQTT). Der Betriebsart-Zähler hat Vorrang — «Strom Heizen» wird nicht gezählt. Misst er
wirklich den Heizbetrieb, ist das richtig; liegt dort ein anderer Zähler (etwa der Kühlbetrieb), zeigt eedc unter Heizen
dessen Wert. Nur Heizen ist betroffen: Warmwasser hat keinen Betriebsart-Zähler, Kühlen keinen eigenen Summanden.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung dieser Wärmepumpe öffnet sich.
2. Prüfen, was der Sensor bei «Strom Heizbetrieb» misst. Misst er den Heizbetrieb, ist nichts zu tun.
3. Misst du Heizen und Warmwasser getrennt, bei «Strom Heizbetrieb» die Quelle «Keine» wählen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald nur noch einer der beiden
   Zähler zugeordnet ist.

**Was ohne Handlung gilt**
eedc zählt unter Heizen den Betriebsart-Zähler; der Wert von «Strom Heizen» bleibt unberücksichtigt.

#### Strom Heizen/Warmwasser zugeordnet, getrennte Messung aus <a name="wp_strom_zugeordnet_getrennte_messung_aus"></a>

**Was eedc sieht**
An der Wärmepumpe ist «Strom Heizen» oder «Strom Warmwasser» zugeordnet (Home-Assistant-Sensor oder MQTT), der Schalter
«Getrennte Strommessung (Heizen / Warmwasser)» an der Komponente ist aber aus. Diese Zähler zählt eedc nur mit Schalter
als Teile des Wärmepumpen-Stroms; ohne ihn rechnet es den Strom allein aus dem Gesamtzähler — Heizen und Warmwasser
bleiben leer, der ganze Strom steht unter „nicht aufgeteilt“. eedc schaltet nicht selbst um: der Schalter sagt, wie du
misst.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Schalter
   «Getrennte Strommessung (Heizen / Warmwasser)».
2. Den Schalter einschalten und speichern.
3. Nutzt du bewusst nur den Gesamtzähler, stattdessen in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei «Strom Heizen» und «Strom Warmwasser» die Quelle
   «Keine» wählen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Heizen und Warmwasser bleiben leer, der ganze Strom der Wärmepumpe steht unter „nicht aufgeteilt“.

#### PV-Zuordnung am Wechselrichter wird nicht ausgewertet <a name="wr_pv_zuordnung_nicht_ausgewertet"></a>

**Was eedc sieht**
Am Wechselrichter hängt ein PV-Zähler, oder dort ist ein PV-Monatswert von Hand gepflegt. Beides zählt nirgends mit:
eedc führt die PV-Erzeugung an den PV-Modulen und, für die ganze Anlage, in der Gruppe «Anlage (Basis)» der
Datenquellen. Solange die alte Zuordnung hängt, gilt die PV in der Zuordnung als abgedeckt, obwohl niemand den Sensor
liest — die Live-Anzeige rechnet dann aus der Leistung hoch und kann deutlich danebenliegen.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim PV-Feld des Wechselrichters.
2. Den Zähler dort zuordnen, wo eedc ihn liest: Misst du je String, beim jeweiligen PV-Modul. Hast du nur einen Zähler
   für die ganze Anlage, in der Gruppe «Anlage (Basis)» — eedc verteilt die Menge dann nach kWp auf deine Module.
3. Danach die alte Zuordnung am Wechselrichter entfernen (Quelle «Keine»); sie bleibt sichtbar, bis du sie löschst.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange am Wechselrichter eine Zuordnung oder
   ein gepflegter PV-Monatswert steht. Einen solchen Monatswert kannst du nicht mehr ändern oder entfernen: der
   Monatsabschluss zeigt das Feld am Wechselrichter nicht mehr, und der Daten-Checker bietet dafür kein «Wert entfernen».
   Steht er, bleibt die Zeile — er zählt trotzdem nirgends mit.

**Was ohne Handlung gilt**
Der Sensor am Wechselrichter und sein Monatswert zählen nirgends; die PV-Erzeugung kommt allein aus Modulen und
Anlagenzähler.

#### Gibt dieses Gerät Strom an Dritte ab? <a name="geraet_abgabe_an_dritte_frage"></a>

**Was eedc sieht**
Dieses Gerät unter Sonstiges ist als Erzeuger erfasst und trägt in einigen Monaten Einspeisung und Erlös, aber keine
Erzeugung über die Einspeisung hinaus — so sieht eine Abgabe an Dritte aus (Mieterstrom, Allgemeinstrom, Nachbarhaus).
Als Erzeuger zählt diese Energie zum Eigenverbrauch deines Hauses und hebt Autarkie und Eigenverbrauchsquote an. Eine
Frage, kein Urteil: eedc stellt nichts um.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Geräts öffnet sich beim Feld «Kategorie».
2. Sitzt ein Zähler an der Übergabestelle: «Abgabe an Dritte» wählen und speichern.
3. Den Zähler in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei diesem Gerät als «Abgabe»
   zuordnen — eedc zieht die Menge dann vom Eigenverbrauch ab. Der Erlös bleibt dein Feld.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Alte Monatswerte im Feld
   «Erzeugung» meldet der Daten-Checker danach eigens; dort gilt der Lösungsweg zu „Wert in einem Feld, das das Gerät
   nicht führt“.

**Was ohne Handlung gilt**
Das Gerät bleibt Erzeuger; seine Menge zählt zum Eigenverbrauch des Hauses.

#### Akku des Balkonkraftwerks nur als Monatswert erfasst <a name="akku_werte_nur_monatswert"></a>

**Was eedc sieht**
Lade- und Entlademengen stehen direkt am Balkonkraftwerk («Speicher Ladung», «Speicher Entladung»). In dieser Form gibt es
sie nur monatlich — im Live-Dashboard, im Tagesverlauf und im Energiefluss fehlt der Akku. Ein Akku mit allen Ansichten
ist eine eigene Komponente vom Typ Speicher, die zum Balkonkraftwerk gehört.

**Lösungsweg**
1. Unter *Einstellungen → Komponenten → Speicher* mit «+» einen Speicher anlegen, bei «Gehört zu» dieses
   Balkonkraftwerk wählen und speichern.
2. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich; die Lade- und Entladesensoren beim
   neuen Speicher zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald ein Speicher zu diesem
   Balkonkraftwerk gehört.

**Was ohne Handlung gilt**
Die gepflegten Monatswerte bleiben erhalten und werden weiter angezeigt; Live-Dashboard, Tagesverlauf und Energiefluss
zeigen den Akku nicht.

#### Keine aktiven Komponenten <a name="keine_aktiven_investitionen"></a>

**Was eedc sieht**
Die Anlage hat keine aktive Komponente. Cockpit, Wirtschaftlichkeit und alle Aufschlüsselungen nach Geräten bleiben leer.

**Lösungsweg**
1. Am Befund **«Komponente anlegen»** klicken — das Formular für neue PV-Module öffnet sich.
2. Mindestens PV-Module oder ein Balkonkraftwerk anlegen (Balkonkraftwerk unter
   *Einstellungen → Komponenten → Balkonkraftwerk* mit «+») und speichern. Gibt es die Komponente schon, aber nicht
   aktiv: sie bearbeiten, «Aktiv (in Berechnungen berücksichtigen)» einschalten und prüfen, ob das «Anschaffungsdatum»
   in der Zukunft oder das «Stilllegungsdatum (optional)» in der Vergangenheit liegt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc kennt keine Geräte der Anlage; Cockpit und Wirtschaftlichkeit zeigen nichts.

#### Leistung der PV-Module fehlt <a name="pv_leistung_kwp_fehlt"></a>

**Was eedc sieht**
Diesen PV-Modulen fehlt die Leistung in kWp. Ohne sie greift die Prüfung der Anlagenleistung gegen die Module nicht, die
Verteilung eines Gesamtwerts nach kWp kennt den Anteil dieser Module nicht, und das PVGIS-Soll je String fehlt.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der PV-Module öffnet sich beim Feld «Leistung (kWp)».
2. Die Leistung eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die kWp-Summe der Anlage ist unvollständig; Soll-Werte und Prognose je String fehlen für diese Module.

#### Ausrichtung oder Neigung der PV-Module fehlt <a name="pv_ausrichtung_fehlt"></a>

**Was eedc sieht**
Diesen PV-Modulen fehlt Ausrichtung oder Neigung. Beides braucht die PVGIS-Solarprognose je String.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der PV-Module öffnet sich beim Feld «Ausrichtung».
2. «Ausrichtung» und «Neigung (Grad)» eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Prognose rechnet für diese Module bei fehlender Ausrichtung mit Süd, bei fehlender Neigung mit 35°.

#### Leistung des Balkonkraftwerks fehlt <a name="bkw_leistung_wp_fehlt"></a>

**Was eedc sieht**
Dem Balkonkraftwerk fehlt die Leistung pro Modul in Wp. Ohne sie (mal Modulanzahl) ist die kWp-Summe der Anlage
unvollständig, solange dem Balkonkraftwerk keine PV-Module zugeordnet sind, und der kWp-Anteil des Balkonkraftwerks an
einem Gesamtwert lässt sich nicht bestimmen. Mit zugeordneten Modulen zählt deren Summe; der Hinweis bleibt trotzdem,
bis «Leistung pro Modul (Wp)» eingetragen ist.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Balkonkraftwerks öffnet sich beim Feld
   «Leistung pro Modul (Wp)».
2. «Leistung pro Modul (Wp)» und «Anzahl Module» eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Ohne zugeordnete PV-Module fehlt die kWp-Summe der Anlage um das Balkonkraftwerk; mit zugeordneten Modulen zählt deren
Summe.

#### Wechselrichter-Leistung des Balkonkraftwerks fehlt <a name="wr_leistung_fehlt"></a>

**Was eedc sieht**
Am Balkonkraftwerk fehlt die Leistung seines Wechselrichters, und die Module leisten zusammen mehr als 800 W (die
typische Einspeisegrenze; darunter meldet eedc nichts); die Meldung nennt die Leistung der Module. Ohne die
Wechselrichter-Leistung rechnet die Prognose mit der vollen Modulleistung — bei Überbelegung (etwa 1.260 W Module an
600 W Wechselrichter) fällt sie zu hoch aus. Mit gepflegtem Wert kappt eedc die Prognose stündlich.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Balkonkraftwerks öffnet sich beim Feld
   «Wechselrichter-Leistung (W)».
2. Die Ausgangsleistung des Wechselrichters in W eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Prognose des Balkonkraftwerks rechnet ungekappt mit der Modulleistung.

#### Kapazität des Speichers fehlt <a name="speicher_kapazitaet_fehlt"></a>

**Was eedc sieht**
Dem Speicher fehlt die Kapazität in kWh. Sie ist die Bezugsgröße der Vollzyklen; die Korrektur des Wirkungsgrads über
den Ladestand und der Ladestand in der Live-Anzeige nutzen die «Nutzbare Kapazität (kWh)» und greifen nur ohne sie auf
diese Kapazität zurück.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich beim Feld «Kapazität (kWh)».
2. Die Brutto-Kapazität in kWh eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Vollzyklen und die auf die Kapazität bezogenen Kennzahlen des Speichers rechnen nicht.

#### Arbitrage aktiv, Ø Ladepreis fehlt <a name="arbitrage_ladepreis_fehlt"></a>

**Was eedc sieht**
Am Speicher ist «Arbitrage-fähig» eingeschaltet, aber der erwartete Ø Ladepreis fehlt. Gemeint ist der Erwartungswert in
den Stammdaten des Speichers — aus ihm rechnen Prognose und Wirtschaftlichkeit in die Zukunft. Der gemessene Monatswert
«Ø Ladepreis» im Monatsabschluss und ein zugeordneter Preis-Sensor ersetzen ihn nicht: sie messen, was war, dieser
schätzt, was kommt.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich im Abschnitt
   «Netzladung & Arbitrage» beim Feld «Ø Ladepreis (ct/kWh)».
2. Den Preis eintragen, zu dem der Speicher im Niedrigtarif-Fenster lädt (etwa bei negativen Börsenpreisen), und
   speichern. Trag einen Wert über 0 ct/kWh ein: 0 zählt hier als nicht eingetragen, die Zeile bliebe stehen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet die Arbitrage mit 12 ct/kWh als Ladepreis.

#### Arbitrage aktiv, Ø Entladepreis fehlt <a name="arbitrage_entladepreis_fehlt"></a>

**Was eedc sieht**
Am Speicher ist «Arbitrage-fähig» eingeschaltet, aber der erwartete Ø Entladepreis fehlt — der Preis, den eine entladene
Kilowattstunde vermeidet. Gemeint ist der Erwartungswert in den Stammdaten des Speichers; aus ihm rechnen Prognose und
Wirtschaftlichkeit in die Zukunft. Gemessene Monatswerte ersetzen ihn nicht.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich im Abschnitt
   «Netzladung & Arbitrage» beim Feld «Ø Entladepreis (ct/kWh)».
2. Den vermiedenen Preis zur Spitzenlastzeit eintragen und speichern. Trag einen Wert über 0 ct/kWh ein: 0 zählt hier
   als nicht eingetragen, die Zeile bliebe stehen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet die Arbitrage mit 35 ct/kWh als Entladepreis.

#### Netzladung übersteigt die Gesamtladung <a name="speicher_netzladung_groesser_gesamt"></a>

**Was eedc sieht**
Über die ganze Geschichte des Speichers steht mehr Netzladung als Ladung. «Ladung» ist die gesamte Ladung (PV und Netz),
«Netzladung» ein Teil davon. In einem einzelnen Monat darf die Netzladung vorn liegen — ein Ladevorgang über die
Monatsgrenze landet beim einen Zähler noch im alten, beim anderen schon im neuen Monat —, in der Summe nicht. Mögliche
Ursachen: der Netz-Zähler ist bei «Ladung» zugeordnet, oder «Ladung» wurde als reine PV-Ladung gepflegt.

**Lösungsweg**
1. Am Befund **«Jahresbilanz prüfen»** klicken — die Speicher-Seite öffnet sich mit der Jahresbilanz dieses Speichers;
   dort siehst du, in welchen Jahren Ladung und Netzladung auseinanderlaufen.
2. In der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei diesem Speicher prüfen, dass bei «Ladung» der
   Zähler der gesamten Ladung liegt und bei «Netzladung» nur der Netz-Anteil.
3. Von Hand gepflegte Monate unter *Einstellungen → Daten → Monatsdaten* berichtigen: «Ladung» enthält die gesamte
   Ladung, die Netzladung ist ein Teil davon.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Summe der Netzladung
   die Summe der Ladung um höchstens 2 % plus 0,1 kWh übersteigt (Spielraum für einen Monatsübergang am Rand).

**Was ohne Handlung gilt**
Die Speicher-Auswertungen rechnen mit den widersprüchlichen Mengen; der PV-Anteil der Ladung stimmt nicht.

#### Entladung übersteigt die Ladung <a name="speicher_entladung_groesser_ladung"></a>

**Was eedc sieht**
Über die ganze Geschichte des Speichers steht mehr Entladung als Ladung — ein Wirkungsgrad über 100 %. Ein einzelner
Monat darf das (Energie aus dem Vormonat fließt ab), die Summe nicht: Ein Speicher kann nicht mehr abgeben, als er
aufgenommen hat; eine der beiden Größen ist falsch gemessen oder gepflegt. Häufigste Ursache bei einem Speicher mit
Netzladung: «Ladung» enthält nur die PV-Ladung — dort gehört die gesamte Ladung hinein, die Netzladung ist ein Teil
davon, kein zweiter Posten daneben.

**Lösungsweg**
1. Am Befund **«Jahresbilanz prüfen»** klicken — die Speicher-Seite öffnet sich mit der Jahresbilanz dieses Speichers;
   dort siehst du, in welchen Jahren die Entladung über der Ladung liegt.
2. In der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei diesem Speicher prüfen, welche Zähler bei
   «Ladung» und «Entladung» liegen.
3. Von Hand gepflegte Monate unter *Einstellungen → Daten → Monatsdaten* berichtigen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Summe der Entladung
   nicht mehr über der Summe der Ladung liegt.

**Was ohne Handlung gilt**
Die Speicher-Sichten zeigen für solche Zeiträume keinen Wirkungsgrad oder höchstens 100 %, und unter «Komponenten» steht
beim Speicher ein Warnhinweis; nur diese Zeile nennt den Überschuss als Zahl.

#### Fahrleistung oder Verbrauch des E-Autos fehlt <a name="eauto_fahrleistung_fehlt"></a>

**Was eedc sieht**
Am E-Auto ist weder die Jahresfahrleistung noch der Verbrauch je 100 km eingetragen. Ohne sie rechnet die Ersparnis
gegenüber einem Verbrenner mit Vorgaben statt mit deinen Angaben. Dienstwagen werden nicht geprüft.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des E-Autos öffnet sich beim Feld
   «Jahresfahrleistung (km)».
2. «Jahresfahrleistung (km)» und/oder «Verbrauch (kWh/100km)» eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Prognose der Ersparnis gegenüber einem Verbrenner rechnet mit den Vorgaben 15.000 km im Jahr und 18 kWh je 100 km
statt mit deinen Angaben.

#### Alternativkosten des E-Autos fehlen <a name="eauto_alternativkosten_fehlen"></a>

**Was eedc sieht**
Am E-Auto fehlen die Anschaffungskosten eines vergleichbaren Verbrenners. Ohne sie rechnet die Amortisation mit den
vollen Anschaffungskosten des E-Autos als Mehrkosten; die Ersparnis gegenüber dem Verbrenner rechnet eedc davon
unabhängig. Dienstwagen werden nicht geprüft.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des E-Autos öffnet sich beim Feld «Alternative Kosten (€)».
2. Die geschätzten Anschaffungskosten eines vergleichbaren Verbrenners eintragen und speichern. Gab es keine
   Verbrenner-Alternative, trag 0 ein — das ist eine gültige Antwort.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Amortisation des E-Autos rechnet mit den vollen Anschaffungskosten; die Ersparnis gegenüber dem Verbrenner wird
weiter gerechnet.

#### Ladeleistung der Wallbox fehlt <a name="wallbox_ladeleistung_fehlt"></a>

**Was eedc sieht**
An der Wallbox ist keine maximale Ladeleistung in kW eingetragen. eedc nennt sie bei der Wallbox, in der
Anlagendokumentation und im Community-Vergleich; keine Auswertung rechnet mit ihr.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wallbox öffnet sich beim Feld «Max. Ladeleistung (kW)».
2. Die Ladeleistung eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Anlagendokumentation lässt die Ladeleistung weg, der Community-Vergleich bekommt keine; alle Zahlen der
Auswertungen bleiben gleich.

#### Leistung des Wechselrichters fehlt <a name="geraet_leistung_kw_fehlt"></a>

**Was eedc sieht**
Am Wechselrichter ist keine AC-Nennleistung in kW eingetragen. Ohne sie begrenzt die Prognose die Module an diesem
Wechselrichter nicht auf seine Leistung, und die Prüfung der Modulleistung gegen den Wechselrichter entfällt.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Wechselrichters öffnet sich beim Feld
   «Max. Leistung (kW)».
2. Die AC-Nennleistung eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Prognose rechnet für die Module an diesem Wechselrichter mit ihrer vollen Leistung, die Prüfung der Modulleistung
gegen den Wechselrichter entfällt, und unter «Komponenten» steht am Wechselrichter keine kW-Angabe.

#### Alternativkosten der Wärmepumpe fehlen <a name="wp_alternativkosten_fehlen"></a>

**Was eedc sieht**
An der Wärmepumpe fehlt, was eine neue Gas- oder Ölheizung gekostet hätte. eedc zieht diesen Betrag von den
Anschaffungskosten ab — nur die Differenz muss sich amortisieren. Die Frage gilt für jede Wärmepumpe, auch im Neubau:
dort gab es keine Heizung zu ersetzen, aber vielleicht einen Gaskessel, den du sonst gekauft hättest.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Feld
   «Alternative Kosten (€)».
2. Die geschätzten Kosten einer vergleichbaren Gas- oder Ölheizung eintragen und speichern. Gab es keine Alternative,
   trag 0 ein — das ist eine gültige Antwort.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Amortisation rechnet mit den vollen Anschaffungskosten der Wärmepumpe.

#### Jahresarbeitszahl der Wärmepumpe fehlt <a name="wp_jaz_fehlt"></a>

**Was eedc sieht**
Als «Berechnungsmodus für Effizienz» ist die Jahresarbeitszahl gewählt, aber keine eingetragen. Ohne sie leitet eedc aus
dem gemessenen Heizstrom keine Heizwärme ab; die Prognose der Jahres-Einsparung rechnet ersatzweise mit 3,5.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Feld
   «Jahresarbeitszahl (JAZ)».
2. Die Jahresarbeitszahl eintragen (typisch 2,5–4,5 bei Luft-Wärmepumpen, 3,5–5,5 bei Sole-Wärmepumpen) und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Ohne gemessene Wärme bleibt die Heizwärme der Wärmepumpe leer; die Prognose der Jahres-Einsparung rechnet mit der
Vorgabe 3,5 statt mit deiner Jahresarbeitszahl.

#### Jahresarbeitszahl der Wärmepumpe unplausibel <a name="wp_jaz_unplausibel"></a>

**Was eedc sieht**
Die eingetragene Jahresarbeitszahl liegt außerhalb von 1,5 bis 7,0 — wahrscheinlich ein Eingabefehler, etwa Komma und
Punkt verwechselt oder ein Prozentwert statt eines Faktors. Typisch sind 2,5–4,5 bei Luft-Wärmepumpen und 3,5–5,5 bei
Sole-Wärmepumpen.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Feld
   «Jahresarbeitszahl (JAZ)».
2. Den Wert prüfen, berichtigen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet mit dem eingetragenen Wert; Heizenergie und Einsparung fallen entsprechend falsch aus.

#### SCOP- oder COP-Werte der Wärmepumpe fehlen <a name="wp_stammdatum_hinweis"></a>

**Was eedc sieht**
Als «Berechnungsmodus für Effizienz» ist SCOP (EU-Energielabel) oder getrennte COPs gewählt, aber ein Wert fehlt; die
Prognose der Jahres-Einsparung rechnet dann mit einer Vorgabe, und fehlt der Heizungs-Wert, leitet eedc aus dem
gemessenen Heizstrom keine Heizwärme ab. Gefragt wird nur nach Achsen, die es am Gerät gibt: An einer
Brauchwasser-Wärmepumpe heißt die Meldung „SCOP Warmwasser fehlt“ bzw. „COP Warmwasser fehlt“, an einer
Split-Klimaanlage umgekehrt „… Heizung fehlt“.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich.
2. Die genannten Werte vom EU-Label oder Datenblatt eintragen — «SCOP Heizung» / «SCOP Warmwasser» bzw.
   «COP Heizung» / «COP Warmwasser» — und speichern. Hat dein Gerät nur eine der beiden Achsen, genügt deren Wert.
   Alternativ den «Berechnungsmodus für Effizienz» auf die Jahresarbeitszahl stellen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Prognose der Jahres-Einsparung rechnet mit den Vorgaben SCOP 4,5 (Heizung) / 3,2 (Warmwasser) bzw. COP 3,9 / 3,0.
Fehlt der Heizungs-Wert, bleibt die Heizwärme der Wärmepumpe ohne gemessene Wärme leer.

#### Alter Energiepreis der Wärmepumpe fehlt <a name="wp_alter_energiepreis_fehlt"></a>

**Was eedc sieht**
An der Wärmepumpe ist ein ersetzter Energieträger gepflegt (Gas, Öl oder Strom-Direktheizung), aber kein Preis dafür. Den
braucht die Einsparungs-Rechnung gegenüber der ersetzten Heizung. Der Hinweis bleibt aus, wenn bei
«Alter Energieträger» die Option «Nichts ersetzt (Neubau)» gewählt ist — bei jeder Wärmepumpe, auch einer Klimaanlage.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich im Abschnitt
   «Vergleich mit alter Heizung (ROI)» beim Feld «Alter Preis (ct/kWh)».
2. Den aktuellen Gas- oder Ölpreis in ct/kWh eintragen und speichern. Hat die Wärmepumpe nichts ersetzt, stattdessen
   «Nichts ersetzt (Neubau)» wählen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Einsparung gegenüber der alten Heizung rechnet mit einem Standardpreis statt mit deinem.

#### Heizwärmebedarf der Wärmepumpe fehlt <a name="wp_heizwaermebedarf_fehlt"></a>

**Was eedc sieht**
An der Wärmepumpe ist kein Jahres-Heizwärmebedarf eingetragen. Ist auch kein «Warmwasserbedarf (kWh/Jahr)» gepflegt,
rechnet die Jahres-Einsparungsschätzung gar nicht; die Zeile der Wirtschaftlichkeit trägt dann „Nicht bewertet“ samt
Begründung. Mit gepflegtem Warmwasserbedarf rechnet sie allein aus diesem und fällt zu niedrig aus. Gefragt wird nur an
Geräten mit Heiz-Achse — eine Split-Klimaanlage behält die Frage, weil viele mit ihr heizen. Der Hinweis bleibt aus,
wenn bei «Alter Energieträger» «Nichts ersetzt (Neubau)» gewählt ist.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Feld
   «Heizwärmebedarf (kWh/Jahr)».
2. Den geschätzten Jahresbedarf eintragen (etwa aus dem Energieausweis) und speichern. Heizt du mit einer Klimaanlage
   nicht, stattdessen «Nichts ersetzt (Neubau)» wählen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Jahres-Einsparung der Wärmepumpe bleibt „Nicht bewertet“, solange auch kein Warmwasserbedarf gepflegt ist; sonst
rechnet sie allein aus dem Warmwasserbedarf.

#### Warmwasserbedarf der Wärmepumpe fehlt <a name="wp_warmwasserbedarf_fehlt"></a>

**Was eedc sieht**
An einem Gerät ohne Heiz-Achse — einer Brauchwasser-Wärmepumpe — fragt eedc nicht nach dem Heizwärmebedarf, sondern nach
dem Jahres-Warmwasserbedarf; er versorgt dieselbe Jahres-Einsparungsschätzung. Es bleibt bei einem Hinweis je Gerät.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Feld
   «Warmwasserbedarf (kWh/Jahr)».
2. Den geschätzten Jahresbedarf eintragen (rund 500 kWh je Person und Jahr) und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Jahres-Einsparung der Wärmepumpe bleibt ungerechnet.

#### Anschaffungsdatum fehlt <a name="anschaffungsdatum_fehlt"></a>

**Was eedc sieht**
Der Komponente fehlt das Anschaffungsdatum. Es ist die Grenze jeder Auswertung — ohne es zählt die Komponente auch für
Zeiträume vor der Anschaffung mit — und der Startpunkt der Amortisation. Neue Komponenten verlangen das Datum; der
Befund betrifft ältere Einträge.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular dieser Komponente öffnet sich beim Feld «Anschaffungsdatum».
2. Das Datum eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Komponente zählt in allen Zeiträumen mit, auch vor ihrer Anschaffung; die Amortisation hat keinen Startpunkt.

#### Anschaffungskosten fehlen <a name="anschaffungskosten_fehlen"></a>

**Was eedc sieht**
Der Komponente fehlen die Anschaffungskosten. Wirtschaftlichkeit und Amortisation rechnen ohne sie mit 0 €.
Verbrauchszähler (Sonstiges mit der Kategorie «Verbrauchszähler (Gas, Wasser, Heizöl — wird nur erfasst)») sind
ausgenommen — sie werden erfasst, nicht bewertet.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular dieser Komponente öffnet sich beim Feld
   «Anschaffungskosten (€)».
2. Die Brutto-Anschaffungskosten eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Die Komponente geht mit 0 € in Wirtschaftlichkeit und Amortisation ein.

#### 4.3.1 PV-Module

Je PV-Modul (String) prüft eedc Leistung in kWp und Ausrichtung/Neigung. Die PV-Erzeugung prüft eedc **anlagenweit**:
ein einzelner Gesamtwert der Anlage deckt alle Strings ab — er füllt die Lücken der Module ohne eigenen Wert, verteilt
nach kWp. Je Monat gibt es deshalb vier Zustände: jedes Modul gemessen (vollständig), Gesamtwert verteilt (geschätzt,
kein Mangel), nur ein Teil der Strings und kein Gesamtwert (unvollständig), gar keine PV-Quelle (fehlt).

**Nicht die Reparatur-Werkbank dafür nehmen.** «Tag neu aggregieren» und «Mehrere Tage neu aggregieren» bauen das
stündliche Energieprofil neu — sie schreiben weder den Gesamtwert noch die Monatswerte je Modul. Fehlende
Monatswerte füllen der Statistik-Import (*Einstellungen → Integration → Statistik-Import*) und der Monatsabschluss.

#### 4.3.2 Balkonkraftwerk

Am Balkonkraftwerk prüft eedc die Leistung pro Modul (Wp), die Leistung des Wechselrichters (für die
Prognose) und die monatliche Erzeugung. Ein Balkonkraftwerk ohne eigenen Zähler bekommt seinen kWp-Anteil am
PV-Gesamtwert der Anlage; ein Monat mit gespeichertem Gesamtwert gilt deshalb nicht als Lücke. Ein Balkonkraftwerk mit
zugeordneten PV-Modulen ist selbst ein Gesamtwert für seine Module. Ein Akku am Balkonkraftwerk gehört als eigene
Komponente vom Typ Speicher dazu (Feld «Gehört zu»); Akku-Werte direkt am Balkonkraftwerk gibt es nur monatlich.

#### 4.3.3 Speicher

Am Speicher prüft eedc die Kapazität, bei eingeschalteter Arbitrage die beiden erwarteten Preise, die monatliche Ladung
und — über die ganze Geschichte — ob Netzladung und Entladung zur Ladung passen. «Ladung» ist immer die gesamte Ladung
(PV und Netz), «Netzladung» ein Teil davon.

**Warum eedc für Arbitrage eine Angabe braucht:** Arbitrage lebt davon, dass dieselbe Kilowattstunde zu verschiedenen
Uhrzeiten verschieden viel kostet — und ein eedc-Tarif kennt keine Uhrzeit. Die beiden Preisfelder «Ø Ladepreis» und
«Ø Entladepreis» stehen im Formular des Speichers unter «Netzladung & Arbitrage», sobald «Arbitrage-fähig» an ist. Wer
einen dynamischen Tarif (Tibber, aWATTar, EPEX) angebunden hat: dort zieht eedc für die gemessenen Monate den
stundengenauen Preis vor; Prognose und Amortisation rechnen weiter mit den beiden Preisen am Speicher, deshalb fragt der
Checker sie trotzdem.

#### 4.3.4 E-Auto (privat)

Am E-Auto prüft eedc Fahrleistung bzw. Verbrauch und die Alternativkosten eines Verbrenners, ohne Wallbox außerdem die
monatliche PV-Ladung. Dienstwagen werden übersprungen — kein PV-Bezug, kein Vergleich mit einem Verbrenner. Mit
Wallbox trägt sie die Heimladung; eine Messung am E-Auto ist dann freiwillig (sie zählt für dieses Auto, die Wallbox
trägt den Rest), und nach der PV-Ladung des Autos wird nicht gefragt.

#### 4.3.5 Wallbox

An der Wallbox prüft eedc die maximale Ladeleistung und die monatliche Gesamtladung.

#### 4.3.6 Wechselrichter

Am Wechselrichter prüft eedc die AC-Nennleistung. Er ist kein PV-Erzeuger: eedc führt die PV-Erzeugung an den PV-Modulen
und, für die ganze Anlage, in der Gruppe «Anlage (Basis)» der Datenquellen. Eine alte PV-Zuordnung oder ein PV-Monatswert
am Wechselrichter wird gemeldet, weil er nirgends mitzählt.

#### 4.3.7 Wärmepumpe

An der Wärmepumpe prüft eedc die Angaben für Effizienz und Wirtschaftlichkeit (Jahresarbeitszahl bzw. SCOP/COP,
Alternativkosten, alter Energiepreis, Wärmebedarf), die Zuordnung der Stromzähler und je Monat Strom und Wärme samt
ihren Widersprüchen.

**Gefragt wird nur nach Größen, die eedc an deinem Gerät erwartet.** Die Wärmepumpenart darf dabei vorschlagen: Bei
**Luft-Luft (Klimaanlage)** ist die Heizwärme optional statt Pflicht, einen Warmwasserkreis gibt es nicht — bei
getrennter Strommessung wird nur «Strom Heizen» erwartet. Bei einer **Brauchwasser-Wärmepumpe** ist die Heizseite
zurückgestuft: gefragt wird nach Warmwasser, nicht nach Heizwärme oder Heizstrom. Der Stromverbrauch bleibt überall
Pflicht; Arbeitszahl und COP zeigen ohne Wärme „—“ mit Grund statt einer Scheinzahl. Eine Wärmepumpe ohne eingetragene
Art gilt als klassische Wärmepumpe. Wer an seiner Klimaanlage doch einen Wärmemengenzähler hat, ordnet ihn weiter zu.

**Die Hinweise zum Vergleich mit Gas/Öl hängen an der Pflege, nicht an der Bauart.** „Alter Energiepreis nicht gesetzt“ und
„Heizwärmebedarf nicht gesetzt“ versorgen die Ersparnis gegenüber einer **ersetzten Heizung**; sie bleiben aus, sobald im Abschnitt
«Vergleich mit alter Heizung (ROI)» bei «Alter Energieträger» die Option «Nichts ersetzt (Neubau)» gewählt ist — bei
jeder Wärmepumpe. Heizt du mit einer Klimaanlage, wähle den ersetzten Energieträger; dann wird die Wirtschaftlichkeit wie
bei jeder anderen Wärmepumpe gerechnet. Nach dem Heizwärmebedarf fragt eedc nur an Geräten mit Heiz-Achse; an einer
Brauchwasser-Wärmepumpe tritt der Warmwasserbedarf an seine Stelle. Dieselbe Achsen-Regel gilt für die SCOP- und
COP-Werte. Die **Alternativkosten** sind eine dritte Frage und gelten für jede Wärmepumpe: Was hättest du stattdessen
kaufen müssen? Gab es keine Alternative, ist 0 eine gültige Antwort.

#### 4.3.8 Allgemein (alle Komponententypen)

Für jede Komponente außer einem Dienstwagen prüft eedc das Anschaffungsdatum — es begrenzt jede Auswertung und ist der
Startpunkt der Amortisation —, die Anschaffungskosten für jede außer einem Verbrauchszähler, sowie die Vollständigkeit ihrer Pflicht-Monatsfelder ab dem Anschaffungsdatum. Ohne
aktive Komponente bleiben Cockpit und Wirtschaftlichkeit leer.

#### 4.3.9 E-Auto + Wallbox – Heimladung je Auto <a name="439-heimladung-je-auto"></a>

Greift nur, wenn eine **private Wallbox** existiert. Die Wallbox ist die **Summe** aller Ladungen an ihr; ein Auto mit
eigener Messung («Heim: PV», «Heim: Netz», «Heim: gesamt», auch 0) trägt diese, der Rest der Wallbox geht an die privaten
Autos ohne eigene Messung ([Bedienung §3.5](HANDBUCH_BEDIENUNG.md#35-e-auto)). Dass Wallbox **und** Auto Heimladung
tragen, ist damit der Normalfall und wird nicht gemeldet. Geprüft wird das Fenster der letzten 12 Monate; mit einem
Ladezähler je Auto vergleicht der Checker die Summe seiner Ladevorgänge im Monat — ein Ladevorgang über den Monatswechsel
löst deshalb keinen Befund aus.

---

##### Autos haben mehr zu Hause geladen, als die Wallbox gemessen hat <a name="emob_autos_mehr_als_wallbox"></a>

**Was eedc sieht**
In den genannten Monaten der letzten zwölf übersteigen die eigenen Heimlade-Werte der Autos (privat und dienstlich)
die Ladung der Wallbox um mehr als 10 kWh und zugleich mehr als 10 % (die größere der beiden Grenzen). Mögliche
Ursachen: Streudaten am Auto, eine Quelle am Auto, die auch das Laden unterwegs zählt, oder ein Auto, das an der
Steckdose statt an der Wallbox geladen hat. Der Rest der Wallbox, der sonst an Autos ohne eigene Messung geht, ist in
diesen Monaten 0.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten genannten Monats öffnet sich am Feld
   «Heim: gesamt» des Autos.
2. Die Heimlade-Werte der Autos («Heim: PV», «Heim: Netz», «Heim: gesamt») mit der Ladung der Wallbox vergleichen und
   den falschen Wert korrigieren; dasselbe für die übrigen genannten Monate.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Hat ein Auto wirklich an der
   Steckdose geladen, stimmen die Werte, und die Zeile bleibt für diese Monate stehen.

**Was ohne Handlung gilt**
eedc rechnet mit den erfassten Werten weiter; Autos ohne eigene Messung bekommen in diesen Monaten keine Heimladung
zugeteilt.

##### Heimladung am Dienstwagen fehlt <a name="emob_dienstwagen_heimladung_fehlt"></a>

**Was eedc sieht**
Die private Wallbox hat geladen und der Dienstwagen ist gefahren, aber am Dienstwagen ist keine Heimladung erfasst (und
es gibt keine dienstliche Wallbox in Betrieb). Lädt er zu Hause, zählt seine Ladung sonst zugleich privat und
dienstlich.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ältesten betroffenen Monats öffnet sich am
   Feld «Heim: gesamt» des Dienstwagens; die Details nennen höchstens die drei jüngsten Monate.
2. Seine Heimladung eintragen («Heim: gesamt» oder «Heim: PV» und «Heim: Netz»). Lädt er nur beim Arbeitgeber,
   **0** eintragen — 0 ist ein Wert. Dasselbe für die übrigen genannten Monate.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Der Rest der Wallbox geht an die privaten Autos ohne eigene Messung; lädt der Dienstwagen zu Hause, ist deren Ladung zu
hoch.

##### Gleicher Sensor an Wallbox und E-Auto <a name="emob_gleicher_sensor_wallbox_eauto"></a>

**Was eedc sieht**
Derselbe Sensor ist der Wallbox und dem E-Auto zugeordnet; die Zeile nennt Sensor und Geräte. Beide messen damit
denselben Ladestrom. In Monat und Jahr zählt eedc die Ladung einmal (das E-Auto trägt seine Messung, für die Wallbox
bleibt kein Rest) — die Zuordnung ist trotzdem falsch.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim E-Auto am Feld der Ladung.
2. Die Zuordnung an einem der beiden Geräte lösen. Faustregel: Die Wallbox misst den Stromfluss, das E-Auto trägt
   Nutzung und Kilometer — meist bleibt der Sensor an der Wallbox.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Ein weiteres Auto ohne eigene Messung bekommt von dieser Wallbox keine Heimladung, und die Sichten je Gerät zeigen
denselben Ladestrom an Wallbox und E-Auto.

### 4.4 Monatsdaten – Vollständigkeit <a name="44-monatsdaten--vollstaendigkeit"></a>

**Was wird geprüft:** Welche Monate zwischen der **Inbetriebnahme der Anlage** und dem Vormonat sind erfasst? Ist keine
Inbetriebnahme gepflegt, gilt das älteste Anschaffungsdatum deiner **Erzeuger** (PV-Module, Balkonkraftwerk), zuletzt der
erste vorhandene Monat. ⚠ Andere Komponenten ziehen den Bereich **nicht** zurück: Ein E-Auto von 2017 an einer Anlage von
2022 fordert keine Zählerwerte ab 2017 — eine Monatszeile ist eine Aussage über die Anlage, nicht über ein einzelnes
Gerät. Ob eine Komponente in einem Monat *mitrechnet*, entscheidet weiterhin ihr eigenes Anschaffungs- bzw.
Stilllegungsdatum. Der laufende Monat wird ausgeklammert, weil er noch nicht abgeschlossen ist. Das Ergebnis fließt
zusätzlich in den Fortschrittsbalken «Monatsdaten-Abdeckung» oben ein.

> **Warum ein fehlender Monat ein Fehler ist und keine Warnung.** Einspeisung und Netzbezug sind die Basis, auf der eedc
> überhaupt eine Bilanz bildet. Ohne sie weiß eedc nicht, woher der Strom eines Geräts kam — **und rechnet trotzdem**:
> Der Direktverbrauch entsteht als *Erzeugung minus Einspeisung minus Speicherladung*, und eine fehlende Einspeisung
> liest diese Rechnung als **0**. Dann gilt die ganze Erzeugung als Eigenverbrauch und wird mit dem **Netzpreis** statt
> der Einspeisevergütung bewertet. An einem echten Monat nachgerechnet: **622 € statt 282 €**, bei einem Gesamtverbrauch
> von 1.838 statt 520 kWh. Die Zahl wäre also nicht ungenau, sondern systematisch zu gut — deshalb ist eine Lücke hier
> kein Schönheitsfehler.
>
> **Hinweis zur Abdeckung:** Der Prozentwert oben bezieht sich auf erwartete Monate, nicht auf Datenfelder *innerhalb*
> eines Monats. Ein zu 100 % abgedeckter Stand kann trotzdem unvollständige Pflichtfelder enthalten — das prüft §4.5.

---

#### Keine Monatsdaten vorhanden <a name="keine_monatsdaten"></a>

**Was eedc sieht**
Es gibt keinen einzigen Monat mit Einspeisung und Netzbezug. Cockpit, Aussicht, Amortisation und Community-Vergleich
bleiben leer.

**Lösungsweg**
1. Am Befund **«Monat erfassen»** klicken — der Monatsabschluss des ersten Monats ab der «Inbetriebnahme (Anlage)»
   öffnet sich; ohne dieses Datum der Monat des ältesten Anschaffungsdatums eines PV-Moduls oder Balkonkraftwerks, sonst
   die Monatsdaten-Liste.
2. Einspeisung und Netzbezug eintragen (auch 0 ist ein Wert) und speichern. Mit zugeordneten Zählern in Home Assistant
   holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) viele Monate
   auf einmal; vorhandene Daten liest unter [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)
   **«CSV importieren»** ein.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; fehlen noch Monate, nennt der
   Daten-Checker sie einzeln.

**Was ohne Handlung gilt**
Ohne Monate gibt es keine Bilanz, keine Jahreswerte und keinen Vergleich; eedc schätzt nichts.

#### Alle Monate vollständig <a name="monate_vollstaendig_ok"></a>

**Was eedc sieht**
Von der Inbetriebnahme der Anlage (ohne sie: ab dem ältesten Anschaffungsdatum eines PV-Moduls oder Balkonkraftwerks,
sonst ab dem ersten erfassten Monat) bis zum Vormonat ist jeder Monat erfasst; die Zeile nennt ihre Zahl. Ob die Felder
innerhalb der Monate vollständig sind, prüft die Plausibilität der Monatsdaten.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange kein Monat fehlt.

**Was ohne Handlung gilt**
Jahreswerte, Amortisation und Community-Vergleich rechnen mit allen Monaten.

#### Monat fehlt <a name="monat_fehlt"></a>

**Was eedc sieht**
Für einen abgeschlossenen Monat ab der Inbetriebnahme (ohne sie: ab dem ältesten Anschaffungsdatum eines PV-Moduls oder
Balkonkraftwerks, sonst ab dem ersten erfassten Monat) gibt es keinen Monatsabschluss — Einspeisung und Netzbezug fehlen.
Ohne sie gibt es keine Bilanz: eedc kann nicht sagen, woher der Strom eines Geräts kam, und rechnet den Monat weder in den
Jahreswert noch in den Community-Vergleich. Mehrere fehlende Monate stehen als eine Zeile «n Monate fehlen» mit einem
Glied je Monat; über zwölf hinaus nennt die Zeile die Zahl der weiteren.

**Lösungsweg**
1. Am Befund ein Glied (den Monat) oder **«Monat erfassen»** klicken — der Monatsabschluss dieses Monats öffnet sich.
2. Einspeisung und Netzbezug eintragen (auch 0 ist ein Wert) und speichern. Mit zugeordneten Zählern in Home Assistant
   holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere Monate
   auf einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Der Monat bleibt leer: Jahreswerte, Amortisation und Community-Vergleich rechnen ohne ihn und sind entsprechend
unvollständig. eedc setzt keine 0 und schätzt nichts.

### 4.4a Monatsdaten – Messwerte ohne Monatszeile <a name="44a-messwerte-ohne-monatszeile"></a>

**Was wird geprüft:** Gibt es Messwerte einzelner Komponenten (PV je Modul, Speicher-Zyklen, Wallbox-Ladung …) für einen
Monat, der selbst nicht erfasst ist?

Ein Monat besteht in eedc aus zwei Teilen: der **Zählerzeile** der Anlage (Einspeisung, Netzbezug …) und den
**Messwerten je Komponente** daneben. Fehlt die Zählerzeile, fehlt der Monat in allen Listen — die Messwerte der
Komponenten wirken aber weiter und weisen einen erneuten Import dieses Monats ab.

> **Vorbeugen:** Der Lösch-Dialog unter *Einstellungen → Daten → Monatsdaten* nennt, wie viele Komponenten-Messwerte an
> einem Monat hängen, und löscht sie zusammen mit der Zählerzeile; hängt ein Zählerstand daran, warnt er davor.

---

#### Messwerte ohne Monatszeile <a name="geraetewerte_ohne_monatszeile"></a>

**Was eedc sieht**
Für den Monat liegen Messwerte einzelner Geräte vor (die Zeile nennt sie), aber keine Zählerzeile mit Einspeisung und
Netzbezug. Die Werte zählen in Cockpit und Auswertungen mit, der Monat erscheint aber in keiner Monatsliste, fehlt in
Autarkie und Community-Vergleich und weist einen erneuten Import ab. Der Zustand entsteht auf mehreren Wegen
(Statistik-Import ohne Zähler-Sensoren, Cloud-Import ohne Smartmeter, ein früher gelöschter Monat); nachträglich sind
sie nicht zu unterscheiden.

Nennt der Befund einen Zählerstand (Gas, Wasser, Öl — Sonstiges der Kategorie Zähler), ist Nachtragen der einzige
unschädliche Weg: Ein Stand ist kein Monatswert, sondern der Anfangswert des Folgemonats. Entfernst du ihn, rechnet der
nächste Monat gegen den vorletzten Stand und weist zwei Monate als einen aus — ohne Hinweis.

**Lösungsweg**
1. Am Befund **«Monat erfassen»** klicken — der Monatsabschluss dieses Monats öffnet sich.
2. Einspeisung und Netzbezug eintragen und speichern — die Messwerte gehören dann wieder dazu. Das ist der Regelfall.
3. Nur wenn die Werte wirklich weg sollen: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die Operation «Messwerte ohne
   Monatszeile entfernen» wählen, den Monat wählen, **«Plan erstellen»**, die Vorschau lesen und anwenden — das ist
   endgültig.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Liste verschwunden.

**Was ohne Handlung gilt**
Die Gerätewerte rechnen weiter mit, der Monat bleibt aber ohne Bilanz und unsichtbar, und ein Import dieses Monats wird
abgewiesen.

### 4.5 Monatsdaten – Plausibilität <a name="45-monatsdaten--plausibilitaet"></a>

**Was wird geprüft:** Für jeden erfassten Monat die Pflichtfelder (Einspeisung, Netzbezug, bei einem Speicher Ladung und
Entladung), die Wertebereiche, die logische Konsistenz der Energiebilanz und — sobald vorhanden — der Vergleich mit dem
Vorjahresmonat und mit der PVGIS-Prognose. Dazu kommen zwei Prüfungen an Geräten: die PV-Ladung einer Wallbox oder eines
E-Autos gegen ihre Gesamtladung und die Arbeitszahl einer Wärmepumpe.

**Die PV-Obergrenze** passt sich an die Anlage an: Mit mindestens sechs Monaten Historie ohne Lücken gilt PVGIS-Soll ×
Performance Ratio × 1,45 — eine systematisch über PVGIS produzierende Anlage (PR über 1,0) bekommt einen entsprechend
höheren Schwellwert. Mindestschwelle ist immer PVGIS × 1,5; ohne PVGIS-Wert gilt ein festes Maximum nach Monat und kWp.
Der Faktor 1,45 deckt die natürliche Schwankung von Monat zu Monat ab.

**Der Knopf «Monat öffnen»** an diesen Befunden öffnet den betroffenen Monat unter *Einstellungen → Daten → Monatsdaten*
zum Bearbeiten («Monatsdaten bearbeiten»), beim genannten Feld bzw. Gerät; nur ein Monat ohne Monatsabschluss öffnet sich
als «Monatsdaten erfassen». **Ein leeres Feld ist keine 0:** eedc rechnet nur mit Werten, die jemand geliefert hat.

---

#### PV-Ladung größer als Gesamtladung <a name="emob_pv_ladung_groesser_gesamt"></a>

**Was eedc sieht**
An einer Wallbox oder einem E-Auto ist für den Monat die aus PV geladene Menge um mehr als 0,1 kWh größer als die
gesamte Ladung. Die PV-Ladung ist ein Teil der Gesamtladung und kann nicht größer sein. eedc rechnet in dieser Lage mit
PV + Netz weiter und legt den eingetragenen Gesamtwert beiseite — die Ladung, die du siehst, ist dann nicht die, die du
erfasst hast. Welcher der beiden Werte stimmt, kann eedc nicht wissen.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss dieses Monats öffnet sich beim genannten Gerät.
2. Beide Werte prüfen und berichtigen: an der Wallbox «Ladung gesamt» und «Ladung PV», am E-Auto «Heim: gesamt» und
   «Heim: PV». Häufige Ursachen: ein Import hat nur eines der beiden Felder aktualisiert, oder Gesamt- und PV-Wert stammen
   aus zwei verschiedenen Quellen (Wallbox-Sicht gegen Fahrzeug-Sicht). Speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc zeigt als Ladung PV + Netz (ohne eingetragenen Netz-Anteil also den PV-Wert); stimmt der PV-Wert nicht, ist auch
die gezeigte Ladung falsch. Der eingetragene Gesamtwert bleibt beiseitegelegt, bis einer der beiden Werte berichtigt ist.

#### Keine Auffälligkeiten in den Monatsdaten <a name="monatsdaten_plausi_ok"></a>

**Was eedc sieht**
Alle vorhandenen Monate haben ihre Pflichtfelder, plausible Werte und eine stimmige Energiebilanz.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange neue Monate ebenso stimmen.

**Was ohne Handlung gilt**
Die Monatsauswertungen rechnen mit den erfassten Werten.

#### Einspeisung oder Netzbezug nicht erfasst <a name="md_feld_nicht_erfasst"></a>

**Was eedc sieht**
Für den Monat steht kein erfasster Wert für Einspeisung bzw. Netzbezug — auch 0 ist ein Wert, aber nur, wenn ihn jemand
geliefert hat (typisch nach einem Import, der nur Wallbox- oder PV-Werte enthielt). Ohne ihn lassen Übersicht,
Jahresbericht, HA-Sensoren, die Tabelle der Auswertungen und die Finanz-Aussicht den Monat aus Eigenverbrauch, Autarkie,
Ersparnis und CO₂ heraus (seine PV-Erzeugung zählen sie weiter), und der Community-Upload teilt ihn nicht. Die
Monatsansicht im Cockpit nimmt den Wert aus der HA-Statistik, sofern ein Zähler zugeordnet ist. Steht dahinter
„(Monat ohne Monatsabschluss)“, gibt es für den Monat keinen Monatsabschluss, und an keinem seiner Tage hat ein Zähler
das Feld gemessen — typisch bei einem Balkonkraftwerk ohne Einspeisungs- oder Netz-Zähler.

**Lösungsweg**
1. Zuerst den Wert aus Home Assistant holen, wenn ein Zähler zugeordnet ist: im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) diesen Monat importieren — ohne
   „Überschreiben“ genügt, solange der Monat so gemeldet ist.
2. Sonst am Befund **«Monat öffnen»** klicken — der Monat öffnet sich zum Bearbeiten («Monatsdaten bearbeiten», für einen
   Monat ohne Monatsabschluss «Monatsdaten erfassen»). Den gemessenen Wert eintragen und speichern. Das Feld steht leer,
   nicht mit 0 — ein leeres Feld ist keine 0; steht schon ein Vorschlag darin, ihn prüfen und speichern.
3. Für einen Monat ohne Monatsabschluss gibt es auch den Weg über die
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen): den Zähler zuordnen. Er zählt ab dann; frühere Tage bleiben
   ohne Wert.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc rechnet das Feld nicht als 0. Eigenverbrauch, Autarkie und Ersparnis des Monats bleiben in der Monats- und der
Jahresansicht im Cockpit leer („–“), sofern die HA-Statistik den Wert nicht liefert; die PV-Erzeugung bleibt.

#### Batterie-Ladung nicht erfasst <a name="md_batterie_ladung_fehlt"></a>

**Was eedc sieht**
Eine aktive Speicher-Komponente ist vorhanden, aber für den Monat ist keine Batterie-Ladung erfasst. Ohne Batterie-Daten
wird der Gesamtverbrauch des Monats falsch berechnet.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich zum Bearbeiten, beim Speicher am Feld «Ladung».
2. Beim Speicher «Ladung» und «Entladung» eintragen und speichern — die Ladung allein löst den Folgebefund «Entladung
   an einem Speicher nicht erfasst» aus.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Der Gesamtverbrauch des Monats rechnet ohne die Ladung und steht damit zu hoch.

#### Batterie-Entladung nicht erfasst <a name="md_batterie_entladung_fehlt"></a>

**Was eedc sieht**
Eine aktive Speicher-Komponente ist vorhanden, aber für den Monat ist keine Batterie-Entladung erfasst. Ohne
Batterie-Daten wird der Gesamtverbrauch des Monats falsch berechnet.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich zum Bearbeiten, beim Speicher am Feld «Entladung».
2. Beim Speicher das Feld «Entladung» eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Der Gesamtverbrauch des Monats rechnet ohne die Entladung und steht damit falsch.

#### Entladung an einem Speicher nicht erfasst <a name="md_geraet_entladung_fehlt"></a>

**Was eedc sieht**
Für den genannten Speicher steht im Monat eine Ladung, aber keine Entladung. Ohne Entladung gibt es keinen gemessenen
Wirkungsgrad und keine Speicher-Ersparnis — der HA-Sensor meldet dann `wirkungsgrad_messung: keine-entladung`. Eine
erfasste 0 ist ein Wert: ein Monat, in dem der Speicher nichts abgegeben hat, wird nicht gemeldet.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim genannten Speicher.
2. Im Feld «Entladung» den gemessenen Wert eintragen (auch 0, wenn der Speicher nichts abgegeben hat) und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Für diesen Speicher und Monat gibt es keinen gemessenen Wirkungsgrad und keine Speicher-Ersparnis.

#### Energiemenge im Monat negativ <a name="md_feld_negativ"></a>

**Was eedc sieht**
Einspeisung, Netzbezug, PV-Erzeugung oder ein Batteriewert ist für den Monat kleiner als 0. Energiemengen können nicht
negativ sein — meist ein Vorzeichen- oder Eingabefehler, seltener ein gesunkener Zählerstand in der Quelle.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim genannten Feld.
2. Den Wert berichtigen und speichern. Kam er aus Home Assistant, dort die Zählerstände prüfen: ein gefallener Stand
   meldet der Daten-Checker auch als «Zählerstände – Rückgang in Home Assistant».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc rechnet mit dem negativen Wert; Bilanz, Eigenverbrauch und alles, was daraus folgt, stehen für den Monat falsch.

#### PV-Erzeugung ungewöhnlich hoch <a name="md_pv_ungewoehnlich_hoch"></a>

**Was eedc sieht**
Die PV-Erzeugung des Monats liegt über der Obergrenze. Liegt eine PVGIS-Prognose vor, ist das
PVGIS × Performance Ratio × 1,45 (ab sechs Monaten Historie), mindestens aber PVGIS × 1,5; ohne PVGIS-Prognose gilt ein
festes Maximum je Monat und kWp. Die Details nennen die verwendete Schwelle. Häufigste echte Ursache ist eine
Doppelerfassung: dieselbe Erzeugung an zwei Stellen zugeordnet.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich bei der PV-Erzeugung. Wert prüfen: Eingabefehler,
   falscher Faktor (etwa Wh statt kWh)?
2. Stimmt der Monatswert, die Zuordnung prüfen: steht dieselbe Erzeugung an zwei Stellen (Anlagenzähler und Modul, oder
   zwei Module mit demselben Sensor)? Das meldet auch die Prüfung «PV – Doppelerfassungs-Verdacht».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach einer Berichtigung ist der Monat aus der Zeile
   verschwunden. War es ein strahlungsreicher Monat, bleibt der Hinweis als Auskunft stehen und sagt, mit welcher Zahl
   eedc rechnet.

**Was ohne Handlung gilt**
eedc rechnet mit dem erfassten Wert — Ersparnis, Autarkie und Vergleiche des Monats folgen ihm.

#### Einspeisung und Netzbezug sind beide 0 <a name="md_einspeisung_netzbezug_null"></a>

**Was eedc sieht**
Beide Kernfelder sind für den Monat als 0 erfasst (eingetragen oder importiert). In den allermeisten Fällen fehlen dann
schlicht die Zählerwerte — ein echter Null-Verbrauch ist selten.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich bei der Einspeisung.
2. Einspeisung und Netzbezug eintragen und speichern.
3. Sind beide Werte bei dir tatsächlich 0 — die Anlage hat keinen Netzanschluss (Inselbetrieb), oder sie war den ganzen
   Monat außer Betrieb —, dann ist 0 richtig und nichts zu tun.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach dem Eintragen ist der Monat aus der Zeile verschwunden; mit
   echten Nullen bleibt der Hinweis als Auskunft stehen.

**Was ohne Handlung gilt**
eedc rechnet für den Monat mit 0 Einspeisung und 0 Netzbezug — die ganze PV-Erzeugung zählt dann als Eigenverbrauch,
und ein Bezug aus dem Netz kommt nicht vor.

#### Energiebilanz ergibt negativen Gesamtverbrauch <a name="md_negativer_gesamtverbrauch"></a>

**Was eedc sieht**
PV − Einspeisung + Netzbezug + Batterie-Entladung − Batterie-Ladung ergibt für den Monat deutlich weniger als 0 (unter
−0,5 kWh). Das ist unmöglich. Die Details listen alle Summanden auf. Häufige Ursachen: vertauschte Einspeisungs- und
Netzbezugs-Sensoren oder fehlende Batterie-Daten.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim Netzbezug.
2. Zuerst die Batterie-Werte vervollständigen (beim Speicher «Ladung» und «Entladung»), dann Einspeisung und Netzbezug
   gegeneinander prüfen. Speichern.
3. Ist die Bilanz weiter negativ, enthält PV-Erzeugung oder Einspeisung einen Eingabefehler; bei Werten aus Home
   Assistant die Zuordnung von Einspeisung und Netzbezug in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) prüfen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Gesamtverbrauch, Eigenverbrauch und Autarkie des Monats stehen falsch.

#### Einspeisung größer als PV-Erzeugung <a name="md_einspeisung_groesser_pv"></a>

**Was eedc sieht**
Für den Monat ist mehr Einspeisung erfasst als PV-Erzeugung — du kannst nicht mehr einspeisen, als du erzeugst. Häufigste
Ursache: Einspeisungs- und Netzbezugs-Sensor sind vertauscht, oder das Vorzeichen eines kombinierten Netz-Sensors ist
umgekehrt. Ebenso häufig ist die Erzeugung nur teilweise erfasst (ein String fehlt in den Komponenten). Liegen die
Tageswerte zusammen um mehr als 20 % und zugleich mehr als 20 kWh (die größere der beiden Grenzen) über dem
Monatswert, sagen das die Details zuerst: dann wurde der Monat nach einer Reparatur der Tage nie nachgezogen.

**Lösungsweg**
1. Nennen die Details höhere Tageswerte: im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) «Vorschau laden» — bereits belegte
   Monate stehen dort unter «Konflikte» und sind zum Überschreiben vorausgewählt; vor dem Import einmal durchsehen.
2. Sonst am Befund **«Monat öffnen»** klicken — der Monat öffnet sich bei der Einspeisung. Einspeisung und PV-Erzeugung
   prüfen und berichtigen; bei vertauschten Sensoren die Zuordnung in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) richtigstellen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Eigenverbrauch und Autarkie des Monats stehen falsch, solange einer der beiden Werte nicht stimmt.

#### Mehr PV verwendet als erzeugt? <a name="md_mehr_pv_verwendet_als_erzeugt"></a>

**Was eedc sieht**
Einspeisung plus die aus PV geladene Speichermenge ist für den Monat größer als die Erzeugung. Beides kommt aus derselben
Erzeugung — zusammen kann es nicht mehr sein, als die Anlage geliefert hat. Bewusst als Frage: die häufigste Ursache ist
kein Messfehler. Kleine Abweichungen (bis 2 % der Erzeugung, mindestens 5 kWh) bleiben still.

**Lösungsweg**
1. Wird der Speicher auch aus dem Netz geladen (Arbitrage, Notladung)? Dann unter
   *Einstellungen → Komponenten → Speicher* «Lädt aus dem Netz (z. B. Backup-/Notladung)» setzen und am Befund
   **«Monat öffnen»** beim Speicher die «Netzladung» eintragen. Dann stimmt die Energie, nur die Zuordnung fehlte.
2. Sonst im geöffneten Monat die Erzeugung prüfen: ist sie zu niedrig erfasst, etwa weil ein String-Sensor ausgesetzt
   hat? Berichtigen und speichern.
3. Sind Einspeisung und Netzbezug vertauscht, steht für den Monat meist zusätzlich der Befund „Einspeisung größer als
   PV-Erzeugung“ — dann dort weitermachen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc korrigiert nichts selbst; der Monat rechnet mit den erfassten Werten.

#### Mehr als dreimal so viel wie im Vorjahr <a name="md_feld_dreifach_vorjahr"></a>

**Was eedc sieht**
Einspeisung oder Netzbezug ist mehr als dreimal so groß wie im gleichen Monat des Vorjahres (Vorjahr über 50 kWh).
Häufig ein Eingabefehler (Faktor 10) oder ein Zählerwechsel ohne Neubeginn. Die Prüfung setzt aus, wenn der
Vergleichsmonat vor oder in der Inbetriebnahme liegt, wenn die Erzeugerleistung um mindestens 10 % gewachsen ist (für die
Einspeisung) oder wenn ein Verbraucher dazugekommen ist — Wärmepumpe, E-Fahrzeug, Wallbox (für den Netzbezug).

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim genannten Feld. Die Werte beider Monate prüfen und
   einen Eingabefehler berichtigen.
2. Ist eine neue Wallbox, Wärmepumpe oder Erzeugung der Grund, aber die Meldung kommt trotzdem: unter
   [Komponenten](eedc:/einstellungen/komponenten) beim neuen Gerät das «Anschaffungsdatum» nachtragen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc rechnet mit dem erfassten Wert; ist er ein Eingabefehler, stehen der Monat und seine Vergleiche falsch.

#### Arbeitszahl höher, als eine Wärmepumpe leisten kann <a name="wp_arbeitszahl_zu_hoch"></a>

**Was eedc sieht**
Die Arbeitszahl der Wärmepumpe liegt in diesem Monat über dem, was eine Wärmepumpe im Monatsmittel erreicht (etwa 7).
Der häufigste Grund ist ein Wärmemengenzähler, der mehr misst, als deine Wärmepumpe liefert: Speist ein zweiter Erzeuger
denselben Heizkreis — ein Gas- oder Ölkessel, ein Kamin mit Wassertasche, ein Heizstab vor dem Zähler —, steht seine
Wärme mit im Zähler, sein Strom aber nicht in der Rechnung. Ein Eingabefehler bei Wärme oder Strom im Monat ist der
zweite Grund.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss dieses Monats öffnet sich bei der Wärmepumpe. Wärme und
   Strom prüfen; stimmt ein Wert nicht, berichtigen und speichern.
2. Stimmen die Werte und speist ein zweiter Erzeuger denselben Heizkreis: unter
   *Einstellungen → Komponenten → Wärmepumpe* das Gerät bearbeiten und im Feld «Fremdanteil auf den Zählern» die
   passende Lage wählen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach einer Berichtigung ist der Monat aus der Zeile
   verschwunden; mit gesetztem Fremdanteil verschwindet die Zeile für dieses Gerät ebenso, und die Auswertungen der
   Wärmepumpe zeigen statt der Arbeitszahl den Grund.

**Was ohne Handlung gilt**
Die erfassten Kilowattstunden bleiben unberührt und zählen in allen Mengen weiter mit. Über einer Arbeitszahl von 10
lässt eedc den Wert im Community-Vergleich ganz weg.

### 4.6 Energieprofil – Zähler-Abdeckung <a name="46-energieprofil--zaehler-abdeckung"></a>

> **Variantenhinweis:** Im **HA Add-on** sind die Zähler Sensoren aus Home Assistant (`sensor.…`) mit
> `state_class: total_increasing`. Im **Standalone-Betrieb** sind sie kumulative MQTT-Topics
> (`eedc/<anlage>/inv/<id>/<feld>`). Die Prüfung ist in beiden Fällen dieselbe — sie schaut, ob in der
> Datenquellen-Zuordnung je Komponente ein kWh-Zähler eingetragen ist.

**Was wird geprüft:** Welche kumulativen kWh-Zähler sind in der Datenquellen-Zuordnung der Anlage gesetzt? Ohne sie bleibt
das Energieprofil für die betroffenen Komponenten leer — und damit Prognose-IST, Lernfaktor und die Monatsauswertungen aus
dem Energieprofil. Live-Anzeigen aus den Leistungs-Sensoren (W) funktionieren weiter, ergeben aber keine Energiemengen.

> **Die teuerste Folge betrifft Speicher und PV.** Der bilanzielle Gesamtverbrauch einer Stunde entsteht als
> PV + Netzbezug − Einspeisung − Speicher (= Eigenverbrauch + Netzbezug). Fehlt einer dieser Anteile, wird er als **0**
> gerechnet: die Stunde bleibt nicht leer, sondern fällt **zu niedrig** aus — und sieht dabei plausibel aus. Daran hängt
> die **Grundlast** (Median der Nachtstunden 0–5 Uhr) und mit ihr die Monatsansicht im Cockpit, der **Monatsbericht** und
> der HA-Sensor `eedc_grundlast_kw`. Typisches Bild bei fehlendem Speicher-Zähler: die Grundlast steht im Sommer nahe
> null und steigt scheinbar von selbst, je weniger der Akku die Nacht trägt.
>
> **Nur diese zwei Komponententypen sind betroffen.** Wärmepumpe, Wallbox und E-Auto stehen nicht in dieser Formel — sie
> sind Teil des Gesamtverbrauchs. Ein fehlender Zähler an ihnen lässt ihre eigenen Auswertungen leer, verfälscht aber
> weder Gesamtverbrauch noch Grundlast (nur der **Restverbrauch** = Gesamtverbrauch − separat erfasste Verbraucher wird zu
> hoch).

**Erwartete Zähler je Komponententyp:**

| Komponententyp | Erwartete kWh-Zähler-Felder |
|---------------|------------------------------|
| PV-Module, Balkonkraftwerk | `pv_erzeugung_kwh` |
| Speicher | `ladung_kwh`, `entladung_kwh` |
| Wärmepumpe | `stromverbrauch_kwh`; mit «Getrennte Strommessung» stattdessen `strom_heizen_kwh` und `strom_warmwasser_kwh` (an einer Split-Klimaanlage nur Heizen) |
| Wallbox, E-Auto | `ladung_kwh` |
| Sonstiges | das Zählerfeld seiner Kategorie (Verbraucher, Erzeuger, Abgabe an Dritte); ein Verbrauchszähler (Gas, Wasser, Heizöl) wird übersprungen |
| Wechselrichter | (keine — wird übersprungen) |

> **Was hier „zugeordnet“ heißt — auch MQTT.** Ein Feld trägt einen Zähler, wenn
>
> 1. ihm ein **Sensor aus Home Assistant** zugeordnet ist, **oder**
> 2. dafür **Zählerstände per MQTT ankommen**.
>
> Hast du für ein Feld ausdrücklich **«Keine»** gewählt, bleibt das deine Absage — sie schlägt beides.
>
> ⚠ **Entscheidend ist der Messwert, nicht der Eintrag.** Ein Feld, das auf MQTT steht, weil eedc das beim Einrichten als
> Grundeinstellung gesetzt hat, gilt nicht automatisch als versorgt — eedc sieht nach, ob auf dem Topic tatsächlich etwas
> angekommen ist. **Das Fenster ist eine Woche:** Bleibt ein Befund stehen, obwohl du per MQTT publizierst, kam auf diesem
> Topic seit über sieben Tagen nichts an. Dann prüfe deinen Publisher, nicht die Zuordnung.

> **Ein „—“ in der Tagesansicht im Cockpit sagt selbst, woran es liegt.** Drei Lagen führen dorthin, und nur die erste
> ist eine Aufgabe für dich: *Kein Zähler zugeordnet* · *Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände
> vor* · *Der Zähler ist an diesem Tag zurückgesprungen*. Der mittlere Fall ist der Regelfall kurz nach einer Zuordnung:
> Der **Monats**wert steht da, weil er aus der Langzeitstatistik von Home Assistant kommt — **Tages**werte entstehen erst
> ab der Zuordnung. Frühere Tage lassen sich in der Reparatur-Werkbank nachrechnen.

> **Wer hier ausgenommen ist:** **Split-Klimaanlagen** (Wärmepumpenart *Luft-Luft*) werden nicht nach Wärme gefragt, eine
> **Brauchwasser-Wärmepumpe** nicht nach Heizwärme. Das **E-Auto** wird für den Ladezähler übersprungen, wenn eine
> **Wallbox mit eigenem kWh-Zähler** in Betrieb ist (dort wird die Heimladung geführt; für die PV-Ladung als Zusatzfeld
> genügt eine Wallbox), oder wenn es als **Dienstwagen** markiert ist. Stillgelegte und inaktive Komponenten
> zählen nicht mit. Ein **Balkonkraftwerk, an dem PV-Module hängen**, braucht keinen eigenen Zähler — die Module tragen
> seine Erzeugung.

> **Hinweis:** Diese Kategorie prüft nur das **Vorhandensein** der Zuordnung — ob der Zähler tatsächlich Daten liefert,
> prüfen die MQTT-Topic-Abdeckung ([§4.8](#48-mqtt-topic-abdeckung)) bzw. Sensor-Mapping – HA-Statistics
> ([§4.9](#49-sensor-mapping--ha-statistics)). Unmögliche Stundenwerte erfasst [§4.7](#47-energieprofil--plausibilitaet).

---

#### Basis-Zähler über eine andere Quelle befüllt <a name="basis_zaehler_manuell_ok"></a>

**Was eedc sieht**
Einspeisung und Netzbezug haben keine Zuordnung, aber die Monatsdaten werden über eine andere Quelle gepflegt (die
Meldung nennt sie). Für die Monatsauswertungen ist die Abdeckung damit erfüllt.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange die Quelle die Monate füllt.

**Was ohne Handlung gilt**
Die Monatsauswertungen rechnen mit den gepflegten Werten. Tages- und Stundenwerte brauchen weiterhin kumulative
kWh-Zähler — ohne sie bleiben die Tagesansicht im Cockpit und die Stundenwerte leer.

#### Kein Basis-Zähler für Einspeisung oder Netzbezug <a name="basis_zaehler_fehlt"></a>

**Was eedc sieht**
In der Datenquellen-Zuordnung fehlt der kumulative kWh-Zähler für Einspeisung, Netzbezug oder beide. Ohne ihn bleibt der
bilanzielle Gesamtverbrauch im Energieprofil leer — und damit auch die Grundlast, die als Median der Nachtstunden daraus
gebildet wird (Monatsansicht im Cockpit, Monatsbericht, HA-Sensor `eedc_grundlast_kw`). Als zugeordnet gilt ein Feld mit
einem Sensor aus Home Assistant oder mit Zählerständen, die in der letzten Woche per MQTT angekommen sind.

**Lösungsweg**
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim fehlenden Zähler.
2. Den kumulativen kWh-Zähler zuordnen, nicht den Leistungs-Sensor in Watt. Schickst du die Werte per MQTT, den
   Publisher prüfen: auf dem Topic kam seit über sieben Tagen nichts an.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — an der Stelle steht «Basis-Zähler (Einspeisung + Netzbezug)
   gemappt».

**Was ohne Handlung gilt**
Gesamtverbrauch und Grundlast bleiben im Energieprofil leer. Die Monatswerte kannst du weiter im Monatsabschluss von Hand
pflegen.

#### Basis-Zähler zugeordnet <a name="basis_zaehler_ok"></a>

**Was eedc sieht**
Für Einspeisung und Netzbezug ist je ein kumulativer kWh-Zähler zugeordnet. Das Energieprofil kann damit den
bilanziellen Gesamtverbrauch und die Grundlast bilden.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange beide Zähler zugeordnet sind.

**Was ohne Handlung gilt**
Gesamtverbrauch und Grundlast entstehen aus den beiden Zählern.

#### Komponenten ohne vollständige kWh-Zähler <a name="komponenten_ohne_zaehler"></a>

**Was eedc sieht**
Mindestens eine aktive Komponente hat nicht alle erwarteten kWh-Zähler zugeordnet; die Meldung nennt die Komponenten und
die fehlenden Felder. Für sie bleibt das Energieprofil leer — Prognose-IST, Lernfaktor und Monatsberichte fehlen. Bei
einem Speicher oder einer PV-Erzeugung kommt die teuerste Folge hinzu: der Gesamtverbrauch je Stunde
(PV + Netzbezug − Einspeisung − Speicher) rechnet den fehlenden Anteil als 0 und fällt zu niedrig aus — mit ihm die
Grundlast (Monatsansicht im Cockpit, Monatsbericht, HA-Sensor `eedc_grundlast_kw`). Diese Zahl sieht plausibel aus.
Wärmepumpe, Wallbox und E-Auto verfälschen Gesamtverbrauch und Grundlast nicht; bei ihnen bleiben nur die eigenen
Auswertungen leer.

**Lösungsweg**
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der ersten genannten Komponente.
2. Je Komponente die kWh-Zeilen belegen, nicht nur die Watt-Zeilen; ein Speicher braucht Ladung und Entladung. Liefert
   ein Gerät nur Leistung (W), baut Home Assistant unter *Helfer → „Integral-Sensor“* (Riemannsche Summe) einen
   kWh-Zähler daraus. Für die übrigen Komponenten der Liste diesen Schritt wiederholen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — an der Stelle steht «Alle … aktiven Komponenten haben
   kWh-Zähler gemappt».

**Was ohne Handlung gilt**
Die Auswertungen dieser Komponenten bleiben leer; fehlt der Zähler an einem Speicher oder einer PV-Erzeugung, stehen
Gesamtverbrauch und Grundlast zu niedrig. Ein Feld, für das du «Keine» gewählt hast, zählt als ohne Zähler — die Zeile
bleibt dann stehen.

#### Balkonkraftwerk über die PV-Module gedeckt <a name="bkw_ueber_module_ok"></a>

**Was eedc sieht**
An einem Balkonkraftwerk hängen PV-Module, und diese tragen seine Erzeugung — gemessen wird am Modul. Das
Balkonkraftwerk selbst braucht dann keinen eigenen kWh-Zähler. Ein Balkonkraftwerk ohne Module braucht weiterhin seinen
eigenen.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange die Module zugeordnet sind.

**Was ohne Handlung gilt**
eedc liest die Erzeugung des Balkonkraftwerks aus den Zählern seiner Module.

#### Alle aktiven Komponenten haben kWh-Zähler <a name="komponenten_zaehler_ok"></a>

**Was eedc sieht**
Alle aktiven Komponenten, für die eedc Zähler erwartet, haben ihre kWh-Zähler zugeordnet.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange die Zuordnungen bestehen.

**Was ohne Handlung gilt**
Das Energieprofil rechnet je Komponente mit den zugeordneten Zählern.

#### Erzeuger über den Anlagen-Zählerstand gedeckt <a name="erzeuger_ueber_anlagenzaehler_ok"></a>

**Was eedc sieht**
Der PV-Zählerstand der ganzen Anlage versorgt Monat, Tag und Stunde als Summe. Es fehlt nur die Aufschlüsselung je
Erzeuger — dafür braucht jeder einzelne einen eigenen Zähler. Misst nur ein Teil der Erzeuger, trägt weiter der
Anlagenzähler die Summe des Tages; erst wenn alle Erzeuger den ganzen Tag messen, rechnet eedc Tag und Stunde aus den
Einzelzählern.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange der Anlagenzähler zugeordnet ist.

**Was ohne Handlung gilt**
eedc rechnet die PV-Erzeugung als Summe aus dem Anlagenzähler, ohne Aufteilung je Erzeuger.

#### Komponenten über eine andere Quelle befüllt <a name="komponenten_manuell_ok"></a>

**Was eedc sieht**
Für diese Komponenten ist keine Zuordnung nötig — ihre Monatsdaten werden über eine andere Quelle gepflegt (die Meldung
nennt sie).

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange die Quelle die Monate füllt.

**Was ohne Handlung gilt**
Die Monatsauswertungen rechnen mit den gepflegten Werten. Tages- und Stundenwerte brauchen weiterhin kumulative
kWh-Zähler — ohne sie bleiben die Tagesansicht im Cockpit und die Stundenwerte leer.

#### Komponenten ohne Zusatz-Zähler für Tageswerte <a name="komponenten_ohne_zusatzzaehler"></a>

**Was eedc sieht**
Es geht um zusätzliche Messstellen: Wärmemengenzähler einer Wärmepumpe (Heizwärme, Warmwasser-Wärme) und die getrennte
PV-Ladung an Wallbox oder E-Auto. Diese Werte lassen sich nur aus einem eigenen kumulativen Zähler ableiten; ohne ihn
bleiben sie in der Tagesansicht im Cockpit auf „—“. Kein Fehler — solche Zähler hat längst nicht jede Anlage. Eine
Split-Klimaanlage wird nicht nach Wärme gefragt, eine Brauchwasser-Wärmepumpe nicht nach Heizwärme.

**Lösungsweg**
1. Hast du einen solchen Zähler: am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der
   ersten genannten Komponente — und das kWh-Feld zuordnen.
2. Hast du keinen: nichts zu tun. Die Monatswerte pflegst du bei Bedarf im Monatsabschluss von Hand.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die zugeordneten Komponenten sind aus der Zeile verschwunden;
   ohne Zähler bleibt sie als Hinweis stehen.

**Was ohne Handlung gilt**
Die Monatsauswertungen sind nicht betroffen. Nur die genannten Tageswerte bleiben in der Tagesansicht im Cockpit auf „—“.

#### Tage vor dem Umbau gerechnet <a name="tage_vor_umbau_ohne_regelmarke"></a>

**Was eedc sieht**
eedc rechnet eine fehlende Stunde aus Home Assistant heute wie das Energie-Dashboard: ihre Energie steht in der Stunde
danach, und die Tagesansicht im Cockpit zeigt Eigenverbrauch, Autarkie und Gesamtverbrauch auch an solchen Tagen. Die
genannten Tage wurden vor dieser Umstellung gerechnet und zeigen dort noch „—“. Gezählt werden nur Tage mit eigenen
Stundenwerten; Tage, deren Mengen aus der Langzeitstatistik von Home Assistant oder aus den gespeicherten
Zählerständen kommen, brauchen das nicht.

**Lösungsweg**
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc rechnet die jüngsten Tage neu,
   höchstens 31 je Lauf.
2. Bleiben ältere Tage übrig, erscheint die Zeile danach mit dem nächsten Zeitraum; den Knopf dann erneut nutzen.
3. Steht am Befund statt dessen **«Sensor zuordnen»**: der Anlage fehlt eine Leistungs- oder Zähler-Zuordnung. Der Knopf
   öffnet die Datenquellen-Zuordnung; nach der Zuordnung steht am Befund wieder «Tage neu aufbauen».
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, oder sie nennt den nächsten
   Zeitraum.

**Was ohne Handlung gilt**
Die genannten Tage zeigen in der Tagesansicht im Cockpit bei Eigenverbrauch, Autarkie und Gesamtverbrauch weiter „—“.
Eine automatische Umrechnung beim Start gibt es bewusst nicht.

#### Tage mit Mengen aus den gespeicherten Stundenwerten <a name="tage_ohne_kanal_deckung"></a>

**Was eedc sieht**
An diesen Tagen kommen PV, Netz und Speicher weder aus der Langzeitstatistik von Home Assistant noch aus eigenen
Zählerständen. eedc liest ihre Mengen deshalb aus den gespeicherten Stunden- und Tageswerten — so wie vor der Umstellung.
Typisch sind Tage vor dem ersten gespeicherten Zählerstand. Die Details nennen auch die Zahl der Tage mit der neuen
Deckung.

**Lösungsweg**
1. Nichts zu tun — das ist kein Fehler. Der Knopf **«Was gilt»** am Befund öffnet diesen Text.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange es solche Tage gibt; sie macht nur
   sichtbar, welche Tage noch aus den gespeicherten Werten rechnen.

**Was ohne Handlung gilt**
Diese Tage rechnen weiter mit den gespeicherten Stunden- und Tageswerten.

### 4.7 Energieprofil – Plausibilität <a name="47-energieprofil--plausibilitaet"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten gleich — sie liest nur die bereits gespeicherten
> Stundenwerte des Energieprofils.

**Was wird geprüft:** Enthalten die Tagesprofile der letzten 30 Tage Stundenwerte, die physikalisch unmöglich sind?
Konkret: PV oder Einspeisung einer Stunde größer als die Anlagenleistung × 1,5. Das tritt typisch nach einem Neustart
während des Tages auf, wenn ein verzerrter Zählerstand gespeichert wurde. Dazu kommen zwei Tagesprüfungen: Tage mit mehr
Einspeisung als Erzeugung plus Speicher-Entladung (Toleranz 0,5 kWh) und Tage mit einem Nachtrag nach eingefrorenem
Zähler.

**Schwelle:** Anlagen-kWp × 1,5. Eine Aufdach-PV-Anlage erzeugt selbst bei optimalem Sonnenstand nicht mehr als etwa
1500 W je kWp — Werte darüber sind Rechen- oder Messfehler, keine Naturereignisse.

**Die Schwelle wächst mit der Zeit, in der sich der Zählerstand nicht geändert hat:** Trägt eine Stunde die Energie einer
Lücke in Home Assistant (in der Stundentabelle beschriftet „enthält n Stunden“) oder den Nachtrag nach Stunden mit
unverändertem Stand, gilt kWp × 1,5 × Stunden seit der letzten Änderung (höchstens 24 Stunden) — sonst würde jeder echte
Nachtrag als unmöglicher Wert gemeldet. Dieselbe Regel entscheidet beim Rechnen der Tage, ob eine Menge verworfen wird.

> **Tage aus der Langzeitstatistik von Home Assistant.** Die Prüfung auf unmögliche Stundenwerte schaut nur auf Tage aus
> eigenen Stundenwerten; der Verdacht auf PV-Doppelerfassung ([§4.18](#418-pv-doppelerfassung)) zählt für den
> spezifischen Tagesertrag auch Tage aus der Langzeitstatistik (die PV wie in der Tagesansicht im Cockpit), nur die
> Performance Ratio bleibt die der gespeicherten Tageszeile. An
> einem Tag, dessen Mengen aus der Langzeitstatistik kommen, ist eine hohe Stunde die Zahl von Home Assistant, wie im
> Energie-Dashboard; ein Sprung mit dem typischen Muster (Sensor fällt kurz auf 0 und kehrt zurück) meldet
> [§4.8b](#48b-zaehlerstaende--sprung-in-home-assistant). **Ein reiner Sprung ohne dieses Muster** bekommt an einem
> solchen Tag **keinen** Befund: prüfe ihn in Home Assistant unter *Entwicklerwerkzeuge → Statistik* und berichtige ihn
> dort.

> **Ältere Tage** (über 30 Tage) prüft die Stundenwert-Prüfung nicht — die beiden Tagesprüfungen (Einspeisung über
> Erzeugung, Nachtrag) sehen alle gespeicherten Tage: dort stehen meist schon berichtigte Werte, und für den aktuellen
> Lernfaktor zählen sie nicht mehr. Wer ältere Tage trotzdem reparieren will, nutzt in der Reparatur-Werkbank
> «Mehrere Tage neu aggregieren» über den entsprechenden Bereich — das reicht so weit zurück wie die Langzeitstatistik
> von Home Assistant.

---

#### Tage mit mehr Einspeisung als Erzeugung <a name="einspeisung_groesser_erzeugung_tage"></a>

**Was eedc sieht**
An diesen Tagen wurde mehr ins Netz eingespeist, als PV und Speicher-Entladung zusammen geliefert haben (Toleranz
0,5 kWh; Entladung ins Netz ist erlaubt). Eigenverbrauch und Autarkie stehen dort auf 0 bzw. „—“. Die Details listen die
Tage mit allen drei Mengen. Häufige Ursachen: der PV-Zähler liefert nicht (steht auf 0), Einspeisung und Netzbezug sind
vertauscht, oder das Vorzeichen eines kombinierten Netz-Sensors ist umgekehrt.

**Lösungsweg**
1. Zuerst die Zuordnung prüfen: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) nachsehen, ob der
   PV-Zähler liefert und ob Einspeisung und Netzbezug richtig herum zugeordnet sind; Fehler dort berichtigen.
2. Danach am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc baut die Tage aus
   eigenen Stundenwerten neu (höchstens 31 Tage je Lauf). Kommen alle Tage aus der Statistik von Home Assistant, heißt
   der Knopf **«Aus Home Assistant neu übernehmen»** und übernimmt nur den jüngsten Tag — dann vorher die Statistik in
   Home Assistant unter *Entwicklerwerkzeuge → Statistik* berichtigen; nach dem erneuten Prüfen steht der Knopf am
   nächsten Tag. Steht am Befund nur
   **«Was gilt»**, kommen die Mengen aus eedcs eigenen Zählerständen; dann wirkt die berichtigte Zuordnung auf die
   folgenden Tage.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die berichtigten Tage sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
An diesen Tagen stehen Eigenverbrauch und Autarkie auf 0 bzw. „—“; Tag und Monat rechnen mit den Mengen, wie sie gemessen
sind.

#### Nachtrag nach eingefrorenem Zähler <a name="nachtrag_nach_eingefrorenem_zaehler"></a>

**Was eedc sieht**
An diesen Tagen stand ein Zähler (PV oder Einspeisung) mehrere Stunden still und lieferte die Menge danach in einer
einzigen Stunde nach — mehr, als in einer Stunde erzeugt werden kann. Sie zählt im Tag und im Monat mit, wie in Home
Assistant. Die Details nennen je Tag die Mengen und sagen, ob der Tag aus der Langzeitstatistik von Home Assistant oder
aus Zählerständen gerechnet ist. Dieselbe Form hat ein Zählersprung nach einer Nacht ohne Erzeugung.

**Lösungsweg**
1. Die genannten Mengen prüfen (der Knopf **«Was gilt»** am Befund öffnet diesen Text). Stimmen sie, ist nichts zu tun.
2. Stimmt eine nicht, liegt der Fehler in der Zähler-Historie der Quelle: in Home Assistant unter
   *Entwicklerwerkzeuge → Statistik* beim Sensor mit „Wert anpassen“ berichtigen. Danach den Tag in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) neu holen: «Aus Home Assistant
   neu übernehmen» für einen Tag aus der Statistik von Home Assistant, sonst «Tag neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein solcher Nachtrag in den Tagen steht.

**Was ohne Handlung gilt**
Der Nachtrag zählt im Tag und im Monat mit, wie in Home Assistant. Die Menge geht nicht verloren, sie steht nur gebündelt
in einer Stunde.

#### Keine unmöglichen Stundenwerte <a name="counter_spikes_ok"></a>

**Was eedc sieht**
In den letzten 30 Tagen liegt kein Stundenwert von PV oder Einspeisung über der Schwelle (Anlagenleistung × 1,5); die
Meldung nennt die Schwelle.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt grün, solange kein solcher Wert dazukommt.

**Was ohne Handlung gilt**
Die Stundenwerte der letzten 30 Tage gehen so in Tag, Monat und Lernfaktor ein.

#### Unmöglicher Stundenwert an einem Tag <a name="counter_spike_tag"></a>

**Was eedc sieht**
Dieser Tag enthält mindestens eine Stunde, in der PV oder Einspeisung über der Schwelle liegt (Anlagenleistung × 1,5 je
Stunde; trägt die Stunde die Energie einer Lücke von n Stunden, gilt die n-fache Schwelle) — so viel erzeugt keine Anlage
in dieser Zeit. Häufige Ursache ist ein Neustart während des Tages, bei dem ein verzerrter
Zählerstand gespeichert wurde. Die Details nennen Stunde und Wert. Geprüft werden die letzten 30 Tage, und nur Tage aus
eigenen Stundenwerten.

**Lösungsweg**
1. Am Befund **«Tag neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt die Zählerstände des Tages
   neu und rechnet den Tag in einem Schritt neu.
2. Sind mehrere Tage betroffen, in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren» mit
   dem passenden Von-/Bis-Bereich nutzen; das reicht auch für Tage, die älter als 30 Tage sind.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist verschwunden, oder an der Stelle steht «Keine
   Counter-Spikes in den letzten 30 Tagen».

**Was ohne Handlung gilt**
Die überhöhte Stunde bleibt im Tag stehen und zählt im Tag und im Lernfaktor mit; in den Monat geht sie nur ein, wenn der
Monat keinen eigenen Monatswert hat.

### 4.8 MQTT-Topic-Abdeckung <a name="48-mqtt-topic-abdeckung"></a>

> **Variantenhinweis:** Diese Kategorie greift in beiden Varianten — aber **nur**, wenn der Empfang über MQTT
> eingeschaltet ist (*Einstellungen → Integration → MQTT-Broker-Verbindung*, Schalter «Daten über MQTT empfangen
> (Import)»). Ohne eingeschalteten Empfang erscheint die Kategorie gar nicht — nicht „OK“, nicht „leer“ —, damit
> Anwender ohne MQTT sie nicht sehen.

**Was wird geprüft:** Kommen die MQTT-Topics, die eedc aus der Datenquellen-Zuordnung erwartet, tatsächlich an? Die
Erwartung entsteht in eedc; der Absender (eine Automation in Home Assistant, ioBroker, Node-RED) ist fest verdrahtet.
Vergisst dort jemand ein neues Feld oder zieht nach einem neuen Import die Nummer eines Geräts nicht nach, laufen
Erwartung und Wirklichkeit auseinander — diese Kategorie macht das sichtbar.

**Schwellwerte für „veraltet“:**

| Topic-Kategorie | Maximales Alter |
|----------------|-----------------|
| Live-Topics (sensorgetrieben) | 2 Minuten |
| Energie-Topics (alle 5 Minuten plus Puffer) | 10 Minuten |

**Welche Topics eedc erwartet.** Gemeldet wird nur, was auch über MQTT kommen soll: Felder, deren Quelle auf **«Keine»**
oder einen **Sensor aus Home Assistant** gespeichert ist, tauchen nicht auf. Es zählt die **gespeicherte** Wahl — zeigt die
Datenquellen-Fläche «Keine» nur an, weil nichts ankommt, zählt das nicht; einmal «Keine» anklicken speichert die Wahl.
Felder über ein **MQTT-Gateway** zählen mit, deren Werte laufen durch denselben Weg. Erwartet wird nur, was es am Gerät
gibt, und davon nur, was am Gerät Pflicht ist oder was du über MQTT zugeordnet hast:

- **Pflicht** heißt dasselbe wie in der Datenquellen-Zuordnung (rot markierte Felder): die Zählerstände Einspeisung,
  Netzbezug und PV gesamt, am Speicher Ladung und Entladung, an der Wärmepumpe der Strom und — außer an einer
  Split-Klimaanlage — die Wärmemenge, am E-Auto die Kilometer, an der Wallbox die Ladung.
- **Optionale Felder** — Live-Leistungen, Ladestand, Netzladung, Betriebsart-Felder an einer Luft-Wasser-Wärmepumpe —
  erwartet eedc nur, wenn du ihnen MQTT oder ein Gateway als Quelle zugeordnet hast (eine Luft-Wasser-Wärmepumpe ohne
  Zuordnungen erwartet damit drei Topics statt siebzehn).
- Die V2H-Entladung nur an einem E-Auto mit „V2H-fähig“, die Netzladung nur an einem Speicher mit «Lädt aus dem Netz
  (z. B. Backup-/Notladung)», der Strom für Heizen und Warmwasser nur an einer Wärmepumpe mit getrennter Strommessung.
- **Neben einer Wallbox mit Ladezähler** erwartet eedc am E-Auto keine Lade- und Verbrauchsfelder (die Wallbox trägt die
  Ladung); Kilometer bleiben erwartet, Ladestand und V2H-Entladung, wenn du sie über MQTT zugeordnet hast.
- Bei **zwei Wegen zu einer Größe** (PV gesamt oder Zähler je Modul, Wärme gesamt oder Heizwärme) erwartet eedc beide,
  solange keiner zugeordnet ist, und nach der Zuordnung des einen nur noch diesen.
- Publizierst du auf ein Topic, ohne das Feld zuzuordnen, übernimmt die Datenquellen-Fläche die Zuordnung beim nächsten
  Öffnen, sobald Werte ankommen — erst dann gilt das Feld hier als zugeordnet.

Wie ein Topic eingerichtet wird, steht im Handbuch Einstellungen,
[§7.5 Ein MQTT-Topic zuordnen](HANDBUCH_EINSTELLUNGEN.md#75-ein-mqtt-topic-zuordnen).

---

#### MQTT-Empfang eingeschaltet, aber nicht verbunden <a name="mqtt_subscriber_laeuft_nicht"></a>

**Was eedc sieht**
Der Empfang über MQTT ist eingeschaltet, aber er läuft nicht — meist, weil eedc beim letzten Start keine Verbindung zum
Broker aufbauen konnte, etwa weil der Broker nicht erreichbar ist oder die Zugangsdaten nicht stimmen. Über MQTT kommen
dann keine Werte an.

**Lösungsweg**
1. Am Befund **«Zur Verbindung»** klicken — die MQTT-Broker-Verbindung öffnet sich.
2. Broker-Adresse und Zugangsdaten prüfen und speichern. Brauchst du keine Daten über MQTT, dort den Schalter «Daten über
   MQTT empfangen (Import)» ausschalten.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; mit ausgeschaltetem Empfang
   zählt der Kopf des Daten-Checkers die Prüfung als «nicht ausführbar (MQTT-Import aus)».

**Was ohne Handlung gilt**
Über MQTT kommen keine Live-Werte und keine Zählerstände an; Felder, die nur über MQTT versorgt werden, bleiben leer.

#### MQTT-Topics erwartet, nie empfangen <a name="mqtt_topics_nie_empfangen"></a>

**Was eedc sieht**
Die Verbindung zum Broker steht, aber für die genannten Topics hat noch keine Quelle Daten geliefert. Die Zeile nennt
die Zahl, die Details bis zu sechs Topics mit vollem Pfad — erst der Pfad sagt, an welchem Gerät das Feld fehlt.
Erwartet werden nur Felder, die über MQTT kommen sollen: die Pflichtfelder eines Geräts (in den Datenquellen rot
markiert) und optionale Felder, denen du MQTT oder ein Gateway als Quelle zugeordnet hast. Felder mit gespeicherter
Quelle «Keine» oder einem Sensor aus Home Assistant zählen nicht.

**Lösungsweg**
1. Am Befund **«Topics prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim ersten betroffenen Gerät.
2. Je Topic klären: Ist die Publisher-Automation (Home Assistant, ioBroker, Node-RED) noch nicht eingerichtet, sie
   einrichten. Hat sich nach einem neuen Import die Nummer des Geräts geändert, das Topic in der Automation nachziehen —
   der Pfad enthält sie.
3. Wird ein Feld gar nicht über MQTT geliefert: in der Datenquellen-Zuordnung dessen Quelle auf «Keine» stellen — einmal
   anklicken speichert die Wahl. Brauchst du MQTT überhaupt nicht, in der
   [MQTT-Broker-Verbindung](eedc:/einstellungen/integration?block=mqtt-broker) «Daten über MQTT empfangen (Import)»
   ausschalten.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die versorgten oder abbestellten Topics sind aus der Zeile
   verschwunden.

**Was ohne Handlung gilt**
Die Felder dieser Topics bleiben leer; was aus ihnen rechnet, fehlt in Live-Anzeige, Tag und Monat.

#### MQTT-Topics mit veralteten Werten <a name="mqtt_topics_veraltet"></a>

**Was eedc sieht**
Die genannten Topics wurden schon empfangen, aber ihr letzter Wert ist älter als erlaubt: Live-Topics sollten innerhalb
von 2 Minuten, Energie-Topics innerhalb von 10 Minuten neu kommen. Die Zeile nennt die Zahl, die Details bis zu fünf
Topics mit ihrem Alter in Minuten. Meist läuft die Publisher-Automation nicht mehr oder hat ihre Quelle verloren (etwa
ein Wechselrichter offline).

**Lösungsweg**
1. Am Befund **«Topics prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim ersten betroffenen Gerät.
2. Die Publisher-Automation prüfen: Läuft sie noch, liefert ihre Quelle? Fehlt die Quelle dauerhaft, die Automation
   aufräumen oder in der Datenquellen-Zuordnung die Quelle des Felds ändern.
3. Brauchst du MQTT überhaupt nicht, in der
   [MQTT-Broker-Verbindung](eedc:/einstellungen/integration?block=mqtt-broker) «Daten über MQTT empfangen (Import)»
   ausschalten.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die wieder frischen Topics sind aus der Zeile verschwunden.

**Was ohne Handlung gilt**
eedc nutzt nur, was ankommt: in der Live-Anzeige bleibt der zuletzt empfangene Wert als aktueller Wert stehen; in den
Mengen von Tag und Monat kommt ab dem letzten Empfang nichts mehr hinzu.

#### Alle erwarteten MQTT-Topics aktuell <a name="mqtt_ok"></a>

**Was eedc sieht**
Die Verbindung zum Broker steht, und alle erwarteten Topics liefern frische Werte innerhalb der Toleranz.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange die Topics regelmäßig kommen.

**Was ohne Handlung gilt**
eedc liest Live-Werte und Zählerstände aus den empfangenen Topics.

### 4.8a Zählerstände – Rücksprung <a name="48a-zaehlerstaende--ruecksprung"></a>

> **Variantenhinweis:** Diese Kategorie greift, sobald Zählerstände über MQTT ankommen. Über Home Assistant ist sie
> gegenstandslos — dort liefert die Langzeitstatistik einen bereits bereinigten Stand, ein Verbrauchszähler mit
> Tageszyklus ist also unschädlich.

**Was wird geprüft:** Steigt jeder per MQTT gelieferte Zählerstand fortlaufend, oder fällt er zwischendurch auf einen
niedrigeren Wert zurück? Geprüft werden die letzten **30 Tage** der mitgeschriebenen Stände.

**Warum das zählt.** eedc bildet aus zwei Ständen eine Menge — Anfang und Ende des Zeitraums, die Differenz dazwischen.
Springt der Zähler dazwischen auf null zurück, gehören die beiden Stände zu **verschiedenen Zählerläufen**, und ihre
Differenz ist keine Menge. Typisch ist das bei einem Feld, das „heute“ oder „diesen Monat“ meint statt des Gesamtstands.

**Was eedc dann tut:** Es liefert für dieses Feld **keinen Wert** — im Monatsabschluss steht kein Vorschlag, in der
Monatsansicht im Cockpit bleibt der gespeicherte Wert stehen. Das ist Absicht: eine Zahl aus zwei unzusammenhängenden
Zählerläufen sähe aus wie eine Messung und wäre keine.

**Mit eigener Summe.** Führt eedc für das Feld eine eigene Summe aus den MQTT-Ständen, rechnet es den Zähler wie Home
Assistant: ein Stand unter 90 % des vorigen gilt als Neubeginn, die Summe läuft weiter — Tag, Monat und Jahr stimmen dann
auch für einen Zähler, der jeden Tag auf null geht. Nicht verlässlich bleiben „heute“ und „gestern“ im Live-Bereich (sie
vergleichen mit dem Stand um Mitternacht) und Geräte-Tageswerte aus der Zeit davor; einen Vorschlag im Monatsabschluss
gibt es für so ein Feld weiterhin nicht. Die Meldung nennt dann, welche Felder so rechnen. Die Empfehlung bleibt dieselbe:
den fortlaufenden Stand schicken.

> ⚠ **eedc rechnet den fehlenden Teil nicht hoch**, obwohl es die Stundenstände hätte. Was zwischen dem letzten
> mitgeschriebenen Stand und dem Rücksprung verbraucht wird, steht in keinem Stand mehr — eine hochgerechnete Zahl wäre
> systematisch zu niedrig und im Monatsabschluss per Knopfdruck ein gespeicherter Wert. Die Reparatur liegt beim Absender;
> sobald die Reihe wieder fortlaufend ist, verschwindet der Befund von selbst.

---

#### Zählerstand springt zwischendurch zurück <a name="zaehler_ruecksprung"></a>

**Was eedc sieht**
Ein Zählerstand muss fortlaufend steigen. Bei den genannten Feldern fällt der per MQTT gelieferte Stand in den letzten
30 Tagen mindestens einmal auf einen niedrigeren Wert zurück — typisch für ein Feld, das „heute“ oder „diesen Monat“
meint statt des Gesamtstands. eedc bildet eine Menge aus zwei Ständen; liegt dazwischen ein Neubeginn, ist ihre
Differenz keine Menge. Die Meldung nennt die Felder, wie oft es passiert ist, und belegt den jüngsten Fall mit beiden
Ständen.

**Lösungsweg**
1. Am Befund **«Sensor wechseln»** klicken — die Datenquellen-Zuordnung öffnet sich beim betroffenen Feld. Dort siehst
   du, woher der Wert kommt.
2. Den fortlaufenden Stand schicken statt des Tageswerts: Kommt der Wert aus einem Helfer von Home Assistant, unter
   *Einstellungen → Geräte & Dienste → Helfer* den Verbrauchszähler öffnen und das Zurücksetzen auf „nie“ (ohne Zyklus)
   stellen. Kommt er aus einer eigenen App oder einem Skript, dort den Lebenszählerstand senden.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Befund verschwindet von selbst, sobald in den letzten
   30 Tagen kein Rücksprung mehr liegt; es gibt nichts zu quittieren.

**Was ohne Handlung gilt**
Für ein solches Feld liefert eedc keinen Wert: im Monatsabschluss steht kein Vorschlag, in der Monatsansicht im Cockpit
bleibt der gespeicherte Wert stehen. Rechnet eedc das Feld über eine eigene Summe (die Meldung sagt das), stimmen Tag,
Monat und Jahr trotzdem; nicht verlässlich bleiben dann „heute“ und „gestern“ im Live-Bereich sowie die Tageswerte
der Geräte aus der Zeit, bevor eedc diese eigene Summe führte. eedc rechnet den
fehlenden Teil nicht hoch — er steht in keinem Stand.

### 4.8b Zählerstände – Sprung in Home Assistant <a name="48b-zaehlerstaende--sprung-in-home-assistant"></a>

eedc übernimmt die Langzeitstatistik von Home Assistant so, wie das Energie-Dashboard sie zeigt — ohne Obergrenze je
Stunde. Meldet ein Sensor kurz 0 (Wechselrichter nachts „nicht verfügbar“, Neustart) und springt danach in einer Stunde
auf seinen alten Stand zurück, hält Home Assistant das für einen neuen Zähler und bucht beim Zurückkehren den ganzen
Zählerstand als Zuwachs dieser Stunde. Dieser Sprung steht dann in Tag, Monat und Jahr und in der Stunde des
Tagesverlaufs — in eedc wie in Home Assistant. Geprüft werden die letzten 30 Tage.

**Was kein Befund ist.** Ein Zähler, der nach dem Zurücksetzen wieder hochzählt (ein neuer Zähler nach einem Tausch):
dort entsteht kein Sprung. Ein **Tageszähler** (PV-Tagesertrag, Verbrauchszähler „heute“), auch wenn seine erste helle
Stunde nach einem schwachen Vortag den Vortag schon fast erreicht. eedc erkennt ihn an zwei Merkmalen, eines genügt: Er
geht an mindestens zwei Tagen des Prüffensters in der ersten Statistikzeile seines Tages auf 0 — um Mitternacht oder, bei
einem nachts abgeschalteten Wechselrichter, in der ersten Stunde mit Werten. Oder sein Stand vor der 0 ist höchstens das
Dreifache seines größten Tageszuwachses im Prüffenster: ein Tageszähler kommt nie über einen Tag hinaus, ein
Gesamtzähler liegt weit darüber. Am Tageszähler ist nur der **Aussetzer** ein Befund: eine 0 mitten im Tag, auf die der
alte Stand in der unmittelbar nächsten Stunde zurückkommt — dann hat Home Assistant den Tag doppelt gebucht.

**Grenzen:** Ein Gesamtzähler mit weniger als drei Tagen eigener Historie und ein Monatszähler in seinen ersten drei
Tagen gelten als Tageszähler (ihr Sprung wäre entsprechend klein); ein Aussetzer über zwei oder mehr Stunden am
Tageszähler ist von einem Tagesbeginn nach einer Lücke nicht zu trennen und wird nicht gemeldet. Die Prüfung erkennt nur
dieses Muster (Rücksetzen und Rückkehr). Springt die Summe in Home Assistant ohne Rücksetzen, meldet weder sie noch die
Prüfung auf unmögliche Stundenwerte ([§4.7](#47-energieprofil--plausibilitaet)) an einem solchen Tag etwas.

---

#### Zählersprung in der Statistik von Home Assistant <a name="ha_zaehlersprung"></a>

**Was eedc sieht**
Ein Sensor hat kurz 0 gemeldet (etwa ein Wechselrichter, der nachts „nicht verfügbar“ ist, oder ein Neustart) und ist
danach auf seinen alten Stand zurückgekehrt. Home Assistant hält das für einen neuen Zähler und bucht beim Zurückkehren
den ganzen Zählerstand als Zuwachs dieser einen Stunde. eedc übernimmt die Langzeitstatistik so, wie das Energie-Dashboard
von Home Assistant sie zeigt — der Sprung steht deshalb in Tag, Monat und Jahr. Die Meldung nennt je Fund der letzten
30 Tage Sensor, Tag, Stunde und die Menge des Sprungs.

**Lösungsweg**
1. In Home Assistant unter *Entwicklerwerkzeuge → Statistik* den genannten Sensor suchen, beim Symbol „Wert anpassen“
   die genannte Stunde wählen und den Zuwachs auf die echte Menge setzen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»** —
   eedc holt die berichtigte Statistik und baut den Tag des ersten Funds neu auf. Ohne Klick gleicht eedc die
   Statistik beim nächtlichen Abgleich von selbst ab.
3. Hast du einen betroffenen Monat schon gespeichert (mit «Aus HA laden» oder per Import), den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen und mit «Aus HA laden» neu übernehmen — ein
   gespeicherter Monat ändert sich nicht von allein.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Sprung ist aus der Liste verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

**Was ohne Handlung gilt**
Der Sprung bleibt in Tag, Monat und Jahr stehen — in eedc wie im Energie-Dashboard von Home Assistant. eedc schneidet
ihn nicht selbst ab: die Quelle ist die Statistik in Home Assistant.

### 4.8c Zählerstände – Rückgang in Home Assistant <a name="48c-zaehlerstaende--rueckgang-in-home-assistant"></a>

Das Gegenstück zum Sprung: Die Summe eines Sensors in der Langzeitstatistik von Home Assistant **fällt** in einer
Stunde, statt zu steigen. Meist wurde der Wert in Home Assistant nachträglich nach unten angepasst (unter
*Entwicklerwerkzeuge → Statistik* mit „Wert anpassen“, mit einer zu großen Korrektur oder an der falschen Stunde), oder
ein Sensor hat einen kleineren Zählerstand gemeldet. Home Assistant bucht das als negative Menge, und eedc übernimmt die
Statistik so, wie das Energie-Dashboard sie zeigt — der Rückgang steht als Abzug in Tag, Monat und Jahr, und
«Aus HA laden» schlägt für den Monat einen zu kleinen oder negativen Wert vor.

Das ist **kein Vorzeichen** für Entladen oder Einspeisen: Lade-, Entlade- und Einspeisezähler laufen nur nach oben, jede
Richtung hat ihr eigenes Feld. Fällt ein Entlade-Zähler, ist das kein Entladen, sondern ein gesunkener Zählerstand —
typisch nach dem Neustart einer Integration, die den Zähler selbst hochrechnet und mit der Zustandsklasse `total` statt
`total_increasing` meldet.

Geprüft wird die **ganze** übernommene Statistik, nicht nur die letzten 30 Tage: ein Rückgang aus einem alten Monat trifft
jede Sicht und «Aus HA laden» genauso wie ein frischer. Der Tag eines Funds ist der Kalendertag, wie im
Energie-Dashboard von Home Assistant: auch die Stunde ab 23:00 gehört zu ihrem eigenen Tag (in der Tagesansicht im
Cockpit die Stunde 23–24 Uhr). Ein täglich zurückgesetzter Helfer ist kein Befund (sein Stand fällt jede Nacht, die
Summe in Home Assistant zählt weiter), ein Zählersprung ([§4.8b](#48b-zaehlerstaende--sprung-in-home-assistant)) auch
nicht — dort steigt die Summe.

Lädst du einen betroffenen Monat mit «Aus HA laden» in einen Monat, der schon Daten hat, nennt der Vergleichsdialog die
Felder mit negativem Wert unter „Rückgang in Home Assistant“ und denselben Weg.

> **Stunden ohne Langzeitstatistik.** Wo die Langzeitstatistik von Home Assistant für eine Stunde nichts hat, nimmt eedc
> seine eigenen gespeicherten Stundenstände dieses Zählers — aber nur für die Zeit vor dem ersten Wert aus Home
> Assistant, nicht für Lücken mittendrin, und ein späterer Abgleich mit Home Assistant ersetzt diese Stunden nicht.
> Liegen von einem Zähler nur Stände um Mitternacht vor, stimmen die Tagesmengen; die Stundenansicht zeigt den Tag als
> eine Spanne ohne Verteilung auf die Stunden.

---

#### Zählerstand in der Statistik von Home Assistant gefallen <a name="ha_zaehler_rueckgang"></a>

**Was eedc sieht**
Die Summe eines Sensors in der Langzeitstatistik von Home Assistant ist in einer Stunde gefallen, statt zu steigen — meist,
weil der Wert in Home Assistant nachträglich zu weit nach unten angepasst wurde, oder weil der Sensor einen kleineren
Zählerstand gemeldet hat (typisch nach dem Neustart einer Integration, die ihren Zähler selbst hochrechnet). eedc
übernimmt die Statistik so, wie das Energie-Dashboard sie zeigt: der Rückgang steht als Abzug in Tag, Monat und Jahr, und
«Aus HA laden» schlägt für den Monat einen zu kleinen oder negativen Wert vor. Das ist kein Vorzeichen für Entladen oder
Einspeisen — jede Richtung hat ihr eigenes Feld. Die Meldung nennt je Sensor und Tag die Menge und die Stunde; geprüft
wird die ganze übernommene Statistik, nicht nur die letzten 30 Tage.

**Lösungsweg**
1. In Home Assistant unter *Entwicklerwerkzeuge → Statistik* den genannten Sensor suchen, beim Symbol „Wert anpassen“
   die genannte Stunde wählen und die Menge auf den echten Wert setzen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**. Ohne
   Klick gleicht eedc die berichtigte Statistik beim nächtlichen Abgleich von selbst ab.
3. Stammt der Rückgang von einem Sensor, den du inzwischen ersetzt hast (die Meldung sagt „Vorgänger-Sensor, zugeordnet
   bis …“): statt in Home Assistant zu berichtigen, in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die Operation «Werte vor dem
   Sensorbeginn verwerfen» ausführen.
4. Hast du einen betroffenen Monat schon gespeichert (mit «Aus HA laden» oder per Import), den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen und mit «Aus HA laden» neu übernehmen — ein
   gespeicherter Monat ändert sich nicht von allein.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Liste verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

**Was ohne Handlung gilt**
Der Rückgang zieht Tag, Monat und Jahr nach unten. eedc verwirft ihn nicht selbst: die Quelle ist die Statistik in Home
Assistant, und übernommen wird nur, was Home Assistant hat.

### 4.8d PV – Messpunkt (Anlagenzähler und Strings) <a name="48d-pv--messpunkt"></a>

Hast du neben den Zählern der einzelnen Strings (oder Module, Balkonkraftwerke) auch einen **Anlagenzähler** im Feld
„PV gesamt“ zugeordnet (in der Datenquellen-Zuordnung „PV-Erzeugung Zählerstand“), misst der eine Zähler **vor** dem
Wechselrichter (DC) und der andere **danach** (AC). Die Differenz zeigt eedc als **Wandlungsverluste**. Ersparnis,
Umsatzsteuer auf den Eigenverbrauch und CO₂ rechnen mit dem Eigenverbrauch **ohne** diese Verluste — eine im
Wechselrichter verlorene Kilowattstunde hättest du ohne PV-Anlage nie gekauft. Bilanz, Autarkie und
Eigenverbrauchsquote tragen sie weiter.

Abgezogen wird nur, was eedc sicher als Wechselrichterverlust **weiß**. Diese Kategorie nennt die Monate, in denen das
nicht gilt, und warum — dann zeigt eedc die Verluste an, bewertet sie aber nicht. Geprüft werden die abgeschlossenen
Monate, deren PV-Zähler eedc lückenlos kennt.

Die Schwellen (10 %, 80 %, 2 %) sind vorsichtig gesetzt und nicht an einer realen Anlage gemessen. Einen Knopf, der
etwas umrechnet, gibt es hier nicht: die Antwort ist eine Zuordnung in der Datenquellen-Zuordnung bzw. die Kopplung am
Speicher.

---

#### Anlagenzähler und String-Zähler messen verschiedene Dinge <a name="messpunkt_anlagenzaehler_vs_strings"></a>

**Was eedc sieht**
Geprüft werden abgeschlossene Monate, in denen der Anlagenzähler einen Wert hat und jede PV-Quelle einen eigenen Zähler.
In den genannten Monaten liegt die Summe der String-Zähler um mehr als 10 % über dem Anlagenzähler (Feld „PV gesamt“).
Wechselrichterverluste dieser Höhe sind nicht plausibel — meist misst der Anlagenzähler nicht dieselbe Anlage wie die
Strings: ein String fehlt in ihm, oder er misst nach dem Speicher. eedc zeigt die Differenz als Wandlungsverluste,
zieht sie in diesen Monaten aber nicht von Ersparnis, Umsatzsteuer und CO₂ ab.

**Lösungsweg**
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Prüfen, welcher Sensor dort steht: Er soll den Gesamtertrag aller Strings nach dem Wechselrichter zählen, nicht einen
   Teil der Anlage und nicht den Ausgang nach dem Speicher. Passt er nicht, den richtigen Zähler zuordnen; passt er,
   die Zähler der einzelnen PV-Module auf derselben Seite prüfen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile nennt nur noch Monate, in denen die Zähler weiter so
   weit auseinanderliegen.

**Was ohne Handlung gilt**
eedc zeigt die Differenz weiter als Wandlungsverluste an, bewertet sie in diesen Monaten aber nicht: Ersparnis,
Umsatzsteuer und CO₂ rechnen ohne Abzug. Bilanz, Autarkie und Eigenverbrauchsquote bleiben davon unberührt.

#### Der Anlagenzähler misst das Balkonkraftwerk offenbar nicht <a name="messpunkt_bkw_nicht_im_anlagenzaehler"></a>

**Was eedc sieht**
Geprüft werden abgeschlossene Monate, in denen der Anlagenzähler einen Wert hat, jede PV-Quelle einen eigenen Zähler und
das Balkonkraftwerk Erzeugung. In den genannten Monaten ist die Differenz zwischen den Zählern der PV-Quellen und dem
Anlagenzähler (Feld „PV gesamt“) fast so groß wie die Erzeugung des Balkonkraftwerks (mindestens 80 %). Das
Balkonkraftwerk speist dann offenbar an einer Stelle ein, die der Anlagenzähler nicht sieht. Neben großen Strings kann
ein sehr kleines Balkonkraftwerk diese Schwelle auch mit echten Verlusten erreichen.

**Lösungsweg**
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Klären, wo das Balkonkraftwerk einspeist: Liegt es außerhalb des Anlagenzählers, ist der Befund richtig und es ist
   nichts zu ändern. Misst dein Anlagenzähler das Balkonkraftwerk doch mit, auf derselben Seite den Zähler des
   Balkonkraftwerks prüfen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile nennt nur noch Monate, in denen die Differenz weiter so
   groß ist.

**Was ohne Handlung gilt**
eedc zieht in diesen Monaten nichts als Wandlungsverluste ab — sonst wäre die Ersparnis des Balkonkraftwerks weg. Die
Differenz wird angezeigt, aber nicht bewertet.

#### Anlagenzähler zählt mehr als die Strings <a name="messpunkt_zaehler_mehr_als_strings"></a>

**Was eedc sieht**
In den genannten Monaten liegt der Anlagenzähler (Feld „PV gesamt“) um mehr als 2 % über der Summe der String-Zähler.
Nach dem Wechselrichter kann nicht mehr ankommen, als die Strings davor liefern — meist zählt der Anlagenzähler eine
weitere Quelle mit (ein Balkonkraftwerk, ein zweiter Wechselrichter), oder ein String-Zähler misst zu wenig.
Geprüft werden abgeschlossene Monate, in denen der Anlagenzähler einen Wert hat und jede PV-Quelle einen eigenen Zähler.
Bei einem DC-gekoppelten Speicher schweigt die Prüfung: Der Anlagenzähler zählt dann die Netzladung der Batterie mit.

**Lösungsweg**
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Prüfen, was der Sensor dort mitzählt: Zählt er eine weitere Quelle mit, braucht diese Quelle einen eigenen Eintrag
   unter den Komponenten mit eigenem Zähler; misst ein String zu wenig, dessen Zähler beim PV-Modul prüfen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile nennt nur noch Monate, in denen der Anlagenzähler
   weiter vorn liegt.

**Was ohne Handlung gilt**
eedc rechnet in diesen Monaten mit der Summe der Strings; Wandlungsverluste gibt es dort keine.

#### DC-Speicher: der AC-Zähler misst die Batterie mit <a name="messpunkt_dc_speicher"></a>

**Was eedc sieht**
Bei einem DC-gekoppelten Speicher misst der Anlagenzähler (nach dem Wechselrichter) Ladung und Entladung der Batterie
mit — die Differenz zu den String-Zählern ist dann nicht nur Wandlungsverlust. Ist die Kopplung am Speicher nicht
eingetragen, nimmt eedc DC an, sobald der Speicher einem Wechselrichter zugeordnet ist; die Meldung sagt dann dazu, dass
die Kopplung fehlt.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — die Seite «Komponenten» öffnet sich; dort beim Speicher das Stift-Symbol
   «Bearbeiten» klicken.
2. Im Feld «Kopplung» eintragen, wie dein Speicher angeschlossen ist: «AC-gekoppelt» oder «DC-gekoppelt». Speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — mit «AC-gekoppelt» verschwindet die Zeile; mit «DC-gekoppelt»
   bleibt sie als Auskunft stehen.

**Was ohne Handlung gilt**
eedc zeigt die Differenz als Verluste an, bewertet sie aber nicht: Ersparnis, Umsatzsteuer und CO₂ rechnen ohne Abzug.

#### „PV gesamt“ gilt als Zähler einschließlich Balkonkraftwerk <a name="messpunkt_pv_gesamt_inkl_bkw"></a>

**Was eedc sieht**
Dem Anlagenzähler (Feld „PV gesamt“) ist ein Sensor zugeordnet, mindestens ein aktives PV-Modul hat keinen eigenen Zähler
und mindestens ein Balkonkraftwerk hat einen. eedc liest den Anlagenzähler dann als Zähler der ganzen Erzeugung
einschließlich Balkonkraftwerk und verteilt seinen Rest nach dem Zähler des Balkonkraftwerks auf die PV-Module ohne
Zähler. Die Meldung nennt beide. Ein Modul, das zum Balkonkraftwerk selbst gehört, zählt nicht als Modul ohne Zähler.

**Lösungsweg**
1. Klären, was dein Anlagenzähler misst (der Knopf **«Was gilt»** am Befund öffnet diesen Text): Zählt er die ganze
   Erzeugung einschließlich Balkonkraftwerk, stimmt die Rechnung, und es ist nichts zu tun.
2. Misst er nur den Wechselrichter: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) den Sensor aus
   „PV-Erzeugung Zählerstand“ herausnehmen und beim PV-Modul im Feld „PV-Erzeugung“ zuordnen — ein Sensor in zwei
   Feldern zählt doppelt. Sonst fehlt die Erzeugung der Balkonkraftwerke in PV gesamt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein PV-Modul ohne eigenen Zähler neben
   dem Anlagenzähler steht.

**Was ohne Handlung gilt**
eedc verteilt den Rest des Anlagenzählers nach dem Zähler des Balkonkraftwerks auf die Module ohne Zähler. Misst der
Anlagenzähler nur den Wechselrichter, fehlt die Erzeugung des Balkonkraftwerks in PV gesamt. Die Messpunkt-Prüfungen
schweigen in dieser Lage, weil der verteilte Rest die Differenz verdeckt.

#### Volleinspeisung ohne AC-Ertragszähler <a name="messpunkt_volleinspeisung_ac_zaehler_fehlt"></a>

**Was eedc sieht**
Es gibt keinen Anlagenzähler, und in den letzten drei abgeschlossenen Monaten ging fast die ganze Erzeugung der
String-Zähler ins Netz. Was dazwischen fehlt, sind bei einer Volleinspeisung vor allem die Verluste im Wechselrichter —
die kennt eedc nur mit einem Zähler nach dem Wechselrichter.

**Lösungsweg**
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Dort den AC-Ertragszähler deines Wechselrichters (Gesamtertrag nach dem Wechselrichter) zuordnen. Denselben Sensor
   zusätzlich als Einspeisung zuzuordnen ist nicht der Weg — das meldet die Datenquellen-Prüfung als Doppelzählung.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc kennt die Wandlungsverluste nicht und rechnet deshalb auch aus ihnen eine Ersparnis — sie zählen, als wären sie
im Haus verbraucht worden.

### 4.8e PV – Zähler steht <a name="48e-pv--zaehler-steht"></a>

Ein PV-Gesamtzähler (Feld „PV gesamt“), der **eingefroren** ist — der Sensor meldet weiter, aber sein Stand bewegt sich
nicht —, sieht für eedc aus wie ein Zähler ohne Erzeugung. Läuft dabei die Einspeisung weiter, passt die Tagesbilanz
nicht mehr zusammen, und Tages- und Monatsansicht im Cockpit zeigen unplausible Werte, etwa eine **negative Autarkie**.
eedc rechnet diese Werte bewusst so, wie sie gemessen sind, und biegt sie nicht zurecht; diese Kategorie nennt die
Ursache.

Geprüft werden die letzten 31 abgeschlossenen Tage des Anlagenzählers „PV gesamt“, soweit eedc ihn lückenlos kennt. Die
Zähler einzelner Strings prüft diese Kategorie nicht: steht ein String, während die anderen erzeugen, ist das meist
Teilbeschattung oder Schnee auf einem Teil der Module — eine richtige Messung.

**Was diese Meldung bewusst nicht auslöst** — das sind richtige Messungen:

- ein Einspeisezähler, der steht, während die PV erzeugt (**Nulleinspeisung**, Wintertage mit 100 % Eigenverbrauch);
- ein Netzbezugszähler, der steht (**autarke Tage** mit Speicher);
- ein PV-Zähler, der steht, während nur der Netzbezug läuft (**Schnee** auf den Modulen);
- ein einzelner String-Zähler, der steht, während die anderen erzeugen (**Teilbeschattung**, Schnee auf einem Teil der
  Module);
- ein Speicher, der bei PV 0 ins Netz entlädt — seine Entladung wird abgezogen. Hat dein Speicher keinen
  Entladungs-Zähler, nimmt eedc die Einspeisung gar nicht als Vergleich.

---

#### PV-Zähler steht, obwohl erzeugt wird <a name="pv_zaehler_steht"></a>

**Was eedc sieht**
Der Anlagenzähler (Feld „PV gesamt“) hat sich mindestens drei volle Tage nicht bewegt, während im selben Zeitraum erzeugt
wurde: die Einspeisung wuchs um mehr als die Entladung deiner Speicher und die Erzeugung der Balkonkraftwerke mit eigenem
Zähler, oder die String-Zähler, die er mitmisst, erzeugten im Mittel mehr als 0,5 kWh am Tag. Ohne Erzeugung kann das
nicht sein — meist liefert der Sensor einen eingefrorenen Wert (Integration hängt, Gerät nicht erreichbar, Zähler
zurückgesetzt). Geprüft werden die letzten 31 abgeschlossenen Tage.

**Lösungsweg**
1. Den Sensor in Home Assistant prüfen (im Standalone-Betrieb das MQTT-Topic): Hängt die Integration, ist das Gerät
   erreichbar, wurde der Zähler zurückgesetzt? Der Knopf **«Was gilt»** am Befund öffnet diesen Text.
2. Liefert der Sensor wieder Werte, zählen die folgenden Tage richtig. Die Tage, an denen er stand, berichtigst du bei
   Bedarf in Home Assistant unter *Entwicklerwerkzeuge → Statistik* mit „Wert anpassen“.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange der Stillstand in den geprüften
   31 Tagen liegt.

**Was ohne Handlung gilt**
eedc rechnet an diesen Tagen mit „keine Erzeugung“ und biegt nichts zurecht; Tages- und Monatsansicht im Cockpit zeigen
deshalb unplausible Werte, etwa eine negative Autarkie. Nulleinspeisung, autarke Tage, Schnee auf den Modulen oder ein
einzelner stehender String lösen diese Meldung nicht aus.

### 4.9 Datenquellen – HA-Statistics <a name="49-sensor-mapping--ha-statistics"></a>

> **Variantenhinweis:** Diese Kategorie greift nur im **HA Add-on**. Im Standalone-Betrieb gibt es keine HA-Long-Term-Statistics; der Kopf des Daten-Checkers zählt die Prüfung dann als nicht ausführbar (siehe §4.9a). Im Standalone-Betrieb gibt es keine Entsprechung dieser Prüfung; §4.8 *MQTT-Topic-Abdeckung* prüft nur, ob die Topics ankommen. Ist Home Assistant im Add-on zwischenzeitlich nicht erreichbar, wird die Kategorie ebenso übersprungen — dann die [HA-Verbindung](HANDBUCH_EINSTELLUNGEN.md#62-ha-verbindung) unter *Einstellungen → Integration → HA-Verbindung* prüfen.

**Was wird geprüft:** Liefert jeder zugeordnete HA-Sensor tatsächlich Long-Term-Statistics nach Home Assistant? Geprüft werden alle zugeordneten kWh-Felder — Einspeisung, Netzbezug, **PV Erzeugung Gesamt** und die Komponenten-Felder —, die Zähler-Felder (z. B. WP-Kompressor-Starts) und die Zählerstand-Felder. Reine Live-Felder (W, %, °C) bleiben außen vor, sie lesen den Momentanwert und brauchen keine Statistik. Beim Gesamt-PV-Zähler prüft eedc die **Zuordnung**, nicht ob die Rechnung ihn diesen Monat gerade liest: fällt ein String-Sensor aus, wird er unmittelbar wieder zur einzigen Quelle. Sensoren ohne `state_class` haben keine LTS-Einträge, und damit greifen die **Reparatur-Werkzeuge in der Energieprofil-Pflege** (Lücken aus HA-LTS nachfüllen, Tag/Bereich neu aggregieren) nicht — sie lesen alle aus HA-LTS. Live-Anzeigen funktionieren weiter (über `state`), aber jeder Aussetzer im Snapshot-Pfad ist permanent verloren, weil er nicht aus LTS nachgeholt werden kann.

Der Sensor-Picker in den Datenquellen zeigt alle Sensoren ohne harten Filter — damit lassen sich z. B. Nibe-Roh-Counter ohne Metadaten zuordnen, aber genau dieser Spielraum verlangt nach dieser Prüfkategorie. (Der Picker warnt beim Zuordnen bereits vor fehlender Langzeitstatistik — siehe [HANDBUCH_EINSTELLUNGEN.md §7.6](HANDBUCH_EINSTELLUNGEN.md#76-validierung--probleme-je-feld).)

**Der übliche Weg ist ein Verbrauchszähler-Helfer in Home Assistant** (§5.1), angelegt unter *Einstellungen → Geräte & Dienste → Helfer*, **ohne Zyklus**: Er bringt die Statistik-Angaben und die Summen-Spalte mit. Ein **Zählerstand** ist eine Bestandsgröße und kommt aus dem Sensor-Zustand — für ihn genügt `state_class: measurement`, eine Summen-Spalte braucht er nicht.

> **Wichtige Lektion:** Frühere Hinweistexte sagten „vergangene Tage bleiben leer". Das ist irreführend, weil HA-Long-Term-Statistics ohnehin erst ab Aktivierung von `state_class` angelegt werden — vor der Aktivierung existieren keine Werte zum Holen, egal auf welchem Weg du den Zähler in Ordnung bringst. Der eigentliche Schmerzpunkt ist daher: ohne `state_class` **wirken die Reparatur-Werkzeuge in der Energieprofil-Pflege nicht**. Ab Aktivierung läuft's lückenfrei, davor bleibt's leer.

---

#### kWh-Sensoren nicht in der Langzeitstatistik von Home Assistant <a name="kwh_sensoren_nicht_in_lts"></a>

**Was eedc sieht**
Mindestens ein zugeordneter kWh-Sensor (etwa für Einspeisung, PV Erzeugung Gesamt oder den Stromverbrauch der Wärmepumpe)
hat in Home Assistant keine `state_class` — typisch bei Modbus-Rohwerten oder Hersteller-Integrationen ohne Angaben dazu.
Home Assistant führt für ihn keine Langzeitstatistik, und alle Reparatur-Werkzeuge der Reparatur-Werkbank lesen genau dort:
Für diese Felder wirken sie nicht. Jeder Aussetzer bleibt verloren. Die Details nennen die betroffenen Sensoren.

**Lösungsweg**
1. Bevorzugt in Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor
   anlegen, Zurücksetzen „nie“ (ohne Zyklus). Der Helfer bringt die nötigen Statistik-Angaben mit und behält seinen Namen
   auch nach einem Gerätetausch.
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen, oder einen anderen Sensor, der schon `state_class: total_increasing` trägt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor in der
   Langzeitstatistik steht.

**Was ohne Handlung gilt**
Live-Anzeigen funktionieren weiter. Die Reparatur-Werkzeuge wirken für diese Felder nicht, und eine Lücke bleibt eine Lücke.
Vergangenes sammelt Home Assistant auch nach der Umstellung nicht nach: Die Reihe beginnt ab der Umstellung.

#### Zähler-Sensoren ohne state_class — Reparatur-Werkzeuge wirken nicht <a name="counter_ohne_state_class"></a>

**Was eedc sieht**
Zähler-Felder wie die Kompressor-Starts einer Wärmepumpe liest eedc stündlich mit, und das funktioniert live. Ohne
`state_class` führt Home Assistant für sie aber keine Langzeitstatistik — die Reparatur-Werkzeuge der Reparatur-Werkbank
lesen genau dort und greifen nicht. Jeder Aussetzer (Neustart, hängende Abfrage) bleibt verloren; im Normalbetrieb fehlt
zusätzlich häufig die letzte Stunde des Tages (23–24 Uhr). Die Details nennen die betroffenen Sensoren.

**Lösungsweg**
1. In Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor anlegen,
   Zurücksetzen „nie“ (ohne Zyklus). Wer die YAML ohnehin pflegt, kann `state_class` stattdessen per `customize` ergänzen.
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor in der
   Langzeitstatistik steht.

**Was ohne Handlung gilt**
Die Zähler laufen live weiter; Aussetzer lassen sich nicht nachholen. Die Historie des Helfers beginnt bei null —
Vergangenes sammelt Home Assistant nicht nach.

#### kWh-Sensoren ohne Summen-Spalte — Tages- und Stundenwerte bleiben leer <a name="kwh_ohne_summen_spalte"></a>

**Was eedc sieht**
Diese kWh-Sensoren stehen in der Langzeitstatistik von Home Assistant, aber mit `state_class: measurement` statt
`total_increasing`. Home Assistant führt dann nur Mittel-, Minimal- und Maximalwerte und keine Zählerstände — eedc kann
daraus keine Stunden- und Tagesmengen bilden. Die Live-Ansicht ist nicht betroffen, sie rechnet aus den Watt-Sensoren;
deshalb stehen dort Werte, während die Tagesansicht im Cockpit und die Stundenwerte 0 zeigen.

**Lösungsweg**
1. In Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor anlegen,
   Zurücksetzen „nie“ (ohne Zyklus) — er führt die Summen-Spalte. Wer die YAML ohnehin pflegt, kann stattdessen
   `state_class: total_increasing` per `customize` setzen (Neustart von Home Assistant nötig).
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen.
3. Die Tage danach in der [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) mit «Mehrere
   Tage neu aggregieren» neu berechnen — Home Assistant sammelt die Summenwerte erst ab der Umstellung.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor eine
   Summen-Spalte hat.

**Was ohne Handlung gilt**
Tagesansicht im Cockpit und Stundenwerte bleiben für diese Felder auf 0, die Live-Ansicht zeigt weiter Werte. Vergangenes
sammelt Home Assistant nicht nach.

#### Zähler-Sensoren ohne Summen-Spalte — Reparatur-Werkzeuge wirken nicht <a name="counter_ohne_summen_spalte"></a>

**Was eedc sieht**
Diese Zähler-Felder liest eedc stündlich mit, und der laufende Betrieb funktioniert. Ihr `state_class` ist aber
`measurement` statt `total_increasing`, deshalb führt Home Assistant für sie keine Summen-Spalte — und alle
Reparatur-Werkzeuge der Reparatur-Werkbank lesen genau die. Ein Aussetzer lässt sich damit nicht nachholen. Die Details
nennen die betroffenen Sensoren.

**Lösungsweg**
1. In Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor anlegen,
   Zurücksetzen „nie“ (ohne Zyklus) — er führt die Summen-Spalte und behält seinen Namen auch nach einem Gerätetausch. Wer
   die YAML ohnehin pflegt, kann stattdessen `state_class: total_increasing` per `customize` setzen (Neustart von Home
   Assistant nötig).
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor eine
   Summen-Spalte hat.

**Was ohne Handlung gilt**
Der laufende Betrieb erfasst die Zähler weiter; Aussetzer bleiben verloren. Die Historie des Helfers beginnt bei null —
Vergangenes sammelt Home Assistant nicht nach.

#### Zählerstand-Sensoren nicht in der Langzeitstatistik von Home Assistant <a name="stand_sensoren_nicht_in_lts"></a>

**Was eedc sieht**
Für diese Zählerstand-Sensoren führt Home Assistant keine Langzeitstatistik — meist fehlt `state_class`. eedc liest den
Zählerstand stündlich genau dort; deshalb wird für diese Zähler gar kein Stand mitgeschrieben: Anfang, Ende und Verbrauch des
Zeitraums bleiben leer, ohne dass sonst etwas darauf hinweist. Die Details nennen die betroffenen Sensoren.

**Lösungsweg**
1. In Home Assistant für diesen Sensor `state_class` ergänzen (etwa per `customize`). Ein Zählerstand ist eine Bestandsgröße:
   `measurement` genügt — `total_increasing` oder ein Verbrauchszähler-Helfer sind dafür nicht nötig.
2. Oder am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld;
   dort einen Sensor wählen, der `state_class` mitbringt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor in der
   Langzeitstatistik steht.

**Was ohne Handlung gilt**
Für diese Zähler bleibt der Stand leer. Vergangenes sammelt Home Assistant nicht nach: Die Reihe beginnt ab der Umstellung.

#### Alle kWh- und Zählerstand-Sensoren in der Langzeitstatistik <a name="stand_sensoren_ok"></a>

**Was eedc sieht**
Die Zeile erscheint für die Gruppe, die vollständig in der Langzeitstatistik von Home Assistant steht — kWh-Sensoren,
Zählerstand-Sensoren oder beide; die Zeile nennt die Zahlen. Die Zähler-Felder (Kompressor-Starts, Betriebsstunden)
zählt sie nicht mit. Für die kWh-Sensoren wirken damit die Reparatur-Werkzeuge auf alle Felder. Für einen Zählerstand
wird bewusst keine Summen-Spalte verlangt — er kommt aus dem Sensor-Zustand, nicht aus einer Verbrauchssumme.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie.

**Was ohne Handlung gilt**
eedc liest Zählerstände und Mengen weiter aus der Statistik von Home Assistant; Lücken lassen sich von dort nachholen.

### 4.9a Datenquellen – Status (Kategorie „Datenquelle – aktiver Pfad“) <a name="49a-datenquellen--status"></a>

> **Variantenhinweis:** Die Kategorie meldet in beiden Varianten genau einen Befund: welcher Weg die Tages- und Stundenwerte zuletzt
> geschrieben hat. Im **HA Add-on** ist das die HA-Langzeitstatistik oder der HA-Spiegel (Kanal-Tag), im **Standalone-Betrieb** der
> Snapshot-Pfad. Ist keine Langzeitstatistik erreichbar, laufen auch die Prüfungen gegen Home Assistant nicht (Sensoren in der
> Langzeitstatistik, Abweichung zu Home Assistant) — der Kopf des Daten-Checkers zählt sie als nicht ausführbar.

**Was wird geprüft:** die Herkunft der jüngsten Tageszeile mit Stundenwerten (die häufigste Quelle ihrer Felder) und ob Home Assistant
erreichbar ist.

---

#### Tageswerte kommen aus der Langzeitstatistik von Home Assistant <a name="datenquelle_ha_lts_ok"></a>

**Was eedc sieht**
Die jüngste Tageszeile mit Stundenwerten stammt direkt aus der Langzeitstatistik von Home Assistant. Stunden- und Tageswerte
passen damit zusammen: Die Summe der Stunden ist der Tag.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

**Was ohne Handlung gilt**
Tag und Stunde kommen weiter aus der Statistik von Home Assistant.

#### Tageswerte kommen aus dem gespiegelten Home-Assistant-Zähler <a name="datenquelle_kanal_ok"></a>

**Was eedc sieht**
Tag und Stunde der jüngsten Tageszeile kommen aus dem Zähler, den eedc aus Home Assistant spiegelt. Stunden- und Tageswerte
passen damit zusammen: Die Summe der Stunden ist der Tag.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

**Was ohne Handlung gilt**
Tag und Stunde kommen weiter aus dem gespiegelten Zähler.

#### Noch keine Tageswerte <a name="datenquelle_noch_keine_tageswerte"></a>

**Was eedc sieht**
Home Assistant ist erreichbar, aber es gibt noch keine Tageszeile mit Stundenwerten. Direkt nach der Einrichtung ist das
normal — die ersten Werte stehen innerhalb einer Stunde bereit. Bleibt es dabei, fehlt meist die Zuordnung der
kWh-Zähler: Es müssen die kWh-Zeilen belegt sein, nicht nur die Watt-Zeilen.

**Lösungsweg**
1. Nach der Einrichtung zuerst den nächsten Lauf abwarten.
2. Bleibt die Zeile: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) die kWh-Zähler zuordnen
   (Einspeisung, Netzbezug, PV und die Komponenten).
3. Zurückliegende Tage holt in der [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die
   Operation «Lücken aus HA-LTS nachfüllen».
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — statt dieser Zeile nennt die Kategorie die aktive Quelle als
   bestanden.

**Was ohne Handlung gilt**
Ohne Tageszeilen bleiben die Tagesansicht im Cockpit, die Stundenwerte und das Energieprofil leer.

#### Tageswerte stammen noch aus einer älteren Quelle <a name="datenquelle_aggregate_aeltere_quelle"></a>

**Was eedc sieht**
Die Langzeitstatistik von Home Assistant ist erreichbar, die jüngste Tageszeile wurde aber noch auf einem anderen Weg
geschrieben, etwa beim Monatsabschluss. Die Meldung nennt das Datum und die Quelle. Sobald diese Tage neu aus der Statistik
aufgebaut sind, gilt sie als Quelle.

**Lösungsweg**
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc baut die jüngsten Tage bis zum
   genannten Tag (höchstens 31 Tage, höchstens bis gestern) aus der Statistik neu auf. Der Bereich beginnt und endet an
   einem Tag aus eedcs eigener Erfassung; Tage dazwischen, die eedc direkt aus Home Assistant führt, behalten ihre
   Mengen — die Vorschau nennt sie.
2. Steht am Befund kein solcher Knopf, gibt es in diesem Fenster keinen Tag, den eedc neu aufbauen müsste. Einen einzelnen
   Tag baut in der [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die Operation «Tag neu
   aggregieren» neu auf.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — statt dieser Zeile nennt die Kategorie die Statistik von Home
   Assistant als aktive Quelle.

**Was ohne Handlung gilt**
Die Tage behalten ihre Werte aus der älteren Quelle; der Monatsabschluss rechnet nur Tage nach, die noch fehlen. Neu baut
sie erst «Tage neu aufbauen» am Befund oder «Tag neu aggregieren» in der Reparatur-Werkbank.

#### Betrieb ohne Langzeitstatistik von Home Assistant <a name="betriebsart_standalone"></a>

**Was eedc sieht**
eedc erreicht keine Langzeitstatistik von Home Assistant — im Standalone-Betrieb ohne Home Assistant ist das der Normalfall,
im Add-on heißt es, dass die Verbindung gerade nicht steht. Tages- und Stundenwerte entstehen dann aus den
5-Minuten-Messungen von eedc. Die Prüfungen gegen Home Assistant (Sensoren in der Langzeitstatistik, Abweichung zu Home
Assistant) laufen deshalb nicht; der Kopf des Daten-Checkers zählt sie als nicht ausführbar.

**Lösungsweg**
1. Standalone ohne Home Assistant: nichts zu tun — die Prüfungen gegen Home Assistant haben hier kein Gegenstück; die
   Kategorie «MQTT – Topic-Abdeckung» prüft dort die Zuordnung.
2. Im Add-on oder mit Zugriffstoken: unter [HA-Verbindung](eedc:/einstellungen/integration?block=ha-verbindung) prüfen, ob
   die Verbindung zu Home Assistant steht.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange keine Langzeitstatistik erreichbar ist;
   mit erreichbarem Home Assistant nennt die Kategorie die aktive Quelle, und die übersprungenen Prüfungen laufen wieder.

**Was ohne Handlung gilt**
eedc rechnet weiter aus seinen 5-Minuten-Messungen; mit der Langzeitstatistik von Home Assistant wäre die Summe der Stunden
genau der Tag. Die Prüfungen gegen Home Assistant bleiben übersprungen.

### 4.10 Energieprofil – fehlende Tageswerte <a name="410-energieprofil--fehlende-tageswerte"></a>

> **Variantenhinweis:** Nur im **HA Add-on** (bzw. Docker mit HA-Recorder-Zugriff). Im Standalone-Betrieb fehlt die unabhängige Referenz, gegen die eedc prüfen könnte — die Kategorie wird dann still übersprungen.

**Was wird geprüft:** Gibt es in den letzten 90 Tagen Tage, an denen ein Zähler zugeordnet ist und die **HA-Langzeitstatistik einen Wert liefert**, die gespeicherte Tageszeile aber leer oder 0 ist? Das ist der typische Fall nach einer nachträglich korrigierten Zuordnung: die Zuordnung steht heute, aber für die Tage davor hat nie ein Aggregator-Lauf stattgefunden. Die Zähler-Abdeckung (§4.6) meldet dort völlig zu Recht „OK" — der Zähler *ist* ja zugeordnet.

**Nur Zeiträume, in denen die Komponente auch gelaufen ist.** Die Prüfung fordert für jeden Tag genau das ein, was der Reparatur-Lauf an diesem Tag auch schreiben darf: Komponenten, die an dem Tag noch nicht angeschafft, bereits stillgelegt oder auf *inaktiv* gesetzt waren, tauchen für diesen Zeitraum nicht auf. Die Anlagen-Grenze wirkt genauso: vor dem Inbetriebnahme-Datum wird nichts eingefordert.

**Kein Knopf ohne Deckung.** Braucht der Tages-Lauf für diese Anlage etwas, das nicht da ist — eine Leistungs-Zuordnung (W) bzw. MQTT-Energie —, dann erscheint der Befund weiterhin, aber **ohne** Reparatur-Knopf; er springt stattdessen mit «Sensor zuordnen» auf das Feld, das zuerst zuzuordnen ist, und Einzeltag-Zeilen entfallen.

**Tage aus dem HA-Spiegel** bzw. den eigenen Zählerständen vergleicht die Prüfung mit den Mengen, die die Tagesansicht im Cockpit dort zeigt (PV, Netz und Speicher aus dem Spiegel) — eine leere gespeicherte Tageszeile ist an einem solchen Tag kein Befund; Wärmepumpe, Wallbox und Sonstiges ohne Kanal prüft sie wie bisher.

**Reichweite:** Die Tagesreparatur heilt Tages- und Stundenwerte, **nicht** die Monatswerte. Für abgeschlossene Monate danach *Einstellungen → Integration → Statistik-Import*.

> **Abgrenzung:** PV-Werte auf einer *bestehenden* Tageszeile gehören der Drift-Prüfung (§4.17) — kein zweiter Turm über denselben Sachverhalt. Der Speicher-Netto-Wert (`batterie_*`) bleibt hier außen vor, er darf legitim ~0 sein.

---

#### Keine reparierbaren Tages-Lücken <a name="tageswerte_ok"></a>

**Was eedc sieht**
In den letzten 90 Tagen trägt jeder Tag mit zugeordnetem Zähler einen Wert. Oder es gibt leere Tage, aber Home Assistant hat
für sie ebenfalls nichts — die Zeile sagt dann «Keine reparierbaren Tages-Lücken gefunden». Solche Lücken sind keine
Fehlfunktion: eedc reicht nur so weit zurück wie Home Assistant selbst.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

**Was ohne Handlung gilt**
Tage, für die auch Home Assistant nichts hat, bleiben leer; sie lassen sich nicht mehr füllen.

#### Tage ohne Werte trotz zugeordnetem Zähler <a name="tageswerte_fehlen_tage"></a>

**Was eedc sieht**
In den letzten 90 Tagen gibt es Tage, an denen ein Zähler zugeordnet ist und die Langzeitstatistik von Home Assistant
für ihn mindestens 1 kWh hat, die gespeicherte Tageszeile in eedc aber leer ist. Das ist der typische Fall nach einer
nachträglich korrigierten Zuordnung: Die Zuordnung steht heute, für die Tage davor hat sie nie jemand aufgeschrieben.
Die Meldung nennt den Zeitraum, die Details die betroffenen Komponenten.

**Lösungsweg**
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt die Tage aus der Statistik
   von Home Assistant nach, höchstens 31 Tage je Lauf; ältere Tage bleiben für einen zweiten Lauf stehen. Einzelne Tage baut
   die Zeile «… Tage ohne Tageswerte, Home Assistant hat Werte» mit einem Glied je Tag neu auf.
2. Steht am Befund stattdessen **«Sensor zuordnen»**, kann eedc die Tage noch nicht nachholen: Der Tages-Lauf braucht
   zusätzlich eine Leistungs-Zuordnung (W). Der Knopf öffnet die
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen?feld=netzbezug_w) am Feld «Netzbezug» — dort einen
   Leistungssensor zuordnen; danach erscheint am Befund der Knopf aus Schritt 1.
3. Die Tagesreparatur heilt Tages- und Stundenwerte, nicht die Monatswerte. Für abgeschlossene Monate danach im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) **«Vorschau laden»** — bereits belegte
   Monate stehen dort unter «Konflikte» und sind zum Überschreiben vorausgewählt, also vor dem Import einmal durchsehen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgeholten Tage sind aus der Zeile verschwunden; nennt die
   Meldung ältere oder noch nicht geprüfte Tage, den Knopf ein weiteres Mal anwenden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

**Was ohne Handlung gilt**
Die Tage bleiben in eedc leer: Tagesansicht im Cockpit, Stundenwerte und Energieprofil zeigen für sie nichts, obwohl Home
Assistant Werte hat. Die Monatswerte sind davon nicht berührt.

#### Ein Tag ohne Tageswerte, Home Assistant hat Werte <a name="tageswerte_fehlen_tag"></a>

**Was eedc sieht**
Für diesen Tag ist die gespeicherte Tageszeile leer, die Langzeitstatistik von Home Assistant hat aber Werte — die Meldung
nennt sie je Komponente. Mehrere solche Tage stehen als eine Zeile «n Tage ohne Tageswerte, Home Assistant hat Werte» mit
einem Glied je Tag; jedes Glied baut genau diesen Tag neu auf.

**Lösungsweg**
1. Am Befund (oder am Glied des Tages) **«Tag neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt
   Tages- und Stundenwerte dieses Tages aus der Statistik von Home Assistant nach.
2. Die Monatswerte schreibt der Knopf nicht. Ist der Monat schon abgeschlossen, ihn danach im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) mit **«Vorschau laden»** neu übernehmen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

**Was ohne Handlung gilt**
Der Tag bleibt in eedc leer; Tagesansicht im Cockpit, Stundenwerte und Energieprofil zeigen für ihn nichts, obwohl Home
Assistant Werte hat.

### 4.11 Geräte-Connector ohne Monatswert <a name="411-geraete-connector-ohne-monatswert"></a>

> **Variantenhinweis:** Nur relevant, wenn ein **Geräte-Connector** eingerichtet ist. Ohne Connector wird die Kategorie still übersprungen — sie meldet nie etwas, das du nicht auflösen könntest.
>
> ⚠ **Ein Cloud-Import ist kein Geräte-Connector.** Beide stehen unter *Einstellungen → Integration → Import-Assistenten*, sind aber verschiedene Dinge: Der **Geräte-Connector** spricht deinen Wechselrichter **im eigenen Netz** über seine lokale Schnittstelle an; ein **Cloud-Import** (Fronius Solar.web, SolarEdge, Growatt, EcoFlow …) holt Daten vom **Portal des Herstellers**. Wer nur einen Cloud-Import eingerichtet hat, bekommt hier **keinen** Befund.

**Was wird geprüft:** Kann eedc aus den gespeicherten Zählerständen des Connectors für den **laufenden Monat** überhaupt einen Wert bilden? Ein Connector-Wert ist immer die **Differenz zweier Snapshots** — einer muss vor dem Monatsbeginn liegen, einer danach. Fehlt einer davon, liefert der Connector für diesen Monat gar nichts, und das wäre sonst nirgends zu sehen: In der Monatsansicht im Cockpit stünde einfach eine Quelle weniger, ohne Hinweis darauf, dass eine eingerichtete Quelle gerade schweigt.

**Kein Lärm am Monatsersten.** Solange der Connector aktiv liefert, fehlt ihm am 1. eines Monats bis zum ersten Abruf naturgemäß der Snapshot *im* Monat. Dieser Zustand erledigt sich innerhalb eines Tages und wird deshalb nicht gemeldet — der Befund erscheint erst, wenn der jüngste Zählerstand älter als zwei Tage ist (oder es überhaupt erst einen gibt).

> **Abgrenzung:** Liefert der Connector einen Wert, misst er aber nur einen **Teil** des Monats (frisch eingerichtet), ist das kein Befund — dort steht eine Zahl, und sie wird in der Monatsansicht im Cockpit mit ihrem Zeitraum beschriftet: „Connector (28.–30.07.2025)". Siehe [HANDBUCH_BEDIENUNG.md §2.3](HANDBUCH_BEDIENUNG.md#23-monat).

---

#### Geräte-Connector liefert für den laufenden Monat keinen Wert <a name="connector_monatswert_fehlt"></a>

**Was eedc sieht**
Ein Connector-Wert ist immer die Differenz zweier verschiedener gespeicherter Zählerstände — der erste vor dem Monat oder
im Monat, der zweite im Monat oder danach. Für den laufenden Monat fehlt der zweite: Entweder gibt es bisher erst einen
Zählerstand, oder der jüngste ist mindestens zwei Tage alt, weil der tägliche Abruf nichts Neues bringt. Die Details nennen den Bestand und wann der Abruf zuletzt lief. In
der Monatsansicht im Cockpit fehlt der Connector dann als Quelle, ohne dass es sonst jemand sagt.

**Lösungsweg**
1. Am Befund **«Zum Connector»** klicken — der Assistent «Geräte-Connector» öffnet sich.
2. Prüfen, ob das Gerät im Netz erreichbar ist und die Zugangsdaten noch gelten, dann mit **«Jetzt ablesen»** den Zähler
   von Hand ablesen. Scheitert der Abruf, steht der Grund dort und im Aktivitätsprotokoll unter
   [Protokolle](eedc:/einstellungen/system?block=protokolle), Reiter «Aktivitäten».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — sobald für den Monat ein zweiter, davon verschiedener
   Zählerstand vorliegt, ist die Zeile verschwunden.

**Was ohne Handlung gilt**
Der tägliche Abruf läuft bei jedem eingerichteten Connector um 3:30 Uhr weiter, er lässt sich weder ein- noch ausschalten;
kommt ein neuer Zählerstand dazu, verschwindet der Befund von selbst. Bis dahin rechnet der Monat ohne den Connector.

### 4.12 Zeitzone – Abweichung zu Home Assistant <a name="412-zeitzone--abweichung-zu-home-assistant"></a>

> **Variantenhinweis:** Nur relevant, wenn eine Verbindung zu Home Assistant besteht — als Add-on oder per Zugriffstoken. Ohne HA-Verbindung wird die Kategorie still übersprungen: Es gäbe nichts zu vergleichen und nichts zu tun.

**Was wird geprüft:** Rechnen eedc und Home Assistant mit derselben Uhrzeit? Verglichen wird der **aktuelle UTC-Abstand** beider Systeme, nicht der Name der Zeitzone — Wien, Zürich und Amsterdam gehen genauso wie Berlin, und dort wäre eine Meldung falsch.

**Warum das zählt:** Läuft eedc in einem Container ohne gesetzte Zeitzone, arbeitet er auf UTC. Der Tag endet dann für eedc um 22:00 Ortszeit, und die letzten Stunden werden dem Folgetag zugerechnet. Betroffen sind alle Tageswerte — die Tagesansicht im Cockpit, das Energieprofil, die Tagesabschlüsse. Wie die Zeitzone im Standalone-Container gesetzt wird, steht in [HANDBUCH_INSTALLATION.md §2](HANDBUCH_INSTALLATION.md#2-installation).

**Was der Befund nicht leistet:** Er beschreibt den Zustand von **jetzt**. Bereits gespeicherte Tage werden dadurch nicht korrigiert — die lassen sich nach dem Neustart in der Reparatur-Werkbank (*Einstellungen → Daten → Energieprofil-Pflege*) neu berechnen.

---

#### eedc und Home Assistant rechnen mit verschiedenen Zeitzonen <a name="zeitzone_abweichung"></a>

**Was eedc sieht**
eedc und Home Assistant liegen zeitlich auseinander — jede Abweichung zählt, auch eine halbe Stunde. Verglichen wird der
aktuelle Abstand zur Weltzeit, nicht der Name der Zeitzone. Die Details nennen die Zeitzone von Home Assistant und den
Abstand. Rund um Mitternacht landen Stundenwerte dadurch im falschen Tag — betroffen sind alle Tageswerte: Tagesansicht
im Cockpit, Energieprofil, Tagesabschlüsse.

**Lösungsweg**
1. Als Add-on: am Befund **«Zum Neustart»** klicken — die [Protokolle](eedc:/einstellungen/system?block=protokolle)
   öffnen sich; dort **«Neustart»** klicken. eedc übernimmt die Zeitzone beim Start von Home Assistant.
2. Standalone (eigener Container): dort die Umgebungsvariable `TZ` auf die Zeitzone von Home Assistant setzen, die die
   Details nennen (in `docker-compose.yml` unter `environment`), und den Container neu starten.
3. Bereits gespeicherte Tage ändern sich dadurch nicht. Sie lassen sich danach in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) mit «Mehrere Tage neu aggregieren» neu
   berechnen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet weiter mit seiner eigenen Zeit: Stunden rund um Mitternacht werden weiter dem falschen Tag zugeordnet, auch in
allen neuen Tagen.

### 4.13 Sonstige Positionen – der Erfassungsort <a name="413-sonstige-positionen--der-erfassungsort"></a>

**Was wird geprüft:** Steht ein Betrag, der **jedes Jahr wiederkommt**, an der Stelle, an der er auch in die Zukunft wirkt?

**Warum das zählt:** eedc fragt nie, ob ein Betrag einmalig oder wiederkehrend ist — es liest das am **Ort** deiner Eingabe. Ein Jahresbetrag an der Komponente (*Betriebskosten/Jahr*, *Ertrag/Jahr*) wirkt jedes Jahr, also auch in Prognose und Amortisation. Eine Position im Monatsabschluss ist per Form **einmal** geflossen: Sie zählt in der Bilanz ihres Monats und im Amortisations-Fortschritt, aber nie in der Vorhersage. Das ist der Grund, warum eedc nichts raten muss — und zugleich die einzige Stelle, an der man es verfehlen kann.

**Woran eedc das erkennt: an der Wiederholung, nie an der Bedeutung.** Aus „Restwert", „Verkauf" oder „Förderung" auf etwas zu schließen wäre geraten — genau das tut eedc an keiner Stelle.

> **Beides sind Hinweise, keine Fehler.** Deine Erfassung ist nicht falsch — sie steht nur an der Stelle, an der sie weniger kann. Es gibt deshalb auch keinen „Akzeptiert"-Knopf: Wer den Betrag bewusst monatlich pflegt, lässt den Hinweis stehen.
>
> **Das Feld „Ertrag/Jahr" gibt es nur bei *Wallbox* und *Sonstiges*.** Bei allen anderen Komponenten rechnet eedc die Jahres-Einsparung selbst; dort meldet der Checker auf der Ertragsseite bewusst nichts, statt auf ein Feld zu verweisen, das im Formular nicht steht.

Hintergrund und die verworfenen Alternativen: [Berechnungen §3.6](BERECHNUNGEN.md#36-roi--amortisation) und [Bedienung, Auswertungen, ROI](HANDBUCH_BEDIENUNG.md#42-roi).

---

#### Jahresbetrag gepflegt und zusätzlich monatlich gebucht <a name="position_doppelerfassung"></a>

**Was eedc sieht**
An der Komponente ist ein Jahresbetrag hinterlegt (die Meldung nennt das Feld, die Details den Betrag), und derselbe Posten
steht zusätzlich in mindestens zwei Monaten im Monatsabschluss. Der Jahresbetrag wirkt jedes Jahr — der Betrag zählt
damit doppelt.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Komponente öffnet sich im Abschnitt «Weitere Angaben & Kosten».
2. Entweder den Jahresbetrag anpassen **oder** die Monatspositionen im Monatsabschluss entfernen. In den Monatsabschluss
   gehört nur die Abweichung vom Plan: die Nachzahlung, nicht die ganze Rechnung.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Der Betrag zählt weiter doppelt — einmal als Jahresbetrag und einmal in den Monaten, in denen er gebucht ist. eedc entfernt
keine der beiden Angaben von selbst.

#### Monatsposition sieht wiederkehrend aus <a name="position_wiederkehrend"></a>

**Was eedc sieht**
Dieselbe Bezeichnung steht an einer Komponente in mindestens drei Monaten im Monatsabschluss, und an der Komponente ist kein
passender Jahresbetrag gepflegt. Als Monatsposition wirkt der Betrag nur in der Bilanz des Monats, in dem er steht — ein
Jahresbetrag an der Komponente wirkt dagegen jedes Jahr, auch in Prognose und Amortisation. eedc erkennt das an der
Wiederholung, nie an der Bedeutung der Bezeichnung.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Komponente öffnet sich im Abschnitt «Weitere Angaben & Kosten».
2. Den Betrag dort als Jahresbetrag eintragen: Ausgaben unter «Betriebskosten/Jahr (€)», Erträge unter «Ertrag/Jahr (€)»
   (das Feld gibt es nur bei Wallbox und Sonstiges). Nennen die Details das Feld «Einspeise-Erlös», gehört der Erlös eines
   Erzeugers (Sonstiges) als Monatswert in dieses Feld des Geräts im Monatsabschluss — am besten aus einem Sensor, dann
   schlägt eedc den Wert dort vor —, nicht als Jahresbetrag an die Komponente. Danach die Monatspositionen entfernen,
   damit der Betrag nicht doppelt zählt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Deine Erfassung ist nicht falsch, sie steht nur an der Stelle, an der sie weniger kann: Der Betrag zählt in der Bilanz seiner
Monate und im Amortisations-Fortschritt, aber nicht in der Prognose. Einmaliges bleibt richtig, wo es ist.

### 4.14 Klimaanlage – Betriebsmodus <a name="414-klimaanlage--betriebsmodus"></a>

**Was wird geprüft:** Hat jedes Gerät, das heizt **und** kühlt, einen Weg, seinen Strom nach Heizen und Kühlen aufzuteilen? Gemeint sind Split-Klimaanlagen (Wärmepumpenart *Luft-Luft*) und jede Wärmepumpe, an der eine Kühl-Größe zugeordnet oder gepflegt ist (Kühl-Leistung, Kältemenge, Kühl-Betriebsart) — sie kühlt nachweislich, gleich welcher Bauart. Eine Luft-Wasser-Wärmepumpe ohne jede Kühl-Spur bekommt keinen Hinweis.

**Warum das zählt:** Deine Klimaanlage heizt im Winter und kühlt im Sommer — über **denselben** Stromzähler. eedc sieht deshalb nur eine Zahl „Stromverbrauch" und kann nicht sagen, welcher Teil davon ins Heizen ging und welcher ins Kühlen. Aus den vorhandenen Werten lässt sich das auch nicht nachrechnen: Es gibt kein Feld, aus dem die Aufteilung ableitbar wäre. Sie entsteht nur, wenn eedc **zur Messzeit mitschreibt**, in welchem Modus das Gerät gerade läuft — oder wenn eigene Zähler je Betriebsart messen.

> **Es gibt zwei Wege zu dieser Aufteilung, und der gemessene gewinnt.**
>
> 1. **Gemessen** — du ordnest eigene Zähler je Betriebsart zu (*Strom Heizbetrieb*, *Kühlbetrieb*, *Lüftbetrieb*, *Entfeuchtung*), am Gerät oder je Innengerät. Wer sie in Home Assistant nicht direkt bekommt, baut sie sich mit einem **Utility Meter** je Betriebsart.
> 2. **Abgeleitet** — du ordnest den **Betriebsmodus** zu (in Home Assistant die climate-Entität des Geräts), und eedc schreibt stündlich mit, was das Gerät gerade tat.
>
> Liegen **gemessene** Werte vor, rechnet eedc die abgeleitete Aufteilung für dieses Gerät gar nicht erst — ganz oder gar nicht, nie beides gemischt. Eine Zuordnung des Betriebsmodus wäre dann wirkungslos. Deshalb erscheint der Hinweis **nicht mehr**, sobald einer der beiden Wege eingerichtet ist (oder Werte auf einem von beiden angekommen sind).

> ⚠ **Die Aufteilung lässt sich nicht rückwirkend nachtragen — das ist der wichtigste Satz hier.** Home Assistant bewahrt Zustände wie „Heizen"/„Kühlen" nur wenige Tage auf (die Langzeit-Statistik gibt es nur für Zahlen-Sensoren). Wer den Sensor heute zuordnet, bekommt die Aufteilung **ab heute**; die Vergangenheit bleibt ungeteilt, und ein längerer eedc-Ausfall reißt eine Lücke, die bleibt. Deshalb lohnt sich die Zuordnung auch dann, wenn man die Auswertung noch nicht braucht.

> **Das Feld bietet eedc jeder Wärmepumpe an**: Es gibt Luft-Wasser-Geräte mit Kühlfunktion, und wer eines hat, findet den Betriebsmodus in der Datenquellen-Zuordnung.

> **Der Betriebsmodus geht auch über MQTT — als Inbound, nicht über das Gateway.** Er ist ein Zustand, kein Messwert: eedc nimmt am Modus-Topic ein Wort oder einen Zahlencode (0–5) entgegen ([Wärme & Klima, „Ohne Home Assistant: der Modus über MQTT"](HANDBUCH_WAERME_KLIMA.md#ohne-home-assistant-der-modus-über-mqtt)). Das Gateway reicht nur Zahlen weiter und steht an diesem Feld nicht zur Wahl. Über MQTT beginnt die Aufteilung mit dem ersten empfangenen Wert — auch hier nicht rückwirkend.

> **Was du nach der Zuordnung siehst:** In der Ansicht der Wärmepumpe unter Komponenten steht ein Block **„Aufteilung Heizen/Kühlen"** mit den beiden Strommengen, der Zeile *nicht aufgeteilt* und der Zahl der Stunden, in denen eedc mitlesen konnte. Dieselbe Aufteilung erscheint in der Monats- und Jahresansicht im Cockpit, dazu zwei Sensoren in Home Assistant. Die Aufteilung entsteht beim **Monatsabschluss**; für den laufenden Monat wird sie direkt aus den Tageswerten gelesen.

**Verwandte Befunde:** Ist die Aufteilung eines Monats größer als der Gesamtverbrauch des Geräts — oder hat eedc sie deshalb beim Speichern gar nicht übernommen —, meldet das die Kategorie **Investitionen** (§4.3), weil es an den Monatswerten des Geräts hängt, nicht an der Sensor-Zuordnung. eedc biegt dort nichts zurecht: Statt die Aufteilung stillschweigend auf den Gesamtwert zu kürzen, bleibt der Widerspruch sichtbar, bis du entschieden hast, welche der beiden Angaben stimmt. ⚠ **Deine Energiebilanz ist davon nicht betroffen:** dort zählt immer der Gesamtwert.

---

#### Kühlanteil wird geschätzt — Stromzähler für den Kühlbetrieb fehlt <a name="klima_kuehlanteil_geschaetzt"></a>

**Was eedc sieht**
Die Wärmepumpe misst Heizen und Warmwasser mit eigenen Zählern und teilt zusätzlich nach dem Betriebsmodus auf. Für den
Kühlbetrieb gibt es aber keinen eigenen Stromzähler — eedc schätzt den Kühlanteil deshalb aus der Summe der beiden anderen.
Verbrauch, Kosten und CO₂ rechnen weiter mit dem vollen Strom. Nur die Aufteilung nach Betriebsart ist eine Verteilung statt
einer Messung, und deshalb kürzt sie die Arbeitszahl nicht.

**Lösungsweg**
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät am Feld
   «Strom Kühlbetrieb (kWh)».
2. Dort den Stromzähler des Kühlbetriebs zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; eedc liest den Kühlstrom ab, statt ihn
   zu verteilen.

**Was ohne Handlung gilt**
Die Zuordnung ist freiwillig — ohne sie bleibt alles wie bisher: Die Mengen stimmen, der Kühlanteil bleibt geschätzt.

#### Heiz- und Kühlstrom werden aufgeteilt <a name="klima_modus_ok"></a>

**Was eedc sieht**
Jedes heizend-kühlende Gerät hat einen Weg zur Aufteilung seines Stroms. Der Titel nennt die Herkunft: «Betriebsart wird
gemessen» (eigene Zähler je Betriebsart, eedc liest ab), «Betriebsmodus ist zugeordnet» (eedc schreibt stündlich mit, ob
geheizt oder gekühlt wurde, und teilt danach auf) oder «Heiz- und Kühlstrom werden getrennt» (ein Teil der Geräte misst,
beim Rest leitet eedc aus dem Betriebsmodus ab).

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

**Was ohne Handlung gilt**
Die Aufteilung steht im Block «Aufteilung Heizen/Kühlen» der Wärmepumpe und in der Monats- und Jahresansicht im Cockpit.

#### Mehrere verschiedene Modus-Quellen an einem Gerät <a name="klima_modus_quellen_mehrdeutig"></a>

**Was eedc sieht**
Der Betriebsmodus ist an mehreren Innengeräten zugeordnet, und sie zeigen auf verschiedene Entitäten. Der Stromzähler des
Geräts ist aber einer — für die Aufteilung braucht eedc genau eine Aussage darüber, was die Anlage gerade tut. Aus mehreren
Innengeräte-Zuständen einen Anlagen-Zustand zu bilden, hängt an deiner Anlage (kann ein Innengerät lüften, während ein
anderes heizt? meldet das Außengerät beim Enteisen etwas?). Das weiß eedc nicht, und es rät nicht: Der Strom wird nicht
aufgeteilt.

**Lösungsweg**
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät am Feld «Betriebsmodus».
2. Einen der zwei Wege wählen: bei allen Innengeräten **dieselbe** climate-Entität zuordnen — dann ist es eine Quelle (bei
   einer Ein-Kreis-Anlage gibt ohnehin das Außengerät die Richtung vor). Oder in Home Assistant einen Template-Sensor bauen,
   der deine Innengeräte zu einer Aussage zusammenfasst, und dessen Ergebnis zuordnen (Vorlage im Handbuch «Wärme & Klima»).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, die Prüfung meldet die Aufteilung als
   eingerichtet.

**Was ohne Handlung gilt**
Alles bleibt wie bisher: Der Stromverbrauch zählt vollständig, nur die Aufteilung in Heizen und Kühlen fehlt. Sie beginnt
mit der eindeutigen Zuordnung und lässt sich nicht rückwirkend nachtragen.

#### Betriebsmodus nicht zugeordnet — Heiz- und Kühlstrom bleiben zusammen <a name="klima_modus_nicht_zugeordnet"></a>

**Was eedc sieht**
Dieses Gerät heizt und kühlt über denselben Stromzähler, und es gibt keinen der beiden Wege zur Aufteilung — weder eigene
Zähler je Betriebsart noch einen zugeordneten Betriebsmodus. eedc sieht deshalb nur eine Zahl und kann nicht sagen, welcher
Teil ins Heizen ging und welcher ins Kühlen. Den Hinweis bekommen Split-Klimaanlagen (Wärmepumpenart Luft/Luft) und jede
Wärmepumpe, an der eine Kühl-Größe zugeordnet oder gepflegt ist (Kühl-Leistung, Kältemenge, Kühl-Betriebsart).

**Lösungsweg**
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät am Feld «Betriebsmodus».
2. Dort die climate-Entität des Geräts zuordnen (in Home Assistant meist `climate.…`, sie zeigt Heizen/Kühlen/Aus). Ohne
   Home Assistant geht der Modus auch über MQTT mit der Quelle «Inbound» (Handbuch «Wärme & Klima»). Wer eigene Stromzähler
   je Betriebsart hat, ordnet stattdessen diese zu — liegen gemessene Werte vor, gelten sie, und der Betriebsmodus wird für
   dieses Gerät nicht gebraucht.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, die Prüfung meldet die Aufteilung als
   eingerichtet.

**Was ohne Handlung gilt**
Die Zuordnung ist freiwillig: Der Stromverbrauch zählt vollständig und richtig, es fehlt nur die Aufteilung. Sie beginnt mit
der Zuordnung und lässt sich nicht rückwirkend nachtragen — Home Assistant bewahrt Zustände wie „Heizen“ nur wenige Tage auf.

### 4.14a Betriebsmodus – unbekannter Wert <a name="414a-betriebsmodus--unbekannter-wert"></a>

**Was wird geprüft:** Liefert der zugeordnete Betriebsmodus-Sensor einer Wärmepumpe oder Klimaanlage gerade einen Wert, den eedc kennt?

**Warum das zählt:** eedc versteht eine feste Liste von Texten (Werte-Tabelle im Handbuch [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md#welchen-sensor-eedc-lesen-kann); dieselbe Liste steht in der Datenquellen-Zuordnung am Feld „Betriebsmodus"). Ein anderer Wert — etwa `heating`, `standby` oder `pool` aus einem eigenen Prioritäts-Sensor — zählt als *unbestimmt*: Der Strom dieser Stunden steht unter „nicht aufgeteilt", ohne dass es sonst jemand sagt.

> **Wann die Meldung schweigt:** ohne Verbindung zu Home Assistant, wenn der Sensor gerade `unknown` oder `unavailable` meldet (kein Wert ist kein falscher Wert), bei `auto`, `heat_cool` und `automatik` (eedc kennt sie und zählt sie bewusst als unbestimmt — das Gerät entscheidet dort selbst) und wenn das Gerät mehrere verschiedene Modus-Quellen hat (dann nennt §4.14 den Fall). Geprüft wird der Wert, den der Sensor **jetzt** meldet: Ein Wert, der nur zeitweise auftaucht, fällt auf, wenn er beim Prüfen ansteht.

---

#### Betriebsmodus-Sensor liefert einen Wert, den eedc nicht kennt <a name="klima_modus_wert_unbekannt"></a>

**Was eedc sieht**
Der zugeordnete Betriebsmodus-Sensor einer Wärmepumpe oder Klimaanlage meldet beim Prüfen einen Wert, den eedc nicht
versteht — etwa „heating“, „standby“ oder „pool“ aus einem eigenen Prioritäts-Sensor. Die Meldung nennt den Sensor und die
Liste der Werte, die eedc versteht; Groß-/Kleinschreibung ist egal. Stunden mit einem unbekannten Wert zählen als
unbestimmt: Ihr Strom steht unter „nicht aufgeteilt“.

**Lösungsweg**
1. In eedc ist dafür nichts umzustellen — der Wert kommt aus Home Assistant. Dort einen Template-Sensor anlegen, der aus
   deinen Werten einen der Texte macht, die eedc versteht (Vorlage und Werte-Tabelle im Handbuch «Wärme & Klima»,
   Schritt 4, Weg B).
2. Den neuen Sensor in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim Gerät im Feld «Betriebsmodus»
   zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald der zugeordnete Sensor einen
   bekannten Wert meldet. Geprüft wird der Wert von jetzt: Ein Wert, der nur zeitweise auftaucht, fällt auf, wenn er beim
   Prüfen ansteht.

**Was ohne Handlung gilt**
Der Stromverbrauch zählt weiter vollständig; nur die Stunden mit dem unbekannten Wert stehen unter „nicht aufgeteilt“. Die
Aufteilung beginnt mit dem neuen Sensor — Stunden davor bleiben, wie sie sind.

### 4.15 Sensor-Zuordnung – Leistung ↔ Energie verwechselt <a name="415-sensor-zuordnung--leistung--energie"></a>

**Was wird geprüft:** Steht in jedem Feld ein Sensor der passenden Art — ein **Leistungssensor** (W/kW) dort, wo eedc eine Momentanleistung erwartet, und ein **kWh-Zähler** dort, wo es eine Energiemenge erwartet? Verglichen wird die in Home Assistant hinterlegte Einheit, nicht der Wert.

**Warum das zählt:** Die beiden Größen sehen im Sensor-Namen oft gleich aus und bedeuten Verschiedenes. Ein Zählerstand in einem Leistungs-Feld wird als Momentanleistung gelesen — aus 7.130 kWh werden 7.130 W, und der live berechnete Restverbrauch klemmt auf 0. Umgekehrt lässt sich aus einem Leistungssensor die Energie nur schätzen.

> **Nur diese eine Verwechslung wird gemeldet.** Ladestand (%), Temperatur (°C), Preis (ct/kWh) und Kilometer bleiben ungeprüft: Dort sind mehrere Einheiten legitim, und eine Meldung wäre öfter falsch als richtig. **Ohne HA-Verbindung** wird die Kategorie still übersprungen — die Einheit kommt aus Home Assistant.

---

#### Energie-Sensor in einem Leistungs-Feld <a name="leistungs_slot_energie_sensor"></a>

**Was eedc sieht**
In einem Feld, das eine Momentanleistung erwartet, steht ein kWh-Zähler; verglichen wird die in Home Assistant hinterlegte
Einheit. Der Zählerstand wird dann als Leistung gelesen (aus 7130 kWh werden 7130 W), und im Live-Energiefluss klemmt der
berechnete Restverbrauch auf 0. Die Meldung nennt das Feld, die Details die zugeordnete Entität.

**Lösungsweg**
1. Am Befund **«Sensor wechseln»** klicken — die Datenquellen-Zuordnung öffnet sich an diesem Feld.
2. Dort einen Leistungssensor (W oder kW) wählen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Der Live-Energiefluss rechnet mit dem Zählerstand als Leistung weiter falsch.

#### Leistungssensor in einem Energie-Feld <a name="energie_slot_leistungssensor"></a>

**Was eedc sieht**
In einem Feld, das eine Energiemenge erwartet, steht ein Leistungssensor (W oder kW); verglichen wird die in Home Assistant
hinterlegte Einheit. Aus einem Leistungssensor lässt sich die Energie nur näherungsweise über die Zeit ableiten — ungenauer
und anfällig für Lücken. Die Meldung nennt das Feld, die Details die zugeordnete Entität.

**Lösungsweg**
1. Am Befund **«Sensor wechseln»** klicken — die Datenquellen-Zuordnung öffnet sich an diesem Feld.
2. Dort einen fortlaufenden kWh-Zähler wählen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
Aus dem Leistungssensor in diesem Feld entsteht kein Stunden- und kein Tageswert; nur wo eine Watt-Zeile mit einem
Leistungssensor belegt ist, schätzt eedc die Tagesenergie aus dessen Verlauf.

### 4.15a Sensor ohne Langzeitstatistik <a name="415a-sensor-ohne-langzeitstatistik"></a>

**Was wird geprüft:** Trägt ein zugeordneter **Vorlauf-**, **Rücklauf-** oder **Zusatzheizungs-Sensor** einer Wärmepumpe in Home Assistant `state_class: measurement`? Gelesen wird der aktuelle Zustand des Sensors, je aktiver Wärmepumpe.

**Warum das zählt:** Den aktuellen Wert zeigt eedc aus dem Sensor-Zustand — live und im Überblick des Wärmepumpen-Hubs. **Stündliche Mittelwerte** übernimmt eedc dagegen aus der Langzeitstatistik von Home Assistant (rückwirkend, so weit sie zurückreicht), und die führt HA nur für Sensoren mit `state_class: measurement`. Ohne sie bleibt der Tagesverlauf dieser Werte leer, ohne dass es sonst jemand sagt.

> **Wann die Meldung schweigt:** ohne Verbindung zu Home Assistant, wenn HA den Sensor gerade nicht liefert, an stillgelegten Geräten und für Felder, deren Quelle MQTT ist — dort schreibt eedc die Stundenmittel selbst aus seiner 5-Minuten-Mitschrift, eine Langzeitstatistik braucht es nicht ([Wärme & Klima, Schritt 6](HANDBUCH_WAERME_KLIMA.md#schritt-6--live-werte-optional)). Entscheidend ist die gespeicherte Quellenwahl des Felds: steht sie auf MQTT, prüft eedc den HA-Sensor nicht; ohne Quellenwahl gilt der HA-Sensor — fehlt ihm die Langzeitstatistik, bleibt die Meldung, und eedc schreibt das Topic nicht stattdessen mit. Die Warmwasser-Temperatur prüft diese Kategorie nicht.

---

#### Wärmepumpen-Sensor ohne Langzeitstatistik — Live ja, Tagesverlauf nein <a name="sensor_ohne_langzeitstatistik"></a>

**Was eedc sieht**
Ein zugeordneter Vorlauf-, Rücklauf- oder Zusatzheizungs-Sensor einer Wärmepumpe trägt in Home Assistant kein
`state_class: measurement`; die Meldung nennt je Sensor das Feld und die Entität. Den aktuellen Wert zeigt eedc trotzdem
(Live, Überblick der Wärmepumpe). Stündliche Mittelwerte für den Tagesverlauf übernimmt eedc aber aus der Langzeitstatistik
von Home Assistant, und die führt Home Assistant nur mit diesem `state_class` — ohne ihn bleibt der Tagesverlauf leer.

**Lösungsweg**
1. In eedc ist dafür nichts umzustellen — der Weg liegt in Home Assistant: dort `state_class: measurement` ergänzen (per
   `customize`, Neustart von Home Assistant nötig) oder einen Template-Sensor anlegen, der es mitbringt.
2. Einen neuen Sensor in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim Gerät zuordnen. Ab dann übernimmt
   eedc die Stundenmittel aus der Statistik, so weit sie zurückreicht; Stunden, für die Home Assistant keine geführt hat,
   bleiben leer.
3. Anderer Weg: den Wert über MQTT liefern (Quelle «Inbound» statt des Home-Assistant-Sensors) — dann entstehen die
   Stundenmittel aus der 5-Minuten-Mitschrift von eedc, ab der Zuordnung, nicht rückwirkend. Ist einem Feld ein
   Home-Assistant-Sensor **und** dasselbe MQTT-Topic zugeordnet, gilt der Home-Assistant-Sensor.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange einer der genannten Sensoren ohne
   Langzeitstatistik zugeordnet ist.

**Was ohne Handlung gilt**
Live-Wert und Überblick funktionieren weiter; der Tagesverlauf dieser Werte bleibt leer.

### 4.16 Quellen-Konflikte <a name="416-quellen-konflikte"></a>

**Was wird geprüft:** Gab es in den letzten 30 Tagen Felder, für die **mehr als eine** Quelle einen Wert geschrieben hat — etwa eine Eingabe von Hand und der Monatsabschluss, oder die HA-Statistik und eine Reparatur?

**Warum das zählt:** Es ist kein Fehler. eedc hat sich bereits entschieden: Bei mehreren Quellen für dasselbe Feld gewinnt die höherwertige, und der angezeigte Wert stammt von ihr. Der Hinweis sagt nur, dass es die Konkurrenz gibt — nützlich, wenn eine Zahl anders aussieht als erwartet.

---

#### Keine Quellen-Konflikte <a name="provenance_ok"></a>

**Was eedc sieht**
Im Prüfzeitraum (die Meldung nennt die Zahl der Tage) hat jedes Feld höchstens eine Quelle geliefert — kein Wert stammt aus
einer Konkurrenz zweier Quellen.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

**Was ohne Handlung gilt**
Jeder angezeigte Wert stammt aus der einen Quelle, die für sein Feld geschrieben hat.

#### Felder mit Werten aus mehreren Quellen <a name="provenance_konflikte"></a>

**Was eedc sieht**
Für einige Felder haben in den letzten 30 Tagen zwei oder mehr Quellen einen Wert geliefert — etwa eine Eingabe von Hand
und der Monatsabschluss, oder die HA-Statistik und eine Reparatur. Die Details nennen je Treffer den Ort (Monatsdaten,
Tagesdaten oder die Komponente), das Feld, den Zeitraum und die beteiligten Quellen. Das ist kein Fehler: Bei mehreren
Quellen für dasselbe Feld gewinnt die höherwertige, und der angezeigte Wert stammt von ihr.

**Lösungsweg**
1. Nichts zu tun — eedc hat bereits entschieden. Der Hinweis ist nützlich, wenn eine Zahl anders aussieht als erwartet: Die
   Details sagen, welche Quellen am Feld konkurriert haben.
2. Zu entfernen gibt es nichts: Die Quellen sind die Wege, auf denen ein Wert geschrieben wurde (Eingabe von Hand,
   Monatsabschluss, HA-Statistik, Reparatur, Import) — keine Zuordnung. Der Hinweis zeigt nur, welche davon am Feld
   nacheinander geschrieben haben.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, bis in den letzten 30 Tagen keine zwei Quellen
   mehr an demselben Feld geschrieben haben.

**Was ohne Handlung gilt**
Der angezeigte Wert kommt weiter aus der höchstprioren Quelle. Der Hinweis ist kein Auftrag und hat keinen
„Akzeptiert“-Knopf.

### 4.17 Datenquellen-Drift zu Home Assistant <a name="417-datenquellen-drift"></a>

> **Variantenhinweis:** Nur mit HA-Verbindung. Ohne sie gibt es keine Vergleichsseite, die Kategorie wird still übersprungen.

**Was wird geprüft:** Stimmt das, was eedc für die letzten 90 Tage gespeichert hat, noch mit dem überein, was Home Assistant für denselben Tag ausweist? Geprüft werden **zwei Achsen**: die **PV-Tagessumme** über alle PV-Module und Balkonkraftwerke, und **jede andere zugeordnete Komponente einzeln** — Wallbox, E-Auto, Wärmepumpe, Sonstiges, dazu Einspeisung und Netzbezug. Gemeldet wird ein Tag ab **mindestens 2 kWh und mindestens 5 %** Unterschied — beide Schwellen zusammen, damit Rundungs-Unterschiede still bleiben.

**Warum das zählt:** eedc hat seine Tageswerte über die Zeit aus verschiedenen Quellen aufgebaut. Ältere Tage können auf einem Stand stehen, den ein heutiger Abruf anders beantwortet. Diese Werte tragen nicht nur die Energiebilanz, sondern auch Wirtschaftlichkeit und CO₂ — eine Abweichung an der Wallbox kostet genauso wie eine an der PV. Die Kategorie startet zugeklappt, weil Drift ein Hinweis ist.

> **Warum PV als Summe und alles andere je Gerät.** Mehrere Strings messen dieselbe Sache; ihre Summe ist die Zahl, die du kennst. Zwei **Geräte** messen nicht dieselbe Sache: In einer gemeinsamen Summe würde ein Plus an der Wärmepumpe ein Minus an der Wallbox ausgleichen, und übrig bliebe eine unauffällige Null.

> **Liest eedc deine Anlage aus der Statistik von Home Assistant,** nimmt es PV, Einspeisung, Netzbezug und Speicher an solchen Tagen direkt von dort — die eedc-Seite des Vergleichs *ist* dann die Zahl von Home Assistant, und eine Abweichung der alten gespeicherten Tageszeile wird nicht mehr gemeldet (die Tagesansicht im Cockpit zeigt sie ohnehin nicht). Wallbox, E-Auto, Wärmepumpe und sonstige Geräte kommen an einem solchen Tag ebenfalls von dort, wenn sie zugeordnet sind; nur ein Gerät ohne solchen Wert liest die Prüfung aus der gespeicherten Tageszeile. Ein bloßes Neuberechnen des Tages ändert daran nichts — deshalb trägt die Zeile an einer solchen Anlage **«Aus Home Assistant neu übernehmen»** (zuerst der Abgleich mit Home Assistant, dann der Tag); ohne diese Verbindung heißt der Knopf **«Tag neu aufbauen»**. Massen-Reparaturen gibt es bewusst nur in der Reparatur-Werkbank, damit sie aktiv gewählt werden.
>
> **Nach einer Korrektur in Home Assistant** (etwa unter *Entwicklerwerkzeuge → Statistik*) trägt eedc bis zum nächtlichen Abgleich um 02:45 noch den alten Stand. So lange bleibt der Drift-Eintrag stehen; danach verschwindet er von selbst. Ob der Abgleich gelaufen ist, steht unter *Einstellungen → System → Protokolle* (Reiter **Aktivitäten**, Kategorie **„Scheduler-Jobs"**): eine Zeile je Nacht und Anlage, auch wenn nichts abweicht. Sofort geht es mit **«Aus Home Assistant neu übernehmen»** an der Zeile.
>
> **Verglichen wird nur, was Home Assistant für den Tag auch liefern konnte.** Ein Zähler ohne Summen-Spalte (§4.9) taucht hier nicht als Lücke auf — sonst meldete der Vergleich Phantom-Drift und böte einen Knopf an, der korrekte Werte mit 0 überschreibt.
>
> **Und je Gerät nur, was auf beiden Seiten einen Wert hat.** Liefert Home Assistant für ein Gerät einen Wert und die gespeicherte Tageszeile nicht, ist das eine **Lücke** und gehört §4.10 *Energieprofil – fehlende Tageswerte*. Die PV-Tagessumme vergleicht die Prüfung dagegen, sobald eine der beiden Seiten mehr als 0 kWh trägt. Der **Speicher** steht in keiner der beiden Achsen: Sein Tages-Netto darf legitim ~0 sein, und sein Vorzeichen hat mit §4.21 *Batterie-Vorzeichen in der Historie* eine eigene Prüfung.
>
> **Höchstens 20 PV-Tage, und je Tag nur, was an diesem Tag in Betrieb war.** Die PV-Tage stehen nach der Größe der Abweichung; die 20 größten erscheinen als Glieder der Zeile «n Tage weichen von Home Assistant ab», die Zeile nennt die Gesamtzahl. Die Home-Assistant-Seite liest an jedem Tag nur die Sensoren der Komponenten, die an diesem Tag in Betrieb waren (Anschaffung, Stilllegung, „aktiv") — ein später angeschafftes oder stillgelegtes Modul erzeugt so keine Abweichung, die kein Knopf auflösen könnte.

---

#### Keine Abweichung zu Home Assistant <a name="drift_ok"></a>

**Was eedc sieht**
In den letzten 90 Tagen stimmt, was eedc gespeichert hat, mit der Langzeitstatistik von Home Assistant überein: die
PV-Tagessumme und jede andere zugeordnete Komponente einzeln (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung,
Netzbezug). Kein Tag weicht um mindestens 2 kWh und 5 % zugleich ab. Der Speicher ist hier nicht dabei — sein
Vorzeichen hat eine eigene Prüfung.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange eedc und Home Assistant übereinstimmen.

**Was ohne Handlung gilt**
eedc und Home Assistant zeigen für diese Tage dieselben Zahlen.

#### Abweichung zu Home Assistant an einem Tag (PV) <a name="drift_tag"></a>

**Was eedc sieht**
Für diesen Tag steht in eedc eine andere PV-Erzeugung als in der Langzeitstatistik von Home Assistant (mindestens 2 kWh und
5 % Unterschied). Mehrere solche Tage stehen als eine Zeile «n Tage weichen von Home Assistant ab» mit einem Glied je Tag,
die größten Abweichungen vorn.

**Lösungsweg**
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Entwicklerwerkzeuge → Statistik* beim Sensor mit „Wert anpassen“ für diesen Tag berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken (ohne Spiegel heißt der Knopf «Tag neu
   aufbauen»), die Vorschau lesen und **«Anwenden»**. Für viele Tage auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

**Was ohne Handlung gilt**
Der Tag behält seinen Wert in eedc; Tagesansicht, Monat und alles, was daraus rechnet, nutzen ihn. Home Assistant und
eedc zeigen für diesen Tag verschiedene Zahlen, bis einer der beiden berichtigt ist.

#### Ein Gerät weicht an Tagen von Home Assistant ab <a name="drift_komponente"></a>

**Was eedc sieht**
Für eine Komponente (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung oder Netzbezug) steht in eedc an einem oder
mehreren Tagen ein anderer Wert als in der Langzeitstatistik von Home Assistant — mindestens 2 kWh und 5 % Unterschied.
Es gibt eine Zeile je Gerät, nicht je Tag; sie nennt den Tag mit der größten Abweichung und beide Zahlen. Diese Werte
tragen Wirtschaftlichkeit und CO₂-Bilanz mit — eine Abweichung an der Wallbox kostet genauso wie eine an der PV.

**Lösungsweg**
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Entwicklerwerkzeuge → Statistik* beim Sensor mit „Wert anpassen“ berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**.
   Liest eedc deine Anlage aus der Statistik von Home Assistant, übernimmt der Knopf die Statistik aller gespiegelten
   Zähler der Anlage neu (ab der ersten abweichenden Stunde) und baut den genannten Tag danach auf. Sonst heißt er «Tag neu aufbauen» und baut nur
   den genannten Tag neu; für alle Tage des Geräts auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — das Gerät ist aus der Liste verschwunden oder nennt weniger Tage.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

**Was ohne Handlung gilt**
Die Tage behalten ihren Wert in eedc; Tagesansicht, Monat, Wirtschaftlichkeit und CO₂-Bilanz rechnen damit. Hast du in
Home Assistant korrigiert und liest eedc die Anlage aus dessen Statistik, verschwindet die Zeile an Tagen, die eedc für
dieses Gerät aus der Statistik liest, nach dem nächtlichen Abgleich um 02:45 von selbst; an älteren Tagen (Gerätewert aus
der gespeicherten Tageszeile) erst nach **«Aus Home Assistant neu übernehmen»**.

### 4.18 PV-Doppelerfassung (Verdacht) <a name="418-pv-doppelerfassung"></a>

**Was wird geprüft:** Liefert deine Anlage an mehreren Tagen **mehr**, als physikalisch plausibel ist? Zwei unabhängige Signale aus den letzten 30 Tagen: eine Performance Ratio über 1,05 und ein spezifischer Tagesertrag über 7 kWh/kWp.

**Warum das zählt:** Der häufigste Grund ist keine Wundertechnik, sondern **dieselbe Erzeugung zweimal gezählt** — etwa ein String-Sensor *und* der Anlagen-Summenzähler, beide zugeordnet. Alles, was auf der Erzeugung aufbaut, wird dadurch zu gut: Eigenverbrauch, Autarkie, Ersparnis, CO₂.

> **Der Verdacht hat zwei Seiten, und die zweite wird leicht übersehen.** Die Performance Ratio ist `Ertrag ÷ (Einstrahlung × kWp)`. Sie steigt also nicht nur, wenn der **Ertrag** zu hoch ist, sondern auch, wenn der **Vergleichsmaßstab** zu klein angesetzt ist — und der hat zwei Faktoren: die eingetragene kWp *und* die Einstrahlung. Wer alle Zuordnungen geprüft hat und nichts Doppeltes findet, sieht deshalb als Nächstes bei **Ausrichtung und Neigung der Module** nach (*Einstellungen → Komponenten → PV-Module*): Ohne sie rechnet eedc mit einer Einstrahlung, die nicht zu deinem Dach passt.

> **Und eine dritte Spur, die nicht bei dir liegt: die Einstrahlung der letzten Tage ist vorläufig.** Den Strahlungswert holt eedc beim Wetterdienst. Für Tage, die weiter als fünf Tage zurückliegen, kommt er aus dem endgültigen Messarchiv; für die Tage davor gibt es das Archiv noch nicht, eedc nimmt dort den Modellwert. Der ist im Mittel gut, an **bewölkten** Tagen aber deutlich zu klein — und ein zu kleiner Vergleichsmaßstab treibt die Performance Ratio nach oben, ohne dass an deiner Anlage etwas falsch wäre. eedc holt den endgültigen Wert von selbst nach, sobald ein Tag alt genug ist (nur die Wetterzeile, die gemessene Energie bleibt). Ein Verdacht, der nur an solchen Tagen hing, verschwindet damit von allein.

> **Liest eedc deine Anlage aus der Statistik von Home Assistant,** zählt für den spezifischen Tagesertrag die PV von dort — dieselbe Zahl wie in der Tagesansicht im Cockpit; die Performance Ratio bleibt die der gespeicherten Tageszeile.

> **eedc kürzt hier nichts.** Es gibt keinen Knopf, der die Erzeugung „gerade zieht" — die Entscheidung, welche Zuordnung die richtige ist, kann nur der Anlagenbetreiber treffen.

---

#### Auffällige PV-Tage mit Zählersprung — kein Doppelerfassungs-Verdacht <a name="pv_ueber_erfassung_spike_ueberdeckt"></a>

**Was eedc sieht**
Einige Tage liegen über dem physikalisch Möglichen, aber jeder davon trägt einen unmöglichen Stundenwert — typisch nach
einer Verbindungsunterbrechung, wenn ein Zähler den Zuwachs nachliefert und Home Assistant ihn in eine Stunde bucht. Die
übrigen Tage sind unauffällig; eine doppelt zugeordnete Erzeugung passt deshalb nicht zum Bild. Die Details nennen die
Tage.

**Lösungsweg**
1. In der Zuordnung ist hier nichts zu suchen. Die Ursache ist der Zählersprung: in der Kategorie «Energieprofil –
   Plausibilität» den Befund «Counter-Spike am …» des Tages öffnen und dessen Weg gehen (dort **«Tag neu aufbauen»**).
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Sprünge behoben sind.

**Was ohne Handlung gilt**
Die Tage behalten den Sprung: Tagesansicht und Monat zeigen an ihnen zu viel Erzeugung. Ein Verdacht auf
Doppelerfassung entsteht daraus nicht.

#### Verdacht auf PV-Doppelerfassung <a name="pv_ueber_erfassung_verdacht"></a>

**Was eedc sieht**
In den letzten 30 Tagen liefert die Anlage mehr, als physikalisch plausibel ist: eine Performance Ratio über 1,05 an
mindestens drei Tagen und mindestens 20 % der Tage mit Performance Ratio, oder ein Tagesertrag über 7 kWh je kWp an
mindestens drei Tagen. Der häufigste Grund ist dieselbe Erzeugung zweimal gezählt — etwa ein
String-Sensor und der Summenzähler der Anlage, beide zugeordnet, oder ein Wechselrichter-Zähler, der ein Balkonkraftwerk
schon mitmisst, das zusätzlich zugeordnet ist. Die Performance Ratio steigt aber auch, wenn der Vergleichsmaßstab zu
klein ist: die eingetragene kWp oder die Einstrahlung. Tage mit bekanntem Zählersprung sind schon herausgerechnet.

**Lösungsweg**
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich bei der PV-Erzeugung. Prüfen, ob
   dieselbe Erzeugung an zwei Stellen zugeordnet ist, auch beim Balkonkraftwerk. Regel: entweder je Erzeuger ein eigener
   Zähler oder ein Summenzähler der Anlage — nicht beides.
2. Findet sich dort nichts: unter *Einstellungen → Komponenten → PV-Module* je Modul «Leistung (kWp)», «Ausrichtung»
   und «Neigung (Grad)» prüfen, unter *Einstellungen → Stammdaten → Anlage* den Standort. Ohne passende Ausrichtung und
   Neigung rechnet eedc mit einer Einstrahlung, die nicht zu deinem Dach passt.
3. Liegen die auffälligen Tage alle in den letzten fünf Tagen und sind es trübe Tage: abwarten. Die Einstrahlung dieser
   Tage ist noch vorläufig und an bewölkten Tagen zu klein; eedc holt den endgültigen Wert selbst nach.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald keine der beiden
   Bedingungen mehr erfüllt ist.

**Was ohne Handlung gilt**
eedc kürzt nichts: welche Zuordnung richtig ist, entscheidest du. Ist die Erzeugung tatsächlich doppelt gezählt, fallen
Eigenverbrauch, Autarkie, Ersparnis und CO₂-Bilanz zu gut aus.

### 4.19 Ladung doppelt gezählt (Wallbox + E-Auto) <a name="419-ladung-doppelt-gezaehlt"></a>

**Was wird geprüft:** Gibt es in den letzten 180 Tagen gespeicherte Tage, an denen **Wallbox und E-Auto beide mindestens 1 kWh Ladung** tragen?

**Warum das zählt:** Wer sein Auto zu Hause lädt, hat oft beide Geräte erfasst — die Wallbox misst, das Auto meldet. Beide Zahlen zu addieren verdoppelt den Verbrauch. eedc kennt die Regel inzwischen (*trägt die Wallbox die Ladeenergie, ist sie die Quelle*), aber **bereits gespeicherte** Tage tragen die alte Rechnung weiter.

> **Warum das kein automatischer Lauf beim Start ist:** Die Berichtigung überschreibt gespeicherte Messwerte. Das passiert in eedc nie ungefragt — du siehst den Befund, die Tage, und entscheidest.

---

#### Keine doppelt gezählte Ladung <a name="emob_doppelzaehlung_ok"></a>

**Was eedc sieht**
An keinem gespeicherten Tag der letzten 180 tragen Wallbox und E-Auto beide eine Ladung von mindestens 1 kWh.
Das heißt „geprüft, soweit Tageswerte vorliegen“: Tage ohne gespeicherte Werte der Geräte kann die Prüfung nicht
ansehen.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange kein Tag die Ladung doppelt trägt.

**Was ohne Handlung gilt**
Jede Heimladung steht an den geprüften Tagen einmal in der Bilanz.

#### Tage zählen dieselbe Ladung doppelt <a name="emob_doppelzaehlung_tage"></a>

**Was eedc sieht**
An diesen gespeicherten Tagen der letzten 180 tragen Wallbox und E-Auto beide eine Ladung von mindestens 1 kWh, die
Ladung steht also zweimal in der Bilanz. eedc zählt eine Ladung inzwischen nur noch einmal (trägt die Wallbox die Ladeenergie, ist sie die Quelle) —
diese Tage wurden aber vorher geschrieben und bleiben so, bis sie neu berechnet werden. Die Details nennen die Menge und
die größten Fälle mit beiden Beträgen.

**Lösungsweg**
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»**. Ein Lauf baut das jüngste Fenster
   von höchstens 31 Tagen neu auf — jeden Tag darin, auch die ohne Befund; er berichtigt Tages- und Stundenwerte, nicht
   die Monatswerte. Werte, die nur per MQTT ankamen, und Strompreis-Sensordaten ohne Gegenstück in Home Assistant gehen
   dabei verloren — die Vorschau nennt es. Ist der jüngste betroffene Tag heute, lehnt die Vorschau ab («Der laufende
   Tag lässt sich erst morgen neu aufbauen.») — dann morgen erneut.
2. Nennen die Details ältere Tage außerhalb dieses Fensters: nach dem Lauf erneut prüfen und den Knopf noch einmal nutzen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt nur noch ältere Tage.

**Was ohne Handlung gilt**
Die Tage behalten die doppelte Ladung; Tagesansicht und Energieprofil zeigen dort zu viel Ladeenergie. eedc überschreibt
gespeicherte Werte nie ungefragt — deshalb läuft die Berichtigung nicht von selbst.

### 4.20 Plug-in-Hybrid – elektrischer Anteil unbestimmt <a name="420-phev-anteil"></a>

**Was wird geprüft:** Ist bei einem Fahrzeug mit Verbrenner-Anteil bestimmbar, **welcher Teil der Kilometer elektrisch** gefahren wurde?

**Warum das zählt:** Trägt ein Fahrzeug einen Verbrauch in l/100 km, hat es einen Verbrennungsmotor. Um die Kilometer aufzuteilen, braucht eedc eine von zwei Angaben: den monatlich erfassten Fahrverbrauch in kWh (gemessen) oder einen gepflegten elektrischen Fahranteil in % (geschätzt). **Fehlen beide, rechnet eedc 100 % elektrisch** — Ersparnis und CO₂-Bilanz fallen dadurch zu gut aus. Ein Richtwert wäre erfunden; deshalb sagt eedc es lieber.

---

#### Elektrischer Anteil eines Plug-in-Hybrids unbestimmt <a name="phev_anteil_unbestimmt"></a>

**Was eedc sieht**
Das Fahrzeug trägt einen Verbrauch in l/100 km, hat also einen Verbrennungsmotor. Um die Kilometer in elektrisch und
mit Kraftstoff gefahren aufzuteilen, braucht eedc eine von zwei Angaben: den monatlich erfassten Verbrauch in kWh
(gemessen) oder einen gepflegten elektrischen Fahranteil in % (geschätzt). In mindestens zwei Monaten mit gefahrenen
Kilometern fehlen beide; ein einzelner solcher Monat wird nicht gemeldet, ein Dienstwagen nicht geprüft.
Einen Richtwert erfindet eedc nicht — deshalb steht der Befund hier.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Fahrzeugs öffnet sich am Feld
   «Elektrischer Fahranteil (%)». Deinen geschätzten Anteil eintragen und speichern.
2. Oder der gemessene Weg: im Monatsabschluss je Monat beim Fahrzeug den «Verbrauch» in kWh eintragen
   ([Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)). Ist er erfasst, rechnet eedc den Anteil daraus —
   gemessen schlägt geschätzt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet diese Monate mit 100 % elektrisch gefahrenen Kilometern. Ersparnis und CO₂-Einsparung des Fahrzeugs fallen
dadurch zu gut aus.

### 4.21 Batterie-Vorzeichen in der Historie <a name="421-batterie-vorzeichen-historie"></a>

**Was wird geprüft:** Tragen gespeicherte Tage die Batterie-Richtung noch **verkehrt herum**?

**Warum das zählt:** Ältere eedc-Versionen schrieben das Batterie-Netto bei der Tagesberechnung in umgekehrter Richtung. Der Fehler steht in bereits gespeicherten Tagen, bis sie neu berechnet werden. **Die Live-Ansicht ist nicht betroffen** — sie hat einen eigenen Weg. Betroffen sind Energieprofil und Tages-Historie.

Erkannt wird das am **Datensignal**, nicht am Datum: Der gespeicherte Tageswert wird gegen einen frischen Abruf verglichen. Zeigen beide in entgegengesetzte Richtungen, ist der Tag mit der alten Logik gerechnet. Eine Zeile nennt alle Tage samt Zeitraum und baut sie in Fenstern von höchstens 31 Tagen neu auf; die Zeile «n Tage mit vertauschtem Batterie-Vorzeichen» bietet daneben bis zu 15 Tage einzeln an (die neuesten zuerst, die
übrigen zählt sie); geprüft werden die letzten 90 Tage.

> **Liest eedc deine Anlage aus der Statistik von Home Assistant,** kommt das Speicher-Netto an solchen Tagen von dort (wie in der Tagesansicht im Cockpit); ein vertauschtes Vorzeichen der alten gespeicherten Tageszeile wird dann nicht mehr gemeldet.
>
> **Eine reine Betrags-Abweichung wird hier bewusst nicht gemeldet** — nur die vertauschte Richtung. Gleiche Richtung mit anderem Betrag ist ein eigenes Thema und kein Vorzeichenfehler.

---

#### Batterie-Richtung in der Historie stimmt <a name="batterie_vorzeichen_ok"></a>

**Was eedc sieht**
Für die letzten 90 Tage zeigen das gespeicherte Speicher-Netto jedes Tages und ein frischer Abruf aus Home Assistant
in dieselbe Richtung: Laden ist Laden, Entladen ist Entladen. Kein Tag trägt noch die vertauschte Richtung einer älteren
eedc-Version.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange kein Tag in die falsche Richtung zeigt.

**Was ohne Handlung gilt**
Energieprofil und Tagesansicht zeigen Laden und Entladen des Speichers richtig herum.

#### Tage mit vertauschtem Batterie-Vorzeichen <a name="batterie_vorzeichen_tage"></a>

**Was eedc sieht**
An diesen gespeicherten Tagen stehen Laden und Entladen des Speichers vertauscht — sie wurden mit einer älteren
eedc-Version berechnet, die das Speicher-Netto in umgekehrter Richtung schrieb. Erkannt wird das am Vergleich mit einem
frischen Abruf aus Home Assistant: beide zeigen in entgegengesetzte Richtungen. Betroffen sind Energieprofil und
Tages-Historie, nicht die Live-Ansicht. Die Zeile nennt Zahl und Zeitraum der Tage.

**Lösungsweg**
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»**. Ein Lauf baut das jüngste Fenster
   von höchstens 31 Tagen neu auf — jeden Tag darin, auch die ohne Befund.
2. Nennen die Details ältere Tage außerhalb dieses Fensters: nach dem Lauf erneut prüfen und den Knopf noch einmal
   nutzen, oder einen einzelnen Tag in der Zeile «… Tage mit vertauschtem Batterie-Vorzeichen» anklicken.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt nur noch ältere Tage.

**Was ohne Handlung gilt**
Die Tage behalten die vertauschte Richtung: Energieprofil und Tagesansicht zeigen dort Laden als Entladen und umgekehrt.
Die Live-Ansicht ist davon nicht betroffen.

#### Ein Tag mit vertauschtem Batterie-Vorzeichen <a name="batterie_vorzeichen_tag"></a>

**Was eedc sieht**
An diesem gespeicherten Tag stehen Laden und Entladen des Speichers vertauscht — er wurde mit einer älteren eedc-Version
berechnet. Gespeicherter Wert und ein frischer Abruf aus Home Assistant zeigen in entgegengesetzte Richtungen. Mehrere
solche Tage stehen als eine Zeile «n Tage mit vertauschtem Batterie-Vorzeichen» mit einem Glied je Tag.

**Lösungsweg**
1. Am Befund einen Tag (ein Glied) bzw. **«Tag neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — genau
   dieser Tag wird neu aufgebaut, mit dem Speicher-Netto in der richtigen Richtung.
2. Für viele Tage auf einmal ist der Befund «… Tag(e) mit vertauschtem Batterie-Vorzeichen» mit seinem Knopf
   «Tage neu aufbauen» der kürzere Weg.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

**Was ohne Handlung gilt**
Der Tag behält die vertauschte Richtung; Energieprofil und Tagesansicht zeigen dort Laden als Entladen und umgekehrt.

### 4.22 Ladestand bei mehreren Speichern <a name="422-ladestand-mehrere-speicher"></a>

**Was wird geprüft:** Kennt die gespeicherte Historie bei einer Anlage mit **mehreren** Speichern den Ladestand **aller** Geräte — oder nur den eines einzelnen?

**Warum das zählt:** Bis August 2026 nahm eedc den ersten gefundenen Ladestand-Sensor und rechnete mit ihm, als gälte er für die ganze Anlage. Welcher das war, entschied die Reihenfolge der Zuordnung. Vollzyklen, Ladestand-Hübe und die Speicher-Auslegung lasen ihn aber als anlagenweit.

> **Anlagen mit einem Speicher erscheinen hier nie.** Dort war die alte Rechnung mit der neuen wertgleich — es gibt nichts zu reparieren.

---

#### Ladestand aller Speicher wird getrennt geführt <a name="soc_ok"></a>

**Was eedc sieht**
Die Anlage hat mehrere Speicher mit eigenem Ladestand, und die gespeicherte Historie kennt jeden davon: der
Anlagen-Ladestand ist das nach Kapazität gewichtete Mittel, die Werte je Gerät stehen daneben. Tage vor einem
Geräte-Wechsel zählen nicht als Befund — an ihnen war nur ein Speicher in Betrieb.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange jeder Tag alle Speicher kennt.

**Was ohne Handlung gilt**
Vollzyklen, Ladestand-Hübe und die Speicher-Auswertungen rechnen mit dem Ladestand aller Speicher.

#### Tage kennen nur den Ladestand eines Speichers <a name="soc_nur_ein_speicher_tage"></a>

**Was eedc sieht**
Die Anlage hat mehrere Speicher mit eigenem Ladestand-Sensor. An diesen Tagen hat eedc nur den Ladestand eines Geräts
gespeichert — welches, entschied die Reihenfolge der Zuordnung — und ihn behandelt, als gälte er für die ganze Anlage.
Die Tage stammen aus der Zeit vor der Korrektur dieser Rechnung. Betroffen sind Vollzyklen, Ladestand-Hübe und die
Speicher-Auswertungen; Erzeugung, Verbrauch und Netzbezug sind es nicht.

**Lösungsweg**
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»**. Ein Lauf baut das jüngste Fenster
   von höchstens 31 Tagen neu auf — jeden Tag darin, auch die ohne Befund.
2. Nennen die Details ältere Tage außerhalb dieses Fensters: nach dem Lauf erneut prüfen und den Knopf noch einmal nutzen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt nur noch ältere Tage.

**Was ohne Handlung gilt**
Für diese Tage rechnen Vollzyklen, Ladestand-Hübe und Speicher-Auswertungen mit dem Ladestand eines einzelnen Speichers,
als wäre es der der ganzen Anlage.

### 4.23 Verbrauchszähler – Zählerstände <a name="423-verbrauchszaehler-zaehlerstaende"></a>

**Was wird geprüft:** Kommt für einen Gas-, Wasser- oder Ölzähler überhaupt ein Stand an, läuft seine Reihe irgendwo **rückwärts**, und ist das Gerät versehentlich auf *nicht aktiv* gesetzt?

**Warum das zählt:** Ein Verbrauchszähler führt genau **einen** Wert — den Zählerstand. Die einzige Rechnung darauf ist *Ende minus Anfang* des angezeigten Zeitraums. Er geht bewusst in **keine** Bewertung ein: nicht in Energiebilanz, Autarkie, Wirtschaftlichkeit, CO₂-Bilanz oder den Community-Vergleich. Genau deshalb fallen Probleme mit ihm nirgends sonst auf — keine Kennzahl wird auffällig, es steht einfach überall „—".

> **Kein Verbrauchszähler eingerichtet ⇒ diese Kategorie erscheint gar nicht.**

> **Zählerwechsel richtig abbilden:** am **alten** Gerät ein **Stilllegungsdatum** setzen und ein neues anlegen. ⚠ Den Haken *aktiv* dabei **stehen lassen**: er bedeutet „wie gelöscht" und würde die alte Historie aus allen Auswertungen entfernen. Danach ist der Verbrauch über den Wechsel hinweg sauber die **Summe beider** Differenzen.

> **eedc heilt einen Bruch in der Reihe nicht von selbst** — dafür müsste es raten, welcher der beiden Stände gilt. Diese Entscheidung gehört dir, deshalb steht beim Befund der Weg und kein Knopf.

---

#### Verbrauchszähler liefert Zählerstände <a name="zaehlerstand_ablesungen_ok"></a>

**Was eedc sieht**
Für diesen Gas-, Wasser- oder Ölzähler liegen Zählerstände vor — aus einem zugeordneten Sensor oder von Hand. Die Zeile
nennt die Zahl der Ablesungen.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange der Zähler Stände liefert.

**Was ohne Handlung gilt**
eedc zeigt für jeden Zeitraum die Differenz aus Ende minus Anfang. Ein Verbrauchszähler geht bewusst in keine Bewertung
ein (Bilanz, Autarkie, Wirtschaftlichkeit, CO₂, Community).

#### Verbrauchszähler ohne Zählerstand <a name="zaehlerstand_kein_stand"></a>

**Was eedc sieht**
Für diesen Gas-, Wasser- oder Ölzähler liegt kein einziger Stand vor — weder aus einem Sensor noch von Hand. In
Cockpit, Komponenten und Tabellen steht deshalb überall „—“. Weil ein Verbrauchszähler in keine Bewertung eingeht,
fällt das sonst nirgends auf.

**Lösungsweg**
1. Am Befund **«Zählerstand erfassen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Zähler am Feld
   «Zählerstand». Einen Sensor zuordnen, der den fortlaufenden Stand liefert; eedc schreibt ihn dann stündlich mit.
2. Oder, gleichwertig: den Stand beim Monatsabschluss ablesen und im Feld «Zählerstand» eintragen
   ([Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)). Für einen Gas- oder Wasserzähler ohne Fernauslesung
   ist das der vorgesehene Weg.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald ein Stand vorliegt.

**Was ohne Handlung gilt**
eedc zeigt für diesen Zähler überall „—“. Andere Zahlen sind nicht berührt — der Zähler geht in keine Bewertung ein.

#### Zählerstand eines Verbrauchszählers ist gefallen <a name="zaehlerstand_reihe_bruch"></a>

**Was eedc sieht**
Ein Zählerstand läuft nicht rückwärts — in dieser Reihe fällt er an einer oder mehreren Stellen (die Details nennen
bis zu drei mit Datum und beiden Ständen, weitere werden gezählt). Liegt der Stand am Ende eines Zeitraums unter dem
am Anfang, zeigt eedc deshalb keine Differenz statt einer negativen Menge; ein Bruch mitten im Zeitraum, nach dem der
Stand wieder über den Anfang steigt, bleibt in der Differenz unsichtbar.
eedc heilt den Bruch nicht selbst: dafür müsste es raten, welcher der beiden Stände gilt.

**Lösungsweg**
1. Am Befund zeigt **«Was gilt»** diesen Abschnitt. Die Ursache bestimmen — drei kommen in Frage, je mit eigenem Weg:
2. **Zähler gewechselt:** der neue Zähler beginnt niedriger. Unter *Einstellungen → Komponenten → Sonstiges* am alten
   Zähler ein «Stilllegungsdatum (optional)» setzen und den neuen als
   eigenes Gerät anlegen. Den Haken «Aktiv (in Berechnungen berücksichtigen)» am alten Gerät **stehen lassen** — ohne
   ihn verschwindet seine Historie aus allen Auswertungen. Der Verbrauch über den Wechsel ist danach die Summe beider
   Differenzen.
3. **Sensor getauscht oder Stand von Hand korrigiert,** und der neue Wert liegt unter dem alten. Kam der Stand von
   Hand, den Wert im Feld «Zählerstand» des betroffenen Monats prüfen
   ([Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)); stimmt er, ist der Bruch echt und bleibt stehen.
4. **Umstieg auf eedc 4.0.25:** bis dahin schrieb eedc für Verbrauchszähler die Verbrauchssumme von Home Assistant statt
   des Zählerstands. Dann fällt die Reihe genau einmal, an der Umstellung, und es ist nichts kaputt. In der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) mit «Mehrere Tage neu aggregieren»
   zieht eedc die Historie nach, soweit Home Assistant sie noch hat.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt weniger Stellen; ein
   Bruch aus einem Zählerwechsel bleibt auch nach der Stilllegung stehen — die Zeile erklärt ihn weiterhin, solange
   die Reihe des alten Zählers den niedrigeren Stand enthält.

**Was ohne Handlung gilt**
Für Zeiträume über eine Bruchstelle zeigt eedc für diesen Zähler keine Differenz; Zeiträume davor und danach rechnen
normal. Andere Zahlen sind nicht berührt — der Zähler geht in keine Bewertung ein.

#### Verbrauchszähler auf „nicht aktiv“ gesetzt <a name="zaehler_nicht_aktiv"></a>

**Was eedc sieht**
Am Zähler ist der Haken „aktiv“ entfernt. In eedc heißt das „wie gelöscht“: seine Ablesungen erscheinen nirgends mehr,
auch nicht für die Vergangenheit, in der er gemessen hat. Die Zeile nennt die Zahl der ausgeblendeten Ablesungen.

**Lösungsweg**
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Zählers öffnet sich am Haken
   «Aktiv (in Berechnungen berücksichtigen)».
2. War es ein Zählerwechsel: den Haken wieder setzen und stattdessen ein «Stilllegungsdatum (optional)» eintragen,
   speichern; den neuen Zähler als eigenes Gerät anlegen. So bleibt die Historie des alten in jedem Zeitraum erhalten,
   in den er hineingemessen hat. Ist das Gerät bewusst ausgeblendet und soll auch historisch verschwinden, ist nichts
   zu tun.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald der Haken gesetzt ist;
   bei einem bewusst ausgeblendeten Gerät bleibt sie stehen.

**Was ohne Handlung gilt**
Die Ablesungen dieses Zählers erscheinen in keinem Zeitraum, auch nicht rückwirkend.

### 4.24 Vergleichspreise – Ø Benzinpreis <a name="424-vergleichspreise-benzinpreis"></a>

**Was wird geprüft:** Trägt jeder Monat, in dem du ein E-Auto hast, den Ø-Benzinpreis dieses Monats?

**Warum das zählt:** Der Vergleich „was hätte dieselbe Strecke mit Benzin gekostet?" ist der Kern der E-Auto-Wirtschaftlichkeit. eedc rechnet ihn **Monat für Monat mit dem Preis des jeweiligen Monats** — ein Monat aus 2023 mit dem Preis von 2023. Die Werte holt eedc täglich und kurz nach jedem Start selbst aus dem *EU Weekly Oil Bulletin* der Europäischen Kommission (nationale Durchschnittspreise für Super 95 inklusive Steuern, Datenbestand seit 2005); du musst dafür nichts eintragen.

Fehlt der Wert für einen Monat, rechnet eedc trotzdem weiter — dann aber mit dem **Modellwert** aus den Angaben zur Komponente (ersatzweise 1,65 €/L). Das ist der eine Preis von heute statt des damaligen: Der *Fortschritt* behauptet dann eine Messung und liefert eine Schätzung. Genau deshalb steht diese Prüfung hier.

> **Kein E-Auto angelegt ⇒ diese Kategorie erscheint gar nicht.** Und Monate **vor** der Anschaffung des Fahrzeugs zählen nicht mit — es gab dort nichts zu vergleichen.

**Wo du den Wert siehst:** *Einstellungen → Daten → Monatsdaten*, Monat öffnen, Abschnitt «Vergleichspreise (optional)», Feld «Ø Benzinpreis». Dort kannst du auch einen eigenen Wert eintragen — ein von Hand gesetzter Preis wird **nie** überschrieben.

---

#### Jeder Monat mit E-Auto trägt einen Benzinpreis <a name="vergleichspreis_ok"></a>

**Was eedc sieht**
Jeder Monat ab der Anschaffung eines E-Autos trägt den Ø-Benzinpreis dieses Monats. Der Vergleich „was hätte dieselbe
Strecke mit Benzin gekostet?“ rechnet damit durchgehend mit den damaligen Preisen.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange kein Monat ohne Preis ist.

**Was ohne Handlung gilt**
eedc holt den Preis neuer Monate täglich selbst nach; die E-Auto-Wirtschaftlichkeit rechnet Monat für Monat mit dem
Preis des jeweiligen Monats.

#### Monate ohne Ø-Benzinpreis <a name="vergleichspreis_fehlt"></a>

**Was eedc sieht**
Für diese Monate mit E-Auto liegt kein Ø-Benzinpreis vor — typisch nach einem Import älterer Monate oder direkt nach
der Einrichtung. Den Preis holt eedc selbst aus dem EU Weekly Oil Bulletin der Europäischen Kommission (nationaler
Durchschnitt für Super 95 inklusive Steuern); er ist die Grundlage des Vergleichs „was hätte dieselbe Strecke mit Benzin
gekostet?“. Die Zeile nennt Zahl und Zeitraum der Monate.

**Lösungsweg**
1. Am Befund **«Benzinpreise nachtragen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt die Wochenpreise
   für alle offenen Monate. Bestehende Werte bleiben unberührt, mehrfaches Ausführen ist gefahrlos.
2. Einen eigenen Wert trägst du im Monat selbst ein: unter *Einstellungen → Daten → Monatsdaten* den Monat öffnen,
   Abschnitt «Vergleichspreise (optional)», Feld «Ø Benzinpreis». Ein von Hand gesetzter Preis wird nie überschrieben.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

**Was ohne Handlung gilt**
eedc rechnet diese Monate mit dem Modellwert aus den Angaben der Komponente (ersatzweise 1,65 €/L) — also mit einem
Preis von heute statt des damaligen. Die Ersparnis dieser Monate ist dann eine Schätzung, keine Messung.

### 4.25 Wetterwerte – fehlende Monatswerte <a name="425-wetterwerte-fehlende-monatswerte"></a>

**Was wird geprüft:** Trägt jeder abgeschlossene Monat seine **drei Wetterwerte** — Globalstrahlung, Sonnenstunden und Ø Temperatur —, stammen sie **aus derselben Quelle**, und ist diese Quelle überhaupt **festgehalten**? Die Ø Temperatur hat eigene Zeilen; Globalstrahlung und Sonnenstunden stehen gemeinsam in **einer** Zeile mit **einer** Aktion, «Wetterreihe nachziehen».

**Warum das zählt:** Globalstrahlung und Sonnenstunden sagen, wie viel Sonne ein Monat hatte — ohne sie lässt sich ein schwaches Jahr nicht von einer schwachen Anlage unterscheiden, und eine Reihe aus zwei Quellen vergleicht Lineale statt Sonne. Das Feld *„Ø Temperatur"* im Monatsabschluss wird beim Abschließen automatisch gefüllt — eedc nimmt zuerst **deine eigene Messreihe** (Stundenwerte der Außentemperatur, ersatzweise das Tages-Min/Max) und sonst das Wetter-Archiv. Zwischen Juli und September 2026 gab es dieses Auto-Fill nicht: Jeder in dieser Zeit abgeschlossene Monat kann ohne Wert dastehen.

> **eedc rechnet mit der Ø Temperatur heute keine Kennzahl aus.** Die Außentemperatur-Linie im Wärme/Klima-Verlauf und der Vergleich *kWh je Heizgradtag* lesen die **Tagesreihe** — feiner und unabhängig von diesem Feld. Der Monatswert ist die gepflegte **Rückfallebene** für Zeiträume, in denen diese Reihe fehlt. Deshalb ist der Befund ein **Hinweis** und keine Warnung.

> **Der laufende Monat wird nie bemängelt** — und auch nicht nachgezogen. Die Wetter-Archive liefern einen Monat erst ein paar Tage nach seinem Ende vollständig; ein halber Monat, als ganzer festgeschrieben, wäre eine falsche Zahl, die danach feststeht.

> **Warum «Wetterreihe nachziehen» immer erst eine Vorschau zeigt.** Die Aktion **ersetzt** vorhandene Werte — das ist ihr Zweck, denn eine Reihe aus zwei Quellen wird man nicht anders los. Etwas, das ersetzt, bekommt bei eedc immer erst eine Vorschau: sie sagt vorher, wie viele Monate betroffen sind und wie viele davon überschrieben werden.

> **Die fehlende Quellenangabe ist der Normalfall jeder Bestandsanlage.** An einer echten Anlage nachgemessen (39 Monate): Globalstrahlung und Sonnenstunden fehlten in **keinem** Monat, und **kein einziger** trug eine festgehaltene Quelle. Ohne diesen Teil der Zeile bliebe eine möglicherweise gemischte Reihe unbemerkt. **Er geht wieder weg:** Sobald jeder Monat seine Quelle trägt, ist die Menge leer — ein Übergangsbefund, kein Dauerzustand. Die **Ø Temperatur** zählt dabei bewusst nicht mit: Kommt sie aus deiner eigenen Messreihe, hat sie legitim keinen Wetterdienst als Quelle.

> **Was diese Prüfung nicht sehen kann.** Sie liest die mitgeschriebene **Herkunft** jedes Werts und fragt dafür kein Wetter-Archiv (eine Prüfung ohne Nebenwirkung). Werte, die geschrieben wurden, bevor eedc die Herkunft mitschrieb, gelten als *unbekannt*, nicht als *abweichend*. Der Bestand heilt beim ersten Nachzug: der schreibt die echte Quelle mit.

**Wo du den Wert siehst:** *Einstellungen → Daten → Monatsdaten*, Monat öffnen, Abschnitt «Wetterdaten (optional)». Ein von Hand gesetzter Wert wird **nie** überschrieben — weder vom Auto-Fill noch von «Temperatur aus Messung übernehmen» noch vom täglichen Lückenschluss. Die **einzige** Ausnahme ist «Wetterreihe nachziehen», und die löst du ausdrücklich aus. Als Kurve stehen Globalstrahlung und Sonnenstunden in den Auswertungen unter «Prognose» im Block «Sonnenangebot».

**Was eedc von allein tut:** Einmal täglich sieht eedc nach, ob ein abgeschlossener Monat eines der drei Felder vermissen lässt, und füllt **nur diese Lücken** — mit der an der Anlage gewählten Quelle. Was schon dasteht, bleibt stehen. Liefert kein messendes Archiv (das kommt außerhalb des DWD-Netzes vor), **bleibt die Lücke sichtbar**, statt mit einem langjährigen Mittelwert zugedeckt zu werden: ein Durchschnitt über viele Jahre würde ein schwaches Jahr unsichtbar machen.

---

#### Wetterreihe uneinheitlich oder lückenhaft <a name="wetterreihe_nachziehen"></a>

**Was eedc sieht**
Globalstrahlung und Sonnenstunden sagen, wie viel Sonne ein Monat hatte — ohne sie lässt sich ein schwaches Jahr nicht
von einer schwachen Anlage unterscheiden. Die Zeile nennt bis zu drei Zahlen abgeschlossener Monate: Monate ohne
Globalstrahlung oder Sonnenstunden; Monate aus einer anderen Wetterquelle als der heute gewählten (Open-Meteo und
Bright Sky messen Sonnenstunden nicht gleich, ein Mehrjahresvergleich sagt dann etwas über die Quelle, nicht über die
Sonne); Monate, bei denen nicht festgehalten ist, woher ihre Werte stammen. Das Letzte behauptet nicht, dass die Reihe
gemischt ist — nur, dass es sich nicht mehr feststellen lässt; das ist der Normalfall jeder älteren Anlage.

**Lösungsweg**
1. Unter *Einstellungen → Stammdaten → Anlage* prüfen, ob die
   [«Wetterdaten-Quelle»](eedc:/einstellungen/stammdaten?block=anlage&feld=wetter_provider) die ist, die du willst —
   von ihr holt eedc die Werte.
2. Am Befund **«Wetterreihe nachziehen»** klicken, die Vorschau lesen und **«Anwenden»**. eedc holt Globalstrahlung,
   Sonnenstunden und Ø Temperatur aller abgeschlossenen Monate von dieser Quelle (die Ø Temperatur zuerst aus deinen
   Messwerten) und **ersetzt** dabei vorhandene Werte aller drei Felder, auch von Hand gesetzte — die Vorschau nennt
   vorher, wie viele Monate betroffen sind. Der laufende Monat bleibt draußen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder abgeschlossene
   Monat Werte mit Quelle trägt; Monate, für die kein messendes Archiv deinen Ort erreicht, bleiben in der Zeile stehen.

**Was ohne Handlung gilt**
Einmal täglich füllt eedc nur fehlende Werte abgeschlossener Monate von der gewählten Quelle nach; was dasteht, bleibt.
Eine gemischte Reihe bleibt gemischt, und Jahresvergleiche von Strahlung und Sonnenstunden können die Quelle statt der
Sonne zeigen.

#### Jeder Monat trägt eine Ø Temperatur <a name="temperatur_ok"></a>

**Was eedc sieht**
Jeder erfasste Monat trägt im Monatsabschluss einen Wert im Feld «Ø Temperatur» — aus deiner eigenen Messreihe oder aus
dem Wetter-Archiv.

**Lösungsweg**
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht hinter «n Prüfungen bestanden» am Fuß ihrer
   Kategorie, solange kein Monat ohne Wert ist.

**Was ohne Handlung gilt**
Leere Ø Temperaturen abgeschlossener Monate füllt eedc einmal täglich von selbst (zuerst aus deiner Messreihe, sonst
aus dem Wetter-Archiv; nur mit hinterlegten Koordinaten der Anlage); ein gesetzter Wert wird nicht überschrieben.

#### Ø Temperatur fehlt — keine eigene Messreihe <a name="temperatur_fehlt_ohne_messreihe"></a>

**Was eedc sieht**
In einigen erfassten Monaten ist das Feld «Ø Temperatur» leer, und für keinen davon reicht deine eigene Messreihe der
Außentemperatur zurück. Betroffen sind vor allem Monate, die zwischen Juli und September 2026 abgeschlossen wurden — da
füllte eedc das Feld nicht selbst. eedc rechnet mit diesem Feld heute keine Kennzahl aus; es ist die Rückfallebene für
Zeiten ohne Tagesreihe. Die Details nennen die Monate.

**Lösungsweg**
1. Am Befund **«Monat öffnen»** klicken — der erste betroffene Monat öffnet sich zum Bearbeiten.
2. Im Abschnitt «Wetterdaten (optional)» auf «Auto-Fill» klicken und speichern — eedc holt den Wert aus dem
   Wetter-Archiv. Die übrigen Monate ebenso unter [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt weniger Monate.

**Was ohne Handlung gilt**
Einmal täglich versucht eedc, leere Wetterfelder abgeschlossener Monate von der an der Anlage gewählten Quelle zu
füllen; ein Monat, für den sie an deinem Ort keinen gemessenen Wert liefert, bleibt ohne Ø Temperatur. Keine Kennzahl
rechnet heute mit dem Feld.

#### Ø Temperatur fehlt — eigene Messwerte reichen <a name="temperatur_aus_messung_moeglich"></a>

**Was eedc sieht**
In einigen erfassten Monaten ist das Feld «Ø Temperatur» leer; für einen Teil davon liegen eigene Messwerte der
Außentemperatur vor. Betroffen sind vor allem Monate, die zwischen Juli und September 2026 abgeschlossen wurden — da
füllte eedc das Feld nicht selbst. eedc rechnet mit diesem Feld heute keine Kennzahl aus (Außentemperatur-Linie und
Vergleich je Heizgradtag lesen die Tagesreihe); es ist die Rückfallebene für Zeiten ohne diese Reihe. Die Zeile nennt
beide Zahlen.

**Lösungsweg**
1. Am Befund **«Temperatur aus Messung übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**. eedc trägt die
   erreichbaren Monate aus deinen Messwerten nach (Stundenmittel, sonst Tages-Min/Max); bereits gepflegte Werte bleiben
   unberührt, mehrfaches Ausführen ist gefahrlos.
2. Für die übrigen Monate (die Details nennen sie): den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen, im Abschnitt «Wetterdaten (optional)» auf
   «Auto-Fill» klicken und speichern — eedc holt den Wert dann aus dem Wetter-Archiv.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; bleiben Monate ohne
   eigene Messwerte, steht statt ihrer die Zeile «Ø Temperatur fehlt in n Monat(en)» mit dem Knopf «Monat öffnen».

**Was ohne Handlung gilt**
Einmal täglich füllt eedc leere Ø Temperaturen abgeschlossener Monate von selbst — zuerst aus deinen Messwerten, sonst
aus dem Archiv der an der Anlage gewählten Quelle; Voraussetzung sind hinterlegte Koordinaten der Anlage. Der Knopf
erledigt es sofort. Keine Kennzahl rechnet heute mit dem Feld.

### 4.26 E-Mobilität – unbekannter Zustand <a name="426-e-mobilitaet--unbekannter-zustand"></a>

**Was wird geprüft:** Ein zugeordneter Zustand der E-Mobilität (Ladezustand, Lademodus, Fahrzeug-Ladezustand, Standort) liefert einen Wert, den eedc nicht kennt. eedc zeigt dann keinen Zustand an. Die Werte-Tabelle steht im Handbuch „Bedienung“, Abschnitt E-Mobilität ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)).

#### Zustand der E-Mobilität mit unbekanntem Wert <a name="emob_zustand_wert_unbekannt"></a>

**Was eedc sieht**
Ein zugeordneter Zustand der E-Mobilität («Ladezustand», «Lademodus», «Ladezustand (Fahrzeug)», «Zu Hause» oder eines
der Felder «evcc: Fahrzeug verbunden», «evcc: lädt», «evcc: Laden freigegeben») liefert gerade einen Wert, den eedc nicht
kennt. eedc zeigt dann keinen Zustand an. Die Details nennen den gelieferten Wert und die
Wörter, die eedc versteht; Groß-/Kleinschreibung ist egal.

**Lösungsweg**
1. In eedc ist dafür nichts umzustellen — der Wert kommt von deinem Gerät. In Home Assistant unter
   *Einstellungen → Geräte & Dienste → Helfer* einen Template-Sensor anlegen, der aus deinen Werten eines der Wörter
   macht, die eedc versteht (Werte-Tabelle im Handbuch «Einstellungen»,
   [Abschnitt 7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)).
2. Den neuen Sensor in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim Gerät an diesem Zustand
   zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald der neue Sensor einen
   bekannten Wert liefert; mit dem alten Sensor bleibt sie stehen.

**Was ohne Handlung gilt**
eedc zeigt für diesen Zustand nichts an, solange der Sensor den unbekannten Wert liefert. Mit einem bekannten Wert
erscheint der Zustand wieder.

### 4.27 E-Mobilität – Fahrzeug der Steuerung unbekannt <a name="427-e-mobilitaet--fahrzeug-unbekannt"></a>

**Was wird geprüft:** Die Steuerung (evcc, openWB) meldet am Ladepunkt einen Fahrzeugnamen, den kein E-Auto der Anlage als „Kennung in der Steuerung“ trägt. Die Wallbox-Karte zeigt dann nur „Fahrzeug der Steuerung unbekannt“; hier stehen der gemeldete Name und der Weg ([Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)).

#### Fahrzeug der Steuerung unbekannt <a name="emob_kennung_unbekannt"></a>

**Was eedc sieht**
Die Steuerung (evcc, openWB) meldet am Ladepunkt einen Fahrzeugnamen, den kein E-Auto der Anlage als „Kennung in der
Steuerung“ trägt. Die Wallbox-Karte zeigt dann nur „Fahrzeug der Steuerung unbekannt“. Die Zeile nennt den gemeldeten
Namen.

**Lösungsweg**
1. Am Befund **«Kennung eintragen»** klicken — mit genau einem E-Auto öffnet sich sein Formular am Feld
   «Kennung in der Steuerung (evcc vehicleName, openWB Fahrzeug)»; mit mehreren E-Autos öffnet sich die Seite
   «Komponenten» — dort beim passenden E-Auto das Stift-Symbol «Bearbeiten» klicken.
2. Am E-Auto den Namen genau so eintragen, wie die Steuerung das Fahrzeug nennt (Groß-/Kleinschreibung ist
   egal), und speichern. Ist es ein fremdes Fahrzeug, ist nichts zu tun.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; bei einem fremden Fahrzeug bleibt
   sie, solange es am Ladepunkt steht.

**Was ohne Handlung gilt**
Die Wallbox-Karte zeigt „Fahrzeug der Steuerung unbekannt“, statt den Ladevorgang einem deiner E-Autos zuzuordnen.
<!-- erzeugt: scripts/daten-checker-handbuch.py §4 Ende — nicht von Hand ändern -->

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

> ⭐ **Mit Home Assistant (seit HA-Bauform E4a-2):** eedc nimmt je Sensor seine Messung wie das Energie-Dashboard von Home Assistant. Jeder Erzeuger mit eigenem Zähler behält seinen Wert — auch wenn ihm einzelne Stunden fehlen —, und der Anlagen-Zählerstand füllt nur, was die Erzeuger ohne eigenen Zähler beigetragen haben, im Verhältnis ihrer kWp. Beispiel: Anlagenzähler 21 kWh, Süd misst 12, West misst 6, das Balkonkraftwerk hat keinen Zähler — es bekommt 3 kWh, gekennzeichnet als geschätzt. Der Kasten darunter beschreibt, wie eedc Tage ohne Home-Assistant-Statistik rechnet.
>
> ⚠ **Es zählt immer nur eine Seite — aber du verlierst nichts.** Für jeden Tag entscheidet eedc: Liefern **alle** deine Erzeuger den ganzen Tag über einen eigenen Zähler, gelten ihre Werte. Sonst gilt der **Anlagen-Zählerstand** — und eedc rechnet daraus aus, wie viel auf die einzelnen Erzeuger entfällt: Wer selbst gemessen hat, behält seinen Wert; die übrigen bekommen den Rest im Verhältnis ihrer kWp. Solche abgeleiteten Werte sind als abgeleitet gekennzeichnet, deine **Anlagensumme stimmt in jedem Fall** — und deine Monatswerte ohnehin.
>
> ⚑ Das gilt seit eedc 4.0.39 (gemeldet über GitHub #406). **Vorher** schaltete schon ein einziger eigener Zähler den Anlagen-Zählerstand für Tag und Stunde ab: Wer einem von drei Strings einen Zähler zuordnete, sah in *Cockpit → Tag* nur noch diesen einen. Und wer die Zuordnung mitten am Tag anlegte — der Zähler liefert dann erst ab dieser Stunde —, verlor die gemessene PV der Stunden davor. Beides ist behoben; ein betroffener Tag lässt sich unter *Einstellungen → Datenverwaltung → Mehrere Tage neu aggregieren* zurückholen.

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

**Symptom:** Befunde aus §4.4 *„MM/JJJJ fehlt"*, ab zwei Monaten als Gruppenzeile *„N Monate fehlen: …"*.

**Drei Wege, je nach Lückengröße:**

| Anzahl fehlender Monate | Empfohlener Weg |
|------------------------|-----------------|
| 1–3 Monate | Monatsdaten-Formular pro Monat (der Knopf „Monat erfassen" bzw. ein Klick auf den Monat in der Gruppenzeile führt direkt dorthin). |
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

> **Ohne Leistungskurve.** Liegt der Tag außerhalb der Aufbewahrung des Home-Assistant-Verlaufs (oder hat die Anlage keinen Leistungssensor) und hat auch die Langzeitstatistik keine Leistungskurve, schreibt „Tag neu aggregieren“ die Gerätewerte und Stunden-kWh trotzdem aus der **Zählerstatistik** von Home Assistant neu; der gespeicherte Leistungsverlauf und die Tagesspitzen bleiben stehen. Eigene Zählerstände von eedc nimmt der Lauf dafür nicht — sie tragen oft genau den Sprung, den du in Home Assistant korrigiert hast. Hat auch die Zählerstatistik nichts, bleibt der Tag unverändert.

> **Stundenwerte und Tages-Kennzahlen sind zwei Wege.** „Tag neu aggregieren“ baut Stundenwerte und Tageszeile neu. Die Tages-Kennzahlen der Energiebilanz (Netzbezug, Einspeisung, PV, Speicher) liest eedc, wo er den Tag deckt, aus dem **HA-Spiegel**, einer Kopie der HA-Langzeitstatistik, ohne Deckel wie das HA-Energie-Dashboard. Steht der Sprung in HAs Statistik selbst (§4.8b), hilft das Neu-Aggregieren dort nicht: in HA korrigieren, dann übernimmt der nächtliche Abgleich (02:45) die Korrektur — oder sofort **„HA-Spiegel jetzt abgleichen“** in der Werkbank.

**Vorgehen für mehrere Tage / längere Bereiche:**

1. Dieselbe Reparatur-Werkbank, Operation *„Mehrere Tage neu aggregieren"*.
2. Von-/Bis-Bereich angeben (Snapshots pro Tag werden frisch gezogen, Default an).
3. Ausführen — Resnap des gesamten Bereichs + Aggregat-Neuaufbau in einem Schritt. Kann bei mehreren Monaten Bestand einige Minuten dauern.

> Die Reparatur-Werkbank fasst die Operationen in einem einzigen Auswahlfeld zusammen (Tag / Mehrere Tage / Lücken nachfüllen / Kraftstoffpreise / Energieprofil-Daten löschen), gruppiert mit Trennlinien. Die frühere Bedienung über ein grünes Reload-Symbol pro Zeile in der Tages-Tabelle entfällt — die Tages-Tabelle selbst ist als **Anzeige** ins [Cockpit → Tag](HANDBUCH_BEDIENUNG.md#22-tag) umgezogen; repariert wird ausschließlich über die Werkbank.

**Lücke über Mitternacht — den Folgetag mitrechnen (ab v4.0.51).** Fehlt in Home Assistant die Stunde um Mitternacht, steht deren Energie wie im HA-Energie-Dashboard in der ersten Stunde des **Folgetags**. Wer einen solchen Tag repariert, nimmt deshalb den Folgetag mit (*„Mehrere Tage neu aggregieren"* über beide Tage); der Tag allein ändert sich dabei nicht, weil die Energie nicht in ihm liegt.

**Was die Rückmeldung sagt:** Steht ein Teil der neuen PV in einer Stunde, die eine Lücke trägt, nennt die Rückmeldung das: *„PV 10,0 → 28,0 kWh (davon 18,0 kWh aus einer Lücke in Home Assistant)"*. Nach einem Einzeltag-Lauf steht dort nicht nur, ob sich der PV-Wert bewegt hat, sondern auch, **für welche Komponenten der Lauf einen Wert schreiben konnte** — und, falls nicht für alle, welche leer geblieben sind. Ein „durchgelaufen" ohne geschriebenen Wert (typisch: kein Leistungssensor zugeordnet, oder die HA-Historie reicht nicht so weit zurück) erscheint als **Hinweis**, nicht als Erfolg. Beim Bereichs-Lauf ist es dieselbe Aussage je Tag: *„N Tag(e) neu aggregiert, M ohne verwertbare Daten übersprungen."*

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
| §4.9 Datenquellen – HA-Statistics | HA-Helfer „Verbrauchszähler" (ohne Zyklus), ersatzweise `customize` (state_class), Datenquellen-Zuordnung (alternativen Sensor wählen) |
| §4.10 Fehlende Tageswerte | Knopf am Befund: *„Tage neu aufbauen"* / *„Tag neu aufbauen"* (mit Vorschau); ohne Leistungs-Zuordnung *„Sensor zuordnen"* (Einstellungen → Datenquellen) |

### Reparatur-Werkzeuge in der Energieprofil-Pflege

Diese Werkzeuge laufen über die **Reparatur-Werkbank** unter Einstellungen → Daten → Energieprofil-Pflege (dieselbe Werkbank ist auch inline im Daten-Checker-Block erreichbar). Sie greifen aber **nur**, wenn die Voraussetzungen aus §4.9 erfüllt sind (Sensoren in HA-Long-Term-Statistics):

| Werkzeug (Werkbank-Operation) | Zweck | Voraussetzung |
|---------|-------|---------------|
| **Lücken aus HA-LTS nachfüllen** | Holt fehlende Tage aus HA-LTS für zugeordnete kWh-Felder (additiv, bestehende Tage bleiben unverändert). | §4.9 OK für betroffene Sensoren |
| **Mehrere Tage neu aggregieren** | Zieht Snapshots des Bereichs aus HA-LTS frisch (Resnap) **und** baut Tages-/Monats-Aggregate neu. Repariert Counter-Spikes wie aus §4.7. | §4.9 OK |
| **Tag neu aggregieren** | Wie *Mehrere Tage neu aggregieren*, aber für einen einzelnen Tag. Hat Home Assistant für den Tag keine Leistungswerte mehr (Verlauf gelöscht oder kein Leistungssensor) und auch die Langzeitstatistik keine Kurve, schreibt der Lauf die Gerätewerte aus der Zählerstatistik von Home Assistant neu und lässt den gespeicherten Leistungsverlauf stehen — die Rückmeldung sagt: „Gerätewerte aus der Home-Assistant-Statistik neu geschrieben; der gespeicherte Leistungsverlauf blieb stehen." Nur wenn auch die Zählerstatistik nichts hat, bleibt der Tag unverändert, und die Meldung sagt warum. | §4.9 OK |
| **HA-Spiegel jetzt abgleichen** | Gleicht den HA-Spiegel (Quelle der Tages- und Monats-Kennzahlen der Energiebilanz) sofort mit der HA-Statistik ab — derselbe Lauf wie nachts um 02:45. Nach einer Korrektur in HA (§4.8b). Stundenwerte und Tageszeile baut er nicht neu. | HA-Betrieb |
| **Kraftstoffpreise nachpflegen** | Holt EU-Oil-Bulletin-Preise für E-Auto- und Verbrenner-Vergleich rückwirkend. | unabhängig von §4.9 |

> **Wichtig:** Wenn §4.9 für einen Sensor WARNING meldet, sind die ersten drei Werkzeuge für diesen Sensor wirkungslos — sie lesen alle aus HA-LTS, die für state_class-lose Sensoren leer ist. Erst §4.9 beheben, dann Reparatur-Werkzeuge laufen lassen.

### Wo erscheint der Daten-Checker noch?

- **In-App-Hilfe** (Menüpunkt Hilfe): Diese Doku ist dort als kuratiertes Hilfe-Dokument verfügbar.
- **Knöpfe an den Befunden**: Ein Sprung-Knopf („Gerät bearbeiten", „Sensor zuordnen", „Monat erfassen" …) führt direkt auf das betroffene Feld ([Sprung aufs Feld](#sprung-aufs-feld)) — kein Suchen in den Kategorien nötig. Eine Reparatur („Wetterreihe nachziehen", „Tag neu aufbauen", „Aus Home Assistant neu übernehmen" …) zeigt zuerst die Vorschau am Befund; **„Details in der Werkbank"** öffnet sie in der **Reparatur-Werkbank**.
- **Komponenten-Achse**: Jede [Komponenten-Sicht](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse) hat einen Block **Daten-Qualität** mit den offenen Daten-Checker-Befunden genau dieser Komponente und Sprung zur Reparatur-Werkbank.
- **Aktivitäten-Log** (Einstellungen → System → Protokolle, Tab *Aktivitäten*): Bestimmte Befund-Kategorien (z. B. Connector-Test-Ergebnisse) finden sich auch dort historisch.

---

> **Verwandte Doku:**
> [Teil III §7 Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) · [Teil III §6.4 Statistik-Import](HANDBUCH_EINSTELLUNGEN.md#64-statistik-import) · [Teil III §6.1 MQTT-Broker-Verbindung](HANDBUCH_EINSTELLUNGEN.md#61-mqtt-broker-verbindung) · [Teil III §5.2 Energieprofil-Pflege](HANDBUCH_EINSTELLUNGEN.md#52-energieprofil-pflege) · [Teil III §9 Energieprofile-Hintergrund](HANDBUCH_EINSTELLUNGEN.md#9-hintergrund-energieprofile--snapshot-architektur)

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
