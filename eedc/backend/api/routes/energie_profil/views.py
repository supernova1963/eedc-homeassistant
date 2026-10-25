"""
Energie-Profil API — Read-Endpoints (Fassade).

GET /api/energie-profil/{anlage_id}/tage       — Tageszusammenfassungen
GET /api/energie-profil/{anlage_id}/tage-werte — Tages-Werte-Zeilen (Bilanz + Finanzen)

GET /api/energie-profil/{anlage_id}/waerme-verlauf         — Tagesreihe des Verlaufs (Cockpit → Monat)
GET /api/energie-profil/{anlage_id}/waerme-verlauf-stunden — 24 Stunden eines Tages (Cockpit → Tag)
GET /api/energie-profil/{anlage_id}/waerme-temperaturen-stunden — Temperaturen je Gerät und Stunde (Cockpit → Tag)
GET /api/energie-profil/{anlage_id}/waerme-verteilung      — Verteilung des Waerme/Klima-Stroms (Tag · Monat · Jahr)

GET /api/energie-profil/{anlage_id}/tag-detail — snapshot-teure Tages-Detailwerte (Cockpit → Tag)
GET /api/energie-profil/{anlage_id}/tag-status — warum ein Tag leer ist, und was hilft (F-2)

GET /api/energie-profil/{anlage_id}/komponenten-serien — `komponenten_kwh`-Keys eines Zeitraums als SerieInfo
GET /api/energie-profil/{anlage_id}/stunden            — 24 Stundenwerte eines Tages
GET /api/energie-profil/{anlage_id}/wochenmuster       — Ø-Tagesprofil je Wochentag

GET /api/energie-profil/{anlage_id}/monat — Heatmap + KPIs + Peaks + Kategorien (auch Quelle des Monatsberichts)

GET /api/energie-profil/{anlage_id}/debug-rohdaten          — Rohdaten TagesEnergieProfil (7 Tage)
GET /api/energie-profil/{anlage_id}/verfuegbare-monate      — Jahr/Monat-Kombis mit Daten
GET /api/energie-profil/{anlage_id}/stats                   — Datenbestand fuer Settings
GET /api/energie-profil/{anlage_id}/reaggregate-tag/preview — Diff-Vorschau Reaggregate
GET /api/energie-profil/{anlage_id}/kraftstoffpreis-status  — Anzahl offener Zeilen

GET /api/energie-profil/{anlage_id}/tagesprognose — kombinierte Tagesprognose (Verbrauch + PV + Speicher-Simulation)

Seit 18.09.2026 sieben Module (Vorlage 4 des Refactorings grosser Dateien, reiner Umzug):
``tage`` · ``waerme`` · ``tag`` · ``serien`` · ``monat`` · ``diagnose`` · ``prognose`` — in dieser Reihenfolge
eingehaengt, damit /api/openapi.json die Routen wie bisher ordnet. Diese Fassade exportiert die Endpunkte und
``ENERGIE_KATEGORIEN`` weiter (Monatsbericht-Builder, Tests); private Helfer bleiben in ihren Modulen —
wer einen patcht, patcht das Modul, das ihn aufruft.
"""

from fastapi import APIRouter

from backend.api.routes.energie_profil.tage import (  # noqa: F401 — Re-Export
    router as _tage_router,
    get_tages_zusammenfassungen,
    get_tage_werte,
)
from backend.api.routes.energie_profil.waerme import (  # noqa: F401 — Re-Export
    router as _waerme_router,
    get_waerme_temperaturen_stunden,
    get_waerme_verlauf,
    get_waerme_verlauf_stunden,
    get_waerme_verteilung,
)
from backend.api.routes.energie_profil.tag import (  # noqa: F401 — Re-Export
    router as _tag_router,
    get_tag_detail,
    get_tag_status,
)
from backend.api.routes.energie_profil.serien import (  # noqa: F401 — Re-Export
    router as _serien_router,
    get_komponenten_serien,
    get_stundenwerte,
    get_wochenmuster,
)
from backend.api.routes.energie_profil.monat import (  # noqa: F401 — Re-Export
    router as _monat_router,
    ENERGIE_KATEGORIEN,
    get_monatsauswertung,
)
from backend.api.routes.energie_profil.diagnose import (  # noqa: F401 — Re-Export
    router as _diagnose_router,
    get_debug_rohdaten,
    verfuegbare_monate,
    get_anlage_stats,
    reaggregate_tag_preview,
    kraftstoffpreis_status,
)
from backend.api.routes.energie_profil.prognose import (  # noqa: F401 — Re-Export
    router as _prognose_router,
    get_tagesprognose,
)

router = APIRouter()
router.include_router(_tage_router)
router.include_router(_waerme_router)
router.include_router(_tag_router)
router.include_router(_serien_router)
router.include_router(_monat_router)
router.include_router(_diagnose_router)
router.include_router(_prognose_router)

__all__ = [
    "router",
    "get_tages_zusammenfassungen",
    "get_tage_werte",
    "get_waerme_verlauf",
    "get_waerme_verlauf_stunden",
    "get_waerme_verteilung",
    "get_tag_detail",
    "get_tag_status",
    "get_komponenten_serien",
    "get_stundenwerte",
    "get_wochenmuster",
    "ENERGIE_KATEGORIEN",
    "get_monatsauswertung",
    "get_debug_rohdaten",
    "verfuegbare_monate",
    "get_anlage_stats",
    "reaggregate_tag_preview",
    "kraftstoffpreis_status",
    "get_tagesprognose",
]
