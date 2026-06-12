"""
Korrekturprofil-Lookup für den Live-Pfad.

Lädt pro Anlage die Korrekturprofile aus der DB (Cache, TTL 1h) und liefert
pro stündlichem GTI-Wert den Korrekturfaktor mit Fallback-Kaskade:

    sonnenstand_wetter (≥10 Datenpunkte pro Bin) →
    stunde             (≥50 Stunden Saisonbin-Belegung, Variante A) →
    sonnenstand        (≥15 Datenpunkte pro Bin) →
    skalar             (≥7 Tage eingegangen) →
    None (Caller fällt auf den klassischen `_get_lernfaktor` zurück)

`stunde` steht VOR `sonnenstand`: das Saisonbin-Profil trennt saisonale
Verschattung (belaubt vs. kahl), die das saisonblinde Sonnenstand-Profil
wegmittelt.

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
    PROFIL_TYP_STUNDE,
    Korrekturprofil,
)
from backend.services.wetter.solar_position import (
    bin_key,
    solar_position_lokal,
)
from backend.services.wetter.utils import Wetterklasse, klassifiziere_stunde

logger = logging.getLogger(__name__)

# Mindest-Datenpunkte pro Stufe (siehe Konzept Fallback-Kaskade)
MIN_DATENPUNKTE_SONNENSTAND_WETTER = 10
MIN_DATENPUNKTE_SONNENSTAND = 15
MIN_TAGE_SKALAR = 7
# stunde-Stufe: Mindestbelegung pro Saisonbin (Σ Stunden-Datenpunkte über
# alle Zellen des Monats). Konservativ höher als die Bin-Stufen, damit das
# Saisonprofil das bewährte Sonnenstand-Profil erst bei solider Datenlage
# übersteuert; die Zell-Qualität selbst sichert die Aggregator-Kaskade
# (Monat ≥15 Tage → Quartal ≥15 → Gesamt ≥7).
MIN_STUNDEN_STUNDE_SAISONBIN = 50

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

    # stunde (Variante A): faktoren = {monat: {stunde: faktor}},
    # datenpunkte = {"monat_stunde": tage}, summen = Σ pro Monat (vorberechnet
    # für das Mindestbelegungs-Gate).
    st_faktoren: dict[str, dict[str, float]]
    st_datenpunkte: dict[str, int]
    st_saisonbin_summen: dict[str, int]

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
    st = by_typ.get(PROFIL_TYP_STUNDE)
    s = by_typ.get(PROFIL_TYP_SONNENSTAND)
    sk = by_typ.get(PROFIL_TYP_SKALAR)

    st_datenpunkte: dict[str, int] = (st.datenpunkte_pro_bin if st else {}) or {}
    st_saisonbin_summen: dict[str, int] = {}
    for key, anzahl in st_datenpunkte.items():
        monat_key = key.split("_", 1)[0]
        st_saisonbin_summen[monat_key] = st_saisonbin_summen.get(monat_key, 0) + int(anzahl)

    return _ProfilCacheEintrag(
        sw_faktoren=(sw.faktoren if sw else {}) or {},
        sw_datenpunkte=(sw.datenpunkte_pro_bin if sw else {}) or {},
        sw_aufloesung_az=int((sw.bin_definition or {}).get("azimut_aufloesung", 10)) if sw else 10,
        sw_aufloesung_el=int((sw.bin_definition or {}).get("elevation_aufloesung", 10)) if sw else 10,
        s_faktoren=(s.faktoren if s else {}) or {},
        s_datenpunkte=(s.datenpunkte_pro_bin if s else {}) or {},
        s_aufloesung_az=int((s.bin_definition or {}).get("azimut_aufloesung", 10)) if s else 10,
        s_aufloesung_el=int((s.bin_definition or {}).get("elevation_aufloesung", 10)) if s else 10,
        st_faktoren=(st.faktoren if st else {}) or {},
        st_datenpunkte=st_datenpunkte,
        st_saisonbin_summen=st_saisonbin_summen,
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
    stufe: str  # "sonnenstand_wetter" | "stunde" | "sonnenstand" | "skalar" | "miss"
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

    # Stufe 2: stunde (Variante A — Saisonbin × Stunde, vor sonnenstand:
    # trennt saisonale Verschattung, die die Sonnenstand-Bins wegmitteln)
    monat_key = str(datum.month)
    if eintrag.st_saisonbin_summen.get(monat_key, 0) >= MIN_STUNDEN_STUNDE_SAISONBIN:
        faktor = (eintrag.st_faktoren.get(monat_key) or {}).get(str(stunde))
        if faktor is not None:
            zell_key = f"{monat_key}_{stunde}"
            return KorrekturfaktorResult(
                faktor=faktor,
                stufe=PROFIL_TYP_STUNDE,
                bin_key=zell_key,
                datenpunkte=eintrag.st_datenpunkte.get(zell_key),
            )

    # Stufe 3: sonnenstand
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

    # Stufe 4: Skalar aus Korrekturprofil-Tabelle
    if eintrag.skalar is not None and eintrag.skalar_tage >= MIN_TAGE_SKALAR:
        return KorrekturfaktorResult(
            faktor=eintrag.skalar,
            stufe=PROFIL_TYP_SKALAR,
            datenpunkte=eintrag.skalar_tage,
        )

    # Kein Profil verfügbar → Caller-Fallback
    return None


async def korrekturfaktoren_fuer_tag(
    db: AsyncSession,
    *,
    anlage_id: int,
    lat: float,
    lon: float,
    datum: date,
    stunden_bewoelkung: Optional[list] = None,
    stunden_niederschlag: Optional[list] = None,
    stunden_wetter_code: Optional[list] = None,
) -> list[Optional[float]]:
    """Kaskaden-Korrekturfaktor für alle 24 Stunden eines Prognose-Tages.

    Wetterklasse pro Stunde via ``klassifiziere_stunde`` aus den stündlichen
    OpenMeteo-Werten; fehlende Arrays/Werte (alte Cache-Einträge ohne
    stündlichen ``weather_code``, Versions-Skew) → Klasse ggf. ``None``, die
    Kaskade greift dann ab Stufe ``stunde``.

    ``None``-Einträge = Kaskaden-Miss für diese Stunde; der Caller fällt dort
    auf den Legacy-Skalar (``_get_lernfaktor``) zurück.

    Performance: das Profil liegt nach dem ersten Lookup im Anlage-Cache
    (TTL 1h) — 24 Aufrufe pro Tag bzw. 96 pro Export-Publish sind reine
    In-Memory-Nachschläge plus Sonnenstand-Berechnung, keine DB-Queries.
    """

    def _wert(arr: Optional[list], h: int):
        return arr[h] if arr is not None and h < len(arr) else None

    faktoren: list[Optional[float]] = []
    for h in range(24):
        klasse = klassifiziere_stunde(
            _wert(stunden_bewoelkung, h),
            _wert(stunden_niederschlag, h),
            _wert(stunden_wetter_code, h),
        )
        kp = await lookup_korrekturfaktor(
            db,
            anlage_id=anlage_id,
            lat=lat,
            lon=lon,
            datum=datum,
            stunde=h,
            klasse=klasse,
        )
        faktoren.append(kp.faktor if kp is not None else None)
    return faktoren
