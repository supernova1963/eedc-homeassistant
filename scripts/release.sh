#!/bin/bash
# =============================================================================
# release.sh – EEDC Release: Version bump + Sync zu eedc-Standalone + Push
#
# Verwendung:
#   cd /home/gernot/claude/eedc-homeassistant
#   ./scripts/release.sh 2.8.6
#
# Was passiert:
#   1. Prüft Voraussetzungen (clean, main-Branch, kein Konfliktmarker)
#   2. Bumpt Version in allen 5 Dateien (eedc-homeassistant)
#   3. Kopiert CHANGELOG nach eedc/
#   4. Committed + taggt eedc-homeassistant
#   5. Pusht eedc-homeassistant
#   6. Synchronisiert shared Code nach eedc-Standalone-Repo
#   7. Committed + taggt + pusht eedc
#   8. Wartet, bis das Add-on-Image in ghcr.io liegt (scripts/warte-auf-image.sh)
#
# Ergebnis: Beide Repos auf gleicher Version, getaggt, gepusht — UND das Image
#           ist nachweislich ausgeliefert. Ein grüner Push allein ist kein
#           ausgeliefertes Add-on (Nebenfund N-169): `eedc/config.yaml` zieht ein
#           vorgebautes ghcr-Image, das ein Workflow erst NACH dem Tag baut.
#
# =============================================================================

set -euo pipefail

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

EEDC_STANDALONE="/home/gernot/claude/eedc"

