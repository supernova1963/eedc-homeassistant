#!/bin/bash
# =============================================================================
# sync-claude.sh – Cross-Machine-Abgleich beim Rechnerwechsel
#
# Gleicht den Claude-Kontext (Memory + Plans + lokale Drafts) und beide
# Git-Repos zwischen den zwei Entwicklungsrechnern ab (gernot001 <-> gernot-iMac14-1).
#
# Verwendung:
#   ./scripts/sync-claude.sh pull    # Session-START: Stände vom Peer holen (Default)
#   ./scripts/sync-claude.sh push    # Session-ENDE:  eigene Stände zum Peer schieben
#
# Was passiert:
#   pull  -> git pull --ff-only für eedc-homeassistant UND den eedc-Mirror,
#            danach rsync Memory + Plans + Drafts VOM Peer (--checksum: Peer
#            gewinnt bei Inhaltsdrift, mtime ist irrelevant)
#   push  -> rsync Memory + Plans + Drafts ZUM Peer
#            (Git-Commits gehen per `git push` über GitHub, nicht hier)
#
# Drafts: docs/drafts/ ist via .gitignore von GitHub ausgenommen und wird
# ausschließlich zwischen den beiden Rechnern hier synchronisiert. Wer
# am Peer einen neuen Draft anlegt, schiebt ihn per `push`; der andere
# zieht ihn per `pull`. Es gibt keine GitHub-Sicht auf diese Files.
#
# Warum --checksum statt --update: nach einem frischen `git pull` haben die
# Repo-Dateien hier eine neuere mtime, aber den ÄLTEREN committed Inhalt.
# `--update` würde dann den jüngeren uncommitted Stand vom Peer fälschlich
# überspringen ("ältere mtime, also überspringen"). Mit `--checksum` zählt
# nur der Inhalt — der Peer ist authoritativ.
#
# Konsequenz: wer `pull` macht, gibt seine lokalen Memory/Plans-Edits auf,
# falls der Peer einen anderen Inhalt hat. Workflow-Disziplin:
# zuletzt-bearbeitender-Rechner pusht, der andere pullt VOR der Arbeit.
#
# Hintergrund: der Abgleich war bisher eine Sammlung manueller rsync/git-
# Befehle (Memory `reference_cross_machine_sync`). Dabei wurde der eedc-
# Mirror nie mitgezogen — release.sh committete dann auf veralteter Basis
# (v3.31.6-Vorfall). Dieses Script zieht BEIDE Repos.
#
# Ist der Peer offline (regelmäßig: Standby, anderes Subnetz), läuft der
# Git-Teil trotzdem; der rsync-Teil wird übersprungen mit Hinweis.
# =============================================================================

set -uo pipefail

# Farben
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# --- Rechner-Topologie (IPs bei DHCP-Wechsel hier anpassen) ------------------
IMAC_HOST="gernot-iMac14-1"
IMAC_IP="192.168.1.102"
GERNOT001_HOST="gernot001"
GERNOT001_IP="192.168.5.3"
SSH_USER="gernot"

# --- Pfade -------------------------------------------------------------------
HA_REPO="/home/gernot/claude/eedc-homeassistant"
MIRROR_REPO="/home/gernot/claude/eedc"
MEMORY_DIR="$HOME/.claude/projects/-home-gernot-claude-eedc-homeassistant/memory/"
PLANS_DIR="$HOME/.claude/plans/"
# Drafts liegen im Repo, sind aber via .gitignore von GitHub ausgenommen und
# werden ausschließlich zwischen den beiden Rechnern ausgetauscht.
DRAFTS_DIR="$HA_REPO/docs/drafts/"

# --- Peer bestimmen ----------------------------------------------------------
LOCAL_HOST=$(hostname)
case "$LOCAL_HOST" in
    "$IMAC_HOST")      PEER_IP="$GERNOT001_IP"; PEER_NAME="$GERNOT001_HOST" ;;
    "$GERNOT001_HOST") PEER_IP="$IMAC_IP";      PEER_NAME="$IMAC_HOST" ;;
    *)
        echo -e "${RED}Unbekannter Rechner '$LOCAL_HOST'.${NC}"
        echo "  Topologie oben im Script ergänzen."
        exit 1
        ;;
