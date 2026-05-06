"""
Korrekturprofil-Lookup für den Live-Pfad.

Lädt pro Anlage die Korrekturprofile aus der DB (Cache, TTL 1h) und liefert
pro stündlichem GTI-Wert den Korrekturfaktor mit Fallback-Kaskade:

    sonnenstand_wetter (≥10 Datenpunkte) →
    sonnenstand        (≥15 Datenpunkte) →
    skalar             (≥7 Tage eingegangen) →
    None (Caller fällt auf den klassischen `_get_lernfaktor` zurück)

Cache wird per `invalidate_cache(anlage_id)` vom Aggregator nach Re-Build
geleert.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.korrekturprofil import (
    PROFIL_TYP_SKALAR,
    PROFIL_TYP_SONNENSTAND,
    PROFIL_TYP_SONNENSTAND_WETTER,
    Korrekturprofil,
)
from backend.services.wetter.solar_position import (
    bin_key,
    solar_position_lokal,
)
from backend.services.wetter.utils import Wetterklasse

logger = logging.getLogger(__name__)

# Mindest-Datenpunkte pro Stufe (siehe Konzept Fallback-Kaskade)
MIN_DATENPUNKTE_SONNENSTAND_WETTER = 10
MIN_DATENPUNKTE_SONNENSTAND = 15
MIN_TAGE_SKALAR = 7

# Cache-TTL — Aggregator läuft nightly, 1h-TTL ist großzügig genug
CACHE_TTL_SECONDS = 3600


@dataclass
class _ProfilCacheEintrag:
    """Eingelesener Profil-Snapshot pro Anlage."""

    sw_faktoren: dict[str, float]
    sw_datenpunkte: dict[str, int]
    sw_aufloesung_az: int
    sw_aufloesung_el: int

    s_faktoren: dict[str, float]
    s_datenpunkte: dict[str, int]
    s_aufloesung_az: int
    s_aufloesung_el: int

    skalar: Optional[float]
    skalar_tage: int

    geladen_am: float


_cache: dict[int, _ProfilCacheEintrag] = {}
_cache_lock = asyncio.Lock()


def invalidate_cache(anlage_id: int) -> None:
    """Aggregator-Hook: Cache nach Re-Build leeren."""
    _cache.pop(anlage_id, None)


def _is_cache_fresh(eintrag: _ProfilCacheEintrag) -> bool:
    return (time.monotonic() - eintrag.geladen_am) < CACHE_TTL_SECONDS


async def _lade_profile(db: AsyncSession, anlage_id: int) -> _ProfilCacheEintrag:
    """Lädt alle Profile einer Anlage aus der DB in Cache-Struktur."""
    result = await db.execute(
        select(Korrekturprofil).where(
            and_(
                Korrekturprofil.anlage_id == anlage_id,
                Korrekturprofil.investition_id.is_(None),
                Korrekturprofil.quelle == "openmeteo",
            )
        )
    )
    by_typ = {p.profil_typ: p for p in result.scalars().all()}

    sw = by_typ.get(PROFIL_TYP_SONNENSTAND_WETTER)
    s = by_typ.get(PROFIL_TYP_SONNENSTAND)
    sk = by_typ.get(PROFIL_TYP_SKALAR)

    return _ProfilCacheEintrag(
        sw_faktoren=(sw.faktoren if sw else {}) or {},
        sw_datenpunkte=(sw.datenpunkte_pro_bin if sw else {}) or {},
        sw_aufloesung_az=int((sw.bin_definition or {}).get("azimut_aufloesung", 10)) if sw else 10,
        sw_aufloesung_el=int((sw.bin_definition or {}).get("elevation_aufloesung", 10)) if sw else 10,
        s_faktoren=(s.faktoren if s else {}) or {},
        s_datenpunkte=(s.datenpunkte_pro_bin if s else {}) or {},
        s_aufloesung_az=int((s.bin_definition or {}).get("azimut_aufloesung", 10)) if s else 10,
        s_aufloesung_el=int((s.bin_definition or {}).get("elevation_aufloesung", 10)) if s else 10,
        skalar=(sk.faktor_skalar if sk else None),
        skalar_tage=(sk.tage_eingegangen if sk else 0),
        geladen_am=time.monotonic(),
    )


async def _get_eintrag(db: AsyncSession, anlage_id: int) -> _ProfilCacheEintrag:
    eintrag = _cache.get(anlage_id)
    if eintrag is not None and _is_cache_fresh(eintrag):
        return eintrag
    async with _cache_lock:
        eintrag = _cache.get(anlage_id)
        if eintrag is not None and _is_cache_fresh(eintrag):
            return eintrag
        eintrag = await _lade_profile(db, anlage_id)
        _cache[anlage_id] = eintrag
        return eintrag


@dataclass
class KorrekturfaktorResult:
    faktor: float
    stufe: str  # "sonnenstand_wetter" | "sonnenstand" | "skalar" | "miss"
    bin_key: Optional[str] = None
    datenpunkte: Optional[int] = None


async def lookup_korrekturfaktor(
    db: AsyncSession,
    *,
    anlage_id: int,
    lat: float,
    lon: float,
    datum: date,
    stunde: int,
    klasse: Optional[Wetterklasse] = None,
) -> Optional[KorrekturfaktorResult]:
    """Liefert den Korrekturfaktor für eine konkrete Stunde mit
    Fallback-Kaskade.

    `None` zurück → Caller (z. B. `live_wetter`) fällt auf den klassischen
    `_get_lernfaktor`-Skalar zurück.
    """
    eintrag = await _get_eintrag(db, anlage_id)

    # Sonnenstand einmal pro Stunde berechnen — gilt für alle Stufen
    sp = solar_position_lokal(lat, lon, datum, stunde)
    bk_sw = bin_key(sp.azimut, sp.elevation, eintrag.sw_aufloesung_az, eintrag.sw_aufloesung_el)
    bk_s = bin_key(sp.azimut, sp.elevation, eintrag.s_aufloesung_az, eintrag.s_aufloesung_el)

    # Stufe 1: sonnenstand_wetter (nur wenn Klasse vorhanden)
    if bk_sw is not None and klasse is not None:
        kombi_key = f"{bk_sw}_{klasse}"
        n = eintrag.sw_datenpunkte.get(kombi_key, 0)
        if n >= MIN_DATENPUNKTE_SONNENSTAND_WETTER:
            faktor = eintrag.sw_faktoren.get(kombi_key)
            if faktor is not None:
                return KorrekturfaktorResult(
                    faktor=faktor,
                    stufe=PROFIL_TYP_SONNENSTAND_WETTER,
                    bin_key=kombi_key,
                    datenpunkte=n,
                )

    # Stufe 2: sonnenstand
    if bk_s is not None:
        n = eintrag.s_datenpunkte.get(bk_s, 0)
        if n >= MIN_DATENPUNKTE_SONNENSTAND:
            faktor = eintrag.s_faktoren.get(bk_s)
            if faktor is not None:
                return KorrekturfaktorResult(
                    faktor=faktor,
                    stufe=PROFIL_TYP_SONNENSTAND,
                    bin_key=bk_s,
                    datenpunkte=n,
                )

    # Stufe 3: Skalar aus Korrekturprofil-Tabelle
    if eintrag.skalar is not None and eintrag.skalar_tage >= MIN_TAGE_SKALAR:
        return KorrekturfaktorResult(
            faktor=eintrag.skalar,
            stufe=PROFIL_TYP_SKALAR,
            datenpunkte=eintrag.skalar_tage,
        )

    # Kein Profil verfügbar → Caller-Fallback
    return None
