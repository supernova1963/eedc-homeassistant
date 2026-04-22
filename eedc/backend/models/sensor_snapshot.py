"""
Sensor Snapshot Model.

Stündliche Snapshots kumulativer kWh-Zählerstände (PV-Erzeugung, Einspeisung,
Netzbezug, Batterie-Ladung/Entladung, WP/Wallbox-Verbrauch) — die Grundlage
für das zähler-basierte Energieprofil (Issue #135).

Differenz zweier Snapshots = kWh-Energie im Intervall. Ersetzt die bisherige
leistung_w-Integration in aggregate_day/backfill_from_statistics.

Self-Healing: Fehlende Snapshots werden on-demand aus HA Statistics gefüllt.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class SensorSnapshot(Base):
    __tablename__ = "sensor_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    sensor_key: Mapped[str] = mapped_column(String(100), nullable=False)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    wert_kwh: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("anlage_id", "sensor_key", "zeitpunkt",
                         name="uq_sensor_snapshot"),
        Index("ix_sensor_snapshot_lookup", "anlage_id", "sensor_key", "zeitpunkt"),
    )
