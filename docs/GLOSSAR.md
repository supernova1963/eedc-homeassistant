
# eedc Glossar & Support

**Version 3.24.1** | Stand: April 2026

> Dieses Glossar ist Teil der eedc-Dokumentation.
> Siehe auch: [Teil I: Installation](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Berechnungen](BERECHNUNGEN.md) | [Sensor-Referenz](SENSOR-REFERENZ.md)

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
| **kWp** | Kilowatt Peak — Nennleistung der PV-Anlage unter Standardtestbedingungen |
| **kWh** | Kilowattstunde — Energiemenge |

### Strahlung & Wetter

| Begriff | Bedeutung |
|---------|-----------|
| **GHI** | Global Horizontal Irradiance — Globalstrahlung auf horizontaler Fläche (W/m²). In Open-Meteo das Feld `shortwave_radiation`. |
| **GTI** | Global Tilted Irradiance — auf die Modul-Fläche projizierte Globalstrahlung (mit Tilt + Azimut). Bei steilen Modulen und tiefstehender Wintersonne 2–3× höher als GHI. eedc nutzt GTI seit v3.20.0 für PV-Prognose und Performance Ratio. |
| **TMY** | Typical Meteorological Year — statistisches Durchschnittswetterjahr als Prognosebasis |
| **Wettermodell-Kaskade** | Bei spezifischer Modellauswahl versucht eedc zuerst das gewählte Modell und fällt bei fehlenden Daten auf den besten verfügbaren Anbieter zurück. Datenquelle pro Tag wird mit Kürzel angezeigt (MS/D2/EU/EC/BM). |
| **Solar Noon** | Astronomische Tagesmitte — Zeitpunkt des höchsten Sonnenstands. Weicht je nach Standort und Datum bis ~30 min von 12:00 Clockzeit ab. eedc splittet VM/NM-Tageshälften daran. |
| **Heizgradtage** | Heuristik für die WP-Temperaturkorrektur: Differenz zwischen Innenraum-Solltemperatur (typ. 20 °C) und Außentemperatur, summiert über die Heizperiode. |

### Prognosen & Genauigkeit

| Begriff | Bedeutung |
|---------|-----------|
| **PVGIS** | Photovoltaic Geographical Information System — EU-Dienst für standortbezogene PV-Ertragsprognosen |
| **Open-Meteo** | Offene Wetter-API mit globaler Abdeckung. Liefert GHI, GTI, Temperatur, Cloud Cover für Live + Kurzfrist-Prognose. |
| **Solcast** | Kommerzielle PV-Prognose-Quelle. eedc unterstützt sowohl Solcast-API (Free/Paid Key) als auch HA-Integration (BJReplay). 30-Min-Buckets, p10/p50/p90-Konfidenzbänder. |
| **SFML** | Solar Forecast ML — KI-basierte Ertragsprognose eines externen Dienstes (forecast.solar oder solcast.com) |
| **Lernfaktor** | Anlagenspezifischer Korrekturfaktor `IST / OpenMeteo-Roh-Prognose`. eedc-kalibrierte Prognose = OpenMeteo × Lernfaktor. |
| **MOS-Kaskade** | Saisonale Lernfaktor-Berechnung: Monatsfaktor (≥ 15 Tage gleicher Kalendermonat) → Quartalsfaktor (≥ 15 Tage) → 30-Tage-Fenster (≥ 7 Tage). Aktive Stufe wird oberhalb der Genauigkeits-Card angezeigt. |
| **MAE** | Mean Absolute Error — `Ø |err_rel|`. Misst Streuung/Schwankungsbreite, unabhängig von der Richtung. |
| **MBE / Bias** | Mean Bias Error — `Ø err_rel` (mit Vorzeichen). Positiv = Prognose im Mittel zu hoch, negativ = im Mittel zu niedrig. Neutral gefärbt — Vorzeichen ist Information, keine Wertung. |
| **Asymmetrie** | Aufteilung der signed errors in „darüber" (`err_rel > 0`) und „darunter" (`err_rel ≤ 0`). Macht sichtbar, ob eine Quelle einseitig daneben liegt — relevant, weil ein einziger Lernfaktor nur symmetrische Fehler glattziehen kann. |
| **Backward-Slot** | Slot N enthält die Energie aus dem Intervall `[N-1, N)` — „die letzte Stunde". Industriestandard für Energiezähler (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber). eedc migriert in v3.20.0 alle Energie-Quellen auf Backward; Strompreis bleibt Forward (`[N, N+1)`, „gilt ab jetzt"). |
| **Day-Ahead** | Erste Prognose des Tages, die nicht mehr überschrieben wird. eedc speichert seit v3.23.4 das Day-Ahead-Stundenprofil (OpenMeteo + Solcast) intern für künftige Diagnostik. |

