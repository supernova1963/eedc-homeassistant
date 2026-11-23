"""Einmal-Lauf beim Start: den abgeleiteten Heimlade-Kanal ab dem ersten markierten Erfassungs-Stillstand neu schreiben lassen
(Fund-Päckchen H, H2; Halt H-NG1-a, Entscheid Master: Option b).

**Warum.** Seit Nachtrag G (NG1) rechnet der abgeleitete Kanal des PV-Anteils der Heimladung (``kanal/abgeleitet.py``,
``abgeleitet:inv:<id>:ladung_pv_kwh``) aus einer Stunde mit der Marke eines Erfassungs-Stillstands keinen Anteil mehr
(``core/berechnungen/spannen.stillstand_ohne_ladeanteil``). Die Regel wirkt für jede Stunde, die der Stundenlauf danach
schreibt; schon gespeicherte Stunden behielten ihren PV-Teil, bis eedc sie neu schreibt — eine von eedc verursachte
falsche Zahl, die ein Monat ohne gepflegtes «Heim: PV» aus dem Kanal liest (N-631).

**Was.** Je Anlage und je abgeleitetem Heimlade-Kanal mit Zeilen: liegt ein markierbares Stillstands-Fenster in seinem
Bereich (``kanal/stillstand.fenster_im_bereich``, vom ersten bis zum letzten Tag mit Zeile), werden seine Zeilen ab dem Beginn
des ersten solchen Fensters gelöscht (``kanal/abgeleitet.verwerfe_ab``, nur dieser Kanal) — der nächste Stundenlauf schreibt
sie mit der Regel neu. Keine Anlage ohne solchen Kanal oder ohne Fenster wird angefasst; gespeicherte Monatswerte bleiben;
kein HA-Abruf, kein Netz. Einmal je Installation (``_apply_once``, Name ``funde_h_heimladung_abgeleitet_ab_stillstand``).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

NAME = "funde_h_heimladung_abgeleitet_ab_stillstand"


async def heimladung_ab_stillstand_neu(session: AsyncSession) -> dict[int, int]:
    """Returns: je Anlage die Zahl der gelöschten Zeilen (nur Anlagen, an denen etwas gelöscht wurde)."""
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.stillstand import fenster_im_bereich

    kanaele = (await session.execute(
        select(Kanal.anlage_id, Kanal.id, Kanal.key, func.min(KanalStatistik.start_ts), func.max(KanalStatistik.start_ts))
        .join(KanalStatistik, KanalStatistik.kanal_id == Kanal.id)
        .where(and_(Kanal.key.like("abgeleitet:inv:%:ladung_pv_kwh")))
        .group_by(Kanal.id)
    )).all()
    out: dict[int, int] = {}
    for anlage_id, _kid, key, erste, letzte in kanaele:
        fenster = await fenster_im_bereich(session, anlage_id, datetime.fromtimestamp(erste).date(),
                                           datetime.fromtimestamp(letzte).date())
        if not fenster:
            continue
        ab = min(f.von_ts for f in fenster)
        n = await verwerfe_ab(session, anlage_id, ab, nur=lambda k, key=key: k == key)
        if n:
            out[anlage_id] = out.get(anlage_id, 0) + n
            logger.info("H2: %s (Anlage %s) ab %s neu zu schreiben: %s Zeilen verworfen", key, anlage_id,
                        datetime.fromtimestamp(ab).isoformat(), n)
    return out
