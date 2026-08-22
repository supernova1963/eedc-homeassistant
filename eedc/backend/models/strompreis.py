"""
Strompreis Model

Speichert Stromtarife mit Gültigkeitszeiträumen.
"""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Float, String, Date, DateTime, ForeignKey
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
    # G19-1 K3 (R19-3): jährliche Zähler-/Messstellengebühr — reiner AUSWEIS in
    # der Jahresaufstellung (Cockpit/Jahr-Finanzen), wird NICHT in Netto-Ertrag/
    # Kosten verrechnet (Kennzahlen-Änderung wäre ein eigener Entscheid).
    zaehlergebuehr_euro_jahr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Gültigkeit
    gueltig_ab: Mapped[date] = mapped_column(Date, nullable=False)
    gueltig_bis: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # NULL = aktuell gültig

    # Tarif-Info
    tarifname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    anbieter: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vertragsart: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # fix, dynamisch, etc.

    # #392 (gruaGit, OeMAG): die Einspeisevergütung wechselt monatlich.
    # Gefragt wird die EIGENSCHAFT („wechselt der Betrag je Monat?"), nicht der
    # Vertragsname — „Direktvermarktung" wurde am 21.08.2026 geprüft und
    # verworfen (bei geförderter Direktvermarktung ist der Erlös stabil, das
    # Feld lüde zum Falschausfüllen mit dem Monatsmarktwert ein). Bewusst
    # unabhängig von `vertragsart`: gruaGits Fall ist fixer Bezug + variable
    # Einspeisung. Mit dem Häkchen bietet der Monatsabschluss
    # `Monatsdaten.einspeise_durchschnittspreis_cent` an; der Monatswert
    # schlägt den Stammwert (`resolve_einspeise_preis_cent`, Symmetrie zu P8).
    einspeisung_variabel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Verwendung (Spezialtarife)
    verwendung: Mapped[str] = mapped_column(String(30), nullable=False, default="allgemein", server_default="allgemein")  # allgemein, waermepumpe, wallbox

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    anlage = relationship("Anlage", back_populates="strompreise")

    def gilt_am(self, stichtag: date) -> bool:
        """P8-Prädikat: gilt dieser Tarifsatz am Stichtag?

        Spiegelt die WHERE-Klausel von `lade_tarife_fuer_anlage`
        (`gueltig_ab <= stichtag` und offenes oder noch nicht erreichtes
        `gueltig_bis`). Eine Stelle für die Regel statt handgeschriebener
        Datumsvergleiche je Aufrufer — die Drift-Klasse, gegen die P8 gebaut
        wurde (Prüfbericht Daten-Checker 2026-08-22/B8, D5).
        """
        return self.gueltig_ab <= stichtag and (
            self.gueltig_bis is None or self.gueltig_bis >= stichtag
        )

    def __repr__(self) -> str:
        return f"<Strompreis(anlage={self.anlage_id}, ab={self.gueltig_ab}, {self.netzbezug_arbeitspreis_cent_kwh}ct)>"
