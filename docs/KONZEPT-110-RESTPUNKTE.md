# Roadmap #110 — die zwei verbliebenen Punkte: Einwertung und Bauplan

> **Stand 13.10.2026, Entscheid Gernot.** Dieses Dokument gehört zum Abschnitt «Gesammelt» der Roadmap
> [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110). Es wertet die zwei dort verbliebenen Punkte am Stand von
> v4.1.7 ein und legt für einen davon den Bauplan fest. **#110 bleibt offen**, beide Punkte bleiben dort stehen — ohne Termin.
>
> | Punkt | Entscheid 13.10.2026 |
> | --- | --- |
> | **Cockpit → Jahr: Stellung «Gesamt» über alle Jahre** (aus #395 Punkt 2, OB73-gif) | **nicht gebaut** — Einwertung in [§1](#1-cockpit-jahr-stellung-gesamt). Auslöser bleibt ein Melder, der die Gesamtsicht braucht; dann ist zuerst die Konzeptfrage in §1.4 zu entscheiden. |
> | **V2H: der Tageswert der Entladung fehlt** | **wird gebaut** — als eigenes Päckchen nach v4.1.7, ohne Termin. Entscheide und Bauplan in [§2](#2-v2h-tageswert). |
>
> Zeilenangaben beziehen sich auf den Stand nach Päckchen M3 (13.10.2026). Wer den Bauplan ausführt, misst sie am HEAD nach.

## 1. Cockpit Jahr: Stellung Gesamt

### 1.1 Was fehlt

Der Reiter heißt «Jahr/Gesamt», wählbar sind nur einzelne Jahre (`eedc/frontend/src/v4/CockpitV4.tsx:25`, Jahreswahl in
`CockpitJahrV4.tsx:98-134`). Einzelne Kacheln zeigen die volle Historie — «CO₂ kumuliert», die Spalte «Ø Jahre», die Jahresleiste —,
die Seite als Ganzes nicht. Das Handbuch sagt das heute ausdrücklich (Bedienung §2.4).

### 1.2 Wo die Gesamtzahlen heute stehen

- **Komponenten → Hub** je Gerät: ganze Laufzeit (Wirtschaftlichkeit, Lebensdauer-Sichten).
- **Jahresbericht-PDF** (Einstellungen → Berichte & Dokumente) mit der Stellung **«Gesamtzeitraum»**; Finanzbericht-PDF mit «Alle Jahre».
- **Auswertungen** (Finanzen, Energie, Tabelle) mit dem Zeitraum **«Alle Jahre»**.
- **Auswertungen → CO₂** und der Block «CO₂-Bilanz» in Cockpit → Jahr: kumuliert über die ganze Historie.

### 1.3 Messung am Stand v4.1.7

| Gemessen | Befund |
| --- | --- |
| Route `backend/api/routes/cockpit/jahr.py:60-67` → `services/jahres_aggregat.py::baue_jahr:128-220` | `jahr` ist Pflichtparameter. **15 Funktionen** der Kette tragen ein `jahr` mit Jahres-Semantik: Monatsauswahl (`:50`, `:111`), Vorlade-Kontext J−1…J (`aktueller_monat/kontext.py:36-43`), USt-Satz je Jahr (`ust_satz.py:61-186`), Vorjahr (`:208`), Ø-Jahr (`:209-210`), Texte (`:186`, `:197`). Rund **33 Einzelstellen in 6 Dateien**. |
| Faltung `core/berechnungen/ergebnis.py::falte_zeitraum:526-829` | nimmt zwar eine beliebige Monatsliste, aber `spez_ertrag` wird **summiert** (`:671`) — über mehrere Jahre entstünden kumulierte kWh/kWp statt des Jahreswerts; Monatsschlüssel und Texte kennen nur die Monatsnummern 1–12 (`:412-426`, `:643-645`, `:892`). |
| Antwort `CockpitJahrResponse` (`jahr.py:46-57`) | alle 8 Felder jahresgebunden (`monate_nr`, `vergleichs_monate`, `vorjahr`, `oe_jahr`, …). |
| Frontend `CockpitJahrV4.tsx` | 5 Datenabrufe, davon 3 jahresgebunden; **8 Blöcke, 7 jahresgebunden**: Bilanz-Fenster nur Monate 1–12 (`lib/monatsFenster.ts:33-56`), Verlauf «genau ein Jahr» (`JahrVerlaufChart.tsx:124`), Wärme-Verteilung ohne Jahr ⇒ HTTP 400 (`energie_profil/waerme.py:505-508`); Zählerstände könnten `gesamt` (`zaehlerstaende.py:85-86`), haben aber keinen Aufrufer. |
| Konsumenten der Route | 2 (`CockpitJahrV4.tsx:147`, `AuswertungenFinanzenV4.tsx:470` — T-Konto im Jahr-Modus). |
| Tests | 7 Backend-Dateien direkt an der Route (≈ 90 Tests) plus 15 weitere mit `baue_jahr`; 12 Frontend-Testdateien; Fokus-ID-Vertrag (`test/fokus-id-vertrag.test.ts`). |
| Vorhandene Gesamt-Faltungen | `GET /cockpit/uebersicht` ohne `jahr` (`uebersicht.py:244`, `:309`; andere Antwortform, ohne Ergebnis-Leiter), `/cockpit/nachhaltigkeit`, `/monatsdaten/aggregiert`, Komponenten-Hub, Jahresbericht-PDF mit `jahr=None`. |

### 1.4 Die offene Konzeptfrage

Zwei Entwürfe liegen vor, keiner ist entschieden:

- **A — dieselbe Seite mit Mehrjahresachse** (interne Vorlage vom 29.09.2026, nicht gebaut): Stellung «Alle Jahre» wie in den
  Auswertungen; Vorjahr und Ø-Jahr entfallen, Wärme-Verteilung entfällt, Verlauf mit Mehrjahresachse, Zählerstände «gesamt»; die
  Faltung über alle Monate läuft über dieselbe Ergebnis-Leiter wie das Jahr.
- **B — eigene Blockmenge aus den vorhandenen Gesamt-Routen** (Konzept Monats-Verdichtung §7): Übersicht ohne Jahr, Nachhaltigkeit,
  `aggregiert`, Hub — kein Fan-out über Monate. «Alle Jahre» ist dabei **kein Δ über alles**: gespeicherte Monatswerte schlagen
  gerechnete, also Δ ≠ Σ.

In beiden Fällen zu klären: der spezifische Ertrag (Summe oder Hochrechnung), die Quoten «nur über vollständige Monate» über mehrere
Jahre, die USt-Sätze je Jahr (`ust_eigenverbrauch_zeitraum` existiert), und ob die Deep-Link-IDs der Jahr-Blöcke dieselben bleiben.

### 1.5 Entscheid

**Nicht gebaut.** Aufwandsklasse: mehrere Tage plus Konzeptentscheid — im Wartungsmodus nur auf einen Melder, der die Gesamtsicht
braucht. Bis dahin gilt §1.2 als Antwort an Anwender.

## 2. V2H-Tageswert

### 2.1 Was fehlt

Vehicle-to-Home: ein bidirektionales Auto speist ins Haus zurück. **Live** (v4.1.0) zeigt «entlädt … kW (V2H)» und rechnet die
Rückspeisung wie eine Speicher-Entladung in Autarkie und Eigenverbrauch (F-69, N-575). **Monat und Jahr** (v4.1.2) zählen
`v2h_entladung_kwh` aus dem Monatsabschluss (N-610). **Cockpit → Tag** kennt V2H nicht: im E-Mobilität-Block steht bei V2H «—»,
und Eigenverbrauch, Gesamtverbrauch und Autarkie des Tages lassen die Rückspeisung weg.

### 2.2 Ursache

`backend/core/field_definitions/karten.py:336-339` führt `("e-auto", "v2h_entladung_kwh")` in `_SNAPSHOT_AUSNAHMEN` mit dem Vermerk
«⚠ UNBEWERTET … Beim nächsten Eingriff am E-Auto-Pfad bewerten». Folgen:

- Das Feld fehlt in `KUMULATIVE_ZAEHLER_FELDER` (`services/snapshot/keys.py:44`): der HA-Writer schreibt nie einen Zählerstand
  (`writer.py:132`), der MQTT-Schlüssel `inv/<id>/v2h_entladung_kwh` wird verworfen (`keys.py:171-197`), damit gibt es auch keinen
  MQTT-Monatsvorschlag (`mqtt_energy_history_service.py:536-541`).
- Unabhängig davon fehlen Kategorie (`keys.py:455-555` kennt für `e-auto` nur Verbrauch und Ladung, `:534-537`), Achse
  (`core/berechnungen/spannen.py:37-50`) und Beitrag (`services/snapshot/komponenten_beitraege.py:498-532`). Deshalb greift auch der
  Pfad über die HA-Langzeitstatistik V2H nicht auf (`lts_aggregator.py:62-118` liest dieselbe Beitragsschicht).
- Im Tag ist das an drei Stellen dokumentiert: `energie_profil/aggregator.py:846-849` («Die Tages-Ebene kennt V2H damit weiterhin
  NICHT»), `tage_werte.py:412-413` («V2H/BKW bleiben 0 — die Stunden kennen sie nicht»), `docs/BERECHNUNGEN.md:289` («der Tag kennt
  kein V2H»). Fundregister N-288 (29.08.2026) hatte denselben Ort benannt und war als Dublette zu #110 erledigt worden.

### 2.3 Entscheide (13.10.2026)

- **E1 — eigenes Tagesfeld, keine Mitnahme in der Batterie-Achse.** Die Monatsformel führt V2H als eigenen Summanden
  (`core/berechnungen/verbrauch.py:104`: Eigenverbrauch = Direktverbrauch + Speicher-Entladung + V2H − Abgabe); Speicher-Kennzahlen
  (Wirkungsgrad, Vollzyklen, Ladung/Entladung) bleiben rein. Der Modell-Kommentar «alle Speicher inkl. V2H» in
  `models/tages_energie_profil.py:57` wird korrigiert, er war nie eingelöst.
- **E2 — keine Migration.** V2H wird als **Tagesgröße** im Rollup `TagesZusammenfassung.komponenten_kwh` unter dem neuen Schlüssel
  `v2h_<id>` geführt (derselbe Weg wie `bkw_<id>` und `sonstige_<id>`). Konsequenz: **kein Stundenwert** — die Stundenzeile
  `TagesEnergieProfil` hat keine Spalte dafür, und ihr JSON `komponenten` ist der Leistungspfad. Stundentabelle und Stundenkurve bleiben
  unverändert; die Tagesbilanz ist die Quelle der Wahrheit für die Rückspeisung.
- **E3 — Reichweite.** Beide Zählerpfade (Snapshot HA/MQTT und HA-Langzeitstatistik) über die **eine** Beitragsschicht; der
  MQTT-Schlüssel wird wieder einlesbar. **Außen vor** (bewusst, §2.6): laufender Monat aus Tagen, Leistungspfad/Stundenkurve,
  Auswertungen → Tabelle, Tagesdetail-Boundary.

### 2.4 Bauplan

| Schritt | Ort | Was |
| --- | --- | --- |
| **B1 Registry** | `karten.py:336-339` | Ausnahme entfernen ⇒ das Feld steht in `KUMULATIVE_ZAEHLER_FELDER["e-auto"]`; HA-Writer und MQTT-Parser nehmen es ohne weitere Änderung. Der Wächter `test_jedes_energie_feld_ist_erfasst_oder_begruendet` bleibt grün; `test_jedes_zaehlerfeld_erzeugt_einen_beitrag_oder_ist_begruendet` verlangt B3. |
| **B2 Kategorie und Achse** | `keys.py::_categorize_counter` (nach `:534-537`), `spannen.py` (`ACHSEN:31-33`, `_ACHSE_JE_KATEGORIE:37-50`) | neue Kategorie `entladung_v2h`, neue Achse `v2h`. Die Achse hat keine Spalte in der Stundenzeile (E2) — sie trägt nur Spannen, Verworfen (R4) und Nachtrag. Vorher alle Konsumenten von `ACHSEN` erheben (`verbrauch_spannen_passen`, Daten-Checker-Anzeige von `verworfen`/`nachtrag`, Tageszeile); setzt einer eine Spalte voraus: anhalten und melden. |
| **B3 Beitrag** | `komponenten_beitraege.py::investition_beitraege`, E-Auto-Zweig `:498-532`, Helfer `_add:347` | `v2h_entladung_kwh` mit Ziel-Schlüssel `v2h_<id>`, Vorzeichen +1 — **vor** dem Parent-Skip und vor `wallbox_deckt_ladung`: beide Regeln betreffen die *Ladung*; die Wallbox hat kein V2H-kWh-Feld (`registry.py:585-588`, nur das Auto, bedingt durch `v2h_faehig`), das Auto hinter der Wallbox ist der einzige Träger. `_add` braucht dafür ein Ziel-Argument; `_TYP_KEY_PREFIX` bleibt (`eauto_<id>` trägt weiter nur die Heimladung). |
| **B4 Tagestabelle** | `tages_tabelle.py:299-304` | nichts zu ändern: Schritt 7 schreibt jeden Beitrag mit Ziel-Schlüssel in `komponenten_kwh`; `ohne_tageswert` (Tagesreset) gilt automatisch. Mit Test belegen, dass die Stundenwerte (`stunden[h]`) unverändert bleiben. |
| **B5 Tagesbilanz** | `core/berechnungen/tagesbilanz.py` | `TagesBilanz.v2h_entladung_kwh: float = 0.0`; `bilanz_aus_stundenrows(rows, *, verworfen=None, v2h_entladung_kwh=0.0)`; **nur im R7-Zweig** (`regelmarke`, `:309-336`): `gesamtverbrauch_ha_formel_kwh(…, v2h_entladung_kwh)` (`:158-175`, Formel PV + Netzbezug + Entladung + V2H − Einspeisung − Ladung) und `_eigenverbrauch_kwh(…, v2h_entladung_kwh)` → `berechne_verbrauchs_kennzahlen(v2h_entladung_kwh=…)` (`:51-74`). Autarkie folgt über `gesamtverbrauch_ha`. Altbestand ohne Regelmarke bleibt unverändert (dort gibt es keinen V2H-Rollup). |
| **B6 Tageswerte** | `services/energie_profil/tage_werte.py` | Rollup lesen (`komp_tag`, `:280`; Muster `summe_bkw_kwh`, `:486`): Σ der `v2h_*`-Schlüssel, `None` wenn keiner da ist (eine 0,0 ist ein Messwert); an `bilanz_aus_stundenrows` übergeben (`:277`); `FinanzZeileEingabe(v2h_entladung_kwh=…)` (`:400-415`, Feld existiert: `finanz_zeilen.py:61`), Kommentar `:412-413` anpassen; `TagWerteResponse.v2h_entladung: Optional[float]` (`api/routes/energie_profil/_shared.py:533-684`, neben `speicher_entladung`). |
| **B7 Feld-Auswertung** | `core/feld_auswertungen.py:472-476` | Eintrag `COCKPIT_TAG` (`services/energie_profil/tage_werte.py`, `baue_tage_werte`); Wächter `test_jedes_feld_hat_eine_auswertung.py`. |
| **B8 Frontend** | `api/energie_profil.ts` (`TagWerte`), `v4/TagKomponenten.tsx:191-196`, `v4/TagBilanz.tsx:181-192` | `emob_v2h_kwh: tag.v2h_entladung ?? null` (die geteilte Zeile «V2H-Rückspeisung» in `KomponentenSektionen.tsx:1164` zeigt sie dann wie Monat und Jahr); Formeltext der Eigenverbrauchs-Kachel «Direktverbrauch + Speicher-Entladung + V2H-Rückspeisung» nur, wenn V2H > 0; Kommentare `:92-94` und `:191-196` anpassen. Keine neue Deep-Link-ID. |
| **B9 Doku** | `docs/BERECHNUNGEN.md:289`, `docs/SENSOR-REFERENZ.md:339` (+ «Cockpit → Tag»), `docs/GLOSSAR.md:16` (wird wahr), `docs/HANDBUCH_BEDIENUNG.md` §2.2 Tag (E-Mobilität-Block), Code-Kommentare (`karten.py`, `tages_energie_profil.py:57`, `energie_profil/aggregator.py:846-849`, `tage_werte.py:412-413`), CHANGELOG `[Unreleased]`, `docs/WAS-IST-NEU.md`, `./scripts/sync-help.sh` | Die Regel in einem Satz: *Der Tag kennt die V2H-Rückspeisung als Tagesgröße aus dem Zählerpfad; Stunden tragen sie nicht.* |
| **B10 Tests** | `backend/tests/`, `frontend/src/` | (1) Beitragsschicht: E-Auto mit `v2h_faehig` und zugeordnetem Zähler ⇒ Beitrag `v2h_<id>` +1, auch hinter einer Wallbox und bei `wallbox_deckt_ladung=True`; ohne Zuordnung kein Beitrag. (2) Kategorie `entladung_v2h`, Achse `v2h`. (3) `baue_tagestabelle` mit V2H-Slots (Snapshot-Doubles) ⇒ `komponenten_kwh["v2h_<id>"]`, Stunden unverändert; dasselbe über den LTS-Pfad. (4) `bilanz_aus_stundenrows(v2h_entladung_kwh=…)`: Eigenverbrauch, Gesamtverbrauch, Autarkie gleich `berechne_verbrauchs_kennzahlen` mit denselben Zahlen (Muster `test_wk16g_tag_liest_wie_der_monat.py`); Altbestand unverändert. (5) `baue_tage_werte` liefert `v2h_entladung` und eine Finanzzeile mit V2H (Muster `test_n635_eine_eigenverbrauchs_formel.py`). (6) MQTT-Schlüssel wieder einlesbar (Wächter `test_publizierte_mqtt_topics_sind_wieder_einlesbar`). (7) Frontend: `TagKomponenten` setzt `emob_v2h_kwh`, `TagBilanz` nennt die Formel. Bestehende Symmetrie-Tests (`test_tage_werte_symmetrie.py`, `test_batterie_vorzeichen_durchgaengig.py`) müssen grün bleiben. |

**Baunotiz B1 (13.10.2026, Bau-Sitzung):** `_SNAPSHOT_AUSNAHMEN` steuert nicht nur `KUMULATIVE_ZAEHLER_FELDER`, sondern auch den
Kanal-Katalog (`services/kanal/katalog.py`, Regel A-S) und damit die E-Mob-Kanalgruppe (`kanal/geraete_leser._emob_felder`). Ohne Gegenmaßnahme
hätte V2H einen `sum`-Kanal bekommen, der laufende Monat hätte V2H über die Gruppe getragen, und bei MQTT-Anlagen wäre die Gruppe im
Übergangsmonat auf den Bestand gefallen. Gebaut nach **O2**: neue Katalog-Klasse `AUSNAHME_TAGESGROESSE` („Tagesgröße ohne Kanal"), `_emob_felder`
aus dem Katalog abgeleitet, der Schreiber lässt die Klasse still aus. Verworfen: O1 (Monat hätte sich geändert, gegen §2.6), O3 (Snapshot-Liste
an der Registry vorbei, gegen die N-259-Bauform). Ebenfalls beim Bau gemessen: an einem **Kanal-Tag** kommt die Tagesbilanz aus der
Kanal-Komposition — V2H wird deshalb über `tagesbilanz.mit_v2h_entladung` einmal nach dem Mischen angewandt (B5).

Es gibt **keinen Prüfdatensatz mit V2H** (weder im Lab noch beim Maintainer). Der Nachweis läuft über Tests mit Snapshot-Doubles;
der erste Realbetrieb ist der nächste V2H-Melder — das steht so auch in der Antwort an ihn.

### 2.5 Konsumenten, die den neuen Wert sehen

`TagWerteResponse` wird gelesen von `CockpitTagV4.tsx`, `CockpitMonatV4.tsx` (Tagesliste), `AuswertungenTabelleV4.tsx` und
`hooks/useTagesWerte.ts` — ein optionales Feld mehr bricht keinen davon. Der MQTT-Monatsvorschlag (`monatsabschluss/views.py`)
bekommt den V2H-Monatswert über `mqtt_monats_mengen` von selbst; ob der HA-Monatsvorschlag das Feld ebenfalls vorschlägt, ist beim Bau
zu prüfen und zu benennen, nicht zu bauen.

### 2.6 Grenzen — bewusst nicht gebaut

- **Kein Stundenwert** (E2): Stundentabelle und Stundenkurve zeigen V2H nicht; die Summe der Stundenverbräuche liegt um die
  Rückspeisung unter dem Tages-Gesamtverbrauch. Die Tagesbilanz ist die Quelle der Wahrheit.
- **Laufender Monat aus Tagen** (`aktueller_monat/aggregation.py:727-728`): V2H bleibt 0 bis zum Monatsabschluss — wie heute.
  Folge: im laufenden Monat weicht die Monatszahl von der Summe der Tage um V2H ab. Wenn ein Symmetrie-Test den laufenden Monat verlangt,
  hält die Bau-Sitzung an (der Weg wäre `TagesMonatsSumme` → Monats-Fakten-Rückfall, drei Stellen).
- **Leistungspfad**: der Live-Tagesverlauf und damit die Stundenkurve des Tages zeichnen die Entladung weiter als Senke
  (Entscheid 28.09.2026, `live_komponenten_builder.py:660-662`). Dieselbe Unstimmigkeit besteht heute schon auf der Live-Seite neben der
  korrekten Live-Bilanz.
- **Auswertungen → Tabelle**: keine V2H-Spalte, weder Monat noch Tag (`lib/werte/registry.ts` kennt keinen V2H-Schlüssel) — unverändert.
- **Standalone ohne Boundary-Rollup**: der Tageswert bleibt «—»; einen Rückfall auf den Leistungspfad gibt es nicht, weil der
  Leistungspfad V2H als Senke trägt.
- **Tagesdetail** (`TAGESDETAIL_AUSGABE`, `TagDetailResponse`): kein zusätzlicher Boundary-Wert; der Rollup reicht.

### 2.7 Gates und Zeitpunkt

**Gebaut am 13.10.2026 (Commit `2ce068fa`), ausgeliefert mit v4.1.7** — das Päckchen wurde auf Entscheid Gernots vor das Release gezogen,
zusammen mit #427 Punkt 2 (Netzladung des Speichers im laufenden Monat). Ursprünglich geplant als eigenes Päckchen nach v4.1.7, ohne Termin
(Wartungsmodus: ohne Vorlage, Gegenprüfung, Nachmessung, Golden Master). Gates wie in
`CLAUDE.md`: berührte Backend-Tests plus die Wächter (`test_wurzelmuster_konformitaet.py`, `test_snapshot_felder_sot_konformitaet.py`,
`test_jedes_feld_hat_eine_auswertung.py`), Frontend `lint`/`tsc`/`test`, `sync-help.sh` und Website-Build, volle Backend-Suite am Ende.
Kein Fund, keine Fund-ID: der Punkt ist ein Wunsch aus #110; der Commit nennt «#110 V2H-Tageswert».

## 3. Verlauf

- **12.10.2026** — Triage auf Gernots Frage, ob beide Punkte bis zum Release 4.1.7 lösbar sind: nein (Messung §1.3 und §2.2–2.4).
- **13.10.2026** — Entscheid Gernot: #110 bleibt offen, beide Punkte bleiben «gesammelt» und verweisen auf dieses Dokument;
  «Gesamt» nicht gebaut; V2H-Tageswert wird gebaut mit E1–E3.
- **13.10.2026 (abends)** — Gernot hält das Release 4.1.7 an und zieht den V2H-Tageswert vor: gebaut nach O2 und B5-a (Baunotiz §2.4),
  Commit `2ce068fa`; mit v4.1.7 ausgeliefert (Release-Commit `ebe90eb7`). «Gesamt» (§1) bleibt ungebaut.
