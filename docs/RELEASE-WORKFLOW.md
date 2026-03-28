# Release-Workflow

## Übersicht

```
eedc-homeassistant (Source of Truth)
├── eedc/backend/          ─── release.sh ───→  eedc (Standalone-Spiegel)
├── eedc/frontend/         ─── release.sh ───→  eedc (Standalone-Spiegel)
├── website/
├── docs/
└── CHANGELOG.md

eedc-community (unabhängig)
```

**Eine Regel:** Alle Änderungen in `eedc-homeassistant` machen. Nie direkt in `eedc`.

## Alltag: Code ändern

1. Änderung in `eedc-homeassistant` machen (backend, frontend, docs, HA-Config)
2. Committen
3. Wenn die Änderung beim User ankommen soll → Release erstellen (siehe unten)

## Release erstellen

Ein Befehl macht alles:

```bash
cd /home/gernot/claude/eedc-homeassistant
./scripts/release.sh 3.2.0
```

Das Script:

1. Prüft ob beide Repos clean sind und auf `main`
2. Bumpt Version in allen 5 Dateien (`config.py`, `version.ts`, `config.yaml`, `run.sh`, `Dockerfile`)
3. Kopiert CHANGELOG nach `eedc/`
4. Committed + taggt + pusht `eedc-homeassistant`
5. Synchronisiert `backend/` + `frontend/` + shared Files nach `eedc`-Standalone
6. Committed + taggt + pusht `eedc`

Ergebnis: Beide Repos auf gleicher Version, getaggt, gepusht.

## Externe PRs

Wenn jemand einen PR gegen `eedc-homeassistant` stellt:

- PR reviewen
- Wenn er Code im `eedc/`-Verzeichnis ändert: Änderung selbst in `eedc-homeassistant` übernehmen
- PR mit Danke-Kommentar schließen
- Beim nächsten Release wird `eedc` automatisch synchronisiert

Wenn jemand einen PR gegen `eedc` stellt:

- Änderung in `eedc-homeassistant/eedc/` übernehmen (nicht direkt mergen!)
- PR schließen mit Hinweis dass `eedc` ein Spiegel ist

## Was wo geändert werden darf

| Bereich | Wo ändern |
| --- | --- |
| Backend-Code (`backend/`) | `eedc-homeassistant/eedc/backend/` |
| Frontend-Code (`frontend/`) | `eedc-homeassistant/eedc/frontend/` |
| HA-Config (`config.yaml`, `run.sh`, `Dockerfile`) | `eedc-homeassistant/eedc/` |
| CHANGELOG | `eedc-homeassistant/CHANGELOG.md` (Root) |
| Dokumentation | `eedc-homeassistant/docs/` |
| Website | `eedc-homeassistant/website/` |
| Standalone-Dockerfile | `eedc/Dockerfile` (einzige Ausnahme, lebt nur dort) |

## Dokumentation → Website synchronisieren

Die Website-Seiten in `website/src/content/docs/` sind **keine automatisch generierten Kopien** von `docs/` — sie müssen manuell aktuell gehalten werden. Jede Datei hat einen Astro-Frontmatter-Header (4 Zeilen), danach folgt der Inhalt aus `docs/`.

Beim Ändern einer Doku-Datei immer auch die korrespondierende Website-Datei aktualisieren:

| `docs/` | `website/src/content/docs/` |
| --- | --- |
| `BENUTZERHANDBUCH.md` | `benutzerhandbuch.md` |
| `HANDBUCH_INSTALLATION.md` | `handbuch-installation.md` |
| `HANDBUCH_BEDIENUNG.md` | `handbuch-bedienung.md` |
| `HANDBUCH_EINSTELLUNGEN.md` | `handbuch-einstellungen.md` |
| `HANDBUCH_INFOTHEK.md` | `handbuch-infothek.md` |
| `GLOSSAR.md` | `glossar.md` |
| `ARCHITEKTUR.md` | `architektur.md` |
| `BERECHNUNGEN.md` | `berechnungen.md` |
| `DEVELOPMENT.md` | `entwicklung.md` |
| `SETUP_DEVMACHINE.md` | `setup-devmachine.md` |

Neue Seiten auch in `website/astro.config.mjs` in die Sidebar eintragen.

## Verboten

- Direkt im `eedc`-Repo Code ändern
- `git subtree pull/push` (wird nicht mehr verwendet)
- `git pull --rebase` in eedc-homeassistant
- CHANGELOG in `eedc/CHANGELOG.md` direkt editieren
