"""
Basis-Klassen für Geräte-Connectoren.

Jeder Hersteller-Connector implementiert DeviceConnector und wird
über den @register_connector Decorator in der Registry registriert.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class ConnectorInfo:
    """Metadaten eines Connectors für die UI-Anzeige."""

    id: str
    name: str
    hersteller: str
    beschreibung: str
    anleitung: str
    getestet: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MeterSnapshot:
    """Kumulative Zählerstände zu einem Zeitpunkt (in kWh)."""

    timestamp: str  # ISO 8601
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConnectionTestResult:
    """Ergebnis eines Verbindungstests."""

    erfolg: bool
    geraet_name: Optional[str] = None
    geraet_typ: Optional[str] = None
    seriennummer: Optional[str] = None
    firmware: Optional[str] = None
    verfuegbare_sensoren: list[str] = field(default_factory=list)
    aktuelle_werte: Optional[MeterSnapshot] = None
    fehler: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class LiveSnapshot:
    """Aktuelle Leistungswerte eines Geräts (in Watt / Prozent)."""

    timestamp: str  # ISO 8601
    leistung_w: Optional[float] = None       # Aktuelle Leistung (PV, Wallbox, WP, ...)
    einspeisung_w: Optional[float] = None    # Grid Export (nur Smart Meter)
    netzbezug_w: Optional[float] = None      # Grid Import (nur Smart Meter)
    soc: Optional[float] = None              # State of Charge % (nur Speicher)
    batterie_ladung_w: Optional[float] = None
    batterie_entladung_w: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class DeviceConnector(ABC):
    """Abstrakte Basisklasse für Geräte-Connectoren."""

    @abstractmethod
    def info(self) -> ConnectorInfo:
        """Connector-Metadaten für die UI."""

    @abstractmethod
    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zum Gerät und gibt Geräteinfo + aktuelle Werte zurück."""

    @abstractmethod
    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom Gerät."""

    async def read_live(
        self, host: str, username: str, password: str
    ) -> Optional[LiveSnapshot]:
        """Liest aktuelle Live-Leistungswerte vom Gerät (optional).

        Connectors die das unterstützen, überschreiben diese Methode.
        Default: None (nur kWh-Zähler verfügbar).
        """
        return None
