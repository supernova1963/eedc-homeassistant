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
| **Block** | oberster Block der Hub-Typ-Seite (Wärmepumpe; Wallbox und E-Auto seit P-433-2b K1 ohne Schaubild, §2b), auch bei gespeicherter Block-Reihenfolge vorn (`voranstellen`). Desktop: Schaubild 2/3, «Auf einen Blick» 1/3; Handy gestapelt. Summary statisch «Schaubild · ‹Gerät›». |
| **Panorama** | ein Bild je Typ, 1312 × 816, hell und dunkel bildgleich (beide gestapelt, Umschaltung über das Farbschema). **Das Bild zeigt immer alle Gerätearten, deine Anlage zeigen die Kacheln.** Eine **Anker-Karte** (Objekt → x/y % des Bildes) liegt als Tabelle neben dem Code; neues Bild = neue Karte. |
| **Kacheln** | Maße wie im Energiefluss (`computeDims`), **Maßstab wie im Energiefluss**: k = 1312 / W mit W = 360 · 450 · 600 nach Containerbreite — Kachel und Schrift sind bei gleicher Breite pixelgleich mit dem Energiefluss. **Zwei Reihen im Bild, Reihe nach Anker-Art** (P-433-2d, Gernot 26.10.2026: **Technik oben, Räume unten** — oben Himmel, Geräte A/B/C/F/O, Speicher D/E, Hydraulikmodul G (Vorlauf · Rücklauf und Wärme heute ohne Stammdatum), Zählerreihe I; unten die Heizkreise J/K mit Vorlauf · Rücklauf und Wärme heute und die Innengeräte L/M/N; Tabelle `ANKER_REIHE` neben der Anker-Karte, Bildlage y < 50 % als Rückfall für Anker ohne Eintrag), Kachel-x = Anker-x mit 1-D-Schub, Linie zum Objekt mit Saum, **keine kreuzenden Linien** — innerhalb einer Reihe Probe + Nachbartausch, zwischen den Reihen **Reihenwechsel bei Kreuzung** (Entscheid Gernot 26.10.2026): kreuzt eine Linie der oberen eine der unteren Reihe (gezeichnete Linie oder Strecke Kachelmitte → Anker), wechselt die beteiligte Kachel, die nicht in der Reihe ihrer Bildlage steht (größter Abstand Anker-y ↔ Reihe zuerst), in die Reihe ihrer Bildlage, und das Layout wird neu gerechnet (Kapazität und «Weitere» inklusive); höchstens n Wechsel, im schlimmsten Fall steht jede Kachel in ihrer Bildlage, und dort kreuzt keine Linie die andere Reihe. **Zwei Plätze wie Netz und Speicher** (P-433-2e, Gernot 26.10.2026, nur Desktop ab 500 px): links die Gerätekachel der Wärmepumpe am ersten belegten Anker in fester Rangfolge A → C → F (Entscheid Master 26.10.2026: unabhängig von der Listenreihenfolge; weitere Geräte am selben Anker mit ihr als «Wärmepumpen (n)»; fällt ein Rang zurück, wird der nächste versucht), rechts die an O (`PLATZ_ANKER` neben der Anker-Karte, Lage gemessen am Bild v4); x am Bildrand wie die äußerste Reihenkachel, y = Anker-y geklemmt — links zwischen Unterkante obere Reihe + 12k und 45 % der Bildhöhe, rechts zwischen 58 % und Oberkante untere Reihe − 12k; Linie von der dem Anker nächsten Kante. Die Plätze werden vor den Reihen aus der Kachelliste genommen (Reihen = der 2d-Lauf, `dims` aus den Reihen); ein belegter rechter Platz kürzt die untere Reihe um eine Kachelbreite. Schneidet die Platz-Linie eine Reihenlinie (gezeichnet oder Mitte → Anker) oder läuft eine Reihenlinie durch das Platz-Rechteck, **Rückfall** in die Reihe (links höchstens drei Versuche, je ein Reihenlauf). Am Handy keine Plätze. Reihenkapazität wie im Energiefluss; der Rest wird gruppiert («Innengeräte (n)», «Wärmepumpen (n)» mit Σ Leistung, «Weitere (n)»), Tipp auf eine Gruppe öffnet die Liste unter dem Bild. Wert-Kacheln (Temperatur, Strom heute) tragen immer die Rollenfarbe. |
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

## 2b. E-Mobilität — Kern K1 (gebaut 27.10.2026, unveröffentlicht)

