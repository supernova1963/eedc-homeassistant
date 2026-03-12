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
./scripts/release.sh 2.8.6
```

Das Script:

1. Prüft ob beide Repos clean sind und auf `main`
2. Bumpt Version in allen 4 Dateien (`config.py`, `version.ts`, `config.yaml`, `run.sh`)
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

## Verboten

- Direkt im `eedc`-Repo Code ändern
- `git subtree pull/push` (wird nicht mehr verwendet)
- `git pull --rebase` in eedc-homeassistant
- CHANGELOG in `eedc/CHANGELOG.md` direkt editieren