### Komponenten & Effizienz

| Begriff | Bedeutung |
|---------|-----------|
| **COP** | Coefficient of Performance — momentane Effizienz der Wärmepumpe (Wärme / Strom). In eedc reserviert für mathematisch-technische Berechnungs-Variablen. |
| **SCOP** | Seasonal COP — saisonale Effizienz vom EU-Energielabel, standortunabhängig |
| **JAZ** | Jahresarbeitszahl — gemessene Effizienz der Wärmepumpe am eigenen Standort über ein Jahr. eedc zeigt Periodenkennzahlen (Cockpit, Auswertung, Monatsabschluss) seit v3.23.4 konsistent als JAZ, nicht COP. |
| **Vollzyklen** | Batterie-Lade-/Entladezyklen, normiert: `Σ |ΔSoC| / 200` (0→100→0 = 200 % = 1 Vollzyklus). Werden seit v3.22.0 ausschließlich aus stationären Speicher-SoCs berechnet — E-Auto-SoC ist ausgeschlossen. |
| **Performance Ratio** | Verhältnis IST-Ertrag zu theoretisch möglichem Ertrag (`PV_kWh / (GTI × kWp)`). Qualitätskennzahl der Anlage. Plausible Werte 0.7–0.95. |
| **V2H** | Vehicle-to-Home — E-Auto speist Strom ins Haus zurück |
| **Arbitrage** | Speicher-Strategie: Bei günstigem Netzstrom laden, bei teurem Strom entladen |
| **BKW** | Balkonkraftwerk — kleine steckfertige PV-Anlage (auch: Steckersolaranlage) |
| **Anschaffungsdatum / Stilllegungsdatum** | Lebenszyklus-Marker pro Investition. Aggregate ignorieren Monatsdaten vor dem Anschaffungsdatum bzw. ab dem Stilllegungsdatum — verhindert Verfälschung bei Erfassungs-Migration oder ausgemusterten Komponenten. |

### Strompreise & Tarife

| Begriff | Bedeutung |
|---------|-----------|
| **EPEX** | European Power Exchange — Strombörse, Quelle für Day-Ahead-Spotpreise. eedc lädt EPEX-Börsenpreise (DE/AT) automatisch via aWATTar API als Tagesverlauf-Overlay. |
| **Dynamischer Strompreis** | Sensor-Mapping-Feld für Tibber, aWATTar, EPEX oder eigene Template-Sensoren. Akzeptiert ct/kWh, EUR/kWh, EUR/MWh (×0.1), Cent, €. |
| **§51 EEG (Negativpreis-Regel)** | Seit 2023: Ab 4 Stunden negativer Day-Ahead-Strompreise entfällt für neue PV-Anlagen die Einspeisevergütung in dieser Stunde. eedc trackt pro Tag Anzahl negativer Stunden + Einspeisung bei Negativpreis. |
| **Spezialtarif** | Tarif mit Zuordnung zu Standard / Wärmepumpe / Wallbox. Ohne Spezialtarif fällt eedc auf den allgemeinen Tarif zurück. |
| **Kraftstoffpreis** | Monatlicher Benzin-/Dieseldurchschnittspreis (€/L) aus dem EU Weekly Oil Bulletin. Ersetzt seit v3.17.0 den statischen Parameter für E-Auto-ROI. |
| **Monats-Gaspreis** | Optionales `Monatsdaten.gaspreis_cent_kwh`-Feld (ab v3.21.0) für die WP-Ersparnis-Historie. Ohne Eintrag fällt eedc auf `alter_preis_cent_kwh` der WP-Investition zurück. |
| **MaStR** | Marktstammdatenregister — amtliches Register aller Energieerzeugungsanlagen in Deutschland |

### Energieprofil & Snapshots

