"""
PVGIS Prognose Model

Speichert PVGIS Ertragsprognosen pro Anlage.
Ermöglicht "Prognose vs. IST" Auswertungen.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, Index, JSON, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base

# Name des partiellen Unique-Index (siehe `PVGISPrognose.__table_args__`).
# Als Konstante, weil `core/database.py` ihn für Bestands-Datenbanken nachträglich
# anlegt und `tests/test_wurzelmuster_p5_invariante.py` ihn gezielt fallen lässt,
# um den Zustand einer Installation ohne Index nachzustellen.
INDEX_EINE_AKTIVE_PROGNOSE = "ix_pvgis_prognosen_eine_aktive_je_anlage"


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

    # Invariante „genau eine aktive Prognose je Anlage" (Wurzelmuster P5, A17).
    #
    # Bewusst ein **partieller** Unique-Index (`WHERE ist_aktiv = 1`) und kein
    # `UniqueConstraint`: die Regel gilt nur für aktive Zeilen — beliebig viele
    # inaktive Prognosen je Anlage sind erwünscht (die Historie ist das Archiv,
    # aus dem der Nutzer eine ältere reaktivieren kann). Ein
    # `UniqueConstraint(anlage_id, ist_aktiv)` würde zusätzlich verbieten, zwei
    # INAKTIVE zu haben, und wäre damit falsch. Zweiter Grund: SQLite erzwingt
    # für ein nachträgliches Table-Constraint einen kompletten Table-Rebuild
    # (CREATE-COPY-DROP-RENAME), ein Index kommt mit einem `CREATE UNIQUE INDEX`
    # ohne Anfassen der Tabelle.
    #
    # Bestandsdaten können die Invariante heute verletzen (der JSON-Backup-Import
    # konnte N aktive erzeugen, s. `import_export/json_operations.py`). Deshalb
    # bereinigt `core/database.py::_migrate_pvgis_eine_aktive_prognose` VOR dem
    # Anlegen des Index — und legt ihn nicht-blockierend an: schlägt es doch fehl,
    # startet die App trotzdem, und die Lesepfade bleiben über den Auswahl-SoT
    # (`services/prognose_auswahl.py`, `LIMIT 1`) deterministisch.
    __table_args__ = (
        Index(
            INDEX_EINE_AKTIVE_PROGNOSE,
            "anlage_id",
            unique=True,
            sqlite_where=text("ist_aktiv = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(Integer, ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False)

    # Timestamp
    abgerufen_am: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Parameter
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    neigung_grad: Mapped[float] = mapped_column(Float, nullable=False)
    ausrichtung_grad: Mapped[float] = mapped_column(Float, nullable=False)  # Azimut
    system_losses: Mapped[float] = mapped_column(Float, default=14.0)

    # Ergebnisse
    jahresertrag_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    spezifischer_ertrag_kwh_kwp: Mapped[float] = mapped_column(Float, nullable=False)
    gesamt_leistung_kwp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Monatswerte als JSON: [{monat: 1, e_m: 123.4, h_m: 45.6}, ...]
    monatswerte: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Per-Modul-Monatswerte für genaue SOLL-Berechnung (NEU v2.3.2)
    # Format: {"str(investition_id)": [{"monat": 1, "e_m": 123.4, "h_m": 45.6, "sd_m": 1.2}, ...], ...}
    # Ohne dieses Feld wird die Verteilung proportional nach kWp berechnet (ungenau bei
    # unterschiedlichen Ausrichtungen). Mit diesem Feld wird pro Modul der exakte PVGIS-Wert genutzt.
    module_monatswerte: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Horizont-Profil wurde bei der Berechnung berücksichtigt
    horizont_verwendet: Mapped[Optional[bool]] = mapped_column(default=False)

    # Strahlungsdatensatz, aus dem diese Zahl stammt (PVGIS `inputs.meteo_data.
    # radiation_db`, z. B. "PVGIS-SARAH3"). Aus der Antwort gelesen, NICHT aus
    # der konfigurierten API-Version abgeleitet: die Version bestimmt den
    # Datensatz zwar heute, aber eine Konstante würde ihn behaupten statt
    # belegen — und PVGIS kann eine Version intern weiterdrehen.
    #
    # Der Wert ist der einzige Auslöser, der eine Anlage OHNE Änderung an ihren
    # Stammdaten betrifft: #363 vergleicht sonst kWp, Winkel, Koordinaten und
    # Verluste, und keiner davon bewegt sich, wenn PVGIS den Datensatz wechselt
    # (gemessen 2026-08-07: v5_2/SARAH2 2005-2020 gegen v5_3/SARAH3 2005-2023
    # ergeben für dieselbe Anlage 10.495,79 gegen 10.727,57 kWh, +2,2 %).
    #
    # NULL bei jeder Zeile, die vor v4.0.11 geschrieben wurde. Das gilt als
    # „nicht der aktuelle Datensatz" und löst genau einmal einen Neuabruf aus.
    raddatabase: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Aktiv-Flag: Nur eine Prognose pro Anlage kann aktiv sein (für Vergleiche)
    ist_aktiv: Mapped[bool] = mapped_column(default=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

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
