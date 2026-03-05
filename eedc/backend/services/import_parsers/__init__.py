"""
Portal-Export Import-Parser Package.

Ermöglicht den Import von Energiedaten aus Hersteller-Portal-Exporten (CSV/Excel).
Jeder Hersteller hat einen eigenen Parser, der das spezifische Export-Format versteht.
"""

from .base import PortalExportParser, ParsedMonthData, ParserInfo
from .registry import list_parsers, get_parser, auto_detect_parser

# Parser hier importieren damit sie sich registrieren
from . import sma_sunny_portal  # noqa: F401
from . import sma_echarger  # noqa: F401
from . import evcc  # noqa: F401
from . import fronius_solarweb  # noqa: F401

__all__ = [
    "PortalExportParser",
    "ParsedMonthData",
    "ParserInfo",
    "list_parsers",
    "get_parser",
    "auto_detect_parser",
]
