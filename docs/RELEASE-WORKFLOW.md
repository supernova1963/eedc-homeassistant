# Release-Workflow: EEDC Repo-Synchronisation

## Übersicht

EEDC besteht aus drei Repositories mit einer klaren Hierarchie:

```
eedc (Source of Truth)          eedc-homeassistant              eedc-community
├── backend/    ──subtree──→    ├── eedc/                       (unabhängig)
├── frontend/   ──subtree──→    │   ├── backend/
└── (kein HA)                   │   ├── frontend/
                                │   ├── config.yaml  ← HA-only
                                │   ├── run.sh       ← HA-only
                                │   └── Dockerfile   ← HA-only
                                ├── website/
                                ├── docs/
                                └── CHANGELOG.md     ← Master-CHANGELOG
```

**Kernregel:** Code-Änderungen immer zuerst in `eedc`, dann per Subtree Pull nach `eedc-homeassistant` synchronisieren. Nie andersherum.

---

## Drei Szenarien

### Szenario A: Bugfix / Feature (ohne Release)

Wenn du nur Code änderst, aber (noch) kein Release machst:

```
┌─────────────────────────────────────────────────┐
│ 1. Code in eedc ändern + committen              │
│ 2. User: git push (manuell, mit Hook-Bestät.)   │
│ 3. cd eedc-homeassistant                        │
│ 4. git subtree pull --prefix=eedc               │
│    https://github.com/supernova1963/eedc.git    │
│    main --squash                                │
│ 5. Konflikte lösen falls nötig                  │
│ 6. User: git push (manuell)                     │
└─────────────────────────────────────────────────┘
```

**WICHTIG:** Kein Versions-Bump, kein Tag. Nur Code-Sync.

### Szenario B: Release (mit Version + Tag)

Wenn ein neues Release erstellt werden soll:

```
┌─────────────────────────────────────────────────┐
│ Schritt 1: eedc (Source of Truth)               │
│                                                 │
│   cd /home/gernot/claude/eedc                   │
│   ./scripts/release.sh 2.8.6                    │
│   → Bumpt config.py + version.ts                │
│   → Committed + taggt                           │
│   → Zeigt nächste Schritte an                   │
│                                                 │
│   git push && git push origin v2.8.6  ← MANUELL│
├─────────────────────────────────────────────────┤
│ Schritt 2: eedc-homeassistant                   │
│                                                 │
│   cd /home/gernot/claude/eedc-homeassistant     │
│   ./scripts/sync-and-release.sh 2.8.6           │
│   → Subtree Pull (löst Konflikte automatisch)   │
│   → Bumpt config.yaml + run.sh                  │
│   → Kopiert CHANGELOG                           │
│   → Committed + taggt                           │
│   → Prüft alle 4 Versionsdateien                │
│                                                 │
│   git push && git push origin v2.8.6  ← MANUELL│
├─────────────────────────────────────────────────┤
│ Schritt 3: GitHub Release (optional)            │
│                                                 │
│   gh release create v2.8.6 \                    │
│     --repo supernova1963/eedc \                 │
│     --title "v2.8.6" --generate-notes           │
│   gh release create v2.8.6 \                    │
│     --repo supernova1963/eedc-homeassistant \   │
│     --title "v2.8.6" --generate-notes           │
└─────────────────────────────────────────────────┘
```

### Szenario C: Externe PRs (wie PLZ-Tabelle PR #24)

Wenn jemand einen PR gegen `eedc-homeassistant` stellt, der Code im `eedc/`-Subtree ändert:

```
┌─────────────────────────────────────────────────┐
│ 1. PR reviewen (Code OK?)                       │
│ 2. Änderung NICHT direkt mergen!                │
│    → Subtree-Änderungen würden beim nächsten    │
│      Subtree Pull überschrieben                 │
│ 3. Stattdessen: Änderung in eedc übernehmen    │
│ 4. eedc pushen                                  │
│ 5. Subtree Pull in eedc-homeassistant           │
│ 6. PR mit Danke-Kommentar schließen             │
└─────────────────────────────────────────────────┘
```

---

## Was wo geändert werden darf

| Dateien / Bereich | Wo ändern? | Warum? |
|---|---|---|
| `backend/**`, `frontend/**` | **eedc** (dann Subtree Pull) | Source of Truth für Code |
| `config.yaml`, `run.sh`, `Dockerfile` | **eedc-homeassistant** direkt | HA-spezifisch, nicht im Subtree |
| `CHANGELOG.md` | **eedc-homeassistant** Root | Master-Copy, wird nach `eedc/` kopiert |
| `website/**`, `docs/**` | **eedc-homeassistant** direkt | Nur dort vorhanden |
| `repository.yaml` | **eedc-homeassistant** direkt | HA Add-on Store Konfiguration |

---

## Versionsdateien (4 Stück, müssen synchron sein!)

| Datei | Repo | Wer bumpt? |
|---|---|---|
| `backend/core/config.py` | eedc | `release.sh` |
| `frontend/src/config/version.ts` | eedc | `release.sh` |
| `config.yaml` | eedc-homeassistant | `sync-and-release.sh` |
| `run.sh` | eedc-homeassistant | `sync-and-release.sh` |

---

## Verboten (ohne explizite Aufforderung!)

- **`git push`** aus Claude Code heraus — immer manuell im Terminal
- **`git subtree push`** — würde HA-Dateien ins Standalone-Repo pushen
- **PRs direkt mergen** die `eedc/`-Subtree-Dateien ändern
- **Versionsnummern manuell ändern** — immer über die Scripts
- **CHANGELOG in `eedc/` direkt editieren** — nur Root-Copy editieren

---

## Fehlerbehebung

### Subtree Pull hat Konflikte

Das Script `sync-and-release.sh` löst bekannte Konflikte automatisch:
- `config.py`, `version.ts` → nimmt upstream (eedc)
- `config.yaml`, `run.sh` → behält HA-Version
- `CHANGELOG.md` → nimmt upstream, wird danach vom Root überschrieben

Bei unbekannten Konflikten stoppt das Script und zeigt die Datei an.

### Push wird vom Hook abgelehnt

Der pre-push Hook erwartet interaktive Bestätigung (Enter drücken innerhalb von 30 Sekunden). Funktioniert nur im Terminal, nicht aus Claude Code.

### Tag existiert bereits

Wenn ein Tag schon existiert, lehnt das Script ab. Tag vorher löschen:
```bash
git tag -d v2.8.6                    # lokal
git push origin :refs/tags/v2.8.6    # remote
```

### "non-fast-forward" beim Push

Remote hat Commits die lokal fehlen. Erst pullen:
```bash
git pull --no-rebase
# Dann erneut pushen
```
**Nicht** `git pull --rebase` verwenden — Subtree-Commits vertragen sich nicht mit Rebase!
