
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

> **Hinweis zum Layout:** eedc ist als datendichte Analyse-App primär für den Desktop gedacht. Live, Cockpit-Monat und die Komponenten-Sichten funktionieren auch am Smartphone gut; für die datendichten Tabellen (Auswertungen → Tabelle, Cockpit → Aussicht) empfehlen wir Querformat oder Desktop. Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom) können einzelne Layouts eng werden — eine bewusste Designentscheidung statt Layout-Patches, die den datendichten Charakter aufweichen würden.

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

**Wetter-Widget** — aktuelle Außentemperatur, Wolkenbedeckung und Stunden-Prognose als kleine Kachel.

**Demo-Modus** — ohne zugeordnete Datenquellen zeigt Live simulierte Werte, damit du die Darstellung vorab testen kannst.

> **Woher kommen die Live-Daten?** Aus deinen zugeordneten **Datenquellen** — Home-Assistant-Sensoren, MQTT-Topics oder Geräte-Connectoren. Die Zuordnung pflegst du unter **Einstellungen → Datenquellen** (siehe [Teil III](HANDBUCH_EINSTELLUNGEN.md)).

### 2.2 Tag

Die **Tag**-Sicht bringt den feingranularen Stunden-Tag ins Cockpit: ein ausgewählter Kalendertag mit Stunden-Auflösung. Über die Datums-Navigation blätterst du zu beliebigen Tagen.

- **Stunden-Verlauf** von Erzeugung, Verbrauch und Speicher
- **Tagesbilanz** als Kennzahl-Strip (Summen des Tages)
- Detail-Sektionen je nach vorhandenen Komponenten

Die Datenbasis sind kumulative Zähler-Snapshots (stündlich); die Tages-Werte folgen der Backward-Slot-Konvention (Slot N = Energie aus dem Intervall [N−1, N), Industriestandard). Fehlen Snapshots (z. B. durch eine HA-Statistik-Latenz oder einen Add-on-Neustart), weist eedc darauf hin und bietet eine Nachberechnung an — die Pflege dazu liegt unter [Einstellungen → Daten → Energieprofil-Pflege](HANDBUCH_EINSTELLUNGEN.md).

### 2.3 Monat

Die **Monat**-Sicht ist das Referenz-Muster der Zeit-Achse: ein ausgewählter Monat mit Tages-Granularität. Über den Monats-Zeitstrahl navigierst du zu beliebigen Vormonaten.

- **Kennzahl-Strip** oben — die wichtigsten Monatswerte mit Δ zum Vormonat
- **Energiebilanz** — PV-Erzeugung, Direktverbrauch, Einspeisung, Netzbezug
- **Finanzen** — Komponenten-Finanz-Tabelle (Saldo je Komponente) mit Sprung in die volle Finanzrechnung (siehe unten)
- **Komponenten-Sektionen** — Status je vorhandener Komponente mit kWh-Werten
- **Datenquellen-Kennzeichnung** — pro Feld ist die Herkunft der Werte sichtbar (HA-Statistik, MQTT, Connector, gespeichert)
- **SOLL/IST** — gegen die Solarprognose
- **Community-Vergleich** — eingebettet, wo Daten geteilt sind

Aus dem feingranularen Stunden-Bestand des Monats zeigt die Sicht zusätzlich:

- **Performance Ratio (Ø Monat)** als Kennzahl
- **Erzeugung & Verbrauch nach Kategorie** — eine kompakte Anteils-Leiste über alle Erzeuger- und Verbraucher-Kategorien
- **Typisches Tagesprofil** — der stündliche Mittelwert von PV und Verbrauch über die Tage des Monats
- **Top-Stunden** — die stärksten Netzbezugs- und Einspeise-Stunden (Datum + Uhrzeit), nützlich zur Tarif-Optimierung
- **§51-EEG-Negativpreis** — Stunden mit negativem Börsenpreis, die dabei eingespeiste Energie und der Ø-Börsenpreis

> **Aus der alten „Energieprofil (Beta)"-Sicht bewusst nicht übernommen:** die Tag×Stunde-Heatmap (kommt später neu gestaltet zurück) und der Wochentag-Wochenvergleich (entfällt — der Ø-gleiche-Wochentag-Rückblick in der Tag-Sicht deckt den Kern).

