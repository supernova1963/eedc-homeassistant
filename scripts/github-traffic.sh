#!/usr/bin/env bash
# Archiviert GitHub Traffic-Daten (Clones + Views) in CSV-Dateien.
# GitHub liefert nur die letzten 14 Tage — dieses Script sichert sie vor dem Verfall.
#
# Nutzung:
#   ./scripts/github-traffic.sh                    # Alle 3 Repos
#   ./scripts/github-traffic.sh supernova1963/eedc # Einzelnes Repo
#
# Cronjob (täglich um 6:00):
#   0 6 * * * /home/gernot/claude/eedc-homeassistant/scripts/github-traffic.sh

set -euo pipefail

REPOS=("supernova1963/eedc-homeassistant" "supernova1963/eedc" "supernova1963/eedc-community")
DATA_DIR="${HOME}/claude/github-traffic"

# Einzelnes Repo als Argument?
if [[ $# -gt 0 ]]; then
  REPOS=("$1")
fi

mkdir -p "$DATA_DIR"

for repo in "${REPOS[@]}"; do
  repo_name="${repo##*/}"
  csv_clones="${DATA_DIR}/${repo_name}-clones.csv"
  csv_views="${DATA_DIR}/${repo_name}-views.csv"

  # Header anlegen falls neu
  [[ -f "$csv_clones" ]] || echo "date,unique,total" > "$csv_clones"
  [[ -f "$csv_views" ]]  || echo "date,unique,total" > "$csv_views"

  # Clones
  gh api "repos/${repo}/traffic/clones" --jq '.clones[] | "\(.timestamp[:10]),\(.uniques),\(.count)"' 2>/dev/null | while IFS= read -r line; do
    date_val="${line%%,*}"
    grep -q "^${date_val}," "$csv_clones" 2>/dev/null || echo "$line" >> "$csv_clones"
  done

  # Views
  gh api "repos/${repo}/traffic/views" --jq '.views[] | "\(.timestamp[:10]),\(.uniques),\(.count)"' 2>/dev/null | while IFS= read -r line; do
    date_val="${line%%,*}"
    grep -q "^${date_val}," "$csv_views" 2>/dev/null || echo "$line" >> "$csv_views"
  done

  echo "[$(date +%Y-%m-%d)] ${repo_name}: OK"
done
