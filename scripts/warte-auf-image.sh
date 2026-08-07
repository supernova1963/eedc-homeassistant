#!/bin/bash
# =============================================================================
# warte-auf-image.sh – wartet, bis das Add-on-Image einer Version wirklich
#                      in der GitHub Container Registry liegt.
#
# Verwendung:
#   ./scripts/warte-auf-image.sh 4.0.11
#   ./scripts/warte-auf-image.sh 4.0.11 --referenz 4.0.10
#
# WARUM ES DAS GIBT (Nebenfund N-169):
#   `release.sh` bumpt, taggt und pusht — das Add-on-Image baut ein Workflow
#   DANACH (.github/workflows/release.yml, Trigger `push: tags: v*`). Zwischen
#   Tag und fertigem Image zeigt der Add-on-Store die neue Version, während der
#   Pull `[404] manifest unknown` meldet. Am 2026-08-06 klaffte dieses Fenster
#   wegen einer GitHub-Actions-Störung sechs Stunden, und DREI Anwender sind
#   hineingelaufen (Forum T89667 #103/#104, GitHub #373). Das Script konnte den
#   Zustand nicht kennen: es endete vor dem Build.
#
#   Der Beleg einer Auslieferung ist das Image-Manifest, nicht ein grüner Push.
#
# SELBSTPRÜFUNG (der Grund, warum dieses Script länger ist als sein Einzeiler):
#   Ein Prüfer, der einen der beiden Pflicht-Header vergisst, meldet JEDE
#   Version als fehlend — ohne `Accept` antwortet die Registry mit 404, ohne
#   `Authorization` mit 401, in beiden Fällen auch für ein längst
#   ausgeliefertes Image. Genau das hat am 2026-08-07 einen Fehlalarm erzeugt.
#   Deshalb weist sich der Prüfer ZUERST an einer bekannt vorhandenen
#   Vorversion aus und schlägt erst danach Alarm. Meldet die Referenz auch
#   „fehlt", ist der Prüfer kaputt und nicht das Release — das ist eine andere
#   Aussage und bekommt einen eigenen Exit-Code.
#
# Exit-Codes:
#   0   beide Architekturen liegen bereit — ausgeliefert
#   1   Wartezeit abgelaufen, Prüfer nachweislich in Ordnung ⇒ Image fehlt wirklich
#   2   Prüfer nicht vertrauenswürdig (Referenz antwortet nicht mit 200)
#   130 vom Benutzer abgebrochen (Ctrl-C)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Der Build-Job in release.yml hat `timeout-minutes: 30` und läuft für zwei
# Architekturen parallel (amd64 auf ubuntu-latest, aarch64 auf ubuntu-24.04-arm).
# 40 Minuten sind dieser Deckel plus Puffer für Runner-Wartezeit — am 06.08.
# bekamen alle drei Workflows 18 Minuten lang keinen Runner zugeteilt.
TIMEOUT_SEK=${WARTE_TIMEOUT_SEK:-2400}
INTERVALL_SEK=20
# Ohne Terminal (Log, CI) wird nicht jede Runde gemeldet — das wären bei 40
# Minuten 120 Zeilen. Alle zwei Minuten eine bleibende Zeile ist genug, um zu
# sehen, dass gewartet und nicht gehangen wird.
LOG_INTERVALL_SEK=120

# Beide Header sind Pflicht — siehe Kopfkommentar.
ACCEPT_HEADER='application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json'
ARCHITEKTUREN=(amd64 aarch64)
IMAGE_BASIS='supernova1963/eedc-homeassistant'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Für Hinweise in den Meldungen absichtlich NICHT $0 — das trägt den Pfad, über
# den zufällig aufgerufen wurde (aus release.sh ein absoluter, aus einer Kette
# auch mal ein unlesbarer). Wer den Hinweis später abtippt, steht im Repo.
AUFRUF_HINWEIS="./scripts/warte-auf-image.sh"

# --- Argumente ---------------------------------------------------------------
VERSION=""
REFERENZ=""

while [ $# -gt 0 ]; do
    case "$1" in
        --referenz)
            REFERENZ="${2:-}"
            shift 2
            ;;
        -h|--help)
            sed -n '3,12p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            if [ -n "$VERSION" ]; then
                echo -e "${RED}Unerwartetes Argument: $1${NC}" >&2
                exit 1
            fi
            VERSION="$1"
            shift
            ;;
    esac
