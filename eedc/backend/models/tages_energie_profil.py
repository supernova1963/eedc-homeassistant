"""
Tages-Energieprofil Modelle.

Persistente Speicherung stündlicher Energiedaten für langfristige Analyse
und Speicher-Dimensionierungs-Simulation.

Daten werden täglich nach Mitternacht aus HA-Sensor-History / MQTT aggregiert
und bleiben dauerhaft erhalten (HA-History hat nur ~10 Tage Retention).

Zwei Tabellen:
  - TagesEnergieProfil: 24 Zeilen pro Anlage+Tag (stündliche Auflösung)
  - TagesZusammenfassung: 1 Zeile pro Anlage+Tag (Tagessummen + KPIs)
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Integer, Float, String, Date, DateTime, ForeignKey,
    UniqueConstraint, Index, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class TagesEnergieProfil(Base):
    """
    Stündliches Energieprofil einer Anlage.

    Eine Zeile pro Anlage + Datum + Stunde (max. 24 Zeilen pro Tag).
    Speichert sowohl Gesamtwerte als auch Per-Komponenten-Aufschlüsselung.
    """

    __tablename__ = "tages_energie_profil"
    __table_args__ = (
        UniqueConstraint("anlage_id", "datum", "stunde",
                         name="uq_tep_anlage_datum_stunde"),
        Index("ix_tep_anlage_datum", "anlage_id", "datum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )

    datum: Mapped[date] = mapped_column(Date, nullable=False)
    stunde: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-23

    # Gesamtwerte (kW Stundenmittel)
    pv_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verbrauch_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    einspeisung_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    netzbezug_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    batterie_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Batterie: positiv=Entladung(Quelle), negativ=Ladung(Senke)

    # Bilanz
    ueberschuss_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # max(0, pv - verbrauch) — was hätte gespeichert werden können
    defizit_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # max(0, verbrauch - pv) — was aus Speicher/Netz gedeckt werden musste

    # Wetter (IST-Daten, von Open-Meteo oder Sensor)
    temperatur_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    globalstrahlung_wm2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Batterie-SoC (Stundenmittel, %)
    soc_prozent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Per-Komponenten-Aufschlüsselung (wie Tagesverlauf-Butterfly)
    # z.B. {"pv_3": 2.1, "waermepumpe_5": -0.8, "haushalt": -1.2}
    komponenten: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    anlage = relationship("Anlage")


class TagesZusammenfassung(Base):
    """
    Tägliche Zusammenfassung einer Anlage.

    Eine Zeile pro Anlage + Datum.
    Aggregierte Kennzahlen für Monatsrollup und Speicher-Simulation.
    """

    __tablename__ = "tages_zusammenfassung"
    __table_args__ = (
        UniqueConstraint("anlage_id", "datum",
                         name="uq_tz_anlage_datum"),
        Index("ix_tz_anlage_datum", "anlage_id", "datum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anlage_id: Mapped[int] = mapped_column(
        ForeignKey("anlagen.id", ondelete="CASCADE"), nullable=False
    )

    datum: Mapped[date] = mapped_column(Date, nullable=False)

    # Energie-Bilanzen (kWh, Summe der Stundenwerte)
    ueberschuss_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    defizit_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Spitzenleistungen (kW)
    peak_pv_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_netzbezug_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_einspeisung_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Batterie-Nutzung
    batterie_vollzyklen: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Berechnung: Σ |ΔSoC| / 2 / 100 (ein Vollzyklus = 0→100→0)

    # Wetter-Tageswerte
    temperatur_min_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperatur_max_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strahlung_summe_wh_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Summe Globalstrahlung über den Tag (Wh/m²)

    # Performance Ratio: IST-Ertrag / (Strahlung × kWp × 1/1000)
    performance_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PV-Prognose (kWh): Vom Wetter-Endpoint berechnete Tagesprognose.
    # Dient als Referenzwert für den Lernfaktor (IST/Prognose-Vergleich).
    pv_prognose_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Anzahl verfügbarer Stundenwerte (Qualitätsindikator)
    stunden_verfuegbar: Mapped[int] = mapped_column(Integer, default=0)

    # Datenquelle
    datenquelle: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # "ha_sensor", "mqtt", "scheduler", "monatsabschluss"

    # Per-Komponenten Tages-kWh (Summe der stündlichen kW-Werte)
    # z.B. {"pv_3": 22.5, "waermepumpe_5": -8.3, "wallbox_7": -12.1, "haushalt": -15.2}
    # Vorzeichen: positiv = Erzeugung (PV), negativ = Verbrauch (WP, Wallbox, etc.)
    komponenten_kwh: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    anlage = relationship("Anlage")
