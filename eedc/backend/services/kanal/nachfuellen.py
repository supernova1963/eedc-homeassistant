"""Nachfüllen Spiegel und Neu-Laden — HA-Bauform E2 (Auftrag Punkte 1 und 3, Bauplan §4).

**Nachfüllen (einmalig je Anlage).** Für jeden Kanal, den der Stundenlauf aus HA spiegelt
(Zähler: ``snapshot/writer._build_counter_map``; Mittelwerte: ``schreiber._mean_zuordnung``), holt es
die **ganze Historie der heutigen Entity** aus HAs Langzeitstatistik: ``sum``/``state`` bzw.
``mean``/``min``/``max`` wörtlich, Einheit wie der Stundenlauf (``schreiber._mengen_faktor``).

* **Rückwärts in Blöcken.** Gefüllt wird nur, was VOR der ersten Zeile des Kanals liegt (ab da schreibt
  der Stundenlauf fort). Je Block: die letzte HA-Zeile vor der bisher ersten Kanal-Zeile suchen
  (``get_stundenzeile_bis`` — springt über HA-Lücken), ``BLOCK_STUNDEN`` davor lesen, schreiben,
  committen. **Kein HA-Abruf in einer offenen Schreib-Transaktion:** gelesen wird zwischen zwei
  Sitzungen, geschrieben in einer kurzen eigenen (``sitzungen()`` je Block) — SQLite hält den
  Schreib-Lock nur für das Einfügen eines Blocks, der Stundenlauf wartet höchstens so lange.
* **Wiederaufnehmbar, idempotent.** Der Fortschritt ist die erste Zeile des Kanals selbst: ein
  abgebrochener Lauf setzt dort fort, ein zweiter Lauf findet vor ihr keine HA-Zeile mehr und schreibt
  nichts. Eingefügt wird ``ON CONFLICT DO NOTHING`` — eine Zeile einer anderen Familie bleibt stehen.
* **Nur die Vorgeschichte DERSELBEN Quelle.** Ist die erste Quelle des Kanals nicht der Spiegel der
  heutigen Entity (Sensortausch, MQTT davor), wird nichts gefüllt und das gezählt — die Historie einer
  anderen Entity gehört nicht in diese Reihe (für diese Zeit bleiben die bisherigen Zeilen die Quelle, §3b).
* **Quelle.** Die Zeilen sind wörtlich; ihr ``offset`` ist der der ersten Quelle (dieselbe Rohreihe),
  deren ``gueltig_ab`` wird auf die neue erste Stunde gesenkt.

**Neu-Laden** (``neu_spiegeln``, vom Konsistenzlauf gerufen): ersetzt ab einer Stunde die
**Spiegelzeilen** eines Kanals durch HAs heutige Zeilen — Bestand- und Mitschriftzeilen bleiben stehen.
Je Spiegel-Abschnitt (eine Quelle = eine Entity) blockweise vorwärts; der letzte Block eines Abschnitts
verschiebt in DERSELBEN Transaktion die ``offset`` aller späteren Quellen um die Änderung des Kanalwerts
am Abschnittsende — damit bleibt jedes Δ nach der Naht so, wie HA es nennt.

**Marke je Kanal** (``kanal_nachfuellung``: Kanal + Entity): ein Kanal mit Marke für seine heutige Entity
wird nie wieder bei HA angefragt; ein später zugeordneter Sensor (neuer Kanal) oder eine neue Entity (neue
``kanal_quelle``) hat keine Marke und wird beim nächsten Lauf gefüllt.

**Auslöser:** ``nachfuellen_nach_dem_start`` (Hintergrund-Aufgabe nach dem Start, alle Zuordnungen) und
``nachfuellen_anstossen`` (vom Stundenlauf NACH seiner Sitzung, nur schon angelegte Kanäle ohne Marke).
Fortschritt und Ergebnis als Aktivität in der Schreib-Sitzung (N-532), nur wenn ein Kanal offen war.

**Stand E2:** wird geschrieben und nachgefüllt, von keiner Sicht gelesen. Die Familie ``bestand`` bleibt **unbelegt** (Entscheid Gernot 06.10., Bauplan §3b): die bisherigen Stunden- und
Tageszeilen werden nicht in Kanäle umgewandelt; sie bleiben die Quelle für Zeiträume, die die Kanäle nicht voll decken.

Schwesterdateien: ``schreiber.py``, ``konsistenz.py``, ``lesen.py``.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import AsyncContextManager, Callable, Optional

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import (
    ART_MEAN,
    ART_STAND,
    ART_SUM,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalNachfuellung,
    KanalQuelle,
    KanalStatistik,
)

logger = logging.getLogger(__name__)

Sitzungen = Callable[[], AsyncContextManager[AsyncSession]]

#: Stunden je Lese- und Schreibblock (31 Tage). Ein Block eines Zählers sind höchstens 744 Zeilen —
#: das Einfügen hält den Schreib-Lock für Millisekunden.
BLOCK_STUNDEN = 24 * 31
_STUNDE = 3600
_TOL = 1e-9


def _unix(dt: datetime) -> int:
    return int(round(dt.timestamp()))


@dataclass
class _Ziel:
    key: str
    eid: str
    art: str
    einheit: str


@dataclass
class NachfuellErgebnis:
    anlage_id: int
    kanaele: int = 0
    gefuellt: int = 0
    zeilen: int = 0
    bloecke: int = 0
    uebersprungen: Counter = field(default_factory=Counter)
    fehler: int = 0
    markiert: int = 0

    def als_dict(self) -> dict:
        return {"kanaele": self.kanaele, "gefuellt": self.gefuellt, "zeilen": self.zeilen,
                "bloecke": self.bloecke, "markiert": self.markiert,
                "uebersprungen": dict(sorted(self.uebersprungen.items())), "fehler": self.fehler}


# ── Plan (eine kurze Lese-Sitzung) ──────────────────────────────────────────


async def _ziele(db: AsyncSession, anlage, jetzt: datetime) -> list[_Ziel]:
    """Dieselbe Auswahl wie der Stundenlauf: Zähler-Spiegel und Mittelwert-Spiegel."""
    from backend.services.kanal import schreiber as sch

    k = await sch._kontext(db, anlage, jetzt)
    ziele: list[_Ziel] = []
    for key, eid in sorted(k.counter_map.items()):
        art, einheit = sch._art_und_einheit(key, k.invs)
        if art in (ART_SUM, ART_STAND):
            ziele.append(_Ziel(key, eid, art, einheit))
    for key, eid in sorted(sch._mean_zuordnung(k).items()):
        ziele.append(_Ziel(key, eid, ART_MEAN, ""))
    return ziele


async def _erste(db: AsyncSession, anlage_id: int, key: str) -> tuple[Optional[Kanal], Optional[int], Optional[KanalQuelle]]:
    kanal = (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == key))
    )).scalar_one_or_none()
    if kanal is None:
        return None, None, None
    erste_ts = (await db.execute(
        select(func.min(KanalStatistik.start_ts)).where(KanalStatistik.kanal_id == kanal.id)
    )).scalar_one_or_none()
    erste_q = (await db.execute(
        select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id).order_by(KanalQuelle.gueltig_ab).limit(1)
    )).scalar_one_or_none()
    return kanal, erste_ts, erste_q


# ── Zeilen aus HA ───────────────────────────────────────────────────────────


def _zeilen_aus_ha(kanal_id: int, art: str, meta, roh: list[dict]) -> Optional[list[dict]]:
    """HA-Zeilen → Kanalzeilen, wörtlich (Einheit wie ``schreiber._spiegel`` bzw. ``_mean_spiegel``).
    ``None``: der Stundenlauf spiegelt diesen Sensor nicht (Menge ohne ``sum`` und ohne Energie-Einheit, #200)."""
    from backend.services.kanal.schreiber import _mal, _mengen_faktor

    if art == ART_MEAN:
        return [{"kanal_id": kanal_id, "start_ts": int(round(z["start_ts"])), "sum": None, "state": None,
                 "mean": float(z["mean"]), "min": None if z["min"] is None else float(z["min"]),
                 "max": None if z["max"] is None else float(z["max"]), "familie": FAMILIE_SPIEGEL}
                for z in roh if z["mean"] is not None]
    faktor = 1.0 if art == ART_STAND else _mengen_faktor(meta)   # ein Stand wird nie umgerechnet (F-58)
    if faktor is None:
        return None
    return [{"kanal_id": kanal_id, "start_ts": int(round(z["start_ts"])), "sum": _mal(z["sum"], faktor),
             "state": _mal(z["state"], faktor), "mean": None, "min": None, "max": None,
             "familie": FAMILIE_SPIEGEL} for z in roh]


async def _einfuegen(db: AsyncSession, zeilen: list[dict]) -> int:
    from backend.services.kanal.schreiber import _zeilen_einfuegen

    return await _zeilen_einfuegen(db, zeilen)


# ── Nachfüllen ──────────────────────────────────────────────────────────────


async def _fuelle_kanal(sitzungen: Sitzungen, anlage_id: int, ziel: _Ziel, ha_svc, ts_bis_jetzt: int,
                        erg: NachfuellErgebnis, block_stunden: int) -> tuple[Optional[int], Optional[str], int]:
    """Vorgeschichte EINES Kanals füllen. Returns ``(kanal_id, grund, neue_zeilen)`` — ``kanal_id`` ``None``,
    solange es den Kanal nicht gibt (HA hat keine Zeile); ``grund`` nennt, warum nichts zu füllen war."""
    from backend.services.kanal.schreiber import kanaele_holen

    async with sitzungen() as db:
        kanal, erste_ts, erste_q = await _erste(db, anlage_id, ziel.key)
    kanal_id = kanal.id if kanal is not None else None
    if erste_q is not None and (erste_q.familie != FAMILIE_SPIEGEL or erste_q.statistic_id != ziel.eid):
        return kanal_id, "vorgeschichte_andere_quelle", 0
    obergrenze = (erste_ts - 1) if erste_ts is not None else ts_bis_jetzt
    neu = 0
    while True:
        anker = await asyncio.to_thread(ha_svc.get_stundenzeile_bis, ziel.eid, obergrenze)
        if anker is None:
            # „Historie zu Ende" — oder HA ist still weg (WebSocket: die Leser liefern dann None statt zu
            # werfen). Nur das erste setzt eine Marke; das zweite ist ein Fehler, der nächste Lauf setzt fort.
            _ha_erreichbar(ha_svc)
            break
        a_ts = float(anker["start_ts"])
        gelesen = await asyncio.to_thread(
            ha_svc.get_stundenzeilen_mehrere, {ziel.eid: a_ts - block_stunden * _STUNDE}, a_ts)
        if ziel.eid not in gelesen:
            _ha_erreichbar(ha_svc)
            return kanal_id, "ha_kennt_sensor_nicht", neu
        meta, roh = gelesen[ziel.eid]
        if not roh:
            _ha_erreichbar(ha_svc)
            break
        async with sitzungen() as db:
            if kanal is None:
                if ziel.art == ART_MEAN:
                    kanal = Kanal(anlage_id=anlage_id, key=ziel.key, art=ART_MEAN, einheit=meta.unit or "")
                    db.add(kanal)
                    await db.flush()
                else:
                    kanal = (await kanaele_holen(db, anlage_id, {ziel.key: (ziel.art, ziel.einheit)}))[ziel.key]
                kanal_id = kanal.id
            elif ziel.art == ART_MEAN and kanal.einheit != (meta.unit or ""):
                return kanal_id, "einheit_abweichend", neu
            zeilen = _zeilen_aus_ha(kanal.id, ziel.art, meta, roh)
            if zeilen is None:
                return kanal_id, "ohne_summe", neu
            if not zeilen:
                obergrenze = int(round(roh[0]["start_ts"])) - 1
                continue
            neu += await _einfuegen(db, zeilen)
            erste_neu = min(z["start_ts"] for z in zeilen)
            q = (await db.execute(
                select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id)
                .order_by(KanalQuelle.gueltig_ab).limit(1)
            )).scalar_one_or_none()
            if q is None:
                db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=erste_neu, familie=FAMILIE_SPIEGEL,
                                   statistic_id=ziel.eid, offset=0.0))
            elif q.gueltig_ab > erste_neu and q.familie == FAMILIE_SPIEGEL and q.statistic_id == ziel.eid:
                await db.execute(update(KanalQuelle).where(and_(
                    KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab == q.gueltig_ab,
                )).values(gueltig_ab=erste_neu))
        erg.bloecke += 1
        obergrenze = erste_neu - 1
    return kanal_id, None, neu


