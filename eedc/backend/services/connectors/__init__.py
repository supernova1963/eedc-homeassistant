"""
Geräte-Connector Package.

Ermöglicht die direkte Verbindung zu Wechselrichtern und Energiemanagement-Systemen
über deren lokale REST-API, um kumulative Zählerstände auszulesen.
"""

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import list_connectors, get_connector

# Connectoren hier importieren damit sie sich registrieren
from . import sma_ennexos  # noqa: F401
from . import sma_webconnect  # noqa: F401
from . import fronius_solar_api  # noqa: F401
from . import go_echarger  # noqa: F401
from . import shelly_em  # noqa: F401
from . import opendtu  # noqa: F401
from . import kostal_plenticore  # noqa: F401
from . import sonnen_batterie  # noqa: F401
from . import tasmota_sml  # noqa: F401

__all__ = [
    "DeviceConnector",
    "ConnectorInfo",
    "MeterSnapshot",
    "ConnectionTestResult",
    "list_connectors",
    "get_connector",
]
