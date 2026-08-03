# CLAUDE.md - Entwickler-Kontext für Claude Code

> Für Detail-Dokumentation siehe: [Architektur](docs/ARCHITEKTUR.md) | [Entwicklung](docs/DEVELOPMENT.md) | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md)

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** hier bewusst **keine Zahl** — Versions-SoT ist [CHANGELOG.md](CHANGELOG.md) (oberster released Abschnitt) bzw. `eedc/backend/core/config.py::APP_VERSION`. `release.sh` bumpt CLAUDE.md **nicht**; eine Zahl an dieser Stelle veraltet daher garantiert (sie stand bis 2026-07-27 auf 3.45.5, während v4.0.1 released war).

## Verbundene Repositories

| Repository | Zweck | Technik |
| --- | --- | --- |
| **eedc-homeassistant** (dieses) | Source of Truth, HA-Add-on, Website, Docs | FastAPI, React, SQLite |
| **[eedc](https://github.com/supernova1963/eedc)** | Standalone-Distribution für Nutzer ohne HA | Spiegel von eedc/ |
| **[eedc-community](https://github.com/supernova1963/eedc-community)** | Anonymer Community-Benchmark-Server | FastAPI, React, PostgreSQL |

**Lokale Pfade:**
- eedc: `/home/gernot/claude/eedc`
- eedc-community: `/home/gernot/claude/eedc-community`

**Live:** https://energy.raunet.eu (Community) | https://supernova1963.github.io/eedc-homeassistant/ (Website)

## Git-Workflow (WICHTIG – gilt für alle Sessions und Rechner!)

### Regeln

1. **Immer auf `main` arbeiten** — keine Feature-Branches. Einzelentwickler-Projekt.
2. **eedc-homeassistant ist Source of Truth** — ALLE Änderungen (backend, frontend, docs, HA-Config) hier machen. Nie direkt in `eedc`.
3. **`eedc`-Repo wird nur per Release-Script synchronisiert** — kein manuelles Editieren, kein Subtree.
4. **Versionsnummern + Release** nur wenn der User es explizit anfordert.
5. **`eedc-community`** ist unabhängig, aber bei Datenmodell-Änderungen beide Repos synchron anpassen.

### Verboten!

- **Direkt im `eedc`-Repo arbeiten** — das ist nur ein Spiegel, wird per Script synchronisiert
- **`git subtree pull/push`** — wird nicht mehr verwendet
- **Releases, Tags, Versionsnummern ändern** — nur auf explizite User-Aufforderung
- **`git push`** — nur auf User-Aufforderung oder über `scripts/release.sh`

### Verzeichnisstruktur

```text
eedc-homeassistant/           ← Source of Truth
├── eedc/                     ← Gesamte Anwendung
│   ├── backend/              ← FastAPI Backend (Python)
│   ├── frontend/             ← React Frontend (TypeScript)
│   ├── Dockerfile            ← HA-spezifisch (mit Labels, jq, run.sh)
│   ├── config.yaml           ← HA Add-on Konfiguration
│   ├── run.sh                ← HA Container-Startscript
│   ├── icon.png / logo.png   ← HA Add-on Icons
│   ├── CHANGELOG.md          ← Kopie von Root (per Script)
│   ├── docker-compose.yml    ← Für Standalone-Nutzung
│   └── README.md             ← Projekt-README
├── website/                  ← Astro Starlight Website
├── scripts/                  ← Release + Utility Scripts
├── docs/                     ← Single Source of Truth für Dokumentation
├── CHANGELOG.md              ← Master-CHANGELOG (hier editieren!)
├── CLAUDE.md
└── repository.yaml
```

## Quick Reference

### Entwicklungsserver starten

```bash
# Backend (Terminal 1)
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend (Terminal 2)
cd eedc/frontend && npm run dev

# URLs: Frontend http://localhost:3000 | API Docs http://localhost:8099/api/docs
```

### Gates (vor jedem Commit-Paket vollständig laufen lassen)

```bash
cd eedc && source backend/venv/bin/activate && python -m pytest backend/tests -q
cd eedc/frontend && npm run test && npx tsc --noEmit && npm run check:design && \
  npm run check:de-de && npm run check:roh-controls && npm run check:parkbar && \
  npm run check:form-controls && npm run check:typografie && npm run check:kennwert-roh && \
  npm run check:co2-roh
```

Die Soll-Zahlen (pytest/Vitest) stehen **nicht hier**, sondern im laufenden Master-Register unter `~/.claude/plans/` — sie ändern sich mit jedem Paket. `check:form-controls` meldet „1 offen (WelcomeStep.tsx)" als dokumentierte Baseline. `check:park-leertest` ist ein Playwright-Livetest gegen eine laufende Box und verlangt ein `VITE_DEMO_DEFAULT=true`-Build; **danach zwingend** `git checkout -- eedc/frontend/dist/ && git clean -fdq eedc/frontend/dist/` — `dist/` ist versioniert, sonst landet ein Demo-Build im Release.

### Release-Workflow (ein Script für alles!)

```bash
cd /home/gernot/claude/eedc-homeassistant
./scripts/release.sh <version>   # Zielversion, z. B. die nächste Patch-Nummer laut CHANGELOG
```

Das Script macht automatisch:
1. Bumpt Version in allen 5 Dateien
2. Kopiert CHANGELOG nach eedc/
3. Committed + taggt + pusht eedc-homeassistant
4. Synchronisiert backend/ + frontend/ nach eedc-Standalone
5. Committed + taggt + pusht eedc

**Versionsdateien (5 Stück, alle in eedc/):**

| Datei | Zweck |
| --- | --- |
| `backend/core/config.py` | APP_VERSION (Backend) |
| `frontend/src/config/version.ts` | APP_VERSION (Frontend) |
| `config.yaml` | HA Add-on Version |
| `run.sh` | Startup-Banner |
| `Dockerfile` | `io.hass.version` Label |

> **WICHTIG:** HA Add-ons lesen `eedc/CHANGELOG.md`. Das Release-Script kopiert automatisch.

### Website (Astro Starlight)

```bash
cd website && npm run dev    # http://localhost:4321/eedc-homeassistant/
cd website && npm run build  # Synct automatisch docs/ → website/ (via scripts/sync-docs.sh)
```

**Technik:** Astro Starlight (v0.37), GitHub Pages, German-only
**Deployment:** Automatisch via `.github/workflows/deploy-website.yml` bei Push auf `main`
**Single Source of Truth:** Dokumentationen in `docs/` pflegen, `scripts/sync-docs.sh` generiert Website-Versionen mit Frontmatter.

**Starlight-Hinweis:** Invertierte Farbskala im Light Mode! `--sl-color-white` = Text, `--sl-color-black` = Hintergrund. Grau-Skala in `custom.css` definieren.

## Architektur-Prinzipien

1. **Standalone-First:** Keine HA-Abhängigkeit für Kernfunktionen
2. **Datenquellen getrennt:** `Monatsdaten` = Zählerwerte, `InvestitionMonatsdaten` = Komponenten-Details
3. **Legacy-Felder NICHT verwenden:** `Monatsdaten.batterie_*` und das computed-Trio (`eigenverbrauch_kwh`, `direktverbrauch_kwh`, `gesamtverbrauch_kwh`) → erst `InvestitionMonatsdaten`, Legacy nur als expliziter Fallback
4. **`Monatsdaten.pv_erzeugung_kwh` ist KEIN Legacy-Feld, aber auch keine Lesequelle** (Gernot 2026-07-29, ADR-002/**P7**): manuelles bzw. importiertes Anlagen-Aggregat und **ausschließlich Eingang** von `resolve_pv_je_modul` — geladen über `services/pv_monatswerte.py`, nie direkt verrechnet. Einzelwerte und ihre Summe haben immer Vorrang; das Aggregat füllt nur die Lücken der Module **ohne** eigenen Wert. Programmatisch füllen bleibt verboten. Der baumweite Wächter ist `test_wurzelmuster_konformitaet.py::test_p7_*` (Baseline 0). Detail: [BERECHNUNGEN §1](docs/BERECHNUNGEN.md), [ADR-002](docs/ADR-002-WURZELMUSTER.md)
5. **Die Monatszeile wird genau einmal aufbereitet** (ADR-002/**P10**): `services/monats_fakten.py` löst auf, filtert (`aktiv` · Anschaffung · Stilllegung · Dienstwagen) und **ruft** die Layer-Formeln — keine Read-Site faltet `InvestitionMonatsdaten` mehr selbst. Verallgemeinerung von P7 von einer Größe auf die ganze Zeile; Auslöser war die Drift-Inventur 2026-07-31 (sechs Befunde, **kein** Rechenfehler im Layer). **Seit S5 baumweit gewächtert** (`test_wurzelmuster_konformitaet.py::test_p10_*`, funktions-granular, Baseline 0); **der Bauplan ist mit S6 abgearbeitet**, die Restschuld steht gezählt in `P10_NOCH_NICHT_MIGRIERT` (**2** seit C1b). Detail: [KONZEPT-MONATS-FAKTEN](docs/KONZEPT-MONATS-FAKTEN.md), [ARCHITEKTUR §7](docs/ARCHITEKTUR.md)

## Drei SoT-Regime — nicht mischen

| Dokument | Regelt | Maschinelles Gegenstück |
| --- | --- | --- |
| [`docs/KONZEPT-STYLE-GUIDE.md`](docs/KONZEPT-STYLE-GUIDE.md) (Regel 0/0a) | **Darstellung** — Farben, Komponenten, Typografie, Chart-Konventionen | die `check:*`-Skripte im Frontend (`eedc/frontend/scripts/check-*.mjs`) |
| [`docs/ADR-001-BERECHNUNGS-LAYER.md`](docs/ADR-001-BERECHNUNGS-LAYER.md) | **Schichtung** — *wo* eine Aggregat-Formel definiert wird (`core/berechnungen/`) | `backend/tests/test_berechnungs_layer_konformitaet.py` |
| [`docs/ADR-002-WURZELMUSTER.md`](docs/ADR-002-WURZELMUSTER.md) | **Invarianten** — *was* ein Wert behaupten darf und woher er kommen muss (P1–P10) | `backend/tests/test_wurzelmuster_*.py` |

> **Backend-Wächter sind pytest, keine `check:*`-Skripte** — alle `check:*` sind Frontend-Node-Skripte. **Zwei** Ausnahmen mit eigener Begründung, beide bewachen die Client-Hälfte einer Backend-Regel: `check:kennwert-roh` für ADR-002/P3-a und `check:co2-roh` für ADR-001/DI-2 (der Client konstruiert keine CO₂-Menge; `CO2_FAKTOR_KG_KWH` darf nur noch *angezeigt* werden).
>
> ADR-002 trägt die Pflicht-Spalte **„gesichert durch"** mit der Unterscheidung **Wächter** (baumweit, fängt auch eine Stelle, die es heute noch nicht gibt) und **Regression** (schützt nur die namentlich aufgerufenen Stellen). Wer die Spalte fortschreibt, trägt die Art der Deckung mit ein — eine Regel ohne Code-Beleg gilt als nicht gesichert.

## Design-Konventionen (Regel 0a — Pflicht bei allem Neuen)

> SoT: [`docs/KONZEPT-STYLE-GUIDE.md`](docs/KONZEPT-STYLE-GUIDE.md) (Regel Nr. 0 + 0a am Anfang). Farb-SoT: `frontend/src/lib/colors.ts`.

Bei **allem mit Darstellung** (Seite, Komponente, Chart, Tabelle, Tooltip, Button, Badge, Bericht, Text, Sensor-Name …) gilt: (1) **Regel/SoT existiert → anwenden** (keine lokale/harte Formatierung daneben); (2) **keine, aber sinnvoll → Regel definieren + Zentrale erweitern in derselben Arbeit**; (3) **echter Einzelfall → Maintainer-Freigabe + Code-Kommentar + Ausnahmen-Liste**.

- **Keine Inline-Hex-Farben** außerhalb `lib/colors.ts`. **Pflicht-Check bei Frontend-Arbeit:** `cd eedc/frontend && npm run check:design` (muss 0 melden) — Allowlist-Eintrag = bewusste Freigabe.
- **Eine Datenrolle = eine Farbe** (`lib/colors.ts`); **eine Komponenten-Klasse = eine SoT-Komponente** (KPICard, Button, ChartTooltip, Modal …) — nie eine zweite Komponente für ein bestehendes Pattern.
- **Typ-Reihenfolge** immer aus `INVESTITION_TYP_ORDER`/`compareTyp` bzw. Backend `sort_investitionen_nach_typ`. **Datums-Listen/Tabellen** Default absteigend (neueste zuerst). **% mit Leerzeichen**, **„eedc"** klein.

## Kritische Code-Patterns

### Monatswerte nur aus den Monats-Fakten (ADR-002/P10)

SoT ist `eedc/backend/services/monats_fakten.py`. Wer eine abgeleitete Monatsgröße auswertet, faltet `InvestitionMonatsdaten` **nicht selbst**:

```python
from backend.services.monats_fakten import lade_monats_fakten, finanz_zeile_eingabe

fakten = await lade_monats_fakten(db, anlage_id, von=(2025, 1), bis=(2025, 12))
for f in fakten:                          # RICHTIG — Zeitfilter + Dienstwagen-
    pv    = f.erzeugung.pv_kwh            #   Filter + Auflösung sind schon drin
    bilanz = f.erzeugung.hinter_zaehler_kwh   # EV/Autarkie: inkl. BHKW & Co.
    zeile  = await baue_finanz_zeile(db, anlage_id, finanz_zeile_eingabe(f), ...)

# FALSCH — die Klasse hinter allen sechs Befunden der Inventur 2026-07-31:
for imd in await db.execute(select(InvestitionMonatsdaten)...):
    summe += (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0)
```

Ausgenommen sind **Schreib-, Import- und Checker-Pfade**. Der baumweite Wächter ist **seit S5 scharf** (`test_wurzelmuster_konformitaet.py::test_p10_*`) — **funktions-granular**, damit eine ausgenommene Datei nicht als Ganzes freigestellt ist, mit drei getrennt klassifizierten Ausnahme-Kategorien (`SCHREIBEN_IMPORT_CHECKER` · `PER_INVESTITION` · `NOCH_NICHT_MIGRIERT`, letztere mit Obergrenze im Test). **Umgehängt seit S2:** Aussichten, Jahresbericht-PDF, Investitions-ROI; **S3** Cockpit/CO₂ + Social; **S4** Cockpit/Übersicht + HA-Export; **S5** Komponenten-Dashboards, dazu die PR-Pfade der Aussichten und Prognose-vs-IST; **S6** Community-Payload — damit ist der Bauplan abgearbeitet. **Teil-migriert** — Monatsgrößen ja, per-Investition-Aggregate nein: `aussichten.py`, `ha_export.py`, `investitionen/crud.py`, `dashboards.py`. **C1a** (03.08.) hat `monatsdaten.py::list_monatsdaten_aggregiert` umgehängt — *Auswertungen → Tabelle* und *Cockpit → Jahr*; **C1b** (03.08.) `cockpit/komponenten.py::get_komponenten_zeitreihe` — *Auswertungen → Komponenten*. **Noch anlagenweit selbst faltend (offene Schuld, 2):** `aktueller_monat.py` (2 Funktionen).

### SQLAlchemy JSON-Felder

```python
from sqlalchemy.orm.attributes import flag_modified
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")  # Ohne das wird die Änderung NICHT persistiert!
db.commit()
```

### 0-Werte prüfen

```python
# FALSCH: if val:     → 0 wird als False gewertet
# RICHTIG: if val is not None:
```

### Investitions-Kennwerte nur über den SoT-Helper (ADR-002/P3-a)

SoT ist `eedc/backend/core/investition_kennwerte.py`:

```python
from backend.core.investition_kennwerte import get_erzeuger_kwp, get_pv_kwp, get_bkw_kwp

kwp = get_erzeuger_kwp(inv)          # RICHTIG — Typ-Dispatcher (BKW vs. PV-Modul)
kwp = inv.leistung_kwp               # FALSCH — Spalte allein, die #229-Klasse
kwp = getattr(inv, "leistung_kwp")   # FALSCH — der Wächter erfasst auch diese Form
```

Die Nennleistung liegt je nach Herkunft in der **Spalte** `Investition.leistung_kwp` **oder** im `parameter`-JSON. Beide Formen sind gewächtert (`test_wurzelmuster_konformitaet.py::test_p3a_*`, Baseline 0 mit klassifizierten Ausnahmen); im Frontend hält `npm run check:kennwert-roh` dieselbe Trennlinie (**Anzeige/Rechnung** lesen `leistung_kwp_effektiv` aus der Response, **Formulare/Wizards** die Rohspalte). Der `getattr`-Zweig ist nicht optional — über ihn fiel `co2_amortisation.py` durch jede Erhebung.

> `Investition.leistung_kwp` ist ein **Mehrzweckfeld**: beim Speicher trägt dieselbe Spalte kWh, beim Wechselrichter kW (AC). Die Helper gelten nur für Erzeuger-Typen; der Aufrufer filtert.

## Bekannte Fallstricke

| Problem | Lösung |
|---------|--------|
| JSON-Änderungen werden nicht gespeichert | `flag_modified(obj, "field_name")` aufrufen |
| 0-Werte verschwinden | `is not None` statt `if val` |
| SOLL-IST zeigt falsches Jahr | `jahr` Parameter explizit übergeben |
| `Monatsdaten.pv_erzeugung_kwh` programmatisch gefüllt **oder direkt gelesen** | Nur manuell/Import; Pro-Modul-Werte nach `InvestitionMonatsdaten`. Lesen ausschließlich über `lade_pv_je_monat`/`pv_summe_je_monat` (P7, s. Prinzip 4) — direkt gelesen ist es entweder eine Teilsumme oder es überschreibt Messungen |
| ROI-Werte unterschiedlich | Cockpit = Jahres-%, Aussichten = Kumuliert-% |
| Zwei Sichten nennen verschiedene CO₂-Zahlen | `berechne_co2_bilanz` ist die **einzige** Konstruktions-Stelle (ADR-001/DI-2: Eigenverbrauch × Strommix **+ WP + E-Mob**), ausgeliefert über `/cockpit/nachhaltigkeit`. Der Client rechnet nichts — Wächter `npm run check:co2-roh`. Der **Tages**-Wert trägt bewusst nur `co2_pv_kg` (WP-Wärme/E-Mob-km gibt es nur monatlich) ⇒ Σ Tage ≠ Monat |
| Nennleistung ist plötzlich 0 | Bei Import-/Altbestand (#229) steht die kWp **nur im `parameter`-JSON** (`kwp` / `leistung_kwp`) — die Spalte allein zu lesen liefert dort still 0. `get_erzeuger_kwp` statt `inv.leistung_kwp` |

## Community-Datenfluss

```
eedc Add-on                                   Community Server
┌───────────────────────────────┐             ┌────────────────────────┐
│ v4/CommunityShareBlock.tsx    │ ─ POST ───→ │ /api/submit            │
│   (teilen / rückw. entfernen) │ ─ DELETE ─→ │ /api/submit/{hash}     │
│ v4/CommunityV4.tsx +          │ ─ Proxy ──→ │ /api/benchmark/        │
│   pages/community/*Teile.tsx  │             │   anlage/{hash}        │
│ "Im Browser öffnen"           │ ─ Link ───→ │ /?anlage=HASH          │
└───────────────────────────────┘             └────────────────────────┘
```

> Der Client spricht den Community-Server **nie direkt** an — alles läuft über `backend/api/routes/community.py` (Proxy + Aufbereitung).

> **Beachte:** Änderungen am Datenmodell müssen in **beiden** Repositories synchron angepasst werden:
> Schemas in `eedc-community/backend/schemas.py` und Aufbereitung in `eedc/backend/services/community_service.py`.
>
> **Der Server rechnet nichts nach** — er hat die Rohdaten nie gesehen. Die Monatswerte kommen seit S6 aus den Monats-Fakten (ADR-002/**P10**), und was ein Feld *bedeutet*, steht als Vertrag im Docstring von `MonatswertInput` (Community-Repo). Wer die Bedeutung ändert, ändert sie dort mit; eine Nachrechnung serverseitig gibt es nicht, Altbestand heilt beim nächsten Voll-Submit.

## Deprecated (nicht löschen!)

> Die alten `ha_sensor_*` Felder im Anlage-Model dürfen NICHT aus der DB/dem Model entfernt werden (bestehende Installationen). Neuer Code nutzt ausschließlich `sensor_mapping`.

## Letzte Änderungen

> **Versions-SoT = [CHANGELOG.md](CHANGELOG.md)** (vollständig, pro Release gepflegt). Dieser Digest ist eine kuratierte Auswahl und kann der Spitze hinterherhinken — `release.sh` bumpt ihn NICHT. Bei Diskrepanz gilt CHANGELOG/`config.py`. **Stand des Digests: v4.0.5** (fortgeschrieben 2026-07-31).

**v4.0.5** (2026-07-31) — Preise je Monat, CO₂ auf dem Eigenverbrauch, eine Zahl je Kennwert:

- **Ein Tarif-Wert trägt den Stichtag seines Monats (ADR-002/P8, gewächtert, Baseline 0):** sechzehn Fundstellen rechneten die Vergangenheit mit dem *heutigen* Tarif — eine Preiserhöhung schrieb die Historie um. Betroffen waren u. a. WP-/Speicher-Dashboard, Monatsbericht, Aussichten-Historie, HA-Export und `GET /monatsdaten/{id}` (dessen handgebaute Query zusätzlich `gueltig_bis` und den `verwendung`-Filter verlor). Dazu: Flex-Ø erreicht die Tagespfade (Σ Tage ≠ Monat war die Folge), „Gültig ab" wird beim ersten Tarif mit dem Inbetriebnahme-Datum vorbelegt, Daten-Checker meldet Monate ohne Tarif-Abdeckung. Auslöser Forum #89667/60 (Algie).
- **Vier Finanz-Sichten, eine Zahl:** USt auf Eigenverbrauch fehlte in PDF, HA-Sensor und den *bisherigen* Aussichten-Erträgen (→ ROI-Fortschritt); der **BKW-Eigenverbrauch** zählte je nach Sicht doppelt, gar nicht oder nur im ROI-Pfad → neuer SoT `core/berechnungen/bkw_finanz.py` (**ADR-002/P9**, Baseline 0). Symmetrie-Test `test_netto_ertrag_vier_wege_symmetrie.py` deckt beide Achsen.
- **Dienstwagen kostet, statt zu verdienen:** PV-Ladung wurde als eingesparter Netzbezug gutgeschrieben und nur die entgangene Einspeisung abgezogen — netto +22 ct/kWh für Strom, den das Haus nie verbraucht hat (196 € > 168 € ohne Auto). Neue Layer-Formel `dienstliche_ladekosten.py` für Cockpit · Aussichten · HA-Export (152 €); Komponenten-Hub zieht nach. **Energiebilanz unberührt.**
- **Eine CO₂-Definition (DI-2 vollendet):** Monatstabelle (Client) und Tagestabelle (Backend) rechneten weiter `Erzeugung × 0,38` — inkl. Einspeisung, ohne WP/E-Mob. Auswertungen → CO₂ liest jetzt `/cockpit/nachhaltigkeit`; Tages-Spalte heißt „CO₂-Einsparung (PV)" (Σ Tage ≠ Monat by design). Wächter `check:co2-roh`. Neu: Block **„CO₂-Bilanz"** in Cockpit → Jahr.
- **BKW-Akku hat einen Erfassungsweg statt zwei:** Kanon = eigene `speicher`-Investition mit BKW-Parent (Live, SoC, Energiefluss, Zählerpfad). Die BKW-eigenen Monatsfelder bleiben erfassbar (`nur_manuell`), aber nicht mehr zuordenbar; Parent-Regel-SoT `models/investition.py::ERLAUBTE_PARENT_TYPEN`, Setup-Wizard bietet den Parent erstmals an. MQTT-Fix: `eigenverbrauch_kwh` lag auf dem Erzeugungs-Kanal.
- **Monats-Fakten-Schicht (ADR-002/P10) ausgeliefert** — S1–S6, Wächter scharf, Restschuld 4. Sichtbare Folgen: Aussichten/PDF/ROI/Prognose-vs-IST/Langfrist/CO₂-Zeitreihe finden die PV bei Gesamtwert-Pflege wieder, HA-Sensoren tragen stillgelegte Komponenten, Community-Payload rechnet mit V2H/BHKW und ohne Dienstwagen. **Social-Media-Textvorlage zurückgebaut** (seit v4.0.0 unerreichbar; Community-Teilen unberührt).

**v4.0.2–v4.0.4** (2026-07-28/30) — Speicher rechnet mit der nutzbaren Kapazität · zugeordnete Sensoren wirken überall (#353 coolxmad) · Daten-Checker erklärt leere Sichten und stellt den Reparatur-Knopf daneben · Balkonkraftwerk in der Prognose (#347, Wechselrichter-Grenze stundenweise) · PV je String bleibt gemessen (Rest-Verteilung statt Alles-Verteilung).

**v4.0.1** (2026-07-26) — Prognose-Werte vereinheitlicht + gemessene PV-Modulwerte:

- **Ein Prognose-Kanon für alle Sichten:** 14-Tage-Balken, Stundenwerte, Kacheln „Morgen/Summe/Ø" und die OM-roh-Kurve rechnen jetzt **jede Ausrichtung getrennt** und mit der gelernten eedc-Korrektur — wie Prognosen-Vergleich und HA-Sensoren. Vorher standen für denselben Tag zwei Zahlen auf einer Seite (Rainer). Bei Mehrfach-Ausrichtung ändern sich die Werte sichtbar; GTI in der 14-Tage-Tabelle ist jetzt **kWp-gewichtet** („GTI Modulfläche").
- **PV-Modulwerte gemessen statt gerechnet:** der Hub-Block „Verlauf" zeigt die Pro-String-Messwerte; wo nur ein Gesamt-Sensor existiert, wird nach kWp verteilt **und gekennzeichnet** („geschätzt (kWp-Anteil)"), statt 0 anzuzeigen. Kein bester/schwächster String, solange verteilt wird.
- **PVGIS: überall die *aktive* Prognose** (P5) — inkl. DB-Invariante gegen „mehrere aktiv" nach Backup-Restore; Monatsbericht-SOLL war dort verdoppelt.
- **Unvollständige Antworten sagen es** (P4): Teil-Fan-out der Wetterabrufe wird ausgewiesen statt still zu niedrig geliefert.
- **Intern:** neue [ADR-002](docs/ADR-002-WURZELMUSTER.md) (sechs Invarianten P1–P6 + Wächter), Anschaffungsdatum ist Pflichtfeld.

**v4.0.0** (2026-07-25) — **IA-V4-Flip: die neue Oberfläche ist ausgeliefert** (Breaking Change, nur UI — Daten unberührt, alte Links werden umgeleitet):

- **Cockpit** (Wann? Live · Tag · Monat · Jahr · Aussicht) · **Komponenten** (Was? je Gerätetyp Status → Verlauf → Vergleich → Wirtschaftlichkeit) · **Auswertungen** (Wie? Finanzen · ROI · Prognose-vs-IST · CO₂ · Tabelle) · Einstellungen als Kachel-Übersicht. Blöcke sind verschiebbar, fokussierbar (⤢) und parkbar.
- **Monatsabschluss als ein Formular** (statt 7-Schritt-Wizard) · **Datenquellen als eine Fläche** (ein Feld = eine Quelle: HA-Sensor · MQTT · Connector; löst Sensor-Mapping- und MQTT-Wizard ab).
- **Drift-Inventur Tier-1 (DI/DI-2):** WP-CO₂, HA-Export-CO₂, Dienstwagen-Filter, §14a-WP-Tarif, Vorjahres-Nettoertrag — sichtbare Zahlenkorrekturen inkl. einmaligem LTS-Sprung beim CO₂-Sensor. Historische Tarife im PDF/HA-Export (#326).
- Der Rückweg bei Problemen ist v3.45.9; ein separates v3.46 gibt es bewusst nicht.

**v3.45.6–v3.45.9** (2026-06-27/29) — Prognose-Kanon „heute" · Speicher-Vorzeichen-Historie als Daten-Checker-Selbstkorrektur (**keine** Start-Migration) · Hotfix Add-on-Startschleife.

**v3.45.5** (2026-06-22) — Live-Tagesverlauf: Nadel-Spikes bei grobem Energie-Zähler weg (#680). Kurve rekonstruiert Leistung aus kWh-Zähler (`ΔkWh×12000`, 5-Min-Annahme); meldet der Zähler seltener, landet der ganze Zuwachs in EINEM Slot → 13-kW-Nadel. Fix: nur die **Kurvenform** fällt stundenweise auf den Live-Leistungssensor zurück (Phantom-Null-Detektor), Stunden-Energie = Zählersumme bleibt LTS-treu (Σ normiert). Intern (damals hinter `VITE_IA_V4` dormant, **ausgeliefert mit v4.0.0**): **IA-V4 A.3 Cockpit/Live** (IST-Layout in v4-Shell, kein Neubau; durchgängig Fokus/Vollbild via geteiltem `FokusVollbild`/`FokusKachel`, BlockShell auf dasselbe Overlay umgestellt) + Komponenten-Hub-Korrekturen.

**v3.45.4** (2026-06-22) — Sonstige Erzeuger (BHKW) in der Energiebilanz: ein Erzeuger unter „Sonstiges" (Kategorie *Erzeuger*) speist hinter den EINEN Hauszähler → seine Erzeugung zählt jetzt in EV/Autarkie in **allen** Bilanz-Pfaden (Monat + Vorjahr, Live, Tag/Energieprofil) via Layer-SoT `erzeugung_hinter_zaehler_kwh`. PV-Kennzahlen (spez. Ertrag/PR) bleiben rein; CO₂/Wirtschaftlichkeit eines Brennstoff-Erzeugers bewusst „nicht bewertet". Lehre: Bilanz-Drift saß in drei getrennten Pfaden — Symptom-Patch hätte nur den Monat erwischt.

> **v3.30–v3.44:** Detail nur noch im [CHANGELOG](CHANGELOG.md) (Digest hier seit v3.29.2 nicht fortgeschrieben).

**v3.29.x** (2026-05-13/14) — Aggregations-Hardening + UX-Bündel vor Menüstruktur-Konzept:

- **Anschaffungs-/Stilllegungsdatum-Filter durchgängig (v3.29.0/v3.29.1, #236 #239):** alle Read-Sites (Cockpit, Energieprofil, HA-Stats-Aggregation, Monatsbericht-Sektionen) respektieren jetzt `inv.installationsdatum`/`stilllegungsdatum`. Folgewelle nach #236 zeigte: Filter auf einer Schicht reicht nicht bei parallelen Pfaden.
- **SoT-Helper `get_inv_value` für `leistung_kwp` (#229):** PV-String-Verteilung liest jetzt Spalten-Wert mit Fallback auf `parameter`-JSON statt Gleichverteilung.
- **UX-Cluster #233 (P13–P18):** chirurgische Fixes Display-Token `'—'`, kWh-Einheiten im WP-Dashboard (#237), Daten-Checker Inbetriebnahme-Monat ausgeschlossen (#240), Sparkline-Tooltip mit Monatsname (#241).
- **eedc-Schreibweise (v3.29.2):** ~130 Treffer in Code + Hilfe-Docs auf Wort „eedc" vereinheitlicht; `\bEEDC\b`-Wortgrenze schützt Identifier wie `EEDC_Prognose` automatisch.

**v3.28.0** (2026-05-13) — Reparatur-Werkbank: Mehrere Tage neu aggregieren (#230).

**v3.27.x** (2026-05-10/12) — Etappe 3d + Tester-Päckchen:

- **Etappe 3d Daten-Provenance & Reparatur-Werkbank (v3.27.0):** Anomalie-Erkennung mit punktuellem Reparatur-Pfad; bewusst KEIN globaler Heiler-Knopf.
- **UX-Sprint A1+A2+A3 + Power-Sensor-Bug (v3.27.1, #200):** Wizard + Live-Heute + Stats-API ziehen jetzt `_is_energy_sensor` konsistent durch (kW darf nicht in kWh-Slot).
- **WP-Aggregation: Split-Strommessung + Counter-Spike-Cap (v3.27.4, #230):** MartyBr-Bug-Report mit Screenshot als Vorlage.
- **UX-Cluster detLAN (v3.27.5, #207 #215 #217 #218 #494) + Folge-Päckchen Tester-Bugs (v3.27.3, #220 #222 #226 #227 #228).**

**v3.26.x** (2026-05-06/09) — Korrekturprofil + HA-Energy-Import + Etappe 3c:

- **EEDC-Korrekturprofil O1+O2 (v3.26.0–v3.26.2):** Päckchen 1 (Recency) + Päckchen 2 (Sonnenstand × Wetter live) parallel zum Legacy-Skalar als Diagnose. Live-Pfad-Switch wird in Prognosequellen-Wahl Schritt 2 mitgemacht.
- **HA-Energiekonfiguration importieren (v3.26.5, #197):** Setup-Vereinfachung Olli0103 — Energy-Dashboard-Konfig aus HA wird im Setup-Wizard übernommen.
- **Etappe 3c Energieprofil Read-/Write-Architektur konsolidiert (v3.26.8):** zentraler SoT-Helper statt Drift-Patches; siehe `docs/archive/KONZEPT-DATENPIPELINE.md`.
- **Reload-Vorschau Counter-Boundary + „Nur neu rechnen" (v3.26.6):** Vorschau heilt sich selbst.

**v3.25.x** (2026-04-29/05-05) — Live-Snapshot 5-Min + Investitions-Parameter-SoT:

- **Live-Snapshot 5-Min Backend (v3.25.3–v3.25.6):** Phase 1 Backend für Live-Tagesverlauf-Service ausgeliefert + validiert (Off-by-one-Fix state→sum). Frontend-Umstellung noch offen.
- **Investitions-Parameter Single Source of Truth (v3.25.0):** `lib/investitionParameter.ts` + `core/investition_parameter.py` als gemeinsame Konstanten-Map; DB-Migration `_migrate_investitionen_parameter_keys_v325` korrigiert 7 Drift-Bugs (V2H, Jahresfahrleistung, PV-Ladeanteil, Vergleichsverbrauch, Speicher-Arbitrage, Wallbox-Leistung, WP-Preis-Default).
- **Pool-Bug Quick-Fix Wallbox+E-Auto (v3.25.11):** Drift-Konsistenz zwischen `cockpit/uebersicht.py` und `aktueller_monat._aggregate` angeglichen.

**v3.24.x** (2026-04-27/29) — WP-Kompressor-Starts + In-App-Hilfe + Sensor-LTS:

- **WP-Kompressor-Starts (v3.24.0, #136):** optionaler Total-Increasing-Sensor pro WP, neue `KUMULATIVE_COUNTER_FELDER`-Architektur trennt Counter strikt von kWh-Feldern. KPI-Kacheln in Monatsbericht + WP-Dashboard (v3.24.4, #169).
- **Sensor-Filter aufgeweicht + „ohne Statistik"-Badge (v3.24.1, #136 Folge):** Nibe-Roh-Counter ohne `state_class` jetzt auswählbar, Frontend-Fallback-Link, Daten-Checker-Kategorie SENSOR_MAPPING_LTS — siehe `feedback_ha_lts_keine_zeitmaschine.md`.
- **In-App-Hilfe als pflegbares Werk (v3.24.2):** Sweep aller acht Hilfe-Dokumente (BENUTZERHANDBUCH, HANDBUCH_INSTALLATION/BEDIENUNG/EINSTELLUNGEN/INFOTHEK, BERECHNUNGEN, SENSOR-REFERENZ, GLOSSAR) auf v3.24-Stand. Sidebar-Eintrag „Was ist neu" (v3.24.5, Discussion #130 Folge Safi105).
- **PV-Cockpit: Speicher-Kapazität + WR-Eigenleistung sichtbar (v3.24.4/v3.24.6, #172 detLAN):** Key-Drift `batteriekapazitaet_kwh` vs. `kapazitaet_kwh` korrigiert, Orphan-Speicher-Block ergänzt.

**v3.23.x** (2026-04-25/27) — MAE/MBE + MQTT-Daten-Checker + Mobile-Hardening:

- **MAE + Bias trennen im Genauigkeits-Tracking (v3.22.0/v3.23.x, #151):** drei Quellen (OpenMeteo/EEDC/Solcast), Bias neutral gefärbt, Spaltenstruktur stabil auch ohne Lernfaktor.
- **MQTT-Topic-Abdeckung im Daten-Checker (v3.23.7, #134):** Drift zwischen dynamischer Konsumenten-Seite und statischer Publisher-Seite wird sichtbar; bei nicht aktivem Subscriber stillschweigend übersprungen (v3.23.8 detLAN/rapahl).
- **Klickbarer Reparatur-Popover bei IST-Lücke (v3.23.0, #147):** Button „Tag neu berechnen" + Fallback-Link Sensor-Mapping. Restart-Recovery für verpasste :05/:55-Snapshot-Jobs.
- **iOS Safari `h-dvh` + COP→JAZ-Harmonisierung (v3.23.6/v3.23.4, #161/#167):** siehe `feedback_ios_companion_app.md` und Wizard-Sweep für Key-Drift (`batterie_kwh`→`batteriekapazitaet_kwh` u. a.).

**v3.19.0–v3.22.0** (2026-04-22/25) — Architekturwechsel + Slot-Konvention + WP-Gaspreis:

- **kWh aus Zähler-Snapshots statt Leistungs-Integration (v3.19.0, #135):** kritischer Architekturwechsel — stündliche `sensor_snapshots`-Tabelle, Self-Healing, ±5–15 % Drift weg.
- **Performance Ratio nutzt GTI statt GHI (v3.20.0, #139):** physikalisch unmögliche PR-Werte >1.2 im Winter korrigiert.
- **Slot-Konvention auf Backward vereinheitlicht (v3.20.0, #144):** OpenMeteo/Solcast/IST jetzt alle Slot N = Energie [N-1, N), Industriestandard.
- **WP-Alternativvergleich + Monats-Gaspreis (v3.21.0, #141) + aufklappbare Energieprofil-Sektionen (#148).**

**v3.17.0–v3.18.0** (2026-04-21) — Dynamische Benzinpreise + Energieprofil-Tab:

- **Dynamische Benzinpreise aus EU Weekly Oil Bulletin (v3.17.0):** echte monatliche Kraftstoffpreise statt statischem Parameter, History seit 2005.
- **Energieprofil-Tab + anlage-spezifische Datenverwaltung (v3.18.0, #133):** Tages-Tabelle mit Spalten-Selektor, Pro-Tag-Reaggregation, Vollbackfill aus HA-Statistik.

**v3.16.x** (April 2026) — Solcast PV Forecast (v3.16.4): Prognosen-Vergleich-Tab (OpenMeteo / EEDC kalibriert / Solcast / IST); Sensor-Mapping Strompreis (Tibber/aWATTar/EPEX), Stündliche Strompreis-Mitschrift; Infothek Etappe 3.6 (v3.16.2).

**Ältere Meilensteine:** PDF-Dokumente + Infothek N:M (v3.15), Stilllegungsdatum (v3.14), Monatsberichte + Energieprofil Etappe 3 (v3.12/3.13), Import-Strategie (v3.10), Live Dashboard Generalüberholung (v3.9), L2-Cache (v3.7), Infothek (v3.5), Wettermodell-Kaskade (v3.4), GTI-Prognose (v3.3), Live Dashboard + MQTT-Inbound (v3.0).

Für Details siehe [CHANGELOG.md](CHANGELOG.md) und [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Roadmap & offene Punkte

Single Source of Truth: **GitHub Issue [#110 — Roadmap Anfrage](https://github.com/supernova1963/eedc-homeassistant/issues/110)**.

Aktuellen Stand bei Bedarf abrufen via `gh issue view 110 --repo supernova1963/eedc-homeassistant`.
