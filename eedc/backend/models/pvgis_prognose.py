"""
PVGIS Prognose Model

Speichert PVGIS Ertragsprognosen pro Anlage.
Ermöglicht "Prognose vs. IST" Auswertungen.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class PVGISPrognose(Base):
    """
    Gespeicherte PVGIS Ertragsprognose.

    Enthält die von PVGIS berechnete Jahresprognose inkl. monatlicher Werte.
    Wird beim Abruf gespeichert und für Prognose vs. IST verwendet.

    Attributes:
        id: Primärschlüssel
        anlage_id: FK zur Anlage
        abgerufen_am: Timestamp des PVGIS-Abrufs

        # Parameter die für die Berechnung verwendet wurden
        latitude: Breitengrad
        longitude: Längengrad
        neigung_grad: Modulneigung
        ausrichtung_grad: Azimut (0=Süd)
        system_losses: Systemverluste in %

        # Ergebnisse
        jahresertrag_kwh: Prognostizierter Jahresertrag
        spezifischer_ertrag_kwh_kwp: kWh pro kWp
        monatswerte: JSON mit monatlichen Werten
    """

    __tablename__ = "pvgis_prognosen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Timestamp
    abgerufen_am: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Parameter
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    neigung_grad: Mapped[float] = mapped_column(Float, nullable=False)
    ausrichtung_grad: Mapped[float] = mapped_column(Float, nullable=False)  # Azimut
    system_losses: Mapped[float] = mapped_column(Float, default=14.0)

    # Ergebnisse
    jahresertrag_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    spezifischer_ertrag_kwh_kwp: Mapped[float] = mapped_column(Float, nullable=False)

    # Monatswerte als JSON: [{monat: 1, e_m: 123.4, h_m: 45.6}, ...]
    monatswerte: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Aktiv-Flag: Nur eine Prognose pro Anlage kann aktiv sein (für Vergleiche)
    ist_aktiv: Mapped[bool] = mapped_column(default=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    anlage = relationship("Anlage", back_populates="pvgis_prognosen")
    monatsprognosen_detail = relationship("PVGISMonatsprognose", back_populates="prognose", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PVGISPrognose(id={self.id}, anlage_id={self.anlage_id}, kwh={self.jahresertrag_kwh})>"


class PVGISMonatsprognose(Base):
    """
    Monatliche Prognosewerte (normalisiert).

    Alternative zu JSON-Speicherung für einfachere SQL-Abfragen.
    Ermöglicht direkte JOINs mit Monatsdaten.
    """

    __tablename__ = "pvgis_monatsprognosen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prognose_id: Mapped[int] = mapped_column(Integer, ForeignKey("pvgis_prognosen.id", ondelete="CASCADE"), nullable=False)

    monat: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    ertrag_kwh: Mapped[float] = mapped_column(Float, nullable=False)  # E_m
    einstrahlung_kwh_m2: Mapped[float] = mapped_column(Float, nullable=False)  # H(i)_m
    standardabweichung_kwh: Mapped[float] = mapped_column(Float, default=0)  # SD_m

    # Relationship
    prognose = relationship("PVGISPrognose", back_populates="monatsprognosen_detail")

    def __repr__(self) -> str:
        return f"<PVGISMonatsprognose(prognose_id={self.prognose_id}, monat={self.monat}, kwh={self.ertrag_kwh})>"
