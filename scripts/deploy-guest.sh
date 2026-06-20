#!/usr/bin/env bash
#
# deploy-guest.sh — IA-v4-Demo auf den externen Tester-Server eedcguest01 ausrollen.
#
# Baut das Frontend flag-on (VITE_IA_V4=true), überträgt aktuelles Backend + dist
# auf den Guest und baut dort ein Overlay-Image auf dem veröffentlichten
# Release-Image (ghcr.io/...:latest erbt alle System-Deps + Python-Env). So zeigt
# der Guest UNRELEASED + flag-gated v4-Inhalte, ohne regulären Standalone-Release.
#
# Voraussetzungen (einmalig auf dem Guest):
#   - /root/eedc            : Klon des eedc-Mirrors mit docker-compose.yml
#                             (image: eedc:v4demo, volume eedc-data:/data,
#                              environment: EEDC_DISABLE_SCHEDULER=true)
#   - SSH-Key-Zugang als root@<GUEST_HOST> (dieser Box-Key)
#   - Demo-DB im Volume (siehe --seed)
#
# Externe Anbindung: nginx Proxy Manager (192.168.1.3) → Guest:8099, HTTPS +
# Basic Auth (eedc.tester). Der Container bleibt auf :8099, Anbindung unberührt.
#
# Aufruf (von der Dev-Box, im Repo-Root oder via absolutem Pfad):
#   scripts/deploy-guest.sh            # Code-Deploy (Build → Image → recreate)
#   scripts/deploy-guest.sh --seed FILE  # zusätzlich Demo-DB aus FILE neu einspielen
#
# Env-Overrides: GUEST_HOST (default root@192.168.1.222), IMAGE_TAG (eedc:v4demo).
set -euo pipefail

GUEST_HOST="${GUEST_HOST:-root@192.168.1.222}"
IMAGE_TAG="${IMAGE_TAG:-eedc:v4demo}"
BUILD_CTX="/root/eedc-v4"     # Build-Kontext auf dem Guest
COMPOSE_DIR="/root/eedc"      # docker-compose.yml auf dem Guest
CONTAINER="eedc-eedc-1"

# Repo-Wurzel = zwei Ebenen über diesem Script; eedc/ ist die Source-of-Truth.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EEDC_DIR="$SCRIPT_DIR/../eedc"

SEED_FILE=""
if [ "${1:-}" = "--seed" ]; then
  SEED_FILE="${2:?--seed braucht einen Pfad zur Demo-DB}"
fi

echo "==> [1/5] Frontend flag-on bauen (VITE_IA_V4=true)"
( cd "$EEDC_DIR" && VITE_IA_V4=true npm --prefix frontend run build >/dev/null )
ls "$EEDC_DIR/frontend/dist/assets/" | grep -qiE 'CockpitV4|LayoutV4' \
  || { echo "FEHLER: keine v4-Chunks im Build"; exit 1; }

echo "==> [2/5] Backend + dist auf den Guest übertragen ($BUILD_CTX)"
ssh -o BatchMode=yes "$GUEST_HOST" "rm -rf $BUILD_CTX/backend $BUILD_CTX/frontend/dist && mkdir -p $BUILD_CTX"
( cd "$EEDC_DIR" && tar czf - --exclude=venv --exclude=__pycache__ --exclude='*.pyc' --exclude='data' backend ) \
  | ssh -o BatchMode=yes "$GUEST_HOST" "tar xzf - -C $BUILD_CTX"
( cd "$EEDC_DIR" && tar czf - frontend/dist ) \
  | ssh -o BatchMode=yes "$GUEST_HOST" "tar xzf - -C $BUILD_CTX"

echo "==> [3/5] Overlay-Dockerfile schreiben + Image bauen ($IMAGE_TAG)"
ssh -o BatchMode=yes "$GUEST_HOST" "cat > $BUILD_CTX/Dockerfile" <<'DOCKERFILE'
# v4-Demo-Overlay: erbt System-Deps + Python-Env vom Release-Image, tauscht nur
# aktuelles main-Backend (neue Endpoints) + flag-on Frontend-dist.
FROM ghcr.io/supernova1963/eedc:latest
WORKDIR /app
COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/
RUN pip install --no-cache-dir -r backend/requirements.txt
DOCKERFILE
ssh -o BatchMode=yes "$GUEST_HOST" "cd $BUILD_CTX && docker build -t $IMAGE_TAG ."

if [ -n "$SEED_FILE" ]; then
  echo "==> [3b] Demo-DB neu einspielen aus $SEED_FILE (Container gestoppt → exklusiver Zugriff)"
  ssh -o BatchMode=yes "$GUEST_HOST" "cd $COMPOSE_DIR && docker compose stop"
  scp -o BatchMode=yes "$SEED_FILE" "$GUEST_HOST:/tmp/eedc_guest_seed.db"
  ssh -o BatchMode=yes "$GUEST_HOST" 'VOL=/var/lib/docker/volumes/eedc_eedc-data/_data; cp /tmp/eedc_guest_seed.db $VOL/eedc.db; rm -f $VOL/eedc.db-wal $VOL/eedc.db-shm'
fi

echo "==> [4/5] Container neu erzeugen"
ssh -o BatchMode=yes "$GUEST_HOST" "cd $COMPOSE_DIR && docker compose up -d --force-recreate"

echo "==> [5/5] Health-Check"
ssh -o BatchMode=yes "$GUEST_HOST" "sh -c 'for i in 1 2 3 4 5 6 7 8 9 10; do docker exec $CONTAINER curl -s -m3 http://127.0.0.1:8099/api/health 2>/dev/null | grep -q healthy && { docker exec $CONTAINER curl -s http://127.0.0.1:8099/api/health; echo; exit 0; }; sleep 2; done; echo \"FEHLER: nicht healthy\"; exit 1'"

echo "==> Fertig. Live: https://eedcguest01.raunet.eu/  (Basic Auth: eedc.tester)"
