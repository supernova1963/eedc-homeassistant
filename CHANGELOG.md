# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

---

## [3.12.7] - 2026-04-13

### Fix

- **Monatsbericht weicht von Auswertung→Tabelle ab** (#118): Für vergangene Monate hat der Monatsbericht-Endpunkt die in `Monatsdaten`/`InvestitionMonatsdaten` gespeicherten Werte stillschweigend mit Live-Werten aus der HA Long-Term Statistics-DB überschrieben (höhere Konfidenz). Wenn HA-Sensoren später umbenannt wurden oder die Recorder-DB für vergangene Monate driftete, zeigte der Monatsbericht andere Zahlen als die Auswertungs-Tabelle — selbst nach abgeschlossenem Monat. Fix: HA-Stats werden für vergangene Monate nur noch als Fallback verwendet (`setdefault`), nicht mehr als Override. Aktueller Monat bleibt unverändert. Auslöser: Safi105.

---

## [3.12.6] - 2026-04-13

### Fix

- **T-Konto Mobile als Gewinn-und-Verlust-Rechnung** (#117): Auf Mobile wird das T-Konto zur G+V umgebaut. SOLL/HABEN-Überschriften entfallen (passen ohne nebeneinanderliegende Konten nicht mehr), die Ergebniszeile wandert aus beiden Blöcken in eine eigene "Gewinn"/"Verlust"-Zeile darunter, und die Summen zeigen jetzt die tatsächlichen Kosten- bzw. Ertragsbeträge statt der um den Gewinn korrigierten T-Konto-Ausgleichssummen. Desktop bleibt unverändert. Auslöser: TomHarm.

### Feat

- **WetterWidget Chart-Toggle PV/Verbrauch/Beides** (#119): Drei Buttons rechts neben der Chart-Überschrift im "Wetter heute"-Diagramm — "Nur PV / Nur Verbrauch / Beides", Auswahl pro Anlage in localStorage. Default bleibt "Beides", die reduzierten Sichten blenden Stack/Legende entsprechend ein und aus. Auslöser: felixlen.
- **Monatsberichte: Individuelle Sektions-Reihenfolge**: Jede Sektion (Energie-Bilanz, Finanzen, Community, Speicher, WP, eMob, BKW, Sonstiges) hat im Header zwei kleine Pfeile zum Verschieben nach oben/unten. Reihenfolge wird in localStorage gespeichert.
- **Speicher: Wirkungsverluste in Euro**: Neue Zeile unter der kWh-Bilanz zeigt die Opportunitätskosten des Roundtrip-Verlusts — anteilig nach Lade-Quelle: PV-Anteil × Einspeisepreis (entgangener Erlös) + Netz-Anteil × Bezugspreis. Tooltip erklärt die Aufschlüsselung. Rein informativ, nicht Teil der T-Konto-Bilanz.

---

## [3.12.5] - 2026-04-12

### Fix

- **Vollbackfill NameError**: `timedelta` fehlte als Import in `get_hourly_sensor_data` → "Verlauf nachberechnen" schlug mit `NameError: name 'timedelta' is not defined` fehl.

---

## [3.12.4] - 2026-04-12

### Fix

- **Vollbackfill Fehlerdiagnose**: Interne Fehler beim "Verlauf nachberechnen" werden jetzt als lesbare Fehlermeldung zurückgegeben statt als stiller 500er.

---

## [3.12.3] - 2026-04-12

### Fix

- **Vollbackfill 500-Fehler**: Fehlende DB-Migration für Spalte `komponenten` in `tages_energie_profil` führte zu einem internen Serverfehler beim Ausführen von "Verlauf nachberechnen". Migration wird jetzt beim Add-on-Start automatisch ergänzt.

---

## [3.12.2] - 2026-04-12

### Feat

- **Post-Save-Dialog im Sensor-Mapping-Wizard**: Nach dem Speichern geänderter Sensor-Zuordnungen erscheint ein kontextueller Dialog. Bei geänderten Live-Sensoren kann der Energieprofil-Verlauf direkt neu berechnet werden. Bei geänderten Felder-Sensoren wird zum HA Statistik-Import (mit Überschreiben) navigiert.

### Fix

- **Community: 0-Wert-Einlieferungen** (#107): Anlagen mit kaputtem Sensor-Mapping die `ertrag_kwh=0` einlieferten, verfälschten den Community-Durchschnitt. Fix: EEDC sendet keine Monate ohne PV-Erzeugung mehr. Community-Server lehnt `ertrag_kwh≤0` mit HTTP 400 ab.
- **Energieprofil-Backfill mit veralteten Sensoren**: Wenn im Live-Sensor-Mapping noch alte/umbenannte HA-Sensoren steckten (z.B. nach Sensor-Austausch im Wizard), scheiterte "Verlauf nachberechnen" mit einem Fehler. Veraltete Sensoren werden jetzt automatisch ignoriert.
- **Sensor-Mapping-Wizard**: Beim Speichern werden Live-Sensoren die in HA nicht mehr existieren automatisch aus dem Mapping entfernt.

---

## [3.12.1] - 2026-04-12

### Feat

- **Energieprofil-Vollbackfill**: Neuer Button "Verlauf nachberechnen" im Sensor-Mapping-Wizard (letzter Schritt). Berechnet stündliche Energieprofile rückwirkend aus HA Long-Term Statistics — unabhängig von der ~10-Tage-Grenze der Sensor-History. Ermöglicht erstmals die Befüllung der gesamten HA-History auf einen Schlag.

### Fix

- **WetterWidget KPI-Aufräumung** (#100): ML/SFML-Tages- und Morgenprognose aus der KPI-Zeile entfernt. PV-Prognose (EEDC GTI) wird jetzt immer angezeigt. ML-Linie bleibt im Chart und in der Legende sichtbar.
- **Monatsberichte Scroll-Bug**: Zeitstrahl-Scrollen beeinflusste fälschlicherweise den Haupt-Viewport — `sticky` sitzt jetzt korrekt am äußeren Container.
- **Monatsberichte Sektions-Zustand**: Auf-/Zugeklappt-Zustand aller Sektionen (Energie-Bilanz, Finanzen, Community etc.) wird jetzt per localStorage gespeichert — Finanzen öffnet nicht mehr immer aufgeklappt.

### Chore

- **Investitionsformular**: Deprecation-Banner für Ansprechpartner- und Wartungsfelder — diese werden in einer der nächsten Versionen entfernt und durch die Infothek ersetzt. Bereits eingetragene Daten bleiben erhalten.

---

## [3.12.0] - 2026-04-11

### Feat

- **Monatsberichte ersetzt "Aktueller Monat"**: Laufender Monat erscheint jetzt direkt im Zeitstrahl (grüner Pulse-Dot). Route `/cockpit/aktueller-monat` redirectet auf Monatsberichte. Refresh-Button und "Abschluss starten"-CTA (nur wenn Vergangenheitsmonate offen) im Titelbereich.
- **Energie-Bilanz Redesign**: Vergleichstabelle mit neuem "Ø [Monatsname]"-Vergleich (z.B. alle März-Monate) statt sinnlosen Gesamt-Ø/Max/Min. SOLL/IST-Block mit großer Prozentanzeige, Fortschrittsbalken und Ampelfarben. PV-Verteilung als kompakte Horizontal-Balken statt großem Donut-Chart.
- **Community-Vergleich**: Neue Sektion zeigt Autarkie, EV-Quote, Einspeisung und Netzbezug gegen den Community-Median des gewählten Monats (▲/▼). Prominente Teilen-Aufforderung wenn Anlage noch nicht geteilt.
- **Mobile T-Konto**: SOLL und HABEN werden auf kleinen Screens untereinander dargestellt.
- **Mobile Vergleichstabelle**: Zahlenwerte ausgeblendet, nur Δ-Badge mit Tooltip sichtbar.

## [3.11.19] - 2026-04-10

### Fix

- **Fronius Custom Report — Zwei Wechselrichter**: Alle `"Energie | [WR-Modell]"`-Spalten werden jetzt summiert (statt nur die erste). Betrifft Anlagen mit mehreren Wechselrichtern (z.B. Symo 4.5 + GEN24 10.0). Auslöser: Joachim-xo.
- **Fronius Custom Report — Wattpilot-Ladedaten**: `"Energie vom Netz/Batterie/PV an Wattpilot"` wird zu `wallbox_ladung_kwh` aggregiert und der konfigurierten Wallbox-Investition zugeordnet (bei mehreren Wallboxen: manuelle Auswahl im Import-Dialog).
- **Portal-Import — Dezimaleingabe Prozent-Anteile**: Tipp eines Kommas oder Punkts sprang den Wert auf 0. Fix: `valueAsNumber` statt `parseFloat`, `step={0.01}` statt `0.1` für 2-stellige Nachkommastellen.

## [3.11.18] - 2026-04-09

### Fix

- **Fronius Custom Report — PV-Spalte 0,00 kWh**: `"Energie | [Gerätemodell]"` wurde von `_normalize()` zu `"energie [modell]"` (Pipe entfernt) — Pattern `"energie |"` traf nie. Stattdessen griff `"ertrag"` auf `"Spezifischer Ertrag [kWh/kWp]"` → Werte ~0,38 als Wh ÷ 1000 = 0,00 kWh. Fix: Raw-Header-Suche auf `startswith("energie |")`, `"ertrag"` aus Patterns entfernt. Verifiziert mit echter CSV von Joachim-xo (365 Tage, 14 Spalten).

## [3.11.17] - 2026-04-09

### Fix

- **Fronius Solar.web Benutzerdefinierter Report: PV-Spalte korrekt erkannt**: Spaltenbezeichnung `"Energie | [Gerätemodell]"` (Pipe-Zeichen + Inverter-Name) wurde nicht als PV-Erzeugung erkannt — Parser griff fälschlich auf `"Spezifischer Ertrag"` (kWh/kWp) zurück. Auslöser: Joachim-xo.

### Feat

- **Aktueller Monat — Wärmepumpe Heizung/Warmwasser-Split**: Label umbenannt in "Wärmepumpe Summe", Heizung und Warmwasser werden als eingerückte Unterzeilen angezeigt (nur wenn Werte > 0 vorhanden). Auslöser: Issue #113.
- **Live-Dashboard — Prognoseabweichung mit %-Wert**: Anzeige erweitert von `+0.7 über Progn.` auf `+0.7 kWh über Progn. (+1%)`. Auslöser: Issue #114 (rapahl).

---

## [3.11.16] - 2026-04-09

### Fix

- **Energieprofil löschen: Bestätigungsmeldung bleibt sichtbar**: Meldung wird nach dem Seiten-Reload gesetzt und außerhalb des bedingten Datenbestand-Blocks gerendert — war vorher unsichtbar weil der Block nach dem Löschen (0 Einträge) ausgeblendet wird.

---

## [3.11.15] - 2026-04-09

### Fix

- **Energieprofil-Daten löschen: auch Tagessummen bereinigen**: Der Lösch-Button entfernt jetzt zusätzlich `TagesZusammenfassung` — diese enthält aggregierte Werte die den PV-Lernfaktor beeinflussen und bei falsch gemappten Sensoren ebenfalls korrumpiert waren. Monatsdaten bleiben erhalten. Auslöser: Joachim-xo.

---

## [3.11.14] - 2026-04-08

### Fix

- **Energieprofil-Daten löschen: 422-Fehler behoben**: DELETE-Endpoint-Pfad von `/alle/rohdaten` auf `/rohdaten` geändert — FastAPI hatte `alle` fälschlich als `anlage_id` (Integer) interpretiert.

---

## [3.11.13] - 2026-04-08

### Feat

- **Einstellungen → System: Button "Energieprofil-Daten löschen"**: Direkt im Datenbestand-Block, mit Bestätigungsdialog. Für Nutzer mit falsch gemappten Sensoren die fehlerhafte Daten in TagesEnergieProfil geschrieben haben. Monatsdaten bleiben erhalten, Scheduler berechnet neu (max. 15 Min). Auslöser: Joachim-xo.

---

## [3.11.12] - 2026-04-08

### Fix

- **WetterWidget: Verbrauchsprognose 1000x zu groß** (Regression v3.11.10): Bei unplausiblen DB-Werten (Median verbrauch_kw > 100 kW) wird auf HA-History-Fallback umgeschaltet statt fehlerhafte Werte zu verwenden. Zusätzlich: Debug-Endpoint `GET /api/energie-profil/{id}/debug-rohdaten` und Lösch-Endpoint `DELETE /api/energie-profil/{id}/rohdaten` zur Diagnose und Bereinigung. Auslöser: Joachim-xo (#231).

---

## [3.11.11] - 2026-04-08

### Fix

- **WetterWidget: Verbrauchsprognose 1000x zu groß** (Regression v3.11.10): Automatische Erkennung und Korrektur von historisch falsch gespeicherten Watt-Werten in `TagesEnergieProfil` (Median > 100 kW → /1000). Auslöser: Joachim-xo (#231).

---

## [3.11.10] - 2026-04-08

### Fix

- **Live-Dashboard: Verzögerung beim Öffnen nach HA-Neustart behoben**: Verbrauchsprofil für das WetterWidget liest jetzt primär aus der EEDC-DB (`TagesEnergieProfil`) statt über die HA-History-API. Eliminiert den 7-Tage-HA-History-Call der nach jedem Add-on-Neustart bis zu 15s Verzögerung verursachte. HA-History bleibt als Fallback für neue Installationen (< 2 Tage DB-Daten). Auslöser: Joachim-xo (#225).

---

## [3.11.9] - 2026-04-08

### Feat

- **Monat-Selektor in "Aktueller Monat"**: Monat und Jahr frei wählbar (bis 6 Jahre zurück). Refresh-Button deaktiviert für Vormonate. Für vergangene Monate werden nur gespeicherte Daten angezeigt (kein MQTT-Inbound). Auslöser: MartyBR (community.simon42.com #216).

---

## [3.11.8] - 2026-04-08

### Fix

- **EnergieFluss Knoten-Tooltips**: Desktop-Hover (native `<title>`-Kindelemente) und Mobile-Touch (`data-title` via `useTouchTitleTooltip`) funktionieren jetzt gleichzeitig. Haus-Knoten-Text in Variable `hausTip` vor `return()` extrahiert.

---

## [3.11.7] - 2026-04-08

### Fix

- **EnergieFluss Mobile-Tooltips**: React rendert `title`-Props auf SVG-Elementen nicht als DOM-Attribute → `getAttribute('title')` lieferte immer `null`. SVG-Knoten nutzen jetzt `data-title="..."`, Hook liest `data-title || title`. HTML-Elemente (Buttons) behalten `title=""`.

---

## [3.11.6] - 2026-04-08

### Fix

- **Y-Achsenbeschriftung in PV-Anlage Charts**: `PVAnlageDashboard` und `PVStringVergleich` — `unit`-Prop entfernt, `useMemo`-Formatter analog AktuellerMonat (MWh ab >10k kWh), `width` auf 80 erhöht. Verhindert Abschneiden der führenden Ziffer.
- **Y-Achsenbeschriftung in Speicher-Charts**: Ladung/Entladung (kWh-Einheit), Zyklen (1 Dezimalstelle), Effizienz (`domain` von `[80,100]` auf `[0,100]` + %-Formatter) — verhindert Recharts-Fallback mit rohen Float-Ticks wenn Werte außerhalb des fixen Domains liegen.
- **Solar-Aussicht Prognose-Quelle**: Live-Dashboard Heute-Prognose nutzt `wetter.pv_prognose_kwh` (GTI + Temperaturkorrektur) statt `tag.pv_ertrag_kwh` — angezeigte Zahl und Differenzrechnung sind nun konsistent.
- **EnergieFluss Mobile-Tooltips**: SVG `<title>`-Kindelemente durch `title=""`-Attribute ersetzt — globaler `useTouchTitleTooltip`-Hook greift jetzt auch auf Mobile (Tap statt Hover).

---

## [3.11.5] - 2026-04-07

### Neu

- **PV-String Auslastungs-Füllung im Energiefluss**: PV-String-Boxen füllen sich analog zur Batterie-SoC-Anzeige von unten proportional zur aktuellen Auslastung (Ist-W / kWp). Farbe: hellgrün (< 40%), gelb (40–80%), amber (> 80%). Tooltip zeigt Auslastung in % und installierte kWp. Auslöser: dietmar1968 (#208).

### Fix

- **Y-Achse abgeschnitten in PV/Auswertungs-Charts**: `width={60}` + k-Notation (≥ 1000 kWh → "x.xk kWh") in PVAnlageDashboard, PVAnlageTab, EnergieTab, KomponentenTab. Auslöser: dietmar1968 (#208).

---

## [3.11.4] - 2026-04-07

### Änderung

- **Live Dashboard Solar-Aussicht überarbeitet**: PV-Prognose-Card entfernt — Solar-Aussicht Heute zeigt den Wert direkt. Verbleibend/Über Prognose klein darunter. Neue kompakte Zeile "Verbrauchsprognose" (Haus + Batterie + WP + Wallbox + Sonstige) mit ⓘ-Tooltip. VM/NM als Spaltenüberschrift. Alle drei Tage einheitlich prominent. Vertikale Ausrichtung der kWh-Werte per Grid. Auslöser: Rainer-Feedback.

---

## [3.11.3] - 2026-04-07

### Fix

- **Plausibilitätsfilter für Sensor-Spikes im Tagesverlauf**: Beim HA-Neustart liefern Sensoren kurzzeitig Extremwerte statt `unavailable`. Diese werden jetzt per Typ-Grenze herausgefiltert (Wallbox/E-Auto/Speicher: 50 kW, WP: 20 kW, BKW: 2 kW, PV: 100 kW). Betrifft HA- und MQTT-Pfad. Auslöser: Fronius Wattpilot HACS-Integration (Joachim-xo).
- **kWp Nachkommastellen in Investitionen**: Im Investitionen-Formular war `step="0.1"` statt `step="0.01"` gesetzt. Betrifft besonders 750W-Module (0.75 kWp). (eedc#3)

---

## [3.11.2] - 2026-04-07

### Fix

- **Negative Cache für Open-Meteo API-Fehler**: Bei Open-Meteo-Ausfällen (502 Bad Gateway) wurde bisher bei jedem Request sofort wieder angefragt, was zu 429 Rate Limiting führte. Jetzt wird nach einem Fehler der Cache-Key für 1–5 Minuten gesperrt (429→5 Min, 502→2 Min, Timeout→1 Min). Betrifft Live-Wetter, Solar-Prognose, Forecast und Archiv. Auslöser: Open-Meteo Ausfall 2026-04-07.

---

## [3.11.1] - 2026-04-07

### Fix

- **Y-Achse in Aktueller-Monat-Charts abgeschnitten** (#112): Dynamischer Formatter für Vorjahresvergleich und SOLL/IST-Vergleich. Werte ≤ 10.000 kWh werden ganzzahlig in kWh angezeigt, darüber in MWh mit einer Nachkommastelle (z.B. `10.5 MWh`). YAxis-Breite auf 90 px erhöht.
- **Backup-Seite — Infothek-Anhänge**: Klarstellung dass PDFs und Fotos nicht im JSON-Export enthalten sind — sie werden als BLOB in der `eedc.db` gespeichert. Hinweis-Block mit Anleitung für HA Add-on (HA-Backup) und Standalone (eedc.db manuell sichern).

---

## [3.11.0] - 2026-04-06

### Neu

- **Energieprofil Etappe 2 — Tagesdetail + Wochenvergleich** (Beta): Neuer Tab "Energieprofil" in den Auswertungen. Persistierte Stundenwerte aus `TagesEnergieProfil` werden als interaktiver Butterfly-Chart (analog Live-Tagesverlauf) und vollständige Tabelle dargestellt.
  - **Tagesdetail**: Datum-Picker, gestapelter AreaChart (Erzeuger oben / Verbraucher unten), gestrichelte Gesamterzeugungslinie. Alle Sonstiges-Investments (Poolpumpe, BHKW, …) erscheinen namentlich als eigene Serien. KPI-Zeile: Gesamterzeugung, Verbrauch, Netzbezug, Einspeisung, Autarkie, Temperatur.
  - **Wochenvergleich**: 9 Gruppen (Mo–Fr, Sa–So, einzelne Wochentage), 4 Zeiträume (30/90/180/365 Tage), 3 Kennzahlen (Verbrauch / PV / Netzbezug).
  - **Tabellen**: Spaltenauswahl mit Gruppen, sortierbare Header, CSV-Export, localStorage-Persistenz — analog Auswertung-Tabelle. Berechnete Spalten Gesamterzeugung und Hausverbrauch.
  - **Beta-Badge + Sammel-Screen**: Tab trägt "Beta"-Kennzeichnung. Solange < 8 Tage Stundenwerte vorhanden sind, erscheint ein Fortschrittsbalken statt leerer Charts.
  - **Info-Panel**: Ausklappbare Erläuterung zu Datenquellen (HA-History / MQTT-Snapshots), Aggregations-Zeitplan und Felddefinitionen.

### Fix

- **Energieprofil — Anlage-Wechsel**: `key={anlageId}` erzwingt vollständigen Remount bei Anlagenwechsel, damit alle internen States (Datum, Daten, extraSerien) korrekt zurückgesetzt werden.

---

## [3.10.6] - 2026-04-06

### Fix

- **MQTT-Standalone: Tagesverlauf-Chart und Energieprofil-Stundenwerte fehlten**: Docker-Standalone-Installationen ohne HA-Integration sammelten keine `TagesEnergieProfil`-Daten, weil `get_tagesverlauf()` ohne HA sofort leere Serien zurückgab. Neue Tabelle `mqtt_live_snapshots` speichert alle 5 Min die aktuellen MQTT Live-Watt-Werte (Einspeisung, Netzbezug, Investitionsleistungen). `live_tagesverlauf_service` nutzt diese als Fallback — damit laufen Tagesverlauf-Chart und Energieprofil-Aggregation auch im reinen MQTT-Modus.

---

## [3.10.5] - 2026-04-06

### Neu

- **MQTT-Gateway: 7 neue Geräte-Presets**: Shelly EM (1-phasig), Shelly Plus Plug S / PM Mini, AhoyDTU, Victron Venus OS, sonnenBatterie, Tasmota Steckdose und Zigbee2MQTT Steckdose. Gesamt jetzt 12 Presets in 5 Gruppen (Shelly / Solar+WR / Speicher / Wallbox / Sonstiges).
- **MQTT-Gateway: Investitions-Kontext für Wallbox und Speicher-Presets**: Presets für Geräte die einer konkreten Investition zuzuordnen sind (go-eCharger, sonnenBatterie, Shelly PM, Tasmota Steckdose, Zigbee2MQTT) fragen jetzt die Ziel-Investition ab und mappen auf `live/inv/{id}/leistung_w` statt auf ein globales Topic. Die Preset-Auswahl zeigt jetzt Gruppen statt einer flachen Liste.

### Fix

- **MQTT-Gateway go-eCharger**: Ziel-Topic korrigiert von `live/wallbox_w` auf `live/inv/{id}/leistung_w` — Ladeleistung wird jetzt korrekt der Wallbox-Investition zugeordnet.

---

## [3.10.4] - 2026-04-06

### Neu

- **BKW mit integriertem Speicher: Speicher-Investition dem Balkonkraftwerk zuordnen**: Für Geräte wie den Anker Solix (BKW + integrierter Akku) kann die Speicher-Investition jetzt direkt dem zugehörigen Balkonkraftwerk zugeordnet werden. Das Dropdown „Gehört zu" im Speicher-Formular zeigt jetzt Wechselrichter und Balkonkraftwerke zur Auswahl. Für die vollständige Live-Dashboard-Anzeige (Batterie-Knoten im Energiefluss) muss die Batterieleistung als separate **Speicher-Investition** mit eigenem bidirektionalen Sensor erfasst werden.
- **UX-Hinweis bei BKW „Mit Speicher"**: Beim Aktivieren der „Mit Speicher"-Option im Balkonkraftwerk-Formular erscheint ein Hinweis, dass für vollständige Auswertungen eine separate Speicher-Investition erforderlich ist.

### Refactoring (intern, kein User-Impact)

- **Basis-MQTT-Live-Topics aus Registry**: Die 8 Basis-Live-Topics (einspeisung_w, netzbezug_w, pv_gesamt_w, sfml_*, aussentemperatur_c) werden jetzt dynamisch aus `BASIS_LIVE_FELDER` in `field_definitions.py` generiert. Neues Basis-Live-Feld → nur noch dort eintragen.

---

## [3.10.3] - 2026-04-06

### Behoben

- **Tagesverlauf: Fehlende Investments sichtbar machen (#109)**: Wenn ein Investment (z.B. Wallbox) keinen HA-Leistungssensor konfiguriert hat, wird es im Tagesverlauf-Chart nicht dargestellt — das war bisher lautlos. Jetzt erscheint ein amber-farbener Hinweis: "Nicht dargestellt (kein HA-Leistungssensor): Wallbox XY". Hinweis: Der Tagesverlauf benötigt zwingend eine HA-Entity für `leistung_w` in der Sensor-Zuordnung — MQTT-only Investments können mangels HA-History nicht angezeigt werden.
- **Live-Dashboard: Datenquellen-Unterschied kennzeichnen (#108)**: Die beiden Charts zeigen konzeptionell unterschiedliche Daten. Kleine Labels machen das jetzt sichtbar: EnergieFluss zeigt "Momentwerte · aktualisiert alle ~30s", Tagesverlauf-Chart zeigt "10-Min-Durchschnitte aus HA-History". (Gemeldet von Joachim-xo)

---

## [3.10.2] - 2026-04-06

### Behoben

- **WP Dashboard: JAZ/Strom Warmwasser zeigt 0.00 statt "–"**: Wenn `strom_warmwasser_kwh = 0` (keine Daten eingetragen), zeigen JAZ Warmwasser und Strom Warmwasser jetzt korrekt "–" statt "0.00" bzw. "0.0 MWh". (Gemeldet von Rainer)
- **Monatsabschluss Wechselrichter: PV-Erzeugung-Feld bei getrennten PV-Arrays**: Das Eingabefeld "PV-Erzeugung (kWh)" im Wechselrichter-Schritt des Monatsabschlusses wird jetzt automatisch ausgeblendet wenn separate PV-Modul-Investments vorhanden sind — die Erzeugung wird dort bei den einzelnen Segmenten erfasst. (Gemeldet von Rainer)
- **Monatsabschluss: Tab-Label "wechselrichter" klein geschrieben**: Tab und Abschnittsüberschrift zeigen jetzt korrekt "Wechselrichter" (Großschreibung). Gleiches für "Sonstiges". (Gemeldet von Rainer)

### Refactoring (intern, kein User-Impact)

- **`bedingung_anlage` in field_definitions.py**: Neue Bedingungsebene in der Investitions-Feld-Registry. Bisher gab es nur `bedingung` (Investment-Parameter, z.B. `arbitrage_faehig`). Mit `bedingung_anlage` können Felder jetzt auch abhängig vom Anlage-Kontext (andere Investments) ein-/ausgeblendet werden. Erster Einsatz: Wechselrichter `pv_erzeugung_kwh` mit `bedingung_anlage: "keine_pv_module"`.
- **Phase 4a abgeschlossen**: Backend-Ableitung von `ERWARTETE_FELDER`, `energy_keys_by_typ`, `SOC_TYPEN` und `FELD_LABELS` aus Registry (kein hardcodierter Block mehr in sensor_mapping.py, live_mqtt_inbound.py, ha_statistics.py).

---

## [3.10.1] - 2026-04-06

### Neu

- **Portal-Import: Zuordnungs-Wizard**: Bei mehreren Investments gleichen Typs (z.B. 2 PV-Strings, 2 Speicher) zeigt der Portal-Import-Wizard jetzt einen optionalen Zuordnungs-Schritt. PV-Erzeugung und Batterie-Werte können prozentual aufgeteilt werden, Wallbox und E-Auto per Auswahl zugeordnet werden. Standard: proportionale Verteilung nach kWp/Kapazität. Bei eindeutiger Zuordnung entfällt der Schritt.

### Behoben

- **Portal-Import: Batterie-Doppelzählung**: `md.batterie_ladung_kwh` / `md.batterie_entladung_kwh` wurden bisher immer in `Monatsdaten` gesetzt, auch wenn gleichzeitig `_distribute_legacy_battery_to_storages()` dieselben Werte in `InvestitionMonatsdaten` schrieb. Die Legacy-Felder werden jetzt nur noch als Fallback gesetzt (kein Speicher angelegt).
- **Portal-Import: `md.pv_erzeugung_kwh` fehlte**: Bei vorhandenen PV-Modulen wurde `md.pv_erzeugung_kwh` nicht gesetzt. Berechnungen die dieses Aggregat-Feld lesen (z.B. Cockpit) sahen 0 statt des tatsächlichen Werts.
- **Portal-Import: E-Auto-Typ-String**: `i.typ == "eauto"` → `"e-auto"` — E-Auto-km-Daten wurden nie in `InvestitionMonatsdaten` geschrieben.

### Refactoring (intern, kein User-Impact)

- **Import-Registry — `field_definitions.py` als Single Source of Truth**: Alle Investitions-Felder sind jetzt mit CSV-Suffix, Aggregat-Zuordnung und Datentyp annotiert. `_import_investition_monatsdaten_v09` (helpers.py) und `_build_investition_felder` / `_detect_investition_spalten` (custom_import.py) werden vollständig aus der Registry abgeleitet — kein hardcodierter Typ-Check mehr. Neue Felder oder Investitionstypen nur noch in `field_definitions.py` eintragen.
- **Lücken L1–L6 geschlossen**: Wallbox `ladung_pv_kwh` (L1), WP `Strom_Heizen/Warmwasser_kWh` (L2), BKW `Eigenverbrauch_kWh` (L3), Sonstiges/Erzeuger `eigenverbrauch_kwh` + `einspeisung_kwh` (L4), Sonstiges/Verbraucher `bezug_pv/netz_kwh` (L5), Sonstiges/Speicher Feldnamen-Korrektur (L6 — Daten wurden bisher in Berechnungen ignoriert).

---

## [3.10.0] - 2026-04-06

### Neu

- **Custom-Import-Wizard: Investitions-Spalten (#111)**: Der Custom-Import-Wizard erkennt und importiert jetzt Investitions-Daten korrekt. Backend: neuer `/apply/{anlage_id}`-Endpoint ruft `_import_investition_monatsdaten_v09` auf und schreibt direkt in `InvestitionMonatsdaten` pro Modul (PV, Speicher, E-Auto etc.). `/analyze` erkennt automatisch EEDC-Investitions-Spalten und generiert personalisierte Dropdown-Felder gruppiert nach Investitionstypen. Vorzeichen-Inversion (↕-Toggle) pro Mapping-Zeile. Frontend: Anlage-Auswahl in Schritt 1, erkannte Investitions-Spalten als grüne Read-only-Sektion, Dark-Mode-Fix für select-Elemente.

### Geändert

- **Stepper-Navigation im Monatsabschluss-Wizard**: Kreise mit Verbindungslinien statt flacher Buttonreihe. Abgeschlossene Schritte grün mit Haken, aktiver Schritt primary-farbig.
- **Layout Padding**: Hauptbereich-Padding oben reduziert (`pt-3` → `pt-1`) für kompakteres Erscheinungsbild.

### Behoben

- **Fronius CSV-Parser Wh→kWh (#107)**: Fronius exportiert Energiedaten in Wh, EEDC hat diese als kWh eingelesen. Konvertierungsfaktor 1/1000 ergänzt.
- **Y-Achse in AktuellerMonat-Charts abgeschnitten (#186)**: `YAxis width={70}` auf allen kWh-Achsen — verhindert Abschneiden bei Werten >3.000 kWh.

---

## [3.9.9] - 2026-04-04

### Behoben

- **Monatsabschluss 500-Fehler**: `NameError: kategorie` beim Aufruf des Monatsabschluss-Wizards. Die Variable wurde im Refactoring v3.9.7 entfernt, der Aufruf `InvestitionStatus(kategorie=kategorie)` blieb aber übrig. Fix: `inv_kategorie` wird jetzt korrekt aus `inv.parameter` gelesen (nur für Typ "sonstiges" relevant).

---

## [3.9.8] - 2026-04-04

### Behoben

- **Y-Achse in Vorjahresvergleich abgeschnitten**: Beschriftungen wie "300 kWh" wurden links abgeschnitten. `margin={{ left: 10 }}` im BarChart behebt das. (Gemeldet von MartyBr, community.simon42.com #186)
- **Touch-Tooltips auf Mobile (#104)**: Info-Icons und `title=""`-Attribute funktionierten auf Mobilgeräten nicht (kein Hover). Zweistufige Lösung: `FormelTooltip`/`SimpleTooltip` erhalten zentralen `useTooltipInteraction`-Hook mit onClick-Toggle; globaler `useTouchTitleTooltip`-Hook in `App.tsx` aktiviert Touch-Support für alle `title=""`-Attribute im gesamten Frontend automatisch. (Gemeldet von dietmar1968 + joachim-xo, community.simon42.com #183/#184)

---

## [3.9.7] - 2026-04-04

### Behoben

- **KPI-Zeile: ML aus Verbleibend entfernt**: "PV-Prognose" und "Verbleibend" verwenden jetzt ausschließlich EEDC-Werte. ML-Vergleich ist bereits in der Solar-Aussicht-Sektion vorhanden.

---

## [3.9.6] - 2026-04-04

### Neu

- **Seamless-Wettermodelle**: Neue Optionen in den Anlage-Stammdaten — ICON Seamless (D2→EU→Global, empfohlen für DE/AT/CH), MeteoSwiss Seamless (Alpenraum) und ECMWF Seamless (Global, 15 Tage). Diese kaskadieren intern bei Open-Meteo automatisch zwischen Hoch- und Grobauflösung.

### Behoben

- **Tageslicht-Zeitschiene ändert sich nicht (#102)**: Countdown "noch Xh Ym Zs Tageslicht" aktualisiert sich jetzt sekündlich statt alle 30 Sekunden. Progress-Bar-Marker bewegt sich flüssig. Sonnenstunden-Bisher/Rest werden jetzt minuten-präzise berechnet (anteilige aktuelle Stunde) statt nur stündlich zu wechseln.
- **"Verbleibend"-KPI unklar (#103)**: Label zeigt jetzt "Verbleibend (EEDC)" bzw. "Verbleibend (ML)" — der User sieht sofort welches Modell verwendet wird. PV-Prognose-Box zeigt zusätzlich den ML-Vergleichswert wenn SFML verfügbar. Tooltip erklärt die Formel: Tagesprognose − bisher erzeugt = verbleibend.
- **Wettermodell-Einstellung ignoriert in Kurzfrist-Aussichten**: `anlage.wetter_modell` wurde nur in der Solar-Prognose berücksichtigt, nicht in Kurzfrist-Aussichten, Prognose-Service und Prefetch. Alle drei Kanäle verwenden jetzt das konfigurierte Modell.
- **Prefetch Cache-Key-Mismatch Live-Wetter**: Der Prefetch hat den Live-Wetter-Cache unter einem anderen Key gespeichert als der Endpoint gelesen hat (`:m=` Suffix fehlte). Dadurch wärmte der Prefetch den Cache nutzlos. Jetzt verwenden beide denselben Key.

### Refactoring (intern, kein User-Impact)

- Wetter-Modul aufgeteilt: `wetter_service.py` (979 Z.) → `services/wetter/` Package (cache, open_meteo, pvgis, orchestrator, models, utils)
- Felddefinitions-Schicht: `backend/core/field_definitions.py` als Single Source of Truth für Monatsdaten-Felder — MonatsabschlussWizard, MonatsdatenForm und CSV-Template nutzen jetzt dieselben kanonischen Feldnamen
- Naming-Fixes in `verbrauch_daten`: `speicher_ladung_netz_kwh` → `ladung_netz_kwh`, `entladung_v2h_kwh` → `v2h_entladung_kwh`
- MonatsdatenForm: 6 Section-Komponenten ausgelagert (1.627 → 970 Zeilen)
- Cockpit-Router aufgeteilt: `cockpit.py` (2.327 Z.) → `cockpit/` Package (6 Module)

---

## [3.9.5] - 2026-04-04

### Behoben

- **Außentemperatur im Live-Dashboard**: Temperatur-Anzeige fehlte, weil die aktuelle Stunde nur in den Stunden 6–20 gesucht wurde. Jetzt werden alle 24 Stunden berücksichtigt. Zusätzlich wird `datetime.now()` mit Europe/Berlin-Timezone aufgerufen, damit Docker-Container mit UTC korrekt funktionieren.
- **Außentemperatur MQTT-Fallback**: Wenn der HA-Sensor nicht erreichbar ist (Standalone-Betrieb), wird die Außentemperatur jetzt aus dem MQTT-Inbound-Cache gelesen.
- **MQTT-Inbound Topic für Außentemperatur**: Das Topic `aussentemperatur_c` fehlte in der generierten Topic-Liste und konnte daher nicht per MQTT-Automation befüllt werden.

---

## [3.9.4] - 2026-04-03

### Behoben

- **Statistik-Import: Verwaiste Sensor-Zuordnungen**: Gelöschte Investitionen hinterließen verwaiste Einträge im Sensor-Mapping, die als "Investition X" mit Warndreieck im Import erschienen. Verwaiste Einträge werden jetzt übersprungen. Beim Löschen einer Investition wird der Mapping-Eintrag automatisch mitentfernt.
- **Fronius CSV-Import: Batterie + Eigenverbrauch**: Batterie-Spalten (Ladung/Entladung) werden jetzt erkannt. "Direkt verbraucht" wird korrekt als Eigenverbrauch statt als Verbrauch gemappt. Spalten-Deduplizierung verhindert Doppelzuordnungen bei ähnlichen Spaltennamen.

### Verbessert

- **Live-Dashboard: Prognose-Übererfüllung**: Wenn die PV-Erzeugung die Tagesprognose übertrifft, wird jetzt "Über Prognose +X kWh" in Grün angezeigt statt das Feld komplett auszublenden.

---

## [3.9.3] - 2026-04-03

### Verbessert

- **Sonnenstunden im Live-Dashboard (#96)**: Neue Anzeige über der SunProgressBar — links Ist-Sonnenstunden bis jetzt, rechts prognostizierte Sonnenstunden bis Sonnenuntergang. Nach Sonnenuntergang wird die Tagessumme angezeigt. Werte basieren auf stündlichen Open-Meteo-Daten (Ist für vergangene Stunden, Prognose für zukünftige).
- **Live-Wetter respektiert Wettermodell**: Der Live-Wetter-Endpoint nutzt jetzt das in den Anlage-Stammdaten konfigurierte Wettermodell (ICON-D2, MeteoSwiss, ECMWF etc.) statt immer best_match.
- **"Sonnenschein" → "Tageslicht"**: Die verbleibende Zeit bis Sonnenuntergang wird jetzt als "Tageslicht" bezeichnet (korrekterer Begriff, da auch bei Bewölkung).

---

## [3.9.2] - 2026-04-03

### Behoben

- **Live-Wetter: NameError nach Sonnenstunden-Refactoring**: `daily`-Variable fehlte nach Umbau auf stündliche `sunshine_duration` — Wetter-Widget zeigte keine Daten (Sunrise, Sunset, Temperatur Min/Max fehlten).

---

## [3.9.1] - 2026-04-03

### Verbessert

- **Monatsabschluss: Anderen Monat bearbeiten (#97)**: Monat-Picker im Wizard entfernt (war fehleranfällig). Stattdessen neuer Kalender-Button (📅) pro Zeile in der Monatsdaten-Tabelle — navigiert direkt zum Monatsabschluss-Assistenten mit korrekt vorgeladenen Daten. Im Wizard selbst ein dezenter Link zurück zur Monatsdaten-Tabelle.
- **Sonnenstunden genauer (#96)**: Stündliche `sunshine_duration`-Werte summiert statt Tages-Prognosewert. Für bereits vergangene Stunden liefert Open-Meteo Ist-Werte, für zukünftige die Prognose — ein Hybrid aus Messung und Vorhersage. Respektiert das konfigurierte Wettermodell (ICON-D2, MeteoSwiss etc.).

---

## [3.9.0] - 2026-04-03

### Refactoring

- **Live Dashboard Backend komplett neu strukturiert**: `live_power_service.py` von 1830 auf 313 Zeilen aufgeteilt in 6 fokussierte Module (`live_sensor_config`, `live_kwh_cache`, `live_history_service`, `live_verbrauchsprofil_service`, `live_tagesverlauf_service`, `live_komponenten_builder`). `live_dashboard.py` von 1656 auf 356 Zeilen durch Extraktion von MQTT- und Wetter-Routes in eigene Router-Dateien.
- **EnergieFluss Frontend**: Statischer SVG-Hintergrund (1019 Zeilen) in `EnergieFlussBackground.tsx` extrahiert — Kernkomponente von 1701 auf 712 Zeilen reduziert.

### Verbessert

- **Performance: HA-Sensor-Einheiten gecacht**: `get_sensor_units()` nutzt jetzt 1 Batch-Call + 1h TTL-Cache statt N sequentieller HTTP-Calls (bei 10 Sensoren bis 50s → jetzt <10ms bei Cache-Hit).
- **Performance: Wetter HA-Sensoren gebatcht**: Außentemperatur + SFML-Sensoren werden in 1 Batch-Call gelesen statt 4 sequentieller Requests (~2s → ~500ms).
- **Performance: EnergieFluss Layout memoized**: `useMemo` für Layout-Berechnung, maxKw und SVG-Höhe — vermeidet vollständige Neuberechnung bei jedem 5s-Refresh-Cycle.
- **Fix: Race Condition bei Anlage-Wechsel im Live Dashboard**: In-flight API-Responses werden verworfen wenn der Nutzer zwischenzeitlich die Anlage gewechselt hat. Verhindert kurzes Flimmern mit Daten der vorherigen Anlage.

---

## [3.8.21] - 2026-04-02

### Behoben

- **WP getrennte Strommessung: Einstellung ging nach Update verloren (#95 Regression)**: Wer die Checkbox vor v3.8.19 aktiviert hatte, konnte den Wert als String `'true'` in der DB gespeichert haben. Der neue strikte `=== true`-Vergleich erkannte diesen String nicht → Checkbox wurde nach dem Update als deaktiviert angezeigt. Fix: beide Typen (`boolean true` und String `'true'`) werden beim Laden akzeptiert. Gemeldet von Rainer.

---

## [3.8.20] - 2026-04-02

### Behoben

- **MQTT Energy Snapshots schlugen für alle Anlagen fehl**: Retained MQTT-Topics einer gelöschten Anlage (ID ohne DB-Eintrag) verursachten einen `FOREIGN KEY constraint failed`-Fehler. Da alle Inserts in einer Transaktion lagen, wurden auch gültige Anlagen nicht gespeichert — über Tage hinweg kein Snapshot → `heute_kWh` im Live-Dashboard blieb `null`. Fix: anlage_ids werden vor dem Insert gegen die DB validiert, unbekannte IDs werden übersprungen.
- **Fronius Solar.web Import: Einspeisung und Netzbezug fehlten bei deutschem Export**: Das deutsche Interface liefert `Energie ins Netz eingespeist` und `Energie vom Netz bezogen` statt `Einspeisung`/`Netzbezug`. Der Parser erkannte diese Varianten nicht → beide Felder wurden als leer importiert. Außerdem wurde das deutsche Format nicht automatisch erkannt. Parser als getestet markiert (verifiziert mit echten Nutzerdaten — Danke Joachim!).

---

## [3.8.19] - 2026-04-02

### Behoben

- **Getrennte Strommessung WP lässt sich nicht abwählen (#95)**: `'false'` (String) ist in JavaScript truthy — die Checkbox blieb nach einmaligem Aktivieren dauerhaft gesetzt. Fix: Laden mit striktem `=== true`-Vergleich, Speichern mit expliziter Boolean-Konvertierung.

### Verbessert

- **Monatsabschluss: Anderen Monat wählen**: Kleiner Link unter dem Titel öffnet einen kompakten Monat/Jahr-Picker, um direkt zu vergangenen Monaten zu navigieren (z.B. für einen nachgeholten Abschluss).

---

## [3.8.18] - 2026-04-02

### Behoben

- **Live-Dashboard: heute-kWh Cache (60s TTL)**: Bei jedem Live-Refresh (alle paar Sekunden) wurde ein voller HA-History-API-Call für alle Sensoren von Mitternacht bis jetzt gemacht. Jetzt wird das Ergebnis 60 Sekunden gecacht — analog zum bestehenden Gestern-Cache.
- **MQTT Energy: Key-Format-Mismatch HA↔MQTT behoben**: MQTT Energy Snapshots lieferten `inv/{inv_id}/{field}` Keys, das Frontend erwartet aber `{typ}_{inv_id}` (wie der HA-Pfad). Neues Mapping übersetzt automatisch anhand der Investitionstypen (z.B. `inv/15/ladung_kwh` → `batterie_15_ladung`).

---

## [3.8.17] - 2026-04-02

### Behoben

- **HA-Statistik-Import: Komponenten-Felder (PV, Speicher, Wallbox, …) werden nie übernommen**: Die Import-Vorschau lieferte Investitions-Felder mit Labels als Schlüssel (`"PV Erzeugung"`, `"Ladung"` …), der Import-Endpoint verglich diese jedoch gegen interne DB-Feldnamen (`"pv_erzeugung_kwh"`, `"ladung_kwh"` …) → alle Investitionsfelder wurden als „nicht ausgewählt" übersprungen, `inv_importiert` blieb immer `False`. Fix: Der Endpoint akzeptiert jetzt sowohl raw Keys als auch Label-Form in `erlaubte_felder`.

---

## [3.8.16] - 2026-04-02

### Behoben

- **Daten-Checker: Wallbox und Wechselrichter melden „Leistung fehlt" obwohl eingetragen**: Das Formular speichert `max_ladeleistung_kw` (Wallbox) und `max_leistung_kw` (Wechselrichter), der Checker suchte aber `leistung_kw` bzw. `leistung_ac_kw` → falsche Warnung trotz eingetragener Werte. Beide Schlüssel werden jetzt geprüft.

---

## [3.8.15] - 2026-04-02

### Behoben

- **Daten-Checker: 66 falsche Batterie-Warnungen bei InvestitionMonatsdaten-Speicher**: Batterie-Checks in „Monatsdaten – Plausibilität" prüften die Legacy-Felder `batterie_ladung_kwh` / `batterie_entladung_kwh` in `Monatsdaten`, die bei investitionsbasierter Speicher-Erfassung (neuer Weg) bewusst leer sind. Fix: Vor dem Legacy-Check wird geprüft ob der Monat bereits durch Speicher-`InvestitionMonatsdaten` abgedeckt ist — wenn ja, entfällt die Warnung. Zusätzlich nutzt die Energiebilanz-Prüfung jetzt die IMD-Werte statt der Legacy-Felder, damit kein falscher negativer Hausverbrauch gemeldet wird.

---

## [3.8.14] - 2026-04-02

### Behoben

- **Batterie-Ladung heute falsch bei Huawei (und ähnlichen) Sensoren (#93 #94)**: Die HA History API liefert als ersten Datenpunkt den letzten bekannten State vor Mitternacht (z.B. 23:59 gestern mit 10,48 kWh) — auch wenn der Sensor kurz danach auf 0 zurückgesetzt wurde. Die bisherige Delta-Berechnung (`val_end − pts[0]`) erkannte diesen Fall nicht (kein Negativsprung im Gesamtdelta) und lieferte z.B. 0,1 statt 10,6 kWh für Batterie-Ladung heute → dadurch war auch der Hausverbrauch ~10 kWh zu hoch. Fix: `pts[0]` durch `min(pts)` ersetzt — der Minimalwert entspricht dem Post-Reset-Wert (≈ 0) und liefert die korrekte Tages-Akkumulation unabhängig davon, ob der Reset-Zeitpunkt im History-Fenster liegt. Betrifft alle kumulativen kWh-Sensoren (Batterie Ladung/Entladung, WP, Wallbox etc.). Zusätzlich: Double-Scale-Bug im Reset-Zweig behoben.

---

## [3.8.13] - 2026-04-02

### Verbessert

- **Daten-Checker: umfassend erweitert** — Der Checker prüft jetzt alle Investitionstypen und Monatsdaten deutlich detaillierter:
  - *Stammdaten*: Standort (Ort/PLZ) für Community-Benchmark-Vergleich
  - *Strompreise*: WP- und E-Auto-Spezialtarife auf Existenz geprüft
  - *Investitionen*: Balkonkraftwerk (`leistung_wp`), Wallbox (`leistung_kw`), Wechselrichter (`leistung_ac_kw`) — bisher ohne Checks. Speicher prüft Arbitrage-Preise wenn aktiv, E-Auto prüft V2H-Entladepreis wenn aktiv. WP prüft JAZ/SCOP/COPs je nach gewähltem Effizienz-Modus auf Plausibilität
  - *Investitions-Monatsdaten*: Vollständigkeit wird jetzt gegen die Hauptmonatsdaten als Referenz geprüft (ab `anschaffungsdatum` der jeweiligen Investition) — fehlende Einträge werden erkannt, nicht nur fehlende Felder in vorhandenen Einträgen. WP berücksichtigt `getrennte_strommessung`
  - *Monatsdaten-Plausibilität*: Pflichtfelder (`einspeisung_kwh`, `netzbezug_kwh`) werden auf `None` geprüft; Batterie-Felder wenn Speicher vorhanden. Neuer Energiebilanz-Check: negativer Hausverbrauch (`PV − Einspeisung + Netzbezug ± Batterie < 0`) wird als ERROR mit vollständiger Wert-Aufschlüsselung gemeldet

---

## [3.8.12] - 2026-04-01

### Behoben

- **Wetter-Endpoint: Verbrauchsprofil blockiert bei HA-Timeout nicht mehr dauerhaft**: `get_verbrauchsprofil()` cachte bisher kein `None`-Ergebnis. Wenn die 14-Tage-HA-History-Anfrage mit `ReadTimeout` scheiterte (und MQTT-Fallback ebenfalls leer war), wiederholte sich der teure Timeout bei jedem Wetter-Refresh (alle 5 Minuten). Fix: `None`-Ergebnis wird jetzt ebenfalls gecacht (Sentinel-Pattern) — der Timeout tritt maximal 1× pro Tag auf statt dauerhaft. Zusätzlich: History-Fenster von 14 auf 7 Tage reduziert (ausreichend für Werktag/Wochenende-Profil, halbiert die HA-Datenmenge).

---

## [3.8.11] - 2026-04-01

### Intern

- **Logging-Konfiguration**: Root-Logger wird jetzt korrekt mit `basicConfig` initialisiert. Bisher gingen alle `logger.info/debug()` Aufrufe der App ins Leere (Uvicorn konfiguriert nur seine eigenen Logger). Diagnose-Logging für `get_verbrauchsprofil()` jetzt auf INFO-Level sichtbar.

---

## [3.8.10] - 2026-04-01

### Intern

- **Diagnose-Logging Verbrauchsprofil**: Debug-Ausgabe in `get_verbrauchsprofil()` zeigt ob HA-History oder MQTT-Fallback erfolgreich war — hilft Performance-Problem im Wetter-Endpoint zu lokalisieren.

---

## [3.8.9] - 2026-04-01

### Hinzugefügt

- **Live-Dashboard: Sonnentags-Fortschrittsbalken** ([#89](https://github.com/supernova1963/eedc-homeassistant/issues/89)): Visueller Trenner zwischen Ist-Werten und Prognose-Tiles in der Sidebar. Zeigt den Tagesfortschritt von Sonnenauf- bis -untergang mit Solar-Noon-Markierung und verbleibender Sonnenscheindauer.
- **Energie-Tabelle: Spalten-Reihenfolge konfigurierbar** ([#88](https://github.com/supernova1963/eedc-homeassistant/issues/88)): ↑↓-Buttons im Spalten-Picker erlauben Umsortierung innerhalb jeder Gruppe. Reihenfolge wird persistent gespeichert, CSV-Export folgt der gewählten Reihenfolge. Reset-Link stellt Default-Reihenfolge wieder her.

---

## [3.8.8] - 2026-04-01

### Behoben

- **Monatsabschluss: Speichern dauerte 30–60 Sekunden**: MQTT-Publish, Energie-Profil Rollup (inkl. Open-Meteo-Calls für jeden Tag des Monats) und Community Auto-Share blockierten bisher den HTTP-Request. Alle drei laufen jetzt als FastAPI BackgroundTasks nach dem DB-Commit — der Wizard kehrt sofort zurück.

---

## [3.8.7] - 2026-04-01

### Hinzugefügt

- **Wallbox: Ladung PV durchgängig**: Das Feld `ladung_pv_kwh` (PV-Anteil der Wallbox-Ladung) war zwar im Monatsabschluss-Wizard sichtbar, fehlte aber an allen anderen Stellen. Jetzt vollständig: Sensor-Mapping (optional, HA-Sensor oder manuell), Monatsdaten-Formular, HA Bulk-Import, Monatsaggregation und Energie-Explorer-Tabelle (neue Spalte „Wallbox PV-Ladung").
- **Monatsabschluss: Wetterdaten automatisch laden**: Globalstrahlung und Sonnenstunden werden beim Öffnen des Wizards automatisch im Hintergrund von Open-Meteo geholt — falls die Felder noch leer sind. Kein Button-Klick mehr nötig.

---

## [3.8.6] - 2026-03-31

### Behoben

- **Live-Dashboard: Ladezeit Wetter/Prognose bei Seitennavigation**: Die `live_wetter`-Cache-TTL wurde von 5 auf 60 Minuten erhöht. Open-Meteo aktualisiert Wetterdaten stündlich (ICON-D2 3-stündlich), die 5-Minuten-TTL war unnötig aggressiv. Der Scheduler-Prefetch läuft alle 45 Minuten — dazwischen konnte der Cache ablaufen und jeder Seitenaufruf blockierte bis zu 15 Sekunden auf einen externen API-Call. Betraf alle Seitennavigationen (nicht nur nach Updates).

---

## [3.8.5] - 2026-03-30

### Hinzugefügt

- **Sensor-Zuordnung: Sonstige Investitionen (#85)**: Investitionen vom Typ „Sonstige" erscheinen jetzt im Sensor-Zuordnungs-Wizard. Felder werden kategorie-abhängig angezeigt: Verbraucher → Verbrauch (kWh), Erzeuger → Erzeugung (kWh), Speicher → beide Felder. Live-Leistungssensor (W) ebenfalls konfigurierbar.
- **Community: Link zum Community-Server (#85)**: Kleines ExternalLink-Icon im Community-Header öffnet energy.raunet.eu direkt im Browser.

### Behoben

- **Community: JAZ-Vergleich nach WP-Typ (#85)**: Die Stärken/Schwächen-Berechnung nutzt jetzt den typ-spezifischen JAZ-Vergleich (`jaz_typ`) statt dem globalen Schnitt. Das Backend hatte den korrekten Wert seit v3.8.4 bereits geliefert — das Frontend ignorierte ihn jedoch und verwendete weiterhin den globalen `jaz.community_avg`. Jetzt wird `jaz_typ` bevorzugt (gleiche WP-Art), mit Fallback auf global wenn zu wenig Vergleichsdaten. Unterstützt alle 4 WP-Arten: Luft/Wasser, Sole/Wasser, Grundwasser, Luft/Luft.

---

## [3.8.3] - 2026-03-30

### Behoben

- **Social-Media-Text: Ausrichtung + Anlagengröße (#84)**: Balkonkraftwerk-Leistung wird zur Gesamtleistung addiert. Ausrichtung wird nur angezeigt wenn eindeutig (1 String oder alle gleich) — Multi-String-Anlagen mit verschiedenen Ausrichtungen zeigen kein Label. Exakter Azimut-Grad aus den Einstellungen hat Vorrang vor dem Dropdown-Label.

## [3.8.2] - 2026-03-30

### Verbessert

- **Aussichten Kurzfristig: 14-Tage-Cache beim Start vorwärmen**: Beim Laden des Live-Dashboards wird die 14-Tage-Solarprognose jetzt im Hintergrund vorab gecacht (fire-and-forget). Wenn der User zu Aussichten navigiert, ist der Cache bereits warm — kein Warten mehr auf Open-Meteo (#82).

---

## [3.8.1] - 2026-03-30

### Behoben

- **Monatsabschluss: UNIQUE constraint bei Energieprofil (#80)**: Seit v3.8.0 liefert `get_tagesverlauf()` 10-Minuten-Daten (144 Punkte). Der `energie_profil_service` las diese Punkte direkt ein und versuchte pro Stunde 6× dieselbe `stunde`-Zeile zu INSERT-en → UNIQUE constraint. Fix: Sub-stündliche Punkte werden vor der Verarbeitung auf Stundenmittelwerte aggregiert.
- **Sensor-Mapping Dropdown: ESC und Click-outside schließen jetzt (#81)**: Im `FeldMappingInput` fehlten ESC-Handler und Click-outside-Handler. Das Dropdown ließ sich nur durch Auswahl eines Eintrags schließen. Beide Handler sind jetzt per `useEffect` registriert.

---

## [3.8.0] - 2026-03-29

### Verbessert

- **Tagesverlauf-Chart: 10-Minuten-Auflösung** (#77): Der Live-Tagesverlauf zeigt jetzt 10-Minuten-Mittelwerte statt Stundenwerte (144 Datenpunkte statt 24). WP-Zyklen, Batterie-Ladekurven und kurzfristige Verbrauchsspitzen werden damit sichtbar. Die "Jetzt"-Referenzlinie wird auf den korrekten 10-Min-Bucket gerundet. Gilt für HA-Nutzer (HA Recorder liefert Sub-Minuten-Rohdaten).
- **Kurzfristig-Prognose: Immer 14 Tage** (#75): Das Tage-Auswahlfeld (7/14/16) wurde entfernt. 14 Tage sind fest eingestellt — Open-Meteo liefert diese Auflösung zuverlässig und schnell. Die 16-Tage-Option entfällt (höhere Ladezeit, kein Mehrwert).
- **KPI-Kacheln leicht transparent** (#78): Hintergrund der Werte-Kacheln auf 90% (Light) bzw. 85% (Dark) Deckkraft reduziert für bessere optische Integration.

### Behoben

- **BKW-Leistung in kWp-Vergleich und Solarprognose** (#74): Der Daten-Checker verglich bisher nur PV-Module gegen den manuellen kWp-Wert und ignorierte Balkonkraftwerke. Jetzt fließt BKW-Leistung korrekt in den Checker-Vergleich ein (Meldung: "Summe PV-Module + BKW"). Außerdem berücksichtigt die Solarprognose (`prognose_service`) die BKW-Leistung beim Gesamt-kWp — BKW ist genauso wetterabhängig wie normale PV.

---

## [3.7.6] - 2026-03-29

### Verbessert

- **Ladezeit Kurzfristig & Live deutlich reduziert**: Zwei gezielte Optimierungen für den ersten Seitenaufruf:
  1. **Jitter bei User-Request deaktiviert**: Der zufällige Verzögerung (bisher 1–30 Sekunden) vor Open-Meteo-API-Calls greift jetzt nur noch beim Hintergrund-Prefetch, nicht beim direkten Aufruf durch den User. Cache-Miss-Latenz sinkt um bis zu 30 Sekunden.
  2. **Sofort-Prefetch nach Kaltstart**: Wenn der Container mit leerem L2-Cache startet (z. B. Erstinstallation oder abgelaufene SQLite-Daten), wird der Prefetch sofort im Hintergrund ausgelöst — ohne den Job-Jitter (5–60s). Der Cache ist warm, bevor der erste User die Seite öffnet.

## [3.7.5] - 2026-03-29

### Behoben

- **„Noch offen" nach Sonnenuntergang ausgeblendet (#72)**: Nach Sonnenuntergang wurde fälschlicherweise noch eine verbleibende Solarprognose angezeigt (z.B. >5 kWh um 21:30 Uhr). Ursache: die Berechnung `Tagesprognose − bisher erzeugte kWh` berücksichtigte nicht, ob die Sonne bereits untergegangen ist. Fix: `wetter.sunset` wird geprüft — nach Sonnenuntergang wird das KPI ausgeblendet.

## [3.7.4] - 2026-03-29

### Verbessert

- **Kostentabelle im Energie-Explorer**: Die Finanzspalten (Einspeise-Erlös, EV-Ersparnis, Netzbezug-Kosten) sind jetzt standardmäßig sichtbar. Neue Spalte **Netto-Bilanz** (Erlös + Ersparnis − Netzbezugskosten) zeigt das monatliche Gesamtergebnis. Vorjahresvergleich mit Δ-Farbkodierung funktioniert wie bei allen anderen Spalten.

## [3.7.2] - 2026-03-29

### Behoben

- **Heute-kWh: kumulierte Monatsabschluss-Sensoren korrekt genutzt (#64 Follow-up)**: Seit v3.6.8 wurden die bereits konfigurierten Energy-Sensoren (Einspeisung, Netzbezug, PV-Erzeugung, Batterie-Ladung/-Entladung) aus dem Monatsabschluss-Mapping für die Live-Dashboard „Heute"-Berechnung nicht genutzt, weil der interne Schlüssel `sensors` statt des korrekten `felder` verwendet wurde und die `FeldMapping`-Struktur (`{strategie, sensor_id}`) nicht ausgelesen wurde. Folge: nach Container-Neustart am Morgen (vor Sonnenaufgang) fehlten PV, Einspeisung, Eigenverbrauch und Batterie-kWh im „Heute"-Abschnitt.
- **Prioritätskette jetzt vollständig**: Basis Einspeisung/Netzbezug und PV-Investitionen nutzen jetzt ebenfalls kumulative Energy-Sensoren als Priorität 1 — keine Trapez-Abhängigkeit mehr wenn kWh-Sensoren konfiguriert sind.
- **`_trapez_kwh` mit 1 Datenpunkt**: Gibt jetzt `0.0` zurück statt `None` (mathematisch korrekt: kein Intervall = 0 kWh). Safety-Net für W-only Setups ohne konfigurierte Energy-Sensoren.

## [3.7.3] - 2026-03-29

### Behoben

- **Foto-Hintergründe im HA Add-on**: Bilder wurden im HA-Ingress-Kontext nicht gefunden (Fragezeichen-Icon). Ursache: absolute Pfade (`/backgrounds/...`) funktionieren hinter HA-Ingress nicht — auf relative Pfade (`./backgrounds/...`) umgestellt.

## [3.7.1] - 2026-03-29

### Verbessert

- **Foto-Hintergründe im Energiefluss**: 6 neue Foto-Varianten wählbar — Alpenpanorama, Milchstraße, Dolomiten, Nebula, Sternennacht, Exoplanet. Der bisherige Wechsel-Button wurde durch ein Dropdown mit allen 9 Varianten (inkl. Tech, Sunset, Alpen) ersetzt. Bilder liegen als WebP vor (413 KB gesamt). Die Auswahl wird per localStorage gespeichert.

## [3.7.0] - 2026-03-28

### Verbessert

- **Batterie Live-kWh: optionale Tages-kWh-Slots (#64)**: Neue optionale Felder im Live-Sensor-Mapping für Speicher: „Ladung heute (kWh)" und „Entladung heute (kWh)". Wer separate Tages-kWh-Sensoren hat (die täglich auf 0 zurückgesetzt werden), kann diese direkt eintragen — sie haben Vorrang vor der bisherigen Berechnung. Vollständige Prioritätskette: (1) Live-Tages-kWh-Sensoren, (2) kumulative Monatsabschluss-Sensoren mit Delta ab Mitternacht, (3) W-Sensor mit Trapez-Integration.
- **WP und Wallbox Live-kWh aus Monatsabschluss-Mapping**: Sind `stromverbrauch_kwh` (WP) bzw. `ladung_kwh` (Wallbox) im Monatsabschluss-Sensor-Mapping konfiguriert, werden diese jetzt ebenfalls für die Live-Dashboard-Tooltips genutzt statt der Trapez-Integration.

## [3.6.9] - 2026-03-28

### Verbessert

- **Energieprofil-Revision (Etappe 1)**: Vorzeichenbasierte Aggregation ersetzt die fehlerhafte kategorie-basierte Logik. BHKW und Sonstiges-Erzeuger fließen korrekt in `pv_kw` ein, V2H wird in `batterie_kw` einbezogen, Wärmepumpe und Wallbox erhalten eigene Spalten (`waermepumpe_kw`, `wallbox_kw`) für spätere Effizienz- und Musteranalyse.
- **Rollierender Energieprofil-Scheduler**: Neuer Job alle 15 Minuten schreibt abgeschlossene Stunden des laufenden Tages — heute's Profil wächst jetzt laufend mit statt erst um 00:15 des Folgetags verfügbar zu sein.
- **Retention-Cleanup**: `TagesEnergieProfil`-Stundenwerte älter als 2 Jahre werden täglich um 00:15 gelöscht. `TagesZusammenfassung` bleibt dauerhaft erhalten.

### Hinweis

Bestehende Energieprofil-Daten werden bei diesem Update einmalig gelöscht und neu aufgebaut (fehlerhafte Aggregation der Vorgängerversion). Die Neusammlung beginnt automatisch.

## [3.6.8] - 2026-03-28

### Behoben

- **Batterie Laden/Entladen kWh im Live-Dashboard zu hoch (#64)**: Wenn Batterie-Sensoren Leistung (W) mit Rauschen um 0 W meldeten, summierte die Trapez-Integration das Rauschen über den Tag auf → überhöhte Werte. Fix: Sind `ladung_kwh`/`entladung_kwh` bereits im Monatsabschluss-Sensor-Mapping konfiguriert, werden diese kumulativen Sensoren direkt via Delta (aktuell − Mitternacht) genutzt — kein Trapez, kein Rauschen. Der W-Sensor-Pfad bleibt als Fallback erhalten.

## [3.6.7] - 2026-03-28

### Behoben

- **MQTT Auto-Publish war nicht aktiv**: Die Einstellung `MQTT_AUTO_PUBLISH=true` wurde zwar gespeichert, aber nie ausgewertet — kein Scheduler-Job war verknüpft. Fix: Bei aktiviertem `MQTT_AUTO_PUBLISH` wird jetzt ein periodischer Job gestartet, der alle `MQTT_PUBLISH_INTERVAL` Minuten (Default: 60) die KPIs aller Anlagen via MQTT Discovery nach Home Assistant publiziert.

## [3.6.6] - 2026-03-28

### Behoben

- **Energie-Explorer Tabelle: Jahresvergleich-Dropdown im Dark Mode unleserlich**: Vergleichsjahr-Select hatte semi-transparenten Hintergrund (`primary-900/30`), der von nativen Dropdowns ignoriert wird. Fix: opaker Dark-Mode-Hintergrund (`gray-800`).

## [3.6.5] - 2026-03-28

### Behoben

- **Cockpit Jahresauswahl: Optionen verschwinden nach Jahreswechsel (#71)**: Beim Wechsel auf ein konkretes Jahr wurden die anderen Jahre aus dem Dropdown entfernt, weil `availableYears` aus der gefilterten API-Antwort berechnet wurde. Fix: Jahre werden jetzt aus den ungefilterten Monatsdaten abgeleitet.

## [3.6.4] - 2026-03-28

### Verbessert

- **Energie-Explorer Tabelle: Sticky Header**: Der Tabellenkopf bleibt beim Scrollen durch lange Datenlisten fixiert (max. 600 px Tabellenhöhe, scrollbar). Wunsch: MartyBr.
- **Energie-Explorer Tabelle: Freie Jahreswahl im Jahresvergleich**: Beim Jahresvergleich kann jetzt ein beliebiges Vergleichsjahr aus einem Dropdown gewählt werden (statt fix Vorjahr). Standard bleibt das Vorjahr, sofern Daten vorhanden. Wunsch: MartyBr.

## [3.6.3] - 2026-03-28

### Behoben

- **Cockpit Zeitraum und Jahresauswahl (#71)**: Bei Anlagen mit Monatsdaten (z.B. Netzbezug) vor der ersten PV-Investition wurde der Zeitraum nur aus InvestitionMonatsdaten berechnet — ältere Monate und Jahre fehlten in der Auswahl. Fix: frühestes und spätestes Datum aus beiden Quellen (Monatsdaten + InvestitionMonatsdaten) kombiniert.
- **FormelTooltip am linken Rand (#70)**: Tooltip wurde am linken Viewport-Rand abgeschnitten. Fix: horizontale Position wird jetzt viewport-bewusst berechnet und bei Bedarf nach rechts verschoben.

## [3.6.2] - 2026-03-28

### Behoben

- **JAZ Heizen/Warmwasser falsch berechnet (#67)**: Wärmemenge summierte über alle Monate, Strom nur über Monate mit getrennter Strommessung → absurde Werte (z.B. 89, 297). Fix in WP-Dashboard und Auswertungen → Komponenten.
- **BKW-Anlagenleistung ignoriert Anzahl Module (#66)**: Im Cockpit wurde nur die Leistung eines einzelnen Moduls in kWp umgerechnet, die Modulanzahl blieb unberücksichtigt.
- **Security: Path Traversal in SPA-Serving (#65)**: `.resolve()` + Prefix-Check verhindert das Auslesen von Dateien außerhalb des Frontend-Ordners.
- **Security: CORS allow_credentials (#65)**: Ungültige Kombination `allow_origins=["*"]` + `allow_credentials=True` korrigiert.
- **Security: Infothek-Upload ohne Größenlimit (#65)**: 50 MB Limit für Datei-Uploads eingebaut.

### Geändert

- **JAZ statt COP im WP-Dashboard (#67)**: Labels umbenannt — "Ø COP" → "JAZ (gesamt)", "COP Heizen" → "JAZ Heizen", "COP Warmwasser" → "JAZ Warmwasser".
- **JAZ in Auswertungen → Komponenten (#67)**: JAZ, JAZ Heizen und JAZ Warmwasser mit Jahresfilter verfügbar (nur bei getrennter Strommessung).

## [3.6.1] - 2026-03-28

### Behoben

- **Browser-Cache nach Updates (#69)**: Nach einem Add-on-Update zeigte der Browser weiterhin die alte Oberfläche, weil `index.html` aus dem Browser-Cache geladen wurde. Fix: `Cache-Control: no-cache` Header für `index.html` — der Browser prüft nun bei jedem Aufruf ob eine neue Version vorliegt. JS/CSS-Bundles bleiben weiterhin gecacht (kein Performance-Verlust).
- **Tabellen-Tab: Render-Crash bei Vorjahresvergleich**: Fehlende Keys auf `React.Fragment` in `map()`-Aufrufen konnten die Auswertungs-Seite zum Absturz bringen sobald der Vorjahresvergleich aktiviert wurde.
- **Monatsabschluss-Tooltip**: Hover über den roten Punkt in der Kopfzeile zeigt jetzt welcher Monat offen ist (z.B. "Monatsabschluss Februar 2026 offen").

## [3.6.0] - 2026-03-28

### Neu

- **Interaktiver Energie-Explorer (Auswertungen → Tabelle)**: Neuer Tab mit vollständiger Tabellenansicht aller Monatsdaten — als Ergänzung zu den Grafiken für präzise Zahlen und individuelle Auswertungen.
  - **22 Spalten** in 7 Gruppen: Energie, Quoten, Speicher, Wärmepumpe, E-Auto, Finanzen, CO₂
  - **Sortierung** per Klick auf jeden Spaltenheader (auf-/absteigend)
  - **Spaltenauswahl** via Dropdown mit Gruppen-Gliederung — Konfiguration wird automatisch im Browser gespeichert (localStorage)
  - **Aggregationszeile** am Ende: Summe für kWh/km/€, Durchschnitt (Ø) für Prozentwerte und COP
  - **Vorjahres-Vergleich**: Toggle-Button zeigt Δ-Spalte pro Metrik mit farbiger Bewertung (grün/rot je nach Richtung)
  - **Finanzen** mit historisch korrektem Tarif pro Monat aus der Strompreise-Tabelle
  - **Deutsches Zahlenformat** mit Tausender-Punkt und Komma-Dezimalstelle
  - **CSV-Export** inkl. Δ-Spalten bei aktivem Vorjahresvergleich

## [3.5.11] - 2026-03-28

### Behoben

- **JAZ Heizen/Warmwasser in Auswertungen → Komponenten (#67)**: Gleicher Monate-Bug wie im WP-Dashboard — Heizung/Warmwasser wurde über alle Monate summiert, Strom nur über Monate mit getrennter Messung. Fix: Nur Monate mit vorhandener getrennter Strommessung fließen in JAZ Heizen/Warmwasser ein.

## [3.5.10] - 2026-03-28

### Behoben

- **JAZ Heizen/Warmwasser falsch berechnet (#67)**: Wärmemenge summierte über alle Monate, Strom nur über Monate mit getrennter Strommessung → absurde Werte (z.B. 89, 297). Fix: Wärme und Strom werden jetzt aus denselben Monaten summiert.
- **BKW-Anlagenleistung ignoriert Anzahl Module (#66)**: Im Cockpit wurde nur die Leistung eines einzelnen Moduls in kWp umgerechnet, die Modulanzahl blieb unberücksichtigt. 2 × 490 Wp ergab fälschlicherweise 0,49 statt 0,98 kWp.
- **Security: Path Traversal in SPA-Serving (#65)**: `.resolve()` + Prefix-Check verhindert jetzt das Auslesen von Dateien außerhalb des Frontend-Ordners über präparierte URL-Pfade.
- **Security: CORS allow_credentials (#65)**: Ungültige Kombination `allow_origins=["*"]` + `allow_credentials=True` korrigiert (`allow_credentials=False`).
- **Security: Infothek-Upload ohne Größenlimit (#65)**: 50 MB Limit für Datei-Uploads eingebaut.

### Geändert

- **JAZ statt COP im WP-Dashboard (#67)**: Labels umbenannt — "Ø COP" → "JAZ (gesamt)", "COP Heizen" → "JAZ Heizen", "COP Warmwasser" → "JAZ Warmwasser". Hinweistext erklärt Gesamtlaufzeit-Bezug.
- **JAZ in Auswertungen → Komponenten (#67)**: JAZ, JAZ Heizen und JAZ Warmwasser jetzt auch im Auswertungs-Tab mit Jahresfilter verfügbar (nur wenn getrennte Strommessung vorhanden).

## [3.5.9] - 2026-03-27

### Neu

- **Hintergrund-Varianten im Energiefluss-Diagramm**: Neuer Toggle-Button (Tech → Sunset → Alpen) mit automatischer Speicherung der Auswahl.
  - **Sunset**: Krepuskulare Sonnenstrahlen im Himmel, elliptische Wellenebenen auf dem Meer, goldene Lichtfunken auf dem Wasser — vollständig in Light und Dark Mode.
  - **Alpen**: Drei Bergketten-Silhouetten mit Schneekuppen. Light Mode mit Sonnenscheibe und goldenen Strahlen. Dark Mode mit Granit-Grau, Nadelwald-Grün, Mondlicht, Sternenhimmel und Aurora-Hauch.

## [3.5.8] - 2026-03-27

### Behoben

- **Kurzfrist-Prognose lädt langsam**: Cache-Key-Mismatch — Frontend fragt standardmäßig `tage=14` an, Prefetch wärmte aber nur `days=7` und `days=16`. Dadurch traf jeder Aufruf der Kurzfrist-Seite einen leeren Cache und wartete 1–30s Jitter + API-Call. Prefetch jetzt für alle drei Werte (7, 14, 16).

## [3.5.7] - 2026-03-27

### Behoben

- **Wärmepumpenart im Investitionsformular (#63)**: Das Dropdown "Wärmepumpenart" (Luft-Wasser, Sole-Wasser, Grundwasser, Luft-Luft) war im Backend bereits definiert, fehlte aber im Frontend-Formular. Jetzt sichtbar unter Investitionen → Wärmepumpe.
- **Historische Tarife in Finanzauswertung (#63)**: Tarif-Auflösung komplett ins Frontend verlagert — alle Stromtarife werden geladen und pro Monat der zum 1. des Monats gültige Tarif verwendet. Funktioniert jetzt auch ohne Investitions-Komponenten.

## [3.5.6] - 2026-03-27

### Behoben

- **Live Dashboard Batterie kWh zu hoch (#64)**: Energie-Sensoren (kWh/Wh/MWh) wurden bisher nochmals über Zeit integriert → massiv überhöhte Werte. Automatische Erkennung: wenn ein Sensor kWh meldet, wird `heute = aktueller_Wert − Mitternacht` berechnet. Keine Mapping-Änderung nötig.

## [3.5.5] - 2026-03-27

### Behoben

- **Historische Tarife in Monatsbalken (#63)**: Finanzauswertung zeigt jetzt pro Monat die Kosten mit dem historisch korrekten Tarif (inkl. Grundpreis). Auch die Balken in "Finanzielle Bilanz pro Monat" nutzen jetzt historische Tarife statt des aktuellen.

## [3.5.4] - 2026-03-27

### Behoben

- **Historische Tarife in Finanzauswertung (#63)**: Netzbezugkosten wurden bisher immer mit dem aktuell gültigen Tarif berechnet. Jetzt wird pro Monat der zum Monatsersten gültige Tarif verwendet — inkl. korrektem Grundpreis. Info-Kasten zeigt jetzt die Summe der monatlichen Kosten statt einer Neuberechnung mit aktuellem Tarif.
- **Wetter-Symbole aus Bewölkung (#59)**: Symbol wird jetzt direkt aus der Bewölkung bestimmt (unabhängig vom WMO-Code): <20% → Sonne, <40% → Sonne+Wolke (warm), <70% → Sonne+Wolke, ≥70% → Wolke. Behebt Inkonsistenz bei MeteoSwiss.
- **Balkonkraftwerk in Live-Dashboard Orientierung (#62)**: BKW wurde bei der Wetter-Orientierungsgruppe nicht berücksichtigt.

## [3.5.3] - 2026-03-27

### Behoben

- **Wetter-Symbole plausibilisiert**: WMO weather_code von MeteoSwiss passte nicht zur Bewölkung (z.B. "bewölkt" bei 27%). Symbole werden jetzt anhand der tatsächlichen Bewölkung korrigiert: <20% → Sonne, <40% → Sonne+Wolke, >80% → Wolke.
- **Migration-Batch Routing-Fehler**: "Übernehmen"-Button auf Investitionen-Seite gab `int_parsing`-Fehler (FastAPI Route-Konflikt).

## [3.5.2] - 2026-03-27

### Hinzugefügt

- **Infothek: Kategorie Messstellenbetreiber** (#60): Neue Vorlage für Nutzer mit separatem Zähleranbieter. Felder: Zählernummer, Messstellenbetreiber, Zähler-Typ (Konventionell/mME/iMSys), Zähler-Hersteller, Einbau-/Eichdatum, Eichfrist, Vertragsnummer, Jahresgebühr, Kundennummer. Auslöser: Rainer.

## [3.5.1] - 2026-03-27

### Hinzugefügt

- **Kaskadierender 2-Stufen-Cache (L1/L2)**: Persistenter SQLite-Cache unter dem RAM-Cache für Wetter- und Solar-Daten. Erster Seitenaufruf nach Server-Neustart wird sofort aus L2 bedient (~5ms statt 5-30s). Startup-Warmup lädt L2 direkt nach DB-Init in L1. Cleanup-Job täglich um 04:00 + Fallback beim Boot.
- **Live-Wetter Prefetch**: Das WetterWidget auf der Live-Seite wird jetzt proaktiv alle 45 Min vom Prefetch-Service vorgeladen (bisher nur on-demand bei Client-Aufruf).
- **Wärmepumpenart (wp_art)**: Neues Dropdown im WP-Investitions-Formular (Luft-Wasser, Sole-Wasser, Grundwasser, Luft-Luft). Wird beim Community-Share mitgesendet für fairen JAZ-Vergleich nach WP-Art. Auslöser: Rainer-Feedback.

### Geändert (Community-Server)

- **JAZ-Benchmark nach WP-Art**: Community-Vergleich zeigt zusätzlich den typ-spezifischen Durchschnitt (z.B. Ø Luft-Wasser: 3.0 statt nur Ø Alle: 3.8).
- **Neuer Endpoint** `GET /api/components/waermepumpe/by-art`: JAZ-Statistiken gruppiert nach Wärmepumpenart.

## [3.5.0] - 2026-03-26

### Hinzugefügt

- **Infothek-Modul**: Neues optionales Modul zur Verwaltung von Verträgen, Zählern, Kontakten und Dokumentation.
  - **14 Kategorien** mit dynamischen Vorlagen-Feldern: Stromvertrag, Einspeisevertrag, Gasvertrag, Wasservertrag, Fernwärme, Brennstoff, Versicherung, Vertragspartner, Wartungsvertrag, MaStR, Förderung, Garantie, Steuerdaten, Sonstiges.
  - **Datei-Upload**: Bis zu 3 Dateien pro Eintrag (Fotos + PDFs). Bilder werden serverseitig auf max 500kb resized, Thumbnails generiert, EXIF-Rotation korrigiert, HEIC→JPEG konvertiert. PDFs max 5 MB.
  - **Lightbox** für Bilder, PDF öffnet in neuem Tab.
  - **Vertragspartner**: Eigene Sektion mit separatem Button, Badges mit Telefon/Mail-Links. Zuordnung per Dropdown bei Verträgen — einmal pflegen, mehrfach zuordnen (z.B. Gemeindewerke → Strom, Gas, Wasser).
  - **Vorbelegung**: Felder werden beim Anlegen aus vorhandenen Systemdaten befüllt (Strompreise → Tarif/Anbieter, Anlage → MaStR/Inbetriebnahme).
  - **Investition-Verknüpfung**: Bidirektional — Infothek-Einträge können mit Investitionen verknüpft werden, Investitions-Karten zeigen verknüpfte Einträge.
  - **Migration**: Bestehende Stammdaten (Kontakte, Garantien, Wartungsverträge) aus Investitionen per Klick in die Infothek übernehmen. Button auf der Investitionen-Seite.
  - **PDF-Export**: Alle oder gefilterte Einträge als PDF, nach Kategorie gruppiert.
  - **Markdown-Notizen**: Toolbar (Bold/Italic/Liste/Link) mit Vorschau-Toggle, Rendering in Karten und im PDF.

### Dependencies

- `react-markdown` (Frontend)
- `Pillow`, `pillow-heif` (Backend — Bildverarbeitung)

## [3.4.34] - 2026-03-26

### Verbessert

- **Performance: Live-Wetter sofort aus Cache**: Open-Meteo Wetter-Response wird 5 Min gecacht — Wetter-Widget lädt sofort statt 5–10s auf API-Antwort zu warten.

## [3.4.33] - 2026-03-26

### Verbessert

- **Performance: API-Calls drastisch reduziert**: Shared Module-Level Cache für `useAnlagen` und `useInvestitionen` — alle Komponenten (TopNavigation, SubTabs, Seiten) teilen einen API-Call statt jeweils eigene zu machen.
- **Performance: Live-Dashboard Backend**: Investitionen-Queries von 3 auf 1 pro 5s-Poll, Gestern-kWh Cache (bis Mitternacht), HA Sensor-Abfragen gebatcht (1 HTTP-Call statt 5–15).
- **Performance: Lernfaktor Cache**: 30-Tage TagesZusammenfassung-Query nur noch 1× pro Tag statt bei jedem Wetter-Abruf.
- **Live-Dashboard Wetter+Prognose**: Parallel via `Promise.allSettled` statt sequentiell — halbe Wartezeit.

## [3.4.32] - 2026-03-26

### Behoben

- **Aussichten-Ladezeit 30s+ (#59)**: Externe API-Abfragen auf Hintergrund-Caching umgestellt. Prognose-Prefetch läuft alle 45 Min automatisch, Seiten laden sofort aus dem Cache.
- **Wallbox/E-Auto Doppelzählung**: Wenn Wallbox und E-Auto denselben Leistungs-Sensor nutzen, wird die Leistung nur einmal gezählt. SoC (Ladezustand) wird weiterhin separat angezeigt.
- **Netto-Hausverbrauch im Energiefluss**: Kind-Komponenten (E-Auto mit parent_key) werden im Zentrum des Energieflusses nicht mehr doppelt mitgezählt.
- **Live-Dashboard Mobile (#56)**: Autarkie/Eigenverbrauch und Prognose-Kacheln einheitlich linksbündig im Grid-Layout. Prognose-Zeile bricht auf schmalen Screens (< 400px) auf 2 Spalten um.
- **Logo Dark Mode**: Halbtransparenter Hintergrund für Full-Logo, "dc" und Subtitel aufgehellt.

### Verbessert

- **Multi-String Solar-Prognose**: Parallel statt sequentiell (asyncio.gather) — deutlich schneller bei mehreren PV-Ausrichtungen.

## [3.4.31] - 2026-03-26

### Behoben

- **Bezug/Einspeisung in Heute-kWh vertauscht (#58)**: Die Vorzeichen-Invertierung aus den Basis-Sensoren wurde bei der History-basierten Tages-kWh-Berechnung nicht angewendet. Betrifft Heute/Gestern-Widgets, Tagesverlauf-Chart und Energieprofil. Live-Leistungsanzeige (W) war korrekt.

## [3.4.30] - 2026-03-26

### Behoben

- **Leere Exception-Logs**: Alle 32 `logger.warning/error`-Stellen im Backend loggen jetzt den Exception-Typ (`ConnectError: ...` statt nur `:`). Betrifft 20 Dateien: HA Statistics, Wetter, Solar Forecast, MQTT, Connector, Monatsabschluss u.a.
- **Protokolle Limit-Inkonsistenz**: Frontend forderte 300 Einträge an, Text sagte "max. 500" — beides auf 500 vereinheitlicht
- **Offset=0 nicht gesendet**: API-Client übersprang `offset=0` (JavaScript falsy) — korrigiert auf `!= null` Check

### Neu

- **Aktivitäts-Logging für alle kritischen Operationen**: 6 neue Kategorien mit ~20 `log_activity()`-Aufrufen:
  - **HA-Statistiken**: DB-Abfrage-Fehler, Import-Ergebnisse (Monate importiert/übersprungen/Fehler)
  - **Scheduler-Jobs**: Monatswechsel-Snapshot, Energie-Profil Aggregation, MQTT Energy Snapshot/Cleanup
  - **MQTT**: Inbound/Gateway/Bridge Start + Verbindungsverlust
  - **Community**: Daten teilen/löschen + Timeout/Verbindungsfehler
  - **Sensor-Mapping**: Speichern/Löschen mit Sensor-Anzahl
  - **HA-Export**: MQTT-Sensoren publiziert/entfernt
  - **Backup-Export/Import**: JSON-Export/Import mit Details
- **Textsuche in Aktivitäten**: Suchfeld mit Debounce (400ms), sucht case-insensitive in Aktion und Details (Backend: `ILIKE` auf `aktion` + `details`)
- **Copy-Button (beide Tabs)**: Kopiert sichtbare Einträge als Markdown — ideal zum Einfügen in GitHub Issues. Button zeigt grünes Häkchen als Feedback
- **Download-Button (System-Logs)**: Exportiert gefilterte Logs als `.txt`-Datei
- **Cleanup-Feedback**: Nach Bereinigung alter Aktivitäten (>90 Tage) zeigt ein grüner Toast die Anzahl entfernter Einträge
- **Debug-Modus**: Log-Level zur Laufzeit zwischen DEBUG/INFO umschaltbar (kein Restart nötig). Amber-farbiger Button + Warnhinweis bei aktivem Debug
- **Neustart-Button**: EEDC direkt aus den Protokollen neu starten (HA: Supervisor-API, Standalone: Container-Restart)

---

## [3.4.29] - 2026-03-25

### Behoben

- **EV-Quote >100% Cap**: Eigenverbrauchsquote wird auf maximal 100% begrenzt
- **API-Cache Random-Jitter**: Cache-Expiry mit zufälligem Offset, verhindert gleichzeitige Cache-Invalidierung aller Clients

### Neu

- **Infothek-Konzept (#57)**: Konzeptdokumentation für optionales Modul (Verträge, Zähler, Kontakte, Fotos) mit UI-Mockups und 5 neuen Kategorien (Gas, Wasser, Fernwärme, Pellets, Versicherung)

---

## [3.4.28] - 2026-03-25

### Behoben

- **Monatsabschluss TypeError (#54)**: `monatsdaten_id` wurde an `InvestitionMonatsdaten`-Konstruktor übergeben, obwohl das Feld im Model nicht existiert — erster Monatsabschluss schlug fehl
- **Health-Check Log-Spam (#54)**: HA Supervisor Health-Checks (`/api/health` alle paar Sekunden) werden aus den Uvicorn Access-Logs gefiltert

### Neu

- **Dynamische Cockpit-Tabs (#56)**: Investitions-Tabs (E-Auto, Wallbox, Speicher etc.) werden nur angezeigt wenn eine entsprechende Investition existiert. Basis-Tabs (Übersicht, Aktueller Monat, PV-Anlage) bleiben immer sichtbar
- **Mobile-Optimierung (#56)**: Komplette Überarbeitung der Mobile-Ansicht:
  - Responsive Padding (Layout, Sticky-Header)
  - KPI-Kacheln: responsive Font-Size, kein Text-Overflow, einspaltig auf Phones
  - EnergieFluss SVG: ResizeObserver + dynamische viewBox (360/450/600px)
  - HeroLeiste + RingGaugeCard: kompakter auf Mobile
  - SubTabs: Scroll-Snap + versteckte Scrollbar
  - Touch-Feedback (active:scale-95) auf Buttons
  - ARIA-Labels und Live-Regions für Screenreader

### Verbessert

- **Anlage-Select vereinheitlicht (#56)**: Kompakte Breite (`compact`-Prop) auf allen Cockpit-Seiten, Anlage-Wechsel synchronisiert alle Komponenten via CustomEvent
- **Header-Layout konsistent (#56)**: Einheitliches Flex-Layout auf Übersicht, Aktueller Monat und allen Investitions-Dashboards

## [3.4.27] - 2026-03-25

### Behoben

- **Fehler „[object Object]" im Monatsabschluss (#54)**: ApiClient warf Plain Object statt Error-Instanz, dadurch wurden Backend-Fehlermeldungen im gesamten Frontend als „[object Object]" oder generische Texte angezeigt. ApiError ist jetzt eine Error-Subklasse
- **Update-Hinweis für HA Add-on präzisiert (#55)**: Statt „Update über Einstellungen → Add-ons" jetzt konkreter Pfad zum manuellen Update-Check mit Hinweis auf automatische Prüfung

### Verbessert

- **Monatsabschluss Save-Logging**: Detailliertes Logging der Eingabedaten und DB-Operationen für Fehlerdiagnose

## [3.4.26] - 2026-03-25

### Neu

- **MQTT Gateway mit Geräte-Presets**: Universelle MQTT-Brücke für beliebige Smarthome-Systeme mit vorgefertigten Geräte-Presets
- **Dashboard Refactoring**: Aufsplitten in wiederverwendbare Komponenten (HeroLeiste, KPICard, RingGaugeCard, EnergyFlowDiagram, etc.)
- **Frontend-Bibliothek** (`lib/`): Zentrale Utilities für Formatierung, Farben, Berechnungen und Konstanten
- **Custom Hooks** (`hooks/`): useApiData, useSelectedAnlage, useYearSelection für einheitliche Datenlade-Patterns
- **Monatsabschluss-Komponenten**: Wizard-Steps als eigenständige Komponenten (BasisStep, InvestitionStep, SummaryStep, etc.)
- **Sensor-Mapping erweitert**: Verbesserte BasisSensorenStep mit Live-Sensor-Vorschau und Mapping-Summary

### Verbessert

- **Solar-Prognose**: Erweiterte API mit Forecast-Daten
- **Live Dashboard**: Erweiterte Power-Service-Integration und Wetter-Widget
- **Cockpit**: Zusätzliche Analyse-Endpoints (Komponenten, PV-Strings, Prognose-Vergleich)
- **Connectors**: MQTT-Bridge für Connector-Daten, verbesserte Geräte-Adapter
- **HA Statistics Service**: Robustere Monatswert-Berechnung

## [3.4.25] - 2026-03-24

### Behoben

- **WP-Wärme Live-Anzeige im laufenden Monat (#53)**: Heizenergie- und Warmwasser-Sensoren wurden im laufenden Monat nicht angezeigt ("Wärme: — kWh"), obwohl sie korrekt gemappt waren. Die Aggregation fehlte für HA Statistics und MQTT-Inbound. Auch getrennte Strommessung wird jetzt korrekt summiert

## [3.4.24] - 2026-03-24

### Behoben

- **Standalone Multi-Arch Manifest fix (#51)**: `docker buildx imagetools create` statt `docker manifest create` für korrekte Multi-Arch-Manifeste

## [3.4.23] - 2026-03-24

### Behoben

- **Pre-built Docker Images für HA Add-on (#51)**: ARM64-Builds hingen wegen QEMU-Emulation. Umstellung auf native ARM64-Runner (`ubuntu-24.04-arm`) für beide Repos

## [3.4.22] - 2026-03-24

### Neu

- **ARM64 Docker-Image für Standalone (#52)**: Multi-Arch-Build (amd64 + arm64) für das Standalone-Docker-Image. Raspberry Pi und andere ARM-Geräte werden jetzt unterstützt

## [3.4.21] - 2026-03-24

### Neu

- **DWD ICON-D2 Wettermodell (#48)**: Neues hochauflösendes Wettermodell (2.2 km) speziell für deutsche Standorte. Kaskade: 2 Tage ICON-D2, danach Fallback auf best_match
- **Netto-Hausverbrauch im Energiefluss**: Haus zeigt Summe aller Verbraucher (ohne Batterie/Netz) statt Residual-Rest

### Behoben

- **Kurzfrist Heute-Markierung**: `ring` → `border` für die Tages-Markierung (kein Abschneiden mehr am Kartenrand)

## [3.4.20] - 2026-03-24

### Neu

- **Community-Nudge + Auto-Share**: Nudge-Banner im Live-Dashboard und Cockpit wenn noch nicht geteilt. Auto-Share Checkbox in Stammdaten, Community-Seite und Monatsabschluss-Hinweis

### Behoben

- **Solarleistung ohne Batterie/Netz (#49)**: Solarleistung zeigt nur PV-Erzeugung (neues Feld `summe_pv_kw`), Position oberhalb Haus

## [3.4.19] - 2026-03-24

### Behoben

- **Installation schlägt fehl (#51)**: Pre-built Docker Images auf GitHub Container Registry (GHCR) bereitgestellt. Bisherige Releases enthielten den Build-Workflow noch nicht, sodass keine Images auf GHCR verfügbar waren (403 Denied beim Pull).

## [3.4.18] - 2026-03-24

### Behoben

- **Multi-String Wetter-Daten (#48)**: Kurzfrist-Tabelle zeigte bei Multi-String-Anlagen keine Temperatur, Bewölkung und Niederschlag (Felder wurden bei der String-Aggregation nicht durchgereicht)

### Neu

- **Wettermodell-Kaskade (#48)**: Neues Dropdown "Prognose-Wettermodell" in Anlage-Stammdaten. Auswahl zwischen Automatisch (best_match), MeteoSwiss Alpen (2.1 km), DWD ICON-EU (7 km) und ECMWF IFS (9 km). Bei spezifischem Modell wird eine Kaskade verwendet: bevorzugtes Modell für die ersten Tage + best_match Fallback für den Rest (parallele API-Calls). Ideal für alpine Standorte (Südtirol, Schweiz, Tirol), die mit dem Standardmodell ungenaue Wetterprognosen erhalten.
- **Datenquellen-Anzeige**: Herkunft der Wetterdaten wird pro Tag in der Kurzfrist-Tabelle als Kürzel (MS/EU/EC/BM) und in der Fußzeile zusammengefasst angezeigt

## [3.4.16] - 2026-03-23

### Behoben

- **Hausverbrauch-Berechnung mit Batterie (#47)**: Live Dashboard Tages-kWh (Eigenverbrauch, Hausverbrauch), Autarkie-/EV-Quote Gauges und Vorjahresvergleich berücksichtigen jetzt Batterie-Ladung/-Entladung. Bisher wurde `Eigenverbrauch = PV - Einspeisung` gerechnet (ohne Batterie), jetzt korrekt: `Direktverbrauch = PV - Einspeisung - Batterieladung`, `Eigenverbrauch = Direktverbrauch + Batterieentladung`, `Hausverbrauch = Eigenverbrauch + Netzbezug`.

## [3.4.14] - 2026-03-23

### Behoben

- **Wetter-Icons in Aussichten**: Kurzfrist-Prognose zeigte immer nur Sonne — Regen, Schnee und Gewitter wurden nie als Icon angezeigt. Zwei Ursachen: (1) Solar-Prognose-Backend fragte keinen WMO Weather Code von Open-Meteo ab, (2) Frontend ignorierte das wetter_symbol-Feld und nutzte nur den Bewölkungsgrad.

## [3.4.13] - 2026-03-23

### Verbessert

- **Sonnenstunden als Zeitformat**: Anzeige `10h 00m` statt `10.0h` im Wetter-Widget (#46)
- **SA/SU/SolarNoon im Chart**: Sonnenaufgang, Sonnenuntergang und Solar Noon als vertikale Linien im PV-Chart (Noon-KPI oben entfernt) (#46)
- **Speicher-Farbwechsel**: Ladung (blau) und Entladung (cyan) im Energiefluss visuell unterscheidbar (#46)
- **Speicher-Ladung sichtbarer**: Opacity im Wetter-Chart deutlich erhöht (#46)
- **Energieumsatz-Tooltip**: Erklärender Tooltip auf dem Energieumsatz-Label im Energiefluss (#46)
- **Echte Gerätenamen statt "Sonstige"**: Im Wetter-Chart und Tooltip werden die tatsächlichen Investitions-Namen angezeigt (#46)
- **PV-Prognose KPI**: Wird nur noch bei aktivem SFML angezeigt (keine Doppelung) (#46)
- **Wallbox-Phantom-Fix**: Chart-Kategorien werden gegen vorhandene Investitionen validiert (#46)

## [3.4.12] - 2026-03-23

### Hinzugefügt

- **Sensor-Vorzeichen invertieren (#44)**: Neue Checkbox "Vorzeichen invertieren (×−1)" bei allen Live-Leistungssensoren (W) in der Sensor-Zuordnung. Löst das Problem bei Wechselrichtern/BMS die umgekehrte Vorzeichen liefern (z.B. Batterie: negativ = Ladung, positiv = Entladung).

## [3.4.10] - 2026-03-23

### Geändert

- **SoC-Anzeige als kompakte Balken**: Halbkreis-Gauges durch farbige Fortschrittsbalken ersetzt (rot < 20%, gelb 20-50%, grün > 50%). Spart ~60% Höhe in der Sidebar.

### Hinzugefügt

- **Batterie heute (Ladung/Entladung)**: Neue Kachel im "Heute"-Bereich zeigt Ladung (▲) und Entladung (▼) getrennt in kWh.

## [3.4.9] - 2026-03-23

### Behoben

- **VM/NM-Split an Solar Noon (#42)**: Vormittag/Nachmittag-Aufteilung nutzt jetzt Solar Noon (Equation of Time) statt hartem 12:00-Split. Behebt die stark verzerrten VM/NM-Verhältnisse (z.B. 15/85 statt ~50/50). Bei Ost/West-Anlagen wird jetzt pro String separat berechnet statt über einen gemittelten Azimut.
- **PV-Erzeugung Doppelzählung im Aktueller Monat (#43)**: Wenn ein Top-Level-Aggregat (z.B. aus gespeicherten Daten oder MQTT pv_gesamt) bereits existierte, wurden Einzel-Investitionswerte nochmals aufaddiert. PV-Erzeugung wurde dadurch doppelt angezeigt.
- **Live-Dashboard: Watt-Auflösung** von 10W auf 1W verbessert (round(kw,3) statt round(kw,2)).

### Hinzugefugt

- **Solar Noon im Wetter-Widget**: Sonnenhöchststand als KPI in "Wetter heute" (z.B. "Noon 12:27"), mit Tooltip-Erklärung.
- **Hausverbrauch heute**: Neue Kachel im "Heute"-Bereich des Live-Dashboards.
- **Info-Tooltips**: Erklärungen an Eigenverbrauch, Netzbezug, PV-Prognose, Solar-Aussicht und Netz-Symbol-Farbe.

### Geändert

- **Live-Dashboard kompakter**: Kleinere Titelzeile, reduzierte Abstände — weniger Scrollbedarf bei maximaler Bildschirmauflösung.

## [3.4.8] - 2026-03-22

### Behoben

- **VM/NM-Werte in Solar-Prognose gefixt**: Die Vormittag/Nachmittag-Aufteilung wurde im Backend berechnet aber bei der API-Antwort nicht durchgereicht (Pydantic-Konvertierung). Jetzt sichtbar in 3-Tage-Vorschau und Kurzfrist-Aussichten.

### Hinzugefügt

- **SFML in "Noch offen" und 3-Tage-Vorschau**: "Noch offen" nutzt jetzt die ML-Prognose wenn verfügbar (genauer als EEDC). 3-Tage-Vorschau zeigt SFML-Wert in lila neben dem EEDC-Wert für Heute und Morgen.

### Geändert

- **Netz-Balken aus Sidebar entfernt**: Die dynamische Netz-Farbe im Energiefluss SVG (grün/orange/rot) macht den separaten Netz-Balken überflüssig. Mehr Platz für 3-Tage-Vorschau und Temperaturen.

## [3.4.7] - 2026-03-22

### Hinzugefügt

- **3-Tage Solar-Vorschau in der Sidebar (#41)**: Kompakte Übersicht für Heute, Morgen und Übermorgen mit Vormittag/Nachmittag-Aufteilung — direkt auf der Live-Seite, ideal für die Planung großer Verbraucher (Waschmaschine, Trockner etc.).
- **"Noch offen" kWh-Kachel (#41)**: Zeigt das Restpotenzial für heute (Tagesprognose − bisheriger Ertrag) neben der PV-Prognose in der Sidebar. Verschwindet wenn die Prognose erreicht oder übertroffen ist.

### Behoben

- **Netz-Farbe im Energiefluss korrigiert**: Die dynamische Einfärbung (grün/orange/rot) hatte die Backend-Semantik vertauscht (erzeugung_kw = Netzbezug, verbrauch_kw = Einspeisung). Jetzt korrekt: orange bei Einspeisung, rot bei Netzbezug, grün bei Balance.

## [3.4.6] - 2026-03-22

### Hinzugefügt

- **Netz-Farbe dynamisch im Energiefluss (#40)**: Die Stromnetz-Linie ändert die Farbe nach Flussrichtung — grün bei Balance (±100W), orange bei Einspeisung, rot bei Netzbezug. Gleiche Logik wie der Netz-Gauge in der Sidebar.
- **Solar-Soll-Wert im Energiefluss (#40)**: Zeigt "Solar Soll ~X.X kW" unter dem Energieumsatz — basierend auf der SFML-Prognose der aktuellen Stunde, Fallback auf EEDC-Prognose.
- **Live als Startseite (#40)**: EEDC öffnet jetzt direkt mit dem Live-Dashboard statt dem Cockpit.
- **Außentemperatur in der Sidebar (#40)**: Aktuelle Temperatur + Min/Max (Tooltip) aus Wetterdaten in der Live-Sidebar.
- **Warmwasser-Temperatur (#41)**: Neuer Live-Sensor für Wärmepumpen (Sensor-Zuordnung → Wärmepumpe → Live-Sensoren). Wird in der Sidebar neben der Außentemperatur angezeigt.
- **Automatische W/kW-Anzeige (#41)**: Energiefluss zeigt unter 1 kW in Watt (z.B. "850 W"), darüber in kW (z.B. "22.0 kW"). Gilt für alle Knoten, Haushalt und Energieumsatz.
- **Solar-Prognose Vor-/Nachmittag (#41)**: Kurzfrist-Aussichten zeigen PV-Ertrag getrennt nach Vormittag (<12h) und Nachmittag (≥12h) — als gestapelte Balken im Chart, in KPI-Cards und Detail-Tabelle. Hilft bei der Planung großer Verbraucher.

### Geändert

- **Demo-Button ausgeblendet (#40)**: Nur noch sichtbar mit URL-Parameter `?debug` — weniger Verwirrung im Normalbetrieb.

## [3.4.5] - 2026-03-22

### Hinzugefügt

- **MQTT Gateway (Stufe 1)**: Topic-Translator für externe MQTT-Geräte (Shelly, Tasmota, OpenDTU, Zigbee2MQTT etc.) — ohne Node-RED oder HA-Automationen. Manuelles Topic-Mapping mit Payload-Transformation (Plain/JSON/Array, Faktor, Offset, Invertierung), Hot-Reload, Topic-Test direkt in der UI. Neuer Bereich auf der MQTT-Inbound-Seite.
- **Connector → MQTT Bridge (Stufe 0)**: Konfigurierte Geräte-Connectors publishen automatisch Live-Leistungswerte (Watt) auf MQTT-Inbound-Topics. Connector-Daten fließen jetzt ins Live-Dashboard und den Energiefluss. Unterstützt: Shelly 3EM, OpenDTU, Fronius, sonnenBatterie, go-eCharger.
- **Energiefluss Lite-Modus**: Reduzierte Animationen für HA Companion App (Android WebView). Auto-Detect für Mobile/Companion + manueller Toggle auf der Live-Page. Schaltet Blur-Filter, 3D-Grid, Partikel und Glow-Effekte ab.
### Behoben

- **MQTT-Topics Parität**: 7 fehlende MQTT-Live-Topics ergänzt die im HA-Sensor-Pfad bereits funktionierten (pv_gesamt_w, netz_kombi_w, SFML-Sensoren, WP-Heizen/Warmwasser/Temperatur). Wichtig für HA-User mit MariaDB/PostgreSQL die MQTT als Fallback nutzen.

## [3.4.2] - 2026-03-22

### Behoben

- **BKW-Erzeugung in Gesamt-PV aufgenommen (#37)**: Balkonkraftwerk-Erzeugung fließt jetzt in die PV-Gesamterzeugung ein. Autarkie, Eigenverbrauch, Prognose-Vergleich und Community-Benchmark werden für BKW-only Nutzer korrekt berechnet. BKW bleibt zusätzlich als separater Komponenten-Wert sichtbar.
- **Daten-Checker: BKW-only kein Fehler mehr (#37)**: Nutzer mit Balkonkraftwerk ohne PV-Module sehen jetzt einen Info-Hinweis statt einer Fehlermeldung.
- **SFML Genauigkeits-Sensor nicht auswählbar (#38)**: Sensoren mit Einheit `%` wurden vom Filter blockiert. Placeholder-Texte auf die realen SFML-Sensornamen aktualisiert.

## [3.4.1] - 2026-03-22

### Hinzugefügt

- **Prognose-Vergleich (ML Phase 2)**: Neuer Vergleichsblock auf der Prognose-vs-IST-Seite — EEDC-Forecast vs. ML-Forecast vs. IST mit Abweichung in %, Balkendiagramm und Detailtabelle mit "Bessere Prognose"-Indikator. Nur sichtbar wenn SFML-Daten vorhanden.
- **SFML Morgen-Vorschau**: Neuer Sensor `sfml_tomorrow_kwh` in der Sensorzuordnung. Zeigt "Morgen ~XX kWh ML" als KPI im Wetter-Widget.
- **SFML-Tagesprognosen persistiert**: ML-Prognosen werden in TagesZusammenfassung gespeichert für langfristigen Vergleich.

## [3.4.0] - 2026-03-22

### Hinzugefügt

- **Solar Forecast ML Integration**: Optionale Anbindung von [Solar Forecast ML](https://github.com/Zara-Toorox/Solar-Forecast-ML) (SFML) im Wetter-Widget. Zeigt ML-basierte PV-Prognose als lila KPI (`~XX kWh ML`) und gepunktete lila Chart-Linie neben der EEDC-Prognose. Konfiguration über Sensor-Zuordnung → Live-Sensoren → Solar Forecast ML. Rein optional — ohne SFML ändert sich nichts.

### Verbessert

- **Dokumentation aktualisiert**: Versionsnummern auf v3.3 in 16 Dokumentationsdateien, Architektur-Doku mit neuen Hooks und Shared Components ergänzt.
- **docs/ aufgeräumt**: Abgeschlossene Pläne archiviert, CSV-Testdaten verschoben, doppelte Screenshots bereinigt.

## [3.3.6] - 2026-03-22

### Verbessert

- **Frontend-Refactoring Phase 7 abgeschlossen**: Alle 27 Seiten auf gemeinsame Hooks (`useSelectedAnlage`, `useApiData`) und Komponenten (`DataLoadingState`, `PageHeader`) migriert. Ca. 300 Zeilen dupliziertes Boilerplate entfernt. Konsistente Anlage-Selektion mit localStorage-Persistierung über alle Seiten.

## [3.3.5] - 2026-03-22

### Hinzugefügt

- **Community-Reset-Hinweis**: Banner auf der Community-Seite informiert Nutzer, dass die Community-Daten durch einen Server-Vorfall am 22.03.2026 verloren gegangen sind und bittet um erneutes Teilen. Der Hinweis kann geschlossen werden und erscheint dann nicht mehr.

### Hinweis

Durch eine fehlerhafte Server-Wartung wurden alle Community-Benchmark-Daten gelöscht. Der Community-Server läuft wieder — bitte teile deine Anlagendaten erneut unter **Community → Daten teilen**, damit der Benchmark wieder aufgebaut werden kann. Wir entschuldigen uns für die Unannehmlichkeiten.

## [3.3.1] - 2026-03-20

### Behoben

- **WP-Symbolwechsel im Energiefluss**: Das Icon der Wärmepumpe wechselt jetzt korrekt zwischen Heizkörper (Heizmodus) und Tropfen (Warmwasser). Bisher wurde der Symbolwechsel nur bei aktivierter „getrennter Strommessung" geprüft. Jetzt werden die optionalen Felder „Leistung Heizen" und „Leistung Warmwasser" immer im Sensor-Mapping angeboten und der dominante Betriebsmodus (höherer Wert) bestimmt das Icon.

## [3.3.0] - 2026-03-20

### Hinzugefügt

- **GTI-basierte PV-Prognose im Live-Dashboard**: Die PV-Ertragsprognose im WetterWidget nutzt jetzt Global Tilted Irradiance (GTI) statt horizontaler Globalstrahlung (GHI). Open-Meteo liefert die Strahlung direkt auf der geneigten Modulfläche — Azimut und Neigung aus den PV-Modul-Investitionen fließen automatisch ein.
- **Multi-String-Prognose**: Bei Anlagen mit unterschiedlich ausgerichteten Modulen (z.B. Ost/West) werden separate GTI-Werte parallel abgerufen und kWp-gewichtet kombiniert. Das ergibt eine realistischere, breitere Tageskurve statt einer überhöhten Mittagsspitze.
- **Lernfaktor**: Täglicher IST/Prognose-Vergleich aus den letzten 30 Tagen wird als Korrekturfaktor angewendet. Kompensiert systematische Abweichungen (Verschattung, Modulalterung, lokale Besonderheiten). Median-basiert für Robustheit gegen Ausreißer, aktiviert sich nach 7 Tagen mit Daten.
- **Temperaturkorrektur**: PV-Ertragsprognose berücksichtigt jetzt die Modultemperatur (Lufttemperatur + strahlungsabhängige Aufheizung, -0.4%/°C über 25°C STC).

### Behoben

- **Frontend-Version im HA Add-on**: Release-Script führt jetzt `npm run build` vor dem Commit durch, damit der dist/-Ordner immer die korrekte Version enthält.

## [3.2.2] - 2026-03-20

### Behoben

- **Tooltip-Farben im Dark Mode** (#31): Chart-Tooltips zeigten seit v3.1.9 keine farbigen Serieneinträge mehr und hatten im Dark Mode teilweise hellen Hintergrund. Neue zentrale `ChartTooltip`-Komponente mit Tailwind-basiertem Dark Mode ersetzt die fehleranfälligen CSS-Variablen. Alle 35 Recharts-Tooltips (Bar, Line, Area, Pie/Donut) einheitlich formatiert.
- **Pie/Donut-Labels im Dark Mode**: Label-Texte an Pie-Charts, Achsenbeschriftungen und Legenden sind im Dark Mode jetzt lesbar.

### Geändert

- **Benutzerhandbuch aufgeteilt** (#32): Monolithisches Handbuch (1.661 Zeilen) in drei Teile gesplittet — Installation, Bedienung, Einstellungen — plus separates Glossar. Website-Navigation angepasst.

## [3.2.1] - 2026-03-19

### Hinzugefügt

- **Italien als Standort-Land** (#30): IT im Land-Dropdown mit automatischem USt-Satz 22%. Italienische PLZ (CAP) korrekt unterstützt, Community-Vergleich mit Länderkennung IT.
- **Dynamisches WP-Icon im Live Dashboard**: Das Wärmepumpen-Icon wechselt je nach Betriebsmodus (Heizen/Warmwasser/Kühlen).

### Behoben

- **Docker-Build im Standalone-Repo**: `run.sh` fehlte im eedc-Repo, da sie nicht vom Release-Script synchronisiert wurde. Das Release-Script kopiert `run.sh` jetzt automatisch mit.

## [3.2.0] - 2026-03-19

### Hinzugefügt

- **Getrennte WP-Strommessung** (#29): Optionale separate Erfassung von Strom-Heizen und Strom-Warmwasser für Wärmepumpen. Ermöglicht getrennte COP-Berechnung pro Komponente (COP Heizung vs. COP Warmwasser). Neue Checkbox "Getrennte Strommessung" in den Investitions-Parametern. Auswirkung auf Monatserfassung, Sensor-Mapping, Monatsabschluss, WP-Dashboard, CSV Import/Export, Live-Dashboard und HA Statistics.
- **Getrennte Live-Leistungssensoren**: Bei aktivierter getrennter Strommessung können separate Leistungssensoren für Heizen und Warmwasser zugeordnet werden. Diese erscheinen als zwei separate Knoten im Energiefluss-Diagramm und als eigene Serien im Tagesverlauf.

Danke an [MartyBr](https://community-smarthome.com/u/martybr) für den Vorschlag!

## [3.1.9] - 2026-03-18

### Hinzugefügt

- **Per-Komponenten Tages-kWh**: Stündliche Leistungswerte pro Komponente (WP, Wallbox, E-Auto, PV-Strings, Speicher) werden jetzt automatisch zu Tages-kWh aufgerollt und in der Tageszusammenfassung persistiert. Grundlage für künftige Tages-/Wochen-Auswertungen pro Komponente.
- **MQTT Energy History für Investitionen**: Investitions-spezifische Energy-Keys (`inv/{id}/{key}`) werden jetzt in der Delta-Berechnung berücksichtigt — auch im Standalone-MQTT-Modus werden per-Komponenten-Tages-kWh erfasst.
- **API-Endpoint Tages-Energieprofil**: Neuer Endpoint `GET /api/energie-profil/{id}/tage?von=...&bis=...` liefert Tageszusammenfassungen mit Per-Komponenten-kWh.

### Behoben

- **Tooltip-Lesbarkeit in Dark/Light Mode** (#27): Alle Recharts-Tooltips nutzen jetzt einheitlich CSS-Variablen statt hardcodierter Farben. Globale CSS-Fallback-Regeln als Sicherheitsnetz.

## [3.1.8] - 2026-03-17

### Hinzugefügt

- **PV Gesamt Live-Sensor** (#25): Neues optionales Feld `pv_gesamt_w` unter Basis → Live im Sensor-Mapping Wizard. Für Wechselrichter die nur einen Gesamt-PV-Sensor liefern (z.B. E3DC) — wird als ein "PV Gesamt"-Knoten im Energiefluss, Tagesverlauf und Heute-kWh angezeigt. Individuelle PV-String-Sensoren werden bevorzugt falls vorhanden.
- **Datenbestand Energieprofile**: Neue Sektion in System → Allgemein zeigt den Bestand der aggregierten Profildaten mit Abdeckungs-Fortschrittsbalken und Wachstumsprognose

## [3.1.7] - 2026-03-17

### Behoben

- **Automatische Einheiten-Konvertierung** (#25): HA-Sensoren mit `suggested_unit_of_measurement` (z.B. E3DC: nativ W, angezeigt als kW) werden jetzt automatisch erkannt und korrekt zu W konvertiert. Betrifft Live-Daten, Tagesverlauf, Tages-kWh und Energieprofil. Keine manuellen kW→W Template-Helper mehr nötig.

## [3.1.6] - 2026-03-17

### Behoben

- **Sensor-Mapping: Anlage-Auswahl** (#26): Bei mehreren Anlagen konnte bisher nur die erste Anlage im Sensor-Mapping Wizard konfiguriert werden. Jetzt erscheint ein Dropdown zur Anlage-Auswahl.
- **Netz-Anzeige Ampel-Schema:** Farbgebung der Netz-Anzeige überarbeitet — Grün = Balance (±100 W), Rot = Netzbezug, Amber = Einspeisung. Kein Balken mehr in der Pufferzone.
- **Grundlast-Berechnung:** Median der Nachtstunden (0–5 Uhr) statt Durchschnitt aller Stunden — robust gegen Ausreißer an der PV-Übergangsstunde.
- **Energiefluss:** „Energieumsatz" statt redundanter Quelle/Senke-Anzeige unter dem Haus-Symbol.
- **Wetter-Timeline:** Stunden-Icons jetzt horizontal mit der Chart-X-Achse ausgerichtet (24h-Grid über dem Chart statt separater Timeline).
- **Wallbox-Icon:** Eigenes Plug-Icon für Wallbox (war identisch mit E-Auto).
- **Legende ohne Phantome:** PV-Chart-Legende zeigt nur Kategorien mit tatsächlichen Werten (keine Wallbox/Sonstige bei 0).

## [3.1.4] - 2026-03-17

### Hinzugefügt

- **Gestapelter Verbrauch im PV-Chart:** Verbrauch im Wetter-Chart wird nach Kategorien aufgeschlüsselt (Haushalt, Speicher-Ladung, Wallbox, Wärmepumpe, Sonstige) statt einer Gesamtlinie. Chart-Höhe verdoppelt (280px). Legende zeigt nur vorhandene Kategorien.
- **Netz-Pufferzone:** Gelbe ±100 W Zone in der Netz-Anzeige reduziert visuelles Flackern bei Werten nahe 0
- **Datenbestand Energieprofile:** Neue Sektion in System → Allgemein zeigt den Bestand der aggregierten Profildaten

### Behoben

- **Verbrauch-Prognose durchgängig:** Gestrichelte Verbrauchs-Prognose-Linie wird jetzt auch für vergangene Stunden angezeigt (IST/Prognose-Vergleich). Kein Sprung mehr an der "Jetzt"-Linie.
- **Stacking-Fix:** 0-Werte in gestapelten Verbrauchskategorien bleiben als 0 statt null — Recharts stackt korrekt
- **Netz-Pufferzone Vollausschlag:** Gelbe Zone war bei kleinem Gauge-Range viel zu breit (Vollausschlag). Jetzt visuell auf max 8% pro Seite begrenzt.
- **Grundlast 0 W:** Stunden ohne HA-History-Daten wurden als 0 kW ins individuelle Verbrauchsprofil geschrieben. Jetzt werden fehlende Stunden übersprungen (BDEW-Fallback greift).
- **Quellen-Indikatoren:** Farbige Punkte an den Balkennamen im Energie-Bilanz-Chart (AktuellerMonat) statt irreführender Pseudo-Legende
- **MariaDB-Hinweis:** Info-Box in Settings warnt dass HA-Statistik nur mit SQLite funktioniert, MQTT-Inbound als Alternative

### Dokumentation

- Energieprofil-Pipeline in ARCHITEKTUR.md, BERECHNUNGEN.md, BENUTZERHANDBUCH.md, DEVELOPMENT.md dokumentiert
- Alle Dokumentationen auf v3.1 aktualisiert, veraltete NEU-Marker entfernt
- README.md (Root + Standalone), Flyer auf v3.1 aktualisiert

## [3.1.1] - 2026-03-16

### Behoben

- **Verbrauch 0,00 kWh bei hoher PV:** Haushalt-Residual im Tagesverlauf wurde aus gerundeten Werten berechnet — akkumulierte Rundungsfehler (±0.005/Serie) konnten den Verbrauch auf 0 drücken. Jetzt aus ungerundeten Rohwerten berechnet.
- **Verbrauch IST im Wetter-Chart:** Berechnung von Butterfly-Senken-Summierung auf Energiebilanz (PV + Netzbezug − Einspeisung) umgestellt — funktioniert unabhängig vom Haushalt-Residual.

## [3.1.0] - 2026-03-16

### Hinzugefügt

- **Wetter-Chart IST/Prognose-Split:** PV-Ertrag vs. Verbrauch zeigt jetzt IST-Daten (solide Linien) für vergangene Stunden und Prognose (gestrichelt) für die Zukunft. Volle 24h-Achse, PV-Prognose auch rückwirkend sichtbar zum Vergleich mit tatsächlicher Erzeugung.
- **Energieprofil-Datenbasis:** Neue persistente Datensammlung als Grundlage für zukünftige Speicher-Dimensionierungsanalyse:
  - Stündliches Energieprofil (24 Werte/Tag) mit Per-Komponenten-Aufschlüsselung, Wetter-IST, Batterie-SoC
  - Tägliche Zusammenfassung: Über-/Unterdeckung (kWh), Spitzenleistungen, Batterie-Vollzyklen, Performance Ratio
  - Automatische tägliche Aggregation (Scheduler, 00:15)
  - Nachberechnung beim Monatsabschluss (Backfill + Rollup)
- **Monatsdaten erweitert:** Neue Felder `ueberschuss_kwh`, `defizit_kwh`, `batterie_vollzyklen`, `performance_ratio`, `peak_netzbezug_kw`
- **Tagesverlauf historisch:** `tage_zurueck` Parameter ermöglicht Abruf vergangener Tage

### Behoben

- **Batterie-Vorzeichen im Tagesverlauf:** Bidirektionale Serien (Batterie) hatten invertierte Vorzeichen — Entladung wurde als Senke statt Quelle dargestellt, Haushalt-Residual war dadurch zu hoch
- **Verbrauch IST im Wetter-Chart:** Exkludiert jetzt korrekt Batterie-Ladung und Netz-Einspeisung (keine echten Verbraucher)

## [3.0.9] - 2026-03-16

### Hinzugefügt

- **HA Automation Generator:** Integrierter Wizard in der MQTT-Inbound-Seite — HA-Sensoren den EEDC-Topics zuordnen und zwei fertige YAML-Automationen (Live + Energy) zum Kopieren erhalten. Anlage-Auswahl, konfigurierbares Intervall (5s/10s/30s/60s), automatische YAML-Generierung.
- **Andere Systeme:** Beispiel-Flows für Node-RED, ioBroker, FHEM, openHAB in eigenem Bereich

### Geändert

- **Beispiel-Flows aufgeteilt:** HA-Nutzer nutzen den neuen Generator, andere Systeme haben einen separaten Bereich

## [3.0.8] - 2026-03-15

### Hinzugefügt

- **Live Sidebar-Redesign:** Zustandswerte-Bereich komplett neu gestaltet
  - „Heute"-Karten: PV-Erzeugung, Eigenverbrauch, Einspeisung, Netzbezug (farbcodiert, kWh)
  - Autarkie- und Eigenverbrauchsquote als berechnete Prozentwerte
  - PV- und Verbrauchs-Prognose direkt in der Sidebar
  - SoC-Gauges nur noch für Batterie/E-Auto (statt alle Gauges)
  - Netz: horizontaler Balken mit 0-Mitte (grün=Einspeisung, rot=Bezug)
  - Gestern-Vergleich als Tooltip auf jeder Karte
- **MQTT-Beispiel-Flows personalisiert:** Topic-Auswahl-Dropdown mit allen konfigurierten Topics, kontextbezogene Sensor-Platzhalter, `retain: true` in allen Snippets

### Verbessert

- **Energiefluss ~10% kompakter:** Alle Skalierungsstufen verkleinert für bessere FHD-Darstellung
- **Energiefluss dynamische Skalierung:** 3 Stufen (≤3, 4, 5+ Komponenten) mit angepassten Boxen/Fonts
- **Sidebar füllt SVG-Höhe:** `flex justify-between` verteilt Elemente optimal

### Behoben

- **Haushalt-Residual:** parent_key statt eauto_ Prefix für korrekte Zuordnung
- **E-Auto Position:** Rechts neben Wallbox im Energiefluss statt separate Zeile
- **Heute-kWh Tooltips:** Pro Komponente im Energiefluss

## [3.0.5] - 2026-03-15

### Behoben

- **Energiefluss: Wallbox/E-Auto Key-Kollision:** Wallbox und E-Auto hatten beide den Key-Prefix `eauto_`, wodurch die parent_key-Zuordnung fehlschlug. Wallbox hat jetzt eigenen Prefix `wallbox_`
- **Energiefluss: SVG-Höhe dynamisch:** ViewBox passt sich an Kind-Knoten an statt fixer Höhe

## [3.0.4] - 2026-03-15

### Behoben

- **Energiefluss: E-Auto/Wallbox Doppelzählung:** E-Auto-Ladeleistung wurde separat zur Wallbox-Leistung in Σ Verbrauch gezählt, obwohl beides denselben Energiefluss misst
- **Energiefluss: E-Auto → Wallbox Verbindung:** E-Auto verbindet sich jetzt mit der Wallbox statt direkt mit dem Haus (physisch korrekt: Haus → Wallbox → E-Auto)

## [3.0.3] - 2026-03-15

### Hinzugefügt

- **Energiefluss-Diagramm:** Neues animiertes SVG-Diagramm im Live Dashboard ersetzt die Energiebilanz-Balken
  - Alle Investitionen als Knoten um zentrales Haus-Symbol
  - Animierte Flusslinien zeigen Energierichtung und -stärke
  - SoC-Pegelanzeige für Speicher und E-Auto (farbcodiert: rot/gelb/grün)
  - Logarithmische Liniendicke, Tooltips mit Tages-kWh

### Behoben

- **Zeitzone:** `datetime.utcnow()` durch `datetime.now()` ersetzt — HA Add-on zeigte Uhrzeiten mit 1h Offset

## [3.0.2] - 2026-03-15

### Behoben

- **run.sh:** Fehlendes Anführungszeichen in Version-Echo repariert (sed-Pattern fraß das `"`)
- **Release-Script:** sed-Pattern auf `[0-9][0-9.]*` eingeschränkt, damit nachfolgende Zeichen erhalten bleiben

## [3.0.1] - 2026-03-15

### Behoben

- **Release-Infrastruktur:** Dockerfile `io.hass.version` Label wird jetzt automatisch gebumpt (war seit v0.9.0 hartcodiert)
- **Release-Script:** sed-Bug behoben (überflüssiges Anführungszeichen beim run.sh-Bump)
- **GitHub Release Workflow:** eedc-homeassistant erstellt jetzt automatisch ein GitHub Release bei Tag-Push (fehlte komplett)

## [3.0.0] - 2026-03-15

### Hinzugefügt

- **Live Dashboard** – Neuer Top-Level-Tab mit Echtzeit-Leistungsdaten (kW), 5-Sekunden Auto-Refresh
  - Energiebilanz-Tabelle mit gespiegelten Balken (Erzeugung links, Verbrauch rechts)
  - Gauge-Charts für SoC (Batterie, E-Auto), Netz-Richtung, Autarkie
  - Tagesverlauf-Chart (24h PV/Verbrauch/Netz/Speicher)
  - Wetter-Widget mit Stunden-Prognose und PV/Verbrauch-Vorhersage
  - Heute/Gestern kWh-Tagessummen (aus HA-History oder MQTT-Snapshots)
  - Demo-Modus für Erstnutzer ohne konfigurierte Sensoren
- **MQTT-Inbound** – Universelle Datenbrücke für jedes Smarthome-System
  - Vordefinierte MQTT-Topic-Struktur für Live-Daten (W) und Monatswerte (kWh)
  - In-Memory-Cache mit Auto-Reconnect und Retained Messages
  - Einrichtungs-UI mit Monitor, Topic-Dokumentation und Beispiel-Flows (HA, Node-RED, ioBroker, FHEM, openHAB)
  - Copy-to-Clipboard für alle Topics und Code-Snippets
- **MQTT Energy → Monatsabschluss** – MQTT-Daten als 6. Datenquelle im Monatsabschluss-Wizard
  - Konfidenz 91% (zwischen Connector 90% und HA Statistics 92%)
  - Energy-Topic-Generierung für alle Investitionstypen (PV, Speicher, WP, E-Auto, Wallbox, BKW)
  - Status-Chip im Wizard-Header, Datenherkunft-Tracking
- **MQTT Energy Mini-History** – SQLite-basierte Snapshot-Historie für Standalone-MQTT-Nutzer
  - Automatische Snapshots alle 5 Minuten via APScheduler
  - Tages-Delta-Berechnung (Mitternacht-Differenzen, Monatswechsel-Handling)
  - 31 Tage Retention mit täglichem Cleanup
  - Fallback-Kette: HA-History → MQTT-Snapshots → leer
- **Live-Sensor-Zuordnung** – Wiederverwendbare Sensor-Konfiguration pro Investitionstyp im Mapping-Wizard
  - Vordefinierte Leistungs-Felder (W) pro Typ (PV, Speicher, WP, E-Auto, Wallbox, BKW)
  - SensorAutocomplete mit device_class: power Filter
- **HA Export: Investitions-Sensoren** – E-Auto (km, kWh/100km, PV-Anteil, Ersparnis vs. Benzin) und WP (COP, Ersparnis vs. alte Heizung) Sensoren aus InvestitionMonatsdaten

### Behoben

- **PDF-Report: WP-Ersparnis** – Berechnet jetzt vs. Gas/Öl aus Investitionsparametern (war 0)
- **PDF-Report: E-Mob-Ersparnis** – Berechnet jetzt vs. Benzin aus Investitionsparametern (war 0)
- **Live Dashboard: Haushalt-Berechnung** – Korrekte Berechnung als Residualwert
- **Live Dashboard: Wechselrichter-Skip** – Investitionen vom Typ „Wechselrichter" werden ausgefiltert
- **Live Dashboard: Negative Verbraucher-kW** – abs() für Sensoren die negative Standby-Werte melden
- **MQTT Port-Validierung** – Nicht-numerischer Port gibt 400 statt 500
- **Initialer MQTT-Snapshot** – Fehlender Logger-Import behoben (NameError wurde still geschluckt)

---

## [2.9.1] - 2026-03-13

### Geändert

- **HA Statistics statt MQTT MWD** – Monatsdaten für „Aktueller Monat" und Monatsabschluss werden jetzt direkt aus der HA Recorder-Statistik-DB gelesen (MAX−MIN). Die fehleranfälligen MWD-MQTT-Sensorpaare (`number.*_mwd_*_start` / `sensor.*_mwd_*_monat`) wurden komplett entfernt.
- **MQTT nur noch für Export** – MQTT wird nur noch zum Exportieren von EEDC-KPIs nach HA verwendet, nicht mehr zum Lesen von Monatsdaten.
- **Sensor-Zuordnung vereinfacht** – Init-Startwerte-Dialog nach dem Speichern entfällt, `mqtt_setup_complete`-Flag entfernt.
- **Scheduler** – Monatswechsel-Job ist jetzt nur noch ein Zeitstempel-Marker, kein MQTT-Rollover mehr.

### Hinzugefügt

- **Einrichtung: HA Sensor-Zuordnung** – Neue Karte auf der Einrichtungs-Seite verlinkt direkt zur Sensor-Zuordnung.
- **Typabhängige Aggregation** – Investitions-Felder (PV, Speicher, E-Auto, Wallbox, WP, BKW) werden automatisch in die Top-Level-Felder des Aktueller-Monat-Dashboards aggregiert.
- **HA-Statistik Quellen-Badge** – Aktueller Monat und Monatsabschluss zeigen „HA-Statistik" als Datenquelle an.

### Behoben

- **Strompreis-Sensor** – `get_ha_state_service()` wurde im Monatsabschluss nicht instanziiert (AttributeError bei dynamischem Tarif).
- **Speicher vs. Wallbox** – Wallbox-Ladung wurde fälschlich in `speicher_ladung_kwh` summiert statt in `emob_ladung_kwh`.

---

## [2.9.0] - 2026-03-12

### Hinzugefügt

- **Aktueller-Monat-Dashboard** – Neues Cockpit-Sub-Tab zeigt den laufenden Monat mit Daten aus HA-Sensoren (95%), Connectors (90%) und gespeicherten Monatsdaten (85%). Enthält Energie-Bilanz-Charts, Komponenten-Karten, Finanz-Übersicht, Vorjahresvergleich und SOLL/IST-Vergleich.
- **Anlage-Selektor** – Cockpit-Übersicht und Aktueller Monat zeigen jetzt einen Anlage-Selektor wenn mehrere Anlagen vorhanden sind
- **Datenquellen-Badges** – Farbige Indikatoren zeigen pro Feld die Herkunft (HA-Sensor, Connector, Gespeichert)
- **Leerer-Zustand-Aktionen** – Wenn keine Daten vorliegen, werden konkrete Import-Möglichkeiten (Monatsabschluss, Connector, Cloud-Import, Portal-Import) als Aktionskarten angeboten
- **Live-Dashboard Plan** – Architekturplan für Stufe 2 (Echtzeit-Leistungsdaten kW) dokumentiert

---

## [2.8.5] - 2026-03-11

### Behoben

- **MQTT: object_id Deprecation** – `object_id` im MQTT Discovery Payload durch `default_entity_id` ersetzt (HA 2026.4 Kompatibilität)

---

## [2.8.4] - 2026-03-10

### Behoben

- **CSV-Export: Fehlende BKW-Erzeugung** – Balkonkraftwerk-Erzeugung wurde unter falschem Feldnamen gespeichert, daher im Export leer (Issue #22)
- **CSV-Export: Dezimaltrennzeichen** – Punkt statt Komma für deutsche Locale, jetzt korrekt mit Semikolon-Trennung und Dezimalkomma
- **CSV-Export: UTF-8 BOM** – Für korrekte Zeichenkodierung in Excel/LibreOffice
- **Monatsdaten-Formular: 0-Werte** – Wert `0` wurde als leer interpretiert und nicht gespeichert (betraf alle Investitionstypen)
- **Aussichten-Finanzen: EV-Quote** – Eigenverbrauchsquote wird jetzt direkt aus historischen Daten berechnet statt synthetisch zerlegt (Issue #21)

---

## [2.8.3] - 2026-03-09

### Hinzugefügt

- **Daten-Checker** – Neue Datenqualitäts-Prüfung unter Einstellungen → Daten
  - 5 Prüfkategorien: Stammdaten, Strompreise, Investitionen, Monatsdaten-Vollständigkeit/-Plausibilität
  - PVGIS-basierte PV-Produktionsprüfung mit dynamischer Performance Ratio
  - Erkennt zu hohe PVGIS-Systemverluste anhand der tatsächlichen Anlagenperformance
  - KPI-Karten, Fortschrittsbalken für Monatsabdeckung, klappbare Kategorien
  - „Beheben"-Links verweisen direkt zum betroffenen Monatsabschluss
- **Protokolle** – Aktivitäts-Logging unter Einstellungen → System
  - Protokollierung von Monatsabschluss, Connector-Abruf, Cloud-Fetch, Portal-Import
  - Live-Filter nach Kategorie und Zeitraum
  - In-Memory Log-Buffer + DB-Persistierung

---

## [2.8.1] - 2026-03-07

### Behoben

- **Custom-Import:** DATEN-Navigationsleiste fehlte auf der Custom-Import-Seite

---

## [2.8.0] - 2026-03-07

### Hinzugefügt

- **5 neue Cloud-Import-Provider** – Historische Monatsdaten direkt aus der Cloud abrufen
  - **SolarEdge** – Monitoring API mit API-Key, monatliche Energiedetails (*)
  - **Fronius SolarWeb** – SolarWeb API mit AccessKey, Monatsaggregation (*)
  - **Huawei FusionSolar** – thirdData API mit XSRF-Token, KPI-Monatswerte (*)
  - **Growatt** – OpenAPI mit MD5-Auth, Monats-Ertragsdaten (*)
  - **Deye/Solarman** – SolarMAN OpenAPI mit OAuth2 + SHA256, historische Monatsdaten (*)
- **Eigene Datei importieren (Custom-Import)** – Neuer Wizard für beliebige CSV/JSON-Dateien
  - Automatische Spalten-Erkennung mit Beispielwerten
  - Flexibles Feld-Mapping per Dropdown (Spalte → EEDC-Feld)
  - Auto-Detect für Spaltenbezeichnungen (deutsch + englisch)
  - Einheit wählbar (Wh/kWh/MWh) mit automatischer Umrechnung
  - Dezimalzeichen konfigurierbar (Auto/Punkt/Komma)
  - Kombinierte Datumsspalte (z.B. "2024-01") oder separate Jahr/Monat-Spalten
  - Mapping als wiederverwendbares Template speichern/laden
  - 4-Schritt-Wizard: Upload → Mapping → Vorschau → Import
  - Neue Kachel "Eigene Datei importieren" auf der Einrichtung-Seite

### Entfernt

- **Kostal Plenticore** und **SMA Local** Cloud-Import-Provider entfernt
  (liefern nur aktuelle Zählerstände, keine historischen Monatsdaten –
  für diese Geräte die Geräte-Connectors verwenden)

(*) Ungetestet – basiert auf Hersteller-API-Dokumentation

---

## [2.7.1] - 2026-03-06

### Verbessert

- **Einstellungen-Menü überarbeitet** – Logische Gruppierung mit 5 Kategorien, Solarprognose zu Stammdaten verschoben
- **Daten-SubTabs vereinfacht** – Statt 8 Tabs nur noch 3: Monatsdaten, Monatsabschluss, Einrichtung
- **Neue Einrichtung-Seite** – Hub mit 4 Karten für alle Datenquellen-Setups (Connector, Portal-Import, Cloud-Import, CSV/JSON)
- **Monatsabschluss Quick-Icon** – CalendarCheck-Button mit rotem Badge in der Hauptnavigation (Desktop + Mobile)
- **Monatsabschluss-Wizard als zentrale Anlaufstelle** – Quellen-Status-Chips zeigen konfigurierte Datenquellen,
  neuer "Cloud-Daten abrufen" Button, Hinweis auf Einrichtung wenn keine Quellen konfiguriert,
  Datenherkunft-Anzeige bei vorhandenen Import-Daten

### Behoben

- Investition-Felder im Monatsabschluss zeigen jetzt die tatsächliche Datenquelle statt immer "manuell"
- CompleteStep: HashRouter-Navigation korrigiert (`window.location.hash` statt `.href`)

### Hinzugefügt

- Backend-Endpoint `POST /monatsabschluss/{id}/{j}/{m}/cloud-fetch` für Einzelmonat-Abruf aus Cloud-API

---

## [2.7.0] - 2026-03-06

### Hinzugefügt

- **Cloud-Import** – Historische Energiedaten direkt aus Hersteller-Cloud-APIs importieren
  - Generische Cloud-Import-Provider-Architektur (ABC + Registry, analog zu Portal-Import)
  - EcoFlow PowerOcean als erster Provider (Developer API mit HMAC-SHA256 Auth) (*)
  - 4-Schritt-Wizard: Verbinden → Zeitraum → Vorschau → Import
  - Credentials pro Anlage speicherbar für wiederholte Imports
  - Wiederverwendung des bestehenden Apply-Mechanismus (Portal-Import)
  - Datenquelle-Tracking: `cloud_import` als neue Quelle neben `portal_import`
- **Exakte Azimut-Eingabe** – PV-Module können jetzt gradgenau ausgerichtet werden (nicht nur 45°-Schritte)
  - Neues Eingabefeld "Azimut (°)" synchronisiert mit dem bestehenden Dropdown
  - Alle PVGIS-Berechnungen nutzen den exakten Wert

(*) Ungetestet – basiert auf Hersteller-API-Dokumentation, indexName-Mapping muss mit echten Daten verifiziert werden

---

## [2.6.0] - 2026-03-05

### Hinzugefügt

- **Portal-Import (CSV-Upload)** – Automatische Erkennung und Import von PV-Portal-Exporten
  - SMA Sunny Portal (PV-Ertrag, Netz, Batterie)
  - SMA eCharger (Wallbox-Ladevorgänge)
  - EVCC (Wallbox-Sessions mit PV-Anteil)
  - Fronius Solarweb (PV-Ertrag, Eigenverbrauch)
- **9 Geräte-Connectors** – Direkte Datenabfrage von Wechselrichtern und Smart-Home-Geräten
  - SMA ennexOS (Tripower X, Wallbox EVC)
  - SMA WebConnect (Sunny Boy, Tripower SE)
  - Fronius Solar API (Symo, Primo, Gen24)
  - go-eCharger (Gemini/HOME v3+)
  - Shelly 3EM (Netz-Monitoring)
  - OpenDTU (Hoymiles/TSUN Mikro-Wechselrichter)
  - Kostal Plenticore (Plenticore plus, PIKO IQ)
  - sonnenBatterie (eco/10 performance)
  - Tasmota SML (Smart Meter via IR-Lesekopf)
- **getestet-Flag** – Parser und Connectors zeigen im UI an ob mit echten Geräten verifiziert
- **Dynamischer Tarif: Monatlicher Durchschnittspreis** – Neues optionales Feld `netzbezug_durchschnittspreis_cent` auf Monatsdaten
  - Wird nur bei dynamischen Tarifen (Tibber, aWATTar) abgefragt
  - Alle Finanzberechnungen nutzen den Monatsdurchschnitt statt des fixen Stammdatenpreises
  - Fallback-Kette: Monats-Durchschnittspreis → Fixer Tarif aus Stammdaten
  - Gewichteter Durchschnittspreis (nach kWh) bei Jahresaggregation im Cockpit
- **Arbitrage-Fallback** – `speicher_ladepreis_cent` → `netzbezug_durchschnittspreis_cent` → Stammdaten-Tarif
- **CSV-Template/Export/Import** – Bedingte Spalte `Durchschnittspreis_Cent` bei dynamischem Tarif
- **JSON-Export/Import** – Neues Feld in Export-Schema
- **MonatsdatenForm** – Bedingtes Eingabefeld "Ø Strompreis (dynamisch)" bei dynamischem Tarif
- **Monatsabschluss-Wizard** – Bedingtes Feld mit HA-Sensor-Vorschlag bei dynamischem Tarif
- **HA-Sensormapping** – Neues Basis-Feld `strompreis` für direktes Sensor-Lesen (kein MWD-Paar)
  - Sensor-Filter erweitert um `monetary` device_class und Preis-Einheiten (EUR/kWh, ct/kWh)

---

## [2.5.5] - 2026-03-03

### Hinzugefügt

- **Hamburger-Menu auf Mobile** ([#18](https://github.com/supernova1963/eedc-homeassistant/issues/18)): Navigation auf schmalen Displays (< 768px) über ausklappbares Menü statt horizontaler Tab-Leiste
- **Energie-Bilanz Perspektiv-Toggle** ([#19](https://github.com/supernova1963/eedc-homeassistant/issues/19)): Umschaltung zwischen Erzeugungs- und Verbrauchsperspektive im Energie-Chart, optionale Autarkie-Linie

### Behoben

- **Mobile Tab-Overflow:** Tab-Navigationen auf Auswertung, Aussichten und HA-Export liefen auf schmalen Displays über den Rand – jetzt horizontal scrollbar

---

## [2.5.4] - 2026-03-03

### Hinzugefügt

- **WP Monatsvergleich – Toggle zwischen Stromverbrauch und COP:** Im Wärmepumpe-Dashboard kann jetzt zwischen Stromverbrauch- und COP-Ansicht umgeschaltet werden

### Behoben

- **PVGIS Monatswerte Export:** list statt dict erlauben bei der Serialisierung
- **Bessere Fehlerbehandlung im JSON-Export Endpoint:** Robustere Serialisierung
- **Backup im Einstellungen-Dropdown ergänzt:** Menüeintrag war nicht sichtbar

---

## [2.5.3] - 2026-03-02

### Hinzugefügt

- **WP Dashboard – COP Monatsvergleich über Jahre:** Vergleich der COP-Werte über mehrere Betriebsjahre

### Behoben

- **Fehlende Felder im Monatsabschluss-Wizard ergänzt**
- **HA-Statistik Feldnamen-Mapping für Monatsabschluss korrigiert**
- **Degradation:** Positive Degradationswerte werden gekappt, Warnung bei < 3 Jahren Betriebsdauer

---

## [2.5.2] - 2026-03-01

### Hinzugefügt

- **Backup & Restore Seite im System-Menü:** Neue dedizierte Seite für Datensicherung

### Behoben

- **JSON Export/Import auf Vollständigkeit gebracht (v1.2)**
- **Demo-Daten Route scrollt zur Demo-Sektion**
- **HA-Mapping Hinweis nur bei verfügbarem Home Assistant anzeigen**
- **PVGIS Horizont-Abruf:** API-Key "horizon" → "horizon_profile"

---

## [2.5.1] - 2026-03-01

### Geändert

- Dokumentation und Website aktualisiert

---

## [2.5.0] - 2026-03-01

### Hinzugefügt

- **PVGIS Horizontprofil-Support für genauere Ertragsprognosen**
  - Automatisches Geländeprofil (DEM) bei allen PVGIS-Abfragen aktiv (`usehorizon=1`)
  - Eigenes Horizontprofil hochladen (PVGIS-Textformat) oder automatisch von PVGIS abrufen
  - Horizont-Card in PVGIS-Einstellungen mit Status, Statistik und Upload/Abruf
  - Badge "Eigenes Profil" / "DEM" bei gespeicherten Prognosen
  - Horizontprofil im JSON-Export/Import enthalten

- **GitHub Releases & Update-Hinweis (Standalone)**
  - Automatische GitHub Releases mit Docker-Image auf ghcr.io bei Tag-Push
  - Update-Banner im Frontend wenn neuere Version verfügbar
  - Deployment-spezifische Update-Anleitung (Docker, HA Add-on, Git)

- **Social-Media-Textvorlage** ([#16](https://github.com/supernova1963/eedc-homeassistant/issues/16))
  - Kopierfertige Monatsübersicht für Social-Media-Posts
  - Zwei Varianten: Kompakt (Twitter/X) und Ausführlich (Facebook/Foren)
  - Bedingte Blöcke je nach Anlagenkomponenten (Speicher, E-Auto, Wärmepumpe)
  - PVGIS-Prognose-Vergleich, CO₂-Einsparung, Netto-Ertrag
  - Share-Button im Dashboard-Header mit Modal, Monat/Jahr-Auswahl und Clipboard-Kopie

### Behoben

- **Community-Vorschau zeigte falsche Ausrichtung und Neigung**: Werte wurden aus leerem Parameter-JSON gelesen statt aus Modelfeldern

---

## [2.4.1] - 2026-02-26

### Technisch

- Version-Bump: v2.4.0 wurde force-pushed und war für HA Add-on-Store nicht als Update erkennbar

---

## [2.4.0] - 2026-02-26

### Hinzugefügt

- **Kleinunternehmerregelung / Steuerliche Behandlung (Issue #9)**
  - Neues Feld `steuerliche_behandlung` auf der Anlage: „Keine USt-Auswirkung" (Standard) oder „Regelbesteuerung"
  - Bei Regelbesteuerung: USt auf Eigenverbrauch (unentgeltliche Wertabgabe §3 Abs. 1b UStG) wird als Kostenfaktor berechnet
  - Bemessungsgrundlage: Selbstkosten (Abschreibung/20J + Betriebskosten / Jahresertrag)
  - Editierbarer USt-Satz mit länderspezifischen Defaults (DE: 19%, AT: 20%, CH: 8.1%)
  - Auto-Vorschlag des USt-Satzes bei Land-Wechsel
  - Dashboard: Neue KPI-Karte „USt Eigenverbrauch" (nur bei Regelbesteuerung sichtbar)
  - Netto-Ertrag-Berechnung im Cockpit, Aussichten und ROI-Dashboard berücksichtigt USt
  - Hinweis im Setup-Wizard: Steuerliche Einstellungen unter Anlage bearbeiten konfigurierbar

- **Spezialtarife für Wärmepumpe & Wallbox (Issue #8)**
  - Neues Feld `verwendung` auf Strompreisen: „Standard", „Wärmepumpe" oder „Wallbox"
  - Neuer API-Endpoint `/api/strompreise/aktuell/{anlage_id}/{verwendung}` mit Fallback auf Standard-Tarif
  - Cockpit-Berechnung nutzt automatisch den günstigsten zutreffenden Tarif pro Komponente
  - Strompreise-Seite: Sortierung (aktuell + Standard zuerst), Verwendungs-Badges, Info-Box für aktive Spezialtarife
  - Tarif-Formular: Neues Dropdown „Tarif-Verwendung" mit kontextabhängigem Hinweis

- **Sonstige Positionen bei Investitionen (Issue #7)**
  - Neuer Investitionstyp „Sonstiges" mit Kategorien: Erzeuger, Verbraucher, Speicher
  - Flexible Monatsdaten-Erfassung je nach Kategorie (Erzeugung/Verbrauch/Ladung-Entladung)
  - Sonstige Erträge & Ausgaben pro Monat (Versicherung, Wartung, Einspeisebonus, etc.)
  - Integration in Dashboard: Finanzen-Tab zeigt sonstige Erträge/Ausgaben
  - Demo-Daten: Beispiel „Notstrom-Batterie" als sonstiger Speicher

- **Firmenwagen & dienstliches Laden – korrekte ROI-Berechnung**
  - Neues Flag `ist_dienstlich` an Wallbox und E-Auto (in Investitions-Parametern)
  - **Wallbox (dienstlich):** ROI = AG-Erstattung minus (Netzbezug × Strompreis + PV-Anteil × Einspeisevergütung); kein Benzinvergleich
  - **E-Auto (dienstlich):** Kraftstoffersparnis geht an Arbeitgeber → `emob_ersparnis = 0`; Ladekosten als Ausgaben; AG-Erstattung als sonstiger Ertrag
  - Hinweistext im Investitionsformular bei aktiviertem Flag (Erklärung + Tipp für gemischte Nutzung)
  - DatenerfassungGuide: neuer Abschnitt „Firmenwagen & dienstliches Laden" mit Empfehlung separater Zähler

- **Realisierungsquote KPI in Auswertung → Investitionen**
  - Neues Panel „Tatsächlich realisiert" vergleicht historische Erträge mit konfigurierter Prognose
  - Realisierungsquote in % mit Farbkodierung: ≥ 90 % grün, ≥ 70 % gelb, < 70 % rot
  - Zeigt die Diskrepanz zwischen parametriertem Potenzial (z.B. 15.000 km/Jahr E-Auto) und tatsächlicher Nutzung

- **Methodenhinweise in Dashboard und Komponenten-Dashboards**
  - Amortisationsbalken im Cockpit: Hinweis „Basis: tatsächlich realisierte Erträge & Kosten (Ø X €/Jahr über N Monate)"
  - E-Auto-, Wärmepumpe-, Balkonkraftwerk-Dashboard: Methodennotiz unter den KPIs (Basis: Monatsdaten)

- **Grundpreis in Netzbezugskosten-Berechnung**
  - Monatlicher Stromgrundpreis wird zu Netzbezugskosten addiert (`calculations.py`, Auswertung/Zeitreihen)

- **Monatsabschluss-Wizard Erweiterungen**
  - Balkonkraftwerk: Speicher-Ladung/Entladung für BKW-Modelle mit integriertem Speicher erfassbar
  - Typ „Sonstiges": kategorie-spezifische Felder (Erzeuger / Verbraucher / Speicher)
  - API-Response liefert `sonstige_positionen` für alle Investitionstypen (nicht nur „Sonstiges")
  - Neue shared Component `SonstigePositionenFields` für strukturierte Ertrags-/Ausgaben-Erfassung

- **SubTabs group-aware Navigation**
  - Tab-Gruppen mit visueller Trennung für bessere Übersichtlichkeit bei vielen Tabs

- **DatenerfassungGuide überarbeitet**
  - Modernere Struktur und Erklärungen; neuer Abschnitt Firmenwagen; Legacy-Guide aufklappbar

### Behoben

- **Leeres Installationsdatum verursachte Setup-Wizard-Fehler (Issue #10):** StrompreiseStep akzeptiert jetzt fehlende Installationsdaten und setzt vernünftige Defaults
- **sonstige_positionen wurde nur für Investitionstyp „Sonstiges" verarbeitet:** Jetzt werden Erträge/Ausgaben aus `sonstige_positionen` für ALLE Investitionstypen in Cockpit und Amortisationsprognose berücksichtigt (z.B. Wartungskosten bei Wärmepumpe, THG-Quote bei E-Auto)
- **BKW Ersparnis und sonstige Netto-Beträge fehlten in Amortisationsprognose (Aussichten → Finanzen):** `bisherige_ertraege` und `jahres_netto_ertrag` waren unvollständig

### Technisch

- DB-Migration: Neue Spalten `steuerliche_behandlung`, `ust_satz_prozent` (Anlage), `verwendung` (Strompreis) – automatisch beim Start
- Neue Berechnungsfunktion `berechne_ust_eigenverbrauch()` in `calculations.py`
- Neue Helper-Funktion `berechne_sonstige_summen()` für sonstige Erträge/Ausgaben
- JSON Export/Import: Steuerliche Felder und Strompreis-Verwendung werden mit exportiert/importiert
- CSV Import: Sonstige Positionen werden korrekt verarbeitet
- `CockpitUebersicht` API-Response: neue Felder `bkw_ersparnis_euro`, `sonstige_netto_euro`

---

## [2.3.2] - 2026-02-24

### Behoben

- **SOLL-Werte im PV-String-Vergleich waren zu hoch – drei Ursachen behoben:**
  1. **Ost-West-Anlagen:** Ausrichtung `ost-west` wurde bisher als Süd (Azimut 0°) an PVGIS übergeben, was ~20–25 % zu hohe SOLL-Werte lieferte. Jetzt werden zwei separate PVGIS-Abfragen durchgeführt (je 50 % kWp auf Ost −90° und West +90°) und die Ergebnisse summiert.
  2. **Proportionale kWp-Verteilung:** Der gespeicherte PVGIS-Gesamtwert wurde bisher anteilig nach kWp auf die einzelnen Strings verteilt – ohne Rücksicht auf unterschiedliche Ausrichtungen. Jetzt werden pro Modul die exakten PVGIS-Werte gespeichert (`module_monatswerte`) und direkt genutzt.
  3. **Teil-Jahre / laufendes Jahr (Auswertungen → PV-Anlage):** SOLL enthielt bisher alle 12 Monate eines Jahres, auch wenn IST-Daten nur für einen Teil des Jahres vorlagen (z.B. Anlage ab Mai, oder laufendes Jahr mit Jan–Feb). Jetzt wird SOLL nur für Monate gezählt, für die auch IST-Daten erfasst sind.

### Technisch

- `PVGISPrognose`-Modell: Neue Felder `gesamt_leistung_kwp` und `module_monatswerte` (JSON)
- DB-Migration läuft automatisch beim Start
- **Wichtig:** Nach dem Update einmalig die PVGIS-Prognose unter *Einstellungen → PVGIS* neu abrufen und speichern, um die korrekten per-Modul-Werte zu erhalten

---

## [2.3.1] - 2026-02-24

### Behoben

- **Docker Build-Fehler behoben:** `package-lock.json` synchronisiert – picomatch Versionskonflikt (2.3.1 → 4.0.3) verhinderte `npm ci` im HA Add-on Build

---

## [2.3.0] - 2026-02-24

### Hinzugefügt

- **Dashboard-Modernisierung (6 neue Features)**
  - **Hero-Leiste:** 3 Top-KPIs (Autarkie, Spez. Ertrag, Netto-Ertrag) mit Jahres-Trend-Pfeilen (▲/▼/—) im Vergleich zum Vorjahr
  - **Energie-Fluss-Diagramm:** Gestapelte Balkendiagramme visualisieren PV-Verteilung (Direktverbrauch, Speicher, Einspeisung) und Haus-Versorgungsquellen (PV direkt, Speicher, Netzbezug)
  - **Ring-Gauges:** SVG-Ringdiagramme für Autarkie- und Eigenverbrauchsquote ersetzen die bisherigen Zahlenkarten
  - **Sparkline:** Monatliche PV-Erträge als kompaktes Balkendiagramm im Energie-Bilanz-Bereich
  - **Amortisations-Fortschrittsbalken:** Zeigt wie viel % der Investition bereits zurückgeflossen sind inkl. geschätztem Amortisationsjahr (nur in Gesamtansicht)
  - **Community-Teaser:** Hinweiskarte mit Link zur Community-Seite (nur sichtbar wenn Daten bereits geteilt wurden)

- **DACH-Onboarding vorbereitet**
  - Neues Feld `standort_land` (DE/AT/CH) im Anlage-Modell
  - Land-Dropdown im Anlage-Formular (Deutschland, Österreich, Schweiz)
  - Community-Regionszuordnung: AT/CH direkt zugeordnet (keine PLZ-Auflösung nötig)
  - JSON-Export/Import berücksichtigt `standort_land`

### Geändert

- **Sparkline zeigt Gesamtzeitraum:** Ohne Jahresfilter werden alle verfügbaren Monate gezeigt (konsistent mit dem Rest des Dashboards), Label zeigt z.B. „2023–2025"

---

## [2.2.0] - 2026-02-22

### Hinzugefügt

- **Choropleth Deutschlandkarte im Regional Tab**
  - Interaktive Bundesländer-Karte mit Farbverlauf nach spezifischem Ertrag (kWh/kWp)
  - Eigenes Bundesland durch blauen Rahmen hervorgehoben
  - Hover-Tooltip mit allen Performance-Details je Bundesland

- **Performance-Metriken im Regionalen Vergleich**
  - Tabelle und Tooltip zeigen jetzt messbare Leistungsdaten statt Ausstattungsquoten
  - 🔋 Speicher: Ø Ladung ↑ / Entladung ↓ kWh pro Monat (getrennt)
  - ♨️ Ø berechnete JAZ (Σ Wärme ÷ Σ Strom, saisonaler Wert)
  - 🚗 Ø km/Monat + Ø kWh zuhause geladen (gesamt − extern)
  - 🔌 Ø kWh/Monat + Ø PV-Anteil in % (wo von Wallbox messbar)
  - 🪟 Ø BKW-Ertrag kWh/Monat

- **Community Server: Regionale Performance-Aggregate**
  - `/api/statistics/regional` liefert jetzt Performance-Durchschnitte pro Bundesland
  - Alle Metriken nur über Anlagen mit dem jeweiligen Gerät und validen Messwerten

### Technisch

- TypeScript Import-Casing-Fix (macOS case-insensitive Filesystem)
- `.nvmrc` mit Node 20 (passend zu Docker `node:20-alpine`)
- Lokale Entwicklungsumgebung: Python 3.11 venv, VS Code tasks.json/launch.json
- Lokale Testdatenbank unter `eedc/data/eedc.db`

---

## [2.1.0] - 2026-02-21

### Hinzugefügt

- **Community als eigenständiger Hauptmenüpunkt**
  - Community jetzt auf Augenhöhe mit Cockpit, Auswertungen und Aussichten
  - Eigener Navigationsbereich statt Tab in Auswertungen
  - 6-Tab-Struktur: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken

- **Übersicht Tab**
  - **Gamification:** 7 Achievements (Autarkiemeister, Effizienzwunder, Solarprofi, Grüner Fahrer, Wärmekönig, Ertragswunder, Speichermeister)
  - **Fortschrittsanzeige** für nicht erreichte Achievements
  - **Radar-Chart:** Eigene Performance vs. Community auf 6 Achsen
  - **Rang-Badges:** Top 10%, Top 25%, Top 50%
  - **KPI-Tooltips:** Erklärungen für Community-Kennzahlen (Spez. Ertrag, JAZ, etc.)

- **PV-Ertrag Tab**
  - **Perzentil-Anzeige:** "Du bist besser als X% der Community"
  - **Abweichungs-KPIs:** vs. Community und vs. Region
  - **Monatlicher Ertrag Chart:** Mit echten monatlichen Community-Durchschnitten (statt Jahresdurchschnitt/12)
  - **Jahresübersicht:** Tabelle mit Abweichungen pro Jahr
  - **Verteilungs-Histogramm:** Eigene Position in der Community-Verteilung

- **Komponenten Tab**
  - **Speicher Deep-Dive:** Wirkungsgrad, Zyklen, PV-Anteil mit Community-Vergleich
  - **Wärmepumpe Deep-Dive:** JAZ-Vergleich nach Region, mit Hinweis bei weniger als 3 Anlagen
  - **E-Auto Deep-Dive:** PV-Anteil, Ladequellen-Chart (PV/Netz/Extern)
  - **Wallbox Deep-Dive:** Ladung und PV-Anteil
  - **Balkonkraftwerk Deep-Dive:** Spezifischer Ertrag und Eigenverbrauchsquote
  - **Zeitraum-Hinweis:** Betrachtungszeitraum wird konsistent angezeigt

- **Regional Tab**
  - **Regionale Position:** Rang im Bundesland
  - **Vergleichs-Chart:** Du / Region / Community als Balken
  - **Regionale Einordnung:** Anlagen-Details im Kontext

- **Trends Tab**
  - **Ertragsverlauf:** Area-Chart über alle Monate
  - **Saisonale Performance:** Frühling/Sommer/Herbst/Winter mit Icons
  - **Jahresvergleich:** Letztes vs. Vorletztes Jahr mit Veränderung
  - **Typischer Monatsverlauf:** Durchschnitt pro Monat über alle Jahre
  - **Community-Entwicklung:** Speicher-/WP-/E-Auto-Quoten über Zeit
  - **Degradations-Analyse:** Ertrag nach Anlagenalter

- **Statistiken Tab**
  - **Community-Zusammenfassung:** Übersicht über alle Teilnehmer
  - **Position in Community:** Rang und Perzentil
  - **Ausstattungs-Übersicht:** Komponenten-Verteilung

- **Backend-Erweiterungen**
  - **Proxy-Endpoints:** Alle Community-Server-Endpoints durchgereicht
  - `/api/community/statistics/global` - Globale Statistiken
  - `/api/community/statistics/monthly-averages` - Monatliche Durchschnitte
  - `/api/community/statistics/regional` - Regionale Statistiken
  - `/api/community/statistics/distributions/{metric}` - Verteilungsdaten
  - `/api/community/statistics/rankings/{category}` - Top-Listen
  - `/api/community/components/*` - Komponenten-Statistiken
  - `/api/community/trends/*` - Trend-Daten und Degradation

### Behoben

- **FastAPI Route-Ordering:** `/api/community/trends/degradation` wurde fälschlich von `/api/community/trends/{period}` gematcht
- **TypeScript-Typen:** Server-Feldnamen (`durchschnitt_zyklen` statt `avg_zyklen`) korrekt gemappt
- **Chronologische Sortierung:** Monatsdaten in PV-Ertrag und Trends Charts werden jetzt korrekt sortiert (älteste links, neueste rechts)
- **Monatliche Durchschnitte:** Community-Vergleich verwendet echte monatliche Werte statt Jahresdurchschnitt/12

### Geändert

- **Auswertungen:** Community-Tab entfernt (jetzt eigenständiger Menüpunkt)
- **Navigation:** Hauptmenü erweitert um Community-Eintrag
- **Tooltips:** Aussichten-Tabs und Community-Seite haben jetzt erklärende Tooltips

---

## [2.0.3] - 2026-02-20

### Hinzugefügt

- **Community-Vergleich Tab in Auswertungen**
  - Neuer "Community" Tab erscheint nach Teilen der Anlagendaten
  - Zeitraum-Auswahl: Letzter Monat, Letzte 12 Monate, Letztes vollständiges Jahr, Seit Installation
  - **PV-Benchmark:** Spezifischer Ertrag im Vergleich zu Community und Region
  - **Rang-Anzeige:** Position gesamt und regional
  - **Komponenten-Benchmarks:** Speicher (Zyklen, Wirkungsgrad), Wärmepumpe (JAZ), E-Auto (PV-Anteil)
  - **Monatlicher Ertrag Chart:** Visualisierung der letzten 12 Monate
  - **Zugangslogik:** Tab nur sichtbar wenn `community_hash` gesetzt (Daten geteilt)

- **Backend: Community-Benchmark Proxy**
  - Neuer Endpoint `GET /api/community/benchmark/{anlage_id}`
  - Proxy zum Community-Server (`/api/benchmark/anlage/{anlage_hash}`)
  - Gibt 403 zurück wenn Anlage nicht geteilt (Fairness-Prinzip: Erst teilen, dann vergleichen)
  - Unterstützt Zeitraum-Filter: `letzter_monat`, `letzte_12_monate`, `letztes_vollstaendiges_jahr`, `jahr`, `seit_installation`

### Geändert

- **Community-Seite (energy.raunet.eu) vereinfacht**
  - Entfernt: Zeitraum-Auswahl (immer Jahresertrag)
  - Entfernt: Komponenten-Benchmarks (jetzt im Add-on)
  - Hinzugefügt: Hinweis-Box mit Verweis auf EEDC Add-on für Details
  - Titel geändert: "Dein Anlagen-Benchmark" (statt "Dein PV-Anlagen Benchmark")

- **Frontend-Types erweitert**
  - `community_hash` Feld zum `Anlage` Interface hinzugefügt
  - Erweiterte TypeScript-Interfaces für Benchmark-Daten

---

## [2.0.2] - 2026-02-19

### Hinzugefügt

- **CSV-Import: Automatische Legacy-Migration**
  - Alte CSV-Dateien mit `PV_Erzeugung_kWh`, `Batterie_Ladung_kWh`, `Batterie_Entladung_kWh` werden automatisch migriert
  - PV-Erzeugung wird proportional nach kWp auf alle PV-Module verteilt
  - Batterie-Werte werden proportional nach Kapazität auf alle Speicher verteilt
  - Warnung wird angezeigt, wenn Legacy-Werte migriert wurden
  - Behebt Import-Fehler bei älteren Backup-Dateien

### Behoben

- **Auswertung/Energie KPIs zeigten falsche Werte**
  - Problem: PV-Erzeugung zeigte 0.3 MWh statt tatsächlicher Werte
  - Ursache: `useMonatsdatenStats` verwendete Legacy-Feld `Monatsdaten.pv_erzeugung_kwh`
  - Fix: Neue Hooks `useAggregierteDaten` und `useAggregierteStats` nutzen aggregierte Daten aus `InvestitionMonatsdaten`
  - Betroffen: Alle KPIs in Auswertung → Energie Tab

- **PrognoseVsIst nutzte Legacy-Felder**
  - Fix: Verwendet jetzt `/api/monatsdaten/aggregiert` Endpoint
  - Korrekte PV-Erzeugungswerte für SOLL-IST Vergleich

- **Swagger UI "Try it out" funktioniert jetzt im HA Ingress**
  - Problem: 404-Fehler beim Testen von API-Endpoints in Swagger UI
  - Ursache: Swagger verwendete falsche Base-URL im Ingress-Proxy
  - Fix: Dynamische Base-URL-Berechnung aus aktueller Browser-URL

---

## [2.0.1] - 2026-02-19

### Hinzugefügt

- **Selektiver Feld-Import im HA-Statistik Wizard**
  - **Import-Modi:** Schnellauswahl zwischen "Alles importieren", "Nur Basis" (Einspeisung/Netzbezug), "Nur Komponenten"
  - **Granulare Feld-Checkboxen:** Jedes Feld kann einzeln an-/abgewählt werden
  - Modus wechselt automatisch zu "Manuell" bei individueller Anpassung
  - Ermöglicht z.B. manuell korrigierte Einspeisung beizubehalten, aber PV-Werte zu importieren

- **Komponenten-Vergleich im HA-Statistik Import Wizard**
  - Zeigt nun alle InvestitionMonatsdaten (PV, Speicher, E-Auto, etc.) im Vergleich
  - Vorhanden vs. HA-Statistik mit Differenz-Berechnung
  - Gelbe Hervorhebung bei Abweichungen ≥1
  - Konflikt-Erkennung berücksichtigt jetzt auch Komponenten-Werte

- **Erweiterte Sensor-Mapping Felder**
  - **E-Auto:** Verbrauch gesamt (kWh), Ladung extern (kWh)
  - **Wallbox:** Ladevorgänge (Anzahl)
  - **Balkonkraftwerk:** Neuer Wizard-Step mit PV-Erzeugung, Eigenverbrauch, Speicher-Ladung/-Entladung

### Behoben

- **Sensor-Filter erlaubt Zähler ohne Einheit** - Sensoren wie `evcc_charging_sessions` mit `state_class: measurement` aber ohne `unit_of_measurement` werden jetzt korrekt angezeigt

---

## [2.0.0] - 2026-02-18

### ⚠️ BREAKING CHANGE - Neuinstallation erforderlich!

Diese Version benötigt **Lesezugriff auf `/config`** für die HA-Statistik-Funktion.
Das Volume-Mapping wurde geändert - eine einfache Aktualisierung reicht nicht!

**Vor dem Update:**
1. **JSON-Export** aller Anlagen erstellen (Anlagen-Seite → Download-Icon ⬇️ bei jeder Anlage)
2. Export-Datei sichern!

**Update durchführen:**
1. Add-on **stoppen**
2. Add-on **deinstallieren** (⚠️ Daten werden gelöscht!)
3. Repository aktualisieren (Add-ons → ⋮ → Nach Updates suchen)
4. Add-on **neu installieren**
5. Add-on **starten**
6. **JSON-Import** durchführen

### Hinzugefügt

- **HA-Statistik-Abfrage** - Direkte Abfrage der Home Assistant Langzeitstatistiken
  - Neuer Service `ha_statistics_service.py` für SQLite-Zugriff auf `/config/home-assistant_v2.db`
  - API-Endpoints unter `/api/ha-statistics/`:
    - `GET /status` - Prüft ob HA-Datenbank verfügbar ist
    - `GET /monatswerte/{anlage_id}/{jahr}/{monat}` - Monatswerte für einen Monat
    - `GET /verfuegbare-monate/{anlage_id}` - Alle Monate mit Daten
    - `GET /alle-monatswerte/{anlage_id}` - Bulk-Abfrage aller historischen Monatswerte
    - `GET /monatsanfang/{anlage_id}/{jahr}/{monat}` - Zählerstände für MQTT-Startwerte
  - Nutzt die sensor_mapping Zuordnungen um HA-Sensoren auf EEDC-Felder zu mappen
  - Ermöglicht rückwirkende Befüllung aller Monatsdaten seit Installationsdatum

- **HA-Statistik Import mit Überschreib-Schutz**
  - `GET /api/ha-statistics/import-vorschau/{anlage_id}` - Vorschau mit Konflikt-Erkennung
  - `POST /api/ha-statistics/import/{anlage_id}` - Import mit intelligenter Logik:
    - Neue Monate werden importiert
    - Leere Monatsdaten werden befüllt
    - Vorhandene Daten werden **nicht** überschrieben (außer explizit gewünscht)
    - Konflikte werden erkannt und angezeigt

- **Frontend: HA-Statistik Import UI**
  - Neue Seite: Einstellungen → Home Assistant → Statistik-Import
  - Bulk-Import aller historischen Monatswerte
  - Vorschau mit farbcodierter Konflikt-Erkennung
  - Option zum Überschreiben vorhandener Daten

- **Monatsabschluss-Wizard: HA-Werte laden**
  - Neuer Button "Werte aus HA-Statistik laden"
  - Lädt Monatswerte direkt aus der HA-Langzeitstatistik
  - Nur sichtbar wenn Sensor-Mapping konfiguriert ist

- **Sensor-Mapping: Startwerte aus HA-DB**
  - Nach Speichern: Option "Aus HA-Statistik laden (empfohlen)"
  - Verwendet gespeicherte Zählerstände vom Monatsanfang
  - Fallback: Aktuelle Sensorwerte verwenden

### Geändert

- **Volume-Mapping erweitert**: `config:ro` für Lesezugriff auf HA-Datenbank

### Behoben

- **Sensor-Mapping UI** - Importierte Sensoren werden jetzt angezeigt auch wenn HA nicht verfügbar
  - Zeigt sensor_id mit Hinweis "(nicht verfügbar)" wenn Sensor nicht in lokaler Liste

- **PVGIS MultipleResultsFound** - 500-Fehler wenn mehrere aktive PVGIS-Prognosen existierten
  - Query mit `.order_by().limit(1)` abgesichert in pvgis.py, cockpit.py, aussichten.py, solar_prognose.py

- **SensorMappingWizard Startwerte laden** - "Cannot convert undefined or null to object" Fehler
  - Interface-Feldnamen korrigiert (`startwerte` statt `werte`) und Null-Safety hinzugefügt

- **HAStatistikImport "NaN Monate importieren"** - Frontend-Interface an Backend-Feldnamen angepasst
  - `anzahl_monate`, `anzahl_importieren`, `anzahl_konflikte`, `anzahl_ueberspringen` korrekt gemappt

- **HAStatistikImport: Individuelle Monatsauswahl** - Checkbox pro Monat statt globaler Überschreiben-Option
  - Benutzer können gezielt einzelne Monate zum Import auswählen

- **Monatsdaten: "Aus HA laden" Button** - Direktes Laden einzelner Monate aus HA-Statistik
  - Modal zur Auswahl von Monat/Jahr aus verfügbaren HA-Statistik-Monaten
  - Bei existierenden Monaten: Vergleichs-Modal mit Diff-Anzeige vor dem Überschreiben
  - Farbcodierte Hervorhebung signifikanter Unterschiede (>10%)

- **HA-Statistik Investitions-Bezeichnungen** - Zeigt nun "BYD HVS 12.8 (speicher)" statt "()"
  - Backend lädt Investitions-Metadaten aus DB für korrektes Label

- **JSON-Import sensor_mapping** - Investitions-Mappings werden beim Import zurückgesetzt
  - IDs ändern sich beim Import, daher muss Sensor-Mapping neu konfiguriert werden
  - Warnung wird angezeigt mit Hinweis auf Neukonfiguration

- **Sensor-Mapping Wizard: Löschen-Button** - Mapping kann nun über Button im Header gelöscht werden
  - Bestätigungsdialog vor dem Löschen

- **Komponenten-Vergleich in "Aus HA laden"** - Zeigt nun Vorhanden vs. HA-Statistik Tabelle für alle Investitionen
  - Differenz-Berechnung wie bei Basis-Werten (Einspeisung, Netzbezug)
  - Zeigt auch Investitionen die nur in Bestandsdaten existieren (ohne HA-Mapping)

---

## [1.1.0-beta.8] - 2026-02-18

(Übersprungen - direkt zu 2.0.0 wegen Breaking Change)

---

## [1.1.0-beta.7] - 2026-02-18

### Behoben

- **JSON-Export Version 1.1 Bug** - Export-Version war fälschlicherweise auf "1.0" hardcoded
  - In beta.5 wurde das Pydantic-Model auf 1.1 aktualisiert, aber der Code der das Export-Objekt erstellt übergab explizit "1.0"
  - Dadurch wurde beim Import die Warnung "sensor_mapping nicht enthalten" angezeigt, obwohl es vorhanden war
  - Export gibt jetzt korrekt `export_version: "1.1"` aus

---

## [1.1.0-beta.6] - 2026-02-18

### Geändert

- **Cockpit PV-Anlage komplett überarbeitet** - zeigt jetzt Gesamtlaufzeit statt einzelne Jahre
  - Neuer API-Endpoint `/api/cockpit/pv-strings-gesamtlaufzeit` für aggregierte Daten
  - **SOLL vs IST pro Jahr**: Balkendiagramm zeigt für jedes Jahr SOLL und IST pro String
  - **Saisonaler Vergleich**: Jan-Dez Durchschnitt vs PVGIS-Prognose als Linien/Flächen-Chart
  - **Gesamtlaufzeit-Tabelle**: Performance-Statistik pro String über alle Jahre
  - Keine Jahr-Auswahl mehr nötig - konsistent mit Cockpit-Philosophie "Gesamtlaufzeit"

### Behoben

- **Dashboard Race Condition** - "Fehler beim Laden der Daten" erschien manchmal nach F5
  - `loading` State wird jetzt mit `true` initialisiert
  - Cockpit-Tabs sind wieder statisch (dynamische Tabs verursachten Race Conditions)

---

## [1.1.0-beta.5] - 2026-02-18

### Hinzugefügt

- **JSON-Export erweitert für vollständiges Backup/Restore** (Export-Version 1.1)
  - `sensor_mapping` - HA Sensor-Zuordnungen werden jetzt exportiert/importiert
  - `durchschnittstemperatur` - Wetterdaten in Monatsdaten
  - `sonderkosten_euro` / `sonderkosten_beschreibung` - Manuelle Sonderkosten
  - Rückwärtskompatibel: Export-Version 1.0 wird weiterhin importiert

### Geändert

- **Monatsdaten-Formular verbessert:**
  - PV-Erzeugung ist jetzt readonly wenn PV-Module mit Werten vorhanden sind (Summe wird automatisch berechnet)
  - Sonnenstunden akzeptiert jetzt Dezimalwerte (step=0.1 statt step=1) - behebt Validierungsfehler bei Auto-Fill

### Hinweis

Beim Import von Anlagen mit Sensor-Mapping:
- Die Zuordnungen werden übernommen, aber `mqtt_setup_complete` wird auf `false` gesetzt
- Nach dem Import muss das Sensor-Mapping erneut gespeichert werden, um die MQTT-Entities zu erstellen
- Grund: Die Investitions-IDs ändern sich beim Import

---

## [1.1.0-beta.4] - 2026-02-18

### Behoben

- **MQTT Entity-IDs** sind jetzt eindeutig durch `object_id` im Discovery-Payload
  - Entity-IDs enthalten jetzt den Key: `number.eedc_winterborn_mwd_inv1_ladung_kwh_start`
  - Vorher wurde die Entity-ID aus dem Namen generiert, was zu `_2` Suffixen führte
  - Friendly Names bleiben lesbar mit Investitionsnamen

### Hinweis

Nach dem Update: MQTT Discovery Topics löschen (`homeassistant/number/eedc_*` und
`homeassistant/sensor/eedc_*`), dann Sensor-Mapping erneut speichern.

---

## [1.1.0-beta.3] - 2026-02-18

### Behoben

- **MQTT Entity-Namen** enthalten jetzt den Investitionsnamen
  - Vorher: Doppelte Entities wenn Speicher und Wallbox beide `ladung_kwh` haben
  - Jetzt: "EEDC BYD HVS 12.8 Ladung Monatsanfang" statt "EEDC Speicher Ladung Monatsanfang"
  - Eindeutige Namen für jede Investition, keine `_2` Suffixe mehr in HA

### Hinweis

Nach dem Update: EEDC-Gerät in Home Assistant löschen und Sensor-Mapping erneut speichern,
damit die neuen Entity-Namen erstellt werden.

---

## [1.1.0-beta.2] - 2026-02-17

### Behoben

- **Datenbank-Migration** für neue Monatsdaten-Felder hinzugefügt
  - `durchschnittstemperatur` (FLOAT)
  - `sonderkosten_euro` (FLOAT)
  - `sonderkosten_beschreibung` (VARCHAR)
  - `notizen` (VARCHAR)
  - Behebt SQLite-Fehler "no such column: monatsdaten.durchschnittstemperatur" nach Update

---

## [1.1.0-beta.1] - 2026-02-17

### Hinzugefügt

- **Sensor-Mapping-Wizard** - Zuordnung von Home Assistant Sensoren zu EEDC-Feldern
  - Intuitive Wizard-Oberfläche mit dynamischen Steps
  - Unterstützte Schätzungsstrategien:
    - **sensor** - Direkter HA-Sensor
    - **kwp_verteilung** - Anteilig nach kWp (für PV-Module ohne eigenen Sensor)
    - **cop_berechnung** - COP × Stromverbrauch (für Wärmepumpen)
    - **ev_quote** - Nach Eigenverbrauchsquote (für E-Auto)
    - **manuell** - Eingabe im Monatsabschluss-Wizard
  - Speicherung in neuem `Anlage.sensor_mapping` JSON-Feld
  - Navigation: Einstellungen → Home Assistant → Sensor-Zuordnung

- **MQTT Auto-Discovery für Monatswerte**
  - EEDC erstellt automatisch MQTT-Entities in Home Assistant:
    - `number.eedc_{anlage}_mwd_{feld}_start` - Zählerstand vom Monatsanfang
    - `sensor.eedc_{anlage}_mwd_{feld}_monat` - Berechneter Monatswert via `value_template`
  - Keine YAML-Bearbeitung oder HA-Neustart nötig
  - Retained Messages für Persistenz

- **Monatsabschluss-Wizard** - Geführte monatliche Dateneingabe
  - **Intelligente Vorschläge** aus verschiedenen Quellen:
    - Vormonat (80% Konfidenz)
    - Vorjahr gleicher Monat (70% Konfidenz)
    - COP-Berechnung für Wärmepumpen (60% Konfidenz)
    - Durchschnitt letzte 12 Monate (50% Konfidenz)
  - **Plausibilitätsprüfungen** mit Warnungen:
    - Negativwerte bei Zählern
    - Große Abweichungen vs. Vorjahr (±50%)
    - Ungewöhnlich niedrige/hohe Werte
  - Dynamische Steps basierend auf Investitionstypen
  - Navigation: Einstellungen → Daten → Monatsabschluss

- **Scheduler für Cron-Jobs**
  - APScheduler-Integration für periodische Tasks
  - Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
  - Status-Endpoint: `GET /api/scheduler`
  - Manueller Trigger: `POST /api/scheduler/monthly-snapshot`

- **Neue API-Endpoints**
  - `/api/sensor-mapping/{anlage_id}` - CRUD für Sensor-Zuordnung
  - `/api/sensor-mapping/{anlage_id}/available-sensors` - Verfügbare HA-Sensoren
  - `/api/monatsabschluss/{anlage_id}/{jahr}/{monat}` - Status und Vorschläge
  - `/api/monatsabschluss/naechster/{anlage_id}` - Nächster offener Monat
  - `/api/scheduler` - Scheduler-Status

- **Neue Backend-Services**
  - `ha_mqtt_sync.py` - MQTT Synchronisations-Service
  - `scheduler.py` - Cron-Job Management
  - `vorschlag_service.py` - Intelligente Vorschläge

### Geändert

- **mqtt_client.py** erweitert um:
  - `publish_number_discovery()` - Erstellt number-Entities
  - `publish_calculated_sensor()` - Erstellt Sensoren mit value_template
  - `update_month_start_value()` - Aktualisiert Monatsanfang-Werte
  - `publish_monatsdaten()` - Publiziert finale Monatsdaten

- **Navigation** erweitert:
  - "Sensor-Zuordnung" unter Einstellungen → Home Assistant
  - "Monatsabschluss" unter Einstellungen → Daten

### Technisch

- **Neue Dependency:** `apscheduler>=3.10.0` für Cron-Jobs
- **DB-Migration:** Neue Spalte `sensor_mapping` (JSON) in `anlagen` Tabelle
- Scheduler startet automatisch mit dem Backend

---

## [1.0.0-beta.13] - 2026-02-17

### Hinzugefügt

- **Logo/Icon Integration**
  - Neues eedc-Logo und Icon durchgängig eingebunden
  - **HA Add-on:** `icon.png` (512x512) und `logo.png` für Add-on Store
  - **Frontend:** Neues Favicon, Icon + "eedc" Text in TopNavigation
  - **Setup-Wizard:** eedc-Icon im Header
  - **PDF-Export:** eedc-Icon in der Kopfzeile (ab Seite 2)
  - **README:** Logo zentriert am Anfang

- **Entwickler-Tools**
  - `scripts/kill-dev.sh`: Beendet alle Entwicklungs-Prozesse und gibt Ports frei
  - Prüft Ports 8099 (Backend), 5173-5176 (Frontend), 3000-3009 (Tests)

### Geändert

- **HA-Integration Bereinigung (Phase 0)**
  - `ha_integration.py`: Von 2037 auf 171 LOC reduziert (-92%)
  - Auto-Discovery komplett entfernt (ineffektiv, ~10% Erkennungsrate)
  - Discovery-UI Komponenten entfernt
  - `ha_sensor_*` Felder auf Anlage als DEPRECATED markiert

- **PDF-Export**
  - HA-Integration Abschnitt wird nur angezeigt wenn Sensoren konfiguriert sind
  - Icon statt Text "eedc" in Kopfzeile

- **Demo-Daten**
  - `ha_sensor_*` Beispielwerte entfernt (waren irreführend)

### Entfernt

- **Backend Services**
  - `ha_yaml_generator.py` (18 LOC Placeholder)
  - `ha_websocket.py` (261 LOC, unzuverlässig)

- **Backend Models**
  - `StringMonatsdaten` (redundant mit `InvestitionMonatsdaten.verbrauch_daten`)

- **Frontend Komponenten**
  - `components/discovery/*` (DeviceCard, DiscoveryDialog, SensorMappingPanel, etc.)
  - `hooks/useDiscovery.ts`
  - `setup-wizard/steps/DiscoveryStep.tsx`
  - `setup-wizard/steps/SensorConfigStep.tsx`

- **API Endpoints (aus ha_integration.py)**
  - `/ha/discover` - Auto-Discovery
  - `/ha/statistics/*` - Long-Term Statistics
  - `/ha/string-monatsdaten/*` - StringMonatsdaten CRUD
  - Diverse Discovery-bezogene Endpoints

---

## [1.0.0-beta.12] - 2026-02-16

### Hinzugefügt

- **PDF-Export: Vollständige Anlagen-Dokumentation**
  - Neuer PDF-Export-Button auf der Anlagen-Seite (orangefarbenes Dokument-Icon)
  - **Gesamtzeitraum als Standard:** Ohne Jahr-Parameter werden alle Jahre exportiert
  - **Vollständige Stammdaten:** Alle Komponenten mit Hersteller, Modell, Seriennummer, Garantie
  - **Ansprechpartner & Wartung:** Service-Kontakte und Wartungsverträge pro Komponente
  - **Versorger-Daten:** Stromversorger, Kundennummern, Zähler mit Zählpunkten
  - **Home Assistant Sensoren:** Konfigurierte Sensor-Mappings

- **PDF-Layout & Design**
  - **Kopfzeile (ab Seite 2):** Anlagenname | "EEDC Anlagenbericht [Zeitraum]" | eedc-Logo
  - **Fußzeile (alle Seiten):** Erstellungsdatum | GitHub-Repository | "Seite X von Y"
  - **Farbschema:** Darkblue-Hintergrund für Kapitel, Orangered für Unterüberschriften
  - **Wiederholende Tabellenköpfe:** Bei Seitenumbrüchen werden Spaltenüberschriften wiederholt

- **PDF-Inhalte**
  - Jahresübersicht mit allen KPIs (Energie, Autarkie, Finanzen, CO2)
  - Drei Diagramme: PV-Erzeugung (Balken + PVGIS-Linie), Energie-Fluss (gestapelt), Autarkie-Verlauf
  - Monatstabellen: Energie, Speicher, Wärmepumpe, E-Mobilität, Finanzen
  - PV-String Vergleich: SOLL (PVGIS) vs. IST mit Abweichung
  - Finanz-Prognose & Amortisations-Fortschritt

- **Erweiterte Demo-Daten**
  - Alle Investitionen mit vollständigen Stammdaten (Hersteller, Seriennummer, Garantie)
  - Ansprechpartner für Wechselrichter, E-Auto, Wärmepumpe
  - Wartungsverträge für Wechselrichter und Wärmepumpe
  - Versorger-Daten mit Zählernummern und Zählpunkten
  - Home Assistant Sensor-Mappings

### Geändert

- **PDF-Button verschoben:** Von Auswertung zu Anlagen-Seite (bei Stammdaten)
- **API-Endpoint `/api/import/pdf/{anlage_id}`:** `jahr`-Parameter ist jetzt optional

---

## [1.0.0-beta.11] - 2026-02-16

### Hinzugefügt

- **Setup-Wizard komplett überarbeitet**
  - Standalone-First: Alle Home Assistant Abhängigkeiten entfernt
  - Neuer 4-Schritte-Flow: Anlage → Strompreise → Komponenten → Zusammenfassung
  - **PVGIS-Integration:** Prognose direkt im Wizard abrufbar
  - **Direkte Navigation:** Nach Abschluss zur Monatsdaten-Erfassung statt Cockpit
  - Komponenten können nach PV-System-Erstellung weiter hinzugefügt werden

- **Erweiterte Komponenten-Felder im Wizard**
  - **Speicher:** Arbitrage-Checkbox (Netzstrom günstig laden, teuer einspeisen)
  - **E-Auto:** V2H-fähig Checkbox (Vehicle-to-Home)
  - **Wallbox:** V2H-fähig Checkbox (Bidirektionales Laden)
  - **Balkonkraftwerk:** Ausrichtung, Neigung, Mit Speicher (z.B. Anker SOLIX)
  - Alle technischen Felder als Pflichtfelder markiert

- **Schnellstart-Buttons für Komponenten**
  - Nach PV-System-Erstellung: Speicher, Wallbox, Wärmepumpe, E-Auto, Balkonkraftwerk
  - Bereits vorhandene Typen werden grün mit ✓ markiert
  - "Investition hinzufügen"-Dropdown für alle Typen weiterhin verfügbar

### Geändert

- **AnlageStep vereinfacht**
  - Entfernt: "Technische Daten (optional)" mit Ausrichtung/Neigung (jetzt in PV-Modulen)
  - Entfernt: "Wechselrichter-Hersteller" mit veraltetem HA-Hinweis
  - Fokus auf Grunddaten: Name, Leistung, Datum, Standort

- **SummaryStep verbessert**
  - PVGIS-Prognose Card mit Button zum Abrufen
  - Zeigt Jahresertrag wenn PVGIS abgerufen
  - "Wie geht es weiter?" Sektion mit Monatsdaten-Hinweis
  - CTA "Weiter zur Datenerfassung" statt "Einrichtung abschließen"

- **CompleteStep aktualisiert**
  - Hauptbutton "Monatsdaten erfassen" → navigiert zu /einstellungen/monatsdaten
  - Sekundärbutton "Zum Cockpit" für alternative Navigation

### Entfernt

- **Home Assistant Integration aus Setup-Wizard**
  - HAConnectionStep entfernt
  - DiscoveryStep entfernt
  - Automatische Sensor-Erkennung entfernt
  - Keine HA-Referenzen mehr in WelcomeStep

---

## [1.0.0-beta.10] - 2026-02-15

### Hinzugefügt

- **Multi-Provider Wetterdienst-Integration**
  - **Bright Sky (DWD):** Hochwertige Wetterdaten für Deutschland via DWD Open Data
  - **Open-Meteo:** Historische und Forecast-Daten weltweit
  - **Open-Meteo Solar:** GTI-basierte Berechnung für geneigte PV-Module
  - Automatische Provider-Auswahl: Bright Sky für DE, Open-Meteo sonst
  - Fallback-Kette bei Nichtverfügbarkeit → PVGIS TMY → Statische Defaults

- **GTI-basierte Solarprognose**
  - Global Tilted Irradiance (GTI) statt horizontaler Globalstrahlung
  - Berücksichtigt Neigung und Ausrichtung der PV-Module
  - Temperaturkorrektur für Wirkungsgradminderung bei Hitze
  - 7-Tage Prognose mit stündlichen/täglichen Werten pro PV-String

- **SCOP-Modus für Wärmepumpe**
  - Neuer dritter Effizienz-Modus neben JAZ und COP
  - EU-Energielabel SCOP-Werte (realistischer als Hersteller-COP)
  - Separate Eingabe für Heiz-SCOP und Warmwasser-SCOP
  - Vorlauftemperatur-Auswahl (35°C/55°C) passend zum EU-Label

- **Kurzfrist-Tab erweitert**
  - Umschalter zwischen Standard-Prognose und GTI-basierter Solarprognose
  - Visualisierung der erwarteten PV-Erträge pro String
  - Integration mit Open-Meteo Solar Forecast API

### Geändert

- **Einstellungen: PVGIS → Solarprognose**
  - Menüpunkt umbenannt von "PVGIS" zu "Solarprognose"
  - Zeigt verfügbare Wetter-Provider und deren Status
  - Kombiniert PVGIS-Langfristprognose mit Wetter-Provider-Info
  - Redirect von `/einstellungen/pvgis` zu `/einstellungen/solarprognose`

- **Demo-Daten aktualisiert**
  - Standort von Wien auf München geändert (für Bright Sky/DWD-Verfügbarkeit)
  - PV-Module mit GTI-Parametern (ausrichtung_grad, neigung_grad)
  - Balkonkraftwerk mit GTI-kompatiblen Parametern

- **API: Wetter-Endpoints erweitert**
  - `GET /api/wetter/provider/{anlage_id}` - Verfügbare Provider mit Status
  - `GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}` - Provider-Vergleich
  - `GET /api/solar-prognose/{anlage_id}` - GTI-basierte PV-Prognose

### Bugfixes

- **GTI-Berechnung korrigiert**
  - Problem: Unrealistische Werte (z.B. 8845 kWh/Tag für 20 kWp)
  - Ursache: Fehlerhafte Einheitenumrechnung Wh→kWh
  - Fix: Korrekte Division durch 1000 in allen Berechnungspfaden

- **wetter_provider in Export/Import**
  - Feld wird jetzt korrekt im JSON-Export mitgeliefert
  - Import setzt Provider-Einstellung der Anlage

- **Bewölkungswerte in Kurzfrist-Prognose**
  - Problem: Spalte "Bewölkung" zeigte nur "- %" statt Werte
  - Ursache: Stündliche cloud_cover-Daten wurden nicht aggregiert
  - Fix: Tagesdurchschnitt aus stündlichen Werten berechnet

- **Standort-Info auf Solarprognose-Seite**
  - Problem: "Standort: Unbekannt" obwohl Koordinaten vorhanden
  - Fix: land/in_deutschland Felder zur StandortInfo hinzugefügt

- **SOLL-IST Vergleich bei mehreren PVGIS-Prognosen**
  - Problem: 500-Fehler wenn mehrere Prognosen für eine Anlage existieren
  - Ursache: `scalar_one_or_none()` bei mehreren Ergebnissen
  - Fix: `.limit(1)` um nur die neueste Prognose zu verwenden

---

## [1.0.0-beta.9] - 2026-02-14

### Hinzugefügt

- **Icons im Hauptmenü**
  - Cockpit, Auswertungen und Aussichten zeigen jetzt passende Icons
  - LayoutDashboard für Cockpit, BarChart3 für Auswertungen, TrendingUp für Aussichten

- **JSON-Import-Vorbereitung**
  - Import-Modul refaktoriert für JSON-Import (lokale Variante)

### Geändert

- **Import/Export-Modul refaktoriert**
  - Aufgeteilt von einer großen Datei (2500+ Zeilen) in modulares Package
  - Neue Struktur: `import_export/` mit separaten Dateien für CSV, JSON, Demo-Daten
  - Bessere Wartbarkeit und Testbarkeit

### Bugfixes

- **Garantiedatum wurde nicht gespeichert**
  - Problem: Datumsfelder wie `stamm_garantie_bis` wurden durch `parseFloat()` in Zahlen konvertiert
  - Lösung: Datumsfelder werden jetzt explizit als Strings behandelt
  - Betrifft: `stamm_garantie_bis`, `wartung_gueltig_bis`, `stamm_erstzulassung`, etc.

- **JSON-Export 404 in Home Assistant**
  - Problem: Download-Button verwendete absoluten Pfad `/api/...` statt relativen `./api/...`
  - Im HA Ingress-Modus führte das zu 404-Fehlern
  - Lösung: Verwendung von `importApi.getFullExportUrl()` mit korrektem relativen Pfad

---

## [1.0.0-beta.8] - 2026-02-13

### Hinzugefügt

- **Vollständiger JSON-Export für Support/Backup**
  - Neuer Endpoint `GET /api/import/export/{anlage_id}/full`
  - Exportiert komplette Anlage mit allen verknüpften Daten
  - Hierarchische Struktur: Anlage → Strompreise → Investitionen (mit Children) → Monatsdaten → PVGIS
  - Download-Button in der Anlagen-Übersicht (neben Bearbeiten/Löschen)

- **CSV-Import: Erweiterte Plausibilitätsprüfungen**
  - **Legacy-Spalten-Validierung:**
    - `PV_Erzeugung_kWh`, `Batterie_Ladung_kWh`, `Batterie_Entladung_kWh` sind Legacy
    - Fehler wenn NUR Legacy-Spalte vorhanden UND PV-Module/Speicher als Investitionen existieren
    - Fehler bei Mismatch zwischen Legacy-Wert und Summe der individuellen Komponenten
    - Warnung wenn redundant (gleiche Werte ±0.5 kWh Toleranz)
  - **Negative Werte blockiert:** Alle kWh/km/€-Felder müssen ≥ 0 sein
  - **Plausibilitätswarnungen:** Sonnenstunden > 400h/Monat, Globalstrahlung > 250 kWh/m²

- **Import-Feedback verbessert**
  - Warnungen werden jetzt zusätzlich zu Fehlern angezeigt
  - Unterschiedliche Farben: Grün (Erfolg), Gelb (mit Hinweisen), Rot (mit Fehlern)
  - Hilfetext zu Legacy-Spalten im Import-Bereich

### Geändert

- **ImportResult Schema erweitert** um `warnungen: list[str]`
- **Frontend Import.tsx** zeigt Warnungen in amber/gelber Farbe

---

## [1.0.0-beta.7] - 2026-02-13

### Bugfixes

- **Kritisch: Datenbank-Migration für beta.6 Spalten fehlte**
  - Problem: Nach Update auf beta.6 fehlte die Migration für `mastr_id` und `versorger_daten`
  - Fehler: `no such column: anlagen.mastr_id` - Anlage wurde nicht mehr angezeigt
  - Fix: `run_migrations()` in `database.py` ergänzt um fehlende Spalten
  - Bestehende Daten bleiben erhalten, Spalten werden automatisch hinzugefügt

---

## [1.0.0-beta.6] - 2026-02-13

### Hinzugefügt

- **Erweiterte Stammdaten für Anlagen**
  - MaStR-ID (Marktstammdatenregister-ID) mit direktem Link zum MaStR
  - Versorger & Zähler als JSON-Struktur (Strom, Gas, Wasser)
  - Beliebig viele Zähler pro Versorger mit Bezeichnung und Nummer
  - Neue Komponente `VersorgerSection` für dynamische Verwaltung

- **Erweiterte Stammdaten für Investitionen**
  - **Gerätedaten:** Hersteller, Modell, Seriennummer, Garantie, MaStR-ID (nur WR)
  - **Ansprechpartner:** Firma, Name, Telefon, E-Mail, Ticketsystem, Kundennummer, Vertragsnummer
  - **Wartungsvertrag:** Vertragsnummer, Anbieter, Gültig bis, Kündigungsfrist, Leistungsumfang
  - Typ-spezifische Zusatzfelder (Garantie-Zyklen für Speicher, Kennzeichen für E-Auto, etc.)
  - Neue Komponente `InvestitionStammdatenSection` mit klappbaren Sektionen

- **Vererbungslogik für PV-System**
  - PV-Module und DC-Speicher erben Ansprechpartner/Wartung vom Wechselrichter
  - Hinweis "(erbt von Wechselrichter)" bei leeren Feldern
  - Nur bei Children mit `parent_investition_id` aktiv

### Geändert

- **Anlage-Datenmodell erweitert**
  - `mastr_id: Optional[str]` - MaStR-ID der Anlage
  - `versorger_daten: Optional[dict]` - JSON mit Versorgern und Zählern

- **Investition.parameter JSON erweitert**
  - Neue Felder: `stamm_*`, `ansprechpartner_*`, `wartung_*`
  - Alle Stammdaten im bestehenden `parameter` JSON gespeichert

### Dokumentation

- CHANGELOG.md: Stammdaten-Erweiterung dokumentiert
- README.md: Version aktualisiert
- CLAUDE.md: Datenstrukturen für Versorger/Investition-Stammdaten
- ARCHITEKTUR.md: JSON-Strukturen dokumentiert
- BENUTZERHANDBUCH.md: Neue Formularsektionen erklärt
- DEVELOPMENT.md: DB-Migration dokumentiert

---

## [1.0.0-beta.5] - 2026-02-13

### Hinzugefügt

- **Aussichten: 4 neue Prognose-Tabs**
  - **Kurzfristig (7 Tage)**: Wetterbasierte Ertragsschätzung mit Open-Meteo
  - **Langfristig (12 Monate)**: PVGIS-basierte Jahresprognose mit Performance-Ratio
  - **Trend-Analyse**: Jahresvergleich, saisonale Muster, Degradationsberechnung
  - **Finanzen**: Amortisations-Fortschritt, Komponenten-Beiträge, Mehrkosten-Ansatz

- **Mehrkosten-Ansatz für ROI-Berechnung**
  - Wärmepumpe: Kosten minus Gasheizung (`alternativ_kosten_euro` Parameter)
  - E-Auto: Kosten minus Verbrenner (`alternativ_kosten_euro` Parameter)
  - PV-System: Volle Kosten (keine Alternative)
  - Alternativkosten-Einsparungen als zusätzliche Erträge (WP vs. Gas, E-Auto vs. Benzin)

### Geändert

- **ROI-Metriken klarer benannt**
  - Cockpit/Auswertung: `jahres_rendite_prozent` (Jahres-Ertrag / Investition)
  - Aussichten/Finanzen: `amortisations_fortschritt_prozent` (Kum. Erträge / Investition)
  - Unterschiedliche Metriken für unterschiedliche Zwecke klar dokumentiert

- **API-Endpoints für Aussichten**
  - `GET /api/aussichten/kurzfristig/{anlage_id}` - 7-Tage Wetterprognose
  - `GET /api/aussichten/langfristig/{anlage_id}` - 12-Monats-Prognose
  - `GET /api/aussichten/trend/{anlage_id}` - Trend-Analyse
  - `GET /api/aussichten/finanzen/{anlage_id}` - Finanz-Prognose

### Dokumentation

- README.md: Aussichten-Feature dokumentiert
- CLAUDE.md: ROI-Metriken erklärt, Aussichten-Endpoints hinzugefügt
- ARCHITEKTUR.md: Aussichten-Modul dokumentiert
- BENUTZERHANDBUCH.md: Aussichten-Tabs erklärt
- DEVELOPMENT.md: Aussichten-API dokumentiert

---

## [1.0.0-beta.4] - 2026-02-12

### Hinzugefügt

- **Monatsdaten-Seite: Aggregierte Darstellung mit allen Komponenten**
  - Neuer API-Endpoint `/api/monatsdaten/aggregiert/{anlage_id}`
  - Zählerwerte (Einspeisung, Netzbezug) aus Monatsdaten
  - Komponenten-Daten (PV, Speicher, WP, E-Auto, Wallbox) aus InvestitionMonatsdaten aggregiert
  - Berechnete Felder (Direktverbrauch, Eigenverbrauch, Autarkie, EV-Quote)
  - Gruppierte Spaltenauswahl mit Ein-/Ausblenden pro Gruppe
  - Farbcodierung: Zählerwerte (blau), Komponenten (amber), Berechnungen (grün)

- **Balkonkraftwerk: Eigenverbrauch-Erfassung**
  - Neues Feld `eigenverbrauch_kwh` in InvestitionMonatsdaten
  - CSV-Template erweitert: `{BKW}_Eigenverbrauch_kWh`
  - Einspeisung wird automatisch berechnet (Erzeugung - Eigenverbrauch)
  - Dashboard zeigt Einspeisung als "unvergütet"

### Geändert

- **Demo-Daten bereinigt (Architektur-Konsistenz)**
  - `Monatsdaten.pv_erzeugung_kwh` entfernt (war Legacy)
  - `batterie_ladung_kwh`, `batterie_entladung_kwh` entfernt (Legacy)
  - Berechnete Felder entfernt (werden dynamisch berechnet)
  - **Prinzip:** Monatsdaten = NUR Zählerwerte; InvestitionMonatsdaten = ALLE Komponenten

- **BKW-Dashboard: Feldnamen-Kompatibilität**
  - Akzeptiert sowohl `pv_erzeugung_kwh` als auch `erzeugung_kwh`

### Dokumentation

- BENUTZERHANDBUCH.md: Aggregierte Monatsdaten und BKW-Eigenverbrauch dokumentiert
- ARCHITEKTUR.md: Datenstrukturen korrigiert (WP: stromverbrauch_kwh, BKW: pv_erzeugung_kwh)
- Alle Dokumente auf Version 1.0.0-beta.4 aktualisiert

---

## [1.0.0-beta.3] - 2026-02-12

### Bugfixes

- **Jahr-Filter in Auswertungen → Komponenten funktioniert jetzt**
  - Problem: Jahr-Auswahl hatte keine Auswirkung auf angezeigte Daten
  - Fix: Jahr-Parameter wird jetzt durch alle Schichten durchgereicht (Backend API → Frontend API → KomponentenTab)
  - Betroffen: `cockpit.py`, `cockpit.ts`, `KomponentenTab.tsx`, `Auswertung.tsx`

---

## [1.0.0-beta.2] - 2026-02-12

### Hinzugefügt

- **Wärmepumpe: Erweiterte Effizienz-Konfiguration**
  - Modus-Auswahl zwischen JAZ und getrennten COPs für Heizung/Warmwasser
  - JAZ (Jahresarbeitszahl): Ein Wert für alles - einfacher (Standard)
  - Getrennte COPs: Separate Werte für Heizung (~3,9) und Warmwasser (~3,0) - präziser
  - Automatische Migration: Bestehende Anlagen nutzen JAZ-Modus

### Geändert

- **ROI-Berechnung Wärmepumpe** berücksichtigt jetzt den gewählten Effizienz-Modus
- **Demo-Daten** zeigen Wärmepumpe mit getrennten COPs als Beispiel

### Dokumentation

- CLAUDE.md: WP-Datenmodell-Beispiele ergänzt
- ARCHITEKTUR.md: WP-Parameter aktualisiert
- BENUTZERHANDBUCH.md: WP-Konfiguration und CSV-Spalten dokumentiert

---

## [1.0.0-beta.1] - 2026-02-11

### Kritische Bugfixes

Diese Version behebt kritische Bugs im SOLL-IST Vergleich und der Datenpersistenz.

#### SOLL-IST Vergleich zeigte falsche Werte

**Problem:** Der SOLL-IST Vergleich im Cockpit → PV-Anlage zeigte falsche IST-Werte (z.B. 0.3 MWh statt ~14 MWh).

**Ursachen und Fixes:**

1. **Legacy-Feld entfernt** - `Monatsdaten.pv_erzeugung_kwh` wurde noch verwendet statt `InvestitionMonatsdaten.verbrauch_daten.pv_erzeugung_kwh`
   - Betroffen: `cockpit.py`, `investitionen.py`, `ha_export.py`, `main.py`

2. **SQLAlchemy flag_modified()** - JSON-Feld-Updates wurden nicht persistiert
   - SQLAlchemy erkennt Änderungen an JSON-Feldern nicht automatisch
   - Fix: `flag_modified(obj, "verbrauch_daten")` nach Änderung
   - Betroffen: `import_export.py`

3. **Jahr-Parameter fehlte** - `PVStringVergleich` erhielt kein `jahr` und verwendete 2026 statt 2025
   - Fix: `latestYear` aus Monatsdaten berechnen und übergeben
   - Betroffen: `PVAnlageDashboard.tsx`

### Geändert

- **CSV-Template bereinigt**
  - Entfernt: `PV_Erzeugung_kWh` (Legacy), `Globalstrahlung_kWh_m2`, `Sonnenstunden` (auto-generiert)
  - Import akzeptiert Legacy-Spalten weiterhin als Fallback

- **run.sh Version korrigiert** - War hardcoded auf 0.9.3

### Dokumentation

- **Vollständige Dokumentation erstellt**
  - `README.md` komplett überarbeitet für v1.0.0
  - `docs/BENUTZERHANDBUCH.md` - Umfassendes Benutzerhandbuch
  - `docs/ARCHITEKTUR.md` - Technische Architektur-Dokumentation
  - `CHANGELOG.md` - Vollständige Versionshistorie
  - `docs/DEVELOPMENT.md` - Entwickler-Setup aktualisiert

### Datenarchitektur-Klarstellung

```
Monatsdaten (Tabelle):
  - einspeisung_kwh      ✓ Primär (Zählerwert)
  - netzbezug_kwh        ✓ Primär (Zählerwert)
  - pv_erzeugung_kwh     ✗ LEGACY - nicht mehr verwenden!
  - batterie_*           ✗ LEGACY - nicht mehr verwenden!

InvestitionMonatsdaten (Tabelle):
  - verbrauch_daten (JSON):
    - pv_erzeugung_kwh   ✓ Primär für PV-Module
    - ladung_kwh         ✓ Primär für Speicher
    - entladung_kwh      ✓ Primär für Speicher
```

---

## [0.9.9] - 2026-02-10

### Architektur-Änderung: Standalone-Fokus

**EEDC ist jetzt primär Standalone ohne HA-Abhängigkeit für die Datenerfassung.**

### Entfernt

- Komplexer HA-Import Wizard (YAML-Generator, Template-Sensoren, Utility Meter, Automationen)
- HA-Sensor-Auswahl und Mapping-Logik
- EVCC-Berechnungen (spezielle Template-Sensoren)
- REST Command / Automation für automatischen Import

### Beibehalten

- CSV-Import (volle Funktionalität)
- Manuelles Formular für Monatsdaten
- Wetter-API (Open-Meteo/PVGIS - HA-unabhängig!)
- HA-Export via MQTT (optional)

### Begründung

Die komplexe HA-Integration erwies sich als zu kompliziert:
- EVCC liefert andere Datenstrukturen als erwartet
- Utility Meter können nicht programmatisch Geräten zugeordnet werden
- Jede Haus-Automatisierung ist anders → Kein "One Size Fits All"

---

## [0.9.8] - 2026-02-09

### Hinzugefügt

- **Wetter-API für automatische Globalstrahlung/Sonnenstunden**
  - `GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}`
  - `GET /api/wetter/monat/koordinaten/{lat}/{lon}/{jahr}/{monat}`
  - Datenquellen: Open-Meteo Archive API (historisch), PVGIS TMY (Fallback)

- **Auto-Fill Button im Monatsdaten-Formular**
  - Globalstrahlung und Sonnenstunden werden automatisch gefüllt
  - Zeigt Datenquelle an (Open-Meteo oder PVGIS TMY)

---

## [0.9.7] - 2026-02-09

### Große Daten-Bereinigung: InvestitionMonatsdaten als primäre Quelle

Diese Version löst ein fundamentales Architekturproblem: Die inkonsistente Mischung von `Monatsdaten` und `InvestitionMonatsdaten` in den Cockpit-Endpoints.

#### Neue Architektur

- **Monatsdaten** = NUR Anlagen-Energiebilanz (Einspeisung, Netzbezug, PV-Erzeugung)
- **InvestitionMonatsdaten** = ALLE Komponenten-Details (Speicher, E-Auto, WP, PV-Module, etc.)

#### Backend-Änderungen

- `get_cockpit_uebersicht`: Speicher-Daten jetzt aus InvestitionMonatsdaten
- `get_nachhaltigkeit`: Zeitreihe aus InvestitionMonatsdaten
- `get_komponenten_zeitreihe`: Erweiterte Felder für alle Komponenten
- `get_speicher_dashboard`: Arbitrage-Auswertung hinzugefügt

#### Neue Auswertungsfelder

| Komponente | Neue Felder |
|------------|-------------|
| **Speicher** | Arbitrage (Netzladung), Ladepreis, Arbitrage-Gewinn |
| **E-Auto** | V2H-Entladung, Ladequellen (PV/Netz/Extern), Externe Kosten |
| **Wärmepumpe** | Heizung vs. Warmwasser getrennt |
| **Balkonkraftwerk** | Speicher-Ladung/Entladung |
| **Alle** | Sonderkosten aggregiert |

#### Frontend-Erweiterungen

- **KomponentenTab (Auswertungen)**:
  - Speicher: Arbitrage-Badge + KPI + gestapeltes Chart
  - E-Auto: V2H-Badge, Ladequellen-Breakdown, gestapeltes Chart
  - Wärmepumpe: Heizung/Warmwasser getrennt (KPIs + gestapeltes Chart)
  - Balkonkraftwerk: "mit Speicher"-Badge + Speicher-KPIs

- **SpeicherDashboard (Cockpit)**:
  - Arbitrage-Sektion mit KPIs (Netzladung, Ø Ladepreis, Gewinn)
  - Gestapeltes Chart zeigt PV-Ladung vs. Netz-Ladung

#### Migration für bestehende Installationen

- Warnung in Monatsdaten-Ansicht wenn Legacy-Daten (Monatsdaten.batterie_*) vorhanden
- Auto-Migration beim Bearbeiten: Legacy-Werte werden automatisch in das Formular übernommen
- Benutzer muss Monatsdaten einmal öffnen und speichern um Daten zu migrieren

#### Demo-Daten erweitert

- PV-Module mit saisonaler Verteilung pro String (Süd/Ost/West)
- Speicher mit Arbitrage-Daten (ab 2025)
- Wallbox mit Ladedaten

---

## [0.9.6] - 2026-02-08

### Cockpit-Struktur verbessert

- Neuer Tab "PV-Anlage" mit detaillierter PV-System-Übersicht
  - Wechselrichter mit zugeordneten PV-Modulen und DC-Speichern
  - kWp-Gesamtleistung pro Wechselrichter
  - Spezifischer Ertrag (kWh/kWp) pro String
  - String-Vergleich nach Ausrichtung (Süd, Ost, West)
- Tab "Übersicht" zeigt jetzt ALLE Komponenten aggregiert
- Komponenten-Kacheln mit Schnellstatus und Klick-Navigation

### KPI-Tooltips

- Alle Cockpit-Dashboards zeigen Formel, Berechnung, Ergebnis per Hover
- SpeicherDashboard, WaermepumpeDashboard, EAutoDashboard
- BalkonkraftwerkDashboard, WallboxDashboard, SonstigesDashboard

---

## [0.9.5] - 2026-02-07

### PV-System ROI-Aggregation

- Wechselrichter + PV-Module + DC-Speicher als "PV-System" aggregiert
- ROI auf Systemebene statt pro Einzelkomponente
- Aufklappbare Komponenten-Zeilen im Frontend
- Einsparung proportional nach kWp auf Module verteilt

### Konfigurationswarnungen

- Warnsymbol bei PV-Modulen ohne Wechselrichter-Zuordnung
- Warnsymbol bei Wechselrichtern ohne zugeordnete PV-Module

### Bugfixes

- Jahr-Filter für Investitionen ROI-Dashboard funktionsfähig
- Investitions-Monatsdaten werden jetzt korrekt gespeichert

---

## [0.9.4] - 2026-02-06

- Jahr-Filter für ROI-Dashboard
- Unterjährigkeits-Korrektur bei Jahresvergleich
- PV_Erzeugung_kWh in CSV-Template

---

## [0.9.3] - 2026-02-05

### HA Sensor Export

- REST API: `/api/ha/export/sensors/{anlage_id}` für HA rest platform
- MQTT Discovery: Native HA-Entitäten via MQTT Auto-Discovery
- YAML-Generator: `/api/ha/export/yaml/{anlage_id}` für configuration.yaml
- Frontend: HAExportSettings.tsx mit MQTT-Config, Test, Publish

### Auswertungen Tabs

- Übersicht = Jahresvergleich (Monats-Charts, Δ%-Indikatoren, Jahrestabelle)
- PV-Anlage = Kombinierte Übersicht + PV-Details
- Investitionen = ROI-Dashboard, Amortisationskurve, Kosten nach Kategorie

---

## [0.9.2] - 2026-02-04

- Balkonkraftwerk Dashboard (Erzeugung, Eigenverbrauch, opt. Speicher)
- Sonstiges Dashboard (Flexible Kategorie: Erzeuger/Verbraucher/Speicher)
- Sonderkosten-Felder für alle Investitionstypen
- Demo-Daten erweitert (Balkonkraftwerk 800Wp + Speicher, Mini-BHKW)

---

## [0.9.1] - 2026-02-03

- Zentrale Versionskonfiguration
- Dynamische Formulare (V2H/Arbitrage bedingt)
- PV-Module mit Anzahl/Wp
- Monatsdaten-Spalten konfigurierbar
- Bugfixes: 0-Wert Import, berechnete Felder

---

## [0.9.0] - 2026-02-01

### Initiales Beta-Release

- FastAPI Backend mit SQLAlchemy 2.0 + SQLite
- React 18 Frontend mit Tailwind CSS + Recharts
- Home Assistant Add-on Konfiguration
- 7-Schritt Setup-Wizard
- Anlagen-, Strompreis-, Investitions-Verwaltung
- Monatsdaten mit CSV-Import/Export
- Cockpit mit aggregierten KPIs
- Auswertungen (Jahresvergleich, ROI, CO₂)
