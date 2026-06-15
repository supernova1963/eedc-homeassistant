#!/bin/bash
# =============================================================================
# smoke.sh — Pre-Release-Smoke-Test ohne HA-Anbindung
#
# Verwendung:
#   cd /home/gernot/claude/eedc-homeassistant
#   ./scripts/smoke.sh
#
# Was wird geprüft:
#   1. Dev-venv vorhanden + pytest installiert (auto-install via
#      requirements-dev.txt, falls fehlt)
#   2. App-Boot in Standalone-Modus (Dev-venv) → erwartete Routen-Anzahl
#   3. Prod-Paritäts-Check: App-Boot + Routen auf FRISCHEM Python 3.11 mit
#      frischem `pip install -r requirements.txt` (spiegelt das Add-on-Image;
#      fängt prod-only-Dependency-Skew VOR dem Tag — Lehre v3.45.1)
#   4. pytest läuft alle Akzeptanz-Tests aus eedc/backend/tests/
#
# Nutzung:
#   - Manuell zwischen Sessions als Sanity-Check
#   - Eingehängt als Pre-Check in scripts/release.sh (vor Version-Bump)
#   - Prod-Paritäts-Check braucht `uv`; bewusst überspringbar mit
#     SMOKE_SKIP_PROD_PARITY=1 (nur, wenn uv nicht verfügbar ist)
#
# Exit-Codes:
#   0 — alle Checks grün
#   1 — venv fehlt oder pip-Install fehlgeschlagen
#   2 — App-Boot fehlgeschlagen (Import-Fehler / Routen-Zahl falsch)
#   3 — pytest fehlgeschlagen (mindestens ein Test rot)
#   4 — Prod-Paritäts-Check fehlgeschlagen (uv fehlt / 3.11-Boot / Routen-Drop)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
EEDC_DIR="$REPO_DIR/eedc"
VENV="$EEDC_DIR/backend/venv"

# Erwartete Mindest-Routen-Zahl. Wenn die App-Refactors hinzukommen, wird
# die Zahl steigen — Wert wird hier hochgezogen, damit ein versehentliches
# Routen-Drop (z. B. fehlerhafter Router-Mount im Refactor) sichtbar ist.
EXPECTED_ROUTES=217

# Aufräumen (Boot-Log + temporäres Prod-Paritäts-venv) zentral via EXIT-Trap.
APP_BOOT_LOG=""
PARITY_DIR=""
cleanup() {
    [ -n "$APP_BOOT_LOG" ] && rm -f "$APP_BOOT_LOG"
    [ -n "$PARITY_DIR" ] && rm -rf "$PARITY_DIR"
    return 0
}
trap cleanup EXIT

echo -e "${BOLD}=== EEDC Smoke ===${NC}"
echo ""

# ── 1. venv + pytest sicherstellen ───────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo -e "${RED}[1/4] Dev-venv fehlt: $VENV${NC}"
    echo "  Bitte einmalig: cd eedc && python3 -m venv backend/venv && backend/venv/bin/pip install -r backend/requirements-dev.txt"
    exit 1
fi

PYTEST="$VENV/bin/pytest"
if [ ! -x "$PYTEST" ]; then
    echo -e "${YELLOW}[1/4] pytest nicht installiert — installiere requirements-dev.txt...${NC}"
    "$VENV/bin/pip" install -q -r "$EEDC_DIR/backend/requirements-dev.txt"
    if [ ! -x "$PYTEST" ]; then
        echo -e "${RED}  pytest-Install fehlgeschlagen.${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}[1/4] Dev-venv + pytest verfügbar.${NC}"

# ── 2. App-Boot + Routen-Check ───────────────────────────────────────────────
echo -e "${CYAN}[2/4] App-Boot prüfen (Dev-venv, Standalone-Modus, kein HA-Token nötig)...${NC}"

cd "$EEDC_DIR"
APP_BOOT_LOG=$(mktemp)

if ! "$VENV/bin/python" -c "
import sys
from backend.main import app
n = len(app.routes)
print(f'Routes: {n}')
if n < $EXPECTED_ROUTES:
    print(f'FEHLER: erwartet >= $EXPECTED_ROUTES, gefunden {n}', file=sys.stderr)
    sys.exit(1)
" >"$APP_BOOT_LOG" 2>&1; then
    echo -e "${RED}  App-Boot fehlgeschlagen:${NC}"
    sed 's/^/    /' "$APP_BOOT_LOG"
    exit 2
