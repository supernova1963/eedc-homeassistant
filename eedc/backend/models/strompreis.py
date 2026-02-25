"""
Strompreis Model

Speichert Stromtarife mit Gültigkeitszeiträumen.
"""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import Float, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class Strompreis(Base):
    """
    Stromtarif mit Gültigkeitszeitraum.

    Ermöglicht historische Preise für korrekte Berechnungen.

    Attributes:
        netzbezug_arbeitspreis_cent_kwh: Preis pro kWh in Cent
        einspeiseverguetung_cent_kwh: Vergütung pro kWh in Cent
        grundpreis_euro_monat: Monatlicher Grundpreis
        gueltig_ab/bis: Gültigkeitszeitraum
    """

    __tablename__ = "strompreise"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Preise
    netzbezug_arbeitspreis_cent_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    einspeiseverguetung_cent_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    grundpreis_euro_monat: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0)

    # Gültigkeit
    gueltig_ab: Mapped[date] = mapped_column(Date, nullable=False)
    gueltig_bis: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # NULL = aktuell gültig

    # Tarif-Info
    tarifname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    anbieter: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vertragsart: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # fix, dynamisch, etc.

    # Verwendung (Spezialtarife)
    verwendung: Mapped[str] = mapped_column(String(30), nullable=False, default="allgemein", server_default="allgemein")  # allgemein, waermepumpe, wallbox

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    anlage = relationship("Anlage", back_populates="strompreise")

    def __repr__(self) -> str:
        return f"<Strompreis(anlage={self.anlage_id}, ab={self.gueltig_ab}, {self.netzbezug_arbeitspreis_cent_kwh}ct)>"