Grundlage: Definitions-Blatt «Überblick E-Mobilität» Fassung 3 und Bauplan K1 (intern). Die Hub-Typ-Seiten **Wallbox** und
**E-Auto** tragen den Block «Überblick» **vorerst ohne Schaubild** (Panorama später, P1) — «Auf einen Blick» in voller Breite,
Park-ID `el:ueberblick-karte` (das Schaubild wird nicht gerendert), Summary «Auf einen Blick · ‹Gerät›», Fokus-ID `ueberblick`.

| Teil | Form |
| --- | --- |
| **Leitsatz** | Registry-Feld = Vertrag, Wert live aus der Integration, **nichts gespeichert** (nur die Zuordnung). Die Felder tragen `nur_live` ⇒ Kanal-Katalog-Ausnahme `nur_live_anzeige` (kein Kanal, keine Mitschrift, kein Mittel im MQTT-Snapshot). Seit K3 tragen Ladezustand, Fahrzeug-Ladezustand und Standort `mitschrift` statt `nur_live` (§2b-K3). |
| **Felder** | Wallbox `ladezustand`, `lademodus` (Zustand), `sitzung_kwh`, `sitzung_dauer_s`, `ladestrom_a`, `phasen_aktiv`, `ziel_ladestand_prozent`, `restzeit_min`; E-Auto `ladezustand_fahrzeug`, `zu_hause` (Zustand), `reichweite_km`, `ziel_ladestand_prozent`, `restzeit_min`. Alle `erweitert`, Datenquellen-Abschnitt «Zustand & Sitzung» (`abschnitt`), Kopf «Zustands-Chip: zugeordnet / fehlt». Keine Einheiten-Umrechnung. |
| **Kanon** | `core/zustands_kanon.py`, tabellengetrieben (je Feld Kanon + Werte-Tabelle + Normalisierer + Klartext); belegt: SMA EV Charger, evcc (Lademodus), Smart #1, go-e (Codes nur MQTT), HA-Zone. Fremder Wert ⇒ kein Chip + Daten-Checker-INFO (E12-Muster); `core/betriebsmodus.py` unberührt. |
| **Leser** | `betriebsmodus_live.lade_zustaende_live` — die Abfrage nimmt jeden Typ mit Zustandsfeld (statt nur Wärmepumpe); derselbe 60-s-Takt wie der Modus, ein gebündelter HA-Abruf für alle E-Mob-Felder; HA über die `live`-Entität, sonst MQTT, «keine» schließt MQTT aus. |
| **Builder** | Wallbox-Knoten `ladezustand(_label)`, `lademodus(_label)`, `sitzung{kwh,dauer_s}`, `ladestrom_a`, `phasen_aktiv`, `ziel_prozent`, `restzeit_min`; `LiveFahrzeug` `reichweite_km`, `ladezustand(_label)` (des Fahrzeugs), `ziel_prozent`, `restzeit_min`, `zu_hause`, `dienstwagen`; Antwort `fahrzeuge_ohne_wallbox` (Autos an keiner live liefernden Wallbox). Alles nur mit Wert, keine Summe liest es. |
| **Gerätekarte Wallbox** | **ein** Chip «Lädt · PV» (Zustand + Lademodus, Lademodus nur bei Lädt/Wartet), Farbe der Funktion (Lädt = Wallbox-Rolle, Wartet = Status-Gelb, Fehler = Signal-Rot, sonst Grau), **keine Rahmenfarbe**; Ladeleistung groß, Anlagen-Ring, Fahrzeugzeile(n) mit Ladestand-Leiste und Zielmarke (`ui/LadestandLeiste`), Ziel · Restzeit, Fußzeile «3 Phasen · 16 A · 9,8 kWh in dieser Sitzung · 2 h 10 min», Link «Hersteller-Oberfläche öffnen» (Stammdatum `oberflaeche_url`, nur http/https). |
| **Gerätekarte E-Auto** | Ladestand groß mit Leiste, Reichweite, Ring, Ort «an ‹Wallbox›» (nur eindeutig), Standort (Zone), Ladeleistung nur mit eigenem Knoten, Ziel · Restzeit; eigener Zustands-Chip nur ohne Wallbox-Zuordnung (eine Aussage je Fläche); Chip «Dienstwagen». |
| **«Heute»** | Ladung heute (Live-Tageswert; am Auto nur mit eigenem Knoten) und PV-Ladung heute «(Anlage)» aus dem Tag-Detail. **Keine Kopfzahl PV-Anteil**: das Tag-Detail trägt keine Wallbox-Menge — die Kopfzahl käme nur aus zwei Pfaden (gemessen 27.10.2026). |
| **Energiefluss** | Wallbox-Kachel: gemessener Zustand ≠ «lädt» ⇒ zweite Zeile als Chip (gedämpft bei «Kein Fahrzeug»/«Fertig»), «lädt» ⇒ Auto-Zeile wie bisher; Tooltip «Zustand: …». Kachel-Komponente unverändert. |
| **Welches Auto** | nur aus der Zuordnung des Builders (eine live liefernde Wallbox ⇒ eindeutig; zwei ⇒ «geschätzt», alle Autos + Satz). Keine Korrelation aus «verbunden». |

