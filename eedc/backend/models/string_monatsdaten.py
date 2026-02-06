"""
String-Monatsdaten Model

DEPRECATED v0.9: Dieses Model wird durch InvestitionMonatsdaten ersetzt.
PV-Modul Erträge werden jetzt in InvestitionMonatsdaten.verbrauch_daten gespeichert:
  {"pv_erzeugung_kwh": 450.5}

Das Model wird beibehalten, um bestehende Datenbanken nicht zu brechen.
Neue Daten sollten über InvestitionMonatsdaten erfasst werden.

---

Legacy-Zweck:
Speichert monatliche PV-Erträge pro String/MPPT.
Ermöglicht SOLL-IST Vergleich pro PV-Modul.
"""

from datetime import datetime
from sqlalchemy import Integer, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class StringMonatsdaten(Base):
    """
    Monatliche Ertragsdaten pro PV-String/Modul.

    Wird aus Home Assistant importiert und mit PVGIS-Prognose verglichen.

    Attributes:
        id: Primärschlüssel
        investition_id: FK zum PV-Modul (Investition)
        jahr: Jahr der Messung
        monat: Monat (1-12)
        pv_erzeugung_kwh: IST-Ertrag dieses Strings im Monat
    """

    __tablename__ = "string_monatsdaten"
    __table_args__ = (
        UniqueConstraint("investition_id", "jahr", "monat", name="uq_string_monatsdaten_periode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    investition_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("investitionen.id", ondelete="CASCADE"),
        nullable=False
    )

    # Zeitraum
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    monat: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12

    # IST-Ertrag
    pv_erzeugung_kwh: Mapped[float] = mapped_column(Float, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    investition = relationship("Investition", backref="string_monatsdaten")

    def __repr__(self) -> str:
        return f"<StringMonatsdaten(inv={self.investition_id}, {self.jahr}/{self.monat:02d}, {self.pv_erzeugung_kwh} kWh)>"
