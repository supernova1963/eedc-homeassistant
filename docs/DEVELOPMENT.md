
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

# Dependencies installieren
pip install -r requirements.txt
```

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

Für Tests in einer echten Home Assistant Umgebung:

1. Repository zu HA Add-on Repositories hinzufügen:
   - Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories
   - URL: `https://github.com/supernova1963/eedc-homeassistant`
2. Add-on installieren und starten
3. Über Sidebar "eedc" öffnen

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
- `black` und `ruff` stehen in `requirements.txt` **auskommentiert** und sind **kein Gate**. Wer
  formatiert, formatiert von Hand im Stil der Umgebung — kein Repo-weiter Reformat-Lauf.
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

SoT ist `eedc/backend/services/monats_fakten.py`. Wer eine abgeleitete Monatsgröße auswertet,
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
│   ├── KONZEPT-BERECHNUNGS-LAYER.md · KONZEPT-COMMUNITY.md · KONZEPT-MOBILE.md
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
    │   │   ├── aktueller_monat.py       # Cockpit → Monat (laufender + gespeicherter Monat)
    │   │   ├── anlagen.py               # Anlagen-CRUD + Anlagenfoto
    │   │   ├── aussichten.py            # Prognose-Aussichten (Kurz/Lang/Trend/Finanzen)
    │   │   ├── prognosen.py             # Prognose-Vergleich, Genauigkeits-Tracking
    │   │   ├── cockpit.py + cockpit/    # Übersicht · Komponenten · Nachhaltigkeit · Jahr
    │   │   ├── monatsdaten.py           # Monatsdaten-CRUD + Aggregation
    │   │   ├── monatsabschluss/         # Monatsabschluss-Formular + Datenquellen-Status
    │   │   ├── investitionen/           # Komponenten, ROI, Stilllegung, Kennwerte
    │   │   ├── strompreise.py           # Tarife, Spezialtarife, Gültigkeitsfenster
    │   │   ├── energie_profil/          # Tages-/Stundenprofile, Reaggregation
    │   │   ├── live_dashboard.py        # Live-Kern (Fluss, Tagesverlauf, Börsenpreise)
    │   │   ├── live_mqtt_inbound.py · live_wetter.py
    │   │   ├── mqtt_gateway.py · mqtt_presets.py   # beide unter /api/live eingehängt
    │   │   ├── datenquellen.py          # Datenquellen-Fläche (ein Feld = eine Quelle)
    │   │   ├── sensor_mapping.py        # HA-Sensor-Zuordnung (nur HA_MODE)
    │   │   ├── ha_integration.py · ha_import.py · ha_statistics.py · ha_export.py · ha_remote.py
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
    │   │   ├── monats_luecken.py · source_priority.py · field_definitions.py
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
    │   │   ├── monats_fakten.py      # ADR-002/P10: die Monatszeile wird EINMAL aufbereitet
    │   │   ├── pv_monatswerte.py     # P7: lade_pv_je_monat / pv_summe_je_monat
    │   │   ├── preis_tag.py          # eine Schicht für Preis-Chart UND HA-Sensoren
    │   │   ├── energie_profil/       # Tages-Aggregation, Monats-Rollup, Tag-Status
    │   │   ├── snapshot/             # 5-Min-/Stunden-Snapshots + aggregator.py
    │   │   ├── daten_checker/        # Kategorien der Datenqualitäts-Prüfung
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
    │   ├── tests/                   # ~300 pytest-Dateien, darunter die Wächter:
    │   │   ├── test_wurzelmuster_konformitaet.py      # ADR-002 P1–P10, baumweit
    │   │   ├── test_berechnungs_layer_konformitaet.py # ADR-001
    │   │   └── test_netto_ertrag_vier_wege_symmetrie.py  # Symmetrie über vier Finanz-Sichten
    │   └── utils/
    │
    └── frontend/                    # React + TypeScript + Vite + Tailwind
        ├── package.json             # Skripte: dev · build · test · lint · check:* (Wächter)
        ├── vite.config.ts · vitest.config.ts   # vitest pinnt die Zeitzone Europe/Berlin
        ├── scripts/check-*.mjs      # die Darstellungs-Wächter (Regel 0/0a)
        ├── dist/                    # versioniert! (Add-on liefert den Build aus)
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
            │   ├── JahrRahmen.tsx · JahrBilanz.tsx · JahrAggregat.tsx · JahresRail.tsx
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
            │   ├── sensor-mapping/ · connector/ · import/ · setup-wizard/
            │   ├── infothek/ · repair/ · layout/ · common/ · preview/
            │   └── AppWithSetup.tsx · AppErrorBoundary.tsx · DokumentationsDialog.tsx
            │
            ├── pages/               # Einstellungs-Flächen + Teile, die V4 einbindet
            │   ├── Einrichtung.tsx · AnlagenTeile.tsx · InvestitionenTeile.tsx
            │   ├── MonatsdatenTeile.tsx · StrompreiseTeile.tsx · InfothekTeile.tsx
            │   ├── EnergieprofilTeile.tsx · DatenCheckerTeile.tsx · ProtokolleTeile.tsx
            │   ├── BackupTeile.tsx · HAExportSettingsTeile.tsx · PVGISSettingsTeile.tsx
            │   ├── HAStatistikImport.tsx · DataImportWizard.tsx · CsvImportWizard.tsx
            │   ├── CloudImportWizard.tsx · CustomImportWizard.tsx · ConnectorSetupWizard.tsx
            │   └── DesignPreview.tsx
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