def _ha_erreichbar(ha_svc) -> None:
    """Wirft, wenn HA nicht (mehr) erreichbar ist — ein leeres Ergebnis heißt dann nichts."""
    if not ha_svc.is_available:
        raise RuntimeError("HA-Langzeitstatistik während des Nachfüllens nicht erreichbar")


async def _marken(db: AsyncSession, anlage_id: int) -> dict[str, tuple[int, Optional[str]]]:
    """``{kanal_key: (kanal_id, statistic_id der Marke | None)}`` aller Kanäle der Anlage — ein Statement."""
    rows = (await db.execute(
        select(Kanal.key, Kanal.id, KanalNachfuellung.statistic_id)
        .outerjoin(KanalNachfuellung, KanalNachfuellung.kanal_id == Kanal.id)
        .where(Kanal.anlage_id == anlage_id)
    )).all()
    return {key: (kid, sid) for key, kid, sid in rows}


async def nachfuellen_spiegel(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, ha_svc=None,
    block_stunden: int = BLOCK_STUNDEN, nur_vorhandene: bool = False, beim_beginn=None,
) -> NachfuellErgebnis:
    """Die Spiegel-Kanäle einer Anlage mit HAs ganzer Historie der heutigen Entity füllen — **je Kanal
    einmal** (Marke ``kanal_nachfuellung`` je Kanal und Entity).

    * Ein Kanal, dessen Marke auf seine heutige Entity zeigt, wird **nicht** bei HA angefragt
      (``schon_gefuellt``).
    * Ohne Marke (neuer Kanal, oder die Zuordnung zeigt jetzt auf eine andere Entity) wird gefüllt; die
      Marke entsteht danach — auch wenn es nichts zu füllen gab (``grund`` in ``ergebnis``), damit derselbe
      Kanal nicht stündlich neu fragt. Ein Fehler setzt keine Marke; der nächste Lauf setzt fort.
    * ``nur_vorhandene`` (Anstoß aus dem Stundenlauf): nur Kanäle, die es schon gibt — der Stundenlauf
      legt einen Kanal an, sobald HA für ihn liefert; ein Sensor ohne Langzeitstatistik kostet so keine
      Abfrage je Stunde. Der Startlauf prüft alle Zuordnungen.

    ``jetzt``: Uhr des Laufs; ohne Kanal-Zeile wird bis zur Stunde vor ``jetzt`` gefüllt (wie der
    Stundenlauf, der danach fortschreibt).
    """
    from backend.models.anlage import Anlage
    from backend.services.ha_statistics_service import get_ha_statistics_service

    ha_svc = ha_svc or get_ha_statistics_service()
    erg = NachfuellErgebnis(anlage_id)
    stunde = jetzt.replace(minute=0, second=0, microsecond=0)
    async with sitzungen() as db:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        ziele = await _ziele(db, anlage, stunde)
        marken = await _marken(db, anlage_id)
    offen = []
    for ziel in ziele:
        kid, sid = marken.get(ziel.key, (None, None))
        if sid == ziel.eid:
            erg.uebersprungen["schon_gefuellt"] += 1
        elif nur_vorhandene and kid is None:
            erg.uebersprungen["noch_kein_kanal"] += 1
        else:
            offen.append(ziel)
    erg.kanaele = len(offen)
    if not offen:
        return erg
    if not ha_svc.is_available:
        erg.uebersprungen["ha_nicht_erreichbar"] += 1
        return erg
    if beim_beginn is not None:
        await beim_beginn(erg)
    ts_bis_jetzt = _unix(stunde - timedelta(hours=1))
    for ziel in offen:
        try:
            kanal_id, grund, neu = await _fuelle_kanal(sitzungen, anlage_id, ziel, ha_svc, ts_bis_jetzt, erg,
                                                       block_stunden)
        except Exception as e:  # noqa: BLE001 — ein Kanal hält die übrigen nicht auf
            erg.fehler += 1
            logger.warning("Kanal-Nachfüllen %s (Anlage %s) abgebrochen: %s: %s",
                           ziel.key, anlage_id, type(e).__name__, e)
            continue
        if grund:
            erg.uebersprungen[grund] += 1
        if neu:
            erg.gefuellt += 1
            erg.zeilen += neu
        if kanal_id is None:
            continue                       # kein Kanal ⇒ keine Marke; der Stundenlauf legt ihn an, wenn HA liefert
        async with sitzungen() as db:
            await db.merge(KanalNachfuellung(
                kanal_id=kanal_id, statistic_id=ziel.eid, abgeschlossen_ts=_unix(jetzt),
                ergebnis={"zeilen": neu, **({"grund": grund} if grund else {})},
            ))
        erg.markiert += 1
    return erg