# --- Argumente prüfen ---
if [ $# -ne 1 ]; then
    echo -e "${RED}Verwendung: $0 <version>${NC}"
    echo "  Beispiel: $0 2.8.6"
    exit 1
fi

VERSION="$1"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Ungültiges Versionsformat: $VERSION${NC}"
    echo "  Erwartet: X.Y.Z (z.B. 2.8.6)"
    exit 1
fi

# --- Voraussetzungen prüfen ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

echo -e "${BOLD}=== EEDC Release v$VERSION ===${NC}"
echo ""

# Richtiges Repo?
if [ ! -f "eedc/config.yaml" ]; then
    echo -e "${RED}Fehler: Muss im eedc-homeassistant-Repo ausgeführt werden!${NC}"
    exit 1
fi

# Schritt 7 braucht das Warte-Script. Die Prüfung steht bewusst HIER und nicht
# erst unten: fehlt es, will man das vor dem Tag-Push wissen — danach wäre das
# Release draußen und die Auslieferung ungeprüft, also genau die Lage aus N-169.
if [ ! -x "$SCRIPT_DIR/warte-auf-image.sh" ]; then
    echo -e "${RED}Fehler: scripts/warte-auf-image.sh fehlt oder ist nicht ausführbar.${NC}"
    echo -e "${YELLOW}  Schritt 7 (Auslieferung abwarten) hängt daran. chmod +x nicht vergessen.${NC}"
    exit 1
fi

# Working Directory clean? — inklusive UNTRACKED.
#
# `git diff` sieht getrackte Änderungen, `git diff --cached` den Index —
# eine neue, noch nie hinzugefügte Datei sieht keiner von beiden. In diesem
# Projekt laufen regelmäßig Parallel-Sessions; eine Scratch-Datei daneben
# würde sonst die ganze Laufzeit über unbemerkt bleiben und beim Commit
# unten mitfahren (Nebenfund N-56). `git status --porcelain` respektiert
# .gitignore, gitignorierte Arbeitsstände (venv/, node_modules/,
# docs/drafts/, data/*.db) lösen also weiterhin nichts aus.
pruefe_baum_sauber() {
    local repo="$1"
    local name="$2"
    local dreckig
    dreckig=$(git -C "$repo" status --porcelain)
    if [ -n "$dreckig" ]; then
        echo -e "${RED}Fehler: $name Working Directory ist nicht clean!${NC}"
        echo "$dreckig"
        echo -e "${YELLOW}  Auch untracked Dateien (Spalte '??') zählen — sie würden im${NC}"
        echo -e "${YELLOW}  Release-Commit landen. Committen, löschen oder ignorieren.${NC}"
        exit 1
    fi
}

pruefe_baum_sauber "$REPO_DIR" "eedc-homeassistant"
pruefe_baum_sauber "$EEDC_STANDALONE" "eedc"

# Sicherung gegen eine UNVOLLSTÄNDIGE Pfadliste (Schritt 4 + 6 stagen explizit
# statt `git add -A`). Eine still fehlende Datei im Release wäre schlimmer als
# eine zuviel eingekehrte — sie fällt erst beim Nutzer auf. Deshalb: nach dem
# Stagen darf nichts mehr offen sein. Bleibt etwas übrig, hat entweder das
# Script etwas Neues erzeugt (→ gehört in die Pfadliste) oder eine
# Parallel-Session hat danebengeschrieben. Beides bricht laut ab.
pruefe_nichts_uebrig() {
    local repo="$1"
    local name="$2"
    local rest
    rest=$( { git -C "$repo" diff --name-only; \
              git -C "$repo" ls-files --others --exclude-standard; } | sort -u )
    if [ -n "$rest" ]; then
        echo -e "${RED}ABBRUCH: in $name sind nach dem Stagen Dateien offen geblieben:${NC}"
        echo "$rest" | sed 's/^/    /'
        echo -e "${YELLOW}  Entweder erzeugt das Release eine Datei, die die Pfadliste noch${NC}"
        echo -e "${YELLOW}  nicht kennt (dann Liste in release.sh ergänzen), oder eine andere${NC}"
        echo -e "${YELLOW}  Session hat in den Baum geschrieben. Der Version-Bump liegt bereits${NC}"
        echo -e "${YELLOW}  gestaged vor — nach dem Aufräumen erneut starten.${NC}"
        exit 1
    fi
}

# Auf main?
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo -e "${RED}Fehler: eedc-homeassistant nicht auf main! (aktuell: $BRANCH)${NC}"
    exit 1
fi

BRANCH_STANDALONE=$(git -C "$EEDC_STANDALONE" branch --show-current)
if [ "$BRANCH_STANDALONE" != "main" ]; then
    echo -e "${RED}Fehler: eedc nicht auf main! (aktuell: $BRANCH_STANDALONE)${NC}"
    exit 1
fi

# Tag existiert schon?
if git tag -l "v$VERSION" | grep -q .; then
    echo -e "${RED}Fehler: Tag v$VERSION existiert bereits in eedc-homeassistant!${NC}"
    exit 1
fi
if git -C "$EEDC_STANDALONE" tag -l "v$VERSION" | grep -q .; then
    echo -e "${RED}Fehler: Tag v$VERSION existiert bereits in eedc!${NC}"
    exit 1
fi

# Neue Version höher als alle existierenden Tags?
LATEST_TAG=$(git tag --list 'v*' --sort=-version:refname | head -1 | sed 's/^v//')
if [ -n "$LATEST_TAG" ]; then
    # Versions-Vergleich via sort -V
    HIGHER=$(printf '%s\n%s\n' "$LATEST_TAG" "$VERSION" | sort -V | tail -1)
    if [ "$HIGHER" != "$VERSION" ]; then
        echo -e "${RED}Fehler: Neue Version v$VERSION ist nicht höher als aktuellster Tag v$LATEST_TAG!${NC}"
        echo -e "  Bitte eine höhere Versionsnummer wählen."
        exit 1
    fi
fi

# CHANGELOG-Eintrag vorhanden?
if ! grep -q "## \[$VERSION\]" CHANGELOG.md 2>/dev/null; then
    echo -e "${RED}Fehler: Kein CHANGELOG-Eintrag für Version $VERSION gefunden!${NC}"
    echo "  Bitte erst ## [$VERSION] in CHANGELOG.md ergänzen."
    exit 1
fi

# WAS-IST-NEU.md: Major.Minor-Sektion vorhanden? (Soft-Check, keine Blockade)
# Bei reinen Bugfix-Releases ohne anwender-sichtbare Änderungen ist das OK,
# aber der Maintainer soll bewusst entscheiden statt es zu vergessen.
MAJOR_MINOR=$(echo "$VERSION" | cut -d. -f1,2)
if ! grep -qE "^## v${MAJOR_MINOR}[. ]" docs/WAS-IST-NEU.md 2>/dev/null; then
    echo -e "${YELLOW}Warnung: Keine v${MAJOR_MINOR}-Sektion in docs/WAS-IST-NEU.md gefunden.${NC}"
    echo -e "${YELLOW}  Wenn dieses Release anwender-sichtbare Änderungen enthält, bitte vorher${NC}"
    echo -e "${YELLOW}  einen ## v${MAJOR_MINOR}.x-Block oben in der Datei ergänzen — die Page wird beim${NC}"
    echo -e "${YELLOW}  Frontend-Build automatisch synchronisiert. Bei reinem Bugfix kann ignoriert werden.${NC}"
    read -r -p "  Trotzdem fortfahren? [y/N] " RESP
    if [ "$RESP" != "y" ] && [ "$RESP" != "Y" ]; then
        echo -e "${RED}Release abgebrochen.${NC}"
        exit 1
    fi
fi

# Smoke-Check: App-Boot + 31 Akzeptanz-Tests grün?
# Läuft VOR Version-Bump, damit ein roter Test nichts an den Versionsdateien
# anfasst. Bei Fehler hartes Abbrechen — kein Skip-Override.
echo ""
echo -e "${CYAN}Pre-Release-Smoke-Check...${NC}"
if ! "$REPO_DIR/scripts/smoke.sh" >/dev/null 2>&1; then
    echo -e "${RED}Fehler: Smoke-Check fehlgeschlagen.${NC}"
    echo -e "${YELLOW}  Detail: $REPO_DIR/scripts/smoke.sh ausführen.${NC}"
    exit 1
fi
echo -e "${GREEN}  Smoke OK.${NC}"

# Aktuelle Version lesen
CURRENT=$(grep -oP '(?<=APP_VERSION = ")[^"]*' eedc/backend/core/config.py)
echo -e "  Aktuell:  ${YELLOW}$CURRENT${NC}"
echo -e "  Neu:      ${GREEN}$VERSION${NC}"
echo ""

# =============================================================================
# SCHRITT 1: Version bumpen in eedc-homeassistant (alle 5 Dateien)
# =============================================================================
echo -e "${CYAN}[1/7] Version bumpen in eedc-homeassistant...${NC}"

sed -i "s/^APP_VERSION = \".*\"/APP_VERSION = \"$VERSION\"/" eedc/backend/core/config.py
echo "  eedc/backend/core/config.py         → $VERSION"

sed -i "s/^export const APP_VERSION = '.*'/export const APP_VERSION = '$VERSION'/" eedc/frontend/src/config/version.ts
echo "  eedc/frontend/src/config/version.ts  → $VERSION"

sed -i "s/^version: \".*\"/version: \"$VERSION\"/" eedc/config.yaml
echo "  eedc/config.yaml                    → $VERSION"

sed -i "s/Version: [0-9][0-9.]*/Version: $VERSION/" eedc/run.sh
echo "  eedc/run.sh                         → $VERSION"

sed -i "s/io.hass.version=\"[^\"]*\"/io.hass.version=\"$VERSION\"/" eedc/Dockerfile
echo "  eedc/Dockerfile (Label)             → $VERSION"

# =============================================================================
# SCHRITT 2: Frontend Build (damit dist/ die neue Version enthält)
# =============================================================================
echo ""
echo -e "${CYAN}[2/7] Frontend Build...${NC}"

# In-App-Hilfe-Inhalte aus docs/ refreshen, damit dist/ aktuell ist
"$REPO_DIR/scripts/sync-help.sh"

cd eedc/frontend
if [ ! -d "node_modules" ]; then
    echo "  npm ci..."
    npm ci --silent
fi
echo "  npm run build..."
npm run build --silent
echo -e "  ${GREEN}Frontend Build erfolgreich${NC}"
cd "$REPO_DIR"

# =============================================================================
# SCHRITT 3: CHANGELOG + README synchronisieren (Root → eedc/)
# =============================================================================
echo ""
echo -e "${CYAN}[3/7] CHANGELOG + README synchronisieren...${NC}"

if [ -f "CHANGELOG.md" ]; then
    cp CHANGELOG.md eedc/CHANGELOG.md
    echo "  CHANGELOG.md → eedc/CHANGELOG.md"
else
    echo -e "${YELLOW}  Kein Root-CHANGELOG.md gefunden, überspringe.${NC}"
fi

# Root-README ist die in HA (App-Info-Tab) gerenderte README → bei jedem Release angleichen.
# Die Standalone-Variante mit LAN-Security-Hinweis liegt separat in eedc/README.standalone.md
# und geht weiter unten in den Standalone-Mirror (siehe SCHRITT 5).
if [ -f "README.md" ]; then
    cp README.md eedc/README.md
    echo "  README.md → eedc/README.md (HA-App-Info-Tab)"
else
    echo -e "${YELLOW}  Kein Root-README.md gefunden, überspringe.${NC}"
fi

# Konfliktmarker-Check
if grep -rn "<<<<<<" eedc/ --include="*.py" --include="*.ts" --include="*.md" --include="*.yaml" --include="*.sh" 2>/dev/null | grep -v node_modules; then
    echo -e "${RED}ABBRUCH: Konfliktmarker gefunden!${NC}"
    exit 1
fi

# =============================================================================
# SCHRITT 4: Commit + Tag + Push eedc-homeassistant
# =============================================================================
echo ""
echo -e "${CYAN}[4/7] Commit + Tag + Push eedc-homeassistant...${NC}"

# Nur einkehren, was dieses Script oben selbst geschrieben hat — kein `git add -A`.
# Erhebung der Schreibstellen (Stand 2026-08-03, Nebenfund N-56):
#   Schritt 1 → die 5 Versionsdateien
#   Schritt 2 → sync-help.sh nach eedc/frontend/public/help/, vite build nach
#               eedc/frontend/dist/ (tsc läuft mit noEmit, schreibt nichts)
#   Schritt 3 → eedc/CHANGELOG.md, eedc/README.md
# smoke.sh (Schritt 0) legt nur außerhalb des Baums bzw. gitignoriert ab.
# Wer hier eine Schreibstelle ergänzt, ergänzt auch diese Liste — sonst
# schlägt pruefe_nichts_uebrig unten an.
RELEASE_PFADE=(
    eedc/backend/core/config.py
    eedc/frontend/src/config/version.ts
    eedc/config.yaml
    eedc/run.sh
    eedc/Dockerfile
    eedc/CHANGELOG.md
    eedc/README.md
    eedc/frontend/public/help
    eedc/frontend/dist
)
git add -A -- "${RELEASE_PFADE[@]}"
pruefe_nichts_uebrig "$REPO_DIR" "eedc-homeassistant"

if git diff --cached --quiet; then
    echo -e "${YELLOW}  Keine Änderungen (Version war bereits $VERSION).${NC}"
else
    git commit -m "release: v$VERSION"
fi
git tag -a "v$VERSION" -m "Version $VERSION"
git push && git push origin "v$VERSION"
echo -e "${GREEN}  eedc-homeassistant v$VERSION gepusht.${NC}"

# =============================================================================
# SCHRITT 5: Sync shared Code → eedc-Standalone
# =============================================================================
echo ""
echo -e "${CYAN}[5/7] Sync nach eedc-Standalone...${NC}"

# eedc-Mirror VOR dem Sync auf origin-Stand bringen. Der Mirror ist ein
# reiner Spiegel (nur release.sh schreibt). Ein lokal veralteter Stand
# (Cross-Machine: ein Release vom anderen Rechner wurde hier nie gepullt)
# oder ein durch einen früheren Fehl-Release divergierter Stand würde sonst
# auf falscher Basis committen → Push scheitert non-fast-forward.
echo "  eedc-Mirror mit origin abgleichen..."
git -C "$EEDC_STANDALONE" fetch origin --quiet
if [ "$(git -C "$EEDC_STANDALONE" rev-parse HEAD)" != "$(git -C "$EEDC_STANDALONE" rev-parse origin/main)" ]; then
    echo -e "${YELLOW}  Mirror war nicht auf origin/main — reset --hard auf origin/main${NC}"
    echo -e "${YELLOW}  (reiner Spiegel: kein lokaler Stand geht verloren).${NC}"
    git -C "$EEDC_STANDALONE" reset --hard origin/main
fi

# backend/ und frontend/ komplett synchronisieren
rsync -a --delete \
    --exclude='__pycache__' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='dist' \
    eedc/backend/ "$EEDC_STANDALONE/backend/"
echo "  backend/ → eedc/backend/"

rsync -a --delete \
    --exclude='node_modules' \
    --exclude='dist' \
    eedc/frontend/ "$EEDC_STANDALONE/frontend/"
echo "  frontend/ → eedc/frontend/"

# Einzeldateien die in beiden Repos existieren
cp eedc/CHANGELOG.md "$EEDC_STANDALONE/CHANGELOG.md"
# Standalone-Mirror bekommt die Standalone-README MIT LAN-Security-Hinweis,
# NICHT die HA-App-README (dort wäre der 8099-Auth-Hinweis falsch, da HA via Ingress läuft).
cp eedc/README.standalone.md "$EEDC_STANDALONE/README.md"
cp eedc/INSTALL.md "$EEDC_STANDALONE/INSTALL.md" 2>/dev/null || true
cp eedc/.gitignore "$EEDC_STANDALONE/.gitignore" 2>/dev/null || true
cp eedc/docker-compose.yml "$EEDC_STANDALONE/docker-compose.yml" 2>/dev/null || true
cp eedc/run.sh "$EEDC_STANDALONE/run.sh"
echo "  Shared Files kopiert"

# Standalone-Dockerfile NICHT überschreiben (hat eigene Version ohne HA-Labels)
# Version im Standalone-config.py ist schon korrekt (wurde oben in eedc/ gebumpt und rüberkopiert)

# =============================================================================
# SCHRITT 6: Commit + Tag + Push eedc-Standalone
# =============================================================================
echo ""
echo -e "${CYAN}[6/7] Commit + Tag + Push eedc-Standalone...${NC}"

cd "$EEDC_STANDALONE"

# Auch hier explizit: genau die Ziele von Schritt 5 (rsync + cp), nichts sonst.
# Der Mirror trägt daneben Dateien, die release.sh NIE anfasst (config.yaml,
# Dockerfile, CLAUDE.md, docs/, .github/, package-lock.json, icon/logo) —
# die haben im Release-Commit nichts verloren. `git add -A -- <pfad>` kehrt
# auch Löschungen ein, die rsync --delete erzeugt hat.
MIRROR_PFADE=(
    backend
    frontend
    CHANGELOG.md
    README.md
    INSTALL.md
    .gitignore
    docker-compose.yml
    run.sh
)
git add -A -- "${MIRROR_PFADE[@]}"
pruefe_nichts_uebrig "$EEDC_STANDALONE" "eedc"

if git diff --cached --quiet; then
    echo -e "${YELLOW}  Keine Änderungen im Standalone-Repo.${NC}"
else
    git commit -m "release: v$VERSION (sync from eedc-homeassistant)"
fi
# Lokalen Tag aus einem früheren Fehl-Release-Lauf tolerieren — sonst bricht
# `git tag -a` mit "already exists" ab. Der Tag auf origin bleibt unberührt;
# ist die Version dort bereits released, scheitert der Push unten laut.
git tag -d "v$VERSION" 2>/dev/null || true
git tag -a "v$VERSION" -m "Version $VERSION"
git push && git push origin "v$VERSION"
echo -e "${GREEN}  eedc v$VERSION gepusht.${NC}"

# =============================================================================
# Ergebnis
# =============================================================================
cd "$REPO_DIR"

echo ""
echo -e "${CYAN}Beide Repos sind gepusht + getaggt:${NC}"
echo -e "  eedc-homeassistant: v$VERSION"
echo -e "  eedc (Standalone):  v$VERSION"
echo ""

# Versionsprüfung
echo -e "${CYAN}Versionsprüfung:${NC}"

check_version() {
    local file=$1
    local found=$(grep -oP "$2" "$file" 2>/dev/null || echo "FEHLT")
    local status="${GREEN}OK${NC}"
    if [ "$found" != "$VERSION" ]; then
        status="${RED}FALSCH ($found)${NC}"
    fi
    printf "  %-50s %s  %b\n" "$file" "$found" "$status"
}

check_version "eedc/backend/core/config.py"         '(?<=APP_VERSION = ")[^"]*'
check_version "eedc/frontend/src/config/version.ts"  "(?<=APP_VERSION = ')[^']*"
check_version "eedc/config.yaml"                     '(?<=version: ")[^"]*'
check_version "eedc/run.sh"                          '(?<=Version: )[0-9]+\.[0-9]+\.[0-9]+'
check_version "eedc/Dockerfile"                       '(?<=io.hass.version=")[^"]*'
check_version "$EEDC_STANDALONE/backend/core/config.py"         '(?<=APP_VERSION = ")[^"]*'
check_version "$EEDC_STANDALONE/frontend/src/config/version.ts"  "(?<=APP_VERSION = ')[^']*"

echo ""

# =============================================================================
# SCHRITT 7: Auf die Auslieferung warten
# =============================================================================
# Bis hierher ist NICHTS beim Anwender angekommen. `eedc/config.yaml` zieht ein
# vorgebautes ghcr-Image, das der Release-Workflow erst nach dem Tag-Push baut —
# und der Add-on-Store zeigt die neue Version schon währenddessen an. Wer hier
# aufhört, meldet einen Erfolg, den er nicht geprüft hat: am 2026-08-06 blieb
# das Fenster wegen einer GitHub-Actions-Störung sechs Stunden offen, und drei
# Anwender liefen mit `[404] manifest unknown` hinein (Nebenfund N-169).
#
# Das Warten steht bewusst in einem eigenen Script: nach einer Störung will man
# nur noch warten und prüfen, ohne ein Release anzufassen.
echo -e "${CYAN}[7/7] Auslieferung abwarten...${NC}"
echo -e "  Der Release-Workflow baut jetzt die Add-on-Images. Das dauert einige"
echo -e "  Minuten; abbrechen mit Ctrl-C ist gefahrlos (das Release bleibt draußen)."
echo ""

WARTE_RC=0
"$SCRIPT_DIR/warte-auf-image.sh" "$VERSION" || WARTE_RC=$?

echo ""
if [ "$WARTE_RC" = "0" ]; then
    echo -e "${BOLD}============================================${NC}"
    echo -e "${GREEN}  Release v$VERSION ist ausgeliefert!${NC}"
    echo -e "${BOLD}============================================${NC}"
    echo ""
    echo -e "  Beide Repos getaggt + gepusht, Image für amd64 und aarch64 bereit."
    echo -e "  Das GitHub-Release erstellt der Workflow im selben Lauf."
    echo ""
    echo -e "${YELLOW}  Nächster Schritt: ~/.claude/plans/auftrag-nachlauf-nach-release.md${NC}"
    echo ""
else
    echo -e "${YELLOW}  Der Versions-Bump, die Commits und die Tags sind vollständig durch —${NC}"
    echo -e "${YELLOW}  hier ist nichts zu wiederholen. Offen ist allein die Auslieferung.${NC}"
    echo ""
    exit "$WARTE_RC"
fi
