
# eedc Handbuch — Teil I: Installation & Einrichtung

**Version 4.0** | Stand: 2026-07-25

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Einführung](#1-einführung)
2. [Installation](#2-installation)
3. [Ersteinrichtung (Setup-Wizard)](#3-ersteinrichtung-setup-wizard)
4. [Nach dem Setup — wie es weitergeht](#4-nach-dem-setup--wie-es-weitergeht)
5. [Tipps & Best Practices](#5-tipps--best-practices)
6. [Fehlerbehebung](#6-fehlerbehebung)

---

## 1. Einführung

### Was ist eedc?

**eedc** (Energie Effizienz Data Center) ist eine lokale Software zur Analyse deiner Photovoltaik-Anlage. Sie hilft dir:

- **Energieflüsse zu verstehen** – Wie viel erzeugst du? Wie viel verbrauchst du selbst?
- **Wirtschaftlichkeit zu analysieren** – Wann amortisiert sich die Investition?
- **Optimierungspotenziale zu erkennen** – Wie erreichst du mehr Eigenverbrauch?
- **Alle Komponenten im Blick zu behalten** – PV-Anlage, Speicher, E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk

### Grundprinzipien

1. **Standalone-First:** eedc funktioniert komplett ohne Home Assistant. Eine HA-Anbindung ist optional und erweitert die Datenerfassung.
2. **Lokale Datenspeicherung:** Alle Daten bleiben auf deinem Server.
3. **Monatliche Basis mit Stunden-Tiefe:** Kennzahlen werden pro Monat geführt; wo Zähler-Snapshots vorliegen, kommt zusätzlich die Stunden- und Tages-Auflösung dazu.
4. **Flexible Datenquellen:** manuelle Eingabe, CSV-Import, Wetter-API sowie – optional – HA-Sensoren, MQTT-Topics und Geräte-Connectoren.

### Systemanforderungen

- **Standalone:** Docker oder Python 3.11+ mit Node.js 20+
- **Home Assistant Add-on:** Home Assistant OS oder Supervised
- **Browser:** moderner Browser (Chrome, Firefox, Safari, Edge)

### Empfohlene Nutzung

eedc ist als datendichte Analyse-App konzipiert und entfaltet seinen vollen Nutzen am **Desktop**. Live, Cockpit-Monat und die Komponenten-Sichten funktionieren auch am Smartphone gut; die datendichten Tabellen (Auswertungen → Tabelle, Cockpit → Aussicht) profitieren spürbar von einem größeren Bildschirm oder dem Querformat.

Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom) können einzelne Layouts eng werden. Das ist eine bewusste Designentscheidung: Layout-Patches, die den datendichten Charakter aufweichen würden, werden nicht eingebaut. Wer eedc primär in der HA-Companion-App nutzt, sollte den Seitenzoom nahe der Standardgröße halten.

> Diese Empfehlung formuliert eine technische App-Eigenschaft (datendicht, Desktop empfohlen) — keine Aussage zu Barrierefreiheit oder Accessibility.

---

## 2. Installation

Wie du eedc installierst, hängt von deiner Umgebung ab. Die eigentliche Software ist in allen Varianten identisch; nur der Start unterscheidet sich.

### Option A: Home Assistant Add-on (empfohlen für HA-Nutzer)

1. **Repository hinzufügen:**
   - Gehe zu *Einstellungen → Add-ons → Add-on Store*
   - Klicke auf das Menü (⋮) → *Repositories*
   - Füge hinzu: `https://github.com/supernova1963/eedc-homeassistant`

2. **Add-on installieren:**
   - Suche nach „eedc" im Add-on Store
   - Klicke auf *Installieren*
   - Aktiviere „In Sidebar anzeigen"
   - Starte das Add-on

3. **Öffnen:**
   - Klicke in der HA-Sidebar auf „eedc"
   - Oder öffne direkt: `http://homeassistant.local:8099`

Im Add-on-Betrieb erkennt eedc deine Home-Assistant-Sensoren automatisch – der Setup-Wizard schlägt dir im Integrations-Schritt passende Sensoren aus deinem HA-Energy-Dashboard vor (siehe [§3](#3-ersteinrichtung-setup-wizard)).

### Option B: Docker (Standalone)

Das Docker-Image ist für `amd64` und `arm64` (Raspberry Pi 4/5, Apple Silicon) verfügbar.

**Empfohlen: Docker Compose**

```bash
# Standalone-Repository klonen
git clone https://github.com/supernova1963/eedc.git
cd eedc

# Mit Docker Compose starten (holt das fertige Image automatisch)
docker compose up -d

# Browser öffnen
open http://localhost:8099
```

**Alternativ: manuell bauen**

```bash
cd eedc

# Image bauen
docker build -t eedc .

# Container starten mit persistentem Datenverzeichnis
docker run -d \
  --name eedc \
  -p 8099:8099 \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  eedc
```

Im Standalone-Betrieb ohne lokales Home Assistant kannst du eedc trotzdem an eine externe HA-Instanz anbinden (per langlebigem Zugriffstoken) oder Daten ausschließlich über MQTT beziehen – beides richtest du im Setup-Wizard oder später unter *Einstellungen → Integration* bzw. *Einstellungen → Datenquellen* ein.

### Option C: Entwicklungsumgebung

Siehe [DEVELOPMENT.md](DEVELOPMENT.md) für die lokale Entwicklungsumgebung (Backend + Frontend getrennt).

---

## 3. Ersteinrichtung (Setup-Wizard)

Beim **ersten Start** – wenn noch keine Anlage angelegt ist – begrüßt dich ein geführter Assistent und richtet eedc in wenigen Schritten ein. Der Assistent erscheint automatisch, solange in der Datenbank **keine Anlage** vorhanden ist; die Datenbank hat dabei Vorrang vor dem Browser-Speicher. Das Anlegen dauert rund 2–3 Minuten.

Der Wizard läuft **vor der eigentlichen App**. Auf jedem Schritt gibt es oben rechts einen **Hilfe-Knopf**, der genau den passenden Abschnitt dieses Kapitels als Overlay einblendet – ohne die Einrichtung zu verlassen.

> **Umgebungsabhängig:** Ein Teil der Schritte passt sich deiner Umgebung an. Der **Integrations-Schritt** sieht im HA-Add-on anders aus als im Standalone-Betrieb, und einzelne Felder erscheinen nur, wenn sie in deiner Umgebung sinnvoll sind. Die folgenden Abschnitte beschreiben den vollen Umfang.

> Dieses Kapitel beschreibt den **Flip-Zustand (v4.0)**. Bis zum Flip sind der **Integrations-Schritt**, das Feld **Straße & Hausnummer** und der Abschluss-Absprung **„Sensor- & Topic-Pflege"** noch hinter dem `IA_V4`-Schalter verborgen; mit **v4.0** erscheinen sie regulär. *(Interner Merker: Das Kontext-Hilfe-Overlay wird über `WIZARD_HILFE_AKTIV` erst im Flip-Zug scharfgeschaltet – nicht vorher anfassen.)*

### Erst-Setup

Der Willkommens-Bildschirm stellt eedc kurz vor – mit den drei Kernbereichen **Auswertungen**, **Wirtschaftlichkeit** und **Prognosen** – und zeigt, was gleich eingerichtet wird: PV-Anlage mit Standort, Stromtarif, Wechselrichter und Module sowie optional Speicher, Wärmepumpe und E-Auto.

Von hier hast du drei Wege:

- **Einrichtung starten** – der normale Weg durch die folgenden Schritte.
- **Demo-Anlage laden** – lädt einen vorbereiteten Beispiel-Datensatz (rund 24 Monate Daten mit Wechselrichter, PV-Modulen, Speicher, Wärmepumpe u. v. m.) und springt direkt ins Cockpit. Ideal zum Ausprobieren, bevor du eigene Daten erfasst.
- **JSON-Backup importieren** – hast du eine frühere JSON-Sicherung, stellst du damit Anlage, Strompreise, Investitionen, Monatsdaten und die Datenquellen-Zuordnung in einem Schritt wieder her. Nach dem Import landest du direkt in der App.

### Erst-Setup: Anlage

Hier legst du deine Anlage als Stammdatensatz an.

| Feld | Bedeutung | Beispiel |
|------|-----------|----------|
| **Anlagenname** (Pflicht) | frei wählbare Bezeichnung | „Meine PV-Anlage" |
| **Leistung (kWp)** (Pflicht) | Gesamtleistung aller Module in Kilowatt-Peak | 10,5 |
| **Inbetriebnahme (Anlage)** | Stammdatum der **Gesamt-Anlage** (nicht das älteste Gerät) | 01.01.2024 |
| **PLZ / Ort** | Standort für die PVGIS-Ertragsprognose | 12345 / Berlin |
| **Straße & Hausnummer** (optional) | schärft die Koordinaten fürs Geocoding | Musterweg 12 |
| **Breitengrad / Längengrad** | werden per Knopf ermittelt oder manuell eingetragen | 52.520008 / 13.404954 |

**Koordinaten ermitteln:** Trage mindestens die PLZ ein (Ort und Straße machen das Ergebnis genauer) und klicke auf **„Koordinaten aus PLZ ermitteln"**. eedc füllt Breiten- und Längengrad automatisch; du kannst sie danach von Hand nachjustieren.

> **Wozu das Inbetriebnahme-Datum?** Es steuert, ab wann Stromtarife gelten und welchen Zeitraum der Community-Vergleich heranzieht. Es ist bewusst das Datum der Anlage als Ganzes – einzelne Geräte tragen ihr eigenes Anschaffungsdatum in den Komponenten.

> **Steuerliche Einstellungen** (Regelbesteuerung / Kleinunternehmer) legst du nicht hier, sondern später unter *Einstellungen → Stammdaten → Anlage bearbeiten* fest.

### Erst-Setup: Strompreise

Der Stromtarif ist die Grundlage aller Wirtschaftlichkeits-Berechnungen. Zwei Wege:

- **Deutsche Standardwerte verwenden** – ein Klick übernimmt einen Ausgangstarif (ca. 30 ct/kWh Netzbezug, 12 €/Monat Grundpreis und eine an die Anlagengröße angepasste Einspeisevergütung). Die Einspeisevergütung richtet sich nach der Leistung: bis 10 kWp 8,2 ct, bis 40 kWp 7,1 ct, darüber 5,8 ct (Stand 2026).
- **Manuell anpassen** – du trägst Netzbezugspreis (Pflicht), Einspeisevergütung, Grundpreis, das Gültigkeitsdatum („Gültig ab", Pflicht) sowie optional Tarifname und Anbieter selbst ein.

> **Mehrere Tarife später möglich:** Bei einem Tarifwechsel oder einer Preisänderung legst du unter *Einstellungen → Stammdaten → Strompreise* einfach einen weiteren Tarif mit eigenem Gültigkeitszeitraum an. Auch **Spezialtarife** für Wärmepumpe oder Wallbox (separater Zähler, günstigerer Tarif) gehören dorthin.

### Erst-Setup: Komponenten

Hier erfasst du die Geräte deiner Anlage. eedc bietet dir einen Schnellstart:

- **PV-System anlegen (empfohlen)** – erstellt in einem Zug einen **Wechselrichter** und die zugehörigen **PV-Module** mit der zuvor eingegebenen Anlagenleistung. Ausrichtung und Neigung der Module trägst du danach nach.
- **Einzeln hinzufügen** – über die Kacheln fügst du gezielt Balkonkraftwerk, Speicher, Wallbox, Wärmepumpe oder E-Auto hinzu; weitere Typen erreichst du über das Auswahl-Menü.

Sind bereits Komponenten angelegt, zeigt der Schritt sie **nach Typ gruppiert** in der einheitlichen eedc-Reihenfolge. Jede Komponente hat ein Inline-Formular, in dem du **Kaufdatum, Kaufpreis und technische Details** ergänzt – diese Angaben braucht die ROI- und Amortisationsberechnung. Pflichtfelder sind mit `*` markiert; der Kaufpreis ist für die Amortisation besonders wichtig.

Dieser Schritt ist **überspringbar** – du kannst mit null Komponenten fortfahren und alles später unter *Einstellungen → Komponenten* nachtragen oder ändern.

> **PV-Module brauchen einen Wechselrichter:** Module (und DC-Speicher) werden einem Wechselrichter zugeordnet. Der Schnellstart „PV-System anlegen" erledigt das automatisch. Details zu den einzelnen Komponenten-Feldern findest du in [Teil III: Einstellungen → Komponenten](HANDBUCH_EINSTELLUNGEN.md#3-komponenten).

### Erst-Setup: Integration

Dieser Schritt bindet – ganz optional – deine **Datenquellen** an. Er passt sich deiner Umgebung an und legt **nie etwas ungefragt** an; alles hier lässt sich später unter *Einstellungen → Datenquellen* ändern. Du kannst ihn auch überspringen.

**Im Home-Assistant-Add-on** ist HA bereits verbunden. eedc liest deine **HA-Energy-Dashboard-Konfiguration** und schlägt dir daraus passende Sensoren vor – für die Anlage insgesamt und für einzelne Komponenten. Du hakst die gewünschten Vorschläge an und übernimmst sie mit **„Ausgewählte übernehmen"**. Die Übernahme ist immer **bestätigt**, nie still. Zusätzlich kannst du den **MQTT-Export** aktivieren.

**Im Standalone-Betrieb** fragt eedc zuerst: *„Nutzt du eine externe Home-Assistant-Instanz?"*

- **Ja, HA verbinden** – du hinterlegst die HA-Basis-URL und einen **langlebigen Zugriffstoken**. Den Token erstellst du in Home Assistant unter *Profil → Sicherheit → „Langlebige Zugriffstoken" → Token erstellen*. Nach **„Verbinden & testen"** stehen dieselben Energy-Dashboard-Vorschläge zur Verfügung wie im Add-on. Auch hier ist der **MQTT-Export** zusätzlich möglich.
- **Nein, nur MQTT** – du richtest **einen** MQTT-Broker ein, der **beide Richtungen** bedient (Empfangen **und** Export). Dafür trägst du Broker-Host, Port (Vorgabe 1883) sowie optional Benutzer und Passwort ein und speicherst.

> **Ein Broker, klare Richtungen:** eedc nutzt genau einen MQTT-Broker. Im HA-Zweig ist MQTT reiner Export; im Nur-MQTT-Zweig kommen empfangene Werte **und** Export über denselben Broker. Die Details der Broker-Verbindung stehen in [Teil III: Einstellungen → Integration](HANDBUCH_EINSTELLUNGEN.md#6-integration).

> **Takt-Hinweis:** Nicht jeder HA-Sensor eignet sich als Datenquelle – manche melden zu selten für eine stündliche Auswertung. Übernommene bzw. zugeordnete Sensoren werden deshalb in der Datenquellen-Fläche auf ihren **Melde-Takt** geprüft (Takt-Check); bei zu grobem Takt bekommst du dort einen Hinweis und kannst die Zuordnung trotzdem bewusst übernehmen. Diese Prüfung läuft in der Datenquellen-Pflege, siehe [Teil III: Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung). *(Redaktion: prüfen, ob der Takt-Check-Hinweis mit v4.0 auch schon im Wizard-Schritt selbst sichtbar ist oder erst in der Datenquellen-Fläche – aktueller Code läuft im Picker.)*

### Erst-Setup: Abschluss

Zum Schluss zeigt dir eedc eine **Zusammenfassung** und lässt dich den **nächsten Schritt** selbst wählen.

**Zusammenfassung prüfen** – auf einen Blick siehst du je Bereich, ob er sauber konfiguriert ist:

- **PV-Anlage** – Name, Leistung, Ort und ob Koordinaten gesetzt sind
- **Stromtarif** – Netzbezug und Einspeisung (ein fehlender Tarif wird als Warnung markiert)
- **Investitionen** – die erfassten Komponenten samt Gesamt-Investitionssumme
- **PVGIS-Ertragsprognose** – sind Koordinaten und PV-Module vorhanden, rufst du hier mit **„PVGIS-Prognose abrufen"** die erwartete Jahres-Erzeugung (kWh/Jahr und kWh/kWp) ab. Sie ist die Grundlage späterer SOLL/IST-Vergleiche.

**Abschluss & nächster Schritt** – nach „Weiter zur Datenerfassung" begrüßt dich der Abschluss-Bildschirm mit einer echten Wahl, wie es weitergeht:

- **Monatsdaten erfassen** – springt direkt in das Monatsdaten-Formular (*Einstellungen → Daten → Monatsdaten*), um die ersten Zählerstände einzutragen.
- **Sensor- & Topic-Pflege** – springt in die Datenquellen-Fläche (*Einstellungen → Datenquellen*), um Felder Sensoren bzw. MQTT-Topics zuzuordnen.
- **Zum Cockpit** – öffnet direkt die Startseite.

> **Woher weiß eedc, dass das Setup erledigt ist?** Sobald eine Anlage in der Datenbank liegt, gilt die Einrichtung als abgeschlossen und der Wizard startet nicht mehr. Möchtest du ihn erneut durchlaufen, hilft der Abschnitt [Fehlerbehebung → Setup-Wizard erneut starten](#setup-wizard-erscheint-erneut).

---

## 4. Nach dem Setup — wie es weitergeht

Der Setup-Wizard richtet die Stammdaten ein. Die **laufende Datenpflege** liegt danach gesammelt unter **Einstellungen** und ist in [Teil III](HANDBUCH_EINSTELLUNGEN.md) beschrieben. Die wichtigsten Wege:

- **Monatsdaten / Monatsabschluss** – ein einziges **Formular** unter *Einstellungen → Daten → Monatsdaten*. Hier trägst du monatliche Zählerstände (Einspeisung, Netzbezug), Verbrauchswerte und „sonstige Positionen" ein; ein offener Monatsabschluss taucht zusätzlich in der Status-Fußzeile auf. *(In früheren Versionen war das ein mehrstufiger Assistent – jetzt ein durchgängiges Formular; siehe [Teil III §5.1](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss).)*
- **Datenquellen zuordnen** – welches Feld aus welchem HA-Sensor, MQTT-Topic oder Connector gespeist wird, pflegst du unter *Einstellungen → Datenquellen* (siehe [Teil III §7](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung)).
- **Import & Nachpflege** – CSV, Cloud/Portal, Geräte-Connector, HA-Statistik-Import sowie die Energieprofil-Pflege (Vollbackfill, Neu-Aggregation) liegen ebenfalls in den Einstellungen.

Wie du die eingerichteten Daten dann **ansiehst und auswertest** (Cockpit, Komponenten, Auswertungen, Community), erklärt [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md).

---

## 5. Tipps & Best Practices

### Datenqualität

1. **Zählerstände nutzen:** Einspeisung und Netzbezug sollten echte Zählerwerte sein.
2. **Regelmäßig erfassen:** mindestens monatlich Daten eintragen.
3. **Konsistenz prüfen:** Eigenverbrauch ≤ Erzeugung.

### Komponenten richtig anlegen

1. **Wechselrichter zuerst,** dann PV-Module zuordnen.
2. **Realistische Werte:** Lebensdauer, Kaufpreis, Installationsdatum.
3. **Alle Kosten** erfassen – auch Montage, Gerüst und Elektriker.

### Auswertungen interpretieren

1. **Jahresvergleich:** gleicher Monat, unterschiedliche Jahre.
2. **Wetter berücksichtigen:** ein schlechtes Jahr bedeutet keine schlechte Anlage.
3. **PVGIS als Referenz:** ±10 % Abweichung ist normal.

### Eigenverbrauch erhöhen

1. **Verbraucher tagsüber** laufen lassen.
2. **Speicher nutzen:** Überschuss für abends aufheben.
3. **E-Auto mittags** bei Sonne laden.

---

## 6. Fehlerbehebung

> **Tipp:** Die **Protokolle-Seite** (*Einstellungen → System → Protokolle*) ist das wichtigste Werkzeug zur Fehlersuche. Dort aktivierst du den **Debug-Modus**, filterst System-Logs nach Fehlern und kopierst Logs per Knopf direkt in ein GitHub-Issue. Details in [Teil III §8.4](HANDBUCH_EINSTELLUNGEN.md#8-system).

### SOLL/IST-Vergleich zeigt 0 kWh

**Problem:** In der Komponenten-Sicht **PV-Anlage** werden keine IST-Werte angezeigt.

**Lösung:**
1. Prüfe, ob PV-Module als Komponenten angelegt sind (*Einstellungen → Komponenten*).
2. Prüfe, ob Monatsdaten mit PV-Erzeugung existieren (*Einstellungen → Daten → Monatsdaten*).
3. Prüfe, ob im Cockpit das richtige Jahr ausgewählt ist.

### CSV-Import schlägt fehl

**Problem:** Beim Import (*Einstellungen → Integration → Import-Assistenten*) erscheint eine Fehlermeldung.

**Lösung:**
1. Vorlage neu herunterladen (Spalten können sich ändern).
2. Spaltentrennzeichen prüfen (Semikolon `;` oder Komma `,`).
3. Dezimaltrennzeichen prüfen (Punkt `.` verwenden).
4. Bei Legacy-Spalten-Fehlern die einzelnen Komponenten-Spalten statt `PV_Erzeugung_kWh` verwenden.
5. Prüfen, ob negative Werte in den Daten stehen (nicht erlaubt).

### Wetter-Daten nicht verfügbar

**Problem:** „Wetter abrufen" zeigt einen Fehler.

**Lösung:**
1. Koordinaten der Anlage prüfen (*Einstellungen → Stammdaten → Anlage*).
2. Internetverbindung prüfen.
3. Die Open-Meteo-API kann kurzzeitig überlastet sein – später erneut versuchen.
4. *Protokolle → System-Logs*: nach „Open-Meteo" oder „Bright Sky" suchen.

### MQTT-Verbindung fehlgeschlagen

**Problem:** Der Verbindungstest zu MQTT schlägt fehl.

**Lösung:**
1. Läuft der MQTT-Broker? (`docker ps` oder HA-Add-on-Status)
2. Host/Port korrekt? (`core-mosquitto` bei HA, sonst die IP des Brokers)
3. Benutzer/Passwort korrekt?
4. Firewall-Regeln prüfen.
5. *Protokolle → Aktivitäten*: Kategorie „MQTT" zeigt Start- und Verbindungsfehler; „Connector-Test" zeigt Verbindungstest-Details.

### Dashboard zeigt keine Daten

**Problem:** Alle Kennzahlen zeigen 0 oder „—".

**Lösung:**
1. Sind Monatsdaten vorhanden? (*Einstellungen → Daten → Monatsdaten*)
2. Ist im Cockpit das richtige Jahr ausgewählt?
3. Sind Strompreise konfiguriert? (*Einstellungen → Stammdaten → Strompreise*)
4. Browser-Cache leeren (Strg+Shift+R).
5. *Protokolle → Aktivitäten*: Kategorie „HA-Statistiken" prüfen, ob der HA-Import funktioniert hat.

### Setup-Wizard erscheint erneut

**Problem:** Nach dem Abschluss startet der Wizard wieder.

**Lösung:** Der Wizard richtet sich nach der **Datenbank**, nicht nach dem Browser-Speicher: Solange **keine Anlage** in der Datenbank liegt, erscheint er bei jedem Start – auch wenn der Browser die Einrichtung als „abgeschlossen" vermerkt hat. Taucht der Wizard also erneut auf, wurde beim ersten Durchlauf keine Anlage gespeichert.
1. Lege im Wizard eine Anlage an (Schritt **Anlage**) und schließe ihn ab.
2. Prüfe in den *Protokollen*, ob beim Speichern der Anlage ein Fehler auftrat.
3. Möchtest du den Wizard **absichtlich** erneut durchlaufen, kannst du den Browser-Speicher zurücksetzen (LocalStorage-Schlüssel `eedc_setup_wizard_completed` und `eedc_setup_wizard_state`) und die Seite neu laden.

### Monatssumme bleibt auf einem festen Wert stehen

**Problem:** Die Monats-Summe (z. B. PV-Erzeugung, Einspeisung) bleibt konstant, obwohl Live- und Tagesdaten korrekt weiterlaufen.

**Lösung:** Bei Sensoren mit **Tagesreset** (der Zähler springt täglich um 0:00 auf 0, z. B. „Erzeugung heute") bildet eedc die Monatssumme aus der reset-bereinigten `sum`-Spalte der HA-Statistik (identisch zum HA Energy Dashboard).
1. Öffne den Monat im Cockpit (*Cockpit → Monat*) erneut – die Summe wird neu berechnet.
2. Passt sie weiterhin nicht, prüfe in der Datenquellen-Zuordnung, ob der gemappte Sensor `state_class: total_increasing` hat. Der Daten-Checker zeigt das unter der Kategorie „Sensor-Zuordnung – HA-Statistics" (siehe [Teil III §5.3](HANDBUCH_EINSTELLUNGEN.md#5-daten)).

### IST-Wert hat ein ⚠ neben den Tageswerten

**Problem:** In der Prognose-Auswertung oder in der Werte-Tabelle erscheint ein ⚠ neben einem IST-Wert.

**Lösung:** Ein Klick auf das ⚠ öffnet einen Reparatur-Popover mit den fehlenden Stunden und dem Knopf **„Tag neu berechnen"** (idempotent; holt fehlende Snapshots aus der HA-Langzeitstatistik nach).
1. Bei einzelnen fehlenden Stunden: Reparatur-Popover → „Tag neu berechnen".
2. Bei vielen fehlenden Tagen nach einem Add-on-Neustart: kurz warten – eedc holt nach dem Start die letzten Stunden je Anlage idempotent nach.
3. Bei systematisch fehlenden Werten: die Datenquellen-Zuordnung prüfen. Der Daten-Checker zeigt fehlende kWh-Zähler pro Komponente unter „Energieprofil – Zähler-Abdeckung".

### Backup-/CSV-/PDF-Download zeigt 401 in der HA-Companion-App

**Problem:** Ein Download (Backup, CSV-Export, PDF) liefert in der iOS-HA-Companion-App „401: unauthorized", im Browser funktioniert er.

**Lösung:** Auf v3.23.2 oder neuer aktualisieren. Seit v3.23.2 läuft der Download als `fetch + Blob` in der bestehenden Ingress-Session (statt in einem externen Safari-Tab ohne HA-Login) und funktioniert in HA-App und Browser gleichermaßen.

### „Wo ist etwas hingezogen?"

Kommst du von der alten Oberfläche und findest einen Bereich nicht wieder, hilft die Umzugs-Tabelle **„Wo ist X hin?"** in [Teil II: Bedienung §8](HANDBUCH_BEDIENUNG.md#8-anhang-wo-ist-x-hin). Kurz zusammengefasst: die Live-Ansicht ist **Cockpit → Live**, die Monatsberichte sind **Cockpit → Monat**, die Sensor-Zuordnung und der frühere MQTT-Inbound sind **Einstellungen → Datenquellen**, und der Monatsabschluss-Assistent ist zum Formular **Einstellungen → Daten → Monatsdaten** geworden.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
