"""Rand eines Tagesfensters an einem gesperrten Stück (Lücke mit Höhenwechsel oder offenes Füllen) — das Laden zur Regel in
``core/berechnungen/zaehler_naht.py`` (Sensorwechsel 4b-1-K/-K2, Bauplan «Zu §14» Nr. 102, Nr. 112; U1).

Die Tagesansicht (``snapshot/aggregator._tagesdetail_boundary_diff_mit_grund``) und der Bereichs-Leser
(``snapshot/bereichs_leser._randstaende``) folgen an einem gesperrten Stück derselben Regel (``ende_der_luecke_davor``,
``endet_in_luecke``, ``traegt_messung``); die zwei Lese-Bausteine, die dafür an die Datenbank gehen, stehen hier — **ein** Ort
für beide Leser. Im Normalbetrieb (kein gesperrtes Stück) ruft sie keiner.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.zaehler_naht import traegt_messung
from backend.services.snapshot.reader import erster_stand_im_fenster, get_snapshot, reihe_im_fenster
from backend.services.zuordnung_wechsel.zeitpunkt import fortsetzungs_naehte


async def rand_nach_luecke(db: AsyncSession, anlage_id: int, sensor_key: str, sensor_id: Optional[str], quellen_energy,
                           ab: datetime, ts_ende: datetime) -> tuple[datetime, Optional[float]]:
    """Der linke Rand hinter einem gesperrten Stück: der Stand am Ende des Stücks (geheilt, wo die Quelle dort bekannt ist),
    sonst der erste Stand danach im Fenster; ``(ab, None)``, wenn das Fenster nicht über das Stück hinausreicht."""
    if ab >= ts_ende:
        return ab, None
    s0 = await get_snapshot(db, anlage_id, sensor_key, sensor_id, ab, quellen_energy=quellen_energy)
    if s0 is not None:
        return ab, s0
    von = await erster_stand_im_fenster(db, anlage_id, sensor_key, ab, ts_ende)
    if von is None or von >= ts_ende:
        return ab, None
    return von, await get_snapshot(db, anlage_id, sensor_key, sensor_id, von, quellen_energy=quellen_energy)


async def gemessen_ausserhalb_der_luecken(db: AsyncSession, anlage_id: int, sensor_key: str,
                                          rand_von: tuple[datetime, float], rand_bis: tuple[datetime, float]) -> bool:
    """Trägt das Fenster außerhalb der gesperrten Stücke eine Messung (``zaehler_naht.traegt_messung`` über die Ränder und
    die Stände dazwischen)? Nur gefragt, wenn der Schlüssel ein gesperrtes Stück hat."""
    folge = [rand_von, *await reihe_im_fenster(db, anlage_id, sensor_key, rand_von[0], rand_bis[0]), rand_bis]
    return traegt_messung(folge, await fortsetzungs_naehte(db, anlage_id, sensor_key))


__all__ = ["gemessen_ausserhalb_der_luecken", "rand_nach_luecke"]
