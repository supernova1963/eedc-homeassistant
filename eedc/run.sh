#!/usr/bin/env bash
# EEDC Add-on Startscript

set -e

# Konfiguration aus Home Assistant Optionen laden
CONFIG_PATH=/data/options.json

if [ -f "$CONFIG_PATH" ]; then
    export LOG_LEVEL=$(jq -r '.log_level // "info"' $CONFIG_PATH)

    # MQTT Export Konfiguration
    export MQTT_ENABLED=$(jq -r '.mqtt.enabled // false' $CONFIG_PATH)
    export MQTT_HOST=$(jq -r '.mqtt.host // "core-mosquitto"' $CONFIG_PATH)
    export MQTT_PORT=$(jq -r '.mqtt.port // 1883' $CONFIG_PATH)
    export MQTT_USER=$(jq -r '.mqtt.username // ""' $CONFIG_PATH)
    export MQTT_PASSWORD=$(jq -r '.mqtt.password // ""' $CONFIG_PATH)
    export MQTT_AUTO_PUBLISH=$(jq -r '.mqtt.auto_publish // false' $CONFIG_PATH)
    export MQTT_PUBLISH_INTERVAL=$(jq -r '.mqtt.publish_interval_minutes // 60' $CONFIG_PATH)
else
    export LOG_LEVEL="info"
fi

# Datenbank-Pfad (aiosqlite für async SQLAlchemy)
export DATABASE_URL="sqlite+aiosqlite:////data/eedc.db"

# Supervisor Token (für HA API Zugriff)
# Wird automatisch von Home Assistant gesetzt

echo "==================================="
echo "  EEDC - Energie Daten Center"
echo "  Version: 1.1.0-beta.1"
echo "==================================="
echo "Log Level: $LOG_LEVEL"
echo "Database: /data/eedc.db"
if [ "$MQTT_ENABLED" = "true" ]; then
    echo "MQTT Export: enabled ($MQTT_HOST:$MQTT_PORT)"
fi
echo ""

# FastAPI Server starten
cd /app
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8099 \
    --log-level "$LOG_LEVEL" \
    --proxy-headers \
    --forwarded-allow-ips="*"
