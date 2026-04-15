"""
Investition Models

Speichert Investitionen (E-Auto, Wärmepumpe, Speicher, etc.) und deren Monatsdaten.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional, Any
from sqlalchemy import Integer, Float, String, Boolean, Date, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class InvestitionTyp(str, Enum):
    """Verfügbare Investitionstypen."""
    E_AUTO = "e-auto"
    WAERMEPUMPE = "waermepumpe"
    SPEICHER = "speicher"
    WALLBOX = "wallbox"
    WECHSELRICHTER = "wechselrichter"
    PV_MODULE = "pv-module"
    BALKONKRAFTWERK = "balkonkraftwerk"
    SONSTIGES = "sonstiges"


class Investition(Base):
    """
    Eine Investition/Erweiterung der PV-Anlage.

    Die typ-spezifischen Parameter werden als JSON gespeichert.

    Beispiel E-Auto Parameter:
        {
            "km_jahr": 15000,
            "verbrauch_kwh_100km": 18,
            "pv_anteil_prozent": 60,
            "benzinpreis_euro": 1.85,
            "nutzt_v2h": true,
            "v2h_entlade_preis_cent": 30
        }

    Beispiel PV-Module Parameter:
        {
            "anzahl_module": 40,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500
        }
    """

    __tablename__ = "investitionen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Stammdaten
    typ: Mapped[str] = mapped_column(String(50), nullable=False)  # InvestitionTyp value
    bezeichnung: Mapped[str] = mapped_column(String(255), nullable=False)
    anschaffungsdatum: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    stilllegungsdatum: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Kosten
    anschaffungskosten_gesamt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    anschaffungskosten_alternativ: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # z.B. neuer Verbrenner
    betriebskosten_jahr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PV-Module spezifische Felder (für PVGIS)
    leistung_kwp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Leistung in kWp
    ausrichtung: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Süd, Ost, West, etc.
    neigung_grad: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Modulneigung in Grad

    # Home Assistant Integration (für String-basierte IST-Erfassung)
    ha_entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # z.B. "sensor.fronius_string1_energy"

    # Typ-spezifische Parameter (JSON)
    parameter: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Prognose-Werte (berechnet)
    einsparung_prognose_jahr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    co2_einsparung_prognose_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)

    # Verknüpfung (z.B. PV-Module -> Wechselrichter)
    parent_investition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("investitionen.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    anlage = relationship("Anlage", back_populates="investitionen")
    monatsdaten = relationship("InvestitionMonatsdaten", back_populates="investition", cascade="all, delete-orphan")
    parent = relationship("Investition", remote_side=[id], backref="children")

    def __repr__(self) -> str:
        return f"<Investition(id={self.id}, typ='{self.typ}', name='{self.bezeichnung}')>"

    def ist_aktiv_an(self, tag: date) -> bool:
        """True, wenn die Investition an einem konkreten Tag aktiv war.

        `aktiv` ist manueller Override (temporär aus), `stilllegungsdatum` finaler End-Marker.
        """
        if not self.aktiv:
            return False
        if self.anschaffungsdatum and self.anschaffungsdatum > tag:
            return False
        if self.stilllegungsdatum and self.stilllegungsdatum < tag:
            return False
        return True

    def ist_aktiv_im_zeitraum(self, start: date, end: date) -> bool:
        """True, wenn die Investition irgendwann im Zeitraum [start, end] aktiv war.

        Historische Sicht — ignoriert `aktiv`-Flag bewusst, weil vergangene Daten
        ("Einsatz in H1/2024") auch nach manuellem Pausieren gültig bleiben sollen.
        Nur `stilllegungsdatum` begrenzt die Lebensspanne endgültig.
        """
        if self.anschaffungsdatum and self.anschaffungsdatum > end:
            return False
        if self.stilllegungsdatum and self.stilllegungsdatum < start:
            return False
        return True

    def ist_aktiv_im_monat(self, jahr: int, monat: int) -> bool:
        """Convenience: True, wenn Investition im gegebenen Kalendermonat (teilweise) aktiv war."""
        from calendar import monthrange
        start = date(jahr, monat, 1)
        end = date(jahr, monat, monthrange(jahr, monat)[1])
        return self.ist_aktiv_im_zeitraum(start, end)


class InvestitionMonatsdaten(Base):
    """
    Monatliche Messwerte für eine Investition.

    Die Daten werden als JSON gespeichert, da sie je nach Typ unterschiedlich sind.

    Beispiel E-Auto verbrauch_daten:
        {
            "km_gefahren": 1200,
            "verbrauch_kwh": 216,
            "ladung_pv_kwh": 130,
            "ladung_netz_kwh": 86,
            "v2h_entladung_kwh": 25,
            "ladevorgaenge": 12
        }
    """

    __tablename__ = "investition_monatsdaten"
    __table_args__ = (
        UniqueConstraint("investition_id", "jahr", "monat", name="uq_inv_monatsdaten_periode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    investition_id: Mapped[int] = mapped_column(ForeignKey("investitionen.id", ondelete="CASCADE"), nullable=False)

    # Zeitraum
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    monat: Mapped[int] = mapped_column(Integer, nullable=False)

    # Typ-spezifische Verbrauchsdaten (JSON)
    verbrauch_daten: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Berechnete Werte
    einsparung_monat_euro: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    co2_einsparung_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    investition = relationship("Investition", back_populates="monatsdaten")

    def __repr__(self) -> str:
        return f"<InvestitionMonatsdaten(inv={self.investition_id}, {self.jahr}/{self.monat:02d})>"
