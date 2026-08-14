
# eedc Handbuch — Teil II: Bedienung

**Version 4.0** | Stand: 2026-07-25

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Navigation & Grundprinzip](#1-navigation--grundprinzip)
2. [Cockpit — die Zeit-Achse](#2-cockpit--die-zeit-achse)
3. [Komponenten — die Was-Achse](#3-komponenten--die-was-achse)
4. [Auswertungen — die Wie-Achse](#4-auswertungen--die-wie-achse)
5. [Community](#5-community)
6. [Daten erfassen im Alltag](#6-daten-erfassen-im-alltag)
7. [Hilfe in der App](#7-hilfe-in-der-app)
8. [Anhang: Wo ist X hin?](#8-anhang-wo-ist-x-hin)

---

## 1. Navigation & Grundprinzip

eedc ist um **drei Analyse-Achsen** herum aufgebaut. Statt vieler nebeneinander stehender Tabs beantwortet jede Achse eine andere Frage über dieselbe Anlage:

| Achse | Frage | Was du dort findest |
|-------|-------|---------------------|
| **Cockpit** | **Wann?** | Dieselben Kennzahlen auf verschiedenen Zeit-Ebenen: Live, Tag, Monat, Jahr/Gesamt, Aussicht |
| **Komponenten** | **Was?** | Detailsicht je Gerätetyp: PV-Anlage, Speicher, Wärmepumpe, Wallbox, E-Auto, Balkonkraftwerk, Sonstiges |
| **Auswertungen** | **Wie?** | Auswertende Sichten quer über die Zeit: Finanzen, ROI, Prognose-Genauigkeit, CO₂, Tabelle |

Daneben stehen in der oberen Leiste die **Community** (anonymer Vergleich mit anderen Anlagen) sowie die beiden Meta-Einträge **Hilfe** und **Einstellungen**.

### 1.1 Die drei Achsen im Detail

- **Cockpit (Wann):** Der Einstieg. Über eine Zeit-Leiste unter der Hauptnavigation wechselst du zwischen **Live** (jetzt), **Tag**, **Monat**, **Jahr/Gesamt** und **Aussicht** (Prognose). Der Aufbau jeder Zeit-Sicht ist bewusst ähnlich — Kennzahlen oben, Hauptdiagramm, dann Detail-Sektionen —, sodass du dich nur einmal orientieren musst.
- **Komponenten (Was):** Für jeden Gerätetyp, den deine Anlage besitzt, erscheint ein eigener Reiter. Er zeigt Status, Aufbau, Verlauf über die ganze Laufzeit, Jahresvergleich, Wirtschaftlichkeit und die Einstellungen genau dieser Komponente. Ein Reiter erscheint nur, wenn du mindestens ein Gerät des Typs erfasst hast.
- **Auswertungen (Wie):** Die auswertenden Gesamtsichten. Über Sub-Reiter erreichst du **Finanzen**, **ROI**, **Prognose** (Genauigkeit gegen IST), **CO₂** und die große **Tabelle** (Werte-Werkbank).

### 1.2 Community, Hilfe und Einstellungen

- **Community** ist ein eigener Hauptbereich mit dem anonymen Benchmark-Vergleich (siehe [§5](#5-community)).
- **Hilfe** öffnet dieses Handbuch direkt in der App — kein Tab-Wechsel, funktioniert auch in der HA-Companion-App (siehe [§7](#7-hilfe-in-der-app)).
- **Einstellungen** führt zu einem **Kachel-Raster** mit allen Konfigurations-Bereichen (Stammdaten, Komponenten erfassen, Infothek, Daten, Integration, Datenquellen, System). Alles Einrichten und Datenpflegen liegt dort — beschrieben in [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md).

Ganz oben rechts findest du außerdem einen **Theme-Umschalter** (Hell/Dunkel/System) und — auf schmalen Bildschirmen — ein **Hamburger-Menü**, das die Navigation einklappt.

### 1.3 Das Block-Modell: klappen, fokussieren, umsortieren, parken

Fast alle Sichten sind aus **Blöcken** aufgebaut — abgegrenzte Karten wie „Aktueller Status", „Verlauf" oder „Finanzen". Diese Blöcke kannst du an deine Arbeitsweise anpassen:

- **Ein-/Ausklappen:** Klick auf den Block-Kopf klappt ihn zu oder auf. Zwei Sammelknöpfe klappen alle Blöcke einer Sicht auf einmal auf bzw. zu.
- **Fokus / Vollbild (⤢):** Über das Vergrößern-Symbol öffnet sich ein Block als konzentrierte Vollbild-Ansicht — nützlich für ein Diagramm oder eine dichte Tabelle. Die Datums-/Zeit-Navigation der Sicht läuft im Fokus oben mit.
- **Reihenfolge ändern (↑ ↓):** In Cockpit- und Komponenten-Sichten lassen sich Blöcke verschieben, sodass du die für dich wichtigsten oben hast.
- **Einzelne Anzeigen parken:** Nicht nur ganze Blöcke, sondern einzelne Kacheln, Diagramme oder Tabellen kannst du **parken** (ausblenden). Am Seitenende zeigt eine Zeile „Geparkt (n)", über die du Geparktes jederzeit wieder einblendest. Ist alles in einem Block geparkt, verschwindet der Block selbst.

Deine Klapp-Zustände, die Reihenfolge und die geparkten Elemente werden **pro Sicht im Browser gespeichert** und bleiben nach einem Neustart erhalten. Ein **Zurücksetzen**-Knopf stellt die Standard-Anordnung einer Sicht wieder her.

> **Hinweis zum Layout:** eedc ist als datendichte Analyse-App primär für den Desktop gedacht. Live, Cockpit-Monat und die Komponenten-Sichten funktionieren auch am Smartphone gut; für die datendichten Tabellen (Auswertungen → Tabelle, Cockpit → Aussicht) empfehlen wir Querformat oder Desktop. **Weggesperrt ist dabei nichts:** wo eine Tabelle auf einem schmalen Bildschirm nicht lesbar wäre, zeigt eedc dieselben Daten als **Karten** — eine je Zeile —, etwa in *Auswertungen → Prognose*, in den Komponenten-Finanzen und im T-Konto. Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom) können einzelne Layouts eng werden — eine bewusste Designentscheidung statt Layout-Patches, die den datendichten Charakter aufweichen würden.

### 1.4 Anlagen-Auswahl und Status-Fußzeile

- **Anlagen-Auswahl:** Hast du mehrere Anlagen angelegt, wählst du die aktive Anlage über den **Anlagen-Selektor** in der oberen Leiste. Alle Sichten beziehen sich dann auf diese Anlage; die Auswahl wird gemerkt.
- **Status-Fußzeile:** Am unteren Rand läuft eine dünne Statusleiste mit drei Zonen:
  - **Links (global):** installations-weite Hinweise — aktuelle **Version / Update-Verfügbarkeit**, ein **offener Monatsabschluss**, der **Community-Teilen**-Status und die **MQTT-Verbindung**. Jedes Symbol öffnet bei Tipp/Klick ein kleines Popover mit Erklärung und oft einem Direktsprung zur passenden Stelle.
  - **Rechts (Sicht):** die **Frische** der gerade gezeigten Daten (z. B. ein Live-Punkt mit „(5 s)").
  - **Ganz rechts (Meta):** ein Demo-Schalter (nur im Debug-Betrieb).

  Die Farbe eines Symbols folgt der Schwere (grün = ok, blau = Info, amber = Warnung, rot = Fehler, grau = kein Zustand).

---

## 2. Cockpit — die Zeit-Achse

Das Cockpit zeigt die Bilanz und die Kennzahlen deiner Anlage auf **fünf Zeit-Ebenen**. Du wechselst sie über die Zeit-Leiste direkt unter der Hauptnavigation:

**Live · Tag · Monat · Jahr/Gesamt · Aussicht**

Nach dem Start landest du auf **Live**.

### 2.1 Live

Live zeigt **Echtzeit-Leistungsdaten** deiner gesamten Anlage und aktualisiert sich alle 5 Sekunden.

**Energiefluss-Diagramm** — das zentrale, animierte Element (ähnlich dem HA Energy Dashboard):

- **Haus** in der Mitte als Senke
- **Erzeuger** (PV-Module, Balkonkraftwerk) oben
- **Netz** links (bidirektional: Bezug / Einspeisung)
- **Speicher** rechts (bidirektional: Laden / Entladen)
- **Verbraucher** (Wärmepumpe, Wallbox, E-Auto, Sonstige) unten

Die **animierten Flusslinien** zeigen Richtung und Stärke: Liniendicke und Animationsgeschwindigkeit steigen mit der Leistung, Farbcodierung nach Komponententyp. Die **Netz-Farbe** wechselt dynamisch: grün (Balance), orange (Einspeisung), rot (Netzbezug). Bei Batterien und E-Autos wird der **Ladezustand (SoC)** als Pegel im Knoten dargestellt (rot < 20 %, gelb 20–50 %, grün > 50 %).

- **Hintergrund-Varianten** (Auswahl im Live-Kopf): Sterne (Standard), Sunset, Alps oder ein eigenes Foto aus der Anlagen-Galerie.
- **Lite- vs. Effekt-Modus:** Auf schwächeren Mobile-Geräten schaltet eedc automatisch in einen reduzierten Lite-Modus; im Effekt-Modus laufen zusätzlich Sonnenstrahlen, Reflexionen, Schneefunkeln und SoC-Partikel. Manueller Umschalter im Kopf.

**Tageswerte (bilanztreu sortiert)** — unterhalb des Diagramms als Kacheln, von den Quellen über den Eigenverbrauch zu den Verbrauchern:

1. **PV-Erzeugung** (heute, kWh)
2. **Batterie** (Lade- und Entladebilanz)
3. **Eigenverbrauch** (in % der PV-Erzeugung, gedeckelt auf 100 % — durch zusätzliche Batterie-Entladung aus Vortagen kann die Quote rechnerisch darüber laufen, das ist visuell nicht sinnvoll)
4. **Netzbezug**
5. **Hausverbrauch**
6. **Einspeisung** (PV-Überschuss ins Netz)

**Tagesverlauf-Diagramm** — Linien-/Flächendiagramm für PV/Verbrauch/Speicher, mit gepunkteter **Strompreis-Linie** auf zweiter Y-Achse:

- Ist ein eigener Strompreis-Sensor als Datenquelle zugeordnet (Tibber, aWATTar, EPEX, eigener Template-Sensor), heißt die Linie „Strompreis".
- Ohne eigenen Sensor greift automatisch der **EPEX-Börsenpreis** (DE/AT via aWATTar-API) → Linie „Börsenpreis (EPEX)"; auch die frühen Morgenstunden vor dem ersten Sensor-Wert werden so aufgefüllt.
- Ein Klick auf einen Legenden-Eintrag schaltet die jeweilige Serie ein oder aus.

**Börsenpreis heute & morgen** — ein eigener Block mit der **Day-Ahead-Kurve** über zwei Tage
auf einer durchgehenden Zeitachse:

- Die Linie ist **nach Preisniveau abgestuft**: **grün** unterhalb deiner Günstig-Schwelle,
  **lila** zwischen Schwelle und Tagesdurchschnitt, **rot** darüber. Zusammenhängende
  günstige Stunden sind zusätzlich als Fläche hinterlegt.
- Die **fünf günstigsten Stunden tragen die Ziffern 1–5** — je einmal für das Tag- und das
  Nachtfenster, also bis zu zehn Ziffern am Tag. Es ist derselbe Rang, den der Sensor
  `eedc_preis_rang` meldet. ⚠ **Rang und „günstig" sind zwei Aussagen:** die Fläche zeigt
  *alle* Stunden unter der Schwelle (das können mehr als fünf sein — die Zahl dient in
  Automationen als Teiler und ist deshalb nicht gedeckelt), die Ziffer zeigt die besten fünf.
- Darüber vier Kennzahlen für **heute**: aktueller Preis, der **Ø ohne die 3 teuersten Stunden**
  (die Bezugsgröße), die **Günstig-Schwelle** samt Anzahl der Stunden darunter und der
  **Abstand zum Ø in ct/kWh**. Es sind dieselben Zahlen, die auch die HA-Sensoren
  `eedc_preis_aktuell_cent`, `eedc_preis_optimierter_durchschnitt_cent`,
  `eedc_preis_guenstige_stunden_anzahl` und `eedc_preis_abstand_cent` melden.
- **Warum der Abstand in Cent und nicht in Prozent?** Weil du nicht den Börsenpreis zahlst,
  sondern Börsenpreis **plus** feste Bestandteile. Dieser Aufschlag verschiebt den Stundenpreis
  und das Tagesmittel um denselben Betrag — der **ct-Abstand bleibt deshalb gleich**, der
  Prozentwert nicht. Für eine Regel wie „lade, solange der Strom 5 ct unter dem Schnitt liegt"
  ist die ct-Zahl also die übertragbare Größe. Den prozentualen Abstand gibt es weiterhin als
  Sensor; Details in der [Sensor-Referenz](SENSOR-REFERENZ.md).
- **Jeder Tag hat seine eigene Schwelle** — Day-Ahead ist ein Tagesprodukt, und ein Durchschnitt
  über beide Tage würde an einem teuren Tag keine einzige Stunde als günstig ausweisen.
- Die Preise für **morgen** veröffentlicht die Auktion gegen **13 Uhr**. Vorher zeigt der Block
  nur heute und sagt, warum die zweite Hälfte fehlt.
- Es sind **Börsenpreise, netto** — ohne Steuern, Abgaben und Netzentgelte. Dein Lieferant
  rechnet andere Beträge ab; für die Frage, *welche* Stunde die günstige ist, zählt der Verlauf.
- Die **Günstig-Schwelle stellst du selbst ein** (Standard: 10 % unter dem Ø ohne Peaks) —
  siehe [Teil III](HANDBUCH_EINSTELLUNGEN.md). ⚠ **0 % schaltet die Schwelle nicht ab**, sondern
  legt sie genau auf den Durchschnitt.

> Der Block braucht **keine zugeordneten Sensoren** — Börsenpreise sind öffentliche Marktdaten.
> Er erscheint deshalb auch dann, wenn Live sonst noch „Keine Live-Daten verfügbar" meldet.
> Nur die Anlagen-Koordinaten müssen gepflegt sein: Aus ihnen ergibt sich, welche Stunden Tag
> und welche Nacht sind — die günstigsten fünf werden je Fenster getrennt bestimmt.
>
> eedc zeigt Preise und **empfiehlt keine Handlung**: Wann geladen, entladen oder pausiert wird,
> entscheidest du in deiner eigenen Automation.

**Wetter-Widget** — aktuelle Außentemperatur, Wolkenbedeckung und Stunden-Prognose als kleine Kachel.

**Demo-Modus** — ohne zugeordnete Datenquellen zeigt Live simulierte Werte, damit du die Darstellung vorab testen kannst. Der Börsenpreis-Block bleibt davon unberührt: Er zeigt auch dort die echte Marktkurve.

> **Woher kommen die Live-Daten?** Aus deinen zugeordneten **Datenquellen** — Home-Assistant-Sensoren, MQTT-Topics oder Geräte-Connectoren. Die Zuordnung pflegst du unter **Einstellungen → Datenquellen** (siehe [Teil III](HANDBUCH_EINSTELLUNGEN.md)).

### 2.2 Tag

Die **Tag**-Sicht bringt den feingranularen Stunden-Tag ins Cockpit: ein ausgewählter Kalendertag mit Stunden-Auflösung. Über die Datums-Navigation blätterst du zu beliebigen Tagen.

- **Stunden-Verlauf** von Erzeugung, Verbrauch und Speicher
- **Tagesbilanz** als Kennzahl-Strip (Summen des Tages)
- Detail-Sektionen je nach vorhandenen Komponenten

> **Wo steht der Speicher?** Nicht im obersten Kennzahlen-Block, sondern weiter unten im
> eingeklappten Block **Speicher** — seine Kopfzeile nennt schon ohne Aufklappen geladene kWh,
> Vollzyklen und Wirkungsgrad. Aufgeklappt stehen dort **Ladung**, **Entladung**,
> **Wirkungsgrad η**, **Vollzyklen** und der **Ladezustand**, dazu Netzladung, effektiver
> Ladepreis und die Tagesbilanz. Der **Ladezustand** zeigt den Stand am **Ende** des Tages und
> darunter die **Spanne**, zwischen der der Speicher an diesem Tag geschwungen ist — am laufenden
> Tag ist „Ende" die zuletzt aufgezeichnete Stunde. Ihn gibt es nur in der Tagessicht: Ein
> Ladestand ist ein Bestand, kein Fluss — über einen Monat gemittelt sagt er nichts. Den
> stündlichen Verlauf blendest du in der Stundenwerte-Tabelle über den Spalten-Auswähler als
> **SoC** ein.

> **Mehrere Dachflächen oder Balkonkraftwerke?** Hat **jedes** Gerät einen eigenen Ertragssensor,
> zeigt der Stunden-Verlauf die PV-Fläche **aufgeteilt** je Gerät statt als einen Block, und die
> Stundenwerte-Tabelle bekommt je Gerät eine Spalte hinter „PV". Aufgeteilt wird ab **zwei**
> Geräten. Was die Geräte nicht abdecken — etwa ein String ohne eigenen Sensor —, steht als
> **„PV (übrige)"** daneben; die Höhe der Kurve bleibt damit deine ganze Erzeugung. Auf Tagesebene
> rechnet eedc **nichts** nach Nennleistung auf die Geräte um: ohne Sensor keine Spalte. Die
> Tages-Historie je Gerät über einen längeren Zeitraum liegt in
> [Auswertungen → Tabelle](#45-tabelle-werte-werkbank).

Die Datenbasis sind kumulative Zähler-Snapshots (stündlich); die Tages-Werte folgen der Backward-Slot-Konvention (Slot N = Energie aus dem Intervall [N−1, N), Industriestandard). Fehlen Snapshots (z. B. durch eine HA-Statistik-Latenz oder einen Add-on-Neustart), weist eedc darauf hin und bietet eine Nachberechnung an — die Pflege dazu liegt unter [Einstellungen → Daten → Energieprofil-Pflege](HANDBUCH_EINSTELLUNGEN.md).

### 2.3 Monat

Die **Monat**-Sicht ist das Referenz-Muster der Zeit-Achse: ein ausgewählter Monat mit Tages-Granularität. Über den Monats-Zeitstrahl navigierst du zu beliebigen Vormonaten.

> **Womit die Sicht aufgeht:** mit dem **laufenden** Monat, solange kein Monatsabschluss offen ist. Fehlt noch ein Abschluss, öffnet sie stattdessen den jüngsten Monat, für den Werte gepflegt sind — dort beginnt der Weg zum offenen Abschluss, und der Knopf „Abschluss starten" steht daneben.

- **Kennzahl-Strip** oben — die wichtigsten Monatswerte mit Δ zum Vormonat
- **Energiebilanz** — PV-Erzeugung, Direktverbrauch, Einspeisung, Netzbezug
- **Finanzen** — Komponenten-Finanz-Tabelle (Saldo je Komponente) mit Sprung in die volle Finanzrechnung (siehe unten)
- **Komponenten-Sektionen** — Status je vorhandener Komponente mit kWh-Werten
- **Datenquellen-Kennzeichnung** — pro Feld ist die Herkunft der Werte sichtbar (HA-Statistik, MQTT, Connector, gespeichert)
- **SOLL/IST** — gegen die Solarprognose
- **Community-Vergleich** — eingebettet, wo Daten geteilt sind

> **Wenn ein Geräte-Connector nur einen Teil des Monats gemessen hat**, steht sein
> Zeitraum direkt am Quellen-Etikett: „Connector (28.–30.07.2025)". Ein Connector-Wert
> ist die **Differenz zweier Zählerstände** — richtest du ihn mitten im Monat ein, kennt
> er die Tage davor nicht, und der Wert ist entsprechend kleiner als der ganze Monat.
> Er verdrängt deshalb keinen gepflegten Monatswert mehr, sondern füllt nur, was sonst
> fehlt. Deckt der Connector den Monat ab dem Ersten ab, steht dort wie bisher schlicht
> „Connector". Die **Jahres**-Sicht nennt keinen Zeitraum — sie fasst zwölf Monate
> zusammen, dort gäbe es keinen einzelnen. Kann der Connector für den laufenden Monat
> **gar keinen** Wert bilden, meldet das der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md).

Aus dem feingranularen Stunden-Bestand des Monats zeigt die Sicht zusätzlich:

- **Performance Ratio (Ø Monat)** als Kennzahl
- **Erzeugung & Verbrauch nach Kategorie** — eine kompakte Anteils-Leiste über alle Erzeuger- und Verbraucher-Kategorien
- **Typisches Tagesprofil** — der stündliche Mittelwert von PV und Verbrauch über die Tage des Monats
- **Top-Stunden** — die stärksten Netzbezugs- und Einspeise-Stunden (Datum + Uhrzeit), nützlich zur Tarif-Optimierung
- **§51-EEG-Negativpreis** — Stunden mit negativem Börsenpreis, die dabei eingespeiste Energie, der Ø-Börsenpreis und der **§51-Verlust** (€): der Erlös, der dir für diese kWh entgeht. Das Anlage-Formular verspricht diesen Ausweis am §51-Schalter; von der neuen Oberfläche bis v4.0.0 zeigte ihn keine Sicht. Denselben Abzug tragen jetzt auch die Einspeise-Zeile des T-Kontos (`§51-Verlust: X kWh ohne Vergütung — Y € entgangen`) und der Kennwert „Einspeiseerlös" in [Auswertungen → Finanzen](#41-finanzen).

> **Aus der alten „Energieprofil (Beta)"-Sicht bewusst nicht übernommen:** die Tag×Stunde-Heatmap (kommt später neu gestaltet zurück) und der Wochentag-Wochenvergleich (entfällt — der Ø-gleiche-Wochentag-Rückblick in der Tag-Sicht deckt den Kern).

**Finanzen-Block** — der Monat (und analog [Jahr/Gesamt](#24-jahrgesamt)) trägt einen eigenen Finanzen-Block als **Komponenten-Finanz-Tabelle**: eine Zeile je Komponente (PV-Anlage, Speicher, Wärmepumpe, E-Auto …) mit den Spalten **Erträge** (tatsächliche Zahlungsflüsse), **Einsparungen** (kalkulatorisch — vermiedene Kosten), **Aufwand** und **Saldo**. Die **Summenzeile ist die Block-Kopf-Kennzahl** (Kopf == sichtbare Summe). Spaltenköpfe und Zeilen zeigen ihre Herleitung im **Tooltip** (Hover/Tipp). Netzbezug-Kosten und Grundgebühr stehen **nachrichtlich** darunter, nicht im Saldo verrechnet. Eine zusätzliche Zeile **„Ergebnis nach Stromrechnung"** (= Saldo − Netzbezug-Kosten) zeigt als **zweite Perspektive** das Haushaltsergebnis; der Komponenten-Saldo bleibt davon unberührt und ist weiterhin die Kopf-Kennzahl. Die **volle Finanzrechnung** (T-Konto je Investition, zeitraum-fähig) und die Finanz-Prognose liegen in [Auswertungen → Finanzen](#41-finanzen); der Block verlinkt direkt dorthin.

> **Die Kachel „Ø-Preis Netz" zeigt unter dem Preis die Arbeitspreis-Kosten** (`Netzbezug ×
> Ø-Preis`) — nicht die Gesamtsumme der Stromrechnung. So geht die Division auf: kWh und €
> der Unterzeile ergeben den Preis darüber. Der **Grundpreis** steht in der Herleitung
> (Tipp/Hover) mit der Gesamtsumme daneben, und im Finanzen-Block darunter sind weiterhin
> die vollen Netzbezug-Kosten ausgewiesen. Bei einem **flexiblen Tarif** ist der Ø-Preis der
> verbrauchsgewichtete Monatsdurchschnitt; mit ihm rechnen dann auch Kosten und
> Eigenverbrauchs-Ersparnis dieses Monats.

> **Zwei Netto-Größen nicht verwechseln:** Die Hero-Kennzahl **„Netto-Ertrag"** (z. B. in Jahr/Gesamt) beziffert die **PV-Anlage** allein (Einspeise-Erlös + Eigenverbrauchs-Ersparnis) und ist bewusst **nicht** identisch mit dem **Finanz-Block-Saldo**, der **alle Komponenten** (Wärmepumpe-, E-Auto-, Speicher-Beiträge und Sonstige Positionen) attribuiert zusammenfasst. Beide Zahlen sind korrekt — sie beantworten verschiedene Fragen (reine PV-Wirtschaftlichkeit vs. Gesamt-Saldo aller Komponenten). Die volle Herleitung steht in [Berechnungen §3.2](BERECHNUNGEN.md#32-finanzen-cockpit).

Die **Erfassung** eines Monats (Zählerstände, Monatsabschluss) läuft über das Formular unter [Einstellungen → Daten → Monatsdaten](HANDBUCH_EINSTELLUNGEN.md); ein offener Monatsabschluss wird zusätzlich in der Status-Fußzeile angezeigt.

**Leerer Zustand:** Liegen für den Monat keine Daten vor, bietet eedc konkrete Erfassungs- und Import-Wege als Aktionskarten an.

### 2.4 Jahr/Gesamt

Die **Jahr/Gesamt**-Sicht fasst die Anlage über ein ganzes Jahr bzw. über die gesamte Laufzeit zusammen (Summe der Monate). Über den Selektor wählst du ein Jahr oder „Gesamt".

**Hero-Kennzahlen** — die drei wichtigsten Werte prominent, je mit Trend-Pfeil zum Vorjahr:

- **Autarkie** (%), **Spezifischer Ertrag** (kWh/kWp), **Netto-Ertrag** (€)

> Der **Netto-Ertrag** hier ist die **PV-Anlagen-Größe** (Einspeise-Erlös + Eigenverbrauchs-Ersparnis) — nicht der komponenten-übergreifende **Finanz-Block-Saldo** (siehe [§2.3](#23-monat), „Zwei Netto-Größen nicht verwechseln"). Der Finanzen-Block als Komponenten-Finanz-Tabelle erscheint auch in Jahr/Gesamt, dann über alle Monate summiert.

**Energiefluss (zwei Balken):**

- **PV-Verteilung** — wohin fließt der erzeugte Strom? (Direktverbrauch / Speicher / Einspeisung)
- **Haus-Versorgung** — woher kommt der Strom im Haus? (PV direkt / Speicher / Netzbezug)

**Energiebilanz** — PV-Erzeugung, Direktverbrauch, Einspeisung, Netzbezug, plus eine **Sparkline** der Monatserträge über den Gesamtzeitraum.

> **Warum weicht der Gesamtverbrauch von meinem Herstellerportal ab?** eedc bilanziert den Verbrauch aus deinen Werten: `Erzeugung − Einspeisung − Speicher-Ladung + Speicher-Entladung + Netzbezug`. Viele Hybrid-Wechselrichter (z. B. E3DC) messen PV und Speicher **DC-seitig**, Einspeisung und Netzbezug aber **AC-seitig** — dann enthält der Gesamtverbrauch die Wandlungsverluste und liegt rund **3–5 % der Erzeugung** über dem „Hausverbrauch" im Portal, das seine Verluste herausrechnet. Beide Werte stimmen: eedc zeigt, was deine Anlage liefern musste (die richtige Basis für Autarkie und Wirtschaftlichkeit — bezahlt werden muss auch der Verlust), das Portal, was die Verbraucher gezogen haben. Details und ein Rechenrezept zum Nachprüfen stehen in der [Berechnungsreferenz 3.1](BERECHNUNGEN.md#31-energie-bilanz-monatskennzahlen).

> **Welche Monate die Jahreszahl umfasst.** Ein Monat zählt zum Jahr, sobald er **Daten trägt** — nicht erst, wenn du ihn im Monatsabschluss abgeschlossen hast. Das ist ein Unterschied: die Zählerstände eines Monats trägst du oft erst Wochen später nach, die Messwerte deiner Komponenten liegen längst vor. Bis dahin fehlte dieser Monat der Jahreszahl vollständig. Der Kopf des Kennzahlen-Blocks nennt das Fenster, sobald es kein volles Jahr ist (`Jan–Aug · 5 Energie-Kennzahlen …`); **auch mehrere offene Monate** werden so gefunden, ebenso eine Lücke mitten im Jahr.
>
> **Womit sich das Jahr vergleicht — und über welche Monate.** Die Energiebilanz stellt dem **IST** zwei Vergleichsspalten gegenüber: das **Vorjahr** und den **Ø der übrigen Jahre**. Verglichen wird über die **abgeschlossenen** Monate, und zwar auf **allen** Spalten gleich — der laufende Monat bleibt außen vor. Sonst stünden zwei Augusttage gegen einen vollen August des Vorjahrs. Auch das Vergleichsjahr wird beschnitten: im laufenden Jahr stünden sonst die bisher gelaufenen Monate gegen ein volles Vorjahr — im Juli sechs gegen zwölf, und die PV-Erzeugung sähe um fast die Hälfte eingebrochen aus, obwohl nichts passiert ist. Eine **Lücke mitten im Jahr** wirkt genauso: verglichen werden immer *dieselben* Monate, nicht „die ersten N".
>
> **Deshalb sind Kachel und Tabelle nicht dieselbe Zahl** — die Kachel zählt das Jahr **bis heute**, die Tabelle bis zum letzten abgeschlossenen Monat. Beide sagen, worauf sie sich beziehen: der Block-Kopf über den Kacheln (`Jan–Aug`), der Kopf der IST-Spalte und der Bilanz-Block-Kopf (`Jan–Jul`), dazu ein Satz unter der Tabelle („… · Kennzahlen oben: Jan–Aug").
>
> **Steht dort weniger als ein volles Jahr, sagt die Anzeige es** — am Spaltenkopf, an den Kennzahl-Kacheln (`VJ (Jan–Jul): 5.146 kWh`) und als Satz unter der Tabelle („Vergleich beschnitten auf die gemeinsamen Monate: Jan–Jul"). In den **Ø der übrigen Jahre** geht nur ein Jahr ein, das dieses Fenster **ganz** abdeckt: Ist deine Anlage im Juni 2023 in Betrieb gegangen, trüge 2023 zu einem Vergleich über Jan–Jun nur einen einzigen Monat bei — dann bleibt das Jahr draußen, und die Zeile darunter zählt entsprechend („Ø aus 2 Jahren" statt 3). Hat das Vorjahr **gar keinen** gemeinsamen Monat, entfällt die Vergleichsspalte („—"), statt 0 zu zeigen. Bei einem abgeschlossenen Jahr mit vollständigen Daten ändert sich nichts.
>
> *Bis Version 4.0.6 verglich diese Sicht das laufende Jahr mit vollen Vorjahren. Wenn deine Vorjahres- und Ø-Spalten kleiner geworden sind und die Δ-Prozente moderater ausfallen, ist das die Korrektur — deine Anlage hat sich nicht verändert.*
>
> *Ebenfalls bis 4.0.6 fehlte der Jahreszahl jeder Monat ohne Monatsabschluss. Wenn deine Jahres-Erzeugung sichtbar **gestiegen** ist, ist das die Korrektur — die alte Zahl war zu klein. Am Beispiel einer Testanlage im August 2026: 7.703 kWh vorher, 9.547 kWh nachher, weil der volle Juli fehlte.*

**Effizienz-Quoten (Ring-Anzeigen):**

- **Autarkie** = (Gesamtverbrauch − Netzbezug) / Gesamtverbrauch × 100 %
- **Eigenverbrauchsquote** = Eigenverbrauch / PV-Erzeugung × 100 %

**Komponenten-Status** — Schnellstatus aller Komponenten mit Sprung in die jeweilige Komponenten-Sicht. Wärmepumpe-, Speicher-, E-Auto- und Wallbox-Kennzahlen verwenden durchgängig dieselben Icons, Farben und Reihenfolgen wie überall in eedc.

**Trend-Historie** — Jahresvergleich und saisonale Muster (beste/schlechteste Monate) über alle bisherigen Jahre. Die reine **Degradations-Prognose** (geschätzter Leistungsrückgang pro Jahr) liegt dagegen in der [Aussicht](#25-aussicht).

**Speicher im Jahr** — der Block erscheint, wenn im gewählten Jahr ein Speicher Bewegung hatte. Er zeigt eine Zeile je Monat (neueste zuerst) mit **Ladung**, **Entladung**, **Vollzyklen**, **Solar-Anteil** der Ladung, **Auslastung** und **Netto-Nutzen** in Euro, dazu eine Gesamtzeile und darunter einen Vergleich der beiden Saison-Fenster **Sommer (Jun–Aug)** und **Winter (Nov–Feb)**.

- **Auslastung** = Entladung ÷ (Kapazität × Tage des Zeitraums). Sie beantwortet „wie viel von dem, was der Speicher hergäbe, nutze ich tatsächlich" — und ist anders als die Vollzyklen zwischen einem kurzen Februar und einem langen Juli direkt vergleichbar. Im **laufenden** Monat zählen nur die bereits abgelaufenen Tage; sonst stünde am 3. eine Zahl, die mehr über das Datum aussagt als über den Speicher. Werte über 100 % sind möglich und richtig — dann wurde mehr als eine Kapazität pro Tag durchgesetzt.
- **Netto-Nutzen** ist derselbe Betrag, der im Finanzen-Block desselben Monats in der Speicher-Zeile steht: die entladene Energie ersetzt Netzbezug, abzüglich der Einspeisevergütung, die sie sonst erbracht hätte. Aus dem **Netz** geladene Energie zählt getrennt, sie hätte nie eingespeist werden können (Details: [Berechnungsreferenz 3.3](BERECHNUNGEN.md#33-speicher-einsparung)).
- **Leere Felder sind Absicht.** Ohne gepflegte **Kapazität** stehen Vollzyklen und Auslastung auf „—" statt auf 0 — ein Speicher ohne Kapazitätsangabe ist ein *unbekannter*, kein ungenutzter; der Daten-Checker weist darauf hin. Ohne gepflegte **Netzladung** bleibt der Solar-Anteil leer, statt 100 % zu behaupten.
- Die beiden Saison-Fenster sind **Fokus-Zeiträume, keine Aufteilung des Jahres**: Frühjahr und Herbst zählen in keinem von beiden. Das steht auch unter der Tabelle.

> Die **Tiefe** zum Speicher — „hätte mehr Kapazität etwas gebracht?" und der Sizing-Rechner — gehört nicht hierher, sondern in den [Komponenten-Hub](#3-komponenten--die-was-achse): dort steht, was über die **Lebensdauer** des Geräts geht, hier, was sich auf einen **Zeitraum** bezieht.

**CO₂-Bilanz** — ein eigener Block mit dem Verlauf der vermiedenen Emissionen. Das gestapelte Monats-Diagramm trennt die drei Quellen, aus denen die Ersparnis entsteht: **PV/Eigenverbrauch** (vermiedener Netzstrom), **Wärmepumpe** (vermiedene fossile Wärme) und **E-Mobilität** (vermiedener Kraftstoff); die Autarkie desselben Monats läuft als Linie mit. Über dem Diagramm stehen zwei Kennwerte, die sich bewusst auf **verschiedene Zeiträume** beziehen:

- **CO₂ eingespart** — die Summe des **gewählten Jahres**; sie ändert sich, wenn du das Jahr wechselst.
- **CO₂ kumuliert** — die **gesamte Historie** seit Inbetriebnahme; sie bleibt beim Jahreswechsel stehen. Der Kennwert sagt das auch dazu.

Wie bei jedem Block lässt sich der Verlauf über ⤢ auf **Vollbild** stellen und dort zwischen Diagramm und **Tabelle** umschalten (mit CSV-Export).

> **Nicht zu verwechseln mit der CO₂-Amortisation** unter **Auswertungen → CO₂** (§4.4). Diese Sicht hier beantwortet „**wann** habe ich wie viel gespart" — Zeitverlauf, nach Quelle getrennt. Die Amortisation beantwortet „**wann ist die Herstellungs-CO₂ meiner Komponenten wieder eingespielt**" (Lebensdauer) und rechnet deshalb immer über die gesamte Historie, nie über ein einzelnes Jahr.

> **Entfallen: die Social-Media-Textvorlage.** Bis Version 3 konntest du über ein Teilen-Symbol im Kopf des Cockpits einen kopierfertigen Text für Social-Media-Posts erzeugen. Mit der neuen Oberfläche (v4) ist diese Funktion weggefallen; dieser Abschnitt hat sie bis Juli 2026 weiter beschrieben. Nicht gemeint ist das **Teilen mit der Community** — das gibt es unverändert, siehe [5. Community](#5-community).

**Kennzahl-Tooltips** — jede Kennzahl zeigt bei Hover/Tipp Formel, eingesetzte Zahlen und Ergebnis. Bei ROI- und Amortisations-Werten kommt eine **„Sicht"-Zeile** hinzu, die die Bezugsbasis klärt (pro Investition vs. gesamt, Jahres-ROI vs. kumuliert, IST vs. Prognose) — eedc zeigt bewusst mehrere ROI-Sichten parallel.

### 2.5 Aussicht

Die **Aussicht** bündelt alle vorwärtsgerichteten Analysen auf einer Seite. Über einen **Horizont-Selektor** wählst du, wie weit du blickst — von den nächsten Tagen bis zur langfristigen Jahresprognose.

**Kurzfristig (nächste 7–14 Tage):**

- Datenquelle: Open-Meteo-Wetterprognose
- Tägliche Erzeugungsschätzung auf Basis der Globalstrahlung, kalibriert mit dem **eedc-Lernfaktor**, sobald genug IST-Daten vorliegen
- Wettersymbole und ein Datenquelle-Kürzel je Tag (MS = MeteoSwiss ICON-CH2, D2 = ICON-D2, EU = ICON-EU, EC = ECMWF IFS, BM = best_match)
- Die Tagesbalken tragen den **erwarteten kWh-Ertrag direkt am Balken** (Balkenlänge = PV-Ertrag), sodass sich die Tage ohne Achsenablesen vergleichen lassen
- Ist **Solar Forecast ML (SFML)** konfiguriert, erscheint eine zweite KI-basierte Ertragslinie
- Das Wettermodell lässt sich pro Anlage fest wählen (Einstellungen → Stammdaten → Anlage → Wettermodell); ohne Auswahl entscheidet eedc automatisch.

**Stundenwerte mit IST:** Steht der Tages-Picker auf **heute**, zeigt die Stundentabelle neben der Prognose eine Spalte **PV IST** mit den bereits gemessenen Stunden; die Summenzeile addiert nur das Gemessene, künftige Stunden bleiben leer. Für andere Tage entfällt die Spalte — dort gibt es kein IST.

**Prognose-Vergleich / Genauigkeit:** Die tiefergehende Bewertung mehrerer Prognosequellen (OpenMeteo, eedc kalibriert, Solcast, IST) mit MAE/Bias und Stundenprofilen findest du in [Auswertungen → Prognose](#43-prognose-genauigkeit-gegen-ist).

**Langfristig:**

- PVGIS-basierte Jahresprognose (Erwartungswerte oder TMY)
- **Performance Ratio**: historischer Vergleich IST vs. SOLL auf Basis der Global Tilted Irradiance (GTI)
- monatliche Aufschlüsselung der erwarteten Erzeugung

**Degradations-Prognose:** geschätzter Leistungsrückgang pro Jahr, primär aus vollständigen Jahren (12 Monate), Fallback über TMY-Auffüllung für unvollständige Jahre.

> **Datenkonvention:** Alle Quellen der Aussicht nutzen die **Backward-Slot-Konvention** (Slot N = Energie aus [N−1, N)). Damit liefert IST um 06:00 noch 0 kWh, und Tagessummen passen exakt zur Stundensumme — Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber).

---

## 3. Komponenten — die Was-Achse

Die **Komponenten**-Achse zeigt jeden Gerätetyp einzeln und in der Tiefe. Unter der Hauptnavigation erscheint für **jeden Typ, den deine Anlage besitzt**, ein eigener Reiter. Die Reihenfolge ist einheitlich (Erzeuger, Speicher, Verbraucher); ein Reiter fehlt, solange du keine Komponente dieses Typs erfasst hast.

Mögliche Reiter: **PV-Anlage · Speicher · Balkonkraftwerk · Wärmepumpe · Wallbox · E-Auto · Sonstiges**.

> **Erfassen vs. Auswerten:** Diese Achse **wertet aus**. Neue Geräte anlegen oder Parameter ändern tust du unter **Einstellungen → Komponenten**. Aus jeder Komponenten-Sicht führen Bearbeiten-Links direkt dorthin.

### 3.1 Gemeinsamer Aufbau je Komponente

Jede Komponenten-Sicht bezieht sich auf den **Gesamtzeitraum** (kein Datums-Selektor — zeitliche Differenzierung erledigt das Cockpit) und ist aus denselben Block-Bausteinen aufgebaut. Wie in allen Sichten kannst du die Blöcke klappen, umsortieren, fokussieren und einzelne Anzeigen parken (siehe [§1.3](#13-das-block-modell-klappen-fokussieren-umsortieren-parken)).

| Block | Inhalt |
|-------|--------|
| **Aktueller Status** | die Kernkennzahlen des Typs (immer offen) |
| **System-Struktur / Zuordnung** | Aufbau und Kopplung (z. B. Wechselrichter → Module/Speicher) bzw. Herkunft der Werte — sofern für den Typ sinnvoll |
| **Sub-Komponente** | untergeordnete Kennzahlen (z. B. gekoppelter Speicher) — sofern vorhanden |
| **Verlauf (gesamte Historie)** | Zeitreihe über die komplette Laufzeit, oft mit Verteilungen und Monats-Detailtabelle |
| **Vergleich** | Jahresvergleich bzw. komponentenspezifische Analyse |
| **Wirtschaftlichkeit** | Ertrags-Zusammensetzung bzw. Kostenvergleich; ohne belastbares Modell ehrlich als „nicht bewertet" |
| **Dokumente & Infos** | mit dieser Komponente verknüpfte Infothek-Einträge (Verträge, Datenblätter) |
| **Daten-Qualität** | offene Daten-Checker-Befunde genau dieser Komponente, mit Sprung zur Reparatur-Werkbank |
| **Einstellungen** | Parameter und Datenquellen-Zuordnungen dieser Komponente, mit Bearbeiten-Links |

Blöcke, die für einen Typ keine Daten haben, werden ehrlich als „im Bau" / „keine Daten" markiert statt mit Platzhalter-Zahlen gefüllt. Hat eine Anlage **mehrere Geräte desselben Typs** (z. B. zwei Wärmepumpen), erscheint oben ein **Geräte-Selektor**.

> **Diese Achse rechnet mit *abgeschlossenen* Monaten — das ist der Unterschied zum Cockpit.**
> Eine Komponenten-Sicht ist die **Lebenslauf-Sicht** eines Geräts: Zyklen, Wirtschaftlichkeit und
> Amortisation entstehen aus den Monatswerten, die du im Monatsabschluss erfasst oder importierst.
> Ein Gerät, das du **im laufenden Monat** angeschafft hast, steht hier deshalb zunächst auf Null,
> obwohl **Cockpit → Tag** und **Cockpit → Monat** es längst zeigen — die rechnen aus den laufenden
> Sensorwerten. Die Sicht sagt das auch: Über den Blöcken steht der Grund und der Weg dorthin, wo das
> Gerät heute schon zu sehen ist. Dasselbe gilt für Geräte, die stillgelegt oder auf inaktiv gesetzt
> sind.

> **Wo ist die „Aussicht" je Komponente?** Bewusst nicht im Hub. Zeitlich-vorausschauende Sichten laufen zentral über [Cockpit → Aussicht](#25-aussicht).

### 3.2 PV-Anlage

Der PV-Reiter fasst **Wechselrichter, zugeordnete Module und DC-Speicher** zu einem System zusammen.

- **Wechselrichter-Übersicht** mit zugeordneten Modulen (System-Struktur zeigt die Topologie WR → Module/Speicher, inkl. Hinweis auf Module/Speicher ohne Zuordnung)
- **String-Vergleich** nach Ausrichtung (Süd, Ost, West)
- **Spezifischer Ertrag** (kWh/kWp) — wichtig für Vergleiche
- **SOLL/IST** gegen die Solarprognose; konsistente Farben (SOLL blau, IST amber, positive Abweichung grün)
- **Performance Ratio** auf Basis der Global Tilted Irradiance (GTI) — bei steilen Modulen und tiefer Wintersonne realistischer als auf GHI-Basis (verhindert physikalisch unmögliche PR-Werte > 1)

Bei **Einzel-String-Anlagen** (genau eine PV-Modul-Investition) entfällt die redundante „Stringsumme"-Zeile.

> **Drei Zahlen, drei Fragen — die Spalten der String-Tabelle:**
> **Performance** misst jeden String gegen **seine eigene** Prognose; Ausrichtung und Neigung stecken
> also schon in der Vorgabe. Ein Nordwest-Dach mit 100 % erfüllt genau das, was für Nordwest zu
> erwarten war — es ist damit *nicht* so gut wie ein Süd-Dach mit 100 %.
> **kWh/kWp** ist die Kennzahl für den Vergleich der Dächer untereinander (dort liegt die bessere
> Ausrichtung vorn, auch mit weniger Modulen).
> **Anteil** zeigt das Gewicht am Gesamtertrag — hier gewinnt in der Regel die größere Fläche.
> Die Fußzeile summiert kWp, SOLL und IST der ganzen Anlage.

> **Die Modulwerte sind gemessen, wo sie gemessen sind — und gekennzeichnet, wo sie gerechnet sind.**
> Der Block **„Verlauf"** zeigt seit v4.0.1 die **eigenen Messwerte** je Modul; bis v4.0.0 zerlegte er
> die Gesamterzeugung stur nach Nennleistung, wodurch ein verschatteter oder abgeschalteter String
> unsichtbar blieb und alle Module rechnerisch denselben spezifischen Ertrag hatten. Der Block
> **„Vergleich"** zeigt dieselben Messwerte — **beide Blöcke einer Karte sagen jetzt dasselbe.**
>
> Wer **nur einen Gesamt-Sensor** für mehrere Strings hat, sieht in beiden Blöcken erstmals Werte, wo
> vorher 0 bzw. eine leere Sicht stand: die Gesamterzeugung anteilig nach Nennleistung verteilt und
> mit einer **Herkunfts-Zeile „geschätzt (kWp-Anteil)"** gekennzeichnet. Die 0 war die unehrlichere
> Anzeige — erzeugt wurde ja etwas.
>
> **Gemischt erfasst? Dann bleibt gemessen gemessen.** Misst ein Teil der Strings selbst und ein Teil
> nicht, behalten die messenden Module ihren echten Wert; nur die übrigen bekommen den **Rest** des
> Gesamtwerts nach Nennleistung. Bis v4.0.1 kippte in dieser Lage die ganze Anlage auf kWp-Anteile —
> ein einziger Sensor-Aussetzer reichte, und die Messwerte der anderen Strings waren für den Monat
> verschwunden.
>
> **Solange die Werte verteilt sind, nennt eedc bewusst keinen besten und keinen schwächsten String.**
> Eine Platzierung wäre dort nur die Reihenfolge der Nennleistungen. Wer das Ranking zurückhaben will,
> gibt jedem Modul einen eigenen Erzeugungs-Sensor
> ([Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung)).
>
> **Der Erzeugungs-Stapel im Verlauf zeigt alle Erzeuger hinter dem Zähler** — Module,
> Balkonkraftwerk und sonstige Erzeuger je als eigenes Segment; er heißt bei mehreren Quellen
> „Erzeugung nach Quelle" statt „nach Modul". So sind der Erzeugungs- und der Verwendungs-Stapel
> daneben **summengleich**; vorher stand links nur die Modul-Erzeugung und rechts die Verwendung der
> *gesamten* Erzeugung.

**SOLL/IST verstehen:**

| Kennzahl | Bedeutung |
|----------|-----------|
| **SOLL** | erwarteter Ertrag aus Standort, Ausrichtung, Neigung |
| **IST** | tatsächlich gemessener Ertrag |
| **Abweichung** | positiv = besser als erwartet, negativ = schlechter |

Typische Abweichungen: ±5 % normal (Wetter), ±10–15 % prüfen (Verschattung? Verschmutzung?), > 20 % Handlungsbedarf (Defekt? Fehlkonfiguration?).

> **Ohne PVGIS-Prognose** entfallen SOLL, Abweichung und Performance — deine **gemessenen** Erträge
> je String, ihr Anteil am Gesamtertrag und der spezifische Ertrag (kWh/kWp) bleiben sichtbar. Eine
> Zeile oben sagt, dass die Prognose fehlt und wo du sie abrufst
> ([Einstellungen → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)). Bis Version 4.0.8
> blendete diese Sicht ohne Prognose **alles** aus, auch die Messwerte.

> **Im laufenden Monat zählt das SOLL nur die vergangenen Tage** — steht am 4. August ein SOLL von
> 179 kWh statt der 1.388 kWh des ganzen Monats, ist das kein Fehler: verglichen wird der bisherige
> Ertrag mit dem, was bis heute zu erwarten war. Die Kachel schreibt das Fenster dazu
> („anteilig · 4 von 31 Tagen"); mit dem Monatsabschluss steht dort wieder der volle Monat.



### 3.3 Speicher

- **Vollzyklen** = entladene Energie ÷ Kapazität — dieselbe Zahl in Tag, Monat, Jahr, PDF und HA-Sensor. Gezählt wird die *entnommene* Energie (darauf zielen Hersteller-Garantien), geteilt durch die **Brutto**-Kapazität. Wer eine „nutzbare Kapazität" gepflegt hat, findet sie beim Wirkungsgrad wieder, nicht hier ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)).
- **SoC-Hübe** (Energieprofil-Tagestabelle, optionale Spalte) — die zweite, andere Zahl: sie summiert die tatsächlichen Ladestands-Bewegungen (ein voller Hub 0→100→0 = 1). Wer den Speicher zwischen 10 und 90 % fährt, sieht hier 0,8 pro Hub. Sie braucht einen SoC-Sensor und ist ausschließlich aus dem **stationären** Speicher-SoC gebildet; E-Auto-SoC ist zuverlässig ausgeschlossen.
- **Effizienz** = Entladung / Ladung × 100 % (durchgängig cyan)
- **Degradation** (Kapazitätsverlust über die Zeit)
- **Arbitrage-Analyse** (wenn aktiviert): Netzladung zu günstigem Strom, Entladung bei hohem Preis, Arbitrage-Gewinn
- **„Hätte mehr Kapazität geholfen?"** (Block *Wirtschaftlichkeit*) — die Sizing-Frage, beantwortet aus deinen Stundenwerten. Siehe unten.
- **„Größerer Speicher?"** (eigener Block) — die Anschlussfrage *wie viel* und *zu welchem Preis*, mit Schieberegler. Siehe unten.

#### Hätte mehr Kapazität geholfen?

Die Auswertung zählt **nicht** einfach, wie viel Strom ins Netz ging, während der Speicher voll war. Diese Zahl steht zwar da — aber ausdrücklich als **Obergrenze**, denn sie überschätzt den Nutzen systematisch: Zusätzliche Kapazität bringt nur dann etwas, wenn der Speicher vor dem nächsten Sonnenaufgang auch **leer läuft**. Tut er das nicht, hätte ein größerer Speicher morgens bloß mehr Restladung — und niemand hätte sie abgenommen.

An einer echten Anlage gemessen: zwölf Junitage, 471 kWh Einspeisung bei vollem Speicher, aber kein einziges Leerlaufen in der Nacht ⇒ **Nutzen 0 kWh**. Im Winter kehrt es sich um: dort läuft der Speicher jede Nacht leer, es kommt nur kaum Überschuss an, den er aufnehmen könnte.

Deshalb zeigt der Block drei Zahlen nebeneinander:

- **Nutzbares Zusatzpotential** — was ein größerer Speicher wirklich zusätzlich durchgesetzt hätte (je Lade-Entlade-Zyklus das Minimum aus Überschuss und nächtlichem Bedarf)
- **Überschuss bei vollem Speicher** — die Obergrenze, nicht der Ertrag
- **Nächte mit leerem Speicher** — die eigentliche Begrenzung

Dazu eine Grafik mit **drei Spuren über dieselbe Monatsachse**:

- **Ladestand über den Monat** — ein Balken je Monat zeigt, wo dein Speicher in **acht von zehn Stunden** stand; die Linie darin ist der typische Wert. Die kurzen Striche am oberen und unteren Rand sind die **Anschläge**: wie oft er voll (≥ 95 %) bzw. leer (≤ 5 %) war. Erst wenn im selben Monat **beide** Striche breit sind, ist mehr Kapazität eine ernsthafte Überlegung — oben angeschlagen heißt „Überschuss ging ins Netz", unten „die Nacht wurde zugekauft".
- **Durchsatz je Monat** — Vollzyklen, also entladene Energie geteilt durch die Kapazität. Ohne sie sieht ein Speicher, der dreimal am Tag durchfährt, aus wie einer, der stillsteht: der Ladestand allein zeigt Zustände, keine Umsätze. Der Wert kann über 100 % der Kapazität liegen, und das ist korrekt.
- **Ladung aus dem Netz** — erscheint nur, wenn es sie gab. Netzladung füllt den Speicher **ohne Sonne**; solche Monate beantworten die Frage nach mehr Kapazität nur eingeschränkt. Der Anteil ist eine **Obergrenze**: innerhalb einer Stunde trennt kein Zähler, was ins Haus und was in den Akku ging.

> **Warum keine Ampelfarben?** Ein voller Speicher ist nicht „gut" und ein leerer nicht „schlecht" — die Aussage entsteht erst aus beidem zusammen. Eine grüne Färbung für „immer voll" würde ausgerechnet den Zustand belohnen, in dem Überschuss verschenkt wird.

> **Mehrere Speicher:** Den Ladestand erfasst eedc für die Anlage als Ganzes. Die Auswertung gilt dann für alle Speicher zusammen, nicht je Gerät — die Sicht weist darauf hin.

#### Größerer Speicher? — der Sizing-Regler

Der Block daneben beantwortet die Anschlussfrage: **wie viel** mehr, und lohnt es sich? Du ziehst einen Regler zwischen **50 % und 200 %** deiner heutigen Kapazität; eedc lässt daraufhin deine echten Stundenwerte noch einmal durchlaufen — dieselbe Sonne, derselbe Verbrauch, nur ein anders großer Speicher.

Angezeigt werden:

- **Netto-Nutzen pro Jahr** — gesparter Netzbezug **minus** der Einspeisung, die dafür entfällt. Ein größerer Speicher senkt beides; nur den Bezug zu rechnen wäre eine Überschätzung (an der Referenzanlage 67 € statt 49 €).
- **Netzbezug** — wie viel weniger (oder mehr) aus dem Netz gekommen wäre.
- **Amortisation** — wie lange die Mehrkosten brauchen, bis sie wieder hereinkommen (Richtwert rund 500 € je kWh; steht als Annahme dabei).
- **Kurve über alle Größen** — flacht sie nach rechts ab, ist dein Speicher bereits groß genug. Die Null-Linie ist deine heutige Kapazität.

**Womit gerechnet wird.** Nicht mit der Kapazität vom Typenschild, sondern mit der, die dein Speicher im Alltag **wirklich bewegt** — eedc leitet sie aus dem Verlauf deines Ladestands ab. ⚠ Das ist **kein Gerätemangel**: Reserven, Ladestrategie, Leistungsgrenzen und Standby gehören dazu. Mit der Zahl vom Typenschild fällt die Rechnung systematisch zu optimistisch aus (an einer echten Anlage: −17,5 % Abweichung beim Netzbezug statt −5,4 %). Lässt sich die Basis nicht ableiten, rechnet eedc mit den gepflegten Parametern **und sagt es**.

**Und der Block sagt, woran ein Unterschied liegt.** Unter *Wie groß ist Ihr Speicher wirklich?* stehen die gepflegte nutzbare Kapazität und die gemessene nebeneinander, dazu der Ladestands-Bereich, in dem dein Speicher lebt, und an wie vielen Tagen er voll bzw. leer wurde. Daraus folgt die Unterscheidung:

- **Voll geladen, trotzdem weniger Durchsatz** ⇒ **Ladeverluste**. Gegen Ende der Ladung nimmt ein Speicher viel Energie auf, die den Ladestand kaum noch bewegt. Deine gepflegte Zahl ist richtig, die kleinere beschreibt den Durchsatz.
- **Nie voll geladen** ⇒ deine **Ladestrategie**. Dann ist die kleinere Zahl kein Verlust; falls das nicht gewollt ist, prüfe die gepflegte nutzbare Kapazität in den Einstellungen der Komponente.

> **Deine gepflegte Zahl wird nie überschrieben.** Sie trägt eine Absicht — wer bewusst nur bis 80 % lädt, hat das so gewollt. eedc erklärt den Unterschied, statt ihn zu „korrigieren".

> **Was die Simulation nicht kann:** Sie kennt nur das Wetter, das war, und dein Verbrauchsverhalten — und das ist bereits auf deinen jetzigen Speicher eingespielt (Lastverschiebung). Sie ist damit belastbarer als ein generisches Sizing-Tool, weil sie deine Saisonalität trägt, aber sie ist **keine Vorhersage**. Dieser Hinweis steht immer neben der Zahl. Unter etwa **180 Tagen** Historie sagt eedc zusätzlich, dass die Aussage noch nicht trägt — ein halbes Jahr deckt Sommer und Winter ab, und genau dazwischen liegt der Nutzen eines Speichers.

### 3.4 Wärmepumpe

Kennzahl-Reihenfolge (durchgängig gleich über Cockpit, diesen Reiter und die Auswertungen):

1. **JAZ** (Jahresarbeitszahl) — Wärme ÷ Strom über den Zeitraum (orange)
2. **Wärme** (kWh) — erzeugte Heizwärme + Warmwasser (rot)
3. **Strom** (kWh) — verbrauchter Strom der Wärmepumpe (gelb)
4. **Ersparnis** (€) — gegenüber der Alternative (Gas/Öl) (grün)

Zusätzlich: JAZ-Heizen / JAZ-Warmwasser getrennt, Saison-/Monatsvergleich, Detailtabellen mit JAZ pro Monat sowie — optional pro Wärmepumpe — die **Kompressor-Starts** (über einen kumulativen Zähler-Sensor).

> **JAZ vs. COP:** Für Perioden-Kennzahlen nutzt eedc durchgängig **JAZ** (ggf. periodenanteilig). **COP** bleibt technischen Backend-Berechnungen vorbehalten.

> **Anschaffungsdatum-Filter:** Aggregate (JAZ, Wärme, Strom, Ersparnis) ignorieren Monatsdaten **vor** dem Anschaffungsdatum. Wechselst du z. B. von der WP-eigenen Strommessung auf einen Shelly-Zähler, bleiben alte Werte historisch erhalten, verfälschen aber die aktuelle JAZ nicht.

### 3.5 E-Auto

- **Gefahrene Kilometer** im Zeitraum
- **Verbrauch** (kWh)
- **Ladequellen-Aufteilung** — PV-Ladung (kostenlos), Netz-Ladung (zu Hause), externe Ladung (unterwegs)
- **Kostenersparnis** gegenüber Benziner/Diesel — auf Basis echter **monatlicher Benzinpreise** aus dem EU Weekly Oil Bulletin (Fallback: statischer Parameter)
- **V2H-Entladung** (wenn aktiviert)

> **Wo wird die Heimladung erfasst — Wallbox oder E-Auto?** Hast du eine **Wallbox** als Komponente angelegt, ist sie die alleinige Quelle der zu Hause geladenen Energie (gesamt / aus PV / aus Netz); das E-Auto trägt dann nur fahrzeugspezifische Werte (km, Verbrauch, externe Ladung, V2H). **Ohne Wallbox** (z. B. Schuko-Lader) bleibt das E-Auto selbst die Quelle der Heimladung — dann erfasst du „Heim: PV" / „Heim: Netz" direkt am E-Auto. Mehr in [Berechnungen §3.4](BERECHNUNGEN.md#34-e-auto-einsparung).

### 3.6 Wallbox

- **Geladene Energie** (kWh)
- **Ladevorgänge** (Anzahl)
- **Durchschnittliche Lademenge**
- **PV-Anteil** der Ladungen

### 3.7 Balkonkraftwerk

- **Erzeugung** (kWh)
- **Eigenverbrauch** (kWh)
- **Einspeisung** (kWh, = Erzeugung − Eigenverbrauch, in der Regel unvergütet)
- optional: gekoppelte Speicher-Nutzung (Ladung/Entladung)

### 3.8 Sonstiges

Für sonstige **Erzeuger** (z. B. BHKW) und sonstige **Verbraucher** mit komponentenspezifischen Kennzahlen. Ein sonstiger Erzeuger hinter dem Hauszähler zählt in die Eigenverbrauchs-/Autarkie-Bilanz; CO₂ und Wirtschaftlichkeit eines Brennstoff-Erzeugers werden bewusst als „nicht bewertet" ausgewiesen, solange kein belastbares Brennstoffmodell vorliegt.

---

## 4. Auswertungen — die Wie-Achse

Die **Auswertungen** bündeln die auswertenden Gesamtsichten quer über die Zeit. Über Sub-Reiter erreichst du:

**Finanzen · ROI · Prognose · CO₂ · Tabelle**

Beim Öffnen landest du auf **Finanzen**.

### 4.1 Finanzen

Die Finanz-Sicht ist der Ort für **Erlöse, Einsparungen, Kosten und die Amortisation** — hierher ist auch der monatliche **Finanz-Abschluss** (T-Konto) aus dem alten Monatsbericht gezogen, jetzt zeitraum-fähig, sowie die frühere Finanz-Prognose.

- **Einspeiseerlös** = **vergütete** Einspeisung × Einspeisevergütung. Bei Anlagen mit aktivem §51-Schalter sind die in Negativpreis-Stunden eingespeisten kWh **abgezogen** — auch im Kennwert und in der Werte-Tabelle, nicht nur im T-Konto darunter (bis v4.0.0 stand derselbe Erlös mit zwei Zahlen auf einer Seite).
- **Eingesparte Stromkosten** = Eigenverbrauch × Bezugspreis. **Aus PV und Balkonkraftwerk** — ein Erzeuger unter „Sonstiges" mit Brennstoff (Mini-BHKW) zählt hier bewusst **nicht** mit: er erscheint voll in der Energiebilanz (Eigenverbrauch, Autarkie, EV-Quote), seine Wirtschaftlichkeit gilt aber als „nicht bewertet", weil der Brennstoff Geld kostet. Die Mengen-Spalte „Eigenverbrauch" ist deshalb bei einem solchen Erzeuger größer als die Menge hinter dieser Ersparnis.
- **USt auf Eigenverbrauch** — nur bei **Regelbesteuerung** (Stammdaten). Sie ist im „Netto-Ertrag (PV)" bereits **abgezogen** und in der Werte-Tabelle über den Spalten-Wähler als eigene Spalte einblendbar. Als Jahresgröße (Selbstkosten je kWh aus Investitionssumme und Jahresertrag) hat sie **kein Tages-Pendant** — die Summe der Tageszeilen ergibt beim Netto-Ertrag dann nicht exakt den Monatswert.
- **Sonstige Positionen** — frei erfassbare Kosten und Erlöse je Monat (Reparaturen, Wartung, sonstige Erträge); sie fließen als eigene T-Konto-Zeilen in die Summen ein
- **Grund- und Zählergebühren** — separat ausgewiesen
- **Netto-Einsparung** = Erlöse + Einsparungen − Kosten

> **Zwei Netto-Begriffe, wortgleich in KPI, Charts, Ø-Karte, CSV und Werte-Tabelle:**
> **„Netto-Ertrag (PV)"** = Einspeiseerlös + Eigenverbrauchs-Ersparnis + Sonstige − Sonderkosten,
> **ohne** Netzbezug-Kosten und **ohne** Wärmepumpe/E-Mobilität. **„Gewinn/Verlust (Haushalt)"** ist
> die Ergebniszeile des T-Kontos und rechnet beides mit. Beide stehen bewusst nebeneinander und im
> [Glossar](GLOSSAR.md#strompreise--tarife); jede Zeile trägt ihre Herleitung im Tooltip.
- **T-Konto** — Erlöse und Einsparungen den Kosten gegenübergestellt, mit Vorjahresvergleich (Δ). Auf Mobilgeräten als 2-Spalten-Layout (Label | Wert + Vorjahr + Δ).
- **Amortisations-Fortschritt** — wie viel % der Investition bereits zurückgeflossen sind (kumuliert, nicht Jahres-Rendite)

**Mehrkosten-Ansatz für Investitionen:**

- **PV-System:** volle Kosten (keine Alternative)
- **Wärmepumpe:** Kosten minus Gasheizung (konfigurierbar); optional plus jährliche Zusatzkosten der Alt-Heizung (Schornsteinfeger, Wartung, Gaszähler-Grundpreis) und ein monatlich gepflegter Gaspreis (verhindert, dass ein Tarifwechsel rückwirkend die ganze Historie ändert)
- **E-Auto:** Kosten minus Verbrenner (konfigurierbar)

> **Zwei Amortisations-Sichten:** Hier siehst du den **kumulierten Fortschritt** (Σ Erträge / Investition). Im Cockpit und unter ROI dagegen die **Jahres-Rendite** (Jahres-Ertrag / Investition). Beide sind korrekt, aber für verschiedene Zwecke — der „Sicht"-Tooltip an jeder Anzeige erklärt die Bezugsbasis.

### 4.2 ROI

Zwei klar getrennte Sichten statt vieler paralleler ROI-Zahlen ohne Bezug:

**Amortisationskurve** — X-Achse Zeit, Y-Achse kumulierte Einsparung vs. Investition, mit **Break-Even-Punkt**.

> **Mit Kalenderjahr** (Forum-Wunsch Radiocarbonat): Neben der Dauer steht das voraussichtliche
> Break-Even-**Jahr** — in der Kachel „Amortisation", unter der Kurve und als X-Achsen-Beschriftung
> (Kalenderjahre statt Jahres-Index). Anker ist das **früheste Anschaffungsjahr** deiner Komponenten;
> ohne gepflegtes Anschaffungsdatum bleibt es beim Jahres-Index. Verteilen sich die Anschaffungen über
> mehrere Jahre, ist das genannte Jahr **optimistisch** — der Text sagt das dazu.

**Zwei Amortisations-Kacheln, die sich ergänzen** (neu, nach dem V4-Flip zurückgeholt):

| Kachel | Was sie sagt | Woher die Zahl kommt |
|---|---|---|
| **Amortisation** | „in 9,2 Jahren" | **Modell** — deine relevanten Kosten geteilt durch eine hochgerechnete Jahres-Einsparung |
| **Amortisations-Fortschritt** | „40,0 % · noch 7.200 € · voraussichtlich 2030" | **Messung** — die Erträge, die deine Anlage seit Inbetriebnahme tatsächlich erwirtschaftet hat |

Beide rechnen gegen **dieselbe** Investitionssumme, deshalb lassen sich die Zahlen ineinander
überführen. Welche der beiden du gerade liest, steht im ⓘ-Tooltip der Kachel.

> **Unter welcher Annahme die Dauer gilt.** Der Fortschritt unterstellt nichts — er zählt, was
> geflossen ist. Eine **Dauer** dagegen muss etwas über die Zukunft unterstellen, und eedc
> unterstellt: **es geht nie wieder etwas kaputt**. Das steht jetzt neben jeder Dauer:
> „ohne künftige Instandhaltung" — an der Kachel, unter der Break-Even-Kurve, je Zeile in der
> Tabelle, im Komponenten-Hub der Wallbox, im PDF-Finanzbericht und im Rechenweg des HA-Sensors
> `amortisation_jahre`.
>
> **Willst du mit Instandhaltung rechnen**, trag sie bei der Komponente als **Kosten/Jahr** ein.
> Dann steht dort „inkl. 200,00 €/Jahr Betriebskosten, ohne weitere Instandhaltung" — der Betrag
> ist in der Zahl bereits abgezogen. Aus deiner bisherigen Reparatur-Historie rechnet eedc
> **keine** Reparatur-Rate hoch: bei ein bis zwei Ereignissen wäre das eine Zahl, die sich jedes
> Jahr ändert, ohne dass etwas passiert ist.

> **Was als „relevante Kosten" zählt.** Nicht der volle Kaufpreis, sondern die **Mehrkosten**
> gegenüber der Alternative: Was hätte eine Gasheizung statt der Wärmepumpe gekostet, was ein
> Verbrenner statt des E-Autos? Diesen Betrag pflegst du je Komponente im Feld
> **„Anschaffungskosten Alternative"** — dasselbe Feld, das der Daten-Checker anmahnt.
> **Pflegst du es nicht, zählen die vollen Anschaffungskosten**; eedc setzt keine Annahme mehr an
> deiner Stelle ein. Früher rechnete diese Sicht mit pauschalen 8.000 € für die Heizung und
> 35.000 € fürs Auto — auch dann, wenn du etwas anderes eingetragen hattest. Wer die Alternative
> pflegt, sieht seine Amortisation seitdem realistischer, und für PV, Speicher und Wechselrichter
> ändert sich nichts (dort gibt es keine Alternative).

> **Reparaturen zählen als eingesetztes Geld, nicht als Dauer-Abzug.**
> Buchst du unter *Sonstige Positionen* eine **Ausgabe** — Reparatur, Ersatzteil, Wartung —,
> erhöht sie ab sofort deinen **Kapitaleinsatz**, statt jedes Jahr von der Ersparnis abgezogen zu
> werden. Vorher verlängerte eine einmalige Reparatur von 3.000 € an einer Wärmepumpe die
> Amortisation von 8,1 auf **42,6 Jahre**, und die Zahl wurde jedes Jahr schlechter, ohne dass
> etwas passiert war. Jetzt sind es **10,5 Jahre**: das Geld ist einmal ausgegeben, nicht jedes
> Jahr neu. Der Tooltip schreibt den Zwischenschritt aus („90.900 € + 1.015 € sonstige Ausgaben
> − 455 € sonstige Erträge = 91.460 €").
>
> **Sonstige Erträge senken dein eingesetztes Geld.**
> Buchst du unter *Sonstige Positionen* einen **Ertrag** — THG-Quote, eine Förderung, ein
> einmaliger Erlös —, mindert er deinen **Kapitaleinsatz**: Geld, das du nie ausgeben musstest,
> muss auch nicht wieder hereinkommen. Deine Amortisation wird dadurch **kürzer**, und der
> Tooltip nennt den Abzug beim Namen. In der **Monatsbilanz** bleibt der Betrag unverändert
> stehen — dort ist er ein Ertrag des Monats, in dem er geflossen ist.
>
> **Erwartest du den Betrag jedes Jahr wieder** — etwa den Einspeise-Erlös eines zweiten
> Erzeugers mit eigenem Tarif —, dann gehört er **nicht** in den Monatsabschluss, sondern an die
> Komponente:
>
> - **„Ertrag/Jahr (€)"** (Bearbeiten → *Weitere Angaben & Kosten*, bei *Wallbox* und
>   *Sonstiges*) — das Gegenstück zu den Betriebskosten pro Jahr;
> - noch besser bei einem zweiten Erzeuger: **„Einspeise-Erlös (€)"** bei *Sonstiges* mit
>   Kategorie *Erzeuger*. Das Feld lässt sich einer Datenquelle zuordnen, also einem Sensor aus
>   Home Assistant — dann kommt der Betrag monatsgenau statt geschätzt.
>
> Nur diese beiden Felder wirken in Prognose und Amortisationsdauer. **Buch dann nicht beides** —
> sonst zählt derselbe Erlös zweimal; der Daten-Checker weist dich darauf hin, wenn derselbe
> Posten Monat für Monat auftaucht.

**ROI pro Komponente — zwei Sichten:**

| Sicht | Bezugsbasis | Wann nutzen? |
|-------|-------------|--------------|
| **Jahres-ROI** | Jahres-Ertrag / Investition | Vergleich mit Geldanlagen |
| **Kumulierte Amortisation** | Σ Erträge / Investition | Fortschritt zur Refinanzierung |

Jeder Wert trägt einen **„Sicht"-Tooltip** (pro Investition vs. gesamt, Mehrkosten- vs. Vollkosten-Ansatz, IST vs. Prognose).

Tabelle je Komponente: **Investition** (Kaufpreis + Installation, bei WP/E-Auto der Mehrkosten-Ansatz) · **Jährliche Einsparung** · **ROI** (Jahres-%) · **Amortisation** (Jahre bis Break-Even).

**Realisierungsquote** — historische Erträge vs. konfigurierte Prognose: ≥ 90 % (grün), ≥ 70 % (gelb), < 70 % (rot).

**PV-System-Aggregation** — Wechselrichter + Module + DC-Speicher werden als ein „PV-System" gerechnet; Einzelkomponenten in aufklappbaren Unterzeilen, Einsparungen proportional nach kWp verteilt.

### 4.3 Prognose (Genauigkeit gegen IST)

Die Vergleichs- und Bewertungsfläche für mehrere PV-Prognosequellen — vier Quellen nebeneinander:

| Quelle | Bedeutung |
|--------|-----------|
| **OpenMeteo (OM)** | wetterbasierte Standardprognose |
| **eedc (kalibriert)** | OM × aktueller Lernfaktor — anlagenspezifisch korrigiert |
| **Solcast** | optionale dritte Quelle (Solcast-API-Key oder HA-Integration „BJReplay") |
| **IST** | tatsächlich gemessener Ertrag (sobald verfügbar) |

- **Kennzahl-Matrix Heute / Morgen / Übermorgen** mit VM/NM-Split am astronomischen Solar Noon (proportional)
- **Stundenprofil-Diagramm** (IST grün, eedc orange, Solcast blau, OpenMeteo gelb)
- **24-Stunden- und 7-Tage-Vergleich** tabellarisch, mit Wettersymbolen und farbkodierten Δ-Spalten (grün < 15 %, gelb 15–30 %, rot > 30 %)
- **Genauigkeits-Tracking:** **MAE** (Streuung) und **MBE** (systematischer Bias, neutral gefärbt — Vorzeichen ist Information, keine Wertung). Ein **diagnostischer Modus** trennt Über- und Unterschätzung, sodass Asymmetrien sichtbar werden.
- **Lernfaktor-Status:** Ist der eedc-Lernfaktor noch nicht aktiv, zeigt ein Banner, wie viele der nötigen Tage gesammelt sind. Sobald genug Daten vorliegen, wechselt der Lernfaktor in eine **saisonale Kaskade** (Monatsfaktor ≥ 15 Tage → Quartalsfaktor ≥ 15 Tage → 30-Tage-Fenster).
- **Reparatur bei IST-Lücke:** Bei unvollständigen IST-Werten erscheint ein ⚠-Symbol; ein Klick listet die fehlenden Stunden und bietet „Tag neu berechnen" (holt fehlende Snapshots nach).

### 4.4 CO₂

- **Vermiedene Emissionen** (kg CO₂) — als Kennwert, als Monats-Diagramm und in anschaulichen **Äquivalenten** (Bäume, Auto-Kilometer, Kurzstreckenflüge)
- **CO₂-Amortisation:** die kumulierte Einsparung gegen die **graue Herstellungs-Last** deiner Komponenten — inklusive des Punktes, ab dem sich beides ausgleicht
- **Berechnungsgrundlage:** Methodik und Ø-Werte, standardmäßig eingeklappt

**Was genau als „gespart" zählt.** Gespart ist, was du **selbst verbraucht** hast: jede eigene Kilowattstunde, die Netzstrom ersetzt, vermeidet den deutschen Strommix (380 g CO₂/kWh). **Eingespeister Strom zählt hier nicht mit** — er verdrängt Netzstrom beim Abnehmer, nicht bei dir. Dazu kommen die beiden anderen Quellen: die **Wärmepumpe** (vermiedene fossile Wärme abzüglich ihres Stroms) und die **E-Mobilität** (vermiedener Kraftstoff abzüglich der Netzladung).

> **Eine Zahl, überall dieselbe.** Diese Seite, der Block „CO₂-Bilanz" in [Cockpit → Jahr/Gesamt](#24-jahrgesamt) und der CO₂-Sensor in Home Assistant nennen seit Juli 2026 denselben Wert. Vorher rechnete diese Seite auf der **Erzeugung** statt auf dem Eigenverbrauch und ließ Wärmepumpe und E-Mobilität weg — sie lag dadurch zu hoch. Wenn deine CO₂-Zahl hier einmalig kleiner geworden ist, ist das die Korrektur; deine Anlage hat sich nicht verschlechtert.

> **Der Jahr-Filter wirkt nicht überall gleich.** Das Monats-Diagramm und der Kennwert „CO₂ eingespart" folgen dem gewählten Jahr. Die **Amortisation** rechnet immer über die **gesamte Historie** — die graue Herstellungs-Last ist einmalig angefallen, ein Vergleich mit nur einem Jahr wäre irreführend. Der Block sagt das sichtbar dazu, sobald ein Einzeljahr gewählt ist.

### 4.5 Tabelle (Werte-Werkbank)

Der interaktive Überblick über alle Monatswerte in einer sortierbaren Tabelle — ideal für eigene Analysen und Jahresvergleiche.

- **Alle Energiefelder** in Spalten (Erzeugung, Einspeisung, Bezug, Direktverbrauch, Speicher, Wärmepumpe, E-Auto, Wallbox, Finanzen, CO₂ …)
- **Vorjahresvergleich** je Metrik: eine zweistufige Kopfzeile — der Metrik-Name überspannt eine Dreiergruppe, darunter die Sub-Labels **aktueller Zeitraum · Vergleichszeitraum · Δ** (z. B. „2026 · 2025 · Δ"); der Δ-Wert ist farbkodiert
- **Zeitraum-Spalte mit Wochentag/Datum-Split:** in der Tagesansicht steht links das **Wochentagskürzel** (Mo, Di …), rechts das Datum; in der Monatsansicht links der Monatsname, rechts das Jahr
- **Deutsches Zahlenformat** (Komma als Dezimaltrennzeichen)
- **Sortierung** per Klick auf den Spalten-Kopf (erneuter Klick kehrt die Richtung um)
- **Spaltenauswahl** über „Spalten" (Auswahl bleibt im Browser gespeichert)
- **CSV-Export** des sichtbaren Inhalts (alle Zeilen, eingeblendete Spalten)

> **Womit sich eine Zeile vergleicht.** Jede Monatszeile steht ihrem **eigenen** Vorjahresmonat gegenüber — Dezember 2025 dem Dezember 2024, auch wenn der Zeitraum „Alle Jahre" umfasst. Gibt es diesen Vorjahresmonat nicht (weil deine Aufzeichnung später beginnt), bleibt die Vergleichsspalte **leer („—")**; es wird kein Ersatzwert eingesetzt und kein Δ von 0,0 % angezeigt. Dasselbe gilt für Tageszeilen.
>
> Die **Summenzeile** hält sich an dieselbe Regel: Sie vergleicht nur, wenn **jede** angezeigte Zeile ein Gegenstück hat. Bei „Alle Jahre" ist das nicht der Fall — die ersten Monate deiner Aufzeichnung haben kein Vorjahr —, dort bleibt die Vergleichs-Spalte des Fußes leer, während die Δ-Werte der einzelnen Zeilen vollständig darüber stehen. Andernfalls stünde dort z. B. die Summe aus 37 Monaten neben der aus 25: eine Prozentzahl, die sich wie eine Aussage über deine Anlage liest und keine ist. Die „aktuell"-Zelle bleibt immer die Summe der Spalte darüber. **Warum sie schweigt, steht unter der Tabelle** — mit der Anzahl der Monate bzw. Tage, die kein Gegenstück haben; derselbe Satz erscheint als Hinweis, wenn du auf die leere Zelle zeigst.
>
> *Bis Version 4.0.5 wurden über mehrjährige Zeiträume alle Jahrgänge desselben Monats verwechselt: jede Zeile verglich sich mit dem jüngsten davon, im Extremfall mit sich selbst (identische Zahlen, Δ 0,0 %). Wenn deine Vorjahresspalte vorher gespiegelte Werte zeigte, ist das die Korrektur.*

> **Erträge je PV-String und je Balkonkraftwerk (Tagesansicht).** Im Block **Energieprofile** führt
> der Spalten-Picker die Gruppe **„Je Erzeuger"**: je Gerät eine Spalte mit seinem Tagesertrag —
> mit Summenzeile, Vergleich und CSV wie jede andere Spalte. Sie erscheint ab **zwei** Erzeugern und
> nur für Geräte mit **eigenem Ertragssensor**; fehlt der Sensor, steht über der Tabelle, welches
> Gerät betroffen ist und wo du ihn zuordnest ([Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md)).
> Eine nach Nennleistung gerechnete Tageszahl gibt es bewusst nicht — sie wäre von einer Messung
> nicht zu unterscheiden. Der Stunden-Blick auf denselben Tag liegt in [Cockpit → Tag](#22-tag).

> Kompakte Werte-Blöcke sind zusätzlich direkt in Cockpit- und Komponenten-Sichten eingebettet; die volle Werkbank mit Picker und Export liegt hier.

> **Die Spalte „CO₂-Einsparung (PV)"** zeigt bewusst nur den **PV-Anteil** (Eigenverbrauch × Strommix) — für Monate **und** Tage, damit sich Tageszeilen zum Monat aufaddieren. Wärmepumpe und E-Mobilität fehlen darin: ihre Bezugsgrößen (erzeugte Wärme, gefahrene Kilometer) erfasst eedc nur monatlich. Die **vollständige** Bilanz steht unter **Auswertungen → CO₂** (§4.4) und im Block „CO₂-Bilanz" in [Cockpit → Jahr/Gesamt](#24-jahrgesamt).

---

## 5. Community

Der Community-Vergleich ermöglicht **anonyme Benchmarks** mit anderen PV-Anlagen-Besitzern. Er ist ein eigener Hauptbereich mit Sub-Reitern.

### 5.1 Daten teilen (Voraussetzung)

Bevor der Vergleich Werte zeigt, teilst du deine Anlagendaten anonym. Den Schalter dafür findest du unter **Einstellungen → Stammdaten → Community-Share**:

- **Vorschau:** zeigt, welche Daten geteilt werden
- **Anonymisierung:** nur Bundesland, keine Adresse/PLZ
- **Jederzeit löschbar** — auch rückwirkend

Solange nichts geteilt ist, führt der Community-Bereich dich mit „Jetzt teilen" direkt zu diesem Schalter. Der Teilen-Status ist zusätzlich in der Status-Fußzeile sichtbar.

### 5.2 Die Community-Reiter

Oben wählst du einen **Zeitraum** (letzter Monat, letzte 12 Monate, letztes vollständiges Jahr, seit Installation) sowie — bei mehreren Anlagen — die Anlage. Ein Symbol öffnet den Community-Server (energy.raunet.eu) im Browser.

Der Community-Bereich hat **sechs Reiter**: **Übersicht · PV-Ertrag · Komponenten · Regional · Trends · Statistiken**.

**Übersicht** — Radar-Chart (eigene Performance vs. Community auf mehreren Achsen), **Ranking** (Platz X von Y, gesamt und regional) und **Achievements** (Autarkiemeister, Effizienzwunder, Solarprofi, Speicherheld, Klimaschützer, Frühstarter, Vorreiter).

**PV-Ertrag** — dein spezifischer Ertrag (kWh/kWp) vs. Community-Durchschnitt, monatlicher Vergleich und ein Histogramm deiner Einordnung in der Verteilung.

**Komponenten** — Benchmarks je Komponente:

| Komponente | Kennzahlen |
|------------|------------|
| **Speicher** | Zyklen, Effizienz, Autarkie-Beitrag |
| **Wärmepumpe** | JAZ vs. Community (typ-spezifisch), PV-Anteil |
| **E-Auto** | km/Monat, Ø kWh/100 km, PV-Anteil |
| **Wallbox** | Ladung kWh/Monat, PV-Anteil % |
| **Balkonkraftwerk** | Ertrag kWh/Monat, Anzahl × Wp pro Modul |

**Regional** — interaktive Deutschlandkarte (Farbkodierung nach spezifischem Ertrag; Hover zeigt Bundesland-Details), Bundesland-Tabelle und regionale Einordnung.

**Trends** — Ertragsverlauf der Community über die Zeit, saisonale Performance, Jahresvergleich.

**Statistiken** — Ausstattungsquoten (wie viele Anlagen haben Speicher, WP, E-Auto …), Top-Listen und eine Community-Gesamtübersicht.

### 5.3 Datenschutz

- Nur aggregierte Statistiken werden angezeigt; kein Rückschluss auf einzelne Anlagen.
- Daten sind jederzeit — auch rückwirkend — wieder löschbar.
- Server: https://energy.raunet.eu (Open Source).

---

## 6. Daten erfassen im Alltag

Diese Bedienungs-Seite beschreibt das **Ansehen und Auswerten**. Das **Erfassen und Einrichten** liegt gesammelt unter **Einstellungen** (Teil III). Die wichtigsten Wege im Alltag:

- **Monatsabschluss / Monatswerte:** ein einziges Formular unter **Einstellungen → Daten → Monatsdaten**. Zählerstände, Kennzahlen und die „sonstigen Positionen" erfasst du hier; ein offener Monatsabschluss taucht in der Status-Fußzeile auf. (In früheren Versionen war das ein mehrstufiger Assistent — jetzt ein durchgängiges Formular.)
- **Datenquellen zuordnen:** welches Feld aus welchem Sensor/Topic gespeist wird, pflegst du unter **Einstellungen → Datenquellen** (eine Fläche für HA-Sensoren, MQTT und Connectoren; ersetzt die früheren getrennten Sensor-Mapping- und MQTT-Inbound-Assistenten).
- **Import & Nachpflege:** CSV, Cloud/Portal, Geräte-Connector, HA-Statistik-Import sowie die Energieprofil-Pflege (Vollbackfill, Neu-Aggregation, Löschen) liegen ebenfalls in den Einstellungen.

Details zu allen diesen Wegen: [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md).

---

## 7. Hilfe in der App

Der Menüpunkt **Hilfe** rendert dieses Benutzerhandbuch direkt in der App. Damit funktioniert die Dokumentation in der HA-Companion-App genauso wie im Browser — ohne Tab-Wechsel und ohne Ingress-Login-Probleme.

- **Auswahl** des Dokuments (Einstieg / Handbuch / Referenz) über eine Seitenleiste (Desktop) bzw. ein Auswahlmenü (Mobile).
- **Direktlinks** per URL-Parameter `?doc=<slug>` sind teilbar (z. B. `?doc=bedienung`).
- **Querverweise** zwischen den Hilfe-Dokumenten werden intern aufgelöst; externe `.md`-Verweise gehen zur GitHub-Quelle.

> Die In-App-Hilfe ist die offizielle Single-Source-of-Truth-Sicht der Doku — dieselben Inhalte stehen als Website unter https://supernova1963.github.io/eedc-homeassistant/.

---

## 8. Anhang: Wo ist X hin?

Die neue Oberfläche ordnet Vertrautes neu. Diese Tabelle zeigt, wo frühere Bereiche jetzt zu finden sind (vollständige Fassung siehe auch „Was ist neu"):

| Früher | Jetzt |
|--------|-------|
| **Live Dashboard** (eigener Tab) | **Cockpit → Live** (weiterhin die Startseite) |
| **Cockpit → Übersicht** | **Cockpit → Jahr/Gesamt** |
| **Cockpit → Monatsberichte** | **Cockpit → Monat**; Finanz-T-Konto → **Auswertungen → Finanzen** |
| **Komponenten-Dashboards** (im Cockpit) | eigene **Komponenten**-Achse (ein Reiter je Typ) |
| **Auswertungen → Energie** | Jahres-Anteile → **Cockpit → Jahr/Gesamt**; Aggregat-Tabelle → **Auswertungen → Tabelle** |
| **Auswertungen → Investitionen** | **Auswertungen → ROI** |
| **Auswertungen → Energieprofil (Beta)** | Tagessicht → **Cockpit → Tag**; Monats-Analysen (Kategorien, Top-Stunden, typisches Tagesprofil, §51, PR Ø) → **Cockpit → Monat**; Tages-Prognose → **Cockpit → Aussicht**; Roh-Tabelle → **Auswertungen → Tabelle**; Pflege → **Einstellungen → Daten**. *Wochentag-Wochenvergleich entfällt; Tag×Stunde-Heatmap kommt später neu gestaltet zurück.* |
| **Aussichten** (eigener Tab, 5 Sub-Tabs) | **Cockpit → Aussicht** (eine Seite, Horizont-Selektor); Prognose-Genauigkeit → **Auswertungen → Prognose** |
| **Monatsabschluss-Assistent** | **Einstellungen → Daten → Monatsdaten** (ein Formular) |
| **Infothek** (eigener Tab) | **Einstellungen → Infothek** |
| **Sensor-Zuordnung / MQTT-Inbound** (Assistenten) | **Einstellungen → Datenquellen** (eine Fläche) |
| **Einstellungen-Dropdown** | **Einstellungen** als Kachel-Raster |
| **Social-Media-Textvorlage** (Teilen-Symbol ↗ im Cockpit-Kopf) | **entfällt ersatzlos.** Mit v4 war sie nicht mehr erreichbar, seit Juli 2026 ist sie auch im Programm zurückgebaut. Das **Teilen mit der Community** ist eine andere Funktion und bleibt (siehe [5. Community](#5-community)). |

---

*Letzte Aktualisierung: 2026-07-31 (v4.0)*
