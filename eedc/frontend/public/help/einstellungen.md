
# eedc Handbuch — Teil III: Einstellungen

**Version 4.0** | Stand: 2026-07-25

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Infothek](HANDBUCH_INFOTHEK.md) | [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md) | [Sensor-Referenz](SENSOR-REFERENZ.md) | [Glossar](GLOSSAR.md)

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

- **auto** (Standard): eedc wählt automatisch (Bright Sky für DE, sonst Open-Meteo best_match). Maßgeblich ist dabei das **Land** aus den Stammdaten — bis zur Korrektur von [#386](https://github.com/supernova1963/eedc-homeassistant/issues/386) entschied allein ein Koordinaten-Rechteck, das halb Österreich und die Nordostschweiz mit einschloss (siehe [§2.1a](#21a-eedc-außerhalb-deutschlands)).
- **MeteoSwiss ICON-CH2** (2 km, empfohlen für alpine Standorte), **ICON-D2** (2,2 km, DWD/DE), **ICON-EU** (mittlere Auflösung), **ECMWF IFS** (global, 0,25°).

Bei fester Modellwahl versucht eedc zuerst das gewählte Modell und fällt bei fehlenden Daten auf den besten verfügbaren Anbieter zurück (Kaskade). Die verwendete Quelle wird pro Tag in der [Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) mit einem Kürzel (MS/D2/EU/EC/BM) angezeigt.

> **Seit v4.0.2 wirkt die Modellwahl auf *alle* Prognose-Sichten** — auch auf die eedc-Tagesprognose, die Stundenprofile und die Prognose-Sensoren in Home Assistant. Bis dahin rechneten diese unabhängig von der Einstellung mit `auto`. Wer ein anderes Modell gewählt hat, sieht dort einmalig andere Zahlen.
>
> **Nicht mehr verfügbar (Stand Juli 2026):** Für **ECMWF Seamless**, **MeteoSwiss Seamless** und **ECMWF IFS (9 km)** liefert Open-Meteo keine Strahlungsdaten mehr. eedc erkennt das und rechnet für diese Anlagen mit `auto` weiter — die Prognose bleibt vollständig, die Modellwahl greift aber nicht. Empfehlung: **ICON Seamless** (Deutschland) bzw. **MeteoSwiss ICON-CH2** (Alpenraum).

**PV-Prognose-Quelle für diese Anlage:** Hier wählst du, mit welcher Prognose eedc arbeitet — **eedc-optimiert** (Open-Meteo mit anlagenspezifischem Lernfaktor, Standard; funktioniert auch ohne Home Assistant), **Solcast** (pur, ohne eedc-Korrektur) oder **Solar Forecast ML** (pur). Die beiden letzten lesen ihre Werte aus Home Assistant und setzen deshalb eine **verbundene** Instanz voraus — als Add-on oder über einen langlebigen Zugriffstoken; Solcast geht daneben auch über einen eigenen API-Token. Ist die gewählte Quelle nicht erreichbar, rechnet eedc mit seiner eigenen Prognose weiter und sagt es. SFML geht bewusst nicht ins Genauigkeits-Ranking ein ([Prognosen §2.5](HANDBUCH_PROGNOSEN.md#25-sfml-solar-forecast-ml--sichtbar-aber-bewusst-nicht-bewertet)).

**Steuerliche Behandlung:**

- **Keine USt-Auswirkung** (Standard): für Anlagen ab 2023 mit Nullsteuersatz (≤ 30 kWp) oder Kleinunternehmer.
- **Regelbesteuerung**: USt auf Eigenverbrauch wird als Kostenfaktor berechnet (Pre-2023, > 30 kWp, AT/CH). Der USt-Satz ist editierbar (DE 19 %, AT 20 %, CH 8,1 %) und passt sich bei Land-Wechsel automatisch an.

### 2.1b Einstellungen mit einer PIN schützen

**Standardmäßig aus.** Wer sie nicht einschaltet, merkt von diesem Abschnitt nichts.

Die Sperre ist für Haushalte gedacht, in denen mehrere Personen auf eedc schauen: Familie und Besucher sollen die Auswertungen ansehen können, aber nichts verstellen. Du findest sie unter *Einstellungen → Anlage*, unterhalb der Anlagen-Tabelle.

**Was sie tut:** Ist eine PIN gesetzt, wird sie **einmal je Browser-Sitzung** abgefragt, sobald du etwas ändern willst. Das gilt für alles Schreibende — Stammdaten, Strompreise, Monatsabschluss, Import, Reparaturen. **Ansehen ist nie gesperrt**, und auch die Umschaltung zwischen heller und dunkler Darstellung bleibt immer frei.

**Was sie nicht ist:** kein Benutzerkonto, keine Rollen, kein Login. eedc weiß nicht, wer davorsitzt — es gibt genau einen Schlüssel. Das Wort „PIN" ist bewusst gewählt: eine Hürde gegen versehentliches oder neugieriges Verstellen, keine Absicherung gegen jemanden, der es darauf anlegt.

**Sie gilt für die ganze eedc-Installation**, nicht nur für die Anlage, in deren Stammdaten du sie einschaltest. Wer mehrere Anlagen führt, hat trotzdem nur eine PIN.

> **PIN vergessen?** Der Rückweg verlangt Zugriff auf die Maschine — absichtlich, denn eine Adresse, die jeder aufrufen kann, wäre keine Sperre.
>
> - **Home-Assistant-App:** Add-on-Konfiguration öffnen, `einstellungen_pin_zuruecksetzen` auf `true`, Add-on neu starten, Option wieder auf `false`.
> - **Standalone:** Container mit `EEDC_PIN_RESET=1` starten.

**Zusammenhang mit der Seitenleiste in Home Assistant:** Seit derselben Version erscheint eedc auch bei Benutzern **ohne** Administratorrechte in der HA-Seitenleiste — etwa auf Wandtablets. Vorher war der Eintrag Administratoren vorbehalten, was für reine Anzeige-Benutzer unpraktisch war. Beides gehört zusammen: der Eintrag macht eedc erreichbar, die PIN entscheidet, wer ändern darf.

### 2.1a eedc außerhalb Deutschlands

eedc lässt sich in **Deutschland, Österreich, der Schweiz und Italien** betreiben — das Land wählst du in den Stammdaten. Was dabei trägt und was nicht, steht hier bewusst offen, damit du es vor der Einrichtung weißt und nicht danach.

**Was überall gleich gut funktioniert**

Die Rechenkerne von eedc kennen keine Landesgrenze: Energiebilanz, Eigenverbrauch, Autarkie, Speicher- und Wärmepumpen-Auswertung, Amortisation und CO₂ arbeiten mit deinen Messwerten und deinen Tarifen. **PVGIS** deckt ganz Europa ab, **Open-Meteo** liefert weltweit Wetter- und Strahlungsdaten. Für alpine Standorte ist **MeteoSwiss ICON-CH2** das genauere Modell — es rechnet auf 2 km Raster und kennt das Relief, das gröbere Modelle glattbügeln.

**Was an Deutschland hängt**

| Funktion | Außerhalb Deutschlands |
| --- | --- |
| **Bright Sky (DWD)** als Wetterquelle | Nicht verfügbar. Das sind Messwerte deutscher Wetterstationen; ihr Netz endet an der Staatsgrenze. eedc nimmt dort automatisch Open-Meteo. |
| **Börsenstrompreise** | DE und AT über aWATTar/EPEX. Für CH und IT gibt es keine Anbindung. |
| **Community-Vergleich nach Region** | Innerhalb Deutschlands nach Bundesland, sonst nach Land. |
| **Kraftstoffpreise** (E-Auto-Vergleich) | DE, AT und IT aus dem EU-Bulletin; für CH rechnet eedc mit den österreichischen Werten als Näherung. |

**Was eedc bewusst *nicht* tut**

Steuerrecht, Netzentgelte, Einspeisevergütungen und Förderprogramme sind in jedem Land anders — und ändern sich dort unabhängig voneinander. eedc bildet sie **nicht** nach. Es rechnet mit den Zahlen, die du einträgst: dein Arbeitspreis, deine Vergütung, dein Umsatzsteuersatz, deine Anschaffungskosten. Der USt-Satz passt sich beim Länderwechsel an (DE 19 %, AT 20 %, CH 8,1 %, IT 22 %), aber ob und wie er auf dich zutrifft, entscheidest du.

Das ist eine bewusste Grenze und keine Lücke, die noch geschlossen wird. Eine Förderdatenbank für vier Länder wäre in dem Moment veraltet, in dem sie fertig ist — und eine falsche Zahl ist schlechter als gar keine. **Wo eedc etwas nicht weiß, fragt es dich, statt zu schätzen.**

### 2.2 Strompreise

Verwalte deine Stromtarife als Tabelle mit Gültigkeitszeiträumen — die Basis jeder Einsparungsberechnung:

- Mehrere Tarife mit **Gültigkeitszeitraum** möglich.
- **Spezialtarife:** Jeder Tarif kann einer Verwendung zugeordnet werden — Standard, Wärmepumpe oder Wallbox. Ohne Spezialtarif nutzt eedc automatisch den Standard-Tarif für die Komponente. Aktive Spezialtarife stehen in der Info-Box oben.
- **Zeitfenster (HT/NT):** Jeder Tarif kann Fenster mit abweichendem Arbeitspreis tragen (Uhrzeit, Wochentage, Preis) — siehe den Kasten unten.
- **Zählergebühr-Tarif:** Neben Grundgebühr lässt sich eine separate Zählergebühr erfassen; Grund- und Zählergebühren werden im Cockpit (Monat/Jahr) getrennt ausgewiesen.
- **Das Badge „Aktuell"** markiert den Tarif, mit dem eedc **heute** rechnet: gültig am heutigen Tag und — je Verwendung — der jüngste „Gültig ab". Standard- und Spezialtarif können damit gleichzeitig aktuell sein, zwei aufeinander folgende Standardtarife nicht. (Bis v4.0.5 trug es jeder Tarif ohne Enddatum, also auch abgelöste.)

> **Dynamischer Strompreis (Tibber/aWATTar/EPEX):** Den zugehörigen Sensor ordnest du nicht mehr hier, sondern unter **Einstellungen → Datenquellen** dem Feld „Strompreis" zu (siehe [§7](#7-datenquellen--feld-zentrische-zuordnung)). Ohne eigenen Sensor blendet eedc automatisch den EPEX-Börsenpreis (DE/AT via aWATTar) als Overlay im Live-Tagesverlauf ein.

> **Zeittarif (HT/NT) — ein anderer Preis zu bestimmten Uhrzeiten.** Zahlst du z. B. täglich von
> 19 bis 20 Uhr nur die Hälfte, trägst du das im Tarif unter **„Zeitfenster (HT/NT)"** ein: Von,
> Bis, der Preis in diesem Fenster und die Wochentage. Ein Fenster darf über Mitternacht laufen
> (Nachtstrom 22–6), und du kannst mehrere anlegen. Ohne Eintrag gilt der Arbeitspreis oben rund
> um die Uhr — an bestehenden Tarifen ändert sich nichts.
>
> **Wie eedc damit rechnet:** Der Monatspreis wird über deinen **gemessenen** Netzbezug
> gewichtet — jede Stunde bekommt den Preis, der zu ihr gehört, und daraus entsteht ein
> Durchschnitt für den Monat. Fielen 3 von 12 kWh ins Fenster, liegt er entsprechend näher am
> Niedertarif. In Cockpit → Monat steht dieser Wert als **„Ø-Preis HT/NT"**, damit er sich nicht
> mit dem Arbeitspreis aus deinen Stammdaten verwechseln lässt.
>
> ⚠ **Dafür braucht eedc Stundenwerte** — die entstehen, wenn der Netzbezug über einen
> zugeordneten Sensor läuft. Trägst du Monatswerte von Hand ein, gibt es die Stundenaufteilung
> nicht: dann rechnet eedc mit dem Arbeitspreis oben, also mit dem **Hochtarif**. Das ist zu
> hoch, aber nachvollziehbar — geschätzt wird nichts. Der Daten-Check sagt dir das, und der Weg
> daraus ist derselbe wie beim dynamischen Tarif: im Monatsabschluss unter **„Ø Strompreis"** den
> Wert aus deiner Abrechnung eintragen; er schlägt beides.
>
> **Feiertage kennt eedc nicht.** Wochentage ja, Feiertage nein — ein Feiertagskalender gilt je
> Bundesland bzw. Kanton, und ein falscher würde still einen falschen Preis erzeugen. Behandelt
> dein Vertrag Feiertage wie Sonntage, ist der Ø-Preis im Monatsabschluss der genaue Weg.
>
> **Die Wochentage gelten für die Uhrzeit selbst.** „Mo–Fr, 22–6 Uhr" deckt Freitag 22 bis 24 Uhr,
> aber **nicht** Samstag 0 bis 6 Uhr. Willst du die Nacht von Freitag auf Samstag ganz drin haben,
> leg ein zweites Fenster an (Sa, 0–6).

> **Einspeisevergütung: eedc rechnet flat mit dem eingetragenen Satz.** Der Einspeise-Erlös ist schlicht *eingespeiste Menge × dein Satz* ([Berechnungsreferenz 3.2](BERECHNUNGEN.md#32-finanzen-cockpit)) — es wird nichts im Hintergrund umgerechnet und nichts aus der Anlagengröße abgeleitet.
>
> **Wechselt deine Vergütung monatlich** (z. B. der OeMAG-Marktpreis in Österreich), setze im
> Tarif das Häkchen **„Einspeisevergütung wechselt monatlich“**. Der Monatsabschluss bietet dann
> das Feld **„Einspeisevergütung (Monat)“** an: der dort gepflegte Satz gilt für genau diesen
> Monat und schlägt den Stammwert aus dem Tarif — auch eine **0** ist ein gültiger Wert. Monate
> ohne Eintrag rechnen mit dem Stammwert; die Prognose nach vorn nimmt immer den Stammwert, denn
> künftige Monate haben noch keinen Satz. eedc holt die Monatswerte nicht automatisch ab — du
> trägst sie ein oder importierst sie per CSV (Spalte `Einspeiseverguetung_Cent`).
>
> Die EEG-Vergütung ist nach **installierter Leistung** gestaffelt (z. B. ein Satz bis 10 kWp, ein niedrigerer darüber) — nicht nach eingespeister Menge. Für die Gesamtanlage gilt deshalb der nach kWp **gewichtete Mischsatz**, und genau der gehört in dieses Feld. Rechenbeispiel mit **erfundenen** Sätzen — die für dich gültigen stehen in deinem Vergütungsbescheid: 12,5 kWp, davon 10,0 kWp zu 8,20 ct und 2,5 kWp zu 7,10 ct ⇒ (10,0 × 8,20 + 2,5 × 7,10) ÷ 12,5 = **7,98 ct/kWh**. Das ist keine Näherung, sondern exakt der Satz, den der Netzbetreiber im Mittel zahlt.
>
> eedc ermittelt diesen Satz **bewusst nicht selbst** — auch nicht als Vorschlag: Die EEG-Sätze ändern sich laufend, und welche Bedingungen für deine Anlage tatsächlich gelten (Inbetriebnahmedatum, Volleinspeisung, PPA, Direktvermarktung), weißt nur du. Ein neuer Tarif startet deshalb mit **0 ct/kWh**; mit 0 bleibt der Einspeise-Erlös des Zeitraums 0 €, und der **Daten-Checker** meldet das, sobald tatsächlich Einspeisung erfasst ist. Ist deine Einspeisung wirklich unvergütet, bleibt 0 richtig und der Hinweis aus.
>
> Wechselt dein Satz, trägst du einen **neuen Tarif mit eigenem „Gültig ab"** ein — die Historie bleibt dann mit ihrem alten Satz gerechnet.

### 2.3 Solarprognose

Diese Kachel kombiniert die PVGIS-Langfristprognose mit den Wetter-Provider-Einstellungen:

- **Systemverluste** (Standard 14 %, für DE typisch), **TMY-Referenz**, **optimale Ausrichtung** (berechnet Neigung/Azimut für deinen Standort).
- **Horizontprofil (Verschattung):** beschreibt, wie hoch Berge/Gebäude/Bäume den Horizont je Himmelsrichtung verdecken — eedc zieht das bei der Langfristprognose ab. Zwei Wege:
  - **Geländeprofil von PVGIS abrufen** — holt das Profil aus PVGIS-Geländedaten (erfasst Berge/Geländekanten, keine Gebäude/Bäume).
  - **Eigene Datei** — lädt ein selbst erstelltes Profil hoch (pro Zeile Azimut + Elevation in Grad, `#` = Kommentar; Azimut 0–360°, Elevation 0–90°, ≥ 4 Punkte). So bildest du feste Hindernisse wie Dachkanten oder Nachbargebäude ab.

  Ist ein Profil hinterlegt, zeigt die Karte Datenpunkte sowie min/max-Elevation; **Löschen** kehrt zu den automatischen Geländedaten zurück. Das Profil bildet **feste** Hindernisse ab — eine jahreszeitlich wechselnde Verschattung (Laubbäume) ändert sich damit nicht mit.
- **Wetter-Provider** (für Autofill/historische Werte): Auto (Bright Sky DE, sonst Open-Meteo), Bright Sky (DWD), Open-Meteo, Open-Meteo Solar (GTI-basiert für geneigte Module).
- **Prognose-Historie:** Jeder Abruf wird gespeichert und bleibt erhalten. **Genau einer ist „Aktiv"** und liefert die SOLL-Werte in *allen* Sichten und Berichten; über „Aktivieren" schaltest du bewusst auf einen anderen — auch auf einen **älteren**, etwa weil er mit einem genaueren Horizontprofil geholt wurde. Mehr dazu: [Prognosen §2.6](HANDBUCH_PROGNOSEN.md#26-die-aktive-pvgis-prognose--eine-und-du-bestimmst-welche).

> **Die Prognose zieht selbst nach, wenn sie nicht mehr zur Anlage passt.**
> Ändert sich die Nennleistung, die Ausrichtung, die Neigung, der Standort oder
> das Horizontprofil, holt eedc nachts eine neue Prognose — mit **deinen**
> eingestellten Systemverlusten, nicht mit dem Standardwert. Die bisherige
> Prognose bleibt in der Historie und ist jederzeit wieder aktivierbar.
>
> Das **Alter** einer Prognose ist dagegen kein Grund für einen Neuabruf, und
> die Kachel warnt auch nicht mehr davor: PVGIS rechnet mit einem
> Langzeit-Mittel über viele Jahre. Eine ein Jahr alte Prognose liefert für
> dieselbe Anlage dieselbe Zahl wie eine von heute — falsch wird sie erst durch
> eine Änderung. Statt „Letzter Abruf vor N Tagen" meldet die Kachel deshalb,
> **was** nicht mehr passt, zum Beispiel „Nennleistung 9,80 → 2,40 kWp".

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

> **Die Zeile heißt „Zuordnung", nicht „Kopplung".** Die frühere Anzeige „DC-gekoppelt" leitete sich allein daraus ab, *ob* ein Wechselrichter zugeordnet ist — ein AC-Speicher am Hybrid-Wechselrichter war damit falsch beschriftet. Die Zeile nennt jetzt den Wechselrichter beim Namen und erklärt, was die Zuordnung bewirkt. Die Kopplung ist davon **unabhängig** und wird seit #351 als eigenes Feld gepflegt (s. [§3.4](#34-typ-spezifische-parameter)); sie ändert keine Zahl, sondern sagt, **wo** gemessen wird.

### 3.2 Anschaffungs- und Stilllegungsdatum

Jede Investition hat zwei Lebenszyklus-Daten, die für **alle** Auswertungen gelten:

> **Das Anschaffungsdatum ist Pflicht** (seit v4.0.1). Es ist die Grenze jeder Auswertung — ohne Datum zählt eine Komponente auch für Zeiträume vor der Anschaffung mit — und der Nullpunkt der Amortisationskurve. Neue Komponenten lassen sich nur noch mit Datum anlegen; für vorhandene meldet es der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md#438-allgemein-alle-komponententypen) als **Fehler** und springt per Klick direkt in das Formular der betroffenen Komponente.

- **Anschaffungsdatum:** ab hier zählt die Investition. Aggregate (JAZ, Wärme, Strom, Ersparnis usw.) ignorieren Monatsdaten **vor** diesem Datum. Nützlich beim Wechsel der Erfassungsmethode (z. B. von WP-eigener Strommessung auf einen Shelly-Zähler): alte Werte bleiben historisch erhalten, verfälschen aber die aktuelle JAZ nicht.
- **Stilllegungsdatum:** Endmarker — ab hier zählt die Investition nicht mehr für aktuelle/künftige Auswertungen; historische Aggregate behalten sie.

> **Ein Gerät darf älter sein als die Anlage.** Das E-Auto von 2017 an einer PV-Anlage von 2022 ist der Regelfall, und das Anschaffungsdatum gehört dann auf 2017. Der Daten-Checker erwähnt das als **Hinweis** — nicht als Fehler: Für die Monate vor der Anlage gibt es keine Einspeisungs- und Netzbezugswerte und damit keine Bilanz, eedc kann dort also nicht sagen, ob der Strom gekauft oder selbst erzeugt war. **Datiere das Gerät deshalb nicht um.** Genau das ist einem Anwender passiert, der die Meldung loswerden wollte; die echte Anschaffungshistorie seines Fahrzeugs war danach verloren. Hast du Zählerwerte aus der Zeit davor, trag sie nach; stimmt umgekehrt das Inbetriebnahme-Datum der **Anlage** nicht, korrigiere dieses.

#### Eine Komponente erweitern oder ersetzen

Ein Speicher wird aufgestockt, ein Gerät gegen ein größeres getauscht — die Frage kommt regelmäßig. **Es gibt zwei Wege, und beide sind richtig; sie kosten nur Verschiedenes.** Eine Erweiterung ohne neue Sensoren lässt sich nicht so abbilden, dass jede Sicht rückwirkend stimmt — deshalb entscheidest du, welcher Preis dir lieber ist:

| | **A — ein Datensatz** | **B — zwei Datensätze** |
| --- | --- | --- |
| Was du tust | Kapazität der Komponente erhöhen, die Kosten der Erweiterung als **Ausgabe unter „Sonstige Positionen"** im Monat der Aufrüstung buchen | Altes Gerät stilllegen, neues mit der Gesamtkapazität anlegen (Schritte unten) |
| Was es kostet | Vollzyklen und Auslastung **der Vergangenheit** rechnen gegen die neue, größere Kapazität — die alten Monate sehen schlechter aus, als sie waren | Die Monatsdaten müssen umgehängt werden, und für das stillgelegte Gerät lässt sich **nichts mehr importieren** |
| Was unberührt bleibt | Sensoren, Import, Datenquellen — alles läuft weiter | Die Kennzahlen jedes Zeitraums stimmen gegen die Kapazität, die damals da war |
| Passt, wenn | dir die Wirtschaftlichkeit wichtiger ist als die Speicher-Historie | du die Speicher-Kennzahlen der Vergangenheit auswerten willst |

**Die Geldrechnung ist bei beiden Wegen gleich** — dein Kapitaleinsatz ist die Summe dessen, was du bezahlt hast, und die Amortisation rechnet damit. Weg A ist der bequemere; wenn du bereits so gepflegt hast, gibt es **keinen Grund umzubauen**.

**Weg B im Einzelnen** — an einem echten Bestand durchgespielt, nicht hergeleitet:

1. **Am alten Gerät das Stilllegungsdatum setzen** — und zwar den **Tag vor** dem Erweiterungstag. Anschaffungs- und Stilllegungsdatum sind beide **inklusiv**; trägst du denselben Tag ein, an dem das neue Gerät startet, zählt der Wechselmonat doppelt. **Niemals stattdessen den Haken „aktiv" entfernen** — das nimmt die Komponente auch aus der Historie.
2. **Neuen Datensatz ab dem Erweiterungstag anlegen**, mit der **Gesamtkapazität** (nicht mit der Differenz).
3. **Denselben Wechselrichter zuordnen** wie beim alten Gerät. Ohne ihn gilt der neue Speicher als eigenständig und bekommt eine eigene ROI-Zeile, während der alte Teil des PV-Systems bleibt — gleicher Gerätetyp, zwei Darstellungen.
4. **Monatsdaten ab dem Wechselmonat umhängen.** Sie bleiben sonst am alten Datensatz und fallen mit dessen Stilllegung aus der Anzeige.
5. **Kosten: jeder Datensatz trägt, was für ihn bezahlt wurde** — das alte Gerät behält seinen ursprünglichen Preis, der neue bekommt **die Kosten der Erweiterung** (nicht den Neuwert des Gesamtsystems). Damit steht in eedc genau die Summe, die du wirklich ausgegeben hast.

> **Und den Restwert des alten Geräts brauchst du nicht** — eedc stellt die Frage gar nicht. Gerechnet wird **eingesetztes Geld gegen Ersparnis**, und eingesetzt ist, was du bezahlt hast; eine Wertfortschreibung wie in einer Bilanz kommt darin nicht vor. Wir haben das durchgerechnet: Den Restwert als Ertrag zu buchen, ihn zwischen den Geräten umzubuchen oder ihn als Nullsumme zu führen — jede dieser Varianten macht eine andere Zahl falsch. Der einfachste Weg ist auch der richtige.

**Was dabei herauskommt:** Der Komponenten-Hub zeigt beide Geräte getrennt, jedes mit eigenem Zeitraum und eigener Kapazität, und jeder Abschnitt rechnet gegen **seine** Kapazität. Die Summe der Lade- und Entlademengen bleibt unverändert — es geht keine Energie verloren und keine wird doppelt gezählt.

> **Die Anlage zählt dabei nur ein Gerät.** Kapazitäts-Angaben — im Cockpit, im Jahresbericht und im anonymen Community-Vergleich — nennen den Speicher, den du **heute** hast, nicht die Summe deiner Gerätegeschichte.

> ⚠ **Eine Einschränkung, die dazugehört:** Für ein stillgelegtes Gerät lässt sich **nichts mehr importieren**. Der Weg gilt deshalb für Bestände, deren Monatswerte gepflegt oder wie in Schritt 4 umgehängt werden — nicht für den laufenden automatischen Sensor-Import über den Wechselmonat hinweg. Trag die Monatsdaten des alten Geräts also **vor** dem Stilllegen fertig ein.

> **Bei PV ist es einfacher:** Ein zusätzliches **Modulfeld mit eigenem Anschaffungsdatum** genügt — kein Stilllegen, kein neuer Datensatz für das Bestehende. Für Wärmepumpe, Wallbox und E-Auto ist dieser Weg **nicht** durchgemessen; dort gilt die Anleitung ausdrücklich nicht.

### 3.3 Geräte-Detaildaten in der Infothek

Hersteller/Modell/Seriennummer/Garantie, Ansprechpartner und Wartungsvertrag sind **nicht** Teil des Komponenten-Formulars, sondern werden über die [Infothek](HANDBUCH_INFOTHEK.md) gepflegt und N:M mit beliebig vielen Komponenten verknüpft. Beim Bearbeiten einer Komponente werden verknüpfte Infothek-Einträge als kompakte Liste mit Direktlink angezeigt.

### 3.4 Typ-spezifische Parameter

- **PV-Module:** Anzahl Module, Leistung pro Modul (Wp), Ausrichtung (Süd = 0°, Ost = −90°, West = +90°), Neigung (0° flach … 90° senkrecht). Anzahl und Wp sind optional; sind beide gepflegt, vergleicht eedc `Anzahl × Wp` mit der eingetragenen Leistung (kWp) und weist eine Abweichung direkt im Formular aus — der Daten-Checker nennt denselben String dann beim Namen, statt nur die Anlagensumme zu bemängeln.
- **Speicher:** Kapazität (kWh), **nutzbare Kapazität (kWh)**, max. Leistung (kW), **Kopplung**, arbitrage-fähig (Ja/Nein). Die nutzbare Kapazität ist die Reserve-bereinigte Größe (wer 10/90 fährt, trägt bei 10 kWh brutto 8 kWh ein); sie verfeinert den gemessenen Wirkungsgrad. Vollzyklen und die Wirtschaftlichkeits-Prognose rechnen weiterhin mit der Brutto-Kapazität ([Berechnungen §3.3](BERECHNUNGEN.md#33-speicher-einsparung)).
  > **Aus dieser Zahl folgt deine Entladegrenze.** eedc rechnet `1 − nutzbar ÷ brutto` und behandelt das Ergebnis als den Ladestand, ab dem dein Speicher nichts mehr abgibt — davon hängt unter *Wirtschaftlichkeit* die Antwort auf „hätte mehr Kapazität geholfen?" ab. Das Formular rechnet die Grenze deshalb beim Eintippen vor.
  > ⚠ **Die Annahme dahinter: die ganze Reserve liegt unten.** Wer 10/90 fährt, trägt die obere Grenze korrekt mit ein (bei 10 kWh brutto also 8 kWh) — die abgeleitete Untergrenze fällt dann aber zu hoch aus (20 % statt 10 %), und die Kapazitätsfrage wird zu positiv beantwortet. Ein zweites Feld „Entladegrenze %" gibt es dafür bewusst nicht; die Anzeige nennt stattdessen die Annahme, damit du die Abweichung siehst.
  > **Kopplung — AC oder DC?** Die Vorbelegung *Automatisch* leitet sie aus der Wechselrichter-Zuordnung ab (zugeordnet ⇒ DC, sonst AC) und schreibt im Formular dazu, was dabei herauskommt. Das trifft die meisten Anlagen, aber nicht alle: Ein **AC-Speicher an einem Hybrid-Wechselrichter** und ein **DC-Speicher ohne erfassten Wechselrichter** brauchen die ausdrückliche Angabe. Sie **ändert keine Zahl** — ob der Speicher als Teil des PV-Systems oder eigenständig gerechnet wird, entscheidet weiterhin allein die Zuordnung. Wozu sie dient: Sie legt fest, **wo** Ladung und Entladung gemessen werden — bei AC-Kopplung hausseitig hinter dem Batterie-Wechselrichter, bei DC-Kopplung am Batterie-Anschluss. **Beide Werte müssen von derselben Seite kommen**, sonst enthält der Wirkungsgrad die Wandlung nur in eine Richtung und beschreibt die Messstelle statt den Speicher.
- **E-Auto:** Batteriekapazität (kWh), V2H-fähig, „nutzt V2H aktiv".
  > **Plug-in-Hybrid?** Dann trag unter *Vergleich & Betrieb* den **eigenen Verbrauch (L/100 km)**
  > ein — das ist, was dein Fahrzeug im Verbrenner-Betrieb wirklich tankt, nicht der
  > Vergleichs-Benziner darüber. Erst dieses Feld sagt eedc, dass überhaupt ein Verbrenner
  > mitfährt; ein eigenes „Fahrzeugtyp"-Feld gibt es bewusst nicht. Lässt du es leer, rechnet
  > eedc wie bisher mit rein elektrischer Fahrt.
  >
  > Den elektrischen Anteil bestimmt eedc am liebsten **gemessen**: aus dem monatlich erfassten
  > Fahrverbrauch (kWh) und deinem kWh/100 km. Erfasst du den Fahrverbrauch nicht, trag den
  > **elektrischen Fahranteil (%)** als Schätzung ein — sonst rechnet eedc weiter mit 100 %
  > elektrisch und sagt es dir im [Daten-Checker](HANDBUCH_DATEN_CHECKER.md). Einen Richtwert
  > setzt eedc nicht von sich aus ein: das wäre eine Behauptung über dein Fahrzeug.
  > Details: [Berechnungen §3.4](BERECHNUNGEN.md#34-e-auto-einsparung).
- **Wärmepumpe:** **JAZ** (Standardwert, falls kein Wärmemengenzähler), **Alternativkosten** (Gas/Öl als Mehrkosten-Basis), **jährliche Zusatzkosten der Alt-Heizung** (Schornsteinfeger, Wartung, Gaszähler-Grundpreis), **Alt-Tarif Gas/Öl** (ct/kWh, Fallback wenn ein Monat keinen eigenen Gaspreis führt).
- **Wallbox:** max. Ladeleistung (kW), bidirektional.
- **Wechselrichter:** max. Leistung (kW), MaStR-ID.
- **Sonstiges:** Kategorie (Erzeuger / Verbraucher / Speicher / **Verbrauchszähler**) + Beschreibung; die Monatsdaten-Felder passen sich der Kategorie an.

  > **Zweiter Erzeuger mit eigenem Einspeisetarif.** eedc kennt genau **einen** Einspeisesatz je Anlage — für einen Erzeuger, der anders vergütet wird (zweiter Wechselrichter, Erweiterung mit neuem EEG-Satz), gibt es bei Kategorie *Erzeuger* das Feld **„Einspeise-Erlös (€)"**. Trag den Betrag entweder im Monatsabschluss ein oder — besser — ordne ihm unter [Datenquellen](#7-datenquellen--feld-zentrische-zuordnung) einen Sensor zu: ein **Helfer in Home Assistant**, der den Erlös mit deinem Satz aufsummiert, am besten als Verbrauchszähler **ohne Zyklus** (nie zurücksetzen — eedc bildet die Monatswerte aus der Differenz). Rechnest du per Template, gib dem Sensor `state_class: total_increasing` und `device_class: monetary` mit, damit er in der Auswahl erscheint.
  >
  > ⚠ **Der Betrag kommt zusätzlich** und wird **nicht** gegen den Einspeise-Erlös der Anlage gerechnet: Zwei Vergütungssätze bedeuten zwei Messungen, in den Einspeisezähler der Anlage gehört also nur die Menge, die zum Anlagentarif abgerechnet wird. Wer den Erlös bisher monatlich als *sonstigen Ertrag* gebucht hat, lässt das ab dem Umstiegsmonat weg — sonst zählt derselbe Betrag zweimal.

### 3.4a Verbrauchszähler für Gas, Öl und Wasser (#377)

Unter *Sonstiges* gibt es die Kategorie **Verbrauchszähler**. Sie ist für die
Zähler gedacht, die neben dem Strom im Haus laufen: Gas, Heizöl, Flüssiggas,
Pellets, Wasser.

**Was eedc damit macht — und was ausdrücklich nicht.**

eedc führt den **Zählerstand** mit, also genau die Zahl, die auf dem Zähler
steht. Die einzige Rechnung darauf ist die Differenz zwischen Anfang und Ende
des Zeitraums, den du gerade ansiehst. Mehr passiert nicht:

| eedc zeigt | eedc rechnet **nicht** |
| --- | --- |
| Aktueller Stand (Live, *Auf einen Blick*) | Energiebilanz, Autarkie, Eigenverbrauchsquote |
| Stand am Anfang/Ende und die Differenz (Cockpit Tag/Monat/Jahr) | Wirtschaftlichkeit, Amortisation, Netto-Ertrag |
| Verlauf über den Gesamtzeitraum (Komponenten → Sonstiges) | CO₂-Bilanz |
| Eine Spalte je Zähler in den Tabellen (wählbar) | Gemeinschaftsdaten (dort ist alles Strom) |

**Warum so streng?** Gas- oder Wasserkosten sind Haushaltskosten. Sie in die
Rechnung der PV-Anlage zu ziehen, machte deren Zahlen unbrauchbar — und für
einen echten Effizienzvergleich (vor/nach einer Modernisierung) bräuchte eedc
die Heizung als eigene Komponente mit Wirkungsgrad und Wärmemenge. Sonst stünden
Kubikmeter gegen Kilowattstunden.

**Einheit.** Beim Anlegen wählst du, was gezählt wird (Gas, Wasser, Heizöl …)
und in welcher Einheit (m³, l, kg, t, kWh). Beides ist **reine Anzeige**: Die
Einheit steht neben der Zahl, und eedc rechnet nichts um. Wer seinen Gaszähler
in kWh abliest, trägt kWh ein — in die Strombilanz kommt der Wert trotzdem
nicht.

**Woher der Stand kommt.** Entweder aus einem Sensor (unter *Datenquellen*
zuordnen — dann schreibt eedc stündlich mit), oder du trägst ihn im
**Monatsabschluss** von Hand ein: das Feld heißt *Zählerstand*. Wo ein Sensor
läuft, wird der mitgeschriebene Stand als Vorschlag angeboten.

> ⚠ **Entweder Sensor oder Handeingabe — nicht gemischt.** Ein von Hand
> eingetragener Stand gilt für genau diesen einen Monat; der nächste kommt
> wieder vom Sensor. Weichen beide voneinander ab, entsteht dazwischen ein
> Sprung, der wie ein riesiger Verbrauch aussähe. eedc weist ihn deshalb nicht
> als Menge aus, sondern sagt „Der Stand ist gefallen — die Reihe hat einen
> Bruch".

> ⚠ **Weicht die Zahl auf deinem Zähler von der im Sensor ab, gehört die
> Korrektur an den Sensor** — in Home Assistant oder in der App, die die Werte
> per MQTT schickt. Dort stimmt sie danach überall, auch in deinen
> HA-Dashboards und Automationen. eedc bietet bewusst kein zweites Startwert-
> oder Offset-Feld an: Du hättest sonst zwei Zahlen für denselben Zähler. Auf
> deinen **Verbrauch** hat der Versatz ohnehin keine Wirkung — die einzige
> Rechnung ist Ende minus Anfang, und die Differenz bleibt dieselbe.

> ⚠ **Zählerwechsel: das alte Gerät stilllegen, ein neues anlegen.**
> Setz beim alten Zähler ein **Stilllegungsdatum** — und lass ihn dabei
> **aktiv**. Dann bleibt seine Ablesehistorie in allen Auswertungen erhalten, in
> deren Zeitraum er gemessen hat, und der Verbrauch über den Wechsel hinweg ist
> sauber die Summe beider Differenzen.
>
> ⛔ **Nicht** den Haken *aktiv* entfernen: Das bedeutet in eedc „wie gelöscht"
> und blendet das Gerät **auch rückwirkend** aus jeder Sicht aus. Die alten
> Ablesungen wären dann weg, obwohl sie gemessen wurden.

### 3.5 Balkonkraftwerk mit mehreren Ausrichtungen — und wann Wechselrichter + PV-Module?

Beide Wege bilden erzeugende Module ab, und die Frage kommt regelmäßig. Sie hängt an **einer**
Eigenschaft:

> **Ein Balkonkraftwerk trägt für sich genau *eine* Ausrichtung und *eine* Neigung.** Es ist als
> Kompaktgerät gedacht — Module, Mikro-Wechselrichter und (optional) Akku in einer Investition. Die
> Modulzahl steckt in *Leistung je Modul × Anzahl*; alle Module teilen sich dann dieselbe
> Ausrichtung. Die Option **„Ost-West (gemischt)"** rechnet einen festen **50/50**-Split.

**Neu: du kannst dem Balkonkraftwerk PV-Module zuordnen.** Damit wird jede Ausrichtung einzeln
erfasst — ohne das Gerät als Wechselrichter umdeklarieren zu müssen. So geht es:

1. *Einstellungen → Investitionen → Hinzufügen*, Typ **PV-Module** (im Einrichtungsassistenten
   genauso).
2. Unter **Gehört zu** das **Balkonkraftwerk** wählen.
3. Je Modul(-gruppe) Leistung, Ausrichtung und Neigung eintragen — eine Investition je Richtung.

**Wann welcher Weg:**

| Deine Anlage | Erfassen als | Warum |
|---|---|---|
| Stecker-Solargerät, alle Module gleich ausgerichtet | **Balkonkraftwerk** allein | Ein Gerät, ein Datensatz. Der Mikro-Wechselrichter braucht keine eigene Investition. |
| Stecker-Solargerät, Module je zur Hälfte Ost und West | **Balkonkraftwerk** allein, Ausrichtung „Ost-West (gemischt)" | Der 50/50-Split trifft genau diesen Fall — der kürzeste Weg. |
| Stecker-Solargerät, Module in **mehreren** Richtungen oder **ungleich** verteilt (Balkon + Terrasse) | **Balkonkraftwerk + zugeordnete PV-Module** | Jede Richtung bekommt ihre eigene Prognose, das Gerät bleibt in eedc ein Balkonkraftwerk. |
| Dachanlage, mehrere Strings | **Wechselrichter + PV-Module** | Der Regelfall. |

**Was das Balkonkraftwerk abgibt, sobald Module zugeordnet sind:** **Nennleistung, Ausrichtung und
Neigung** kommen dann von den Modulen — das Gerät zeigt als Leistung die Summe seiner Module, und
seine eigenen Felder beschreiben nur noch das Gerät. Das Formular sagt es an der Stelle.

> ⚠ **Was es behält, und was du weiter pflegen musst: die *Wechselrichter-Leistung (W)*.** Sie
> gehört dem Gerät und begrenzt die **Summe** aller zugeordneten Module — sie ergibt sich gerade
> *nicht* aus ihnen. Bei einem Stecker-Gerät sind das 800 W (bzw. 600 W bei älteren). eedc kappt dein
> SOLL damit **stündlich** an dieser Grenze, gemeinsam über alle Module. Ohne den Eintrag
> prognostiziert PVGIS die volle Modulleistung, und dein SOLL wäre ein Ziel, das die Anlage
> konstruktionsbedingt nie erreicht. Das sind zwei **verschiedene** Grenzen — die AC-Grenze am
> Wechselrichter-Ausgang und die Modulleistung —, und nur die zweite wächst mit der Zuordnung.

**Beim Monatsabschluss ändert sich nichts, was du wissen musst:** Der Wert **Erzeugung** am
Balkonkraftwerk bleibt nutzbar und zuordenbar — bei einem Set ist der Wechselrichter meist der
einzige Zähler, den es gibt. Er gilt dann als **Gesamtsumme der Module**: Hat ein Modul einen eigenen
Messwert, gewinnt der; die übrigen bekommen den Rest nach Leistungsanteil. Doppelt gezählt wird
nichts.

**In der Wirtschaftlichkeit stehen sie als ein System.** Sobald etwas an deinem Balkonkraftwerk
hängt — Module oder ein Speicher —, zeigt *Auswertungen → ROI* dafür **eine** Zeile mit deinem
Gerätenamen; die Komponenten klappst du darunter auf. Das ist Absicht und dieselbe Darstellung wie
bei einem Wechselrichter mit seinen Strings: Die Ersparnisse der Ebenen lassen sich **nicht
addieren**, weil sie alle aus derselben Energie stammen. Bis v4.0.18 standen dort drei getrennte
Zeilen, deren Summe die Amortisation deutlich zu kurz erscheinen ließ.

**Wenn du auf Wechselrichter + PV-Module ausweichst** (Dachanlage oder gewachsene Anlage): Trage beim
Wechselrichter die **max. Leistung (kW)** ein — dieselbe Rolle wie oben, eine Ebene höher.

> **Achte auf die Nennleistung der Anlage.** Ein Balkonkraftwerk zählt in eedc **nicht** in die
> Anlagenleistung — es ist eine eigene Anlage mit eigener MaStR-Registrierung. Wechselrichter +
> PV-Module dagegen schon. Wer von einem Weg auf den anderen wechselt, prüft danach *Einstellungen →
> Anlage → Leistung (kWp)*.

**Was ein Balkonkraftwerk alles kann:** eigenes PVGIS-SOLL, eigene Zeile im String-Vergleich und in
der Mehrjahres-Performance, eigene Zeile im Jahresbericht, eigene Wirtschaftlichkeit, eigener Eintrag
in Energiebilanz und CO₂ — mehrere Ausrichtungen (s. o.) und einen **eigenen Akku** (s. unten). Der
Weg über den Wechselrichter ist damit kein Ausweichweg mehr, sondern nur noch der Fall Dachanlage.

**Der Akku am Balkonkraftwerk** (Anker Solarbank, Zendure u. ä.) wird als **eigene Speicher-Investition** angelegt, mit dem Balkonkraftwerk als übergeordneter Komponente. Nur so bekommt er Live-Leistung, Ladestand, einen Knoten im Energiefluss und einen eigenen Zählerpfad. Die Speicher-Felder im Monatsabschluss des Balkonkraftwerks selbst sind Altbestand aus der Zeit davor — sie lassen sich weiter pflegen, aber der Akku ist darüber keiner Auswertung zuzuordnen.

---

> **Ein Schlüsselsatz für alle Wege:** Setup-Wizard, Komponenten-Formular und das Backend halten dieselben Parameter-Schlüssel. Felder, die du im [Setup-Wizard](HANDBUCH_INSTALLATION.md) erfasst, landen direkt unter den hier dokumentierten Werten.

---

## 4. Infothek & Berichte

### 4.1 Infothek

Die Infothek ist deine anlagengebundene Wissensbasis (Verträge, Datenblätter, Notizen, Links, Vertragspartner). Sie läuft als vollständige Verwaltung **inline im Block** — der große Voll-Blick über die Vollbild-Ansicht (⤢). Details und Kategorien: **[Infothek-Handbuch](HANDBUCH_INFOTHEK.md)**.

### 4.2 Berichte & Dokumente

Die Kachel **Berichte & Dokumente** öffnet den Dokumente-Dialog der Anlage. Jede Karte lädt ihr PDF mit einem Klick; **die Einstellungen eines Dokuments stehen in seiner Karte** (Zeitraum beim Jahresbericht, Monat und Themen beim Monatsbericht). Für mehrere Berichte auf einmal gibt es oben rechts **„Mehrere als ZIP"** — dann wählen dieselben Karten aus, statt zu laden.

- **Jahresbericht** (alle KPIs: Energie, Autarkie, Finanzen, CO₂; Diagramme; Monatstabellen; PV-String SOLL/IST).
- **Anlagendokumentation** (Stammdaten, Versorger, Tarif, Komponenten mit Parametern + verknüpften Infothek-Einträgen).
- **Finanzbericht** und **Infothek-Dossier**.
- **Monatsbericht** — die Zahlen **eines** Monats im Stil der Cockpit-Monatsansicht, mit Kennzahl-Kacheln, Anteils-Leisten und Diagrammen.

> **HA-Companion:** PDF-, CSV- und Backup-Downloads laufen über `fetch + Blob` — damit funktionieren sie in der iOS-HA-Companion-App ohne 401-/Ingress-Probleme.

#### Der Monatsbericht

Er ist der einzige Bericht mit eigenen Einstellungen — sie stehen direkt unter den Karten:

| Einstellung | Was sie bewirkt |
| --- | --- |
| **Monat** | Genau ein Monat, voreingestellt der neueste erfasste. Eine Spanne über mehrere Monate ist der Jahresbericht darüber. |
| **Themen** (Energie · Komponenten · Finanzen · CO₂ · Community) | Bestimmen, *was für ein* Bericht entsteht. Voreingestellt sind alle an. |
| **Wie in meiner Monatsansicht** | Lässt die Anzeigen weg, die du unter *Cockpit → Monat* geparkt hast. Erscheint nur, wenn dort überhaupt etwas geparkt ist; voreingestellt an. |

Anlagenname und Standort stehen immer im Dokument, wie in jedem anderen Bericht dieser Anlage.

**Was der Bericht grafisch aufbereitet:**

- **Kennzahl-Kacheln** oben — PV-Erzeugung, Eigenverbrauch, Einspeisung, Netzbezug,
  Gesamtverbrauch, Autarkie und die Quoten, wie im Kopf der Monatsansicht.
- **Anteils-Leisten** für die PV-Verteilung und für Erzeugung bzw. Verbrauch nach Kategorie.
- **Verlauf** — ein Balken je Tag des Monats. ⚠ **Tage ohne gemessene Erzeugung bekommen keinen
  Balken**, auch keinen der Höhe null: Eine Null-Säule neben echten Werten würde behaupten, an
  diesem Tag sei nichts erzeugt worden. Wie viele Tage gemessen wurden, steht als Zeile darunter.
- **Typisches Tagesprofil** — die Ø-Leistung je Stunde über den Monat, PV und Verbrauch.
- **Spitzenstunden** für Netzbezug und Einspeisung, je die fünf höchsten.

> **Jede Aussage steht auch als Zahl.** Was ein Diagramm zeigt — bester Tag, schwächster Tag,
> Durchschnitt —, steht als Zeile daneben; das Bild ist die Veranschaulichung, nicht die einzige
> Quelle.

#### Der Community-Vergleich im Bericht

Mit dem Thema **Community** stellt der Bericht deine Werte dem **Median** aller Anlagen
gegenüber, die ihre Zahlen für **denselben Monat** geteilt haben — spezifischer Ertrag,
Autarkie, Eigenverbrauchsquote, Einspeisung und Netzbezug. Dabei steht, gegen **wie viele
Anlagen** verglichen wurde: Ein Median aus drei Anlagen sagt etwas anderes als einer aus
dreihundert.

> **Ist der Community-Server gerade nicht erreichbar, entfällt allein dieser Abschnitt** —
> der übrige Bericht entsteht vollständig und unverändert. Es erscheinen dort keine
> Gedankenstriche und keine Fehlermeldung: Ein Vergleich, den es nicht gibt, wird nicht
> behauptet.

> **Der Vergleich ist an *diesen* Monat gebunden, nicht an den Tag der Erstellung.** Der Median
> kann sich später noch leicht verschieben, wenn weitere Anlagen ihre Werte für den Monat
> nachreichen — die verglichene Größe bleibt dieselbe.

> **Es gibt bewusst kein „anonymisiert".** Ein PV-Monatsbericht ist über Ertragsprofil,
> Standort und Tarif praktisch eindeutig; die Zusage wäre nicht zu halten. Über die
> Themenschalter entscheidest du, was drinsteht — und siehst das Ergebnis. Wer wirklich
> anonym vergleichen will, nutzt den **Community-Vergleich**: der arbeitet mit einer
> Kennung statt mit deinem Namen.

> **Der Park-Zustand gehört zu diesem Browser.** Wer am Tablet Anzeigen parkt und am PC den
> Bericht zieht, bekommt dort den vollständigen Bericht — die geparkte Auswahl liegt nicht
> in der Anlage, sondern im Browser, in dem du geparkt hast. Was der Bericht weggelassen
> hat, steht am Ende des Dokuments.

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
- **„Weicht ab" meldet sich nur bei echten Unterschieden.** Ob Sensorwert und gespeicherter Wert als gleich gelten, entscheidet die **Genauigkeit des Sensorwerts**: liefert er eine Nachkommastelle, wird auch nur auf diese Stelle verglichen (2,3 ↔ 2,33 = gleich), liefert er mehr, wird auf höchstens drei Stellen verglichen. Damit verschwinden die Rundungs-Meldungen, die sich nach jedem Speichern wieder zeigten. Eine **echte** Differenz — etwa 453,7 gegen 454,74 — bleibt markiert; das ist die Funktion und ein Hinweis darauf, dass Zähler und gespeicherter Wert wirklich auseinanderlaufen.
- **„Gespeicherten behalten" bleibt erhalten.** Entscheidest du dich bei einer echten Abweichung bewusst für deinen Wert, merkt sich eedc diese Entscheidung — der Monat kann damit „alles fertig" erreichen, statt dauerhaft auf „prüfen" zu stehen. Das Feld wird **nicht stumm**: das Etikett sagt weiter „geprüft (weicht vom Sensor ab)", und die Zeile „Sensor meldet X · gespeichert Y · von dir behalten" bleibt lesbar, samt „Sensorwert übernehmen" als Rückweg. Gemerkt wird dabei nicht nur „bestätigt", sondern **wogegen**: meldet der Zähler später einen anderen Wert oder änderst du den gespeicherten Wert, ist die Entscheidung hinfällig und das Feld meldet sich wieder. So kann eine alte Bestätigung keine neue Abweichung verdecken.
- **Vorschläge sind nach Herkunft gewichtet — und die Zuordnung schlägt die Verteilung.** Ein Wechselrichter-Connector liefert genau **einen** Zählerstand. Hast du dieses Feld einer bestimmten Komponente zugeordnet (Einstellungen → Connector), geht der volle Wert dorthin und heißt „Vom Wechselrichter (Zählerstand-Differenz)" — die anderen Module bekommen aus dieser Quelle keinen Vorschlag mehr, denn der Zähler ist bereits vollständig zugeordnet. **Ohne** Zuordnung wird nach Nennleistung verteilt; der Vorschlag heißt dann ehrlich „Gesamtwert, anteilig nach kWp auf die Strings verteilt" und wird **niedriger gewichtet als jede gemessene Quelle**. Für Speicher gilt dasselbe mit der Kapazität. Bei nur einer Komponente ändert sich nichts. **Vorschläge werden wie immer erst durch Bestätigen übernommen** — nichts wird automatisch geschrieben.
- **Verschachtelte Sektionen:** Die Felder sind in einklappbare Abschnitte je Komponententyp/Gerät gegliedert, jeweils mit einem Rollup-Badge.

**Felder (Auswahl):**

- **Basis (immer):** Jahr, Monat, Einspeisung (kWh), Netzbezug (kWh).
- **Je Komponente (Energie-Daten in kWh):** PV-Erzeugung pro String; Speicher-Ladung/-Entladung/-Netzladung; WP Strom sowie WP Wärme Heizen/WW (die beiden Wärme-Spalten sind **thermisch**, nicht der Strom); E-Auto km/Verbrauch/externe Ladung; Wallbox-Ladung; BKW Erzeugung/Eigenverbrauch (Einspeisung wird berechnet).
- **Vergleichspreise (optional):** eine eigene Untergruppe — **Ø Benzinpreis (€/L)** und **Ø Gas-/Ölpreis (ct/kWh)** als Monatsdurchschnitte für die Alternativ-Vergleiche (E-Auto / Wärmepumpe). Sie sind **nicht Teil der kWh-Bilanz** und erscheinen nur, wenn eine E-Auto- oder Wärmepumpe-Komponente vorhanden ist. (Bewusst aus den kWh-Feldern herausgezogen, damit Energie-Werte und Preis-Annahmen nicht vermischt werden.)
- **Sonstige Positionen (G19-1):** frei erfassbare Kosten und Erlöse je Monat (Reparaturen, Wartung, THG-Quote, sonstige Erträge). Sie fließen als eigene Zeilen in die Finanz-Summen ein — siehe [Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#41-finanzen). In der **Wirtschaftlichkeit** wirken sie genau einmal: eine Ausgabe erhöht deinen Kapitaleinsatz, ein Ertrag mindert ihn. **Wiederkehrende** Beträge gehören stattdessen an die Komponente (*Kosten/Jahr* bzw. *Ertrag/Jahr*, beim zweiten Erzeuger *Einspeise-Erlös*) — nur dort wirken sie auch in der Prognose.

> **Heimladung gehört an die Wallbox.** Hast du eine Wallbox angelegt, blendet das E-Auto-Formular die Felder „Heim: PV"/„Heim: Netz" aus — sie werden an der Wallbox erfasst. Ohne Wallbox (Schuko/Steckerlader) bleibt das E-Auto die Quelle. So kann derselbe Stromfluss nicht aus zwei Quellen widersprüchlich gepflegt werden. Hintergrund: [Berechnungen §3.4](BERECHNUNGEN.md#34-e-auto-einsparung).

**Werte aus Home Assistant holen:** Neben „Neuer Monat" gibt es „Aus HA laden". Bei einem **neuen** Monat werden die Werte direkt ins Formular übernommen; bei einem **existierenden** Monat zeigt ein Vergleichs-Modal die Unterschiede (Vorhanden / HA-Statistik / Diff, farbkodiert ab 10 %) mit „HA-Werte übernehmen" oder „Abbrechen". Bei E-Auto- bzw. WP-Komponenten schlägt eedc den Ø Benzin- bzw. Gaspreis vor.

**Wetter-Autofill:** „Wetter abrufen" füllt Globalstrahlung und Sonnenstunden (Open-Meteo historisch bzw. PVGIS TMY).

**Ø Benzinpreis kommt von selbst.** eedc holt den Monatsdurchschnitt täglich aus dem EU Weekly Oil Bulletin und trägt ihn in jeden Monat ohne Preis nach — auch rückwirkend, auch für importierte Monate; du musst dafür nichts tun. Bleibt doch einmal ein Monat offen, meldet es der **Daten-Checker** unter *Vergleichspreise – Ø Benzinpreis* und stellt „Vergleichspreise nachpflegen" daneben. *(Bis v4.0.15 stand hier ein eigener Knopf unter dem Monatsdaten-Block; er ist mit der V4-Oberfläche entfallen — diese Zeile beschrieb ihn danach noch, obwohl es ihn nicht mehr gab.)*

### 5.2 Energieprofil-Pflege

Diese Kachel enthält **nur die Pflege-Funktionen** des Energieprofils; die **Anzeige** (Tagesdetail, Monatsanalysen, Prognose) ist in die Cockpit-Achsen umgezogen (siehe [Teil II](HANDBUCH_BEDIENUNG.md#2-cockpit--die-zeit-achse)).

- **Datenbestand-Kacheln** je Anlage: Stundenwerte, Tagessummen, Monatswerte (Anzahl + Zeitraum) und Abdeckung in %.
- **„Lücken aus HA-LTS nachfüllen" (Vollbackfill):** liest historische Snapshots aus HA und ergänzt **nur fehlende** Tage. **Bestehende Tage bleiben unverändert** — es gibt bewusst keinen Overwrite-Modus. Sinnvoll nach Erstinstallation, längerem Stillstand oder einer Datenquellen-Änderung.
- **„Kraftstoffpreise nachpflegen":** trägt fehlende Benzin-/Dieselpreise (EU Weekly Oil Bulletin) für die E-Auto-Ersparnis nach; strikt additiv, mehrfach gefahrlos.
- **Energieprofil-Daten löschen:** anlage-spezifisch (Monatsdaten bleiben erhalten; der Scheduler baut die Tage danach neu auf).
- **Einen Monat löschen:** nimmt den Monat **ganz** — die Zählerwerte und die Messwerte aller Komponenten desselben Monats. Der Dialog nennt vorher, welche Komponenten betroffen sind. ⚠ **Bis v4.0.13 war das teilbar** und die Voreinstellung schonte die Gerätewerte; gemeint war eine Vorsicht, herausgekommen ist ein Monat, der in keiner Liste mehr auftauchte und trotzdem jeden erneuten Import abwies. Einspeisung und Netzbezug sind Pflichtfelder eines Monats — eine Hälfte allein zu löschen ergibt keinen Zustand, den eine Auswertung darstellen könnte.
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
- **Günstig-Schwelle:** Eine Stunde gilt als „günstig", wenn ihr Börsenpreis mindestens den eingestellten Prozentsatz unter dem Tagesschnitt ohne die 3 teuersten Stunden liegt („optimierter Ø"). Der Prozentsatz ist je Anlage einstellbar (0–50 %, Standard 10 %); bei **0 %** liegt die Schwelle genau **auf** dem Ø — günstig ist dann alles darunter. Der **Rang** (`eedc_preis_rang`) ist davon getrennt: er nennt die fünf billigsten Stunden je Tag-/Nacht-Fenster und ist deshalb bei 5 gedeckelt, die **Anzahl** günstiger Stunden ist es seit v4.0.10 nicht mehr. eedc liefert nur diese Trigger-Werte — die Lade-/Entlade-Strategie baust du in deinen HA-Automationen.
- **Alternative REST-API:** Statt MQTT kannst du die Sensoren auch per REST-Sensor aus `…/api/ha/export/sensors/{id}` in HA ziehen (YAML-Beispiel im Block). **Beide Wege liefern dieselbe Zahl** — wie viele Nachkommastellen sie trägt, hängt an der Größenart (kWh ganzzahlig, Geld auf Cent, Prozent auf eine Stelle; die PV-Prognose-Sensoren tragen eine Nachkommastelle); Einzelheiten in der [Sensor-Referenz §11](SENSOR-REFERENZ.md).

> #### Zu viele Entitäten? Wähl sie in eedc ab
>
> In der Sensorliste hat jede Zeile ein Häkchen, jede Kategorie ein Sammel-Häkchen. Nimm das Häkchen weg, und dieser Sensor geht nicht mehr nach Home Assistant. **Voreingestellt sind alle an** — was du abwählst, ist deine Entscheidung, nicht unsere Voreinstellung.
>
> **Warum die Abwahl hier sitzt und nicht in Home Assistant:** HA kann eine Entität deaktivieren oder löschen, aber ihr Eintrag in der Registry bleibt bestehen — bei der nächsten Auto-Discovery ist sie wieder da. Abwählen lässt sie sich deshalb nur dort, wo sie herkommt.
>
> **Was beim Abwählen passiert:** eedc nimmt seine eigenen MQTT-Nachrichten zurück — den Auto-Discovery-Eintrag sowie den zuletzt gesendeten Wert und seine Attribute. Ohne diesen Schritt käme der Sensor beim nächsten Neustart von Home Assistant zurück, weil der Broker die Nachricht festhält und jedem neuen Abonnenten erneut zustellt. **Die bisherigen Daten dieses Sensors in Home Assistant und auf dem Broker sind damit verloren**; eedc fragt vorher nach und sagt es. Wählst du ihn später wieder an, wird er neu angelegt — ohne seine alte Historie.
>
> **In Home Assistant selbst ändert eedc nichts.** Mögliche Reste dort räumst du nach Bedarf selbst weg. Deine Daten **in eedc** bleiben in jedem Fall unberührt: es geht ausschließlich um die Weitergabe.
>
> **Sensoren ohne Wert** stehen mit „—" in der Liste. Sie sind heute nicht in Home Assistant, lassen sich aber vorab abwählen — dann erscheinen sie auch nicht, sobald sie einen Wert bekommen.
>
> Wer die Werte lieber behalten, aber nicht aufzeichnen will, kann sie in HA weiterhin per `recorder:`-`exclude` von der Aufzeichnung ausnehmen (aktuelle Werte bleiben sichtbar, keine DB-Historie).

> **„Sensoren entfernen" nimmt alles zurück.** Der rote Knopf entfernt sämtliche eedc-Sensoren dieser Anlage von Home Assistant und vom Broker — die anlagenweiten **und** die je Komponente, jeweils mit Wert und Attributen. Auch hier wird vorher gefragt. Mit **Sensoren publizieren** oder beim nächsten automatischen Lauf kommen sie neu — ohne ihre alte Historie.
>
> ⚠ **Bis August 2026 räumte dieser Knopf unvollständig:** Er entfernte 34 der 44 anlagenweiten Sensoren und keinen einzigen der gerätebezogenen — meldete aber Erfolg. Wer aufgeräumt hatte, behielt den Rest und hielt ihn für gelöscht.

**Startwerte:** Damit die Monatswert-Berechnung stimmt, müssen einmalig die Zählerstände vom Monatsanfang als Startwerte gesetzt sein — entweder aus der HA-Statistik geladen oder direkt an den `number.eedc_…_start`-Entities in Home Assistant. Erscheinen Entities doppelt (`_2`-Suffix), lösche die alten Discovery-Topics unter `homeassistant/number/eedc_…` bzw. `homeassistant/sensor/eedc_…` (z. B. per MQTT Explorer) und speichere den Export erneut.

### 6.4 Statistik-Import

*(Braucht eine **verbundene** Home-Assistant-Instanz — als Add-on oder über einen langlebigen Zugriffstoken. Bis August 2026 war die Fläche irrtümlich dem Add-on vorbehalten, obwohl der Voraussetzungs-Kasten unten den Token-Weg schon nannte.)* Importiert **alle historischen Monatsdaten seit Anlagen-Installation** aus der HA-Langzeitstatistik — nützlich bei Neuinstallation, zum Nachbefüllen oder beim Umstieg von manueller auf automatische Erfassung.

**Ablauf (Assistent):** Quelle/Anlage wählen → Zeitraum festlegen → Vorschau laden → Monate auswählen → importieren. Die Vorschau markiert je Monat:

- **Grün** — neuer Monat (standardmäßig ausgewählt).
- **Grau** — bereits ausgefüllt (nicht ausgewählt).
- **Amber** — Konflikt: HA-Werte weichen ab (nicht ausgewählt).

Jeder Monat ist einzeln per Checkbox wählbar — so bleiben manuell erfasste Daten geschützt.

> **Voraussetzungen:** zugeordnete HA-Sensoren (siehe [Datenquellen](#7-datenquellen--feld-zentrische-zuordnung)) und Sensoren, die in der HA-Langzeitstatistik geführt werden. Den **Zugang zur Statistik** hat eedc auf drei Wegen, und einer genügt: über die verbundene Home-Assistant-Instanz (Add-on oder Long-Lived-Token — **ohne** jede weitere Einrichtung), über das Volume-Mapping `config:ro` auf die Recorder-Datei, oder über `HA_RECORDER_DB_URL` bei MariaDB/MySQL. Wo eine Datenbank erreichbar ist, wird sie bevorzugt; sonst holt eedc dieselben Werte über die HA-API. Bei Tagesreset-Zählern nutzt eedc `MAX(sum) − MIN(sum)` aus HA-Statistics (reset-bereinigt).
>
> **Wie weit zurück?** So weit, wie Home Assistant den Sensor selbst führt — die Langzeitstatistik beginnt mit seiner Einrichtung. Für die Zeit davor gibt es den Datei-Import (CSV/Excel); daran ändert auch der API-Weg nichts.

> **Ohne Zähler-Sensoren entsteht kein vollständiger Monat — und eedc sagt es.** Ein Monat besteht aus der **Zählerzeile** deiner Anlage (Einspeisung, Netzbezug) und den **Messwerten je Komponente**. Sind nur Erzeuger-Sensoren zugeordnet — oder wählst du die Basis-Felder in der Vorschau ab —, kommen die Gerätewerte an, die Zählerzeile entsteht aber nicht. Der Monat taucht dann in keiner Monatsliste auf und fehlt in Autarkie und Community-Vergleich. Der Import nennt die betroffenen Monate nach dem Lauf und sagt, wie du sie vervollständigst; im [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) findest du sie unter „Messwerte ohne Monatszeile" mit einem Link direkt ins Monatsformular.
>
> ⚠ **Bis v4.0.13 legte eedc in diesem Fall eine Zeile mit 0 kWh Einspeisung und 0 kWh Netzbezug an** — eine Messung, die niemand gemessen hatte, und die der Daten-Checker anschließend zu Recht als unplausibel meldete. Jetzt entsteht keine Zeile mehr, wo kein Zählerwert vorliegt. Ein Zähler, der ehrlich 0 meldet (Einspeisung im Dezember), schreibt seinen Monat weiterhin.

> #### „Bestehende Monate überschreiben" — was der Haken tut
>
> **Ohne Haken** ergänzt ein Import nur, was fehlt. Werte, die schon da sind, bleiben unangetastet — egal woher sie kommen.
>
> **Mit Haken** ersetzt der Import auch Werte, die du **von Hand** eingetragen oder korrigiert hast. Bevor er das tut, sagt der Assistent, wie viele es sind und in welchen Monaten, mit Beispielen. Nimmst du den Haken wieder heraus, bleiben sie erhalten.
>
> ⚠ **Bis v4.0.13 war das anders**, und es war ein Fehler: Der Haken ließ manuell gepflegte Werte stehen und meldete das hinterher als „durch manuell gepflegte Werte geschützt". eedc tat damit etwas anderes, als du angekreuzt hattest — und wer einen einmal korrigierten Monat neu importieren wollte, kam nicht mehr durch. Die Schutzregel selbst bleibt richtig und gilt weiter für alles, was **im Hintergrund** schreibt (Sensor-Abrufe, automatische Aggregation): Handarbeit wird von der Maschine nicht überschrieben. Nur dein eigener, ausdrücklicher Klick zählt jetzt als das, was er ist.

### 6.5 Import-Assistenten

Ein Sammel-Einstieg für die einmaligen und wiederkehrenden Importe. Jeder Assistent öffnet als **Overlay** (keine eigene Seite mehr):

- **Portal-Import** und **Cloud-Import** (Hersteller-Cloud-APIs: SolarEdge, Fronius SolarWeb, Huawei FusionSolar, Growatt, Deye/Solarman, EcoFlow, Anker …). Ablauf: Verbinden → Zeitraum → Vorschau → Import; Credentials pro Anlage speicherbar. **Server-Region beachten:** Mehrere Hersteller betreiben getrennte Wolken je Weltregion (Anker, EcoFlow, Sungrow, Huawei, Deye/Solarman) — maßgeblich ist die Adresse, unter der du dich im Hersteller-Portal anmeldest. Ein europäisches Konto existiert auf dem chinesischen Server nicht; passt die Region nicht, scheitert schon der Verbindungstest. Die Fehlermeldung nennt den angesprochenen Server und die Antwort des Herstellers im Klartext.
- **Geräte-Connector** — direkter Abruf lokaler/Cloud-Geräte; kann seine Werte optional als MQTT-Bridge auf eedc-Topics publishen.
- **Eigene Datei / Vorlage (Custom-Import)** — beliebige CSV/JSON mit Spalten-Mapping (Auto-Detect, Einheiten Wh/kWh/MWh, Dezimalzeichen, Datumsspalte, speicherbare Mapping-Vorlagen). Unter jeder zugeordneten Spalte steht, **welche Größe** das gewählte Zielfeld erwartet — bei den Wärmepumpen-Feldern also, ob eine elektrische oder eine thermische Menge gemeint ist. Das ist die Stelle, an der sich *Strom Warmwasser* und *Warmwasser-Wärme* am leichtesten verwechseln lassen.
- **CSV-Import** — eedc-Template mit dynamischen Komponenten-Spalten; Plausibilitätsprüfung (negative Werte, Legacy-Spalten-Mismatch = Abbruch; redundante Legacy-Spalten / unplausible Wetterwerte = Warnung). Duplikate werden überschrieben.

> **Mehrere Wechselrichter, mehrere Cloud-„Stationen" — trotzdem EINE Anlage.** Hersteller-Wolken führen häufig je Wechselrichter eine eigene Station (Solarman tut das). In eedc ist eine Anlage dagegen ein **Standort mit einem Hausanschluss**: Netzbezug, Einspeisung, Eigenverbrauch, Autarkie und Wirtschaftlichkeit gibt es dort nur einmal, und zwei Anlagen für ein Haus würden sie in zwei Hälften zerlegen. Der richtige Aufbau ist **ein Wechselrichter je Gerät**, darunter seine PV-Module und ggf. sein Speicher.
>
> Damit beide Stationen nebeneinander bestehen können, fragt der Cloud-Import in der Vorschau **„Diese Quelle misst"**. Voreingestellt ist *die ganze Anlage* (Gesamtwerte, wie bisher). Wählst du stattdessen einen **Wechselrichter**, dann gilt: die Erträge gehen an **seine** PV-Module und **seinen** Speicher, und ein bereits erfasster Monat blockiert die zweite Quelle nicht mehr. So importierst du Station 1 und Station 2 nacheinander für denselben Zeitraum, ohne dass eine die andere überschreibt.
>
> **Einspeisung und Netzbezug kommen trotzdem an.** Diese beiden Größen misst kein Wechselrichter selbst — er liest sie vom Smartmeter am Hausanschluss oder vom Zähler. Alle Geräte an einem Anschluss melden deshalb **denselben** Wert. eedc übernimmt ihn **einmal** in den Monat; eine zweite Station addiert nichts dazu, sie bestätigt ihn nur. Meldet ein Wechselrichter gar keine Zählerwerte (kein Smartmeter angebunden), überschreibt seine 0 nichts — und wenn zwei Geräte **verschiedene** Zählerstände melden, sagt eedc es, statt still einen davon zu nehmen. Der **Eigenverbrauch** wird beim gerätegebundenen Import nicht übernommen; eedc leitet ihn ohnehin aus Erzeugung, Einspeisung und Netzbezug ab.
>
> **Die Zugangsdaten werden je Gerät gespeichert.** Beim Speichern im letzten Wizard-Schritt geht die gewählte Zuordnung mit; mehrere Konten liegen nebeneinander, statt sich zu überschreiben. Der **Cloud-Abruf im Monatsabschluss** zieht dann **alle** gespeicherten Quellen: jede liefert die Werte ihres Wechselrichters, und ist eine gerade nicht erreichbar, kommen die übrigen trotzdem — die Antwort nennt die fehlende. **Netzbezug und Einspeisung schlägt der Abruf ebenfalls vor**, auch wenn alle deine Quellen einem Gerät zugeordnet sind: eine Quelle **ohne** Zuordnung hat Vorrang, sonst nimmt eedc die erste Station, die den Zähler liest. Weichen zwei Quellen voneinander ab, steht das als Hinweis dabei. Liefert keine deiner Quellen Zählerwerte, bleiben die Felder leer und der Abruf sagt es; sie kommen dann aus dem Zähler bzw. den zugeordneten Sensoren. Ein bereits gespeichertes Konto aus früheren Versionen gilt unverändert für die ganze Anlage — es ist nichts neu einzurichten.

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

- **Ein Block je Investitionstyp** (mit den farbigen Typ-Icons und einer Zusammenfassung wie „3 Geräte · 2 Felder noch ohne Quelle"), dazu ganz oben ein Zusatz-Block **„Anlage / Zähler"** für die Basis-Felder (Einspeisung, Netzbezug, Wetter).
- Darunter je Gerät eine einklappbare Sektion mit einem Rollup-Badge.
- Die Felder je Gerät sind in drei Abschnitte nach Einheit gegliedert: **Energie-Sensoren (kWh)**, **Leistung-Sensoren (W)**, **Sonstige Sensoren** (SoC in %, Temperatur, km, €, Ladevorgänge). Leere Abschnitte entfallen.

### 7.3 Was muss zugeordnet werden — und was nicht?

Nicht jedes Feld braucht eine Quelle. Die Fläche sagt dir bei jedem, woran du bist:

| Darstellung | Bedeutung | Was tun? |
|-------------|-----------|----------|
| roter `*` am Feldnamen | **Pflichtfeld** — ohne diesen Wert fehlt eine Kernauswertung | zuordnen, oder den Wert im Monatsabschluss manuell pflegen |
| roter `*` **und** roter, offener Hinweis | Pflichtfeld **ohne** Quelle, und auch kein Ersatzweg belegt | hier liegt echter Nachholbedarf — der aufgeklappte Hinweis sagt, welcher Sensortyp passt |
| „optional" in grau | schön zu haben, aber nichts hängt daran | leer lassen ist in Ordnung |
| grauer Erklärsatz statt „keine Quelle" | wird **an anderer Stelle** erfasst | nichts tun — die Angabe hier hätte keine Wirkung |

Der Zähler im Block-Kopf („2 Felder noch ohne Quelle") zählt **nur die offenen Pflichtfelder**. Steht dort nichts, ist die Zuordnung fertig — auch wenn einzelne Felder leer sind.

**Wann wird ein Feld „an anderer Stelle erfasst"?** Immer dann, wenn zwei Wege dasselbe abdecken und eedc einen davon als maßgeblich ansieht:

- **PV-Erzeugung und PV-Leistung:** entweder anlagenweit (ein Sensor für alles) **oder** je PV-Modul. Sobald ein Modul einen eigenen Sensor hat, gilt dieser — die anlagenweite Angabe wird dann ignoriert. Wer mehrere Strings getrennt auswerten will, ordnet je Modul zu; wer nur einen Gesamtzähler hat, nutzt das Modul-Feld ebenfalls (bei einem Modul ist beides gleichwertig).
- **Netz-Leistung:** entweder **ein** vorzeichenbehafteter Sensor unter „Netz kombiniert (±)" **oder** „Einspeisung (W)" und „Netzbezug (W)" getrennt. Der Kombi-Sensor wirkt nur, wenn die beiden getrennten Felder leer sind.
- **Heimladung des E-Autos:** hat deine Anlage eine **Wallbox**, ist sie die maßgebliche Quelle — die Felder „Heim: PV" und „Heim: Netz" am Fahrzeug bleiben dann ungenutzt. (Sind sie bei dir noch belegt, weist die Fläche darauf hin und bietet an, sie auf „keine" zu setzen.)

**Manche Felder gibt es hier gar nicht — sie werden ausschließlich von Hand erfasst.** Für sie existiert kein Sensor- und kein Topic-Weg; eine Zuordnung hätte keine Wirkung, würde aber eine Daten-Checker-Meldung auslösen. Sie stehen im Monatsabschluss, im CSV-Import und (wo sinnvoll) als errechneter Vorschlag zur Verfügung. Betroffen sind der **Ø Ladepreis** des Speichers (ct/kWh) und die BKW-eigenen Speicher-Felder *Ladung*/*Entladung*. Liegt heute noch eine Quelle auf so einem Feld, bleibt es sichtbar, damit du sie über **Keine** entfernen kannst.

> **„Ladung" beim Speicher ist die Gesamtmenge.** Das Feld heißt bei Speichern mit Netzladung ausdrücklich **„Ladung (gesamt, inkl. Netz)"** — **„Netzladung"** sagt nur, wie viel *davon* aus dem Netz kam, und ist kein zweiter Summand. Wer nur den PV-Ladezähler auf „Ladung" legt, verliert die Netzladung in der Gesamtmenge und zählt sie zugleich doppelt. Liefert dein Gerät PV- und Netzladung getrennt (z. B. Kostal Plenticore), addierst du beide in Home Assistant zu einem Helfer und ordnest diesen zu.

> **„Keine Quelle" ist kein Fehler.** Alle kWh-Felder lassen sich im Monatsabschluss auch von Hand erfassen — rot heißt „hier fehlt noch etwas", nicht „falsch".

**Jede Feld-Zeile** zeigt: Feldname (+ Einheit), die **aktive Zuordnung** — mit dem **Klarnamen** des Sensors neben der Entity-ID —, den zuletzt **empfangenen Wert** und rechts die Quellen-Wahl. Ein Info-Symbol blendet den Feld-Hinweis aus der Registry ein.

**Quellen-Wahl (Buttons):** Je Feld ist immer genau eine Quelle aktiv (gefüllter Button):

- **HA-Sensor**, **Gateway**, **Inbound** — erscheinen nur, wenn die zugehörige Verbindung besteht (ohne HA-Verbindung kein HA-Button; ohne MQTT-Broker keine Gateway-/Inbound-Buttons). Eine bestehende Zuordnung bleibt sichtbar, auch wenn die Verbindung gerade fehlt.
- **Keine** — der **einzige** Weg, eine Zuordnung wieder zu entfernen.

> **Ein Klick auf die aktive Quelle löscht sie nicht.** Er öffnet die Zuordnung — den Picker mit dem bereits hinterlegten Sensor als Vorauswahl. Bis v4.0.0 bedeutete derselbe Knopf zweierlei (bei inaktiver Quelle „auswählen", bei aktiver „Zuordnung verwerfen", ohne Rückfrage); wer nur nachsehen wollte, welcher Sensor hinterlegt ist, verlor ihn. Entfernt wird ausschließlich über **Keine**.

**Wert-Anzeige:** Ein zugeordnetes Feld ohne empfangenen Wert wird **amber** markiert (Zuordnung + Wert) — so ist ein Quellen-Ausfall sofort sichtbar. Ein grüner Wert bedeutet: Quelle liefert.

**Vorzeichen umkehren (±):** Bei signierten Leistungs-Feldern (W) gibt es ein ±-Symbol direkt am Wert. Manche Sensoren liefern z. B. Einspeisung als negativen Wert — der Schalter kehrt das Vorzeichen um. Er ist **quellen-unabhängig** (sitzt am Wert, gilt für jede Quelle); eedc rechnet intern immer mit positiven Werten.

> **Mobil:** Statt einer Tabelle erscheint pro Feld eine Karte (Feldname + Wert, darunter die Zuordnung, darunter die Quellen als Chip-Reihe).

### 7.4 Eine HA-Entity zuordnen (Picker)

Klick auf **HA-Sensor** öffnet einen Picker mit allen Entities der aktiven HA-Verbindung — durchsuchbar nach Entity-ID oder Name; jede Zeile zeigt Einheit und aktuellen State. Der Picker assistiert beim Wählen:

- **Einheiten-Warnung:** Passt die Sensor-Einheit nicht zur erwarteten Feld-Dimension (z. B. ein kWh-Zähler für ein W-Feld), erscheint ein amber Hinweis an der Zeile — Warnung, keine Sperre.
- **Filter „Nur passende Einheit" (Forum-Wunsch fridolin22):** eine Checkbox über der Liste blendet Sensoren mit abweichender Einheit aus und nennt deren Anzahl. **Standardmäßig aus** — wer keinen passenden Sensor besitzt, soll die vorhandenen sehen und daraus in Home Assistant einen Helfer bauen können. Sensoren **ohne** Einheitsangabe bleiben immer sichtbar.
- **Integrations-Vorschläge (Zuordnungs-Assistenz, #343):** Erkennt eedc eine bekannte Integration (Muster-Match auf die Entity-Liste), erscheint über der Suchliste ein Abschnitt „Vorschläge — Integration erkannt: …" mit den passenden Entities und einem Hinweis-Text, welcher Sensor der richtige ist. Die Vorschläge sind reine **Assistenz** — die Auswahl trifft immer du; die volle Suchliste bleibt sichtbar. Bekannte Fehlgriffe (z. B. ein Zähler, der erst am Session-Ende springt) werden als amber Warnhinweis in der Liste markiert.
- **Takt-Check bei kWh-Zählern:** Wählst du einen Energie-Zähler, prüft eedc einmalig dessen jüngsten Verlauf. Ein Zähler, der sich nur sprunghaft aktualisiert (z. B. erst am Ladeende), erzeugt in Tages-/Live-Kurven Nadeln — eedc warnt dann („Für Monatssummen ok") mit **„Trotzdem übernehmen"** oder „Anderen wählen". Ist HA nicht erreichbar oder gibt es keinen numerischen Verlauf, wird der Check stillschweigend übersprungen (keine Pseudo-Bestätigung).

> **Wissensbasis wächst kuratiert.** Die Integrations-Vorschläge starten bewusst klein (evcc mit belegten Feld-Mustern; go-eCharger/openWB/Keba/Zappi als Erkennung) und werden mit Tester-Wissen erweitert — nichts wird geraten.

### 7.5 Ein MQTT-Topic zuordnen

- **Gateway (Fremd-Topic):** Klick auf **Gateway** öffnet den Topic-Picker mit einer **Broker-Discovery** (`#`-Scan mit Suche) — du wählst ein vorhandenes Topic deines Geräts (Shelly, OpenDTU, Tasmota …), gibst bei JSON-Payloads den Pfad an und optional Faktor/Einheit. eedc übersetzt das auf sein Feld.
- **Inbound (Standard-Topic):** Klick auf **Inbound** setzt direkt das kanonische eedc-Topic (`eedc/{anlage}/…`), auf das du selbst aus deinem Smarthome (HA-Automation, Node-RED, ioBroker, FHEM, openHAB) publishst. Live-Topics speisen das Live-Dashboard, Energy-Topics (monoton steigende Zählerstände) den Monatsabschluss.

> **Topic-Drift:** Kommen in eedc Felder dazu oder wechseln Komponenten-IDs nach einem Re-Import, kann ein statischer Publisher gegen die erwarteten Topics driften. Der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) meldet das in der Kategorie MQTT-Topic-Abdeckung.

**Alle Topics auf einen Blick.** Wer seine Werte aus ioBroker, FHEM, evcc, Node-RED oder einem eigenen Skript schickt, braucht die Topics am Stück statt verstreut unter den einzelnen Feldern. Dafür gibt es am Ende der Datenquellen-Fläche den zugeklappten Block **„MQTT-Topics"**: er listet die Topics **deiner** Anlage — nach Gerät gruppiert, mit Feldname und Einheit — und hat je Zeile einen Kopier-Knopf sowie oben **„Alle kopieren"** für die ganze Liste.

Zwei Dinge dazu, die Zeit sparen:

- **Zuordnen musst du vorher nichts.** eedc holt auf diesen Topics nichts ab, es hört zu: Sobald auf einem Topic ein Wert ankommt, stellt sich das zugehörige Feld von selbst auf *MQTT-Inbound*. Ein Wert je Nachricht, als Zahl.
- **Der Namensteil hinter der Anlagennummer ist optional.** `eedc/1/live/…` wirkt genauso wie `eedc/1_Meine-Anlage/live/…` — praktisch, wenn du die Anlage später umbenennst. Ein eingerichteter Geräte-Connector nutzt intern denselben Weg und schreibt die kurze Form.

### 7.6 Validierung & Probleme je Feld

Zur Zuordnungszeit erkennbare Fehler zeigt eedc **direkt an der Feld-Zeile** — diagnostisch, nie blockierend (rot = Fehler, amber = Warnung):

- **Einheiten-Mismatch** — der zugeordnete HA-Sensor hat eine andere Dimension als das Feld (kWh-Sensor in W-Feld). Nur bei HA-Feldern prüfbar (MQTT-Topics tragen keine Einheit-Metadaten).
- **Kein `state_class` / keine Langzeitstatistik** — der HA-Sensor liefert für kWh-Felder still keine History (keine Zeitmaschine). Für reine Live-/Counter-Felder unproblematisch.
- **Aggregat-Redundanz** — ist eine Gesamt-Zuordnung wirkungslos, weil die Einzelwerte sie ersetzen, bietet ein amber Hinweis inline **„auf keine setzen"** an (kein automatischer Eingriff). Wann das gilt, hängt am Feld:
  - **PV gesamt (W)** und **Kombi-Netzsensor** — sobald **eine** Einzelkomponente zugeordnet ist. Das Live-Dashboard nutzt dann ausschließlich die Einzelwerte.
  - **PV gesamt (kWh)** — erst wenn **jede** PV-Quelle (PV-Module und Balkonkraftwerke) einen eigenen kWh-Zähler hat. Vorher füllt der Gesamtzähler die Lücken der Module ohne eigenen Wert und ist damit die Quelle der Monatswerte; ihn dort abzuschalten würde die Anlagen-Erzeugung auf 0 setzen. Bei Teil-Abdeckung schweigt der Hinweis deshalb bewusst.
- **Sensor-Doppelmapping** — dieselbe HA-Entity in zwei Feldern → Doppelzählungs-Gefahr; beide betroffenen Felder werden benannt.

Die datenbasierten (rückblickenden) Prüfungen — Über-Erfassung, Datenquellen-Drift, Vorzeichen-Historie — bleiben im [Daten-Checker](HANDBUCH_DATEN_CHECKER.md).

### 7.7 Eine geänderte Zuordnung gilt ab jetzt — nicht rückwirkend

Ordnest du einem Feld eine andere Quelle zu (oder kehrst ein Vorzeichen um), gilt das **ab diesem Moment**. Deine bereits gespeicherten Tages- und Stundenwerte bleiben, wie sie gerechnet wurden: sie tragen die Zuordnung, die zum Zeitpunkt ihrer Berechnung galt. Das betrifft **jede** Art von Zuordnung — Zähler, Leistung, Ladestand und Strompreis fließen alle in die gespeicherten Tageswerte ein.

Praktisch heißt das: Wer eine neue Komponente ergänzt (zweiter Wechselrichter, weitere Module, ein Speicher), findet sie in Live und ab dem laufenden Tag überall wieder — in der Vergangenheit aber nicht.

**eedc sagt es dir.** Nach einer Änderung erscheint oben auf der Datenquellen-Fläche ein Hinweis mit den geänderten Feldern und dem Datum, ab dem die Werte neu sind. Er blockiert nichts und bleibt stehen, bis du ihn mit **„Verstanden"** quittierst — auch über einen Neustart hinweg, denn die Frage stellt sich oft erst Tage später.

**Wenn du die Vergangenheit nachziehen willst,** führt der Knopf **„Zur Reparatur-Werkbank"** direkt dorthin: *Einstellungen → Daten → Energieprofil-Pflege → Zeitraum neu aggregieren*, in Blöcken von bis zu 31 Tagen je Lauf. Deine **Monatsdaten bleiben unberührt** — neu gerechnet werden nur die Tages- und Stundenwerte.

> **Es passiert nichts von allein.** eedc rechnet die Historie nicht selbsttätig neu — das kann Stunden dauern und ist selten gewollt. Und die Quittung heißt „zur Kenntnis genommen", nicht „erledigt": ob und wie weit du nachgezogen hast, weißt nur du.

> ⚑ **Eine Ausnahme, und die ist gewollt: der laufende Tag.** Er wird alle 15 Minuten vollständig neu gerechnet — eine Zuordnung, die du um 22 Uhr anlegst, wirkt dort also binnen einer Viertelstunde für **den ganzen Tag** zurück, nicht erst ab 22 Uhr. Das ist der Grund, warum dieser Abschnitt „nicht rückwirkend" heißt und für heute trotzdem etwas anderes gilt.

> **Für die Zeit vor eedc gilt das nicht.** Wo keine Sensordaten in Home Assistant liegen (etwa Monate, die du aus einer Hersteller-Cloud importiert hast), findet ein neuer Lauf nichts — dort sind die Monatswerte die Datenlage, und die genügen für Cockpit, Auswertungen und Jahresbericht.

### 7.8 Voraussetzung: die Verbindungen

Damit HA-Sensoren bzw. MQTT-Topics überhaupt wählbar sind, muss die jeweilige Verbindung stehen — MQTT-Broker und HA-Verbindung richtest du unter [Integration](#6-integration) ein. Änderst du dort etwas, blenden sich die Quellen-Buttons in der Datenquellen-Fläche sofort passend ein oder aus.

### 7.9 Was aus den alten Assistenten wurde

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

Für die E-Auto-Ersparnis nutzt eedc echte monatliche Benzinpreise aus dem EU Weekly Oil Bulletin (History seit 2005). Der Backfill (Tages-/Monatsebene, siehe [§5.1](#51-monatsdaten--monatsabschluss)/[§5.2](#52-energieprofil-pflege)) setzt nur Werte, wo noch keiner vorhanden ist, und kann gefahrlos mehrfach laufen; ein Scheduler-Job (**täglich 06:00**, dazu ein Lauf kurz nach jedem Start) befüllt neue Tage und Monate automatisch. Bleibt ein Monat trotzdem ohne Preis, meldet das der Daten-Checker mit dem Nachpflegen-Knopf daneben.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
