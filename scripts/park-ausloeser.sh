#!/usr/bin/env bash
# park-ausloeser.sh — läuft der Park-Leertest für dieses Paket?
#
# **Die Regel (Gernot, 24.08.2026):** Er läuft, wenn das Paket ein **Park-Element
# HINZUFÜGT** — und vor jedem Release. Seine Begründung, die das trägt: *„wenn sie
# einmal eine entsprechende ID haben und einmal geprüft wurde, ob der Block nicht
# mehr angezeigt wird, wenn alle der ihm zugeordneten Elemente geparkt sind"* —
# eine bestehende, unveränderte Park-ID ist bereits geprüft.
#
# ⛔ **Warum es dieses Skript gibt: der Einzeiler in CLAUDE.md maß etwas anderes,
# als die Regel sagt** (gemessen 02.09.2026). Er zählte Park-Bezeichner in
# **hinzugefügten Diff-Zeilen** — und eine *geänderte* Zeile ist im Diff eine
# hinzugefügte. Ein Paket, das an einer bestehenden `<Parkbar id="chart:wp-vergleich">`
# nur ein Prop der Kind-Komponente ergänzt, meldete damit „fahren", obwohl die
# Park-ID-Menge der Datei **bitgleich** blieb.
#
# **Das ist die dritte Runde derselben Klasse, nur eine Ebene tiefer:**
#   • 1. Fassung — Pflicht mit Begründungszwang           (Ermessen bei jedem Commit)
#   • 2. Fassung — „Datei ENTHÄLT einen Park-Bezeichner"  (5 Fehlauslösungen/40 Commits)
#   • 3. Fassung — „geänderte ZEILE enthält einen"        ⇐ dieselbe Verwechslung
#   • jetzt      — die MENGE der Park-Elemente wächst
#
# Die Gegenprobe der 3. Fassung hat es nicht gefangen, weil unter ihren drei
# Beispielen keine geänderte Zeile mit bestehender Park-ID war.
#
# Aufruf:  scripts/park-ausloeser.sh [BASIS] [ZIEL]
#          BASIS  Default HEAD  — womit verglichen wird
#          ZIEL   Default leer  — leer heisst ARBEITSBAUM (der Normalfall vor dem
#                 Commit). Ein Commit als ZIEL erlaubt die Gegenprobe an
#                 historischen Paketen, OHNE den Arbeitsbaum anzufassen.
#
# ⛔ **Das zweite Argument ist kein Komfort, es ist die Lehre aus dem Bau selbst**
#   (02.09.2026): Ohne es habe ich die historischen Belegfaelle per
#   `git checkout <commit> -- eedc/frontend/src` nachgestellt — das hat vier
#   Dateien aus alten Commits in den Index geholt, die in HEAD gar nicht
#   existieren, und die Messung obendrein verfaelscht (0 statt 5). Ein Pruefer,
#   dessen Gegenprobe den Arbeitsbaum umbaut, ist gefaehrlicher als keiner.
# ⚠ Basis ist HEAD, NICHT origin/main — Gates laufen VOR dem Commit; origin/main
#   schleppte alle bereits geprüften ungepushten Commits mit. Umfasst das Paket
#   schon Commits, entsprechend `HEAD~n` einsetzen.
set -u
BASIS="${1:-HEAD}"
ZIEL="${2:-}"
cd "$(dirname "$0")/.." || exit 2

# Park-Elemente einer Datei-Fassung: die IDs plus jedes `<FokusKachel`.
#
# ⛔ **Das ist KEINE Regel „jedes Element muss parkbar sein".** Dieses Skript
# entscheidet ausschließlich, WANN geprüft wird — es sagt nichts darüber, was
# erlaubt ist. Eine `FokusKachel` ohne Park-ID ist völlig in Ordnung (es gibt
# sieben im Baum, Stand 02.09.2026, alle richtig).
#
# Sie zählt hier mit, weil sie eine Container-Hülle ist und damit genau die
# Klasse trägt, die **nur** der Leertest fängt: eine Hülle, die sich nicht
# selbst versteckt, wenn alle ihre Kinder geparkt sind. Ein neues solches
# Element ist ein Grund zu PRÜFEN, nicht ein Mangel.
#
# ⚑ Gegenüber der alten Fassung ist das an dieser Stelle **milder**, nicht
# strenger: die zählte jedes Vorkommen in einer geänderten Zeile, diese
# verlangt einen Zuwachs.
# ⛔ **EIN grep mit Alternation, nicht drei hintereinander.** Die erste Fassung
# hatte drei greps in einer Gruppe — der erste liest den Stream leer, die beiden
# anderen bekommen nichts. Sie meldete deshalb GRÜN, als ein Sprengsatz eine neue
# `<Parkbar id="…">` einbaute. Gefunden hat es genau dieser Sprengsatz; die
# Gegenproben davor liefen gegen eine **zweite, inline geschriebene Fassung** mit
# einem grep und waren korrekt — sie prüften also nicht das Stück, das hier steht.
# *Eine Gegenprobe, die eine andere Implementierung misst als die ausgelieferte,
# belegt nichts.*
elemente() {
  grep -oE 'data-park-id="[^"]*"|<Parkbar[^>]*id="[^"]*"|<FokusKachel' | sort || true
}

NEU=0
while IFS= read -r f; do
  case "$f" in
    eedc/frontend/src/test/*|*.test.ts|*.test.tsx) continue ;;
    eedc/frontend/src/*) ;;
    *) continue ;;
  esac
  vorher=$(git show "$BASIS:$f" 2>/dev/null | elemente)
  # Gelöschte Datei: nachher leer — kann nichts hinzufügen.
  if [ -n "$ZIEL" ]; then
    nachher=$(git show "$ZIEL:$f" 2>/dev/null | elemente)
  elif [ -f "$f" ]; then
    nachher=$(elemente < "$f")
  else
    nachher=""
  fi
  # Nur ZUWACHS zählt: was nachher steht und vorher nicht (mit Vielfachheit).
  zuwachs=$(comm -13 <(printf '%s\n' "$vorher") <(printf '%s\n' "$nachher") | grep -c . )
  if [ "$zuwachs" -gt 0 ]; then
    echo "  + $f — $zuwachs neue(s) Park-Element(e):"
    comm -13 <(printf '%s\n' "$vorher") <(printf '%s\n' "$nachher") | sed 's/^/      /'
    NEU=$((NEU + zuwachs))
  fi
done < <(git diff --name-only --diff-filter=d "$BASIS" ${ZIEL:+"$ZIEL"} -- 'eedc/frontend/src')

if [ "$NEU" -gt 0 ]; then
  echo
  echo "⇒ Park-Leertest FAHREN ($NEU neue Park-Elemente)."
  echo "  Er braucht eine Demo-Box: VITE_DEMO_DEFAULT=true npm run build,"
  echo "  Runbook ~/.claude/plans/runbook-dev-box.md, dann npm run check:park-leertest"
  exit 1
fi
echo "✓ Park-Leertest nicht fällig — kein Park-Element kommt hinzu (Basis $BASIS)."
echo "  (Vor jedem RELEASE läuft er trotzdem.)"
exit 0