| Begriff | Bedeutung |
|---------|-----------|
| **Snapshot** | Stündlich erfasster kumulativer Zählerstand pro Anlage und gemapptem kWh-Sensor (Tabelle `sensor_snapshots`). Quellen: HA Long-Term Statistics (Add-on) oder MQTT-Energy-Snapshots (Standalone/Docker). Stunden-kWh = Differenz benachbarter Snapshots. |
| **Sensor-Snapshot-Job** | Scheduler-Job (`:05` und `:55`). `:05` schreibt regulär aus HA-Statistics, `:55` schreibt einen Live-Preview für die anstehende volle Stunde — die laufende Stunde wird damit sofort am Stundenende sichtbar. |
| **Self-Healing** | Bei fehlenden Snapshots holt eedc sie on-demand aus HA Long-Term Statistics nach (Toleranz 10 min, vorher 120 min). Echte Lücken werden linear zwischen Nachbar-Stunden interpoliert. |
| **Restart-Recovery** | Beim Scheduler-Start (Add-on-Update / Watchdog) holt eedc für die letzten 6 Stunden je Anlage Snapshots nach — verpasste `:05`/`:55`-Jobs werden idempotent ausgeholt. |
| **Tagesreset-Heuristik** | Erkennt HA-`utility_meter`-Sensoren mit täglichem 0-Reset am Muster `s1 < 0.5 ∧ s0 > 0.5` und nimmt `max(0, s1)` als Slot-0-Wert. Verhindert „IST unvollständig"-Flag um Mitternacht. |
| **Pro-Tag-Reaggregation** | Selbsthilfe-Knopf in der Tages-Tabelle. Triggert `aggregate_day` für einen einzelnen Tag (idempotent: delete + insert). Erfolgsmeldung zeigt Slots mit echten Messdaten (grün > 0, amber = 0). |
| **Counter-Feld** | Total-Increasing-Sensor ohne Energie-Einheit (z. B. WP-Kompressor-Starts). Strikt getrennt von kWh-Feldern in `KUMULATIVE_COUNTER_FELDER` — fließt nicht in die Energie-Bilanz. |
| **HA Long-Term Statistics (LTS)** | HA's `statistics`-Tabelle mit `sum`-Spalte (reset-bereinigte Kumulation) und stundengranularen `state`/`mean`/`min`/`max`. Sensoren ohne `state_class` sind **nicht** in LTS — wichtig für die Mapping-Wahl. |

### Integration & Tools

| Begriff | Bedeutung |
|---------|-----------|
| **MQTT** | Message Queuing Telemetry Transport — schlankes Protokoll für IoT- und Smarthome-Kommunikation |
| **MQTT-Inbound** | eedc-Funktion zum Empfang von Echtzeitdaten aus beliebigen Smarthome-Systemen via MQTT (`eedc/{anlage_id}/live/...` und `…/energy/...`). |
| **MQTT-Gateway** | eedc-Funktion zum Übersetzen eigener Geräte-Topics (Shelly, OpenDTU, Tasmota …) auf eedc-Felder |
| **Sensor-Mapping** | Zuordnung von Home-Assistant-Sensoren zu eedc-Feldern im Wizard |
| **Connector** | Geräte-Modul in eedc für direkten API-Abruf von Wechselrichtern, Speichern und Ladesäulen |
| **Daten-Checker** | eedc-System für Datenqualitäts-Prüfung in 8 Kategorien — von Stammdaten über Plausibilität bis MQTT-Topic-Abdeckung und HA-Statistics-Verfügbarkeit. |
| **Heatmap** | Tabellen-Darstellung mit Zellfärbung nach Wertgröße. eedc nutzt sie in Auswertung → Energieprofil → Monat (24h × N Tage) und in der Tage-Tabelle (pro Spalte). |
| **CollapsibleSection** | Wiederverwendbare UI-Komponente mit localStorage-Persistenz pro `storageKey`. Status der Sektionen (offen/zu) bleibt pro Browser erhalten. |

### Sonstiges

| Begriff | Bedeutung |
|---------|-----------|
| **Infothek** | Optionales eedc-Modul zur Verwaltung von Verträgen, Zählern, Kontakten und Dokumenten. N:M-Verknüpfung mit Investitionen seit v3.15.2. |
| **Monatsabschluss** | Monatliche Datenerfassung via geführtem Wizard mit automatischen Vorschlägen aus HA-Statistik / MQTT / Connector / Gespeichert (Konfidenz 85–95). |
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
3. **Protokolle-Seite** (Einstellungen → System → Protokolle): Debug-Modus aktivieren, Logs kopieren, in Issue einfügen
4. **Daten-Checker** (Einstellungen → System → Daten-Checker): Zeigt 8 Prüfkategorien — von Stammdaten über Plausibilität bis MQTT-Topic-Abdeckung und HA-Statistics-Verfügbarkeit
5. **Web-Dokumentation**: [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/)

---

*Letzte Aktualisierung: April 2026 (v3.24.1)*
