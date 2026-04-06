"""
MQTT Live Snapshot Model.

Periodische Snapshots der MQTT Live-Leistungsdaten (W) für Tagesverlauf-Chart
im Standalone-MQTT-Modus ohne HA.

Snapshots werden alle 5 Minuten vom Scheduler geschrieben.
Retention: 15 Tage (genug für Tagesverlauf + Puffer).

component_key Format:
  "basis:einspeisung_w"       — Basis-Einspeisung
  "basis:netzbezug_w"         — Basis-Netzbezug
  "basis:pv_gesamt_w"         — PV Gesamt (Basis-Sensor)
  "basis:netz_kombi_w"        — Netz kombiniert (bidirektional)
  "inv:14:leistung_w"         — Investition 14, Gesamtleistung
  "inv:14:leistung_heizen_w"  — WP Heizung separat
  "inv:14:leistung_warmwasser_w" — WP Warmwasser separat
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class MqttLiveSnapshot(Base):
    __tablename__ = "mqtt_live_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    component_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_w: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_mqtt_live_snapshot_lookup", "anlage_id", "timestamp"),
    )
