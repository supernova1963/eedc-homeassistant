#!/bin/bash
# =============================================================================
# sync-and-release.sh – Subtree Pull + Release in eedc-homeassistant
#
# Verwendung:
#   cd /home/gernot/claude/eedc-homeassistant
#   ./scripts/sync-and-release.sh 2.8.6
#
# VORAUSSETZUNG:
#   - eedc-Repo ist bereits released + gepusht (./scripts/release.sh)
#
# Was passiert:
#   1. Prüft ob Working Directory clean ist
#   2. git subtree pull (eedc → eedc/)
#   3. Löst Versionskonflikte automatisch (nimmt immer die neue Version)
#   4. Bumpt HA-spezifische Dateien (config.yaml, run.sh)
#   5. Synchronisiert CHANGELOG (Root → eedc/)
#   6. Committed + taggt (aber pusht NICHT!)
#
# Danach MANUELL:
#   git push && git push origin v2.8.6
#
# =============================================================================

set -euo pipefail

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Argumente prüfen ---
if [ $# -ne 1 ]; then
    echo -e "${RED}Verwendung: $0 <version>${NC}"
    echo "  Beispiel: $0 2.8.6"
    exit 1
fi

VERSION="$1"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Ungültiges Versionsformat: $VERSION${NC}"
    exit 1
fi

# --- Voraussetzungen prüfen ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# Richtiges Repo?
if [ ! -f "eedc/config.yaml" ]; then
    echo -e "${RED}Fehler: Muss im eedc-homeassistant-Repo ausgeführt werden!${NC}"
    exit 1
fi

# Working Directory clean?
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo -e "${RED}Fehler: Working Directory ist nicht clean!${NC}"
    git status --short
    exit 1
fi

# Auf main?
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo -e "${RED}Fehler: Nicht auf main-Branch! (aktuell: $BRANCH)${NC}"
    exit 1
fi

# Tag existiert schon?
if git tag -l "v$VERSION" | grep -q .; then
    echo -e "${RED}Fehler: Tag v$VERSION existiert bereits!${NC}"
    exit 1
fi

echo -e "${CYAN}=== EEDC HomeAssistant Sync & Release ===${NC}"
echo -e "  Version: ${GREEN}$VERSION${NC}"
echo ""

# =============================================================================
# SCHRITT 1: Subtree Pull
# =============================================================================
echo -e "${CYAN}[1/4] Subtree Pull von eedc...${NC}"

# Subtree Pull ausführen – Konflikte sind bei Versionsdateien normal
if git subtree pull --prefix=eedc https://github.com/supernova1963/eedc.git main --squash 2>&1; then
    echo -e "${GREEN}  Subtree Pull ohne Konflikte.${NC}"
else
    echo -e "${YELLOW}  Konflikte gefunden – löse automatisch...${NC}"

    # Bekannte Konfliktdateien: Versionsdateien → immer neue Version nehmen
    CONFLICT_FILES=$(git diff --name-only --diff-filter=U 2>/dev/null || true)

    if [ -z "$CONFLICT_FILES" ]; then
        echo -e "${RED}  Subtree Pull fehlgeschlagen, aber keine Konflikte?${NC}"
        echo "  Bitte manuell prüfen: git status"
        exit 1
    fi

    for FILE in $CONFLICT_FILES; do
        case "$FILE" in
            eedc/backend/core/config.py|eedc/frontend/src/config/version.ts)
                # Versionsdateien: Upstream (eedc) gewinnt – wird danach sowieso gebumpt
                echo "  → $FILE: nehme upstream (eedc)"
                git checkout --theirs "$FILE"
                git add "$FILE"
                ;;
            eedc/CHANGELOG.md)
                # CHANGELOG: Upstream nehmen, wird danach von Root kopiert
                echo "  → $FILE: nehme upstream (eedc)"
                git checkout --theirs "$FILE"
                git add "$FILE"
                ;;
            eedc/run.sh|eedc/config.yaml)
                # HA-spezifische Dateien: Unsere Version behalten, wird danach gebumpt
                echo "  → $FILE: behalte HA-Version (ours)"
                git checkout --ours "$FILE"
                git add "$FILE"
                ;;
            *)
                echo -e "${YELLOW}  → $FILE: UNBEKANNTER KONFLIKT – bitte manuell lösen!${NC}"
                echo "    git mergetool $FILE"
                echo "    Danach: git add $FILE && git rebase --continue"
                exit 1
                ;;
        esac
    done

    # Merge abschließen
    git commit --no-edit
    echo -e "${GREEN}  Konflikte automatisch gelöst.${NC}"
