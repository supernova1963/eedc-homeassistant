"""Kanal-Bausteine des Nachlaufs eines Sensorwechsels (Sensorwechsel mit Grund, Bauplan B-6 Schritt 3, §10 Nr. 34) — seit
Weg B nur noch für das Ansetzen eines Wechsels «bleiben» (``zuordnung_wechsel/ansatz.py``) und «Daten vor der Änderung löschen»
(``services/feld_loeschen.py``).

* ``KanalKorrektur`` — was der Lauf im Kanal getan hat bzw. noch tun soll (``w0``, ``h0``, Versatz, abgeleitete Kanäle).
* ``_referenz`` / ``_ha_wert`` — letzter Stand vor einem Zeitpunkt im Kanal bzw. der Wert einer HA-Zeile in der Einheit des Kanals.
* ``fuelle_kanal`` — der Abschnitt der neuen Quelle ab ``h0`` mit dem Blockleser des Konsistenzlaufs (``nachfuellen.neu_spiegeln``)
  bis zur letzten vollen Stunde vor jetzt (``fuell_ende``, Lab-K F1).
* **Abgeleitete Kanäle** (Bauplan §10 Nr. 34): nur die vom Feld abhängigen (``abhaengige_abgeleitete``, ``gehoert_zu``) werden
  verworfen und im selben Lauf nach dem Füllen neu geschrieben (``schreibe_abgeleitete_nach``: dieselben drei Schreiber wie der
  Stundenlauf).

Die Korrektur eines Kanals über ein verworfenes Intervall (``korrigiere_kanal``, Versatz R2, «Regel 2», Brücke einer MQTT-Lücke)
ist mit «verwerfen» seit Weg B, Sitzung B3a, entfernt.

Schwesterdateien: ``verwerfen.py`` (Werkbank und «löschen»), ``nachfuellen.py``, ``services/zuordnung_wechsel/korrektur.py``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_STAND, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal import merken

_STUNDE = 3600


@dataclass
class KanalKorrektur:
    """Was der Nachlauf im Kanal getan hat bzw. noch tun soll (für Lauf, Aktivität und Proben)."""

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


async def fuelle_kanal(sitzungen, anlage_id: int, erg: KanalKorrektur, *, ha_svc, bis_ts: int) -> int:
    """Der Abschnitt der neuen Quelle ab ``h0`` mit dem Blockleser des Konsistenzlaufs (``neu_spiegeln``)."""
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


async def schreibe_abgeleitete_nach(sitzungen, anlage_id: int, erg: KanalKorrektur, zeitpunkt, *,
                                    immer: bool = False) -> int:
    """Nach dem Füllen: die verworfenen abhängigen Kanäle im selben Lauf neu schreiben — dieselben drei Schreiber wie der
    Stundenlauf (``schreiber.schreibe_kanaele_im_stundenlauf``), jeder ab seiner letzten Zeile bis zur Stunde vor
    ``zeitpunkt``; der Strom je Betriebsart nur für die betroffenen Wärmepumpen. ``immer`` (Ansetzen eines Wechsels,
    Korrekturrunde Lab-K F1): auch ohne verworfene Zeile fortschreiben — der Stundenlauf hat den Schlüssel mit offener
    Wechsel-Zeile ausgelassen, und die Stunde des Wechsels fehlte sonst bis zum nächsten Lauf."""
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.services.kanal.abgeleitet import schreibe_abgeleitete
    from backend.services.kanal.kosten import schreibe_kosten
    from backend.services.kanal.modus_strom import schreibe_modus_strom

    if not erg.abgeleitet_verworfen and not immer:
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
    """Obergrenze des Füllens und Lesens einer Korrektur bzw. eines Ansetzens: **die letzte volle Stunde vor jetzt** (Beginn
    der Zeile, die zur vollen Stunde endet) — dieselbe Stunde, bis zu der der Stundenlauf um :05 spiegelt
    (``schreiber._spiegel``) und bis zu der das Ansetzen seine Lage liest (``zuordnung_wechsel/ansatz.lage``). Korrekturrunde
    Lab-K (F1): bis dahin galt das Soll-Ende der Leser (``lesen.soll_ende``, 70 Minuten Verzug) — zwischen H:05 und H:10
    löschte eine Korrektur bzw. ein Ansetzen die vom Stundenlauf geschriebene Zeile ``H − 1`` und füllte nur bis ``H − 2``;
    die Stunde fehlte bis zum nächsten Stundenlauf. Führt Home Assistant die Zeile noch nicht (H:00–H:01), schreibt sie der
    Stundenlauf um :05."""
    return (int(jetzt_ts) // _STUNDE) * _STUNDE - _STUNDE
