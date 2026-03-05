"""
Basis-Klassen für Portal-Export-Parser.

Jeder Hersteller-Parser implementiert PortalExportParser und wird
über den @register_parser Decorator in der Registry registriert.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ParsedMonthData:
    """Ein Monat an geparsten Energiedaten aus einem Portal-Export."""

    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    # Wallbox / Ladestation
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    # E-Auto
    eauto_km_gefahren: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def has_data(self) -> bool:
        """Prüft ob mindestens ein Energiewert vorhanden ist."""
        return any(
            v is not None
            for v in [
                self.pv_erzeugung_kwh,
                self.einspeisung_kwh,
                self.netzbezug_kwh,
                self.batterie_ladung_kwh,
                self.batterie_entladung_kwh,
                self.eigenverbrauch_kwh,
                self.wallbox_ladung_kwh,
                self.wallbox_ladung_pv_kwh,
                self.eauto_km_gefahren,
            ]
        )


@dataclass
class ParserInfo:
    """Metadaten eines Parsers für die UI-Anzeige."""

    id: str
    name: str
    hersteller: str
    beschreibung: str
    erwartetes_format: str
    anleitung: str
    beispiel_header: str
    getestet: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class PortalExportParser(ABC):
    """Abstrakte Basisklasse für Portal-Export-Parser."""

    @abstractmethod
    def info(self) -> ParserInfo:
        """Parser-Metadaten für die UI."""

    @abstractmethod
    def can_parse(self, content: str, filename: str) -> bool:
        """Prüft ob dieser Parser die Datei verarbeiten kann (Auto-Detect)."""

    @abstractmethod
    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed die Datei und gibt Monatswerte zurück."""
