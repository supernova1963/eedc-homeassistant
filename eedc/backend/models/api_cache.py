"""
API-Response-Cache (L2) — persistente Schicht unter dem In-Memory-Cache.

Überlebt Server-Neustarts und wird beim Boot in den RAM-Cache (L1) geladen.
Reduziert Wartezeiten beim ersten Seitenaufruf nach Neustart auf ~5ms.
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, JSON, DateTime, Text
from backend.core.database import Base


class ApiCache(Base):
    """Persistenter Cache für API-Responses (Open-Meteo, BrightSky etc.)."""
    __tablename__ = "api_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(500), unique=True, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    ttl_seconds = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
