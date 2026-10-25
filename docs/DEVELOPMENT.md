
# EEDC Development Guide

**Stand: 2026-08-07** — gegen den Baum gemessen, nicht fortgeschrieben.
**Nachgemessen am 2026-08-11:** die Modul-Liste unter `core/berechnungen/` (36 Module, maschinell gegen das Verzeichnis geprüft) und die `services/`-Neuzugänge des Wirtschaftlichkeits- und Cloud-Import-Pakets. Die übrigen Kapitel tragen weiterhin den Stand vom 07.08.

> **Dieses Dokument trägt bewusst keine Versionsnummer.** Der Versions-SoT ist
> [CHANGELOG.md](../CHANGELOG.md) (oberster released Abschnitt) bzw.
> `eedc/backend/core/config.py::APP_VERSION`; `scripts/release.sh` bumpt `docs/` **nicht**. Eine
> Zahl an dieser Stelle veraltet daher garantiert — genau daran ist der vorige Kopf gescheitert
> (er stand bis 2026-08-07 auf „v3.24.1, April 2026", während v4.0.10 ausgeliefert war).
>
> **Wer die Oberfläche ändert**, findet die verbindlichen Regeln nicht hier, sondern in den drei
> SoT-Regimen — siehe [Die drei SoT-Regime](#die-drei-sot-regime) weiter unten. Dieses Dokument
> beschreibt **Einrichtung, Struktur und Werkzeuge**, keine Fachregeln.

---

## Voraussetzungen

- Python 3.11+
- Node.js 20+ (empfohlen via nvm; `eedc/frontend/.nvmrc` enthält `20`)
- Docker/Podman (für Container-Tests)

## Schnellstart

### 1. Repository klonen

```bash
git clone https://github.com/supernova1963/eedc-homeassistant.git
cd eedc-homeassistant
```

### 2. Backend einrichten

```bash
cd eedc/backend

# Virtual Environment erstellen (einmalig)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren — mit dem Lock als Constraints, damit das Dev-venv dieselben
# Versionen trägt wie die Images (requirements.lock, erzeugt aus requirements.txt)
pip install -c requirements.lock -r requirements-dev.txt
```

> **Abhängigkeiten ändern:** Absicht in `requirements.txt` eintragen (Untergrenze, bekannte Brüche
> als Kommentar), dann das Lock neu erzeugen — die Anleitung steht im Kopf von `requirements.txt`
> (`uv pip compile … --universal`, Python 3.11, amd64 + aarch64). Beide Dockerfiles, der
> Prod-Paritäts-Check in `scripts/smoke.sh` und die CI installieren **nur das Lock**; ein
> Upstream-Release ändert damit nichts am Image, bis jemand das Lock bewusst neu erzeugt. Das
> Standalone-Dockerfile liegt im Spiegel-Repo `eedc` und wird vom Release-Skript nicht überschrieben.

### 3. Frontend einrichten

```bash
cd eedc/frontend

# Node 20 aktivieren (falls nvm genutzt wird)
nvm use 20

# Dependencies installieren (einmalig)
npm install
```

### 4. Entwicklungsserver starten

**Terminal 1 (Backend):**

```bash
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099
```

**Terminal 2 (Frontend):**

```bash
cd eedc/frontend && npm run dev
```

**URLs:**

- Frontend: http://localhost:3000 (Vite Dev Server, Proxy zu Backend)
- API Docs: http://localhost:8099/api/docs
- ReDoc: http://localhost:8099/api/redoc

---

## Docker/Podman Build

```bash
cd eedc

# Image bauen
docker build -t eedc .
# oder: podman build -t eedc .

# Container starten
docker run -p 8099:8099 -v $(pwd)/data:/data eedc
# oder: podman run -p 8099:8099 -v $(pwd)/data:/data eedc

# Browser öffnen
open http://localhost:8099
```

---

## Home Assistant Add-on Test

Es gibt zwei Wege, und sie haben verschiedene Zwecke.

### A) Veröffentlichten Stand prüfen (der Weg, den auch Anwender gehen)

1. Repository zu HA Add-on Repositories hinzufügen:
   - Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories
   - URL: `https://github.com/supernova1963/eedc-homeassistant`
2. Add-on installieren und starten
3. Über Sidebar "eedc" öffnen

Damit testet man **das, was schon draußen ist** — nützlich zur Reproduktion einer Meldung,
nutzlos als Abnahme vor einem Release.

### B) Release-Kandidat prüfen, BEVOR er veröffentlicht wird (HAOS-Test-Lab)

**Das ist der Pflichtweg vor jedem Release** (Praxis seit 2026-09-09). Er fängt die Klasse
Fehler, die weder `pytest` noch ein `check:*`-Skript sehen kann, weil sie erst entsteht, wenn
ein **echter Supervisor** die `config.yaml` einliest oder wenn jemand klickt. Beispiel aus der
Praxis: der Supervisor meldet `map`-Optionen als veraltet — das sieht kein Gate im Repo.

**Umgebung:** VM `haos-lab` unter `10.100.1.167` (HAOS mit Mosquitto, echter Recorder-Datenbank
und zwei Anlagen). Das Add-on liegt dort als **lokales** Add-on unter `/addons/eedc` und wird
**auf der Maschine gebaut**, nicht aus der Registry gezogen.

```bash
# 1. Den GETAGGTEN Stand spiegeln — nicht HEAD.
#    HEAD trägt nach einem Release oft schon Commits der Folgeversion; die gehören nicht in den Test.
git archive <tag> eedc/ | tar -x -C /tmp/rc
rsync -a --delete --exclude config.yaml.original /tmp/rc/eedc/ root@10.100.1.167:/addons/eedc/

# 2. GATE — die image:-Zeile MUSS in der Lab-Kopie fehlen.
#    Bleibt sie stehen, zieht der Supervisor das veröffentlichte ghcr-Image: man klickt dann
#    das ALTE Release durch und hält es für den Kandidaten.
ssh root@10.100.1.167 'cp /addons/eedc/config.yaml /addons/eedc/config.yaml.original
                       sed -i "/^image: /d" /addons/eedc/config.yaml
                       grep -c "^image:" /addons/eedc/config.yaml'      # muss 0 ergeben

# 3. Store neu einlesen und aktualisieren.
#    "ha addons reload" genügt NICHT — der Store-Cache bleibt sonst auf der alten Version stehen.
ssh root@10.100.1.167 'ha store reload && sleep 8 && ha apps update local_eedc'

# 4. Prüfen. Im Supervisor-Log muss "local/amd64-addon-eedc:<version>" stehen (lokaler Build, ca. 30 s).
ssh root@10.100.1.167 'curl -s http://local-eedc:8099/api/health
                       curl -s http://local-eedc:8099/api/ha-statistics/status'
```

**Der Kandidat braucht eine erhöhte Versionsnummer** — sonst sieht der Supervisor kein Update.

**Worauf zu achten ist:**

| | |
|---|---|
| `/api/health` | `status: healthy`, erwartete Version, `database: connected` |
| `/api/ha-statistics/status` | muss `SQLite` melden. Fällt es auf WebSocket zurück, ist der `config`-Mount kaputt |
| Supervisor-Log | `WARNING [supervisor.apps.validate]` — Meldungen zur `config.yaml` erscheinen **nur hier** |
| Oberfläche | die Sichten durchklicken, die das Release berührt hat |

Wer den Durchlauf auslässt, sagt das ausdrücklich; er ist an kein Auslöser-Muster gebunden.

---

## Repository-Workflow

**`eedc-homeassistant` ist die Source of Truth.** Alle Änderungen (Backend, Frontend, Docs, HA-Config) hier machen. Das `eedc`-Standalone-Repo ist ein Spiegel und wird per Release-Script synchronisiert.

Siehe [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md) für Details.

## Versionierung

Ein Release-Script bumpt alle Versionsdateien, committed, taggt, pusht, synchronisiert das
Standalone-Repo — und wartet zum Schluss, bis das Add-on-Image wirklich in der Registry liegt:

```bash
./scripts/release.sh <version>       # z. B. die nächste Patch-Nummer laut CHANGELOG
```

| Datei | Feld |
| ----- | ---- |
| `eedc/backend/core/config.py` | `APP_VERSION` |
| `eedc/frontend/src/config/version.ts` | `APP_VERSION` |
| `eedc/config.yaml` | `version` (HA Add-on) |
| `eedc/run.sh` | Startbanner |
| `eedc/Dockerfile` | `io.hass.version`-Label |
| `CHANGELOG.md` | neuer Abschnitt (**manuell vor** dem Release; wird nach `eedc/` kopiert) |

**HA-Nutzer erreicht nur ein Release.** Jede Änderung, die bei ihnen ankommen soll, braucht eine
neue Version — ein Commit auf `main` genügt nicht.

> ⚠ **Ein grüner Push ist kein ausgeliefertes Add-on.** `eedc/config.yaml` zieht ein **vorgebautes
> Image** von ghcr.io, das ein Workflow **nach** dem Tag baut. Zwischen Tag und fertigem Image
> zeigt der Store die neue Version, während die Installation `[404] manifest unknown` meldet — am
> 2026-08-06 klaffte dieses Fenster wegen einer GitHub-Actions-Störung sechs Stunden, und drei
> Anwender sind hineingelaufen. **Der Beleg einer Auslieferung ist das Image-Manifest**, nicht der
> grüne Push:
>
> ```bash
> REPO=supernova1963/eedc-homeassistant-amd64        # bzw. …-aarch64
> TOK=$(curl -s "https://ghcr.io/token?scope=repository:$REPO:pull" \
>   | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
> curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOK" \
>   -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json" \
>   "https://ghcr.io/v2/$REPO/manifests/<version>"
> ```
>
> **Beide Header sind Pflicht.** Ohne `Authorization` antwortet die Registry auf *jede* Version mit
> **401**, ohne den `Accept`-Header auf jede mit **404** — ein Prüfer, der das vergisst, meldet ein
> längst ausgeliefertes Image als fehlend. Gemessen am 2026-08-07: `4.0.10` → **200**, `4.0.9` →
> **200**, erfundene `4.0.99` → **404**. **Immer gegen die Vorversion und eine erfundene Version
> gegenprüfen**, bevor ein Alarm daraus wird.
>
> **Von Hand braucht man das nur noch zur Diagnose.** `release.sh` ruft als Schritt 7
> `scripts/warte-auf-image.sh <version>` auf, das genau diesen Abruf für **beide** Architekturen
> wiederholt (alle 20 s, längstens 40 Minuten) und erst danach „ausgeliefert" meldet. Das Script
> **weist sich vorher an der Vorversion aus** und bricht mit einer eigenen Meldung ab, wenn schon
> die als fehlend gemeldet wird — dann ist der Prüfer kaputt, nicht das Release. Exit-Codes:
> `0` ausgeliefert · `1` Wartezeit abgelaufen, Image fehlt wirklich · `2` Prüfer nicht
> vertrauenswürdig · `130` per Ctrl-C abgebrochen. Nach einer Störung (Actions-Ausfall,
> abgebrochener Build) startet man es **allein**, ohne das Release anzufassen:
>
> ```bash
> gh run list --repo supernova1963/eedc-homeassistant --workflow Release --limit 5
> gh run rerun <run-id> --repo supernova1963/eedc-homeassistant
> ./scripts/warte-auf-image.sh <version>
> ```

---

## Code-Konventionen

### Python (Backend)

- Type Hints verwenden; Docstrings für öffentliche Funktionen — und zwar mit dem **Warum**, nicht
  nur dem Was. Die Docstrings sind hier Trägermedium der Regeln (etwa „drei gleichwertige
  Transporte, eine Quelle" in `ha_statistics_service.py`).
- **`ruff check backend` ist ein Gate** (seit 14.10.2026, aus `eedc/`, Regeln in `eedc/ruff.toml`, in
  CI vor pytest): nur Pyflakes und Syntax (`F`, `E9`) — undefinierte Namen, geschattete Importe,
  Syntaxfehler. Vier Regeln stehen mit Baseline-Zahl als `ignore` in der Datei; wer eine einschaltet,
  misst erst und räumt dann auf. Stil-Regeln sind bewusst kein Gate, `black` gibt es nicht. Wer
  formatiert, formatiert von Hand im Stil der Umgebung — kein Repo-weiter Reformat-Lauf.
- **Kognitive Komplexität je Funktion: Schwelle 50, keine über 100** — gewächtert durch
  `backend/tests/test_kognitive_komplexitaet.py` mit eingecheckter Baseline, die nur schrumpfen darf
  (seit 14.10.2026). Die Schwelle ist bewusst 50 statt SonarQubes Voreinstellung 15: eedc wird mit
  KI-Unterstützung und Golden Masters gepflegt, und 50 ist nach der Refactoring-Serie die Größe, die eine
  Bau-Sitzung samt Kontext sicher in einem Zug ändert; gemessen am 14.10.2026 steigt die Dichte der
  Fund-Vermerke je 1 000 Zeilen von 12,7 (≤ 15) über 16,9 (16–50) auf 18,8 (51–100). Ausnahmen über 100
  (lineare Listen) stehen mit Grund im Wächter; ein Neuzugang über 50 wird aufgeteilt, nicht eingetragen.
  Stand nach dem Komplexitäts-Paket RF-29 … RF-39 (23./24.10.2026, Bauform RF-1, je Funktion Golden Master
  bitgleich): Baseline 60 → 48; über 80 liegen nur noch `main.py::lifespan` (Start-Orchestrierung, bewusst
  ausgelassen — ihr einziger Prüfstand ist der Lab-Start) und `migrate_emob_canonical_source` (Einmal-Migration)
  neben den beiden Migrations-Ausnahmen. Nächstes Band, falls je wieder gewollt: 66–80 (15 Funktionen).
- Neuer Code liest im Stil der Nachbarschaft: gleiche Kommentar-Dichte, gleiche Benennung.

### TypeScript (Frontend)

- `npx tsc --noEmit` ist das Gate, `npm run lint` (ESLint, `--max-warnings 0`) die Ergänzung.
- Funktionskomponenten mit Hooks; abgeleitete Logik in reine, testbare Funktionen ziehen
  (Beispiel `waehleDefaultMonat`) — eine reine Funktion lässt sich rot verifizieren, ein
  `useEffect` nicht.
- Keine Inline-Hex-Farben außerhalb `lib/colors.ts`, keine Roh-Controls, keine lokalen
  Label-/Wochentags-Arrays — dafür gibt es Wächter, und sie fangen es.

### Git Commits

Betreffs sind **deutsch und sagen die Wirkung**, nicht die Tätigkeit — `typ(bereich): aussage`:

```text
fix(boersenpreis): ein Tag ist der Tag der Marktzone, nicht der UTC-Tag
feat(cockpit-tag): der Speicher-Block nennt auch den Ladezustand
docs: Doku-Durchgang vor <version>
release: v<version>
```

Verwendete Typen: `fix` · `feat` · `docs` · `refactor` · `perf` · `build` · `release`. Der Body
nennt **Ursache, Wirkung und Melder** (Issue/Forum/PN) — er ist die einzige Stelle, an der später
noch steht, *warum* etwas so ist.

⚠ **Nur explizite Pfade committen, nie `git add -A`** — es laufen parallele Sessions im selben
Arbeitsbaum. `git push`, Tags und Versionsnummern passieren ausschließlich auf ausdrückliche
Anweisung bzw. über `scripts/release.sh`.

---

## Die drei SoT-Regime

Drei Dokumente regeln **verschiedene** Fragen. Sie werden nicht gemischt, und jedes hat ein
maschinelles Gegenstück, das im Zweifel gewinnt:

| Dokument | Regelt | Maschinelles Gegenstück |
| --- | --- | --- |
| [KONZEPT-STYLE-GUIDE.md](KONZEPT-STYLE-GUIDE.md) (Regel 0/0a) | **Darstellung** — Farben, Komponenten, Typografie, Chart-Konventionen | die `check:*`-Skripte (`eedc/frontend/scripts/check-*.mjs`) |
| [ADR-001-BERECHNUNGS-LAYER.md](ADR-001-BERECHNUNGS-LAYER.md) | **Schichtung** — *wo* eine Aggregat-Formel definiert wird (`core/berechnungen/`) | `backend/tests/test_berechnungs_layer_konformitaet.py` |
| [ADR-002-WURZELMUSTER.md](ADR-002-WURZELMUSTER.md) | **Invarianten P1–P10** — *was* ein Wert behaupten darf und woher er kommen muss | `backend/tests/test_wurzelmuster_*.py` |

Dazu die Oberflächen-Invarianten I1–I16 in [KONZEPT-IA-V4.md](KONZEPT-IA-V4.md) (IA, Park-Doktrin,
Redirect-Tabelle) und die Monatszeilen-Schicht in
[KONZEPT-MONATS-FAKTEN.md](KONZEPT-MONATS-FAKTEN.md) (ADR-002/P10).

**Backend-Wächter sind pytest, keine `check:*`-Skripte.** Alle `check:*` sind Node-Skripte im
Frontend. Zwei Ausnahmen bewachen die Client-Hälfte einer Backend-Regel: `check:kennwert-roh`
(ADR-002/P3-a) und `check:co2-roh` (ADR-001/DI-2).

**Regel 0a in einem Satz:** Wer etwas Sichtbares baut und dafür eine Regel/SoT vorfindet, wendet
sie an; existiert keine, aber wäre sinnvoll, wird sie **in derselben Arbeit** definiert und die
Zentrale erweitert; ein echter Einzelfall braucht Maintainer-Freigabe, Code-Kommentar und einen
Eintrag in der Ausnahmen-Liste.

---

## Kritische Code-Patterns

> Diese Liste ist der Einstieg. Die vollständige Fassung samt Fallstricken steht in
> [CLAUDE.md](../CLAUDE.md) §„Kritische Code-Patterns" und §„Bekannte Fallstricke" — dort wird sie
> gepflegt, hier stehen die vier, die am häufigsten getroffen werden.

### Monatswerte nur aus den Monats-Fakten (ADR-002/P10)

SoT ist `eedc/backend/services/monats_fakten/`. Wer eine abgeleitete Monatsgröße auswertet,
faltet `InvestitionMonatsdaten` **nicht selbst** — Zeitfilter, Dienstwagen-Filter und Auflösung
sind dort schon drin:

```python
from backend.services.monats_fakten import lade_monats_fakten, finanz_zeile_eingabe

fakten = await lade_monats_fakten(db, anlage_id, von=(2025, 1), bis=(2025, 12))
for f in fakten:
    pv = f.erzeugung.pv_kwh                    # RICHTIG
    bilanz = f.erzeugung.hinter_zaehler_kwh    # EV/Autarkie: inkl. BHKW & Co.
```

Ausgenommen sind Schreib-, Import- und Checker-Pfade. Der baumweite Wächter ist funktions-granular
(`test_wurzelmuster_konformitaet.py::test_p10_*`).

### Investitions-Kennwerte nur über den SoT-Helper (ADR-002/P3-a)

Die Nennleistung liegt je nach Herkunft in der **Spalte** `Investition.leistung_kwp` **oder** im
`parameter`-JSON — die Spalte allein zu lesen liefert bei Import-/Altbestand still 0:

```python
from backend.core.investition_kennwerte import get_erzeuger_kwp, get_pv_kwp, get_bkw_kwp

kwp = get_erzeuger_kwp(inv)          # RICHTIG — Typ-Dispatcher (BKW vs. PV-Modul)
kwp = inv.leistung_kwp               # FALSCH — auch als getattr() gewächtert
```

`leistung_kwp` ist ein **Mehrzweckfeld**: beim Speicher trägt dieselbe Spalte kWh, beim
Wechselrichter kW (AC). Die Helper gelten nur für Erzeuger-Typen, der Aufrufer filtert.

### SQLAlchemy JSON-Felder

SQLAlchemy erkennt Änderungen an JSON-Feldern nicht automatisch:

```python
from sqlalchemy.orm.attributes import flag_modified

# Nach Änderung an JSON-Feldern IMMER flag_modified aufrufen!
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")
db.commit()
```

### 0-Werte korrekt prüfen

```python
# FALSCH - 0 wird als False gewertet
if val:
    ...

# RICHTIG
if val is not None:
    ...
```

### Datenquellen-Trennung

- `Monatsdaten` = Nur Zählerwerte (Einspeisung, Netzbezug)
- `InvestitionMonatsdaten` = Alle Komponenten-Details

**Legacy-Felder nicht verwenden:**

- `Monatsdaten.pv_erzeugung_kwh` — Nutze `InvestitionMonatsdaten`
- `Monatsdaten.batterie_*` — Nutze `InvestitionMonatsdaten`

---

## Projektstruktur

> **Vollständig gegen den Baum erhoben (2026-08-07).** Wer eine Datei hinzufügt oder löscht, zieht
> diese Liste mit — sie ist der einzige Ort, an dem der Bestand am Stück steht. Die Zahlen in den
> Kommentaren sind Stichtagswerte; bei Abweichung gewinnt der Baum.

```text
eedc-homeassistant/                  ← Source of Truth (alle Änderungen hier)
├── README.md                        # Projekt-Übersicht
├── CHANGELOG.md                     # Versions-SoT (Master, hier editieren)
├── CLAUDE.md                        # Entwickler-/KI-Kontext, Kritische Patterns, Fallstricke
├── LICENSE · repository.yaml        # HA-Add-on-Repository-Manifest
│
├── scripts/
│   ├── release.sh                   # Release + Sync beider Repos (ein Script für alles)
│   ├── sync-help.sh                 # docs/ → In-App-Hilfe-Kopien (nach Doku-Arbeit!)
│   ├── sync-claude.sh               # CLAUDE.md/Kontext zwischen Rechnern
│   ├── backup-context.sh · kill-dev.sh · smoke.sh
│   ├── github-traffic.sh            # GitHub-Traffic-Statistik
│   ├── build-demo-db.sh · seed_demo_profil.py · seed-v4-sommer-2026.py
│   ├── reseed-v4-tag-demo.py        # Demo-Datenstände für Screenshots/Tests
│   └── check-live-snapshot-5min.sh  # Diagnose des 5-Minuten-Snapshot-Pfads
│
├── docs/                            # SoT für ALLE Dokumentation (Website + In-App-Hilfe)
│   ├── ADR-001-BERECHNUNGS-LAYER.md # Schichtung der Berechnungen
│   ├── ADR-002-WURZELMUSTER.md      # Invarianten P1–P10 + „gesichert durch"
│   ├── ARCHITEKTUR.md               # Technische Gesamtsicht
│   ├── BERECHNUNGEN.md              # Formel-Referenz
│   ├── DEVELOPMENT.md               # Diese Datei
│   ├── RELEASE-WORKFLOW.md          # Release-Prozess
│   ├── SETUP_DEVMACHINE.md          # Entwicklungsrechner einrichten
│   ├── BENUTZERHANDBUCH.md          # Endnutzer-Index
│   ├── HANDBUCH_INSTALLATION.md · HANDBUCH_BEDIENUNG.md · HANDBUCH_EINSTELLUNGEN.md
│   ├── HANDBUCH_INFOTHEK.md · HANDBUCH_ENERGIEPROFIL.md · HANDBUCH_PROGNOSEN.md
│   ├── HANDBUCH_DATEN_CHECKER.md
│   ├── KONZEPT-IA-V4.md             # IA + Oberflächen-Invarianten I1–I16 + Redirect-Tabelle
│   ├── KONZEPT-STYLE-GUIDE.md       # Darstellungs-SoT (Regel 0/0a)
│   ├── KONZEPT-MONATS-FAKTEN.md     # Monatszeilen-Schicht (ADR-002/P10)
│   ├── KONZEPT-BERECHNUNGS-LAYER.md
│   ├── KONZEPT-UNVOLLSTAENDIGE-WERTE.md
│   ├── KONZEPT-WALLBOX-EAUTO.md
│   ├── SENSOR-REFERENZ.md · MQTT_INBOUND.md · GLOSSAR.md · FLYER.md
│   ├── WAS-IST-NEU.md               # In-App-Hilfe „Was ist neu" (Anwender-Sprache)
│   └── archive/                     # Abgeschlossene Konzepte (nicht löschen, nicht pflegen)
│
├── website/                         # Astro Starlight (GitHub Pages, deutsch)
│   ├── astro.config.mjs             # Sidebar-Konfiguration
│   └── src/content/docs/            # generiert von sync-docs.sh — gitignored, NICHT editieren
│
└── eedc/                            # Die Anwendung (Spiegel des Standalone-Repos)
    ├── config.yaml                  # HA-Add-on-Konfiguration (zieht ein vorgebautes ghcr-Image!)
    ├── Dockerfile · run.sh          # HA-Container (Labels, jq, Startbanner)
    ├── docker-compose.yml           # Standalone-Deployment
    ├── icon.png · logo.png · CHANGELOG.md   # Kopie der Wurzel (per Script)
    │
    ├── backend/                     # FastAPI
    │   ├── main.py                  # Entry Point + alle include_router-Aufrufe
    │   ├── requirements.txt
    │   ├── api/routes/
    │   │   ├── aktueller_monat/         # Cockpit → Monat — Paket seit 18.09.2026: __init__ (Router, Sammler, Endpunkt als Orchestrator, Antwort) · schemas · vergleich · tkonto · aggregation · finanzen · waerme · komponenten
    │   │   │   └── quellen_leser.py     # Leser der Quellen-Kaskade ohne Uhr und Test-Naht (RF-12): gespeicherter Zweig, Kanal-Leser des Kalendermonats, gemessene 0, Wandlungsverluste
    │   │   ├── anlagen.py               # Anlagen-CRUD + Anlagenfoto
    │   │   ├── aussichten/              # Prognose-Aussichten — Paket seit 18.09.2026 (Vorlage 7)
    │   │   │   ├── __init__.py          # Fassade: Router-Bündel + Re-Export
    │   │   │   ├── prognose.py · trend.py · wetter.py   # kurzfristig/langfristig · Trend · Wettervorhersage
    │   │   │   ├── finanzen.py          # Finanz-Prognose (Auswertungen → Finanzen) — Orchestrator seit 18.09.2026 (Vorlage 7b)
    │   │   │   ├── finanz_eingaenge.py · finanz_rueckblick.py · finanz_prognose.py · finanz_zerlegung.py   # seine zehn Phasen
    │   │   │   └── schemas.py · basis.py   # Antwortmodelle · Konstanten, Anlagen-Lader
    │   │   ├── prognosen.py             # Prognose-Vergleich, Genauigkeits-Tracking
    │   │   ├── cockpit.py + cockpit/    # Übersicht · Komponenten · Nachhaltigkeit · Jahr
    │   │   ├── monatsdaten.py           # Monatsdaten-CRUD + Aggregation
    │   │   ├── monatsdaten_aggregiert.py  # Phasen der Monatszeile von /aggregiert (RF-27)
    │   │   ├── monatsabschluss/         # Monatsabschluss-Formular + Datenquellen-Status
    │   │   ├── investitionen/           # Komponenten, ROI, Stilllegung, Kennwerte
    │   │   │   ├── crud.py              # CRUD-Routen, Parent-Regel; hängt roi.py ein, re-exportiert (seit 18.09.2026, Vorlage 5)
    │   │   │   ├── schemas.py · roi.py  # Investitions-Schemas · ROI-Dashboard (Orchestrator), Gruppierung, Kennwert-Auflöser
    │   │   │   ├── roi_eingaenge.py · roi_pv.py · roi_standalone.py   # die Phasen des ROI-Dashboards (Vorlage 5b, 18.09.2026)
    │   │   │   ├── dashboards.py        # Fassade: Monatsdaten je Monat, CO2-Amortisation, Hub-Leer-Grund; hängt die Typ-Dashboards ein
    │   │   │   ├── dashboard_<typ>.py   # eauto · waermepumpe · speicher · wallbox · balkonkraftwerk · sonstiges (Vorlage 6, 18.09.2026)
    │   │   │   ├── dashboard_basis.py   # Preis-Mittelung, Monatsdaten-Response
    │   │   │   └── speicher_potential.py · speicher_sizing.py
    │   │   ├── strompreise.py           # Tarife, Spezialtarife, Gültigkeitsfenster
    │   │   ├── energie_profil/          # Tages-/Stundenprofile, Reaggregation
    │   │   │   ├── views.py             # Fassade: Router-Bündel + Re-Export (seit 18.09.2026, Vorlage 4)
    │   │   │   ├── tage.py · serien.py  # Tagesreihen · Stunden-/Serienreihen
    │   │   │   ├── tag.py · monat.py    # Tag-Detail/-Status · Monatsauswertung + ENERGIE_KATEGORIEN
    │   │   │   ├── waerme.py · prognose.py · diagnose.py
    │   │   │   ├── repair.py            # Reparatur-/Schreib-Endpunkte
    │   │   │   └── _shared.py           # Antwortmodelle, SerieInfo-Auflösung
    │   │   ├── live_dashboard.py        # Live-Kern (Fluss, Tagesverlauf, Börsenpreise)
    │   │   ├── live_mqtt_inbound.py · live_wetter.py
    │   │   ├── live_wetter_antwort.py   # Phasen der Wetter-Route `get_live_wetter` (seit 11.10.2026, RF-7)
    │   │   ├── mqtt_gateway.py · mqtt_presets.py   # beide unter /api/live eingehängt
    │   │   ├── datenquellen.py          # Datenquellen-Fläche (ein Feld = eine Quelle)
    │   │   ├── sensor_mapping.py        # HA-Sensor-Zuordnung (nur HA_MODE)
    │   │   ├── ha_integration.py · ha_statistics.py · ha_remote.py
    │   │   ├── ha_statistics_import.py  # Schreibweg des HA-Statistik-Sammelimports (seit 11.10.2026, RF-5)
    │   │   ├── ha_export/               # HA-Sensor-Export — Paket seit 18.09.2026 (Vorlage 8)
    │   │   │   ├── __init__.py          # Fassade: Router (Präfix /ha/export) + Re-Export
    │   │   │   ├── anlage_sensoren.py · investition_sensoren.py   # die zwei Rechenkerne (Anlage: Orchestrator seit 18.09.2026, Vorlage 8b)
    │   │   │   ├── anlage_energie.py · anlage_komponenten.py · anlage_sensorwerte.py   # seine neun Phasen
    │   │   │   └── schemas.py · emob.py · konfig.py · sensoren.py · mqtt.py   # Modelle · E-Mob-Pool · Routen
    │   │   ├── connector.py             # Geräte-Connectors (lokales Netz)
    │   │   ├── cloud_import.py          # Cloud-API-Import
    │   │   ├── custom_import/ · data_import.py · import_export/   # CSV/JSON/Demo/PDF
    │   │   ├── community.py             # Community-Proxy + Aufbereitung
    │   │   ├── wetter.py · solar_prognose.py · pvgis.py
    │   │   ├── korrekturprofil.py       # gelernte eedc-Prognose-Korrektur
    │   │   ├── daten_checker.py · system_logs.py · diagnostics.py
    │   │   ├── repair.py                # Reparatur-Werkbank (Tag/Zeitraum neu rechnen)
    │   │   ├── dokumentation.py         # PDF-Dokumente
    │   │   └── infothek.py              # Komponenten-Akten, Verträge, Datei-Upload (N:M)
    │   │
    │   ├── core/
    │   │   ├── config.py                # APP_VERSION + Settings
    │   │   ├── database.py              # Engine, Schema-Nachzug (ALTER TABLE), Daten-Migrationen
    │   │   ├── berechnungen/            # ADR-001: HIER und nur hier liegen Aggregat-Formeln
    │   │   │   ├── energie.py · verbrauch.py · tagesbilanz.py · kennzahlen.py
    │   │   │   ├── finanz_aggregat.py · einspeise_erloes.py · netzbezug_kosten.py
    │   │   │   ├── ust_eigenverbrauch.py · bkw_finanz.py · dienstliche_ladekosten.py
    │   │   │   ├── investitionskosten.py · amortisation.py · alternativkosten.py
    │   │   │   ├── kapitalrechnung.py · ertrag_zerlegung.py   # Nenner + Fortschritt je ROI-Zeile
    │   │   │   ├── phev_anteil.py · pv_anteil_ladung.py
    │   │   │   ├── speicher.py · speicher_simulation.py · speicher_wirtschaftlichkeit.py
    │   │   │   ├── pv_verteilung.py · spez_ertrag.py · wr_kappung.py · grundlast.py
    │   │   │   ├── prognose_final.py · prognose_korrektur.py · preis_rang.py
    │   │   │   ├── co2_amortisation.py · emob.py · counter.py · monatsfenster.py
    │   │   │   ├── imd_monatsaggregat.py · live_tagesverlauf_5min.py
    │   │   │   ├── slot_konvention.py   # Slot N = Energie [N-1, N) — Backward, baumweit
    │   │   │   ├── datenquellen.py · invarianten.py
    │   │   ├── investition_kennwerte.py # SoT für kWp/kWh je Typ (ADR-002/P3-a)
    │   │   ├── investition_parameter.py # gemeinsame Parameter-Keys mit dem Frontend
    │   │   ├── monats_luecken.py · source_priority.py · field_definitions/ (Paket seit 18.09.2026: keys · registry · bedingungen · karten · auswahl · reader · wp_strom, Fassade __init__)
    │   │   ├── wirtschaftlichkeit_defaults.py · ha_integrations_wissen.py
    │   │   ├── exceptions.py · log_buffer.py · calculations.py
    │   │
    │   ├── models/                  # SQLAlchemy
    │   │   ├── anlage.py             # Anlage + sensor_mapping (+ deprecated ha_sensor_*)
    │   │   ├── monatsdaten.py        # Monatsdaten (Zählerwerte) + InvestitionMonatsdaten
    │   │   ├── investition.py        # Investition + ERLAUBTE_PARENT_TYPEN (Parent-Regel-SoT)
    │   │   ├── strompreis.py · pvgis_prognose.py · korrekturprofil.py
    │   │   ├── tages_energie_profil.py  # TagesEnergieProfil + TagesZusammenfassung
    │   │   ├── sensor_snapshot.py    # stündliche Zähler-Snapshots (kWh-Quelle)
    │   │   ├── mqtt_live_snapshot.py · mqtt_energy_snapshot.py · mqtt_gateway_mapping.py
    │   │   ├── infothek.py · settings.py · api_cache.py
    │   │   ├── activity_log.py · data_provenance_log.py
    │   │
    │   ├── services/                # ~70 Module + Unterpakete
    │   │   ├── monats_fakten/        # ADR-002/P10: die Monatszeile wird EINMAL aufbereitet — seit 19.09.2026 ein Paket:
    │   │   │   ├── __init__.py       #   Fassade + Re-Exporte (lade_monats_fakten, MonatsFakt, WpFakten, …)
    │   │   │   ├── fakten.py         #   die Feldgruppen (Konzept §3) und MonatsFakt
    │   │   │   ├── fakten_wp.py      #   WpFakten
    │   │   │   ├── roh.py            #   _RohMonat (falte) und die Lader
    │   │   │   ├── tarif.py          #   Monatstarif je Stichtag (P8)
    │   │   │   ├── bau.py            #   _baue_fakt: Rohmonat → Fakt
    │   │   │   ├── laden.py          #   lade_monats_fakten (Orchestrator)
    │   │   │   └── ableitungen.py    #   finanz_zeile_eingabe, Kennzahlen, PV-Hinweis, PV-Ladeanteil
    │   │   ├── pv_monatswerte.py     # P7: lade_pv_je_monat / pv_summe_je_monat
    │   │   ├── preis_tag.py          # eine Schicht für Preis-Chart UND HA-Sensoren
    │   │   ├── energie_profil/       # Tages-Aggregation, Monats-Rollup, Tag-Status
    │   │   ├── snapshot/             # 5-Min-/Stunden-Snapshots + aggregator.py
    │   │   ├── daten_checker/        # Kategorien der Datenqualitäts-Prüfung
    │   │   │   └── datenquelle/      # Quellen · Tage · Speicher · Klima · Connector · Zeitzone · Rücksprung — Unterpaket seit 18.09.2026 (Vorlage 9)
    │   │   ├── cloud_import/         # Cloud-Provider (registry.py = SoT der Liste,
    │   │   │                         #   quellen.py = mehrere Quellen je Anlage, je mit Ziel-Gerät)
    │   │   ├── erzeuger_ziel.py      # SoT: welche Investition darf Ziel einer Quelle sein
    │   │   ├── connectors/           # Geräte-Connectors (registry.py = SoT der Liste)
    │   │   ├── import_parsers/       # CSV/JSON-Parser je Herkunft
    │   │   ├── wetter/               # Multi-Provider-Kaskade
    │   │   ├── pdf/                  # WeasyPrint + Jinja2 + SVG-Charts (builders/templates)
    │   │   ├── migrations/           # Daten-Migrationen, aufgerufen aus core/database.py
    │   │   ├── ha_statistics_service.py # LTS: DB-URL · Recorder-Datei · WebSocket
    │   │   ├── ha_statistics_ws.py   # recorder/statistics_during_period (ohne DB-Zugang)
    │   │   ├── ha_state_service.py · ha_connection.py · ha_energy_service.py
    │   │   ├── mqtt_client.py · mqtt_inbound_service.py · ha_mqtt_sync.py
    │   │   ├── community_service.py  # Payload für den Community-Server
    │   │   ├── prognose_service.py · solar_forecast_service.py · brightsky_service.py
    │   │   ├── kraftstoff_preis_service.py  # EU Oil Bulletin
    │   │   ├── scheduler.py          # APScheduler (Snapshot-, Prognose-, Korrektur-Jobs)
    │   │   └── …                     # vollständige Liste: ls eedc/backend/services/
    │   │
    │   ├── tests/                   # ~400 pytest-Dateien, darunter die Wächter:
    │   │   ├── conftest.py           # die `db`-Fixture (In-Memory je Test) + Netzsperre + Wegwerf-Produktiv-DB (nie data/eedc.db)
    │   │   ├── factories.py          # Modell-Factories + Szenarien (s. unten)
    │   │   ├── quellbaum.py          # EINE Dateiquelle für alle baumweiten Prüfer (s. unten)
    │   │   ├── ha_lts_helfer.py      # EINE Fassung des HA-Recorder-Schemas (s. unten)
    │   │   ├── test_wurzelmuster_konformitaet.py      # ADR-002 P1–P10, baumweit
    │   │   ├── test_berechnungs_layer_konformitaet.py # ADR-001
    │   │   ├── test_konformitaet_schwesterdateien.py  # Präfix-Cluster + Schwesterverweis
    │   │   └── test_netto_ertrag_vier_wege_symmetrie.py  # Symmetrie über vier Finanz-Sichten
    │   └── utils/
    │
    └── frontend/                    # React + TypeScript + Vite + Tailwind
        ├── package.json             # Skripte: dev · build · test · lint · check:* (Wächter)
        ├── vite.config.ts · vitest.config.ts   # vitest pinnt die Zeitzone Europe/Berlin
        ├── scripts/check-*.mjs      # die Darstellungs-Wächter (Regel 0/0a)
        ├── dist/                    # NICHT versioniert (.gitignore) — beide Dockerfiles bauen selbst
        └── src/
            ├── v4/                  # die ausgelieferte Oberfläche (IA-V4)
            │   ├── LayoutV4.tsx · ViewShell.tsx · AnlagenSelektor.tsx · ReloadButton.tsx
            │   ├── CockpitV4.tsx    # Wann? — Live · Tag · Monat · Jahr · Aussicht
            │   ├── CockpitLiveV4.tsx · CockpitTagV4.tsx · CockpitMonatV4.tsx
            │   ├── CockpitJahrV4.tsx · CockpitAussichtV4.tsx
            │   ├── TagRahmen.tsx · TagBilanz.tsx · TagKomponenten.tsx · TagesRail.tsx
            │   ├── TagStepper.tsx · TagLeerGrund.tsx · TagesverlaufChart.tsx
            │   ├── MonatRahmen.tsx · MonatBilanz.tsx · MonatsRail.tsx · MonatStepper.tsx
            │   ├── MonatAuswertungBloecke.tsx · KomponentenMonatsTabelle.tsx
            │   ├── JahrRahmen.tsx · JahrBilanz.tsx · JahresRail.tsx
            │   ├── JahrStepper.tsx · JahrVerlaufChart.tsx · JahrCo2Chart.tsx
            │   ├── JahrSpeicherTabelle.tsx · SpeicherVerlaufIST.tsx
            │   ├── KomponentenV4.tsx # Was? — je Gerätetyp Status → Verlauf → Vergleich → ROI
            │   ├── KomponentenTypV4.tsx · KomponentenSektionen.tsx · komponentenAdapter.tsx
            │   ├── komponentenAnalyse.tsx · KomponentenVergleich.tsx
            │   ├── KomponentenVerlaufChart.tsx · VergleichBalken.tsx
            │   ├── BkwHubBloecke.tsx · EAutoHubBloecke.tsx · WallboxHubBloecke.tsx
            │   ├── WaermepumpeHubBloecke.tsx
            │   ├── AuswertungenV4.tsx # Wie? — Finanzen · ROI · Prognose-vs-IST · CO₂ · Tabelle
            │   ├── AuswertungenFinanzenV4.tsx · AuswertungenRoiV4.tsx
            │   ├── AuswertungenPrognoseV4.tsx · AuswertungenCo2V4.tsx
            │   ├── AuswertungenTabelleV4.tsx · AuswertungKopf.tsx
            │   ├── CommunityV4.tsx + CommunityUebersichtV4/PVErtragV4/RegionalV4/
            │   │                      TrendsV4/StatistikenV4/KomponentenV4 · CommunityShareBlock.tsx
            │   ├── EinstellungenV4.tsx · EinstellungenModalHost.tsx · HilfeV4.tsx
            │   ├── ZeitStepper.tsx · WerkbankZeitraum.tsx · ZeitraumHinweis.tsx
            │   ├── ProvenanzQuellen.tsx · OnboardingLeer.tsx · V4Platzhalter.tsx
            │   └── status/           # AppStatusContext · GlobalStatusProvider · StatusFusszeile
            │
            ├── components/          # geteilte SoT-Komponenten — eine Klasse = EINE Komponente
            │   ├── ui/              # Card · Button · Modal · Table · ChartTooltip · Badge …
            │   ├── blocks/          # Block-Rahmen, Fokus/Vollbild, BlockShell
            │   ├── park/            # Park-Doktrin (Parkbar, parken/entparken)
            │   ├── charts/          # Chart-Bausteine (Achsen, Legende)
            │   ├── forms/           # Formular-Controls (Regel 0a: keine Roh-Controls)
            │   ├── live/            # EnergieFluss (SVG) · EnergieBilanz · WetterWidget …
            │   ├── tag/ · werte/ · finanzen/ · roi/ · aussicht/ · prognose/
            │   ├── pv/ · speicher/ · waermepumpe/ · wallbox/ · eauto/ · balkonkraftwerk/
            │   ├── monatsabschluss/ # das Monatsabschluss-Formular
            │   ├── connector/ · import/ · setup-wizard/
            │   ├── infothek/ · repair/ · layout/ · common/
            │   └── AppWithSetup.tsx · AppErrorBoundary.tsx · DokumentationsDialog.tsx
            │
            ├── pages/               # Einstellungs-Flächen + Teile, die V4 einbindet
            │   ├── Einrichtung.tsx · AnlagenTeile.tsx · InvestitionenTeile.tsx
            │   ├── MonatsdatenTeile.tsx · StrompreiseTeile.tsx · InfothekTeile.tsx
            │   ├── EnergieprofilTeile.tsx · DatenCheckerTeile.tsx · ProtokolleTeile.tsx
            │   ├── BackupTeile.tsx · HAExportSettingsTeile.tsx · PVGISSettingsTeile.tsx
            │   ├── HAStatistikImport.tsx · DataImportWizard.tsx · CsvImportWizard.tsx
            │   └── CloudImportWizard.tsx · CustomImportWizard.tsx · ConnectorSetupWizard.tsx
            │
            ├── lib/                 # SoT-Helfer (keine lokalen Kopien daneben!)
            │   ├── colors.ts        # Farb-SoT — keine Inline-Hex außerhalb
            │   ├── datum.ts         # heuteIso · toIsoDatum · verschiebeIsoTage (lokale Uhr!)
            │   ├── monatsLuecken.ts # „welcher Monat ist offen" (Binnen-Lücken inklusive)
            │   ├── einheiten.ts · chartAchse.ts · blockStyle.ts · komponentenStyle.ts
            │   ├── investitionAktiv.ts · investitionParameter.ts · erzeugerSpalten.ts
            │   ├── erfassungZustand.ts · sollErfuellung.ts · stundenSlot.ts
            │   ├── prognoseAnzeige.ts · prognoseHinweise.ts · pvHerkunft.ts
            │   ├── calculations.ts · constants.ts · fieldDefinitions.ts · flags.ts
            │   ├── download.ts · wirtschaftlichkeitDefaults.ts · werte/
            │
            ├── api/                 # ein Modul je Backend-Router (client.ts = Basis)
            ├── hooks/               # useApiData (SWR-Cache) · useAnlagen · useSectionOrder …
            ├── config/              # version.ts · einstellungenKatalog.tsx · v3ZuV4Route.ts
            ├── routes/              # routeManifest.ts + redirects (V3 → V4)
            ├── context/             # ThemeContext (Light/Dark)
            ├── types/ · utils/ · assets/
            └── test/                # Wächter-Selbsttests + setup.ts
                ├── factories.ts     # typgebundene API-Fixtures (s. unten)
                └── render.tsx       # renderMitProvidern + stubMatchMedia
```

---

## Datenbank

- **Typ:** SQLite
- **Pfad:** `/data/eedc.db`
- **Schema:** Wird beim ersten Start automatisch erstellt

Für Schema-Änderungen:

1. Model in `backend/models/` anpassen
2. Die Spalte in `core/database.py::run_migrations` eintragen (dort steht je Tabelle eine Liste,
   aus der beim Start ein `ALTER TABLE … ADD COLUMN` erzeugt wird, wenn die Spalte fehlt)
3. Backend neu starten

**Nicht auf SQLAlchemy verlassen:** `create_all` legt fehlende **Tabellen** an, aber keine fehlenden
**Spalten** in bestehenden Tabellen. Genau dafür gibt es `run_migrations` — wer die Spalte dort
vergisst, bekommt sie auf einer frischen Installation und nicht auf einer bestehenden.

Die `parameter`-JSON-Spalte in `investitionen` wird automatisch erweitert (kein `ALTER TABLE`
nötig) — neue Schlüssel gehören aber in
`core/investition_parameter.py` + `lib/investitionParameter.ts`, sonst driften Backend und Client
auseinander.

**Daten-Migrationen** (nicht Schema, sondern Inhalt) liegen in `services/migrations/` und werden
aus `core/database.py::_run_data_migrations` **einmalig** gefahren. Regeln dafür:

- **Nie blockierend, nie über HTTP** — der Start darf daran nicht hängen.
- **Kein „großer Heiler-Knopf"**: eine Migration korrigiert eine benannte, belegte Fehlform.
  Alles andere gehört in den Daten-Checker und in die Reparatur-Werkbank, wo der Nutzer punktuell
  entscheidet.
- Ein reiner Diagnose-Befund wird **gemeldet, nicht geheilt**.

---

## Tests & Gates

**Vor jedem Commit-Paket vollständig laufen lassen.** Die Soll-Zahlen (pytest/Vitest) stehen bewusst
**nicht** hier — sie ändern sich mit jedem Paket. Wer wissen will, ob ein Lauf vollständig war, liest
die **Summenzeile**, nicht die letzte grüne Zeile.

**Summenzeile = `N passed` und sonst nichts** (Entscheid Gernot 24.10.2026). `skipped`, `xfailed`, `xpassed` und
`warnings` sind kein Normalstand, sondern Arbeitsvorrat: Eine Zahl neben `passed` wird nach dem dritten Lauf zum Rauschen,
und ein Agent liest sie als Soll („2 skipped, 8 xfailed wie immer") statt als Befund. Taucht ein Skip, ein xfail oder
eine Warnung auf, ist das ein Päckchen-Punkt (Ursache beheben, nicht filtern). **Benannte Grenzen** — gemessene rote
Sichten, die bewusst bestehen bleiben — zählen grün, wenn ihre roten Sichten *exakt* dem Register entsprechen; „neu rot"
und „geheilt (Markierung entfernen)" bleiben Fehler. Das Register steht in der Matrixdatei selbst:
`backend/tests/test_pv_achse_matrix.py::URSACHE`/`ROT` (heute `ABSCHLUSS-BESTAND-VS-KANAL-TAGE`, `W2-R5-KLEMME`) und
`backend/tests/test_achsen_matrix.py::URSACHE`/`ROT` (leer). Die Testzelle schreibt dann eine Zeile
„benannte Grenze <Ursache>" in ihre Ausgabe (`pytest -rP` bzw. `-rA` zeigt sie unter «PASSES»).
Die Regel gilt auch für die CI-Jobs `backend-tests (UTC)` und `backend-tests (Pacific/Auckland)`; die
Runner-Bibliotheken, die eine Warnung verhindern (heute `libharfbuzz-subset0` für WeasyPrint), stehen in
`.github/workflows/tests.yml`.

**Reihenfolge ist nicht beliebig:** `tsc --noEmit` kommt **vor** dem ersten vollen Vitest-Lauf. Ein
vergessener Import fällt dort in Sekunden auf, im Vitest-Lauf erst nach Minuten und mit
irreführender Fehlermeldung.

**Der Testlauf berührt `data/eedc.db` nie.** `conftest.py` setzt `DATABASE_URL` auf eine Wegwerf-Datei
je Worker, *bevor* `backend.core.database` importiert wird, legt dort das Schema an, setzt das
L2-Cache-Flag des Prognose-Kanons je Test zurück und startet die App-Lifespan ohne Scheduler
(`EEDC_DISABLE_SCHEDULER`). Bis zum 19.09.2026 schrieb jeder Lauf 12–20 Aktivitätszeilen in die
Entwickler-Datenbank, und die nie geschlossene Verbindung der Produktiv-Engine war die wandernde
Warnung „Event loop is closed" (N-414 · N-532). Wer eine Probe mit eigener Engine schreibt, disposed
sie im `finally` — die `db`-Fixture ist das Vorbild.

```bash
# 0. Lint (Sekunden; fängt undefinierte Namen, bevor pytest Minuten braucht)
cd eedc && source backend/venv/bin/activate && ruff check backend

# 1. Backend (bei Backend-Arbeit vollständig)
python -m pytest backend/tests -q

# 2. Frontend: Typen ZUERST, dann Unit-Tests
cd eedc/frontend && npx tsc --noEmit && npm run test

# 3. Die Wächter (alle auflisten statt eine Zahl zu glauben)
npm run 2>&1 | grep 'check:'
```

**Die Wächter (`npm run check:*`, `eedc/frontend/scripts/check-*.mjs`)** setzen die
Darstellungs-Regeln maschinell durch — Regel 0/0a aus
[KONZEPT-STYLE-GUIDE.md](KONZEPT-STYLE-GUIDE.md). Sie sind **statisch** (Quelltext-Analyse, kein
Browser), mit drei Ausnahmen und einer Baseline:

| Wächter | Besonderheit |
| --- | --- |
| `check:charts` · `check:achsen` · `check:chart-audit` | **Bei Chart-Arbeit zusätzlich Pflicht.** `check:chart-audit` fährt **Chromium** gegen einen laufenden Dev-Server — jsdom rendert **keine** Charts, ein grüner Vitest-Lauf sagt über ein Chart nichts aus |
| `check:park-leertest` | **Playwright-Livetest** gegen eine laufende Box, verlangt ein `VITE_DEMO_DEFAULT=true`-Build. **Läuft am Auslöser, nicht am Takt** (Entscheid 23.08.): nur wenn eine im **Paket** geänderte Datei unter `eedc/frontend/src` `Parkbar`, `data-park-id` oder `FokusKachel` enthält (Basis `HEAD`, nicht `origin/main`) — und vor jedem Release. Mit 188 s der teuerste Einzelprüfer; was er als Einziger fängt, steht in `CLAUDE.md` §Gates. ⛔ Hier stand bis 23.08. die Anweisung, danach zwingend `git checkout -- eedc/frontend/dist/` zu fahren, weil `dist/` versioniert sei — **das gilt seit N-246 / v4.0.15 nicht mehr**: `eedc/frontend/dist` ist nicht versioniert (beide Dockerfiles bauen das Frontend in einer eigenen Stage), der Schutz sitzt in `release.sh::pruefe_nichts_uebrig`. CLAUDE.md trug den Widerruf, diese Tabelle nicht |
| `check:form-controls` | meldet „1 offen (WelcomeStep.tsx)" als **dokumentierte Baseline** (rc=0) |
| `check:de-de` | **Scope über einen Import-Graph**, nicht über Verzeichnisse: `src/v4/` + `src/components/` als Startknoten, dazu die transitive Hülle der von dort erreichten `pages/`- und `config/`-Dateien. ⚠ **Wer den Graph anfasst, prüft beide Kanten-Formen**: `from '…'` **und** `lazy(() => import('…'))`. Bis 13.08. fehlte die dynamische Form — die sieben Einstellungs-Wizards hingen genau daran und lagen samt 15 roher Anzeigen außerhalb; die zehn `pages/*Teile.tsx` fielen an der `config/`-Kante heraus. **Ein Wächter, dessen Reichweite an der Import-Form hängt statt an der Sichtbarkeit, prüft die falsche Menge.** Der Rest-Zähler („N Treffer außerhalb") ist **keine Schuldenzahl** — er enthält auch Nicht-Anzeigen wie URL-Parameter in `src/api/` |

### Einen baumweiten Wächter schreiben: `quellbaum` statt eigener `rglob`

Zehn Prüfer laufen über den Backend-Quelltext. Die Frage „welche Dateien gehören dazu" steht
**einmal** — in `backend/tests/quellbaum.py`:

```python
from backend.tests.quellbaum import produktivbaum   # alles ohne tests/, venv/, __pycache__
from backend.tests.quellbaum import probenbaum      # der Testbaum

for datei in produktivbaum():
    datei.rel      # "services/monats_fakten/laden.py" — der Name, den der Prüfer meldet
    datei.quelle   # Quelltext
    datei.baum     # fertiger ast.Module — NICHT selbst parsen
```

⚠ **Nicht selbst `rglob` + `ast.parse` schreiben.** Bis zum 2026-08-24 tat das jeder Prüfer für
sich — neun handgeschriebene Kopien derselben Regel in vier Schreibweisen, und **zwei davon waren
falsch**: `test_n252_speicher_wirkungsgrad_deckung.py` filterte mit `"/venv/" in rel` auf einem
**relativen** Pfad und nahm deshalb **3828 Dateien statt 337** (3491 aus dem virtualenv, 14,27 s
statt 1,32 s); `test_datenquellen_mapping_sync.py` hatte gar keinen venv-Filter. Beide meldeten
grün — ein Abwesenheitsbeweis über fremden `site-packages`-Code behauptet mehr, als er weiß.

**Der Cache ist der Nebeneffekt, nicht der Zweck.** `test_wurzelmuster_konformitaet.py` ruft seine
Dateiquelle sechzehnmal auf: **27,36 s → 8,93 s**. Über alle Prüfer zusammen **51,96 s → 18,01 s**,
bei unveränderter Fallzahl.

⚠ **Kein Export dieser Datei heißt `test…`** — unter dem Namen `testbaum` hat pytest die Funktion
beim Importeur als **Testfunktion eingesammelt** (`python_functions = test*` greift auf jeden Namen
im Modul-Namensraum) und als „grün" gezählt, ohne dass sie etwas prüfte. Sie heißt deshalb
`probenbaum`; `test_quellbaum.py::test_kein_export_heisst_wie_eine_probe` hält es fest.

**Wer einen neuen Wächter baut, prüft auch seine Prüfmenge.** `quellbaum` liefert
`nicht_parsebar()` — Dateien, die `ast.parse` nicht annimmt. Ein Prüfer, der sie still überspringt,
verliert Deckung, ohne es zu melden (die N-318-Klasse). Heute ist die Liste leer, und ein
Selbsttest hält sie leer.

### Einen Backend-Test schreiben: die Factories benutzen

`backend/tests/factories.py` baut die Modelle, `conftest.py` liefert die `db`-Fixture. **Neue Tests
nutzen die Factories, alte werden bei Berührung umgehängt** — nicht in einem Zug.

```python
from backend.tests import factories

async def test_etwas(db):
    a = await factories.anlage(db, standort_land="DE")     # + flush, `a.id` steht bereit
    inv = await factories.investition(db, a.id, "pv-module", leistung_kwp=5.0)
    await factories.imd(db, inv.id, 2025, 7, {"pv_erzeugung_kwh": 420.0})
    await db.flush()
```

**Zwei Formen:** `mach_*` konstruiert nur (ohne Session), die kurzen Namen legen an und flushen.
`commit` ruft der Test selbst, damit er sichtbar bleibt. Wiederkehrende Aufbauten aus mehr als
einem Modell stehen als **Szenarien** daneben (`anlage_mit_pv` · `anlage_mit_tarif` ·
`anlage_mit_modul` · `zwei_wechselrichter` · `mach_anlage_mit_mapping`).

⚠ **Defaults nur für das technisch Nötige, nie für fachliche Werte.** `anlage()` setzt Namen und
kWp (98 % bzw. 96 % aller Konstruktionen tun das, kein Test behauptet sie) — aber **kein**
`standort_land` und **keine** Tarifpreise: eine Factory, die einen Tarif erfindet, hält genau den
Test still grün, der den Tarif behaupten wollte. `test_factories.py` hält das fest.

**Werte-Fakten (§3, seit E6):** `mach_monats_fakt()` und `mach_kennzahlen()` bauen einen
`MonatsFakt` (ADR-002/P10) bzw. `VerbrauchsKennzahlen`. Beide verlangen alle Felder als
Pflichtargumente — acht Teil-Fakten bzw. sieben Kennzahlen. Wer nur eine Größe behaupten will,
baut sonst den Rest von Hand und muss ihn anfassen, sobald ein Teil-Fakt dazukommt:

```python
from backend.tests.factories import mach_kennzahlen, mach_monats_fakt

fakt = mach_monats_fakt(kennzahlen=mach_kennzahlen(eigenverbrauch_kwh=1000.0))
```

Alles Übrige steht auf 0 bzw. leer — dieselbe Regel wie oben: was ein Test behauptet, setzt er
selbst.

### Eine Testdatei benennen: Präfix-Cluster und Schwesterverweis

Der Backend-Testbaum ist **flach** — 409 Dateien in `backend/tests/`, ohne Themen-Ordner.
**Das ist eine Entscheidung, keine offene Baustelle** (Gernot, 2026-08-24): am Baum gemessen
tragen **135 der 409 Dateien (33 %) mehr als ein Thema im Namen** —
`test_ha_export_wp_spezialtarif.py` gehörte gleichzeitig nach `ha/`, `waerme/`, `finanzen/` und
`import_export/`. Ein Themen-Ordner wäre eine dritte Konvention über den Feature-Namen und
träfe für jede dieser Dateien eine Wahl, die der nächste Sucher nicht nachvollziehen kann.

Stattdessen gilt die Regel, die ohnehin schon galt — jetzt gewächtert:

1. **Neue Datei in den bestehenden Präfix-Cluster einordnen**, keine dritte Namensvariante für
   dasselbe Modul schaffen (`HAStatisticsService` → einheitlich `test_ha_lts_*`).
2. **Im Modul-Docstring mindestens eine Schwesterdatei nennen.**

```python
"""`HAStatisticsService.get_hourly_mean_for_day()` — Stunden-Mean roh + Einheit.

Schwesterdateien der `ha_lts`-Familie (SoT des HA-Schemas: `ha_lts_helfer.py`):
`test_ha_lts_hourly_reader.py` (Stunden-Summen) · `test_ha_lts_minmax_reader.py`
(Stunden-Min/Max) · `test_ha_lts_monatswerte_lookup.py` (Monatswerte + get_value_at).
"""
```

**Warum das mehr ist als Kosmetik.** Namens-Drift erzeugt Lücken aus **beiden** Suchrichtungen:
`ha_statistics_service.py` galt einmal als „0 Tests", weil die Suche `test_ha_statistics*`
lautete und die Familie `test_ha_lts_*` heißt. Der Fehlbefund floss in einen Refactoring-Plan
ein. Ein Docstring, der eine Schwester nennt, macht das Set von jedem Einstiegspunkt aus
begehbar. Deshalb misst man Testabdeckung auch **per Symbol**, nie per geratenem Dateinamen.

Der Wächter ist `test_konformitaet_schwesterdateien.py`. Er verlangt den Verweis nur von Dateien,
deren Präfix-Cluster mindestens zwei Dateien umfasst — ein Einzelgänger hat keine Schwester. Der
genannte Name muss **existieren** und darf **nicht die Datei selbst** sein (16 Bestandsdateien
nannten im Docstring ausschließlich sich; das ist eine Überschrift, kein Querverweis). Die
Schwester darf **über den Cluster hinausgehen** — ein Symmetriepartner ist oft der nützlichere
Hinweis. Die Baseline (272 Dateien) ist **abschmelzend**: sie heilt nichts, sie verhindert die
273., und ein erledigter Eintrag ist selbst ein Fehler.

### Eine HA-LTS-Probe schreiben: `ha_lts_helfer`

Das Recorder-Schema von Home Assistant (`statistics_meta` · `statistics` ·
`statistics_short_term`) steht **einmal** — in `backend/tests/ha_lts_helfer.py`. Es ist ein
fremdes Schema; vier handgeschriebene Kopien driften, sobald HA eine Spalte anfasst.

```python
from backend.tests import ha_lts_helfer

svc = ha_lts_helfer.mach_service()                                   # In-Memory-SQLite + Schema
mid = ha_lts_helfer.sensor(svc, "sensor.pv", "kWh", has_sum=True)    # statistics_meta
ha_lts_helfer.zeile(svc, mid, datetime(2026, 5, 15, 12), sum_wert=42.0)
```

`has_mean` folgt standardmäßig aus `has_sum` — ein Zähler trägt keinen Mittelwert, ein Messwert
umgekehrt. `zeile()` schreibt wahlweise nach `statistics` oder `statistics_short_term`
(`tabelle=`).

⚠ **Kein Export eines Helfer-Moduls darf mit `test` beginnen** — `python_functions = test*`
greift auf jeden Namen im Modul-Namensraum des **Importeurs**; pytest sammelte so schon einmal
eine Quell-Funktion als Testfunktion ein und zählte sie grün.

### Einen Frontend-Test schreiben: die Factories und `renderMitProvidern`

`src/test/factories.ts` baut die drei großen API-Antworten, `src/test/render.tsx` den
Provider-Turm. **Neue Tests nutzen sie, alte werden bei Berührung umgehängt** — nicht in
einem Zug, wie im Backend.

```tsx
import { aktuellerMonat, monatsZeile, tagWerte } from '../test/factories'
import { renderMitProvidern, stubMatchMedia } from '../test/render'

const d = (over: Partial<AktuellerMonatResponse> = {}) =>
  aktuellerMonat(2026, 8, { pv_erzeugung_kwh: 412, ...over })   // Rest = Nullstellung

beforeEach(() => { stubMatchMedia() })            // jsdom kennt matchMedia nicht
renderMitProvidern(<CockpitJahrV4 anlageId={1} />, { route: '/cockpit/jahr' })
```

⭐ **Warum typgebunden statt `as unknown as`.** `AktuellerMonatResponse` hat 88 Pflichtfelder,
`AggregierteMonatsdaten` und `TagWerte` je 42 — von Hand schreibt das niemand aus, also stand in
38 Testdateien ein `as unknown as X`. **Ein solcher Cast entkoppelt die Fixture vom Typsystem:**
ein umbenanntes Feld im API-Client bricht dort keinen Test. Am realen Sprengsatz gemessen
(2026-08-24, je ein umbenanntes Pflichtfeld): `AggregierteMonatsdaten.netzbezug_kwh` meldeten
**vorher 2 Testdateien, nachher 9**; `AktuellerMonatResponse.netzbezug_kwh` **vorher 3,
nachher 11.** ⚠ Wer diese Messung wiederholt, ersetzt **innerhalb des Interface-Blocks** —
`netzbezug_kwh: number` steht in `monatsdaten.ts` dreimal, und ein globales Replace traf beim
ersten Versuch `MonatsdatenCreate` und meldete folgerichtig **0** betroffene Dateien. Das Basisobjekt der Factory erfüllt den Typ per `satisfies`, der
Aufrufer übergibt `Partial<T>` — ein Tippfehler darin ist ein Compile-Fehler statt eines stillen
`undefined`.

⚠ **Die Defaults behaupten nichts** — dieselbe Regel wie im Backend. Jede Menge steht auf ihrer
Nullstellung (`null` wo der Typ es zulässt, sonst `0`/`false`/`{}`/`[]`), Identität ist
**Parameter**, nicht Default. `factories.test.ts` hält das mit einem Wächter fest, der jedes
Feld auf erfundene Zahlen und Texte absucht.

⚠ **Nullstellung ist nicht `undefined`.** Der handgebaute Cast ließ ungenannte Felder
`undefined`; die Factory setzt sie auf `null`/`0`. Für `??` ist das gleich, für `!== undefined`
und `Object.keys` nicht — wer eine Bestandsdatei umhängt, misst ihre Vitest-Fallzahl vor und
nach dem Eingriff. ⛔ **`tsc` ist dabei der einzige Prüfer, der zählt:** Vitest strippt die
Typen, ESLint kennt den fehlenden Typ-Import nicht — ein bei der Umstellung mitentfernter
`import type` fiel am 24.08. nur `tsc --noEmit` auf, nachdem `lint` und Vitest grün gemeldet
hatten.

**Backend-Regeln haben pytest als Wächter, keine `check:*`-Skripte** (die sind alle Frontend-Node):
`test_berechnungs_layer_konformitaet.py` ([ADR-001](ADR-001-BERECHNUNGS-LAYER.md)) ·
`test_wurzelmuster_*.py` ([ADR-002](ADR-002-WURZELMUSTER.md)). Zwei Ausnahmen bewachen die
Client-Hälfte einer Backend-Regel: `check:kennwert-roh` (P3-a) und `check:co2-roh` (DI-2).

### Was ein Test leisten muss

- **Neue Proben rot verifizieren.** Ein Test, der gegen den alten *und* den neuen Stand grün ist,
  beweist nichts. Der Sprengsatz muss **außerhalb** eines `except Exception` zünden — sonst
  verschluckt der Catch ihn und die Probe bleibt stumm.
- **Bleibt eine Probe grün, wird sie geschärft, nicht weggelassen.** Häufigste Ursache: die Fixture
  bildet den Fehlerfall nicht ab (etwa „doppelte Daten" geprüft, während der Fehler *verschiedene
  Daten mit gleichen Werten* erzeugt).
- **Fixtures fremder APIs brauchen eine benannte Quelle im Docstring.** Eine selbstgebaute
  Antwortform ist eine Behauptung über einen fremden Server; Rot-Verifikation prüft nur, ob der
  Test den eigenen Code greift.
- **Hermetisch heißt auch: ohne echte Uhr und ohne Systemzeitzone.** `vitest.config.ts` pinnt
  `Europe/Berlin`; im Backend gehört die Zeit in die Fixture. Eine Probe, die in vier von
  24 Stunden fällt, macht jeden grünen Lauf zum Zufallsbefund.
- **Vor dem Ändern einer Meldung im `tests/`-Baum nach dem alten Wortlaut greppen** — ein
  Wortlaut-Filter macht Negativ-Tests stumm.
- **Mount-Proben der V4-Sichten leeren den SWR-Cache** (`_clearSwrCacheForTests`); er ist ein
  Modul-Singleton und trägt sonst Werte in die nächste Probe.

> **Gates ≠ CI.** Die Gates laufen auf **einer** Maschine mit ihren Paketversionen und ihrer
> Uptime; der GitHub-Runner ist frisch. Ein grüner Gate-Lauf ist die **Voraussetzung** für ein
> Release, nicht die Bestätigung, dass CI grün wird — und ein rotes CI ist nicht automatisch ein
> Testproblem, sondern erst nach Ursachen-Beleg.

---

## API Dokumentation

Nach dem Start des Backends verfügbar unter:

| Format       | URL                                    |
| ------------ | -------------------------------------- |
| Swagger UI   | `http://localhost:8099/api/docs`        |
| ReDoc        | `http://localhost:8099/api/redoc`       |
| OpenAPI JSON | `http://localhost:8099/api/openapi.json`|

### API-Routen Übersicht

> **Erhoben aus `backend/main.py` (die `include_router`-Aufrufe), Stand 2026-08-07.** Die Prefixe
> sind dort der SoT — ein Modulname sagt nichts über seinen Prefix, und mehrere Module teilen sich
> einen. Im Zweifel: `grep include_router backend/main.py`.

| Prefix | Module | Beschreibung |
| --- | --- | --- |
| `/api/anlagen` | `anlagen` | Anlagen-CRUD + Anlagenfoto |
| `/api/monatsdaten` | `monatsdaten` | Monatsdaten-CRUD, Aggregation, Monatsliste |
| `/api/aktueller-monat` | `aktueller_monat` | Cockpit → Monat (laufender Monat + gespeicherte Monate) |
| `/api/investitionen` | `investitionen/` | Komponenten, ROI, Stilllegung, Kennwerte |
| `/api/cockpit` | `cockpit`, `cockpit/` | Übersicht, KPIs, Komponenten, Nachhaltigkeit, Jahr |
| `/api/aussichten` | `aussichten`, **`prognosen`** | Prognose-Aussichten **und** Prognose-Vergleich/Genauigkeit — zwei Module, ein Prefix |
| `/api/solar-prognose` | `solar_prognose` | Open-Meteo Solar GTI |
| `/api/pvgis` | `pvgis` | PVGIS-Daten + Horizontprofil |
| `/api/wetter` | `wetter` | Multi-Provider (Open-Meteo, Bright Sky, PVGIS TMY) |
| `/api/korrekturprofil` | `korrekturprofil` | gelernte eedc-Prognose-Korrektur |
| `/api/strompreise` | `strompreise` | Tarife, Spezialtarife, Gültigkeitsfenster |
| `/api/live` | `live_dashboard`, `live_mqtt_inbound`, `live_wetter`, **`mqtt_gateway`**, **`mqtt_presets`** | Live-Fluss, Tagesverlauf, Börsenpreise, MQTT-Inbound, Topic-Mapping, Geräte-Presets — **fünf** Module unter einem Prefix |
| `/api/datenquellen` | `datenquellen` | Datenquellen-Fläche (ein Feld = eine Quelle) |
| `/api/connectors` | `connector` | Geräte-Connectors im lokalen Netz (**9**, SoT: `services/connectors/registry.py`) |
| `/api/cloud-import` | `cloud_import` | Cloud-API-Import (**12** Provider, SoT: `services/cloud_import/registry.py`) |
| `/api/portal-import` | `data_import` | Portal-CSV-Import — ⚠ **Modul heißt `data_import`, Prefix `portal-import`** |
| `/api/custom-import` | `custom_import/` | CSV/JSON mit Feld-Mapping |
| `/api/import` | `import_export/` | CSV, JSON, Demo-Daten, PDF |
| `/api` | **`monatsabschluss/`**, **`community`**, **`ha_export`** | drei Module ohne eigenes Prefix — ihre Pfade stehen im Modul selbst |
| `/api/energie-profil` | `energie_profil/` | Stunden-/Tagesprofile, Reaggregation, Tag-Status |
| `/api/repair` | `repair` | Reparatur-Werkbank (Tag/Zeitraum neu rechnen) |
| `/api/system` | `system_logs`, `daten_checker` | Logs **und** Daten-Checker — zwei Module, ein Prefix |
| `/api/diagnostics` | `diagnostics` | Diagnose-Endpunkte |
| `/api/dokumentation` | `dokumentation` | PDF-Dokumente (Anlagendoku, Finanzbericht) |
| `/api/infothek` | `infothek` | Komponenten-Akten, Verträge, Datei-Upload (N:M) |
| `/api/ha` | `ha_remote`, *(HA_MODE)* `ha_integration` | HA-Verbindung/Token · HA-Status |
| `/api/sensor-mapping` | *(HA_MODE)* `sensor_mapping` | **nur noch `/{id}/suggest`** (HA-Energy-Vorschläge, #197). Die fünf Zuordnungs-Endpunkte sind seit 2026-08-13 stillgelegt (N-241) — Zuordnung läuft über `/api/datenquellen` |
| `/api/ha-statistics` | *(HA_MODE)* `ha_statistics` | HA-Langzeitstatistik — **drei Transporte**: externe Recorder-DB (`HA_RECORDER_DB_URL`), eingehängte Recorder-Datei, **WebSocket** `recorder/statistics_during_period` (ohne DB-Zugang) |

> **Hinweis:** die mit *(HA_MODE)* markierten Router werden nur eingehängt, wenn `HA_MODE=true`.
> `/api/ha` gibt es in **beiden** Betriebsarten — `ha_remote` (Verbindung + Token für den
> Standalone-Container) hängt nicht am Add-on-Modus.

---

## Dokumentation pflegen

**`docs/` ist der SoT.** Zwei generierte Kopien hängen daran, und beide werden **nicht** von Hand
editiert:

| Ziel | Erzeugt von | Zustand im Repo |
| --- | --- | --- |
| Website (Astro Starlight, GitHub Pages) | `website/scripts/sync-docs.sh` (läuft als `prebuild` **im `website/`-Verzeichnis**) | `website/src/content/docs/` ist **gitignored** |
| In-App-Hilfe | **`scripts/sync-help.sh`** | die Kopien sind **versioniert** und gehören in denselben Commit |

**Nach jeder Doku-Arbeit `scripts/sync-help.sh` laufen lassen und die Kopien mitcommitten** —
sonst zeigt die Hilfe im Add-on einen anderen Text als das Repo. Die In-App-Hilfe ist kein Archiv:
[WAS-IST-NEU.md](WAS-IST-NEU.md) wird darin **zurückgeblättert**, ein überholter Satz in einem alten
Abschnitt bleibt also sichtbar. Wird eine Aussage später widerlegt, kommt ein **Korrektur-Vermerk**
an den alten Eintrag; der historische Wortlaut bleibt stehen.

**Eine Versionsnummer schreibt nur, wer sie kennt.** Solange der Release-Entscheid nicht gefallen
ist, gehört in einen Doku-Absatz **kein** „ab v4.x" — die Zahl steht dann im CHANGELOG-Abschnitt,
nicht im Fließtext. Am 2026-08-06 mussten so 19 Behauptungen vor einem Release korrigiert werden,
14 davon „v4.1", vier in ausgelieferter Anwender-Doku.

### Ein Statuskopf ist eine Behauptung

Konzept-Dokumente werden **im Rumpf** fortgeschrieben — der **Kopf** bleibt stehen. Genau dort
liest aber jeder zuerst. Am 2026-08-08 gemessen, drei Fälle derselben Klasse:

- `KONZEPT-SPEICHER-AUSWERTUNG.md` nannte „Kern weiterhin offen" und verwies auf ein Issue, das
  mit v4.0.0 geschlossen wurde — drei Absätze tiefer im **selben** Kasten stand „Phase 1
  ausgeliefert".
- `KONZEPT-UNVOLLSTAENDIGE-WERTE.md` trug „VORSCHLAG — kein Code", während die ersten beiden
  Bausteine am selben Tag gebaut worden waren.
- `KONZEPT-HA-EXPORT-ARCHITEKTUR.md` führte eine Restarbeit als offen, die längst erledigt war
  (`sw_version` liest `APP_VERSION`, der tote Helper ist entfernt).

**Die Regel:** Wer ein Konzept anfasst, fasst seinen **Status** mit an und hält die **offenen
Zeilen gegen den Code**. Ein Statuskopf trägt ein **Mess-Datum, keine Versionsnummer** — eine
Zahl an dieser Stelle veraltet garantiert. Und: **die offenen Zeilen eines publizierten Konzepts
sind selbst eine Arbeitsquelle** — sie werden bei der Paket-Wahl mitgelesen, auch wenn kein Issue
dafür existiert.

### Wenn ein Docstring auf `docs/drafts/` zeigt

`docs/drafts/` ist **gitignored** (`.gitignore:82`) — die Dateien dort liegen nur auf der Maschine,
auf der sie entstanden sind. Ein Verweis dorthin ist für jeden Mitleser ein 404. Am 2026-08-08
baumweit gemessen: **16 Stellen im Produktionscode** zeigten dorthin, zwei davon
(`api/routes/datenquellen.py`, `hooks/useApiData.ts`) mit dem Wort **„SoT"**.

**Die Regel, die daraus folgt:**

1. **Ein Dokument, das im Code als SoT zitiert wird, gehört nach `docs/`** — nicht in `drafts/`.
   Deshalb ist `KONZEPT-DATENQUELLEN-V4.md` dorthin gewandert, so wie vorher schon
   [KONZEPT-MONATS-FAKTEN.md](KONZEPT-MONATS-FAKTEN.md).
   ⚑ **Die Umkehrung gilt seit 2026-08-28 genauso** (Entscheid Gernot): Ein Dokument, das **nur
   noch einen Bauplan** enthält — Maßnahmen-Register, Pakete, offene Punkte —, gehört **nicht**
   ins öffentliche Repository. `docs/` ist die Beschreibung des **gebauten** Systems; Baupläne
   und Vorhaben leben in `docs/drafts/` (lokal). Wer ein solches Dokument hinausschiebt, löst
   **vorher** jeden Verweis darauf auf: Die Regel wandert in den Docstring, das Dokument bleibt
   höchstens Herkunftsangabe. So sind am 28.08. `KONZEPT-FOKUS-DEEPLINK`, `KONZEPT-CHART-TABELLEN`,
   `KONZEPT-COMMUNITY` und `IA-V4-SOT-INVENTAR` gegangen — mit null verbliebenen Zeigern.
2. **Bestehende Verweise auf `docs/drafts/archive/…` sind Herkunftsbelege, keine Voraussetzung.**
   Sie sagen, aus welchem Bau-Vertrag eine Regel stammt; die Regel selbst steht immer im
   versionierten Baum (ADR, Konzept, Docstring). ADR-002 formuliert das für sich selbst
   ausdrücklich so: *„Diese ADR ist so geschrieben, dass sie ohne den Bericht trägt."* Wer eine
   solche Stelle anfasst, prüft, ob die tragende Passage schon eine versionierte Heimat hat — und
   hebt sie sonst dorthin.
3. **Ein Verweis darf nicht ins Leere zeigen**, auch nicht innerhalb von `drafts/`. Wandert ein
   Dokument nach `drafts/archive/`, wandern seine Verweise mit (am 2026-08-08 waren acht Pfade
   falsch, weil das Ziel längst archiviert war).

## Weiterführende Dokumentation

| Dokument | Inhalt |
| --- | --- |
| [ARCHITEKTUR.md](ARCHITEKTUR.md) | technische Gesamtsicht (Datenmodell, Services, Design-Entscheidungen) |
| [BERECHNUNGEN.md](BERECHNUNGEN.md) | Formel-Referenz je Kennzahl |
| [ADR-001](ADR-001-BERECHNUNGS-LAYER.md) · [ADR-002](ADR-002-WURZELMUSTER.md) | Schichtung · Invarianten P1–P10 |
| [KONZEPT-IA-V4.md](KONZEPT-IA-V4.md) | Informationsarchitektur + Invarianten I1–I16 + Redirects |
| [KONZEPT-STYLE-GUIDE.md](KONZEPT-STYLE-GUIDE.md) | Darstellungs-SoT (Regel 0/0a) |
| [KONZEPT-MONATS-FAKTEN.md](KONZEPT-MONATS-FAKTEN.md) | die Monatszeile als eine Schicht (P10) |
| [KONZEPT-DATENQUELLEN-V4.md](KONZEPT-DATENQUELLEN-V4.md) | eine Quelle je Feld, HA-first (Invariante I16) |
| [KONZEPT-263-klima-split.md](KONZEPT-263-klima-split.md) · [KONZEPT-263-INNENGERAETE.md](KONZEPT-263-INNENGERAETE.md) | **abgeschlossen und gebaut** — zwei **Bauform-Kapitel** (Split-Klimaanlage · Multisplit-Innengeräte). ⚠ **Nicht das Konzept der Fläche „Heizen · Warmwasser · Kühlen“** — das ist das Flächen-Konzept *SOLL Wärme/Klima* (**Maintainer-intern, noch nicht im Repo**). Beide Kapitel tragen im Kopf eine Korrekturliste. **Bis 27.08. standen sie hier unter „geplante Pakete“** |
| [HANDBUCH_WAERME_KLIMA.md](HANDBUCH_WAERME_KLIMA.md) | Wärme/Klima aus Anwendersicht — Erfassungswege, Werte des Modus-Sensors, Kennzahlen, FAQ. **Auch für Entwickler die schnellste Antwort auf „was sieht der Melder?“** |
| [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md) | Release-Prozess beider Repos |
| [SETUP_DEVMACHINE.md](SETUP_DEVMACHINE.md) | Entwicklungsrechner einrichten |
| [SENSOR-REFERENZ.md](SENSOR-REFERENZ.md) · [MQTT_INBOUND.md](MQTT_INBOUND.md) | Sensor-Felder · Topic-Struktur |
| [BENUTZERHANDBUCH.md](BENUTZERHANDBUCH.md) | Endnutzer-Index (Installation, Bedienung, Einstellungen) |
| [CLAUDE.md](../CLAUDE.md) | Entwickler-/KI-Kontext: Patterns, Fallstricke, Git-Regeln |

---

*Dieses Dokument trägt keine Versionsnummer — siehe Kopf. Stand der letzten Messung: 2026-08-07, Layer- und Service-Listen 2026-08-11.*

## Pflege — so läuft eine Fix-Sitzung (seit 11.10.2026)

> eedc ist ausgereift: Fehler haben Vorrang und erscheinen mit dem nächsten Release, in der Regel monatlich; Wünsche gehen nach #110
> (Entscheid Maintainer 10./11.10.2026; Hintergrund in `ARCHIV-CLAUDE-2026-10-10.md`).
> Dieser Abschnitt ist der komplette Ablauf, damit eine Sitzung ohne weiteres Vorwissen einen gemeldeten Fehler sauber behebt.

1. **Eingang.** Nur ein Melder-Beitrag (GitHub-Issue, simon42-Thread 89667, photovoltaikforum 258098, community-smarthome 10057, PN) oder
   ein Eintrag im Fundregister (`~/.claude/plans/fundregister.yaml`, Status `offen`). Wünsche gehen nach #110 «Gesammelt», ohne Termin.
2. **Analyse vor Eintrag.** Am aktuellen Stand messen, ob der beschriebene Zustand noch existiert (Datei:Zeile, Minimalfall gegen eine
   Wegwerf-DB); abgleichen mit CHANGELOG, ADR-001/ADR-002, Konzepten; die Folge für den Anwender nennen und prüfen, ob Daten-Checker,
   Wächter oder Hilfe den Fall schon decken. Erst dann Registereintrag (`status: offen`, Band, Einwertung, Entscheid Maintainer); ohne
   Analyse ist es `verdacht`. Nach jeder Registeränderung `python3 ~/.claude/plans/skript-artifact-bauen.py` und das Artifact neu publizieren.
3. **Bau** in einer Opus-Sitzung (`bau-opus`): nur die berührten Testdateien plus `backend/tests/test_wurzelmuster_konformitaet.py`,
   bei Frontend-Änderung `npm run lint`, `npx tsc --noEmit`, `npm run test`, `npm run check:design` (0), Doku-Spiegel `./scripts/sync-help.sh`;
   am Ende **einmal** die volle Backend-Suite mit gekürzter Ausgabe:
   `cd eedc && source backend/venv/bin/activate && find . -name __pycache__ -prune -exec rm -rf {} + && python -m pytest backend/tests -q -n 3 -p no:cacheprovider 2>&1 | tail -3`
   (≈ 9 min). CHANGELOG `## [Unreleased]` und `docs/WAS-IST-NEU.md` `## Unreleased` je Fix eine Zeile in Anwender-Sprache.
4. **Commit** mit expliziten Pfaden (nie `git add -A`), **kein Push, kein Tag** außerhalb des Release-Skripts. Register: Status `gebaut`
   mit Commit-Hash.
5. **Release** (wenn ein Fix drin ist, sonst quartalsweise): Kandidat ins HAOS-Lab (`bash ~/.claude/plans/lab-werkzeug/lab-rc.sh <rc> <version>`,
   Lab 10.100.1.167, Durchklick durch den Maintainer), Überschriften `## [<version>] - <Datum>` im CHANGELOG und `## v<version>` in
   WAS-IST-NEU, dann `./scripts/release.sh <version>` (bumpt fünf Versionsdateien, fährt den Smoke-Check = volle Suite, taggt, pusht beide
   Repos, wartet auf das Image). Danach `gh run list` in **beiden** Repos (Add-on und Standalone); CI fährt die Suite in UTC und Auckland.
   Community-Server (`/home/gernot/claude/eedc-community`) nur zusammen mit einem Add-on-Release deployen.
6. **Nicht tun:** Produktiv-Box `10.100.1.13` schreiben; `eedc/data/eedc.db` anfassen; einen Server gegen die Demo-DB mit Broker starten;
   neue Wächter, Matrix-Formen, Golden-Master-Läufe oder Gegenprüfungs-Sitzungen anlegen; Listen neben dem Register führen.

## Bereichs-Karte — wo ein Bereich im Baum liegt (erhoben 18.10.2026)

> **Zweck:** Eine Fix-Sitzung ordnet einen gemeldeten Fehler einer Zeile zu und weiß, wo Code, Tests, Golden Master und Handbuch liegen —
> **ohne zu suchen.** Zuordnung nach Dateiname und Routenpräfix (`main.py`), nicht nach Inhalt; Test-Muster sind Namensmuster. Jede Zelle ist
> gegen den Baum geprüft (Stand HEAD `bcc31087`). **Wer ein Modul verschiebt oder neu anlegt, zieht die Zeile nach** — bei Abweichung gewinnt der Baum.
> Die fünf GM-Skripte `cockpit-monat`, `analyse-leser`, `analyse-sichten`, `live-tagesverlauf`, `jahr-fold` (.mjs) liegen in `~/.claude/plans/`,
> fehlen aber in der GM-Tabelle unten.

Pfad-Präfixe in den Zellen: `R/` = eedc/backend/api/routes/ · `S/` = eedc/backend/services/ · `B/` = eedc/backend/core/berechnungen/ · `T/` = eedc/backend/tests/ · `F/` = eedc/frontend/src/ · `D/` = docs/ · `GM` = ~/.claude/plans/skript-golden-master-<name>.py (Ablage ~/.claude/plans/golden-master/<name>/ bei In-Process-GMs).
Ein `*` ist ein Glob; jedes Muster trifft mindestens eine Datei. Verzeichnisse enden auf `/`. Die Zuordnung Bereich ↔ Modul ist nach Dateiname und Routenpräfix (main.py) erhoben, nicht nach Inhalt gelesen.

| Bereich | Frontend-Route / Seite | Backend-Routen | Services / Layer | Tests | Golden Master | Handbuch |
| --- | --- | --- | --- | --- | --- | --- |
| Cockpit → Live | `/cockpit/live` · `F/v4/CockpitLiveV4.tsx` (Shell `F/v4/CockpitV4.tsx`) | `R/live_dashboard.py`, `R/live_wetter.py`, `R/live_wetter_antwort.py` | `S/live_komponenten_builder.py`, `S/live_power_service.py`, `S/live_history_service.py`, `S/live_kwh_cache.py`, `S/live_sensor_config.py`, `S/live_tagesverlauf_service.py`, `S/live_verbrauchsprofil_service.py`, `S/betriebsmodus_live.py`, `B/live_tagesverlauf_5min.py` | `T/test_live_*.py`, `T/test_*_live_*.py`, `T/test_n752_live_pv_wie_tag.py`, `T/test_398_betriebsmodus_live.py` | `live-komponenten`, `live-tages-kwh`, `live-tagesverlauf` | `D/HANDBUCH_BEDIENUNG.md` §2.1 |
| Cockpit → Tag | `/cockpit/tag` · `F/v4/CockpitTagV4.tsx` (+ `TagBilanz.tsx`, `TagRahmen.tsx`, `TagesRail.tsx`) | `R/energie_profil/tag.py`, `R/energie_profil/tage.py`, `R/energie_profil/views.py` | `S/energie_profil/tage_werte.py`, `S/energie_profil/tag_status.py`, `S/energie_profil/vergleichstage.py`, `S/kanal/stunden_leser.py`, `B/tagesbilanz.py`, `B/stundenbilanz.py` | `T/test_tag_*.py`, `T/test_tage_werte_symmetrie.py`, `T/test_rf20_tage_werte_faelle.py`, `T/test_n444_tagesdetail_ein_fenster.py`, `T/test_s4_kalendertag_sichten.py` | `energie-profil`, `aggregate-day` | `D/HANDBUCH_BEDIENUNG.md` §2.2 · `D/HANDBUCH_ENERGIEPROFIL.md` §2.1 |
| Cockpit → Monat | `/cockpit/monat` · `F/v4/CockpitMonatV4.tsx` (+ `MonatBilanz.tsx`, `MonatsRail.tsx`) | `R/cockpit/uebersicht.py`, `R/aktueller_monat/`, `R/monatsdaten_aggregiert.py` | `S/monats_fakten/`, `S/jahres_aggregat.py`, `S/monats_co2.py`, `B/monatsfenster.py`, `R/aktueller_monat/tkonto.py` | `T/test_aktueller_monat_*.py`, `T/test_monats_fakten_schicht.py`, `T/test_c1*_monats_fakten.py`, `T/test_n451_monatspfad_k3.py`, `T/test_b4_cockpit_matrix.py` | `aktueller-monat`, `cockpit-monat`, `ergebnisgroessen` | `D/HANDBUCH_BEDIENUNG.md` §2.3 |
| Cockpit → Jahr/Gesamt | `/cockpit/jahr` · `F/v4/CockpitJahrV4.tsx` (+ `JahrBilanz.tsx`, `JahresRail.tsx`) | `R/cockpit/jahr.py`, `R/cockpit/nachhaltigkeit.py`, `R/cockpit/pv_strings.py`, `R/cockpit/komponenten.py`, `R/cockpit/prognose.py` | `S/jahres_aggregat.py`, `S/monats_co2.py`, `B/bilanz_zeitraum.py`, `B/ergebnis.py`, `B/co2_amortisation.py` | `T/test_ergebnis_*.py`, `T/test_cockpit_*.py`, `T/test_jahresroute_hinweise.py`, `T/test_n584_jahr_grundgesamtheit.py` | `ergebnisgroessen`, `jahr-fold` (.mjs) | `D/HANDBUCH_BEDIENUNG.md` §2.4 |
| Cockpit → Aussicht / Aussichten-Finanzen | `/cockpit/aussicht` · `F/v4/CockpitAussichtV4.tsx` | `R/aussichten/` (`finanz_prognose.py`, `finanz_rueckblick.py`, `finanz_zerlegung.py`, `prognose.py`, `trend.py`, `wetter.py`) | `S/prognose_service.py`, `S/eedc_prognose_service.py`, `S/verbrauch_prognose_service.py`, `S/finanz_zeilen.py`, `B/kapitalrechnung.py`, `B/finanz_aggregat.py` | `T/test_aussichten_*.py`, `T/test_rf18_finanz_prognose_faelle.py` | `aussichten` | `D/HANDBUCH_BEDIENUNG.md` §2.5 · `D/HANDBUCH_PROGNOSEN.md` |
| Prognosen (Quellen, Kanon, Genauigkeit) | `/auswertungen/prognose` · `F/v4/AuswertungenPrognoseV4.tsx`, `F/pages/aussichten/KorrekturprofilHeatmapCard.tsx` | `R/prognosen.py`, `R/solar_prognose.py`, `R/korrekturprofil.py`, `R/pvgis.py` | `S/prognose_kanon.py`, `S/prognose_router.py`, `S/prognose_auswahl.py`, `S/prognose_adapter.py`, `S/prognose_discovery.py`, `S/prognose_genauigkeit_service.py`, `S/solar_forecast_service.py`, `S/solcast_service.py`, `S/korrekturprofil_aggregator.py`, `S/korrekturprofil_lookup.py`, `S/pvgis_soll.py`, `B/prognose_final.py`, `B/prognose_genauigkeit.py`, `B/prognose_korrektur.py` | `T/test_prognose_*.py`, `T/test_genauigkeit_*.py`, `T/test_pvgis_*.py`, `T/test_solcast_tagesprofile_357.py`, `T/test_eedc_prognose_kaskade.py`, `T/test_korrekturprofil_stunde_variante_a.py` | `prognose-kanon`, `prognosen-vergleich` | `D/HANDBUCH_PROGNOSEN.md` · `D/HANDBUCH_BEDIENUNG.md` §4.3 |
| Energieprofil (Tages-/Stundenwerte, Reparatur) | `/einstellungen/daten` (Pflege), `F/pages/EnergieprofilTeile.tsx`, `F/pages/auswertung/EnergieprofilPrognose.tsx` | `R/energie_profil/` (`diagnose.py`, `repair.py`, `monat.py`, `serien.py`, `prognose.py`, `waerme.py`), `R/repair.py` | `S/energie_profil/`, `S/energie_profil_service.py`, `S/repair_orchestrator.py`, `S/kanal/`, `S/snapshot/`, `S/verwerfen_vor_quellbeginn.py` | `T/test_kanal_*.py` (34), `T/test_energie_profil_rollup_kette.py`, `T/test_energieprofil_komponenten_serien.py`, `T/test_backfill_*.py`, `T/test_repair_orchestrator.py`, `T/test_reparatur_*.py`, `T/test_n595_*.py`, `T/test_n596_*.py`, `T/test_s5_*.py` | `energie-profil`, `aggregate-day`, `analyse-leser`, `analyse-sichten` | `D/HANDBUCH_ENERGIEPROFIL.md` |
| HA-Bauform: Kanal-Schicht, Lesestelle, Merken, Mengen-Weiche, Bestands-Tagespfad (Querschnitt, Stand S5 `1924d252`) | — (trägt Cockpit Tag/Monat/Jahr, Auswertungen, Daten-Checker, HA-Export) | — (Routen in den Zeilen der Sichten) | Kanal-Schicht `S/kanal/` (`lesen.py`, `fenster.py`, `quellenwahl.py`, `bilanz_leser.py`, `stunden_leser.py`, `lade_kontext.py`) · Lesestelle aller Mengen-Leser `S/energie_profil/kanal_stunden.py` (`stunden_der_tage`, `komponenten_der_tage`, `tages_eingaenge`) · Merken je Prozess `S/kanal/merken.py` (`ADAPTER`, `TAGESWAHL`, `GERAETE`) · Mengen-Weiche des Schreibers `S/energie_profil/mengen_weiche.py` (Schreiber `S/energie_profil/aggregator.py`) · Bestands-Tagespfad (Lesart 1) `S/snapshot/aggregator.py`, `S/snapshot/tages_tabelle.py`, `S/snapshot/bereichs_leser.py`, `S/snapshot/lts_aggregator.py`, `S/snapshot/boundary_range.py` | `T/test_kanal_*.py`, `T/test_s5_*.py`, `T/test_tep_mengen_leser_waechter.py`, `T/test_e4f_lade_kontext.py`, `T/test_pv_achse_matrix.py`, `T/test_achsen_matrix.py` | `energie-profil`, `aggregate-day`, `analyse-leser`, `analyse-sichten`, `daten-checker` | `D/BERECHNUNGEN.md` §6b (Tabelle „Stand der HA-Bauform") · `D/ARCHITEKTUR.md` (Kanal-Schicht, Energieprofil Service) · `D/HANDBUCH_ENERGIEPROFIL.md` |
| Daten-Checker | `/einstellungen/daten` · `F/pages/DatenCheckerTeile.tsx`, `F/pages/datenCheckerMeldungen.ts`, `F/config/datenCheckerKategorien.ts` | `R/daten_checker.py` | `S/daten_checker/` (`stammdaten.py`, `monatsdaten.py`, `energieprofil.py`, `zaehler.py`, `waermepumpe.py`, `emob.py`, `sensoren.py`, `datenquelle/`) | `T/test_daten_checker_*.py` (> 50), `T/test_b2_daten_checker_registry.py`, `T/test_d3_zaehlerstaende_checker.py`, `T/test_n751_checker_monat_ohne_zeile.py` | `daten-checker` | `D/HANDBUCH_DATEN_CHECKER.md` · `D/HANDBUCH_EINSTELLUNGEN.md` §5.3 |
| CSV-/Datei-/Portal-Import | Wizards im Modal-Host: `F/pages/CsvImportWizard.tsx`, `CustomImportWizard.tsx`, `DataImportWizard.tsx` (Host `F/v4/EinstellungenModalHost.tsx`) | `R/import_export/` (`csv_operations.py`, `json_operations.py`, `sensor_mapping_remap.py`), `R/custom_import/`, `R/data_import.py` | `S/import_writer.py`, `S/import_hauszaehler.py`, `S/import_parsers/`, `B/imd_monatsaggregat.py` | `T/test_import_*.py`, `T/test_custom_import_*.py`, `T/test_n70[2-9]_custom_import_*.py`, `T/test_n71[0-4]_*.py`, `T/test_csv_vorlage_rundlauf_f55.py`, `T/test_n747_n748_csv_legacy_und_zeile.py`, `T/test_n538_csv_wege_ohne_schutzzaehler.py` | `csv-import`, `custom-import`, `import` | `D/HANDBUCH_EINSTELLUNGEN.md` §6.5 |
| Cloud-Import / Geräte-Connector | `F/pages/CloudImportWizard.tsx`, `F/pages/ConnectorSetupWizard.tsx` | `R/cloud_import.py`, `R/connector.py` | `S/cloud_import/`, `S/connectors/`, `S/connector_mqtt_bridge.py` | `T/test_cloud_*.py`, `T/test_connector_*.py`, `T/test_ecoflow_*.py`, `T/test_deye_solarman_region_auth.py`, `T/test_victron_vrm.py`, `T/test_sungrow_isolarcloud.py`, `T/test_viessmann_gridbox.py`, `T/test_anker_solix_auth.py`, `T/test_n737_cloud_import_null_ist_wert.py` | — | `D/HANDBUCH_EINSTELLUNGEN.md` §6.5 |
| HA-Export / Sensoren (MQTT-Export, REST) | `/einstellungen/integration` · `F/pages/HAExportSettingsTeile.tsx` | `R/ha_export/` (`anlage_*.py`, `investition_sensoren.py`, `emob.py`, `mqtt.py`, `sensoren.py`, `konfig.py`), `R/ha_integration.py`, `R/mqtt_presets.py` | `S/ha_sensors_export.py`, `S/ha_export_bezugspreis.py`, `S/ha_export_fenster.py`, `S/ha_export_preis.py`, `S/ha_export_prognose.py`, `S/ha_mqtt_sync.py`, `S/mqtt_client.py`, `S/mqtt_presets.py`, `S/mqtt_topic_registry.py`, `S/mqtt_broker_settings.py` | `T/test_ha_export_*.py`, `T/test_mqtt_export_*.py`, `T/test_mqtt_*.py`, `T/test_export_rundung_rest_mqtt_gleich.py`, `T/test_n531_ha_export_ohne_jitter.py`, `T/test_n541_rest_export_traegt_attribute.py`, `T/test_b5_export_matrix.py` | `ha-export`, `ha-export-anlage`, `ha-export-investition` | `D/HANDBUCH_EINSTELLUNGEN.md` §6.3 · `D/SENSOR-REFERENZ.md` · `D/MQTT_INBOUND.md` |
| HA-Verbindung / Statistik-Import | `/einstellungen/integration` · `F/pages/HAStatistikImport.tsx` | `R/ha_statistics.py`, `R/ha_statistics_import.py`, `R/ha_remote.py` | `S/ha_statistics_service.py`, `S/ha_statistics_ws.py`, `S/ha_connection.py`, `S/ha_energy_service.py`, `S/ha_state_service.py` | `T/test_ha_lts_*.py`, `T/test_ha_statistics_websocket_transport.py`, `T/test_ha_recorder_*.py`, `T/test_ha_verbindung_remote_erreicht_beide_dienste.py`, `T/test_n237_lts_import_ohne_supervisor.py`, `T/test_n156_ha_wege_ohne_supervisor.py` | `ha-statistics` | `D/HANDBUCH_EINSTELLUNGEN.md` §6.2, §6.4 |
| Datenquellen (feld-zentrische Zuordnung) | `/einstellungen/datenquellen` · `F/components/live/DatenquellenZuordnung.tsx` (Wärmepumpe nach Betriebsart: `F/components/live/datenquellenBetriebsart.ts`) | `R/datenquellen.py`, `R/sensor_mapping.py` | `S/datenquellen_resolver.py`, `S/datenquellen_validierung.py`, `S/datenquellen_historie.py`, `S/datenquellen_mapping_sync.py`, `B/datenquellen.py` | `T/test_datenquellen_*.py`, `T/test_n556_datenquellen_protokoll.py`, `T/test_s2_*.py`, `T/test_p433_2_datenquellen_betriebsart.py` | — | `D/HANDBUCH_EINSTELLUNGEN.md` §7 · `D/KONZEPT-DATENQUELLEN-V4.md` · `D/KONZEPT-433-UEBERBLICK.md` |
| Live / MQTT (Inbound, Gateway) | `/einstellungen/integration` (Konfiguration), `/cockpit/live` (Anzeige) | `R/live_mqtt_inbound.py`, `R/mqtt_gateway.py` | `S/mqtt_inbound_service.py`, `S/mqtt_gateway_service.py`, `S/mqtt_energy_history_service.py`, `S/mqtt_live_history_service.py` | `T/test_mqtt_*.py`, `T/test_n400_mqtt_tages_kwh_uebergebene_sitzung.py`, `T/test_n328_mqtt_zaehler_erkennen.py`, `T/test_400_mqtt_sensor_abwahl.py`, `T/test_396_mqtt_stand_zaehler_reihe.py` | — | `D/MQTT_INBOUND.md` · `D/HANDBUCH_EINSTELLUNGEN.md` §6.1 |
| Monatsabschluss / Monatsdaten | `/einstellungen/daten` · `F/pages/MonatsdatenTeile.tsx` (Wizard-Route `monatsabschluss/*` leitet um) | `R/monatsabschluss/` (`wizard.py`, `views.py`), `R/monatsdaten.py`, `R/zaehlerstaende.py` | `S/monatsabschluss_aggregator.py`, `S/monat_loeschen.py`, `S/zaehlerstaende.py`, `S/pv_monatswerte.py` | `T/test_monatsabschluss_*.py`, `T/test_monatsdaten_tarif_aufloesung.py`, `T/test_*zaehlerstand*.py`, `T/test_zaehlerluecken_*.py`, `T/test_377_zaehlerst*.py`, `T/test_rf25_monat_faelle.py`, `T/test_n72[1-2]_*.py`, `T/test_n739_netzfeld_nicht_erfasst_im_abschluss.py` | `monatsabschluss` | `D/HANDBUCH_EINSTELLUNGEN.md` §5.1 |
| Investitionen / Komponenten-Stammdaten | `/einstellungen/komponenten` · `F/pages/InvestitionenTeile.tsx` | `R/investitionen/crud.py`, `R/anlagen.py` | `S/erzeuger_ziel.py`, `S/ust_satz.py`, `S/plz_to_state.py`, `B/anlagen_kwp.py`, `B/investitionskosten.py`, `core/investition_kennwerte.py` | `T/test_investition_*.py`, `T/test_berechnungen_anlagen_kwp.py`, `T/test_rf19_stammdaten_investitionen_faelle.py`, `T/test_bkw_*.py`, `T/test_n668_investition_loeschen_messreihen.py` | `investitionen` | `D/HANDBUCH_EINSTELLUNGEN.md` §3 |
| Komponenten-Hubs gesamt (PV, Speicher, Sonstiges) | `/komponenten/:typ` · `F/v4/KomponentenV4.tsx`, `KomponentenTypV4.tsx`, `KomponentenSektionen.tsx` | `R/investitionen/dashboards.py`, `dashboard_speicher.py`, `dashboard_sonstiges.py`, `dashboard_basis.py`, `speicher_potential.py`, `speicher_sizing.py`, `roi*.py` | `S/speicher_potential_service.py`, `S/speicher_sizing_service.py`, `S/speicher_wirtschaftlichkeit.py`, `B/speicher*.py`, `B/pv_verteilung.py` | `T/test_speicher_*.py`, `T/test_b3_hub_matrix.py`, `T/test_komponenten_dashboards_monats_fakten.py`, `T/test_sonstiges_*.py`, `T/test_roi_*.py` | `investitionen` | `D/HANDBUCH_BEDIENUNG.md` §3.2, §3.3, §3.8 |
| Balkonkraftwerk-Hub | `/komponenten/balkonkraftwerk` · `F/v4/BkwHubBloecke.tsx` | `R/investitionen/dashboard_balkonkraftwerk.py` | `B/bkw_finanz.py`, `B/wr_kappung.py` | `T/test_bkw_*.py`, `T/test_n638_bkw_hub_monatsreihe.py`, `T/test_n664_n671_bkw_hub_aus_fakten.py`, `T/test_n724_bkw_hub_gleich_tkonto.py` | `investitionen` | `D/HANDBUCH_BEDIENUNG.md` §3.7 |
| E-Auto-Hub (inkl. Wallbox) | `/komponenten/e-auto`, `/komponenten/wallbox` · `F/v4/EAutoHubBloecke.tsx`, `WallboxHubBloecke.tsx` | `R/investitionen/dashboard_eauto.py`, `dashboard_wallbox.py` | `S/emob_*.py`, `S/eauto_wirtschaftlichkeit.py`, `S/kraftstoff_preis_service.py`, `B/emob.py`, `B/heimladung_kosten.py`, `B/dienstliche_ladekosten.py`, `B/pv_anteil_ladung.py`, `B/phev_anteil.py` | `T/test_emob_*.py`, `T/test_eauto_*.py`, `T/test_rf16_eauto_dashboard_faelle.py`, `T/test_n55[5-8]_*.py`, `T/test_n564_eauto_hub_kachel_gleich_tabelle.py`, `T/test_n728_eauto_hub_extern_kopf_gleich_reihe.py`, `T/test_pv_anteil_ladung*.py` | `emob-heimladung`, `investitionen` | `D/HANDBUCH_BEDIENUNG.md` §3.5, §3.6 · `D/KONZEPT-WALLBOX-EAUTO.md` |
| Wärmepumpe-Hub (Wärme/Klima) | `/komponenten/waermepumpe` · `F/v4/WaermepumpeHubBloecke.tsx`, `waermeKlimaSicht.ts`, Block «Überblick» `F/components/komponenten/ueberblick/` (Kachel-SoT `F/components/live/EnergieFlussKachel.tsx`) | `R/investitionen/dashboard_waermepumpe.py`, `R/energie_profil/waerme.py` | `S/waermepumpe_jahreskennzahlen.py`, `S/waermepumpe_kennzahlen_je_geraet.py`, `S/waerme_klima_block.py`, `S/wp_wirtschaftlichkeit.py`, `S/waerme_verteilung.py`, `S/mitteltemperatur.py`, `B/waermepumpe_kennzahl.py`, `B/waerme_verteilung.py`, `B/heizgradtage.py`, `B/betriebsart_gemessen.py`, `B/modus_split.py` | `T/test_wp_*.py`, `T/test_waerme_*.py`, `T/test_soll_waerme_klima_*.py`, `T/test_rf17_wp_hub_faelle.py`, `T/test_rf26_klima_modus_faelle.py`, `T/test_n39[1-8]_*.py`, `T/test_n60[59]_*.py`, `T/test_263_*.py`, `T/test_p433_3_s1_live_temperaturen.py` (Live je Gerät, Überblick-Felder, Checker «Sensor ohne Langzeitstatistik»), `T/test_p433_3_s2_heizstab_zusatzheizung.py` (Heizstab-Zähler, «AZ ohne Zusatzheizung» in Tag/Hub/Monatstabelle, Summen unverändert) | `investitionen`, `live-komponenten` | `D/HANDBUCH_WAERME_KLIMA.md` · `D/HANDBUCH_BEDIENUNG.md` §3.4 |
| Auswertungen (Finanzen, ROI, CO₂, Tabelle) | `/auswertungen/:sub` · `F/v4/AuswertungenV4.tsx`, `AuswertungenFinanzenV4.tsx`, `AuswertungenRoiV4.tsx`, `AuswertungenCo2V4.tsx`, `AuswertungenTabelleV4.tsx` | `R/aussichten/finanzen.py`, `R/investitionen/roi.py`, `roi_pv.py`, `roi_eingaenge.py`, `roi_standalone.py`, `R/cockpit/nachhaltigkeit.py`, `R/energie_profil/serien.py` | `B/amortisation.py`, `B/kapitalrechnung.py`, `B/co2_amortisation.py`, `S/monats_co2.py`, `S/finanz_zeilen.py`, `B/ust_eigenverbrauch.py` | `T/test_b6_auswertungen_matrix.py`, `T/test_roi_*.py`, `T/test_amortisation*.py`, `T/test_co2_*.py`, `T/test_kapitaleinsatz_vier_sichten_symmetrie.py`, `T/test_n720_rendite_einzeljahr_nenner.py` | `ergebnisgroessen`, `investitionen` | `D/HANDBUCH_BEDIENUNG.md` §4.1, §4.2, §4.4, §4.5 |
| Jahresbericht / PDF / Monatsbericht | Berichte-Modal (`F/components/DokumentationsDialog.tsx`), `/einstellungen/infothek` | `R/import_export/pdf_operations.py`, `R/dokumentation.py` | `S/pdf/` (`engine.py`, `builders/`, `charts.py`) | `T/test_pdf_*.py`, `T/test_n13[6]_jahresbericht_mehrkosten_sot.py`, `T/test_b6_jahresbericht_symmetrie.py`, `T/test_jahresbericht_dienstwagen_ausschluss.py`, `T/test_n69[3]_jahresbericht_kopf_tarif.py`, `T/test_n61[46]_*.py`, `T/test_monatsbericht.py`, `T/test_n700_jahresbericht_speicher_wirkungsgrad.py`, `T/test_n731_pdf_mehrkosten_ist_rendite_nenner.py` | `jahresbericht` | `D/HANDBUCH_EINSTELLUNGEN.md` §4.2 · `D/KONZEPT-MONATSBERICHT.md` |
| Community | `/community/:sub` · `F/v4/CommunityV4.tsx` (+ `F/pages/community/`) | `R/community.py` | `S/community_service.py`, `S/community_client.py`, `S/community_nachsenden.py` | `T/test_community_*.py`, `T/test_n617_community_stammdaten_heute.py` | — | `D/HANDBUCH_BEDIENUNG.md` §5 · `D/HANDBUCH_EINSTELLUNGEN.md` §2.4 |
| Wetter | (Anzeige in Cockpit Live/Tag/Aussicht; Einstellung `/einstellungen/stammdaten`) | `R/wetter.py`, `R/live_wetter.py`, `R/live_wetter_antwort.py` | `S/wetter/` (`open_meteo.py`, `orchestrator.py`, `luecken.py`, `monatswerte.py`), `S/wetter_service.py`, `S/wetter_backfill_service.py`, `S/brightsky_service.py`, `S/prefetch_service.py` | `T/test_wetter_*.py`, `T/test_live_wetter_*.py`, `T/test_388_wetter_altbestand.py`, `T/test_archiv_nachzug_wetter.py`, `T/test_n69[5-8]_*.py`, `T/test_n689_live_wetter_antwortmodell.py`, `T/test_n697_grenztag_ohne_gti.py` | `wetter-monat`, `live-wetter` | `D/HANDBUCH_PROGNOSEN.md` §4 · `D/HANDBUCH_EINSTELLUNGEN.md` §2.1a |
| Strompreise / Tarife | `/einstellungen/stammdaten` · `F/pages/StrompreiseTeile.tsx` | `R/strompreise.py` | `S/strompreis_aggregator.py`, `S/strompreis_markt_service.py`, `S/preis_tag.py`, `B/preis_reihe.py`, `B/preis_rang.py`, `B/zeittarif.py`, `B/netzbezug_kosten.py`, `B/einspeise_erloes.py`, `S/einspeise_erloes_service.py` | `T/test_preis_*.py`, `T/test_zeittarif_ht_nt.py`, `T/test_einspeise_*.py`, `T/test_netzbezug_*.py`, `T/test_n663_wp_preis_flex_monatsdurchschnitt.py`, `T/test_n712_n713_symmetrie_monatspreis.py`, `T/test_n715_n716_verguetung_je_monat.py` | — | `D/HANDBUCH_EINSTELLUNGEN.md` §2.2 · `D/KONZEPT-FLEX-TARIFE.md` |
| Einstellungen (Stammdaten, System, Sperre, Infothek, Backup) | `/einstellungen/:kategorie` (`stammdaten`, `komponenten`, `infothek`, `daten`, `integration`, `datenquellen`, `system`) · `F/v4/EinstellungenV4.tsx`, `F/config/einstellungenKatalog.tsx`, `F/pages/AnlagenTeile.tsx`, `BackupTeile.tsx`, `ProtokolleTeile.tsx`, `PVGISSettingsTeile.tsx`, `InfothekTeile.tsx` | `R/anlagen.py`, `R/sperre.py`, `R/infothek.py`, `R/system_logs.py`, `R/diagnostics.py`, `R/pvgis.py`, `R/import_export/demo_data.py` | `S/infothek_datei_service.py`, `S/infothek_migration.py`, `S/activity_service.py`, `S/scheduler.py`, `S/provenance.py` | `T/test_einstellungs_sperre_*.py`, `T/test_scheduler_*.py`, `T/test_provenance*.py`, `T/test_n53[0-2]_*.py`, `T/test_n73[4-8]_*.py`, `T/test_migrations_round_trip.py` | — | `D/HANDBUCH_EINSTELLUNGEN.md` · `D/HANDBUCH_INFOTHEK.md` · `D/HANDBUCH_INSTALLATION.md` |
| Rechenkern-Wächter (bereichsübergreifend) | — | — | `B/invarianten.py`, `services/monats_fakten/`, `core/berechnungen/` | `T/test_wurzelmuster_*.py`, `T/test_berechnungs_layer_konformitaet.py`, `T/test_kognitive_komplexitaet.py`, `T/test_konformitaet_*.py`, `T/test_achsen_matrix.py`, `T/test_pv_achse_matrix.py` (Register der benannten Grenzen: `URSACHE`/`ROT` in der Matrixdatei, zählen grün — [Summenzeile](#tests--gates)), `T/test_quellbaum.py`, `T/test_routen_baseline.py` | `ergebnisgroessen` | `D/ADR-001-BERECHNUNGS-LAYER.md`, `D/ADR-002-WURZELMUSTER.md`, `D/BERECHNUNGEN.md` |

### Nicht zugeordnet

Routen-/Service-Module, die in keiner Zeile namentlich oder per Glob stehen (Abgleich: jede Datei/jedes Verzeichnis unter `eedc/backend/api/routes` und `eedc/backend/services` gegen den Text der Tabelle; `S/emob_*.py` ist über den Glob in der E-Auto-Zeile erfasst):

- Routen: keine (alle Module unter `eedc/backend/api/routes` stehen in einer Zeile)
- `eedc/backend/services/ha_integration_aufloeser.py`
- `eedc/backend/services/sensor_snapshot_service.py`
- `eedc/backend/services/vorschlag_service.py`
- `eedc/backend/services/verbrauchsprognose_heute.py`
- `eedc/backend/services/pvgis_aktualitaet.py`
- `eedc/backend/services/pv_orientation.py`
- `eedc/backend/services/provenance_migrate.py`
- `eedc/backend/services/etappe_4_migrate.py`
- `eedc/backend/services/migrations/`

Nicht durchsucht / nicht Teil der Karte: `eedc/backend/core/` außer `core/berechnungen/` und `core/investition_kennwerte.py`; `eedc/backend/models`, `schemas`, `utils`; Frontend `components/`, `hooks/`, `lib/` (nur `v4/`, `pages/`, `config/`, `routes/` herangezogen); Inhalt der Dateien (Zuordnung nach Dateiname/Routenpräfix, nicht nach Lesen); Test-Muster sind Namensmuster, nicht auf Inhalt geprüft; `eedc-community`, `eedc-card`, Spiegel `eedc`. Golden-Master-Skripte `cockpit-monat`, `analyse-leser`, `analyse-sichten`, `live-tagesverlauf`, `jahr-fold` (.mjs) liegen in `~/.claude/plans/`, stehen aber nicht in der DEVELOPMENT.md-Tabelle. Frontend-Routen aus `F/App.tsx`: `cockpit/:zeit` (live, tag, monat, jahr, aussicht), `komponenten/:typ`, `auswertungen/:sub` (finanzen, roi, co2, prognose, tabelle), `community/:sub` (uebersicht, pv-ertrag, komponenten, regional, trends, statistiken), `hilfe`, `einstellungen/:kategorie`; `aussichten/*` und `monatsabschluss/*` leiten um.

## Golden Master — Verhaltens-Fixpunkte für Umbauten (seit 12.10.2026)

Ein Golden Master (GM) friert das Verhalten einer Route oder Funktion ein, damit ein Umbau **bitgleich** bleibt. Die Skripte
liegen außerhalb des Repos unter `~/.claude/plans/skript-golden-master-*.py`; sie fassen `eedc/data/eedc.db` nie an und arbeiten
nur auf Kopien (`~/.claude/plans/**/devbox-*.db`). Es gibt zwei Bauformen:

| Bauform | Skripte | Aufruf | Was verglichen wird |
| --- | --- | --- | --- |
| **Worktree-GM** (alt gegen neu, je Lauf) | `aktueller-monat`, `aussichten`, `daten-checker`, `energie-profil`, `ergebnisgroessen`, `ha-export`, `import`, `investitionen`, `monatsabschluss`, `aggregate-day`, `wetter-monat` | `cd eedc && backend/venv/bin/python ~/.claude/plans/skript-golden-master-<name>.py --alt <ref> [--db <Kopie>]` | API-Sichten (JSON) der Referenz gegen den Arbeitsbaum, teils Schreib-Sequenz + Tabellen |
| **In-Process-GM mit Ablage** (Aufzeichnung am sauberen HEAD) | `live-komponenten`, `live-tages-kwh`, `live-wetter`, `ha-statistics`, `ha-export-investition`, `jahresbericht`, `custom-import`, `csv-import` (RF-14, Wetter-Fake auf `loese_monats_wetter`), `ha-export-anlage` (RF-15, Fakes auf `berechne_prognose_export`/`berechne_preis_export` am Modul `anlage_sensorwerte`), `prognose-kanon` (RF-21, `kanon_tagesprognose` mit Tagesschleife; Fakes nur an den Test-Patch-Zielen `get_solar_prognose`/`_get_lernfaktor(_gekappt)`/`korrekturfaktoren_fuer_tag`/Uhr, je Fall In-Memory-SQLite statt DB-Kopie), `emob-heimladung` (RF-24, `entscheide_emob_heimladung` samt Phasen in `services/emob_heimladung_phasen.py`; reine Funktion ohne DB und ohne Fakes — 41 Handfälle, 48 Eingänge der DB-Kopien in `bestand.pkl` der Ablage, 20 000 Zufallsfälle; Ablage eine gzip-Datei `faelle.jsonl.gz` statt einer Datei je Fall), `prognosen-vergleich` (RF-28, `get_prognosen_vergleich` samt Phasen in `api/routes/prognosen.py`; Fakes auf `fetch_open_meteo_forecast`/`get_solcast_forecast`/`kanon_tagesprognose`/`_get_lernfaktor_detail` am Modul `prognosen`, dazu SFML-Discovery, HA-Dienst und Uhr; 104 synthetische Fälle in In-Memory-SQLite + 16 Läufe auf drei DB-Kopien mit echtem Lernfaktor), `fronius-parser` (RF-36, `FroniusSolarwebParser.parse` samt Phasen in `services/import_parsers/fronius_solarweb.py`; reine Funktion ohne DB und ohne Fakes — 10 Testfälle, die Inline-CSV des Import-GM, 52 synthetische Varianten je Verzweigung, 3 000 Zufallsfälle; Ablage `faelle.jsonl.gz`; `--abdeckung` belegt jede Verzweigung von `parse` und seinen Phasen), `solar-prognose-build` (RF-38, `_build_prognose` samt Phasen in `services/solar_forecast_service.py`; reine Funktion ohne DB, Uhr am geladenen Modul festgenagelt (`abgerufen_am`) — 21 Eingänge der Tests (eingefroren in der Ablage), 8 `om()`-Fakes des Live-Wetter-GM, 137 synthetische Varianten (Tage 1…17, fehlende/überzählige Stunden, None-Zellen, Zeitumstellung 23/25 h, 0-Werte, Ränder), 3 000 Zufallsfälle; Ablage `faelle.jsonl.gz`; `--abdeckung` instrumentiert die Quelle im Speicher und belegt jede Bedingungs-Seite von `_build_prognose` und seinen Phasen) | `cd eedc && [GM_TMP=<scratch>] backend/venv/bin/python -I -B ~/.claude/plans/skript-golden-master-<name>.py --aufzeichnen \| --vergleichen \| --abdeckung \| --gegenprobe head\|kandidat` | Rohrückgabe/Kontext mit Schlüsselfolge, Float-`repr`, Aufrufprotokoll der Fakes, Log, SQL-Folge; Ablage `~/.claude/plans/golden-master/<name>/` mit Manifest (HEAD-Hash) |

**Regeln, alle gemessen (Serie RF-4…RF-10, Oktober 2026):**

1. **Aufzeichnen nur am sauberen Baum** — das Skript bricht sonst ab. Nach jedem Commit, der die gedeckte Funktion ändert, neu
   aufzeichnen; vorher `--vergleichen` zeigt, ob nur die gewollten Fälle abweichen (Liste gehört in den Commit-Text).
2. **Fester Hash-Seed.** Die Parameterfolge eines SQL-`IN (…)` hängt an `PYTHONHASHSEED`; die Skripte starten sich selbst mit
   festem Seed neu. ⚠ `python -I` wirft Umgebungsvariablen weg — deshalb den Aufruf aus dem Skript-Kopf nehmen, nie
   `PYTHONHASHSEED=0 python -I …` von Hand (ergab 89/95 und lauter «rote» Sprengsätze, die Rauschen waren).
3. **Rauschen über zwei getrennte Prozesse messen**, nicht nur im selben Prozess.
4. **Ein GM ist erst scharf, wenn die Gegenprobe rot kann.** `--gegenprobe` legt je Verzweigungsklasse einen Sprengsatz auf eine
   Scratch-Kopie; «rot in ≥ 2 Fällen», «0 nicht scharf», Nullprobe grün. Breite allein ist blind: volle Anweisungsabdeckung ließ
   in RF-4 zwei und in RF-5 sechs Sprengsätze still — erst Entscheidungs-Kombinationen und Nachkommastellen fingen sie.
5. **Sprengsätze altern mit dem Code.** Nach jedem Schnitt die Gegenprobe auf dem **neuen** Stand fahren; Suchtexte, die nicht
   mehr vorkommen, melden «NICHT SCHARF» und sind nachzuziehen (zwei Textsätze `head`/`kandidat` im Skript).
6. **Die Zählung muss diskriminieren**: Nullprobe x/x grün, ein bekannter Sprengsatz < x/x — sonst zählt das Werkzeug nur Fälle.
7. **Arbeitskopien räumen**: Worktree-GMs legen `/tmp/golden-*`, `/tmp/gm-erg-*` an und räumen nicht (17 GB in acht Tagen, Platte
   voll am 11.10.) — nach jeder Runde `rm -rf /tmp/golden-* /tmp/gm-erg-*`.
8. **Was ein GM nicht sieht:** nur das, was ein Fall enthält. Kein Bestand der Kopien trägt eine Tariflücke, einen gepflegten
   Monats-Ø, Kombi-Sensor + Zähler oder Sonstiges mit Zähler — solche Fälle wurden je Fund synthetisch ergänzt.
9. **Fixture-DBs nach jeder neuen Start-Migration einmal migrieren.** Die untracked Kopien `eedc/data/devbox-*.db` laufen sonst bei jedem
   In-Process-GM-Lauf erneut durch die Migration, die `updated_at` der betroffenen Zeilen neu setzt — der GM rauscht (gemessen 12.10. an der
   N-738-Migration: fünf Formularzeilen der Prüf-DB). Handgriff: Backup der Kopien in den Scratch, `init_db()` einmal gegen jede Kopie, danach
   die betroffenen GMs neu aufzeichnen (Regel 1).

Fehlt für eine Route ein GM, ist er **Schritt 0** des Umbaus (Muster: RF-6 für reine Funktionen mit Fakes an den Test-Nähten,
RF-8/RF-9 für Routen mit SQL-Folge, RF-5 für Schreibpfade mit Tabellenvergleich).

