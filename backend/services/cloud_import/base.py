"""
Basis-Klassen für Cloud-Import-Provider.

Cloud-Provider holen historische Energiedaten direkt aus Hersteller-Cloud-APIs.
Jeder Provider implementiert CloudImportProvider und wird über den
@register_provider Decorator in der Registry registriert.

Output: list[ParsedMonthData] — identisch zum Portal-Import,
sodass der gleiche Apply-Mechanismus wiederverwendet werden kann.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import Optional

from backend.services.import_parsers.base import ParsedMonthData


@dataclass
class CredentialField:
    """Definition eines Eingabefelds für Provider-Credentials."""

    id: str
    label: str
    type: str = "text"  # text, password, select
    placeholder: str = ""
    required: bool = True
    options: list[dict] = field(default_factory=list)  # Für type=select: [{value, label}]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CloudProviderInfo:
    """Metadaten eines Cloud-Import-Providers für die UI."""

    id: str
    name: str
    hersteller: str
    beschreibung: str
    anleitung: str
    credential_fields: list[CredentialField] = field(default_factory=list)
    getestet: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CloudConnectionTestResult:
    """Ergebnis eines Cloud-Verbindungstests."""

    erfolg: bool
    geraet_name: Optional[str] = None
    geraet_typ: Optional[str] = None
    seriennummer: Optional[str] = None
    verfuegbare_daten: Optional[str] = None  # z.B. "Daten seit 2024-01"
    fehler: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CloudImportProvider(ABC):
    """Abstrakte Basisklasse für Cloud-Import-Provider."""

    @abstractmethod
    def info(self) -> CloudProviderInfo:
        """Provider-Metadaten für die UI."""

    @abstractmethod
    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Cloud-API mit den angegebenen Credentials."""

    @abstractmethod
    async def fetch_monthly_data(
        self,
        credentials: dict,
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
    ) -> list[ParsedMonthData]:
        """Holt historische Monatsdaten aus der Cloud-API."""