### 2b-K2a. Fahrzeug am Ladepunkt, Gast, Zuordnung (gebaut 27.10.2026, unveröffentlicht)

Grundlage: Bauplan K2 Fassung 2 (intern, nach Gegenprüfung), Sitzung K2a; Entscheide Gernot 27.10.2026 **D1** (bleibt genau
eine Wallbox ohne Steuerungs-Aussage, ist sie «eindeutig») und **D2** (der Rohtext der Steuerung steht nicht auf der Karte).

| Nr. | Entscheid |
| --- | --- |
| K2-1 | **Zuordnung nur nach Blatt §4:** eine Wallbox ⇒ heutige Regel; mehrere ⇒ nur über den Treffer `fahrzeug_am_ladepunkt` ↔ `kennung_in_steuerung`; nie Korrelation aus zwei «verbunden». |
| K2-2 | **Gast** = das Textfeld hat **geantwortet** und ist leer (HA: State vorhanden, Text leer — evcc `null`; MQTT: Cache-Eintrag «») **und** `ladezustand` ∈ verbunden · wartet · lädt · fertig. «Leer» entsteht nie aus der Zuordnungs-Konfiguration; ohne Antwort kein Gast. |
| K2-3 | **Feldart Text** = Registry-Feld `zustand: True, text: True` ohne Kanon; abgeleitete Menge `TEXT_LIVE_FELDER`/`ist_text_feld` (`core/field_definitions/karten.py`), keine getippte Liste. Inbound: eine Weiche «leer ist ein Wert» nur für Textfelder; kein Kanon, kein Checker «fremder Wert», keine Werte-Tabelle, kein Kanal (`nur_live`). |
| K2-4 | **Stammdatum** `kennung_in_steuerung` am E-Auto (Text, optional, ≤ 80 Zeichen; Vergleich getrimmt, ohne Groß/Klein), Backend `PARAM_E_AUTO` + Client-SoT, Formular als Text. |
| K2-5 | **`parent_key`, Summen, Residual und der Layoutcode des Energieflusses bleiben unverändert** — der Treffer ändert nur `fahrzeuge` und die Kennzeichen. Golden Master live-komponenten: Bestand bitgleich. |
| K2-6 | **Kein drittes Zuordnungswort:** `fahrzeuge_zuordnung` bleibt `eindeutig`/`geschaetzt`; Treffer, Gast und unbekannt heißen «eindeutig» mit `fahrzeuge_quelle = "steuerung"` (dazu `gast` bzw. `fahrzeug_unbekannt`). «Alle Autos» bei «geschätzt» sammeln nur aus «geschätzt»-Knoten. |
| K2-10 | Ein gemeldeter Name **ohne Treffer**: Karte «Fahrzeug der Steuerung unbekannt» (D2), Daten-Checker INFO `emob_kennung_unbekannt` mit Rohtext und Handgriff «Kennung am E-Auto eintragen». |
| K2-11 | Farbe = Rolle, kein Gast-Farbton, keine Rahmenfarbe; «Gastfahrzeug» ist Text. Der Client rechnet nichts; keine Monatsrechnung, keine Gast-kWh. |
| K2-12 | **Schnitt:** K2a = Text, Stammdatum, Zuordnung, Gast, Checker, Karte, Datenquellen; K2b = evcc-Ladezustand aus drei Binär-Sensoren (Option A), Gateway-Text, Preset «evcc Ladepunkt» (§2b-K2b). |

**Zuordnung in zwei Schritten** (`live_komponenten_builder._ordne_fahrzeuge_zu`): Schritt 1 setzt `parent_key` reihum wie bisher;
Schritt 2 (`_fahrzeug_anzeige_zuordnung`) liest je Wallbox-Knoten das Textfeld und verteilt die übrigen Autos auf die Wallboxen
ohne Aussage — genau eine ⇒ «eindeutig» (D1), mehrere ⇒ reihum «geschätzt», keine ⇒ `fahrzeuge_ohne_wallbox`. **Benannte
Grenzen:** Gast nur mit Fahrzeugerkennung (evcc, openWB); ein leerer `input_text` in HA gilt nicht als Gast; ein leerer
retained MQTT-Payload löscht die Nachricht am Broker (nach einem Neustart keine Antwort bis zur nächsten Meldung). Der
`parent_key` eines Auto-Knotens (eigener Leistungssensor) bleibt der aus Schritt 1, auch wenn die Steuerung das Auto an einer
anderen Wallbox meldet (K2-5): er entscheidet nur, dass der Auto-Knoten im Energiefluss keine eigene Kachel bekommt und aus
dem Restverbrauch fällt; welches Auto eine Kachel und eine Karte nennen, kommt aus `fahrzeuge`.

