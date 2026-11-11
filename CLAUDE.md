# CLAUDE.md — eedc (Pflegebetrieb seit 11.10.2026)

> Das bisherige, ausführliche CLAUDE.md liegt unter [docs/ARCHIV-CLAUDE-2026-10-10.md](docs/ARCHIV-CLAUDE-2026-10-10.md).
> Es beschreibt den Prüfprozess (Vorlage → Gegenprüfung → Opus-Bau mit Halten → Nachmessung → Golden Master → Matrix-Form),
> der am 10.10.2026 **ausgesetzt** wurde (Entscheid Gernot).
> Die Konsolidierung (10./11.10., 31 Funde, v4.1.6) war der Abschluss der aktiven Phase; seitdem **Pflegebetrieb**.
> Was dort als Regel steht, gilt als **Hintergrundwissen**, nicht als Pflicht — außer den hier genannten Punkten.

## Was eedc ist

**eedc** (Energie Effizienz Data Center) — PV-Analyse als HA-Add-on und Standalone. FastAPI + React + SQLite.
Detail: [Architektur](docs/ARCHITEKTUR.md) · [Entwicklung](docs/DEVELOPMENT.md) (mit **Bereichs-Karte**: Bereich → Module → Tests → GM → Handbuch) · [Berechnungen](docs/BERECHNUNGEN.md) ·
[ADR-001 Layer](docs/ADR-001-BERECHNUNGS-LAYER.md) · [ADR-002 Invarianten](docs/ADR-002-WURZELMUSTER.md) · [Style-Guide](docs/KONZEPT-STYLE-GUIDE.md).
Version: [CHANGELOG.md](CHANGELOG.md) (oberster Abschnitt) bzw. `eedc/backend/core/config.py::APP_VERSION`.

| Repo | Rolle |
| --- | --- |
| **eedc-homeassistant** (dieses, `/home/gernot/claude/eedc-homeassistant`) | Source of Truth, HA-Add-on, Website, Docs — **hier arbeiten** |
| **eedc** (`/home/gernot/claude/eedc`) | Standalone-Spiegel, **nur** per `scripts/release.sh` |
| **eedc-community** (`/home/gernot/claude/eedc-community`) | Community-Server, eigenes Repo; Deploy nur mit einem Add-on-Release |

## Arbeitsmodus Pflege (Entscheid Gernot 10./11.10.2026, präzisiert 15.10.2026)

> **Einstieg jeder Sitzung: `~/.claude/plans/STAND.md`** (ein Blatt, wird überschrieben; Stand, laufende Stufe, nächste Etappe, Release-Entscheid).

> **Was der Modus bezweckt (Gernot 15.10.):** Token sparen an zwei Stellen — die Session verspricht Meldern nicht mehr schnell
> eedc-Lösungen für externe Probleme, Sonderlocken und Erweiterungswünsche, und Gernot hält sich mit neuen Ideen zurück.
> **Fehlerbeseitigung läuft weiter.** Das Konzept «eedc nach HA-Bauform» ist gebaut (S1–S5, Releases 4.1.3 · 4.1.8 · 4.1.9; die
> Matrix-xfail sind abgebaut). Eine künftige Bauform-Etappe behält den Stufen-Apparat (Golden Master über die Kopien, Lab,
> Nachmessung), weil sie jede Tages-/Stundenzahl anfasst. Der Modus ist kein Stopp, sondern eine Bremse für Zusagen und Neuvorhaben.
>
> **Präzisiert 23.10.2026 (Gernot, bis auf Widerruf): die Bremse gilt nur nach außen** — Zusagen, Melder-Antworten, Sonderlocken,
> Erweiterungswünsche. Intern entscheidet Gernot je Vorhaben über den Einsatz des Budgets; «keine Refactoring-Serie» (Nr. 1) heißt
> seitdem «nur nach Gernots Go» (so das Komplexitäts-Paket RF-29 … RF-39 vom 23./24.10.2026 mit dem Apparat der RF-Serie:
> Golden Master je Funktion, Fable-Nachmessung je Sitzung, Gegenprüfung bei Wächter-Berührung).

