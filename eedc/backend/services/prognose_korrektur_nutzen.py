"""Wächter «Korrektur nur, wenn sie hilft» — die Messung je Anlage und Tag (Päckchen CC, 9.11.2026).

Je Anlage einmal am Tag (Tagescache, Muster ``live_wetter._get_lernfaktor_detail``; kein Scheduler-Job — der Kanon fragt
beim ersten Aufruf des Tages): die letzten 30 Tage mit IST, je Tag der relative Tagesfehler der **Kaskade**
(Σ ``pv_prognose_kaskade_stundenprofil``, für Tage vor der Spalte Σ ``pv_prognose_stundenprofil`` — bis dahin identisch,
weil die Korrektur nie ausgesetzt war) und der **Rohprognose** (Σ ``lern_soll_stundenprofil_kwh``, OpenMeteo gekappt,
unkorrigiert). Gepaart wird nur, wo beide einen Fehler haben; Zählerlücken wie HA (``tage_ohne_tagesvergleich``) und die
IST-Stelle ``pv_ist_je_tag`` wie ``prognose_genauigkeit_service.eedc_mae_prozent``. Die Entscheidung trifft der Layer
(``core/berechnungen/prognose_korrektur_nutzen.korrektur_aussetzen``); der Zustand des Vortags liegt im Cache (beim Start
``False``).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select

from backend.core.berechnungen.prognose_genauigkeit import mae_prozent, relativer_tagesfehler_prozent
from backend.core.berechnungen.prognose_korrektur_nutzen import (
    KORREKTUR_FENSTER_TAGE,
    KorrekturNutzen,
    korrektur_aussetzen,
)
from backend.models.tages_energie_profil import TagesZusammenfassung

logger = logging.getLogger(__name__)

#: anlage_id → (Tag ISO, Ergebnis). Der Eintrag des Vortags trägt den Zustand für die Hysterese.
_nutzen_cache: dict[int, tuple[str, KorrekturNutzen]] = {}


def cache_leeren() -> None:
    """Modulzustand zurücksetzen (Tests; ein Worker öffnet viele Datenbanken)."""
    _nutzen_cache.clear()


async def _fehlerpaare(db, anlage_id: int, heute: date) -> tuple[list[float], list[float]]:
    """Relative Tagesfehler (Kaskade, roh) der letzten 30 Tage — nur Tage, an denen beide einen Fehler haben."""
    from backend.services.energie_profil.kanal_stunden import pv_ist_je_tag
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich
    from backend.services.prognose_genauigkeit_service import profil_tageswert_kwh

    von = heute - timedelta(days=KORREKTUR_FENSTER_TAGE)
    res = await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum < heute,
        )
    )
    tageszeilen = res.scalars().all()
    if not tageszeilen:
        return [], []
    ohne = await tage_ohne_tagesvergleich(db, anlage_id, "pv", von=von, bis=heute)
    ist_je_tag = await pv_ist_je_tag(db, anlage_id, tageszeilen)
    kaskade: list[float] = []
    roh: list[float] = []
    for tz in tageszeilen:
        if tz.datum in ohne:
            continue
        reihe = tz.pv_prognose_kaskade_stundenprofil or tz.pv_prognose_stundenprofil
        ist = ist_je_tag.get(tz.datum)
        e_k = relativer_tagesfehler_prozent(profil_tageswert_kwh(reihe), ist)
        e_r = relativer_tagesfehler_prozent(profil_tageswert_kwh(tz.lern_soll_stundenprofil_kwh), ist)
        if e_k is not None and e_r is not None:
            kaskade.append(e_k)
            roh.append(e_r)
    return kaskade, roh


async def korrektur_nutzen(db, anlage_id: int, heute: date) -> KorrekturNutzen:
    """Der Wächter-Stand der Anlage für ``heute`` — je Tag einmal gerechnet, danach aus dem Cache."""
    tag = heute.isoformat()
    alt = _nutzen_cache.get(anlage_id)
    if alt is not None and alt[0] == tag:
        return alt[1]
    bisher = alt[1].ausgesetzt if alt is not None else False
    try:
        kaskade, roh = await _fehlerpaare(db, anlage_id, heute)
    except Exception as e:  # der Kanon darf am Wächter nicht sterben — dann gilt die Korrektur
        logger.warning("Korrektur-Wächter Anlage %s: %s: %s", anlage_id, type(e).__name__, e)
        return KorrekturNutzen(None, None, 0, False)
    mae_k, mae_r, n = mae_prozent(kaskade), mae_prozent(roh), len(kaskade)
    nutzen = KorrekturNutzen(
        mae_kaskade_prozent=mae_k,
        mae_roh_prozent=mae_r,
        tage=n,
        ausgesetzt=korrektur_aussetzen(mae_k, mae_r, bisher_ausgesetzt=bisher, tage=n),
    )
    _nutzen_cache[anlage_id] = (tag, nutzen)
    return nutzen
