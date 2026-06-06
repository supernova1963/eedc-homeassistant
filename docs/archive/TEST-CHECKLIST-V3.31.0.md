# Test-Checkliste v3.31.0 — Etappe 4+5 (HA-Statistics als Source-of-Truth)

> Diese Checkliste durchgehen, nachdem das HA-Add-on auf v3.31.0 aktualisiert wurde.
> Sie deckt sowohl die Architektur-Umstellung (Etappe 4: Aggregate aus HA-LTS) als
> auch die drei eliminierten Klimmzüge (Etappe 5: Peak-Werte, Speicher-SoC,
> Strompreis-Stundenmittel) ab.

## Vor dem Update — Snapshot machen

- [ ] **Heutige Tageswerte für eine Test-Anlage notieren**: PV-Erzeugung, Netzbezug, Einspeisung, peak_pv_kw — aus Cockpit oder Energieprofil-Tab
- [ ] **Screenshot vom Monatsbericht-Energieprofil-Tab** eines Tages mit bekannter Drift (z. B. 15.05.2026), als Vorher-Beleg
- [ ] **Drei-Sichten-Vergleich** für denselben Tag dokumentieren (PV-Ertrag aus Genauigkeits-Tracking IST, aus Tages-Energieprofile-Tabelle, aus Monatsbericht-Stunden-Σ) — sind sie heute schon konsistent oder nicht?

## A — Sanity-Check (alles läuft)

- [ ] **Anwendung öffnet** ohne Fehlerseite, Cockpit zeigt Werte
- [ ] **Daten-Checker** öffnen (Einstellungen → Daten-Checker):
  - Neue Kategorie **„Datenquelle – aktiver Pfad"** sollte sichtbar sein
  - Erwartung kurz nach Update: blauer Info-Hinweis *„HA-Statistics-Pfad bereit, Aggregate aus älterer Quelle"*
  - Kein neuer roter Fehler (Warnungen aus früher dürfen weiter da sein)

## B — Vollbackfill von Hand triggern (Etappe-4-Pfad aktivieren)

Statt auf den Monatsabschluss zu warten, kann der Vollbackfill direkt über die UI angestoßen werden.

- [ ] **Energieprofil-Tab** öffnen: `Aussichten → Energieprofil`
- [ ] Anlage auswählen
- [ ] Knopf **„Lücken nachfüllen"** drücken (Bereich „Energieprofil-Lücken aus HA-Statistik nachfüllen")
- [ ] Warten bis Ergebnis-Meldung kommt (typisch wenige Sekunden bis 2 Minuten)
- [ ] **Daten-Checker** erneut öffnen → Erwartung: **„HA-Statistics als Source-of-Truth aktiv"** (grünes Häkchen)

> ⚠️ **Wichtig:** „Lücken nachfüllen" ist **additiv** — bestehende Tage bleiben unverändert. Für die Migration *vorhandener* Tage gilt Abschnitt C.

## C — Bestehenden Tag testweise reaggregieren (Rainer-15.05.-Pattern)

Für Tage, die schon Daten haben (aus dem alten Mix-Source-Pfad), aber jetzt auf HA-LTS umgestellt werden sollen:

- [ ] **Energieprofil-Tab** → Tagestabelle
- [ ] Bei einem Tag mit auffälliger Drift (z. B. 15.05.2026) den **Reload-Knopf (↻)** klicken
- [ ] **Vorschau** erscheint mit alten vs. neuen Werten → übernehmen
- [ ] Prüfen: stimmt der neue Wert mit dem HA-Energy-Dashboard für denselben Tag überein?

### Drei-Sichten-Konsistenz für diesen Tag prüfen

- [ ] **Genauigkeits-Tracking** (`Aussichten → Genauigkeits-Tracking`) — IST-Wert
- [ ] **Energieprofil-Tabelle** — Spalte „PV-Ertrag"
- [ ] **Monatsbericht-Energieprofil-Tab** — Σ über 24 Stunden
- [ ] **Erwartung:** alle drei identisch (innerhalb < 0,1 kWh)

## D — Etappe-5-spezifisch: Peaks + SoC + Strompreis

Auf einem Tag, der nach dem Update aggregiert wurde (heute oder reaggregierter Tag aus C):

### Peak-Werte aus HA-LTS-Max