1. **Eingang nur Melder** (GitHub-Issues, simon42-Forum T89667, photovoltaikforum T258098, community-smarthome T10057, PN — **Gernot
   liest die Kanäle selbst und gibt den Beitrag weiter; keine routinemäßigen Melder-Sweeps durch Agenten**) **und das Fundregister**
   (`~/.claude/plans/fundregister.yaml` — das EINE Register; Stand 11.10.: 0 offen). Keine zweite Liste neben dem Register. Wünsche
   stehen in #110 «Gesammelt» ohne Termin.
   Keine Matrix-Sweeps, keine Beobachtungsliste abarbeiten, keine Refactoring-Serie, keine neuen Vorhaben aus dem Index.
2. **Fund nur bei Wirkung:** falsche Zahl, die ein Anwender sieht · Absturz · Datenverlust. Sonst Antwort oder Handgriff.
   **Die Register-Disziplin gilt unverändert** (Gernot 10.10.): kein Eintrag ohne Analyse am HEAD, drei Tore (gemessen · abgeglichen ·
   Folge nennbar und „schon gedeckt?"), Klassen-Dreifrage, Band, Einwertung durch den Master und Entscheid Gernot — vorher ist es
   `verdacht`. Keine Sammelaufnahme, keine Sammelkategorie, kein Doku-Abschnitt ohne Genehmigung. Reduziert ist nur der Bau-Apparat (Nr. 3).
   **Melder-Antwort beginnt beim Daten-Checker (Gernot 11.11.2026):** erst prüfen, ob ein Befund mit Lösungsweg (`code` im Katalog
   `services/daten_checker/handgriffe.py`, Datei `docs/daten-checker/<code>.md`, Handbuch «Daten-Checker» §4) den Fall deckt, und den Melder
   darauf verweisen — Handgriff mit dem Knopf-Text, Schritte des Lösungswegs. Deckt kein Befund den Fall und hat er Wirkung, gehört zum Fix
   **ein neuer Befund** (Code, Ziel oder Aktion, Lösungsweg-Datei, Wächter W-1/W-2/W-13/W-14), nicht nur die Korrektur.
3. **Ein Fund-Päckchen = eine Opus-Sitzung** (3–5 Punkte), ohne Vorlage, ohne Gegenprüfung, ohne Nachmessung, ohne Golden Master,
   ohne neue Matrix-Form, ohne neuen Wächter. Bestehende Wächter und Matrizen laufen in CI mit. **Eine Bauform-Etappe** behält
   den Apparat des Bauplans (Golden Master, Lab, `nachmesser-fable`).
   **Gekürzt (Gernot 16.10.2026, nach vier Runden à 0,5–1,5 h):** Punkte **sammeln und in einem Lauf** bauen statt serieller Runden;
   Melder-Eingänge warten bis zum nächsten Päckchen, außer P1. **Keine Sprengsätze.** Golden Master **nur**, wenn Monats-Fakten oder
   der Layer (`core/berechnungen/`) berührt sind. **Volle Suite einmal am Ende durch die Bau-Session**; der Master liest die archivierte
   Summenzeile und fährt sie **nicht** noch einmal. Komplexität prüft der Wächter in der Suite, keine Einzelmessung im Bericht.
   **Bericht: Kopf · je Punkt drei Zeilen (gemessen · gebaut · Checker) · eine Gate-Zeile · Commit-Paket** — keine Etappen-Prosa,
   Ablage nur für Messskripte, die ein Register-Eintrag nennt.
4. **Fable nur zur Triage** auf Gernots Ruf, kurz.
5. **Commit je Päckchen mit expliziten Pfaden** (nie `git add -A`); **kein Push, kein Tag außerhalb von `scripts/release.sh`** (Gernot
   10.10.: mehrere Repos, nur das Release hält sie gleich; «pushen ohne taggen» hat Probleme gemacht). Volle Backend-Suite lokal am Ende
   jedes Päckchens mit gekürzter Ausgabe (`| tail -3`). Release, wenn ein Melder-Fix drin ist, sonst quartalsweise — per `scripts/release.sh <version>` auf Gernots Wort.
6. **Nichts öffentlich ohne Go** — Issue-Kommentare, Foren-Texte, #110-Änderungen legt die Session vor, Gernot entscheidet (GitHub
   darf die Session nach dem Go selbst posten; Foren postet Gernot).
