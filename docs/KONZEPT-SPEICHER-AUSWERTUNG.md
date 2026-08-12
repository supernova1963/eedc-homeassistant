# Konzept: Auswertung PV-Speicher

> **Status (gemessen 2026-08-12): Phase 1 + Phase 2 ausgeliefert · Phasen 3–4 offen, getrackt als [#358](https://github.com/supernova1963/eedc-homeassistant/issues/358).** ⚠ Bis heute nannte diese Zeile „Kern weiterhin offen" und verwies auf **#243**, das mit v4.0.0 geschlossen wurde — während drei Absätze tiefer im selben Kasten „Phase 1 ausgeliefert" steht. Der **Statuskopf** ist die Stelle, die jeder zuerst liest und die beim Fortschreiben des Rumpfes niemand anfasst (Fund N-182). Alles unter dieser Zeile bleibt inhaltlich gültig. Einzel-Issue #142 (rapahl) wurde 2026-05-23 in die Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) verschoben. **Ort-Entscheid (IA-V4):** die Tiefe kommt als **Ausbau des Komponenten-Hubs Speicher** (SPEC-KOMPONENTEN K-O2), NICHT als eigener Auswertungen-Tab — Phase-1-Verortung unten entsprechend re-lesen. **⚑ Präzisiert 2026-08-01 (Gernot, nach Community-Einwand unter #350):** es gilt die **Ortsregel nach Zeitraum** — **zeitbezogene** Sichten (Tag/Monat/Jahr, also Phase 1: Monats-Tabelle, KPI-Kacheln, Sommer/Winter) gehören ins **Cockpit** neben die Energiebilanz; im **Komponenten-Hub** bleibt, was über die **Lebensdauer** des Geräts geht (Phase 2 SoC-Heatmap, Phase 3 Sizing-Simulator, Wirtschaftlichkeit). „Nicht als eigener Auswertungen-Tab" bleibt unverändert gültig — die Korrektur betrifft Hub ↔ Cockpit, nicht den Auswertungen-Bereich. **Seit Konzept-Erstellung bereits geliefert (vor B11-Bau einarbeiten):**
> - **#264 Etappen A–C (stlorenz, v3.31.x):** gemessener IST-Wirkungsgrad (SoC-korrigiert + Degradations-Alarm) und stundengewichteter effektiver Ladepreis mit Quelle-Transparenz → beantwortet die „Offenen Fragen" 1 + 2 unten.
> - **R15-Scheiben (Rainer-PN #88625, 2026-07-05):** Kosten-Kacheln „Batterieladung Netz" + „Durchschnittspreis Netz" in Cockpit Monat/Tag/Jahr (`berechne_netzladung_kosten`, Preis-Kette TEP→IMD→Bezugspreis) · Ø-Ladepreis-**Vorschlag** im Monatsabschluss-Wizard · Netzladung-Kosten-**Ausweis** im Hub-Arbitrage-Block + T-Konto („davon"-Zeile) · Kanon-Key-Fix `get_speicher_netzladung_kwh` (Hub-Arbitrage war unsichtbar) → deckt die Sichtbarkeits-Seite von Frage 4 + 5 im Kleinen.
> - **Phase-3-Grundstein:** `core/berechnungen/speicher_simulation.py` (`simuliere_speicher_tag`) existiert.
>
> **✅ Phase 1 ausgeliefert (2026-08-04, #358).** Block **„Speicher im Jahr"** in *Cockpit → Jahr*:
> Monatstabelle (Ladung · Entladung · Vollzyklen · Solar-Anteil · Auslastung · Netto-Nutzen) +
> Gesamtzeile + Saison-Vergleich über `SAISON_FENSTER`; zwei zusätzliche KPI-Kacheln (Auslastung,
> Netto-Nutzen) im Speicher-Abschnitt von Monat und Jahr. **Kein neuer Endpoint** (D3): die Sicht
> faltet dieselben Monats-Antworten wie die Kacheln darüber. Neue Layer-Formeln
> `auslastungs_basis_kwh` + `auslastung_prozent` (`core/berechnungen/speicher.py`) — die **Basis**
> ist bewusst ein eigenes, additives Feld, weil sich Auslastungs-Prozente nicht mitteln lassen.
> Damit sind die Issue-Punkte **1, 4, 5 und 6** beantwortet.
>
> **✅ Der Spread-Entscheid ist im selben Paket gefallen** (Gernot 2026-08-04): der Speicher-Nutzen
> ist der **Spread** (Bezug − Einspeisung), Netzladung ausgenommen. Er bestätigt die Entscheidung
> aus Drift-Audit A3 — neu ist ihre **Durchsetzung**: `aktueller_monat.py` rechnete den
> T-Konto-Posten mit dem Voll-Strompreis (36 % zu hoch bei 30/8 ct), `dashboards.py` den Spread
> inline auf der **gesamten** Entladung und wies den Arbitrage-Gewinn zusätzlich aus (Doppelzählung
> im Hub). Alle drei Stellen rufen jetzt `berechne_speicher_ersparnis`; gewächtert von
> `backend/tests/test_speicher_kanon_symmetrie.py` (3 Achsen, mit absoluten Erwartungen — Symmetrie
> allein ließe auch drei gleich falsche Zahlen durch). Im selben Zug fiel die letzte Route auf, die
> Vollzyklen aus der **Ladung** rechnete (`cockpit/uebersicht.py`; der Kanon-Sweep vom 2026-07-28
> hatte sie übersehen, sie hatte damals keinen Client-Leser).
>
> **Offen (= B11-Kern):** Phase 2 (SoC-Heatmap „ungenutztes Potential"), Phase 3
> (Sizing-Simulator-UI), Phase 4 (#101-Kopplung) — alle drei im **Komponenten-Hub**, sie gehen
> über die Lebensdauer des Geräts.
>
> Zugehörig: [#101](https://github.com/supernova1963/eedc-homeassistant/issues/101) (Live-Restzeit), [Energieprofil Etappe 4](https://github.com/supernova1963/eedc-homeassistant/issues/110) (Saison)

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

> ⚠ **Korrigiert 2026-08-12 beim Bau von Phase 2 — die ursprüngliche Formel unten beantwortet ihre eigene Frage nicht.** Sie lautete:
>
> ```
> ungenutztes_potential_kwh = Σ (einspeisung_kwh an Tagen mit SoC_max ≥ 95 %)
> ```
>
> An zwölf Junitagen der Dev-Anlage ergibt das **471,6 kWh** „ungenutztes Potential" — die Einspeisung fällt dort fast vollständig in Stunden mit vollem Speicher. Gemessen fiel der Speicher in **keiner** dieser Nächte unter **31 %**: Wer daraufhin Kapazität kauft, hat morgens mehr Restladung und gibt sie nie ab. **Nutzen real 0 kWh, ausgewiesen 471,6 kWh.** Im Winter kippt es in die Gegenrichtung (November: SoC-Maximum 2 %) — dort fehlt die Sonne, nicht der Speicher.
>
> **Der begrenzende Faktor ist die Nacht, nicht die Sonne.** Zusätzliche Kapazität nützt nur, wenn *beides* zusammenkommt: Überschuss, den der volle Speicher nicht aufnahm, **und** eine Nacht, in der er vor dem nächsten Sonnenaufgang leer lief. Die gebaute Kennzahl ist deshalb ein **Minimum aus beidem, je Lade-Entlade-Zyklus** (Gernots Entscheid 2026-08-12; die Alternative „naive Summe mit Kleingedrucktem" wurde ausdrücklich verworfen — an dieser Zahl hängt eine Kaufentscheidung):
>
> ```
> je Zyklus:  nutzbar = min( Σ Einspeisung bei SoC ≥ 95 %,
>                            Σ Netzbezug ab dem Moment, in dem SoC ≤ 5 % war )
> gesamt   =  Σ nutzbar über alle Zyklen
> ```
>
> Zyklusweise, nicht zeitraumweise: sonst rechtfertigt eine einzige leergelaufene Nacht die Überschüsse aller anderen Tage. Über die **durchgehende** Stundenreihe statt je Kalendertag, weil die Nacht über Mitternacht liegt. SoT: `core/berechnungen/speicher_potential.py`, Sourcing in `services/speicher_potential_service.py`.
>
> Gemessene Trennschärfe (Dev-Anlage, je 12 Tage): Juni 471,6 → **0** · März 227,0 → **29,3** · Oktober 9,5 → **0,5** · Februar 32,6 → **32,6** (dort greift die Deckelung nicht — jeder Zyklus lief leer).

Die naive Summe bleibt als **Obergrenze** sichtbar („was ein beliebig großer Speicher höchstens hätte aufnehmen können"), damit der Unterschied nicht verschwiegen, sondern erklärt wird.

Anzeige im **Komponenten-Hub Speicher**, Block „Wirtschaftlichkeit": Befund-Satz + drei Kacheln + Heatmap Monat × SoC-Bin. Aussagekraft setzt SoC-Stundendaten voraus (vorhanden seit v3.19.0; an der Dev-Anlage 651 Tage mit 100 % Abdeckung, SoC durchgängig gefüllt).

⚠ **Der SoC in `TagesEnergieProfil` ist anlagenweit** (die Tabelle hat `anlage_id`, keine `investition_id`). Bei mehreren Speichern ist er ein Mischwert; die Sicht sagt das, statt eine Gerätegenauigkeit zu suggerieren.

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

### Phase 2 — „Hätte mehr Kapazität geholfen?" ✅ (2026-08-12)

Gebaut im **Komponenten-Hub Speicher**, Block „Wirtschaftlichkeit":

- **Gedeckelte** Kennzahl `nutzbares_zusatzpotential_kwh` (Herleitung und Messung
  oben unter Kennzahl 2) — daneben die naive Summe als ausdrückliche Obergrenze
- Befund-Satz, der die Zahl einordnet: „0 kWh" ist sonst nicht von „keine Daten"
  zu unterscheiden
- Heatmap Monat × SoC-Bin (zehn Zehntel-Bins) — eine dunkle Zeile oben heißt
  „lief oft voll", eine dunkle unten „lief oft leer"; erst beides zusammen macht
  mehr Kapazität sinnvoll
- Kachel „Nächte mit leerem Speicher" (x von y Zyklen) als die eigentliche
  Begrenzung

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