- [ ] **TagesZusammenfassung-Peak-Werte** in der Tagestabelle prüfen (Spalte „Peak PV", „Peak Netzbezug", „Peak Einspeisung")
  - Wert sollte **≥ vorher** sein (10-Min-Mittel unterschätzte systematisch)
  - Quervergleich mit HA-Energy-Dashboard Tages-Max: sollte praktisch identisch sein
- [ ] Plausibilität: peak_pv_kw < kWp × 1.2 (Wechselrichter-Begrenzung); peak_einspeisung_kw < peak_pv_kw

### Speicher-SoC-Stundenwerte

- [ ] **SoC-Verlauf** im Energieprofil-Tagesverlauf (Sparkline oder Spalte mit Speicher-Ladestand) prüfen
- [ ] Quervergleich mit HA-Energy-Dashboard SoC-Graph für denselben Tag — Stundenwerte sollten praktisch identisch sein
- [ ] Wenn kein Speicher: nichts zu prüfen, kein Crash

### Strompreis-Stundenwerte (nur bei Tibber/aWATTar-Sensor)

- [ ] **Strompreis-Verlauf** im Tagesverlauf prüfen
- [ ] Quervergleich mit HA-Sensor-History (HA → Verlaufsansicht des Strompreis-Sensors) — Stundenmittel sollten übereinstimmen
- [ ] Einheit korrekt: cent/kWh (auch wenn der Sensor in EUR/kWh liefert)

## E — Regression-Check (nichts darf kaputt sein)

- [ ] **Live-Heute** auf dem Cockpit funktioniert, Werte plausibel
- [ ] **Monatsbericht** für aktuellen Monat lädt ohne Fehler
- [ ] **Prognose-Genauigkeits-Tab** zeigt keine offensichtlich falschen MAE-Werte
  - Hinweis: durch den Batterie-Bug-Fix kann der IST-Wert leicht *sinken* — das ist gewollt (saubere PV-Erzeugung statt PV+Batterie-Ladung)
- [ ] **Daten-Checker** zeigt keine *neuen* Fehler (Counter-Spike-Warnungen aus früher dürfen weiter da sein)
- [ ] **Heatmap / Cockpit-Tageswerte / Wartung / Wizard** lassen sich öffnen, keine Fehlermeldung

## F — Falls etwas auffällt

- [ ] **Logs prüfen**: `Einstellungen → System-Logs` → Filter `monatsabschluss` oder `energie-profil` — Suche nach `Auto-Vollbackfill`-Einträgen
- [ ] **Im Daten-Checker** Eintrag aus A erneut prüfen — wenn er noch *„Aggregate aus älterer Quelle"* sagt, ist Schritt B noch nicht durchgelaufen
- [ ] **Notnagel** (zerstört Stundenwerte + Tagessummen, Monatsdaten bleiben):
  - `Aussichten → Energieprofil` → Rohdaten-Löschen-Knopf (am Seitenende)
  - Scheduler rechnet alles in max. 15 Minuten neu aus HA-LTS
- [ ] **Notnagel-Plus** (zerstört für eine Anlage gezielt): über die Anlagen-Detailseite ebenso, dann Vollbackfill aus B erneut

## Erfolgskriterien

Der Test ist erfolgreich, wenn:

1. ✅ Daten-Checker zeigt **„HA-Statistics als Source-of-Truth aktiv"** nach Schritt B
2. ✅ Drei-Sichten-Konsistenz aus C erreicht (Σ Stunden = Tag = Genauigkeits-Tracking-IST)
3. ✅ Peak-Werte aus D entsprechen dem HA-Energy-Dashboard
4. ✅ Keine neuen Fehler im Daten-Checker
5. ✅ Bestehende Funktionen aus E laufen weiter

## Bekannte Erwartete Änderungen (kein Bug)

- **Peak-Werte werden höher**: 10-Min-Mittel unterschätzte Peaks. HA-LTS-Max ist die physikalisch korrekte Tagesspitze.
- **Prognose-IST-Wert wird etwas kleiner**: bei Anlagen mit Speicher, die über den Tag netto laden. Batterie-Ladung wird nicht mehr fälschlich als PV-Erzeugung mitgezählt (Bug-Fix).
- **Tageswerte können sich um wenige Prozent verschieben**: vom Mix-Source-Wert auf den HA-Energy-Dashboard-konformen Wert.

## Hintergrund-Dokumentation

- Konzept-Detail: `docs/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` (Abschnitt 9a für Etappe 5)
- Anwender-Hinweise: `docs/WAS-IST-NEU.md` → v3.31.0
- Vollständige Änderungsliste: `CHANGELOG.md` → [3.31.0]
