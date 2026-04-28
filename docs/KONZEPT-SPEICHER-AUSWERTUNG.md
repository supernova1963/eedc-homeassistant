# Konzept: Auswertung PV-Speicher

> Status: Entwurf (2026-04-28) | Issue [#142](https://github.com/supernova1963/eedc-homeassistant/issues/142) | Zugehörig: [#101](https://github.com/supernova1963/eedc-homeassistant/issues/101) (Live-Restzeit), [Energieprofil Etappe 4](https://github.com/supernova1963/eedc-homeassistant/issues/110) (Saison)

## Motivation

Bei größeren PV-Anlagen ist der Speicher der teuerste Posten und gleichzeitig die schwerste Sizing-Entscheidung. EEDC sammelt seit v3.19.0 (Snapshot-Rework) und v3.21.0 stündliche, kalibrierte Lade-/Entladewerte plus SoC — das reicht inhaltlich, um die **sechs Anwender-Fragen aus #142** zu beantworten:

1. Auslastung pro Monat (kWh + %)
2. Auslastung in Relation zur Einspeisung — wäre mehr Kapazität sinnvoll gewesen?
3. Lohnt sich eine größere Batterie überhaupt?
4. Direkte Gegenüberstellung Solar-Ladung vs. Netz-Ladung (Arbitrage)
5. Einsparung durch Solarladung in € abzgl. entgangener Einspeisevergütung
6. Einspeisevergütung pro Monat in Relation zu Be-/Entladung

Die Auswertung soll **monats-basiert** sein (keine zusätzlichen Live-Sensoren nötig — Anforderung aus dem Issue), Vergleichs-Achsen: Jahr, Sommer/Winter-Zeitraum, einzelne Monate.

## Datenbasis (vorhanden)

| Quelle | Granularität | Felder | Status |
|---|---|---|---|
| `Monatsdaten.verbrauch_daten` (pro Speicher) | Monat | `speicher_ladung_kwh`, `speicher_entladung_kwh`, `speicher_ladung_netz_kwh` (Arbitrage), `speicher_ladepreis_cent`, ggf. SoC-Tagesmittel | ✅ ab v3.16.0 in `field_definitions.py` |
| `TagesEnergieProfil` | Stunde | Speicher-Snapshot kumuliert (Lade/Entlade-Zähler), SoC-Stundenwerte | ✅ ab v3.19.0 |
| `Anlage.einspeiseverguetung_cent_kwh` + `Strompreis` | Tarifperiode | Endpreis + Börsenpreis | ✅ |
| Investitions-Parameter Speicher | statisch | `batteriekapazitaet_kwh`, `max_leistung_kw`, `arbitrage_faehig`, `bidirektional`, `wirkungsgrad`, `zyklen_garantiert` | ✅ |

**Was fehlt** für die sechs Fragen ist nicht die Datenerfassung, sondern die **Aufbereitung** + **Dimensions-Vergleich**. Die Berechnung läuft über aggregierte Monatswerte; Stundendaten brauchen wir nur für Sub-Auswertungen wie „SoC-Verteilung über den Tag" (siehe Phase 2).

## Kennzahlen-Mapping (Issue → Berechnung)

### 1. Auslastung pro Monat (kWh + %)

```
zyklen_monat        = entladung_kwh / batteriekapazitaet_kwh
durchsatz_kwh       = ladung_kwh + entladung_kwh
auslastung_prozent  = entladung_kwh / (batteriekapazitaet_kwh * tage_im_monat)
```

Anzeige: kWh (Ladung/Entladung), Vollzyklen-Äquivalent, Auslastung in % der theoretischen Maximalkapazität.

### 2. Auslastung vs. Einspeisung — „mehr Kapazität sinnvoll gewesen?"

Indikator-Schwelle: **Tage mit `SoC_max ≥ 95 %` UND gleichzeitiger Einspeisung ≥ X kWh** sind Kandidaten für ungenutztes Potential — der Speicher war voll, PV ging trotzdem ins Netz.

```
ungenutztes_potential_kwh = Σ (einspeisung_kwh an Tagen mit SoC_max ≥ 95 %)
```

Anzeige als Monats-Balken neben dem Speicher-Durchsatz. Aussagekraft setzt SoC-Stundendaten voraus (vorhanden seit v3.19.0).

### 3. „Lohnt sich eine größere Batterie?" — Was-wäre-wenn-Sizing

Wir simulieren rückblickend mit den vorhandenen Stunden-Profilen einen **alternativen Speicher** (X kWh, Y kW Leistung, Z % Wirkungsgrad), füttern ihn mit den realen PV/Verbrauch-Stundenwerten und vergleichen Eigenverbrauchsquote / Autarkie / Einspeisung.

- Eingabe: Slider „Speicher-Kapazität" (50 % … 200 % der aktuellen) + ggf. Leistung
- Ausgabe: Δ Eigenverbrauch [kWh], Δ Einsparung [€], Amortisations-Aufschlag bei Mehrkosten [€/kWh-Speicher]
- Voraussetzung: 6–12 Monate Stundendaten — bei kürzerer Historie Hinweis-Banner anzeigen

**Methodischer Hinweis** für die Hilfe-Seite: Die Simulation kennt nur das tatsächlich beobachtete Wetter und Verbrauchsverhalten. Sie überschätzt Speicher-Nutzen tendenziell, weil das vorhandene Verbrauchsprofil bereits auf den vorhandenen Speicher optimiert ist (Lastverschiebung). Für eine Sizing-Entscheidung trotzdem belastbarer als ein generisches Sizing-Tool, weil es die individuelle Saisonalität trägt.

### 4. Solar- vs. Netz-Ladung

`speicher_ladung_netz_kwh` ist bereits separates Feld. Anzeige als gestapelter Monats-Balken. Bei `arbitrage_faehig=false` reduziert sich die Sicht auf reine Solar-Ladung.

### 5. + 6. Wirtschaftlichkeit pro Monat

```
einsparung_solar_eur     = entladung_aus_solar_kwh * strompreis_eur_kwh
opportunitaet_eur        = entladung_aus_solar_kwh * einspeiseverguetung_eur_kwh
netto_einsparung_eur     = einsparung_solar_eur - opportunitaet_eur

arbitrage_ergebnis_eur   = entladung_aus_arbitrage_kwh * (strompreis_eur_kwh - ladepreis_eur_kwh)
                           - wirkungsgrad_verlust_kwh * ladepreis_eur_kwh
```

Aufschlüsselung der Entladung in „aus Solar" vs. „aus Arbitrage-Netzladung" über die Lade-Anteile (anteiliger Wirkungsgrad).

Anzeige: Monats-T-Konto „Plus Eigenverbrauch / Minus entgangene Einspeisung / Arbitrage-Saldo / Netto-Beitrag".

## Phasen-Vorschlag

### Phase 1 — Auswertungs-Tab „Speicher" (klein anfangen)

Neue Sektion in **Auswertungen** (bestehende Architektur, kein neues Top-Level-Tab nötig):

- Monats-Tabelle mit Spalten: Ladung [kWh], Entladung [kWh], Vollzyklen, Solar-Anteil [%], Netz-Anteil [%], Netto-Einsparung [€]
- Jahres-Aggregat + Sommer/Winter-Split (analog WP-Heizgradtage-Ansatz)
- Drei KPI-Kacheln: Ø Vollzyklen/Jahr, Ø Netto-Einsparung/Jahr, kumulierte Einsparung seit Anschaffung

**Liefert:** Issue-Punkte 1, 4, 5, 6. Reine Aggregation aus Monatsdaten + Stundendaten — ohne neue Datenmodell-Felder.

### Phase 2 — „Hätte mehr Kapazität geholfen?"

- Indikator-KPI: Tage mit `SoC_max ≥ 95 %` + Einspeisung
- Saisonaler Verlauf: Heatmap Monat × SoC-Bin → wo lief der Speicher voll?

**Liefert:** Issue-Punkt 2.

### Phase 3 — Was-wäre-wenn-Sizing-Simulator

- Slider-basiert, rückblickende Simulation
- Hinweis-Banner zur methodischen Einschränkung
- Optional: Vergleich „eine Größe kleiner / aktuelle / eine Größe größer"

**Liefert:** Issue-Punkt 3.

### Phase 4 — Verknüpfung mit #101 (Live-Restzeit)

Die Live-Restzeit „Speicher voll um HH:MM" erbt aus den Phase-1/2-Aggregaten ein **typisches Stundenprofil** der PV-Restprognose pro Saisonbin → realistischere Aussage als reine Linear-Extrapolation. Trigger: nach Prognose-Konsolidierung (Blended Forecast).

## Datenmodell — was wir NICHT brauchen

- **Keine neuen Live-Sensoren.** Anforderung aus dem Issue, wird respektiert. Stundendaten kommen aus dem bestehenden Snapshot-Job.
- **Keine neue Tabelle.** `Monatsdaten.verbrauch_daten` (JSON pro Speicher-Investition) trägt Phase 1; für Phase 3 reicht eine Read-Only-Simulation aus den Stunden-Profilen, kein Persist nötig.

## Datenmodell — was wir vermutlich brauchen

- **Kennzahl-Cache** für Sizing-Simulationen: Phase-3-Auswertungen sind teuer (8760 h × Slider-Schritte). Caching analog L2-Cache der Prognosen, Key = `(anlage_id, simulations_hash)`. Erst implementieren, wenn Phase 3 wirklich umgesetzt wird.
- **Optional**: ein zusätzliches Monats-Aggregat-Feld `speicher_entladung_aus_solar_kwh` würde Phase 1 stark beschleunigen, weil sonst pro Monat die Stundendaten neu durchgerechnet werden. Trigger: messen ob Phase 1 ohne dieses Feld schnell genug ist.

## Trigger für Umsetzung

- **Phase 1**: Sobald **konkretes Forum-Feedback** kommt, dass die heute schon vorhandenen Speicher-Werte in den Monats-/Jahres-Auswertungen zu versteckt sind. Mehrere Tester haben mindestens 6–12 Monate Snapshot-Daten ab v3.19.0.
- **Phase 2**: Direkt im Anschluss an Phase 1, wenn das SoC-Heatmap-Visual Sinn ergibt.
- **Phase 3**: Wenn Phase 1+2 stabil sind UND ein Tester aktiv nach Sizing-Beratung fragt. Vorher zuviel Aufwand für Edge-Case.
- **Phase 4**: Gekoppelt an [Prognose-Konsolidierung](https://github.com/supernova1963/eedc-homeassistant/issues/110) und #101.

## Offene Fragen

1. **Wirkungsgrad** — aus `Investition.parameter_schema` oder gemessen aus Lade-/Entlade-Quotient? Gemessen ist genauer, parameter_schema ist Fallback.
2. **„Strompreis"** für die Einsparungs-Rechnung — Endpreis (inkl. Steuern + Abgaben) ist die korrekte Vergleichsbasis. Bei dynamischem Strompreis: stündlich gewichteter Ø des Entlade-Zeitraums (haben wir seit v3.16.0).
3. **Garantie-Restzyklen** — `zyklen_garantiert` minus aufsummierte Vollzyklen → KPI „verbleibende Garantie-Reserve". Niedrige Priorität, aber attraktiv für Anwender.
4. **Multi-Speicher-Anlagen** — heute selten, aber Architektur muss pro Speicher-Investition aggregieren (analog Wallbox/E-Auto-Konzept).

---

*Letzte Aktualisierung: 2026-04-28*
