
# eedc Handbuch — Energieprofil

**Version 3.34.1** | Stand: Mai 2026

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen & Sensormapping](HANDBUCH_EINSTELLUNGEN.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Prognosen](HANDBUCH_PROGNOSEN.md) | [Berechnungen & Kennzahlen](BERECHNUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was ist das Energieprofil?](#1-was-ist-das-energieprofil)
2. [Die zwei Orte in der App](#2-die-zwei-orte-in-der-app)
3. [Woher die Daten kommen — die Pipeline](#3-woher-die-daten-kommen--die-pipeline)
4. [Was du konfigurieren musst (Abhängigkeiten)](#4-was-du-konfigurieren-musst-abhaengigkeiten)
5. [Wie aus Zählern Stunden- und Tageswerte werden](#5-wie-aus-zaehlern-stunden--und-tageswerte-werden)
6. [Die Reparatur-Werkzeuge](#6-die-reparatur-werkzeuge)
7. [Bekannte Probleme & Fehlerbilder](#7-bekannte-probleme--fehlerbilder)
8. [Beziehung zu anderen Auswertungen](#8-beziehung-zu-anderen-auswertungen)

---

## 1. Was ist das Energieprofil?

Das **Energieprofil** ist die feinste zeitliche Auflösung deiner Anlagendaten in eedc: **eine Zeile pro Stunde** und daraus abgeleitet **eine Zusammenfassung pro Tag**. Während Cockpit und Monatsbericht mit Monatssummen arbeiten, zeigt das Energieprofil, *wann an einem Tag* welche Energie geflossen ist — Stunde für Stunde, getrennt nach PV-Erzeugung, Netzbezug, Einspeisung, Batterie, Wärmepumpe, Wallbox und sonstigen Verbrauchern.

Das Energieprofil ist damit die **Datengrundlage fast aller anderen Auswertungen**: Tages- und Stundenwerte werden zu Tagessummen verdichtet, Tagessummen zu Monatswerten. Wenn im Cockpit oder Monatsbericht etwas „komisch" aussieht, liegt die Ursache fast immer eine Ebene tiefer — im Energieprofil.

> **Kernidee:** eedc rechnet kWh **als Differenz kumulativer Zählerstände** (wie das HA-Energie-Dashboard), **nicht** durch Aufsummieren von Leistungsmesswerten. Das ist der wichtigste Unterschied, den man verstehen muss, um die Abhängigkeiten und Fehlerbilder dieses Bereichs zu deuten (siehe [§3](#3-woher-die-daten-kommen--die-pipeline)).

---

## 2. Die zwei Orte in der App

Das Energieprofil erscheint an **zwei Stellen** mit unterschiedlichem Zweck. Das verwirrt anfangs — die Trennung ist aber bewusst:

### A) Auswertung → Energieprofil — *die Analyse-Sicht*

Hier **liest und interpretierst** du die Daten. Vier Unter-Tabs:

| Tab | Inhalt |
|-----|--------|
| **Tagesdetail** | Butterfly-Chart (Quellen oben, Senken unten) + Stundentabelle für einen einzelnen Tag. KPI-Zeile: Verfügbare Energie, PV-Anteil, Gesamtverbrauch, Netzbezug, Einspeisung, Autarkie, Temperatur. |
| **Wochenvergleich** | Durchschnittliches Stundenprofil je Wochentag — zeigt typische Tagesmuster. |
| **Monat** | Heatmap Tag × Stunde, Monats-KPIs, Peak-Stunden, Aufschlüsselung nach Komponenten und Kategorien. |
| **Prognose** | Tagesprognose mit Batteriesimulation (siehe [Handbuch Prognosen](HANDBUCH_PROGNOSEN.md)). |

> Die Unter-Tabs schalten sich erst frei, sobald **mindestens 8 Tage** mit Stundenwerten vorliegen. Davor siehst du einen Fortschrittsbalken „X von 8 Tagen". Das ist kein Fehler — eedc sammelt erst genug Daten, damit Durchschnitte und Muster aussagekräftig sind.

### B) Einstellungen → Daten → Energieprofil — *die Verwaltungs-Sicht*

Hier **pflegst und reparierst** du die Daten. Diese Seite enthält:

- **Datenbestand** — KPI-Kacheln (Stundenwerte / Tagessummen / Monatswerte) und ein Abdeckungs-Balken „X von Y Tagen erfasst".
- **Tages-Energieprofile-Tabelle** — eine Zeile pro Tag mit Spalten-Selektor (siehe unten), Monats-Summenzeile und einem **Reload-Knopf je Tag**.
- **Datenverwaltung** — „Lücken aus HA-Statistik nachfüllen" (Vollbackfill), optionaler Kraftstoffpreis-Backfill, und im Gefahrenbereich „Energieprofil-Daten löschen".
- **Reparatur-Werkbank** — siehe [§6](#6-die-reparatur-werkzeuge).

#### Spalten der Tages-Tabelle

Die Tabelle hat **feste Spalten** (immer sinnvoll) und **dynamische Diagnose-Spalten** (pro Gerät, standardmäßig ausgeblendet):

- **Tages-Summen (kWh):** PV-Ertrag, Überschuss, Defizit
- **Peak-Leistungen (kW):** Peak PV / Netzbezug / Einspeisung
- **Performance:** Performance Ratio (%), Batterie-Vollzyklen, „Stunden verfügbar" (z. B. 20/24)
- **Wetter:** Temp min/max, Strahlung
- **Börsenpreis (§51 EEG):** Ø/Min-Preis, Negativpreis-Stunden, „Einspeisung bei Negativpreis"
- **Komponenten-Counter:** WP-Starts
- **Diagnose-Spalten (einblendbar):** je Gerät eine Spalte, Wert = Tages-kWh dieser Komponente. **Vorzeichen: positiv = Erzeugung, negativ = Verbrauch.**

> **„Stunden verfügbar"** ist die wichtigste Diagnose-Spalte: zeigt sie dauerhaft etwas wie `14/24`, fehlen dir Stunden — ein Hinweis auf Lücken in den Snapshots oder ein Sensor-Problem.

---

## 3. Woher die Daten kommen — die Pipeline

Das Verständnis dieser Kette erklärt fast alle Abhängigkeiten und Probleme:

```
Kumulative kWh-Zähler (deine Sensoren, z. B. sensor.pv_erzeugung_total)
        │   stündlicher Snapshot (Cron :05) + Preview-Snapshot (:55)
        ▼
sensor_snapshots  bzw.  HA-Long-Term-Statistics (statistics-Tabelle)
        │   Stunden-Delta = Zählerstand[h] − Zählerstand[h-1]
        ▼
TagesEnergieProfil   (24 Zeilen pro Tag, je Kategorie eine Spalte)
        │   Tagesfenster-Differenz = Zählerstand[Folgetag 00:00] − [Tag 00:00]
        ▼
TagesZusammenfassung.komponenten_kwh   (1 Zeile pro Tag, kWh je Gerät)
        │   Monatsabschluss (Rollup)
        ▼
Monatsdaten   (nur 5 aggregierte Top-Level-Felder)
```

### Zwei Datenherkünfte — zwei parallele Pfade

Welche Quelle eedc nutzt, hängt von der Installation ab — das Ergebnisformat ist identisch:

1. **HA-Add-on / Docker mit HA-Recorder-Zugriff → HA-Long-Term-Statistics (LTS).** Das ist die bevorzugte Quelle. eedc liest die Stunden-Deltas direkt aus der HA-`statistics`-Tabelle.
2. **Standalone / MQTT → Snapshot-Pfad.** eedc speichert stündlich eigene Snapshots in der `sensor_snapshots`-Tabelle und rechnet daraus.

> **Warum das wichtig ist:** Dass zwei Pfade dasselbe liefern *sollen*, ist die häufigste Quelle für „Drift" — kleine Abweichungen zwischen zwei Berechnungswegen. eedc prüft diese Konsistenz inzwischen aktiv (siehe [§7](#7-bekannte-probleme--fehlerbilder)), aber als Nutzer solltest du wissen: Wenn HA und eedc minimal unterschiedliche Tageswerte zeigen, ist das fast immer ein Pfad-/Slot-Thema, kein „kaputter" Zähler.

### Die zentrale Aggregationsregel: MAX(sum) − MIN(sum)

HA speichert für jeden Zähler-Sensor mit gesetzter `state_class` eine fortlaufende `sum`-Spalte, die **Zähler-Resets bereits glättet**. eedc bildet Tages- und Stundenwerte aus der **Differenz dieser `sum`-Werte**, nicht aus den `state`-Werten. Das ist entscheidend, weil viele Sensoren (z. B. `utility_meter` mit Tageszyklus) um Mitternacht auf 0 zurückspringen — die `state`-Differenz wäre dann negativ und unbrauchbar, die `sum`-Differenz ist korrekt.

### Verbrauch wird gerechnet, nicht gemessen

Den Gesamtverbrauch misst kein einzelner Sensor. eedc berechnet ihn bilanziell:

```
Verbrauch = PV-Erzeugung + Netzbezug − Einspeisung − Batterie-Netto
```

Das gilt nur, wenn **PV, Netzbezug und Einspeisung alle vorhanden** sind. Fehlt einer dieser drei, bleibt die Verbrauchsspalte leer — ein häufiger Grund für „leere" Auswertungen.

---

## 4. Was du konfigurieren musst (Abhängigkeiten)

Das Energieprofil rechnet nur so gut wie sein Sensor-Mapping. Diese Voraussetzungen müssen erfüllt sein:

### 4.1 Kumulative kWh-Zähler mappen — keine Leistungssensoren!

Der Aggregator liest **ausschließlich** kumulative kWh-Zähler. Erwartet werden:

- **Basis (Anlage):** `einspeisung` **und** `netzbezug`. Fehlen sie, bleibt der gesamte bilanzielle Verbrauch leer.
- **Pro Investition:**
  - PV-Module / Balkonkraftwerk → `pv_erzeugung_kwh`
  - Speicher → `ladung_kwh` **und** `entladung_kwh` (ein evtl. vorhandener „Netzladung"-Zähler ist eine Teilmenge und wird **nicht** zusätzlich gezählt)
  - Wärmepumpe → `stromverbrauch_kwh` — **oder** bei getrennter Messung die zwei Felder `strom_heizen_kwh` + `strom_warmwasser_kwh`
  - Wallbox → `ladung_kwh` (PV-/Netz-Splits sind Teilmengen, nicht zusätzlich)
  - E-Auto → `ladung_kwh` oder `verbrauch_kwh`
  - Sonstiges → `verbrauch_kwh` / `erzeugung_kwh`

> ⚠️ **Häufigster Fehler:** Ein **Leistungssensor (W/kW)** wird in einen kWh-Slot gemappt. Das liefert physikalisch unmögliche Stundenwerte (siehe [§7](#7-bekannte-probleme--fehlerbilder)). eedc kappt solche Ausreißer und der Daten-Checker meldet sie — aber die saubere Lösung ist, den **richtigen kumulativen Zähler** zu mappen. Details: [feedback zur Sensoreinheit, Handbuch Einstellungen](HANDBUCH_EINSTELLUNGEN.md).

### 4.2 `state_class` muss gesetzt sein — HA-LTS ist keine Zeitmaschine

HA legt für einen Sensor **erst dann** Long-Term-Statistics an, wenn dessen `state_class` (`total`, `total_increasing` oder `measurement`) gesetzt ist. **Vor diesem Zeitpunkt existieren keine LTS-Daten.** Kein Backfill der Welt kann nachholen, was HA nie aufgezeichnet hat.

Das ist kein eedc-Bug, sondern eine Eigenschaft von Home Assistant. Der Daten-Checker (Kategorie *Sensor-Mapping – HA-Statistics*) warnt, wenn ein gemappter Sensor keine `state_class` hat.

### 4.3 Anschaffungs- und Stilllegungsdatum

Eine Investition fließt nur an den Tagen in die Aggregation ein, an denen sie laut `installationsdatum` / `stilllegungsdatum` aktiv war. Trägst du diese Daten korrekt ein, erscheint eine neue PV-Erweiterung nicht rückwirkend in alten Monaten — und eine stillgelegte Komponente verschwindet sauber ab dem Stilllegungstag.

### 4.4 PV-Leistung (kWp) und Koordinaten

`leistung_kwp` ist Voraussetzung für die **Performance Ratio** und für den **Counter-Spike-Schutz** (die Plausibilitätsgrenze ist `kWp × 1,5` pro Stunde). Ohne kWp bleibt PR leer und Ausreißer werden nicht gekappt. Standort-Koordinaten brauchst du für Wetter-IST und Strahlungswerte.

---

## 5. Wie aus Zählern Stunden- und Tageswerte werden

### 5.1 Die Backward-Slot-Konvention

eedc ordnet jede Stunde nach dem Industriestandard (HA, SMA, Fronius, Tibber) ein:

> **Slot N = Energie aus dem Intervall [N−1, N)** — „die *vergangene* Stunde".
> Slot 0 = Energie von 23:00–24:00 des **Vortags**. Slot 8 = Energie von 07:00–08:00.

Wichtig zu wissen:

- Das **Tagesfenster** für die Tages-kWh ist `[Tag 00:00, Folgetag 00:00)`. Es ist 24 Stunden lang, aber **nicht** identisch mit „Summe der Slots 0–23" — die beiden Fenster sind gegeneinander um eine Stunde versetzt. `Σ Slot[0..23] ≠ Tagesgesamt` ist also normal, kein Fehler.
- **Strompreise** folgen weiterhin der *Forward*-Konvention `[N, N+1)`. Diese Asymmetrie ist beabsichtigt.

### 5.2 Zähler-Resets und Lücken

- **Tagesreset-Erkennung:** Springt ein Zähler um Mitternacht auf ~0 zurück, erkennt eedc das Muster und nimmt den Wert *seit dem Reset* als Energie — statt die Stunde als „leer" zu werten.
- **Lücken-Interpolation:** Fehlt ein einzelner stündlicher Snapshot, interpoliert eedc linear zwischen den bekannten Nachbarwerten. Die Tagessumme bleibt korrekt, weil sie aus der Tagesfenster-Differenz kommt. **Ränder werden nicht extrapoliert** — fehlt der erste oder letzte Snapshot des Tages, entsteht eine echte Lücke.

### 5.3 Getrennte Strommessung bei Wärmepumpen

Hat eine WP getrennte Zähler für Heizen und Warmwasser (`getrennte_strommessung = True`), sind `strom_heizen_kwh` + `strom_warmwasser_kwh` die elektrische Wahrheit; ein etwaiger Gesamtzähler `stromverbrauch_kwh` wird dann ignoriert (sonst Doppelzählung).

### 5.4 Counter-Spike-Schutz

Nach HA-Neustarts oder bei `sum = NULL` kann ein Zähler kurzzeitig seinen *Lebensdauer-Stand* als Stundenwert liefern (z. B. 12.000 kWh in einer Stunde). eedc kappt:

- **PV / Einspeisung:** Stundenwerte über `kWp × 1,5` → verworfen + protokolliert.
- **WP-Starts:** mehr als 200 Starts/Stunde → 0.

Diese Schwelle teilt sich eedc mit dem Daten-Checker — was der Aggregator kappt, kann der Checker nicht mehr als Auffälligkeit melden.

### 5.5 Der laufende Tag (heute)

Für **heute** kann eedc das volle Tagesfenster noch nicht schließen (der Snapshot für „morgen 00:00" existiert noch nicht). Deshalb läuft für den heutigen Tag ein **slot-basierter Pfad**, der die bereits abgelaufenen Stunden aufsummiert und eine **ehrliche Teilsumme** liefert. Der heutige Wert wächst über den Tag — das ist korrekt, kein Fehler.

> **Hintergrund (v3.34.1, „B-clean", #620):** Im HA-Add-on blieb die Tages-kWh-Spalte für *heute* früher strukturell leer (ein „toter Punkt"). Das ist behoben; heute zeigt jetzt eine laufende Teilsumme.

---

## 6. Die Reparatur-Werkzeuge

eedc bietet bewusst **keinen** großen „Alles-heilen"-Knopf, sondern gezielte, nachvollziehbare Werkzeuge mit Vorschau. Leitlinie: lieber einen konkreten Tag prüfen und reparieren als blind alles überschreiben.

### 6.1 Einen Tag neu aggregieren (mit Vorschau)

Der **Reload-Knopf** je Tabellenzeile öffnet eine **Alt/Neu-Vorschau**: Tagessummen, alle 24 Stunden-Slots und die Counter-Tagesdelta nebeneinander. Erst danach entscheidest du:

- **„Aus HA neu laden + neu rechnen"** — holt die Snapshots frisch aus HA-LTS und rechnet neu (~30 s). Richtig, wenn die Snapshots selbst fehlerhaft waren.
- **„Nur neu rechnen"** — rechnet nur aus den vorhandenen Snapshots neu (~2 s). eedc empfiehlt diese Variante automatisch, wenn die Vorschau zeigt, dass die Snapshots bereits stimmen.

Nach dem Anwenden meldet eedc, wie viele **Stunden mit echten Messdaten** verarbeitet wurden — ein ehrlicher Erfolgsindikator (nicht „erledigt", wenn gar keine Daten da waren).

### 6.2 Mehrere Tage neu aggregieren

Über die Reparatur-Werkbank lässt sich ein **Datumsbereich** (max. 31 Tage) neu aggregieren. Die Tage werden einzeln verarbeitet und committet — ein Abbruch lässt die bereits reparierten Tage stehen. Für längere Zeiträume in mehreren Schüben arbeiten.

### 6.3 Lücken nachfüllen (Vollbackfill) — immer additiv

„Lücken aus HA-Statistik nachfüllen" ergänzt **nur fehlende** Tage aus HA-LTS. **Bestehende Tage bleiben unverändert** — es gibt bewusst keinen Overwrite-Modus mehr. eedc nennt für jeden Tag transparent den Grund, falls er übersprungen wurde (keine HA-Daten / existiert bereits).

**Wann sinnvoll:** nach der Erstinstallation, nach längerem App-Stillstand oder nach einer Sensor-Mapping-Änderung.

### 6.4 Daten löschen (Gefahrenbereich)

Löscht Stunden- und Tageswerte des Energieprofils. **Monatsdaten bleiben erhalten.** Der Scheduler rechnet die Tage anschließend neu (binnen ~15 Min). Nur nutzen, wenn ein Neuaufbau wirklich gewollt ist.

---

## 7. Bekannte Probleme & Fehlerbilder

| Symptom | Ursache | Was tun |
|---------|---------|---------|
| **Tage/Stunden fehlen, „X/24"** | Sensor hatte (noch) keine `state_class`; HA-LTS reicht nicht so weit zurück | `state_class` setzen, danach läuft die Erfassung ab *jetzt*. Rückwirkend ist nichts zu retten — HA-LTS ist keine Zeitmaschine. |
| **Verbrauchsspalte leer** | `einspeisung` oder `netzbezug` nicht gemappt | Beide Basis-Zähler im Sensor-Mapping ergänzen. |
| **Unmöglich hohe Stundenwerte** | Leistungssensor (W/kW) in kWh-Slot gemappt, oder Counter-Spike nach HA-Neustart | Richtigen kumulativen kWh-Zähler mappen; betroffenen Tag neu aggregieren. eedc kappt zwar, aber das Mapping ist die eigentliche Korrektur. |
| **HA und eedc zeigen leicht andere Tageswerte** | Drift zwischen den beiden Aggregator-Pfaden oder Slot-Versatz | Meist harmlos; bei größerer Abweichung Tag neu aggregieren. eedc protokolliert Drift > 0,5 kWh selbst. |
| **PV doppelt gezählt** | Gerät wurde unter zwei Komponenten-Schlüsseln geschrieben | In aktuellen Versionen behoben (ein eindeutiger Schreiber pro Komponente). Bei Altbeständen: betroffene Tage neu aggregieren. |
| **E-Auto + Wallbox doppelt** | Die Wallbox misst bereits die Ladung des E-Autos | E-Auto als „Kind" der Wallbox verknüpfen (`parent_investition_id`), dann wird es nicht zusätzlich gezählt. |
| **heute leer** | Betraf Versionen vor v3.34.1 | Auf aktuelle Version updaten. |

### Der Daten-Checker als Frühwarnsystem

Drei Daten-Checker-Kategorien beziehen sich direkt aufs Energieprofil:

- **Energieprofil – Zähler-Abdeckung:** prüft, welche kumulativen kWh-Zähler gemappt sind. Fehlen sie, bleiben Prognosen-IST, Heatmap, Lernfaktor und Monatsberichte leer.
- **Energieprofil – Plausibilität:** erkennt Stundenwerte über `kWp × 1,5` der letzten 30 Tage und verlinkt direkt zum betroffenen Tag mit „Tag neu aggregieren".
- **Datenquelle-Drift:** vergleicht (nur im HA-Betrieb) die eedc-PV-Tagessumme gegen den HA-LTS-Wert der letzten 90 Tage und listet auffällige Tage mit Inline-Reparatur-Link.

Details: [Handbuch Daten-Checker](HANDBUCH_DATEN_CHECKER.md).

---

## 8. Beziehung zu anderen Auswertungen

Das Energieprofil ist die Wurzel des Datenbaums:

- **→ Monatsbericht / Auswertung-Monat:** Heatmap, Autarkie, Eigenverbrauch, Grundbedarf, Batterie-Wirkungsgrad und Peak-Stunden werden direkt aus den Stunden-/Tageswerten des Monats gebaut.
- **→ Monatsabschluss (Rollup):** Aus den Tageszusammenfassungen entstehen **fünf** aggregierte Monatsfelder (Überschuss, Defizit, Batterie-Vollzyklen, Performance Ratio, Peak Netzbezug). **Wichtig:** Die komponentenweisen kWh werden **nicht** in die `Monatsdaten` gespiegelt. Die gerätbezogenen Monatswerte für Cockpit und ROI kommen aus `InvestitionMonatsdaten` — einer **getrennten** Datenquelle. (Grundsatz: `Monatsdaten` = Zählerwerte, `InvestitionMonatsdaten` = Komponenten-Details.)
- **→ Cockpit:** Die Heute-/Komponenten-Anzeige liest die Tages-`komponenten_kwh`; die §51-EEG-Sektion (Negativpreis-Einspeisung) kommt aus der Tageszusammenfassung.
- **→ Prognosen / Genauigkeits-Tracking:** Die **IST-Werte** für den Prognosenvergleich und den Lernfaktor stammen aus dem Energieprofil (PV-Tagessumme über die Schlüssel mit Präfix `pv_`/`bkw_`). Fehlt hier die Zähler-Abdeckung, kann eedc keine Prognose-Genauigkeit berechnen. Siehe [Handbuch Prognosen](HANDBUCH_PROGNOSEN.md).

> **Merksatz:** Stimmt das Energieprofil, stimmen die darüberliegenden Ebenen meist von selbst. Lohnt sich also, bei Auffälligkeiten zuerst hier zu schauen — und bei Bedarf gezielt einen Tag neu zu aggregieren, statt an den abgeleiteten Werten zu drehen.
