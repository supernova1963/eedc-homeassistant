"""
Backward-compatibility shim — bitte aus backend.services.wetter importieren.

Dieses Modul existiert nur für eventuelle externe oder dynamische Imports
die noch auf wetter_service zeigen. Alle internen Imports wurden migriert.
"""
from backend.services.wetter import *  # noqa: F401,F403
from backend.services.wetter import (  # noqa: F401 — explizit für private Symbole
    _cache,
    _cache_get,
    _cache_set,
    _loop_running,
    _persist_to_l2,
)
