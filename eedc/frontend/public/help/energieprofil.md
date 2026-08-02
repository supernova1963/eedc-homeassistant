
# eedc Handbuch — Energieprofil

**Version 4.0** | Stand: 2026-07-25

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Prognosen](HANDBUCH_PROGNOSEN.md) | [Berechnungen & Kennzahlen](BERECHNUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was ist das Energieprofil?](#1-was-ist-das-energieprofil)
2. [Wo du das Energieprofil in der App findest](#2-wo-du-das-energieprofil-in-der-app-findest)
3. [Voraussetzungen: die richtigen Datenquellen](#3-voraussetzungen-die-richtigen-datenquellen)
4. [Reparatur & Pflege](#4-reparatur--pflege)
5. [Bekannte Fehlerbilder](#5-bekannte-fehlerbilder)
6. [Beziehung zu anderen Auswertungen](#6-beziehung-zu-anderen-auswertungen)

---

## 1. Was ist das Energieprofil?

Das **Energieprofil** ist die feinste zeitliche Auflösung deiner Anlagendaten in eedc: **eine Zeile pro Stunde** und daraus abgeleitet **eine Zusammenfassung pro Tag**. Während das Cockpit auf Monats- und Jahresebene mit Summen arbeitet, hält das Energieprofil fest, *wann an einem Tag* welche Energie geflossen ist — Stunde für Stunde, getrennt nach PV-Erzeugung, Netzbezug, Einspeisung, Batterie, Wärmepumpe, Wallbox und sonstigen Verbrauchern.

Damit ist das Energieprofil die **Datengrundlage fast aller anderen Auswertungen**: Stundenwerte werden zu Tagessummen verdichtet, Tagessummen zu Monatswerten. Wenn im Cockpit oder in den Auswertungen etwas „komisch" aussieht, liegt die Ursache fast immer eine Ebene tiefer — im Energieprofil.

> **Kernidee:** eedc rechnet kWh **als Differenz kumulativer Zählerstände** (wie das HA-Energie-Dashboard), **nicht** durch Aufsummieren von Leistungsmesswerten. Das ist der wichtigste Unterschied, um die Abhängigkeiten und Fehlerbilder dieses Bereichs zu verstehen. Wie eedc die Werte erhebt und verdichtet, steht ausführlich im Hintergrund-Kapitel [Einstellungen → Hintergrund: Energieprofile & Snapshot-Architektur](HANDBUCH_EINSTELLUNGEN.md#9-hintergrund-energieprofile--snapshot-architektur).

---

## 2. Wo du das Energieprofil in der App findest

Früher hatte das Energieprofil einen **eigenen Tab** „Auswertung → Energieprofil (Beta)" mit vier Sub-Reitern (Tagesdetail, Wochenvergleich, Monat, Prognose). In der neuen Oberfläche gibt es diesen Tab nicht mehr. Stattdessen sind seine Darstellungen **dorthin gewandert, wo sie thematisch hingehören** — und nach einem einfachen Grundsatz getrennt:

> **Anzeige ≠ Pflege.** Die *Auswertung* der Stunden- und Tageswerte findest du im **Cockpit** (nach Zeit-Ebene sortiert); das *Pflegen und Reparieren* der Daten liegt gebündelt in den **Einstellungen**.

| Früher (Sub-Tab „Energieprofil (Beta)") | Jetzt |
|---|---|
| **Tagesdetail** (Butterfly-Chart + Stundentabelle) | **Cockpit → Tag** |
| **Monat** (Monats-Reichdarstellungen) | **Cockpit → Monat** |
| **Prognose** (Tagesprognose) | **Cockpit → Aussicht** |
| **Tages-Tabelle** (eine Zeile pro Tag, viele Spalten) | **Auswertungen → Tabelle** |
| **Datenverwaltung / Reparatur** | **Einstellungen → Daten → Energieprofil-Pflege** |
| **Wochenvergleich** | *entfällt* (siehe Hinweis unten) |

### 2.1 Tagesdetail → Cockpit → Tag

Der einzelne Kalendertag mit Stunden-Auflösung. Die **Tag**-Sicht zeigt den Stunden-Verlauf von Erzeugung, Verbrauch und Speicher, eine Tagesbilanz als Kennzahl-Strip und die Stundenwert-Detailtabelle. Datum-Navigation über die Zeit-Leiste. Details: [Bedienung → Cockpit → Tag](HANDBUCH_BEDIENUNG.md#22-tag).

### 2.2 Monats-Analysen → Cockpit → Monat

Die reichhaltigen Monats-Darstellungen des alten Energieprofils sind in die **Monat**-Sicht des Cockpits gehoben — reuse aus demselben Stunden-Bestand, ohne neuen Rechenweg. Neben Kennzahl-Strip und Energiebilanz zeigt die Monat-Sicht:

- **Performance Ratio (Ø Monat)** — als Kennzahl.
- **Erzeugung & Verbrauch nach Kategorie** — eine kompakte Anteils-Leiste über alle Erzeuger- und Verbraucher-Kategorien.
- **Typisches Tagesprofil** — der stündliche Mittelwert von PV und Verbrauch über die Tage des Monats.
- **Top-Stunden** — die stärksten Netzbezugs- und Einspeise-Stunden (Datum + Uhrzeit), nützlich zur Tarif-Optimierung.
- **§51-EEG-Negativpreis** — Stunden mit negativem Börsenpreis, die dabei eingespeiste Energie und der Ø-Börsenpreis.

Details: [Bedienung → Cockpit → Monat](HANDBUCH_BEDIENUNG.md#23-monat).

### 2.3 Tages-Prognose → Cockpit → Aussicht

Die stündliche Tagesprognose (PV vs. Verbrauch vs. Netto mit Ladezustands-Overlay) und die zugehörige Prognose-Stundentabelle liegen in der **Aussicht**. eedc wählt die Prognosebasis (gleicher Wochentag/Tagestyp) und die Wetterquelle automatisch; die gewählte Basis steht als Beschriftung an der Karte. Details: [Bedienung → Cockpit → Aussicht](HANDBUCH_BEDIENUNG.md#25-aussicht) und [Handbuch Prognosen](HANDBUCH_PROGNOSEN.md).

### 2.4 Roh-Tabelle / Tageswerte → Auswertungen → Tabelle

Die tabellarische **Zeile-pro-Tag**-Sicht mit Spalten-Selektor, Monats-Summen-/Durchschnittszeile und den Detail-Spalten (Tages-kWh je Gerät, Peaks, Performance Ratio, Börsenpreis-Spalten …) ist in die **Werte-Werkbank** unter [Auswertungen → Tabelle](HANDBUCH_BEDIENUNG.md#45-tabelle-werte-werkbank) gezogen. Dort wählst du Granularität (Tag/Monat) und Spalten und exportierst bei Bedarf.

> **Vorzeichen der Geräte-Spalten:** positiv = Erzeugung, negativ = Verbrauch. Die Spalte „Stunden verfügbar" (z. B. `20/24`) bleibt die wichtigste Diagnose: zeigt sie dauerhaft weniger als 24, fehlen dir Stunden — ein Hinweis auf Snapshot-Lücken oder ein Datenquellen-Problem.

### 2.5 Pflege → Einstellungen → Daten

Datenbestand-Status, Lücken-Nachfüllen (Vollbackfill), Kraftstoffpreis-Backfill und die **Reparatur-Werkbank** liegen unter **Einstellungen → Daten → Energieprofil-Pflege**. Siehe [§4](#4-reparatur--pflege).

> **Aus der alten „Energieprofil (Beta)"-Sicht bewusst nicht übernommen:**
> - der **Wochentag-Wochenvergleich** *entfällt* — der Rückblick „Ø gleicher Wochentag" in der Tag-Sicht deckt den Kern.
> - die **Tag×Stunde-Heatmap** ist vorerst nicht dabei und **kommt später neu gestaltet zurück** (Cockpit → Monat).

---

## 3. Voraussetzungen: die richtigen Datenquellen

Das Energieprofil rechnet nur so gut wie seine zugeordneten Datenquellen. Die Zuordnung pflegst du feld-zentrisch unter **Einstellungen → Datenquellen** ([Teil III §7](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung)). Vier Punkte sind entscheidend:

- **Kumulative kWh-Zähler, keine Leistungssensoren.** Der Aggregator liest ausschließlich fortlaufende kWh-Zählerstände. Ein **Leistungssensor (W/kW)** in einem kWh-Feld liefert physikalisch unmögliche Stundenwerte. Basis der Anlage sind `einspeisung` **und** `netzbezug` — fehlt einer, bleibt der bilanziell gerechnete Gesamtverbrauch leer.
- **`state_class` muss gesetzt sein — HA-LTS ist keine Zeitmaschine.** Home Assistant legt Long-Term-Statistics für einen Sensor **erst ab dem Zeitpunkt** an, an dem dessen `state_class` gesetzt ist. Vorher existieren keine Daten; kein Backfill kann nachholen, was HA nie aufgezeichnet hat.
- **Anschaffungs- und Stilllegungsdatum.** Eine Komponente fließt nur an den Tagen in die Aggregation ein, an denen sie laut Datum aktiv war (gepflegt unter [Einstellungen → Komponenten](HANDBUCH_EINSTELLUNGEN.md#3-komponenten)).
- **PV-Leistung (kWp) und Koordinaten.** `leistung_kwp` ist Voraussetzung für die Performance Ratio und den Ausreißer-Schutz; Standort-Koordinaten brauchst du für Wetter-IST und Strahlungswerte.

> Wie eedc daraus Stunden-, Tages- und Monatswerte macht (Snapshot-Job, Backward-Slot, NULL-Semantik, Zähler-Resets, Ausreißer-Schutz), steht im Hintergrund-Kapitel [Einstellungen → §9](HANDBUCH_EINSTELLUNGEN.md#9-hintergrund-energieprofile--snapshot-architektur). Der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) warnt aktiv, wenn eine dieser Voraussetzungen fehlt.

---

## 4. Reparatur & Pflege

Alle Pflege-Funktionen liegen unter **Einstellungen → Daten → Energieprofil-Pflege**. eedc bietet bewusst **keinen** großen „Alles-heilen"-Knopf, sondern gezielte, nachvollziehbare Werkzeuge mit Vorschau — lieber einen konkreten Tag prüfen und reparieren als blind alles überschreiben.

Die **Reparatur-Werkbank** bündelt die Operationen mit ihren echten Bezeichnungen:

- **„Tag neu aggregieren"** — einen einzelnen Tag neu berechnen. Über eine **Alt/Neu-Vorschau** entscheidest du zwischen „aus HA neu laden + neu rechnen" (holt die Snapshots frisch) und „nur neu rechnen" (aus den vorhandenen Snapshots). eedc meldet danach, wie viele **Stunden mit echten Messdaten** verarbeitet wurden — ein ehrlicher Erfolgsindikator, kein pauschales „erledigt".
- **„Mehrere Tage neu aggregieren"** — ein Datumsbereich (max. 31 Tage). Die Tage werden einzeln verarbeitet und festgeschrieben; ein Abbruch lässt bereits reparierte Tage stehen.

> **Die Reparatur sagt, was sie getan hat — je Komponente.** Nach einem Tages-Lauf steht in der Rückmeldung, für welche der zugeordneten Komponenten ein Wert geschrieben wurde und welche leer geblieben sind („2 von 3 Komponenten neu geschrieben — ohne Wert blieb: Wärmepumpe"). Konnte der Lauf für **keine** Komponente etwas holen, erscheint das als **Hinweis** statt als Erfolg, mit der häufigsten Ursache daneben (kein Leistungssensor zugeordnet, oder die HA-Historie reicht nicht so weit zurück). Vorher meldete der Einzeltag-Lauf immer „OK" und zeigte nur die PV-Tagessumme vor/nach — eine Komponente ohne geschriebenen Wert war davon nicht zu unterscheiden. Der Bereichs-Lauf macht dieselbe Aussage je Tag.

> **Wie weit die Reparatur zurückreicht.** Sie holt die Stunden-Leistungskurve zuerst aus der HA-**Historie** — die hebt Home Assistant standardmäßig nur rund **zehn Tage** auf. Findet sie dort nichts, greift sie auf die **Langzeitstatistik** zurück, denselben Weg wie „Lücken aus HA-LTS nachfüllen". Damit reicht die Tagesreparatur so weit zurück wie deine LTS-Daten, nicht nur zehn Tage (bis v4.0.5 stieg sie für ältere Tage mit „keine Live-/MQTT-Daten gefunden" aus, obwohl der Daten-Checker 90 Tage weit prüft). Geht es trotzdem nicht, nennt die Meldung den Grund: **keine Leistungs-Zuordnung** (Handgriff: [Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung)), **HA nicht erreichbar** oder **HA hat für den Tag selbst nichts** — Letzteres ist keine Fehlfunktion und lässt sich nicht füllen.
- **„Lücken aus HA-LTS nachfüllen"** (Vollbackfill) — ergänzt **nur fehlende** Tage aus den HA-Long-Term-Statistics. **Bestehende Tage bleiben unverändert** — es gibt bewusst keinen Overwrite-Modus. Sinnvoll nach Erstinstallation, längerem Stillstand oder einer Datenquellen-Änderung.
- **„Kraftstoffpreise nachpflegen"** — trägt fehlende Benzin-/Dieselpreise (EU Weekly Oil Bulletin) für die E-Auto-Ersparnis nach; strikt additiv.

Der **Gefahrenbereich** „Energieprofil-Daten löschen" entfernt Stunden- und Tageswerte (Monatsdaten bleiben erhalten); der Scheduler baut die Tage anschließend neu auf. Nur nutzen, wenn ein Neuaufbau wirklich gewollt ist.

Vollständige Beschreibung der Pflege-Kachel: [Einstellungen → §5.2 Energieprofil-Pflege](HANDBUCH_EINSTELLUNGEN.md#52-energieprofil-pflege).

<!-- [T20-Review] Eingehender Querverweis: HANDBUCH_PROGNOSEN.md verlinkt aktuell auf den alten
     Anker `HANDBUCH_ENERGIEPROFIL.md#6-die-reparatur-werkzeuge`. Der existiert in dieser V4-Fassung
     nicht mehr (neuer Anker: `#4-reparatur--pflege`). Beim R2a-Umschreiben von HANDBUCH_PROGNOSEN
     den Link auf `#4-reparatur--pflege` (oder direkt auf HANDBUCH_EINSTELLUNGEN.md#52-energieprofil-pflege)
     repointen. Beide Dateien fahren im selben Flip-Push-Zug aus → kein Live-Bruch, solange gemeinsam
     gepusht. -->

---

## 5. Bekannte Fehlerbilder

| Symptom | Ursache | Was tun |
|---------|---------|---------|
| **Tage/Stunden fehlen, „X/24"** | Sensor hatte (noch) keine `state_class`; HA-LTS reicht nicht so weit zurück | `state_class` setzen — danach läuft die Erfassung ab *jetzt*. Rückwirkend ist nichts zu retten. |
| **Verbrauchsspalte leer** | `einspeisung` oder `netzbezug` nicht zugeordnet | Beide Basis-Felder unter [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) ergänzen. |
| **Unmöglich hohe Stundenwerte** | Leistungssensor (W/kW) in kWh-Feld, oder Zähler-Sprung nach HA-Neustart | Richtigen kumulativen kWh-Zähler zuordnen; betroffenen Tag neu aggregieren. eedc kappt zwar, aber die Zuordnung ist die eigentliche Korrektur. |
| **HA und eedc zeigen leicht andere Tageswerte** | Drift zwischen den beiden Aggregator-Pfaden oder Slot-Versatz | Meist harmlos; bei größerer Abweichung Tag neu aggregieren. Der Daten-Checker protokolliert auffällige Tage. |
| **PV doppelt gezählt** | Gerät unter zwei Komponenten-Schlüsseln geschrieben (Altbestand) | In aktuellen Versionen behoben (ein eindeutiger Schreiber pro Komponente). Bei Altbeständen betroffene Tage neu aggregieren. |
| **E-Auto + Wallbox doppelt** | Die Wallbox misst bereits die Ladung des E-Autos | E-Auto als „Kind" der Wallbox verknüpfen (Parent-Child, [Einstellungen → §3.1](HANDBUCH_EINSTELLUNGEN.md#31-parent-child-beziehungen)) — dann wird es nicht zusätzlich gezählt. |

> **Der Daten-Checker als Frühwarnsystem.** Mehrere Kategorien beziehen sich direkt aufs Energieprofil (Zähler-Abdeckung, Plausibilität der Stundenwerte, Datenquelle-Drift im HA-Betrieb) und verlinken bei einem Befund direkt zum betroffenen Tag mit „Tag neu aggregieren". Details: [Handbuch Daten-Checker](HANDBUCH_DATEN_CHECKER.md).

---

## 6. Beziehung zu anderen Auswertungen

Das Energieprofil ist die Wurzel des Datenbaums — stimmt es, stimmen die darüberliegenden Ebenen meist von selbst:

- **→ Cockpit → Monat:** Autarkie, Eigenverbrauch, Grundbedarf, Batterie-Wirkungsgrad, Performance Ratio, Kategorien-Anteile, Top-Stunden und §51-Negativpreis werden direkt aus den Stunden-/Tageswerten des Monats gebaut.
- **→ Monatsabschluss (Rollup):** Aus den Tageszusammenfassungen entstehen **fünf** aggregierte Monatsfelder (Überschuss, Defizit, Batterie-Vollzyklen, Performance Ratio, Peak Netzbezug). Die komponentenweisen kWh werden **nicht** in die `Monatsdaten` gespiegelt — die gerätbezogenen Monatswerte für Cockpit und ROI kommen aus einer **getrennten** Datenquelle (`InvestitionMonatsdaten`). Grundsatz: `Monatsdaten` = Zählerwerte, `InvestitionMonatsdaten` = Komponenten-Details.
- **→ Prognosen / Genauigkeits-Tracking:** Die **IST-Werte** für den Prognosen-Vergleich und den Lernfaktor stammen aus dem Energieprofil (PV-Tagessumme). Fehlt hier die Zähler-Abdeckung, kann eedc keine Prognose-Genauigkeit berechnen. Siehe [Handbuch Prognosen](HANDBUCH_PROGNOSEN.md).

> **Merksatz:** Bei Auffälligkeiten zuerst hier schauen — und bei Bedarf gezielt einen Tag neu aggregieren, statt an den abgeleiteten Werten zu drehen. Die zugrunde liegende Rechen-Mechanik (Snapshot-Architektur, Backward-Slot, Aggregationsregel) ist im Hintergrund-Kapitel [Einstellungen → §9](HANDBUCH_EINSTELLUNGEN.md#9-hintergrund-energieprofile--snapshot-architektur) und in den [Berechnungen](BERECHNUNGEN.md) beschrieben.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