# ── Neu-Laden (Konsistenzlauf) ──────────────────────────────────────────────


@dataclass
class _Abschnitt:
    eid: str
    von: int          # erste Stunde der Quelle (gueltig_ab)
    bis: Optional[int]  # erste Stunde der nächsten Quelle (exklusiv) oder None


def abschnitte(quellen: list[KanalQuelle]) -> list[_Abschnitt]:
    """Spiegel-Abschnitte eines Kanals: je Spiegel-Quelle ``[gueltig_ab, nächstes gueltig_ab)``."""
    qs = sorted(quellen, key=lambda q: q.gueltig_ab)
    out = []
    for i, q in enumerate(qs):
        if q.familie == FAMILIE_SPIEGEL and q.statistic_id:
            out.append(_Abschnitt(q.statistic_id, q.gueltig_ab, qs[i + 1].gueltig_ab if i + 1 < len(qs) else None))
    return out


def _wertspalte(art: str) -> str:
    return "state" if art == ART_STAND else "sum"


async def _wert_am_ende(db: AsyncSession, kanal: Kanal, abschnitt: _Abschnitt) -> Optional[float]:
    spalte = getattr(KanalStatistik, _wertspalte(kanal.art))
    bed = [KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts >= abschnitt.von, spalte.is_not(None)]
    if abschnitt.bis is not None:
        bed.append(KanalStatistik.start_ts < abschnitt.bis)
    v = (await db.execute(select(spalte).where(and_(*bed)).order_by(KanalStatistik.start_ts.desc()).limit(1))).scalar_one_or_none()
    return None if v is None else float(v)


