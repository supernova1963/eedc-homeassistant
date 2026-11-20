"""Kanal-Schicht der **Korrektur** eines Sensorwechsels (Sensorwechsel mit Grund, Bauplan B-6 Schritt 3, §7 Nr. 6–9; Sitzung 3).

**Lage.** Ein Kanal (= ein zugeordnetes Zählerfeld) trägt im Korrektur-Intervall ``[falsch_seit, ab)`` Zeilen einer Quelle,
die nicht die richtige ist. Die richtige Quelle ist die heutige HA-Entität ``richtig`` (Art ``ha``); bei MQTT bzw. ohne HA gibt
es keine richtige Geschichte (dieselbe ``mqtt_key`` trägt beide Publisher) — dann ist **jede** Zeile im Intervall falsch.

**Ablauf** (``korrigiere_kanal``, eine Schreib-Sitzung, danach das Füllen):

1. **Falsche Abschnitte** sind die Quellen-Abschnitte ``[gueltig_ab, nächstes gueltig_ab)``, deren Quelle nicht ``richtig``
   ist und die das Intervall schneiden (der Abschnitt der ersten Quelle reicht nach unten offen: Zeilen vor ihrem ``gueltig_ab``
   gehören zu ihr). ``w0`` = Beginn des falschen Teils (``max(falsch_seit, Beginn des ersten falschen Abschnitts)``).
   Gelöscht werden **nur** deren Zeilen im Intervall — Zeilen eines Abschnitts der richtigen Quelle bleiben.
2. **Die richtige Quelle beginnt mit ihrer ersten Zeile** ``h0`` (erste HA-Zeile ab ``w0``) und trägt **einen** Versatz nach
   **R2** (§7 Nr. 6): ``Versatz = Kanalwert am letzten Stand vor w0 − Stand der richtigen Quelle`` — am selben Zeitpunkt, wenn HA
   ihn führt (die Stunden danach zählen ihren eigenen Zuwachs), sonst an ``h0`` (die erste Stunde zählt 0). Die leere Zeit
   zählt 0. Eine spätere Quellzeile derselben Entität entfällt (ihr Abschnitt geht in den neuen auf); spätere Quellen anderer
   Entitäten rücken um die Änderung des Versatzes mit (sonst sprünge der Kanal an ihrer Grenze).
3. **Die falsche Quelle bleibt mit** ``verworfen_ts`` **genau über die Zeit, die leer bleibt** (``[w0, h0)``, ohne ``h0`` bis
   zur nächsten Quelle): an ``w0`` eine Quellzeile mit Marke (die vorhandene wird markiert, sonst eine neue mit der Herkunft der
   dort geltenden Quelle), weitere falsche Quellzeilen in der leeren Zeit werden markiert. Trägt der Kanal nach ``ab`` Zeilen
   ohne eigene Quellgrenze (MQTT: derselbe Schlüssel), beginnt an der ersten eine Quellzeile, die dort ohne Zuwachs ansetzt —
   **U3 b (Rechenweg G7 (b)):** ist die leere Zeit eine Lücke ohne Höhenwechsel (``bruecke``; dieselbe Regel wie die Leser der
   Reihe, ``zeitpunkt.ohne_hoehenwechsel``) und die Quelle MQTT, setzt sie stattdessen mit der Menge der Zeit an
   (``core/berechnungen/rohstand_rand.bruecke``: Stand danach − Stand davor, wie an jeder Zählerlücke).
4. **Füllen** mit dem Blockleser des Konsistenzlaufs (``nachfuellen.neu_spiegeln`` ab ``h0`` bis zum Soll-Ende), gemerkte
   Tage der Anlage verworfen. **Abgeleitete Kanäle** (Bauplan §10 Nr. 34): nur die vom Feld abhängigen
   (``abhaengige_abgeleitete``) ab ``w0`` bis zum Ende verworfen und im selben Lauf nach dem Füllen neu geschrieben
   (``schreibe_abgeleitete_nach``: dieselben drei Schreiber wie der Stundenlauf) — kein Sichtfenster mit fehlenden Zeilen.

``_erste`` und die Marke ``kanal_nachfuellung`` bleiben unangetastet (Startlauf, Anstoß, Stände-Nachbau, Konsistenzlauf wie
bisher); ``abschnitte()`` liefert für eine verworfene Quelle keinen Abschnitt (§7 Nr. 8), der Leser nennt einen Zeitraum über
sie nicht voll (``lesen.GRUND_VERWORFEN``, §7 Nr. 7), ``BewusstLeer`` prüft die erste Zeile je Abschnitt (§7 Nr. 9), und der
Stundenlauf beginnt hinter einem verworfenen Abschnitt immer eine neue Quelle (``schreiber``).

Schwesterdateien: ``verwerfen.py`` (Werkbank, ältere Bausteine), ``nachfuellen.py``, ``services/zuordnung_wechsel/korrektur.py``
(der Dienst über alle Schichten).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_STAND, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal import merken
from backend.services.kanal.fenster import kalendertag_der_stunde

_STUNDE = 3600


@dataclass(frozen=True)
class _Abschnitt:
    quelle: KanalQuelle
    von: Optional[int]          # None = nach unten offen (erste Quelle)
    bis: Optional[int]          # None = offen


def _abschnitte(quellen: list[KanalQuelle]) -> list[_Abschnitt]:
    qs = sorted(quellen, key=lambda q: q.gueltig_ab)
    return [_Abschnitt(q, None if i == 0 else q.gueltig_ab, qs[i + 1].gueltig_ab if i + 1 < len(qs) else None)
            for i, q in enumerate(qs)]


def ist_richtig(q: KanalQuelle, richtig: Optional[str]) -> bool:
    return richtig is not None and q.familie == FAMILIE_SPIEGEL and q.statistic_id == richtig and q.verworfen_ts is None


def _schneidet(a: _Abschnitt, f: Optional[int], ab: int) -> bool:
    return (a.von is None or a.von < ab) and (a.bis is None or f is None or a.bis > f)


def _teil(a: _Abschnitt, f: Optional[int], ab: int) -> tuple[Optional[int], int]:
    """Der Teil eines Abschnitts im Intervall ``[f, ab)`` (``None`` = nach unten offen)."""
    unten = a.von if f is None else (f if a.von is None else max(f, a.von))
    return unten, ab if a.bis is None else min(ab, a.bis)


def _zeilen_bed(kanal_id: int, unten: Optional[int], oben: int):
    bed = [KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts < oben]
    if unten is not None:
        bed.append(KanalStatistik.start_ts >= unten)
    return and_(*bed)


@dataclass(frozen=True)
class KanalLage:
    """Was die Korrektur im Kanal vorfindet (ohne Schreiben)."""

    kanal: Optional[Kanal]
    quellen: tuple[KanalQuelle, ...]
    falsch: tuple[_Abschnitt, ...]
    #: Beginn des falschen Teils; ``None`` ⇒ im Intervall trägt keine falsche Quelle Zeilen oder Abschnitte.
    w0: Optional[int]
    zeilen: int
    tage: tuple[date, ...] = ()

    @property
    def offen(self) -> bool:
        """Ein falscher Abschnitt ist noch nicht verworfen (sonst hat ein früherer Lauf ihn schon erledigt)."""
        return any(a.quelle.verworfen_ts is None for a in self.falsch)


async def kanal_lage(db: AsyncSession, anlage_id: int, key: str, f: Optional[int], ab: int,
                     richtig: Optional[str]) -> KanalLage:
    kanal = (await db.execute(select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == key)))).scalar_one_or_none()
    if kanal is None:
        return KanalLage(None, (), (), None, 0)
    quellen = list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id)
                                     .order_by(KanalQuelle.gueltig_ab))).scalars().all())
    falsch = tuple(a for a in _abschnitte(quellen) if not ist_richtig(a.quelle, richtig) and _schneidet(a, f, ab))
    if not falsch:
        return KanalLage(kanal, tuple(quellen), (), None, 0)
    stunden: list[int] = []
    for a in falsch:
        unten, oben = _teil(a, f, ab)
        stunden += list((await db.execute(select(KanalStatistik.start_ts).where(_zeilen_bed(kanal.id, unten, oben))))
                        .scalars().all())
    # Nach unten offen (Werkbank «vor dem Sensorbeginn»): der verworfene Abschnitt beginnt an der ersten Quelle — davor gilt
    # keine Quelle (die Zeilen dort werden mit gelöscht, wie bisher).
    erste = falsch[0].von if falsch[0].von is not None else falsch[0].quelle.gueltig_ab
    if f is not None:
        erste = max(f, erste)
    tage = tuple(sorted({kalendertag_der_stunde(int(s)) for s in stunden}))
    return KanalLage(kanal, tuple(quellen), falsch, int(erste), len(stunden), tage)


@dataclass
class KanalKorrektur:
    """Was ``korrigiere_kanal`` getan hat (für Bericht, Aktivität und Proben)."""

    key: str
    kanal_id: Optional[int] = None
    w0: Optional[int] = None
    h0: Optional[int] = None
    versatz: Optional[float] = None
    geloescht: int = 0
    markiert: int = 0
    neu_gespiegelt: int = 0
    quellen: list[tuple] = field(default_factory=list)
    #: Die abhängigen Familien der abgeleiteten Kanäle (``None`` = alle) und ihre ab ``w0`` verworfenen Zeilen.
    abgeleitet_familien: Optional[frozenset] = None
    abgeleitet_verworfen: int = 0
    abgeleitet_neu: int = 0


def _wertspalte(art: str) -> str:
    return "state" if art == ART_STAND else "sum"


async def _referenz(db: AsyncSession, kanal: Kanal, w0: int) -> Optional[tuple[int, float]]:
    """Letzter Stand vor ``w0`` als ``(start_ts, Brückenwert = Rohwert + Versatz seines Abschnitts)``."""
    spalte = getattr(KanalStatistik, _wertspalte(kanal.art))
    zeile = (await db.execute(select(KanalStatistik.start_ts, spalte).where(and_(
        KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts < w0, spalte.is_not(None)))
        .order_by(KanalStatistik.start_ts.desc()).limit(1))).one_or_none()
    if zeile is None:
        return None
    off = (await db.execute(select(KanalQuelle.offset).where(and_(
        KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab <= zeile[0]))
        .order_by(KanalQuelle.gueltig_ab.desc()).limit(1))).scalar_one_or_none()
    return int(zeile[0]), float(zeile[1]) + float(off or 0.0)


async def _ha_wert(ha_svc, kanal: Kanal, eid: str, ts: int) -> Optional[float]:
    """Wert der HA-Zeile ``ts`` in der Einheit des Kanals (dieselbe Umrechnung wie der Spiegel)."""
    from backend.services.kanal.nachfuellen import _zeilen_aus_ha

    gelesen = await asyncio.to_thread(ha_svc.get_stundenzeilen_mehrere, {eid: ts - 1}, ts)
    if eid not in gelesen:
        return None
    meta, roh = gelesen[eid]
    zeilen = _zeilen_aus_ha(kanal.id, kanal.art, meta, [z for z in roh if int(round(z["start_ts"])) == ts]) or []
    wert = zeilen[0][_wertspalte(kanal.art)] if zeilen else None
    return None if wert is None else float(wert)


async def erste_ha_zeile(ha_svc, eid: str, w0: int, bis_ts: int) -> Optional[int]:
    """``h0``: die erste HA-Zeile der richtigen Entität ab ``w0`` (bis ``bis_ts``). HA nicht erreichbar ⇒ Fehler."""
    from backend.services.kanal.nachfuellen import _ha_erreichbar

    kz = await asyncio.to_thread(ha_svc.get_stundenzeilen_kennzahlen, eid, w0 - 1, bis_ts)
    if kz is None:
        _ha_erreichbar(ha_svc)
        return None
    if not kz.get("anzahl") or kz.get("erste_ts") is None:
        return None
    return int(round(kz["erste_ts"]))


async def _versatz(db, kanal: Kanal, ref: Optional[tuple[int, float]], ha_svc, eid: str, h0: int,
                   spaeter: Optional[KanalQuelle]) -> float:
    """R2 (§7 Nr. 6)."""
    if ref is None:
        return float(spaeter.offset) if spaeter is not None else 0.0
    wert = await _ha_wert(ha_svc, kanal, eid, ref[0])
    if wert is None:
        wert = await _ha_wert(ha_svc, kanal, eid, h0)
    return ref[1] - (wert or 0.0)


def _spaetere_richtige(quellen: list[KanalQuelle], ab: int, richtig: Optional[str]) -> list[KanalQuelle]:
    """Die Quellzeilen ab ``ab − 1 h``, die die richtige Entität ohne Unterbrechung fortsetzen (sie gehen im neuen Abschnitt
    auf). Ab ``ab − 1 h``, weil eine Kanal-Quelle eine Stunde vor dem Stand der Reihe beginnt (die Zeile ``ab − 1 h`` trägt den
    Stand um ``ab``; Bauplan «Zu §14» Nr. 97, Messblatt 4b-0 e) — sonst rückte eine spätere Quelle nicht mit (A → X → A → C)."""
    out = []
    for q in sorted(quellen, key=lambda q: q.gueltig_ab):
        if q.gueltig_ab < ab - _STUNDE:
            continue
        if not ist_richtig(q, richtig):
            break
        out.append(q)
    return out


async def _quellen_umschreiben(db: AsyncSession, kanal: Kanal, lage: KanalLage, ab: int, h0: Optional[int],
                               versatz: Optional[float], ref: Optional[tuple[int, float]], richtig: Optional[str],
                               jetzt_ts: int, bruecke: bool = False) -> int:
    """Quellzeilen nach Schritt 2/3 (Modul-Docstring). Returns: Zahl der neu markierten bzw. angelegten verworfenen Quellen."""
    w0 = lage.w0
    quellen = list(lage.quellen)
    leer_bis = h0 if h0 is not None else ab
    o_ref = None
    if ref is not None:
        o_ref = (await db.execute(select(KanalQuelle.offset).where(and_(
            KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab <= ref[0]))
            .order_by(KanalQuelle.gueltig_ab.desc()).limit(1))).scalar_one_or_none()
    vorher_bei_w0 = max((q for q in quellen if q.gueltig_ab <= w0), key=lambda q: q.gueltig_ab, default=lage.falsch[0].quelle)
    spaeter = _spaetere_richtige(quellen, ab, richtig) if h0 is not None else []
    verschiebung = (versatz - float(spaeter[0].offset)) if (spaeter and versatz is not None) else None
    weg = set(id(q) for q in spaeter)
    markiert = 0
    for q in quellen:
        if w0 < q.gueltig_ab < ab and h0 is not None and q.gueltig_ab >= h0:
            weg.add(id(q))                          # im neuen Abschnitt der richtigen Quelle
    for q in quellen:
        if id(q) in weg:
            await db.delete(q)
        elif w0 <= q.gueltig_ab < leer_bis and not ist_richtig(q, richtig):
            markiert += q.verworfen_ts is None
            q.verworfen_ts = q.verworfen_ts or jetzt_ts
            if o_ref is not None:
                q.offset = float(o_ref)             # ohne Zeilen: trägt nur die Brücke für den nächsten Abschnitt
        elif verschiebung is not None and q.gueltig_ab > ab and spaeter and q.gueltig_ab > spaeter[-1].gueltig_ab:
            q.offset = float(q.offset) + verschiebung
    await db.flush()
    vorhanden = {q.gueltig_ab for q in quellen if id(q) not in weg}
    if (h0 is None or h0 > w0) and w0 not in vorhanden:
        db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=w0, familie=vorher_bei_w0.familie,
                           statistic_id=vorher_bei_w0.statistic_id,
                           offset=float(o_ref if o_ref is not None else vorher_bei_w0.offset), verworfen_ts=jetzt_ts))
        markiert += 1
    if h0 is not None:
        alt = next((q for q in quellen if q.gueltig_ab == h0 and id(q) not in weg), None)
        if alt is not None:
            alt.familie, alt.statistic_id, alt.offset, alt.verworfen_ts = FAMILIE_SPIEGEL, richtig, float(versatz), None
        else:
            db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=h0, familie=FAMILIE_SPIEGEL, statistic_id=richtig,
                               offset=float(versatz)))
    await db.flush()
    await _fortsetzung_nach_ab(db, kanal, ab, leer_bis, ref, o_ref, bruecke)
    return markiert


async def _fortsetzung_nach_ab(db: AsyncSession, kanal: Kanal, ab: int, leer_bis: int, ref, o_ref,
                               bruecke: bool = False) -> None:
    """Trägt der Kanal ab ``ab`` Zeilen ohne eigene Quellgrenze (MQTT: derselbe Schlüssel über den Wechsel), gälte der
    verworfene Abschnitt auch für sie — dann beginnt an der ersten eine Quellzeile, die ohne Zuwachs ansetzt; mit ``bruecke``
    an einer MQTT-Quelle mit der Menge der leeren Zeit (``bruecken_versatz``, U3 b G7 (b))."""
    if leer_bis < ab:
        return
    spalte = getattr(KanalStatistik, _wertspalte(kanal.art))
    erste = (await db.execute(select(KanalStatistik.start_ts, spalte).where(and_(
        KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts >= ab, spalte.is_not(None)))
        .order_by(KanalStatistik.start_ts).limit(1))).one_or_none()
    if erste is None:
        return
    geltend = (await db.execute(select(KanalQuelle).where(and_(
        KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab <= erste[0]))
        .order_by(KanalQuelle.gueltig_ab.desc()).limit(1))).scalar_one_or_none()
    if geltend is None or geltend.verworfen_ts is None:
        return
    offset = (ref[1] - float(erste[1])) if ref is not None else float(o_ref or 0.0)
    if bruecke and ref is not None:
        offset = await bruecken_versatz(db, kanal, geltend, ref, int(erste[0])) or offset
    db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=int(erste[0]), familie=geltend.familie,
                       statistic_id=geltend.statistic_id, offset=offset))
    await db.flush()


async def bruecken_versatz(db: AsyncSession, kanal: Kanal, quelle: KanalQuelle, ref: tuple[int, float],
                           erste_ts: int) -> Optional[float]:
    """U3 b (G7 (b)): der Versatz der ersten Quellzeile nach einer leeren Zeit ohne Höhenwechsel einer MQTT-Quelle — die Zeile
    ``erste_ts`` trägt den Kanalwert davor (``ref``) plus ``Stand(erste) − Stand(ref)`` (``rohstand_rand.bruecke``). ``None``,
    wenn die Quelle keine MQTT-Mitschrift ist oder ein Stand fehlt (dann ohne Zuwachs wie bisher). Dieselbe Regel liest
    ``ist_ueberbrueckt`` (die Auskunft «Zeit verworfen» muss wahr bleiben, P-1 aus U3 a)."""
    from backend.core.berechnungen.rohstand_rand import bruecke
    from backend.models.kanal import FAMILIE_MITSCHRIFT
    from backend.services.kanal.nachfuellen import STAENDE_HA_PRAEFIX

    if quelle.familie != FAMILIE_MITSCHRIFT or (quelle.statistic_id or "").startswith(STAENDE_HA_PRAEFIX):
        return None
    zeilen = {int(t): (st, w) for t, st, w in (await db.execute(select(
        KanalStatistik.start_ts, KanalStatistik.state, getattr(KanalStatistik, _wertspalte(kanal.art))).where(and_(
            KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts.in_((ref[0], erste_ts)))))).all()}
    (st_ref, _w0), (st_erste, w_erste) = zeilen.get(ref[0], (None, None)), zeilen.get(erste_ts, (None, None))
    if st_ref is None or st_erste is None or w_erste is None:
        return None
    return bruecke(ref[1], float(st_ref), float(st_erste), float(w_erste))


async def ist_ueberbrueckt(db: AsyncSession, anlage_id: int, key: str, von_ts: int, bis_ts: int) -> bool:
    """Setzt der Kanal des Schlüssels nach der verworfenen Zeit ``[von_ts, bis_ts)`` mit ihrer Menge an (``bruecken_versatz``)?
    Ja, wenn die erste Quellzeile ab ``bis_ts`` (nach der verworfenen) genau diesen Versatz trägt."""
    kanal = (await db.execute(select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == key)))).scalar_one_or_none()
    if kanal is None:
        return False
    quellen = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id)
                                .order_by(KanalQuelle.gueltig_ab))).scalars().all()
    nach = next((q for q in quellen if q.gueltig_ab >= bis_ts and q.verworfen_ts is None), None)
    if nach is None or not any(von_ts - _STUNDE <= q.gueltig_ab < bis_ts and q.verworfen_ts for q in quellen):
        return False
    ref = await _referenz(db, kanal, min(q.gueltig_ab for q in quellen if q.verworfen_ts and q.gueltig_ab >= von_ts - _STUNDE))
    erwartet = await bruecken_versatz(db, kanal, nach, ref, nach.gueltig_ab) if ref is not None else None
    return erwartet is not None and abs(erwartet - float(nach.offset)) < 1e-6


async def korrigiere_kanal(db: AsyncSession, anlage_id: int, key: str, f: Optional[int], ab: int, richtig: Optional[str],
                           *, ha_svc=None, jetzt_ts: int, bis_ts: int, bruecke: bool = False) -> KanalKorrektur:
    """Schritte 1–3 in der Sitzung des Aufrufers (kein Commit): löschen, Quellen umschreiben, abgeleitete Kanäle und gemerkte
    Tage verwerfen. ``richtig`` = heutige HA-Entität oder ``None`` (MQTT/ohne HA — nichts wird gefüllt); ``ha_svc`` ``None``
    ⇒ ebenfalls ohne Füllen. Das Füllen (Schritt 4) macht ``fuelle_kanal`` nach dem Commit."""
    from backend.services.kanal.abgeleitet import verwerfe_ab

    erg = KanalKorrektur(key)
    lage = await kanal_lage(db, anlage_id, key, f, ab, richtig)
    if lage.kanal is None or lage.w0 is None:
        return erg
    kanal, erg.w0, erg.kanal_id = lage.kanal, lage.w0, lage.kanal.id
    h0 = await erste_ha_zeile(ha_svc, richtig, lage.w0, bis_ts) if (richtig and ha_svc is not None) else None
    from backend.services.kanal.verwerfen import loesche_zeilen_zwischen

    for a in lage.falsch:
        unten, oben = _teil(a, f, ab)
        erg.geloescht += await loesche_zeilen_zwischen(db, kanal.id, unten, oben)
    ref = await _referenz(db, kanal, lage.w0)          # der letzte Stand, der stehen bleibt
    versatz = None
    if h0 is not None:
        versatz = await _versatz(db, kanal, ref, ha_svc, richtig, h0,
                                 next(iter(_spaetere_richtige(list(lage.quellen), ab, richtig)), None))
    erg.markiert = await _quellen_umschreiben(db, kanal, lage, ab, h0, versatz, ref, richtig, jetzt_ts, bruecke)
    erg.abgeleitet_familien = await abhaengige_abgeleitete(db, anlage_id, key)
    erg.abgeleitet_verworfen = await verwerfe_ab(db, anlage_id, lage.w0,
                                                 nur=lambda k: gehoert_zu(erg.abgeleitet_familien, k))
    merken.invalidiere(anlage_id, db=db)
    erg.quellen = [(q.gueltig_ab, q.familie, q.statistic_id, round(float(q.offset), 6), q.verworfen_ts)
                   for q in (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id)
                                              .order_by(KanalQuelle.gueltig_ab))).scalars().all()]
    erg.h0, erg.versatz = h0, versatz
    return erg


async def fuelle_kanal(sitzungen, anlage_id: int, erg: KanalKorrektur, *, ha_svc, bis_ts: int) -> int:
    """Schritt 4: der Abschnitt der richtigen Quelle ab ``h0`` mit dem Blockleser des Konsistenzlaufs (``neu_spiegeln``)."""
    from backend.services.kanal.nachfuellen import neu_spiegeln

    if erg.h0 is None or erg.kanal_id is None:
        return 0
    erg.neu_gespiegelt = await neu_spiegeln(sitzungen, erg.kanal_id, erg.h0, ha_svc=ha_svc, bis_ts=bis_ts)
    merken.invalidiere(anlage_id)
    return erg.neu_gespiegelt


# ── Abgeleitete Kanäle: nur die vom Feld abhängigen (Bauplan §10 Nr. 34) ─────────


#: Familien der abgeleiteten Kanäle; der Strom je Betriebsart heißt ``modus_strom:<inv_id>`` (je Wärmepumpe).
PV_ANTEIL, KOSTEN, MODUS_STROM = "pv_anteil", "kosten", "modus_strom:"


async def abhaengige_abgeleitete(db: AsyncSession, anlage_id: int, key: str) -> Optional[frozenset]:
    """Die Familien abgeleiteter Kanäle, die aus dem Feld ``key`` rechnen — ``None`` = unbekannter Schlüssel ⇒ alle.

    Ladezähler der Wallbox-Achse, Netzbezug, Einspeisung ⇒ PV-Anteil der Heimladung (``abgeleitet.py``: ``L(h)`` ist die
    Summe aller Geräte der Achse, also alle Kanäle dieser Familie) · Strom-Kanäle einer Wärmepumpe ⇒ deren Strom je
    Betriebsart (``modus_strom.py``) · Bilanz-/PV-Zähler (``kosten._KATEGORIEN``) und Preis ⇒ Kosten (``kosten.py``). Die
    Kategorie des Felds ist die Abbildung des Tagespfads (``snapshot/keys._categorize_counter``); ein Feld mit bekannter
    Kategorie, aus der kein abgeleiteter Kanal rechnet (Speicher, Sonstiges-Verbraucher …), hat keine abhängigen."""
    from backend.core.berechnungen.spannen import achse_der_kategorie
    from backend.models.investition import Investition
    from backend.services.kanal.abgeleitet import ACHSE_LADUNG
    from backend.services.kanal.kosten import _KATEGORIEN, PREIS_KEY
    from backend.services.snapshot.keys import _categorize_counter

    if key == PREIS_KEY:
        return frozenset({KOSTEN})
    teile = key.split(":")
    inv = None
    if teile[0] == "basis" and len(teile) == 2:
        kat = _categorize_counter(teile[1], None, None)
    elif teile[0] == "inv" and len(teile) == 3 and teile[1].isdigit():
        inv = (await db.execute(select(Investition).where(and_(
            Investition.anlage_id == anlage_id, Investition.id == int(teile[1]))))).scalar_one_or_none()
        if inv is None:
            return None
        kat = _categorize_counter(teile[2], inv.typ, inv.parameter)
    else:
        return None
    if kat is None:
        return None
    familien = set()
    if kat in ("netzbezug", "einspeisung") or (inv is not None and achse_der_kategorie(kat) == ACHSE_LADUNG):
        familien.add(PV_ANTEIL)
    if kat in _KATEGORIEN:
        familien.add(KOSTEN)
    if inv is not None and inv.typ == "waermepumpe" and achse_der_kategorie(kat) == "waermepumpe":
        familien.add(f"{MODUS_STROM}{inv.id}")
    return frozenset(familien)


def gehoert_zu(familien: Optional[frozenset], kanal_key: str) -> bool:
    """Gehört der abgeleitete Kanal ``kanal_key`` zu einer der Familien (``None`` = alle)?"""
    from backend.services.kanal.abgeleitet import abgeleitet_key
    from backend.services.kanal.kosten import KOSTEN_KANAELE
    from backend.services.kanal.modus_strom import alle_keys

    if familien is None:
        return True
    teile = kanal_key.split(":")
    if PV_ANTEIL in familien and len(teile) == 4 and kanal_key == abgeleitet_key(teile[2]):
        return True
    if KOSTEN in familien and kanal_key in KOSTEN_KANAELE:
        return True
    return any(f.startswith(MODUS_STROM) and kanal_key in alle_keys(f[len(MODUS_STROM):]) for f in familien)


async def schreibe_abgeleitete_nach(sitzungen, anlage_id: int, erg: KanalKorrektur, zeitpunkt) -> int:
    """Nach dem Füllen: die verworfenen abhängigen Kanäle im selben Lauf neu schreiben — dieselben drei Schreiber wie der
    Stundenlauf (``schreiber.schreibe_kanaele_im_stundenlauf``), jeder ab seiner letzten Zeile bis zur Stunde vor
    ``zeitpunkt``; der Strom je Betriebsart nur für die betroffenen Wärmepumpen."""
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.services.kanal.abgeleitet import schreibe_abgeleitete
    from backend.services.kanal.kosten import schreibe_kosten
    from backend.services.kanal.modus_strom import schreibe_modus_strom

    if not erg.abgeleitet_verworfen:
        return 0
    f = erg.abgeleitet_familien
    async with sitzungen() as db:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all())
        n = 0
        if f is None or PV_ANTEIL in f:
            n += await schreibe_abgeleitete(db, anlage, zeitpunkt, invs=invs)
        wps = [i for i in invs if f is None or f"{MODUS_STROM}{i.id}" in f]
        if wps:
            n += await schreibe_modus_strom(db, anlage, zeitpunkt, invs=wps)
        if f is None or KOSTEN in f:
            n += await schreibe_kosten(db, anlage, zeitpunkt)
    merken.invalidiere(anlage_id)
    erg.abgeleitet_neu = n
    return n


def fuell_ende(jetzt_ts: int) -> int:
    """Obergrenze des Füllens: das Soll-Ende des Stundenlaufs (``lesen.soll_ende``) — danach schreibt er selbst."""
    from backend.services.kanal.lesen import soll_ende

    return soll_ende(jetzt_ts)
