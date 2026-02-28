"""
Settings Model

Key-Value Store für Anwendungseinstellungen.
"""

from datetime import datetime
from typing import Any
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class Settings(Base):
    """
    Anwendungseinstellungen als Key-Value Store.

    Beispiele:
        - theme: "dark"
        - ha_sensor_mapping: {...}
        - last_import: "2024-01-15T10:30:00"
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Settings(key='{self.key}')>"