### 2b-K2b. Option A, Gateway-Text, Preset evcc (gebaut 27.10.2026, unveröffentlicht)

Grundlage: Bauplan K2 Fassung 2, Sitzung K2b; Entscheid Gernot 27.10.2026 **D3** (am Betriebsmodus bleibt der Gateway-Knopf aus).

| Nr. | Entscheid |
| --- | --- |
| K2-7 | **Option A** statt eines Mehrfach-Sensor-Lesers (K1 HALT K-9): drei Rollen-Felder `evcc_verbunden` · `evcc_laedt` · `evcc_freigegeben` (Zustand, Kanon `an`/`aus`; `on`/`true` ⇒ an, `off`/`false` ⇒ aus; `1`/`0` **nur** über MQTT). Der Leser (`betriebsmodus_live._kombiniere_option_a`) setzt den Ladezustand zusammen, **nur wenn kein gemessener vorliegt**: ¬verbunden ⇒ kein Fahrzeug · verbunden ∧ lädt ⇒ lädt · verbunden ∧ ¬freigegeben ⇒ wartet · sonst verbunden. Ohne «lädt»/«freigegeben» nie «lädt»/«wartet», «fertig» kennt Option A nicht. Builder und Energiefluss unverändert (sie lesen `ladezustand`). |
| K2-8 | **Gateway-Text als Weiche am Zielfeld:** `transform_payload(…, *, als_text)` liefert an ein Zustandsfeld den getrimmten Rohstring (`plain`) bzw. den Wert am Pfad als Text (`json`/`json_array`), ohne Faktor/Offset; Republish unverändert. Ein Wort auf ein Zahlenfeld bleibt `transform_fehler` ohne Republish. Kein neuer `payload_typ`, keine 400-Regel. **Am Betriebsmodus** bleibt das Gateway beim Zahlen-Weg und die Fläche zeigt keinen Knopf (D3). |
| K2-9 | **Preset «evcc Ladepunkt»** nur mit belegten Einheiten (evcc `server/mqtt.go encode()`: Floats `%.3f`, `time.Duration` als ganze Sekunden, Bools `true`/`false`, `nil` als leerer String): `chargePower` W · `sessionEnergy` Wh ×0,001 · `chargeDuration` s · `chargeRemainingDuration` s ×1/60 · `phasesActive` · `chargeTotalImport` kWh ×1 als Zählerstand unter `energy/` (die Bauplan-Annahme Wh war falsch, Quelle `api.MeterEnergy`) · `mode` · `connected`/`charging`/`enabled` · `vehicleName`. Nicht im Preset: Auto-Werte (`vehicleSoc`/`vehicleRange`), undokumentierte Topics. Presets bietet die Oberfläche derzeit nicht an (Aufruf über die API). |

**Release-Regel (Gernot 27.10.2026):** kein Release der E-Mobilitäts-Änderungen ohne Panorama — K1 bis K3 sammeln sich
ungepusht, das Panorama schließt das Paket. **K3** («Betrieb heute» aus einer typoffenen Mitschrift) ist gebaut (§2b-K3). Der
evcc-Ladezustand aus drei Binär-Sensoren (offen aus K1) ist mit Option A (K2-7) gelöst; Weg B (Template-Sensor) bleibt für
andere Integrationen.

### 2b-K3. Zustands-Mitschrift typoffen, Karte «Betrieb heute» (gebaut 28.10.2026, unveröffentlicht)

Grundlage: Konzept-Nachtrag K3 und Bauplan K3 (intern); Entscheide Gernot 28.10.2026 **D4** (Ladevorgänge über einen
Wechsel-Zähler: ja) · **D5** (Standort mitschreiben: ja) · **D6** (Option A auch in der HA-Mitschrift: bauen, in K3) ·
**D7** (Lademodus mitschreiben: nein).

