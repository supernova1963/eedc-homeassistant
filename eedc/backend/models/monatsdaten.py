"""
Monatsdaten Model

Speichert die monatlichen Energie-Messwerte einer Anlage.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Float, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class Monatsdaten(Base):
    """
    Monatliche Energiedaten einer PV-Anlage.

    Attributes:
        jahr/monat: Zeitraum
        einspeisung_kwh: Ins Netz eingespeiste Energie
        netzbezug_kwh: Aus dem Netz bezogene Energie
        pv_erzeugung_kwh: Gesamte PV-Erzeugung (kann berechnet werden)
        batterie_*: Speicher-Daten falls vorhanden
        globalstrahlung_kwh_m2: Wetterdaten (optional)
    """

    __tablename__ = "monatsdaten"
    __table_args__ = (
        UniqueConstraint("anlage_id", "jahr", "monat", name="uq_monatsdaten_anlage_periode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Zeitraum
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    monat: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12

    # Kern-Messwerte (kWh)
    einspeisung_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    netzbezug_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    pv_erzeugung_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Berechnete Werte (werden bei Speichern berechnet)
    direktverbrauch_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eigenverbrauch_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gesamtverbrauch_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Batterie/Speicher
    batterie_ladung_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    batterie_entladung_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    batterie_ladung_netz_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Arbitrage
    batterie_ladepreis_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Arbitrage

    # Wetterdaten (optional, von Open-Meteo)
    globalstrahlung_kwh_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sonnenstunden: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadaten
    datenquelle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # manual, csv, ha_import
    notizen: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    anlage = relationship("Anlage", back_populates="monatsdaten")

    def __repr__(self) -> str:
        return f"<Monatsdaten(anlage={self.anlage_id}, {self.jahr}/{self.monat:02d})>"
