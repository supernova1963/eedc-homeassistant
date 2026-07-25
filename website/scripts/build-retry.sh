#!/bin/bash
# build-retry.sh — astro build mit Retry gegen die Content-Layer-Race (Astro 5.18)
#
# Beim Kaltstart (leerer Content-Store, z. B. frischer CI-Checkout) verliert Astro
# nichtdeterministisch die render-schwersten Docs (viele Code-Fences × Größe):
# der Data-Store wird gespeichert, bevor alle Einträge fertig gerendert sind →
#   [AstroUserError] The slug "…" specified in the Starlight sidebar config does not exist.
# Der Store behält erfolgreich geladene Einträge über Fehlversuche hinweg — jeder
# Retry rendert nur die noch fehlenden nach und konvergiert (empirisch: 2. Versuch).
# Deshalb zwischen den Versuchen NIEMALS .astro/ oder node_modules/.astro löschen.
set -uo pipefail
cd "$(dirname "$0")/.."

for try in 1 2 3 4; do
    if npx astro build; then
        echo "✓ astro build grün (Versuch $try)"
        exit 0
    fi
    echo "⚠ astro build fehlgeschlagen (Versuch $try) — Retry mit warmem Content-Store"
done

echo "✗ astro build nach 4 Versuchen rot"
exit 1
