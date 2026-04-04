"""
Wetter-Package: Zentraler Re-Export aller öffentlichen Symbole.

Alle Consumer importieren hier her — entweder direkt aus diesem Package
oder (für Rückwärtskompatibilität) über den wetter_service.py Shim.
"""

from backend.services.wetter.cache import (
    _cache,
    _cache_get,
    _cache_set,
    _loop_running,
    _persist_to_l2,
    warmup_l1_from_l2,
    cleanup_l2_cache,
    FORECAST_CACHE_TTL,
    ARCHIVE_CACHE_TTL,
    JITTER_MAX_SECONDS,
)
from backend.services.wetter.models import (
    WetterProvider,
    WETTER_MODELLE,
    MODELL_ANZEIGE,
)
from backend.services.wetter.utils import (
    MJ_TO_KWH,
    SECONDS_TO_HOURS,
    wetter_code_zu_symbol,
)
from backend.services.wetter.open_meteo import (
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_FORECAST_URL,
    fetch_open_meteo_archive,
    fetch_open_meteo_forecast,
)
from backend.services.wetter.pvgis import (
    PVGIS_TMY_DEFAULTS,
    fetch_pvgis_tmy_monat,
    get_pvgis_tmy_defaults,
)
from backend.services.wetter.orchestrator import (
    get_wetterdaten,
    get_wetterdaten_multi,
    get_available_providers,
    get_provider_comparison,
)

__all__ = [
    # Cache
    "_cache", "_cache_get", "_cache_set", "_loop_running", "_persist_to_l2",
    "warmup_l1_from_l2", "cleanup_l2_cache",
    "FORECAST_CACHE_TTL", "ARCHIVE_CACHE_TTL", "JITTER_MAX_SECONDS",
    # Models
    "WetterProvider", "WETTER_MODELLE", "MODELL_ANZEIGE",
    # Utils
    "MJ_TO_KWH", "SECONDS_TO_HOURS", "wetter_code_zu_symbol",
    # Open-Meteo
    "OPEN_METEO_ARCHIVE_URL", "OPEN_METEO_FORECAST_URL",
    "fetch_open_meteo_archive", "fetch_open_meteo_forecast",
    # PVGIS
    "PVGIS_TMY_DEFAULTS", "fetch_pvgis_tmy_monat", "get_pvgis_tmy_defaults",
    # Orchestrator
    "get_wetterdaten", "get_wetterdaten_multi",
    "get_available_providers", "get_provider_comparison",
]