7. **Doku gehört zum Fix:** CHANGELOG `[Unreleased]`, `docs/WAS-IST-NEU.md`, betroffenes Handbuch; `./scripts/sync-help.sh` spiegelt.

## Entwicklung und Gates

```bash
cd eedc && source backend/venv/bin/activate          # Python 3.11
uvicorn backend.main:app --reload --port 8099         # Backend;  Frontend: cd eedc/frontend && npm run dev
# Gate je Päckchen (lokal):
ruff check backend                                    # Lint-Gate (F + E9, eedc/ruff.toml), läuft auch in CI
python -m pytest backend/tests/<berührte Dateien> -q  # plus die Wächter: backend/tests/test_wurzelmuster_konformitaet.py
cd eedc/frontend && npm run lint && npx tsc --noEmit && npm run test
./scripts/sync-help.sh && (cd website && npm run build)   # nur bei Doku-Änderung
# Volle Backend-Suite (≈ 25 min mit `-n 6` auf der 8-Kern-Box, `-n 3` ≈ 28 min; Stand 9.11.2026, 12 107 Tests) am Ende jedes Päckchens, Ausgabe `| tail -3`; CI fährt sie beim Release-Push in UTC und Auckland.
# Summenzeile = `N passed` und sonst nichts — skipped/xfailed/warnings sind Arbeitsvorrat, kein Normalstand (Gernot 24.10.2026);
# benannte Matrix-Grenzen zählen grün und stehen im Register der Matrixdatei (test_pv_achse_matrix.py::URSACHE/ROT).
```

Vor einem Release: Kandidat ins HAOS-Lab (`bash ~/.claude/plans/lab-werkzeug/lab-rc.sh <rc> <version>`, Lab `10.100.1.167`),
Gernot klickt durch, dann `./scripts/release.sh <version>` (bumpt fünf Versionsdateien, taggt, pusht beide Repos, baut Images).
Danach `gh run list` in **beiden** Repos prüfen. Galerie-Screenshots nur auf Nachfrage (`scripts/galerie-screenshots.mjs`).
Produktiv-Box `10.100.1.13:8099` **nur lesen**; `eedc/data/eedc.db` nie anfassen; kein Serverstart gegen die Demo-DB mit Broker.

## Code-Regeln, die bleiben (kurz; Begründung im Archiv)

- **Übersicht zuerst, dann Code-Ort:** eine Größe zuerst in `docs/UEBERSICHT-GROESSEN.md` nachschlagen (Bedeutung, Herkunft,
  Code-Ort, Regel-Anker, Test). Die drei erzeugten Referenzen (`UEBERSICHT-GROESSEN.md`, `SENSOR-REFERENZ.md`, `MQTT_INBOUND.md`) nie
  von Hand ändern; nach Änderungen an ihren Quellen (u. a. Feld-Registry, `feld_auswertungen.py`, Kanal-Katalog, `monats_fakten/fakten*.py`,
  `lib/werte/registry.ts`, `ha_sensors_export.py`, `mqtt_topic_registry.py`, BERECHNUNGEN-Überschriften, Bausteine `docs/sensor-referenz/`,
  `docs/mqtt-inbound/`) `./scripts/groessen-uebersicht.sh && ./scripts/sync-help.sh` (der Wächter sagt es sonst). Hand-Wissen nur in
  `groessen_hand.yaml`.
