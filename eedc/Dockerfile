# EEDC Home Assistant Add-on
# Multi-Stage Build: Node (Frontend) + Python (Backend)

# =============================================================================
# Stage 1: Frontend Build
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Dependencies zuerst (Cache-Optimierung)
COPY frontend/package*.json ./
RUN npm ci

# Source kopieren und bauen
COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2: Production Image
# =============================================================================
FROM python:3.11-slim

# Labels für Home Assistant
LABEL \
    io.hass.name="EEDC" \
    io.hass.description="Energie Effizienz Data Center - PV-Anlagen Auswertung" \
    io.hass.type="addon" \
    io.hass.version="3.23.5"

# System-Abhängigkeiten
# WeasyPrint (neue PDF-Engine) braucht Pango/Cairo/HarfBuzz als native Libs.
# libpango-1.0-0 zieht libcairo + harfbuzz transitiv mit, fontconfig ist
# für die Schriften-Auflösung nötig.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis
WORKDIR /app

# Python Dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend kopieren
COPY backend/ ./backend/

# Frontend Build kopieren
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Startscript
COPY run.sh /
RUN chmod +x /run.sh

# Daten-Verzeichnis (wird als Volume gemountet)
RUN mkdir -p /data

# Port
EXPOSE 8099

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8099/api/health || exit 1

# Start
CMD ["/run.sh"]
