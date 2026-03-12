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
#   2. Bumpt Version in allen 4 Dateien (eedc-homeassistant)
#   3. Kopiert CHANGELOG nach eedc/
#   4. Committed + taggt eedc-homeassistant
#   5. Pusht eedc-homeassistant
#   6. Synchronisiert shared Code nach eedc-Standalone-Repo
#   7. Committed + taggt + pusht eedc
#
# Ergebnis: Beide Repos auf gleicher Version, getaggt, gepusht.
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

# Working Directory clean?
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo -e "${RED}Fehler: eedc-homeassistant Working Directory ist nicht clean!${NC}"
    git status --short
    exit 1
fi

# Standalone-Repo clean?
if ! git -C "$EEDC_STANDALONE" diff --quiet || ! git -C "$EEDC_STANDALONE" diff --cached --quiet; then
    echo -e "${RED}Fehler: eedc Working Directory ist nicht clean!${NC}"
    git -C "$EEDC_STANDALONE" status --short
    exit 1
fi

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

# Aktuelle Version lesen
CURRENT=$(grep -oP '(?<=APP_VERSION = ")[^"]*' eedc/backend/core/config.py)
echo -e "  Aktuell:  ${YELLOW}$CURRENT${NC}"
echo -e "  Neu:      ${GREEN}$VERSION${NC}"
echo ""

# =============================================================================
# SCHRITT 1: Version bumpen in eedc-homeassistant (alle 4 Dateien)
# =============================================================================
echo -e "${CYAN}[1/5] Version bumpen in eedc-homeassistant...${NC}"

sed -i "s/^APP_VERSION = \".*\"/APP_VERSION = \"$VERSION\"/" eedc/backend/core/config.py
echo "  eedc/backend/core/config.py         → $VERSION"

sed -i "s/^export const APP_VERSION = '.*'/export const APP_VERSION = '$VERSION'/" eedc/frontend/src/config/version.ts
echo "  eedc/frontend/src/config/version.ts  → $VERSION"

sed -i "s/^version: \".*\"/version: \"$VERSION\"/" eedc/config.yaml
echo "  eedc/config.yaml                    → $VERSION"

sed -i "s/Version: .*/Version: $VERSION\"/" eedc/run.sh
echo "  eedc/run.sh                         → $VERSION"

# =============================================================================
# SCHRITT 2: CHANGELOG synchronisieren (Root → eedc/)
# =============================================================================
echo ""
echo -e "${CYAN}[2/5] CHANGELOG synchronisieren...${NC}"

if [ -f "CHANGELOG.md" ]; then
    cp CHANGELOG.md eedc/CHANGELOG.md
    echo "  CHANGELOG.md → eedc/CHANGELOG.md"
else
    echo -e "${YELLOW}  Kein Root-CHANGELOG.md gefunden, überspringe.${NC}"
fi

# Konfliktmarker-Check
if grep -rn "<<<<<<" eedc/ --include="*.py" --include="*.ts" --include="*.md" --include="*.yaml" --include="*.sh" 2>/dev/null | grep -v node_modules; then
    echo -e "${RED}ABBRUCH: Konfliktmarker gefunden!${NC}"
    exit 1
fi

# =============================================================================
# SCHRITT 3: Commit + Tag + Push eedc-homeassistant
# =============================================================================
echo ""
echo -e "${CYAN}[3/5] Commit + Tag + Push eedc-homeassistant...${NC}"

git add -A
if git diff --cached --quiet; then
    echo -e "${YELLOW}  Keine Änderungen (Version war bereits $VERSION).${NC}"
else
    git commit -m "release: v$VERSION"
fi
git tag -a "v$VERSION" -m "Version $VERSION"
git push && git push origin "v$VERSION"
echo -e "${GREEN}  eedc-homeassistant v$VERSION gepusht.${NC}"

# =============================================================================
# SCHRITT 4: Sync shared Code → eedc-Standalone
# =============================================================================
echo ""
echo -e "${CYAN}[4/5] Sync nach eedc-Standalone...${NC}"

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
cp eedc/README.md "$EEDC_STANDALONE/README.md"
cp eedc/INSTALL.md "$EEDC_STANDALONE/INSTALL.md" 2>/dev/null || true
cp eedc/.gitignore "$EEDC_STANDALONE/.gitignore" 2>/dev/null || true
cp eedc/docker-compose.yml "$EEDC_STANDALONE/docker-compose.yml" 2>/dev/null || true
echo "  Shared Files kopiert"

# Standalone-Dockerfile NICHT überschreiben (hat eigene Version ohne HA-Labels)
# Version im Standalone-config.py ist schon korrekt (wurde oben in eedc/ gebumpt und rüberkopiert)

# =============================================================================
# SCHRITT 5: Commit + Tag + Push eedc-Standalone
# =============================================================================
echo ""
echo -e "${CYAN}[5/5] Commit + Tag + Push eedc-Standalone...${NC}"

cd "$EEDC_STANDALONE"
git add -A
if git diff --cached --quiet; then
    echo -e "${YELLOW}  Keine Änderungen im Standalone-Repo.${NC}"
else
    git commit -m "release: v$VERSION (sync from eedc-homeassistant)"
fi
git tag -a "v$VERSION" -m "Version $VERSION"
git push && git push origin "v$VERSION"
echo -e "${GREEN}  eedc v$VERSION gepusht.${NC}"

# =============================================================================
# Ergebnis
# =============================================================================
cd "$REPO_DIR"

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${GREEN}  Release v$VERSION abgeschlossen!${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""
echo -e "  eedc-homeassistant: v$VERSION gepusht + getaggt"
echo -e "  eedc (Standalone):  v$VERSION gepusht + getaggt"
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
check_version "$EEDC_STANDALONE/backend/core/config.py"         '(?<=APP_VERSION = ")[^"]*'
check_version "$EEDC_STANDALONE/frontend/src/config/version.ts"  "(?<=APP_VERSION = ')[^']*"

echo ""
echo "Optional: GitHub Releases erstellen:"
echo "  gh release create v$VERSION -R supernova1963/eedc-homeassistant --title \"v$VERSION\" --generate-notes"
echo "  gh release create v$VERSION -R supernova1963/eedc --title \"v$VERSION\" --generate-notes"
echo ""