- **Monatsgrößen nur aus den Monats-Fakten** (`services/monats_fakten/`, ADR-002/P10) — nie `InvestitionMonatsdaten` selbst falten.
- **`Monatsdaten.pv_erzeugung_kwh` nur über `lade_pv_je_monat`/`pv_summe_je_monat` lesen** (P7), nie programmatisch füllen.
- **Kennwerte über `core/investition_kennwerte.py`** (`get_erzeuger_kwp` statt `inv.leistung_kwp`, P3-a).
- **Eine Formel, ein Ort:** Aggregat-Formeln in `core/berechnungen/`; CO₂ nur über `berechne_co2_bilanz` (DI-2); Ersparnis/USt/CO₂
  auf `eigenverbrauch_ohne_verluste_kwh` (P15); der Client rechnet nichts (`check:co2-roh`, `check:kennwert-roh`).
- **SQLAlchemy JSON:** nach Änderung `flag_modified(obj, "feld")`. **0-Werte:** `is not None`, nie `if val`.
- **Schreibrouten:** `Depends(get_db, scope="function")` (N-530). **`log_activity(..., db=db)`** in Funktionen mit Sitzung (N-532).
- **Design:** keine Hex-Farben außerhalb `lib/colors.ts` (`npm run check:design` = 0); eine Komponenten-Klasse = eine SoT-Komponente;
  Typ-Reihenfolge `INVESTITION_TYP_ORDER`; „eedc" klein; „% " mit Leerzeichen.
- **Zeitzone:** eedc folgt HA, kein Pin. **Legacy `ha_sensor_*`-Spalten** bleiben im Model.
- **Rechenstellen (seit Päckchen Z, 9.11.2026):** in Routen, Services und Sichten entsteht keine neue Formel der Gestalten Quote, Differenz oder Produkt
  zweier Fach-Größen, Menge × Preis, Menge × Zahl — sie gehört in `core/berechnungen/` (Backend) bzw. als Feld in die Antwort (Client zeigt). Wächter
  `backend/tests/test_dezentrale_rechenstellen.py` (Werkzeug `werkzeug_rechenstellen.py`, Baseline `rechenstellen_baseline.txt`) und
  `npm run check:rechenstellen` (`frontend/rechenstellen-baseline.txt`); beide Baselines schrumpfen nur, ein verwaister Eintrag ist rot. Erlaubt bleiben
  Einheitenumrechnung, Zähler, Summen, Verteilung nach Anteil und die Monats-Fakten selbst (ADR-002/P10).
- **Kognitive Komplexität:** Schwelle 50 je Funktion, keine über 100; Wächter `backend/tests/test_kognitive_komplexitaet.py`
  mit Baseline, die nur schrumpft (Neuschreiben per Befehl im Docstring). Ein Neuzugang über 50 wird aufgeteilt (Bauform RF-1).
  Datei-Kriterium 900 netto-Codezeilen: keine neue Datei darüber, eine Bestandsdatei wächst höchstens 2 % — Wächter
  `backend/tests/test_dateilaenge.py` und `npm run check:dateilaenge`, Baselines schrumpfen nur.
- **Abhängigkeiten:** Absicht in `backend/requirements.txt`, ausgeliefert wird `requirements.lock` (Anleitung im Kopf der
  txt; nach jeder Änderung neu erzeugen). Das Standalone-Dockerfile liegt im Spiegel `eedc` und braucht dieselbe Änderung von Hand.

## Community

Client ↔ Server nur über `backend/api/routes/community.py` (Proxy); Datenmodell-Änderungen in beiden Repos (`community_service.py`
↔ `eedc-community/backend/schemas.py::MonatswertInput`). Der Server rechnet nicht nach.

## Roadmap

GitHub [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) — nur auf Gernots Aufforderung ändern.