async def neu_spiegeln(
    sitzungen: Sitzungen, kanal_id: int, ab_ts: int, *, ha_svc, block_stunden: int = BLOCK_STUNDEN,
) -> int:
    """Spiegelzeilen eines Kanals ab ``ab_ts`` durch HAs heutige Zeilen ersetzen. Nie Bestand oder Mitschrift.

    Obergrenze ist die letzte Spiegelzeile zum Zeitpunkt des Plans — was danach kommt, schreibt der
    Stundenlauf. Untergrenze des Löschens ist HAs erste Zeile des Abschnitts: was HA nicht mehr hält, bleibt.
    HA unterwegs unerreichbar ⇒ Fehler, der Block wird nicht angefasst. Returns: Zahl der neu eingefügten Zeilen.
    """
    async with sitzungen() as db:
        kanal = (await db.execute(select(Kanal).where(Kanal.id == kanal_id))).scalar_one()
        quellen = list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id))).scalars().all())
        oben = (await db.execute(select(func.max(KanalStatistik.start_ts)).where(and_(
            KanalStatistik.kanal_id == kanal_id, KanalStatistik.familie == FAMILIE_SPIEGEL,
        )))).scalar_one_or_none()
    if oben is None or kanal.art not in (ART_SUM, ART_STAND, ART_MEAN):
        return 0
    neu = 0
    for ab in abschnitte(quellen):
        a = max(ab_ts, ab.von)
        e = oben if ab.bis is None else min(oben, ab.bis - 1)
        if a > e:
            continue
        # Untergrenze des Löschens: HAs erste Zeile des ABSCHNITTS. Hält HA den Anfang nicht mehr (z. B. „alte
        # Statistik löschen" nach einem Einheitenwechsel), bleibt darunter stehen, was da ist (Nachmessung E2, 2b).
        kz = await asyncio.to_thread(ha_svc.get_stundenzeilen_kennzahlen, ab.eid, ab.von - 1, e)
        if kz is None:
            _ha_erreichbar(ha_svc)
            continue                       # HA kennt die Entity nicht mehr — nichts löschen
        if not kz["anzahl"] or kz["erste_ts"] is None:
            continue
        ha_erste = int(round(kz["erste_ts"]))
        cursor = a - 1                     # exklusiv
        while cursor < e:
            ende = min(e, cursor + block_stunden * _STUNDE)
            gelesen = await asyncio.to_thread(ha_svc.get_stundenzeilen_mehrere, {ab.eid: cursor}, ende)
            if ab.eid not in gelesen:
                _ha_erreichbar(ha_svc)     # still weg ⇒ Fehler; sonst: HA kennt die Entity nicht mehr
                break                      # — in beiden Fällen nichts löschen
            meta, roh = gelesen[ab.eid]
            letzter = ende >= e
            if not roh:
                # HA liefert für diesen Block nichts (Statistik dort gelöscht?): NICHT nachziehen — ein
                # Neu-Laden soll eine Korrektur übernehmen, keine Historie wegwerfen.
                cursor = ende
                continue
            unten = max(cursor, ha_erste - 1)
            async with sitzungen() as db:
                vorher = await _wert_am_ende(db, kanal, ab) if (letzter and kanal.art != ART_MEAN) else None
                zeilen = _zeilen_aus_ha(kanal.id, kanal.art, meta, roh) or []
                await db.execute(delete(KanalStatistik).where(and_(
                    KanalStatistik.kanal_id == kanal.id, KanalStatistik.familie == FAMILIE_SPIEGEL,
                    KanalStatistik.start_ts > unten, KanalStatistik.start_ts <= ende,
                )))
                neu += await _einfuegen(db, zeilen)
                if letzter and kanal.art != ART_MEAN and ab.bis is not None and vorher is not None:
                    nachher = await _wert_am_ende(db, kanal, ab)
                    if nachher is not None and abs(nachher - vorher) > _TOL:
                        await db.execute(update(KanalQuelle).where(and_(
                            KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab >= ab.bis,
                        )).values(offset=KanalQuelle.offset + (nachher - vorher)))
            cursor = ende
    return neu


