"""Lese-Hilfe der Kanalstatistik — **nur für die Wächter** (HA-Bauform E2, Auftrag Punkt 5).

Das ist NICHT die Lese-Schicht aus E3 (``zeitraum``/``reihe``/``mittel`` mit Abdeckung, Bauplan §5). Keine
Sicht, keine Route, kein Dienst ruft diese Funktionen; der Wächter ``test_kanal_symmetrie.py`` und die
Proben tun es. Ein Leser in ``api/`` oder ``services/`` außerhalb ``services/kanal/`` wäre ein Vorgriff
auf E3.

**Was ein Kanalwert ist** (Leseregel, Bauplan §3a Nachtrag 06.10.):

* Art ``sum``: ``sum + offset`` der für die Stunde geltenden Quelle (``kanal_quelle`` mit dem größten
  ``gueltig_ab ≤ start_ts``). Vor der ersten Zeile ist der Wert 0 — HAs Summe beginnt bei 0
  (``recorder_statistics.py:1720f.``: ein Zeitraum vor der ersten Zeile hat den Anfangsstand 0).
* Art ``stand``: der Stand ist ``state`` **roh** (die Zahl auf dem Zähler, F-58). ``offset`` dient nur
  der Differenz über eine Quellgrenze: Δ = (``state`` + ``offset``)(bis) − (``state`` + ``offset``)(von).
  Ohne Zeile vor ``von`` gibt es kein Δ (ein Stand hat keinen Nullpunkt).
* Art ``mean``: kein Δ; der Wert einer Stunde ist ``mean``.

**Rangfolge** (Spiegel, sonst Mitschrift — Bauplan §2): Eine Stunde hat genau EINE Zeile (Primärschlüssel
``(kanal_id, start_ts)``); welche Familie sie trägt, entscheiden die Schreiber (Neu-Laden ersetzt nur
Spiegelzeilen). Der Leser liest die eine Zeile und nennt ihre Familie mit. Die Familie ``bestand`` bleibt **unbelegt** (Entscheid Gernot 06.10., Bauplan §3b): die bisherigen Stunden- und
Tageszeilen werden nicht in Kanäle umgewandelt; sie bleiben die Quelle für Zeiträume, die die Kanäle nicht voll decken.

Schwesterdateien: ``schreiber.py``, ``nachfuellen.py``, ``konsistenz.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_MEAN, ART_STAND, ART_SUM, Kanal, KanalQuelle, KanalStatistik


@dataclass(frozen=True)
class Kanalwert:
    """Der Wert eines Kanals in einer Stunde."""

    start_ts: int
    wert: Optional[float]
    familie: str


def _spalte(art: str) -> str:
    return {ART_SUM: "sum", ART_STAND: "state", ART_MEAN: "mean"}[art]


async def _quellen(db: AsyncSession, kanal_id: int) -> list[KanalQuelle]:
    return list((await db.execute(
        select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id).order_by(KanalQuelle.gueltig_ab)
    )).scalars().all())


def _offset(quellen: list[KanalQuelle], start_ts: int) -> float:
    off = 0.0
    for q in quellen:
        if q.gueltig_ab <= start_ts:
            off = float(q.offset)
        else:
            break
    return off


async def _letzte_bis(db: AsyncSession, kanal: Kanal, ts: int) -> Optional[KanalStatistik]:
    spalte = getattr(KanalStatistik, _spalte(kanal.art))
    return (await db.execute(
        select(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts <= ts, spalte.is_not(None),
        )).order_by(KanalStatistik.start_ts.desc()).limit(1)
    )).scalar_one_or_none()


async def kanalwert(db: AsyncSession, kanal: Kanal, start_ts: int) -> Optional[Kanalwert]:
    """Der Wert der Zeile GENAU dieser Stunde (``None``: keine Zeile)."""
    z = (await db.execute(select(KanalStatistik).where(and_(
        KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts == start_ts,
    )))).scalar_one_or_none()
    if z is None:
        return None
    roh = getattr(z, _spalte(kanal.art))
    if roh is None or kanal.art != ART_SUM:
        return Kanalwert(z.start_ts, None if roh is None else float(roh), z.familie)
    return Kanalwert(z.start_ts, float(roh) + _offset(await _quellen(db, kanal.id), z.start_ts), z.familie)


async def delta(db: AsyncSession, kanal: Kanal, ts_von: int, ts_bis: int) -> Optional[float]:
    """Δ eines Mengen- oder Stand-Kanals zwischen zwei Zeitpunkten.

    Wert(t) = Wert der letzten Zeile mit ``start_ts ≤ t`` (Lücke = die Energie steht in der nächsten
    vorhandenen Zeile, wie bei HA). ``None``: keine Zeile bis ``ts_bis`` — oder beim Stand keine vor
    ``ts_von``.
    """
    if kanal.art == ART_MEAN:
        raise ValueError(f"Kanal {kanal.key}: ein Mittelwert hat kein Δ")
    b = await _letzte_bis(db, kanal, ts_bis)
    if b is None:
        return None
    a = await _letzte_bis(db, kanal, ts_von)
    quellen = await _quellen(db, kanal.id)
    spalte = _spalte(kanal.art)
    wert_b = float(getattr(b, spalte)) + _offset(quellen, b.start_ts)
    if a is None:
        return wert_b if kanal.art == ART_SUM else None
    return wert_b - (float(getattr(a, spalte)) + _offset(quellen, a.start_ts))