| Nr. | Entscheid |
| --- | --- |
| K3-1 | **Eine Regel:** jedes Registry-Zustandsfeld mit Kanon und `mitschrift: True` bekommt die Mitschrift der Betriebsart (Anteil der Stunde je Kanon-Wert) — Wallbox `ladezustand`, E-Auto `ladezustand_fahrzeug`, `zu_hause`; abgeleitete Menge `MITSCHRIFT_LIVE_FELDER`. Der Betriebsmodus behält seinen Pfad byte-gleich. |
| K3-2 | Kanal `zustand:inv:<id>:<feld>:<wert>` (`mean`, Anteil); Wechsel-Zähler `wechsel:inv:<id>:ladezustand:laedt` (`sum`, fortlaufend). |
| K3-3 | Snapshot `inv:<id>:<feld>:<wert>` (Anteil des 5-Minuten-Fensters) und `inv:<id>:ladezustand:wechsel_laedt` (Anzahl). |
| K3-4 | Inbound-Fenster je (Gerät, Feld); Ladezustand über `ladezustand_aus_werten` (gemessener zuerst, sonst Option A) — eine Funktion für Live und Mitschrift. |
| K3-5 | HA typoffen (`_get_zustand_history`), Option A über HA als verschränkte Zeitlinie der drei Verläufe; ein gemessener Ladezustand geht vor. |
| K3-6/7 | Leser `zustand_anteile_je_stunde`, Layer `stunden_je_zustand` (WP-Fassungen sind Hüllen, bitgleich); Tag-Detail `emob_betrieb` (nur Tag). |
| K3-8 | Karte «Betrieb heute» (`BetriebKarteEmob`): Wallbox Lädt · Verbunden · Wartet · Fertig + «Ladevorgänge heute»; E-Auto Laden (Lädt · Lädt DC · Verbunden) und Standort (Zu Hause · Unterwegs); `kein_fahrzeug`/`gesperrt`/`fehler`/`nicht_verbunden` kein Betrieb; Farbe = Funktion, keine Rahmenfarbe; «Heute kein Betrieb» bei gemessener 0. |

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
| — | Panorama E-Mobilität | später (P1, Gernot 27.10.2026): erst die Karten (K1), das Panorama schließt das E-Mobilitäts-Paket; kein Release vorher. |
| B6 | Wallbox-Zustand | **«Zustand nur gemessen»** (P9, 27.10.2026; vorher «gibt es nicht»): ein Zustand nur aus einem zugeordneten Feld, nie aus der Leistung, keine Schwelle. |

## 4. Grenzen (benannt)

- **Ein Bild je Typ:** eine Luft-Luft-Anlage sieht Erdsonden und Speicher im Bild.
- **Warmwasser-Temperatur** ist ein anlagenweiter Wert (erste Wärmepumpe mit Sensor); die Zeile «Ohne Sensor …» nennt sie unabhängig von der Bauart.
- **Heute-Werte je Gerät** (Wärme, Arbeitszahl) nur, wenn das Gerät heute einen Strom-Beitrag hat.
- **«Betrieb heute» E-Mobilität** (K3): ab der Zuordnung, nicht rückwirkend; nur abgeschlossene Stunden; über MQTT
  5-Minuten-Fenster (Broker-Lücke = Stunde ohne Zeile, nach Neustart erst ab der nächsten Meldung); der erste Wert nach einem
  Neustart ist kein Ladevorgang; der Wechsel-Zähler schreibt nur vorwärts; Option A über HA braucht `evcc_verbunden` (ohne
  «lädt»/«freigegeben» nur Verbunden/Kein Fahrzeug); Gast und Fahrzeug je Stunde werden nicht mitgeschrieben; das Tag-Detail
  hat keinen Demo-Schalter.
- **«Betrieb heute»** nur mit Home-Assistant-Modus-Sensor und erst ab Beginn der Betriebsart-Mitschrift; **Leerlauf** zählt nicht
  getrennt (die Mitschrift schreibt ihn nicht — eine Stunde «Heizen · Leerlauf» zählt als Heizen). Ein Tag, an dem das Gerät nur
  aus war, zeigt «Heute kein Betrieb».
- **Kachel «Wärme heute»** kommt aus dem Tag-Detail (alle 5 min), nicht aus der Live-Antwort; eine Zweitzeile Heizen · Warmwasser
  gibt es nicht (die Gerätezeile liefert Wärme je Funktion nicht).
- **Tag-Detail hat keinen Demo-Schalter:** im Demo-Modus zeigt die Karte Heute-Wärme und -Arbeitszahl des echten Tages.
- **Live-Kacheln ohne Home-Assistant-Zuordnung** (MQTT ohne Modus) gibt es nur für die zugeordneten Zahlen; der Modus bleibt leer.