fi
ROUTES_LINE=$(grep "^Routes:" "$APP_BOOT_LOG" || echo "Routes: ?")
echo -e "${GREEN}  $ROUTES_LINE (>=$EXPECTED_ROUTES erwartet)${NC}"

# ── 3. Prod-Paritäts-Routen-Check (frisches 3.11 + frisches pip install) ──────
# Das Add-on läuft auf python:3.11-slim mit `pip install -r requirements.txt`
# (ohne Lockfile). Der Dev-venv-Check (Schritt 2) kann eine prod-only-Regression
# maskieren — andere Python-Minor + gecachte Dependency-Versionen. Beispiel
# v3.45.1: frisch erschienenes fastapi 0.137.0 brach die Routen NUR auf frischem
# 3.11; Dev (3.12 + gecachtes 0.136.3) blieb grün → Release ging rot raus.
# Dieser Schritt spiegelt das Image und gatet das Release VOR dem Tag.
echo -e "${CYAN}[3/4] Prod-Paritäts-Check: Routen auf frischem Python 3.11...${NC}"

if ! command -v uv >/dev/null 2>&1; then
    if [ "${SMOKE_SKIP_PROD_PARITY:-0}" = "1" ]; then
        echo -e "${YELLOW}  ⚠ uv fehlt — Prod-Paritäts-Check ÜBERSPRUNGEN (SMOKE_SKIP_PROD_PARITY=1).${NC}"
        echo -e "${YELLOW}    Release ohne prod-nahe Routen-Prüfung — nur bewusst nutzen.${NC}"
    else
        echo -e "${RED}  uv nicht gefunden — Prod-Paritäts-Check nicht durchführbar.${NC}"
        echo -e "    Installieren: ${BOLD}curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
        echo -e "    Oder bewusst überspringen: ${BOLD}SMOKE_SKIP_PROD_PARITY=1 $0${NC}"
        exit 4
    fi
else
    PARITY_DIR=$(mktemp -d)
    if ! uv venv --python 3.11 "$PARITY_DIR/venv" >"$PARITY_DIR/setup.log" 2>&1; then
        echo -e "${RED}  Konnte kein 3.11-venv anlegen:${NC}"
        sed 's/^/    /' "$PARITY_DIR/setup.log"
        exit 4
    fi
    echo -e "  frisches 3.11-venv + requirements.txt installieren (~30–60 s)..."
    if ! uv pip install --python "$PARITY_DIR/venv/bin/python" -q -r "$EEDC_DIR/backend/requirements.txt" >"$PARITY_DIR/pip.log" 2>&1; then
        echo -e "${RED}  pip install (requirements.txt) auf 3.11 fehlgeschlagen:${NC}"
        tail -8 "$PARITY_DIR/pip.log" | sed 's/^/    /'
        exit 4
    fi
    if ! "$PARITY_DIR/venv/bin/python" -c "
import sys
import fastapi
from backend.main import app
n = len(app.routes)
print(f'Routes: {n} (fastapi {fastapi.__version__})')
if n < $EXPECTED_ROUTES:
    print(f'FEHLER: erwartet >= $EXPECTED_ROUTES, gefunden {n}', file=sys.stderr)
    sys.exit(1)
" >"$PARITY_DIR/boot.log" 2>&1; then
        echo -e "${RED}  Prod-Paritäts-Boot fehlgeschlagen (prod-nahe Deps!):${NC}"
        sed 's/^/    /' "$PARITY_DIR/boot.log"
        echo -e "${RED}  → Genau diese Klasse hat v3.45.1 gebrochen — Dependency-Versionen prüfen/deckeln.${NC}"
        exit 4
    fi
    PARITY_ROUTES=$(grep "^Routes:" "$PARITY_DIR/boot.log" || echo "Routes: ?")
    echo -e "${GREEN}  $PARITY_ROUTES (>=$EXPECTED_ROUTES erwartet)${NC}"
fi

# ── 4. pytest ────────────────────────────────────────────────────────────────
echo -e "${CYAN}[4/4] Akzeptanz-Tests via pytest...${NC}"

if ! "$PYTEST" -q --no-header 2>&1 | tee /tmp/eedc-smoke-pytest.log | tail -3; then
    echo -e "${RED}  pytest fehlgeschlagen — Detail in /tmp/eedc-smoke-pytest.log${NC}"
    exit 3
fi

echo ""
echo -e "${BOLD}${GREEN}Smoke OK.${NC}"
