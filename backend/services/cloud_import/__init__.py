"""
Cloud-Import-Provider Package.

Ermöglicht den Import von historischen Energiedaten direkt aus Hersteller-Cloud-APIs.
Jeder Hersteller hat einen eigenen Provider, der die spezifische API anspricht.

Output: list[ParsedMonthData] — identisch zum Portal-Import.
"""

from .base import (
    CloudImportProvider,
    CloudProviderInfo,
    CloudConnectionTestResult,
    CredentialField,
)
from .registry import list_providers, get_provider

# Provider hier importieren damit sie sich registrieren
from . import ecoflow_powerocean  # noqa: F401

__all__ = [
    "CloudImportProvider",
    "CloudProviderInfo",
    "CloudConnectionTestResult",
    "CredentialField",
    "list_providers",
    "get_provider",
]
