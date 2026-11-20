"""Angaben eines Zähler-Kanals für die Abfrage beim Sensorwechsel (Sensorwechsel mit Grund, Bauplan B-2; Sitzung 3b).

Lesend: erste Stunde, Zahl der Tage, letzter **Zählerstand** (Spalte ``state`` — der Stand, den der bisherige Sensor zuletzt
zeigte, wie ihn Home Assistant und die Wert-Spalte der Fläche zeigen; nicht HAs Statistik-Summe, Bauplan §11 Nr. 47), der
Zählerstand der neuen HA-Entität jetzt, Beginn der jüngsten nicht verworfenen Quelle, die Quelle zu einer Stunde, die erste
schon geschriebene Stunde ab einem Zeitpunkt und der bisherige Zuwachs einer Stunde (über ``lesen.stunden`` — der eine
Kanal-Leser, keine eigene Rechnung). Aufrufer: ``services/zuordnung_wechsel/abfrage.py`` (Dialog: erster Wert, Tage, Stände,
Vorgabe «falsch seit») und ``zaehler_getauscht.py`` (welcher Weg zur Stunde des Tauschs gilt, welche Stunde der Nachtrag einer
Fortsetzung trägt und was sie bisher zählt).

Schwesterdateien: ``korrektur.py`` (Kanal-Schicht der Korrektur), ``naht.py`` (Fortsetzung bei MQTT).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_SUM, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal.fenster import kalendertag_der_stunde

_STUNDE = 3600


async def kanal_des_schluessels(db: AsyncSession, anlage_id: int, key: str) -> Optional[Kanal]:
    return (await db.execute(select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == key)))).scalar_one_or_none()


async def quelle_zur_stunde(db: AsyncSession, kanal_id: int, ts: int) -> Optional[KanalQuelle]:
    """Die Quelle, die zur Stunde ``ts`` gilt (größtes ``gueltig_ab ≤ ts`` — wie ``lesen``, auch eine verworfene);
    ``None`` = vor der ersten Quelle des Kanals."""
    return (await db.execute(select(KanalQuelle).where(and_(KanalQuelle.kanal_id == kanal_id, KanalQuelle.gueltig_ab <= ts))
                             .order_by(KanalQuelle.gueltig_ab.desc()).limit(1))).scalar_one_or_none()


async def angaben(db: AsyncSession, kanal: Kanal) -> tuple[Optional[datetime], int, Optional[float]]:
    """``(erste Stunde, Zahl der Kalendertage mit Zeilen, letzter Zählerstand)`` — ohne ``state`` keine Angabe."""
    stunden = list((await db.execute(select(KanalStatistik.start_ts).where(KanalStatistik.kanal_id == kanal.id)))
                   .scalars().all())
    if not stunden:
        return None, 0, None
    letzter = (await db.execute(select(KanalStatistik.state).where(and_(
        KanalStatistik.kanal_id == kanal.id, KanalStatistik.state.is_not(None)))
        .order_by(KanalStatistik.start_ts.desc()).limit(1))).scalar_one_or_none()
    return (datetime.fromtimestamp(min(stunden)), len({kalendertag_der_stunde(int(s)) for s in stunden}),
            None if letzter is None else float(letzter))


def _stand_kurzzeit(ha_svc, eid: str, art: str, jetzt: datetime) -> Optional[float]:
    """Korrekturrunde Lab-K W6: der jüngste Stand (``state``) aus HAs Kurzzeitstatistik (5-Minuten-Zeilen der letzten Stunde)
    in der Einheit des Kanals (dieselbe Umrechnung wie der Spiegel, ``schreiber._mengen_faktor``; ein Stand nie umgerechnet).
    ``None``, wenn HA dort keine Zeile führt (dann die jüngste Stundenzeile)."""
    from backend.models.kanal import ART_STAND
    from backend.services.kanal.schreiber import _mengen_faktor

    with ha_svc._verbindung() as conn:
        meta = ha_svc.get_metadata(conn, eid)
    if meta is None:
        return None
    stand = ha_svc.get_value_at(eid, jetzt, 60, True, True)
    faktor = 1.0 if art == ART_STAND else _mengen_faktor(meta)
    return None if stand is None or faktor is None else round(float(stand) * faktor, 3)


async def zaehlerstand_ha_jetzt(ha_svc, kanal_id: int, art: str, eid: str) -> Optional[float]:
    """Der Zählerstand (``state``) von ``eid`` jetzt in der Einheit des Kanals: der jüngste aus HAs Kurzzeitstatistik
    (Lab-K W6 — in der Stunde des Tauschs führt HA für den neuen Sensor noch keine Stundenzeile, und der letzte Stand des
    alten liegt nach seiner letzten Stundenzeile), sonst der der jüngsten Stundenzeile (dieselbe Umrechnung wie der Spiegel);
    ``None``, wenn HA keine Zeile oder keinen Stand führt."""
    from backend.services.kanal.nachfuellen import _zeilen_aus_ha

    kurz = await asyncio.to_thread(_stand_kurzzeit, ha_svc, eid, art, datetime.now())
    if kurz is not None:
        return kurz
    zeile = await asyncio.to_thread(ha_svc.get_stundenzeile_bis, eid, datetime.now().timestamp())
    if zeile is None:
        return None
    ts = int(round(zeile["start_ts"]))
    gelesen = await asyncio.to_thread(ha_svc.get_stundenzeilen_mehrere, {eid: ts - 1}, ts)
    if eid not in gelesen:
        return None
    meta, roh = gelesen[eid]
    zeilen = _zeilen_aus_ha(kanal_id, art, meta, [z for z in roh if int(round(z["start_ts"])) == ts]) or []
    wert = zeilen[0]["state"] if zeilen else None
    return None if wert is None else float(wert)


async def beginn_juengste_quelle(db: AsyncSession, kanal_id: int) -> Optional[datetime]:
    """Beginn der jüngsten nicht verworfenen Quelle als örtliche Zeit ohne Zone — über die Quellzeilen derselben Kennung
    zurück, die sie fortsetzen (Naht des Stundenlaufs, Nachtrag eines «Zähler getauscht»): Beginn ist die erste Zeile dieser
    Folge, nicht die jüngste Fortsetzung (Bauplan §11 Nr. 54)."""
    quellen = list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id)
                                     .order_by(KanalQuelle.gueltig_ab.desc()))).scalars().all())
    folge = [q for q in quellen if q.verworfen_ts is None]
    if not folge:
        return None
    juengste = folge[0]
    beginn = juengste.gueltig_ab
    for q in quellen[quellen.index(juengste) + 1:]:
        if q.verworfen_ts is not None or (q.familie, q.statistic_id) != (juengste.familie, juengste.statistic_id):
            break
        beginn = q.gueltig_ab
    return datetime.fromtimestamp(int(beginn))


async def beginn_quelle_vor(db: AsyncSession, kanal_id: int, ts: int) -> Optional[datetime]:
    """Beginn der Quelle, die **vor** ``ts`` galt (größtes nicht verworfenes ``gueltig_ab < ts``), über die Quellzeilen
    derselben Kennung zurück wie ``beginn_juengste_quelle`` — die Vorgabe «falsch seit» beim Nachtragen eines Grunds
    (Sitzung 4): die bisherige Quelle ist die vor dem Wechsel, nicht die jüngste. ``None`` = vor ``ts`` keine Quelle."""
    quellen = list((await db.execute(select(KanalQuelle).where(and_(KanalQuelle.kanal_id == kanal_id,
                                                                    KanalQuelle.gueltig_ab < ts))
                                     .order_by(KanalQuelle.gueltig_ab.desc()))).scalars().all())
    folge = [q for q in quellen if q.verworfen_ts is None]
    if not folge:
        return None
    letzte = folge[0]
    beginn = letzte.gueltig_ab
    for q in quellen[quellen.index(letzte) + 1:]:
        if q.verworfen_ts is not None or (q.familie, q.statistic_id) != (letzte.familie, letzte.statistic_id):
            break
        beginn = q.gueltig_ab
    return datetime.fromtimestamp(int(beginn))


async def erste_zeile_ab(db: AsyncSession, kanal_id: int, ts: int) -> Optional[int]:
    """``start_ts`` der ersten geschriebenen Stunde ab ``ts`` (``None`` = noch keine)."""
    return (await db.execute(select(KanalStatistik.start_ts).where(and_(
        KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts >= ts))
        .order_by(KanalStatistik.start_ts).limit(1))).scalar_one_or_none()


async def erste_zeile(db: AsyncSession, kanal_id: int) -> Optional[datetime]:
    """Die erste geschriebene Stunde des Kanals (örtlich ohne Zone; ``None`` = keine Zeile)."""
    ts = (await db.execute(select(func.min(KanalStatistik.start_ts)).where(KanalStatistik.kanal_id == kanal_id))).scalar_one()
    return None if ts is None else datetime.fromtimestamp(int(ts))


async def zuwachs_der_stunde(db: AsyncSession, kanal: Kanal, ts: int) -> Optional[float]:
    """Der Zuwachs, den die geschriebene Stunde ``ts`` bisher zählt (Kanalwert der Zeile − Kanalwert des vorigen Stands,
    samt Versatz der geltenden Quelle — ``lesen.stunden``, wie jede Stunden-Sicht); ``None`` ohne vorigen Stand oder bei
    einem Kanal, der keine Menge ist."""
    from backend.services.kanal.lesen import stunden

    if kanal.art != ART_SUM:
        return None
    werte = (await stunden(db, kanal, ts, ts + _STUNDE)).werte
    return next((w.change for w in werte if w.start_ts == ts), None)
