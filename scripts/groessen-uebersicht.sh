#!/bin/bash
# =============================================================================
# groessen-uebersicht.sh — docs/UEBERSICHT-GROESSEN.md aus dem Code erzeugen
#
# Erzeuger: eedc/backend/tests/groessen_uebersicht.py (Bauplan «Übersicht der Größen»).
# Wächter:  eedc/backend/tests/test_groessen_uebersicht.py — rot, sobald Registry, Monats-Fakten,
#           Werte-Registry, Export-Sensoren oder groessen_hand.yaml sich ändern und dieser Lauf fehlt.
#
# Verwendung:
#   ./scripts/groessen-uebersicht.sh              # Datei neu schreiben (Vorgabe: --schreiben)
#   ./scripts/groessen-uebersicht.sh --baseline   # eedc/backend/tests/groessen_offen_baseline.txt neu schreiben
#   ./scripts/groessen-uebersicht.sh --pruefen    # nur vergleichen (Exit 1 bei Abweichung)
#
# ⚠ DATABASE_URL zeigt auf eine Wegwerf-DB, BEVOR Python `backend` importiert: `core/database.py` baut die
#   Engine beim Import — ohne diese Zeile stünde dort eedc/data/eedc.db (Vorfall 28.10.2026). Der Erzeuger
#   liest keine Datenbank, er braucht nur einen harmlosen Import.
#
# Danach bewusst von Hand: ./scripts/sync-help.sh (In-App-Hilfe); die Website spiegelt beim Build.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

cd "$REPO_DIR/eedc"
# shellcheck disable=SC1091
source backend/venv/bin/activate
export DATABASE_URL="sqlite+aiosqlite:///$SCRATCH/groessen.db"

if [ $# -eq 0 ]; then
    set -- --schreiben
fi
python -m backend.tests.groessen_uebersicht "$@"
