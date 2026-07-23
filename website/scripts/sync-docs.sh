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
  ["BENUTZERHANDBUCH.md"]="benutzerhandbuch.md|Benutzerhandbuch|Übersicht und Navigation zum eedc-Benutzerhandbuch"
  ["HANDBUCH_INSTALLATION.md"]="handbuch-installation.md|Installation & Einrichtung|Teil I: Installation, Setup-Wizard, Monatsabschluss, Tipps und Fehlerbehebung"
  ["HANDBUCH_BEDIENUNG.md"]="handbuch-bedienung.md|Bedienung|Teil II: Cockpit, Komponenten, Auswertungen, Community"
  ["HANDBUCH_EINSTELLUNGEN.md"]="handbuch-einstellungen.md|Einstellungen & Datenquellen|Teil III: Einstellungen, Datenerfassung, Datenquellen-Zuordnung und HA-Integration"
  ["HANDBUCH_INFOTHEK.md"]="handbuch-infothek.md|Modul: Infothek|Dokumente, Verträge und Komponenten-Akte verwalten"
  ["HANDBUCH_DATEN_CHECKER.md"]="handbuch-daten-checker.md|Modul: Daten-Checker|Datenqualität prüfen und Reparatur-Werkbank"
  ["HANDBUCH_ENERGIEPROFIL.md"]="handbuch-energieprofil.md|Modul: Energieprofil|Stundengenaues Energieprofil – wo es in v4 liegt"
  ["HANDBUCH_PROGNOSEN.md"]="handbuch-prognosen.md|Modul: Prognosen|Vorschau, Genauigkeit und Prognosequellen"
  ["SENSOR-REFERENZ.md"]="sensor-referenz.md|Sensor-Referenz|HA-Export-Sensoren und MQTT-Topics im Überblick"
  ["BERECHNUNGEN.md"]="berechnungen.md|Berechnungsreferenz|Formeln und Berechnungsgrundlagen aller Kennzahlen"
  ["GLOSSAR.md"]="glossar.md|Glossar|Begriffserklärungen und Support-Informationen"
  ["WAS-IST-NEU.md"]="was-ist-neu.md|Was ist neu|Was sich pro Version für dich als Anwender geändert hat"
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
sync_file "$CHANGELOG" "changelog.md" "Changelog" "Alle Änderungen und Versionshistorie von eedc"

echo "✓ Docs sync complete (16 files)"