esac

MODE="${1:-pull}"
if [ "$MODE" != "pull" ] && [ "$MODE" != "push" ]; then
    echo -e "${RED}Verwendung: $0 [pull|push]${NC}"
    exit 1
fi

echo -e "${BOLD}sync-claude.sh — $LOCAL_HOST  [$MODE]  Peer: $PEER_NAME ($PEER_IP)${NC}"

# --- Peer erreichbar? --------------------------------------------------------
peer_online() {
    ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_USER@$PEER_IP" true 2>/dev/null
}

FEHLER=0

# --- git pull für ein Repo ---------------------------------------------------
pull_repo() {
    local repo=$1 name=$2
    if [ ! -d "$repo/.git" ]; then
        echo -e "  ${YELLOW}$name: kein Git-Repo unter $repo — übersprungen${NC}"
        return
    fi
    echo -e "${CYAN}  git pull --ff-only  $name${NC}"
    if git -C "$repo" pull --ff-only 2>&1 | sed 's/^/    /'; then
        :
    else
        echo -e "  ${RED}$name: pull fehlgeschlagen (Divergenz? uncommittete Änderungen?) — bitte manuell prüfen${NC}"
        FEHLER=1
    fi
}

# --- rsync Memory + Plans + Drafts -------------------------------------------
rsync_kontext() {
    local direction=$1   # "from" oder "to"
    for paar in "Memory:$MEMORY_DIR" "Plans:$PLANS_DIR" "Drafts:$DRAFTS_DIR"; do
        local label="${paar%%:*}" dir="${paar#*:}"
        if [ "$direction" = "from" ]; then
            echo -e "${CYAN}  rsync $label  <- $PEER_NAME${NC}"
            rsync -a --checksum "$SSH_USER@$PEER_IP:$dir" "$dir" 2>&1 | sed 's/^/    /' || FEHLER=1
        else
            echo -e "${CYAN}  rsync $label  -> $PEER_NAME${NC}"
            rsync -a --checksum "$dir" "$SSH_USER@$PEER_IP:$dir" 2>&1 | sed 's/^/    /' || FEHLER=1
        fi
    done
}

# =============================================================================
if [ "$MODE" = "pull" ]; then
    echo ""
    echo -e "${BOLD}[1/2] Git-Repos aktualisieren (von GitHub)${NC}"
    pull_repo "$HA_REPO" "eedc-homeassistant"
    pull_repo "$MIRROR_REPO" "eedc (Mirror)"

    echo ""
    echo -e "${BOLD}[2/2] Claude-Kontext vom Peer holen${NC}"
    if peer_online; then
        rsync_kontext from
    else
        echo -e "  ${YELLOW}Peer $PEER_NAME offline — Memory/Plans NICHT geholt.${NC}"
        echo -e "  ${YELLOW}Sobald der Peer wieder online ist, dieses Script erneut mit 'pull' laufen lassen.${NC}"
        FEHLER=1
    fi

else  # push
    echo ""
    echo -e "${BOLD}[1/1] Claude-Kontext zum Peer schieben${NC}"
    if peer_online; then
        rsync_kontext to
    else
        echo -e "  ${YELLOW}Peer $PEER_NAME offline — Memory/Plans NICHT geschoben.${NC}"
        echo -e "  ${YELLOW}Empfehlung vor Rechnerwechsel ein lokales Backup anlegen:${NC}"
        echo    "    cp -a \"$MEMORY_DIR\" \"$HOME/.claude/memory-backup-\$(date +%Y%m%d)-vor-sync/\""
        FEHLER=1
    fi
    echo -e "  ${YELLOW}Hinweis: Git-Commits gehen über GitHub (git push), nicht über dieses Script.${NC}"
fi

echo ""
if [ "$FEHLER" -eq 0 ]; then
    echo -e "${GREEN}sync-claude.sh [$MODE] abgeschlossen.${NC}"
else
    echo -e "${YELLOW}sync-claude.sh [$MODE] mit Hinweisen abgeschlossen — siehe oben.${NC}"
fi
exit 0
