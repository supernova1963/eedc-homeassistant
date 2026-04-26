# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

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
