"""
Activity Log Model.

Persistentes strukturiertes Protokoll für wichtige Operationen
(Connector-Tests, Imports, Cloud-Fetch etc.).
"""

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import String, Integer, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class ActivityLog(Base):
    """
    Strukturierter Aktivitätsprotokoll-Eintrag.

    Kategorien: connector_test, connector_setup, connector_fetch,
    portal_import, cloud_import, cloud_fetch, custom_import,
    backup_export, backup_import, monatsabschluss
    """

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    kategorie: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    aktion: Mapped[str] = mapped_column(String(500), nullable=False)
    erfolg: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    anlage_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="SET NULL"), nullable=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "kategorie": self.kategorie,
            "aktion": self.aktion,
            "erfolg": self.erfolg,
            "details": self.details,
            "details_json": self.details_json,
            "anlage_id": self.anlage_id,
        }