# ── Auslöser: Startlauf und Anstoß aus dem Stundenlauf ─────────────────────


async def nachfuellen_anlage(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, ha_svc=None,
    block_stunden: int = BLOCK_STUNDEN, nur_vorhandene: bool = False,
) -> NachfuellErgebnis:
    """``nachfuellen_spiegel`` mit Protokoll: „begonnen" und „abgeschlossen"/„unvollständig" — nur, wenn ein
    Kanal offen war (ein Lauf ohne offenen Kanal schreibt nichts, auch kein Protokoll). Jeder Eintrag in der
    Sitzung, die ihn schreibt (N-532)."""
    from backend.services.activity_service import log_activity

    async def _begonnen(e: NachfuellErgebnis) -> None:
        async with sitzungen() as db:
            await log_activity(kategorie="scheduler", aktion="Kanalstatistik: Nachfüllen aus HA begonnen",
                               details=f"{e.kanaele} Kanäle ohne Marke", anlage_id=anlage_id, db=db)

    erg = await nachfuellen_spiegel(sitzungen, anlage_id, jetzt=jetzt, ha_svc=ha_svc,
                                    block_stunden=block_stunden, nur_vorhandene=nur_vorhandene,
                                    beim_beginn=_begonnen)
    if not erg.kanaele or erg.uebersprungen.get("ha_nicht_erreichbar"):
        return erg
    async with sitzungen() as db:
        await log_activity(
            kategorie="scheduler",
            aktion="Kanalstatistik: Nachfüllen aus HA " + ("abgeschlossen" if erg.fehler == 0 else "unvollständig"),
            erfolg=erg.fehler == 0,
            details=(f"{erg.gefuellt} von {erg.kanaele} offenen Kanälen gefüllt, {erg.zeilen} Stundenzeilen in "
                     f"{erg.bloecke} Blöcken" + (f", {erg.fehler} Kanäle abgebrochen (nächster Lauf setzt fort)"
                                                  if erg.fehler else "")),
            details_json=erg.als_dict(), anlage_id=anlage_id, db=db,
        )
    return erg


