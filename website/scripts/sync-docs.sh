#!/bin/bash
# sync-docs.sh - Kopiert docs/ → website/src/content/docs/ mit YAML-Frontmatter
#
# Single Source of Truth: Die Dokumentationen werden in docs/ gepflegt.
# Dieses Script generiert die Website-Versionen mit Astro-Frontmatter.
# Wird automatisch vor `astro build` ausgeführt (siehe package.json prebuild).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

DOCS_DIR="../docs"
CHANGELOG="../CHANGELOG.md"
TARGET="src/content/docs"

# Mapping: Quelldatei → Zieldatei|Titel|Beschreibung
declare -A DOCS=(
  ["BENUTZERHANDBUCH.md"]="benutzerhandbuch.md|Benutzerhandbuch|Vollständiges Benutzerhandbuch für EEDC"
  ["ARCHITEKTUR.md"]="architektur.md|Architektur|Architektur-Dokumentation – Systemaufbau, Datenmodell und Schnittstellen"
  ["DEVELOPMENT.md"]="entwicklung.md|Entwicklung|Entwicklungsanleitung – Setup, Build, Test und Deployment"
  ["SETUP_DEVMACHINE.md"]="setup-devmachine.md|Dev-Machine Setup|Entwicklungsrechner einrichten – Ubuntu 24.04"
)

sync_file() {
  local src="$1" target="$2" title="$3" desc="$4"

  if [ ! -f "$src" ]; then
    echo "⚠ SKIP: $src not found"
    return
  fi

  {
    echo "---"
    echo "title: \"$title\""
    echo "description: \"$desc\""
    echo "---"
    echo ""
    cat "$src"
  } > "$TARGET/$target"

  echo "  ✓ $target (from $(basename "$src"))"
}

echo "Syncing docs/ → website/src/content/docs/ ..."

for src in "${!DOCS[@]}"; do
  IFS='|' read -r target title desc <<< "${DOCS[$src]}"
  sync_file "$DOCS_DIR/$src" "$target" "$title" "$desc"
done

# Changelog separat (von Repository-Root)
sync_file "$CHANGELOG" "changelog.md" "Changelog" "Alle Änderungen und Versionshistorie von EEDC"

echo "✓ Docs sync complete (5 files)"