done

if [ -z "$VERSION" ]; then
    echo -e "${RED}Verwendung: ${AUFRUF_HINWEIS} <version> [--referenz <version>]${NC}" >&2
    echo "  Beispiel: ${AUFRUF_HINWEIS} 4.0.11" >&2
    exit 1
fi

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Ungültiges Versionsformat: $VERSION${NC}" >&2
    exit 1
fi

# --- Registry-Abfrage --------------------------------------------------------
# Gibt den HTTP-Code des Manifest-Abrufs aus, oder ein Sentinel-Wort, wenn schon
# der Token-Abruf scheitert. Ein Sentinel ist absichtlich KEIN Code: „kein Netz"
# und „404" sind verschiedene Aussagen, und die Verwechslung der beiden ist die
# Fehlerklasse, gegen die dieses Script gebaut ist.
ghcr_manifest_status() {
    local arch="$1" version="$2"
    local repo="${IMAGE_BASIS}-${arch}"
    local tok code

    tok=$(curl -fsS --max-time 20 "https://ghcr.io/token?scope=repository:${repo}:pull" 2>/dev/null \
          | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])' 2>/dev/null) || tok=""
    if [ -z "$tok" ]; then
        echo "kein-token"
        return 0
    fi

    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
        -H "Authorization: Bearer $tok" \
        -H "Accept: ${ACCEPT_HEADER}" \
        "https://ghcr.io/v2/${repo}/manifests/${version}" 2>/dev/null) || code="kein-netz"
    echo "$code"
}

# Höchster vorhandener Tag unterhalb der Zielversion. Beim Aufruf aus release.sh
# ist der Tag der NEUEN Version bereits gesetzt, deshalb wird er ausgeschlossen.
ermittle_referenz() {
    git -C "$REPO_DIR" tag --list 'v*' --sort=-version:refname 2>/dev/null \
        | sed 's/^v//' \
        | grep -vx "$VERSION" \
        | head -1
}

# --- E5: der Prüfer weist sich aus, BEVOR er wartet --------------------------
# Zuerst, nicht erst beim Timeout: ein kaputter Prüfer würde sonst 40 Minuten
# lang etwas Richtiges für falsch halten.
if [ -z "$REFERENZ" ]; then
    REFERENZ=$(ermittle_referenz || true)
fi

echo -e "${CYAN}Warte auf das Add-on-Image v${VERSION} in ghcr.io …${NC}"

if [ -z "$REFERENZ" ]; then
    echo -e "${YELLOW}  Keine Vorversion gefunden — die Selbstprüfung des Prüfers entfällt.${NC}"
    echo -e "${YELLOW}  Ein „Image fehlt\" unten ist damit schwächer belegt als sonst.${NC}"
else
    echo -n "  Selbstprüfung an der Vorversion v${REFERENZ}: "
    ref_amd=$(ghcr_manifest_status "amd64" "$REFERENZ")
    if [ "$ref_amd" = "200" ]; then
        echo -e "${GREEN}OK${NC} (der Prüfer sieht ein vorhandenes Image)"
    else
        echo -e "${RED}FEHLGESCHLAGEN ($ref_amd)${NC}"
        echo ""
        echo -e "${RED}ABBRUCH: Der Prüfer ist nicht vertrauenswürdig.${NC}"
        echo -e "  Die Vorversion v${REFERENZ} ist nachweislich ausgeliefert, wird hier aber"
        echo -e "  als nicht vorhanden gemeldet. Damit sagt dieses Script nichts über v${VERSION}."
        echo -e "${YELLOW}  Übliche Ursachen: keine Internet-Verbindung, ghcr.io gestört, oder einer${NC}"
        echo -e "${YELLOW}  der beiden Pflicht-Header fehlt (ohne Accept meldet die Registry 404 für${NC}"
        echo -e "${YELLOW}  jede Version, ohne Authorization 401 für jede).${NC}"
        echo -e "  Hintergrund: docs/DEVELOPMENT.md §Versionierung."
        exit 2
    fi
fi