async def nachfuellen_alle_anlagen(sitzungen: Sitzungen, *, jetzt: Optional[datetime] = None, ha_svc=None,
                                   nur_vorhandene: bool = False) -> list[NachfuellErgebnis]:
    from backend.models.anlage import Anlage

    async with sitzungen() as db:
        ids = list((await db.execute(select(Anlage.id).order_by(Anlage.id))).scalars().all())
    return [await nachfuellen_anlage(sitzungen, aid, jetzt=jetzt or datetime.now(), ha_svc=ha_svc,
                                     nur_vorhandene=nur_vorhandene) for aid in ids]


async def nachfuellen_nach_dem_start(*, warte_s: float = 120.0) -> None:
    """Hintergrund-Aufgabe nach dem Start (``main.py``): jeder Kanal ohne Marke für seine Entity.

    Blockiert weder den Start (eigene Aufgabe, erst nach ``warte_s``) noch den Stundenlauf (kurze
    Schreib-Transaktionen je Block, HA-Abrufe außerhalb). Ein Fehler bleibt hier und wird geloggt.
    """
    from backend.core.database import get_session

    try:
        await asyncio.sleep(warte_s)
        await nachfuellen_alle_anlagen(get_session)
    except Exception as e:  # noqa: BLE001 — eine Hintergrund-Aufgabe darf den Prozess nicht stören
        logger.warning("Kanal-Nachfüllen nach dem Start fehlgeschlagen: %s: %s", type(e).__name__, e)


