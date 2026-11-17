"""Räumen der Wechsel-Zeilen beim Löschen eines Geräts oder Innengeräts (Bauplan B-1).

Die Anlage räumt ``ON DELETE CASCADE`` (mit ``PRAGMA foreign_keys=ON``, ``core/database.py``). Ein Gerät und ein Innengerät
räumen ausdrücklich — aus demselben Grund wie die Messreihen (N-668, ``api/routes/investitionen/crud.py::_entferne_messreihen``):
die Schlüssel tragen nur die ID, und SQLite vergibt die ID der zuletzt angelegten Investition neu; blieben die Zeilen liegen,
gälte der Wechsel der gelöschten für die nächste Investition mit dieser ID.
"""

from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy import delete, select

from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel.zeitpunkt import vergiss


async def raeume_geraet(
    db, anlage_id: int, investition_id: int, betroffen: Optional[Callable[[str], bool]] = None,
) -> int:
    """Löscht die Wechsel-Zeilen ``inv:<id>:<feld>`` (``betroffen(feld)`` grenzt ein, z. B. auf entfallene Innengeräte).

    Returns: Anzahl gelöschter Zeilen."""
    praefix = f"inv:{int(investition_id)}:"
    rows = (await db.execute(select(ZuordnungWechsel.id, ZuordnungWechsel.sensor_key).where(
        ZuordnungWechsel.anlage_id == anlage_id,
        ZuordnungWechsel.sensor_key.startswith(praefix, autoescape=True),
    ))).all()
    ids = [rid for rid, key in rows if betroffen is None or betroffen(key[len(praefix):])]
    if ids:
        await db.execute(delete(ZuordnungWechsel).where(ZuordnungWechsel.id.in_(ids)))
        vergiss(db, anlage_id)
    return len(ids)
