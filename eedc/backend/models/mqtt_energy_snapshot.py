"""
MQTT Energy Snapshot Model.

Periodische Snapshots der MQTT Energy-Cache-Werte für Tagesberechnungen
(heute/gestern kWh) im Standalone-MQTT-Modus ohne HA.

Snapshots werden alle 5 Minuten vom Scheduler geschrieben.
Retention: 31 Tage.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class MqttEnergySnapshot(Base):
    __tablename__ = "mqtt_energy_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    energy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_kwh: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_mqtt_snapshot_lookup", "anlage_id", "energy_key", "timestamp"),
    )