#: Die laufende Anstoß-Aufgabe (höchstens eine — ein langer Lauf wird nicht verdoppelt).
_ANSTOSS: Optional[asyncio.Task] = None


def nachfuellen_anstossen(sitzungen: Optional[Sitzungen] = None, *, jetzt: Optional[datetime] = None,
                          ha_svc=None) -> Optional[asyncio.Task]:
    """Vom Stundenlauf NACH seiner Sitzung gerufen: Kanäle ohne Marke (neu angelegt oder neue Entity) im
    Hintergrund nachfüllen. Kanäle mit Marke kosten dabei keine HA-Abfrage, nur einen Blick in die Tabelle.

    Returns die Aufgabe (Proben warten darauf) oder ``None``, wenn noch eine läuft.
    """
    global _ANSTOSS
    if _ANSTOSS is not None and not _ANSTOSS.done():
        return None

    async def _lauf() -> None:
        from backend.core.database import get_session

        try:
            await nachfuellen_alle_anlagen(sitzungen or get_session, jetzt=jetzt, ha_svc=ha_svc,
                                           nur_vorhandene=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("Kanal-Nachfüllen (Anstoß Stundenlauf) fehlgeschlagen: %s: %s", type(e).__name__, e)

    _ANSTOSS = asyncio.get_running_loop().create_task(_lauf())
    return _ANSTOSS
