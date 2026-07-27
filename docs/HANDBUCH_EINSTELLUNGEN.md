
# eedc Handbuch — Teil III: Einstellungen

**Version 4.0** | Stand: 2026-07-25

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Infothek](HANDBUCH_INFOTHEK.md) | [Sensor-Referenz](SENSOR-REFERENZ.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Einstellungen-Überblick](#1-einstellungen-überblick)
2. [Stammdaten](#2-stammdaten)
3. [Komponenten](#3-komponenten)
4. [Infothek & Berichte](#4-infothek--berichte)
5. [Daten](#5-daten)
6. [Integration](#6-integration)
7. [Datenquellen — feld-zentrische Zuordnung](#7-datenquellen--feld-zentrische-zuordnung)
8. [System](#8-system)
9. [Hintergrund: Energieprofile & Snapshot-Architektur](#9-hintergrund-energieprofile--snapshot-architektur)

---

## 1. Einstellungen-Überblick

Alles Einrichten und Datenpflegen liegt gesammelt unter **Einstellungen** (Zahnrad in der oberen Leiste). Statt eines Dropdowns führt der Eintrag zu einem **Kachel-Raster**, das nach sieben Kategorien gegliedert ist:

| Kategorie | Zweck |
|-----------|-------|
| **Stammdaten** | Anlage, Strompreise, Solarprognose, Community-Share |
| **Komponenten** | Geräte je Typ anlegen und pflegen (PV, Speicher, Wärmepumpe, E-Auto, Wallbox, Balkonkraftwerk, Sonstiges) |
| **Infothek** | Wissensbasis (Verträge, Dokumente) und die PDF-Berichte |
| **Daten** | Monatsdaten & Monatsabschluss, Energieprofil-Pflege, Daten-Checker, Ersteinrichtung |
| **Integration** | Verbindungen (MQTT-Broker, Home Assistant), Export, Statistik-Import, Import-Assistenten |
| **Datenquellen** | feld-zentrische Zuordnung: welche Quelle den Wert jedes eedc-Feldes liefert |
| **System** | Allgemein (Theme), Demo-Daten, Backup, Protokolle |

### 1.1 Suche und Status

- **Suche:** Über dem Kachel-Raster gibt es ein Suchfeld („Suchen in allen Einstellungen …"). Es durchsucht **alle** Kategorien gleichzeitig nach Namen und Schlagworten — tippst du z. B. „Token", „CSV" oder „Autarkie", erscheinen die passenden Kacheln quer über die Kategorien.
- **Status-Anzeigen:** Kacheln, deren Bereich Aufmerksamkeit braucht (z. B. eine nicht getestete Verbindung), tragen ein kleines Status-Symbol im Block-Kopf. Die Farbe folgt der app-weiten Schwere-Skala (grün = ok, blau = Info, amber = Warnung, rot = Fehler, grau = kein Zustand). Ein Tooltip nennt den Grund.

### 1.2 Kacheln sind Blöcke

Jede Kachel ist ein **Block** im Sinne von [Teil II §1.3](HANDBUCH_BEDIENUNG.md#13-das-block-modell-klappen-fokussieren-umsortieren-parken): Klick auf den Kopf klappt sie auf, und über das Vergrößern-Symbol (⤢) öffnest du den Inhalt als konzentrierte Vollbild-Ansicht — praktisch bei datendichten Flächen wie der Monatsdaten-Tabelle, dem Daten-Checker oder der Datenquellen-Zuordnung. Die Konfiguration passiert **direkt im Block** (früher lag vieles hinter „öffnen" auf eigenen Seiten).

> **Direktlinks:** Viele Stellen in eedc verlinken direkt auf die passende Einstellungs-Kachel (z. B. „Beheben"-Links im Daten-Checker, „Bearbeiten" in den Komponenten-Sichten, das Zahnrad-Symbol in der Status-Fußzeile). Der Ziel-Block öffnet sich dann automatisch.

---

## 2. Stammdaten

Die **Stammdaten** beschreiben, was deine Anlage ist und mit welchen Rahmenwerten eedc rechnet.

### 2.1 Anlage

Der Anlage-Block zeigt eine Tabelle deiner Anlagen mit einem Bearbeiten-Modal (auch bei nur einer Anlage). Pro Anlage pflegst du:

- **Name, Adresse, Koordinaten, Bundesland** (das Bundesland speist die regionalen Community-Vergleiche).
- **Straße & Hausnummer** fließen in die Geokoordinaten-Ermittlung ein (Nominatim versteht „Musterweg 12"); der Standort wird damit exakter, auch wenn Wetter- und PVGIS-Raster grob bleiben.
- **MaStR-ID** — Marktstammdatenregister-ID mit direktem Link zum Register.
- **Versorger & Zähler** — Strom-, Gas- und Wasserversorger mit beliebig vielen Zählern (Bezeichnung, Kundennummer, Portal-URL, Zählernummer). Beim Anlegen eines Stromvertrags in der Infothek werden Anbieter, Tarif und Zählernummer aus diesen Versorger-Daten vorbelegt.

> **Ausrichtung & Neigung gehören ans PV-Modul, nicht an die Anlage.** Seit der Umstellung auf PV-Modul-Investitionen werden die früheren Anlage-Felder „Ausrichtung"/„Neigung" nicht mehr gepflegt — sie stehen jetzt pro Modul-String im Komponenten-Formular (siehe [§3](#3-komponenten)). Die alten DB-Spalten bleiben für Bestandsinstallationen erhalten, der aktive Code greift nicht mehr darauf zu.

**Wettermodell** (steuert Kurzfrist-Prognose und Wetter-Autofill):

- **auto** (Standard): eedc wählt automatisch (Bright Sky für DE, sonst Open-Meteo best_match).
- **MeteoSwiss ICON-CH2** (2 km, empfohlen für alpine Standorte), **ICON-D2** (2,2 km, DWD/DE), **ICON-EU** (mittlere Auflösung), **ECMWF IFS** (global, 0,25°).

Bei fester Modellwahl versucht eedc zuerst das gewählte Modell und fällt bei fehlenden Daten auf den besten verfügbaren Anbieter zurück (Kaskade). Die verwendete Quelle wird pro Tag in der [Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) mit einem Kürzel (MS/D2/EU/EC/BM) angezeigt.

**Prognose-Basis:** Hier wählst du, auf welcher Quelle der eedc-Lernfaktor und die kalibrierte Prognose aufbauen — OpenMeteo (Standard) oder Solcast (wenn konfiguriert). SFML ist im Code als künftige Erweiterung vorbereitet, geht aber bewusst nicht ins Genauigkeits-Ranking ein.

**Steuerliche Behandlung:**

- **Keine USt-Auswirkung** (Standard): für Anlagen ab 2023 mit Nullsteuersatz (≤ 30 kWp) oder Kleinunternehmer.
- **Regelbesteuerung**: USt auf Eigenverbrauch wird als Kostenfaktor berechnet (Pre-2023, > 30 kWp, AT/CH). Der USt-Satz ist editierbar (DE 19 %, AT 20 %, CH 8,1 %) und passt sich bei Land-Wechsel automatisch an.

### 2.2 Strompreise

Verwalte deine Stromtarife als Tabelle mit Gültigkeitszeiträumen — die Basis jeder Einsparungsberechnung:

- Mehrere Tarife mit **Gültigkeitszeitraum** möglich.
- **Spezialtarife:** Jeder Tarif kann einer Verwendung zugeordnet werden — Standard, Wärmepumpe oder Wallbox. Ohne Spezialtarif nutzt eedc automatisch den Standard-Tarif für die Komponente. Aktive Spezialtarife stehen in der Info-Box oben.
- **Zählergebühr-Tarif:** Neben Grundgebühr lässt sich eine separate Zählergebühr erfassen; Grund- und Zählergebühren werden im Cockpit (Monat/Jahr) getrennt ausgewiesen.

> **Dynamischer Strompreis (Tibber/aWATTar/EPEX):** Den zugehörigen Sensor ordnest du nicht mehr hier, sondern unter **Einstellungen → Datenquellen** dem Feld „Strompreis" zu (siehe [§7](#7-datenquellen--feld-zentrische-zuordnung)). Ohne eigenen Sensor blendet eedc automatisch den EPEX-Börsenpreis (DE/AT via aWATTar) als Overlay im Live-Tagesverlauf ein.

### 2.3 Solarprognose

Diese Kachel kombiniert die PVGIS-Langfristprognose mit den Wetter-Provider-Einstellungen:

- **Systemverluste** (Standard 14 %, für DE typisch), **TMY-Referenz**, **optimale Ausrichtung** (berechnet Neigung/Azimut für deinen Standort).
- **Horizontprofil (Verschattung):** beschreibt, wie hoch Berge/Gebäude/Bäume den Horizont je Himmelsrichtung verdecken — eedc zieht das bei der Langfristprognose ab. Zwei Wege:
  - **Geländeprofil von PVGIS abrufen** — holt das Profil aus PVGIS-Geländedaten (erfasst Berge/Geländekanten, keine Gebäude/Bäume).
  - **Eigene Datei** — lädt ein selbst erstelltes Profil hoch (pro Zeile Azimut + Elevation in Grad, `#` = Kommentar; Azimut 0–360°, Elevation 0–90°, ≥ 4 Punkte). So bildest du feste Hindernisse wie Dachkanten oder Nachbargebäude ab.

  Ist ein Profil hinterlegt, zeigt die Karte Datenpunkte sowie min/max-Elevation; **Löschen** kehrt zu den automatischen Geländedaten zurück. Das Profil bildet **feste** Hindernisse ab — eine jahreszeitlich wechselnde Verschattung (Laubbäume) ändert sich damit nicht mit.
- **Wetter-Provider** (für Autofill/historische Werte): Auto (Bright Sky DE, sonst Open-Meteo), Bright Sky (DWD), Open-Meteo, Open-Meteo Solar (GTI-basiert für geneigte Module).
- **Prognose-Historie:** Jeder Abruf wird gespeichert und bleibt erhalten. **Genau einer ist „Aktiv"** und liefert die SOLL-Werte in *allen* Sichten und Berichten; über „Aktivieren" schaltest du bewusst auf einen anderen — auch auf einen **älteren**, etwa weil er mit einem genaueren Horizontprofil geholt wurde. Mehr dazu: [Prognosen §2.6](HANDBUCH_PROGNOSEN.md#26-die-aktive-pvgis-prognose--eine-und-du-bestimmst-welche).

### 2.4 Community-Share

Der Schalter zum anonymen Teilen deiner Anlagendaten für den [Community-Vergleich](HANDBUCH_BEDIENUNG.md#5-community). Der „Teilen"-Umschalter sitzt im Block-Kopf, der Inhalt zeigt eine **Vorschau** der geteilten Daten (abgeblendet, wenn aus):

- **Anonymisierung:** nur Bundesland, keine Adresse/PLZ.
- **Jederzeit löschbar** — auch rückwirkend (einzelne Monate).
- Der Teilen-Status ist zusätzlich in der Status-Fußzeile sichtbar.

---

## 3. Komponenten

Unter **Einstellungen → Komponenten** legst du deine Geräte an und pflegst ihre Parameter. Anders als die übrigen Kategorien ist dies keine Kachel-Liste, sondern **ein Block je Investitionstyp** (in fester Reihenfolge) mit einem „+ Neu"-Knopf pro Typ. Aus jeder [Komponenten-Sicht](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse) (Was-Achse) führen Bearbeiten-Links direkt hierher.

> **Erfassen ≠ Auswerten:** Hier werden Geräte **angelegt und konfiguriert**. Ihre Kennzahlen und Verläufe siehst du in der Komponenten-Achse (Teil II).

### 3.1 Parent-Child-Beziehungen

| Typ | Wechselrichter-Zuordnung | Pflicht? |
|-----|--------------------------|----------|
| PV-Module | ja | **Ja** — ohne sie fehlt der Bezug zwischen Modulfläche und Umrichter |
| Speicher | optional | **Nein** — ein Speicher **ohne** Zuordnung ist der Normalfall (AC-gekoppelt) |
| E-Auto · Wärmepumpe · Wallbox · Balkonkraftwerk · Sonstiges | – | – |

**Nur PV-Module ohne Wechselrichter tragen ein Warnsymbol.** Bis v4.0.0 wurde auch bei Speichern „Speicher ohne Wechselrichter-Zuordnung" gemeldet — und verleitete dazu, eine falsche Zuordnung anzulegen. Speicher ohne Zuordnung heißen jetzt neutral **„Eigenständige Speicher"**.

> **Die Zeile heißt „Zuordnung", nicht „Kopplung".** eedc kennt **kein** Feld für AC-/DC-Kopplung; die frühere Anzeige „DC-gekoppelt" leitete sich allein daraus ab, *ob* ein Wechselrichter zugeordnet ist — ein AC-Speicher am Hybrid-Wechselrichter war damit falsch beschriftet. Die Zeile nennt jetzt den Wechselrichter beim Namen und erklärt, was die Zuordnung bewirkt.

### 3.2 Anschaffungs- und Stilllegungsdatum

Jede Investition hat zwei Lebenszyklus-Daten, die für **alle** Auswertungen gelten:

> **Das Anschaffungsdatum ist Pflicht** (seit v4.0.1). Es ist die Grenze jeder Auswertung — ohne Datum zählt eine Komponente auch für Zeiträume vor der Anschaffung mit — und der Nullpunkt der Amortisationskurve. Neue Komponenten lassen sich nur noch mit Datum anlegen; für vorhandene meldet es der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md#438-allgemein-alle-komponententypen) als **Fehler** und springt per Klick direkt in das Formular der betroffenen Komponente.

- **Anschaffungsdatum:** ab hier zählt die Investition. Aggregate (JAZ, Wärme, Strom, Ersparnis usw.) ignorieren Monatsdaten **vor** diesem Datum. Nützlich beim Wechsel der Erfassungsmethode (z. B. von WP-eigener Strommessung auf einen Shelly-Zähler): alte Werte bleiben historisch erhalten, verfälschen aber die aktuelle JAZ nicht.
- **Stilllegungsdatum:** Endmarker — ab hier zählt die Investition nicht mehr für aktuelle/künftige Auswertungen; historische Aggregate behalten sie.

### 3.3 Geräte-Detaildaten in der Infothek

Hersteller/Modell/Seriennummer/Garantie, Ansprechpartner und Wartungsvertrag sind **nicht** Teil des Komponenten-Formulars, sondern werden über die [Infothek](HANDBUCH_INFOTHEK.md) gepflegt und N:M mit beliebig vielen Komponenten verknüpft. Beim Bearbeiten einer Komponente werden verknüpfte Infothek-Einträge als kompakte Liste mit Direktlink angezeigt.

### 3.4 Typ-spezifische Parameter

- **PV-Module:** Anzahl Module, Leistung pro Modul (Wp), Ausrichtung (Süd = 0°, Ost = −90°, West = +90°), Neigung (0° flach … 90° senkrecht). Anzahl und Wp sind optional; sind beide gepflegt, vergleicht eedc `Anzahl × Wp` mit der eingetragenen Leistung (kWp) und weist eine Abweichung direkt im Formular aus — der Daten-Checker nennt denselben String dann beim Namen, statt nur die Anlagensumme zu bemängeln.
- **Speicher:** Kapazität (kWh), **nutzbare Kapazität (kWh)**, max. Leistung (kW), arbitrage-fähig (Ja/Nein). Die nutzbare Kapazität ist die Reserve-bereinigte Größe (wer 10/90 fährt, trägt bei 10 kWh brutto 8 kWh ein); sie verfeinert den gemessenen Wirkungsgrad. Vollzyklen und die Wirtschaftlichkeits-Prognose rechnen weiterhin mit der Brutto-Kapazität ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)).
- **E-Auto:** Batteriekapazität (kWh), V2H-fähig, „nutzt V2H aktiv".
- **Wärmepumpe:** **JAZ** (Standardwert, falls kein Wärmemengenzähler), **Alternativkosten** (Gas/Öl als Mehrkosten-Basis), **jährliche Zusatzkosten der Alt-Heizung** (Schornsteinfeger, Wartung, Gaszähler-Grundpreis), **Alt-Tarif Gas/Öl** (ct/kWh, Fallback wenn ein Monat keinen eigenen Gaspreis führt).
- **Wallbox:** max. Ladeleistung (kW), bidirektional.
- **Wechselrichter:** max. Leistung (kW), MaStR-ID.
- **Sonstiges:** Kategorie (Erzeuger / Verbraucher / Speicher) + Beschreibung; die Monatsdaten-Felder passen sich der Kategorie an.

> **Ein Schlüsselsatz für alle Wege:** Setup-Wizard, Komponenten-Formular und das Backend halten dieselben Parameter-Schlüssel. Felder, die du im [Setup-Wizard](HANDBUCH_INSTALLATION.md) erfasst, landen direkt unter den hier dokumentierten Werten.

---

## 4. Infothek & Berichte

### 4.1 Infothek

Die Infothek ist deine anlagengebundene Wissensbasis (Verträge, Datenblätter, Notizen, Links, Vertragspartner). Sie läuft als vollständige Verwaltung **inline im Block** — der große Voll-Blick über die Vollbild-Ansicht (⤢). Details und Kategorien: **[Infothek-Handbuch](HANDBUCH_INFOTHEK.md)**.

### 4.2 Berichte & Dokumente

Die Kachel **Berichte & Dokumente** öffnet den Dokumente-Dialog der Anlage. Er erzeugt anlagengebundene PDFs — einzeln oder als ZIP, mit Jahr-Auswahl:

- **Jahresbericht** (alle KPIs: Energie, Autarkie, Finanzen, CO₂; Diagramme; Monatstabellen; PV-String SOLL/IST).
- **Anlagendokumentation** (Stammdaten, Versorger, Tarif, Komponenten mit Parametern + verknüpften Infothek-Einträgen).
- **Finanzbericht** und **Infothek-Dossier**.

> **HA-Companion:** PDF-, CSV- und Backup-Downloads laufen über `fetch + Blob` — damit funktionieren sie in der iOS-HA-Companion-App ohne 401-/Ingress-Probleme.

---

## 5. Daten

Die Kategorie **Daten** bündelt die laufende Datenpflege einer Anlage.

### 5.1 Monatsdaten & Monatsabschluss

Der Monatsabschluss ist **ein einziges Formular** — kein mehrstufiger Assistent mehr. Die frühere Wizard-Fläche ist stillgelegt; erfasst und abgeschlossen wird über `MonatsdatenForm`.

Der Block zeigt die Tabelle aller erfassten Monate inline (sortierbar, mit Spalten-Toggle nach Gruppen); der große Voll-Blick läuft über die Vollbild-Ansicht des Blocks.

> **„Nächster offener Monat" = der früheste fehlende (R20-2):** Der Block weist dich auf den **frühesten** noch nicht erfassten Monat hin — im Bereich vom Anschaffungs-Monat bis zum Vormonat, **inklusive Binnen-Lücken**. Fehlt z. B. mitten in der Historie ein Monat, springt der Hinweis genau dorthin, nicht auf „letzter Monat + 1". So schließt du Lücken der Reihe nach. *(Die Status-Fußzeile signalisiert lediglich, dass überhaupt ein Monatsabschluss offen ist; die genaue Lücken-Reihenfolge zeigt dieser Block.)*

**Ein Monat erfassen:**

- **„Neuer Monat"** öffnet das Formular. Es zeigt datengetrieben genau die Felder, die zu deinen Komponenten passen (neue Felder erscheinen automatisch, sobald sie zentral definiert sind).
- **Assistenz je Feld:** Statt den gemessenen Wert in den Feldtitel zu schreiben, führt eedc ihn in einer Assistenz-Zone: ein Badge „gemessen / geschätzt (Quelle)", ein Platzhalter „Vorschlag: …" (Durchschnitt / Vorjahresmonat) und, wo eine Datenquelle zugeordnet ist, „Sensor meldet X · gespeichert Y" mit einer Inline-Übernahme. Ein Kopf-Ampel und ein Abschluss-Review rahmen das Formular.
- **Vorschläge sind nach Herkunft gewichtet — und die Zuordnung schlägt die Verteilung.** Ein Wechselrichter-Connector liefert genau **einen** Zählerstand. Hast du dieses Feld einer bestimmten Komponente zugeordnet (Einstellungen → Connector), geht der volle Wert dorthin und heißt „Vom Wechselrichter (Zählerstand-Differenz)" — die anderen Module bekommen aus dieser Quelle keinen Vorschlag mehr, denn der Zähler ist bereits vollständig zugeordnet. **Ohne** Zuordnung wird nach Nennleistung verteilt; der Vorschlag heißt dann ehrlich „Gesamtwert, anteilig nach kWp auf die Strings verteilt" und wird **niedriger gewichtet als jede gemessene Quelle**. Für Speicher gilt dasselbe mit der Kapazität. Bei nur einer Komponente ändert sich nichts. **Vorschläge werden wie immer erst durch Bestätigen übernommen** — nichts wird automatisch geschrieben.
- **Verschachtelte Sektionen:** Die Felder sind in einklappbare Abschnitte je Komponententyp/Gerät gegliedert, jeweils mit einem Rollup-Badge.

**Felder (Auswahl):**

- **Basis (immer):** Jahr, Monat, Einspeisung (kWh), Netzbezug (kWh).
- **Je Komponente (Energie-Daten in kWh):** PV-Erzeugung pro String; Speicher-Ladung/-Entladung/-Netzladung; WP Strom/Heizung/Warmwasser; E-Auto km/Verbrauch/externe Ladung; Wallbox-Ladung; BKW Erzeugung/Eigenverbrauch (Einspeisung wird berechnet).
- **Vergleichspreise (optional):** eine eigene Untergruppe — **Ø Benzinpreis (€/L)** und **Ø Gas-/Ölpreis (ct/kWh)** als Monatsdurchschnitte für die Alternativ-Vergleiche (E-Auto / Wärmepumpe). Sie sind **nicht Teil der kWh-Bilanz** und erscheinen nur, wenn eine E-Auto- oder Wärmepumpe-Komponente vorhanden ist. (Bewusst aus den kWh-Feldern herausgezogen, damit Energie-Werte und Preis-Annahmen nicht vermischt werden.)
- **Sonstige Positionen (G19-1):** frei erfassbare Kosten und Erlöse je Monat (Reparaturen, Wartung, THG-Quote, sonstige Erträge). Sie fließen als eigene Zeilen in die Finanz-Summen ein — siehe [Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen).

> **Heimladung gehört an die Wallbox.** Hast du eine Wallbox angelegt, blendet das E-Auto-Formular die Felder „Heim: PV"/„Heim: Netz" aus — sie werden an der Wallbox erfasst. Ohne Wallbox (Schuko/Steckerlader) bleibt das E-Auto die Quelle. So kann derselbe Stromfluss nicht aus zwei Quellen widersprüchlich gepflegt werden. Hintergrund: [Berechnungen §3.4](BERECHNUNGEN.md#34-e-auto-einsparung).

**Werte aus Home Assistant holen:** Neben „Neuer Monat" gibt es „Aus HA laden". Bei einem **neuen** Monat werden die Werte direkt ins Formular übernommen; bei einem **existierenden** Monat zeigt ein Vergleichs-Modal die Unterschiede (Vorhanden / HA-Statistik / Diff, farbkodiert ab 10 %) mit „HA-Werte übernehmen" oder „Abbrechen". Bei E-Auto- bzw. WP-Komponenten schlägt eedc den Ø Benzin- bzw. Gaspreis vor.

**Wetter-Autofill:** „Wetter abrufen" füllt Globalstrahlung und Sonnenstunden (Open-Meteo historisch bzw. PVGIS TMY).

**Kraftstoffpreis-Backfill (Monats):** Unten im Block, sichtbar nur bei offenen Monaten. Befüllt rückwirkend den Benzinpreis aus dem EU Weekly Oil Bulletin (History seit 2005). Service-Fehler (z. B. Bulletin-URL-Wechsel) erscheinen als roter Alert, nicht stillschweigend.

### 5.2 Energieprofil-Pflege

Diese Kachel enthält **nur die Pflege-Funktionen** des Energieprofils; die **Anzeige** (Tagesdetail, Monatsanalysen, Prognose) ist in die Cockpit-Achsen umgezogen (siehe [Teil II](HANDBUCH_BEDIENUNG.md#2-cockpit--die-zeit-achse)).

- **Datenbestand-Kacheln** je Anlage: Stundenwerte, Tagessummen, Monatswerte (Anzahl + Zeitraum) und Abdeckung in %.
- **„Lücken aus HA-LTS nachfüllen" (Vollbackfill):** liest historische Snapshots aus HA und ergänzt **nur fehlende** Tage. **Bestehende Tage bleiben unverändert** — es gibt bewusst keinen Overwrite-Modus. Sinnvoll nach Erstinstallation, längerem Stillstand oder einer Datenquellen-Änderung.
- **„Kraftstoffpreise nachpflegen":** trägt fehlende Benzin-/Dieselpreise (EU Weekly Oil Bulletin) für die E-Auto-Ersparnis nach; strikt additiv, mehrfach gefahrlos.
- **Energieprofil-Daten löschen:** anlage-spezifisch (Monatsdaten bleiben erhalten; der Scheduler baut die Tage danach neu auf).
- **Reparatur-Werkbank:** die gezielten Neuberechnungs-Operationen — **„Tag neu aggregieren"** (mit Alt/Neu-Vorschau), **„Mehrere Tage neu aggregieren"** (Datumsbereich, max. 31 Tage, Tag für Tag festgeschrieben) — der punktuelle Reparatur-Pfad, der fehlende Snapshots nachholt. Bewusst **kein** globaler „Heiler-Knopf".

> **Tipp:** Steht im CHANGELOG eines Updates „Empfohlene Aktion: betroffene Tage neu aggregieren", nutze dafür **„Mehrere Tage neu aggregieren"** über den betroffenen Zeitraum (in Schüben zu je max. 31 Tagen). Das Nachfüllen aus HA-LTS überschreibt bestehende Tage nicht — es füllt nur echte Lücken.

### 5.3 Daten-Checker

Der Daten-Checker prüft die Qualität deiner Daten in mehreren Kategorien — von Stammdaten und Strompreisen über Plausibilität der Monatsdaten bis zu Datenquellen-Konsistenz und HA-Long-Term-Statistics-Verfügbarkeit der zugeordneten Sensoren. Pro Befund gibt es Severity (❌ ERROR / ⚠️ WARNING / ℹ️ INFO / ✅ OK), erklärenden Text und einen „Beheben"-Link zur betroffenen Stelle. Der Prüf-Lauf und die Reparatur-Werkbank laufen inline im Block.

> **Vollständige Doku** mit allen Kategorien, Befund-Tabellen und Behebungs-Workflows: **[Daten-Checker-Handbuch](HANDBUCH_DATEN_CHECKER.md)**.

### 5.4 Ersteinrichtung

Ein geführter Assistent, der Anlage, Datenquellen und Strompreise in einem Durchlauf abfragt — die **Pflege-Route** für später. Sie ist getrennt vom **First-Run-Setup-Wizard**, der einmalig vor der App läuft (in v4-Optik) und in [Teil I: Installation](HANDBUCH_INSTALLATION.md) beschrieben ist.

---

## 6. Integration

Die Kategorie **Integration** regelt, **wie** eedc mit der Außenwelt spricht: die Verbindungen (MQTT-Broker, Home Assistant), der Export von Kennzahlen und die Import-Wege. **Welche** Quelle dann ein einzelnes Feld speist, legst du danach unter [Datenquellen](#7-datenquellen--feld-zentrische-zuordnung) fest.

> **Verbindung ≠ Feld-Zuordnung.** Bewusst getrennt: hier richtest du **einmal** die Verbindung ein (Broker-Zugangsdaten, HA-Token), dort ordnest du **pro Feld** die konkrete Quelle zu.

### 6.1 MQTT-Broker-Verbindung

**Ein** Broker für alle Richtungen — Inbound-Empfang, Gateway und Export nutzen dieselbe Verbindung.

- **Zugangsdaten** (Host, Port, Benutzer, Passwort) sind richtungs-neutral und immer sichtbar — der Export braucht sie auch, wenn der Import aus ist.
- **„Daten über MQTT empfangen (Import)":** Dieser Schalter steuert die **Import-Richtung**. Ist er **an**, stehen MQTT-Topics in den Datenquellen als Feld-Quelle zur Verfügung. Ist er **aus**, bietet die Datenquellen-Fläche keine MQTT-Quellen an — der Export über dieselbe Verbindung bleibt davon unberührt.
- **„Verbindung testen"** prüft die Erreichbarkeit; **„Speichern & Verbinden"** startet den Subscriber. Der Block-Kopf trägt ein Status-Badge (verbunden / Nachrichten empfangen).

### 6.2 HA-Verbindung

Der zweite Verbindungs-Block — die Voraussetzung dafür, dass HA-Sensoren als Datenquelle wählbar sind.

- **eedc als HA-Add-on (Supervisor):** Die Verbindung läuft automatisch über den Supervisor; der Block zeigt nur den Status „Verbunden über die Home-Assistant-Integration". Keine weitere Eingabe nötig.
- **eedc Standalone (ohne HA-Add-on):** Hier trägst du eine entfernte HA-Installation ein — **Basis-URL** + **Long-Lived-Token** (aus dem HA-Benutzerprofil → Sicherheit → Langlebiger Zugriffstoken), dann „Verbindung testen" und „Speichern".

> **Standalone-Hinweis:** Die Remote-Verbindung lässt sich hier bereits einrichten und testen. HA-Sensoren im Standalone tatsächlich als laufende Datenquelle zu nutzen, folgt in einem späteren Schritt.

> **Nebeneffekt sichtbar gemacht:** Aktivierst du die HA-Verbindung, stellt eedc den MQTT-**Import** auf den Default (aus) — die Zuordnung läuft dann über HA-Sensoren, MQTT bleibt für den Export aktiv. Ein Hinweis nennt das ausdrücklich (kein stiller Nebeneffekt), inklusive Warnung, falls Geräte-Connectoren ihre Werte noch über MQTT liefern.

### 6.3 MQTT-Export

eedc exportiert berechnete Kennzahlen an einen Broker (HA-Discovery-Konvention). Der Export nutzt den gemeinsamen Broker aus §6.1 — damit kann auch eine Standalone-Instanz ihre Sensoren an einen beliebigen Broker publizieren.

- **Auto-Discovery:** Für jedes über eine Datenquelle mit HA-Sensor bequellte Feld erzeugt eedc zwei Entities: eine `number.eedc_…_start` (Zählerstand vom Monatsanfang) und einen `sensor.eedc_…_monat` (berechneter Monatswert = aktueller Stand − Startwert). Die Friendly Names tragen den Komponentennamen zur besseren Lesbarkeit.
- **KPI-Export:** zusätzlich exportiert eedc Kennzahlen-Gruppen (Energie & Quoten, Finanzen & Investition, spezifischer Ertrag [aufs Jahr normiert], PV-Prognose, Börsenpreis-Trigger). Die vollständige Liste mit Bedeutung und Einheiten steht in der **[Sensor-Referenz](SENSOR-REFERENZ.md)**.
- **Günstig-Schwelle:** Eine Stunde gilt als „günstig", wenn sie zu den 5 billigsten ihres Tag-/Nacht-Fensters gehört **und** ihr Börsenpreis mindestens den eingestellten Prozentsatz unter dem Tagesschnitt (ohne die 3 teuersten Stunden) liegt. Der Prozentsatz ist je Anlage einstellbar (0–50 %, Standard 10 %). **0 % schaltet die Schwelle ab** — dann zählen wieder allein die 5 günstigsten Stunden je Fenster, unabhängig vom Preisabstand. eedc liefert nur diese Trigger-Werte — die Lade-/Entlade-Strategie baust du in deinen HA-Automationen.
- **Alternative REST-API:** Statt MQTT kannst du die Sensoren auch per REST-Sensor aus `…/api/ha/export/sensors/{id}` in HA ziehen (YAML-Beispiel im Block).

> **Zu viele Entitäten?** Nicht benötigte Sensoren in HA deaktivieren — oder per `recorder:`-`exclude` nur von der Aufzeichnung ausnehmen (aktuelle Werte bleiben sichtbar, keine DB-Historie).

**Startwerte:** Damit die Monatswert-Berechnung stimmt, müssen einmalig die Zählerstände vom Monatsanfang als Startwerte gesetzt sein — entweder aus der HA-Statistik geladen oder direkt an den `number.eedc_…_start`-Entities in Home Assistant. Erscheinen Entities doppelt (`_2`-Suffix), lösche die alten Discovery-Topics unter `homeassistant/number/eedc_…` bzw. `homeassistant/sensor/eedc_…` (z. B. per MQTT Explorer) und speichere den Export erneut.

### 6.4 Statistik-Import

*(Nur mit Home-Assistant-Integration.)* Importiert **alle historischen Monatsdaten seit Anlagen-Installation** aus der HA-Langzeitstatistik — nützlich bei Neuinstallation, zum Nachbefüllen oder beim Umstieg von manueller auf automatische Erfassung.

**Ablauf (Assistent):** Quelle/Anlage wählen → Zeitraum festlegen → Vorschau laden → Monate auswählen → importieren. Die Vorschau markiert je Monat:

- **Grün** — neuer Monat (standardmäßig ausgewählt).
- **Grau** — bereits ausgefüllt (nicht ausgewählt).
- **Amber** — Konflikt: HA-Werte weichen ab (nicht ausgewählt).

Jeder Monat ist einzeln per Checkbox wählbar — so bleiben manuell erfasste Daten geschützt.

> **Voraussetzungen:** zugeordnete HA-Sensoren (siehe [Datenquellen](#7-datenquellen--feld-zentrische-zuordnung)), Sensoren in der HA-Langzeitstatistik, Volume-Mapping `config:ro`. Unterstützt SQLite **und** MariaDB/MySQL als Recorder-Backend (automatische Erkennung). Bei Tagesreset-Zählern nutzt eedc `MAX(sum) − MIN(sum)` aus HA-Statistics (reset-bereinigt).

### 6.5 Import-Assistenten

Ein Sammel-Einstieg für die einmaligen und wiederkehrenden Importe. Jeder Assistent öffnet als **Overlay** (keine eigene Seite mehr):

- **Portal-Import** und **Cloud-Import** (Hersteller-Cloud-APIs: SolarEdge, Fronius SolarWeb, Huawei FusionSolar, Growatt, Deye/Solarman, EcoFlow, Anker …). Ablauf: Verbinden → Zeitraum → Vorschau → Import; Credentials pro Anlage speicherbar.
- **Geräte-Connector** — direkter Abruf lokaler/Cloud-Geräte; kann seine Werte optional als MQTT-Bridge auf eedc-Topics publishen.
- **Eigene Datei / Vorlage (Custom-Import)** — beliebige CSV/JSON mit Spalten-Mapping (Auto-Detect, Einheiten Wh/kWh/MWh, Dezimalzeichen, Datumsspalte, speicherbare Mapping-Vorlagen).
- **CSV-Import** — eedc-Template mit dynamischen Komponenten-Spalten; Plausibilitätsprüfung (negative Werte, Legacy-Spalten-Mismatch = Abbruch; redundante Legacy-Spalten / unplausible Wetterwerte = Warnung). Duplikate werden überschrieben.

> **Der Schritt „Zuordnung" verteilt nach Nennleistung.** Hast du mehrere PV-Modulfelder (oder mehrere Speicher, Wallboxen, E-Autos), fragt der Assistent, wie die importierten Monatswerte auf die Komponenten aufzuteilen sind. Die Vorauswahl ist **proportional zur Nennleistung** (bei Speichern zur Kapazität) — bei 12 kWp Süddach + 3 kWp Garage also 80/20. Bis v4.0.0 war die Vorauswahl **immer** eine Gleichverteilung, weil der Wizard die Nennleistung unter einem Namen suchte, den eedc gar nicht kennt; die kWp-Spalte blieb dabei leer. **Wer vorher importiert und den Vorschlag übernommen hat, sollte die Aufteilung prüfen** (Komponenten → PV-Modul → Monatswerte); ein erneuter Import mit korrigierten Anteilen überschreibt die Werte. Ist die Bezugsgröße tatsächlich nirgends gepflegt, verteilt der Assistent weiterhin gleichmäßig — sagt aber dazu, dass das **keine** proportionale Aufteilung ist.

> **Ganze Anlage sichern/wiederherstellen:** Der JSON-Export/-Import ganzer Anlagen läuft über den Backup-Block (siehe [§8.3](#83-backup)), nicht über die Import-Assistenten.

---

## 7. Datenquellen — feld-zentrische Zuordnung

Die Kategorie **Datenquellen** ist die zentrale, neue Fläche für die Frage: **Woher kommt der Wert jedes eedc-Feldes?** Sie löst die früheren getrennten Assistenten „Sensor-Zuordnung" und „MQTT-Inbound/-Gateway" ab und führt HA-Sensoren, MQTT-Topics und Geräte-Connectoren an **einer** Stelle zusammen.

### 7.1 Prinzip: ein Feld — eine Quelle

Jedes eedc-Feld (Energie- wie Live-Feld) bezieht seinen Wert aus **genau einer** Quelle — kein Vermischen mehrerer Quellen zur Laufzeit. Wählbar sind:

| Quelle | Bedeutung |
|--------|-----------|
| **HA-Sensor** | eine Home-Assistant-Entity (über Supervisor **oder** Remote-Verbindung — transparent) |
| **MQTT-Gateway** | ein beliebiges Fremd-Topic deines Brokers, das eedc übersetzt (Transform) |
| **MQTT-Inbound** | das kanonische eedc-Standard-Topic (`eedc/…`), auf das du selbst publishst |
| **Keine** | bewusst keine Quelle — das Feld wird manuell bzw. über die Vorschläge (Durchschnitt / Vorjahresmonat) im Monatsabschluss gefüllt |

**Präferenz beim Vorschlag** (nur als Default, nicht als Laufzeit-Kette): HA-Sensor → MQTT-Gateway → MQTT-Inbound → manuell. **Kontextabhängig:**

- **eedc als HA-Add-on:** HA-Sensoren haben Vorrang; MQTT deckt die Felder ohne HA-Sensor.
- **Standalone mit Remote-HA:** HA-Sensor gleichrangig zu MQTT — du wählst bewusst (HA hat den Recovery-Vorteil, s. u.).
- **Standalone ohne HA:** nur MQTT / manuell.

> **Kein stiller Wechsel.** Fällt die zugeordnete Quelle aus, schaltet eedc **nicht** heimlich auf eine andere um. Stattdessen wird der Ausfall sichtbar (amber Wert + Daten-Checker-Eintrag). Was eine HA-Quelle an heutigen Stunden verpasst hat, holt die untertägige Selbstheilung später nach — was MQTT verpasst, ist weg (MQTT kann nicht rückwirkend liefern).

### 7.2 Die Fläche

Die Zuordnung spiegelt die Struktur von **Einstellungen → Komponenten**:

- **Ein Block je Investitionstyp** (mit den farbigen Typ-Icons und einer Zusammenfassung wie „3 Geräte · 2 Felder ohne Quelle"), dazu ganz oben ein Zusatz-Block **„Anlage / Zähler"** für die Basis-Felder (Einspeisung, Netzbezug, Wetter).
- Darunter je Gerät eine einklappbare Sektion mit einem Rollup-Badge (Felder mit / ohne Quelle).
- Die Felder je Gerät sind in drei Abschnitte nach Einheit gegliedert: **Energie-Sensoren (kWh)**, **Leistung-Sensoren (W)**, **Sonstige Sensoren** (SoC in %, Temperatur, km, €, Ladevorgänge). Leere Abschnitte entfallen.

**Jede Feld-Zeile** zeigt: Feldname (+ Einheit), die **aktive Zuordnung** — mit dem **Klarnamen** des Sensors neben der Entity-ID —, den zuletzt **empfangenen Wert** und rechts die Quellen-Wahl. Ein Info-Symbol blendet den Feld-Hinweis aus der Registry ein.

**Quellen-Wahl (Buttons):** Je Feld ist immer genau eine Quelle aktiv (gefüllter Button):

- **HA-Sensor**, **Gateway**, **Inbound** — erscheinen nur, wenn die zugehörige Verbindung besteht (ohne HA-Verbindung kein HA-Button; ohne MQTT-Broker keine Gateway-/Inbound-Buttons). Eine bestehende Zuordnung bleibt sichtbar, auch wenn die Verbindung gerade fehlt.
- **Keine** — der **einzige** Weg, eine Zuordnung wieder zu entfernen.

> **Ein Klick auf die aktive Quelle löscht sie nicht.** Er öffnet die Zuordnung — den Picker mit dem bereits hinterlegten Sensor als Vorauswahl. Bis v4.0.0 bedeutete derselbe Knopf zweierlei (bei inaktiver Quelle „auswählen", bei aktiver „Zuordnung verwerfen", ohne Rückfrage); wer nur nachsehen wollte, welcher Sensor hinterlegt ist, verlor ihn. Entfernt wird ausschließlich über **Keine**.

**Wert-Anzeige:** Ein zugeordnetes Feld ohne empfangenen Wert wird **amber** markiert (Zuordnung + Wert) — so ist ein Quellen-Ausfall sofort sichtbar. Ein grüner Wert bedeutet: Quelle liefert.

**Vorzeichen umkehren (±):** Bei signierten Leistungs-Feldern (W) gibt es ein ±-Symbol direkt am Wert. Manche Sensoren liefern z. B. Einspeisung als negativen Wert — der Schalter kehrt das Vorzeichen um. Er ist **quellen-unabhängig** (sitzt am Wert, gilt für jede Quelle); eedc rechnet intern immer mit positiven Werten.

> **Mobil:** Statt einer Tabelle erscheint pro Feld eine Karte (Feldname + Wert, darunter die Zuordnung, darunter die Quellen als Chip-Reihe).

### 7.3 Eine HA-Entity zuordnen (Picker)

Klick auf **HA-Sensor** öffnet einen Picker mit allen Entities der aktiven HA-Verbindung — durchsuchbar nach Entity-ID oder Name; jede Zeile zeigt Einheit und aktuellen State. Der Picker assistiert beim Wählen:

- **Einheiten-Warnung:** Passt die Sensor-Einheit nicht zur erwarteten Feld-Dimension (z. B. ein kWh-Zähler für ein W-Feld), erscheint ein amber Hinweis an der Zeile — Warnung, keine Sperre.
- **Filter „Nur passende Einheit" (Forum-Wunsch fridolin22):** eine Checkbox über der Liste blendet Sensoren mit abweichender Einheit aus und nennt deren Anzahl. **Standardmäßig aus** — wer keinen passenden Sensor besitzt, soll die vorhandenen sehen und daraus in Home Assistant einen Helfer bauen können. Sensoren **ohne** Einheitsangabe bleiben immer sichtbar.
- **Integrations-Vorschläge (Zuordnungs-Assistenz, #343):** Erkennt eedc eine bekannte Integration (Muster-Match auf die Entity-Liste), erscheint über der Suchliste ein Abschnitt „Vorschläge — Integration erkannt: …" mit den passenden Entities und einem Hinweis-Text, welcher Sensor der richtige ist. Die Vorschläge sind reine **Assistenz** — die Auswahl trifft immer du; die volle Suchliste bleibt sichtbar. Bekannte Fehlgriffe (z. B. ein Zähler, der erst am Session-Ende springt) werden als amber Warnhinweis in der Liste markiert.
- **Takt-Check bei kWh-Zählern:** Wählst du einen Energie-Zähler, prüft eedc einmalig dessen jüngsten Verlauf. Ein Zähler, der sich nur sprunghaft aktualisiert (z. B. erst am Ladeende), erzeugt in Tages-/Live-Kurven Nadeln — eedc warnt dann („Für Monatssummen ok") mit **„Trotzdem übernehmen"** oder „Anderen wählen". Ist HA nicht erreichbar oder gibt es keinen numerischen Verlauf, wird der Check stillschweigend übersprungen (keine Pseudo-Bestätigung).

> **Wissensbasis wächst kuratiert.** Die Integrations-Vorschläge starten bewusst klein (evcc mit belegten Feld-Mustern; go-eCharger/openWB/Keba/Zappi als Erkennung) und werden mit Tester-Wissen erweitert — nichts wird geraten.

### 7.4 Ein MQTT-Topic zuordnen

- **Gateway (Fremd-Topic):** Klick auf **Gateway** öffnet den Topic-Picker mit einer **Broker-Discovery** (`#`-Scan mit Suche) — du wählst ein vorhandenes Topic deines Geräts (Shelly, OpenDTU, Tasmota …), gibst bei JSON-Payloads den Pfad an und optional Faktor/Einheit. eedc übersetzt das auf sein Feld.
- **Inbound (Standard-Topic):** Klick auf **Inbound** setzt direkt das kanonische eedc-Topic (`eedc/{anlage}/…`), auf das du selbst aus deinem Smarthome (HA-Automation, Node-RED, ioBroker, FHEM, openHAB) publishst. Live-Topics speisen das Live-Dashboard, Energy-Topics (monoton steigende Zählerstände) den Monatsabschluss.

> **Topic-Drift:** Kommen in eedc Felder dazu oder wechseln Komponenten-IDs nach einem Re-Import, kann ein statischer Publisher gegen die erwarteten Topics driften. Der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) meldet das in der Kategorie MQTT-Topic-Abdeckung.

### 7.5 Validierung & Probleme je Feld

Zur Zuordnungszeit erkennbare Fehler zeigt eedc **direkt an der Feld-Zeile** — diagnostisch, nie blockierend (rot = Fehler, amber = Warnung):

- **Einheiten-Mismatch** — der zugeordnete HA-Sensor hat eine andere Dimension als das Feld (kWh-Sensor in W-Feld). Nur bei HA-Feldern prüfbar (MQTT-Topics tragen keine Einheit-Metadaten).
- **Kein `state_class` / keine Langzeitstatistik** — der HA-Sensor liefert für kWh-Felder still keine History (keine Zeitmaschine). Für reine Live-/Counter-Felder unproblematisch.
- **Aggregat-Redundanz** — ist ein Gesamt-Sensor (z. B. „PV gesamt") **und** ≥ 1 Einzelkomponente zugeordnet, ist die Gesamt-Zuordnung wirkungslos (die Engine nutzt die Einzelwerte). Ein amber Hinweis bietet inline **„auf keine setzen"** an — kein automatischer Eingriff.
- **Sensor-Doppelmapping** — dieselbe HA-Entity in zwei Feldern → Doppelzählungs-Gefahr; beide betroffenen Felder werden benannt.

Die datenbasierten (rückblickenden) Prüfungen — Über-Erfassung, Datenquellen-Drift, Vorzeichen-Historie — bleiben im [Daten-Checker](HANDBUCH_DATEN_CHECKER.md).

### 7.6 Voraussetzung: die Verbindungen

Damit HA-Sensoren bzw. MQTT-Topics überhaupt wählbar sind, muss die jeweilige Verbindung stehen — MQTT-Broker und HA-Verbindung richtest du unter [Integration](#6-integration) ein. Änderst du dort etwas, blenden sich die Quellen-Buttons in der Datenquellen-Fläche sofort passend ein oder aus.

### 7.7 Was aus den alten Assistenten wurde

| Früher | Jetzt |
|--------|-------|
| **Sensor-Mapping-Wizard** | in dieser Fläche aufgegangen — HA-Sensor je Feld |
| **MQTT-Inbound-Wizard** | Verbindung → [Integration → MQTT-Broker](#61-mqtt-broker-verbindung); Feld-Zuordnung → hier (Inbound/Gateway) |
| **MQTT-Gateway** (Topic-Mapping) | die „Gateway"-Quelle je Feld (Fremd-Topic mit Transform) |

Bestehende Zuordnungen wurden **verlustfrei** übernommen (HA-first: hatte ein Feld einen HA-Sensor, wurde HA die Quelle; ein etwaiges paralleles MQTT-Mapping wurde nur deaktiviert, nicht gelöscht).

---

## 8. System

### 8.1 Allgemein

- **Theme** — Hell / Dunkel / System.
- **HA-Integration-Status**, **Datenbank-Info** (Anzahl Datensätze, Pfad, Größe), **Version + API-Status**.

### 8.2 Demo-Daten

Zum Ausprobieren ohne echte Daten: generiert eine „Demo-Anlage" mit realistischen Beispieldaten über alle Komponenten-Typen und lässt sie jederzeit wieder löschen.

### 8.3 Backup

Vollständiger **JSON-Export** einer Anlage und **Drag-&-Drop-Restore** — inline im Block (kein separater Assistent):

- **Enthalten:** Anlage-Stammdaten (inkl. MaStR-ID, Versorger), Datenquellen-Zuordnungen, alle Komponenten mit Monatsdaten, Strompreise, PVGIS-Prognosen, Monatsdaten inkl. Wetter und sonstige Positionen.
- **Restore:** optional „Überschreiben" (sonst wird bei gleichem Namen ein Suffix ergänzt).

> **Nach dem Restore:** Komponenten-IDs ändern sich beim Import — prüfe die Datenquellen-Zuordnungen (und den MQTT-Export) und speichere sie bei Bedarf erneut. Die MQTT-Topic-Abdeckung im [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) zeigt sofort, ob deine Publisher noch zu den Topic-Pfaden passen.

### 8.4 Protokolle

Das zentrale Werkzeug zur Fehlersuche — zwei Tabs, Debug-Umschalter und Neustart im Kopf.

- **System-Logs:** Echtzeit-Logviewer (Ring-Puffer, max. 500 Einträge, gehen beim Neustart verloren). Filter nach Level (DEBUG/INFO/WARNING/ERROR), Modul und Freitext; Copy (als Markdown-Tabelle für GitHub-Issues) und Download (.txt).
- **Aktivitäten:** persistentes Protokoll in der DB (überlebt Neustarts, Bereinigung nach 90 Tagen / max. 1000 Einträge). Filter nach Kategorie (Connector, Cloud-/Portal-Import, Backup, Monatsabschluss, HA-Statistiken, Scheduler-Jobs, MQTT, Community, Datenquellen, HA-Export …), Status und Freitext.
- **Debug** (Käfer): schaltet den Log-Level auf DEBUG (danach wieder aus — erhöhter Speicherverbrauch), kein Neustart nötig. **Neustart** (Pfeil): über Supervisor-API (Add-on) bzw. Container-Restart (Standalone), mit Bestätigung.

**Support-Workflow:** Debug an → Problem reproduzieren → System-Logs (Level WARNING, Modul-Filter) → Aktivitäten prüfen → Logs kopieren → in Issue einfügen → Debug wieder aus.

---

## 9. Hintergrund: Energieprofile & Snapshot-Architektur

> Dieser Abschnitt erklärt, **wie eedc die Stunden-/Tages-/Monatswerte erhebt und verdichtet** — als Hintergrund zu den Anzeigen im Cockpit und zur Energieprofil-Pflege ([§5.2](#52-energieprofil-pflege)). Er ist fachlich und ändert sich mit der neuen Oberfläche nicht.

eedc sammelt automatisch stündliche Energiedaten und verdichtet sie zu Tages- und Monatswerten.

### 9.1 Snapshot-basierte Erhebung

Stunden-kWh kommen nicht aus der Integration von Leistungs-Samples, sondern aus **kumulativen Zähler-Snapshots**:

1. **Stündlicher Snapshot-Job** (Cron `:05`) schreibt pro Anlage und zugeordnetem kWh-Sensor den aktuellen Zählerstand in die Tabelle `sensor_snapshots`. Quellen: HA-Long-Term-Statistics (Add-on) oder MQTT-Energy-Snapshots (Standalone).
2. **`:55`-Live-Preview:** zum Stundenende wird zusätzlich ein Live-Snapshot geschrieben — die laufende Stunde ist damit sofort sichtbar.
3. **Tageszusammenfassung** (00:15 für den Vortag): aus den 25 Snapshot-Werten (h = −1..23) werden 24 Stunden-Differenzen gebildet. Snapshot-Lücken werden **linear zwischen Nachbarstunden interpoliert**; die Tagessumme bleibt in jedem Fall korrekt (letzter − erster Snapshot).
4. **Laufender Tag rollierend** (alle 15 Min): abgeschlossene Stunden des heutigen Tags werden fortlaufend nachgezogen.
5. **Monats-Rollup** beim Monatsabschluss (mit rückwirkender Nachberechnung, falls Lücken bestehen).

### 9.2 Backward-Slot-Konvention

Slot N enthält die Energie aus dem Intervall **[N−1, N)** — „die letzte Stunde". Industriestandard, konsistent mit HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber. Strompreis-Stunden bleiben Forward (`[N, N+1)`, „gilt ab jetzt").

### 9.3 Strikte NULL-Semantik

Ist für ein Feld **keine** kumulative Zähler-Quelle zugeordnet, bleiben die betroffenen Stunden-Felder `NULL` — statt aus Leistungs-Samples geschätzt zu werden. Im Frontend erscheint ein ⚠-Badge neben IST-Werten bei Datenlücken; ein Klick öffnet den Reparatur-Pfad (siehe [§5.2](#52-energieprofil-pflege)).

### 9.4 Selbstheilung & Sonderfälle

- **Restart-Recovery:** Wird das Add-on zwischen `:55` und `:05` neu gestartet, holt eine Startup-Recovery die Snapshots der letzten Stunden idempotent aus HA-Statistics nach und aggregiert den heutigen Tag sofort neu.
- **Tagesreset-Zähler:** HA-`utility_meter` mit täglichem Reset („Erzeugung heute") würden um Mitternacht ein stark negatives Delta werfen; eedc erkennt das Muster und nimmt `max(0, Wert)` als Nachtwert.
- **WP-Kompressor-Starts:** optional pro Wärmepumpe über einen Total-Increasing-Zähler; Counter-Felder sind strikt von kWh-Feldern getrennt, damit reine Zähler nicht in die Energiebilanz fließen.

### 9.5 Warum eedc überhaupt speichert

Die HA-History hat nur ~10 Tage Retention. eedc sichert die verdichteten Werte dauerhaft — so bleiben langfristige Analysen (Jahresvergleiche, Speicher-Dimensionierung) möglich, auch wenn HA die Rohdaten längst verworfen hat.

### 9.6 Felder & Vorzeichen

Zur Deutung der Stunden-/Tageswerte:

- **PV** — Summe aller lokalen Erzeuger (PV-Module, Balkonkraftwerk).
- **Verbrauch** — Gesamtverbrauch (Haushalt + Wärmepumpe + Wallbox + …).
- **Bezug / Einspeisung** — Netto-Austausch mit dem Stromnetz.
- **Batterie** — positiv = Entladung (Quelle), negativ = Ladung (Senke).
- **Überschuss** = max(0, PV − Verbrauch) je Stunde; **Defizit** = max(0, Verbrauch − PV) je Stunde.
- **SoC** — Batterie-Ladestand als Stundenmittel.

> **Summenregel:** kW-Felder über einen Tag aufsummiert ergeben kWh/Tag (1 Stundenwert × 1 h = kWh). SoC, Temperatur und Strahlung werden **nicht** summiert (sie sind Mittel-/Momentanwerte).

### 9.7 Kraftstoffpreise (EU Weekly Oil Bulletin)

Für die E-Auto-Ersparnis nutzt eedc echte monatliche Benzinpreise aus dem EU Weekly Oil Bulletin (History seit 2005). Der Backfill (Tages-/Monatsebene, siehe [§5.1](#51-monatsdaten--monatsabschluss)/[§5.2](#52-energieprofil-pflege)) setzt nur Werte, wo noch keiner vorhanden ist, und kann gefahrlos mehrfach laufen; ein Scheduler-Job (Dienstag 06:00) befüllt neue Tage automatisch.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
