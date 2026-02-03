#!/usr/bin/env bash
# EEDC Add-on Startscript

set -e

# Konfiguration aus Home Assistant Optionen laden
CONFIG_PATH=/data/options.json

if [ -f "$CONFIG_PATH" ]; then
    export LOG_LEVEL=$(jq -r '.log_level // "info"' $CONFIG_PATH)
    export HA_SENSOR_PV=$(jq -r '.ha_sensors.pv_erzeugung // ""' $CONFIG_PATH)
    export HA_SENSOR_EINSPEISUNG=$(jq -r '.ha_sensors.einspeisung // ""' $CONFIG_PATH)
    export HA_SENSOR_NETZBEZUG=$(jq -r '.ha_sensors.netzbezug // ""' $CONFIG_PATH)
    export HA_SENSOR_BATTERIE_LADUNG=$(jq -r '.ha_sensors.batterie_ladung // ""' $CONFIG_PATH)
    export HA_SENSOR_BATTERIE_ENTLADUNG=$(jq -r '.ha_sensors.batterie_entladung // ""' $CONFIG_PATH)
else
    export LOG_LEVEL="info"
fi

# Datenbank-Pfad (aiosqlite für async SQLAlchemy)
export DATABASE_URL="sqlite+aiosqlite:////data/eedc.db"

# Supervisor Token (für HA API Zugriff)
# Wird automatisch von Home Assistant gesetzt

echo "==================================="
echo "  EEDC - Energie Daten Center"
echo "  Version: 0.1.0"
echo "==================================="
echo "Log Level: $LOG_LEVEL"
echo "Database: /data/eedc.db"
echo ""

# FastAPI Server starten
cd /app
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8099 \
    --log-level "$LOG_LEVEL" \
    --proxy-headers \
    --forwarded-allow-ips="*"
