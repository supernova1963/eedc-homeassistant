# CLAUDE.md — eedc (Konsolidierungs- und Wartungsmodus seit 10.10.2026)

> Das bisherige, ausführliche CLAUDE.md liegt unter [docs/ARCHIV-CLAUDE-2026-10-10.md](docs/ARCHIV-CLAUDE-2026-10-10.md).
> Es beschreibt den Prüfprozess (Vorlage → Gegenprüfung → Opus-Bau mit Halten → Nachmessung → Golden Master → Matrix-Form),
> der am 10.10.2026 **ausgesetzt** wurde (Entscheid Gernot: wirtschaftlich nicht mehr tragbar für ein Solo-Open-Source-Projekt).
> Was dort als Regel steht, gilt als **Hintergrundwissen**, nicht als Pflicht — außer den hier genannten Punkten.

## Was eedc ist

**eedc** (Energie Effizienz Data Center) — PV-Analyse als HA-Add-on und Standalone. FastAPI + React + SQLite.
Detail: [Architektur](docs/ARCHITEKTUR.md) · [Entwicklung](docs/DEVELOPMENT.md) · [Berechnungen](docs/BERECHNUNGEN.md) ·
[ADR-001 Layer](docs/ADR-001-BERECHNUNGS-LAYER.md) · [ADR-002 Invarianten](docs/ADR-002-WURZELMUSTER.md) · [Style-Guide](docs/KONZEPT-STYLE-GUIDE.md).
Version: [CHANGELOG.md](CHANGELOG.md) (oberster Abschnitt) bzw. `eedc/backend/core/config.py::APP_VERSION`.

| Repo | Rolle |
| --- | --- |
| **eedc-homeassistant** (dieses, `/home/gernot/claude/eedc-homeassistant`) | Source of Truth, HA-Add-on, Website, Docs — **hier arbeiten** |
| **eedc** (`/home/gernot/claude/eedc`) | Standalone-Spiegel, **nur** per `scripts/release.sh` |
| **eedc-community** (`/home/gernot/claude/eedc-community`) | Community-Server, eigenes Repo; Deploy nur mit einem Add-on-Release |

## Arbeitsmodus (Entscheid Gernot 10.10.2026)

1. **Eingang nur Melder** (GitHub-Issues, simon42-Forum T89667, photovoltaikforum T258098, community-smarthome T10057, PN) **und
   die Konsolidierungsliste** `~/.claude/plans/KONSOLIDIERUNG-LISTE-2026-10.md` (von Gernot triagiert: beheben · dokumentieren · verwerfen).
   Keine Matrix-Sweeps, keine Beobachtungsliste abarbeiten, keine Refactoring-Serie, kein HA-Bauform-S3, keine Vorhaben aus dem Index.
2. **Fund nur bei Wirkung:** falsche Zahl, die ein Anwender sieht · Absturz · Datenverlust. Sonst Antwort oder Handgriff.
3. **Ein Päckchen = eine Opus-Sitzung** (3–5 Punkte), ohne Vorlage, ohne Gegenprüfung, ohne Nachmessung, ohne Golden Master,
   ohne neue Matrix-Form, ohne neuen Wächter. Bestehende Wächter und Matrizen laufen in CI mit.
4. **Fable nur zur Triage** auf Gernots Ruf, kurz.
5. **Commit je Päckchen mit expliziten Pfaden** (nie `git add -A`); **Push erlaubt** (CI prüft, 9 min); Release gebündelt
   (wöchentlich im Konsolidierungsmonat, danach quartalsweise oder bei Melder-Fix) per `scripts/release.sh <version>` auf Gernots Wort.
6. **Nichts öffentlich ohne Go** — Issue-Kommentare, Foren-Texte, #110-Änderungen legt die Session vor, Gernot entscheidet (GitHub
   darf die Session nach dem Go selbst posten; Foren postet Gernot).
7. **Doku gehört zum Fix:** CHANGELOG `[Unreleased]`, `docs/WAS-IST-NEU.md`, betroffenes Handbuch; `./scripts/sync-help.sh` spiegelt.

## Entwicklung und Gates

```bash
cd eedc && source backend/venv/bin/activate          # Python 3.11
uvicorn backend.main:app --reload --port 8099         # Backend;  Frontend: cd eedc/frontend && npm run dev
# Gate je Päckchen (lokal):
python -m pytest backend/tests/<berührte Dateien> -q  # plus die Wächter: backend/tests/test_wurzelmuster_konformitaet.py
cd eedc/frontend && npm run lint && npx tsc --noEmit && npm run test
./scripts/sync-help.sh && (cd website && npm run build)   # nur bei Doku-Änderung
# Volle Backend-Suite (≈ 9 min, -n 3) vor jedem Release; CI fährt sie bei jedem Push in UTC und Pacific/Auckland (je -n 4).
```

Vor einem Release: Kandidat ins HAOS-Lab (`bash ~/.claude/plans/lab-werkzeug/lab-rc.sh <rc> <version>`, Lab `10.100.1.167`),
Gernot klickt durch, dann `./scripts/release.sh <version>` (bumpt fünf Versionsdateien, taggt, pusht beide Repos, baut Images).
Danach `gh run list` in **beiden** Repos prüfen. Galerie-Screenshots nur auf Nachfrage (`scripts/galerie-screenshots.mjs`).
Produktiv-Box `10.100.1.13:8099` **nur lesen**; `eedc/data/eedc.db` nie anfassen; kein Serverstart gegen die Demo-DB mit Broker.

## Code-Regeln, die bleiben (kurz; Begründung im Archiv)

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

## Community

Client ↔ Server nur über `backend/api/routes/community.py` (Proxy); Datenmodell-Änderungen in beiden Repos (`community_service.py`
↔ `eedc-community/backend/schemas.py::MonatswertInput`). Der Server rechnet nicht nach.

## Roadmap

GitHub [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) — nur auf Gernots Aufforderung ändern.