**Finanzen-Block** — der Monat (und analog [Jahr/Gesamt](#24-jahrgesamt)) trägt einen eigenen Finanzen-Block als **Komponenten-Finanz-Tabelle**: eine Zeile je Komponente (PV-Anlage, Speicher, Wärmepumpe, E-Auto …) mit den Spalten **Erträge** (tatsächliche Zahlungsflüsse), **Einsparungen** (kalkulatorisch — vermiedene Kosten), **Aufwand** und **Saldo**. Die **Summenzeile ist die Block-Kopf-Kennzahl** (Kopf == sichtbare Summe). Spaltenköpfe und Zeilen zeigen ihre Herleitung im **Tooltip** (Hover/Tipp). Netzbezug-Kosten und Grundgebühr stehen **nachrichtlich** darunter, nicht im Saldo verrechnet. Eine zusätzliche Zeile **„Ergebnis nach Stromrechnung"** (= Saldo − Netzbezug-Kosten) zeigt als **zweite Perspektive** das Haushaltsergebnis; der Komponenten-Saldo bleibt davon unberührt und ist weiterhin die Kopf-Kennzahl. Die **volle Finanzrechnung** (T-Konto je Investition, zeitraum-fähig) und die Finanz-Prognose liegen in [Auswertungen → Finanzen](#41-finanzen); der Block verlinkt direkt dorthin.

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

**Effizienz-Quoten (Ring-Anzeigen):**

- **Autarkie** = (Gesamtverbrauch − Netzbezug) / Gesamtverbrauch × 100 %
- **Eigenverbrauchsquote** = Eigenverbrauch / PV-Erzeugung × 100 %

**Komponenten-Status** — Schnellstatus aller Komponenten mit Sprung in die jeweilige Komponenten-Sicht. Wärmepumpe-, Speicher-, E-Auto- und Wallbox-Kennzahlen verwenden durchgängig dieselben Icons, Farben und Reihenfolgen wie überall in eedc.

**Trend-Historie** — Jahresvergleich und saisonale Muster (beste/schlechteste Monate) über alle bisherigen Jahre. Die reine **Degradations-Prognose** (geschätzter Leistungsrückgang pro Jahr) liegt dagegen in der [Aussicht](#25-aussicht).

**CO₂-Bilanz** — vermiedene Emissionen (kg) im Vergleich zu reinem Netzbezug.

**Social-Media-Textvorlage** — über das Teilen-Symbol (↗) im Kopf erzeugst du einen kopierfertigen Text für Social-Media-Posts:

1. **Monat/Jahr wählen** (Standard: letzter verfügbarer Monat)
2. **Variante wählen** — *Kompakt* (Twitter/X, mit Hashtags) oder *Ausführlich* (Facebook-Gruppen/Foren, mit Emojis)
3. **Vorschau** wird sofort angezeigt
4. **Kopieren** in die Zwischenablage

Der Text enthält automatisch Anlagenleistung (kWp), Ausrichtung, Bundesland, Erzeugung, Autarkie, Eigenverbrauchsquote, den Prognose-Vergleich (wenn vorhanden), vorhandene Komponenten (Speicher, Wärmepumpe, E-Auto), CO₂-Einsparung und Netto-Ertrag.

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

> **Wo ist die „Aussicht" je Komponente?** Bewusst nicht im Hub. Zeitlich-vorausschauende Sichten laufen zentral über [Cockpit → Aussicht](#25-aussicht).

### 3.2 PV-Anlage

Der PV-Reiter fasst **Wechselrichter, zugeordnete Module und DC-Speicher** zu einem System zusammen.

- **Wechselrichter-Übersicht** mit zugeordneten Modulen (System-Struktur zeigt die Topologie WR → Module/Speicher, inkl. Hinweis auf Module/Speicher ohne Zuordnung)
- **String-Vergleich** nach Ausrichtung (Süd, Ost, West)
- **Spezifischer Ertrag** (kWh/kWp) — wichtig für Vergleiche
- **SOLL/IST** gegen die Solarprognose; konsistente Farben (SOLL blau, IST amber, positive Abweichung grün)
- **Performance Ratio** auf Basis der Global Tilted Irradiance (GTI) — bei steilen Modulen und tiefer Wintersonne realistischer als auf GHI-Basis (verhindert physikalisch unmögliche PR-Werte > 1)

Bei **Einzel-String-Anlagen** (genau eine PV-Modul-Investition) entfällt die redundante „Stringsumme"-Zeile.

**SOLL/IST verstehen:**

| Kennzahl | Bedeutung |
|----------|-----------|
| **SOLL** | erwarteter Ertrag aus Standort, Ausrichtung, Neigung |
| **IST** | tatsächlich gemessener Ertrag |
| **Abweichung** | positiv = besser als erwartet, negativ = schlechter |

Typische Abweichungen: ±5 % normal (Wetter), ±10–15 % prüfen (Verschattung? Verschmutzung?), > 20 % Handlungsbedarf (Defekt? Fehlkonfiguration?).

### 3.3 Speicher

- **Ladezyklen** (Vollzyklen) — ausschließlich aus dem stationären Speicher-SoC; E-Auto-SoC ist zuverlässig ausgeschlossen
- **Effizienz** = Entladung / Ladung × 100 % (durchgängig cyan)
- **Degradation** (Kapazitätsverlust über die Zeit)
- **Arbitrage-Analyse** (wenn aktiviert): Netzladung zu günstigem Strom, Entladung bei hohem Preis, Arbitrage-Gewinn

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

- **Einspeiseerlös** = Einspeisung × Einspeisevergütung
- **Eingesparte Stromkosten** = Eigenverbrauch × Bezugspreis
- **Sonstige Positionen** — frei erfassbare Kosten und Erlöse je Monat (Reparaturen, Wartung, sonstige Erträge); sie fließen als eigene T-Konto-Zeilen in die Summen ein
- **Grund- und Zählergebühren** — separat ausgewiesen
- **Netto-Einsparung** = Erlöse + Einsparungen − Kosten
- **T-Konto** — Erlöse und Einsparungen den Kosten gegenübergestellt, mit Vorjahresvergleich (Δ). Auf Mobilgeräten als 2-Spalten-Layout (Label | Wert + Vorjahr + Δ).
- **Amortisations-Fortschritt** — wie viel % der Investition bereits zurückgeflossen sind (kumuliert, nicht Jahres-Rendite)

**Mehrkosten-Ansatz für Investitionen:**

- **PV-System:** volle Kosten (keine Alternative)
- **Wärmepumpe:** Kosten minus Gasheizung (konfigurierbar); optional plus jährliche Zusatzkosten der Alt-Heizung (Schornsteinfeger, Wartung, Gaszähler-Grundpreis) und ein monatlich gepflegter Gaspreis (verhindert, dass ein Tarifwechsel rückwirkend die ganze Historie ändert)
- **E-Auto:** Kosten minus Verbrenner (konfigurierbar)

> **Zwei Amortisations-Sichten:** Hier siehst du den **kumulierten Fortschritt** (Σ Erträge / Investition). Im Cockpit und unter ROI dagegen die **Jahres-Rendite** (Jahres-Ertrag / Investition). Beide sind korrekt, aber für verschiedene Zwecke — der „Sicht"-Tooltip an jeder Anzeige erklärt die Bezugsbasis.

### 4.2 ROI

Zwei klar getrennte Sichten statt vieler paralleler ROI-Zahlen ohne Bezug:

**Amortisationskurve** — X-Achse Zeit (Jahre), Y-Achse kumulierte Einsparung vs. Investition, mit **Break-Even-Punkt**.

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

- **Vermiedene Emissionen** (kg CO₂)
- **Berechnung:** Eigenverbrauch × CO₂-Faktor des Strommix
- **Zeitreihe** der Einsparung
- **Äquivalente** (z. B. „entspricht X km Autofahren")

### 4.5 Tabelle (Werte-Werkbank)

Der interaktive Überblick über alle Monatswerte in einer sortierbaren Tabelle — ideal für eigene Analysen und Jahresvergleiche.

- **Alle Energiefelder** in Spalten (Erzeugung, Einspeisung, Bezug, Direktverbrauch, Speicher, Wärmepumpe, E-Auto, Wallbox, Finanzen, CO₂ …)
- **Vorjahresvergleich** je Metrik: eine zweistufige Kopfzeile — der Metrik-Name überspannt eine Dreiergruppe, darunter die Sub-Labels **aktueller Zeitraum · Vergleichszeitraum · Δ** (z. B. „2026 · 2025 · Δ"); der Δ-Wert ist farbkodiert
- **Zeitraum-Spalte mit Wochentag/Datum-Split:** in der Tagesansicht steht links das **Wochentagskürzel** (Mo, Di …), rechts das Datum; in der Monatsansicht links der Monatsname, rechts das Jahr
- **Deutsches Zahlenformat** (Komma als Dezimaltrennzeichen)
- **Sortierung** per Klick auf den Spalten-Kopf (erneuter Klick kehrt die Richtung um)
- **Spaltenauswahl** über „Spalten" (Auswahl bleibt im Browser gespeichert)
- **CSV-Export** des sichtbaren Inhalts (alle Zeilen, eingeblendete Spalten)

> Kompakte Werte-Blöcke sind zusätzlich direkt in Cockpit- und Komponenten-Sichten eingebettet; die volle Werkbank mit Picker und Export liegt hier.

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

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
