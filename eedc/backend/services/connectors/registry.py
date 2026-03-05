"""
Connector-Registry: Verwaltet alle verfügbaren Geräte-Connectoren.

Connectoren registrieren sich über den @register_connector Decorator.
"""

from .base import DeviceConnector, ConnectorInfo

_CONNECTORS: dict[str, type[DeviceConnector]] = {}


def register_connector(cls: type[DeviceConnector]) -> type[DeviceConnector]:
    """Decorator zum Registrieren eines Connectors."""
    instance = cls()
    connector_info = instance.info()
    _CONNECTORS[connector_info.id] = cls
    return cls


def list_connectors() -> list[ConnectorInfo]:
    """Alle verfügbaren Connectoren mit Metadaten."""
    return [cls().info() for cls in _CONNECTORS.values()]


def get_connector(connector_id: str) -> DeviceConnector:
    """Connector nach ID instanziieren."""
    if connector_id not in _CONNECTORS:
        raise ValueError(f"Unbekannter Connector: {connector_id}")
    return _CONNECTORS[connector_id]()
