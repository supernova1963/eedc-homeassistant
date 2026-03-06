"""
Cloud-Import-Provider Registry: Verwaltet alle verfügbaren Cloud-Import-Provider.

Provider registrieren sich über den @register_provider Decorator.
"""

from .base import CloudImportProvider, CloudProviderInfo

_PROVIDERS: dict[str, type[CloudImportProvider]] = {}


def register_provider(cls: type[CloudImportProvider]) -> type[CloudImportProvider]:
    """Decorator zum Registrieren eines Cloud-Import-Providers."""
    instance = cls()
    provider_info = instance.info()
    _PROVIDERS[provider_info.id] = cls
    return cls


def list_providers() -> list[CloudProviderInfo]:
    """Alle verfügbaren Provider mit Metadaten."""
    return [cls().info() for cls in _PROVIDERS.values()]


def get_provider(provider_id: str) -> CloudImportProvider:
    """Provider nach ID instanziieren."""
    if provider_id not in _PROVIDERS:
        raise ValueError(f"Unbekannter Cloud-Import-Provider: {provider_id}")
    return _PROVIDERS[provider_id]()
