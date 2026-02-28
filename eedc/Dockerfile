# EEDC Standalone
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

# System-Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python Dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend kopieren
COPY backend/ ./backend/

# Frontend Build kopieren
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Daten-Verzeichnis
RUN mkdir -p /data

EXPOSE 8099

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8099/api/health || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8099"]
