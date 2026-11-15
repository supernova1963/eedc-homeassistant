"""HA-Abgleich des Diagnose-Pakets v4 — je Spiegel-Abschnitt wie der Nachtlauf, **nur lesend** (Konzept Q2, Bauplan §3.7, G4).

Auswahl wie ``kanal/konsistenz.konsistenz_anlage``: Kanäle der Art ``sum``/``stand``, Abschnitte aus ``nachfuellen.abschnitte``
(je Abschnitt dessen eigene Entity, Ü14), Prüfung ``konsistenz.pruefe_abschnitt_lesend`` — nie ``neu_spiegeln``. Bei Abweichung
HAs Stundenzeilen roh ab der ersten abweichenden Stunde, höchstens 744 (31 Tage) je Abschnitt.

Gründe: HA weg ⇒ ``verfuegbar: false, grund: "ha_nicht_erreichbar"``; keine Spiegel-Abschnitte ⇒ ``grund: "kein_spiegel"``
(dann wird HA gar nicht gefragt, ``verfuegbar: null``); je Abschnitt ``ha_kennt_sensor_nicht`` · ``ohne_summe`` ·
``ha_ohne_zeilen`` · ``fehler: <Typ>``; ``gekuerzt`` wie der Nachtlauf (``ha_historie_gekuerzt``). Zeitgrenze
``HA_ABGLEICH_ZEITGRENZE_S`` als Restbudget über alle Abschnitte (``asyncio.wait_for`` je Abschnitt, eigene Sitzung);
erreicht ⇒ ``status: "zeitgrenze"``, übrige Abschnitte ``grund: "nicht_geprueft"``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from sqlalchemy import and_, select

from backend.models.kanal import ART_STAND, ART_SUM, Kanal, KanalQuelle
from backend.services.kanal import konsistenz
from backend.services.kanal.nachfuellen import Sitzungen, abschnitte

HA_ABGLEICH_ZEITGRENZE_S = 60
HA_ZEILEN_MAX = 744
_STUNDE = 3600


async def _spiegel_abschnitte(sitzungen: Sitzungen, anlage_id: int) -> list[tuple[Kanal, object]]:
    async with sitzungen() as db:
        kanaele = list((await db.execute(select(Kanal).where(and_(
            Kanal.anlage_id == anlage_id, Kanal.art.in_([ART_SUM, ART_STAND]),
        )).order_by(Kanal.key))).scalars().all())
        quellen = {k.id: list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all())
                   for k in kanaele}
    return [(k, ab) for k in kanaele for ab in abschnitte(quellen[k.id])]


def _eintrag(kanal: Kanal, ab) -> dict:
    return {"kanal_key": kanal.key, "entity": ab.eid, "von": ab.von, "bis": ab.bis, "zeilen_spiegel": None,
            "zeilen_ha": None, "faktor": None, "gleich": None, "erste_abweichung": None, "grund": None, "gekuerzt": None,
            "dauer_ms": None, "ha_zeilen": []}


def _ha_zeilen(ha_svc, ab, t0: int) -> list[dict]:
    """HAs Stundenzeilen roh ab ``t0``, höchstens 744 und nie über das Abschnittsende."""
    bis = t0 + (HA_ZEILEN_MAX - 1) * _STUNDE
    if ab.bis is not None:
        bis = min(bis, ab.bis - _STUNDE)
    roh = ha_svc.get_stundenzeilen_mehrere({ab.eid: t0 - 1}, bis)
    return list(roh.get(ab.eid, (None, []))[1])[:HA_ZEILEN_MAX]


async def _pruefe(sitzungen: Sitzungen, kanal: Kanal, ab, ha_svc, e: dict, budget: float) -> None:
    bef = await asyncio.wait_for(konsistenz.pruefe_abschnitt_lesend(sitzungen, kanal, ab, ha_svc), timeout=budget)
    if bef is None:
        e["zeilen_spiegel"], e["grund"] = 0, "ohne_spiegelzeilen"
        return
    e.update(zeilen_spiegel=bef.zeilen_spiegel, zeilen_ha=bef.zeilen_ha, faktor=bef.faktor, gekuerzt=bef.gekuerzt)
    if bef.grund:
        e["grund"] = bef.grund
        return
    if bef.fehler is not None:
        e["grund"] = f"fehler: {type(bef.fehler).__name__}"
        return
    e["gleich"] = bef.erste_abweichung is None
    if bef.erste_abweichung is not None:
        e["erste_abweichung"] = bef.erste_abweichung
        e["ha_zeilen"] = await asyncio.to_thread(_ha_zeilen, ha_svc, ab, bef.erste_abweichung)


async def ha_abgleich(sitzungen: Sitzungen, anlage_id: int, *, ha_svc=None,
                      uhr: Callable[[], float] = time.monotonic, zeitgrenze_s: Optional[float] = None) -> dict:
    """``lage.ha_abgleich`` einer Anlage (Format Bauplan §3.3)."""
    grenze = HA_ABGLEICH_ZEITGRENZE_S if zeitgrenze_s is None else zeitgrenze_s
    out = {"verfuegbar": None, "grund": None, "status": "ok", "zeitgrenze_s": grenze, "abschnitte": []}
    teile = await _spiegel_abschnitte(sitzungen, anlage_id)
    if not teile:
        out["grund"] = "kein_spiegel"
        return out
    if ha_svc is None:
        from backend.services.ha_statistics_service import get_ha_statistics_service

        ha_svc = get_ha_statistics_service()
    out["verfuegbar"] = bool(ha_svc.is_available)
    if not out["verfuegbar"]:
        out["grund"] = "ha_nicht_erreichbar"
        return out
    start = uhr()
    for kanal, ab in teile:
        e = _eintrag(kanal, ab)
        out["abschnitte"].append(e)
        rest = grenze - (uhr() - start)
        if out["status"] == "zeitgrenze" or rest <= 0:
            out["status"], e["grund"] = "zeitgrenze", "nicht_geprueft"
            continue
        t0 = uhr()
        try:
            await _pruefe(sitzungen, kanal, ab, ha_svc, e, rest)
        except asyncio.TimeoutError:
            out["status"], e["grund"] = "zeitgrenze", "zeitgrenze"
        except Exception as ex:  # noqa: BLE001 — ein Abschnitt hält die übrigen nicht auf
            e["grund"] = f"fehler: {type(ex).__name__}"
        e["dauer_ms"] = int(round((uhr() - t0) * 1000))
    return out
