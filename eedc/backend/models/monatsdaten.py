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

    # Dynamischer Tarif: Monatsdurchschnitt Netzbezugspreis (ct/kWh)
    netzbezug_durchschnittspreis_cent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Kraftstoffpreis: Monatsdurchschnitt aus EU Weekly Oil Bulletin (€/L)
    kraftstoffpreis_euro: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Alter Energiepreis (Gas/Öl) für WP-Alternativvergleich (ct/kWh)
    # Optional pro Monat — Fallback: Investition.parameter.alter_preis_cent_kwh
    gaspreis_cent_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Wetterdaten (optional, von Open-Meteo)
    globalstrahlung_kwh_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sonnenstunden: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    durchschnittstemperatur: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Energiebilanz-Analyse (aus TagesZusammenfassung aggregiert)
    ueberschuss_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Σ stündlicher PV-Überschüsse (PV > Verbrauch) — Speicher-Potenzial
    defizit_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Σ stündlicher Defizite (Verbrauch > PV) — Speicher-Bedarf
    batterie_vollzyklen: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Σ Vollzyklen im Monat (ein Zyklus = 0→100→0)
    performance_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Durchschnittliche Performance Ratio im Monat
    peak_netzbezug_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Maximaler Netzbezug im Monat (kW)

    # Sonderkosten (manuelle Eingabe)
    sonderkosten_euro: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sonderkosten_beschreibung: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Metadaten
    datenquelle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # manual, csv, ha_import
    notizen: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    anlage = relationship("Anlage", back_populates="monatsdaten")

    def __repr__(self) -> str:
        return f"<Monatsdaten(anlage={self.anlage_id}, {self.jahr}/{self.monat:02d})>"
