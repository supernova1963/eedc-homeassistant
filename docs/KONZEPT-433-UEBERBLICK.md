# Konzept #433 — Block «Überblick» im Komponenten-Hub und Datenquellen nach Betriebsart

> **Stand:** 24.10.2026, gebaut für Wärme/Klima (P-433-2). Anlass: GitHub [#433](https://github.com/supernova1963/eedc-homeassistant/issues/433)
> (Live-Energiefluss: Verbraucher-Gruppe, Modus-Chip, Geräte-Details) und [#431](https://github.com/supernova1963/eedc-homeassistant/issues/431)
> (Datenquellen je Betriebsart). Diese Datei hält fest, **was gilt** — den Rahmen, die gebaute Form der Stufe 2 und die Entscheide.
> Die Stufen 1, 1b und 3 sind beschrieben, aber nicht gebaut; sie stehen hier nur, soweit sie die Bauform von Stufe 2 binden.
> Handbuch: [Bedienung §3.4](HANDBUCH_BEDIENUNG.md#34-wärmepumpe) · [Wärme & Klima §1 «Schaubild»](HANDBUCH_WAERME_KLIMA.md#schaubild) ·
> [Einstellungen §7.2](HANDBUCH_EINSTELLUNGEN.md#72-die-fläche).

## 1. Der Rahmen — entschiedene Fragen, die dieses Konzept nicht neu aufrollt

| Entscheid | Folge |
| --- | --- |
| **Haus-Mitte des Energieflusses = Rest ohne einzeln gezeigte Geräte** (#314, bestätigt 20.10.2026) | Die Mitte bleibt der Rest; ein Gesamtverbrauch darf *zusätzlich* erscheinen (Stufe 1, nicht gebaut). |
| **Kein Hausverbrauchs-Sensor** (25.07.2026) | bleibt Nicht-Ziel. |
| **eedc wirkt nicht nach außen** (31.08.2026) | Chips und Kacheln zeigen Gemessenes, keine Schaltflächen; «steuerbar» ist keine Aussage, die eedc kennt. |
| **Modus wird gemessen, nicht abgeleitet** (21.08.2026) | keine Standby-Schwelle; eine gemessene Ruhe (`hvac_action: idle`) ist der Weg für «Leerlauf» (Stufe 1). |
| **«Jetzt» nur im Energiefluss** (27.08.2026) — **bewusst geöffnet am 23.10.2026** | Der Hub-Block «Überblick» trägt **dieselbe Energiefluss-Kachel** als herausgelöste Komponente; sie bleibt die einzige «Jetzt»-Fläche, nur an zwei Orten. Lebensdauer-Kennzahlen stehen in einem eigenen Block («Kennzahlen (gesamte Laufzeit)»). |
| **Live-Abschnitte parken, kein Sonder-Schalter** (28.06.2026) | Der Überblick ist ein gewöhnlicher Block: einklappbar, verschiebbar, fokussierbar, seine zwei Elemente parkbar. |
| **Deep-Link-IDs sind Vertrag** (22.09.2026) | ein neuer Hub-Block = eine neue Fokus-ID (`ueberblick`, Zuwachs). |
| **Die Bauart entscheidet keine Größe** (R1, ADR-002/P13) | Was ein Gerät liefern kann, sagt der zugeordnete Zähler. Die Bauart wählt nur, **an welchem Bildobjekt** eine Kachel steht, und wirkt in den Datenquellen nur über die Registry (`bedingung`/`weich`). |

## 2. Stufe 2 — Block «Überblick» (gebaut für Wärme/Klima)

**Leitregel:** Die Energiefluss-Kachel ist **eine** Komponente (`components/live/EnergieFlussKachel.tsx`), die an zwei Orten steht: im
Live-Energiefluss (Bilanz der Anlage, unverändert — Bitgleichheit per Snapshot-Wächter) und im Block «Überblick» je Gerätetyp (Facetten
der Geräte auf einem Panorama). Kacheln nur für Werte mit Sensor; keine Kachel je Modus — Wert, Farbe und Modus-Zeile wechseln.

| Teil | Form |
| --- | --- |
| **Block** | oberster Block der Hub-Typ-Seite (zuerst nur Wärmepumpe; E-Mobilität folgt), auch bei gespeicherter Block-Reihenfolge vorn (`voranstellen`). Desktop: Schaubild 2/3, «Auf einen Blick» 1/3; Handy gestapelt. Summary statisch «Schaubild · ‹Gerät›». |
| **Panorama** | ein Bild je Typ, 1312 × 816, hell und dunkel bildgleich (beide gestapelt, Umschaltung über das Farbschema). **Das Bild zeigt immer alle Gerätearten, deine Anlage zeigen die Kacheln.** Eine **Anker-Karte** (Objekt → x/y % des Bildes) liegt als Tabelle neben dem Code; neues Bild = neue Karte. |
| **Kacheln** | Maße wie im Energiefluss (`computeDims`), **Maßstab wie im Energiefluss**: k = 1312 / W mit W = 360 · 450 · 600 nach Containerbreite — Kachel und Schrift sind bei gleicher Breite pixelgleich mit dem Energiefluss. **Zwei Reihen im Bild** (Anker-y unter 50 % → oben), Kachel-x = Anker-x mit 1-D-Schub, Linie zum Objekt mit Saum, **keine kreuzenden Linien** (Probe + Nachbartausch). Reihenkapazität wie im Energiefluss; der Rest wird gruppiert («Innengeräte (n)», «Wärmepumpen (n)» mit Σ Leistung, «Weitere (n)»), Tipp auf eine Gruppe öffnet die Liste unter dem Bild. Wert-Kacheln (Temperatur, Strom heute) tragen immer die Rollenfarbe. |
| **Objekt-Zuordnung Wärme/Klima** | Leistung + Modus des Geräts: Luft-Wasser → Außengerät · Sole/Grundwasser → Technik-Schrank · Brauchwasser → Speicher · Luft-Luft → Klima-Außengerät; Innengeräte → die drei Innengeräte im Bild, ab dem vierten gruppiert; Warmwasser-Temperatur → Speicher; Strom heute → Zähler; Außentemperatur (Wetterdienst) → Himmel. Vorlauf/Rücklauf/Heizstab haben Anker, aber erst mit Stufe 3 Werte. Seit P-433-2c je Gerät **«Wärme heute»** (aus dem Tag-Detail) am selben Heizkreis-Objekt wie Vorlauf · Rücklauf; nur mit Wert, nicht in der «Ohne Sensor»-Zeile. |
| **Ohne Sensor** | eine Zeile unter dem Bild «Ohne Sensor, deshalb ohne Kachel: … → Datenquellen zuordnen». Der Block erscheint auch ganz ohne Live-Werte (das Bild erklärt den Typ). |
| **Tooltip** | `data-title` wie im Energiefluss (ein Tooltip-Hook für die ganze App): Name · Leistung · Modus · heute kWh · Herkunft («Live-Snapshot», «HA-LTS (Tageszähler)», «Wetterdienst»). Die Entität steht nicht darin (benannte Grenze: der Hub lädt die Datenquellen-Antwort nur im zugeklappten Block «Einstellungen»). |
| **Zustand** | vom Gerät (Betriebsmodus-Kanon); «Kühlen (passiv)» aus dem Stammdatum `kuehlung_art`. Der Modus-Chip ist eine eigene UI-Komponente (`ui/ModusChip`), Farbpunkt in der Farbe der Funktion (`lib/funktionsFarben.ts`). |
| **«Auf einen Blick»** | für das im Selektor gewählte Gerät **bis zu drei Karten** (Gestalt nach dem Mockup, P-433-2c): **(1) Gerätekarte** — Name + Modus-Chip, Leistung jetzt groß (Schriftgrad der Cockpit-KPI-Kachel), daneben der Anlagen-Ring = Gauge «Eigenverbrauch» des Cockpits, beschriftet **«Eigenverbrauch (Anlage)»** (EV-Quote der Anlage inkl. Speicher-Entladung, kein Wert je Gerät; nur wenn er geliefert wird), darunter Warmwasser · Zusatzheizung · Vorlauf · Rücklauf · Spreizung · Außentemperatur; ohne Vorlauf und Rücklauf die Fußzeile «Vorlauf und Rücklauf erscheinen hier, sobald zugeordnet». **(2) «AZ heute»** — Arbeitszahl des Tages groß, darunter die Herleitung «x kWh Wärme ÷ y kWh Strom» aus Zähler und Nenner des Backends und je Funktion die Arbeitszahl; dazu Strom und Wärme heute (ohne Arbeitszahl heißt die Karte «Heute» und trägt nur die Mengen). **(3) «Betrieb heute»** — Stunden je Betriebsart des Tages aus der Mitschrift des Modus-Sensors (Heizen · Warmwasser · Kühlen · Lüften · Entfeuchten, nur mit Stunden; «Kühlen passiv» bei passiv kühlendem Gerät). Jede Zeile und jede Karte nur mit Wert; keine Kosten, kein CO₂. **Gestrichen:** Kompressor-Starts (kein Feld), PV-Anteil je Gerät (nicht geplant, Gernot 24.10.), «seit hh:mm». |
| **Live-Datenpfad** | eigener Hook im Blockinhalt: Live-Antwort alle 5 s, Wetter und Tag-Detail alle 5 min, nur bei sichtbarem Tab; zugeklappt oder ganz geparkt ist der Inhalt nicht montiert, dann fragt nichts. Ein offener Hub-Tab mit aufgeklapptem Überblick fragt Home Assistant also im 5-s-Takt — benannte Grenze. Werte aus `GET /api/live/{id}`, kein zweiter Live-Pfad im Backend. |
| **Mehrere Geräte** | Kacheln aller Geräte im Bild (gleicher Anker ⇒ Gruppe), Karte des gewählten Geräts. |

**Datenquellen nach Betriebsart (#431, Variante C) — Teil von Stufe 2.** Bleibt in den Einstellungen. Für eine Wärmepumpe bündelt die
Zuordnung die Felder in Blöcke **Gerät gesamt · Heizen · Warmwasser · Kühlen · Lüften · Entfeuchten**; die Zeile Feld · Quelle · Knöpfe
bleibt die aller Typen, andere Typen behalten die Abschnitte nach Einheit.

- **Die Betriebsart ist ein Registry-Attribut** (`betriebsart` je Feld, `core/field_definitions/registry.py`); jedes WP-Feld trägt genau eine.
- **Sichtbar** ist ein Block, wenn mindestens ein Feld seiner Betriebsart in der ersten Reihe steht (nicht `erweitert`). Was in der
  ersten Reihe steht, entscheidet allein die Registry: die Live-Felder tragen dieselben weichen Bedingungen wie ihre kWh-Geschwister
  (Leistung Heizen `!brauchwasser`, Leistung und Temperatur Warmwasser `!luft_luft`), die Kühl-Felder die weiche Bedingung **`kuehlt`**
  — ein Funktions-Stammdatum (Klimagerät oder `kuehlung_art` aktiv/passiv), keine Bauart. Erweiterte Felder bleiben unter
  «Weitere Größen erfassen»; zugeordnet rücken sie in ihren Block.
- **Status im Blockkopf in Wörtern, keine Arbeitszahl:** «vollständig» (Strom und Wärme gedeckt) · «fehlt: Strom, Wärme» · «passiv» ·
  «aus Betriebsmodus abgeleitet» (kein eigener Stromzähler, aber Betriebsmodus-Sensor und Gesamtstrom). Je Feld zählt ● Sensor ·
  Σ durch andere gedeckt · ⊘ keine. Ein Block nur mit Leistung oder Temperatur hat keinen Status.
- **Kein «+ Betriebsart»** in der Zuordnung — die Betriebsarten folgen der Investition.
- **Der Betriebsart-Zähler Heizen** sagt im Hinweis, dass er Vorrang vor «Strom Heizen» hat; wer getrennt misst, lässt ihn leer.

## 3. Entscheide

| # | Frage | Entscheid |
| --- | --- | --- |
| E2 | Wo die Geräte-Details leben | Block «Überblick» im Komponenten-Hub je Typ, mit den Energiefluss-Kacheln auf dem Panorama (23.10.2026). Ein Abschnitt «Geräte» neben dem Fluss ist Rückfall, nicht gebaut. |
| E3 | PV-Anteil je Verbraucher | **nicht geplant, kein Trigger** (24.10.2026): die PV-kWh ist anlagenweit einmal gutgeschrieben, eine Zuordnung je Gerät ändert keine Zahl, die ein Anwender sieht; an der Wallbox wäre sie mit der heutigen Einspeise-Deckung identisch (Messung 24.10.). **E3a:** eine anlagenweite Zahl in «Auf einen Blick» — gebaut als Gauge «Eigenverbrauch» («(Anlage)»), dieselbe Zahl wie das Cockpit. |
| E6 | «Standby» | gemessene `hvac_action: idle` als «· Leerlauf» über die zweite Kachelzeile; keine Schwelle (Stufe 1, nicht gebaut). |
| E9 | Reihenfolge | Überblick Wärme/Klima mit Variante C → «Kompakt» (Stufe 1) → Temperaturen + Heizstab (mit #432) → Überblick E-Mobilität → Verbraucher-Rahmen. |
| E11 | Name des Blocks `status` | «Kennzahlen (gesamte Laufzeit)», ID bleibt. |
| E12 | Unbekannter Betriebsmodus-Wert | fester Kanon + Werte-Liste am Feld + Daten-Checker-Hinweis; keine Synonyme. |
| — | Maßstab der Kacheln | wie im Energiefluss (k = 1312 / W), nicht ein fester Faktor. |
| — | Position des Blocks bei gespeicherter Reihenfolge | vorn (`voranstellen` in der Block-Hülle). |
| — | Datenquellen-Blockkopf | Status-Wörter, keine Arbeitszahl. |
| — | Poll-Hook teilen | nein, eigener Hook; Zusammenführung mit dem Cockpit später mit eigenem Go. |
| — | Demo-Daten | die Demo-Wärmepumpe trägt Modus «Heizen» und die Antwort eine Warmwasser-Temperatur; die Demo-Knoten nehmen die IDs der aktiven Investitionen der Anlage (n-ter Demo-Knoten eines Typs = n-te Investition), sonst ihre festen IDs. |
| — | Panorama E-Mobilität | wartet, bis Wärme/Klima mit dem Melder geklärt ist. |

## 4. Grenzen (benannt)

- **Ein Bild je Typ:** eine Luft-Luft-Anlage sieht Erdsonden und Speicher im Bild. Sole-, Brauchwasser- und Luft-Luft-Anlagen haben heute
  alle Kacheln in der oberen Reihe.
- **Warmwasser-Temperatur** ist ein anlagenweiter Wert (erste Wärmepumpe mit Sensor); die Zeile «Ohne Sensor …» nennt sie unabhängig von der Bauart.
- **Heute-Werte je Gerät** (Wärme, Arbeitszahl) nur, wenn das Gerät heute einen Strom-Beitrag hat.
- **«Betrieb heute»** nur mit Home-Assistant-Modus-Sensor und erst ab Beginn der Betriebsart-Mitschrift; **Leerlauf** zählt nicht
  getrennt (die Mitschrift schreibt ihn nicht — eine Stunde «Heizen · Leerlauf» zählt als Heizen). Ein Tag, an dem das Gerät nur
  aus war, zeigt «Heute kein Betrieb».
- **Kachel «Wärme heute»** kommt aus dem Tag-Detail (alle 5 min), nicht aus der Live-Antwort; eine Zweitzeile Heizen · Warmwasser
  gibt es nicht (die Gerätezeile liefert Wärme je Funktion nicht).
- **Tag-Detail hat keinen Demo-Schalter:** im Demo-Modus zeigt die Karte Heute-Wärme und -Arbeitszahl des echten Tages.
- **Live-Kacheln ohne Home-Assistant-Zuordnung** (MQTT ohne Modus) gibt es nur für die zugeordneten Zahlen; der Modus bleibt leer.
