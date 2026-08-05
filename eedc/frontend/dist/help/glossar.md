
# eedc Glossar & Support

**Version 4.0** | Stand: 2026-07-25

> Dieses Glossar ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Berechnungen](BERECHNUNGEN.md) | [Prognosen](HANDBUCH_PROGNOSEN.md) | [Sensor-Referenz](SENSOR-REFERENZ.md)

---

## Glossar

### Energie & Bilanzen

| Begriff | Bedeutung |
|---------|-----------|
| **Autarkie** | Grad der Unabhängigkeit vom Stromnetz: Eigenverbrauch / Gesamtverbrauch × 100 % |
| **Eigenverbrauch** | Selbst genutzter PV-Strom (Direktverbrauch + Speicher-Entladung + V2H). Kann rechnerisch > 100 % der Tages-PV liegen, wenn Batterie-Entladung aus Vortagen einfließt — im Live-Dashboard auf 100 % gecappt. |
| **Direktverbrauch** | Sofort verbrauchter PV-Strom ohne Umweg über den Speicher |
| **Einspeisung** | Ins Netz abgegebener PV-Überschuss |
| **Netzbezug** | Aus dem Netz bezogener Strom |
| **EV-Quote** | Eigenverbrauchsquote = Eigenverbrauch / PV-Erzeugung × 100 % |
| **Erzeugung hinter dem Zähler** | Summe **aller** lokalen Erzeuger am EINEN Netzanschluss (PV + Balkonkraftwerk + sonstige Erzeuger wie BHKW). Sie geht in Eigenverbrauch/Autarkie ein, nicht nur die PV-Erzeugung. |
| **Gesamtverbrauch** | Was das Haus insgesamt verbraucht hat: Eigenverbrauch + Netzbezug. eedc bilanziert den Wert aus deinen Zähler- und Komponentenwerten, es gibt keinen eigenen Hausverbrauchs-Sensor. Messen Wechselrichter PV und Speicher DC-seitig, das Netz aber AC-seitig (z. B. E3DC), enthält der Gesamtverbrauch die Wandlungsverluste und liegt ~3–5 % der Erzeugung über dem „Hausverbrauch" im Herstellerportal — beide Werte sind richtig, sie beantworten verschiedene Fragen (siehe [Berechnungsreferenz 3.1](BERECHNUNGEN.md#31-energie-bilanz-monatskennzahlen)). |
| **PV-Anlage** | Im Produkt **immer die ganze Anlage**: Wechselrichter, Module, Speicher **und** Balkonkraftwerk. So heißt auch der Komponenten-Hub. |
| **PV-Module** | Nur die Dach-/Fassaden-/Freiflächen-Module — **ohne** Balkonkraftwerk und ohne sonstige Erzeuger. Der Verlaufs-Wert dazu hieß bis v4.0.0 intern „PV-Anlage" und meinte damit das Gegenteil des Produktbegriffs; er heißt jetzt „PV-Module". |
| **`pv_erzeugung_kwh` — ein Name, drei Bedeutungen** | Je nachdem, wo der Begriff steht: (1) **Monats-Gesamtwert** der Anlage, manuell erfasst oder importiert — Grundlage der kWp-Verteilung auf die Strings; (2) **Erzeugung eines einzelnen Moduls** in dessen Monatsdaten; (3) **Auswertungs-Feld** = PV-Module **+** Balkonkraftwerk. Der Name bleibt bewusst unverändert, weil er zugleich MQTT-Topic, CSV-Spalte und Backup-Feld ist. Siehe [Berechnungen §1](BERECHNUNGEN.md#1-datenmodell-3-schichten). |
| **kWp** | Kilowatt Peak — Nennleistung der PV-Anlage unter Standardtestbedingungen |
| **kWh** | Kilowattstunde — Energiemenge |
| **Spezifischer Ertrag** | kWh je kWp Nennleistung — die Vergleichsgröße zwischen Anlagen. eedc führt sie in **zwei** Ausprägungen: **annualisiert** (saisonal gewichtet, mit der im jeweiligen Monat installierten Leistung — in Cockpit, HA-Sensor und Community-Vergleich; über verschieden lange Zeiträume vergleichbar) und **Zeitraum** (Erzeugung des Berichtszeitraums ÷ Nennleistung, ohne Normierung — im PDF-Jahresbericht, dort als **„Spez. Ertrag (Zeitraum)"** beschriftet). Über mehrere Jahre summiert sich die Zeitraum-Größe auf; beide sind richtig, sie beantworten verschiedene Fragen. |
| **Amortisation** | Ebenfalls zwei Größen: **Amortisation (Ist)** in [Auswertungen → ROI](HANDBUCH_BEDIENUNG.md#42-roi) rechnet mit den tatsächlich erfassten Erträgen und nennt neben der Dauer auch das voraussichtliche **Break-Even-Jahr** (Anker = frühestes Anschaffungsjahr). **Amortisation (Prognose)** im PDF-Finanzbericht ist eine Projektion aus Gesamtkosten ÷ prognostizierter Jahres-Einsparung. |

### Strahlung & Wetter

| Begriff | Bedeutung |
|---------|-----------|
| **GHI** | Global Horizontal Irradiance — Globalstrahlung auf horizontaler Fläche (W/m²). In Open-Meteo das Feld `shortwave_radiation`. |
| **GTI** | Global Tilted Irradiance — auf die Modul-Fläche projizierte Globalstrahlung (mit Tilt + Azimut). Bei steilen Modulen und tiefstehender Wintersonne 2–3× höher als GHI. eedc nutzt GTI seit v3.20.0 für PV-Prognose und Performance Ratio. |
| **TMY** | Typical Meteorological Year — statistisches Durchschnittswetterjahr als Prognosebasis |
| **Wettermodell-Kaskade** | Bei spezifischer Modellauswahl versucht eedc zuerst das gewählte Modell und fällt bei fehlenden Daten auf den besten verfügbaren Anbieter zurück. Datenquelle pro Tag wird mit Kürzel angezeigt (MS/D2/EU/EC/BM). Wahl unter [Einstellungen → Stammdaten → Anlage](HANDBUCH_EINSTELLUNGEN.md#21-anlage). |
| **Solar Noon** | Astronomische Tagesmitte — Zeitpunkt des höchsten Sonnenstands. Weicht je nach Standort und Datum bis ~30 min von 12:00 Clockzeit ab. eedc splittet VM/NM-Tageshälften daran. |
| **Heizgradtage** | Heuristik für die WP-Temperaturkorrektur: Differenz zwischen Innenraum-Solltemperatur (typ. 20 °C) und Außentemperatur, summiert über die Heizperiode. |

### Prognosen & Genauigkeit

| Begriff | Bedeutung |
|---------|-----------|
| **PVGIS** | Photovoltaic Geographical Information System — EU-Dienst für standortbezogene PV-Ertragsprognosen (Langfrist-/Jahressicht) |
| **Open-Meteo** | Offene Wetter-API mit globaler Abdeckung. Liefert GHI, GTI, Temperatur, Cloud Cover für Live + Kurzfrist-Prognose. |
| **Solcast** | Kommerzielle PV-Prognose-Quelle. eedc unterstützt sowohl Solcast-API (Free/Paid Key) als auch HA-Integration (BJReplay). 30-Min-Buckets, p10/p50/p90-Konfidenzbänder. |
| **SFML** | Solar Forecast ML — KI-basierte Ertragsprognose eines externen Dienstes (HA-Integration von Tom-HA). In eedc als **operative** Prognosequelle wählbar (nur im HA-Add-on). Ist sie gewählt, erscheint SFML im Prognosen-Vergleich als **Wert** — aber bewusst ohne Abweichungs-Spalte und gar nicht im Genauigkeits-Tracking. Siehe [Prognosen §2.5](HANDBUCH_PROGNOSEN.md#25-sfml-solar-forecast-ml--sichtbar-aber-bewusst-nicht-bewertet). |
| **Lernfaktor** | Anlagenspezifischer Korrekturfaktor `IST / OpenMeteo-Roh-Prognose`. Er ist die **gröbste Stufe** der Korrektur-Kaskade; feiner korrigiert eedc pro Sonnenstand × Wetterklasse und pro Stunden-Slot (siehe **Korrekturprofil**). |
| **Aktive PVGIS-Prognose** | Von beliebig vielen gespeicherten PVGIS-Abrufen ist genau **einer** aktiv — er liefert die SOLL-Werte in allen Sichten und Berichten. Die Wahl trifft der Anwender ([Einstellungen → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)); eine bewusst aktivierte **ältere** Prognose gilt überall. Seit v4.0.1 datenbankseitig auf „genau eine" begrenzt; Bestände mit mehreren aktiven werden beim Start einmalig bereinigt (deaktiviert, **nicht** gelöscht). Siehe [Prognosen §2.6](HANDBUCH_PROGNOSEN.md#26-die-aktive-pvgis-prognose--eine-und-du-bestimmst-welche). |
| **Korrekturprofil** | Mehrdimensionale Weiterentwicklung des Lernfaktors: pro Sonnenstand × Wetterklasse ein eigener Faktor — korrigiert den Tages*gang*, nicht nur die Tagessumme. Siehe [Prognosen §5.3](HANDBUCH_PROGNOSEN.md#53-das-korrekturprofil-sonnenstand--wetter). |
| **Prognose-Kanon** | EIN kanonischer Rechenweg (`services/prognose_kanon.py`) für die „PV-Tagesprognose heute" (+ Rest, morgen/übermorgen, VM/NM, Stundenprofil). Liefert allen Sichten denselben Wert — Cockpit/Live, Aussicht, Auswertungen, Vergleich-„eedc"-Spalte, persistierter Tageswert und MQTT-Sensoren. Multi-String-Fan-out pro Orientierung + Korrektur pro Energie-Slot; rollt synchron mit OpenMeteo. |
| **Tracking-Endwert (`pv_prognose_final_kwh`)** | Der für das Genauigkeits-Ranking eingefrorene Tagesprognose-Wert: rollt mit, bis OpenMeteo nach Sonnenuntergang konvergiert ist, dann fix (`pv_prognose_final_at`). Trennt den *rollenden* Anzeige-Wert vom *fertigen* Vergleichswert. |
| **MOS-Kaskade** | Saisonale Lernfaktor-Berechnung: Monatsfaktor (≥ 15 Tage gleicher Kalendermonat) → Quartalsfaktor (≥ 15 Tage) → 30-Tage-Fenster (≥ 7 Tage). Aktive Stufe wird oberhalb der Genauigkeits-Card angezeigt. |
| **MAE** | Mean Absolute Error — `Ø |err_rel|`. Misst Streuung/Schwankungsbreite, unabhängig von der Richtung. |
| **MBE / Bias** | Mean Bias Error — `Ø err_rel` (mit Vorzeichen). Positiv = Prognose im Mittel zu hoch, negativ = im Mittel zu niedrig. Neutral gefärbt — Vorzeichen ist Information, keine Wertung. |
| **Asymmetrie** | Aufteilung der signed errors in „darüber" (`err_rel > 0`) und „darunter" (`err_rel ≤ 0`). Macht sichtbar, ob eine Quelle einseitig daneben liegt — relevant, weil ein einziger Lernfaktor nur symmetrische Fehler glattziehen kann. |
| **Backward-Slot** | Slot N enthält die Energie aus dem Intervall `[N-1, N)` — „die letzte Stunde". Industriestandard für Energiezähler (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber). eedc migriert in v3.20.0 alle Energie-Quellen auf Backward; Strompreis bleibt Forward (`[N, N+1)`, „gilt ab jetzt"). |
| **Day-Ahead** | Erste Prognose des Tages, die nicht mehr überschrieben wird. eedc speichert seit v3.23.4 das Day-Ahead-Stundenprofil (OpenMeteo + Solcast) intern für künftige Diagnostik. |

### Komponenten & Effizienz

| Begriff | Bedeutung |
|---------|-----------|
| **Komponente** | Ein erfasstes Gerät der Anlage (PV-Modul, Wechselrichter, Speicher, Wärmepumpe, E-Auto, Wallbox, Balkonkraftwerk, Sonstiges). In der v4-Oberfläche der durchgängige Begriff für das, was im Datenmodell **Investition** heißt: Angelegt/konfiguriert unter [Einstellungen → Komponenten](HANDBUCH_EINSTELLUNGEN.md#3-komponenten), ausgewertet in der [Komponenten-Achse](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse). *(ehemals als „Investitionen-Tab" bezeichnet.)* |
| **Investition** | Datenmodell-Begriff für eine Komponente (Kosten, Parameter, Monatsdaten). In Berechnungen und Sensor-Namen weiterhin so benannt; in der Oberfläche „Komponente". |
| **COP** | Coefficient of Performance — momentane Effizienz der Wärmepumpe (Wärme / Strom). In eedc reserviert für mathematisch-technische Berechnungs-Variablen. |
| **SCOP** | Seasonal COP — saisonale Effizienz vom EU-Energielabel, standortunabhängig |
| **JAZ** | Jahresarbeitszahl — gemessene Effizienz der Wärmepumpe am eigenen Standort über ein Jahr. eedc zeigt Periodenkennzahlen (Cockpit, Auswertungen, Monatsdaten) seit v3.23.4 konsistent als JAZ, nicht COP. |
| **Kompressor-Starts** | Wie oft der WP-Kompressor anläuft (optionaler Total-Increasing-Zähler pro Wärmepumpe). **Verschleiß-Indikator:** viele Starts = häufiges Takten, mechanisch belastend. Allein wenig aussagekräftig — erst im Verhältnis zu den Betriebsstunden (siehe dort). |
| **Betriebsstunden** | Wie lange die Wärmepumpe tatsächlich läuft (optionaler Total-Increasing-Zähler pro WP, Stunden). **Auslegungs-Indikator:** 10 Starts bei 23 h Laufzeit/Tag sind harmloser als 10 Starts bei nur 4 h. Erst Starts ÷ Betriebsstunden („Takte pro Stunde") bzw. Betriebsstunden ÷ Starts („Ø Laufzeit pro Start") zeigen, ob die Heizkurve/Hysterese passt. Sichtbar in der Wärmepumpe-Komponentensicht, den Auswertungen und im PDF-Jahresbericht (#238). |
| **Vollzyklen** | Batterie-Lade-/Entladezyklen, normiert: `Σ |ΔSoC| / 200` (0→100→0 = 200 % = 1 Vollzyklus). Werden seit v3.22.0 ausschließlich aus stationären Speicher-SoCs berechnet — E-Auto-SoC ist ausgeschlossen. |
| **Performance Ratio** | Verhältnis IST-Ertrag zu theoretisch möglichem Ertrag (`PV_kWh / (GTI × kWp)`). Qualitätskennzahl der Anlage. Plausible Werte 0.7–0.95. |
| **V2H** | Vehicle-to-Home — E-Auto speist Strom ins Haus zurück |
| **Heimladung** | Zu Hause geladene Energie eines E-Autos (gesamt / aus PV / aus Netz), im Gegensatz zur externen Ladung unterwegs. Ab Phase 2a kanonisch an der **Wallbox** geführt, sofern eine existiert; ohne Wallbox (Steckerlader/Schuko) am E-Auto. |
| **Kanonische Quelle** | Die eine, strukturell festgelegte Investition, aus der eedc einen Wert liest, wenn ihn mehrere Komponenten messen könnten. Für die Heimladung: Wallbox vorhanden → Wallbox, sonst E-Auto. Ersetzt das frühere magnitudenabhängige „Poolen" (größerer Wert gewinnt), das bei Streudaten falsch wählen konnte. |
| **Arbitrage** | Speicher-Strategie: Bei günstigem Netzstrom laden, bei teurem Strom entladen |
| **BKW** | Balkonkraftwerk — kleine steckfertige PV-Anlage (auch: Steckersolaranlage) |
| **Anschaffungsdatum / Stilllegungsdatum** | Lebenszyklus-Marker pro Komponente. Aggregate ignorieren Monatsdaten vor dem Anschaffungsdatum bzw. ab dem Stilllegungsdatum — verhindert Verfälschung bei Erfassungs-Migration oder ausgemusterten Komponenten. Das **Anschaffungsdatum ist ab v4.0.1 Pflicht**: es ist die Grenze jeder Auswertung und der Nullpunkt der Amortisationskurve; für Bestandskomponenten ohne Datum meldet es der Daten-Checker als Fehler. Gepflegt unter [Einstellungen → Komponenten](HANDBUCH_EINSTELLUNGEN.md#32-anschaffungs--und-stilllegungsdatum). |

### Strompreise & Tarife

| Begriff | Bedeutung |
|---------|-----------|
| **EPEX** | European Power Exchange — Strombörse, Quelle für Day-Ahead-Spotpreise. eedc lädt EPEX-Börsenpreise (DE/AT) automatisch via aWATTar API als Tagesverlauf-Overlay. |
| **Dynamischer Strompreis** | Datenquellen-Feld für Tibber, aWATTar, EPEX oder eigene Template-Sensoren. Akzeptiert ct/kWh, EUR/kWh, EUR/MWh (×0.1), Cent, €. Zuordnung unter [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) (Feld „Strompreis"). |
| **§51 EEG (Negativpreis-Regel)** | Seit 2023: Ab 4 Stunden negativer Day-Ahead-Strompreise entfällt für neue PV-Anlagen die Einspeisevergütung in dieser Stunde. eedc trackt pro Tag Anzahl negativer Stunden + Einspeisung bei Negativpreis (sichtbar in [Cockpit → Monat](HANDBUCH_BEDIENUNG.md#23-monat)). |
| **Spezialtarif** | Tarif mit Zuordnung zu Standard / Wärmepumpe / Wallbox. Ohne Spezialtarif fällt eedc auf den allgemeinen Tarif zurück. |
| **Netto-Ertrag (PV)** | Was die PV-Anlage einbringt: Einspeiseerlös + Eigenverbrauchs-Ersparnis (+ Sonstige Erträge − Sonderkosten), bei Regelbesteuerung **abzüglich der USt auf den Eigenverbrauch**. **Ohne** Netzbezug-Kosten — die fielen auch ohne PV an — und **ohne** Wärmepumpen-/E-Mobilitäts-Ersparnis. Ein **Brennstoff-Erzeuger** (Mini-BHKW unter „Sonstiges") zählt hier **nicht** mit: in der Energiebilanz ja, wirtschaftlich bewusst „nicht bewertet". Kennzahl im Block „Finanz-Übersicht" ([Auswertungen → Finanzen](HANDBUCH_BEDIENUNG.md#3-auswertungen)). Siehe [Berechnungen §3.1](BERECHNUNGEN.md). |
| **Gewinn / Verlust (Haushalt)** | Ergebniszeile des SOLL/HABEN-T-Kontos: HABEN − SOLL, also Einspeiseerlös + EV-Ersparnis + Wärmepumpen-/E-Mobilitäts-Ersparnis **abzüglich** Netzbezug-Kosten und sonstiger Ausgaben. Andere Abgrenzung als der **Netto-Ertrag (PV)** im Block darüber — beide Zahlen stehen bewusst nebeneinander. |
| **Grundgebühr / Zählergebühr** | Feste monatliche bzw. jährliche Tarif-Bestandteile. Die **Grundgebühr** ist in den Netzbezugskosten enthalten; die **Zählergebühr** (optionales Tarif-Feld ab v4.0) wird getrennt ausgewiesen, aber **nicht** in Kosten/Netto verrechnet. |
| **Kraftstoffpreis** | Monatlicher Benzin-/Dieseldurchschnittspreis (€/L) aus dem EU Weekly Oil Bulletin. Ersetzt seit v3.17.0 den statischen Parameter für E-Auto-ROI. |
| **Monats-Gaspreis** | Optionales `Monatsdaten.gaspreis_cent_kwh`-Feld (ab v3.21.0) für die WP-Ersparnis-Historie. Ohne Eintrag fällt eedc auf `alter_preis_cent_kwh` der WP-Komponente zurück. |
| **MaStR** | Marktstammdatenregister — amtliches Register aller Energieerzeugungsanlagen in Deutschland |

### Energieprofil & Snapshots

| Begriff | Bedeutung |
|---------|-----------|
| **Energieprofil** | Die feinste zeitliche Auflösung der Anlagendaten: eine Zeile pro Stunde, verdichtet zu einer Zusammenfassung pro Tag. Datengrundlage fast aller anderen Auswertungen. In v4 kein eigener Tab mehr — die Anzeigen sind über die [Cockpit-Achsen](HANDBUCH_BEDIENUNG.md#2-cockpit--die-zeit-achse) verteilt, die Pflege liegt unter [Einstellungen → Daten](HANDBUCH_EINSTELLUNGEN.md#52-energieprofil-pflege). Siehe [Handbuch Energieprofil](HANDBUCH_ENERGIEPROFIL.md). |
| **Snapshot** | Stündlich erfasster kumulativer Zählerstand pro Anlage und zugeordnetem kWh-Sensor (Tabelle `sensor_snapshots`). Quellen: HA Long-Term Statistics (Add-on) oder MQTT-Energy-Snapshots (Standalone/Docker). Stunden-kWh = Differenz benachbarter Snapshots. |
| **Sensor-Snapshot-Job** | Scheduler-Job (`:05` und `:55`). `:05` schreibt regulär aus HA-Statistics, `:55` schreibt einen Live-Preview für die anstehende volle Stunde — die laufende Stunde wird damit sofort am Stundenende sichtbar. |
| **Self-Healing** | Bei fehlenden Snapshots holt eedc sie on-demand aus HA Long-Term Statistics nach (Toleranz 10 min, vorher 120 min). Echte Lücken werden linear zwischen Nachbar-Stunden interpoliert. |
| **Restart-Recovery** | Beim Scheduler-Start (Add-on-Update / Watchdog) holt eedc für die letzten 6 Stunden je Anlage Snapshots nach — verpasste `:05`/`:55`-Jobs werden idempotent ausgeholt. |
| **Tagesreset-Heuristik** | Erkennt HA-`utility_meter`-Sensoren mit täglichem 0-Reset am Muster `s1 < 0.5 ∧ s0 > 0.5` und nimmt `max(0, s1)` als Slot-0-Wert. Verhindert „IST unvollständig"-Flag um Mitternacht. |
| **Reaggregation (Tag / mehrere Tage)** | Selbsthilfe in der Reparatur-Werkbank ([Einstellungen → Daten](HANDBUCH_EINSTELLUNGEN.md#52-energieprofil-pflege)). „Tag neu aggregieren" bzw. „Mehrere Tage neu aggregieren" (max. 31) berechnet Tage neu (idempotent: delete + insert). Erfolgsmeldung zeigt Slots mit echten Messdaten (grün > 0, amber = 0). |
| **Vollbackfill** | „Lücken aus HA-LTS nachfüllen" — ergänzt **nur fehlende** Tage aus den HA-Long-Term-Statistics, strikt additiv (kein Overwrite-Modus). |
| **Counter-Feld** | Total-Increasing-Sensor ohne Energie-Einheit (z. B. WP-Kompressor-Starts). Strikt getrennt von kWh-Feldern in `KUMULATIVE_COUNTER_FELDER` — fließt nicht in die Energie-Bilanz. |
| **HA Long-Term Statistics (LTS)** | HA's `statistics`-Tabelle mit `sum`-Spalte (reset-bereinigte Kumulation) und stundengranularen `state`/`mean`/`min`/`max`. Sensoren ohne `state_class` sind **nicht** in LTS — wichtig für die Datenquellen-Wahl. |

### Integration & Datenquellen

| Begriff | Bedeutung |
|---------|-----------|
| **MQTT** | Message Queuing Telemetry Transport — schlankes Protokoll für IoT- und Smarthome-Kommunikation |
| **Datenquellen-Zuordnung** | Die zentrale feld-zentrische Fläche in v4: **jedes** eedc-Feld bezieht seinen Wert aus **genau einer** Quelle (HA-Sensor / MQTT-Gateway / MQTT-Inbound / keine). Löst die früheren getrennten Assistenten ab. Siehe [Einstellungen → Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung). *(ehemals: „Sensor-Mapping-Wizard" + „MQTT-Inbound/-Gateway-Wizard".)* |
| **MQTT-Inbound** | eedc-Funktion zum Empfang von Echtzeitdaten via die kanonischen eedc-Standard-Topics (`eedc/{anlage_id}/live/...` und `…/energy/...`). In v4 eine **Quellen-Art** je Feld in der Datenquellen-Zuordnung; die Verbindung richtest du einmal unter [Integration → MQTT-Broker](HANDBUCH_EINSTELLUNGEN.md#61-mqtt-broker-verbindung) ein. |
| **MQTT-Gateway** | eedc-Funktion zum Übersetzen eigener Geräte-Topics (Shelly, OpenDTU, Tasmota …) auf eedc-Felder. In v4 die „Gateway"-Quelle je Feld in der Datenquellen-Zuordnung. |
| **Sensor-Mapping** | *ehemals:* Zuordnung von Home-Assistant-Sensoren zu eedc-Feldern im eigenen Wizard. In v4 in die [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) aufgegangen (Quellen-Art „HA-Sensor" je Feld). Sensor-Namen/Topics unverändert. |
| **Connector** | Geräte-Modul in eedc für direkten API-Abruf von Wechselrichtern, Speichern und Ladesäulen. Startbar über die [Import-Assistenten](HANDBUCH_EINSTELLUNGEN.md#65-import-assistenten); kann seine Werte optional als MQTT-Bridge auf eedc-Topics publishen. |
| **Daten-Checker** | eedc-System für Datenqualitäts-Prüfung in mehreren Kategorien — von Stammdaten über Plausibilität bis Datenquellen-Konsistenz und HA-Statistics-Verfügbarkeit. In v4 unter [Einstellungen → Daten](HANDBUCH_EINSTELLUNGEN.md#53-daten-checker). Details: [Handbuch Daten-Checker](HANDBUCH_DATEN_CHECKER.md). |
| **Heatmap** | Tabellen-Darstellung mit Zellfärbung nach Wertgröße. eedc nutzt sie in der [Werte-Werkbank](HANDBUCH_BEDIENUNG.md#45-tabelle-werte-werkbank) (pro Spalte). Die Tag×Stunde-Heatmap des alten Energieprofils kommt später neu gestaltet zurück (Cockpit → Monat). |

### Oberfläche (v4)

| Begriff | Bedeutung |
|---------|-----------|
| **Cockpit** | Die **Zeit-Achse** der v4-Navigation: dieselbe Anlage nach Zeit-Ebene — Live · Tag · Monat · Jahr/Gesamt · Aussicht. Siehe [Bedienung §2](HANDBUCH_BEDIENUNG.md#2-cockpit--die-zeit-achse). |
| **Komponenten (Achse)** | Die **Was-Achse**: jeder Gerätetyp einzeln und in der Tiefe (ein Reiter je vorhandenem Typ). Siehe [Bedienung §3](HANDBUCH_BEDIENUNG.md#3-komponenten--die-was-achse). |
| **Auswertungen** | Die **Wie-Achse**: auswertende Gesamtsichten quer über die Zeit — Finanzen · ROI · Prognose · CO₂ · Tabelle. Siehe [Bedienung §4](HANDBUCH_BEDIENUNG.md#4-auswertungen--die-wie-achse). |
| **Aussicht** | Die vorwärtsgerichtete Cockpit-Sicht (Kurzfrist, Langfrist, Degradation) mit **Horizont-Selektor**. Der tiefere Prognose-Vergleich mit Genauigkeit liegt in [Auswertungen → Prognose](HANDBUCH_BEDIENUNG.md#43-prognose-genauigkeit-gegen-ist). |
| **Block-Modell** | Jede Sicht ist aus **Blöcken** aufgebaut, die sich klappen, umsortieren, fokussieren und parken lassen. |
| **Fokus / Vollbild** | Ein Block lässt sich in den **Fokus** heben (⤢ Vollbild-Ansicht) — z. B. eine inline gezeigte Tabelle oder die Infothek im großen Blick. Geteilte Overlay-Mechanik über alle Sichten. |
| **Parken (Parkbar)** | Einzelne Anzeigen (Kacheln, Charts) lassen sich **parken** (ausblenden) und später wiederherstellen. Eine Parkbar = eine atomare Anzeige. |
| **Herkunfts-Zeile** | Die Kopfzeile „woher kommen diese Zahlen?" über einem Diagramm, Balken oder einer Tabelle: ein Zustands-Zeichen (**gemessen** / **geschätzt** — gerechnet statt gemessen / **weicht ab** — unvollständig), worauf sich die Kennzeichnung bezieht, und ein Erklärsatz. Immer sichtbar, nicht nur als Hover-Tooltip, damit sie auch auf Touch lesbar ist. |
| **Monatsdaten-Formular** | Der EINE Erfassungsweg für die monatlichen Zählerwerte in v4 (`MonatsdatenForm`) — datengetrieben, mit Assistenz je Feld. Löst den mehrstufigen [Monatsabschluss-Wizard](#sonstiges) ab. Unter [Einstellungen → Daten → Monatsdaten](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss). |
| **Vorjahresvergleich** | Der Vergleichs-Modus der Werte-Tabelle und der Zeit-Sichten: jede Zeile steht **ihrem eigenen** Zeitraum ein Jahr früher gegenüber (Dez 2025 ↔ Dez 2024), auch über mehrjährige Zeiträume. Fehlt dieser Vorjahres-Zeitraum, bleibt die Spalte **leer („—")** — es wird kein Ersatzwert eingesetzt. Siehe [Bedienung §4.5](HANDBUCH_BEDIENUNG.md#45-tabelle-werte-werkbank). |
| **Status-Fußzeile** | Die dauerhaft sichtbare Zeile mit Anlagen-Auswahl, Datenquellen-/Teilen-Status und Verbindungshinweisen. |
| **CollapsibleSection** | Wiederverwendbare UI-Komponente mit localStorage-Persistenz pro `storageKey`. Status der Sektionen (offen/zu) bleibt pro Browser erhalten. |

### Sonstiges

| Begriff | Bedeutung |
|---------|-----------|
| **Infothek** | Optionales eedc-Modul zur Verwaltung von Verträgen, Zählern, Kontakten und Dokumenten. N:M-Verknüpfung mit Komponenten seit v3.15.2. In v4 eine eigene Kachel-Kategorie unter [Einstellungen → Infothek](HANDBUCH_EINSTELLUNGEN.md#41-infothek). Siehe [Handbuch Infothek](HANDBUCH_INFOTHEK.md). |
| **Monatsabschluss** | Die monatliche Datenerfassung. In v4 als **Monatsdaten-Formular** umgesetzt (ein Formular, datengetrieben, mit Assistenz je Feld und automatischen Vorschlägen aus HA-Statistik / Datenquelle / Vorjahr). *(ehemals: mehrstufiger „Monatsabschluss-Wizard" — als v4-Fläche stillgelegt, bis zum Flip nur noch über die alte Route erreichbar.)* |
| **Sonstige Positionen** | Frei erfassbare Kosten und Erlöse je Monat (Reparaturen, Wartung, THG-Quote, Guthaben-Auszahlung …), Typ Ertrag/Ausgabe. Ab v4.0 auch auf **Anlage-Ebene** (nicht nur pro Komponente); sie fließen in Netto-Ertrag und T-Konto ein. Siehe [Berechnungen §3.10](BERECHNUNGEN.md#310-sonstige-positionen). |
| **Community-Hash** | Anonymer Identifier für die Community-Benchmark-Funktion; kein Rückschluss auf Person oder Adresse |
| **In-App-Hilfe** | Hilfe-Seite (Hauptmenü „Hilfe") seit v3.24.0. Rendert die kuratierten Markdown-Dokumente direkt in der App — funktioniert in der HA-Companion-App identisch zum Browser. URL-Parameter `?doc=<slug>` macht Direktlinks teilbar. |
| **ICON-CH2** | MeteoSwiss-Wettermodell mit 2 km Auflösung; empfohlen für alpine Standorte (CH, AT, Südtirol) |
| **ICON-D2** | DWD-Wettermodell mit 2,2 km Auflösung; hochauflösend für Deutschland |
| **ECMWF IFS** | Globales Wettermodell des Europäischen Zentrums für mittelfristige Wettervorhersage |

---

## Support

Bei Fragen oder Problemen:

1. **In-App-Hilfe** (Hauptmenü → Hilfe): Vollständiges Handbuch direkt in der App
2. **GitHub Issues**: [github.com/supernova1963/eedc-homeassistant/issues](https://github.com/supernova1963/eedc-homeassistant/issues)
3. **Protokolle** ([Einstellungen → System → Protokolle](HANDBUCH_EINSTELLUNGEN.md#84-protokolle)): Debug-Modus aktivieren, Problem reproduzieren, Logs als Markdown-Tabelle kopieren, in Issue einfügen
4. **Daten-Checker** ([Einstellungen → Daten → Daten-Checker](HANDBUCH_EINSTELLUNGEN.md#53-daten-checker)): prüft Datenqualität in mehreren Kategorien — von Stammdaten über Plausibilität bis Datenquellen-Konsistenz und HA-Statistics-Verfügbarkeit
5. **Web-Dokumentation**: [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/)

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
