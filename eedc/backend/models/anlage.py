"""
Anlage Model

Repräsentiert eine PV-Anlage mit Stammdaten.
"""

from datetime import date, datetime
from typing import Optional, Any
from sqlalchemy import String, Float, Integer, Date, DateTime, JSON, Boolean, LargeBinary, ForeignKey
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
    standort_land: Mapped[Optional[str]] = mapped_column(String(5), nullable=True, default='DE')
    standort_plz: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    standort_ort: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    standort_strasse: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Geokoordinaten (für PVGIS)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Horizont-Profil für PVGIS (userhorizon Parameter)
    # Flat-Liste von Elevationswerten (Grad) bei gleichmäßigen Azimut-Schritten ab Nord (0°)
    horizont_daten: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

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

    # Wettermodell für Solar-Prognose (Open-Meteo Forecast Model)
    # Optionen: "auto" (best_match), "meteoswiss_icon_ch2", "icon_d2", "icon_eu", "ecmwf_ifs04"
    wetter_modell: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="auto")

    # Sensor-Mapping für Home Assistant Integration
    # Struktur: {"basis": {...}, "investitionen": {...}}
    # Siehe docs/PLAN_AUTOMATISCHE_DATENERFASSUNG.md für vollständige Dokumentation
    sensor_mapping: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Connector-Konfiguration für direkte Geräteverbindung (ennexOS REST API etc.)
    # Struktur: {"connector_id": "sma_ennexos", "host": "...", "username": "...",
    #            "password": "base64...", "geraet_name": "...", "meter_snapshots": {...}, ...}
    connector_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Community-Sharing: Hash zur Identifikation bei Löschung
    # Wird nach erfolgreichem Teilen gesetzt und für Delete-Endpoint benötigt
    community_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Auto-Share: Monatsdaten nach Abschluss automatisch an Community senden
    community_auto_share: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    # Energiefluss-Anzeige: Netz-Puffer in Watt (unterhalb = Balance/grün)
    netz_puffer_w: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=100)

    # Prognose-Basis: welche Quelle als Grundlage für EEDC-kalibriert dient
    # "openmeteo" (Default, Standalone), "solcast" (wenn konfiguriert)
    prognose_basis: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="openmeteo")

    # Einmaliger Auto-Vollbackfill aus HA Statistics: läuft beim ersten Monatsabschluss
    # nach Upgrade automatisch durch (siehe _post_save_hintergrund). Wird gesetzt vom
    # manuellen Wizard-Button und vom Auto-Lauf, damit es genau einmal pro Anlage greift.
    vollbackfill_durchgefuehrt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Steuerliche Behandlung
    # keine_ust: Kein USt-Effekt (Post-2023 ≤30kWp, Kleinunternehmer)
    # regelbesteuerung: USt auf Eigenverbrauch (Pre-2023, >30kWp, AT/CH)
    steuerliche_behandlung: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="keine_ust")
    ust_satz_prozent: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=19.0)  # DE: 19, AT: 20, CH: 8.1, IT: 22

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    monatsdaten = relationship("Monatsdaten", back_populates="anlage", cascade="all, delete-orphan")
    investitionen = relationship("Investition", back_populates="anlage", cascade="all, delete-orphan")
    strompreise = relationship("Strompreis", back_populates="anlage", cascade="all, delete-orphan")
    pvgis_prognosen = relationship("PVGISPrognose", back_populates="anlage", cascade="all, delete-orphan")
    infothek_eintraege = relationship("InfothekEintrag", back_populates="anlage", cascade="all, delete-orphan")
    foto = relationship("AnlageFoto", back_populates="anlage", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Anlage(id={self.id}, name='{self.anlagenname}', kWp={self.leistung_kwp})>"


class AnlageFoto(Base):
    """
    Hauptfoto einer Anlage — wird auf der Titelseite der Anlagendokumentation
    gerendert. Eine Anlage hat genau ein Foto (1:1).

    Bildpipeline: wiederverwendet aus infothek_datei_service (Resize auf
    ~500 KB, Thumbnail ~50 KB, EXIF-Rotation, HEIC→JPEG-Konvertierung).
    """

    __tablename__ = "anlage_foto"

    anlage_id: Mapped[int] = mapped_column(
        ForeignKey("anlagen.id", ondelete="CASCADE"), primary_key=True
    )
    dateiname: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    daten: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    thumbnail: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    anlage = relationship("Anlage", back_populates="foto")

    def __repr__(self) -> str:
        return f"<AnlageFoto(anlage_id={self.anlage_id}, {len(self.daten)} bytes)>"