**Reihenfolge ist nicht beliebig:** `tsc --noEmit` kommt **vor** dem ersten vollen Vitest-Lauf. Ein
vergessener Import fällt dort in Sekunden auf, im Vitest-Lauf erst nach Minuten und mit
irreführender Fehlermeldung.

```bash
# 1. Backend (bei Backend-Arbeit vollständig)
cd eedc && source backend/venv/bin/activate && python -m pytest backend/tests -q

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
| `check:park-leertest` | **Playwright-Livetest** gegen eine laufende Box, verlangt ein `VITE_DEMO_DEFAULT=true`-Build. **Danach zwingend** `git checkout -- eedc/frontend/dist/ && git clean -fdq eedc/frontend/dist/` — `dist/` ist versioniert, sonst landet ein Demo-Build im Release |
| `check:form-controls` | meldet „1 offen (WelcomeStep.tsx)" als **dokumentierte Baseline** (rc=0) |
| `check:de-de` | **Scope über einen Import-Graph**, nicht über Verzeichnisse: `src/v4/` + `src/components/` als Startknoten, dazu die transitive Hülle der von dort erreichten `pages/`- und `config/`-Dateien. ⚠ **Wer den Graph anfasst, prüft beide Kanten-Formen**: `from '…'` **und** `lazy(() => import('…'))`. Bis 13.08. fehlte die dynamische Form — die sieben Einstellungs-Wizards hingen genau daran und lagen samt 15 roher Anzeigen außerhalb; die zehn `pages/*Teile.tsx` fielen an der `config/`-Kante heraus. **Ein Wächter, dessen Reichweite an der Import-Form hängt statt an der Sichtbarkeit, prüft die falsche Menge.** Der Rest-Zähler („N Treffer außerhalb") ist **keine Schuldenzahl** — er enthält auch Nicht-Anzeigen wie URL-Parameter in `src/api/` |

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
| `/api/ha-import` | *(HA_MODE)* `ha_import` | Datenimport aus HA |
| `/api/sensor-mapping` | *(HA_MODE)* `sensor_mapping` | HA-Sensor-Zuordnung inkl. Strompreis |
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
   Deshalb sind `KONZEPT-DATENQUELLEN-V4.md`, `KONZEPT-LADEZEIT-CACHE-SWR.md` und
   `IA-V4-SOT-INVENTAR.md` dorthin gewandert, so wie vorher schon
   [KONZEPT-MONATS-FAKTEN.md](KONZEPT-MONATS-FAKTEN.md).
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
| [IA-V4-SOT-INVENTAR.md](IA-V4-SOT-INVENTAR.md) | Register der UI-SoT-Patterns (Invariante I12) |
| [KONZEPT-DATENQUELLEN-V4.md](KONZEPT-DATENQUELLEN-V4.md) | eine Quelle je Feld, HA-first (Invariante I16) |
| [KONZEPT-LADEZEIT-CACHE-SWR.md](KONZEPT-LADEZEIT-CACHE-SWR.md) | SoT für `hooks/useApiData.ts` (SWR, Skeletons) |
| [KONZEPT-HA-EXPORT-ARCHITEKTUR.md](KONZEPT-HA-EXPORT-ARCHITEKTUR.md) | was nach HA exportiert wird — und was nie |
| [KONZEPT-FOKUS-DEEPLINK.md](KONZEPT-FOKUS-DEEPLINK.md) · [KONZEPT-CHART-TABELLEN.md](KONZEPT-CHART-TABELLEN.md) · [KONZEPT-263-klima-split.md](KONZEPT-263-klima-split.md) | geplante Pakete aus der Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) |
| [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md) | Release-Prozess beider Repos |
| [SETUP_DEVMACHINE.md](SETUP_DEVMACHINE.md) | Entwicklungsrechner einrichten |
| [SENSOR-REFERENZ.md](SENSOR-REFERENZ.md) · [MQTT_INBOUND.md](MQTT_INBOUND.md) | Sensor-Felder · Topic-Struktur |
| [BENUTZERHANDBUCH.md](BENUTZERHANDBUCH.md) | Endnutzer-Index (Installation, Bedienung, Einstellungen) |
| [CLAUDE.md](../CLAUDE.md) | Entwickler-/KI-Kontext: Patterns, Fallstricke, Git-Regeln |

---

*Dieses Dokument trägt keine Versionsnummer — siehe Kopf. Stand der letzten Messung: 2026-08-07, Layer- und Service-Listen 2026-08-11.*
