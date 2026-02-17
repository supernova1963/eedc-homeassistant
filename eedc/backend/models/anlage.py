"""
Anlage Model

Repräsentiert eine PV-Anlage mit Stammdaten.
"""

from datetime import date, datetime
from typing import Optional, Any
from sqlalchemy import String, Float, Date, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class Anlage(Base):
    """
    PV-Anlage Stammdaten.

    Die Anlage repräsentiert einen Standort mit PV-Modulen.
    Die einzelnen PV-Module werden als Investitionen vom Typ "pv-module" erfasst,
    wobei jedes Modul eigene Ausrichtung, Neigung und Leistung haben kann.

    Attributes:
        id: Primärschlüssel
        anlagenname: Bezeichnung der Anlage
        leistung_kwp: Gesamtleistung in kWp (Referenzwert, echte Leistung = Summe der PV-Module)
        installationsdatum: Datum der Inbetriebnahme
        standort_*: Adressdaten
        latitude/longitude: Geokoordinaten für PVGIS (gilt für alle PV-Module am Standort)
        ausrichtung: DEPRECATED - jetzt bei PV-Modul Investitionen
        neigung_grad: DEPRECATED - jetzt bei PV-Modul Investitionen
    """

    __tablename__ = "anlagen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Stammdaten
    anlagenname: Mapped[str] = mapped_column(String(255), nullable=False)
    leistung_kwp: Mapped[float] = mapped_column(Float, nullable=False)
    installationsdatum: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Standort
    standort_plz: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    standort_ort: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    standort_strasse: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Geokoordinaten (für PVGIS)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Technische Daten
    ausrichtung: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Süd, Ost-West, etc.
    neigung_grad: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wechselrichter_hersteller: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # sma, fronius, kostal, etc.

    # DEPRECATED: Manuelle HA Sensor-Konfiguration
    # Diese Felder werden durch den neuen Utility Meter Ansatz (Teil 2) ersetzt.
    # Felder bleiben für Rückwärtskompatibilität erhalten, werden aber nicht mehr
    # aktiv genutzt. Neue Anlagen sollten diese Felder nicht mehr setzen.
    # TODO: Nach Migration auf Utility Meters entfernen (v2.0)
    ha_sensor_pv_erzeugung: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # DEPRECATED
    ha_sensor_einspeisung: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # DEPRECATED
    ha_sensor_netzbezug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # DEPRECATED
    ha_sensor_batterie_ladung: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # DEPRECATED
    ha_sensor_batterie_entladung: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # DEPRECATED

    # Erweiterte Stammdaten
    mastr_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # MaStR-ID der Anlage

    # Versorger und Zähler (JSON-Struktur)
    # Struktur: {"strom": {"name": "...", "kundennummer": "...", "portal_url": "...", "notizen": "", "zaehler": [...]}, ...}
    versorger_daten: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Wetterdaten-Provider (für Globalstrahlung/Sonnenstunden)
    # Optionen: "auto", "open-meteo", "brightsky", "open-meteo-solar"
    wetter_provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="auto")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    monatsdaten = relationship("Monatsdaten", back_populates="anlage", cascade="all, delete-orphan")
    investitionen = relationship("Investition", back_populates="anlage", cascade="all, delete-orphan")
    strompreise = relationship("Strompreis", back_populates="anlage", cascade="all, delete-orphan")
    pvgis_prognosen = relationship("PVGISPrognose", back_populates="anlage", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Anlage(id={self.id}, name='{self.anlagenname}', kWp={self.leistung_kwp})>"
