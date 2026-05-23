# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

---

## [3.32.3] - 2026-05-23 — Doku-Nachreichung WAS-IST-NEU

> 📝 **Reine Doku-Nachreichung.** Bei v3.32.2 war die WAS-IST-NEU-Seite noch auf v3.32.1-Stand — `sync-help.sh` läuft vor dem Frontend-Build, also wurde der alte Stand ins v3.32.2-Image gebacken. Anwender hätten den v3.32.2-Inhalt erst beim nächsten Release gesehen. Diese Version bringt den WAS-IST-NEU-Block für v3.32.2 in die In-App-Hilfe.

### Changed

- **WAS-IST-NEU.md (In-App-Hilfe „Was ist neu") für v3.32.2 nachgepflegt**: Sungrow-AppKey-Rotation, EcoFlow-indexNames, Victron-Freigabe, WP-Betriebsstunden, evcc-Pool-Mismatch-Warnung, §51 EEG Phase 2, Delete-Button-Hinweis und IA-v4.0.0-Konzept sind jetzt auch in der In-App-Hilfe sichtbar. Keine Code-Änderungen.

---

## [3.32.2] - 2026-05-23 — Cloud-Import-Hardening + WP-Betriebsstunden + IA v4.0.0 Konzept

> 🔧 **Patch-Release.** Schwerpunkt: drei Cloud-Import-Tester-Fixes (Sungrow #287, EcoFlow Dirk-PN, Victron-Verifizierung #255), neues WP-Betriebsstunden-Tracking (#238) und das IA v4.0.0 Konzept als gemeinsame Anlaufstelle für den größeren UX-/Menüstruktur-Refactor in der nächsten Major-Welle.

### Added

- **WP-Betriebsstunden-Sensor + KPIs** (#238 detLAN): optionaler `total_increasing`-Sensor pro WP-Investition, integriert in die `KUMULATIVE_COUNTER_FELDER`-Architektur. Tagesaggregat liefert Starts × Betriebsstunden + Ø Laufzeit pro Start; KPI-Kachel im Monatsbericht und im WP-Dashboard. Architektur analog v3.24.0 Kompressor-Starts.
- **Daten-Checker: evcc-Pool-Pflege-Mismatch-Warnung** (Phase 2a): erkennt, wenn der zentrale evcc-Pool-Sensor nicht (mehr) zur Sensor-Zuordnung passt — z. B. nach Wallbox/E-Auto-Hinzufügen ohne Pool-Update. Diagnostischer Hinweis mit Reparatur-Link, kein Auto-Heal.

### Changed

- **§51 EEG Phase 2 — Erlös-Abzug in weiteren Read-Sites**: nach Phase 1 (Aussichten + Monatsabschluss) wird der Abzug bei negativen Börsenpreisen jetzt auch in Cockpit-Übersicht, ROI-Dashboard, PDF-Jahresbericht, HA-Sensor-Export, Auswertungen-Energie und Auswertungen-Finanzen konsistent angewendet. Single Source of Truth: `core/berechnungen/eeg.py:erloes_minus_eeg51`.
- **Berechnungs-Layer PRIO-1-Migrationen**: `prognosen.py` und `repair.py` lesen IST-PV-Ertrag jetzt über den SoT-Helper `summe_pv_bkw_kwh` aus `core/berechnungen/energie.py` (Whitelist-konsistent zu Cockpit/Aussichten/HA-Export; ADR-001). Verhindert Drift-Klasse 2026-05-19 (BKW-Bug, Rainer-PN) in Genauigkeits- und Reparatur-Pfaden.

### Fixed

- **Cloud-Import Sungrow iSolarCloud: AppKey-Rotation entschärft** (#287 detlefh68): der mitgesendete App-Key war auf einem alten Stand und wurde von Sungrow mit „Illegal c-access-key" abgelehnt. Aktualisiert auf den aktuellen Default-Wert aus dem GoSungrow-Projekt. Plus optionales Feld „App-Key" im Setup, damit bei künftiger Key-Rotation der Anwender einen eigenen Wert eintragen kann, ohne auf ein eedc-Release warten zu müssen.
- **Cloud-Import EcoFlow PowerOcean: echte indexName-Matrix** (Dirk-PN): die in v3.32.0 hinzugefügte Diagnose hat die echten `indexName`s im API-Response aus Dirks Log offengelegt. Mapping um die tatsächlich gelieferten Namen ergänzt — der Import liefert jetzt Werte statt leer zu bleiben.
- **Investitionen löschen: stiller Disabled-Button** (#288 NongJoWo): der „Endgültig löschen"-Button im Backup-Bestätigungsdialog ist by design disabled, solange weder ein Backup erstellt noch „Ohne Backup fortfahren" geklickt wurde — der Grund war im Dialog nicht sichtbar. Jetzt: dezenter Hilfetext links neben den Aktions-Buttons („Bitte oben eine Backup-Option wählen") plus Tooltip am disabled Button.

### Cloud-Import

- **Victron VRM: `getestet=True`** (#255 kingcap1): nach erfolgreicher Verifizierung gegen ein echtes Konto wird der `getestet=False`-Banner entfernt. Der Provider ist damit vollständig produktiv.

### Konzept

- **IA v4.0.0 — Informationsarchitektur-Konzept veröffentlicht** ([#243](https://github.com/supernova1963/eedc-homeassistant/issues/243)): drei orthogonale Achsen (Zeit / Was / Wie) lösen die heutige Vermischung in der Top-Navigation auf. Cockpit wird zur Zeitachse (Live · Heute · Monatsbericht · Jahr · Aussicht), Komponenten bekommen einen eigenen Hub mit Status/Verlauf/Vergleich/Aussicht-Sektionen, Auswertungen wird auf analytische Schnitte konsolidiert. Drei Konzept-Dokumente in `docs/`: [`KONZEPT-IA-V4.md`](docs/KONZEPT-IA-V4.md), [`KONZEPT-STYLE-GUIDE.md`](docs/KONZEPT-STYLE-GUIDE.md) (mit Hell/Dunkel-Mode + Einstellbarkeits-Cap), [`KONZEPT-MOBILE.md`](docs/KONZEPT-MOBILE.md) (Hamburger-Top-Nav, Pflicht-Querschnittsregeln). Feedback und Ideen sind willkommen, zentral im Issue. Code-Umsetzung folgt in v4.0.0.

---

## [3.32.1] - 2026-05-23 — Multi-Geräte-Drift-Hardening + Tester-Fixes

> 🔧 **Patch-Release.** Schwerpunkt: Aggregations-Drift bei Anlagen mit mehreren E-Autos oder Wärmepumpen. Eine Schleife schrieb Vergleichsparameter (Vergleichsverbrauch, Vergleichspreis, Wirkungsgrad) last-write-wins in globale Variablen — alle Geräte wurden mit den Werten des LETZTEN gerechnet. Betroffen waren Aussichten, ROI-Dashboard, HA-Sensor-Export und der PDF-Jahresbericht. Plus zwei Folge-Fixes zu #286 (`MonatsdatenForm`-Pfad + 0-€-Positionen).

### Changed

- **ROI-Dashboard: Benzinpreis-Auflösungs-Kette pro E-Auto** (Nebenbefund #260): Der Query-Param `benzinpreis_euro` ist jetzt optional. Pro E-Auto-Berechnung: Slider-Override → `inv.parameter['benzinpreis_euro']` → letzter `Monatsdaten.kraftstoffpreis_euro` (EU OB) → `PARAM_E_AUTO_DEFAULTS['benzinpreis_euro']`. Vorher las das ROI-Dashboard im E-Auto-Branch 7 von 8 nötigen Params aus `inv.parameter` (v3.25.0-Klasse), `benzinpreis_euro` war vergessen — Query-Default 1,85 €/L überschrieb stillschweigend gepflegte Werte. Frontend-Slider-State von Hardcode `1.85` auf `undefined` (leer = nicht überschreiben); Placeholder zeigt den aufgelösten Marktpreis aus der Response.
- **PDF-Jahresbericht: IMD vor Anschaffung / nach Stilllegung gefiltert**: `all_imd` in `pdf_operations.py` wird jetzt analog `aussichten.py:942` (#236, v3.29.0) mit `inv.ist_aktiv_im_monat` vorgefiltert. Custom-Import-Daten außerhalb der Investitions-Lebenszeit fließen damit nicht mehr in PV-Erzeugung, Speicher-Ladung, WP-Wärme und E-Mob-Aggregate des Jahresberichts ein.
- **Aussichten: bisherige-Ersparnis-Schleifen mit `ist_aktiv_im_monat`-Filter** in WP, E-Auto, BKW, sonstige Positionen, Dienstlich-Ladekosten. Schließt eine Lücke nach #236 — die Quoten-/PV-Anteilsberechnung filterte bereits, die parallelen Ersparnis-Schleifen nicht. PV/BKW-Erzeugungs-Aggregation bleibt bewusst ungefiltert (Issue #123 — historische Erzeugung darf durch spätere Stilllegung nicht aus der Vergangenheit gelöscht werden).

### Fixed

- **Aussichten: Mehrfach-E-Auto-Drift** (Bug A + B + C, drei verkettete Vorkommen einer Wurzel): `eauto_benzinpreis` und `eauto_vergleich_l_100km` wurden in einer `for ea`-Schleife last-write-wins in globale Variablen geschrieben. Bei zwei E-Autos mit unterschiedlichen Parametern (z. B. Klein-EV 6 L/100km und SUV-EV 10 L/100km) wurden beide mit den Werten des letzten gerechnet — `bisherige_eauto_ersparnis`, `jahres_eauto_km_ersparnis` und die per-EA-`KomponentenBeitragSchema`-Beschreibungstexte waren entsprechend falsch. Fix: `eauto_aggregate[ea.id]` mit per-E-Auto-Werten, km-gewichteter Aggregat für die Saisonalprognose, per-EA-Aufschlüsselung der Komponenten-Beiträge.
- **HA-Sensor-Export: Mehrfach-E-Auto-Drift + Monatspreis-Fallback** (`calculate_anlage_sensors`): selbe last-write-wins-Klasse wie in Aussichten. Davon abgeleitet: HA-Sensoren `jahres_ersparnis_euro`, `roi_prozent` und `amortisation_jahre` waren bei Multi-EA-Haushalten falsch. Zusätzlich fehlte der `Monatsdaten.kraftstoffpreis_euro`-Fallback — der Anlage-Sensor driftete dadurch auch gegen den per-Investition-Sensor `e_auto_ersparnis_vs_benzin_euro` (der den Monatspreis korrekt nutzt). Fix: per-EA-Lookup in der Ersparnis-Schleife + Monats-Preis-Fallback pro Monat.
- **PDF-Jahresbericht: Mehrfach-E-Auto-Drift + Wallbox-Falle** (`export_pdf`): die Vergleichsparameter wurden aus der ERSTEN passenden e-auto-ODER-wallbox-Investition mit `parameter` gezogen (`for inv … break`). Bei zwei E-Autos griff nur der erste; stand zudem eine Wallbox mit irgendwelchen Parametern vor der E-Auto in der Liste, wurde die Wallbox zur Param-Quelle — obwohl `vergleich_verbrauch_l_100km` ein Vehicle-Attribut ist. Fix: neuer SoT-Helper `km_gewichtete_eauto_params` in `services/eauto_wirtschaftlichkeit.py`, iteriert nur über E-Autos, km-gewichtet (bei 1 EA = dessen Wert).
- **Aussichten + HA-Export + PDF-Jahresbericht: Mehrfach-Wärmepumpe-Drift**: gleiche Klasse wie E-Auto, aber für WP-Vergleichsparameter (`alter_preis_cent_kwh`, `alter_energietraeger`/Wirkungsgrad). Bei zwei WPs mit unterschiedlichen Energieträgern (Gas + Öl) wurde die Gas-WP mit dem Öl-Wirkungsgrad gerechnet — alte Heizungskosten ~5,5 % zu hoch angesetzt. `pdf_operations.py` hatte zusätzlich `break` → `wp_alternativ_zusatzkosten_jahr` summierte nicht über alle WPs. Fix: `wp_aggregate`-Dict pro WP, thermisch-gewichtetes Mittel für Aggregat-Werte in der Jahresprognose.
- **Monatsabschluss: sonstige Positionen über `MonatsdatenForm` wieder löschbar** (#286 rcmcronny): Der v3.32.0-Fix (`50706fe7`) deckte nur den Wizard ab — `MonatsdatenForm` (Tabellen-Edit) hatte exakt denselben Bug. Bei leerer Positionen-Liste wurde der Sub-Key nicht ins Payload aufgenommen, der Backend-Helper `_save_investitionen_monatsdaten` ließ den Sub-Key unangetastet, die alte Liste blieb in der DB. Fix: `initialHattePositionen`-Spur + Submit schickt `sonstige_positionen: []` als explizites Löschsignal; 0-€-Filter raus (rilmor-Klasse). +3 Akzeptanztests für beide Wege.
- **Monatsabschluss: 0-€-Positionen werden gespeichert** (#286 rilmor-mhrs): der `betrag > 0`-Filter im Frontend (`MonatsabschlussWizard.tsx:493`) und Backend (`monatsabschluss/wizard.py:330`) verwarf 0-€-Positionen mit Bezeichnung stillschweigend. Neuer SoT-Helper `ist_gueltige_position` in `utils/sonstige_positionen.py` (Kriterium: nur Bezeichnung nicht leer); Backend importiert, Frontend gelockert.
- **E-Auto-Dashboard: Benzinpreis pro Monat aus EU-OB** (#260 NongJoWo): `get_eauto_dashboard` summierte km gesamt und multiplizierte einmal mit einem Query-Default 1,65 €/L — die Cockpit-Übersicht rechnete dagegen seit v3.17.0 pro Monat mit `Monatsdaten.kraftstoffpreis_euro`. Resultat: 2696 € vs. 2375 € für dieselbe Anlage. Neuer SoT-Helper `berechne_eauto_ersparnis_periode` in `services/eauto_wirtschaftlichkeit.py` (`Σ km_monat × verbrauch × preis_monat`); Query-Param entfernt (war effektiv tot).
- **Monatsabschluss-Wizard: doppeltes „Sonstiges" in der Stepper-Leiste** (Rainer-PN): bei einer `typ='sonstiges'`-Investition hieß sowohl der Investitionstyp-Schritt als auch der nachfolgende OPTIONALE_FELDER-Schritt „Sonstiges". Fix: der hintere Schritt heißt „Allgemein" (typ-übergreifend); bei genau einer `sonstiges`-Investition wird deren `bezeichnung` als Stepper-Titel verwendet.

### Cloud-Import

- **Victron VRM gegen die echte API neu gebaut** (#255): der v3.32.0-Provider war ein erster Wurf — der neue ruft `/users/me`+`installations` für die Discovery, mappt die Energiefluss-Matrix korrekt auf Monatswerte und chunked in 24-Monats-Blöcken. `getestet=False`-Banner bleibt vorerst; Verifizierung über kingcap1/FrodoVDR-Konten erbeten.
- **EcoFlow PowerOcean/PowerStream: Diagnose-Log für indexNames**: bei leerem Cloud-Import schreibt eedc jetzt die tatsächlichen `indexName`s pro Block ins INFO-Log und gibt ein WARNING aus, wenn die API zwar antwortet, aber keiner der bekannten Index-Namen zutrifft — vereinfacht künftige Mapping-Erweiterungen.

---

## [3.32.0] - 2026-05-22 — Victron-VRM-Cloud-Import + Fix-Bündel

> ✨ **Feature-Release.** Neu: ein Cloud-Import-Provider für das Victron VRM Portal. Dazu ein Bündel Fehlerbehebungen — ROI-Dashboard-Absturz, nächtlicher Scheduler-Crash, EcoFlow-History-Import und zwei Fehlalarme rund um Speicher-Kennzahlen.

### Added

- **Victron VRM Cloud-Import** (#255): neuer Cloud-Import-Provider holt historische Monatswerte (PV-Erzeugung, Einspeisung, Netzbezug, Batterie) direkt aus dem Victron VRM Portal — für das Nachholen von Daten aus der Zeit vor der HA-Anbindung. Anmeldung per Access-Token (im VRM-Portal unter Preferences → Integrations erzeugt), kein Passwort, kein Admin-Recht nötig. Der Live-Pfad (HA-Add-on + ha-victron-mqtt) bleibt unberührt. Der Provider ist noch nicht final mit echten Konten getestet (`getestet=False`).

### Changed

- **Speicher-Effizienz-Chart auf gleitende 12 Monate** (rapahl-PN): die Monats-Effizienz `Entladung/Ladung` konnte über 100 % anzeigen — pro Monat ist das durch den Ladestands-Übertrag legitim, als Kennzahl aber irreführend. Das Chart zeigt jetzt die gleitende 12-Monats-Effizienz (Carry-over-immun); eine neue Berechnungs-Invariante prüft `Σ Entladung ≤ Σ Ladung` kumulativ.

### Fixed

- **ROI-Dashboard-Absturz** (#285): das ROI-Dashboard zeigte „Ein Fehler ist aufgetreten" und ließ sich nicht öffnen — gleiche Fehlerklasse wie der Speicher-Cockpit-Absturz in v3.31.8 (`installationsdatum` statt `anschaffungsdatum`), an zwei weiteren Stellen. Behoben + Regressionstests. Mit Dank an Klausnn für die Meldung.
- **Nächtlicher Scheduler-Crash** (#286): ein Hintergrund-Job brach nachts mit einem Fehler ab — Ursache war ein falsch genutzter Datenbank-Kontext an zwei Job-Stellen. Behoben. Mit Dank an rcmcronny für die Meldung.
- **Monatsabschluss: sonstige Positionen wieder löschbar** (#286): sonstige Kostenpositionen ließen sich im Monatsabschluss nicht mehr entfernen. Behoben.
- **EcoFlow History-Import** (Dirk-PN): der Cloud-Import scheiterte mit `time must be less than one week`. Die EcoFlow-API verlangt ein Abfragefenster von strikt weniger als einer Woche — eedc fragt jetzt in 6-Tage-Blöcken ab. Historische Daten beliebigen Alters lassen sich damit importieren.
- **Daten-Checker: Netzladung-Fehlalarm** (rapahl-PN): der Daten-Checker meldete „Netzladung übersteigt Gesamtladung", obwohl die Differenz nur ein harmloser Effekt an der Monatsgrenze war (Akku-Nachtladung über Mitternacht). Die Prüfung erfolgt jetzt kumulativ über die gesamte Historie — ein echter Erfassungsfehler wird weiterhin erkannt.

---

## [3.31.8] - 2026-05-22 — Bündel-Release: Speicher-Cockpit-Fix + EcoFlow-Import + WP-Saison-Politur

> 🔧 **Patch-Release.** Behebt einen Absturz der Cockpit-Rubrik „Speicher" (Regression aus v3.31.7), repariert den EcoFlow-PowerOcean-Cloud-Import und setzt vier Feedback-Punkte zum WP-Saisonvergleich um (rapahl-PN).

### Changed

- **WP-Saisonvergleich heizungsbereinigt** (#195, rapahl-PN): Bei getrennter Strommessung rechnet der Saison-Vergleich (Strom & JAZ) jetzt nur noch die Heizung — Warmwasser läuft ganzjährig ~konstant und verwässerte den Heizperioden-Vergleich. Ohne getrennte Messung unverändert der Gesamtwert. Neue Fußzeile nennt Saison-Fenster, Anzahl der Monate und die verwendete Strom-Basis.
- **WP-Saisonvergleich — Darstellung**: vertikale Hilfslinien im Monats-/Saison-Vergleich entfernt (störten im Dark Mode); Summen-Labels größer und in hellem wie dunklem Theme gut lesbar.

### Fixed

- **Cockpit-Rubrik „Speicher" — Absturz behoben** (rapahl-PN): die Speicher-Ansicht im Cockpit zeigte „Ein Fehler ist aufgetreten" und ließ sich nicht öffnen. Regression aus der Etappe-C-UI in v3.31.7 — `get_speicher_dashboard` griff auf das nicht existierende Feld `installationsdatum` zu (das `Investition`-Model hat `anschaffungsdatum`). Behoben + Regressionstest, der den Endpoint jetzt direkt mit einer echten Investition prüft.
- **EcoFlow PowerOcean Cloud-Import: Signaturfehler behoben** (Dirk-PN): signierte Requests scheiterten mit `code=8521 signature is wrong`; Ursache war ein fehlerhaft gesetzter Content-Type-Header. Der Cloud-Import funktioniert damit wieder.

---

## [3.31.7] - 2026-05-21 — Bündel-Release: Prognose-Korrektur + Community-Fehlermeldungen + Backup-Abfrage

> 🔧 **Patch-Release.** Schwerpunkt: die Prognose-Korrektur (Lernfaktor + wetterabhängiges Korrekturprofil) wurde überprüft und auf den zentralen Berechnungs-Layer (ADR-001) gezogen. Dazu feldgenaue Fehlermeldungen beim Community-Teilen (#282), eine Backup-Abfrage vor dem Löschen (#283) und die Cockpit-Kacheln der Speicher-Wirtschaftlichkeit Etappe C (#264).

### Added

- **Speicher-Wirtschaftlichkeit — Etappe C-UI** (#264): die in v3.31.6 (C-Backend) angekündigten Cockpit-Kacheln — dynamischer Ladepreis aus TEP-Stundenwerten, SoC-korrigierter Wirkungsgrad — sind jetzt im Speicher-Dashboard sichtbar.
- **Backup-Abfrage vor destruktiven Aktionen** (#283, PR von stlorenz): Bestätigungsdialog (`DestructiveActionDialog`) mit Backup-Erinnerung vor dem Löschen von Anlage/Komponente; Lösch-Fehler werden im Dialog sichtbar gemacht.

### Changed

- **Lernfaktor-IST über den Berechnungs-Layer** (`live_wetter._filtere_tage`): die IST-Ermittlung für den Lernfaktor nutzt jetzt den SoT-Helper `summe_pv_bkw_kwh` (Whitelist `pv_`/`bkw_`, `core/berechnungen/energie.py`) — dieselbe Quelle wie Daten-Checker und Genauigkeits-Tracking. +5 Akzeptanztests.
- **Investitionen-Dashboards in eigenes Modul** (`api/routes/investitionen/dashboards.py`): verhaltenserhaltender Refactor.

### Fixed

- **Korrekturprofil: Day-Ahead-Stundenprofil bleibt über die Tagesaggregation erhalten** (`aggregate_day`): Das Delete-and-Recreate der `TagesZusammenfassung` rettete bisher nur die fünf Skalar-Prognosefelder — `pv_prognose_stundenprofil` / `solcast_prognose_stundenprofil` fehlten in der Rettungsliste und gingen jede Nacht verloren, die Korrekturprofil-Heatmap blieb dadurch leer. Rettungsliste jetzt als Konstante `_PROGNOSE_FELDER_RETTEN` (alle 7 Prognosefelder). Wirkt vorwärts. +3 Akzeptanztests.
- **Community-Server: Fehler 422 mit Feld-Detail** (#282, SlapJackNpNp): das feldgenaue Pydantic-Detail wird jetzt lesbar in der UI angezeigt statt einer generischen Meldung.
- **Daten-Checker: toter „Beheben"-Link + Zukunfts-Stub-Fehlalarm**: ein Reparatur-Link zeigte auf eine veraltete Route; Tage in der Zukunft wurden als Datenlücke fehlinterpretiert.
- **Lösch-Fehler im `DestructiveActionDialog`** werden im Dialog angezeigt statt still verschluckt.

---

## [3.31.6] - 2026-05-20 — Bündel-Release: E-Mobilitäts-Pool-Konsistenz + Saison-Vergleich + Daten-Checker

> 🔌 **E-Mobilitäts-Sichten zeigen wieder dieselben Zahlen.** junky84 (#262) meldete nach v3.31.5 vier verschiedene Werte für dieselbe evcc-Ladung: Cockpit-E-Auto 4127 kWh / 48 % PV (korrekt), Wallbox-Dashboard 5278 / 38 %, Auswertungen-Komponenten 4130 mit PV 48 % + Netz 85 % = 133 % (mathematisch unmöglich). Ursache: vier Read-Sites poolten E-Auto- + Wallbox-IMD mit feldweisem `max(eauto_X, wb_X)` — drei unabhängige `max()`-Aufrufe für `gesamt`/`pv`/`netz` konnten die Felder aus verschiedenen Quellen mischen, das Tripel war intern inkonsistent. Nur das E-Auto-Dashboard war korrekt (poolt über `compute_emob_pool_attribution` eine ganze Quelle). **Fix:** SoT-Helper `aggregiere_emob_ladung` — die Quelle mit der größeren Heimladung gewinnt die komplette, in sich konsistente Trias (`pv + netz == ladung` garantiert); alle Sichten rufen ihn auf. Plus #195-Abschluss (Saison-Vergleich), #613-Daten-Checker-Fix und ein PVGIS-Systemverluste-Drift-Refactor.

### Added

- **Wärmepumpe: Saison-Toggle im Monatsvergleich** (#195 Punkt 2): Das WP-Cockpit kann den Monatsvergleich auf Saison-Fenster umstellen — neue `SAISON_FENSTER`-Konstante in `lib/constants.ts` (Winter Nov–Feb / Heizperiode Okt–Apr / Sommer Jun–Aug). Achsen-Toggle Monate/Saison + Fenster-Selektor, Saison-Instanzen auf der X-Achse, kein Jahresfilter (Cockpit-vs-Auswertung-Grenze).
- **Auswertung: Vergleichsjahr-Absolutwert in der Tabelle** (#195 Punkt 1): Die Auswertungs-Tabelle zeigt das Vergleichsjahr zusätzlich als absoluten kWh-/€-Wert statt nur als Differenz zum aktuellen Jahr.
- **Energieprofil-Tagestabelle: Komponenten-Spalten**: zusätzliche Spalten für die einzelnen Komponenten (Speicher, Wärmepumpe, E-Mobilität) in der Tages-Tabelle.
- **Speicher-Wirtschaftlichkeit — Etappe C-Backend** (#264, PR [#278](https://github.com/supernova1963/eedc-homeassistant/pull/278) von stlorenz, maintainer-rebased + reviewt): dynamischer Ladepreis aus den TEP-Stundenwerten + SoC-korrigierter Wirkungsgrad statt Parameter-Durchschnitt. Die Frontend-KPIs (Etappe C-UI) folgen in einem Nachgang-Release. Zwei Review-Nits gefixt (Funktionen aus dem Import-Block geholt, stilles `except: pass` → `logger.warning`).

### Changed

- **E-Mobilitäts-Pool zentralisiert** (#262): neuer SoT-Helper `aggregiere_emob_ladung` in `services/eauto_wirtschaftlichkeit.py` ersetzt feldweises `max()` in vier Sichten (Wallbox-Dashboard, Komponenten-Zeitreihe, Cockpit-Übersicht, `aktueller_monat._collect_saved_data`). Die Quelle mit der größeren Heimladung gewinnt die komplette `(gesamt, pv, netz)`-Trias — `pv + netz == ladung` ist garantiert. Externe Ladung kommt paarweise (kWh, €) aus der Quelle mit den höheren Extern-Kosten. Das E-Auto-Dashboard bleibt unverändert (`compute_emob_pool_attribution`, selbe use-wb-pool-Entscheidung → konsistent). Netto −155 Zeilen duplizierte Pool-Logik. Neun neue Tests in `test_emob_pool_konsistenz.py`.
- **PVGIS-Systemverluste zentralisiert**: `DEFAULT_SYSTEM_LOSSES = 0.14` war 5× definiert, die Auflöse-Zeile `pvgis.system_losses / 100 if … else …` stand 6× parallel. Zentralisiert in `services/pv_orientation.py` (`DEFAULT_SYSTEM_LOSSES` + `resolve_system_losses(pvgis)`). Verhaltenserhaltender Refactor, vier neue Unit-Tests. Memory-Linie `feedback_aggregations_drift`.
- **PV-Prefix-Whitelist im Frontend konsolidiert**: die PV-Komponenten-Prefix-Liste wird im Frontend jetzt aus einer Stelle gelesen — Analogon zum Backend-Berechnungs-Layer (ADR-001).
- **`docs/KONZEPT-WALLBOX-EAUTO.md` aktualisiert**: Pool-Konsolidierung dokumentiert; Phase 2 in **2a** (Feldzuordnung geradeziehen, schulden-getrieben — Trigger durch das evcc-Import-Churn gefeuert) und **2b** (Vehicle-Sensor-Mapping, feature-getrieben) gesplittet; neuer Abschnitt »Phase-2-Trigger«.

### Fixed

- **E-Mobilität: vier Sichten zeigten verschiedene Lade-Zahlen** (#262, junky84): siehe Intro — feldweises `max()` über getrennte E-Auto-/Wallbox-Töpfe erzeugte intern inkonsistente `(gesamt, pv, netz)`-Tripel, in Extremfällen PV-Anteil > 100 %. Behoben durch den `aggregiere_emob_ladung`-Gewinner-Pool.
- **Daten-Checker: stillgelegte Investition im LTS-Check** (#613, MartyBr-Forum-Meldung): `_check_sensor_mapping_lts` flaggte den kWh-Sensor einer stillgelegten Investition weiter als „nicht in HA-LTS". Der #608-Stilllegungs-Sweep aus v3.31.5 hatte diesen Pfad übersehen, weil die Funktion das `sensor_mapping`-JSON-Dict iteriert statt `anlage.investitionen`. Fix + Akzeptanztest.
- **UI: SOLL/IST → IST/SOLL Label-Korrektur** (rapahl-PN): vertauschte Spalten-Beschriftung korrigiert.

---

## [3.31.5] - 2026-05-19 — Bündel-Release: BKW-Doppelzählung weg + Berechnungs-Layer (ADR-001) + Tester-Bündel

> 🧮 **Strukturelle Antwort auf die BKW-Drift-Klasse.** Rainer-PN 2026-05-19 zeigte eine systematische IST-Über-Erfassung (~5-8 % Bias gegenüber Solcast) bei einer Anlage mit Balkonkraftwerk. Diagnose: `TV_SERIE_CONFIG["balkonkraftwerk"].kategorie = "pv"` ließ den Live-Tagesverlauf-Service den BKW-Wert unter `pv_<inv_id>` akkumulieren, der HA-LTS-Boundary-Aggregator nutzt aber `bkw_<inv_id>`. Bei Schema-Mismatch blieben beide Keys parallel in `komponenten_kwh`, alle Konsumenten mit Whitelist `("pv_", "bkw_")` zählten BKW doppelt. **Strukturelle Lösung statt Pflaster:** Live-Σ-Riemann-Akkumulation für `komponenten_kwh` ist im HA-Add-on-Modus jetzt komplett deaktiviert — `boundary_kwh` (HA-LTS) ist alleiniger Schreiber. Damit ist die ganze Bug-Klasse strukturell weg, nicht nur das eine Symptom. Plus: neuer Berechnungs-Layer `backend/core/berechnungen/` als SoT für Aggregat-Helper, Pytest-Konformitäts-Test blockiert künftige Whitelist-Duplikate, Pflicht-Invariante im Aggregator loggt Schreib-Drift sofort.

### Added

- **Berechnungs-Layer `backend/core/berechnungen/` als Single Source of Truth** ([ADR-001](docs/ADR-001-BERECHNUNGS-LAYER.md), [Konzept](docs/KONZEPT-BERECHNUNGS-LAYER.md)): Whitelist-Konstanten, Σ-Helper und Konsistenz-Invarianten leben jetzt in einem eigenen Layer statt verteilt über Domain-Module. Submodule:
  - `energie.py` — `PV_KOMPONENTEN_PREFIXE` + `summe_pv_bkw_kwh` (SoT für Aggregat aus `TagesZusammenfassung.komponenten_kwh`)
  - `invarianten.py` — `pruefe_tep_tz_konsistenz` / `assert_tep_tz_konsistent` (Σ Hourly == Daily über `pv_kw` ↔ `komponenten_kwh[pv_*, bkw_*]`)
  - `__init__.py` mit Re-Exports
  Erster migrierter Konsument: `services/daten_checker.py` (`_summe_pv_bkw_kwh` ist jetzt ein Re-Import statt eigener Definition). Weitere Konsumenten (prognosen.py, repair.py u. a.) werden step-by-step beim nächsten Touch migriert — siehe `INLINE_PATTERN_GRANDFATHERED` in `tests/test_berechnungs_layer_konformitaet.py`.
- **Pytest-Konformitäts-Test** (`tests/test_berechnungs_layer_konformitaet.py`): drei Schichten Pflichten-Test — `("pv_", "bkw_")`-Tuple und `startswith("pv_") or startswith("bkw_")`-Inline-Pattern dürfen nur in `core/berechnungen/` stehen (mit Grandfathered-Whitelist für die bekannten Altlasten); zusätzlich „veraltete Grandfathered-Einträge"-Check, der schlägt an, wenn eine Datei das Pattern nach Migration nicht mehr enthält — verhindert Karteileichen.
- **Pflicht-Invariante im Aggregator** (`energie_profil/aggregator.py::aggregate_day`): nach jedem Schreib-Lauf wird `pruefe_tep_tz_konsistenz(tep_rows, zusammenfassung.komponenten_kwh)` aufgerufen. Verletzung wird als Warning geloggt — kein Tag wird zurückgehalten, aber Drift ist im Add-on-Log sofort sichtbar (statt erst Wochen später durch Anwender-Meldungen).
- **Daten-Checker: PR-Plausibilitäts-Check für PV-Doppelerfassung** (rapahl-PN, Etappe-6-Erweiterung): neuer Check `_check_pv_ueber_erfassung` meldet, wenn die Performance Ratio an ≥ 3 von ≥ 20 % der PR-Tage über 1,05 liegt oder der spezifische Tagesertrag > 7 kWh/kWp an ≥ 3 Tagen erreicht. Diagnose-Charakter, keine automatische Reparatur. 10 Akzeptanztests in `test_daten_checker_pv_ueber_erfassung.py`. Memory-Linie `feedback_grenze_externe_daten_diagnose`.
- **Prognose-Vergleichs-Tab: 4 Tage zurück + 3 Tage vorwärts** (rapahl-PN): die 7-Tages-Tabelle zeigt jetzt 4 historische Tage (aus `genauigkeit.tage` mit echtem IST + gespeicherten Prognosen) plus 3 zukünftige Tage. Trennlinie zwischen Vergangenheit und Zukunft; historische Zeilen ohne Wetter-Icon/Solcast-Konfidenzband.
- **Cloud-Import: Backend-Fehler im Wizard sichtbar**: bei fehlgeschlagenem Verbindungstest zeigt der Wizard jetzt den vollen `testResult.fehler`-Text in einem roten Detail-Block mit Monospace-Schrift — bisher wurde die konkrete API-Antwort verschluckt zugunsten eines generischen „Verbindung fehlgeschlagen". EcoFlow-PowerOcean-Connector zusätzlich mit ausführlichem Diagnose-Logging vor jedem Return (HTTP-Status, Body-Auszug, Hersteller-`code`/`message`). Trigger: Dirk-PN.

### Changed

- **Aggregator-Mode-Switch: Live-Σ-Riemann nur noch im Standalone-Modus** (`energie_profil/aggregator.py:358-368`): die Live-Akkumulation pro Stunde (`kW × 1h = kWh` über `werte`-Keys) läuft im HA-Add-on-Modus (`kwh_source_label == "external:ha_statistics:hourly"`) NICHT mehr — `boundary_kwh` (HA-LTS) ist alleiniger Schreiber für `komponenten_kwh`. Etappe-4-Komplettierung: der Riemann-Pfad-Rückbau, der im ursprünglichen v3.31.0-Release laut Konzept-Doc geplant war, ist jetzt strukturell vollzogen. Im Standalone-Modus (kein HA-LTS) bleibt der Live-Pfad als Pfad-2-Fallback aktiv.
- **`docs/KONZEPT-DATENPIPELINE.md` Abschnitt 3.5 ergänzt** um Berechnungs-Layer-Verweis; **`docs/KONZEPT-COUNTER-DAILY-DRIFT.md`** als Sub-Konzept des Berechnungs-Layers verankert; **`docs/KONZEPT-DATENCHECKER-KONSISTENZ.md`** mit Querverweis, dass Achse-A/B/C-Refactor `core/berechnungen` benutzen MUSS.

### Fixed

- **Stilllegungs-Filter in kWp-Summe + Sensor-Mapping-Check + Inbetriebnahme-Monat** (#608, Steffen2-PN): die stillgelegte Dachanlage trotz Stilllegungs-Datum (a) wurde in der Modul-kWp-Summen-Anzeige des Daten-Checkers mitgezählt → führte zur Warnung „PV-Module kWp stimmt nicht mit Anlagenleistung überein", obwohl die echte Anlagenleistung korrekt war, (b) wurde im Sensor-Mapping-Vollständigkeits-Check als „fehlt" gemeldet, (c) der Inbetriebnahme-Monat (Monat vor Stilllegung) wurde als Datenlücke fehlinterpretiert. Alle drei behoben durch `ist_aktiv_an(heute)`-Filter analog zu den Read-Sites in v3.29.x. Acht Akzeptanztests in `test_daten_checker_stilllegung.py` + `test_daten_checker_vorjahr_inbetriebnahme.py`.
- **Daten-Checker: Reparatur-Werkbank-Link im Provenance-Konflikt-Eintrag** (Steffen2-PN): das Daten-Checker-Eintrag „14 Felder mit mehreren Quellen in den letzten 30 Tagen — der Resolver hat schon entschieden, die Reparatur-Werkbank kann sie aufdröseln" enthielt bisher keinen `link`, deshalb keinen „Beheben"-Button. Link auf `/einstellungen/energieprofil` (Reparatur-Werkbank ganz unten) jetzt im CheckErgebnis.
- **Daten-Checker: Route-Korrektur `/aussichten/energieprofil` → `/einstellungen/energieprofil`** an drei Stellen (Reparatur-Werkbank-Link aus dem vorherigen Fix + zwei ältere Counter-Spike-/Drift-Links). Die alte Route gibt's nicht — die SubTabs-Kategorie ist „Daten" unter Einstellungen.
- **E-Mobilität: Pool-vs-Komponente-Drift bei evcc-Setups** (#260 Folge nach v3.31.3): die Cockpit-Komponenten-Sicht und die Aktueller-Monat-Sicht zeigten unterschiedliche Ersparnisse für dasselbe E-Auto bei mehreren Wallbox-Sessions pro Monat. Ursache: inkonsistente Aggregation über mehrere Komponenten — der Pool-Helper aus #260 wurde nicht überall sauber durchgereicht. Fünf neue Akzeptanztests in `test_emob_pool_komponenten.py`.
- **Custom-Import: Einheits-Konvertierung Wh/MWh → kWh + Legacy-Top-Level-Targets** (#229 JanKgh-Folge): CSV-Import-Pipeline konvertiert jetzt automatisch von Wh oder MWh nach kWh, falls die Quelldatei nicht-kWh-Einheiten verwendet (typisch z. B. bei Solarmanager-Exporten). Zusätzlich akzeptiert die Mapping-Logik auch ältere Top-Level-Spalten-Namen aus früheren eedc-Versionen, ohne Wizard-Rename. Vier neue Akzeptanztests in `test_custom_import_einheit_non_energy.py`.

### Removed

- **`backend/services/daten_checker.py:_summe_pv_bkw_kwh` als eigene Definition**: ersetzt durch Re-Import aus `backend.core.berechnungen` (semantisch identisch, Migration zum SoT-Layer). Externe Aufrufer ändern sich nicht.

### Internal

- **Test-Aufräumen Plan E**: zentrale `db`-Fixture in `backend/tests/conftest.py`, 18 Test-Dateien migriert, alle `_session_ctx`-Definitionen + 14 Standalone-`__main__`-Runner entfernt. Sonderfälle: `test_repair_orchestrator.py` hat lokale `autouse`-Fixture für `_reset_state_for_tests()`, `test_lts_aggregator_konsistenz.py` nutzt inline `db=None` (LTS-Pfad braucht keine echte Session). −712 Netto-Zeilen.
- **Konzept-Pflege**: 7 abgeschlossene Konzepte ins `docs/archive/` verschoben (`KONZEPT-ETAPPE-4-HA-LTS-SOT`, `KONZEPT-ETAPPE-6-DRIFT-ANZEIGE`, `KONZEPT-INFOTHEK`, `KONZEPT-KORREKTURPROFIL`, `KONZEPT-MQTT-GATEWAY`, `KONZEPT-PROGNOSEQUELLEN-WAHL`, `KONZEPT-STROMPREIS-MITSCHRIFT`), Forum-Post-Entwurf `forum-post-iobroker-mqtt.md` ebenfalls archiviert, `KONZEPT-ENERGIEPROFIL-3C` ins Archiv nach Re-Audit (Drift-Befunde gegen 3d/4/5/6-Stand geprüft). Neu: `KONZEPT-DATENCHECKER-KONSISTENZ.md` als geparktes Konzept für die Daten-Checker-Aufräumung.
- **Roadmap (#110)** auf v3.31.5-Stand aktualisiert: neuer Geplant-Punkt „Berechnungs-Layer step-by-step Migration", neuer In-Arbeit-Punkt „Komponenten-Drill-down in der Energieprofil-Tagestabelle" (Rainer-Wunsch).

### Tests

- 256/256 grün (253 Stand vor Session + 3 neue Konformitäts-Tests; die 2 obsoleten BKW-Pflaster-Tests sind im strukturellen Fix gelöscht worden).

### Verhalten / Memory

Heute zweimal in die „User verdächtigen statt eigenen Code prüfen"-Falle gelaufen (Steffen2 + Rainer) bevor Code-Audit den BKW-Bug fand. Neue Memory-Linie `feedback_eigenen_code_zuerst` adressiert das Reflex-Pattern; `feedback_aggregations_drift` erweitert um Write-Side-Variante (zwei parallele Schreiber auf demselben JSON-Feld); `feedback_step_by_step_berechnungs_layer` formalisiert die Migrations-Disziplin.

---

## [3.31.4] - 2026-05-18 — Bündel-Release: Security-Hardening + Speicher-Etappe A/B + Tester-Beiträge

> 🔐 **Sicherheits-Härtung als Schwerpunkt.** Drei Schichten gegen typische Angriffsvektoren in selbst-gehosteten Apps: Credential-Maskierung deny-by-default, SSRF-Schutz im Connector-Test gegen Loopback/Link-Local/Multicast-Ziele (inkl. DNS-Rebinding), und das `curl | bash`-Anti-Pattern aus der Setup-Anleitung ersetzt durch `curl → less → bash`. Plus zwei Etappen aus Stefans Speicher-Konzept (`laedt_aus_netz`-Schalter + Speicher-Wirtschaftlichkeit mit PV-/Netz-Anteil), klarere README für den Standalone-Modus, und ein Pool-Drift-Fix für die E-Mob-Auswertung beim evcc-Import.

### Security

- **Credential-Maskierung deny-by-default** (PR #275): Provider-aware Detection für sensible Eingabefelder — alles mit `type="password"` plus Substring-Heuristik für ungewöhnlich benannte Token-Felder. Eingaben in Logs, Debug-Outputs und Connector-Test-Antworten werden vor der Weitergabe maskiert. Neun Akzeptanztests, deny-by-default-Linie statt allow-list (sicher ist sicher; lieber ein nicht-sensibles Feld maskieren als ein sensibles übersehen).
- **SSRF-Schutz im Connector-Test** (PR #275): `/api/connector/test` und `/api/connector/setup` lösen jetzt vor jedem ausgehenden Request den Ziel-Hostnamen via `getaddrinfo` auf und prüfen jede IP mit `ipaddress.is_loopback / is_link_local / is_multicast / is_unspecified / is_reserved`. Loopback-Ziele (127.0.0.0/8, ::1), Link-Local (169.254.0.0/16), Multicast, IPv4/IPv6-Mapped-Adressen und private Bereiche werden geblockt. DNS-Rebinding-Schutz durch Re-Resolve direkt vor dem Connect. 21 Akzeptanztests.
- **`curl | bash` aus der Setup-Anleitung entfernt** (PR #275): `docs/SETUP_DEVMACHINE.md` zeigt jetzt explizit das `curl -fsSL -o /tmp/eedc-setup.sh … && less /tmp/eedc-setup.sh && bash /tmp/eedc-setup.sh`-Pattern mit Sicherheitshinweis zur Begründung. Pipe-to-shell wird in keiner offiziellen Anleitung mehr empfohlen.
- **Setup-Skript ohne automatische Maintainer-Identität**: `docs/setup-devmachine.sh` setzte bei fehlender Git-Identität automatisch Platzhalter-Werte des Maintainers (`git config --global user.name "supernova1963"`). Das ist raus — Skript gibt jetzt nur einen Hinweis mit Platzhalter-Anleitung aus, jeder Nutzer trägt seine eigene Identität ein.
- **Standalone-README: LAN-Only + kein Auth-Layer-Roadmap-Versprechen** (PR #276 + #277): `README.md` macht für den Standalone-Modus explizit klar, dass die App als LAN-Only-Setup konzipiert ist. Für öffentliche Erreichbarkeit verweist sie auf etabliertes Standard-Tooling (nginx + Basic-Auth, OAuth2-Proxy, Cloudflare Access, Tailscale Funnel). Ein eigener Auth-Layer im Container ist bewusst *nicht* auf der Roadmap — Standard-Werkzeuge lösen das Problem nachweislich besser als eine selbstgebaute In-App-Implementierung. Im HA-Add-on-Modus liegt der Auth-Layer bei Home Assistant. Memory-Linie `feedback_externer_druck_reflex.md`.

### Added

- **Speicher Etappe A: Erfassungs-Schalter `laedt_aus_netz`** (PR #269 stlorenz, Issue #264): Neuer Boolean pro Speicher-Investition, ob der Speicher überhaupt aus dem Netz lädt (z. B. für Arbitrage bei dynamischen Tarifen) oder rein PV-getrieben. Erfassung im Investitions-Formular, Default false. Vorbereitung für die Wirtschaftlichkeits-Berechnung in Etappe B.
- **Speicher Etappe B: Wirtschaftlichkeit mit PV-/Netz-Anteil** (PR #271 stlorenz, Issue #264): ROI-Berechnung berücksichtigt jetzt den PV- vs. Netz-Anteil der Speicher-Ladung. Bisher wurden alle Ladungen mit Bezugspreis bewertet — bei Speichern mit Netzladung (z. B. Tibber-Optimierung) realistisch, bei rein-PV-Speichern systematisch zu negativ. Drift-Audit-D-Wrapper konsolidiert die Aggregations-Logik mit den anderen Wirtschaftlichkeits-Pfaden. Memory-Linie `feedback_aggregations_drift.md`. Etappe C (TEP-Lookups + SoC-korrigierter η) folgt mit dem nächsten Release zusammen mit dem Frontend-PR.

### Fixed

- **E-Mobilität: `ladung_netz_kwh`-Drift bei evcc-Import** (#262 junky84-Folge nach v3.31.3): junky84 meldete nach v3.31.3 weiter unstimmige Werte — Wallbox-Dashboard zeigte PV-Anteil 100 %, Netzladung 0 kWh trotz Netzbezug-Werten. Ursache: evcc-CSV liefert nur `total` + `pv-%`, das abgeleitete Feld `ladung_netz_kwh` wurde beim Import nie geschrieben. Acht Read-Sites (Investitionen, Cockpit-Übersicht, Cockpit-Komponenten, aktueller Monat, HA-Export, PDF-Jahresbericht u. a.) lasen das fehlende Feld direkt und kamen auf 0. Fix per zwei Schichten: (1) Import-Site in `data_import.py` schreibt jetzt `ladung_netz_kwh = max(0, total - pv)` mit, (2) neuer SoT-Helper `get_emob_pv_netz_kwh()` in `field_definitions.py` mit demselben Fallback für Bestandsdaten, alle acht Read-Sites umgestellt. Mathematisch validiert gegen Gernots HA-Template-Helper (`evcc_helper_pv_charged_kwh` + `evcc_helper_net_charged_kwh` machen exakt dieselbe Rechnung) und gegen reale evcc-CSV (5 Sessions, 80 kWh total, Σ PV 65,97 kWh, abgeleitet Netz 14,05 kWh). Fünf neue Akzeptanztests in `test_dashboards_evcc_pool_fallback.py`. Memory-Linie `feedback_aggregations_drift.md`.
- **EVCC-Import: DE- und EN-Header-Erkennung + Sprach-Hinweis** (PR #268 stlorenz): EVCC-CSV-Export ist je nach Web-UI-Sprache deutsch oder englisch (`Sitzungen` vs. `Sessions`, `Energie` vs. `Energy`). Der Parser akzeptierte bisher nur die deutsche Variante. Beide Sprachen werden jetzt erkannt; bei dritter Sprache erscheint ein klarer Hinweis im Import-Dialog.
- **E-Mobilität: `ist_dienstlich`-Feld String-Drift-tolerant lesen** (PR #270 stlorenz): Der Boolean-Schalter „Dienstwagen" wurde teils als String (`"true"`/`"false"`), teils als echtes Bool gelesen. Aufrufer in der Ersparnis-Berechnung interpretierten String-Werte teils unterschiedlich. Helper `_ist_dienstlich(inv)` normalisiert beide Repräsentationen.
- **Daten-Checker: NameError nach Merge-Konflikt #270 ↔ v3.31.3** (PR #274): Beim Merge des `ist_dienstlich`-Refactors wurde im neu hinzugefügten WP-Block die `param`-Variable referenziert, die im selben PR durch den Refactor weggefallen war (NameError, 500 auf `/api/check`). Drei Akzeptanztests verifizieren, dass der gesamte Check-Pfad durchläuft.
- **Cockpit: Spezifischer Ertrag bei „alle Jahre" + historischen Größenänderungen** (PR #273 stlorenz): KPI „Spezifischer Ertrag" im „alle Jahre"-Filter mittelte über die aktuelle Anlagenleistung — bei nachträglichen Erweiterungen (Modul hinzu) wurde die Anzeige für historische Jahre verzerrt. Mittlung läuft jetzt periodengenau pro Jahr gewichtet über die zum jeweiligen Zeitpunkt installierte Leistung.

### Changed

- **`eedc/eedc.db` nicht mehr getrackt + DB global gitignoret**: Die SQLite-Stub-Datei (0 Bytes, Release-Skript-Artefakt aus v3.19.0) wurde aus dem Repository entfernt und `*.db` / `*.sqlite` / `*.sqlite3` global in `.gitignore` ergänzt — verhindert versehentliches Einchecken künftiger DB-Stände. Plus: WAL/SHM-Backup-Begleitdateien (`*.db-wal`, `*.db-shm`) ebenfalls ignoriert (PR #272 stlorenz).
- **SFML-Stats-Plattform-Korrektur im archivierten Konzept** (`docs/archive/KONZEPT-ML-PROGNOSE.md`): In der archivierten Datei stand, SFML Stats laufe nur auf x86_64 und EEDC schließe die Lücke auf ARM/Pi. Beide Aussagen sind falsch — SFML Stats läuft auf beiden Architekturen. Korrektur-Block am Dateianfang mit Datum und Hinweis-Quelle (SFML-Entwickler Tom-HA / Zara-Toorox).

### Tests

220/220 grün — Suite wächst von 151 auf 220 (+ 69 neue Akzeptanztests durch die Security-Hardening-Pakete, Etappe A/B-Tests und die evcc-Drift-Akzeptanz).

### Hinweis für Anwender

Repo-Klone vor diesem Release: durch History-Rewrites im Laufe des Tages (Bereinigung von Artefakten aus älteren Releases) divergieren bestehende lokale Klone. Wer den Repository-Stand neu pullen will, sollte `git fetch && git reset --hard origin/main` ausführen. Für HACS-Add-on-Nutzer ohne lokalen Klon ändert sich nichts — das Update zieht den aktuellen Tag-Inhalt.

---

## [3.31.3] - 2026-05-18 — Bündel-Release: Aggregations-Drifts + Forum-Bugfixes + Pfad-Hinweise

> 🛠 **Bündel-Release nach drei Etappen-Tagen.** Sieben anwender-relevante Bugfixes aus Forum + Issues, dazu eine konsistente Korrektur veralteter UI-Pfad-Hinweise. Schwerpunkt: drei Aggregations-Drifts in unterschiedlichen Verbrauchsbereichen (E-Mob-Ersparnis, Live-Tagesverlauf-Strompreis, Wallbox+E-Auto-Dashboards), zwei Robustheits-Fixes (Cloud-Import-Whitespace, getrennte WP-Strommessung), zwei stlorenz-Beiträge (Cockpit-Genauigkeit, HA-Backup-Konsistenz).

### Fixed

- **E-Mobilität-Ersparnis: externe Lade-Kosten in Cockpit-Pfaden mitrechnen** (#260 NongJoWo): Die Cockpit-Übersicht und der aktuelle Monatsbericht zeigten ~273 € weniger Ersparnis als das E-Auto-Dashboard. Ursache: drei Aufrufer von `berechne_eauto_ersparnis` hatten `ladung_extern_euro=0.0` hartcodiert, das E-Auto-Dashboard zog den Wert korrekt aus den evcc-Portal-Daten. Alle drei Aufrufer ziehen jetzt denselben Wert. Memory-Linie `feedback_aggregations_drift.md`.
- **Cloud-Import: Whitespace in Credentials trimmen** (#261 FrodoVDR): API-Keys aus Hersteller-Portalen werden oft mit Leerzeichen am Anfang oder Ende kopiert, SolarEdge antwortet darauf mit 403. Frontend und Backend trimmen jetzt User-Eingaben für Cloud-Import-Credentials vor dem API-Call. Memory-Linie `feedback_credential_whitespace.md`.
- **Daten-Checker: WP mit getrennter Strommessung nicht als fehlend melden** (Forum dietmar1968): Der Daten-Checker prüfte hartcodiert das Legacy-Feld `stromverbrauch_kwh` und meldete eine fehlende Konfiguration, auch wenn `stromverbrauch_heizen_kwh` + `stromverbrauch_warmwasser_kwh` korrekt gemappt waren (getrennte Strommessung seit v3.25.x). Prüfung respektiert jetzt den `getrennte_strommessung`-Pfad.
- **Live-Tagesverlauf: Strompreis-Carry-Forward statt EPEX-Sprung** (#267 rilmor-mhrs): Bei Tibber liefert HA alle 15 Minuten ein Step-Update — der Live-Tagesverlauf prüfte aber pro 10-Min-Slot, ob ein Update *innerhalb* des Slots liegt. Jeder zweite oder dritte Slot ohne Update fiel auf den EPEX-Börsenpreis-Fallback (~8-12 ct statt ~35 ct Tibber-Endkundenpreis) — die Strompreis-Linie zeigte hässliche Sprünge. Tibber/aWATTar sind Step-Funktionen: bei leerem Slot wird jetzt zuerst der letzte bekannte Wert weitergeführt, EPEX nur noch als finaler Fallback ohne jeden Tagespunkt. Fünf Akzeptanztests.
- **Wallbox- und E-Auto-Dashboards: Pool-Fallback bei evcc-Import** (#262 junky84): evcc-Portal-Import schreibt Ladedaten architektonisch in die Wallbox-Investition (km gehen zum E-Auto). Die Cockpit-Übersicht griff das korrekt via Pool-Max ab, aber Wallbox- und E-Auto-Dashboards lasen jeweils nur den eigenen Pfad — bei junky84 zeigten beide „Noch keine Ladedaten vorhanden" trotz 4,12 MWh im Pool. Beide Dashboards bekommen jetzt dieselbe Pool-Max-Logik wie Cockpit; E-Auto-Dashboard verteilt Wallbox-Aggregate km-anteilig auf die E-Autos. Premium-Setups mit separat gepflegten E-Auto-Sensoren unverändert.
- **Cockpit: Spezifischer Ertrag periodengenau & jahresverlauf-gewichtet** (PR #265 stlorenz): KPI „Spezifischer Ertrag" bezog sich bisher auf die Anlagenleistung zum Stichtag — bei nachträglichen Erweiterungen (Modul hinzu, Speicher dazu) verzerrte das die Anzeige. Der spezifische Ertrag wird jetzt periodengenau gewichtet pro Monat über den Jahresverlauf bestimmt.
- **HA-Backup-Konsistenz via WAL-Checkpoint** (PR #266 stlorenz): Vor jedem Snapshot-Export wird jetzt ein WAL-Checkpoint geschrieben — verhindert die Race-Condition, in der HA-Backups eine inkonsistente DB-Datei aufnehmen konnten.
- **Daten-Checker Drift-Knopf: konkrete Vorher/Nachher-Anzeige im Toast** (PN dietmar1968): „Tag reparieren" gab bisher pauschal „OK" zurück, auch wenn `aggregate_day` inhaltlich nichts geändert hatte (z. B. weil HA-LTS für einen der gemappten PV-Sensoren keine `sum`-Spalte hat — die Riemann-Summe aus dem Live-Tagesverlauf wird dann nicht durch HA-LTS-Boundaries überschrieben, die Drift bleibt). Endpoint liefert jetzt `pv_kwh_alt` + `pv_kwh_neu` mit derselben Aggregations-Logik wie der Drift-Check. Frontend zeigt drei Toast-Varianten: tatsächliche Änderung („PV 71,8 → 67,6 kWh"), unveränderter Wert mit Sensor-Mapping-Hinweis, oder Fallback ohne Werte (frische Aggregation ohne vorherige Zusammenfassung). Memory-Linie `feedback_daten_checker_kein_akzeptiert.md`.

### Changed

- **UI-Pfad-Hinweise konsistent korrigiert**: Hinweistexte im Monatsabschluss-Wizard, in der Daten-Checker-Drift-Liste und in den Release-Notes verwiesen auf einen nicht existierenden Menüpunkt „Wartung". Korrekt: „Einstellungen → Daten → Energieprofil → Reparatur-Werkbank". Elf Stellen synchron gefixt (Frontend-Wizard, Backend-API-Response, Daten-Checker-Hinweis, CHANGELOG, WAS-IST-NEU, KONZEPT-Doku, In-App-Hilfe via sync-help.sh). Außerdem ein „Aussichten → Energieprofil"-Tippfehler korrigiert (richtig „Auswertungen").

### Tests

151/151 grün — bestehende Suite, keine neuen Tests dazu/entfernt.

---

## [3.31.2] - 2026-05-17 — Hotfix: „Tag reparieren"-Knopf in Daten-Checker

### Fixed

- **Reparatur-Knopf erscheint jetzt wirklich**: In v3.31.1 wurde der neue Per-Tag-Reparatur-Knopf in der Drift-Anzeige des Daten-Checkers nicht angezeigt — stattdessen kam der alte „Beheben"-Link, der nur zum Tag im Energieprofil-Tab springt. Ursache: das API-Response-Schema (`CheckErgebnisResponse` in `backend/api/routes/daten_checker.py`) wurde nicht um die neuen Felder `action_kind`/`action_params`/`action_label` erweitert, Pydantic filterte sie raus. Mit v3.31.2 kommen die Felder durch — Frontend rendert wie geplant den „Tag reparieren"-Knopf neben jedem Drift-Eintrag.
- **Schutz gegen Wiederholung**: neuer Akzeptanz-Test `test_daten_checker_schema_durchreichung.py` prüft per Reflection, dass jedes Feld der internen `CheckErgebnis`-Dataclass auch im Pydantic-Response-Schema existiert. Künftige Felder-Erweiterungen können nicht mehr stillschweigend rausgefiltert werden.

### Hinweis für Anwender

Wer v3.31.1 bereits installiert hat: einmal aktualisieren, dann erscheint der Reparatur-Knopf wie versprochen. Wer den Workaround genutzt hat („Beheben"-Klick → Reload-Knopf im Energieprofil): das hat funktional dasselbe erreicht, war nur ein Klick mehr.

---

## [3.31.1] - 2026-05-17 — Etappe 6: Per-Tag-Drift-Anzeige + Reparatur

> 🔍 **Sichtbar machen, was Etappe 4 erst möglich gemacht hat.** v3.31.0 hat die Architektur auf HA-Statistics umgestellt — neue Tage werden sauber aus HA-LTS aggregiert, bestehende Tage bleiben aber auf ihren alten Werten (Auto-Vollbackfill ist additiv, schützt manuelle Korrekturen). v3.31.1 zeigt jetzt im Daten-Checker pro Tag, wo dein eedc-Wert vom HA-Statistics-Wert abweicht, und legt einen „Tag reparieren"-Knopf direkt neben jeden Eintrag.

### Added

- **Daten-Checker-Kategorie *„Datenquelle – Drift zu HA-Statistics"***: vergleicht die PV-Tagessumme der TagesZusammenfassung mit der HA-Statistics-Tagessumme der letzten 90 Tage. Tage mit Drift bekommen pro Tag einen INFO-Eintrag mit eedc-Wert, HA-Wert und Differenz in kWh und Prozent. Direkt daneben ein „Tag reparieren"-Knopf, der den bestehenden `/reaggregate-tag`-Endpoint aufruft. Schwelle: ≥ 2 kWh UND ≥ 5 % Abweichung gleichzeitig (Boundary-Rauschen wird unterdrückt). Liste auf die 20 Tage mit größtem |Δ| begrenzt. Bewusst kein Sammel-Reparatur-Knopf in der Liste — für mehrere Tage gibt es weiterhin `Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Bereich neu aggregieren`.
- **`CheckErgebnis`-Felder für Inline-Reparatur-Aktionen**: `action_kind`, `action_params`, `action_label`. Rückwärtskompatibel — bestehende Check-Kategorien lassen die Felder leer.

### Changed

- **Daten-Checker-Frontend rendert Reparatur-Knöpfe für `action_kind="reaggregate_day"`-Einträge**. Beim Klick wird der reaggregate-Tag-Endpoint aufgerufen, ein Erfolgs-/Fehler-Toast erscheint, und der Daten-Checker lädt neu. Drift-Einträge verschwinden dadurch automatisch, wenn der Tag jetzt unter der Schwelle liegt.

### Hinweis für Anwender

Direkt nach dem Update v3.31.0 (gestern) standen deine *bestehenden* Tages-Werte noch auf ihren alten Mix-Source-Werten — neue Tage wurden ab sofort sauber aus HA-Statistics aggregiert. v3.31.1 macht jetzt sichtbar, welche bestehenden Tage signifikant abweichen, und bietet pro Tag einen sicheren Reparatur-Pfad ohne Massen-Aktion. Liste leer → alles sauber, kein Handlungsbedarf.

### Konzept-Dokumentation

`docs/KONZEPT-ETAPPE-6-DRIFT-ANZEIGE.md` mit Architektur-Detail, Schwellen-Begründung, vermiedenen Anti-Patterns (kein „Akzeptiert"-Button, kein Sammel-Heiler-Knopf, kein Lösch-Pfad).

### Tests

Suite wächst von 125 auf 133 Tests:

- 8 neue Tests für `_check_datenquelle_drift` (Schwellen-Logik, Sortierung, Max-20-Cap, Inbetriebnahme-Edge-Case, HA-LTS-Fallback, leere Anlage)

---

## [3.31.0] - 2026-05-17 — Etappe 4+5: HA-Statistics als Source-of-Truth

> 🎯 **Konsistenz der Energie-Aggregate erzwungen.** Drei Sichten auf denselben Tag (Genauigkeits-Tracking IST, Tages-Energieprofile PV-Ertrag, Σ Stundenwerte im Monatsbericht) zeigten bei manchen Anlagen voneinander abweichende Werte für die PV-Erzeugung — teils um ~10 %. Ursache: zwei parallel laufende Datenpfade (Riemann-Integration aus dem Live-Tagesverlauf + Counter-Boundary-Diff aus Sensor-Snapshots) mit unterschiedlichen Aggregationsfenstern, plus ein Filter-Bug im Genauigkeits-Tracking. Ab v3.31.0 sind die Aggregat-Tabellen Cache von HA-Statistics-Long-Term — eine einzige Quelle für alle Sichten, Σ Stundenwerte = Tagessumme per Konstruktion. Zusätzlich werden mit Etappe 5 die letzten drei eedc-eigenen Berechnungen (Tages-Peaks, Batterie-SoC-Stundenmittel, Strompreis-Stundenmittel) durch direkten HA-Statistics-Read ersetzt.

### Fixed

- **Genauigkeits-Tracking IST enthält keine Batterie-Netto-Ladung mehr**: Der IST-Wert für PV-Erzeugung im Genauigkeits-Tracking summierte bisher `komponenten_kwh`-Subkeys mit positivem Wert über eine Negativliste hinaus — bei Anlagen, deren Batterie über den Tag netto geladen hatte (z. B. 4–6 kWh Überschuss), wurde diese Ladung als IST-Erzeugung mitgezählt. Der Filter wurde auf eine Prefix-Whitelist `pv_*` und `bkw_*` umgestellt, analog zur Frontend-Spalte „PV-Ertrag" in der Tages-Energieprofile-Tabelle. Die Prognose-MAE-Werte werden dadurch realistischer (kein künstlich besserer Wert mehr).

### Changed

- **TagesEnergieProfil + TagesZusammenfassung werden Cache von HA-Statistics-LTS**: Die Stunden- und Tageswerte für PV, Einspeisung, Netzbezug, Batterie, Wärmepumpe, Wallbox usw. werden im HA-Add-on-Modus jetzt direkt aus den HA-Long-Term-Statistics gelesen (über die neue Funktion `HAStatisticsService.get_hourly_kwh_deltas_for_day`). Damit gilt für alle Anlagen mit HA-Integration: `Σ TagesEnergieProfil.pv_kw == TagesZusammenfassung.komponenten_kwh["pv_<id>"]` (und analog für alle anderen Kategorien). Der bestehende Sensor-Snapshot-Pfad bleibt als Fallback für Standalone-Anlagen ohne HA aktiv.
- **Schreib-Provenance-Vokabular erweitert**: Neue Source-Labels `external:ha_statistics:hourly` (für Stundenwerte in `TagesEnergieProfil`) und `external:ha_statistics:daily` (für `TagesZusammenfassung.komponenten_kwh`). Die Aufsplittung ermöglicht im Audit-Log die Diagnose, ob Stunden- oder Tagessumme den jeweiligen Wert geschrieben hat. Beide auf Stufe EXTERNAL_AUTHORITATIVE — manuelle Einträge gewinnen weiterhin unbedingt (Schutzrichtung aus v3.30.3 bleibt).
- **Daten-Checker zeigt aktiven Datenquellen-Pfad**: Neue Kategorie „Datenquelle – aktiver Pfad" mit drei möglichen Stati: (1) HA-Statistics als Source-of-Truth aktiv (OK), (2) HA-Statistics verfügbar, Aggregate noch aus älterer Quelle (Info, heilt sich beim nächsten Monatsabschluss), (3) Standalone-Modus ohne HA-LTS (Info, eingeschränkt durch Sub-Stunden-Boundary-Effekte). Transparente Diagnose für Anwender, die wissen wollen, woher ihre Zahlen kommen.
- **Etappe 5 — Tages-Peak-Werte aus HA-Statistics-Min/Max**: `peak_pv_kw`, `peak_netzbezug_kw` und `peak_einspeisung_kw` werden bevorzugt aus den Stunden-Extremwerten gelesen, die HA-Recorder für `has_mean=True`-Sensoren ohnehin schreibt (`statistics.max` / `statistics.min`). Die bisherige Berechnung aus 10-Min-Mittelwerten unterschätzte Peaks systematisch — der HA-Wert entspricht jetzt der physikalisch korrekten Tagesspitze. Mehrere PV-Sensoren werden per Σ max je Stunde aggregiert (obere Schranke, in der Praxis < 5 % Drift). Fallback auf den bisherigen Pfad bleibt für Standalone-Modus ohne HA-LTS.
- **Etappe 5 — Batterie-SoC- und Strompreis-Stundenmittel aus HA-Statistics**: `_get_soc_history()` und `_get_strompreis_stunden()` lesen Stundenwerte direkt aus `statistics.mean` statt sie aus der State-History selbst zu mitteln. Damit sind alle Stundenwerte im TagesEnergieProfil aus derselben HA-Statistics-Quelle wie das HA-Energy-Dashboard, mit gemeinsamer Recompile- und Kompression-Logik. State-History-Mittelung bleibt als Fallback wenn LTS leer.

### Migration

- **Automatischer Vollbackfill bei Upgrade**: Beim Update auf v3.31.0 wird für Anlagen mit HA-Integration und bestehenden Aggregat-Daten das `vollbackfill_durchgefuehrt`-Flag auf `False` zurückgesetzt. Beim nächsten Monatsabschluss läuft dann der Auto-Vollbackfill aus HA-LTS einmalig durch und füllt **fehlende** Tage nach (additiv, bestehende Tage bleiben unverändert — Schutz manueller Korrekturen). Anwender müssen für neue Tage nichts aktiv tun; um bestehende Tage gezielt auf die HA-Statistics-Werte umzustellen, stehen `Auswertungen → Energieprofil → Tag-Reload` (Vorschau) und `Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Bereich neu aggregieren` zur Verfügung. Anlagen ohne HA-Integration (Standalone-Docker) bleiben unverändert — ihr Snapshot-basierter Pfad funktioniert weiter wie bisher.

### Hinweis für Anwender

Wenn dir nach dem Update auffällt, dass historische Tageswerte sich um wenige Prozent ändern: das ist beabsichtigt. Die Werte wurden von dem rechnerisch nicht ganz sauberen Mix-Pfad auf die HA-Statistics-konformen Werte umgezogen (gleiches Ergebnis wie das HA-Energy-Dashboard). Die neuen Werte sind durchgängig konsistent zwischen allen eedc-Sichten — die Drift, die manche Anwender zuvor zwischen Genauigkeits-Tracking, Tages-Energieprofile und Stunden-Σ gesehen hatten, ist Geschichte.

### Konzept-Dokumentation

Vollständige Architektur + Pfad-Inventar + Test-Plan: `docs/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` (Etappe 5 als Anhang 9a).

### Tests

Suite wächst von 96 auf 125 Tests (29 neue, alle grün):
- 5 Tests für `HAStatisticsService.get_hourly_kwh_deltas_for_day` (Lückenbehandlung, Einheiten, Mehrfach-Sensoren)
- 7 Konsistenz-Tests für die LTS-Aggregator-Pfade (Σ Hourly == Daily über alle Investitionstypen)
- 6 Tests für die Migration (Reset-Verhalten, Idempotenz, Standalone-No-Op)
- 5 Tests für `HAStatisticsService.get_hourly_mean_for_day` (Etappe 5: SoC + Strompreis, Roh-Einheit)
- 5 Tests für `HAStatisticsService.get_hourly_minmax_sensor_data` (Etappe 5: Stunden-Extrema, Einheiten-Filter, Boundary)
- 6 Tests für `_get_tagespeaks_aus_ha_lts` (Etappe 5: Einzel-/Multi-PV, Kombi-Netz, Invert-Flag, Fallback)

---

## [3.30.3] - 2026-05-16 — Split-Klimaanlagen als Luft-Luft-WP (Forum #548)

> ❄️ **Klimaanlagen sind jetzt Wärmepumpen.** Eine Split-Klimaanlage ist physikalisch eine Luft-Luft-Wärmepumpe (Reverse-Cycle, Heizen + Kühlen). Bisher wurden sie pragmatisch unter „Sonstiges" geführt — was im Cockpit-Wärmepumpenbereich keinen Eintrag erzeugt und die JAZ-Statistik verfälscht. Ab v3.30.3 steht `wp_art = "luft_luft"` als gleichwertiger WP-Subtyp zur Verfügung; das System rechnet und meldet entsprechend.

### Changed

- **JAZ/COP-Berechnung tolerant gegen fehlenden Wärmemengenzähler** (Forum #548 alex_s9027): Die JAZ wird jetzt nur ausgegeben, wenn **beide** Seiten gemessen sind — Stromverbrauch UND Heizenergie. Bisher kam bei Klimas (Stromverbrauch ja, Heizenergie nein) ein irreführender Wert „0.0" heraus, jetzt sauber „—" (Lücke). Betroffene Endpunkte: Cockpit-Übersicht, Cockpit-Komponenten, PDF-Jahresbericht, PDF-Operationen, Sozial-Bilanz.
- **Daten-Checker still bei Klimaanlagen**: Bei `wp_art = "luft_luft"` wird die „Heizwärme fehlt"-INFO nicht mehr gemeldet — bei Klimas ist das normal (Standardausstattung HACS-Integrationen liefert nur Stromzähler), nicht ein Datenloch. Klassische Luft-Wasser-WPs bekommen die Warnung weiterhin (kein Regress).
- **WP-Wizard: Hinweis-Box bei Wahl „Luft-Luft (Klimaanlage)"**: erklärt, dass nur der Stromverbrauchs-Sensor nötig ist, die JAZ-Kachel bleibt leer.

### Fixed

- **Cockpit-Übersicht zeigt jetzt eine Sonstiges-Sektion** (Forum #548): Bisher hatten „Sonstiges"-Investitionen (Pool, Sauna, Klima ohne WP-Kategorie, Zweit-Erzeuger) zwar im Detail-Tab und in der Monatsübersicht ihre Werte — die Cockpit-Übersicht (Hauptseite) hat sie aber komplett ignoriert. Backend-Endpoint `/api/cockpit/uebersicht` liefert jetzt `sonstiges_erzeugung_kwh` + `sonstiges_verbrauch_kwh` + `hat_sonstiges`, das Cockpit-Dashboard rendert eine entsprechende Section mit Erzeugungs- und Verbrauchs-KPI-Kacheln (sichtbar nur wenn die Investition mindestens eine Seite gepflegt hat).
- **MariaDB-Verbindung mit `mysql://`-URL funktioniert jetzt** (#251 FrodoVDR): Der HA-Recorder-Doku-Standard `mysql://user:pass@host/db` führte zu `ModuleNotFoundError: No module named 'MySQLdb'`, weil SQLAlchemy bei dieser Schreibweise das C-Modul mysqlclient lädt (im Add-on-Image ist nur `pymysql` installiert). Auto-Treiber-Mapping in `ha_statistics_service.py` biegt `mysql://` und `mariadb://` intern auf `mysql+pymysql://` bzw. `mariadb+pymysql://` um. Wer den `+pymysql`-Suffix bereits in der URL stehen hat, ist unverändert.
- **Plan-Vorschau zeigt korrekte Uhrzeit für die Gültigkeit** (#257 detLAN): Der „Plan gültig bis"-Header in der Reparatur-Werkbank zeigte die UTC-Zeit als wäre sie Lokalzeit — in MESZ ergab das eine Differenz von 2 Stunden (z. B. „21:00" statt korrekt „23:00"). Backend liefert die Zeit jetzt als tz-aware UTC mit `+00:00`-Marker, Frontend interpretiert korrekt + defensive Normalisierung für Übergangs-Cache-Fälle.
- **Obsolete WP-Stromverbrauchs-Sensoren werden beim Wizard-Speichern automatisch entfernt** (rapahl PN 2026-05-16): Wer eine Wärmepumpe von „Gesamt-Strommessung" auf „getrennte Strommessung" (Strom Heizen + Strom Warmwasser) umgestellt hat, hatte den alten `stromverbrauch_kwh`-Eintrag weiterhin im Sensor-Mapping liegen — die UI blendete das Feld bei aktivierter getrennter Messung aus, der Daten-Checker zeigte daher einen INFO-Hinweis ohne klickbaren Lösch-Pfad. Ab v3.30.3 räumt der Wizard-Save den Eintrag still auf (kein Datenverlust, der Sensor wird in der Aggregation ohnehin ignoriert), der Daten-Checker-Hinweis erklärt das Verhalten und entfällt nach dem nächsten Speichern.
- **Live-Heute: doppelte Skalierung bei MWh/Wh-Sensoren behoben** (#242 NongJoWo): Energie-Sensoren mit Einheit Wh oder MWh wurden im Live-Heute-Pfad doppelt skaliert — `ha_statistics_service.get_value_at` skaliert intern bereits auf kWh, aber `live_history_service._energy_delta` multiplizierte den Statistics-Pfad-Wert nochmal mit `_KWH_SCALE`. Folge: MWh-Werte wurden mit Faktor 1000 zu hoch angezeigt (NongJoWo: 8.11 kWh Einspeisung wurden als 8097 kWh dargestellt). Fix: Statistics-Pfad wird unverändert weitergegeben (Werte sind bereits kWh), `_KWH_SCALE` greift nur noch im state-history-Fallback (rohe state-Werte). Tests entsprechend angepasst — die alte Test-Erwartung mockte das echte Verhalten falsch und ließ den Bug durchrutschen.
- **WP-Kompressor-Starts werden jetzt auch beim Vollbackfill aus HA-Statistics geschrieben** (#259 detLAN): Bisher füllte der Vollbackfill-Pfad (`Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Lücken aus HA-LTS nachfüllen`) zwar alle Energiewerte, ließ aber `wp_starts_anzahl` leer — die Tagesdetail-Tabelle in „Auswertungen → Energieprofil" zeigte leere WP-Starts-Spalten für nachgefüllte Tage. `aggregate_day` hatte den Pfad bereits korrekt (v3.24.0), Backfill nicht. Jetzt analog implementiert.
- **Manuelle Eingabe schlägt jetzt jede andere Datenquelle — auch `repair`** (#251 FrodoVDR): Bisher konnte der Provenance-Resolver eine Wizard-Eingabe still verwerfen, wenn das Feld zuvor von einer Reparatur-Operation (Quelle `repair`) gestempelt war — der User sah „erfolgreich gespeichert", aber die DB blieb unverändert. Auch der zwischenzeitlich eingebaute Schreib-Reject-Hinweis war Symptombehandlung, nicht der Fix. Jetzt: jede explizite User-Eingabe über Wizard oder Monatsformular gewinnt unbedingt, unabhängig von der existierenden Provenance. Hintergrund-Quellen (Cloud, HA-Stats, Aggregation, Fallback) können den manuell gepflegten Wert weiterhin nicht überschreiben — die Schutzrichtung war schon immer korrekt, jetzt ist sie auch ohne Schlupfloch.

### Hinweis für Anwender

Wenn du eine Split-Klimaanlage bisher unter „Sonstiges" hattest: lege sie als neue Investition vom Typ „Wärmepumpe" mit `wp_art = "Luft-Luft (Klimaanlage)"` an, weise denselben Stromverbrauchs-Sensor zu, lösche die alte „Sonstiges"-Investition. Sie taucht dann im Cockpit-Wärmepumpenbereich auf, in der Komponenten-Auswertung und im Community-Benchmark (gruppiert mit anderen Luft-Luft-Klimas). Wer „Sonstiges" für andere Verbraucher/Erzeuger nutzt (Pool/Sauna/etc.), bekommt sie ab v3.30.3 automatisch im Cockpit angezeigt.

Was Phase 1 **nicht** enthält (folgt anlassbezogen): eigene Kühlenergie-Erfassung (`kuehlenergie_kwh`), EER-Effizienz-Metrik für Kühlbetrieb, Modus-Erkennung über Thermostat-Entitäten.

---

## [3.30.2] - 2026-05-15 — PV-Counter-Spike-Cap (Forum #529)

> 🛡️ **Schutz vor Counter-Off-by-ones.** HA-Statistics liefert nach manchen Restarts einen falschen Stunden-Sprung im PV-Counter (z. B. +109 kWh in einer Stunde bei einer 11 kWp-Anlage). Der Daten-Checker hat solche Spikes bisher *erkannt*, aber der Aggregator schrieb sie ungekappt in den Stundenwert — Reaggregation war idempotent und konnte sie nicht heilen. Ab v3.30.2 cappt der Aggregator PV- und Einspeisungs-Stundenwerte präventiv gegen `kwp × 1.5`.

### Fixed

- **PV-/Einspeisungs-Stundenwerte werden gegen Plausibilität gecappt** (Forum #529, dietmar1968): Wenn ein Stunden-kWh-Wert mehr als das 1,5-fache der PV-Anlagenleistung beträgt, wird er in `TagesEnergieProfil` als Lücke (None) gespeichert statt als Spike. Damit greift „Tag neu aggregieren" in der Reparatur-Werkbank jetzt auch bei klassischen Counter-Off-by-ones, die bei der bisherigen idempotenten Reaggregation unverändert zurückkamen.
- **SoT-Konvention zwischen Detektor und Cap**: Schwelle `kwp × 1.5` lebt jetzt zentral in `backend/services/snapshot/plausibility.py`. Daten-Checker und Aggregator ziehen dieselbe Schwelle aus diesem Helper — kein Drift mehr möglich.

### Hinweis für Betroffene

Nach dem Update einmal über **Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Tag neu aggregieren** für den betroffenen Tag laufen. Stundenwert mit Spike wird zur Lücke, Tageswerte fallen auf das physikalisch plausible Niveau. Anlagen ohne hinterlegte `leistung_kwp` werden nicht gecappt (Stammdaten-Check meldet das schon separat).

---

## [3.30.1] - 2026-05-15 — Prognosequellen-Wahl pro Anlage + Strompreis-Vorschlag

> ☀️ **Drei PV-Prognosequellen zur Auswahl.** Jede Anlage kann jetzt zwischen eedc-optimiert (Standard), Solcast und Solar Forecast ML wählen. Auto-Discovery erkennt installierte Integrationen in HA automatisch — kein manuelles Sensor-Mapping mehr nötig.

### Added

- **Prognosequelle pro Anlage wählbar**: neues Feld `prognose_quelle` in den Anlagen-Einstellungen mit drei Optionen:
  - **eedc-optimiert** (Standard): OpenMeteo × anlagenspezifischer Lernfaktor — funktioniert überall, auch standalone
  - **Solcast** (pur): Satellitenbasierte Prognose direkt, ohne eedc-Korrektur
  - **Solar Forecast ML** (pur): ML-basierte Prognose direkt aus der HA-Integration, ohne eedc-Korrektur (nur im HA-Add-on)
- **Auto-Discovery**: SFML- und Solcast-Sensoren werden automatisch in HA erkannt — kein manuelles Sensor-Mapping im Wizard mehr nötig. Discovery erkennt die Integration anhand der Entity-ID-Patterns und mappt alle relevanten Sensoren automatisch
- **Solcast Standalone**: API-Token + Resource-IDs können im Sensor-Mapping-Wizard eingegeben werden (für Nutzer ohne HA-Integration)
- **Quellen-Hinweis**: WetterWidget und Live-Dashboard zeigen die aktive Quelle an (nur bei Nicht-Default). Bei Fallback auf eedc erscheint ein Amber-Hinweis mit Erklärung
- **Resolver-Service** (`prognose_router.py`): zentrale Quellen-Auflösung mit Verfügbarkeits-Check und automatischem Fallback auf eedc
- **Discovery-Endpoint** `GET /api/anlagen/prognose-quellen/discover`: zeigt dem Frontend die in HA erkannten Integrationen + Sensoren
- **Verbrauchsgewichteter Ø-Strompreis im Monatsabschluss-Wizard** (#250): Bei dynamischen Tarifen (Tibber, aWATTar) berechnet eedc jetzt automatisch den verbrauchsgewichteten Monats-Durchschnittspreis aus den gesammelten Stundendaten — als Vorschlag mit Konfidenz-Staffelung (je nach Stunden-Abdeckung). Der bisherige HA-Sensor-Momentanwert bleibt als Fallback mit reduzierter Konfidenz erhalten

### Changed

- **EEDC-Lernfaktor O12 als Live-Default**: Der verbesserte Lernfaktor mit Recency-Boost und Trim-Mean (O1+O2) ist jetzt der aktive Live-Faktor. Legacy-Skalar dient als Fallback und wird im Log als Diagnose-Vergleich ausgegeben
- **EEDC nutzt immer OpenMeteo als Basis**: Die bisherige Option „Solcast als EEDC-Basis" entfällt — Solcast ist jetzt eine eigenständige Quelle (pur, ohne Korrektur). Wer vorher `prognose_basis=solcast` hatte, wird automatisch auf `prognose_quelle=solcast` migriert
- **Solcast im HA-Add-on ohne manuelle Konfiguration**: `solcast_service.py` erkennt die Solcast-Integration automatisch per Auto-Discovery, auch ohne explizite `solcast_config` im Sensor-Mapping
- **Prognosen-Tab**: reine EEDC-Diagnose-Sicht (OpenMeteo vs. eedc-kalibriert vs. Solcast vs. IST), keine SFML-Vergleichs-Spalte mehr

### Fixed

- **„Database is locked" beim Monatsabschluss**: SQLite WAL-Journal + `busy_timeout=10000` + `synchronous=NORMAL`. Parallele Writer (MQTT-Inbound, Background-Aggregator, Wizard) warten jetzt aufeinander statt sofort abzubrechen. *(PR #248, @stlorenz)*

### Removed

- **SFML-Vergleichs-Card** in Aussichten → Prognosen (eedc vs. ML vs. IST Tabelle + Chart) — entfällt zugunsten der Quellenwahl
- **SFML-Anzeigen im Live-Dashboard**: lila ML-Zahl neben Tagesprognose + Tooltip
- **SFML-Linie im WetterWidget**: lila dotted ML-Prognose-Linie + Legende + Gradient
- **Manuelle SFML-Sensor-Zuordnung** im Wizard (3 Felder: sfml_today_kwh, sfml_tomorrow_kwh, sfml_accuracy_pct) — ersetzt durch Auto-Discovery
- **`prognose_basis`-Feld**: deprecated, wird automatisch zu `prognose_quelle` migriert

---

## [3.29.2] - 2026-05-14 — Vorab-Fixes vor Menüstruktur-Konzept (#206 #210)

> 🧹 **Stall ausmisten vor dem großen Konzept.** Kleine UX-Fehler und Schreibweisen-Drift, die nicht auf das künftige Menüstruktur-Konzept warten sollten. Kein neuer Funktionsumfang.

### Fixed

- **Komponenten-Beiträge zur Finanzierung — Sortierung und Icons** (#210 detLAN). In Aussichten → Finanzen wurden die Beiträge in der Reihenfolge Speicher → E-Auto-V2H → E-Auto-Benzin → E-Auto-PV → WP-PV → WP-Ersparnis angezeigt — Wärmepumpe stand also nach E-Auto, inkonsistent zur App-weiten `INVESTITION_TYP_ORDER` (Wallbox/E-Auto-Cluster nach WP). Zusätzlich fielen drei Beitragstypen (`waermepumpe-pv`, `waermepumpe-ersparnis`, `e-auto-benzin`) auf den `Battery`-Fallback-Icon durch, weil das Mapping in `FinanzenTab.tsx` die Suffix-Typen nicht kannte. Beides behoben:
    - Neuer `komponentenBeitragTypIndex()`-Helper mappt Suffix-Typen auf ihren Basis-Typ (z. B. `waermepumpe-pv` → `waermepumpe`) und sortiert nach dem Index in `INVESTITION_TYP_ORDER`.
    - `KOMPONENTEN_ICONS` um die drei Suffix-Typen erweitert: `e-auto-benzin` → `Fuel`, `waermepumpe-pv` und `waermepumpe-ersparnis` → `Flame`.
    - Die 4-Kacheln-Zusammenfassung unter der Karte (Speicher EV+ / V2H / E-Auto PV-Ladung / WP PV-Direkt) zieht in dieselbe Reihenfolge: Speicher → WP → V2H → E-Auto-PV-Ladung.
- **Dekoratives Calendar-Icon vor Jahres-Filter in Auswertungen entfernt** (#206 P2-Folge detLAN). Das gleiche Phänomen wie im Cockpit (in v3.27.1 schon entfernt) saß noch in der Auswertungen-Top-Bar: nicht-klickbares `Calendar`-Icon neben klickbarem Year-`<select>` verwirrt — weniger ist mehr. Beide Selects (Jahr + Anlage) haben jetzt `aria-label`/`title` für Bildschirmleser.
- **Schreibweise „eedc" durchgängig — Code-Sichtbares + Hilfe-Dokumente** (#206 P4 detLAN). Bisherige `EEDC`-Reste in anwender-sichtbaren Stellen auf das lower-case Marken-Token umgestellt:
    - **Code (8 Bereiche, 19 Stellen)**: Share-Text-Footer (`social.py` 2×), HA-Verbindungsfehler-Message (`ha_integration.py`), HA-Sensor-Export-YAML-Header + Friendly-Name-Präfix + Device-Doc (`ha_export.py` 3×), MQTT-Device-Name + manufacturer (`mqtt_client.py` 5×), Restart-Message (`system_logs.py`), Fallback-API-Antwort (`main.py`), PDF-Bericht-Titel (`pdf_service.py` 3×), PVGIS-User-Agent (`anlagen.py`), Browser-Tab-Titel + meta description (`index.html` 2×).
    - **Hilfe-Dokumente (10 Dateien, ~130 Treffer)**: BENUTZERHANDBUCH, WAS-IST-NEU, HANDBUCH_INSTALLATION/BEDIENUNG/EINSTELLUNGEN/INFOTHEK/DATEN_CHECKER, BERECHNUNGEN, SENSOR-REFERENZ, GLOSSAR — `\bEEDC\b` mit Wortgrenze ersetzt, schützte Code-Identifier wie `EEDC_ENERGIEPROFIL_QUELLE` und Formel-Variablen `EEDC_Abweichung`/`EEDC_Prognose`/`EEDC_Roh_Prognose_kWh` automatisch. ReportLab-Style `EEDCBody` und Doc-Strings/Code-Kommentare im Backend (Dev-Sicht) unverändert.

> **Hinweis für Bestandsnutzer mit MQTT-Discovery**: HA-Devices erscheinen ab diesem Update mit Friendly-Name „eedc - <Anlagenname>" statt „EEDC - <Anlagenname>". Entity-IDs (`eedc_anlage_*`, `sensor.eedc_*`) bleiben gleich, keine Daten-Migration. Wer im YAML-Sensor-Export-Snippet die Friendly-Names manuell übernommen hat, kann das Snippet aus „Einstellungen → HA-Export" neu kopieren — funktional ändert sich nichts.

### Internal

- A6 (globaler `pt-4`-Whitespace zwischen Sub-Tabs und erstem Page-Inhalt) bereits in v3.29.1 via `Layout.tsx`-Commit `650adb09` (#233 P15) erledigt — detLAN's #209 P5-Comment lag vor v3.29.1 und ist seitdem implizit gefixt.
- Vorbereitung für **Konzept-Issue „Durchgängige Menüstruktur + Mobile-Strategie"**: bestehende Sub-Tracker #203, #204, #206, #208, #209, #210, #216 werden mit Verweis aufs neue Konzept geschlossen.

---

## [3.29.1] - 2026-05-14 — Anschaffungsdatum-Komplettierung + UX-Cluster (#229 #233 #237 #239 #240 #241)

> 🪛 **Tester-Welle vom 13./14. Mai gebündelt** — detLAN-Folge zu #236 mit zwei zusätzlichen Pfaden, JanKgh-Multi-String-Verteilungsbug, fünf UX-Verbesserungen aus detLAN/NongJoWo. Kein neuer Funktionsumfang.

### Fixed

- **Monatsbericht-Sektion vor Anschaffungsdatum ausblenden** (#239 detLAN-Folge zu #236). v3.29.0 hatte den Aggregat-Filter ausgerollt, aber die Sektions-Sichtbarkeit im Monatsbericht (Wärmepumpe / Speicher / E-Mobilität / Balkonkraftwerk / Sonstiges) wurde weiter anlagenweit berechnet. Folge: WP-Sektion erschien auch in Monaten vor Anschaffung — alle Werte „—", aber der Block stand. Fix in `aktueller_monat.py:1101+`: die `hat_*`-Flags und die `wp_invs`-Liste für Kompressor-Starts respektieren jetzt `ist_aktiv_im_monat(jahr, monat)`. Sektion verschwindet komplett, Folgesektionen rücken hoch.
- **HA-Statistics-/MQTT-Aggregation respektiert Anschaffungsdatum** (#239 detLAN-Folge). Zweiter Pfad, der nach dem v3.29.0-Fix immer noch Vor-Anschaffungs-Werte durchließ: `aktueller_monat.py` aggregierte HA-Sensor-Werte über `inv_{id}_*`-Keys ohne Anschaffungsdatum-Filter. Sensoren existieren in HA häufig schon vor der EEDC-Registrierung. Beispiel detLAN: WP-Anschaffungsdatum April, im März-Monatsbericht standen trotzdem 145 kWh Strom. Fix: `ist_aktiv_im_monat(jahr, monat)` als Vor-Filter in beiden Aggregations-Schleifen (typ_aggregation + E-Mob-Pool).
- **Einheitliches Display-Token '—' statt '---' für leere Felder** (#239 detLAN). An manchen Stellen wurde '---' (drei ASCII-Bindestriche), an anderen '—' (em-dash) für „kein Wert" gezeigt. Alle 41 Frontend-Vorkommen auf em-dash umgestellt (war ohnehin Mehrheit mit 68 Stellen). Display-Token-Änderung, keine Code-Logik berührt.
- **Modul-Verteilung primär aus Tabellen-Spalte, parameter als Fallback** (#229 JanKgh, SolarEdge-Multi-String). Bei 4 PV-Modul-Investitionen Ost/West × 2 Neigungen wurde die Anlagengesamterzeugung gleichverteilt (1/4 je Modul) statt anteilig nach kWp — der Verteilungs-Helper las `leistung_kwp` aus `parameter`-JSON, gepflegt ist aber die Tabellen-Spalte. SoT-Helper `backend/utils/investition_value.py:get_inv_value(inv, key)` liest primär die Spalte, fällt auf `parameter` zurück. Beide Verteilungs-Helper umgestellt (`import_export/helpers.py:_distribute_legacy_pv_to_modules` für CSV-Import, `connector.py:_distribute_by_param` für HA-Live-Daten). Mapping `_COLUMN_FOR_PARAM` erweiterbar.
- **UX-Konsistenz Einstellungen → Allgemein/Protokolle + globaler Page-Whitespace** (#233 detLAN P13–P18). Zwei weitere überflüssige Page-Überschriften, die in v3.27.5 übersehen wurden, entfernt: „Einstellungen" (Allgemein-Tab) und „Protokolle" (Protokolle-Tab). „Debug" + „Neustart" rücken in dieselbe Reihe wie die Sub-Sub-Tabs „System-Logs/Aktivitäten" — gemeinsame Toolbar statt zwei getrennter Header-Zeilen. **Layout-weit**: Main-Container von `pt-1` auf `pt-4` — zusammen mit `SubTabs py-2` ergibt das 24 px Whitespace zwischen Sub-Tabs und erstem Page-Inhalt, konsistent zu `space-y-6` zwischen Cards.
- **kWh-Einheiten an Wärmepumpe-Dashboard ergänzt** (#237 detLAN). Drei Stellen ohne Einheitsangabe in „Cockpit → Wärmepumpe": Monatsdaten-Tabellen-Header (Strom/Heizung/Warmwasser → jeweils „(kWh)"), Wärme-Verteilung Summary „Heizung 1621 kWh · Warmwasser 133 kWh" (vorher fehlte Einheit bei Heizung), Wärmeerzeugung-pro-Monat Chart — Y-Achse beschriftet mit „kWh", Tooltip mit Einheit.
- **Daten-Checker: Inbetriebnahme-Monat als Vorjahres-Vergleichsbasis ausgeschlossen** (#240 NongJoWo). Anlage seit Ende März 2022 → März-2022-Werte (50 kWh, Bruchteil) im März-2023-Vergleich (261 kWh) als „3× Vorjahr" gemeldet. Fix in `_check_monatsdaten_plausibilitaet`: Vergleich überspringt Monate, in denen die Anlage im Inbetriebnahme-Monat (oder davor) war — die Werte sind dann strukturell unvollständig. Linie: Daten-Checker-Hinweise bleiben nicht-quittierbar, stattdessen die Heuristik schärfen.
- **Sparkline-Tooltip zeigt Monatsnamen statt Bar-Index** (#241 NongJoWo). Cockpit → Übersicht → Energie-Bilanz → PV-Monatserträge-Sparkline zeigte beim Hover „1" / „2" / „3" als Header. Hidden `XAxis` mit `dataKey="name"` ergänzt — Tooltip liest jetzt den Monatsnamen aus den Daten („Mär 22" / „Jan 26").

### Internal

- Drei neue/erweiterte Test-Dateien: `test_monatsbericht_hat_flags_filtern_vor_anschaffung` in `test_investition_aktiv_filter.py` (für #239), `test_inv_value_spalten_fallback.py` (6 Tests für #229), `test_daten_checker_vorjahr_inbetriebnahme.py` (2 Tests für #240). Alle grün, bestehende Suiten weiterhin grün.
- SoT-Helper `backend/utils/investition_value.py` (`get_inv_value`) mit Mapping `_COLUMN_FOR_PARAM` für künftige Spalten-vs.-Parameter-Drift.

---

## [3.29.0] - 2026-05-13 — Aggregations-/UX-Bündel (#222 #231 #232 #234 #235 #236)

> 🪛 **Tester-Welle vom 12./13. Mai gebündelt** — fünf strukturelle Reparaturen aus detLAN-/NongJoWo-Meldungen plus ein UX-Fix in „Eigene Dateien"-Vorschau. Kein neuer Funktionsumfang.

### Fixed

- **Anschaffungs-/Stilllegungsdatum-Filter über alle Read-Sites** (#236 detLAN). detLAN hatte gemeldet, dass eine WP-Investition mit `anschaffungsdatum=April` Vor-Anschaffungs-Daten (März) weiterhin in Aggregaten zeigt. Drift-Sweep ergab: Helper `Investition.ist_aktiv_im_monat` existiert (mit `stilllegungsdatum`), wird aber an **13 Stellen** entweder gar nicht oder nur per inline-Check (ohne Stilllegung) angewendet. Backend-SoT-Migration: `monatsdaten.py /aggregiert` + `ha_export.py /api/ha-export` (Per-IMD-Filter via `ist_aktiv_im_monat`, vorher kein Filter); Cockpit-Suite (`uebersicht`, `social`, `nachhaltigkeit`, `aktueller_monat`, `komponenten` 2 Stellen), `investitionen.py` (5 Dashboards + Wallbox-Helper), `aussichten.py` (zentral beim Laden) — inline-Check durch SoT-Helper ersetzt, bringt Stilllegungs-Korrektheit gratis mit (Memory-Linie `feedback_aggregations_drift.md`); `pdf/jahresbericht.py` + `cockpit/pv_strings.py` beide Endpoints. Schema 0 ≠ None (CLAUDE.md „0-Werte prüfen"): `AggregierteMonatsdatenResponse`-Komponenten-Felder `Optional[float]`. `None` = keine aktive Komponente in dem Monat (vor Anschaffung / nach Stilllegung / Anlage hat den Typ nicht). `0` = Komponente aktiv, IMD vorhanden, Wert echt 0 (z. B. WP-Heizung im Sommer). Frontend `AggregierteMonatsdaten` + `MonatsZeitreihe`: nullable Felder durchgereicht, Tabellen-`fmtVal` rendert `null` als „—". JAZ-Kachel zeigte „Jahresarbeitszahl 2023-2026" obwohl WP erst seit 2025: `KomponentenTab.tsx` berechnet `wpZeitraumLabel` jetzt aus `chartData` (Monate mit `wp_strom > 0`), nicht aus dem Anlagen-weiten `zeitraumLabel`.
- **Wh→kWh-Skalierung im Statistics-Pfad von `_energy_delta`** (#232 NongJoWo). Live-Heute zeigte für einen `Wh`-Sensor Werte mit Faktor 1000 zu hoch (z. B. 87.000 statt 87 kWh). Der `_is_energy_sensor`-Check, der im Sensor-Mapping-Wizard und im Live-Pfad bereits Wh-Slots in kWh konvertiert, fehlte im Statistics-Fallback der `_energy_delta`-Helfer. Pfad jetzt konsistent.
- **Pool-Doppelzählung in Auswertungen → Komponenten** (#231 NongJoWo). Wallbox-IMD (Loadpoint-Sicht) und E-Auto-IMD (Vehicle-Sicht) messen oft denselben Stromfluss aus zwei Perspektiven. `cockpit/komponenten.py` summierte beide → Doppelzählung, PV-Anteil > 100 % möglich. Konsolidierung analog zu `aktueller_monat._aggregate`: getrennte Akkumulatoren `eauto_*` + `wb_*` pro Monat, `ist_dienstlich`-Filter früh, beim Konsolidieren pro Feld `max(eauto, wb)`. Km/V2H kommen nur vom E-Auto (Wallbox kennt das nicht). Vier neue Akzeptanztests in `test_emob_pool_komponenten.py`.
- **Reparatur-Werkbank-UI-State setzt sich nach erfolgreichem Lauf zurück** (#234 + #235 detLAN). Nach einem Reaggregations-Lauf (Tag oder Range) blieben Plan-/Execute-Steuerelemente versteckt — Modal-State überlebte zwischen Aufrufen und „Plan erstellen" verschwand nach Execute. `RepairWorkbench.tsx` setzt jetzt nach Abschluss eines Laufs den vollständigen Editor-State zurück (Form-Felder + Plan-Snapshot + Run-Result).
- **„Eigene Dateien"-Vorschau zeigt Investitions-Spalten als Tabellen-Spalten** (#222 NongJoWo). Wer eine CSV mit ausschließlich auto-erkannten Investitions-Spalten importiert hatte, sah eine Vorschau-Tabelle voller „—" — die Spalten wurden korrekt erkannt, aber die Werte tauchten erst nach dem Apply auf. UX wirkte wie Bug. `PreviewMonth.inv_werte: dict[str, float]` und `PreviewResponse.inv_spalten: list[str]` ergänzt; `_apply_mapping` sammelt manuell `inv:`-gemappte und auto-erkannte Spalten gleichermaßen ein; bei Doppel-Mapping gewinnt manuell. `used_inv_spalten`-Set filtert leere Spalten aus der Header-Liste. Frontend rendert dynamische `<th>`/`<td>` hinter den fünf Standard-Spalten. Banner-Text „Werte in der Vorschau-Tabelle nicht sichtbar" entfällt. Fünf Akzeptanztests in `test_custom_import_preview_inv_werte.py`.

### Internal

- 25 neue/erweiterte Akzeptanztests; vier neue Test-Dateien für #231 + #222, je ein Test in `test_investition_aktiv_filter.py` für #236. Bestehende Regressions-Suiten (emob_pool_komponenten, wp_aggregator_bugs, investition_aktiv_filter, live_history_kwh_scale, repair_orchestrator, provenance, snapshot) bleiben grün.
- Frontend TypeScript-Check ohne Fehler nach Schema-Erweiterungen (`PreviewMonth.inv_werte`, `PreviewResult.inv_spalten`, `AggregierteMonatsdaten` nullable Komponenten-Felder).
- Memory-Linie `feedback_aggregations_drift.md` (bereits etabliert, jetzt sechs+ Vorfälle dokumentiert) — bei JSON-Key/Filter/Cap-Drift über mehrere Read-Sites immer SoT-Helper einführen, nie punktuell patchen.

---

## [3.28.0] - 2026-05-13 — Mehrere Tage neu aggregieren in Reparatur-Werkbank (#230)

> 🪛 **Neue Reparatur-Operation `REAGGREGATE_RANGE`** — Schleife über `aggregate_day` pro Tag, max. 31 Tage pro Lauf, Per-Tag-Commit für Abbruch-Robustheit, Pflicht-Checkbox „ohne Support-Anspruch" im UI. Aus Martins Anregung in #230 zu mehreren Schüben Reaggregation für historische WP-Daten nach Sensor-Wechsel. Bewusst eng dimensioniert (Memory-Linie `feedback_kein_grosser_heiler_knopf.md`): kein Universal-Reset-Knopf, sondern transparent dimensioniertes Power-User-Werkzeug.

### Added

- **`RepairOperationType.REAGGREGATE_RANGE`** in [services/repair_orchestrator.py](eedc/backend/services/repair_orchestrator.py). Plan validiert von/bis (von ≤ bis, bis < heute, anzahl_tage ≤ `REAGGREGATE_RANGE_MAX_DAYS=31`), zählt vorhandene Tageszusammenfassungen im Bereich, liefert eine sechspunktige Warnungs-Liste (Per-Feld-Provenance-Überschreibung, MQTT-Only-Verlust-Risiko, Strompreis-Sensor-Verlust-Risiko, Prognose+Korrekturprofil-Erhaltung, Support-Disclaimer). Execute schleift seriell mit `aggregate_day(datenquelle="manuell")` + optionalem `resnap_anlage_range` pro Tag, macht **Per-Tag-Commit** für Abbruch-Robustheit, sammelt Erfolg/keine_daten/Fehlgeschlagen-Counter plus Cap-Detail-Liste (20 Einträge max im Response-Body, vollständig im Backend-Log).
- **Endpoint `POST /api/energie-profil/{anlage_id}/reaggregate-bereich`** in [routes/energie_profil/repair.py](eedc/backend/api/routes/energie_profil/repair.py). Params `von` + `bis` (Pflicht), `mit_resnap` (Default true). Wrapper über Orchestrator-Plan+Execute.
- **UI-Operation „Mehrere Tage neu aggregieren"** in [components/repair/RepairWorkbench.tsx](eedc/frontend/src/components/repair/RepairWorkbench.tsx) + Metadaten in [api/repair.ts](eedc/frontend/src/api/repair.ts). Date-Range-Picker mit 31-Tage-Frontend-Cap (Backend-Cap-Kopie), `mit_resnap`-Toggle und prominente amber-Pflicht-Bestätigung im Editor-Block. Validierung vor dem Plan-Erstellen (von ≤ bis, bis < heute, anzahl_tage ≤ 31, Checkbox geahkt).

### Internal

- Drei neue Akzeptanztests in [backend/tests/test_repair_orchestrator.py](eedc/backend/tests/test_repair_orchestrator.py): `test_plan_reaggregate_range_rejects_invalid_bounds` (drei ValueError-Pfade), `test_plan_reaggregate_range_valid_returns_warnings` (Warnungs-Liste vollständig), `test_execute_reaggregate_range_iterates_and_commits_per_day` (Schleife läuft auch nach Tages-Fehler weiter, Summary mit korrekten Zählern, `aggregate_day`+`resnap_anlage_range` via AsyncMock). Alle 11 Tests grün.
- Memory-Linie `feedback_kein_grosser_heiler_knopf.md` neu — dokumentiert, warum Massen-Reaggregation kein Default-Vorschlag ist (Reflex zur „pauschalen Heiler-Funktion" kehrt wieder, auch nach Kritik) und unter welchen Bedingungen sie trotzdem verantwortbar gebaut werden kann (explizit, mit Warnung, ohne Support).

---

## [3.27.5] - 2026-05-12 — UX-Cluster detLAN + PV-Ertrag-Spalte (#207 #215 #217 #218 #494)

> 🪛 **detLAN-Cluster aus #203–#218 strukturell abgearbeitet** plus eine Spalten-Erweiterung von dietmar1968 (#494). Kein neuer Funktionsumfang — fünf koordinierte Detail-Verbesserungen, die in Summe die UI-Konsistenz spürbar anziehen (Tab-Header vs. Page-Titel, Schaltflächen-Stil, Komponenten-Reihenfolge).

### Added

- **Spalte „PV-Ertrag" in Tages-Energieprofile-Tabelle** (#494 dietmar1968). Tagessumme der PV-Erzeugung als neue default-visible Spalte in Gruppe „Tages-Summen". Wert = Σ über alle `komponenten_kwh`-Keys mit Prefix `pv_` oder `bkw_` (`snapshot/aggregator.py:get_komponenten_tageskwh`). Storage-Migration v1→v2 in localStorage ergänzt die Spalte für existierende User automatisch, ohne deren Spalten-Anpassungen zu überschreiben.

### Changed

- **Live-Header entanimiert** (#207 Rainer per PN + dietmar1968 Forum #345 + detLAN). Pulsierender `animate-ping`-Punkt + `animate-spin`-Refresh-Spinner produzierten auf schmalen Fenstern Layout-Sprünge ohne UX-Mehrwert (der Update-Timestamp zeigt eh den Stand). Statischer grüner Punkt bleibt als Online-Indikator, von links nach rechts neben Update-Zeile verschoben (detLAN-Vorschlag) — konsolidiert zwei Status-Inseln zu einer. Drei unabhängige User-Meldungen haben den Ausschlag für die Kehrtwende gegeben.
- **Sechs überflüssige Page-Überschriften entfernt** (#218 detLAN). Jeder Sub-Tab benennt seinen Bereich schon — eine darunter wortgleiche h1 frisst nur Platz: Einstellungen → Anlage(n) / Strompreise / Investitionen / Sensor-Zuordnung / Statistik-Import; plus MQTT-Export (#218 P11), wo die Überschrift „HA-Sensor-Export" zudem nicht zum Sub-Tab passte → komplett raus, die Info-Box darunter erklärt schon. Sub-Tab „Anlage" → „Anlagen" umbenannt (Konsistenz zum Plural-Inhalt). Container-Layouts dabei von `justify-between` auf `justify-end` umgestellt, wo nur noch eine Action-Bar übrig bleibt.
- **Vier Refresh-Icons als Schaltfläche statt flach** (#217 detLAN, Folgepunkt zu #209 P6). Aktualisieren-Knöpfe in Solarprognose-Setup, Daten-Checker, MQTT-Export und System-Einstellungen waren bisher nackte Icons im `text-gray-500`-Stil — andere Action-Bars in der App nutzen `<Button variant="secondary">`. Vier Stellen einheitlich auf Icon + „Aktualisieren"-Label gebracht.
- **Komponenten-Reihenfolge auf SoT `INVESTITION_TYP_ORDER` gebracht** (#215 detLAN, Folgepunkt zu #211 P4). Vier Stellen im Community-Bereich hatten unterschiedliche Reihenfolgen — Balkonkraftwerk landete oft ans Ende statt zwischen Speicher und WP, E-Auto stand stellenweise vor Wallbox. Statistiken-Tab (Ausstattung + Quoten-Cards), Übersicht-Tab (Komponenten-Benchmarks), Komponenten-Tab (Deep-Dives) auf `Speicher → BKW → WP → Wallbox → E-Auto` ausgerichtet.

---

## [3.27.4] - 2026-05-12 — Wärmepumpen-Aggregation: Split-Strommessung + Counter-Spike-Cap (#230)

> 🪛 **Zwei strukturelle Lücken im Snapshot-Aggregations-Pfad**, beide aus Martins Forum-Befund (#230). Setups mit getrennter Strom-Messung für Heizen/Warmwasser (seit #191 unterstützt) hatten in der Stundenwerte-Tabelle des Energieprofils eine leere Wärmepumpe-Spalte, und WP-Kompressor-Start-Counter-Spikes aus HA-Statistics-`sum`/`state`-Mix (siehe #184) standen als 49.000+-Werte in einer einzelnen Stunde, während die Tages-Boundary-Diff sauber bei 0 lag.

### Fixed

- **Wärmepumpe-Spalte in Stundenwerte-Tabelle leer trotz korrekt gemappter Strom-Heizen/-Warmwasser-Sensoren** (#230 MartyBr). Wer im Sensor-Mapping `getrennte_strommessung=True` setzt und die Sensoren `strom_heizen_kwh` + `strom_warmwasser_kwh` mappt, hatte zwar im Live-Tagesverlauf eine sichtbare WP-Kurve (Live-Pfad liest HA direkt), aber die Auswertungs-Stundenwerte blieben leer und die Tages-Heatmap zeigte für die WP nichts. Ursache: `KUMULATIVE_ZAEHLER_FELDER["waermepumpe"]` in [keys.py:23](eedc/backend/services/snapshot/keys.py#L23) kannte nur den Single-Sensor `stromverbrauch_kwh` und die thermischen Felder `heizenergie_kwh`/`warmwasser_kwh`; die Split-Sensoren wurden vom Snapshot-Writer per `_is_kumulativ_feld`-Whitelist silently gedroppt, also nie in `sensor_snapshots` geschrieben. `_categorize_counter` summierte zudem nur `stromverbrauch_kwh` als `verbrauch_wp`, und `get_komponenten_tageskwh` hatte einen semantisch falschen Fallback `heizenergie + warmwasser` (thermische Wärmeabgabe, nicht elektrischer Verbrauch — Faktor 4-5× zu hoch). Dreifach-Fix: Whitelist erweitert (Split-Felder mit aufgenommen), `_categorize_counter` fall-abhängig nach `parameter.getrennte_strommessung` (analog zur SoT `get_wp_strom_kwh()` in `field_definitions.py`), `get_komponenten_tageskwh` mit korrekter Split-Sensor-Summe statt thermischem Fallback. Anwender mit `getrennte_strommessung=True` müssen nach dem Update einmal in der Reparatur-Werkbank den betroffenen Zeitraum vollbackfillen, damit fehlende Snapshots aus HA-Statistics nachgezogen werden.
- **WP-Starts-Spike (49.073) in einzelner Stunde der Stundenwerte-Tabelle, während Tages-Tab denselben Tag mit 0 Starts zeigt** (#230 MartyBr). Klassischer Drift zwischen `get_daily_counter_deltas_by_inv` (Boundary-Diff `snap[24:00] − snap[00:00]`, ignoriert Mitten-Spikes) und `get_hourly_counter_sum_by_feld` (24× `snap[h] − snap[h-1]`, sieht jeden Snapshot). Wenn HA-Statistics nach Restart `sum=NULL` liefert und der `state`-Fallback einen Lifetime-Counter-Wert (Größenordnung 10⁴+) zurückgibt, landet dieser als Snapshot in der DB; der Stunden-Pfad rechnet die nachfolgende negative Differenz korrekt auf 0, aber der Spike-Slot selbst stand ungeklemmt. Plausibilitäts-Cap `MAX_PLAUSIBLE_COUNTER_PER_HOUR = 200` ergänzt — WP-Kompressor-Starts sind physikalisch durch Mindeststillstand/-laufzeit auf realistisch < 20/h begrenzt, 200 ist eine 10×-Sicherheitsmarge. Bei Überschreitung Clamp auf 0 + Logwarnung. Nach Reparatur-Werkbank-Reaggregation des Tages bereinigt sich die Anzeige.

### Internal

- `KUMULATIVE_ZAEHLER_FELDER["waermepumpe"]` erweitert um `strom_heizen_kwh` + `strom_warmwasser_kwh`; `_categorize_counter` parameter-sensitiv (getrennte_strommessung); `get_komponenten_tageskwh` analog. Sieben Akzeptanz-Tests in `test_wp_aggregator_bugs.py` (drei für Kategorisierung, zwei für Tages-Summe, zwei für Counter-Cap). Smoke grün: 217 Routes + 38 Tests.

---

## [3.27.3] - 2026-05-12 — Folge-Päckchen Tester-Bugs (#220 #222 #226 #227 #228)

> 🪛 **Reaktion auf v3.27.2-Tester-Feedback + drei neu gemeldete Bugs.** Rainer (#220) und NongJoWo (#222) hatten gemeldet, dass v3.27.2 ihre Probleme nicht gelöst hat — diesmal mit echten Logs/Reproduktionsdaten, sodass die tatsächlichen Bug-Pfade gefunden werden konnten. Plus drei frische Issues von JanKgh und NongJoWo (#226 #227 #228). Alle fünf Fixes lokal reproduziert + verifiziert.

### Fixed

- **CSV-Export "Failed to fetch" trotz HTTP 200 OK** (#220 rapahl). Rainers Backend-Logs zu v3.27.2 zeigten: Server antwortet sauber 200 OK, der Browser bricht trotzdem ab. Ursache: `Content-Disposition`-Header mit `filename=` enthielt den **Anlagenname ungefiltert** — bei Sonderzeichen (Umlaute, Leerzeichen, Semikolon, Quotes) wird der Header ungültig und HA-Ingress oder fetch() schließen den Stream als "Failed to fetch". Frontend ([Import.tsx:124](eedc/frontend/src/pages/Import.tsx#L124)) sanitisierte schon — Backend tat es nicht. Fix: `_sanitize_column_name()` (existierender Helper) auf Anlagenname anwenden + Filename mit doppelten Quotes umschließen. Lokal mit 7 problematischen Namen verifiziert (Leerzeichen, Ä/Ö/Ü/ß, /, ;, "...", Newline).
- **Custom-Import-Vorschau ignorierte auto-erkannte Investitions-Spalten** (#222 NongJoWo). NongJos v3.27.2-Fix-Versuch traf den falschen Crash-Pfad. Echtes Problem (mit seiner CSV reproduziert): wenn die Anlage eine passende Investition hat (z. B. "Wollis-ID5"), erkennt der Analyze-Schritt die Spalten via Suffix-Match → Frontend setzt sie auf "Ignorieren". Beim Apply würden sie automatisch importiert. Preview kannte aber nur das Mapping, nicht die Auto-Erkennung → 29 Zeilen ohne globale Felder gemappt → `monate=[]` → 400-Fehler. Fix: Preview-Endpoint optional um `anlage_id` erweitert, ruft dann selbst `_detect_investition_spalten()` und wertet diese Spalten als gültige Daten-Marker. Frontend reicht `selectedAnlageId` durch. Lokal mit NongJos CSV verifiziert (29 Monate + Hinweis-Warnung statt 400).
- **Datenchecker mahnte Batterie-Daten für Monate vor Speicher-Installation** (#226 JanKgh). Setup: PV seit 11/2021, Speicher erst ab 11/2022. Datenchecker prüfte nur `"speicher" in aktive_typen` ohne Datums-Match → warnte für 12 Monate Batterie-Daten an, die per Konstruktion nicht existieren können. Fix: neue Bedingung `speicher_aktiv_monate` (set), die pro Monat prüft, ob mindestens ein Speicher zu diesem Zeitpunkt aktiv war (Anschaffung erfolgt, kein Stilllegung). Lokal mit verschobenem Anschaffungsdatum verifiziert (0 Vor-Anschaffungs-Warnungen, Folgemonate-Logik unverändert).
- **Tagesverlauf: Wallbox + E-Auto Pool-Doppelzählung** (#227 JanKgh). Wenn beide Investitionen denselben Leistungs-Sensor nutzen (typisch wenn `parent_investition_id` nicht gesetzt ist) und im Stacking addiert werden, ist Σ Verbrauch um die Fahrzeug-Ladung zu hoch. Bestehender Schutz greift nur bei expliziter parent-Verknüpfung. Defensiver Code-Fix in `live_tagesverlauf_service.py`: nach Serien-Aufbau Deduplizierung per Leistungs-Entity, Wallbox vor E-Auto priorisiert. Workaround per UI (parent setzen) bleibt der saubere Pfad.
- **Vollzyklen-Tooltip mit 13 Nachkommastellen** (#228 NongJoWo). `<ChartTooltip decimals={1} />` im Vollzyklen-pro-Monat-Chart wurde im ELSE-Branch (kein unit, kein formatter) auf `String(val)` umgeleitet und ignorierte decimals → "10.5252891704708..." statt "10,5". Fix: decimals wird jetzt unit-unabhängig respektiert, Default zu `undefined` (statt 0) gesetzt. Bonus: deutsches Komma-Format wird auch ohne unit angewandt.

---

## [3.27.2] - 2026-05-11 — Tester-Bugfix-Päckchen (#220 #222 #223)

> 🪛 **Patch-Päckchen, drei Tester-Bugs hintereinander erledigt:** ein CSV-Export-Crash mit Stream-Abbruch („Failed to fetch"), eine unbrauchbare Fehlermeldung in der Custom-Import-Vorschau und eine Doppelzählung im T-Konto der Monatsberichte. Alle drei wurden von Anwendern gemeldet (rapahl, NongJoWo) und ließen sich lokal mit Demo-Daten reproduzieren — kein Hypothesen-Stack, jede Diagnose mit Traceback bzw. Berechnungs-Vergleich bestätigt.

### Fixed

- **CSV-Export brach mit „Failed to fetch" ab, wenn Sonderkosten als String in der DB lagen** (#220 rapahl). `berechne_sonstige_summen` und `get_sonstige_positionen` in [eedc/backend/utils/sonstige_positionen.py](eedc/backend/utils/sonstige_positionen.py) crashten mit `TypeError`, sobald ein `sonderkosten_euro`- oder `sonstige_positionen[*].betrag`-Wert als String statt Number gespeichert war (z. B. `"150,00"` mit deutschem Komma). Das passierte still — der Frontend-Stream brach mittendrin ab und der Browser zeigte nur „Failed to fetch", ohne Hinweis worauf. Neuer `_safe_float()`-Helper akzeptiert int/float, `"150"` und `"150,00"`, alles andere fällt sauber auf 0 zurück statt zu crashen. Profitieren tut nicht nur der CSV-Export — derselbe Helper wird auch von Cockpit-Komponenten, Aktueller-Monat-Aggregaten und dem ROI-Dashboard genutzt; dort hätte der Bug irgendwann denselben Crash ergeben.
- **Custom-Import-Vorschau warf „Keine gültigen Monatsdaten mit diesem Mapping gefunden", obwohl die Datei korrekt war** (#222 NongJoWo). Wer im Wizard zusätzlich zu den automatisch erkannten eedc-Investitions-Spalten auch noch manuell `inv:ID:feld`-Slots im Mapping wählte, sah die unhilfreiche Standard-Fehlermeldung. Vorschau erkennt jetzt `inv:`-Mappings als gültige Daten-Marker und gibt einen erklärenden Hinweis: „X Spalte(n) als Investitions-Daten gemappt — werden beim Import automatisch der zugehörigen Investition zugeordnet". Plus: bei wirklich leerer Vorschau zeigt die Fehlermeldung jetzt die `warnungen`-Diagnose (z. B. „247 Zeilen übersprungen — kein gültiges Jahr/Monat") und nennt konkrete Verdachtsfälle (Datums-Format ISO-Zeitstempel, Dezimalzeichen Punkt vs. Komma) statt nur „prüfe Jahr/Monat".
- **PV-Eigenverbrauch-Ersparnis im T-Konto enthielt Wallbox-PV-Ladung doppelt** (#223 NongJoWo). Backend berechnet `ev_ersparnis = eigenverbrauch_kwh × netzbezug_preis`, wobei `eigenverbrauch` den Direktverbrauch inkl. Wallbox-PV-Ladung umfasst ([calculations.py:128–132](eedc/backend/core/calculations.py#L128-L132)). Im T-Konto ([MonatsabschlussView.tsx:676](eedc/frontend/src/pages/MonatsabschlussView.tsx#L676)) wurde von diesem Wert nur BKW + Speicher abgezogen — die Wallbox-PV-Ladung stand parallel als separater „Wallbox — PV-Ladung-Ersparnis"-Posten und damit doppelt in Σ Haben. Filter erweitert um Wallbox-PV-Ladung (Label-spezifisch, damit die nicht doppelt-gezählte „Ersparnis vs. Verbrenner" unangetastet bleibt). Verifiziert mit Demo-Anlage: angereicherte 150 kWh Wallbox-PV-Ladung (= 45 €) ergab Korrektur in exakt dieser Höhe.

---

## [3.27.1] - 2026-05-10 — UX-Sprint A1+A2+A3 & Power-Sensor-Bug (#200)

> 🪛 **Bugfix-Release zwischen den Etappen.** Bündelt drei UX-Sprints aus dem detLAN-Cluster (#205/#206/#208/#209/#211/#212/#213/#214) und einen handfesten Datenintegritäts-Bug, den rcmcronny gemeldet hatte (#200): Leistungs-Sensoren (W/kW) ließen sich versehentlich in kWh-Slots des Sensor-Mappings eintragen, der Live-Heute-Pfad rechnete sie dann als kumulative Energie und produzierte Quatsch (mal 0, mal 1000+ kWh). Plus zentrale `INVESTITION_TYP_ORDER`-Konsolidierung — drei drift-anfällige Reihenfolge-Definitionen wurden auf eine einzige SoT zusammengeführt.

### Fixed

- **Power-Sensor in kWh-Slot rechnete Quatsch** (#200 rcmcronny). Wer einen Leistungs-Sensor (`unit=kW`, `device_class=power`) in einen kWh-Slot des Sensor-Mappings eingetragen hatte (z. B. „Netzbezug Tageswert"), bekam im Live-Heute-Pfad völlig falsche Tagessummen — meist nahe 0, gelegentlich 1000+ kWh. Drei Schutz-Stellen ergänzt: Live-Pfad (`live_history_service:_energy_delta`) prüft jetzt vor dem Stats-Lookup, ob der Sensor überhaupt eine Energie-Einheit hat, sonst Trapez-Integration der W-Werte (physikalisch korrekt). Stats-API (`ha_statistics_service:get_value_at`) gibt bei Sensoren ohne `has_sum` und Nicht-Energie-Einheit `None` statt rohen `state` zurück. Sensor-Mapping-Wizard zeigt eine Warnung „Einheit XXX passt nicht in einen kWh-Slot" mit Wegweiser zum Live-Sensoren-Slot, sobald ein W/kW-Sensor in einen kWh-Slot ausgewählt wird (nicht blockierend, mit Workaround-Hinweis).
- **Wallbox-Card im Dark Mode war rahmenlos** (#211 P1 detLAN). Die Komponenten-Karten in Community → Statistiken → Ausstattung nutzten dynamische Tailwind-Klassen (`bg-${color}-50`), die der JIT-Compiler beim Build wegpurged hat — bei Wallbox (cyan) war der Dark-Mode-Rahmen daher unsichtbar. Klassen jetzt in einer statischen Map ausgeschrieben; alle fünf Cards rendern zuverlässig.
- **Performance-Profil Radar-Chart Community-Linie verschmolz mit Gitterlinien** (#211 P2 detLAN). Community-Datenreihe war auf `#9ca3af` (gray-400) gesetzt — identisch zu den Polar-Grid-Linien. Im Dark Mode war die Linie kaum erkennbar. Farbe jetzt amber `#f59e0b` mit erhöhter Opacity 0.15.
- **Doppeltes Info-Icon in Aussichten → Prognosen** (#212 detLAN, schon in Sprint A1). Eine zweite AlertCircle-Instanz war versehentlich mitgerendert; Imports aufgeräumt.
- **Plural-Bug „1 Hinweise / 1 Warnungen" im Daten-Checker** (#214 detLAN, schon in Sprint A1). Singular/Plural sauber unterschieden.
- **Übernehmen-Knopf im Monatsabschluss-Wizard verdeckte Number-Input-Spinner-Pfeile** (#213 P1 detLAN, schon in Sprint A1). Knopf jetzt neben dem Input statt darüber, Zurück-Button auf `<Button variant="secondary">` umgestellt.

### Changed

- **Tab-Navigation in Auswertungen, Aussichten, Community jetzt als Schaltflächen** (#208 P1+P4+P5 detLAN). Statt der bisherigen Underline-Tabs jetzt eine einheitliche Pill-Style-Leiste (active = primary-Hintergrund, inaktiv = grau). Neue zentrale `<PillTabs>`-Komponente in `components/ui/` — drift-arme SoT für künftige Tab-Leisten.
- **Community-Hauptseite ohne Überschrift „Community"** (#208 P9 detLAN). Die Seitenüberschrift mit Users-Icon im Hauptmenü-Bereich war redundant zur Hauptnav. Onboarding-Empty-State (wenn noch nicht geteilt) behält die Überschrift als Orientierung.
- **Daten → Monatsdaten ohne Überschrift, Selektoren in einer Zeile, Anlage-Selektor verschwindet bei einer Anlage** (#209 P1+P2+P4 detLAN). Statt `<PageHeader title="Monatsdaten">` jetzt nur noch eine rechte Action-Bar mit Anlage-Select (nur sichtbar wenn ≥ 2 Anlagen), „Aus HA laden" und „Neuer Monat" — alles auf einer Zeile.
- **Cockpit Top-Banner kompakter** (#206 P1+P2 detLAN). Großes Home-Icon (h-8 w-8) entfernt, Anlagenname und kWp inline statt zweispaltig. Decoratives Calendar-Icon vor dem Jahres-Filter entfernt — es war nicht klickbar während der Share-Button daneben klickbar war (verwirrend, „weniger ist mehr").
- **„Erstellt mit EEDC" jetzt auch in der kompakten Share-Variante** (#206 P4 detLAN). Die ausführliche Variante hatte den Hinweis schon, in der kompakten fehlte er — jetzt konsistent in beiden, am Ende des Texts.
- **Wallbox vor E-Auto in Community Übersicht-Stärken/Schwächen + Komponenten-Tab + Empty-State** (#211 P4+P5 detLAN, schon in Sprint A1). Reihenfolge spiegelt Anwender-Workflow: Wallbox als Ladeinfrastruktur vor dem Fahrzeug.
- **Daten-Checker: Wärmepumpe vor Wallbox** (#214 Reihenfolge detLAN). Anomalie-Liste pro Komponente folgt jetzt der zentralen `INVESTITION_TYP_ORDER` (Wechselrichter → PV-Module → Speicher → Balkonkraftwerk → WP → Wallbox → E-Auto → Sonstiges) statt DB-Insert-Reihenfolge.
- **Jahresübersicht in Community → PV-Ertrag absteigend (neueste oben)** (#211 P3 detLAN).
- **Auto-Fill Ø-Temperatur im Monatsabschluss-Wizard** (#205-Bug Rainer, schon in Sprint A1). `WetterDatenResponse` und Open-Meteo-Archive ergänzt um `temperature_2m_mean`; Frontend füllt das Feld pro-Feld auto, wenn es leer ist und die Wetter-Daten verfügbar sind.

### Internal

- **Zentrale `INVESTITION_TYP_ORDER`-SoT** in `frontend/src/lib/constants.ts` und `backend/utils/investition_filter.py` (Spiegel). Vorher gab es drei abweichende Reihenfolge-Definitionen: `useSetupWizard.ts:INVESTITION_TYP_ORDER`, lokale `TYP_REIHENFOLGE` im PDF-Builder, neuer `lib/constants.ts`-Versuch. Konsolidiert auf eine SoT, alle Konsumenten umgestellt (5 Frontend-Stellen + Backend Daten-Checker + PDF-Builder). Neue Helper: `compareTyp` (Frontend) und `sort_investitionen_nach_typ` (Backend). `useSetupWizard.ts:INVESTITION_TYP_LABELS` entfernt — alle Konsumenten nutzen jetzt `TYP_LABELS` aus `lib/constants.ts`.
- **`<PillTabs>`-Komponente** als shared Sub-Tab-Primitive in `components/ui/`. Ersetzt drei nahezu identische, individuelle Tab-Implementationen in Auswertungen/Aussichten/Community. Tooltip-Support via `SimpleTooltip`, Beta-Badge integriert.
- **Smoke-Check vor Release** (Pre-Check via `scripts/smoke.sh`) bleibt grün: 217 Routes + 31 Akzeptanz-Tests.

---

## [3.27.0] - 2026-05-10 — Etappe 3d: Daten-Provenance & Reparatur-Werkbank

> 🧱 **Architektur-Etappe — sichtbar als Reparatur-Werkbank im Energieprofil + neue Schutz-Mechanik gegen Daten-Drift.** Vier Päckchen aus dem Etappe-3d-Detail-Konzept (`docs/KONZEPT-DATENPIPELINE.md`): Schema-Fundament für Quellen-Hierarchie pro Feld, Cloud-/CSV-/Backup-Pfade an Provenance angeschlossen, Konflikt-Resolver aktiviert, Reparatur-Orchestrator mit Plan-Vorschau + Apply-Pfad. Plus 3d-Etappenabschluss-Sprint mit drei pragma-verschobenen Refactoring-Tails und einer Pool-Bug-Konsistenz-Fix-Runde. Plus Test-Infrastruktur: pytest-Migration + Pre-Release-Smoke-Skript. Insgesamt 33 Commits seit v3.26.8 + Test-Infra-Commit.

### Added

- **Reparatur-Werkbank** im Energieprofil unter „Datenverwaltung" (Etappe 3d Päckchen 4). Operation-Auswahl (`REAGGREGATE_TODAY` / `REAGGREGATE_DAY` / `VOLLBACKFILL` / `RESET_CLOUD_IMPORT` / `KRAFTSTOFFPREIS_BACKFILL_*`), Plan-Vorschau zeigt **vor** dem Apply was sich an welchen Feldern ändert (gruppierte Diff-Tabelle, Sticky-Header, capped 200 Zeilen), Bestätigungs-Knopf „N Änderungen anwenden", AbortController + Cancel-Knopf nach 30 s, Verlauf-Akkordeon mit Audit-Log-Counter. Die alten Schnellbuttons bleiben als Wrapper bestehen.
- **Wizard-Hinweis „X Felder durch manuelle Werte geschützt — Reset über Reparatur-Werkbank wenn gewollt"** in Cloud-Import-Wizards + CSV-Apply (Etappe 3d Päckchen 2). Manuell gepflegte Werte überleben jetzt Cloud-/Portal-Apply auch bei `ueberschreiben=true` — die Quellen-Hierarchie blockiert die niedriger-priorisierten Schreiber pro Sub-Key, der Wizard zeigt sichtbar wie viele Felder betroffen waren.
- **Daten-Checker-Kategorie `PROVENANCE_CONFLICT`** (Etappe 3d Päckchen 3). Macht sichtbar, wenn Cloud-Werte versuchen, manuell gepflegte Werte zu überschreiben — ohne dass eine Reparatur-Werkbank-Aktion läuft.
- **Plan-API für Reparatur** als REST-Layer (`POST /api/repair/plan`, `POST /api/repair/execute/{id}`, `GET /api/repair/plans`, `DELETE /api/repair/plans/{id}`). Plan-Lookup über In-Memory-Cache mit 1 h Expiry; nach Ablauf liefert Execute `410 Gone`.
- **Test-Infrastruktur:** `eedc/backend/requirements-dev.txt` (pytest + pytest-asyncio, getrennt von Production), `eedc/pytest.ini` (`asyncio_mode=auto`), `scripts/smoke.sh` (Dev-venv + App-Boot mit Routen-Schwelle ≥217 + 31 Akzeptanz-Tests in einem Befehl). `scripts/release.sh` läuft Smoke-Check als Pre-Check vor dem Version-Bump.

### Changed

- **Quellen-Hierarchie pro Feld aktiv** (Etappe 3d Päckchen 1). 22 Source-Labels in fünf Stufen: `repair` > `manual:*` > `external:cloud_import:*` / `external:ha_statistics` / `external:portal_import` > `auto:monatsabschluss` > `fallback:*`. Höhere Priorität gewinnt; gleicher Rang folgt Last-Writer-Wins. Audit-Log dokumentiert jede Entscheidung (`applied` / `rejected_lower_priority` / `no_op_same_value`).
- **Manual-Form / Auto-Aggregation / HA-Stats-Import / Custom-Import / Live-Wetter / Kraftstoff-Preis-Service auf `write_with_provenance` umgestellt** (Etappe 3d Päckchen 3). Initial-Migration für Bestandsdaten markiert vorgefundene Werte als `legacy:unknown` — sie verlieren gegen jeden neuen Schreiber. Akzeptanz: manuelle Korrektur überlebt nächtlichen Auto-Aggregations-Job.
- **Pool-Doppelzählung E-Auto + Wallbox in Cockpit + Monatsbericht behoben** (3d-Etappenabschluss-Sprint, Folge zu Quick-Fix `92d522a8`). Bei Setups mit 1 E-Auto + 1 Wallbox produzieren beide Investitionstypen denselben Stromfluss aus zwei Perspektiven (Vehicle vs. Loadpoint) — Aufsummieren ergab z. B. PV-Anteil > 100 %. `cockpit/uebersicht.py` und `aktueller_monat._aggregate` (sensor-basierter Pfad ohne InvestitionMonatsdaten) ziehen jetzt das Quick-Fix-Pattern: getrennte Akkumulatoren `eauto_*` / `wb_*`, max-Pool pro Feld, PV ≤ Gesamt erzwingen, Dienstwagen-Filter (`ist_dienstlich`) früh. Saubere Trennung pro Fahrzeug folgt erst in Phase 2 des Wallbox/E-Auto-Konzepts.

### Internal

- **`backend/services/provenance.py`** mit `write_with_provenance()` + `write_json_subkey_with_provenance()` (Hierarchie-Check + No-Op-Detection + flag_modified-Pflicht + Append-Only-Audit-Log). 10 Akzeptanz-Tests grün.
- **`backend/services/import_writer.py`** als gemeinsamer Provenance-Wrapper für Cloud-/CSV-/Portal-Apply-Pfade. Per-Sub-Key-Hierarchie + Full-Payload-No-Op + `geschuetzt_count` / `geschuetzte_felder`-Antwort. 7 Akzeptanz-Tests grün.
- **`backend/services/repair_orchestrator.py`** mit `Operation`-Enum (7 Werte), `FieldDiff` / `Plan` / `Result`-Models, In-Memory-Cache + Lock + 1 h Expiry, `_reset_value_for_field` per SQLAlchemy-Reflection für NOT-NULL-Defaults, `RESET_CLOUD_IMPORT` mit `force_override` + providers-Filter. 8 Akzeptanz-Tests grün.
- **Schema-Migration:** `data_provenance_log`-Tabelle + `source_provenance`-JSON-Spalte in `monatsdaten` / `investition_monatsdaten` / `tages_zusammenfassung` / `tages_energie_profil` + `source_hash`-TEXT-Spalte in `monatsdaten` / `investition_monatsdaten`. Migrationen idempotent; Initial-Provenance läuft beim ersten App-Start nach Update einmalig.
- **Refactoring-Tails (3d-P3 + 3d-Etappenabschluss-Sprint):** `services/energie_profil_service.py` von 1224 → 360 → ~46 Zeilen reduziert (`rollup` / `backfill` / `scheduler_jobs` / `aggregator` / `_helpers` als Slices); `services/monatsabschluss_aggregator.py` neu; `routes/energie_profil.py` (1741 Z) in Paket `views.py` / `repair.py` / `_shared.py` / `__init__.py`-Fassade zerlegt; `routes/monatsabschluss.py` (1078 Z) in Paket `monatsabschluss/views.py` / `wizard.py` / `_shared.py`; `routes/custom_import.py` (1102 Z) in Paket `custom_import/analyze.py` / `preview.py` / `apply.py` / `templates.py` / `_shared.py`. App-Boot 217 Routen identisch zum Vor-3d-Stand.
- **31 Akzeptanz-Tests grün** (10 Provenance + 7 ImportWriter + 6 ProvenanceMigrate + 8 RepairOrchestrator). Tests bleiben rückwärtskompatibel als Standalone-Skripte aufrufbar; pytest collected sie ohne Code-Anpassung.

---

## [3.26.8] - 2026-05-09 — Etappe 3c: Energieprofil Read-/Write-Architektur konsolidiert

> 🧱 **Architektur-Etappe — Anwender-sichtbar als Konsistenz-Patch.** Vier Päckchen aus dem Etappe-3c-Detail-Konzept (`docs/KONZEPT-ENERGIEPROFIL-3C.md`): Slot-Konvention zwischen kWh- und Counter-Feldern symmetrisch, Tagesgesamt für Komponenten-Energien strikt aus Boundary-Diff (HA-konform), SensorSnapshots tragen einen Source-Marker als 3d-Schablone, Reaggregate-Modal trennt Resnap+Aggregat klar von „Nur neu rechnen". Verbessert die Self-Healing-Eigenschaften aus v3.26.6 strukturell — kein neuer Anwender-Knopf, sondern saubere Pfade darunter.

### Changed

- **Counter-Felder folgen jetzt der #144-Backward-Slot-Konvention** (Etappe 3c P2, E1). WP-Kompressor-Starts und alle künftigen Counter-Sensoren werden symmetrisch zu kWh-Slots auf das Stunden-Ende ausgerichtet (Slot N = Δ aus [N-1, N)). Vorher trug der Counter-Pfad noch die ursprüngliche Forward-Konvention der Snapshot-Erfassung — bei Re-Aggregation entstand dadurch eine Stunden-Verschiebung gegenüber der kWh-Heatmap. Bestehende Daten werden beim ersten App-Start nach Update einmalig idempotent migriert (`migrations`-Tabelle, kein User-Eingriff nötig). `BoundaryRange`-Helper als zentraler Slot-Cutoff für beide Aggregat-Typen.
- **Tagesgesamt für komponenten-kWh-Felder kommt strikt aus dem Boundary-Diff** (Etappe 3c P3, E2). Statt Slot-Σ über 24 Heatmap-Werte wird `snap(Folgetag 00:00) − snap(Tag 00:00)` als Tagessumme geschrieben — identisch zur Logik des HA Energy Dashboards. Dadurch sind EEDC-Tagessummen ab jetzt strukturell mit HA konsistent, auch wenn ein Slot durch Sensor-Reset/Spike degradiert ist. Slot-Σ bleibt unverändert für die Verteilungs-Heatmap, ist aber jetzt semantisch klar von der „Tagesgesamt"-Sicht (Boundary) getrennt.
- **Reaggregate-Modal trennt Resnap+Aggregat von „Nur neu rechnen"** (Etappe 3c P4, E4). Der Vorschau-Knopf zeigt zwei Aktionsbuttons statt einem: *Snapshots neu holen + Tagesaggregat rechnen* (langsam, ~275 HA-Stats-Queries) und *Nur neu rechnen* (sub-sekündlich, wenn Snapshots schon stimmen). Die heuristische Auto-Erkennung aus v3.26.6 setzt den Default, ist aber jetzt User-übersteuerbar — z. B. nach Sensor-Tausch sinnvoll, wenn Snapshots ungeprüft erscheinen. Cancel-Knopf erscheint nach 30 Sekunden Resnap-Laufzeit (bricht nur die Anzeige ab; der Backend-Job läuft idempotent zu Ende).

### Added

- **Source-Marker `quelle` auf SensorSnapshots** (Etappe 3c P1, E3). Jeder geschriebene Snapshot trägt jetzt eine Herkunftsnotiz — `ha_statistics`, `mqtt_inbound`, `mqtt_live`, `live_fallback`, `unknown`. Bestehende Snapshots bleiben auf `unknown` (rückwirkend nicht rekonstruierbar). Schablone für Etappe 3d (Daten-Provenance); wird in der Datenverwaltungs-Seite später sichtbar gemacht. Aktuell Lese-Konsument nur intern im Reaggregate-Pfad (welche Slots dürfen überschrieben werden).

### Internal

- **`sensor_snapshot_service.py` (1530 Zeilen) in 6 Slices zerlegt** als Refactoring-Tail von Päckchen 1. Schnittstelle nach außen unverändert; intern jetzt nach Reader / Writer / Aggregator / Counter-Logik / Migration / Range-Helper getrennt.
- **`aggregate_day` in eigenen Slice extrahiert** als Refactoring-Tail von Päckchen 3. Tagesaggregations-Logik nicht mehr in Snapshot-Service eingebettet.
- **Aufräum-Sprint Phase B Konzept-Docs auf v3.26.7-Stand**: 9 Konzept-Dokumente (KONZEPT-ENERGIEPROFIL, KONZEPT-INFOTHEK, KONZEPT-KORREKTURPROFIL, KONZEPT-MQTT-GATEWAY, KONZEPT-SPEICHER-AUSWERTUNG, KONZEPT-STROMPREIS-MITSCHRIFT, KONZEPT-UMFRAGE, KONZEPT-WALLBOX-EAUTO, KONZEPT-COCKPIT-LAYOUT) mit aktuellen Status-Headern und Implementierungstabellen. 10 abgeschlossene oder verworfene Docs nach `docs/archive/` verschoben (Solcast-Konzept, What's-new-Banner, Standalone-API-Stub, Drift-Audit-Vorbereitungen, Doku-Sweep-Arbeitsdoku, PN-Drafts). KONZEPT-LIVE-SNAPSHOT-5MIN von `drafts/` nach `docs/` befördert.
- **Etappe-3c-Detail-Konzept** als `docs/KONZEPT-ENERGIEPROFIL-3C.md` abgelegt (vier E-Entscheidungen, vier Päckchen P1–P4, Refactoring-Tails). Etappe-3d-Vorbereitungs-Konzept `docs/KONZEPT-DATENPIPELINE.md` parallel ausgearbeitet (5-Stufen-Hierarchie, Hybrid-Provenance, Konflikt-Resolver, Repair-Orchestrator).

---

## [3.26.7] - 2026-05-09 — UX-Bündel: Pfeile, Schreibweise, Seitentitel

> ✨ **Vier kleine UX-Verbesserungen aus aktivem Tester-Feedback in einem Patch.** Live-Heute Batterie-Pfeile alignieren mit dem HA Energy Dashboard, „eedc" und „Home Assistant App" werden durchgängig geschrieben, redundante Seitentitel im Cockpit/Auswertungen/Aussichten/Live-Daten/Community-Vergleich und mehreren Einstellungs-Seiten sind raus.

### Changed

- **Live-Heute Batterie-Pfeile angepasst an HA Energy Dashboard** (#201 detLAN). eedc zeigte ▲ Ladung / ▼ Entladung (Tank-Logik), HA zeigt umgekehrt: ▼ Strom in den Speicher rein, ▲ aus dem Speicher raus. eedc folgt jetzt der HA-Konvention. Auch in der Community-Regionen-Tabelle gleichgezogen.
- **Schreibweise „eedc" durchgängig vereinheitlicht** (#199 detLAN). Bisher gemischt EEDC/eedc, ab jetzt überall lowercase wie das Logo und CLAUDE.md-Konvention.
- **„Home Assistant Add-on" → „Home Assistant App"** durchgehend in user-sichtbaren Strings (#199). Die HA-eigenen Menü-Pfade (z. B. „Einstellungen → Add-ons → ⋮") und Verweise auf andere HACS-Add-ons (Solar Forecast ML) bleiben unverändert.
- **Redundante Seitentitel entfernt** (#196 detLAN). Die `<h1>`-Doppelung neben dem aktiven Tab/Sub-Tab in 14 Pages ist raus: Dashboard (Übersicht), Aussichten, Auswertung, Live-Daten, Community Vergleich, Daten-Checker, Backup, Solarprognose, Infothek, Einrichtung, Balkonkraftwerk/Speicher/E-Auto/Sonstiges Dashboards. Pages mit dynamischem Untertitel (Anlagenname, Investitions-Bezeichnung) bleiben unverändert — die Top-/Sub-Navigation zeigt die aktive Position bereits sichtbar.

### Internal

- **#200 Folge:** Der Code-Fix für die Live-Tageskonsumenten aus v3.26.6 (`a435a58f`) hatte Ronnys „warte auf Punkt 2"-Comment knapp überholt. Verifikations-Anfrage am Issue gepostet.

---

## [3.26.6] - 2026-05-08 — Reload-Vorschau heilt sich selbst: Counter-Boundary + „Nur neu rechnen"

> 🩹 **Folgehotfix nach v3.26.5** — der Reload-Pfad hatte zwei eng verwandte Lücken, die bei Forum-Tester MartyBr (Sensor-Migration Vicare→Optisplitter, Forum #462ff) sichtbar wurden: erstens überschrieb der Resnap die Folgetag-00:00-Boundary nicht, was den Counter-Tagesdelta auf falscher Skala stehen ließ. Zweitens hing das „Übernehmen" für Tage, deren Snapshots längst aktuell waren, im teuren HA-Stats-Polling fest, statt einfach nur das Aggregat neu zu rechnen. Beides gefixt — die Vorschau erkennt jetzt automatisch, ob Resnap nötig ist, oder ob ein „Nur neu rechnen" reicht.

### Fixed

- **Reload-Range schließt Folgetag 00:00 ein.** Bisher resnappte `reaggregate-tag` nur Vortag 23:00 .. Tag 23:00 — passgenau zur Backward-Konvention der kWh-Slots (#144). Counter-Felder (`wp_starts_anzahl`, etc.) lesen aber nach Forward (#136) und brauchen `snap(Folgetag 00:00) − snap(Tag 00:00)` bzw. `snap(Folgetag 00:00) − snap(Tag 23:00)` für Slot 23. Ohne diesen Boundary blieb ein alter (oft korrupter) Wert stehen und faltete sich beim Reload als Lifetime-Sprung in die Tagessumme. Range jetzt um eine Stunde verlängert; kWh-Konsumenten sind unberührt.
- **„Nur neu rechnen"-Pfad im Reload-Modal.** Wenn die Vorschau zeigt, dass alle Werte alt = neu sind (Snapshots stimmen mit HA-Stats überein, nur das gespeicherte Tages-Aggregat ist veraltet), schaltet der Übernehmen-Knopf automatisch auf `mit_resnap=false`. Damit entfallen 275 5-Min-HA-Stats-Queries plus die DELETE-Operationen für leere Slots — der Reload geht von „möglicherweise hängend" auf „sub-sekündlich". Hängt zusätzlich ein blauer Info-Hinweis im Modal („Snapshots sind bereits aktuell") und ändert das Knopf-Label auf „Nur neu rechnen".

### Internal

- **Konventionsfalle dokumentiert:** ausführlicher Code-Kommentar in `reaggregate_tag` zur Slot-Konvention (kWh Backward / Counter Forward) und warum die Boundary-Erweiterung NUR den Counter-Pfad heilt, ohne die kWh-Slot-Konvention anzufassen. Verhindert, dass künftige Refactor-Versuche den Konvention-Wechsel von #144 wieder kippen.

---

## [3.26.5] - 2026-05-07 — Setup-Vereinfachung: HA-Energiekonfiguration importieren + Counter im Reload-Vorschau (#197)

> ✨ **Wer schon ein HA-Energy-Dashboard eingerichtet hat, muss seine Sensoren nicht mehr ein zweites Mal von Hand raussuchen.** Beim Aufruf des HA-Sensor-Zuordnungs-Wizards liest EEDC `/config/.storage/core.energy` und befüllt die passenden Felder als Vorschlag vor: Netzbezug, Einspeisung, PV-Erzeugung, Batterie-Ladung/Entladung. Aus der `device_consumption`-Liste werden zusätzlich Wallbox / Wärmepumpe / E-Auto per Namens-Heuristik (Wallbox/go-eCharger/Keba/Tesla/Daikin/…) den passenden Investitionen zugeordnet. Ein Banner oberhalb des Wizards zeigt, wie viele Sensoren übernommen wurden, plus „HA-Energy-Vorschläge entfernen"-Knopf — der entfernt **nur** die unveränderten Vorschläge, manuell editierte Sensoren bleiben unangetastet.

### Added

- **Neuer Backend-Service `services/ha_energy_service.py`** liest `/config/.storage/core.energy`, parst `energy_sources` (grid/solar/battery) und `device_consumption`, und liefert Substring-basierte Typ-Erkennung für Wallbox / Wärmepumpe / E-Auto. Add-on-only — auf Standalone-Setups (kein `SUPERVISOR_TOKEN`) wird `available=false` zurückgegeben und der Wizard zeigt keinen Banner.
- **Neuer Endpoint `GET /api/sensor-mapping/{anlage_id}/suggest`** kombiniert die HA-Energy-Vorschläge mit den Investitionen der Anlage und liefert direkt anwendbare Sensor-Mapping-Vorschläge (Speicher → erste Speicher-Investition; device_consumption → erste passende Wallbox/WP/E-Auto-Investition).
- **Auto-Vorbefüllung im SensorMappingWizard** läuft beim ersten Aufruf (= leeres Mapping). Bei späterem Re-Aufruf zeigt der Wizard keinen Banner — manuelle Korrekturen werden nicht überstimmt.
- **Selektiver Reset-Knopf** im Banner: vergleicht den aktuellen Wizard-Zustand mit dem Snapshot der HA-Energy-Vorschläge und entfernt nur die Felder, die unverändert dem Vorschlag entsprechen. User-Anpassungen bleiben erhalten.
- **Counter-Tagesgesamt im Reload-Vorschau-Modal** macht reine Counter-Felder (z. B. WP-Kompressor-Starts) vor dem „Übernehmen" sichtbar — Tageszahl alt → neu, summiert über alle Investitionen pro Feld. Bisher zeigte die Vorschau nur kWh-Energiekategorien; Drift bei Counter-Sensoren nach HA-Restart-Spike fiel erst nach dem Klick auf. Boundary: `snap(Tag 00:00)` gegen `snap(Folgetag 00:00)`, alt aus DB, neu aus HA-Statistics.

### Internal

- **Heuristik-Reihenfolge im Service:** e-auto vor wallbox vor waermepumpe — damit Brand-Tokens wie `tesla` (= Auto) nicht durch das generischere `charger` (= Wallbox) überstimmt werden.
- **Default-Felder pro Investitions-Typ:** `wallbox→ladung_kwh`, `waermepumpe→stromverbrauch_kwh`, `e-auto→verbrauch_kwh`. Wenn das Default-Feld in der konkreten Investition nicht existiert (z.B. WP mit `getrennte_strommessung=true` hat kein `stromverbrauch_kwh`), wird der Vorschlag stillschweigend verworfen — User mappt manuell.
- **Field-Definitions sind SoT:** `get_felder_fuer_investition()` filtert die Vorschläge gegen die tatsächlich verfügbaren Felder pro Investition.
- **Smoketests grün:** Heuristik-Suite (12 Cases inkl. Brand-Edge-Cases), End-to-end gegen Winterborn-DB (5 Investitionen, 4 device_consumption-Einträge → 4 Matches inkl. Skip eines WP-Kandidaten ohne passende Investition).

---

## [3.26.4] - 2026-05-06 — Hotfix: Wetter-Backfill schließt jetzt auch die letzten 5 Tage

> 🩹 **Hotfix wenige Stunden nach v3.26.3** — der Wetter-Backfill ließ die letzten 5 Tage strukturell unbefüllt, weil Open-Meteo Archive sie wegen 2-5 Tage Reanalyse-Lag nicht hatte. Per Designkommentar sollten diese Tage über den Live-Forecast-Pfad in `aggregate_day` mitkommen — aber `_get_wetter_ist` routete für *alle* Tage außer heute auf den Archive-Endpoint, also auch für den Vortag, der dort noch fehlt. Resultat: Stratifizierungs-Card zeigte „5 Tage noch nicht geladen" und der Button lieferte „0 Stunden / 0 Tage" — Drift zwischen drei Read-/Write-Sites mit unterschiedlichen Cutoffs.

### Fixed

- **SoT-Helper `archive_cutoff()`** in `wetter_backfill_service.py` — eine zentrale Stelle definiert die Grenze zwischen Archive- und Forecast-Endpoint (`heute - ARCHIVE_LAG_TAGE`).
- **`_get_wetter_ist` in `energie_profil_service.py`** routet jetzt auf den Forecast-Endpoint für `datum >= archive_cutoff()`, nicht nur für `datum == heute`. Damit befüllt `aggregate_day` für den Vortag (oder rollende Heute-Aggregation) die Wetter-Spalten korrekt aus der Reanalyse-Approximation.
- **`wetter_backfill_anlage`** holt zwei Range-Calls statt einem: Archive für ältere Tage, Forecast für die jüngsten N Tage. Beide fließen in denselben `_fetch_und_update`-Helper (Code-Deduplikation). Status `ok` solange mindestens einer erfolgreich war.
- **Stratifizierungs-Card-Empty-State löst sich auf**, sobald der Backfill-Button geklickt wurde — alle backfill-baren Tage werden tatsächlich geladen, kein "5 Tage noch nicht geladen → 0 geladen"-Geisterbild mehr.

### Internal

- **Drift-Vermeidung** (Memory `feedback_aggregations_drift.md`): `ARCHIVE_LAG_TAGE` und `archive_cutoff()` sind die Single-Source-of-Truth, wird von Backfill und aggregate_day gleichermaßen importiert.
- **Live-Test gegen Open-Meteo** (gegen produktive API): Forecast-Endpoint mit `start_date/end_date` für 5 Tage in der Vergangenheit liefert Stundendaten (`cloud_cover/precipitation/weather_code`).

---

## [3.26.3] - 2026-05-06 — Hotfix: Aggregator schreibt Skalar auch ohne Day-Ahead-Stundenprofile

> 🩹 **Hotfix wenige Stunden nach v3.26.2** — der Aggregator brach mit `status="skipped" / grund="Keine Day-Ahead-Snapshots im Zeitraum"` ab, sobald `pv_prognose_stundenprofil` (seit v3.26.0 mitgeschrieben, vorher leer) im Auswertungszeitraum noch nicht aufgelaufen war. Bestehende Anlagen haben Tages-Prognose `pv_prognose_kwh` schon seit Monaten, aber das Stundenprofil erst seit Tagen — die Skalar-Stufe war damit auf den meisten Anlagen unerreichbar und der Live-Pfad fiel auf den Legacy-`_get_lernfaktor` zurück, statt auf den Korrekturprofil-Skalar.

### Fixed

- **Skalar-Stufe wird unabhängig vom Stundenprofil berechnet.** `_lade_tagesist_skalar` zieht die Tages-Aggregation jetzt direkt aus `(von, bis)` statt aus `prog_pro_tag.keys()`. Sonnenstand-Bin-Stufen bleiben leer, solange Stundenprofile fehlen — die Skalar-Stufe steht ab Tag 1 zur Verfügung.
- **Aggregator `status="ok"` auch bei reiner Skalar-Stufe.** Nur bei kompletter Datenleere (weder `pv_prognose_kwh` noch IST) wird noch geskipped. `tage_eingegangen` zeigt im UI die Skalar-Tagesanzahl, wenn keine Bin-Tage vorhanden sind.
- **Heatmap-Card mit Hinweis-Block,** wenn nur die Skalar-Stufe vorhanden ist: erklärt, dass Sonnenstand- und Wetter-Bins Day-Ahead-Stundenprofile (`pv_prognose_stundenprofil`) brauchen und sich über die nächsten Wochen organisch aufbauen.

### Internal

- **Smoketest erweitert** um den Fall „30 Tage Tagesprognose + IST, ohne Stundenprofile" → Skalar 0.88 geschrieben, Live-Lookup nutzt Stufe `skalar`. Empty-Anlage bleibt korrekt skipped.

---

## [3.26.2] - 2026-05-06 — Päckchen 2 Korrekturprofil (Sonnenstand × Wetter live)

> ✨ **Päckchen 2 von zwei** — das in v3.26.0 angelegte stündliche Korrekturprofil ist jetzt produktiv. Pro Live-Forecast-Stunde wird die OpenMeteo-Strahlung mit einem Faktor multipliziert, der aus `(azimut_bin, elevation_bin, wetterklasse)` aus der historischen IST/Day-Ahead-Aufschlüsselung kommt. Fallback-Kaskade hält den Pfad für datenarme Anlagen sanft auf den klassischen Skalar-Lernfaktor.

### Added

- **`Korrekturprofil`-Tabelle** (`korrekturprofile`) mit `(anlage_id, investition_id, quelle, profil_typ)` als Scope. JSON-Felder `bin_definition`, `faktoren`, `datenpunkte_pro_bin` tragen alle drei Profil-Stufen ohne Schema-Änderung. Tabelle wird beim Backend-Start via `create_all` automatisch angelegt; bestehende Installationen brauchen keine manuelle Migration.
- **Solar-Position-Helper** (`services/wetter/solar_position.py`) — vereinfachter NOAA-Algorithmus, ~0.1° Genauigkeit, keine externe Astro-Dependency. Lokalzeit-Konvertierung über `zoneinfo` mit `Europe/Berlin`-Default und Längengrad-basiertem Fallback.
- **Korrekturprofil-Aggregator** (`services/korrekturprofil_aggregator.py`) — schreibt drei Profil-Stufen pro Anlage:
  - `sonnenstand_wetter` (primär, ~150–200 belegte Bins × 3 Klassen)
  - `sonnenstand` (Fallback ohne Wetter-Achse)
  - `skalar` (O1+O2-Tagesfaktor als letzter Fallback)
  Idempotent, clamp `[0.5; 1.3]`, Mindest-Summe 1 kWh pro Bin gegen Mini-Quotienten-Verzerrung.
- **Live-Pfad-Lookup** (`services/korrekturprofil_lookup.py`) mit Fallback-Kaskade und Anlagen-Cache (TTL 1h). Schwellen pro Stufe: ≥10 Datenpunkte (sonnenstand_wetter), ≥15 (sonnenstand), ≥7 Tage (skalar). Aggregator invalidiert Cache nach Re-Build automatisch.
- **`get_live_wetter` ersetzt globale Skalar-Multiplikation** durch Pro-Stunde-Lookup. Bei fehlendem Profil oder zu wenigen Datenpunkten fällt der Pfad auf den existierenden `_get_lernfaktor`-Skalar zurück (bewusste Variante 1: Sanftverlauf statt Feature-Flag).
- **Scheduler-Job `korrekturprofil_aggregation`** täglich um 02:30 (zwischen Energie-Profil-Recovery 02:15 und MQTT-Cleanup 03:00). Iteriert über alle Anlagen mit Koordinaten.
- **Endpoints** `POST /api/korrekturprofil/{anlage_id}/aggregate` (manueller Re-Build) und `GET /api/korrekturprofil/{anlage_id}/profile` (Lesen für Frontend).
- **Heatmap-Card im Prognosen-Vergleich-Tab** (`KorrekturprofilHeatmapCard.tsx`) — Klassen-Tabs (klar / diffus / wechselhaft / Alle), Azimut × Elevation als Farbverlauf, Empty-State mit Aggregator-Trigger, Stats-Zeile mit Tage/Bins/Skalar.

### Changed

- **`live_wetter.py`** — Skalar-Lernfaktor wird zum Fallback hinter dem Pro-Stunde-Korrekturprofil-Lookup. Bestehende `_get_lernfaktor_detail`-Logik unverändert; nur die Anwendung im Forecast-Loop ersetzt.

### Internal

- **End-to-end-Smoketest** (in-memory SQLite, 9 Tests): skipped-Pfade (no geo, no snapshots), ok-Pfad (60 synth Tage → 43 Bins + Skalar 0.8), Lookup-Kaskade über alle drei Stufen, Cache-Invalidation, Idempotenz, fehlende Anlage → None (Caller-Fallback).
- **`profil_typ='stunde'`** im Schema vorgesehen, vom Aggregator bewusst nicht geschrieben — Sonnenstand-Bins decken denselben Effekt physikalisch sauberer ab; die Saisonbin × Stunde-Stufe ist konzept-doku-konform durch die direkte Skalar-Stufe ersetzt.

---

## [3.26.1] - 2026-05-06 — Hotfix: Backfill-Button auch ohne Day-Ahead-Stundenprofile

> 🩹 **Hotfix wenige Stunden nach v3.26.0** — der "Wetter-Historie nachladen"-Empty-State erschien auf vielen Anlagen gar nicht, weil mein Trigger fälschlich an `pv_prognose_stundenprofil` hing (Day-Ahead-Snapshot, first-write-wins, auf vielen länger laufenden Anlagen lückenhaft befüllt). Das hat das Hauptfeature von v3.26.0 unsichtbar gemacht.

### Fixed

- **Empty-State-Trigger entkoppelt vom Day-Ahead-Snapshot.** Backend-Endpoint `/api/korrekturprofil/{id}/stratifizierung` liefert jetzt zusätzlich `tep_tage_ohne_wetter` — Tage im Auswertungszeitraum, an denen mindestens eine `TagesEnergieProfil`-Zeile noch kein Wetter trägt. Frontend-Empty-State zeigt den Backfill-Button bereits, sobald dieser Wert > 0 ist.
- **Erklärtext im Empty-State angepasst** je nach Datenlage: wenn Day-Ahead-Snapshots existieren → "Card füllt sich danach mit MAE/MBE pro Klasse"; wenn nicht → "Stratifizierungs-Tabelle bleibt vorerst leer, die Wetter-Daten dienen Päckchen 2".

---

## [3.26.0] - 2026-05-06 — Päckchen 1 Korrekturprofil-Konzept

> ✨ **Daten-Layer + Skalar-Verbesserung für das geplante stündliche Korrekturprofil.** Päckchen 1 von zwei: bringt stündliche Wetter-Daten (Bewölkung, Niederschlag, WMO-Code) in `TagesEnergieProfil`, einen Open-Meteo-Archive-Backfill für 2 Jahre Historie, eine zweite Berechnungsvariante des Lernfaktors (Trim-Mean + Recency-Boost, läuft parallel zum Live-Faktor zu Diagnose-Zwecken) und zwei additive Diagnose-Cards im Prognosen-Vergleich-Tab. Die Solcast-Spalte und die Tab-Struktur bleiben unverändert. Päckchen 2 (Sonnenstand-Bin × Wetterklasse als kombinierter stündlicher Korrekturfaktor) folgt nach Beobachtungs-Phase.

### Added

- **Stündliche Wetter-Spalten in `TagesEnergieProfil`** — `bewoelkung_prozent`, `niederschlag_mm`, `wetter_code` werden bei der täglichen Aggregation automatisch aus dem bereits laufenden Open-Meteo-Fetch mitgeschrieben. DB-Migration läuft beim Backend-Start additiv. Speicheraufwand vernachlässigbar (~3 Floats × 24 h × 365 × 2 Jahre pro Anlage).
- **Wetter-Backfill-Service + Endpoint** (`POST /api/korrekturprofil/{anlage_id}/wetter-backfill`) — füllt fehlende Wetter-Felder rückwirkend aus Open-Meteo Archive (ERA5-Reanalyse, gratis, 2 Jahre). Strikt additiv: bestehende Werte werden nicht überschrieben. Idempotent. Free-Tier-konform (~30 Calls pro Anlage für 2 Jahre).
- **Wetter-Klassifikations-Helper** (`klassifiziere_stunde()`, `klassifiziere_tag()`) in `services/wetter/utils.py` — drei Klassen (klar / diffus / wechselhaft) mit Schwellen aus Bewölkung, Niederschlag und WMO-Code. Niederschlag-Marker und WMO-Sicht-Beeinträchtigung dominieren.
- **O1 Recency-Boost + O2 Trim-Mean als Doppel-Variante des Lernfaktors** — `_aggregiere_o12()` läuft parallel zum Legacy-Aggregator auf den gleichen Tagen. Trim-Mean entfernt Sensor-Aussetzer (oberste/unterste 10 % der Tagesquotienten); Recency-Boost gewichtet Tage jünger als 30 Tage mit +30 % stärker. Live-Pfad nutzt weiter den Legacy-Faktor — Aktivierung als Default erst nach mehrwöchiger Beobachtung.
- **Stratifizierungs-Endpoint** (`GET /api/korrekturprofil/{anlage_id}/stratifizierung?tage=90`) — wetter-stratifizierte Stunden-Genauigkeit (MAE/MBE in % vom IST) der Day-Ahead-Prognose pro Wetter-Klasse, plus Aufschlüsselung pro (Klasse × Stunde) als JSON-Map.
- **Diagnose-Cards im Prognosen-Vergleich-Tab** (additiv, ändert nichts an bestehenden Inhalten) — *Lernfaktor-Doppel-Variante* (Legacy vs. O1+O2 mit Δ-Anzeige) und *Wetter-Stratifizierung* (Tabelle MAE/MBE pro Klasse). Beide rendern conditional nur wenn Daten vorhanden sind.
- **Empty-State-Button „Wetter-Historie nachladen"** in der Stratifizierungs-Card. Wenn Day-Ahead-Snapshots vorhanden sind aber Wetter-Historie noch fehlt (typisch direkt nach dem Update), bietet die Card einen Klick-Trigger für den 2-Jahres-Backfill an. Status-Anzeige (lädt / X Stunden geladen / Fehler) inline. Kein automatischer Backfill beim Backend-Start — User behält Kontrolle, kein Quota-Spike beim Add-on-Update.

### Changed

- **`prognosen.py` Response erweitert** um `eedc_lernfaktor_o12` und `eedc_lernfaktor_o12_delta_pct`. Bestehende Felder unverändert, Frontend-Konsumenten ohne O12-Awareness brechen nicht.
- **`_berechne_faktor` intern refaktoriert** in `_filtere_tage` + `_aggregiere_legacy`. Backwards-Compat-Alias bleibt, externe Aufrufe weiter funktionsfähig.
- **`_get_wetter_ist`** holt zusätzlich `cloud_cover`, `precipitation`, `weather_code` aus Open-Meteo Forecast/Archive (kostet keinen extra Call, die Variablen sind im selben Endpoint).

### Documentation

- **`docs/KONZEPT-KORREKTURPROFIL.md` v3 verabschiedet** — ersetzt v2 vom 2026-05-03. Varianten A/B/C nicht mehr „nur reaktiv", sondern: eine geplante Ziel-Architektur (Sonnenstand-Bin × Wetterklasse als kombinierte Tabelle, kein multiplikatives Splitting), zwei Päckchen, Variante C bleibt reaktiv. Solcast-Spalte ausdrücklich „bleibt — Tester-Pakt mit Rainer".

### Internal

- **Konzept-Doku zur multiplikativen Faktoren-Trennung** verworfen: Verschattung × Wetter ist eine echte Interaktion, multiplikatives Splitting wäre identifizierungs-bedingt ill-posed. Stattdessen kombinierte Tabelle mit Fallback-Kaskade.
- **Backfill ist additiv** (Marker-Spalte `bewoelkung_prozent IS NULL`) — `feedback_vollbackfill_nur_additiv.md`-Linie konsequent fortgesetzt.

---

## [3.25.23] - 2026-05-05

> 🩹 **Tab-Bildlaufleiste auf drei Seiten weg (#193 detLAN)** — Patch-Release mit nur einem UI-Fix.

### Fixed

- **Keine permanent sichtbare Scrollbar mehr unter den Tabs auf Auswertung / Aussichten / Community (#193 detLAN)** — Die Tab-Header-Zeilen dieser drei Pages tragen jetzt die bereits in `SubTabs.tsx` und `MonatsabschlussView.tsx` etablierte `scrollbar-none`-Utility auf ihrem `<nav>`-Element. Ursache: das `overflow-x-auto` für horizontales Tab-Scrolling rendert auf Desktop-Browsern und in der HA Companion-App eine permanente graue Scrollbar-Spur, die wie ein Layout-Bug wirkt. Funktional bleibt alles erhalten — Tabs lassen sich weiter per Touch/Wheel/Drag horizontal wischen.

---

## [3.25.22] - 2026-05-05

> 🩹 **Vollbackfill-Aufräumen + drei Folge-Items aus #190/#191/#182** — Klausnns Hänger im „Lücken überschreiben"-Modus (#190) hat eine Architektur-Frage aufgedeckt: der Overwrite-Modus war ein Recovery-Tool aus Bug-Zeiten und richtet seit den 3.25.x-Counter-Fixes nur noch Schaden an. Er ist deshalb komplett raus. Plus: WP-Strom-Splits im Monatsbericht (#191 rapahl), Scroll-Position beim Monatswechsel (#182 detLAN), Skip-Transparenz im Vollbackfill-Banner (#190 Klausnn).

### Changed

- **Vollbackfill ist nur noch additiv (#190 Klausnn → Architektur)** — Der Modus „Bestehende Tage überschreiben" + die zugehörige Pre-Backfill-Resnap-Schleife sind aus dem Code raus. Hintergrund: Der Overwrite-Pfad war ein Recovery-Tool für alte Aggregations-Bugs (Off-by-one in `get_value_at` v3.25.9, sum/state-Mix #184, Vortag-Boundary, Counter-Doppelzählung). Nach v3.25.20 sind diese Bugs gefixt — der Recovery-Bedarf entfällt. Gleichzeitig hat der Modus dauerhaften Datenverlust verursacht: HA-LTS reicht in vielen Setups (Recorder-Purge, Sensor-Umbau) kürzer zurück als das gepflegte Profil. „Löschen + neu rechnen" als Reflex bei Datenmisstrauen löschte dann Wochen oder Monate Historie unwiederbringlich. Korrekturprofil, saisonale Mustersuche, Speicher-Simulation und Verschleißkurven hängen aber an dieser Tiefe. Konkrete Code-Änderung: `backfill_from_statistics` und `resolve_and_backfill_from_statistics` haben den `skip_existing`/`overwrite`-Parameter verloren und sind hardcoded additiv. Der Endpoint `/vollbackfill?overwrite=...` akzeptiert den Param weiter (deprecated), ignoriert ihn aber und schreibt eine Info-Zeile ins Log — schützt alte Frontend-Caches und API-Konsumenten vor Crashes.
- **UI: „Vollbackfill" → „Energieprofil-Lücken aus HA-Statistik nachfüllen"** — Der Knopf in **Daten → Energieprofil** und die Wizard-Box im Sensor-Mapping heißen jetzt klar nach dem, was sie tun. Die Overwrite-Checkbox ist weg, die rote „Empfohlen nach Updates"-Empfehlungsbox ebenso (sie verwies auf den jetzt obsoleten Overwrite-Modus). Stattdessen ein nüchterner Hinweis auf den Reparatur-Pfad: „Möchtest du einen einzelnen Tag reparieren, der verzerrt aussieht? Nutze den Daten-Checker und den Reload-Knopf in der Tagestabelle (mit Vorschau vor Übernahme)."

### Added

- **Monatsbericht WP: Strom-Splits Heizung/Warmwasser sichtbar (#191 rapahl)** — Wer in der Wärmepumpe-Investition `getrennte_strommessung=true` aktiviert hat (Rainer war Ideengeber dafür), sieht jetzt im Monatsbericht unter „Stromverbrauch" zwei „davon"-Zeilen: Heizung und Warmwasser. Konsistent zur bereits vorhandenen Wärme-Aufteilung darunter. Daten waren in `InvestitionMonatsdaten.verbrauch_daten` schon vorhanden (`strom_heizen_kwh` / `strom_warmwasser_kwh`), wurden aber von der `aktueller-monat`- und `monatsdaten/aggregiert`-API nicht herausgereicht. Beide Endpoints + die Pydantic-Response-Models + die TypeScript-Types kennen die Felder jetzt; das Frontend rendert sie nur, wenn das Backend nicht-`null` schickt — Anlagen ohne getrennte Messung sehen die Zeilen weiter nicht.
- **Vollbackfill-Banner zeigt Skip-Gründe (#190 Klausnn)** — Bisher meldete der Erfolgs-Hinweis nur „X von Y Tagen geschrieben" — der Cap bei z.B. 79,4 % wirkte wie Datenverlust. Tatsächlich werden Tage übersprungen, wenn HA für den Tag keine Statistics-Werte hat (Sensor existierte noch nicht, HA-Recorder war down, …). Das Banner unterscheidet jetzt explizit: „X Tage geschrieben · Y Tage ohne HA-Statistics-Daten übersprungen · Z Tage bereits vorhanden". Backend-Response (`/energie-profil/{id}/vollbackfill`) liefert die Werte als `uebersprungen_keine_daten` und `uebersprungen_existiert`. `BackfillResult`-Dataclass entsprechend erweitert.

### Fixed

- **Monatsbericht: Scroll-Position bleibt beim Monatswechsel (#182 detLAN)** — Wer im Monatsbericht die Wärmepumpe-Sektion aufgeschlagen hat und auf einen anderen Monat klickt, bleibt jetzt an der Wärmepumpe — die rechte Inhaltsspalte springt nicht mehr ungewollt an den Seitenanfang. Mechanik: vor `setSelectedJahr/setSelectedMonat` merkt sich `MonatsabschlussView` die `scrollTop` des `<main>`-Containers in einem Ref, ein `useLayoutEffect` auf `monatData` stellt sie nach dem Daten-Reload wieder her (vor dem Browser-Paint, kein sichtbares Springen). Der Layout-Reset bei Menüpunkt-Wechsel (`Layout.tsx` reagiert auf `location.pathname`) bleibt davon unberührt — innerhalb von Monatsberichten ist der Wechsel ein State-Update, kein Routenwechsel.

### Internal

- **Designprinzip dokumentiert: Vollbackfill ist nur additiv** — Neuer Memory-Eintrag `feedback_vollbackfill_nur_additiv.md` ergänzt `feedback_reparatur_statt_loesch_features.md`: Aggregations-Bug-Fixes gehören in gezielte Migrations-Skripte im Release, nicht in einen User-Knopf für „alles neu rechnen". Reparatur einzelner Tage läuft über `/reaggregate-tag` mit Vorschau (chirurgisch, idempotent). Phase-2-Themen (Lösch-Knopf-Diagnose mit Datenverlust-Vorhersage, Sensor-Mapping-Änderung soll Backfill anbieten, JSON-Restore-Pfad muss `vollbackfill_durchgefuehrt`-Flag explizit zurücksetzen) sind in einem eigenen GitHub-Issue für späteres Anpacken festgehalten.
- **`resnap_anlage_range` bekommt Progress-Logging (alle 5 %)** — Die Funktion hat noch zwei legitime Caller (`/reaggregate-tag` und `/diagnostics/...`), und der Vollbackfill-Hänger aus #190 hat gezeigt, wie unangenehm sie ohne Log-Output ist. Bei großen Ranges erscheint jetzt regelmäßig „Resnap Anlage X: 240/1440 Stunden (16 %), Y Snapshots geschrieben".

---

## [3.25.21] - 2026-05-04

> 🩹 **detLAN-Folge zum UX-Bündel: Reihenfolge-Korrektur + Stammdaten-Sortierung + Monatsberichte-Stickybug** — Drei Issues aus dem direkten Folge-Tag zu v3.25.19/20: #187 (Reihenfolge falsch interpretiert + Label-Politur), #189 (Stammdaten → Investitionen folgte alter Reihenfolge), #182 (Sticky-Bug in der Monatsberichte-Spalte ließ sich mit `overscroll-contain` allein nicht beheben).

### Fixed

- **`INVESTITION_TYP_ORDER` korrigiert auf Cockpit-Banner-Reihenfolge (#187 detLAN)** — v3.25.19 hatte Wallbox+E-Auto **vor** Wärmepumpe gesetzt, weil die #186-Punkte 1/2/5 als „WB/EAuto vorne" gelesen wurden. Das Cockpit-Banner-Bild aus #186 zeigt aber `PV-Anlage → Speicher → Wärmepumpe → Wallbox → E-Auto`. Korrigiert: `wechselrichter, pv-module, balkonkraftwerk, speicher, waermepumpe, wallbox, e-auto, sonstiges`. Wirkt zentral aus `hooks/useSetupWizard.ts` auf alle Konsumenten (`SubTabs.tsx`, `HAStatistikImport.tsx`, `HAExportSettings.tsx`, `MappingSummaryStep.tsx`, neu auch `Investitionen.tsx`). Innerhalb des WB/EAuto-Paares bleibt E-Auto unter Wallbox (#186-Detail unverändert).
- **Stammdaten → Investitionen folgt jetzt der globalen Reihenfolge (#189 detLAN)** — `pages/Investitionen.tsx` hatte eine eigene lokale `investitionTypen`-Liste mit anderer Reihenfolge (`e-auto, waermepumpe, speicher, wallbox, ...`), die `INVESTITION_TYP_ORDER` ignorierte — klassischer SoT-Drift. Die lokale Liste ist entfernt; Reihenfolge + Labels kommen aus `INVESTITION_TYP_ORDER` + `INVESTITION_TYP_LABELS`. Innerhalb der Typ-Gruppe wird zusätzlich nach `anschaffungsdatum` absteigend sortiert (neueste Anschaffung oben, fehlende Datums ans Ende mit Bezeichnungs-Fallback).
- **Monatsberichte-Sticky-Spalte: Aside selbst zum scrollenden Sticky-Container (#182 detLAN)** — v3.25.13 hatte `overscroll-contain` auf einen inneren Wrapper-Div gelegt; das fing zwar Wheel-Bubble ab, löste aber nicht den eigentlichen Bug, dass die Aside beim Klick auf einen alten Monat (oder beim Mitscrollen der rechten Spalte) verschoben wurde. Ursache: der innere Container hatte `max-h-[calc(100vh-6rem)]` (viewport-relativ), aber der eigentliche Scroll-Container ist das Layout-`<main>` (`Layout.tsx:99`), das ist *kleiner* als 100vh — TopNav + SubTabs + Footer + Padding ziehen ~10rem ab. Damit war die Aside höher als ihr scroll-Vorfahre, sticky konnte nicht greifen, sie scrollte mit. Fix: Aside selbst trägt `sticky top-0 max-h-[calc(100dvh-12rem)] overflow-y-auto overscroll-contain`. Reserve 12rem deckt sicher TopNav + SubTabs + Footer + Padding. Plus `100dvh` statt `100vh` für iOS-Safari (Memory-Pattern).
- **„km gefahren" → „Gefahrene km" überall (#187 detLAN)** — Konsistente Schreibweise in `lib/fieldDefinitions.ts` (Statistik-Import), `pages/EAutoDashboard.tsx` (Σ-KPI-Kachel), `components/sensor-mapping/MappingSummaryStep.tsx` (Mapping-Zusammenfassung), `pages/CustomImportWizard.tsx` (Spalten-Dropdown), `backend/core/field_definitions.py`, `backend/api/routes/custom_import.py`. Ein Label, eine Schreibweise.

### Internal

- **Lesson learned (Drift-Pattern bestätigt)** — Drei UI-Stellen mit eigener Sortierung/Reihenfolge sind in den letzten Wochen aufgefallen (`SubTabs`, `HAStatistikImport`, `Investitionen`). Für künftige Reihenfolge-Themen: `INVESTITION_TYP_ORDER` ist die Single Source of Truth, jede neue UI-Stelle muss sie konsumieren. Der Memory-Eintrag `feedback_typ_labels_pattern.md` ist um diesen Vorfall ergänzt.

---

## [3.25.20] - 2026-05-04

> 🩹 **Daten-Checker-Fehlalarme: Strompreis-Sensor und Dienstwagen-E-Autos** — Joachim-PN-Folge nach v3.25.19. Zwei Warnungen im Daten-Checker, die für ihn (und vermutlich für andere mit gleichem Setup) Fehlalarme waren — beide sind jetzt entfernt.

### Fixed

- **Strompreis-Sensor wird nicht mehr als kWh-Counter geprüft** — `_check_sensor_mapping_lts` listete `basis.strompreis` zusammen mit Einspeisung, Netzbezug und PV-Gesamt auf und meldete bei fehlendem `state_class` eine WARNING „kWh-Sensor(en) nicht in HA-Long-Term-Statistics". Strompreis ist aber ct/kWh oder €/kWh — kein kumulativer kWh-Counter, sondern ein Live-Preis-Sensor. Wir lesen ihn live, nicht aus LTS aggregiert; ein fehlendes `state_class` ist hier irrelevant. (Joachim-PN: `sensor.grid_price_monitor_average_price_today` wurde fälschlich angemahnt.) `pv_gesamt` aus der Liste mit entfernt — wird heute nur als `pv_gesamt_w` (Live-W) gemappt, ebenfalls kein LTS-Bedarf.
- **Dienstwagen-E-Autos werden im Energieprofil-Abdeckungs-Check übersprungen** — Bei einem als Dienstwagen markierten E-Auto gibt es per Definition keinen PV-Bezug und keine Verbrauchsbilanz; ein kumulativer kWh-Counter wäre ohne Funktion. `_check_investitionen` (ROI-Check) hatte den Skip schon, `_check_energieprofil_abdeckung` aber nicht — der hat trotzdem „verbrauch_kwh oder ladung_kwh fehlt" gemeldet. Jetzt konsistent. (Joachim-PN: ID.4 als Dienstwagen meldete trotz korrekt fehlender Zuordnung eine Warnung.)

### Internal

- **Lesson learned: Dienstwagen-Flag muss in ALLEN E-Auto-spezifischen Checks greifen** — Bisher war der Skip nur an einer Stelle. Bei zukünftigen E-Auto-Checks daran denken: `inv.parameter.get("ist_dienstlich")` prüfen, Dienstwagen früh herausfiltern.

---

## [3.25.19] - 2026-05-04

> ✨ **UX-Konsistenz-Bündel** — Sammlung von kleinen Schliff-Items aus den Issues #185, #186, #187, #188 + ein Joachim-PN-Befund. Inhaltliche Klammer: Cockpit-Reihenfolge konsistent durchziehen, Statistik-Import lesbar machen, Kraftstoff-Hinweis kontextabhängig, KPI-Kachel-Schreibweise vereinheitlichen, Sensor-Mapping-Badge nur dort wo relevant.

### Changed

- **`INVESTITION_TYP_ORDER` global auf Wallbox → E-Auto → WP umgestellt (#187/2 detLAN)** — Bisher `wechselrichter, pv-module, speicher, balkonkraftwerk, waermepumpe, wallbox, e-auto, sonstiges`; jetzt `..., wallbox, e-auto, waermepumpe, sonstiges`. Wirkt zentral aus `hooks/useSetupWizard.ts` auf Setup-Wizard, MappingSummaryStep, HAExportSettings und Statistik-Import. `components/layout/SubTabs.tsx` (Cockpit-Subtab-Reihenfolge) parallel angepasst — Wallbox+E-Auto bilden ein Paar (fest installierte Anschluss-Komponente + mobiler Verbraucher), WP folgt danach.
- **Statistik-Import (`HAStatistikImport.tsx`) zeigt deutsche Labels (#187/1 detLAN)** — Basis-Felder werden mit `FELD_LABELS` aufgelöst und im Backend (`ha_statistics.py`) als Anzeige-Kopie der Werte mit Label-Keys ausgeliefert (`einspeisung → "Einspeisung"`, `netzbezug → "Netzbezug"`, `pv_gesamt → "PV Erzeugung Gesamt"`). `_basis_aktiv`-Helper im Import-Endpoint akzeptiert sowohl Raw-Keys als auch Labels für `basis_felder` (analog zur bestehenden Komponenten-Logik). Investitions-Typ-Badge im Frontend nutzt `TYP_LABELS` aus `lib/constants.ts` (`waermepumpe → "Wärmepumpe"`, `e-auto → "E-Auto"` etc.). `wp_starts_anzahl` kommt als „Kompressor-Starts" — neuer Eintrag in `build_feld_labels()` für Counter-Felder, die nicht in `INVESTITION_FELDER` registriert sind.
- **Statistik-Import: Komponenten-Reihenfolge nach `INVESTITION_TYP_ORDER`, Monatsliste chronologisch absteigend (#186/3 detLAN)** — Investitionen pro Monat werden jetzt nach `INVESTITION_TYP_ORDER` sortiert (Wallbox vor E-Auto vor WP, konsistent zum Rest). Monatsliste gespiegelt von aufsteigend zu absteigend (aktuellster Monat oben).
- **HAExportSettings `CATEGORY_ORDER` (#186/4 detLAN)** — Neue Reihenfolge der „Verfügbare Sensoren"-Kategorien: `anlage, energie, speicher, investition, wallbox, e_auto, waermepumpe, finanzen, quote, umwelt, autarkie, performance, sonstige, status`. Speicher früh (wichtigste Investition), Komponenten-Detailkategorien direkt hinter `investition`, Status zuletzt.
- **Sensor-Mapping-Wizard „Wallbox & E-Auto" (#186/1 detLAN)** — Sektions-Titel umbenannt von „E-Auto & Wallbox" → „Wallbox & E-Auto" in `SensorMappingWizard.tsx`. In `EAutoStep.tsx` werden Wallbox-Komponenten zuerst gerendert, E-Auto-Komponenten danach (mt-8-Abstand entsprechend verschoben).
- **Monatsbericht-KPI-Kachel „Kompressor-Starts" (#185 detLAN)** — In `MonatsabschlussView.tsx` werden Σ Monat und Max/Tag getauscht: prominent angezeigt wird jetzt die Monats-Summe (`wp_starts_summe_monat`), der Verschleiß-Indikator (Tages-Maximum) wandert in den Subtitel. Konsistent zu allen anderen Σ-KPI-Kacheln im Monatsbericht. Title verkürzt von „Kompressor-Starts (Max/Tag)" auf „Kompressor-Starts".
- **Kraftstoff-Box nur bei E-Auto-Anlagen (#188 rapahl)** — Der Hinweis-Block „Kraftstoffpreise nachpflegen" wird in `pages/Monatsdaten.tsx` (Monats-Ebene) und `pages/Energieprofil.tsx` (Tages-Ebene) jetzt zusätzlich gegen `investitionen.some(i => i.typ === 'e-auto')` geprüft. Ohne E-Auto-Investition ist der Backfill für die Anlage ohne Wert.

### Fixed

- **„keine HA-Statistik"-Badge nur bei kumulativen kWh-Countern (Joachim-PN, Wattpilot)** — `SensorAutocomplete` hat einen neuen Prop `requireStatistics` (Default `true` für `FeldMappingInput` = kWh-Counter, die zwingend Long-Term-Statistics brauchen). Live-Sensor-Aufrufer setzen ihn auf `false`: `LiveSensorSection` (alle Live-Felder pro Investitions-Typ — `leistung_w`, `soc`, Temperatur, etc.), `BasisSensorenStep` (`pv_gesamt_w`, `aussentemperatur_c`, `sfml_*`, `netz_kombi_w`, `einspeisung_w`, `netzbezug_w`), `PVModuleStep` (Live-Leistung pro String). Vorher wirkte der Badge bei W/%/°C-Sensoren wie ein echter Mapping-Fehler, obwohl alles korrekt war — diese Sensoren werden direkt aus dem HA-State gelesen, `state_class` ist dafür irrelevant.

### Internal

- **`INVESTITION_TYP_ORDER`-Comment ausführlicher** — Begründungs-Kette dokumentiert (Erzeuger/Speicher → Wallbox+E-Auto-Paar → WP → Catch-All) statt nur ein Detail-Hinweis auf detLAN #180. Hilft bei künftigen Reihenfolge-Diskussionen, alle Decisions auf einen Blick.

---

## [3.25.18] - 2026-05-03

> 🩹 **Reload-Knopf heilt jetzt auch den Stunde-0-Spike — mit Vorschau-Tabelle vor Übernahme.** Rainer-Befund nach v3.25.17: das Reaggregate-Tool zeigte für 1.5. weiter PV 1.047 / Einspeisung 8.543 / Bezug 2.757 kWh in Stunde 0:00, obwohl 264 Snapshot-Upserts protokolliert wurden. Audit aller Schreib-/Lesepfade hat zwei Bugs aufgedeckt — beide gefixt. Plus: damit das nie wieder „Klick und hoffen" ist, gibt es jetzt eine Übernahmetabelle, die alt vs. neu zeigt, bevor irgendetwas geschrieben wird. Außerdem im Bündel: drei kleine UX-Items aus dem detLAN-Pakt.

### Fixed

- **Reaggregate-Tag deckt jetzt den Vortag-23:00-Boundary ab (Bug A)** — Slot 0 = `snap(Tag 00:00) − snap(Vortag 23:00)`, der Reload-Pfad schrieb aber nur Snapshots für Tag 00:00..23:00 (24 Stück). Ein korrupter Vortags-Snapshot — z. B. aus prä-#184-Phase oder einem aussetzenden :05-Job — blieb dadurch in der DB stehen, und Slot 0 zeigte beliebig oft denselben Spike. Der Range erweitert sich jetzt um eine Stunde nach hinten (`reaggregate_tag` in `energie_profil.py:1052`). 25 Snapshots werden überschrieben, der Vortags-Boundary wird mit dem aktuellen HA-`sum`-Wert frisch geschrieben.
- **`live_snapshot_if_missing` schreibt keine HA-`state`-Werte mehr (Bug B, Wurzel von #184)** — Der `:55`-Preview-Job las bisher via `ha_state_svc.get_sensor_state()` den Sensor-`state` und schrieb ihn als Snapshot für die anstehende volle Stunde. Bei Tagesreset-Zählern (utility_meter daily) ist `state` aber etwas anderes als das Statistics-`sum`: `state`=Tagesenergie, `sum`=Lifetime-bereinigt. Wurde der reguläre :05-Hourly-Job danach übersprungen (HA-/Add-on-Restart, Job-Crash), blieb der `state`-Wert persistent in der Snapshot-Tabelle und produzierte beim nächsten Aggregat einen Lifetime-grossen Stunden-Spike — genau das Symptom aus Issue #184. Der HA-Counter-Pfad ist entfernt; die laufende Stunde im Energieprofil wartet im Add-on-Modus jetzt bis :05 der Folgestunde (wie vor #146). Der MQTT-Pfad bleibt aktiv — MQTT-Topics liefern direkt kumulative Lifetime-Werte ohne `state`/`sum`-Split.

### Added

- **Vorschau-Tabelle vor Reload („Übernahmetabelle")** — Statt nach Confirm-Dialog blind zu schreiben, öffnet der Reload-Knopf jetzt ein Modal mit einer Stundentabelle. Pro Kategorie (PV/Einspeisung/Bezug/…) eine Alt-Spalte (DB-Snapshot) und eine Neu-Spalte (Wert aus HA jetzt). Slot 0 ist farblich markiert mit „↤ Vortag"-Hinweis, weil er von der Vortags-23:00-Boundary abhängt. Differenzen über 0.1 kWh sind orange, über 1 kWh fett. Tagesumme alt/neu pro Kategorie obendrauf. Erst nach „Übernehmen" werden die Snapshots geschrieben und der Tag neu aggregiert. „Abbrechen" schreibt nichts. Wenn HA-Statistics nicht erreichbar ist (Neu-Spalte leer), ist der Übernahme-Button gesperrt — verhindert das Heilen mit Null-Werten. Neuer Endpoint `GET /api/energie-profil/{anlage}/reaggregate-tag/preview` liefert die Tabelle ohne irgendetwas zu schreiben.

### Changed

- **Tagesdetail-Datums-Picker erreicht den heutigen Tag (D#181 detLAN)** — Vor/Zurück-Pfeile und der date-Input waren bisher auf gestern gedeckelt mit der Begründung „heute hat noch keinen abgeschlossenen Energieprofil-Tag". Stimmt nicht: `aggregate_today_all` schreibt rollierend alle 15 Minuten alle abgeschlossenen Stunden des heutigen Tages. Maximum jetzt `heuteISO()` in `EnergieprofilTab.tsx` — der Pfeil zur rechten Seite springt zu heute, sobald gestern der aktuelle Stand ist.
- **Lade-Indikator mit 250ms-Threshold (D#181 Nachtrag detLAN)** — Der `Lade…`-Span im Tagesdetail-Datum-Picker erschien bei jedem Tag-Wechsel kurz und wurde dann sofort wieder ausgeblendet — auf schnellen Rechnern ein nutzloser Flash, den detLAN als „kann man nicht erkennen, lieber gleich weglassen" beschrieben hat. Statt ihn ersatzlos zu entfernen kommt jetzt ein 250ms-Threshold: ist der Fetch nach 250ms noch nicht fertig, erscheint der Indikator. Schneller Rechner → kein Flash. Langsamer Rechner / Netz → weiterhin sichtbares Feedback.
- **Wallbox vor E-Auto in `INVESTITION_TYP_ORDER` (#180 detLAN)** — Die Reihenfolge `'e-auto'` vor `'wallbox'` widersprach dem Cockpit-Subtabs-Pattern (PV → BKW → Speicher → WP → Wallbox → E-Auto → Sonstiges). Inhaltliche Begründung: Wallbox ist eine fest installierte Anlagen-Komponente mit Anschaffungs-/Stilllegungsdatum und JAZ-ähnlicher Effizienz-Auswertung, das E-Auto eher mobiler Verbraucher. Daher Wallbox vor E-Auto. Konstantenfeld in `useSetupWizard.ts` umsortiert — wirkt auf Setup-Wizard, MappingSummaryStep, HAExportSettings und alle anderen Konsumenten der Konstante in einem Schritt.

### Internal

- **Audit aller Snapshot-Pfade vor dem Fix** — `:05`-Hourly-Job, `:55`-Preview-Job, Recovery-Job (Startup), `vollbackfill` (über `leistung_w` — orthogonal), `_fill_gaps_linear` (extrapoliert nicht am Rand, ist OK), `_upsert_snapshot` (UniqueConstraint vorhanden, exakter `zeitpunkt`-Match), `_categorize_counter` + Negative-Delta-Schutz, Daten-Checker Spike-Erkennung, alle Resnap-Endpoints, Zeitzonen/DST. Ergebnis: nur die zwei oben gefixten Stellen waren buggy.
- **Drei Reproduktionstests vor Release** (in-memory SQLite, gemockte HA-Statistics): pre-Fix Spike persistent / post-Fix sauber, HA-state-Pfad inaktiv / MQTT-Pfad aktiv, Preview liefert alt/neu ohne zu schreiben. Alle drei grün.

---

## [3.25.17] - 2026-05-03

> 🩹 **Reaggregate-Tag heilt prä-#184-Spikes endlich richtig** — Rainer-Befund nach v3.25.16: das Reparatur-Tool unter „Daten → Energieprofil" konzentrierte die Werte am Tagesanfang, statt sie zu reparieren (PV 1047 kW in Stunde 0:00, alle anderen Stunden ~0). Ursache: `resnap_anlage_range` überschrieb nur Slots, für die HA-Statistics einen Wert lieferte — bei `sum=NULL`-Slots aus prä-#184-Phase blieb der korrupte alte Snapshot in der DB stehen, und `aggregate_day` rechnete jedes Mal denselben Spike zurück.

### Fixed

- **resnap löscht Snapshots, wenn HA jetzt `None` liefert (Rainer-PN 2026-05-03)** — Neuer Helper `_delete_snapshot_if_exists` und ein `force_resnap`-Parameter in `snapshot_anlage` / `snapshot_anlage_5min`. Im Recovery-Pfad (`resnap_anlage_range`) ist der Modus jetzt aktiv: liefert `get_value_at` für einen Slot `None` (typisch für sum=NULL aus prä-#184-Schreibphase), wird der vorhandene Snapshot gelöscht statt belassen. `aggregate_day` sieht damit eine echte Lücke und überspringt die Slot-Berechnung sauber, anstatt einen falschen Lifetime-Sprung als Stunden-Δ zu interpretieren. Der reguläre stündliche Snapshot-Job (Cron `:05`) behält das alte Skip-Verhalten — ein temporärer HA-Latenz-Hänger nimmt also keinen frisch geschriebenen Slot weg, nur der explizite Recovery-Aufruf räumt aktiv auf.
- **Repro-Test (Demo-Daten, in-memory SQLite, gemockte HA-Statistics)** — Synthetisches Szenario: korrupter `snap(00:00) = 0`, sauberes `snap(01:00) = 100`, HA liefert für 00:00 weiterhin None (sum=NULL). Vor Fix: nach reaggregate bleibt snap(00:00)=0 und Δ Stunde 0 = 100 kWh als Spike (= Rainer's Symptom). Nach Fix: snap(00:00) wird gelöscht, Δ Stunde 0 = Lücke. Test grün vor Release verifiziert.

### Internal

- **Lesson learned: skip-on-None ≠ idempotenter Recovery** — Der :05-hourly-Job will defensiv bleiben (skip statt überschreiben). Der Recovery-Pfad muss aggressiv aufräumen (None → delete). Beides hatte vorher dieselbe Implementierung — `force_resnap` macht den Unterschied jetzt explizit.

---

## [3.25.16] - 2026-05-03

> 🧹 **Aufräumen statt nachschärfen: WP-Kompressor-Starts ohne Selbstkalibrierung** — detLAN-Folge-Beobachtung nach v3.25.14: Cockpit zeigte 146 statt 134 Starts (+12 Drift), Monatsbericht Mai 112. Statt die Eichungs-Logik (`baseline = sensor.gesamt − Σ TZ < heute` + heute_live-Hochrechnung) noch eine Iteration nachzuschärfen, fliegt sie ganz raus. Σ Lebensdauer im Cockpit kommt direkt aus dem Hersteller-Sensor — Punkt. Drift gegenüber den EEDC-erfassten Tagesinkrementen wird nicht mehr maskiert, sondern bleibt zwischen den Anzeigen sichtbar.

### Changed

- **WP Σ Lebensdauer = Hersteller-Counter direkt (#173 detLAN)** — Cockpit-Aggregation `get_waermepumpe_dashboard` liest den Lebensdauer-Stand jetzt direkt aus dem Hersteller-Sensor (HA-State → HA-Statistics → jüngster Snapshot als Fallback). Keine Wizard-Save-Eichung mehr, keine Live-Hochrechnung, keine Race-Möglichkeit zwischen Save-Zeitpunkt und Aggregations-Job um 00:15. Neuer schlanker Helper `get_counter_lifetime` in `sensor_snapshot_service.py` ersetzt `compute_counter_baseline` + `get_counter_today_live`. `_refresh_counter_baselines` aus `sensor_mapping.py` ebenfalls entfernt — der Wizard-Save schreibt keine Counter-Baselines mehr.
- **Monatsbericht „Aktueller Monat" zeigt ehrlich was EEDC erfasst hat** — `wp_starts_summe_monat` ist jetzt schlicht `Σ TZ Mai`, kein Live-Add-on für den heutigen Tag mehr. Wenn diese Summe vom Hersteller-Counter abweicht, ist das in der Anzeige sichtbar (Cockpit zeigt Hersteller-Wahrheit, Monatsbericht zeigt EEDC-Erfassung) — Diagnose ohne Magic.
- **Tooltip im Cockpit auf eine Zeile geschrumpft** — „Aus Hersteller-Sensor (Lebensdauer-Counter)" + Höchste Tagessumme. Drei-Anteile-Aufschlüsselung (Baseline + abgeschlossene Tage + heute live) entfällt, da die zugrundeliegende Berechnung weg ist.

### Migration

- Alte `wp_starts_anzahl_baseline*`-Felder in `Investition.parameter` bleiben in der DB stehen (Deprecated-Regel), werden vom neuen Code nicht mehr gelesen. Keine Migration nötig.
- detLAN-Heilung nach Update: Cockpit zeigt sofort Hersteller-Wahrheit (134 statt 146). Falls Mai-Bericht weiter zu hoch erscheint und das nicht der tatsächlichen Schalthäufigkeit entspricht, einzelne Tage in Auswertungen → Energieprofil → Tagesdetail über das Reload-Symbol neu aggregieren.

### Internal

- **Lesson learned: keine Selbstkalibrierung gegen instabile Aggregate** — Die `compute_counter_baseline`-Konstruktion (Eichung an einem Punkt, Aktualisierung der Σ über Zeit) hatte zwischen v3.25.13 und v3.25.15 drei verschiedene Drift-Symptome produziert (Wizard-Save-Persistierung, Tagesverlaufs-Doppelzählung, Aggregations-Drift um 00:15). Der vierte Iterations-Versuch wäre vermutlich auch wieder eine Krücke gewesen. Der direkte Hersteller-Read braucht keine Selbstkorrektur, weil er keine Berechnung kennt — der Sensor selbst ist die Wahrheit. Netto −237 Zeilen Code.

---

## [3.25.15] - 2026-05-03

> ✨ **UX: Vor/Zurück-Pfeile im Tagesdetail-Datum-Picker** — Kleinstrelease mit einem detLAN-Item (#181). Die Symmetrie zwischen Monats- und Tagesdetail-Ansicht ist jetzt hergestellt.

### Added

- **Vor/Zurück-Pfeile im Tagesdetail-Datum-Picker (#181 detLAN)** — Auswertungen → Energieprofil → Tagesdetail bekommt links und rechts vom Datums-Eingabefeld jeweils einen Chevron-Button (`<` / `>`), analog zur bereits bestehenden Monats-Ansicht (`EnergieprofilMonat.tsx`). Folgetag-Button ist disabled, sobald gestern erreicht ist (heute hat noch keinen abgeschlossenen Energieprofil-Tag). Helper `tagVerschieben(iso, n)` lokal im Tab. Pattern 1:1 von der Monats-Ansicht übernommen — gleiche Tailwind-Klassen, gleiche Aria-Labels, gleiches Disabled-Verhalten.

---

## [3.25.14] - 2026-05-03

> 🩹 **Forum-Bündel: Counter-Doppelzählung + UI-Polish + WP-Wording** — Eine Wert-Korrektur (WP-Kompressor-Starts Σ Lebensdauer wuchs im Tagesverlauf zu hoch, detLAN-Folgebefund aus #173), zwei UI-Bug-Bündel (Großschreibung / Sortierung / Truncation in Sensor-Zuordnung & MQTT-Export, detLAN #180 + #179) und eine seit April fällige Wording-Schärfung (Heizenergie → Heizwärme + Tooltips, rcmcronny #120).

### Fixed

- **Counter-Doppelzählung im Tagesverlauf, Σ vor heute + Live-Hochrechnung (#173 Folge detLAN 2026-05-03)** — Nach dem v3.25.13-Fix für die Wizard-Save-Persistierung der Baseline meldete detLAN Folgendes: nach 7 realen Kompressor-Starts heute zeigte das Cockpit Σ Lebensdauer 136 statt 131 — also 5 Starts zu viel. Ursache: `TagesZusammenfassung[heute].komponenten_starts` wird im Lauf des Tages mehrfach neu berechnet (Snapshot-Job hourly, `get_snapshot` mit Toleranz-Fenster nimmt jüngsten verfügbaren Snapshot statt morgen 00:00). Sowohl `compute_counter_baseline` als auch die Cockpit-Aggregation lasen TZ inkl. heute → `baseline + Σ_inkl_heute > sensor_gesamt`. Fix: heutiger Tag wird konsistent aus TZ-Aggregation ausgeschlossen (`datum < today`), heutiger Verlauf kommt aus dem Live-Sensor (neuer Helper `get_counter_today_live`: `sensor_live − snapshot(heute 00:00)`). Σ Lebensdauer bleibt damit synchron mit dem Hersteller-Counter ohne Doppelzählung. Tooltip im Cockpit zerlegt die drei Anteile getrennt: Hersteller-Baseline + EEDC abgeschlossene Tage + heute live. Gleicher Fix auch im Monatsbericht (Aktueller Monat) — analoger Drift-Mechanismus, gleiche Bug-Klasse zentral konsistent gefixt (Drift-Lesson). Bei MQTT-only-Standalone-Setups ohne Live-State fehlt heute in der Σ bis zum Tagesabschluss — bewusst statt Doppelzählung.

- **Großschreibung, Sortierung & Sensor-ID-Truncation in Sensor-Zuordnung-Zusammenfassung (#180 detLAN)** — Der „Zusammenfassung"-Tab des Sensor-Mapping-Wizards zeigte die Investitions-Typen in Klammern als rohe Enum-Werte (`(e-auto)`, `(pv-module)`, `(speicher)`, `(waermepumpe)`, `(wallbox)`) statt als deutsche Labels. Feldnamen wurden aus den Backend-Schlüsseln per `replace(/_/g, ' ')` generiert, ohne Akronym-Behandlung — `pv erzeugung (kWh)` statt `PV-Erzeugung (kWh)`, `wp starts anzahl` statt `Kompressor-Starts`, `km gefahren` statt `Kilometer gefahren`. Außerdem schnitt die Sensor-ID rechts auch auf breiten Viewports bei 200 px ab (`...sensor.bat...`). Fix: Typ-Klammer auf `TYP_LABELS`-Lookup aus `lib/constants.ts`, Feld-Labels via `FIELD_LABEL_OVERRIDES`-Mapping mit Title-Case-Fallback, Investitions-Karten nach `INVESTITION_TYP_ORDER` sortiert (PV → Wechselrichter → Speicher → BKW → WP → E-Auto → Wallbox → Sonstiges), Sensor-ID-Truncation nur noch auf schmalen Viewports (`max-w-[200px] sm:max-w-[300px] md:max-w-[400px] lg:max-w-none`).

- **MQTT-Export: Categories haben deutsche Labels + sprechende Icons + Sortierung + Card-Ecken-Fix (#179 detLAN)** — Der „Verfügbare Sensoren"-Block im MQTT-Export-Tab zeigte mehrere Categories (`anlage`, `quote`, `investition`, `speicher`, `status`, `waermepumpe`, `e_auto`, `wallbox`) als rohen Enum-Wert mit Pin-Default-Icon, weil deren Mapping in `categoryLabels`/`categoryIcons` fehlte. Der Investitions-Sensoren-Block hatte das gleiche Problem in der Klammer (`(wechselrichter`, `(pv-module`, `(speicher`, `(wallbox`, `(waermepumpe`, `(e-auto`). Zusätzlich war die Border-Radius-Ecke des `<details>`-Wrappers defekt — der Hover-Hintergrund von `<summary>` schnitt über den Border. Fix: alle Backend-Categories aus `SensorCategory`-Enum mit deutschen Labels + Icons gemappt, fixe Anzeige-Reihenfolge (Anlage zuerst, dann Auswertungs-Pyramide Energie/Quote/Finanzen/Umwelt, dann Investitions-Aspekte, Status zuletzt), Investitions-Sensoren analog `INVESTITION_TYP_ORDER`-sortiert, `<details>` bekommt `overflow-hidden`.

- **WP-Wording „Heizenergie" → „Heizwärme" + Tooltips (#120 rcmcronny)** — Seit April 2026 versprochen, jetzt nachgereicht. „Heizenergie" wurde in der Eingabemaske mit dem WP-Stromverbrauch verwechselt — COP=1 verrät das, ist aber für Erstnutzer nicht selbsterklärend. Konsistent über alle UI-Stellen umgestellt: Frontend `fieldDefinitions.ts` (Eingabemaske) und Backend `field_definitions.py` (HA-Statistik-Wizard / custom_import / Monatsabschluss / FELD_LABELS-Registry), HA-Import-Wizard, Sensor-Mapping-Wizard `WaermepumpeStep.tsx`, Komponenten-Tab (Formel-Tooltips), WaermepumpeDashboard (JAZ-Heizen-Formel), MappingSummaryStep (FIELD_LABEL_OVERRIDES), Daten-Checker-Meldung. Backend-Schlüssel `heizenergie_kwh` und CSV-Suffix `_Heizung_kWh` bleiben unverändert (Backwards-Kompat für bestehende Templates). Neue Hover-Tooltips direkt im Eingabefeld differenzieren elektrisch vs. thermisch:
  - Stromverbrauch / Strom Heizen / Strom Warmwasser: „Stromaufnahme … (elektrisch)"
  - Heizwärme: „Abgegebene Heizwärme (thermisch) — COP = Heizwärme / Strom"
  - Warmwasser: „Abgegebene Warmwasser-Wärme (thermisch)"

### Internal

- **Lesson learned: Aggregations-Drift bestätigte sich erneut** — Der #173-Folgebug betraf zwei Read-Sites (Cockpit `investitionen.py:get_waermepumpe_dashboard` + Monatsbericht `aktueller_monat.py`). Konsequent zentral statt einzeln gepatcht, neuer Helper `get_counter_today_live` für die Live-Hochrechnungs-Logik. Memory-Eintrag `feedback_aggregations_drift.md` um diesen Vorfall erweitert.
- **Lesson learned: Roh-Enum-Werte in der UI sind Drift-Indikator** — Sowohl #180 (Sensor-Zuordnung-Zusammenfassung) als auch #179 (MQTT-Export-Investitions-Sensoren) zeigten Investitions-Typen als rohe `inv.typ`-Strings statt als deutsche Labels. Wenn ein User-sichtbarer Roh-Enum-Wert auftaucht, gibt es wahrscheinlich noch andere unbemerkte Stellen — `TYP_LABELS` aus `lib/constants.ts` ist die Single Source of Truth, sollte überall verwendet werden statt String-Konkatenation.

---

## [3.25.13] - 2026-05-02

> 🩹 **Forum-Bündel: Werte-Bug + Layout-Korrekturen** — Ein Werte-Bug in den Investitions-Parametern (Wizard-only-Keys gehen beim Save verloren), drei Layout-Bugs aus detLAN-Reports (Mobile-Sortable-Sections nicht erreichbar, Energiefluss-Eckenfix bei Sunset/Alps, Layout-Lücken bei mittlerer Fensterbreite, iOS-Body-Scroll-Drift) sowie zwei vorgezogene Werte-Fixes aus dem Rainer-Bündel (Counter-Spike sum/state-Vermischung, WP `getrennte_strommessung` JAZ-Konsistenz).

### Fixed

- **Wizard-only-Parameter beim Investitionen-Speichern erhalten (#173 detLAN)** — Beim Speichern eines Investitionen-Form (z. B. „Wärmepumpe → Speichern") schickte das Frontend ein neu zusammengebautes `parameter`-JSON ans Backend, das **nur die im Form sichtbaren Felder** enthielt. Das Backend ersetzte das ganze `parameter`-Objekt im Replace-Modus — Wizard-only-Felder wie `wp_starts_anzahl_baseline` (von `_refresh_counter_baselines` in `sensor_mapping.py` geschrieben) wurden bei jedem Form-Save gelöscht. Folge: detLAN's WP-Kompressor-Starts-Baseline wurde beim Schließen des Investitionen-Dialogs (auch ohne Datenänderung) auf `None` gesetzt, das Cockpit zeigte nur noch die Σ der EEDC-Tagesdifferenzen statt `Baseline + Σ Tagesdifferenzen`. Frontend mergt jetzt `parameter` mit dem bestehenden `investition.parameter` statt es zu ersetzen — Wizard-Keys bleiben erhalten. Nach dem Update einmalig Sensor-Zuordnung → Speichern & Abschließen zur Neusetzung der Baseline.
- **Counter-Spike durch sum/state-Vermischung in `get_value_at` (#184 Rainer-PN 2026-05-01)** — Reproduziert auf synthetischer HA-DB: `sum=NULL/state=5` und `sum=2390/state=11` in aufeinanderfolgenden Slots erzeugten Δ=2385 statt der echten Δ=6. Ursache: `get_value_at` priorisierte `sum` ohne den vorangegangenen `state`-Pfad zu berücksichtigen; sobald HA für einen Slot keinen `sum` lieferte (kurzfristig nach Restart oder Sensor-Lücke), griff der Code auf `state` zurück, im nächsten Slot wieder auf `sum` — die Differenz mischte beide Quellen. Jetzt: konsistent eine Quelle pro Range, mit korrekter Behandlung von measurement-only-Sensoren (`has_sum=False`).
- **WP `getrennte_strommessung` JAZ-Konsistenz + obsoleter Sensor (#183 Rainer-PN 2026-05-01)** — Drei Schichten: (1) **Aggregation:** neuer SoT-Helper `get_wp_strom_kwh(data, params)` in `field_definitions.py`, an 8 Read-Sites genutzt (Cockpit Komponenten/Übersicht/Social/Nachhaltigkeit, Monatsbericht, Monatsdaten, Aussichten ROI+Finanzen, HA-Export, Community-Service, PDF-Jahresbericht). Bei `getrennte_strommessung=True` wird Gesamt-Strom aus `strom_heizen_kwh + strom_warmwasser_kwh` berechnet, der alte Sammel-Sensor wird ignoriert. (2) **UI:** `MappingSummaryStep.tsx` rendert den alten Stromverbrauch-Sensor bei aktivierter getrennter Messung mit `(obsolet)`-Badge + reduzierter Opazität + Tooltip. (3) **Daten-Checker:** zusätzlicher INFO-Hinweis im `_check_wp_monatsdaten`-Pfad.

- **Sortable Sections in Monatsbericht-Mobile-Ansicht erreichbar (#175 detLAN)** — Mit aufgeklappter Energie-Bilanz-Sektion konnten die Sektionen darunter (Community-Vergleich, Speicher, Wärmepumpe, E-Mobilität, Balkonkraftwerk, Sonstiges) im Mobile-Viewport nicht erreicht werden — der Scroll-Bereich endete bei Finanzen. Ursache: `flex-1` und `min-h-0` auf dem inneren `<main>` und Outer-Flex-Container waren ohne `lg:`-Prefix gesetzt. Im Mobile-`flex-col`-Mode mit unbestimmter Container-Höhe ergibt das einen Henne-Ei-Konflikt — der Browser kollabiert die Höhe falsch, Sections darunter liegen außerhalb des Layout-Scroll-Bereichs. `flex-1` und `min-h-0` jetzt mit `lg:`-Prefix — auf Desktop unverändert, Mobile-Layout fließt natürlich.
- **Mobile-Sticky-Scroll-Containment in Monatsberichten (#182 detLAN)** — Beim Scrollen in der linken Sticky-Monatsspalte (Desktop) oder am Mobile-Selektor bubbelten Wheel-Events nach Reach-End auf den Hauptseiten-Scroll → die rechte Inhaltsspalte wurde mitgescrollt und der WP-Fokus ging verloren. `overscroll-contain` Tailwind-Klasse auf den Sticky-Scroll-Container fängt die Events lokal ab.
- **Sunset/Alps-Eckenfix für Effekt-Layer (#164a detLAN)** — In v3.23.7 wurde der Hintergrund-`<rect>` der Sunset/Alps-Tile auf `clipPath="url(#ef-photo-clip)"` (mit `rx="8"`) umgestellt. Die Effekt-Layer (Krepuskulare Strahlen, Atmosphären-Bögen, Mondlicht-Strahlen, Sterne, Aurora) blieben aber außen vor — sie nutzen `ef-sky-clip` / `ef-sea-clip` / `ef-alps-sky-clip`, die einfache Rechtecke ohne Border-Radius sind. Die Effekte ragten somit in die abgerundeten Tile-Ecken. Lösung: zusätzlicher `<g clipPath="url(#ef-photo-clip)">`-Wrapper um die Sunset- und Alps-Effekt-Blöcke zieht den Border-Radius über alle inneren Layer.
- **Energiefluss-Layout-Lücken bei mittlerer Fensterbreite (#164b detLAN)** — Im Bereich 1024–1280 px war die Heute-Box höher als das natürliche Aspect-Ratio des Energiefluss-SVGs zuließ. Das Grid (`lg:grid-cols-3`) zog den linken Container auf gleiche Zeilenhöhe → SVG mit `preserveAspectRatio="xMidYMid meet"` zentrierte sich vertikal mit Lücken oben/unten. Side-by-Side-Layout jetzt erst ab `xl:` (≥1280 px) — im md/lg-Bereich stapelt Heute-Box unter dem Energiefluss, was detLAN's eigenem Fix-Vorschlag entspricht.
- **iOS-Body-Scroll-Drift auf kleinen Viewports (#161 detLAN)** — Auf iOS Safari/WKWebView (HA Companion) und in Browser-DevTools mit iPhone-SE-Simulation konnte der Document-Root (Body/HTML) unabhängig vom Layout-Wrapper (`h-dvh overflow-hidden`) scrollen — die App ließ sich so weit nach oben schieben, dass nur noch die HA-Titelleiste sichtbar blieb (auf iPhone SE: schwarze leere Fläche unter dem Footer). Ursache: HTML/Body hatten kein eigenes `overflow`/`height`-Constraint. `index.css` setzt jetzt `html, body { @apply h-full overflow-hidden overscroll-none }` — Layout-Wrapper bleibt der einzige Scroll-Owner. Auf Desktop und größeren iPhones (11/16 Pro) keine sichtbare Veränderung; iPhone SE und HA-Companion-App profitieren.

### Internal

- **Lesson learned: `min-h-0` + `flex-1` immer mit Breakpoint-Prefix in Multi-Layout-Containern** — Der #175-Bug zeigt einen wiederkehrenden Henne-Ei-Konflikt: flex-Klassen ohne `lg:`-Prefix wirken auch in `flex-col`-Mode (Mobile), dort ohne Container-Höhe undefiniert. Wenn ein flex-Container je nach Breakpoint zwischen flex-col und flex-row schaltet, müssen flex-Höhen-Klassen (`flex-1`, `min-h-0`) konsistent mit dem Breakpoint des Direction-Switches stehen. Beobachtung in MEMORY festgehalten.

---

## [3.25.12] - 2026-05-02

> 📝 **Doku-Nachreichung zu v3.25.11** — `WAS-IST-NEU.md` um die drei User-sichtbaren Highlights aus v3.25.11 (Sonstige Erträge im T-Konto, Pool-Doppelzählung Wallbox/E-Auto, Daten-Checker `verbrauch_kwh`/`ladung_kwh`) ergänzt sowie um den Self-Heal-Workflow gegen Counter-Spikes. Kein Funktions-Code geändert, nur die In-App-Hilfe.

### Changed

- **`WAS-IST-NEU.md` aktualisiert** — vier neue Einträge oben in der Liste, Stand-Header von v3.25.10 auf v3.25.12 gezogen. Wer in der In-App-Hilfe „Was ist neu" aufruft, sieht die v3.25.11-Wert-Korrekturen jetzt direkt am Anfang. Die ausführliche technische Beschreibung steht weiterhin im [v3.25.11-CHANGELOG-Block](#32511---2026-05-02).

---

## [3.25.11] - 2026-05-02

> 🩹 **Sammelpatch: Counter-Spike Self-Heal + Monatsbericht-Korrekturen** — Drei neue Selbstheilungs-Wege für Snapshot-Verzerrungen (Folge des in v3.25.10 behobenen Off-by-one-Bugs) und drei Bug-Fixes aus einer Joachim-Tester-PN (sichtbare Sonstige Erträge, Pool-Doppelzählung E-Auto/Wallbox, Daten-Checker-Drift `verbrauch_kwh` ↔ `ladung_kwh`).

### Fixed

- **Sonstige Erträge im T-Konto + Monatsergebnis (Joachim-PN)** — Erfasste Erträge mit `typ='ertrag'` (z. B. AG-Erstattung beim Dienstwagen) waren auf der HABEN-Seite des Monatsbericht-T-Kontos nicht sichtbar und wurden im Monatsergebnis ignoriert; für E-Autos mit Dienstwagen-Flag wurde der ganze Wirtschaftlichkeits-Branch übersprungen. Backend wertet `sonstige_positionen` jetzt typ-unabhängig pro Investition aus, neue Aggregat-Felder `sonstige_ertraege_euro/sonstige_ausgaben_euro/sonstige_netto_euro` auf der Response. Frontend rendert pro Investition eigene HABEN- und SOLL-Zeilen und korrigiert das Monatsergebnis auf `gesamtnettoertrag − betriebskosten + sonstige_netto`. User mit Dienstwagen-AG-Erstattung sehen das Monatsergebnis um den Erstattungsbetrag weniger negativ.
- **Pool-Doppelzählung E-Auto/Wallbox in der Monatsbericht-Aggregation (Joachim/Gernot-PN)** — `_collect_saved_data` und `_load_vorjahr` summierten `ladung_kwh` und `ladung_pv_kwh` über E-Auto- und Wallbox-Investitionen kommentarlos auf, obwohl beide Typen denselben Stromfluss aus zwei Perspektiven messen (Wallbox = Loadpoint, E-Auto = Vehicle). Folge bei zwei Testern: `kWh/100km` etwa doppelt so hoch wie real (Smart EQ Februar 61,6 statt ~20), PV-Anteil > 100 % möglich (April 189 %). Quick-Fix: getrennte Akkumulatoren pro Investitionstyp, pro Feld die größere Quelle als Wahrheit, `PV ≤ Gesamt` als harte Sicherung. Saubere Per-Fahrzeug-Trennung folgt mit Phase 2 des Wallbox/E-Auto-Konzepts. Folge-Pfade `cockpit/uebersicht.py` und der HA-Stats-/MQTT-Aggregator bleiben bewusst auf der alten Pool-Logik — werden mit Phase 2 mitgezogen.
- **Daten-Checker akzeptiert `verbrauch_kwh` UND `ladung_kwh` für E-Autos (Joachim-PN)** — Schema-Drift: das E-Auto-Field-Schema definiert das Gesamt-Ladung-Feld als `verbrauch_kwh` (was der Sensor-Mapping-Wizard entsprechend anbietet), der Daten-Checker verlangte aber `ladung_kwh`. User mit korrekt gemapptem Sensor sahen trotzdem die Warnung „Komponenten ohne kWh-Zähler-Abdeckung". `erwartete_felder`-Struktur auf Liste-von-Alternativen umgestellt; für E-Autos zählt jeder der beiden Schlüssel als gemappt. Konsistent mit `get_eauto_ladung_kwh`-Helper, `sensor_snapshot_service` und dem Monatsbericht-Pfad.

### Added

- **Counter-Spike Self-Heal — drei zusammengehörige Reparatur-Pfade (Rainer-PN-Spike 2026-05-01)** — Hintergrund: das v3.25.3-Cluster (Phase 1 5-Min-Snapshots aktivieren) hat den damals noch vorhandenen `get_value_at`-Off-by-one (behoben in v3.25.10) erstmals als sichtbaren Counter-Spike sichtbar gemacht (Slot 10:00 mit 2384 kWh statt 5 kWh). Bestehende Snapshot-Werte mussten manuell repariert werden — bisher nur via F12-Console.
  - **A: Vollbackfill mit `overwrite=True` zieht Snapshots frisch** — Bei aktiviertem Überschreiben ruft `backfill_from_statistics` jetzt vor der Pro-Tag-Schleife `resnap_anlage_range` für den gesamten Bereich auf. Das schreibt SensorSnapshots (hourly + 5-Min wo HA-Retention reicht) mit dem korrigierten `get_value_at`-Pfad neu, danach läuft der Aggregat-Pfad gegen frische Daten. `skip_existing=True`-Initial-Backfill bleibt unverändert. Frontend-Banner ergänzt um den Reparatur-Aspekt.
  - **B: „Tag neu aggregieren"-Button mit Resnap-Vorlauf** — Endpoint `/reaggregate-tag` bekommt `mit_resnap`-Parameter (Default `true`). Vor dem Aggregat werden die SensorSnapshots des Tages frisch aus HA-Statistics gezogen, dann läuft `aggregate_day` gegen die korrigierten Werte. Power-User können via `?mit_resnap=false` auf das alte Verhalten zurückfallen.
  - **C: Daten-Checker-Kategorie `ENERGIEPROFIL_PLAUSIBILITAET`** — Macht Counter-Spikes im Tagesprofil sichtbar statt Tester selbst forschen zu lassen. Schwelle: `pv_kw` oder `einspeisung_kw` > Anlagen-kWp × 1,5 (eindeutig unphysikalisch). Prüfraum: letzte 30 Tage `TagesEnergieProfil`. Detail-Meldung pro Tag mit betroffenen Stunden + Werten. Verweist auf den Reparatur-Workflow B. Doku in `HANDBUCH_DATEN_CHECKER.md` (Kategorie 9, neue §4.7 + §5.6).

### Changed

- **Konzept-Doc `KONZEPT-WALLBOX-EAUTO.md` Phase 2 ergänzt** — Daten-Checker-Warnung bei Pool-Pflege-Mismatch (E-Auto + Wallbox beide gepflegt, Werte erkennbar dieselbe Realität) als zusätzlicher Phase-2-Bestandteil dokumentiert. Hintergrund kommt aus dem Pool-Doppelzählungs-Befund 2026-05-02.

### Internal

- **Resnap-Endpoint v3.25.10 wird produktiv genutzt** — Die in v3.25.10 hinzugefügte Resnap-Funktion (`POST /api/diagnostics/resnap-snapshots`) bleibt als manuelles Diagnostik-Werkzeug; A und B nutzen den darin gekapselten `resnap_anlage_range`-Helper jetzt im regulären Service-Pfad.

---

## [3.25.10] - 2026-05-01

> 🐛 **Off-by-one-Stunde-Bug in Counter-Snapshots behoben** — `HAStatisticsService.get_value_at` las den `state` einer Zeile bei `start_ts ≈ zeitpunkt`, während HA's Konvention "last value of the period" ist: `state(start_ts=11:00)` ist der Zählerstand AM ENDE der Stunde, also um 12:00 Uhr. Damit waren alle SensorSnapshot-Werte seit v3.19 (Snapshot-Rework, Issue #135) systematisch um eine Stunde nach hinten verschoben. Tagessummen sind unbeeinflusst (zirkular), aber Stundenwerte im `tages_energie_profil` sind betroffen.
>
> 📦 **Bündelt v3.25.9 mit ein** — der separat geplante v3.25.9-Release (Drift-Audit-Bündel G) wurde zwischen dem Schreiben des CHANGELOGs und dem eigentlichen Release vom Off-by-one-Fix eingeholt. Statt zwei Releases im Abstand von Minuten zu schießen, sind beide Pakete unter Tag `v3.25.10` zusammengefasst. Die `[3.25.9]`-Sektion unten beschreibt den Bündel-G-Anteil — sie hat kein eigenes Tag, ihr Code (`field_definitions.py`-Reader-Helper, DB-Migration `_migrate_verbrauch_daten_keys_v326`) ist Teil von v3.25.10. Tag-Sprung 3.25.8 → 3.25.10 ist beabsichtigt.

### Fixed

- **`get_value_at` Off-by-one + sum-Bevorzugung** — Lookup-Target jetzt `zeitpunkt - period_length` (1h hourly, 5min short_term), Spalte `sum` mit Fallback auf `state` für measurement-Sensoren ohne `has_sum`. `sum` ist zusätzlich reset-bereinigt (HA tracked Resets transparent), `state` springt nach Tagesreset zurück. Befund verifiziert via HA-MCP gegen `sensor.sn_3012412676_pv_gen_meter` auf Winterborn 2026-05-01: HA Energy Dashboard 11–12 = 8.897 kWh = `change(start_ts=11)` = `sum(start_ts=11) - sum(start_ts=10)` ✓. Bug war maskiert durch (a) Tagessummen-Symmetrie und (b) HA-:05-Latenz, die beim Hourly-Job oft den korrekten Vorgänger-Slot lieferte. Mit Phase-1 5-Min-Snapshots wurde die Diskrepanz erstmals systematisch sichtbar.
- **Konsequenz für Phase 1 Live-Snapshot 5-Min** — Vor diesem Fix hätte das Frontend-Wiring auf 5-Min-Counter-Snapshots die Live-Tagesverlauf-Linie um 1 Stunde nach hinten verschoben. Phase-1-Frontend war deshalb zurückgehalten. Nach Resnap der letzten 7 Tage (siehe unten) und positivem Drift-Vergleich gegen HA Energy Dashboard kann das Wiring angegangen werden.

### Added

- **`POST /api/diagnostics/resnap-snapshots?days=N&include_5min=true`** — Schreibt für alle Anlagen die SensorSnapshots der letzten N Tage (1–14, default 7) neu. Sowohl hourly :00 als auch 5-Min Sub-Hour-Slots werden mit dem korrigierten `get_value_at`-Pfad regeneriert. Gedacht für Validierung nach Service-Bugfixes — der `get_value_at`-Fix schlägt sonst nicht auf bestehende Snapshot-Werte durch.
- **`snapshot_anlage_5min(force=True)`-Parameter** — bestehende 5-Min-Slots überschreiben statt überspringen. Wird vom Resnap-Endpoint genutzt, regulärer Scheduler-Job bleibt idempotent (`force=False`).

### Internal

- **`resnap_anlage_range(von, bis, include_5min)`** — Helper in `sensor_snapshot_service.py`, iteriert über Stunden (und optional 5-Min-Slots) und ruft `snapshot_anlage`/`snapshot_anlage_5min` mit `force=True`. Wiederverwendbar für künftige Service-Bugfixes oder die "Per-Tag-Reaggregation" UX.

---

## [3.25.9] - 2026-05-01 *(kein eigener Tag — mit v3.25.10 ausgeliefert)*

> 🧹 **Aufräum-Release ohne User-sichtbare Wirkung** — Letzter Bündel der Drift-Audit-Initiative aus v3.25.7/v3.25.8. Schließt 23 verstreute Doppel-Read-Stellen und konsolidiert die Daten in `verbrauch_daten`-JSONs auf kanonische Schlüssel. Werte-Anzeigen ändern sich nicht.
>
> ℹ️ **Tag-Hinweis:** Diese Sektion hat kein eigenes Git-Tag. Der Code (Reader-Helper + DB-Migration `_migrate_verbrauch_daten_keys_v326`) ist Teil von Tag `v3.25.10` — siehe [v3.25.10-Sektion](#32510---2026-05-01) oben für die Begründung.

### Changed

- **Zentrale Reader-Helper für `verbrauch_daten`-JSON (Bündel G)** — Bisher waren Doppel-Read-Muster der Form `data.get("a", 0) or data.get("b", 0)` für historisch umbenannte Felder an 23 Stellen über das Repo verstreut. Bei künftigen Schema-Wechseln musste jede einzelne Stelle gefunden und angepasst werden — ein Drift-Risiko, das bei jeder Code-Generation neu auflebt. Fünf Reader-Helper in `core/field_definitions.py` (`get_pv_erzeugung_kwh`, `get_wp_heizenergie_kwh`, `get_eauto_ladung_kwh`, `get_speicher_netzladung_kwh`, `get_sonstiges_verbrauch_kwh`) sind jetzt SoT. Alle 23 Stellen aufgerufen statt direkter `.get()`-Doppel-Reads. Künftige Schema-Wechsel betreffen nur einen Helper.

### Internal

- **DB-Migration `_migrate_verbrauch_daten_keys_v326`** — Schreibt Legacy-Keys in `InvestitionMonatsdaten.verbrauch_daten` auf den kanonischen Key um, sofern der Kanon-Key noch leer ist (wenn beide gesetzt, gewinnt der Kanon-Key). Pro Investitions-Typ unterschiedliches Mapping — `verbrauch_kwh` bei *Sonstiges* ist legitim und wird NICHT migriert. Idempotent, mit synthetischer Drift-DB verifiziert. Konsolidierte Pairs:
  - `erzeugung_kwh` → `pv_erzeugung_kwh` (PV-Modul, BKW)
  - `heizung_kwh` → `heizenergie_kwh` (WP)
  - `verbrauch_kwh` → `ladung_kwh` (E-Auto, Wallbox)
  - `speicher_ladung_netz_kwh` → `ladung_netz_kwh` (Speicher-Arbitrage)

  Migration läuft bei jedem Add-on-Start einmalig in `database.py:run_migrations()`. Bestehende Anlagen profitieren automatisch, kein User-Eingriff nötig.
- **Drift-Audit-Initiative abgeschlossen** — Mit diesem Release sind alle 16 Drifts aus 6 Domänen ([INVENTUR-DRIFT-AUDIT.md](docs/drafts/INVENTUR-DRIFT-AUDIT.md)) abgearbeitet. Bündel A (WP) in v3.25.7, Bündel B+C+D+E+F (E-Auto, Konstanten, Speicher-Spread, Strompreis-Helper, Filter) in v3.25.8, Bündel G (Field-Reader) in v3.25.9.

---

## [3.25.8] - 2026-05-01

> 📊 **Drift-Audit-Initiative** — als Folge des #178-Fixes (siehe v3.25.7) eine systematische Inventur aller Investitions-Berechnungen durchgeführt. 16 Drifts in 6 Domänen identifiziert ([INVENTUR-DRIFT-AUDIT.md](docs/drafts/INVENTUR-DRIFT-AUDIT.md)). Diese Version bündelt die Fixes für 5 davon (Bündel B, C, D, E, F). User-sichtbare Hauptänderung: Speicher- und V2H-Ersparnis im Aussichten-Tab werden jetzt nach demselben Spread-Modell berechnet wie das Investitionen-Detail (~25 % niedriger als vorher) — siehe Erklärung unten.

### Changed

- **Speicher- und V2H-Ersparnis im Aussichten-Tab: Spread-Modell statt Voll-Strompreis (Bündel D)** — Bisher rechnete Aussichten `entladung × Bezugspreis`, das Investitionen-Detail aber `entladung × (Bezug − Einspeise)`. Bei typischem Tarif (30/8 ct) ergab das **36 % Differenz** für dieselbe Anlage. Der ökonomisch korrekte Wert ist der Spread, weil die Speicher-Energie ohne Speicher als Einspeisung Vergütung erwirtschaftet hätte — nur die Differenz ist echter Netto-Gewinn. Aussichten ist jetzt auf das Spread-Modell umgestellt → User sehen bei einer Anlage mit z. B. 2000 kWh Durchsatz/Jahr nicht mehr 600 €, sondern 440 € Speicher-Ersparnis. V2H-Berechnung folgt der gleichen Logik. SpeicherDashboard-Label im Frontend korrigiert (vorher: „× Strompreis", war eine Lüge).
- **Cockpit-E-Auto-Ersparnis liest jetzt User-Werte (Bündel B)** — Bisher waren in den Cockpit-Stellen 7 L/100 km Vergleichsverbrauch und 1,80 €/L Benzinpreis hartcodiert; der gepflegte Pflege-Wert wurde ignoriert. Cockpit zeigte deshalb 7–9 % höhere Ersparnis als Aussichten/PDF (die respektierten den Pflege-Wert schon). Jetzt rufen alle Stellen denselben Helper auf, kanonische Defaults (7,5 L / 1,65 €/L). Folge: Cockpit-Ersparnis sinkt typisch um 3–5 % auf den korrekten Wert.
- **Hartcodierte Konstanten zentralisiert (Bündel C)** — Wirkungsgrade Gas/Öl (0,90 / 0,85 in 13 Stellen), CO2-Faktoren (0,38 / 2,37 in 7 Stellen) und Default-Tarife (8,2 ct Einspeise in 6 Stellen, 30 ct Bezug in 6 Stellen) werden jetzt aus zentralen Modulen gelesen statt überall dupliziert. Keine User-sichtbare Änderung außer minimalem CO2-Drift bei Gas (0,2 → 0,201 kg/kWh, ≈ 0,5 % höher — der korrekte Wert).

### Fixed

- **Cockpit-Wärmepumpe-Detail / KomponentenTab Ersparnis ignorierte User-Pflege (#178 Folge, Bündel A)** — *Bereits in v3.25.7 released, hier nur als Anker.* Vier UI-Stellen rechneten unterschiedliche WP-Ersparnis für dieselbe Anlage (7 € / 61 € / 77 € / 61 €). Helper `services/wp_wirtschaftlichkeit.py` mit kanonischer Formel + Param-Key-Fix.
- **Speicher-Dashboard ignorierte Anlagen-Tarife (Bündel E)** — Speicher-Endpoint nutzte bisher die hartcodierten Query-Param-Defaults `30 ct/8 ct` statt die Anlagen-Tarife aus der DB zu lesen. Jetzt werden Anlage-spezifische Tarife herangezogen (`netzbezug_arbeitspreis_cent_kwh`, `einspeiseverguetung_cent_kwh`).
- **Strompreis-Lookup-Kaskade vereinheitlicht (Bündel E)** — Drei verschachtelte Ternäre der Form `wallbox_tarif → allgemein_tarif → 30.0` durch zentralen Helper `resolve_strompreis_for_komponente(tarife, "allgemein|waermepumpe|wallbox")` ersetzt. Künftige Tarif-Änderungen wirken jetzt automatisch in allen Endpoints.
- **Cockpit-Prognose, HA-Sensor-Export und Community-Server-Submission ignorierten Anschaffungsdatum-Filter (Bündel F)** — Drei Endpoints aggregierten `InvestitionMonatsdaten` ohne den seit v3.23.1 in den anderen Endpoints aktiven Anschaffungsdatum-Check. Folge: Wenn User vor-Anschaffungs-Daten via CSV-Backfill geladen hatte (z. B. WP-Daten ab Januar, obwohl WP erst im April installiert), flossen diese in Cockpit-Prognose, HA-Sensor `wp_ersparnis_euro` und in den Community-Server-Datensatz ein. Jetzt nutzen alle drei `Investition.ist_aktiv_im_monat(jahr, monat)`. Fix verhindert künftig korrupte Community-Submissions.

### Internal

- **Inventur-Dokument [INVENTUR-DRIFT-AUDIT.md](docs/drafts/INVENTUR-DRIFT-AUDIT.md)** — 6 Domänen × 16 Drifts dokumentiert mit Render-Stellen-Matrix, Soll-Formel und Fix-Priorität. Ankerdokument für künftige Drift-Issues — bei neuen Forum-Berichten erst hier prüfen.
- **Neue Service-Helper als Single Source of Truth:** `wp_wirtschaftlichkeit.berechne_wp_ersparnis()` (Bündel A, schon in v3.25.7), `eauto_wirtschaftlichkeit.berechne_eauto_ersparnis()` (B), `speicher_wirtschaftlichkeit.berechne_speicher_ersparnis() / berechne_v2h_ersparnis()` (D). Konstanten-Module `core/wirtschaftlichkeit_defaults.py` (Backend) + `lib/wirtschaftlichkeitDefaults.ts` (Frontend).
- **Bündel G** (Field-Reader-Helper für `verbrauch_daten`-Schema-Drift mit DB-Migration, 27+ Doppel-Read-Stellen) wird in einer separaten Folge-Version umgesetzt — Migration-Risiko, sollte allein laufen.

---

## [3.25.7] - 2026-05-01

> ⚠ **Folge-Patch zum internen Test-Feature** — interessiert nur, wer den Diagnose-Endpoint nutzt (siehe v3.25.5).

### Fixed

- **fix(diagnostics): Microsecond-Mismatch im Live-Snapshot-5-Min-Endpoint** — In den Checks 4 (Mitternachts-Boundary) und 6 (Verdichtungs-Garantie) verglich der SQL `s.zeitpunkt = datetime('YYYY-MM-DD HH:00:00')`, die DB speichert die Werte aber als `'YYYY-MM-DD HH:00:00.000000'` (mit Microseconds). String-Equality matched nicht → beide Checks lieferten fälschlich `skip` mit „keine vollständigen Stunden". Fix: beide Seiten durch `datetime()` normalisieren, das strippt die Microseconds.

---

## [3.25.6] - 2026-05-01

### Changed

- **chore(addon-config): Add-on-Option `live_snapshot_5min_enabled` als TEST markieren + WAS-IST-NEU.md aktualisieren** — Drei kosmetische Klarstellungen zur Vermeidung versehentlicher Aktivierung des internen Test-Features:
  - **Add-on-UI Translation:** Neue `eedc/translations/de.yaml` + `en.yaml` geben der Option im Konfig-UI einen sprechenden Namen („5-Min-Snapshots (TEST — bitte aus lassen)") + Beschreibung („Internes Test-Feature ... Standard-User: aus lassen ... wird nach Validierung entfernt"). Andere Optionen ohne Translation bleiben mit YAML-Key-Anzeige (additiv).
  - **CHANGELOG-Hinweis-Block** prefix in v3.25.3 + v3.25.5 Release-Einträgen — die in GitHub Releases sichtbare Notiz „internes Test-Feature, default off, Standard-User brauchen nichts zu tun".
  - **WAS-IST-NEU.md** auf v3.25.5 hochgezogen + zwei klar User-sichtbare v3.25.3-Features ergänzt (#173 WP-Lebensdauer-Counter im Cockpit, #175 SortableSection in PV/WP/Monatsabschluss-Dashboards). Live-Snapshot 5-Min bewusst NICHT erwähnt — Test-Features gehören nicht in die User-Pflege-Seite.

---

## [3.25.5] - 2026-05-01

> ⚠ **Internes Test-Feature** — `live_snapshot_5min_enabled` ist eine Option für die Phase-1-Validierung der Counter-basierten Live-IST-Linie. Standard-User brauchen nichts zu tun (default off). Wird nach Abschluss der Tests entfernt oder default aktiviert.

### Fixed

- **fix(addon-config): `live_snapshot_5min_enabled` als Add-on-Option exposen** — In v3.25.3 als Env-Var `LIVE_SNAPSHOT_5MIN_ENABLED` im Backend eingeführt, aber vergessen in `eedc/config.yaml` (`options:` + `schema:`) zu deklarieren und in `eedc/run.sh` als Env-Var aus `/data/options.json` zu exportieren. Konsequenz: User sehen die Option im Add-on-Konfig-UI gar nicht und können das Phase-1-Backend nicht aktivieren — die Schnittstelle war bisher nur per Standalone-Docker mit eigenem Env-Var-Setup erreichbar. Fix: Boolean-Option `live_snapshot_5min_enabled` (default false) im Add-on-UI sichtbar, `run.sh` mappt sie nach `LIVE_SNAPSHOT_5MIN_ENABLED`. Dadurch lässt sich Phase 1 jetzt ohne Standalone-Workaround testen.

---

## [3.25.4] - 2026-05-01

### Added

- **feat(diagnostics): Endpoint `/api/diagnostics/live-snapshot-5min` für Phase-1-Validierung** — Wrapper um die sechs Checks aus `scripts/check-live-snapshot-5min.sh`, gibt JSON statt Terminal-Output zurück. Per `curl http://<addon-host>:8099/api/diagnostics/live-snapshot-5min` aus dem LAN abrufbar (kein Auth, weil Add-on-API im LAN läuft). Ersetzt das sqlite3-im-Container-Skript für den schnellen Fern-Check; das Skript bleibt als Standalone-Fallback. Gibt zusätzlich Scheduler-Job-Status (sind die neuen 5-Min-Crons registriert?), Feature-Flag-Wert und eine `summary`-Zeile mit PASS/WARN/FAIL-Tendenz zurück. Wird zur Frontend-Wiring-Entscheidung des Live-Snapshot-Pfads gebraucht (Voraussetzung: Drift gegen HA Energy Dashboard = 0, keine Glitches).

---

## [3.25.3] - 2026-05-01

> ⚠ **Live-Snapshot 5-Min ist ein internes Test-Feature** — die in diesem Release eingeführte Add-on-Option (offiziell ab v3.25.5) ist für die Phase-1-Validierung gedacht. Standard-User brauchen nichts zu tun (default off, keine User-sichtbare Wirkung). Wird nach Abschluss der Tests entfernt oder default aktiviert.

### Added

- **feat(live-snapshot-5min): Backend-Infrastruktur für Counter-basierte Live-IST-Linie (Phase 1, Konzept [KONZEPT-LIVE-SNAPSHOT-5MIN.md](docs/drafts/KONZEPT-LIVE-SNAPSHOT-5MIN.md))** — Heute lesen die Live-Tagesverlauf-Linie und das Wetter-Widget die IST-Stunden aus dem Power-Sensor (W) per Trapez-Integration über on-change-States. HA Energy Dashboard liest aus dem kWh-Counter (sum-delta). Beide weichen typisch um 1–3 % ab, weil die Trapezregel über ungleichmäßig verteilte Stützstellen systematisch driftet — Anwender sehen das als „die Linien stimmen nie überein, irgendwas an EEDC fabriziert Werte" (Rainer-PN 2026-04-30, hat als Konsequenz seine Energieprofil-Daten gelöscht „weil die eh falsch sind"). Lösung: kaskadierte Counter-Snapshots — wie bisher hourly für historische Tage (`sensor_snapshots` mit `zeitpunkt.minute = 0`, dauerhaft), plus 5-Min-Auflösung für den laufenden Tag (`zeitpunkt.minute ∈ {5,10,…,55}`, Cleanup nach 24h). Schema bleibt unverändert — `SensorSnapshot.zeitpunkt: DateTime` ist seit v3.19 granularitätsfrei.

  **Diese Phase implementiert nur die Backend-Infrastruktur:**
  - `Settings.live_snapshot_5min_enabled` (Env-Var `LIVE_SNAPSHOT_5MIN_ENABLED`, default off) — Roll-out per Anlage über Add-on-Config
  - [HAStatisticsService.get_value_at(short_term=True)](eedc/backend/services/ha_statistics_service.py#L613) — liest aus `statistics_short_term` statt `statistics` (HA hält die 5-Min-Slots ~10–14 Tage vor)
  - [snapshot_anlage_5min()](eedc/backend/services/sensor_snapshot_service.py#L950) — schreibt 5-Min-Snapshots, idempotent (überspringt belegte Slots, damit der reguläre `:05`-hourly-Job die :00-Snapshots nicht zerschießt), Toleranz 3 min gegen Latenz-Jitter
  - [cleanup_5min_snapshots()](eedc/backend/services/sensor_snapshot_service.py#L1015) — löscht Sub-Hour-Slots > 24h via `strftime('%M', zeitpunkt) != '00'`
  - Scheduler-Jobs `sensor_snapshot_5min` (`*/5:30` — 30s nach jeder HA short-term-Boundary) und `sensor_snapshot_5min_cleanup` (täglich `00:30`), beide nur registriert wenn Flag an
  - Restart-Recovery in [sensor_snapshot_startup_recovery](eedc/backend/services/scheduler.py#L569) um 5-Min-Slots seit `00:00` heute erweitert (nur wenn Flag an)

  **Frontend-Wiring (`live_tagesverlauf_service`) ist bewusst zurückgestellt** bis zur empirischen Bestätigung, dass die 5-Min-Snapshots auf einer realen Anlage stabil entstehen und der Drift gegen HA Energy Dashboard wirklich auf 0 fällt — sonst riskieren wir, dass die neue IST-Linie aus zu wenigen oder verglitchten Slots Murks rendert. Roll-out-Reihenfolge: Flag auf Winterborn aktivieren, ein paar Tage Snapshots sammeln (`SELECT COUNT(*) FROM sensor_snapshots WHERE strftime('%M', zeitpunkt) != '00'` sollte ~288 × Counter-Anzahl/Tag ergeben), dann Tagesverlauf-Linie umstellen und Default-on schalten. Power-Pfad bleibt als Fallback für Anlagen ohne Counter-Sensoren (häufig WP/Wallbox).

- **feat(wp-starts-baseline): Hersteller-Lebensdauer-Counter integrieren (Issue [#173](https://github.com/supernova1963/eedc-homeassistant/issues/173))** — Wärmepumpen-Hersteller wie Nibe oder Viessmann haben einen Counter „Kompressor-Starts gesamt" (Lebensdauer ab Werks-Inbetriebnahme, oft 4-stellig im Auslieferungszustand). EEDC zählt erst ab Sensor-Aktivierung über Snapshot-Differenzen — die historische Baseline fehlte, sodass das WP-Cockpit unter „Kompressor-Starts Σ" einen viel zu kleinen Wert zeigte (z.B. 87 statt 5.234). detLAN's Vorschlag im Issue: Baseline einmalig beim Wizard-Save eichen (`baseline = sensor.gesamt − Σ(eedc-Tagesdifferenzen seit Inbetriebnahme)`), dann beim Anzeigen `Σ_lebensdauer = baseline + Σ(eedc-Tagesdifferenzen)` rechnen. Selbstkorrigierend bei Wizard-Rerun.

  Implementierung: [compute_counter_baseline](eedc/backend/services/sensor_snapshot_service.py#L758) liest den aktuellen Sensor-Wert (Live-State → HA-Statistics → jüngster Snapshot) und subtrahiert die kumulierten EEDC-Tagesdifferenzen aus `TagesZusammenfassung.komponenten_starts` ab `inv.anschaffungsdatum`. Das Ergebnis wird beim Sensor-Mapping-Save automatisch in `inv.parameter.{wp_starts_anzahl}_baseline` abgelegt ([_refresh_counter_baselines](eedc/backend/api/routes/sensor_mapping.py#L457)) — Fehler beim Baseline-Lookup (z.B. Sensor noch unavailable) brechen das Mapping-Save **nicht** ab, sondern werden geloggt. WP-Cockpit ([WaermepumpeDashboard.tsx:308](eedc/frontend/src/pages/WaermepumpeDashboard.tsx#L308)) zeigt Σ_lebensdauer = baseline + EEDC, mit Tooltip-Zerlegung „Hersteller-Baseline (Wizard-Save) + EEDC seit Aktivierung + höchste Tagessumme".

### Changed

- **chore(ui): SortableSection als wiederverwendbare Komponente extrahiert + auf 3 Cockpit-Dashboards ausgerollt (Issue [#175](https://github.com/supernova1963/eedc-homeassistant/issues/175), detLAN-Vorschlag)** — Die seit v3.21.0 im Auswertungs-Tab vorhandene Auf-/Zuklappen-+-Sortierung-Mechanik war an die `MonatsabschlussView` hartgekoppelt. detLAN hat im Forum vorgeschlagen, dasselbe Verhalten auch in andere Cockpit-Ansichten zu bringen. Refactor:

  - Neue UI-Komponente [SortableSection](eedc/frontend/src/components/ui/SortableSection.tsx) (mit `OrderedSections`-Container) und Hook [useSectionOrder](eedc/frontend/src/hooks/useSectionOrder.ts) extrahiert. Persistiert die User-Reihenfolge per Anlage in `localStorage` (Schlüssel `eedc.section_order.{viewKey}.{anlageId}`).
  - [MonatsabschlussView.tsx](eedc/frontend/src/pages/MonatsabschlussView.tsx) auf die neue Komponente migriert (-199 Zeilen — der Großteil war duplizierter Drag-Drop-Boilerplate, jetzt im SortableSection-Modul).
  - [PVAnlageDashboard.tsx](eedc/frontend/src/pages/PVAnlageDashboard.tsx) und [WaermepumpeDashboard.tsx](eedc/frontend/src/pages/WaermepumpeDashboard.tsx) auf SortableSection umgebaut — die WR-Karten / KPI-Sektionen / Komponenten-Listen lassen sich jetzt einzeln einklappen und neu anordnen, Reihenfolge wird pro Anlage gespeichert.

  Verhalten ist 1:1 identisch zur bisherigen Auswertungs-Implementierung, nur eben jetzt überall. Konzept-Skizze in [docs/drafts/KONZEPT-COCKPIT-LAYOUT.md](docs/drafts/KONZEPT-COCKPIT-LAYOUT.md).

---

## [3.25.2] - 2026-04-30

### Fixed

- **fix(wp-starts): Slot 23:00 + Tagesaggregat-Lücke bei Kompressor-Starts (Issue [#136](https://github.com/supernova1963/eedc-homeassistant/issues/136))** — Im stündlichen Snapshot-Pfad ([sensor_snapshot_preview_job](eedc/backend/services/scheduler.py#L412)) crashte der :55-Vorab-Snapshot-Job seit Einführung in v3.21.0 (Issue #146) still mit `NameError: timedelta is not defined` — der Import in [scheduler.py:9](eedc/backend/services/scheduler.py#L9) fehlte. Konsequenz: der 00:00-Boundary-Snapshot wurde nicht vorab geschrieben, sondern musste vom regulären :05-Job ab Mitternacht aus HA Statistics gezogen werden. Bei Counter-Sensoren ohne `state_class` (typisch Nibe/Viessmann WP-Starts) ist die LTS-Tabelle zu :05 oft noch leer → Snapshot fehlt → sowohl Slot 23 im Tagesdetail (`get_hourly_counter_sum_by_feld` braucht snap[24]) als auch der Tageswert in Monatsbericht/Cockpit-WP (`get_daily_counter_deltas_by_inv` braucht snap @ 00:00 Folgetag) bleiben leer. Beide Lücken haben dieselbe Wurzelursache. Fix: `timedelta` zum Import ergänzt — `:55`-Job läuft wieder und schreibt den 00:00-Snapshot vorab als Live-Approx, der reguläre `:05`-Job überschreibt ihn später mit dem exakten LTS-Wert. detLAN-Mehrfach-Beobachtung über mehrere Tage.

### Changed

- **chore(pv-cockpit): Module + Speicher nebeneinander in 2-Spalten-Grid (Issue [#172](https://github.com/supernova1963/eedc-homeassistant/issues/172))** — In [PVAnlageDashboard.tsx:273-318](eedc/frontend/src/pages/PVAnlageDashboard.tsx#L273) waren die Sub-Sektionen *Module* und *Speicher* innerhalb der Wechselrichter-Karte vertikal gestapelt — bei vielen Komponenten wirkte die Karte länglich und unausgewogen. Jetzt nebeneinander in `grid-cols-1 md:grid-cols-2` (Desktop zwei Spalten, Smartphone weiterhin gestapelt), gemäß detLAN-Mockup. Innerhalb jeder Sub-Sektion bleiben Werte rechtsbündig (`ml-auto`), Bezeichnung darf truncaten.

---

## [3.25.1] - 2026-04-29

### Fixed

- **fix(hilfe): Interne Links + Anker im Inhaltsverzeichnis funktionieren wieder** — Drei Bugs in der seit v3.24.0 verfügbaren In-App-Hilfe ([Hilfe.tsx](eedc/frontend/src/pages/Hilfe.tsx)):
  - **Anker-Links im Inhaltsverzeichnis zerstörten die Hilfe-Seite.** Klick auf TOC-Einträge wie `[Installation](#2-installation)` setzte `window.location.hash` auf `#2-installation`, was den HashRouter-Routen-Hash (`#/hilfe?doc=…`) überschrieb — die Hilfe-Seite verschwand. Da fast jedes Hilfe-Dokument ein TOC mit Anker-Links hat, war das der dominierende Fail-Modus (Rainer-PN).
  - **Headings hatten gar keine `id`.** Die Custom-Komponenten für `h1`/`h2`/`h3` ließen den `id`-Prop fallen und es war kein Slug-Plugin aktiv — Anker-Targets existierten also nicht.
  - **Externe `…/CHANGELOG.md`-URLs wurden zu Doppel-URLs umgeschrieben.** Die `rewriteLink`-Regex matchte ALLE Strings die auf `.md` enden (auch absolute `https://`-URLs), und der Fallback-Pfad präfixte dann `https://github.com/.../docs/` vor die volle URL.

  **Fixes:**
  - `rehype-slug` (Auto-IDs auf Headings) + `rehype-raw` (manuelle `<a name="…">`-Anker im `HANDBUCH_DATEN_CHECKER.md` bleiben erhalten) eingeführt.
  - `id`-Prop in `h1`–`h4`-Komponenten durchgereicht.
  - Absolute URLs in `rewriteLink` erkannt (Protokoll-Regex).
  - Anker-Klicks intercepten jetzt `preventDefault` und scrollen im echten Scroll-Container — `<main>`, nicht `<article>` (verschachtelte Overflow-Container, je nach Höhen-Constraint scrollt mal das eine, mal das andere).
  - Inter-Doc-Links mit Hash (`?doc=bedienung#3-cockpit-dashboards`) scrollen nach Doc-Wechsel an die Ziel-Heading.
  - Browser-Back funktioniert wieder, weil jede Navigation einen sauberen History-Eintrag setzt statt die Route zu zerstören.

  Verifiziert mit Headless-Chrome-Click-Test über vier Szenarien (Inter-Doc / extern / Anker-in-Doc / Inter-Doc-mit-Hash).

---

## [3.25.0] - 2026-04-29

### Refactor

- **refactor(investitions-parameter): Single Source of Truth für `parameter`-JSON-Keys + 7 Drift-Bugs gefixt** — Investitionen tragen ihre typ-spezifischen Detail-Daten in einem unstrukturierten JSON-Feld (`parameter`). Über mehrere Iterationen waren Schlüsselnamen zwischen **Form** ([InvestitionForm.tsx](eedc/frontend/src/components/forms/InvestitionForm.tsx)), **Wizard** ([InvestitionenStep.tsx](eedc/frontend/src/components/setup-wizard/steps/InvestitionenStep.tsx)) und **Backend-Lese-Code** (ROI, Aussichten, Live, HA-Export, PDF, Cockpit, Community) auseinandergedriftet. Der ursprünglich als Schema gedachte API-Endpoint `/investitionen/typen` mit `parameter_schema` war zudem ein Phantom — exportiert und vom Frontend nie aufgerufen, dafür inhaltlich von den echten Form/Wizard-Keys abweichend. Eine Vollinventur (siehe [docs/drafts/INVENTUR-INVESTITIONS-PARAMETER.md](docs/drafts/INVENTUR-INVESTITIONS-PARAMETER.md)) hat 7 Production-Bugs zutage gefördert, in denen das Backend Schlüssel las, die Form/Wizard nie geschrieben haben — d. h. User-Eingaben wurden im ROI / Aussichten-Tab / Live-Komponenten-Erkennung / Wallbox-Dashboard / Community-Datensatz stillschweigend ignoriert und durch hartkodierte Defaults ersetzt.

  **Strukturelle Änderungen:**
  - **Single Source of Truth eingeführt:** `eedc/frontend/src/lib/investitionParameter.ts` und `eedc/backend/core/investition_parameter.py` — pro Investitions-Typ eine Konstanten-Map, ein TS-Interface (Frontend) und eine `_DEFAULTS`-Map mit zentral verbindlichen Default-Werten (Frontend und Backend importieren denselben Default, damit Default-Drift wie Bug #7 strukturell unmöglich ist).
  - **Phantom-Endpoint `/investitionen/typen` entfernt** (165 Zeilen `parameter_schema`-Block in `investitionen.py`, `InvestitionTypInfo` API-Type, `useInvestitionTypen`-Hook, `getTypen`-API-Methode). Nichts ruft das mehr auf, das Schema war historisch toter Code.
  - **Frontend-Refactor:** Form-Defaults aus den `_DEFAULTS`-Konstanten geladen (vorher hardcoded Strings); Wizard-`getParam('…')`/`updateParam('…', …)`-Calls auf Konstanten-Lookups umgestellt; Render-Stellen ([PVAnlageDashboard](eedc/frontend/src/pages/PVAnlageDashboard.tsx), [Investitionen.tsx](eedc/frontend/src/pages/Investitionen.tsx)) lesen über typed Helper (`speicherParameter(inv.parameter).kapazitaet_kwh`).
  - **Backend-Refactor:** Alle `inv.parameter.get("…")` in [aussichten.py](eedc/backend/api/routes/aussichten.py), [investitionen.py](eedc/backend/api/routes/investitionen.py), [ha_export.py](eedc/backend/api/routes/ha_export.py), [ha_import.py](eedc/backend/api/routes/ha_import.py), [sensor_mapping.py](eedc/backend/api/routes/sensor_mapping.py), [cockpit/uebersicht.py](eedc/backend/api/routes/cockpit/uebersicht.py), [pdf_operations.py](eedc/backend/api/routes/import_export/pdf_operations.py), [community_service.py](eedc/backend/services/community_service.py) und [live_komponenten_builder.py](eedc/backend/services/live_komponenten_builder.py) auf `PARAM_<TYP>["KEY"]`-Konstanten umgestellt; defensive Doppel-Reads (z. B. `nutzt_v2h or v2h_faehig` in `ha_import.py:80`) durch den Kanon ersetzt, weil die DB-Migration Drift-Inhalte vereinheitlicht.
  - **DB-Migration `_migrate_investitionen_parameter_keys_v325`** in [database.py](eedc/backend/core/database.py): iteriert beim Start einmalig alle Investitionen, schreibt alte JSON-Keys auf den Kanon um (`nutzt_v2h` → `v2h_faehig`, `km_jahr` → `jahresfahrleistung_km`, `pv_anteil_prozent` → `pv_ladeanteil_prozent` (E-Auto only), `benzin_verbrauch_liter_100km` → `vergleich_verbrauch_l_100km`, `nutzt_arbitrage` → `arbitrage_faehig`, `leistung_kw`/`ladeleistung_kw` → `max_ladeleistung_kw` (Wallbox), `getrennte_strommessung` String → Boolean). Idempotent — läuft beim ersten Mal echt, danach No-Op. Smoke-Test mit synthetischer Drift-DB validiert.

  **Behobene Bugs (User-sichtbar):**
  - **#1 V2H 3-fach kaputt** — [aussichten.py:1414](eedc/backend/api/routes/aussichten.py#L1414), [live_komponenten_builder.py:130](eedc/backend/services/live_komponenten_builder.py#L130) und [investitionen.py:1167](eedc/backend/api/routes/investitionen.py#L1167) lasen `nutzt_v2h` ohne Fallback, Form/Wizard schreiben `v2h_faehig`. Konsequenz: V2H-Aktivierung in der Maske wurde im Aussichten-Tab, in der Live-Komponenten-Erkennung und im E-Auto-ROI ignoriert. Nur `ha_import.py:80` hatte einen defensiven Doppel-Read.
  - **#2 E-Auto Jahresfahrleistung im ROI ignoriert** — investitionen.py:1163 las `km_jahr` mit Default 15000, Form schreibt `jahresfahrleistung_km`.
  - **#3 E-Auto PV-Ladeanteil im ROI ignoriert** — `pv_anteil_prozent` (Default 60) statt `pv_ladeanteil_prozent`.
  - **#4 E-Auto Vergleichsverbrauch im ROI ignoriert** — `benzin_verbrauch_liter_100km` (Default 7.0) statt `vergleich_verbrauch_l_100km`. Aussichten + ha_export + pdf nutzten den richtigen Key, ROI weichte ab.
  - **#5 Speicher-Arbitrage-ROI kaputt** — investitionen.py:1018+1140 (DC- und AC-Speicher) lasen `nutzt_arbitrage` mit Default False. Form/Wizard/Dashboard/ha_import nutzten `arbitrage_faehig`. Konsequenz: User aktivierte Arbitrage, ROI ignorierte die Aktivierung — Dashboard zeigte Arbitrage-Sektion korrekt.
  - **#6 Wallbox-Leistung im Dashboard kaputt** — investitionen.py:2032 las `leistung_kw` (toter Schema-Key) mit Default 11. Form/Wizard schreiben `max_ladeleistung_kw`. Plus 2. Stelle: community_service.py:144 las `ladeleistung_kw` (auch tot) → Community-Datensatz lieferte stets `wallbox_kw=None`.
  - **#7 WP `alter_preis_cent_kwh` Default-Inkonsistenz** — aussichten.py:1091 und ha_export.py:241 defaulteten auf 10.0, alle anderen auf 12.0. Bei leerem Form-Wert sah der User je nach Tab unterschiedliche Ersparnis. Default jetzt zentral aus `PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"] = 12`.
  - **#8 WP `getrennte_strommessung` String-vs-Boolean** — Form speicherte als String `'true'`/`'false'`, Dashboard wertete als Boolean aus. `'false'` ist JS-truthy → Schalter ging nicht aus. DB-Migration korrigiert auch das.

  **Auswirkungen für bestehende Anlagen:** Tester, die bisher V2H, Arbitrage oder eine von 11 kW abweichende Wallbox-Leistung im Form aktiviert/eingegeben haben, sehen ab v3.25.0 plötzlich neue Werte im ROI, im Aussichten-Tab und im Wallbox-Dashboard. Die alten Werte waren Default-Anzeigen, nicht User-Werte.

---

## [3.24.6] - 2026-04-29

### Bugfixes

- **fix(pv-cockpit): Speicher-Kapazität wird wieder angezeigt — Key-Drift behoben (#172 detLAN, Folgefix zu v3.24.4)** — In v3.24.4 sollte die Speicher-Kapazität in „Cockpit → PV-Anlage → PV-Komponenten" zusätzlich zur Bezeichnung erscheinen. Der Render-Code in [PVAnlageDashboard.tsx](eedc/frontend/src/pages/PVAnlageDashboard.tsx) las den Wert aber unter dem falschen Schlüssel `batteriekapazitaet_kwh` (das ist der E-Auto-Key) — gespeichert wird die Speicher-Kapazität überall im Backend und in `InvestitionForm` als `kapazitaet_kwh`. Konsequenz: gepflegte Daten waren da, der Cockpit-Block blieb leer und wirkte „unausgewogen". Ursache ist die in der Memory-Lesson schon notierte Drei-Sprachen-Drift (Backend / Wizard / Form). Jetzt liest das Cockpit denselben Schlüssel wie das Speicher-Formular.

### Verbesserungen

- **feat(pv-cockpit): WR/Module/Speicher in PV-Komponenten visuell getrennt + Orphan-Speicher-Block (#172 detLAN)** — Innerhalb jeder Wechselrichter-Karte werden Module und Speicher jetzt in eigenen, beschrifteten Sub-Sektionen mit hellem Hintergrund-Tint dargestellt — vorher standen sie gemischt in einem 2-Spalten-Grid. Werte (kWp / kWh) richten sich rechtsbündig aus (`ml-auto` + `whitespace-nowrap`), die Bezeichnung darf links truncaten. Speicher ohne Wechselrichter-Zuordnung (Parent ist optional) wurden bisher stillschweigend aus dem Cockpit ausgeblendet — sie erscheinen jetzt in einem separaten Block „Speicher ohne Wechselrichter-Zuordnung" am Ende des PV-Komponenten-Blocks, analog zum bestehenden Orphan-Module-Hinweis.

- **fix(wizard): Kompressor-Starts-Hinweistext gestrafft (#136 detLAN)** — Im Sensor-Mapping → Wärmepumpe-Step war der Erklär-Text unter dem Feld „Kompressor-Starts" auf detail-orientierte Tester zugeschnitten („Bei Nibe und Viessmann fehlt der Sensor häufig…, weil ihm `state_class` nicht gesetzt ist"). detLAN hat die Formulierung als für Einsteiger zu technisch gemeldet und einen klareren Hinweis vorgeschlagen. Jetzt: „Sollte der Sensor das „ohne Statistik"-Badge aufweisen, beachte bitte die Anleitung zum Nachrüsten — siehe Hilfe → Sensor-Referenz → „ohne Statistik"-Badge." Die referenzierte Stelle in `docs/SENSOR-REFERENZ.md` enthält jetzt den `customize.yaml`-Snippet direkt unter §„ohne Statistik"-Badge (statt drei Sektionen weiter unten unter „Plan B außerhalb von EEDC") und einen klaren Hinweis, dass die Korrektur nur ab Aktivierungs-Zeitpunkt greift, nicht rückwirkend (Lesson aus v3.24.3).

---

## [3.24.5] - 2026-04-29

### Dokumentation

- **feat(hilfe): Was-ist-neu-Seite als Pull-Variante (Discussion #130 Folge-Wunsch von Safi105)** — Statt eines What's-new-Banners nach Update jetzt eine eigene Hilfe-Seite *„Was ist neu"* in der In-App-Hilfe-Sidebar (Kategorie *Einstieg*, direkt unter „Übersicht"). Begründung: HA-Add-on-Nutzer sehen den Changelog ohnehin schon im Add-on-Store beim Update, GitHub-Releases haben einen eigenen — ein zusätzlicher Banner wäre die dritte Stimme zur selben Information. Pull statt Push respektiert den Nutzer und spart die ganze localStorage-/Versionsvergleich-/Bestand-vs-Neuinstall-Mechanik des ursprünglichen Banner-Konzepts. Inhalt: ~270 Zeilen, pro Version 3–5 anwender-perspektivisch formulierte Highlights mit Deep-Links in die zuständigen Hilfe-Sektionen, chronologisch absteigend von v3.24 zurück bis v3.16. Footer-Block mit vier weiterführenden Quellen (CHANGELOG, Releases-Übersicht, Repo, Online-Doku). Discussion [#130](https://github.com/supernova1963/eedc-homeassistant/discussions/130). Konzept-Datei `docs/KONZEPT-WHATS-NEW-BANNER.md` als „verworfen" markiert, Body bleibt als Entscheidungs-Beleg erhalten.

- **build(release.sh): Soft-Check für Major.Minor-Sektion in docs/WAS-IST-NEU.md** — Prüft beim Release, ob für die neue Version eine `## v3.X.x`- oder `## v3.X`-Sektion in der „Was ist neu"-Hilfe-Seite vorhanden ist. Bei reinen Bugfix-Patches (Major.Minor existiert schon) → kein Friction. Bei Sprung in eine neue Versionsreihe (z. B. v3.25.0) → Warnung mit Bestätigungs-Prompt, damit der Maintainer bewusst entscheidet zwischen „neuer Highlights-Block" und „diesmal nichts Anwender-Sichtbares". Volle Auto-Befüllung aus CHANGELOG bewusst nicht — die zwei Stränge bedienen unterschiedliche Zielgruppen (technisch vs. anwender-perspektivisch). `scripts/sync-help.sh` synchronisiert die Page beim Frontend-Build automatisch.

- **fix(handbuch): In-App-Hilfe-Einführungsversion v3.24.0 → v3.24.2** — Im Benutzerhandbuch zwei Stellen, die die In-App-Hilfe als „eingeführt in v3.24.0" auswiesen — tatsächlich kam sie in v3.24.2 (Commit `51922da6` liegt zwischen Tag v3.24.1 und v3.24.2). Korrigiert in `docs/BENUTZERHANDBUCH.md` (Lifecycle-Block + „Was ist neu seit v3.16?"-Tabelle).

---

## [3.24.4] - 2026-04-29

### Verbesserungen

- **feat(cockpit): Kompressor-Starts in Monatsbericht + WP-Dashboard (#169 detLAN)** — KPI-Kacheln für die in v3.24.0 erfassten WP-Kompressor-Starts, Quelle ist `TagesZusammenfassung.komponenten_starts`. **MonatsabschlussView** (Cockpit → Monatsberichte, WP-Sektion): neuer Tile „Kompressor-Starts (Max/Tag)" — höchste Tagessumme im Monat als Hauptzahl (Verschleiß-Indikator), Σ im Monat als Subtitle. **WaermepumpeDashboard** (Cockpit → Wärmepumpe): neuer Tile mit Σ über die Lebensdauer ab Anschaffung als Hauptzahl (Auslegungs-Indikator), Max/Tag als Subtitle. Backend-Aggregation in beiden Endpoints (`get_aktueller_monat` über Monat, `get_waermepumpe_dashboard` über Lebensdauer) liest `TagesZusammenfassung` zusätzlich zu `InvestitionMonatsdaten` — gefiltert pro WP-Investition aus dem JSON `wp_starts_anzahl`-Subfeld. **Live-Dashboard bewusst ausgenommen** — WP-Starts heute sind nur in der Trimming-Phase aussagekräftig; nach Einstellungs-Findung wäre das Feld Karteileiche. Auswertung → Energieprofil → Monat-Tabelle bleibt unverändert (WP-Starts-Spalte ist seit v3.24.0 dort einblendbar).

- **fix(energieprofil-monat): Jahre-Selektor ab Anlagen-Inbetriebnahmejahr (#171 detLAN)** — Der Monat-Tab im Energieprofil zeigte fix die letzten 6 Jahre, also auch Jahre vor Inbetriebnahme der Anlage — bei detLANs Anlage (PV seit 2023) erschienen 2021/2022 als wählbare aber inhaltslose Optionen. `EnergieprofilMonat` lädt jetzt beim Mount die Anlage und nutzt `installationsdatum.year` als Untergrenze der Optionen-Range. Fallback ohne `installationsdatum`: weiterhin 6 Jahre rückwärts.

- **fix(ha-statistik-import): doppeltes Icon entfernt + Navigation in Card-Hülle (#170 detLAN)** — Zwei Kosmetik-Punkte aus detLANs Screenshots: (1) Im Datenbank-Status-Alert standen zwei Häkchen-Icons hintereinander — der `<Alert type="success">` bringt sein Icon selbst mit, der explizite `<CheckCircle>` daneben war redundant. Beide entfernt (auch `<XCircle>` im Error-Branch + ungenutzter Import). (2) Die unteren Navigations-Buttons („Zurück zu Sensor-Zuordnung" / „Zu Monatsdaten") standen direkt auf dem Page-Hintergrund ohne Card-Hülle, während der gesamte Hauptinhalt in weissen Cards mit Border lebt. Jetzt in derselben `bg-white`/Border-Card eingebettet, konsistent mit dem Layout-Stil der Seite.

- **fix(pv-cockpit): Speicher-Kapazität + WR-Eigenleistung in PV-Komponenten anzeigen (#172 detLAN)** — Im PV-Anlagen-Cockpit zeigte der „PV-Komponenten"-Block beim Speicher ausschließlich die Bezeichnung — Kapazität (`batteriekapazitaet_kwh`), nutzbare Kapazität (`nutzbare_kapazitaet_kwh`) und WR-Eigenleistung (`max_leistung_kw`) wurden nirgendwo gerendert, obwohl die Stammdaten gepflegt sein können. Beim Wechselrichter stand rechts nur die Σ-Modul-kWp, was bei einer Anlage mit nur einem Modul-Eintrag wie ein Echo der Modul-Zeile darunter wirkte. Speicher-Zeile zeigt jetzt Kapazität (kWh) wenn gepflegt; bei abweichender nutzbarer Kapazität (DOD-Reserve > ~0.05 kWh) zusätzlich „(X nutzbar)" in Klammern. Wechselrichter-Header zeigt jetzt „WR X kW · Module Σ Y kWp" wenn `max_leistung_kw` gepflegt ist (sonst nur „Module Σ Y kWp"). Lade-/Entladeleistung und Wirkungsgrad bewusst nicht im Cockpit-Kontext — die gehören in die Speicher-Detail-Seite.

---

## [3.24.3] - 2026-04-29

### Verbesserungen

- **fix(sensor-zuordnung + daten-checker): state_class-Hinweise auf den richtigen Hebel umgestellt + Counter-Branch zu WARNING (#136 Folge)** — Im Nachgang zu detLANs (#136) und Joachims (Forum #436) Berichten zur 23–24-Uhr-Lücke wurde gemeinsam herausgearbeitet, dass die bisherige Begründung „vergangene Tage bleiben leer" am eigentlichen Problem vorbeigeht: das passiert auch mit `customize.yaml`-Korrektur, weil HA LTS erst ab dem Aktivierungs-Zeitpunkt persistiert. **Der relevante Unterschied im Betrieb:** ohne `state_class` greifen die **Korrektur-Werkzeuge in der Datenverwaltung** nicht — Vollbackfill, „Verlauf nachrechnen" und Per-Tag-Reaggregation lesen alle aus HA's LTS. Jeder Aussetzer (HA-/EEDC-Neustart, Polling-Hänger um Mitternacht) ist bei einem Sensor ohne `state_class` **permanent verloren**, eine zweite Chance gibt es nicht. Drei Stellen entsprechend nachgezogen: **(1) Wizard-Banner** [SensorMappingWizard.tsx](eedc/frontend/src/pages/SensorMappingWizard.tsx) — „Korrektur-Werkzeuge wirken nicht" als zentrale Folge, „Aussetzer permanent verloren" und „23–24 Uhr fehlt häufig" als nachgelagerte Symptome. **(2) Daten-Checker SENSOR_MAPPING_LTS** [daten_checker.py](eedc/backend/services/daten_checker.py) — Counter-Branch von INFO auf **WARNING** hochgestuft (vorher als „erwartetes Verhalten" beschrieben, was angesichts der fehlenden Reparatur-Werkzeuge zu beruhigend war), kWh- und Counter-Details auf den neuen Hebel umformuliert. **(3) Badge-Tooltips** in [FeldMappingInput.tsx](eedc/frontend/src/components/sensor-mapping/FeldMappingInput.tsx) — der irreführende Halbsatz „für Counter unproblematisch" ist raus. **(4) WP-Step-Hilfetext** [WaermepumpeStep.tsx](eedc/frontend/src/components/sensor-mapping/WaermepumpeStep.tsx) — der ausführliche customize-Snippet-Block ist gekürzt auf einen einzeiligen Verweis auf Hilfe → Sensor-Referenz. **Filter-Aufweichung bleibt** — Power-User mit nicht-konfigurierbarer HA-Installation behalten die Möglichkeit, einen Sensor ohne `state_class` zu wählen, sehen aber jetzt klar, was sie damit aufgeben.

---

## [3.24.2] - 2026-04-28

### Dokumentation

- **docs(handbuch): Sweep v3.16–v3.24 — Funktions-Inventur über alle Hilfe-Dokumente** — Alle acht in der In-App-Hilfe gerenderten Markdown-Dokumente (`BENUTZERHANDBUCH`, `HANDBUCH_INSTALLATION/BEDIENUNG/EINSTELLUNGEN/INFOTHEK`, `BERECHNUNGEN`, `SENSOR-REFERENZ`, `GLOSSAR`) wurden im Bündel auf den Stand von v3.24.1 gehoben. Hintergrund: nach Aktivierung der In-App-Hilfe in v3.24.0 (#130) wurde Veraltung sofort sichtbar — Versions-Stempel waren bereits korrekt, aber viele in v3.16–v3.23 ergänzte Funktionen fehlten in den Detail-Beschreibungen. **Bedienung** bekommt einen neuen §5.8 Energieprofil-Tab (Beta) und einen kompletten §7.2 Prognosen-Tab (OpenMeteo / EEDC kalibriert / Solcast / IST inkl. MAE/MBE-Trennung, Asymmetrie-Diagnostik aus v3.23.3, Reparatur-Popover bei IST-Lücken, Backward-Slot-Konvention); Cockpit-Reihenfolge auf v3.23.4-Stand, WP-KPI-Reihenfolge JAZ → Wärme → Strom → Ersparnis. **Einstellungen** bekommt einen neuen §1.6 zur Energieprofil-Seite (Tages-Tabelle mit Pro-Tag-Reaggregation, Datenverwaltung pro Anlage), das Sensor-Mapping mit Solcast-Toggle, Strompreis-Sensor, JAZ-Wording, „ohne Statistik"-Badge und Fallback-Link sowie Daten-Checker auf 8 Kategorien (inkl. MQTT-Topic-Abdeckung #134 und HA-Statistics-Sensor-Mapping). **Berechnungen** bekommen einen neuen §4.1c zu Lernfaktor / saisonaler MOS-Kaskade / MAE+MBE-Trennung / Asymmetrie-Diagnostik plus überarbeiteten §6b (Snapshot-Architektur, Backward-Slot, GTI-PR, Vollzyklen-Filter auf stationäre Speicher). **Sensor-Referenz** mit Strompreis-Sensor, WP-Kompressor-Starts-Counter, Solcast-Anbindung (BJReplay + API), Counter-vs-kWh-Trennung und LTS-Verfügbarkeit. **Glossar** thematisch in 8 Gruppen umgebaut. **Installation** bekommt den „Empfohlene Nutzung"-Block (datendichte App, Desktop empfohlen — als technische App-Eigenschaft formuliert) und 5 neue Fehlerbehebungs-Einträge. **Übersicht** bekommt einen Lifecycle-Block der In-App-Hilfe selbst und eine kuratierte „Was ist neu seit v3.16?"-Tabelle mit Deep-Links — als statische Vorlage für einen späteren What's-new-Banner (Discussion #130 Folge-Wunsch von Safi105).

- **docs(konzept): What's-new-Banner nach Update** — Konzept-Skizze unter [`docs/KONZEPT-WHATS-NEW-BANNER.md`](docs/KONZEPT-WHATS-NEW-BANNER.md): versionsbezogener In-App-Banner mit kuratierten Highlights seit der zuletzt vom Nutzer gesehenen Version, Datenquelle initial aus der „Was ist neu seit v3.16?"-Tabelle des Benutzerhandbuchs, Persistenz per `localStorage`, Re-Open via Hilfe-Sidebar-Eintrag. Bewusst keine automatische CHANGELOG-Extraktion (technisch vs. anwenderzentriert), kein Analytics. Antwort auf Safi105's Folge-Reply in Discussion #130 nach der Zusage zur In-App-Hilfe; Implementierung offen, Trigger: ruhiges Forum-Bündel oder Major-Sprung.

---

## [3.24.1] - 2026-04-28

### Bugfixes

- **fix(sensor-zuordnung): Nibe-Roh-Counter und sonstige `total_increasing`-Sensoren ohne Standard-Unit auswählbar (#136 Folge-Fix detLAN)** — detLAN testete v3.24.0 mit `sensor.compressor_number_of_starts_eb101_ep14_31490` (lokale „Nibe Heat Pump"-Integration) und konnte den Sensor im Wizard nicht finden — und im Frontend gibt es keine Freitext-Eingabe als Notausgang. Ursache: die Nibe-Integration setzt für Coils mit unbekannter Unit weder `state_class` noch `device_class` noch `unit_of_measurement` ([Community-Thread](https://community.home-assistant.io/t/statistics-card-and-nibe-s1155-compressor-number-of-starts-eb100-ep14/791289)) — der bisherige Energy-Filter in [sensor_mapping.py](eedc/backend/api/routes/sensor_mapping.py) ließ nur Sensoren mit `state_class in ["measurement", "total_increasing", "total"] and not unit` durch, also genau das umgekehrte Profil. Drei Verbesserungen: **(1) Filter aufgeweicht:** `state_class in ["total_increasing", "total"]` jetzt **immer** erlaubt (Unit egal — kumulativer Counter ist per Definition Mapping-Kandidat) plus neuer Pfad „ganzzahliger State ohne jegliche Metadaten" für Roh-Counter wie die Nibe-Integration. **(2) Frontend-Fallback im Wizard:** kleiner Link „Sensor nicht in der Auswahl? Alle Sensoren ohne Filter anzeigen" über dem Step-Content lädt on-demand mit `filter_energy=false` nach und merged in die bestehende Liste — wer den gesuchten Sensor weiterhin nicht findet, sieht jetzt alle `sensor.*`-Entities. **(3) Hilfetext im WP-Step:** Hinweis auf den Fallback-Link plus `customize.yaml`-Plan-B (`state_class: total_increasing` für Nibe-Roh-Counter setzen) als manueller Workaround ohne EEDC-Update.

- **fix(sensor-zuordnung + daten-checker): Sichtbarkeit für Sensoren ohne HA-Long-Term-Statistics** — Folge des aufgeweichten Filters: ab v3.24.1 können auch Sensoren ohne `state_class` ins Mapping aufgenommen werden — die fehlen aber in HA's `statistics_meta`-Tabelle und liefern damit für **kWh-Felder** (Monatswerte, Vollbackfill) still keine Daten. Counter-Felder (z.B. WP-Kompressor-Starts) sind davon nicht betroffen, weil sie über den Snapshot-Service laufen. Drei Maßnahmen, die das Problem an einer Stelle sichtbar machen statt überall im Code zu prüfen: **(1) Backend-Schema:** [`HASensorInfo`](eedc/backend/api/routes/sensor_mapping.py) trägt jetzt das Feld `has_statistics: bool` (= `state_class is not None`). **(2) Wizard-Dropdown:** kleines amber-farbiges Badge „ohne Statistik" neben dem Sensor-Namen — sowohl in der Suchergebnis-Liste als auch in der „bereits gewählt"-Anzeige. Tooltip erklärt: für kWh-Felder ungeeignet, für Counter unproblematisch. **(3) Daten-Checker-Kategorie „Sensor-Mapping – HA-Statistics":** prüft beim regulären Daten-Check pro Anlage, ob die im Mapping verwendeten kWh-Sensoren tatsächlich in HA-LTS landen. **WARNING** wenn ein kWh-Feld auf einen LTS-losen Sensor zeigt (still kritisch — Monatsabschluss bleibt leer), **INFO** wenn ein Counter-Feld auf einen LTS-losen Sensor zeigt (erwartetes Verhalten — Snapshot-Pfad), **OK** wenn alle kWh-Sensoren in LTS verfügbar sind. Live-Mappings (`leistung_w`, `soc`) werden nicht geprüft — sie lesen `state` direkt und brauchen kein LTS. Damit sind alle Stellen im Code, an denen LTS-Verfügbarkeit relevant ist, **drei** (Schema, Wizard-Anzeige, Daten-Checker) — kein „überall in jedem Lese-Pfad prüfen".

---

## [3.24.0] - 2026-04-27

### Neue Features

- **feat(energieprofil): WP-Kompressor-Starts als Stunden-/Tages-/Monats-KPI (#136)** — Optionaler kumulativer Anzahl-Zähler für Wärmepumpen-Kompressor-Starts. Im Sensor-Zuordnungs-Wizard kann pro WP-Investition ein Total-Increasing-Sensor angegeben werden (bei Nibe z.B. aus der lokalen „Nibe Heat Pump"-Integration: `sensor.compressor_number_of_starts_…`); der stündliche Snapshot-Job erfasst den Counter wie kWh-Zähler in `sensor_snapshots`, der Tagesabschluss berechnet (a) Stunden-Summen pro Stunde in `TagesEnergieProfil.wp_starts_anzahl` (Summe aller WP-Investitionen) und (b) Tages-Differenzen pro Investition in `TagesZusammenfassung.komponenten_starts` (`{"wp_starts_anzahl": {"<inv_id>": <int>}}`). Vollbackfill aus HA Long-Term Statistics greift für Tages-Summen mit (Counter-Werte werden vom HA-Statistics-Pfad nicht durch 1000 geteilt — Faktor bleibt bei unbekannter Einheit `1.0`); Stunden-Detail wird ab Live-Erfassung gefüllt, historische Tage haben dort `null`. **Anzeige-Stellen unter „Auswertung → Energieprofil":** (1) **Tab Tagesdetail** — neue Spalte „WP-Starts" in der Verbrauchs-Gruppe (default ausgeblendet, im Spalten-Selektor aktivierbar), Stundenwerte + Tagessumme im Footer. (2) **Tab Monat** — neue Gruppe „Komponenten" mit Spalte „WP-Starts" (default ausgeblendet), Tageswerte je Zeile + Monatssumme im Footer. Zusätzlich im Sensor-Zuordnungs-Wizard im WP-Step: neuer optionaler Eintrag mit Hinweis auf die Nibe-Integration. **Bewusst nicht gebaut:** Fallback-Heuristik aus `leistung_w`/Compressor-Binary wäre gerade bei kurzen Takten (wo der KPI sticht) systematisch unterzählen, kein Backfill möglich, Defrost-Verfälschung. Architektur trennt Counter-Felder strikt von kWh-Feldern in `KUMULATIVE_COUNTER_FELDER`, damit reine Counter nicht versehentlich in die Energie-Bilanz fließen. Issue #136.

---

## [3.23.8] - 2026-04-27

### Verbesserungen

- **fix(daten-checker): MQTT-Topic-Abdeckung präziser + nicht mehr für MQTT-Verweigerer (Forum #404/#405 detLAN/rapahl)** — detLAN sah im Daten-Checker eine Warnung „MQTT-Topic erwartet, nie empfangen" mit Beheben-Link auf MQTT-Inbound, obwohl er die Funktion gar nicht nutzen wollte. Ursache: in seinen DB-Settings war MQTT-Inbound aktiviert (Toggle aus dem Wizard), der Subscriber lief, aber keine HA-Publisher-Automation lieferte Topics. Die Warnung war technisch korrekt, im Wording aber unklar — sie listete keine Lösung außer „Publisher einrichten". Zwei Verbesserungen: (1) **Kategorie wird stillschweigend übersprungen**, wenn weder Subscriber läuft noch das DB-Setting `mqtt_inbound.enabled` gesetzt ist — wer MQTT-Inbound nie eingeschaltet hat, sieht die Kategorie gar nicht erst. Bei aktivem DB-Setting aber nicht laufendem Subscriber bleibt eine INFO-Meldung mit Diagnose-Hinweisen (Broker-Adresse / Zugangsdaten / Deaktivierung). (2) **WARNING-Meldungen** weisen jetzt explizit auf den **Deaktivierungs-Pfad** hin („Wenn du keine Live-Daten via MQTT brauchst, kannst du MQTT-Inbound unter Daten → Einrichtung → MQTT-Inbound deaktivieren") — rapahls Tipp aus #405 ist damit Teil der Fehlermeldung selbst.

- **fix(prognosen-tab): Mobile-Hinweis statt überlappende Tabellen (#165 Safi105)** — Safi105 zeigte per iPhone-Screenshot, dass die drei datendichten Tabellen im Prognosen-Tab (KPI-Matrix Heute/Morgen/Übermorgen, 7-Tage-Vergleich, Genauigkeits-Tracking) im Hochformat optisch zusammenbrechen: Header verschmelzen zu „SolcastIST", Werte und Delta-Annotationen wie „77.3 (0.2 79) kWh" überlappen, VM/NM-Aufteilungen werden zerrissen. Der parallele Stundenvergleich-Tab funktioniert dort, weil er kürzere Spalten-Header nutzt — der v3.23.2-Refactor zur Spalten-Konsistenz hatte die Reihenfolge vereinheitlicht, das Header-Wording aber nicht. Der Prognosen-Tab ist als Solcast-Evaluierungsfläche nicht auf langen Bestand ausgelegt — daher pragmatische Lösung statt Layout-Refactor: ab dem `sm`-Breakpoint (640 px) werden die drei Tabellen wie bisher gezeigt, darunter eine Hinweis-Box mit zwei Wordings — im Hochformat „Datendichte Tabelle — bitte Gerät ins Querformat drehen oder Desktop verwenden", im Querformat „Auflösung zu gering für datendichte Anzeige — bitte Desktop verwenden". Stundenvergleich-Tabelle bleibt unverändert sichtbar, ebenso der Ertrags-Chart und MAE/Bias-KPIs darüber. Konsistent mit der „Empfohlene Nutzung"-Linie aus v3.23.7-README.

- **fix(ha-statistics): Monatswert nutzt sum-Spalte statt state-Differenz — Tagesreset-Zähler korrekt aggregieren (Discussion #131 rcmcronny)** — Ronnys „Aktueller Monat bleibt bei 60 kWh fest"-Bericht: bei Sensoren mit Tagesreset (Zähler springt täglich um 0:00 auf 0) lieferte `MAX(state) - MIN(state)` über den Monat fälschlich die **größte Tagessumme** statt der Monatssumme — MIN ≈ 0 (jeden Tag erneut), MAX = bester Tag im Monat, Differenz wächst nach dem Spitzentag nicht weiter. In [ha_statistics_service.py](eedc/backend/services/ha_statistics_service.py) jetzt **`MAX(sum) - MIN(sum)`** als primärer Pfad: HA's `sum`-Spalte ist die reset-bereinigte Kumulation für total_increasing-Sensoren (genau das, was HA's eigenes Energy-Dashboard intern nutzt — funktioniert auch bei Tagesreset und Mehrfach-Resets). Fallback auf `state`-Differenz bleibt für measurement-Sensoren ohne `has_sum`.

- **fix(energiefluss): Sunset/Alps-Effekt-Layer auf abgerundete Ecken clippen (#164 reopened, detLAN)** — Folgefehler des v3.23.7-Eckenfixes: bei aktivierten Effekten zeichneten die Sunset-Animations-Layer (Sonnenstrahlen, Sky-/Reflektions-Partikel, Halo-Ringe) und die Alps-Animations-Layer (Wolken, Schneefunkeln, Sterne) ohne `clipPath` über die abgerundeten Ecken hinaus — sichtbar als kleine Pixel-Reste an den oberen Ecken bei Sunset. Die statischen Hintergrund-Rects waren in v3.23.7 schon auf `clipPath="url(#ef-photo-clip)"` umgestellt, die Animations-Blöcke nicht. Jetzt in [EnergieFlussBackground.tsx](eedc/frontend/src/components/live/EnergieFlussBackground.tsx) beide Animations-Blöcke in eine `<g clipPath="url(#ef-photo-clip)">`-Gruppe gewickelt — das `rx="8"`-clipPath gilt rekursiv für alle Kinder. Issue #164.

- **fix(live-dashboard): Temperatur-Cards mit Inline-Beschriftung (#166 detLAN, reduzierter Scope)** — detLAN bemängelte zwei Punkte am Energiefluss-Tile: (1) den separaten Ladezustand rechts (sei doppelt zum Energiefluss) und (2) die fehlende Temperatur-Überschrift bei den Außen-/Warmwasser-Cards. Zu (1): **Ladezustand bleibt** — das Tile-Component wird auch für E-Auto verwendet, dort ist die SOC-Anzeige explizite Benutzer-Anforderung; eine Entfernung würde das Component aufspalten oder konditional rendern. Zu (2): **keine separate Überschrift** (würde eine Zeile vertikal kosten — relevant bei gestapelten Tiles auf dichten Energie-Dashboards), stattdessen die kleinen Card-Labels von „Außen" und „Warmwasser" auf **„Außen Temperatur"** und **„Warmwasser Temperatur"** erweitert. Selbsterklärend und ohne zusätzliche Höhe. Issue #166.

- **fix(setup-wizard + sensor-zuordnung): Wizard-Daten landen wieder im Investment + COP→JAZ-Drift + Icon-Konsistenz + Scroll-to-Top (#167 detLAN)** — Vier Punkte aus detLANs Neueinrichtungs-Test gebündelt:
  - **(1) Wizard ↔ InvestitionForm Key-Drift behoben:** Der Setup-Wizard schrieb fünf Parameter unter falschen Keys, sodass die eigentliche InvestitionForm sie nicht fand und das frisch angelegte Investment „leer" wirkte. Korrigiert in [InvestitionenStep.tsx](eedc/frontend/src/components/setup-wizard/steps/InvestitionenStep.tsx): E-Auto-Batteriekapazität (`batterie_kwh` → `batteriekapazitaet_kwh`), E-Auto-V2H-Toggle (`v2h` → `v2h_faehig`), Wechselrichter-Maximalleistung (`leistung_kw` → `max_leistung_kw`), Speicher-Arbitrage (`arbitrage` → `arbitrage_faehig`), Wallbox-Ladeleistung (`leistung_kw` → `max_ladeleistung_kw`) und Wallbox-Bidirektional (`v2h` → `bidirektional`). detLAN hatte drei davon konkret gemeldet, die übrigen sind dasselbe Bug-Muster und wurden im selben Sweep mitgenommen.
  - **(2) COP/JAZ-Drift in Wizard und Sensor-Zuordnung:** Der v3.23.4-Sweep hatte vier Render-Stellen auf JAZ harmonisiert, Setup-Wizard und WP-Sensor-Zuordnung waren nicht in der Liste. Im Wizard heißt das WP-Eingabefeld jetzt „Jahresarbeitszahl (JAZ)" und schreibt unter Key `jaz` plus implizitem `effizienz_modus: 'gesamt_jaz'` (das ist semantisch das, was hier erfasst wird — eine Jahresarbeitszahl, nicht ein Betriebspunkt-COP). In [WaermepumpeStep.tsx](eedc/frontend/src/components/sensor-mapping/WaermepumpeStep.tsx) wurde der Card-Untertitel von „JAZ/COP: 3.5" auf „JAZ: 3.5" gekürzt, der Hinweis-Block-Titel von „COP-Berechnung" auf „JAZ-basierte Berechnung" und die Strategie-Labels von „COP-Berechnung" auf „JAZ-Berechnung" umgestellt. **Bewusst nicht angefasst:** mathematisch-technische Berechnungs-Variablennamen (z.B. `cop_default`, `cop_berechnung`-Strategy-Wert für API-Kompatibilität) — dort ist „COP" das mathematisch korrekte Wort.
  - **(3) Gelbes Icon-Inkonsistenz behoben:** Beim WP-Block in der Sensor-Zuordnung saß das gelbe Zap-Icon bei „Stromverbrauch (kWh)" links **außerhalb** der Card, während „Heizenergie (kWh)" und „Warmwasser (kWh)" gar kein Icon hatten. Der externe Icon-Wrapper bei Stromverbrauch wurde entfernt — alle drei Felder rendern jetzt einheitlich als `FeldMappingInput` ohne externes Icon-Kästchen.
  - **(4) Scroll-to-Top im Sensor-Mapping-Wizard (#154-Folgefehler):** Die grünen Submit-/Step-Schaltflächen im Sensor-Mapping-Wizard ändern nur den lokalen `currentStep`-State (kein Route-Wechsel), daher griff der zentrale Layout.tsx-Scroll-Reset aus v3.23.6 nicht. Lokales `useEffect` auf `currentStep` in [SensorMappingWizard.tsx](eedc/frontend/src/pages/SensorMappingWizard.tsx) ergänzt — scrollt den `<main>`-Container bei jedem Step-Wechsel an den Anfang.

---

## [3.23.7] - 2026-04-27

### Neue Features

- **feat(daten-checker): neue Kategorie MQTT-Topic-Abdeckung (#134)** — Schließt die Drift-Lücke zwischen dynamischer Konsumenten-Seite (Erwartungsliste aus [`field_definitions.py`](eedc/backend/core/field_definitions.py)) und statisch hartkodierter Publisher-Seite (HA-Automation-YAML / iobroker / Node-RED): Sobald in EEDC neue Felder dazukommen oder Investitions-IDs nach Re-Import wechseln, driftet Publisher gegen Konsument unbemerkt — diese Daten-Checker-Kategorie macht das sofort sichtbar. Drei Befunde pro Anlage: **(WARNING) Topic erwartet, nie empfangen** mit Beispielen in den Details (typische Ursachen: Publisher-Automation noch nicht eingerichtet, Investitions-IDs nach Re-Import in der Automation nicht nachgezogen), **(WARNING) Topic empfangen, Wert älter als Schwellwert** (live ≤ 2 min, energy ≤ 10 min — passt zum sensorgetriebenen Live-Update- und 5-Minuten-Energy-Pattern), **(OK) Alle erwarteten Topics aktuell empfangen**. Bei nicht-aktivem MQTT-Inbound-Subscriber wird die Kategorie als INFO neutral gemeldet (kein Alarm). Pre-work: Topic-Erwartungsliste aus [`live_mqtt_inbound.py`](eedc/backend/api/routes/live_mqtt_inbound.py) in eigenen Helfer [`mqtt_topic_registry.build_expected_topics()`](eedc/backend/services/mqtt_topic_registry.py) extrahiert — Endpoint `/api/live/mqtt/topics` und der Daten-Checker nutzen jetzt denselben Helfer (eine Quelle, ein Bedeutungsraum für „erwartete Topics"). Issue #134.

### Bugfixes

- **fix(energiefluss): Sunset/Alps-Hintergründe mit Border-Radius clippen (#164 detLAN)** — detLAN-Beobachtung beim iPhone-Anzeigezoom-Sweep: bei den Hintergrund-Varianten Sunset und Alps (sowie wahrgenommen bei Alben-Foto-Hintergrund) sind die Ecken nicht abgerundet, im Gegensatz zu den anderen Varianten. Ursache in [`EnergieFlussBackground.tsx`](eedc/frontend/src/components/live/EnergieFlussBackground.tsx): die Himmel/Meer- bzw. Himmel/Tal-Rects der Sunset- und Alps-Varianten zogen ohne `clipPath` bis in die Ecken des SVG und überzeichneten damit die abgerundeten Container-Ecken — Foto-Hintergründe nutzen schon `clipPath="ef-photo-clip"`. Jetzt `clipPath` konsistent auf allen vier Sunset- und vier Alps-Hintergrund-Rects, Ecken sind in allen Varianten gleich abgerundet. Die übrigen Punkte aus #164 (Werte rechts ausbrechend, „Prognose"-Umbruch, Diagramm-Breiten) sind Effekte des aktivierten iOS-Anzeigezooms „Größerer Text" bzw. der HA-Companion-Seitenzoom-Stufe — siehe „Empfohlene Nutzung" im README. Issue #164.

### Dokumentation

- **docs(readme): „Empfohlene Nutzung"-Block** — Im Root- und Standalone-README dokumentiert, dass eedc als datendichte Analyse-App primär für Desktop konzipiert ist. Smartphone in Standard-Anzeigegröße deckt Live-Dashboard und einfache Sichten ab, datendichte Auswertungs-Bereiche profitieren von größerem Bildschirm. Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom) können einzelne Layouts eng werden — bewusste Designentscheidung statt Layout-by-Layout-Patches, die den datendichten Charakter aufweichen würden. Wording als technische App-Eigenschaft formuliert (keine Aussagen zu Barrierefreiheit / Accessibility).

---

## [3.23.6] - 2026-04-26

### Bugfixes

- **fix(layout): h-screen → h-dvh gegen leeren Bereich unter Footer auf iOS (#161 detLAN)** — detLAN meldete bei iPhone mit Anzeigezoom „Größerer Text" (und analog HA-Companion-App mit erhöhtem Seitenzoom): in den Monatsberichten ans Ende scrollen, neu absetzen und weiterziehen — und es geht *noch weiter*, der Footer sitzt mitten im Viewport mit leerem Raum darunter. Ursache: Layout-Wrapper [Layout.tsx](eedc/frontend/src/components/layout/Layout.tsx) nutzt `h-screen` (= `100vh`); auf iOS Safari / WKWebView ist `100vh` statisch das Viewport ohne UI-Chrome (Adressleiste, Tab-Bar). Mit eingeklappter Adressleiste oder Anzeigezoom wird das echte Viewport größer als `100vh` — der äußere Container füllt es nicht aus, das innere `<main>` mit `flex-1 overflow-auto` lässt sich nach dem ersten Scroll-Anschlag im Overscroll noch ein Stück weiter ziehen. Fix: `h-screen` → **`h-dvh`** (dynamic viewport height, von Tailwind 3.4+ unterstützt). `dvh` reagiert dynamisch auf Adressleisten-Animationen und füllt das echte sichtbare Viewport. Eine-Zeilen-Änderung. Issue #161.

- **fix(layout): Einstellungs-Dropdown scrollbar + SimpleTooltip Viewport-Clamp (#158 detLAN)** — Zwei kleine UX-Bugs aus detLAN's Mobile/Smartfenster-Re-Test. (1) Bei kurzem Browser-Fenster lief das Desktop-Einstellungs-Dropdown unten aus dem Viewport — der letzte Eintrag „Sensor-Zuordnung" war nicht erreichbar. Der äquivalente Container im Mobile-Panel hatte `max-h-[calc(100vh-3.5rem)] overflow-y-auto`, das Desktop-Dropdown nicht. Jetzt analog ergänzt in [`TopNavigation.tsx`](eedc/frontend/src/components/layout/TopNavigation.tsx). (2) Tooltips aus `SimpleTooltip` (z. B. „Strom der aus dem Netz bezogen wird (nicht durch PV gedeckt)" auf der Live-Dashboard-Netzbezug-Kachel) wurden bei langem Text und Trigger nahe am rechten Rand abgeschnitten — die Kombination `whitespace-nowrap` + `transform: translateX(-50%)` erzeugte einen einzeiligen Streifen, der über den Viewport-Rand hinausragte. Jetzt in [`FormelTooltip.tsx`](eedc/frontend/src/components/ui/FormelTooltip.tsx): `max-w-xs whitespace-normal break-words` (mehrzeilig, max ~320 px) plus Edge-Clamp auf `coords.left` damit die Tooltip-Box auch bei Trigger nahe Viewport-Rand vollständig sichtbar bleibt. Issue #158.

- **fix(wetter-widget): Stunden-Aggregation IST von „last" auf „mean" (Rainer-PN)** — Rainer-PN-Idee zum Versatz im „Wetter heute"-Chart: aus Apex-Charts kennt er Kurven-Versatz durch Aggregations-Methode (`group_by`/`statistics` mit `avg`/`last`/`first`). Bei uns trifft das zu, in kleiner Form: das Frontend hat im Live-Heute-Chart pro Stunde den **letzten** 10-Min-Slot übernommen (`result[h] = ...` mehrfach überschrieben → `last`), Open-Meteo dagegen liefert das Stunden-**Mittel**. Effekt: ~25 Min systematischer Versatz zwischen IST und Prognose im selben Stundenfach. Jetzt in [`WetterWidget.tsx`](eedc/frontend/src/components/live/WetterWidget.tsx): Akkumulator pro Stunde + Mittelwert über alle vorhandenen 10-Min-Slots. Konsistent mit der Mean-Konvention der Prognose-Linien. Den anlagenspezifischen 1-Stunden-Versatz, den Rainer beobachtet, erklärt das nicht — der kommt aus dem Stundenprofil seiner Anlage und gehört zum Korrekturprofil-Konzept (siehe [`docs/KONZEPT-KORREKTURPROFIL.md`](docs/KONZEPT-KORREKTURPROFIL.md)).

- **fix(layout): globaler Scroll-to-Top bei jedem Route-Wechsel (#154 reopened, detLAN)** — detLAN-Re-Test nach v3.23.5: das Scroll-Problem aus #154 existiert noch unter „Daten" beim Wechsel auf den Tab „Einrichtung" (und implizit überall wo SubTabs route-basiert wechseln — Stammdaten, HA, System). Der v3.23.4-Fix saß nur in `Auswertung.tsx` mit lokalem `activeTab`-State; bei `NavLink`-Wechseln im Layout greift das nicht. Jetzt zentral in [`Layout.tsx`](eedc/frontend/src/components/layout/Layout.tsx): `useEffect` auf `useLocation().pathname` scrollt den `<main>`-Container per Ref bei jedem Routenwechsel an den Anfang. Damit konsistent für **alle** SubTab-Gruppen.

---

## [3.23.5] - 2026-04-26

### Bugfixes

- **fix(live-heute): EV-Quote auf 100 % begrenzt + Bilanz-Sortierung (#157 detLAN)** — detLAN-Beobachtung: „Wie kann man 195 % Eigenverbr. haben? Meiner Meinung nach kann man maximal 100 % haben." Sachstand: die 195 % sind mathematisch korrekt (Eigenverbrauch enthält seit [#47/b1519cb3](https://github.com/supernova1963/eedc-homeassistant/commit/b1519cb3) auch Batterieentladung — bei niedriger heutiger PV und Bat-Entladung aus Vortagen kann ev/pv > 100 % rechnen), aber visuell unsinnig. Genau dieses Phänomen war an Periodenwerten schon mit Commit [`588a8b07`](https://github.com/supernova1963/eedc-homeassistant/commit/588a8b07) (25.3.2026) an sieben Backend-Stellen mit `min(…, 100)` gecappt — der Live-Frontend-Pfad rechnet die Quote allerdings lokal in JS und ist beim 7-Dateien-Patch durchs Raster gefallen. Jetzt nachgezogen: `Math.min((ev / pv) * 100, 100)` in [`LiveDashboard.tsx`](eedc/frontend/src/pages/LiveDashboard.tsx). Plus zwei Folge-Punkte aus #157: (1) Wording-Konsistenz „Eigenverbr." → **„Eigenverbrauch"** ausgeschrieben (passt mit dem 100 %-Cap auch in die Pille), (2) Bilanz-Sortierung der Tageswerte-Kacheln nach detLAN's Energie-Logik **PV → Batterie → Eigenverbrauch (Quellen-Σ) → Netzbezug → Hausverbrauch (Verbrauchs-Σ) → Einspeisung (PV-Überschuss)**. Issue #157.

---

## [3.23.4] - 2026-04-26

### Verbesserungen

- **refactor(komponenten-style): Wärmepumpe-KPIs in 4 Sichten harmonisiert + Speicher-Effizienz vereinheitlicht (#155 reopened, detLAN)** — detLAN's Re-Test nach v3.23.1: Werte stimmen, aber Icons, Farben, Reihenfolge und Wording der Wärmepumpe-KPIs driften zwischen Cockpit-Übersicht, WP-Dashboard, Auswertung→Komponenten und Monatsabschluss noch deutlich auseinander. detLAN's Bonus-Vorschlag (zentrale Style-Konstanten) übernommen: neues [`lib/komponentenStyle.ts`](eedc/frontend/src/lib/komponentenStyle.ts) mit `WP_KPI` (jaz/waerme/strom/ersparnis: Thermometer-orange / Flame-red / Zap-yellow / TrendingUp-green) und Helper `fmtKpi(value, decimals)` der bei `null`/`undefined`/NaN konsistent `'---'` zurückgibt — Auswertung→Komponenten ist die Referenz, dort waren Reihenfolge und Style schon richtig. Vier Render-Stellen umgestellt: (1) [Cockpit-Übersicht WP-Tile](eedc/frontend/src/pages/Dashboard.tsx) auf JAZ-Wärme-Strom-Ersparnis (vorher Wärme-Strom-JAZ-Ersparnis, Strom-Tile war zudem violett-Zap statt yellow-Zap), (2) [WP-Dashboard](eedc/frontend/src/pages/WaermepumpeDashboard.tsx) Header-Tile von „JAZ (gesamt)" auf „JAZ", Monatsvergleichs-Toggle und Detail-Tabellen-Spalte von „COP" auf „JAZ" (detLAN's „zweimal COP statt JAZ"), JAZ-Heizen / JAZ-Warmwasser auf einheitliches Thermometer-orange (vorher blue/purple), (3) [Monatsabschluss WP-Sektion](eedc/frontend/src/pages/MonatsabschlussView.tsx) auf JAZ-Wärme-Strom-Ersparnis mit Thermometer/Flame/Zap/TrendingUp (vorher Stromverbrauch-Wärmeertrag-COP-Ersparnis mit Zap/Flame/Gauge/Euro), Section-Summary-Badge auf „JAZ X.XX" statt „COP X.XX". Bonus aus detLAN's Hinweis „Speicher-Effizienz an mehreren Stellen uneinheitlich": die Speicher-Effizienz-KPI nutzt jetzt durchgängig **Activity-Icon + cyan** (vorher Battery-cyan in Auswertung→Komponenten, Activity-green im Speicher-Dashboard, Gauge-teal in der Cockpit-Übersicht, Gauge-green im Monatsabschluss). Fehlende Werte (`null` / 0 / NaN) zeigen einheitlich `---` statt „0" oder „—". Issue #155.

- **refactor(cockpit): Cockpit-Tabs harmonisiert nach PV-Vorlage (#156 reopened, detLAN)** — detLAN's Korrektur zu v3.23.1: (1) der Tab-Titel sollte bei tatsächlichen Investments (Wärmepumpe / Speicher / Wallbox / E-Auto / Balkonkraftwerk / Sonstiges) nicht der Anlagenname sein, sondern die `bezeichnung` des konkreten Investments — bei mehreren Investments derselben Art entsteht so automatisch eine Abgrenzung über die jeweiligen Block-Header. PV-Anlage bleibt mit Anlagennamen (kein direktes Investment). (2) Card-Layout vereinheitlicht: die einzelnen Investment-Blöcke werden nicht mehr in eine eigene Card-Box gepackt — bei einem einzigen Investment fällt der Box-Wrapper weg, bei mehreren trennt jetzt eine durchgezogene Linie statt einer Card-Border (analog zur Komponenten-Liste in der Auswertung). (3) Cockpit-Tab-Reihenfolge auf detLAN's Vorschlag umsortiert: Übersicht → Monatsberichte → PV-Anlage → Balkonkraftwerk → Speicher → Wärmepumpe → Wallbox → E-Auto → Sonstiges (Erzeuger oben, Speicher in der Mitte, Verbraucher unten, „Sonstiges" am Ende). Issue #156.

- **build(lint): ESLint-Setup für Frontend nachgereicht + 50 Errors aufgeräumt** — `npm run lint` war seit Projektbeginn als npm-Skript hinterlegt, die zugehörige Konfiguration und der TS-Parser fehlten aber, sodass der Befehl nie lief. Jetzt: `.eslintrc.cjs` mit der Standard-Vite-React-TS-Konfiguration (`eslint:recommended` + `@typescript-eslint/recommended` + `react-hooks` + `react-refresh`) und `@typescript-eslint/parser` / `@typescript-eslint/eslint-plugin` v7 als devDependencies. Beim ersten Lauf 50 Errors aufgedeckt — alle gefixt: ~20× `no-explicit-any` (catch-Parameter auf `instanceof Error`-Pattern, drei interne Tooltip-Props strikt typisiert, ein veralteter `(anlage as any)`-Cast in `AnlageForm` entfernt nachdem `wetter_provider` schon im Anlage-Type war), ~20× `react-hooks/rules-of-hooks` (Hook-Aufrufe nach Early-Returns in `EnergieFluss`, `auswertung/FinanzenTab` und allen fünf `community/KomponentenTab`-Deep-Dives — Hooks vor das `return null` gezogen, Hook-Bodies um defensive Null-Checks ergänzt), drei `no-empty` (`} catch {}`-Stellen in `MonatsabschlussView` mit Begründungs-Kommentar), zwei `no-case-declarations` (`switch`-cases in `InvestitionForm` und `HAStatistikImport` in Block-Scopes gewickelt), drei `no-unused-vars` (durch `argsIgnorePattern: '^_'` als bewusst-unused erkannt). `--max-warnings 0` aus dem Skript entfernt: 22 verbleibende Warnings (`exhaustive-deps` + `react-refresh/only-export-components`) sind bekannt-tolerable Style-Hinweise und werden als separate Cleanup-Aufgabe geführt.

### Bugfixes

- **fix(auswertung): Tab-Wechsel scrollt zuverlässig zum Seitenanfang (#154 detLAN, dritter Anlauf)** — detLAN-Re-Test: Tabs „CO2" und „Tabelle" übernahmen die Scroll-Position der vorherigen Tab, andere Tabs scrollten korrekt nach oben. Ursache: bisheriges `scrollTo` lief im `onClick`-Handler **vor** dem React-Re-Render und mit `behavior:'smooth'` — bei Tabs mit langem Inhalt wurde die Animation durch das Re-Render unterbrochen oder gekappt. Lösung: `useEffect` auf `activeTab`-Änderung mit `behavior:'auto'` — scrollt **nach** dem Re-Render hart auf 0, ohne Smooth-Animation. Entspricht dem Cockpit-Pattern (jeder Sub-Tab beginnt am Seitenanfang) und detLAN's explizit formuliertem Wunsch.

### Internal

- **internal: Day-Ahead-Stundenprofil-Snapshot in `TagesZusammenfassung`** — Zwei neue JSON-Felder (`pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil`) speichern den ersten OpenMeteo-/Solcast-Forecast des Tages als 24-Werte-Liste in kWh (Backward-Slot-Konvention). First-write-wins: spätere Aufrufe am selben Tag überschreiben das Profil nicht, der Day-Ahead-Charakter bleibt erhalten. Schreiben passiert fire-and-forget aus dem bestehenden Live-Wetter-Endpoint, kein neuer Scheduler-Job, kein UI, kein API-Endpunkt — reine Hintergrund-Datensammlung für künftige Diagnostik (siehe [`docs/KONZEPT-KORREKTURPROFIL.md`](docs/KONZEPT-KORREKTURPROFIL.md)). Storage ~80 KB/Jahr/Anlage.

---

## [3.23.3] - 2026-04-26

### Neue Features

- **feat(prognose): Diagnostisch-Modus für Genauigkeits-Tracking — Asymmetrie sichtbar machen (#151 Variante B, Rainer-Mockup)** — Der MAE/MBE-Modus aus v3.22.0 zeigt Streuung und Bias kompakt, verbirgt aber, ob die Streuung symmetrisch ist (Rauschen ohne Hebel) oder asymmetrisch (z. B. „bei dichten Wolken systematisch zu hoch, bei klarem Himmel zu niedrig" — Lernfaktor lässt sich nur einseitig nutzen). Neuer Toggle **„Kompakt / Diagnostisch"** im Header der Genauigkeits-Tracking-Card schaltet zwischen den zwei Sichten um. Im Diagnostisch-Modus zeigt jede Quelle (OpenMeteo / EEDC / Solcast) zwei Boxen nebeneinander: **darüber** = Tage an denen die Prognose über dem IST lag (Ø-Überschätzung in % + Anzahl Tage, amber) und **darunter** analog für Unterschätzung (sky-blau). Dahinter neues Backend-Schema `AsymmetrieEintrag` (`over_count`, `over_avg_prozent`, `under_count`, `under_avg_prozent`) das die signed errors an 0 splittet — `GET /aussichten/prognosen/{id}/genauigkeit` liefert jetzt zusätzlich `openmeteo_asymmetrie` / `eedc_asymmetrie` / `solcast_asymmetrie`. Default bleibt kompakt; das Asymmetrie-Detail ist optional und stört den Standard-Workflow nicht.

---

## [3.23.2] - 2026-04-26

### Bugfixes

- **fix(downloads): Backup/CSV/PDF-Downloads über Blob-Pattern statt `window.open` (Joachim-PN)** — Joachim meldete „401: unauthorized" beim Tippen auf den Backup-Button in der iOS HA Companion-App. Ursache: `window.open(url, '_blank')` (in [`Backup.tsx`](eedc/frontend/src/pages/Backup.tsx)) öffnet `_blank`-Links extern in Safari — und Safari hat keine HA-Ingress-Session, daher 401 vom Ingress-Endpoint. Browser klappte das deshalb, App nicht. Fünf Stellen umgestellt auf zentrales `downloadFile(url, filename)` aus neuem [`lib/download.ts`](eedc/frontend/src/lib/download.ts) (fetch + Blob + temporärer `<a download>`): Backup-Button, JSON-Export-Icon in der Anlagen-Liste, CSV-Template + CSV-Export im Import-Dialog, alle vier PDF-Dokumente im Dokumente-Dialog (lokale Helper-Duplikate konsolidiert). Damit läuft die HTTP-Anfrage in der bestehenden iframe-Session und der Download geht als blob:-URL ins Filesystem — funktioniert in der HA-App + Browser gleichermaßen.

- **fix(prognosen-tabelle): „Laufbalken" entfernt + Spalten konsistent ausgerichtet (Rainer-PN, Detlef-PN)** — Rainer meldete einen sichtbaren Vertikal-Balken am rechten Rand der 24h-Stundenvergleichstabelle nach „Tag neu berechnen". Es war die Browser-Scrollbar des Tabellen-Containers — `max-h-96` (384px) plus die Stunden-Anzahl in den Übergangs-Monaten ließen die Tabelle um wenige Pixel überlaufen → Scrollbar erschien, obwohl optisch alles reinpasste. Höhen-Constraint + sticky-thead/tfoot entfernt. Im selben Zug die Spaltenstruktur **aller vier Tabellen** auf der Prognosen-Seite vereinheitlicht: KPI-Matrix (Heute/Morgen/Übermorgen), 24h-Stundenvergleich, 7-Tage-Vergleich und Genauigkeits-Tracking nutzen jetzt durchgängig **`table-fixed` + `<colgroup>`** mit konsistenten Title-Spalten und gleichmäßig verteilten Wertspalten. Im 7-Tage-Vergleich wurde die **Wetter-Spalte vor das Datum** verschoben (zweispaltiger Zeilentitel), im Genauigkeits-Tracking die **IST-Spalte ans Ende**. Damit stehen OpenMeteo / EEDC / Solcast / IST in allen vier Tabellen in derselben vertikalen Linie übereinander — die Seite scrollt sauber von oben nach unten ohne Auge-Zickzack.

---

## [3.23.1] - 2026-04-26

### Bugfixes

- **fix(cockpit-uebersicht): JAZ/Wärme/Strom ignorieren Daten vor Anschaffungsdatum (#155.1, Folgefix zu #153)** — detLAN-Beobachtung: „Die Wärmepumpe im Cockpit-Überblick haben wir übersehen." Der v3.23.0-Filter aus #153 wurde nur in `cockpit/komponenten.py` und im WP-Detail-Endpoint (`investitionen.py:/dashboard/waermepumpe`) eingebaut. Die Cockpit-Hauptseite („Übersicht") zog ihre WP-Aggregate aus `cockpit/uebersicht.py` — und summierte dort weiter alle vorhandenen `InvestitionMonatsdaten` ungefiltert. Dasselbe Problem in vier weiteren Endpunkten (`cockpit/social.py`, `cockpit/nachhaltigkeit.py`, `aktueller_monat.py`, `aussichten.py`) und in fünf Dashboards (E-Auto, Speicher, Wallbox, Balkonkraftwerk — der WP-Dashboard hatte den Filter bereits). Filter konsistent eingebaut: Monate vor `(anschaffung.year, anschaffung.month)` werden überall ignoriert. Greift für WP, Speicher, Wallbox/E-Auto und Balkonkraftwerk gleichermaßen; das löst auch #155.4-Beobachtung („Es wird erneut das Anlagendatum für den Zeitraum ausgewählt"), weil der Zeitraum jetzt aus dem gefilterten Datensatz hergeleitet wird.

- **fix(auswertung): Tab-Wechsel scrollt jetzt wirklich (#154 reopened)** — Der v3.23.0-Fix scrollte `window` per `window.scrollTo(...)`, das eigentlich scrollende Element ist aber das `<main>` mit `overflow-auto` aus dem App-Layout — `window.scrollTo` war damit ein No-Op. Korrigiert auf `document.querySelector('main')?.scrollTo({...})`.

- **fix(cockpit): Anlagenname als Titel statt redundanter Typ-Bezeichnung (#156)** — detLAN: „Die Art des Investments geht aus dem aktiven Tab hervor — eine Wiederholung als Titel ist nicht erforderlich." Der `<h1>` der vier Cockpit-Dashboards (PV-Anlage, Wärmepumpe, Speicher, Wallbox) zeigt jetzt `{anlage.anlagenname}` statt „PV-Anlage" / „Wärmepumpe" / „Speicher" / „Wallbox" — Investment-Art bleibt nur noch im aktiven grünen Tab sichtbar, der Card-Header bei mehreren Investments derselben Art trägt weiterhin `{investition.bezeichnung}` zur Unterscheidung.

- **fix(cockpit): Icon-Overflow bei schmalen Fenstergrößen (#155.4)** — In den vier Cockpit-Dashboards rutschten Header-Icon (Sun/Flame/Battery/Plug) und Card-Header-Icon (Flame/Battery/Plug) aus dem Container, sobald der Bezeichnungs-Text zu lang wurde. `flex-shrink-0` auf den Icons + `min-w-0` + `truncate` auf den Text-Containern halten das Layout stabil.

- **fix(navigation): Hamburger-Menü früher aktiv (md → lg, #155.1)** — detLAN-Screenshot zeigte bei 1539px die Hauptnavigation und das Settings-Dropdown im Konflikt. Breakpoint in `TopNavigation.tsx` von `md:` (768px) auf `lg:` (1024px) gehoben — Hamburger-Layout ist damit auf typischen Notebook-Viewports und kleineren Browser-Fenstern aktiv.

- **fix(cockpit): WP-Tile zeigt „JAZ" statt „Ø COP" (#155.3, #155.5)** — detLAN: Auswertung→Komponenten→WP nutzt für die Periode JAZ, das Cockpit-Hauptseiten-Tile zeigte demgegenüber „Ø COP". Cockpit-Tile auf „JAZ" + Formel-Beschriftung „JAZ = Wärme ÷ Strom" harmonisiert; pro-Monat-Werte (Tabelle, Vergleichs-Toggle) bleiben weiter als COP.

- **fix(monatsabschluss-wp): VM-Vergleich nur wenn Vormonat tatsächlich WP-Daten hat (#155.2)** — Bei einer WP, die im aktuellen Monat zum ersten Mal Daten hat, zeigte der Monatsabschluss alle vier KPI-Tiles („Stromverbrauch", „Wärmeertrag", „COP", „Ersparnis vs. Gas") mit „VM: 0 kWh" oder „VM: NaN kWh" — irreführend, weil der Vormonat keinen WP-Betrieb hatte. Single-Source-Guard `hatVmWp = (vm?.wp_strom_kwh ?? 0) > 0` unterdrückt jetzt sowohl die Subtitle-Zeilen als auch die `VglZeile`-Vergleichsspalten der WP-Sektion.

---

## [3.23.0] - 2026-04-25

### Neue Features

- **feat(prognose): Klickbarer Reparatur-Popover bei IST-Datenlücke (#147 fortlaufend)** — Wenn die Prognosen-IST-Anzeige eine Datenlücke hat (⚠ neben dem Tageswert), öffnet ein Klick auf das Symbol jetzt einen kompakten Popover statt des Hover-Tooltips. Inhalt: konkrete Auflistung der fehlenden Stunden, kurzer Erklärungstext (Snapshot-Zyklus, Sensor-Mapping), Button **„Tag neu berechnen"** (triggert `POST /api/energie-profil/{anlage_id}/reaggregate-tag` mit Refetch + Status-Banner) und Fallback-Link zum Sensor-Mapping. Layout am ⚠ rechtsbündig verankert (`right-0`) mit `max-w-[calc(100vw-2rem)]` — bricht nicht mehr aus dem Viewport.

- **feat(snapshot): Restart-Recovery für verpasste :05/:55-Jobs** — Wird das Add-on zwischen `:55` (Live-Snapshot-Preview) und `:05` (regulärer HA-Statistics-Snapshot) der Folgestunde neu gestartet, fehlten die Snapshots der laufenden und ggf. der gerade abgeschlossenen Stunde, weil die Cron-Trigger keine Misfire-Recovery hatten. Neue `sensor_snapshot_startup_recovery()` läuft nach Scheduler-Start im Hintergrund: holt für die letzten 6 Stunden je Anlage `snapshot_anlage` (HA-Statistics, idempotent dank Upsert) und für die laufende Stunde zusätzlich `live_snapshot_if_missing` (aus HA-Live-State); anschließend `aggregate_today_all` für sofortige Sichtbarkeit. Damit ist das Energieprofil nach Add-on-Restarts (Watchdog, Update) ohne Wartezeit wieder vollständig.

### Bugfixes

- **fix(prognose): IST-Slot der gerade abgeschlossenen Stunde nicht mehr als Lücke flaggen** — Slot N (= Backward-Slot-Konvention `[N-1, N)`) hängt von der HA-Hourly-Statistics-Row für `start_ts=N`, die HA aber erst am Ende der Stunde schreibt. Innerhalb des Zeitfensters zwischen Stundenwechsel und HA-Stats-Write (typisch ~5–60 Min) ist der Slot zwangsläufig `None`. Die `<=`-Bedingung in `prognosen.py:431` flaggte das fälschlich als „IST-Daten unvollständig". Geändert zu `<` — der gerade abgeschlossene Slot wird nicht mehr geflaggt; ältere echte Lücken (>1 h alt) weiter wie bisher.

- **fix(snapshot): Tagesreset-Heuristik für utility_meter mit daily cycle** — Forum-Beobachtung Rainer: HA-`utility_meter`-Sensoren mit täglichem Reset (z. B. „Erzeugung heute") werfen um Mitternacht ein stark negatives Delta (Vortag-Endwert → ~0). `get_hourly_kwh_by_category` hatte das pauschal als „Sensor-Reset" verworfen → Slot 0 dauerhaft `None` → `ist_unvollstaendig=True` jeden Tag. Heuristik in `sensor_snapshot_service.py:548-559` erkennt Daily-Reset-Muster (`s1 < 0.5 ∧ s0 > 0.5`) und nimmt `max(0, s1)` als Slot-0-Wert (Energie seit Reset, typ. ≈ 0 nachts). Bei untypischen negativen Deltas mitten am Tag bleibt die Reset-Warnung wie bisher.

- **fix(daten-checker): Falscher Beheben-Link bei „X Komponenten ohne kWh-Zähler"** — Joachim-PN: Klick auf „Beheben" in dieser Daten-Checker-Kategorie führte auf eine weiße Seite. Der Link verwies auf `/einstellungen/sensoren`; die Route heißt aber `/einstellungen/sensor-mapping`. In [`daten_checker.py`](eedc/backend/services/daten_checker.py) zwei Stellen korrigiert.

- **fix(live-dashboard): Wetter-Timeline-Alignment im Tagesverlauf-Chart (MartyBr)** — Hartcodiertes `paddingLeft: 40` in der Wetter-Timeline ignorierte die dynamische Recharts-`YAxis`-Breite. Bei größeren PV-Werten (>10 kW) wurde die YAxis breiter und die Wetter-Icons saßen nicht mehr exakt über den X-Tick-Stunden. Fix: `<YAxis width={45}>` setzt deterministische Breite, `margin.left=0` und `paddingLeft: 45` halten die Plot-Area konsistent über den Tag.

- **fix(card): Border-Radius-Clipping bei Tabellen-/Section-Headern (#149, #152)** — detLAN-Bündel: Auf vier Pages (Monatsabschluss-T-Konto Mobile, Monatsdaten-Tabelle, Anlagen-Liste, Strompreise-Liste) ragten farbige `<th>`-/Section-Bänder über die abgerundeten Card-Ecken hinaus, sodass die Rahmenlinie an den Ecken nicht sauber schloss. `overflow-hidden` auf der jeweiligen Card behebt das.

- **fix(legacy): `Anlage.ausrichtung` / `Anlage.neigung_grad` aus aktivem Code entfernt (#152)** — Die Spalte „Ausrichtung" in der Anlagen-Liste zeigte bei detLAN konsistent `-`, weil das Feld am Anlage-Modell seit dem Refactoring zu PV-Modul-Investitionen nicht mehr gepflegt wird. Geprüft: weder Berechnungen (Prognose, PVGIS, Solar-Forecast, PR), Community-Submit, Infothek noch JSON-Export greifen darauf zu. Spalte aus der Liste entfernt, Setup-Wizard-Lese-Stellen aufgeräumt, Pydantic-`AnlageExport`-Schema und TypeScript-`Anlage`-Interface bereinigt. **DB-Spalte bleibt erhalten** für Bestandsinstallationen (Pattern wie `ha_sensor_*`); Kommentar im Modell präzisiert.

- **fix(pv-cockpit): Modul-Anzahl zählt jetzt `parameter.anzahl_module` statt nur Investitions-Einträge (#152)** — Anzeige „1 WR, 1 Module" trotz 21 gepflegter Module in der PV-Modul-Investition. Subtitle berechnet jetzt `anzahl_module` pro Modul-Investition (Default 1 falls Parameter leer).

- **fix(anlage-form): Umlaute „fur"/„wunschen"/„Warmepumpe" (#152)** — In `AnlageForm` (Steuerlicher Hinweis) und `Strompreise` (Spezialtarif-Hinweis) waren ASCII-Stümpfe statt korrekter Umlaute hinterlegt — ggf. ein altes copy-paste aus einer ASCII-only-Quelle.

- **fix(input): Date-Inputs in Webkit linksbündig erzwingen (#152)** — `<input type="date">` rendert in Safari/iOS den Datumstext per Default zentriert, in Anlage-/Investition-/Strompreis-Modals fiel das auf. CSS-Selector `[&[type='date']]:text-left` und `[&::-webkit-datetime-edit]:text-left` in der zentralen `Input`-Komponente erzwingt linksbündig.

- **fix(auswertung): Tab-Wechsel scrollt zum Seitenanfang (#154)** — Bei Tab-Wechseln innerhalb der Auswertung (Energie/PV/Komponenten/Finanzen/CO2/Investitionen/Tabelle/Energieprofil) blieb die Seite auf der vorherigen Scroll-Position — am Tab-Wechselpunkt unsichtbar bis der Nutzer manuell hochscrollte. Smooth-Scroll auf den Page-Top im `onClick` der Tab-Buttons.

- **fix(waermepumpe): Konsistente KPI-Anzeige zwischen Cockpit und Auswertung (#153)** — Detlef-Bündel: in beiden Dialogen jetzt identische **Reihenfolge** (JAZ → Wärme → Strom → Ersparnis), **Icons** (Thermometer / Flame / Zap / TrendingUp) und **Farben** (orange / red / yellow / green). Zuvor war die Auswertungs-Sicht aus der Reihe (Wärme zuerst, JAZ an Position 3), Strom-Icon und -Farbe (lila vs. gelb) waren divergent.

- **fix(waermepumpe): JAZ ignoriert Daten vor Anschaffungsdatum (#153)** — Wichtigster Punkt aus Detlef-Issue #153: Im Cockpit- und Auswertungs-Dashboard summierten Backend-Aggregatoren alle vorhandenen `InvestitionMonatsdaten` der Wärmepumpe, ungeachtet des `anschaffungsdatum`. Das verfälschte JAZ und Ersparnis bei Anlagen, die vor dem Stichtag andere (unvollständige) Erfassungs-Methoden hatten — z. B. Detlef's Migration zu Shelly-erfasstem WP-Stromverbrauch ab April 2026: das alte JAZ blieb auf dem optimistischen Wert der WP-eigenen Strommessung (5,2) statt auf den realistischen 3,7–4. Filter eingebaut in `cockpit/komponenten.py` und `investitionen.py` (`/dashboard/waermepumpe`): Monate vor `(anschaffung.year, anschaffung.month)` werden ignoriert.

- **fix(dashboards): „Dashboard"-Suffix aus Top-Header entfernt + Card-Header bei n=1 versteckt (#153)** — Vereinheitlichung mit PV-Anlage-Cockpit, das nur eine Überschrift zeigt. Top-Header der Komponenten-Dashboards (Wärmepumpe / Speicher / Wallbox / E-Auto / Balkonkraftwerk / Sonstiges) heißt jetzt analog „Wärmepumpe" statt „Wärmepumpe Dashboard". Bei der Wärmepumpe wird zusätzlich der Card-interne Header ausgeblendet, wenn nur eine WP existiert (vorher doppelte „Wärmepumpe"-Überschrift).

---

## [3.22.0] - 2026-04-25

### Neue Features

- **feat(prognose): Genauigkeits-Tracking — MAE + Bias trennen, Spaltenstruktur stabilisieren (#151)** — Zwei eng verzahnte Diagnosen aus Rainer-PN gemeinsam aufgelöst. **MAE + MBE getrennt ausweisen:** Backend `GET /aussichten/prognosen/{id}/genauigkeit` aggregiert jetzt auf vorzeichenbehafteten relativen Fehlern und liefert zwei Kennzahlen — MAE (`abs()`) für Streuung, MBE (ohne `abs()`) für systematischen Bias. Drei Quellen statt zwei: zusätzlich zu OpenMeteo und Solcast wird auch EEDC bewertet (Basis × aktueller Lernfaktor). Neue Response-Felder: `openmeteo_mbe_prozent`, `eedc_mae_prozent`, `eedc_mbe_prozent`, `solcast_mbe_prozent`, plus `eedc_kwh` pro Tag. Frontend: `MAECard` → `MaeMbeCard` mit zwei KPIs nebeneinander (MAE + Bias) und Tooltips, drei Cards in der Genauigkeits-Sektion. Bias neutral gefärbt — Vorzeichen ist Information, nicht Wertung. **Spaltenstruktur stabil:** EEDC-Spalte in allen vier Tabellen (KPI-Matrix, 24h-Stundenvergleich, 7-Tage, Genauigkeits-Tracking) immer gerendert. Bei fehlendem Lernfaktor gedämpfter Header (`text-gray-400`) und `—` als Platzhalter, Tooltip verweist auf den Status-Banner. Die Genauigkeits-Tracking-Tabelle hatte bisher gar keine EEDC-Spalte; ist jetzt konsistent. Kein Spaltenflattern mehr nach Tag 7.

- **feat(prognose): Banner zeigt Restzeit bis Lernfaktor-Schwelle** — Der Hinweis „EEDC-Prognose nicht verfügbar" erläutert jetzt zusätzlich, wie viele Tage bereits gesammelt sind und wie viele noch bis zur 7-Tage-Schwelle fehlen (z. B. „3 von 7 Tagen, noch 4 Tage"). Die Berechnung filtert Tage mit gültiger OpenMeteo-Prognose UND IST-Ertrag > 0.5 kWh — analog zur Backend-Logik in `_berechne_faktor`.

- **feat(prognose): VM/NM-Split an Solar Noon proportional aufteilen** — Tageshälften (Vormittag/Nachmittag) wurden bisher hart bei 12:00 Uhr Clockzeit gesplittet. Korrekt ist der Split an der astronomischen Tagesmitte (Solar Noon, via Equation of Time), die je nach Standort und Datum bis ~30 min von 12:00 abweicht. Slots, die Solar Noon enthalten, werden proportional auf VM und NM verteilt. Konsistent zu `solar_forecast_service`.

### Bugfixes

- **fix(mobile): Mehrere Darstellungsprobleme auf kleinem Bildschirm (#149)** — Bündel von 7 Mobile-Layout-Fixes aus detLAN-Bugreport: Cockpit-/Energieprofil-SubTabs scrollen aktiven Tab automatisch in den sichtbaren Bereich (PV-Anlage, Daten-Cleanup nicht mehr abgeschnitten); Info-Icon der KPI-Tiles auf Mobile ausgeblendet (Tap-Tooltip bleibt); Monatsberichte Finanzen-T-Konto auf Mobile als 2-Spalten-Layout (Label | Wert+VJ+Δ gestapelt) statt 4 Spalten — GEWINN/Badges nicht mehr abgeschnitten; Section-Header „Monatsergebnis" + Ø-Cent-Suffix auf Mobile ausgeblendet (sonst mid-word truncated); Page-Sticky-Bars (Auswertung, Aussichten, Community) auf z-30, damit Tabellen-thead (z-10) sie nicht mehr überlagert; Energieprofil-Subtabs in Auswertung als `flex-wrap` (umbricht statt rechts rauszulaufen); Aussichten Langfristig stapelt Steuerung vertikal auf Mobile; Energieprofil-Seite mit `p-3 sm:p-6` und kleineren KPI-Tiles auf Mobile; Tabellen mit vielen Spalten zeigen Querformat-Hinweis nur in Mobile-Portrait.

- **fix(energieprofil): Batterie-Vollzyklen verwenden nur stationäre Speicher-SoC** — `_get_soc_history` und der Bulk-Fetch in `backfill_from_statistics` sammelten alle `live.soc`-Sensoren aus den Investitionen und nahmen den **ersten** als Batterie-SoC. Bei Anlagen mit E-Auto-Investition landete deren SoC-Sensor zuerst in der Liste — `break` nach dem ersten Entity sorgte dafür, dass der eigentliche stationäre Speicher nie angefasst wurde. Folge: `batterie_vollzyklen` in TagesZusammenfassung spiegelten den ΔSoC des Autos wider, nicht des Speichers. Im neuen Tage-Tabellen-Tab (#148, v3.21.0) wurde das offensichtlich (Tage mit `-` bei abgesteckten Auto, vereinzelt 0.7+ wenn das Auto gefahren+geladen wurde). Beide Selektions-Pfade filtern jetzt auf `inv.typ == "speicher"`. Multi-Speicher-Anlagen behalten das bisherige „erstes Speicher-Entity"-Verhalten (Kapazitäts-Gewichtung wäre eine separate Erweiterung). **Nutzer-Schritt nach Update:** einmal „Verlauf nachberechnen + überschreiben" auslösen, damit historische `batterie_vollzyklen`-Werte korrigiert werden.

- **fix(kraftstoffpreis): Service-Fehler im Backfill durchreichen statt verschlucken** — Wenn der EU-Oil-Bulletin-Download oder das XLSX-Parsing fehlschlug, lieferte der Service `{"aktualisiert": 0, "fehler": "Keine Kraftstoffpreise verfügbar"}` zurück. Der Endpoint las aber nur `aktualisiert/land/hinweis` — `fehler` wurde gestrippt und das Frontend zeigte „Keine offenen Tage." statt eines Error-Alerts. Der Counter „X Tage ohne Kraftstoffpreis" blieb unverändert, der Nutzer hatte keinen Hinweis auf den eigentlichen Fehler (z.B. URL-Wechsel beim Bulletin). Beide Endpoints (`/tages` und `/monats`) reichen `fehler` jetzt durch, das Frontend zeigt es als roten Error-Alert.

- **fix(energieprofil): Auswertungs-Tabelle Verfeinerungen** — Aktualisieren-Button pro Zeile in Auswertung → Energieprofil → Monat ausgeblendet (`showReaggregate`-Prop) — Reaggregation gehört in die Datenverwaltung (Daten → Energieprofil), nicht in die Auswertungs-Sicht. Stunden-Aggregat im Footer als „Xh YYmin" statt „22.93/24" (Pro-Tag-Werte bleiben unverändert „20/24"). Footer-Hintergrund voll-opak (statt /70-Transparenz im Dark Mode), damit die Summenleiste klar abgesetzt ist.

---

## [3.21.0] - 2026-04-25

### Neue Features

- **enhance(wp/roi): WP-Alternativvergleich präzisieren — Zusatzkosten + Monats-Gaspreis (#141)** — Zwei systematische Lücken im Gas-vs-WP-Vergleich geschlossen. Neuer Investitions-Parameter `alternativ_zusatzkosten_jahr` (€/Jahr) für Schornsteinfeger, Wartung, Gaszähler-Grundpreis — wird in allen 5 Berechnungs-Stellen (Aussichten historisch + Prognose, HA-Export inkl. WP-Sensor, PDF-Jahresbericht, Investitions-Vorschau) zu den Alt-Heizungs-Kosten addiert, in historischen Aggregaten anteilig pro erfasstem Monat. Neue optionale `Monatsdaten.gaspreis_cent_kwh`-Spalte (analog zu `kraftstoffpreis_euro` für Benzin): wenn pro Monat gepflegt, wird sie in der historischen Aggregation Monat für Monat verwendet, Fallback bleibt `wp.parameter.alter_preis_cent_kwh`. Damit ändert ein Tarifwechsel nicht mehr rückwirkend die ganze Historie. Erscheint im Monatsabschluss-Wizard und in `MonatsdatenForm` automatisch über `BEDINGTE_BASIS_FELDER` mit `bedingung_basis: hat_waermepumpe`.

- **enhance(auswertung/energieprofile): Tage-Tabelle im Monat-Tab + aufklappbare Sektionen (#148)** — Rainer's Wunsch (#148): „Tages-Energieprofile"-Tabelle prominent in den Auswertungen sichtbar machen. Sie bleibt unter Daten → Energieprofil als schmucklose Datenkonsole, im Auswertungs-Tab kommt eine optisch aufgewertete Sicht hinzu. Neue wiederverwendbare `<CollapsibleSection>`-Komponente in `components/ui` mit localStorage-Persistenz pro `storageKey`. `EnergieprofilTageTabelle` refactored: Body als wiederverwendbare Sub-Komponente `EnergieprofilTageTabelleEmbedded({anlageId, jahr, monat})` ohne Card-Wrap und Monatsauswahl, der Auswertungs-Monat-Tab nutzt sie ohne doppelten Selector. UI-Aufwertung der Tabelle (gilt für beide Sichten): Zellfarbe nach Wert (Heatmap-Stil), Negativpreis-Tage mit amber-Streifen + §51-Badge, sticky Σ-Monat-Footer mit Spaltenaggregat (Σ/Ø/max/min je nach Spalte). `EnergieprofilMonat` umgebaut: alle Sektionen nutzen `CollapsibleSection` in der Reihenfolge KPI-Strips (fix) → §51 → Kategorien (offen) → **Tage des Monats (neu, offen)** → Heatmap (offen) → Geräte/Tagesprofil/Peaks (zu).

- **enhance(auswertung/investitionen, cockpit): ROI-Seite aufräumen + zwei Amortisations-Sichten (#140)** — siehe gleichnamiger Commit-Hash 40ab07bd.

- **feat(energieprofil): Pro-Tag-Reaggregation per Knopf in der Tagestabelle (#146)** — Selbsthilfe-Mechanismus für den Fall, dass ein einzelner Tag im Energieprofil offensichtlich falsche Werte hat. Statt manuell die DB zu editieren oder das volle Backfill auszulösen, kann der Nutzer den Tag mit einem Klick neu aggregieren — `aggregate_day` macht intern delete+insert, ist also idempotent und betrifft nur den gewählten Tag. Refresh-Icon-Button am Ende jeder Tageszeile. Klick → Confirmation → API-Aufruf → Reload der Tabelle. Erfolgsmeldung mit Diagnose: grün bei Messdaten > 0, amber bei 0 Messdaten („keine Snapshots in DB, HA-Statistics nicht erreichbar"). Wirkt sowohl in Daten → Energieprofil als auch in Auswertung → Energieprofile (Beta) → Monat (geteilte Komponente). Neuer Endpoint `POST /api/energie-profil/{anlage_id}/reaggregate-tag?datum=YYYY-MM-DD`, der zusätzlich zu `stunden_verfuegbar` (geschriebene Slots) auch `stunden_mit_messdaten` (Slots mit echten Werten ≠ NULL) zurückgibt — letzteres ist der ehrlichere Erfolgsindikator.

### Bugfixes

- **fix(energieprofil): Snapshot-Job-Toleranz 60→10min + :55-Live-Preview (#146)** — Forum-Beobachtung Rainer (#146): Stundenwerte zeigten gelegentlich das Muster „Stunde 0.00 gefolgt von Folge-Stunde mit 2h-Summen-Spike". Identisches Symptom wie #145, aber in einem anderen Pfad nicht abgedeckt. **Root Cause**: `snapshot_anlage` (stündlicher :05-Job) verwendete `toleranz_minuten=60` beim HA-Statistics-Lookup. Wenn HA die Zielstunde zur Job-Laufzeit noch nicht finalisiert hatte (Latenz > paar Minuten), griff der 60-Min-Fallback und lieferte den Nachbar-Eintrag der Vorstunde. snap[h:00] wurde dann mit dem Wert von snap[(h-1):00] gespeichert → Slot h = 0 → Slot h+1 = 2-Stunden-Delta als Spike. #145 hatte denselben Mechanismus für `get_snapshot` (Self-Healing-Pfad) auf 10 Min Toleranz reduziert; der Scheduler-Job blieb dabei übersehen. **Fixes**: HA-Toleranz 60→10 Min, MQTT-Toleranz 30→10 Min, konsistent zu den anderen Pfaden. Wenn die Stunde zum :05-Zeitpunkt noch nicht in HA ist, schreibt der Job nichts; der nächste `aggregate_day`-Lauf (15 Min später) holt den Wert via Self-Healing nach. Plus neuer Scheduler-Job `sensor_snapshot_preview_job` bei `:55`: Schreibt pro Anlage einen Live-Zählerstand für die anstehende volle Stunde (h+1:00), aber nur wenn dort noch kein Eintrag existiert. Damit ist die laufende Stunde im Energieprofil sofort am Stundenende sichtbar statt erst um (h+1):05.

### Cleanup

- **cleanup(energieprofil): Phase D — W-Fallback + Feature-Flag entfernen (#138)** — Folge zu #135. Nach Validation auf Winterborn (v3.19.0+: 538 Tage Backfill, 0.1 % Drift Live↔Prognose-IST) ist der Zähler-Snapshot-Pfad als alleinige kWh-Quelle bestätigt. Phase D entfernt den Rollback-Pfad: Setting `energieprofil_quelle` und Env-Var `EEDC_ENERGIEPROFIL_QUELLE` entfernt; in `aggregate_day` der `_val()`-Helper raus, Werte direkt aus `snap_h`; in `backfill_from_statistics` der `else`-Branch (W-Pfad als kWh-Quelle) entfernt. Tote `batterie_kw_w`/`waermepumpe_kw_w`/`wallbox_kw_w`/`verbrauch_kw_w` entfernt — Peaks brauchen nur PV/Bezug/Einspeisung aus W-Integration. Netto −66 Zeilen. Verhalten auf Anlagen mit korrekt gemappten Energiezählern unverändert; auf nicht migrierten Anlagen erscheinen Stunden-kWh-Felder als `None` statt fehlerhaft hochgerechneter W-Integration.

---

## [3.20.4] - 2026-04-24

### Bugfixes

- **fix(tagesprognose): `AttributeError: 'Anlage' object has no attribute 'system_losses'` verschluckt** — Folgefix zu v3.20.3. Die Tagesprognose lieferte für Anlagen mit PV-Konfiguration weiter 0.0 kWh, obwohl Aussichten-Kurzfrist funktionierte. Log-Beleg: `WARNING energie_profil PV-Prognose für Tagesprognose fehlgeschlagen: 'Anlage' object has no attribute 'system_losses'`. Ursache: Der Code nutzte `anlage.system_losses or 14` — dieses Attribut existiert aber nicht auf dem `Anlage`-Modell; `system_losses` liegt historisch auf der letzten aktiven `PVGISPrognose` (so lesen es auch `solar_prognose.py` und `prefetch_service.py`). Der `AttributeError` wurde im umschließenden `try/except` als Warning geloggt und die Prognose fiel auf den Null-Initialwert zurück. Jetzt wird `system_losses` aus `PVGISPrognose` nachgeladen (gleicher Query wie in den anderen beiden Pfaden) mit Fallback auf `DEFAULT_SYSTEM_LOSSES`. Damit sind alle drei Prognose-Pfade final konsistent und die Tagesprognose liefert denselben Wertebereich wie Aussichten-Kurzfrist.

---

## [3.20.3] - 2026-04-24

### Bugfixes

- **fix(prognose): kWp/Neigung/Azimut aus Top-Level-Spalten lesen, nicht nur parameter-JSON** — Folgefix zu v3.20.2. Aussichten-Kurzfristig zeigte zwar sinnvolle Werte (z.B. 72.4 kWh), aber das lag nur an den zufällig passenden Defaults (Neigung=35°, Azimut=0° ≈ Süd). Im Log ([`solar_forecast_service`](eedc/backend/services/solar_forecast_service.py)) war sichtbar: `Open-Meteo Solar: 14 Tage, Neigung=35°, Azimut=0°` — also die Werte aus dem Code-Default, nicht aus der Investition. Ursache: `InvestitionForm` speichert `leistung_kwp`, `neigung_grad` und `ausrichtung` als **Top-Level-Spalten** auf der Investition-Tabelle, aber nur `ausrichtung_grad` im `parameter`-JSON. Die drei Prognose-Pfade (`energie_profil.py` Tagesprognose, `solar_prognose.py` Aussichten-Kurzfrist, `prefetch_service.py` Cache-Warmup) lasen alle ausschließlich aus `parameter`-JSON — und fielen stumm auf Defaults zurück, wenn die Werte dort nicht waren. Neuer Helper [`services/pv_orientation.py`](eedc/backend/services/pv_orientation.py) mit drei Funktionen (`get_pv_kwp`, `get_pv_neigung`, `get_pv_azimut`), die beide Speicher-Orte robust prüfen: erst Top-Level-Spalte, dann `parameter.*_grad` (Zahl), dann `parameter.*` (Zahl oder String mit Mapping), dann Default. Alle drei Prognose-Pfade umgestellt — zukünftig liefern sie identische Eingabe-Parameter an Open-Meteo, unabhängig davon, wo die PV-Parameter in der DB stehen.

---

## [3.20.2] - 2026-04-24

### Bugfixes

- **fix(tagesprognose): PV-Prognose fiel auf 0 kWh, wenn PV-Investition Text-Ausrichtung („Süd") statt numerischem Azimut hatte** — Im Energieprofil → Prognose-Tab lieferte die PV-Tagesprognose für Einzel-String-Anlagen teils `0.0 kWh`, während Aussichten → Kurzfristig für denselben Tag einen realistischen Wert (z.B. 72.4 kWh) zeigte. Ursache: Der Code in [energie_profil.py:1334](eedc/backend/api/routes/energie_profil.py#L1334) las `parameter.ausrichtung` direkt (z.B. `"Süd"`), während das Investitionsformular den exakten Azimut parallel in `parameter.ausrichtung_grad` (int) speichert. Der String ging ungeprüft an `get_solar_prognose()`, das eine Zahl erwartet — der Open-Meteo-API-Call schlug fehl und die Exception wurde im umschließenden `try/except` stillschweigend geschluckt, sodass `pv_stunden = [0.0] * 24` blieb. Die Kurzfrist-Prognose nutzt dieselbe Logik wie jetzt der Fix: erst `ausrichtung_grad` (Zahl), dann Fallback auf String-Mapping `{"süd": 0, "ost": -90, ...}`. Analog für Neigung (`neigung_grad` → `neigung` → Default 35°). Beide Prognose-Pfade liefern nun identische Eingabe-Parameter an Open-Meteo.

---

## [3.20.1] - 2026-04-24

### Verbessert

- **enhance(live/energiefluss, auswertung/pv-anlage): Redundante „Stringsumme" bei Einzel-String-Anlagen ausgeblendet (#137, Forum #335 detlan)** — An zwei Stellen wurde bei Anlagen mit nur einem PV-String dieselbe Zahl doppelt angezeigt:
  - Im **Live-Energiefluss** stand „Solarleistung X kW" als Summen-Label über dem Haus — identisch mit dem einzigen PV-Knoten-Label daneben. Wird jetzt nur noch bei `≥ 2` PV-Strings angezeigt (Summe über Teilerträge bleibt eine echte Zusatzinformation). Die Y-Position des darüberliegenden „Solar Soll"-Labels folgt dem mit.
  - In der **Auswertung → PV-Anlage „String-Details"-Tabelle** war die „Gesamt"-Fußzeile Duplikat der einzigen Detail-Zeile (kWp, SOLL, IST, Abweichung, kWh/kWp alle identisch, detlan-Kommentar im Issue). Footer wird jetzt nur noch bei `data.strings.length > 1` gerendert — die bereits bestehende Konvention im Performance-Chart des gleichen Tabs.

- **enhance(live/energiefluss): Fließende Strom-Linien im Lite-Modus (Forum dietmar1968)** — Nach dem Entfernen der SMIL-Partikel in v3.19.4 (die auf Mobile-Safari die Hauptruckel-Ursache waren) fehlte Dietmar die optische Visualisierung des Stromflusses. Jetzt zeichnet der Lite-Modus auf jeder aktiven Verbindungs-Kern-Linie einen CSS-animierten `stroke-dashoffset`-Fluss — derselbe Ansatz wie in LuminaCard und Tom's STATS Card. GPU-beschleunigt, Browser-nativ, kein SMIL-Overhead: Linien fließen deutlich sichtbar zur korrekten Seite (Quellen → Haus, Haus → Senken per `animation-direction: reverse`), Geschwindigkeit skaliert mit der Leistung (höhere kW = schnellerer Fluss, über CSS-Custom-Property `--flow-duration` pro Linie). iOS-Nutzer mit „Bewegung reduzieren" erhalten über `@media (prefers-reduced-motion: reduce)` automatisch statische Linien. Der Effekt-Modus bleibt unverändert — dort liefern die SMIL-Partikel weiterhin den vollen Visual-Wumms.

### Bugfixes

- **fix(tagesverlauf): Börsenpreis-Overlay für die frühen Morgenstunden erschien nicht (#147 Safi105)** — Im Live-Dashboard-Tagesverlauf fehlte die gepunktete Börsenpreis-Linie von 00:00 bis zum ersten Datenpunkt des Tages (z.B. 02:00). Zwei Ursachen:
  - Der EPEX-Fallback über aWATTar wurde nur geladen, wenn **gar kein** Strompreis-Sensor im Sensor-Mapping konfiguriert war. Hatten Nutzer einen Tibber/aWATTar-Sensor aktiviert, griff der Fallback nie — und HA-Recorder-Lücken (Sensoren publizieren oft erst nach Mitternacht) fielen heraus. Jetzt wird der Börsenpreis-Fallback **immer** geladen und pro 10-Minuten-Slot eingefüllt, wenn der Sensor für diesen Slot keine Werte liefert.
  - Im Frontend wurden fehlende Overlay-Werte als `0` (statt `null`) in die Chart-Datenstruktur geschrieben. Recharts zeichnete die Linie dadurch bei Y=0, was außerhalb der automatisch skalierten sekundären Y-Achse (typ. 5–20 ct/kWh) liegt — die Linie war faktisch unsichtbar. Fehlende Overlay-Werte sind jetzt `null`, `connectNulls={false}` erzeugt echte Lücken statt unsichtbarer Linien.
  - Zusätzlich: `TagesverlaufSerie`-Pydantic-Model um `einheit` und `max_w` erweitert — `einheit: "ct/kWh"` wurde bisher stillschweigend gestrippt (Legende zeigte „Börsenpreis (EPEX) ()" statt „(ct/kWh)"). Docker-Standalone-Nebenfix: Im MQTT-Pfad war `end = now` nur im Exception-Branch des EPEX-Loads gesetzt — `UnboundLocalError`, wenn der Fallback-Load erfolgreich war.

- **fix(monatsberichte): Kacheln auf Mobile schneiden Text ab (#147 Safi105)** — In den Monatsberichten rendete das Grid für Speicher-, Wärmepumpe- und E-Mobilität-KPIs mit `grid-cols-2 sm:grid-cols-4`, d.h. zwei Spalten bereits unter 640 px. Auf iPhone-Breiten reichte die Spaltenbreite nicht, die KPICard-Titel-/Subtitle-Truncation schlug zu: „Wirkungs…" statt „Wirkungsgrad", „Kapazität…" statt „Kapazität: 8 kWh". Jetzt konsistent mit dem Cockpit-Dashboard-Pattern `grid-cols-1 sm:grid-cols-2 md:grid-cols-4` — eine Spalte auf Mobile, zwei ab 640 px, vier ab 768 px. Die ausführliche Liste darunter (Ladung/Entladung/Bilanz/Wirkungsverluste) bleibt unverändert.

- **fix(cockpit): KPICard-Versatz bei klickbaren vs. nicht-klickbaren Karten (#147 Safi105)** — In der „Energie-Bilanz"-Sektion fiel die erste Karte (PV-Erzeugung, mit Klick-Navigation) einen Tick kleiner aus als Gesamtverbrauch/Netzbezug/Einspeisung. Ursache: Der Button-Zweig der Dashboard-`KPICard` setzte `className="card p-3"`, während der nicht-klickbare Zweig `<Card className="p-3">` nutzte. Die `Card`-Komponente injizierte zusätzlich ihr Default-Padding `p-6`, und mit zwei konkurrierenden Padding-Klassen gewinnt in Tailwind die in der CSS-Reihenfolge spätere — also `p-6` statt des gewünschten `p-3`. Nicht-klickbare Variante nutzt jetzt ebenfalls `<div className="card p-3">` direkt, damit beide Varianten pixelgleich sind.

- **fix(anlagendialog): Löschen von Versorgern/Zählern wurde rückgängig gemacht** — Entfernte man im Anlagendialog den letzten Versorger (Strom/Gas/Wasser) und speicherte, erschienen Versorger und Zähler beim nächsten Öffnen wieder („wie von Zauberhand", Forum-Bericht #376 detlan). Ursache: `AnlageForm` sendete `versorger_daten: undefined`, wenn der lokale State leer war — Pydantic `exclude_unset=True` ließ das Feld im Update dadurch komplett aus, und der Backend-Wert blieb unverändert. Frontend sendet jetzt `null`, das Feld wird in der DB explizit geleert. Betrifft nur den Fall „letzter Versorger entfernt"; Löschen einzelner Zähler innerhalb eines Versorgers war nie betroffen.

- **fix(infothek): Vertragsbeginn/Kündigungsfrist erschienen doppelt im Formular** — Die Kategorie-Schemas für `stromvertrag`, `gasvertrag`, `versicherung` und `wartungsvertrag` enthielten eigene `vertragsbeginn` / `kuendigungsfrist_monate` / `vertragsnummer`-Felder, während die übergreifende „Vertragsdaten (optional)"-Sektion darunter dieselben Felder noch einmal rendert (Forum-Bericht #376 detlan). Doppelte Keys aus den Kategorie-Schemas entfernt; die übergreifende Sektion ist jetzt die einzige Stelle für diese drei Felder. JSON-Keys und gespeicherte Parameter bleiben identisch — keine Daten-Migration nötig. Beide PDF-Export-Pfade (reportlab + weasyprint) mergen die übergreifenden Felder beim Rendern, damit Labels wie „Kündigungsfrist (Monate)" korrekt erscheinen statt eines Key-Fallbacks.

### Verbessert

- **enhance(infothek): Zählernummer wird aus Anlagendaten vorbelegt** — Beim Anlegen eines neuen Stromvertrag-Eintrags wird die Zählernummer jetzt aus `anlage.versorger_daten.strom.zaehler[]` vorbelegt (erster Zähler mit gefüllter Nummer). Ergänzt die bereits bestehende Vorbelegung für `anbieter`, `tarif_ct_kwh` und `kundennummer` (Forum-Bericht #376 detlan).

---

## [3.20.0] - 2026-04-23

### Bugfixes

- **fix(kennzahlen): Performance Ratio nutzt jetzt GTI statt horizontaler Einstrahlung (#139)** — Die PR-Formel `pv_ertrag / (strahlung_summe × kWp)` nutzte `shortwave_radiation` von Open-Meteo — das ist die **horizontale** Globalstrahlung (GHI). Bei steilen Modulen (typ. 30–40°) und tiefstehender Wintersonne ist die auf die Modul-Fläche projizierte **Global Tilted Irradiance (GTI)** 2–3× höher. Die theoretische Ertragsreferenz wurde dadurch im Winter systematisch unterschätzt und PR-Werte liefen auf physikalisch unmögliche 1.2–2.8 (Winterborn 2025-12-28: PR=2.807 bei 42.7 kWh Ertrag). Open-Meteo Archive + Forecast liefern jetzt zusätzlich `global_tilted_irradiance` mit Modul-Tilt und -Azimut; bei Multi-String-Anlagen werden parallele Calls pro Orientierungsgruppe abgesetzt und kWp-gewichtet kombiniert (analog Live-Wetter-Pfad). Ohne gemappte PV-Module bleibt PR bewusst `None` statt einen verzerrten GHI-Wert zu melden. Validation: Winterborn 2025-12-28 (GHI 1317 Wh/m², GTI Süd35° 3358 Wh/m², Faktor 2.55×) liefert bei 15 kWp Anlagenleistung PR=0.85 (plausibel für einen kalten Wintertag), vorher 2.16. Betrifft historische `TagesZusammenfassung.performance_ratio`, `MonatsAuswertungResponse.performance_ratio_avg` und die PR-Spalte im PDF-Jahresbericht — **nach Update einmalig „Verlauf nachberechnen + überschreiben" auslösen**. PV-kWh-Werte selbst bleiben unverändert.

- **fix(energieprofil/prognose): Stunden-Slot-Konvention vereinheitlicht auf Backward (#144)** — Im Prognosen-Tab (Aussichten → Prognosen → Stundenvergleich) zeigten OpenMeteo, Solcast und IST unter demselben Slot-Label physikalisch unterschiedliche Zeitintervalle: OpenMeteo [N-1, N), Solcast [N-0.5, N+0.5), IST [N, N+1). Forum-Bericht MartyBr (#344) + rapahl (#356): „Um 6:00 Uhr müsste IST noch 0 sein, weil Sonne erst aufgeht". Jetzt alle drei auf Backward-Konvention **Slot N = Energie [N-1, N)** — Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber). Slot 0 eines Tages enthält jetzt die Energie der letzten Stunde des Vortags (23:00 → 00:00), passend zur Summenbildung.
  - `sensor_snapshot_service.get_hourly_kwh_by_category`: Delta `snap[h] − snap[h-1]` wird in Slot h eingetragen (vorher: `snap[h+1] − snap[h]` in Slot h). Snapshot-Range auf h = -1..23 erweitert, damit Slot 0 aus dem Vortag-23:00-Snapshot gefüllt werden kann.
  - `solcast_service` (beide Pfade, API + HA-Sensor): 30-Min-Buckets werden jetzt per Slot-Marker `ceil(bucket_ende)` dem richtigen Backward-Slot zugeordnet. Ein Bucket am Tagesübergang (z.B. [23:00, 23:30) heute) landet korrekt in Slot 0 des **Folgetags**, nicht fälschlich in Slot 0 des heutigen Tages.
  - **Strompreis-Stunden bleiben Forward** ([N, N+1)): industrieüblich für aWATTar/Tibber/EPEX („Slot N = Preis ab N Uhr"), semantisch passend für einen Intervallwert „gilt ab jetzt" statt akkumulierter Energie.
  - **W-Fallback (Anlagen ohne gemappte Zähler)** bleibt vorerst Forward — wird mit Issue #138 (W-Fallback-Cleanup) entfernt.
  - **Nach Update nötig:** Einmalig „Verlauf nachberechnen" mit Überschreiben (Energieprofil → Datenverwaltung) auslösen, damit alle historischen Stundenwerte in die Backward-Slots umverteilt werden. Tagessummen und alle abgeleiteten Kennzahlen (Autarkie, PR, Lernfaktor) bleiben konventionsunabhängig korrekt.

- **fix(energieprofil): Snapshot-Lücken lösen nicht mehr „Stunde-Null + Folge-Spike" aus (#145)** — Fehlt ein stündlicher Sensor-Snapshot in `sensor_snapshots` (Scheduler-Ausfall, HA-Statistics-Timeout, MQTT-Cache leer), erzeugte die kumulative Delta-Bildung in `get_hourly_kwh_by_category` bisher ein sichtbares Artefakt: eine Stunde mit 0.00 kWh, gefolgt von einer Stunde mit dem aufgestauten 2h-Delta als Spike (Forum-Bericht MartyBr #354). Ursache: Das Self-Healing im `get_snapshot`-Fallback griff auf HA Long-Term-Statistics mit ±120 min Toleranz zu und lieferte per `ORDER BY ABS(...)` den zeitlich nächsten Nachbar-Wert zurück — wenn die Stunde in HA ebenfalls fehlte, war das der Wert der Vor- oder Folgestunde, und der nachfolgende Delta `snap[h+1] − snap[h]` wurde 0. Zwei Änderungen:
  - `get_snapshot`: HA-Statistics-Fallback-Toleranz von 120 min auf **10 min** reduziert. Hourly-Statistics speichern auf der Stundengrenze; eine Abweichung > 10 min ist fast immer ein „kein Eintrag zur Zielstunde" — der Fallback liefert dann bewusst None, statt einen falschen Nachbar-Wert. Gleiches Prinzip für den MQTT-Snapshot-Fallback (30 → 10 min), zusätzlich `nearest`-Sortierung statt `timestamp.asc()` (der frühere „erster-im-Fenster"-Lookup hätte bei mehreren Publikationen zufällig den ältesten zurückgegeben).
  - `get_hourly_kwh_by_category`: Nach der Snapshot-Collection werden **echte Lücken jetzt linear zwischen den Nachbar-Stunden interpoliert**. Ein kumulativer Zähler wächst monoton — die Interpolation verteilt das Gesamt-Delta über eine Lücke gleichmäßig auf die betroffenen Stunden, statt es in eine einzige Stunde aufzustauen. Ränder (H0 fehlend am Tagesanfang, H24 am Tagesende) werden nicht extrapoliert — dort bleibt der Wert None und die betroffene Stunde fällt wie bisher aus der Delta-Bildung. Tagessumme bleibt in allen Fällen korrekt (bereits vorher durch `snapshot[24] − snapshot[0]`).

---

## [3.19.4] - 2026-04-23

### Performance

- **perf(live/energiefluss): Lite-Modus jetzt wirklich „lite" — iPad/Mobile-Safari** — Drei Änderungen am Energiefluss-Diagramm, die zusammen Ruckler auf iPad und schwächeren Mobile-Geräten beseitigen sollten. Forum-Bericht (#345 + #353, dietmar1968: „ruckelt auch im Lite-Modus").

  - **SMIL-Partikel-Animationen werden im Lite-Modus nicht mehr gerendert** — Bisher liefen pro aktiver Linie weiterhin ein `<animateMotion>` + ein `<animate>` mit `repeatCount="indefinite"`. Bei einer Anlage mit 6 aktiven Knoten waren das ≥12 dauerhafte SMIL-Animationen — auf Mobile-Safari der mit Abstand größte Performance-Faktor (WebKit hat SMIL nie effizient implementiert). Im Effekt-Modus bleiben sie unverändert.
  - **`filter`-Attribute der Knoten-Karten werden im Lite-Modus weggelassen** — statt sie nur zu No-Op-Filter-Definitionen zu reduzieren. Safari erstellt für jedes Element mit `filter="…"` einen separaten Compositing-Layer, auch wenn der Filter nichts tut.
  - **`EnergieFlussBackground` in `React.memo` gewrappt** — die ~180 SVG-Hintergrund-Elemente (Sterne, Ringe, Strahlen je nach Variante) werden jetzt nicht mehr bei jedem 5-Sekunden-Polling neu durch React diff'd, weil sich keine Background-Props ändern.

---

## [3.19.3] - 2026-04-23

### Bugfixes

- **fix(community): BKW-Leistung jetzt × Anzahl Module aggregiert** — `community_service.py` summierte für Balkonkraftwerk nur das Feld `leistung_wp` (Watt pro Modul), ohne die Anzahl der Module einzurechnen. 800-W-BKWs mit 2 × 400 W erschienen in der Community-Anzeige daher als 400 W. Forum-Bericht (#342, Radiocarbonat).

- **fix(community/trends): Tooltip in „Community-Entwicklung" zeigt formatierte Labels** — Der Hover-Tooltip im Trends-Tab nutzte die rohen Daten-Keys (`speicher`, `waermepumpe`, `eauto`), während die Legende darunter bereits korrekt formatierte. Tooltip nutzt jetzt denselben `nameFormatter` wie die Legende (Speicher-Quote, Wärmepumpen-Quote, E-Auto-Quote). Forum-Bericht (#342, Radiocarbonat).

- **fix(live/tagesverlauf): Legenden-Toggle blendet wieder ein** — Klick auf einen Legenden-Eintrag entfernte die Linie/Area komplett aus dem DOM (über `hatDaten()`-Filter bei 0-Daten), wodurch ein erneuter Klick die Serie nicht zurückbringen konnte. Hide-Steuerung wurde auf das Recharts-eigene `hide`-Prop umgestellt; Toggle funktioniert jetzt zuverlässig in beide Richtungen — sowohl für Areas (PV/Verbrauch/Speicher) als auch für die Overlay-Linie (Strompreis). Forum-Berichte (#343 detlan, #348 dietmar1968).

- **fix(waermepumpe): „Wärmepumpe" wird im Kostenvergleichs-Chart nicht mehr abgeschnitten** — Y-Achsen-Spalte des horizontalen Bar-Charts war mit `width={100}` zu schmal für das längste Label (11 Zeichen). Auf 110 erhöht — analog zu bestehenden Charts in der Auswertung. Forum-Bericht (#343, detlan).

- **fix(live/energiefluss): iPad-Lite-Default robuster** — Der Auto-Detect für den Lite-Modus (reduzierte Animationen, kein Blur-Filter — schont schwächere GPUs) griff für iPads bisher nur unter 768 px Viewport-Breite, was iPads üblicherweise nicht erfüllen. Zusätzlich identifiziert sich iPadOS-13+ in Safari als „Macintosh", weshalb die `/iPad/`-UA-Prüfung leer lief. Erkennung jetzt zusätzlich über `navigator.maxTouchPoints > 1` bei Macintosh-UA. Wirkt nur bei neuen Nutzern — wer den Toggle bereits einmal manuell angefasst hat, behält seine localStorage-Wahl. Forum-Bericht (#345, dietmar1968).

### Issues

- **#143** Wetter-Dashboard: vermutete Zeitverschiebung in Stunden-Prognose (offen, wartet auf Diagnose-Daten von MartyBr — Forum #344)

---

## [3.19.2] - 2026-04-23

### Bugfixes

- **fix(ui/tooltip): Tooltip löst horizontalen Scroll in Tabellen aus** — `FormelTooltip` rendert jetzt mit `position: fixed` (statt `absolute`), damit `overflow-x:auto`-Container (z. B. ROI-Tabelle) den Tooltip nicht clippen und keinen unerwünschten horizontalen Scroll auslösen. Tooltip bleibt zudem zuverlässig im Viewport (Links-/Rechts-Clamp). Forum-Bericht (#340): Scrollbar in der ROI-Tabelle „kurz sichtbar, springt zurück".

- **fix(ui/charts): Y-Achse zeigte „0000 kWh" statt „10.000 kWh"** — Im Cockpit-PV-Anlage-Diagramm (`PVStringVergleich`) wurde der Y-Achsen-Tick bei 10.000 kWh wegen zu schmaler Achse abgeschnitten. Formatter nutzt jetzt deutsche Tausenderpunkte (`10.000 kWh`) und schaltet bereits ab 5.000 kWh auf MWh-Anzeige um (`10 MWh`).

### Verbessert

- **enhance(ui/charts): SOLL/IST-Farben vereinheitlicht** — Neue Konstante `SOLL_IST_COLORS` (Blau/Amber/Grün) in `lib/colors.ts`. Beide SOLL-IST-Diagramme im Auswertungen-PV-Tab nutzen sie konsistent (vorher: `opacity={0.6}` auf SOLL machte das Blau im zweiten Diagramm dunkler als die Legende — Forum-Bericht #340: „Das Blau im zweiten Diagram entspricht nicht dem Blau der Legende"). Cockpit-PV-Vergleich nutzt sie bei Single-String-Anlagen, behält die String-Farben-Differenzierung bei mehreren Strings.

### Issues

- **#136** WP-Taktungs-Anzahl als fortlaufender Zähler in Tages-/Monats-Analytik (offen)
- **#137** Live-Energiefluss: Stringsumme über dem Haus bei Einzel-PV-Konfiguration ausblenden (offen)
- **#140** ROI/Amortisations-Anzeige verschlanken: weniger parallele Werte, klarere Hierarchie (offen, Diskussion mit detlan)

---

## [3.19.1] - 2026-04-22

### Bugfixes

- **fix(ha-export/mqtt): WP-/E-Auto-/BKW-Ersparnisse in MQTT-Jahresersparnis** — Die MQTT-Sensoren `jahres_ersparnis_euro`, `roi_prozent` und `amortisation_jahre` rechneten bisher nur den PV-Netto-Ertrag (Einspeise-Erlös + Eigenverbrauchs-Ersparnis) und ignorierten die Alternativkosten-Ersparnisse von Wärmepumpe (vs. Gas/Öl), E-Auto (vs. Benzin) und Balkonkraftwerk. Bei Anlagen mit WP/E-Auto führte das zu absurd langer Amortisation (Forum-Bericht: 188,6 Jahre). `calculate_anlage_sensors` rechnet die historischen Komponenten jetzt analog zu `aussichten.py:get_finanz_prognose` mit ein. Wirkt automatisch auch im periodischen `mqtt_auto_publish_job`.

- **fix(community): JAZ-Kachel nutzt typ-spezifischen Vergleich** — Die Wärmepumpen-JAZ in der Komponenten-Kachel der Community-Übersicht verglich gegen den globalen Durchschnitt über alle WP-Arten, während das Verbesserungspotenzial bereits den fairen typ-spezifischen Vergleich (`jaz_typ`) nutzte. Ergebnis: leicht abweichende Prozentwerte bei identischer Kennzahl (Forum-Rückfrage: -11,1 % vs. -11,9 %). Beide Darstellungen nutzen jetzt konsistent `jaz_typ` mit Fallback auf `jaz`.

### Verbessert

- **enhance(ui/roi): „Sicht"-Hinweis in allen ROI-Tooltips** — `FormelTooltip` um optionalen `sicht`-Block erweitert. Alle ROI-/Amortisations-Anzeigen (Cockpit, Investitionen-Tab inkl. „Tatsächlich realisiert"-Block, ROI-Dashboard inkl. Detail-Tabelle, Aussichten-Finanzen, Amortisations-Bar) zeigen jetzt im Tooltip an, **welche Sicht** die Zahl darstellt (z. B. „Pro Investition · Jahres-ROI · Mehrkosten-Ansatz · Prognose" vs. „Gesamt-Anlage · IST-Werte · kumuliert"). Adressiert die im Forum berichtete Verwirrung über mehrere unterschiedliche ROI-/Amortisations-Werte nebeneinander.

---

## [3.19.0] - 2026-04-22

### Kritischer Bugfix

- **fix(energieprofil): kWh-Werte aus Zähler-Snapshots statt Leistungs-Integration (#135)** — Bisher berechnete `aggregate_day` Stunden-kWh aus `leistung_w`-10-Min-Samples (±5-15% Drift), obwohl kumulative Zähler wie `pv_erzeugung_kwh` im Sensor-Mapping vorhanden waren. Dadurch wichen Prognosen-IST, Lernfaktor, Heatmaps und abgeleitete Monatswerte vom Live Dashboard ab (konkreter Fall: Winterborn 2026-04-22 — Live 28.3 vs Prognosen IST 31.0 kWh, Zähler-Realität 31.25 kWh). Neue Architektur: Scheduler-Job schreibt stündlich kumulative Zählerstände in die `sensor_snapshots`-Tabelle, alle kWh-Werte werden als Snapshot-Differenz berechnet. Quellen: HA Statistics (Add-on) oder MQTT-Energy-Snapshots (Standalone/Docker). Self-Healing füllt Lücken on-demand.

### Features

- **feat(energieprofil): Strikte NULL-Semantik bei fehlenden Zählern** — Wenn keine kumulativen Zähler gemappt sind, bleiben die betroffenen `TagesEnergieProfil`-Felder `NULL` statt aus Leistungs-Samples geschätzt zu werden. Prognosen-IST-Response enthält neues `ist_unvollstaendig`-Flag, Monatsauswertung liefert `stunden_fehlend_pv`/`stunden_fehlend_verbrauch`. Frontend zeigt ⚠-Badge neben IST-Werten bei Datenlücken.

- **feat(datencheck): Neue Kategorie „Energieprofil – Zähler-Abdeckung"** — Daten-Checker prüft pro Anlage und Komponente, welche kumulativen kWh-Zähler (`pv_erzeugung_kwh`, `ladung_kwh`, `entladung_kwh`, `stromverbrauch_kwh`, Einspeisung/Netzbezug) gemappt sind. Warnt mit konkreter Liste fehlender Zähler und verlinkt zum Sensor-Mapping-Wizard.

### Verbessert

- **enhance(energieprofil): Info-Banner auf Datenverwaltungs-Seite** — Neuer Hinweis, der Nutzer einmalig nach dem Update zur Ausführung von „Verlauf nachberechnen" mit aktiver „Überschreiben"-Option auffordert, damit historische Daten auch aus Zählern statt aus Leistungs-Schätzung stammen.

- **enhance(prognosen): StundenProfilEintrag.kw jetzt nullable** — Datenlücken im Stundenprofil werden als `null` übertragen (Recharts zeigt Chart-Unterbrechung statt 0-Linie).

### Backend

- **feat(db): Neue Tabelle `sensor_snapshots`** — Stündliche Snapshots kumulativer kWh-Zählerstände (anlage_id + sensor_key + zeitpunkt). Basis für die neue Energieprofil-Berechnung.

- **feat(api): HA Statistics Helper `get_value_at`** — Liest kumulativen Zählerstand zu einem bestimmten Zeitpunkt aus HA Statistics (SQLite + MariaDB, Wh→kWh-Konvertierung, ±Toleranzfenster).

- **feat(scheduler): `sensor_snapshot_job`** — Neuer stündlicher Job (`minute=5` Cron) schreibt aktuelle Zählerstände aus HA Statistics + MQTT-Energy-Cache in `sensor_snapshots`.

- **feat(standalone): MQTT-Energy-Cache als Zähler-Quelle** — Standalone/Docker-Installationen ohne HA Statistics nutzen automatisch `mqtt_energy_snapshots` als Basis für die Zähler-Berechnung. `aggregate_day` synthetisiert ein 24h-Stundenraster wenn nur kumulative Zähler ohne `leistung_w` verfügbar sind.

- **fix(backfill): `sonstige_keys` in `_sonderschluessel` ergänzt** — Latenter Bug in `backfill_from_statistics`: Sonstige-Erzeuger-Investitionen flossen doppelt in `pv_kw` ein (analog zum bereits gefixten Bug in `aggregate_day`).

- **feat(config): Feature-Flag `EEDC_ENERGIEPROFIL_QUELLE`** — Default `"zaehler"` (neue Architektur), Rollback auf `"leistung_w"` möglich bei Problemen.

### Hinweis

> **Empfohlene Aktion nach Update:** Auf `Einstellungen → Energieprofil → Verlauf nachberechnen` klicken, Option „Bestehende Tage überschreiben" aktivieren, dann „Verlauf nachberechnen" auslösen. Dadurch werden historische Tagesprofile konsistent aus den kumulativen Zählerständen neu berechnet (einmalig, 1-5 Min Laufzeit). Ohne diesen Schritt bleiben ältere Tage mit der alten Leistungs-Schätzung bestehen.

---

## [3.18.0] - 2026-04-21

### Features

- **feat(energieprofil): Eigener Tab mit Tages-Tabelle + Datenverwaltung (#133)** — Neue Seite `Einstellungen → Energieprofil` bündelt die tagesbezogenen Auswertungen und Datenverwaltungs-Aktionen der gewählten Anlage. Datenbestand-Kacheln (Stundenwerte/Tagessummen/Monatswerte, Abdeckung, Zeitraum) sind jetzt anlage-spezifisch. Tages-Tabelle mit Jahr/Monat-Selektor (zeigt nur Zeiträume mit Daten), Spalten-Selektor mit Gruppen (Peak-Leistungen, Tages-Summen, Performance, Wetter, §51-Börsenpreise), 12-Zeilen-Scrollansicht mit sticky Header. Aktionen: Vollbackfill aus HA-Statistik (mit overwrite-Option), Kraftstoffpreis-Tages-Backfill (nur sichtbar bei offenen Tagen), Energieprofil-Daten löschen (anlage-spezifisch statt global).

- **feat(monatsdaten): Datenverwaltung auf Monatsdaten-Seite** — Neuer Abschnitt für Kraftstoffpreis-Monats-Backfill (nur sichtbar bei offenen Monaten). Tabelle jetzt auf ~12 Zeilen mit eigener vertikaler Scrollbar und sticky Header begrenzt. `<select>`-Accessibility-Labels verknüpft.

### Verbessert

- **enhance(navigation): Tab-Konsolidierung (#133)** — Tab `Monatsabschluss` in der Einstellungen-Tab-Leiste entfernt (war nur Redirect auf Monatsdaten). Direkt-Einstieg über den `Monatsabschluss`-Menüpunkt in der Einstellungen-Dropdown bleibt erhalten. Neuer Tab `Energieprofil` in der Daten-Gruppe ergänzt.

- **enhance(settings): `Allgemein` entkernt** — Block `Datenbestand Energieprofile` samt globalem Löschen-Button aus `Einstellungen → Allgemein` entfernt (wandert zur neuen Energieprofil-Seite). Die Seite zeigt jetzt nur noch Theme, HA-Integration und Datenbank-Info.

### Backend

- **feat(api): Anlage-spezifische Energieprofil-Endpoints** — Neu: `GET /energie-profil/{id}/stats` (Profildaten-Kennzahlen pro Anlage), `GET /verfuegbare-monate` (Jahr/Monat-Kombinationen mit Einträgen), `GET /kraftstoffpreis-status` (offene Tages-/Monats-Zeilen), `POST /kraftstoffpreis-backfill/tages` und `/monats` als Split des bisherigen kombinierten Endpoints (Alt-Endpoint bleibt als Alias). `DELETE /energie-profil/{id}/rohdaten` löscht jetzt konsistent auch `TagesZusammenfassung` (analog zum globalen Alt-Endpoint).

---

## [3.17.1] - 2026-04-21

> **⚠️ Backup erforderlich** — Internes Refactoring der Formulardaten-Verarbeitung. Bitte vor dem Update ein Backup erstellen.

### Verbessert

- **refactor(monatsdaten): Dynamisches Formular aus field_definitions (#132 Phase E)** — MonatsdatenForm nutzt jetzt `getFelderFuerInvestition()` als Single Source of Truth für alle Investitionsfelder. Initialisierung, Submit-Handler und Section-Rendering sind vollständig generisch — keine hardcodierten Typ→Felder-Maps mehr. 4 spezialisierte Section-Komponenten (Speicher, E-Auto, Balkonkraftwerk, Sonstiges) durch die generische InvestitionSection ersetzt. Neue Felder werden automatisch angezeigt wenn sie in `field_definitions.py` definiert sind.

### Bugfixes

- **fix(monatsdaten): Sonstiges/Speicher sendete falsche Feldnamen** — Die Monatsdaten-Erfassung für Sonstiges-Investitionen der Kategorie "Speicher" sendete `ladung_kwh`/`entladung_kwh` statt der kanonischen Namen `erzeugung_kwh`/`verbrauch_sonstig_kwh`. Die alten Feldnamen wurden vom Cockpit nie gelesen, sodass diese Daten in der Auswertung fehlten. Jetzt werden die korrekten kanonischen Namen verwendet.

---

## [3.17.0] - 2026-04-21

### Features

- **feat(kraftstoffpreis): Dynamische Benzinpreise für E-Auto-ROI** — Statt statischem `benzinpreis_euro`-Parameter werden jetzt echte monatliche Kraftstoffpreise aus dem EU Weekly Oil Bulletin verwendet. Neues Feld `Monatsdaten.kraftstoffpreis_euro` (€/L) mit automatischem Vorschlagswert im Monatsabschluss-Wizard (Konfidenz 85). ROI-Berechnung (Aussichten), HA-Sensor-Export und PDF-Finanzbericht nutzen pro Monat den echten Preis — Fallback auf statischen Parameter wenn kein Monatswert vorhanden. Backfill-Endpoint befüllt auch Monatsdaten rückwirkend (Oil Bulletin History seit 2005).

> **Hinweis:** Die E-Auto-Ersparnis (Aussichten, HA-Sensor, PDF) wird jetzt mit echten monatlichen Benzinpreisen berechnet statt mit dem statischen Wert aus den Investitions-Parametern. Dadurch können sich angezeigte Ersparnisse gegenüber früheren Versionen verändern — nach oben oder unten, je nachdem ob der reale Preis über oder unter dem konfigurierten Wert lag. Die Berechnung ist damit genauer. Um die Monatsdaten rückwirkend mit Preisen zu befüllen: Einstellungen → Energieprofil → Kraftstoffpreis-Backfill.

### Verbessert

- **enhance(monatsabschluss): Preisfelder im Wizard und Zusammenfassung** — Kraftstoffpreis und Strompreis werden jetzt in der Basisdaten-Seite und in der Zusammenfassung des Monatsabschluss-Wizards angezeigt. Monatsdaten-Formular (Erstellen/Bearbeiten) zeigt ebenfalls das Benzinpreis-Feld (bedingt: nur bei E-Auto-Investitionen).

---

## [3.16.16] - 2026-04-21

### Features

- **feat(energieprofil): Verbrauchsprognose (Etappe 3b Phase A)** — Neuer Sub-Tab "Prognose" im Energieprofil: Kombinierte Verbrauchs- + PV- + Batterie-Prognose für einen Tag. Verbrauchsprofil aus historischen Stundenmitteln (gewichteter Ø, Wochentag-Kaskade, Halbwertszeit 14 Tage), PV-Stundenprofil aus OpenMeteo GTI (kalibriert mit Lernfaktor) oder Solcast, Batterie-SoC-Simulation mit Speicher-voll/leer-Zeitpunkt. Chart (PV/Verbrauch/Netto + SoC-Overlay), KPI-Cards, Stundentabelle.

### Vorbereitung (v3.17.0)

- **prep(kraftstoff): EU-Kraftstoffpreis-Sammlung** — Wöchentliche nationale Durchschnittspreise (Euro-Super 95, inkl. Steuern) aus dem EU Weekly Oil Bulletin der EU-Kommission. Historische Daten seit 2005, alle EU-Länder + CH (via AT). Scheduler-Job (Di 06:00), manueller Backfill-Endpoint, Speicherung in `TagesZusammenfassung.kraftstoffpreis_euro`. Vorbereitung für dynamische E-Auto-Ersparnisberechnung.

### Bugfixes

- **fix(energieprofil): pv_kw zählte Sonstiges-Erzeuger fälschlich als PV** — Sonstige Erzeuger (BHKW etc.) wurden in der TagesEnergieProfil-Aggregation mitgezählt, was PV-spezifische KPIs (Performance Ratio, Lernfaktor) verfälschte.

- **fix(prognose): Grün-Schwelle bei Prognose-Abweichung auf 10%** — Anpassung der farblichen Bewertung der Prognosegenauigkeit.

---

## [3.16.15] - 2026-04-20

### Features

- **feat(prognose): Saisonaler Lernfaktor (MOS-Kaskade)** — Der Lernfaktor nutzt jetzt eine saisonale Kaskade: Monatsfaktor (≥15 Tage gleicher Kalendermonat) → Quartalsfaktor (≥15 Tage) → 30-Tage-Fenster (≥7 Tage, bisheriges Verhalten). Bei wachsendem Datenbestand wird die Kalibrierung automatisch präziser. Im Prognosen-Tab wird die aktive Stufe angezeigt.

- **feat(prognose): Erweiterbare Prognose-Architektur** — Prognose-Quellen als Registry (`PROGNOSE_QUELLEN`) für zukünftige Erweiterungen vorbereitet. Neues Anlage-Feld `prognose_basis` zur Auswahl der Kalibrierungsquelle in den Anlagenstammdaten. Lernfaktor wird pro Quelle separat berechnet und gecacht.

---

## [3.16.14] - 2026-04-20

### Bugfixes

- **fix(prefetch): Prognose-Persistierung vom Dashboard in den Scheduler verlagert** — `pv_prognose_kwh` und Solcast-Tageswerte werden jetzt alle 45 Min automatisch vom Prefetch-Job in `TagesZusammenfassung` geschrieben. Vorher war die Persistierung ein Nebeneffekt des Dashboard-Besuchs (fragil), was dazu führte, dass der Lernfaktor bei keinem Nutzer berechnet werden konnte.

---

## [3.16.13] - 2026-04-20

### Bugfixes

- **fix(solcast): DetailedForecast Attribut-Name korrigiert** — BJReplay Solcast-Integration liefert das Stundenprofil als `DetailedForecast`, nicht `detailedHourly`. Dadurch fehlten bei HA-Sensor-Nutzern das Stundenprofil im Chart und die p10/p90 Konfidenzintervalle in der 7-Tage-Tabelle. Betraf insbesondere Anlagen mit mehreren Dachsegmenten (Danke @rapahl).

---

## [3.16.12] - 2026-04-20

### Bugfixes

- **fix(prognosen): 0.0 kWh ab Tag 3 bei icon_d2 Wettermodell** — Modelle mit kurzem Horizont (z.B. icon_d2 = 2 Tage) lieferten ab Tag 3 keine Daten. Neuer Fallback: Primary-Modell + best_match parallel abrufen und Tage mergen (analog zur GTI-Kaskade).
- **fix(prognosen): Verbleibend-Werte pro Quelle in KPI-Matrix** — Die Verbleibend-Zeile zeigt jetzt OM/EEDC/Solcast-Werte (Tagesprognose − bisheriger IST) statt nur den kombinierten IST-Wert.
- **fix(solcast): Entity-Mapping für "übermorgen"** — `_ubermorgen` und `_uebermorgen` als Aliase für `tag_3` im Suffix-Mapper ergänzt.
- **fix(prognosen): Solcast p90-Konfidenzband im Stundenprofil entfernt** — Der halbtransparente "Schatten" im Chart sorgte für Verwirrung.
- **fix(prognosen): Σ-Summenzeile im Stundenvergleich sticky** — Die Summenzeile ist jetzt am unteren Rand fixiert und bleibt beim Scrollen sichtbar.

---

## [3.16.11] - 2026-04-19

### Bugfixes

- **fix(solcast): Discovery filtert auf kWh + schließt "verbleibend" aus** — `prognose_verbleibende_leistung_heute` konnte statt `prognose_heute` gematcht werden (beide enden auf `_heute`). Jetzt: nur Sensoren mit `unit_of_measurement=kWh` und ohne "verbleibend"/"remaining" im Namen.
- **fix(prognosen): IST-Berechnung schließt strompreis/netzbezug/einspeisung aus** — `komponenten_kwh` enthält auch `strompreis` (ct/kWh), `netzbezug` und `einspeisung`. Diese verfälschten den IST-Wert im Genauigkeits-Tracking und Lernfaktor massiv (z.B. 244 kWh statt 40 kWh wegen `strompreis=202.95` ct).

---

## [3.16.10] - 2026-04-19

### Bugfixes

- **fix(solcast): Discovery via /api/states Suffix-Pattern statt Entity Registry** — Die Entity Registry API ist über die HA Supervisor REST API nicht verfügbar (404), und `unique_id`s können sich bei Integrations-Updates ändern. Neuer Ansatz: `/api/states` laden und Solcast-Entities per Suffix-Pattern matchen (`_heute`/`_today`, `_morgen`/`_tomorrow`, `_tag_N`/`_day_N`). Robust gegenüber Spracheinstellungen, Umbenennungen und unique_id-Änderungen.
- **fix(live): Redundanten Momentwerte-Text über Energiefluss entfernt** — Refresh-Takt wird bereits oben rechts angezeigt (5s), der separate Text war zudem falsch (~30s).

---

## [3.16.9] - 2026-04-19

### Bugfixes

- **fix(solcast): Auto-Discovery sprachunabhängig via Entity Registry** — Solcast-Sensoren werden jetzt über die HA Entity Registry (`unique_id`) aufgelöst statt über hardcodierte `entity_id`s. Funktioniert unabhängig von der HA-Spracheinstellung (`prognose_heute` vs. `vorhersage_heute` vs. `forecast_today`).
- **fix(energieprofil): aggregate_day() überschreibt Prognose-Felder nicht mehr** — `aggregate_day()` löschte die gesamte `TagesZusammenfassung` und verlor dabei `pv_prognose_kwh`, `sfml_prognose_kwh` und `solcast_*_kwh`. Jetzt werden die Prognose-Felder vor dem DELETE gerettet und nach dem INSERT wiederhergestellt. Dadurch wird der Lernfaktor und das Genauigkeits-Tracking erstmals korrekt befüllt.

### Neu

- **Prognosen-Abweichungen inline mit Farbskala** — Stundenvergleich + 7-Tage-Vergleich zeigen die Abweichung direkt neben jedem Prognosewert (OM, EEDC, Solcast) mit Pfeil (↑/↓) und Farbskala (grün <15%, gelb 15–30%, rot >30%). Bei Zukunfts-Tagen ohne IST wird der Mittelwert aller Prognosen als Referenz verwendet.

---

## [3.16.8] - 2026-04-19

### Bugfixes (Code-Audit v3.16.3–v3.16.7)

- **fix(prognosen): bestPrognose-Berechnung lieferte `false` statt Zahl** — Δ-Spalte im Stundenvergleich zeigte falsche Werte wenn Solcast nicht aktiv
- **fix(prognosen): 0-as-falsy bei eedc_*_kwh und Genauigkeit** — 0.0 kWh Prognose wurde als `None` angezeigt statt als 0
- **fix(prognosen): asyncio.gather mit Fehler-Isolation** — Ein API-Timeout (OpenMeteo/Solcast) crashte den gesamten Prognosen-Tab, jetzt werden verfügbare Daten angezeigt
- **fix(sensor-mapping): `?force=true` DELETE-Parameter implementiert** — War nur in Fehlermeldung referenziert, Query-Parameter fehlte

### Neu

- **API: `POST /api/energie-profil/reaggregate-heute`** — Manuelle Neu-Aggregation des heutigen Tages (nach Bugfixes oder Konfigurationsänderungen)

---

## [3.16.7] - 2026-04-19

### Bugfix

- **fix(energieprofil): Börsenpreis-Kontamination in pv_kw behoben** — Der `strompreis`-Schlüssel aus den Tagesverlauf-Daten (ct/kWh) wurde fälschlich als PV-Erzeugung (kW) in `pv_kw` aufaddiert. Betroffen: IST-Stundenprofil im Prognosen-Tab (falsche Werte nachts), `komponenten_kwh` in TagesZusammenfassung, Lernfaktor-Berechnung. Fix: `strompreis` und `haushalt` aus der generischen Energiefluss-Aggregation ausgeschlossen.

---

## [3.16.6] - 2026-04-19

### Solcast PV Forecast — Stabiles Release

Zusammenfassung von v3.16.4 + v3.16.5 (Pre-Releases) als stabile Version.

- **Neuer Tab „Prognosen"** in Aussichten: OpenMeteo / EEDC (kalibriert) / Solcast / IST im Vergleich
- **Solcast HA-Integration**: Ein Toggle im Sensor-Mapping Wizard — automatische Erkennung der Solcast-Sensoren (BJReplay)
- **Solcast API-Zugang**: Für Standalone-Nutzer (Free/Paid Key), L1/L2-Cache überlebt Neustarts
- **KPI-Matrix**: Heute/Morgen/Übermorgen × alle Quellen mit VM/NM-Split
- **Stundenprofil-Chart**: GTI-basiertes OpenMeteo, EEDC (kalibriert), Solcast, IST mit p10/p90-Band
- **24h + 7-Tage-Vergleichstabelle**: Mit Differenzen und Wetter-Symbolen
- **Genauigkeits-Tracking**: MAE-Berechnung über historische IST-Daten
- **Integrations-Vorschlag**: Erläuterung der Nutzung in Live, Kurzfristig, Lernfaktor, Finanzen
- **Statusmeldungen**: Kontextbezogene Hinweise (Tageslimit, Auth, HA nicht erreichbar)
- **Sicherheit**: DELETE-Schutz für sensor_mapping mit aktiven Live-Sensoren
- **Refactoring**: Prognosen-Code in eigene prognosen.py ausgelagert
- **DB-Migration**: 3 neue Spalten in TagesZusammenfassung (solcast_prognose_kwh, p10, p90)

---

## [3.16.5] - 2026-04-19 (Pre-Release)

### Solcast PV Forecast — Sensor-Mapping Wizard

- **Ein-Klick-Aktivierung**: Toggle „Solcast PV Forecast" im Sensor-Mapping Wizard — automatische Erkennung der Solcast HA-Integration (BJReplay), kein manueller DB-Eintrag nötig
- **7-Tage-Prognose aus HA-Sensoren**: Heute + Morgen + Tag 3–7 direkt als Sensor-States gelesen (standardisierte Entity-IDs)
- **Zusammenfassung**: Solcast-Sektion im Wizard-Abschluss sichtbar
- **Status-Hinweise**: Kontext-bezogene Meldungen wenn Sensoren noch nicht geladen oder HA nicht erreichbar

---

## [3.16.4] - 2026-04-19

### Solcast PV Forecast — Prognosen-Vergleich (Evaluierung)

- **Neuer Tab „Prognosen"** in Aussichten: Evaluierungs-Cockpit für das Zusammenspiel von OpenMeteo und Solcast
- **Solcast-Service**: API-Zugang (Free/Paid) und HA-Sensor-Anbindung mit L1/L2-Cache (überlebt Neustarts)
- **EEDC-Prognose**: Kalibrierter OpenMeteo-Wert (×Lernfaktor) als dritte Vergleichsspalte
- **KPI-Matrix**: OpenMeteo / EEDC / Solcast / IST × Heute / Morgen / Übermorgen mit VM/NM-Split
- **Stundenprofil-Chart**: 4 Linien (IST grün, EEDC orange, Solcast blau, OpenMeteo gelb) + Solcast p10/p90-Band
- **24h-Vergleichstabelle**: Stündliche Werte mit Differenzen (Δ IST–Prognose)
- **7-Tage-Vergleichstabelle**: Alle Quellen mit Solcast-Konfidenzband
- **Genauigkeits-Tracking**: MAE-Berechnung (OpenMeteo vs. Solcast) aus historischen TagesZusammenfassungen
- **Statusmeldungen**: Kontextbezogene Hinweise bei Tageslimit, fehlender Config, HA nicht erreichbar
- **Integrations-Vorschlag**: Erläuterung der geplanten Einbindung in Live, Kurzfristig, Lernfaktor, Finanzen
- **Refactoring**: Prognosen-Code aus aussichten.py in eigene prognosen.py ausgelagert (−360 Zeilen)
- **DB-Migration**: 3 neue Spalten in TagesZusammenfassung (solcast_prognose_kwh, p10, p90)

---

## [3.16.3] - 2026-04-18

### Verbesserungen (Community-Feedback)

- **Sensor-Mapping**: Strompreis-Sensoren mit Einheiten wie `ct`, `Cent`, `EUR/MWh`, `€` werden jetzt akzeptiert (bisher nur `EUR/kWh`, `ct/kWh`, `€/kWh`)
- **Tagesverlauf**: EUR/MWh-Sensoren werden korrekt nach ct/kWh normalisiert (×0.1)
- **PDF-Deckblatt**: MaStR-Feld durch Geo-Koordinaten ersetzt, Schriftgrößen für Adresse und Komponentenliste vergrößert
- **Energiefluss**: Leistungsanzeige bleibt bis 9.999 W in Watt, Umschaltung auf kW erst ab 10 kW

---

## [3.16.2] - 2026-04-18

### Infothek — Investitionsformular verschlanken (Etappe 3.6)

- **Stammdaten-Felder entfernt**: Gerätedaten (`stamm_*`), Ansprechpartner (`ansprechpartner_*`) und Wartungsvertrag (`wartung_*`) aus dem Investitionsformular entfernt — alle Daten werden jetzt über die Infothek verwaltet
- **Infothek-Verknüpfungen im Formular**: Beim Bearbeiten einer Investition werden verknüpfte Infothek-Einträge als kompakte Liste mit Kategorie und Direktlink angezeigt
- **PDF-Jahresbericht bereinigt**: Gerätedaten/Ansprechpartner/Wartung-Sektionen entfernt (Anlagendokumentation-PDF nutzt bereits ausschließlich Infothek-Daten)
- **Migrations-Banner bleibt**: Nutzer mit Altdaten sehen weiterhin den Hinweis „Stammdaten in Infothek übernehmen?" in der Investitions-Übersicht
- **Dokumentation aktualisiert**: ARCHITEKTUR.md (Infothek-Datenmodell im ER-Diagramm + Tabellen), HANDBUCH_INFOTHEK.md (Migrations-Hinweis + Formular-Verknüpfungen)

---

## [3.16.1] - 2026-04-18

### Bugfix

- **Wetter-Widget**: Strompreis-Sensor (EPEX Börsenpreis, kat=preis) wurde fälschlich als „Sonstige"-Verbrauch interpretiert — ct/kWh-Werte erschienen als ~11 kW graue Fläche ab 02:00 Uhr im Tagesverlauf-Chart

---

## [3.16.0] - 2026-04-18

### Feature — Dynamischer Strompreis: Sensor-Mapping + EPEX-Börsenpreis (Joachim-xo)

- **Sensor-Mapping Wizard**: Neues optionales Feld „Strompreis (dynamischer Tarif)" unter Basis-Sensoren — Tibber, aWATTar, EPEX oder eigener Template-Sensor zuordnen
- **Börsenpreis für alle**: EPEX Day-Ahead Preise (DE/AT) werden automatisch via aWATTar API geholt — als Overlay im Tagesverlauf, auch ohne eigenen Sensor
- **Tagesverlauf-Overlay**: Eigener Sensor → „Strompreis", kein Sensor → „Börsenpreis (EPEX)" — pinke Linie auf sekundärer Y-Achse
- **MQTT-Support**: Topic `eedc/{id}/live/strompreis_ct` für Standalone-Docker-Nutzer

### Feature — Stündliche Strompreis-Mitschrift im Energieprofil (Vorbereitung)

- **Zwei getrennte Preisfelder** im TagesEnergieProfil: `strompreis_cent` (Endpreis aus HA-Sensor) + `boersenpreis_cent` (EPEX, immer befüllt)
- **Tagesaggregation**: Börsenpreis Ø/Min, Anzahl negativer Preis-Stunden, Einspeisung bei negativem Börsenpreis (§51 EEG Vorbereitung)
- Datensammlung als Grundlage für mögliche spätere Features (Monatsvorschlag, Negativpreis-Analyse)

### Fix — Strompreis-Overlay las falsches Feld

- Tagesverlauf suchte `entity_id` statt `sensor_id` im Sensor-Mapping → Overlay konnte nicht funktionieren

---

## [3.15.8] - 2026-04-17

### Feature — Tagesverlauf: Einspeisung + Strompreis-Overlay (Rainer-Feedback)

- **Einspeisung als eigene Serie**: Netz-Serie aufgeteilt in Netzbezug (rot, oben) und Einspeisung (cyan, unten) mit eigenem Legendeneintrag
- **Strompreis-Overlay**: Sekundäre Y-Achse (ct/kWh) mit Step-Linie — zeigt EPEX/Tibber-Preis im Tagesverlauf, wenn ein Strompreis-Sensor im Sensor-Mapping konfiguriert ist
- **Einheiten-Normalisierung**: EUR/kWh-Sensoren werden automatisch in ct/kWh konvertiert
- Beide Pfade (HA + MQTT) angepasst

### Fix — Lernfaktor robuster bei Wetterwechseln (Rainer-Feedback)

- **Produktionsgewichtet**: Σ(IST) / Σ(Prognose) statt Median der Tages-Ratios — sonnige Tage dominieren automatisch, bewölkte Phasen verzerren den Faktor nicht mehr nach unten

### Fix — Backfill: Stillgelegte Investitionen zeitraumgerecht (MartyBr)

- **Backfill** nutzte `aktiv_jetzt()` statt `aktiv_im_zeitraum()` — stillgelegte Investitionen wurden komplett ignoriert, auch für historische Tage VOR dem Stilllegungsdatum
- Jetzt: Pro Tag wird geprüft ob die Investition an dem konkreten Tag aktiv war

### Verbesserung — PDF-Farbstreifen einheitlich

- **Finanzbericht**: Streifen von 6mm auf 1.5mm (wie Anlagendokumentation)
- **Jahresbericht + Infothek**: Farbstreifen über base.html + styles.css ergänzt
- Alle 4 Berichte haben jetzt den gleichen subtilen 1.5mm-Streifen

---

## [3.15.7] - 2026-04-17

### Fix — Stillgelegte Komponenten in Gesamt-kWp (MartyBr Forum #308)

- **Cockpit kWp-Summe**: Stillgelegte/deaktivierte PV-Module und BKW werden nicht mehr zur Gesamtleistung addiert
- **Komponenten-Flags**: Speicher, Wärmepumpe, E-Mobilität und BKW-Sektionen respektieren jetzt Stilllegungsdatum
- **Sensor-Mapping gesamt_kwp**: Nur noch aktive Module in der kWp-Summe

### Fix — WetterWidget Tooltip zeigt irrelevante Kategorien (av3 Forum #311)

- **Tooltip**: Verbrauchskategorien (Wallbox, WP, Sonstige) werden nur angezeigt, wenn entsprechende Investitionen existieren
- **Legende**: Verbrauchs-Kategorien als gefüllte Rechtecke statt Linien-Symbole (passend zur Flächendarstellung)

---

## [3.15.6] - 2026-04-17

### Verbesserung — PDF-Anlagenbericht nach Rainer-Feedback

- **EEDC-Vermerk entfernt**: Titelseite zeigt nur noch "Stand DD.MM.YYYY" statt redundantem EEDC-Branding
- **Kompaktere Komponenten**: Zeilenabstand in Komponenten-Blöcken reduziert
- **Hinweis-Box entfernt**: "Keine Komponenten-Akte verknüpft" (Beta-Phase vorbei)
- **Logo-Fallback**: EEDC-Logo wird angezeigt wenn kein eigenes Anlagenfoto hochgeladen ist
- **PV-Komponenten dedupliziert**: Bei n:m-Verknüpfung wird jede Komponente nur einmal angezeigt, mit "Gilt für"-Hinweis (z.B. "alle Modulfelder" oder "Süddach")
- **Farbstreifen subtiler**: Durchgehend dünne 1.5mm-Linie statt dominantem 6mm-Streifen
- **Logo einzeilig**: "ENERGIE EFFIZIENZ DATA CENTER" auf einer Zeile (SVG + PNG aktualisiert)
- **Duplicate Macro entfernt**: `komponente_block` war im Template doppelt definiert

---

## [3.15.5] - 2026-04-16

### Fix — PDF-Download Mobile 401 Unauthorized

- **PDF-Download auf Mobile (HA Companion App)**: `target="_blank"` Links verloren den Ingress-Auth-Token → 401 Unauthorized. PDFs werden jetzt per `fetch()` im aktuellen Auth-Kontext geladen und als Blob-Download angeboten. Spinner während der PDF-Generierung.

---

## [3.15.4] - 2026-04-16

### Fix — Anlagendokumentation PDF + Foto-Upload

- **PDF Jinja-Fehler behoben**: `TemplateSyntaxError` bei Anlagendokumentation — `elif`-Block stand nach `else` im Template (ungültig in Jinja). Reihenfolge korrigiert.
- **Anlagenfoto verschwindet nach Upload**: HEAD-Request feuerte nach jedem Upload erneut und setzte das Foto bei Timing-Problemen zurück. Check läuft jetzt nur noch beim Öffnen des Dialogs.

---

## [3.15.3] - 2026-04-16

### Perf — N+1 Queries, Code-Splitting, Konstanten-Bereinigung

- **Backend: N+1 Queries eliminiert**: 6 Dashboard-Endpoints (`investitionen.py`) von Loop-Queries auf Batch-Queries (`WHERE investition_id IN`) umgestellt. E-Auto, Wärmepumpe, Speicher, Wallbox (3 Schleifen → 1 Query), BKW und Monatsdaten-by-Month.
- **Backend: aktueller_monat.py**: 5 sequentielle InvestitionMonatsdaten-Queries (Speicher/WP/EMob/BKW/Sonstiges) zu einer Batch-Query zusammengefasst.
- **Backend: aussichten.py**: Shared Helper `_lade_anlage_mit_pv()` extrahiert — 3 Forecast-Endpoints sparen je 3 duplizierte Queries (Anlage + PV + BKW → 1 kombinierte Query).
- **Frontend: React.lazy Code-Splitting**: 33 Seiten als Lazy-Imports, nur LiveDashboard (Startseite) bleibt eager. Vite erzeugt separate Chunks pro Route — Initial-Bundle deutlich kleiner.
- **Frontend: Community-Benchmark zentralisiert**: `getBenchmark()` wird einmal im Parent geladen und als Props an alle 6 Tabs weitergereicht. Kein Re-Fetch bei Tab-Wechsel.
- **Frontend: Duplizierte Konstanten bereinigt**: `REGION_NAMEN` (4×), `MONAT_NAMEN`/`MONAT_KURZ` (4×) zentralisiert in `lib/constants.ts`.

### Fix

- **Daten-Checker: Dienstwagen ausgenommen**: E-Autos mit `ist_dienstlich`-Flag werden im Daten-Checker komplett übersprungen — keine PV-Ladungs-, Alternativkosten- oder Anschaffungskosten-Checks mehr.

---

## [3.15.2] - 2026-04-16

### Feat — Infothek N:M Verknüpfung + Komponenten-Akte am Investment (#121)

- **Mehrfachverknüpfung Infothek ↔ Investitionen (N:M)**: Ein Datenblatt (z.B. „Trina Vertex S 430Wp") kann jetzt mit mehreren Investments gleichzeitig verknüpft werden — statt für 6 PV-Strings 6 identische Einträge zu pflegen. Neue Junction Table `infothek_investition`, bestehende 1:1-Verknüpfungen werden automatisch migriert. Im Formular ersetzt eine Checkbox-Liste das bisherige Single-Select-Dropdown. API bleibt rückwärtskompatibel (`investition_id` weiterhin akzeptiert).
- **Komponenten-Akte direkt am Investment**: Kontextabhängiger Button in der Investitions-Übersicht: „Komponenten-Akte anlegen" (0 Einträge), „Komponenten-Akte öffnen" (1 Eintrag), Dropdown-Liste mit Direktlinks (N Einträge) + „Weitere verknüpfen". Quick-Create öffnet ein Modal mit vorausgefüllter Kategorie und Verknüpfung.
- **„In Anlagendokumentation anzeigen" Flag**: Neues Häkchen pro Infothek-Eintrag (Default: an). Steuert, ob der Eintrag in der Anlagendokumentation (PDF) erscheint. Das Infothek-Dossier zeigt weiterhin immer alles, Jahres- und Finanzbericht sind nicht betroffen.
- **Infrastruktur-Abschnitt in Anlagendokumentation**: Infothek-Einträge der Kategorie „Komponente / Datenblatt" ohne Investment-Verknüpfung (z.B. Zähler, Zählerschränke, Verkabelung) bekommen eine eigene Seite im PDF.

### Fix

- **Wallbox-Dashboard: Ladevorgänge immer 0**: Sensor-Mapping speichert `ladevorgaenge` in den Wallbox-Monatsdaten, aber das Dashboard las nur E-Auto-Monatsdaten. Fix: beide Quellen aggregieren (Wallbox primär, E-Auto als Fallback für manuelle Altdaten).
- **Infothek Datei-Label**: Zeigte „max. 3", tatsächliches Limit ist 15. Dateigröße (bis 10 MB) ergänzt.
- **Stromzähler-Placeholder erweitert**: Strom-Zähler-Bezeichnung zeigt jetzt Beispiele für WP-Strom, Wallbox, Haushalt als Placeholder-Text.

---

## [3.15.1] - 2026-04-16

### Feat — Auto-Vollbackfill aus HA Long-Term Statistics

- **Erster Monatsabschluss nach Upgrade befüllt automatisch die komplette HA-History** ins Energieprofil. Bisher wurde nur der Monat des jeweiligen Monatsabschlusses per `backfill_range` aufgefüllt — die HA Long-Term Statistics (Jahre zurück) wurden nicht angetastet. Wer auf v3.1.x+ upgegradet hatte, blieb folglich ohne Energieprofil-Historie aus der Zeit vor dem Upgrade. Bisher gab es nur den manuellen „Vollständig nachberechnen"-Button im Sensor-Mapping-Wizard (v3.12.1) — wer den nicht aktiv geklickt hat, hatte schlicht nichts. Mit v3.16.0 läuft der Vollbackfill jetzt **einmalig pro Anlage** automatisch im Hintergrund mit, sobald der erste Monatsabschluss nach dem Upgrade gespeichert wird (manuell ODER per Scheduler — beide Pfade durchlaufen `_post_save_hintergrund`).
- **Neues Anlage-Feld `vollbackfill_durchgefuehrt`**: Wird gesetzt, sobald entweder der manuelle Wizard-Button oder der Auto-Lauf durch ist (Erfolg oder Fehler). Damit greift der Auto-Vollbackfill garantiert nur einmal pro Anlage und führt auch bei defekter HA-DB nicht zu Endlos-Retries. Beim **Löschen der Energieprofil-Rohdaten** (Single-Anlage und Bulk-Endpoint) wird das Flag zurückgesetzt → der nächste Monatsabschluss zieht die History erneut nach. Das Feld ist server-intern, nicht über die Anlage-API editierbar.
- **Bestandsdaten-Heuristik** in der DB-Migration: Anlagen mit mehr als 30 Tagen Energieprofil-Historie werden bei der Migration auf v3.16.0 direkt mit `vollbackfill_durchgefuehrt = True` markiert. So bekommt z.B. Rainer (578 Tage) keinen überraschenden Multi-Jahres-Backfill beim ersten Scheduler-Lauf — wer das explizit will, kann den Wizard-Button weiter manuell anstoßen.
- **Verhalten in Edge-Cases**: HA Statistics nicht verfügbar → Flag wird trotzdem gesetzt, kein Retry. Keine validen Sensoren konfiguriert → Flag wird trotzdem gesetzt. Frische Installation ohne Profile-Daten → Flag bleibt False, erster Monatsabschluss zieht die komplette History. Wizard-Vollbackfill bereits gelaufen → Flag ist True, kein erneuter Auto-Lauf.

### Fix

- **Infothek-Kategorie „Garantie" → „Komponente / Datenblatt"**: Das Label in der Infothek-UI stimmte nicht mit dem Verweis in der Anlagendokumentation überein. Nutzer, die dem Hinweis „Kategorie Komponente / Datenblatt" folgten, fanden die Kategorie nicht, weil sie im Frontend noch „Garantie" hieß. Auslöser: Rainer.

### Maintenance

- Neue gemeinsame Helper-Funktion `resolve_and_backfill_from_statistics()` in `backend/services/energie_profil_service.py` mit `BackfillResult`-Dataclass. Vereint die zuvor ~50 Zeilen duplizierte Orchestrierungs-Logik (Sensor-Discovery, ungültige Sensoren filtern, frühestes Datum aus HA Statistics ermitteln, Backfill auslösen) zwischen dem manuellen Vollbackfill-Endpoint und dem neuen Auto-Vollbackfill im Background-Task. Beide Call-Sites mappen den `BackfillResult.status` ("ok"/"ha_unavailable"/"no_sensors"/"no_valid_sensors"/"earliest_unknown"/"empty_range") auf ihre eigene Fehlerbehandlung (HTTPException vs. Log-Warnung).
- `_post_save_hintergrund` lädt die `Anlage` jetzt nur noch einmal (vorher: separate Sessions für Rollup und Auto-Vollbackfill, zwei SELECTs auf jedem Save). Closing-Month-Backfill, Rollup und Auto-Vollbackfill teilen sich dieselbe DB-Session.
- Konstante `VOLLBACKFILL_BESTAND_SCHWELLE_TAGE = 30` in `backend/core/database.py`.

---

## [3.15.0] - 2026-04-15

### Feat — Anlagendokumentation & Finanzbericht (Issue #121 Phase 4, Beta)

- **Neuer zentraler „Dokumente"-Dialog pro Anlage**: Der bisherige Einzel-Button auf der Anlagen-Seite wird abgelöst durch einen **Dokumente**-Button (orangefarbenes Ordner-Icon), der einen Download-Hub mit allen verfügbaren PDF-Dokumenten öffnet. Aktuell vier Karten: **Jahresbericht**, **Infothek-Dossier**, **Anlagendokumentation** (Beta) und **Finanzbericht** (Beta). Die beiden neuen Dokumente sind mit einem amber-farbenen „Beta"-Badge gekennzeichnet und verlinken direkt auf Issue #121 für Feedback.
- **Anlagendokumentation (Beta)** — neues PDF im V4-Layout mit Urkunden-Charakter: Titelseite mit Anlagenfoto, gesperrter Headline, großem Anlagennamen, Meta-Zeile (Leistung / Inbetriebnahme / MaStR) und Komponenten-Übersicht. Folgeseiten mit **Hybrid-Gruppierung**: alle PV-Modulfelder werden gesammelt auf einer Seite gerendert, alle anderen Investitionstypen (Wechselrichter, Speicher, Wärmepumpe, Wallbox, E-Fahrzeug, Balkonkraftwerk, Sonstiges) bekommen eine eigene Folgeseite. Unter der Technik jeder Investition wird der Komponenten-Akte-Block aus verknüpften Infothek-Einträgen der Kategorie „Komponente / Datenblatt" gerendert — mit allen gepflegten Feldern (Hersteller, Seriennummer, Garantie, Prüftermine, Datenblatt-URL), mehrzeiligen Freitext-Blöcken (Technische Daten, Garantie-Bedingungen, Sonstige Verträge) und der Liste angehängter Dateien inkl. Beschreibung. Ist keine Komponenten-Akte verknüpft, zeigt die Seite eine freundliche Hinweis-Box mit dem Pflege-Pfad. **Keine Geldbeträge** — die Anlagendokumentation ist bewusst für Versicherung, Nachlass und Archiv konzipiert und kann ohne Finanzbedenken weitergegeben werden.
- **Finanzbericht (Beta)** — neues PDF mit allen monetären Kennzahlen zur Anlage: Investitions-Tabelle mit Bezeichnung, Kategorie, Inbetriebnahme, Kosten, Alternativ-Kosten und Jahres-Ersparnis je Investition; Summenzeile; KPI-Block mit Amortisations-Prognose, Differenz zum Alt-Szenario und Netto-Kosten nach Förderung; gruppierte Sektionen **Förderungen**, **Versicherung** und **Steuerdaten** aus den jeweiligen Infothek-Kategorien (`foerderung`, `versicherung`, `steuerdaten`) mit allen Einzel-Einträgen. Abgeschlossen mit einem Vertraulichkeits-Hinweis.
- **Anlagenfoto am Anlage-Modell**: Neuer Upload-Bereich in der Anlage-Stammdaten-Form — Drag & Drop oder Klick, Vorschau als 128 × 128-Thumbnail, Ersetzen und Entfernen. Die bestehende Bildpipeline aus der Infothek wird wiederverwendet (EXIF-Rotation, HEIC→JPEG, Resize auf ~500 kB, 200 × 200-Thumbnail). Gespeichert wird in einer neuen Tabelle `anlage_foto` (1:1 zu `anlagen`, Cascade-Delete). Ein Foto pro Anlage — ein neues Foto überschreibt das alte. Genutzt wird es auf der Titelseite der Anlagendokumentation; ohne Foto bleibt die Titelseite aufgeräumt ohne Platzhalter.
- **Neue API-Routen** unter `/api/anlagen/{id}/foto` (POST/GET/GET/thumb/DELETE) und unter `/api/dokumentation/anlagendokumentation/{id}` sowie `/api/dokumentation/finanzbericht/{id}`. Die beiden Dokumentations-Routen sind **WeasyPrint-only** — bei `PDF_ENGINE=reportlab` liefern sie `HTTP 503` mit klarem Hinweistext („Im HA-Add-on in der Konfiguration umschaltbar, im Standalone-Docker via Umgebungsvariable"). Begründung: Das V4-Layout (mehrseitige Komponenten-Blöcke, seitenübergreifende 3-Farben-Leiste, CSS-Gradients, `position: fixed`) ist auf WeasyPrint + Pango/Cairo ausgelegt und im reportlab-Builder nicht realistisch abbildbar.

### Beta-Hinweis & Feedback-Einladung

Die beiden neuen Dokumente sind bewusst als **Beta** markiert und werden über Issue [#121](https://github.com/supernova1963/eedc-homeassistant/issues/121) iteriert. Die Grundstruktur ist freigegeben (V4-Layout von rapahl approved, Hybrid-Gruppierung und B1-Datenquelle abgestimmt), aber Feld-Auswahl und Layout-Details werden nach Community-Praxis-Tests verfeinert. Feedback bitte konkret: „X fehlt, weil Y beim Ausfüllen/Drucken nicht passt". Das Fundament (Komponentenakte) aus v3.14.0 bleibt stabil, strukturelle Änderungen sind damit zukünftig reine Builder-/Template-Anpassungen — keine Datenmodell-Brüche.

### Maintenance

- Neuer PDF-Builder-Modul: `backend/services/pdf/builders/anlagendokumentation.py` und `backend/services/pdf/builders/finanzbericht.py`, Templates analog unter `backend/services/pdf/templates/`.
- Seitenübergreifende 3-Farben-Leiste via `position: fixed` (WeasyPrint repliziert fixed-Elemente auf jeder physischen Seite) und `@page { margin: 22mm 22mm 22mm 38mm }` — damit starten auch automatisch umgebrochene Überlauf-Seiten auf Höhe des Streifen-Oberrands statt am Papier-Rand.
- Neue Frontend-Komponenten: `AnlagenfotoSection.tsx`, `DokumentationsDialog.tsx`. Bestehender `ApiClient.upload()` um optionalen `extraFields`-Parameter erweitert (wurde für die Datei-Beschreibungen in v3.14.0 bereits vorbereitet).

---

## [3.14.0] - 2026-04-15

### Fix

- **Historische Aggregate blenden deaktivierte Investitionen nicht mehr aus (#123)**: Bis jetzt haben ~32 Call-Sites im Backend (Monatsdaten-Aggregation, Cockpit-KPIs, PDF-Jahresbericht, Nachhaltigkeit, Social-Text, PV-Strings-Vergleich, Export-Routen) Investitionen strikt mit `aktiv == True` gefiltert. Folge: Sobald ein Nutzer eine Komponente deaktiviert hat (z.B. nach WR-Upgrade oder Verkauf), sind ihre historischen Werte **rückwirkend und stillschweigend** aus allen Auswertungen verschwunden — Rohdaten in `InvestitionMonatsdaten` blieben zwar erhalten, wurden aber nicht mehr summiert. Aufgefallen ist das bei MartyBr (community.simon42.com #297), der seinen zweiten WR in Betrieb genommen hat. Fix in zwei Richtungen: (1) Alle historischen Auswertungen laden Investitionen jetzt ohne `aktiv`-Filter, sodass vergangene Werte erhalten bleiben. (2) Neues optionales Feld **Stilllegungsdatum** auf jeder Investition als finaler Endmarker — bis dahin zählt die Komponente für Historie und Live/Prognose, danach nur noch für Historie. Live-/Prognose-Queries (Solar-Forecast, Live-Dashboard, Sensor-Mapping, MQTT-Routing, PVGIS-Refresh) respektieren das neue Feld zusätzlich zum bestehenden `aktiv`-Flag. Empfehlung für Gerätewechsel: neue Investition anlegen (Anschaffungsdatum = Umbautag) + Stilllegungsdatum auf alter Investition setzen (nicht mehr deaktivieren).

### Feat

- **Infothek-Komponentenakte — Garantie-Kategorie zum vollwertigen Datenblatt ausgebaut (#121)**: Erste testbare Beta der Komponentenakte für die kommende Anlagendokumentation (Phase 4). Die bestehende Kategorie `garantie` wird als **„Komponente / Datenblatt"** umgelabelt und um acht Felder erweitert: Seriennummer, Einbau-Datum, Installations-Firma, Letzte/Nächste Prüfung, Link zum Hersteller-Datenblatt sowie zwei mehrzeilige Freitextfelder **„Technische Daten"** (typ-spezifisch — von Kabelquerschnitt bis COP) und **„Sonstige zugehörige Verträge / Dokumente"**. Der interne Key bleibt `garantie`, bestehende Einträge sind unverändert gültig, keine DB-Migration nötig. Neuer Feld-Typ `text` wird im Formular-Renderer als `<textarea>` dargestellt. **Datei-Upload**: Limit von 3 auf 15 Dateien pro Eintrag erhöht, PDF-Größe von 5 auf 10 MB. Pro Datei kann jetzt eine optionale **Beschreibung** mitgegeben werden (Staging-Queue im Upload-Widget, Beschreibung später unter dem Thumbnail sichtbar). Damit ist das Fundament gelegt, auf dem der Anlagendokumentations-Builder verknüpfte Komponenten-Daten je Investition rendern wird. Feedback aus der Praxis wird über Issue #121 gesammelt — bitte testen und fehlende/überflüssige Felder melden.
- **Stilllegungsdatum in der Investitions-Form**: Neuer DatePicker unter dem Anschaffungsdatum in allen Investitions-Typen (E-Auto, WP, Speicher, Wallbox, WR, PV-Module, Balkonkraftwerk, Sonstiges). Validierung: nicht vor dem Anschaffungsdatum. In der Investitions-Übersicht zeigt ein neuer amber-farbener **Stillgelegt**-Badge den Zustand an (mit Tooltip `Stillgelegt seit YYYY-MM-DD`).
- **MonatsdatenForm-Editor zeigt historisch aktive Komponenten**: Beim Bearbeiten eines Monats sieht man jetzt alle Investitionen, die in diesem Monat (mindestens teilweise) in Betrieb waren — auch inzwischen stillgelegte. Vorher waren die für historische Nachträge unsichtbar.

### Maintenance

- Neues Helper-Modul `backend/utils/investition_filter.py` mit wiederverwendbaren Filter-Funktionen `aktiv_jetzt()`, `aktiv_im_zeitraum()`, `aktiv_im_monat()`, `aktiv_im_jahr()` und Model-Methoden `Investition.ist_aktiv_an()`, `ist_aktiv_im_zeitraum()`, `ist_aktiv_im_monat()` für In-Memory-Checks in Aggregations-Loops.
- `aussichten.py`-Langfristbericht: historische Aggregation vs. Prognose-Basis sauber getrennt — Prognose-kWp kommt nur aus aktuell aktiven PV-Modulen, historische Werte aus allen je vorhandenen.
- JSON-Backup-Export/Import persistiert Stilllegungsdatum.
- DB-Migration `investitionen.stilllegungsdatum DATE` (SQLite + MariaDB/MySQL), rückwärtskompatibel — bestehende Installationen behalten ihr Verhalten, solange kein Datum gesetzt ist.

### Bekannter Folgepunkt

- **ROI-Dashboard zeitanteilige Gewichtung**: Der eigentliche Bug (stillschweigend falsche historische Zahlen) ist in v3.14.0 behoben. Offene Verfeinerung: Das ROI-Modell geht aktuell von "Investition läuft das ganze Jahr" aus — bei mitten im Jahr stillgelegten Komponenten wäre eine zeitanteilige Gewichtung sauberer. Nicht dringend; wird in einem späteren Release angegangen.

---

## [3.13.5] - 2026-04-15

### Fix

- **Solarprognose PVGIS: Y-Achsen-Clipping + Multi-String-Anzeige**: Im PVGIS-Prognose-Chart wurde bei Anlagen mit mehreren Strings der höchste Wert oben am Rand abgeschnitten; zusätzlich fehlte die String-übergreifende Summendarstellung in einigen Ansichten. Y-Achse bekommt jetzt automatischen Headroom, Multi-String-Summe wird konsistent dargestellt.

### Maintenance

- `type="button"` auf zwei Icon-Buttons im PVGIS-Dialog ergänzt (verhindert unbeabsichtigtes Form-Submit).

---

## [3.13.4] - 2026-04-14

### Vorbereitung

- **PDF-Engine als HA-Add-on-Option (#121)**: v3.13.3 hatte die neue WeasyPrint-Engine zwar im Hintergrund installiert, aber nur über die Umgebungsvariable `PDF_ENGINE=weasyprint` aktivierbar — was im HA-Add-on-Kontext gar nicht möglich war. v3.13.4 ergänzt eine Add-on-Option `pdf_engine` (Default `reportlab`), die in der HA-UI direkt umgeschaltet werden kann. Standalone-Docker-User können die ENV-Variable wie bisher in `docker-compose.yml` setzen — keine Verhaltensänderung. Default bleibt `reportlab`, am sichtbaren Verhalten ändert sich für niemanden etwas.

---

## [3.13.3] - 2026-04-14

### Vorbereitung

- **PDF-Pipeline-Umstellung (Issue #121) — Substrat-Release**: Die neue PDF-Engine (WeasyPrint + Jinja2 + Matplotlib) wird im Hintergrund installiert und ist über die Umgebungsvariable `PDF_ENGINE=weasyprint` opt-in testbar. Default bleibt `reportlab`, am sichtbaren Verhalten ändert sich für niemanden etwas. Drin sind die neuen Builder für **Jahresbericht** und **Infothek-Dossier** mit einheitlichem Corporate-Design, Matplotlib-Charts (PV-Erzeugung, Energiefluss, Autarkie) und Markdown-Notizen-Rendering. Der bisherige reportlab-Pfad bleibt vollständig erhalten und wird unverändert genutzt. Anlagendokumentation, Finanzbericht und der Dokumenten-Dialog im Frontend folgen in einem späteren Beta-Release, sobald das Layout (V4 — siehe #121) und die Verknüpfung Investition↔Infothek-Eintrag ausreichend mit der Community abgestimmt sind. Native Libs (libpango, fontconfig, fonts-dejavu-core) sind im Dockerfile ergänzt — der HA-Add-on-Build vergrößert sich um wenige MB.

---

## [3.13.2] - 2026-04-13

### Fix

- **MQTT-Export: Icons wurden als Text angezeigt**: Im HA-Export-Tab stand bei jedem Sensor der MDI-Name als Text (`mdi:solar-power`, `mdi:lightning-bolt` …) statt eines echten Icons. Frontend rendert jetzt die tatsächlichen Material-Design-Icons über `@mdi/react` + `@mdi/js` — identisch zur Darstellung in Home Assistant. Auslöser: Rainer.

---

## [3.13.1] - 2026-04-13

### Fix

- **Energieprofil Monat: Zukunftsmonate auch in Selects sperren**: Bis jetzt war nur der ▶-Button für Zukunftsmonate deaktiviert, über die Monats-/Jahres-Dropdowns ließen sich trotzdem Monate in der Zukunft (z.B. Juni 2026 am 13.04.2026) auswählen — mit leerer Anzeige als Folge. Im Monats-Select sind Zukunftsmonate jetzt `disabled`, das Jahres-Select listet nur bis zum aktuellen Jahr, und wer beim Jahreswechsel in einem Zukunftsmonat landet, wird automatisch auf den letzten erlaubten Monat geklemmt. Lücken in der Vergangenheit bleiben sichtbar — die sind Absicht, damit man fehlende Daten überhaupt findet.

---

## [3.13.0] - 2026-04-13

### Feat

- **Energieprofil Etappe 3: Monatsauswertung**: Neuer Sub-Tab "Monat" in Auswertung → Energieprofil mit vollständiger monatlicher Analyse der persistierten Stundenwerte.
  - **Heatmap 24h × N Tage** mit umschaltbarer Metrik (PV / Verbrauch / Netzbezug / Einspeisung / Überschuss-divergent), Hover-Tooltip pro Zelle und Skalen-Legende.
  - **Monats-KPIs (1. Reihe)**: PV-Erzeugung, Verbrauch, Einspeisung, Netzbezug, Autarkie, Eigenverbrauch, Performance-Ratio Ø, Batterie-Vollzyklen-Summe.
  - **Analyse-KPIs (2. Reihe)**: Grundbedarf (Nacht-Ø 0–5 Uhr), Direkt-Eigenverbrauch (PV → Senke ohne Batterie-Umweg), Batterie geladen/entladen/η, PV Best-/Ø-/Schlecht-Tag.
  - **Kategorien-Leiste**: Erzeugung und Verbrauch nach Gruppen — PV-Module, Balkonkraftwerk, Sonstige Erzeuger, Wärmepumpe, Wallbox/E-Auto, Haushalt, Sonstige Verbraucher — mit kWh + Anteil am jeweiligen Gesamt.
  - **Geräte-Tabelle**: Eine Zeile pro Investition (Süddach, Ostdach, WP, Wallbox …) mit Monats-kWh und prozentualem Anteil.
  - **Typisches Tagesprofil**: 24h-Linien-Chart (Ø PV + Ø Verbrauch über den Monat) als Basis für spätere Verbrauchsprognose (Etappe 3b).
  - **Peak-Tabellen**: Top-10 Netzbezug- und Einspeise-Stunden für Tarif-Optimierung und Batterie-Timing.
  - **Monats-Picker** mit Vorher/Nachher-Buttons, Sperre für Zukunftsmonate, Anzeige "X von Y Tagen mit Daten".

  Backend: Neuer Endpoint `GET /api/energie-profil/{anlage_id}/monat?jahr=&monat=&top_n=` aggregiert `TagesEnergieProfil` (stündlich) + `TagesZusammenfassung` (Tages-Rollup inkl. `komponenten_kwh`) zu einer einzigen kompakten Response — Frontend lädt die komplette Monatsansicht in einem Request.

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
