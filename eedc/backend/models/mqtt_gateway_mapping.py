"""
MQTT Gateway Mapping Model.

Speichert Topic-Übersetzungsregeln: Quell-Topic → EEDC-Inbound-Topic.
Jedes Mapping transformiert den Payload eines externen MQTT-Topics
und publisht ihn auf dem entsprechenden EEDC-Topic.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class MqttGatewayMapping(Base):
    __tablename__ = "mqtt_gateway_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )
    quell_topic: Mapped[str] = mapped_column(String(500), nullable=False)
    ziel_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_typ: Mapped[str] = mapped_column(String(20), default="plain")  # plain, json, json_array
    json_pfad: Mapped[str | None] = mapped_column(String(200), nullable=True)
    array_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    faktor: Mapped[float] = mapped_column(Float, default=1.0)
    offset: Mapped[float] = mapped_column(Float, default=0.0)
    invertieren: Mapped[bool] = mapped_column(Boolean, default=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    beschreibung: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_gateway_mapping_anlage", "anlage_id"),
    )