# --- Warteschleife -----------------------------------------------------------
abgebrochen() {
    echo ""
    echo -e "${YELLOW}Abgebrochen. Das Release ist trotzdem draußen — Tag und Push sind durch,${NC}"
    echo -e "${YELLOW}nur das Image war beim Abbruch noch nicht bestätigt. Später prüfen mit:${NC}"
    echo -e "  ${BOLD}${AUFRUF_HINWEIS} $VERSION${NC}"
    exit 130
}
trap abgebrochen INT

start=$SECONDS
letzte_meldung=0
interaktiv=0
[ -t 1 ] && interaktiv=1

while true; do
    alle_da=1
    status_zeile=""
    for arch in "${ARCHITEKTUREN[@]}"; do
        code=$(ghcr_manifest_status "$arch" "$VERSION")
        status_zeile+="${arch}=${code} "
        [ "$code" = "200" ] || alle_da=0
    done

    if [ "$alle_da" = "1" ]; then
        [ "$interaktiv" = "1" ] && printf '\r%*s\r' 78 ''
        echo -e "${GREEN}  Image v${VERSION} liegt bereit — amd64 und aarch64.${NC}"
        exit 0
    fi

    verstrichen=$((SECONDS - start))
    if [ "$verstrichen" -ge "$TIMEOUT_SEK" ]; then
        break
    fi

    if [ "$interaktiv" = "1" ]; then
        printf '\r  %3d:%02d gewartet — %s(noch im Bau)   ' \
            $((verstrichen / 60)) $((verstrichen % 60)) "$status_zeile"
    elif [ $((verstrichen - letzte_meldung)) -ge "$LOG_INTERVALL_SEK" ]; then
        # Ohne Terminal keine \r-Zeile, sondern eine bleibende je LOG_INTERVALL_SEK.
        echo "  ${verstrichen}s gewartet — ${status_zeile}(noch im Bau)"
        letzte_meldung=$verstrichen
    fi

    sleep "$INTERVALL_SEK"
done

# --- Timeout: erst noch einmal den Prüfer prüfen -----------------------------
# Zwischen Start und Timeout können 40 Minuten liegen; die Verbindung, die
# eingangs stand, muss am Ende nicht mehr stehen.
[ "$interaktiv" = "1" ] && printf '\r%*s\r' 78 ''
echo ""

if [ -n "$REFERENZ" ]; then
    ref_amd=$(ghcr_manifest_status "amd64" "$REFERENZ")
    if [ "$ref_amd" != "200" ]; then
        echo -e "${RED}Wartezeit abgelaufen — aber der Prüfer ist nicht mehr vertrauenswürdig.${NC}"
        echo -e "  Die Vorversion v${REFERENZ} meldet jetzt ebenfalls „$ref_amd\"; zu Beginn war sie"
        echo -e "  erreichbar. Über v${VERSION} sagt dieser Lauf damit nichts."
        echo -e "${YELLOW}  Verbindung prüfen und erneut starten: ${AUFRUF_HINWEIS} $VERSION${NC}"
        exit 2
    fi
fi

echo -e "${RED}============================================${NC}"
echo -e "${RED}  v${VERSION} ist NICHT ausgeliefert.${NC}"
echo -e "${RED}============================================${NC}"
echo ""
echo -e "  Tag und Push sind durch — was fehlt, ist das Image."
echo -e "  Für Anwender heißt das: der Add-on-Store zeigt v${VERSION} an, das Update"
echo -e "  scheitert aber mit ${BOLD}[404] manifest unknown${NC}."
echo ""
echo -e "  Zuletzt gesehen: ${status_zeile}"
echo ""
echo -e "${YELLOW}  Nächster Schritt — den Build ansehen:${NC}"
echo -e "    gh run list --repo supernova1963/eedc-homeassistant --workflow Release --limit 5"
echo -e "${YELLOW}  Abgebrochene Läufe (etwa bei einer GitHub-Actions-Störung) neu starten:${NC}"
echo -e "    gh run rerun <run-id> --repo supernova1963/eedc-homeassistant"
echo -e "${YELLOW}  Danach erneut warten, ohne das Release anzufassen:${NC}"
echo -e "    ${AUFRUF_HINWEIS} $VERSION"
echo ""
exit 1