fi

# =============================================================================
# SCHRITT 2: HA-spezifische Versionsdateien bumpen
# =============================================================================
echo ""
echo -e "${CYAN}[2/4] HA-spezifische Versionsdateien bumpen...${NC}"

# config.yaml
sed -i "s/^version: \".*\"/version: \"$VERSION\"/" eedc/config.yaml
echo "  eedc/config.yaml → $VERSION"

# run.sh
sed -i "s/Version: .*/Version: $VERSION\"/" eedc/run.sh
echo "  eedc/run.sh      → $VERSION"

# =============================================================================
# SCHRITT 3: CHANGELOG synchronisieren
# =============================================================================
echo ""
echo -e "${CYAN}[3/4] CHANGELOG synchronisieren...${NC}"

if [ -f "CHANGELOG.md" ]; then
    cp CHANGELOG.md eedc/CHANGELOG.md
    echo "  CHANGELOG.md → eedc/CHANGELOG.md kopiert"
else
    echo -e "${YELLOW}  Kein Root-CHANGELOG.md gefunden, überspringe.${NC}"
fi

# Prüfen ob Konfliktmarker übrig sind
if grep -rn "<<<<<<" eedc/ --include="*.py" --include="*.ts" --include="*.md" --include="*.yaml" --include="*.sh" 2>/dev/null | grep -v node_modules; then
    echo -e "${RED}  WARNUNG: Konfliktmarker gefunden! Bitte manuell prüfen.${NC}"
    exit 1
fi

# =============================================================================
# SCHRITT 4: Commit + Tag
# =============================================================================
echo ""
echo -e "${CYAN}[4/4] Commit + Tag...${NC}"

git add -A

# Prüfen ob es Änderungen gibt
if git diff --cached --quiet; then
    echo -e "${YELLOW}  Keine Änderungen zum Committen (bereits synchron).${NC}"
else
    git diff --cached --stat
    git commit -m "release: v$VERSION – Subtree Sync + HA Version Bump"
fi

git tag -a "v$VERSION" -m "Version $VERSION"

# =============================================================================
# Versionsprüfung
# =============================================================================
echo ""
echo -e "${CYAN}Versionsprüfung:${NC}"

check_version() {
    local file=$1
    local found=$(grep -oP "$2" "$file" 2>/dev/null || echo "NICHT GEFUNDEN")
    local status="${GREEN}OK${NC}"
    if [ "$found" != "$VERSION" ]; then
        status="${RED}FALSCH ($found)${NC}"
    fi
    printf "  %-45s %s  %b\n" "$file" "$found" "$status"
}

check_version "eedc/backend/core/config.py"        '(?<=APP_VERSION = ")[^"]*'
check_version "eedc/frontend/src/config/version.ts" "(?<=APP_VERSION = ')[^']*"
check_version "eedc/config.yaml"                    '(?<=version: ")[^"]*'
check_version "eedc/run.sh"                         '(?<=Version: )[0-9]+\.[0-9]+\.[0-9]+'

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Release v$VERSION vorbereitet!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "Nächster Schritt (${YELLOW}MANUELL${NC}):"
echo ""
echo "  git push && git push origin v$VERSION"
echo ""
