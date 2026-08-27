
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
    │   │   ├── ha_integration.py · ha_statistics.py · ha_export.py · ha_remote.py
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
    │   ├── tests/                   # ~400 pytest-Dateien, darunter die Wächter:
    │   │   ├── conftest.py           # die `db`-Fixture (In-Memory je Test) + Netzsperre
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
    datei.rel      # "services/monats_fakten.py" — der Name, den der Prüfer meldet
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
| [KONZEPT-FOKUS-DEEPLINK.md](KONZEPT-FOKUS-DEEPLINK.md) · [KONZEPT-CHART-TABELLEN.md](KONZEPT-CHART-TABELLEN.md) | geplante Pakete aus der Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) |
| [KONZEPT-263-klima-split.md](KONZEPT-263-klima-split.md) · [KONZEPT-263-INNENGERAETE.md](KONZEPT-263-INNENGERAETE.md) | **abgeschlossen und gebaut** — zwei **Bauform-Kapitel** (Split-Klimaanlage · Multisplit-Innengeräte). ⚠ **Nicht das Konzept der Fläche „Heizen · Warmwasser · Kühlen“** — das ist das Flächen-Konzept *SOLL Wärme/Klima* (**Maintainer-intern, noch nicht im Repo**). Beide Kapitel tragen im Kopf eine Korrekturliste. **Bis 27.08. standen sie hier unter „geplante Pakete“** |
| [HANDBUCH_WAERME_KLIMA.md](HANDBUCH_WAERME_KLIMA.md) | Wärme/Klima aus Anwendersicht — Erfassungswege, Werte des Modus-Sensors, Kennzahlen, FAQ. **Auch für Entwickler die schnellste Antwort auf „was sieht der Melder?“** |
| [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md) | Release-Prozess beider Repos |
| [SETUP_DEVMACHINE.md](SETUP_DEVMACHINE.md) | Entwicklungsrechner einrichten |
| [SENSOR-REFERENZ.md](SENSOR-REFERENZ.md) · [MQTT_INBOUND.md](MQTT_INBOUND.md) | Sensor-Felder · Topic-Struktur |
| [BENUTZERHANDBUCH.md](BENUTZERHANDBUCH.md) | Endnutzer-Index (Installation, Bedienung, Einstellungen) |
| [CLAUDE.md](../CLAUDE.md) | Entwickler-/KI-Kontext: Patterns, Fallstricke, Git-Regeln |

---

*Dieses Dokument trägt keine Versionsnummer — siehe Kopf. Stand der letzten Messung: 2026-08-07, Layer- und Service-Listen 2026-08-11.*
