#!/bin/bash
#
# kill-dev.sh - Beendet alle EEDC Entwicklungs-Prozesse und gibt Ports frei
#
# Verwendung: ./scripts/kill-dev.sh
#

# Kein set -e, da kill-Befehle fehlschlagen können wenn Prozess bereits beendet

echo "🔍 Suche nach EEDC Entwicklungs-Prozessen..."
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

killed_count=0

# Funktion: Port-Prozesse finden und beenden
kill_port() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null || true)

    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Port $port belegt - beende Prozesse: $pids${NC}"
        for pid in $pids; do
            local cmd=$(ps -p $pid -o comm= 2>/dev/null || echo "unbekannt")
            echo "  → PID $pid ($cmd)"
            kill -9 $pid 2>/dev/null || true
            ((killed_count++))
        done
    else
        echo -e "${GREEN}Port $port ist frei${NC}"
    fi
}

# Funktion: Prozesse nach Name finden und beenden
kill_by_name() {
    local pattern=$1
    local description=$2
    local pids=$(pgrep -f "$pattern" 2>/dev/null || true)

    if [ -n "$pids" ]; then
        echo -e "${YELLOW}$description gefunden - beende Prozesse${NC}"
        for pid in $pids; do
            local cmd=$(ps -p $pid -o args= 2>/dev/null | head -c 60 || echo "unbekannt")
            echo "  → PID $pid: $cmd..."
            kill -9 $pid 2>/dev/null || true
            ((killed_count++))
        done
    fi
}

echo "═══════════════════════════════════════════════════════════"
echo "1. Backend-Prozesse (uvicorn, Python)"
echo "═══════════════════════════════════════════════════════════"

# Uvicorn Backend (Port 8099)
kill_port 8099

# Uvicorn Prozesse nach Name
kill_by_name "uvicorn backend.main" "Uvicorn Backend"
kill_by_name "uvicorn.*8099" "Uvicorn auf Port 8099"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "2. Frontend-Prozesse (Vite, Node)"
echo "═══════════════════════════════════════════════════════════"

# Vite Dev Server (Port 5173)
kill_port 5173

# Alternative Frontend Ports (falls Vite auf andere Ports ausweicht)
for port in 5174 5175 5176; do
    kill_port $port
done

# Vite Prozesse nach Name
kill_by_name "vite" "Vite Dev Server"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "3. Test-Ports 3000-3009"
echo "═══════════════════════════════════════════════════════════"

for port in $(seq 3000 3009); do
    kill_port $port
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "4. Sonstige Node/npm Prozesse im Projektverzeichnis"
echo "═══════════════════════════════════════════════════════════"

kill_by_name "node.*eedc" "Node.js (eedc)"
kill_by_name "npm.*eedc" "npm (eedc)"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Zusammenfassung"
echo "═══════════════════════════════════════════════════════════"

if [ $killed_count -gt 0 ]; then
    echo -e "${GREEN}✓ $killed_count Prozess(e) beendet${NC}"
else
    echo -e "${GREEN}✓ Keine laufenden Entwicklungs-Prozesse gefunden${NC}"
fi

echo ""
echo "Ports jetzt verfügbar:"
echo "  • Backend:  http://localhost:8099"
echo "  • Frontend: http://localhost:5173"
echo ""
echo "Starte Entwicklungsserver mit:"
echo "  cd eedc && source backend/venv/bin/activate"
echo "  uvicorn backend.main:app --reload --port 8099  # Terminal 1"
echo "  cd eedc/frontend && npm run dev                 # Terminal 2"
echo ""
