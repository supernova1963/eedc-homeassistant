#!/bin/bash
# =============================================================================
# sync-help.sh – Kuratierte Docs für In-App-Hilfe-Seite synchronisieren
#
# Liest die nutzer­seitigen Markdown-Dateien aus docs/ und legt sie in
#   eedc/frontend/public/help/
# ab, zusammen mit einer index.json (Reihenfolge + Titel + Kategorie).
#
# Wird automatisch von release.sh vor dem Frontend-Build aufgerufen.
# Manuell ausführbar während der Entwicklung:
#   ./scripts/sync-help.sh
#
# Source of Truth bleibt docs/ — die Kopien sind committed, damit
# git-clone ohne Umweg funktioniert.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SRC="$REPO_DIR/docs"
DST="$REPO_DIR/eedc/frontend/public/help"

if [ ! -d "$SRC" ]; then
    echo "Fehler: docs/ nicht gefunden ($SRC)" >&2
    exit 1
fi

mkdir -p "$DST"

# Kuratierte Liste: nur nutzer­seitige Doku, keine internen Konzept-Papiere.
# Format: <slug>|<dateiname>|<titel>|<kategorie>
ENTRIES=(
    "benutzerhandbuch|BENUTZERHANDBUCH.md|Übersicht|Einstieg"
    "installation|HANDBUCH_INSTALLATION.md|Teil I: Installation & Einrichtung|Handbuch"
    "bedienung|HANDBUCH_BEDIENUNG.md|Teil II: Bedienung|Handbuch"
    "einstellungen|HANDBUCH_EINSTELLUNGEN.md|Teil III: Einstellungen & Sensormapping|Handbuch"
    "infothek|HANDBUCH_INFOTHEK.md|Teil IV: Infothek|Handbuch"
    "berechnungen|BERECHNUNGEN.md|Berechnungen & Kennzahlen|Referenz"
    "sensor-referenz|SENSOR-REFERENZ.md|Sensor-Referenz|Referenz"
    "glossar|GLOSSAR.md|Glossar|Referenz"
)

# Index-JSON aufbauen
INDEX="$DST/index.json"
{
    echo "["
    first=1
    for entry in "${ENTRIES[@]}"; do
        IFS='|' read -r slug filename title category <<<"$entry"
        src="$SRC/$filename"
        if [ ! -f "$src" ]; then
            echo "  Überspringe (nicht gefunden): $filename" >&2
            continue
        fi
        cp "$src" "$DST/$slug.md"
        if [ $first -eq 0 ]; then echo ","; fi
        first=0
        printf '  {"slug": "%s", "title": "%s", "category": "%s", "filename": "%s"}' \
            "$slug" "$title" "$category" "$filename"
    done
    echo
    echo "]"
} >"$INDEX"

# Anzahl synchronisierter Dateien
COUNT=$(find "$DST" -maxdepth 1 -name '*.md' | wc -l)
echo "  $COUNT Hilfe-Datei(en) → eedc/frontend/public/help/"
